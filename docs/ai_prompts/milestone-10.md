# Milestone 10 — Full-repo review + fixes (appended 2026-07-07)

A post-v1.3 AI-assisted pass. The user asked for a comprehensive review of the whole repo,
then chose to fix the highest-value findings. Tooling: Claude Code (Fable 5 orchestrator +
Fable 5 / Opus 4.8 subagents), dynamic workflows.

## 1. Instructions (user-issued, verbatim)

1. "i need a very good review on every thing in the rep make sure you use all of your power
   and use workflows"
2. (after the review report) AskUserQuestion → **"Fix HIGH + 2 security MEDIUMs"**

## 2. The review (workflow `wf_e89fe41e-b13`, 67 agents)

Ten read-lenses (correctness, security, async/resources, error-handling, performance,
dead-code, non-BDD test quality, BDD quality, docs-truth, reviewer-attack) plus four
execution probes (fresh-clone quickstart, Make/CI parity, a full git-history secrets scan,
git-history presentation), each finding routed to an independent adversarial verifier
(default REFUTED), then a completeness critic. 52 findings → 43 confirmed / 9 refuted;
**0 critical**, 1 high, 5 medium, the rest polish.

The secrets probe came back clean and was independently confirmed: no real credential ever
entered git history (the only `sk-` in history is the `sk-...` placeholder in `.env.example`),
and `.env` was never tracked.

## 3. Fixes applied (v1.3 → this pass)

Scope: the 1 high + the 2 security mediums. **No behavior outside these three was changed.**

- **HIGH — fresh-Redis quickstart crash.** `make redis-up -> make run` provisioned no vector
  index, so the first `memory_search` hit a missing index and raised `RedisSearchError`
  (not a redis outage), escaping the `memory_search` guard: a raw traceback and no logged
  turn. Fix: an idempotent, exists-guarded `RedisMemoryStore.ensure_ready()` (added to the
  `MemoryStore` Protocol), called once at `Agent` startup — `Agent.answer()` calls it lazily
  and the REPL calls it before its loop. A genuine schema/programming error still surfaces
  loudly; a redis outage still degrades via the typed error. (`memory/store.py`, `app.py`,
  `cli.py`, `interfaces.py`)
- **MEDIUM — SSRF via redirects.** The fetcher ran `follow_redirects=True`, so a public page
  could 302 the fetcher to `169.254.169.254`/loopback and the body would be ingested and
  cited. Fix: `follow_redirects=False` + a manual redirect loop (capped at `MAX_REDIRECTS`)
  that re-runs `_is_safe_fetch_target` on every hop. (`web/fetch.py`)
- **MEDIUM — Tavily malformed-200 skipped the fallback.** The response `.json()` parse sat
  outside the caught exception tuple, so a 200 with a non-JSON body raised `JSONDecodeError`
  and forced a `failed` turn instead of degrading to the keyless ddgs provider. Fix: wrap the
  parse and raise the typed `SearchUnavailableError`, which `FallbackProvider` already
  catches. (`web/search.py`)

## 4. Verification

- Full suite 371 passed (was 362: +5 BDD scenarios covering the 4 new functions —
  `MemoryStore.ensure_ready`, `RedisMemoryStore.ensure_ready`, `Agent.ensure_ready`,
  `_is_safe_fetch_target` — plus +4 unit tests); ruff check + format clean; the AST
  traceability gate green at 142 → 146 functions covered.
- Each fix was mutation-tested: the SSRF guard forced always-safe, the Tavily parse left
  unguarded, and `ensure_ready` made a no-op — every mutant made a guarding test fail, then
  was reverted.
- No source changed beyond the three fixes; `docs/BDD.md` regenerated; threat model gains a
  T5 (SSRF) row.

## 5. Judgement notes

- Provisioning was placed at `Agent` startup, not in the `knn`/`store` hot path: the
  store-level unit tests drive `knn`/`store` directly with minimal fakes, and putting an
  `index.exists()` call there would have intruded on them. Startup is also where the reviewer
  pointed. `ensure_ready` joined the `MemoryStore` Protocol so the contract is explicit.
- The redirect guard matches the existing mini-guard's scope (scheme + private-IP literal);
  DNS resolution stays out of scope, consistent with `_is_private_host`'s documented limit.
