"""M1 smoke test — keeps CI's unit run green before M2 adds real tests.

Deliberately bounded: import + Settings defaults + schema shape ONLY.
Routing/similarity/chunker tests are M2-owned files; do not grow them here.
"""

from memagent.config import Settings
from memagent.memory.schema import build_schema


def test_package_imports() -> None:
    import memagent

    assert memagent.__version__


def test_settings_defaults() -> None:
    s = Settings()
    assert s.similarity_threshold == 0.7
    assert s.embedding_dim == 1536
    assert s.memory_index_name == "web_memory"


def test_schema_has_eleven_fields() -> None:
    schema = build_schema(Settings())
    assert len(schema.fields) == 11
