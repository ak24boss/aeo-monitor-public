from __future__ import annotations
import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import duckdb

log = logging.getLogger(__name__)


def _mechanism(brand_domain: str) -> dict:
    return {
        "review_platform": "Submit a listing and request a review campaign",
        "reddit_forum": "Participate in thread or craft a targeted answer",
        "listicle": "Pitch author for inclusion / publish a competing comparison",
        "competitor_owned": f"Publish a direct comparison page on {brand_domain}",
        "vendor_neutral_media": "Pitch journalist or author for coverage",
        "other": "Contact publisher for inclusion",
    }


def write_citation_graph_csv(
    conn: "duckdb.DuckDBPyConnection", run_date: date, out_dir: Path
) -> Path:
    df = conn.execute(
        "SELECT * FROM citation_graph WHERE run_date = ? ORDER BY weighted_score DESC",
        [run_date],
    ).df()
    path = out_dir / "citation_graph.csv"
    df.to_csv(path, index=False)
    log.info("Wrote %s (%d rows)", path, len(df))
    return path


def write_placement_targets_md(
    conn: "duckdb.DuckDBPyConnection",
    run_date: date,
    out_dir: Path,
    company_name: str = "Your Company",
    brand_domain: str = "yourcompany.com",
) -> Path:
    df = conn.execute(
        """
        SELECT
            cg.url,
            cg.domain,
            cg.domain_type,
            cg.weighted_score,
            cg.queries_appearing_in,
            cg.top_position,
            sa.brand_mentioned,
            sa.competitors_mentioned,
            sa.page_type,
            sa.last_updated
        FROM citation_graph cg
        LEFT JOIN source_analysis sa
            ON cg.url = sa.url AND sa.run_date = cg.run_date
        WHERE cg.run_date = ?
          AND cg.domain_type != 'brand_owned'
          AND (sa.brand_mentioned IS NULL OR sa.brand_mentioned = FALSE)
        ORDER BY cg.weighted_score DESC
        LIMIT 30
        """,
        [run_date],
    ).df()

    mechanism = _mechanism(brand_domain)
    path = out_dir / "placement_targets.md"
    lines = [
        f"# Placement Targets — {run_date}\n",
        f"*{len(df)} high-value pages where {company_name} is absent. Ranked by citation weight.*\n",
        "",
    ]

    for rank, row in enumerate(df.itertuples(), 1):
        competitors_raw = getattr(row, "competitors_mentioned", None)
        competitors: list[str] = []
        if competitors_raw and isinstance(competitors_raw, str):
            try:
                parsed = json.loads(competitors_raw)
                competitors = [str(c) for c in parsed if c and str(c) not in ("nan", "None")]
            except Exception:
                competitors = [competitors_raw]
        competitors_str = ", ".join(competitors) if competitors else "none detected"

        action = mechanism.get(row.domain_type, mechanism["other"])
        lines.append(f"## {rank}. {row.url}")
        lines.append(f"- **Domain type**: {row.domain_type}")
        lines.append(f"- **Citation weight**: {row.weighted_score:.2f}")
        lines.append(f"- **Appears in**: {row.queries_appearing_in} queries (best position: #{row.top_position})")
        lines.append(f"- **Competitors mentioned**: {competitors_str}")
        lines.append(f"- **Page type**: {row.page_type or 'unknown'}")
        lu = row.last_updated
        if lu and str(lu) not in ("nan", "None", ""):
            lines.append(f"- **Last updated**: {lu}")
        lines.append(f"- **Action**: {action}")
        lines.append("")

    path.write_text("\n".join(lines))
    log.info("Wrote %s (%d targets)", path, len(df))
    return path


def write_query_opportunities_csv(
    conn: "duckdb.DuckDBPyConnection",
    run_date: date,
    out_dir: Path,
    brand_domain: str = "yourcompany.com",
) -> Path:
    brand_slug = brand_domain.split(".")[0]
    serp_df = conn.execute(
        f"""
        SELECT
            query,
            MIN(CASE WHEN domain LIKE '%{brand_slug}%' THEN position END) AS brand_position,
            COUNT(CASE WHEN domain LIKE '%{brand_slug}%' THEN 1 END) AS brand_result_count
        FROM serp_results
        WHERE run_date = ?
        GROUP BY query
        """,
        [run_date],
    ).df()

    trend_df = conn.execute(
        """
        SELECT
            keyword,
            AVG(interest) AS trend_avg,
            LAST(interest ORDER BY week) AS trend_last,
            FIRST(interest ORDER BY week) AS trend_first
        FROM trend_data
        WHERE run_date = ?
        GROUP BY keyword
        """,
        [run_date],
    ).df() if _table_has_rows(conn, "trend_data", run_date) else pd.DataFrame(columns=["keyword", "trend_avg", "trend_last", "trend_first"])

    merged = serp_df.copy()
    merged["brand_present"] = merged["brand_result_count"] > 0
    merged["brand_best_position"] = merged["brand_position"]

    if not trend_df.empty:
        merged = merged.merge(trend_df, left_on="query", right_on="keyword", how="left")
        merged["trend_direction"] = merged.apply(_trend_direction, axis=1)
        merged["trend_12m_avg"] = merged["trend_avg"].round(1)
    else:
        merged["trend_direction"] = None
        merged["trend_12m_avg"] = None

    output_cols = ["query", "brand_present", "brand_best_position", "trend_12m_avg", "trend_direction"]
    result = merged[[c for c in output_cols if c in merged.columns]].copy()
    result = result.sort_values(
        ["brand_present", "trend_direction"],
        ascending=[True, False],
        na_position="last",
    )

    path = out_dir / "query_opportunities.csv"
    result.to_csv(path, index=False)
    log.info("Wrote %s (%d rows)", path, len(result))
    return path


def write_pain_language_md(
    conn: "duckdb.DuckDBPyConnection", run_date: date, out_dir: Path
) -> Path:
    df = conn.execute(
        """
        SELECT url, pain_language, competitors_mentioned
        FROM source_analysis
        WHERE run_date = ? AND pain_language IS NOT NULL AND pain_language != ''
        """,
        [run_date],
    ).df()

    path = out_dir / "pain_language.md"
    lines = [
        f"# Pain Language — {run_date}\n",
        "*Verbatim complaint quotes harvested from forum sources. No paraphrase.*\n",
        "",
    ]

    if df.empty:
        lines.append("*No forum pain language captured in this run.*")
    else:
        for row in df.itertuples():
            lines.append(f"## Source: {row.url}")
            competitors_raw = getattr(row, "competitors_mentioned", None)
            if competitors_raw:
                try:
                    competitors = json.loads(competitors_raw)
                    if competitors:
                        lines.append(f"*Competitors mentioned: {', '.join(competitors)}*")
                except Exception:
                    pass
            lines.append("")
            lines.append(row.pain_language)
            lines.append("")

    path.write_text("\n".join(lines))
    log.info("Wrote %s (%d sources)", path, len(df))
    return path


def write_weekly_diff_md(
    conn: "duckdb.DuckDBPyConnection", run_date: date, out_dir: Path
) -> Path:
    from db import get_previous_run_date, get_citation_graph_for_date

    path = out_dir / "weekly_diff.md"
    prev_date = get_previous_run_date(conn, run_date)

    if prev_date is None:
        path.write_text(
            f"# Weekly Diff — {run_date}\n\nFirst run — no diff available.\n"
        )
        log.info("Wrote %s (first run)", path)
        return path

    current = {r.url: r for r in get_citation_graph_for_date(conn, run_date)}
    previous = {r.url: r for r in get_citation_graph_for_date(conn, prev_date)}

    new_entries = [url for url in current if url not in previous]
    dropped = [url for url in previous if url not in current]
    changed = [
        (url, current[url].weighted_score - previous[url].weighted_score)
        for url in current
        if url in previous and abs(current[url].weighted_score - previous[url].weighted_score) > 0.01
    ]
    changed.sort(key=lambda x: abs(x[1]), reverse=True)

    lines = [
        f"# Weekly Diff — {run_date} vs {prev_date}\n",
        f"- New entries: {len(new_entries)}",
        f"- Dropped: {len(dropped)}",
        f"- Score changes: {len(changed)}",
        "",
    ]

    if new_entries:
        lines.append("## New URLs")
        for url in new_entries[:10]:
            r = current[url]
            lines.append(f"- `{url}` ({r.domain_type}, score={r.weighted_score:.2f})")
        lines.append("")

    if dropped:
        lines.append("## Dropped URLs")
        for url in dropped[:10]:
            r = previous[url]
            lines.append(f"- `{url}` (was score={r.weighted_score:.2f})")
        lines.append("")

    if changed:
        lines.append("## Score Changes")
        for url, delta in changed[:10]:
            sign = "+" if delta > 0 else ""
            lines.append(f"- `{url}` {sign}{delta:.2f}")
        lines.append("")

    path.write_text("\n".join(lines))
    log.info("Wrote %s (prev run: %s)", path, prev_date)
    return path


def write_ai_visibility_md(
    conn: "duckdb.DuckDBPyConnection",
    run_date: date,
    out_dir: Path,
    company_name: str = "Your Company",
    brand_domain: str = "yourcompany.com",
) -> Path:
    path = out_dir / "ai_visibility.md"

    if not _table_has_rows(conn, "ae_probe_results", run_date):
        path.write_text(
            f"# AI Engine Visibility — {run_date}\n\n"
            "*No AI engine probe data for this run. "
            "Add probes.yaml and configure engine API keys to enable Phase 4A.*\n"
        )
        return path

    probe_rows = conn.execute(
        """
        SELECT engine, probe_id, probe_text, brand_mentioned,
               brand_context, competitors_mentioned, cited_urls
        FROM ae_probe_results
        WHERE run_date = ?
        ORDER BY engine, probe_id
        """,
        [run_date],
    ).fetchall()

    # Share-of-voice per engine
    engine_stats: dict[str, dict] = {}
    for engine, probe_id, probe_text, brand_mentioned, brand_ctx, comps_json, cited_json in probe_rows:
        if engine not in engine_stats:
            engine_stats[engine] = {"total": 0, "brand_mentioned": 0, "all_cited": []}
        engine_stats[engine]["total"] += 1
        if brand_mentioned:
            engine_stats[engine]["brand_mentioned"] += 1
        for url in json.loads(cited_json or "[]"):
            engine_stats[engine]["all_cited"].append(url)

    # Cross-reference rows for critical/high priority items
    xref_rows = conn.execute(
        """
        SELECT url, domain, serp_weighted_score, engines_citing_url,
               engine_citation_count, action_priority
        FROM cross_reference
        WHERE run_date = ?
          AND action_priority IN ('critical', 'high')
        ORDER BY
            CASE action_priority WHEN 'critical' THEN 0 ELSE 1 END,
            serp_weighted_score DESC
        LIMIT 20
        """,
        [run_date],
    ).fetchall() if _table_has_rows(conn, "cross_reference", run_date) else []

    lines = [
        f"# AI Engine Visibility — {run_date}\n",
        f"*Direct probe results: what AI engines say when users ask about {company_name}'s problem space.*\n",
        "",
        "## Share of Voice by Engine\n",
        f"| Engine | Probes | {company_name} Mentions | Share |",
        "|--------|--------|------------------------|-------|",
    ]
    for engine, stats in sorted(engine_stats.items()):
        total = stats["total"]
        mentioned = stats["brand_mentioned"]
        pct = (mentioned / total * 100) if total else 0
        lines.append(f"| {engine} | {total} | {mentioned} | {pct:.1f}% |")

    lines += ["", "## Critical Gaps — High-SERP Pages AI Engines Cite Without You\n"]
    if not xref_rows:
        lines.append("*No critical/high gaps detected — no cross-reference data or brand present on all cited pages.*\n")
    else:
        lines.append(f"*Pages AI engines actively cite where {company_name} is absent — ranked by SERP score.*\n")
        for url, domain, score, engines_json, cite_count, priority in xref_rows:
            engines = json.loads(engines_json or "[]") if isinstance(engines_json, str) else (engines_json or [])
            badge = "[CRITICAL]" if priority == "critical" else "[HIGH]"
            lines.append(f"### {badge} {url}")
            lines.append(f"- SERP weight: {score:.2f} | Cited by: {', '.join(engines) or 'none'}")
            lines.append("")

    lines += ["", "## Probe-by-Probe Breakdown\n"]
    for engine, probe_id, probe_text, brand_mentioned, brand_ctx, comps_json, cited_json in probe_rows:
        comps = json.loads(comps_json or "[]")
        cited = json.loads(cited_json or "[]")
        mention_icon = "✓" if brand_mentioned else "✗"
        lines.append(f"### [{engine}] {probe_text}")
        lines.append(f"- {company_name} mentioned: **{mention_icon}**" + (f" — \"{brand_ctx}\"" if brand_ctx else ""))
        if comps:
            lines.append(f"- Competitors: {', '.join(comps)}")
        if cited:
            lines.append(f"- Cited ({len(cited)}): {', '.join(cited[:5])}" + (" ..." if len(cited) > 5 else ""))
        lines.append("")

    path.write_text("\n".join(lines))
    log.info("Wrote %s", path)
    return path


def _trend_direction(row) -> Optional[str]:
    first = row.get("trend_first")
    last = row.get("trend_last")
    if pd.isna(first) or pd.isna(last) or first == 0:
        return None
    pct = (last - first) / first
    if pct > 0.1:
        return "rising"
    if pct < -0.1:
        return "falling"
    return "flat"


def _table_has_rows(conn, table: str, run_date: date) -> bool:
    count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE run_date = ?", [run_date]).fetchone()[0]
    return count > 0
