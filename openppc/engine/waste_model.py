"""Waste model: how sure can we be that a search term is bad, not just unlucky?

A fixed dollar threshold treats a term with 3 clicks and one with 300 the same way. This model
asks the account instead. Nobody knows a search term's true conversion rate, but the account's
own terms show how rates spread around the account average (an empirical-Bayes beta prior).
Each term's clicks and conversions then update that prior, and the answer is the probability
that the term truly converts at less than half the account's rate: P(bad).

With few clicks, P(bad) stays close to the account's baseline whatever the term cost. With
many clicks and no conversions it climbs toward 1. Adding up 1 - P(bad) over the flagged terms
says how many of the flags are probably bad luck.

Standard library only. The regularized incomplete beta function is the continued fraction in
Numerical Recipes (Press et al., 3rd edition, section 6.4).
"""
import math

BAD_RATIO = 0.5                 # "bad" means converting at less than this share of the account's rate
CONFIDENT = 0.9                 # flag a term once P(bad) reaches this
MIN_CONCENTRATION = 1.0         # the prior's strength (alpha + beta) stays in this range: the floor keeps
MAX_CONCENTRATION = 10_000.0    # the prior from saying most terms are bad before any click, the cap bounds the search


def fit_prior(terms):
    """Beta prior (alpha, beta) for the account's term-level conversion rates.

    terms: (clicks, conversions) pairs. The mean is the account's own conversion rate; the
    spread is fit by maximum marginal likelihood (the beta-binomial model), which weighs each
    term by what its clicks can actually say, so one big brand term cannot set the spread and
    an account whose terms really are alike is not mistaken for a noisy one. None if there is
    nothing to learn from (no clicks, or no conversions at all)."""
    counts = {}
    for n, k in terms:
        if n > 0:
            key = (n, min(k, n))
            counts[key] = counts.get(key, 0) + 1
    clicks = sum(n * c for (n, _), c in counts.items())
    conversions = sum(k * c for (_, k), c in counts.items())
    if not clicks or not conversions or conversions >= clicks:
        return None
    mu = conversions / clicks

    def loglik(log_kappa):
        kappa = math.exp(log_kappa)
        a, b = mu * kappa, (1 - mu) * kappa
        norm = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        return sum(c * (norm + math.lgamma(a + k) + math.lgamma(b + n - k) - math.lgamma(a + b + n))
                   for (n, k), c in counts.items())

    lo, hi = math.log(MIN_CONCENTRATION), math.log(MAX_CONCENTRATION)
    golden = (math.sqrt(5) - 1) / 2
    x1, x2 = hi - golden * (hi - lo), lo + golden * (hi - lo)
    f1, f2 = loglik(x1), loglik(x2)
    for _ in range(100):  # golden-section search: the likelihood has one peak in log(kappa)
        if f1 < f2:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + golden * (hi - lo)
            f2 = loglik(x2)
        else:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - golden * (hi - lo)
            f1 = loglik(x1)
    kappa = math.exp((lo + hi) / 2)
    return mu * kappa, (1 - mu) * kappa


def p_bad(clicks, conversions, prior, ratio=BAD_RATIO):
    """Probability that the term's true conversion rate is below ratio x the account's rate."""
    a, b = prior
    k = min(conversions, clicks)
    return incomplete_beta(a + k, b + clicks - k, ratio * a / (a + b))


def clicks_to_flag(prior, conversions=0, sure=CONFIDENT, ratio=BAD_RATIO, limit=10 ** 7):
    """The fewest clicks at which a term with this many conversions reaches P(bad) >= sure.
    P(bad) only rises with clicks at a fixed conversion count, so a doubling search and a
    bisection find it exactly. None if it would take more than `limit` clicks."""
    lo = hi = max(1, math.ceil(conversions))
    if p_bad(hi, conversions, prior, ratio) >= sure:
        return hi
    while p_bad(hi, conversions, prior, ratio) < sure:
        if hi > limit:
            return None
        lo, hi = hi, hi * 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if p_bad(mid, conversions, prior, ratio) >= sure:
            hi = mid
        else:
            lo = mid
    return hi


def incomplete_beta(a, b, x):
    """Regularized incomplete beta function I_x(a, b): the CDF of Beta(a, b) at x."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return front * _continued_fraction(a, b, x) / a
    return 1.0 - front * _continued_fraction(b, a, 1 - x) / b


def _continued_fraction(a, b, x, iterations=5000, eps=1e-15):
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, iterations + 1):
        m2 = 2 * m
        for num in (m * (b - m) * x / ((a - 1 + m2) * (a + m2)),
                    -(a + m) * (a + b + m) * x / ((a + m2) * (a + 1 + m2))):
            d = 1.0 + num * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + num / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < eps:
            return h
    return h
