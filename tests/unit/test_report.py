"""analytics/report.py — zero coverage before M7 (FR-M4-16/17/18).

aggregate()'s hit-rate denominator counts only turns that actually reached a memory lookup
(memory_hit / memory_miss_web_search, plus snippets-only degraded) — blocked/failed and
redis-down-degraded turns are excluded. render_report() escapes user-derived strings so a
logged query like "[red]boom[/red]" renders literally and never styles the table.
"""

import io

from rich.console import Console

from memagent.analytics.report import aggregate, render_report


def test_hit_rate_excludes_blocked_from_denominator():
    agg = aggregate(
        [
            {"route": "memory_hit"},
            {"route": "memory_hit"},
            {"route": "memory_miss_web_search"},
            {"route": "blocked"},
        ]
    )
    assert agg["total_turns"] == 4
    assert agg["hit_rate"] == 2 / 3  # 2 hits over 3 lookups; blocked not in the denominator


def test_snippets_only_counts_as_lookup_but_redis_down_does_not():
    snip = aggregate(
        [{"route": "memory_hit"}, {"route": "degraded_web", "degradation": "snippets_only"}]
    )
    assert snip["hit_rate"] == 0.5  # 1 hit / 2 lookups
    down = aggregate(
        [{"route": "memory_hit"}, {"route": "degraded_web", "degradation": "redis_down"}]
    )
    assert down["hit_rate"] == 1.0  # redis-down degraded turn never reached a lookup


def test_empty_log_has_zero_hit_rate():
    assert aggregate([])["hit_rate"] == 0.0


def test_render_report_escapes_rich_markup_in_query():
    agg = aggregate(
        [
            {
                "route": "memory_hit",
                "query": "[red]boom[/red]",
                "ts": "2026-01-01T00:00:00",
                "analytics": {"topic": "t"},
            }
        ]
    )
    buf = io.StringIO()
    render_report(agg, Console(file=buf, width=200, force_terminal=False))
    out = buf.getvalue()
    # Rendered literally. Without escape() rich would interpret the markup and drop the brackets.
    assert "[red]boom[/red]" in out
