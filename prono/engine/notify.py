"""Notifications sur le téléphone : ntfy (appli gratuite, sans compte) et/ou Telegram."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess

from .data import ROOT

STATE_FILE = os.path.join(ROOT, "data", "notified.json")
DAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def send(cfg: dict, title: str, message: str, priority: int = 3, tags=None, at: dt.datetime | None = None):
    """Envoie tout de suite, ou à l'heure `at` : ntfy garde la notif et la délivre au bon moment."""
    n = cfg["notify"]
    if n.get("ntfy_topic"):
        payload = {"topic": n["ntfy_topic"], "title": title, "message": message,
                   "priority": priority, "tags": tags or []}
        if cfg.get("public_url"):
            payload["click"] = cfg["public_url"]  # toucher la notif ouvre l'appli
        if at:
            payload["delay"] = str(int(at.timestamp()))
        subprocess.run(["curl", "-sS", "--fail", "-m", "20", "-H", "Content-Type: application/json",
                        "-d", json.dumps(payload), "https://ntfy.sh/"], check=True, capture_output=True)
    if n.get("telegram_token") and n.get("telegram_chat_id"):
        subprocess.run(["curl", "-sS", "--fail", "-m", "20",
                        "--data-urlencode", f"chat_id={n['telegram_chat_id']}",
                        "--data-urlencode", f"text={title}\n\n{message}",
                        f"https://api.telegram.org/bot{n['telegram_token']}/sendMessage"],
                       check=True, capture_output=True)


def _when(ko: dt.datetime, tbc: bool = False) -> str:
    return f"{DAYS[ko.weekday()]} " + ("(horaire à venir)" if tbc else f"{ko:%H:%M}")


def _num(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def _icon(s: dict) -> str:
    return "🎾" if s["match_id"].startswith("tn-") else "⚽"


def _card(s: dict, bank: float) -> str:
    """Le corps d'une notif pour un seul prono : trois lignes courtes, lisibles écran verrouillé."""
    out = (f"{_icon(s)} {s['match']} · {_when(s['ko'], s.get('time_tbc'))}\n"
           f"Joue à partir de {_num(s['min_odds'])} · proba {s['p'] * 100:.0f} % · mise {_num(bank * s['stake_pct'])} €")
    if s.get("tag_titles"):
        out += f"\n{s['tag_titles'][0]}"
    return out


def _short(s: dict) -> str:
    """Une ligne de liste : le pari et sa cote mini, puis le match."""
    return f"• {s['label']} (≥ {_num(s['min_odds'])})\n   {_icon(s)} {s['match']} · {_when(s['ko'], s.get('time_tbc'))}"


def _uid(kind: str, s: dict) -> str:
    return f"{kind}:{s['id']}" if kind == "combo" else f"{kind}:{s['match_id']}:{s['key']}"


def _load() -> dict:
    try:
        with open(STATE_FILE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _pre_match(m: dict, picks: list, bank: float):
    """Titre, texte et priorité de la notif d'avant-match : quoi jouer, ou passer son tour."""
    title = f"{m['home']} – {m['away']} · {m['ko']:%H:%M}"
    if not picks:
        p = m["probs"]
        return title, ("Rien qui vaille le coup sur ce match : passe ton tour.\n"
                       f"Probas : 1 {p['1'] * 100:.0f} % · N {p['N'] * 100:.0f} % · 2 {p['2'] * 100:.0f} %"), 2
    main = picks[0]
    body = (f"À jouer : {main['label']}\n"
            f"Joue à partir de {_num(main['min_odds'])} · proba {main['p'] * 100:.0f} % · mise {_num(bank * main['stake_pct'])} €")
    for s in picks[1:3]:
        body += f"\nAussi : {s['label']} (≥ {_num(s['min_odds'])})"
    if main.get("tag_titles"):
        body += f"\n{main['tag_titles'][0]}"
    return title, body, 4


def dispatch(cfg: dict, rep: dict, now: dt.datetime, log=print):
    """Une notif avant chaque match des grands championnats, programmée chez ntfy pour arriver
    avant le coup d'envoi ; pour le reste (tennis, Ligue 2, combinés), les nouveautés à chaque passage."""
    n = cfg["notify"]
    sent = set(_load().get("sent", []))
    bank, big = cfg["bankroll"], set(n["match_leagues"])
    lead, window = dt.timedelta(minutes=n["match_lead_min"]), dt.timedelta(hours=n["match_window_h"])
    div_of = {m["id"]: m.get("div") for m in rep["matches"]}
    msgs = []  # (titre, texte, priorité, tags, identifiants, heure d'envoi)

    picks = {}
    for lst in (rep["contre_pieds"], rep["solides"], rep["stats"]):  # le contre-pied passe en premier
        for s in lst:
            picks.setdefault(s["match_id"], []).append(s)
    for m in rep["matches"]:
        uid = f"match:{m['id']}"
        if m.get("div") in big and now < m["ko"] <= now + window and uid not in sent:
            title, body, prio = _pre_match(m, picks.get(m["id"], []), bank)
            msgs.append((title, body, prio, ["soccer"], [uid], max(m["ko"] - lead, now)))

    others = lambda s: div_of.get(s["match_id"]) not in big
    cps = [s for s in rep["contre_pieds"] if others(s) and _uid("cp", s) not in sent]
    for s in cps[:5]:
        msgs.append((s["label"], _card(s, bank), 4, ["dart"], [_uid("cp", s)], now))
    if len(cps) > 5:
        rest = cps[5:]
        msgs.append((f"+{len(rest)} autres contre-pieds", "\n".join(_short(s) for s in rest[:10]), 3, ["dart"],
                     [_uid("cp", s) for s in rest], now))
    sol = [s for s in rep["solides"] if others(s) and _uid("sol", s) not in sent]
    if sol:
        msgs.append(("Les Solides (objectif 80 %)", "\n".join(_short(s) for s in sol), 3, ["lock"],
                     [_uid("sol", s) for s in sol], now))
    coup = rep.get("coup")
    if coup and _uid("combo", coup) not in sent:
        legs = "\n".join(f"• {x['label']} (≥ {_num(x['min_odds'])})\n   {_icon(x)} {x['match']} · {_when(x['ko'], x.get('time_tbc'))}"
                         for x in coup["legs"])
        why = "\n".join(f"{r['icon']} {r['title']}" for r in coup.get("reasons", [])[:2])
        body = f"{legs}\n{why}\nProba {coup['p'] * 100:.0f} % · mise {_num(bank * coup['stake_pct'])} €"
        msgs.append((f"La grosse cote du jour · ≈ {_num(coup['fair'])}", body, 4, ["dart"], [_uid("combo", coup)], now))
    for c in rep["combos"]:
        if _uid("combo", c) in sent:
            continue
        legs = "\n".join(f"• {x['label']}\n   {_icon(x)} {x['match']}" for x in c["legs"])
        body = f"{legs}\n1 chance sur {c['one_in']:.0f} · mise {_num(bank * c['stake_pct'])} €"
        odds = f"cote juste ≈ {_num(c['odds'], 0)}" if c["kind"] in ("enfer", "mille") else f"cote ≥ {_num(c['odds'])}"
        msgs.append((f"{c['name']} · {odds}", body, 3,
                     [{"chatte": "four_leaf_clover", "enfer": "fire", "mille": "slot_machine"}.get(c["kind"], "bricks")], [_uid("combo", c)], now))

    for title, body, prio, tags, uids, at in msgs:
        later = at - now > dt.timedelta(minutes=1)
        try:
            send(cfg, title, body, prio, tags, at=at if later else None)
        except subprocess.CalledProcessError as e:
            log(f"Notification non envoyée ({title}) : {e.stderr.decode(errors='replace').strip()}")
            continue
        sent.update(uids)
        log(f"Notification {'programmée à ' + at.strftime('%H:%M') if later else 'envoyée'} : {title}")
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as fh:
        json.dump({"sent": sorted(sent)}, fh, indent=1)
