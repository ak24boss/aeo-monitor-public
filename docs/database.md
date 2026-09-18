# AEO Monitor — Database Reference

## Overview

All pipeline output is persisted to `aeo_monitor.db`, a single-file DuckDB database. The file is gitignored — each installation starts fresh. Rows use `INSERT OR REPLACE` (upsert semantics), so re-running the pipeline on the same day overwrites rather than duplicates.

**DuckDB is single-process only** — do not attempt concurrent writes. The Streamlit dashboard (`app.py`) connects read-only.

## Tables

### `serp_results`

SERP results from Phase 1 (Firecrawl search).

| Column | Type | Description |
|--------|------|-------------|
| `run_date` | DATE | Pipeline run date (PK component) |
| `query` | TEXT | The search query text (PK component) |
| `position` | INTEGER | Organic position (PK component) |
| `title` | TEXT | Page title |
| `url` | TEXT | Full URL |
| `domain` | TEXT | Extracted domain (no www.) |
| `snippet` | TEXT | Search result snippet |
| `ai_overview_box` | TEXT | AI overview text if present (only on first result per query) |
| `raw_response_path` | TEXT | Cache file path (for debugging) |

**PK**: `(run_date, query, position)`

### `citation_graph`

Decay-weighted URL aggregation from Phase 2.

| Column | Type | Description |
|--------|------|-------------|
| `run_date` | DATE | (PK component) |
| `url` | TEXT | Full URL (PK component) |
| `domain` | TEXT | Domain |
| `domain_type` | TEXT | One of 7 classification types |
| `weighted_score` | DOUBLE | Sum of `1/log2(pos+1)` across all queries |
| `queries_appearing_in` | INTEGER | Number of distinct queries this URL appeared in |
| `top_position` | INTEGER | Best (lowest) position across all queries |

**PK**: `(run_date, url)`

### `source_analysis`

Scrape results from Phase 3.

| Column | Type | Description |
|--------|------|-------------|
| `run_date` | DATE | (PK component) |
| `url` | TEXT | (PK component) |
| `lido_mentioned` | BOOLEAN | Whether "lido" appears in scraped text |
| `lido_context` | TEXT | ~100-char excerpt around the Lido mention |
| `competitors_mentioned` | TEXT | JSON array of competitor domains found |
| `page_type` | TEXT | `listicle`, `review`, `forum`, `blog`, `web` |
| `last_updated` | TEXT | Date extracted from content or metadata |
| `pain_language` | TEXT | Raw comment text from forum sources |
| `raw_response_path` | TEXT | Cache directory path |

**PK**: `(run_date, url)`

**Note**: `competitors_mentioned` is stored as a JSON string — use `json_extract()` in DuckDB to query it.

### `ae_citations`

Perplexity sonar citation results from Phase 4.

| Column | Type | Description |
|--------|------|-------------|
| `run_date` | DATE | (PK component) |
| `query` | TEXT | The high-priority query (PK component) |
| `cited_url` | TEXT | URL cited by Perplexity (PK component) |
| `cited_domain` | TEXT | Extracted domain |
| `position_in_response` | INTEGER | Order in Perplexity's citation list (1-indexed) |

**PK**: `(run_date, query, cited_url)`

### `trend_data`

Google Trends weekly interest from Phase 5.

| Column | Type | Description |
|--------|------|-------------|
| `run_date` | DATE | (PK component) |
| `keyword` | TEXT | The query keyword (PK component) |
| `week` | TEXT | ISO week string e.g. `"2026-01-05"` (PK component) |
| `interest` | INTEGER | Google Trends interest (0-100) |
| `rising_related` | TEXT | JSON array of rising related query strings |

**PK**: `(run_date, keyword, week)`

## Example SQL queries

```sql
-- Top pages by weighted score (primary deliverable input)
SELECT url, domain_type, weighted_score, queries_appearing_in
FROM citation_graph
ORDER BY weighted_score DESC
LIMIT 10;

-- Pages where Lido is mentioned
SELECT url, lido_context
FROM source_analysis
WHERE lido_mentioned = TRUE;

-- Gap pages: high score, competitors present, Lido absent
SELECT cg.url, cg.weighted_score, sa.competitors_mentioned
FROM citation_graph cg
JOIN source_analysis sa ON cg.url = sa.url AND cg.run_date = sa.run_date
WHERE sa.lido_mentioned = FALSE
  AND sa.competitors_mentioned != '[]'
ORDER BY cg.weighted_score DESC;

-- All queries and how many results they returned
SELECT query, COUNT(*) AS results
FROM serp_results
GROUP BY query
ORDER BY results DESC;
```

## Accessing the database

```bash
# Python REPL
venv/bin/python -c "import duckdb; conn = duckdb.connect('aeo_monitor.db'); conn.execute('SELECT COUNT(*) FROM serp_results').fetchall()"

# DuckDB CLI (if installed)
duckdb aeo_monitor.db
```
