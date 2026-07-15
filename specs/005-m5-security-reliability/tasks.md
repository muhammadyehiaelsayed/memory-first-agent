---
description: "M5 task list — guardrails (L1/L2/L3) and reliability (retries, degradation)"
---

# Tasks: Milestone 5 — Guardrails (L1/L2/L3) and Reliability

**Input**: Design documents in `/Users/mohamed.elsayed/Desktop/epam/specs/005-m5-security-reliability/`
**Repo**: `/Users/mohamed.elsayed/Desktop/epam/memory-first-agent/` (main `5bc6bfc`, 50 tests green)
**Prerequisites**: plan.md, spec.md, research.md (D1–D15), data-model.md, contracts/{security-guardrails,prompts-l2,reliability,graph-and-cli}.md, quickstart.md

**Tests**: REQUIRED. The spec and Constitution (Principle VIII, test-file ownership) name
five M5-owned unit files; they are authored FIRST per story and expected to fail until the
implementation tasks land (TDD, the M2–M4 pattern).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallel-safe (different file, no dependency on an incomplete task)
- **[Story]**: US1 (P1 L1 screen) · US2 (P2 poisoning defence) · US3 (P3 retries) · US4 (P4 degradation)
- All paths are under `src/memagent/` unless stated.

**Recheck fixes baked in** (from the adversarial plan recheck, 2026-07-05 — six fixes A–F):
**[A]** web `sanitizer_flags` producer chain — populated-flags test (T012) + ingest enrich
(T015) + answer copy (T016); **[B]** `ask` table orders `failed` before `redis_down` (T010);
**[C]** ddgs leg stubbed in the search-retry test, since respx can't see primp (T017);
**[D]** dangling `FR-M5-31` → `FR-031` — doc-only, already applied to quickstart.md during
the recheck (no implementation task); **[E]** redis "3 retries = 4 tries" wording (T024);
**[F]** `ruff format --check` intentionally not gated (T001 baseline + T031 DoD sweep).

---

## Phase 1: Setup

**Purpose**: branch, baseline gate, and pin the plan-phase repo facts as the implementation baseline.

- [X] T001 Create branch `m5-security-reliability` from green main (`5bc6bfc`+) in `~/Desktop/epam/memory-first-agent/` — NB the deliverable-repo git branch is the unprefixed `m5-…` (M1–M4 convention: `m4-llms-logging-analytics`, etc.), distinct from the spec-kit feature-dir `005-m5-security-reliability` that plan.md's header names. Baseline gate `uv run ruff check . && make test` (50 tests, zero keys). Do NOT run `ruff format --check` — it is intentionally not a repo gate (matches `make lint`/CI; M4 finding: 16 pre-existing files predate the formatter) **[F]**
- [X] T002 Scripted repo-fact confirmation (no code changes) captured for `docs/ai_prompts/milestone-5.md` (research §R0): (a) only `src/memagent/nodes/memory.py` lacks a try/except — the other five nodes already catch and record `errors[]`; (b) `src/memagent/memory/store.py` `_write` already persists `sanitizer_flags` (CSV) + `content_sha256=sha256(text)`, and `knn` returns `stored_at`+parsed flags (FR-014 pre-satisfied); (c) `web/fetch.py` already enforces non-HTML/oversize/per-URL-non-fatal + `wait_for(page_deadline_s)`; (d) `routers.py` has `route_after_guard` verbatim and `route_after_embed` routes falsy vector → `answer_failure`; (e) `app.py` `TurnResult` has NO `degradation` field; (f) `analytics/classify.py` owns its own `@retry(stop_after_attempt(2))`+`wait_for(8s)`; (g) `cli.py` holds `_redis_down_in_chain`; (h) live `draw_mermaid()` renders `__start__ --> guard_input` and dotted `guard_input -.-> log_turn` (D2 literals)

**Checkpoint**: baseline green, repo facts confirmed — stories can begin.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the two primitives shared across stories — typed errors (US3/US4) and the
pattern registry (US1 L1 + US2 L3). No story can complete without these.

- [X] T003 [P] Fill `src/memagent/utils/errors.py`: `LLMUnavailableError`, `SearchUnavailableError`, `PageFetchError`, `MemoryUnavailableError`, and `redis_down_in_chain(exc) -> bool` (walk `__cause__`; True if any link is redis `ConnectionError`/`TimeoutError` or `OSError`) — MOVE the chain-walk out of `cli.py`; update `src/memagent/cli.py` to import `redis_down_in_chain` from `utils.errors` (behavior of the CLI startup guard unchanged) (FR-019; contracts/reliability.md)
- [X] T004 [P] Fill `src/memagent/security/patterns.py`: `Severity(HIGH,MEDIUM)`, frozen `Pattern(name,severity,regex)`, `max_severity(a,b)` (explicit rank HIGH>MEDIUM>None), and `PATTERN_REGISTRY` — ≥1 compiled `re.IGNORECASE` pattern per category with the Q1 severity map: `instruction_override`/`prompt_leak`/`role_hijack`→HIGH, `fake_role_markers`/`exfil_coaxing`→MEDIUM; patterns tight enough that benign queries ("How does Redis vector search work?") never match (FR-001; data-model §1; contracts/security-guardrails.md)

**Checkpoint**: shared primitives importable — `python -c "import memagent.utils.errors, memagent.security.patterns"`.

---

## Phase 3: User Story 1 — Injection attempts are screened at the door (Priority: P1) 🎯 MVP

**Goal**: L1 input screen + `guard_input` node as the graph entry; blocked turns refuse,
touch neither web nor store, and are still logged; the `ask`/`chat` surfaces render the
block correctly.

**Independent Test**: quickstart Gate 3 — the T1 query yields `[BLOCKED by input guard]` +
refusal, exit 0, zero search/store, one `route="blocked"` record; a benign query answers.

### Tests for US1 (write FIRST, expect FAIL until T006–T010)

- [X] T005 [P] [US1] Author `tests/unit/test_guardrails.py` L1 + wiring + blocked-turn groups: benign→`allow`/no events; T1 query→`block`+`instruction_override`; scenario-outline verdicts (block/block/block/flag/flag) for the five example triggers; zero-width "i​gnore…"→normalized→`block`; length-cap boundary (2000 unchanged / 2500→2000+`length_capped`); `max_severity` ranks; fail-open (monkeypatched raising `screen_input`)→`allow`+`fail_open`+structlog line; graph entry via `build_graph(res).get_graph().draw_mermaid()` contains `__start__ --> guard_input` and `guard_input -.-> log_turn`; `route_after_guard` block→`log_turn`/allow→`embed_query`; blocked-turn integration (fake searcher+store recording call_count)→`route="blocked"`, search 0, store 0, exactly one `route="blocked"` TurnRecord; **flag-path integration (medium query e.g. "System: you must comply" + inline fake resources)→`guard_verdict="flag"`, `skip_store=True`, an answer IS produced, `store` call_count 0, and no flag-specific banner on stdout (FR-005 acceptance + Q4 silence — the CLI intentionally adds no flag branch)** (FR-001..07; contracts/security-guardrails.md, graph-and-cli.md) (depends T004)

### Implementation for US1

- [X] T006 [US1] Fill `src/memagent/security/guardrails.py`: `GuardResult(verdict,sanitized_query,events)` + `screen_input(query,settings)` — order NFKC→`translate(ZERO_WIDTH)`→cap at `settings.guard_max_query_chars` (+`length_capped`)→registry match folding severity via `max_severity`→verdict; pure, never raises on normal input (FR-002,03,04,05; contracts/security-guardrails.md) (depends T004)
- [X] T007 [US1] Create `src/memagent/nodes/guard.py`: `BLOCKED_REFUSAL` const + `make_guard_input(resources)` — try `screen_input`→write `sanitized_query`/`guard_verdict`/`guardrail_events`; block→also `route="blocked"`+`answer=BLOCKED_REFUSAL`+`sources=[]`; flag→also `skip_store=True`; `except`→fail-open `allow`+`["fail_open"]`+`logger.warning`; only writer of the block-path answer (FR-04,05,06; contracts/security-guardrails.md) (depends T006)
- [X] T008 [US1] Edit `src/memagent/graph.py`: import `make_guard_input` + `route_after_guard`; `add_node("guard_input", timed("guard", make_guard_input(resources)))`; `set_entry_point("guard_input")` (replace the `embed_query` entry + its temp comment); `add_conditional_edges("guard_input", route_after_guard, {"log_turn":"log_turn","embed_query":"embed_query"})` (FR-07; contracts/graph-and-cli.md) (depends T007)
- [X] T009 [P] [US1] Create keyless `scripts/render_graph.py`: `Settings(_env_file=None)` + `AgentResources(...=None)` → `print(build_graph(resources).get_graph().draw_mermaid())` (node factories only close over resources; compilation touches no client/key — verified in plan) (FR-07 DoD; contracts/graph-and-cli.md) (depends T008)
- [X] T010 [US1] `src/memagent/app.py`: add `degradation: str | None = None` to `TurnResult` (NamedTuple default) and set it from `final.get("degradation")` in `Agent.answer`. `src/memagent/cli.py`: add `BLOCKED_BANNER="[BLOCKED by input guard]"` + `MEMORY_OFFLINE_BANNER="[MEMORY OFFLINE → searching the web (not cached)]"`; implement the full top-down `ask` render table **ordered `blocked` → `failed`(exit 1) → `memory_hit` → `degradation=="redis_down"` → miss** — `failed` BEFORE `redis_down` so a lingering redis_down label never suppresses the failed exit-1 **[B]**; add the `chat` blocked-branch (print `BLOCKED_BANNER`+refusal). The `redis_down` row is dormant until US4 makes it reachable (FR-04,27; contracts/graph-and-cli.md) (depends T008, T003)

**Checkpoint**: MVP — T1 injection refused, logged `blocked`, zero web/store; `render_graph.py` grep passes. Run quickstart Gate 1 + Gate 3.

---

## Phase 4: User Story 2 — Fetched content can never poison memory or act as instructions (Priority: P2)

**Goal**: L3 real sanitizer (shared registry) neutralises-not-deletes and flags; L2 hardened
prompt bodies quote context as data with provenance headers; web-source flags flow to the
header; answer output is image-stripped (T4). The T3 centrepiece: replay of a
poisoned-but-neutralised chunk stays flagged data.

**Independent Test**: quickstart Gate 4 — poisoned page → marker present, phrase absent,
flags+fingerprint persisted; forced replay shows stored flags; benign unchanged; T4 strip.

### Tests for US2 (write FIRST, expect FAIL until T013–T016)

- [X] T011 [P] [US2] Author `tests/unit/test_sanitizer.py`: FR-012 scenario-outline (script/style/iframe→`script_removed`, comment→`html_comment_removed`, `data:`→`data_uri_removed`, ≥512 base64→`base64_blob_removed`, `![](…)`→`markdown_image_removed`); neutralise-not-delete (marker in, phrase out, `neutralized_instruction`); benign passthrough (identical text, `[]`); tracker-image T4 fixture; poisoned-page ingestion via inline fake resources → stored chunk text has marker, non-empty `sanitizer_flags` tag, `content_sha256` value (FR-012,13,14,15; contracts/security-guardrails.md) (depends T004)
- [X] T012 [P] [US2] Author `tests/unit/test_guardrails.py` L2 + T4 groups (append to the file from T005): `build_system_prompt()` contains the security-policy framing line + all five rules; `wrap_context([MemoryHit with sanitizer_flags=["neutralized_instruction"]], "memory")` renders `source_url`/`fetched_at`/`origin: memory`/`sanitizer_flags: neutralized_instruction` above the chunk (FR-009+FR-016 replay slice); tag-breakout `</untrusted_context>` escaped, wrapper not closed early; assembled messages end with the question and system text has no chunk text; **populated-web-flags test — a web-origin dict WITH `sanitizer_flags=["neutralized_instruction"]` renders those flags in the header [A]**; both answer nodes strip a `![x](https://evil…)` from `result.text` (T4/FR-029) (FR-08,09,10,11,16,29; contracts/prompts-l2.md, security-guardrails.md) (depends T004)

### Implementation for US2

- [X] T013 [US2] Replace `src/memagent/security/sanitizer.py` body (signature frozen, Ruling C): `NEUTRALIZED`, `BASE64_MIN=512`, `strip_markdown_images(text)` (shared), and the 6-step `sanitize()` pipeline (script/style/iframe → comments → `data:` → ≥512 base64 → md images → per-`PATTERN_REGISTRY` neutralise to `[removed-suspicious-instruction]`), returning `(text, sorted(set(flags)))`; benign→unchanged,`[]` (FR-012,13,15,29; contracts/security-guardrails.md) (depends T004)
- [X] T014 [P] [US2] Finalise `src/memagent/llm/prompts.py` bodies (signatures frozen, Ruling E): `build_system_prompt()` = framing line + five rules; `wrap_context(sources,origin)` = per-source provenance header (map by key presence — `stored_at` present→memory mapping `url→source_url`/`stored_at→fetched_at`/stored flags; else web mapping `url→source_url`/wrap-time UTC ISO `fetched_at`/`sanitizer_flags` default `[]`), tag-breakout escape, chunk-text selection unchanged (FR-08,09,10,11,16; contracts/prompts-l2.md)
- [X] T015 [US2] Edit `src/memagent/nodes/ingest.py` (additive; `sanitize()` call-site FROZEN): enrich each output doc → `doc_out = {**doc, "summary": summary, "sanitizer_flags": flags}` using the `flags` already returned by the top-of-loop `sanitize()`; no `FetchedDoc`/state-field change — producer root of the web-provenance chain **[A]** (FR-009; contracts/prompts-l2.md §Producer side) (depends T013)
- [X] T016 [US2] Edit `src/memagent/nodes/answer.py`: (1) `answer_from_web` copies `doc.get("sanitizer_flags", [])` into each source dict it builds **[A]**; (2) BOTH answer nodes set `answer = strip_markdown_images(result.text)` before the "Sources:" append / disclaimer prepend (T4/FR-029). Leave route/degradation for T019 (US4) — this task is provenance + output-strip only (FR-016,29; contracts/prompts-l2.md, security-guardrails.md) (depends T013, T014, T015)

**Checkpoint**: poisoned page neutralised+flagged+persisted; forced replay shows flags; benign untouched; answer image-stripped. Run quickstart Gate 4. US1+US2 = both grading centrepieces (guardrails + poisoning defence) demoable.

---

## Phase 5: User Story 3 — Transient failures recover automatically; permanent ones fail fast (Priority: P3)

**Goal**: single-owner tenacity policies per dependency; four typed errors; client seams
wrapped (analytics client deliberately NOT wrapped, D3); redis native `Retry`. Instant
through the production path at `WAIT_CAP_SCALE=0`.

**Independent Test**: quickstart Gate 5 — search 429×2→200=3 calls, 401=1 call+ddgs, 503
exhaustion→typed; fetch timeout-retry/404-skip/oversize/non-HTML/non-fatal; OpenAI
4-attempt + 401 fast-fail→typed; redis `Retry(retries=3)` + down→typed.

### Tests for US3 (write FIRST, expect FAIL until T020–T024)

- [X] T017 [P] [US3] Author `tests/unit/test_search_retry.py` (respx intercepts **Tavily only**; `WAIT_CAP_SCALE=0`): 429→429→200 → success, Tavily `call_count==3`; 401 → Tavily `call_count==1` + fallback (`provider_used=="ddgs"`); 503×∞ → `TavilySearcher.search` raises `SearchUnavailableError`, `call_count==3`. **The ddgs leg is STUBBED (monkeypatch `DdgsSearcher.search` / inject a fake into `FallbackProvider._ddgs`) — ddgs uses primp/Rust, invisible to respx; without the stub the 401 case hits the live network or leaves `provider_used=None` [C]** (FR-019,21; contracts/reliability.md) (depends T003 — imports the typed errors)
- [X] T018 [P] [US3] Author `tests/unit/test_fetch_retry.py` (respx, `WAIT_CAP_SCALE=0`): read-timeout→200 = `call_count==2`; 404 → `PageFetchError`, `call_count==1`; body > `fetch_max_bytes` → skipped; non-HTML content-type → skipped; three URLs, middle 404s → `fetch_pages` returns 2 docs, turn continues (FR-022; contracts/reliability.md) (depends T003 — imports `PageFetchError`)
- [X] T019 [P] [US3] Author `tests/unit/test_reliability.py` OpenAI + redis groups (inline fakes; D13): `AsyncOpenAI(max_retries=0)` asserted + no `nodes/` module imports tenacity; fake chat raising `RateLimitError`×3→success under 4 attempts + one `before_sleep` line/retry; fake chat raising a 401 (`APIStatusError` status 401)→`LLMUnavailableError`, exactly 1 call; `WAIT_CAP_SCALE=0` → 4-attempt run wall-time <1 s, call_count 4; `make_redis_client` has `Retry` with `retries==3`; fake redis raising `ConnectionError` → `store`/`knn` raise `MemoryUnavailableError` (FR-017,18,19,20,23; contracts/reliability.md) (depends T003 — imports the typed errors)

### Implementation for US3

- [X] T020 [US3] Fill `src/memagent/utils/reliability.py`: `_max_wait(cap_s,settings)=cap_s*settings.wait_cap_scale`; `llm_retry`/`tavily_retry`/`fetch_retry` decorator factories over `Settings` — `wait_random_exponential(multiplier=1,max=_max_wait(cap,settings))`, `before_sleep=before_sleep_log(logging.getLogger("memagent.reliability"), WARNING)`, `reraise=True`; predicates + typed translation per the table (llm 4/cap20 → `LLMUnavailableError` on fast-fail{400,401,403,404,422}+exhaustion; tavily 3/cap8 → re-raise 400/401/403 for fallback, `SearchUnavailableError` on exhaustion; fetch 2/cap2 → `PageFetchError`) (FR-017,18,20,21,22; contracts/reliability.md) (depends T003)
- [X] T021 [US3] Edit `src/memagent/llm/clients.py`: add `retrying: Callable|None=None` to `OpenAIChatLLM.__init__`/`OpenAIEmbedder.__init__`; when set, decorate `_call`/`_parse_call` (chat) and the `embeddings.create` seam (embed) — bodies unchanged; `build_openai_clients` passes `retrying=llm_retry(settings)` to the conversation client AND embedder ONLY, analytics client stays `retrying=None` (D3 — keeps classify's own M4 policy; avoids 2×4 nesting); `AsyncOpenAI(max_retries=0)` unchanged (FR-017,20; contracts/reliability.md) (depends T020)
- [X] T022 [P] [US3] Edit `src/memagent/web/search.py`: `TavilySearcher.__init__` sets `httpx.AsyncClient(timeout=httpx.Timeout(settings.read_timeout_s, connect=settings.connect_timeout_s), headers=…)` (was no explicit timeout); wrap the POST with `tavily_retry(settings)`; `FallbackProvider.search` catches `(httpx.HTTPStatusError, httpx.TransportError, SearchUnavailableError)` from Tavily → ddgs, and raises `SearchUnavailableError` if ddgs also fails (was: returns `[]`); keep the `httpx.AsyncClient` attribute (respx regression guard) (FR-021; contracts/reliability.md) (depends T020)
- [X] T023 [P] [US3] Edit `src/memagent/web/fetch.py`: wrap `_fetch_one` with `fetch_retry(settings)`; the `asyncio.wait_for(page_deadline_s)` in `_fetch_guarded` stays OUTSIDE the retry (bounds both attempts); `None`-skips (non-HTML/oversize/unconvertible) stay skips (never retried); non-retryable statuses raise `PageFetchError`; `_fetch_guarded` broad catch keeps per-URL failures non-fatal (FR-022; contracts/reliability.md) (depends T020)
- [X] T024 [US3] Edit `src/memagent/memory/store.py`: add `make_redis_client(settings)` = `aioredis.from_url(url, retry=Retry(ExponentialBackoff(cap=1.0), 3), retry_on_error=[redis ConnectionError, TimeoutError], socket_timeout=2.0, socket_connect_timeout=2.0)` (note: `retries=3` = 3 retries/4 total tries **[E]**); `knn`/`store`/`is_fresh` translate `(redis ConnectionError, TimeoutError, OSError)` or `RedisSearchError` where `redis_down_in_chain(exc)` → `MemoryUnavailableError` (chain original); `ResponseError` NOT caught. Update `src/memagent/app.py` `build_resources` and `src/memagent/cli.py` `_wipe` to use `make_redis_client` (FR-023; contracts/reliability.md) (depends T003)

**Checkpoint**: retry policies + typed errors proven; `WAIT_CAP_SCALE=0` instant through the prod path. Run quickstart Gate 5.

---

## Phase 6: User Story 4 — Every hard failure has a designed outcome, never a crash (Priority: P4)

**Goal**: wire the degradation matrix end to end so every dependency failure produces a
designed route/degradation and exactly one logged turn — no traceback.

**Independent Test**: quickstart Gate 6 (inline-fake matrix) + Gate 7 (manual `docker stop`).

### Tests for US4 (write FIRST, expect FAIL until T026–T028)

- [X] T025 [P] [US4] Extend `tests/unit/test_reliability.py` with degradation-matrix scenarios (inline fake resources + graph/`Agent`): redis-down (store raises `MemoryUnavailableError`) → answer from web, `skip_store=True`, store call_count 0, `route="degraded_web"`/`degradation="redis_down"`; all fetches raise `PageFetchError` → snippets answer + disclaimer, `degraded_web`/`snippets_only`; searcher raises/`[]` → `answer_failure`, `route="failed"`, no LLM call; chat LLM raises → `failed`; embedder raises → `embed_query`→`answer_failure`→`failed`; analytics raises → record `analytics: null`, route unchanged; **combined redis-down + chat-down → `route="failed"` (regression guard for the ask exit-code ordering [B])**; each case writes exactly one TurnRecord (FR-024,25,26,27,28; data-model §3; contracts/reliability.md) (depends T019)

### Implementation for US4

- [X] T026 [US4] Edit `src/memagent/nodes/memory.py`: wrap the `knn` call in `try/except MemoryUnavailableError` ONLY → return `{"memory_hits":[], "top_similarity":None, "skip_store":True, "degradation":"redis_down", "errors":[…]}`; everything else propagates (ResponseError surfaces loudly, D8) (FR-024; contracts/reliability.md) (depends T024)
- [X] T027 [US4] Edit `src/memagent/nodes/answer.py` `answer_from_web` route/degradation mapping (D9): `degradation = state.get("degradation")` on the fetched path, `= state.get("degradation") or "snippets_only"` on the snippets path (disclaimer still prepended when snippets path runs); `route = "degraded_web" if degradation else "memory_miss_web_search"`. Existing broad LLM catch (→`route="failed"`) unchanged; do NOT clear a lingering `redis_down` on failure (the ask table's `failed`-first ordering handles it) (FR-024,25; contracts/reliability.md) (depends T016 — same file; sequence after T016)
- [X] T028 [US4] Edit `src/memagent/cli.py` `chat`: in the `memory_search` stream branch, print `MEMORY_OFFLINE_BANNER` when `update.get("degradation")=="redis_down"` (else hit/miss as today); confirm a mid-turn redis failure now degrades (graph → `degraded_web`) instead of tripping the outer `_REDIS_DOWN`/`RedisSearchError` startup catch. `ask`'s `redis_down` row (built in T010) now becomes reachable (FR-024; contracts/graph-and-cli.md) (depends T010, T026)

**Checkpoint**: full degradation matrix wired; every failure logged once. Run quickstart Gate 6, then Gate 7 (`docker stop memagent-redis` mid-chat → memory-offline banner + sourced answer, no traceback).

---

## Phase 7: Polish & Milestone Close

- [X] T029 [P] State the threat model T1–T4 + the §7.3 out-of-scope list in a security-notes section (source content for M6's verbatim README publication) — `docs/` or a README subsection (T-M5-18, §6.8)
- [X] T030 [P] Author `docs/ai_prompts/milestone-5.md` (complete M5 instruction record: the five spec-kit phase prompts verbatim, the four `/speckit-clarify` answers, the adversarial plan-recheck workflow and its six applied fixes, the live library-surface verifications) and append the M5 section + per-component provenance rows to `AI_USAGE.md` (FR-030, Constitution P-VII)
- [X] T031 Final DoD sweep per quickstart §Definition of Done: Gate 1 (imports + `render_graph.py` grep) → Gate 2 (five owned files + full suite green + `WAIT_CAP_SCALE=0` instant; `ruff check` only, NOT `format --check` **[F]**) → Gates 3–6 → Gate 7 demoable (T1 blocked+logged; `docker stop` mid-session → clean degraded answer); confirm the **SC-006 invariant** — every turn this session (blocked/degraded/failed included) wrote exactly one `logs/turns.jsonl` line (line count == turn count). Then commit → push `m5-security-reliability` → CI green → merge to main → CI green (M1–M4 workflow); update the project memory note (FR-031, §9 DoD)

---

## Dependencies & Execution Order

- **Phase 1 → 2**: T001 → T002 (facts before code); T003, T004 depend only on T002.
- **US1 (P1, MVP)**: T005 [P] (test, fails) → T006 → T007 → T008 → {T009 [P]} ; T010 needs T008 + T003. Blocked-turn integration in T005 goes green at T010.
- **US2 (P2)**: T011/T012 [P] (tests, fail) → T013 → {T014 [P]} → T015 (needs T013) → T016 (needs T013+T014+T015). Independent of US1 code; run after US1 for a clean MVP checkpoint.
- **US3 (P3)**: T017/T018/T019 [P] (tests, fail) → T020 → then T021 / T022 [P] / T023 [P] (all need T020) ; T024 needs T003. Independent of US1/US2.
- **US4 (P4)**: T025 [P] (test, fails) → T026 (needs T024) → T027 (needs T016 — same file) → T028 (needs T010 + T026). Depends on US3's typed errors.
- **File-coordination (no parallel writes to one file)**: `cli.py` has four writers — T003 (import `redis_down_in_chain`) → T010 (banners/ask-table/chat blocked-branch) → T024 (`_wipe` uses `make_redis_client`) → T028 (chat memory-offline branch). `app.py`: T010 (TurnResult.degradation) → T024 (`build_resources` uses `make_redis_client`). `answer.py`: T016 → T027. `nodes/memory.py`: T026 only. `test_guardrails.py`: T005 → T012 (append). `test_reliability.py`: T019 → T025 (append). `graph.py`: T008 only.
- **Polish**: T029 [P] anytime after US2; T030 [P] alongside late US4; T031 last.

### Parallel opportunities

- T003 + T004 (errors / patterns — different files).
- Within US1: T009 [P] after T008; T005 authored while T006 is being written.
- Within US2: T011 + T012 (both test files) ; T014 [P] alongside T013.
- Within US3: T017 + T018 + T019 (three test files) ; T022 + T023 [P] after T020.
- T029 [P] with US2/US3; T030 [P] with late US4.

## Implementation Strategy

**MVP = Phase 1–3 (US1)**: the L1 input screen + blocked-turn logging is the first graded
"prompt-injection guardrails (basic but real)" deliverable and is demoable alone (`ask` a
T1 query → refusal + one `blocked` record, zero web/store). Then **US2** (the poisoning
defence — the threat model's highest-value T3 centrepiece), **US3** (single-owner retries +
typed errors — the "timeouts/retries" grading requirement), **US4** (the degradation matrix
that closes the demoable `docker stop` outcome). Stop-and-validate at every checkpoint
(T010, T016, T024, T028). The five owned test files are authored before their
implementations and go green as each story lands — the full suite (50 prior + M5) plus
`WAIT_CAP_SCALE=0` instant-retry proof is the final gate. No new dependencies; every edit
sits at a pre-existing M2–M4 seam (Rulings A–G), with the one additive `ingest.py`
enrichment and the `TurnResult.degradation` field explicitly scoped in the plan.

## Traceability (source spec §8 T-M5-01..20 → these tasks)

| Source task | Here | Note |
|---|---|---|
| T-M5-01 errors | T003 | + `redis_down_in_chain` moved from cli.py |
| T-M5-02 patterns | T004 | Q1 severity map |
| T-M5-03 guardrails | T006 | |
| T-M5-04 guard node | T007 | |
| T-M5-05 graph wire | T008 (+T009 render script) | |
| T-M5-06 prompts L2 | T014 | |
| T-M5-07 sanitizer body | T013 | |
| T-M5-08 sha256/flags persist | T002 (verify) + T011 (test) | **pre-satisfied by store.py** |
| T-M5-09 reliability.py | T020 | |
| T-M5-10 client wraps | T021 + T022 + T023 | analytics client NOT wrapped (D3) |
| T-M5-11 redis Retry | T024 | |
| T-M5-12a memory_search redis_down | T026 | |
| T-M5-12b search/empty→failed | existing catch; T025 (test) | pre-wired |
| T-M5-12c fetch→snippets | T027 (+existing fetch catch) | |
| T-M5-12d answer LLM-fail + T4 strip | T016 (T4) + existing catches | embed→failed pre-wired |
| T-M5-12e analytics null | M4 (pre-satisfied); T025 (test) | |
| T-M5-13 test_guardrails | T005 + T012 | |
| T-M5-14 test_sanitizer | T011 | |
| T-M5-15 test_search_retry | T017 | ddgs stub [C] |
| T-M5-16 test_fetch_retry | T018 | |
| T-M5-17 reliability/degradation scenarios | T019 + T025 | |
| T-M5-18 threat model | T029 | |
| T-M5-19 AI_USAGE | T030 | FR-030 |
| T-M5-20 DoD + demo | T031 | FR-031 |
