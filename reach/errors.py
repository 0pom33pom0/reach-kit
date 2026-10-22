from __future__ import annotations

from typing import List, Optional

# Stable error codes. Agents and scripts can branch on these.
CODES = (
    "blocked",         # the platform refused us (403/429/captcha/IP block)
    "not_found",       # 404 or the item does not exist
    "login_required",  # needs an account/cookies/API key we don't have
    "unsupported",     # we cannot do this for this platform at all
    "tool_missing",    # yt-dlp / gh not installed
    "timeout",
    "network",
    "invalid_url",
    "unsafe_url",      # blocked by the SSRF guard
    "parse_error",     # the platform changed its format
    "http_error",
    "conflict",        # e.g. a different skill is already installed
)


class ReachError(Exception):
    """An error that always says what failed, what was tried and what to do next."""

    def __init__(
        self,
        code: str,
        message: str,
        hint: str = "",
        tried: Optional[List[str]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code if code in CODES else "http_error"
        self.message = message
        self.hint = hint
        self.tried = list(tried or [])

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "tried": self.tried,
            "hint": self.hint,
        }

    def __str__(self) -> str:
        lines = [f"[{self.code}] {self.message}"]
        for t in self.tried:
            lines.append(f"  - tried: {t}")
        if self.hint:
            lines.append(f"  hint: {self.hint}")
        return "\n".join(lines)


def first_error(errors: List[ReachError], message: str, hint: str = "") -> ReachError:
    """Combine the errors of every fallback step into one ReachError."""
    tried = [f"{e.message} ({e.code})" for e in errors]
    # The most informative code wins: a block or a missing login beats a generic failure.
    order = ["login_required", "blocked", "not_found", "tool_missing", "unsupported", "timeout"]
    codes = [e.code for e in errors]
    code = next((c for c in order if c in codes), codes[0] if codes else "http_error")
    hints = [e.hint for e in errors if e.hint]
    return ReachError(code, message, hint or (hints[0] if hints else ""), tried)
