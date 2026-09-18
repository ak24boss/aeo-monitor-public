from __future__ import annotations
import pytest
from datetime import date
from source_analysis import _find_brand, _find_competitors, _extract_page_type, _parse_scraped
from models import CitationRow

TODAY = date(2026, 8, 31)
BRAND_DOMAIN = "acme.com"
COMPANY_NAME = "Acme"
COMPETITORS = {"nanonets.com", "rossum.ai", "parseur.com"}


def _citation(url: str, domain_type: str = "other") -> CitationRow:
    return CitationRow(
        run_date=TODAY,
        url=url,
        domain=url.split("/")[2].lstrip("www."),
        domain_type=domain_type,
        weighted_score=1.0,
        queries_appearing_in=1,
        top_position=1,
    )


def test_find_brand_found():
    found, ctx = _find_brand("We tested Acme and it was excellent for invoices.", COMPANY_NAME)
    assert found is True
    assert ctx is not None
    assert "Acme" in ctx


def test_find_brand_case_insensitive():
    found, ctx = _find_brand("acme.com is a document extraction tool.", COMPANY_NAME)
    assert found is True


def test_find_brand_not_found():
    found, ctx = _find_brand("We use nanonets and rossum for extraction.", COMPANY_NAME)
    assert found is False
    assert ctx is None


def test_find_competitors_nanonets():
    found = _find_competitors("We compared nanonets for invoice processing.", COMPETITORS)
    assert "nanonets.com" in found


def test_find_competitors_multiple():
    found = _find_competitors("Testing nanonets, rossum, and parseur.", COMPETITORS)
    assert "nanonets.com" in found
    assert "rossum.ai" in found
    assert "parseur.com" in found


def test_find_competitors_no_match():
    found = _find_competitors("No competitors mentioned here.", COMPETITORS)
    assert found == []


def test_extract_page_type_listicle_alternatives():
    pt = _extract_page_type("https://example.com/nanonets-alternatives", "")
    assert pt == "listicle"


def test_extract_page_type_listicle_best():
    pt = _extract_page_type("https://example.com/best-ocr-tools", "")
    assert pt == "listicle"


def test_extract_page_type_review():
    pt = _extract_page_type("https://example.com/review/acme-software", "")
    assert pt == "review"


def test_extract_page_type_blog():
    pt = _extract_page_type("https://example.com/blog/document-extraction-guide", "")
    assert pt == "blog"


def test_extract_page_type_fallback():
    pt = _extract_page_type("https://example.com/about", "")
    assert pt == "web"


def test_parse_scraped_brand_found():
    citation = _citation("https://g2.com/compare/acme-vs-nanonets")
    raw = {
        "url": citation.url,
        "markdown": "We tested Acme extensively. nanonets is also popular.",
        "title": "Comparison page",
        "modified_time": None,
    }
    row = _parse_scraped(citation, raw, COMPANY_NAME, COMPETITORS, "/tmp/cache")
    assert row.brand_mentioned is True
    assert "Acme" in (row.brand_context or "")
    assert "nanonets.com" in row.competitors_mentioned


def test_parse_scraped_brand_absent():
    citation = _citation("https://example.com/ocr-tools")
    raw = {
        "url": citation.url,
        "markdown": "nanonets and rossum are both excellent choices.",
        "title": "OCR Tools",
        "modified_time": None,
    }
    row = _parse_scraped(citation, raw, COMPANY_NAME, COMPETITORS, "/tmp/cache")
    assert row.brand_mentioned is False
    assert row.brand_context is None


def test_parse_scraped_empty_markdown():
    citation = _citation("https://example.com/page")
    raw = {"url": citation.url, "markdown": "", "title": None, "modified_time": None}
    row = _parse_scraped(citation, raw, COMPANY_NAME, COMPETITORS, "/tmp/cache")
    assert row.brand_mentioned is False
    assert row.competitors_mentioned == []
