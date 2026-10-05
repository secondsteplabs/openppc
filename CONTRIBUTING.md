# Contributing to OpenPPC

Thanks for helping. A few rules keep OpenPPC trustworthy.

## Never share client data

- Never attach a client's export, screenshot or audit to an issue or pull request. Describe the problem instead: the export's header row, how many rows it has, and what you expected.
- Tests, samples and docs use fictional accounts only, like the Acme Plumbing sample in `examples/`. Never paste real search terms, account IDs or figures.
- Keep real exports in `exports/`, which git ignores.

## Set up

```bash
git clone https://github.com/secondsteplabs/openppc
cd openppc
uv venv && uv pip install -e ".[dev,mcp]"
pytest -q
```

After you change the engine, run `python tools/build_web.py` to rebuild the browser app's `web/engine.js`; a test fails if you forget. `python tools/build_site.py` builds the website into `dist/`.

## What makes a good change

- A bug fix comes with a test that fails before the fix.
- A new rule is a row in `rulebook/rules.csv`, with its source, plus the code that runs it. A test keeps the two in step.
- Support for a new export format comes with a fictional sample file.
- Every number a template prints is registered as a fact, so the checker can trace it.
- The engine uses the Python standard library only, so it keeps running in the browser. Please don't add runtime dependencies.

## Security problems

Please don't open a public issue. See [SECURITY.md](SECURITY.md).
