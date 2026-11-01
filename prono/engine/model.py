"""Modèle de buts : notes attaque/défense pondérées dans le temps, correction Dixon-Coles.

La « performance » d'une équipe sur un match mélange buts réels et xG : les xG prédisent mieux
la suite que les buts, et c'est ce qui permet de repérer les séries en trompe-l'œil.
"""
from __future__ import annotations

import math
from collections import defaultdict

NEW_TEAM = (0.85, 1.15)  # note par défaut d'une équipe jamais vue (attaque, défense)
RHO = -0.08              # correction Dixon-Coles des petits scores (0-0, 1-1 un peu plus fréquents)


def decay(age_days: float, half_life: float) -> float:
    return 0.5 ** (age_days / half_life)


class Ratings:
    def __init__(self, base=1.3, home=1.15, att=None, dfn=None):
        self.base, self.home = base, home
        self.att, self.dfn = att or {}, dfn or {}

    def expect(self, h: str, a: str):
        ah, dh = self.att.get(h, NEW_TEAM[0]), self.dfn.get(h, NEW_TEAM[1])
        aa, da = self.att.get(a, NEW_TEAM[0]), self.dfn.get(a, NEW_TEAM[1])
        return self.base * self.home * ah * da, self.base * aa * dh


def fit_ratings(rows: list, prior: float = 4.0, iters: int = 30) -> Ratings:
    """rows : (poids, domicile, extérieur, valeur_dom, valeur_ext). Modèle multiplicatif de Maher.

    `prior` ajoute à chaque équipe ce nombre de matchs « moyens » fictifs, pour éviter
    les notes extrêmes quand une équipe a peu de matchs.
    """
    if not rows:
        return Ratings()
    teams = {t for r in rows for t in (r[1], r[2])}
    att = dict.fromkeys(teams, 1.0)
    dfn = dict.fromkeys(teams, 1.0)
    tw = sum(r[0] for r in rows)
    base = sum(r[0] * (r[3] + r[4]) for r in rows) / (2 * tw)
    home = 1.0
    for _ in range(iters):
        num, den = defaultdict(float), defaultdict(float)
        for w, h, a, vh, va in rows:
            num[h] += w * vh
            den[h] += w * base * home * dfn[a]
            num[a] += w * va
            den[a] += w * base * dfn[h]
        for t in teams:
            att[t] = (num[t] + prior * base) / (den[t] + prior * base)
        num, den = defaultdict(float), defaultdict(float)
        for w, h, a, vh, va in rows:
            num[a] += w * vh
            den[a] += w * base * home * att[h]
            num[h] += w * va
            den[h] += w * base * att[a]
        for t in teams:
            dfn[t] = (num[t] + prior * base) / (den[t] + prior * base)
        ga = math.exp(sum(math.log(v) for v in att.values()) / len(att))
        gd = math.exp(sum(math.log(v) for v in dfn.values()) / len(dfn))
        for t in teams:
            att[t] /= ga
            dfn[t] /= gd
        base *= ga * gd
        home = (sum(w * vh for w, h, a, vh, va in rows)
                / sum(w * base * att[h] * dfn[a] for w, h, a, vh, va in rows))
        base = (sum(w * (vh + va) for w, h, a, vh, va in rows)
                / sum(w * (home * att[h] * dfn[a] + att[a] * dfn[h]) for w, h, a, vh, va in rows))
    return Ratings(base, home, att, dfn)


def xg_of(m: dict, side: str, conv: dict):
    """xG réel si dispo, sinon estimé à partir des tirs cadrés (taux de conversion de la division)."""
    x = m["hxg" if side == "h" else "axg"]
    if x is not None:
        return x
    sot = m["hst" if side == "h" else "ast"]
    return conv.get(m["div"], 0.3) * sot if sot is not None else None


def performance(m: dict, side: str, conv: dict, w_xg: float) -> float:
    g = m["hg" if side == "h" else "ag"]
    x = xg_of(m, side, conv)
    return g if x is None else (1 - w_xg) * g + w_xg * x


def conversion_rates(results: list) -> dict:
    goals, sot = defaultdict(float), defaultdict(float)
    for m in results:
        if m["hst"] is not None and m["ast"] is not None:
            goals[m["div"]] += m["hg"] + m["ag"]
            sot[m["div"]] += m["hst"] + m["ast"]
    return {d: goals[d] / sot[d] for d in sot if sot[d] > 50}


class Models:
    """Tout ce qu'on apprend de l'historique à une date donnée."""

    def __init__(self, results: list, ref_ko, cfg: dict):
        hl, w_xg = cfg["half_life_days"], cfg["xg_weight"]
        past = [m for m in results if m["ko"] < ref_ko]
        self.conv = conversion_rates(past)
        weighted = []
        for m in past:
            w = decay((ref_ko - m["ko"]).total_seconds() / 86400, hl)
            if w > 0.03:
                weighted.append((w, m))
        self.goals = fit_ratings([(w, m["home"], m["away"], performance(m, "h", self.conv, w_xg),
                                   performance(m, "a", self.conv, w_xg)) for w, m in weighted])
        self.shots = fit_ratings([(w, m["home"], m["away"], m["hs"], m["as"])
                                  for w, m in weighted if m["hs"] is not None and m["as"] is not None], prior=6)
        self.sot = fit_ratings([(w, m["home"], m["away"], m["hst"], m["ast"])
                                for w, m in weighted if m["hst"] is not None and m["ast"] is not None], prior=6)
        self.corners = fit_ratings([(w, m["home"], m["away"], m["hc"], m["ac"])
                                    for w, m in weighted if m["hc"] is not None and m["ac"] is not None], prior=6)
        cards = [(w, m) for w, m in weighted if m["hy"] is not None and m["ay"] is not None]
        self.cards = fit_ratings([(w, m["home"], m["away"], m["hy"] + (m["hr"] or 0), m["ay"] + (m["ar"] or 0))
                                  for w, m in cards], prior=6)
        self.ref_factor = self._referees(cards, cfg.get("ref_prior_matches", 6))
        self.home_fx = self._home_effects(weighted, w_xg)

    def _referees(self, cards: list, prior: float) -> dict:
        act, pred = defaultdict(float), defaultdict(float)
        for w, m in cards:
            if not m["ref"]:
                continue
            lh, la = self.cards.expect(m["home"], m["away"])
            act[m["ref"]] += w * (m["hy"] + m["ay"] + (m["hr"] or 0) + (m["ar"] or 0))
            pred[m["ref"]] += w * (lh + la)
        k = prior * 4.2  # matchs moyens fictifs
        return {r: (act[r] + k) / (pred[r] + k) for r in pred}

    def _home_effects(self, weighted: list, w_xg: float) -> dict:
        """Écart entre le niveau d'une équipe à domicile et à l'extérieur, au-delà de l'avantage moyen."""
        s = defaultdict(lambda: [0.0] * 8)
        for w, m in weighted:
            lh, la = self.goals.expect(m["home"], m["away"])
            vh, va = performance(m, "h", self.conv, w_xg), performance(m, "a", self.conv, w_xg)
            H, A = s[m["home"]], s[m["away"]]
            H[0] += w * vh; H[1] += w * lh; H[2] += w * va; H[3] += w * la   # attaque/défense à domicile
            A[4] += w * va; A[5] += w * la; A[6] += w * vh; A[7] += w * lh   # attaque/défense à l'extérieur
        k = 8 * 1.3
        out = {}
        for t, v in s.items():
            att_h, def_h = (v[0] + k) / (v[1] + k), (v[2] + k) / (v[3] + k)
            att_a, def_a = (v[4] + k) / (v[5] + k), (v[6] + k) / (v[7] + k)
            fa = min(1.1, max(0.9, math.sqrt(att_h / att_a)))
            fd = min(1.1, max(0.9, math.sqrt(def_h / def_a)))
            out[t] = (fa, fd)
        return out


# ---------- Probabilités de score ----------

def poisson_pmf(lam: float, kmax: int) -> list:
    p = [math.exp(-lam)]
    for k in range(1, kmax + 1):
        p.append(p[-1] * lam / k)
    return p


def score_matrix(lh: float, la: float, rho: float = RHO, kmax: int = 10) -> list:
    ph, pa = poisson_pmf(lh, kmax), poisson_pmf(la, kmax)
    M = [[ph[i] * pa[j] for j in range(kmax + 1)] for i in range(kmax + 1)]
    M[0][0] *= max(0.0, 1 - lh * la * rho)
    M[0][1] *= max(0.0, 1 + lh * rho)
    M[1][0] *= max(0.0, 1 + la * rho)
    M[1][1] *= max(0.0, 1 - rho)
    s = sum(map(sum, M))
    return [[v / s for v in row] for row in M]


def markets(M: list) -> dict:
    n = len(M)
    p1 = sum(M[i][j] for i in range(n) for j in range(i))
    p2 = sum(M[i][j] for i in range(n) for j in range(i + 1, n))
    pn = 1 - p1 - p2
    tot = defaultdict(float)
    for i in range(n):
        for j in range(n):
            tot[i + j] += M[i][j]
    under = lambda line: sum(v for g, v in tot.items() if g < line)
    h0 = sum(M[0][j] for j in range(n))
    a0 = sum(M[i][0] for i in range(n))
    btts = 1 - h0 - a0 + M[0][0]
    scores = sorted(((M[i][j], f"{i}-{j}") for i in range(6) for j in range(6)), reverse=True)
    return {
        "1": p1, "N": pn, "2": p2, "1N": p1 + pn, "N2": pn + p2, "12": p1 + p2,
        "o15": 1 - under(1.5), "u15": under(1.5), "o25": 1 - under(2.5), "u25": under(2.5),
        "o35": 1 - under(3.5), "u35": under(3.5), "btts": btts, "nobtts": 1 - btts,
        "h_scores": 1 - h0, "a_scores": 1 - a0, "h_cs": a0, "a_cs": h0,
        "scores": [(s, p) for p, s in scores[:6]],
    }


def _quick(lh: float, la: float):
    p1 = p2 = under = 0.0
    for i, row in enumerate(score_matrix(lh, la, kmax=8)):
        for j, v in enumerate(row):
            if i > j:
                p1 += v
            elif j > i:
                p2 += v
            if i + j <= 2:
                under += v
    return p1, p2, 1 - under


def fit_lambdas(t1: float, t2: float, to25=None, start=(1.4, 1.1)):
    """Buts attendus (dom, ext) qui reproduisent les probabilités visées (1, 2, +2,5)."""
    def resid(x):
        p1, p2, po = _quick(*x)
        r = [p1 - t1, p2 - t2]
        if to25 is not None:
            r.append(po - to25)
        return r

    x = [min(5.0, max(0.1, start[0])), min(5.0, max(0.1, start[1]))]
    for _ in range(20):
        r = resid(x)
        if sum(v * v for v in r) < 1e-9:
            break
        J = []
        for k in range(2):
            xp = x[:]
            xp[k] += 1e-4
            rp = resid(xp)
            J.append([(rp[i] - r[i]) / 1e-4 for i in range(len(r))])
        a11 = sum(v * v for v in J[0]) + 1e-6
        a22 = sum(v * v for v in J[1]) + 1e-6
        a12 = sum(J[0][i] * J[1][i] for i in range(len(r)))
        g1 = sum(J[0][i] * r[i] for i in range(len(r)))
        g2 = sum(J[1][i] * r[i] for i in range(len(r)))
        det = a11 * a22 - a12 * a12
        if abs(det) < 1e-12:
            break
        d1 = -(a22 * g1 - a12 * g2) / det
        d2 = -(a11 * g2 - a12 * g1) / det
        x = [min(6.0, max(0.05, x[0] + max(-0.5, min(0.5, d1)))),
             min(6.0, max(0.05, x[1] + max(-0.5, min(0.5, d2))))]
    return x[0], x[1]


def over_prob(mu: float, line: float, phi: float = 1.3) -> float:
    """P(total > line) pour une loi binomiale négative de moyenne mu (variance = phi * mu)."""
    kmax = int(math.floor(line))
    if phi <= 1.0001:
        return 1 - sum(poisson_pmf(mu, kmax))
    r, p = mu / (phi - 1), 1 / phi
    cdf = 0.0
    for k in range(kmax + 1):
        cdf += math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                        + r * math.log(p) + k * math.log(1 - p))
    return max(0.0, min(1.0, 1 - cdf))


def devig(odds: list) -> list:
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [v / s for v in inv]
