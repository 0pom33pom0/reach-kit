"""RSS 2.0 / Atom feeds with the standard library XML parser (no external entities)."""

from __future__ import annotations

import urllib.parse
from typing import List

from .. import net
from ..errors import ReachError
from ..model import Item, Options, Result
from ..text import clean, html_to_text, parse_xml

NAME = "rss"
ATOM = "{http://www.w3.org/2005/Atom}"
FEED_HINTS = (".rss", ".xml", ".atom", "/feed", "/rss", "format=rss")


def match(url: str) -> bool:
    low = url.lower()
    path = urllib.parse.urlsplit(low).path
    return any(path.endswith(h) or h in low for h in FEED_HINTS)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse(xml_text: str, url: str, limit: int) -> Result:
    root = parse_xml(xml_text)
    items: List[Item] = []
    title = ""
    if _local(root.tag) == "feed":  # Atom
        title = clean(root.findtext(f"{ATOM}title", ""))
        for e in root.findall(f"{ATOM}entry"):
            link = ""
            for ln in e.findall(f"{ATOM}link"):
                if ln.get("rel", "alternate") == "alternate":
                    link = ln.get("href", "")
                    break
            summary = e.findtext(f"{ATOM}summary") or e.findtext(f"{ATOM}content") or ""
            items.append(Item(
                title=clean(e.findtext(f"{ATOM}title", "")), url=link,
                snippet=html_to_text(summary)[:500],
                author=clean(e.findtext(f"{ATOM}author/{ATOM}name", "")),
                published=e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated"),
            ))
    else:  # RSS 2.0 / RDF
        channel = root.find("channel")
        title = clean(channel.findtext("title", "")) if channel is not None else ""
        for e in root.iter():
            if _local(e.tag) != "item":
                continue
            fields = {_local(c.tag): (c.text or "") for c in e}
            items.append(Item(
                title=clean(fields.get("title", "")), url=fields.get("link", "").strip(),
                snippet=html_to_text(fields.get("description", ""))[:500],
                author=clean(fields.get("creator") or fields.get("author", "")),
                published=fields.get("pubDate") or fields.get("date"),
            ))
    if not items and not title:
        raise ReachError("parse_error", "no RSS/Atom entries found")
    return Result(platform=NAME, url=url, title=title, items=items[:limit], source="rss")


def read(url: str, opts: Options) -> Result:
    resp = net.http_get(url, timeout=opts.timeout, browser=True,
                        headers={"Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"})
    return parse(resp.text(), url, opts.limit)
