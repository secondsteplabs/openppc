"""`openppc-online app`: the OpenPPC web app, served from this computer.

It is the app at openppc.si, and audits and checks still run in the browser tab. What a tab can't do on its own
runs here as a job the page starts and polls: a site audit (`openppc-online site`), shown in the Site view that
local/site.js adds, and a download through an ad platform's API (`openppc-online fetch`), in the Download view that
local/fetch.js adds. A download's credentials come in its request and are dropped when it ends.

The server answers only on 127.0.0.1, and only to its own Host name, which shuts out DNS rebinding. Its API needs
the token written into the page it serves, sent in a header: another website open in the browser can't read the
page, and sending that header from elsewhere takes a CORS preflight this server never allows. A POST is read only
once all of that holds, and only as JSON of a bounded size. It serves a fixed list of files read at start, so no
path reaches anything else on disk. THREAT_MODEL.md has the rest.
"""
import json
import re
import secrets
import sys
import threading
import time
import traceback
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import openppc

from . import __version__, site
from .fetch import command as fetch_command
from .fetch.files import DAYS
from .siteaudit.crawl import MAX_PER_PATTERN
from .siteaudit import words
from .siteaudit.checks import CATEGORIES
from .siteaudit.render import INSTALL, installed

PACKAGE = Path(__file__).resolve().parent
PACKAGED_WEB = PACKAGE / "web"            # the wheel's copy (tools/stage_companion_web.py)
CLONE_WEB = PACKAGE.parent.parent / "web"  # a clone of the repository serves its own web/
LOCAL = PACKAGE / "local"                 # what only this copy of the app has
PORT = 8766
TIMEOUT = 30  # seconds a connection may sit idle: a slow client can't hold a thread for good
CHUNK = 8_192  # bytes per socket write: on some Windows machines a 64 KB write to a loopback reader stalls until
               # the connection times out, and the page loads without app.js
HOSTED_CONNECT = "connect-src https://cdn.jsdelivr.net"  # web/index.html's policy
LOCAL_CONNECT = "connect-src 'self' https://cdn.jsdelivr.net"
POLICY = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">')
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
TOKEN_HEADER = "X-OpenPPC-Token"
MAX_BODY = 20 * 1024 * 1024  # bytes of JSON a POST may carry: rule packs and a baseline from a large crawl
LINGER = 2  # seconds a closing connection waits for what the client is still sending, which is thrown away
KEEP_JOBS = 4                # finished jobs kept, in memory only, for the page to fetch
STOPPED = "stopped with the Stop button"
STOP_CHECK = 0.25  # seconds between looks at the Stop button while a platform builds a report
JOB = re.compile(r"/api/jobs/([\w-]{1,32})")
STOP = re.compile(r"/api/jobs/([\w-]{1,32})/stop")
SITE_FIELDS = {"kind", "url", "max_pages", "max_time", "fast", "external", "allow_private", "render", "render_urls",
               "consent_selector", "crux_key", "psi", "psi_key", "single", "configs", "baseline"}
FETCH_FIELDS = {"kind", "platform", "account", "days", "conversion", "credentials"}
MAX_FILES = 20
MAX_NAME = 100


def web_root() -> Path:
    for web in (PACKAGED_WEB, CLONE_WEB):
        if (web / "index.html").is_file():
            return web
    raise ValueError("this install has no copy of the web app. Reinstall openppc-online, or in a clone of the "
                     "repository run it from there.")


def _once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"web/index.html changed: expected one {old!r}. Update openppc_online/app.py to match.")
    return text.replace(old, new)


def page(web: Path, token: str) -> tuple[bytes, str]:
    """(web/index.html with the token and the local files in it, and its policy): the hosted page, allowed to call
    this server. A change to the hosted page's policy stops the server rather than serve a page that half works."""
    html = (web / "index.html").read_text(encoding="utf-8")
    html = _once(html, HOSTED_CONNECT + ";", LOCAL_CONNECT + ";")
    html = _once(html, '<meta charset="utf-8">', f'<meta charset="utf-8">\n<meta name="openppc-local" content="{token}">')
    html = _once(html, '<link rel="stylesheet" href="style.css">',
                 '<link rel="stylesheet" href="style.css">\n<link rel="stylesheet" href="site.css">')
    html = _once(html, '<script defer src="app.js"></script>',  # after app.js: site.js and fetch.js use its helpers
                 '<script defer src="app.js"></script>\n<script defer src="local.js"></script>\n'
                 '<script defer src="site.js"></script>\n<script defer src="fetch.js"></script>')
    policy = POLICY.search(html)
    if policy is None:
        raise RuntimeError("web/index.html has no Content-Security-Policy. Update openppc_online/app.py to match.")
    return html.encode("utf-8"), policy[1] + "; frame-ancestors 'none'"


def files(web: Path) -> dict[str, tuple[bytes, str]]:
    """Every file the page may load, by address, read once: nothing else on disk can be asked for."""
    found = [p for p in web.iterdir() if p.is_file() and p.suffix in TYPES and p.name != "index.html"]
    found += [LOCAL / "local.js", LOCAL / "site.js", LOCAL / "fetch.js", LOCAL / "site.css"]
    return {f"/{p.name}": (p.read_bytes(), TYPES[p.suffix]) for p in found}


class Job:
    """One run in its own thread. Stop takes effect at the run's next progress line: a site audit's crawl so far still
    makes a report, as Ctrl-C does on the command line; a download keeps nothing."""

    def __init__(self, work: Callable[["Job"], dict[str, Any]], kind: str = "site"):
        self.id, self.kind = secrets.token_urlsafe(9), kind
        self.state = "running"  # then "done" or "failed"
        self.progress = "Starting…"
        self.stopping = False
        self.error = ""
        self.result: dict[str, Any] | None = None
        self.thread = threading.Thread(target=self._run, args=(work,), daemon=True)

    def tick(self, message: str) -> None:
        self.progress = message[:160]
        if self.stopping:
            raise KeyboardInterrupt(STOPPED)

    def _run(self, work: Callable[["Job"], dict[str, Any]]) -> None:
        try:
            self.result = work(self)
            self.state = "done"
            return
        except (ValueError, OSError) as e:
            self.error = str(e) or type(e).__name__
        except KeyboardInterrupt:
            self.error = "Stopped before the scan began."
        except Exception as e:  # a bug: say so on the page instead of leaving it waiting
            traceback.print_exc()
            self.error = f"openppc-online hit a bug ({type(e).__name__}). Please report it, with the terminal's text."
        self.state = "failed"

    def view(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": True, "id": self.id, "kind": self.kind, "state": self.state,
                               "progress": self.progress, "stopping": self.stopping}
        if self.state == "failed":
            out["error"] = self.error
        if self.result is not None:
            out["result"] = self.result
        return out


def _flag(p: dict[str, Any], key: str, default: bool) -> bool:
    value = p.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false")
    return value


def _limit(p: dict[str, Any], key: str) -> float | None:
    """A limit the form may leave empty (no limit), else more than 0."""
    value = p.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise ValueError(f"{key} must be a number above 0, or left empty for no limit")
    return value


def _text(p: dict[str, Any], key: str, most: int = 2000) -> str:
    value = p.get(key, "")
    if not isinstance(value, str) or len(value) > most:
        raise ValueError(f"{key} must be text of at most {most} characters")
    return value.strip()


def _upload(value: Any) -> tuple[str, str]:
    """A file from the page, {name, text}, as (name, text): its base name only, cut short, without control
    characters or the backtick that would end the report's code span around it."""
    if not isinstance(value, dict) or not isinstance(value.get("text"), str) or not isinstance(value.get("name"), str):
        raise ValueError("a file arrived without its name and contents")
    name = re.sub(r"[\x00-\x1f\x7f`]", "", value["name"].replace("\\", "/").rsplit("/", 1)[-1])[:MAX_NAME]
    return name or "file.json", value["text"]


def site_job(p: dict[str, Any]) -> Callable[[Job], dict[str, Any]]:
    """The page's Site form as `site.run` arguments, every field checked before the job starts."""
    unknown = sorted(set(p) - SITE_FIELDS)
    if unknown:
        raise ValueError(f"unknown field {unknown[0]!r}")
    url = _text(p, "url")
    if not url:
        raise ValueError("give the address of the site to audit, e.g. example.com")
    max_pages = _limit(p, "max_pages")
    if max_pages is not None and max_pages != int(max_pages):
        raise ValueError("max_pages must be a whole number")
    urls, configs = p.get("render_urls", []), p.get("configs", [])
    if not isinstance(urls, list) or len(urls) > MAX_FILES or not all(isinstance(u, str) for u in urls):
        raise ValueError(f"render_urls must be a list of at most {MAX_FILES} addresses")
    if not isinstance(configs, list) or len(configs) > MAX_FILES:
        raise ValueError(f"configs must be a list of at most {MAX_FILES} files")
    psi_key = _text(p, "psi_key", 500)
    args: dict[str, Any] = {
        "psi_key": psi_key if _flag(p, "psi", False) else None, "single": _flag(p, "single", False),
        "max_pages": None if max_pages is None else int(max_pages), "max_seconds": _limit(p, "max_time"),
        "max_per_pattern": MAX_PER_PATTERN, "fast": _flag(p, "fast", False), "external": _flag(p, "external", True),
        "allow_private": _flag(p, "allow_private", False), "rendered": _flag(p, "render", False),
        "render_url": [u.strip() for u in urls if u.strip()], "consent_selector": _text(p, "consent_selector", 500),
        "crux_key": _text(p, "crux_key", 500) or None, "config": [_upload(c) for c in configs],
        "baseline": _upload(p["baseline"]) if p.get("baseline") is not None else None}

    def work(job: Job) -> dict[str, Any]:
        result, _ = site.run(url, progress=job.tick, **args)
        return {"origin": result.origin, "passed": result.passed, "inconclusive": result.inconclusive,
                "findings": len(result.findings), "high": sum(f.level == "high" for f in result.findings),
                "texts": result.texts, "words": {"why": words.WHY, "differs": words.DIFFERS, "measures": words.MEASURES,
                                                 "findings": words.FINDINGS, "a11y": words.A11Y, "who": words.WHO,
                                                 "areas": CATEGORIES,
                                                 "glossary": [(term, line) for term, _, line in words.GLOSSARY]}}
    return work


def fetch_job(p: dict[str, Any]) -> Callable[[Job], dict[str, Any]]:
    """The page's Download form as `fetch` arguments, every field checked before the job starts. The credentials live
    in this job's memory only, and are cleared when it ends."""
    unknown = sorted(set(p) - FETCH_FIELDS)
    if unknown:
        raise ValueError(f"unknown field {unknown[0]!r}")
    platform = _text(p, "platform", 20)
    if platform not in fetch_command.PLATFORMS:
        raise ValueError(f"platform must be one of {', '.join(fetch_command.PLATFORMS)}")
    account = _text(p, "account", 100)
    if not account:
        raise ValueError("give the account's ID")
    days = p.get("days", DAYS)
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= fetch_command.MAX_DAYS:
        raise ValueError(f"days must be a whole number from 1 to {fetch_command.MAX_DAYS}")
    conversion = _text(p, "conversion", 200) or None
    given = p.get("credentials", {})
    if not isinstance(given, dict) or not all(isinstance(v, str) and len(v) <= 4000 for v in given.values()):
        raise ValueError("credentials must be names and values of at most 4000 characters")
    extra = sorted(set(given) - set(fetch_command.CREDENTIALS[platform]))
    if extra:
        raise ValueError(f"{extra[0]!r} isn't a {fetch_command.TITLES[platform]} credential")
    creds = {name: value.strip() for name, value in given.items() if value.strip()}

    def work(job: Job) -> dict[str, Any]:
        def wait(seconds: float) -> None:
            end = time.monotonic() + seconds
            while (left := end - time.monotonic()) > 0:
                job.tick(f"Waiting for {fetch_command.TITLES[platform]} to build the report…")
                time.sleep(min(left, STOP_CHECK))

        job.tick(f"Downloading from {fetch_command.TITLES[platform]}…")
        try:
            found, notes = fetch_command.contents(platform, account, creds, days=days, conversion=conversion,
                                                  sleep=wait)
        except KeyboardInterrupt:
            raise ValueError("Stopped with the Stop button; nothing was downloaded.") from None
        finally:
            creds.clear()
        return {"platform": platform, "files": found, "notes": notes,
                "templates": {name: fetch_command.TEMPLATE[name] for name in found}}
    return work


JOBS = {"site": site_job, "fetch": fetch_job}
RUNNING = {"site": "A site audit", "fetch": "A download"}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"  # on Windows it would let a second server share a taken port

    def __init__(self, port: int, web: Path):
        super().__init__(("127.0.0.1", port), Handler)
        self.token = secrets.token_urlsafe(32)
        self.port = self.server_address[1]
        self.hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self.origins = {f"http://{host}" for host in self.hosts}
        self.index, self.policy = page(web, self.token)
        self.files = files(web)
        self.jobs: dict[str, Job] = {}  # oldest first
        self.jobs_lock = threading.Lock()

    def start(self, work: Callable[[Job], dict[str, Any]], kind: str = "site") -> tuple[Job, bool]:
        """(the new job, True), or (the one already running, False): one at a time, since a crawl with a browser is
        a heavy thing to run twice. The oldest finished jobs go past KEEP_JOBS."""
        with self.jobs_lock:
            for job in self.jobs.values():
                if job.state == "running":
                    return job, False
            finished = list(self.jobs)
            for old in finished[:max(len(finished) - KEEP_JOBS + 1, 0)]:
                del self.jobs[old]
            job = Job(work, kind)
            self.jobs[job.id] = job
        job.thread.start()
        return job, True

    def close_request(self, request: Any) -> None:
        """Closes a connection once the client has stopped sending (at most MAX_BODY bytes or LINGER seconds, thrown
        away unread): closing with bytes unread resets the connection, and the client can lose the answer, such as a
        refused POST's, whose body is never read. The answer is all sent by now (shutdown_request shut writing)."""
        deadline, left = time.monotonic() + LINGER, MAX_BODY
        try:
            while left > 0 and (wait := deadline - time.monotonic()) > 0:
                request.settimeout(wait)
                chunk = request.recv(min(left, 65_536))
                if not chunk:
                    break
                left -= len(chunk)
        except OSError:
            pass
        super().close_request(request)


class Handler(BaseHTTPRequestHandler):
    server: Server
    server_version = "openppc-online"
    sys_version = ""
    timeout = TIMEOUT

    def log_message(self, format: str, *args: Any) -> None:
        pass  # the terminal says the app is running; a line per file would bury that

    def _send(self, code: int, body: bytes, kind: str, cache: str = "no-cache", policy: bool = False) -> None:
        self.send_response(code)
        for name, value in (("Content-Type", kind), ("Content-Length", str(len(body))), ("Cache-Control", cache),
                            ("Referrer-Policy", "no-referrer"), ("X-Content-Type-Options", "nosniff"),
                            ("Cross-Origin-Resource-Policy", "same-origin")):
            self.send_header(name, value)
        if policy:  # the page's only: a worker takes its policy from its own script, and openppc.si sends it none
            self.send_header("Content-Security-Policy", self.server.policy)
        self.end_headers()
        if self.command != "HEAD":
            for at in range(0, len(body), CHUNK):
                self.wfile.write(body[at:at + CHUNK])

    def _text(self, code: int, text: str) -> None:
        self._send(code, text.encode("utf-8"), "text/plain; charset=utf-8")

    def _refuse(self, code: int, error: str) -> None:
        """An answer that leaves the request's body unread, so the connection closes after it (Server.close_request)."""
        self.close_connection = True
        self._json(code, {"ok": False, "error": error})

    def _host_ok(self) -> bool:
        if self.headers.get("Host", "") in self.server.hosts:
            return True
        self.close_connection = True
        self._text(421, "This server answers only at its own address, 127.0.0.1.")
        return False

    def _api_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self.server.origins:
            self._refuse(403, "openppc-online answers only the page it serves.")
            return False
        given = self.headers.get(TOKEN_HEADER, "").encode("latin-1", "replace")
        if not secrets.compare_digest(given, self.server.token.encode("ascii")):
            self._refuse(403, "This page isn't the one openppc-online app is serving now. Reload it.")
            return False
        return True

    def do_GET(self) -> None:
        if not self._host_ok():
            return
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, self.server.index, TYPES[".html"], cache="no-store", policy=True)
        elif path.startswith("/api/"):
            if self._api_ok():
                self._get_api(path)
        elif path in self.server.files:
            self._send(200, *self.server.files[path])
        else:
            self._text(404, "Not found.")

    do_HEAD = do_GET

    def do_POST(self) -> None:
        if not self._host_ok():
            return
        path = urlsplit(self.path).path
        if not path.startswith("/api/"):
            self.close_connection = True
            self._text(404, "Not found.")
            return
        if not self._api_ok():
            return
        body = self._body()
        if body is None:
            return
        stop = STOP.fullmatch(path)
        if path == "/api/jobs":
            self._start(body)
        elif stop:
            job = self.server.jobs.get(stop[1])
            if job is None:
                self._gone()
                return
            job.stopping = job.state == "running"
            self._json(200, job.view())
        else:
            self._no_such_address()

    def _body(self) -> dict[str, Any] | None:
        """The request's JSON object, read only when it says it is JSON of a size this server takes."""
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            self._refuse(415, "openppc-online takes JSON only.")
            return None
        length = self.headers.get("Content-Length", "")
        if "Transfer-Encoding" in self.headers or not length.isdigit():
            self._refuse(411, "openppc-online needs the request's length up front.")
            return None
        if int(length) > MAX_BODY:
            self._refuse(413, f"That is more than openppc-online takes at once ({MAX_BODY // 1024 // 1024} MB). "
                              "Leave out the largest file.")
            return None
        try:
            body = json.loads(self.rfile.read(int(length)))
        except (ValueError, UnicodeDecodeError):
            body = None
        if not isinstance(body, dict):
            self._json(400, {"ok": False, "error": "The request wasn't a JSON object. Reload the page."})
            return None
        return body

    def _start(self, body: dict[str, Any]) -> None:
        kind = body.get("kind")
        if kind not in JOBS:
            self._json(400, {"ok": False, "error": "openppc-online runs site audits and downloads only. Reload the "
                                                   "page."})
            return
        try:
            work = JOBS[kind](body)
        except ValueError as e:
            self._json(400, {"ok": False, "error": str(e)})
            return
        job, started = self.server.start(work, kind)
        if started:
            self._json(202, job.view())
        else:
            self._json(409, {"ok": False, "error": f"{RUNNING[job.kind]} is already running; one at a time.",
                             "id": job.id, "kind": job.kind})

    def _get_api(self, path: str) -> None:
        job = JOB.fullmatch(path)
        if path == "/api/info":
            self._json(200, {"ok": True, "version": __version__, "openppc": openppc.__version__,
                             "render": installed(), **({} if installed() else {"render_install": INSTALL})})
        elif job:
            found = self.server.jobs.get(job[1])
            if found is None:
                self._gone()
            else:
                self._json(200, found.view())
        else:
            self._no_such_address()

    def _gone(self) -> None:
        self._json(404, {"ok": False, "error": f"That run is gone: openppc-online keeps the last {KEEP_JOBS}, and "
                                               "none from before it restarted. Run it again."})

    def _no_such_address(self) -> None:
        self._json(404, {"ok": False, "error": "openppc-online has no such address. Reload the page."})

    def _json(self, code: int, obj: dict[str, Any]) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")


def serve(port: int = PORT, open_browser: bool = True) -> int:
    web = web_root()
    try:
        server = Server(port, web)
    except OSError:
        server = Server(0, web)  # the port is taken, by another copy perhaps: any free one will do
    url = f"http://127.0.0.1:{server.port}/"
    print(f"OpenPPC is running on this computer at {url}\nKeep this window open while you use it; Ctrl-C stops it.",
          file=sys.stderr)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("openppc-online: stopped", file=sys.stderr)
    finally:
        server.server_close()
    return 0
