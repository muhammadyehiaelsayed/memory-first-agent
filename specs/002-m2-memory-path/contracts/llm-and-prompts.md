# Contract: `memagent.llm` — clients and prompts (M2 thin, seams to M4/M5)

## `llm/clients.py` (Ruling D — the wrapper seam exists from day one)

- **`OpenAIEmbedder(settings)`**: builds
  `AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None,
  max_retries=0, timeout=45.0)`; `dim = settings.embedding_dim` (1536);
  `embed(texts) -> list[list[float]]` via `model=settings.embedding_model`, vectors in
  input order, exactly one call-site.
- **`OpenAIChatLLM(settings, model)`**: same client construction;
  `complete(system, messages) -> CompletionResult(text, usage)` with `max_tokens=2048`,
  `temperature=0`; `usage = {"model": model, "input_tokens": …, "output_tokens": …}`.
  `parse()` exists but is basic — M4 finalizes (structured output, `max_tokens=256`,
  usage plumbing).
- **Retry ownership**: `max_retries=0` is mandatory (constitution P-III); NO retry loop
  anywhere in M2 — M5's tenacity wraps the single call-sites.
- **M4 finalization notice** (do not fight it): constructors become
  `OpenAIEmbedder(client, model, dim)` / `OpenAIChatLLM(client, model, max_tokens,
  temperature)` behind `build_openai_clients(settings)`; the `embed`/`complete`
  interfaces are stable, so node code written in M2/M3 is untouched.
- **GitHub Models dev mode (Clarifications 2026-07-05)**: for all M2 live calls,
  `OPENAI_BASE_URL` points at the GitHub Models endpoint and the key is a fine-grained
  PAT (`models: read`). Dev-mode catalogue ids (e.g. `openai/gpt-5.4-mini`) are set via
  env for the session — production defaults in `Settings` are never rewritten.
- **FR-M2-25 verification duties** (record pass/fail + actual id strings in
  `docs/ai_prompts/milestone-2.md`): (1) the three catalogue ids resolve on GitHub
  Models; (2) `gpt-5.4-mini` accepts `temperature=0` (a single live sanity call — the
  validation *logic* is M4's).

## `llm/prompts.py` (Ruling E — **API FINAL as of M2**)

```python
def build_system_prompt() -> str: ...                       # no args — FINAL signature
def wrap_context(sources, origin) -> str: ...               # origin: "memory" | "web" — FINAL
```

- M2 bodies (basic): system prompt states that everything inside `<untrusted_context>` is
  quoted data and never instructions, and that the answer MUST end with a "Sources:"
  section. `wrap_context` puts all sources in ONE `<untrusted_context>` block, each
  preceded by a minimal header carrying at least `source_url`, with `origin` recorded.
- Call sites fixed now: `answer_from_memory` → `wrap_context(memory_hits, "memory")`;
  M3's `answer_from_web` → `wrap_context(sources, "web")`.
- M5 hardening (provenance headers `fetched_at`/`sanitizer_flags`, tag-breakout escaping,
  user-question-last, cite-only-`source_url` rule text) is a **pure body swap** — any
  signature change is a contract violation.
