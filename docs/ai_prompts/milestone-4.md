# Milestone 4 — Complete instruction record (appended 2026-07-05)

Chronological log of every instruction that drove Milestone 4 (finalized LLM clients,
turn log, classifier, analytics CLI, chat REPL), per the disclosure rule in `AI_USAGE.md`
(Constitution P-VII: appended per milestone, never retroactively). Tooling: Claude Code
(Fable 5) + GitHub Spec Kit at the planning workspace root; the milestone source spec is
`specs/milestone-4-llms-logging-analytics.md`.

## 1. Spec Kit phase prompts (user-issued, verbatim)

1. `/speckit-specify for Milestone 4, feeding it specs/milestone-4-llms-logging-analytics.md`
   → `specs/004-m4-llms-logging-analytics/spec.md` (24 FRs: FR-001…022 ↔ FR-M4-01…22,
   +FR-023 AI-disclosure, +FR-024 demoable outcome; 4 user stories; 16/16 quality
   checklist).
2. `/speckit-clarify` → ONE question asked: FR-M4-07's `temperature=0` probe needs the
   pinned `gpt-5.4-mini`, which GitHub Models does not serve — will a real OpenAI key be
   available? **User answer: "B"** — a real platform key is provided for the one-off
   probe only; all other M4 dev stays on the free GitHub Models endpoint.
3. `/speckit-plan` → plan.md (Constitution Check 11/11 PASS pre- and post-design),
   research.md (D1–D11), data-model.md, 4 contracts, quickstart.md. The plan phase probed
   the repo BEFORE cutting tasks (the M3 lesson) — findings in §2.
4. Mid-plan user request: *"how to get [the real key] … i already made a fine-grained
   key github_pat_… "* then *"try it"* twice → live PAT probes (§3).
5. `/speckit-tasks` → tasks.md, 27 tasks in 7 phases (US1 turn log → US2 analytics →
   US3 clients → US4 REPL), traceability map to the source T-M4-01…16.
6. `/speckit-analyze` → 3 findings (I1 HIGH, I2 MEDIUM, U1 LOW; §4). User: **"fix all of
   them"** → remediated in tasks/contracts/data-model/research before implementation.
7. `/speckit-implement` → executed 26 of 27 tasks (T019 pending the real key; §6).

## 2. Plan-phase live verifications (Constitution P-IX)

| Check | Method | Result (2026-07-05) |
|---|---|---|
| Repo-state vs source-spec assumptions | read clients/answer/log/app/interfaces on main `20145bd` | `complete()` ALREADY returns `CompletionResult` w/ usage; answer nodes ALREADY write `tokens.answer_llm` (source T-M4-08b pre-satisfied); log stub is `nodes/log.py` NOT `log_turn.py`; turnlog/report/timing exist as M1 placeholder files; `Agent.answer` already stamps turn bookkeeping |
| openai 2.44.0 parse surface | `inspect.signature` | `chat.completions.parse` exists; accepts `response_format`, `max_tokens`, `max_completion_tokens` |
| structlog 26.1.0 | attribute checks | `contextvars.merge_contextvars`/`bind`/`clear`, `PrintLoggerFactory`, `dev.ConsoleRenderer` all present |
| rich 15.0.0 | live escape call | `markup.escape("[red]x[/red]")` escapes; NOTE: no module `__version__` in rich 15 |
| langgraph 1.2.7 | source inspection | `CompiledStateGraph.astream` supports `stream_mode` |
| tenacity 9.1.4 | import | `retry`/`stop_after_attempt` available (M1 pin, no new deps) |

## 3. Credential probes (user-driven, live)

- Fine-grained GitHub PAT (pasted in chat): catalog `GET /catalog/models` → 200,
  **37 models, no `gpt-5.4*` ids** (closest `openai/gpt-5[-mini/-nano]`); inference →
  **403 `no_access`** on chat AND embeddings. Diagnosis: missing Account permission
  "Models: Read-only". After the user added it: chat mini (`temperature=0`) 200 "Pong!",
  nano 200, embeddings 1536d — verified raw AND via a full live agent turn.
- `.env` `OPENAI_API_KEY` swapped to the fine-grained PAT (least privilege); the classic
  PAT remains only as `gh` CLI auth. Both PATs + the Tavily key are on the
  revoke-at-project-end list.
- Consequence confirmed: **no PAT can run the FR-M4-07 pinned-id probe** — it requires a
  real platform key (Clarify ruling B stands).

## 4. Analyze findings and their fixes (user: "fix all of them")

- **I1 (HIGH, doc↔code)**: three M3 nodes self-measured latency (`web_search`,
  `fetch_pages`, `ingest_content` keys) — the planned `timed()` wrapper would clobber
  and double-measure, with key drift vs PLAN §8.2 names. Fix: `timed()` declared the
  single stage-latency owner (P-III), merges node-returned latency, and T022 deletes the
  three in-node writes (pre-verified: no test asserted the old keys).
- **I2 (MEDIUM)**: `.gitignore` excluded the `logs/` DIRECTORY — git cannot re-include a
  file under an excluded dir, so the tracked sample log was impossible and a `!` negation
  would silently fail (proven with `git check-ignore`). Fix: ignore `logs/turns.jsonl`
  only.
- **U1 (LOW)**: the REPL bypasses `Agent.answer()`, so T024 must bind/clear the
  `turn_id` contextvars itself — made explicit.

## 5. Implementation session (task order, what was built)

Branch `m4-llms-logging-analytics` from main `20145bd`. T002 pinned the §2 repo facts as
assertions → T003/T004 authored the two owned test files FIRST (collection errors
confirmed = TDD fail) → T005 classify.py hardened in place (`_missing_`, prompts,
`classify()` = wait_for(8s) over tenacity ×2, null-on-failure) → T006 turnlog.py →
T007 real `log_turn` in `nodes/log.py` (merge-reduced dicts; never raises) → T008 app.py
real `TurnLogger` → T009 checkpoint (14 new tests; live wipe → miss → verbatim HIT
sim=0.74 with 2 full JSONL records) → T010–T014 analytics (aggregate/render, 10-record
sample, CLI `--json`, README DuckDB note; hit-rate 3/7=42.9% verified; markup escaped;
missing-file friendly) → T015–T017 clients finalized (ONE shared AsyncOpenAI, seams,
scripted FR-001…006 assertions) → T018 MODEL_CHOICES.md ported → T021–T025 timing +
structlog + REPL (live piped chat: MISS then `[MEMORY HIT sim=0.74]`; stdout pipe-clean,
`turn_id` on stderr) → this log → final gates + publish.

## 6. Hand-caught findings during implementation

- **Classifier returned `language: "English"`, not `"en"`** (first live turn). The PLAN
  §8.3 schema's ISO-639-1 comment is invisible to the model. Fix: pydantic
  `Field(description="ISO 639-1 two-letter code…")` — shape unchanged, verified live
  (`"en"` on the next turn). FR-M4-13's "two-letter code" now holds.
- **`ruff format --check` was never a repo gate**: 16 files on GREEN main would reformat
  under the installed ruff 0.15.20 formatter. CI and `make lint` gate `ruff check` only
  (always green). M4 did not bulk-reformat untouched files (scope discipline; noisy
  diff); the source spec's `ruff format --check .` command line is recorded here as
  aspirational-not-enforced. A wholesale reformat is an M6 option.
- **Calibration re-confirmed**: the ddgs question missed on verbatim re-ask (stored
  content scores < 0.70) while the Redis question re-hits at 0.74 — consistent with the
  M3 finding that re-ask hits are topic-dependent. Demos should use the Redis question.
- **`grep "turn_id="` on colored stderr finds nothing** — ConsoleRenderer inserts ANSI
  codes between key and `=`; grep for `turn_id` alone when verifying FR-M4-21.
- **`Settings()` reads `.env`**: client-contract assertions must construct
  `Settings(_env_file=None)` to test pinned defaults (first T017 run failed on the dev
  alias override — corrected, both modes now asserted).

## 7. FR-M4-07 status (temperature probe) — ⏳ PENDING real key

- Prices re-verified live 2026-07-05 on developers.openai.com/api/docs/pricing:
  mini $0.75/$4.50, nano $0.20/$1.25, flagship $2.50/$15.00 (unchanged);
  text-embedding-3-small not on the main page — $0.02 stands per 2026-07-04.
- The pinned-id `temperature=0` + `max_tokens` probe awaits the user's `sk-…` key
  (platform.openai.com, ~$5 min billing). Dev-alias evidence (gpt-4.1-mini, HTTP 200 with
  both kwargs) is recorded in `MODEL_CHOICES.md` §Build-time validation, which will be
  amended with the dated pinned-id outcome the moment the key lands. Contingencies
  documented there (temp-400 → `temperature=None`; max_tokens-400 →
  `max_completion_tokens` at the seams; never a silent model swap).
