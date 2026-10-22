"""HTML → text and small formatting helpers (standard library only)."""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from typing import List, Optional

from .errors import ReachError

_SKIP = {"script", "style", "noscript", "svg", "template", "head", "nav", "footer", "form", "iframe"}
_BLOCK = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr", "main", "aside",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in _SKIP:
            self.skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3") and not self.skip:
            self.parts.append("#" * int(tag[1]) + " ")
        if tag == "li" and not self.skip:
            self.parts.append("- ")

    def handle_startendtag(self, tag, attrs):
        if tag in ("br", "hr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in _SKIP and self.skip:
            self.skip -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self.skip:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    """Readable plain text from an HTML fragment or page."""
    p = _TextExtractor()
    try:
        p.feed(markup)
        p.close()
    except Exception:  # malformed HTML must never crash a read
        return clean(re.sub(r"<[^>]+>", " ", html.unescape(markup)))
    return clean("".join(p.parts))


def html_title(markup: str) -> str:
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)', markup, re.I)
    if m:
        return html.unescape(m.group(1)).strip()
    m = re.search(r"<title[^>]*>(.*?)</title>", markup, re.I | re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def iso_from_unix(ts) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(float(ts)), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def iso_from_yyyymmdd(s) -> Optional[str]:
    if not s or len(str(s)) != 8:
        return None
    s = str(s)
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def iso_from_bangkok(s: str) -> Optional[str]:
    """Pantip style 'MM/DD/YYYY HH:MM:SS' in Bangkok time → ISO 8601 with +07:00."""
    try:
        dt = datetime.strptime(s.strip(), "%m/%d/%Y %H:%M:%S")
    except (ValueError, AttributeError):
        return None
    return dt.replace(tzinfo=timezone(timedelta(hours=7))).isoformat()


def to_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_xml(text: str):
    """Parse untrusted XML. Any entity declaration anywhere is refused (billion-laughs)."""
    if "<!ENTITY" in text:
        raise ReachError("parse_error", "XML declares entities; refusing to parse it")
    try:
        return ET.fromstring(text.lstrip("\ufeff").strip())
    except ET.ParseError as e:
        raise ReachError("parse_error", f"invalid XML: {e}")
