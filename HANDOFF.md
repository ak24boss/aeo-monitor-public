# AEO Monitor — Handoff

**Repo:** `github.com/ak24boss/aeo-monitor` (private, ak24boss account)
**Live dashboard:** `https://aeo-monitor-production-1b14.up.railway.app`
**Local dir:** `/Users/alexanderkamperin-lido/aeo-monitor-public/`
**Railway project ID:** `b55baf55-19ee-48da-84d9-1c3a9da66676`
**Railway service ID:** `1db4e1d3-5bd2-4a0c-b79f-db0b6d029826`

---

## Completed

### Generalization (Lido → any company)
- [x] `company.yaml` / `company.yaml.example` — single config file per tenant (company_name, company_domain, contact_email, competitors)
- [x] `config.py` — loads `company.yaml` at startup; raises `FileNotFoundError` with helpful message if missing
- [x] `models.py` — `lido_owned` → `brand_owned`, `lido_mentioned` → `brand_mentioned`, `lido_context` → `brand_context`
- [x] `utils.py` — removed hardcoded `COMPETITOR_DOMAINS`; `classify_domain()` and `classify_domain_with_url()` take `competitors: set[str]` param
- [x] `db.py` — schema uses `brand_mentioned`, `brand_context`; insert functions updated
- [x] `source_analysis.py` — `REDDIT_UA` from `contact_email`; `_find_lido()` → `_find_brand(text, company_name)`; competitors passed as param
- [x] `ae_citations.py` — `HTTP-Referer` uses `brand_domain` from settings
- [x] `citation_graph.py` — `get_top_non_lido_urls()` → `get_top_non_brand_urls()`; build function takes `brand_domain, competitors`
- [x] `outputs.py` — all SQL and output strings parameterized; output cols `brand_present`/`brand_best_position`
- [x] `cli.py` — generic; passes `brand_domain` and `company_name` through pipeline
- [x] `reporter.py` — filters on `brand_owned`
- [x] `dashboard.py` (renamed from `app.py`) — loads `company.yaml` at startup; all Lido hardcodes replaced with `COMPANY_NAME`, `BRAND_DOMAIN`, `BRAND_SLUG`, `COMPETITORS`; handles missing DB gracefully with `st.info()` instead of crashing
- [x] `tests/` — all 57 tests updated and passing (`make check`)
- [x] `README.md` — full rewrite as generic onboarding guide
- [x] `.gitignore` — covers `company.yaml`, `.env`, `cache/`, `out/`, `*.db`, `venv/`, `__pycache__/`
- [x] Deleted `PROGRESS.md` and `docs/seo-aeo-rundown.md` (Lido-specific)

### Railway deployment
- [x] App deployed to Railway under `alexkamp24@gmail.com` account
- [x] `Procfile` + `railway.json` both use `/app/.venv/bin/streamlit run dashboard.py`
- [x] `streamlit` and `plotly` added to `requirements.txt` (were missing, caused initial crash)
- [x] Dashboard handles missing DB gracefully (shows "run the pipeline" message instead of crashing)
- [x] **Deploy trick:** to ship the DB, remove `*.db` from `.gitignore` before `railway up`, then restore. Railway respects `.gitignore` but ignores `.railwayignore`.

### Orrigo AI — first run (2026-09-18)
- [x] `company.yaml` created for Orrigo AI (domain: orrigo.ai; competitors: responsive.io, loopio.com, qvidian.com, rocketdocs.com, dasseti.com, diligencevault.com, door.com, cntrl.com)
- [x] `config/queries.yaml` rewritten with 72 RFP/DDQ-specific queries across 8 categories
- [x] Pipeline run completed: 72 queries, 172 Firecrawl credits, 1,209 AE citation rows
- [x] 30 placement targets written to `out/placement_targets.md`
- [x] Live dashboard deployed with populated `aeo_monitor.db`

**Key findings from run:**
- Orrigo has **0 AI citations** (invisible to Perplexity across all 60 high-priority queries)
- Top AE-cited competitors: autorfp.ai (90x), responsive.io (79x), inventive.ai (70x), loopio.com (67x)
- autorfp.ai and inventive.ai are AI-native tools not in Orrigo's competitor list but dominating citations
- #1 placement target: Gartner Peer Insights (RFP Response Management) — score 10.3, 16 queries, all legacy competitors listed
- #2: arphie.ai DDQ listicle (updated Sep 14 2026) — 8 queries, active, has all major competitors
- AIMA DDQ page (aima.org) lists Dasseti + Diligence Vault — high-trust finance authority, Orrigo absent

---

## To Do

### Immediate (Orrigo AI actions)
- [ ] Submit Orrigo to Gartner Peer Insights (RFP Response Management category)
- [ ] Pitch arphie.ai DDQ listicle author for inclusion (`/blog/best-ai-tools-ddq-automation-due-diligence-questionnaire-software`)
- [ ] Publish `orrigo.ai/vs/loopio` and `orrigo.ai/vs/responsive` comparison pages (Loopio's comparison posts are ranking #1 for these queries)
- [ ] Reach out to AIMA (aima.org) for DDQ tools page inclusion
- [ ] Add autorfp.ai and inventive.ai to `company.yaml` competitors list (they're dominating AE citations, currently untracked)

### Dashboard / product
- [ ] **Auth** — add Streamlit username/password via `st.secrets` + Railway env vars (currently public to anyone with the URL)
- [ ] **Multi-tenant** — currently one `company.yaml` per deploy; future: support multiple companies in one DB with a company selector in the dashboard
- [ ] **Weekly diff page** — `weekly_diff.md` is written from run 2 onward; need a second run to populate it
- [ ] **Trends** — run once with `python __main__.py run` (no `--skip-trends`) to populate the Trends page

### Infrastructure
- [ ] **Persistent DB** — current approach (baking DB into Railway image) means data resets on every redeploy. Options: (a) Railway Volume for persistent storage, (b) periodic `railway up` redeploy workflow after each pipeline run
- [ ] **Scheduled runs** — add a cron or Railway cron job so the pipeline runs automatically every Monday
- [ ] **Cache persistence** — `cache/` dir is ephemeral on Railway; the pipeline re-fetches everything on each deploy. Move cache to a Volume alongside the DB.

### Repo / tooling
- [ ] Fix `railway.json` deprecation warning — migrate to `.railway/railway.ts` (Infrastructure as Code) before 2026-12-01
- [ ] Push latest code to `ak24boss/aeo-monitor` (most recent changes are local only — the Orrigo config, `.railwayignore`, and this file)
- [ ] Consider renaming `HANDOFF.md` → exclude from git (add to `.gitignore`) so it doesn't leak tenant config hints

---

## How to redeploy with fresh data

```bash
cd /Users/alexanderkamperin-lido/aeo-monitor-public

# 1. Run the pipeline
venv/bin/python __main__.py run --skip-trends

# 2. Temporarily allow DB in upload
#    Edit .gitignore: remove the `*.db` line

# 3. Deploy
railway up --service aeo-monitor --detach

# 4. Restore .gitignore: add `*.db` line back
```

## API keys (stored in local .env, not committed)

- `FIRECRAWL_API_KEY` — fc-fee8... (4,076 credits remaining as of 2026-09-18)
- `PERPLEXITY_API_KEY` — sk-or-v1... (OpenRouter key, ~$0.06/full run)

## Accounts

| Service | Account |
|---|---|
| GitHub repo | ak24boss (alexkamp24@gmail.com) |
| Railway | ak24boss / alexkamp24@gmail.com |
| Firecrawl | (Lido key — shared with aeo-monitor internal) |
| OpenRouter | (Lido key — shared with aeo-monitor internal) |
