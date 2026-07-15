# Data Model: Milestone 4 — Turn Log, Classifier, Analytics, Clients

**Date**: 2026-07-05 · Sources: source spec §6.3/§6.4/§6.7, PLAN §8.2/§8.3 (verbatim
schemas), repo `state.py`/`interfaces.py` as probed in research D1.

## 1. TurnRecord (JSONL line — `logs/turns.jsonl`)

One JSON object per completed turn, append-only. Built by
`build_turn_record(state, settings)`; written by `TurnLogger.log(record)`.

| Field | Type | Source (AgentState / computed) | Rules |
|---|---|---|---|
| `turn_id` | str | `state["turn_id"]` | uuid4 string (stamped by facade/REPL at turn start) |
| `ts` | str | computed at write | UTC ISO-8601, milliseconds precision |
| `session_id` | str | `state["session_id"]` | uuid4 per process/session |
| `query` | str | `state["query"]` | raw user query |
| `query_sha256` | str | computed | `sha256(query)[:16]` — 16 hex chars |
| `route` | str | `state["route"]` | CLOSED enum: `memory_hit \| memory_miss_web_search \| degraded_web \| blocked \| failed` (state.py `Route`) |
| `degradation` | str\|null | `state["degradation"]` | `"redis_down" \| "snippets_only" \| null` |
| `similarity_top` | float\|null | `state["top_similarity"]` | null when memory never consulted |
| `similarity_threshold` | float | `state.get("threshold", settings.similarity_threshold)` | default 0.7 |
| `web` | obj\|null | built iff route ∈ {`memory_miss_web_search`, `degraded_web`} | `{provider, results_returned, pages_fetched, chunks_ingested}`; `provider` = `state["search_provider"]` (`"tavily"`/`"ddgs"`/null); `pages_fetched` counts `fetched_docs[].ok` |
| `sources` | list | `state["sources"]` | `[{url, title, origin}]` (SourceRef) |
| `latency_ms` | obj | reduced `state["latency_ms"]` + log_turn's own `{classify, total}` | int ms per stage; `total` = wall-clock from `turn_started_at` to record write |
| `tokens` | obj | remapped from `state["tokens"]` | only roles `answer_llm`/`analytics_llm`, each `{model, input, output}` (remap from usage's `input_tokens`/`output_tokens`); `summary:{h}` keys in state are NOT itemised (research D8) |
| `guardrail` | obj | `{verdict: state.get("guard_verdict","allow"), events: state.get("guardrail_events",[])}` | reads `"allow"`/`[]` until M5 |
| `errors` | list | `[dict(e) for e in state["errors"]]` | StepError dicts |
| `analytics` | obj\|null | `state["analytics"].model_dump()` or null | null = "Unclassified" |

**Identity/uniqueness**: `turn_id` unique per turn (uuid4); ordering comes from `ts`, never
from ids. **Lifecycle**: records are immutable once written; no updates, no deletion (the
file is the single source of truth — Constitution P-IV).

## 2. QueryClassification (`analytics/classify.py` — hardened in place)

Existing M2 schema (verbatim PLAN §8.3) gains only the `_missing_` hooks:

- `topic: str` — free-form, 1–4 lowercase words
- `category: Category` — 9 values: `technology, science, health, finance_business,
  travel_geography, entertainment_sports, history_politics, lifestyle, other`;
  `_missing_ → other`
- `question_type: QuestionType` — 6 values: `factual, how_to, comparison, opinion,
  troubleshooting, other`; `_missing_ → other`
- `language: str` — ISO 639-1
- `confidence: float` — 0..1

**Transitions**: none (value object). Failure mode is absence: `classify()` →
`(None, {})` ⇒ record's `analytics: null`.

## 3. Usage account (`CompletionResult.usage` — already in `interfaces.py`)

`{"input_tokens": int, "output_tokens": int, "model": str}` — produced by BOTH client
surfaces (`complete`, `parse`); flows: answer nodes → `state.tokens["answer_llm"]`
(already live), `log_turn` → `state.tokens["analytics_llm"]`, ingest →
`state.tokens["summary:{h}"]` (state-only). Record remap renames
`input_tokens/output_tokens → input/output`.

## 4. Analytics aggregate (`aggregate(records) -> dict`)

```python
{
  "total_turns": int,
  "hit_rate": float,          # research D10 rule; 0.0 on empty denominator
  "top_topics": [(topic, count), ...],            # top 10
  "categories": {category: count},
  "question_types": {qtype: count},
  "languages": {lang: count},
  "avg_latency_ms_by_route": {route: mean_total_ms},
  "errors": int,              # turns with non-empty errors
  "unclassified": int,        # turns with analytics == null
  "recent": [{ts, route, similarity_top, topic, query}, ...],   # last 10
}
```

Pure function over parsed JSONL dicts; tolerant of missing keys (skips blanks, treats
absent `latency_ms.total` as excluded from the mean).

## 5. Sample turn log (`logs/turns.sample.jsonl`)

10 full-schema records; coverage matrix (research D10): all 5 routes ≥1, `analytics: null`
≥1, non-empty `errors` ≥1, ≥1 non-English `language`, ≥1 query containing rich markup,
fixed fictional timestamps in file order.

## 6. Chat history (REPL, in-memory only)

`list[{"role": "user"|"assistant", "content": str}]`; append 2 entries per turn, then
truncate to last `HISTORY_MAX_TURNS * 2 = 12`; passed into the turn state as
`history[-12:]`. Never persisted (per-turn stateless graph).

## 7. Stage-name map (latency instrumentation — research D9)

| Graph node | `latency_ms` key |
|---|---|
| `embed_query` | `embed` |
| `memory_search` | `vector_search` |
| `web_search` | `web_search` |
| `fetch_pages` | `fetch` |
| `ingest_content` | `ingest` (covers summarize — node granularity) |
| `answer_from_memory` / `answer_from_web` | `answer_llm` |
| `answer_failure` | `answer_failure` |
| `log_turn` | NOT wrapped; writes `classify` + `total` itself |

`timed()` is the SINGLE stage-latency owner (analyze I1): the pre-existing in-node latency
writes in `search.py`/`fetch.py`/`ingest.py` (keys `web_search`, `fetch_pages`,
`ingest_content`) are deleted when the wrapper is wired, and `timed()` merges — never
replaces — any `latency_ms` a node returns.
