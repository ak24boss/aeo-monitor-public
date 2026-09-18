from __future__ import annotations
from datetime import date
from typing import Optional

from cache import CacheStats
from models import CitationRow


def print_run_summary(
    run_date: date,
    queries_run: int,
    stats: CacheStats,
    credits_before: Optional[int],
    credits_after: Optional[int],
    phases_skipped: list[str],
    citation_graph: list[CitationRow],
    dry_run: bool = False,
) -> None:
    label = " [DRY RUN]" if dry_run else ""
    print(f"\n{'='*60}")
    print(f"AEO Monitor — {run_date}{label}")
    print(f"{'='*60}")
    print(f"Queries run:      {queries_run}")
    print(f"Cache hit rate:   {stats.rate:.0%} ({stats.hits}/{stats.total})")

    if credits_before is not None and credits_after is not None:
        used = credits_before - credits_after
        print(f"Credits used:     {used} (remaining: {credits_after})")
    elif credits_after is not None:
        print(f"Credits remaining: {credits_after}")
    else:
        print("Credits used:     N/A")

    if phases_skipped:
        print(f"Phases skipped:   {', '.join(phases_skipped)}")
    else:
        print("Phases skipped:   none")

    print()
    top5 = [r for r in citation_graph if r.domain_type != "brand_owned"][:5]
    if top5:
        print("Top 5 placement targets:")
        for i, r in enumerate(top5, 1):
            print(f"  {i}. {r.url[:70]}")
            print(f"     score={r.weighted_score:.2f} | {r.domain_type} | {r.queries_appearing_in} queries")
    else:
        print("(no citation graph data — dry run or no results)")

    print(f"{'='*60}\n")
