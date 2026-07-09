"""Generate .env.example from Settings — the single anti-drift mechanism (FR-M1-08).

Iterates ``Settings.model_fields`` in declaration order with a fixed per-field line
template (``ENV_NAME=<placeholder>`` plus an optional inline comment), so every field
is covered and the ordering cannot drift. Output MUST be byte-identical to the
committed .env.example: regenerating leaves ``git diff .env.example`` empty.

Secret-shaped fields deliberately do NOT emit their raw Python defaults:
OPENAI_API_KEY emits the illustrative ``sk-...`` placeholder; OPENAI_BASE_URL and
TAVILY_API_KEY emit blank (their defaults are ``None``/``""`` — never the literal
``None``).
"""

from pathlib import Path

from memagent.config import Settings

# Placeholder overrides for secret-shaped fields (never emit raw defaults for these).
PLACEHOLDERS: dict[str, str] = {
    "openai_api_key": "sk-...",
    "openai_base_url": "",
    "tavily_api_key": "",
    "langsmith_tracing": "false",  # dotenv-style bool, not the Python literal `False`
    "langsmith_api_key": "",
}

# Inline comments, verbatim from PLAN section 10.3. Comment column starts at char 40.
COMMENTS: dict[str, str] = {
    "openai_api_key": "# the ONE required key (LLMs + embeddings)",
    "openai_base_url": "# optional - GitHub Models endpoint + GitHub PAT for free dev",
    "tavily_api_key": "# optional - blank = keyless DuckDuckGo fallback",
    "conversation_model": "# verified 2026-07-04; gpt-5.4 flagship = zero-code-change fallback",
    "similarity_threshold": "# inclusive; hit <=> 1 - distance >= this",
    "memory_ttl_seconds": "# 7d; 0 disables",
    "wait_cap_scale": "# tests set 0 -> instant retries through prod code path",
    "langsmith_tracing": "# opt-in: true + key -> one LangSmith trace per turn",
    "langsmith_api_key": "# optional - blank keeps tracing off (zero egress)",
}

COMMENT_COLUMN = 39


def render() -> str:
    lines: list[str] = []
    for name, field in Settings.model_fields.items():
        value = PLACEHOLDERS.get(name, field.default)
        entry = f"{name.upper()}={value}"
        comment = COMMENTS.get(name)
        if comment:
            entry = f"{entry:<{COMMENT_COLUMN}}{comment}"
        lines.append(entry)
    return "\n".join(lines) + "\n"


def main() -> None:
    out = Path(__file__).resolve().parent.parent / ".env.example"
    out.write_text(render(), encoding="utf-8")
    print(f"Wrote {out} ({len(Settings.model_fields)} settings)")


if __name__ == "__main__":
    main()
