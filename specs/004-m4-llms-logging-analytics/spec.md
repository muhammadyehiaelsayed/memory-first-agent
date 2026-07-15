# Feature Specification: Milestone 4 — LLM Clients Finalized, Turn Log, Classifier, Analytics CLI, REPL

**Feature Branch**: `004-m4-llms-logging-analytics`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "for Milestone 4, feeding it specs/milestone-4-llms-logging-analytics.md"

> **Source of truth**: this spec restates `specs/milestone-4-llms-logging-analytics.md`
> (§1/2/5/7 per its §11 Spec Kit mapping). That file's §3/4/6/10 feed `/speckit-plan`; its
> §8/9 feed `/speckit-tasks`. On any conflict, `PLAN.md` wins (Constitution, Principle VI).
> Depends on Milestone 1 (closed 2026-07-05), Milestone 2 (closed 2026-07-05), and
> Milestone 3 (closed 2026-07-05: full web pipeline live, miss→ingest→hit lifecycle
> captured). M4 turns the agent from "answers questions" into "can be operated and
> measured": after this milestone every turn is graded into a per-turn log line, an
> analytics report reads that log, the two language-model clients take their final
> production shape with an honest documented cost story, and the operator gets a streaming
> chat session with clean, pipe-safe output.

## Clarifications

### Session 2026-07-05

- Q: FR-007's live `temperature=0` validation must run against the pinned `gpt-5.4-mini`
  id, but development runs on the GitHub Models free tier whose catalog does not serve
  that id — will a real OpenAI key be available at M4? → A: Option B — a **real OpenAI
  API key is provided for the one-off validation only**. The single pinned-id
  `temperature=0` probe (~8 tokens, well under $0.01) runs during M4 and its 200 outcome
  is recorded in the model-choice document and the AI-usage log; all remaining M4
  development continues on the free GitHub Models endpoint. The key lives only in the
  git-ignored `.env` and is never committed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every turn leaves exactly one graded record (Priority: P1)

Whenever the agent completes a turn — answered from memory, answered from the web, degraded,
blocked, or failed — exactly one structured record of that turn is appended to a durable
per-turn log file. The record grades the turn: what was asked (plus a short digest of it),
which route it took, how close the best memory match was against the decision threshold, what
web activity happened (provider used, results returned, pages fetched, fragments stored),
which sources were cited, how long each stage took (plus a wall-clock total), how many tokens
each model call consumed, the guardrail verdict, any errors, and an automatic classification
of the query (topic, category, question type, language, confidence). Recording is
best-effort by design: a recording or classification failure never breaks the user's turn.

**Why this priority**: this is the assignment requirement "log each turn: memory hit / miss
+ web search" made a first-class artifact — the graded log is the evidence stream every
later capability (analytics in this milestone, security routes in the next, the final
evaluation) reads. Without it, nothing else in M4 has data to show.

**Independent Test**: run a few turns, then inspect the log file — it has exactly one
parseable line per turn with the full record shape; force the recorder to fail and the turn
still completes for the user; construct a blocked turn and it is logged too.

**Acceptance Scenarios**:

1. **Given** three completed turns, **When** the turn log is inspected, **Then** it contains
   exactly three non-empty lines, each independently parseable, each carrying: a unique turn
   id, a timestamp, a session id, the query and a 16-character digest of it, a route from
   the closed five-value set (`memory_hit`, `memory_miss_web_search`, `degraded_web`,
   `blocked`, `failed`), the top similarity and the threshold in force, the cited sources,
   per-stage latencies, token accounts, the guardrail verdict, an errors list, and the query
   classification.
2. **Given** a turn that took the web route, **When** its record is inspected, **Then** it
   includes a web-activity block naming the search provider actually used, the number of
   results returned, pages successfully fetched, and fragments stored; **Given** a
   memory-hit turn, **Then** its record has no web-activity block and shows the 0.7
   threshold it was judged against.
3. **Given** a turn with route `blocked`, **When** the turn completes, **Then** a record for
   it is still appended.
4. **Given** a recorder that fails on write, or a classifier that fails or hangs, **When**
   the turn completes, **Then** the user still receives their answer normally, an
   operational error is reported on the diagnostic stream, and nothing crashes.
5. **Given** a completed turn whose answer call consumed a known number of input and output
   tokens, **When** its record is inspected, **Then** the token account for the answering
   model matches those numbers and names the model, the classification call's tokens are
   accounted separately, and the latency section has one entry per executed stage plus a
   wall-clock `total` that is at least as large as any single stage.
6. **Given** a query the classifier cannot process (failure, timeout, or malformed output),
   **When** the record is written, **Then** its classification field is null (reported later
   as "Unclassified") rather than the turn erroring; **Given** a classification whose
   category or question type is outside the known sets, **Then** it degrades to `other`
   instead of failing.

---

### User Story 2 - The operator reads hit-rate and topic analytics over the log (Priority: P2)

An operator runs a single analytics command and gets a readable report over everything the
agent has done: how many turns ran, what fraction of memory lookups were answered from
memory (hit-rate), the top topics asked about, how queries distribute across categories,
question types, and languages, average latency per route, how many turns had errors, how
many could not be classified, and the most recent turns at a glance. A machine-readable mode
emits the same aggregates as JSON. A bundled sample log makes the report demonstrable on a
fresh clone before any live turn has run.

**Why this priority**: this is the assignment requirement "analytics on topics & question
types" — the consumer of User Story 1's records. It is what makes the log *useful* rather
than just present, and it is the milestone's demoable outcome ("analytics renders a table
over real turns").

**Independent Test**: point the analytics command at the bundled sample log — all ten report
sections render; run it with the JSON flag — standard output is a single JSON aggregate and
nothing else; delete the log — a friendly "no turns yet" message appears instead of an
error dump.

**Acceptance Scenarios**:

1. **Given** the bundled sample log, **When** `memagent analytics` runs, **Then** all ten
   sections render: total turns, hit-rate %, top topics, category distribution,
   question-type distribution, language distribution, average latency per route, error
   count, unclassified count, and a recent-turns table.
2. **Given** records with routes [memory_hit, memory_hit, memory_miss_web_search, blocked],
   **When** aggregation runs, **Then** total turns is 4 and the hit-rate is 2 of 3 — hits
   divided by memory-lookup turns, with blocked/failed turns (where memory was never
   consulted) excluded from the denominator; an empty denominator yields 0 rather than an
   error.
3. **Given** the JSON flag, **When** the command runs, **Then** standard output is valid
   JSON containing the totals, hit-rate, topics, distributions, per-route latency averages,
   and the error/unclassified counts — and no tables or decoration appear on standard
   output.
4. **Given** a logged query containing display-styling markup (e.g. `[red]boom[/red]`),
   **When** the report renders, **Then** the text appears literally and unstyled — every
   user-derived string (query, topic, source title/URL, language) is escaped before display.
5. **Given** a fresh environment with no turn log, **When** the analytics command runs,
   **Then** it prints friendly guidance ("no turns logged yet — run `memagent ask` …")
   and no error trace.
6. **Given** the delivered repository, **Then** the bundled sample log of about ten records
   covers all five routes and at least one unclassified turn, and the README documents the
   one-line external-tool query over the turn log (DuckDB note).

---

### User Story 3 - Two finalized models with an honest, documented cost story (Priority: P3)

The agent's two language models take their final production shape: a pinned conversation
model that answers deterministically with a bounded reply length, and a pinned small
analytics model for classification and page summaries with a tighter reply bound. Every
model call reports its token consumption so turns can be costed. A missing API key fails
fast with one readable line; an optional alternate endpoint switch routes all model traffic
(conversation, analytics, embeddings) to a free development provider without code changes.
The choice of models ships as a written explanation with verified prices, per-turn cost
estimates, a named runner-up, and the reasons alternatives were rejected.

**Why this priority**: this is the assignment requirement "two LLMs (conversation +
analytics) with a choice/cost/quality explanation". It also feeds User Story 1 — without
per-call token reporting the turn records cannot account cost — but the record schema
itself is testable without it, so it lands after the log and its reader.

**Independent Test**: build the clients from configuration and inspect them — the pinned
model names, reply bounds, determinism setting, no hidden transport retries, and the
45-second call timeout are all in force; call the conversation model against a stub and the
reply comes back with its token account; unset the key and a single readable error line
appears; the model-choice document exists at the repository root with every stated price.

**Acceptance Scenarios**:

1. **Given** default configuration, **When** the model clients are built, **Then** the
   conversation client is pinned to `gpt-5.4-mini` with deterministic output
   (temperature 0) and a 2048-token reply cap, the analytics client is pinned to
   `gpt-5.4-nano` with a 256-token reply cap, and the shared transport performs no retries
   of its own and times out calls at 45 seconds.
2. **Given** a stubbed reply that consumed 2311 input and 402 output tokens, **When** the
   conversation client completes a call, **Then** the caller receives the reply text
   together with a usage account of exactly those numbers and the configured model name.
3. **Given** a classification request, **When** the analytics client is asked for
   structured output, **Then** the caller receives a validated classification object (not
   free text) plus the same three-part usage account.
4. **Given** an empty API key, **When** any command needing models starts, **Then** it
   stops with a single readable error line pointing at the environment setup — never a
   stack trace; **Given** the alternate-endpoint variable is set, **Then** all three model
   surfaces (conversation, analytics, embeddings) route to it through one code path.
5. **Given** the pinned conversation model, **When** a one-off live call with deterministic
   settings is made at build time, **Then** it is accepted (not rejected as unsupported) and
   the outcome is recorded in the model-choice document and the AI-usage log; if a future
   model snapshot rejects the setting, the documented contingency is to drop the setting for
   that client and note it — never to silently swap models.
6. **Given** the delivered repository root, **Then** the model-choice document exists and
   contains: the chosen-pair price table with its verification date, the per-turn cost
   (~$0.006 hit / ~$0.008 miss), the 100-turn demo estimate ($0.60–0.90 vs ~$1.50–2 on the
   flagship), the flagship named as the zero-code-change runner-up, the full
   why-not-alternatives list, and the free-development-endpoint note.
7. **Given** each model client, **Then** every network call it makes flows through exactly
   one internal call path per call surface, so the next milestone can attach its retry
   policy at that one place without touching any caller.

---

### User Story 4 - Interactive chat with clean, observable operation (Priority: P4)

A user opens an interactive chat session. Each question immediately shows whether memory
answered it (`[MEMORY HIT sim=X.XX]`) or the web is being consulted
(`[MEMORY MISS → searching the web]`); the answer prints the moment it is ready — before
any background record-keeping runs — followed by its sources. The conversation keeps only
the most recent six exchanges as context. Meanwhile, operational diagnostics (stage
timings, turn ids) go to the diagnostic stream only, so redirecting or piping the answer
output stays clean.

**Why this priority**: this is the operator experience that makes the whole agent pleasant
to demo and debug — but it is UX over machinery that User Stories 1–3 already prove, so it
lands last.

**Independent Test**: in one chat session ask the same question twice — miss banner then hit
banner, with no web activity on the second turn; redirect a single-question run to a file —
the file holds only the answer and sources while diagnostics appear on the other stream.

**Acceptance Scenarios**:

1. **Given** an interactive session with empty memory, **When** the same question is asked
   twice, **Then** the first turn shows the miss banner and a sourced answer, and the second
   shows a hit banner whose similarity is at or above 0.70 with no web search performed.
2. **Given** a turn that routes through the web, **When** the answer is composed, **Then**
   it prints immediately on completion — classification and record-writing happen after the
   answer is already on screen.
3. **Given** a memory-lookup outcome exactly at the threshold (similarity 0.70), **Then**
   the hit banner is shown; **Given** 0.6999, **Then** the miss banner is shown — the
   boundary is inclusive and matches the router's decision exactly.
4. **Given** seven completed exchanges, **When** the next turn is prepared, **Then** only
   the most recent six exchanges (twelve messages) are carried as context.
5. **Given** `memagent ask "x"` redirected to a file, **When** the run completes, **Then**
   the file contains only the answer and sources, and diagnostic lines carrying the turn id
   appear on the diagnostic stream instead.
6. **Given** a future blocked turn (activated next milestone), **When** it occurs in chat,
   **Then** the session already knows how to print the refusal — the handling ships now,
   dormant.

---

### Edge Cases

- **Recorder write failure**: the record writer raising (e.g. disk error) must not
  propagate — the turn ends normally, the failure is reported diagnostically. (US1)
- **Classifier hang**: a classification call that would run 30 seconds is cut off by the
  8-second ceiling and yields "unclassified" at roughly 8 seconds, not 30. One transient
  failure is retried once; persistent failure yields null. (US1)
- **Out-of-set labels**: a classification naming an unknown category or question type (e.g.
  "wombat") deserializes to `other` — never an exception. (US1)
- **Hit-rate with no lookups**: aggregation over records containing no memory-lookup turns
  reports a 0 hit-rate rather than dividing by zero. (US2)
- **Markup injection into the report**: user queries can contain display-markup; every
  user-derived string is escaped so the report cannot be styled or broken by a query. (US2)
- **Missing turn log**: analytics over a path with no file prints guidance, not a
  traceback. (US2)
- **Determinism setting rejected**: if the pinned conversation model ever rejects
  temperature 0 (the flagship does; snapshots vary), the client is built without the
  setting and the fact is documented — the model is never silently swapped. (US3)
- **Token accounts do not accumulate**: the per-turn token map keeps the last write per
  model role; the answer call and the classification call are written under separate roles
  so neither overwrites the other, and per-page summary usage is not separately itemised.
  (US1/US3)
- **Wall-clock total vs stage sum**: the latency `total` is wall-clock from turn start to
  record write — it may legitimately exceed the sum of instrumented stages. (US1)
- **Degraded routes and the denominator**: a degraded turn where memory was consulted
  (snippets-only) counts as a lookup for hit-rate; a degraded turn where memory was
  unreachable does not. (US2)
- **Blocked route today**: until the guard activates (next milestone), no live turn takes
  the blocked route — the recorder and report must nonetheless handle it now (proven with
  constructed records and the sample log). (US1/US2)

## Requirements *(mandatory)*

### Functional Requirements

Numbering preserves the source spec: FR-001…FR-022 restate FR-M4-01…FR-M4-22; FR-023 and
FR-024 add the milestone's standing disclosure and demoable-outcome obligations.

**Model clients**

- **FR-001**: Every conversation-model completion MUST return the reply text together with
  a usage account of the call — input tokens, output tokens, and the model identity — taken
  from the provider's reported usage, so each turn's cost is attributable.
- **FR-002**: The system MUST support structured-output calls that return a validated
  classification object (not free text to parse by hand) plus the same three-part usage
  account.
- **FR-003**: The conversation client MUST be pinned to the configured conversation model
  (default `gpt-5.4-mini`) with deterministic output (temperature 0) and a 2048-token reply
  cap, over a transport that performs no retries of its own and times out calls at the
  configured 45 seconds.
- **FR-004**: The analytics client MUST be pinned to the configured analytics model
  (default `gpt-5.4-nano`) with a 256-token reply cap.
- **FR-005**: When the alternate-endpoint variable is set, all model traffic (conversation,
  analytics, embeddings) MUST route to it through one shared code path; when the API key is
  missing, startup MUST stop with a single readable error line, never a stack trace.
- **FR-006**: Each client MUST route every network request through exactly one internal
  call path per call surface, so the next milestone's retry policy attaches at exactly one
  place without editing any caller.
- **FR-007**: Deterministic output (temperature 0) MUST be validated against the pinned
  conversation model with a documented one-off live call whose outcome is recorded in the
  model-choice document and the AI-usage log; support is version-sensitive across model
  snapshots, so validation cannot be skipped.

**Model documentation**

- **FR-008**: A model-choice document MUST exist at the delivered repository root
  containing: the chosen-pair price table (prices re-verified this milestone, with the
  verification date), the per-turn cost (~$0.006 hit / ~$0.008 miss), the 100-turn demo
  estimate ($0.60–0.90 vs ~$1.50–2 flagship), the flagship runner-up (zero-code-change
  swap), the full why-not-alternatives list, and the free-development-endpoint note.

**Turn log**

- **FR-009**: Every completed turn MUST append exactly one record as one line to the turn
  log file (append-only; the containing folder is created on demand). After N turns the
  file has exactly N non-empty, independently parseable lines.
- **FR-010**: Each record MUST match the canonical turn-record shape: unique turn id
  (random UUID), timestamp, session id, query and its 16-character digest, a route from the
  closed five-value set, degradation marker, top similarity and threshold, web-activity
  block (on web routes), sources, per-stage latencies, per-role token accounts, guardrail
  verdict and events, errors, and the query classification.
- **FR-011**: Blocked turns MUST be logged too, and the recording step MUST never raise —
  a recording or classification failure is swallowed, reported diagnostically, and the
  user's turn completes normally.
- **FR-012**: The real recording step MUST replace the placeholder wired in Milestone 2: it
  classifies the query, builds the record — including a wall-clock latency `total` and the
  token accounts — and writes it, on every terminal path of every turn.

**Query classifier**

- **FR-013**: The classification result MUST carry exactly: a free-form short topic, a
  category from the closed nine-value set (technology, science, health, finance_business,
  travel_geography, entertainment_sports, history_politics, lifestyle, other), a question
  type from the closed six-value set (factual, how_to, comparison, opinion,
  troubleshooting, other), a two-letter language code, and a confidence between 0 and 1.
- **FR-014**: The classifier prompt MUST frame the user's query strictly as data to be
  classified — wrapped in explicit data tags and preceded by never-follow-instructions
  framing — so a query cannot steer the classifier.
- **FR-015**: Classification MUST enforce the configured 8-second ceiling, retry once on a
  transient failure, and on any failure (timeout, error, malformed output) yield
  "unclassified" (null) without raising; out-of-set category or question-type labels MUST
  degrade to `other`.

**Analytics report**

- **FR-016**: The analytics command MUST render, over the turn log: total turns, hit-rate %
  (hits ÷ memory-lookup turns; blocked/failed and memory-unreachable turns excluded from
  the denominator; 0 when the denominator is empty), top topics, category distribution,
  question-type distribution, language distribution, average latency per route, error
  count, unclassified count, and a recent-turns table — ten sections in all.
- **FR-017**: A JSON mode MUST write the aggregate object to standard output as valid JSON
  and render no tables or decoration there.
- **FR-018**: Every user-derived string (query, topic, source title/URL, language) MUST be
  escaped before display so display-markup in a query renders literally and cannot style or
  break the report.
- **FR-019**: A bundled sample turn log (~10 records covering all five routes and at least
  one unclassified turn) MUST ship in the repository so the report is demonstrable with
  zero live turns, and the README MUST carry the one-line external-tool query note (DuckDB)
  over the turn log.

**Chat session & observability**

- **FR-020**: The interactive chat MUST stream turn progress, print
  `[MEMORY HIT sim=X.XX]` when the top similarity meets the inclusive 0.70 threshold and
  the byte-identical `[MEMORY MISS → searching the web]` banner otherwise, print the answer
  the moment an answering step completes (before record-keeping), and carry at most the
  most recent six exchanges as context.
- **FR-021**: Operational diagnostics MUST go to the diagnostic stream only, with the turn
  id attached to every line of a turn; the answer stream stays pipe-clean (redirecting a
  run leaves a file containing only the answer and sources).
- **FR-022**: Each pipeline stage's elapsed milliseconds MUST be recorded per turn, and the
  usage accounts from the answering and classification calls MUST flow into the turn
  record (`answer` and `analytics` roles respectively), with the wall-clock `total`
  measured from turn start to record write.

**Milestone obligations**

- **FR-023**: The complete instruction record for this milestone MUST be appended to the
  AI-usage disclosure (`AI_USAGE.md` section + a dated `docs/ai_prompts/` entry), never
  retroactively (Constitution, Principle VII).
- **FR-024**: All four commands (`chat`, `ask`, `analytics`, `wipe-memory`) MUST perform
  their real function — no remaining placeholder responses — and the analytics command
  MUST render a real hit-rate and topic table over turns generated in the same session
  (the milestone's demoable outcome).

### Key Entities

- **Turn record**: the one-per-turn graded artifact — identity (turn id, session id,
  timestamp), the query and its digest, routing outcome (route, degradation, similarity vs
  threshold), web activity (provider, counts), sources, per-stage latencies with wall-clock
  total, per-role token accounts, guardrail verdict/events, errors, and the classification.
  Append-only lines in the turn log file; the single source of truth for analytics.
- **Query classification**: the automatic label set for one query — topic (short free
  text), category (closed nine-value set), question type (closed six-value set), language
  code, confidence. May be null ("Unclassified") when classification fails; unknown labels
  degrade to `other`.
- **Usage account**: the per-call cost triple — input tokens, output tokens, model
  identity — attached to every model call and rolled into the turn record per role
  (answering vs analytics).
- **Analytics aggregate**: the computed summary over turn records — totals, hit-rate,
  top topics, three distributions, per-route latency averages, error and unclassified
  counts, recent turns — renderable as tables or emitted as JSON.
- **Sample turn log**: ~10 bundled records covering all five routes and an unclassified
  turn; makes the report demonstrable on a fresh clone.
- **Chat history**: the rolling conversation context, capped at the six most recent
  exchanges (twelve messages).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After any N completed turns (including blocked/failed ones), the turn log
  contains exactly N parseable records — a 1:1 turn-to-record guarantee with zero lost or
  duplicated turns.
- **SC-002**: A single analytics command over the bundled sample log renders all ten report
  sections; with the JSON flag, standard output is one valid JSON document and nothing else.
- **SC-003**: All four user commands perform their real function end to end, and the
  analytics report shows a real hit-rate and topic table over turns generated in the same
  session — the milestone's demoable outcome.
- **SC-004**: In one interactive session, the same question asked twice yields a miss
  banner then a hit banner (similarity ≥ 0.70) with zero web activity on the second turn,
  and each answer is on screen before its record-keeping runs.
- **SC-005**: Redirecting a single-question run to a file yields a file with zero
  diagnostic lines — only the answer and its sources.
- **SC-006**: No classifier or recorder failure ever surfaces to the user: across failure
  drills (raising recorder, raising classifier, hanging classifier, malformed labels), the
  user-visible turn completes normally 100% of the time and the affected records show
  "unclassified" rather than being dropped.
- **SC-007**: The model-choice document at the repository root states every price with a
  verification date, the ~$0.006/hit and ~$0.008/miss per-turn costs, and the 100-turn
  estimate — the cost story is auditable without reading any code.
- **SC-008**: The milestone's owned unit tests and the full existing suite pass with zero
  real keys and no live network, and lint stays clean (Constitution, Principle VIII).

## Assumptions

- **Adopted defaults from the source spec's marked notes** (each "change freely" in the
  source; restated here as this feature's working decisions):
  - *Hit-rate definition*: hits ÷ memory-lookup turns, where lookup turns are hits, misses,
    and snippets-only degraded turns; blocked, failed, and memory-unreachable degraded
    turns are excluded; 0 when the denominator is empty.
  - *Latency total*: wall-clock from turn-state construction to record write, computed
    inside the recording step (an outer wrapper or facade would run only after the record
    is already written).
  - *Analytics model determinism*: the analytics client also runs at temperature 0 for
    reproducible classification; if a pinned snapshot rejects it, the setting is dropped
    for that client and noted.
  - *Structured-output surface*: the chat-completions parse surface is used for symmetry
    with completion calls; if the pinned SDK offers only the responses surface, the
    single-call-path seam makes it a one-line swap.
  - *Classifier retry locality*: the classifier's small, null-tolerant retry-once policy
    lives at the classification call site this milestone (the source mandates it now); the
    next milestone may relocate it into the central reliability module without changing the
    classifier's contract.
  - *Token-account semantics*: the per-turn token map keeps the last write per role; the
    answering call and the classification call are written under distinct roles; per-page
    summary usage is not separately itemised this milestone.
  - *Logging configuration home*: operational-logging setup lives with the application
    facade and is invoked once at command start.
- **Constructor reconciliation is in scope** (Ruling D finalisation): Milestone 2's thin
  per-client construction is replaced by one shared transport and finalized client
  signatures, and the application facade's resource builder is rewritten to use it; the
  call interfaces Milestone 3's nodes consume are unchanged, so no Milestone 3 node is
  touched.
- **Named Milestone 2 → 4 seams close here**: the placeholder recording step (Ruling B) is
  replaced by the real one, and the schema-only classification enums shipped in Milestone 2
  are hardened in place (unknown labels → `other`) rather than re-declared.
- **Guard routes are wired but dormant**: the guard entry activates next milestone; until
  then the verdict defaults to "allow", no live turn takes the blocked route, and blocked
  handling is proven with constructed records, the sample log, and the dormant chat branch.
- **Test ownership honours the milestone map**: this milestone owns the classifier-parsing
  and turn-log unit tests, built with small inline fakes; the shared test fixtures arrive
  with Milestone 6 and are not created early. Retry policies for general client calls,
  prompt hardening, and the input guard remain next-milestone scope.
- **Determinism validation runs on a real key** (clarified 2026-07-05): a real OpenAI API
  key is provided for the one-off FR-007 probe against the pinned `gpt-5.4-mini` id; its
  outcome is recorded with the run date in the model-choice document and the AI-usage log
  (Constitution, Principle IX). Day-to-day M4 development stays on the free GitHub Models
  endpoint (whose catalog serves development aliases, not the pinned id — established in
  Milestone 2). If the probe were ever rejected, the documented contingency (drop the
  setting for that client and note it) applies; the model is never silently swapped.
- **Calibration honesty for the re-ask demo**: measured behaviour (Milestones 2–3) puts
  verbatim re-ask similarity around 0.74 — not the illustrative 0.9x — and hitting on
  re-ask is topic-dependent (one measured topic missed at 0.692). The interactive demo
  should use a topic known to re-hit; the hit banner's similarity may read anywhere from
  0.70 to 1.00.
- **Free development endpoint limits**: the free tier (~50–150 requests/day) is for
  development only, never the recorded demo; the recorded demo runs with a real key and the
  alternate-endpoint variable unset.
- **No new dependencies**: everything this milestone needs (retry library, terminal-table
  library, structured logging) has been a pinned runtime dependency since Milestone 1.
- **Anti-churn boundaries hold** (Constitution, Principle VI): no turn-log mirror in the
  memory store, no token-by-token streaming (the chat streams step updates only), no
  coverage gate, no gray-zone guard classifier, no non-UUID id scheme.
