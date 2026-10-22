# reach-kit

Let AI agents (Claude Code and any MCP client) **read web pages, social posts and their comments**:
YouTube, TikTok, X, Facebook, Instagram, Reddit, Pantip, GitHub, Hacker News, arXiv, RSS and any web page.

[ภาษาไทย](README.md) · **English**

## Why

- **Zero dependencies** — Python standard library only (`dependencies = []`). The whole codebase is readable in an afternoon.
- **No self-update, no telemetry** — it never downloads instructions or code; you upgrade by changing the pinned tag yourself.
- **No stored cookies** — anonymous by default; `--cookies-from-browser` is opt-in per command, CLI only, never cached.
- **Comments are first-class** — limit, sort (top/new), reply depth.
- **One output shape** for every platform (markdown or JSON), size budget, local cache.
- **Honest** — `reach doctor` really fetches a sample from each channel; every error says what was tried and how to fix it; auto-generated / machine-translated subtitles are always flagged.
- **Hardened** — SSRF guard (no localhost/LAN/metadata IPs, re-checked on redirects), fetched content wrapped as untrusted data against prompt injection.

## Support (no login)

| Platform | Content | Comments |
|---|---|---|
| Web pages | ✅ | — |
| YouTube | ✅ info + transcript | ✅ |
| TikTok | ✅ video info | 🟡 often blocked |
| X | ✅ single posts | ❌ |
| Facebook / Instagram | 🟡 public posts | ❌ |
| Reddit | ✅ (many networks need a free Reddit app) | ✅ |
| Pantip | ✅ | ✅ with replies |
| GitHub | ✅ repo / issue / PR | ✅ |
| Hacker News | ✅ | ✅ |
| arXiv / RSS | ✅ | — |
| Web search | ✅ with an API key | — |

Run `reach doctor` to see what works from your network right now.

## Install

```bash
brew install yt-dlp                       # or: pipx install yt-dlp
pipx install "git+https://github.com/0pom33pom0/reach-kit@v1.0.0"
reach install-skill                       # Claude Code skill → ~/.claude/skills/reach-kit
claude mcp add reach -- reach mcp         # optional: MCP server
reach doctor
```

## Use

```bash
reach read <url> [--comments]
reach comments <url> --limit 100 --sort new --depth 1
reach transcript <youtube-url> --lang th,en
reach search "query"        reach feed <rss-url>
reach hn top|new|search "q" reach arxiv "query"
reach doctor
```

Common options: `--json`, `--max-chars N`, `--limit N`, `--no-cache`, `--timeout S`.

## Optional environment variables

| Variable | Purpose |
|---|---|
| `BRAVE_API_KEY` | web search via Brave Search API (free tier) — recommended |
| `JINA_API_KEY` | Jina search + higher Jina Reader limits |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit official API, app-only OAuth (create a "script" app at reddit.com/prefs/apps) |
| `REACH_NO_JINA=1` | never send URLs to Jina Reader |
| `REACH_CACHE_DIR` | cache location (default `~/.cache/reach-kit`) |

## Updating

There is no auto-update. Review `https://github.com/0pom33pom0/reach-kit/compare/<old>...<new>` and the [CHANGELOG](CHANGELOG.md), then `pipx install --force "git+https://github.com/0pom33pom0/reach-kit@<new>"` and `reach install-skill --force`.

## Security

See [SECURITY.md](SECURITY.md). Every rule there is enforced by a test.

## License

[MIT](LICENSE)
