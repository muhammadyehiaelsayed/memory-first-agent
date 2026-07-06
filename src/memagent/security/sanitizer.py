"""L3 sanitize-before-store (M5) — real body replacing the M3 pass-through (Ruling C).

Runs between markdown conversion and chunking (wired by M3's ingest_content; that call-site
is FROZEN). Strips dangerous constructs and NEUTRALISES injection phrases to a visible
marker — never silently deletes — so stored text is safe to replay yet grounding stays
coherent and auditable. The signature `sanitize(text) -> (clean_text, flags)` is unchanged.
Shares PATTERN_REGISTRY with the L1 screen (one registry, two defence points).
"""

import re

from memagent.security.patterns import PATTERN_REGISTRY

NEUTRALIZED = "[removed-suspicious-instruction]"
BASE64_MIN = 512  # a base64 run this long or longer is stripped (PLAN-silent default)

_SCRIPT_RE = re.compile(r"(?is)<(script|style|iframe)\b.*?</\1>")
_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
_DATA_URI_RE = re.compile(r"""data:[^\s)"']+""")
_BASE64_RE = re.compile(rf"[A-Za-z0-9+/]{{{BASE64_MIN},}}={{0,2}}")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def strip_markdown_images(text: str) -> str:
    """Remove markdown images `![alt](url)` — shared by L3 and the T4 answer-output defence."""
    return _IMAGE_RE.sub("", text)


def _flag(n: int, flags: list[str], name: str) -> None:
    if n:
        flags.append(name)


def sanitize(text: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    text, n = _SCRIPT_RE.subn("", text)
    _flag(n, flags, "script_removed")  # script/style/iframe share one flag
    text, n = _COMMENT_RE.subn("", text)
    _flag(n, flags, "html_comment_removed")
    text, n = _DATA_URI_RE.subn("", text)
    _flag(n, flags, "data_uri_removed")
    text, n = _BASE64_RE.subn("", text)
    _flag(n, flags, "base64_blob_removed")
    text, n = _IMAGE_RE.subn("", text)
    _flag(n, flags, "markdown_image_removed")
    neutralised = 0
    for pattern in PATTERN_REGISTRY:
        text, n = pattern.regex.subn(NEUTRALIZED, text)
        neutralised += n
    _flag(neutralised, flags, "neutralized_instruction")
    return text, sorted(set(flags))
