"""The committed validator QA package must keep saying what is actually true.

`qa/validator-upload-package/` ships eighteen record files that a human uploads
one at a time through the Standalone Validator, plus a `MANIFEST.json` that
states, per file, the verdict the official validator ACTUALLY produced when the
package was built. That manifest is a measurement, not an intention — so it can
go stale in three separate ways, and each of them matters:

  1. Someone edits a record file and its verdict changes. The guide a human is
     following would then be wrong about what they are about to see.
  2. The vendored schema is refreshed (`schema/PROVENANCE.md` documents the
     procedure) and a file that used to pass now fails, or vice versa.
  3. **A defect the package exists to demonstrate gets fixed.** Two files —
     `invalid-date-time.json` and `empty-measurement-series.json` — are recorded
     with `measured_matches_intent: false` precisely because they PASS when their
     names say they should not. Arming `format` enforcement would flip the first
     one. That is a WELCOME change, and this file is written so that it fails
     LOUDLY and tells the next reader to update the package and the guide, rather
     than leaving a human to be told "expect PASS" by a document that is no
     longer true.

So: this is a consistency test between a committed document and the deterministic
validator, not an assertion that the current behaviour is desirable.

WHAT THIS DOES NOT COVER. It re-measures `validate_official` only. It does NOT
exercise `POST /api/validate/record` (its 512 KB bound, its 422 on unparseable
input, or the client-side pre-checks in `RecordValidator.tsx` that mean two of the
files never produce an HTTP request at all) — those live with the API tests. It
also says nothing about what the UI renders.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_records.official import validate_official

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "qa" / "validator-upload-package"
MANIFEST = PACKAGE / "MANIFEST.json"


def _entries() -> list[dict]:
    data = json.loads(MANIFEST.read_text())
    # The manifest's own shape is asserted separately below; here we only need the
    # per-file list, whatever the surrounding key is called.
    for key in ("files", "fixtures", "entries"):
        if isinstance(data.get(key), list):
            return data[key]
    raise AssertionError(
        f"MANIFEST.json has no per-file list under 'files'/'fixtures'/'entries'; "
        f"top-level keys are {sorted(data)}"
    )


ENTRIES = _entries()
JSON_ENTRIES = [e for e in ENTRIES if str(e.get("filename", "")).endswith(".json")]


def test_the_package_directory_and_manifest_exist():
    assert PACKAGE.is_dir(), f"missing QA package directory: {PACKAGE}"
    assert MANIFEST.is_file(), f"missing manifest: {MANIFEST}"


def test_every_manifest_entry_names_a_file_that_exists():
    missing = [e["filename"] for e in ENTRIES if not (PACKAGE / e["filename"]).is_file()]
    assert not missing, (
        "MANIFEST.json describes files that are not in the package: "
        f"{missing}. Either the file was deleted or the manifest was not updated."
    )


def test_every_shipped_record_file_is_described_by_the_manifest():
    described = {e["filename"] for e in ENTRIES}
    # Documentation, the download archive and this package's README are not
    # fixtures and are deliberately not manifest entries.
    not_fixtures = {
        "MANIFEST.json",
        "UPLOAD-GUIDE.md",
        "ENGINEERING-NOTES.md",
        "README.md",
        "isaac-validator-qa-files.zip",
    }
    shipped = {p.name for p in PACKAGE.iterdir() if p.name not in not_fixtures}
    undescribed = sorted(shipped - described)
    assert not undescribed, (
        "these files are in the package but absent from MANIFEST.json, so a human "
        f"following UPLOAD-GUIDE.md has no stated expectation for them: {undescribed}"
    )


@pytest.mark.parametrize("entry", JSON_ENTRIES, ids=lambda e: e["filename"])
def test_the_manifest_records_the_verdict_the_validator_actually_produces(entry):
    """Re-measure. The manifest must agree with the deterministic validator."""
    path = PACKAGE / entry["filename"]
    raw = path.read_text()

    measured = entry["measured_validator_result"]
    expected_ok = measured["ok"]
    expected_count = measured.get("error_count")

    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        # Only the deliberately-malformed file may land here. Its manifest entry
        # must record that no verdict exists (`parsed: false`, `ok: null`) rather
        # than claiming one — a stated PASS/FAIL for a file the validator was
        # never invoked on would be a fabricated measurement.
        assert measured.get("parsed") is False, (
            f"{path.name} does not parse as JSON ({exc}), so its manifest entry "
            "must record parsed: false rather than a validator verdict"
        )
        assert expected_ok is None, (
            f"{path.name} does not parse as JSON, so no verdict can exist for it, "
            f"but its manifest entry claims ok={expected_ok!r}"
        )
        return

    assert measured.get("parsed") is True, (
        f"{path.name} parses as JSON, but its manifest entry records "
        f"parsed={measured.get('parsed')!r}"
    )
    report = validate_official(record, ROOT)

    assert report.ok is expected_ok, (
        f"{path.name}: MANIFEST.json says ok={expected_ok}, the validator says "
        f"ok={report.ok}.\n"
        "If the validator changed for a GOOD reason (e.g. `format` enforcement was "
        "armed, or the vendored schema was refreshed), then this package and "
        "UPLOAD-GUIDE.md are now telling a human the wrong thing — update the "
        "manifest, the guide's row for this file, and the README's "
        "'expected to PASS' section together.\n"
        f"Validator output:\n{report.render()}"
    )

    if expected_count is not None:
        assert len(report.errors) == expected_count, (
            f"{path.name}: MANIFEST.json says error_count={expected_count}, "
            f"measured {len(report.errors)}.\n{report.render()}"
        )


def test_the_two_known_divergences_are_still_declared_as_divergences():
    """The package's diagnostic value depends on these being flagged, not hidden.

    Pinned by NAME rather than by counting flags, so that adding a third
    divergence does not fail this test while silently un-flagging one of these
    two would.
    """
    by_name = {e["filename"]: e for e in ENTRIES}
    for filename in ("invalid-date-time.json", "empty-measurement-series.json"):
        entry = by_name.get(filename)
        assert entry is not None, f"{filename} is missing from MANIFEST.json"
        assert entry.get("measured_matches_intent") is False, (
            f"{filename} is one of the two files whose whole purpose is that its "
            "measured verdict CONTRADICTS its name. Its manifest entry must keep "
            "measured_matches_intent: false. If the underlying defect was fixed, "
            "do not just flip this flag — rewrite the file's purpose, its guide "
            "row, and the README."
        )


def test_no_qa_record_carries_an_attribution_block():
    """No person or account may be named in a shipped fixture."""
    offenders = []
    for entry in JSON_ENTRIES:
        raw = (PACKAGE / entry["filename"]).read_text()
        if '"attribution"' in raw:
            offenders.append(entry["filename"])
    assert not offenders, (
        f"these QA records contain an `attribution` block: {offenders}. The block "
        "is optional in the schema and is omitted on purpose so that no person or "
        "account is named in a committed fixture."
    )


#: Vocabulary that must not appear in anything a NORMAL USER reads. The records
#: themselves and the user-facing guide are held to this; `ENGINEERING-NOTES.md`,
#: this test file and the README are engineering documents and are exempt — they
#: are required to call these files what they are.
_DEV_VOCABULARY = (
    "synthetic",
    "demo",
    "fixture",
    "mock",
    "fake",
    "dummy",
    "test data",
    "sample data",
    "seeded",
    "scenario",
)


def test_user_facing_package_content_uses_no_development_vocabulary():
    user_facing = [PACKAGE / e["filename"] for e in ENTRIES]
    user_facing.append(PACKAGE / "UPLOAD-GUIDE.md")
    hits: list[str] = []
    for path in user_facing:
        lowered = path.read_text().lower()
        for word in _DEV_VOCABULARY:
            if word in lowered:
                hits.append(f"{path.name}: {word!r}")
    assert not hits, (
        "development vocabulary reached content a normal user reads — the record "
        "files and UPLOAD-GUIDE.md must use product language. "
        f"Hits: {hits}. (ENGINEERING-NOTES.md and README.md are deliberately "
        "exempt and must stay truthful.)"
    )
