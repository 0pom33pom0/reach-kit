# reach-kit platform notes

## Web pages
- First tries Jina Reader (`r.jina.ai`, a third-party service that sees the URL), then a direct fetch with HTML→text.
- `REACH_NO_JINA=1` disables Jina entirely.
- Only public `http`/`https` addresses are allowed. Local and private network addresses are refused (`unsafe_url`).

## Search
- With `BRAVE_API_KEY` → Brave Search API. With `JINA_API_KEY` → Jina Search.
- Without keys → DuckDuckGo HTML, which often shows a bot check (`blocked`).

## YouTube
- Needs `yt-dlp`. Comments: `--limit` top-level threads, up to 5 replies each when `--depth` ≥ 2. Comment dates are approximate (YouTube only says "3 years ago").
- `transcript` prefers human subtitles in the original or requested language. Auto-generated or machine-translated captions are always flagged in `warnings`.

## TikTok
- Video info via `yt-dlp`, then TikTok oEmbed, then Jina. Comments are frequently blocked for anonymous users; the result says so.

## X (Twitter)
- Single posts via X's public embed endpoint (`cdn.syndication.twimg.com`), then `yt-dlp` (video posts), then Jina.
- Replies, profiles, timelines and search are not available without login.

## Facebook / Instagram
- Public videos and posts via `yt-dlp`, then Jina. Comments are not available without login.

## Reddit
- Public `.json` first. Reddit blocks many networks (HTTP 403). The reliable route is your own free "script" app:
  1. Go to https://www.reddit.com/prefs/apps → "create another app" → type **script**.
  2. Set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in your environment.
  This uses app-only OAuth: no account login, no cookies. The token is kept in memory only.

## Pantip
- Topic page + Pantip's comment feed. Up to 500 comments (5 pages); Pantip includes up to 5 replies per comment.
- Members' IPs, e-mails and IDs present in Pantip's feed are never output.

## GitHub
- Repos (with README), issues and pull requests with comments. Uses `gh` if installed (your auth), otherwise the public API (60 requests/hour).

## Hacker News
- Items and comment trees via the Algolia API. HN has no comment scores, so `--sort top` keeps thread order.

## arXiv
- Paper metadata and abstract via the official export API. Search with `reach arxiv "<query>"`.

## RSS / Atom
- `reach feed <url>`. XML entity declarations are refused.

## Cookies
- `--cookies-from-browser <browser>` (CLI only, yt-dlp platforms only) lets yt-dlp read your browser login for that one command. reach-kit never stores cookies, never caches results fetched with them, and does not offer this option over MCP.
