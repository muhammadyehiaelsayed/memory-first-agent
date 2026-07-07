"""Analytics over the turn log: pure aggregate() + rich render_report() (M4).

Reads TurnRecord dicts only (Constitution P-IV). Every user-derived string (query, topic,
source title/url, language) passes through rich.markup.escape() before rendering — a query
like "[red]boom[/red]" must render literally, never style the table (PLAN section 8.4).
"""

from collections import Counter, defaultdict
from collections.abc import Iterable

from rich.console import Console
from rich.markup import escape
from rich.table import Table

# Hit-rate denominator: turns where memory was actually consulted (specs/004 research D10).
# blocked/failed and redis_down-degraded turns never reached a memory lookup.
_LOOKUP_ROUTES = ("memory_hit", "memory_miss_web_search")

# Documented per-1M-token prices (USD), verified against the official OpenAI pricing page
# (MODEL_CHOICES.md / docs/verification-2026-07-06.md): (input, output). Models absent here
# are still token-counted; their cost simply shows as 0 rather than guessing an unknown price.
_MODEL_PRICES_PER_1M = {
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "text-embedding-3-small": (0.02, 0.0),
}


def _is_lookup(record: dict) -> bool:
    route = record.get("route")
    if route in _LOOKUP_ROUTES:
        return True
    return route == "degraded_web" and record.get("degradation") == "snippets_only"


def aggregate(records: Iterable[dict]) -> dict:
    # Loads the whole turn log into a list (caller reads every line): fine under the project's
    # bounded single-user local-CLI assumption; a long-lived multi-user deployment would want a
    # streaming pass instead (specs YAGNI — not built speculatively).
    recs = list(records)

    def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
        in_price, out_price = _MODEL_PRICES_PER_1M.get(model, (0.0, 0.0))
        return (input_tokens * in_price + output_tokens * out_price) / 1_000_000

    topics: Counter = Counter()
    categories: Counter = Counter()
    question_types: Counter = Counter()
    languages: Counter = Counter()
    totals_by_route: dict[str, list[int]] = defaultdict(list)
    tokens_in: Counter = Counter()  # input tokens summed per model
    tokens_out: Counter = Counter()  # output tokens summed per model
    hits = errors = unclassified = lookups = 0

    for r in recs:
        if _is_lookup(r):
            lookups += 1
        if r.get("route") == "memory_hit":
            hits += 1
        if r.get("errors"):
            errors += 1
        analytics = r.get("analytics")
        if analytics:
            topics[analytics.get("topic", "?")] += 1
            categories[analytics.get("category", "other")] += 1
            question_types[analytics.get("question_type", "other")] += 1
            languages[analytics.get("language", "?")] += 1
        else:
            unclassified += 1
        total_ms = (r.get("latency_ms") or {}).get("total")
        if isinstance(total_ms, int) and r.get("route"):
            totals_by_route[r["route"]].append(total_ms)
        # answer_llm / analytics_llm / summary_llm buckets all share {model, input, output}.
        for usage in (r.get("tokens") or {}).values():
            if not usage:
                continue
            tokens_in[usage.get("model", "?")] += usage.get("input", 0)
            tokens_out[usage.get("model", "?")] += usage.get("output", 0)

    by_model = {
        model: {
            "input": tokens_in[model],
            "output": tokens_out[model],
            "cost_usd": round(_cost_usd(model, tokens_in[model], tokens_out[model]), 6),
        }
        for model in sorted(set(tokens_in) | set(tokens_out))
    }
    tokens_summary = {
        "by_model": by_model,
        "total_input": sum(tokens_in.values()),
        "total_output": sum(tokens_out.values()),
        "total_cost_usd": round(sum(m["cost_usd"] for m in by_model.values()), 6),
    }

    return {
        "total_turns": len(recs),
        "hit_rate": (hits / lookups) if lookups else 0.0,
        "top_topics": topics.most_common(10),
        "categories": dict(categories),
        "question_types": dict(question_types),
        "languages": dict(languages),
        "avg_latency_ms_by_route": {
            route: round(sum(v) / len(v)) for route, v in totals_by_route.items()
        },
        "errors": errors,
        "unclassified": unclassified,
        "tokens": tokens_summary,
        "recent": [
            {
                "ts": r.get("ts"),
                "route": r.get("route"),
                "similarity_top": r.get("similarity_top"),
                "topic": (r.get("analytics") or {}).get("topic"),
                "query": r.get("query"),
            }
            for r in recs[-10:]
        ],
    }


def _counter_table(title: str, counts: dict, key_header: str) -> Table:
    table = Table(title=title)
    table.add_column(key_header)
    table.add_column("turns", justify="right")
    for key, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        table.add_row(escape(str(key)), str(count))
    return table


def render_report(agg: dict, console: Console) -> None:
    headline = Table(title="Turn log summary")
    for column in ("total turns", "hit-rate %", "errors", "unclassified"):
        headline.add_column(column, justify="right")
    headline.add_row(
        str(agg["total_turns"]),
        f"{agg['hit_rate'] * 100:.1f}",
        str(agg["errors"]),
        str(agg["unclassified"]),
    )
    console.print(headline)

    topics = Table(title="Top topics")
    topics.add_column("topic")
    topics.add_column("turns", justify="right")
    for topic, count in agg["top_topics"]:
        topics.add_row(escape(str(topic)), str(count))
    console.print(topics)

    console.print(_counter_table("Categories", agg["categories"], "category"))
    console.print(_counter_table("Question types", agg["question_types"], "question type"))
    console.print(_counter_table("Languages", agg["languages"], "language"))

    latency = Table(title="Avg latency per route (ms)")
    latency.add_column("route")
    latency.add_column("avg total ms", justify="right")
    for route, ms in sorted(agg["avg_latency_ms_by_route"].items()):
        latency.add_row(route, str(ms))
    console.print(latency)

    # Token spend + cost turns the already-logged per-turn usage into the cost story the
    # memory-first pitch depends on. Absent when no turn recorded any token usage.
    tokens = agg.get("tokens") or {}
    if tokens.get("by_model"):
        usage = Table(title="Token usage & cost (USD)")
        for column in ("model", "input tok", "output tok", "cost USD"):
            usage.add_column(column, justify="right" if column != "model" else "left")
        for model, u in sorted(tokens["by_model"].items()):
            usage.add_row(
                escape(str(model)), str(u["input"]), str(u["output"]), f"{u['cost_usd']:.4f}"
            )
        usage.add_row(
            "TOTAL",
            str(tokens["total_input"]),
            str(tokens["total_output"]),
            f"{tokens['total_cost_usd']:.4f}",
        )
        console.print(usage)

    recent = Table(title="Recent turns")
    for column in ("ts", "route", "sim", "topic", "query"):
        recent.add_column(column)
    for r in agg["recent"]:
        sim = f"{r['similarity_top']:.2f}" if isinstance(r.get("similarity_top"), float) else "-"
        recent.add_row(
            escape(str(r.get("ts") or "-")),
            str(r.get("route") or "-"),
            sim,
            escape(str(r.get("topic") or "Unclassified")),
            escape(str(r.get("query") or "")),
        )
    console.print(recent)
