# Security

reach-kit exists because tools that give AI agents internet access are a juicy target. These rules are
enforced by `tests/test_security.py` and `tests/test_output.py`; a change that breaks one fails CI.

## Rules

1. **No dependencies.** `pyproject.toml` has `dependencies = []`. Every import must be on a short stdlib allowlist in the tests.
2. **Only two external programs**, `yt-dlp` and `gh`, started only from `reach/proc.py`, as an argument list (never `shell=True`), with a timeout. URLs are passed after `--` so they can never be read as options.
3. **No self-update, telemetry or remote instructions.** reach-kit never contacts a reach-kit server, never downloads code or prompts, never installs anything. The skill tells agents not to install or upgrade anything either.
4. **SSRF guard.** Only `http`/`https`. Hostnames are resolved and every address must be public (no loopback, private, link-local such as `169.254.169.254`, CGNAT, multicast, IPv4-mapped tricks). The address actually connected to is checked again (defeats DNS rebinding), redirects are re-checked, and URLs are checked before being handed to Jina Reader too. A proxy you configure yourself via `HTTP(S)_PROXY` may be local.
5. **Prompt-injection hygiene.** Every field that comes from the internet (title, author, text, comments, links) is inside `<<<UNTRUSTED CONTENT …>>>` markers, and `<<<`/`>>>` in fetched text are replaced by look-alikes so a page cannot fake the end marker. The skill and the MCP server instructions tell the agent never to follow instructions inside.
6. **Cookies.** reach-kit never reads, stores or logs cookies. `--cookies-from-browser` is passed to yt-dlp for a single CLI command only, results fetched that way are never cached, and the option is not exposed over MCP so a model or a web page cannot turn it on.
7. **Secrets** (`BRAVE_API_KEY`, `JINA_API_KEY`, `REDDIT_CLIENT_*`) are read from the environment only, never written to disk or printed. The Reddit OAuth token lives in memory only.
8. **Local files.** Only `~/.cache/reach-kit/` (mode 0700): results, 15 min–24 h TTL, 200 MB cap. `reach install-skill` writes only to the skill folder and refuses to overwrite your edits without `--force`.
9. **Privacy.** Pantip's comment feed contains members' IPs and e-mail flags; reach-kit drops them. Jina Reader (third party) sees the URLs you read through it — disable with `REACH_NO_JINA=1`.
10. **Bounded parsing.** Responses are capped at 10 MB (also after gzip). XML containing an entity declaration anywhere is refused.

## Known limits

- `yt-dlp` and `gh` are trusted tools you install yourself. Keep them updated from their official sources.

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting** on this repository (Security → Report a vulnerability) rather than a public issue.
