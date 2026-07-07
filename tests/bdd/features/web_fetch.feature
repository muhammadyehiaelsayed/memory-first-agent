# Module: src/memagent/web/fetch.py
# Derived from: 00_main_functionality.feature :: "Fall back to the web and ingest what was found on a memory miss"
# Spec sources: milestone-3-web-pipeline.md
# Executable binding: tests/bdd/test_bdd_web_fetch.py
Feature: Bounded, guarded page fetching for the web branch (src/memagent/web/fetch.py)
  On a memory miss the agent searches the web and must fetch the winning pages
  safely. This module is the mini-SSRF/diversity URL filter plus the bounded,
  streamed, deadline-capped HttpxPageFetcher whose per-URL failures degrade to a
  skipped page rather than a crash. It feeds the root "memory_miss_web_search"
  flow and, when every fetch fails, the sibling "degraded_web" flow.

  # source: milestone-3-web-pipeline.md :: JS-only domains are denylisted (registrable-domain matching)
  # covers: memagent.web.fetch._registrable_domain
  Scenario: The registrable domain collapses to its last two labels
    Given hosts with sub-domains, mixed case and a bare single label
    When the registrable domain is computed for each host
    Then a multi-label host keeps only its last two labels
    And the result is lower-cased with any trailing dot removed
    And a single-label host is returned unchanged

  # source: milestone-3-web-pipeline.md :: Private, loopback and link-local targets are rejected
  # covers: memagent.web.fetch._is_private_host
  Scenario: Private, loopback and link-local hosts are recognised
    Given a mix of localhost, private, loopback, link-local and public hosts
    When each host is tested against the private-host guard
    Then localhost and the private, loopback and link-local IP literals are flagged private
    And a public IP and an unresolved hostname are not flagged

  # source: milestone-3-web-pipeline.md :: Only http and https schemes survive
  # covers: memagent.web.fetch.filter_urls
  Scenario: Unsafe schemes and private hosts are removed by the URL filter
    Given a list of candidate URLs mixing https, http, ftp, file, data and a private IP
    When the URLs are filtered for the fetch stage
    Then only the http and https public URLs survive
    And the ftp, file, data and private-host URLs are dropped

  # source: milestone-3-web-pipeline.md :: At most two URLs per domain, order preserved
  # covers: memagent.web.fetch.filter_urls
  Scenario: Denylisted domains are dropped and each domain is capped for diversity
    Given three URLs on one domain, a youtube.com URL and one URL on another domain
    When the URLs are filtered for the fetch stage
    Then the youtube.com URL is dropped
    And at most two URLs from the repeated domain survive in their original order
    And the other-domain URL survives

  # source: milestone-3-web-pipeline.md :: Redirects are followed and the final URL is stored (title handling)
  # covers: memagent.web.fetch._extract_title
  Scenario: The page title is extracted, unescaped, whitespace-collapsed and bounded
    Given HTML whose title carries an entity and collapsible whitespace
    When the title is extracted with a fallback identifier
    Then the entity is unescaped and the whitespace collapsed
    And a titleless document falls back to the provided identifier
    And an over-long title is truncated to 300 characters

  # source: milestone-3-web-pipeline.md :: Requests carry an honest User-Agent with the repo link
  # covers: memagent.web.fetch.HttpxPageFetcher.__init__
  Scenario: The fetcher handles redirects manually, with bounded concurrency and an honest User-Agent
    Given the default web settings
    When a page fetcher is constructed
    Then its httpx client does not auto-follow redirects and sends the memagent User-Agent carrying a URL
    And the concurrency semaphore is sized to FETCH_CONCURRENCY

  # covers: memagent.web.fetch._is_safe_fetch_target
  Scenario: The SSRF target check rejects private hosts and non-HTTP schemes but accepts public URLs
    Given a public https URL, a loopback URL, a link-local metadata URL and a file URL
    When each URL is tested against the SSRF fetch-target guard
    Then only the public https URL is judged safe to fetch
    And the loopback, metadata and file URLs are rejected

  # covers: memagent.web.fetch.HttpxPageFetcher._fetch_one
  Scenario: A page that redirects to a private address is not followed
    Given a URL that 302-redirects to a link-local metadata address
    When the page is fetched
    Then the page is skipped and yields no document

  # source: milestone-3-web-pipeline.md :: A single failing URL is skipped and the rest continue
  # covers: memagent.web.fetch.HttpxPageFetcher.fetch
  Scenario: One failing URL does not stop the others on a memory miss
    Given three fetchable URLs where the middle one returns 404
    When the fetcher fetches all three
    Then two FetchedDocs are returned for the healthy URLs
    And the failed URL contributes no document

  # source: milestone-3-web-pipeline.md :: Degrade gracefully when every page fetch fails
  # covers: memagent.web.fetch.HttpxPageFetcher.fetch
  Scenario: Every page failing yields an empty result set for the degraded path
    Given two URLs that both return 404
    When the fetcher fetches them
    Then no FetchedDocs are returned

  # source: milestone-3-web-pipeline.md :: A single failing URL is skipped and the rest continue
  # covers: memagent.web.fetch.HttpxPageFetcher._fetch_guarded
  Scenario: A per-URL failure is swallowed into a skipped page
    Given one URL that returns 404 and one healthy URL
    When each is fetched through the guarded per-URL path
    Then the failing URL yields None instead of raising
    And the healthy URL yields a FetchedDoc

  # source: milestone-3-web-pipeline.md :: Redirects are followed and the final URL is stored
  # covers: memagent.web.fetch.HttpxPageFetcher._fetch_one
  Scenario: A redirect chain stores the final resolved URL
    Given a URL that 301-redirects to a final page
    When the page is fetched
    Then the FetchedDoc records the final resolved URL

  # source: milestone-3-web-pipeline.md :: Page-fetch retry policy (M5) exercised through the prod path
  # covers: memagent.web.fetch.HttpxPageFetcher._fetch_one
  Scenario: A transient read timeout is retried and then the page succeeds
    Given a URL that times out once and then returns HTML
    When the page is fetched
    Then the transport is called twice
    And a usable FetchedDoc is produced

  # source: milestone-3-web-pipeline.md :: Body larger than the cap is skipped
  # covers: memagent.web.fetch.HttpxPageFetcher._fetch_one
  Scenario: An oversize body is abandoned rather than truncated
    Given a response body larger than FETCH_MAX_BYTES
    When the page is fetched
    Then the page is skipped and yields no document

  # source: milestone-3-web-pipeline.md :: Content-type gate accepts only text formats
  # covers: memagent.web.fetch.HttpxPageFetcher._fetch_one
  Scenario: A non-HTML content type is skipped
    Given a response whose content type is application/pdf
    When the page is fetched
    Then the page is skipped and yields no document

  # source: milestone-3-web-pipeline.md :: A hard 404 is not retried
  # covers: memagent.web.fetch.HttpxPageFetcher._fetch_one
  Scenario: A hard 404 raises a page-fetch error without retrying
    Given a URL that returns 404
    When the page is fetched
    Then a PageFetchError is raised
    And the transport is called exactly once
