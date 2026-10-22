"""arXiv papers via the official export API (Atom)."""

from __future__ import annotations

import re
import urllib.parse
from typing import List

from .. import net
from ..errors import ReachError
from ..model import Item, Options, Result
from ..text import clean, parse_xml

NAME = "arxiv"
API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}
ID_RE = re.compile(r"/(?:abs|pdf|html)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?/?$")


def match(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    return (parts.hostname or "").lower() in ("arxiv.org", "www.arxiv.org") and bool(ID_RE.search(parts.path))


def _one_line(s: str) -> str:
    return " ".join((s or "").split())


def parse_feed(xml_text: str) -> List[Item]:
    root = parse_xml(xml_text)
    items = []
    for e in root.findall("a:entry", NS):
        authors = [_one_line(a.findtext("a:name", "", NS)) for a in e.findall("a:author", NS)]
        items.append(Item(
            title=_one_line(e.findtext("a:title", "", NS)),
            url=clean(e.findtext("a:id", "", NS)).replace("http://", "https://"),
            snippet=clean(e.findtext("a:summary", "", NS)),
            author=", ".join(authors),
            published=e.findtext("a:published", None, NS),
        ))
    return items


def read(url: str, opts: Options) -> Result:
    m = ID_RE.search(urllib.parse.urlsplit(url).path)
    if not m:
        raise ReachError("invalid_url", "arXiv URLs look like https://arxiv.org/abs/<id>")
    items = parse_feed(net.http_get(f"{API}?id_list={urllib.parse.quote(m.group(1))}", timeout=opts.timeout).text())
    if not items or not items[0].title:
        raise ReachError("not_found", f"arXiv paper {m.group(1)} not found")
    p = items[0]
    return Result(platform=NAME, url=p.url, title=p.title, author=p.author, published=p.published,
                  text=p.snippet, source="export.arxiv.org")


def search(query: str, opts: Options) -> Result:
    n = min(max(opts.limit, 1), 50)
    q = urllib.parse.urlencode({"search_query": f"all:{query}", "max_results": n, "sortBy": "relevance"})
    items = parse_feed(net.http_get(f"{API}?{q}", timeout=opts.timeout).text())
    for it in items:
        it.snippet = it.snippet[:500]
    return Result(platform=NAME, url="https://arxiv.org/", title=f"arXiv search: {query}", items=items,
                  source="export.arxiv.org")
