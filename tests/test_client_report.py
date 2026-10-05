"""The branded client report: its pages say only what the audit computed, and the app can check them."""
import datetime as dt
import hashlib
import json
from pathlib import Path

from openppc import webapi
from openppc.engine.trace import trace
from openppc.ingest.google_ads_csv import Report
from openppc.templates import run_template_book, search_term_waste

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "examples" / "search_terms_acme.csv"


def page_lines(client):
    """The text of the client pages, one line per row, the way the laid-out page reads."""
    h = client["headline"]
    out = [" ".join(filter(None, [h["value"], h["text"]]))] + [f"{s['value']} {s['label']}" for s in h["stats"]]
    for sec in client["sections"]:
        out.append(sec["title"])
        for b in sec["blocks"]:
            t = b["type"]
            if t == "lead":
                out.append(" ".join(filter(None, [b["strong"], b["text"]])))
            elif t in ("p", "note", "h2"):
                out.append(b["text"])
            elif t == "bars":
                out += [b["title"]] + [f"{r['label']} | {r['value']} | {r['tag']}" for r in b["rows"]] + [b["caption"]]
            elif t == "table":
                out += [" | ".join(r) for r in b["rows"]]
            elif t == "stats":
                out += [b["title"]] + [f"{i['value']} {i['label']}" for i in b["items"]]
            elif t == "step":
                out += [b["title"], b["text"]] + [" | ".join(r) for r in (b.get("table") or {}).get("rows", [])]
            elif t == "compare":
                out += [b["name"], b["read"], f"Yours {b['yours']}", f"Industry average {b['average']}"]
            elif t == "list":
                out += b["items"]
    return "\n".join(out)


def passes(client, book):
    claims, contradictions = trace(page_lines(client), book.facts)
    untraced = [(c.written, c.verdict, c.context) for c in claims if c.verdict != "traced"]
    assert not untraced and not contradictions, untraced
    return len(claims)


def _row(term, cost, clicks, conversions=0):
    return {"search_term": term, "match_type": "Broad match", "campaign_type": "Search", "clicks": clicks,
            "impressions": clicks * 10, "cost": cost, "conversions": conversions}


def _client(rows, **params):
    report = Report(rows=rows, columns={"search_term", "match_type", "campaign_type", "clicks", "impressions", "cost",
                                        "conversions"},
                    source="test.csv", start=dt.date(2026, 7, 1), end=dt.date(2026, 7, 30), currency="USD")
    _, book = search_term_waste.run(report, **params)
    passes(book.client, book)
    return book.client


def test_the_sample_client_report_passes_the_number_check():
    _, book, _ = run_template_book("search-term-waste", str(SAMPLE), industry="home-services")
    client = book.client
    assert passes(client, book) >= 50
    assert [s["id"] for s in client["sections"]] == ["found", "recommend", "benchmarks", "method"]
    assert client["headline"]["value"] == "$767.20" and client["period"] == "July 1 to July 31, 2026"
    assert client["month"] == "July 2026" and client["title"] == "Search-term review"
    steps = [b for b in client["sections"][1]["blocks"] if b["type"] == "step"]
    assert [(s["tag"], s["n"]) for s in steps] == [("Watch", 1), ("Review", 2), ("Grow", 3)]
    method = client["sections"][3]["blocks"]
    sha = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    assert {"type": "fingerprint", "value": sha} in method and method[-1]["type"] == "check"


def test_no_industry_means_no_comparison_page():
    _, book, _ = run_template_book("search-term-waste", str(SAMPLE))
    assert [s["id"] for s in book.client["sections"]] == ["found", "recommend", "method"]


def test_a_proven_term_becomes_a_block_step():
    rows = [_row("plumbing repair", 900.0, 300, 45), _row("drain cleaning", 400.0, 100, 25), _row("pipe repair", 200.0, 50, 12),
            _row("leak detection", 300.0, 80, 2), _row("water heater install", 250.0, 60, 1),
            _row("free plumbing course", 240.0, 150, 0), _row("plumber salary", 30.0, 4, 0), _row("pvc glue", 25.0, 3, 0)]
    client = _client(rows)
    first = next(b for b in client["sections"][1]["blocks"] if b["type"] == "step")
    assert (first["tag"], first["title"]) == ("Block", "Add 1 negative keyword")
    bars = next(b for b in client["sections"][0]["blocks"] if b["type"] == "bars")
    assert [r["strong"] for r in bars["rows"]] == [True, False, False]


def test_an_account_whose_terms_convert_alike_is_told_so():
    rows = [_row(f"plumbing service {i}", 50.0, 100, 10) for i in range(40)] + [_row("plumber near me", 60.0, 25, 0)]
    client = _client(rows)
    text = page_lines(client)
    assert "convert at much the same rate" in text and "Watch the 1 term before adding negatives" in text


def test_a_long_waste_list_is_summed_up_not_dropped():
    rows = [_row("plumbing repair", 900.0, 300, 45)] + [_row(f"diy fix number {i}", 30.0 + i, 3) for i in range(30)]
    client = _client(rows, top=25)
    found = client["sections"][0]["blocks"]
    bars = next(b for b in found if b["type"] == "bars")
    assert len(bars["rows"]) == 25 and any(b["type"] == "note" and b["text"].startswith("Plus 5 more terms") for b in found)


def test_the_app_can_check_the_finished_pdf():
    res = json.loads(webapi.audit("search-term-waste", str(SAMPLE), "home-services"))
    text = page_lines(res["client"]) + "\nPrepared for Plumbing 24/7 by Harbor Lane Digital"
    ok = json.loads(webapi.verify(res["token"], text, json.dumps(["Plumbing 24/7", "Harbor Lane Digital"])))
    assert ok["ok"] and ok["total"] >= 50 and ok["traced"] == ok["total"] and ok["problems"] == []
    typed = json.loads(webapi.verify(res["token"], text + "\nWe saved you $4,200.", "[]"))
    assert {p["written"] for p in typed["problems"]} == {"24", "$4,200"}  # a typed name is only safe when set aside
    assert not json.loads(webapi.verify("audit-missing", text))["ok"]
