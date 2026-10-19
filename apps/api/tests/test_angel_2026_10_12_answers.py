"""The domain owner's 2026-10-12 answers, as the historical import now implements them.

**PROVENANCE.** Every answer here is an OWNER RELAY of the domain owner's (Angel's) words,
relayed by the project owner on 2026-10-12 — the evidentiary class `DEC-47` records. No
transcript is committed; only Krish can confirm the relay, and only Angel the content.
The answers, quoted in ``docs/bl15-2-domain-questions-2026-09-16.md`` §"RECONCILED
2026-10-12":

* the general rule — values are taken from the metadata, or left blank for a person;
* Q6/Q7/Q8 for one beamtime (operando, OER, three_electrode; ex_situ for dry samples);
* Q21 — acquisition settings stay one value per measurement;
* timestamps — disagreements are real discrepancies;
* sample positions — the raw file's recorded position is the real one;
* the follow-up — read the cell type, environment and reaction from the LOGBOOK when it
  states them, otherwise leave them blank.

**EVERY FIXTURE IS SYNTHETIC.** Each archive below is built in ``tmp_path`` from a COPY of
``tests/fixtures/bl15/semantics/multi_operator_corpus`` (sample codes ``ZZ``, element
``Zz``, years 2099/2100) with invented lines added; the committed corpora are never
edited. Nothing here reads ``examples/``.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.capabilities as capabilities
import isaac_api.historical_import as hist
import isaac_api.identity as identity
import isaac_api.routes as routes
import isaac_api.workspace as ws
from isaac_api.bl15 import conditions as cond
from isaac_api.bl15 import evidence as ev
from isaac_api.bl15 import macros, scans, spec
from isaac_api.bl15 import mapping as mp
from isaac_api.bl15 import reconstruct as rc
from isaac_api.bl15 import resolution as res
from isaac_api.bl15 import filenames

REPO_ROOT = Path(__file__).resolve().parents[3]
SEMANTICS = REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
NOTES_NAME = "2099 SYNTHETIC semantics notes.txt"
SCHEMA = json.loads((REPO_ROOT / "schema/isaac_record_v1.json").read_text(encoding="utf-8"))


def _schema_enum(path: str) -> list[str]:
    node = SCHEMA
    for segment in path.split("."):
        node = node["properties"][segment]
    return list(node["enum"])


# --- building synthetic archives -----------------------------------------------------


def _copy(tmp_path: Path, name: str = "corpus") -> Path:
    target = tmp_path / name
    shutil.copytree(SEMANTICS, target)
    return target


def _edit_notes(corpus: Path, after: dict[str, str]) -> None:
    """Insert a line after the FIRST line equal to each key. CRLF and the BOM are kept."""
    path = corpus / NOTES_NAME
    text = path.read_bytes().decode("utf-8")
    lines = text.split("\r\n")
    for anchor, inserted in after.items():
        index = next(i for i, line in enumerate(lines) if line.strip() == anchor.strip())
        lines.insert(index + 1, inserted)
    path.write_bytes("\r\n".join(lines).encode("utf-8"))


def _add_unit(corpus: Path, stem: str, *, p0_extra: str = "") -> None:
    """A synthetic acquisition named ``stem``: unit 01's bytes with its own ``#F``, one
    scan export, and a ``newfile`` declaration, so its name is never disputed."""
    template = "01_01_ZZ1_acid_after500Cycling_filter10_100mV"
    body = (corpus / template).read_text()
    body = re.sub(r"^#F .*$", f"#F {stem}", body, count=1, flags=re.M)
    (corpus / stem).write_text(body)
    folder = corpus / f"{stem}_dir"
    folder.mkdir()
    export = (corpus / f"{template}_dir" / f"{template}_001.dat").read_text()
    if p0_extra:
        export = "\n".join(
            line + p0_extra if line.startswith("#P0") else line for line in export.splitlines()
        ) + "\n"
    (folder / f"{stem}_001.dat").write_text(export)
    macro = corpus / "run01.mac"
    macro.write_text(macro.read_text() + f"newfile {stem}\n")


def _with_positions(corpus: Path, stem: str, *, planned: str, recorded: str) -> None:
    """A planned `mv` after ``stem``'s own `newfile`, and recorded positions on its scans."""
    macro = corpus / "run01.mac"
    macro.write_text(
        macro.read_text().replace(f"newfile {stem}\n", f"newfile {stem}\nmv {planned}\n", 1)
    )
    for export in sorted((corpus / f"{stem}_dir").glob("*.dat")):
        export.write_text(
            "\n".join(
                line + " " + recorded if line.startswith("#P0") else line
                for line in export.read_text().splitlines()
            )
            + "\n"
        )


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    monkeypatch.delenv(capabilities.INGESTION_ENV, raising=False)
    monkeypatch.delenv(capabilities.STAGING_ROOT_ENV, raising=False)
    return ws


@pytest.fixture()
def client(workspace):
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _register(monkeypatch, corpus: Path, name: str = "angel_probe") -> str:
    monkeypatch.setitem(hist.ARCHIVE_FIXTURES, name, str(corpus))
    return name


def _import(client, archive: str) -> str:
    created = client.post("/api/imports", json={"label": "synthetic 2026-10-12 probe"})
    assert created.status_code == 200, created.text
    import_id = created.json()["import"]["import_id"]
    added = client.post(
        f"/api/imports/{import_id}/sources", json={"kind": "archive", "fixture_name": archive}
    )
    assert added.status_code == 200, added.text
    assert client.post(f"/api/imports/{import_id}/parse").status_code == 200
    assert client.post(f"/api/imports/{import_id}/reconstruct").status_code == 200
    return import_id


def _view(client, import_id: str) -> dict:
    response = client.get(f"/api/imports/{import_id}")
    assert response.status_code == 200, response.text
    return response.json()["import"]


def _candidates(view_or_id) -> dict[str, dict]:
    """EVERY candidate, read from the stored session — the session view WINDOWS its
    candidate list (`hist.ARCHIVE_PAGE_WINDOW`), so a probe unit added at the end of an
    archive can sit past it."""
    import_id = view_or_id["import_id"] if isinstance(view_or_id, dict) else view_or_id
    session = hist.load_session(import_id)
    assert session is not None
    return {c.candidate_id: c.to_state() for c in hist.candidates_of(session)}


def _stem(view: dict, legacy: str) -> str:
    return next(
        row["stem"] for row in view["archive"]["units_page"]["rows"] if row["stem"].startswith(f"{legacy}_")
    )


# =====================================================================================
# 1. THE ANSWERS ARE RECORDED, WITH THEIR SOURCE
# =====================================================================================


def test_no_packet_question_is_open_and_each_answer_names_the_owner_relay():
    assert mp.open_domain_questions() == ()
    for qid in ("Q6", "Q7", "Q8", "Q21"):
        assert mp.DOMAIN_QUESTIONS[qid].attribution == mp.ANGEL_2026_10_12, qid
    assert "only Krish can confirm the relay and only Angel the content" in mp.ANGEL_2026_10_12
    # The standing rule's attribution is the same sentence, kept in its own module so the
    # resolution layer does not import the registry.
    assert res.STANDING_RULE_ATTRIBUTION == mp.ANGEL_2026_10_12


def test_the_three_fields_a_person_chooses_are_the_schemas_own_paths():
    for path in mp.PERSON_CHOICE_PATHS:
        assert _schema_enum(path), path
        assert mp.schema_enum(path) == tuple(_schema_enum(path)), path


def test_a_path_the_schema_does_not_declare_has_no_enum():
    assert mp.schema_enum("context.electrochemistry.no_such_field") == ()
    assert mp.schema_enum("context.temperature_K") == ()


# =====================================================================================
# 2. NOTHING EXPERIMENT-SPECIFIC IS AUTO-FILLED; WHAT IS LEFT IS SAID
# =====================================================================================


def test_the_committed_corpus_fills_none_of_the_three_and_says_so(client, monkeypatch, tmp_path):
    """The multi-operator corpus states no environment, reaction or cell type anywhere,
    so nothing is proposed for any of them — not "operando", not "OER", not
    "three_electrode", which were the domain owner's answers for a DIFFERENT beamtime —
    and every Run lists all three as left for a person, with the reason."""
    view = _view(client, _import(client, _register(monkeypatch, _copy(tmp_path))))
    for candidate in view["reconstruction"]["candidates"]:
        assert candidate["target_field_path"] not in mp.PERSON_CHOICE_PATHS, candidate["candidate_id"]
    wire = json.dumps(view["reconstruction"])
    for value in ("operando", "three_electrode", '"OER"'):
        assert value not in wire
    left = view["left_for_a_person"]
    assert left["fills_anything"] is False
    assert left["runs"] == len(left["by_measurement"]) > 0
    assert [f["path"] for f in left["fields"]] == list(mp.PERSON_CHOICE_PATHS)
    for field in left["fields"]:
        assert field["left"] == left["runs"] and field["offered"] == 0
        assert field["options"] == _schema_enum(field["path"])
    for rows in left["by_measurement"].values():
        assert [(r["path"], r["reason"]) for r in rows] == [
            (path, "not_stated") for path in mp.PERSON_CHOICE_PATHS
        ]
    assert "left blank for a person" in left["rule"]
    assert "Conditions for this run" in left["where"]


# =====================================================================================
# 3. DRY / NO ELECTROLYTE -> ex_situ, AS A PROPOSAL
# =====================================================================================


@pytest.fixture()
def dry_archive(tmp_path, monkeypatch):
    corpus = _copy(tmp_path)
    _add_unit(corpus, "09_04_ZZ4_AsIs_NoElectrolyte")
    _add_unit(corpus, "10_04_ZZ4_dry_filter10")
    _add_unit(corpus, "11_04_ZZ4_AsIs_filter10")
    _add_unit(corpus, "12_04_ZZ4_acid_NoElectrolyte_100mV")
    return _register(monkeypatch, corpus)


def test_a_measurement_named_dry_or_no_electrolyte_gets_an_ex_situ_proposal(client, dry_archive):
    view = _view(client, _import(client, dry_archive))
    cands = _candidates(view)
    for stem in ("09_04_ZZ4_AsIs_NoElectrolyte", "10_04_ZZ4_dry_filter10"):
        env = cands[f"{stem}::environment"]
        assert env["target_field_path"] == "context.environment"
        assert env["proposed_value"] == "ex_situ"
        assert env["proposable"] is True
        assert env["determinism"] == "inferred"
        assert rc.RULE_DRY_SAMPLE_IS_EX_SITU in env["rule"]
        # It cites what the name says, verbatim.
        assert any(s["value"] in ("NoElectrolyte", "dry") for s in env["supporting_statements"])
    # ex_situ is one of the schema's own members, read at runtime.
    assert "ex_situ" in mp.schema_enum("context.environment")


def test_as_is_alone_is_not_dry_and_proposes_nothing(client, dry_archive):
    """An as-received electrode can be measured in electrolyte, so `AsIs` by itself says
    nothing about the environment."""
    cands = _candidates(_view(client, _import(client, dry_archive)))
    assert "11_04_ZZ4_AsIs_filter10::environment" not in cands


def test_a_name_that_also_states_an_electrolyte_or_a_potential_is_left_for_a_person(client, dry_archive):
    cands = _candidates(_view(client, _import(client, dry_archive)))
    env = cands["12_04_ZZ4_acid_NoElectrolyte_100mV::environment"]
    assert env["proposed_value"] is None
    assert env["proposable"] is False
    assert "left blank for a person" in env["not_proposable_reason"]
    assert "acid" in env["not_proposable_reason"]


def test_the_ex_situ_value_reaches_a_run_only_as_a_proposal(client, dry_archive):
    import_id = _import(client, dry_archive)
    created = client.post("/api/experiments", json={"title": "dry samples"})
    eid = created.json()["id"]
    added = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": client.get(f"/api/experiments/{eid}").headers["ETag"]},
    )
    assert added.status_code == 200, added.text
    sent = {row["candidate_id"]: row for row in added.json()["sent"]}
    proposal_row = sent["09_04_ZZ4_AsIs_NoElectrolyte::environment"]
    assert proposal_row["run_id"] is not None
    exp = ws.load_experiment(eid)
    run = exp.get_run(proposal_row["run_id"])
    # NOTHING WRITTEN: the run holds no environment; the record holds an OPEN proposal.
    assert "context.environment" not in ((run.draft or {}).get("fields") or {})
    proposals = client.get(f"/api/experiments/{eid}/proposals?limit=200").json()["proposals"]
    mine = [p for p in proposals if p["proposal_id"] == proposal_row["proposal_id"]]
    assert mine and mine[0]["proposed_value"] == "ex_situ" and mine[0]["state"] == "open"
    # And the report says what was left for a person, per field.
    report = added.json()["left_for_a_person"]
    assert "by_measurement" not in report
    env = next(f for f in report["fields"] if f["path"] == "context.environment")
    assert env["offered"] == 2


# =====================================================================================
# 4. SAMPLE POSITION: THE RECORDED POSITION IS THE READING USED
# =====================================================================================


def _ev(concept, literal, *, path, source_type, parser_id, scope=ev.SCOPE_MEASUREMENT,
        scan=None, item=None, normalized=None, n=0):
    return ev.SourceEvidence(
        evidence_id=f"e{n}:{path}:{literal}:{item}:{scan}",
        source_path=path,
        source_type=source_type,
        locator=f"FAKE locator {n}",
        raw_literal=literal,
        concept=concept,
        parser_id=parser_id,
        determinism=ev.DETERMINISM_NORMALIZED if normalized is not None else ev.DETERMINISM_READ,
        normalization_rule="bl15.test.rule" if normalized is not None else None,
        normalized_value=normalized,
        scope=scope,
        scan=scan,
        item=item,
    )


def _plan(motor, value, *, relative=False, n=0):
    return _ev(
        ev.CONCEPT_SAMPLE_POSITION, str(value), path="run01.mac", source_type=ev.SOURCE_TYPE_MACRO,
        parser_id=macros.PARSER_ID, item=motor,
        normalized={"motor": motor, "value": value, "relative": relative}, n=n,
    )


def _recorded(motor, value, *, scan, n=0, path="ZZ_dir/ZZ_unit_001.dat"):
    return _ev(
        ev.CONCEPT_SAMPLE_POSITION, str(value), path=path, source_type=ev.SOURCE_TYPE_SCAN_EXPORT,
        parser_id=scans.PARSER_ID, scope=ev.SCOPE_SCAN, scan=scan, item=motor,
        normalized=value, n=n,
    )


def _by_concept(items):
    return {
        c.candidate_id.split("::")[-1]: c
        for c in rc._candidates_from_evidence(
            items, candidate_prefix="ZZ_unit", source_ids={},
            by_concept=defaultdict(int), by_status=defaultdict(int), unregistered=set(),
        )
    }


def test_two_motors_are_two_readings_not_a_disagreement():
    """v2 compared `Sx` with `Sy` as one measurement-level value and reported a conflict
    in every acquisition that recorded both. MUTATION: dropping `sample_position` from
    `CONCEPT_CARDINALITY` turns this red."""
    candidate = _by_concept([
        _recorded("Sx", 12.5, scan="1", n=1),
        _recorded("Sy", 2.0, scan="1", n=2),
    ])[ev.CONCEPT_SAMPLE_POSITION]
    assert candidate.unresolved_reason is None
    assert candidate.agreement == "varies"
    assert {(r["item"], r["value"]) for r in candidate.variation} == {("Sx", "Sx 12.5"), ("Sy", "Sy 2.0")}


def test_a_planned_move_against_the_recorded_position_is_resolved_by_the_standing_rule():
    candidate = _by_concept([
        _plan("Sx", 13.0, n=1),
        _plan("Sy", 2.0, n=2),
        _recorded("Sx", 12.5, scan="1", n=3),
        _recorded("Sy", 2.0, scan="1", n=4),
    ])[ev.CONCEPT_SAMPLE_POSITION]
    # BOTH READINGS KEPT — the disagreement is still there, verbatim.
    assert sorted(row["value"] for row in candidate.disagreement) == ["Sx 12.5", "Sx 13.0"]
    assert candidate.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE
    # RESOLVED BY THE RULE, named and versioned, with its provenance.
    assert candidate.resolved_by_rule == res.STANDING_RULE_RECORDED_POSITION
    assert candidate.review_status == "resolved"
    standing = candidate.standing_resolution
    assert standing["rule_id"] == "bl15.resolution.recorded_motor_position.v1"
    assert standing["authority"] == "domain_owner_rule"
    assert standing["layer"] == res.LAYER_CONFIRMED_RESOLUTION
    assert standing["chosen_source_role"] == res.ROLE_INSTRUMENT_HEADER
    assert standing["over_source_role"] == res.ROLE_PLANNED_ACQUISITION
    assert standing["attribution"] == mp.ANGEL_2026_10_12
    assert [row["value"] for row in standing["reading_used"]] == ["Sx 12.5"]
    # IT WRITES NO FIELD: there is no official field for a sample position (Q19).
    assert candidate.target_field_path is None
    assert candidate.proposable is False
    assert standing["writes_a_record_field"] is False


def test_a_planned_move_that_matches_the_recording_is_no_disagreement_at_all():
    """`13` recorded and `13.0` planned are one position — compared on the number."""
    candidate = _by_concept([
        _plan("Sx", 13.0, n=1),
        _recorded("Sx", 13, scan="1", n=2),
    ])[ev.CONCEPT_SAMPLE_POSITION]
    assert candidate.unresolved_reason is None
    assert candidate.resolved_by_rule is None


def test_MUTATION_two_recordings_that_disagree_stay_an_open_conflict():
    """The rule reaches a plan-versus-recording disagreement ONLY. Two acquisition files
    recording different positions for the same motor of the same scan is a real
    question, and the rule says nothing."""
    candidate = _by_concept([
        _plan("Sx", 13.0, n=1),
        _recorded("Sx", 12.5, scan="1", n=2, path="ZZ_dir/ZZ_unit_001.dat"),
        _ev(ev.CONCEPT_SAMPLE_POSITION, "12.0", path="ZZ_unit", source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
            parser_id=spec.PARSER_ID, scope=ev.SCOPE_SCAN, scan="1", item="Sx", normalized=12.0, n=3),
    ])[ev.CONCEPT_SAMPLE_POSITION]
    assert candidate.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE
    assert candidate.resolved_by_rule is None
    assert candidate.review_status == "sources_conflict"


def test_a_relative_move_is_a_change_not_a_position_and_is_never_compared():
    candidate = _by_concept([
        _plan("Sz", -0.3, relative=True, n=1),
        _recorded("Sz", -3.5, scan="1", n=2),
        _recorded("Sz", -3.8, scan="2", n=3, path="ZZ_dir/ZZ_unit_002.dat"),
    ])[ev.CONCEPT_SAMPLE_POSITION]
    assert candidate.unresolved_reason is None
    # Kept, and written the way the command says it.
    assert any("by -0.3 (relative move)" in row["value"] for row in candidate.variation)


def test_the_parser_ids_the_role_classifier_names_are_the_readers_own():
    assert res._FILENAME_PARSER_IDS == {filenames.PARSER_ID}
    assert res._RECORDING_PARSER_IDS == {spec.PARSER_ID, scans.PARSER_ID}


def test_through_the_import_the_position_conflict_is_shown_resolved_with_both_readings(
    client, tmp_path, monkeypatch
):
    corpus = _copy(tmp_path)
    stem = "04_02_ZZ2_base_after500Cycling_filter20_800mV"
    _with_positions(corpus, stem, planned="Sx 13.0 Sy 2.0", recorded="Sx=12.5 Sy=2.0")
    view = _view(client, _import(client, _register(monkeypatch, corpus)))
    candidate = _candidates(view)[f"{stem}::sample_position"]
    assert candidate["review_status"] == "resolved"
    assert candidate["agreement"] == "sources_conflict"
    assert sorted(row["value"] for row in candidate["disagreement"]) == ["Sx 12.5", "Sx 13.0"]
    assert any("`mv`" in loc for row in candidate["disagreement"] for loc in row["locators"])
    assert candidate["standing_resolution"]["rule_id"] == res.STANDING_RULE_RECORDED_POSITION
    assert candidate["standing_resolution"]["statement"].startswith(
        "The position the acquisition file recorded is the one used."
    )
    # Survives the session round trip.
    again = hist.SemanticCandidate.from_state(candidate)
    assert again.standing_resolution == candidate["standing_resolution"]


# =====================================================================================
# 5. Q21 AND TIMESTAMPS: CONFIRMED, AND SAID PLAINLY
# =====================================================================================


def test_an_acquisition_setting_that_differs_within_one_measurement_is_a_discrepancy():
    candidate = _by_concept([
        _ev(ev.CONCEPT_EMISSION_ENERGY, "900", path="run01.mac", source_type=ev.SOURCE_TYPE_MACRO,
            parser_id=macros.PARSER_ID, normalized=900.0, n=1),
        _ev(ev.CONCEPT_EMISSION_ENERGY, "905.0", path="ZZ_unit", source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
            parser_id=spec.PARSER_ID, scope=ev.SCOPE_SCAN, scan="1", normalized=905.0, n=2),
    ])[ev.CONCEPT_EMISSION_ENERGY]
    assert candidate.unresolved_reason == hist.UNRESOLVED_SOURCES_DISAGREE
    assert "kept the same for every scan of a measurement" in candidate.rule
    assert "Different measurements may use different settings" in candidate.rule


def test_different_measurements_with_different_settings_are_never_compared(client, monkeypatch, tmp_path):
    """Units 01 (filter 10) and 04 (filter 20) are different measurements. Every reading a
    unit's setting candidate rests on comes from that unit's OWN files or the macro that
    declared it — never another measurement's — so a difference between measurements can
    never become a disagreement. (Unit 04's corpus-designed within-measurement filter
    conflict is exactly that: its own files disagreeing.)"""
    view = _view(client, _import(client, _register(monkeypatch, _copy(tmp_path))))
    cands = _candidates(view)
    for legacy in ("01", "04"):
        stem = _stem(view, legacy)
        for concept in ("filter", "emission_energy", "counting_time"):
            candidate = cands.get(f"{stem}::{concept}")
            if candidate is None:
                continue
            for statement in candidate["supporting_statements"]:
                where = statement["locator"].split(" · ", 1)[0]
                assert where.startswith(stem) or where.endswith(".mac"), (stem, concept, where)


def test_no_served_sentence_about_these_says_pending_or_cites_a_question():
    for sentence in (*rc.WITHIN_ONE_MEASUREMENT.values(), *(r.statement for r in res.STANDING_RESOLUTIONS)):
        assert "Q21" not in sentence and "pending" not in sentence.lower()
        assert not re.search(r"\b20\d\d-\d\d-\d\d\b", sentence)
    assert "real discrepancy" in rc.WITHIN_ONE_MEASUREMENT[ev.CONCEPT_ACQUISITION_TIMESTAMP]


# =====================================================================================
# 6. A PERSON CAN CHOOSE REACTION AND CELL TYPE ON A RUN
# =====================================================================================


def _run(client, eid):
    added = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "R1"},
        headers={"If-Match": client.get(f"/api/experiments/{eid}").headers["ETag"]},
    )
    assert added.status_code == 201, added.text
    return added.json()["run"]["id"]


def _patch(client, eid, run_id, fields):
    etag = client.get(f"/api/experiments/{eid}/runs/{run_id}").headers["ETag"]
    return client.patch(
        f"/api/experiments/{eid}/runs/{run_id}",
        json={"confirmed_by_user": True, "fields": fields},
        headers={"If-Match": etag},
    )


def test_reaction_and_cell_type_are_run_writable_closed_enums_from_the_schema(client):
    eid = client.post("/api/experiments", json={"title": "electrochemistry"}).json()["id"]
    run_id = _run(client, eid)
    assert routes._run_chosen_enum_fields() == {
        "context.electrochemistry.reaction": tuple(_schema_enum("context.electrochemistry.reaction")),
        "context.electrochemistry.cell_type": tuple(_schema_enum("context.electrochemistry.cell_type")),
    }
    ok = _patch(client, eid, run_id, {
        "context.electrochemistry.reaction": "OER",
        "context.electrochemistry.cell_type": "three_electrode",
    })
    assert ok.status_code == 200, ok.text
    fields = ws.load_experiment(eid).get_run(run_id).draft["fields"]
    assert fields["context.electrochemistry.reaction"]["value"] == "OER"
    assert fields["context.electrochemistry.cell_type"]["value"] == "three_electrode"
    assert fields["context.electrochemistry.cell_type"]["status"] == "verified"


def test_an_off_enum_reaction_or_cell_type_is_refused_and_nothing_is_written(client):
    eid = client.post("/api/experiments", json={"title": "electrochemistry"}).json()["id"]
    run_id = _run(client, eid)
    refused = _patch(client, eid, run_id, {
        "context.electrochemistry.cell_type": "two_electrode",
        "context.electrochemistry.reaction": "OER",
    })
    assert refused.status_code == 422
    body = refused.json()
    assert body["error"] == "not_an_allowed_value"
    assert body["keys"] == ["context.electrochemistry.cell_type"]
    assert body["allowed"]["context.electrochemistry.cell_type"] == _schema_enum(
        "context.electrochemistry.cell_type"
    )
    assert "two_electrode" not in json.dumps(body)  # the rejected value is not echoed
    fields = (ws.load_experiment(eid).get_run(run_id).draft or {}).get("fields") or {}
    assert "context.electrochemistry.reaction" not in fields  # refused WHOLE


def test_clearing_a_chosen_value_is_allowed(client):
    eid = client.post("/api/experiments", json={"title": "electrochemistry"}).json()["id"]
    run_id = _run(client, eid)
    assert _patch(client, eid, run_id, {"context.electrochemistry.reaction": "HER"}).status_code == 200
    assert _patch(client, eid, run_id, {"context.electrochemistry.reaction": None}).status_code == 200
    fields = ws.load_experiment(eid).get_run(run_id).draft.get("fields") or {}
    assert "context.electrochemistry.reaction" not in fields


def test_the_run_editors_options_are_the_schemas_own_enum():
    """`runFields.ts` transcribes the options (the browser has no schema read); this pins
    the transcription to the vendored schema so a refresh fails here."""
    text = (REPO_ROOT / "apps/web/src/lib/runFields.ts").read_text(encoding="utf-8")
    for path in routes.RUN_CHOSEN_ENUM_PATH_NAMES:
        block = re.search(
            r"path:\s*'" + re.escape(path) + r"'.*?options:\s*\[(.*?)\]", text, re.S
        )
        assert block is not None, path
        options = re.findall(r"'([^']+)'", block.group(1))
        assert options == _schema_enum(path), path


# =====================================================================================
# 7. THE LOGBOOK'S OWN WORDS
# =====================================================================================


def _hits(line):
    return [(h.concept, h.status, h.member) for h in cond.read_line(line)]


@pytest.mark.parametrize(
    "line, expected",
    [
        ("measured operando", [(ev.CONCEPT_ENVIRONMENT_STATEMENT, "member", "operando")]),
        ("an In-Situ cell", [(ev.CONCEPT_ENVIRONMENT_STATEMENT, "member", "in_situ")]),
        ("in situ", [(ev.CONCEPT_ENVIRONMENT_STATEMENT, "member", "in_situ")]),
        ("measured ex-situ", [(ev.CONCEPT_ENVIRONMENT_STATEMENT, "member", "ex_situ")]),
        ("Ex Situ", [(ev.CONCEPT_ENVIRONMENT_STATEMENT, "member", "ex_situ")]),
        ("a Three-Electrode cell", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "member", "three_electrode")]),
        ("three electrode", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "member", "three_electrode")]),
        ("3-electrode", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "member", "three_electrode")]),
        ("Flow cell = 10 ml/min", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "member", "flow_cell")]),
        ("an H-cell", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "member", "h_cell")]),
        ("coin cell", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "member", "coin_cell")]),
        ("microfluidic flow cell", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "member", "microfluidic_flow_cell")]),
        ("for the OER", [(ev.CONCEPT_REACTION_STATEMENT, "member", "OER")]),
        ("oxygen evolution reaction", [(ev.CONCEPT_REACTION_STATEMENT, "member", "OER")]),
        ("HER", [(ev.CONCEPT_REACTION_STATEMENT, "member", "HER")]),
        ("Hydrogen Evolution", [(ev.CONCEPT_REACTION_STATEMENT, "member", "HER")]),
        ("ORR", [(ev.CONCEPT_REACTION_STATEMENT, "member", "ORR")]),
        ("oxygen reduction reaction", [(ev.CONCEPT_REACTION_STATEMENT, "member", "ORR")]),
        ("CO2RR", [(ev.CONCEPT_REACTION_STATEMENT, "member", "CO2RR")]),
        ("NO3RR", [(ev.CONCEPT_REACTION_STATEMENT, "member", "NO3RR")]),
        ("NRR", [(ev.CONCEPT_REACTION_STATEMENT, "member", "NRR")]),
        ("a two-electrode cell", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "not_an_option", None)]),
        ("a battery", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "not_an_option", None)]),
        ("the electrolyzer", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "not_an_option", None)]),
        ("water oxidation", [(ev.CONCEPT_REACTION_STATEMENT, "ambiguous", None)]),
        ("nitrogen reduction", [(ev.CONCEPT_REACTION_STATEMENT, "ambiguous", None)]),
        ("not operando", [(ev.CONCEPT_ENVIRONMENT_STATEMENT, "negated", None)]),
        ("without a flow cell", [(ev.CONCEPT_CELL_TYPE_STATEMENT, "negated", None)]),
    ],
)
def test_each_lexicon_term(line, expected):
    assert _hits(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "for her sample",  # the pronoun is not the reaction
        "PROCEDURE FOR PREPARING",  # FOR is never read as an abbreviation
        "file IrOx_OER_1",  # inside a name, not a statement
        "no none",  # the schema's `None` is never read from prose
        "Electrochemical cell",  # no cell type named
        "Working electrode",
    ],
)
def test_a_line_that_names_no_option_reads_as_nothing(line):
    assert cond.read_line(line) == []


def test_every_member_the_lexicon_names_is_one_the_schema_declares():
    for concept, (path, _rule, _name) in cond.FIELDS.items():
        allowed = set(_schema_enum(path))
        for _pattern, status, member, options in cond._patterns(concept):
            if status == cond.STATUS_MEMBER:
                assert member in allowed, (concept, member)
            for option in options:
                assert option in allowed, (concept, option)


@pytest.fixture()
def logbook_archive(tmp_path, monkeypatch):
    corpus = _copy(tmp_path)
    _edit_notes(corpus, {
        # Beamtime level: before any sample section.
        "SYNTHETIC: held at room temperature throughout": (
            "SYNTHETIC: every acquisition was measured operando in a three-electrode cell."
        ),
        # Sample 2 (file numbers 04, 05): overrides the cell for its own section, adds a
        # reaction for its own section only.
        "Operator: Operator Beta (synthetic)": "SYNTHETIC: this sample used an H-cell for the OER.",
        # Sample 3 (06, 07): a term the schema has no option for, and an ambiguous one.
        "Operator: Operator Gamma (synthetic)": (
            "SYNTHETIC: a two-electrode cell; water oxidation was studied."
        ),
    })
    _add_unit(corpus, "09_04_ZZ4_AsIs_NoElectrolyte")
    return _register(monkeypatch, corpus)


def test_logbook_statements_become_proposals_scoped_by_section(client, logbook_archive):
    view = _view(client, _import(client, logbook_archive))
    cands = _candidates(view)
    s01, s04 = _stem(view, "01"), _stem(view, "04")
    # Sample 1: the beamtime statement applies.
    assert cands[f"{s01}::environment_statement"]["proposed_value"] == "operando"
    assert cands[f"{s01}::cell_type_statement"]["proposed_value"] == "three_electrode"
    assert f"{s01}::reaction_statement" not in cands  # the logbook says no reaction there
    # Sample 2: its own section overrides the cell type, adds the reaction; the beamtime
    # environment still applies because the section says nothing about it.
    assert cands[f"{s04}::cell_type_statement"]["proposed_value"] == "h_cell"
    assert cands[f"{s04}::reaction_statement"]["proposed_value"] == "OER"
    assert cands[f"{s04}::environment_statement"]["proposed_value"] == "operando"
    for cid in (f"{s04}::cell_type_statement", f"{s04}::reaction_statement"):
        candidate = cands[cid]
        assert candidate["proposable"] is True
        assert candidate["target_field_path"] in mp.PERSON_CHOICE_PATHS
        # It cites the exact logbook sentence, verbatim, with its locator.
        assert candidate["supporting_statements"][0]["value"] == (
            "SYNTHETIC: this sample used an H-cell for the OER."
        )
        assert NOTES_NAME in candidate["supporting_statements"][0]["locator"]


def test_a_term_with_no_option_or_several_is_kept_and_left_for_a_person(client, logbook_archive):
    view = _view(client, _import(client, logbook_archive))
    cands = _candidates(view)
    s06 = _stem(view, "06")
    cell = cands[f"{s06}::cell_type_statement"]
    assert cell["proposed_value"] is None and cell["proposable"] is False
    assert "two-electrode" in cell["not_proposable_reason"]
    assert "not one of the cell type options the official schema offers" in cell["not_proposable_reason"]
    assert cell["supporting_statements"][0]["value"] == (
        "SYNTHETIC: a two-electrode cell; water oxidation was studied."
    )
    reaction = cands[f"{s06}::reaction_statement"]
    assert reaction["proposed_value"] is None
    assert "fits more than one" in reaction["not_proposable_reason"]
    left = {r["path"]: r["reason"] for r in view["left_for_a_person"]["by_measurement"][s06]}
    assert left["context.electrochemistry.cell_type"] == "stated_not_settled"
    assert left["context.electrochemistry.reaction"] == "stated_not_settled"
    assert "context.environment" not in left  # operando (beamtime) is offered


def test_two_options_in_one_scope_are_a_conflict(client, tmp_path, monkeypatch):
    corpus = _copy(tmp_path)
    _edit_notes(corpus, {
        "Operator: Operator Alpha (synthetic)": "SYNTHETIC: a flow cell, later a coin cell.",
    })
    view = _view(client, _import(client, _register(monkeypatch, corpus)))
    cell = _candidates(view)[f"{_stem(view, '01')}::cell_type_statement"]
    assert cell["agreement"] == "sources_conflict"
    assert cell["proposed_value"] is None
    assert sorted(row["value"] for row in cell["disagreement"]) == ["coin_cell", "flow_cell"]


def test_the_filename_rule_and_the_logbook_disagreeing_is_a_conflict(client, logbook_archive):
    """Unit 09's name says no electrolyte (ex_situ); the beamtime logbook says operando.
    Neither wins silently."""
    view = _view(client, _import(client, logbook_archive))
    cands = _candidates(view)
    stem = "09_04_ZZ4_AsIs_NoElectrolyte"
    env_rows = [
        c for c in cands.values()
        if c["candidate_id"].startswith(f"{stem}::") and c["target_field_path"] == "context.environment"
    ]
    conflicted = [c for c in env_rows if c["agreement"] == "sources_conflict"]
    assert len(conflicted) == 1
    assert sorted(row["value"] for row in conflicted[0]["disagreement"]) == ["ex_situ", "operando"]
    assert not any(c["proposable"] for c in env_rows)
    left = {r["path"]: r["reason"] for r in view["left_for_a_person"]["by_measurement"][stem]}
    assert left["context.environment"] == "sources_disagree"


def test_a_silent_logbook_proposes_nothing(client, tmp_path, monkeypatch):
    view = _view(client, _import(client, _register(monkeypatch, _copy(tmp_path))))
    for cid in _candidates(view):
        assert not cid.endswith(("::environment_statement", "::reaction_statement", "::cell_type_statement"))


def test_a_notes_cell_is_never_read_for_these(client, tmp_path, monkeypatch):
    """A Data Quality Note is never parsed (2026-09-22). A tab-prefixed Notes cell that
    happens to say "operando" proposes nothing."""
    corpus = _copy(tmp_path)
    _edit_notes(corpus, {"\tSYNTHETIC: skip the opening sweep": "\tSYNTHETIC: operando, OER"})
    view = _view(client, _import(client, _register(monkeypatch, corpus)))
    assert not any(cid.endswith("::environment_statement") for cid in _candidates(view))


def test_a_reaction_proposal_is_accepted_only_onto_the_schemas_list(client, logbook_archive, monkeypatch):
    """The accept path checks the enum too, so a proposal cannot write what a direct edit
    refuses. Accepting needs a trusted actor; the deterministic fixture verifier is it."""
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, "test_fixture")
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, "synthetic-reviewer")
    import_id = _import(client, logbook_archive)
    eid = client.post("/api/experiments", json={"title": "logbook"}).json()["id"]
    added = client.post(
        f"/api/imports/{import_id}/add-to-experiment",
        json={"experiment_id": eid, "create_runs": True},
        headers={"If-Match": client.get(f"/api/experiments/{eid}").headers["ETag"]},
    )
    assert added.status_code == 200, added.text
    view = _view(client, import_id)
    s04 = _stem(view, "04")
    row = next(r for r in added.json()["sent"] if r["candidate_id"] == f"{s04}::reaction_statement")
    review = f"/api/experiments/{eid}/proposals/{row['proposal_id']}/review"
    etag = client.get(f"/api/experiments/{eid}").headers["ETag"]
    off = client.post(
        review,
        json={"confirmed_by_user": True, "action": "accept", "accepted_from": "edited", "value": "OERR"},
        headers={"If-Match": etag},
    )
    if off.status_code == 409 and off.json().get("error") == "human_actor_required":
        pytest.skip("this build's fixture verifier is not configured in this environment")
    assert off.status_code == 422, off.text
    assert off.json()["error"] == "not_an_allowed_value"
    etag = client.get(f"/api/experiments/{eid}").headers["ETag"]
    ok = client.post(
        review,
        json={"confirmed_by_user": True, "action": "accept", "accepted_from": "candidate"},
        headers={"If-Match": etag},
    )
    assert ok.status_code == 200, ok.text
    run = ws.load_experiment(eid).get_run(row["run_id"])
    assert run.draft["fields"]["context.electrochemistry.reaction"]["value"] == "OER"


# =====================================================================================
# 8. AN INDEPENDENT REVIEW'S FINDINGS (2026-10-12) — each in the reviewer's own words
# =====================================================================================


def _logbook(client, monkeypatch, tmp_path, edits, units=()):
    corpus = _copy(tmp_path)
    _edit_notes(corpus, edits)
    for stem in units:
        _add_unit(corpus, stem)
    import_id = _import(client, _register(monkeypatch, corpus))
    return import_id, _view(client, import_id)


BEAMTIME = "SYNTHETIC: held at room temperature throughout"


def _proposed(cands, path):
    return {
        cid.split("::")[0]: c["proposed_value"]
        for cid, c in cands.items()
        if c["target_field_path"] == path and c["proposable"]
    }


# --- I1: negations and hedges -----------------------------------------------------


@pytest.mark.parametrize(
    "line, status",
    [
        ("SYNTHETIC: None of the samples were measured operando.", cond.STATUS_NEGATED),
        ("Nothing operando today", cond.STATUS_NEGATED),
        ("Neither operando nor in situ", cond.STATUS_NEGATED),
        ("nobody ran it operando", cond.STATUS_NEGATED),
        ("no one used a flow cell", cond.STATUS_NEGATED),
        ("Operando? check with Angel", cond.STATUS_HEDGED),
        ("possibly OER", cond.STATUS_HEDGED),
        ("maybe HER", cond.STATUS_HEDGED),
        ("perhaps operando", cond.STATUS_HEDGED),
        ("might be a flow cell", cond.STATUS_HEDGED),
        ("could be in situ", cond.STATUS_HEDGED),
        ("planned operando", cond.STATUS_HEDGED),
        ("cell type to be confirmed: H-cell", cond.STATUS_HEDGED),
        ("reaction TBD, OER likely", cond.STATUS_HEDGED),
        ("check: three-electrode", cond.STATUS_HEDGED),
    ],
)
def test_a_negated_or_hedged_sentence_is_never_a_statement(line, status):
    hits = cond.read_line(line)
    assert hits, line
    assert {h.status for h in hits} == {status}, line
    assert all(h.member is None for h in hits), line


def test_I1_none_of_the_samples_operando_proposes_operando_for_no_run(client, monkeypatch, tmp_path):
    import_id, view = _logbook(
        client, monkeypatch, tmp_path,
        {BEAMTIME: "SYNTHETIC: None of the samples were measured operando."},
    )
    cands = _candidates(import_id)
    assert _proposed(cands, "context.environment") == {}
    env = next(f for f in view["left_for_a_person"]["fields"] if f["path"] == "context.environment")
    assert env["offered"] == 0 and env["left"] == view["left_for_a_person"]["runs"]
    kept = [c for cid, c in cands.items() if cid.endswith("::environment_statement")]
    assert kept and all("negates" in c["not_proposable_reason"] for c in kept)


def test_I1_neither_nor_is_not_a_two_environment_conflict(client, monkeypatch, tmp_path):
    import_id, _view_ = _logbook(
        client, monkeypatch, tmp_path, {BEAMTIME: "SYNTHETIC: Neither operando nor in situ."}
    )
    cands = _candidates(import_id)
    env = [c for cid, c in cands.items() if cid.endswith("::environment_statement")]
    assert env and not any(c["agreement"] == "sources_conflict" for c in env)
    assert _proposed(cands, "context.environment") == {}


def test_I1_a_hedge_is_kept_and_proposes_nothing(client, monkeypatch, tmp_path):
    import_id, _view_ = _logbook(
        client, monkeypatch, tmp_path,
        {BEAMTIME: "SYNTHETIC: Operando? check with the beamline. Possibly OER."},
    )
    cands = _candidates(import_id)
    assert _proposed(cands, "context.environment") == {}
    assert _proposed(cands, "context.electrochemistry.reaction") == {}
    reaction = next(c for cid, c in cands.items() if cid.endswith("::reaction_statement"))
    assert "a question, a plan or a guess" in reaction["not_proposable_reason"]
    assert reaction["supporting_statements"][0]["value"] == (
        "SYNTHETIC: Operando? check with the beamline. Possibly OER."
    )


# --- I2: capitals, paths, file names ------------------------------------------------


@pytest.mark.parametrize(
    "line",
    ["NOTE: GIVE HER THE CELL KEYS", "/data/OER/2099", "OER.dat", "saved to C:\\runs\\OER\\x", "HER/OER"],
)
def test_I2_capitals_paths_and_file_names_are_not_statements(line):
    assert cond.read_line(line) == []


def test_I2_an_all_caps_note_proposes_no_reaction(client, monkeypatch, tmp_path):
    import_id, _view_ = _logbook(
        client, monkeypatch, tmp_path, {BEAMTIME: "NOTE: GIVE HER THE CELL KEYS"}
    )
    assert not any(cid.endswith("::reaction_statement") for cid in _candidates(import_id))


def test_I2_a_lowercase_sentence_still_reads_the_abbreviation():
    assert [(h.member, h.status) for h in cond.read_line("measured under OER conditions")] == [
        ("OER", cond.STATUS_MEMBER)
    ]


# --- I3: a beamtime sentence that names samples -------------------------------------


def test_I3_only_samples_3_and_4_does_not_apply_to_every_run(client, monkeypatch, tmp_path):
    """The reviewer's sentence, before any sample section. In this corpus the logbook's
    "Sample 3" section lists files 06-07 while the filename token 03 covers 06-08, so the
    logbook's numbering is NOT the filenames' — which samples it means is not decided,
    and it applies to none. It is kept, verbatim, as one beamtime candidate."""
    sentence = "SYNTHETIC: only samples 3 and 4 were run in a flow cell."
    import_id, view = _logbook(client, monkeypatch, tmp_path, {BEAMTIME: sentence})
    cands = _candidates(import_id)
    assert _proposed(cands, "context.electrochemistry.cell_type") == {}
    kept = cands["shared::unscoped::cell_type_statement"]
    assert kept["proposable"] is False
    assert kept["supporting_statements"][0]["value"] == sentence
    assert "applied to none" in kept["not_proposable_reason"]
    cell = next(f for f in view["left_for_a_person"]["fields"] if f["path"] == "context.electrochemistry.cell_type")
    assert cell["offered"] == 0


def test_I3_named_samples_apply_to_exactly_those_when_the_numbering_agrees(client, monkeypatch, tmp_path):
    """Sections 1 and 2 list exactly the files whose sample token is 01 and 02."""
    import_id, view = _logbook(
        client, monkeypatch, tmp_path,
        {BEAMTIME: "SYNTHETIC: only samples 1 and 2 were run in a flow cell."},
    )
    proposed = _proposed(_candidates(import_id), "context.electrochemistry.cell_type")
    assert set(proposed.values()) == {"flow_cell"}
    assert {stem.split("_")[1] for stem in proposed} == {"01", "02"}


def test_I3_the_real_Q8_shape_samples_7_to_8_flowing(client, monkeypatch, tmp_path):
    """The shape the domain owner's Q8 answer sits beside: a beamtime sentence about
    samples 7–8 (an en-dash range) only. With no "Sample 7"/"Sample 8" section to
    contradict it, the confirmed token (`DEC-47`) decides: 07 and 08 only."""
    import_id, _view_ = _logbook(
        client, monkeypatch, tmp_path,
        {BEAMTIME: "SYNTHETIC: samples 7–8 were measured in a flow cell."},
        units=("20_07_ZZ7_acid_filter10", "21_08_ZZ8_acid_filter10"),
    )
    proposed = _proposed(_candidates(import_id), "context.electrochemistry.cell_type")
    assert proposed == {"20_07_ZZ7_acid_filter10": "flow_cell", "21_08_ZZ8_acid_filter10": "flow_cell"}


@pytest.mark.parametrize(
    "sentence",
    [
        "SYNTHETIC: every sample except sample 2 was run in a flow cell.",
        "SYNTHETIC: only some acquisitions used a flow cell.",
        "SYNTHETIC: the ZZ3 electrodes were run in a flow cell.",
    ],
)
def test_I3_an_unnamed_or_excluding_subset_applies_to_none(client, monkeypatch, tmp_path, sentence):
    import_id, _view_ = _logbook(client, monkeypatch, tmp_path, {BEAMTIME: sentence})
    cands = _candidates(import_id)
    assert _proposed(cands, "context.electrochemistry.cell_type") == {}
    assert "shared::unscoped::cell_type_statement" in cands


# --- I4: the dry rule reads only a name that says nothing else -----------------------


@pytest.mark.parametrize(
    "stem",
    [
        "10_04_ZZ4_dry_O2Sat",
        "11_04_ZZ4_dry_pH13",
        "12_04_ZZ4_dry_10mLmin",
        "13_04_ZZ4_dry_O2",
        "14_04_ZZ4_dry_alk",
        # the potential check, with no electrolyte token beside it (a surviving mutant)
        "15_04_ZZ4_NoElectrolyte_100mV",
        "16_04_ZZ4_dry_after500Cycling",
    ],
)
def test_I4_any_other_condition_in_the_name_leaves_the_environment_for_a_person(
    client, monkeypatch, tmp_path, stem
):
    corpus = _copy(tmp_path)
    _add_unit(corpus, stem)
    env = _candidates(_import(client, _register(monkeypatch, corpus)))[f"{stem}::environment"]
    assert env["proposed_value"] is None and env["proposable"] is False
    assert "left blank for a person" in env["not_proposable_reason"]


def test_I4_identity_tokens_beside_dry_still_qualify(client, monkeypatch, tmp_path):
    corpus = _copy(tmp_path)
    _add_unit(corpus, "17_04_ZZ4_dry_filter10")
    _add_unit(corpus, "18_04_ZZ4_0p5nm_AsIs_NoElectrolyte")
    cands = _candidates(_import(client, _register(monkeypatch, corpus)))
    assert cands["17_04_ZZ4_dry_filter10::environment"]["proposed_value"] == "ex_situ"
    assert cands["18_04_ZZ4_0p5nm_AsIs_NoElectrolyte::environment"]["proposed_value"] == "ex_situ"


# --- surviving mutants ----------------------------------------------------------------


def test_an_option_plus_a_negated_term_in_one_scope_proposes_nothing(client, monkeypatch, tmp_path):
    """MUTATION: `if len(members) == 1:` (dropping `and not unusable`) turns this red."""
    import_id, view = _logbook(
        client, monkeypatch, tmp_path,
        {
            "Operator: Operator Alpha (synthetic)": "SYNTHETIC: measured in a flow cell.",
            "SYNTHETIC: measured in a flow cell.": "SYNTHETIC: not a coin cell.",
        },
    )
    cell = _candidates(import_id)[f"{_stem(view, '01')}::cell_type_statement"]
    assert cell["proposed_value"] is None and cell["proposable"] is False


# =====================================================================================
# 9. THE RE-REVIEW'S LAST ROUND (2026-10-12)
# =====================================================================================


@pytest.mark.parametrize(
    "line",
    [
        "Hydrogen evolution was suppressed",
        "HER was inhibited by the coating",
        "we avoided ORR",
        "OER minimised at this potential",
        "OER minimized at this potential",
        "HER is a side reaction here",
        "the competing HER",
    ],
)
def test_a_suppressed_or_competing_reaction_is_not_the_reaction_under_study(line):
    hits = [h for h in cond.read_line(line) if h.concept == ev.CONCEPT_REACTION_STATEMENT]
    assert hits, line
    assert all(h.member is None for h in hits), line


@pytest.mark.parametrize("line", ["operando w/o potential", "measured W/O a flow cell"])
def test_w_slash_o_is_a_negation(line):
    hits = cond.read_line(line)
    assert hits and all(h.status == cond.STATUS_NEGATED for h in hits), line


def test_a_run_whose_logbook_sentence_could_not_be_matched_does_not_read_not_stated(
    client, monkeypatch, tmp_path
):
    """The sentence names samples the logbook numbers differently from the filenames, so
    it applies to no run — and every run must say THAT, not "no file states it"."""
    import_id, view = _logbook(
        client, monkeypatch, tmp_path,
        {BEAMTIME: "SYNTHETIC: only samples 3 and 4 were run in a flow cell."},
    )
    assert "shared::unscoped::cell_type_statement" in _candidates(import_id)
    left = view["left_for_a_person"]
    reasons = {
        r["reason"]
        for rows in left["by_measurement"].values()
        for r in rows
        if r["path"] == "context.electrochemistry.cell_type"
    }
    assert reasons == {"stated_unmatched"}
    assert "could match" in left["reasons"]["stated_unmatched"]
    # The other two fields, which the logbook never mentions, still say not_stated.
    assert {
        r["reason"]
        for rows in left["by_measurement"].values()
        for r in rows
        if r["path"] == "context.electrochemistry.reaction"
    } == {"not_stated"}


def test_the_dry_rule_names_each_contrary_token_once(client, monkeypatch, tmp_path):
    corpus = _copy(tmp_path)
    _add_unit(corpus, "19_04_ZZ4_dry_afterCV")
    env = _candidates(_import(client, _register(monkeypatch, corpus)))["19_04_ZZ4_dry_afterCV::environment"]
    assert env["proposable"] is False
    assert env["not_proposable_reason"].count("`afterCV`") == 1
