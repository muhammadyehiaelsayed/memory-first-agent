"""Executable binding for the eval/demo script feature files.

Self-contained and keyless. The three scripts under scripts/ are NOT an
installed package, so they are loaded by absolute path with
``importlib.util.spec_from_file_location`` (their own top-level ``sys.path``
shim makes ``tests.conftest`` importable). Each covered function is exercised
against real behaviour:

* pure helpers (``_banner``, ``_page_html``, ``_render``, ``_score``) run with
  fakes and their real output/return values are asserted;
* the real-key entrypoints (``_run_real``) are driven by monkeypatching the
  boundary they build (the Agent facade / the OpenAI client builder) so the
  real control flow runs without keys;
* ``eval_lifecycle._run_mock`` — the keyless CI hard gate — runs the REAL graph
  against the live redis:8.2 on this machine (skips if Redis is unreachable via
  the shared ``redis_url`` fixture), with respx handled inside the script;
* ``main`` is called for its real exit codes (2 with no key, 0 under --mock),
  and the lifecycle gate is additionally driven end-to-end as a subprocess.
"""

import asyncio
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # repo root on path so `tests.conftest` is importable

from pytest_bdd import given, scenarios, then, when  # noqa: E402

from memagent.app import TurnResult  # noqa: E402
from tests.conftest import FakeEmbedder, FakeLLM  # noqa: E402


def _load(mod_name: str, rel: str):
    path = REPO / rel
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


CAPTURE = _load("capture_demo_script", "scripts/capture_demo.py")
GROUNDING = _load("eval_grounding_script", "scripts/eval_grounding.py")
LIFECYCLE = _load("eval_lifecycle_script", "scripts/eval_lifecycle.py")

scenarios("features/scripts_capture_demo.feature")
scenarios("features/scripts_eval_grounding.feature")
scenarios("features/scripts_eval_lifecycle.feature")


# --------------------------------------------------------------------------- #
# shared fakes
# --------------------------------------------------------------------------- #
class _MissThenHitAgent:
    """Fake Agent facade: the same question misses on the first ask, hits on the
    second — the miss-then-hit contract the demo/lifecycle scripts verify."""

    def __init__(self, *args, **kwargs):
        self._seen: dict[str, int] = {}

    async def answer(self, query: str) -> TurnResult:
        n = self._seen.get(query, 0)
        self._seen[query] = n + 1
        if n == 0:
            return TurnResult(
                "memory_miss_web_search",
                "Answered from the web.",
                [{"url": "https://example.test/x", "title": "X", "origin": "web"}],
                None,
            )
        return TurnResult(
            "memory_hit",
            "Answered from memory.",
            [{"url": "https://example.test/x", "title": "X", "origin": "memory"}],
            0.95,
        )


def _passing_judge() -> FakeLLM:
    return FakeLLM(
        schema_factory=lambda schema: GROUNDING.GroundingVerdict(
            grounded=True, citations_valid=True, abstained_correctly=True
        )
    )


# --------------------------------------------------------------------------- #
# shared steps
# --------------------------------------------------------------------------- #
@given("no OpenAI API key is configured", target_fixture="ctx")
def _no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return {}


@given("no API key and no Redis are available", target_fixture="ctx")
def _no_key_no_redis(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return {}


@then("it exits with code 2")
def _exit_two(ctx):
    assert ctx["rc"] == 2


@then("it explains that a real OpenAI key is required")
def _explains_key(ctx):
    assert "OPENAI_API_KEY" in ctx["stderr"]


@then("it prints an aggregate scorecard")
def _prints_scorecard(ctx):
    assert "Aggregate over" in ctx["out"]


@then("it returns exit code 0")
def _returns_zero(ctx):
    assert ctx["rc"] == 0


# --------------------------------------------------------------------------- #
# capture_demo._banner
# --------------------------------------------------------------------------- #
@given("turn results for a memory hit, a web miss and a degraded turn", target_fixture="ctx")
def _banner_inputs():
    return {
        "hit": TurnResult("memory_hit", "a", [], 0.87),
        "miss": TurnResult("memory_miss_web_search", "a", [], None),
        "other": TurnResult("degraded_web", "a", [], None),
    }


@when("each result is rendered as a transcript banner")
def _render_banners(ctx):
    ctx["hit_b"] = CAPTURE._banner(ctx["hit"])
    ctx["miss_b"] = CAPTURE._banner(ctx["miss"])
    ctx["other_b"] = CAPTURE._banner(ctx["other"])


@then("the memory-hit banner shows the similarity score")
def _hit_banner(ctx):
    assert ctx["hit_b"] == "[MEMORY HIT sim=0.87]"


@then("the web-miss banner announces the web search")
def _miss_banner(ctx):
    assert ctx["miss_b"] == "[MEMORY MISS -> searching the web]"


@then("any other route is shown verbatim in brackets")
def _other_banner(ctx):
    assert ctx["other_b"] == "[degraded_web]"


# --------------------------------------------------------------------------- #
# capture_demo._capture
# --------------------------------------------------------------------------- #
@given("a stubbed Agent that misses then hits on the demo question", target_fixture="ctx")
def _stub_capture_agent(monkeypatch):
    monkeypatch.setattr(CAPTURE, "Agent", _MissThenHitAgent)
    return {}


@when("the demo session is captured to markdown")
def _do_capture(ctx):
    ctx["md"] = asyncio.run(CAPTURE._capture())


@then("the transcript records two turns")
def _two_turns(ctx):
    assert "## Turn 1" in ctx["md"]
    assert "## Turn 2" in ctx["md"]


@then("turn one is a memory miss with a web source")
def _turn_one(ctx):
    assert "[MEMORY MISS -> searching the web]" in ctx["md"]
    assert "(web)" in ctx["md"]


@then("turn two is a memory hit whose banner shows the similarity")
def _turn_two(ctx):
    assert "[MEMORY HIT sim=0.95]" in ctx["md"]
    assert "(memory)" in ctx["md"]


# --------------------------------------------------------------------------- #
# capture_demo.main
# --------------------------------------------------------------------------- #
@when("the capture-demo entrypoint runs")
def _run_capture_main(ctx, capsys):
    ctx["rc"] = CAPTURE.main()
    out = capsys.readouterr()
    ctx["stdout"], ctx["stderr"] = out.out, out.err


# --------------------------------------------------------------------------- #
# eval_grounding._score
# --------------------------------------------------------------------------- #
@given("a fake answerer and a fake grounding judge", target_fixture="ctx")
def _score_fakes():
    return {
        "answerer": FakeLLM(answer=f"Grounded in the context. Sources:\n- {GROUNDING.SRC}"),
        "judge": _passing_judge(),
    }


@when("the fixed grounding cases are scored")
def _do_score(ctx):
    ctx["rows"] = asyncio.run(GROUNDING._score(ctx["answerer"], ctx["judge"]))


@then("one verdict row is produced per fixed case")
def _rows_len(ctx):
    assert len(ctx["rows"]) == len(GROUNDING.CASES)


@then("the answerer and judge were each invoked once per case")
def _calls_per_case(ctx):
    n = len(GROUNDING.CASES)
    assert ctx["answerer"].complete_calls == n
    assert ctx["judge"].parse_calls == n


@then("every row carries a grounding verdict")
def _rows_verdict(ctx):
    for question, expect, verdict in ctx["rows"]:
        assert isinstance(question, str)
        assert expect in {"grounded", "abstain"}
        assert isinstance(verdict, GROUNDING.GroundingVerdict)


# --------------------------------------------------------------------------- #
# eval_grounding._render
# --------------------------------------------------------------------------- #
@given("a set of scored grounding verdicts", target_fixture="ctx")
def _render_rows():
    verdict = GROUNDING.GroundingVerdict(
        grounded=True, citations_valid=True, abstained_correctly=True
    )
    rows = [(question, expect, verdict) for question, _c, expect in GROUNDING.CASES]
    return {"rows": rows}


@when("the scorecard is rendered")
def _do_render(ctx, capsys):
    GROUNDING._render(ctx["rows"])
    ctx["out"] = capsys.readouterr().out


@then("a row is printed for each scored case")
def _rows_printed(ctx):
    for question, _expect, _verdict in ctx["rows"]:
        assert repr(question) in ctx["out"]


@then("an aggregate over all three dimensions is printed")
def _aggregate_printed(ctx):
    assert f"Aggregate over {len(ctx['rows'])} cases" in ctx["out"]
    assert "grounded" in ctx["out"]
    assert "citations_valid" in ctx["out"]
    assert "abstained_correctly" in ctx["out"]


@then("the output states it is a demonstration, not a benchmark")
def _disclaimer(ctx):
    assert "DEMONSTRATION" in ctx["out"]
    assert "not a benchmark" in ctx["out"]


# --------------------------------------------------------------------------- #
# eval_grounding._run_mock
# --------------------------------------------------------------------------- #
@when("the grounding mock run executes")
def _do_run_mock_grounding(ctx, capsys):
    ctx["rc"] = asyncio.run(GROUNDING._run_mock())
    ctx["out"] = capsys.readouterr().out


# --------------------------------------------------------------------------- #
# eval_grounding._run_real
# --------------------------------------------------------------------------- #
@given("the OpenAI client builder is stubbed with fakes", target_fixture="ctx")
def _stub_grounding_clients(monkeypatch):
    import memagent.llm.clients as clients_mod

    def _fake_build(settings):
        answerer = FakeLLM(answer=f"Grounded in the context. Sources:\n- {GROUNDING.SRC}")
        return answerer, _passing_judge(), FakeEmbedder(settings.embedding_dim)

    monkeypatch.setattr(clients_mod, "build_openai_clients", _fake_build)
    return {}


@when("the grounding real run executes")
def _do_run_real_grounding(ctx, capsys):
    ctx["rc"] = asyncio.run(GROUNDING._run_real())
    ctx["out"] = capsys.readouterr().out


# --------------------------------------------------------------------------- #
# eval_grounding.main
# --------------------------------------------------------------------------- #
@when("the grounding entrypoint runs with the mock flag")
def _run_grounding_main_mock(ctx, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["eval_grounding.py", "--mock"])
    ctx["rc"] = GROUNDING.main()
    ctx["out"] = capsys.readouterr().out


@when("the grounding entrypoint runs without arguments")
def _run_grounding_main_nokey(ctx, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["eval_grounding.py"])
    ctx["rc"] = GROUNDING.main()
    out = capsys.readouterr()
    ctx["stdout"], ctx["stderr"] = out.out, out.err


# --------------------------------------------------------------------------- #
# eval_lifecycle._page_html
# --------------------------------------------------------------------------- #
@given("a lifecycle question", target_fixture="ctx")
def _lifecycle_question():
    return {"q": "How does Redis vector search work?"}


@when("the mock page HTML is generated for it")
def _gen_html(ctx):
    ctx["html"] = LIFECYCLE._page_html(ctx["q"])


@then("the HTML is a full document with a block-level article")
def _full_doc(ctx):
    html = ctx["html"]
    assert html.startswith("<html>")
    assert "<article>" in html
    assert html.rstrip().endswith("</html>")


@then("the question text is repeated many times so it dominates the extracted content")
def _repeated(ctx):
    assert ctx["html"].count(ctx["q"]) >= 40
    assert len(ctx["html"]) > 200


# --------------------------------------------------------------------------- #
# eval_lifecycle._run_mock  (real graph against live redis:8.2)
# --------------------------------------------------------------------------- #
@given("a live redis:8.2 is reachable", target_fixture="ctx")
def _redis_reachable(redis_url):
    return {"redis_url": redis_url}


@when("the lifecycle mock gate runs against real Redis with mocked search and fetch")
def _do_run_mock_lifecycle(ctx, capsys):
    ctx["rc"] = asyncio.run(LIFECYCLE._run_mock())
    ctx["out"] = capsys.readouterr().out


@then("the gate reports every question passed")
def _gate_reports_pass(ctx):
    assert "PASS: all" in ctx["out"]
    for question, _url in LIFECYCLE.QUESTIONS:
        assert f"[PASS] {question!r}" in ctx["out"]


# --------------------------------------------------------------------------- #
# eval_lifecycle._run_real
# --------------------------------------------------------------------------- #
@given("the Agent facade is stubbed to miss then hit on each question", target_fixture="ctx")
def _stub_lifecycle_agent(monkeypatch):
    import memagent.app as app_mod

    monkeypatch.setattr(app_mod, "Agent", _MissThenHitAgent)
    return {}


@when("the lifecycle real run executes")
def _do_run_real_lifecycle(ctx, capsys):
    ctx["rc"] = asyncio.run(LIFECYCLE._run_real())
    ctx["out"] = capsys.readouterr().out


@then("each question is reported as miss then hit")
def _each_miss_then_hit(ctx):
    out = ctx["out"]
    assert "FAIL" not in out
    for question, _url in LIFECYCLE.QUESTIONS:
        assert f"[PASS] {question!r}" in out
    assert "turn1=memory_miss_web_search" in out
    assert "turn2=memory_hit" in out


# --------------------------------------------------------------------------- #
# eval_lifecycle.main
# --------------------------------------------------------------------------- #
@when("the lifecycle script is executed as a subprocess with the mock flag")
def _subprocess_mock(ctx):
    ctx["proc"] = subprocess.run(
        [sys.executable, "scripts/eval_lifecycle.py", "--mock"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )


@then("the subprocess exits with status 0")
def _subproc_zero(ctx):
    proc = ctx["proc"]
    assert proc.returncode == 0, (proc.stdout, proc.stderr)


@then("the subprocess output reports all questions passed")
def _subproc_pass(ctx):
    assert "PASS: all" in ctx["proc"].stdout


@when("the lifecycle entrypoint runs without arguments")
def _run_lifecycle_main_nokey(ctx, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["eval_lifecycle.py"])
    ctx["rc"] = LIFECYCLE.main()
    out = capsys.readouterr()
    ctx["stdout"], ctx["stderr"] = out.out, out.err
