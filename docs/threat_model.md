# Threat model (M5)

The memory-first web agent ingests untrusted web content and stores it for reuse, so the
threat model centres on prompt injection and memory poisoning. Four threats are defended;
the mitigations are the three guardrail layers (L1 input screen, L2 instruction/data
separation, L3 sanitize-before-store) plus an output defence.

| ID | Threat | Mitigation |
|----|--------|------------|
| T1 | Direct injection in the user query | **L1** input screen (`security/guardrails.py` + `security/patterns.py`): NFKC-normalise + zero-width strip → severity-tagged registry match; HIGH → refuse the turn (`blocked`, logged, web/store never touched); MEDIUM → answer but never cache. Plus **L2** prompt hardening. |
| T2 | Indirect injection inside fetched pages | **L2** data/instruction separation (`llm/prompts.py`): retrieved content is quoted DATA inside `<untrusted_context>` with per-source provenance headers, tag-breakout escaped, the user question placed last; **L3** sanitizer neutralises injection phrases in the fetched text before it is ever used. |
| T3 | **Memory poisoning** — injected content stored in Redis and replayed as trusted context on future hits (highest-value threat) | **L3 sanitize-before-store** (`security/sanitizer.py`): fetched content is neutralised **once, between markdown conversion and chunking**, so stored text is always sanitised text. Injection phrases become the literal marker `[removed-suspicious-instruction]` (never silently deleted). `sanitizer_flags` and a `content_sha256` fingerprint are persisted per chunk and re-attached in the L2 provenance header on every memory hit, so poisoned-but-neutralised content always replays as flagged quoted data. |
| T4 | Exfiltration / unsafe output (attacker URLs, tracker images) | The L2 prompt rule "cite only URLs that appear in a `source_url` field" plus a markdown-image strip applied to the produced answer text in both answer nodes, so a tracker/exfil image can never reach output even if the model emits one. |

Every mitigation and degradation path above is pinned by executable BDD scenarios
(`tests/bdd/features/security_*.feature`, `nodes_guard.feature`, `utils_reliability.feature`;
the blocked/degraded/failed routes end-to-end in `00_main_functionality.feature` — full index
and traceability matrix in `docs/BDD.md`).

## Reliability posture

Every upstream dependency has a single-owner retry policy (`utils/reliability.py`, tenacity)
with typed failures (`utils/errors.py`); every failure mode has a designed degradation
outcome (web-only on Redis down, snippets-only when fetches fail, a clean `failed` apology
when search/LLM/embeddings are down) and the turn is always logged exactly once — never a
traceback.

## Explicitly out of scope

Stated plainly (no jailbreak-proof claims):

- ML-based injection classifiers (e.g. llm-guard / Prompt-Guard) — a production upgrade path.
- DLP / PII redaction.
- URL reputation / allow-listing.
- Authentication and rate limiting.
- Canary tokens and output URL-defang allow-listing (evaluated and cut as stretch scope).

These are deliberate scope boundaries for a single-user take-home agent; the L1/L2/L3
layers are "basic but real", not a claim of completeness.
