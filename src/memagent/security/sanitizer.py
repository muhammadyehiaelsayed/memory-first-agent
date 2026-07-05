"""L3 sanitize-before-store; pass-through seam until M5 (M3/M5)."""


def sanitize(text: str) -> tuple[str, list[str]]:
    """L3 sanitize-before-store. M3 stub: pass-through.

    M5 replaces the internals (strip script/style/iframe, HTML comments, data: URIs,
    long base64, markdown images; neutralise injection phrases to
    '[removed-suspicious-instruction]'; return provenance flags).
    ingest_content must NOT change when M5 lands.
    """
    return text, []
