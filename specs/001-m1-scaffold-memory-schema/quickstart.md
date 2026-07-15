# Quickstart Validation: Milestone 1 — Repo Scaffold, Toolchain & Memory Index Schema

**Date**: 2026-07-05 · Proves the feature end-to-end. Contracts: [contracts/](contracts/) ·
Data model: [data-model.md](data-model.md)

## Prerequisites

- Python 3.12, uv, Docker Desktop with compose v2 (`docker compose version` works)
- GitHub account with `gh` CLI authenticated (for the public-repo + CI close-out, SC-005)
- No API keys required anywhere below (SC-002)

## 1. Foundation boots (User Story 1 / SC-001 — the 5-command path)

```bash
cd ~/Desktop/epam/memory-first-agent    # repo root (Clarifications: deliverable subfolder)
make setup                               # uv sync + .env from .env.example
make redis-up                            # redis:8.2 + RedisInsight, blocks until healthy
uv run memagent wipe-memory              # → "Wiped and recreated index 'web_memory'."
```

Expected: all exit 0 in under 10 minutes on a clean machine; then open
`http://localhost:5540` → RedisInsight shows the empty `web_memory` index.
Deeper check: `docker exec memagent-redis redis-cli FT.INFO web_memory` lists the index with
prefix `chunk:` (single colon) and a 1536-dim FLAT cosine vector field.

## 2. CLI surface (US1 scenarios 4–5)

```bash
uv run memagent --help                   # lists exactly: chat, ask, analytics, wipe-memory
uv run memagent ask "how does redis vector search work"   # echoes query + "wired in M2", exit 0
uv run memagent chat                     # "wired in M4" banner, exit 0
uv run memagent analytics                # "wired in M4" notice, exit 0
```

## 3. Configuration single-source (User Story 2 / SC-004)

```bash
uv run python - <<'EOF'
from memagent.config import Settings
s = Settings()
assert s.similarity_threshold == 0.7 and s.embedding_dim == 1536
assert s.memory_index_name == "web_memory" and s.memory_ttl_seconds == 604800
assert s.openai_api_key == ""            # keyless construction works (FR-018)
print("Settings defaults OK")
EOF
SIMILARITY_THRESHOLD=0.85 uv run python -c \
  "from memagent.config import Settings; assert Settings().similarity_threshold == 0.85; print('env override OK')"
uv run python scripts/gen_env_example.py && git diff --exit-code .env.example   # byte-identical
```

## 4. Index lifecycle & idempotency (User Story 3 / SC-003)

```bash
uv run memagent wipe-memory && uv run memagent wipe-memory   # both exit 0 (FR-019)
docker compose stop redis
uv run memagent wipe-memory; echo "exit=$?"                  # non-zero + readable error, no traceback wall
docker compose start redis
uv run python - <<'EOF'
from memagent.config import Settings
from memagent.memory.schema import assert_index_dims
assert_index_dims(1536, Settings())                          # returns silently
try:
    assert_index_dims(3072, Settings()); raise SystemExit("should have raised")
except ValueError as e:
    assert "wipe-memory" in str(e); print("dimension contract OK")
EOF
```

## 5. Quality gates & delivery guardrails (User Story 4 / SC-005, SC-006)

```bash
uv run ruff check .                                          # lint clean
uv run pytest -m "not integration and not e2e"               # smoke test green, keyless
uv sync --locked                                             # lockfile resolves (FR-002)
grep -c '^## ' AI_USAGE.md                                   # 8 headings (FR-012)
test -s docs/ai_prompts/milestone-1.md && echo "prompt log present"
head -1 LICENSE                                              # MIT
# Close-out (Clarifications Q3): publish + live CI (repo was git-initialized in task T001)
git add -A && git commit -m "M1: scaffold, toolchain, memory index schema"
gh repo create memory-first-agent --public --source=. --push
gh run watch                                                 # single job: ruff → unit tests → green
```

Expected: CI completes green with zero repository secrets configured.

## Done when

Every command above behaves as stated — that satisfies SC-001…SC-006 and the demoable
outcome from PLAN §13 (M1 row). Then append the milestone-1 prompts to
`docs/ai_prompts/milestone-1.md` (Constitution P-VII) before starting Milestone 2.
