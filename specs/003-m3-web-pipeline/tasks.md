# Tasks: Milestone 3 — Web Pipeline (Search, Fetch, Markdown, Summarize, Ingest)

**Input**: Design documents from `/specs/003-m3-web-pipeline/`
**Prerequisites**: plan.md, spec.md (+ Clarifications 2026-07-05), research.md (D1–D10),
data-model.md, contracts/ (4 files), quickstart.md
**Code root**: `~/Desktop/epam/memory-first-agent/` (all file paths below are relative to it)

**Tests**: M3 owns exactly ONE automated test file — the OPTIONAL
`tests/unit/test_to_markdown.py` (Ruling A; spec Assumptions). Every other §7 scenario is
M5/M6-owned automation. Do NOT write other test files in this milestone.

**Phase ordering note**: story phases are ordered by build dependency
(US2 → US3 → US4 → US1), not by priority number. US1 (P1) is the capstone integration
story — the live miss→ingest→hit demo — and consumes everything the other stories build.
This mirrors the source file's T-M3-01..14 ordering.

**Organization**: tasks are grouped by user story; source task ids (T-M3-NN) and FR ids
are cited per task for traceability.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4)

## Phase 1: Setup

**Purpose**: prove the prerequisites and open the working branch

- [X] T001 Verify M3 prerequisites and open branch `m3-web-pipeline` in the deliverable
      repo: `git -C ~/Desktop/epam/memory-first-agent checkout -b m3-web-pipeline` from
      green main; `make redis-up` running; `.env` carries the GitHub Models block (M2)
      plus `TAVILY_API_KEY` (probe-verified 2026-07-05, research D1);
      `uv run python -c "import httpx, trafilatura, ddgs, structlog"` exits 0
      (all pinned since M1 — plan Technical Context)

**Checkpoint**: branch open, Redis up, credentials in place, zero new pins needed

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the two contract/seam edits every later phase assumes

- [X] T002 [P] Fill `src/memagent/security/sanitizer.py` with the PASS-THROUGH stub
      `sanitize(text) -> tuple[str, list[str]]` returning `(text, [])`, carrying the
      M5-replacement docstring verbatim from contracts/ingest-and-sanitize.md
      (T-M3-02; FR-021; Ruling C)
- [X] T003 [P] Edit `src/memagent/interfaces.py` — two Protocol changes: (a) add
      `async def is_fresh(self, h: str) -> bool: ...` to `MemoryStore`, matching the
      existing `RedisMemoryStore.is_fresh` signature (store.py:140); (b) replace the
      M2 placeholder `PageFetcher.fetch(self, results: list[SearchResult])` with the M3
      design signature `async def fetch(self, urls: list[str]) -> list[FetchedDoc]: ...`
      and drop its placeholder docstring (authorized: the placeholder says "M3 fleshes
      this out"; the node applies `filter_urls` and passes plain URLs). No other
      Protocol changes (research D4; data-model.md §4; FR-024 prerequisite; analyze I1)

**Checkpoint**: seams fixed — `uv run python -c "import memagent.interfaces,
memagent.security.sanitizer"` exits 0

---

## Phase 3: User Story 2 — Web content acquisition is safe, bounded, and resilient (Priority: P2)

**Goal**: the three web modules + the two acquisition nodes: Tavily/ddgs search with
fallback + provider recording, SSRF-guarded bounded fetch, markdown gating.

**Independent Test**: `filter_urls` drops every unsafe-table URL and keeps article links
(spot-check via `uv run python -c`); a live one-off `FallbackProvider.search` returns
Tavily results with `provider_used="tavily"`; `uv run pytest
tests/unit/test_to_markdown.py -q` green.

- [X] T004 [P] [US2] Fill `src/memagent/web/to_markdown.py`: `to_markdown(html) -> str | None`
      with `MIN_MARKDOWN_CHARS=200`, `MAX_MARKDOWN_CHARS=20_000`, precision pass →
      recall retry → floor reject → cap, kwargs verbatim per
      contracts/fetch-and-markdown.md (T-M3-01; FR-017..020; research D9)
- [X] T005 [P] [US2] Write OPTIONAL M3-owned `tests/unit/test_to_markdown.py`: precision
      kwargs asserted, empty-precision→recall retry, 199→None / 200→kept floor,
      25000→20000 cap — monkeypatch `trafilatura.extract`; keyless, no network
      (T-M3-01; quickstart §2)
- [X] T006 [US2] Implement `TavilySearcher` in `src/memagent/web/search.py`: reusable
      `httpx.AsyncClient`, raw POST to `https://api.tavily.com/search` with bearer auth
      and `include_raw_content: False`, map `content→snippet` (research D1), order→rank;
      NO `tavily` import (T-M3-03; FR-001, FR-002)
- [X] T007 [US2] Add `DdgsSearcher` (sync `DDGS().text` via `asyncio.to_thread`, map
      `title/href/body`, research D2) and `FallbackProvider` (Tavily-first iff key
      non-blank; `httpx.HTTPStatusError | httpx.TransportError` → ddgs; both-fail → `[]`;
      sets `self.provider_used`; ONE structlog line with `provider_used`; NO retries) to
      `src/memagent/web/search.py` (T-M3-04; FR-003, FR-004, FR-005; research D5, D6)
- [X] T008 [P] [US2] Implement `filter_urls(urls, settings)` in `src/memagent/web/fetch.py`
      with `ALLOWED_SCHEMES`, SSRF guard via `ipaddress` (localhost/private/loopback/
      link-local/reserved literals), `JS_ONLY_DENYLIST` (7 domains, registrable-domain
      match), max-2-per-domain order-preserving — constants verbatim from
      contracts/fetch-and-markdown.md (T-M3-05; FR-006..009)
- [X] T009 [US2] Implement `HttpxPageFetcher` in `src/memagent/web/fetch.py`:
      `follow_redirects=True`, `httpx.Timeout(connect=5, read=10)` from Settings,
      `USER_AGENT` const with repo link, `asyncio.Semaphore(FETCH_CONCURRENCY)`, per-URL
      `asyncio.wait_for(_, PAGE_DEADLINE_S)`, streamed body abort at `FETCH_MAX_BYTES`
      (skip, never truncate-keep), content-type gate, final-URL storage, `<title>`
      extraction, `to_markdown` gate, per-URL failure skip; failed URLs omitted
      (T-M3-06; FR-010..016)
- [X] T010 [P] [US2] Create `src/memagent/nodes/search.py`: `make_web_search(resources)` —
      search `sanitized_query` with `SEARCH_MAX_RESULTS`, write `search_results` +
      `search_provider` (via `getattr(searcher, "provider_used", None)`), never raise
      (exception ⇒ `search_results=[]` + StepError), latency entry
      (T-M3-07; FR-004, FR-005 wiring; contracts/web-search.md)
- [X] T011 [P] [US2] Create `src/memagent/nodes/fetch.py`: `make_fetch_pages(resources)` —
      `filter_urls` → first `FETCH_TOP_N` → `fetcher.fetch`, write `fetched_docs`, never
      raise (T-M3-08; FR-009..016 wiring; contracts/fetch-and-markdown.md)

**Checkpoint**: acquisition layer complete and independently exercisable

---

## Phase 4: User Story 3 — Learned content is stored durably, freshly, tolerantly (Priority: P3)

**Goal**: the `ingest_content` node — sanitize → summarize → chunk → embed → store with
freshness/skip gates and failure tolerance. All three tasks edit the SAME file:
sequential, no [P] (source keeps 09a/b/c sequential to keep the riskiest node honest).

**Independent Test**: with Redis up and free-tier keys, a hand-built `FetchedDoc` run
through the node stores `chunk:{h}:0..N` + `chunk:{h}:summary` + `doc:{h}` with all five
metadata fields; re-run within 24 h stores nothing; forced summary/store failures still
emit chunks in state.

- [X] T012 [US3] Create `src/memagent/nodes/ingest.py`: `make_ingest_content(resources)`
      core path per page — `sanitize(markdown)` FIRST, summary via
      `analytics_llm.complete(SUMMARY_SYSTEM, [user: clean[:SUMMARY_INPUT_CHARS]])`
      (5–8 sentences, `SUMMARY_INPUT_CHARS=6000`), `chunk_markdown(clean)` → wrap into
      `Chunk` records (`chunk_id=f"{h}:{i}"`), ONE embed batch
      `([summary] if summary else []) + chunk_texts` (M2 vector-alignment), store via
      `memory.store(page=doc_with_summary, chunks, vectors, source_query=state["query"],
      flags)`; emit enriched `fetched_docs` + `chunks` + `stored_chunk_ids`
      (T-M3-09a; FR-021, FR-022, FR-023; contracts/ingest-and-sanitize.md)
- [X] T013 [US3] Add gating to `src/memagent/nodes/ingest.py`: freshness gate —
      `h = url_hash(canonicalize(doc["url"]))`, `await memory.is_fresh(h)` ⇒ skip
      summary/embed/store for that page, but **chunking still runs** so the page's first
      chunks serve the in-hand answer (analyze I2); `skip_store`
      honoured — zero Redis writes, `stored_chunk_ids=[]`, summaries + chunks still
      populated (T-M3-09b; FR-024, FR-025; Ruling G)
- [X] T014 [US3] Add failure tolerance to `src/memagent/nodes/ingest.py`: summary
      exception ⇒ `summary=None`, chunk sanitized markdown, no summary doc, continue;
      store exception ⇒ caught + StepError appended, answer never depends on
      persistence, turn NEVER routed `failed` by storage (T-M3-09c; FR-026, FR-027)

**Checkpoint**: ingestion complete — memory grows on misses without ever harming answers

---

## Phase 5: User Story 4 — Miss branch wired for real; answers grounded and bounded (Priority: P4)

**Goal**: `answer_from_web`, real resources, the graph rewire (Ruling B), and the
canonical CLI miss banner.

**Independent Test**: quickstart §1 — imports clean, forbidden-import grep empty, mermaid
shows `web_search → fetch_pages → ingest_content → answer_from_web` with the temp edge
gone.

- [X] T015 [P] [US4] Add `answer_from_web` (+ `make_answer_from_web(resources)`) to
      `src/memagent/nodes/answer.py`: bounded context — per page summary (omit line if
      None) + first `WEB_CONTEXT_CHUNKS_PER_PAGE=2` chunks by `chunk_index`; wrap with
      `wrap_context(sources, origin="web")`; normal path `route="memory_miss_web_search"`
      + deduped `origin="web"` sources + "Sources:" ending (reuse M2 append pattern);
      snippets-only path (`fetched_docs==[]`) → `LOW_CONFIDENCE_DISCLAIMER` prepended,
      `route="degraded_web"`, `degradation="snippets_only"`; ZERO memory/Redis reads;
      chat-LLM failure ⇒ `route="failed"` + FAILURE_APOLOGY
      (T-M3-10; FR-028..031; contracts/answer-and-graph.md)
- [X] T016 [P] [US4] Edit `src/memagent/app.py` `build_resources()`: construct
      `FallbackProvider(settings)` + `HttpxPageFetcher(settings)` into `AgentResources`;
      delete `_NoopSearcher`/`_NoopFetcher`; KEEP `_NoopTurnLogger` (M4's); no call-site
      changes (T-M3-11; contracts/answer-and-graph.md)
- [X] T017 [US4] Edit `src/memagent/graph.py`: add the four web nodes; remap
      `route_after_memory`'s `"web_search"` path from `answer_failure` to the real
      `web_search` node (remove the TEMPORARY comment + edge); add conditional edges for
      `route_after_search` / `route_after_fetch`; `ingest_content → answer_from_web →
      log_turn`; entry stays `embed_query` (T-M3-12; FR-032; Rulings B, F)
- [X] T018 [P] [US4] Edit `src/memagent/cli.py` `ask`: miss branch prints canonical
      `[MEMORY MISS → searching the web]` (replace bare `[MEMORY MISS]` + its temporary
      comment) and lists sources on BOTH outcomes — `(web) {title} <{url}>` on miss,
      `(memory)` on hit (unchanged); hit banner + error guards untouched
      (§6.13a; FR-033)
- [X] T019 [US4] Structural verification (quickstart §1): module imports exit 0;
      `! grep -rn "tavily-python\|import tavily\|markdownify" src/` empty;
      `OPENAI_API_KEY=dummy` mermaid render shows all four web nodes on the miss path
      and NO `memory_search → answer_failure` edge; `uv run ruff check src tests` clean
      (T-M3-12 verify; FR-032; DoD items 1–4, 6)

**Checkpoint**: the graph is whole — every M3-active route reachable, structure provable

---

## Phase 6: User Story 1 — Novel question from the web; re-ask from memory (Priority: P1) 🎯 the graded outcome

**Goal**: the live miss→ingest→hit lifecycle, captured as the first demo transcript.

**Independent Test**: quickstart §3 verbatim — this IS the milestone's demoable outcome
(PLAN §13).

- [X] T020 [US1] Run the live lifecycle (quickstart §3): `uv run memagent wipe-memory`;
      `uv run memagent ask "<novel question>"` → `[MEMORY MISS → searching the web]` +
      web Sources (structlog `provider_used="tavily"`); identical verbatim re-ask →
      `[MEMORY HIT sim=0.XX]` ≥ 0.70 + `(memory)` sources + zero web calls; inspect
      Redis: `chunk:{h}:0..N`, `chunk:{h}:summary`, `doc:{h}` present with TTL
      (T-M3-13; FR-029, FR-031, SC-001, SC-006; DoD items 7–8)
- [X] T021 [US1] Capture the two-turn session verbatim into `docs/demo_transcript.md`
      (command lines + full output, provider noted) (T-M3-13; FR-034; DoD item 9)

**Checkpoint**: SC-001 proven live and recorded — the assignment's core behavior works

---

## Phase 7: Polish & Definition of Done

**Purpose**: disclosure, lint/suite green, DoD sweep, publish

- [X] T022 [P] Write `docs/ai_prompts/milestone-3.md`: complete dated M3 instruction
      record (specify→clarify→plan→tasks→analyze→implement prompts + the Tavily
      key/probe and ddgs/trafilatura verification records) (T-M3-14; FR-035; P-VII)
- [X] T023 [P] Update `AI_USAGE.md`: §3 provenance rows for `web/`, `security/sanitizer`,
      new nodes, graph/app/cli edits; §5 link to `docs/ai_prompts/milestone-3.md`
      (T-M3-14; FR-035)
- [X] T024 Full-suite gate: `uv run ruff check src tests` and `make test` green (keyless
      — the M3 web code must not break M1/M2's 28+ tests); fix anything that fails
      (DoD items 5–6; SC-007)
- [X] T025 Close the milestone: commit on `m3-web-pipeline` with the repo-local identity,
      push, verify CI green on the branch, merge to `main`, verify CI green on main
      (constitution P-VIII; SC-007)

---

## Dependencies & Execution Order

- **Setup (T001)** → everything.
- **Foundational**: T002, T003 [P] with each other → required by Phase 4+ (T002/T003)
  and consumed by T012/T013.
- **US2 (T004–T011)**: T004∥T005∥T006∥T008 start together ([P] where marked); T007 after
  T006 (same file); T009 after T008 (same file) and after T004 (calls `to_markdown`);
  T010∥T011 after their modules (T007, T009).
- **US3 (T012–T014)**: after T002, T003, T007, T009 (consumes sanitize/is_fresh/docs);
  strictly sequential — one file.
- **US4 (T015–T018)**: T015∥T016∥T018 in parallel; T017 after T010, T011, T014, T015
  (imports all four node factories) and after T016 (resources feed compile check);
  T019 after T017 + T018.
- **US1 (T020–T021)**: after T019 — needs the whole pipeline live. T021 after T020.
- **Polish**: T022∥T023 anytime after T020; T024 after all code tasks; T025 last.

## Parallel Example: fastest start after T003

```text
Lane A: T004 to_markdown → T009 fetcher ─┐
Lane B: T006 Tavily → T007 fallback ─────┼→ T010∥T11 nodes → T012→T013→T014 ingest ─┐
Lane C: T008 filter_urls ────────────────┘                                          ├→ T017 → T019 → T020 → T021
Lane D: T005 test_to_markdown ∥ T015 answer_from_web ∥ T016 app.py ∥ T018 cli.py ───┘
```

## Implementation Strategy

Build order is dependency-first (US2 → US3 → US4), but the **MVP scope is US1** — the
milestone is done when the two-turn lifecycle runs live and is captured. If time-boxed:
T005 (the optional test file) is the only droppable task (spec marks it OPTIONAL); every
other task is on the DoD critical path. No stopping point before T020 yields a
demonstrable milestone — this phase's stories integrate rather than stand alone, which is
why US1 closes the sequence.
