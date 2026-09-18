# AEO Monitor — Feature List

> **WIP rule**: Only one feature may be `in-progress` at a time. Mark `done` only when the verification command passes. Do not start the next feature until the current one passes verification.

---

## Feature: Harvest phase

- **Behavior**: Runs Firecrawl SERP search for all configured queries with ISO-week caching; stores results in `serp_results` DuckDB table.
- **Verification**: `make dev-run` completes Phase 1 without error; `venv/bin/python -c "import duckdb; c=duckdb.connect('aeo_monitor.db'); print(c.execute('SELECT COUNT(*) FROM serp_results').fetchone())"` returns a non-zero count.
- **State**: [done]

---

## Feature: Citation graph

- **Behavior**: Aggregates SERP results into a decay-weighted URL citation graph (`1/log2(pos+1)`); classifies domains into 7 types; stores in `citation_graph` table.
- **Verification**: `make check` passes `tests/test_citation_graph.py` (10 tests).
- **State**: [done]

---

## Feature: Source analysis

- **Behavior**: Scrapes top 30 non-Lido URLs from citation graph; detects Lido mention, competitor presence, page type, and pain language; stores in `source_analysis` table.
- **Verification**: `make check` passes `tests/test_source_analysis.py` (12 tests).
- **State**: [done]

---

## Feature: AE citations (optional)

- **Behavior**: Queries Perplexity sonar for high-priority queries; extracts cited URLs; stores in `ae_citations` table. Skips cleanly if `PERPLEXITY_API_KEY` is absent.
- **Verification**: `make check` passes `tests/test_ae_citations.py` (5 tests).
- **State**: [done]

---

## Feature: Trends

- **Behavior**: Fetches Google Trends 12-month interest via pytrends for top queries; enforces 30-second timeout; stores in `trend_data` table. Skippable via `--skip-trends`.
- **Verification**: `make check` passes (mock); `make run-with-trends` completes without uncaught exception.
- **State**: [done]

---

## Feature: Output files

- **Behavior**: After each run, writes 5 files to `out/`: `placement_targets.md`, `citation_graph.csv`, `query_opportunities.csv`, `pain_language.md`, `weekly_diff.md`.
- **Verification**: After `make dev-run`, `ls out/` shows all 5 files with content (non-zero size).
- **State**: [done]

---

## Feature: Streamlit dashboard

- **Behavior**: 6-page dashboard at `localhost:8501` visualising all DuckDB tables. Pages: Overview, Placement Targets, Query Universe, AE Citations, SERP Analysis, Weekly Diff.
- **Verification**: `make dashboard` starts without Python exception; all 6 tabs load in browser.
- **State**: [done]

---

## Feature: DuckDB state persistence and weekly diff

- **Behavior**: All phase data persists to `aeo_monitor.db` across runs. On second run, `out/weekly_diff.md` shows new/dropped/changed URLs vs previous run date.
- **Verification**: Run `make dev-run` twice; confirm `out/weekly_diff.md` contains "vs [prev_date]" on second run.
- **State**: [done]

---

## Feature: 7 missing query categories

- **Behavior**: Add `email_triage`, `form_filling`, `document_splitting`, `bpo_reshoring`, `font_rex_alternatives`, `commerce_industry`, and `rules_logic_layer` categories to `config/queries.yaml`. Each should have 3-8 queries with appropriate `intent`, `vertical`, and `priority` values sourced from `~/Lido Content/lido-rundown.md`.
- **Verification**: `venv/bin/python -c "import yaml; d=yaml.safe_load(open('config/queries.yaml')); cats=list(d['categories']); assert all(k in cats for k in ['email_triage','form_filling','document_splitting','bpo_reshoring','font_rex_alternatives','commerce_industry','rules_logic_layer']), cats; print('OK')`
- **State**: [todo]

---

## Feature: Full 170-query pipeline run

- **Behavior**: Run the complete expanded query universe (170+ queries) for the first time, generating presence data for all categories.
- **Verification**: After `make run`, `venv/bin/python -c "import duckdb; c=duckdb.connect('aeo_monitor.db'); n=c.execute('SELECT COUNT(*) FROM serp_results').fetchone()[0]; assert n > 1000, n; print(f'{n} rows OK')"` passes; `out/placement_targets.md` mentions queries from at least 10 distinct categories.
- **State**: [todo]

---

## Feature: Perplexity Agent API migration

- **Behavior**: Migrate `ae_citations.py` function `query_perplexity()` (lines 57-87) to Perplexity's Agent API (`client.responses.create()`) before the Chat Completions endpoint retires on **2026-09-27**.
- **Verification**: `make check` passes all `test_ae_citations.py` tests; `make dev-run` shows AE citations in Phase 4 report output (requires valid key).
- **State**: [todo]

---

## Feature: Vertical filter in outputs

- **Behavior**: `python __main__.py run --vertical accounting` produces a `placement_targets.md` scoped to accounting-vertical queries only. The `--vertical` flag is optional; omitting it gives the full cross-vertical output.
- **Verification**: `make check` includes a test in `tests/test_outputs.py` asserting that filtered output excludes results from other-vertical queries.
- **State**: [todo]

---

## Feature: CI workflow

- **Behavior**: `.github/workflows/ci.yml` runs `make check` on every push to any branch, with no API keys required.
- **Verification**: File `.github/workflows/ci.yml` exists; workflow passes on a clean checkout with no `.env` file present.
- **State**: [todo]
