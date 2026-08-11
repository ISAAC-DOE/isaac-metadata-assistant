"""The committed validator QA package must keep saying what is actually true.

`qa/validator-upload-package/` ships eighteen record files that a human uploads
one at a time through the Standalone Validator, plus a `MANIFEST.json` that
states, per file, the verdict the official validator ACTUALLY produced when the
package was built. That manifest is a measurement, not an intention — so it can
go stale in several separate ways, and each of them matters:

  1. Someone edits a record file and its verdict changes. The guide a human is
     following would then be wrong about what they are about to see.
  2. The vendored schema is refreshed (`schema/PROVENANCE.md` documents the
     procedure) and a file that used to pass now fails, or vice versa. Note that
     a refresh can also leave `ok` and `error_count` untouched while changing the
     MESSAGE — extending an enum, say — which is why the first error's path and
     message are asserted too, not just the verdict.
  3. **A defect the package exists to demonstrate gets fixed.** Two files —
     `invalid-date-time.json` and `empty-measurement-series.json` — are recorded
     with `measured_matches_intent: false` precisely because they PASS when their
     names say they should not. Arming `format` enforcement would flip the first
     one. That is a WELCOME change, and this file is written so that it fails
     LOUDLY and names the documents to update, rather than leaving a human to be
     told "expect PASS" by a document that is no longer true.
  4. A record is edited so that it still fails ONCE but for a completely
     different reason, falsifying its `purpose` and `schema_paths_exercised`
     while `ok`/`error_count` hold.
  5. **The download archive drifts from the loose files.**
     `isaac-validator-qa-files.zip` is the delivery vehicle a human actually
     downloads. Re-measuring the loose files proves nothing about the archive, so
     the archive is compared byte-for-byte against them. Without this, the
     manifest's measured truth would apply to files the human never uploads.
  6. The guide's per-file rows drift from the manifest. Re-measuring the manifest
     and forgetting the eighteen guide rows is the likeliest staleness path, so
     the guide's quick-reference table is cross-checked.

So: this is a consistency test between committed documents, an archive, and the
deterministic validator. It is NOT an assertion that the current behaviour is
desirable.

WHAT THIS DOES NOT COVER. It re-measures `validate_official` only. It does NOT
exercise `POST /api/validate/record` (its 512 KB bound, its 422 on unparseable
input, or the client-side pre-checks in `RecordValidator.tsx` that mean two of the
files never produce an HTTP request at all) — those live with the API tests. It
says nothing about what the UI renders. And it checks only the guide's
quick-reference TABLE, not the prose of the eighteen per-file sections: the table
is the part that states a verdict in a machine-checkable shape.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest

from isaac_records.official import validate_official
from isaac_records.portal_warnings import portal_warnings

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "qa" / "validator-upload-package"
MANIFEST = PACKAGE / "MANIFEST.json"
ARCHIVE = PACKAGE / "isaac-validator-qa-files.zip"
GUIDE = PACKAGE / "UPLOAD-GUIDE.md"

#: Package files that are NOT fixtures and so carry no manifest entry.
_NOT_FIXTURES = frozenset(
    {
        "MANIFEST.json",
        "UPLOAD-GUIDE.md",
        "ENGINEERING-NOTES.md",
        "README.md",
        ARCHIVE.name,
    }
)

#: Package files exempt from the development-vocabulary rule.
#:
#: `ENGINEERING-NOTES.md` and `README.md` are engineering documents, required to
#: call these files what they are. `MANIFEST.json` is exempt for a DIFFERENT
#: reason and the distinction is deliberate rather than accidental: unlike those
#: two it ships inside the user's archive, but it is a machine-readable artifact
#: whose `provenance` block must name its public upstream sources truthfully.
#: Guarded by `test_the_vocabulary_exemption_set_is_exactly_what_we_intend`.
_VOCABULARY_EXEMPT = frozenset({"MANIFEST.json", "ENGINEERING-NOTES.md", "README.md"})


def _entries() -> list[dict]:
    """Per-file manifest entries, or `[]` if the manifest is missing/unreadable.

    Deliberately tolerant. An earlier version raised here, at MODULE level, which
    made `test_the_package_directory_and_manifest_exist` DEAD: deleting the
    manifest crashed collection with a bare `FileNotFoundError` instead of
    producing that test's clear message. Returning `[]` lets collection succeed so
    the existence tests can fire and say what is actually wrong.
    """
    try:
        data = json.loads(MANIFEST.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    for key in ("files", "fixtures", "entries"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


ENTRIES = _entries()
JSON_ENTRIES = [e for e in ENTRIES if str(e.get("filename", "")).endswith(".json")]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_the_package_directory_and_manifest_exist():
    assert PACKAGE.is_dir(), f"missing QA package directory: {PACKAGE}"
    assert MANIFEST.is_file(), f"missing manifest: {MANIFEST}"
    assert ENTRIES, (
        f"{MANIFEST} exists but yielded no per-file entries — it is unreadable, is "
        "not JSON, or has no list under 'files'/'fixtures'/'entries'. Every "
        "per-file test in this module is vacuous until that is fixed."
    )


def test_the_archive_and_guide_exist():
    assert ARCHIVE.is_file(), f"missing download archive: {ARCHIVE}"
    assert GUIDE.is_file(), f"missing user guide: {GUIDE}"


def test_every_manifest_entry_names_a_file_that_exists():
    missing = [e["filename"] for e in ENTRIES if not (PACKAGE / e["filename"]).is_file()]
    assert not missing, (
        "MANIFEST.json describes files that are not in the package: "
        f"{missing}. Either the file was deleted or the manifest was not updated."
    )


def test_every_shipped_record_file_is_described_by_the_manifest():
    described = {e["filename"] for e in ENTRIES}
    shipped = {p.name for p in PACKAGE.iterdir() if p.name not in _NOT_FIXTURES}
    undescribed = sorted(shipped - described)
    assert not undescribed, (
        "these files are in the package but absent from MANIFEST.json, so a human "
        f"following UPLOAD-GUIDE.md has no stated expectation for them: {undescribed}"
    )


# --- the archive the human actually downloads ---------------------------------


def test_the_archive_contents_are_byte_identical_to_the_loose_files():
    with zipfile.ZipFile(ARCHIVE) as zf:
        mismatched: list[str] = []
        for name in sorted(zf.namelist()):
            loose = PACKAGE / name
            if not loose.is_file():
                mismatched.append(f"{name}: in the archive but not in the package")
                continue
            zipped, on_disk = _sha256(zf.read(name)), _sha256(loose.read_bytes())
            if zipped != on_disk:
                mismatched.append(
                    f"{name}: archive sha256 {zipped[:12]}… != on-disk {on_disk[:12]}…"
                )
    assert not mismatched, (
        "isaac-validator-qa-files.zip does not match the files in the package:\n  "
        + "\n  ".join(mismatched)
        + "\n\nThe archive is what a human downloads and uploads, but everything "
        "the manifest measured applies to the LOOSE files — so a drifted archive "
        "ships content nothing has ever verified. Rebuild it from the package "
        "directory."
    )


def test_the_archive_contains_every_fixture_and_the_user_facing_documents():
    with zipfile.ZipFile(ARCHIVE) as zf:
        names = set(zf.namelist())
    required = {e["filename"] for e in ENTRIES} | {"UPLOAD-GUIDE.md", "MANIFEST.json"}
    assert required <= names, (
        f"the archive is missing files a human needs: {sorted(required - names)}"
    )
    assert ARCHIVE.name not in names, "the archive contains itself"
    assert "ENGINEERING-NOTES.md" not in names, (
        "ENGINEERING-NOTES.md is an internal document and must not ship in the "
        "user's download"
    )


def test_the_archive_contains_NOTHING_BEYOND_what_a_human_needs():
    """No extra entry, named or unnamed.

    The test above is a SUBSET check (`required <= names`) plus two named
    exclusions, so it passes with an arbitrary extra file in the archive as long
    as that file is neither the archive itself nor `ENGINEERING-NOTES.md`. This
    one pins the SET, which is the property that actually matters: the archive is
    the only thing a human downloads, so anything inside it is something they
    were handed — and nothing else in the repository re-measures a file that got
    in by accident.
    """
    with zipfile.ZipFile(ARCHIVE) as zf:
        names = set(zf.namelist())
    expected = {e["filename"] for e in ENTRIES} | {"UPLOAD-GUIDE.md", "MANIFEST.json"}
    assert names == expected, (
        "the archive's contents are not exactly the eighteen files plus the two "
        f"user-facing documents.\n  unexpected: {sorted(names - expected)}\n"
        f"  missing:    {sorted(expected - names)}"
    )
    assert not any("/" in n for n in names), (
        f"the archive contains a directory entry or nested path: "
        f"{sorted(n for n in names if '/' in n)}. It is built flat so that a human "
        "who unzips it gets the files themselves, not a folder to dig through."
    )


#: Absolute paths that only exist on one particular machine.
#:
#: WHY THIS IS A DEFECT EVEN THOUGH THIS REPOSITORY IS PRIVATE. It is not a secret
#: leak and must not be described as one — the harm is plainer than that. Everything
#: inside the archive is handed to an operator, and `MANIFEST.json`'s
#: `validator_invocation` block is a REPRODUCTION INSTRUCTION: it tells the reader
#: how to re-derive the verdicts the manifest states. `Run from
#: /Users/<somebody>/Documents/ISAAC` is an instruction nobody but that one person
#: can follow, on that one machine, and it silently stops being followable for its
#: own author the moment the checkout moves. A repo-relative instruction
#: ("the directory containing schema/isaac_record_v1.json") works for every reader,
#: including the author later. The same argument covers a `/home/...` path from a
#: Linux checkout and a `C:\...` path from a Windows one.
#:
#: SCOPE: this guards the ARCHIVE's members, because those are what leaves the
#: repository. `ENGINEERING-NOTES.md` is deliberately not covered — it is pinned OUT
#: of the archive by `test_the_archive_contains_every_fixture_and_the_user_facing_documents`
#: and so is never distributed. (Its own two occurrences were cleaned at the same
#: time as this guard was added; that is hygiene, not a requirement this test makes.)
_MACHINE_SPECIFIC_PATH_MARKERS = (
    "/Users/",
    "/home/",
    "C:\\",
    "/private/tmp/",
    "/var/folders/",
)


def test_no_archive_member_carries_a_machine_specific_path():
    """Scans the BYTES of everything in the download, not just the documents.

    Pinning the member SET (above) says nothing about member CONTENT, and the
    per-file measurement tests read the loose files for verdicts rather than for
    paths — so an absolute path could sit in the shipped `MANIFEST.json` with every
    test in this module green. It did: `validator_invocation.note` carried
    `Run from /Users/…/Documents/ISAAC` until this assertion was written.

    Whole-file substring scan on purpose. A defect like this arrives inside prose
    that no structured assertion is looking at, so there is nothing narrower to
    check.
    """
    with zipfile.ZipFile(ARCHIVE) as zf:
        offenders: list[str] = []
        for name in sorted(zf.namelist()):
            text = zf.read(name).decode("utf-8", errors="replace")
            offenders += [
                f"{name}: {marker!r}"
                for marker in _MACHINE_SPECIFIC_PATH_MARKERS
                if marker in text
            ]
    assert not offenders, (
        "machine-specific absolute paths are inside the archive an operator "
        f"downloads: {offenders}.\n"
        "This is not a secret leak — it is a reproduction instruction that only "
        "works on one machine, in a document handed to somebody else. Rewrite it "
        "relative to the repository root (e.g. 'the directory containing "
        "schema/isaac_record_v1.json'), then rebuild the archive and re-measure its "
        "digest in docs/krish-manual-verification-checklist.md."
    )


#: The committed archive, measured. Regenerate BOTH numbers together with the
#: archive; never copy one across from a previous build.
#:
#:   shasum -a 256 qa/validator-upload-package/isaac-validator-qa-files.zip
#:   wc -c          qa/validator-upload-package/isaac-validator-qa-files.zip
_ARCHIVE_SHA256 = "daee2ebc7bfa9dc0abbb167f575b02ab2477f384c38bcacbff63f1b124a66d04"
_ARCHIVE_BYTES = 66823

#: Documents that quote the digest to a human. Both are asserted to be FOUND, so
#: renaming one cannot make the cross-check vacuous.
_DIGEST_QUOTING_DOCS = (
    Path("docs/krish-manual-verification-checklist.md"),
    Path("docs/superpowers/plans/2026-08-03-product-hardening-closure.md"),
)

#: Any 64-hex token, i.e. anything shaped like a sha256.
_SHA256_TOKEN = re.compile(r"\b[0-9a-f]{64}\b")


def test_the_committed_archive_matches_the_digest_and_size_the_operator_is_told_to_verify():
    """Pins the archive's own bytes, and the number quoted to the operator.

    `docs/krish-manual-verification-checklist.md` tells a human to run `shasum -a
    256` and — by its own wording — to distrust the archive on a mismatch. Nothing
    asserted that digest, so any edit inside the package that got the archive
    correctly rebuilt would leave the document quoting the PREVIOUS build: every
    test green, and the operator instructed to refuse a correct archive. That is the
    failure mode this test exists for, and it is worse than a stale document,
    because the person it misleads has been told to trust it.

    THE DIGEST IS OF THE COMMITTED BYTES, NOT OF A REBUILD. A rebuild-and-compare
    would be the tempting form and it is unusable here: a ZIP's bytes include
    DEFLATE output, which is a property of the linked zlib rather than of the ZIP
    format, so a rebuild pin fails on a machine where nothing is wrong.
    `test_the_archive_metadata_is_normalised_so_the_build_is_reproducible` is what
    covers reproducibility; this one covers "the document and the file agree".
    """
    data = ARCHIVE.read_bytes()
    assert len(data) == _ARCHIVE_BYTES, (
        f"the archive is {len(data)} bytes, this test pins {_ARCHIVE_BYTES}. "
        "Re-measure with `wc -c` and update _ARCHIVE_BYTES, _ARCHIVE_SHA256 and "
        "every document listed in _DIGEST_QUOTING_DOCS together."
    )
    assert (measured := _sha256(data)) == _ARCHIVE_SHA256, (
        f"the archive's sha256 is {measured}, this test pins {_ARCHIVE_SHA256}.\n"
        "If you changed the package on purpose, rebuild the archive and then update "
        "_ARCHIVE_SHA256, _ARCHIVE_BYTES and every document in "
        "_DIGEST_QUOTING_DOCS in the SAME commit — the operator is told to refuse "
        "an archive whose digest does not match the document."
    )

    for relative in _DIGEST_QUOTING_DOCS:
        doc = ROOT / relative
        assert doc.is_file(), (
            f"{relative} is missing, so this test's cross-check is vacuous. If the "
            "document moved, update _DIGEST_QUOTING_DOCS."
        )
        text = doc.read_text()
        assert "isaac-validator-qa-files" in text, (
            f"{relative} no longer mentions the archive; revisit whether it still "
            "belongs in _DIGEST_QUOTING_DOCS."
        )
        assert _ARCHIVE_SHA256 in text, (
            f"{relative} does not quote the archive's current sha256 "
            f"{_ARCHIVE_SHA256}. It instructs a human to verify the checksum and to "
            "distrust a mismatch, so a stale digest there makes a CORRECT archive "
            "look tampered with."
        )

    # A THIRD document could start quoting a digest later and go stale unnoticed, so
    # every sha256-shaped token in any Markdown that mentions the archive must be
    # this digest. Scoped to files that mention the archive, so unrelated hashes
    # elsewhere in the docs are not this test's business.
    candidates = [*ROOT.glob("docs/**/*.md"), *PACKAGE.glob("*.md"), ROOT / "README.md"]
    stale: list[str] = []
    for doc in sorted(set(candidates)):
        if not doc.is_file():
            continue
        text = doc.read_text()
        if "isaac-validator-qa-files" not in text:
            continue
        stale += [
            f"{doc.relative_to(ROOT)}: {token}"
            for token in set(_SHA256_TOKEN.findall(text))
            if token != _ARCHIVE_SHA256
        ]
    assert not stale, (
        "these documents mention the QA archive and quote a sha256 that is not its "
        f"current digest {_ARCHIVE_SHA256}:\n  " + "\n  ".join(sorted(stale))
    )


def test_the_archive_metadata_is_normalised_so_the_build_is_reproducible():
    """The archive rebuilds to identical bytes — enforced via its metadata.

    WHY THIS IS NOT A sha256 PIN. A pinned archive digest would be the most
    direct assertion and it would be the wrong one: a ZIP's bytes include DEFLATE
    output, and DEFLATE is a property of the linked zlib rather than of the ZIP
    format. The same content at the same nominal level can compress to a
    different (perfectly valid) byte stream under a different zlib, so a digest
    pin would fail on a machine where nothing was wrong. Verified locally: the
    committed archive reproduces bit-for-bit at zlib's DEFAULT level and differs
    at levels 1 and 9.

    What IS portable is the metadata normalisation that makes the build
    reproducible in the first place, and it is the part a careless rebuild
    destroys. `zip -r` from a shell, or `zipfile` without an explicit `ZipInfo`,
    stamps every entry with the current wall-clock time and the umask of whoever
    ran it — so the archive's bytes change on every rebuild while its contents do
    not, and the checksum quoted to an operator in
    `docs/krish-manual-verification-checklist.md` becomes noise.

    The recipe these assertions describe: entries sorted by name; each
    `ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))` with
    `external_attr = 0o644 << 16`, `create_system = 3` and `ZIP_DEFLATED` at
    zlib's default level; no extra fields, no comments, no directory entries.
    """
    with zipfile.ZipFile(ARCHIVE) as zf:
        infos = zf.infolist()
        assert zf.comment == b"", "the archive carries a comment, which a rebuild would not"

    assert [i.filename for i in infos] == sorted(i.filename for i in infos), (
        "the archive's entries are not in sorted order, so two rebuilds from the "
        "same directory can disagree — directory iteration order is not stable "
        "across filesystems"
    )

    epoch = (1980, 1, 1, 0, 0, 0)
    stamped = {i.filename: i.date_time for i in infos if i.date_time != epoch}
    assert not stamped, (
        "these entries do not carry the fixed ZIP epoch, so the archive was built "
        f"with wall-clock timestamps and cannot rebuild to the same bytes: {stamped}"
    )

    modes = {i.external_attr >> 16 for i in infos}
    assert modes == {0o644}, (
        f"entry permission bits are not uniformly 0644: {[oct(m) for m in sorted(modes)]}. "
        "A umask-dependent mode makes the archive's bytes depend on who built it."
    )

    assert {i.compress_type for i in infos} == {zipfile.ZIP_DEFLATED}, (
        "entries are not uniformly DEFLATE-compressed; a mixed archive is a sign "
        "of a hand-edited or appended-to file rather than a clean rebuild"
    )
    assert {i.create_system for i in infos} == {3}, (
        "entries do not uniformly declare create_system 3 (Unix), so the archive "
        "would rebuild differently on a different platform"
    )

    decorated = {
        i.filename: (len(i.extra), i.comment) for i in infos if i.extra or i.comment
    }
    assert not decorated, (
        "these entries carry extra fields or per-entry comments, which macOS "
        f"archive tools add and which are not reproducible: {decorated}"
    )


# --- the measurement ----------------------------------------------------------


@pytest.mark.parametrize("entry", JSON_ENTRIES, ids=lambda e: e["filename"])
def test_the_manifest_records_the_verdict_the_validator_actually_produces(entry):
    """Re-measure. The manifest must agree with the deterministic validator."""
    path = PACKAGE / entry["filename"]
    raw_bytes = path.read_bytes()
    measured = entry["measured_validator_result"]
    expected_ok = measured["ok"]

    if "bytes" in entry:
        assert entry["bytes"] == len(raw_bytes), (
            f"{path.name}: MANIFEST.json says bytes={entry['bytes']}, the file is "
            f"{len(raw_bytes)}. UPLOAD-GUIDE.md quotes byte counts to the reader."
        )

    try:
        record = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        # Only the deliberately-malformed file may land here. Its entry must record
        # that no verdict exists (`parsed: false`, `ok: null`) rather than claiming
        # one — a stated PASS/FAIL for a file the validator was never invoked on
        # would be a fabricated measurement.
        assert measured.get("parsed") is False, (
            f"{path.name} does not parse as JSON ({exc}), so its manifest entry "
            "must record parsed: false rather than a validator verdict"
        )
        assert expected_ok is None, (
            f"{path.name} does not parse as JSON, so no verdict can exist for it, "
            f"but its manifest entry claims ok={expected_ok!r}"
        )
        if "parse_error" in measured:
            assert measured["parse_error"] == str(exc), (
                f"{path.name}: MANIFEST.json records parse_error\n"
                f"  {measured['parse_error']!r}\n"
                f"but the parser actually says\n  {str(exc)!r}\n"
                "The manifest reports measurements; a paraphrase is not one."
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
        "armed, or the vendored schema was refreshed), then this package is now "
        "telling a human the wrong thing. Update ALL FOUR together: MANIFEST.json; "
        "UPLOAD-GUIDE.md's per-file row AND its quick-reference table; README.md's "
        "'expected to PASS' section; and ENGINEERING-NOTES.md, which holds the "
        "root-cause analysis and would be the most wrong of the four.\n"
        f"Validator output:\n{report.render()}"
    )

    if (expected_count := measured.get("error_count")) is not None:
        assert len(report.errors) == expected_count, (
            f"{path.name}: MANIFEST.json says error_count={expected_count}, "
            f"measured {len(report.errors)}.\n{report.render()}"
        )

    # R2 — the ADVISORY tier, re-measured too.
    #
    # The manifest now publishes an `advisory_warnings` list per file, and the guide
    # tells the operator which warning to expect on which screen. Without this
    # assertion those are unverified prose: the manifest could name a warning the code
    # no longer emits, or go silent about one it does, and the operator would work from
    # it either way. `ok`/`error_count` above cannot catch that — warnings are
    # deliberately non-gating, so they move independently of the verdict.
    if (expected_warnings := measured.get("advisory_warnings")) is not None:
        actual = sorted(w.code for w in portal_warnings(record).warnings)
        assert actual == sorted(expected_warnings), (
            f"{path.name}: MANIFEST.json says advisory_warnings="
            f"{sorted(expected_warnings)}, measured {actual}.\n"
            "UPLOAD-GUIDE.md quotes these to the operator per file AND in its "
            "quick-reference table — update both, and re-check whether "
            "known_divergences still describes the situation."
        )
        # Non-gating is a property of the CONTRACT, not a hope about it: a record can
        # carry warnings and still be `ok`, and that must stay true or this tier
        # becomes a second authority on validity beside the vendored schema.
        assert measured.get("advisory_is_gating") is False, (
            f"{path.name}: the manifest must record advisory_is_gating: false"
        )

    # `ok` and `error_count` alone let a file be swapped to fail for a COMPLETELY
    # different reason while both hold — falsifying the entry's `purpose`, its
    # `schema_paths_exercised`, and the exact error string the guide quotes.
    if report.errors:
        first = report.errors[0]
        if (want_path := measured.get("first_error_path")) is not None:
            assert first.path == want_path, (
                f"{path.name}: MANIFEST.json says the first error is at "
                f"{want_path!r}, measured {first.path!r}. The file can still fail "
                "the same NUMBER of times while exercising a different schema path "
                f"than its purpose claims.\n{report.render()}"
            )
        if (want_msg := measured.get("first_error_message")) is not None:
            assert first.message == want_msg, (
                f"{path.name}: MANIFEST.json says the first error message is\n"
                f"  {want_msg!r}\nmeasured\n  {first.message!r}\n"
                f"UPLOAD-GUIDE.md quotes this string to the reader.\n{report.render()}"
            )


# --- the guide ----------------------------------------------------------------

#: Matches `| 7 | `some-file.json` | FAIL — 2 errors |` and `… | PASS |`.
_GUIDE_ROW = re.compile(
    r"^\|\s*\d+\s*\|\s*`(?P<file>[^`]+)`\s*\|\s*(?P<verdict>[^|]+?)\s*\|\s*$",
    re.MULTILINE,
)


def _guide_rows() -> dict[str, str]:
    return {
        m.group("file"): m.group("verdict") for m in _GUIDE_ROW.finditer(GUIDE.read_text())
    }


def test_the_guide_quick_reference_table_covers_every_file():
    rows = _guide_rows()
    assert rows, (
        "no quick-reference rows matched in UPLOAD-GUIDE.md. Either the table was "
        "removed or its shape changed, so the cross-check below is now vacuous — "
        "which is worse than absent. Update `_GUIDE_ROW`."
    )
    missing = sorted({e["filename"] for e in ENTRIES} - set(rows))
    assert not missing, f"UPLOAD-GUIDE.md's quick-reference table omits: {missing}"


def test_the_guide_quick_reference_table_agrees_with_the_manifest():
    rows = _guide_rows()
    disagreements: list[str] = []
    for entry in ENTRIES:
        verdict = rows.get(entry["filename"])
        if verdict is None:
            continue  # covered by the test above
        measured = entry["measured_validator_result"]
        ok = measured.get("ok")
        says_pass = "PASS" in verdict.upper()
        says_fail = "FAIL" in verdict.upper()

        if ok is True and not says_pass:
            disagreements.append(
                f"{entry['filename']}: manifest ok=True, guide says {verdict!r}"
            )
        elif ok is False and not says_fail:
            disagreements.append(
                f"{entry['filename']}: manifest ok=False, guide says {verdict!r}"
            )
        elif ok is None and (says_pass or says_fail):
            disagreements.append(
                f"{entry['filename']}: no verdict exists (unparseable), but the "
                f"guide states one: {verdict!r}"
            )

        if (m := re.search(r"(\d+)\s+error", verdict)) and measured.get(
            "error_count"
        ) is not None:
            if int(m.group(1)) != measured["error_count"]:
                disagreements.append(
                    f"{entry['filename']}: guide says {m.group(1)} error(s), "
                    f"manifest measured {measured['error_count']}"
                )

    assert not disagreements, (
        "UPLOAD-GUIDE.md contradicts MANIFEST.json. A human follows the guide, so "
        "the guide being wrong is precisely the harm this package exists to "
        "avoid:\n  " + "\n  ".join(disagreements)
    )


# --- governance ---------------------------------------------------------------


def test_the_two_known_divergences_are_still_declared_as_divergences():
    """The package's diagnostic value depends on these being flagged, not hidden.

    Pinned by NAME rather than by counting flags, so that adding a third
    divergence does not fail this test while silently un-flagging one of these two
    would.
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
            "row, README.md and ENGINEERING-NOTES.md."
        )


def test_no_qa_record_carries_an_attribution_block():
    """No person or account may be named in a shipped fixture.

    Scans every non-document file in the package, not only the `.json` manifest
    entries, so a `.txt` fixture cannot slip past.
    """
    offenders = [
        p.name
        for p in sorted(PACKAGE.iterdir())
        if p.name not in _NOT_FIXTURES and '"attribution"' in p.read_text()
    ]
    assert not offenders, (
        f"these QA records contain an `attribution` block: {offenders}. The block "
        "is optional in the schema and is omitted on purpose so that no person or "
        "account is named in a committed fixture."
    )


#: The two sentences every shipped file states about itself. Product language, so
#: they survive `_DEV_VOCABULARY`; unambiguous, so a reader cannot mistake the file
#: for a transcription of a real measurement.
_PROVENANCE_SENTENCES = (
    "Constructed by hand for validator exercise",
    "no measurement provenance",
)


def test_every_shipped_fixture_states_its_own_provenance_in_its_own_text():
    """CLAUDE.md §6: a committed fixture must be unmistakably not real data.

    The seventeen JSON records have always carried these sentences by convention —
    but a convention is not a check, and `unsupported-file.txt` was the one file
    that carried NEITHER. It read as a genuine logbook transcription (a real-looking
    beamline designation and the textbook Cu K-edge energy presented as a measured
    value), which is exactly the shape §6 forbids, and no assertion noticed.

    `_DEV_VOCABULARY` below constrains the fix and is the reason this is subtle: the
    package's fixtures are operator-facing product content, so "synthetic" and
    "test data" are BANNED here. The disclosure therefore has to be product
    language that is still unambiguous, which is what these two sentences are.
    Scans every non-document file, so a future `.txt` or `.csv` cannot slip in
    silently either.
    """
    missing: list[str] = []
    for path in sorted(PACKAGE.iterdir()):
        if path.name in _NOT_FIXTURES:
            continue
        text = path.read_text()
        missing += [
            f"{path.name}: {sentence!r}"
            for sentence in _PROVENANCE_SENTENCES
            if sentence not in text
        ]
    assert not missing, (
        "these shipped files do not state their own provenance in their own text: "
        f"{missing}. Every file in this package must say, in language an operator "
        "reads, that it was constructed by hand and carries no measurement "
        "provenance — otherwise it can be mistaken for a record of a real "
        "measurement. Note that `_DEV_VOCABULARY` forbids the obvious words, so the "
        "disclosure must be product language."
    )


#: Vocabulary that must not appear in anything a NORMAL USER reads.
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
    hits: list[str] = []
    for path in sorted(PACKAGE.iterdir()):
        if path.name in _VOCABULARY_EXEMPT or path.name == ARCHIVE.name:
            continue
        lowered = path.read_text().lower()
        hits += [f"{path.name}: {word!r}" for word in _DEV_VOCABULARY if word in lowered]
    assert not hits, (
        "development vocabulary reached content a normal user reads — the record "
        f"files and UPLOAD-GUIDE.md must use product language. Hits: {hits}. "
        "(See `_VOCABULARY_EXEMPT` for the three deliberate exemptions and the "
        "reason each one is exempt.)"
    )


def test_the_vocabulary_exemption_set_is_exactly_what_we_intend():
    """Guards the exemption list itself, so it cannot quietly grow.

    `MANIFEST.json` is the interesting member: unlike the other two it DOES ship
    inside the user's archive. It is exempt anyway because it is a machine-readable
    artifact whose `provenance` block has to name its public upstream sources
    truthfully. That is a deliberate decision, recorded here so a future reader
    does not mistake it for an oversight — and so that adding a fourth exemption
    requires editing this assertion and justifying it.
    """
    assert _VOCABULARY_EXEMPT == {
        "MANIFEST.json",
        "ENGINEERING-NOTES.md",
        "README.md",
    }, (
        "the vocabulary exemption set changed. Every exemption is a place where "
        "development vocabulary may reach a reader; justify the change here."
    )
    with zipfile.ZipFile(ARCHIVE) as zf:
        shipped = set(zf.namelist())
    assert "MANIFEST.json" in shipped, (
        "this test's rationale assumes MANIFEST.json ships to the user; it no "
        "longer does, so revisit whether it still needs the exemption"
    )
