# Phase 0 Research: Milestone 4 — LLM Clients Finalized, Turn Log, Classifier, Analytics CLI, REPL

**Date**: 2026-07-05 · **Feature**: `specs/004-m4-llms-logging-analytics/`
**Method**: source-spec §3/§4/§6/§10 consolidation + live code probes of the deliverable
repo (`~/Desktop/epam/memory-first-agent`, main @ `20145bd`) + runtime library-surface
verification (Constitution P-IX: every claim below that is time- or version-sensitive was
verified today, not assumed).

## D1 — Actual repo state vs the source spec's M2/M3 assumptions (code probe)

**Decision**: build M4 against the repo as it exists, not as the source spec's §3
summarises it. Probed 2026-07-05; deltas that change task scope:

| Source-spec assumption | Actual repo state (verified) | Consequence for M4 |
|---|---|---|
| `complete()` is "thin, text only"; M4 makes it return `CompletionResult` | `llm/clients.py:40-52` **already returns `CompletionResult(text, usage)`** with the exact 3-key usage dict | M4 does NOT re-implement `complete()`; it only reroutes the body through the new `_call` seam and parameterises `max_tokens`/`temperature` |
| `parse()` is M4's to add | A **basic `parse()` already exists** (`llm/clients.py:54-66`, `chat.completions.parse`, returns `(parsed, usage)`) | M4 adds the `_parse_call` seam + per-client `max_tokens`; contract already proven importable |
| T-M4-08b: "capture usage into `state.tokens['answer_llm']` in both answer nodes" | **Already done** — `nodes/answer.py:47` and `:116` both return `"tokens": {"answer_llm": result.usage}` | T-M4-08b becomes a verify-only assertion, not new code |
| Real node lands in `nodes/log_turn.py` | The stub lives in **`nodes/log.py`** (`make_log_turn`, returns `{}`); `graph.py:19` imports `from memagent.nodes.log import make_log_turn` | Replace the stub **in place in `nodes/log.py`** — creating `log_turn.py` would change a call site (Constitution: replacing a stub MUST NOT change its call sites) |
| M4 "creates" turnlog/report/timing modules | `analytics/turnlog.py`, `analytics/report.py`, `utils/timing.py` **exist as one-line docstring placeholders** (M1 scaffold) | Tasks fill existing files; no new module paths, no import churn |
| M4 creates the classification schema | `analytics/classify.py` ships the **schema-only** enums + `QueryClassification` (M2, verbatim PLAN §8.3) with a docstring explicitly reserving `_missing_` + `classify()` for M4 | M4 hardens in place (adds `_missing_` hooks + `classify()`); never re-declares |
| Facade stamps `turn_started_at` as an M4 change | `app.py:84` **already stamps** `turn_started_at`, plus `turn_id`/`session_id`/`search_provider`; `state.py:92-93` already declares the channels | `Agent.answer()` needs no state-shape change; only the REPL must mirror the same complete initial state |
| `TurnLogger` Protocol to be "fleshed out" | `interfaces.py:60-63` already fixes `log(self, record: dict) -> None` | Protocol signature unchanged; only its placeholder docstring updates |

**Rationale**: M3's analyze pass caught exactly this class of drift (I1, the `PageFetcher`
signature conflict) *after* planning; probing first removes it before tasks are cut.

**Alternatives considered**: trusting the source spec's §3 verbatim — rejected; two of its
"M4 will add X" items are already on main and would have produced duplicate/conflicting
tasks.

## D2 — OpenAI SDK surface for the finalized clients (live verification)

**Decision**: `openai 2.44.0` (installed). Use `chat.completions.parse` for structured
output and keep `max_tokens` + `temperature` kwargs, all routed through the two seam
methods.

Verified 2026-07-05 by `inspect.signature` against the installed SDK:

- `AsyncOpenAI().chat.completions.parse` **exists**; accepts `response_format`,
  `max_tokens`, **and** `max_completion_tokens`.
- `chat.completions.create` accepts `max_tokens`, `max_completion_tokens`, `temperature`.

**Rationale**: PLAN pins `max_tokens` (2048/256) and the M2 thin client already sends
`max_tokens` successfully against the dev endpoint. Both token-cap spellings being
SDK-accepted means a pinned-model rejection of the legacy spelling is a **one-line swap at
`_call`/`_parse_call`** — extend the FR-007 live probe to confirm `max_tokens` acceptance
alongside `temperature=0`, and record the outcome.

**Alternatives considered**: `responses.parse` (source spec's named alternative) — kept as
the documented fallback; not chosen because `chat.completions.parse` is symmetric with
`complete()` and verified present.

## D3 — Dev endpoint reality and the FR-007 probe path (live probes, 2026-07-05)

**Decision**: M4 development continues on GitHub Models with the **classic** PAT and the
`gpt-4.1-mini`/`-nano` dev aliases already in `.env`; the FR-007 `temperature=0` probe runs
against the pinned `gpt-5.4-mini` id on a **real OpenAI platform key** (Clarify session
2026-07-05, Option B), provided at implement time into the git-ignored `.env`.

Probe records:

| Probe | Result |
|---|---|
| `GET https://models.github.ai/catalog/models` with the user's NEW fine-grained PAT | HTTP 200, 37 models; **no `gpt-5.4*` ids** (closest: `openai/gpt-5`, `gpt-5-chat`, `gpt-5-mini`, `gpt-5-nano`) |
| Inference `POST /inference/chat/completions`, `openai/gpt-4.1-mini`, `temperature=0` with the fine-grained PAT | **HTTP 403 `no_access`** — the fine-grained PAT lacks the "Models: read" account permission |
| Same call, `openai/gpt-5-mini` | HTTP 403 `no_access` (same cause) |
| Classic PAT (in `.env` since M2) | Known-good for inference incl. `temperature=0` (M2 verification, reconfirmed by M3's live turns) |

**Rationale**: catalog listing ≠ inference access; the pinned id is simply not served by
the free endpoint, so no PAT of any kind can satisfy FR-007 — confirming the clarify
ruling. The fine-grained PAT is usable for dev **only after** the user re-issues it with
the "Models" account permission (Read); until then the classic PAT stays.

**Alternatives considered**: substituting `openai/gpt-5-mini` (GitHub Models) for the
probe — rejected: FR-007 names the pinned id and the DoD greps for it; a different model's
acceptance proves nothing about `gpt-5.4-mini` snapshots.

## D4 — structlog operational logging (live verification)

**Decision**: `structlog 26.1.0` (installed). `configure_logging(settings)` lives in
`app.py`, called once at CLI command start; processors =
`contextvars.merge_contextvars` → `add_log_level` → `TimeStamper(fmt="iso")` →
`dev.ConsoleRenderer()`, with `PrintLoggerFactory(file=sys.stderr)`. Per-turn
`bind_contextvars(turn_id=…)` / `clear_contextvars()` in `Agent.answer()` and the REPL
loop. All five attributes verified present on the installed version.

**Rationale**: keeps stdout pipe-clean (FR-021) with zero new dependencies; existing
module loggers (`web/search.py`, `nodes/*`) inherit the stderr factory unchanged.

**Alternatives considered**: stdlib-logging-only routing — rejected; structlog is already
the project's logger everywhere and the key=value ConsoleRenderer lines are the format M3's
transcripts already show.

## D5 — rich report rendering (live verification)

**Decision**: `rich 15.0.0` (installed; note: no module-level `__version__` in v15 — use
`importlib.metadata.version`). `rich.markup.escape` verified:
`escape("[red]x[/red]") == "\\[red]x\\[/red]"`. Every user-derived cell (query, topic,
source title/URL, language) passes through it (FR-018). `--json` short-circuits before any
`Console` construction so stdout carries only `json.dumps(aggregate(...))`.

**Alternatives considered**: none — rich is the locked dependency and the injection risk
is named in the source spec (§10).

## D6 — classifier retry & timeout (installed-lib check + source mandate)

**Decision**: `tenacity 9.1.4` (installed since M1). The classifier's local policy is
`@retry(stop=stop_after_attempt(2), reraise=True)` around the single parse call, wrapped
in `asyncio.wait_for(..., timeout=settings.classify_timeout_s)` (8 s), all inside
`classify()` which returns `(None, {})` on ANY failure. This is a deliberate, documented
carve-out from P-III's "retries live in `utils/reliability.py`" — the source spec mandates
the ×2 policy in M4 while `reliability.py` itself is M5 scope; M5 may relocate it as
`classify_retry` without touching `classify()`'s signature.

**Alternatives considered**: deferring all retry to M5 — rejected: the source's canonical
fact list requires "tenacity retry ×2" in M4 and the null-tolerant policy differs from
M5's raise-after-4 OpenAI policy anyway.

## D7 — REPL streaming (live verification)

**Decision**: `langgraph 1.2.7` (installed): `CompiledStateGraph.astream` exists and its
source references `stream_mode` — `astream(state, stream_mode="updates")` is the REPL
loop. Banner decision runs on the `memory_search` update (`top_similarity >= threshold`
inclusive → HIT); answers print on the first update from
{`answer_from_memory`, `answer_from_web`, `answer_failure`} carrying an `answer`; the
dormant `guard_input`/blocked branch ships now (Ruling F). History append+truncate to
`HISTORY_MAX_TURNS * 2 = 12` messages after each turn. The REPL constructs the same
complete initial state dict as `Agent.answer()` (all `AgentState` keys), sharing one
helper to prevent drift.

**Alternatives considered**: token streaming (`stream_mode="messages"`) — anti-churn
banned (Constitution P-VI); it also breaks "answer printed before log_turn".

## D8 — tokens channel semantics (code probe)

**Decision**: the turn record itemises exactly two roles: `answer_llm` (written by the
answer nodes — already live) and `analytics_llm` (written by the real `log_turn` from the
classifier's usage). Verified: `nodes/ingest.py:59` writes per-page summary usage under
**`summary:{h}` keys** in the same `tokens` channel; `build_turn_record` reads only the
two role keys, so summary usage is present in state but NOT itemised in the record —
matching the spec's adopted default. The `{**a, **b}` reducer means distinct keys never
collide; `log_turn` must still merge reduced dicts (never `{**state, **updates}`
shallow-clobber) when building the record, because its own updates haven't passed through
the reducer yet at write time.

## D9 — `timed()` stage wiring (node-name mapping)

**Decision**: wrap at `graph.py` `add_node` time; node → stage name:
`embed_query→embed`, `memory_search→vector_search`, `web_search→web_search`,
`fetch_pages→fetch`, `ingest_content→ingest`, `answer_from_memory→answer_llm`,
`answer_from_web→answer_llm`, `answer_failure→answer_failure`. `log_turn` is NOT wrapped —
it measures its own `classify` ms and computes wall-clock `total` from
`state["turn_started_at"]` internally, because the record is written inside the node
before any wrapper/reducer runs. Accepted delta from the PLAN §8.2 example: the example
shows separate `summarize` and `ingest` latencies, but summarisation happens inside the
`ingest_content` node (M3), so one `ingest` stage covers both — node-granularity
instrumentation, documented here.

**Alternatives considered**: instrumenting summarize separately inside ingest — rejected
as scope creep; the record's latency map is keyed by stage and nothing consumes a
`summarize` key.

**Amendment (analyze I1, 2026-07-05)**: a code probe found three M3 nodes already
self-measuring latency (`search.py:28` `web_search`, `fetch.py:29` `fetch_pages`,
`ingest.py:107` `ingest_content`) — double ownership plus key drift vs PLAN §8.2. Ruling:
`timed()` is the single stage-latency owner; those in-node writes are deleted when the
wrapper is wired (T022), and `timed()` merges any node-returned `latency_ms` instead of
replacing it. No existing test asserts the old keys (verified).

## D10 — aggregate & sample-log construction rules

**Decision** (restating the spec's adopted defaults as build rules):

- `hit_rate = hits / lookup_turns`; lookup turns = `memory_hit` + `memory_miss_web_search`
  + (`degraded_web` with `degradation == "snippets_only"`); denominator 0 → `0.0`.
- `aggregate()` is pure (Counter-based), returns the 10-key dict (total_turns, hit_rate,
  top_topics[10], categories, question_types, languages, avg_latency_ms_by_route — mean of
  `latency_ms.total` per route, errors, unclassified, recent[10]).
- `logs/turns.sample.jsonl`: 10 hand-authored full-schema records — ≥1 of each of the 5
  routes, ≥1 `"analytics": null`, ≥1 non-empty `errors`, varied
  category/question_type/language (≥1 non-`en`), one record whose `query` contains rich
  markup (feeds the FR-018 manual check). Timestamps use a fixed fictional day; `ts`
  ordering is the file order (uuid4 ids are unordered by design).
- Missing log file → friendly stdout guidance naming `memagent ask` and the sample file;
  exit code 0 (nothing is wrong).

## D11 — MODEL_CHOICES.md port

**Decision**: copy the planning-phase `/Users/mohamed.elsayed/Desktop/epam/MODEL_CHOICES.md`
to the deliverable repo root, then (a) re-verify each price against the official OpenAI
pricing page at implement time and refresh the verification date, (b) append the FR-007
probe outcome (model id, date, HTTP status, `max_tokens` acceptance), (c) keep the full
why-not table verbatim. The 100-turn estimate and per-turn costs are already consistent
with the §6.1 table (checked against the source spec today).
