"""Phase 4A — AI engine direct-query probes.

Runs each probe from probes.yaml against each configured provider,
detects brand mentions, extracts cited URLs, and persists to ae_probe_results.
Skips cleanly if probes list is empty or no providers are configured.
"""
from __future__ import annotations
import hashlib
import json
import logging
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import duckdb

from cache import CacheStats
from db import insert_ae_probe_results
from models import AEProbeRow, ProbeConfig
from providers.base import AIEngineProvider
from source_analysis import _find_brand, _find_competitors

log = logging.getLogger(__name__)


def run_ai_engine_probe_phase(
    probes: list[ProbeConfig],
    providers: list[AIEngineProvider],
    conn: duckdb.DuckDBPyConnection,
    company_name: str,
    competitors: set[str],
    cache_dir: Path,
    stats: CacheStats,
    run_date: date,
    dry_run: bool = False,
) -> list[AEProbeRow]:
    if not probes or not providers:
        log.info("Phase 4A: skipped (no probes or no providers configured)")
        return []

    log.info(
        "Phase 4A: AI engine probes — %d probes × %d provider(s)",
        len(probes), len(providers),
    )

    rows: list[AEProbeRow] = []

    for provider in providers:
        for probe in probes:
            cache_key = _probe_cache_key(provider.engine_name, probe.id, run_date)
            cached = _load_cache(cache_dir, cache_key)

            if cached is not None:
                stats.hits += 1
                log.info(
                    "Phase 4A: [cache hit] %s / %s", provider.engine_name, probe.id
                )
                probe_resp = cached
            elif dry_run:
                stats.misses += 1
                log.info(
                    "Phase 4A: [dry run] %s / %s — skipping API call",
                    provider.engine_name, probe.id,
                )
                continue
            else:
                stats.misses += 1
                try:
                    probe_resp = provider.run(probe.text, probe.id)
                    _save_cache(cache_dir, cache_key, probe_resp.__dict__)
                except Exception as exc:
                    log.warning(
                        "Phase 4A: %s / %s failed — %s",
                        provider.engine_name, probe.id, exc,
                    )
                    continue

            text = probe_resp.response_text if hasattr(probe_resp, "response_text") else probe_resp.get("response_text", "")
            cited_urls = probe_resp.cited_urls if hasattr(probe_resp, "cited_urls") else probe_resp.get("cited_urls", [])
            raw = probe_resp.raw if hasattr(probe_resp, "raw") else probe_resp.get("raw", {})

            brand_mentioned, brand_context = _find_brand(text, company_name)
            competitors_found = _find_competitors(text, competitors)
            cited_domains = [_domain(u) for u in cited_urls if u]
            # Google provider embeds ad slot domains in raw["_ads_domains"]
            sponsored_domains = raw.get("_ads_domains", []) if isinstance(raw, dict) else []

            row = AEProbeRow(
                run_date=run_date,
                engine=provider.engine_name,
                probe_id=probe.id,
                probe_text=probe.text,
                brand_mentioned=brand_mentioned,
                brand_context=brand_context,
                competitors_mentioned=competitors_found,
                cited_urls=cited_urls,
                cited_domains=cited_domains,
                sponsored_domains=sponsored_domains,
                raw_response=json.dumps(raw),
                seed_topic=probe.seed_topic,
                perturbation_class=probe.perturbation_class,
                perturbation_type=probe.perturbation_type,
            )
            rows.append(row)
            log.info(
                "Phase 4A: %s / %s — brand=%s, competitors=%s, citations=%d, sponsored=%s",
                provider.engine_name, probe.id,
                brand_mentioned, competitors_found, len(cited_urls), sponsored_domains,
            )

    insert_ae_probe_results(conn, rows)
    log.info("Phase 4A: inserted %d rows", len(rows))
    return rows


def _probe_cache_key(engine: str, probe_id: str, run_date: date) -> str:
    iso_week = run_date.isocalendar()
    raw = f"ae_probe|{engine}|{probe_id}|{iso_week.year}-W{iso_week.week:02d}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_cache(cache_dir: Path, key: str):
    path = cache_dir / f"ae_probe_{key}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(cache_dir: Path, key: str, data: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"ae_probe_{key}.json"
    # cited_urls may contain ProviderResponse objects — ensure serialisable
    safe = {k: (list(v) if hasattr(v, "__iter__") and not isinstance(v, (str, dict)) else v)
            for k, v in data.items()}
    with open(path, "w") as f:
        json.dump(safe, f)


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lstrip("www.")
    except Exception:
        return ""
