# AEO Monitor — Agent Entry File

## What this is

AEO Monitor is a weekly research tool for Lido (`lido.app`). It answers: which third-party pages (G2 listings, listicles, Reddit threads, comparison articles) appear in Google for document-extraction queries, which of those pages mention competitors but not Lido, and which are therefore the highest-leverage pages to get onto.

It runs a 7-phase pipeline — harvest → citation graph → source analysis → AE citations → trends → outputs → report — writing 5 files to `out/` and persisting all data to `aeo_monitor.db` (DuckDB). The query library lives in `config/queries.yaml`: 170 queries across 23 categories covering verticals, alternatives, integrations, problem-aware, and ROI angles.

## Orient yourself

- [`docs/pipeline.md`](docs/pipeline.md) — 7-phase architecture, decay-weight formula, cache system, output files
- [`docs/queries.md`](docs/queries.md) — QueryConfig schema, category list, how to add new queries
- [`docs/ae-citations.md`](docs/ae-citations.md) — Perplexity sonar phase, response formats, **migration deadline 2026-09-27**
- [`docs/database.md`](docs/database.md) — DuckDB schema for all 5 tables, example SQL queries
- [`docs/development.md`](docs/development.md) — Setup, test guide, how to add a test
- [`docs/dashboard.md`](docs/dashboard.md) — Streamlit dashboard page inventory (6 pages)
- [`docs/api-notes.md`](docs/api-notes.md) — Firecrawl API notes and rate limiting

## Run it

```bash
make check        # run test suite (no API keys, <10 seconds)
make dry-run      # print plan + credit estimate, zero API calls
make dev-run      # 3 queries, skip trends (fast, costs ~33 credits)
make run          # full 170-query run, skip flaky trends
```

## Verify your work

After any change, `make check` must pass. The test suite runs offline — no API keys or network required — and completes in under 10 seconds. Do not commit if `make check` fails.

## Hard constraints — do not break these

- **`_decay_weight` formula** (`citation_graph.py`) is the citation scoring definition. Changing it invalidates all historical scores stored in `citation_graph` table.
- **Cache key** (`cache.py: _cache_key`) includes ISO week. Changing it invalidates all existing cache files in `cache/`.
- **`FIRECRAWL_API_KEY`** is required; pipeline will not start without it. **`PERPLEXITY_API_KEY`** is optional — Phase 4 skips cleanly if absent.
- **Perplexity Chat Completions deprecates 2026-09-27.** Migration is isolated to `ae_citations.py` lines 57-87. See `docs/ae-citations.md`.
- **`signal.alarm`** in `trends.py` is Unix-only. Always preserve `--skip-trends` support for portability.
- **`config/queries.yaml`** is the only file ops/marketing should need to edit. Keep the schema stable.

## Adding queries

Edit `config/queries.yaml`. No code changes needed. See `docs/queries.md`. Do not duplicate existing entries — 23 categories are already present as of 2026-08-31.

## Current pipeline state

Last full run: **2026-08-28** (27 queries only). Current YAML: **170 queries** across 23 categories. The expanded universe has never been run. Seven additional categories are pending (see `PROGRESS.md`). `PERPLEXITY_API_KEY` not confirmed — `ae_citations` table is empty.

## Session exit checklist

Before ending any session:
- [ ] `make check` passes
- [ ] `PROGRESS.md` updated with what was done and what's next
- [ ] Any architectural decision logged in `DECISIONS.md`
- [ ] No debug code left (`print()`, temporary `TODO` comments)
