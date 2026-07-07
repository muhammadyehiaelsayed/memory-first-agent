# Module: src/memagent/nodes/search.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-3-web-pipeline.md
# Executable binding: tests/bdd/test_bdd_nodes_web_path.py
Feature: Web search node runs the provider and records who answered (src/memagent/nodes/search.py)
  On a memory miss the agent leaves memory and searches the web. The web_search
  node is the first step of that branch: it asks the configured searcher for the
  sanitized query, records the results, and stamps which provider actually served
  the turn so the analytics log can attribute the web call. A provider failure is
  swallowed into an empty result set so the graph degrades instead of crashing.

  # covers: memagent.nodes.search.make_web_search
  Scenario: A successful web search feeds the miss branch and records the provider
    Given a searcher that returns three results and reports provider "tavily"
    And a memory-miss turn whose sanitized query is "how does redis persist data"
    When the web search node runs
    Then the returned state carries the three search results
    And the searcher was asked for exactly SEARCH_MAX_RESULTS results for that query
    And the state records the search provider as "tavily"

  # source: milestone-3-web-pipeline.md :: No results routes to answer_failure
  # covers: memagent.nodes.search.make_web_search
  Scenario: A search-provider failure degrades to an empty result set instead of raising
    Given a searcher that raises a transport error
    And a memory-miss turn whose sanitized query is "an obscure novel question"
    When the web search node runs
    Then the returned state carries no search results
    And a web_search error is recorded on the turn
    And the state records no search provider
