<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/secondsteplabs/openppc/main/brand/png/openppc-logo-reverse-1600.png">
    <img alt="OpenPPC" src="https://raw.githubusercontent.com/secondsteplabs/openppc/main/brand/png/openppc-logo-1600.png" width="340">
  </picture>
</h1>

Read-only Google Ads audits where every number is traced back to your own export. For PPC freelancers and agencies who use AI on client accounts but won't hand it the keys, or trust its math.

## Why

AI will happily audit a Google Ads account. When we tested language models on real accounts, they read trends backwards and invented dollar figures, even after fine-tuning. So this tool splits the job: code computes every number, and a checker traces each figure in the report back to your data. It never connects to your account, never changes anything, and makes no network calls.

## Two things it does

**Audit.** Run a template on a report you exported from Google Ads. You get a markdown report where every figure is computed from your file, and the report checks itself before you see it.

**Check.** Point it at any audit, from ChatGPT, Claude, a colleague or another tool, plus your export. Every number comes back marked:

- **traced**: it matches your data, at the precision it was written
- **mismatch**: right number, wrong metric or row ("22 conversions" when 22 is that search term's clicks)
- **not in data**: nothing in your files produces it, and the flag says what the figure really is ("no: the cost of
  'pipe repair' is 296.40")
- **can't check**: a target, threshold, forecast or what-if, or the audit's own working over rows an export can't
  rebuild (brand against non-brand, "the other $3,690"). Listed apart with a prompt to ask for the working, never
  counted against the audit

A number is only flagged when the checker knows what it claims to be: a row or match type the text names, the rows it
names together, the terms that never converted, or the whole account. Anything else it can't confirm is "can't check",
because calling the audit's own arithmetic wrong would be a guess.

Besides each row and the account totals, it checks what audits usually work out: the sums, rates and shares of the
rows a sentence names together, of a match type ("broad", "exact/phrase") and of the rows under a heading. It also
flags sentences that contradict their own numbers ("fell from 9% to 14%").

## Quick start

```bash
git clone https://github.com/secondsteplabs/openppc
cd openppc
uv venv && uv pip install -e .

openppc audit search-term-waste examples/search_terms_acme.csv --industry home-services
openppc check --audit examples/ai_audit_sample.md --data examples/search_terms_acme.csv
```

The examples are synthetic, so this runs with no account and no API keys. For your own data, export a report from Google Ads and put it in `exports/`, which git ignores.

## Run it in your browser

The web app in `web/` runs the same engine inside the browser tab (Python compiled to WebAssembly with [Pyodide](https://pyodide.org)). Your export and the audit stay on your machine: the page's security policy only lets it download its runtime, libraries and fonts from one pinned CDN (each checked against a fingerprint), so it has no way to send your files anywhere.

```bash
python3 -m http.server 8765 --directory web
# open http://localhost:8765 and click "Try the sample account"
```

What it has:

- **Check**: paste any AI's audit next to the export it was written from, and see each number traced, mismatched or not in your data.
- **Audit**: run a free template on your export. The search-term waste audit comes back as cards: the headline numbers, what to do, and the wasted terms with the chance each one is bad, ready to copy as exact-match negatives or download as a .csv.
- **Templates**: every free template, with a link to its code.
- **Branded PDF**: a client-ready report under your agency's name, logo and brand color: a cover with the headline, then what we found, what we recommend, how the account compares with its industry, and how the report was made (the export's name, dates and SHA-256 fingerprint). Pages are laid out at Letter or A4 size exactly as they print: a block that does not fit moves to the next page, and long tables continue there under their own header, so nothing is cut. Before you can save, the checker reads the text of every page and confirms each number traces to the export. Save it from the browser's print dialog (Chrome and Edge keep the layout exactly). The logo stays in the browser.
- **Rules** (coming soon): turn a rulebook rule into a Google Ads Script you install yourself. Nothing is built for it yet.

The first visit downloads about 12 MB of runtime, which your browser then keeps. After changing anything in `openppc/` or `examples/`, rebuild the bundle the page loads (a test fails if you forget):

```bash
python tools/build_web.py
```

## Website

The site at [openppc.si](https://openppc.si) is built from `site/` together with the app, which it serves at `/app/`:

```bash
python tools/build_site.py
python3 -m http.server 8766 --directory dist
```

Pages are HTML fragments in `site/pages/` wrapped in `site/layout.html`. The build fails on any broken internal link, and the pages load nothing from other sites.

## Templates

| Template | Reads | You get |
|---|---|---|
| `search-term-waste` | Search terms report (.csv) | Zero-conversion search terms ranked by cost (Search and Performance Max apart), each with the chance it is genuinely bad, the words behind the long tail, expensive converters, terms worth adding as keywords |
| `keyword-audit` | Keywords report (.csv) | Keywords spending without converting, budget by match type, spend on low Quality Scores |
| `account-structure` | Account snapshot (.json); Google Ads Editor export next | How the account is built: broad match without Smart Bidding, brand mixed with non-brand, duplicate keywords, negatives that block your own keywords, thin or pinned ads, missing sitelinks, retired bidding. Where Google and practitioners disagree, it shows both |
| `account-read` | Two-period totals (.json) | What changed and why it matters: efficiency win, over-expansion, broken tracking and more |

Add `--industry` to compare against published industry averages. `openppc industries` lists them.

Add `--brand "Your Brand, Short Name"` so brand searches, and close misspellings of them, are never flagged as waste or suggested as negatives:

```bash
openppc audit search-term-waste exports/search_terms.csv --brand "Acme Plumbing, Acme"
```

Premium templates are planned as a paid add-on: a full account audit, Performance Max, a branded client-ready PDF, and multi-account triage. Everything in this repository stays free under the MIT license.

## Use it inside Claude, Cursor and ChatGPT

OpenPPC is an MCP server: your assistant writes the words, and OpenPPC computes and checks the numbers.

**On your computer** (Claude Code, Claude Desktop, Cursor). It reads your exports where they are:

```bash
claude mcp add openppc -- uvx --from "openppc[mcp] @ git+https://github.com/secondsteplabs/openppc" openppc-mcp
```

For Claude Desktop or Cursor, add the same server to `claude_desktop_config.json` or `~/.cursor/mcp.json`:

```json
{ "mcpServers": { "openppc": { "command": "uvx", "args": ["--from", "openppc[mcp] @ git+https://github.com/secondsteplabs/openppc", "openppc-mcp"] } } }
```

OpenPPC isn't on PyPI yet, so these commands fetch it straight from GitHub.

**As a web connector** (ChatGPT, claude.ai), over streamable HTTP at `/mcp`:

```bash
openppc-mcp --http --host 0.0.0.0 --port 8000
```

Put it behind HTTPS and add `https://your-host/mcp` in ChatGPT (Developer mode) or claude.ai (Connectors). A hosted connector at `https://mcp.openppc.si/mcp` is coming soon. The connector's tools take the export's contents instead of a path, work in a temporary folder that is deleted when the call ends, and keep nothing. To keep an export on your computer while using ChatGPT, run OpenPPC locally and connect it through OpenAI's Secure MCP Tunnel.

Every tool is read-only: `list_templates` everywhere; `audit_account` and `check_numbers` on your computer; `audit_export` and `check_audit` on the connector. From a clone, `uv pip install -e ".[mcp]"` and then `claude mcp add openppc -- openppc-mcp`.

## How it works

```
your export (.csv)
  -> parse      skips Google's title, date and Total lines; recomputes every total from the rows
  -> template   computes each figure in code and registers it as a labeled fact
  -> report     prints registered facts only
  -> check      traces every number in the report back to a fact before you see it
```

The checker compares numbers at the precision they were written: "$1.4k" matches 1,361.04 because both round to 1,400, and "$1,500" does not. It reads the words around a number, and the table column it sits in, to catch a right number attached to the wrong metric or row.

## How sure is a waste flag?

A search term with no conversions might be bad, or just unlucky. A fixed rule ("no conversions after $20") can't tell the difference. OpenPPC's waste model learns how much your account's search terms differ in conversion rate, then gives each term the chance that it truly converts at less than half your account's rate. Only terms at 90% or more are marked as negatives to add; the rest are too early to judge, and the words they share are listed instead.

We backtested this on live accounts, excluding terms that people had already added as negatives. Terms the model was 90% sure about kept converting at a small fraction of their account's rate over the next five months. Terms flagged by a fixed dollar threshold went on to convert at close to the normal rate. The sample is still small, and the method is in `openppc/engine/waste_model.py`.

## The rulebook

Every rule the tool applies is a row in [`rulebook/rules.csv`](https://github.com/secondsteplabs/openppc/blob/main/rulebook/rules.csv): what it checks, the formula, the threshold, where the idea comes from (Google's own guidance, practitioners, or our reasoning) and the line of code that runs it. A test fails if a threshold in the code and its row ever disagree, so the rulebook is always what the tool actually does. Planned rules sit in the same file. Argue with any of them in an issue or a pull request.

## What it is not

- Not connected to your account. It reads a file you exported.
- Not an autopilot. It never changes a campaign.
- Not a strategy checker. It checks numbers and their direction, not whether the advice is good.

## Known limits

- With thousands of figures in a file, a number can match one by coincidence. Every trace names the fact it matched, so read the "traced to" column instead of just counting.
- "Not in data" means not in the files you provided. The figure may come from another report or date range.
- Benchmarks are the public WordStream / LocaliQ 2026 US averages: a ballpark, not a target.
- Google renames export columns from time to time. If a file won't load, open an issue with its header row.

## Roadmap

- An optional writer that turns the facts into prose with your own model key, while every number still comes from code
- A public eval: can an AI read a Google Ads account correctly?
- More exports: campaigns, Performance Max, Search Console, Meta

## Configuration

None. No API keys, no `.env`.

## Contributing

Issues and pull requests are welcome. Read [CONTRIBUTING.md](https://github.com/secondsteplabs/openppc/blob/main/CONTRIBUTING.md) first, and never attach a client's export.

## Security

To report a vulnerability, see [SECURITY.md](https://github.com/secondsteplabs/openppc/blob/main/SECURITY.md).

## License

MIT. See [LICENSE](https://github.com/secondsteplabs/openppc/blob/main/LICENSE).

---

<p align="center">
  <a href="https://github.com/secondsteplabs">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/secondsteplabs/.github/raw/main/assets/logo-labs-horizontal-dark.png">
      <img alt="labs.secondstep" src="https://github.com/secondsteplabs/.github/raw/main/assets/logo-labs-horizontal-light.png" width="200">
    </picture>
  </a>
</p>

Built by [labs.secondstep](https://github.com/secondsteplabs), the open-source side of [Second Step](https://getsecondstep.com).
