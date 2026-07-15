# Feature Specification: Milestone 2 — Memory Path (Embeddings, Store, Threshold Routing, Graph Skeleton)

**Feature Branch**: `002-m2-memory-path`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "for Milestone 2, feeding it specs/milestone-2-memory-path.md"

> **Source of truth**: this spec restates `specs/milestone-2-memory-path.md` (§1/2/5/7 per its
> §11 Spec Kit mapping). That file's §6 Technical specification feeds `/speckit-plan`; its
> §8/9 feed `/speckit-tasks`. On any conflict, `PLAN.md` wins (Constitution, Principle VI).
> Depends on Milestone 1 (closed 2026-07-05: repo scaffold, `Settings`, `web_memory` index,
> functional `wipe-memory`, green CI on the public repo).

## Clarifications

### Session 2026-07-05

- Q: Which credentials power M2's live work (seeding, hit demo, FR-025 verification)? →
  A: Option A — **GitHub Models free dev mode** for all M2 live calls: `OPENAI_BASE_URL`
  points at the GitHub Models endpoint with a **fine-grained GitHub PAT carrying the
  `models: read` permission** as the key. $0 cost; FR-025's catalogue + `temperature=0`
  verification is satisfied through the same configuration. The real `OPENAI_API_KEY`
  enters only at M6 for the recorded demo ("develop free, demo on the real key",
  PLAN §6).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A seeded question is answered from memory, with visible proof (Priority: P1)

After seeding the memory with a document, a user asks a question about it and receives an
answer produced **from memory only** — the terminal shows a `[MEMORY HIT sim=0.XX]` banner
with the measured similarity, the answer text, a closing "Sources:" section, and the stored
source metadata (URL and title). An unrelated question takes the (temporary) miss path and
returns a deterministic response instead of crashing.

**Why this priority**: this is the assignment's core graded behavior — "embed the query,
vector-search Redis first; similarity ≥ 0.7 → answer from memory only, with stored
metadata." M2 exists to make this demonstrable end-to-end.

**Independent Test**: run the seed script with a text + URL, then `memagent ask` the same
topic → hit banner with similarity ≥ 0.70 and the seeded URL; ask something unrelated →
miss banner + deterministic response. (PLAN §13 M2 demoable outcome.)

**Acceptance Scenarios**:

1. **Given** a document seeded into memory, **When** the user asks a question about that
   document, **Then** the reply shows `[MEMORY HIT sim=0.XX]` with similarity ≥ 0.70, an
   answer grounded in the stored text, a "Sources:" section, and the seeded URL + title.
2. **Given** an empty or unrelated memory, **When** the user asks a question, **Then** a
   `[MEMORY MISS]` banner appears followed by a deterministic response (the temporary miss
   path — the web pipeline arrives in M3), and the process exits cleanly.
3. **Given** a memory hit with several matching fragments from the same page, **When** the
   answer is produced, **Then** the sources list contains that page **once** (deduplicated
   by URL) and every source is marked as coming from memory.
4. **Given** the embedding service fails, **When** the user asks a question, **Then** the
   turn ends with a deterministic apology (route "failed"), no answer model is called, and
   nothing crashes.
5. **Given** the hit banner, **When** similarity is displayed, **Then** it is formatted to
   two decimals (e.g. `sim=0.87`).

---

### User Story 2 - The 0.70 threshold contract is provable, not approximate (Priority: P2)

A reviewer can verify — from automated tests alone — that the hit/miss decision is a pure,
deterministic threshold rule: similarity **exactly** 0.70 is a hit (inclusive), 0.6999 is a
miss, an empty memory is a miss, and the similarity number itself comes from exactly one
conversion site (`similarity = 1 − distance`, never the halved variant).

**Why this priority**: the memory-first contract is only trustworthy if the boundary is
exact and the conversion is single-sourced — this is the #1 correctness trap named in the
plan and the constitution (P-I, P-II).

**Independent Test**: the routing and similarity unit tests pass keyless and without Docker;
the boundary table (0.70 → hit, 0.6999 → miss, None → miss, 1.0 → hit, 0.0 → miss) is
asserted verbatim.

**Acceptance Scenarios**:

1. **Given** a top similarity of exactly 0.70 and a threshold of 0.70, **When** routing
   runs, **Then** the turn is a memory hit (inclusive boundary).
2. **Given** a top similarity of 0.6999, **When** routing runs, **Then** the turn is a miss.
3. **Given** no memory results at all, **When** routing runs, **Then** the turn is a miss
   (never an error).
4. **Given** a stored distance of 0.30, **When** it is converted, **Then** similarity is
   0.70 and routes as a hit; the halved formula (1 − d/2) appears nowhere.
5. **Given** all five routing functions, **When** called twice with identical inputs,
   **Then** they return identical outputs and perform no I/O (pure).
6. **Given** float32 storage noise (a true 0.70 read back as 0.699999988), **When** the
   boundary test runs, **Then** the documented epsilon decision holds (comparison stays
   `>= threshold`; the epsilon variant is adopted only if the test proves flaky, and the
   decision is recorded once).

---

### User Story 3 - Memory foundations behave correctly under storage realities (Priority: P3)

The building blocks the answer path stands on are individually correct: nearest-neighbor
lookup returns the raw top-5 with similarity attached (no hidden filtering), stored content
expires after the configured retention (7 days by default, disable-able), re-storing a page
cleans up its previous fragments, recently fetched pages are recognized as fresh, long
documents are split into bounded overlapping chunks without corruption, and URL variants
(tracking parameters, fragments, case) collapse to one canonical identity.

**Why this priority**: every later milestone (web ingestion in M3, analytics in M4,
security provenance in M5) writes through or reads from these primitives; defects here
surface as wrong routing or stale citations later.

**Independent Test**: the chunker unit tests pass keyless; store/freshness/URL behaviors are
verifiable against the local memory store per the source file's §7 scenarios.

**Acceptance Scenarios**:

1. **Given** a seeded memory and a query vector, **When** the top-5 lookup runs, **Then**
   results arrive ordered by descending similarity with the nearest first, unfiltered by
   any threshold; **Given** an empty memory, **Then** the result is an empty list, not an
   error.
2. **Given** default retention, **When** content is stored, **Then** each stored fragment
   carries a positive expiry ≤ 7 days; **Given** retention configured to 0, **Then** no
   expiry is set.
3. **Given** a page already stored with 5 fragments, **When** it is re-stored with 3,
   **Then** no stale fragments beyond the new count remain.
4. **Given** a page fetched 1 hour ago, **Then** it is considered fresh; 48 hours ago or
   never seen → not fresh.
5. **Given** a long markdown document, **When** chunked, **Then** every chunk respects the
   1600-character size and 200-character overlap bounds, chunks under 100 characters are
   dropped, at most 25 chunks are produced per page, no chunk is empty, and non-Latin text
   survives uncorrupted.
6. **Given** `HTTP://Example.com/a?utm_source=x#frag` and `http://example.com/a`, **When**
   canonicalized, **Then** both produce the same canonical URL and the same 16-character
   identity hash.
7. **Given** the embedding client, **Then** it reports 1536 dimensions and returns one
   vector per input in order; **Given** the chat client, **Then** an answer call returns
   text plus a usage record (model, input tokens, output tokens).

---

### User Story 4 - The structural spine is in place for every later milestone (Priority: P4)

The typed state, the dependency-injection contracts, the frozen resources container, the
compiled graph with its temporary stubs, and the answer facade all exist with their public
shapes fixed — so M3–M5 drop their pieces in without changing any call site. The free
development mode is verified live (catalogue ids resolve; deterministic `temperature=0`
accepted), and the milestone's complete prompt log is appended to the disclosure record.

**Why this priority**: this is scaffolding-for-others rather than user-visible behavior,
but the seams it fixes are load-bearing contracts (constitution workflow gates).

**Independent Test**: the canonical types import cleanly and the route vocabulary is the
closed 5-value set; the graph compiles and renders a diagram; the resources container is
immutable; the two live verification calls are recorded.

**Acceptance Scenarios**:

1. **Given** the canonical state module, **When** imported, **Then** all record types
   resolve and the route vocabulary is exactly the closed set {memory_hit,
   memory_miss_web_search, degraded_web, blocked, failed}.
2. **Given** the resources container, **When** any field is assigned after construction,
   **Then** it refuses (immutable).
3. **Given** the compiled graph, **Then** it renders a non-empty auto-generated diagram,
   the hit path runs end-to-end through the no-op turn-log stub, and the miss branch
   temporarily terminates in the deterministic failure response (replaced by the web path
   in M3).
4. **Given** the answer facade, **When** a question is asked, **Then** the conversation
   history passed to the graph is empty (per-turn statelessness; session history is M4).
5. **Given** free-dev credentials, **When** the catalogue verification runs, **Then** the
   three needed model ids resolve and `temperature=0` is accepted by the conversation
   model — both results recorded in the disclosure log with pass/fail.
6. **Given** the milestone closes, **Then** a dated M2 prompt-log file exists and
   `AI_USAGE.md` references it (appended, never retroactive).

---

### Edge Cases

- Empty memory index → normal miss (empty result list), never an exception (US3-1, US1-2).
- Embedding failure mid-turn → deterministic apology, route "failed", zero answer-model
  calls, error recorded; the turn never falls through to the web (deferred-by-design:
  embeddings and the answer model share one provider).
- Similarity exactly at the boundary (0.70) → hit; float32 noise handling documented once.
- Duplicate-URL memory hits → deduplicated sources list.
- Retention set to 0 → stored content never expires (explicit "disable" semantics).
- Re-store with fewer fragments → stale keys removed via the stored fragment count.
- Very short document → at most one chunk (or none if under the 100-char floor).
- Malformed state reaching the failure responder → still answers deterministically, never
  raises.
- The deterministic failure responder makes **no** model call (verified by an injected
  counting fake).

## Requirements *(mandatory)*

### Functional Requirements

Traceability: FR-001…FR-026 map 1:1 to FR-M2-01…FR-M2-26 in
`specs/milestone-2-memory-path.md` §5, which carries the full acceptance criterion for each.

- **FR-001**: The canonical state module MUST define the typed agent state and record types
  (memory hit, search result, fetched document, chunk, source reference, step error) plus
  the two turn-bookkeeping channels (turn start time, search provider) (source: FR-M2-01).
- **FR-002**: The route vocabulary MUST be the closed 5-value set — memory_hit,
  memory_miss_web_search, degraded_web, blocked, failed (source: FR-M2-02).
- **FR-003**: The dependency-injection contracts MUST be defined verbatim, with the memory
  lookup contractually returning **raw unfiltered top-k** (no threshold parameter exists)
  (source: FR-M2-03).
- **FR-004**: The resources container MUST be immutable after construction
  (source: FR-M2-04).
- **FR-005**: All five routing functions MUST be pure (no I/O, deterministic) and delivered
  now, including the three that only activate in later milestones (source: FR-M2-05).
- **FR-006**: Memory routing MUST be hit iff top similarity is present and ≥ the threshold
  (inclusive), else miss — proven at the 0.70/0.6999/None/1.0/0.0 boundary table
  (source: FR-M2-06).
- **FR-007**: The distance→similarity conversion MUST be `1 − distance` (never `1 − d/2`)
  and live at exactly one site, called inside the lookup (source: FR-M2-07).
- **FR-008**: The embedding client MUST report 1536 dimensions, disable SDK-level retries,
  honor the optional alternate endpoint, and return one ordered vector per input
  (source: FR-M2-08).
- **FR-009**: The chat client MUST return answer text plus a usage record (model, input
  tokens, output tokens) (source: FR-M2-09).
- **FR-010**: The memory lookup MUST return up to top-5 results ordered by descending
  similarity with similarity attached; an empty index yields an empty list
  (source: FR-M2-10).
- **FR-011**: Storing a page MUST write its fragments (and optional summary) under the
  page's identity, plus a non-indexed page record, applying the configured expiry to each
  fragment (0 disables) (source: FR-M2-11).
- **FR-012**: Re-storing an existing page MUST first remove its previous fragments using
  the stored fragment count (source: FR-M2-12).
- **FR-013**: A freshness helper MUST report pages fetched within the freshness window as
  fresh; stale or unknown pages as not fresh (source: FR-M2-13).
- **FR-014**: Chunking MUST respect size 1600 / overlap 200, drop fragments under 100
  characters, cap at 25 per page, never emit empty fragments, and preserve non-Latin text
  (source: FR-M2-14).
- **FR-015**: URL canonicalization MUST lowercase scheme/host and strip fragments and
  tracking parameters; the identity hash is the first 16 hex characters of the canonical
  URL's digest (source: FR-M2-15).
- **FR-016**: The query-embedding step MUST set the query vector on success and, on
  failure, clear it and record the error so routing ends the turn in the deterministic
  failure response (source: FR-M2-16).
- **FR-017**: The memory-search step MUST attach the raw results and the highest
  similarity (or none when empty) and MUST NOT apply the threshold itself
  (source: FR-M2-17).
- **FR-018**: The memory-answer step MUST answer only from the retrieved memory content
  (wrapped as untrusted data), mark the route as a memory hit, deduplicate sources by URL,
  and end the answer with a "Sources:" section (source: FR-M2-18).
- **FR-019**: The failure responder MUST produce a fixed apology, make no model call, and
  never raise — even on malformed state (source: FR-M2-19).
- **FR-020**: The prompt module MUST expose its two functions with signatures fixed now
  (including the origin argument); the system prompt declares wrapped content
  data-not-instructions and requires the "Sources:" ending (source: FR-M2-20).
- **FR-021**: The compiled graph MUST run the hit path end-to-end (entry: query embedding;
  temporary no-op turn log; temporary miss→failure edge) and render a non-empty
  auto-generated diagram (source: FR-M2-21).
- **FR-022**: The answer facade MUST build the initial turn state (fresh turn id, empty
  history, threshold from settings, allow verdict, query mirrored as sanitized query) and
  return route, answer, sources, and similarity (source: FR-M2-22).
- **FR-023**: The seed script MUST take a text (or file) plus URL and store it so an
  equivalent question becomes a memory hit (source: FR-M2-23).
- **FR-024**: The ask command MUST print the hit banner with two-decimal similarity and
  stored URL + title on hits, and the miss banner with a deterministic response on misses
  (source: FR-M2-24).
- **FR-025**: One live call MUST confirm the free-dev catalogue ids resolve and one MUST
  confirm the conversation model accepts deterministic output (temperature 0) — both
  recorded with pass/fail; id corrections land in the configuration defaults
  (source: FR-M2-25).
- **FR-026**: The M2 prompt log MUST be appended (dated, never retroactive) and referenced
  from the disclosure index (source: FR-M2-26).

### Key Entities

- **Agent state**: the typed per-turn record every step reads/writes — query, history
  (empty in M2), threshold, guard verdict (defaults to allow), query vector, memory hits,
  top similarity, route, answer, sources, errors, latency, tokens, plus turn bookkeeping.
- **Memory hit**: one retrieved fragment — text, URL, title, similarity (converted once),
  stored-at timestamp, provenance flags, and document kind (fragment vs summary).
- **Turn result**: what the facade returns — route, answer, sources, similarity.
- **Resources container**: the immutable set of collaborators (settings, memory store,
  embedder, chat + analytics clients, searcher/fetcher/turn-logger stubs) injected into
  the graph; stubs are replaced by M3/M4 without call-site changes.
- **Seeded document**: text + URL stored by the seed script — the demo's ground truth.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After seeding one document, asking an equivalent question answers **from
  memory only** with displayed similarity ≥ 0.70, the seeded source cited, and a
  "Sources:" ending — reproducibly, run after run.
- **SC-002**: The boundary is exact and machine-verified: similarity 0.70 routes as a hit,
  0.6999 as a miss, empty memory as a miss — 100% of the boundary table passes in
  automated tests.
- **SC-003**: All M2 unit tests pass with zero keys and zero Docker; the repository's CI
  stays green on every push.
- **SC-004**: An unseeded question completes cleanly in under the answer path's normal
  time with a deterministic miss response — zero crashes across repeated runs.
- **SC-005**: The two live free-dev verifications (catalogue ids; deterministic output)
  are executed and their pass/fail results recorded in the disclosure log.
- **SC-006**: A dated M2 prompt-log entry exists and is referenced from the disclosure
  index before Milestone 3 starts.

## Assumptions

- Milestone 1 artifacts are in place and green (verified 2026-07-05): `Settings`,
  `web_memory` index + `wipe-memory`, docker-compose redis:8.2, CI on the public repo.
- All M2 live calls (seed script, hit demo, FR-025 verification) run on the **GitHub
  Models free tier** via `OPENAI_BASE_URL` (per Clarifications, Session 2026-07-05); unit
  tests need no credentials at all. The user provides a fine-grained GitHub PAT with the
  `models: read` permission before the live-demo tasks run (the existing classic PAT does
  not carry that permission). Free-tier daily rate limits are acceptable for development;
  the real `OPENAI_API_KEY` is deferred to M6's recorded demo. If GitHub Models serves
  different catalogue id strings (e.g. `openai/gpt-5.4-mini`), the dev-mode configuration
  records them without changing the production defaults in `Settings`.
- Seed content for the demo is any suitable public text/URL chosen at implementation time
  (the seed script takes both as arguments — no fixed corpus is mandated).
- `specs/milestone-2-memory-path.md` §6 carries the full technical detail (verbatim state
  block, store/KNN bodies, prompt templates, node functions) and is the direct input to
  `/speckit-plan`; this spec stays at capability level. The stack is locked by the
  constitution; naming it here is traceability, not an open choice.
- No `[NEEDS CLARIFICATION]` markers: scope, seams, and acceptance criteria are fully
  determined by the source milestone file, the orchestrator rulings, and PLAN.md.
