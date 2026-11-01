"""Assemble tout : probabilités finales, sélections, catégories (Solides, Contre-pieds, Stats) et combinés."""
from __future__ import annotations

import hashlib

from . import criteria, model
from .data import LEAGUES

# Tags qui contredisent une lecture naïve des séries en cours : ce sont eux qui font les « contre-pieds ».
ANTI_NAIVE = {"fausse-panne", "muraille-carton", "serie-trompe-oeil", "ca-va-tourner", "chanceux", "poissard",
              "piege-00", "feu-artifice-evente", "popularite"}
SHOT_LINES = [19.5, 20.5, 21.5, 22.5, 23.5, 24.5, 25.5, 26.5, 27.5, 28.5, 29.5, 30.5]
SOT_LINES = [5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]
# Marchés de stats : jamais dans les Solides ni les contre-pieds, ils ont leur propre rubrique.
STAT_PREFIXES = ("cs:", "co:", "cu:", "ko:", "ku:", "tirs", "cadres", "jeux")
STAT_FAMILIES = (("tirs+", "tirs-"), ("cadres+", "cadres-"), ("jeux+", "jeux-"))


def label(key: str, h: str, a: str) -> str:
    fixed = {
        "1": f"Victoire {h}", "N": "Match nul", "2": f"Victoire {a}", "1N": f"{h} ou nul", "N2": f"{a} ou nul",
        "12": "Pas de match nul", "o15": "Plus de 1,5 buts", "u15": "Moins de 1,5 buts", "o25": "Plus de 2,5 buts", "u25": "Moins de 2,5 buts",
        "o35": "Plus de 3,5 buts", "u35": "Moins de 3,5 buts", "btts": "Les deux équipes marquent",
        "nobtts": "Les deux équipes marquent : non", "h_scores": f"{h} marque", "a_scores": f"{a} marque",
        "h_cs": f"{h} ne prend pas de but", "a_cs": f"{a} ne prend pas de but",
    }
    if key in fixed:
        return fixed[key]
    kind, val = key.split(":")
    line = val.replace(".", ",")
    return {"cs": f"Score exact {val}", "co": f"Plus de {line} corners", "cu": f"Moins de {line} corners",
            "ko": f"Plus de {line} cartons", "ku": f"Moins de {line} cartons",
            "tirs+": f"Plus de {line} tirs", "tirs-": f"Moins de {line} tirs",
            "cadres+": f"Plus de {line} tirs cadrés", "cadres-": f"Moins de {line} tirs cadrés"}[kind]


def _tag_hits(sel_key: str, tag_key: str) -> bool:
    if tag_key == "cards+":
        return sel_key.startswith("ko:")
    if tag_key == "cards-":
        return sel_key.startswith("ku:")
    if tag_key == "00":
        return sel_key == "cs:0-0"
    return sel_key == tag_key


def _market_tags(fx, p_mkt, mk_model, tags):
    od, h, a = fx["odds"], fx["home"], fx["away"]
    if od["sharp"] and od["avg"]:
        ps, pa = model.devig(od["sharp"]), model.devig(od["avg"])
        for i, k in enumerate(("1", "N", "2")):
            if ps[i] - pa[i] >= 0.03:
                tags.append(criteria._tag(
                    "argent-malin", "💸", f"L'argent malin pousse : {label(k, h, a)}",
                    f"Sur la bourse aux paris (là où jouent les pros), « {label(k, h, a)} » est à {ps[i] * 100:.0f} % "
                    f"contre {pa[i] * 100:.0f} % chez les bookmakers classiques. Les gros parieurs savent quelque chose.",
                    supports=[k]))
            if od["max"] and od["max"][i] >= 1.06 / ps[i]:
                tags.append(criteria._tag(
                    "cote-en-retard", "🐢", f"Bookmaker en retard : {label(k, h, a)}",
                    f"Un bookmaker paie {od['max'][i]:.2f} alors que la cote juste est {1 / ps[i]:.2f}. "
                    f"Compare les sites avant de jouer.", supports=[k]))
    if p_mkt:
        for team, idx, side in ((h, 0, "h"), (a, 2, "a")):
            diff = p_mkt[idx] - mk_model["1" if idx == 0 else "2"]
            if team in criteria.POPULAR and diff >= 0.05:
                K = criteria._keys(side)
                tags.append(criteria._tag(
                    "popularite", "📣", f"Taxe de popularité — {team}",
                    f"Le grand public fonce sur {team} : le marché le voit gagnant à {p_mkt[idx] * 100:.0f} %, "
                    f"nos stats disent {mk_model['1' if idx == 0 else '2'] * 100:.0f} %. Sa cote est trop basse.",
                    supports=[K["opp_dc"]], against=[K["win"]]))


def analyse(fx: dict, models, hist: dict, cfg: dict, weather=None) -> dict:
    h, a = fx["home"], fx["away"]
    lam0 = models.goals.expect(h, a)
    adj, tags, info = criteria.evaluate(fx, hist, models, lam0, weather)
    lh, la = lam0[0] * adj["h"], lam0[1] * adj["a"]
    mk_model = model.markets(model.score_matrix(lh, la))
    od = fx["odds"]
    ref = od["sharp"] or od["avg"]
    ref_ou = od["ou_sharp"] or od["ou_avg"]
    p_mkt = model.devig(ref) if ref else None
    p_mkt_ou = model.devig(ref_ou)[0] if ref_ou else None
    a1, a2 = cfg["alpha_1x2"], cfg["alpha_ou"]
    t1, t2 = mk_model["1"], mk_model["2"]
    if p_mkt:
        t1, t2 = a1 * t1 + (1 - a1) * p_mkt[0], a1 * t2 + (1 - a1) * p_mkt[2]
    to = a2 * mk_model["o25"] + (1 - a2) * p_mkt_ou if p_mkt_ou else mk_model["o25"]
    lhf, laf = model.fit_lambdas(t1, t2, to, start=(lh, la)) if (p_mkt or p_mkt_ou) else (lh, la)
    mk = model.markets(model.score_matrix(lhf, laf))
    _market_tags(fx, p_mkt, mk_model, tags)

    mu_shots = sum(models.shots.expect(h, a))
    mu_sot = sum(models.sot.expect(h, a))

    mkt_p = {}
    if p_mkt:
        mkt_p.update({"1": p_mkt[0], "N": p_mkt[1], "2": p_mkt[2]})
    if p_mkt_ou:
        mkt_p.update({"o25": p_mkt_ou, "u25": 1 - p_mkt_ou})
    odds_avg, odds_max = {}, {}
    for i, k in enumerate(("1", "N", "2")):
        if od["avg"]:
            odds_avg[k] = od["avg"][i]
        if od["max"]:
            odds_max[k] = od["max"][i]
    for i, k in enumerate(("o25", "u25")):
        if od["ou_avg"]:
            odds_avg[k] = od["ou_avg"][i]
        if od["ou_max"]:
            odds_max[k] = od["ou_max"][i]

    probs = {k: v for k, v in mk.items() if k != "scores"}
    probs.update({f"cs:{s}": p for s, p in mk["scores"][:3]})
    probs["cs:0-0"] = model.score_matrix(lhf, laf)[0][0]
    if models.shots.att:
        for line in SHOT_LINES:
            po = model.over_prob(mu_shots, line, cfg["shots_dispersion"])
            probs[f"tirs+:{line}"], probs[f"tirs-:{line}"] = po, 1 - po
    if models.sot.att:
        for line in SOT_LINES:
            po = model.over_prob(mu_sot, line, cfg["sot_dispersion"])
            probs[f"cadres+:{line}"], probs[f"cadres-:{line}"] = po, 1 - po

    sels = []
    for key, p in probs.items():
        if p <= 0.02 or p >= 0.995:
            continue
        s = {"key": key, "label": label(key, h, a), "p": p, "fair": 1 / p,
             "min_odds": (1 + cfg["min_edge_play"]) / p, "odds": odds_avg.get(key), "odds_max": odds_max.get(key),
             "p_mkt": mkt_p.get(key), "p_model": mk_model.get(key) if key in mk_model else None,
             "tags": [t["id"] for t in tags if any(_tag_hits(key, x) for x in t["supports"])],
             "against": [t["id"] for t in tags if any(_tag_hits(key, x) for x in t["against"])]}
        s["edge"] = p * s["odds"] - 1 if s["odds"] else None
        s["breaks"] = bool(set(s["tags"]) & ANTI_NAIVE)
        sels.append(s)

    return {
        "id": fx["id"], "div": fx["div"], "league": LEAGUES.get(fx["div"], fx["div"]), "ko": fx["ko"],
        "home": h, "away": a, "ref": fx.get("ref"), "xg": (lhf, laf), "xg_model": (lh, la),
        "shots": mu_shots, "sot": mu_sot, "probs": {k: probs[k] for k in ("1", "N", "2", "o25", "btts")},
        "pm": {k: mk_model[k] for k in ("1", "N", "2", "o25")},
        "p_mkt": p_mkt, "p_mkt_ou": p_mkt_ou, "odds": od, "scores": mk["scores"][:3],
        "tags": tags, "info": info, "sels": sels,
    }


# ---------- Catégories ----------

def _leg(m, s):
    return dict(s, match=f"{m['home']} - {m['away']}", match_id=m["id"], league=m["league"], ko=m["ko"],
                time_tbc=m.get("time_tbc", False),
                tag_titles=[f"{t['icon']} {t['title']}"
                            for t in sorted(m["tags"], key=lambda t: t.get("status") != "ok")
                            if t["id"] in s["tags"] and t.get("status") != "ko"])


def _kelly(p, odds, cfg):
    f = (p * odds - 1) / (odds - 1) * cfg["kelly_fraction"]
    return max(0.0, min(cfg["max_stake_pct"], f))


def tag_summary(raw: dict) -> dict:
    """Bilan d'un critère : réussite réelle des paris qu'il soutient vs ce que le modèle prévoyait.

    `lift` retire l'écart que le modèle a déjà en moyenne sur ces mêmes types de paris :
    il ne reste que ce que le critère apporte en propre.
    """
    n = raw["n"]
    return {"n": n, "hit": raw["won"] / n, "expected_hit": raw["p"] / n,
            "lift": (raw["won"] - raw["p"] - raw["base"]) / n,
            "market_hit": raw["won_mkt"] / raw["n_mkt"] if raw["n_mkt"] else None,
            "market_expected": raw["p_mkt"] / raw["n_mkt"] if raw["n_mkt"] else None,
            "roi": raw["profit"] / raw["priced"] if raw["priced"] else None, "priced": raw["priced"]}


def tag_lifts(cfg: dict) -> dict:
    """Critères validés par le backtest : assez de cas et une réussite au-dessus du modèle."""
    out = {}
    for tid, raw in (cfg.get("tag_stats") or {}).items():
        s = tag_summary(raw)
        if s["n"] >= cfg["tag_min_n"] and s["lift"] >= cfg["tag_min_lift"]:
            out[tid] = s["lift"]
    return out


def contre_pieds(analyses: list, cfg: dict) -> list:
    """Paris soutenus par un critère validé, qui va souvent contre la lecture naïve des séries.

    La probabilité est relevée de la moitié de l'avantage mesuré du critère (prudence).
    Sur les marchés où l'on connaît la cote, on exige qu'elle reste au-dessus de la cote juste.
    """
    lifts = tag_lifts(cfg)
    out = []
    for m in analyses:
        cands = []
        for s in m["sels"]:
            good = [lifts[t] for t in s["tags"] if t in lifts]
            if not good or s["against"] or s["key"].startswith(STAT_PREFIXES):
                continue
            lift = max(good)
            p = min(0.97, s["p"] + 0.5 * lift)
            if not 0.35 <= p <= 0.88:
                continue
            c = dict(s, p=p, fair=1 / p, min_odds=(1 + cfg["min_edge_play"]) / p, lift=lift)
            c["edge"] = p * c["odds"] - 1 if c["odds"] else None
            if c["edge"] is not None and c["edge"] < 0:
                continue
            cands.append(c)
        if cands:
            best = max(cands, key=lambda c: (c["lift"], c["fair"]))
            stake = _kelly(best["p"], best["odds"], cfg) if best["odds"] else cfg["stake_solide_pct"] / 2
            out.append(dict(_leg(m, best), stake_pct=stake))
    return sorted(out, key=lambda s: (-s["breaks"], -s["lift"], -s["p"]))


def solides(analyses: list, cfg: dict) -> list:
    out = []
    for m in analyses:
        cands = [s for s in m["sels"] if cfg["solide_min_p"] <= s["p"] <= 0.93 and not s["against"]
                 and (s["edge"] is None or s["edge"] >= -0.06) and not s["key"].startswith(STAT_PREFIXES)]
        if cands:
            best = max(cands, key=lambda s: (s["fair"], len(s["tags"])))
            out.append(dict(_leg(m, best), stake_pct=cfg["stake_solide_pct"]))
    return sorted(out, key=lambda s: -s["p"])[:cfg["max_solides"]]


def stats_a_jouer(analyses: list, cfg: dict) -> list:
    out = []
    for m in analyses:
        picks = []
        for prefix in STAT_FAMILIES:
            c = [s for s in m["sels"] if s["key"].startswith(prefix) and 0.62 <= s["p"] <= 0.85 and not s["against"]]
            if c:
                picks.append(max(c, key=lambda s: (len(s["tags"]), s["fair"])))
        for s in picks:
            out.append(dict(_leg(m, s), stake_pct=cfg["stake_solide_pct"] / 2))
    return sorted(out, key=lambda s: (-len(s["tags"]), -s["p"]))[:cfg["max_stats"]]


def _chance_text(n: float) -> str:
    if n < 4:
        return "Tranquille"
    if n < 12:
        return "Faut y croire"
    if n < 40:
        return "Grosse chatte requise"
    if n < 150:
        return "Chatte cosmique"
    return "Miracle de Lourdes"


def _combo(name, kind, legs, stake_pct, blurb):
    p, odds, fair, priced = 1.0, 1.0, 1.0, True
    for s in legs:
        p *= s["p"]
        fair *= s["fair"]
        odds *= s["odds"] or s["min_odds"]
        priced = priced and bool(s["odds"])
    cid = hashlib.sha1("|".join(f"{s['match_id']}:{s['key']}" for s in legs).encode()).hexdigest()[:10]
    return {"id": cid, "name": name, "kind": kind, "legs": legs, "p": p, "odds": odds, "fair": fair,
            "priced": priced, "ev": p * odds - 1, "one_in": 1 / p, "chance_text": _chance_text(1 / p),
            "stake_pct": stake_pct, "blurb": blurb}


def combines(sol: list, cps: list, stats: list, cfg: dict) -> list:
    out = []

    def distinct(pool, n, cond=lambda s: True):
        legs, seen = [], set()
        for s in pool:
            if s["match_id"] in seen or not cond(s):
                continue
            legs.append(s)
            seen.add(s["match_id"])
            if len(legs) == n:
                break
        return legs

    legs = distinct(sol, 3)
    if len(legs) >= 2:
        out.append(_combo("Le combiné béton", "solide", legs, cfg["stake_combo_pct"],
                          "Les sélections les plus sûres du moment, réunies."))
    pool = sorted(cps, key=lambda s: (-s["breaks"], -s["lift"]))
    legs = distinct(pool, 3, lambda s: 1.6 <= s["fair"] <= 3.5)
    if len(legs) >= 3:
        out.append(_combo("Petite chatte", "chatte", legs, cfg["stake_chatte_pct"],
                          "Trois contre-pieds validés par les stats. Ça se tente, sans y mettre le loyer."))
    # La grosse prend les contre-pieds les plus osés : les plus grosses cotes encore validées.
    legs = distinct(sorted(cps, key=lambda s: -s["fair"]), 5, lambda s: s["fair"] >= 1.4)
    if len(legs) < 5:
        used = {x["match_id"] for x in legs}
        legs += distinct([s for s in stats if s["match_id"] not in used], 5 - len(legs))
    if len(legs) >= 5:
        out.append(_combo("Grosse chatte", "chatte", legs, cfg["stake_chatte_pct"] / 2,
                          "Le ticket qui défie les stats : chaque sélection casse une série que tout le monde croit."))
    return out


def enfer(analyses: list, cfg: dict):
    """Le combiné de l'enfer : une petite cote par match, chacune au-dessus de 82 %, sur 24 matchs.

    Par match, on garde la sélection la mieux payée qui reste au-dessus du seuil (le maxi booster),
    puis les 24 meilleures cotes. Chaque jambe passe souvent ; les 24 ensemble, très rarement.
    """
    legs = []
    for m in analyses:
        cands = [s for s in m["sels"] if cfg["enfer_min_p"] < s["p"] <= 0.97 and not s["against"]
                 and not s["key"].startswith(STAT_PREFIXES)]
        if cands:
            legs.append(_leg(m, max(cands, key=lambda s: s["fair"])))
    legs = sorted(legs, key=lambda s: -s["fair"])[:cfg["enfer_legs"]]
    if len(legs) < cfg["enfer_min_legs"]:
        return None
    c = _combo("Le combiné de l'enfer", "enfer", sorted(legs, key=lambda s: s["ko"]), cfg["stake_enfer_pct"],
               f"{len(legs)} petites cotes, chacune au-dessus de {cfg['enfer_min_p'] * 100:.0f} %. Une par une, elles "
               f"passent presque toujours. Toutes ensemble, c'est l'enfer.")
    # On affiche la cote juste : ton site paiera moins, car sa marge se multiplie à chaque sélection.
    c["odds"], c["priced"] = c["fair"], False
    return c


def chatte_rows(hist: dict, teams: dict, now) -> list:
    """Indice de chatte de chaque équipe : positif = plus de points que son jeu n'en méritait."""
    rows = []
    for team, div in teams.items():
        lk = criteria.luck(criteria.before(hist.get(team, []), now))
        if lk:
            rows.append(dict(lk, team=team, league=LEAGUES.get(div, div)))
    return rows
