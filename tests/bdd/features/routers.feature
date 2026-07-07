# Module: src/memagent/routers.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-2-memory-path.md
# Executable binding: tests/bdd/test_bdd_orchestration.py
Feature: Pure routing decisions steer every turn (src/memagent/routers.py)
  The five pure router functions are the deterministic branches behind all five
  root routes: route_after_guard realises "blocked", route_after_embed realises
  "failed", route_after_memory is the inclusive cosine >= 0.70 hit/miss decision
  behind "memory_hit" vs the web fallback, and route_after_search /
  route_after_fetch steer the "memory_miss_web_search" and "degraded_web" legs.
  They are pure functions of the state dict — no I/O, no model judgment — so the
  hit/miss decision lives in code, never in an LLM.

  # source: milestone-2-memory-path.md :: route_after_guard blocks a blocked verdict
  # covers: memagent.routers.route_after_guard
  Scenario: A blocked verdict is routed straight to logging while everything else proceeds
    Given a guard verdict of "block"
    When the post-guard router decides where to go
    Then it routes to "log_turn"
    And a guard verdict of "allow" routes to "embed_query"
    And a guard verdict of "flag" routes to "embed_query"

  # source: milestone-2-memory-path.md :: route_after_embed sends a valid vector to memory search
  # covers: memagent.routers.route_after_embed
  Scenario: A successful embedding proceeds to memory search and a missing vector fails the turn
    Given a state carrying a 1536-float query vector
    When the post-embed router decides where to go
    Then it routes to "memory_search"
    And a state whose query vector is None routes to "answer_failure"
    And a state with no query vector at all routes to "answer_failure"

  # source: milestone-2-memory-path.md :: the 0.30 distance routes as an inclusive hit
  # covers: memagent.routers.route_after_memory
  Scenario: A similarity exactly at the 0.70 threshold is an inclusive memory hit
    Given a top similarity of 0.70 and a threshold of 0.70
    When the post-memory router decides where to go
    Then it routes to "answer_from_memory"
    And a top similarity of 0.6999 at the same threshold routes to "web_search"
    And an absent top similarity routes to "web_search"

  # source: milestone-2-memory-path.md :: route_after_search with results proceeds to fetch
  # covers: memagent.routers.route_after_search
  Scenario: Search results proceed to fetching and no results fails the turn
    Given search results containing at least one entry
    When the post-search router decides where to go
    Then it routes to "fetch_pages"
    And an empty search-results list routes to "answer_failure"

  # source: milestone-2-memory-path.md :: route_after_fetch with fetched docs proceeds to ingest
  # covers: memagent.routers.route_after_fetch
  Scenario: Fetched pages proceed to ingestion and nothing fetched answers from snippets
    Given fetched documents containing at least one page
    When the post-fetch router decides where to go
    Then it routes to "ingest_content"
    And an empty fetched-docs list routes to "answer_from_web"
