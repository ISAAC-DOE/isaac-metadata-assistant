"""B-A17 — the reason string shipped a literal ``(s)`` placeholder to the reader.

``build_invalidation`` composed ``f"Updated {n} field(s); …"`` (a literal ``field(s)``), so a
scientist (or an agent reading the MCP result) was told "Updated 1 field(s); no downstream steps
reopened." — the placeholder verbatim. The
count is the ``changed_fields`` length, and the reason is rendered verbatim on the Complete
screen after an edit, so the placeholder reached a page.

``assistant_paths.count`` is the module the assistant already uses for exactly this, with its
own docstring promising that "no ``field(s)`` placeholder ever survives to rendered output".
The reason now goes through it.
"""

from __future__ import annotations

import pytest

from isaac_api import dependencies


class _Exp:
    """The two things ``build_invalidation`` reads off the post-mutation experiment."""

    rev = 4

    def export_units(self):
        return []


@pytest.fixture(autouse=True)
def _flat_derivations(monkeypatch):
    # The reason string is what is under test, not the workflow/artifact derivations.
    monkeypatch.setattr(dependencies, "_post_workflow", lambda *_a, **_k: {"ordered_steps": []})
    monkeypatch.setattr(dependencies, "artifact_state", lambda *_a, **_k: {"state": "none"})
    monkeypatch.setattr(dependencies, "_labels", lambda ids: "Export")


def _reason(monkeypatch, n: int, *, reopened: tuple = ()) -> str:
    monkeypatch.setattr(dependencies, "reopened_steps", lambda *_a, **_k: list(reopened))
    return dependencies.build_invalidation(
        changed=True,
        changed_fields=[f"field.{i}" for i in range(n)],
        pre_steps=[],
        post_exp=_Exp(),
    )["reason"]


@pytest.mark.parametrize(
    "n,expected",
    [
        (1, "Updated 1 field; no downstream steps reopened."),
        (2, "Updated 2 fields; no downstream steps reopened."),
        (5, "Updated 5 fields; no downstream steps reopened."),
    ],
)
def test_the_count_is_pluralized_deterministically(monkeypatch, n, expected):
    assert _reason(monkeypatch, n) == expected


def test_no_placeholder_survives_in_either_branch(monkeypatch):
    for n in (1, 3):
        for reopened in ((), ("export",)):
            assert "(s)" not in _reason(monkeypatch, n, reopened=reopened)


def test_the_reopened_branch_is_pluralized_too(monkeypatch):
    assert _reason(monkeypatch, 1, reopened=("export",)) == "Updated 1 field; reopened: Export."
    assert _reason(monkeypatch, 2, reopened=("export",)) == "Updated 2 fields; reopened: Export."
