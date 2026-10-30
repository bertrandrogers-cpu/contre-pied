"""Suivi des pronos émis : on garde tout, on règle quand le résultat tombe, on fait le bilan."""
from __future__ import annotations

import datetime as dt
import json
import os

from .data import ROOT

HISTORY_FILE = os.path.join(ROOT, "data", "history.json")


def settle(key: str, m: dict):
    """True/False si le pari est gagné/perdu avec le résultat m, None si la stat manque."""
    if m.get("sport") == "tennis":
        from .tennis import settle as settle_tennis
        return settle_tennis(key, m)
    hg, ag = m["hg"], m["ag"]
    t = hg + ag
    simple = {
        "1": hg > ag, "N": hg == ag, "2": hg < ag, "1N": hg >= ag, "N2": hg <= ag, "12": hg != ag,
        "o15": t >= 2, "u15": t < 2, "o25": t >= 3, "u25": t <= 2, "o35": t >= 4, "u35": t <= 3,
        "btts": hg > 0 and ag > 0, "nobtts": not (hg > 0 and ag > 0),
        "h_scores": hg > 0, "a_scores": ag > 0, "h_cs": ag == 0, "a_cs": hg == 0,
    }
    if key in simple:
        return simple[key]
    kind, val = key.split(":")
    if kind == "cs":
        return f"{int(hg)}-{int(ag)}" == val
    if kind in ("co", "cu"):
        if m["hc"] is None or m["ac"] is None:
            return None
        c = m["hc"] + m["ac"]
        return c > float(val) if kind == "co" else c < float(val)
    if kind in ("ko", "ku"):
        if m["hy"] is None or m["ay"] is None:
            return None
        c = m["hy"] + m["ay"] + (m["hr"] or 0) + (m["ar"] or 0)
        return c > float(val) if kind == "ko" else c < float(val)
    return None


def load() -> list:
    try:
        with open(HISTORY_FILE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def save(items: list):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, HISTORY_FILE)


def _leg_record(s: dict) -> dict:
    return {"match_id": s["match_id"], "match": s["match"], "league": s["league"], "ko": s["ko"].isoformat(),
            "key": s["key"], "label": s["label"], "p": round(s["p"], 4), "odds": s["odds"],
            "min_odds": round(s["min_odds"], 2), "result": None}


def record(items: list, kind: str, picks: list, now: dt.datetime):
    """Ajoute les pronos jamais vus. La première cote vue est conservée (c'est celle qu'on t'a notifiée)."""
    known = {i["uid"] for i in items}
    for s in picks:
        uid = f"{kind}:{s['id']}" if kind == "combo" else f"{kind}:{s['match_id']}:{s['key']}"
        if uid in known:
            continue
        if kind == "combo":
            rec = {"uid": uid, "kind": kind, "name": s["name"], "legs": [_leg_record(x) for x in s["legs"]],
                   "p": round(s["p"], 5), "odds": round(s["odds"], 2), "result": None}
        else:
            rec = dict(_leg_record(s), uid=uid, kind=kind)
        rec["created"] = now.isoformat()
        items.append(rec)
        known.add(uid)


def settle_all(items: list, results: list):
    by_id = {m["id"]: m for m in results}
    for it in items:
        if it["result"] is not None:
            continue
        legs = it["legs"] if it["kind"] == "combo" else [it]
        for leg in legs:
            if leg["result"] is None and leg["match_id"] in by_id:
                won = settle(leg["key"], by_id[leg["match_id"]])
                if won is not None:
                    leg["result"] = "won" if won else "lost"
        if it["kind"] == "combo":
            res = [leg["result"] for leg in legs]
            if "lost" in res:
                it["result"] = "lost"
            elif all(r == "won" for r in res):
                it["result"] = "won"


def summary(items: list) -> dict:
    out = {}
    for it in items:
        if it["result"] is None:
            continue
        s = out.setdefault(it["kind"], {"n": 0, "won": 0, "staked": 0, "profit": 0.0, "p_sum": 0.0})
        s["n"] += 1
        s["p_sum"] += it["p"]
        won = it["result"] == "won"
        s["won"] += won
        odds = it["odds"] or it.get("min_odds")
        if odds:
            s["staked"] += 1
            s["profit"] += (odds - 1) if won else -1
    for s in out.values():
        s["hit"] = s["won"] / s["n"]
        s["expected_hit"] = s.pop("p_sum") / s["n"]
        s["roi"] = s["profit"] / s["staked"] if s["staked"] else None
    return out
