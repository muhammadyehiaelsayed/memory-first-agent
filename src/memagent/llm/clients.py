"""Thin AsyncOpenAI wrappers (Ruling D seam — one call-site per client).

max_retries=0 is mandatory: tenacity (M5) is the single retry owner. M4 finalizes
constructors to shared-client signatures via build_openai_clients(); the embed()/
complete() interfaces are stable. base_url supports the GitHub Models free-dev mode.
"""

from openai import AsyncOpenAI
from pydantic import BaseModel

from memagent.config import Settings
from memagent.interfaces import CompletionResult


def _client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        max_retries=0,
        timeout=float(settings.llm_timeout_s),
    )


class OpenAIEmbedder:
    def __init__(self, settings: Settings):
        self._client = _client(settings)
        self._model = settings.embedding_model
        self.dim = settings.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]


class OpenAIChatLLM:
    def __init__(self, settings: Settings, model: str):
        self._client = _client(settings)
        self._model = model

    async def complete(self, system: str, messages: list[dict]) -> CompletionResult:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=2048,
            temperature=0,
        )
        usage = {
            "model": self._model,
            "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
        }
        return CompletionResult(text=resp.choices[0].message.content or "", usage=usage)

    async def parse(self, system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel, dict]:
        # Basic structured-output call — M4 finalizes (max_tokens=256, usage plumbing, retries).
        resp = await self._client.chat.completions.parse(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=schema,
        )
        usage = {
            "model": self._model,
            "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
        }
        return resp.choices[0].message.parsed, usage
