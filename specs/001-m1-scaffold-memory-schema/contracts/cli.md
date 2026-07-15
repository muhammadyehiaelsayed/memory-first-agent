# Contract: `memagent` CLI (M1 surface)

Entry point: `[project.scripts] memagent = "memagent.cli:app"` (Typer,
`add_completion=False`). Exactly four subcommands — no more, no fewer (FR-006).

| Command | Args | Exit 0 when | Output contract | Side effects |
|---|---|---|---|---|
| `wipe-memory` | — | index dropped + recreated (or created fresh) | `Wiped and recreated index 'web_memory'.` | Redis only; idempotent (FR-019) |
| `ask` | `QUERY` (str, required) | always (stub) | echoes the query verbatim + "wired in M2" notice | none — no network, no Redis |
| `chat` | — | always (stub) | one-line "wired in M4" banner | none |
| `analytics` | — | always (stub) | one-line "wired in M4" notice | none |

Failure contract (M1): `wipe-memory` with Redis down → exit code ≠ 0, single readable error
line naming `settings.redis_url`; never a bare traceback as the only output.

`memagent --help` lists exactly the four subcommands; `uv run memagent --help` exits 0
straight after `uv sync` (FR-004).

## Replacement schedule (Constitution: replacing a stub must not change call sites)

- `ask` → M2 (real answer via the graph/Agent facade)
- `chat` → M4 (rich REPL streaming graph updates, hit/miss banners)
- `analytics` → M4 (rich report over `logs/turns.jsonl`)
- `wipe-memory` → permanent as delivered (M5 may add typed-error wrapping in the layers
  beneath it, not in the command's contract)
