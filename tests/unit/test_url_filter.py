"""filter_urls — the mini-SSRF guard (FR-M3-06..09), untested before M7.

The scheme allowlist + private-IP/SSRF block + JS-only denylist + max-2-per-domain cap were
named by the M3 spec (§7, owner tests/unit/test_fetch_retry.py) but asserted nowhere. A
regression in _is_private_host would silently let the cloud-metadata SSRF target through.
"""

from memagent.config import Settings
from memagent.web.fetch import _is_private_host, filter_urls

S = Settings(_env_file=None)


def test_ssrf_and_private_hosts_are_dropped():
    blocked = [
        "http://169.254.169.254/latest/meta-data",  # cloud metadata (link-local)
        "http://127.0.0.1/",  # loopback
        "http://10.0.0.5/",  # private RFC1918
        "http://192.168.1.1/",  # private RFC1918
        "http://localhost/",  # localhost by name
        "http://[::1]/",  # ipv6 loopback
    ]
    assert filter_urls(blocked, S) == []


def test_disallowed_schemes_are_dropped():
    urls = ["data:text/html,x", "file:///etc/passwd", "javascript:alert(1)", "ftp://x.com/a"]
    assert filter_urls(urls, S) == []


def test_js_only_denylist_is_dropped():
    urls = [
        "https://youtube.com/watch",
        "https://youtu.be/x",
        "https://x.com/a",
        "https://twitter.com/b",
    ]
    assert filter_urls(urls, S) == []


def test_max_two_per_registrable_domain():
    # sub.example.com shares the registrable domain example.com, so the third is capped out.
    kept = filter_urls(
        ["http://example.com/1", "http://sub.example.com/2", "http://example.com/3"], S
    )
    assert kept == ["http://example.com/1", "http://sub.example.com/2"]
    assert S.max_urls_per_domain == 2


def test_ordering_preserved_and_public_urls_kept():
    urls = [
        "http://169.254.169.254/",  # dropped (SSRF)
        "https://ok.org/a",
        "http://example.com/1",
        "https://ok.org/b",
    ]
    assert filter_urls(urls, S) == ["https://ok.org/a", "http://example.com/1", "https://ok.org/b"]


def test_is_private_host_predicate():
    for host in ("169.254.169.254", "127.0.0.1", "10.0.0.5", "192.168.1.1", "localhost", "::1"):
        assert _is_private_host(host) is True, host
    for host in ("8.8.8.8", "example.com", "redis.io"):
        assert _is_private_host(host) is False, host
