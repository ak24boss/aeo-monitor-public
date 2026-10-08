"""Fake clients for offline testing — no API keys, no network calls."""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from providers.base import ProviderResponse

import pandas as pd


class FakeFirecrawlClient:
    """Drop-in for AEOFirecrawlClient with deterministic fixture responses."""

    def search(self, query: str, limit: int = 10) -> dict:
        return {
            "web": [
                {
                    "url": "https://g2.com/compare/lido",
                    "title": "G2 Compare Lido",
                    "description": "Compare Lido with alternatives on G2.",
                    "position": 1,
                    "category": "organic",
                    "markdown": None,
                },
                {
                    "url": "https://example.com/ai-answer",
                    "title": "AI Overview",
                    "description": "AI answer about document extraction.",
                    "position": 1,
                    "category": "ai_overview",
                    "markdown": "Lido is a document extraction tool used by finance teams.",
                },
            ]
        }

    def scrape(self, url: str) -> dict:
        return {
            "url": url,
            "markdown": "Lido is mentioned here. nanonets is a competitor. rossum is also used.",
            "title": "Test Page",
            "modified_time": None,
        }

    def map_site(self, url: str, limit: int = 50) -> list[str]:
        return [f"{url}/page1", f"{url}/page2"]

    def get_credits_remaining(self) -> Optional[int]:
        return 500


class FakePerplexityResponse:
    """Callable that returns a mock httpx.Response-like object."""

    def __init__(self):
        self._data = {
            "citations": ["https://g2.com/lido"],
            "choices": [{"message": {"annotations": []}}],
        }

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


class FakeTrendReq:
    """Drop-in for pytrends.request.TrendReq."""

    def __init__(self, hl: str = "en-US", tz: int = 360, **kwargs):
        self._keywords: list[str] = []

    def build_payload(self, keywords: list[str], cat: int = 0, timeframe: str = "today 12-m", **kwargs) -> None:
        self._keywords = list(keywords)

    def interest_over_time(self) -> pd.DataFrame:
        if not self._keywords:
            return pd.DataFrame()
        kw = self._keywords[0]
        idx = pd.date_range("2026-01-01", periods=2, freq="W")
        return pd.DataFrame({kw: [45, 50]}, index=idx)

    def related_queries(self) -> dict:
        if not self._keywords:
            return {}
        kw = self._keywords[0]
        return {kw: {"rising": pd.DataFrame({"query": ["lido ocr", "lido excel"]})}}


class FakeMockProvider:
    """Provider that mentions the brand name in its response — tests mention detection."""

    engine_name = "mock"

    def __init__(self, brand_name: str = "Lido"):
        self._brand_name = brand_name

    def run(self, probe_text: str, probe_id: str) -> ProviderResponse:
        return ProviderResponse(
            engine="mock",
            probe_id=probe_id,
            response_text=(
                f"{self._brand_name} is one of the leading tools for this use case. "
                "See https://g2.com/lido and https://capterra.com/lido for reviews."
            ),
            cited_urls=["https://g2.com/lido", "https://capterra.com/lido"],
            raw={"mock": True},
        )


class FakeSilentMockProvider:
    """Provider that does NOT mention the brand — tests the absent-brand path."""

    engine_name = "mock"

    def run(self, probe_text: str, probe_id: str) -> ProviderResponse:
        return ProviderResponse(
            engine="mock",
            probe_id=probe_id,
            response_text=(
                "nanonets and rossum are popular choices for document extraction. "
                "See https://g2.com/nanonets and https://capterra.com for comparisons."
            ),
            cited_urls=["https://g2.com/nanonets", "https://capterra.com"],
            raw={"mock": True},
        )
