# AEO Monitor — Streamlit Dashboard

## Overview

`app.py` (~560 lines) is a 6-page Streamlit dashboard that visualises all DuckDB tables. Run with `make dashboard`. Serves on `localhost:8501`.

**Auth**: None — this is a local tool. Do not expose publicly.

**Data source**: `aeo_monitor.db` (read-only). Requires at least one pipeline run to populate.

## Pages

### 1. Overview

Run summary KPIs: total queries run, URLs in citation graph, source analysis coverage rate, AE citation count. Includes a bar chart of domain type distribution in the citation graph.

### 2. Placement Targets

The primary deliverable page. Ranked list of non-Lido URLs by `weighted_score` from `citation_graph`. Filters: domain type selector. Shows: URL, score, domain type, number of queries, top position, and whether Lido is mentioned (from `source_analysis` join).

Color coding matches `DOMAIN_COLORS` in `app.py` (review_platform = indigo, listicle = amber, competitor_owned = red, reddit_forum = orange, vendor_neutral_media = green, lido_owned = blue, other = gray).

### 3. Query Universe

All queries from `serp_results` with Lido presence status, average position, and trend direction. Filterable by category and vertical. Highlights queries where `lido_present = FALSE` — these are content/SEO gaps.

### 4. AE Citations

Perplexity citation share by domain. Shows which pages are most frequently cited by the AI answer engine across high-priority queries. **This page is empty until Phase 4 runs with a valid `PERPLEXITY_API_KEY`.**

### 5. SERP Analysis

Per-query position breakdown. Grouped by category. Shows position distribution and which domains consistently appear at the top.

### 6. Weekly Diff

New, dropped, and score-changed URLs between the current run and the previous run. Requires at least two pipeline runs to populate. Driven by `out/weekly_diff.md`.

## Known issues / fixes applied

- **`int(NaN)` on `lido_position`**: Fixed with `pd.notna(lp)` check before casting. Occurs when a URL has no Lido position data in `source_analysis`.

## Category display order

Pages that show categories use `FUNNEL_ORDER` in `app.py` (line 33) to sort by funnel stage (commercial → problem-aware → integration → ROI → vertical). New categories added to `queries.yaml` appear at the bottom unless added to `FUNNEL_ORDER`.
