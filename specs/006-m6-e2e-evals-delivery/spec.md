# Feature Specification: Milestone 6 — Integration/E2E Tests, Eval Harnesses, CI Green, Docs, v1.0

**Feature Branch**: `006-m6-e2e-evals-delivery`

**Created**: 2026-07-06

**Status**: Draft

**Input**: User description: "for Milestone 6, feeding it specs/milestone-6-e2e-evals-delivery.md"

> **Source of truth**: this spec restates `specs/milestone-6-e2e-evals-delivery.md`
> (§1/2/5/7 per its §11 Spec Kit mapping). That file's §3/4/6/10 feed `/speckit-plan`; its
> §8/9 feed `/speckit-tasks`. On any conflict, `PLAN.md` wins (Constitution, Principle VI).
> Depends on Milestones 1–5 (all closed on `main` 2026-07-06: scaffold + schema, memory
> path, web pipeline, finalized clients + turn log + classifier + analytics + REPL, and
> guardrails + reliability). **M6 is the terminal milestone: it adds no product behaviour.**
> It *proves* the behaviour built in M1–M5, packages it, and ships it — the canonical test
> fixtures every other test already depends on, the real-Redis integration round-trip, the
> end-to-end miss→hit lifecycle proof, two eval harnesses (a hard lifecycle gate and an
> honest grounding demonstration), a single green zero-key CI job, auto-generated docs, the
> complete README and AI_USAGE record, a pre-tag re-verification of every time-sensitive
> fact, and the `v1.0` tag. The demoable outcome: **the evaluator runs everything in 5
> commands.**

## Clarifications

### Session 2026-07-06

- Q: Three M6 deliverables need a real OpenAI (`sk-…`) key that isn't available yet — the
  captured live demo transcript (FR-020), the real-key lifecycle run (FR-014), and the
  `temperature=0` re-verification on the pinned `gpt-5.4-mini` id (FR-023, the open M4 T019
  probe). How should these gate the `v1.0` tag? → A: Option A — tag `v1.0` on the **keyless
  path** (CI green + both `--mock` evals + every fact re-verifiable without a paid key). The
  three real-key artifacts are marked **"pending real-key capture"** with a dated note +
  documented placeholders; the tag is NOT blocked on them. This honors zero-key delivery
  (Constitution VIII) and treats the real-key items as the pre-submission/`@manual` steps
  they are by design.
- Q: How should the e2e lifecycle test and the `eval_lifecycle` harness mock web search +
  fetch — which fixes what "search endpoint `call_count`" means in FR-010/011/013? → A: Option
  A — **respx intercepting the real search/fetch httpx client** (LOCKED, not merely preferred).
  `call_count` is a literal HTTP route counter and the real Tavily+trafilatura pipeline is
  exercised end-to-end. A dummy `TAVILY_API_KEY` is set so the searcher takes the interceptable
  httpx path (the keyless fallback provider is not httpx and would escape respx). A counting-fake
  searcher/fetcher was considered and rejected as a weaker proof (it would not exercise the real
  web pipeline).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The memory-first lifecycle is proven end-to-end (Priority: P1)

The assignment's central claim — *ask a question, it searches the web; ask the identical
question again, it answers from memory without touching the web* — is proven as an
executable test, not asserted in prose. A canonical set of test fixtures (a zero-wait
settings object, a deterministic fake language model, a deterministic fake embedder, a
Redis-skip guard, and a clean-index helper) lets the whole suite run without keys or
network. Against a real Redis, a stored page round-trips through the memory store with its
text and metadata intact and its similarity computed exactly at the 0.70 boundary. Then the
single end-to-end test drives the real graph through the agent facade: turn 1 misses memory
and searches the web (returning web-origin sources, the search endpoint called exactly
once); the identical turn 2 hits memory with similarity ≥ 0.70 and the search endpoint call
count is unchanged. Each turn writes exactly one record to the turn log.

**Why this priority**: This is the milestone's core deliverable and the assignment's headline
proof. If only this ships, the graded "memory-first" contract and "log each turn (hit/miss)"
requirement are verified end-to-end. Everything else in M6 packages or continuously re-runs
this proof; the fixtures it introduces are the foundation every other test and script reuses.

**Independent Test**: With a live `redis:8.2` and no keys, run the integration and e2e
suites. The integration test shows a stored chunk retrievable by KNN with intact metadata and
exact 0.70-boundary similarity; the e2e test shows turn 1 `memory_miss_web_search` (search
call count 1, web sources) then identical turn 2 `memory_hit` (similarity ≥ 0.70, search call
count still 1), with exactly two turn records in order.

**Acceptance Scenarios**:

1. **Given** the canonical `settings` fixture, **When** a 4-attempt retry-wrapped call that
   always raises a retryable error runs under it, **Then** `wait_cap_scale` is exactly 0 and
   the call completes all 4 attempts with total sleep time under 0.05 s (production retry path,
   no monkeypatching).
2. **Given** the fake language-model fixture, **When** `complete()` is awaited twice, **Then**
   both results have identical text and each usage block has integer input/output token counts
   and a model string; **and** `parse()` returns a valid instance of the requested schema plus
   a usage dict — with no network.
3. **Given** the fake embedder fixture, **When** the same text is embedded twice, **Then** both
   vectors are bit-identical, length 1536, and unit-norm; **and** a query-dominated text scores
   cosine ≥ 0.70 against the query while a disjoint text scores below 0.70.
4. **Given** no Redis running, **When** the unit subset runs, **Then** it passes and the
   integration/e2e tests report `skipped` (never `error`); **Given** a live Redis, the
   clean-index fixture leaves an empty index (a KNN query returns `[]`).
5. **Given** a live Redis and the clean-index fixture, **When** a page's chunk is embedded and
   stored, **Then** KNN retrieves it with `text`, `url`, `title` intact and `stored_at` a valid
   ISO-8601 string equal to the ISO form of the stored epoch `fetched_at`; **and** creating the
   index a second time raises nothing and leaves exactly one index.
6. **Given** a stored unit vector, **When** queried with the identical vector, an orthogonal
   vector, and a cosine-0.70 vector, **Then** the returned similarity is exactly 1.0, exactly
   0.0, and within 1e-6 of 0.70 respectively (`similarity = 1 − vector_distance`).
7. **Given** real Redis with an empty index and mocked search/fetch endpoints plus the fakes,
   **When** the agent answers "How does Redis vector search work?", **Then** the route is
   `memory_miss_web_search`, at least one source has origin `web`, and the search endpoint call
   count is 1.
8. **Given** turn 1 has ingested the page, **When** the agent answers the identical question,
   **Then** the route is `memory_hit`, the similarity is ≥ 0.70, at least one source has origin
   `memory`, and the search endpoint call count is still 1.
9. **Given** turns 1 and 2 have completed, **When** the per-test turn-log file is read, **Then**
   it contains exactly two JSON lines whose routes are `memory_miss_web_search` then
   `memory_hit` (the second with `similarity_top` ≥ 0.70), each carrying a populated tokens
   block.

---

### User Story 2 - The build verifies itself with zero keys (Priority: P2)

The continuous-integration pipeline re-runs the entire proof on every push with **no real
keys and no secrets**, so the evaluator can trust a green check. A lifecycle eval harness
asks each of a small fixed set of questions twice and is a *hard gate*: it exits non-zero
unless every question is a miss-then-hit. A grounding eval harness demonstrates — honestly
labelled as a demonstration, not a benchmark — that answers are grounded in supplied context,
cite only valid source URLs, and abstain when context is insufficient; in mock mode it needs
no key and always exits zero after printing its scorecard. CI is a single job that runs, in
order, lint → unit → integration/e2e → the lifecycle gate → the grounding demonstration →
a coverage report (report only, never a gate), on a Redis service pinned to the same image
the project ships.

**Why this priority**: This turns the P1 proof into a continuously-enforced contract and
satisfies the "deliver a repo only, runnable" requirement with a reproducible zero-key path.
It depends on the P1 fixtures and the shared resource helper.

**Independent Test**: Run `eval_lifecycle --mock` (exits 0 on a healthy build; 1 and names the
failing question when a turn-2 page is not query-dominated) and `eval_grounding --mock`
(keyless, prints a three-dimension scorecard, exits 0). Inspect `ci.yml`: one job, correct
step order, no `secrets.*`, `redis:8.2` service, Python from `.python-version`, pinned actions,
no coverage threshold.

**Acceptance Scenarios**:

1. **Given** a live `redis:8.2` and no API keys, **When** `python scripts/eval_lifecycle.py
   --mock` runs, **Then** every fixed question routes miss-then-hit (similarity ≥ 0.70) and the
   process exits 0.
2. **Given** a question whose turn-2 page is deliberately not query-dominated, **When** the
   lifecycle eval runs, **Then** the failing question is named in the output and the process
   exits 1.
3. **Given** `--mock` is omitted and `OPENAI_API_KEY` is unset, **When** the lifecycle eval
   runs, **Then** it prints a readable "OPENAI_API_KEY required" message and exits non-zero
   without a Python traceback.
4. **Given** no API key and no Redis, **When** `python scripts/eval_grounding.py --mock` runs,
   **Then** it prints a per-case row for each of the 5–8 fixed cases plus an aggregate for
   grounding, citation-validity, and abstention, states it is a demonstration (not a benchmark),
   and exits 0.
5. **Given** the finalized `ci.yml`, **When** it is inspected, **Then** it is exactly one job
   whose steps run in order ruff → unit → integration/e2e → `eval_lifecycle --mock` →
   `eval_grounding --mock` → coverage report; it contains no `secrets.*` reference; and the
   coverage step has no `--cov-fail-under`/threshold flag.
6. **Given** the finalized `ci.yml`, **When** it is inspected, **Then** the Redis service image
   is exactly `redis:8.2`, the setup-python step reads `python-version-file` `.python-version`,
   and no `actions/*` reference is unpinned (`@main`).

---

### User Story 3 - Documentation is auto-generated and verifiable (Priority: P3)

The architecture diagram in the README is provably generated from the compiled graph, not
hand-drawn: a script renders the graph's mermaid and splices it between stable markers in the
README and the architecture doc, and re-running the script reproduces byte-identical output
listing all ten graph nodes. A capture script runs a live miss→hit session and writes a
reproducible demo transcript showing the same question answered first from the web, then from
memory.

**Why this priority**: A verifiably-generated diagram and a captured transcript raise evaluator
trust and make the "not hand-drawn" claim checkable, but they package the already-proven
system rather than proving new behaviour, so they rank below the proof and its CI gate.

**Independent Test**: Run the render script twice — the mermaid between the markers is
byte-identical on the second run and names all ten nodes. Run the capture script with a real
key + Docker Redis — the transcript shows a MISS with web sources then a HIT with similarity
≥ 0.70.

**Acceptance Scenarios**:

1. **Given** the compiled graph built with fake resources, **When** the render script runs,
   **Then** the README and the architecture doc contain a mermaid block between the stable
   markers naming all ten nodes (`guard_input`, `embed_query`, `memory_search`,
   `answer_from_memory`, `web_search`, `fetch_pages`, `ingest_content`, `answer_from_web`,
   `answer_failure`, `log_turn`).
2. **Given** the render script has already run once, **When** it runs again, **Then** the
   mermaid content between the markers is byte-identical (idempotent).
3. **Given** a valid `OPENAI_API_KEY` and Docker Redis, **When** the capture script runs the
   same question twice, **Then** the demo transcript shows a MISS with web sources followed by
   a HIT from memory with similarity ≥ 0.70.

---

### User Story 4 - The repo is delivered: complete docs, re-verified facts, v1.0 (Priority: P4)

The repository reaches a submittable state. The README contains every required section
verbatim — the quickstart including the zero-keys line, the threat-model table, the 0.70
calibration note, the coarse-TTL note with its ETag production upgrade, the robots.txt
limitation, why fetch+markdown stay in-house, the DuckDB-queryable-JSONL note, the pip
fallback, the worked paraphrase example, and the rationale for deliberately not being a
ReAct/tool-calling agent. `AI_USAGE.md` holds the complete instruction record with the M6
prompts appended as the milestone lands. Every time-sensitive fact (model ids, prices,
dependency pins, library signatures) is re-verified immediately before tagging and any drift
is corrected. Finally the `v1.0` tag is cut on the green commit, and a fresh evaluator can go
from clone to a live miss→hit in five commands.

**Why this priority**: This is the terminal "ship it" slice. It depends on everything above
being green (the proof, the CI gate, the generated docs) and closes the assignment's
"document AI assistance" and "deliver a runnable repo" requirements. It ranks last because it
packages and releases rather than proving behaviour.

**Independent Test**: Grep the README for each required phrase (e.g. "Zero keys needed",
"Memory poisoning", "read_json_auto", "not a ReAct"); confirm `AI_USAGE.md` contains the
literal "the complete instruction record" and a per-milestone log through M6 in
`docs/ai_prompts/`; confirm a dated re-verification note lists each time-sensitive fact; run
the documented 5-command sequence to a live miss→hit and the zero-key path with no keys; and
`git tag` lists `v1.0`.

**Acceptance Scenarios**:

1. **Given** the finalized README, **When** it is inspected, **Then** it contains all ten
   required verbatim sections: the quickstart incl. the zero-keys line, the T1–T4 threat-model
   table, the 0.70 calibration note, the coarse-TTL note + ETag upgrade, the robots.txt
   limitation + production fix, why fetch+markdown stay in-house, the DuckDB `read_json_auto`
   note, the pip fallback, the worked paraphrase example, and the "not a ReAct/tool-calling
   agent" rationale.
2. **Given** the finalized `AI_USAGE.md`, **When** it is inspected, **Then** it has all eight
   sections, contains the literal phrase "the complete instruction record", and points to
   `docs/ai_prompts/` which holds a chronological per-milestone log through M6 (the M6 entry
   appended as the milestone landed, not retroactively).
3. **Given** the pre-tag re-verification list, **When** each time-sensitive fact is re-checked
   immediately before tagging, **Then** a date-stamped note (2026-07-04 or later) records each
   row's status and any price/id drift has been corrected in config and `MODEL_CHOICES.md`.
4. **Given** CI is green and all M6 requirements pass on HEAD, **When** the release is tagged,
   **Then** `git tag` lists `v1.0`.
5. **Given** a fresh clone, `OPENAI_API_KEY`, and Docker, **When** the five documented commands
   run in order, **Then** the chat REPL answers the same question first as a MISS then as a HIT;
   **and** with no keys and no Redis, `make test` passes the unit subset (integration/e2e
   skipped) and `python scripts/eval_lifecycle.py --mock` passes against the CI Redis.

---

### Edge Cases

- **Distance ≠ similarity.** The integration test asserts `similarity = 1 − vector_distance`
  (never `1 − d/2`); the 0.70 boundary is inclusive. A float32 "true 0.70" that returns as
  `0.69999…` is compared with a `1e-6` tolerance — the global threshold is never loosened.
- **Turn-2 hit depends on fake-embedder token overlap.** If the mocked page does not repeat the
  query verbatim (or extraction strips it below the 200-char / 100-char floors), turn 2 can fall
  below 0.70 and the core proof fails for the wrong reason. The mocked HTML must stay
  query-dominated and > 200 chars after extraction.
- **HTTP mocking only patches httpx.** Redis traffic and the fakes are untouched; the searcher
  must therefore take the Tavily-httpx path (a dummy `TAVILY_API_KEY` is set), or the keyless
  fallback provider (not httpx) escapes interception and the search call count never increments.
- **First query always misses.** An empty index makes KNN return `[]` and the top similarity
  `None` — a normal miss, not an error; the e2e turn 1 relies on this.
- **Fallback-provider fragility at demo time.** The keyless fallback is a scraper; the capture
  and real-key lifecycle runs prefer the primary provider, and a fallback throw degrades to an
  explicit "web search unavailable" turn, never a traceback.
- **Scope creep while "polishing".** No coverage gate, no Redis turn-log mirror, no
  canary/output-defang, no gray-zone LLM guard, no 0.50 salvage route may be added — they were
  cut by design (Constitution VI, anti-churn).
- **Model/price drift.** Prices and ids were verified 2026-07-04; they are re-verified at tag.
  `temperature=0` support on the pinned model id is snapshot-sensitive and must be confirmed.
- **Evaluator without uv/Docker.** The pip fallback is documented and the unit subset must pass
  keyless and dockerless (verified in a clean venv).
- **CI service vs docker-compose drift.** The CI Redis image must stay exactly `redis:8.2`
  (matching `docker-compose.yml`) so the tested environment equals the shipped one.

## Requirements *(mandatory)*

Numbering preserves the source spec: FR-001…FR-025 restate FR-M6-01…FR-M6-24 (including the
source's `FR-M6-11b`, which becomes **FR-012**, shifting FR-M6-12…24 to FR-013…025). No
milestone product behaviour is added — every requirement is a proof, a package step, or a
release gate.

### Functional Requirements

**Canonical test fixtures — `tests/conftest.py` (US1)**

- **FR-001**: The system MUST provide a `settings` fixture returning a `Settings` with
  `wait_cap_scale == 0`, a per-test temporary turn-log path, and a dummy key so no real key is
  needed. *Acceptance*: a retry decorated by the reliability owner performs its full attempt
  count with total sleep time ≈ 0 s (no real backoff, production code path).
- **FR-002**: The system MUST provide a `FakeLLM` fixture implementing the chat-LLM protocol:
  `complete()` returns a canned result whose usage dict has integer input/output token counts
  and a model string; `parse()` returns a valid instance of the requested schema plus a usage
  dict. *Acceptance*: `complete()` and `parse()` need no network and return deterministic values
  across runs.
- **FR-003**: The system MUST provide a deterministic `FakeEmbedder` fixture with `dim == 1536`
  whose `embed()` returns L2-normalized unit vectors, is bit-stable for identical input, and
  scores a query-dominated text at cosine ≥ 0.70 to the query. *Acceptance*: embedding the same
  text twice is bit-identical; for a query-dominated page `p`, `cosine(embed(q), embed(p)) ≥
  0.70`; a disjoint text scores below 0.70. (A page merely *containing* the query plus
  substantial unrelated content is not guaranteed to clear 0.70 — the e2e proof relies on a
  query-dominated page.)
- **FR-004**: The system MUST provide a `redis_url` fixture that pings the configured Redis and
  calls `pytest.skip(...)` if it is unreachable. *Acceptance*: with no Redis running,
  `pytest -m "not integration and not e2e"` passes and integration/e2e tests report `skipped`,
  never `error`.
- **FR-005**: The system MUST provide a `clean_index` fixture (depending on `redis_url`) that
  drops and recreates the empty `web_memory` index before the test body, using the M1 schema
  helpers (`get_index` + `wipe_index`, not an invented `build_index`). *Acceptance*: after the
  fixture runs, a KNN query returns `[]`.

**Redis integration round-trip — `tests/integration/test_redis_store.py` (US1)**

- **FR-006**: Creating the index when it already exists MUST NOT raise and MUST NOT duplicate
  it. *Acceptance*: calling create twice leaves exactly one `web_memory` index.
- **FR-007**: A stored page's chunk MUST be retrievable by KNN with its `text`, `url`, and
  `title` intact. *Acceptance*: after `store(...)`, `knn(embed(query), k=5)` returns a hit whose
  `text`/`url`/`title` equal the stored chunk.
- **FR-008**: `url`, `title`, and `fetched_at` MUST survive the round-trip, with `fetched_at`
  converted from epoch to ISO-8601 at the memory-hit boundary. *Acceptance*: the returned hit's
  `stored_at` is a valid ISO-8601 string equal to the ISO form of the stored epoch `fetched_at`.
- **FR-009**: A vector stored and queried with a known cosine relationship MUST yield
  `similarity == 1 − vector_distance`, including the exact 0.70 boundary. *Acceptance*: the
  identical vector gives similarity 1.0, an orthogonal vector 0.0, and a cosine-0.70 pair a
  similarity within 1e-6 of 0.70; with `SIMILARITY_THRESHOLD` 0.7 the 0.70 case routes as an
  inclusive hit.

**End-to-end lifecycle — `tests/e2e/test_lifecycle.py` (US1)**

- **FR-010**: Against real Redis with mocked search/fetch and the fakes, the first ask of a
  fresh question MUST route `memory_miss_web_search` and return web-origin sources.
  *Acceptance*: `route == "memory_miss_web_search"`, at least one source has `origin == "web"`,
  and the search endpoint call count (the respx HTTP route counter) is 1.
- **FR-011**: The identical second ask MUST route `memory_hit` with similarity ≥ 0.70 and MUST
  NOT touch the web. *Acceptance*: `route == "memory_hit"`, `similarity >= 0.70`, at least one
  source has `origin == "memory"` citing the turn-1 URL, and the search endpoint call count is
  still 1.
- **FR-012**: Each turn MUST write exactly one turn record to `settings.turn_log_path`. This is
  where M6 *proves* the "log each turn (hit/miss)" requirement end-to-end. *Acceptance*: after
  turns 1 and 2 the per-test `turns.jsonl` holds exactly two parseable JSON objects whose routes
  are `["memory_miss_web_search", "memory_hit"]` in order, each with a non-empty tokens dict, and
  the second object's `similarity_top >= 0.70`.

**Eval harnesses — `scripts/eval_lifecycle.py`, `scripts/eval_grounding.py` (US2)**

- **FR-013**: `eval_lifecycle.py --mock` MUST ask each fixed question twice and exit 1 unless
  **every** question is miss-then-hit (`memory_miss_web_search` then `memory_hit` with similarity
  ≥ 0.70); it exits 0 when all hold. *Acceptance*: on a healthy build it exits 0; if any question
  breaks the contract it names that question and exits 1.
- **FR-014**: The same script MUST run against real OpenAI + real search when `--mock` is
  omitted and `OPENAI_API_KEY` is set, for a manual pre-submission check. This real-key run is
  **not** a `v1.0` gate (Clarifications): absent a key it is recorded "pending real-key
  capture". *Acceptance*: without `--mock` and without `OPENAI_API_KEY` it exits non-zero with a
  readable "OPENAI_API_KEY required" message and no traceback.
- **FR-015**: `eval_grounding.py` MUST run 5–8 fixed cases and, for each, produce an answer over
  a supplied context and score it on grounding, citation-validity, and abstention with the nano
  model as judge; the output MUST state it is a demonstration, not a benchmark. *Acceptance*: the
  printed scorecard contains a per-case row and an aggregate for all three dimensions; the file
  is a small single-purpose script (~120 lines with both `--mock` and real-key modes; the
  original "~40–60" estimate did not account for the real-key mode + ruff formatting).
- **FR-016**: `eval_grounding.py --mock` MUST use the fake LLM for both answerer and judge, need
  no API key and no Redis, and exit 0 after printing the scorecard. *Acceptance*: it exits 0 with
  no network access.

**CI pipeline — `.github/workflows/ci.yml` (US2)**

- **FR-017**: CI MUST be a single job running, in order: ruff (lint + format check) → unit →
  integration/e2e → `eval_lifecycle --mock` → `eval_grounding --mock` → coverage report; it MUST
  reference no repository secrets. *Acceptance (independent checks)*: (a) exactly one job; (b)
  steps in the stated order; (c) no `secrets.*` reference; (d) the coverage step has no
  `--cov-fail-under`/threshold flag.
- **FR-018**: The CI environment MUST match the shipped one: the Redis service is pinned
  `redis:8.2` (matching `docker-compose.yml`), Python comes from `.python-version`, and every
  `actions/*` is pinned. *Acceptance (independent checks)*: (a) `services.redis.image ==
  "redis:8.2"`; (b) the setup-python step uses `python-version-file`; (c) no `actions/*@main` or
  otherwise-unpinned action use.

**Auto-generated documentation — `scripts/render_graph.py`, `scripts/capture_demo.py` (US3)**

- **FR-019**: `render_graph.py` MUST render the compiled graph's mermaid and write it between
  stable markers in both `README.md` and `docs/architecture.md`; re-running MUST reproduce
  byte-identical mermaid between the markers. *Acceptance*: a second run leaves the between-marker
  content unchanged and the diagram names all ten nodes.
- **FR-020**: `capture_demo.py` MUST run a live miss→hit session and write `docs/demo_transcript.md`
  (real OpenAI key only — the Constitution forbids GitHub Models for the recorded demo). Absent a
  real key, `docs/demo_transcript.md` is a documented placeholder marked "pending real-key capture"
  and does not block the tag (Clarifications). *Acceptance*: when captured, the transcript shows the
  same question twice — a MISS with web sources, then a HIT from memory with similarity ≥ 0.70.

**Final documentation and release — README, AI_USAGE, re-verification, tag (US4)**

- **FR-021**: The README MUST contain all ten required sections sourced verbatim: the quickstart
  incl. the zero-keys line; the T1–T4 threat-model table; the 0.70 calibration note; the
  coarse-TTL note + ETag production upgrade; the robots.txt limitation + production fix; why
  fetch+markdown stay in-house; the DuckDB `read_json_auto` note; the pip fallback; the worked
  paraphrase example; and the "deliberately not a ReAct/tool-calling agent" rationale.
  *Acceptance*: each of the ten items is present and matches the source wording.
- **FR-022**: `AI_USAGE.md` MUST have all eight sections and point to `docs/ai_prompts/`,
  explicitly labelled "the complete instruction record", with the M6 prompts appended as the
  milestone lands (never retroactively). *Acceptance*: `docs/ai_prompts/` contains a per-milestone
  chronological log through M6 and `AI_USAGE.md` contains the literal phrase "the complete
  instruction record".
- **FR-023**: Every time-sensitive fact (model ids + prices, `temperature=0` support on the
  pinned model id, search request shapes, fallback API, model-catalog ids, `redis:8.2` module
  availability, the structured-output method, all dependency pins, and the key library
  signatures) MUST be re-verified immediately before tagging and any drift corrected in config
  and docs. Facts re-verifiable without a paid key are checked at tag; real-key-dependent facts
  (notably `temperature=0` support on `gpt-5.4-mini` — the open M4 T019 probe) are recorded
  "pending real-key capture" in the note rather than blocking the tag (Clarifications).
  *Acceptance*: a date-stamped note (2026-07-04 or later) records each row checked, its status,
  and any item marked "pending real-key capture".
- **FR-024**: A `v1.0` git tag MUST be created on the commit where CI is green and every
  requirement verifiable on the **keyless path** passes; the three real-key artifacts (the
  real-key portions of FR-014, FR-020, FR-023) may be marked "pending real-key capture" and do
  NOT block the tag (Clarifications). *Acceptance*: `git tag` lists `v1.0` on a green,
  keyless-verified commit.
- **FR-025**: A fresh evaluator MUST be able to go from clone to a live miss→hit in five
  commands, and the zero-key path (`make test` + `eval_lifecycle --mock`) MUST pass with no keys.
  *Acceptance*: the documented 5-command sequence produces a working miss→hit session and the
  zero-key path passes with Docker stopped for the unit subset and a CI-equivalent Redis for the
  mock eval.

### Key Entities

- **Canonical fixtures**: the five load-bearing pytest fixtures whose names and signatures are
  frozen from first use — `settings` (`WAIT_CAP_SCALE=0`, per-test turn-log), `fake_embedder`
  (dim 1536, unit vectors, token-overlap → high cosine), `fake_llm` (deterministic
  `complete`/`parse` with usage), `redis_url` (ping-or-skip), `clean_index` (drop + recreate
  empty index). Consumed by every test file.
- **Shared resource helper (`build_test_resources()`)**: a plain, importable function that
  assembles the agent's resources (fakes for LLM/embedder, real store for integration/e2e,
  mocked search/fetch, a real turn logger at the per-test log path). The pytest `resources`/`agent`
  fixtures wrap it; `eval_lifecycle` (a standalone script) imports it after prepending the repo root
  to `sys.path` (`tests/` is not an installed package). `render_graph` stays keyless and does NOT use
  it; `eval_grounding --mock` is redis-less and does NOT use it (uses `FakeLLM` directly).
- **Lifecycle eval harness**: the hard gate that asks each fixed question twice and exits
  non-zero unless every question is miss-then-hit. Mock mode is keyless (CI); real-key mode is a
  manual pre-submission check.
- **Grounding eval harness**: an honestly-labelled *demonstration* (not a benchmark) that scores
  grounding, citation-validity, and abstention with the nano model as judge over 5–8 fixed cases;
  mock mode is keyless and non-gating (exit 0).
- **CI job**: the single zero-secret GitHub Actions job pinning `redis:8.2` and `.python-version`,
  running lint → unit → integration/e2e → both eval mocks → a coverage report (no gate).
- **Turn log (JSONL)**: the append-only `turns.jsonl` — the single source of truth for turns; the
  e2e test reads it back to prove one record per turn.
- **Architecture diagram**: the mermaid rendered from the compiled graph, spliced between stable
  markers in the README + architecture doc; idempotent and naming all ten nodes.
- **`v1.0` tag**: the release marker cut on the green commit that satisfies every M6 requirement.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The unit subset passes with **no Redis, no network, no keys**, and the
  integration/e2e tests report `skipped` (never `error`) when Redis is down.
- **SC-002**: The end-to-end lifecycle test proves the assignment's core contract: turn 1
  `memory_miss_web_search` with web sources and search call count 1; identical turn 2
  `memory_hit` with similarity ≥ 0.70 and search call count still 1; exactly two turn records
  written in order.
- **SC-003**: The Redis integration round-trip preserves a stored chunk's text and metadata and
  computes similarity exactly (`1 − vector_distance`) at the identical, orthogonal, and 0.70
  boundary cases (within 1e-6).
- **SC-004**: `eval_lifecycle --mock` exits 0 on a healthy build and 1 (naming the failing
  question) when any question breaks miss-then-hit; `eval_grounding --mock` exits 0 keyless after
  printing a three-dimension scorecard.
- **SC-005**: CI is a single green job — ruff → unit → integration/e2e (`redis:8.2`) →
  `eval_lifecycle --mock` → `eval_grounding --mock` → coverage report — with no `secrets.*`, no
  coverage gate, pinned actions, and Python from `.python-version`.
- **SC-006**: The README contains all ten required verbatim sections and `AI_USAGE.md` carries
  the complete instruction record (the literal phrase present, M6 appended non-retroactively) with
  a per-milestone log through M6 in `docs/ai_prompts/`.
- **SC-007**: `render_graph.py` regenerates a mermaid diagram naming all ten nodes into the
  README + architecture doc idempotently (a second run leaves the between-marker content
  byte-identical), and `docs/demo_transcript.md` captures a real miss→hit session **when a real
  `OPENAI_API_KEY` is available** — otherwise it is a dated "pending real-key capture" placeholder
  that does not block `v1.0` (Clarification Q1 / FR-020).
- **SC-008**: Every keyless-verifiable time-sensitive fact is re-verified with a date-stamped
  note before tagging (real-key-dependent items marked "pending real-key capture"), any drift
  corrected, and `v1.0` is tagged on the green, keyless-verified commit — after which a fresh
  evaluator reaches a live miss→hit in five commands and the zero-key path passes.

## Assumptions

- **M6 owns exactly the five test/eval artifacts plus `conftest.py`** (ruling A): `tests/conftest.py`,
  `tests/integration/test_redis_store.py`, `tests/e2e/test_lifecycle.py`, `scripts/eval_lifecycle.py`,
  `scripts/eval_grounding.py`, plus the doc/render/capture scripts. All other test files
  (`test_routing`, `test_similarity`, `test_chunker` — M2; `test_classifier_parsing`, `test_turnlog`
  — M4; `test_sanitizer`, `test_guardrails`, `test_search_retry`, `test_fetch_retry` — M5) are owned
  upstream; M6 consumes their green status in CI and does not rewrite them.
- **Non-happy-path routes are covered upstream, not re-proven e2e.** The e2e lifecycle test proves
  only `memory_miss_web_search` → `memory_hit`. `blocked` (M5 guardrails + M2 routing + M4 turnlog),
  `degraded_web` and `failed` (M5 reliability/degradation + M2 routers) are consumed green in CI.
- **Fixture names/signatures are frozen from first use** and consolidated into the single canonical
  `conftest.py` here; upstream M2/M4/M5 unit tests keep passing unchanged against the finalized
  fixtures.
- **Plan-silent minimal-assumption defaults** (change freely; documented in the source spec): the
  `PageFetcher` signature is `async def fetch(self, urls) -> list[FetchedDoc]`; `TurnLogger.log(record: dict)`
  is a synchronous append; the `FakeLLM.parse` `schema_factory` shape is M6-local; the lifecycle eval's
  question set is three diverse, unambiguous questions each with a query-dominated mocked page; the
  grounding eval's case texts are M6-local; the "5 commands" naming is the minimal reading of the §13
  demoable outcome.
- **HTTP mocking approach (LOCKED, Clarifications)**: respx intercepts the real search/fetch httpx
  client, so the "search endpoint `call_count`" assertion is a literal HTTP route counter and the
  real Tavily+trafilatura pipeline is exercised end-to-end. A dummy `TAVILY_API_KEY` forces the
  httpx path so interception is valid (the keyless fallback provider is not httpx and would escape
  respx). The injected counting-fake alternative was considered and rejected as a weaker proof.
- **Similarity boundary**: `similarity = 1 − vector_distance` exactly; 0.70 is an inclusive hit;
  float32 boundary noise is absorbed with a 1e-6 tolerance, never by loosening the global threshold.
- **No new product behaviour and no new dependencies**: M6 finalizes and proves; it introduces no
  temporary stubs and replaces none. Dev deps (`pytest`, `pytest-asyncio`, `respx`, `pytest-cov`,
  `ruff`) have been pinned since M1/M5.
- **Anti-churn cuts stand** (Constitution VI; do not re-add while "polishing"): coverage gate, Redis
  turn-log mirror, output URL-defang allowlist / canary token, gray-zone LLM guard, the 0.50
  weak-memory salvage route, the embed-failure→web route, token streaming, deep session memory.
- **If a test reveals a bug in an upstream module**, the fix is applied here as a corrective and logged
  in `AI_USAGE.md`; M6 does not otherwise modify M1–M5 implementations.
- **`DECISIONS.md` finalization** is a delivery/DoD item carried from the source spec §2/§9 (finalize the
  repo-root anti-churn record scaffolded in M1); it has **no discrete FR-###** in this spec's FR set
  (FR-001…025) and is covered by task T014 + the quickstart DoD rather than a numbered requirement.
- **Audience**: the primary user is the developer/evaluator operating the agent and CI locally;
  requirement and scenario language may therefore reference the delivered commands, files, and record
  fields directly.
