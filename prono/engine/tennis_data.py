"""Données tennis : historique ATP/WTA avec scores et cotes (tennis-data.co.uk), matchs de la semaine (ESPN)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

from .data import PARIS, ROOT, cached_file

# tennis-data.co.uk filtre les serveurs (dont GitHub) : ses fichiers sont gardés dans le dépôt,
# rafraîchis depuis le Mac par « prono.py sync-tennis ».
TENNIS_DIR = os.path.join(ROOT, "data", "tennis")
TD_BASE = "http://www.tennis-data.co.uk"
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
EXCEL_EPOCH = dt.date(1899, 12, 30)


def read_xlsx(path: str) -> list:
    """Première feuille d'un .xlsx en liste de dicts (en-têtes de la première ligne), sans dépendance."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
    header, rows = None, []
    for r in ET.fromstring(z.read(sheet)).iter(NS + "row"):
        row = {}
        for c in r.iter(NS + "c"):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            v, t = c.find(NS + "v"), c.get("t")
            if t == "inlineStr":
                row[col] = "".join(x.text or "" for x in c.iter(NS + "t"))
            elif v is not None:
                row[col] = shared[int(v.text)] if t == "s" else v.text
        if header is None:
            header = row
        else:
            rows.append({header[k]: v for k, v in row.items() if k in header})
    return rows


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _pair(r: dict, a: str, b: str):
    x, y = _num(r.get(a)), _num(r.get(b))
    return [x, y] if x and y and x > 1 and y > 1 else None


def _links() -> dict:
    """Le site range ses fichiers derrière un chemin qui change : on le relit sur la page de téléchargement."""
    path = cached_file("tennis_alldata.html", f"{TD_BASE}/alldata.php", 24 * 7, TENNIS_DIR)
    if not path:
        raise RuntimeError("tennis-data.co.uk injoignable et aucune copie locale")
    with open(path, encoding="latin-1") as fh:
        html = fh.read()
    return {m.group(2): m.group(1) for m in re.finditer(r'href="([^"]*/(\d{4}w?)/\d{4}\.xlsx?)"', html, re.I)}


def load_history(years, refresh_h: float = 12) -> list:
    """Matchs ATP et WTA des années demandées, triés par date."""
    links = _links()
    this_year = dt.date.today().year
    out = []
    for year in years:
        for tour, suffix in (("ATP", ""), ("WTA", "w")):
            key = f"{year}{suffix}"
            if key not in links or not links[key].endswith("xlsx"):
                continue
            age = refresh_h if year == this_year else 24 * 365
            path = cached_file(f"tennis_{key}.xlsx", f"{TD_BASE}/{links[key]}", age, TENNIS_DIR)
            if path:
                out += [m for m in (_row(r, tour) for r in read_xlsx(path)) if m]
    out.sort(key=lambda m: m["date"])
    return out


def _row(r: dict, tour: str):
    w, l = (r.get("Winner") or "").strip(), (r.get("Loser") or "").strip()
    d = _num(r.get("Date"))
    if not w or not l or d is None:
        return None
    sets = []
    for i in range(1, 6):
        a, b = _num(r.get(f"W{i}")), _num(r.get(f"L{i}"))
        if a is None or b is None:
            break
        sets.append((int(a), int(b)))
    return {
        "tour": tour, "date": EXCEL_EPOCH + dt.timedelta(days=int(d)), "tournament": (r.get("Tournament") or "").strip(),
        "location": (r.get("Location") or "").strip(), "court": (r.get("Court") or "").strip(),
        "surface": (r.get("Surface") or "").strip(), "round": (r.get("Round") or "").strip(),
        "best_of": int(_num(r.get("Best of")) or 3), "winner": w, "loser": l,
        "wrank": _num(r.get("WRank")), "lrank": _num(r.get("LRank")), "sets": sets,
        "comment": (r.get("Comment") or "").strip(),
        "odds": {"avg": _pair(r, "AvgW", "AvgL"), "max": _pair(r, "MaxW", "MaxL"),
                 "sharp": _pair(r, "PSW", "PSL") or _pair(r, "BFEW", "BFEL")},
    }


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z ]", " ", s).split())


class NameIndex:
    """Relie « Carlos Alcaraz » (ESPN) à « Alcaraz C. » (tennis-data)."""

    def __init__(self, names_recent_first):
        self.idx = {}
        for n in names_recent_first:
            parts = n.split()
            if len(parts) < 2:
                continue
            # « Cerundolo J.M. » : le dernier bloc porte les initiales du prénom.
            surname, abbr = norm(" ".join(parts[:-1])), norm(parts[-1]).replace(" ", "")
            if surname and abbr:
                self.idx.setdefault((surname, abbr[0]), []).append((abbr, n))

    def find(self, full: str):
        t = norm(full).split()
        for k in range(1, len(t)):
            for surname, first in ((" ".join(t[k:]), t[0]), (" ".join(t[:k]), t[k])):
                cands = self.idx.get((surname, first[0]))
                if cands:
                    return next((n for abbr, n in cands if first.startswith(abbr)), cands[0][1])
        return None


def load_espn(tour: str, refresh_h: float = 0.5) -> list:
    """Matchs de simple de la semaine (à venir, en cours, terminés)."""
    path = cached_file(f"espn_{tour}.json", ESPN_URL.format(tour=tour), refresh_h)
    if not path:
        return []
    with open(path) as fh:
        d = json.load(fh)
    out = []
    for e in d.get("events", []):
        city = ((e.get("venue") or {}).get("displayName") or "").split(",")[0].strip()
        for g in e.get("groupings", []):
            if "Singles" not in (g.get("grouping") or {}).get("displayName", ""):
                continue
            for c in g.get("competitions", []):
                comps = c.get("competitors", [])
                names = [(x.get("athlete") or {}).get("displayName") for x in comps]
                if len(comps) != 2 or not all(names) or "TBD" in names:
                    continue
                st = (c.get("status") or {}).get("type") or {}
                rnd = (c.get("round") or {}).get("displayName", "")
                games = [[l.get("value") for l in x.get("linescores", [])] for x in comps]
                ko = dt.datetime.fromisoformat(c["date"].replace("Z", "+00:00")).astimezone(PARIS)
                time_valid = c.get("timeValid", True) is not False
                if not time_valid:  # programme pas encore publié : le match reste visible jusqu'au soir
                    ko = dt.datetime.combine(ko.date(), dt.time(20, 0), tzinfo=PARIS)
                out.append({
                    "id": f"tn-{c['id']}", "tour": tour.upper(), "event": e.get("name", ""), "city": city,
                    "round": rnd, "qualifying": "Qualifying" in rnd, "time_tbc": not time_valid,
                    "ko": ko,
                    "p1": names[0], "p2": names[1], "state": st.get("state"), "status": st.get("description", ""),
                    "winner": 1 if comps[0].get("winner") else 2 if comps[1].get("winner") else None,
                    "sets": [(int(a), int(b)) for a, b in zip(*games) if a is not None and b is not None],
                })
    return out
