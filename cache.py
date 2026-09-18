from __future__ import annotations
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _iso_week() -> str:
    cal = datetime.now().isocalendar()
    return f"{cal.year}-W{cal.week:02d}"


def _cache_key(provider: str, query: str) -> str:
    raw = f"{provider}|{query}|{_iso_week()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_path(provider: str, query: str, cache_dir: Path) -> Path:
    return cache_dir / f"{_cache_key(provider, query)}.json"


def load_cache(provider: str, query: str, cache_dir: Path) -> Optional[dict]:
    p = cache_path(provider, query, cache_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        log.warning("Cache read error %s: %s", p, e)
        return None


def save_cache(provider: str, query: str, data: dict, cache_dir: Path) -> Path:
    p = cache_path(provider, query, cache_dir)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, default=str))
    tmp.rename(p)
    return p


class CacheStats:
    def __init__(self) -> None:
        self.hits = 0
        self.misses = 0

    def hit(self) -> None:
        self.hits += 1

    def miss(self) -> None:
        self.misses += 1

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.hits / self.total
