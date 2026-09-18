from __future__ import annotations
import json
import logging
import re
import time
import urllib.parse
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import httpx

from cache import CacheStats, load_cache, save_cache
from firecrawl_client import AEOFirecrawlClient
from models import CitationRow, SourceAnalysisRow

if TYPE_CHECKING:
    import duckdb
    from config import Settings

log = logging.getLogger(__name__)

PROVIDER_SCRAPE = "firecrawl_scrape"
PROVIDER_REDDIT = "reddit_json"


def analyze_url(
    citation: CitationRow,
    client: AEOFirecrawlClient,
    cache_dir: Path,
    stats: CacheStats,
    brand_domain: str = "yourcompany.com",
    company_name: str = "Your Company",
    competitors: set[str] = frozenset(),
    contact_email: str = "you@yourcompany.com",
    dry_run: bool = False,
) -> SourceAnalysisRow:
    is_reddit = citation.domain_type == "reddit_forum"
    provider = PROVIDER_REDDIT if is_reddit else PROVIDER_SCRAPE
    reddit_ua = f"aeo-monitor/1.0 (research tool; contact {contact_email})"

    cached = load_cache(provider, citation.url, cache_dir)
    if cached is not None:
        stats.hit()
        raw = cached
    elif dry_run:
        stats.miss()
        return _empty_row(citation)
    else:
        stats.miss()
        if is_reddit:
            raw = _fetch_reddit_json(citation.url, reddit_ua)
            if raw is None:
                log.info("Reddit JSON 403, falling back to scrape: %s", citation.url)
                provider = PROVIDER_SCRAPE
                is_reddit = False
                try:
                    raw = client.scrape(citation.url)
                except Exception as e:
                    log.warning("Scrape fallback failed for %s: %s", citation.url, e)
                    return _empty_row(citation)
        else:
            try:
                log.info("Scraping: %s", citation.url)
                raw = client.scrape(citation.url)
            except Exception as e:
                log.warning("Scrape failed for %s: %s", citation.url, e)
                return _empty_row(citation)
        save_cache(provider, citation.url, raw, cache_dir)

    if is_reddit:
        return _parse_reddit(citation, raw, company_name, competitors, str(cache_dir))
    else:
        return _parse_scraped(citation, raw, company_name, competitors, str(cache_dir))


def _empty_row(citation: CitationRow) -> SourceAnalysisRow:
    return SourceAnalysisRow(
        run_date=citation.run_date,
        url=citation.url,
        brand_mentioned=False,
    )


def _fetch_reddit_json(url: str, user_agent: str, timeout: float = 15.0) -> Optional[dict]:
    clean = url.split("?")[0].rstrip("/")
    if not clean.endswith(".json"):
        clean += ".json"
    try:
        resp = httpx.get(clean, headers={"User-Agent": user_agent}, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return {"_reddit_json": resp.json(), "_url": url}
    except Exception as e:
        log.warning("Reddit JSON fetch failed for %s: %s", url, e)
        return None


def _parse_reddit(
    citation: CitationRow, raw: dict, company_name: str, competitors: set[str], cache_dir: str
) -> SourceAnalysisRow:
    data = raw.get("_reddit_json", [])
    comments: list[str] = []

    try:
        if isinstance(data, list) and len(data) > 1:
            comment_children = data[1]["data"]["children"]
            for child in comment_children[:5]:
                body = child.get("data", {}).get("body", "")
                if body and body != "[deleted]":
                    comments.append(body.strip())
    except Exception as e:
        log.warning("Reddit parse error for %s: %s", citation.url, e)

    full_text = " ".join(comments)
    brand_found, brand_ctx = _find_brand(full_text, company_name)
    comps = _find_competitors(full_text, competitors)
    pain = "\n---\n".join(comments[:3]) if comments else None

    return SourceAnalysisRow(
        run_date=citation.run_date,
        url=citation.url,
        brand_mentioned=brand_found,
        brand_context=brand_ctx,
        competitors_mentioned=comps,
        page_type="forum",
        last_updated=None,
        pain_language=pain,
        raw_response_path=cache_dir,
    )


def _parse_scraped(
    citation: CitationRow, raw: dict, company_name: str, competitors: set[str], cache_dir: str
) -> SourceAnalysisRow:
    markdown = raw.get("markdown", "") or ""
    brand_found, brand_ctx = _find_brand(markdown, company_name)
    comps = _find_competitors(markdown, competitors)
    page_type = _extract_page_type(citation.url, markdown)
    last_updated = _extract_last_updated(raw)

    return SourceAnalysisRow(
        run_date=citation.run_date,
        url=citation.url,
        brand_mentioned=brand_found,
        brand_context=brand_ctx,
        competitors_mentioned=comps,
        page_type=page_type,
        last_updated=last_updated,
        pain_language=None,
        raw_response_path=cache_dir,
    )


def _find_brand(text: str, company_name: str) -> tuple[bool, Optional[str]]:
    # Match the bare brand name (first word of company_name) case-insensitively
    brand_word = company_name.split()[0] if company_name else "brand"
    pattern = re.compile(re.escape(brand_word), re.IGNORECASE)
    m = pattern.search(text)
    if not m:
        return False, None
    start = max(0, m.start() - 50)
    end = min(len(text), m.end() + 50)
    return True, text[start:end].strip()


def _find_competitors(text: str, competitors: set[str]) -> list[str]:
    found: list[str] = []
    text_lower = text.lower()
    for domain in competitors:
        name = domain.split(".")[0]
        if name in text_lower and domain not in found:
            found.append(domain)
    return found


def _extract_page_type(url: str, markdown: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    domain = urllib.parse.urlparse(url).netloc.lower()
    if "reddit.com" in domain:
        return "forum"
    if any(s in path for s in ["alternative", "vs", "compare", "best-", "top-"]):
        return "listicle"
    if "review" in path or "review" in domain:
        return "review"
    if "blog" in path:
        return "blog"
    return "web"


def _extract_last_updated(raw: dict) -> Optional[str]:
    modified = raw.get("modified_time")
    if modified:
        return str(modified)
    markdown = raw.get("markdown", "") or ""
    m = re.search(r"(?:last updated|published)[:\s]+([A-Za-z]+ \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2})", markdown, re.IGNORECASE)
    return m.group(1) if m else None


def run_source_analysis_phase(
    top_urls: list[CitationRow],
    client: AEOFirecrawlClient,
    conn: "duckdb.DuckDBPyConnection",
    settings: "Settings",
    stats: CacheStats,
    run_date: date,
    dry_run: bool = False,
) -> list[SourceAnalysisRow]:
    from db import insert_source_analysis

    rows: list[SourceAnalysisRow] = []
    sleep_interval = 1.0 / settings.firecrawl_rate_limit_rps

    for i, citation in enumerate(top_urls):
        if i > 0:
            time.sleep(sleep_interval)
        row = analyze_url(
            citation, client, settings.cache_dir, stats,
            brand_domain=settings.brand_domain,
            company_name=settings.company_name,
            competitors=settings.competitors,
            contact_email=settings.contact_email,
            dry_run=dry_run,
        )
        rows.append(row)
        log.info(
            "Analyzed %d/%d: %s brand=%s",
            i + 1, len(top_urls), citation.url[:60], row.brand_mentioned,
        )

    if not dry_run:
        insert_source_analysis(conn, rows)
        log.info("Inserted %d source analysis rows", len(rows))

    return rows
