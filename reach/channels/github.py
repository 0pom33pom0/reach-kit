"""GitHub repos, issues and pull requests with comments.

Uses `gh` when installed (your auth, higher rate limits), otherwise the
public REST API (60 requests/hour per IP).
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import List

from .. import net, proc
from ..errors import ReachError
from ..model import Comment, Options, Result
from ..text import to_int

NAME = "github"
PATH_RE = re.compile(r"^/([\w.-]+)/([\w.-]+)(?:/(issues|pull|discussions)/(\d+))?/?$")


def match(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    return (parts.hostname or "").lower() in ("github.com", "www.github.com") and bool(PATH_RE.match(parts.path))


def api(path: str, opts: Options, raw: bool = False):
    """GET an API path via gh if available, else the public API."""
    if proc.which("gh"):
        args = ["api", path]
        if raw:
            args += ["-H", "Accept: application/vnd.github.raw"]
        out = proc.run_tool("gh", args, timeout=max(30, opts.timeout * 2))
        if raw:
            return out
        try:
            return json.loads(out)
        except ValueError:
            raise ReachError("parse_error", "gh returned invalid JSON")
    headers = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
    resp = net.http_get("https://api.github.com/" + path.lstrip("/"), headers=headers, timeout=opts.timeout)
    return resp.text() if raw else resp.json()


def _reactions(d: dict):
    return to_int((d.get("reactions") or {}).get("total_count"))


def read(url: str, opts: Options) -> Result:
    m = PATH_RE.match(urllib.parse.urlsplit(url).path)
    if not m:
        raise ReachError("unsupported", "supported: github.com/<owner>/<repo>[/issues|/pull/<n>]")
    owner, repo, kind, num = m.groups()
    if owner.strip(".") == "" or repo.strip(".") == "":
        # "github.com/../.." would make the API path point at your own account
        raise ReachError("invalid_url", "invalid GitHub owner or repository name")
    if kind == "discussions":
        raise ReachError("unsupported", "GitHub discussions are not supported yet; use `reach read` on the page with the web reader")
    if not kind:
        d = api(f"repos/{owner}/{repo}", opts)
        try:
            readme = api(f"repos/{owner}/{repo}/readme", opts, raw=True)
        except ReachError:
            readme = ""
        return Result(
            platform=NAME, url=d.get("html_url", url), title=d.get("full_name", f"{owner}/{repo}"),
            author=(d.get("owner") or {}).get("login", owner), published=d.get("created_at"),
            text=((d.get("description") or "") + "\n\n" + readme).strip(),
            stats={"stars": to_int(d.get("stargazers_count")), "forks": to_int(d.get("forks_count")),
                   "open_issues": to_int(d.get("open_issues_count")), "language": d.get("language"),
                   "license": (d.get("license") or {}).get("spdx_id"), "updated": d.get("pushed_at")},
            source="gh api" if proc.which("gh") else "api.github.com",
        )
    d = api(f"repos/{owner}/{repo}/issues/{num}", opts)
    r = Result(
        platform=NAME, url=d.get("html_url", url), title=f"#{num} {d.get('title', '')}",
        author=(d.get("user") or {}).get("login", ""), published=d.get("created_at"),
        text=(d.get("body") or "").strip(),
        stats={"state": d.get("state"), "comments": to_int(d.get("comments")), "reactions": _reactions(d),
               "type": "pull request" if d.get("pull_request") else "issue"},
        source="gh api" if proc.which("gh") else "api.github.com",
    )
    if opts.comments:
        # "top" needs a wider pool to rank; GitHub's maximum page size is 100.
        per = 100 if opts.sort == "top" else min(max(opts.limit, 1), 100)
        total = to_int(d.get("comments")) or 0
        page = 1
        if opts.sort == "new" and total > per:
            page = (total + per - 1) // per  # newest are on the last page
        raw = api(f"repos/{owner}/{repo}/issues/{num}/comments?per_page={per}&page={page}", opts)
        comments: List[Comment] = [
            Comment(author=(c.get("user") or {}).get("login", ""), text=(c.get("body") or "").strip(),
                    likes=_reactions(c), published=c.get("created_at"))
            for c in raw or []
        ]
        if opts.sort == "new":
            comments.reverse()
        elif opts.sort == "top":
            comments.sort(key=lambda c: c.likes or 0, reverse=True)
        r.comments = comments[: opts.limit]
    return r
