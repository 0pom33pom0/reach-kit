from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Options:
    comments: bool = False
    limit: int = 50              # comments or list items
    sort: str = "top"            # top | new
    depth: int = 2               # 1 = top-level comments only
    lang: List[str] = field(default_factory=list)
    max_chars: int = 20000
    cookies_from_browser: Optional[str] = None
    timeout: int = 20
    no_cache: bool = False


@dataclass
class Comment:
    author: str = ""
    text: str = ""
    likes: Optional[int] = None
    published: Optional[str] = None
    replies: List["Comment"] = field(default_factory=list)


@dataclass
class Item:
    """One entry of a list result (search hits, feed entries, front pages)."""

    title: str = ""
    url: str = ""
    snippet: str = ""
    author: str = ""
    published: Optional[str] = None
    stats: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    platform: str
    url: str
    title: str = ""
    author: str = ""
    published: Optional[str] = None
    text: str = ""
    stats: Dict[str, Any] = field(default_factory=dict)
    comments: Optional[List[Comment]] = None
    items: Optional[List[Item]] = None
    source: str = ""
    warnings: List[str] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["comments"] is None:
            del d["comments"]
        if d["items"] is None:
            del d["items"]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Result":
        d = dict(d)

        def comment(c: dict) -> Comment:
            return Comment(
                author=c.get("author", ""),
                text=c.get("text", ""),
                likes=c.get("likes"),
                published=c.get("published"),
                replies=[comment(r) for r in c.get("replies", [])],
            )

        if d.get("comments") is not None:
            d["comments"] = [comment(c) for c in d["comments"]]
        if d.get("items") is not None:
            d["items"] = [Item(**i) for i in d["items"]]
        return cls(**d)


def count_comments(comments: Optional[List[Comment]]) -> int:
    if not comments:
        return 0
    return sum(1 + count_comments(c.replies) for c in comments)
