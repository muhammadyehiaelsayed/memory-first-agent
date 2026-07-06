"""Severity-tagged injection pattern registry (M5) — shared by L1 and L3.

The SAME registry powers the L1 input screen (`guardrails.screen_input`) and the L3
content sanitizer (`sanitizer.sanitize`): one place to tune, two defence points. The
category -> severity map is Clarification Q1, pinned by the guard tests and the T1 fixture:
instruction-override / prompt-leak / role-hijack -> HIGH (block); fake-role-markers /
exfil-coaxing -> MEDIUM (flag + skip_store). Patterns are kept tight enough that benign
queries ("How does Redis vector search work?") never match.
"""

import re
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    HIGH = "high"      # -> block
    MEDIUM = "medium"  # -> flag + skip_store


# Explicit rank: severity string values do NOT sort in severity order ("high" < "medium").
_RANK: dict[object, int] = {None: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def max_severity(a: "Severity | None", b: "Severity | None") -> "Severity | None":
    """Return the higher of two severities by explicit rank (HIGH > MEDIUM > None)."""
    return a if _RANK[a] >= _RANK[b] else b


@dataclass(frozen=True)
class Pattern:
    name: str
    severity: Severity
    regex: re.Pattern


def _c(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


PATTERN_REGISTRY: list[Pattern] = [
    # --- HIGH severity -> block ---
    Pattern(
        "instruction_override",
        Severity.HIGH,
        # A directional word is REQUIRED (previous/prior/above/earlier/preceding/system);
        # all|any|the|your|these|those are only optional quantifiers before it, so benign
        # "ignore any formatting instructions" no longer trips (workflow finding).
        _c(
            r"\b(?:ignore|disregard|forget|override)\b[\s\S]{0,40}"
            r"(?:\b(?:all|any|the|your|these|those)\b\s+)?"
            r"\b(?:previous|prior|above|earlier|preceding|system)\b"
            r"[\s\S]{0,25}\binstruction"
        ),
    ),
    Pattern(
        "prompt_leak",
        Severity.HIGH,
        _c(r"\b(reveal|show|print|repeat|display|expose|leak|give me|tell me)\b[\s\S]{0,40}\b(system|initial|original|developer)\b[\s\S]{0,15}(prompt|instruction|message|rules)"),
    ),
    Pattern(
        "role_hijack",
        Severity.HIGH,
        # A persona-adoption framing verb must be followed (within 30 chars) by a JAILBREAK
        # persona token — so benign "act as a mentor" / "developer mode in Chrome" / "from now
        # on you will notice…" no longer match (workflow finding); plus standalone jailbreak
        # tokens. This shared registry also screens fetched content (L3), so tightness here
        # keeps benign pages from being corrupted. NB: "developer mode" is deliberately NOT a
        # persona token — it collides with a real product feature (ChromeOS/Chrome/Windows
        # "developer mode"), and manual testing showed it corrupted a benign Chromium doc;
        # the DAN "Developer Mode" jailbreak is still caught by its dan/do-anything-now/
        # unrestricted hallmarks.
        _c(
            r"\b(?:you are now|from now on|pretend|roleplay as|act as|behave as|switch to)\b[\s\S]{0,30}"
            r"\b(?:dan|unrestricted|jailbroken|uncensored|do[ -]?anything[ -]?now|"
            r"no[ -]?restrictions?|without (?:any )?(?:restrictions|rules|filters?)|a different (?:ai|assistant|persona))\b"
            # standalone tokens are unambiguous attack phrases only. NB: bare "jailbreak" is
            # deliberately excluded — it collides with benign descriptive prose ("how you can
            # jailbreak your device" on a security doc) and benign topics ("how do I jailbreak
            # my phone"); a real jailbreak attempt still hits the framing-gated "jailbroken".
            r"|\b(?:dan mode|do anything now)\b"
        ),
    ),
    # --- MEDIUM severity -> flag + skip_store ---
    Pattern(
        "fake_role_markers",
        Severity.MEDIUM,
        _c(r"(?m)^\s*(?:system|assistant|user)\s*:|<\|?im_(?:start|end)\|?>|\[/?(?:INST|SYS)\]"),
    ),
    Pattern(
        "exfil_coaxing",
        Severity.MEDIUM,
        _c(r"\b(?:e-?mail|send|forward|upload|post|exfiltrate|transmit)\b[\s\S]{0,40}(?:https?://|[\w.+-]+@[\w-]+\.\w+)"),
    ),
]
