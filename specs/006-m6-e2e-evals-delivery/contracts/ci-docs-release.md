# Contract — CI, Auto-Docs, Delivery & Release (`ci.yml`, `render_graph.py`, `capture_demo.py`, README, AI_USAGE, `v1.0`)

FR-017..025. Current `ci.yml` is a single lint+unit job (D10); `render_graph.py` exists keyless
(D2, D8); the eval/demo scripts are new.

## `.github/workflows/ci.yml` — finalize (FR-017, FR-018, D10)

```yaml
name: ci
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:8.2                       # MUST equal docker-compose.yml (R0 #11)
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping" --health-interval 5s
          --health-timeout 3s --health-retries 5
    steps:
      - uses: actions/checkout@v4               # pinned
      - uses: actions/setup-python@v5           # pinned
        with: { python-version-file: ".python-version" }
      - uses: astral-sh/setup-uv@v6             # pinned
      - run: uv sync --frozen
      - run: uv run ruff check . && uv run ruff format --check .          # (D11)
      - run: uv run pytest -m "not integration and not e2e" --cov=memagent --cov-report=term
      - run: uv run pytest -m "integration or e2e" --cov=memagent --cov-append --cov-report=term
        env: { REDIS_URL: "redis://localhost:6379/0" }
      - run: uv run python scripts/eval_lifecycle.py --mock
      - run: uv run python scripts/eval_grounding.py --mock
      - run: uv run coverage report            # REPORT ONLY — no --cov-fail-under
```

**Independent acceptance checks** — FR-017: (a) exactly one job; (b) steps in the order above;
(c) no `secrets.*` anywhere; (d) coverage step has no `--cov-fail-under`/threshold. FR-018:
(a) `services.redis.image == "redis:8.2"`; (b) setup-python uses `python-version-file`; (c) no
`actions/*@main`/unpinned use. Zero real keys — the only live dependency is the pinned redis.

## `ruff format` finalization (D11)

Before finalizing CI: `uv run ruff format .` once (cosmetic, **no logic change**), committed as a
**dedicated** "M6: repo-wide ruff format" commit (kept separate from logic commits). Then the CI
`ruff format --check .` step passes. Fallback (large/unacceptable diff): keep `ruff check .` only
and note in quickstart that FR-017's "format check" is satisfied by `ruff check` — decided on the
actual diff at implement time.

## `scripts/render_graph.py` — extend (FR-019, D2)

Keep the existing **keyless** resource build (all-`None` clients + `Settings(_env_file=None)`);
graph compilation touches no client, so it stays Redis-less. **Add** a between-marker splice:

```python
mermaid = build_graph(resources).get_graph().draw_mermaid()   # already there; prints today
block = f"```mermaid\n{mermaid}```"
for path in ("README.md", "docs/architecture.md"):
    replace_between(path, "<!-- BEGIN graph -->", "<!-- END graph -->", block)
# keep printing to stdout too (the DoD grep + M5 behavior)
```

`replace_between` rewrites only the text between the markers (creating the file/markers if
absent). **Acceptance**: a second run leaves the between-marker bytes identical (idempotent); the
block names all 10 nodes (`guard_input … log_turn`) and contains `__start__ --> guard_input`.

## `scripts/capture_demo.py` — new (FR-020, D13)

Real-key only (Constitution forbids GitHub Models for the recorded demo). Drives `Agent.answer`
over the same question twice via `build_test_resources`-style real wiring **against real OpenAI +
real search + real Redis**, capturing route banners + sources, and writes `docs/demo_transcript.md`
(mini at `temperature=0` for reproducibility). **Absent a real key**, `docs/demo_transcript.md` is
a committed **placeholder** marked "pending real-key capture" (Clarification Q1) — it does not
block the tag. **Acceptance (when captured)**: transcript shows MISS with web sources then HIT
`sim >= 0.70`.

## README — ten verbatim sections (FR-021)

README MUST contain, matching source wording (each an independent grep check): (1) the §10.4
quickstart incl. the **"Zero keys needed"** line; (2) the **T1–T4 threat-model table** verbatim
(T3 memory-poisoning centerpiece); (3) the **0.70 calibration** note (calibrated to
`text-embedding-3-small`; changing `EMBEDDING_MODEL` → re-tune `SIMILARITY_THRESHOLD` +
`wipe-memory`); (4) **TTL-is-coarse** + ETag/Last-Modified production upgrade; (5) **robots.txt**
limitation + production fix; (6) why **fetch+markdown stay in-house** (graded steps; local
trafilatura; no 2nd key); (7) **DuckDB** `duckdb -c "SELECT route, count(*) FROM
read_json_auto('logs/turns.jsonl') GROUP BY route"`; (8) **pip fallback**; (9) **worked paraphrase
example** (§15.2: verbatim re-ask → hit; paraphrase → depends; summary docs raise hit rate);
(10) **"deliberately not a ReAct/tool-calling agent"** (§2: hit/miss is a deterministic threshold
router in code, not model judgment; parallelism inside `fetch_pages`, not graph fan-out). The
mermaid graph sits between the `<!-- BEGIN graph -->` / `<!-- END graph -->` markers (render script).

> Doc accuracy: `make wipe` runs the `wipe-memory` CLI subcommand (target name ≠ CLI name, R0 #15);
> the 5 commands are clone → install uv → `make setup` → `make redis-up` → `make run`.

## `AI_USAGE.md` + `docs/ai_prompts/milestone-6.md` (FR-022)

`AI_USAGE.md` has all 8 sections (PLAN §11), contains the literal phrase **"the complete
instruction record"**, and points to `docs/ai_prompts/` which holds a chronological per-milestone
log through **M6** — the M6 entry appended **as the milestone lands** (never retroactively —
Constitution VII). Also finalize repo-root `DECISIONS.md` (verify it exists in the repo; scaffolded
M1) with the complete anti-churn record.

## Pre-tag re-verification (FR-023, D14) + `v1.0` (FR-024) + 5 commands (FR-025)

- **Re-verify** the keyless §14 facts into a dated note `docs/verification-2026-07-06.md` (or a
  MODEL_CHOICES/AI_USAGE section): dependency pins (from `uv.lock`), `redisvl`
  `create`/`VectorQuery`/`array_to_buffer` signatures, `draw_mermaid()`, model catalog ids +
  prices (public pricing). Record `temperature=0` on `gpt-5.4-mini` as **"pending real-key
  capture"** (R0 #13). Correct any drift in `config.py`/`.env.example`/`MODEL_CHOICES.md`.
- **Tag** `v1.0` on the commit where CI is green and every keyless-verifiable requirement passes;
  the three real-key artifacts (real-key `eval_lifecycle`, `capture_demo` transcript, temperature
  probe) may be "pending real-key capture" and do **not** block the tag (Clarification Q1).
- **5 commands** (FR-025): clone → `curl … uv install` → `make setup` → `make redis-up` →
  `make run` gives a live MISS→HIT; the zero-key path (`make test` + `eval_lifecycle --mock`)
  passes with no keys (unit subset dockerless; mock eval against the CI redis).

**Acceptance**: `git tag` lists `v1.0`; README greps hit all ten phrases; `AI_USAGE.md` contains
"the complete instruction record"; the dated verification note exists.
