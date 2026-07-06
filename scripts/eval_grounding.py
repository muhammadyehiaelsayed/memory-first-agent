"""Grounding eval harness — an honest DEMONSTRATION, not a benchmark (FR-015, FR-016).

python scripts/eval_grounding.py --mock   # FakeLLM answerer + judge; keyless AND redis-less; exit 0.
python scripts/eval_grounding.py          # real: nano model as LLM-judge (needs OPENAI_API_KEY).
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # tests/ import (recheck H)

from pydantic import BaseModel  # noqa: E402

from memagent.config import Settings  # noqa: E402


class GroundingVerdict(BaseModel):
    grounded: bool  # every claim is supported by the supplied context
    citations_valid: bool  # cited URLs appear as a source_url in the context
    abstained_correctly: bool  # for abstain cases, the answerer refused


SRC = "https://redis.io/docs/vector"
CASES = [  # (question, context, expect) — 4 grounded, 2 abstain
    (
        "How does Redis store vectors?",
        f"Redis stores vectors in HASH fields. source_url={SRC}",
        "grounded",
    ),
    (
        "What distance metric does the index use?",
        f"The web_memory index uses cosine distance. source_url={SRC}",
        "grounded",
    ),
    (
        "What is the default similarity threshold?",
        f"The default threshold is 0.70, inclusive. source_url={SRC}",
        "grounded",
    ),
    (
        "What TTL applies to stored chunks?",
        f"Stored chunks expire after 7 days. source_url={SRC}",
        "grounded",
    ),
    ("Who won the 2019 cricket world cup?", "", "abstain"),
    ("What is the capital of Mars?", "This page is about Redis vector search only.", "abstain"),
]
ANSWER_SYS = (
    "Answer ONLY from the provided context and cite the source_url. If the context is "
    "insufficient, reply exactly 'insufficient context'."
)
JUDGE_SYS = (
    "You are a strict grounding judge. Score grounded, citations_valid, and abstained_correctly."
)


async def _score(answerer, judge) -> list[tuple]:
    rows = []
    for q, ctx, expect in CASES:
        ans = (
            await answerer.complete(
                ANSWER_SYS, [{"role": "user", "content": f"Context:\n{ctx}\n\nQuestion: {q}"}]
            )
        ).text
        verdict, _ = await judge.parse(
            JUDGE_SYS,
            f"Question: {q}\nContext: {ctx}\nAnswer: {ans}\nExpected: {expect}",
            GroundingVerdict,
        )
        rows.append((q, expect, verdict))
    return rows


def _render(rows: list[tuple]) -> None:
    print("Grounding eval — DEMONSTRATION, not a benchmark (fixed cases, LLM-as-judge).\n")
    g = c = a = 0
    for q, expect, v in rows:
        print(
            f"  [{expect:8}] grounded={int(v.grounded)} citations_valid={int(v.citations_valid)} "
            f"abstained_correctly={int(v.abstained_correctly)}  {q!r}"
        )
        g, c, a = g + v.grounded, c + v.citations_valid, a + v.abstained_correctly
    n = len(rows)
    print(
        f"\nAggregate over {n} cases: grounded {g}/{n}, citations_valid {c}/{n}, abstained_correctly {a}/{n}"
    )
    print("(Demonstration only — a real benchmark needs a labeled dataset and independent judges.)")


async def _run_mock() -> int:
    from tests.conftest import FakeLLM

    answerer = FakeLLM(answer=f"Grounded in the context. Sources:\n- {SRC}")
    judge = FakeLLM(
        schema_factory=lambda s: GroundingVerdict(
            grounded=True, citations_valid=True, abstained_correctly=True
        )
    )
    _render(await _score(answerer, judge))
    return 0


async def _run_real() -> int:
    from memagent.llm.clients import build_openai_clients

    conv, analytics, _ = build_openai_clients(Settings(_env_file=None))
    _render(await _score(conv, analytics))
    return 0


def main() -> int:
    mock = "--mock" in sys.argv[1:]
    if not mock and not Settings(_env_file=None).openai_api_key:
        print(
            "ERROR: OPENAI_API_KEY required for the real grounding eval (or pass --mock).",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_run_mock() if mock else _run_real())


if __name__ == "__main__":
    raise SystemExit(main())
