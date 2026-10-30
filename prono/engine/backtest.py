"""Backtest « walk-forward » : on rejoue des saisons passées semaine par semaine, sans jamais voir le futur.

1. Saison N-2 : on mesure chaque critère surprise (est-ce qu'il voit plus juste que le modèle ?).
2. Saison N-1 : on joue les pronos avec les seuls critères validés sur N-2 — un vrai test hors échantillon.
Les critères utilisés en direct sont ensuite mesurés sur les deux saisons cumulées.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from collections import defaultdict

from . import criteria, data, model, picks
from .tracker import settle

ALPHAS = [0.0, 0.2, 0.35, 0.5, 0.7, 1.0]
OUT_FILE = os.path.join(data.ROOT, "data", "backtest.json")
RAW_FIELDS = ("n", "won", "p", "base", "n_mkt", "won_mkt", "p_mkt", "priced", "profit")


def collect(cfg: dict, season_back: int = 1, log=print):
    today = dt.date.today()
    target, prev = data.season_code(today, season_back), data.season_code(today, season_back + 1)
    fams = []
    for d in cfg["leagues"]:
        if data.family(d) not in fams:
            fams.append(data.family(d))
    records = []
    for fam in fams:
        res = data.load_results(fam, [prev, target])
        test = [m for m in res if data.season_code(m["date"]) == target and m["div"] in cfg["leagues"]]
        if not test:
            continue
        ref = test[0]["ko"].replace(hour=0, minute=0)
        n0 = len(records)
        while ref <= test[-1]["ko"]:
            nxt = ref + dt.timedelta(days=7)
            week = [m for m in test if ref <= m["ko"] < nxt]
            if week:
                models = model.Models(res, ref, cfg)
                hist = criteria.build_history([m for m in res if m["ko"] < ref], models.conv)
                for m in week:
                    an = picks.analyse(m, models, hist, cfg)
                    an["week"] = ref.date().isoformat()
                    records.append((m, an))
            ref = nxt
        log(f"  {' + '.join(data.LEAGUES[d] for d in fam if d in cfg['leagues'])} : {len(records) - n0} matchs")
    return f"20{target[:2]}/{target[2:]}", records


def tag_study(records: list) -> dict:
    """Compte brut, par critère, des paris qu'il soutient (gagnés, probas prévues, écart moyen du modèle)."""
    base = defaultdict(lambda: [0, 0, 0.0])
    rows = []
    for m, an in records:
        for s in an["sels"]:
            won = settle(s["key"], m)
            if won is None:
                continue
            b = base[s.get("base_key", s["key"])]
            b[0] += 1
            b[1] += won
            b[2] += s["p"]
            rows += [(tid, s, won) for tid in s["tags"]]
    gap = {k: (v[1] - v[2]) / v[0] for k, v in base.items()}
    raw = defaultdict(lambda: dict.fromkeys(RAW_FIELDS, 0))
    for tid, s, won in rows:
        t = raw[tid]
        t["n"] += 1
        t["won"] += won
        t["p"] += s["p"]
        t["base"] += gap[s.get("base_key", s["key"])]
        if s["p_mkt"] is not None:
            t["n_mkt"] += 1
            t["won_mkt"] += won
            t["p_mkt"] += s["p_mkt"]
        if s["odds"]:
            t["priced"] += 1
            t["profit"] += s["odds"] - 1 if won else -1
    return dict(raw)


def merge_raw(*raws: dict) -> dict:
    out = {}
    for raw in raws:
        for tid, t in raw.items():
            acc = out.setdefault(tid, dict.fromkeys(RAW_FIELDS, 0))
            for f in RAW_FIELDS:
                acc[f] += t[f]
    return out


def _clv(odds: float, closing, i: int):
    return odds * model.devig(closing)[i] - 1 if closing else None


def value_bets_study(records: list, cfg: dict) -> dict:
    """Les « value bets » classiques sur 1N2 et +/-2,5, pour chaque poids du modèle face au marché."""
    out = {}
    for a in ALPHAS:
        ll = ll_ou = n = n_ou = 0
        bets = []
        for m, an in records:
            win_idx = 0 if m["hg"] > m["ag"] else 1 if m["hg"] == m["ag"] else 2
            od = m["odds"]
            if an["p_mkt"]:
                pf = [a * an["pm"][k] + (1 - a) * an["p_mkt"][i] for i, k in enumerate("1N2")]
                ll -= math.log(max(pf[win_idx], 1e-6))
                n += 1
                if od["avg"]:
                    for i, k in enumerate("1N2"):
                        if (pf[i] * od["avg"][i] - 1 >= cfg["edge_min"] and pf[i] >= 0.2
                                and an["pm"][k] - an["p_mkt"][i] >= 0.02):
                            won = i == win_idx
                            bets.append((od["avg"][i] - 1 if won else -1, won, _clv(od["avg"][i], od["c_avg"], i)))
            if an["p_mkt_ou"] is not None:
                po = a * an["pm"]["o25"] + (1 - a) * an["p_mkt_ou"]
                over = m["hg"] + m["ag"] >= 3
                ll_ou -= math.log(max(po if over else 1 - po, 1e-6))
                n_ou += 1
                if od["ou_avg"]:
                    for i, (p, won, diff) in enumerate(((po, over, an["pm"]["o25"] - an["p_mkt_ou"]),
                                                        (1 - po, not over, an["p_mkt_ou"] - an["pm"]["o25"]))):
                        if p * od["ou_avg"][i] - 1 >= cfg["edge_min"] and diff >= 0.02:
                            bets.append((od["ou_avg"][i] - 1 if won else -1, won,
                                         _clv(od["ou_avg"][i], od["c_ou_avg"], i)))
        clv = [c for *_, c in bets if c is not None]
        out[str(a)] = {"bets": len(bets), "logloss_1x2": ll / max(n, 1), "logloss_ou": ll_ou / max(n_ou, 1),
                       "roi": sum(p for p, _, _ in bets) / len(bets) if bets else None,
                       "hit": sum(w for _, w, _ in bets) / len(bets) if bets else None,
                       "clv": sum(clv) / len(clv) if clv else None}
    return out


def _approx_odds(s: dict, m: dict):
    """Cote réelle si connue, sinon cote de double chance reconstruite à partir des cotes 1N2."""
    if s["odds"]:
        return s["odds"]
    o = m["odds"]["avg"]
    if o and s["key"] in ("1N", "N2", "12"):
        i, j = {"1N": (0, 1), "N2": (1, 2), "12": (0, 2)}[s["key"]]
        return 1 / (1 / o[i] + 1 / o[j])
    return None


def _cat(items: list) -> dict:
    """items : (sélection, gagné, cote réelle ou approchée, ou None)"""
    if not items:
        return {"n": 0}
    priced = [(w, o) for _, w, o in items if o]
    return {"n": len(items), "hit": sum(w for _, w, _ in items) / len(items),
            "expected_hit": sum(s["p"] for s, _, _ in items) / len(items), "priced": len(priced),
            "roi": sum(o - 1 if w else -1 for w, o in priced) / len(priced) if priced else None}


def evaluate(records: list, cfg: dict) -> dict:
    by_id = {an["id"]: m for m, an in records}
    weeks = defaultdict(list)
    for m, an in records:
        weeks[an["week"]].append(an)

    cats, combos = defaultdict(list), defaultdict(list)
    for week, ans in sorted(weeks.items()):
        sol, cps, sts = picks.solides(ans, cfg), picks.contre_pieds(ans, cfg), picks.stats_a_jouer(ans, cfg)
        for name, lst in (("solides", sol), ("contre_pieds", cps), ("stats", sts)):
            for s in lst:
                m = by_id[s["match_id"]]
                won = settle(s["key"], m)
                if won is not None:
                    cats[name].append((s, won, _approx_odds(s, m)))
                    if name == "contre_pieds" and s["breaks"]:
                        cats["contre_pieds_casse_series"].append((s, won, _approx_odds(s, m)))
        for c in picks.combines(sol, cps, sts, cfg):
            res = [settle(leg["key"], by_id[leg["match_id"]]) for leg in c["legs"]]
            if None not in res:
                combos[c["name"]].append((all(res), c["p"], c["one_in"]))

    naive = {"n": 0, "nil_nil": 0, "draws": 0, "p00": 0.0, "pN": 0.0, "piege_n": 0, "piege_o15": 0}
    for m, an in records:
        if an["info"].get("naive00"):
            naive["n"] += 1
            naive["nil_nil"] += m["hg"] == 0 and m["ag"] == 0
            naive["draws"] += m["hg"] == m["ag"]
            naive["p00"] += next(s["p"] for s in an["sels"] if s["key"] == "cs:0-0")
            naive["pN"] += an["probs"]["N"]
            if any(t["id"] == "piege-00" for t in an["tags"]):
                naive["piege_n"] += 1
                naive["piege_o15"] += m["hg"] + m["ag"] >= 2

    return {
        "matches": len(records),
        "value_bets": value_bets_study(records, cfg),
        "categories": {k: _cat(v) for k, v in cats.items()},
        "combos": {k: {"n": len(v), "won": sum(w for w, _, _ in v), "expected_won": sum(p for _, p, _ in v),
                       "avg_one_in": sum(x for *_, x in v) / len(v)} for k, v in combos.items()},
        "naive00": naive,
    }


def run(cfg: dict, log=print) -> dict:
    log("Saison N-2 : mesure des critères…")
    s2, rec2 = collect(cfg, 2, log)
    raw2 = tag_study(rec2)
    log("Saison N-1 : test des pronos avec les critères validés sur N-2…")
    cfg1 = dict(cfg, tag_stats=raw2)
    s1, rec1 = collect(cfg1, 1, log)
    report = evaluate(rec1, cfg1)
    raw1 = tag_study(rec1)
    combined = merge_raw(raw2, raw1)
    report.update({
        "season": s1, "calibration_season": s2, "generated": dt.datetime.now().isoformat(timespec="minutes"),
        "validated_on_calibration": sorted(picks.tag_lifts(cfg1)),
        "tags_raw": combined,
        "tags": {tid: picks.tag_summary(r) for tid, r in combined.items() if r["n"]},
        "tags_by_season": {s2: {t: picks.tag_summary(r) for t, r in raw2.items() if r["n"]},
                           s1: {t: picks.tag_summary(r) for t, r in raw1.items() if r["n"]}},
    })
    if cfg.get("tennis", True):
        from . import tennis
        log("Tennis : calage sur la saison dernière, test sur celle en cours…")
        try:
            report["tennis"] = tennis.backtest(cfg, log)
        except Exception as e:  # le tennis ne doit jamais empêcher le bilan foot
            log(f"Tennis indisponible : {e}")
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    return report


def load() -> dict | None:
    try:
        with open(OUT_FILE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None
