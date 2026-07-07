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


def _token_records():
    # Two web-miss turns, each carrying answer_llm (mini) + summary_llm (nano) usage.
    return [
        {
            "route": "memory_miss_web_search",
            "tokens": {
                "answer_llm": {"model": "gpt-5.4-mini", "input": 1000, "output": 200},
                "summary_llm": {"model": "gpt-5.4-nano", "input": 500, "output": 100},
            },
        },
        {
            "route": "memory_miss_web_search",
            "tokens": {
                "answer_llm": {"model": "gpt-5.4-mini", "input": 1000, "output": 200},
                "summary_llm": {"model": "gpt-5.4-nano", "input": 500, "output": 100},
            },
        },
    ]


def test_aggregate_sums_tokens_and_costs_by_model():
    agg = aggregate(_token_records())
    tok = agg["tokens"]
    assert tok["by_model"]["gpt-5.4-mini"]["input"] == 2000  # summed across both turns
    assert tok["by_model"]["gpt-5.4-mini"]["output"] == 400
    assert tok["by_model"]["gpt-5.4-nano"]["input"] == 1000
    assert tok["total_input"] == 3000
    assert tok["total_output"] == 600  # mini 400 + nano 200 across both turns
    # documented prices: mini $0.75 in / $4.50 out, nano $0.20 in / $1.25 out (per 1M)
    mini_cost = (2000 * 0.75 + 400 * 4.50) / 1_000_000
    nano_cost = (1000 * 0.20 + 200 * 1.25) / 1_000_000
    assert tok["by_model"]["gpt-5.4-mini"]["cost_usd"] == round(mini_cost, 6)
    assert tok["total_cost_usd"] == round(mini_cost + nano_cost, 6)


def test_aggregate_tokens_empty_when_no_usage_logged():
    agg = aggregate([{"route": "memory_hit"}])
    assert agg["tokens"]["by_model"] == {}
    assert agg["tokens"]["total_cost_usd"] == 0.0


def test_render_report_shows_token_usage_and_cost_section():
    buf = io.StringIO()
    render_report(aggregate(_token_records()), Console(file=buf, width=200, force_terminal=False))
    out = buf.getvalue()
    assert "Token usage & cost" in out
    assert "gpt-5.4-mini" in out and "gpt-5.4-nano" in out
    assert "TOTAL" in out


def test_render_report_omits_token_section_when_no_usage():
    buf = io.StringIO()
    render_report(aggregate([{"route": "memory_hit"}]), Console(file=buf, width=200))
    assert "Token usage & cost" not in buf.getvalue()


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
