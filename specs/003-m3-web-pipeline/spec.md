# Feature Specification: Milestone 3 — Web Pipeline (Search, Fetch, Markdown, Summarize, Ingest)

**Feature Branch**: `003-m3-web-pipeline`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "for Milestone 3, feeding it specs/milestone-3-web-pipeline.md"

> **Source of truth**: this spec restates `specs/milestone-3-web-pipeline.md` (§1/2/5/7 per its
> §11 Spec Kit mapping). That file's §3/4/6/10 feed `/speckit-plan`; its §8/9 feed
> `/speckit-tasks`. On any conflict, `PLAN.md` wins (Constitution, Principle VI).
> Depends on Milestone 1 (closed 2026-07-05) and Milestone 2 (closed 2026-07-05: memory
> path live, threshold routing proven, graph skeleton with the temporary miss edge this
> milestone replaces).

## Clarifications

### Session 2026-07-05

- Q: Will you obtain a Tavily API key for M3, or should all M3 live searches run on the
  keyless DuckDuckGo (ddgs) fallback? → A: Option A — a **free-tier Tavily API key is
  provided** for M3. Live searches, including the recorded demo transcript, run on the
  primary provider; keyless ddgs remains the built-and-tested fallback. The key lives
  only in the git-ignored `.env` and is never committed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A novel question is answered from the live web, and its re-ask is answered from memory (Priority: P1)

A user asks a question the memory has never seen. The agent announces
`[MEMORY MISS → searching the web]`, searches the web, fetches the top result pages,
converts them to readable text, summarizes and stores what it learned, and answers with
source URLs marked as coming from the web. The user then asks the **identical** question
again: this time the reply is `[MEMORY HIT sim=0.XX]` answered **from memory only**, with
memory-marked sources and **no web activity at all**. The two-turn session is captured as
the project's first demo transcript.

**Why this priority**: this is the core thing the assignment grades — "miss → web search,
fetch top pages, convert to markdown, summarise, store chunks & metadata, answer; next
equivalent question is a hit." M3 exists to make that lifecycle demonstrable end to end.

**Independent Test**: wipe memory, ask a novel question → miss banner + web sources; ask
the same question verbatim → hit banner (similarity ≥ 0.70) + memory sources, zero web
calls on turn 2. (PLAN §13 M3 demoable outcome.)

**Acceptance Scenarios**:

1. **Given** an empty memory and a novel question, **When** the user asks it, **Then** the
   reply shows `[MEMORY MISS → searching the web]`, an answer grounded in fetched pages
   ending with a "Sources:" section, and every listed source marked `(web)` with its URL.
2. **Given** the same question asked a second time verbatim, **When** the turn completes,
   **Then** the reply shows `[MEMORY HIT sim=0.XX]` with similarity ≥ 0.70, sources marked
   `(memory)`, and the web search/fetch machinery is not invoked at all.
3. **Given** the first (miss) turn completed, **When** stored memory is inspected, **Then**
   the fetched pages' fragments and one summary record per page exist, each carrying the
   page URL, title, fetch time, the originating query, and sanitizer provenance flags.
4. **Given** both search providers return nothing, **When** the turn completes, **Then**
   the user receives the deterministic failure response (no crash, clean exit).
5. **Given** the two-turn session ran live, **Then** it is captured into
   `docs/demo_transcript.md` as the first demo transcript.

---

### User Story 2 - Web content acquisition is safe, bounded, and resilient (Priority: P2)

The agent's web reach is guarded: it only follows regular public web links (never local or
private network addresses, never non-web link types, never known JS-only social/video
domains), takes at most two pages from any one site for diversity, refuses oversized or
non-text responses, abandons pages that stall, and identifies itself honestly. Search
itself is resilient: a paid provider is preferred, but on quota/auth/transport failure a
keyless fallback provider supplies results — and the provider actually used is recorded
for the turn. A page that fails never takes down the others.

**Why this priority**: the web is adversarial input. Fetching it safely (mini-SSRF guard,
size/type/time caps) and searching it resiliently (provider fallback) is what makes the P1
lifecycle dependable rather than lucky — and the provenance trail (provider used, final
URLs) feeds analytics in M4 and security hardening in M5.

**Independent Test**: the URL filter drops every unsafe example (local addresses, private
ranges, non-web schemes, denylisted domains, third-plus same-domain URL) while keeping
normal article links; a mocked provider failure produces results via the fallback with the
provider recorded; a mix of good and failing pages yields the good pages only.

**Acceptance Scenarios**:

1. **Given** candidate links including `ftp:`, `file:`, `javascript:`, and `data:` targets,
   **When** filtering runs, **Then** only `http`/`https` links survive.
2. **Given** links to localhost, loopback, private, and link-local addresses (including the
   cloud metadata address), **When** filtering runs, **Then** all are dropped and a public
   host survives.
3. **Given** links to known JS-only domains (video/social) and a normal article domain,
   **When** filtering runs, **Then** the JS-only links are dropped and the article link
   survives.
4. **Given** three links on one site and one on another, **When** filtering runs, **Then**
   the first two from the first site and the one from the second survive, order preserved.
5. **Given** the paid search provider fails with an auth, quota, or transport error,
   **When** the search step runs, **Then** the keyless fallback supplies the results and
   the turn records the fallback as the provider used; on success the paid provider is
   recorded and the fallback is never called.
6. **Given** a response larger than the size cap, or of a non-text content type, or a page
   that stalls past the per-page deadline, **When** fetching runs, **Then** that page is
   skipped (never truncated-and-kept) and the remaining pages complete normally.
7. **Given** a page that redirects, **When** it is fetched, **Then** the **final** resolved
   URL is the one stored and cited.
8. **Given** any fetched page, **Then** the request carried an honest user-agent string
   containing the project's repository link, and no more than the configured number of
   fetches were in flight at once.
9. **Given** extracted page text shorter than the usability floor (200 characters),
   **When** conversion runs, **Then** the page is treated as unusable and skipped; text
   longer than the cap (20,000 characters) is truncated to the cap; an empty first
   extraction pass is retried once in recall mode before giving up.

---

### User Story 3 - What the agent learns is stored durably, freshly, and tolerantly (Priority: P3)

Every page the agent reads on a miss is passed through the sanitize-before-store seam (the
poisoning defence hook, a pass-through in this milestone), summarized into a short
per-page digest, split into bounded fragments, and stored with full provenance metadata —
so the *next* equivalent question hits memory. Storage is polite about repetition (a page
seen within the last 24 hours is not re-ingested) and never lets persistence problems harm
the user: if summarization fails the page is stored without a summary; if storage itself
fails the user still gets their answer; if storage is explicitly disabled for the turn the
answer is still produced from the in-hand content.

**Why this priority**: ingestion is what turns the web pipeline into *memory-first*
behavior — but it must degrade safely. Answering never depends on persistence; persistence
serves the next question, not this one.

**Independent Test**: an ingested page yields N fragment records + 1 summary record, each
carrying URL/title/fetch-time/source-query/sanitizer-flags; re-ingesting a 1-hour-old URL
performs no new writes while a 25-hour-old one does; forced summary and store failures
leave the turn answered; the skip-storage flag produces zero writes yet a full answer.

**Acceptance Scenarios**:

1. **Given** a fetched page, **When** ingestion runs, **Then** the sanitize seam is invoked
   on the page text **before** any splitting or storage (order is the defence), and the
   stored records carry the sanitizer's provenance flags (empty in this milestone).
2. **Given** a page yielding 3 fragments and a successful summary, **When** stored,
   **Then** 3 fragment records and 1 summary record exist under the page's identity, each
   carrying URL, title, fetch time, originating query, and provenance flags.
3. **Given** a long page, **When** the summary is produced, **Then** it is built from at
   most the first 6,000 characters of the sanitized text and is 5–8 sentences long.
4. **Given** a URL stored 1 hour ago, **When** it appears again in a miss turn, **Then**
   no re-summarize/re-embed/re-store work happens for it; a URL stored 25 hours ago is
   re-ingested (24-hour freshness window).
5. **Given** the turn's skip-storage flag is set, **When** ingestion runs, **Then** nothing
   is written yet summaries and fragments are still prepared so the answer proceeds.
6. **Given** the summary step fails for a page, **When** ingestion continues, **Then** the
   page's fragments are still produced and stored without a summary record, and the turn
   is not marked failed.
7. **Given** the storage step fails, **When** the turn completes, **Then** the answer is
   still produced from the in-hand content and the turn is not marked failed.

---

### User Story 4 - The miss branch is wired for real, answers stay grounded and bounded (Priority: P4)

The temporary dead-end miss path from M2 is gone: a miss now flows search → fetch → ingest
→ answer as one pipeline, and the graph diagram proves it. The web answer is built from a
**bounded** context — each page's summary plus only its first two fragments, never
everything — is marked with the miss route, cites only web-origin sources, and never makes
a second trip to memory (the answer uses what is already in hand). When nothing could be
fetched at all, the agent still answers from search snippets, explicitly labeled as
degraded and low-confidence. The single canonical miss banner is fixed for all commands,
and the milestone's complete prompt log is appended to the disclosure record.

**Why this priority**: this is the structural half — rewiring, bounded context, route
labels, and disclosure. It makes the P1 behavior inspectable (diagram, routes) and keeps
answer cost bounded regardless of how much was ingested.

**Independent Test**: the compiled graph's diagram shows the four web steps on the miss
path with the temporary edge absent; a 10-fragment page contributes exactly summary + 2
fragments to the answer context; the all-fetch-fail path produces the degraded route with
a disclaimer; the answer step performs zero memory reads.

**Acceptance Scenarios**:

1. **Given** the compiled graph, **When** its diagram is rendered, **Then** the miss path
   reads search → fetch → ingest → answer-from-web → turn-log, the old temporary
   miss→failure edge is absent, and the hit path is unchanged.
2. **Given** a page with a summary and 10 fragments, **When** the web answer is built,
   **Then** its context contains that page's summary and exactly its first 2 fragments —
   none of the other 8; a page with a failed (absent) summary still contributes its first
   2 fragments; a page with only 1 fragment contributes it without error.
3. **Given** a normal miss turn, **When** the answer is produced, **Then** the route is
   the miss route, every cited source is web-origin, and the answer ends with a "Sources:"
   section.
4. **Given** search returned results but no page could be fetched, **When** the answer is
   produced, **Then** it is built from the search snippets, the route is the degraded-web
   route with the snippets-only label, and the answer carries a low-confidence disclaimer.
5. **Given** any miss turn, **When** the answer is built, **Then** no memory lookup is
   performed — the context comes only from the turn's own fetched content.
6. **Given** a miss in the ask command, **When** the banner prints, **Then** it is the
   canonical `[MEMORY MISS → searching the web]` string (byte-identical to the banner the
   M4 chat REPL will use) and the web sources are listed; a hit still prints the M2 hit
   banner with memory sources.
7. **Given** the milestone closes, **Then** a dated M3 prompt-log file exists and
   `AI_USAGE.md` references it (appended, never retroactive).

---

### Edge Cases

- Both search providers return empty → deterministic failure response, never a crash
  (US1-4).
- Every fetched page fails (timeout/oversize/wrong type) → snippets-only degraded answer
  with disclaimer (US4-4), not a failure.
- One page fails mid-fetch → skipped; the others proceed (US2-6).
- A page stalls past the per-page wall-clock deadline → abandoned, others complete.
- Extraction yields under 200 characters (cookie wall / JS shell) → page treated as
  unusable, skipped.
- Redirected page → final URL stored and cited, not the original.
- Re-ask lands within the freshness window → no duplicate ingestion of the same URL.
- Summary model fails per page → page stored summary-less; turn unaffected (US3-6).
- Storage fails entirely → answer produced from in-hand content; turn unaffected (US3-7).
- Skip-storage turns still answer fully; nothing is persisted (US3-5).
- The keyless fallback search provider is scrape-based and can rate-limit or break — its
  failure surfaces as the explicit deterministic failure response, and a paid-provider key
  is preferred for recorded demos (source §10).
- A reworded (non-verbatim) re-ask may still score below the 0.70 threshold and re-search;
  the freshness gate then prevents duplicate ingestion — demo with a verbatim re-ask
  (source §10).

## Requirements *(mandatory)*

### Functional Requirements

Traceability: FR-001…FR-032 map 1:1 to FR-M3-01…FR-M3-32 in
`specs/milestone-3-web-pipeline.md` §5 (FR-010 covers both FR-M3-10a and FR-M3-10b), which
carries the full acceptance criterion for each. FR-033…FR-035 restate in-scope
deliverables from that file's §2/§6.13a/§9.

- **FR-001**: The primary web search MUST call the paid provider's search endpoint
  directly (bearer-authenticated, raw-content exclusion on, result count from
  configuration) and return ranked results each carrying URL, title, snippet, and rank
  (source: FR-M3-01).
- **FR-002**: The primary searcher MUST hold a reusable async HTTP client and MUST NOT use
  the provider's SDK package (source: FR-M3-02).
- **FR-003**: The keyless fallback searcher MUST run its synchronous engine off the event
  loop, require no credentials, and return up to the requested number of ranked results
  (source: FR-M3-03).
- **FR-004**: The provider-selection layer MUST try the paid provider first, fall back to
  the keyless provider on quota/auth/transport errors, and record the provider actually
  used both in the turn's log line and in the turn state for downstream analytics
  (source: FR-M3-04).
- **FR-005**: An empty combined search result MUST route the turn to the deterministic
  failure response (source: FR-M3-05).
- **FR-006**: URL filtering MUST accept only `http`/`https` schemes (source: FR-M3-06).
- **FR-007**: URL filtering MUST reject localhost and private/loopback/link-local address
  literals — the mini-SSRF guard (source: FR-M3-07).
- **FR-008**: URL filtering MUST drop denylisted JS-only domains (source: FR-M3-08).
- **FR-009**: URL filtering MUST keep at most 2 URLs per registrable domain,
  order-preserving (source: FR-M3-09).
- **FR-010**: Page fetching MUST be configured with the connect/read timeouts and a hard
  per-URL wall-clock deadline from configuration, and a URL exceeding that deadline MUST
  be abandoned while the others continue (source: FR-M3-10a, FR-M3-10b; the automated
  assertions for both are M5-owned per Ruling A — M3 delivers the wiring).
- **FR-011**: The fetch body MUST be capped at the configured maximum while streaming; an
  oversized response is skipped, never truncated-and-kept (source: FR-M3-11).
- **FR-012**: Fetching MUST gate on content type, accepting only HTML/XHTML/plain-text
  responses (source: FR-M3-12).
- **FR-013**: Redirects MUST be followed with the final resolved URL stored on the fetched
  document (source: FR-M3-13).
- **FR-014**: Concurrent fetching MUST be bounded by the configured concurrency limit
  (source: FR-M3-14).
- **FR-015**: Every fetch request MUST carry an honest user-agent containing the
  repository link (source: FR-M3-15).
- **FR-016**: A single URL's failure (timeout, wrong type, oversize, error status) MUST be
  skipped while the remaining URLs complete (source: FR-M3-16).
- **FR-017**: Text extraction MUST use the precision-first markdown conversion with tables
  kept and inline links dropped (source: FR-M3-17).
- **FR-018**: An empty precision extraction MUST be retried once in recall mode
  (source: FR-M3-18).
- **FR-019**: Extraction results under 200 characters MUST be rejected as unusable
  (source: FR-M3-19).
- **FR-020**: Extraction results MUST be capped at 20,000 characters per page
  (source: FR-M3-20).
- **FR-021**: Ingestion MUST invoke the sanitize seam on page text strictly **before**
  splitting/embedding and store the returned provenance flags with every record; in this
  milestone the seam is a pass-through returning the text unchanged with no flags
  (source: FR-M3-21; seam internals are M5's, Ruling C).
- **FR-022**: Ingestion MUST produce a 5–8 sentence per-page summary from at most the
  first 6,000 characters of sanitized text using the analytics model, stored as a
  summary-type record (source: FR-M3-22).
- **FR-023**: Ingestion MUST split pages into bounded overlapping fragments, batch-embed
  them, and store fragment-type records plus the one summary-type record, each carrying
  URL, title, fetch time, originating query, and sanitizer flags, keyed by the page's
  canonical identity (source: FR-M3-23).
- **FR-024**: A freshness gate MUST skip re-ingesting any URL stored within the 24-hour
  freshness window; older or unknown URLs are (re-)ingested (source: FR-M3-24).
- **FR-025**: Ingestion MUST honour the turn's skip-storage flag: no persistence, yet
  summaries and fragments are still prepared for the in-hand answer (source: FR-M3-25).
- **FR-026**: Summary failure MUST be tolerated — the page's fragments are still produced
  and stored without a summary record, and the turn is not failed (source: FR-M3-26).
- **FR-027**: Store failure MUST be tolerated — the answer never depends on persistence
  and the turn is not failed by a storage error (source: FR-M3-27).
- **FR-028**: The web answer MUST be built from each page's summary plus only its first
  two fragments — never all fragments (source: FR-M3-28).
- **FR-029**: On the normal miss path the web answer MUST set the miss route, cite
  non-empty web-origin sources, and end with a "Sources:" section (source: FR-M3-29).
- **FR-030**: When no page was fetched but search returned results, the answer MUST be
  built from snippets with the degraded-web route, the snippets-only label, and a
  low-confidence disclaimer (source: FR-M3-30).
- **FR-031**: The miss answer MUST use only in-hand content — zero additional memory
  lookups during answering (source: FR-M3-31).
- **FR-032**: The graph's miss branch MUST be rewired search → fetch → ingest →
  answer-from-web → turn-log with the temporary miss→failure edge removed, the two
  M2-delivered routers activated, and every currently-active route still reachable
  (source: FR-M3-32; the blocked route activates in M5, Ruling F).
- **FR-033**: The ask command MUST print the canonical miss banner
  `[MEMORY MISS → searching the web]` (the single canonical string shared with M4's chat)
  and list web sources on a miss, while hits keep the M2 hit banner and memory sources
  (source: §2/§6.13a — M3 is the sole owner of this update).
- **FR-034**: The live two-turn miss→ingest→hit session MUST be captured into
  `docs/demo_transcript.md` (source: §9 Definition of Done).
- **FR-035**: The M3 prompt log MUST be appended (dated, never retroactive) and referenced
  from the disclosure index before Milestone 4 starts (source: §9 Definition of Done).

### Key Entities

- **Search result**: one ranked web finding — URL, title, snippet, rank; produced by
  whichever provider served the turn.
- **Fetched document**: one successfully fetched-and-extracted page — final URL, title,
  extracted text, optional per-page summary, success marker.
- **Fragment (chunk)**: one bounded overlapping piece of a page's text, carrying its page
  identity, position, and provenance metadata; the unit of storage and retrieval.
- **Page summary**: the 5–8 sentence digest of a page, stored alongside its fragments as a
  distinct record type — the question-altitude entry point for future retrieval.
- **Sanitizer seam**: the sanitize-before-store hook invoked on every ingested page —
  pass-through now, real defence internals in M5; its position in the order is the
  contract.
- **Provider record**: which search provider actually served the turn — recorded per turn
  for the analytics and reliability work of M4/M5.
- **Demo transcript**: the captured two-turn miss→hit session — the milestone's demoable
  artifact.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From an empty memory, a novel question is answered from the live web with
  web-marked source URLs, and the identical question asked again is answered from memory
  with displayed similarity ≥ 0.70 and **zero** web calls — the full lifecycle
  reproducible run after run.
- **SC-002**: 100% of the unsafe-link table is rejected: local/private/link-local
  addresses, non-web schemes, denylisted domains, and third-plus same-site links never
  reach the network.
- **SC-003**: No single misbehaving page can break a turn: oversized, wrong-type,
  stalling, or erroring pages are skipped and the remaining pages complete — zero crashes
  across repeated runs.
- **SC-004**: Ingestion failures degrade storage only, never answers: with summarization
  or storage forced to fail, the user still receives a grounded answer in 100% of runs.
- **SC-005**: When nothing can be fetched, the user still receives a snippet-based answer
  explicitly labeled low-confidence (degraded route) — never an unlabeled or crashed turn.
- **SC-006**: After the first miss turn, the stored records for each ingested page (its
  fragments and one summary) are inspectable with full provenance (URL, title, fetch time,
  originating query, sanitizer flags).
- **SC-007**: The two-turn demo transcript exists in the repository, the dated M3 prompt
  log is referenced from the disclosure index, and CI stays green on every push.

## Assumptions

- Milestones 1 and 2 are closed and green (verified 2026-07-05): typed state, protocols,
  frozen resources, all five routers, memory store + chunker + URL identity, prompts API,
  compiled graph skeleton with the temporary miss edge, and the two M2-declared turn
  channels (turn start time, search provider) this milestone writes.
- **Credentials**: M3's live work continues on the **GitHub Models free tier** exactly as
  clarified for M2 (dev aliases in `.env`; production defaults untouched; the real
  `OPENAI_API_KEY` enters at M6's recorded demo). Per Clarifications (Session
  2026-07-05), a **free-tier Tavily API key is provided** for M3: live searches and the
  demo transcript run on the primary provider (`provider_used="tavily"`). Blank-key
  operation remains a supported design property — with `TAVILY_API_KEY` empty, the
  keyless fallback serves all searches (source §10 risk note). The key lives only in the
  git-ignored `.env`.
- **Test ownership (Ruling A)**: M3 ships at most one automated test file (the optional
  markdown-gating unit tests). The search/fetch/retry scenarios in §7 are behavioral
  acceptance criteria automated by M5's test files; ingest/answer scenarios are proven by
  M6's e2e lifecycle test. M3's proof is the live demo transcript.
- `specs/milestone-3-web-pipeline.md` §6 carries the full technical detail (request
  shapes, filter constants, fetcher configuration, node contracts, env defaults, pins)
  and is the direct input to `/speckit-plan`; this spec stays at capability level. The
  stack is locked by the constitution; naming it here is traceability, not an open choice.
- Anti-churn (source §2): no retries/backoff here (M5), no real sanitizer internals (M5),
  no turn-log body or analytics (M4), no e2e/eval automation (M6), no salvage route, no
  robots.txt consultation, no hosted extractors, no raw-content search shortcut.
- No `[NEEDS CLARIFICATION]` markers: scope, seams, and acceptance criteria are fully
  determined by the source milestone file, the orchestrator rulings, and PLAN.md.
