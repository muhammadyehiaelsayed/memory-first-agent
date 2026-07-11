"""answer_from_memory, answer_from_web, and answer_failure nodes."""

import re

from memagent.llm.prompts import build_system_prompt, wrap_context
from memagent.resources import AgentResources
from memagent.security.sanitizer import strip_markdown_images
from memagent.state import SourceRef

FAILURE_APOLOGY = (
    "I'm sorry - I can't answer that right now because a required step failed. "
    "Nothing was stored for this turn. Please try again."
)

LOW_CONFIDENCE_DISCLAIMER = (
    "Note: I couldn't fetch any full pages for this question, so this answer is based "
    "only on search result snippets and may be incomplete or less reliable."
)

# A7: on the miss path ingest_content may have persisted chunks BEFORE the answer LLM
# failed, so the generic "Nothing was stored" line would be false. This variant is used
# only in answer_from_web's failure branch when stored_chunk_ids is nonempty.
WEB_FAILURE_AFTER_STORE_APOLOGY = (
    "I'm sorry - I can't answer that right now because a required step failed. "
    "Fetched pages were saved to memory, but the answer step failed. Please try again."
)

# cli._chat classifies a turn as failed by matching the answer text; BOTH apology
# variants must count as a failed turn (FR-M5-27).
FAILURE_APOLOGIES = (FAILURE_APOLOGY, WEB_FAILURE_AFTER_STORE_APOLOGY)


def _dedupe_sources(hits: list[dict], origin: str) -> list[SourceRef]:
    seen: set[str] = set()
    sources: list[SourceRef] = []
    for h in hits:
        url = h.get("url", "")
        if url and url not in seen:
            seen.add(url)
            sources.append(SourceRef(url=url, title=h.get("title", ""), origin=origin))
    return sources


def make_answer_from_memory(resources: AgentResources):
    async def answer_from_memory(state: dict) -> dict:
        # A11: keep only at/above-threshold hits — knn returns the raw top-k, but the router
        # only guarantees hits[0] cleared the threshold, so below-threshold neighbours must
        # not dilute the context or surface as displayed sources (the list is never empty
        # here: hits[0] survives by construction of this branch). The threshold is always in
        # real state; guard the read so a direct-call state that omits it is not filtered.
        hits = state["memory_hits"]
        threshold = state.get("threshold")
        if threshold is not None:
            hits = [h for h in hits if h["similarity"] >= threshold]
        context = wrap_context(hits, origin="memory")
        # H1: the model sees the guard-capped sanitized_query, never the raw query, so a
        # past-cap injection can't reach it (fallback keeps direct-call/older state working).
        query = state.get("sanitized_query") or state["query"]
        messages = [
            *state.get("history", []),
            {"role": "user", "content": f"{context}\n\nQuestion: {query}"},
        ]
        try:
            result = await resources.chat_llm.complete(build_system_prompt(), messages)
        except Exception as exc:  # noqa: BLE001 — node owns degradation; retries are M5's
            return {
                "route": "failed",
                "answer": FAILURE_APOLOGY,
                "sources": [],
                "errors": [
                    {
                        "node": "answer_from_memory",
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:200],
                    }
                ],
            }
        sources = _dedupe_sources(hits, "memory")
        answer = strip_markdown_images(result.text)  # T4 output defence (FR-M5-29)
        # A5: drop any model-emitted trailing "Sources:" block (it may carry invented or
        # injection-induced URLs) and ALWAYS append the programmatic listing built from the
        # real hits, so displayed citations always equal the structured provenance set.
        # match the citation header in any form the model might emit — plain "Sources:", an
        # ATX heading ("## Sources"), or bold ("**Sources:**") — so an invented/injected URL
        # block cannot survive by dressing its header in markdown.
        answer = re.split(r"(?im)^\s{0,3}#{0,6}\s*\*{0,2}\s*sources\s*:?.*$", answer, maxsplit=1)[
            0
        ].rstrip()
        listing = "\n".join(f"- {s['url']}" for s in sources)
        answer = f"{answer}\n\nSources:\n{listing}"
        return {
            "route": "memory_hit",
            "answer": answer,
            "sources": sources,
            "tokens": {"answer_llm": result.usage},
        }

    return answer_from_memory


def make_answer_from_web(resources: AgentResources):
    async def answer_from_web(state: dict) -> dict:
        fetched = state["fetched_docs"]
        source_dicts: list[dict] = []
        if fetched:
            # Bounded context: each page's summary + its first N chunks — never all.
            per_page = resources.settings.web_context_chunks_per_page
            for doc in fetched:
                page_chunks = sorted(
                    (c for c in state["chunks"] if c["url"] == doc["url"]),
                    key=lambda c: c["chunk_index"],
                )
                parts: list[str] = []
                if doc.get("summary"):
                    parts.append(f"Summary: {doc['summary']}")
                parts.extend(c["text"] for c in page_chunks[:per_page])
                if not parts:
                    continue
                source_dicts.append(
                    {
                        "url": doc["url"],
                        "title": doc["title"],
                        "text": "\n\n".join(parts),
                        # D10: carry per-page sanitizer flags into the L2 provenance header.
                        "sanitizer_flags": doc.get("sanitizer_flags", []),
                    }
                )
        # H2: key the grounded/degraded decision on usable CONTENT, not just fetched-list
        # nonemptiness — a doc whose text the sanitizer stripped (no summary, no chunks)
        # contributes zero parts above, so an empty source_dicts must degrade to the
        # snippets path (never a clean "success" with an empty Sources header), exactly
        # like the no-fetch case.
        if source_dicts:
            # D9: a lingering redis_down (from memory_search) makes even a clean fetched
            # answer a degraded_web turn (FR-M5-24); otherwise it's a normal miss.
            degradation = state.get("degradation")
            route = "degraded_web" if degradation else "memory_miss_web_search"
            disclaimer = None
        else:
            # Snippets-only degraded path: search succeeded but nothing was fetchable, or
            # every fetched page yielded no usable text.
            source_dicts = [
                {"url": r["url"], "title": r["title"], "text": r["snippet"]}
                for r in state["search_results"]
            ]
            # redis_down (if present) is the first cause and keeps the label; disclaimer still shows.
            degradation = state.get("degradation") or "snippets_only"
            route, disclaimer = "degraded_web", LOW_CONFIDENCE_DISCLAIMER

        # In-hand content only — no memory.knn, no Redis reads on the miss path.
        context = wrap_context(source_dicts, origin="web")
        # H1: the model sees the guard-capped sanitized_query, never the raw query.
        query = state.get("sanitized_query") or state["query"]
        messages = [
            *state.get("history", []),
            {"role": "user", "content": f"{context}\n\nQuestion: {query}"},
        ]
        try:
            result = await resources.chat_llm.complete(build_system_prompt(), messages)
        except Exception as exc:  # noqa: BLE001 — node owns degradation; retries are M5's
            # A7: ingest_content may have persisted chunks BEFORE this LLM call failed, so
            # only claim "nothing was stored" when nothing actually was (cli treats both
            # variants as a failed turn via FAILURE_APOLOGIES).
            apology = (
                WEB_FAILURE_AFTER_STORE_APOLOGY
                if state.get("stored_chunk_ids")
                else FAILURE_APOLOGY
            )
            return {
                "route": "failed",
                "answer": apology,
                "sources": [],
                "errors": [
                    {
                        "node": "answer_from_web",
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:200],
                    }
                ],
            }
        sources = _dedupe_sources(source_dicts, "web")
        answer = strip_markdown_images(result.text)  # T4 output defence (FR-M5-29)
        # A5: drop any model-emitted trailing "Sources:" block and ALWAYS append the
        # programmatic listing, so displayed citations always equal the provenance set.
        # match the citation header in any form the model might emit — plain "Sources:", an
        # ATX heading ("## Sources"), or bold ("**Sources:**") — so an invented/injected URL
        # block cannot survive by dressing its header in markdown.
        answer = re.split(r"(?im)^\s{0,3}#{0,6}\s*\*{0,2}\s*sources\s*:?.*$", answer, maxsplit=1)[
            0
        ].rstrip()
        listing = "\n".join(f"- {s['url']}" for s in sources)
        answer = f"{answer}\n\nSources:\n{listing}"
        if disclaimer:
            answer = f"{disclaimer}\n\n{answer}"
        return {
            "route": route,
            "degradation": degradation,
            "answer": answer,
            "sources": sources,
            "tokens": {"answer_llm": result.usage},
        }

    return answer_from_web


def make_answer_failure(resources: AgentResources):  # noqa: ARG001 — uniform node factory signature
    async def answer_failure(state: dict) -> dict:  # noqa: ARG001 — must tolerate malformed state
        # Deterministic apology. No LLM call. Must never raise.
        return {"route": "failed", "answer": FAILURE_APOLOGY, "sources": []}

    return answer_failure
