# Module: src/memagent/web/search.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-3-web-pipeline.md (§6.6, FR-M3-01..FR-M3-04)
# Executable binding: tests/bdd/test_bdd_web_search.py
Feature: Web search with Tavily-first, keyless ddgs fallback (src/memagent/web/search.py)
  On a memory miss the agent must reach the web. This module is the search
  boundary: TavilySearcher issues a raw httpx POST (so respx can see it and so
  our own fetch+markdown pipeline does the extraction, not Tavily), DdgsSearcher
  is the keyless DuckDuckGo fallback, and FallbackProvider tries Tavily first
  then degrades to ddgs on quota/auth/transport failures — recording which
  provider served the turn. This is what makes the root "memory_miss_web_search"
  route produce results instead of crashing.

  # source: milestone-3-web-pipeline.md :: The Tavily searcher holds an httpx.AsyncClient
  # covers: memagent.web.search.TavilySearcher.__init__
  Scenario: The Tavily searcher owns a reusable httpx client with bearer auth
    Given a Tavily searcher constructed from the keyless test settings
    Then its HTTP client is a reusable httpx.AsyncClient
    And the client carries an "Authorization: Bearer <key>" header and the module never imports the tavily package

  # source: milestone-3-web-pipeline.md :: Tavily 429 then 429 then 200 succeeds after retries
  # covers: memagent.web.search.TavilySearcher._post
  Scenario: Transient rate limits are retried at the single POST call site
    Given a Tavily searcher constructed from the keyless test settings
    And the Tavily endpoint responds 429, then 429, then 200
    When the Tavily searcher posts the query directly
    Then the POST call site is invoked three times and yields a 200 response

  # source: milestone-3-web-pipeline.md :: Tavily returns eight results via a raw httpx POST
  # covers: memagent.web.search.TavilySearcher.search
  Scenario: A Tavily search returns ranked results and asks Tavily not to pre-extract content
    Given a Tavily searcher constructed from the keyless test settings
    And the Tavily endpoint returns three search results
    When the Tavily searcher searches for "redis vector search" with k of 3
    Then three ranked SearchResults are returned mapping the response content field to snippet
    And the POST body sets include_raw_content to false and max_results to 3

  # source: milestone-3-web-pipeline.md :: ddgs fallback runs off the event loop and is keyless
  # covers: memagent.web.search.DdgsSearcher.search
  # covers: memagent.web.search.DdgsSearcher.__init__
  Scenario: The keyless DuckDuckGo fallback maps result fields and ranks by order
    Given a stubbed ddgs backend returning two rows
    When the ddgs searcher searches without any API key
    Then two SearchResults come back mapping href to url and body to snippet, ranked by row order

  # covers: memagent.web.search.FallbackProvider.__init__
  Scenario: A freshly built fallback provider has not yet chosen a provider
    Given a fallback search provider built from settings
    Then it holds both a Tavily searcher and a keyless ddgs searcher
    And it has recorded no provider_used yet

  # source: milestone-3-web-pipeline.md :: FallbackProvider records tavily on success
  # covers: memagent.web.search.FallbackProvider.search
  Scenario: On a memory miss the provider searches Tavily first and records it
    Given the Tavily endpoint returns results successfully
    And a ddgs backend that must not be called
    When the fallback provider searches on a memory miss
    Then Tavily supplies the results and provider_used is "tavily"
    And the ddgs backend was never called

  # source: milestone-3-web-pipeline.md :: FallbackProvider switches to ddgs and records provider_used
  # covers: memagent.web.search.FallbackProvider.search
  Scenario: When Tavily rejects the key the provider degrades to the keyless fallback
    Given the Tavily endpoint rejects the request with HTTP 401
    And a ddgs backend that returns one result
    When the fallback provider searches on a memory miss
    Then ddgs supplies the results and provider_used is "ddgs"
    And Tavily was called exactly once without retrying the 401

  # covers: memagent.web.search.FallbackProvider.search
  Scenario: When every search provider fails the turn gets a typed unavailability error
    Given the Tavily endpoint rejects the request with HTTP 401
    And a ddgs backend that raises
    When the fallback provider searches on a memory miss
    Then a SearchUnavailableError is raised and provider_used is cleared
