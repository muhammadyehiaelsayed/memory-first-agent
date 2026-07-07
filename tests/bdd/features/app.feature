# Module: src/memagent/app.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-2-memory-path.md, milestone-6-e2e-evals-delivery.md, code-derived
# Executable binding: tests/bdd/test_bdd_orchestration.py
Feature: The Agent facade assembles resources and answers turns (src/memagent/app.py)
  app.py is the public facade tying the whole system together. configure_logging
  sends operational logs to stderr so stdout stays pipe-clean; new_turn_state mints
  the one complete initial AgentState for a turn; build_resources assembles the real
  clients (LLMs, embedder, Redis store, search, fetch, turn logger); and the Agent
  compiles the graph once and drives a full memory-first turn end to end, returning a
  TurnResult. This is the object the CLI and evals call to realise the root routes.

  # covers: memagent.app.configure_logging
  Scenario: Operational logging is wired to stderr so stdout stays pipe-clean
    Given logging is configured from the keyless settings
    When the active structured-logging configuration is inspected
    Then its logger factory writes to stderr rather than stdout
    And the log stream is rendered for the console

  # covers: memagent.app.new_turn_state
  Scenario: A fresh turn starts allowed, thresholded from settings and unrouted until proven
    Given a fresh turn state built for the question "How does Redis vector search work?"
    Then the guard verdict starts as "allow" and the sanitized query mirrors the question
    And the threshold is taken from the configured similarity threshold
    And the route defaults to "failed" until a node proves otherwise
    And the turn carries a non-empty turn id and the conversation history is capped

  # covers: memagent.app.build_resources
  Scenario: Building resources assembles the real clients without a live connection
    Given resources are built from the keyless settings
    Then the memory store is a Redis-backed store and the embedder matches the configured dimension
    And the searcher is the Tavily-first fallback provider and the fetcher is the httpx page fetcher
    And the same settings object is threaded through the resources

  # covers: memagent.app.Agent.__init__
  Scenario: Constructing the agent compiles the graph once and mints a session id
    Given an agent constructed from keyless resources
    Then it holds a compiled, invokable graph and the resources it was given
    And it has a non-empty session id distinct from a second agent's

  # covers: memagent.app.Agent.ensure_ready
  Scenario: The agent provisions its memory index once at startup and is idempotent
    Given a live agent over an empty memory index
    When the agent is made ready twice against a dropped index
    Then the memory index exists and readiness is a no-op the second time

  # source: milestone-6-e2e-evals-delivery.md :: Turn 1 misses memory and searches the web
  # covers: memagent.app.Agent.answer
  Scenario: Answering a novel question misses memory, reaches the web and cites its sources
    Given a live agent over an empty memory index
    And the web returns a page relevant to the question
    When the agent answers the question
    Then the returned turn result is routed "memory_miss_web_search"
    And the result carries a non-empty answer and cites the web source URL
    And the reported similarity is None because memory was empty
