"""Grounding eval harness — an honest DEMONSTRATION, not a benchmark (FR-015, FR-016).

python scripts/eval_grounding.py --mock   # keyless AND redis-less; derives verdicts, non-zero on regression.
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


ABSTAIN = "insufficient context"  # the exact refusal ANSWER_SYS mandates


async def _run_mock() -> int:
    """Keyless, Redis-less DEMONSTRATION that also exercises its own branches.

    The answerer emits the real "insufficient context" refusal whenever the context
    carries no source_url to cite; the judge DERIVES each verdict from the actual
    answer (not a hard-coded pass) — abstained_correctly from whether the answer
    abstained, grounded/citations from the cited source in the non-abstain cases.
    So the scorecard reflects real behaviour and the run returns non-zero if that
    behaviour regressed, instead of being a green-forever no-op.
    """
    from memagent.interfaces import CompletionResult

    _usage = {"input_tokens": 0, "output_tokens": 0, "model": "mock"}

    class _CtxAnswerer:
        """Answers from context, abstaining (per ANSWER_SYS) when nothing is citable."""

        def __init__(self):
            self.complete_calls = 0

        async def complete(self, system, messages):
            self.complete_calls += 1
            ctx = messages[-1]["content"]
            text = (
                f"Grounded in the context. Sources:\n- {SRC}" if "source_url=" in ctx else ABSTAIN
            )
            return CompletionResult(text=text, usage=_usage)

    class _DerivingJudge:
        """Reads the answer + expected label out of the prompt and derives the verdict,
        so a broken answerer surfaces as a failing row rather than a silent pass."""

        def __init__(self):
            self.parse_calls = 0

        async def parse(self, system, user, schema):
            self.parse_calls += 1
            answer = user.split("\nAnswer: ", 1)[1].rsplit("\nExpected: ", 1)[0]
            expected_abstain = user.rsplit("Expected: ", 1)[-1].strip() == "abstain"
            abstained = answer.strip() == ABSTAIN
            cited = (not abstained) and SRC in answer
            verdict = schema(
                grounded=cited,
                citations_valid=cited,
                abstained_correctly=(abstained == expected_abstain),
            )
            return verdict, _usage

    rows = await _score(_CtxAnswerer(), _DerivingJudge())
    _render(rows)
    ok = all(
        v.abstained_correctly and (expect == "abstain" or (v.grounded and v.citations_valid))
        for _q, expect, v in rows
    )
    return 0 if ok else 1


async def _run_real() -> int:
    from memagent.llm.clients import build_openai_clients

    conv, analytics, _ = build_openai_clients(Settings(_env_file=None))
    rows = await _score(conv, analytics)
    _render(rows)
    # Same ok-predicate as _run_mock: real mode must also gate on the judge's
    # grounding/citation/abstention verdicts instead of always returning 0.
    ok = all(
        v.abstained_correctly and (expect == "abstain" or (v.grounded and v.citations_valid))
        for _q, expect, v in rows
    )
    return 0 if ok else 1


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
