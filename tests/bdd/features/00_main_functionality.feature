# ============================================================================
# ROOT FEATURE — the main functionality of the memory-first web agent.
#
# Every other .feature file in this directory derives its scenarios from one
# of the five root scenarios below (one per Route literal, state.py:13) plus
# the per-turn logging invariant. Each derived file names its parent in a
# "Derived from" header comment.
#
# Sources: README.md (Architecture), src/memagent/routers.py,
#          specs/milestone-2-memory-path.md, specs/milestone-3-web-pipeline.md,
#          specs/milestone-4-llms-logging-analytics.md,
#          specs/milestone-5-security-reliability.md
# Executable binding: tests/bdd/test_bdd_main_functionality.py
# ============================================================================
Feature: Memory-first web agent answers questions
  A user asks a question. The agent guards the input, embeds it, and searches
  Redis vector memory FIRST. The hit/miss decision is a deterministic branch
  in code (cosine similarity >= 0.70, inclusive) — never a model judgment.
  On a hit it answers from stored memory; on a miss it searches the web,
  fetches and cleans pages, ingests them for future reuse, and answers
  grounded in the fetched content with source URLs. Failures degrade to a
  poorer answer instead of a crash, and every turn appends exactly one JSONL
  analytics record.

  # covers-route: memory_hit
  Scenario: Answer from memory when a similar question was seen before
    Given memory already holds content similar to the question
    When the user asks the question
    Then the turn is routed "memory_hit"
    And the answer is generated from the stored memory chunks
    And no web search is performed

  # covers-route: memory_miss_web_search
  Scenario: Fall back to the web and ingest what was found on a memory miss
    Given an empty memory
    And the web returns pages relevant to the question
    When the user asks the question
    Then the turn is routed "memory_miss_web_search"
    And the fetched content is ingested into memory for future reuse
    And the answer cites its source URLs

  # covers-route: degraded_web
  Scenario: Degrade gracefully when search succeeds but every page fetch fails
    Given an empty memory
    And the web search returns results whose pages cannot be fetched
    When the user asks the question
    Then the turn is routed "degraded_web"
    And the agent still produces an answer instead of crashing

  # covers-route: blocked
  Scenario: Block malicious input at the guard before any model call
    Given a question that triggers the input guard
    When the user asks the question
    Then the turn is routed "blocked"
    And no embedding, search, or answer model is invoked

  # covers-route: failed
  Scenario: Report failure when the query cannot be embedded
    Given the embedding service is unavailable
    When the user asks the question
    Then the turn is routed "failed"
    And the agent reports the failure instead of raising

  Scenario: Log exactly one analytics record for every turn
    Given an agent that has answered one turn by any route
    When the turn completes
    Then exactly one JSON line has been appended to the turn log
    And the record names the route that was taken
