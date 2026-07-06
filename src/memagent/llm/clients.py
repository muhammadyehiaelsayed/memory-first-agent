"""Finalized AsyncOpenAI wrappers (M4, Ruling D — one call-site per surface).

ONE shared AsyncOpenAI transport serves all three clients (build_openai_clients);
max_retries=0 is mandatory because tenacity (M5) is the single retry owner, and every
network request flows through exactly one private seam per surface (_call/_parse_call)
so M5's @openai_retry decorates there without touching complete()/parse() bodies.
base_url supports the GitHub Models free-dev mode.
"""

from openai import AsyncOpenAI
from pydantic import BaseModel

from memagent.config import Settings
from memagent.interfaces import CompletionResult
from memagent.utils.reliability import llm_retry

CONVERSATION_MAX_TOKENS = 2048  # code constants, not env vars (PLAN section 6)
ANALYTICS_MAX_TOKENS = 256      # also caps M3's per-page summaries (5-8 sentences fit)


class OpenAIEmbedder:
    def __init__(self, client: AsyncOpenAI, model: str, dim: int, retrying=None):
        self._client = client
        self._model = model
        self.dim = dim
        if retrying is not None:  # M5: wrap the ONE network seam (Ruling D)
            self._embed_call = retrying(self._embed_call)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._embed_call(model=self._model, input=texts)
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    async def _embed_call(self, **kw):
        return await self._client.embeddings.create(**kw)


class OpenAIChatLLM:
    def __init__(
        self, client: AsyncOpenAI, model: str, max_tokens: int, temperature: float | None = 0.0,
        retrying=None,
    ):
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        if retrying is not None:  # M5: wrap the two network seams (Ruling D)
            self._call = retrying(self._call)
            self._parse_call = retrying(self._parse_call)

    def _usage(self, resp) -> dict:
        return {
            "model": self._model,
            "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
        }

    async def complete(self, system: str, messages: list[dict]) -> CompletionResult:
        resp = await self._call(
            model=self._model,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=self._max_tokens,
            **({"temperature": self._temperature} if self._temperature is not None else {}),
        )
        return CompletionResult(
            text=resp.choices[0].message.content or "", usage=self._usage(resp)
        )

    async def parse(self, system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel, dict]:
        resp = await self._parse_call(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=schema,
            max_tokens=self._max_tokens,
            **({"temperature": self._temperature} if self._temperature is not None else {}),
        )
        return resp.choices[0].message.parsed, self._usage(resp)

    # --- the one seam per surface (Ruling D): M5 adds @openai_retry HERE, nowhere else ---
    async def _call(self, **kw):
        return await self._client.chat.completions.create(**kw)

    async def _parse_call(self, **kw):
        return await self._client.chat.completions.parse(**kw)


def build_openai_clients(settings: Settings) -> tuple[OpenAIChatLLM, OpenAIChatLLM, OpenAIEmbedder]:
    """ONE shared transport -> (conversation, analytics, embedder)."""
    if not settings.openai_api_key:
        raise SystemExit(
            "OPENAI_API_KEY is not set — see .env.example (one key covers LLMs + embeddings)."
        )
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,  # None -> OpenAI default host
        max_retries=0,
        timeout=float(settings.llm_timeout_s),
    )
    retrying = llm_retry(settings)
    conversation = OpenAIChatLLM(
        client, settings.conversation_model, CONVERSATION_MAX_TOKENS, temperature=0.0,
        retrying=retrying,
    )
    # Analytics client is deliberately NOT wrapped (D3): classify.py owns its own
    # wait_for(8s) + stop_after_attempt(2); wrapping here would nest 2×4 retries and
    # break the M4 exactly-2-calls tests. Its failure already degrades to analytics=null.
    analytics = OpenAIChatLLM(
        client, settings.analytics_model, ANALYTICS_MAX_TOKENS, temperature=0.0
    )
    embedder = OpenAIEmbedder(
        client, settings.embedding_model, settings.embedding_dim, retrying=retrying
    )
    return conversation, analytics, embedder
