"""Reddit posts, subreddits and comment trees.

Order: public .json → official API with your own app (REDDIT_CLIENT_ID /
REDDIT_CLIENT_SECRET, app-only OAuth: no account login, no cookies).
Reddit blocks anonymous access from many networks, so the app route is the
reliable one. The token lives in memory only.
"""

from __future__ import annotations

import base64
import os
import urllib.parse
from typing import List, Optional

from .. import net
from ..errors import ReachError, first_error
from ..model import Comment, Item, Options, Result
from ..text import iso_from_unix, to_int

NAME = "reddit"
HOSTS = ("reddit.com", "redd.it")
APP_HINT = (
    "Reddit blocks anonymous access from this network. Create a free 'script' app at "
    "https://www.reddit.com/prefs/apps and set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET "
    "(no account login or cookies needed)"
)
_token: Optional[str] = None


def match(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in HOSTS)


def _path(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path.rstrip("/")
    if host == "redd.it" or host.endswith(".redd.it"):
        path = "/comments" + path  # redd.it/<id> → /comments/<id>
    if path.endswith(".json"):
        path = path[:-5].rstrip("/")
    return path or "/"


def _query(opts: Options, is_post: bool) -> str:
    q = {"raw_json": "1", "limit": str(min(max(opts.limit, 1), 100))}
    if is_post:
        q["sort"] = "new" if opts.sort == "new" else "top"
        q["depth"] = str(max(opts.depth, 1))
    return urllib.parse.urlencode(q)


def _app_token(timeout: int) -> Optional[str]:
    global _token
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return None
    if _token:
        return _token
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    resp = net.http_get(
        "https://www.reddit.com/api/v1/access_token",
        headers={"Authorization": f"Basic {auth}"},
        data={"grant_type": "client_credentials"},
        timeout=timeout,
    )
    _token = (resp.json() or {}).get("access_token")
    if not _token:
        raise ReachError("login_required", "Reddit rejected REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET")
    return _token


def fetch(url: str, opts: Options):
    path = _path(url)
    is_post = "/comments/" in path + "/"
    query = _query(opts, is_post)
    errors: List[ReachError] = []
    try:
        return net.http_get(f"https://www.reddit.com{path}.json?{query}", timeout=opts.timeout).json(), "reddit public json"
    except ReachError as e:
        if e.code in ("not_found", "unsafe_url"):
            raise
        errors.append(e)
    try:
        token = _app_token(opts.timeout)
    except ReachError as e:
        errors.append(e)
        token = None
    if token:
        try:
            return net.http_get(f"https://oauth.reddit.com{path}?{query}",
                                headers={"Authorization": f"Bearer {token}"},
                                timeout=opts.timeout).json(), "reddit api (app-only oauth)"
        except ReachError as e:
            errors.append(e)
    raise first_error(errors, "could not read Reddit", "" if token else APP_HINT)


def _comments(children, opts: Options, depth: int) -> List[Comment]:
    out: List[Comment] = []
    for ch in children or []:
        if ch.get("kind") != "t1":
            continue
        d = ch.get("data") or {}
        replies = []
        if depth < opts.depth and isinstance(d.get("replies"), dict):
            replies = _comments(d["replies"].get("data", {}).get("children"), opts, depth + 1)
        out.append(Comment(
            author=d.get("author") or "[deleted]",
            text=(d.get("body") or "").strip(),
            likes=to_int(d.get("score")),
            published=iso_from_unix(d.get("created_utc")),
            replies=replies,
        ))
    return out


def parse(data, url: str, opts: Options) -> Result:
    if isinstance(data, list) and data:  # a post: [post listing, comment listing]
        post = (data[0].get("data", {}).get("children") or [{}])[0].get("data", {})
        r = Result(
            platform=NAME,
            url="https://www.reddit.com" + post.get("permalink", "") if post.get("permalink") else url,
            title=post.get("title", ""),
            author=post.get("author", ""),
            published=iso_from_unix(post.get("created_utc")),
            text=(post.get("selftext") or post.get("url_overridden_by_dest") or "").strip(),
            stats={"score": to_int(post.get("score")), "comments": to_int(post.get("num_comments")),
                   "subreddit": post.get("subreddit_name_prefixed")},
        )
        if opts.comments and len(data) > 1:
            r.comments = _comments(data[1].get("data", {}).get("children"), opts, 1)[: opts.limit]
        return r
    if isinstance(data, dict) and data.get("kind") == "Listing":  # subreddit / listing
        items = []
        for ch in data.get("data", {}).get("children", []):
            d = ch.get("data") or {}
            if ch.get("kind") != "t3":
                continue
            items.append(Item(
                title=d.get("title", ""),
                url="https://www.reddit.com" + d.get("permalink", ""),
                snippet=(d.get("selftext") or "")[:300],
                author=d.get("author", ""),
                published=iso_from_unix(d.get("created_utc")),
                stats={"score": to_int(d.get("score")), "comments": to_int(d.get("num_comments"))},
            ))
        return Result(platform=NAME, url=url, title=_path(url), items=items[: opts.limit])
    raise ReachError("parse_error", "unexpected Reddit response format")


def read(url: str, opts: Options) -> Result:
    data, source = fetch(url, opts)
    r = parse(data, url, opts)
    r.source = source
    return r
