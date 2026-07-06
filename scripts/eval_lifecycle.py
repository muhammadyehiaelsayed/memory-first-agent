"""Lifecycle eval harness — the memory-first HARD GATE (FR-013, FR-014).

  python scripts/eval_lifecycle.py --mock   # FakeLLM/FakeEmbedder + respx-mocked search/fetch,
                                             # REAL redis:8.2 (CI). Exit 0 iff every question is
                                             # miss-then-hit; else exit 1 (names the failing one).
  python scripts/eval_lifecycle.py          # real OpenAI + real search (manual, needs OPENAI_API_KEY).

Not a `v1.0` gate in real-key mode (Clarification Q1): absent a key it exits non-zero with a
readable message and no traceback.
"""

import asyncio
import pathlib
import sys

# Standalone script: put the repo root on sys.path so `tests.conftest` is importable
# (tests/ is not an installed package — recheck H). memagent is installed (editable).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from memagent.config import Settings  # noqa: E402

# (question, unique URL) — each mocked page repeats its own question verbatim (query-dominated).
QUESTIONS = [
    ("How does Redis vector search work?", "https://example.test/redis-vector-search"),
    ("What is cosine similarity?", "https://example.test/cosine-similarity"),
    ("How do I set a TTL on a Redis key?", "https://example.test/redis-ttl"),
]


def _page_html(question: str) -> str:
    # Full HTML doc + block tag so trafilatura extracts it (a bare <article> is dropped).
    return "<html><body><article><p>" + (question + " ") * 40 + "</p></article></body></html>"


async def _run_mock() -> int:
    import httpx
    import respx

    from memagent.app import Agent
    from memagent.memory.schema import get_index, wipe_index
    from memagent.memory.store import make_redis_client
    from memagent.utils.errors import redis_down_in_chain
    from tests.conftest import build_test_resources

    settings = Settings(_env_file=None, wait_cap_scale=0.0, tavily_api_key="test-key")
    client = make_redis_client(settings)
    failures: list[str] = []
    try:
        index = get_index(settings, client)
        for question, url in QUESTIONS:
            await wipe_index(index)  # fresh slate so turn 1 is a genuine miss
            with respx.mock(assert_all_called=False) as mock:
                mock.post("https://api.tavily.com/search").mock(
                    return_value=httpx.Response(
                        200,
                        json={"results": [{"url": url, "title": question, "content": question}]},
                    )
                )
                mock.get(url).mock(
                    return_value=httpx.Response(
                        200, headers={"content-type": "text/html"}, text=_page_html(question)
                    )
                )
                agent = Agent(build_test_resources(settings, client))
                r1 = await agent.answer(question)
                r2 = await agent.answer(question)
            ok = (
                r1.route == "memory_miss_web_search"
                and r2.route == "memory_hit"
                and (r2.similarity or 0.0) >= 0.70
            )
            print(
                f"  [{'PASS' if ok else 'FAIL'}] {question!r}: "
                f"turn1={r1.route}, turn2={r2.route}, sim={r2.similarity}"
            )
            if not ok:
                failures.append(question)
    except Exception as exc:  # noqa: BLE001 — redis down -> clean message, never a traceback
        if redis_down_in_chain(exc):
            print(
                "ERROR: --mock needs a local redis:8.2 (run `make redis-up`).",
                file=sys.stderr,
            )
            return 1
        raise
    finally:
        await client.aclose()

    if failures:
        print(
            f"\nFAIL: {len(failures)}/{len(QUESTIONS)} question(s) broke miss-then-hit: {failures}"
        )
        return 1
    print(f"\nPASS: all {len(QUESTIONS)} questions are miss-then-hit (sim >= 0.70).")
    return 0


async def _run_real() -> int:
    from memagent.app import Agent

    agent = Agent()  # real OpenAI + real search + real Redis
    failures: list[str] = []
    for question, _ in QUESTIONS:
        r1 = await agent.answer(question)
        r2 = await agent.answer(question)
        ok = (
            r1.route == "memory_miss_web_search"
            and r2.route == "memory_hit"
            and (r2.similarity or 0.0) >= 0.70
        )
        print(
            f"  [{'PASS' if ok else 'FAIL'}] {question!r}: turn1={r1.route}, turn2={r2.route}, sim={r2.similarity}"
        )
        if not ok:
            failures.append(question)
    return 1 if failures else 0


def main() -> int:
    mock = "--mock" in sys.argv[1:]
    if not mock and not Settings(_env_file=None).openai_api_key:
        print("ERROR: OPENAI_API_KEY required for real-key mode (or pass --mock).", file=sys.stderr)
        return 2
    return asyncio.run(_run_mock() if mock else _run_real())


if __name__ == "__main__":
    raise SystemExit(main())
