# Module: src/memagent/config.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-1-scaffold-and-memory-schema.md
# Executable binding: tests/bdd/test_bdd_contracts.py
# covers-module: memagent.config
Feature: Configuration is the single source of the agent's tunable values (src/memagent/config.py)
  The memory-hit decision the root scenario relies on is a deterministic branch on
  "cosine similarity >= 0.70", and that 0.70 lives here as a Settings default rather
  than a literal buried in a node. This module holds every tunable number and env
  name for the agent: the defaults load with no .env present, an environment variable
  overrides its field, the one runtime key stays optional so keyless paths run, and
  unrecognised variables are ignored.

  # source: milestone-1-scaffold-and-memory-schema.md :: defaults load with no .env present
  Scenario: The documented defaults load when no environment overrides are present
    Given no similarity or key overrides are set in the environment
    When Settings are constructed from the environment
    Then the similarity threshold defaults to 0.70
    And the embedding dimension defaults to 1536
    And the memory index is named "web_memory"
    And the memory TTL defaults to 604800 seconds
    And the chunk size defaults to 1600 characters

  # source: milestone-1-scaffold-and-memory-schema.md :: an environment variable overrides its default
  Scenario: An environment variable overrides the field default
    Given the environment sets SIMILARITY_THRESHOLD to "0.85"
    When Settings are constructed from the environment
    Then the similarity threshold is exactly 0.85

  # source: milestone-1-scaffold-and-memory-schema.md :: missing OPENAI_API_KEY does not raise
  Scenario: The one runtime key stays optional so keyless paths keep working
    Given OPENAI_API_KEY is not set in the environment
    When Settings are constructed from the environment
    Then construction succeeds without raising
    And the OpenAI API key is the empty string

  # source: milestone-1-scaffold-and-memory-schema.md :: unknown environment variables are ignored
  Scenario: Unknown environment variables are ignored rather than rejected
    Given an unrecognised environment variable SOME_UNKNOWN_VAR is set to "x"
    When Settings are constructed from the environment
    Then construction succeeds without raising
    And the settings object has no attribute named "some_unknown_var"
