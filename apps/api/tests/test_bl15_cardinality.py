"""PER-SCAN VARIATION IS NOT A DISAGREEMENT — `bl15.mapping.RULE_CARDINALITY` (2026-09-22).

THE DEFECT THIS EXISTS FOR, MEASURED ON THE SYNTHETIC MULTI-OPERATOR CORPUS: of 43
"field disagreements" the reconstruction reported, **36 were not disagreements at all**.
Different SCANS of one measurement legitimately state different values — each scan
export names its own scan index (`acquisition_target`), a `#L` line lists several
detector columns (`detector_column`), a `#P` line gives several motors' positions
(`motor_position`), and each scan file's name carries its own index token
(`unknown_token`) — and every one of those was presented to a scientist as "the sources
disagree about this". Worse, `acquisition_target` reached the screen as a Python dict
repr: `{'measurement_stem': '01_01_…', 'scan_index': 1}`.

THE RULE: a concept has a CARDINALITY in the registry, stated per concept and never
guessed. Readings of a `per_scan` concept are compared only with other readings of the
SAME scan (and, for `per_scan_item`, the same column or motor within it); a `per_source`
concept only within one file. Values that differ across scans are preserved as
per-scan readings, not a conflict. A genuine disagreement — two sources about the same
scan, or a per-measurement concept that truly disagrees — is still a conflict, and the
tests below prove each half.

Every value is synthetic (`ZZ` samples, the committed fixtures).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

import pytest
from fastapi.testclient import TestClient

import isaac_api.capabilities as capabilities
import isaac_api.historical_import as hist
import isaac_api.identity as identity
from isaac_api.bl15 import evidence as ev
from isaac_api.bl15 import mapping as mp
from isaac_api.bl15 import reconstruct as rc

SEMANTICS = "tests/fixtures/bl15/semantics/multi_operator_corpus"
ARCHIVE = "bl15_synthetic_semantics_corpus"
MINI = "bl15_synthetic_mini_corpus"


# --- the registry --------------------------------------------------------------


def test_the_cardinality_rule_is_named_versioned_and_stated_per_concept():
    # v2 (2026-09-23): the meaning changed — scans are established only by a source's
    # own `#S`, and every measurement-level reading is compared with every scan's.
    assert mp.RULE_CARDINALITY.startswith("bl15.mapping.cardinality.v2:")
    assert set(mp.CONCEPT_CARDINALITY.values()) <= mp.CARDINALITIES
    for concept in mp.CONCEPT_CARDINALITY:
        assert concept in ev.CONCEPTS, concept
    assert mp.cardinality_for(ev.CONCEPT_ACQUISITION_TARGET) == mp.CARDINALITY_PER_SCAN
    assert mp.cardinality_for(ev.CONCEPT_DETECTOR_COLUMN) == mp.CARDINALITY_PER_SCAN_ITEM
    assert mp.cardinality_for(ev.CONCEPT_MOTOR_POSITION) == mp.CARDINALITY_PER_SCAN_ITEM
    assert mp.cardinality_for(ev.CONCEPT_UNKNOWN_TOKEN) == mp.CARDINALITY_PER_SOURCE
    # ANYTHING NOT DECLARED IS ONE VALUE PER MEASUREMENT — the conservative default,
    # because comparing everything is what can never hide a disagreement.
    assert mp.cardinality_for(ev.CONCEPT_SAMPLE_NAME) == mp.CARDINALITY_PER_MEASUREMENT


def test_four_scan_stated_quantities_were_reverted_to_per_measurement_pending_Q21():
    """v1 declared them per scan; a macro's planned value and the header's recorded
    value for the SAME, only scan then read as variation. Reverted until the domain
    owner answers which acquisition quantities vary per scan (Q21)."""
    for concept in (
        ev.CONCEPT_COUNTING_TIME,
        ev.CONCEPT_SCAN_COMMAND,
        ev.CONCEPT_ENERGY_GRID,
        ev.CONCEPT_EMISSION_ENERGY,
    ):
        assert mp.cardinality_for(concept) == mp.CARDINALITY_PER_MEASUREMENT, concept


def test_two_scan_carried_concepts_stay_per_measurement_on_purpose():
    """`filter` and `acquisition_timestamp` are stated per scan too, and are NOT
    per-scan concepts. A filter is a condition of the measurement — a scan header's
    `filter` motor disagreeing with the filename's filter index is a real question —
    and a timestamp feeds `timestamps.acquired_start_utc`, one value per run, where
    choosing between scans' dates is a decision, not a reading."""
    assert mp.cardinality_for(ev.CONCEPT_FILTER) == mp.CARDINALITY_PER_MEASUREMENT
    assert mp.cardinality_for(ev.CONCEPT_ACQUISITION_TIMESTAMP) == mp.CARDINALITY_PER_MEASUREMENT


def test_the_served_registry_carries_each_concepts_cardinality():
    for concept, entry in mp.MAPPINGS.items():
        assert entry.to_state()["cardinality"] == mp.cardinality_for(concept)


# --- the reconstruction, on hand-built evidence ------------------------------------


def _item(concept, literal, *, path, scan=None, item=None, scope=ev.SCOPE_SCAN, n=0,
          normalized=None, source_type=ev.SOURCE_TYPE_SCAN_EXPORT):
    return ev.SourceEvidence(
        evidence_id=f"e{n}-{path}-{literal}",
        source_path=path,
        source_type=source_type,
        locator=f"FAKE locator {n}",
        raw_literal=literal,
        concept=concept,
        parser_id="bl15.test",
        determinism=ev.DETERMINISM_NORMALIZED if normalized is not None else ev.DETERMINISM_READ,
        normalization_rule="bl15.test.rule" if normalized is not None else None,
        normalized_value=normalized,
        scope=scope,
        scan=scan,
        item=item,
    )


def _candidates(items):
    return {
        c.candidate_id.split("::")[-1]: c
        for c in rc._candidates_from_evidence(
            items,
            candidate_prefix="ZZ_unit",
            source_ids={},
            by_concept=defaultdict(int),
            by_status=defaultdict(int),
            unregistered=set(),
        )
    }


SPEC = "ZZ_dir/ZZ_unit"
S1 = "ZZ_dir/ZZ_unit_001.dat"
S2 = "ZZ_dir/ZZ_unit_002.dat"


def test_detector_columns_that_differ_between_scans_are_per_scan_readings_not_a_conflict():
    col = ev.CONCEPT_DETECTOR_COLUMN
    items = [
        _item(col, "I0", path=SPEC, scan="1", item="column 0", source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION),
        _item(col, "vortDT", path=SPEC, scan="1", item="column 1", source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION),
        _item(col, "I0", path=S1, scan="1", item="column 0"),
        _item(col, "vortDT", path=S1, scan="1", item="column 1"),
        _item(col, "I0", path=S2, scan="2", item="column 0"),
        _item(col, "vortDT2", path=S2, scan="2", item="column 1"),
    ]
    candidate = _candidates(items)[col]
    assert candidate.unresolved_reason is None
    assert candidate.disagreement == ()
    assert candidate.agreement == "varies"
    assert candidate.review_status != "sources_conflict"
    assert candidate.variation_basis == mp.CARDINALITY_PER_SCAN_ITEM
    rows = {(r["scan"], r["item"]): r["value"] for r in candidate.variation}
    assert rows == {
        ("1", "column 0"): "I0",
        ("1", "column 1"): "vortDT",
        ("2", "column 0"): "I0",
        ("2", "column 1"): "vortDT2",
    }
    assert candidate.variation_scans == 2


def test_MUTATION_two_sources_disagreeing_about_the_SAME_scan_still_conflict():
    """MUTATION: keying every reading on its scan alone (dropping the item) or on
    nothing at all changes this; keying on the file (so the SPEC file and scan 1's
    export are never compared) turns it GREEN-by-omission — asserted below."""
    col = ev.CONCEPT_DETECTOR_COLUMN
    items = [
        _item(col, "vortDT", path=SPEC, scan="1", item="column 1", source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION),
        _item(col, "vortXX", path=S1, scan="1", item="column 1"),
        _item(col, "vortDT2", path=S2, scan="2", item="column 1"),
    ]
    candidate = _candidates(items)[col]
    assert candidate.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE
    assert candidate.review_status == "sources_conflict"
    # ONLY the readings about the disputed scan are the competing ones — scan 2's
    # different value is its own scan's reading, not a third side of this dispute.
    assert sorted(row["value"] for row in candidate.disagreement) == ["vortDT", "vortXX"]
    assert "same scan" in candidate.rule


def test_acquisition_targets_are_structured_text_never_a_python_repr():
    target = ev.CONCEPT_ACQUISITION_TARGET
    items = [
        _item(target, "ZZ_unit_001.dat", path=S1, scan="1", normalized={"measurement_stem": "ZZ_unit", "scan_index": 1}),
        _item(target, "ZZ_unit_002.dat", path=S2, scan="2", normalized={"measurement_stem": "ZZ_unit", "scan_index": 2}),
    ]
    candidate = _candidates(items)[target]
    assert candidate.unresolved_reason is None
    wire = json.dumps(candidate.to_state())
    assert "{'" not in wire and "':" not in wire
    assert sorted(r["value"] for r in candidate.variation) == ["ZZ_unit · scan 1", "ZZ_unit · scan 2"]
    assert rc.reading_of(items[0]) == "ZZ_unit · scan 1"


def test_a_per_measurement_concept_that_differs_between_scans_is_still_a_conflict():
    """Never suppressed: `filter` is one value per measurement, so two scans stating
    different filters is a disagreement about the measurement."""
    items = [
        _item(ev.CONCEPT_FILTER, "10", path=S1, scan="1", item="filter"),
        _item(ev.CONCEPT_FILTER, "20", path=S2, scan="2", item="filter"),
    ]
    candidate = _candidates(items)[ev.CONCEPT_FILTER]
    assert candidate.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE
    assert candidate.variation == ()


def test_unknown_tokens_are_compared_only_within_one_file():
    token = ev.CONCEPT_UNKNOWN_TOKEN
    items = [
        _item(token, "001", path=S1, scope=ev.SCOPE_MEASUREMENT),
        _item(token, "002", path=S2, scope=ev.SCOPE_MEASUREMENT),
    ]
    candidate = _candidates(items)[token]
    assert candidate.unresolved_reason is None
    assert candidate.variation_basis == mp.CARDINALITY_PER_SOURCE
    assert candidate.agreement == "varies"


def test_variation_survives_the_round_trip_and_is_windowed_with_a_true_total():
    col = ev.CONCEPT_MOTOR_POSITION
    items = [
        _item(col, str(n), path=S1, scan="1", item=f"motor{n}", n=n, normalized=float(n))
        for n in range(hist.MAX_VARIATION_ROWS + 7)
    ]
    candidate = _candidates(items)[col]
    bounded = hist._bound_candidate(candidate, frozenset())
    assert len(bounded.variation) == hist.MAX_VARIATION_ROWS
    assert bounded.variation_total == hist.MAX_VARIATION_ROWS + 7
    again = hist.SemanticCandidate.from_state(bounded.to_state())
    assert again.variation == bounded.variation
    assert again.variation_total == bounded.variation_total
    assert again.agreement == "varies"


# --- v2: what an independent review measured v1 getting wrong (2026-09-23) --------


def test_MUTATION_a_macro_plan_against_the_headers_recording_of_the_only_scan_conflicts():
    """The review's probe: macro plans 9175 eV, the only scan's header records 9180 eV.
    v1 called that variation. MUTATION (run): v1's grouping — measurement-level readings
    in a group of their own — together with `emission_energy` restored to `per_scan`
    turns this red. Each change alone is caught elsewhere: the revert by the test above,
    the grouping by the three comparison tests below (all three went red)."""
    items = [
        _item(ev.CONCEPT_EMISSION_ENERGY, "9175", path="run01.mac", scope=ev.SCOPE_MEASUREMENT,
              normalized=9175.0, source_type=ev.SOURCE_TYPE_MACRO),
        _item(ev.CONCEPT_EMISSION_ENERGY, "9180.0", path=SPEC, scan="1", normalized=9180.0,
              source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION),
    ]
    candidate = _candidates(items)[ev.CONCEPT_EMISSION_ENERGY]
    assert candidate.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE
    assert candidate.variation == ()


def test_MUTATION_a_measurement_level_target_is_compared_with_every_scans_stem():
    """For a per-scan concept a measurement-level reading is compared with EVERY scan
    reading — for `acquisition_target` on the stem alone. A macro declaring another
    stem is a conflict; a macro declaring this one is not."""
    target = ev.CONCEPT_ACQUISITION_TARGET
    scans = [
        _item(target, "ZZ_unit_001.dat", path=S1, scan="1", normalized={"measurement_stem": "ZZ_unit", "scan_index": 1}),
        _item(target, "ZZ_unit_002.dat", path=S2, scan="2", normalized={"measurement_stem": "ZZ_unit", "scan_index": 2}),
    ]
    other = _item(target, "ZZ_other", path="run01.mac", scope=ev.SCOPE_MEASUREMENT, source_type=ev.SOURCE_TYPE_MACRO)
    disputed = _candidates([other, *scans])[target]
    assert disputed.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE
    assert "ZZ_other" in [row["value"] for row in disputed.disagreement]
    same = _item(target, "ZZ_unit", path="run01.mac", scope=ev.SCOPE_MEASUREMENT, source_type=ev.SOURCE_TYPE_MACRO)
    varies = _candidates([same, *scans])[target]
    assert varies.unresolved_reason is None
    assert varies.agreement == "varies"
    # The macro's reading is kept, as the measurement's row, beside each scan's.
    assert [r["scan"] for r in varies.variation] == [None, "1", "2"]


def test_MUTATION_a_file_level_column_that_disagrees_with_a_scans_column_conflicts():
    col = ev.CONCEPT_DETECTOR_COLUMN
    items = [
        _item(col, "I0", path=SPEC, item="column 1", scope=ev.SCOPE_MEASUREMENT,
              source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION),
        _item(col, "vortDT", path=S1, scan="1", item="column 1"),
    ]
    candidate = _candidates(items)[col]
    assert candidate.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE


def test_MUTATION_a_reading_whose_scan_is_not_established_is_never_variation():
    """A scan export that names no single scan (`scan` None) cannot be a different
    scan from the SPEC file's scan 1 — it is compared as the same measurement, and
    differing is a conflict, not variation."""
    col = ev.CONCEPT_DETECTOR_COLUMN
    items = [
        _item(col, "vortDT", path=SPEC, scan="1", item="column 2", source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION),
        _item(col, "vortDT2", path=S1, scan=None, item="column 2"),
    ]
    candidate = _candidates(items)[col]
    assert candidate.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE
    assert candidate.variation == ()


def test_one_scan_never_differs_from_scan_to_scan():
    target = ev.CONCEPT_ACQUISITION_TARGET
    one = [
        _item(target, "ZZ_unit", path="run01.mac", scope=ev.SCOPE_MEASUREMENT, source_type=ev.SOURCE_TYPE_MACRO),
        _item(target, "ZZ_unit_001.dat", path=S1, scan="1", normalized={"measurement_stem": "ZZ_unit", "scan_index": 1}),
    ]
    candidate = _candidates(one)[target]
    assert candidate.unresolved_reason is None
    # The stems agree and only ONE scan exists: agreement, not variation.
    assert candidate.variation == ()
    assert "scan to scan" not in candidate.rule
    # A concept a scan states several of, over ONE scan, says "several" — never
    # "differs from scan to scan".
    col = ev.CONCEPT_DETECTOR_COLUMN
    columns = _candidates([
        _item(col, "I0", path=S1, scan="1", item="column 0"),
        _item(col, "vortDT", path=S1, scan="1", item="column 1"),
    ])[col]
    assert columns.agreement == "varies"
    assert columns.variation_basis == mp.CARDINALITY_PER_SCAN_ITEM
    assert "several values" in columns.rule
    assert "scan to scan" not in columns.rule


def _export(tmp_path, name, body):
    import hashlib

    from isaac_api.bl15 import scans as scan_reader
    from isaac_api.bl15.inventory import SourceRecord

    data = body.encode()
    record = SourceRecord(
        archive_path=f"ZZ_dir/{name}",
        basename=name,
        extension="dat",
        size_bytes=len(data),
        content_sha256=hashlib.sha256(data).hexdigest(),
        parent_dir="ZZ_dir",
        depth=1,
    )
    return scan_reader.read_scan_export(record, body).evidence


def test_a_scan_exports_scan_is_its_own_S_line_never_its_file_index(tmp_path):
    """The review's case: a SPEC file reopened and appended can export `#S 6` as
    `_001`. The export's statements are about SPEC scan 6, not scan 1."""
    evidence = _export(
        tmp_path,
        "ZZ_unit_001.dat",
        "#S 6 gscan 1000 1100 5 0.5\n#T 0.5  (Seconds)\n#L synenergy I0\n1000 1\n",
    )
    assert {e.scan for e in evidence if e.scope == ev.SCOPE_SCAN} == {"6"}


def test_an_export_naming_no_single_scan_leaves_its_scan_unestablished(tmp_path):
    evidence = _export(
        tmp_path,
        "ZZ_unit_001.dat",
        "#S 1 gscan 1000 1100 5 0.5\n#S 2 gscan 1000 1100 5 0.5\n#L synenergy I0\n1000 1\n",
    )
    assert {e.scan for e in evidence} == {None}


def test_a_repeated_SPEC_scan_number_is_left_unestablished():
    import hashlib

    from isaac_api.bl15 import spec as spec_reader
    from isaac_api.bl15.inventory import SourceRecord

    body = (
        "#F ZZ_unit\n#E 1\n#D Fri Jan 01 00:00:00 2100\n"
        "#S 1 gscan 1000 1100 5 0.5\n#T 0.5  (Seconds)\n#L synenergy I0\n1000 1\n\n"
        "#S 1 gscan 1000 1100 5 0.5\n#T 1.0  (Seconds)\n#L synenergy I0\n1000 1\n\n"
        "#S 2 gscan 1000 1100 5 0.5\n#T 1.0  (Seconds)\n#L synenergy I0\n1000 1\n"
    )
    data = body.encode()
    record = SourceRecord(
        archive_path="ZZ_unit", basename="ZZ_unit", extension="", size_bytes=len(data),
        content_sha256=hashlib.sha256(data).hexdigest(), parent_dir="", depth=0,
    )
    evidence = spec_reader.read_spec_acquisition(record, body).evidence
    times = [(e.scan, e.raw_literal) for e in evidence if e.concept == ev.CONCEPT_COUNTING_TIME]
    # `#S 1` appears twice, so neither is scan 1; `#S 2` is.
    assert times == [(None, "0.5  (Seconds)"), (None, "1.0  (Seconds)"), ("2", "1.0  (Seconds)")]


# --- the real synthetic corpora, end to end ----------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(capabilities.INGESTION_ENV, raising=False)
    monkeypatch.delenv(capabilities.STAGING_ROOT_ENV, raising=False)
    monkeypatch.setitem(hist.ARCHIVE_FIXTURES, ARCHIVE, SEMANTICS)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _session(client, archive):
    import_id = client.post("/api/imports", json={"label": "cardinality"}).json()["import"]["import_id"]
    assert client.post(
        f"/api/imports/{import_id}/sources", json={"kind": "archive", "fixture_name": archive}
    ).status_code == 200
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    assert client.post(f"/api/imports/{import_id}/reconstruct").status_code == 200
    response = client.get(f"/api/imports/{import_id}")
    assert response.status_code == 200
    return response.json()["import"]


def _field_conflicts(view):
    return [
        c
        for c in view["reconstruction"]["candidates"]
        if c["kind"] == "field" and c["disagreement"]
    ]


def _concept(candidate):
    return candidate["candidate_id"].split("::")[-1]


def test_the_multi_operator_corpus_reports_no_conflict_for_per_scan_variation(client):
    view = _session(client, ARCHIVE)
    conflicts = _field_conflicts(view)
    per_scan = {
        ev.CONCEPT_ACQUISITION_TARGET,
        ev.CONCEPT_DETECTOR_COLUMN,
        ev.CONCEPT_MOTOR_POSITION,
        ev.CONCEPT_UNKNOWN_TOKEN,
    }
    assert [c for c in conflicts if _concept(c) in per_scan] == []
    # THE VARIATION IS KEPT, not dropped: every measurement's detector columns are
    # still a candidate, now carrying one reading per scan and column.
    varying = [
        c for c in view["reconstruction"]["candidates"]
        if _concept(c) in per_scan and c["agreement"] == "varies"
    ]
    assert len(varying) == 9 * 4
    for c in varying:
        assert c["variation"], c["candidate_id"]
        assert c["review_status"] != "sources_conflict"
    # AND A MACRO'S STATEMENT ABOUT ANOTHER MEASUREMENT IS NOT THIS ONE'S EVIDENCE: one
    # nine-block macro declares every measurement here, and before 2026-09-22 each unit
    # received all nine declared targets. Every acquisition-target reading a unit now
    # carries names that unit.
    for c in view["reconstruction"]["candidates"]:
        if _concept(c) != ev.CONCEPT_ACQUISITION_TARGET:
            continue
        stem = c["candidate_id"].split("::")[0]
        for statement in c["supporting_statements"]:
            assert stem in statement["value"], (stem, statement)


def test_every_genuine_disagreement_in_the_multi_operator_corpus_is_still_a_conflict(client):
    view = _session(client, ARCHIVE)
    by_concept = defaultdict(int)
    for c in _field_conflicts(view):
        by_concept[_concept(c)] += 1
    # Measured before the rule (2026-09-22): 43 field conflicts = 9 acquisition_target +
    # 9 detector_column + 9 motor_position + 9 unknown_token + 6 filter + 1 timestamp.
    # After it, exactly the genuine seven remain.
    assert dict(by_concept) == {ev.CONCEPT_FILTER: 6, ev.CONCEPT_ACQUISITION_TIMESTAMP: 1}
    # And the STRUCTURAL disagreements — the filename vs header vs macro cases and the
    # shared legacy number — are untouched: they are `bl15.relate`'s, not per-value.
    kinds = defaultdict(int)
    relationships = view["corpus_review"]["relationships"]
    for unit in relationships["units"]:
        for conflict in unit["conflicts"]:
            kinds[conflict["kind"]] += 1
    for conflict in relationships["corpus_conflicts"]:
        kinds[conflict["kind"]] += 1
    assert dict(kinds) == {
        "internal_declaration_vs_filename": 3,
        "acquired_never_declared": 3,
        "duplicate_legacy_number": 1,
        "macro_declared_never_acquired": 3,
    }


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


#: A Python dict repr: `{'` anywhere, or a quoted IDENTIFIER followed by `': ` — the
#: shape of a repr's key. The bare two characters `':` are NOT the test, and that is
#: measured rather than chosen: they occur in legitimate prose served by the HERFD
#: selector — "the domain owner's 'vortDT is generally the HERFD channel': recorded for
#: the reviewer …" — a quoted phrase followed by a colon, which no repr produces.
_REPR = re.compile(r"\{'|'[A-Za-z_][A-Za-z0-9_]*': ")


def test_the_repr_detector_catches_a_repr_and_spares_prose():
    assert _REPR.search("{'measurement_stem': 'ZZ', 'scan_index': 1}")
    assert _REPR.search("stem='ZZ', 'scan_index': 1")
    assert not _REPR.search("the owner's 'vortDT is generally the HERFD channel': recorded")


@pytest.mark.parametrize("archive", [ARCHIVE, MINI])
def test_no_python_repr_reaches_the_wire_anywhere_in_the_session(client, archive):
    view = _session(client, archive)
    leaks = [s for s in _strings(view) if _REPR.search(s)]
    assert leaks == []
