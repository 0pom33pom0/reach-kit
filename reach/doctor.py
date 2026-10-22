"""`reach doctor`: really fetch a known sample from every channel and report.

No guessing from "is the tool installed": each probe makes the same request a
real read would make, in parallel, with a hard time limit.
"""

from __future__ import annotations

import concurrent.futures as cf
import os
from typing import Callable, Dict, List, Tuple

from . import proc
from .channels import arxiv, github, hn, pantip, reddit, search, social, web, youtube
from .errors import ReachError
from .model import Options

OK, PARTIAL, FAIL = "ok", "partial", "fail"
ICON = {OK: "✅", PARTIAL: "🟡", FAIL: "❌"}
PROBE_TIMEOUT = 25


def _opts(**kw) -> Options:
    o = Options(timeout=12, limit=3, no_cache=True)
    for k, v in kw.items():
        setattr(o, k, v)
    return o


def p_web() -> Tuple[str, str]:
    r = web.read("https://example.com/", _opts())
    return OK, f"read example.com via {r.source}"


def p_search() -> Tuple[str, str]:
    r = search.search("wikipedia", _opts())
    if not r.items:
        return FAIL, "no results"
    return OK, f"{len(r.items)} results via {r.source}"


def p_youtube() -> Tuple[str, str]:
    r = youtube.read("https://www.youtube.com/watch?v=jNQXAC9IVRw", _opts(comments=True))
    if r.comments:
        return OK, "video info + comments"
    return PARTIAL, "video info works, comments returned none"


def p_tiktok() -> Tuple[str, str]:
    r = social.read("https://www.tiktok.com/@tiktok/video/7106594312292453675", _opts(comments=True))
    if r.comments:
        return OK, "video info + comments"
    return PARTIAL, f"video info via {r.source}; comments blocked from this network"


def p_x() -> Tuple[str, str]:
    r = social.read_x("https://x.com/jack/status/20", _opts())
    return (PARTIAL, "public posts readable; replies need login") if r.text else (FAIL, "empty post")


def p_facebook() -> Tuple[str, str]:
    social.read("https://www.facebook.com/watch/?v=10153231379946729", _opts())
    return PARTIAL, "public videos readable; comments need login"


def p_reddit() -> Tuple[str, str]:
    reddit.read("https://www.reddit.com/r/announcements/", _opts())
    return OK, "listing + comments"


def p_pantip() -> Tuple[str, str]:
    r = pantip.read("https://pantip.com/topic/43000000", _opts(comments=True))
    return OK, f"topic + {len(r.comments or [])} comments"


def p_github() -> Tuple[str, str]:
    github.read("https://github.com/cli/cli", _opts())
    via = "gh (authenticated)" if proc.which("gh") else "public API (60 req/hour)"
    return OK, f"via {via}"


def p_hn() -> Tuple[str, str]:
    hn.read("https://news.ycombinator.com/item?id=1", _opts(comments=True))
    return OK, "story + comment tree"


def p_arxiv() -> Tuple[str, str]:
    arxiv.read("https://arxiv.org/abs/1706.03762", _opts())
    return OK, "paper metadata + abstract"


PROBES: Dict[str, Callable[[], Tuple[str, str]]] = {
    "web": p_web, "search": p_search, "youtube": p_youtube, "tiktok": p_tiktok, "x": p_x,
    "facebook": p_facebook, "reddit": p_reddit, "pantip": p_pantip, "github": p_github,
    "hn": p_hn, "arxiv": p_arxiv,
}
NEEDS_YTDLP = {"youtube"}  # other social probes have non-yt-dlp fallbacks


def _run(name: str) -> dict:
    try:
        status, detail = PROBES[name]()
        return {"channel": name, "status": status, "detail": detail, "hint": ""}
    except ReachError as e:
        return {"channel": name, "status": FAIL, "detail": f"[{e.code}] {e.message}", "hint": e.hint}
    except Exception as e:  # a probe must never crash doctor
        return {"channel": name, "status": FAIL, "detail": f"unexpected error: {e!r}", "hint": ""}


def tools() -> List[dict]:
    out = []
    for t in proc.ALLOWED_TOOLS:
        path = proc.which(t)
        version = ""
        if path:
            try:
                version = proc.run_tool(t, ["--version"], timeout=15).strip().splitlines()[0]
            except ReachError as e:
                version = f"error: {e.message}"
        out.append({"tool": t, "installed": bool(path), "version": version, "hint": "" if path else proc.INSTALL_HINTS[t]})
    return out


def run() -> dict:
    tool_info = tools()
    have_ytdlp = any(t["tool"] == "yt-dlp" and t["installed"] for t in tool_info)
    results: Dict[str, dict] = {}
    names = list(PROBES)
    ex = cf.ThreadPoolExecutor(max_workers=len(names))
    try:
        futures = {}
        for n in names:
            if n in NEEDS_YTDLP and not have_ytdlp:
                results[n] = {"channel": n, "status": FAIL, "detail": "yt-dlp is not installed",
                              "hint": proc.INSTALL_HINTS["yt-dlp"]}
                continue
            futures[ex.submit(_run, n)] = n
        done, pending = cf.wait(futures, timeout=PROBE_TIMEOUT * 2)
        for f in done:
            results[futures[f]] = f.result()
        for f in pending:
            n = futures[f]
            results[n] = {"channel": n, "status": FAIL, "detail": "timed out", "hint": ""}
    finally:
        ex.shutdown(wait=False)
    env = {k: bool(os.environ.get(k)) for k in
           ("BRAVE_API_KEY", "JINA_API_KEY", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REACH_NO_JINA")}
    return {"tools": tool_info, "channels": [results[n] for n in names], "env": env}


def to_text(report: dict) -> str:
    lines = ["reach-kit doctor", "", "Tools:"]
    for t in report["tools"]:
        mark = "✅" if t["installed"] else "❌"
        lines.append(f"  {mark} {t['tool']:7} {t['version'] or 'not installed'}")
        if t["hint"]:
            lines.append(f"       → {t['hint']}")
    lines += ["", "Channels (live test):"]
    for c in report["channels"]:
        lines.append(f"  {ICON[c['status']]} {c['channel']:9} {c['detail']}")
        if c["hint"]:
            lines.append(f"       → {c['hint']}")
    set_keys = [k for k, v in report["env"].items() if v]
    lines += ["", "Optional settings in use: " + (", ".join(set_keys) if set_keys else "none")]
    return "\n".join(lines)
