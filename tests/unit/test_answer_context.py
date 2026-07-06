"""answer_from_web bounded-context rule (FR-M3-28), untested before M7.

Each fetched page contributes its summary + only its first web_context_chunks_per_page (=2)
chunks to the LLM prompt — never all chunks. The one prior exercise supplied a single chunk,
so the bound was never observed. In-memory fakes — no Redis, no network.
"""

import asyncio

from memagent.config import Settings
from memagent.interfaces import CompletionResult
from memagent.nodes.answer import make_answer_from_web
from memagent.resources import AgentResources

S = Settings(_env_file=None)


def _run(coro):
    return asyncio.run(coro)


class CapturingChat:
    def __init__(self):
        self.prompt = None

    async def complete(self, system, messages):
        self.prompt = messages[-1]["content"]
        return CompletionResult(
            text="answer", usage={"input_tokens": 1, "output_tokens": 1, "model": "fake"}
        )


def test_answer_from_web_bounds_context_to_first_two_chunks_per_page():
    url = "https://redis.io/vs"
    chunks = [
        {
            "chunk_id": f"{url}:{i}",
            "text": f"CHUNKBODY{i}",
            "url": url,
            "title": "Redis",
            "chunk_index": i,
        }
        for i in range(4)
    ]
    state = {
        "query": "how does redis vector search work",
        "fetched_docs": [{"url": url, "title": "Redis", "summary": "the summary", "ok": True}],
        "chunks": chunks,
        "search_results": [],
    }
    chat = CapturingChat()
    resources = AgentResources(
        settings=S,
        memory=None,
        embedder=None,
        chat_llm=chat,
        analytics_llm=None,
        searcher=None,
        fetcher=None,
        turn_logger=None,
    )
    out = _run(make_answer_from_web(resources)(state))
    assert out["route"] == "memory_miss_web_search"
    assert "CHUNKBODY0" in chat.prompt and "CHUNKBODY1" in chat.prompt  # first 2 included
    assert "CHUNKBODY2" not in chat.prompt and "CHUNKBODY3" not in chat.prompt  # rest excluded
    assert S.web_context_chunks_per_page == 2
