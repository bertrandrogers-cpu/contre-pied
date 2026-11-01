"""Une passe complète : données → modèle → critères → pronos → suivi → tableau de bord → notifications."""
from __future__ import annotations

import datetime as dt

from . import backtest, criteria, dashboard, data, model, notify, picks, tennis, tracker, weather


def _tag_status(cfg: dict, bt: dict | None) -> dict:
    """Pour chaque critère : validé / démenti / pas assez de recul, d'après le backtest."""
    lifts = picks.tag_lifts(cfg)
    out = {}
    tags = dict((bt or {}).get("tags") or {}, **(((bt or {}).get("tennis") or {}).get("tags") or {}))
    for tid, s in tags.items():
        if tid in lifts:
            status = "ok"
        elif s["n"] >= cfg["tag_min_n"] and s["lift"] <= -cfg["tag_min_lift"]:
            status = "ko"
        else:
            status = "neutral"
        out[tid] = dict(s, status=status)
    return out


def run(cfg: dict, send_notifs: bool = True, log=print) -> dict:
    now = dt.datetime.now(data.PARIS)
    bt = backtest.load()
    if bt:
        tn = bt.get("tennis") or {}
        cfg = dict(cfg, tag_stats=dict(bt["tags_raw"], **tn.get("tags_raw", {})),
                   tennis_coef=tn.get("coef"), tennis_cal=tn.get("calibration"), tennis_games=tn.get("games"))
    else:
        log("Pas encore de backtest : lance « python3 prono.py backtest » pour activer les contre-pieds.")
    status = _tag_status(cfg, bt)

    horizon = now + dt.timedelta(days=cfg["horizon_days"])
    fixtures = [f for f in data.load_fixtures() if f["div"] in cfg["leagues"] and now < f["ko"] <= horizon]
    log(f"{len(fixtures)} matchs à venir sur {cfg['horizon_days']} jours")

    seasons = [data.season_code(now.date(), 1), data.season_code(now.date())]
    current = seasons[1]
    fams = []
    for d in cfg["leagues"]:
        if data.family(d) not in fams:
            fams.append(data.family(d))
    analyses, results, board = [], [], []
    for fam in fams:
        res = data.load_results(fam, seasons)
        results += res
        models = model.Models(res, now, cfg)
        hist = criteria.build_history(res, models.conv)
        for f in fixtures:
            if f["div"] in fam:
                w = weather.at_kickoff(f["home"], f["div"], f["ko"]) if cfg.get("weather") else None
                analyses.append(picks.analyse(f, models, hist, cfg, w))
        teams = {}
        for m in res:
            if m["div"] in cfg["leagues"] and data.season_code(m["date"]) == current:
                teams[m["home"]] = teams[m["away"]] = m["div"]
        board += picks.chatte_rows(hist, teams, now)
    if cfg.get("tennis", True):
        try:
            t_an, t_res = tennis.live(cfg, now, log)
            analyses += t_an
            results += t_res
        except Exception as e:  # une source tennis en panne ne doit pas bloquer le foot
            log(f"Tennis indisponible : {e}")
    analyses.sort(key=lambda a: a["ko"])
    for an in analyses:
        for t in an["tags"]:
            st = status.get(t["id"])
            t["status"] = st["status"] if st else "neutral"
            t["record"] = {k: st[k] for k in ("n", "hit", "expected_hit")} if st else None

    sol = picks.solides(analyses, cfg)
    cps = picks.contre_pieds(analyses, cfg)
    sts = picks.stats_a_jouer(analyses, cfg)
    combos = picks.combines(sol, cps, sts, cfg)
    hell = picks.enfer(analyses, cfg)
    if hell:
        combos.append(hell)
    log(f"{len(cps)} contre-pieds, {len(sol)} solides, {len(sts)} stats à jouer, {len(combos)} combinés")

    items = tracker.load()
    tracker.settle_all(items, results)
    for kind, lst in (("contre_pied", cps), ("solide", sol), ("stat", sts), ("combo", combos)):
        tracker.record(items, kind, lst, now)
    tracker.save(items)

    board.sort(key=lambda r: -r["luck"])
    rep = {
        "generated": now, "bankroll": cfg["bankroll"],
        "leagues": [data.LEAGUES.get(d, d) for d in cfg["leagues"]],
        "matches": analyses, "solides": sol, "contre_pieds": cps, "stats": sts, "combos": combos,
        "chatte": {"lucky": board[:10], "unlucky": board[::-1][:10]},
        "tracking": tracker.summary(items), "history": items[-80:],
        "backtest": dict({k: v for k, v in bt.items() if k not in ("tags_raw", "tennis")},
                         tennis={k: v for k, v in (bt.get("tennis") or {}).items() if k != "tags_raw"} or None)
        if bt else None,
        "tag_status": status, "tag_info": dict(criteria.TAG_INFO, **tennis.TAG_INFO),
        "tennis_tags": sorted(tennis.TAG_INFO),
    }
    log(f"Tableau de bord : {dashboard.write(rep)}")
    if send_notifs:
        notify.dispatch(cfg, rep, now, log)
    return rep
