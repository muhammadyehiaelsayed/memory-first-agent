"""Single-owner retry policies (M5, PLAN §9). Applied ONLY in client wrappers, never nodes.

Factories over Settings so tests drive the production path with WAIT_CAP_SCALE=0 (no
monkeypatched sleeps — the wait cap collapses to 0 while the attempt count and code path
are unchanged). Full jitter + before_sleep_log for free "retrying in 1.7s after 429"
observability. Typed-error translation lives here so nodes never see raw transport errors:
- llm_retry:    4 attempts, cap 20s; fast-fail 400/401/403/404/422; exhaustion+fast-fail → LLMUnavailableError
- tavily_retry: 3 attempts, cap 8s;  fast-fail 400/401/403 → RE-RAISE original (feeds the ddgs fallback); exhaustion → SearchUnavailableError
- fetch_retry:  2 attempts, cap 2s;  non-retryable status/exhaustion → PageFetchError (per-URL, non-fatal)
"""

import functools
import logging

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from memagent.config import Settings
from memagent.utils.errors import (
    LLMUnavailableError,
    PageFetchError,
    SearchUnavailableError,
)

# stdlib logger — routed to stderr by app.configure_logging's basicConfig.
logger = logging.getLogger("memagent.reliability")

_LLM_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
_LLM_FAST_FAIL_STATUS = {400, 401, 403, 404, 422}


def _max_wait(cap_s: float, settings: Settings) -> float:
    return cap_s * settings.wait_cap_scale


def _status(exc: BaseException) -> int | None:
    if isinstance(exc, APIStatusError):
        return exc.status_code
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


def _is_retryable_llm(exc: BaseException) -> bool:
    return isinstance(exc, _LLM_RETRYABLE)


def _is_retryable_tavily(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    status = _status(exc)
    return status is not None and (status == 429 or status >= 500)


def _is_retryable_fetch(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    return _status(exc) in (502, 503, 504)


def llm_retry(settings: Settings):
    wait = wait_random_exponential(multiplier=1, max=_max_wait(20.0, settings))

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            retryer = AsyncRetrying(
                stop=stop_after_attempt(settings.llm_max_attempts),
                wait=wait,
                retry=retry_if_exception(_is_retryable_llm),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=True,
            )
            try:
                return await retryer(fn, *args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — fast-fail (4xx) OR exhaustion → typed
                raise LLMUnavailableError(str(exc)) from exc

        return wrapper

    return decorator


def tavily_retry(settings: Settings):
    wait = wait_random_exponential(multiplier=1, max=_max_wait(8.0, settings))

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            retryer = AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait,
                retry=retry_if_exception(_is_retryable_tavily),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=True,
            )
            try:
                return await retryer(fn, *args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                if _is_retryable_tavily(exc):
                    raise SearchUnavailableError(str(exc)) from exc  # exhaustion
                raise  # 400/401/403 (or other) → original, so FallbackProvider hits ddgs

        return wrapper

    return decorator


def fetch_retry(settings: Settings):
    wait = wait_random_exponential(multiplier=1, max=_max_wait(2.0, settings))

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            retryer = AsyncRetrying(
                stop=stop_after_attempt(2),
                wait=wait,
                retry=retry_if_exception(_is_retryable_fetch),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=True,
            )
            try:
                return await retryer(fn, *args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — non-retryable status OR exhaustion → typed
                raise PageFetchError(str(exc)) from exc

        return wrapper

    return decorator
