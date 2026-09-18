from __future__ import annotations
import pytest
from utils import extract_domain, classify_domain, classify_domain_with_url, estimate_credit_cost
from models import QueryConfig
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

COMPETITORS = {"nanonets.com", "rossum.ai", "parseur.com", "docsumo.com"}


@dataclass
class _FakeSettings:
    top_urls_for_analysis: int
    perplexity_api_key: Optional[str] = None


def test_extract_domain_strips_www():
    assert extract_domain("https://www.g2.com/foo/bar") == "g2.com"


def test_extract_domain_no_www():
    assert extract_domain("https://capterra.com/reviews/acme") == "capterra.com"


def test_classify_brand():
    assert classify_domain("acme.com", "acme.com", COMPETITORS) == "brand_owned"


def test_classify_brand_subdomain():
    assert classify_domain("app.acme.com", "acme.com", COMPETITORS) == "brand_owned"


def test_classify_review_platform():
    assert classify_domain("g2.com", "acme.com", COMPETITORS) == "review_platform"


def test_classify_reddit():
    assert classify_domain("reddit.com", "acme.com", COMPETITORS) == "reddit_forum"
    assert classify_domain("old.reddit.com", "acme.com", COMPETITORS) == "reddit_forum"


def test_classify_competitor():
    assert classify_domain("nanonets.com", "acme.com", COMPETITORS) == "competitor_owned"
    assert classify_domain("rossum.ai", "acme.com", COMPETITORS) == "competitor_owned"


def test_classify_other():
    assert classify_domain("techcrunch.com", "acme.com", COMPETITORS) == "other"


def test_classify_domain_with_url_listicle_by_path():
    result = classify_domain_with_url(
        "https://example.com/best-ocr-tools-2024",
        "example.com",
        "acme.com",
        COMPETITORS,
    )
    assert result == "listicle"


def test_classify_domain_with_url_alternatives_path():
    result = classify_domain_with_url(
        "https://example.com/nanonets-alternatives",
        "example.com",
        "acme.com",
        COMPETITORS,
    )
    assert result == "listicle"


def test_estimate_credit_cost_basic():
    queries = [
        QueryConfig(text="best OCR tool", intent="tool discovery", vertical="general", priority="high", category="commercial"),
        QueryConfig(text="invoice extraction", intent="use case", vertical="finance", priority="medium", category="vertical"),
    ]
    settings = _FakeSettings(top_urls_for_analysis=30, perplexity_api_key="fake-key")
    result = estimate_credit_cost(queries, settings)
    assert result["queries"] == 2
    assert result["high_priority_queries"] == 1
    assert result["total_firecrawl_credits"] == 32  # 2 search + 30 scrape
    assert result["perplexity_usd_estimate"] == pytest.approx(0.001)


def test_estimate_credit_cost_no_perplexity():
    queries = [
        QueryConfig(text="best OCR", intent="tool discovery", vertical="general", priority="high", category="commercial"),
    ]
    settings = _FakeSettings(top_urls_for_analysis=10, perplexity_api_key=None)
    result = estimate_credit_cost(queries, settings)
    assert result["perplexity_usd_estimate"] == 0.0
