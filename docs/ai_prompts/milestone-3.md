# Milestone 3 — Complete instruction record (appended 2026-07-05)

Chronological log of every instruction that drove Milestone 3 (web pipeline: search,
fetch, markdown, summarize, ingest), per the disclosure rule in `AI_USAGE.md`
(Constitution P-VII: appended per milestone, never retroactively). Tooling: Claude Code
(Fable 5) + GitHub Spec Kit at the planning workspace root; the milestone source spec is
`specs/milestone-3-web-pipeline.md` (from the 6-file spec-authoring workflow logged in
milestone-1.md).

## 1. Spec Kit phase prompts (user-issued, verbatim)

1. `/speckit-specify for Milestone 3, feeding it specs/milestone-3-web-pipeline.md`
   → produced `specs/003-m3-web-pipeline/spec.md` (35 FRs; FR-001…032 ↔ FR-M3-01…32,
   +FR-033 CLI banner, +FR-034 demo transcript, +FR-035 this log) and a 16-item quality
   checklist (all passing).
2. `/speckit-clarify` → ONE question asked: obtain a Tavily key for M3, or run keyless
   ddgs? **User answer: "A" + pasted a free-tier Tavily API key in chat.** Recorded in
   spec Clarifications (Session 2026-07-05); the key went ONLY into the git-ignored
   `.env` and was live-probe-verified (below). Advice on record: revoke the key when the
   project ends (it appeared in the chat transcript).
3. `/speckit-plan` → plan.md (11-gate Constitution Check, all PASS), research.md
   (D1–D10), data-model.md, contracts/ (web-search, fetch-and-markdown,
   ingest-and-sanitize, answer-and-graph), quickstart.md.
4. `/speckit-tasks` → tasks.md, 25 tasks in 7 phases; story phases dependency-ordered
   (US2 acquisition → US3 ingest → US4 wiring → US1 lifecycle capstone).
5. `/speckit-analyze` → 3 findings (I1 HIGH, I2 MEDIUM, U1 LOW; details §3). User:
   **"yes apply the fixes"** → all three remediated across tasks/contracts/plan/
   research/data-model/quickstart before implementation.
6. `/speckit-implement` → executed all 25 tasks (this session).

## 2. Live verification records (Constitution P-IX — evidence with dates)

| Check | Command / method | Result (2026-07-05) |
|---|---|---|
| Tavily key + request shape | raw `curl POST https://api.tavily.com/search` (bearer, `include_raw_content:false`, `max_results:2`) | HTTP 200; result fields `['content','raw_content','score','title','url']` → `snippet` maps from **`content`**; `raw_content` null as requested |
| ddgs keyless + field names | `DDGS().text("redis vector search", max_results=2)` on installed ddgs 9.14.4 | 2 rows, keys exactly `['body','href','title']` → mapping `title/href/body → title/url/snippet` |
| trafilatura kwargs | `inspect.signature(trafilatura.extract)` on installed 2.1.0 | all five kwargs present (`output_format`, `include_tables`, `include_links`, `favor_precision`, `favor_recall`) |
| Freshness helper | read `RedisMemoryStore.is_fresh` source | signature is `is_fresh(self, h: str)` — **hash**-keyed, not URL-keyed (store.py:140) |
| Dependency pins | `uv pip list` | httpx 0.28.1, trafilatura 2.1.0, ddgs 9.14.4, structlog 26.1.0 — all landed in M1; zero new pins for M3 |

## 3. Analyze findings and their fixes (user-approved)

- **I1 (HIGH)**: M2's placeholder `PageFetcher` Protocol took `results: list[SearchResult]`
  while the M3 design fixes `fetch(urls: list[str])` — and no task updated the Protocol.
  Fix: T003 extended to replace the placeholder signature (pre-authorized by its own
  "M3 fleshes this out" docstring); recorded in research D4 + plan post-check.
- **I2 (MEDIUM)**: the ingest contract's freshness gate said "skip steps 3–6", which
  would skip *chunking* — a fresh page would contribute nothing to the answer context.
  Fix: gate skips summary/embed/store only; **chunking always runs**.
- **U1 (LOW)**: quickstart's negative mermaid assert could pass vacuously; replaced with
  positive node assertions + a mandated eyeball of the printed diagram.

## 4. Implementation session (what was built, in task order)

Branch `m3-web-pipeline` from green main. T002–T003 seams (sanitizer pass-through stub;
`is_fresh` + `PageFetcher` Protocol edits) → T004–T011 acquisition (`web/to_markdown.py`,
`tests/unit/test_to_markdown.py` 8 tests, `web/search.py` TavilySearcher/DdgsSearcher/
FallbackProvider, `web/fetch.py` filter_urls/HttpxPageFetcher, `nodes/search.py`,
`nodes/fetch.py`) → T012–T014 `nodes/ingest.py` (sanitize→summary→chunk→embed→store;
freshness + skip_store gates; summary/store failure tolerance) → T015–T019 wiring
(`answer_from_web` in nodes/answer.py, real resources in app.py, graph rewire removing
the M2 temporary miss edge, canonical CLI banner, structural verification) → T020–T021
live lifecycle + `docs/demo_transcript.md` → this log + AI_USAGE + full suite + publish.

Verifications executed for real: imports clean; forbidden-import grep empty (after
rewording a docstring that itself contained the banned package name — the grep guards
code AND comments); ruff clean; 36/36 tests green (28 prior + 8 new); mermaid diagram
eyeballed (miss path `memory_search → web_search → fetch_pages → ingest_content →
answer_from_web → log_turn`; `answer_failure` reachable only from embed/search);
14-URL unsafe filter table all dropped, diversity + order preserved.

## 5. Hand-caught finding during live verification (and its fix)

Inspecting Redis after the first live lifecycle showed **7 `doc:*` meta keys** — more
than the turn's fetched pages. Root cause: `wipe_index` (M1) drops the index and its
indexed `chunk:*` keys, but the deliberately NON-indexed `doc:{url_hash}` metas
survive. Harmless in M1/M2 — but M3's freshness gate reads `doc:{h}.fetched_at`, so a
wipe followed by re-asking within 24 h would *silently skip re-ingestion* of
previously-seen URLs (memory stays empty for them; the wipe→miss→ingest→hit demo would
break). Fix: `wipe_index` now also scans and deletes `doc:*` (schema.py; CLI call site
unchanged). Verified live: post-wipe `doc:*` count is 0, and the demo transcript was
recaptured from a genuinely clean slate.

## 5a. Manual test session findings (user request: "test it like if i test it manually", 2026-07-05)

A full hands-on session was run after the DoD closed. Two findings:

- **BUG (fixed)**: `ask` with Redis down printed a 372-line typer pretty-traceback
  (leaking turn locals) instead of the CLI's promised one-line readable error —
  redisvl wraps the connection failure in `RedisSearchError`, which the `_REDIS_DOWN`
  tuple didn't cover (M2 only ever live-tested redis-down on `wipe-memory`, which hits
  redis directly). Fix: cause-chain walk in cli.py (`_redis_down_in_chain`) — verified:
  one line, exit 1.
- **CALIBRATION (documented, not a bug)**: a verbatim re-ask is NOT guaranteed to hit —
  it hits iff the stored content scores ≥ 0.70 against the query. Measured live:
  "How does Redis 8 vector search work?" → re-ask HIT at 0.74; "What is the trafilatura
  Python library used for?" → re-ask MISS at top similarity 0.692 (re-searched; the
  freshness gate correctly stored nothing — `fetched_at` unchanged). The
  `SIMILARITY_THRESHOLD=0.65` lever flips the second case to `[MEMORY HIT sim=0.69]`.
  The milestone source's "a verbatim re-ask hits" (§10) is topic-dependent in practice.

Also proven in the session: blank `TAVILY_API_KEY` → `provider_used=ddgs`; bogus key →
`tavily_failed error=HTTPStatusError` warning then ddgs (no retry); `FETCH_MAX_BYTES=1`
→ all pages skipped → snippets-only degraded answer with the low-confidence disclaimer;
missing `OPENAI_API_KEY` → readable guard line.

## 6. Live lifecycle result (the milestone's demoable outcome)

`docs/demo_transcript.md` (captured 2026-07-05): turn 1 `[MEMORY MISS → searching the
web]` with `provider_used=tavily`, grounded answer + "Sources:" + 4 `(web)` sources;
turn 2 (verbatim re-ask) `[MEMORY HIT sim=0.74]` from memory only — no web log lines —
with `(memory)` sources. Storage after turn 1: `chunk:{h}:0..N` + `chunk:{h}:summary`
(4 summary docs) + `doc:{h}` per page, ~7-day TTLs. Calibration note: 0.74 satisfies the
≥ 0.70 contract; the source file's `sim=0.9x` illustration was optimistic for
query-vs-summary embeddings (consistent with M2's measured 0.74–0.84 range).
