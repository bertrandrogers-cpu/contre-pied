"""Notifications sur le téléphone : ntfy (appli gratuite, sans compte) et/ou Telegram."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess

from .data import ROOT

STATE_FILE = os.path.join(ROOT, "data", "notified.json")
DAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def send(cfg: dict, title: str, message: str, priority: int = 3, tags=None):
    n = cfg["notify"]
    if n.get("ntfy_topic"):
        payload = {"topic": n["ntfy_topic"], "title": title, "message": message,
                   "priority": priority, "tags": tags or []}
        if cfg.get("public_url"):
            payload["click"] = cfg["public_url"]  # toucher la notif ouvre l'appli
        subprocess.run(["curl", "-sS", "--fail", "-m", "20", "-H", "Content-Type: application/json",
                        "-d", json.dumps(payload), "https://ntfy.sh/"], check=True, capture_output=True)
    if n.get("telegram_token") and n.get("telegram_chat_id"):
        subprocess.run(["curl", "-sS", "--fail", "-m", "20",
                        "--data-urlencode", f"chat_id={n['telegram_chat_id']}",
                        "--data-urlencode", f"text={title}\n\n{message}",
                        f"https://api.telegram.org/bot{n['telegram_token']}/sendMessage"],
                       check=True, capture_output=True)


def _when(ko: dt.datetime) -> str:
    return f"{DAYS[ko.weekday()]} {ko:%H:%M}"


def _num(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def _icon(s: dict) -> str:
    return "🎾" if s["match_id"].startswith("tn-") else "⚽"


def _card(s: dict, bank: float) -> str:
    """Le corps d'une notif pour un seul prono : trois lignes courtes, lisibles écran verrouillé."""
    out = (f"{_icon(s)} {s['match']} · {_when(s['ko'])}\n"
           f"Joue à partir de {_num(s['min_odds'])} · proba {s['p'] * 100:.0f} % · mise {_num(bank * s['stake_pct'])} €")
    if s.get("tag_titles"):
        out += f"\n{s['tag_titles'][0]}"
    return out


def _short(s: dict) -> str:
    """Une ligne de liste : le pari et sa cote mini, puis le match."""
    return f"• {s['label']} (≥ {_num(s['min_odds'])})\n   {_icon(s)} {s['match']} · {_when(s['ko'])}"


def _uid(kind: str, s: dict) -> str:
    return f"{kind}:{s['id']}" if kind == "combo" else f"{kind}:{s['match_id']}:{s['key']}"


def _load() -> dict:
    try:
        with open(STATE_FILE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def dispatch(cfg: dict, rep: dict, now: dt.datetime, log=print):
    """Envoie seulement ce qui est nouveau depuis la dernière fois, plus un rappel avant le coup d'envoi."""
    st = _load()
    sent, reminded = set(st.get("sent", [])), set(st.get("reminded", []))
    bank = cfg["bankroll"]
    msgs = []

    cps = [s for s in rep["contre_pieds"] if _uid("cp", s) not in sent]
    for s in cps[:5]:
        msgs.append((s["label"], _card(s, bank), 4, ["dart"], [_uid("cp", s)], "sent"))
    if len(cps) > 5:
        rest = cps[5:]
        msgs.append((f"+{len(rest)} autres contre-pieds", "\n".join(_short(s) for s in rest[:10]), 3, ["dart"],
                     [_uid("cp", s) for s in rest], "sent"))
    sol = [s for s in rep["solides"] if _uid("sol", s) not in sent]
    if sol:
        msgs.append(("Les Solides (objectif 80 %)", "\n".join(_short(s) for s in sol), 3, ["lock"],
                     [_uid("sol", s) for s in sol], "sent"))
    for c in rep["combos"]:
        if _uid("combo", c) in sent:
            continue
        legs = "\n".join(f"• {x['label']}\n   {_icon(x)} {x['match']}" for x in c["legs"])
        body = f"{legs}\n1 chance sur {c['one_in']:.0f} · mise {_num(bank * c['stake_pct'])} €"
        msgs.append((f"{c['name']} · cote ≥ {_num(c['odds'])}", body, 3,
                     ["four_leaf_clover" if c["kind"] == "chatte" else "bricks"], [_uid("combo", c)], "sent"))

    soon = []
    for kind, lst in (("cp", rep["contre_pieds"]), ("sol", rep["solides"])):
        for s in lst:
            left = (s["ko"] - now).total_seconds() / 3600
            if 0 < left <= cfg["notify"]["remind_hours"] and _uid(kind, s) not in reminded:
                soon.append((kind, s))
    if soon:
        msgs.append(("Ça commence bientôt", "\n".join(_short(s) for _, s in soon), 4, ["alarm_clock"],
                     [_uid(k, s) for k, s in soon], "reminded"))

    for title, body, prio, tags, uids, bucket in msgs:
        try:
            send(cfg, title, body, prio, tags)
        except subprocess.CalledProcessError as e:
            log(f"Notification non envoyée ({title}) : {e.stderr.decode(errors='replace').strip()}")
            continue
        (sent if bucket == "sent" else reminded).update(uids)
        log(f"Notification envoyée : {title}")
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as fh:
        json.dump({"sent": sorted(sent), "reminded": sorted(reminded)}, fh, indent=1)
