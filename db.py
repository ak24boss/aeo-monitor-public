from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from typing import Optional

import duckdb

from models import (
    AECitationRow,
    AEProbeRow,
    CitationRow,
    CrossReferenceRow,
    SerpResult,
    SourceAnalysisRow,
    TrendRow,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS serp_results (
    run_date DATE NOT NULL,
    query TEXT NOT NULL,
    position INTEGER NOT NULL,
    title TEXT,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    snippet TEXT,
    ai_overview_box TEXT,
    raw_response_path TEXT,
    PRIMARY KEY (run_date, query, position)
);

CREATE TABLE IF NOT EXISTS citation_graph (
    run_date DATE NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    domain_type TEXT NOT NULL,
    weighted_score DOUBLE NOT NULL,
    queries_appearing_in INTEGER NOT NULL,
    top_position INTEGER NOT NULL,
    PRIMARY KEY (run_date, url)
);

CREATE TABLE IF NOT EXISTS source_analysis (
    run_date DATE NOT NULL,
    url TEXT NOT NULL,
    brand_mentioned BOOLEAN NOT NULL,
    brand_context TEXT,
    competitors_mentioned TEXT,
    page_type TEXT,
    last_updated TEXT,
    pain_language TEXT,
    raw_response_path TEXT,
    PRIMARY KEY (run_date, url)
);

CREATE TABLE IF NOT EXISTS ae_citations (
    run_date DATE NOT NULL,
    query TEXT NOT NULL,
    cited_url TEXT NOT NULL,
    cited_domain TEXT NOT NULL,
    position_in_response INTEGER NOT NULL,
    PRIMARY KEY (run_date, query, cited_url)
);

CREATE TABLE IF NOT EXISTS trend_data (
    run_date DATE NOT NULL,
    keyword TEXT NOT NULL,
    week TEXT NOT NULL,
    interest INTEGER NOT NULL,
    rising_related TEXT,
    PRIMARY KEY (run_date, keyword, week)
);

CREATE TABLE IF NOT EXISTS ae_probe_results (
    run_date DATE NOT NULL,
    engine TEXT NOT NULL,
    probe_id TEXT NOT NULL,
    probe_text TEXT NOT NULL,
    brand_mentioned BOOLEAN NOT NULL,
    brand_context TEXT,
    competitors_mentioned TEXT,
    cited_urls TEXT,
    cited_domains TEXT,
    sponsored_domains TEXT,
    raw_response TEXT,
    PRIMARY KEY (run_date, engine, probe_id)
);

CREATE TABLE IF NOT EXISTS cross_reference (
    run_date DATE NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    serp_weighted_score DOUBLE NOT NULL,
    serp_queries_appearing_in INTEGER NOT NULL,
    engines_citing_url TEXT,
    engine_citation_count INTEGER NOT NULL DEFAULT 0,
    brand_mentioned_on_page BOOLEAN,
    action_priority TEXT NOT NULL DEFAULT 'medium',
    PRIMARY KEY (run_date, url)
);
"""


def get_connection(db_path: Path) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(str(db_path))
    conn.execute(SCHEMA_SQL)
    # Migrate ae_probe_results to add perturbation metadata columns
    for col, default in [
        ("seed_topic", "'general'"),
        ("perturbation_class", "'seed'"),
        ("perturbation_type", "'seed'"),
        ("sponsored_domains", "NULL"),
    ]:
        try:
            conn.execute(
                f"ALTER TABLE ae_probe_results ADD COLUMN IF NOT EXISTS {col} TEXT DEFAULT {default}"
            )
        except Exception:
            pass
    return conn


def insert_serp_results(conn: duckdb.DuckDBPyConnection, rows: list[SerpResult]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO serp_results
            (run_date, query, position, title, url, domain, snippet, ai_overview_box, raw_response_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                r.run_date, r.query, r.position, r.title, r.url,
                r.domain, r.snippet, r.ai_overview_box, r.raw_response_path,
            )
            for r in rows
        ],
    )


def insert_citation_graph(conn: duckdb.DuckDBPyConnection, rows: list[CitationRow]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO citation_graph
            (run_date, url, domain, domain_type, weighted_score, queries_appearing_in, top_position)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (r.run_date, r.url, r.domain, r.domain_type,
             r.weighted_score, r.queries_appearing_in, r.top_position)
            for r in rows
        ],
    )


def insert_source_analysis(conn: duckdb.DuckDBPyConnection, rows: list[SourceAnalysisRow]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO source_analysis
            (run_date, url, brand_mentioned, brand_context, competitors_mentioned,
             page_type, last_updated, pain_language, raw_response_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                r.run_date, r.url, r.brand_mentioned, r.brand_context,
                json.dumps(r.competitors_mentioned), r.page_type,
                r.last_updated, r.pain_language, r.raw_response_path,
            )
            for r in rows
        ],
    )


def insert_ae_citations(conn: duckdb.DuckDBPyConnection, rows: list[AECitationRow]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO ae_citations
            (run_date, query, cited_url, cited_domain, position_in_response)
        VALUES (?, ?, ?, ?, ?)
        """,
        [(r.run_date, r.query, r.cited_url, r.cited_domain, r.position_in_response) for r in rows],
    )


def insert_trend_data(conn: duckdb.DuckDBPyConnection, rows: list[TrendRow]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO trend_data
            (run_date, keyword, week, interest, rising_related)
        VALUES (?, ?, ?, ?, ?)
        """,
        [(r.run_date, r.keyword, r.week, r.interest, json.dumps(r.rising_related)) for r in rows],
    )


def get_previous_run_date(conn: duckdb.DuckDBPyConnection, before_date: date) -> Optional[date]:
    row = conn.execute(
        "SELECT MAX(run_date) FROM citation_graph WHERE run_date < ?", [before_date]
    ).fetchone()
    return row[0] if row and row[0] else None


def get_citation_graph_for_date(
    conn: duckdb.DuckDBPyConnection, run_date: date
) -> list[CitationRow]:
    rows = conn.execute(
        "SELECT * FROM citation_graph WHERE run_date = ? ORDER BY weighted_score DESC",
        [run_date],
    ).fetchall()
    cols = ["run_date", "url", "domain", "domain_type", "weighted_score",
            "queries_appearing_in", "top_position"]
    return [CitationRow(**dict(zip(cols, r))) for r in rows]


def insert_ae_probe_results(
    conn: duckdb.DuckDBPyConnection, rows: list[AEProbeRow]
) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO ae_probe_results
            (run_date, engine, probe_id, probe_text, brand_mentioned, brand_context,
             competitors_mentioned, cited_urls, cited_domains, sponsored_domains,
             raw_response, seed_topic, perturbation_class, perturbation_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                r.run_date, r.engine, r.probe_id, r.probe_text,
                r.brand_mentioned, r.brand_context,
                json.dumps(r.competitors_mentioned),
                json.dumps(r.cited_urls),
                json.dumps(r.cited_domains),
                json.dumps(r.sponsored_domains),
                r.raw_response,
                r.seed_topic, r.perturbation_class, r.perturbation_type,
            )
            for r in rows
        ],
    )


def insert_cross_reference(
    conn: duckdb.DuckDBPyConnection, rows: list[CrossReferenceRow]
) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO cross_reference
            (run_date, url, domain, serp_weighted_score, serp_queries_appearing_in,
             engines_citing_url, engine_citation_count, brand_mentioned_on_page, action_priority)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                r.run_date, r.url, r.domain,
                r.serp_weighted_score, r.serp_queries_appearing_in,
                json.dumps(r.engines_citing_url),
                r.engine_citation_count,
                r.brand_mentioned_on_page,
                r.action_priority,
            )
            for r in rows
        ],
    )


def get_ai_visibility_summary(
    conn: duckdb.DuckDBPyConnection, run_date: date
):
    """Return ae_probe_results rows for run_date as a list of dicts."""
    rows = conn.execute(
        """
        SELECT engine, probe_id, probe_text, brand_mentioned,
               brand_context, competitors_mentioned, cited_urls
        FROM ae_probe_results
        WHERE run_date = ?
        ORDER BY engine, probe_id
        """,
        [run_date],
    ).fetchall()
    cols = [
        "engine", "probe_id", "probe_text", "brand_mentioned",
        "brand_context", "competitors_mentioned", "cited_urls",
    ]
    result = []
    for r in rows:
        d = dict(zip(cols, r))
        d["competitors_mentioned"] = json.loads(d["competitors_mentioned"] or "[]")
        d["cited_urls"] = json.loads(d["cited_urls"] or "[]")
        result.append(d)
    return result
