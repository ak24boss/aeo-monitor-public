from __future__ import annotations
import pytest
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
import duckdb

from cache import save_cache, CacheStats
from ae_citations import query_perplexity, run_ae_phase
from models import QueryConfig
from db import SCHEMA_SQL

TODAY = date(2026, 8, 31)

QUERY = QueryConfig(
    text="best document extraction software",
    intent="tool discovery",
    vertical="general",
    priority="high",
    category="commercial",
)

PERPLEXITY_RESPONSE = {
    "citations": ["https://g2.com/lido", "https://capterra.com/lido"],
    "choices": [{"message": {"annotations": []}}],
}


def _make_conn():
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_SQL)
    return conn


class _FakeSettings:
    def __init__(self, perplexity_api_key=None, cache_dir=None):
        self.perplexity_api_key = perplexity_api_key
        self.cache_dir = cache_dir


def test_perplexity_cache_hit(tmp_path):
    save_cache("perplexity", QUERY.text, PERPLEXITY_RESPONSE, tmp_path)
    stats = CacheStats()
    rows = query_perplexity(QUERY, "fake-key", tmp_path, stats, TODAY)
    assert len(rows) == 2
    assert rows[0].cited_url == "https://g2.com/lido"
    assert rows[0].position_in_response == 1
    assert stats.hits == 1
    assert stats.misses == 0


def test_perplexity_dry_run_on_cache_miss(tmp_path):
    stats = CacheStats()
    rows = query_perplexity(QUERY, "fake-key", tmp_path, stats, TODAY, dry_run=True)
    assert rows == []
    assert stats.misses == 1
    assert stats.hits == 0


def test_perplexity_skip_when_no_key(tmp_path):
    conn = _make_conn()
    settings = _FakeSettings(perplexity_api_key=None, cache_dir=tmp_path)
    stats = CacheStats()
    rows = run_ae_phase([QUERY], settings, conn, stats, TODAY)
    assert rows == []


def test_perplexity_annotations_format(tmp_path):
    """Handles OpenRouter annotation format (no top-level citations[])."""
    annotation_response = {
        "citations": [],
        "choices": [
            {
                "message": {
                    "annotations": [
                        {"type": "url_citation", "url_citation": {"url": "https://g2.com/lido"}},
                        {"type": "url_citation", "url_citation": {"url": "https://capterra.com/lido"}},
                    ]
                }
            }
        ],
    }
    save_cache("perplexity", QUERY.text, annotation_response, tmp_path)
    stats = CacheStats()
    rows = query_perplexity(QUERY, "fake-key", tmp_path, stats, TODAY)
    assert len(rows) == 2
    assert rows[0].cited_domain == "g2.com"


def test_perplexity_cited_domain_extracted(tmp_path):
    save_cache("perplexity", QUERY.text, PERPLEXITY_RESPONSE, tmp_path)
    stats = CacheStats()
    rows = query_perplexity(QUERY, "fake-key", tmp_path, stats, TODAY)
    assert rows[0].cited_domain == "g2.com"
    assert rows[1].cited_domain == "capterra.com"
