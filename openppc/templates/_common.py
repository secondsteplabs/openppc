"""Helpers shared by the templates."""
import difflib
import hashlib
import os
import re
from collections import namedtuple

Totals = namedtuple("Totals", "cost clicks impressions conversions")

BRAND_MIN_LETTERS = 3      # brand names shorter than this are ignored
BRAND_TYPO_MIN_LETTERS = 5  # a brand's first word needs this many letters before typos of it count
BRAND_TYPO_RATIO = 0.8     # a word at least this similar to that first word is a typo of the brand
MIN_COST_USD = 20.0        # cost a zero-conversion search term or keyword needs before it is listed
# The same threshold in other currencies: about $20, rounded to a figure people type. Exchange rates drift, so
# these are starting points; --min-cost (Waste threshold in the app) always wins.
MIN_COST = {"USD": MIN_COST_USD, "CAD": 25, "AUD": 30, "NZD": 35, "EUR": 20, "GBP": 15, "CHF": 20, "SEK": 200,
            "NOK": 200, "DKK": 150, "PLN": 80, "CZK": 450, "HUF": 7_000, "INR": 1_500, "JPY": 3_000, "KRW": 25_000,
            "CNY": 150, "HKD": 150, "SGD": 25, "MYR": 90, "THB": 700, "IDR": 300_000, "PHP": 1_000,
            "VND": 500_000, "AED": 75, "SAR": 75, "ILS": 75, "TRY": 700, "ZAR": 350, "BRL": 100, "MXN": 350}


def min_cost_for(currency):
    """(threshold, known): the default threshold in the export's currency. For a currency without a
    default it is 20 of that currency, and known is False so the report can say so."""
    code = (currency or "USD").upper()
    return float(MIN_COST.get(code, MIN_COST_USD)), code in MIN_COST


def val(row, key):
    return row.get(key) or 0


def totals(rows):
    return Totals(*(sum(val(r, k) for r in rows) for k in ("cost", "clicks", "impressions", "conversions")))


def conv_dp(*values):
    """Conversions print as whole numbers unless the account records fractional ones."""
    return 1 if any((v or 0) % 1 for v in values) else 0


def esc(text):
    return str(text).replace("|", "\\|")


def plural(n, one, many=None):
    return one if n == 1 else (many or one + "s")


def brand_matcher(brand):
    """Return is_brand(text) for comma-separated brand names ("Pipewell Plumbing, Pipewell").

    A term is brand when it contains a brand name, or a word within a typo or two of a brand
    name's first word when that word has 5+ letters: "pipewel plumbing" counts for "Pipewell Plumbing".
    Brand terms are never flagged as waste, so they never become negative keywords."""
    names = [" ".join(re.findall(r"[a-z0-9]+", n.lower())) for n in re.split(r"[,;\n]", brand or "")]
    names = [n for n in names if len(n) >= BRAND_MIN_LETTERS]
    firsts = {n.split()[0] for n in names if len(n.split()[0]) >= BRAND_TYPO_MIN_LETTERS}

    def is_brand(text):
        words = re.findall(r"[a-z0-9]+", str(text).lower())
        padded = f" {' '.join(words)} "
        return (any(f" {n} " in padded for n in names)
                or any(difflib.SequenceMatcher(None, f, w).ratio() >= BRAND_TYPO_RATIO for f in firsts for w in words))
    return is_brand


def need(report, column, export_name, how_to_export):
    if not report.has(column, "clicks", "cost", "conversions"):
        raise ValueError(f"This template needs a {export_name} export with Clicks, Cost and "
                         f"Conversions columns. {how_to_export}")


def header(book, report, title):
    bits = [f"Source: `{os.path.basename(report.source)}`"]
    if report.start and report.end:
        s, e = report.start, report.end
        days = book.count("days in the date range", report.days, "days")
        bits.append(f"{s:%B} {s.day}, {s.year} to {e:%B} {e.day}, {e.year} ({days} days)")
    bits.append(f"currency {report.currency}")
    return [f"# {title}", "", " · ".join(bits), "",
            "_Built by OpenPPC, read-only: computed from this file alone, with no network calls._", ""]


def settings_line(min_s, brand=None, industry=None):
    """The settings that change a report's figures, said in the report itself, so `openppc check` can run the same
    audit again when it checks this report against the export."""
    bits = [f"waste threshold {min_s}"]
    if brand and brand.strip():
        bits.append(f"brand terms “{brand.strip()}”")
    if industry:
        from ..engine.benchmarks import lookup
        bits.append(f"industry averages: {lookup(industry)['key']}")
    return "Settings: " + " · ".join(bits)


def fingerprint(path):
    """SHA-256 of the export, so a reader can tell exactly which file a report was computed from."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (OSError, TypeError):
        return None


def period(report, compact=False):
    """ "July 1, 2026 to July 31, 2026", or "July 1 to July 31, 2026" when compact and within one year."""
    s, e = report.start, report.end
    if not (s and e):
        return None
    if compact and s.year == e.year:
        return f"{s:%B} {s.day} to {e:%B} {e.day}, {e.year}"
    return f"{s:%B} {s.day}, {s.year} to {e:%B} {e.day}, {e.year}"


def month_label(report):
    """ "July 2026" for a report inside one month, else the compact period."""
    s, e = report.start, report.end
    if not (s and e):
        return None
    return f"{s:%B} {s.year}" if (s.year, s.month) == (e.year, e.month) else period(report, compact=True)


def figures(t, grand, named=True):
    """Every standard figure of a row or group (named) or of the account, in the order they are registered:
    (label pattern, value, kind, metric). The pattern takes the name in quotes: "cost of {}"."""
    out = [("cost of {}", t.cost, "money", "cost"), ("clicks of {}", t.clicks, "count", "clicks")]
    if t.impressions:
        out.append(("impressions of {}", t.impressions, "count", "impressions"))
    out.append(("conversions of {}", t.conversions, "count", "conversions"))
    if t.impressions:
        out.append(("CTR of {}", t.clicks / t.impressions * 100, "pct", "ctr"))
    if t.clicks:
        out.append(("CPC of {}", t.cost / t.clicks, "money", "cpc"))
        out.append(("conversion rate of {}", t.conversions / t.clicks * 100, "pct", "cvr"))
    if t.conversions:
        out.append(("cost per conversion of {}", t.cost / t.conversions, "money", "cpa"))
    if named:
        if grand.cost:
            out.append(("{} share of total cost", t.cost / grand.cost * 100, "pct", "cost"))
        if grand.clicks:
            out.append(("{} share of total clicks", t.clicks / grand.clicks * 100, "pct", "clicks"))
        if grand.conversions:
            out.append(("{} share of total conversions", t.conversions / grand.conversions * 100, "pct", "conversions"))
    return out


def register_group(book, entity, t, grand):
    """Register every standard figure for one row or group (entity) or the account (entity '')."""
    name = f"'{entity}'" if entity else "the account"
    for pattern, value, kind, metric in figures(t, grand, bool(entity)):
        book.add(pattern.format(name), value, kind, metric, entity)
