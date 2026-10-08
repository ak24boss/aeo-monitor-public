"""Tests for cross_reference.py (Phase 4B) — in-memory DuckDB, no API calls."""
from __future__ import annotations
import json
from datetime import date

import pytest

from cross_reference import _priority, run_cross_reference_phase
from db import get_connection, insert_ae_probe_results, insert_citation_graph, insert_cross_reference, insert_source_analysis
from models import AEProbeRow, CitationRow, CrossReferenceRow, SourceAnalysisRow


RUN_DATE = date(2026, 10, 6)


@pytest.fixture()
def conn(tmp_path):
    return get_connection(tmp_path / "test.db")


def _seed_citation_graph(conn, url: str, score: float, queries_in: int = 3):
    insert_citation_graph(conn, [CitationRow(
        run_date=RUN_DATE, url=url, domain=url.split("/")[2],
        domain_type="listicle", weighted_score=score,
        queries_appearing_in=queries_in, top_position=1,
    )])


def _seed_probe_result(conn, cited_urls: list[str], engine: str = "mock", probe_id: str = "p1"):
    insert_ae_probe_results(conn, [AEProbeRow(
        run_date=RUN_DATE, engine=engine, probe_id=probe_id,
        probe_text="test probe", brand_mentioned=False,
        cited_urls=cited_urls,
        cited_domains=[u.split("/")[2] for u in cited_urls if "/" in u],
    )])


def test_priority_critical():
    assert _priority(2.0, 3) == "critical"


def test_priority_high_ai_cited():
    assert _priority(0.6, 1) == "high"


def test_priority_high_serp_only():
    assert _priority(1.6, 0) == "high"


def test_priority_medium():
    assert _priority(0.3, 0) == "medium"


def test_cross_ref_critical_priority(conn):
    url = "https://g2.com/compare"
    _seed_citation_graph(conn, url, score=2.0)
    _seed_probe_result(conn, cited_urls=[url])

    rows = run_cross_reference_phase(conn, RUN_DATE, "testco.com", "TestCo")
    assert len(rows) == 1
    assert rows[0].action_priority == "critical"
    assert rows[0].engine_citation_count == 1


def test_cross_ref_brand_present_excluded(conn):
    url = "https://g2.com/compare"
    _seed_citation_graph(conn, url, score=2.0)
    insert_source_analysis(conn, [SourceAnalysisRow(
        run_date=RUN_DATE, url=url, brand_mentioned=True,
        brand_context="TestCo is listed here.",
    )])
    _seed_probe_result(conn, cited_urls=[url])

    rows = run_cross_reference_phase(conn, RUN_DATE, "testco.com", "TestCo")
    assert rows == []


def test_cross_ref_no_probe_data_skips(conn):
    url = "https://g2.com/compare"
    _seed_citation_graph(conn, url, score=2.0)
    # No ae_probe_results seeded

    rows = run_cross_reference_phase(conn, RUN_DATE, "testco.com", "TestCo")
    assert rows == []


def test_cross_ref_inserts_to_db(conn):
    url = "https://capterra.com/list"
    _seed_citation_graph(conn, url, score=0.8)
    _seed_probe_result(conn, cited_urls=[url])

    run_cross_reference_phase(conn, RUN_DATE, "testco.com", "TestCo")

    count = conn.execute(
        "SELECT COUNT(*) FROM cross_reference WHERE run_date = ?", [RUN_DATE]
    ).fetchone()[0]
    assert count == 1
