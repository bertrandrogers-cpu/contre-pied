#!/usr/bin/env python3
"""Contre-Pied — les pronos foot qui défient les stats.

  python3 prono.py run          met à jour les données, calcule les pronos, le tableau de bord et les notifs
  python3 prono.py run --quiet  pareil, sans envoyer de notification
  python3 prono.py backtest     rejoue la saison dernière pour vérifier ce que vaut le modèle
  python3 prono.py test-notif   envoie une notification de test sur ton téléphone
  python3 prono.py install      lance « run » toutes les heures sur ce Mac (tâche launchd)
  python3 prono.py uninstall    retire cette tâche
"""
import json
import os
import plistlib
import secrets
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import data  # noqa: E402

CONFIG = os.path.join(data.ROOT, "config.json")
# Les infos privées (canal de notifs, Telegram, adresse de l'appli) ne vont jamais dans le dépôt public.
SECRETS = os.path.join(data.ROOT, "secrets.json")
SECRET_ENV = {"ntfy_topic": "NTFY_TOPIC", "telegram_token": "TELEGRAM_TOKEN", "telegram_chat_id": "TELEGRAM_CHAT_ID"}
LABEL = "com.contrepied.prono"
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def install():
    if "scratch-workspaces" in data.ROOT:
        sys.exit("Ce dossier est temporaire : déplace d'abord l'appli dans un dossier à toi, puis relance install.")
    log = os.path.join(data.ROOT, "data", "run.log")
    spec = {"Label": LABEL, "ProgramArguments": [sys.executable, os.path.abspath(__file__), "run"],
            "WorkingDirectory": data.ROOT, "StartInterval": 3600, "RunAtLoad": True,
            "StandardOutPath": log, "StandardErrorPath": log}
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "wb") as fh:
        plistlib.dump(spec, fh)
    target = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{target}/{LABEL}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", target, PLIST], check=True)
    print(f"Tâche installée : Contre-Pied tourne toutes les heures tant que le Mac est allumé (journal : {log}).")


def uninstall():
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    if os.path.exists(PLIST):
        os.remove(PLIST)
    print("Tâche retirée.")


def _write_json(path: str, obj: dict):
    with open(path, "w") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def load_config() -> dict:
    """config.json (public) + secrets.json ou variables d'environnement (privés, ex. secrets GitHub)."""
    with open(CONFIG) as fh:
        cfg = json.load(fh)
    sec = {}
    if os.path.exists(SECRETS):
        with open(SECRETS) as fh:
            sec = json.load(fh)
    notify_cfg = cfg["notify"]
    moved = {k: notify_cfg[k] for k in SECRET_ENV if notify_cfg.get(k) and not sec.get(k)}
    if moved:  # ancienne config : le canal était rangé dans config.json
        sec.update(moved)
        _write_json(SECRETS, sec)
        _write_json(CONFIG, dict(cfg, notify=dict(notify_cfg, **dict.fromkeys(moved, ""))))
    for key, env in SECRET_ENV.items():
        notify_cfg[key] = os.environ.get(env) or sec.get(key) or ""
    cfg["public_url"] = os.environ.get("PUBLIC_URL") or sec.get("public_url") or ""
    if not notify_cfg["ntfy_topic"] and not os.environ.get("CI"):
        # Nom de canal impossible à deviner : c'est lui qui protège tes notifs.
        sec["ntfy_topic"] = notify_cfg["ntfy_topic"] = "contre-pied-" + secrets.token_hex(6)
        _write_json(SECRETS, sec)
    return cfg


def pct(x):
    return "—" if x is None else f"{x * 100:+.1f} %"


def print_backtest(r: dict):
    print(f"\n=== Backtest — critères mesurés sur {r['calibration_season']}, pronos joués sur {r['season']}"
          f" ({r['matches']} matchs) ===")
    print("\nValue bets classiques 1N2 et +/-2,5 selon le poids du modèle face au marché :")
    for a, v in r["value_bets"].items():
        print(f"  modèle {float(a) * 100:>3.0f} % | logloss 1N2 {v['logloss_1x2']:.4f}  +/-2,5 {v['logloss_ou']:.4f}"
              f" | paris {v['bets']:>4}  ROI {pct(v['roi'])}  CLV {pct(v['clv'])}")
    print("\nCatégories :")
    for k, v in r["categories"].items():
        if v["n"]:
            print(f"  {k:<26} n={v['n']:>4}  réussite {v['hit'] * 100:5.1f} % (prévu {v['expected_hit'] * 100:5.1f} %)"
                  f"  ROI {pct(v['roi'])} sur {v['priced']} cotés")
    print("\nCombinés :")
    for k, v in r["combos"].items():
        print(f"  {k:<18} joués {v['n']:>3}  passés {v['won']:>2} (prévu {v['expected_won']:.1f})"
              f"  1 chance sur {v['avg_one_in']:.0f} en moyenne")
    print(f"\nCritères validés sur {r['calibration_season']} : {', '.join(r['validated_on_calibration']) or 'aucun'}")
    print("Critères sur les deux saisons (lift = ce que le critère apporte en plus du modèle) :")
    for k, v in sorted(r["tags"].items(), key=lambda kv: -kv[1]["lift"]):
        print(f"  {k:<22} n={v['n']:>5}  réussite {v['hit'] * 100:5.1f} %  prévu {v['expected_hit'] * 100:5.1f} %"
              f"  lift {v['lift'] * 100:+5.1f} pts  ROI {pct(v['roi'])} ({v['priced']})")
    t = r.get("tennis")
    if t:
        print(f"\n=== Tennis — modèle calé sur {t['calibration_season']}, pronos joués sur {t['season']}"
              f" ({t['matches']} matchs) ===")
        print(f"  poids Elo {t['coef'][0]:.2f}, poids classement {t['coef'][1]:.2f} | logloss modèle "
              f"{t['logloss_model']:.4f}, marché {t['logloss_market']:.4f} | vainqueur à la cote moyenne : "
              f"{t['value_bets']['bets']} paris, ROI {pct(t['value_bets']['roi'])}")
        for k, v in t["categories"].items():
            if v["n"]:
                print(f"  {k:<14} n={v['n']:>4}  réussite {v['hit'] * 100:5.1f} % (prévu {v['expected_hit'] * 100:5.1f} %)")
        for k, v in t["combos"].items():
            print(f"  {k:<18} joués {v['n']:>3}  passés {v['won']:>2} (prévu {v['expected_won']:.1f})")
        print(f"  Critères validés sur {t['calibration_season']} : {', '.join(t['validated_on_calibration']) or 'aucun'}")
        for k, v in sorted(t["tags"].items(), key=lambda kv: -kv[1]["lift"]):
            print(f"  {k:<20} n={v['n']:>5}  réussite {v['hit'] * 100:5.1f} %  prévu {v['expected_hit'] * 100:5.1f} %"
                  f"  lift {v['lift'] * 100:+5.1f} pts")
    n = r["naive00"]
    if n["n"]:
        print(f"\nTon exemple (2 équipes en panne / matchs fermés) : {n['n']} matchs, 0-0 réel {n['nil_nil'] / n['n'] * 100:.1f} %"
              f" (prévu {n['p00'] / n['n'] * 100:.1f} %), nuls {n['draws'] / n['n'] * 100:.1f} %"
              f" ; « Piège à 0-0 » : {n['piege_n']} matchs, +1,5 buts {n['piege_o15'] / max(n['piege_n'], 1) * 100:.0f} %")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "run"
    cfg = load_config()
    if cmd == "backtest":
        from engine import backtest
        print_backtest(backtest.run(cfg))
    elif cmd == "run":
        from engine import app
        app.run(cfg, send_notifs="--quiet" not in argv)
    elif cmd == "test-notif":
        from engine import notify
        notify.send(cfg, "Contre-Pied est branché ⚽", "Les alertes arriveront ici dès qu'une cote vaut le coup.",
                    tags=["soccer"])
        print(f"Notification envoyée sur le canal ntfy « {cfg['notify']['ntfy_topic']} ».")
    elif cmd == "install":
        install()
    elif cmd == "uninstall":
        uninstall()
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
