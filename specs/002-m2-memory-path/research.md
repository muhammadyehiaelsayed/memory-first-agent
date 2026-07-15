# Phase 0 Research: Milestone 2 — Memory Path

**Date**: 2026-07-05 · **Plan**: [plan.md](plan.md)

No `NEEDS CLARIFICATION` markers remained after `/speckit-clarify` (session 2026-07-05).
Consolidated decisions: the clarify answer, the source file's spec-noted defaults, and
inherited verified research. Live verifications deliberately deferred to runtime tasks:
FR-M2-25 (GitHub Models catalogue + `temperature=0`).

## Decisions

### D1. Credentials — GitHub Models free tier for all M2 live calls
- **Decision**: `OPENAI_BASE_URL` → GitHub Models OpenAI-compatible endpoint; key = a
  **fine-grained GitHub PAT with `models: read`**. Real `OPENAI_API_KEY` deferred to M6.
- **Rationale**: $0 during development (locked strategy "develop free, demo on the real
  key", PLAN §6); FR-M2-25's verification happens as a side effect of simply using it.
- **Alternatives**: real OpenAI key now (cents, but violates the free-dev strategy);
  both (extra ceremony without M2 value).
- **Source**: spec Clarifications Q1 → A. **Verify at implement time**: the current
  candidate endpoint is `https://models.github.ai/inference` with catalogue ids like
  `openai/gpt-5.4-mini` — confirm with one live call and record actual strings (dev-mode
  ids never overwrite production defaults in `Settings`).

### D2. Two state channels beyond PLAN §3.1 — `turn_started_at`, `search_provider`
- **Decision**: `state.py` declares both (single-writer, no reducer).
- **Rationale**: LangGraph only propagates keys declared in the state schema; M4's
  TurnRecord needs `latency_ms.total` (from `turn_started_at`) and `web.provider` (from
  `search_provider`). Declaring them later would force M4 to edit M2's canonical file.
- **Alternatives**: side-channel via closure/contextvars (breaks graph statelessness);
  M4 edits state.py (violates single-owner discipline).
- **Source**: milestone §6.2 spec note (cross-audited against M4's spec).

### D3. `QueryClassification` placement — schema-only in `analytics/classify.py` now
- **Decision**: M2 ships the pydantic schema + `Category`/`QuestionType` enums (verbatim,
  no `_missing_` hooks); M4 hardens the same file (adds `_missing_`, classifier fn, retry).
- **Rationale**: `AgentState.analytics: QueryClassification | None` must resolve at
  runtime (`get_type_hints` evaluates every annotation) even while `log_turn` is a no-op.
- **Alternatives**: house it in `state.py` (works, but splits analytics types across
  modules); string annotation + skip resolution (fights LangGraph's reducer discovery).
- **Source**: milestone §6.2 spec note; named seam in M4's spec §6.4.

### D4. `StepError` definition — minimal 3-field TypedDict
- **Decision**: `{node: str, error_type: str, detail: str}` defined in `state.py`.
- **Rationale**: PLAN references it but never defines fields; state.py is the canonical
  home; three fields cover the M4 turn log's `errors` array.
- **Source**: milestone §6.2 spec note (marked change-freely).

### D5. Conversion site — `RedisMemoryStore.knn`, not the `memory_search` node
- **Decision**: `distance_to_similarity()` is a module-level pure helper in
  `memory/store.py`; `knn` attaches similarity; the node only reads.
- **Rationale**: PLAN §4.3 places the conversion at the "memory_search/store boundary";
  putting it in the store keeps `MemoryHit` complete at the contract boundary and gives
  M6's integration test one place to assert. The verbatim §3.1 comment ("computed in
  memory_search only") is historical wording — the spec note resolves it authoritatively.
- **Alternatives**: convert in the node (splits the trap across layers); convert in both
  (two sites = the exact defect P-II forbids).
- **Source**: milestone §6.2/§6.7 spec notes; FR-M2-07.

### D6. Vector/summary alignment convention for `store()`
- **Decision**: summary present → `vectors[0]` = summary embedding, `vectors[1:]` ↔
  chunks (len = chunks+1); no summary → 1:1 (len = chunks). Seeding passes
  `summary=None`.
- **Rationale**: keeps one `store()` signature that M3's `ingest_content` can call with
  batch-embedded `([summary] if summary else []) + chunk_texts` — no M3 signature change.
- **Alternatives**: separate `store_summary()` (second write path to keep consistent);
  dict payloads (loses ordering guarantees).
- **Source**: milestone §6.7 (contract pinned against M3 §6.10).

### D7. Client constructor seam — thin now, finalized in M4
- **Decision**: M2 constructors `OpenAIEmbedder(settings)` / `OpenAIChatLLM(settings,
  model)`, each building its own `AsyncOpenAI(max_retries=0, timeout=45.0,
  base_url=settings.openai_base_url or None)`. M4 rewrites to the shared-client
  signatures via `build_openai_clients(settings)`; `embed()`/`complete()` call interfaces
  never change.
- **Rationale**: Ruling D — the wrapper seam (one call-site per client) must exist now so
  M5's tenacity wrap and M4's finalization are drop-ins that don't touch node code.
- **Source**: milestone §6.10 spec note.

### D8. Float32 boundary epsilon — comparison stays `>= threshold`
- **Decision**: keep the router comparison exactly `sim >= threshold`; adopt
  `>= threshold - 1e-6` ONLY if the boundary test proves flaky; the decision is recorded
  once in `test_similarity.py`.
- **Rationale**: don't pre-solve a problem that may not exist; the decision point is
  documented so a flake has a one-line remedy.
- **Source**: milestone §6.5 spec note; PLAN §4.3.

### D9. URL canonicalization — lowercase scheme+host (path/query case preserved)
- **Decision**: canonical = lowercase scheme/host + drop fragment + drop `utm_*` params;
  hash = sha256(canonical)[:16].
- **Rationale**: scheme/host are case-insensitive per RFC 3986 — safe dedup win; path
  case can be significant, so it is preserved.
- **Source**: milestone §6.9 spec note; FR-M2-15.

### D10. Forward refs for M3/M4 types in `AgentResources`
- **Decision**: `from __future__ import annotations` in `resources.py` + minimal
  placeholder Protocols `PageFetcher`/`TurnLogger` in `interfaces.py`; M2 populates those
  fields with no-op stubs.
- **Rationale**: the frozen dataclass must construct today with fields typed for objects
  that arrive in M3/M4; never call `get_type_hints` on `AgentResources`.
- **Source**: milestone §6.3 spec note; Ruling B stub table.

### D11. Miss-branch seam — path-map remapping, not router edits
- **Decision**: `route_after_memory` returns the string `"web_search"` forever; M2's
  graph maps that key to `answer_failure`; M3 remaps it to the real `web_search` node.
- **Rationale**: routers stay verbatim and unit-stable; the whole miss seam is one
  path-map line in `graph.py` — the cheapest possible M3 handoff.
- **Source**: milestone §6.12; Ruling B.

## Best-practice notes applied

- **No degradation matrix yet**: Redis-down during M2 may surface an error — the demo
  assumes Redis is up; graceful `redis_down` handling is M5's (source §6.7 spec note).
- **`build_resources()` keyless caveat**: graph-inspection paths need a non-empty dummy
  key (`OPENAI_API_KEY=dummy`) because clients construct `AsyncOpenAI` eagerly — noted in
  quickstart.
- **Banner ownership**: M2's miss banner is the bare `[MEMORY MISS]`; upgrading it to
  `[MEMORY MISS → searching the web]` is explicitly M3's edit (source §6.14).
