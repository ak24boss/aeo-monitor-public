from __future__ import annotations
import logging
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import httpx

from cache import CacheStats, load_cache, save_cache
from models import AECitationRow, QueryConfig
from utils import extract_domain

if TYPE_CHECKING:
    import duckdb
    from config import Settings

log = logging.getLogger(__name__)

PROVIDER = "perplexity"
PERPLEXITY_URL = "https://openrouter.ai/api/v1/chat/completions"
PERPLEXITY_MODEL = "perplexity/sonar"


def query_perplexity(
    query: QueryConfig,
    api_key: str,
    cache_dir: Path,
    stats: CacheStats,
    run_date: date,
    brand_domain: str = "yourcompany.com",
    dry_run: bool = False,
) -> list[AECitationRow]:
    cached = load_cache(PROVIDER, query.text, cache_dir)
    if cached is not None:
        stats.hit()
        raw = cached
    elif dry_run:
        stats.miss()
        return []
    else:
        stats.miss()
        try:
            log.info("Querying Perplexity: %s", query.text)
            resp = httpx.post(
                PERPLEXITY_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": f"https://{brand_domain}",
                    "X-Title": "AEO Monitor",
                },
                json={
                    "model": PERPLEXITY_MODEL,
                    "messages": [{"role": "user", "content": query.text}],
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            raw = resp.json()
            save_cache(PROVIDER, query.text, raw, cache_dir)
        except Exception as e:
            log.warning(
                "Perplexity query failed for %r: %s  "
                "[check PERPLEXITY_API_KEY, verify openrouter.ai balance, or set PERPLEXITY_API_KEY= to skip]",
                query.text, e,
            )
            return []

    # Native Perplexity returns top-level citations[]; OpenRouter returns
    # annotations on the message with type="url_citation"
    citations = raw.get("citations", [])
    if not citations:
        message = (raw.get("choices") or [{}])[0].get("message", {})
        citations = [
            a["url_citation"]["url"]
            for a in message.get("annotations", [])
            if a.get("type") == "url_citation" and a.get("url_citation", {}).get("url")
        ]
    rows: list[AECitationRow] = []
    for i, url in enumerate(citations):
        if not url:
            continue
        rows.append(
            AECitationRow(
                run_date=run_date,
                query=query.text,
                cited_url=url,
                cited_domain=extract_domain(url),
                position_in_response=i + 1,
            )
        )
    return rows


def run_ae_phase(
    queries: list[QueryConfig],
    settings: "Settings",
    conn: "duckdb.DuckDBPyConnection",
    stats: CacheStats,
    run_date: date,
    dry_run: bool = False,
) -> list[AECitationRow]:
    from db import insert_ae_citations

    if not settings.perplexity_api_key:
        log.warning("PERPLEXITY_API_KEY not set — skipping answer-engine phase")
        return []

    high_priority = [q for q in queries if q.priority == "high"]
    log.info("AE phase: %d high-priority queries", len(high_priority))

    all_rows: list[AECitationRow] = []
    for i, query in enumerate(high_priority):
        if i > 0:
            time.sleep(1.0)
        rows = query_perplexity(
            query, settings.perplexity_api_key, settings.cache_dir, stats, run_date,
            brand_domain=settings.brand_domain, dry_run=dry_run,
        )
        all_rows.extend(rows)
        log.info("AE query %d/%d: %d citations", i + 1, len(high_priority), len(rows))

    if not dry_run:
        insert_ae_citations(conn, all_rows)
        log.info("Inserted %d AE citation rows", len(all_rows))

    return all_rows
