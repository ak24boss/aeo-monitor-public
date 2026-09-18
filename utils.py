from __future__ import annotations
import urllib.parse
from typing import TYPE_CHECKING

from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

if TYPE_CHECKING:
    from config import Settings
    from models import QueryConfig, DomainType

REVIEW_PLATFORMS = {
    "g2.com", "capterra.com", "trustradius.com", "getapp.com",
    "softwareadvice.com", "gartner.com", "trustpilot.com",
}

LISTICLE_SIGNALS = {"best", "top", "alternatives", "vs", "compare", "comparison", "review"}


def extract_domain(url: str) -> str:
    netloc = urllib.parse.urlparse(url).netloc
    return netloc.lstrip("www.")


def classify_domain(domain: str, brand_domain: str, competitors: set[str]) -> "DomainType":
    d = domain.lstrip("www.")
    if d == brand_domain or d.endswith("." + brand_domain):
        return "brand_owned"
    if d in REVIEW_PLATFORMS or any(d.endswith("." + r) for r in REVIEW_PLATFORMS):
        return "review_platform"
    if d == "reddit.com" or d.endswith(".reddit.com"):
        return "reddit_forum"
    if d in competitors or any(d.endswith("." + c) for c in competitors):
        return "competitor_owned"
    if any(sig in d for sig in LISTICLE_SIGNALS):
        return "listicle"
    return "other"


def classify_domain_with_url(url: str, domain: str, brand_domain: str, competitors: set[str]) -> "DomainType":
    base = classify_domain(domain, brand_domain, competitors)
    if base != "other":
        return base
    path = urllib.parse.urlparse(url).path.lower()
    if any(sig in path for sig in LISTICLE_SIGNALS):
        return "listicle"
    return "other"


def firecrawl_retry(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30) + wait_random(0, 1),
        reraise=True,
    )(func)


def estimate_credit_cost(queries: list["QueryConfig"], settings: "Settings") -> dict:
    n = len(queries)
    high_priority = sum(1 for q in queries if q.priority == "high")
    search_credits = n
    scrape_credits = settings.top_urls_for_analysis
    perplexity_usd = high_priority * 0.001 if settings.perplexity_api_key else 0.0
    return {
        "queries": n,
        "high_priority_queries": high_priority,
        "firecrawl_search_credits": search_credits,
        "firecrawl_scrape_credits": scrape_credits,
        "total_firecrawl_credits": search_credits + scrape_credits,
        "perplexity_usd_estimate": perplexity_usd,
    }
