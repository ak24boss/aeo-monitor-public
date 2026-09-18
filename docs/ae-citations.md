# AEO Monitor — Answer-Engine Citations Phase

## What it does

Phase 4 queries the Perplexity `sonar` model for each `priority: high` query. Sonar is an LLM that searches the web in real time and cites its sources. The phase extracts those cited URLs and stores them in `ae_citations`, showing which pages an AI answer engine cites when a user asks a document-extraction query.

This reveals a second dimension beyond SERP rankings: a page may rank #4 organically but be cited by Perplexity for 10 queries — that's a high-leverage AEO target.

## API details

**Endpoint (current)**: `POST https://openrouter.ai/api/v1/chat/completions`

**Model**: `perplexity/sonar`

**Auth**: `Authorization: Bearer $PERPLEXITY_API_KEY` (this is actually your OpenRouter key)

**Cost**: ~$0.001/query (sonar tier on OpenRouter)

**Phase trigger**: only `priority: high` queries are sent. With 170 queries and ~20% high-priority, expect ~34 queries → ~$0.034/run.

## ⚠️ Migration deadline: 2026-09-27

**Perplexity is retiring the Chat Completions endpoint on 2026-09-27.** The replacement is the Agent API (`client.responses.create()`). After this date, Phase 4 will fail with a 404 or 410 unless migrated.

**Migration scope**: `ae_citations.py`, function `query_perplexity()`, lines 57-87.

**Current request structure**:
```python
httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    json={
        "model": "perplexity/sonar",
        "messages": [{"role": "user", "content": query.text}],
    },
)
```

**Migration target**: Switch to Perplexity's native Agent API or OpenRouter's updated endpoint when available. Monitor `docs/api-notes.md` for updates.

## Response formats (both handled)

The phase handles two citation formats depending on whether you call via OpenRouter or native Perplexity:

**Format 1 — Top-level `citations[]`** (native Perplexity):
```json
{
  "citations": ["https://g2.com/lido", "https://capterra.com/lido"],
  "choices": [...]
}
```

**Format 2 — `choices[0].message.annotations[]`** (OpenRouter):
```json
{
  "citations": [],
  "choices": [{
    "message": {
      "annotations": [
        {"type": "url_citation", "url_citation": {"url": "https://g2.com/lido"}}
      ]
    }
  }]
}
```

Both formats are parsed in `ae_citations.py` lines 65-88. The phase tries `citations[]` first; falls back to annotations if empty.

## If the key is absent

If `PERPLEXITY_API_KEY` is not set (or is an empty string), Phase 4 logs a warning and returns `[]`. The pipeline continues normally. The `ae_citations` table will remain empty. The dashboard's "AE Citations" page handles this gracefully.

**Current status (2026-08-31)**: Key not confirmed present. `ae_citations` table is empty.

## Cache

Perplexity responses are cached under provider `"perplexity"`, scoped to ISO week. Cache key: `sha256("perplexity|{query.text}|{iso_week}")`. Delete `cache/<key>.json` to force a fresh fetch.
