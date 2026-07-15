# Contract: Fetch & Markdown — `web/fetch.py`, `web/to_markdown.py` + `nodes/fetch.py`

**FRs**: FR-006…FR-020 · **Consumers**: `ingest_content` (docs), M5 retry wrap +
`test_fetch_retry.py` (wiring guards), M3-owned optional `test_to_markdown.py`.

## `filter_urls(urls: list[str], settings: Settings) -> list[str]`

Order-preserving; drops (in this check order per URL):

1. Scheme not in `ALLOWED_SCHEMES = {"http", "https"}` (FR-006) — kills `ftp:`, `file:`,
   `javascript:`, `data:`.
2. SSRF guard (FR-007): host == `localhost` OR an IP literal (v4/v6, use `ipaddress`)
   that is private/loopback/link-local/reserved — kills `127.0.0.1`, `10.x`, `192.168.x`,
   `169.254.169.254`, `[::1]`. Hostname DNS resolution deferred to M5 (source §6.7 note).
3. `JS_ONLY_DENYLIST` registrable-domain match (FR-008): youtube.com, youtu.be, x.com,
   twitter.com, facebook.com, instagram.com, tiktok.com (subdomains included).
4. Max 2 URLs per registrable domain, first-seen wins (FR-009).

## HttpxPageFetcher (satisfies the `PageFetcher` Protocol)

```python
class HttpxPageFetcher:
    def __init__(self, settings: Settings) -> None: ...
    async def fetch(self, urls: list[str]) -> list[FetchedDoc]: ...
```

> The `PageFetcher` Protocol in `interfaces.py` is updated in T003 from the M2
> placeholder (`fetch(results: list[SearchResult])`) to this URL-list signature —
> pre-authorized placeholder replacement (research D4 companion note; analyze I1).

- Client: `httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(connect=5, read=10, ...),
  headers={"User-Agent": USER_AGENT})` — values from `Settings` (FR-010, FR-015).
- Per URL: `asyncio.wait_for(fetch_one(url), settings.page_deadline_s)` — deadline
  overrun ⇒ abandoned + skipped, others continue (FR-010/FR-016).
- Concurrency: `asyncio.Semaphore(settings.fetch_concurrency)` (FR-014).
- Streamed GET: abort at `settings.fetch_max_bytes` — oversize page SKIPPED, never
  truncated-and-kept (FR-011).
- Content-type gate before body read: only `ACCEPTED_CONTENT_TYPES` proceed (FR-012).
- `FetchedDoc.url = str(response.url)` — the FINAL post-redirect URL (FR-013).
- Title: `<title>` text if present, else the final URL.
- Extraction: `to_markdown(html)`; `None` ⇒ page skipped. Returned docs have
  `markdown` set, `summary=None`, `ok=True`; failed URLs are OMITTED (source §4 note).
- Any per-URL exception (timeout, status, transport, oversize, gate) ⇒ skip that URL
  (FR-016). NO retries (M5).

## `to_markdown(html: str) -> str | None` (verbatim from source §6.8)

```python
MIN_MARKDOWN_CHARS = 200
MAX_MARKDOWN_CHARS = 20_000

def to_markdown(html):
    md = trafilatura.extract(html, output_format="markdown", include_tables=True,
                             include_links=False, favor_precision=True)      # FR-017
    if not md:
        md = trafilatura.extract(html, ..., favor_recall=True)               # FR-018
    if not md or len(md) < MIN_MARKDOWN_CHARS:
        return None                                                          # FR-019
    return md[:MAX_MARKDOWN_CHARS]                                           # FR-020
```

trafilatura 2.1.0 kwargs runtime-verified 2026-07-05 (research D9). The optional M3-owned
`tests/unit/test_to_markdown.py` covers exactly: precision kwargs, recall retry, 199/200
floor, 25000→20000 cap (via monkeypatched `trafilatura.extract` — keyless, no network).

## `fetch_pages` node (`nodes/fetch.py`, factory `make_fetch_pages(resources)`)

- `urls = filter_urls([r["url"] for r in state["search_results"]], settings)`
- `docs = await resources.fetcher.fetch(urls[: settings.fetch_top_n])`
- Returns `{"fetched_docs": docs}` (+ latency; errors appended on caught failure with
  `fetched_docs=[]`). Never raises.

## Routing (M2-delivered, activates now)

```python
def route_after_fetch(s): return "ingest_content" if s["fetched_docs"] else "answer_from_web"
```

Empty `fetched_docs` skips ingest and goes straight to the snippets-only degraded answer.
