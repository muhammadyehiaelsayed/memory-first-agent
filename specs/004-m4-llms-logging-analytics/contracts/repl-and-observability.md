# Contract: Chat REPL + observability (`cli.py`, `app.py`, `utils/timing.py`, `graph.py`) — FR-020…022

**Consumers**: the end user (chat), M5 (blocked branch goes live; timed() reusable), M6
(demo capture drives the REPL).

## timed() (`utils/timing.py` — fills the M1 placeholder file)

```python
def timed(stage: str, fn):
    async def wrapped(state):
        t0 = time.perf_counter()
        out = await fn(state) or {}
        dt = int((time.perf_counter() - t0) * 1000)
        # MERGE with any latency the node itself returned — never replace the dict
        return {**out, "latency_ms": {**out.get("latency_ms", {}), stage: dt}}
    return wrapped
```

- Preserves every key `fn` returned — including node-returned `latency_ms` entries, which
  are merged, never clobbered (analyze finding I1).
- **Single owner (P-III)**: `timed()` is THE stage-latency owner. The three M3 nodes that
  self-measure today — `nodes/search.py:28` (`web_search`), `nodes/fetch.py:29`
  (`fetch_pages`), `nodes/ingest.py:107` (`ingest_content`) — have those latency writes
  (and their `started = time.perf_counter()` bookkeeping) DELETED when `timed()` is wired,
  eliminating double measurement and the key drift vs PLAN §8.2 names (`fetch`/`ingest`).
  Verified 2026-07-05: no existing test asserts those keys.
- Wired in `graph.py` at `add_node` time using the data-model §7 stage map; `log_turn`
  is NOT wrapped (it writes the record before wrappers/reducers run). Node NAMES are
  unchanged → the mermaid diagram and all router mappings are untouched.

## Chat REPL (`cli.py chat` — replaces the M1 stub)

Per-turn contract (source §6.8, adjusted to the probed repo state — research D1):

1. Build the turn state via a SHARED helper with `Agent.answer()` (one function producing
   the complete `AgentState` initial dict — every key, as `app.py:59-86` does today) with:
   fresh uuid4 `turn_id`, the session's `session_id`, `history=history[-12:]`,
   `turn_started_at=time.perf_counter()`.
2. `async for chunk in agent.graph.astream(state, stream_mode="updates")` — for each
   `(node, update)`:
   - `guard_input` + `route=="blocked"` → print the canned refusal if present (dormant
     until M5; ships now).
   - `memory_search` → banner: `top_similarity is not None and sim >= threshold` →
     `[MEMORY HIT sim={sim:.2f}]` else the byte-identical
     `[MEMORY MISS → searching the web]` (same literal the `ask` command already prints —
     single source: reuse/share the constant, do not retype it).
   - node ∈ {`answer_from_memory`, `answer_from_web`, `answer_failure`} with an `answer`
     → print it immediately, then sources in the `ask` format `(origin) title <url>`.
3. After the turn: append user+assistant messages; truncate history to
   `settings.history_max_turns * 2` (12) messages.
4. Exit: `exit`/`quit`/EOF (Ctrl-D) leave cleanly; empty input re-prompts.
5. Startup: same `OPENAI_API_KEY` guard and Redis-down handling as `ask` (reuse
   `_exit_redis_down` / `_redis_down_in_chain` — the M3 manual-test fix applies to the
   REPL too; a mid-session Redis outage must print the one-line error, not a traceback
   wall).

## Banner boundary (FR-020 accept)

`sim=0.70`, threshold 0.70 → HIT banner; `sim=0.6999` → MISS banner. The decision reads
the SAME inclusive comparison the router uses (`>=`) — unit-testable as a pure function on
a `memory_search` update dict.

## structlog configuration (`configure_logging(settings)` in `app.py`)

```python
logging.basicConfig(stream=sys.stderr, level=getattr(logging, settings.log_level.upper(), logging.INFO))
structlog.configure(
    processors=[structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer()],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)
```

- Called once at the start of each CLI command that runs turns (`ask`, `chat`).
- `Agent.answer()` (and the REPL loop) binds
  `structlog.contextvars.bind_contextvars(turn_id=…)` at turn start and
  `clear_contextvars()` in a finally block — every operational line of a turn carries
  `turn_id=` (FR-021).
- stdout budget: banners + answer + sources ONLY. All existing module loggers
  (web/search, nodes) inherit the stderr factory — no per-module changes.

## Tokens plumbing (FR-022)

Already-live pieces (verified — research D1): answer nodes return
`{"tokens": {"answer_llm": result.usage}}`; facade stamps `turn_started_at`. M4 adds:
`log_turn` contributes `{"analytics_llm": usage}` + `classify`/`total` latencies; `timed()`
fills the per-stage keys. Accept: a run's `latency_ms` has one key per executed stage plus
`total`; `tokens.answer_llm` matches the answer call's usage.

## Acceptance mapping

| FR | Check |
|---|---|
| FR-020 | manual: miss→hit banners across identical turns; unit: boundary table (0.70/0.6999); unit: history cap after 7 turns → 12 messages |
| FR-021 | manual: `uv run memagent ask "x" > out.txt` → out.txt log-free; stderr lines carry `turn_id=` |
| FR-022 | unit: `timed("embed", fn)` returns original keys + int `latency_ms.embed`; record-level checks live in test_turnlog (FR-012) |
