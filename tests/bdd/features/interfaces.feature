# Module: src/memagent/interfaces.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Derived from: 00_main_functionality.feature :: "Log exactly one analytics record for every turn"
# Spec sources: milestone-1-scaffold-and-memory-schema.md
# Executable binding: tests/bdd/test_bdd_contracts.py
Feature: Dependency-injection Protocols define the collaborator contracts (src/memagent/interfaces.py)
  Every root scenario is served by collaborators behind these Protocols: the embedder
  and chat model on the memory-hit answer, the searcher and page fetcher on the memory
  miss, the memory store on the hit/miss branch, and the turn logger on the per-turn
  record. Each scenario exercises a conforming implementation of one contract and
  asserts both the documented behaviour and that the Protocol declares the method with
  the right async shape. The load-bearing contract asserted here is the store's: knn
  returns the RAW unfiltered top-k with similarity attached, never the threshold cut.

  # covers: memagent.interfaces.Embedder.embed
  Scenario: An embedder maps a batch of texts to fixed-width vectors
    Given a conforming embedder
    When it embeds a batch that repeats one text
    Then it returns one vector per input text
    And every vector has the configured embedding width
    And identical input texts produce identical vectors
    And the Embedder contract declares embed as an async method

  # covers: memagent.interfaces.ChatLLM.complete
  Scenario: A chat model returns generated text alongside a token-usage record
    Given a conforming chat model
    When it completes a system-plus-user conversation
    Then the result carries the generated answer text
    And the result carries a usage record with input, output and model
    And the ChatLLM contract declares complete as an async method

  # covers: memagent.interfaces.ChatLLM.parse
  Scenario: A chat model parses a prompt into a typed schema instance with usage
    Given a conforming classifier chat model
    When it parses a query into a QueryClassification schema
    Then it returns the populated schema instance and a usage record
    And the parsed instance is a QueryClassification
    And the ChatLLM contract declares parse as an async method

  # covers: memagent.interfaces.WebSearcher.search
  Scenario: A web searcher returns ranked results mapped from the provider response
    Given a Tavily-backed web searcher
    When it searches for a query capped at three results
    Then it returns three ranked SearchResult records
    And each result preserves its zero-based rank order
    And the snippet is mapped from the provider content field
    And the WebSearcher contract declares search as an async method

  # covers: memagent.interfaces.MemoryStore.ensure_ready
  Scenario: A memory store can be asked to provision itself before first use
    Given a conforming in-memory store
    When its index provisioning is ensured
    Then the provisioning completes without error
    And the MemoryStore contract declares ensure_ready as an async method

  # covers: memagent.interfaces.MemoryStore.knn
  Scenario: A memory store returns the raw nearest neighbours without applying the threshold
    Given an in-memory store holding hits both above and below the similarity threshold
    When the store is queried for its nearest neighbours
    Then it returns the raw top-k ordered by descending similarity
    And hits below the 0.70 threshold are still returned unfiltered
    And every returned hit carries its similarity score
    And the MemoryStore contract declares knn as an async method

  # covers: memagent.interfaces.MemoryStore.store
  Scenario: Storing a page's chunks returns one identifier per persisted chunk
    Given an in-memory store and a page split into three chunks
    When the chunks and their vectors are stored
    Then one chunk identifier is returned per chunk
    And the MemoryStore contract declares store as an async method

  # covers: memagent.interfaces.MemoryStore.is_fresh
  Scenario: A store reports whether a URL hash was seen within the freshness window
    Given an in-memory store that has recently seen one URL hash
    When freshness is checked for a seen and an unseen hash
    Then the seen hash is reported fresh and the unseen hash is not
    And the MemoryStore contract declares is_fresh as an async method

  # covers: memagent.interfaces.PageFetcher.fetch
  Scenario: A page fetcher returns cleaned documents for fetchable URLs
    Given an httpx page fetcher and two stubbed HTML pages
    When it fetches both URLs
    Then it returns one cleaned document per fetchable page
    And each document is marked ok with extracted markdown and a title
    And the PageFetcher contract declares fetch as an async method

  # covers: memagent.interfaces.TurnLogger.log
  Scenario: The turn logger appends exactly one JSON line per record
    Given a turn logger writing to a temporary log file
    When two turn records are logged
    Then exactly two JSON lines are appended
    And each line round-trips to the record that was logged
    And the TurnLogger contract declares log as a synchronous method
