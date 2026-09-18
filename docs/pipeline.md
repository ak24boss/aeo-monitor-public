# AEO Monitor — Pipeline Architecture

## Overview

Seven sequential phases, orchestrated by `cli.py:cmd_run()`. All phase outputs persist to `aeo_monitor.db` (DuckDB). The pipeline can be interrupted cleanly — each phase writes before passing to the next.

## Phases

| # | Module | Input | Output | DuckDB table | Cache provider |
|---|--------|-------|--------|--------------|----------------|
| 1 | `harvest.py` | `queries.yaml` | `list[SerpResult]` | `serp_results` | `firecrawl_search` |
| 2 | `citation_graph.py` | SERP results | `list[CitationRow]` | `citation_graph` | — (pure compute) |
| 3 | `source_analysis.py` | Top 30 non-Lido URLs | `list[SourceAnalysisRow]` | `source_analysis` | `firecrawl_scrape`, `reddit_json` |
| 4 | `ae_citations.py` | High-priority queries | `list[AECitationRow]` | `ae_citations` | `perplexity` |
| 5 | `trends.py` | Top 25 queries by weight | `list[TrendRow]` | `trend_data` | `pytrends` |
| 6 | `outputs.py` | All 5 DB tables | 5 files in `out/` | — | — |
| 7 | `reporter.py` | DB + stats | stdout summary | — | — |

### Phase 1: Harvest

Iterates all queries from `config/queries.yaml`. For each query: checks ISO-week cache, then calls `AEOFirecrawlClient.search()` (1 Firecrawl credit). Parses web results + AI overview box. Rate-limited to 2 RPS (`firecrawl_rate_limit_rps`).

### Phase 2: Citation Graph

Aggregates all URLs across SERP results into a weighted graph. Classifies each URL domain (7 types). Selects top 30 non-Lido URLs for Phase 3.

**Decay-weight formula**: `1 / log2(position + 1)`

| Position | Weight |
|----------|--------|
| 1 | 1.000 |
| 3 | 0.631 |
| 5 | 0.431 |
| 10 | 0.289 |

The same URL appearing at position 1 for two queries accumulates `1.0 + 1.0 = 2.0` weight. This formula is load-bearing — do not change it without migrating `citation_graph` table history.

### Phase 3: Source Analysis

Scrapes the top 30 non-Lido URLs. For Reddit URLs: tries `.json` endpoint first (free, no API key), falls back to Firecrawl scrape on 403 (1 credit). For all other URLs: uses `client.scrape()` (1 credit each). Detects Lido mentions (regex), competitor presence (against `COMPETITOR_DOMAINS` in `utils.py`), page type, and extracts pain language from forum posts.

### Phase 4: AE Citations (optional)

Queries Perplexity `sonar` model via OpenRouter for high-priority queries only. Requires `PERPLEXITY_API_KEY`. Skipped cleanly if key is absent. **Deprecation: Chat Completions endpoint retires 2026-09-27 — see `docs/ae-citations.md`.**

### Phase 5: Trends (optional, `--skip-trends`)

Fetches Google Trends 12-month interest via `pytrends`. Hard 30-second timeout using `signal.alarm` (Unix only). Skip with `--skip-trends` for faster runs or non-Unix environments.

### Phase 6: Outputs

Writes 5 files to `out/`:

| File | DuckDB source | Reader |
|------|---------------|--------|
| `placement_targets.md` | `citation_graph` + `source_analysis` JOIN | Marketing/ops (primary deliverable) |
| `citation_graph.csv` | `citation_graph` full dump | Analysis |
| `query_opportunities.csv` | `serp_results` + `trend_data` | SEO/content |
| `pain_language.md` | `source_analysis.pain_language` (forum rows) | Content/messaging |
| `weekly_diff.md` | Current vs previous run `citation_graph` | Monitoring |

### Phase 7: Report

Prints run summary to stdout: queries run, cache hit rate, Firecrawl credits used, phases skipped, top 5 placement targets. Always runs (even on `--dry-run`).

## Cache System

**Key format**: `sha256(provider|query|iso_week).hexdigest()`

**Location**: `cache/` (gitignored)

**TTL**: One ISO week — cache expires every Monday. The same query on Monday and Friday of the same week hits cache; the following Monday forces a fresh fetch.

**Providers**: `firecrawl_search`, `firecrawl_scrape`, `reddit_json`, `perplexity`, `pytrends`

**Manual invalidation**: Delete `cache/<key>.json` to force a refresh for a specific query.

## Domain Classification

7 domain types (defined in `utils.py`):

| Type | Examples |
|------|---------|
| `lido_owned` | lido.app, app.lido.app |
| `review_platform` | g2.com, capterra.com, trustradius.com |
| `reddit_forum` | reddit.com |
| `competitor_owned` | nanonets.com, rossum.ai, parseur.com, datasnipper.com |
| `listicle` | URLs with "best", "vs", "alternatives", "compare" in path |
| `vendor_neutral_media` | — |
| `other` | Everything else |

## CLI Flags

| Flag | Default | Effect |
|------|---------|--------|
| `--dry-run` | False | No API calls; cache misses return empty; shows credit estimate |
| `--skip-trends` | False | Skip Phase 5 entirely |
| `--queries N` | None | Limit to first N queries from YAML |
