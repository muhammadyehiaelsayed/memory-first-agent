# Contract: Finalized LLM clients (`llm/clients.py`, `app.py`) — FR-001…008

**Consumers**: answer nodes (M2/M3, unchanged), `ingest_content` summaries (M3, unchanged),
`log_turn` classifier (M4), M5's tenacity decorators, M6's e2e/evals.

## OpenAIChatLLM — final shape (edits M2's class in place; Ruling D)

```python
CONVERSATION_MAX_TOKENS = 2048   # module constants, not env vars
ANALYTICS_MAX_TOKENS    = 256

class OpenAIChatLLM:                     # implements interfaces.ChatLLM (unchanged Protocol)
    def __init__(self, client: AsyncOpenAI, model: str, max_tokens: int,
                 temperature: float | None = 0.0) -> None: ...
    async def complete(self, system, messages) -> CompletionResult: ...
    async def parse(self, system, user, schema) -> tuple[BaseModel, dict]: ...
    # SEAM (Ruling D): the ONLY places that touch self._client — M5 decorates here.
    async def _call(self, **kw):        # chat.completions.create(**kw)
    async def _parse_call(self, **kw):  # chat.completions.parse(**kw)
```

Behavior rules:

1. `complete()` body: build messages (`system` + `*messages`), pass
   `max_tokens=self._max_tokens`, include `temperature` ONLY when `self._temperature` is
   not None; call `_call`; return `CompletionResult(text=content or "", usage=…)` with
   usage from `resp.usage.prompt_tokens/completion_tokens` and `model=self._model`
   (missing `resp.usage` → zeros, as M2 already does).
2. `parse()` body: same construction with `response_format=schema` and
   `max_tokens=self._max_tokens`; call `_parse_call`; return
   `(resp.choices[0].message.parsed, usage)` — same 3-key usage dict.
3. `complete`/`parse` MUST NOT reference `self._client` directly (FR-006 accept:
   inspection of both bodies shows only `_call`/`_parse_call`).
4. `OpenAIEmbedder` is reconciled to the shared client:
   `OpenAIEmbedder(client, model, dim)` — `embed()` behavior byte-identical to M2's.

## build_openai_clients(settings)

```python
def build_openai_clients(settings) -> tuple[OpenAIChatLLM, OpenAIChatLLM, OpenAIEmbedder]
```

- Empty `settings.openai_api_key` → `raise SystemExit("OPENAI_API_KEY is not set — see
  .env.example (one key covers LLMs + embeddings).")` — one readable line (FR-005).
- ONE `AsyncOpenAI(api_key=…, base_url=settings.openai_base_url or None, max_retries=0,
  timeout=float(settings.llm_timeout_s))` shared by all three clients.
- Returns: conversation (`settings.conversation_model`, 2048, `temperature=0.0`),
  analytics (`settings.analytics_model`, 256, `temperature=0.0`), embedder
  (`settings.embedding_model`, `settings.embedding_dim`).

## app.py rewiring (Ruling D finalisation)

`build_resources()` replaces the two `OpenAIChatLLM(settings, model)` constructions and
`OpenAIEmbedder(settings)` with one `build_openai_clients(settings)` call; the module-level
`_client(settings)` helper in `llm/clients.py` is deleted (nothing else uses it —
verified). `assert_index_dims(embedder.dim, settings)` call stays. Everything else in
`build_resources` (Redis, searcher, fetcher) is untouched; `_NoopTurnLogger` is replaced by
the real `TurnLogger(settings.turn_log_path)` (see turn-log contract).

## FR-007 live probe (real key — Clarify Option B)

Run once at implement time (T-M4-04 equivalent), record verbatim outcome in
`MODEL_CHOICES.md` + `docs/ai_prompts/milestone-4.md`:

```bash
uv run python -c "import asyncio,os; from openai import AsyncOpenAI; \
c=AsyncOpenAI(api_key=os.environ['OPENAI_API_KEY'], base_url=os.environ.get('OPENAI_BASE_URL') or None); \
print(asyncio.run(c.chat.completions.create(model='gpt-5.4-mini', temperature=0, max_tokens=8, \
messages=[{'role':'user','content':'ping'}])).choices[0].message.content)"
```

Accept: HTTP 200 + short reply — validating BOTH `temperature=0` and `max_tokens`
acceptance on the pinned id (research D2). Rejection contingency: `temperature` 400 →
construct the conversation client with `temperature=None` and document; `max_tokens` 400 →
swap the kwarg to `max_completion_tokens` inside `_call`/`_parse_call` only, and document.
Never a silent model swap.

## Acceptance mapping

| FR | Check |
|---|---|
| FR-001/002 | unit: stubbed `_call`/`_parse_call` responses → exact usage dicts |
| FR-003/004 | unit: `build_openai_clients` products carry pinned model/max_tokens/temperature; shared AsyncOpenAI has `max_retries==0`, `timeout==45.0` |
| FR-005 | unit: empty key → SystemExit w/ readable message; base_url plumbed when set |
| FR-006 | unit: `inspect.getsource(complete/parse)` contains no `self._client.` |
| FR-007 | manual live probe above (real key) |
| FR-008 | `MODEL_CHOICES.md` grep checks (see quickstart) |
