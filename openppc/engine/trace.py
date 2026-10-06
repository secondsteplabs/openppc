"""The checker: find every number in a piece of text and trace it back to your data.

Each number gets one of four verdicts. People see two of them by plainer names (VERDICT_LABEL):
"not in data" is shown as "wrong number" and "mismatch" as "wrong label".

  traced        it equals a fact from your data, at the precision it was written.
                "$1.4k" matches 1,361.04 because both round to 1,400; "$1,500" does not.
  mismatch      it equals a fact, but the text attaches it to a different metric or row:
                "22 conversions" when 22 is that search term's clicks.
  not in data   nothing in your data produces it. It may be a guess, a typo, or a figure
                from data you did not provide. Either way, nobody has checked it.
  can't check   it is not a figure an export holds (a target, a threshold, a forecast, a
                what-if: "would cut CPA to $49"), or it is the audit's own calculation over rows
                we cannot rebuild (Performance Max against non-brand Search, "the other $3,690").
                Shown apart, with a prompt to ask for the working, and never counted as failing.

A number is only ever flagged when we know what it claims to be: a figure of a row or match type
the text names, of the rows it names together, of the terms that never converted, or of the whole
account. The flag then says what that figure really is. Everything else we cannot confirm is
"can't check": flagging the audit's own arithmetic as wrong would be a guess.

It also flags sentences whose verb contradicts their own numbers ("fell from 9% to 14%").

Besides each row and the account, it checks what audits usually work out: the sum, rates and
shares of the rows a sentence names together ("these three terms: 60 conversions, $44.99 per
conversion"), of a match type ("broad", "exact/phrase"), and of the rows under a heading. A
sentence that says "this term" or "it" refers to the row named just before.

Skipped on purpose: whole numbers up to 12 with no $ or % ("top 5", "7 skills", list
markers), unless they count the clicks, conversions or impressions of a row the text names
or of the whole account ("'drain cleaning' got 7 conversions"); years; day-of-month numbers
after a month name; and digits inside a search term or keyword that the text names
("40 gallon water heater"), quoted or not.

A row's figure backs a number only when the text names that row. With no row named, only
account-level figures count: otherwise any made-up number would find some row that happens
to share it. Round numbers with no metric word can still match an account figure by chance,
so every trace names the fact it matched. Read the "traced to" column, don't just count.
"""
import re
from dataclasses import dataclass

from ..facts import Fact, fmt_money

# Money: a symbol before the number ($, A$, CA$, NZ$, €, £, ₹, ¥, Rs), or a currency code before or after it.
CODES = ("USD|INR|EUR|GBP|AUD|CAD|NZD|JPY|CHF|SEK|NOK|DKK|PLN|CZK|HUF|KRW|CNY|HKD|SGD|MYR|THB|IDR|PHP|VND|AED"
         "|SAR|ILS|TRY|ZAR|BRL|MXN")
CUR = rf"(?:(?:US|AU|A|CA|C|NZ|HK|S|R|MX)\$|[$€£₹¥]|Rs\.?\s?|(?:{CODES})\s)"
# Grouped in thousands (144,775) or the Indian way in lakhs (1,44,775); "1.45 lakh" and "2 crore" are magnitudes.
# European decimals are one number: "€58,51" is 58.51 and "4.973,64" is 4,973.64. A minus sign stays with its number
# ("-$0.00"), but a dash between two numbers is not one ("$5-$7").
NUM = re.compile(rf"(?<![\w.$])(?P<sign>[-\u2212](?=\d|{CUR}))?(?P<cur>{CUR})?\s?(?P<num>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?"
                 rf"|\d{{1,2}}(?:,\d{{2}})+,\d{{3}}(?:\.\d+)?|\d{{1,3}}(?:\.\d{{3}})+,\d{{1,2}}(?!\d)"
                 rf"|(?<!\d,)\d+,\d{{1,2}}(?![\d,])|\d+(?:\.\d+)?)(?P<mag>[kKmM](?![A-Za-z])|\s?(?:[Ll]akhs?|[Ll]acs?|[Cc]rores?|[Cc]r|mn|bn)\b|\s(?:[Tt]housand|[Mm]illion|[Bb]illion)\b)?"
                 rf"(?P<pct>\s?%)?(?P<code>\s(?:{CODES})\b)?")
LIST_MARKER = re.compile(r"^\s*(?:[-*>]\s*)?(\d+)[.):/]\s")
MONTH_DAY = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b",
                       re.I)
CODE_SPAN = re.compile(r"`[^`]*`")  # file names and commands are identifiers, not claims
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}")
FROM_TO = re.compile(rf"\bfrom\s+~?{CUR}?\s?(\d[\d,]*(?:\.\d+)?)\s*%?\s*(?:to|→|-)\s*~?{CUR}?\s?"
                     r"(\d[\d,]*(?:\.\d+)?)", re.I)
VERB = re.compile(r"\b(fell|falls|fall|dropped|drops|declined|decreased|shrank|slipped|down|"
                  r"rose|rises|grew|increased|climbed|jumped|up)\b", re.I)
DOWN_VERBS = {"fell", "falls", "fall", "dropped", "drops", "declined", "decreased", "shrank", "slipped", "down"}
MAG = {"k": 1e3, "m": 1e6, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7,
       "thousand": 1e3, "million": 1e6, "billion": 1e9, "mn": 1e6, "bn": 1e9}
GENERIC = ("", "rule")  # facts that fit any wording: account-level unlabeled figures and our own thresholds
MONEY_METRICS = {"cost", "cpc", "cpa"}  # a dollar figure is a cost, a cost per click or a cost per conversion
ACCOUNT_ONLY = {"days"}  # no search term or keyword has a figure in days
NEVER_METRICS = {"cost", "clicks", "impressions", "terms"}  # what the terms that never converted add up to
GROUP = "__group__"  # the rows a sentence takes together; its figures are worked out per sentence

# Longer phrases win over the words inside them ("cost per click" is CPC, not cost).
METRIC_WORDS = [(metric, re.compile(pattern)) for metric, pattern in (
    ("cpc", r"cost[- ]per[- ]click|\bcpc\b|\bper click\b"),
    ("cpa", r"cost[- ]per[- ](?:conversion|conv|lead|acquisition|booking|sale|enquiry|inquiry|enquirie|inquirie)s?"
            r"|\bcpa\b|\bcpl\b|cost\s*/\s*conv\.?|\bcost each\b|(?<=\d)\s?each\b"
            r"|(?<=\d)\s?an? (?:lead|conversion|sale|booking|sign-?up|enquiry|inquiry|call|customer|student|admission)\b"
            r"|\bper (?:conversion|lead|booking|enquiry|inquiry|sale|sign-?up|admission|student|customer)\b"),
    ("ctr", r"click[- ]?through(?:[- ]rate)?|\bctr\b"),
    ("cvr", r"conv(?:ersion)?\.?[- ]rate|\bcvr\b|\bconvert(?:s|ed|ing)? at\b"
            r"|\bof (?:its |their |the |all )?clicks? (?:became|become|turned into|turns? into|converted|convert|led to|resulted in)"
            r"(?: (?:into |to )?(?:a |an )?(?:leads?|conversions?|sales|bookings?|sign-?ups?|enquir(?:y|ies)|inquir(?:y|ies)))?\b"
            r"|\b(?:became|become|turned into|turns? into|converted into|resulted in|led to) (?:a |an )?"
            r"(?:leads?|conversions?|sales|bookings?|sign-?ups?|enquir(?:y|ies)|inquir(?:y|ies))\b"),
    ("impressions", r"\bimpressions?\b|\bimpr\b"),
    ("clicks", r"\bclicks?\b"),
    ("conversions", r"\bconversions?\b|\bconv\b|\bleads?\b|\bbookings?\b|\bsales\b|\bsign-?ups?\b"
                    r"|\benquir(?:y|ies)\b|\binquir(?:y|ies)\b"),
    ("cost", r"\bcost\b|\bspend(?:ing)?\b|\bspent\b|\bwaste[d]?\b|\bwasting\b|\bbudget\b|\bburn(?:ed|ing|t|s)?\b"),
    ("terms", r"\bsearch terms?\b|\bkeywords?\b|\bterms\b|\bqueries\b"),  # "30 search terms" counts terms
    ("days", r"\bdays\b"),  # plural only: "31 days" counts days, "$24.75 a day" is a rate
)]
CLAUSE_BREAK = re.compile(r"[,;:.()]")  # "732 clicks, 85 conversions": the comma ends clicks' claim on 85
# A softer break: in "CTR was 7.43% and cost per conversion $58.5", "and" hands the next metric its own number.
CONJUNCTION = re.compile(r"\b(?:and|but|while|whereas|versus|vs)\b")
# Small whole numbers: checked only when they count something ("7 conversions"), never "top 5" or "step 3".
SMALL_COUNT = re.compile(r"\s*(?:more\s+|fewer\s+|extra\s+|new\s+)?(?:conversions?|conv\b|leads?|sales\b|bookings?|"
                         r"sign-?ups?|clicks?|impressions?|impr\b)", re.I)
NOT_A_COUNT = re.compile(r"(?:\btop|\bfirst|\blast|\bnext|\bstep|\bpriority|\brank|\bpage|\bposition|#)\s*$", re.I)
ACCOUNT_CUE = re.compile(r"\b(?:account|total|overall|in all|altogether)\b", re.I)
PERFORMANCE = {"clicks", "conversions", "impressions"}

QUOTED = re.compile(r"[“\"]([^”\"]{1,80})[”\"]")  # a quoted name counts at any length
MATCH_TYPES = {"broad match", "phrase match", "exact match", "broad", "phrase", "exact",
               "exact match (close variant)", "phrase match (close variant)"}
# "broad match", "6 broad keywords", "Broad:"; a pair ("exact/phrase", "Exact and Phrase deliver") names both together
# anywhere, while one word alone means nothing ("a broad strategy", "the exact figure")
MATCH_ALIAS = re.compile(r"\b(broad|exact|phrase)\s*(?:and|&|/|or|\+)\s*(broad|exact|phrase)\b|\b(broad|exact|phrase)"
                         r"(?=\s*(?:match|keywords?|terms?|queries|rows|:|\)|spend|cost|cpa|cost per|conversions?|clicks|"
                         r"\(\s*\d+\s*(?:keywords?|search terms?|terms?)))",
                         re.I)
SENTENCE = re.compile(r"(?<=[.!?])[*_]{0,2}\s+(?=\S)")
ANAPHORA = re.compile(r"\b(?:this|it|its|these|those|they|their|both)\b", re.I)
GROUP_CUE = re.compile(r"\b(?:combined|together|altogether|in total|between them|both|these|those)\b", re.I)
THESE_N = re.compile(r"\b(?:these|those|the|all)\s+(two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\b", re.I)
WORD_NUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
# Words that make a number something an export cannot hold: a target or limit, or a forecast or what-if.
TARGET = re.compile(r"\b(?:thresholds?|targets?|goals?|aim(?:ing)?|benchmarks?|limits?|caps?|minimum|maximum|"
                    r"at least|at most|no more than|up to|under|over|more than|fewer than|less than|smaller than|"
                    r"larger than|bigger than|above|below|measured against|compared (?:to|with)|relative to|"
                    r"sure|confiden(?:t|ce)|significan(?:t|ce)|bar|reach(?:ed|es)?|industry|sector|vertical|niche|"
                    r"typical|median)\b|\b[a-z]+-[a-z]+\s+average\b",
                    re.I)
WHATIF = re.compile(r"\b(?:would|could|might|will|if|without|excluding|instead|expect(?:ed)?|forecasts?|"
                    r"projected|projections?|estimated?|annuali[sz]ed|a year|per year|yearly|per month|monthly|"
                    r"saves?|saved|savings?|frees? up|recover(?:ed|able)?|redeploy(?:ed)?|realloca\w*|increase|decrease|raise|"
                    r"(?<!or )lower|reduce|cuts?|cutting|boost|lift|improve(?:ment|s|d)?)\b|\d\s?[x×]\b|"
                    r"\bof (?:that|this|the|its) (?:ad group|campaign)", re.I)
LIST_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
OF_PAIR = re.compile(r"(\d[\d,]*(?:\.\d+)?)%?\s+(?:of|out of)\s+(?:the\s+|all\s+|its\s+|their\s+)?"
                     r"(?:[$\u20ac\u00a3\u20b9]\s?)?(\d[\d,]*(?:\.\d+)?)")  # "60 of 85 conversions"
NEVER = re.compile(r"never convert|zero[- ](?:conversions?|leads?|enquir(?:y|ies)|inquir(?:y|ies)|sales|bookings?)|"
                   r"no (?:conversions?|leads|enquir(?:y|ies)|inquir(?:y|ies)|sales|bookings)|0 conversions?|"
                   r"without (?:a |any )?(?:conversions?|leads?|enquir(?:y|ies))|did(?:n't| not) convert|"
                   r"(?:non|zero)-?converting", re.I)
WASTE_WORDS = re.compile(r"wast|never convert|zero[- ]conv|no conv|zero[- ](?:lead|enquir)|no (?:leads|enquir)|"
                         r"(?:non|zero)-?converting", re.I)
# subjects we cannot rebuild from an export: subsets, segments, campaign types, unnamed groups
SUBSET = re.compile(r"\b(?:the other|the rest|remaining|rest of|excluding|except|"
                    r"other than|non-?brand|branded|brand|subtotal|only|just|of them|of which|each of|mobile|desktop|"
                    r"tablet|devices?|weekends?|weekdays?|mornings?|evenings?|hours?|locations?|cit(?:y|ies)|"
                    r"regions?|states?|countr(?:y|ies)|age|gender|audiences?|pmax|performance max|display|shopping|"
                    r"video|demand gen|campaigns?|ad groups?|or (?:lower|below|less|fewer|higher|above|more)|low[- ]scor\w*)\b", re.I)
UNNAMED = re.compile(r"\b(?:one|a|an|another|some|each|any|the top|top|the best|the worst|the biggest|the largest|"
                     r"the cheapest)\s+(?:\w+\s+)?(?:search\s+)?(?:terms?|keywords?|quer(?:y|ies)|campaigns?|"
                     r"ad groups?|searches)\b", re.I)
QUALIFIER = re.compile(r"\b(?:non-?brand|brand(?:ed)?|search(?!\s+(?:terms?|quer(?:y|ies)))|pmax|performance max|"
                       r"display|shopping|"
                       r"video|demand gen|excluding|except|without|other than|only)\b", re.I)
# A waste figure over a slice of the no-conversion terms (brand left out, one campaign type), which an export can't
# rebuild without knowing the slice: never compared with the figure for all of them. "Without" alone is not one:
# "terms without conversions" is how waste is described.
NEVER_SLICE = re.compile(r"\bnon-?brand(?:ed)?\b|\bbrand(?:ed)?\b|\b(?:excluding|exclude[sd]?|except|other than|minus|"
                         r"not counting|leaving out|leave out|apart from)\b|\bwithout (?:your |the |any )?brand|"
                         r"\bsearch(?!\s+(?:terms?|quer(?:y|ies)|reports?))\b|\bpmax\b|\bperformance max\b|\bdisplay\b|"
                         r"\bshopping\b", re.I)
# "the rows named together" only when the text means them together; with no such rows, these words mean a subset
GROUP_WORDS = re.compile(r"\b(?:combined|together|between them|both|these|those|they|them|their)\b", re.I)
# "five terms drove 71 of 85 conversions": a counted set of rows, not the account, unless it is all of them
COUNTED = re.compile(r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{1,3})\s+(?:[a-z-]+\s+){0,2}?"
                     r"(?:search terms?|keywords?|terms|queries|searches)\b")
# a list that goes on past the rows it names ("..., plus teacher jobs"; "including X"): the names are examples
LIST_MORE = re.compile(r"\b(?:plus|including|includes|such as|among|e\.g\.|etc|and others|and more|led by)\b", re.I)
# "paused keywords", "tightly targeted keywords", "how-to queries": rows the text describes but does not name
SUBSET_NOUN = re.compile(r"\b([a-z][a-z'-]*)\s+(?:keywords|search terms|search queries|terms|searches|queries)\b")
NOT_A_SUBSET = {"all", "the", "your", "our", "their", "its", "these", "those", "search", "total", "no", "zero", "non",
                "any", "some", "each", "every", "other", "more", "fewer", "of", "and", "or", "in", "on", "to", "for",
                "with", "from", "by", "at", "as", "into", "across", "between", "a", "an", "two", "three", "four",
                "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "many", "several", "few", "both",
                "which", "that", "were", "are", "is", "was", "have", "has", "had", "broad", "phrase", "exact",
                "match", "matching", "same", "such", "whose", "where", "than", "word", "live", "active", "enabled",
                "serving", "running", "current"}
PER_UNIT_GAP = re.compile(r"\s*(?:(?:to|-|–|and)\s*~?[$€£₹]?\s?[\d,.]+[kKmM]?\s*)?")
LABEL_COLON = re.compile(r"[\s*_]*:[\s*_]*")
# "$44 to $48", "9-14%": the two ends of a range share their words
RANGE_MAG = r"(?:[km]|\s?(?:thousand|million|lakhs?|crores?))?"  # "$2.5k to $3k": the first end's own magnitude
BETWEEN = re.compile(rf"\bbetween\s+~?{CUR}?\s?(\d[\d,.]*){RANGE_MAG}\s*%?\s*(?:and|&)\s*~?{CUR}?\s?(\d[\d,.]*)")
EU_DECIMAL = re.compile(r",\d{1,2}$")  # "58,51" and "4.973,64"; "4,200" and "1,44,775" are grouped thousands
RANGE = re.compile(rf"(\d[\d,]*(?:\.\d+)?){RANGE_MAG}\s*%?\s*(?:to|–|-)\s*~?{CUR}?\s?(\d[\d,]*(?:\.\d+)?)")
COST_WORD = re.compile(r"\bcosts?\b|\bcosting\b")  # "cost $157.02" may mean a price per lead as well as a total
# a table on its side whose columns are the account: "| Metric | July |", "| | Value |"
PERIOD_HEADER = re.compile(r"^\W*(?:values?|totals?|account|amounts?|figures?|results?|numbers?|this month|last month|"
                           r"month|period|this period|last \d+ days|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
                           r"[a-z]*\W*(?:\d{4})?\W*$")
OF_BASE = re.compile(r"\s*of\s+(?:the\s+|total\s+|all\s+|your\s+|its\s+|their\s+|our\s+)?")
# words that can stand before a number in its clause without naming anything: "drove 31", "your account spent"
LABEL_STOP = set("""a an the and or but yet nor so for of to in on at by with from into over under about around across
between per each than then also just only still even nearly almost roughly approximately some any all both this that
these those its it they their them our your you we us which who whose what when where while whereas is was are were be
been being has have had does did do got gets get gave give gives took take takes made make makes brought bring brings
drove drive drives used use uses spent spend spends cost costs paid pay pays earned earns generated generates delivered
delivers produced produces returned returns yielded yields converted converts scored scores ran runs sits stands came
comes went goes worth plus total overall average averaging avg rate share means giving leaving left more less fewer
most least top best worst biggest largest highest lowest alone combined together respectively one two three four five
six seven eight nine ten eleven twelve month months week weeks day days year last this next january february march
april may june july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec account
accounts google ads adwords ppc paid there here now today currently ending ended landed fell rose dropped grew climbed
jumped declined increased decreased went moved stayed remained hit reached up down not exactly precisely actually really
simply already always never rather instead again once twice versus against compared though although because since
after before during within without via like such""".split())
BRACKET_OPEN = re.compile(r"\s*\(\s*")  # "₹25,287 (17.5%)": a bare share right after a figure, in brackets
ACCOUNT_LABEL = {"cost": "cost", "clicks": "clicks", "conversions": "conversions", "impressions": "impressions",
                 "ctr": "CTR", "cpc": "CPC", "cvr": "conversion rate", "cpa": "cost per conversion"}
CLAUSE_EDGE = re.compile(r"(?<!\d)[,;:](?!\d)|[,;:](?=\s)|\.(?=[*_]{0,2}(?:\s|$))|\(|\)")  # not "1,234"
# "At this account's 11.0% conversion rate", "the account's $58.51 per conversion": whatever else the sentence
# compares or forecasts, this number is the account's own figure
ACCOUNT_ANCHOR = re.compile(r"\b(?:the|this|your) account(?:'s|s')?(?:\s+[a-z./-]+){0,3}\s*$")
# "It converts, but at $90.63 each": the one row the line named just before
ANAPHORA_START = re.compile(r"^\W*(?:it|its|this (?:term|keyword|search|query|one)|that (?:term|keyword|one))\b")
CURRENT = {"cost": "spend", "impressions": "impressions", "clicks": "clicks", "conversions": "conversions",
           "ctr": "CTR", "cpa": "CPA", "cvr": "conversion rate", "cpc": "CPC"}  # an account report's period figures


@dataclass
class Claim:
    line: int
    written: str
    value: float
    verdict: str   # "traced" | "mismatch" | "not in data" | "can't check"
    detail: str    # the fact it traced to, or why it did not
    context: str


def _digits(num):
    """A number as written, as plain digits: '1,361.04' -> '1361.04', '4.973,64' -> '4973.64', '58,51' -> '58.51'."""
    if EU_DECIMAL.search(num):
        return num.replace(".", "").replace(",", ".")
    return num.replace(",", "")


def _ranges(line, masked, sentences, earlier):
    """'$5-$7', '7-8%', 'between 50 and 60': each end's position -> the range, judged as one figure. A range is
    true when the real figure falls inside it, so it is checked at its middle with half its width as slack."""
    found = {m.start("num"): m for m in NUM.finditer(line)}
    out = {}
    for r in list(RANGE.finditer(masked)) + list(BETWEEN.finditer(masked)):
        ends = [found.get(r.start(1)), found.get(r.start(2))]
        if None in ends or r.start(1) in earlier or any(e.group("sign") for e in ends):
            continue  # "from 9% to 14%" is a change; "-5% to -7%" is left alone
        kinds = {"money" if (e.group("cur") or e.group("code")) else "pct" if e.group("pct") else "plain" for e in ends}
        if kinds >= {"money", "pct"}:
            continue
        kind = "money" if "money" in kinds else "pct" if "pct" in kinds else "plain"
        raws, mags = [e.group("num") for e in ends], [e.group("mag") for e in ends]
        if bool(mags[0]) != bool(mags[1]):
            mags = [mags[0] or mags[1]] * 2  # "₹6-7k": the k is for both ends
        vals = [float(_digits(n)) * MAG.get((g or "").strip().lower(), 1) for n, g in zip(raws, mags)]
        gap = masked[ends[0].end():ends[1].start()]
        sentence = next((masked[a:b] for a, b in sentences if a <= r.start(1) < b), masked)
        if kind == "plain" and (gap.strip() == "-" or all(1900 <= v <= 2100 and n.isdigit() for v, n in zip(vals, raws))):
            continue  # "2025-26", "9-5", "between 2024 and 2026": not a range of figures
        if "to" in gap and VERB.search(sentence):
            continue  # "CTR fell 9% to 7%": a change, not a range
        lo, hi = min(vals), max(vals)
        if lo <= 0 or hi / lo > 10:
            continue  # too wide to be one figure's range: each number is judged on its own
        tol = (hi - lo) / 2 + max(_tolerance(n, g, kind == "pct") for n, g in zip(raws, mags))
        for e in ends:
            out[e.start("num")] = {"id": r.start(1), "kind": kind, "mid": (lo + hi) / 2, "tol": tol}
    return out


def _tolerance(num, mag, pct=False):
    """Half of one unit in the last digit written. '312' -> 0.5, '1.4k' -> 50, '16.8' -> 0.05.
    Trailing zeros on large whole numbers are ambiguous ('4,200'), so they get at most 5% slack. Not on
    percentages or numbers under 100: '60%' for 57% and '20 clicks' for 19 are wrong, not rounded."""
    s = _digits(num)
    mult = MAG.get((mag or "").strip().lower(), 1)
    if "." in s:
        return 10 ** -len(s.split(".", 1)[1]) / 2 * mult + 1e-9
    stripped = s.rstrip("0") or "0"
    trailing = len(s) - len(stripped)
    if pct or float(s) * mult < 100:
        trailing = 0
    half = 10 ** trailing / 2
    if trailing:
        half = min(half, 0.05 * float(s))
    return half * mult + 1e-9


def _metric_spans(text):
    spans = []
    for prio, (metric, rx) in enumerate(METRIC_WORDS):
        spans += [(m.start(), m.end(), metric, prio) for m in rx.finditer(text)]
    return [a for a in spans
            if not any(b[0] <= a[0] and a[1] <= b[1] and (b[1] - b[0]) > (a[1] - a[0]) for b in spans)]


def _evidence(text, spans, start, end, kind, numbers, partner=None, bounds=None, limit=45):
    """Every metric word near a number, ranked by distance. A clause break or an "and" makes a word
    farther, and a dollar figure only listens to money words: it is never a click count or a rate.
    A word with another number between it and this one belongs to that number ("$1,361 / 31 conversions /
    $43.90 CPA": CPA is $43.90's), except a number's partner: "from $45 to $58" and "60 of 85 conversions"
    share their words. A word in another sentence never counts."""
    found = {}
    for s, e, metric, prio in spans:
        if kind == "money" and metric not in MONEY_METRICS or kind != "plain" and metric in ("terms", "days"):
            continue
        if bounds and not (bounds[0] <= s < bounds[1]):
            continue
        lo, hi = (end, s) if s >= end else ((e, start) if e <= start else (None, None))
        if lo is None:
            continue
        between = text[lo:hi]
        if len(between) > limit or ";" in between or between.count("(") != between.count(")"):
            continue  # "...($157.02 each); its twin gets 22": "each" is the bracket's, and the clause is over
        if any(lo <= a < hi and a != partner for a, _ in numbers):
            continue
        if kind == "pct" and s >= end and OF_BASE.fullmatch(between):
            rank = (0, prio)  # "59% of spend": the share is of the metric named right after it
        elif kind == "money" and metric in ("cpa", "cpc") and s >= end and PER_UNIT_GAP.fullmatch(between):
            rank = (0, prio)  # "$45.82 a lead", "$44 to $48 a lead": a price per lead, whatever "cost" said before
        elif s < start and LABEL_COLON.fullmatch(between):
            rank = (1, prio)  # "Spend: $4,973.64": a label and its value
        else:
            rank = (len(between) + (25 if CLAUSE_BREAK.search(between) else 0)
                    + (10 if CONJUNCTION.search(between) else 0), prio)
        found[metric] = min(rank, found.get(metric, rank))
    return found


def _entities_in(low, entities):
    found = []
    for ent in entities:
        i = low.find(ent)
        while i != -1:
            j = i + len(ent)
            bounded = (i == 0 or not low[i - 1].isalnum()) and (j == len(low) or not low[j].isalnum())
            negated = low[max(0, i - 4):i] in ("non-", "non ")  # "non-brand" is everything but the Brand campaign
            if bounded and not negated and not any(s <= i and j <= e for s, e, _ in found):
                found.append((i, j, ent))
            i = low.find(ent, i + 1)
    return found


def _quoted(low, all_entities, found):
    """Rows named in quotes, at any length: “日本” or "tv" is a name when it is exactly a row."""
    out = []
    for m in QUOTED.finditer(low):
        name = " ".join(m.group(1).split()).strip(" *")
        if name in all_entities and not any(s <= m.start(1) < e for s, e, _ in found + out):
            out.append((m.start(1), m.end(1), name))
    return out


def _row_name(line, all_entities):
    """The row a table line is about: its first cell, when that cell is exactly a row in the data. Exact, so a
    short name counts here ("got", "tv") though it is too short to look for in running text. Works for markdown
    tables and for the "cell | cell |" lines the app reads off a finished PDF."""
    if "|" not in line:
        return None
    first = line.strip().strip("|").split("|", 1)[0].strip(" *“”\"'`").lower()
    if first in all_entities:
        return first
    kind = re.match(r"(broad|exact|phrase)(?:\s+match)?\b(?!\s*(?:and|&|/|or|\+))", first)
    return f"{kind.group(1)} match" if kind and f"{kind.group(1)} match" in all_entities else None


def _mask(text, spans):
    chars = list(text)
    for s, e, _ in spans:
        chars[s:e] = " " * (e - s)
    return "".join(chars)


def _cells(line):
    out, start = [], None
    for i, ch in enumerate(line):
        if ch == "|":
            if start is not None:
                out.append((start, i))
            start = i + 1
    return out


def _tables(lines):
    """line index -> [(cell start, cell end, header text)] for each markdown table body row."""
    ctx, i = {}, 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|") and i + 1 < len(lines) and TABLE_SEP.match(lines[i + 1]):
            headers = [lines[i][s:e].strip() for s, e in _cells(lines[i])]
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                ctx[j] = [(s, e, headers[k] if k < len(headers) else "")
                          for k, (s, e) in enumerate(_cells(lines[j]))]
                j += 1
            i = j
        else:
            i += 1
    return ctx


def _header_metric(header):
    low = header.lower()
    low = _mask(low, [(m.start(), m.end(), "") for m in NEVER.finditer(low) if not m.group(0)[0].isdigit()])
    spans = _metric_spans(low)
    return min(spans, key=lambda s: s[3])[2] if spans else None


def _small_count(line, m, cell, named):
    """Whether a whole number up to 12 is a claim to check: a click, conversion or impression count of a row
    the text names, or of the whole account. A Clicks or Conversions column counts as the metric word."""
    if NOT_A_COUNT.search(line[:m.start()]):
        return False
    counted = (cell is not None and _header_metric(cell) in PERFORMANCE) or bool(SMALL_COUNT.match(line[m.end():]))
    return counted and (bool(named) or bool(ACCOUNT_CUE.search(line)))


def _bases(facts):
    """Each row's own cost, clicks, conversions and impressions, and the account's: what group figures add up."""
    base, grand = {}, {}
    for f in facts:
        for metric, kind in (("cost", "money"), ("clicks", "count"), ("conversions", "count"),
                             ("impressions", "count")):
            if f.metric != metric or f.kind != kind:
                continue
            if f.entity and f.label == f"{metric} of '{f.entity}'":
                row = base.setdefault(f.entity.lower(), {"level": f.level})
                row.setdefault(metric, f.value)  # the first is the row's total
                if f.currency:
                    row.setdefault("currency", f.currency)
            elif not f.entity and f.label == f"{metric} of the account":
                grand.setdefault(metric, f.value)
    return base, grand


def _group_facts(members, base, grand):
    """Sum, rates and shares of rows named together. Like with like: search terms with search terms, a match
    type with a match type, never a campaign plus the terms inside it."""
    uniq = [m for m in dict.fromkeys(members) if m in base]
    terms = [m for m in uniq if base[m].get("level") == "row"]
    groups = [m for m in uniq if base[m].get("level") == "group"]
    pick = terms if len(terms) >= 2 else groups if len(groups) >= 2 else uniq if not terms and not groups else []
    rows = [base[m] for m in pick]
    if len(rows) < 2:
        return []
    s = {k: sum(r.get(k) or 0 for r in rows) for k in ("cost", "clicks", "conversions", "impressions")}
    tag = f"the {len(rows)} rows named together"
    cur = next((r["currency"] for r in rows if r.get("currency")), "")
    out = [Fact(f"cost of {tag}", s["cost"], "money", "cost", GROUP, currency=cur),
           Fact(f"clicks of {tag}", s["clicks"], "count", "clicks", GROUP),
           Fact(f"conversions of {tag}", s["conversions"], "count", "conversions", GROUP)]
    if s["impressions"]:
        out += [Fact(f"impressions of {tag}", s["impressions"], "count", "impressions", GROUP),
                Fact(f"CTR of {tag}", s["clicks"] / s["impressions"] * 100, "pct", "ctr", GROUP)]
    if s["clicks"]:
        out += [Fact(f"CPC of {tag}", s["cost"] / s["clicks"], "money", "cpc", GROUP, currency=cur),
                Fact(f"conversion rate of {tag}", s["conversions"] / s["clicks"] * 100, "pct", "cvr", GROUP)]
    if s["conversions"]:
        out.append(Fact(f"cost per conversion of {tag}", s["cost"] / s["conversions"], "money", "cpa", GROUP,
                        currency=cur))
    for metric in ("cost", "clicks", "conversions"):
        if grand.get(metric):
            out.append(Fact(f"share of total {metric} of {tag}", s[metric] / grand[metric] * 100, "pct", metric, GROUP))
    return out


def _cant_check(clause):
    """Why a number that traced to nothing is not a figure an export holds, judged on its own clause."""
    if WHATIF.search(clause):
        return "a forecast, what-if or calculation an export cannot confirm: check it yourself"
    if TARGET.search(clause):
        return "a target, threshold or comparison, not a figure in your data"
    return None


def _show(f):
    if f.kind == "money":
        return fmt_money(f.value, f.currency) if f.currency else f"{f.value:,.2f}"
    if f.kind == "pct":
        return f"{f.value:.2f}%" if abs(f.value) < 1 else f"{f.value:.1f}%"
    return f"{f.value:,.1f}" if f.value % 1 else f"{f.value:,.0f}"


def _canonical(subject, metric, kind, facts, sentence):
    """The figure a subject has for a metric, when there is exactly one sensible one to compare with."""
    who, name = subject
    if who == "account" and kind == "pct" and VERB.search(sentence) and not FROM_TO.search(sentence):
        label = f"{CURRENT.get(metric, metric)} change"  # "CPA down 20%": the change on the period before
        change = next((f for f in facts if not f.entity and f.label == label), None)
        if change:
            return change
    want = "money" if metric in MONEY_METRICS else ("pct" if metric in ("ctr", "cvr") else "count")
    if kind == "pct" and metric in ("cost", "clicks", "conversions"):
        want = "pct"  # a share of total cost, clicks or conversions
    if kind != "plain" and kind != want:
        return None
    pool = [f for f in facts if f.metric == metric and f.kind == want]
    if who == "account":
        if metric == "terms":
            return next((f for f in facts if not f.entity and f.label.endswith(" in this export")), None)
        labels = {f"{ACCOUNT_LABEL.get(metric, metric)} of the account", f"current {CURRENT.get(metric, metric)}"}
        return next((f for f in pool if not f.entity and f.label in labels), None)
    if who == "never":
        return next((f for f in pool if not f.entity and "with no conversions" in f.label), None)
    if who == "group":
        return next((f for f in pool if f.entity == GROUP), None)  # the sum, or for a percentage the share
    own = [f for f in pool if f.entity.lower() == name]
    if want == "pct" and metric in ("cost", "clicks", "conversions"):
        waste = [f for f in own if "with no conversions" in f.label]
        share = [f for f in own if "share of total" in f.label]
        own = waste if (waste and WASTE_WORDS.search(sentence)) else share
    return own[0] if own else None


def _settle(value, kind, about, subject, facts, sentence, detail=""):
    """For a number that traced to nothing: flag it only when we know what it claims to be, and say what that
    figure really is; otherwise it is the audit's own calculation, which we cannot confirm."""
    open_calc = ("can't check", "the audit's own calculation over rows OpenPPC cannot rebuild: ask it to show "
                                "which rows it added up")
    if subject is None:
        return open_calc
    if subject[0] == "unnamed":
        return "can't check", "about a row the text doesn't name: name the search term or campaign to check it"
    if subject[0] == "earlier":
        return "can't check", "an earlier figure: an export of one period cannot confirm it"
    if about is None:
        if subject[0] == "row":  # a named row, and none of its figures is this number
            return "not in data", (detail if detail.startswith("that figure is the")
                                   else f"none of the figures for '{subject[1]}' is this number")
        return open_calc
    fact = _canonical(subject, about, kind, facts, sentence)
    if fact is None:
        return open_calc
    return "not in data", f"no: the {fact.label} is {_show(fact)}"


def _judge(value, tol, kind, evidence, ents, facts, implied=False, loose=False):
    """Weigh every fact the number could be, then pick the one the sentence most likely means.

    The closest metric word says what the number is about. A row the sentence names counts unless the
    metric is one no row has ("Acme audit, last 30 days": the brand is also a search term, but
    days belong to the account). The named row's own figure on another metric is a mismatch, but only
    when the text names the row itself: a row carried over from "this term" is a guess, never grounds to accuse.
    A mismatch also needs the metric word right at the number ("22 conversions", "CTR of 7.4%", "Spend: $312"):
    a word further off may belong to something else, so that is "can't check", with the figure it matches.
    """
    cands = [f for f in facts if (kind == "plain" or f.kind == kind) and abs(f.value - value) <= tol]
    if not cands:
        return "not in data", "no figure in your files matches it at the precision written"
    about = min(evidence, key=evidence.get) if evidence else None
    named = set() if about in ACCOUNT_ONLY else ents

    strong = about is not None and evidence[about][0] <= 6

    def fits(f):
        return (about is None or f.metric in GENERIC or f.metric == about
                or (loose and f.metric in MONEY_METRICS))  # "cost $157.02": a total, or the cost of each lead

    def accuse(f):
        if strong:
            return "mismatch", f"that figure is the {f.label}"
        return "can't check", f"it matches the {f.label}: check which figure the text means"

    def closest(fs):
        return min(fs, key=lambda f: (abs(f.value - value), evidence.get(f.metric, (99, 99))))

    if named:
        own = [f for f in cands if f.entity.lower() in named]
        if any(fits(f) for f in own):
            return "traced", closest([f for f in own if fits(f)]).label
        overall = [f for f in cands if not f.entity and fits(f)]
        if overall:  # an account figure that fits the words beats a named row's figure on another metric
            return "traced", closest(overall).label
        if own and not implied:
            return accuse(closest(own))
        other = closest(cands)
        if not other.entity:  # an account figure on another metric: a mix-up we can name for sure
            return accuse(other)
        # another row's figure: a wrong row, or a row named in a way we did not recognise; flag it, don't accuse
        return "not in data", f"that figure is the {other.label}, not a figure of what the text names"
    good = [f for f in cands if fits(f)]
    account = [f for f in good if not f.entity]
    if account:  # no row named: only an account-level figure can back it
        return "traced", closest(account).label
    if good:  # only some row's figure, and the text never says which row: chance until it names one
        return "not in data", (f"only a row the text doesn't name has this figure (the {closest(good).label}); "
                               "name the search term or campaign to check it")
    account = [f for f in cands if not f.entity]
    if account:  # "309 conversions" when the account had 309 clicks
        return accuse(closest(account))
    # the only match is some unnamed row's figure on another metric: a coincidence, not a mix-up
    return "not in data", "no figure in your files matches it at the precision written"


def _contradictions(lines):
    found = []
    for n, line in enumerate(lines, 1):
        for m in FROM_TO.finditer(line):
            verbs = list(VERB.finditer(line[max(0, m.start() - 45):m.start()]))
            if not verbs:
                continue
            verb = verbs[-1].group(1).lower()
            a, b = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
            if a == b:
                continue
            said_down = verb in DOWN_VERBS
            if said_down != (b < a):
                movement = "a fall" if b < a else "a rise"
                found.append((n, f"says '{verb}', but {m.group(1)} to {m.group(2)} is {movement}", line.strip()[:140]))
    return found


def _names(line, low, entities, all_entities, families):
    """The rows a line names: in running text (four letters or more), in quotes, as a table row's first cell,
    or as a match type ("broad keywords"; "exact/phrase" names both together, as one group)."""
    ents = _entities_in(low, entities)
    ents += _quoted(low, all_entities, ents)
    row = _row_name(line, all_entities)
    named = [(s, e, n) for s, e, n in ents]
    if row and not any(n == row for _, _, n in named):
        named.append((0, 0, row))
    unions = []
    for m in MATCH_ALIAS.finditer(low):
        if any(s <= m.start() < e for s, e, _ in ents):
            continue
        before = low[:m.start()].rstrip(" *(")
        if any(before.endswith(n) for _, _, n in ents):  # "plumber near me (exact)" is that term's match type
            continue
        words = [w.lower() for w in m.groups() if w]
        members = [e for w in words for e in families.get(w, [])]
        if len(words) == 2:
            unions.append((m.start(), m.end(), members))
        else:
            named += [(m.start(), m.end(), e) for e in members]
    return ents, named, unions


def _column(header, entities, all_entities, families):
    """What a column of a table on its side is about, from its header: one row or match type ("Broad (6 keywords)"),
    two match types together ("Exact/phrase"), the account ("July", "Value"), or None when we can't tell."""
    low = " ".join(header.lower().replace("*", " ").split())
    kind = re.fullmatch(r"(broad|exact|phrase)(?:\s+match)?(?:\s*\(.*\))?", low)
    if kind and f"{kind.group(1)} match" in all_entities:
        return ("row", f"{kind.group(1)} match")
    _, named, unions = _names(low, low, entities, all_entities, families)
    if unions:
        return ("group", unions[0][2])
    found = list(dict.fromkeys(n for _, _, n in named))
    if len(found) == 1:
        return ("row", found[0])
    if not found and (not low or PERIOD_HEADER.match(low)):
        return ("account", None)
    return None


def _counted(sentence, own):
    """Whether the sentence is about a counted set of rows ("five terms", "3 broad keywords") other than all of them.
    The count that is itself the number being checked does not count."""
    for m in COUNTED.finditer(sentence):
        if m.start() <= own < m.end():
            continue
        before = sentence[:m.start()].rstrip().split()[-1:] or [""]
        if before[0] not in ("all", "your", "account's", "the"):
            return True
    return False


def _subset_noun(text):
    """Whether the text describes rows without naming them: "paused keywords", "tightly targeted keywords"."""
    return any(m.group(1) not in NOT_A_SUBSET and m.group(1).split("-")[0] not in NOT_A_SUBSET
               for m in SUBSET_NOUN.finditer(text))


def _labelled(before):
    """Whether the words before a number in its clause name something we did not recognise: "IAS salary ₹2,930",
    "hostel (₹2,710)". The number belongs to that, not to a row named elsewhere in the sentence."""
    return any(w not in LABEL_STOP for w in re.findall(r"[a-z][a-z'-]{2,}", before))


def _subject(named, unions, row, here, implied, lo, hi, a, b, start, sentence, clause, cell, line, base, about,
             groups=1, before="", heading=""):
    """What a number claims to be a figure of, read from the closest words out: a table row; the one row or match
    type its own clause names, or the rows it names together; the terms that never converted; the one row or the
    rows its sentence names; or else the whole account. None when it is a slice we cannot rebuild ("Search broad
    match", "excluding brand", "paused keywords", a list that goes on with "plus ..."), or a row only implied by
    "this". The flag that follows is only as sure as this reading, so every doubt answers None."""
    if implied:
        return None
    header = (cell or "").lower()
    first = line.strip().strip("|").split("|", 1)[0].strip(" *").lower() if "|" in line else ""
    if row:
        return None if SUBSET.search(header) else ("row", row)
    if cell is not None:  # a table row we could not name: its first cell says what it is, or we can't tell
        if QUALIFIER.search(first) or SUBSET.search(header + " " + first):
            return None  # "All Search", "Non-brand"
        if about in NEVER_METRICS and (NEVER.search(first) or WASTE_WORDS.search(first)):
            return None if NEVER_SLICE.search(heading) else ("never", None)
        return ("account", None) if ACCOUNT_CUE.search(first) or PERIOD_HEADER.match(first) else None
    # names after "including" or "plus", when that word comes after the number, are examples of what it covers
    cut = min([a + m.start() for m in LIST_MORE.finditer(sentence) if a + m.start() > start], default=len(line) + 1)
    in_clause = list(dict.fromkeys(n for s, _, n in named if lo <= s < hi and s < cut))
    in_sentence = list(dict.fromkeys(n for s, _, n in named if a <= s < b and s < cut))
    clause_union = any(lo <= s < hi for s, _, _ in unions)
    sentence_union = any(a <= s < b for s, _, _ in unions)

    def one(name):
        if base.get(name, {}).get("level") != "row" and (QUALIFIER.search(sentence) or _subset_noun(sentence)):
            return None  # "Search broad match", "water heater keywords ... broad": a slice of the match type
        return ("row", name)

    def together():
        if not here or groups != 1 or QUALIFIER.search(sentence) or LIST_MORE.search(sentence):
            return None  # a slice of these rows, a list that goes on past them, or two groups to choose from
        return ("group", GROUP)

    if _subset_noun(clause):
        return None
    if len(in_clause) == 1 and not clause_union:
        return one(in_clause[0])
    if in_clause or clause_union:
        return together()
    named_before = list(dict.fromkeys(n for s, _, n in named if s < a))
    if not in_sentence and ANAPHORA_START.search(sentence) and len(named_before) == 1:
        return one(named_before[0])
    if about in NEVER_METRICS and (NEVER.search(sentence) or WASTE_WORDS.search(sentence)):
        return None if NEVER_SLICE.search(sentence) or NEVER_SLICE.search(heading) else ("never", None)
    if UNNAMED.search(clause):
        return ("unnamed", None)
    if WHATIF.search(sentence) or TARGET.search(sentence) or _labelled(before):
        return None  # the sentence compares or forecasts, or the number has a label of its own we don't know
    if SUBSET.search(sentence) or _subset_noun(sentence) or (not here and (GROUP_WORDS.search(sentence)
                                                                            or _counted(sentence, start - a))):
        return None
    if UNNAMED.search(sentence):
        return ("unnamed", None)
    if len(in_sentence) == 1 and not sentence_union:
        return one(in_sentence[0])
    if in_sentence or sentence_union or (here and GROUP_CUE.search(sentence)):
        return together()
    return ("account", None)


def trace(text, facts):
    """Return (claims, contradictions) for every checkable number in the text."""
    facts = list(facts)
    entities = sorted({f.entity.lower() for f in facts if len(f.entity) >= 4}, key=len, reverse=True)
    all_entities = {f.entity.lower() for f in facts if f.entity}
    base, grand = _bases(facts)
    families = {w: sorted(e for e in base if e in MATCH_TYPES and e.startswith(w)) for w in ("broad", "exact", "phrase")}
    lines = text.splitlines()
    tables = _tables(lines)
    parsed = [_names(line, line.lower(), entities, all_entities, families) for line in lines]
    under = {}  # a heading's line -> the rows its numbers usually sum up: its first list, or its whole section
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            section, first, in_list, done, j = [], [], False, False, i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("#"):
                rows = [n for _, _, n in parsed[j][1] if n in base]
                section += rows
                if not done and LIST_LINE.match(lines[j]) and rows:
                    first, in_list = first + rows, True
                elif in_list and lines[j].strip() and not LIST_LINE.match(lines[j]):
                    done = True
                j += 1
            under[i] = [first, section]
    claims, history, block, carried, quiet, heading = [], [], [], set(), 0, ""
    for i, line in enumerate(lines):
        low = line.lower()
        if line.lstrip().startswith("#"):
            heading = low
        ents, named, unions = parsed[i]
        row = _row_name(line, all_entities)
        masked = _mask(low, ents)
        # "zero conversions" says which rows, not what a number is: "₹24,427 on nine zero-conversion terms" is a cost
        spans = _metric_spans(_mask(masked, [(m.start(), m.end(), "") for m in NEVER.finditer(masked)
                                             if not m.group(0)[0].isdigit()]))
        # the line with metric words, numbers and markup blanked: what is left before a number is its label, if any
        wordless = _mask(masked, [(sp[0], sp[1], "") for sp in spans]
                         + [(m.start(), m.end(), "") for m in NUM.finditer(masked)])
        skip = {m.start(1) for m in MONTH_DAY.finditer(line)}
        skip |= {p for m in CODE_SPAN.finditer(line) for p in range(m.start(), m.end())}
        marker = LIST_MARKER.match(line)
        if marker:
            skip.add(marker.start(1))
        names = {n for _, _, n in named}
        if row:  # a table row is about its first cell; its match type column is a description, not a subject
            names = {n for n in names if n not in MATCH_TYPES or n == row}
        implied = False
        if not names and ANAPHORA.search(low) and carried:
            names, implied = set(carried), True  # "This term generated 2 conversions": the row named just before
        numbers = [(m.start("cur") if m.group("cur") else m.start("num"), m.end()) for m in NUM.finditer(line)]
        partners = {}  # "from $45 to $58" and "60 of 85 conversions": one number may use its partner's words
        earlier = {m.start(1) for m in FROM_TO.finditer(masked)}  # "fell from 9%": a figure from before the export
        for m in FROM_TO.finditer(masked):
            partners[m.start(2)] = next((a for a, b in numbers if a <= m.start(1) < b), m.start(1))
        for m in OF_PAIR.finditer(masked):
            partners.setdefault(m.start(1), next((a for a, b in numbers if a <= m.start(2) < b), m.start(2)))
        for m in list(RANGE.finditer(masked)) + list(BETWEEN.finditer(masked)):
            partners.setdefault(m.start(1), next((a for a, b in numbers if a <= m.start(2) < b), m.start(2)))
            partners.setdefault(m.start(2), next((a for a, b in numbers if a <= m.start(1) < b), m.start(1)))
        # the rows each sentence takes together, and the figures they add up to
        sentences, pos = [], 0
        for cut in [m.start() for m in SENTENCE.finditer(line)] + [len(line)]:
            sentences.append((pos, cut))
            pos = cut
        ranges, settled = _ranges(line, masked, sentences, earlier), {}
        local, prev_rows = [], []
        for a, b in sentences:
            rows = [n for s, _, n in named if a <= s < b and n in base]
            sentence = low[a:b]
            group = rows if len(set(rows)) >= 2 else []
            if not group and GROUP_CUE.search(sentence):
                n = THESE_N.search(sentence)
                k = None
                if n:
                    w = n.group(1).lower()
                    k = WORD_NUM.get(w) or (int(w) if w.isdigit() else None)
                if k:  # "these four": the last four rows of one kind named before, or none at all
                    order = list(dict.fromkeys(reversed(history)))
                    for level in ("row", "group"):
                        same = [n for n in order if base.get(n, {}).get("level") == level]
                        if len(same) >= k:
                            group = same[:k]
                            break
                elif len(set(prev_rows)) >= 2:
                    group = prev_rows
                elif len(set(block)) >= 2:
                    group = block
            if not group and i in under and not rows:
                for cand in under[i]:
                    if len(set(cand)) >= 2:
                        local.append((a, b, _group_facts(cand, base, grand)))
            for s, e, members in unions:
                if a <= s < b:
                    local.append((a, b, _group_facts(members, base, grand)))
            if group:
                local.append((a, b, _group_facts(group, base, grand)))
            prev_rows = rows or prev_rows
        last = None  # the figure just before: a bare share in brackets after it is a share of it
        for m in NUM.finditer(line):
            pos = m.start("num")
            if pos in skip or any(s <= pos < e for s, e, _ in ents):
                continue
            raw, cur, mag, pct = m.group("num"), m.group("cur"), m.group("mag"), bool(m.group("pct"))
            code = m.group("code")
            value = float(_digits(raw)) * MAG.get((mag or "").strip().lower(), 1)
            money = bool(cur or code)
            plain = not (money or pct or mag)
            kind = "money" if money else ("pct" if pct else "plain")
            start = m.start("cur") if cur else pos
            rng = ranges.get(pos)
            if rng:
                kind = rng["kind"]  # "7-8%": the 7 is a percentage too
                money, plain = kind == "money", kind == "plain" and not mag
                if rng["id"] in settled:  # the range's other end: one claim, one verdict
                    a, b = next(((a, b) for a, b in sentences if a <= start < b), (0, len(line)))
                    claims.append(Claim(i + 1, m.group(0).strip(), value, *settled[rng["id"]],
                                        _quote(line, a, b, start, m.end())))
                    continue
            here = [f for a, b, fs in local if a <= start < b for f in fs]
            groups = sum(1 for a, b, fs in local if a <= start < b and fs)
            seen = names | ({GROUP} if here else set())
            cell = next((header for s, e, header in tables.get(i, []) if s <= start < e), None)
            side = None  # a table on its side: metrics down the first column, what they are of across the top
            if cell is not None and row is None and _header_metric(cell) in (None, "terms"):
                metric = _header_metric(line.strip().strip("|").split("|", 1)[0].strip(" *").lower())
                # the cell's own words come first: "| Leads | 85 (from 732 clicks) |"
                own = _evidence(masked, spans, start, m.end(), kind, [n for n in numbers if n[0] != start],
                                partners.get(pos), next(((s0, e0) for s0, e0, _ in tables[i] if s0 <= start < e0), None))
                if metric and not own:
                    side = (metric, _column(cell, entities, all_entities, families))
                    col = side[1]
                    if col and col[0] == "group":
                        here, groups, seen = _group_facts(col[1], base, grand), 1, {GROUP}
                    else:
                        seen = {col[1]} if col and col[0] == "row" else set()
            if plain and value <= 12 and not (side and side[0] in PERFORMANCE and seen) \
                    and not _small_count(line, m, cell, seen):
                continue
            if plain and "," not in raw and "." not in raw and 1900 <= value <= 2100:
                continue
            evidence = {}
            if side:
                if not (kind == "money" and side[0] not in MONEY_METRICS):
                    evidence = {side[0]: (0, 0)}
            elif cell is not None:
                metric = _header_metric(cell)
                if metric and not (kind == "money" and metric not in MONEY_METRICS):
                    evidence = {metric: (0, 0)}
            if not evidence:
                bounds = next(((a, b) for a, b in sentences if a <= start < b), None)
                others = [n for n in numbers if n[0] != start]
                if kind == "pct" and last and BRACKET_OPEN.fullmatch(line[last[0]:start]):
                    close = line.find(")", m.end())
                    evidence = _evidence(masked, spans, start, m.end(), kind, others, partners.get(pos),
                                         (start, close if close != -1 else len(line)))
                    if not evidence:  # "₹25,287 (17.5%)": a share of that cost; "113 clicks (15%)": of the clicks
                        evidence = {"cost": (0, 0)} if last[1] == "money" else dict(last[2])
                else:
                    evidence = _evidence(masked, spans, start, m.end(), kind, others, partners.get(pos), bounds)
            last = (m.end(), kind, evidence)
            judged = rng["mid"] if rng else value
            tol = rng["tol"] if rng else _tolerance(raw, mag, pct)
            if kind == "money" and judged >= 100:
                tol = max(tol, judged * 0.001)  # "₹1,087" for 1,086.48: a slip in the last digit, not a wrong figure
            about = min(evidence, key=evidence.get) if evidence else None
            loose = about == "cost" and kind == "money" and bool(COST_WORD.search(masked[max(0, start - 20):start]))
            verdict, detail = _judge(judged, tol, kind, evidence, seen, facts + here, implied and not here, loose)
            if verdict != "traced":
                a, b = next(((a, b) for a, b in sentences if a <= start < b), (0, len(line)))
                edges = [e.start() for e in CLAUSE_EDGE.finditer(masked)]
                lo = max([e for e in edges if e < start], default=a - 1) + 1
                if lo > 0 and masked[lo - 1] == "(":  # "pipe repair ($269.40, 38 clicks)": the row before it
                    lo = max([e for e in edges if e < lo - 1], default=a - 1) + 1
                hi = min([e for e in edges if e >= m.end()], default=len(line))
                lo, hi = max(lo, a), min(hi, b)
                anchored = bool(ACCOUNT_ANCHOR.search(masked[lo:start]))
                why = None if anchored else _cant_check(masked[lo:hi])  # names blanked: "free ... estimate" is a term
                if why:
                    verdict, detail = "can't check", why
                elif not anchored and detail.startswith("only a row the text doesn't name") and tol < 0.005 * judged:
                    verdict = "can't check"  # too exact to be chance: a real row's figure, under a name we don't know
                elif verdict == "not in data":
                    about = min(evidence, key=evidence.get) if evidence else None
                    if about is None:  # "We spent $1.4k, exactly $1,361.04, not $1,500": the sentence's one metric
                        said = {mt for s0, _, mt, _ in spans if a <= s0 < b and mt not in ("terms", "days")}
                        if len(said) == 1 and (kind != "money" or said <= MONEY_METRICS):
                            about = said.pop()
                    column = side and side[1] and (("group", GROUP) if side[1][0] == "group" else side[1])
                    subject = (("earlier", None) if pos in earlier else ("account", None) if anchored else
                               column if side else _subject(named, unions, row, here, implied, lo, hi, a, b, start, masked[a:b],
                                        masked[lo:hi], cell, line, base, about, groups, wordless[lo:start], heading))
                    verdict, detail = _settle(judged, kind, about, subject, facts + here, masked[a:b], detail)
            if rng:
                a, b = next(((a, b) for a, b in sentences if a <= start < b), (0, len(line)))
                why = _cant_check(masked[a:b]) if verdict == "traced" else None
                if why:  # a range is loose evidence: in a forecast or a target, never call it traced
                    verdict, detail = "can't check", why
                fact = next((f for f in facts + here if f.label == detail), None) if verdict == "traced" else None
                if fact:  # rows named together share the range: "X and Y show 9-14%" needs each inside it
                    fits = {}
                    for f in facts:  # a row is inside when its total or any of its rows is ("plumbing services" phrase)
                        if f.entity.lower() in seen and f.metric == fact.metric and f.kind == fact.kind:
                            fits.setdefault(f.entity.lower(), []).append(f)
                    outside = [fs[0] for fs in fits.values() if all(abs(f.value - judged) > tol for f in fs)]
                    if outside:
                        verdict, detail = "can't check", (f"the {outside[0].label} is {_show(outside[0])}, outside "
                                                          "this range: check which rows it covers")
                    else:
                        detail = f"the {fact.label} is {_show(fact)}, inside this range"
                settled[rng["id"]] = (verdict, detail)
            a, b = next(((a, b) for a, b in sentences if a <= start < b), (0, len(line)))
            claims.append(Claim(i + 1, m.group(0).strip(), value, verdict, detail, _quote(line, a, b, start, m.end())))
        rows_here = [n for _, _, n in named if n in base] + ([row] if row and row in base else [])
        if rows_here:
            history += rows_here
            block = (block if quiet == 0 else []) + rows_here
            carried = set(rows_here)
            quiet = 0
        elif line.strip():
            quiet += 1
    return claims, _contradictions(lines)


def _quote(line, a, b, start, end, width=200):
    """The sentence a number is in, cut to whole words around the number when it is longer than 200 characters."""
    text = line[a:b].strip()
    if len(text) <= width:
        return text
    lo = max(a, min(start - width // 2, b - width))
    hi = min(b, lo + width)
    lo = line.rfind(" ", a, lo + 1) + 1 if lo > a else a  # whole words only
    cut = line.find(" ", hi)
    hi = b if cut == -1 or cut >= b else cut
    return ("..." if lo > a else "") + line[lo:hi].strip() + ("..." if hi < b else "")


def _esc(text):
    return str(text).replace("|", "\\|")


# What each verdict is called wherever people read it. The codes stay as they are in claims and in the app's data.
VERDICT_LABEL = {"traced": "traced", "not in data": "wrong number", "mismatch": "wrong label", "can't check": "can't check"}


def render_check(claims, contradictions):
    traced = [c for c in claims if c.verdict == "traced"]
    flagged = sorted((c for c in claims if c.verdict in ("mismatch", "not in data")), key=lambda c: c.verdict != "not in data")
    unchecked = [c for c in claims if c.verdict == "can't check"]
    labels = sum(c.verdict == "mismatch" for c in claims)
    wrong = len(flagged) - labels
    n, bad = len(claims), len(contradictions)
    out = ["# Number check", "",
           f"**{n:,} {'number' if n == 1 else 'numbers'} found: {len(traced):,} traced to your data, "
           f"{wrong:,} {'wrong number' if wrong == 1 else 'wrong numbers'}, "
           f"{labels:,} {'wrong label' if labels == 1 else 'wrong labels'}"
           + (f", {len(unchecked):,} can't be checked from an export" if unchecked else "") + ".** "
           + f"{bad:,} {'sentence contradicts its' if bad == 1 else 'sentences contradict their'} own numbers."]
    if not flagged and not contradictions:
        out += ["", "Every number an export can confirm traces back to your data. That checks the numbers, "
                    "not the advice."]
    if flagged:
        out += ["", "## Needs attention", "", "| Line | As written | Verdict | Detail | Context |",
                "|---|---|---|---|---|"]
        out += [f"| {c.line} | {_esc(c.written)} | {VERDICT_LABEL[c.verdict]} | {_esc(c.detail)} | {_esc(c.context)} |"
                for c in flagged]
    if contradictions:
        out += ["", "## Contradictions", "", "| Line | Problem | Context |", "|---|---|---|"]
        out += [f"| {n} | {_esc(p)} | {_esc(ctx)} |" for n, p, ctx in contradictions]
    if unchecked:
        out += ["", "## Can't be checked from an export", "", "| Line | As written | Why | Context |",
                "|---|---|---|---|"]
        out += [f"| {c.line} | {_esc(c.written)} | {_esc(c.detail)} | {_esc(c.context)} |" for c in unchecked]
        out += ["", "_To check these, ask whoever wrote the audit to show, for each one, which rows of the export it "
                    "added up, divided or compared._"]
    if traced:
        out += ["", "## Traced", "", "| Line | As written | Traced to |", "|---|---|---|"]
        out += [f"| {c.line} | {_esc(c.written)} | {_esc(c.detail)} |" for c in traced]
    out += ["", "_A wrong number doesn't match your files: where it is clear what the figure is of, Detail gives the "
                "real one. It may also be rounded differently, about a row the text doesn't name, or from data you did "
                "not include. A wrong label is a real figure on the wrong metric or row. Can't be checked means it is "
                "a target, a forecast, a what-if, or the audit's own working over rows an export can't rebuild._"]
    return "\n".join(out)
