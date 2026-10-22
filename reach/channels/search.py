"""Web search.

Keyed providers are reliable; keyless scraping is often blocked:
  1. Brave Search API  (BRAVE_API_KEY — free tier at https://brave.com/search/api/)
  2. Jina Search       (JINA_API_KEY)
  3. DuckDuckGo HTML   (no key; frequently shows a bot check)
Inside Claude Code, the built-in WebSearch tool is usually the better choice.
"""

from __future__ import annotations

import html
import os
import re
import urllib.parse
from typing import List

from .. import net
from ..errors import ReachError, first_error
from ..model import Item, Options, Result
from ..text import html_to_text

NAME = "search"
NO_KEY_HINT = (
    "keyless search is blocked from this network. Set BRAVE_API_KEY (free tier: "
    "https://brave.com/search/api/) or JINA_API_KEY, or use your agent's built-in web search"
)


def brave(query: str, n: int, opts: Options) -> List[Item]:
    key = os.environ["BRAVE_API_KEY"]
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": query, "count": n})
    data = net.http_get(url, headers={"X-Subscription-Token": key, "Accept": "application/json"},
                        timeout=opts.timeout).json()
    return [Item(title=r.get("title", ""), url=r.get("url", ""), snippet=html_to_text(r.get("description", "")),
                 published=r.get("page_age"))
            for r in (data.get("web") or {}).get("results", [])]


def jina(query: str, n: int, opts: Options) -> List[Item]:
    key = os.environ["JINA_API_KEY"]
    url = "https://s.jina.ai/?" + urllib.parse.urlencode({"q": query})
    data = net.http_get(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                                      "X-Respond-With": "no-content"}, timeout=max(opts.timeout, 30)).json()
    return [Item(title=r.get("title", ""), url=r.get("url", ""),
                 snippet=(r.get("description") or r.get("content") or "")[:400])
            for r in (data.get("data") or [])][:n]


def parse_ddg(markup: str) -> List[Item]:
    if "anomaly" in markup and "result__a" not in markup:
        raise ReachError("blocked", "DuckDuckGo showed a bot check")
    items = []
    anchors = list(re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
                               r'|<a[^>]*href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>', markup, re.S))
    for i, a in enumerate(anchors):
        href = html.unescape(a.group(1) or a.group(3))
        label = a.group(2) or a.group(4) or ""
        if "uddg=" in href:
            href = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get("uddg", [href])[0]
        if "duckduckgo.com/y.js" in href or not href.startswith("http"):  # ads / internal
            continue
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(markup)
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|div|td)>', markup[a.end():end], re.S)
        items.append(Item(title=html_to_text(label), url=href,
                          snippet=html_to_text(snip.group(1)) if snip else ""))
    return items


def ddg(query: str, n: int, opts: Options) -> List[Item]:
    resp = net.http_get("https://html.duckduckgo.com/html/", data={"q": query}, browser=True, timeout=opts.timeout)
    items = parse_ddg(resp.text())
    if not items:
        raise ReachError("blocked", "DuckDuckGo returned no results (possibly a bot check)")
    return items[:n]


def search(query: str, opts: Options) -> Result:
    query = query.strip()
    if not query:
        raise ReachError("invalid_url", "empty search query")
    n = min(max(opts.limit, 1), 20)
    providers = []
    if os.environ.get("BRAVE_API_KEY"):
        providers.append(("brave", brave))
    if os.environ.get("JINA_API_KEY"):
        providers.append(("jina", jina))
    providers.append(("duckduckgo", ddg))
    errors = []
    for name, fn in providers:
        try:
            items = fn(query, n, opts)
            r = Result(platform=NAME, url="", title=f"search: {query}", items=items, source=name)
            if errors:
                r.warnings.append("; ".join(e.message for e in errors))
            return r
        except ReachError as e:
            errors.append(e)
    has_key = len(providers) > 1
    raise first_error(errors, f"web search failed for {query!r}", "" if has_key else NO_KEY_HINT)
