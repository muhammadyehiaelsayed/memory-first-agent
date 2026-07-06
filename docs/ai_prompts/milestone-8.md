# Milestone 8 — Delivery-readiness review + fixes (appended 2026-07-06)

A post-v1.1 AI-assisted pass, not one of the six planned milestones. The user asked for a
manual-style end-to-end run plus a reviewer-lens review of every file, to make the repo
ready to hand to a reviewer. Tooling: Claude Code (Opus 4.8) + dynamic subagent workflows.
Result: tag `v1.2`.

## 1. Instructions (user-issued, verbatim)

1. "i want you to make another end to end test like if i test it manualy and then make final
   review on every file in folder make sure it is ready to be dilived to my reviewer which he
   will discuss it in the interview make sure you use workflows"
2. (after the review report) AskUserQuestion → **"Everything incl. behavior changes"**
3. AskUserQuestion → **"Full land + tag v1.2"**

## 2. Live manual end-to-end run

Driven by the orchestrator (not a workflow — it mutates Redis and spends real API calls),
against real `redis:8.2` + the GitHub Models key + Tavily key in `.env`: `wipe-memory` → cold
ask "What is the RESP protocol in Redis?" (`[MEMORY MISS → searching the web]`, Tavily 8
results, 4 cited sources, one page fetch-failed and skipped gracefully) → verbatim re-ask
(`[MEMORY HIT sim=0.81]`, memory-origin, zero web) → paraphrase (`sim=0.81`, semantic hit) →
prompt-injection query (`[BLOCKED by input guard]`, exit 0) → a second topic (miss → web) →
`analytics` (full report). The memory-first / grounded-with-citations / guardrailed promise
holds live.

## 3. Delivery-readiness review (report-first)

A dynamic workflow (`wqpkb37s8`, 36 agents) reviewed every file across 11 areas through the
lens of "the senior engineer who will interview the candidate about this repo", then an
independent skeptic verified each finding (default REFUTED). One area (`llm/*`, `answer.py`,
remaining nodes) came back fully delivery-ready. **23 findings confirmed (2 MAJOR, 8 MINOR,
13 NIT), 0 blockers, 2 refuted** (a bare Redis client in the one-shot seeder — real but
immaterial; `architecture.md` being diagram-only — a deliberate generated artifact).

## 4. Fixes (all 23, "everything incl. behavior changes")

- **MAJOR:** `scripts/seed_memory.py` was dead-on-arrival — `OpenAIEmbedder(settings)` is a
  `TypeError` (wrong constructor args); fixed to build via `build_openai_clients` +
  `make_redis_client`. And this AI-usage record itself: v1.1 shipped an AI-authored M7 with no
  prompt log — added `milestone-7.md` and this file, and updated `AI_USAGE.md`.
- **Behavior changes (each with a mutation-verified test):** (1) the L3 content sanitizer now
  neutralises only HIGH-severity injection patterns — the MEDIUM patterns (fake role markers,
  exfil coaxing) were corrupting benign fetched prose (chat transcripts, "contact us" emails);
  they remain L1 INPUT signals. (2) The `doc:{h}` meta hash now expires with the same TTL as its
  chunks (was unbounded). (3) The hardcoded tunables `max_urls_per_domain`, `min/max_markdown_chars`,
  `summary_input_chars`, `min_chunk_chars` were promoted to `Settings` (P-III now holds;
  `filter_urls` no longer takes `settings` only to ignore it); `.env.example` regenerated.
- **Polish:** `analytics` `chunks_ingested` now counts chunks PERSISTED (`stored_chunk_ids`),
  not produced; `FetchedDoc` declares its `sanitizer_flags` field; stale milestone-tense
  docstrings/comments corrected to present tense (cli `ask`, web `fetch`/`search`, `app`,
  `classify`, `config` P-III claim); the README verbatim-re-ask `sim ≈ 1.0` claim corrected to
  `≈ 0.8` (matches the transcript and the live run); the MODEL_CHOICES uncited benchmark hedged;
  `make lint` now mirrors CI (adds `ruff format --check`); RedisInsight's floating tag annotated
  as an intentional dev-only choice; conftest stale "12 unit tests" count dropped.

Not changed: the credential-leak NIT is a delivery-process action (rotate the tokens in `.env`
and hand the repo over as a git clone/archive, not a zip) — reinforced to the user, not a code
fix. The `milestone-5.md` stale "ruff format not gated" note was left as-is: it is an
append-only historical log, accurate for its milestone; the live divergence it described is
fixed in the Makefile.

## 5. Verification

The 3 behavior changes + the promoted-constant call sites were **mutation-verified 6/6**.
Full suite green (140 unit + 7 integration/e2e = 147; was 144); ruff + format clean; both eval
harnesses exit 0; render idempotent. Landed on `m8-delivery-polish`, CI green, merged to main,
tagged `v1.2`.
