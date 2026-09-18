from __future__ import annotations
from datetime import date
from reporter import print_run_summary
from cache import CacheStats

TODAY = date(2026, 8, 31)


def test_print_run_summary_dry_run(capsys):
    stats = CacheStats()
    print_run_summary(TODAY, 5, stats, None, None, [], [], dry_run=True)
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "2026-08-31" in out


def test_print_run_summary_normal(capsys):
    stats = CacheStats()
    stats.hit()
    stats.hit()
    stats.miss()
    print_run_summary(TODAY, 27, stats, 500, 443, [], [], dry_run=False)
    out = capsys.readouterr().out
    assert "DRY RUN" not in out
    assert "27" in out
    assert "67%" in out or "66%" in out  # 2/3 hit rate


def test_print_run_summary_with_phases_skipped(capsys):
    stats = CacheStats()
    print_run_summary(TODAY, 10, stats, None, None, ["trends"], [], dry_run=False)
    out = capsys.readouterr().out
    assert "trends" in out


def test_print_run_summary_no_citation_data(capsys):
    stats = CacheStats()
    print_run_summary(TODAY, 0, stats, None, None, [], [], dry_run=True)
    out = capsys.readouterr().out
    assert "no citation graph data" in out
