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


def _is_lookup(record: dict) -> bool:
    route = record.get("route")
    if route in _LOOKUP_ROUTES:
        return True
    return route == "degraded_web" and record.get("degradation") == "snippets_only"


def aggregate(records: Iterable[dict]) -> dict:
    recs = list(records)
    topics: Counter = Counter()
    categories: Counter = Counter()
    question_types: Counter = Counter()
    languages: Counter = Counter()
    totals_by_route: dict[str, list[int]] = defaultdict(list)
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
