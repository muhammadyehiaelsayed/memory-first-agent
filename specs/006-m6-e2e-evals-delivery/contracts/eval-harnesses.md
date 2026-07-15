# Contract — Eval Harnesses (`scripts/eval_lifecycle.py`, `scripts/eval_grounding.py`)

FR-013..016. Both are new standalone scripts (absent — D15); neither is a pytest. They run as
files (`python scripts/…py`), so the repo root is NOT on `sys.path` and `tests/` is not an installed
package (pyproject packages only `src/memagent`; no `__init__.py`; no pytest `pythonpath`) — every
script that imports from `tests.conftest` MUST first prepend the repo root (recheck H):
`import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))`.
**`eval_lifecycle` imports `build_test_resources()`** (D2 — real store, live `redis:8.2`).
**`eval_grounding --mock` does NOT** — it uses `FakeLLM` directly as answerer + judge, no store/index
(keyless AND redis-less — D13, recheck I).

## `scripts/eval_lifecycle.py` — hard gate (FR-013, FR-014)

```
Usage: python scripts/eval_lifecycle.py [--mock]
  --mock : FakeLLM + FakeEmbedder + respx-mocked search/fetch, REAL Redis (CI).
  (no flag): real OpenAI + real search; requires OPENAI_API_KEY (manual, pre-submission).
```

**Question set (D13 — three query-dominated defaults, §6.5):**
`"How does Redis vector search work?"`, `"What is cosine similarity?"`,
`"How do I set a TTL on a Redis key?"` — each mocked page repeats its own question verbatim.

**--mock flow (needs a live `redis:8.2`)**:
1. `settings = Settings(_env_file=None, wait_cap_scale=0.0, tavily_api_key="test-key")` (D3).
2. `wipe_index(get_index(settings, client))` once (clean slate).
3. For each question: enter a `respx.mock(...)` context with a `POST /search` (200, one result)
   and a `GET <url>` (200, query-dominated HTML, no redirect); `agent =
   Agent(build_test_resources(settings, client))  # Agent builds the graph itself (recheck A)`; `r1 = await agent.answer(q)`;
   `r2 = await agent.answer(q)`.
   - **PASS** iff `r1.route == "memory_miss_web_search"` AND `r2.route == "memory_hit"` AND
     `r2.similarity >= 0.70`.
   - Reset the index between questions (wipe) OR key each question's page/URL uniquely so turn-1 of
     question N is a genuine miss.
4. Print a per-question line; **exit 0** iff all pass, else **exit 1** naming the failing question.

**Acceptance**:
- `python scripts/eval_lifecycle.py --mock; echo $?` → `0` on a healthy build.
- A deliberately non-query-dominated turn-2 page → the failing question is named, **exit 1**.
- (FR-014) no `--mock` and no `OPENAI_API_KEY` → readable `"OPENAI_API_KEY required"` to stderr,
  **non-zero exit, no traceback** (guard at top: `if not mock and not settings.openai_api_key:
  print(...); raise SystemExit(2)`). This real-key run is **not** a `v1.0` gate (Clarification Q1).

> Redis-less by design? **No** — `--mock` still exercises the real store (the whole point is the
> real KNN lifecycle). It runs in CI behind the `redis:8.2` service. Only `eval_grounding --mock`
> is redis-less.

## `scripts/eval_grounding.py` — demonstration (FR-015, FR-016)

~120 lines (mock + real-key modes; the original "~40–60" was optimistic). Honest **demonstration, not a benchmark** (printed + README). 5–8 fixed cases
`(question, context, expect ∈ {"grounded","abstain"})`:
- **grounded**: context has the answer + a `source_url`; the answerer must answer and cite it.
- **abstain**: context empty/off-topic; the answerer must refuse ("insufficient context").

Judge = the **nano** model via `analytics_llm.parse(system, user, GroundingVerdict)`:

```python
class GroundingVerdict(BaseModel):
    grounded: bool
    citations_valid: bool
    abstained_correctly: bool
```

**--mock (keyless AND redis-less — D13)**: `FakeLLM` is both answerer and judge; its
`schema_factory` returns a passing `GroundingVerdict`; no API key, no Redis. Print a per-case row
+ an aggregate for grounding / citation-validity / abstention, and a line stating it is a
**demonstration, not a benchmark**; **exit 0** (non-gating).

**Acceptance**:
- `python scripts/eval_grounding.py --mock; echo $?` → `0` with no network, no Redis.
- Scorecard shows one row per case (5–8) + a three-dimension aggregate; the demonstration
  disclaimer is present; file is a small single-purpose script (~120 lines).

> The mock judge always returning "pass" is intentional — `--mock` proves the harness *plumbing*
> (answerer→judge→scorecard→exit 0) keylessly; the real signal comes from the real-key run
> (manual). Do not add a gate here (only `eval_lifecycle` gates — Constitution VI).
