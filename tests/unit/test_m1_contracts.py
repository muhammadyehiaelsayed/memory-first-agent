"""M1 contracts untested before M7.

- assert_index_dims (FR-M1-16): a wrong-dimension embedder must raise with the wipe-memory
  recovery hint, not silently write into the 1536-dim index.
- .env.example anti-drift (FR-M1-08): render() must reproduce the committed file byte-for-byte
  and every Settings field must appear (spec §7 mandated these two @unit scenarios).
"""

import pathlib
import sys

import pytest

from memagent.config import Settings
from memagent.memory.schema import assert_index_dims

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))  # scripts/ is not an installed package (recheck H shim)
from scripts.gen_env_example import render  # noqa: E402

S = Settings(_env_file=None)


def test_assert_index_dims_passes_on_match():
    assert assert_index_dims(S.embedding_dim, S) is None  # 1536 == 1536: no raise


def test_assert_index_dims_raises_on_mismatch_with_recovery_hint():
    with pytest.raises(ValueError, match="wipe-memory"):
        assert_index_dims(3072, S)  # a 3072-dim embedder against the 1536 index


def test_env_example_is_a_regeneration_no_op():
    committed = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert render() == committed  # regenerating leaves `git diff .env.example` empty


def test_every_settings_field_appears_in_env_example():
    committed = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for name in Settings.model_fields:
        assert f"{name.upper()}=" in committed, name
