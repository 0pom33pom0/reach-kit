"""The only place reach-kit starts other programs.

Allowlisted tools only, argument lists only (never a shell), always a timeout.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import List

from .errors import ReachError

ALLOWED_TOOLS = ("yt-dlp", "gh")

INSTALL_HINTS = {
    "yt-dlp": "install it with `brew install yt-dlp` or `pipx install yt-dlp`",
    "gh": "install it from https://cli.github.com (optional: reach-kit falls back to the public GitHub API)",
}


def which(tool: str):
    if tool not in ALLOWED_TOOLS:
        raise ValueError(f"tool not allowed: {tool}")
    return shutil.which(tool)


def run_tool(tool: str, args: List[str], timeout: int = 60) -> str:
    """Run an allowlisted tool and return stdout. Raises ReachError on failure."""
    path = which(tool)
    if not path:
        raise ReachError("tool_missing", f"{tool} is not installed", INSTALL_HINTS[tool])
    try:
        proc = subprocess.run(
            [path, *args],
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise ReachError("timeout", f"{tool} did not finish within {timeout}s")
    except OSError as e:
        raise ReachError("tool_missing", f"cannot run {tool}: {e}", INSTALL_HINTS[tool])
    out = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise classify_tool_error(tool, err or out)
    return out


def classify_tool_error(tool: str, err: str) -> ReachError:
    last = [line for line in err.splitlines() if line.strip()]
    msg = last[-1] if last else f"{tool} failed"
    low = err.lower()
    if "ip address is blocked" in low or "http error 403" in low or "http error 429" in low or "rate-limit" in low:
        code = "blocked"
    elif "sign in" in low or "login" in low or "cookies" in low or "authentication" in low:
        code = "login_required"
    elif "http error 404" in low or "not found" in low or "unavailable" in low or "does not exist" in low:
        code = "not_found"
    elif "unsupported url" in low:
        code = "unsupported"
    else:
        code = "http_error"
    return ReachError(code, f"{tool}: {msg[:300]}")
