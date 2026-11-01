"""Les critères « surprise » : ce que la forme brute ne voit pas.

Chaque critère produit un tag affiché sur le match (avec les paris qu'il soutient ou
contredit) et, pour certains, un petit ajustement des buts attendus.
"""
from __future__ import annotations

from collections import defaultdict

from .model import poisson_pmf, xg_of

_D = [
    ("Paris SG", "Marseille", "Le Classique"), ("Lyon", "St Etienne", "Derby du Rhône"),
    ("Lens", "Lille", "Derby du Nord"), ("Nice", "Monaco", "Derby de la Côte d'Azur"),
    ("Marseille", "Lyon", "Olympico"), ("Rennes", "Nantes", "Derby breton"), ("Rennes", "Brest", "Derby breton"),
    ("Rennes", "Lorient", "Derby breton"), ("Brest", "Lorient", "Derby breton"), ("Brest", "Guingamp", "Derby breton"),
    ("Lorient", "Guingamp", "Derby breton"), ("Rennes", "Guingamp", "Derby breton"),
    ("Paris SG", "Paris FC", "Derby parisien"), ("Metz", "Nancy", "Derby lorrain"),
    ("Montpellier", "Nimes", "Derby du Languedoc"), ("Ajaccio", "Bastia", "Derby corse"),
    ("Le Havre", "Caen", "Derby normand"), ("Bordeaux", "Toulouse", "Derby de la Garonne"),
    ("Man City", "Man United", "Derby de Manchester"), ("Liverpool", "Everton", "Derby de la Mersey"),
    ("Arsenal", "Tottenham", "North London Derby"), ("Liverpool", "Man United", "North-West Derby"),
    ("Chelsea", "Tottenham", "Derby londonien"), ("Chelsea", "Arsenal", "Derby londonien"),
    ("West Ham", "Tottenham", "Derby londonien"), ("West Ham", "Chelsea", "Derby londonien"),
    ("Crystal Palace", "Brighton", "M23 Derby"), ("Newcastle", "Sunderland", "Tyne-Wear Derby"),
    ("Aston Villa", "Birmingham", "Second City Derby"), ("Leeds", "Man United", "Roses Derby"),
    ("Wolves", "West Brom", "Black Country Derby"), ("Sheffield United", "Sheffield Weds", "Steel City Derby"),
    ("Ipswich", "Norwich", "East Anglian Derby"), ("Nott'm Forest", "Derby", "East Midlands Derby"),
    ("Real Madrid", "Barcelona", "El Clásico"), ("Real Madrid", "Ath Madrid", "Derbi madrileño"),
    ("Barcelona", "Espanol", "Derbi barceloní"), ("Sevilla", "Betis", "Gran Derbi"),
    ("Ath Bilbao", "Sociedad", "Derbi vasco"), ("Valencia", "Levante", "Derbi valenciano"),
    ("Valencia", "Villarreal", "Derbi de la Comunitat"), ("Celta", "La Coruna", "Derbi gallego"),
    ("Sp Gijon", "Oviedo", "Derbi asturiano"),
    ("Inter", "Milan", "Derby della Madonnina"), ("Roma", "Lazio", "Derby della Capitale"),
    ("Juventus", "Torino", "Derby della Mole"), ("Inter", "Juventus", "Derby d'Italia"),
    ("Genoa", "Sampdoria", "Derby della Lanterna"), ("Napoli", "Roma", "Derby del Sole"),
    ("Fiorentina", "Bologna", "Derby dell'Appennino"),
    ("Dortmund", "Schalke 04", "Revierderby"), ("Bayern Munich", "Dortmund", "Der Klassiker"),
    ("Hamburg", "Werder Bremen", "Nordderby"), ("FC Koln", "M'gladbach", "Rheinderby"),
    ("Hamburg", "St Pauli", "Derby de Hambourg"), ("Union Berlin", "Hertha", "Derby de Berlin"),
    ("Leverkusen", "FC Koln", "Derby rhénan"),
    ("Benfica", "Sp Lisbon", "Derby de Lisbonne"), ("Porto", "Benfica", "O Clássico"),
    ("Porto", "Sp Lisbon", "Clássico"), ("Galatasaray", "Fenerbahce", "Derby intercontinental"),
    ("Besiktas", "Galatasaray", "Derby d'Istanbul"), ("Besiktas", "Fenerbahce", "Derby d'Istanbul"),
    ("Ajax", "Feyenoord", "De Klassieker"), ("PSV Eindhoven", "Ajax", "De Topper"),
    ("Celtic", "Rangers", "Old Firm"), ("Hearts", "Hibernian", "Derby d'Édimbourg"),
    ("Olympiakos", "Panathinaikos", "Derby des ennemis éternels"), ("Club Brugge", "Anderlecht", "Topper belge"),
    ("Club Brugge", "Cercle Brugge", "Derby de Bruges"),
]
DERBIES = {frozenset((a, b)): name for a, b, name in _D}
TAG_INFO = {
    "fausse-panne": ("🔫", "Fausse panne"), "vraie-panne": ("🪫", "Vraie panne"),
    "muraille-carton": ("🧱", "Muraille en carton"), "serie-trompe-oeil": ("🎭", "Série en trompe-l'œil"),
    "ca-va-tourner": ("🔄", "Ça va tourner"), "chanceux": ("🍀", "Bénie des dieux"), "poissard": ("🐈‍⬛", "Chat noir"),
    "piege-00": ("🪤", "Piège à 0-0"), "00-credible": ("😴", "0-0 crédible"),
    "feu-artifice-evente": ("🎆", "Feu d'artifice éventé"), "jambes-lourdes": ("😮‍💨", "Jambes lourdes"),
    "forteresse": ("🏰", "Forteresse"), "domicile-maudit": ("🫥", "Domicile maudit"), "voyageur": ("🧳", "Voyageur"),
    "derby": ("⚔️", "Derby"), "arbitre-severe": ("🟨", "Arbitre à cartons"), "arbitre-coulant": ("🕊️", "Arbitre coulant"),
    "deluge": ("🌧️", "Déluge"), "pluie": ("🌦️", "Pluie"), "vent": ("💨", "Gros vent"), "froid": ("🥶", "Froid polaire"),
    "argent-malin": ("💸", "L'argent malin"), "cote-en-retard": ("🐢", "Bookmaker en retard"),
    "popularite": ("📣", "Taxe de popularité"),
}
# Clubs sur lesquels le grand public mise par réflexe : leurs cotes sont souvent trop basses.
POPULAR = {"Paris SG", "Marseille", "Lyon", "Real Madrid", "Barcelona", "Ath Madrid", "Man United", "Liverpool",
           "Arsenal", "Chelsea", "Man City", "Tottenham", "Bayern Munich", "Dortmund", "Juventus", "Milan",
           "Inter", "Napoli"}


def build_history(results: list, conv: dict) -> dict:
    hist = defaultdict(list)
    for m in results:
        hx, ax = xg_of(m, "h", conv), xg_of(m, "a", conv)
        hist[m["home"]].append({"ko": m["ko"], "opp": m["away"], "home": True,
                                "gf": m["hg"], "ga": m["ag"], "xgf": hx, "xga": ax})
        hist[m["away"]].append({"ko": m["ko"], "opp": m["home"], "home": False,
                                "gf": m["ag"], "ga": m["hg"], "xgf": ax, "xga": hx})
    return hist


def before(entries: list, ko) -> list:
    i = len(entries)
    while i and entries[i - 1]["ko"] >= ko:
        i -= 1
    return entries[:i]


def streak(entries: list, cond) -> int:
    n = 0
    for e in reversed(entries):
        if not cond(e):
            break
        n += 1
    return n


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def expected_points(xf: float, xa: float) -> float:
    pf, pa = poisson_pmf(xf, 8), poisson_pmf(xa, 8)
    win = sum(pf[i] * pa[j] for i in range(9) for j in range(i))
    draw = sum(pf[i] * pa[i] for i in range(9))
    return 3 * win + draw


def luck(entries: list, n: int = 6):
    """Indice de chatte : points pris moins points « mérités » d'après les xG, sur les n derniers matchs."""
    last = [e for e in entries[-n:] if e["xgf"] is not None and e["xga"] is not None]
    if len(last) < 4:
        return None
    pts = sum(3 if e["gf"] > e["ga"] else 1 if e["gf"] == e["ga"] else 0 for e in last)
    xpts = sum(expected_points(e["xgf"], e["xga"]) for e in last)
    goals = sum((e["gf"] - e["xgf"]) - (e["ga"] - e["xga"]) for e in last)
    return {"luck": round(pts - xpts, 1), "pts": pts, "xpts": round(xpts, 1), "goal_luck": round(goals, 1),
            "n": len(last)}


def _keys(side: str) -> dict:
    h = side == "h"
    return {"win": "1" if h else "2", "dc": "1N" if h else "N2", "opp_dc": "N2" if h else "1N",
            "opp_win": "2" if h else "1", "scores": f"{side}_scores",
            "opp_scores": "a_scores" if h else "h_scores", "cs": f"{side}_cs"}


def _tag(tid, icon, title, text, supports=(), against=(), effect=None):
    return {"id": tid, "icon": icon, "title": title, "text": text,
            "supports": list(supports), "against": list(against), "effect": effect}


def _f(x, d=1):
    return f"{x:.{d}f}".replace(".", ",")


def evaluate(fx: dict, hist: dict, models, lam: tuple, weather=None):
    """Renvoie (ajustements, tags, infos) pour un match à venir. lam = buts attendus bruts du modèle."""
    h, a = fx["home"], fx["away"]
    adj = {"h": 1.0, "a": 1.0, "corners": 1.0, "cards": 1.0}
    tags, info = [], {}
    ent = {"h": before(hist.get(h, []), fx["ko"]), "a": before(hist.get(a, []), fx["ko"])}
    naive00 = {}
    for side, team in (("h", h), ("a", a)):
        e, K = ent[side], _keys(side)
        if len(e) < 3:
            continue
        info[side] = {"luck": luck(e), "rest": (fx["ko"] - e[-1]["ko"]).days,
                      "form": "".join("V" if x["gf"] > x["ga"] else "N" if x["gf"] == x["ga"] else "D"
                                      for x in e[-5:])}
        n0 = streak(e, lambda x: x["gf"] == 0)
        unders = streak(e, lambda x: x["gf"] + x["ga"] <= 2)
        naive00[side] = n0 >= 2 or unders >= 3
        if n0 >= 2:
            xg = _avg(x["xgf"] for x in e[-n0:])
            if xg is not None and xg >= 1.0:
                tags.append(_tag("fausse-panne", "🔫", f"Fausse panne — {team}",
                                 f"{team} n'a plus marqué depuis {n0} matchs… mais {_f(xg)} xG par match sur la période. "
                                 f"Les occasions sont là, le but va finir par tomber.",
                                 supports=[K["scores"], "o15", "btts"], against=["nobtts", "u25", "00"]))
            elif xg is not None and xg <= 0.75:
                tags.append(_tag("vraie-panne", "🪫", f"Vraie panne — {team}",
                                 f"{team} ne marque plus ({n0} matchs) et ne crée presque rien ({_f(xg)} xG/match).",
                                 supports=[_keys("a" if side == "h" else "h")["cs"], "nobtts"],
                                 against=[K["scores"], "btts"]))
        ncs = streak(e, lambda x: x["ga"] == 0)
        if ncs >= 2:
            xga = _avg(x["xga"] for x in e[-ncs:])
            if xga is not None and xga >= 1.2:
                tags.append(_tag("muraille-carton", "🧱", f"Muraille en carton — {team}",
                                 f"{team} n'a rien encaissé depuis {ncs} matchs mais concède {_f(xga)} xG par match : "
                                 f"le gardien enchaîne les miracles, ça ne durera pas.",
                                 supports=[K["opp_scores"], "btts"], against=[K["cs"], "nobtts"]))
        lk = info[side]["luck"]
        nw = streak(e, lambda x: x["gf"] > x["ga"])
        nwl = streak(e, lambda x: x["gf"] <= x["ga"])
        if lk and nw >= 3 and lk["luck"] >= 2.5:
            tags.append(_tag("serie-trompe-oeil", "🎭", f"Série en trompe-l'œil — {team}",
                             f"{nw} victoires de suite, mais {lk['pts']} points pris pour {_f(lk['xpts'])} « mérités » "
                             f"sur {lk['n']} matchs. La série est gonflée à la chatte.",
                             supports=[K["opp_dc"]], against=[K["win"]]))
        elif lk and nwl >= 3 and lk["luck"] <= -2.5:
            tags.append(_tag("ca-va-tourner", "🔄", f"Ça va tourner — {team}",
                             f"{nwl} matchs sans victoire alors que son jeu valait {_f(lk['xpts'])} points "
                             f"(il n'en a pris que {lk['pts']}). La poisse ne dure jamais.",
                             supports=[K["win"], K["dc"]], against=[K["opp_win"]]))
        elif lk and lk["luck"] >= 3:
            tags.append(_tag("chanceux", "🍀", f"Bénie des dieux — {team}",
                             f"+{_f(lk['luck'])} points de plus que ce que valait son jeu sur {lk['n']} matchs.",
                             supports=[K["opp_dc"]], against=[K["win"]]))
        elif lk and lk["luck"] <= -3:
            tags.append(_tag("poissard", "🐈‍⬛", f"Chat noir — {team}",
                             f"{_f(lk['luck'])} points par rapport à ce que valait son jeu sur {lk['n']} matchs.",
                             supports=[K["dc"]], against=[K["opp_win"]]))

    total = lam[0] + lam[1]
    info["naive00"] = bool(naive00.get("h") and naive00.get("a"))
    if info["naive00"]:
        if total >= 2.45:
            tags.append(_tag("piege-00", "🪤", "Piège à 0-0",
                             f"Les deux équipes sortent de matchs fermés : une IA de base te dirait « nul 0-0 ». "
                             f"Sauf que leurs occasions valent {_f(total)} buts pour ce match. Le 0-0 est un piège.",
                             supports=["o15", "btts"], against=["00", "u25", "N"]))
        elif total <= 2.1:
            tags.append(_tag("00-credible", "😴", "0-0 crédible",
                             f"Deux équipes en panne et seulement {_f(total)} buts attendus : pour une fois, la série dit vrai.",
                             supports=["u25", "nobtts"], against=["o25", "btts"]))
    if len(ent["h"]) >= 3 and len(ent["a"]) >= 3:
        overs = [streak(ent[s], lambda x: x["gf"] + x["ga"] >= 3) for s in "ha"]
        if min(overs) >= 3 and total <= 2.35:
            tags.append(_tag("feu-artifice-evente", "🎆", "Feu d'artifice éventé",
                             f"Les deux équipes restent sur {min(overs)}+ matchs à 3 buts ou plus, et tout le monde "
                             f"va jouer « plus de 2,5 ». Les xG disent {_f(total)} buts : le spectacle était du hasard.",
                             supports=["u25", "u35"], against=["o25"]))

    if "h" in info and "a" in info:
        for side, other, team in (("h", "a", h), ("a", "h", a)):
            r, ro = info[side]["rest"], info[other]["rest"]
            if r <= 3 and ro >= 5:
                adj[side] *= 0.96
                adj[other] *= 1.03
                tags.append(_tag("jambes-lourdes", "😮‍💨", f"Jambes lourdes — {team}",
                                 f"{team} a joué il y a {r} jours, son adversaire a eu {ro} jours pour souffler.",
                                 supports=[_keys(other)["dc"]], against=[_keys(side)["win"]], effect="−4 % en attaque"))

    fa, fd = models.home_fx.get(h, (1.0, 1.0))
    adj["h"] *= fa
    adj["a"] *= fd
    if fa / fd >= 1.10:
        tags.append(_tag("forteresse", "🏰", f"Forteresse — {h}",
                         f"{h} joue nettement mieux chez lui que son niveau moyen (+{(fa / fd - 1) * 100:.0f} % net à domicile).",
                         supports=["1", "1N"], effect=f"+{(fa - 1) * 100:.0f} % de buts à domicile"))
    elif fa / fd <= 0.90:
        tags.append(_tag("domicile-maudit", "🫥", f"Domicile maudit — {h}",
                         f"{h} est moins bon à la maison qu'en déplacement, à l'inverse de presque tout le monde.",
                         supports=["N2"], against=["1"]))
    fa, fd = models.home_fx.get(a, (1.0, 1.0))
    adj["a"] /= fa
    adj["h"] /= fd
    if fd / fa >= 1.10:
        tags.append(_tag("voyageur", "🧳", f"Voyageur — {a}",
                         f"{a} garde son niveau loin de chez lui, bien mieux que la moyenne des équipes.",
                         supports=["2", "N2"], against=["1"]))

    derby = DERBIES.get(frozenset((h, a)))
    if derby:
        adj["h"] *= 0.96
        adj["a"] *= 0.96
        adj["cards"] *= 1.15
        tags.append(_tag("derby", "⚔️", derby,
                         "Les derbys sont plus fermés et plus nerveux : un peu moins de buts, plus de cartons.",
                         supports=["u25", "cards+"], effect="−4 % de buts, +15 % de cartons"))

    ref = fx.get("ref")
    rf = models.ref_factor.get(ref) if ref else None
    if rf:
        adj["cards"] *= min(1.35, max(0.75, rf))
        if rf >= 1.12:
            tags.append(_tag("arbitre-severe", "🟨", f"Arbitre à cartons — {ref}",
                             f"{ref} sort {(rf - 1) * 100:.0f} % de cartons de plus que ce que les équipes "
                             f"prennent d'habitude.", supports=["cards+"]))
        elif rf <= 0.88:
            tags.append(_tag("arbitre-coulant", "🕊️", f"Arbitre coulant — {ref}",
                             f"{ref} sort {(1 - rf) * 100:.0f} % de cartons de moins que la moyenne.", supports=["cards-"]))

    if weather:
        k = 1.0
        if weather["rain"] >= 4:
            k *= 0.92
            tags.append(_tag("deluge", "🌧️", "Déluge annoncé",
                             f"{_f(weather['rain'])} mm/h de pluie prévus au coup d'envoi : terrain lourd, jeu haché.",
                             supports=["u25"], effect="−8 % de buts"))
        elif weather["rain"] >= 1.5:
            k *= 0.96
            tags.append(_tag("pluie", "🌦️", "Pluie au coup d'envoi",
                             f"{_f(weather['rain'])} mm/h prévus : ballon glissant, un peu moins de buts.",
                             supports=["u25"], effect="−4 % de buts"))
        if weather["wind"] >= 35:
            k *= 0.96
            tags.append(_tag("vent", "💨", "Gros vent",
                             f"Rafales de {weather['wind']:.0f} km/h : jeu long difficile, moins de précision.",
                             supports=["u25"], effect="−4 % de buts"))
        if weather["temp"] <= 0:
            k *= 0.98
            tags.append(_tag("froid", "🥶", "Froid polaire", f"{_f(weather['temp'])} °C au coup d'envoi.",
                             supports=["u25"], effect="−2 % de buts"))
        adj["h"] *= k
        adj["a"] *= k
        info["weather"] = weather
    return adj, tags, info
