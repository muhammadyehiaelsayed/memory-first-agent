"""answer_from_memory and answer_failure nodes."""

from memagent.llm.prompts import build_system_prompt, wrap_context
from memagent.resources import AgentResources
from memagent.state import SourceRef

FAILURE_APOLOGY = (
    "I'm sorry - I can't answer that right now because a required step failed. "
    "Nothing was stored for this turn. Please try again."
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
        result = await resources.chat_llm.complete(build_system_prompt(), messages)
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


def make_answer_failure(resources: AgentResources):  # noqa: ARG001 — uniform node factory signature
    async def answer_failure(state: dict) -> dict:  # noqa: ARG001 — must tolerate malformed state
        # Deterministic apology. No LLM call. Must never raise.
        return {"route": "failed", "answer": FAILURE_APOLOGY, "sources": []}

    return answer_failure
