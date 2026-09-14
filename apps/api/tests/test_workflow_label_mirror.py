"""The frontend's copy of the workflow labels matches this module's.

``apps/web/src/lib/workflowSteps.ts`` holds a SECOND COPY of
:data:`isaac_api.workflow.CANONICAL_LABELS`. The mirror is deliberate — its own
note explains that it exists so a screen NAME can be the step's name rather than a
third string authored beside it — but nothing checked it, and on 2026-09-14 it
drifted: ``load_record`` was relabelled ``Load Record`` -> ``Record Created`` here
(the step links to the ``fields`` workspace, so a STEP and a PLACE had
near-identical names for one page, which the project owner reported as *"'record
fields' is the same as 'load record'"*), the mirror was not updated in the same
edit, and **four unrelated statistics-chart assertions** in the frontend were the
only thing that noticed.

WHY THIS TEST IS IN PYTHON AND READS TYPESCRIPT. The drift is across a language
boundary, so neither suite can see both sides by importing. The frontend half
(`workflow-steps-mirror.test.ts`) proves the two CLIENT copies agree; this half
proves the client agrees with the SERVER, which is the direction that matters
because this module is the source. Parsing TypeScript from a Python test is an
established pattern in this repository — `connect-your-agent.test.tsx` parses
`mcp/tools.py` for the same reason, in the same spirit, in the other direction.

It is a PARSE, not an import, so it is deliberately strict about shape: if the
literal's formatting changes enough that the regex stops matching, the test FAILS
on a vacuity guard rather than silently passing over nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from isaac_api.workflow import CANONICAL_LABELS, CANONICAL_ORDER

MIRROR = (
    Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "lib" / "workflowSteps.ts"
)

#: `{ id: 'load_record', label: 'Record Created' },` — tolerant of whitespace and
#: of either quote style, strict about the two keys being on one entry.
_ENTRY = re.compile(
    r"\{\s*id:\s*['\"](?P<id>[a-z_]+)['\"]\s*,\s*label:\s*['\"](?P<label>[^'\"]+)['\"]\s*,?\s*\}"
)


def _mirror_entries() -> list[tuple[str, str]]:
    if not MIRROR.exists():  # pragma: no cover - the path is committed
        pytest.skip(f"frontend mirror not present at {MIRROR}")
    # Read as bytes-ish so a NUL-bearing file cannot hide a hit; see CLAUDE.md §11.
    source = MIRROR.read_text(encoding="latin-1")
    # Only the CANONICAL_STEPS literal, so an example in a comment cannot contribute.
    start = source.index("export const CANONICAL_STEPS")
    end = source.index("] as const;", start)
    body = source[start:end]
    # Comments inside the literal may legitimately quote a retired label; strip them.
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"(?m)//.*$", "", body)
    return [(m.group("id"), m.group("label")) for m in _ENTRY.finditer(body)]


def test_the_mirror_is_parseable_and_not_vacuous() -> None:
    entries = _mirror_entries()
    assert len(entries) == len(CANONICAL_ORDER), (
        f"parsed {len(entries)} entries from {MIRROR.name} but this module declares "
        f"{len(CANONICAL_ORDER)}. Either the mirror changed shape (fix the regex, do "
        f"not delete the test) or a step was added on one side only."
    )


def test_the_mirror_has_the_same_ids_in_the_same_order() -> None:
    assert [e[0] for e in _mirror_entries()] == list(CANONICAL_ORDER)


def test_the_mirror_has_the_same_labels() -> None:
    for step_id, label in _mirror_entries():
        assert label == CANONICAL_LABELS[step_id], (
            f"{MIRROR.name} calls {step_id!r} {label!r}; this module calls it "
            f"{CANONICAL_LABELS[step_id]!r}. The server is the source — update the mirror."
        )


def test_the_retired_label_is_gone_from_both_sides() -> None:
    """Named explicitly, so the defect is legible without git history."""
    assert "Load Record" not in CANONICAL_LABELS.values()
    assert CANONICAL_LABELS["load_record"] == "Record Created"
    assert all(label != "Load Record" for _, label in _mirror_entries())
