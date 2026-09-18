from __future__ import annotations
import pytest
from cache import load_cache, save_cache, CacheStats


def test_cache_miss_returns_none(tmp_path):
    assert load_cache("fc", "some query", tmp_path) is None


def test_round_trip(tmp_path):
    data = {"web": [{"url": "https://example.com", "position": 1}]}
    save_cache("fc", "my query", data, tmp_path)
    loaded = load_cache("fc", "my query", tmp_path)
    assert loaded == data


def test_different_providers_different_keys(tmp_path):
    data = {"citations": ["https://g2.com"]}
    save_cache("fc", "query", data, tmp_path)
    # Different provider = different cache key
    assert load_cache("perplexity", "query", tmp_path) is None


def test_same_query_different_text_miss(tmp_path):
    data = {"web": []}
    save_cache("fc", "query A", data, tmp_path)
    assert load_cache("fc", "query B", tmp_path) is None


def test_cache_stats_rate():
    stats = CacheStats()
    stats.hit()
    stats.hit()
    stats.miss()
    assert stats.total == 3
    assert stats.rate == pytest.approx(2 / 3)


def test_cache_stats_zero_total():
    stats = CacheStats()
    assert stats.rate == 0.0
    assert stats.total == 0
