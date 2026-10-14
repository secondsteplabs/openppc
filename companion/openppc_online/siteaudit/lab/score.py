"""Lighthouse 13's performance score: each metric on a log-normal curve between its 10th-percentile and median
control points, then the weighted mean. Ported from Lighthouse (Apache-2.0; shared/statistics.js, shared/util.js,
core/audits/metrics/*.js, core/scoring.js), credited in THIRD_PARTY_LICENSES.md."""
import math

# Closest double to erfc^-1(1/5): a value at the p10 point scores 0.9
INVERSE_ERFC_ONE_FIFTH = 0.9061938024368232
# metric -> (p10, median) per device; a value at the median scores 0.5
CONTROL = {
    "mobile": {"first-contentful-paint": (1800, 3000), "speed-index": (3387, 5800),
               "largest-contentful-paint": (2500, 4000), "total-blocking-time": (200, 600),
               "cumulative-layout-shift": (0.1, 0.25)},
    "desktop": {"first-contentful-paint": (934, 1600), "speed-index": (1311, 2300),
                "largest-contentful-paint": (1200, 2400), "total-blocking-time": (150, 350),
                "cumulative-layout-shift": (0.1, 0.25)},
}
WEIGHTS = {"first-contentful-paint": 10, "speed-index": 10, "largest-contentful-paint": 25,
           "total-blocking-time": 30, "cumulative-layout-shift": 25}
BANDS = ((90, "good"), (50, "needs improvement"), (0, "poor"))   # PSI's colours: green, orange, red
# the exact doubles Lighthouse clamps each range to
MIN_PASSING = 0.9000000000000000222
MAX_AVERAGE = 0.8999999999999999112
MAX_FAILING = 0.4999999999999999445


def _erf(x: float) -> float:
    """Abramowitz and Stegun 7.1.26, as Lighthouse approximates it (not math.erf, so scores match to the digit)."""
    sign = math.copysign(1, x)
    x = abs(x)
    t = 1 / (1 + 0.3275911 * x)
    y = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    return sign * (1 - y * math.exp(-x * x))


def log_normal(p10: float, median: float, value: float) -> float:
    """The share of the distribution above value, clamped to the band value falls in."""
    if value <= 0:
        return 1.0
    x = math.log(max(value / median, 5e-324)) * INVERSE_ERFC_ONE_FIFTH / -math.log(p10 / median)
    p = (1 - _erf(x)) / 2
    if value <= p10:
        return max(MIN_PASSING, min(1.0, p))
    if value <= median:
        return max(0.5, min(MAX_AVERAGE, p))
    return max(0.0, min(MAX_FAILING, p))


def metric_score(metric: str, device: str, value: float) -> float:
    """A metric's score from 0 to 1, two decimals, as its Lighthouse audit gives it."""
    p = log_normal(*CONTROL[device][metric], value)
    if p > 0.9:  # scores above 0.9 get up to half a point more, so more top scores floor to 1
        p += 0.05 * (p - 0.9)
    return math.floor(p * 100) / 100


def _js_round(v: float) -> int:
    """JavaScript's Math.round: halves go up, where Python's round goes to even."""
    return math.floor(v + 0.5)


def performance(values: dict[str, float], device: str) -> int:
    """The 0-100 performance score from the five metrics' values (ms; CLS unitless)."""
    total = sum(metric_score(m, device, values[m]) * w for m, w in WEIGHTS.items())
    return _js_round(_js_round(total / sum(WEIGHTS.values()) * 100) / 100 * 100)


def band(score: int) -> str:
    return next(name for line, name in BANDS if score >= line)
