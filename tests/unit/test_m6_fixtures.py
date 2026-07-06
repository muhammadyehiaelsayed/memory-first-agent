"""M6-owned keyless assertions for the conftest fixtures (FR-001..004).

The happy-path integration/e2e tests exercise the fixtures but never fire the retry path
(FR-001) or the disjoint-cosine case (FR-003), so these keyless unit assertions guard those
acceptance criteria. Keyless + dockerless; a NEW M6-owned file, distinct from the 12 frozen
upstream unit files (Ruling A).
"""

import asyncio
import math
import pathlib
import sys
import time

import httpx
import pytest
from openai import APIConnectionError

from memagent.analytics.classify import QueryClassification
from memagent.config import Settings
from memagent.utils.reliability import llm_retry

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # repo root on path
from tests.conftest import probe_redis_or_skip  # noqa: E402  (recheck H shim; tests/ not a package)

REQ = httpx.Request("POST", "https://api.openai.com/v1/x")


# ---- FR-001: WAIT_CAP_SCALE=0 drives the production retry path with zero backoff ----
def test_wait_cap_scale_zero_retries_full_budget_instantly(settings):
    assert settings.wait_cap_scale == 0
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] <= 3:
            raise APIConnectionError(request=REQ)
        return "ok"

    wrapped = llm_retry(settings)(flaky)
    start = time.perf_counter()
    assert asyncio.run(wrapped()) == "ok"
    elapsed = time.perf_counter() - start
    assert calls["n"] == 4  # full 4-attempt budget (3 transient failures + 1 success)
    assert elapsed < 0.05  # no real sleep — the wait cap collapsed to 0 (prod path)


# ---- FR-002: FakeLLM deterministic complete() + valid-schema parse() ----
def test_fake_llm_complete_deterministic_with_usage(fake_llm):
    a = asyncio.run(fake_llm.complete("sys", []))
    b = asyncio.run(fake_llm.complete("sys", []))
    assert a.text == b.text
    for r in (a, b):
        assert isinstance(r.usage["input_tokens"], int)
        assert isinstance(r.usage["output_tokens"], int)
        assert isinstance(r.usage["model"], str)


def test_fake_llm_parse_returns_valid_schema_instance(fake_llm_qc):
    obj, usage = asyncio.run(fake_llm_qc.parse("sys", "hello", QueryClassification))
    assert isinstance(obj, QueryClassification)
    assert isinstance(usage, dict) and usage["model"] == "fake"


# ---- FR-003: deterministic 1536-dim unit vectors; token overlap -> cosine ----
def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both L2-unit -> dot product == cosine


def test_fake_embedder_bit_stable_unit_1536(fake_embedder):
    v1 = asyncio.run(fake_embedder.embed(["redis vector search"]))[0]
    v2 = asyncio.run(fake_embedder.embed(["redis vector search"]))[0]
    assert v1 == v2
    assert len(v1) == 1536
    assert abs(math.sqrt(sum(x * x for x in v1)) - 1.0) < 1e-6


def test_fake_embedder_query_dominated_high_disjoint_low(fake_embedder):
    q = "how does redis vector search work"
    vq = asyncio.run(fake_embedder.embed([q]))[0]
    vp = asyncio.run(fake_embedder.embed([(q + " ") * 3]))[0]  # query-dominated
    vd = asyncio.run(fake_embedder.embed(["completely unrelated banana orchestra"]))[0]
    assert _cos(vq, vp) >= 0.70  # repeated query -> same direction -> cosine ~ 1.0
    assert _cos(vq, vd) < 0.70  # disjoint token bags -> near-orthogonal


# ---- FR-004: redis_url skips (never errors) when Redis is unreachable ----
def test_probe_redis_or_skip_skips_on_dead_port():
    # Exercises the ACTUAL fixture helper (conftest.probe_redis_or_skip): an unreachable Redis
    # must raise Skipped (pytest.skip), so integration/e2e report `skipped`, never `error`.
    # (Previously a tautology that rebuilt the socket probe inline and never ran the fixture.)
    dead = Settings(_env_file=None, redis_url="redis://127.0.0.1:6390/0")  # dead port
    with pytest.raises(pytest.skip.Exception):
        probe_redis_or_skip(dead)
