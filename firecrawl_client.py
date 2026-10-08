from __future__ import annotations
import logging
import time
import re
from typing import Optional

from firecrawl.v2.client import FirecrawlClient
from firecrawl.v2.types import ScrapeOptions

log = logging.getLogger(__name__)

_RATE_LIMIT_DEFAULT_WAIT = 60  # seconds to wait when no retry-after hint


def _retry_after(exc: Exception) -> int:
    """Parse 'retry after Ns' from a RateLimitError message, defaulting to 60s."""
    msg = str(exc)
    m = re.search(r"retry after (\d+)s", msg)
    return int(m.group(1)) + 2 if m else _RATE_LIMIT_DEFAULT_WAIT


class AEOFirecrawlClient:
    """Thin wrapper around firecrawl-py v2 FirecrawlClient."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY is required")
        self._client = FirecrawlClient(api_key=api_key)
        self._key_prefix = api_key[:8] + "..."

    def search(self, query: str, limit: int = 10) -> dict:
        """
        Run a web search. Returns a dict with key 'web' containing a list of result dicts.
        Each result has: url, title, description, position, category.
        Retries once on RateLimitError with the suggested backoff.
        """
        for attempt in range(2):
            try:
                result = self._client.search(query, limit=limit)
                break
            except Exception as exc:
                if "RateLimitError" in type(exc).__name__ and attempt == 0:
                    wait = _retry_after(exc)
                    log.warning("Firecrawl rate limit — waiting %ds before retry", wait)
                    time.sleep(wait)
                else:
                    raise
        web = result.web or []
        return {
            "web": [
                {
                    "url": getattr(r, "url", None) or "",
                    "title": getattr(r, "title", None),
                    "description": getattr(r, "description", None),
                    "position": getattr(r, "position", None),
                    "category": getattr(r, "category", None),
                    "markdown": getattr(r, "markdown", None),
                }
                for r in web
                if getattr(r, "url", None)
            ]
        }

    def scrape(self, url: str) -> dict:
        """Scrape a URL and return markdown content plus metadata. Retries once on rate limit."""
        for attempt in range(2):
            try:
                doc = self._client.scrape(url, formats=["markdown"])
                break
            except Exception as exc:
                if "RateLimitError" in type(exc).__name__ and attempt == 0:
                    wait = _retry_after(exc)
                    log.warning("Firecrawl rate limit (scrape) — waiting %ds", wait)
                    time.sleep(wait)
                else:
                    raise
        metadata = doc.metadata or {}
        return {
            "url": url,
            "markdown": doc.markdown or "",
            "title": getattr(metadata, "title", None),
            "modified_time": getattr(metadata, "modified_time", None),
        }

    def map_site(self, url: str, limit: int = 50) -> list[str]:
        """Return list of URLs found on a site (used for dry-run estimation)."""
        result = self._client.map(url, limit=limit)
        links = getattr(result, "links", None) or []
        return [getattr(lnk, "url", lnk) if not isinstance(lnk, str) else lnk for lnk in links]

    def get_credits_remaining(self) -> Optional[int]:
        try:
            usage = self._client.get_credit_usage()
            return getattr(usage, "remaining_credits", None)
        except Exception as e:
            log.warning("Could not fetch credit usage: %s", e)
            return None
