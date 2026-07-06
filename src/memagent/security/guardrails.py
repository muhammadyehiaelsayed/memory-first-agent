"""L1 input screen (M5).

`screen_input` is a pure function: NFKC-normalise -> strip zero-width -> length-cap ->
match the shared PATTERN_REGISTRY, folding severities by explicit rank. Order is
load-bearing: a payload hidden past the cap is truncated away before matching, and an
evasion (zero-width joiners inside "ignore") normalises before matching. The `guard_input`
NODE (nodes/guard.py) wraps this and owns fail-open + state writes.
"""

import unicodedata
from dataclasses import dataclass
from typing import Literal

from memagent.config import Settings
from memagent.security.patterns import PATTERN_REGISTRY, Severity, max_severity

# U+200B ZERO WIDTH SPACE, U+200C ZWNJ, U+200D ZWJ, U+FEFF BOM/ZWNBSP.
ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"), None)


@dataclass(frozen=True)
class GuardResult:
    verdict: Literal["allow", "flag", "block"]
    sanitized_query: str  # NFKC-normalised, zero-width-stripped, length-capped
    events: list[str]  # matched pattern names + "length_capped" (+ "fail_open" set by the node)


def screen_input(query: str, settings: Settings) -> GuardResult:
    events: list[str] = []
    norm = unicodedata.normalize("NFKC", query).translate(ZERO_WIDTH)
    if len(norm) > settings.guard_max_query_chars:
        norm = norm[: settings.guard_max_query_chars]
        events.append("length_capped")
    severity: Severity | None = None
    for pattern in PATTERN_REGISTRY:
        if pattern.regex.search(norm):
            events.append(pattern.name)
            severity = max_severity(severity, pattern.severity)
    verdict: Literal["allow", "flag", "block"] = (
        "block" if severity is Severity.HIGH else "flag" if severity is Severity.MEDIUM else "allow"
    )
    return GuardResult(verdict=verdict, sanitized_query=norm, events=events)
