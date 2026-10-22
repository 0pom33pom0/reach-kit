"""Pantip topics and their comments (with replies). No login needed.

Only public fields are kept: we never output members' IPs, emails or IDs
even though Pantip's comment feed includes some of them.
"""

from __future__ import annotations

import math
import re
import urllib.parse
from typing import List, Tuple

from .. import net
from ..errors import ReachError
from ..model import Comment, Options, Result
from ..text import html_to_text, html_title, iso_from_bangkok, iso_from_unix, to_int

NAME = "pantip"
TOPIC_RE = re.compile(r"/topic/(\d+)")
PAGE_SIZE = 100
MAX_PAGES = 5


def match(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return (host == "pantip.com" or host.endswith(".pantip.com")) and bool(TOPIC_RE.search(url))


def topic_id(url: str) -> str:
    m = TOPIC_RE.search(urllib.parse.urlsplit(url).path)
    if not m:
        raise ReachError("invalid_url", "Pantip URLs look like https://pantip.com/topic/<number>")
    return m.group(1)


def _first_div(markup: str, cls: str) -> str:
    """Inner HTML of the first <div class="cls"> (handles nested divs)."""
    m = re.search(r'<div[^>]*class="%s"[^>]*>' % re.escape(cls), markup)
    if not m:
        return ""
    i, depth = m.end(), 1
    for t in re.finditer(r"<(/?)div\b[^>]*>", markup[i:]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return markup[i: i + t.start()]
    return markup[i:]


def parse_topic(markup: str, url: str) -> Result:
    title = html_title(markup)
    if not title or "ไม่พบกระทู้" in markup[:5000] and not _first_div(markup, "display-post-story"):
        raise ReachError("not_found", "Pantip topic not found (deleted or hidden)")
    body = html_to_text(_first_div(markup, "display-post-story"))
    author = ""
    m = re.search(r'class="display-post-name owner"[^>]*>([^<]+)<', markup)
    if m:
        author = m.group(1).strip()
    published = None
    m = re.search(r'data-utime="(\d\d/\d\d/\d{4} \d\d:\d\d:\d\d)"', markup)
    if m:
        published = iso_from_bangkok(m.group(1))
    likes = None
    m = re.search(r'<span class="like-score[^"]*">(\d+)<', markup)
    if m:
        likes = int(m.group(1))
    tags = re.findall(r'<a[^>]+href="https://pantip\.com/tag/[^"]+"[^>]*>([^<]+)</a>', markup)
    title = re.sub(r"\s*-\s*Pantip\s*$", "", title)
    stats = {"likes": likes}
    if tags:
        stats["tags"] = ", ".join(dict.fromkeys(t.strip() for t in tags))
    return Result(platform=NAME, url=url, title=title, author=author, published=published,
                  text=body, stats=stats, source="pantip topic page")


def _comment(c: dict) -> Comment:
    published = iso_from_unix(c.get("created_time")) or iso_from_bangkok(c.get("data_utime") or "")
    return Comment(
        author=((c.get("user") or {}).get("name") or "").strip(),
        text=html_to_text(c.get("message") or ""),
        likes=to_int(c.get("point")),
        published=published,
    )


def parse_comments(pages: List[dict], opts: Options) -> Tuple[List[Comment], int, int]:
    """Returns (comments, total_on_pantip, replies_not_loaded)."""
    out: List[Comment] = []
    total = 0
    hidden_replies = 0
    for page in pages:
        total = max(total, to_int(page.get("count")) or 0)
        for c in page.get("comments") or []:
            node = _comment(c)
            replies = c.get("replies") or []
            if opts.depth > 1:
                node.replies = [_comment(r) for r in replies]
                hidden_replies += max(0, (to_int(c.get("reply_count")) or 0) - len(replies))
            out.append(node)
    if opts.sort == "top":
        out.sort(key=lambda n: n.likes or 0, reverse=True)
    elif opts.sort == "new":
        out.reverse()
    return out[: opts.limit], total, hidden_replies


def _fetch_comment_page(tid: str, page: int, opts: Options) -> dict:
    url = (f"https://pantip.com/forum/topic/render_comments?tid={tid}"
           f"&param={'page%d' % page if page > 1 else ''}&type=3&page={page}")
    resp = net.http_get(url, timeout=opts.timeout, browser=True, headers={
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://pantip.com/topic/{tid}",
    })
    data = resp.json()
    if not isinstance(data, dict):
        raise ReachError("parse_error", "unexpected Pantip comments format")
    return data


def read(url: str, opts: Options) -> Result:
    tid = topic_id(url)
    canonical = f"https://pantip.com/topic/{tid}"
    page = net.http_get(canonical, timeout=opts.timeout, browser=True)
    r = parse_topic(page.text(), canonical)
    if not opts.comments:
        return r
    first = _fetch_comment_page(tid, 1, opts)
    pages = [first]
    total = to_int(first.get("count")) or 0
    # Load every page (max 5 = 500 comments) so "top"/"new" are judged over the whole topic.
    n_pages = max(1, min(MAX_PAGES, math.ceil(total / PAGE_SIZE)))
    for p in range(2, n_pages + 1):
        try:
            pages.append(_fetch_comment_page(tid, p, opts))
        except ReachError as e:
            r.warnings.append(f"stopped loading comment pages at page {p}: {e.message}")
            break
    r.comments, total, hidden = parse_comments(pages, opts)
    r.stats["comments"] = total
    if total > PAGE_SIZE * MAX_PAGES:
        r.warnings.append(f"topic has {total} comments; sorted among the first 500 only")
    if hidden:
        r.warnings.append(f"{hidden} older replies inside comments were not loaded (Pantip shows 5 per comment)")
    r.source = "pantip topic page + render_comments"
    return r
