# BDD Scenarios — Behavior Coverage for Every Python Function

The agent's behavior is specified as executable Gherkin. **Every module-level
function and class method in `src/` and `scripts/` (152 functions) has its own
BDD scenario** (232 scenarios across 45 feature files), each derived from
the root feature `tests/bdd/features/00_main_functionality.feature` — the main
functionality (memory-first answering over the five routes: `memory_hit`,
`memory_miss_web_search`, `degraded_web`, `blocked`, `failed`).

This is **enforced, not aspirational**: `tests/bdd/test_bdd_traceability.py`
re-derives the function inventory from the source tree by AST on every run and
fails the build if any function lacks a `# covers:` declaration (or any
declaration goes stale), in both directions. This document is generated from
the same declarations.

## How to run

```bash
uv run pytest tests/bdd -q          # the full BDD suite (keyless; redis-backed
                                    # scenarios auto-skip when redis is down)
make redis-up                       # to also run the redis-backed store/e2e scenarios
uv run pytest tests -q              # everything: unit + integration + e2e + BDD
```

Scenarios are plain pytest items (pytest-bdd), so they run in CI with the rest
of the suite — no separate BDD runner.

## Layout

- `tests/bdd/features/*.feature` — Gherkin. One feature file per Python module;
  one scenario per function, marked by a `# covers: <qualname>` comment.
- `tests/bdd/test_bdd_*.py` — pytest-bdd step bindings (one per batch of
  related modules). Steps call the real functions with the same keyless
  fakes/respx techniques as the unit suite.
- `tests/bdd/features/00_main_functionality.feature` — the root feature; every
  module feature names its parent root scenario in a `# Derived from:` header.
- `tests/bdd/test_bdd_traceability.py` — the coverage gate described above.

## Feature files

| Feature file | Module | Derived from (root scenario) | Scenarios | Binding |
|---|---|---|---|---|
| `00_main_functionality.feature` | `—` | — | 6 | `tests/bdd/test_bdd_main_functionality.py` |
| `99_traceability.feature` | `—` | — | 1 | `tests/bdd/test_bdd_traceability.py` |
| `analytics_classify.feature` | `src/memagent/analytics/classify.py` | "Log exactly one analytics record for every turn" | 6 | `tests/bdd/test_bdd_analytics.py` |
| `analytics_report.feature` | `src/memagent/analytics/report.py` | "Log exactly one analytics record for every turn" | 5 | `tests/bdd/test_bdd_analytics.py` |
| `analytics_turnlog.feature` | `src/memagent/analytics/turnlog.py` | "Log exactly one analytics record for every turn" | 5 | `tests/bdd/test_bdd_analytics.py` |
| `app.feature` | `src/memagent/app.py` | "Fall back to the web and ingest what was found on a memory miss" | 10 | `tests/bdd/test_bdd_orchestration.py` |
| `cli.feature` | `src/memagent/cli.py` | "Answer from memory when a similar question was seen before" | 27 | `tests/bdd/test_bdd_cli.py` |
| `config.feature` | `src/memagent/config.py` | "Answer from memory when a similar question was seen before" | 4 | `tests/bdd/test_bdd_contracts.py` |
| `graph.feature` | `src/memagent/graph.py` | "Block malicious input at the guard before any model call" | 2 | `tests/bdd/test_bdd_orchestration.py` |
| `interfaces.feature` | `src/memagent/interfaces.py` | "Answer from memory when a similar question was seen before" | 10 | `tests/bdd/test_bdd_contracts.py` |
| `llm_clients.feature` | `src/memagent/llm/clients.py` | "Answer from memory when a similar question was seen before" | 9 | `tests/bdd/test_bdd_llm_clients.py` |
| `llm_prompts.feature` | `src/memagent/llm/prompts.py` | "Answer from memory when a similar question was seen before" | 5 | `tests/bdd/test_bdd_llm_prompts.py` |
| `main_entry.feature` | `src/memagent/__main__.py` | "Answer from memory when a similar question was seen before" | 1 | `tests/bdd/test_bdd_contracts.py` |
| `memory_chunking.feature` | `src/memagent/memory/chunking.py` | "Fall back to the web and ingest what was found on a memory miss" | 4 | `tests/bdd/test_bdd_memory_support.py` |
| `memory_schema.feature` | `src/memagent/memory/schema.py` | "Answer from memory when a similar question was seen before" | 5 | `tests/bdd/test_bdd_memory_support.py` |
| `memory_store.feature` | `src/memagent/memory/store.py` | "Answer from memory when a similar question was seen before" | 10 | `tests/bdd/test_bdd_memory_store.py` |
| `memory_urls.feature` | `src/memagent/memory/urls.py` | "Fall back to the web and ingest what was found on a memory miss" | 2 | `tests/bdd/test_bdd_memory_support.py` |
| `nodes_answer.feature` | `src/memagent/nodes/answer.py` | "Answer from memory when a similar question was seen before" | 5 | `tests/bdd/test_bdd_nodes_memory_path.py` |
| `nodes_embed.feature` | `src/memagent/nodes/embed.py` | "Report failure when the query cannot be embedded" | 2 | `tests/bdd/test_bdd_nodes_memory_path.py` |
| `nodes_fetch.feature` | `src/memagent/nodes/fetch.py` | "Fall back to the web and ingest what was found on a memory miss" | 2 | `tests/bdd/test_bdd_nodes_web_path.py` |
| `nodes_guard.feature` | `src/memagent/nodes/guard.py` | "Block malicious input at the guard before any model call" | 4 | `tests/bdd/test_bdd_security.py` |
| `nodes_ingest.feature` | `src/memagent/nodes/ingest.py` | "Fall back to the web and ingest what was found on a memory miss" | 7 | `tests/bdd/test_bdd_nodes_web_path.py` |
| `nodes_log.feature` | `src/memagent/nodes/log.py` | "Log exactly one analytics record for every turn" | 3 | `tests/bdd/test_bdd_analytics.py` |
| `nodes_memory.feature` | `src/memagent/nodes/memory.py` | "Answer from memory when a similar question was seen before" | 3 | `tests/bdd/test_bdd_nodes_memory_path.py` |
| `nodes_search.feature` | `src/memagent/nodes/search.py` | "Fall back to the web and ingest what was found on a memory miss" | 2 | `tests/bdd/test_bdd_nodes_web_path.py` |
| `package.feature` | `src/memagent/__init__.py` | "Answer from memory when a similar question was seen before" | 1 | `tests/bdd/test_bdd_contracts.py` |
| `resources.feature` | `src/memagent/resources.py` | "Report failure when the query cannot be embedded" | 2 | `tests/bdd/test_bdd_contracts.py` |
| `routers.feature` | `src/memagent/routers.py` | "Answer from memory when a similar question was seen before" | 5 | `tests/bdd/test_bdd_orchestration.py` |
| `scripts_capture_demo.feature` | `scripts/capture_demo.py` | "Answer from memory when a similar question was seen before" | 3 | `tests/bdd/test_bdd_scripts_evals.py` |
| `scripts_eval_grounding.feature` | `scripts/eval_grounding.py` | "Fall back to the web and ingest what was found on a memory miss" | 7 | `tests/bdd/test_bdd_scripts_evals.py` |
| `scripts_eval_lifecycle.feature` | `scripts/eval_lifecycle.py` | "Fall back to the web and ingest what was found on a memory miss" | 5 | `tests/bdd/test_bdd_scripts_evals.py` |
| `scripts_gen_env_example.feature` | `scripts/gen_env_example.py` | "Answer from memory when a similar question was seen before" | 3 | `tests/bdd/test_bdd_scripts_tooling.py` |
| `scripts_render_graph.feature` | `scripts/render_graph.py` | "Fall back to the web and ingest what was found on a memory miss" | 3 | `tests/bdd/test_bdd_scripts_tooling.py` |
| `scripts_seed_memory.feature` | `scripts/seed_memory.py` | "Answer from memory when a similar question was seen before" | 2 | `tests/bdd/test_bdd_scripts_tooling.py` |
| `scripts_verify_redisvl.feature` | `scripts/verify_redisvl.py` | "Answer from memory when a similar question was seen before" | 6 | `tests/bdd/test_bdd_scripts_tooling.py` |
| `security_guardrails.feature` | `src/memagent/security/guardrails.py` | "Block malicious input at the guard before any model call" | 5 | `tests/bdd/test_bdd_security.py` |
| `security_patterns.feature` | `src/memagent/security/patterns.py` | "Block malicious input at the guard before any model call" | 2 | `tests/bdd/test_bdd_security.py` |
| `security_sanitizer.feature` | `src/memagent/security/sanitizer.py` | "Fall back to the web and ingest what was found on a memory miss" | 5 | `tests/bdd/test_bdd_security.py` |
| `state.feature` | `src/memagent/state.py` | "Log exactly one analytics record for every turn" | 1 | `tests/bdd/test_bdd_contracts.py` |
| `utils_errors.feature` | `src/memagent/utils/errors.py` | "Degrade gracefully when search succeeds but every page fetch fails" | 1 | `tests/bdd/test_bdd_utils.py` |
| `utils_reliability.feature` | `src/memagent/utils/reliability.py` | "Report failure when the query cannot be embedded" | 9 | `tests/bdd/test_bdd_utils.py` |
| `utils_timing.feature` | `src/memagent/utils/timing.py` | "Log exactly one analytics record for every turn" | 1 | `tests/bdd/test_bdd_utils.py` |
| `web_fetch.feature` | `src/memagent/web/fetch.py` | "Fall back to the web and ingest what was found on a memory miss" | 18 | `tests/bdd/test_bdd_web_fetch.py` |
| `web_search.feature` | `src/memagent/web/search.py` | "Fall back to the web and ingest what was found on a memory miss" | 8 | `tests/bdd/test_bdd_web_search.py` |
| `web_to_markdown.feature` | `src/memagent/web/to_markdown.py` | "Fall back to the web and ingest what was found on a memory miss" | 5 | `tests/bdd/test_bdd_web_fetch.py` |

## Function → scenario traceability matrix

225 coverage declarations for 152 functions.

| Function | Scenario | Feature file |
|---|---|---|
| `memagent.analytics.classify.Category._missing_` | Unknown category and question-type labels degrade to "other" instead of raising | `analytics_classify.feature` |
| `memagent.analytics.classify.QuestionType._missing_` | Unknown category and question-type labels degrade to "other" instead of raising | `analytics_classify.feature` |
| `memagent.analytics.classify._classify_user` | The classifier frames the user query as data inside query tags | `analytics_classify.feature` |
| `memagent.analytics.classify.classify` | A persistently failing classifier degrades to a null classification | `analytics_classify.feature` |
| `memagent.analytics.classify.classify` | A slow classification is cut off by the timeout and degrades to null | `analytics_classify.feature` |
| `memagent.analytics.classify.classify` | A transient model error is retried once and then succeeds | `analytics_classify.feature` |
| `memagent.analytics.classify.classify` | A well-formed model response yields a typed classification with usage | `analytics_classify.feature` |
| `memagent.analytics.report._counter_table` | A distribution table lists each key with its turn count, most frequent first | `analytics_report.feature` |
| `memagent.analytics.report._is_lookup` | Only turns that consulted memory count as lookups | `analytics_report.feature` |
| `memagent.analytics.report.aggregate` | Hit-rate is computed over lookup turns, with unclassified and error counts | `analytics_report.feature` |
| `memagent.analytics.report.aggregate` | Token usage and cost are aggregated by model and rendered | `analytics_report.feature` |
| `memagent.analytics.report.render_report` | The full report renders every section and escapes rich markup in user text | `analytics_report.feature` |
| `memagent.analytics.report.render_report` | Token usage and cost are aggregated by model and rendered | `analytics_report.feature` |
| `memagent.analytics.turnlog.TurnLogger.__init__` | The writer appends exactly one JSON line per record and creates missing directories | `analytics_turnlog.feature` |
| `memagent.analytics.turnlog.TurnLogger.log` | The writer appends exactly one JSON line per record and creates missing directories | `analytics_turnlog.feature` |
| `memagent.analytics.turnlog.build_turn_record` | A memory-hit record carries every schema field and no web block | `analytics_turnlog.feature` |
| `memagent.analytics.turnlog.build_turn_record` | A web-route record reports provider, results, fetched pages, and only persisted chunks | `analytics_turnlog.feature` |
| `memagent.analytics.turnlog.build_turn_record` | Per-page summary tokens are folded into a summary_llm bucket | `analytics_turnlog.feature` |
| `memagent.analytics.turnlog.build_turn_record` | Every turn record prices its token usage in USD | `analytics_turnlog.feature` |
| `memagent.analytics.turnlog.cost_usd` | Every turn record prices its token usage in USD | `analytics_turnlog.feature` |
| `memagent.app.Agent.__init__` | Constructing the agent compiles the graph once and mints a session id | `app.feature` |
| `memagent.app.Agent.answer` | Answering a novel question misses memory, reaches the web and cites its sources | `app.feature` |
| `memagent.app.Agent.ensure_ready` | The agent provisions its memory index once at startup and is idempotent | `app.feature` |
| `memagent.app.build_resources` | Building resources assembles the real clients without a live connection | `app.feature` |
| `memagent.app.build_resources` | Building resources activates opt-in tracing through the real environment | `app.feature` |
| `memagent.app.configure_logging` | Operational logging is wired to stderr so stdout stays pipe-clean | `app.feature` |
| `memagent.app.configure_tracing` | Tracing is off by default so no telemetry leaves the machine | `app.feature` |
| `memagent.app.configure_tracing` | Setting the tracing flag without an API key still keeps tracing off | `app.feature` |
| `memagent.app.configure_tracing` | Opting in to LangSmith exports the tracing environment for the graph run | `app.feature` |
| `memagent.app.new_turn_state` | A fresh turn starts allowed, thresholded from settings and unrouted until proven | `app.feature` |
| `memagent.cli._advance_status` | The live status names the step that runs next as each node finishes | `cli.feature` |
| `memagent.cli._ask` | A single question is answered through the agent facade | `cli.feature` |
| `memagent.cli._chat` | A blocked chat turn is refused and never re-enters replayed history | `cli.feature` |
| `memagent.cli._chat` | A cancelled turn (Ctrl-C) is discarded and the chat keeps going | `cli.feature` |
| `memagent.cli._chat` | A failed turn shows one clean error, never a hit banner then an apology | `cli.feature` |
| `memagent.cli._chat` | The chat REPL prints the hit banner, the answer, and its sources | `cli.feature` |
| `memagent.cli._emit` | Emitting to a non-terminal stdout stays byte-identical plain text | `cli.feature` |
| `memagent.cli._exit_redis_down` | A Redis outage is reported to stderr and exits non-zero | `cli.feature` |
| `memagent.cli._hit_banner` | The memory-hit banner shows the similarity to two decimals | `cli.feature` |
| `memagent.cli._print_sources` | Cited sources print one per line, and an empty list prints nothing | `cli.feature` |
| `memagent.cli._stream_turn` | Streaming a turn returns the merged state, the memory-search update, and the block flag | `cli.feature` |
| `memagent.cli._wipe` | Wiping memory drops and recreates the vector index | `cli.feature` |
| `memagent.cli.analytics` | analytics --json prints the aggregate object as JSON to stdout | `cli.feature` |
| `memagent.cli.analytics` | analytics prints friendly guidance when no turn log exists | `cli.feature` |
| `memagent.cli.analytics` | analytics renders the report tables over the turn log | `cli.feature` |
| `memagent.cli.ask` | ask presents the memory-hit banner and cited sources | `cli.feature` |
| `memagent.cli.ask` | ask prints the blocked banner and no sources for a guarded turn | `cli.feature` |
| `memagent.cli.ask` | ask refuses to run without an OpenAI key | `cli.feature` |
| `memagent.cli.ask` | ask reports a failed turn as a bare apology with a non-zero exit | `cli.feature` |
| `memagent.cli.ask` | ask shows the miss banner when it falls back to the web | `cli.feature` |
| `memagent.cli.ask` | ask shows the offline banner when Redis is down mid-turn | `cli.feature` |
| `memagent.cli.ask` | ask surfaces a Redis outage as a friendly error and non-zero exit | `cli.feature` |
| `memagent.cli.chat` | chat refuses to start without an OpenAI key | `cli.feature` |
| `memagent.cli.chat` | chat starts the interactive REPL when a key is configured | `cli.feature` |
| `memagent.cli.chat_help_text` | The chat help lists every command and both ways to stop | `cli.feature` |
| `memagent.cli.status_label` | status_label narrates each decision, colours it, and keeps the locked step names | `cli.feature` |
| `memagent.cli.wipe_memory` | wipe-memory reports a friendly error when Redis is unreachable | `cli.feature` |
| `memagent.graph.build_graph` | The graph screens input at the entry and can short-circuit a block to logging | `graph.feature` |
| `memagent.graph.build_graph` | The graph searches memory before the web and drains every path into logging | `graph.feature` |
| `memagent.interfaces.ChatLLM.complete` | A chat model returns generated text alongside a token-usage record | `interfaces.feature` |
| `memagent.interfaces.ChatLLM.parse` | A chat model parses a prompt into a typed schema instance with usage | `interfaces.feature` |
| `memagent.interfaces.Embedder.embed` | An embedder maps a batch of texts to fixed-width vectors | `interfaces.feature` |
| `memagent.interfaces.MemoryStore.ensure_ready` | A memory store can be asked to provision itself before first use | `interfaces.feature` |
| `memagent.interfaces.MemoryStore.is_fresh` | A store reports whether a URL hash was seen within the freshness window | `interfaces.feature` |
| `memagent.interfaces.MemoryStore.knn` | A memory store returns the raw nearest neighbours without applying the threshold | `interfaces.feature` |
| `memagent.interfaces.MemoryStore.store` | Storing a page's chunks returns one identifier per persisted chunk | `interfaces.feature` |
| `memagent.interfaces.PageFetcher.fetch` | A page fetcher returns cleaned documents for fetchable URLs | `interfaces.feature` |
| `memagent.interfaces.TurnLogger.log` | The turn logger appends exactly one JSON line per record | `interfaces.feature` |
| `memagent.interfaces.WebSearcher.search` | A web searcher returns ranked results mapped from the provider response | `interfaces.feature` |
| `memagent.llm.clients.OpenAIChatLLM.__init__` | Constructing a chat client pins its model, token cap and temperature | `llm_clients.feature` |
| `memagent.llm.clients.OpenAIChatLLM._call` | A completed answer carries the model text and token accounting | `llm_clients.feature` |
| `memagent.llm.clients.OpenAIChatLLM._parse_call` | A structured classification is returned together with its token usage | `llm_clients.feature` |
| `memagent.llm.clients.OpenAIChatLLM._usage` | Token accounting falls back to zero when the SDK omits usage | `llm_clients.feature` |
| `memagent.llm.clients.OpenAIChatLLM.complete` | A completed answer carries the model text and token accounting | `llm_clients.feature` |
| `memagent.llm.clients.OpenAIChatLLM.parse` | A structured classification is returned together with its token usage | `llm_clients.feature` |
| `memagent.llm.clients.OpenAIEmbedder.__init__` | A retry policy wraps the embedder's single network seam | `llm_clients.feature` |
| `memagent.llm.clients.OpenAIEmbedder._embed_call` | Embedding vectors are returned in the SDK's index order | `llm_clients.feature` |
| `memagent.llm.clients.OpenAIEmbedder.embed` | Embedding vectors are returned in the SDK's index order | `llm_clients.feature` |
| `memagent.llm.clients.build_openai_clients` | Building the client trio shares one transport with retries disabled | `llm_clients.feature` |
| `memagent.llm.clients.build_openai_clients` | The shared transport honours the base URL and fails fast without a key | `llm_clients.feature` |
| `memagent.llm.clients.build_openai_clients` | The shared transport is wrapped for LangSmith only when tracing is fully opted in | `llm_clients.feature` |
| `memagent.llm.prompts._escape_breakout` | A closing-tag breakout attempt inside content cannot terminate the wrapper | `llm_prompts.feature` |
| `memagent.llm.prompts._iso_now` | A freshly fetched web source is stamped with the current UTC fetch time | `llm_prompts.feature` |
| `memagent.llm.prompts.build_system_prompt` | The system prompt frames retrieved context as data and mandates source citations | `llm_prompts.feature` |
| `memagent.llm.prompts.wrap_context` | A stored memory hit is wrapped with its replayed provenance header | `llm_prompts.feature` |
| `memagent.llm.prompts.wrap_context` | Multiple fetched web pages are each wrapped with a numbered web-origin header | `llm_prompts.feature` |
| `memagent.memory.chunking.chunk_markdown` | A fragment below the minimum length is dropped entirely | `memory_chunking.feature` |
| `memagent.memory.chunking.chunk_markdown` | A long page is split into overlapping, size-bounded chunks | `memory_chunking.feature` |
| `memagent.memory.chunking.chunk_markdown` | A whole short page above the floor survives as a single chunk | `memory_chunking.feature` |
| `memagent.memory.chunking.chunk_markdown` | The per-page chunk count is capped for cost control | `memory_chunking.feature` |
| `memagent.memory.schema.assert_index_dims` | A mismatched embedding dimension is rejected while a match passes | `memory_schema.feature` |
| `memagent.memory.schema.build_schema` | The schema pins eleven fields and a cosine float32 vector | `memory_schema.feature` |
| `memagent.memory.schema.ensure_index` | Ensuring the index creates it once and is a no-op thereafter | `memory_schema.feature` |
| `memagent.memory.schema.get_index` | An async search index is built over the schema and a Redis client | `memory_schema.feature` |
| `memagent.memory.schema.wipe_index` | Wiping drops the index and its metadata hashes then recreates it empty | `memory_schema.feature` |
| `memagent.memory.store.RedisMemoryStore.__init__` | Constructing the store opens the shared web_memory index | `memory_store.feature` |
| `memagent.memory.store.RedisMemoryStore._io` | A Redis outage during an I/O op is translated while bugs surface loudly | `memory_store.feature` |
| `memagent.memory.store.RedisMemoryStore.ensure_ready` | A fresh Redis with no index is provisioned on first use instead of crashing | `memory_store.feature` |
| `memagent.memory.store.RedisMemoryStore.is_fresh` | The freshness gate is inclusive-inside and exclusive at the 24h boundary | `memory_store.feature` |
| `memagent.memory.store.RedisMemoryStore.knn` | A stored chunk is found again with its similarity attached at the 0.70 hit boundary | `memory_store.feature` |
| `memagent.memory.store.RedisMemoryStore.store` | Ingested page content round-trips and re-ingestion prunes stale chunks | `memory_store.feature` |
| `memagent.memory.store._as_memory_error` | A wrapped Redis outage is recognised as a typed memory error | `memory_store.feature` |
| `memagent.memory.store._epoch_to_iso` | A stored epoch timestamp is exposed as an ISO-8601 UTC instant | `memory_store.feature` |
| `memagent.memory.store.distance_to_similarity` | A cosine distance becomes a similarity by one minus the distance | `memory_store.feature` |
| `memagent.memory.store.make_redis_client` | The Redis client is built with bounded native retries | `memory_store.feature` |
| `memagent.memory.urls.canonicalize` | Tracking params, fragments and host casing collapse to one form | `memory_urls.feature` |
| `memagent.memory.urls.url_hash` | Variant spellings of one page share a stable 16-char identity | `memory_urls.feature` |
| `memagent.nodes.answer._dedupe_sources` | Duplicate source URLs collapse to a single reference | `nodes_answer.feature` |
| `memagent.nodes.answer.make_answer_failure` | The failure node returns a deterministic apology without calling any model | `nodes_answer.feature` |
| `memagent.nodes.answer.make_answer_from_memory` | A memory hit is answered from stored context and cites its source | `nodes_answer.feature` |
| `memagent.nodes.answer.make_answer_from_web` | A web-miss answer is grounded in fetched pages and bounds context per page | `nodes_answer.feature` |
| `memagent.nodes.answer.make_answer_from_web` | When no page can be fetched the agent degrades to snippets with a disclaimer | `nodes_answer.feature` |
| `memagent.nodes.embed.make_embed_query` | A successful embedding populates the query vector | `nodes_embed.feature` |
| `memagent.nodes.embed.make_embed_query` | An embedding failure clears the vector and records a step error | `nodes_embed.feature` |
| `memagent.nodes.fetch.make_fetch_pages` | A total fetch failure degrades gracefully instead of crashing | `nodes_fetch.feature` |
| `memagent.nodes.fetch.make_fetch_pages` | Unsafe URLs are filtered out and only the top N safe pages are fetched | `nodes_fetch.feature` |
| `memagent.nodes.guard.make_guard_input` | A benign question passes the guard untouched | `nodes_guard.feature` |
| `memagent.nodes.guard.make_guard_input` | A crashing screen keeps the agent available by failing open | `nodes_guard.feature` |
| `memagent.nodes.guard.make_guard_input` | A flagged query proceeds but is barred from being stored | `nodes_guard.feature` |
| `memagent.nodes.guard.make_guard_input` | Malicious input is refused at the guard with a canned message | `nodes_guard.feature` |
| `memagent.nodes.ingest.make_ingest_content` | A fetched page is sanitized, summarised, chunked and stored for future reuse | `nodes_ingest.feature` |
| `memagent.nodes.ingest.make_ingest_content` | A page whose chunker blows up degrades to a skipped doc without crashing the turn | `nodes_ingest.feature` |
| `memagent.nodes.ingest.make_ingest_content` | A recently ingested URL is not re-stored within the freshness window | `nodes_ingest.feature` |
| `memagent.nodes.ingest.make_ingest_content` | A skip-store turn persists nothing yet still chunks for the answer | `nodes_ingest.feature` |
| `memagent.nodes.ingest.make_ingest_content` | A store failure never blocks the in-hand answer | `nodes_ingest.feature` |
| `memagent.nodes.ingest.make_ingest_content` | A summary failure is tolerated and chunking still flows | `nodes_ingest.feature` |
| `memagent.nodes.ingest.make_ingest_content` | The summary input is capped so a huge page never blows the token budget | `nodes_ingest.feature` |
| `memagent.nodes.log.make_log_turn` | A blocked turn is still recorded in the turn log | `nodes_log.feature` |
| `memagent.nodes.log.make_log_turn` | A completed turn is classified, timed, and written as one full record | `nodes_log.feature` |
| `memagent.nodes.log.make_log_turn` | A failing turn logger never crashes the turn | `nodes_log.feature` |
| `memagent.nodes.memory.make_memory_search` | A Redis outage degrades to a miss labelled redis_down | `nodes_memory.feature` |
| `memagent.nodes.memory.make_memory_search` | An empty memory index is a normal miss, not an error | `nodes_memory.feature` |
| `memagent.nodes.memory.make_memory_search` | The raw top-k is returned unfiltered with the highest similarity surfaced | `nodes_memory.feature` |
| `memagent.nodes.search.make_web_search` | A search-provider failure degrades to an empty result set instead of raising | `nodes_search.feature` |
| `memagent.nodes.search.make_web_search` | A successful web search feeds the miss branch and records the provider | `nodes_search.feature` |
| `memagent.routers.route_after_embed` | A successful embedding proceeds to memory search and a missing vector fails the turn | `routers.feature` |
| `memagent.routers.route_after_fetch` | Fetched pages proceed to ingestion and nothing fetched answers from snippets | `routers.feature` |
| `memagent.routers.route_after_guard` | A blocked verdict is routed straight to logging while everything else proceeds | `routers.feature` |
| `memagent.routers.route_after_memory` | A similarity exactly at the 0.70 threshold is an inclusive memory hit | `routers.feature` |
| `memagent.routers.route_after_search` | Search results proceed to fetching and no results fails the turn | `routers.feature` |
| `memagent.security.guardrails.screen_input` | A benign question is allowed with no guardrail events | `security_guardrails.feature` |
| `memagent.security.guardrails.screen_input` | A direct instruction-override attempt is blocked | `security_guardrails.feature` |
| `memagent.security.guardrails.screen_input` | A zero-width evasion is normalised before matching | `security_guardrails.feature` |
| `memagent.security.guardrails.screen_input` | Each attack category resolves to its designed severity verdict | `security_guardrails.feature` |
| `memagent.security.guardrails.screen_input` | Over-long queries are truncated to the configured cap | `security_guardrails.feature` |
| `memagent.security.patterns._c` | The registry compiler produces case-insensitive matchers | `security_patterns.feature` |
| `memagent.security.patterns.max_severity` | Severity folding ranks HIGH above MEDIUM above nothing | `security_patterns.feature` |
| `memagent.security.sanitizer._flag` | A removal is only flagged when something was actually removed | `security_sanitizer.feature` |
| `memagent.security.sanitizer.sanitize` | An injection phrase is neutralised rather than deleted | `security_sanitizer.feature` |
| `memagent.security.sanitizer.sanitize` | Benign markdown is passed through unchanged | `security_sanitizer.feature` |
| `memagent.security.sanitizer.sanitize` | Dangerous HTML and payload constructs are stripped and flagged | `security_sanitizer.feature` |
| `memagent.security.sanitizer.strip_markdown_images` | The image stripper removes markdown images in place | `security_sanitizer.feature` |
| `memagent.state._merge_dicts` | Per-node latency and token contributions accumulate into one turn map | `state.feature` |
| `memagent.utils.errors.redis_down_in_chain` | A wrapped redis connection error is recognised through the cause chain | `utils_errors.feature` |
| `memagent.utils.reliability._is_retryable_fetch` | Page fetch retries only gateway errors and timeouts | `utils_reliability.feature` |
| `memagent.utils.reliability._is_retryable_llm` | Transient OpenAI errors are retryable while client errors are not | `utils_reliability.feature` |
| `memagent.utils.reliability._is_retryable_tavily` | Search retries cover timeouts, 429, and 5xx but never 4xx auth failures | `utils_reliability.feature` |
| `memagent.utils.reliability._max_wait` | Backoff wait caps collapse to zero under the test scale | `utils_reliability.feature` |
| `memagent.utils.reliability._status` | The HTTP status is extracted from both SDK and transport errors | `utils_reliability.feature` |
| `memagent.utils.reliability.fetch_retry` | A non-retryable page fetch becomes a non-fatal PageFetchError while a timeout is retried once | `utils_reliability.feature` |
| `memagent.utils.reliability.llm_retry` | A transient LLM call retries to success then an auth failure fast-fails as a typed error | `utils_reliability.feature` |
| `memagent.utils.reliability.summary_retry` | The page summary retries a transient error once then re-raises after the 2-attempt budget | `utils_reliability.feature` |
| `memagent.utils.reliability.tavily_retry` | Auth failures fall through to the fallback while exhausted search retries raise the typed error | `utils_reliability.feature` |
| `memagent.utils.timing.timed` | A stage timing is measured and merged without clobbering node-supplied timings | `utils_timing.feature` |
| `memagent.web.fetch.HttpxPageFetcher.__init__` | The fetcher handles redirects manually, with bounded concurrency and an honest User-Agent | `web_fetch.feature` |
| `memagent.web.fetch.HttpxPageFetcher._fetch_guarded` | A per-URL failure is swallowed into a skipped page | `web_fetch.feature` |
| `memagent.web.fetch.HttpxPageFetcher._fetch_one` | A hard 404 raises a page-fetch error without retrying | `web_fetch.feature` |
| `memagent.web.fetch.HttpxPageFetcher._fetch_one` | A non-HTML content type is skipped | `web_fetch.feature` |
| `memagent.web.fetch.HttpxPageFetcher._fetch_one` | A page that redirects to a private address is not followed | `web_fetch.feature` |
| `memagent.web.fetch.HttpxPageFetcher._fetch_one` | A redirect chain stores the final resolved URL | `web_fetch.feature` |
| `memagent.web.fetch.HttpxPageFetcher._fetch_one` | A transient read timeout is retried and then the page succeeds | `web_fetch.feature` |
| `memagent.web.fetch.HttpxPageFetcher._fetch_one` | An oversize body is abandoned rather than truncated | `web_fetch.feature` |
| `memagent.web.fetch.HttpxPageFetcher.fetch` | Every page failing yields an empty result set for the degraded path | `web_fetch.feature` |
| `memagent.web.fetch.HttpxPageFetcher.fetch` | One failing URL does not stop the others on a memory miss | `web_fetch.feature` |
| `memagent.web.fetch._extract_title` | The page title is extracted, unescaped, whitespace-collapsed and bounded | `web_fetch.feature` |
| `memagent.web.fetch._is_private_host` | A hostname resolving to a private IP is flagged private | `web_fetch.feature` |
| `memagent.web.fetch._is_private_host` | Private, loopback and link-local hosts are recognised | `web_fetch.feature` |
| `memagent.web.fetch._is_safe_fetch_target` | The SSRF target check rejects private hosts and non-HTTP schemes but accepts public URLs | `web_fetch.feature` |
| `memagent.web.fetch._registrable_domain` | Distinct organisations under a compound ccTLD are not collapsed | `web_fetch.feature` |
| `memagent.web.fetch._registrable_domain` | The registrable domain collapses to its last two labels | `web_fetch.feature` |
| `memagent.web.fetch.filter_urls` | Denylisted domains are dropped and each domain is capped for diversity | `web_fetch.feature` |
| `memagent.web.fetch.filter_urls` | Unsafe schemes and private hosts are removed by the URL filter | `web_fetch.feature` |
| `memagent.web.search.DdgsSearcher.__init__` | The keyless DuckDuckGo fallback maps result fields and ranks by order | `web_search.feature` |
| `memagent.web.search.DdgsSearcher.search` | The keyless DuckDuckGo fallback maps result fields and ranks by order | `web_search.feature` |
| `memagent.web.search.FallbackProvider.__init__` | A freshly built fallback provider has not yet chosen a provider | `web_search.feature` |
| `memagent.web.search.FallbackProvider.search` | On a memory miss the provider searches Tavily first and records it | `web_search.feature` |
| `memagent.web.search.FallbackProvider.search` | When Tavily rejects the key the provider degrades to the keyless fallback | `web_search.feature` |
| `memagent.web.search.FallbackProvider.search` | When every search provider fails the turn gets a typed unavailability error | `web_search.feature` |
| `memagent.web.search.TavilySearcher.__init__` | The Tavily searcher owns a reusable httpx client with bearer auth | `web_search.feature` |
| `memagent.web.search.TavilySearcher._post` | Transient rate limits are retried at the single POST call site | `web_search.feature` |
| `memagent.web.search.TavilySearcher.search` | A Tavily search returns ranked results and asks Tavily not to pre-extract content | `web_search.feature` |
| `memagent.web.to_markdown.to_markdown` | An empty precision pass retries once with recall | `web_to_markdown.feature` |
| `memagent.web.to_markdown.to_markdown` | Extractions below the floor are rejected as unusable | `web_to_markdown.feature` |
| `memagent.web.to_markdown.to_markdown` | Over-long extractions are capped at the maximum character budget | `web_to_markdown.feature` |
| `memagent.web.to_markdown.to_markdown` | The precision pass uses the configured trafilatura keyword arguments | `web_to_markdown.feature` |
| `memagent.web.to_markdown.to_markdown` | Two empty passes yield no markdown | `web_to_markdown.feature` |
| `scripts.capture_demo._banner` | The transcript banner names each turn's routing decision | `scripts_capture_demo.feature` |
| `scripts.capture_demo._capture` | Capturing a live session renders both turns as a miss-then-hit transcript | `scripts_capture_demo.feature` |
| `scripts.capture_demo.main` | Without a real OpenAI key the demo stays a pending placeholder | `scripts_capture_demo.feature` |
| `scripts.eval_grounding._render` | The scorecard prints per-case rows, an aggregate, and an honest disclaimer | `scripts_eval_grounding.feature` |
| `scripts.eval_grounding._run_mock` | The keyless mock run derives verdicts from real answers and passes on correct behaviour | `scripts_eval_grounding.feature` |
| `scripts.eval_grounding._run_real` | The real run drives the OpenAI-backed answerer and judge | `scripts_eval_grounding.feature` |
| `scripts.eval_grounding._run_real` | The real run exits non-zero when the judge reports a bad grounding verdict | `scripts_eval_grounding.feature` |
| `scripts.eval_grounding._score` | Scoring drives every fixed case through the answerer and the judge | `scripts_eval_grounding.feature` |
| `scripts.eval_grounding.main` | The grounding entrypoint runs keylessly under the mock flag and exits zero | `scripts_eval_grounding.feature` |
| `scripts.eval_grounding.main` | The grounding entrypoint without a key or the mock flag fails readably | `scripts_eval_grounding.feature` |
| `scripts.eval_lifecycle._page_html` | The mocked page repeats its question so it embeds as a later memory hit | `scripts_eval_lifecycle.feature` |
| `scripts.eval_lifecycle._run_mock` | The mock gate proves every fixed question misses then hits against real Redis | `scripts_eval_lifecycle.feature` |
| `scripts.eval_lifecycle._run_real` | The real-key run verifies miss-then-hit through the live Agent facade | `scripts_eval_lifecycle.feature` |
| `scripts.eval_lifecycle.main` | The lifecycle entrypoint runs the hard gate keylessly and exits zero | `scripts_eval_lifecycle.feature` |
| `scripts.eval_lifecycle.main` | The lifecycle entrypoint without a key or the mock flag fails readably | `scripts_eval_lifecycle.feature` |
| `scripts.gen_env_example.main` | Running the generator writes the template to the .env.example path | `scripts_gen_env_example.feature` |
| `scripts.gen_env_example.render` | Every Settings field is emitted, with secret-shaped fields blanked | `scripts_gen_env_example.feature` |
| `scripts.gen_env_example.render` | The rendered template reproduces the committed .env.example byte-for-byte | `scripts_gen_env_example.feature` |
| `scripts.render_graph.main` | The docs entry point prints the diagram and writes it into both doc files | `scripts_render_graph.feature` |
| `scripts.render_graph.render_mermaid` | The compiled graph renders to a deterministic mermaid diagram without any keys | `scripts_render_graph.feature` |
| `scripts.render_graph.splice` | Splicing into a document inserts one fenced mermaid block and stays idempotent | `scripts_render_graph.feature` |
| `scripts.seed_memory.main` | The seed entry point accepts inline text and reports what it stored | `scripts_seed_memory.feature` |
| `scripts.seed_memory.seed` | Seeding a page embeds and stores one chunk per chunk in Redis | `scripts_seed_memory.feature` |
| `scripts.verify_redisvl.check` | A capability that reports present is confirmed and logged as OK | `scripts_verify_redisvl.feature` |
| `scripts.verify_redisvl.check` | A probe that raises is caught and reported as absent rather than crashing | `scripts_verify_redisvl.feature` |
| `scripts.verify_redisvl.has_array_to_buffer` | The float32 vector-packing helper is importable from the installed redisvl | `scripts_verify_redisvl.feature` |
| `scripts.verify_redisvl.has_load_ttl` | The per-key TTL keyword on the index loader is detected in the installed redisvl | `scripts_verify_redisvl.feature` |
| `scripts.verify_redisvl.has_vector_query` | The KNN VectorQuery object is importable from the installed redisvl | `scripts_verify_redisvl.feature` |
| `scripts.verify_redisvl.main` | The verification report names the redisvl version and every probed signature | `scripts_verify_redisvl.feature` |

---
*Generated by a repo-external script from the `# covers:` declarations; regenerate after adding scenarios. The traceability gate keeps it honest.*
