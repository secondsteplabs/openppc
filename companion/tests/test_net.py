"""The site check's network guard, fitness function 12 (SCOPE_WIDENING_PLAN.md, section 4): never a private address
without --allow-private, never link-local or cloud metadata, through redirects, DNS rebinding, IPv4-mapped and 6to4
addresses too, and never more than its byte and time limits; the browser's proxy holds to the same rules."""
import gzip
import ipaddress
import socket

import pytest
from sites import local, page

from openppc_online.siteaudit import net
from openppc_online.siteaudit.net import Guard, GuardProxy, Refused, fetch, refusal


@pytest.mark.parametrize("address, by_default, with_allow_private", [
    ("8.8.8.8", True, True), ("2001:4860:4860::8888", True, True),
    ("127.0.0.1", False, True), ("10.1.2.3", False, True), ("192.168.0.1", False, True),
    ("172.16.0.1", False, True), ("::1", False, True), ("fd12::1", False, True),
    ("::ffff:127.0.0.1", False, True),
    # never: link-local, cloud metadata, carrier-grade NAT, unspecified, multicast, and wrapped forms of them
    ("169.254.169.254", False, False), ("fe80::1", False, False), ("100.100.100.200", False, False),
    ("fd00:ec2::254", False, False), ("100.64.0.1", False, False), ("0.0.0.0", False, False),
    ("224.0.0.1", False, False), ("::ffff:169.254.169.254", False, False), ("2002:a9fe:a9fe::1", False, False),
    ("2001:0:4136:e378:8000:63bf:3fff:fdd2", False, False),  # Teredo
])
def test_which_addresses_open_and_when(address, by_default, with_allow_private):
    ip = ipaddress.ip_address(address)
    assert (refusal(ip) == "") == by_default
    assert (refusal(ip, allow_private=True) == "") == with_allow_private


def test_a_name_with_one_private_address_among_public_ones_is_refused():
    guard = Guard(allow_private=False, resolve=lambda host, port: ["93.184.215.14", "10.0.0.5"])
    with pytest.raises(Refused, match=r"10\.0\.0\.5"):
        guard.addresses("rebind.example", 80)
    assert guard.refused == ["rebind.example"]


def test_a_name_is_resolved_once_per_connection_and_connected_by_the_checked_address(serve):
    # DNS rebinding: a second lookup could answer with a private address after the first one passed
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    answers = [["127.0.0.1"], ["169.254.169.254"]]
    guard = Guard(allow_private=True, resolve=lambda host, port: answers.pop(0))
    resp = fetch(base.replace("127.0.0.1", "site.test") + "/", guard)
    assert resp.status == 200 and answers == [["169.254.169.254"]]


def test_a_redirect_to_the_metadata_address_is_refused(serve):
    base = serve(lambda b: {"/": (302, {"Location": "http://169.254.169.254/latest/meta-data/"}, "")})
    resp = fetch(base + "/", Guard(allow_private=True))
    assert resp.refused and resp.status == 0
    assert resp.hops == [(base + "/", 302)]


def test_localhost_needs_allow_private(serve):
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    resp = fetch(base + "/", Guard())
    assert resp.refused and "--allow-private" in resp.error
    assert fetch(base + "/", Guard(allow_private=True)).status == 200


def test_a_compressed_bomb_is_cut_off(serve):
    bomb = gzip.compress(b"\0" * 20_000_000)
    base = serve(lambda b: {"/": (200, {"Content-Encoding": "gzip"}, bomb)})
    resp = fetch(base + "/", local(), max_bytes=1000)
    assert resp.truncated and len(resp.body) == 1000


def test_a_body_that_fails_part_way_is_no_response(serve, monkeypatch):
    def stall(*args):
        raise TimeoutError
    monkeypatch.setattr(net, "_read", stall)
    base = serve(lambda b: {"/": (200, {}, page("Home"))})
    resp = fetch(base + "/", local())
    assert resp.status == 0 and resp.error == "timed out"


def test_only_html_bodies_are_read_when_asked(serve):
    base = serve(lambda b: {"/f.pdf": (200, {"Content-Type": "application/pdf"}, b"%PDF" * 1000)})
    resp = fetch(base + "/f.pdf", local(), html_only=True)
    assert resp.status == 200 and resp.body == b""


def test_too_many_redirects_and_other_schemes_are_no_response(serve):
    base = serve(lambda b: {"/loop": (302, {"Location": "/loop"}, ""), "/ftp": (302, {"Location": "ftp://x.test/"}, "")})
    loop = fetch(base + "/loop", local())
    assert loop.status == 0 and "more than 10 redirects" in loop.error and len(loop.hops) == net.MAX_REDIRECTS + 1
    ftp = fetch(base + "/ftp", local())
    assert ftp.status == 0 and "not an http(s) address" in ftp.error


def test_cookies_are_never_kept_and_the_user_agent_says_who_asks(serve):
    base = serve(lambda b: {"/": (200, {"Set-Cookie": "session=secret"}, page("Home"))})
    resp = fetch(base + "/", local())
    assert "set-cookie" not in resp.headers
    assert "OpenPPC-SiteAudit/" in net.USER_AGENT and "+https://openppc.si" in net.USER_AGENT


def _ask_proxy(proxy, *requests):
    """Sends each request on one connection to the proxy, reading an answer after each; returns the answers."""
    host, port = proxy.url.rsplit("/", 1)[1].split(":")
    answers = []
    with socket.create_connection((host, int(port)), timeout=10) as s:
        for request in requests:
            s.sendall(request.encode())
            answers.append(s.recv(65536).decode("latin-1"))
    return answers


def test_the_browsers_proxy_applies_the_same_rules(serve):
    base = serve(lambda b: {"/": (200, {}, page("Proxied"))})
    hostport = base.split("//")[1]
    get, connect = f"GET {base}/ HTTP/1.1\r\nHost: x\r\n\r\n", f"CONNECT {hostport} HTTP/1.1\r\nHost: x\r\n\r\n"
    with GuardProxy(Guard()) as proxy:
        assert _ask_proxy(proxy, get)[0].startswith("HTTP/1.1 403")
        assert _ask_proxy(proxy, connect)[0].startswith("HTTP/1.1 403")
    with GuardProxy(Guard(allow_private=True)) as proxy:
        assert " 200 " in _ask_proxy(proxy, get)[0].split("\r\n")[0]
        tunnel = _ask_proxy(proxy, connect, "GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        assert tunnel[0].startswith("HTTP/1.1 200 Connection Established") and " 200 " in tunnel[1].split("\r\n")[0]
        assert _ask_proxy(proxy, "GET / HTTP/1.1\r\nHost: x\r\n\r\n")[0].startswith("HTTP/1.1 502")  # not a proxy request


def test_the_browsers_proxy_never_opens_the_metadata_address():
    guard = Guard(allow_private=True, resolve=lambda host, port: ["169.254.169.254"])
    with GuardProxy(guard) as proxy:
        assert _ask_proxy(proxy, "GET http://metadata.test/latest/ HTTP/1.1\r\nHost: x\r\n\r\n")[0].startswith(
            "HTTP/1.1 403")
        assert _ask_proxy(proxy, "CONNECT metadata.test:443 HTTP/1.1\r\nHost: x\r\n\r\n")[0].startswith("HTTP/1.1 403")
    assert guard.refused == ["metadata.test", "metadata.test"]


def test_the_browsers_proxy_ends_a_reset_tunnel_quietly():
    class Reset:
        def __init__(self):
            self.a, self.b = socket.socketpair()

        def fileno(self):
            return self.a.fileno()

        def recv(self, n):
            raise ConnectionResetError(10054, "reset by peer")

    left, right = Reset(), Reset()
    left.b.send(b"x")
    net._pipe(left, right)  # returns instead of raising
    for s in (left.a, left.b, right.a, right.b):
        s.close()
