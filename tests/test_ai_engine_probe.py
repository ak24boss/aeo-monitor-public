"""Tests for ai_engine_probe.py (Phase 4A) — all offline, no API keys."""
from __future__ import annotations
from datetime import date

import duckdb
import pytest

from ai_engine_probe import run_ai_engine_probe_phase
from cache import CacheStats
from db import get_connection
from models import ProbeConfig
from tests.fakes import FakeMockProvider, FakeSilentMockProvider


COMPANY_NAME = "Lido"
COMPETITORS = {"nanonets.com", "rossum.ai"}
RUN_DATE = date(2026, 10, 6)

PROBES = [
    ProbeConfig(id="p1", text="best document extraction software?", intent="tool discovery", priority="high"),
    ProbeConfig(id="p2", text="how to automate invoices?", intent="use case", priority="medium"),
]


@pytest.fixture()
def conn(tmp_path):
    db = tmp_path / "test.db"
    return get_connection(db)


@pytest.fixture()
def cache(tmp_path):
    d = tmp_path / "cache"
    d.mkdir()
    return d


def test_probe_brand_mentioned_detected(conn, cache):
    provider = FakeMockProvider(brand_name="Lido")
    rows = run_ai_engine_probe_phase(
        PROBES, [provider], conn, COMPANY_NAME, COMPETITORS, cache, CacheStats(), RUN_DATE
    )
    assert len(rows) == 2
    assert all(r.brand_mentioned for r in rows)
    assert all(r.brand_context is not None for r in rows)


def test_probe_brand_absent(conn, cache):
    provider = FakeSilentMockProvider()
    rows = run_ai_engine_probe_phase(
        PROBES, [provider], conn, COMPANY_NAME, COMPETITORS, cache, CacheStats(), RUN_DATE
    )
    assert len(rows) == 2
    assert all(not r.brand_mentioned for r in rows)


def test_probe_competitor_detection(conn, cache):
    provider = FakeSilentMockProvider()
    rows = run_ai_engine_probe_phase(
        PROBES, [provider], conn, COMPANY_NAME, COMPETITORS, cache, CacheStats(), RUN_DATE
    )
    all_competitors = {c for r in rows for c in r.competitors_mentioned}
    assert "nanonets.com" in all_competitors


def test_probe_inserts_to_db(conn, cache):
    provider = FakeMockProvider()
    run_ai_engine_probe_phase(
        PROBES, [provider], conn, COMPANY_NAME, COMPETITORS, cache, CacheStats(), RUN_DATE
    )
    count = conn.execute(
        "SELECT COUNT(*) FROM ae_probe_results WHERE run_date = ?", [RUN_DATE]
    ).fetchone()[0]
    assert count == len(PROBES)


def test_probe_cache_hit(conn, cache):
    provider = FakeMockProvider()
    stats = CacheStats()
    # First run populates cache
    run_ai_engine_probe_phase(PROBES, [provider], conn, COMPANY_NAME, COMPETITORS, cache, stats, RUN_DATE)
    hits_after_first = stats.hits

    # Second run should hit cache for all probes
    stats2 = CacheStats()
    run_ai_engine_probe_phase(PROBES, [provider], conn, COMPANY_NAME, COMPETITORS, cache, stats2, RUN_DATE)
    assert stats2.hits == len(PROBES)
    assert stats2.misses == 0


def test_probe_dry_run_skips_provider(conn, cache, monkeypatch):
    called = []

    class TrackingProvider(FakeSilentMockProvider):
        def run(self, probe_text, probe_id):
            called.append(probe_id)
            return super().run(probe_text, probe_id)

    run_ai_engine_probe_phase(
        PROBES, [TrackingProvider()], conn, COMPANY_NAME, COMPETITORS,
        cache, CacheStats(), RUN_DATE, dry_run=True,
    )
    assert called == [], "dry_run=True should not call provider.run()"


def test_probe_multiple_providers(conn, cache):
    p1 = FakeMockProvider(brand_name="Lido")
    p2 = FakeSilentMockProvider()
    rows = run_ai_engine_probe_phase(
        [PROBES[0]], [p1, p2], conn, COMPANY_NAME, COMPETITORS, cache, CacheStats(), RUN_DATE
    )
    assert len(rows) == 2


def test_probe_empty_probes_skips_cleanly(conn, cache):
    provider = FakeMockProvider()
    rows = run_ai_engine_probe_phase(
        [], [provider], conn, COMPANY_NAME, COMPETITORS, cache, CacheStats(), RUN_DATE
    )
    assert rows == []
