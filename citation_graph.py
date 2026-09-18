from __future__ import annotations
import math
import logging
from collections import defaultdict
from datetime import date
from typing import TYPE_CHECKING

from models import CitationRow, SerpResult
from utils import classify_domain_with_url

if TYPE_CHECKING:
    import duckdb

log = logging.getLogger(__name__)


def _decay_weight(position: int) -> float:
    """1 / log2(position + 1); position 1 = 1.0, position 10 ≈ 0.29."""
    if position <= 0:
        return 0.0
    return 1.0 / math.log2(position + 1)


def build_citation_graph(
    results: list[SerpResult],
    brand_domain: str,
    competitors: set[str],
    run_date: date,
) -> list[CitationRow]:
    scores: dict[str, float] = defaultdict(float)
    query_counts: dict[str, set[str]] = defaultdict(set)
    top_positions: dict[str, int] = {}
    domains: dict[str, str] = {}

    for r in results:
        if not r.url or r.url == "about:ai_overview":
            continue
        scores[r.url] += _decay_weight(r.position)
        query_counts[r.url].add(r.query)
        if r.url not in top_positions or r.position < top_positions[r.url]:
            top_positions[r.url] = r.position
        domains[r.url] = r.domain

    rows: list[CitationRow] = []
    for url, score in scores.items():
        domain = domains[url]
        rows.append(
            CitationRow(
                run_date=run_date,
                url=url,
                domain=domain,
                domain_type=classify_domain_with_url(url, domain, brand_domain, competitors),
                weighted_score=round(score, 4),
                queries_appearing_in=len(query_counts[url]),
                top_position=top_positions[url],
            )
        )

    rows.sort(key=lambda r: r.weighted_score, reverse=True)
    log.info("Built citation graph: %d unique URLs", len(rows))
    return rows


def get_top_non_brand_urls(
    graph: list[CitationRow],
    n: int = 30,
) -> list[CitationRow]:
    filtered = [r for r in graph if r.domain_type != "brand_owned"]
    return filtered[:n]


def run_citation_graph_phase(
    results: list[SerpResult],
    conn: "duckdb.DuckDBPyConnection",
    brand_domain: str,
    competitors: set[str],
    run_date: date,
    top_n: int = 30,
    dry_run: bool = False,
) -> tuple[list[CitationRow], list[CitationRow]]:
    from db import insert_citation_graph

    graph = build_citation_graph(results, brand_domain, competitors, run_date)
    top_urls = get_top_non_brand_urls(graph, n=top_n)

    if not dry_run:
        insert_citation_graph(conn, graph)
        log.info("Inserted %d citation graph rows", len(graph))

    return graph, top_urls
