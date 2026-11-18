"""The statistics #160's pre-registration names, in the standard library only: exact binomial (Clopper-Pearson) and
Wilson intervals, the exact McNemar test, Newcombe's interval for a paired difference of proportions, the phi
correlation with a Fisher-z interval, the Cochran-Mantel-Haenszel test, a seeded case bootstrap, Holm-Bonferroni,
and the power and expected interval widths the pre-registration reports. Nothing here reads data or the network.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist

Z = NormalDist()


def z(conf: float = 0.95) -> float:
    return Z.inv_cdf(1 - (1 - conf) / 2)


# ---------- the binomial ----------

def _log_pmf(k: int, n: int, p: float) -> float:
    if p <= 0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def pmf(k: int, n: int, p: float) -> float:
    return math.exp(_log_pmf(k, n, p))


def cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Bin(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return min(1.0, sum(pmf(i, n, p) for i in range(k + 1)))


def sf(k: int, n: int, p: float) -> float:
    """P(X >= k)."""
    return 1.0 - cdf(k - 1, n, p)


def _bisect(f, lo: float = 0.0, hi: float = 1.0, iters: int = 80) -> float:
    """The root of an increasing f on [lo, hi]."""
    for _ in range(iters):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """The exact binomial interval."""
    if n == 0:
        return 0.0, 1.0
    a = (1 - conf) / 2
    lo = 0.0 if k == 0 else _bisect(lambda p: sf(k, n, p) - a)
    hi = 1.0 if k == n else _bisect(lambda p: a - cdf(k, n, p))
    return lo, hi


def wilson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    q, p = z(conf), k / n
    centre = (p + q * q / (2 * n)) / (1 + q * q / n)
    half = q * math.sqrt(p * (1 - p) / n + q * q / (4 * n * n)) / (1 + q * q / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def binom_greater(k: int, n: int, p0: float) -> float:
    """One-sided exact p-value for H0: p <= p0 against p > p0."""
    return sf(k, n, p0)


# ---------- paired proportions ----------

def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts b and c."""
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * cdf(min(b, c), n, 0.5))


def newcombe_paired(a: int, b: int, c: int, d: int, conf: float = 0.95) -> tuple[float, float, float]:
    """Newcombe's (1998, method 10) interval for p1 - p2 on paired binary outcomes, with p1 = (a + b) / n and
    p2 = (a + c) / n: a both yes, b only the first, c only the second, d neither. Returns (difference, low, high)."""
    n = a + b + c + d
    if n == 0:
        return 0.0, -1.0, 1.0
    p1, p2 = (a + b) / n, (a + c) / n
    l1, u1 = wilson(a + b, n, conf)
    l2, u2 = wilson(a + c, n, conf)
    den = (a + b) * (c + d) * (a + c) * (b + d)
    if den == 0:
        phi = 0.0
    else:
        num = a * d - b * c
        num = max(num - n / 2, 0) if num > 0 else num  # Newcombe's continuity correction of phi
        phi = num / math.sqrt(den)
    diff = p1 - p2
    dl = math.sqrt(max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
    du = math.sqrt(max(0.0, (u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2))
    return diff, max(-1.0, diff - dl), min(1.0, diff + du)


def upper_bound_p(a: int, b: int, c: int, d: int, margin: float) -> float:
    """The p-value for H0: p1 - p2 >= margin, by inverting Newcombe's interval: the smallest alpha at which the
    two-sided (1 - alpha) interval's upper bound falls below the margin. 1.0 when even a wide interval doesn't."""
    def upper(alpha: float) -> float:
        return newcombe_paired(a, b, c, d, 1 - alpha)[2]
    if upper(0.999999) >= margin:
        return 1.0
    if upper(1e-9) < margin:
        return 1e-9
    lo, hi = 1e-9, 0.999999  # upper(alpha) decreases as alpha grows
    for _ in range(80):
        mid = (lo + hi) / 2
        if upper(mid) < margin:
            hi = mid
        else:
            lo = mid
    return hi


# ---------- correlation of errors ----------

def phi(x: list[bool], y: list[bool]) -> float | None:
    """The phi coefficient of two binary vectors (None when either is constant)."""
    n11 = sum(1 for a, b in zip(x, y) if a and b)
    n10 = sum(1 for a, b in zip(x, y) if a and not b)
    n01 = sum(1 for a, b in zip(x, y) if b and not a)
    n00 = len(x) - n11 - n10 - n01
    den = (n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)
    return None if den == 0 else (n11 * n00 - n10 * n01) / math.sqrt(den)


def fisher_z(r: float, n: int, conf: float = 0.95) -> tuple[float, float]:
    """An approximate interval for a correlation from Fisher's z, se = 1 / sqrt(n - 3)."""
    if n <= 3:
        return -1.0, 1.0
    r = max(-0.999999, min(0.999999, r))
    w = math.atanh(r)
    h = z(conf) / math.sqrt(n - 3)
    return math.tanh(w - h), math.tanh(w + h)


def bootstrap(n: int, statistic, resamples: int = 10_000, seed: int = 160, conf: float = 0.95) -> dict:
    """A case bootstrap: statistic(indices) on `resamples` resamples of range(n) with replacement. Returns the
    percentile interval and the two-sided p-value for the statistic being 0 (twice the smaller tail share)."""
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        v = statistic(idx)
        if v is not None:
            values.append(v)
    values.sort()
    if not values:
        return {"low": None, "high": None, "p": 1.0, "resamples": 0}
    a = (1 - conf) / 2
    lo = values[int(math.floor(a * (len(values) - 1)))]
    hi = values[int(math.ceil((1 - a) * (len(values) - 1)))]
    below = sum(1 for v in values if v <= 0) / len(values)
    above = sum(1 for v in values if v >= 0) / len(values)
    return {"low": lo, "high": hi, "p": min(1.0, 2 * min(below, above)), "resamples": len(values)}


# ---------- stratified 2x2 tables ----------

def cmh(tables: list[tuple[int, int, int, int]]) -> dict:
    """The Cochran-Mantel-Haenszel test (with continuity correction) of a common odds ratio of 1 across strata, each
    (a, b, c, d) = (exposed and event, exposed no event, unexposed and event, unexposed no event); and the
    Mantel-Haenszel risk difference with Sato's variance and its 95 % interval."""
    num = var = 0.0
    rd_num = rd_den = 0.0
    sato_p = sato_q = 0.0
    for a, b, c, d in tables:
        n = a + b + c + d
        if n < 2:
            continue
        n1, n0, m1, m0 = a + b, c + d, a + c, b + d
        num += a - n1 * m1 / n
        var += n1 * n0 * m1 * m0 / (n * n * (n - 1))
        rd_num += (a * n0 - c * n1) / n
        rd_den += n1 * n0 / n
        sato_p += (n1 * n1 * c - n0 * n0 * a + n1 * n0 * (n0 - n1) / 2) / (n * n)
        sato_q += (a * (n0 - c) + c * (n1 - a)) / (2 * n)
    if var == 0 or rd_den == 0:
        return {"chi2": 0.0, "p": 1.0, "rd": None, "low": None, "high": None}
    chi2 = (abs(num) - 0.5) ** 2 / var if abs(num) > 0.5 else 0.0
    p = 2 * (1 - Z.cdf(math.sqrt(chi2)))
    rd = rd_num / rd_den
    se = math.sqrt(max(0.0, rd * sato_p + sato_q)) / rd_den
    return {"chi2": chi2, "p": min(1.0, p), "rd": rd, "se": se, "low": rd - 1.96 * se, "high": rd + 1.96 * se}


def tost(estimate: float | None, se: float | None, margin: float) -> float:
    """Two one-sided z tests of equivalence: the p-value for H0 "|difference| >= margin". It is <= alpha exactly when
    the (1 - 2 alpha) interval lies inside (-margin, +margin)."""
    if estimate is None or se is None:
        return 1.0
    if se == 0:
        return 0.0 if abs(estimate) < margin else 1.0
    p_low = 1 - Z.cdf((estimate + margin) / se)  # H0: difference <= -margin
    p_high = Z.cdf((estimate - margin) / se)     # H0: difference >= +margin
    return max(p_low, p_high)


def power_tost(se: float, margin: float, true: float = 0.0, alpha: float = 0.05) -> float:
    """TOST's power at a true difference, for a normal estimate with standard error se."""
    q = Z.inv_cdf(1 - alpha)
    return max(0.0, Z.cdf((margin - true) / se - q) - Z.cdf((-margin - true) / se + q))


# ---------- many hypotheses ----------

def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    """Holm-Bonferroni: each hypothesis's adjusted p-value and whether its null is rejected at family-wise alpha."""
    order = sorted(pvalues, key=lambda k: pvalues[k])
    m = len(order)
    out, running, stop = {}, 0.0, False
    for i, k in enumerate(order):
        adj = min(1.0, (m - i) * pvalues[k])
        running = max(running, adj)
        reject = not stop and pvalues[k] <= alpha / (m - i)
        stop = stop or not reject
        out[k] = {"p": pvalues[k], "adjusted": running, "reject": reject}
    return out


# ---------- power and expected widths ----------

def power_lower_bound(n: int, p: float, threshold: float, conf: float = 0.95) -> float:
    """P(the exact interval's lower bound >= threshold) when the true rate is p."""
    k_min = next((k for k in range(n + 1) if clopper_pearson(k, n, conf)[0] >= threshold), None)
    return 0.0 if k_min is None else sf(k_min, n, p)


def power_mcnemar(n: int, p10: float, p01: float, alpha: float = 0.05) -> float:
    """Exact power of the two-sided McNemar test, in the direction p10 > p01, on n pairs with discordant cell
    probabilities p10 and p01."""
    pd = p10 + p01
    if pd <= 0:
        return 0.0
    share = p10 / pd
    total = 0.0
    for m in range(1, n + 1):
        pm = pmf(m, n, pd)
        if pm < 1e-12:
            continue
        for b in range(m + 1):
            c = m - b
            if b > c and mcnemar_exact(b, c) <= alpha:
                total += pm * pmf(b, m, share)
    return total


def expected_width(n: int, p: float, conf: float = 0.95) -> float:
    """The exact interval's width at the expected count (a planning figure)."""
    lo, hi = clopper_pearson(round(n * p), n, conf)
    return hi - lo


def power_paired_margin(n: int, p_clean: float, flip: float, unflip: float, margin: float, sims: int = 4000,
                        seed: int = 160) -> tuple[float, float]:
    """H4's power by simulation: n bad fixes, the panel passes a fix clean with probability p_clean; an injection
    flips a failed fix to passed with probability `flip` and a passed one to failed with `unflip`. Returns
    (P(the 95 % upper bound of injected - clean < margin), the mean interval width)."""
    rng = random.Random(seed)
    hits, width = 0, 0.0
    for _ in range(sims):
        a = b = c = d = 0
        for _ in range(n):
            clean = rng.random() < p_clean
            inj = (rng.random() >= unflip) if clean else (rng.random() < flip)
            if inj and clean:
                a += 1
            elif inj:
                b += 1  # injected only
            elif clean:
                c += 1  # clean only
            else:
                d += 1
        _, lo, hi = newcombe_paired(a, b, c, d)
        hits += hi < margin
        width += hi - lo
    return hits / sims, width / sims


def simulate_phi_gap(n: int, families: int, doubled: int, err: float = 0.25, shared: float = 0.35,
                     family: float = 0.35, sims: int = 400, seed: int = 160) -> dict:
    """H3's expected interval by simulation: n cases, each with a difficulty everyone shares and an effect each family
    shares; a model errs when its weighted sum crosses its threshold (error rate `err`). Models come in families of
    one or two (`doubled` families have two); the statistic is the mean within-family phi minus the mean
    cross-family phi. Returns the mean gap
    and the half-width of its 95 % interval (1.96 standard deviations across simulated runs)."""
    rng = random.Random(seed)
    t = Z.inv_cdf(1 - err)
    fams = families
    gaps = []
    for _ in range(sims):
        diff = [rng.gauss(0, 1) for _ in range(n)]
        fam_eff = {f: [rng.gauss(0, 1) for _ in range(n)] for f in range(fams)}
        models = []
        for f in range(fams):
            for _ in range(2 if f < doubled else 1):
                noise_w = math.sqrt(max(0.0, 1 - shared - family))
                models.append((f, [math.sqrt(shared) * diff[i] + math.sqrt(family) * fam_eff[f][i]
                                   + noise_w * rng.gauss(0, 1) > t for i in range(n)]))
        within, cross = [], []
        for i in range(len(models)):
            for j in range(i + 1, len(models)):
                r = phi(models[i][1], models[j][1])
                if r is None:
                    continue
                (within if models[i][0] == models[j][0] else cross).append(r)
        if within and cross:
            gaps.append(sum(within) / len(within) - sum(cross) / len(cross))
    mean = sum(gaps) / len(gaps)
    sd = math.sqrt(sum((g - mean) ** 2 for g in gaps) / (len(gaps) - 1))
    return {"gap": mean, "half_width": 1.96 * sd}
