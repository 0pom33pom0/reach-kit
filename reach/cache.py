"""Small on-disk cache under ~/.cache/reach-kit (0700). Stores results only, never cookies or keys."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

TTL_SECONDS = 24 * 3600
MAX_TOTAL_BYTES = 200 * 1024 * 1024


def cache_dir() -> Path:
    base = os.environ.get("REACH_CACHE_DIR")
    if base:
        return Path(base)
    xdg = os.environ.get("XDG_CACHE_HOME")
    return Path(xdg) / "reach-kit" if xdg else Path.home() / ".cache" / "reach-kit"


def _path(key: str) -> Path:
    return cache_dir() / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")


def get(key: str, ttl: int = TTL_SECONDS) -> Optional[dict]:
    p = _path(key)
    try:
        if time.time() - p.stat().st_mtime > min(ttl, TTL_SECONDS):
            p.unlink()
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def put(key: str, value: dict) -> None:
    d = cache_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
        tmp = _path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _path(key))
        _prune(d)
    except OSError:
        pass  # caching is best-effort; never fail a read because of it


def _prune(d: Path) -> None:
    files = []
    now = time.time()
    for p in d.glob("*.json"):
        try:
            st = p.stat()
        except OSError:
            continue
        if now - st.st_mtime > TTL_SECONDS:
            try:
                p.unlink()
            except OSError:
                pass
            continue
        files.append((st.st_mtime, st.st_size, p))
    total = sum(f[1] for f in files)
    for _, size, p in sorted(files):
        if total <= MAX_TOTAL_BYTES:
            break
        try:
            p.unlink()
        except OSError:
            pass
        total -= size


def clear() -> int:
    n = 0
    for p in cache_dir().glob("*.json"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    return n
