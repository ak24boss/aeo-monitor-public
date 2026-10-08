"""Phase 4B — Cross-reference SERP citation graph × AI engine citations.

Pure SQL join — no API calls, zero cost.
Joins citation_graph + source_analysis + unnested cited_urls from ae_probe_results
to identify "high-SERP + AI-cited + brand-absent" pages and assign action_priority.

Priority matrix:
  serp_weighted_score >= 1.5 AND AI-cited → critical
  serp_weighted_score >= 0.5 AND AI-cited → high
  serp_weighted_score >= 1.5 (not AI-cited) → high
  anything else (brand absent) → medium
"""
from __future__ import annotations
import json
import logging
from datetime import date

import duckdb

from db import insert_cross_reference
from models import CrossReferenceRow

log = logging.getLogger(__name__)


def run_cross_reference_phase(
    conn: duckdb.DuckDBPyConnection,
    run_date: date,
    brand_domain: str,
    company_name: str,
    dry_run: bool = False,
) -> list[CrossReferenceRow]:
    has_probes = conn.execute(
        "SELECT COUNT(*) FROM ae_probe_results WHERE run_date = ?", [run_date]
    ).fetchone()[0]

    if not has_probes:
        log.info("Phase 4B: skipped (no ae_probe_results for %s)", run_date)
        return []

    log.info("Phase 4B: building cross-reference for %s", run_date)

    # Load probe results and unnest cited_urls in Python to avoid DuckDB
    # JSON unnesting syntax variance across versions.
    raw_probes = conn.execute(
        "SELECT engine, cited_urls FROM ae_probe_results WHERE run_date = ?",
        [run_date],
    ).fetchall()

    # Build: url → (set of engines, count)
    url_engines: dict[str, set[str]] = {}
    url_counts: dict[str, int] = {}
    for engine, cited_urls_json in raw_probes:
        urls = json.loads(cited_urls_json or "[]")
        for url in urls:
            url = url.strip()
            if not url:
                continue
            url_engines.setdefault(url, set()).add(engine)
            url_counts[url] = url_counts.get(url, 0) + 1

    ai_citations: dict[str, tuple[list[str], int]] = {
        url: (sorted(engines), url_counts[url])
        for url, engines in url_engines.items()
    }

    # Pull citation graph (excluding brand-owned domains)
    brand_slug = brand_domain.split(".")[0].lower() if brand_domain else ""
    cg_rows = conn.execute(
        """
        SELECT
            cg.url, cg.domain, cg.weighted_score, cg.queries_appearing_in,
            sa.brand_mentioned
        FROM citation_graph cg
        LEFT JOIN source_analysis sa ON cg.url = sa.url AND sa.run_date = ?
        WHERE cg.run_date = ?
          AND cg.domain_type != 'brand_owned'
        ORDER BY cg.weighted_score DESC
        """,
        [run_date, run_date],
    ).fetchall()

    rows: list[CrossReferenceRow] = []
    for url, domain, score, queries_in, brand_on_page in cg_rows:
        if brand_on_page:
            continue  # brand already present on this page

        engine_data = ai_citations.get(url, ([], 0))
        engines_citing, cite_count = engine_data
        action_priority = _priority(score, cite_count)

        rows.append(CrossReferenceRow(
            run_date=run_date,
            url=url,
            domain=domain,
            serp_weighted_score=score,
            serp_queries_appearing_in=queries_in,
            engines_citing_url=engines_citing,
            engine_citation_count=cite_count,
            brand_mentioned_on_page=bool(brand_on_page) if brand_on_page is not None else None,
            action_priority=action_priority,
        ))

    if not dry_run:
        insert_cross_reference(conn, rows)
    log.info("Phase 4B: %d cross-reference rows (dry_run=%s)", len(rows), dry_run)
    return rows


def _priority(
    serp_score: float,
    ai_citation_count: int,
) -> str:
    ai_cited = ai_citation_count > 0
    if serp_score >= 1.5 and ai_cited:
        return "critical"
    if serp_score >= 0.5 and ai_cited:
        return "high"
    if serp_score >= 1.5:
        return "high"
    return "medium"
