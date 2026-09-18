from __future__ import annotations
import pytest
from datetime import date
from pathlib import Path
from cache import save_cache, CacheStats
from harvest import harvest_serp
from models import QueryConfig
from tests.fakes import FakeFirecrawlClient

TODAY = date(2026, 8, 31)

QUERY = QueryConfig(
    text="best OCR software",
    intent="tool discovery",
    vertical="general",
    priority="high",
    category="commercial",
)

FAKE_SERP = {
    "web": [
        {
            "url": "https://g2.com/compare/lido",
            "title": "G2",
            "description": "Compare tools",
            "position": 1,
            "category": "organic",
            "markdown": None,
        }
    ]
}


def test_harvest_serp_cache_hit(tmp_path):
    save_cache("firecrawl_search", QUERY.text, FAKE_SERP, tmp_path)
    stats = CacheStats()
    results = harvest_serp(QUERY, FakeFirecrawlClient(), tmp_path, stats, TODAY)
    assert len(results) == 1
    assert results[0].url == "https://g2.com/compare/lido"
    assert stats.hits == 1
    assert stats.misses == 0


def test_harvest_serp_dry_run_on_cache_miss(tmp_path):
    stats = CacheStats()
    results = harvest_serp(QUERY, FakeFirecrawlClient(), tmp_path, stats, TODAY, dry_run=True)
    assert results == []
    assert stats.misses == 1
    assert stats.hits == 0


def test_harvest_serp_live_call_uses_fake_client(tmp_path):
    stats = CacheStats()
    results = harvest_serp(QUERY, FakeFirecrawlClient(), tmp_path, stats, TODAY, dry_run=False)
    # FakeFirecrawlClient returns 1 organic + 1 ai_overview; only organic becomes a result
    assert len(results) == 1
    assert results[0].url == "https://g2.com/compare/lido"
    assert stats.misses == 1


def test_harvest_serp_attaches_ai_overview_to_first_result(tmp_path):
    stats = CacheStats()
    results = harvest_serp(QUERY, FakeFirecrawlClient(), tmp_path, stats, TODAY, dry_run=False)
    # AI overview text should be attached to the first organic result
    assert results[0].ai_overview_box is not None
    assert "Lido" in results[0].ai_overview_box


def test_harvest_serp_result_has_correct_fields(tmp_path):
    stats = CacheStats()
    results = harvest_serp(QUERY, FakeFirecrawlClient(), tmp_path, stats, TODAY, dry_run=False)
    r = results[0]
    assert r.run_date == TODAY
    assert r.query == QUERY.text
    assert r.domain == "g2.com"
    assert r.position == 1
