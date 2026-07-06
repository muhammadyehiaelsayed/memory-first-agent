"""Typed dependency errors + the redis-down cause-chain probe (M5).

Clients raise these on retry exhaustion / fast-fail; pipeline nodes translate them into
designed degradation outcomes (memory_search -> redis_down, etc.). `redis_down_in_chain`
walks `__cause__` because redisvl wraps connection failures in `RedisSearchError` with the
real error nested (found in M3 manual testing) — the store's typed translation and the CLI
startup guard both need to recognise that wrapped shape.
"""

from redis import exceptions as redis_exceptions

# redis-py's ConnectionError/TimeoutError do NOT subclass the builtins.
REDIS_DOWN_ERRORS = (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError, OSError)


class LLMUnavailableError(Exception):
    """OpenAI chat/embed unreachable after the retry policy (or a fast-fail 4xx)."""


class SearchUnavailableError(Exception):
    """Both web-search providers failed / the primary exhausted its retries."""


class PageFetchError(Exception):
    """A single page could not be fetched (per-URL, non-fatal to the turn)."""


class MemoryUnavailableError(Exception):
    """Redis exhausted its native retries (connection / timeout)."""


def redis_down_in_chain(exc: BaseException) -> bool:
    """True if exc or any `__cause__` link is a redis connection/timeout/OS error.

    redisvl wraps connection failures in RedisSearchError with the real error in the
    cause chain (M3 finding), so a plain isinstance check on the top exception misses the
    most common outage shape.
    """
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, REDIS_DOWN_ERRORS):
            return True
        cause = cause.__cause__
    return False
