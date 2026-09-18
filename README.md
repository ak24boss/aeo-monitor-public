# AEO Monitor

Weekly SEO/AEO research tool for any company. Answers: **which third-party pages (G2 listings, listicles, Reddit threads, comparison articles) appear across your target queries, which of those pages mention competitors but not you, and therefore which pages are the highest-leverage targets to get onto.**

Also tracks which of those pages get cited by AI answer engines (Perplexity), so you know where to focus for both classic SEO and the emerging AEO/GEO layer.

---

## Setup

```bash
git clone https://github.com/ak24boss/aeo-monitor
cd aeo-monitor
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 1. Configure your company

```bash
cp company.yaml.example company.yaml
```

Edit `company.yaml`:

```yaml
company_name: "Acme Corp"
company_domain: "acme.com"
contact_email: "you@acme.com"

competitors:
  - competitor1.com
  - competitor2.com
```

### 2. Configure your API keys

```bash
cp .env.example .env
```

Edit `.env`:

```
FIRECRAWL_API_KEY=fc-your-key-here   # required — get one at firecrawl.dev
PERPLEXITY_API_KEY=                  # optional — enables AE citations phase
```

### 3. Configure your queries

Edit `config/queries.yaml`. The included file is a working example for document/IDP companies — replace or extend it with queries relevant to your product:

```yaml
categories:
  commercial:
    - text: "best [your category] software"
      intent: "tool discovery"
      vertical: "general"
      priority: high

  alternatives:
    - text: "[competitor] alternatives"
      intent: "comparison"
      vertical: "general"
      priority: high

  problem_aware:
    - text: "how to [solve the problem your product solves]"
      intent: "use case"
      vertical: "finance"
      priority: medium
```

**Query fields:**
- `intent`: `tool discovery` | `use case` | `comparison` | `workflow` | `competitor displacement`
- `vertical`: any label you want (used for filtering in the dashboard)
- `priority`: `high` queries are sent to Perplexity for AE citations; `medium`/`low` are SERP-only

---

## Running

```bash
# Dry run — prints plan and estimated credit cost, zero API calls
python __main__.py run --dry-run

# Dev run — first 5 queries, skip Google Trends (faster, cheaper for testing)
python __main__.py run --queries 5 --skip-trends

# Full run, skip trends (recommended weekly cadence)
python __main__.py run --skip-trends

# Full run with Google Trends
python __main__.py run
```

### Streamlit dashboard

```bash
venv/bin/streamlit run dashboard.py
```

Opens at `localhost:8501`. Six pages: Overview, Placement Targets, Query Universe, AE Citations, SERP Analysis, Weekly Diff.

---

## Output files

All written to `out/` after each run.

| File | Purpose |
|------|---------|
| `placement_targets.md` | **Primary deliverable.** Ranked list of pages where you're absent, with recommended action per page type. |
| `citation_graph.csv` | All URLs seen across queries with weighted scores and domain types. |
| `query_opportunities.csv` | Per-query brand presence + trend direction. |
| `pain_language.md` | Verbatim complaint quotes from Reddit threads. |
| `weekly_diff.md` | What changed since the previous run. Populated from run 2 onward. |

---

## Cost per run

| Run type | Firecrawl credits | Perplexity (optional) |
|---|---|---|
| Full run — N queries | N search + 30 scrape | ~$0.001 × high-priority queries |
| Dev run — 5 queries | 5 search + 30 scrape | — |

Firecrawl charges per credit (not per result). Cache is keyed by ISO week — re-running within the same week costs nothing.

---

## Architecture

Seven-phase pipeline, all output to a single DuckDB file (`aeo_monitor.db`):

1. **Harvest** — Firecrawl search for each query → `serp_results` table
2. **Citation graph** — Decay-weighted aggregation by URL using `1/log2(position+1)` → `citation_graph` table
3. **Source analysis** — Scrape top 30 non-brand URLs, detect your brand and competitor mentions → `source_analysis` table
4. **Answer engine** — Perplexity `sonar` for structured citations on high-priority queries → `ae_citations` table
5. **Trends** — pytrends 12-month interest (best-effort, 30s timeout) → `trend_data` table
6. **Outputs** — Write five files to `out/`
7. **Report** — Stdout summary: queries run, cache rate, credits used, top 5 targets

**Caching:** all API responses cached in `cache/` by `sha256(provider|query|iso_week)`. Fresh data fetched once per week per query.

**Domain classification:**
| Type | Examples |
|---|---|
| `brand_owned` | your domain |
| `review_platform` | g2.com, capterra.com, gartner.com |
| `reddit_forum` | reddit.com |
| `competitor_owned` | domains listed in `company.yaml` |
| `listicle` | URLs containing "best", "vs", "alternatives", "compare" |
| `other` | everything else |

---

## Inspecting the database

```bash
duckdb aeo_monitor.db
```

```sql
-- Top pages by citation weight
SELECT url, domain_type, weighted_score, queries_appearing_in
FROM citation_graph ORDER BY weighted_score DESC LIMIT 10;

-- Pages where your brand is mentioned
SELECT url, brand_context FROM source_analysis WHERE brand_mentioned = TRUE;

-- Queries and brand presence
SELECT query, COUNT(*) as results FROM serp_results GROUP BY query;
```

---

## Development

```bash
make check      # run all 57 tests
make dry-run    # dry run with credit estimate
make run        # full pipeline
make dashboard  # open Streamlit
```
