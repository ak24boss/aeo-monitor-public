from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from models import QueryConfig

ROOT = Path(__file__).parent


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
    firecrawl_rate_limit_rps: float = 2.0


def load_settings(query_limit: Optional[int] = None) -> Settings:
    load_dotenv(ROOT / ".env")

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

    company = _load_company(ROOT / "company.yaml")
    queries = _parse_queries(ROOT / "config" / "queries.yaml")
    if query_limit is not None:
        queries = queries[:query_limit]

    cache_dir = ROOT / "cache"
    out_dir = ROOT / "out"
    cache_dir.mkdir(exist_ok=True)
    out_dir.mkdir(exist_ok=True)

    return Settings(
        firecrawl_api_key=api_key,
        perplexity_api_key=perplexity_key,
        db_path=ROOT / "aeo_monitor.db",
        cache_dir=cache_dir,
        out_dir=out_dir,
        queries=queries,
        company_name=company.get("company_name", "Your Company"),
        brand_domain=company.get("company_domain", "yourcompany.com"),
        contact_email=company.get("contact_email", "you@yourcompany.com"),
        competitors=set(company.get("competitors", [])),
    )


def _load_company(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            "company.yaml not found.\n"
            "Fix: copy company.yaml.example to company.yaml and fill in your details.\n"
            "  cp company.yaml.example company.yaml"
        )
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _parse_queries(yaml_path: Path) -> list[QueryConfig]:
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    queries: list[QueryConfig] = []
    for category, items in data.get("categories", {}).items():
        for item in items:
            queries.append(QueryConfig(category=category, **item))
    return queries
