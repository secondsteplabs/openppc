"""The checker's core metric, measured: how often it flags a made-up number (recall) and how
often a flag is right (precision), on a labeled corpus of real and fabricated claims.

The corpus is generated from the 120-row fixture with a fixed seed: real claims quote a row's own
figures, fabricated ones change a figure or pin it on the wrong metric. A fabricated number can
still match some other row by coincidence (README: "a number can match one by coincidence"), which
is exactly what recall measures. The floors sit just under today's scores, so a change that makes
the checker more gullible fails here.
"""
import random
from pathlib import Path

from openppc.checkfacts import facts_for_paths
from openppc.engine.trace import trace
from openppc.ingest import load_report

EXPORT = Path(__file__).parent / "fixtures" / "search_terms_fractional.csv"
MIN_RECALL = 0.95      # measured 0.964 on 680 claims when set (0.1.11)
MIN_PRECISION = 0.99   # measured 1.000 when set


def corpus(rows, seed=4_1):
    """[(sentence, label)], label "real" or "fake", one checkable number per sentence."""
    rng = random.Random(seed)
    out = []
    for r in rows:
        term, cost, clicks, conv = r["search_term"], r["cost"], int(r["clicks"]), r["conversions"]
        out.append((f'The search term "{term}" cost ${cost:,.2f}.', "real"))
        if clicks > 12:
            out.append((f'"{term}" got {clicks} clicks.', "real"))
        fake = round(cost * rng.uniform(1.15, 3.0), 2)
        out.append((f'The search term "{term}" cost ${fake:,.2f}.', "fake"))
        if clicks > 12 and clicks != conv:
            out.append((f'"{term}" drove {clicks} conversions.', "fake"))
        # naming no row is where coincidences live (review 4.1): any row's figure can match
        out.append((f"One search term cost ${cost:,.2f}.", "real"))
        out.append((f"One search term cost about ${round(fake):,}.", "fake"))
    total = sum(r["cost"] for r in rows)
    out += [(f"In total the account spent ${total:,.2f}.", "real"),
            (f"In total the account spent ${total * 1.08:,.2f}.", "fake")]
    return out


def test_the_checker_flags_made_up_numbers_and_trusts_real_ones():
    report = load_report(EXPORT)
    facts = facts_for_paths([EXPORT])
    labeled = corpus(report.rows)
    text = "\n".join(s for s, _ in labeled)
    claims, _ = trace(text, facts)
    verdict = {c.line: c.verdict for c in claims}
    assert len(verdict) == len(labeled), "every sentence holds exactly one checkable number"
    # a sentence naming no row is "can't check" whether its figure is real or not: neither flagged nor trusted
    checkable = {n for n, v in verdict.items() if v != "can't check"}
    flagged = {n for n in checkable if verdict[n] != "traced"}
    fake = {n for n, (_, label) in enumerate(labeled, 1) if label == "fake" and n in checkable}
    recall = len(flagged & fake) / len(fake)
    precision = len(flagged & fake) / len(flagged) if flagged else 1.0
    print(f"checker accuracy on {len(labeled)} claims: recall {recall:.3f}, precision {precision:.3f}")
    assert recall >= MIN_RECALL, f"recall {recall:.3f} fell under {MIN_RECALL}"
    assert precision >= MIN_PRECISION, f"precision {precision:.3f} fell under {MIN_PRECISION}"
