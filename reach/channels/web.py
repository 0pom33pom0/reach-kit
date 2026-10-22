"""Any web page: Jina Reader first (clean markdown), then a direct fetch + HTML→text.

Privacy note: Jina Reader is a third-party service and sees the URL you read.
Set REACH_NO_JINA=1 to always fetch directly.
"""

from __future__ import annotations

import os
import urllib.parse

from .. import net
from ..errors import ReachError, first_error
from ..model import Options, Result
from ..text import html_to_text, html_title

NAME = "web"


def match(url: str) -> bool:
    return urllib.parse.urlsplit(url).scheme in ("http", "https")


def jina_enabled() -> bool:
    return os.environ.get("REACH_NO_JINA", "").strip() not in ("1", "true", "yes")


def read_via_jina(url: str, opts: Options, platform: str = NAME) -> Result:
    net.check_url(url)  # never ask a proxy to fetch what we would refuse ourselves
    headers = {"X-Return-Format": "markdown"}
    key = os.environ.get("JINA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = net.http_get("https://r.jina.ai/" + url, headers=headers, timeout=max(opts.timeout, 30))
    return parse_jina(resp.text(), url, platform)


def parse_jina(body: str, url: str, platform: str = NAME) -> Result:
    title, published = "", None
    content = body
    head, sep, rest = body.partition("Markdown Content:")
    if sep:
        content = rest
        for line in head.splitlines():
            if line.startswith("Title:"):
                title = line[6:].strip()
            elif line.startswith("Published Time:"):
                published = line[15:].strip() or None
    content = content.strip()
    low = title.lower()
    if not content or ("404" in low and "not found" in low):
        raise ReachError("not_found", f"page not found or empty: {url}")
    if any(s in low for s in ("just a moment", "attention required", "access denied")):
        raise ReachError("blocked", f"the site showed a bot challenge instead of content: {url}")
    return Result(platform=platform, url=url, title=title, published=published, text=content, source="jina-reader")


def read_direct(url: str, opts: Options, platform: str = NAME) -> Result:
    resp = net.http_get(url, timeout=opts.timeout, browser=True,
                        headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
    ctype = resp.headers.get("content-type", "")
    body = resp.text()
    if "html" in ctype or body.lstrip()[:200].lower().startswith(("<!doctype html", "<html")):
        text = html_to_text(body)
        title = html_title(body)
    elif ctype.startswith("text/") or "json" in ctype or "xml" in ctype:
        text, title = body, ""
    else:
        raise ReachError("unsupported", f"not a text page ({ctype or 'unknown type'}): {url}")
    r = Result(platform=platform, url=resp.url, title=title, text=text, source="direct")
    if resp.truncated:
        r.warnings.append("page was larger than 10 MB and was cut")
    return r


def read(url: str, opts: Options) -> Result:
    net.check_url(url)
    errors = []
    if jina_enabled():
        try:
            return read_via_jina(url, opts)
        except ReachError as e:
            if e.code in ("unsafe_url", "invalid_url"):
                raise
            errors.append(e)
    try:
        r = read_direct(url, opts)
        if errors:
            r.warnings.append("Jina Reader failed; used a direct fetch (layout may be rougher)")
        return r
    except ReachError as e:
        errors.append(e)
    raise first_error(errors, f"could not read {url}")
