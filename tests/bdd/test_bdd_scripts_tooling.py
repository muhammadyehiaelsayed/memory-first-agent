"""Executable binding for the scripts_tooling batch feature files.

Covers the four repo tooling scripts that are NOT an installed package:
  - scripts/gen_env_example.py  (the .env.example anti-drift generator)
  - scripts/render_graph.py     (the keyless mermaid architecture diagram)
  - scripts/verify_redisvl.py   (the redisvl signature verification duty)
  - scripts/seed_memory.py      (prime Redis so a memory hit is demoable)

scripts/ is not importable as a package, so each module is loaded by absolute
path via importlib.util.spec_from_file_location (module __name__ is not
"__main__", so the trailing `if __name__ == "__main__": main()` guards do NOT
fire at import). pytest-bdd generates SYNC tests; every coroutine is driven with
asyncio.run(...), and each Redis-touching step opens and closes its own client
inside a single asyncio.run so client + ops + aclose share one event loop.

Live-Redis scenarios use the keyless `settings` + `redis_url` skip-not-fail
fixtures from tests/conftest.py; every real network call to OpenAI is displaced
by monkeypatching the script's own `build_openai_clients` with a deterministic
fake embedder. render_graph/gen_env writes are redirected to tmp paths so no
pre-existing repo file is ever touched.
"""

import asyncio
import importlib.util
import pathlib
import sys

import redis.asyncio as aioredis
from pytest_bdd import given, scenarios, then, when

from memagent.config import Settings
from memagent.memory.schema import ensure_index, get_index
from memagent.memory.urls import url_hash

# ---------------------------------------------------------------------------
# Load the four standalone scripts by path (scripts/ is not a package).
# ---------------------------------------------------------------------------
REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"scripts.{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen_env = _load("gen_env_example")
render_graph = _load("render_graph")
verify_redisvl = _load("verify_redisvl")
seed_memory = _load("seed_memory")

scenarios("features/scripts_gen_env_example.feature")
scenarios("features/scripts_render_graph.feature")
scenarios("features/scripts_verify_redisvl.feature")
scenarios("features/scripts_seed_memory.feature")

_NODE_NAMES = [
    "guard_input",
    "embed_query",
    "memory_search",
    "answer_from_memory",
    "web_search",
    "fetch_pages",
    "ingest_content",
    "answer_from_web",
    "answer_failure",
    "log_turn",
]

_SEED_URL = "https://redis.io/docs/vector-search?utm_source=bdd"
_SEED_TEXT = (
    "# Redis vector search\n\n"
    "Redis stores dense embedding vectors alongside the source data and answers "
    "K-nearest-neighbour queries with the FLAT cosine index. A canonical URL and a "
    "content hash keep each stored chunk deduplicated so an identical follow-up question "
    "can be answered straight from memory without touching the web again."
)


# ===========================================================================
# scripts_gen_env_example.feature — render + main
# ===========================================================================
@given("the committed .env.example file", target_fixture="committed_env")
def committed_env():
    return (REPO / ".env.example").read_text(encoding="utf-8")


@when("the env template is rendered from Settings", target_fixture="rendered_env")
def render_template():
    return gen_env.render()


@then("the rendered text is byte-identical to the committed file")
def rendered_matches_committed(rendered_env, committed_env):
    assert rendered_env == committed_env


@then("every Settings field name appears uppercased as a KEY= line")
def every_field_is_a_key(rendered_env):
    lines = rendered_env.splitlines()
    for name in Settings.model_fields:
        key = f"{name.upper()}="
        assert any(line.startswith(key) for line in lines), f"missing key line for {key}"


@then("the secret-shaped fields emit safe placeholders instead of their raw defaults")
def secrets_are_blanked(rendered_env):
    assert "OPENAI_API_KEY=sk-..." in rendered_env
    # OPENAI_BASE_URL default is None / TAVILY_API_KEY is "" — never the literal "None".
    assert "OPENAI_BASE_URL=None" not in rendered_env
    assert "TAVILY_API_KEY=None" not in rendered_env


@given("the generator output is redirected to a temporary directory", target_fixture="env_out")
def redirect_env_output(tmp_path, monkeypatch):
    fake_script = pathlib.Path(str(tmp_path / "scripts" / "gen_env_example.py"))
    # main() computes: Path(__file__).resolve().parent.parent / ".env.example"
    monkeypatch.setattr(gen_env, "Path", lambda _arg: fake_script)
    return fake_script.resolve().parent.parent / ".env.example"


@when("the generator entry point runs", target_fixture="gen_main_out")
def run_gen_main(env_out, capsys):
    gen_env.main()
    return capsys.readouterr().out


@then("the redirected .env.example matches the rendered template")
def redirected_matches(env_out):
    assert env_out.exists()
    assert env_out.read_text(encoding="utf-8") == gen_env.render()


@then("the run reports how many settings it wrote")
def gen_reports_count(gen_main_out):
    assert "settings" in gen_main_out
    assert str(len(Settings.model_fields)) in gen_main_out


# ===========================================================================
# scripts_render_graph.feature — render_mermaid + splice + main
# ===========================================================================
@when("the agent graph is rendered to mermaid", target_fixture="mermaid")
def render_the_graph():
    return render_graph.render_mermaid()


@then("the mermaid text names every one of the ten pipeline nodes")
def mermaid_has_all_nodes(mermaid):
    missing = [n for n in _NODE_NAMES if n not in mermaid]
    assert not missing, f"mermaid diagram is missing nodes: {missing}"


@then("rendering it a second time produces byte-identical output")
def render_is_deterministic(mermaid):
    assert render_graph.render_mermaid() == mermaid


@given("a fresh markdown file that holds no diagram yet", target_fixture="doc_path")
def fresh_markdown_file(tmp_path):
    path = tmp_path / "README.md"
    assert not path.exists()
    return path


@when("the mermaid block is spliced into it twice", target_fixture="splice_texts")
def splice_twice(doc_path):
    diagram = "graph TD;\n  A[guard] --> B[answer]"
    render_graph.splice(doc_path, diagram, title="Architecture")
    first = doc_path.read_text(encoding="utf-8")
    render_graph.splice(doc_path, diagram, title="Architecture")
    second = doc_path.read_text(encoding="utf-8")
    return {"first": first, "second": second}


@then("the file holds exactly one fenced mermaid block between the stable markers")
def one_block_between_markers(splice_texts):
    text = splice_texts["first"]
    assert text.count(render_graph.BEGIN) == 1
    assert text.count(render_graph.END) == 1
    assert text.count("```mermaid") == 1
    assert text.index(render_graph.BEGIN) < text.index("```mermaid") < text.index(render_graph.END)


@then("the second splice leaves the file byte-identical to the first")
def splice_is_idempotent(splice_texts):
    assert splice_texts["second"] == splice_texts["first"]


@given("the working directory is an empty temporary project", target_fixture="proj_dir")
def empty_project_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@when("the render-graph entry point runs", target_fixture="render_main_out")
def run_render_main(proj_dir, capsys):
    render_graph.main()
    return capsys.readouterr().out


@then("the mermaid diagram is printed to standard output")
def diagram_printed(render_main_out):
    assert "graph TD" in render_main_out
    assert "guard_input" in render_main_out


@then("both README.md and docs/architecture.md contain the spliced mermaid block")
def docs_contain_block(proj_dir):
    readme = (proj_dir / "README.md").read_text(encoding="utf-8")
    arch = (proj_dir / "docs" / "architecture.md").read_text(encoding="utf-8")
    for text in (readme, arch):
        assert render_graph.BEGIN in text
        assert "```mermaid" in text
        assert "guard_input" in text


# ===========================================================================
# scripts_verify_redisvl.feature — check + has_* + main
# ===========================================================================
@given("a capability probe that reports the feature is present", target_fixture="probe_case")
def probe_present():
    return {"label": "demo-present", "fn": lambda: True}


@given("a capability probe that raises an exception", target_fixture="probe_case")
def probe_raises():
    def boom():
        raise RuntimeError("probe blew up")

    return {"label": "demo-broken", "fn": boom}


@when("the verifier checks that probe", target_fixture="check_out")
def run_check(probe_case, capsys):
    result = verify_redisvl.check(probe_case["label"], probe_case["fn"])
    return {"result": result, "out": capsys.readouterr().out, "label": probe_case["label"]}


@then("the check returns a truthy result")
def check_truthy(check_out):
    assert check_out["result"] is True


@then("an OK line naming the probe is printed")
def check_prints_ok(check_out):
    assert "[OK]" in check_out["out"]
    assert check_out["label"] in check_out["out"]


@then("the check returns a falsy result without propagating the error")
def check_falsy(check_out):
    assert check_out["result"] is False


@then("an errored line naming the probe is printed")
def check_prints_error(check_out):
    assert "errored" in check_out["out"]
    assert check_out["label"] in check_out["out"]


@when("the loader TTL capability is probed", target_fixture="ttl_probe")
def probe_ttl():
    return verify_redisvl.has_load_ttl()


@then("the probe confirms the ttl keyword is accepted")
def ttl_accepted(ttl_probe):
    assert ttl_probe is True


@when("the array-to-buffer capability is probed", target_fixture="a2b_probe")
def probe_a2b():
    return verify_redisvl.has_array_to_buffer()


@then("the probe confirms the helper is importable")
def a2b_importable(a2b_probe):
    assert a2b_probe is True


@when("the vector-query capability is probed", target_fixture="vq_probe")
def probe_vq():
    return verify_redisvl.has_vector_query()


@then("the probe confirms the query object is importable")
def vq_importable(vq_probe):
    assert vq_probe is True


@when("the redisvl verification report is produced", target_fixture="verify_report")
def produce_report(capsys):
    verify_redisvl.main()
    return capsys.readouterr().out


@then("the report states the installed redisvl version")
def report_names_version(verify_report):
    assert "redisvl version:" in verify_report


@then("the report lists the load-ttl, array-to-buffer and VectorQuery probes")
def report_lists_probes(verify_report):
    assert "SearchIndex.load" in verify_report
    assert "array_to_buffer" in verify_report
    assert "VectorQuery" in verify_report


# ===========================================================================
# scripts_seed_memory.feature — seed + main (live Redis)
# ===========================================================================
@given("a running Redis with the web_memory index", target_fixture="live_redis")
def ensure_live_index(redis_url, settings):
    async def _ensure():
        client = aioredis.from_url(settings.redis_url)
        try:
            await ensure_index(get_index(settings, client))
        finally:
            await client.aclose()

    asyncio.run(_ensure())
    return settings.redis_url


@given(
    "the OpenAI client factory is replaced with a deterministic fake embedder",
    target_fixture="seed_embedder",
)
def patch_client_factory(monkeypatch, fake_embedder):
    monkeypatch.setattr(
        seed_memory,
        "build_openai_clients",
        lambda settings: (object(), object(), fake_embedder),
    )
    return fake_embedder


@when("a page of markdown is seeded under a source URL", target_fixture="seed_result")
def do_seed(live_redis, seed_embedder):
    n = asyncio.run(seed_memory.seed(_SEED_URL, _SEED_TEXT, "Redis Vectors"))
    return {"n": n, "url": _SEED_URL, "text": _SEED_TEXT}


@then("it stores one chunk id per produced chunk")
def stored_one_id_per_chunk(seed_result):
    expected = len(seed_memory.chunk_markdown(seed_result["text"]))
    assert expected >= 1
    assert seed_result["n"] == expected


@then("each stored chunk key is present in Redis under the page identity")
def keys_present_in_redis(seed_result, settings):
    h = url_hash(seed_result["url"])

    async def _check():
        client = aioredis.from_url(settings.redis_url)
        try:
            return [await client.exists(f"chunk:{h}:{i}") for i in range(seed_result["n"])]
        finally:
            await client.aclose()

    present = asyncio.run(_check())
    assert present and all(flag == 1 for flag in present)


@when("the seed entry point runs with an inline text argument", target_fixture="seed_main_out")
def run_seed_main(live_redis, seed_embedder, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["seed_memory.py", "--url", _SEED_URL, "--text", _SEED_TEXT, "--title", "Redis Vectors"],
    )
    seed_memory.main()
    return capsys.readouterr().out


@then("it reports how many chunks were seeded for the canonical URL")
def seed_main_reports(seed_main_out):
    assert "Seeded" in seed_main_out
    assert "chunk" in seed_main_out
    # canonicalize() drops utm_* -> the canonical URL (no query) is echoed
    assert "https://redis.io/docs/vector-search" in seed_main_out
    assert any(ch.isdigit() for ch in seed_main_out)
