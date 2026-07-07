# Module: src/memagent/memory/schema.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-1-scaffold-and-memory-schema.md
# Executable binding: tests/bdd/test_bdd_memory_support.py
Feature: The web_memory vector index schema and its lifecycle (src/memagent/memory/schema.py)
  Before the agent can vector-search Redis FIRST on a memory hit, the web_memory
  index must exist with the exact field layout the store writes and reads. This
  module defines that schema once and owns the create / ensure / wipe lifecycle
  plus the dimension contract every later milestone loads. It is the substrate
  the root "answer from memory" scenario stands on.

  # covers: memagent.memory.schema.build_schema
  Scenario: The schema pins eleven fields and a cosine float32 vector
    # source: milestone-1-scaffold-and-memory-schema.md :: "the schema declares eleven fields"
    When the web_memory schema is built from settings
    Then it declares exactly 11 fields named chunk_text, url, url_hash, title, doc_type, source_query, chunk_index, fetched_at, sanitizer_flags, content_sha256, embedding
    And the index name is "web_memory" with hash storage and a "chunk" prefix
    And the embedding field is a flat cosine float32 vector of 1536 dims

  # covers: memagent.memory.schema.get_index
  Scenario: An async search index is built over the schema and a Redis client
    Given a Redis client for the configured URL
    When an index is built from the schema and that client
    Then the result is an AsyncSearchIndex bound to that client
    And the index is named "web_memory"

  # covers: memagent.memory.schema.ensure_index
  Scenario: Ensuring the index creates it once and is a no-op thereafter
    # source: milestone-1-scaffold-and-memory-schema.md :: "wipe-memory is idempotent when the index already exists"
    Given a running Redis with no web_memory index
    When ensure_index is called twice in a row
    Then the first call reports it created the index
    And the second call reports no creation
    And the web_memory index exists afterwards

  # covers: memagent.memory.schema.wipe_index
  Scenario: Wiping drops the index and its metadata hashes then recreates it empty
    # source: milestone-1-scaffold-and-memory-schema.md :: "wipe-memory drops existing data"
    Given a running Redis with the web_memory index and a stale doc: meta hash
    When wipe_index runs
    Then the stale doc: meta hash is gone
    And an empty web_memory index still exists

  # covers: memagent.memory.schema.assert_index_dims
  Scenario Outline: A mismatched embedding dimension is rejected while a match passes
    # source: milestone-1-scaffold-and-memory-schema.md :: "a dimension mismatch raises an actionable error"
    When assert_index_dims is called with an embedder dimension of <dim>
    Then the dimension check <verdict>
    Examples:
      | dim  | verdict |
      | 1536 | passes  |
      | 3072 | raises  |
