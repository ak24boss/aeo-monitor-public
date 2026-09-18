from __future__ import annotations
import math
import pytest
from datetime import date
from citation_graph import _decay_weight, build_citation_graph, get_top_non_brand_urls
from models import SerpResult


TODAY = date(2026, 8, 31)
BRAND = "acme.com"
COMPETITORS: set[str] = {"nanonets.com", "rossum.ai"}


def _serp(url: str, domain: str, query: str, position: int) -> SerpResult:
    return SerpResult(
        run_date=TODAY,
        query=query,
        position=position,
        url=url,
        domain=domain,
    )


def test_decay_weight_position_1():
    assert _decay_weight(1) == pytest.approx(1.0)


def test_decay_weight_position_2():
    assert _decay_weight(2) == pytest.approx(1.0 / math.log2(3))


def test_decay_weight_position_10():
    assert _decay_weight(10) == pytest.approx(1.0 / math.log2(11))


def test_decay_weight_zero_returns_zero():
    assert _decay_weight(0) == 0.0


def test_decay_weight_negative_returns_zero():
    assert _decay_weight(-1) == 0.0


def test_build_citation_graph_aggregates_same_url():
    results = [
        _serp("https://g2.com/compare/acme", "g2.com", "best OCR", 1),
        _serp("https://g2.com/compare/acme", "g2.com", "invoice extraction", 3),
    ]
    graph = build_citation_graph(results, BRAND, COMPETITORS, TODAY)
    assert len(graph) == 1
    row = graph[0]
    assert row.url == "https://g2.com/compare/acme"
    assert row.weighted_score == pytest.approx(_decay_weight(1) + _decay_weight(3), rel=1e-3)
    assert row.queries_appearing_in == 2
    assert row.top_position == 1


def test_build_citation_graph_multiple_urls():
    results = [
        _serp("https://g2.com/compare/acme", "g2.com", "best OCR", 1),
        _serp("https://capterra.com/acme", "capterra.com", "best OCR", 2),
    ]
    graph = build_citation_graph(results, BRAND, COMPETITORS, TODAY)
    assert len(graph) == 2
    assert graph[0].weighted_score > graph[1].weighted_score


def test_build_citation_graph_skips_ai_overview():
    results = [
        SerpResult(run_date=TODAY, query="test", position=0, url="about:ai_overview", domain=""),
    ]
    graph = build_citation_graph(results, BRAND, COMPETITORS, TODAY)
    assert len(graph) == 0


def test_build_citation_graph_sorted_by_score():
    results = [
        _serp("https://low.com", "low.com", "q1", 10),
        _serp("https://high.com", "high.com", "q1", 1),
    ]
    graph = build_citation_graph(results, BRAND, COMPETITORS, TODAY)
    assert graph[0].weighted_score > graph[1].weighted_score


def test_brand_urls_filtered_from_top():
    results = [
        _serp("https://acme.com/blog", "acme.com", "q1", 1),
        _serp("https://g2.com/acme", "g2.com", "q1", 2),
    ]
    graph = build_citation_graph(results, BRAND, COMPETITORS, TODAY)
    top = get_top_non_brand_urls(graph, n=10)
    urls = [r.url for r in top]
    assert "https://acme.com/blog" not in urls
    assert "https://g2.com/acme" in urls


def test_get_top_non_brand_urls_respects_n():
    results = [
        _serp(f"https://site{i}.com/page", f"site{i}.com", "q1", i + 1)
        for i in range(10)
    ]
    graph = build_citation_graph(results, BRAND, COMPETITORS, TODAY)
    top = get_top_non_brand_urls(graph, n=3)
    assert len(top) == 3
