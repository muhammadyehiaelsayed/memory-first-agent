"""URL canonicalization and identity hashing (PLAN section 4.2 + specs/002 research D9).

Canonical form: lowercase scheme + host (case-insensitive per RFC 3986), fragment
dropped, every utm_* query parameter dropped, remaining params and path case preserved.
"""

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonicalize(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_")
        ]
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(canonicalize(url).encode()).hexdigest()[:16]
