"""Tennis : Elo par surface, probabilités de sets, critères surprise, pronos du moment et backtest."""
from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict

from . import tennis_data as td
from .data import PARIS
from .model import devig

SLAMS = ("Australian Open", "French Open", "Roland Garros", "Wimbledon", "US Open")
SURF_FR = {"Hard": "dur", "Indoor": "dur indoor", "Clay": "terre battue", "Grass": "gazon"}
ROUNDS_FR = {
    "1st Round": "1er tour", "2nd Round": "2e tour", "3rd Round": "3e tour", "4th Round": "8e de finale",
    "Round 1": "1er tour", "Round 2": "2e tour", "Round 3": "3e tour", "Round of 16": "8e de finale",
    "Quarterfinals": "Quart de finale", "Quarterfinal": "Quart de finale", "Semifinals": "Demi-finale",
    "Semifinal": "Demi-finale", "The Final": "Finale", "Final": "Finale", "Round Robin": "Phase de poules",
    "Qualifying 1st Round": "Qualifs, 1er tour", "Qualifying 2nd Round": "Qualifs, 2e tour",
    "Qualifying Final": "Qualifs, dernier tour",
}
# Critères qui vont contre ce que le grand public croit voir (série, classement, face-à-face…).
ANTI_NAIVE = {"chatte-tie-break", "maudit-tie-break", "en-feu", "classement-trompeur", "bete-noire",
              "gueule-de-bois", "fin-de-saison"}
TAG_INFO = {
    "chatte-tie-break": ("🍀", "Chatte au tie-break"), "maudit-tie-break": ("🐈‍⬛", "Maudit au tie-break"),
    "marathon": ("😮‍💨", "Marathon la veille"), "rouille": ("🧊", "Rouillé"), "rescape": ("🩹", "Rescapé"),
    "gueule-de-bois": ("🍾", "Gueule de bois du champion"), "en-feu": ("🔥", "En feu"),
    "specialiste": ("🏟️", "Spécialiste de la surface"), "pas-sa-surface": ("🙃", "Pas sa surface"),
    "fin-de-saison": ("🍂", "Fin de saison"), "classement-trompeur": ("🎭", "Classement trompeur"),
    "bete-noire": ("👻", "Bête noire"),
}


def surface_key(surface: str, court: str) -> str:
    s = (surface or "Hard").strip().title()
    if s == "Carpet" or (s == "Hard" and (court or "").strip().lower() == "indoor"):
        s = "Indoor"
    return s if s in SURF_FR else "Hard"


class Elo:
    """Elo général + Elo par surface (moitié-moitié), K décroissant avec le nombre de matchs joués."""

    def __init__(self, scale: float = 1.0):
        self.r, self.rs = {}, {}
        self.n, self.ns = defaultdict(int), defaultdict(int)
        self.scale = scale

    def overall(self, p):
        return self.r.get(p, 1500.0)

    def surf(self, p, s):
        return self.rs.get((p, s), self.overall(p))

    def rating(self, p, s):
        return 0.5 * self.overall(p) + 0.5 * self.surf(p, s)

    def diff(self, a, b, s):
        return self.rating(a, s) - self.rating(b, s)

    def prob(self, a, b, s):
        return 1 / (1 + 10 ** (-self.scale * self.diff(a, b, s) / 400))

    @staticmethod
    def _k(n):
        return 250 / (n + 5) ** 0.4

    def update(self, w, l, s):
        e = 1 / (1 + 10 ** ((self.overall(l) - self.overall(w)) / 400))
        self.r[w] = self.overall(w) + self._k(self.n[w]) * (1 - e)
        self.r[l] = self.overall(l) - self._k(self.n[l]) * (1 - e)
        e = 1 / (1 + 10 ** ((self.surf(l, s) - self.surf(w, s)) / 400))
        self.rs[(w, s)] = self.surf(w, s) + self._k(self.ns[(w, s)]) * (1 - e)
        self.rs[(l, s)] = self.surf(l, s) - self._k(self.ns[(l, s)]) * (1 - e)
        self.n[w] += 1
        self.n[l] += 1
        self.ns[(w, s)] += 1
        self.ns[(l, s)] += 1


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, x))))


def fit_logistic(xs: list, ys: list, start: list) -> list:
    """Régression logistique sans constante (Newton), pour quelques variables."""
    b = list(start)
    k = len(b)
    for _ in range(30):
        g = [0.0] * k
        h = [[0.0] * k for _ in range(k)]
        for x, y in zip(xs, ys):
            q = _sigmoid(sum(bi * xi for bi, xi in zip(b, x)))
            w = q * (1 - q)
            for i in range(k):
                g[i] += (q - y) * x[i]
                for j in range(k):
                    h[i][j] += w * x[i] * x[j]
        if k == 1:
            step = [g[0] / h[0][0]] if h[0][0] else [0.0]
        else:
            det = h[0][0] * h[1][1] - h[0][1] * h[1][0]
            if abs(det) < 1e-12:
                break
            step = [(h[1][1] * g[0] - h[0][1] * g[1]) / det, (h[0][0] * g[1] - h[1][0] * g[0]) / det]
        b = [bi - si for bi, si in zip(b, step)]
        if max(abs(s) for s in step) < 1e-7:
            break
    return b


def features(elo: "Elo", st: "State", k1: str, k2: str, surf: str) -> list:
    """Écart Elo (en unités logit) et écart de classement (log du rapport des rangs)."""
    r1, r2 = st.rank.get(k1, 300), st.rank.get(k2, 300)
    return [elo.diff(k1, k2, surf) * math.log(10) / 400, math.log(min(r2, 500) / min(r1, 500))]


def calibrate(mk: dict, cal: dict, fav: int) -> dict:
    """Recale la victoire du favori et les victoires en sets secs, puis rebâtit les autres marchés."""
    f, g = str(fav), str(3 - fav)
    wf = _sigmoid(cal["w_fav"][0] + cal["w_fav"][1] * _logit(mk["w" + f]))
    stf = min(_sigmoid(cal["st_fav"][0] + cal["st_fav"][1] * _logit(mk["st" + f])), wf - 0.001)
    std = min(_sigmoid(cal["st_dog"][0] + cal["st_dog"][1] * _logit(mk["st" + g])), 1 - wf - 0.001)
    stf, std = max(stf, 0.001), max(std, 0.001)
    return {"w" + f: wf, "w" + g: 1 - wf, "st" + f: stf, "st" + g: std, "s" + f: 1 - std, "s" + g: 1 - stf,
            "dec": 1 - stf - std}


def fit_platt(pairs: list) -> list:
    """Recalage (a, b) : p' = sigmoïde(a + b·logit(p))."""
    a, b = fit_logistic([[1.0, _logit(p)] for p, _ in pairs], [y for _, y in pairs], [0.0, 1.0])
    return [a, b]


def set_prob(p_bo3: float) -> float:
    """Probabilité de gagner un set, à partir de celle de gagner un match en 2 sets gagnants."""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if mid * mid * (3 - 2 * mid) < p_bo3 else (lo, mid)
    return (lo + hi) / 2


def markets(p_bo3: float, best_of: int) -> dict:
    s = set_prob(p_bo3)
    q = 1 - s
    if best_of == 5:
        w1, st1, st2 = s ** 3 * (10 - 15 * s + 6 * s * s), s ** 3, q ** 3
        dec = 1 - st1 - st2
    else:
        w1, st1, st2, dec = p_bo3, s * s, q * q, 2 * s * q
    return {"w1": w1, "w2": 1 - w1, "s1": 1 - st2, "s2": 1 - st1, "st1": st1, "st2": st2, "dec": dec}


GPS_MEAN = 9.7  # jeux par set en moyenne sur le circuit
GAME_LINES = {3: [17.5, 18.5, 19.5, 20.5, 21.5, 22.5, 23.5, 24.5, 25.5, 26.5],
              5: [31.5, 32.5, 33.5, 34.5, 35.5, 36.5, 37.5, 38.5, 39.5, 40.5, 41.5, 42.5, 43.5]}
# Jeux par set = a + b·(habitude des deux joueurs − moyenne) + c·déséquilibre ; écart type par set : sd.
DEFAULT_GAMES = {"a": GPS_MEAN, "b": 1.0, "c": -2.0, "sd": 2.4}


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _nsets(dec: float, close: float, best_of: int) -> dict:
    """Probabilité de chaque nombre de sets ; dec = proba d'aller au-delà du minimum (déjà calibrée)."""
    if best_of != 5:
        return {2: 1 - dec, 3: dec}
    s = 0.5 + close
    q = 1 - s
    p4, p5 = 3 * (s ** 3 * q + q ** 3 * s), 6 * (s ** 3 * q * q + q ** 3 * s * s)
    return {3: 1 - dec, 4: dec * p4 / (p4 + p5), 5: dec * p5 / (p4 + p5)}


def fit_games(rows: list) -> dict:
    """rows : (écart d'habitude, déséquilibre, nombre de sets, jeux du match). Moindres carrés sur les jeux par set."""
    X = [[1.0, d, c] for d, c, _, _ in rows]
    Y = [g / n for _, _, n, g in rows]
    A = [[sum(x[i] * x[j] for x in X) for j in range(3)] for i in range(3)]
    B = [sum(x[i] * y for x, y in zip(X, Y)) for i in range(3)]
    for i in range(3):  # élimination de Gauss
        for j in range(i + 1, 3):
            f = A[j][i] / A[i][i]
            A[j] = [a - f * b for a, b in zip(A[j], A[i])]
            B[j] -= f * B[i]
    sol = [0.0, 0.0, 0.0]
    for i in (2, 1, 0):
        sol[i] = (B[i] - sum(A[i][k] * sol[k] for k in range(i + 1, 3))) / A[i][i]
    a, b, c = sol
    res = [(g - n * (a + b * d + c * cl)) / math.sqrt(n) for d, cl, n, g in rows]
    return {"a": a, "b": b, "c": c, "sd": math.sqrt(sum(r * r for r in res) / len(res))}


def label(key: str, p1: str, p2: str, best_of: int) -> str:
    if key.startswith("jeux"):
        kind, val = key.split(":")
        return f"{'Plus' if kind == 'jeux+' else 'Moins'} de {val.replace('.', ',')} jeux dans le match"
    if key == "dec":
        return "Match en 3 sets" if best_of == 3 else "Au moins 4 sets"
    name = p1 if key.endswith("1") else p2
    return {"w": f"Victoire {name}", "s": f"{name} gagne au moins un set",
            "st": f"{name} gagne sans perdre de set"}[key[:-1]]


def settle(key: str, m: dict):
    if not m.get("completed"):
        return None
    if key.startswith("jeux"):
        kind, val = key.split(":")
        total = sum(a + b for a, b in m["sets"])
        return total > float(val) if kind == "jeux+" else total < float(val)
    n1 = sum(a > b for a, b in m["sets"])
    n2 = sum(b > a for a, b in m["sets"])
    if n1 == n2:
        return None
    w = 1 if n1 > n2 else 2
    return {"w1": w == 1, "w2": w == 2, "s1": n1 >= 1, "s2": n2 >= 1, "st1": w == 1 and n2 == 0,
            "st2": w == 2 and n1 == 0,
            "dec": (n1 + n2) == 3 if m["best_of"] == 3 else (n1 + n2) >= 4}.get(key)


class State:
    """Ce qu'on sait de chaque joueur avant un match : historique, classement, face-à-face."""

    def __init__(self):
        self.hist = defaultdict(list)
        self.h2h = defaultdict(list)
        self.rank = {}

    def add(self, m: dict):
        if m["comment"] in ("Walkover", "Cancelled", "Awarded") or not m["sets"]:
            return
        surf = surface_key(m["surface"], m["court"])
        retired = m["comment"].lower().startswith(("ret", "rrt"))
        common = {"date": m["date"], "tournament": m["tournament"], "round": m["round"], "surface": surf,
                  "best_of": m["best_of"], "nsets": len(m["sets"]), "games": sum(a + b for a, b in m["sets"])}
        for name, opp, won, sets in ((m["winner"], m["loser"], True, m["sets"]),
                                     (m["loser"], m["winner"], False, [(b, a) for a, b in m["sets"]])):
            self.hist[name].append(dict(common, opp=opp, won=won, retired=retired and not won,
                                        sets_won=sum(a > b for a, b in sets), sets_lost=sum(b > a for a, b in sets),
                                        tb_won=sum(a == 7 and b == 6 for a, b in sets),
                                        tb_lost=sum(a == 6 and b == 7 for a, b in sets)))
        self.h2h[frozenset((m["winner"], m["loser"]))].append((m["date"], m["winner"]))
        if m.get("wrank"):
            self.rank[m["winner"]] = int(m["wrank"])
        if m.get("lrank"):
            self.rank[m["loser"]] = int(m["lrank"])

    def gps(self, name: str, day, k: int = 20) -> float:
        """Jeux par set dans les matchs du joueur sur 12 mois (gros serveurs : plus de jeux, plus de tie-breaks)."""
        recent = [e for e in self.hist.get(name, []) if 0 < (day - e["date"]).days <= 365]
        g, n = sum(e["games"] for e in recent), sum(e["nsets"] for e in recent)
        return (g + k * GPS_MEAN) / (n + k)


def _tag(tid, title, text, supports=(), against=()):
    icon = TAG_INFO[tid][0]
    return {"id": tid, "icon": icon, "title": title, "text": text, "supports": list(supports),
            "against": list(against), "effect": None}


def evaluate(fx: dict, st: State, elo: Elo, p: float) -> list:
    d, surf = fx["date"], fx["surface"]
    names = {1: fx["p1"], 2: fx["p2"]}
    keys = {1: fx["k1"], 2: fx["k2"]}
    fav, dog = (1, 2) if p >= 0.5 else (2, 1)
    tags = []
    for i in (1, 2):
        j, name, h = 3 - i, names[i], st.hist.get(keys[i], [])
        if not h:
            continue
        last, days = h[-1], (d - h[-1]["date"]).days
        if days >= 35 and len(h) >= 10:
            tags.append(_tag("rouille", f"Rouillé — {name}", f"{name} n'a plus joué depuis {days} jours.",
                             supports=[f"w{j}", f"s{j}"], against=[f"st{i}"]))
        if not last["won"] and last["retired"] and days <= 45:
            tags.append(_tag("rescape", f"Rescapé — {name}",
                             f"{name} a abandonné en cours de match il y a {days} jours. Le corps suit-il ?",
                             supports=[f"w{j}", f"s{j}"]))
        if (days <= 2 and last["tournament"] == fx["tournament"]
                and (last["nsets"] == last["best_of"] or last["games"] >= 30)):
            tags.append(_tag("marathon", f"Marathon la veille — {name}",
                             f"{name} sort d'un match en {last['nsets']} sets ({last['games']} jeux). Son adversaire est plus frais.",
                             supports=[f"s{j}", f"w{j}"], against=[f"st{i}"]))
        if last["won"] and last["round"] == "The Final" and last["tournament"] != fx["tournament"] and days <= 10:
            tags.append(_tag("gueule-de-bois", f"Gueule de bois du champion — {name}",
                             f"{name} vient de gagner le titre à {last['tournament']}. Les lendemains de titre font souvent mal.",
                             supports=[f"s{j}"], against=[f"st{i}"]))
        recent = [e for e in h if (d - e["date"]).days <= 365]
        tbw, tbl = sum(e["tb_won"] for e in recent), sum(e["tb_lost"] for e in recent)
        sw, sl = sum(e["sets_won"] for e in recent) - tbw, sum(e["sets_lost"] for e in recent) - tbl
        if tbw + tbl >= 8 and sw + sl >= 20:
            luck = tbw - (tbw + tbl) * sw / (sw + sl)
            if luck >= 2.5:
                tags.append(_tag("chatte-tie-break", f"Chatte au tie-break — {name}",
                                 f"{tbw} tie-breaks gagnés sur {tbw + tbl} cette année, bien plus que son niveau dans "
                                 f"les autres sets ne le justifie (+{luck:.1f}). Ça finit toujours par se payer.",
                                 supports=[f"s{j}"], against=[f"st{i}"]))
            elif luck <= -2.5:
                tags.append(_tag("maudit-tie-break", f"Maudit au tie-break — {name}",
                                 f"Seulement {tbw} tie-breaks gagnés sur {tbw + tbl} cette année ({luck:.1f} par rapport à "
                                 f"son niveau). La poisse ne dure pas.", supports=[f"w{i}", f"s{i}"]))
        streak = 0
        for e in reversed(h):
            if not e["won"]:
                break
            streak += 1
        if streak >= 7:
            tags.append(_tag("en-feu", f"En feu — {name}",
                             f"{streak} victoires de suite : tout le monde va le jouer, et sa cote baisse en conséquence.",
                             supports=[f"s{j}"], against=[f"st{i}"]))
        if elo.ns[(keys[i], surf)] >= 10:
            gap = elo.surf(keys[i], surf) - elo.overall(keys[i])
            if gap >= 60:
                tags.append(_tag("specialiste", f"Spécialiste {SURF_FR[surf]} — {name}",
                                 f"{name} vaut {gap:.0f} points Elo de plus sur {SURF_FR[surf]} que sur l'ensemble des surfaces.",
                                 supports=[f"w{i}", f"s{i}"]))
            elif gap <= -60:
                tags.append(_tag("pas-sa-surface", f"Pas sa surface — {name}",
                                 f"{name} perd {-gap:.0f} points Elo sur {SURF_FR[surf]}.", supports=[f"s{j}"]))
        if d.month in (10, 11) and i == fav and st.rank.get(keys[i], 999) <= 10:
            tags.append(_tag("fin-de-saison", f"Fin de saison — {name}",
                             "Top 10 en fin d'année : la tête est souvent aux Masters ou aux vacances.",
                             supports=[f"s{j}"], against=[f"st{i}"]))
    r1, r2 = st.rank.get(keys[1]), st.rank.get(keys[2])
    elo_fav = 1 if elo.diff(keys[1], keys[2], surf) >= 0 else 2
    if r1 and r2 and max(r1, r2) / min(r1, r2) >= 2:
        ranked = 1 if r1 < r2 else 2
        if ranked != elo_fav:
            tags.append(_tag("classement-trompeur", "Classement trompeur",
                             f"{names[ranked]} est mieux classé (n°{min(r1, r2)} contre n°{max(r1, r2)}), mais le niveau "
                             f"de jeu récent (Elo) de {names[elo_fav]} est supérieur. Le grand public regarde le classement.",
                             supports=[f"w{elo_fav}", f"s{elo_fav}"]))
    meetings = [w for when, w in st.h2h.get(frozenset((keys[1], keys[2])), []) if (d - when).days <= 4 * 365]
    wd, wf = meetings.count(keys[dog]), meetings.count(keys[fav])
    if wd >= 3 and wd - wf >= 2:
        tags.append(_tag("bete-noire", f"Bête noire — {names[dog]}",
                         f"{names[dog]} mène {wd}-{wf} dans leurs face-à-face récents, alors que le niveau actuel donne "
                         f"{names[fav]} favori. Qui a raison ?", supports=[f"w{dog}", f"s{dog}"]))
    return tags


def analyse(fx: dict, st: State, elo: Elo, cfg: dict) -> dict:
    """fx : p1/p2 (noms affichés), k1/k2 (noms dans l'historique), date, ko, surface, best_of, tournament, odds."""
    x = features(elo, st, fx["k1"], fx["k2"], fx["surface"])
    coef = cfg.get("tennis_coef") or [1.0, 0.0]
    p = _sigmoid(coef[0] * x[0] + coef[1] * x[1])
    mk = markets(p, fx["best_of"])
    fav = 1 if mk["w1"] >= 0.5 else 2
    if cfg.get("tennis_cal"):
        mk = calibrate(mk, cfg["tennis_cal"], fav)
    # Nombre de jeux : mélange « 2 sets / 3 sets » (proba du set décisif déjà calibrée) × jeux par set,
    # qui dépendent de l'habitude des deux joueurs (gros serveurs = plus de jeux) et de leur écart de niveau.
    s_set, bo = set_prob(p), fx["best_of"]
    close = abs(s_set - 0.5)
    nsets = _nsets(mk["dec"], close, bo)
    gp = cfg.get("tennis_games") or DEFAULT_GAMES
    dev = (st.gps(fx["k1"], fx["date"]) + st.gps(fx["k2"], fx["date"])) / 2 - GPS_MEAN
    g_set = gp["a"] + gp["b"] * dev + gp["c"] * close
    mu_games = sum(pn * n * g_set for n, pn in nsets.items())
    for line in GAME_LINES[bo]:
        po = sum(pn * (1 - _phi((line - n * g_set) / (gp["sd"] * math.sqrt(n)))) for n, pn in nsets.items())
        mk[f"jeux+:{line}"], mk[f"jeux-:{line}"] = po, 1 - po
    tags = evaluate(fx, st, elo, mk["w1"])
    odds = fx.get("odds") or {}
    p_mkt = devig(odds["sharp"]) if odds.get("sharp") else None
    sels = []
    for key, prob in mk.items():
        if prob <= 0.02 or prob >= 0.995:
            continue
        side = 0 if key.endswith("1") else 1 if key.endswith("2") else None
        o = odds["avg"][side] if odds.get("avg") and side is not None and key[0] == "w" else None
        s = {"key": key, "label": label(key, fx["p1"], fx["p2"], fx["best_of"]), "p": prob, "fair": 1 / prob,
             "min_odds": (1 + cfg["min_edge_play"]) / prob, "odds": o,
             "odds_max": odds["max"][side] if o and odds.get("max") else None,
             "p_mkt": p_mkt[side] if p_mkt and o else None, "p_model": prob, "edge": prob * o - 1 if o else None,
             "base_key": (key.split(":")[0] if key.startswith("jeux") else key) if side is None
             else f"{key[:-1]}_{'fav' if side + 1 == fav else 'dog'}",
             "tags": [t["id"] for t in tags if key in t["supports"]],
             "against": [t["id"] for t in tags if key in t["against"]]}
        s["breaks"] = bool(set(s["tags"]) & ANTI_NAIVE)
        sels.append(s)
    return {
        "id": fx["id"], "sport": "tennis", "tour": fx["tour"], "league": f"{fx['tour']} · {fx['event']}",
        "ko": fx["ko"], "home": fx["p1"], "away": fx["p2"], "round": ROUNDS_FR.get(fx["round"], fx["round"]),
        "surface": SURF_FR[fx["surface"]], "best_of": fx["best_of"], "tennis": mk, "p_mkt": p_mkt,
        "elo": [round(elo.rating(fx["k1"], fx["surface"])), round(elo.rating(fx["k2"], fx["surface"]))],
        "rank": [st.rank.get(fx["k1"]), st.rank.get(fx["k2"])],
        "form": ["".join("V" if e["won"] else "D" for e in st.hist.get(k, [])[-5:]) for k in (fx["k1"], fx["k2"])],
        "tags": tags, "info": {}, "sels": sels, "date": fx["date"], "time_tbc": fx.get("time_tbc", False),
        "games": mu_games, "games_feat": (dev, close),
    }


# ---------- Le moment présent ----------

def _surfaces(rows: list) -> dict:
    """Lieu → {mois: surface} : à Paris, c'est la terre battue en mai et le dur indoor en novembre."""
    out = defaultdict(dict)
    for r in rows:
        out[td.norm(r["location"])][r["date"].month] = surface_key(r["surface"], r["court"])
    return out


def _surface_for(city: str, table: dict, month: int) -> str:
    c = td.norm(city)
    # « Santiago de Querétaro » ne doit pas tomber sur « Santiago » (Chili, terre battue).
    by_month = table.get(c) or next(
        (v for loc, v in table.items() if loc and (c.endswith(" " + loc) or loc.endswith(" " + c))), None)
    if not by_month:
        return "Hard"
    return by_month[min(by_month, key=lambda m: min(abs(m - month), 12 - abs(m - month)))]


def live(cfg: dict, now: dt.datetime, log=print):
    """Pronos sur les matchs de simple à venir cette semaine, et résultats pour régler les anciens pronos."""
    rows = td.load_history(range(now.year - 5, now.year + 1))
    espn = td.load_espn("atp") + td.load_espn("wta")
    index, last_date = {}, {}
    for tour in ("ATP", "WTA"):
        tr = [r for r in rows if r["tour"] == tour]
        index[tour] = td.NameIndex(dict.fromkeys(n for r in reversed(tr) for n in (r["winner"], r["loser"])))
        last_date[tour] = tr[-1]["date"] if tr else dt.date.min
    surfaces = _surfaces(rows)
    key = lambda e, n: index[e["tour"]].find(n) or n

    def best_of(e):
        return 5 if e["tour"] == "ATP" and any(s in e["event"] for s in SLAMS) else 3

    # Les matchs de cette semaine ne sont pas encore dans l'historique : on les ajoute depuis ESPN.
    extra = []
    for e in espn:
        if e["state"] == "post" and e["winner"] and e["sets"] and e["ko"].date() > last_date[e["tour"]]:
            w = e["winner"]
            sets = e["sets"] if w == 1 else [(b, a) for a, b in e["sets"]]
            sk = _surface_for(e["city"], surfaces, e["ko"].month)
            extra.append({"tour": e["tour"], "date": e["ko"].date(), "tournament": e["event"], "location": e["city"],
                          "court": "Indoor" if sk == "Indoor" else "Outdoor", "surface": "Hard" if sk == "Indoor" else sk,
                          "round": "The Final" if e["round"] == "Final" else e["round"], "best_of": best_of(e),
                          "winner": key(e, e["p1"] if w == 1 else e["p2"]), "loser": key(e, e["p2"] if w == 1 else e["p1"]),
                          "wrank": None, "lrank": None, "sets": sets,
                          "comment": "Completed" if e["status"] == "Final" else "Retired", "odds": {}})
    elo, st = Elo(), State()
    for r in sorted(rows + extra, key=lambda r: r["date"]):
        st.add(r)
        if r["comment"] == "Completed" and r["sets"]:
            elo.update(r["winner"], r["loser"], surface_key(r["surface"], r["court"]))

    horizon = now + dt.timedelta(days=cfg["horizon_days"])
    analyses = []
    for e in espn:
        if e["state"] != "pre" or not now < e["ko"] <= horizon:
            continue
        fx = {"id": e["id"], "tour": e["tour"], "event": e["event"], "tournament": e["event"], "round": e["round"],
              "ko": e["ko"], "date": e["ko"].date(), "p1": e["p1"], "p2": e["p2"], "k1": key(e, e["p1"]),
              "k2": key(e, e["p2"]), "surface": _surface_for(e["city"], surfaces, e["ko"].month), "best_of": best_of(e),
              "time_tbc": e["time_tbc"]}
        analyses.append(analyse(fx, st, elo, cfg))
    results = [{"id": e["id"], "sport": "tennis", "sets": e["sets"], "best_of": best_of(e),
                "completed": e["state"] == "post" and e["status"] == "Final"} for e in espn if e["state"] == "post"]
    log(f"Tennis : {len(analyses)} matchs à venir ({sum(e['state'] == 'pre' for e in espn)} programmés cette semaine)")
    return analyses, results


# ---------- Backtest ----------

def _replay(rows: list, cfg: dict, from_year: int, collect: bool = True):
    """Rejoue l'historique dans l'ordre : chaque prono est fait avant de connaître le résultat.

    collect=False : renvoie seulement les variables du modèle et le résultat, pour caler ses poids.
    """
    elo, st = Elo(), State()
    records, feats = [], []
    for r in rows:
        surf = surface_key(r["surface"], r["court"])
        if not collect and r["date"].year >= from_year and r["comment"] == "Completed":
            a, b = sorted((r["winner"], r["loser"]))
            feats.append((r["date"].year, features(elo, st, a, b, surf), int(a == r["winner"])))
        elif collect and r["date"].year >= from_year and r["comment"] in ("Completed", "Retired") and r["sets"]:
            a, b = sorted((r["winner"], r["loser"]))
            swap = a != r["winner"]
            odds = {k: (v[::-1] if swap else v) for k, v in r["odds"].items() if v}
            fx = {"id": f"{r['date']}-{a}-{b}", "tour": r["tour"], "event": r["tournament"],
                  "tournament": r["tournament"], "round": r["round"], "date": r["date"],
                  "ko": dt.datetime.combine(r["date"], dt.time(12), tzinfo=PARIS), "p1": a, "p2": b, "k1": a, "k2": b,
                  "surface": surf, "best_of": r["best_of"], "odds": odds}
            res = {"sport": "tennis", "best_of": r["best_of"], "completed": r["comment"] == "Completed",
                   "sets": [(y, x) for x, y in r["sets"]] if swap else list(r["sets"])}
            records.append((res, analyse(fx, st, elo, cfg)))
        st.add(r)
        if r["comment"] == "Completed" and r["sets"]:
            elo.update(r["winner"], r["loser"], surf)
    return records, feats


def backtest(cfg: dict, log=print) -> dict:
    """Saison N-1 : on cale le modèle et on mesure les critères. Saison N : on joue, sans rien retoucher."""
    from . import backtest as bt
    from . import picks

    year = dt.date.today().year
    rows = td.load_history(range(year - 5, year + 1))
    _, feats = _replay(rows, cfg, year - 1, collect=False)
    calib = [(x, y) for yr, x, y in feats if yr == year - 1]
    coef = fit_logistic([x for x, _ in calib], [y for _, y in calib], [1.0, 0.0])
    log(f"  Tennis : poids Elo {coef[0]:.2f}, poids classement {coef[1]:.2f} (calés sur {year - 1})")
    raw_records, _ = _replay(rows, dict(cfg, tennis_coef=coef), year - 1)
    pairs = defaultdict(list)
    for m, an in raw_records:
        if an["date"].year != year - 1 or not m["completed"]:
            continue
        f = 1 if an["tennis"]["w1"] >= 0.5 else 2
        for name, key in (("w_fav", f"w{f}"), ("st_fav", f"st{f}"), ("st_dog", f"st{3 - f}")):
            pairs[name].append((an["tennis"][key], int(settle(key, m))))
    cal_params = {k: fit_platt(v) for k, v in pairs.items()}
    games = [(*an["games_feat"], len(m["sets"]), sum(a + b for a, b in m["sets"]))
             for m, an in raw_records if an["date"].year == year - 1 and m["completed"]]
    gp = fit_games(games)
    # Les scores de tennis ont des queues plus épaisses qu'une courbe en cloche : on règle l'écart type pour que
    # les lignes qu'on joue vraiment (proba 62-85 %) passent aussi souvent qu'annoncé sur la saison de calage.
    feats = [(an["games_feat"], an["tennis"]["dec"], an["best_of"], sum(a + b for a, b in m["sets"]))
             for m, an in raw_records if an["date"].year == year - 1 and m["completed"]]

    def games_gap(sd):
        gap = n = 0
        for (dev, close), dec, bo, total in feats:
            g_set = gp["a"] + gp["b"] * dev + gp["c"] * close
            for line in GAME_LINES[bo]:
                po = sum(pn * (1 - _phi((line - k * g_set) / (sd * math.sqrt(k))))
                         for k, pn in _nsets(dec, close, bo).items())
                p, won = (po, total > line) if po >= 0.5 else (1 - po, total < line)
                if 0.62 <= p <= 0.85:
                    gap += won - p
                    n += 1
        return abs(gap / max(n, 1))

    gp["sd"] = min((gp["sd"] * k / 10 for k in range(10, 31)), key=games_gap)
    log(f"  Tennis : jeux par set {gp['a']:.2f} + {gp['b']:.2f}×habitude {gp['c']:+.2f}×déséquilibre (écart type {gp['sd']:.2f})")
    cfg_m = dict(cfg, tennis_coef=coef, tennis_cal=cal_params, tennis_games=gp)
    records, _ = _replay(rows, cfg_m, year - 1)
    cal = [(m, an) for m, an in records if an["date"].year == year - 1]
    test = [(m, an) for m, an in records if an["date"].year == year]
    raw_cal = bt.tag_study(cal)
    cfg1 = dict(cfg_m, tag_stats=raw_cal)
    reliab = defaultdict(lambda: [0, 0, 0.0])
    for m, an in test:
        for s in an["sels"]:
            won = settle(s["key"], m)
            if won is not None:
                r = reliab[s["base_key"]]
                r[0] += 1
                r[1] += won
                r[2] += s["p"]

    lm = lk = n = 0
    bets = []
    for m, an in test:
        if not m["completed"]:
            continue
        w = 0 if settle("w1", m) else 1
        lm -= math.log(max(an["tennis"]["w1" if w == 0 else "w2"], 1e-6))
        if an["p_mkt"]:
            lk -= math.log(max(an["p_mkt"][w], 1e-6))
            n += 1
        for s in an["sels"]:
            if s["odds"] and s["edge"] >= cfg["edge_min"]:
                won = settle(s["key"], m)
                bets.append(s["odds"] - 1 if won else -1)
    weeks = defaultdict(list)
    by_id = {}
    for m, an in test:
        weeks[an["date"].isocalendar()[:2]].append(an)
        by_id[an["id"]] = m
    cats, combos = defaultdict(list), defaultdict(list)
    for _, ans in sorted(weeks.items()):
        sol, cps, sts = picks.solides(ans, cfg1), picks.contre_pieds(ans, cfg1), picks.stats_a_jouer(ans, cfg1)
        for name, lst in (("solides", sol), ("contre_pieds", cps), ("stats", sts)):
            for s in lst:
                won = settle(s["key"], by_id[s["match_id"]])
                if won is not None:
                    cats[name].append((s, won, s["odds"]))
        extras = [x for x in (picks.enfer(ans, cfg1), picks.ticket(cps, ans, cfg1)) if x]
        for c in picks.combines(sol, cps, [], cfg1) + extras:
            res = [settle(x["key"], by_id[x["match_id"]]) for x in c["legs"]]
            if None not in res:
                combos[c["name"]].append((all(res), c["p"], c["one_in"]))
    raw = bt.merge_raw(raw_cal, bt.tag_study(test))
    return {
        "season": str(year), "calibration_season": str(year - 1), "matches": len(test),
        "coef": coef, "calibration": cal_params, "games": gp,
        "reliability": {k: {"n": v[0], "hit": v[1] / v[0], "expected_hit": v[2] / v[0]} for k, v in reliab.items()},
        "logloss_model": lm / max(len(test), 1), "logloss_market": lk / max(n, 1),
        "value_bets": {"bets": len(bets), "roi": sum(bets) / len(bets) if bets else None},
        "categories": {k: bt._cat(v) for k, v in cats.items()},
        "combos": {k: {"n": len(v), "won": sum(w for w, _, _ in v), "expected_won": sum(p for _, p, _ in v),
                       "avg_one_in": sum(x for *_, x in v) / len(v)} for k, v in combos.items()},
        "validated_on_calibration": sorted(picks.tag_lifts(cfg1)),
        "tags_raw": raw, "tags": {t: picks.tag_summary(r) for t, r in raw.items() if r["n"]},
    }
