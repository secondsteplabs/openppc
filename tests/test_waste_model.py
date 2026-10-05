import math
import random

from openppc.engine.waste_model import clicks_to_flag, fit_prior, incomplete_beta, p_bad


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_incomplete_beta_matches_closed_forms():
    for x in (0.001, 0.05, 0.3, 0.5, 0.77, 0.999):
        assert close(incomplete_beta(1, 1, x), x)                       # uniform
        assert close(incomplete_beta(3.5, 1, x), x ** 3.5)              # I_x(a, 1) = x^a
        assert close(incomplete_beta(1, 4.2, x), 1 - (1 - x) ** 4.2)    # I_x(1, b) = 1 - (1 - x)^b
        assert close(incomplete_beta(2.5, 7, x), 1 - incomplete_beta(7, 2.5, 1 - x))  # symmetry
    assert close(incomplete_beta(40, 40, 0.5), 0.5)
    assert close(incomplete_beta(3, 2, 0.4), 0.1792)                   # 4x^3 - 3x^4 at 0.4
    assert close(incomplete_beta(900.5, 9100.5, 0.09), incomplete_beta(900.5, 9100.5, 0.09))  # large shapes converge
    assert 0 < incomplete_beta(900.5, 9100.5, 0.09) < 0.5


def test_prior_recovers_the_account_rate_and_its_spread():
    rng = random.Random(7)
    wide, narrow = [], []
    for _ in range(3000):
        n = rng.randint(5, 80)
        rate = rng.betavariate(2, 18)                                                  # each term has its own rate
        wide.append((n, sum(rng.random() < rate for _ in range(n))))
        narrow.append((n, sum(rng.random() < 0.10 for _ in range(n))))                  # every term the same
    a, b = fit_prior(wide)
    assert abs(a / (a + b) - 0.10) < 0.01 and 12 < a + b < 30                         # true alpha + beta = 20
    a, b = fit_prior(narrow)
    assert abs(a / (a + b) - 0.10) < 0.01 and a + b > 200                            # little real spread
    assert fit_prior([(10, 0), (5, 0)]) is None and fit_prior([]) is None


def test_more_clicks_without_conversions_mean_more_certainty():
    prior = (2.0, 18.0)                                                            # account rate 10%
    chances = [p_bad(n, 0, prior) for n in (0, 5, 10, 20, 40, 80, 160)]
    assert chances == sorted(chances) and chances[-1] > 0.99
    assert close(chances[5], 1 - 0.95 ** 98 * (1 + 98 * 0.05))                      # I_x(2, b) closed form: 0.961
    assert p_bad(40, 4, prior) < p_bad(40, 0, prior)                                # conversions are evidence too


def test_clicks_to_flag_is_the_exact_boundary():
    prior = (2.0, 18.0)
    n = clicks_to_flag(prior)
    assert p_bad(n, 0, prior) >= 0.9 > p_bad(n - 1, 0, prior)
    assert clicks_to_flag(prior, conversions=1) > n                                  # one conversion buys time
    assert clicks_to_flag((0.5, 99.5)) > clicks_to_flag((2.0, 18.0))                 # rarer conversions need more clicks
    assert math.isfinite(clicks_to_flag((5000.0, 45000.0)))                          # strong priors still converge
