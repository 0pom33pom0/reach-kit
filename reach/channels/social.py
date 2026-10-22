"""TikTok, X (Twitter), Facebook and Instagram — public posts, no login by default."""

from __future__ import annotations

import re
import urllib.parse

from .. import net
from ..errors import ReachError, first_error
from ..model import Options, Result
from ..text import to_int
from . import web, ytdlp

PLATFORMS = {
    "tiktok": ("tiktok.com",),
    "x": ("x.com", "twitter.com", "fxtwitter.com", "vxtwitter.com"),
    "facebook": ("facebook.com", "fb.watch", "fb.com"),
    "instagram": ("instagram.com",),
}
NO_COMMENTS = {
    "x": "X replies cannot be read without logging in; reach-kit shows the post only",
    "facebook": "Facebook comments cannot be read without logging in; reach-kit shows the post only",
    "instagram": "Instagram comments cannot be read without logging in; reach-kit shows the post only",
}
COOKIE_WARNING = (
    "using your browser cookies: the platform sees requests as your account "
    "(automated use can get accounts limited or banned)"
)


def platform_of(url: str):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    for name, hosts in PLATFORMS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return name
    return None


def match(url: str) -> bool:
    return platform_of(url) is not None


# ---- X ----------------------------------------------------------------------

STATUS_RE = re.compile(r"/status(?:es)?/(\d+)")


def parse_x_syndication(data: dict, url: str) -> Result:
    if not data or data.get("__typename") == "TweetTombstone":
        raise ReachError("not_found", "this post is deleted, private or age-restricted")
    user = data.get("user") or {}
    text = data.get("text") or ""
    media = [m.get("media_url_https") for m in data.get("mediaDetails") or [] if m.get("media_url_https")]
    if media:
        text += "\n\nmedia: " + " ".join(media)
    quoted = data.get("quoted_tweet")
    if quoted:
        qu = (quoted.get("user") or {}).get("screen_name", "")
        text += f"\n\nquoting @{qu}: {quoted.get('text', '')}"
    name, handle = user.get("name", ""), user.get("screen_name", "")
    return Result(
        platform="x",
        url=f"https://x.com/{handle}/status/{data.get('id_str')}" if handle else url,
        title=f"{name} (@{handle})" if handle else "",
        author=f"@{handle}" if handle else name,
        published=data.get("created_at"),
        text=text.strip(),
        stats={"likes": to_int(data.get("favorite_count")), "replies": to_int(data.get("conversation_count"))},
        source="x embed (cdn.syndication.twimg.com)",
    )


def read_x(url: str, opts: Options) -> Result:
    m = STATUS_RE.search(urllib.parse.urlsplit(url).path)
    if not m:
        raise ReachError("unsupported", "only X post URLs (…/status/<id>) are supported without login",
                         "for profiles or search, use a web search instead")
    tid = m.group(1)
    resp = net.http_get(
        f"https://cdn.syndication.twimg.com/tweet-result?id={tid}&lang=en&token=a",
        timeout=opts.timeout, browser=True,
    )
    return parse_x_syndication(resp.json(), url)


# ---- TikTok -----------------------------------------------------------------

def read_tiktok_oembed(url: str, opts: Options) -> Result:
    data = net.http_get("https://www.tiktok.com/oembed?url=" + urllib.parse.quote(url, safe=""),
                        timeout=opts.timeout).json()
    if not data.get("title") and not data.get("author_name"):
        raise ReachError("blocked", "TikTok oEmbed returned no details for this video")
    return Result(platform="tiktok", url=url, title=data.get("title", ""),
                  author=data.get("author_name", ""), text=data.get("title", ""),
                  source="tiktok oembed")


# ---- dispatcher -------------------------------------------------------------

def read(url: str, opts: Options) -> Result:
    platform = platform_of(url)
    if platform is None:
        raise ReachError("unsupported", f"not a social URL: {url}")
    errors = []
    steps = []
    if platform == "x":
        steps.append(("x embed", lambda: read_x(url, opts)))
    steps.append(("yt-dlp", lambda: ytdlp.to_result(
        ytdlp.info(url, opts, comments=opts.comments and platform == "tiktok"), platform, url, opts)))
    if platform == "tiktok":
        steps.append(("tiktok oembed", lambda: read_tiktok_oembed(url, opts)))
    if web.jina_enabled():
        steps.append(("jina reader", lambda: web.read_via_jina(url, opts, platform)))

    for _, step in steps:
        try:
            r = step()
            break
        except ReachError as e:
            if e.code in ("unsafe_url", "invalid_url"):
                raise
            errors.append(e)
    else:
        hint = "" if opts.cookies_from_browser else (
            "the post may be private or the platform is blocking anonymous access; "
            "you can retry with --cookies-from-browser chrome (uses your login, ban risk)"
        )
        raise first_error(errors, f"could not read this {platform} post", hint)

    r.platform = platform
    if errors:
        r.warnings.append(f"earlier methods failed: {'; '.join(e.message for e in errors)}")
    if opts.cookies_from_browser:
        r.warnings.append(COOKIE_WARNING)
    if opts.comments and platform in NO_COMMENTS:
        r.warnings.append(NO_COMMENTS[platform])
        if r.comments is None:
            r.comments = []
    if opts.comments and platform == "tiktok" and r.comments is None:
        r.comments = []
        r.warnings.append("TikTok comments could not be fetched with this method")
    return r
