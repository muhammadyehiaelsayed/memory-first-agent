# Quickstart / Validation — M6 Integration/E2E, Evals, CI, Docs, v1.0

Prove M6 end to end. Contracts: `contracts/test-fixtures.md`, `contracts/integration-e2e.md`,
`contracts/eval-harnesses.md`, `contracts/ci-docs-release.md`. Types + consumed signatures:
`data-model.md`. Run from `memory-first-agent/`.

## Prerequisites

- `uv sync` (no new deps — pytest/pytest-asyncio/respx/pytest-cov/ruff pinned since M1/M5).
- Keyless for unit + both `--mock` evals; integration/e2e + `eval_lifecycle --mock` need
  `make redis-up` (`redis:8.2`). The captured demo + real-key lifecycle + temperature probe need
  a real `OPENAI_API_KEY` and are **pending real-key capture** (Clarification Q1) — not tag gates.

## Gate 0 — conftest + dirs exist (FR-001..005)

```bash
test -f tests/conftest.py && test -d tests/integration && test -d tests/e2e
uv run python -c "import tests.conftest"    # importable (or: pytest --collect-only)
```

## Gate 1 — unit subset, zero keys / no Redis / no network (US1 fixtures + regression)

```bash
uv run pytest -m "not integration and not e2e" -q      # 103 prior + new fixture tests, all green
uv run ruff check . && uv run ruff format --check .     # D11: format pass applied first
```
With **Docker stopped**, integration/e2e report `skipped` (never `error`) — FR-004.

## Gate 2 — Redis integration round-trip (US1, FR-006..009)

```bash
make redis-up
uv run pytest -m integration -q     # tests/integration/test_redis_store.py
# idempotent ensure_index x2 (one index); store->knn round-trip (text/url/title);
# monkeypatched-clock stored_at == _epoch_to_iso(1751625600); similarity 1.0 / 0.0 / 0.70+-1e-6
```

## Gate 3 — e2e lifecycle miss→hit (US1, FR-010..012) — THE core proof

```bash
uv run pytest -m e2e tests/e2e/test_lifecycle.py -v
# turn 1: route=memory_miss_web_search, a web source, tavily call_count==1
# turn 2: route=memory_hit, similarity>=0.70, a memory source (URL==turn1), tavily call_count STILL 1
# turns.jsonl: exactly 2 records [memory_miss_web_search, memory_hit], 2nd similarity_top>=0.70, tokens non-empty
```

## Gate 4 — eval harnesses (US2, FR-013..016)

```bash
uv run python scripts/eval_lifecycle.py --mock ; echo "exit=$?"   # 0 healthy; 1 (names q) if any non-miss-then-hit — needs redis
uv run python scripts/eval_grounding.py --mock ; echo "exit=$?"   # 0, keyless AND redis-less; 3-dim scorecard + "demonstration, not a benchmark"
uv run python scripts/eval_lifecycle.py ; echo "exit=$?"          # no key -> readable "OPENAI_API_KEY required", non-zero, no traceback
```

## Gate 5 — CI single green job (US2, FR-017, FR-018)

Push; the one `build` job runs: `ruff check`+`ruff format --check` → unit → integration/e2e
(`redis:8.2` service, `REDIS_URL`) → `eval_lifecycle --mock` → `eval_grounding --mock` → coverage
report. Inspect `ci.yml`: one job; steps in that order; **no `secrets.*`**; **no
`--cov-fail-under`**; `services.redis.image == redis:8.2`; `python-version-file: .python-version`;
`actions/*` pinned (`@v4/@v5/@v6`, none `@main`).

## Gate 6 — auto-generated docs (US3, FR-019, FR-020)

```bash
uv run python scripts/render_graph.py                 # splices mermaid into README + docs/architecture.md
git diff --quiet README.md docs/architecture.md || echo "first run wrote"
uv run python scripts/render_graph.py                 # second run
git diff README.md docs/architecture.md               # EMPTY between markers (idempotent, FR-019)
grep -c -E "guard_input|embed_query|memory_search|answer_from_memory|web_search|fetch_pages|ingest_content|answer_from_web|answer_failure|log_turn" README.md   # all 10 nodes
# capture_demo (real key): docs/demo_transcript.md shows MISS(web) then HIT(sim>=0.70); else a "pending real-key capture" placeholder
```

## Gate 7 — delivery: README + AI_USAGE + re-verification + v1.0 (US4, FR-021..025)

```bash
for p in "Zero keys needed" "Memory poisoning" "read_json_auto" "not a ReAct" "robots.txt" "ETag"; do grep -q "$p" README.md && echo "ok: $p" || echo "MISSING: $p"; done
grep -q "the complete instruction record" AI_USAGE.md && test -f docs/ai_prompts/milestone-6.md
test -f docs/verification-2026-07-06.md    # dated §14 re-verify note (temperature=0 marked pending)
test -s DECISIONS.md                        # finalized anti-churn record (repo root)
# 5-command live path (real key + Docker): clone -> install uv -> make setup -> make redis-up -> make run  => MISS then HIT
git tag | grep -x v1.0
```

## Definition of Done (spec §9, adapted)

- [ ] `tests/conftest.py` created (fixtures `settings`/`fake_embedder`/`fake_llm`/`redis_url`/
      `clean_index` + `build_test_resources()`); the 12 existing unit files are not rewritten (local
      fakes/logic unchanged, Ruling A) and still green — 7 of them receive whitespace-only
      reformatting from the separate D11 `ruff format` commit (recheck E).
- [ ] `pytest -m "not integration and not e2e"` passes with no Redis/network/keys; integration/e2e
      `skipped` when Redis is down (Gate 1).
- [ ] `pytest -m "integration or e2e"` passes on `redis:8.2` (Gates 2–3).
- [ ] e2e asserts turn 1 miss (call_count 1) + turn 2 hit (sim≥0.70, call_count still 1) + 2 turn
      records (Gate 3).
- [ ] `eval_lifecycle --mock` exits 0 healthy / 1 on any non-miss-then-hit; `eval_grounding --mock`
      exits 0 keyless with a 3-dim scorecard (Gate 4).
- [ ] CI is one green job (ruff→unit→integration/e2e→both eval mocks→coverage report), `redis:8.2`,
      no secrets, no coverage gate, pinned actions (Gate 5).
- [ ] `render_graph.py` writes an idempotent 10-node mermaid into README + `docs/architecture.md`
      (Gate 6); `docs/demo_transcript.md` captured or a "pending real-key capture" placeholder.
- [ ] README has all ten verbatim sections (Gate 7); `AI_USAGE.md` + `docs/ai_prompts/milestone-6.md`
      appended non-retroactively (Constitution VII); `DECISIONS.md` finalized.
- [ ] Dated §14 re-verification note (`temperature=0` on `gpt-5.4-mini` marked "pending real-key
      capture"); drift corrected.
- [ ] `ruff format` applied once (D11) as a separate commit; CI `ruff format --check` green.
- [ ] `v1.0` tagged on the green, keyless-verified commit; the 5-command live path yields MISS→HIT
      and the zero-key path passes (Gate 7).
