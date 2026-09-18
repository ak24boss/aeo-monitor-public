from __future__ import annotations
import logging
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from cache import CacheStats, load_cache, save_cache
from firecrawl_client import AEOFirecrawlClient
from models import QueryConfig, SerpResult
from utils import extract_domain

if TYPE_CHECKING:
    import duckdb
    from config import Settings

log = logging.getLogger(__name__)

PROVIDER = "firecrawl_search"


def harvest_serp(
    query: QueryConfig,
    client: AEOFirecrawlClient,
    cache_dir: Path,
    stats: CacheStats,
    run_date: date,
    limit: int = 10,
    dry_run: bool = False,
) -> list[SerpResult]:
    cached = load_cache(PROVIDER, query.text, cache_dir)
    if cached is not None:
        stats.hit()
        log.debug("Cache hit for query: %s", query.text)
        raw = cached
    elif dry_run:
        stats.miss()
        return []
    else:
        stats.miss()
        log.info("Fetching SERP: %s", query.text)
        raw = client.search(query.text, limit=limit)
        path = save_cache(PROVIDER, query.text, raw, cache_dir)
        log.debug("Cached response to %s", path)

    results: list[SerpResult] = []
    ai_overview_text: str | None = None

    web_results = raw.get("web", [])
    for idx, item in enumerate(web_results):
        category = item.get("category")
        url = item.get("url", "")
        if not url:
            continue

        if category == "ai_overview":
            # Capture AI overview verbatim; don't add as a ranked result
            ai_overview_text = item.get("markdown") or item.get("description") or None
            continue

        position = item.get("position") or (idx + 1)
        results.append(
            SerpResult(
                run_date=run_date,
                query=query.text,
                position=position,
                title=item.get("title"),
                url=url,
                domain=extract_domain(url),
                snippet=item.get("description"),
                ai_overview_box=None,
            )
        )

    # Attach AI overview to first result (if any) as metadata, or store standalone
    if ai_overview_text and results:
        results[0] = results[0].model_copy(update={"ai_overview_box": ai_overview_text})
    elif ai_overview_text and not results:
        # Rare: only an AI overview returned, no web results
        results.append(
            SerpResult(
                run_date=run_date,
                query=query.text,
                position=0,
                url="about:ai_overview",
                domain="",
                ai_overview_box=ai_overview_text,
            )
        )

    return results


def run_harvest_phase(
    queries: list[QueryConfig],
    client: AEOFirecrawlClient,
    conn: "duckdb.DuckDBPyConnection",
    settings: "Settings",
    stats: CacheStats,
    run_date: date,
    dry_run: bool = False,
) -> list[SerpResult]:
    from db import insert_serp_results

    all_results: list[SerpResult] = []
    sleep_interval = 1.0 / settings.firecrawl_rate_limit_rps

    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(sleep_interval)
        rows = harvest_serp(
            query, client, settings.cache_dir, stats, run_date,
            limit=settings.max_serp_results, dry_run=dry_run,
        )
        all_results.extend(rows)
        if not rows and not dry_run:
            log.warning(
                "Query %d/%d returned 0 results: %r  "
                "[check FIRECRAWL_API_KEY credits or try --dry-run]",
                i + 1, len(queries), query.text,
            )
        log.info("Query %d/%d: %d results", i + 1, len(queries), len(rows))

    if not dry_run:
        insert_serp_results(conn, all_results)
        log.info("Inserted %d SERP rows", len(all_results))

    return all_results
