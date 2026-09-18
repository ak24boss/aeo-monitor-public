from __future__ import annotations
import logging
import signal
import time
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cache import CacheStats, load_cache, save_cache
from models import QueryConfig, TrendRow

if TYPE_CHECKING:
    import duckdb
    from config import Settings

log = logging.getLogger(__name__)

PROVIDER = "pytrends"


def _iso_week() -> str:
    cal = datetime.now().isocalendar()
    return f"{cal.year}-W{cal.week:02d}"


def _timeout_handler(signum, frame):
    raise TimeoutError("pytrends exceeded hard timeout")


def fetch_keyword_trends(
    keyword: str,
    cache_dir: Path,
    stats: CacheStats,
    run_date: date,
    timeframe: str = "today 12-m",
    timeout_seconds: int = 30,
) -> list[TrendRow]:
    cached = load_cache(PROVIDER, keyword, cache_dir)
    if cached is not None:
        stats.hit()
        return _deserialize_trend_rows(cached, run_date)

    stats.miss()
    try:
        from pytrends.request import TrendReq

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout_seconds)
        try:
            pt = TrendReq(hl="en-US", tz=360)
            pt.build_payload([keyword], timeframe=timeframe)
            iot = pt.interest_over_time()
            rising_df = pt.related_queries().get(keyword, {}).get("rising")
            signal.alarm(0)
        finally:
            signal.signal(signal.SIGALRM, old_handler)
            signal.alarm(0)

        if iot is None or iot.empty:
            log.warning("No trend data for keyword: %s", keyword)
            return []

        iot = iot.drop(columns=["isPartial"], errors="ignore")
        rising_list: list[str] = []
        if rising_df is not None and not rising_df.empty:
            rising_list = rising_df["query"].head(5).tolist()

        week = _iso_week()
        rows: list[TrendRow] = []
        for ts, row in iot.iterrows():
            interest = int(row.get(keyword, 0))
            rows.append(
                TrendRow(
                    run_date=run_date,
                    keyword=keyword,
                    week=ts.strftime("%Y-W%W"),
                    interest=interest,
                    rising_related=rising_list if not rows else [],
                )
            )

        raw = {
            "rows": [
                {"week": r.week, "interest": r.interest, "rising_related": r.rising_related}
                for r in rows
            ]
        }
        save_cache(PROVIDER, keyword, raw, cache_dir)
        log.info("Fetched trends for '%s': %d weeks", keyword, len(rows))
        return rows

    except TimeoutError:
        log.warning("Trends timeout for keyword: %s", keyword)
        return []
    except Exception as e:
        log.warning("Trends error for keyword '%s': %s", keyword, e)
        return []


def _deserialize_trend_rows(raw: dict, run_date: date) -> list[TrendRow]:
    rows: list[TrendRow] = []
    for item in raw.get("rows", []):
        rows.append(
            TrendRow(
                run_date=run_date,
                keyword=raw.get("keyword", ""),
                week=item["week"],
                interest=item["interest"],
                rising_related=item.get("rising_related", []),
            )
        )
    return rows


def run_trends_phase(
    queries: list[QueryConfig],
    settings: "Settings",
    conn: "duckdb.DuckDBPyConnection",
    stats: CacheStats,
    run_date: date,
    skip: bool = False,
    dry_run: bool = False,
) -> list[TrendRow]:
    from db import insert_trend_data

    if skip:
        log.info("Trends disabled via flag")
        return []

    # Use full query text as keyword (no truncation)
    seen: set[str] = set()
    keywords: list[str] = []
    for q in queries:
        kw = q.text
        if kw not in seen:
            seen.add(kw)
            keywords.append(kw)
    keywords = keywords[: settings.top_keywords_for_trends]

    log.info("Trends phase: %d keywords", len(keywords))
    all_rows: list[TrendRow] = []
    for i, kw in enumerate(keywords):
        if i > 0:
            time.sleep(1.0)
        if dry_run:
            continue
        rows = fetch_keyword_trends(kw, settings.cache_dir, stats, run_date)
        all_rows.extend(rows)

    if not dry_run:
        insert_trend_data(conn, all_rows)
        log.info("Inserted %d trend rows", len(all_rows))

    return all_rows
