"""The frontend's canonical-seed fixtures must not lag `workspace.py`.

WHY THIS EXISTS, AND WHAT IT CAUGHT. `apps/web/src/test/apiFixtures.ts` describes
the five built-in example records for the whole frontend suite: their ids, the
shared title base every one of them carries, and the derived scenario labels the API
serves for them. All three are *backend* constants, restated in TypeScript.

Two of the three had silently drifted at `main`:

  * `RESET_TITLE_BASE` read ``'Synthetic XANES — CuO (Cu K-edge)'`` while
    ``workspace._SEED_TITLE_BASE`` had been renamed to
    ``'XANES Example — CuO (Cu K-edge)'``;
  * ``CANONICAL_SCENARIO_LABELS`` still carried the retired
    ``'Scenario N · seeded: …'`` wording, replaced in the backend by
    ``'Example N · at setup: …'``.

Nothing failed, in either suite, for the same structural reason the sibling
`test_contract_description_parity.py` was written for: the Vitest suite cannot
import Python, and no pytest test read the TypeScript. Every frontend assertion over
a scenario label was therefore asserting invented copy — including the ones whose
whole point is that the label is honest about *how* a fixture was materialised.

WHAT THIS DOES NOT DO. It does not parse TypeScript. It regex-extracts three
specific literals, and `test_the_fixture_literals_are_parseable` fails loudly if the
shape changes, rather than silently matching nothing — which is the failure mode that
matters for a parity check. It also says nothing about whether a label is *good*, only
that the copy matches what the backend actually derives.

DIRECTION IS DELIBERATE. The backend is the source of truth: when this fails, fix the
`.ts`. Editing `workspace.py` to match a stale fixture would rename a real record
title, and `_SEED_TITLE_BASE`'s own docstring records why that is a behaviour change
rather than a copy change.
"""

from __future__ import annotations

import re
from pathlib import Path

from isaac_api import workspace as ws

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_TS = REPO_ROOT / "apps" / "web" / "src" / "test" / "apiFixtures.ts"

#: `export const RESET_TITLE_BASE = '…';`
_TITLE_RE = re.compile(r"export const RESET_TITLE_BASE\s*=\s*'((?:[^'\\]|\\.)*)'")

#: `export const CANONICAL_RESET_IDS = [ '…', … ];`
_IDS_RE = re.compile(r"export const CANONICAL_RESET_IDS\s*=\s*\[(.*?)\]", re.DOTALL)

#: `export const CANONICAL_SCENARIO_LABELS = [ '…', … ];`
_LABELS_RE = re.compile(
    r"export const CANONICAL_SCENARIO_LABELS\s*=\s*\[(.*?)\]", re.DOTALL
)

_SINGLE_QUOTED = re.compile(r"'((?:[^'\\]|\\.)*)'")


def _source() -> str:
    return FIXTURES_TS.read_text()


def _title_base() -> str | None:
    m = _TITLE_RE.search(_source())
    return m.group(1) if m else None


def _array(pattern: re.Pattern[str]) -> list[str] | None:
    m = pattern.search(_source())
    if m is None:
        return None
    return _SINGLE_QUOTED.findall(m.group(1))


def test_the_fixture_literals_are_parseable():
    """Guards the three regexes, so the parity assertions cannot go vacuous."""
    assert FIXTURES_TS.is_file(), f"missing {FIXTURES_TS}"
    assert _title_base() is not None, (
        "RESET_TITLE_BASE could not be extracted from apiFixtures.ts. It must stay an "
        "exported single-quoted string literal, or the parity assertion below matches "
        "nothing and passes for the wrong reason. Fix `_TITLE_RE`, do not delete this."
    )
    ids = _array(_IDS_RE)
    labels = _array(_LABELS_RE)
    assert ids is not None and len(ids) == 5, f"expected 5 fixture ids, parsed {ids}"
    assert labels is not None and len(labels) == 5, (
        f"expected 5 fixture scenario labels, parsed {labels}"
    )


def test_the_fixture_title_base_matches_the_backend():
    assert _title_base() == ws._SEED_TITLE_BASE, (
        "apiFixtures.ts `RESET_TITLE_BASE` has drifted from "
        "`workspace._SEED_TITLE_BASE`.\n"
        f"    backend:  {ws._SEED_TITLE_BASE!r}\n"
        f"    fixture:  {_title_base()!r}\n"
        "Fix the fixture. Renaming the backend constant to match is a BEHAVIOUR change "
        "— see its docstring — not a way to make this pass."
    )


def test_the_fixture_ids_are_the_canonical_seed_ids_in_order():
    expected = [s.id for s in ws._seed_specs()]
    assert _array(_IDS_RE) == expected, (
        "apiFixtures.ts `CANONICAL_RESET_IDS` has drifted from the canonical seed ids.\n"
        f"    backend:  {expected}\n"
        f"    fixture:  {_array(_IDS_RE)}\n"
        "Order matters: the fixture indexes into this array by scenario number."
    )


def test_the_fixture_scenario_labels_match_the_backend_in_order():
    expected = [ws.SEED_SCENARIOS[s.id] for s in ws._seed_specs()]
    assert _array(_LABELS_RE) == expected, (
        "apiFixtures.ts `CANONICAL_SCENARIO_LABELS` has drifted from "
        "`workspace.SEED_SCENARIOS`.\n"
        f"    backend:  {expected}\n"
        f"    fixture:  {_array(_LABELS_RE)}\n"
        "Every frontend assertion over a scenario label reads this array, so a stale "
        "entry makes those assertions test invented copy."
    )


def test_the_derived_titles_the_fixture_builds_are_the_titles_the_backend_serves():
    """The whole point, end to end: the composed titles must agree.

    The fixture builds each summary title as ```${RESET_TITLE_BASE} · <suffix>```, and
    the backend builds it as ``f"{_SEED_TITLE_BASE} · <suffix>"``. The two previous
    tests pin the base and the labels; this one pins the *composition*, so a fixture
    that fixed the base but kept a hand-written suffix would still fail.
    """
    source = _source()
    for spec in ws._seed_specs():
        suffix = spec.title.split(" · ", 1)[1]
        composed = f"`${{RESET_TITLE_BASE}} · {suffix}`"
        assert composed in source, (
            f"apiFixtures.ts does not compose the title the backend serves for "
            f"{spec.id}.\n"
            f"    backend title: {spec.title!r}\n"
            f"    expected the fixture to contain: {composed}"
        )
