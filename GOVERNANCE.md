# Governance

> **Draft for the maintainer's review.** Nothing on this page is adopted until it merges to `main`.

## Who decides

OpenPPC is maintained by Shivendra Rawat through Second Step Labs. Anyone can propose a change in an issue or a pull request (see [CONTRIBUTING.md](CONTRIBUTING.md)). The maintainer decides what merges, and says why when a proposal is declined. The roadmap is public in the [README](README.md#roadmap).

Work lands on the `stagging` branch first. The maintainer merges it to `main`, and releases are tagged from `main`.

A change to a rule needs a source: every rule is a row in [`rulebook/rules.csv`](rulebook/rules.csv) saying where it comes from, and a test keeps the code and the rulebook in step.

## What will not change

These are commitments to everyone who uses or contributes to OpenPPC. Pledges 3 and 4 describe OpenPPC itself: the `openppc` package and command, the app at [openppc.si](https://openppc.si), and the MCP server (`openppc-mcp`).

1. **Released code stays MIT.** Code released in this repository under the MIT license stays available under it. It is never relicensed retroactively.
2. **Free stays free.** Everything in this repository stays free under the MIT license. A feature released free here is never moved behind a paywall, removed to be sold back, or limited to push people to a paid edition.
3. **No hidden phone-home.** OpenPPC makes no network calls and uploads nothing. The command line and the MCP server never reach out to anything (with `--http`, the MCP server only answers the AI client you point at it); the browser app downloads only its own pinned code (the Python runtime, two libraries and the fonts) and never sends your files anywhere. If that ever changes, it will be documented, off by default, and turned on only by you.
4. **Read-only.** OpenPPC never connects to your account and never changes anything in it.
5. **Code computes the numbers.** Every figure in a report is computed by code and traced to your data. An AI model may write words around the numbers; it is never their source.

## The online companion

Some jobs need the network: downloading an export through an ad platform's API, or crawling a landing page. These are planned as a separate install with its own name and command, `openppc-online`, so that pledges 3 and 4 stay true of OpenPPC without exceptions. It is not released yet. When it is:

6. **Off unless you install it and run it.** Installing `openppc` never installs it, and OpenPPC never calls it.
7. **Read-only.** It reads reports and pages. It never creates, changes or deletes anything in an ad account or on a site.
8. **Your own credentials.** It uses API keys and tokens you create, kept on your machine. OpenPPC never ships, proxies or stores one.
9. **Only the hosts it declares.** It connects only to the hosts its documentation lists, plus the site you ask it to crawl.

## Changing this page

A change to this page is proposed in a public issue and stays open for comment for at least 30 days before it merges. A change never applies to code already released.

## Elsewhere

- Security problems: [SECURITY.md](SECURITY.md)
- Conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Licenses of what OpenPPC uses: [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)
