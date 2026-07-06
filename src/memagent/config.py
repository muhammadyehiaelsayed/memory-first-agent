"""Application settings — THE single source of every tunable number and env name.

Every configurable value in the project is a field here (Constitution P-III); other
modules read from `Settings` and never define their own numbers. `.env.example` is
generated from this class by `scripts/gen_env_example.py` so docs cannot drift.

Keys are optional at this stage so keyless paths (tests, lint, wipe-memory) run;
the readable fail-fast check for OPENAI_API_KEY lands in M4's client construction.
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

    # --- llm timing / retries ---
    llm_timeout_s: int = 45
    llm_max_attempts: int = 4
    classify_timeout_s: int = 8

    # --- chunking / context ---
    chunk_size_chars: int = 1600
    chunk_overlap_chars: int = 200
    max_chunks_per_page: int = 25
    web_context_chunks_per_page: int = 2
    history_max_turns: int = 6

    # --- reliability / guard / logging ---
    wait_cap_scale: float = 1.0  # tests set 0 -> instant retries via prod path
    guard_max_query_chars: int = 2000
    log_level: str = "INFO"
    turn_log_path: str = "logs/turns.jsonl"
