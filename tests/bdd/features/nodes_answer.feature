# Module: src/memagent/nodes/answer.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-2-memory-path.md, milestone-3-web-pipeline.md
# Executable binding: tests/bdd/test_bdd_nodes_memory_path.py
Feature: Generate grounded answers with cited sources (src/memagent/nodes/answer.py)
  The answer nodes turn retrieved context into the user-facing answer for every
  terminal route. answer_from_memory produces the root "Answer from memory" hit;
  answer_from_web produces the "Fall back to the web" miss and the "Degrade
  gracefully" snippets-only path; answer_failure produces the deterministic
  "Report failure" apology. All of them dedupe sources by URL and every answer
  ends with a "Sources:" section.

  # source: milestone-2-memory-path.md :: "duplicate-URL hits are deduplicated in sources"
  # covers: memagent.nodes.answer._dedupe_sources
  Scenario: Duplicate source URLs collapse to a single reference
    Given three retrieved hits that share one source URL plus one blank-URL hit
    When the sources are deduplicated with origin "memory"
    Then exactly one source reference remains, tagged origin "memory"
    And the blank-URL hit is dropped

  # source: milestone-2-memory-path.md :: "a memory hit answers from the wrapped context and cites sources"
  # covers: memagent.nodes.answer.make_answer_from_memory
  Scenario: A memory hit is answered from stored context and cites its source
    Given memory holds a hit for a stored page with a URL and title
    When the answer_from_memory node runs
    Then the turn is routed "memory_hit"
    And the answer cites the stored URL with origin "memory"
    And the rendered answer ends with a "Sources:" section

  # source: milestone-3-web-pipeline.md :: "Context uses each page summary plus only the first two chunks"
  # covers: memagent.nodes.answer.make_answer_from_web
  Scenario: A web-miss answer is grounded in fetched pages and bounds context per page
    Given a fetched web page with a summary and four chunks
    When the answer_from_web node runs
    Then the turn is routed "memory_miss_web_search"
    And only the first two chunks of the page appear in the answer context
    And the web sources are cited with origin "web"

  # source: milestone-3-web-pipeline.md :: "No page fetched falls back to snippets with a disclaimer"
  # covers: memagent.nodes.answer.make_answer_from_web
  Scenario: When no page can be fetched the agent degrades to snippets with a disclaimer
    Given a web search that returned snippets but no fetchable pages
    When the answer_from_web node runs
    Then the turn is routed "degraded_web"
    And the degradation is recorded as "snippets_only"
    And the answer carries a low-confidence disclaimer

  # source: milestone-2-memory-path.md :: "failure is deterministic and calls no model"
  # covers: memagent.nodes.answer.make_answer_failure
  Scenario: The failure node returns a deterministic apology without calling any model
    Given a chat model spy that must not be called
    When the answer_failure node runs on a minimal state
    Then the turn is routed "failed"
    And the answer is the deterministic failure apology
    And no chat completion was ever requested
