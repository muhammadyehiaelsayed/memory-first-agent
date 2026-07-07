# Module: scripts/seed_memory.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-6-e2e-evals-delivery.md (demoable miss->hit lifecycle); code-derived from scripts/seed_memory.py (FR-M2-23)
# Executable binding: tests/bdd/test_bdd_scripts_tooling.py
Feature: Seeding a document primes Redis so a memory hit is demoable (scripts/seed_memory.py)
  A memory hit requires memory to already hold content similar to the question. This
  script exists to make that state on demand: it canonicalises a URL, chunks the
  markdown, embeds each chunk, and stores the chunks in the real web_memory index so a
  later identical question routes memory_hit. The scenarios exercise the real store
  against a live Redis with the OpenAI embedder replaced by a deterministic fake.

  # covers: scripts.seed_memory.seed
  Scenario: Seeding a page embeds and stores one chunk per chunk in Redis
    Given a running Redis with the web_memory index
    And the OpenAI client factory is replaced with a deterministic fake embedder
    When a page of markdown is seeded under a source URL
    Then it stores one chunk id per produced chunk
    And each stored chunk key is present in Redis under the page identity

  # covers: scripts.seed_memory.main
  Scenario: The seed entry point accepts inline text and reports what it stored
    Given a running Redis with the web_memory index
    And the OpenAI client factory is replaced with a deterministic fake embedder
    When the seed entry point runs with an inline text argument
    Then it reports how many chunks were seeded for the canonical URL
