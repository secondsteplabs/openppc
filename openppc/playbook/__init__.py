"""The Playbook: how to fix each finding in an OpenPPC audit.

A separate app on top of the audits. It reads what an audit found (`book.findings`, sentences the report already
printed) and pairs each finding with a guide in `guides/`: why it matters, the steps in Google Ads, what to check
first and how to tell it worked. It never computes a number and never changes how an audit computes one, so
everything it prints is either a sentence from the audit or advice that cites its rulebook rules and sources.

    from openppc.playbook import fix_plan
    print(fix_plan("search-term-waste", "exports/search_terms.csv", brand="Acme"))
"""
import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent
GUIDES = HERE / "guides"
SOURCES = (HERE / "sources.csv", HERE.parent.parent / "rulebook" / "sources.csv")  # the wheel's copy, then a clone's


@dataclass(frozen=True)
class Guide:
    id: str
    template: str
    finding: str
    rules: tuple
    sources: tuple
    title: str
    body: str  # markdown after the title, with {found} where the audit's sentence goes


def _parse(path):
    _, head, text = path.read_text(encoding="utf-8").split("---", 2)
    meta = dict(line.split(": ", 1) for line in head.strip().splitlines())
    title, _, body = text.strip().partition("\n")
    split = lambda value: tuple(x.strip() for x in value.split(",") if x.strip())
    return Guide(meta["id"], meta["template"], meta["finding"], split(meta["rules"]), split(meta["sources"]),
                 title.lstrip("# ").strip(), body.strip())


@lru_cache(maxsize=1)
def guides():
    """Every guide, by id."""
    return {g.id: g for g in map(_parse, sorted(GUIDES.glob("*.md")))}


@lru_cache(maxsize=1)
def sources():
    """The rulebook's sources, by id: {"title", "publisher", "url"}."""
    path = next((p for p in SOURCES if p.exists()), None)
    if path is None:
        return {}
    with path.open(encoding="utf-8") as f:
        return {r["source_id"]: r for r in csv.DictReader(f)}


def fixes(findings):
    """Pair an audit's findings with their guides: [(guide, [what the audit found, ...])], in the audit's order, one
    entry per guide however many findings it covers. Findings with no guide are skipped."""
    order, found = [], {}
    for f in findings:
        if f["guide"] in guides():
            if f["guide"] not in found:
                order.append(f["guide"])
                found[f["guide"]] = []
            found[f["guide"]].append(f["found"])
    return [(guides()[g], found[g]) for g in order]


def _cite(source_id):
    s = sources().get(source_id)
    if not s:
        return f"- {source_id}"
    name = f"{s['title']} ({s['publisher']})" if s.get("publisher") else s["title"]
    return f"- [{name}]({s['url']})" if s.get("url") else f"- {name}"


def render(findings, title="Fix plan"):
    """The fix plan as markdown: one section per guide, opening with what the audit found."""
    pairs = fixes(findings)
    if not pairs:
        return f"# {title}\n\nThe audit found nothing the Playbook has a guide for. Nothing to fix here.\n"
    out = [f"# {title}", "",
           "_From the OpenPPC Playbook. Every number below is quoted from the audit; the steps cite the rules and "
           "sources they come from. OpenPPC never changes your account: you make each change in Google Ads._"]
    for n, (guide, found) in enumerate(pairs, 1):
        body = guide.body.replace("{found}", " ".join(found))
        out += ["", f"## {n}. {guide.title}", "", _demote(body), "", "**Sources:**"]
        out += [_cite(s) for s in guide.sources]
        out.append(f"\n_Rules: {', '.join(f'`{r}`' for r in guide.rules)}_")
    return "\n".join(out) + "\n"


def _demote(markdown):
    """A guide's own ## headings become ### inside the fix plan, under the guide's numbered title."""
    return "\n".join("#" + line if line.startswith("## ") else line for line in markdown.splitlines())


def fix_plan(template, path, **params):
    """Run an audit template on an export and return its fix plan as markdown."""
    from ..templates import TEMPLATES, run_template_book
    _, book, _ = run_template_book(template, path, **params)
    return render(book.findings, f"Fix plan: {TEMPLATES[template].TITLE}")
