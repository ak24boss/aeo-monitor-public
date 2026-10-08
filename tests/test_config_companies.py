"""Tests for the company template system (config.py company_slug routing)."""
from __future__ import annotations
import os
import pytest
from pathlib import Path


@pytest.fixture()
def company_dir(tmp_path, monkeypatch):
    """Create a minimal companies/testco/ structure under tmp_path."""
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-fake")
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    companies = tmp_path / "companies"
    slug_dir = companies / "testco"
    slug_dir.mkdir(parents=True)

    (slug_dir / "profile.yaml").write_text(
        "slug: testco\n"
        "company_name: Test Co\n"
        "company_domain: testco.com\n"
        "contact_email: hi@testco.com\n"
        "competitors:\n"
        "  - rival.com\n"
    )
    (slug_dir / "queries.yaml").write_text(
        "categories:\n"
        "  commercial:\n"
        "    - text: 'best test software'\n"
        "      intent: 'tool discovery'\n"
        "      vertical: 'general'\n"
        "      priority: high\n"
    )
    # probes.yaml intentionally absent — tests missing-file handling

    # Patch COMPANIES_DIR so config.py finds our tmp directory
    import config as cfg
    monkeypatch.setattr(cfg, "COMPANIES_DIR", companies)
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    # Provide a dummy company.yaml at ROOT so legacy path doesn't blow up
    (tmp_path / "company.yaml").write_text(
        "company_name: Legacy Co\n"
        "company_domain: legacy.com\n"
        "contact_email: x@legacy.com\n"
        "competitors: []\n"
    )
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "queries.yaml").write_text(
        "categories:\n"
        "  commercial:\n"
        "    - text: 'legacy query'\n"
        "      intent: 'tool discovery'\n"
        "      vertical: 'general'\n"
        "      priority: high\n"
    )
    return slug_dir


def test_load_settings_company_slug(company_dir, monkeypatch):
    """--company testco loads from companies/testco/, not root."""
    from config import load_settings

    settings = load_settings(company_slug="testco")

    assert settings.company_name == "Test Co"
    assert settings.brand_domain == "testco.com"
    assert "rival.com" in settings.competitors
    assert len(settings.queries) == 1
    assert settings.queries[0].text == "best test software"
    assert settings.db_path == company_dir / "data.db"
    assert settings.out_dir == company_dir / "out"


def test_load_probes_empty_if_missing(company_dir, monkeypatch):
    """Missing probes.yaml returns empty list — phase skips cleanly."""
    from config import load_settings

    settings = load_settings(company_slug="testco")
    assert settings.probes == []


def test_profile_slug_validation(company_dir, monkeypatch):
    """Slug in profile.yaml must match the directory name."""
    (company_dir / "profile.yaml").write_text(
        "slug: WRONG\n"
        "company_name: Test Co\n"
        "company_domain: testco.com\n"
        "contact_email: hi@testco.com\n"
        "competitors: []\n"
    )
    from config import load_settings

    with pytest.raises(ValueError, match="Slug mismatch"):
        load_settings(company_slug="testco")


def test_template_company_blocked(monkeypatch):
    """--company _template is always rejected, even if the directory exists."""
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-fake")
    from config import load_settings

    with pytest.raises(ValueError, match="reserved slug"):
        load_settings(company_slug="_template")
