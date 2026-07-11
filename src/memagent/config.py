"""Application settings — the single source of the project's tunable values and env names.

Every user-facing tunable is a field here (Constitution P-III); modules read from `Settings`
rather than inventing their own knobs. A few internal structural literals (the sanitizer's
regex sizes, the retry wait caps) stay at their use site. `.env.example` is generated from
this class by `scripts/gen_env_example.py` so the documented env cannot drift.

Keys are optional so keyless paths (tests, lint, wipe-memory) run; the readable fail-fast
check for OPENAI_API_KEY lives in build_openai_clients (llm/clients.py).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- keys (all optional so keyless test/lint/wipe run) ---
    openai_api_key: str = ""  # the ONE required key at runtime (LLMs + embeddings)
    openai_base_url: str | None = None  # optional -> GitHub Models free dev mode
    tavily_api_key: str = ""  # optional -> keyless ddgs fallback

    # --- models ---
    conversation_model: str = "gpt-5.4-mini"
    analytics_model: str = "gpt-5.4-nano"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # --- redis / memory ---
    redis_url: str = "redis://localhost:6379/0"
    memory_index_name: str = "web_memory"
    # Key prefixes for the indexed chunk docs and the non-indexed meta hashes. Overridable so
    # tests/evals can carve out a fully disjoint namespace (distinct index name AND prefix) on
    # the same Redis: RediSearch indexes are instance-global and refuse a second index over an
    # already-indexed prefix, so a distinct index name alone is not enough to avoid clobbering
    # the demo — the prefix must differ too.
    memory_chunk_prefix: str = "chunk"
    memory_meta_prefix: str = "doc"
    similarity_threshold: float = 0.7  # inclusive: hit <=> (1 - distance) >= this
    memory_top_k: int = 5
    memory_ttl_seconds: int = 604800  # 7 days; 0 disables
    freshness_window_seconds: int = 86400

    # --- web ---
    search_max_results: int = 8
    fetch_top_n: int = 5
    fetch_concurrency: int = 5
    connect_timeout_s: int = 5
    read_timeout_s: int = 10
    page_deadline_s: int = 20
    fetch_max_bytes: int = 2500000
    max_urls_per_domain: int = 2  # diversity cap in filter_urls
    min_markdown_chars: int = 200  # reject cookie-wall / JS-shell pages
    max_markdown_chars: int = 20000  # cap token cost on huge articles

    # --- llm timing / retries ---
    llm_timeout_s: int = 45
    llm_max_attempts: int = 4
    classify_timeout_s: int = 8

    # --- chunking / context ---
    chunk_size_chars: int = 1600
    chunk_overlap_chars: int = 200
    min_chunk_chars: int = 100  # drop fragments shorter than this after splitting
    max_chunks_per_page: int = 25
    summary_input_chars: int = 6000  # cap on the page text sent to the summary LLM
    web_context_chunks_per_page: int = 2
    history_max_turns: int = 6

    # --- reliability / guard / logging ---
    wait_cap_scale: float = 1.0  # tests set 0 -> instant retries via prod path
    guard_max_query_chars: int = 2000
    log_level: str = "INFO"
    turn_log_path: str = "logs/turns.jsonl"

    # --- observability (LangSmith tracing, opt-in; logs/turns.jsonl stays the source of truth) ---
    langsmith_tracing: bool = False  # true + api key -> one trace per turn (configure_tracing)
    langsmith_api_key: str = ""  # blank keeps tracing off -> the default posture is zero-egress
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "memory-first-web-agent"
