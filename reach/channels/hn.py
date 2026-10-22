"""Hacker News via the Algolia API: stories, comment trees, front page, search."""

from __future__ import annotations

import urllib.parse
from typing import List

from .. import net
from ..errors import ReachError
from ..model import Comment, Item, Options, Result
from ..text import html_to_text, to_int

NAME = "hn"
API = "https://hn.algolia.com/api/v1"


def match(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    return (parts.hostname or "").lower() == "news.ycombinator.com" and "id=" in parts.query


def _children(kids, opts: Options, depth: int) -> List[Comment]:
    out: List[Comment] = []
    for k in kids or []:
        if k.get("type") != "comment" or not k.get("text"):
            continue
        out.append(Comment(
            author=k.get("author") or "",
            text=html_to_text(k.get("text") or ""),
            published=k.get("created_at"),
            replies=_children(k.get("children"), opts, depth + 1) if depth < opts.depth else [],
        ))
    if opts.sort == "new":
        out.sort(key=lambda c: c.published or "", reverse=True)
    return out


def parse_item(d: dict, opts: Options) -> Result:
    if not d or d.get("id") is None:
        raise ReachError("not_found", "Hacker News item not found")
    r = Result(
        platform=NAME,
        url=f"https://news.ycombinator.com/item?id={d['id']}",
        title=d.get("title") or "",
        author=d.get("author") or "",
        published=d.get("created_at"),
        text="\n\n".join(x for x in (d.get("url") or "", html_to_text(d.get("text") or "")) if x),
        stats={"points": to_int(d.get("points"))},
        source="hn.algolia.com",
    )
    if opts.comments:
        r.comments = _children(d.get("children"), opts, 1)[: opts.limit]
        if opts.sort == "top":
            r.warnings.append("HN does not expose comment scores; comments are in HN's thread order")
    return r


def read(url: str, opts: Options) -> Result:
    qs = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    item_id = (qs.get("id") or [""])[0]
    if not item_id.isdigit():
        raise ReachError("invalid_url", "HN URLs look like https://news.ycombinator.com/item?id=<number>")
    return parse_item(net.http_get(f"{API}/items/{item_id}", timeout=opts.timeout).json(), opts)


def parse_hits(data: dict) -> List[Item]:
    items = []
    for h in data.get("hits") or []:
        oid = h.get("objectID")
        items.append(Item(
            title=h.get("title") or h.get("story_title") or "",
            url=f"https://news.ycombinator.com/item?id={oid}",
            snippet=h.get("url") or "",
            author=h.get("author") or "",
            published=h.get("created_at"),
            stats={"points": to_int(h.get("points")), "comments": to_int(h.get("num_comments"))},
        ))
    return items


def listing(mode: str, query: str, opts: Options) -> Result:
    n = min(max(opts.limit, 1), 100)
    if mode == "top":
        url = f"{API}/search?tags=front_page&hitsPerPage={n}"
    elif mode == "new":
        url = f"{API}/search_by_date?tags=story&hitsPerPage={n}"
    elif mode == "search":
        if not query:
            raise ReachError("invalid_url", "usage: reach hn search \"<query>\"")
        url = f"{API}/search?tags=story&hitsPerPage={n}&query=" + urllib.parse.quote(query)
    else:
        raise ReachError("invalid_url", "mode must be top, new or search")
    items = parse_hits(net.http_get(url, timeout=opts.timeout).json())
    return Result(platform=NAME, url="https://news.ycombinator.com/", title=f"Hacker News — {mode} {query}".strip(),
                  items=items, source="hn.algolia.com")
