"""`REAL_CONTRACT_DESCRIPTIONS` must not silently lag the generated OpenAPI spec.

`apps/web/src/test/apiFixtures.ts` exports `REAL_CONTRACT_DESCRIPTIONS`, a
hand-transcribed copy of every operation `description` in the app's OpenAPI
document. The frontend suite uses it to assert that the Endpoint Explorer renders
REAL contract prose rather than invented copy — so the assertions are only as
honest as the copy.

It had no parity check, and its own comment in `settings-api.test.tsx` says so:
"a point-in-time copy". That gap bit twice in one session. Two separate slices
edited operation descriptions in `routes.py`, and in both cases nothing failed:
the frontend suite cannot generate the spec (it would have to import Python), and
the backend suite never read the TypeScript file. The drift was found each time by
a human reviewer noticing, which is not a control.

This test closes it from the side that CAN see both: Python generates the real
spec and reads the `.ts` file as text.

WHAT THIS DOES NOT DO. It does not parse TypeScript — it regex-extracts the
`{ op, description }` object literals, so it depends on that array staying a flat
list of double-quoted literals. If the shape changes, `test_the_array_is_parseable`
fails loudly rather than silently matching nothing, which is the failure mode that
matters. It also says nothing about whether a description is *good*, only that the
copy matches what the server actually serves.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_TS = REPO_ROOT / "apps" / "web" / "src" / "test" / "apiFixtures.ts"

#: One `{ op: "METHOD /path", description: "…" }` literal.
_ENTRY_RE = re.compile(
    r'\{\s*op:\s*"([^"]+)",\s*description:\s*"((?:[^"\\]|\\.)*)"\s*\}'
)


def _unescape(raw: str) -> str:
    # Order matters: the backslash rule must come last or it would double-process
    # the escapes the earlier rules introduce.
    return (
        raw.replace("\\n", "\n")
        .replace('\\"', '"')
        .replace("\\'", "'")
        .replace("\\\\", "\\")
    )


def _entries() -> list[tuple[str, str]]:
    src = FIXTURES_TS.read_text()
    start = src.index("REAL_CONTRACT_DESCRIPTIONS")
    end = src.index("\n];", start)
    return [(op, _unescape(desc)) for op, desc in _ENTRY_RE.findall(src[start:end])]


@pytest.fixture(scope="module")
def spec() -> dict:
    from isaac_api.app import create_app

    return create_app().openapi()


def test_the_array_is_parseable():
    """Guards the regex, so a shape change cannot make the parity check vacuous."""
    assert FIXTURES_TS.is_file(), f"missing {FIXTURES_TS}"
    entries = _entries()
    assert len(entries) >= 30, (
        f"only {len(entries)} REAL_CONTRACT_DESCRIPTIONS entries parsed out of "
        "apiFixtures.ts. The array's shape probably changed, which would make the "
        "parity assertion below match nothing and pass for the wrong reason. Fix "
        "`_ENTRY_RE` rather than deleting this test."
    )


def test_every_transcribed_description_matches_the_generated_spec(spec):
    entries = _entries()
    problems: list[str] = []
    for op, transcribed in entries:
        method, path = op.split(" ", 1)
        operation = (spec["paths"].get(path) or {}).get(method.lower())
        if operation is None:
            problems.append(f"{op}: named in apiFixtures.ts but absent from the spec")
            continue
        served = (operation.get("description") or "").strip()
        if served != transcribed.strip():
            problems.append(
                f"{op}: the transcribed copy differs from what the server serves.\n"
                f"    served:      {served[:160]!r}…\n"
                f"    transcribed: {transcribed.strip()[:160]!r}…"
            )
    assert not problems, (
        "REAL_CONTRACT_DESCRIPTIONS has drifted from the generated OpenAPI "
        "document. The frontend asserts the Endpoint Explorer renders REAL "
        "contract prose using this copy, so a stale entry makes those assertions "
        "test invented text.\n\nRe-transcribe the affected entries from "
        "`create_app().openapi()` — do not edit the served description to match "
        "the copy.\n\n" + "\n".join(problems)
    )


def test_every_documented_operation_is_transcribed(spec):
    """The other direction: a NEW documented operation must be added to the copy.

    Without this, adding an endpoint would leave the Endpoint Explorer's coverage
    assertions silently narrower than the API.
    """
    transcribed = {op for op, _ in _entries()}
    served = {
        f"{method.upper()} {path}"
        for path, methods in spec["paths"].items()
        for method, operation in methods.items()
        if isinstance(operation, dict) and operation.get("description")
    }
    missing = sorted(served - transcribed)
    assert not missing, (
        "these operations carry a description in the served OpenAPI document but "
        "are absent from REAL_CONTRACT_DESCRIPTIONS in apiFixtures.ts, so the "
        f"Endpoint Explorer assertions do not cover them: {missing}"
    )


def test_no_operation_is_transcribed_twice(spec):
    """The direction BOTH parity checks above are structurally blind to.

    `test_every_transcribed_description_matches_the_generated_spec` iterates the
    ENTRIES and looks each one up in the spec, so a duplicated row simply matches
    twice and passes. `test_every_documented_operation_is_transcribed` compares
    SETS, so a duplicate collapses before the comparison. A merge resolved by
    "keep both sides" therefore put `GET /api/runtime/verification` and
    `GET /api/health` in the array twice each — 42 entries describing 40
    operations — and every check in this file stayed green.

    That is not a cosmetic problem: `settings-api.test.tsx` sums character and
    paragraph totals over the array and pins them, so two whole descriptions were
    counted twice and the pinned numbers were then RAISED to match, each honestly
    measured from a corrupt input.

    The count is compared to the SERVED operation count rather than to a literal,
    so a new endpoint moves both sides together and this test never needs editing.
    """
    entries = _entries()
    ops = [op for op, _ in entries]
    duplicated = sorted({op for op in ops if ops.count(op) > 1})
    assert not duplicated, (
        "REAL_CONTRACT_DESCRIPTIONS lists these operations more than once, which "
        "double-counts their descriptions in the frontend's character and "
        f"paragraph totals: {duplicated}"
    )
    served = {
        f"{method.upper()} {path}"
        for path, methods in spec["paths"].items()
        for method, operation in methods.items()
        if isinstance(operation, dict) and operation.get("description")
    }
    assert len(entries) == len(served), (
        f"{len(entries)} transcribed entries for {len(served)} documented "
        "operations"
    )
