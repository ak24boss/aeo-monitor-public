# AEO Monitor — Development Guide

## Prerequisites

- Python 3.14.7 (see `.python-version`)
- Existing `venv/` with dependencies installed (created once)
- `FIRECRAWL_API_KEY` in `.env` for live runs (not needed for tests)

## Setup

```bash
# From scratch
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Or reproduce exact locked versions
venv/bin/pip install -r requirements-lock.txt
```

## Environment variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
FIRECRAWL_API_KEY=fc-your-key-here
PERPLEXITY_API_KEY=sk-or-your-openrouter-key  # optional
```

`FIRECRAWL_API_KEY` is required to start the pipeline. `PERPLEXITY_API_KEY` is optional — Phase 4 skips cleanly if absent.

## Running the pipeline

```bash
make dry-run      # Plan only, no API calls, shows credit estimate
make dev-run      # 3 queries, skip trends (~33 Firecrawl credits)
make run          # Full 170-query run, skip trends (~200 credits)
make run-with-trends   # Full run including Google Trends (flaky, +60s)
```

## Running tests

```bash
make check        # Fast, no API keys, <10 seconds
```

The test suite runs entirely offline using mock clients in `tests/fakes.py`. No `FIRECRAWL_API_KEY` or `PERPLEXITY_API_KEY` is needed.

## How to add a test

1. Create `tests/test_<module>.py`
2. Import the function or class you want to test
3. Use `tests/fakes.py` for any external client (`FakeFirecrawlClient`, `FakeTrendReq`)
4. Use `tmp_path` (pytest fixture) for cache directory tests
5. Run `make check` to verify it passes

**Example**:
```python
from cache import save_cache, CacheStats
from harvest import harvest_serp
from models import QueryConfig
from tests.fakes import FakeFirecrawlClient
from datetime import date

def test_my_feature(tmp_path):
    query = QueryConfig(text="test query", intent="tool discovery",
                        vertical="general", priority="high", category="commercial")
    stats = CacheStats()
    results = harvest_serp(query, FakeFirecrawlClient(), tmp_path, stats, date.today())
    assert len(results) == 1
```

## Platform notes

- `trends.py` uses `signal.alarm()` for a 30-second timeout. This is **Unix/macOS only** — it will not work on Windows. Use `--skip-trends` on Windows or in CI.
- The Streamlit dashboard (`dashboard.py`) has no authentication. Do not expose it to the public internet without adding auth (e.g., Streamlit secrets-based password gate).
- `write_query_opportunities_csv` in `outputs.py` uses DuckDB-specific `FIRST()`/`LAST()` aggregate functions — these are not standard SQL and will not port to SQLite or PostgreSQL without changes.

## Project structure

```
aeo-monitor/
├── AGENTS.md           # Agent entry file (read this first)
├── Makefile            # All canonical commands
├── PROGRESS.md         # Current state and next actions
├── DECISIONS.md        # Architectural decision log
├── features.md         # Feature list with verification commands
├── pytest.ini          # Test configuration
├── requirements.txt    # Loose dependency pins
├── requirements-lock.txt # Exact locked versions (for reproducibility)
├── .python-version     # Python version pin (3.14.7)
├── .env                # API keys (gitignored)
├── .env.example        # Template for .env
├── config/
│   └── queries.yaml    # 170 queries across 23 categories
├── docs/               # Topic documentation
├── tests/              # Test suite
│   ├── fakes.py        # Mock clients (no network/API keys)
│   └── fixtures/       # Static test data
├── cache/              # ISO-week response cache (gitignored)
├── out/                # Output files (gitignored)
├── aeo_monitor.db      # DuckDB database (gitignored)
├── dashboard.py              # Streamlit dashboard
├── __main__.py         # CLI entry point
├── cli.py              # 7-phase pipeline orchestrator
├── harvest.py          # Phase 1: SERP search
├── citation_graph.py   # Phase 2: URL scoring
├── source_analysis.py  # Phase 3: Page scraping
├── ae_citations.py     # Phase 4: Perplexity AE
├── trends.py           # Phase 5: Google Trends
├── outputs.py          # Phase 6: File writers
├── reporter.py         # Phase 7: Run summary
├── cache.py            # Cache read/write/stats
├── db.py               # DuckDB schema and insert functions
├── models.py           # Pydantic data models
├── config.py           # Settings dataclass and YAML loader
├── utils.py            # Domain classification, credit estimation
└── firecrawl_client.py # Firecrawl API wrapper
```
