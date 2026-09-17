"""THE BL15-2 HISTORICAL IMPORT, END TO END, OVER A REAL ARCHIVE.

    the sanitized mini corpus
      -> import session -> inventory -> classification -> reading
      -> relationships -> sample groups -> candidate Runs
      -> conflicts / unmapped / partial readings preserved
      -> review -> add to experiment -> ordinary Runs workspace
      -> isaac_records.draft_validator.validate_draft

**IT IS A REAL WALK, NOT A SEEDED ONE, AND THAT IS THE WHOLE REASON THIS FILE
EXISTS RATHER THAN AN ASSERTION ADDED TO AN EXISTING SUITE.**
``CLAUDE.md`` §11 records why: all five canonical scenarios are built by
``build_draft`` from a fixture sheet that ALREADY CARRIES the values, so every
completion and export test in the suite began past the part that did not work,
and three real defects lived inside 4,714 passing backend tests.
``test_scientist_can_finish_a_record.py`` is the precedent. So every expectation
below is **written out here**, and
:func:`test_nothing_in_this_file_borrows_a_reconstruction` is a negative control
that parses this file and fails if it ever reaches for the reading layer to tell
it what to expect.

WHAT "WRITTEN OUT" MEANS PRECISELY, because it is not "no imports":
this file may call the PRODUCT (the nine HTTP operations, the record routes, the
truth core's validator) and it may call the gold-standard harness, whose own
ground truth is a committed human-authored document that
``bl15.evaluate.load_gold_standard`` refuses if it admits to being machine-
derived. It may **not** call ``bl15.archive``, ``bl15.classify``,
``bl15.relate``, ``bl15.reconstruct`` or any reader to discover what the answer
is — a walk that asked the reading layer what it had read would agree with
itself by construction.

FIVE PROOFS, EACH ITS OWN TEST, each one a shortcut the design forbids:

1. ``.dat`` scan exports do NOT become Runs — 908 of them in the real archive
   against ~92 measurements, so one-file-one-run would invent 816 measurements.
2. ``.mac`` macros do NOT become Runs, and a multi-``newfile`` macro yields
   SEVERAL declarations — 29 real macros declare more than one target (max 8)
   and 4 declare none, so one macro is neither one measurement nor zero.
3. Shared README/notes context is INHERITED, not copied onto each unit — a
   beamtime value rendered 94 times as though entered 94 times is a lie about
   where it came from.
4. Conflicts stay VISIBLE with every reading and NO chosen winner — the corpus
   contains a systematic rename, so "trust the header, it is closer to the
   instrument" is wrong for exactly the cases it would be reached for.
5. Unknown tokens and unmapped concepts SURVIVE — 39 of 45 concepts have no
   proposable mapping, so dropping them would discard most of the corpus.

DATA BOUNDARY: none. The only archive read is
``tests/fixtures/bl15/gold/mini_corpus``, committed sanitized fixtures whose
sample names, potentials and motor values are unmistakably synthetic; the
workspace is a ``tmp_path``; no database connection is opened; nothing under
``examples/`` is read and no model sees anything.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from fastapi.testclient import TestClient

import isaac_api.historical_import as hist
import isaac_api.identity as identity
import isaac_api.workspace as ws

#: The committed archive this walk imports. Named from the application's own
#: allowlist key, not from a filesystem path.
ARCHIVE = "bl15_synthetic_mini_corpus"

ACTOR = "ada.lovelace"

# --- WHAT THIS CORPUS CONTAINS, WRITTEN OUT ----------------------------------
#
# Every literal below was read by a person from the fixture files' own names and
# contents, not harvested from any reader's output. They are the expectations a
# scientist looking at the folder would state.

#: The 14 files the archive holds, as the walk's own archive-relative paths.
EXPECTED_FILES = (
    "01_01_SYN1_acid_beforeCycling_filter10_060mV",
    "01_01_SYN1_acid_beforeCycling_filter10_060mV_dir/"
    "01_01_SYN1_acid_beforeCycling_filter10_060mV",
    "01_01_SYN1_acid_beforeCycling_filter10_060mV_dir/"
    "01_01_SYN1_acid_beforeCycling_filter10_060mV_001.dat",
    "01_01_SYN1_acid_beforeCycling_filter10_060mV_dir/"
    "01_01_SYN1_acid_beforeCycling_filter10_060mV_002.dat",
    "02_01_SYN1_acid_beforeCycling_filter10_060mV_again",
    "02_01_SYN1_acid_beforeCycling_filter10_060mV_again_dir/"
    "02_01_SYN1_acid_beforeCycling_filter10_060mV_again",
    "03_02_SYN2_base_after1500Cycling_ffilter35_1200mV_zz9",
    "03_02_SYN2_base_after1500Cycling_filter20_0p5nm_1200mV",
    "990101 SYNTHETIC BL15 notes.txt",
    "Synth_XAS.mac",
    "alignsynth",
    "readme.txt",
    "run01.mac",
    "runsynth",
)

#: The FOUR sample measurements a scientist would offer as Runs. `alignsynth` is
#: the fifth measurement and is deliberately NOT one of them.
EXPECTED_RUN_STEMS = (
    "01_01_SYN1_acid_beforeCycling_filter10_060mV",
    "02_01_SYN1_acid_beforeCycling_filter10_060mV_again",
    "03_02_SYN2_base_after1500Cycling_ffilter35_1200mV_zz9",
    "03_02_SYN2_base_after1500Cycling_filter20_0p5nm_1200mV",
)

#: The alignment acquisition. A real measurement, fully assembled, NOT a Run.
ALIGNMENT_STEM = "alignsynth"

#: The two `.dat` scan children, written out. They belong to the FIRST
#: measurement and are never measurements of their own.
SCAN_EXPORTS = (
    "01_01_SYN1_acid_beforeCycling_filter10_060mV_dir/"
    "01_01_SYN1_acid_beforeCycling_filter10_060mV_001.dat",
    "01_01_SYN1_acid_beforeCycling_filter10_060mV_dir/"
    "01_01_SYN1_acid_beforeCycling_filter10_060mV_002.dat",
)

#: The three macro files. `runsynth` has NO extension, which is why a macro
#: inventory built from `*.mac` alone finds two of three — the same off-by-one
#: the real corpus produces with `run29`.
MACRO_FILES = ("Synth_XAS.mac", "run01.mac", "runsynth")

#: `run01.mac`'s two `newfile` declarations, written out from the file.
RUN01_DECLARED = (
    "01_01_SYN1_acid_beforeCycling_filter10_060mV",
    "99_NEVER_ACQUIRED_SYN",
)

#: The measurement whose `#F` header disagrees with its own filename: the
#: filename says `after1500Cycling`, the header says `beforeCycling`.
RENAMED_STEM = "03_02_SYN2_base_after1500Cycling_ffilter35_1200mV_zz9"

#: The unrecognised filename token a profile must REPORT rather than drop.
UNKNOWN_TOKEN = "zz9"

#: The one run-scoped official path with a write route in this build that this
#: corpus evidences. Written out; the walk proves the server agrees.
RUN_TARGET_PATH = "timestamps.acquired_start_utc"

#: The one record-scoped official path with a write route that this corpus
#: evidences.
RECORD_TARGET_PATH = "system.technique"


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    return ws


@pytest.fixture()
def client(workspace):
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def armed_client(workspace, monkeypatch):
    """A deployment that CAN accept a proposal: the fixture verifier.

    No shipped deploy artifact sets these variables. Every default-configured
    deployment answers ``409 human_actor_required`` on acceptance, which is a
    CONFIGURATION fact and not a defect; running the last leg of the walk here is
    what makes the chain provably complete, and
    :func:`test_a_default_deployment_still_stops_at_the_proposal` is what proves
    it stops where it is supposed to.
    """
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


# --- helpers: the PRODUCT's own operations, nothing else ----------------------


def _imported(client) -> str:
    """One session holding the archive, walked and reconstructed. Over HTTP."""
    created = client.post("/api/imports", json={"label": "BL15-2 historical"})
    assert created.status_code == 200, created.text
    import_id = created.json()["import"]["import_id"]

    added = client.post(
        f"/api/imports/{import_id}/sources",
        json={"kind": "archive", "fixture_name": ARCHIVE, "filename": "BL15-2 corpus"},
    )
    assert added.status_code == 200, added.text

    parsed = client.post(f"/api/imports/{import_id}/parse")
    assert parsed.status_code == 200, parsed.text
    built = client.post(f"/api/imports/{import_id}/reconstruct")
    assert built.status_code == 200, built.text
    return import_id


def _view(client, import_id: str) -> dict:
    response = client.get(f"/api/imports/{import_id}")
    assert response.status_code == 200, response.text
    return response.json()["import"]


def _record(client, title="BL15-2 historical import") -> str:
    response = client.post("/api/experiments", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _add_to_experiment(client, import_id: str, eid: str, **body) -> dict:
    response = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, **body},
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _runs(client, eid: str) -> list[dict]:
    response = client.get(f"/api/experiments/{eid}/runs")
    assert response.status_code == 200, response.text
    return response.json()["runs"]


def _manifest_rows(view: dict) -> dict[str, dict]:
    page = view["archive"]["manifest_page"]
    # THE WHOLE MANIFEST MUST BE ON THIS PAGE for this corpus, or the assertions
    # below would be reading a window and calling it the archive.
    assert page["total"] == len(page["rows"]) == 14, page["total"]
    assert page["truncated"] is False
    return {row["archive_path"]: row for row in page["rows"]}


def _units(view: dict) -> dict[str, dict]:
    page = view["archive"]["units_page"]
    assert page["truncated"] is False
    return {row["stem"]: row for row in page["rows"]}


def _candidates(view: dict) -> list[dict]:
    page = view["reconstruction"]["candidate_page"]
    # Every candidate this corpus produces fits in one page; if a future fixture
    # grows past it, this assertion is the thing that says so rather than the
    # tests below quietly examining a subset.
    assert page["truncated"] is False, page
    return view["reconstruction"]["candidates"]


# --- the walk -----------------------------------------------------------------


def test_the_archive_is_one_manifest_entry_and_its_parse_is_an_inventory(client):
    """1,192 files must not be 1,192 manifest rows, and 500 is the ceiling.

    ``MAX_SOURCES_PER_SESSION`` is 500 and the real corpus is 1,192 files.
    Raising it was the wrong fix — a complete manifest a scientist cannot audit
    is the same as no manifest — so a folder is ONE entry whose parse result is
    an inventory.
    """
    import_id = _imported(client)
    view = _view(client, import_id)

    assert len(view["sources"]) == 1, view["sources"]
    entry = view["sources"][0]
    assert entry["kind"] == "archive"
    assert entry["parse_state"] == "parsed"
    assert view["source_counts"]["total"] == 1

    # THE INVENTORY IS THE PARSE RESULT, and it has all 14 files in it.
    assert view["archive"]["inventory"]["entry_count"] == 14
    assert set(_manifest_rows(view)) == set(EXPECTED_FILES)


def test_the_archive_sources_sha256_is_absent_unless_the_scientist_supplied_one(client):
    """THE CLAIM CORRECTION, MADE MECHANICAL.

    The walk computes a SHA-256 of every archive MEMBER — it must, or the corpus
    doubles and the duplicate groups cannot be found. ``historical_import``'s
    module docstring had asserted *"A DIGEST IS NEVER COMPUTED HERE, not even for
    a fixture this module does read"*, which that made false; the corrected claim
    is narrower: a member digest is computed inside the parse, for structural
    deduplication, and is NEVER published as a manifest ``sha256`` for any
    source, of any kind. This test is what makes that a mechanism rather than
    prose.

    MUTATION: assigning any member digest to the manifest entry's ``sha256``
    makes the first half RED; dropping ``content_sha256`` from the manifest rows
    makes the second half RED.
    """
    import_id = _imported(client)
    view = _view(client, import_id)

    # 1. THE MANIFEST ENTRY CARRIES NO DIGEST. Nothing was supplied, so nothing
    #    is recorded — "recorded", never "verified".
    assert view["sources"][0]["sha256"] is None

    # 2. AND MEMBER DIGESTS DO EXIST, which is why the claim needed correcting
    #    rather than merely restating. Every accepted entry has one.
    rows = _manifest_rows(view)
    digests = [row["content_sha256"] for row in rows.values()]
    assert all(isinstance(d, str) and len(d) == 64 for d in digests), digests

    # 3. THE DUPLICATE GROUPS ARE WHAT THEY ARE FOR. Two root acquisitions each
    #    have a byte-identical copy inside their own `_dir`, exactly as every
    #    `_dir` in the real archive does.
    assert view["corpus_digest"]["duplicate_group_count"] == 2
    root = "01_01_SYN1_acid_beforeCycling_filter10_060mV"
    copy_in_dir = f"{root}_dir/{root}"
    assert rows[root]["content_sha256"] == rows[copy_in_dir]["content_sha256"]


def test_a_scientist_supplied_digest_is_still_recorded_on_an_archive(client):
    """NEGATIVE CONTROL for the test above: absence is not an inability.

    If ``sha256`` were simply dropped for the archive kind, the previous test
    would pass for the wrong reason. A digest the scientist supplies is stored
    verbatim, shape-checked and never computed — the same contract as the other
    two kinds.
    """
    created = client.post("/api/imports", json={"label": "with a digest"})
    import_id = created.json()["import"]["import_id"]
    supplied = "a" * 64
    added = client.post(
        f"/api/imports/{import_id}/sources",
        json={"kind": "archive", "fixture_name": ARCHIVE, "sha256": supplied},
    )
    assert added.status_code == 200, added.text
    assert added.json()["source"]["sha256"] == supplied

    # AND A MALFORMED ONE IS REFUSED, with the sentence that says nothing is ever
    # computed.
    bad = client.post(
        f"/api/imports/{import_id}/sources",
        json={"kind": "archive", "fixture_name": ARCHIVE, "sha256": "not-a-digest"},
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["error"] == "malformed_sha256"
    assert "never computes one" in bad.json()["message"]


def test_the_corpus_digest_is_what_a_scientist_reads_first(client):
    """Totals, counts by source type, refusals and truncation. Every one counted.

    ``SourceRecord`` carries no ``source_type`` — classification is
    ``bl15.classify``'s and lives nowhere on the record — so without the
    classification map on the wire these figures are not derivable from anything
    a client can see, and a surface would be tempted to write them down.

    MUTATION: replacing ``by_source_type`` with a literal makes this RED, because
    the counts are asserted against expectations written out at the top of this
    file from the fixture names.
    """
    import_id = _imported(client)
    view = _view(client, import_id)
    digest = view["corpus_digest"]

    assert digest["total_sources"] == 14
    assert digest["refused"] == []
    assert digest["refused_count"] == 0
    assert digest["truncated_reason"] is None

    # COUNTED BY KIND, and the kinds are what a person reading the folder would
    # say: six SPEC acquisitions (four samples, plus one `_dir` copy each for two
    # of them), one alignment, two scan exports, two macros, one acquisition-
    # method macro, one shared readme, one beamtime notes document.
    assert digest["by_source_type"] == {
        "acquisition_method_macro": 1,
        "alignment": 1,
        "beamtime_notes": 1,
        "macro": 2,
        "scan_export": 2,
        "shared_readme": 1,
        "spec_acquisition": 6,
    }
    # EVERY CLASSIFICATION WAS DECIDED BY READING THE FILE'S OWN BYTES. A
    # path-confidence verdict is a lead, not a fact, and there are none here.
    assert digest["by_classification_confidence"] == {"content": 14}

    assert digest["measurement_units"] == 5
    assert digest["run_candidate_units"] == 4
    assert digest["conflicts"] == 5

    # THE HONESTY NUMBERS. Nothing was suppressed in this corpus, and the digest
    # says so as a measured zero rather than by omitting the key — over the real
    # archive one file suppresses ~41,000 statements.
    assert digest["statements_suppressed"] == 0
    assert digest["partial_readings"] == 0
    assert digest["statements_read"] > 0

    # AND THE THREE REASONS A RUN FROM THIS CORPUS CANNOT BE EXPORT-READY, stated
    # rather than left to be discovered as a progress bar that never fills.
    assert len(digest["cannot_be_export_ready"]) == 3
    joined = " ".join(digest["cannot_be_export_ready"])
    assert "temperature" in joined
    assert "descriptors" in joined
    assert "sha256" in joined


def test_no_progress_indicator_can_ever_fill_and_the_digest_says_why(client):
    """The three blockers come from the registry's own wording, not new copy.

    Two are ``bl15.mapping``'s constants and the third is
    ``historical_import.EXPORT_BLOCKED_NO_DESCRIPTORS``. Asserted by IDENTITY so
    a future edit cannot paraphrase one of them into a second wording of the same
    fact.
    """
    from isaac_api.bl15 import mapping as mp

    import_id = _imported(client)
    served = _view(client, import_id)["corpus_digest"]["cannot_be_export_ready"]
    assert served == [
        mp.TEMPERATURE_ABSENT_REASON,
        hist.EXPORT_BLOCKED_NO_DESCRIPTORS,
        mp.ASSETS_BLOCKED_REASON,
    ]


# --- PROOF 1: `.dat` files do not become Runs ---------------------------------


def test_proof_1_scan_exports_do_not_become_runs(client):
    """908 `.dat` files against ~92 measurements in the real archive.

    Promoting each to a Run would invent 816 measurements nobody performed. Here
    the two scan exports are the CHILDREN of the first measurement and are units
    of nothing.

    MUTATION: adding ``scan_export`` to ``relate.UNIT_SOURCE_TYPES`` makes this
    RED.
    """
    import_id = _imported(client)
    view = _view(client, import_id)
    rows = _manifest_rows(view)
    units = _units(view)

    # The two files ARE classified as scan exports — so this is not passing
    # because they were never recognised.
    for path in SCAN_EXPORTS:
        assert rows[path]["source_type"] == "scan_export", path

    # And NONE of them is a measurement, by acquisition path or by stem.
    acquisitions = {row["acquisition_path"] for row in units.values()}
    assert acquisitions.isdisjoint(SCAN_EXPORTS)
    assert set(units).isdisjoint({p.rsplit("/", 1)[-1] for p in SCAN_EXPORTS})

    # They are ATTACHED to the measurement whose directory holds them, which is
    # the alternative to being units: an unattached scan would be a source a
    # scientist could not find.
    first = units["01_01_SYN1_acid_beforeCycling_filter10_060mV"]
    assert first["scan_count"] == 2

    # AND ONE MEASUREMENT LEGITIMATELY HAS ZERO SCANS. Its `_dir` exists and is
    # empty, reproducing the two empty scan directories in the real archive — so
    # "every measurement has at least one scan" is false of the real corpus too.
    assert units["02_01_SYN1_acid_beforeCycling_filter10_060mV_again"]["scan_count"] == 0


# --- PROOF 2: `.mac` files do not become Runs --------------------------------


def test_proof_2_macros_do_not_become_runs_and_a_multi_newfile_macro_declares_several(
    client,
):
    """One `.mac` is neither one measurement nor zero.

    In the real archive 156 ``newfile`` declarations sit across 60 macro files:
    29 declare more than one, the maximum is 8, and **4 declare none at all**.
    One-macro-one-unit would have produced 60 units for 95 declared measurements
    AND turned four non-measurements into measurements.

    MUTATION: adding ``macro`` to ``relate.UNIT_SOURCE_TYPES`` makes the first
    half RED; making ``newfile`` parsing stop at the first block makes the second
    half RED.
    """
    import_id = _imported(client)
    view = _view(client, import_id)
    rows = _manifest_rows(view)
    units = _units(view)

    # All three macro files are recognised as macros — including `runsynth`,
    # which has no extension, so this is content-led and not a name rule.
    for path in MACRO_FILES:
        assert rows[path]["source_type"].endswith("macro"), (path, rows[path])
    assert rows["runsynth"]["extension"] == ""

    # NONE is a measurement.
    acquisitions = {row["acquisition_path"] for row in units.values()}
    assert acquisitions.isdisjoint(MACRO_FILES)
    assert set(units).isdisjoint(set(MACRO_FILES))

    # AND `run01.mac`'s TWO `newfile` blocks reach TWO different places — one
    # attaches to a measurement that exists, the other becomes a conflict
    # because nothing acquired it. That is the "several candidates from one
    # macro" property, and it is asserted by NAMING both targets.
    relationships = view["archive"]["relationships"]
    declared_targets: set[str] = set()
    for unit in relationships["units"]:
        for block in unit["declared_by"]:
            if block["macro_path"] == "run01.mac":
                declared_targets.add(block["declared_target"])
    conflict_subjects = {c["subject"] for c in relationships["corpus_conflicts"]}
    assert RUN01_DECLARED[0] in declared_targets, declared_targets
    assert RUN01_DECLARED[1] in conflict_subjects, conflict_subjects
    assert len(declared_targets | (conflict_subjects & set(RUN01_DECLARED))) == 2

    # AND ONE MACRO DECLARES NOTHING. `Synth_XAS.mac` is an acquisition-method
    # definition, which is the fourth real case a one-macro-one-run rule breaks.
    assert rows["Synth_XAS.mac"]["source_type"] == "acquisition_method_macro"
    for unit in relationships["units"]:
        for block in unit["declared_by"]:
            assert block["macro_path"] != "Synth_XAS.mac", unit["stem"]


# --- PROOF 3: shared context is inherited, not copied -------------------------


def test_proof_3_shared_context_is_inherited_not_copied_onto_each_unit(client):
    """A beamtime value rendered 94 times is a lie about where it came from.

    The shared candidates belong to the IMPORT. They are listed once, under
    ``shared_candidate_ids``, and they appear in NO unit's ``candidate_ids``.

    MUTATION: copying the shared evidence into each unit's candidate list makes
    this RED — the disjointness assertion is what catches it, not a count.
    """
    import_id = _imported(client)
    view = _view(client, import_id)
    shared = set(view["archive"]["shared_candidate_ids"])
    units = _units(view)

    # There IS inherited context, so this is not passing by there being none.
    assert shared, view["archive"]
    # Every shared candidate is attributed to a beamtime-scope source — the
    # notes document or the readme, neither of which is a measurement.
    unattached = {
        row["archive_path"] for row in view["archive"]["relationships"]["unattached"]
    }
    assert "readme.txt" in unattached
    assert "990101 SYNTHETIC BL15 notes.txt" in unattached

    # AND NOT ONE UNIT CLAIMS ANY OF THEM.
    for stem, unit in units.items():
        assert shared.isdisjoint(unit["candidate_ids"]), stem

    # The inheritance is also visible the other way round: each shared candidate
    # names the ONE archive source id (the whole archive is one manifest entry),
    # not a per-measurement id it does not have.
    source_id = view["sources"][0]["source_id"]
    for candidate in _candidates(view):
        if candidate["candidate_id"] in shared:
            assert candidate["supporting_source_ids"] == [source_id], candidate


# --- PROOF 4: conflicts stay visible, with no winner -------------------------


def test_proof_4_conflicts_stay_visible_with_every_reading_and_no_winner(client):
    """The corpus contains a systematic rename, so no source ranking is applied.

    ``03_02_SYN2_…_ffilter35_1200mV_zz9``'s own ``#F`` header says
    ``beforeCycling`` while its filename says ``after1500Cycling``. A rule like
    *"trust the internal header, it is closer to the instrument"* sounds obviously
    right and is WRONG for exactly those files, because a deliberate rename is
    likelier to be the scientist's correction.

    MUTATION: letting a conflicted candidate carry a ``proposed_value`` makes
    this RED — and ``SemanticCandidate`` refuses that at construction, so the
    mutation has to be to the type, which is the point.
    """
    import_id = _imported(client)
    view = _view(client, import_id)

    relationships = view["archive"]["relationships"]
    # FIVE conflicts, and they are asserted BY NAME rather than by count: a
    # reconstruction that lost all five and invented five others would pass a
    # count check perfectly.
    kinds: set[str] = set()
    for unit in relationships["units"]:
        kinds.update(c["kind"] for c in unit["conflicts"])
    kinds.update(c["kind"] for c in relationships["corpus_conflicts"])
    assert "internal_declaration_vs_filename" in kinds
    assert "duplicate_legacy_number" in kinds
    assert "macro_declared_never_acquired" in kinds

    # THE RENAME IS ON THE UNIT IT IS ABOUT, and it carries BOTH readings.
    renamed = [u for u in relationships["units"] if u["stem"] == RENAMED_STEM][0]
    rename_conflict = [
        c
        for c in renamed["conflicts"]
        if c["kind"] == "internal_declaration_vs_filename"
    ][0]
    values = {reading["value"] for reading in rename_conflict["readings"]}
    assert len(values) >= 2, rename_conflict
    assert any("beforeCycling" in v for v in values), values
    assert any("after1500Cycling" in v for v in values), values
    # NO WINNER IS RECORDED. The only value this build has for a conflict's
    # resolution is the one that says there is none, and it is named rather than
    # left absent so no consumer reads absence as agreement.
    assert rename_conflict["unresolved_reason"] == "sources_disagree"
    assert "value" not in rename_conflict, rename_conflict
    # AND THE CONFLICT EXPLAINS ITSELF. A conflict a reader cannot interpret is a
    # conflict they will dismiss.
    assert rename_conflict["explanation"], rename_conflict

    # AND THE SAME HOLDS OF EVERY CANDIDATE CARRYING A DISAGREEMENT: no value,
    # every reading, and a reason.
    disagreeing = [c for c in _candidates(view) if c["disagreement"]]
    assert disagreeing, "no conflict reached the candidate list"
    for candidate in disagreeing:
        assert candidate["proposed_value"] is None, candidate
        assert candidate["unresolved_reason"] == "sources_disagree"
        assert candidate["proposable"] is False
        assert len(candidate["disagreement"]) >= 2, candidate


def test_a_conflicted_candidate_cannot_be_sent_and_the_batch_still_proceeds(client):
    """A conflict is reported, never dropped, and never blocks the rest."""
    import_id = _imported(client)
    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)

    unresolved = [row for row in body["not_sent"] if row["error"] == "candidate_unresolved"]
    assert unresolved, body["not_sent"]
    for row in unresolved:
        assert row["reason"], row
    # AND WORK STILL HAPPENED: a conflict does not refuse the batch.
    assert body["counts"]["sent"] > 0, body["counts"]


# --- PROOF 5: unknown tokens and unmapped concepts survive -------------------


def test_proof_5_unknown_tokens_and_unmapped_concepts_survive(client):
    """39 of 45 concepts have no proposable mapping; dropping them loses the corpus.

    An unrecognised filename token must be REPORTED. Silently discarding the part
    of a name a profile does not recognise leaves a scientist unable to see what
    was passed over, which is ``HIST-004``'s banned pattern one layer down.

    MUTATION: dropping a candidate whose mapping is not proposable makes the
    second half RED, and it is the half that matters — the first would still pass.
    """
    import_id = _imported(client)
    view = _view(client, import_id)
    digest = view["corpus_digest"]

    # 1. THE UNKNOWN TOKEN IS PRESENT, as a concept the readers reported.
    assert digest["by_concept"].get("unknown_token"), digest["by_concept"]
    literals = [
        statement["value"]
        for candidate in _candidates(view)
        for statement in candidate["supporting_statements"]
        if statement["key"] == "unknown_token"
    ]
    assert UNKNOWN_TOKEN in literals, literals

    # 2. UNMAPPED CONCEPTS ARE CANDIDATES WITH THE REGISTRY'S OWN REASON, not
    #    absences. `not_expressible` is the largest bucket by far.
    statuses = digest["by_mapping_status"]
    assert statuses["not_expressible"] > statuses.get("deterministic", 0), statuses
    assert statuses["needs_domain_review"] > 0, statuses

    # 3. AND EVERY CONCEPT THE READERS EMITTED IS IN THE REGISTRY. A non-empty
    #    `unregistered_concepts` is a FINDING, not a failure — so it is asserted
    #    empty here and the assertion names what a non-empty value would mean.
    assert digest["unregistered_concepts"] == [], (
        "a reader emitted a concept the mapping registry has never examined: "
        f"{digest['unregistered_concepts']}"
    )

    # 4. THE VALUE IS THE SOURCE'S OWN WORDS. `ffilter35` is preserved verbatim;
    #    the normalisation ("filter 35") belongs beside it with its rule named,
    #    never instead of it.
    filters = [
        statement["value"]
        for candidate in _candidates(view)
        for statement in candidate["supporting_statements"]
        if statement["key"] == "filter"
    ]
    assert "ffilter35" in filters, filters


# --- add to experiment: ordinary Runs ----------------------------------------


def test_add_to_experiment_creates_one_ordinary_run_per_reviewed_measurement(client):
    """FOUR measurements, FOUR ordinary runs, ONE revision, and no `Run` field added.

    A run's authoritative content is exactly
    ``{id, experiment_id, label, ordinal, draft, record_id, overrides}``, so no
    ``origin`` marker is added — that would touch the run signature, the
    ``isaac_run_projection`` write and ``test_run_row_parity.py``'s exact key
    set, which is CI-only against a real PostgreSQL. Provenance is per-VALUE
    instead: a note beside every proposal carries the source filename and the
    statement.

    MUTATION: creating the runs in a loop with one save each makes the ``+1``
    assertion RED, which is the assertion that fails if this is ever
    reimplemented as a client loop.
    """
    import_id = _imported(client)
    eid = _record(client)

    before = ws.load_experiment(eid)
    assert before is not None and before.runs == []
    rev_before = before.rev

    body = _add_to_experiment(client, import_id, eid, create_runs=True)
    assert body["create_runs"] is True
    assert body["counts"]["runs_created"] == 4, body["counts"]

    # ONE REVISION FOR THE WHOLE BATCH. Four runs and every proposal, in one
    # `record_lock` and one `_save_versioned`.
    after = ws.load_experiment(eid)
    assert after is not None
    assert after.rev == rev_before + 1, (rev_before, after.rev)

    # FOUR ORDINARY RUNS, indistinguishable from ones added by hand: the run list
    # route serves them with no import-specific key anywhere.
    runs = _runs(client, eid)
    assert len(runs) == 4
    assert {row["stem"] for row in body["created_runs"]} == set(EXPECTED_RUN_STEMS)

    # THE LABEL IS THE SCIENTIST'S HANDLE: the legacy number the archive already
    # used, then the condition as the FILENAME WROTE IT. Written out here, not
    # harvested — `ffilter35` is NOT corrected to "filter 35" and
    # `after1500Cycling` is NOT expanded, because either would be this build
    # composing prose out of a token in the one string a run is identified by.
    labels = {row["label"] for row in runs}
    assert (
        "Legacy 3 · 02 · SYN2 · base · after1500Cycling · ffilter35 · 1200mV" in labels
    ), labels
    assert (
        "Legacy 1 · 01 · SYN1 · acid · beforeCycling · filter10 · 060mV" in labels
    ), labels
    # NO RUN IS CALLED "Run 1". `workspace.new_run` assigns that when a caller
    # names none; an import always has a better handle.
    assert not any(label.startswith("Run ") for label in labels), labels


def test_no_created_run_holds_a_single_value_from_the_import(client):
    """A HISTORICAL IMPORT WRITES NO VALUE. The runs are created EMPTY of it.

    ``HIST-005``'s requirement, proven at both target paths: the record-scoped
    one and the run-scoped one. Everything the import read arrives as an open
    proposal with a note, and a person decides each one.

    MUTATION: seeding a run's draft from the reader's output makes this RED,
    which is the whole point — that seeding would bypass review entirely.
    """
    import_id = _imported(client)
    eid = _record(client)
    _add_to_experiment(client, import_id, eid, create_runs=True)

    exp = ws.load_experiment(eid)
    assert exp is not None
    assert len(exp.runs) == 4

    for run in exp.runs:
        fields = (run.draft or {}).get("fields") or {}
        # BOTH TARGET PATHS ABSENT. Asserted per run rather than in aggregate, so
        # one seeded run cannot hide behind three empty ones.
        assert RUN_TARGET_PATH not in fields, (run.label, fields)
        assert RECORD_TARGET_PATH not in fields, (run.label, fields)
        # And no field anywhere carries a value: a historical import fills in
        # nothing at all, not merely nothing at the two paths this walk targets.
        valued = {
            path: env
            for path, env in fields.items()
            if isinstance(env, dict) and env.get("value") is not None
        }
        assert valued == {}, (run.label, valued)

    # THE RECORD'S OWN DRAFT IS LIKEWISE UNTOUCHED at the record-scoped path.
    assert RECORD_TARGET_PATH not in (exp.draft.get("fields") or {})


def test_the_proposals_and_notes_are_present_and_each_names_its_source_file(client):
    """Provenance is per-VALUE and durable, which is better than a run-level flag.

    Every proposal cites a note, and the note carries the source's own words
    prefixed by the FILE and the LINE they were read from — so a reader meeting
    it later can say which file supports which value.

    **THE EQUALITY `len(rows) == counts["sent"]` WAS PINNED HERE AND IS NOW AN
    IDENTITY OVER TWO PRODUCERS, 2026-09-17 (`DEC-43`, `CTX-002`).** The batch
    additionally OFFERS the one nominal value in this programme —
    ``context.temperature_K = 298`` for the BL15-2 Angel profile — as a proposal per
    created run, and a nominal offer is deliberately NOT in ``counts``: nothing read
    it from any source, so it is not a candidate and counting it as one would break
    the sum identity ``test_historical_import_routes.py`` asserts over that block.
    The count is therefore taken from BOTH published lists rather than relaxed to an
    inequality — a relaxed assertion here would no longer catch a proposal nothing
    accounted for, which is what this line exists to catch.

    The per-source assertions below run over the CANDIDATE proposals only, because a
    nominal offer cites no source file — that is the whole of `DEC-43` — and its own
    provenance is asserted in ``test_extended_context_wiring.py``.
    """
    import_id = _imported(client)
    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)
    assert body["counts"]["sent"] > 0

    proposals = client.get(f"/api/experiments/{eid}/proposals")
    assert proposals.status_code == 200, proposals.text
    rows = proposals.json()["proposals"]
    nominal_ids = {row["proposal_id"] for row in body["nominal_offers"]}
    assert len(rows) == body["counts"]["sent"] + len(nominal_ids), (
        len(rows),
        body["counts"],
        len(nominal_ids),
    )
    rows = [row for row in rows if row["proposal_id"] not in nominal_ids]

    notes = client.get(f"/api/experiments/{eid}/notes")
    assert notes.status_code == 200, notes.text
    note_text = {row["id"]: row["text"] for row in notes.json()["notes"]}
    assert note_text

    archive_paths = set(EXPECTED_FILES)
    for proposal in rows:
        assert proposal["state"] == "open"
        text = note_text[proposal["note_id"]]
        # THE NOTE NAMES THE SOURCE IT WAS READ FROM, and it names it twice over:
        # the ARCHIVE the scientist chose, then the MEMBER path inside it.
        #
        # **THIS ASSERTION FOUND A REAL DEFECT AND IS KEPT IN THE SHAPE THAT
        # FOUND IT.** Before `_import_statement_filename` existed, every one of
        # these notes read `" (01_01_SYN1_… · line 2 header #E): … = …"` — with
        # NOTHING before the bracket — because both routes resolved the filename
        # from a `source_id` on the statement, which `bl15.reconstruct` does not
        # put there. A test asserting only "the note mentions a file" would have
        # passed on that: the member path was always in the locator.
        prefix, bracket, remainder = text.partition(" (")
        assert bracket, text
        assert prefix == "BL15-2 corpus", text
        member, separator, _locator = remainder.partition(" · ")
        assert separator, text
        assert member in archive_paths, text
        assert "): " in remainder, text

    # EVERY RUN-SCOPED PROPOSAL IS ON A RUN THIS BATCH CREATED, and it is the run
    # of the measurement the value was read from — not all of them on one run.
    run_ids = {run.id for run in ws.load_experiment(eid).runs}
    run_scoped = [p for p in rows if p["run_id"] is not None]
    assert run_scoped, rows
    assert {p["run_id"] for p in run_scoped} <= run_ids
    assert len({p["run_id"] for p in run_scoped}) > 1, (
        "every run-scoped proposal landed on one run, so the per-measurement "
        "routing is not doing anything"
    )


def test_alignment_is_never_a_run_and_its_values_are_reported_not_dropped(client):
    """Alignment and standards are NOT run candidates. Never create a Run from one.

    ``MeasurementUnit.run_candidate`` is DERIVED from the classification, so a
    scientist who disagrees changes the classification — a separate act — and
    nothing is discarded either way.

    MUTATION: adding ``alignment`` to
    ``bl15.evidence.RUN_CANDIDATE_SOURCE_TYPES`` makes this RED.
    """
    import_id = _imported(client)
    view = _view(client, import_id)
    units = _units(view)

    # It IS a measurement — fully assembled, with its own candidates — and it is
    # NOT offered as a Run.
    assert ALIGNMENT_STEM in units
    assert units[ALIGNMENT_STEM]["run_candidate"] is False
    assert units[ALIGNMENT_STEM]["candidate_ids"], units[ALIGNMENT_STEM]
    for stem in EXPECTED_RUN_STEMS:
        assert units[stem]["run_candidate"] is True, stem

    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)
    assert {row["stem"] for row in body["created_runs"]} == set(EXPECTED_RUN_STEMS)
    assert ALIGNMENT_STEM not in {row["stem"] for row in body["created_runs"]}

    # ITS VALUES ARE REPORTED WITH A REASON, never silently dropped.
    orphaned = [row for row in body["not_sent"] if row["error"] == "no_run_for_this_candidate"]
    assert orphaned, body["not_sent"]
    assert any(
        row["reason"] == hist_reason
        for row in orphaned
        for hist_reason in (
            _routes_reason("_IMPORT_CANDIDATE_UNIT_IS_NOT_A_RUN"),
            _routes_reason("_IMPORT_CANDIDATE_IS_BEAMTIME_SCOPE"),
        )
    ), orphaned


def _routes_reason(name: str) -> str:
    import isaac_api.routes as routes

    return getattr(routes, name)


def test_create_runs_and_run_id_together_are_refused(client):
    """Two different answers to the same question; neither may silently win."""
    import_id = _imported(client)
    eid = _record(client)
    created = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "by hand"},
        headers={"If-Match": _etag(client, eid)},
    )
    # 201, measured rather than assumed: the first version of this asserted 200.
    assert created.status_code == 201, created.text
    run_id = created.json()["run"]["id"]

    response = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "run_id": run_id, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "run_id_and_create_runs"
    # NOTHING WAS WRITTEN: the record still holds only the run added by hand.
    assert len(ws.load_experiment(eid).runs) == 1


def test_create_runs_is_refused_on_a_bundle_with_no_archive(client):
    """A bundle of pointers and example sources describes files, not measurements."""
    created = client.post("/api/imports", json={"label": "pointers only"})
    import_id = created.json()["import"]["import_id"]
    added = client.post(
        f"/api/imports/{import_id}/sources",
        json={
            "kind": "reference",
            "filename": "scan_0012.mac",
            "reference": "/nfs/fake-beamline/2019/scan_0012.mac",
        },
    )
    assert added.status_code == 200, added.text
    eid = _record(client)

    response = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] in {
        "no_archive_in_this_import",
        "nothing_to_send",
    }
    assert ws.load_experiment(eid).runs == []


def test_create_runs_must_be_a_boolean_and_is_never_coerced(client):
    """A truthy string would create runs for a caller that sent `"false"`."""
    import_id = _imported(client)
    eid = _record(client)
    response = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": "yes"},
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_create_runs"
    assert ws.load_experiment(eid).runs == []


def test_running_the_batch_twice_creates_no_second_set_of_runs(client):
    """Exactly-once per measurement, so a second batch doubles nothing.

    ── THE NAME WAS RIGHT AND THE ASSERTIONS WERE WRONG, FIXED 2026-09-16 ─────

    This test used to assert the OPPOSITE of its own name: ``runs_created == 4``
    on the second call and ``len(runs) == 8``. Its docstring argued the position
    honestly — a run had no dedupe key, so re-running created more — and
    independent review measured what that meant in practice: the second batch's
    four runs carried **not one proposal**, because every proposal deduplicated
    onto the FIRST set. So a double-click on a 94-measurement archive left 188
    runs, 94 of them empty, while this operation's own published description
    promised that running it twice "adds nothing".

    **The description's promise was the right one, so the behaviour moved to meet
    it.** The key is the run LABEL, which ``historical_import`` derives
    deterministically from the measurement stem — the same key twice for the same
    measurement, and not an identity this route invents.

    Worth recording: a test whose NAME states a guarantee while its body asserts
    the inverse is how this survived. A reader checking "is the batch idempotent
    with respect to runs?" by grepping test names would have read the guarantee.
    """
    import_id = _imported(client)
    eid = _record(client)
    first = _add_to_experiment(client, import_id, eid, create_runs=True)
    assert first["counts"]["runs_created"] == 4
    assert first["counts"]["runs_already_present"] == 0
    first_ids = {run.id for run in ws.load_experiment(eid).runs}
    assert len(first_ids) == 4

    second = _add_to_experiment(client, import_id, eid, create_runs=True)
    # EVERY CANDIDATE IS ALREADY SENT, and no second proposal is minted.
    assert second["counts"]["sent"] == 0, second["counts"]
    assert second["counts"]["already_sent"] == first["counts"]["sent"]

    # AND NO SECOND SET OF RUNS — which is what the name has always said.
    assert second["counts"]["runs_created"] == 0, second["counts"]
    assert second["created_runs"] == []
    assert len(ws.load_experiment(eid).runs) == 4
    assert {run.id for run in ws.load_experiment(eid).runs} == first_ids

    # THE ALREADY-PRESENT ONES ARE REPORTED, NOT SILENTLY SKIPPED. A batch that
    # created nothing because everything was already there is a different
    # outcome from one that created nothing because there was nothing to create,
    # and the response distinguishes them.
    assert second["counts"]["runs_already_present"] == 4
    assert {row["run_id"] for row in second["runs_already_present"]} == first_ids
    for row in second["runs_already_present"]:
        assert row["stem"] and row["label"] and row["ordinal"]

    # NEGATIVE CONTROL for the whole guarantee: the labels really are the key, so
    # a run whose label no measurement produces is untouched by a batch.
    exp = ws.load_experiment(eid)
    assert len({run.label for run in exp.runs}) == 4, "labels are not unique"


def test_a_default_deployment_still_stops_at_the_proposal(client):
    """Acceptance answers `409 human_actor_required` in every shipped deployment.

    A CONFIGURATION fact, not a build defect: no trusted authentication boundary
    exists in this build, and no application change can close it. The chain
    stopping at an open proposal is the design.
    """
    import_id = _imported(client)
    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)
    proposal_id = body["sent"][0]["proposal_id"]

    response = client.post(
        f"/api/experiments/{eid}/proposals/{proposal_id}/review",
        json={"action": "accept", "accepted_from": "candidate", "confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "human_actor_required"


# --- the last leg: review -> draft -> deterministic validation ----------------


def test_the_whole_walk_ends_in_a_deterministically_validated_draft(armed_client):
    """THE DELIVERABLE: a real archive, through review, into the truth core.

    Run under the fixture edge verifier, which is the only configuration in which
    a person can accept anything — see the test above for why that is a
    configuration fact rather than a gap.

    The value that lands is the SOURCE's, accepted by a PERSON, carrying the
    user-confirmation evidence the writer manual entry uses mints — not anything
    the import wrote.
    """
    client = armed_client
    import_id = _imported(client)
    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)

    run_scoped = [
        row
        for row in body["sent"]
        if row["target_field_path"] == RUN_TARGET_PATH and row["run_id"]
    ]
    assert run_scoped, body["sent"]
    chosen = run_scoped[0]

    accepted = client.post(
        f"/api/experiments/{eid}/proposals/{chosen['proposal_id']}/review",
        json={"action": "accept", "accepted_from": "candidate", "confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["proposal"]["state"] == "accepted"

    # THE RUN'S OWN DRAFT NOW HOLDS THE VALUE, with evidence.
    exp = ws.load_experiment(eid)
    run = exp.get_run(chosen["run_id"])
    assert run is not None
    envelope = (run.draft or {}).get("fields", {}).get(RUN_TARGET_PATH)
    assert envelope is not None, run.draft
    assert envelope["value"], envelope
    assert envelope["status"] == "verified"
    assert envelope["evidence"], envelope
    # THE EVIDENCE IS A USER CONFIRMATION — minted by the writer manual entry
    # uses, not by anything in the import path, which mints none.
    assert envelope["evidence"][0]["source_type"] == "user_confirmation"

    # DETERMINISTIC VALIDATION over the run's resolved draft — the truth core,
    # unmodified.
    from isaac_records.draft_validator import validate_draft

    resolved = exp.resolved_run_draft(run)
    report = validate_draft(resolved)
    offending = [issue for issue in report.errors if RUN_TARGET_PATH in str(issue)]
    assert offending == [], offending

    # AND THE RECORD IS STILL NOT EXPORT-READY, for the three measured reasons the
    # digest already stated. This is the correct outcome and the surface says so
    # rather than showing a progress bar that can never fill.
    assert report.errors != [] or exp.pending_count() > 0, (
        "a historical import produced an export-ready record, which contradicts "
        "the three blockers the corpus digest publishes"
    )


# --- the gold-standard harness ------------------------------------------------


def _harness_candidate(candidate: dict, cited_literals: list[str], concept: str):
    """``(determinism, normalization_rule)`` for the harness. MEASURED, not asserted.

    **THE THIRD BRANCH IS THE ONE THAT KEEPS THE METRIC HONEST.**

    * the proposed value IS one of the cited literals -> ``read``;
    * else the MAPPING REGISTRY names a stored rule for this concept ->
      ``normalized``, citing it. The harness then refuses any name the gold
      standard does not declare, so this cannot legitimise an arbitrary
      transformation;
    * else -> ``read``, which the harness will score as FABRICATED. Deliberate: a
      value no source states and no named rule explains is exactly what this
      metric exists to catch, and an adapter that quietly reclassified it would
      be measuring itself.

    **THE RULE NAME COMES FROM ``bl15.mapping``, AND THAT IS THE GOLD STANDARD'S
    OWN INSTRUCTION rather than a convenience.** Its
    ``declared_normalization_rules`` comment says the entries are *"`bl15.mapping`'s
    own rule names, quoted so the gold standard and the registry cannot drift
    apart"*. Two vocabularies exist and only one of them is the harness's:

    * ``ConceptMapping.rule`` — ``unix_epoch_seconds_to_iso8601_utc``,
      ``millivolts_to_volts_and_p_as_decimal_point``. THESE are what the gold
      standard declares.
    * ``SourceEvidence.normalization_rule`` — an id plus a paragraph, e.g.
      ``bl15.spec.epoch_to_utc_iso.v1: ``#E`` states a Unix epoch…``. **Measured:
      not one of these appears in the gold standard's list**, so an adapter that
      took the rule name from the reader's prose scores every normalised
      candidate as fabricated. The first version of this function did exactly
      that and produced ``0.53``.

    **ONE NAMED WIRE GAP REMAINS, recorded rather than papered over.**
    ``SemanticCandidate`` carries no ``concept``, so it is read off the first
    supporting statement's ``key`` — which is exact, because
    ``bl15.reconstruct.statement_for`` sets ``key = concept``, and which is
    nonetheless a join a consumer should not have to make. Serving the concept on
    the candidate is the fix; the report names it.
    """
    from isaac_api.bl15 import evaluate as ev
    from isaac_api.bl15 import mapping as mp

    value = candidate["proposed_value"]
    if any(str(literal) == str(value) for literal in cited_literals):
        return ev.DETERMINISM_READ, None
    entry = mp.mapping_for(concept)
    if entry is not None and entry.rule:
        return ev.DETERMINISM_NORMALIZED, entry.rule
    return ev.DETERMINISM_READ, None


def test_the_walk_fabricates_no_value_and_every_candidate_names_its_evidence(client):
    """``HIST-006``'s two HARD metrics, over this walk's own output.

    ``fabricated_value_rate`` must be 0 and ``provenance_coverage`` must be 1.0,
    or the slice is not done. The gold standard is a committed, human-authored
    document that ``load_gold_standard`` REFUSES if it declares itself derived
    from parser output — a parser that scores itself is measuring nothing.

    The harness is handed the values the PRODUCT served, read off the session
    view over HTTP. It is not handed a reader's output.

    **WHICH CANDIDATES ARE SCORED, AND WHY THE EXCLUSION IS NOT A LOOPHOLE.**
    ``CandidateValue`` is *"ONE value a reconstruction proposes"*, so the set
    scored here is every candidate that PROPOSES ONE. A candidate with
    ``proposed_value: null`` proposes nothing and cannot have fabricated it —
    that is the conflicted ones (no winner is chosen, by design) and the ones
    whose concept has no proposable mapping (39 of 45). Those are not dropped
    from the walk: ``test_proof_4`` and ``test_proof_5`` assert that each carries
    every reading and the registry's own reason. The count of both sets is
    asserted below, so a future change that silently emptied the scored set would
    fail here rather than reporting a rate of zero over nothing.
    """
    from isaac_api.bl15 import evaluate as ev

    gold = ev.load_gold_standard(
        ev.GOLD_DIR / "bl15-mini-synthetic-v1.gold.json"
    )

    import_id = _imported(client)
    view = _view(client, import_id)
    rows = _manifest_rows(view)

    candidates: list[ev.CandidateValue] = []
    evidence: list[dict] = []
    valueless = 0
    for candidate in _candidates(view):
        # A candidate's CONCEPT is the key its statements carry — `statement_for`
        # sets `EvidenceStatement.key = concept` — so it is read off the payload
        # rather than parsed out of the candidate id.
        statements = candidate["supporting_statements"]
        if not statements:
            continue
        concept = statements[0]["key"]
        if concept not in ev.CONCEPTS:
            continue
        if candidate["proposed_value"] is None:
            valueless += 1
            continue
        ids = []
        literals: list[str] = []
        for index, statement in enumerate(statements):
            eid_ = f"{candidate['candidate_id']}#{index}"
            ids.append(eid_)
            literals.append(statement["value"])
            path, _, locator = statement["locator"].partition(" · ")
            evidence.append(
                {
                    "evidence_id": eid_,
                    "source_path": path,
                    "locator": locator,
                    "raw_literal": statement["value"],
                    "concept": concept,
                }
            )
        determinism, rule_name = _harness_candidate(candidate, literals, concept)
        candidates.append(
            ev.CandidateValue(
                candidate_id=candidate["candidate_id"],
                concept=concept,
                value=candidate["proposed_value"],
                determinism=determinism,
                normalization_rule=rule_name,
                evidence_ids=tuple(ids),
                official_path=candidate["target_field_path"],
            )
        )

    # BOTH SETS ARE NON-EMPTY AND ARE COUNTED. A rate of 0 over an empty set is
    # not a measurement, and this is the assertion that says so.
    assert len(candidates) >= 10, len(candidates)
    assert valueless >= 10, valueless

    # --- EVERY OTHER `Observed` FIELD THE SERVED PAYLOAD CAN SUPPLY -----------
    #
    # `Observed` defaults every field to `None`, and `None` means "no producer
    # ran" — the metric then reports UNMEASURABLE rather than a zero, because an
    # unbuilt layer must not read the same as a broken one. So leaving a field
    # absent is a claim too, and each one below is populated from what the SERVER
    # served rather than left to report a non-answer.
    #
    # THREE ARE LEFT ABSENT DELIBERATELY, and each is named: `conflicts` and
    # `links` because the gold standard names them in ITS OWN vocabulary
    # (`duplicate_legacy_number:03`, `replica_of`) which no wire field carries,
    # so an adapter would be INVENTING a translation between a human's names and
    # the product's — the exact conflict of interest this harness exists to
    # prevent; and `inherited_beamtime_context`, because this corpus's
    # `readme.txt` yields no evidence at all (see the finding in this file's
    # report) and populating it would report a real gap as an empty measurement.
    filename_tokens: dict[str, dict] = {}
    unknown_tokens: dict[str, list[str]] = {}
    technique = None
    for candidate in _candidates(view):
        for statement in candidate["supporting_statements"]:
            path, _, locator = statement["locator"].partition(" · ")
            if locator.startswith("filename"):
                filename_tokens.setdefault(path, {})[statement["key"]] = statement[
                    "value"
                ]
            if statement["key"] == "unknown_token":
                unknown_tokens.setdefault(path, []).append(statement["value"])
        if (
            candidate["target_field_path"] == RECORD_TARGET_PATH
            and candidate["proposed_value"] is not None
            and technique is None
        ):
            technique = {
                "official_path": candidate["target_field_path"],
                "value": candidate["proposed_value"],
            }

    # DUPLICATE GROUPS, derived from the manifest's own member digests. They are
    # not served as groups — `ArchiveInventory.to_state()` publishes only a COUNT
    # — so this rebuilds them from the digests beside each row, which is the same
    # identity the walk grouped on.
    by_digest: dict[str, list[str]] = {}
    for path, row in rows.items():
        by_digest.setdefault(row["content_sha256"], []).append(path)
    duplicate_groups = tuple(
        tuple(sorted(paths)) for paths in by_digest.values() if len(paths) > 1
    )
    assert len(duplicate_groups) == view["corpus_digest"]["duplicate_group_count"], (
        "the groups rebuilt from the served digests disagree with the count the "
        "server published"
    )

    measurement_groups = {
        unit["stem"]: tuple(scan["path"] for scan in unit["scans"])
        for unit in view["archive"]["relationships"]["units"]
    }

    # The concepts the import's SHARED candidates carry. Read off each statement's
    # `key`, which `reconstruct.statement_for` sets to the concept — so this is the
    # server's own label, not a second vocabulary.
    shared_ids = set(view["archive"]["shared_candidate_ids"])
    # THE CONCEPTS THE README CONTRIBUTES, not every beamtime-scope concept. Selected by
    # the statement's own LOCATOR, which carries the archive path — so this is derived
    # from the served payload and not from the gold standard.
    #
    # The distinction is real and the first version of this got it wrong: the notes
    # document ALSO states things at beamtime scope (an acquisition method, a medium), so
    # the shared set is legitimately wider than the README's contribution, and this
    # metric is about the README. The metric caught it — it reported 0.0 with
    # `acquisition_method` among the concepts it did not expect.
    readme_concepts = sorted(
        {
            statement["key"]
            for candidate in _candidates(view)
            if candidate["candidate_id"] in shared_ids
            for statement in candidate["supporting_statements"]
            if "readme" in statement["locator"].lower()
        }
    )

    observed = ev.Observed(
        source_classification={
            path: row["source_type"] for path, row in rows.items()
        },
        candidates=tuple(candidates),
        evidence=tuple(evidence),
        filename_tokens=filename_tokens,
        measurement_groups=measurement_groups,
        duplicate_groups=duplicate_groups,
        unknown_tokens={path: tuple(t) for path, t in unknown_tokens.items()},
        technique=technique,
        run_sources=tuple(
            {
                "run_id": unit["stem"],
                "source_path": unit["acquisition_path"],
                "source_type": unit["source_type"],
            }
            for unit in _units(view).values()
            if unit["run_candidate"]
        ),
        # README INHERITANCE, SUPPLIED FOR THE FIRST TIME 2026-09-16.
        #
        # This was deliberately omitted and the metric went UNMEASURABLE, because the
        # mini corpus's `readme.txt` used a format `read_shared_readme` does not
        # recognise — it produced ZERO evidence, so the gold standard's
        # `readme_inheritance` expectation was unmeetable by any reader in this build.
        # Independent review found it, and the fixture was the thing that was wrong: the
        # reader's grammar was validated against the real archive's file and the
        # fixture's was validated against nothing. The fixture is rewritten; this now
        # supplies the observation.
        #
        # **IT IS DERIVED FROM THE SERVED PAYLOAD, NOT FROM THE GOLD STANDARD**, which is
        # the whole reason it is worth supplying. `test_bl15_evaluate.py`'s own
        # `_perfect(gold)` builds this member FROM `gold.readme_inheritance`, so the
        # harness test asserts 1.0 against an observation constructed from the
        # expectation — legitimate for testing the harness, and it means nothing
        # confronted the gold standard with a real reading until now.
        #
        # Every run candidate inherits every beamtime-scope concept: that IS what
        # inheritance means here, and `reconstruct` selects shared candidates by the
        # reading's own scope rather than by which file it came from.
        #
        # EVERY UNIT, not only the run candidates — which the metric also caught. An
        # alignment acquisition inherits the beamtime's own context exactly as a sample
        # measurement does; whether it may become a Run is a different question, and the
        # gold standard expects all five units for that reason.
        inherited_beamtime_context={
            unit["stem"]: tuple(readme_concepts)
            for unit in _units(view).values()
        },
    )
    report = ev.evaluate(gold, observed)
    by_id = report.by_id()

    fabricated = by_id[ev.METRIC_FABRICATED_VALUE_RATE]
    assert fabricated.outcome == ev.MEASURED, fabricated
    assert fabricated.value == 0, fabricated
    assert fabricated.passed is True, fabricated

    provenance = by_id[ev.METRIC_PROVENANCE_COVERAGE]
    assert provenance.outcome == ev.MEASURED, provenance
    assert provenance.value == 1.0, provenance
    assert provenance.passed is True, provenance

    # THE THIRD HONESTY METRIC, which the two above do not cover: a mapping the
    # reconstruction was CONFIDENT about and got wrong.
    incorrect = by_id[ev.METRIC_INCORRECT_CONFIDENT_MAPPING_RATE]
    assert incorrect.outcome == ev.MEASURED, incorrect
    assert incorrect.value == 0, incorrect
    assert incorrect.passed is True, incorrect

    # AND NO HARD REQUIREMENT FAILED OR WENT UNMEASURABLE. `report.passed` is
    # False when a hard metric could not be COMPUTED as well as when it failed —
    # "we could not check whether anything was invented" must never read the same
    # as "nothing was invented".
    assert report.hard_failures == (), report.hard_failures
    assert report.passed is True, [
        (m.metric_id, m.outcome, m.passed) for m in report.metrics
    ]

    # EVERY OTHER METRIC THE SERVED PAYLOAD CAN FEED IS MEASURED, and each is
    # asserted so a future change that emptied one would report UNMEASURABLE
    # here rather than quietly reducing the harness to three numbers.
    for metric_id in (
        ev.METRIC_SOURCE_CLASSIFICATION,
        ev.METRIC_FILENAME_TOKENS,
        ev.METRIC_LEGACY_NUMBER,
        ev.METRIC_POTENTIAL_MAGNITUDE,
        ev.METRIC_FILTER,
        ev.METRIC_CYCLING_STATE,
        ev.METRIC_SCAN_GROUPING,
        ev.METRIC_DUPLICATE_RECOGNITION,
        ev.METRIC_UNKNOWN_TOKEN_PRESERVATION,
        # ADDED 2026-09-16. This metric was UNMEASURABLE in this walk, and the reason
        # was a fixture defect rather than a design choice: the mini corpus's
        # `readme.txt` used a format `read_shared_readme` does not recognise, so it
        # produced zero evidence and the gold standard's expectation was unmeetable by
        # any reader in this build. Found by independent review. The fixture is rewritten
        # in the format the reader spec declares the real archive uses, and the
        # observation is now DERIVED FROM THE SERVED PAYLOAD — which matters, because
        # `test_bl15_evaluate.py`'s `_perfect(gold)` builds this member from the
        # expectation itself, so until now nothing confronted the gold standard with a
        # real reading of a README.
        ev.METRIC_README_INHERITANCE,
    ):
        result = by_id[metric_id]
        assert result.outcome == ev.MEASURED, (metric_id, result)
        assert result.value == 1.0, (metric_id, result.detail)
        assert result.missed == 0, (metric_id, result.detail)

    # THE POTENTIAL'S REFERENCE BASIS MUST BE LEFT UNRESOLVED, and the gold
    # standard scores that with the OPPOSITE polarity to every other token: no
    # source in this corpus states what the potential is measured against, the
    # official schema's answer to that is vocabulary for absence rather than a
    # default, and reporting a basis would be a MISS.
    basis = by_id[ev.METRIC_POTENTIAL_REFERENCE]
    assert basis.outcome == ev.MEASURED, basis
    assert basis.value == 1.0, basis.detail


# --- negative control ---------------------------------------------------------


def test_the_technique_mapping_IS_NOW_DEFERRED_TO_A_SCIENTIST(client):
    """WAS a measured miss; the registry was corrected and this is the inversion.

    ── HISTORY, KEPT BECAUSE THE DEFECT IS THE INSTRUCTIVE PART ────────────────

    This test was written to pin a miss it could not fix, and it did its job: the
    registry was corrected within the hour and this test went red, exactly as its
    own last paragraph predicted. It is INVERTED rather than deleted, which is
    this repository's established remedy for a test that pinned a defect.

    **The original finding.** The gold standard declares ``system.technique``
    should be ``HERFD-XAS``. What the reconstruction proposed was **the macro's
    filename**, because ``bl15.mapping`` mapped the ``acquisition_method`` concept
    to ``system.technique`` with status ``deterministic``.

    **Why the honesty metrics were right to pass anyway**, which is the subtle
    part: ``fabricated_value_rate`` was 0 and stayed 0, because the value WAS
    evidenced — a source literally says that filename, at a named locator. Nothing
    was invented. What was wrong was the MAPPING, and a mapping error is not a
    fabrication. A suite that only checked for fabrication would never have seen
    it.

    **What the correction rests on**, measured rather than reasoned: this concept
    carries the macro's own name from a macro, and a lowercase alias reading from
    a filename, and **not one of those is a member of the schema's technique
    enum** — so the old status proposed an off-enum value from every source. One
    of those aliases is a DETECTION MODE, which the enum has no member for and
    which is not a technique at all.

    Below: the technique candidate still EXISTS and still carries its readings, and
    it proposes nothing.
    """
    from isaac_api.bl15 import evaluate as ev
    from isaac_api.bl15 import mapping as mp

    import_id = _imported(client)
    view = _view(client, import_id)

    # THE RATCHET FIRED AND THE REGISTRY WAS CORRECTED. What follows is the
    # inverted assertion: no value is proposed at this path at all, and the
    # candidate that WOULD have carried one now carries the registry's reason.
    entry = mp.MAPPINGS["acquisition_method"]
    assert entry.status == mp.STATUS_NEEDS_DOMAIN_REVIEW
    assert not entry.proposable
    assert entry.official_path == RECORD_TARGET_PATH

    at_path = [
        candidate
        for candidate in _candidates(view)
        if candidate["target_field_path"] == RECORD_TARGET_PATH
    ]
    assert at_path, "the technique candidate vanished entirely, which loses evidence"

    # NOT PROPOSABLE, AND CARRYING NO VALUE — the two together are the fix. A
    # candidate that kept its value while being unproposable would still be a
    # macro filename sitting at a schema path, one surface away from a record.
    for candidate in at_path:
        assert candidate["proposed_value"] is None, candidate
        assert candidate["proposable"] is False, candidate
        assert candidate["not_proposable_reason"], candidate

    # The evidence still survives in full — the point of deferring rather than
    # dropping. The macro's own name is still readable at its locator.
    literals = {
        statement["value"]
        for candidate in at_path
        for statement in candidate["supporting_statements"]
    }
    assert literals, "the readings behind the deferred candidate were dropped"

    # And the enum members a scientist chooses between are named, so the domain
    # question is answerable in one word.
    assert "HERFD-XAS" in (entry.allowed_values or ())
    assert ev.METRIC_TECHNIQUE_MAPPING == "technique_mapping"


def test_nothing_in_this_file_borrows_a_reconstruction():
    """NEGATIVE CONTROL for this file's own premise.

    Its whole value is that its expectations were WRITTEN OUT. A future edit that
    reached for ``bl15.archive``, ``bl15.classify``, ``bl15.relate``,
    ``bl15.reconstruct`` or a reader to discover what the answer is would restore
    exactly the blind spot ``CLAUDE.md`` §11 records — a suite that begins past
    the part that does not work, and agrees with itself by construction.

    PARSED, not grepped, for ``test_scientist_can_finish_a_record.py``'s reason:
    the first version of that guard tripped on its own docstring, which is a
    guard failing to tell talking about a thing from doing it.
    """
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    # THIS FUNCTION IS EXCLUDED FROM ITS OWN SCAN, by name so a rename cannot
    # silently widen the hole: it has to name the modules it forbids in order to
    # look for them.
    tree.body = [
        node
        for node in tree.body
        if not (
            isinstance(node, ast.FunctionDef)
            and node.name == "test_nothing_in_this_file_borrows_a_reconstruction"
        )
    ]
    forbidden = {
        "archive",
        "classify",
        "relate",
        "reconstruct",
        "spec",
        "scans",
        "macros",
        "notes",
        "filenames",
        "inventory",
        "profiles",
    }
    used: list[str] = []
    for node in ast.walk(tree):
        # `from isaac_api.bl15 import <reader>` — the shape that would let this
        # file ask the reading layer what it had read.
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "isaac_api.bl15"
        ):
            for alias in node.names:
                if alias.name in forbidden:
                    used.append(f"{node.module}.{alias.name}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                tail = alias.name.rsplit(".", 1)[-1]
                if alias.name.startswith("isaac_api.bl15") and tail in forbidden:
                    used.append(alias.name)
    assert used == [], f"this file borrowed the reading layer: {sorted(set(used))}"

    # AND IT MUST ACTUALLY BE CAPABLE OF FAILING. `mapping` and `evaluate` ARE
    # imported here and are deliberately allowed — the registry is the schema
    # mapping's one definition, and the harness's ground truth is a committed
    # human-authored document it refuses if it says otherwise. So the guard is
    # proven live by confirming it would catch a reader import written the same
    # way those two are.
    sample = ast.parse("from isaac_api.bl15 import relate as R")
    assert any(
        isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("isaac_api.bl15")
        and any(alias.name in forbidden for alias in node.names)
        for node in ast.walk(sample)
    ), "the guard's own predicate does not match the shape it forbids"


def test_the_run_that_inherits_the_records_existing_answers_is_NAMED(client):
    """AN ASSOCIATION CLAIM, DISCLOSED. Independent review found it undisclosed.

    ``_seed_for_new_run`` gives the FIRST run of a record the run-level content the
    record already held — a spectrum, a QC verdict — because otherwise adding a run
    silently drops answers a person entered. For ``POST /runs`` that is
    unobjectionable: a human chose that run.

    **Here the batch creates several at once, so the inheriting one is whichever
    measurement `relate` ordered first** — and the record's measured spectrum then
    claims to be a measurement of THAT acquisition, an association nothing evidenced.
    The inheritance is kept (passing ``{}`` reintroduces the measured data-loss defect
    the seeder exists to close, and another test proves nothing from the archive
    reaches any draft); what was missing was that the response said nothing about it.

    At most ONE row per batch can carry the flag, because the seeder's asymmetry keys
    on whether the record has runs yet.
    """
    import_id = _imported(client)
    eid = _record(client)
    body = _add_to_experiment(client, import_id, eid, create_runs=True)
    rows = body["created_runs"]
    assert rows

    # EVERY ROW CARRIES THE KEY, so absence is never ambiguous with false.
    for row in rows:
        assert "inherited_record_level_content" in row, row
        assert isinstance(row["inherited_record_level_content"], bool)

    # AT MOST ONE, and it can only be the first — asserted over the ordinals rather
    # than over list position, because the response order is not the contract.
    inheriting = [r for r in rows if r["inherited_record_level_content"]]
    assert len(inheriting) <= 1, inheriting
    for row in inheriting:
        assert row["ordinal"] == min(r["ordinal"] for r in rows), row

    # AND THE FLAG IS DERIVED FROM THE DRAFT THAT WAS ACTUALLY WRITTEN, not from
    # "this is the first row" — a positional flag would keep reading `true` on a
    # record that had nothing to inherit.
    exp = ws.load_experiment(eid)
    by_id = {run.id: run for run in exp.runs}
    for row in rows:
        draft = by_id[row["run_id"]].draft
        carries = bool(draft.get("fields") or draft.get("blocks"))
        assert row["inherited_record_level_content"] == carries, row
