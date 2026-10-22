"""`reach` command line."""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, core, doctor
from .errors import ReachError
from .model import Options
from .render import to_json, to_markdown

SKILL_SRC = Path(__file__).parent / "skill"
DEFAULT_SKILL_TARGET = Path.home() / ".claude" / "skills" / "reach-kit"

# Kept in one place so tests can check SKILL.md, the CLI and the MCP tools agree.
COMMANDS = ("read", "comments", "transcript", "search", "feed", "hn", "arxiv", "doctor", "install-skill", "mcp")


def _common(p: argparse.ArgumentParser, comments: bool = False) -> None:
    p.add_argument("--json", action="store_true", help="output JSON instead of markdown")
    p.add_argument("--max-chars", type=int, default=20000, help="output size budget (default 20000)")
    p.add_argument("--limit", type=int, default=None, help="number of comments / items")
    p.add_argument("--timeout", type=int, default=20, help="network timeout in seconds")
    p.add_argument("--no-cache", action="store_true", help="ignore cached results")
    p.add_argument("--cookies-from-browser", metavar="BROWSER", default=None,
                   help="(yt-dlp platforms only) use your browser login, e.g. chrome. Ban risk; never stored")
    if comments:
        p.add_argument("--sort", choices=("top", "new"), default="top")
        p.add_argument("--depth", type=int, default=2, help="1 = top-level comments only (default 2)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="reach",
        description="Read the web, social posts and their comments. Standard library only, no self-update.",
    )
    ap.add_argument("--version", action="version", version=f"reach-kit {__version__}")
    sub = ap.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("read", help="read any URL (platform is detected automatically)")
    p.add_argument("url")
    p.add_argument("--comments", action="store_true", help="include comments when the platform supports it")
    _common(p, comments=True)

    p = sub.add_parser("comments", help="read comments of a post/video/topic")
    p.add_argument("url")
    _common(p, comments=True)

    p = sub.add_parser("transcript", help="YouTube subtitles as plain text")
    p.add_argument("url")
    p.add_argument("--lang", default="", help="preferred languages, e.g. th,en")
    _common(p)

    p = sub.add_parser("search", help="web search")
    p.add_argument("query")
    _common(p)

    p = sub.add_parser("feed", help="read an RSS/Atom feed")
    p.add_argument("url")
    _common(p)

    p = sub.add_parser("hn", help="Hacker News: top | new | search <query>")
    p.add_argument("mode", choices=("top", "new", "search"))
    p.add_argument("query", nargs="?", default="")
    _common(p)

    p = sub.add_parser("arxiv", help="search arXiv papers")
    p.add_argument("query")
    _common(p)

    p = sub.add_parser("doctor", help="live-test every channel")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("install-skill", help="copy the Claude Code skill into ~/.claude/skills/reach-kit")
    p.add_argument("--target", default=str(DEFAULT_SKILL_TARGET))
    p.add_argument("--force", action="store_true", help="overwrite an existing, different skill")

    sub.add_parser("mcp", help="run the MCP server on stdio")
    return ap


def options_from(args: argparse.Namespace) -> Options:
    o = Options()
    if getattr(args, "limit", None) is not None:
        o.limit = max(1, args.limit)
    elif args.command in ("search", "hn", "arxiv"):
        o.limit = 10
    elif args.command == "feed":
        o.limit = 20
    for name in ("max_chars", "timeout", "no_cache", "cookies_from_browser", "sort", "depth"):
        if hasattr(args, name):
            setattr(o, name, getattr(args, name))
    o.timeout = max(1, o.timeout)
    o.depth = max(1, o.depth)
    if getattr(args, "lang", ""):
        o.lang = [x.strip() for x in args.lang.split(",") if x.strip()]
    if getattr(args, "comments", False):
        o.comments = True
    return o


def _differs(src: Path, dst: Path) -> bool:
    cmp = filecmp.dircmp(src, dst)

    def walk(c) -> bool:
        if c.left_only or c.right_only or c.diff_files or c.funny_files:
            return True
        return any(walk(s) for s in c.subdirs.values())

    return walk(cmp)


def install_skill(target: str, force: bool) -> str:
    dst = Path(target).expanduser()
    if dst.exists():
        if not _differs(SKILL_SRC, dst):
            return f"skill already up to date at {dst}"
        if not force:
            raise ReachError(
                "conflict", f"a different skill already exists at {dst}",
                "it may contain your own edits; re-run with --force to replace it",
            )
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SKILL_SRC, dst, ignore=shutil.ignore_patterns("__pycache__"))
    return f"installed skill to {dst}"


def run(argv: Optional[List[str]] = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.command:
        ap.print_help()
        return 2
    as_json = getattr(args, "json", False)
    try:
        if args.command == "mcp":
            from .mcp_server import serve
            serve()
            return 0
        if args.command == "doctor":
            report = doctor.run()
            print(json.dumps(report, ensure_ascii=False, indent=2) if as_json else doctor.to_text(report))
            return 0 if all(c["status"] != "fail" for c in report["channels"]) else 1
        if args.command == "install-skill":
            print(install_skill(args.target, args.force))
            return 0
        o = options_from(args)
        if args.command == "read":
            r = core.read(args.url, o)
        elif args.command == "comments":
            r = core.comments(args.url, o)
        elif args.command == "transcript":
            r = core.transcript(args.url, o)
        elif args.command == "search":
            r = core.search(args.query, o)
        elif args.command == "feed":
            r = core.feed(args.url, o)
        elif args.command == "hn":
            r = core.hn_list(args.mode, args.query, o)
        elif args.command == "arxiv":
            r = core.arxiv_search(args.query, o)
        else:  # pragma: no cover
            ap.error(f"unknown command {args.command}")
            return 2
        print(to_json(r) if as_json else to_markdown(r))
        return 0
    except ReachError as e:
        if as_json:
            print(json.dumps({"error": e.to_dict()}, ensure_ascii=False, indent=2))
        else:
            print(str(e), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Thai text on Windows consoles
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(run())


if __name__ == "__main__":
    main()
