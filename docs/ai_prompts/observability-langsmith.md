# Observability — opt-in LangSmith tracing + per-turn cost (appended 2026-07-09)

A post-delivery addition on the `observability-langsmith` branch. After the final-polish
merge, the user asked to layer LangSmith tracing on top of the existing JSONL turn log.
Tooling: Claude Code (Fable 5), with a verification workflow (parallel review + docs-audit
subagents) before push.

## 1. Instruction (user-issued, verbatim)

1. "if i want to use langsmith for obsivability is it free" / "does it requre credit card" /
   "can i add both the curren way and langsmith"
2. "here is the inforamtion LANGSMITH_TRACING=true … make sure you make all nessry logs
   using langsmith / use workflwos make sure after you finish it is working fine and as it
   should and keep doing unitill it is done / make sure you update all nessary docs files"

## 2. Approach

Design constraint: **off by default, zero egress unless opted in** — the JSONL turn log
(`logs/turns.jsonl`) stays the keyless, offline source of truth; LangSmith is an additive
span viewer, enabled only when `LANGSMITH_TRACING=true` **and** an API key are set.

- Four new `Settings` fields (`LANGSMITH_TRACING/API_KEY/ENDPOINT/PROJECT`);
  `.env.example` regenerated from the class (the anti-drift mechanism, FR-M1-08).
- `configure_tracing` (app.py) exports the standard `LANGSMITH_*` environment when opted
  in — needed because `Settings` reads `.env` without touching `os.environ`, while the
  langsmith SDK only sees real environment variables. Called once in `build_resources`.
- `build_openai_clients` passes the one shared `AsyncOpenAI` transport through
  `langsmith.wrappers.wrap_openai` under the same gate, so chat `create`/`parse` calls
  appear as LLM spans inside node traces (lazy import: tracing-off runs never load it).
- `sg.compile(name="memagent")` names the root run (mermaid output verified unchanged).
- The conftest `settings` fixture pins `LANGSMITH_TRACING=false` so the keyless suite
  stays zero-egress even when the developer's real `.env` opts in; the new BDD scenarios
  drive `configure_tracing` against an injected env dict, never real `os.environ`.

## 3. Verified

- 5 new BDD scenarios (off-by-default, flag-without-key stays off, opt-in export,
  wrap-only-when-fully-opted-in, build_resources activates tracing through the real
  environment) with `# covers:` declarations; the traceability gate passes at
  147 functions / 226 scenarios.
- Mutation-verified: `and → flag-only` in the configure_tracing gate, `and → or` in the
  clients gate, and deleting the `configure_tracing` call in build_resources each turn
  exactly one of the new scenarios red.
- `make test`: 396 keyless tests green, zero warnings; `make lint` clean.
- Live end-to-end: one miss turn and one hit turn each produced a `memagent` root run in
  the LangSmith project, verified via the LangSmith API — the miss trace shows the full
  `guard_input → embed_query → memory_search → web_search → fetch_pages → ingest_content
  → answer_from_web → log_turn` chain plus router spans and 7 `ChatOpenAI` LLM spans; the
  hit trace shows the short memory path ending in `answer_from_memory`. `logs/turns.jsonl`
  recorded both turns unchanged.

## 4. Pre-push adversarial review

A 10-agent workflow (3 review lenses — correctness/egress, test+gate coherence, docs
truth — then an independent skeptic per finding) confirmed 6 gaps, all fixed before push:

1. The tracing-off pin lived only in the function-scoped `settings` fixture, so
   shell-exported `LANGSMITH_*` variables could have made non-fixture graph tests upload
   traces → replaced with an **autouse** fixture pinning/clearing all four variables for
   every test.
2. + 3. The AND gate (flag **and** key) was only tested both-on/both-off in both files —
   an `and → or` regression would have passed the suite → added the flag-without-key
   boundary scenario and a half-opt-in build assertion (both mutation-verified).
4. Nothing exercised the production wiring (`build_resources → configure_tracing →
   os.environ`) — deleting the call would have silently killed the feature → added a
   scenario that asserts the real environment after building opted-in resources.
5. The tracing scenarios could be broken by ambient shell variables → same autouse fix.
6. `AI_USAGE.md` still said `Settings` has 37 fields; it has 41 → corrected.

## 5. Docs updated

README (new "Optional LangSmith tracing" section with the stated egress trade-off, test
counts), `docs/BDD.md` (counts, index rows, matrix rows), `.env.example` (regenerated),
`AI_USAGE.md` (this record's index entry + the `Settings` field-count truth-check).

## 6. Follow-up instruction (same day, verbatim)

1. "can you add the cost as well in all logs local and langsmit"

Per-turn USD cost added to both sinks from ONE pricing site: `_MODEL_PRICES_PER_1M` and
`cost_usd()` moved to `analytics/turnlog.py` (the record-schema owner); the aggregate in
`report.py` now imports it, so per-turn and aggregate cost cannot drift. Every turn record
gains a top-level `cost_usd` (after `tokens`; unpriced models — including, at the time,
the $0 GitHub Models dev aliases — contribute 0, never a guess; §7 later priced the
free-dev aliases as a paid-equivalent estimate). `log_turn` writes the same figure into
graph state (new `cost_usd` state channel, initialised in `new_turn_state`), so an opt-in
LangSmith trace shows it on the `log_turn` span outputs and the root run's final state —
verified live against the LangSmith API and the JSONL record of the same turn.
`logs/turns.sample.jsonl` regenerated with priced records. +1 scenario / extended two
others; mutations (a wrong table price, dropping the record field, dropping the
state write) each turn tests red. 397 keyless / 405 total; gate 148 functions /
227 scenarios.

## 7. Follow-up instruction (2026-07-10, verbatim)

1. "one more thing when you log the cost local and in langsmith it is always 0 becasue i
   use free models from github but i want for now becasue i use git hub i need an
   estimation to actual cost based on in and out tokens if i use this models and pay for
   it use workflows and make sure the change is minimal and make sure it works after you
   finish"

Minimal change (one file of code): the GitHub Models free-dev aliases
(`openai/gpt-4.1-mini` $0.40/$1.60, `openai/gpt-4.1-nano` $0.10/$0.40 per 1M — verified on
the official OpenAI model pages 2026-07-10) were added to `_MODEL_PRICES_PER_1M`, so
free-tier dev turns now log what the same in/out tokens would cost if paid — in the JSONL
record, the graph state, and the LangSmith trace, all through the existing single pricing
site (zero changes to `cost_usd`, `build_turn_record`, `log_turn`, or the report). The
"unpriced models report 0" behaviour is unchanged for genuinely unknown models; README,
MODEL_CHOICES, and the table comments now state the estimate explicitly. The existing
pricing scenario gained one step hand-computing both alias prices; mutations (a wrong alias
price, a deleted alias row) each turn the test red. Because the analytics report prices
token buckets through the same table, `memagent analytics` retroactively estimates cost for
previously-logged free-tier turns too (their stored `cost_usd: 0.0` is immutable history).

Follow-up (same day): the user pointed out LangSmith's own per-run cost column still read
$0 — that column is LangSmith's separate pricing layer, computed at ingest from its model
price map, whose anchored default patterns (`^gpt-4\.1-mini…$`) cannot match the prefixed
alias IDs. Fixed without code: two workspace price-map entries were added via the
`model-price-map` API (match `^openai/gpt-4\.1-mini(-\d{4}-\d{2}-\d{2})?$` at
$0.40/$1.60 per 1M, and the nano equivalent at $0.10/$0.40). Verified on a live turn: the
root run's native `total_cost` (0.002656) now equals the app-logged `cost_usd` (0.002656)
on the same trace, with per-span costs on each LLM call. The price map applies at ingest,
so earlier traces keep native $0; their outputs still carry the app's `cost_usd`. README's
LangSmith section documents the price-map step.
