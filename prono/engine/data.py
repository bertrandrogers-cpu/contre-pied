"""Téléchargement et lecture des données football-data.co.uk (résultats, xG, stats, cotes)."""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "cache")
BASE_URL = "https://www.football-data.co.uk"
UK = ZoneInfo("Europe/London")
PARIS = ZoneInfo("Europe/Paris")

LEAGUES = {
    "F1": "Ligue 1", "F2": "Ligue 2", "E0": "Premier League", "E1": "Championship", "E2": "League One",
    "E3": "League Two", "SP1": "Liga", "SP2": "Liga 2", "I1": "Serie A", "I2": "Serie B",
    "D1": "Bundesliga", "D2": "2. Bundesliga", "N1": "Eredivisie", "P1": "Liga Portugal",
    "B1": "Pro League", "T1": "Süper Lig", "SC0": "Premiership (Écosse)", "SC1": "Championship (Écosse)",
    "G1": "Super League (Grèce)",
    "AUT": "Bundesliga (Autriche)", "SWZ": "Super League (Suisse)", "DNK": "Superliga (Danemark)",
    "POL": "Ekstraklasa", "ROU": "Liga 1 (Roumanie)", "RUS": "Premier League (Russie)", "SWE": "Allsvenskan",
    "NOR": "Eliteserien", "FIN": "Veikkausliiga", "IRL": "Premier Division (Irlande)",
}
COUNTRY = {"F": "FR", "E": "GB", "SP": "ES", "I": "IT", "D": "DE", "N": "NL", "P": "PT",
           "B": "BE", "T": "TR", "SC": "GB", "G": "GR", "AUT": "AT", "SWZ": "CH", "DNK": "DK", "POL": "PL",
           "ROU": "RO", "RUS": "RU", "SWE": "SE", "NOR": "NO", "FIN": "FI", "IRL": "IE"}
# Championnats publiés dans un autre format (un fichier par pays, cotes de clôture, sans stats de tirs).
NEW_LEAGUES = {"AUT": "Austria", "SWZ": "Switzerland", "DNK": "Denmark", "POL": "Poland", "ROU": "Romania",
               "RUS": "Russia", "SWE": "Sweden", "NOR": "Norway", "FIN": "Finland", "IRL": "Ireland"}
CODE_OF_COUNTRY = {v: k for k, v in NEW_LEAGUES.items()}
# Une division est toujours modélisée avec ses voisines : les promus et relégués gardent une note.
FAMILIES = [["F1", "F2"], ["E0", "E1", "E2", "E3"], ["SP1", "SP2"], ["I1", "I2"], ["D1", "D2"], ["SC0", "SC1"]]


def family(div: str) -> list:
    for fam in FAMILIES:
        if div in fam:
            return fam
    return [div]


def country_of(div: str) -> str:
    return COUNTRY.get(re.sub(r"\d", "", div), "")


def http_get(url: str, timeout: int = 40) -> bytes:
    out = subprocess.run(["curl", "-sSL", "--fail", "-m", str(timeout), "-A", "prono-app/1.0", url],
                         capture_output=True, check=True)
    return out.stdout


def cached_file(name: str, url: str, max_age_h: float, folder: str = CACHE_DIR) -> str | None:
    """Renvoie le chemin du fichier en cache, retéléchargé s'il est plus vieux que max_age_h.

    Si le téléchargement échoue, on garde la dernière copie connue.
    """
    path = os.path.join(folder, name)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_h * 3600:
        return path
    os.makedirs(folder, exist_ok=True)
    try:
        data = http_get(url)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except subprocess.CalledProcessError as e:
        print(f"Téléchargement impossible ({url}) : {e.stderr.decode(errors='replace').strip()}", file=sys.stderr)
        if not os.path.exists(path):
            return None
    return path


def season_code(day: dt.date, back: int = 0) -> str:
    start = (day.year if day.month >= 7 else day.year - 1) - back
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def _num(row: dict, key: str):
    v = row.get(key)
    if v is None or not v.strip():
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _triple(row: dict, prefix: str):
    vals = [_num(row, prefix + s) for s in "HDA"]
    return vals if all(v and v > 1 for v in vals) else None


def _pair(row: dict, prefix: str):
    o, u = _num(row, prefix + ">2.5"), _num(row, prefix + "<2.5")
    return [o, u] if o and u and o > 1 and u > 1 else None


def _first(*vals):
    for v in vals:
        if v:
            return v
    return None


def _parse_date(s: str) -> dt.date | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse_csv(path: str) -> list:
    with open(path, "rb") as fh:
        text = fh.read().decode("utf-8-sig", errors="replace")
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        row = {(k or "").strip(): v for k, v in row.items()}
        # Deux formats : « HomeTeam/FTHG/Div » (grands championnats) et « Home/HG/Country » (les autres).
        home = (row.get("HomeTeam") or row.get("Home") or "").strip()
        away = (row.get("AwayTeam") or row.get("Away") or "").strip()
        div = (row.get("Div") or "").strip() or CODE_OF_COUNTRY.get((row.get("Country") or "").strip(), "")
        day = _parse_date(row.get("Date") or "")
        if not home or not away or not day or not div:
            continue
        hhmm = (row.get("Time") or "15:00").strip() or "15:00"
        try:
            t = dt.datetime.strptime(hhmm, "%H:%M").time()
        except ValueError:
            t = dt.time(15, 0)
        # Les horaires du fichier sont à l'heure anglaise.
        ko = dt.datetime.combine(day, t, tzinfo=UK).astimezone(PARIS)
        m = {
            "div": div, "date": day, "ko": ko, "home": home, "away": away,
            "id": f"{div}-{day:%Y%m%d}-{slug(home)}-{slug(away)}",
            # Pas de « ou » ici : un score de 0 est une vraie valeur, pas une case vide.
            "hg": _num(row, "FTHG" if "FTHG" in row else "HG"), "ag": _num(row, "FTAG" if "FTAG" in row else "AG"),
            "hxg": _num(row, "HxG"), "axg": _num(row, "AxG"),
            "hs": _num(row, "HS"), "as": _num(row, "AS"),
            "hst": _num(row, "HST"), "ast": _num(row, "AST"),
            "hc": _num(row, "HC"), "ac": _num(row, "AC"),
            "hy": _num(row, "HY"), "ay": _num(row, "AY"),
            "hr": _num(row, "HR"), "ar": _num(row, "AR"),
            "ref": (row.get("Referee") or "").strip() or None,
            "odds": {
                # Dans l'historique des « autres » championnats, seules les cotes de clôture existent.
                "avg": _first(_triple(row, "Avg"), _triple(row, "AvgC")),
                "max": _first(_triple(row, "Max"), _triple(row, "MaxC")),
                "sharp": _first(_triple(row, "BFE"), _triple(row, "PS"), _triple(row, "PSC"), _triple(row, "BFEC")),
                "ou_avg": _pair(row, "Avg"), "ou_max": _pair(row, "Max"),
                "ou_sharp": _first(_pair(row, "BFE"), _pair(row, "P")),
                "c_avg": _triple(row, "AvgC"), "c_ou_avg": _pair(row, "AvgC"),
            },
        }
        out.append(m)
    return out


def load_results(divs: list, seasons: list, refresh_h: float = 12) -> list:
    """Matchs joués des divisions/saisons demandées. Les saisons passées ne sont jamais retéléchargées."""
    current = season_code(dt.date.today())
    matches = []
    for season in seasons:
        for div in divs:
            if div in NEW_LEAGUES:
                continue
            age = refresh_h if season == current else 24 * 365
            path = cached_file(f"{season}_{div}.csv", f"{BASE_URL}/mmz4281/{season}/{div}.csv", age)
            if path:
                matches += [m for m in parse_csv(path) if m["hg"] is not None]
    # Format « un fichier par pays, toutes saisons » : on garde à partir du 1er janvier de la plus ancienne saison
    # (certains de ces championnats se jouent sur l'année civile).
    since = dt.date(2000 + int(min(seasons)[:2]), 1, 1)
    for div in divs:
        if div in NEW_LEAGUES:
            path = cached_file(f"new_{div}.csv", f"{BASE_URL}/new/{div}.csv", refresh_h)
            if path:
                matches += [m for m in parse_csv(path) if m["hg"] is not None and m["date"] >= since]
    matches.sort(key=lambda m: m["ko"])
    return matches


def load_fixtures(refresh_h: float = 3) -> list:
    out = []
    for name in ("fixtures.csv", "new_league_fixtures.csv"):
        path = cached_file(name, f"{BASE_URL}/{name}", refresh_h)
        if path:
            out += parse_csv(path)
    return out
