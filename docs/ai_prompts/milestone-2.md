# Milestone 2 — Prompt Log (part of the complete instruction record)

> Chronological record of the instructions that produced Milestone 2 (2026-07-05).
> Appended as the milestone was built — never retroactively.

## Spec Kit flow for Milestone 2

1. **Specify**: "/speckit-specify for Milestone 2, feeding it specs/milestone-2-memory-path.md"
   → feature `002-m2-memory-path`, 26 FRs, 4 user stories, 16/16 quality checklist.
2. **Clarify**: one question — credentials for M2 live calls. User answer: **A** — GitHub
   Models free tier (`OPENAI_BASE_URL` + PAT), real `OPENAI_API_KEY` deferred to M6
   ("develop free, demo on the real key").
3. **Plan**: plan.md (11/11 constitution gates PASS), research.md (11 decisions incl. the
   two added state channels, the single conversion site, the vector-alignment convention),
   data-model.md, 4 contracts, quickstart.md.
4. **Tasks**: 32 tasks across 7 phases.
5. **Analyze**: 4 findings (HIGH: `docs/seed.md` fixture was never created by any task;
   MEDIUM: FR-M2-15 URL scenarios had no owning test file; 2 LOW). User: "yes apply the
   fixes" → T020 authors the fixture; test_chunker.py hosts the URL scenarios.
6. **Implement**: T001–T032 executed — this changeset.

## FR-M2-25 verification records (PLAN §14 duty) — verified live 2026-07-05

**Endpoint**: `https://models.github.ai/inference` (OpenAI-compatible), auth = classic
GitHub PAT (worked directly — a fine-grained `models:read` PAT was NOT required for this
account).

**Catalogue findings** (37 models listed):
- `openai/text-embedding-3-small` — **present and working**: returned 1536-dim vectors
  (live call). The 0.70 threshold calibration therefore carries over to dev mode exactly.
- `openai/text-embedding-3-large` — present (upgrade path id also available).
- `gpt-5.4-mini` / `gpt-5.4-nano` — **absent from GitHub Models** (OpenAI-API-only ids).
  Nearest family `openai/gpt-5-mini`/`gpt-5-nano` is listed but tier `custom` →
  HTTP 400 `unavailable_model` on the free tier for this account.
- **Dev aliases chosen** (session-level env only; production `Settings` defaults
  unchanged): `CONVERSATION_MODEL=openai/gpt-4.1-mini`,
  `ANALYTICS_MODEL=openai/gpt-4.1-nano` (same mini/nano tiering, tier `low`, working).

**temperature=0**: accepted (HTTP 200) on `openai/gpt-4.1-mini`, `gpt-4.1-nano`, and
`gpt-4o-mini` with `temperature: 0` in the request. ⚠ The pinned production id
`gpt-5.4-mini` could NOT be validated on GitHub Models (id absent) — that validation
re-runs on the real OpenAI key during M4's client finalization (Ruling D), before the M6
recorded demo.

## Demo outcome (PLAN §13 M2 row) — live 2026-07-05

- `wipe-memory` → seed `docs/seed.md` (2 chunks) → ask "How does Redis vector search
  work?" → **`[MEMORY HIT sim=0.74]`**, grounded answer, "Sources:" section, stored
  URL + title printed.
- Unseeded ask → `[MEMORY MISS]` + deterministic apology (temporary M2 miss path).
- Near-verbatim single-sentence ask → `[MEMORY HIT sim=0.75]`.
- **Calibration note (recorded honestly):** paraphrase/sentence-length questions score
  ~0.74–0.75 against 1600-char chunks — comfortably above the 0.70 contract but below the
  0.9x sketch in the demo notes; full-question-vs-ingested-chunk similarity rises when
  chunks are shorter or the query matches more of the chunk. This is the PLAN §15.2
  behavior, working as documented.

## Live store validations (T027)

- Upsert shrink: re-seeding the same URL with fewer chunks left NO stale
  `chunk:{hash}:{i}` keys (2 → 1, key `:1` removed).
- `is_fresh`: just-seeded → True; absent hash → False.
- `MEMORY_TTL_SECONDS=0` → `TTL` = -1 (no expiry); default → 604771s remaining.
- `knn` on a wiped index → `[]` (a normal miss, not an error).

## Corrections during implementation

- None to code logic — 25/25 unit tests passed first run; the only adjustments were
  environmental (GitHub Models tier gating → dev-alias selection, recorded above).
