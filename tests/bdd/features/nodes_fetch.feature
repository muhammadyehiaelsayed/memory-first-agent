# Module: src/memagent/nodes/fetch.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-3-web-pipeline.md
# Executable binding: tests/bdd/test_bdd_nodes_web_path.py
Feature: Fetch-pages node filters unsafe URLs and bounds how many pages are fetched (src/memagent/nodes/fetch.py)
  After a successful web search the fetch_pages node turns result URLs into fetched
  documents. It first runs the SSRF / diversity URL filter, then hands only the top
  FETCH_TOP_N surviving URLs to the page fetcher. When every fetch fails the node
  yields no documents so the graph degrades to the snippets-only answer rather than
  crashing.

  # source: milestone-3-web-pipeline.md :: Private, loopback and link-local targets are rejected
  # covers: memagent.nodes.fetch.make_fetch_pages
  Scenario: Unsafe URLs are filtered out and only the top N safe pages are fetched
    Given search results for six public domains plus one loopback address
    And FETCH_TOP_N is 5
    When the fetch pages node runs
    Then the loopback address is never handed to the fetcher
    And exactly five URLs are handed to the fetcher
    And a fetched document is returned for each fetched URL

  # source: milestone-3-web-pipeline.md :: FR-M3-16 (a failing fetch is skipped, not fatal)
  # covers: memagent.nodes.fetch.make_fetch_pages
  Scenario: A total fetch failure degrades gracefully instead of crashing
    Given search results with one fetchable URL
    And a fetcher that raises on every call
    When the fetch pages node runs
    Then the returned state carries no fetched documents
    And a fetch_pages error is recorded on the turn
