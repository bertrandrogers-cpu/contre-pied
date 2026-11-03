"""Coupes d'Europe (Ligue des champions, Ligue Europa, Ligue Conférence) : calendrier et cotes ESPN.

Nos notes d'équipes sont calculées championnat par championnat : elles ne disent pas si un club turc vaut
un club anglais. Pour les coupes, la base est donc la cote du marché (DraftKings, via ESPN), débarrassée de
sa marge. Nos critères (séries, fausse panne, chatte…) s'y ajoutent quand on connaît le club par son championnat.
"""
from __future__ import annotations

import datetime as dt
import json

from . import model, picks
from .data import PARIS, cached_file, slug
from .tennis_data import norm

CUPS = {"UCL": ("uefa.champions", "Ligue des champions"), "UEL": ("uefa.europa", "Ligue Europa"),
        "UECL": ("uefa.europa.conf", "Ligue Conférence")}
# ESPN accepte un jour ou un mois entier (AAAAMM), pas une période : on demande le ou les mois concernés.
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={month}"
# Noms ESPN → noms de nos championnats, quand la ressemblance ne suffit pas.
ALIASES = {
    "atletico madrid": "Ath Madrid", "paris saint germain": "Paris SG", "internazionale": "Inter",
    "inter milan": "Inter", "as roma": "Roma", "ac milan": "Milan", "manchester united": "Man United",
    "manchester city": "Man City", "sporting cp": "Sp Lisbon", "braga": "Sp Braga", "sc braga": "Sp Braga",
    "olympiacos": "Olympiakos", "stade rennais": "Rennes", "feyenoord rotterdam": "Feyenoord",
    "psv eindhoven": "PSV Eindhoven", "psv": "PSV Eindhoven", "az alkmaar": "AZ Alkmaar",
    "tottenham hotspur": "Tottenham", "newcastle united": "Newcastle", "nottingham forest": "Nott'm Forest",
    "west ham united": "West Ham", "wolverhampton wanderers": "Wolves", "bayer leverkusen": "Leverkusen",
    "borussia dortmund": "Dortmund", "eintracht frankfurt": "Ein Frankfurt", "borussia monchengladbach": "M'gladbach",
    "olympique lyonnais": "Lyon", "olympique de marseille": "Marseille", "real betis": "Betis",
    "real sociedad": "Sociedad", "athletic club": "Ath Bilbao", "celta vigo": "Celta", "fc porto": "Porto",
    "sl benfica": "Benfica", "union st gilloise": "St. Gilloise", "union saint gilloise": "St. Gilloise",
    "ajax amsterdam": "Ajax", "heart of midlothian": "Hearts", "paok salonika": "PAOK", "aek athens": "AEK",
    "bayern munich": "Bayern Munich", "rb leipzig": "RB Leipzig", "vfb stuttgart": "Stuttgart",
}
NOISE = {"fc", "cf", "sc", "ac", "as", "afc", "sk", "fk", "bk", "cd", "ud", "sv", "vfb", "vfl", "tsg", "rc", "club",
         "de", "sl", "cp", "ssc", "if", "ff", "1", "1899", "1909", "04", "05"}


class _Flat:
    """Notes « neutres » : les buts attendus viennent des cotes, pas de nos championnats."""

    def __init__(self, lam=None):
        self.att = {"marché": 1.0} if lam else {}
        self._lam = lam or (0.0, 0.0)

    def expect(self, h, a):
        return self._lam


class CupModels:
    def __init__(self, lam):
        self.goals, self.shots, self.sot = _Flat(lam), _Flat(), _Flat()
        self.home_fx, self.ref_factor, self.conv = {}, {}, {}


def _key(name: str) -> str:
    return " ".join(t for t in norm(name).split() if t not in NOISE)


class TeamIndex:
    def __init__(self, names):
        self.exact = {_key(n): n for n in names}

    def find(self, espn_name: str):
        n = norm(espn_name)
        if n in ALIASES:
            return ALIASES[n]
        k = _key(espn_name)
        if k in self.exact:
            return self.exact[k]
        hits = {v for kk, v in self.exact.items() if kk and (f" {kk} " in f" {k} " or f" {k} " in f" {kk} ")}
        return hits.pop() if len(hits) == 1 else None


def american(s) -> float:
    v = float(str(s).replace("+", ""))
    return 1 + v / 100 if v > 0 else 1 + 100 / abs(v)


def _price(side: dict):
    for when in ("current", "close", "open"):
        o = (side or {}).get(when) or {}
        if o.get("odds") not in (None, "", "OFF"):
            return o
    return None


def _odds(c: dict):
    """Cotes 1N2 décimales et ligne de buts (ligne, cote plus, cote moins), ou None."""
    o = (c.get("odds") or [None])[0]
    if not o:
        return None, None
    ml = o.get("moneyline") or {}
    prices = [_price(ml.get(k)) for k in ("home", "draw", "away")]
    if not all(prices):
        return None, None
    try:
        x12 = [american(p["odds"]) for p in prices]
    except ValueError:
        return None, None
    tot = o.get("total") or {}
    over, under = _price(tot.get("over")), _price(tot.get("under"))
    total = None
    if over and under and over.get("line"):
        try:
            total = (float(over["line"].lstrip("ou")), american(over["odds"]), american(under["odds"]))
        except ValueError:
            total = None
    return x12, total


def live(cfg: dict, now: dt.datetime, hist: dict, names, log=print):
    """Analyses des matchs de coupe à venir (avec cotes) et résultats des matchs joués, pour le suivi."""
    index = TeamIndex(names)
    start, end = (now - dt.timedelta(days=3)).date(), (now + dt.timedelta(days=cfg["horizon_days"])).date()
    horizon = now + dt.timedelta(days=cfg["horizon_days"])
    analyses, results, skipped = [], [], 0
    months = sorted({f"{d:%Y%m}" for d in (start, end)})
    for div, (espn, title) in CUPS.items():
        events = {}
        for month in months:
            path = cached_file(f"espn_{espn}_{month}.json", ESPN.format(slug=espn, month=month), 0.5)
            if path:
                with open(path) as fh:
                    events.update({e["id"]: e for e in json.load(fh).get("events", [])})
        for e in events.values():
            c = e["competitions"][0]
            teams = {t["homeAway"]: t for t in c["competitors"]}
            if set(teams) != {"home", "away"}:
                continue
            raw = {s: teams[s]["team"]["displayName"] for s in ("home", "away")}
            home, away = (index.find(raw[s]) or raw[s] for s in ("home", "away"))
            ko = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(PARIS)
            mid = f"{div}-{ko:%Y%m%d}-{slug(home)}-{slug(away)}"
            state = c["status"]["type"]["state"]
            if state == "post":
                try:
                    hg, ag = float(teams["home"]["score"]), float(teams["away"]["score"])
                except (KeyError, TypeError, ValueError):
                    continue
                results.append(dict(dict.fromkeys(("hs", "as", "hst", "ast", "hc", "ac", "hy", "ay", "hr", "ar")),
                                    id=mid, hg=hg, ag=ag))
                continue
            if state != "pre" or not now < ko <= horizon:
                continue
            x12, total = _odds(c)
            if not x12:
                skipped += 1
                continue
            p = model.devig(x12)
            line, p_over = 2.5, None
            if total:
                line, p_over = total[0], model.devig([total[1], total[2]])[0]
            lam = model.fit_lambdas(p[0], p[2], p_over, line=line)
            fx = {"div": div, "id": mid, "ko": ko, "home": home, "away": away, "ref": None,
                  "odds": {"avg": x12, "max": x12, "sharp": None, "ou_avg": None, "ou_max": None, "ou_sharp": None,
                           "c_avg": None, "c_ou_avg": None}}
            an = picks.analyse(fx, CupModels(lam), hist, cfg)
            an["league"] = title
            analyses.append(an)
    log(f"Coupes d'Europe : {len(analyses)} matchs à venir avec cotes ({skipped} sans cote, laissés de côté)")
    return analyses, results
