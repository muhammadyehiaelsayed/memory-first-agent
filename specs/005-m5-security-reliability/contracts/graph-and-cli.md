# Contract — Graph Rewire, CLI Surface, Graph Render Script

Implements FR-M5-07 and clarifications Q2/Q3/Q4. No new route enum values.

## `graph.py` — add guard, move entry (Ruling F)

```python
from memagent.nodes.guard import make_guard_input
from memagent.routers import route_after_guard   # already exists, verbatim

sg.add_node("guard_input", timed("guard", make_guard_input(resources)))
sg.set_entry_point("guard_input")                 # replaces set_entry_point("embed_query")
sg.add_conditional_edges("guard_input", route_after_guard,
                         {"log_turn": "log_turn", "embed_query": "embed_query"})
```

Everything downstream of `embed_query` is unchanged; the temporary
`set_entry_point("embed_query")` comment is removed (last M-seam closed).

**Contract tests** (`test_guardrails.py`, wiring group):
- `build_graph(resources).get_graph().draw_mermaid()` contains `"__start__ --> guard_input"`
  and `"guard_input -.-> log_turn"` (D2 literals — dotted, unlabeled).
- `route_after_guard({"guard_verdict": "block"}) == "log_turn"`;
  `route_after_guard({"guard_verdict": "allow"}) == "embed_query"`.
- blocked-turn integration (fake searcher + store recording call_count): agent answering
  the T1 query → `route == "blocked"`, `searcher.search` call_count 0, `store` call_count
  0, exactly one TurnRecord with `route == "blocked"`.

## `app.py` — `TurnResult.degradation`

`TurnResult` NamedTuple gains `degradation: str | None = None`; `Agent.answer` sets it
from `final.get("degradation")`. Additive, default-safe (existing unpackers unaffected).

## `cli.py` — banners, exit codes (Q2/Q3/Q4)

New module constants:
```python
BLOCKED_BANNER = "[BLOCKED by input guard]"
MEMORY_OFFLINE_BANNER = "[MEMORY OFFLINE → searching the web (not cached)]"
```

### `ask` result rendering (replaces the current hit-else-miss block)

Conditions are checked **top-down; first match wins** (order is load-bearing — see the
`failed`-before-`redis_down` note):

| `result.route` / condition | stdout | exit |
|---|---|---|
| `blocked` | `BLOCKED_BANNER` then `answer`; **no sources** | 0 |
| `failed` | **no banner**; `answer` (apology) | **1** |
| `memory_hit` | `_hit_banner(similarity)` then answer + sources | 0 |
| `result.degradation == "redis_down"` | `MEMORY_OFFLINE_BANNER` then answer + sources | 0 |
| otherwise (miss / snippets_only degraded) | `MISS_BANNER` then answer + sources | 0 |

`failed → exit 1` is new (FR-M5-27 non-zero exit; today `ask` always exits 0 and would
print the miss banner on a failed turn). Flagged turns render exactly like their route
(no extra output — Q4). Exit via `raise typer.Exit(code=1)` after printing.

**Why `failed` is checked before the `degradation == "redis_down"` row**: `degradation`
has no reducer (last-write-wins) and `memory_search` sets it to `"redis_down"` on the
web-only path. If the conversation LLM then also fails, `answer_from_web` returns
`route="failed"` **without clearing** the lingering `degradation="redis_down"`. A
route-agnostic redis_down check would then print `MEMORY_OFFLINE_BANNER` + exit 0 for a
turn that actually failed — violating FR-027's non-zero-exit contract. Ordering `failed`
first (equivalently: gate the redis_down row on `route != "failed"`) makes a failed turn
always yield the apology + exit 1 regardless of a stale degradation label. `chat`'s
`memory_search` banner branch is likewise reached only on non-failed turns (the graph
still routes redis-down→web, but a subsequent answer-node failure sets `route="failed"`
and the REPL prints the apology, not the offline banner).

### `chat` streaming branches (add to the existing `astream` loop)

- `guard_input` update with `route == "blocked"` and an `answer` → print
  `BLOCKED_BANNER` then the refusal (the branch scaffold already exists for M5).
- `memory_search` update: if `update.get("degradation") == "redis_down"` → print
  `MEMORY_OFFLINE_BANNER`; elif `sim >= threshold` → hit banner; else → `MISS_BANNER`.
- failed turns print the apology (already handled by the ANSWER_NODES branch) and never
  exit the REPL.
- mid-turn redis failure no longer trips the outer `_REDIS_DOWN`/`RedisSearchError` catch
  (the graph degrades it to `degraded_web`); the outer catch remains a startup safety net.

**Contract tests**: covered as CLI-level assertions in `test_reliability.py` /
`test_guardrails.py` where cheap (banner-selection is pure given a `TurnResult`); the full
`docker stop` behavior is the manual DoD demo + M6 e2e.

## `scripts/render_graph.py` (new, keyless)

Prints `build_graph(resources).get_graph().draw_mermaid()` for the DoD grep and README.
Builds resources without keys or network:
```python
settings = Settings(_env_file=None)          # pinned defaults, no .env
# node factories only close over resources; compilation touches no client/key
resources = AgentResources(settings=settings, memory=None, embedder=None, chat_llm=None,
                           analytics_llm=None, searcher=None, fetcher=None, turn_logger=None)
print(build_graph(resources).get_graph().draw_mermaid())
```
DoD command: `uv run python scripts/render_graph.py | grep -E "guard_input"` shows
`__start__ --> guard_input` and `guard_input -.-> log_turn`.
