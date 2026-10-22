"""The single entry point used by the CLI, the MCP server and the skill.

Routes a URL to its platform module, applies the cache and the size budget.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import asdict
from typing import Callable

from . import cache, net
from .channels import arxiv, github, hn, pantip, reddit, rss, search as search_mod, social, web, youtube
from .errors import ReachError
from .model import Options, Result
from .render import fit

# Order matters: specific platforms first, the generic web reader last.
CHANNELS = (youtube, social, reddit, pantip, github, hn, arxiv, rss, web)
COMMENT_PLATFORMS = ("youtube", "tiktok", "reddit", "pantip", "github", "hn")


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ReachError("invalid_url", "no URL given")
    if "://" not in url:
        url = "https://" + url
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ReachError("unsafe_url", f"only http/https URLs are allowed, got {parts.scheme!r}")
    return url


def route(url: str):
    for ch in CHANNELS:
        if ch.match(url):
            return ch
    raise ReachError("unsupported", f"no reader for {url}")


def platform_name(url: str) -> str:
    ch = route(url)
    if ch is social:
        return social.platform_of(url) or "web"
    return ch.NAME


# How long a cached result is reused: pages and comments change, lists change fast.
TTL = {"read": 3600, "transcript": 24 * 3600, "search": 900, "feed": 900, "hn": 900, "arxiv": 3600}


def _cached(kind: str, key: str, opts: Options, fn: Callable[[], Result]) -> Result:
    o = asdict(opts)
    o.pop("max_chars", None)
    o.pop("no_cache", None)
    ckey = json.dumps([kind, key, o], sort_keys=True)
    if not opts.no_cache and not opts.cookies_from_browser:
        hit = cache.get(ckey, TTL[kind])
        if hit:
            r = Result.from_dict(hit)
            r.source = (r.source + " (cached)").strip()
            return fit(r, opts.max_chars)
    r = fn()
    if not opts.cookies_from_browser:  # never persist anything fetched with your login
        cache.put(ckey, r.to_dict())
    return fit(r, opts.max_chars)


def read(url: str, opts: Options) -> Result:
    url = normalize_url(url)
    net.check_url(url)
    ch = route(url)
    return _cached("read", url, opts, lambda: ch.read(url, opts))


def comments(url: str, opts: Options) -> Result:
    url = normalize_url(url)
    name = platform_name(url)
    if name not in COMMENT_PLATFORMS and name not in social.NO_COMMENTS:
        raise ReachError("unsupported", f"reading comments is not supported for {name}",
                         f"comments work for: {', '.join(COMMENT_PLATFORMS)}")
    opts.comments = True
    return read(url, opts)


def transcript(url: str, opts: Options) -> Result:
    url = normalize_url(url)
    net.check_url(url)
    if not youtube.match(url):
        raise ReachError("unsupported", "transcripts are available for YouTube URLs only")
    return _cached("transcript", url, opts, lambda: youtube.transcript(url, opts))


def search(query: str, opts: Options) -> Result:
    return _cached("search", query, opts, lambda: search_mod.search(query, opts))


def feed(url: str, opts: Options) -> Result:
    url = normalize_url(url)
    net.check_url(url)
    return _cached("feed", url, opts, lambda: rss.read(url, opts))


def hn_list(mode: str, query: str, opts: Options) -> Result:
    return _cached("hn", f"{mode}:{query}", opts, lambda: hn.listing(mode, query, opts))


def arxiv_search(query: str, opts: Options) -> Result:
    return _cached("arxiv", query, opts, lambda: arxiv.search(query, opts))
