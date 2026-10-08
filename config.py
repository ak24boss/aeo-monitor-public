from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from models import ProbeConfig, QueryConfig

ROOT = Path(__file__).parent
COMPANIES_DIR = ROOT / "companies"

_RESERVED_SLUGS = {"_template"}


@dataclass
class Settings:
    firecrawl_api_key: str
    perplexity_api_key: Optional[str]
    db_path: Path
    cache_dir: Path
    out_dir: Path
    queries: list[QueryConfig]
    company_name: str = "Your Company"
    brand_domain: str = "yourcompany.com"
    contact_email: str = "you@yourcompany.com"
    competitors: set[str] = field(default_factory=set)
    max_serp_results: int = 10
    top_urls_for_analysis: int = 30
    top_keywords_for_trends: int = 25
    firecrawl_rate_limit_rps: float = 0.14  # 10 req/min Firecrawl cap → stay at ~8/min
    probes: list[ProbeConfig] = field(default_factory=list)
    ai_engine_keys: dict[str, str] = field(default_factory=dict)


def load_settings(
    query_limit: Optional[int] = None,
    company_slug: Optional[str] = None,
) -> Settings:
    load_dotenv(ROOT / ".env")

    if company_slug in _RESERVED_SLUGS:
        raise ValueError(
            f"'{company_slug}' is a reserved slug and cannot be used as a company.\n"
            "Copy companies/_template/ to a new directory and use that slug instead."
        )

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise ValueError(
            "FIRECRAWL_API_KEY is required but not set.\n"
            "Fix: add FIRECRAWL_API_KEY=fc-your-key to the .env file.\n"
            "See .env.example for the format. Get a key at firecrawl.dev."
        )

    perplexity_key = os.getenv("PERPLEXITY_API_KEY") or None
    if perplexity_key == "":
        perplexity_key = None

    ai_engine_keys = _load_ai_engine_keys(perplexity_key)

    if company_slug:
        company_dir = COMPANIES_DIR / company_slug
        if not company_dir.is_dir():
            raise FileNotFoundError(
                f"companies/{company_slug}/ not found.\n"
                "Run: make new-company SLUG={company_slug}"
            )
        company = _load_company(company_dir / "profile.yaml")
        _validate_slug(company, company_slug)
        queries = _parse_queries(company_dir / "queries.yaml")
        probes = load_probes(company_dir / "probes.yaml")
        db_path = company_dir / "data.db"
        cache_dir = company_dir / "cache"
        out_dir = company_dir / "out"
    else:
        company = _load_company(ROOT / "company.yaml")
        queries = _parse_queries(ROOT / "config" / "queries.yaml")
        probes = []
        db_path = ROOT / "aeo_monitor.db"
        cache_dir = ROOT / "cache"
        out_dir = ROOT / "out"

    if query_limit is not None:
        queries = queries[:query_limit]

    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        firecrawl_api_key=api_key,
        perplexity_api_key=perplexity_key,
        db_path=db_path,
        cache_dir=cache_dir,
        out_dir=out_dir,
        queries=queries,
        company_name=company.get("company_name", "Your Company"),
        brand_domain=company.get("company_domain", "yourcompany.com"),
        contact_email=company.get("contact_email", "you@yourcompany.com"),
        competitors=set(company.get("competitors", [])),
        max_serp_results=company.get("max_serp_results", 10),
        top_urls_for_analysis=company.get("top_urls_for_analysis", 30),
        firecrawl_rate_limit_rps=company.get("firecrawl_rate_limit_rps", 2.0),
        probes=probes,
        ai_engine_keys=ai_engine_keys,
    )


def load_probes(path: Path) -> list[ProbeConfig]:
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return [ProbeConfig(**item) for item in data.get("probes", [])]


def _load_company(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found.\n"
            "For company-specific runs: make new-company SLUG=yourslug\n"
            "For legacy runs: cp company.yaml.example company.yaml"
        )
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _validate_slug(profile: dict, expected_slug: str) -> None:
    slug_in_file = profile.get("slug")
    if slug_in_file and slug_in_file != expected_slug:
        raise ValueError(
            f"Slug mismatch: directory is '{expected_slug}' but profile.yaml says slug='{slug_in_file}'.\n"
            f"Fix: set `slug: {expected_slug}` in companies/{expected_slug}/profile.yaml."
        )


def _parse_queries(yaml_path: Path) -> list[QueryConfig]:
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    queries: list[QueryConfig] = []
    for category, items in data.get("categories", {}).items():
        for item in items:
            queries.append(QueryConfig(category=category, **item))
    return queries


def _load_ai_engine_keys(perplexity_key: Optional[str]) -> dict[str, str]:
    # OPENROUTER_API_KEY is the single key that covers all three engines.
    # PERPLEXITY_API_KEY is the legacy name (same value — OpenRouter key).
    # Engine-specific env vars override the shared key if set.
    openrouter_key = os.getenv("OPENROUTER_API_KEY") or perplexity_key or None

    keys: dict[str, str] = {}
    for engine in ("perplexity", "claude", "openai"):
        env_var = f"{engine.upper()}_API_KEY"
        specific = os.getenv(env_var)
        resolved = specific or openrouter_key
        if resolved:
            keys[engine] = resolved
    return keys
