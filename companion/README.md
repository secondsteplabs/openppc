# openppc-online

The optional companion to [OpenPPC](https://github.com/secondsteplabs/openppc), for the jobs that need more than a
browser tab or an offline command: each runs only when you run it.

OpenPPC itself never goes online. `pip install openppc` never installs this, and the `openppc` command never calls
it. This is a separate install with its own command, so that stays true without exceptions.

It is not released yet. Version 0.1.0 is its foundation: the app on your computer. Landing page and tracking
checks (`openppc-online site`) and downloads with your own API credentials (`openppc-online fetch`) are planned.

## What it promises

These are pledges 6 to 9 in OpenPPC's [GOVERNANCE.md](https://github.com/secondsteplabs/openppc/blob/main/GOVERNANCE.md#the-online-companion):

- **Off unless you install it and run it.** Installing `openppc` never installs it, and OpenPPC never calls it.
- **Read-only.** It reads reports and pages. It never creates, changes or deletes anything in an ad account or on a
  site.
- **Your own credentials.** It uses API keys and tokens you create, kept on your machine. OpenPPC never ships,
  proxies or stores one.
- **Only the hosts it declares.** Each command below lists every host it connects to.

## Commands

### `openppc-online app`

```
openppc-online app
openppc-online app --port 8800 --no-browser
```

Opens the OpenPPC app from this computer, at `http://127.0.0.1:8766/` (or any free port if that one is taken). It is
the same app as [openppc.si/app](https://openppc.si/app/): audits and checks run in the browser tab, and your files
stay on your computer. The line at the top of the page names openppc-online when this server is serving it.

- **Hosts:** it answers only on 127.0.0.1. It connects to nothing itself; the page loads its Python runtime,
  libraries and fonts from cdn.jsdelivr.net, as on openppc.si.
- **Security:** it answers only to its own address, and the page gets a new token on each run, which every call to
  this server needs. [THREAT_MODEL.md](https://github.com/secondsteplabs/openppc/blob/main/companion/THREAT_MODEL.md)
  has the details.

Exit codes: 0 when it stops normally (Ctrl-C), 1 for bad input, as `openppc` uses them.

## Install

Once it is released:

```
pip install openppc-online
```

It needs `openppc` 0.4, which it installs. In a clone of the repository:

```
pip install -e .
pip install -e companion
openppc-online app
```

A clone serves its own `web/` folder. The wheel carries a copy, made by `python tools/stage_companion_web.py`
before `python -m build companion`.

## Tests

```
pytest companion
pytest -m e2e companion   # in Chromium: pip install -e "companion[e2e]", then playwright install chromium
```

MIT license, like OpenPPC.
