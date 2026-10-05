"""Facts: the only numbers OpenPPC is allowed to print.

Templates print a number only by registering it here first, as a labeled fact. That
makes it impossible for a report to contain a figure the checker cannot trace, and it
gives `openppc check` the same list to judge anyone else's audit against.
"""
from dataclasses import dataclass, field

SYMBOLS = {"USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$", "EUR": "€", "GBP": "£", "INR": "₹"}


@dataclass(frozen=True)
class Fact:
    label: str        # what the number is, in words: "cost of 'free plumbing estimate'"
    value: float
    kind: str         # "money" | "pct" | "count"
    metric: str = ""  # cost, clicks, impressions, conversions, ctr, cpc, cpa, cvr, days, rule
    entity: str = ""  # the row or group it belongs to; "" for account-level figures
    level: str = ""   # "row" (a search term or keyword) or "group" (a campaign, ad group or match type)


def fmt_money(value, currency="USD"):
    symbol = SYMBOLS.get((currency or "").upper())
    return f"{symbol}{value:,.2f}" if symbol else f"{value:,.2f} {currency}"


@dataclass
class FactBook:
    currency: str = "USD"
    facts: list = field(default_factory=list)
    cards: dict = field(default_factory=dict)  # a template's results as data, for the web app; numbers as printed
    client: dict = field(default_factory=dict)  # the branded client report's pages as blocks; numbers as printed

    def add(self, label, value, kind, metric="", entity=""):
        if value is not None:
            self.facts.append(Fact(label, float(value), kind, metric, entity))
        return value

    def money(self, label, value, metric="cost", entity=""):
        self.add(label, value, "money", metric, entity)
        return fmt_money(value, self.currency)

    def pct(self, label, value, metric="", entity="", dp=1):
        self.add(label, value, "pct", metric, entity)
        return f"{value:.{dp}f}%"

    def count(self, label, value, metric="", entity="", dp=0):
        self.add(label, value, "count", metric, entity)
        return f"{value:,.{dp}f}"
