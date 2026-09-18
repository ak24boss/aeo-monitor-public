from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from typing import Optional

import duckdb

from models import (
    AECitationRow,
    CitationRow,
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
"""


def get_connection(db_path: Path) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(str(db_path))
    conn.execute(SCHEMA_SQL)
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
