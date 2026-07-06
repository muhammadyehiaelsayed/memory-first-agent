"""Capture a live miss->hit demo transcript -> docs/demo_transcript.md (FR-020).

Real OpenAI + real search + real redis:8.2 ONLY — Constitution VIII forbids GitHub Models for
the recorded demo. Absent a real key, docs/demo_transcript.md stays a committed
"pending real-key capture" placeholder (Clarification Q1) and does NOT block v1.0.
"""

import asyncio
import sys
from pathlib import Path

from memagent.app import Agent
from memagent.config import Settings

QUESTION = "How does Redis vector search work?"
OUT = Path("docs/demo_transcript.md")


def _banner(r) -> str:
    if r.route == "memory_hit":
        return f"[MEMORY HIT sim={r.similarity:.2f}]"
    if r.route == "memory_miss_web_search":
        return "[MEMORY MISS -> searching the web]"
    return f"[{r.route}]"


async def _capture() -> str:
    agent = Agent()  # real resources (real OpenAI + real search + real Redis)
    out = [
        "# Demo transcript — memory-first miss->hit",
        "",
        "Captured live (real OpenAI + real search + real redis:8.2); the same question asked twice.",
    ]
    for i in (1, 2):
        r = await agent.answer(QUESTION)
        out += [
            "",
            f"## Turn {i}",
            "",
            f"**Q:** {QUESTION}",
            "",
            f"**Route:** `{r.route}` {_banner(r)}",
        ]
        if r.sources:
            out += ["", "**Sources:**"] + [f"- {s['url']} ({s['origin']})" for s in r.sources]
        out += ["", "**Answer:**", "", r.answer or ""]
    return "\n".join(out) + "\n"


def main() -> int:
    if not Settings(_env_file=None).openai_api_key:
        print(
            "ERROR: OPENAI_API_KEY required to capture the demo transcript (real key only — "
            "GitHub Models is forbidden for the recorded demo). docs/demo_transcript.md stays "
            "a 'pending real-key capture' placeholder (Clarification Q1).",
            file=sys.stderr,
        )
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(asyncio.run(_capture()), encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
