# Module: src/memagent/memory/urls.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-3-web-pipeline.md, code-derived (memagent/memory/urls.py)
# Executable binding: tests/bdd/test_bdd_memory_support.py
Feature: URL canonicalisation and identity hashing for ingest dedup (src/memagent/memory/urls.py)
  On a memory miss the agent ingests fetched pages "into memory for future
  reuse". Reuse needs a stable identity per page so the same URL is stored,
  deduped, and freshness-gated under one key regardless of tracking-parameter
  or host-casing variation. This module canonicalises URLs and derives that
  16-character identity hash.

  # covers: memagent.memory.urls.canonicalize
  Scenario Outline: Tracking params, fragments and host casing collapse to one form
    When the URL "<raw>" is canonicalised
    Then the canonical URL is "<canonical>"
    Examples:
      | raw                                    | canonical              |
      | HTTP://Example.com/a?utm_source=x#frag | http://example.com/a   |
      | http://example.com/a                   | http://example.com/a   |
      | https://Foo.COM/p?utm_medium=e&id=7    | https://foo.com/p?id=7 |

  # covers: memagent.memory.urls.url_hash
  Scenario: Variant spellings of one page share a stable 16-char identity
    When the identity hashes of "HTTP://Example.com/a?utm_source=x#frag" and "http://example.com/a" are computed
    Then the two hashes are equal
    And the hash is 16 lowercase hexadecimal characters
