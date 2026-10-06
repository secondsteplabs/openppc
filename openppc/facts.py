"""Facts: the only numbers OpenPPC is allowed to print.

Templates print a number only by registering it here first, as a labeled fact. That
makes it impossible for a report to contain a figure the checker cannot trace, and it
gives `openppc check` the same list to judge anyone else's audit against.
"""
from collections.abc import Sequence
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
    currency: str = ""  # money only: the currency code it is in, so it prints with its symbol


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
            self.facts.append(Fact(label, float(value), kind, metric, entity,
                                   currency=self.currency if kind == "money" else ""))
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


class FactList(Sequence):
    """Facts in order, where a long run of rows can be a block (checkfacts.RowFacts) that keeps each row as plain
    numbers and builds its facts only when they are read. Reads like a list of facts; trace reads the blocks by name
    and by value instead of end to end."""

    def __init__(self, parts=()):
        self.parts = []
        for part in parts:
            self += part

    def __iadd__(self, other):
        for part in other.parts if isinstance(other, FactList) else [other]:
            if not isinstance(part, list):
                self.parts.append(part)
            elif self.parts and isinstance(self.parts[-1], list):
                self.parts[-1] = self.parts[-1] + part
            else:
                self.parts.append(list(part))
        return self

    def __add__(self, other):
        return FactList([self, other])

    def __radd__(self, other):
        return FactList([other, self])

    def __len__(self):
        return sum(len(part) for part in self.parts)

    def __iter__(self):
        for part in self.parts:
            yield from part

    def __getitem__(self, i):
        if isinstance(i, slice):
            return list(self)[i]
        i = i + len(self) if i < 0 else i
        for part in self.parts:
            if i < len(part):
                return part[i]
            i -= len(part)
        raise IndexError("fact index out of range")
