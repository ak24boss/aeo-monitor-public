# AEO Monitor — Architectural Decisions

---

## Decision 1 — Decay-weight formula: `1 / log2(position + 1)`

**Date**: 2026-08-28
**Status**: accepted

**Context**: We need a position-weighted citation score that gives position 1 the highest weight and falls off sub-linearly. Multiple formulas were considered.

**Decision**: Use `1 / log2(position + 1)`, the reciprocal log formula used in Discounted Cumulative Gain (DCG).
- Position 1: 1.000
- Position 3: 0.631
- Position 5: 0.431
- Position 10: 0.289

**Consequences**: Changing this formula invalidates all historical scores stored in the `citation_graph` table — you'd need to either clear the table or re-run all historical data. The formula is intentionally simple to understand and audit. It is locked as a hard constraint in `AGENTS.md`.

---

## Decision 2 — DuckDB over SQLite or PostgreSQL

**Date**: 2026-08-28
**Status**: accepted

**Context**: Need a local, embeddable database that handles analytical queries (GROUP BY, window functions, JSON extraction) well. The pipeline is single-process with no concurrent writes.

**Decision**: DuckDB — columnar storage engine, optimised for analytical reads, file-based (single `.db` file), excellent pandas integration via `.df()`, supports `INSERT OR REPLACE`, `FIRST()`/`LAST()` aggregates, JSON functions.

**Consequences**: The DuckDB file is not safe for concurrent writes — this is fine since the pipeline is single-process. The Streamlit dashboard opens a separate read-only connection. `FIRST()`/`LAST()` in `outputs.py` are DuckDB-specific; porting to standard SQL would require `MIN BY` subqueries.

---

## Decision 3 — Cache keyed by ISO week, not by date

**Date**: 2026-08-28
**Status**: accepted

**Context**: AEO Monitor is a weekly tool — re-running on Tuesday versus Thursday of the same week should not cost additional Firecrawl credits.

**Decision**: Cache key is `sha256(provider|query|iso_week)` where `iso_week = f"{year}-W{week:02d}"`. This means all runs within the same ISO week (Monday–Sunday) share the same cache for a given query and provider.

**Consequences**: Fresh data is only fetched once per ISO week per query. If you need same-day fresh data (e.g., after a major SERP shake-up), delete the specific cache file at `cache/<sha256>.json`. Do not change `_cache_key()` in `cache.py` without deleting all existing cache files — the key change will force a cold cache on next run.

---

## Decision 4 — Perplexity via OpenRouter, not direct Perplexity API

**Date**: 2026-08-28
**Status**: accepted (but see migration note)

**Context**: Both the Perplexity direct API and OpenRouter give access to `sonar`. OpenRouter provides a single billing account for multiple models and avoids managing separate per-provider keys.

**Decision**: Use OpenRouter endpoint (`https://openrouter.ai/api/v1/chat/completions`) with model `perplexity/sonar`. The `PERPLEXITY_API_KEY` env var is actually the OpenRouter key.

**Consequences**: The response shape differs slightly from native Perplexity — citations may appear in `choices[0].message.annotations[]` rather than top-level `citations[]`. Both formats are handled in `ae_citations.py` lines 65-88. **Perplexity Chat Completions deprecates 2026-09-27** — migration required. See `docs/ae-citations.md`.

---

## Decision 5 — Reddit: try `.json` endpoint first, Firecrawl fallback on 403

**Date**: 2026-08-28
**Status**: accepted

**Context**: Reddit's `/thread_id.json` endpoint returns structured JSON (post + comments) with no API key required. However, Reddit has increasingly blocked this for non-browser traffic.

**Decision**: Try `.json` endpoint first (free, no credits). On 403 or any exception, fall back to `client.scrape()` (1 Firecrawl credit). Reddit posts go through `PROVIDER_REDDIT` provider for caching; if they fall back to scrape, the cache is saved under `PROVIDER_SCRAPE`.

**Consequences**: Reddit URLs cost 1 Firecrawl credit each when the JSON endpoint is blocked (which is almost always the case as of mid-2026). If Reddit content is high-priority, consider implementing OAuth app authentication to the Reddit API instead.

---

## Decision 6 — AE phase runs on high-priority queries only

**Date**: 2026-08-28
**Status**: accepted

**Context**: Sending all queries to Perplexity would cost ~$0.17/run (170 queries × $0.001). Most queries don't need AI-engine citation data — the SERP data is sufficient.

**Decision**: Only queries with `priority: high` in `queries.yaml` are sent to the AE phase. With ~20% of queries marked high, the cost is ~$0.034/run.

**Consequences**: Medium and low-priority queries have no data in `ae_citations` table. The dashboard's AE Citations page only shows high-priority query coverage. If broader coverage is needed, either (a) mark more queries `high` or (b) create a separate cheaper Perplexity tier.

---

## Decision 7 — Query universe expanded 27 → 170 in August 2026

**Date**: 2026-08-28
**Status**: accepted

**Context**: The original 27 queries (commercial + alternatives) covered Lido's most obvious search terms. Cross-referencing `~/Lido Content/lido-rundown.md` (the internal GTM doc) against SERP coverage revealed that large segments of the buyer journey had zero coverage: problem-aware queries, vertical-specific queries, integration queries, BPO reshoring queries, and ROI queries.

**Decision**: Expand to 23 categories, 170 total queries. The expansion map was driven entirely by GTM triggers and product tiers listed in `lido-rundown.md`. Seven additional categories were identified but not yet added (email triage, form filling, document splitting, BPO reshoring, Font Rex alternatives, commerce/industry, rules & logic layer).

**Consequences**: The 170-query set has never been run as a batch. The first full run will be a cold cache, costing approximately 170 Firecrawl search credits + 30 scrape credits ≈ 200 credits (~$2). Run with `make run` after adding the 7 pending categories.
