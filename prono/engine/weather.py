"""Météo au coup d'envoi (Open-Meteo, gratuit et sans clé)."""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse

from .data import CACHE_DIR, country_of, http_get

# Équipes dont le nom n'est pas celui de la ville.
CITY = {
    "Paris SG": "Paris", "Paris FC": "Paris", "St Etienne": "Saint-Étienne", "Clermont": "Clermont-Ferrand",
    "Red Star": "Saint-Ouen-sur-Seine", "Man City": "Manchester", "Man United": "Manchester",
    "Arsenal": "London", "Chelsea": "London", "Tottenham": "London", "West Ham": "London", "Fulham": "London",
    "Brentford": "London", "Crystal Palace": "London", "QPR": "London", "Millwall": "London",
    "Charlton": "London", "Wolves": "Wolverhampton", "Nott'm Forest": "Nottingham", "Aston Villa": "Birmingham",
    "West Brom": "West Bromwich", "Everton": "Liverpool", "Sheffield United": "Sheffield",
    "Sheffield Weds": "Sheffield", "Newcastle": "Newcastle upon Tyne", "Hull": "Kingston upon Hull",
    "Ath Madrid": "Madrid", "Real Madrid": "Madrid", "Vallecano": "Madrid", "Ath Bilbao": "Bilbao",
    "Sociedad": "San Sebastián", "Betis": "Sevilla", "Celta": "Vigo", "Espanol": "Barcelona",
    "Alaves": "Vitoria-Gasteiz", "Mallorca": "Palma", "Las Palmas": "Las Palmas de Gran Canaria",
    "Osasuna": "Pamplona", "Levante": "Valencia", "Sp Gijon": "Gijón", "La Coruna": "A Coruña",
    "Inter": "Milano", "Milan": "Milano", "Juventus": "Torino", "Roma": "Roma", "Lazio": "Roma",
    "Fiorentina": "Firenze", "Atalanta": "Bergamo", "Genoa": "Genova", "Sampdoria": "Genova",
    "Sassuolo": "Reggio Emilia", "Napoli": "Napoli", "Bayern Munich": "München", "Leverkusen": "Leverkusen",
    "RB Leipzig": "Leipzig", "Ein Frankfurt": "Frankfurt am Main", "M'gladbach": "Mönchengladbach",
    "Werder Bremen": "Bremen", "Union Berlin": "Berlin", "Hertha": "Berlin", "FC Koln": "Köln",
    "Hoffenheim": "Sinsheim", "Freiburg": "Freiburg im Breisgau", "Heidenheim": "Heidenheim an der Brenz",
    "St Pauli": "Hamburg", "Schalke 04": "Gelsenkirchen", "Fortuna Dusseldorf": "Düsseldorf",
}
GEO_FILE = os.path.join(CACHE_DIR, "geo.json")


def _load(path: str) -> dict:
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save(path: str, obj: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh)


def locate(team: str, div: str):
    geo = _load(GEO_FILE)
    key = f"{div}|{team}"
    if key in geo:
        return geo[key]
    name = CITY.get(team, team)
    q = urllib.parse.urlencode({"name": name, "count": 1, "language": "fr", "countryCode": country_of(div)})
    try:
        res = json.loads(http_get(f"https://geocoding-api.open-meteo.com/v1/search?{q}", timeout=15))
        hit = (res.get("results") or [None])[0]
        geo[key] = [hit["latitude"], hit["longitude"]] if hit else None
    except Exception:
        return None
    _save(GEO_FILE, geo)
    return geo[key]


def at_kickoff(team: str, div: str, ko: dt.datetime):
    """{'rain': mm/h, 'wind': km/h, 'temp': °C} à l'heure du match, ou None si trop loin / indisponible."""
    if not 0 <= (ko - dt.datetime.now(ko.tzinfo)).days <= 6:
        return None
    pos = locate(team, div)
    if not pos:
        return None
    q = urllib.parse.urlencode({"latitude": pos[0], "longitude": pos[1], "timezone": "Europe/Paris",
                                "hourly": "precipitation,wind_speed_10m,temperature_2m", "forecast_days": 7})
    try:
        res = json.loads(http_get(f"https://api.open-meteo.com/v1/forecast?{q}", timeout=15))
        hours = res["hourly"]
        i = hours["time"].index(ko.strftime("%Y-%m-%dT%H:00"))
        return {"rain": hours["precipitation"][i], "wind": hours["wind_speed_10m"][i],
                "temp": hours["temperature_2m"][i]}
    except Exception:
        return None
