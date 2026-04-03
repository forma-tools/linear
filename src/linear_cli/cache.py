"""File-based TTL cache for API responses.

Cache directory resolution:
  1. LINEAR_CACHE_DIR environment variable
  2. Platform default: ~/Library/Caches/linear (macOS)
     ~/.cache/linear (Linux) / %LOCALAPPDATA%/linear/cache (Win)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path


class ResponseCache:
    """File-based TTL cache for API responses."""

    def __init__(self, cache_dir: Path | None = None):
        self._dir = cache_dir or self._default_dir()

    def _default_dir(self) -> Path:
        env_dir = os.environ.get("LINEAR_CACHE_DIR")
        if env_dir:
            return Path(env_dir)
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Caches"
        else:
            base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        return base / "linear"

    @staticmethod
    def key(*parts: str) -> str:
        """Build deterministic cache key from parts."""
        raw = ":".join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, key: str, ttl: int | None = 300) -> dict | None:
        """Get cached data if within TTL. ttl=None means permanent."""
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            if ttl is not None:
                if time.time() - entry.get("cached_at", 0) > ttl:
                    path.unlink(missing_ok=True)
                    return None
            return entry.get("data")
        except (json.JSONDecodeError, KeyError, OSError):
            path.unlink(missing_ok=True)
            return None

    def set(self, key: str, data) -> None:
        """Store response data."""
        self._dir.mkdir(parents=True, exist_ok=True)
        entry = {"cached_at": time.time(), "data": data}
        try:
            (self._dir / f"{key}.json").write_text(json.dumps(entry, default=str), encoding="utf-8")
        except OSError:
            pass

    def clear(self) -> int:
        """Remove all cached entries. Returns count removed."""
        if not self._dir.exists():
            return 0
        count = 0
        for f in self._dir.glob("*.json"):
            f.unlink(missing_ok=True)
            count += 1
        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        if not self._dir.exists():
            return {
                "cache_dir": str(self._dir),
                "entries": 0,
                "active": 0,
                "expired": 0,
                "size_bytes": 0,
            }
        entries = list(self._dir.glob("*.json"))
        total_size = 0
        active = expired = 0
        for f in entries:
            total_size += f.stat().st_size
            try:
                json.loads(f.read_text(encoding="utf-8"))
                active += 1
            except (json.JSONDecodeError, OSError):
                expired += 1
        return {
            "cache_dir": str(self._dir),
            "entries": len(entries),
            "active": active,
            "expired": expired,
            "size_bytes": total_size,
        }
