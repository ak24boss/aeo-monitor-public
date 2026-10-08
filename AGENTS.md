# AEO Monitor — Agent Entry File

## What this is

AEO Monitor is a multi-company SEO/AEO research platform. It answers: which third-party pages appear in Google for your target queries, which of those pages mention competitors but not your brand (highest-leverage placement targets), and which of those pages AI engines actively cite when users ask directly about your problem space.

It runs a 9-phase pipeline — harvest → citation graph → source analysis → AE citations (SERP-driven) → **AI engine probes** → **cross-reference** → trends → outputs → report — writing output files to `companies/{slug}/out/` and persisting all data to `companies/{slug}/data.db` (DuckDB).

Company identity, queries, and AI engine probes live in `companies/{slug}/` — swap companies by pointing `--company` at a different directory.

## Orient yourself

- [`docs/pipeline.md`](docs/pipeline.md) — 9-phase architecture, decay-weight formula, cache system, output files
- [`docs/queries.md`](docs/queries.md) — QueryConfig schema, category list, how to add new queries
- [`docs/ae-citations.md`](docs/ae-citations.md) — Perplexity sonar phase (SERP-driven), response formats
- [`docs/database.md`](docs/database.md) — DuckDB schema for all 7 tables, example SQL queries
- [`docs/development.md`](docs/development.md) — Setup, test guide, how to add a test
- [`docs/dashboard.md`](docs/dashboard.md) — Streamlit dashboard page inventory (7 pages)
- [`docs/api-notes.md`](docs/api-notes.md) — Firecrawl API notes and rate limiting

**New modules (hybrid layer):**
- `providers/` — pluggable AI engine provider package (`base.py`, `mock.py`, `perplexity.py`, `claude.py`, `openai_provider.py`)
- `ai_engine_probe.py` — Phase 4A: runs `probes.yaml` prompts against AI engines, detects brand mentions, extracts citations
- `cross_reference.py` — Phase 4B: SQL join of SERP citation graph × AI engine citations → prioritised placement targets

**Company template files (per slug):**
- `companies/{slug}/profile.yaml` — company identity, domain, competitors, optional pipeline overrides
- `companies/{slug}/queries.yaml` — SERP query library (same schema as legacy `config/queries.yaml`)
- `companies/{slug}/probes.yaml` — AI engine direct-query prompts + engine whitelist
- `companies/{slug}/data.db` — per-company DuckDB (created at runtime)
- `companies/{slug}/out/` — per-company output files

## Run it

```bash
# Legacy (reads root company.yaml — backward compat)
make check        # run test suite (no API keys, <10 seconds)
make dry-run      # print plan + credit estimate, zero API calls
make dev-run      # 3 queries, skip trends

# Multi-company
make dry-run-lido              # dry run for Lido
make dev-run-lido              # 3 queries, real API calls
make run-lido                  # full run, skip trends
make dashboard-lido            # Streamlit dashboard for Lido

# Generic (COMPANY var)
make dry-run-company COMPANY=acme
make dev-run-company COMPANY=acme

# Onboard a new company
make new-company SLUG=acme     # copies _template/, edit the three YAML files
```

## Verify your work

After any change, `make check` must pass. The test suite runs offline — no API keys or network required — and completes in under 10 seconds. Do not commit if `make check` fails.

## Hard constraints — do not break these

- **`_decay_weight` formula** (`citation_graph.py`) is the citation scoring definition. Changing it invalidates all historical scores stored in `citation_graph` table.
- **Cache key** (`cache.py: _cache_key`) includes ISO week. Changing it invalidates all existing cache files in `cache/`.
- **`FIRECRAWL_API_KEY`** is required; pipeline will not start without it. **`PERPLEXITY_API_KEY`** is optional — Phase 4 skips cleanly if absent.
- **`signal.alarm`** in `trends.py` is Unix-only. Always preserve `--skip-trends` support for portability.
- **`companies/_template/`** must never be run directly — `load_settings(company_slug="_template")` raises `ValueError` by design.
- **Per-company DuckDB** — each company has `companies/{slug}/data.db`. Never share a DB across companies.
- **Probe cache key** uses `probe.id`, not probe text. Renaming an `id` in `probes.yaml` busts cache; rephrasing the text does not.
- **Phase 4 (SERP-driven AE citations) is preserved** — Phase 4A (probe-driven) is additive, not a replacement.

## Adding a new company

```bash
make new-company SLUG=acme
# Then edit:
#   companies/acme/profile.yaml  — name, domain, competitors
#   companies/acme/queries.yaml  — SERP query library
#   companies/acme/probes.yaml   — AI engine probes
make dry-run-company COMPANY=acme
```

## Current pipeline state

Legacy (root company.yaml): Orrigo AI. Last full run: 2026-08-28.
Lido (`companies/lido/`): template created 2026-10-06. First run pending.

## Session exit checklist

Before ending any session:
- [ ] `make check` passes
- [ ] `PROGRESS.md` updated with what was done and what's next
- [ ] Any architectural decision logged in `DECISIONS.md`
- [ ] No debug code left (`print()`, temporary `TODO` comments)
