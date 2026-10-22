"""HTTP with an SSRF guard. Every network request in reach-kit goes through here."""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Dict, Optional

from . import __version__
from .errors import ReachError

UA = f"reach-kit/{__version__} (+https://github.com/0pom33pom/reach-kit)"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
MAX_BYTES = 10 * 1024 * 1024


def check_url(url: str) -> str:
    """Allow only public http(s) URLs. Raises ReachError('unsafe_url') otherwise.

    Blocks file://, localhost, loopback, private, link-local and reserved
    addresses (checked after DNS resolution), so a page or a prompt cannot
    make reach-kit read your machine or your LAN.
    """
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        raise ReachError("invalid_url", f"not a valid URL: {url!r}")
    if parts.scheme not in ("http", "https"):
        raise ReachError("unsafe_url", f"only http/https URLs are allowed, got {parts.scheme or 'none'!r}")
    host = parts.hostname
    if not host:
        raise ReachError("invalid_url", f"URL has no host: {url!r}")
    if host.lower() in ("localhost", "localhost.localdomain") or host.lower().endswith(".localhost"):
        raise ReachError("unsafe_url", f"refusing local address: {host}")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise ReachError("invalid_url", f"bad port in URL: {url!r}")
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as e:
        raise ReachError("network", f"cannot resolve {host}: {e}")
    for info in infos:
        _require_public(info[4][0], host)
    return url


def _require_public(addr: str, host: str) -> None:
    ip = ipaddress.ip_address(addr.split("%", 1)[0])
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if not ip.is_global or ip.is_multicast:
        raise ReachError("unsafe_url", f"refusing non-public address {ip} for {host}")


def _proxy_hosts() -> set:
    hosts = set()
    for proxy in urllib.request.getproxies().values():
        h = urllib.parse.urlsplit(proxy if "://" in proxy else "//" + proxy).hostname
        if h:
            hosts.add(h.lower())
    return hosts


def _guarded_create_connection(address, *args, **kwargs):
    """socket.create_connection that re-checks the address we really connected to.

    check_url() resolves the name once; DNS can answer differently a moment
    later (DNS rebinding). Checking the connected peer closes that gap. A
    proxy you configured yourself (HTTP(S)_PROXY) is allowed to be local.
    """
    sock = socket.create_connection(address, *args, **kwargs)
    host = str(address[0]).lower()
    if host not in _proxy_hosts():
        try:
            _require_public(sock.getpeername()[0], host)
        except ReachError:
            sock.close()
            raise
    return sock


class _GuardedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _guarded_create_connection


class _GuardedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _guarded_create_connection


class _GuardedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_GuardedHTTPConnection, req)


class _GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_GuardedHTTPSConnection, req, context=self._context)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect, _GuardedHTTPHandler, _GuardedHTTPSHandler)


class Response:
    def __init__(self, status: int, url: str, headers: Dict[str, str], body: bytes, truncated: bool):
        self.status = status
        self.url = url
        self.headers = headers
        self.body = body
        self.truncated = truncated

    def text(self) -> str:
        charset = "utf-8"
        ctype = self.headers.get("content-type", "")
        if "charset=" in ctype:
            charset = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        if charset.lower().replace("-", "") == "utf8":
            charset = "utf-8-sig"  # Pantip and others send a BOM
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8-sig", errors="replace")

    def json(self):
        try:
            return json.loads(self.text())
        except ValueError as e:
            raise ReachError("parse_error", f"expected JSON from {self.url}: {e}")


def _status_error(status: int, url: str, body: str = "") -> ReachError:
    host = urllib.parse.urlsplit(url).hostname or url
    if status in (401,):
        return ReachError("login_required", f"{host} requires authentication (HTTP {status})")
    if status in (403, 429, 451):
        return ReachError("blocked", f"{host} refused the request (HTTP {status})")
    if status in (404, 410):
        return ReachError("not_found", f"not found on {host} (HTTP {status})")
    return ReachError("http_error", f"{host} returned HTTP {status}")


def http_get(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
    browser: bool = False,
    data: Optional[Dict[str, str]] = None,
) -> Response:
    """GET (or POST form when `data` is given) a public URL."""
    check_url(url)
    h = {
        "User-Agent": BROWSER_UA if browser else UA,
        "Accept-Encoding": "gzip",
        "Accept": "*/*",
    }
    h.update(headers or {})
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=h, method="POST" if data is not None else "GET")
    try:
        with _opener.open(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BYTES + 1)
            status = resp.status
            final = resp.geturl()
            rh = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        e.close()
        raise _status_error(e.code, url)
    except ReachError:
        raise
    except (socket.timeout, TimeoutError):
        raise ReachError("timeout", f"timed out after {timeout}s: {url}")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise ReachError("timeout", f"timed out after {timeout}s: {url}")
        raise ReachError("network", f"network error for {url}: {e.reason}")
    except (OSError, ValueError) as e:
        raise ReachError("network", f"network error for {url}: {e}")
    truncated = len(raw) > MAX_BYTES
    raw = raw[:MAX_BYTES]
    if rh.get("content-encoding") == "gzip":
        try:
            # Bounded decompression: a tiny gzip bomb cannot blow up memory.
            raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, MAX_BYTES)
        except zlib.error:
            pass
    return Response(status, final, rh, raw, truncated)
