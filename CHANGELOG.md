# Changelog

## v1.0.0 — 2026-10-22

First release.

- Channels: web (Jina Reader → direct), search (Brave → Jina → DuckDuckGo), YouTube (info, comments, transcripts),
  TikTok, X (public embed endpoint), Facebook, Instagram, Reddit (public JSON → app-only OAuth), Pantip (topic +
  comments + replies), GitHub (repo, issues, PRs + comments), Hacker News, arXiv, RSS/Atom.
- Interfaces: `reach` CLI, MCP server (`reach mcp`, stdlib JSON-RPC), Claude Code skill (`reach install-skill`).
- `reach doctor` live-tests every channel.
- Security: zero dependencies, SSRF guard, no self-update, no stored cookies, untrusted-content markers.
