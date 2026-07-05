"""to_markdown gating invariants (M3-owned OPTIONAL unit tests; keyless, no network).

trafilatura.extract is monkeypatched throughout — these tests pin OUR gating logic
(kwargs, recall retry, 200-char floor, 20k cap), not trafilatura's extraction quality.
"""

import pytest

import memagent.web.to_markdown as tm

PRECISION_KWARGS = {
    "output_format": "markdown",
    "include_tables": True,
    "include_links": False,
    "favor_precision": True,
}


def test_precision_pass_uses_exact_kwargs(monkeypatch):
    calls: list[dict] = []

    def fake_extract(html, **kwargs):
        calls.append(kwargs)
        return "x" * 500

    monkeypatch.setattr(tm.trafilatura, "extract", fake_extract)
    assert tm.to_markdown("<html></html>") == "x" * 500
    assert calls == [PRECISION_KWARGS]


def test_empty_precision_retries_once_with_recall(monkeypatch):
    calls: list[dict] = []

    def fake_extract(html, **kwargs):
        calls.append(kwargs)
        return None if kwargs.get("favor_precision") else "y" * 500

    monkeypatch.setattr(tm.trafilatura, "extract", fake_extract)
    assert tm.to_markdown("<html></html>") == "y" * 500
    assert len(calls) == 2
    assert calls[1]["favor_recall"] is True
    assert "favor_precision" not in calls[1]


def test_both_passes_empty_returns_none(monkeypatch):
    monkeypatch.setattr(tm.trafilatura, "extract", lambda html, **kw: None)
    assert tm.to_markdown("<html></html>") is None


@pytest.mark.parametrize(
    ("length", "expected_len"),
    [(199, None), (200, 200), (20_000, 20_000), (25_000, 20_000)],
)
def test_floor_and_cap(monkeypatch, length, expected_len):
    monkeypatch.setattr(tm.trafilatura, "extract", lambda html, **kw: "z" * length)
    result = tm.to_markdown("<html></html>")
    if expected_len is None:
        assert result is None
    else:
        assert result is not None and len(result) == expected_len


def test_constants_are_the_documented_values():
    assert tm.MIN_MARKDOWN_CHARS == 200
    assert tm.MAX_MARKDOWN_CHARS == 20_000
