# Design Decisions (finalized in M6, extended at v1.3)

Key technology rulings for this repo, seeded at M1, finalized at M6 (2026-07-06), and extended
at v1.3 with the BDD-layer rulings. The standing rulings below are binding from day one; the
anti-churn list was re-verified against the M2–M6 specs and remains the complete cut-scope
record cited by every milestone's plan.

## Locked at M1

- **Redis 8 (`redis:8.2`)** via **redisvl >=0.22,<0.24** — FT.* vector search in core;
  redis-stack is EOL (documented last-resort fallback only). Verified live 2026-07-05.
- **FLAT / cosine / float32 / 1536** index `web_memory` — exact KNN keeps the 0.70 routing
  deterministic; HNSW is the documented >100k-vector growth path. `similarity = 1 − distance`
  (conversion lives in `memory/store.py` only, from M2); hit ⇔ similarity ≥ 0.70 **inclusive**.
- **`Settings` (`config.py`) is the single source of every number**; `.env.example` is
  generated from it (`scripts/gen_env_example.py`) so docs cannot drift.
- **Python 3.12 + uv** (committed `uv.lock`, pip fallback documented), src layout, Typer CLI.
- **One OpenAI key** for LLMs + embeddings (clients land in M2/M4); optional
  `OPENAI_BASE_URL` → GitHub Models for free development only, never the recorded demo.

## Locked at v1.3 (BDD layer)

- **pytest-bdd scenarios run as plain pytest items** — no separate BDD runner; the suite runs
  in CI with everything else.
- **One Gherkin scenario per module-level function** (one feature file per module), each
  derived from the root feature's main-functionality scenarios.
- **AST-derived bidirectional `# covers:` gate** (`tests/bdd/test_bdd_traceability.py`) —
  a missing or stale declaration fails the build; `docs/BDD.md` is the generated index.
- **Keyless by default** — redis-backed scenarios auto-skip when Redis is unreachable.

## Standing anti-churn rulings (do NOT re-add; evaluated twice and rejected)

- The **0.50 weak-memory salvage route** (no env var, no route) and the 2-hit chunk-drop policy.
- **Canary token** and **output URL-defang allowlist** (stretch only).
- **Redis turn-log mirror** — `logs/turns.jsonl` (JSONL) stays the single source of truth.
- **CI *line-coverage* gate** — a coverage *report* is emitted; no coverage-% threshold fails
  the build. (Distinct from the v1.3 BDD traceability gate, which *does* fail the build on
  missing function→scenario coverage.)
- **`GUARD_LLM_CHECK`** gray-zone LLM classifier (stretch only).
- **Token streaming** — the REPL streams graph *updates*, not tokens.
- **Deep session memory** — chat history is the REPL's last 6 turns; the Redis memory is
  the assignment's knowledge store, not a conversation store.
