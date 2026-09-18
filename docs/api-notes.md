# API Notes — AEO Monitor

## Firecrawl (firecrawl-py v4.40.0)

**Client**: `firecrawl.v2.client.FirecrawlClient`

### search()
- Endpoint: `POST /v2/search`
- Returns: `SearchData` with `.web: list[SearchResultWeb | Document]`
- `SearchResultWeb` fields: `url`, `title`, `description` (snippet), `position` (Optional[int]), `category`
- AI overview box appears as a result with `category == "ai_overview"` — does not have a `position`
- **Credit cost**: 1 credit per search call (not per result returned)
- Default limit: 5; we use 10

### scrape()
- Endpoint: `POST /v2/scrape`
- Returns: `Document` with `.markdown`, `.metadata`
- **Credit cost**: 1 credit per page
- Pass `formats=["markdown"]` for clean text
- `metadata.modified_time` is the best source of last-updated date; often None

### map()
- Returns a list of URLs from a domain
- Not used in main pipeline; available for dry-run site enumeration
- **Credit cost**: 1 credit per call (returns up to limit URLs)

### extract
- **DEPRECATED / maintenance mode** as of v4.x. Do not use.
- Use `scrape()` + markdown parsing instead.

### get_credit_usage()
- Returns remaining_credits for the team
- Called before and after each run to compute spend
- Read-only; does not consume credits

---

## Reddit public JSON API

Reddit previously allowed unauthenticated `.json` requests (append `.json` to any thread URL).
As of ~2024, Reddit returns **403 Blocked** for most unauthenticated requests even with a valid User-Agent.

**Current behavior**: `source_analysis.py` attempts the `.json` path first, then falls back to Firecrawl scrape on 403. This uses 1 Firecrawl credit per Reddit URL but gives usable markdown content.

**Alternative**: Reddit's official API requires OAuth and a registered app. Not implemented to keep the tool keyless; add if Reddit content is a priority.

---

## Perplexity API

- Endpoint: `POST https://api.perplexity.ai/chat/completions`
- Model: `sonar` — use this. Other tiers: `sonar-pro` (better reasoning, 3×), `sonar-reasoning-pro`, `sonar-deep-research`. All return `citations[]`; tier doesn't change the field, only answer quality.
- Response: `{"choices": [...], "citations": ["https://...", ...]}`
- Citations are 0-indexed; position = index + 1
- **Cost**: ~$1/1M tokens (sonar); ~$3/1M tokens (sonar-pro)
- Skipped cleanly when `PERPLEXITY_API_KEY` is absent

**⚠ Migration deadline: September 27, 2026**
Perplexity is deprecating the Chat Completions endpoint in favor of a new "Agent API" (`client.responses.create()`). The new response structure for citations is not yet clearly documented. Migrate `ae_citations.py` before this date once Perplexity publishes the new citation access pattern.

---

## Google Trends (pytrends)

- Unofficial library; wraps Google Trends frontend
- Rate limited aggressively by Google — single-threaded with 1s sleep between calls
- Hard 30s timeout per keyword via `signal.alarm` (macOS/Unix only)
- Results cached for 7 days (ISO week bucket)
- **Reliability**: flaky. Expect occasional 429s or empty results. Pipeline continues on failure.
- `interest_over_time()` returns weekly data for the requested timeframe
- `related_queries()[keyword]["rising"]` returns rising related queries

---

## Credit Budget Reference (verified 2026-08-28)

| Operation | Credits |
|-----------|---------|
| Firecrawl search (1 call) | 1 |
| Firecrawl scrape (1 page) | 1 |
| Full 27-query run | ~57 (27 search + 30 scrape) |
| Dev run (3 queries) | ~33 (3 search + 30 scrape) |
