"""Shared yt-dlp helpers (YouTube, TikTok, X video, Facebook, Instagram)."""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from .. import proc
from ..errors import ReachError
from ..model import Comment, Options, Result
from ..text import iso_from_unix, iso_from_yyyymmdd, to_int


def info(url: str, opts: Options, comments: bool = False, extractor_args: Optional[str] = None) -> dict:
    args = [
        "-J", "--skip-download", "--no-warnings", "--no-playlist",
        "--socket-timeout", str(opts.timeout),
    ]
    if opts.cookies_from_browser:
        args += ["--cookies-from-browser", opts.cookies_from_browser]
    if comments:
        args.append("--write-comments")
    if extractor_args:
        args += ["--extractor-args", extractor_args]
    args += ["--", url]  # "--" stops a URL from ever being read as an option
    out = proc.run_tool("yt-dlp", args, timeout=max(60, opts.timeout * 6))
    try:
        data = json.loads(out)
    except ValueError:
        raise ReachError("parse_error", "yt-dlp returned invalid JSON")
    if not isinstance(data, dict):
        raise ReachError("not_found", "yt-dlp returned no data for this URL")
    return data


def build_tree(raw: List[dict], opts: Options) -> List[Comment]:
    """yt-dlp gives a flat list with `parent` ('root' or a comment id)."""
    nodes: Dict[str, Comment] = {}
    roots: List[Comment] = []
    order: List[tuple] = []
    for c in raw or []:
        node = Comment(
            author=c.get("author") or "",
            text=(c.get("text") or "").strip(),
            likes=to_int(c.get("like_count")),
            # yt-dlp derives comment times from "3 years ago"; only the date is meaningful
            published=(iso_from_unix(c.get("timestamp")) or "")[:10] or None,
        )
        nodes[str(c.get("id"))] = node
        order.append((c.get("parent") or "root", node, to_int(c.get("timestamp")) or 0))
    for parent, node, _ in order:
        if parent == "root":
            roots.append(node)
        elif opts.depth > 1 and parent in nodes:
            nodes[parent].replies.append(node)
    if opts.sort == "new":
        stamp = {id(n): ts for _, n, ts in order}
        roots.sort(key=lambda n: stamp.get(id(n), 0), reverse=True)
    elif opts.sort == "top":
        roots.sort(key=lambda n: n.likes or 0, reverse=True)
    return roots[: opts.limit]


def to_result(data: dict, platform: str, url: str, opts: Options) -> Result:
    published = iso_from_unix(data.get("timestamp")) or iso_from_yyyymmdd(data.get("upload_date"))
    title = (data.get("title") or "")[:200]
    text = data.get("description") or ""
    r = Result(
        platform=platform,
        url=data.get("webpage_url") or url,
        title=title,
        author=data.get("uploader") or data.get("channel") or data.get("creator") or "",
        published=published,
        text=text.strip(),
        stats={
            "views": to_int(data.get("view_count")),
            "likes": to_int(data.get("like_count")),
            "comments": to_int(data.get("comment_count")),
            "duration_s": to_int(data.get("duration")),
        },
        source="yt-dlp",
    )
    if opts.comments:
        raw = data.get("comments") or []
        r.comments = build_tree(raw, opts)
        if raw:
            # with --write-comments yt-dlp overwrites comment_count with the number it fetched
            r.stats["comments"] = None
            r.stats["comments_fetched"] = len(raw)
        elif (r.stats.get("comments") or 0) > 0:
            r.warnings.append(
                f"{platform} reported {r.stats['comments']} comments but returned none "
                "(the platform is likely blocking anonymous comment access)"
            )
    return r
