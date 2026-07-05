"""answer_from_memory, answer_from_web, and answer_failure nodes."""

from memagent.llm.prompts import build_system_prompt, wrap_context
from memagent.resources import AgentResources
from memagent.state import SourceRef

FAILURE_APOLOGY = (
    "I'm sorry - I can't answer that right now because a required step failed. "
    "Nothing was stored for this turn. Please try again."
)

LOW_CONFIDENCE_DISCLAIMER = (
    "Note: I couldn't fetch any full pages for this question, so this answer is based "
    "only on search result snippets and may be incomplete or less reliable."
)


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
        hits = state["memory_hits"]
        context = wrap_context(hits, origin="memory")
        messages = [
            *state.get("history", []),
            {"role": "user", "content": f"{context}\n\nQuestion: {state['query']}"},
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
        answer = result.text
        if "sources:" not in answer.lower():
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
        if fetched:
            # Bounded context: each page's summary + its first N chunks — never all.
            per_page = resources.settings.web_context_chunks_per_page
            source_dicts: list[dict] = []
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
                    {"url": doc["url"], "title": doc["title"], "text": "\n\n".join(parts)}
                )
            route, degradation, disclaimer = "memory_miss_web_search", None, None
        else:
            # Snippets-only degraded path: search succeeded but nothing was fetchable.
            source_dicts = [
                {"url": r["url"], "title": r["title"], "text": r["snippet"]}
                for r in state["search_results"]
            ]
            route, degradation, disclaimer = "degraded_web", "snippets_only", LOW_CONFIDENCE_DISCLAIMER

        # In-hand content only — no memory.knn, no Redis reads on the miss path.
        context = wrap_context(source_dicts, origin="web")
        messages = [
            *state.get("history", []),
            {"role": "user", "content": f"{context}\n\nQuestion: {state['query']}"},
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
                        "node": "answer_from_web",
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:200],
                    }
                ],
            }
        sources = _dedupe_sources(source_dicts, "web")
        answer = result.text
        if "sources:" not in answer.lower():
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
