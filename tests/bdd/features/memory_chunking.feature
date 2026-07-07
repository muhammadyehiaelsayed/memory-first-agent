# Module: src/memagent/memory/chunking.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-3-web-pipeline.md, code-derived (memagent/memory/chunking.py)
# Executable binding: tests/bdd/test_bdd_memory_support.py
Feature: Markdown-aware chunking of fetched pages before ingestion (src/memagent/memory/chunking.py)
  When the agent ingests fetched content "into memory for future reuse", each
  page's cleaned markdown is split into bounded, overlapping chunks that are
  then embedded and stored. This module owns that split: chunk size and
  overlap, the minimum-length floor, and the per-page chunk cap.

  # covers: memagent.memory.chunking.chunk_markdown
  Scenario: A long page is split into overlapping, size-bounded chunks
    Given a long markdown document of many space-separated tokens
    When it is chunked with default settings
    Then every chunk is within the configured chunk size
    And there are at least two chunks
    And the tail of the first chunk reappears at the head of the second

  # covers: memagent.memory.chunking.chunk_markdown
  Scenario: A fragment below the minimum length is dropped entirely
    Given the markdown text "short."
    When it is chunked with default settings
    Then no chunks are returned

  # covers: memagent.memory.chunking.chunk_markdown
  Scenario: A whole short page above the floor survives as a single chunk
    Given a single paragraph that exceeds the 100-character floor but is shorter than one chunk
    When it is chunked with default settings
    Then exactly one chunk is returned equal to the input paragraph

  # covers: memagent.memory.chunking.chunk_markdown
  Scenario: The per-page chunk count is capped for cost control
    Given a very large markdown document
    When it is chunked with default settings
    Then no more than the configured maximum number of chunks is returned
