# Phase 0 Research — M5 Guardrails & Reliability

**Date**: 2026-07-05 | **Feature**: 005-m5-security-reliability
**Method**: live repo probe of `memory-first-agent` (main `5bc6bfc`, 50 tests green) +
live library-surface verification inside the project venv (Constitution P-IX), before any
design was fixed. The source spec `specs/milestone-5-security-reliability.md` was written
against the plan; the probe found several of its "M5 adds X" statements already shipped
by M2–M4 — each is recorded below so `/speckit-tasks` does not cut duplicate work.

## R0 — Repo-state probe: source-spec deltas (main `5bc6bfc`)

| # | Source-spec assumption | Actual repo state | Consequence for M5 |
|---|---|---|---|
| 1 | `security/patterns.py`, `security/guardrails.py`, `utils/errors.py`, `utils/reliability.py` are **new** files | All four exist as docstring-only placeholders (M1 scaffold) | Tasks say "fill", not "create"; imports already resolve |
| 2 | §6.7 "M5 adds the try/except → degrade logic" to nodes | `embed_query`, `web_search`, `fetch_pages`, both answer nodes, and `ingest_content` **already** catch broadly and record `errors[]` (M2–M4; the answer-node catches landed in the M4 manual-test fix). Only `memory_search` has **no catch** | Node work shrinks to: `memory_search` typed catch + `redis_down` labeling; `answer_from_web` route/degradation mapping; T4 image strip. Existing broad catches stay — typed errors flow through them |
| 3 | FR-M5-14: persist `sanitizer_flags` + `content_sha256` | **Pre-satisfied**: `memory/store.py:_write` already persists both; sha256 is computed over the stored (sanitized) text at the store boundary; `knn` already returns `stored_at` + parsed `sanitizer_flags` | T-M5-08 collapses to test-only; no store code change |
| 4 | FR-M5-22 skip rules (non-HTML, oversize, per-URL non-fatal, 20 s deadline) | **Pre-satisfied** in `web/fetch.py` (streamed cap, content-type gate, `asyncio.wait_for(page_deadline_s)`, gather-and-skip) | Fetch delta = retry policy on retryable failures only + `PageFetchError` typing |
| 5 | Tavily timeout "10 s (5 s connect)" | `TavilySearcher`'s `httpx.AsyncClient` has **no explicit timeout** (httpx default = 5 s everything) | M5 sets `httpx.Timeout(read_timeout_s, connect=connect_timeout_s)` on the Tavily client |
| 6 | DoD greps `START --> guard_input` and `guard_input -->|block| log_turn`; command `scripts/render_graph.py` | Live `draw_mermaid()` renders `__start__ --> guard_input;` and **unlabeled dotted** conditional edges `guard_input -.-> log_turn;`. `scripts/render_graph.py` **does not exist** | Assertions adapted to the real literals (D2); M5 adds the small keyless `scripts/render_graph.py` |
| 7 | `route_after_guard` etc. authored in M2 | Confirmed verbatim in `routers.py`; `route_after_embed` already routes falsy `query_vector` → `answer_failure` | FR-M5-27's embed half is behaviorally pre-wired; M5 only makes the raised error typed |
| 8 | Analytics retry: "M5 relies on null-tolerance" | `analytics/classify.py` owns `@retry(stop_after_attempt(2))` + `wait_for(8s)`, and its docstring declares this policy "distinct from M5's"; M4 tests assert **exactly 2 calls** | M5's OpenAI policy must NOT wrap the analytics client (D3) or those M4 tests break with hidden 2×4 retry multiplication |
| 9 | `wrap_context(sources)` consumes `MemoryHit \| FetchedDoc` | Real call sites pass `MemoryHit` dicts (memory path) and node-built `{url,title,text}` dicts (web path — `answer_from_web` constructs them); web sources carry **no sanitizer flags in state** (ingest passes flags to `store()` only) | D10: ingest enriches its output docs with `sanitizer_flags`; `answer_from_web` copies them into its source dicts; `wrap_context` maps by key presence with `[]`/now-time defaults |
| 10 | CLI behavior on blocked/degraded/failed | `ask` prints hit banner for `memory_hit` else the MISS banner, always exits 0; `chat` already has a dormant `guard_input` blocked-answer branch and a sim-threshold banner branch | D11: `ask`/`chat` gain blocked + memory-offline banner branches; `ask` exits 1 on `failed` (today it doesn't); `TurnResult` gains `degradation` |
| 11 | — | `TurnResult` (app.py) has no `degradation` field, so `ask` cannot know a redis-down turn | Add `degradation: str \| None = None` to the NamedTuple (additive, default-safe) |
| 12 | Redis client construction site | `app.py:build_resources` calls `aioredis.from_url(settings.redis_url)` bare; `cli._wipe` builds its own bare client; redisvl wraps connection failures in `RedisSearchError` with the redis error in the `__cause__` chain (M3 finding; cause-walk helper lives in `cli.py`) | D7: one `make_redis_client(settings)` helper; typed translation in store methods must also walk `RedisSearchError` causes — move the chain-walk helper to `utils/errors.py` and reuse it from `cli.py` |
| 13 | Reliability/degradation tests: "no dedicated §12 file allocated" | M5's constitution-fixed owned files are 4 (sanitizer, guardrails, search-retry, fetch-retry) | D13: allocate one new M5-owned file `tests/unit/test_reliability.py` for the OpenAI-policy, redis-retry, and degradation-matrix scenarios (no other milestone owns it; ownership table extended, not violated) |

## Live library verifications (P-IX, run 2026-07-05 in-project)

| Check | Method | Result |
|---|---|---|
| Mermaid literals | compiled a 3-node graph with a conditional guard edge, printed `draw_mermaid()` | `__start__ --> guard_input;` + `guard_input -.-> log_turn;` (dotted, **no labels**) — DoD greps use these |
| openai 2.44.0 exceptions | import probe | `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `InternalServerError`, `APIStatusError` (+`BadRequestError`, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `UnprocessableEntityError`) all present; `APIStatusError.status_code` available for fail-fast checks |
| tenacity 9.1.4 | import + signature probe (no `__version__` attr — use `importlib.metadata`) | `AsyncRetrying`, `retry`, `stop_after_attempt`, `wait_random_exponential(multiplier, max, exp_base, min)`, `retry_if_exception`, `retry_if_exception_type`, `before_sleep_log` all present |
| redis 6.4.0 native retry | signature probe | `redis.asyncio.retry.Retry(backoff, retries, supported_errors=(ConnectionError, TimeoutError))`; `redis.backoff.ExponentialBackoff(cap=0.512, base=0.008)`; `from_url` forwards `retry`, `retry_on_error`, `socket_timeout`, `socket_connect_timeout` |
| respx 0.23.1 / httpx | import probe | `TimeoutException`, `TransportError`, `HTTPStatusError`, `ReadTimeout`, `ConnectError` present; **httpx default timeout is 5 s** (why delta #5 matters) |
| Test baseline | `uv run pytest -q` | **50 passed** on main `5bc6bfc` |
| ddgs error surface | dir() probe | no public exception types — broad catch at the fallback boundary stays |

## Decisions

### D1 — Guard node placement, naming, timing stage
**Decision**: new node factory `make_guard_input(resources)` in `src/memagent/nodes/guard.py`
(repo convention: short module names — `answer.py`, `embed.py`, …). The node is wrapped
`timed("guard", …)` in `graph.py`, adding a `guard` key to `latency_ms` (the M4 `timed()`
merge tolerates new stages; `log_turn` passes latency through untouched). The canned
refusal is a module constant `BLOCKED_REFUSAL` in `nodes/guard.py` — the guard node is the
only writer of the blocked-path `answer` (spec assumption).
**Rationale**: matches existing file layout; per-stage latency stays complete under the
single-owner `timed()` rule (P-III).
**Alternatives**: `nodes/guard_input.py` (source-spec literal) — rejected for naming
consistency; leaving the node untimed — rejected, every other stage is timed.

### D2 — Graph-entry assertion literals (replaces the source DoD greps)
**Decision**: FR-007's acceptance asserts, on `build_graph(resources).get_graph().draw_mermaid()`:
`"__start__ --> guard_input"` (entry) and `"guard_input -.-> log_turn"` (block edge), plus
router-level unit assertions (`route_after_guard({"guard_verdict": "block"}) == "log_turn"`).
`scripts/render_graph.py` (new, keyless) prints the mermaid text for the DoD/README; it
builds `AgentResources` with `Settings(_env_file=None)` and `None` clients — node
factories only close over resources, so compilation never touches a client or a key.
**Rationale**: live probe showed the source-spec literals (`START -->`, `-->|block|`) can
never appear in langgraph 1.2.7 mermaid output; conditional edges render unlabeled+dotted.
**Alternatives**: post-processing the mermaid text to inject labels — rejected (asserting
on decorated output proves nothing about the graph).

### D3 — Where the OpenAI retry policy applies (and where it must NOT)
**Decision**: `reliability.py` exposes `llm_retry(settings)` — a decorator factory.
`OpenAIChatLLM` and `OpenAIEmbedder` gain an optional `retrying` constructor argument
(default `None` = no wrap); when provided, `__init__` wraps the private seams
(`_call`/`_parse_call` for chat, the single `embeddings.create` seam for embed).
`build_openai_clients` passes `retrying=llm_retry(settings)` to the **conversation client
and the embedder only**. The **analytics client gets none**: the classifier keeps its
M4-contracted `wait_for(8s)` + `stop_after_attempt(2)` (its docstring already declares it
distinct), and ingest page-summaries stay unretried-but-tolerated (their failure already
degrades to chunk-the-markdown).
**Rationale**: single owner per *dependency path* (P-III). Wrapping the analytics client
would nest retries (2×4 = 8 hidden attempts inside an 8 s ceiling) and break M4's
`test_classifier_parsing` assertions of exactly 2 calls. The §9 policy table row is
"OpenAI (chat + embed)" — the analytics path has its own documented policy.
**Alternatives**: removing classify's inner retry and relying on the client policy —
rejected (rewrites M4-owned tests and its contract for zero behavioral gain).

### D4 — Retry predicates and typed-error translation (per dependency)
**Decision** (all built from `Settings`, all waits `wait_random_exponential(max=cap * settings.wait_cap_scale)`, all with `before_sleep_log`):

| Policy | Attempts | Wait cap | Retry on | Fail fast on | Raises on exhaustion / fast-fail |
|---|---|---|---|---|---|
| `llm_retry` | `llm_max_attempts` (4) | 20 s | `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `InternalServerError` | `APIStatusError` with status in {400, 401, 403, 404, 422} | `LLMUnavailableError` (both cases; original exception chained) |
| `tavily_retry` | 3 | 8 s | `httpx.TimeoutException`, `httpx.TransportError`, `HTTPStatusError` 429/5xx | `HTTPStatusError` 400/401/403 → **re-raise original** (fallback trigger, not a typed error) | `SearchUnavailableError` on exhaustion |
| `fetch_retry` | 2 | 2 s | `httpx.TimeoutException`, `httpx.TransportError`, `HTTPStatusError` 502/503/504 | any other `HTTPStatusError` → `PageFetchError` immediately | `PageFetchError` on exhaustion (per URL, non-fatal) |

Translation lives inside each decorator (one place): fail-fast statuses raise the typed
error (or re-raise, Tavily) without consuming retries; `reraise=True` + a final
`except`→typed-error wrap covers exhaustion. `before_sleep_log` uses a **stdlib**
`logging.getLogger("memagent.reliability")` (already routed to stderr by
`configure_logging`'s `basicConfig`) — structlog's PrintLogger is not guaranteed
stdlib-`log()`-compatible.
**Rationale**: verbatim §9 policy table; retrying a 401 hides a bad key and wastes ~15 s
(source risk #1).

### D5 — FallbackProvider semantics under the new policy
**Decision**: `TavilySearcher.search` is wrapped with `tavily_retry`. `FallbackProvider`
catches `(httpx.HTTPStatusError, httpx.TransportError, SearchUnavailableError)` from
Tavily → falls back to ddgs (so BOTH fast-fail 401 and 3-attempt exhaustion reach the
keyless fallback — availability first). If ddgs then also fails, `FallbackProvider`
**raises `SearchUnavailableError`** (today it returns `[]`); the `web_search` node's
existing broad catch converts that to `search_results=[]` + an `errors[]` entry, and
`route_after_search` routes to `answer_failure` → `failed` — same route as today, better
observability.
**Rationale**: FR-M5-21's provider-level exhaustion assertion targets `TavilySearcher`;
the fallback's job is availability. Source risk #10 requires ddgs failures to surface as
the typed error, never a traceback.
**Alternatives**: Tavily exhaustion → raise without trying ddgs — rejected (throws away a
working keyless provider at demo time).

### D6 — Fetch retry integration
**Decision**: `fetch_retry` wraps `_fetch_one` (the single transport seam); the existing
`asyncio.wait_for(page_deadline_s)` in `_fetch_guarded` stays **outside** the retry, so
the 20 s deadline bounds both attempts. The `None`-skip returns (non-HTML, oversize,
unconvertible markdown) remain skips — they are not errors and never retry. Non-retryable
HTTP statuses raise `PageFetchError` (typed) from the decorator; `_fetch_guarded`'s
existing broad catch logs `fetch_skipped` and returns `None` — per-URL, non-fatal,
unchanged shape.
**Rationale**: preserves every M3 behavior the probe found already correct (delta #4)
while adding exactly the retry+typing the FRs demand.

### D7 — Redis native retry + typed translation
**Decision**: new helper `make_redis_client(settings)` in `memory/store.py`:
`aioredis.from_url(settings.redis_url, retry=Retry(ExponentialBackoff(cap=1.0), 3),`
`retry_on_error=[redis ConnectionError, redis TimeoutError], socket_timeout=2.0,`
`socket_connect_timeout=2.0)`. Used by `app.py:build_resources` and `cli._wipe`.
`RedisMemoryStore.knn/store/is_fresh` translate exhausted connection failures to
`MemoryUnavailableError`: each catches `(redis ConnectionError, redis TimeoutError,`
`OSError, RedisSearchError-with-redis-cause)` — the cause-chain walk moves from `cli.py`
to `utils/errors.py` as `redis_down_in_chain(exc)` and is imported by both. Redis
`ResponseError` is **not** caught anywhere (programming bug → surfaces loudly).
**Rationale**: FR-M5-23 wants library-native retry (3 attempts, ~1 s cap, 2 s socket) and
loud programming errors; redisvl's `RedisSearchError` wrapping was a live M3/M4 finding —
without the cause-walk, knn's typed translation would miss the most common failure shape.
**Alternatives**: tenacity for redis too — rejected (the plan pins native `Retry`; two
retry layers on one dependency violates P-III).

### D8 — `memory_search` catch is narrow
**Decision**: the node catches **only `MemoryUnavailableError`** → returns
`{"memory_hits": [], "top_similarity": None, "skip_store": True,`
`"degradation": "redis_down", "errors": [...]}`. Everything else propagates.
**Rationale**: FR-M5-23's "ResponseError surfaces loudly" forbids the broad catch used in
the other nodes; the typed error is the designed degradation signal.

### D9 — `answer_from_web` route/degradation mapping (redis-down aware)
**Decision**: the node stops hardcoding `degradation=None` on the fetched path. New rule:
`degradation = state.get("degradation")` (preserves `redis_down`) — on the snippets path,
`degradation = state.get("degradation") or "snippets_only"` (redis_down wins as the first
cause; the low-confidence disclaimer is still prepended whenever the snippets path runs).
`route = "degraded_web" if degradation else "memory_miss_web_search"`.
**Rationale**: FR-M5-24 requires `degraded_web`/`redis_down` even when pages fetch
normally; today's node would silently overwrite the label.

### D10 — Web-source provenance flags reach `wrap_context`
**Decision**: `ingest_content` adds `"sanitizer_flags": flags` to each enriched output doc
(runtime-additive dict key; the M2 `FetchedDoc` TypedDict declaration is untouched).
`answer_from_web` copies `doc.get("sanitizer_flags", [])` into the source dicts it builds.
`wrap_context` maps by key presence: `stored_at` present → memory mapping
(`url→source_url`, `stored_at→fetched_at`, stored flags); otherwise web mapping
(`url→source_url`, `fetched_at` = wrap-time UTC ISO timestamp computed once per call,
flags default `[]`). Snippets-path sources naturally render `sanitizer_flags: []`.
**Rationale**: §6.4's field mapping requires flags for web sources, but the probe (delta
#9) showed flags never reach state today; enriching the docs ingest already returns is the
only path that adds no state field and no signature change (Rulings C/E hold).
**Alternatives**: a new `AgentState`/`FetchedDoc` field — rejected (M2 owns those types).

### D11 — CLI surface: banners, exit codes, `TurnResult`
**Decision** (implements clarifications Q2/Q3/Q4):
- New `cli.py` constants: `BLOCKED_BANNER = "[BLOCKED by input guard]"`,
  `MEMORY_OFFLINE_BANNER = "[MEMORY OFFLINE → searching the web (not cached)]"`.
- `TurnResult` gains `degradation: str | None = None` (additive NamedTuple default).
- `ask`: `blocked` → blocked banner + refusal, **no sources, exit 0**; `memory_hit` → hit
  banner; `degradation == "redis_down"` → memory-offline banner (replaces miss banner);
  `failed` → **no banner**, apology, **exit 1** (new — today `ask` exits 0 and shows the
  misleading miss banner on failed turns); everything else → miss banner. Flagged turns
  print nothing extra (Q4).
- `chat`: the dormant `guard_input` branch prints the blocked banner before the refusal;
  the `memory_search` branch checks `update.get("degradation") == "redis_down"` → prints
  the memory-offline banner instead of hit/miss; failed turns never exit the REPL.
- The existing `_REDIS_DOWN`/`RedisSearchError` outer catches in `ask`/`chat` remain as a
  startup safety net, but mid-turn redis failures now degrade instead of exiting (the
  graph converts them to `degraded_web` turns) — this is the FR-M5-24 demo behavior.
**Rationale**: pins the three clarification rulings to concrete surfaces; `failed → exit
1` implements FR-M5-27's "non-zero exit" which the probe showed is not true today.

### D12 — `WAIT_CAP_SCALE` mechanics
**Decision**: every policy computes `max_wait = cap_seconds * settings.wait_cap_scale`
inside the factory; `wait_random_exponential(multiplier=1, max=max_wait)` gives full
jitter; scale 0 → `max=0` → every wait is 0 while attempt counts and code path are
unchanged. Policies are factories taking `settings` precisely so tests construct them
with `wait_cap_scale=0` through the production constructor path (no monkeypatched sleeps
— source risk #4).

### D13 — Test allocation and adapted verify commands
**Decision**: M5 owns **five** test files: the four constitution-listed ones
(`test_guardrails.py`, `test_sanitizer.py`, `test_search_retry.py`, `test_fetch_retry.py`)
plus `tests/unit/test_reliability.py` for the scenarios the source left file-unallocated
(OpenAI policy incl. fail-fast/exhaustion, `WAIT_CAP_SCALE=0` wall-time, redis `Retry`
config + `MemoryUnavailableError`, and the degradation-matrix node scenarios with inline
fakes). DoD commands extend accordingly; the graph-entry greps use D2's literals.
**Rationale**: stuffing reliability scenarios into a security-named file hides them; a new
file collides with no other milestone's ownership (M6 owns conftest/integration/e2e/evals).

### D14 — Markdown-image strip is shared, owned by the sanitizer module
**Decision**: `security/sanitizer.py` exposes the compiled image regex and a tiny helper
`strip_markdown_images(text) -> str`; the sanitizer uses it for stored content (FR-012)
and both answer nodes call it on `result.text` **before** appending their own "Sources:"
listing (FR-029) — the appended plain-URL listing is never image syntax, so ordering keeps
citations intact.
**Rationale**: one regex, one owner (P-III); T4 needs the identical semantics at both
defence points.

### D15 — Constants vs Settings
**Decision**: the base64-run threshold (512), `BLOCKED_REFUSAL`, the two new CLI banners,
and the neutralization marker `[removed-suspicious-instruction]` are **code constants**,
not `Settings` fields.
**Rationale**: follows the M4 precedent (`CONVERSATION_MAX_TOKENS` — "code constants, not
env vars", PLAN §6); the source spec marks the 512 threshold "change freely", and none of
these are operational tunables. All genuine tunables M5 reads already exist in `Settings`
(probe-verified: `guard_max_query_chars`, `wait_cap_scale`, `llm_max_attempts`,
`connect/read/page/fetch` caps, `classify_timeout_s`).
