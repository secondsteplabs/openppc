"""The site audit report. Like every OpenPPC report, each number in it is registered as a fact first,
and the finished markdown is run through the number check before anyone sees it."""
from dataclasses import dataclass, field
from typing import Any

from openppc.engine.trace import trace
from openppc.facts import FactBook
from .checks import (
    CATEGORIES,
    CLS_GOOD,
    CLS_POOR,
    LCP_GOOD_MS,
    LCP_POOR_MS,
    RULES,
    SEVERITY_RANK,
    TBT_GOOD_MS,
    TBT_POOR_MS,
    TITLE_MAX_CHARS,
    Finding,
    code,
    events,
    home,
    tracking,
)
from .crawl import MAX_QUERY_VARIANTS, Crawl
from .crux import FORM_FACTOR, FieldData
from .crux import METRICS as CRUX_METRICS
from .lab.throttle import LOAD_CAP_MS, MOBILE
from .net import ROBOTS_TOKEN
from .render import AXE_VERSION, BLOCK_HITS, PROFILE, RENDER_FLAG, Rendered, Vitals
from .tags import VENDORS
from .tags import VERSION as SIGNATURES
from .triage import (
    FINGERPRINT,
    SCORE_HIGH,
    SCORE_LOW,
    SCORE_MEDIUM,
    Diff,
    Score,
    Suppressed,
    as_data,
    counted_elsewhere,
    fingerprint,
    grade,
    health,
    overall,
    redact_text,
    scores,
)

FIX_FIRST = 5
LEVELS = ("high", "medium", "low", "info")
NEEDS_BROWSER = [k for k, r in RULES.items()
                 if (r.category in ("accessibility", "performance") and not k.startswith("site-field-"))
                 or (r.category == "tracking" and k != "site-no-analytics") or k == "site-js-only-links"]
VITALS = (("lcp", "Largest Contentful Paint", "ms", LCP_GOOD_MS, LCP_POOR_MS, 0),
          ("cls", "Cumulative Layout Shift", "", CLS_GOOD, CLS_POOR, 3),
          ("tbt", "Total Blocking Time", "ms", TBT_GOOD_MS, TBT_POOR_MS, 0))
FIELD_NAMES = {"lcp": ("Largest Contentful Paint", "ms", 0), "inp": ("Interaction to Next Paint", "ms", 0),
               "cls": ("Cumulative Layout Shift", "", 2)}
BAR = 10  # characters in a score bar
WRONG_FINDING = "https://github.com/secondsteplabs/openppc/issues/new?template=wrong_finding.yml"
# what automated checks can't judge (WCAG success criteria in brackets), for a person to check by hand
MANUAL_CHECKS = (
    "Every link, button and form field can be reached and used with the keyboard alone, in a sensible order "
    "(`2.1.1`, `2.4.3`).",
    "The keyboard focus is always visible (`2.4.7`).",
    "Images' alt text says what the image is for, not just that it is there (`1.1.1`).",
    "Videos have captions and audio has a transcript (`1.2.2`, `1.2.1`).",
    "The page still works zoomed to twice its size, and on a narrow phone screen (`1.4.4`, `1.4.10`).",
    "Form errors say what went wrong and how to fix it (`3.3.1`, `3.3.3`).",
    "A screen reader (NVDA, VoiceOver) reads the main tasks in an order that makes sense (`1.3.2`).",
    "Nothing flashes, and moving content can be paused (`2.3.1`, `2.2.2`).",
)


@dataclass
class Extras:
    """What the CLI adds around the checks: rule pack files, suppressions, a baseline, field data."""
    config: list[str] = field(default_factory=list)
    suppressed: list[Suppressed] = field(default_factory=list)
    diff: Diff | None = None
    field_data: list[FieldData] = field(default_factory=list)


def _item(x: str) -> str:
    """URLs and host names as code spans: the digits in them are not claims."""
    return x if x.startswith("`") or ("/" not in x and "." not in x) else f"`{x}`"


def _units(count: str, unit: str) -> str:
    return f"{count} {unit[:-1] if count == '1' else unit}"


def _title(f: Finding) -> str:
    return f.title or f.about.title


def _ranked(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: -SEVERITY_RANK[f.level])  # stable: ties keep the checks' order


def _text_numbers(book: FactBook, text: str, label: str) -> None:
    """Numbers in text a user wrote (a rule pack's title, a suppression's reason) are theirs to claim."""
    claims, _ = trace(text, [])
    for value in {v for claim in claims for v in (claim.value, abs(claim.value))}:
        book.add(label, value, "count", "rule")
        book.add(label, value, "pct", "rule")


def _bar(score: int) -> str:
    full = round(score / (100 / BAR))
    return "█" * full + "░" * (BAR - full)


def _markdown(c: Crawl, r: Rendered | None, findings: list[Finding], extras: Extras, book: FactBook) -> list[str]:
    n = book.count
    book.add("title length limit", TITLE_MAX_CHARS, "count", "rule")  # in a rule's title
    for f in findings:
        if f.spec:
            _text_numbers(book, f.spec.title + " " + f.spec.fix, f"rule pack text of {f.id}")
    out = [f"# Site audit: `{c.origin}`", ""]
    levels = {lv: sum(f.level == lv for f in findings) for lv in LEVELS}
    checked = sum(x.status != -1 for x in c.external.values())
    out += [f"- **Pages fetched:** {n('pages fetched', len(c.pages))}",
            f"- **URLs listed in the sitemap:** {n('URLs in the sitemap', len(c.sitemap_urls))}",
            f"- **Links to other sites checked:** {n('external links checked', checked)}",
            "- **Findings:** " + ", ".join(f"{n(f'{lv} findings', k)} {lv}" for lv, k in levels.items())]
    if extras.config:
        out.append("- **Rule packs and config:** " + ", ".join(f"`{p}`" for p in extras.config))
    if c.allow_private:
        out += ["", "> Run with `--allow-private`: private network addresses were allowed."]
    if c.incomplete:
        out += ["", f"> The crawl is incomplete: it {c.incomplete}. Pages it didn't reach were not checked."]
    sick = health(c)
    if sick:
        out += ["", f"> Inconclusive: {sick}. The findings are what could be checked, and there are no scores; "
                    "with `--fail-on`, the exit code is `4`, not a pass."]
    if r:
        out += ["", f"Rendered {_units(n('pages rendered', len(r.pages)), 'pages')} in Chromium for tags, consent, "
                    "accessibility and Web Vitals."]
    else:
        out += ["", f"{n('checks that need a browser', len(NEEDS_BROWSER))} checks (tags firing, consent, "
                    f"accessibility, Web Vitals) need a browser: run again with {RENDER_FLAG}."]

    graded = {} if sick else scores(findings, r is not None)
    out += _scores(graded, book)
    out += _baseline(extras.diff, book)

    top = [f for f in _ranked(findings) if f.level != "info"][:FIX_FIRST]
    if top:
        out += ["", "## Fix first", ""]
        for i, f in enumerate(top, 1):
            rule = f.about
            out.append(f"{i}. **{_title(f)}** ({f.level}, {_units(n(_title(f), len(f.items)), rule.unit)}, "
                       f"effort {rule.effort}). {rule.fix}")

    cost = {f.id: p for s in graded.values() for f, p in s.lost}
    for cat, name in CATEGORIES.items():
        group = [f for f in _ranked(findings) if f.about.category == cat]
        if cat == "accessibility" and r:
            out += ["", f"## {name}", "", f"Checked with axe-core `{AXE_VERSION}` against WCAG A and AA. "
                    "Automated checks catch some accessibility problems, not all: a clean result is not "
                    "a compliance claim."]
            if not group:
                out += ["", "Nothing found."]
        elif group:
            out += ["", f"## {name}"]
        for f in group:
            rule = f.about
            costs = f", costs {n(f'points {f.id} costs', cost[f.id], 'rule')} points" if cost.get(f.id) else ""
            twin = counted_elsewhere(f, findings) if graded else None
            if twin:
                costs = f", no points here: {_title(twin).lower()} already costs them under SEO"
            out += ["", f"### {_title(f)}", "",
                    f"{f.level.capitalize()}, {_units(n(_title(f), len(f.items)), rule.unit)}, effort "
                    f"{rule.effort}{costs}. {rule.fix}", ""]
            for x in f.items:
                line = f"- {_item(x)}"
                ref = c.referrer.get(x) if rule.unit == "links" else None
                if ref:
                    line += f", linked from `{ref}`"
                if f.notes.get(x):
                    line += f": {f.notes[x]}"
                out.append(line)
        if cat == "accessibility" and r:
            out += ["", "### Check by hand", "", "Automated checks can't judge these; a person should:", ""]
            out += [f"- [ ] {x}" for x in MANUAL_CHECKS]

    out += _tracking_table(c, r)
    out += _vitals_tables(r, book)
    out += _field_table(extras.field_data, book)
    out += _suppressed(extras.suppressed, book)
    out += _crawl_notes(c, r, book)
    return out


def _scores(graded: dict[str, Score], book: FactBook) -> list[str]:
    if not graded:
        return []
    n = book.count
    out = ["", "## Scores", "",
           f"Each area starts at {n('perfect score', 100, 'rule')} and every finding in it costs points by "
           f"severity: high {n('points for a high finding', SCORE_HIGH, 'rule')}, medium "
           f"{n('points for a medium finding', SCORE_MEDIUM, 'rule')}, low "
           f"{n('points for a low finding', SCORE_LOW, 'rule')}, info none. Each finding below says what it cost.",
           "", "| Area | Score | Grade | |", "|---|---|---|---|"]
    for cat, s in graded.items():
        if s.score is None:
            out.append(f"| {CATEGORIES[cat]} | not scored | | {s.why_not} |")
        else:
            out.append(f"| {CATEGORIES[cat]} | {n(f'{cat} score', s.score)} | {s.grade} | {_bar(s.score)} |")
    mean = overall(graded)
    if mean is not None:
        out += ["", f"Overall: **{grade(mean)}**, the average of the scored areas "
                    f"({n('average score', mean, dp=0)})."]
    return out


def _baseline(diff: Diff | None, book: FactBook) -> list[str]:
    if diff is None:
        return []
    n = book.count
    new = sum(len(v) for v in diff.new.values())
    out = ["", "## Compared with the baseline", "",
           f"Against `{diff.file}`: {n('new since the baseline', new)} new, "
           f"{n('fixed since the baseline', len(diff.fixed))} fixed, "
           f"{n('unchanged since the baseline', diff.unchanged)} unchanged. With `--fail-on`, only new problems fail "
           "the run."]
    if diff.new:
        out += ["", "### New since the baseline", ""]
        out += [f"- `{fid}`: {_item(x)}" for fid, items in diff.new.items() for x in items]
    if diff.fixed:
        out += ["", "### Fixed since the baseline", ""]
        out += [f"- {code(title)}: {_item(x)}" for title, x in diff.fixed]
    return out


def _names(names: list[str]) -> str:
    return ", ".join(code(n).replace("|", "\\|") for n in names)


def _tracking_table(c: Crawl, r: Rendered | None) -> list[str]:
    tags = tracking(c, r)
    if not tags:
        return []
    yes = {True: "yes", False: "no"}
    out = ["", "## Tags found", ""]
    if r:
        sent = events(r)
        out += ["| Tag | In the HTML | Script loaded | Sent before consent | Consent Mode ping | Sent after consent "
                "| Events sent |", "|---|---|---|---|---|---|---|"]
        out += [f"| {VENDORS[v]['name']} | {yes[s['source']]} | {yes[s['loaded']]} | {yes[s['before']]} | "
                f"{yes[s['ping']]} | {yes[s['after']]} | {_names(sent.get(v, []))} |" for v, s in tags.items()]
        pushed = list(dict.fromkeys(e for o in r.pages for e in o.datalayer))
        if pushed:
            out += ["", f"Events the site pushed to the dataLayer: {_names(pushed)}."]
        observed = [o for o in r.pages if o.consent]
        if observed:
            o = observed[0]
            out += ["", f"Consent banner: `{o.consent}`, " + (f"accepted by clicking `{o.selector}`." if o.accepted
                                                             else "not accepted, so there is no after-consent data.")]
    else:
        out += [f"Found in the home page's HTML. Whether they fire, and when, needs {RENDER_FLAG}.", ""]
        out += [f"- {VENDORS[v]['name']}" for v in tags]
    return out


def _vitals_tables(r: Rendered | None, book: FactBook) -> list[str]:
    if not r or not r.vitals:
        return []
    for label, setting in (("lab phone width", MOBILE.width), ("lab phone height", MOBILE.height),
                           ("lab latency ms", MOBILE.latency_ms), ("lab Mbps down", round(MOBILE.down_kbps / 1024, 2))):
        book.add(label, setting, "count", "rule")
    out = ["", "## Web Vitals (lab)", "", f"{PROFILE[0].upper() + PROFILE[1:]}. Lab numbers show what to fix; real "
           "visitors' numbers (from Chrome's field data, `--crux`) can differ. Interaction to Next Paint needs "
           "real clicks, so it isn't measured; Total Blocking Time is its lab stand-in."]
    if BLOCK_HITS:
        out += ["", "During these loads, tag hits (analytics and ad pixels reporting a visit) were answered on this "
                    "computer, so measuring sends no visits to the site's analytics or ad accounts; the tags themselves "
                    "still load. The tags and consent pass above was a real visit."]
    for v in r.vitals:
        out += _vitals_one(v, book)
    return out


def _vitals_one(v: Vitals, book: FactBook) -> list[str]:
    if not v.runs:
        return ["", f"`{v.url}` couldn't be measured: {code(v.error or 'no load finished')}"]
    out = ["", f"### `{v.url}`", "", f"The median of {book.count(f'Web Vitals runs on {v.url}', len(v.runs))} loads."]
    if v.error:
        out += ["", f"A run failed: {code(v.error)}"]
    if v.hits_answered:
        out += ["", f"Tag hits answered on this computer: {book.count(f'tag hits answered on {v.url}', v.hits_answered)}."]
    if v.capped:
        out += ["", f"{book.count(f'loads still going at the cap on {v.url}', v.capped)} of them hadn't finished "
                    f"loading after {book.count('load cap seconds', LOAD_CAP_MS / 1000, 'rule')} seconds, so they "
                    "were measured as they were then, as Lighthouse does."]
    out += ["", "| Measure | Median | Good up to | Poor above |", "|---|---|---|---|"]
    median = v.median
    for key, name, unit, good, poor, dp in VITALS:
        value = median[key]
        cells = ["not measured" if value is None else book.count(f"median {name} (lab) on {v.url}", value, dp=dp),
                 book.count(f"{name} good line", good, "rule", dp=dp),
                 book.count(f"{name} poor line", poor, "rule", dp=dp)]
        out.append(f"| {name} | " + " | ".join(f"{x} {unit}".strip() if x != "not measured" else x for x in cells)
                   + " |")
    d = v.details
    slows = []
    if d.get("lcp_element"):
        slows.append(f"- The largest element is {code(d['lcp_element'])}"
                     + (f", loaded from `{d['lcp_url']}`" if d.get("lcp_url") else "") + ".")
    if d.get("blocking"):
        slows.append("- Files that block the first paint: " + ", ".join(f"`{u}`" for u in d["blocking"]) + ".")
    if d.get("heavy"):
        slows.append("- The largest files: " + ", ".join(
            f"`{u}` ({book.count(f'size of {u} in KB', size / 1024)} KB)" for u, size in d["heavy"]) + ".")
    if slows:
        out += ["", "What slows it down, from the first load:", ""] + slows
    return out


def _field_table(data: list[FieldData], book: FactBook) -> list[str]:
    if not data:
        return []
    n = book.count
    out = ["", "## Real visitors (Chrome UX Report)", ""]
    shown = [d for d in data if d.p75]
    if shown:
        period = next((d.period for d in shown if d.period), "")
        out += [f"Chrome's field data for {FORM_FACTOR.lower()} visitors" + (f", `{period}`" if period else "")
                + ": the value three visits in four beat (p75). These are the numbers Google's ranking signal uses.",
                "", "| Measure | " + " | ".join("Whole site" if d.origin else f"`{d.target}`" for d in shown)
                + " | Good up to | Poor above |", "|---|" + "---|" * (len(shown) + 2)]
        for short, good, poor in CRUX_METRICS.values():
            label, unit, dp = FIELD_NAMES[short]
            cells = [f"{n(f'p75 {label} for {d.target}', d.p75[short], dp=dp)} {unit}".strip() if short in d.p75
                     else "no data" for d in shown]
            cells += [f"{n(f'{label} field good line', good, 'rule', dp=dp)} {unit}".strip(),
                      f"{n(f'{label} field poor line', poor, 'rule', dp=dp)} {unit}".strip()]
            out.append(f"| {label} | " + " | ".join(cells) + " |")
    out += [f"- {'Whole site' if d.origin else f'`{d.target}`'}: {d.error}." for d in data if d.error]
    return out


def _suppressed(used: list[Suppressed], book: FactBook) -> list[str]:
    if not used:
        return []
    out = ["", "## Suppressed", "", "Hidden on purpose by a config file, each with its reason:", ""]
    for s in used:
        _text_numbers(book, s.rule.reason, "suppression reason")
        what = f"`{s.rule.rule}`" + (f" on `{s.rule.match}`" if s.rule.match else "")
        hidden = (f"hid {_units(book.count(f'items hidden by {s.rule.rule} {s.rule.match}', len(s.items)), 'items')}"
                  if s.items else "matched nothing, so it can go")
        out.append(f"- {what} ({hidden}, from `{s.rule.source}`): {s.rule.reason}")
    return out


def _crawl_notes(c: Crawl, r: Rendered | None, book: FactBook) -> list[str]:
    n = book.count
    host = c.origin.split("://", 1)[1]
    out = ["", "## About this crawl", "",
           f"- Fetched the start page, then the sitemap's URLs, then links breadth-first, on `{host}` only, "
           f"obeying robots.txt as `{ROBOTS_TOKEN}`. Tag signatures `{SIGNATURES}`."]
    if c.robots_blocked:
        out.append(f"- {n('URLs robots.txt blocks', len(c.robots_blocked))} URLs were not fetched because "
                   "robots.txt disallows them.")
    if c.skipped:
        out.append(f"- {n('URLs skipped by the caps', sum(c.skipped.values()))} URLs were skipped: their pattern "
                   f"already had enough pages (`--max-per-pattern`; `0` lifts it), or their path already had "
                   f"{MAX_QUERY_VARIANTS} versions with different query strings:")
        out += [f"  - `{p}`: {n(f'URLs skipped at {p}', k, entity=p)}" for p, k in c.skipped.most_common()]
    refused = [u for u, x in c.external.items() if x.refused]
    if refused:
        out.append(f"- {n('links to private addresses', len(refused))} links point at private or local "
                   "addresses and were not checked.")
    out += [f"- Sitemap problem: {code(e)}" for e in c.sitemap_errors if c.sitemap_files]
    if not c.allowed(c.origin + "/llms.txt"):
        out.append("- `/llms.txt`: not checked, because robots.txt disallows it.")
    else:
        out.append("- `/llms.txt`: " + ("found." if c.llms_txt else "not found (optional; a few AI tools read it)."))
    if r:
        out += [f"- Rendering `{o.url}` failed: {code(o.error)}" for o in r.pages if o.error]
        out += [f"- Screenshot of `{o.url}` as first loaded: `{o.screenshot}`" for o in r.pages if o.screenshot]
        if r.refused:
            out.append(f"- The browser was stopped from reaching {n('hosts refused to the browser', len(r.refused))} "
                       "hosts on private or local addresses: " + ", ".join(f"`{h}`" for h in r.refused) + ".")
    out.append(f"- Finding ids and fingerprints (recipe `{FINGERPRINT}`) stay the same from run to run, for "
               "`--baseline` and suppressions. A finding that's wrong? Report it: " + WRONG_FINDING)
    return out


def report(c: Crawl, r: Rendered | None, findings: list[Finding],
           extras: Extras | None = None) -> tuple[str, FactBook, bool]:
    """(markdown, its facts, whether it passed its own number check). Secret-looking URL values are masked."""
    book = FactBook()
    markdown = "\n".join(_markdown(c, r, findings, extras or Extras(), book))
    markdown, masked = redact_text(markdown)
    if masked:
        markdown += ("\n- Secret-looking values in URL query strings (`token=`, `session=`, `email=` and the like) "
                     "are shown as `REDACTED`.")
    claims, contradictions = trace(markdown, book.facts)
    passed = all(x.verdict == "traced" for x in claims) and not contradictions
    markdown += "\n\n---\n\n" + (
        "Number check: every number in this report traces back to the crawl."
        if passed else
        "Number check FAILED: this report contains a number the checker could not trace. "
        "That is a bug in OpenPPC, please report it.")
    return markdown, book, passed


def _vitals_data(v: Vitals) -> dict[str, Any]:
    return {"url": v.url, "profile": PROFILE, "runs": v.runs, "median": v.median, "error": v.error,
            "details": v.details, "capped": v.capped, "hits_answered": v.hits_answered}


def data(c: Crawl, r: Rendered | None, findings: list[Finding], extras: Extras | None = None) -> dict[str, Any]:
    """The audit as data, for --format json. The CLI masks secret-looking URL values in it."""
    x = extras or Extras()
    sick = health(c)
    graded = {} if sick else scores(findings, r is not None)
    mean = overall(graded)
    return {
        "site": c.origin, "start": c.start, "allow_private": c.allow_private, "incomplete": c.incomplete,
        "inconclusive": sick, "seconds": round(c.seconds, 1), "signatures": SIGNATURES,
        "fingerprint_recipe": FINGERPRINT, "config": x.config,
        "findings": [{"id": f.id, "rule": f.rule, "category": f.about.category, "severity": f.level,
                      "effort": f.about.effort, "title": _title(f), "unit": f.about.unit, "fix": f.about.fix,
                      "custom": f.spec is not None, "fingerprint": fingerprint(f.id),
                      "items": f.items, "notes": f.notes} for f in findings],
        "scores": as_data(graded), "overall": None if mean is None else {"score": round(mean), "grade": grade(mean)},
        "suppressed": [{"rule": s.rule.rule, "match": s.rule.match, "reason": s.rule.reason, "source": s.rule.source,
                        "hidden": [{"finding": fid, "item": item} for fid, item in s.items]} for s in x.suppressed],
        "baseline": None if x.diff is None else {
            "file": x.diff.file, "new": x.diff.new, "unchanged": x.diff.unchanged,
            "fixed": [{"title": t, "item": i} for t, i in x.diff.fixed]},
        "field_data": [{"target": d.target, "origin": d.origin, "p75": d.p75, "period": d.period, "error": d.error}
                       for d in x.field_data],
        "pages": [{"url": p.url, "status": p.status, "final_url": p.resp.final_url, "depth": p.depth,
                   "linked_from": c.referrer.get(p.url, "")} for p in c.pages.values()],
        "home": home(c).url,
        "sitemap": {"files": c.sitemap_files, "urls": len(c.sitemap_urls), "errors": c.sitemap_errors},
        "robots_blocked": sorted(c.robots_blocked), "skipped": dict(c.skipped), "llms_txt": c.llms_txt,
        "tags": tracking(c, r), "events": events(r),
        "rendered": None if not r else {
            "pages": [{"url": o.url, "error": o.error, "consent": o.consent, "accepted": o.accepted,
                       "tcf": o.tcf, "consent_mode": o.consent_mode, "screenshot": o.screenshot,
                       "events": o.events, "datalayer": o.datalayer} for o in r.pages],
            "vitals": [_vitals_data(v) for v in r.vitals],
            "refused": r.refused},
    }


def sarif(c: Crawl, findings: list[Finding], version: str) -> dict[str, Any]:
    """The findings as SARIF 2.1.0, one result per item, located at the page's URL where there is one."""
    level = {"high": "error", "medium": "warning", "low": "note", "info": "note"}
    rules: dict[str, Finding] = {}
    for f in findings:
        rules.setdefault(f.id, f)
    results = []
    for f in findings:
        for item in f.items:
            target = item.strip("`")
            result: dict[str, Any] = {
                "ruleId": f.id, "level": level[f.level],
                "message": {"text": f"{_title(f)}: {target}" + (f" ({f.notes[item]})" if f.notes.get(item) else "")},
                "partialFingerprints": {f"openppcSite/{FINGERPRINT}": fingerprint(f.id, item)}}
            if target.startswith(("http://", "https://")):
                result["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": target}}}]
            results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
        "runs": [{"tool": {"driver": {
            "name": "OpenPPC site audit", "version": version, "informationUri": "https://openppc.si",
            "rules": [{"id": fid, "name": fid, "shortDescription": {"text": _title(f)},
                       "help": {"text": f.about.fix},
                       "properties": {"category": f.about.category, "severity": f.level, "effort": f.about.effort},
                       "defaultConfiguration": {"level": level[f.level]}} for fid, f in rules.items()]}},
            "originalUriBaseIds": {"SITE": {"uri": c.origin + "/"}},
            "results": results}],
    }
