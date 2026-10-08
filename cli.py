from __future__ import annotations
import argparse
import logging
import sys
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aeo_monitor",
        description="SEO/AEO placement monitor — tracks where your brand appears (and doesn't) across search and AI answer engines",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run the full pipeline")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan and credit estimate without making API calls",
    )
    run_parser.add_argument(
        "--skip-trends",
        action="store_true",
        help="Skip the Google Trends phase",
    )
    run_parser.add_argument(
        "--queries",
        type=int,
        default=None,
        metavar="N",
        help="Limit to first N queries (dev mode)",
    )
    run_parser.add_argument(
        "--company",
        type=str,
        default=None,
        metavar="SLUG",
        help="Company slug — loads from companies/{slug}/ instead of root company.yaml",
    )
    return parser


def cmd_run(args) -> None:
    from config import load_settings
    from db import get_connection
    from firecrawl_client import AEOFirecrawlClient
    from cache import CacheStats
    from harvest import run_harvest_phase
    from citation_graph import run_citation_graph_phase
    from source_analysis import run_source_analysis_phase
    from ae_citations import run_ae_phase
    from ai_engine_probe import run_ai_engine_probe_phase
    from cross_reference import run_cross_reference_phase
    from trends import run_trends_phase
    from outputs import (
        write_citation_graph_csv,
        write_placement_targets_md,
        write_query_opportunities_csv,
        write_pain_language_md,
        write_weekly_diff_md,
        write_ai_visibility_md,
    )
    from reporter import print_run_summary
    from utils import estimate_credit_cost

    dry_run: bool = args.dry_run
    skip_trends: bool = args.skip_trends
    run_date = date.today()

    settings = load_settings(query_limit=args.queries, company_slug=getattr(args, "company", None))
    log.info("Loaded %d queries", len(settings.queries))

    if dry_run:
        cost = estimate_credit_cost(settings.queries, settings)
        print("\n--- DRY RUN — Estimated credit cost ---")
        print(f"  Queries:                   {cost['queries']}")
        print(f"  High-priority queries:     {cost['high_priority_queries']}")
        print(f"  Firecrawl search credits:  {cost['firecrawl_search_credits']}")
        print(f"  Firecrawl scrape credits:  {cost['firecrawl_scrape_credits']}")
        print(f"  Total Firecrawl credits:   {cost['total_firecrawl_credits']}")
        print(f"  Perplexity (USD est.):     ${cost['perplexity_usd_estimate']:.4f}")
        if skip_trends:
            print("  Trends:                    DISABLED")
        print("---------------------------------------\n")

    conn = get_connection(settings.db_path)
    client = AEOFirecrawlClient(settings.firecrawl_api_key)
    stats = CacheStats()
    phases_skipped: list[str] = []

    credits_before = client.get_credits_remaining()

    # Phase 1 — SERP harvest
    log.info("Phase 1: SERP harvest")
    all_results = run_harvest_phase(
        settings.queries, client, conn, settings, stats, run_date, dry_run=dry_run
    )

    # Phase 2 — Citation graph
    log.info("Phase 2: Citation graph")
    graph, top_urls = run_citation_graph_phase(
        all_results, conn, settings.brand_domain, settings.competitors, run_date,
        top_n=settings.top_urls_for_analysis, dry_run=dry_run,
    )

    # Phase 3 — Source analysis
    log.info("Phase 3: Source analysis")
    run_source_analysis_phase(
        top_urls, client, conn, settings, stats, run_date, dry_run=dry_run
    )

    # Phase 4 — Answer engine
    log.info("Phase 4: Answer-engine citations")
    if not settings.perplexity_api_key:
        phases_skipped.append("ae_citations (no PERPLEXITY_API_KEY)")
    run_ae_phase(settings.queries, settings, conn, stats, run_date, dry_run=dry_run)

    # Phase 4A — AI engine probes
    if settings.probes:
        from providers.perplexity import PerplexityProvider
        from providers.claude import GeminiProvider
        from providers.openai_provider import OpenAIProvider
        from providers.google_ai_overview import GoogleAIOverviewProvider

        engine_map = {
            "perplexity": lambda key: PerplexityProvider(key, settings.brand_domain),
            "gemini": lambda key: GeminiProvider(key, settings.brand_domain),
            "openai": lambda key: OpenAIProvider(key, settings.brand_domain),
            "google": lambda key: GoogleAIOverviewProvider(key, settings.brand_domain),
        }
        active_providers = []
        for engine, factory in engine_map.items():
            key = settings.ai_engine_keys.get(engine)
            if key:
                active_providers.append(factory(key))
            else:
                phases_skipped.append(f"ai_probe/{engine} (no {engine.upper()}_API_KEY)")

        log.info("Phase 4A: AI engine probes")
        run_ai_engine_probe_phase(
            probes=settings.probes,
            providers=active_providers,
            conn=conn,
            company_name=settings.company_name,
            competitors=settings.competitors,
            cache_dir=settings.cache_dir,
            stats=stats,
            run_date=run_date,
            dry_run=dry_run,
        )

        # Phase 4B — Cross-reference
        log.info("Phase 4B: Cross-reference")
        run_cross_reference_phase(
            conn=conn,
            run_date=run_date,
            brand_domain=settings.brand_domain,
            company_name=settings.company_name,
            dry_run=dry_run,
        )
    else:
        phases_skipped.append("ai_probes (no probes.yaml or empty probes list)")

    # Phase 5 — Trends
    log.info("Phase 5: Trends")
    if skip_trends:
        phases_skipped.append("trends (--skip-trends flag)")
    run_trends_phase(
        settings.queries, settings, conn, stats, run_date,
        skip=skip_trends, dry_run=dry_run,
    )

    # Phase 6 — Outputs
    if not dry_run:
        log.info("Phase 6: Writing outputs")
        write_citation_graph_csv(conn, run_date, settings.out_dir)
        write_placement_targets_md(conn, run_date, settings.out_dir,
                                   company_name=settings.company_name,
                                   brand_domain=settings.brand_domain)
        write_query_opportunities_csv(conn, run_date, settings.out_dir,
                                      brand_domain=settings.brand_domain)
        write_pain_language_md(conn, run_date, settings.out_dir)
        write_weekly_diff_md(conn, run_date, settings.out_dir)
        if settings.probes:
            write_ai_visibility_md(
                conn, run_date, settings.out_dir,
                company_name=settings.company_name,
                brand_domain=settings.brand_domain,
            )
    else:
        phases_skipped.append("outputs (dry run)")

    credits_after = client.get_credits_remaining()

    # Phase 7 — Report
    print_run_summary(
        run_date=run_date,
        queries_run=len(settings.queries),
        stats=stats,
        credits_before=credits_before,
        credits_after=credits_after,
        phases_skipped=phases_skipped,
        citation_graph=graph,
        dry_run=dry_run,
    )
