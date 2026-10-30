"""LOCAL-2: bundle mutations (annotate, decide, blind protocol), record composition,
validation (draft, official, exactness, offline portal), export and the upload dry run.

Synthetic only: the committed multi-operator corpus, plus hand-made record_groups and
processing_results (LOCAL-P builds the real ones in parallel). The upstream portal
runner is MOCKED here; no test needs the upstream checkout or the network.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
from pathlib import Path

import pytest

import isaac_api.workspace as ws
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import portal as P
from isaac_api.local_import import records as R

REPO_ROOT = ws.REPO_ROOT
SEMANTICS = REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
BY = dict(by="Synthetic Scientist", orcid="0000-0002-1825-0097")


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    out = tmp_path_factory.mktemp("pristine") / "bundle"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    return out


@pytest.fixture()
def bdir(pristine, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(pristine, target)
    return target


def _run(capsys, *argv):
    code = cli.main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def _add_group(bdir: Path, *, verdict: str = "pass") -> None:
    b = M.load(bdir)
    run = b["runs"][0]
    (bdir / "processing").mkdir(exist_ok=True)
    spec = bdir / "processing" / "g1_norm.txt"
    spec.write_text("# SYNTHETIC\n" + "\n".join(f"{1000 + 5 * i} {min(1.0, i / 10):.3f}" for i in range(21)) + "\n")
    b["record_groups"].append(
        {"group_id": "g1", "experiment_key": "exp", "member_run_keys": [run["run_key"]],
         "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}},
         "split_reasons": [], "status": "proposed", "questions": []}
    )
    b["processing_results"].append(
        {"result_id": "p1", "group_id": "g1", "protocol_id": "isaac.xas.synthetic", "protocol_version": "0.1",
         "protocol_status": "draft_unreviewed", "source": "isaac_protocol",
         "inputs": [{"source_id": run["scans"][0]["source_id"], "scan": 1, "channel": "vortDT"}],
         "steps": [{"step": "normalize", "params": {}, "outcome": {}, "flags": []}],
         "outputs": {"files": [{"role": "normalized_spectrum", "relative_path": "processing/g1_norm.txt",
                                "sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}],
                     "e0_eV": 1012.0, "edge_step": 1.0, "points": 21},
         "qc": {"metrics": {}, "verdict": verdict}, "comparison": None, "state": "candidate_extracted"}
    )
    M.save_bundle(bdir, b)


def _miss(b, path, run_id):
    return next(m["value_id"] for m in b["missing_values"] if m["target_field_path"] == path and m["run_id"] == run_id)


def _cand(b, path, run_id):
    return next(c for c in b["candidates"] if c["target_field_path"] == path and c["run_id"] == run_id)


def _decide_everything(bdir: Path, *, temperature=True, sample_form=True) -> None:
    _add_group(bdir)
    b = M.load(bdir)
    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="valid", **BY)
    M.decide(bdir, target_ids=[_cand(b, "timestamps.acquired_start_utc", "run-001")["candidate_id"]], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=[_cand(b, "sample.material.name", "run-001")["candidate_id"]], decision="correct", value="ZZ1 synthetic", **BY)
    M.decide(bdir, target_ids=[_cand(b, "system.technique", None)["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    M.decide(bdir, target_ids=[_miss(b, "system.domain", None)], decision="correct", value="experimental", **BY)
    M.decide(bdir, target_ids=[_miss(b, "attribution.produced_by.group", None)], decision="correct", value="Synthetic Scientist group", **BY)
    M.decide(bdir, target_ids=[_miss(b, "attribution.produced_by.organization", None)], decision="correct", value="Synthetic University", **BY)
    answers = [("context.environment", "ex_situ")]
    if sample_form:
        answers.append(("sample.sample_form", "powder"))
    if temperature:
        answers.append(("context.temperature_K", 298.0))
    for path, value in answers:
        M.decide(bdir, target_ids=[_miss(b, path, "run-001")], decision="correct", value=value, **BY)


def _portal(outcome: str, errors=(), warnings=()):
    def run(record):
        result = {"valid": outcome != "reject", "errors": list(errors), "warnings": list(warnings)}
        return {"status": "ran", "result": result, "outcome": outcome, "held": [], "verdict": outcome}
    return run


def _unavailable(record):
    return {"status": "unavailable", "reason": "not installed (test)", "verdict": P.VERDICT_UNAVAILABLE}


def upstream_like_schema() -> dict:
    """A SYNTHETIC stand-in for the pinned upstream schema (DEC-76): the vendored schema
    plus exactly the upstream shapes the composer writes — attribution.produced_by,
    temperature_K nullable with temperature_basis and its conditional, context.reaction.
    No upstream file is committed; the real one is used only by the opt-in run."""
    schema = json.loads((REPO_ROOT / "schema" / "isaac_record_v1.json").read_text())
    props = schema["properties"]
    props["attribution"]["properties"]["produced_by"] = {
        "type": "object", "additionalProperties": False,
        "properties": {"group": {"type": "string"}, "organization": {"type": "string"},
                       "people": {"type": "array", "items": {"type": "string"}}, "contact": {"type": "string"}},
    }
    ctx = props["context"]
    ctx["properties"]["temperature_K"] = {"type": ["number", "null"]}
    ctx["properties"]["temperature_basis"] = {"type": "string", "enum": ["stated", "room_temperature", "not_reported"]}
    ctx["properties"]["reaction"] = {
        "type": "object", "additionalProperties": False, "required": ["name", "drive", "catalysis"],
        "properties": {"name": {"type": "string"}, "drive": {"type": "string"}, "catalysis": {"type": "string"}},
    }
    ctx["allOf"] = [
        {"if": {"properties": {"temperature_K": {"type": "null"}}, "required": ["temperature_K"]},
         "then": {"properties": {"temperature_basis": {"const": "not_reported"}}, "required": ["temperature_basis"]}},
    ]
    return schema


@pytest.fixture(autouse=True)
def fake_upstream(tmp_path_factory, monkeypatch):
    up = tmp_path_factory.mktemp("upstream")
    (up / "portal").mkdir()
    (up / "portal" / "validation.py").write_text("# synthetic stand-in; never executed (the runner is mocked)\n")
    (up / "schema").mkdir()
    (up / ".git").mkdir()
    (up / ".git" / "HEAD").write_text("a1cb1c8" + "0" * 33 + "\n")
    (up / "schema" / "isaac_record_v1.json").write_text(json.dumps(upstream_like_schema()))
    import sys as _sys

    monkeypatch.setenv(P.DIR_ENV, str(up))
    monkeypatch.setenv(P.PYTHON_ENV, _sys.executable)
    return up


# --- questions.json -----------------------------------------------------------------------


def test_missing_value_questions_are_only_for_values_the_record_requires(pristine):
    """The fine-grained v1 list (bundle.json): missing_value only for REQUIRED fields."""
    b = json.loads((pristine / "bundle.json").read_text())
    required = B.required_record_paths() + B.PORTAL_REQUIRED_PATHS
    missing = {m["value_id"]: m for m in b["missing_values"]}
    qs = [q for q in b["questions"] if q["kind"] == "missing_value"]
    assert qs
    for q in qs:
        path = missing[q["target"]["id"]]["target_field_path"]
        assert B._required_for(path, required), path
        assert q["required_by"]
    asked = {missing[q["target"]["id"]]["target_field_path"] for q in qs}
    assert "system.facility.beamline" not in asked  # missing, but not required
    assert {"context.environment", "context.temperature_K", "system.domain", "attribution.produced_by.group"} <= asked
    order = [q["run_id"] for q in qs]
    assert order[0] is None  # record-scope first, then runs in order
    assert order == sorted(order, key=lambda r: (r is not None, r or ""))


def test_missing_value_questions_follow_record_groups_once_grouped(bdir):
    b = M.load(bdir)
    last = b["runs"][-1]
    b["record_groups"].append({"group_id": "gz", "experiment_key": "e", "member_run_keys": [last["run_key"]],
                               "basis": {"sample": None, "technique": None, "environment": None, "conditions": {}},
                               "split_reasons": [], "status": "proposed", "questions": []})
    M.save_bundle(bdir, b)
    qs = [q for q in M.load(bdir)["questions"] if q["kind"] == "missing_value" and q["run_id"]]
    assert qs[0]["run_id"] == last["run_id"]


# --- summary has no non-conflicting parser values -----------------------------------------------


def test_summary_shows_no_non_conflicting_parser_value(pristine):
    text = (pristine / "summary.md").read_text()
    assert "2100-01-01T00:10:00" not in text  # an extracted acquisition time
    assert "ZZ1" not in text and "ZZ2" not in text  # sample-name readings


# --- blind protocol ----------------------------------------------------------------------------


def test_blind_is_honoured_before_exposure_and_downgraded_after(bdir, capsys):
    b = M.load(bdir)
    a, c2 = [c["candidate_id"] for c in b["candidates"] if c["value"] is not None][:2]
    first = M.annotate(bdir, target_id=a, value="x", excerpt_locator="line 2", source_id=None,
                       model_id="synthetic-model", blind=True, rationale="")
    assert first["blind"] is True
    assert _run(capsys, "bundle", "show", str(bdir), "candidate", c2)[0] == 0
    second = M.annotate(bdir, target_id=c2, value="x", excerpt_locator=None, source_id=None,
                        model_id="synthetic-model", blind=True, rationale="")
    assert second["blind"] is False
    assert "bundle show candidate" in second["blind_basis"]


def test_list_candidates_records_exposures_but_no_values_does_not(bdir, capsys):
    code, out, _ = _run(capsys, "bundle", "list", str(bdir), "candidates", "--limit", "3", "--no-values")
    assert code == 0 and all("value" not in i for i in json.loads(out)["items"])
    assert M.load(bdir)["exposures"] == []
    code, out, _ = _run(capsys, "bundle", "list", str(bdir), "candidates", "--limit", "3")
    ids = {i["candidate_id"] for i in json.loads(out)["items"]}
    assert {e["target"]["id"] for e in M.load(bdir)["exposures"]} == ids


def test_reveal_records_an_exposure_and_compares(bdir):
    b = M.load(bdir)
    c = _cand(b, "timestamps.acquired_start_utc", "run-001")
    M.annotate(bdir, target_id=c["candidate_id"], value=c["value"], excerpt_locator="line 2",
               source_id=c["evidence"][0]["source_id"], model_id="m", blind=True, rationale="")
    shown = M.reveal(bdir, c["candidate_id"])
    assert shown["ai_readings"][0]["agrees_with_parser"] is True
    assert M.exposures_for(M.load(bdir), "candidate", c["candidate_id"])


def test_crosscheck_plan_lists_targets_and_locators_but_no_values(bdir):
    b = M.load(bdir)
    plan = M.crosscheck_plan(b)
    assert plan["total"] == len(plan["items"]) > 0
    cats = {i["category"] for i in plan["items"]}
    assert {"run_association", "herfd_signal_choice", "acquisition_time", "required_by_record"} <= cats
    text = json.dumps(plan)
    for c in b["candidates"]:
        if isinstance(c["value"], str) and len(c["value"]) > 6:
            assert c["value"] not in text
    assert plan["coverage"]["checked"] == 0 and "Spot checks only" in plan["coverage"]["statement"]


def test_excerpt_shows_raw_text_and_refuses_a_changed_source(bdir, tmp_path):
    source = tmp_path / "src"
    shutil.copytree(SEMANTICS, source)
    b = M.load(bdir)
    c = _cand(b, "timestamps.acquired_start_utc", "run-001")
    got = M.excerpt(b, c["candidate_id"], source=str(source))
    assert "#E" in got["excerpts"][0]["text"]
    assert "2100-01-01T00:10:00+00:00" not in json.dumps(got)  # the parser's normalised value
    path = source / c["evidence"][0]["relative_path"]
    path.write_text(path.read_text() + "\n# changed\n")
    again = M.excerpt(b, c["candidate_id"], source=str(source))
    assert "changed since the import" in again["excerpts"][0]["refused"]
    with pytest.raises(M.MutationRefused):
        M.excerpt(b, c["candidate_id"], source=None)


# --- AI interpretation never above needs_review ------------------------------------------------------


def test_an_ai_annotation_never_sets_a_state_above_needs_review(bdir):
    b = M.load(bdir)
    ready = next(c for c in b["candidates"] if c["value_state"] == "candidate_extracted")
    miss = b["missing_values"][0]
    M.annotate(bdir, target_id=ready["candidate_id"], value=ready["value"], excerpt_locator=None,
               source_id=None, model_id="m", blind=False, rationale="")
    M.annotate(bdir, target_id=miss["value_id"], value="anything", excerpt_locator=None,
               source_id=None, model_id="m", blind=False, rationale="")
    b = M.load(bdir)
    by = {c["candidate_id"]: c for c in b["candidates"]}
    assert by[ready["candidate_id"]]["value_state"] == "needs_review"
    assert next(m for m in b["missing_values"] if m["value_id"] == miss["value_id"])["value_state"] == "needs_review"
    assert any(e["method"] == "ai_interpretation" for e in by[ready["candidate_id"]]["evidence"])
    assert b["readiness"]["eligible_value_count"] == 0
    conflict = b["conflicts"][0]["conflict_id"]
    with pytest.raises(M.MutationRefused):
        M.annotate(bdir, target_id=conflict, value="x", excerpt_locator=None, source_id=None,
                   model_id="m", blind=False, rationale="")


# --- decide ---------------------------------------------------------------------------------------


def test_decide_confirms_with_a_local_unverified_identity_and_orcid_as_credit_only(bdir):
    b = M.load(bdir)
    c = _cand(b, "timestamps.acquired_start_utc", "run-001")
    M.decide(bdir, target_ids=[c["candidate_id"]], decision="confirm", value=None, **BY)
    b = M.load(bdir)
    d = b["scientist_decisions"][-1]
    assert d["decided_by"]["identity"] == "local_unverified"
    assert d["decided_by"]["orcid_claimed"] == {"value": BY["orcid"], "basis": "claimed_for_credit_not_authentication"}
    got = next(x for x in b["candidates"] if x["candidate_id"] == c["candidate_id"])
    assert got["value_state"] == "scientist_confirmed" and got["eligibility_for_official_record"]["eligible"]


def test_an_orcid_is_never_authentication(bdir):
    b = M.load(bdir)
    cid = b["candidates"][1]["candidate_id"]
    with pytest.raises(M.MutationRefused):
        M.decide(bdir, target_ids=[cid], decision="confirm", value=None, by="", orcid=BY["orcid"])
    with pytest.raises(M.MutationRefused):
        M.decide(bdir, target_ids=[cid], decision="confirm", value=None, by="X", orcid="not-an-orcid")
    M.decide(bdir, target_ids=[cid], decision="confirm", value=None, by="X", orcid=None)
    assert M.load(bdir)["scientist_decisions"][-1]["decided_by"]["identity"] == "local_unverified"


def test_replaying_the_same_decision_is_idempotent(bdir):
    b = M.load(bdir)
    cid = _cand(b, "timestamps.acquired_start_utc", "run-001")["candidate_id"]
    first = M.decide(bdir, target_ids=[cid], decision="confirm", value=None, **BY)
    before = (bdir / "bundle.json").read_bytes()
    second = M.decide(bdir, target_ids=[cid], decision="confirm", value=None, **BY)
    assert first["recorded"] == [cid] and second == {"recorded": [], "unchanged": [cid], "batch_id": None}
    assert len(M.load(bdir)["scientist_decisions"]) == 1
    assert json.loads((bdir / "bundle.json").read_bytes())["scientist_decisions"] == json.loads(before)["scientist_decisions"]


def test_bulk_confirm_lists_each_decision_and_is_all_or_nothing(bdir, tmp_path):
    b = M.load(bdir)
    good = [c["candidate_id"] for c in b["candidates"] if c["value"] is not None][:3]
    empty = next(c["candidate_id"] for c in b["candidates"] if c["value"] is None)
    f = tmp_path / "targets.json"
    f.write_text(json.dumps(good + [empty]))
    with pytest.raises(M.MutationRefused):
        M.decide(bdir, target_ids=json.loads(f.read_text()), decision="confirm", value=None, **BY)
    assert M.load(bdir)["scientist_decisions"] == []
    f.write_text("\n".join(good))
    code = cli.main(["bundle", "decide", str(bdir), "--targets-file", str(f), "--decision", "confirm", "--by", "S"])
    assert code == 0
    decisions = M.load(bdir)["scientist_decisions"]
    assert [d["target"]["id"] for d in decisions] == good
    assert len({d["batch_id"] for d in decisions}) == 1 and decisions[0]["batch_id"]


def test_a_mutation_that_would_be_invalid_writes_nothing(bdir, monkeypatch):
    before = (bdir / "bundle.json").read_bytes()
    monkeypatch.setattr(B, "validate_bundle", lambda bundle, **_: ["synthetic refusal"])
    with pytest.raises(M.MutationRefused) as raised:
        M.decide(bdir, target_ids=["cand-0002"], decision="confirm", value=None, **BY)
    assert raised.value.code == 5
    assert (bdir / "bundle.json").read_bytes() == before
    assert not list(bdir.glob(".bundle.json.*.tmp"))


def test_a_mutation_regenerates_the_section_files(bdir):
    M.decide(bdir, target_ids=["cand-0002"], decision="confirm", value=None, **BY)
    b = json.loads((bdir / "bundle.json").read_text())
    from isaac_api.local_import import questions as Q

    assert json.loads((bdir / "questions.json").read_text())["questions"] == Q.consolidate(b)["questions"]
    assert B.check_bundle(bdir) == []


def test_group_and_processing_decisions(bdir):
    _add_group(bdir)
    assert M.load(bdir)["record_groups"][0]["status"] == "proposed"
    M.decide(bdir, target_ids=["g1"], decision="split", value=None, split_into=[["a"], ["b"]], **BY)
    assert M.load(bdir)["record_groups"][0]["status"] == "split"
    M.decide(bdir, target_ids=["p1"], decision="needs_changes", value=None, **BY)
    assert M.load(bdir)["processing_results"][0]["state"] == "needs_review"
    with pytest.raises(M.MutationRefused):
        M.decide(bdir, target_ids=["p1"], decision="confirm", value=None, **BY)
    b = M.load(bdir)
    b["record_groups"][0]["status"] = "scientist_confirmed"  # a hand edit, no decision
    b["scientist_decisions"] = [d for d in b["scientist_decisions"] if d["target"]["id"] != "g1"]
    assert any("record group g1" in e for e in B.validate_bundle(b))


# --- build-records ---------------------------------------------------------------------------------


def test_build_records_uses_only_eligible_values(bdir):
    _decide_everything(bdir)
    b = M.load(bdir)
    # an AI reading and an unconfirmed extracted value must not reach the draft
    other = _cand(b, "timestamps.acquired_start_utc", "run-002")
    M.annotate(bdir, target_id=_miss(b, "system.facility.beamline", "run-001"), value="15-2",
               excerpt_locator=None, source_id=None, model_id="m", blind=False, rationale="")
    R.build_records(bdir)
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    fields = draft["fields"]
    assert "system.facility.beamline" not in fields
    assert fields["sample.material.name"]["value"] == "ZZ1 synthetic"
    assert fields["timestamps.acquired_start_utc"]["value"] == "2100-01-01T00:10:00+00:00"
    assert other["value_state"] != "scientist_confirmed"
    for path, env in fields.items():
        if env["status"] != "missing":
            kinds = {e["source_type"] for e in env["evidence"]}
            assert "user_confirmation" in kinds, path
            assert all(e.get("identity", "local_unverified") == "local_unverified" for e in env["evidence"] if e["source_type"] == "user_confirmation")
    assert draft["series"][0]["channels"][0]["values"][-1] == 1.0
    assert draft["qc"] == {"status": "valid"}
    assert draft["descriptors_outputs"][0]["descriptors"][0]["uncertainty"] == {"sigma": None, "basis": "not_reported"}


def test_a_missing_required_value_stays_missing_and_is_listed(bdir):
    _decide_everything(bdir, sample_form=False)
    result = R.build_records(bdir)
    assert result["drafts"][0]["missing_required"] == ["sample.sample_form"]
    assert result["drafts"][0]["complete"] is False
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    assert draft["fields"]["sample.sample_form"] == {"value": None, "status": "missing", "evidence": []}
    report = R.validate_draft_file(draft, run_portal=_portal("publish"))
    assert report["verdict"] == "incomplete"


def test_an_unknown_temperature_is_null_with_basis_not_reported_never_a_default(bdir):
    _decide_everything(bdir, temperature=False)
    result = R.build_records(bdir)
    assert result["drafts"][0]["missing_required"] == []
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    comp = json.loads((bdir / "drafts" / "g1.composition.json").read_text())
    assert draft["fields"]["context.temperature_basis"]["value"] == "not_reported"
    assert "context.temperature_K" not in draft["fields"]
    record = R.compose_record(draft, comp, record_id="0" * 26, now="1970-01-01T00:00:00Z")
    assert record["context"]["temperature_K"] is None
    assert record["context"]["temperature_basis"] == "not_reported"
    report = R.validate_draft_file(draft, run_portal=_portal("publish"), composition=comp)
    assert report["verdict"] == "exportable", report["plain_summary"]


def test_a_reaction_goes_to_context_reaction_name_and_requires_drive_and_catalysis(bdir):
    _decide_everything(bdir)
    b = M.load(bdir)
    rx = next((m["value_id"] for m in b["missing_values"] if m["target_field_path"] == "context.electrochemistry.reaction" and m["run_id"] == "run-001"), None)
    assert rx is not None
    M.decide(bdir, target_ids=[rx], decision="correct", value="OER", **BY)
    R.build_records(bdir)
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    assert draft["fields"]["context.reaction.name"]["value"] == "OER"
    assert "context.electrochemistry.reaction" not in draft["fields"]
    comp = json.loads((bdir / "drafts" / "g1.composition.json").read_text())
    assert {m["path"] for m in comp["missing_required"]} == {"context.reaction.drive", "context.reaction.catalysis"}


def test_an_unconfirmed_group_makes_no_draft(bdir):
    _add_group(bdir)
    result = R.build_records(bdir)
    assert result["drafts"] == [] and result["skipped_groups"][0]["group_id"] == "g1"


# --- validate / export --------------------------------------------------------------------------------


def test_the_portal_verdict_is_surfaced_verbatim(bdir):
    _decide_everything(bdir)
    R.build_records(bdir)
    errors = [{"code": "SYNTHETIC_CODE", "path": "x/y", "message": "verbatim message ✓"}]
    R.validate_records(bdir, run_portal=_portal("reject", errors=errors))
    report = json.loads((bdir / "validation" / "g1.json").read_text())
    assert report["portal_check"]["result"]["errors"] == errors
    assert report["verdict"] == "portal_reject"
    assert any("reject" in line for line in report["plain_summary"])


def test_portal_unavailable_is_never_a_pass_and_blocks_export(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    result = R.export_records(bdir, tmp_path / "records", run_portal=_unavailable)
    assert result["exported"] == [] and result["refused"][0]["verdict"] == "portal_check_unavailable"
    assert not (tmp_path / "records").exists()


@pytest.mark.parametrize("outcome", ["hold", "reject"])
def test_export_refuses_unless_the_portal_says_publish(bdir, tmp_path, outcome):
    _decide_everything(bdir)
    R.build_records(bdir)
    result = R.export_records(bdir, tmp_path / "records", run_portal=_portal(outcome))
    assert result["exported"] == []


def test_an_incomplete_draft_is_never_exported(bdir, tmp_path):
    _decide_everything(bdir, sample_form=False)
    R.build_records(bdir)
    result = R.export_records(bdir, tmp_path / "records", run_portal=_portal("publish"))
    assert result["exported"] == [] and result["refused"][0]["verdict"] == "incomplete"


def fake_upstream_dir() -> Path:
    import os as _os

    return Path(_os.environ[P.DIR_ENV])


def test_a_complete_record_with_portal_publish_is_exported_with_its_sidecar(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    result = R.export_records(bdir, out, run_portal=_portal("publish"))
    assert len(result["exported"]) == 1, result
    rid = result["exported"][0]["record_id"]
    record = json.loads((out / f"{rid}.json").read_text())
    assert (out / f"{rid}.evidence.json").is_file()
    assert (out / f"{rid}.artifacts" / "processing" / "g1_norm.txt").is_file()
    from isaac_records.official import validate_official

    assert validate_official(record, fake_upstream_dir()).ok  # the export target
    assert record["attribution"]["produced_by"] == {"group": "Synthetic Scientist group", "organization": "Synthetic University"}
    assert "uploaded_by" not in record["attribution"]
    assert "NOT claimed valid for the website" in result["exported"][0]["statement"]
    sidecar = json.loads((out / f"{rid}.evidence.json").read_text())
    assert sidecar["schemas_used"]["website_schema"]["gates"] == []


def test_vendored_upstream_drift_is_reported(bdir):
    _decide_everything(bdir)
    R.build_records(bdir)
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    demands = [{"code": "PRODUCED_BY_MISSING", "path": "attribution/produced_by", "message": "state who produced it"}]
    report = R.validate_draft_file(draft, run_portal=_portal("reject", errors=demands))
    assert report["verdict"] == "portal_reject"  # DEC-76: drift is reported, the portal gates
    assert report["schema_drift"]["portal_requires_undeclared_fields"][0]["path"] == "attribution.produced_by"


def test_the_unknown_temperature_drift_is_named(monkeypatch):
    """Upstream allows temperature_K null + temperature_basis not_reported; vendored does not."""
    upstream = json.loads((REPO_ROOT / "schema" / "isaac_record_v1.json").read_text())
    ctx = upstream["properties"]["context"]
    ctx["properties"]["temperature_K"] = {"type": ["number", "null"]}
    ctx["properties"]["temperature_basis"] = {"enum": ["stated", "room_temperature", "not_reported"]}
    record = {"isaac_record_version": "1.05", "record_id": "0" * 26, "record_type": "evidence",
              "record_domain": "characterization", "source_type": "facility",
              "timestamps": {"created_utc": "2026-10-28T00:00:00Z"}, "context": {"environment": "ex_situ"}}
    drift = R.schema_drift(record, upstream)
    assert drift["blocked_by_schema_drift"] is True and "temperature_basis" in drift["temperature"]


# --- upload dry run -------------------------------------------------------------------------------------


def test_upload_refuses_without_dry_run(tmp_path, capsys):
    tmp_path.joinpath("r").mkdir()
    code, _, err = _run(capsys, "bundle", "upload", str(tmp_path / "r"))
    assert code == 2 and "uploads are disabled in this build" in err


def test_upload_dry_run_touches_no_network_and_never_reads_the_token(tmp_path, capsys, monkeypatch):
    records = tmp_path / "records"
    records.mkdir()
    body = b'{"record_id": "SYNTHETIC"}\n'
    (records / "01ABC.json").write_bytes(body)
    (records / "01ABC.evidence.json").write_text("{}")
    monkeypatch.setenv("ISAAC_PORTAL_TOKEN", "SENTINEL-TOKEN-NEVER-PRINTED")

    def no_network(*_a, **_k):
        raise AssertionError("a socket was opened")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    code, out, _ = _run(capsys, "bundle", "upload", str(records), "--dry-run", "--portal-url", "https://portal.invalid")
    assert code == 0
    assert "SENTINEL-TOKEN-NEVER-PRINTED" not in out
    plan = json.loads(out)
    assert plan["network_calls"] == 0 and len(plan["records"]) == 1
    validate, post = plan["records"][0]["requests"]
    assert (validate["method"], validate["url"]) == ("POST", "https://portal.invalid/portal/api/validate")
    assert (post["method"], post["url"]) == ("POST", "https://portal.invalid/portal/api/records")
    assert post["headers"]["Authorization"] == "Bearer <from $ISAAC_PORTAL_TOKEN, not read>"
    assert post["body_bytes"] == len(body) and post["body_sha256"] == hashlib.sha256(body).hexdigest()


def test_the_upload_module_never_reads_the_token_variable():
    import inspect

    source = inspect.getsource(R.upload_plan)
    assert "environ" not in source and "getenv" not in source


# --- portal runner -------------------------------------------------------------------------------------


def test_a_missing_portal_validator_is_reported_as_unavailable(monkeypatch, tmp_path):
    monkeypatch.delenv(P.DIR_ENV, raising=False)
    monkeypatch.setattr(P, "CACHE_ROOT", tmp_path / "nothing")
    check = P.run_portal_check({"x": 1})
    assert check["verdict"] == P.VERDICT_UNAVAILABLE and P.verdict_of(check) == P.VERDICT_UNAVAILABLE


def test_a_degraded_portal_result_is_never_a_publish():
    check = {"status": "ran", "outcome": "publish", "result": {"degraded": [{"layer": "vocabulary"}]}}
    assert P.verdict_of(check) == P.VERDICT_DEGRADED


# --- audit: corrected values' evidence (3), processing-derived missing values (5), re-export (7) ------


def test_a_corrected_value_does_not_cite_the_old_values_quotes_as_support(bdir):
    _decide_everything(bdir)  # corrects sample.material.name; confirms the start time as the file states it
    R.build_records(bdir)
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    corrected = draft["fields"]["sample.material.name"]
    assert corrected["value"] == "ZZ1 synthetic"
    quotes = [e for e in corrected["evidence"] if e["source_type"] == "document"]
    assert quotes, "the file's own statements are kept"
    for e in quotes:
        assert e["relation"] in ("supports", "contradicts") and "relation_to_parser_value" in e
        assert e["quote"] == "ZZ1 synthetic" or e["relation"] == "contradicts"
    [conf] = [e for e in corrected["evidence"] if e["source_type"] == "user_confirmation"]
    assert conf["provenance"] == R.PROVENANCE_CORRECTED and "previous_value" in conf
    confirmed = draft["fields"]["timestamps.acquired_start_utc"]
    assert all(e["relation"] == "supports" and "relation_to_parser_value" not in e
               for e in confirmed["evidence"] if e["source_type"] == "document")
    [conf2] = [e for e in confirmed["evidence"] if e["source_type"] == "user_confirmation"]
    assert conf2["provenance"] == R.PROVENANCE_CONFIRMED and "previous_value" not in conf2


def test_the_relation_label_reaches_the_exported_sidecar(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    result = R.export_records(bdir, out, run_portal=_portal("publish"))
    rid = result["exported"][0]["record_id"]
    sidecar = json.loads((out / f"{rid}.evidence.json").read_text())
    entries = sidecar["evidence"]["sample.material.name"]
    assert any(e.get("provenance") == R.PROVENANCE_CORRECTED for e in entries)
    assert all("relation" in e for e in entries if e.get("source_type") == "document")


def test_validate_says_an_unapproved_processing_result_is_what_is_missing(bdir):
    """Before the fix: verdict invalid_official, "Missing required values: none" — pointing at "correct the value"."""
    _decide_everything(bdir)
    M.decide(bdir, target_ids=["p1"], decision="defer", value=None, **BY)  # the approval is withdrawn
    R.build_records(bdir)
    R.validate_records(bdir, run_portal=_portal("publish"))
    report = json.loads((bdir / "validation" / "g1.json").read_text())
    assert report["verdict"] == "incomplete"
    assert {"measurement.series", "measurement.qc.status", "descriptors.outputs"} <= set(report["missing_required"])
    assert report["missing_from_processing"] and "--target p1 --decision approve --qc-status" in report["processing_fix"]
    summary = "\n".join(report["plain_summary"])
    assert "Missing required values: none" not in summary and "measurement.series" in summary
    assert "isaac bundle decide <bundle_dir> --target p1 --decision approve" in summary


def test_re_exporting_an_unchanged_record_reuses_its_id_and_bytes(bdir, tmp_path, monkeypatch):
    import isaac_records.export as X

    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    first = R.export_records(bdir, out, run_portal=_portal("publish"))
    [row] = first["exported"]
    assert row["export"] == "new"
    rid = row["record_id"]
    files = {p.name: p.read_bytes() for p in out.glob("*.json")}
    # a later export: every clock says another time
    monkeypatch.setattr(M, "now_utc", lambda: "2099-01-01T00:00:00Z")
    monkeypatch.setattr(X, "_now_iso", lambda: "2099-01-01T00:00:00Z")
    second = R.export_records(bdir, out, run_portal=_portal("publish"))
    [row2] = second["exported"]
    assert row2["record_id"] == rid and row2["export"] == "unchanged"
    assert {p.name: p.read_bytes() for p in out.glob("*.json")} == files  # byte for byte; no second record
    assert [p["record"] for p in R.upload_plan(out, None)] == [f"{rid}.json"]  # the index is not a record


def test_re_exporting_a_changed_record_supersedes_the_old_one_and_says_so(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    old = R.export_records(bdir, out, run_portal=_portal("publish"))["exported"][0]["record_id"]
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_cand(b, "sample.material.name", "run-001")["candidate_id"]], decision="correct",
             value="ZZ1 synthetic, revised", **BY)
    R.build_records(bdir)
    [row] = R.export_records(bdir, out, run_portal=_portal("publish"))["exported"]
    assert row["export"] == "replaced" and row["replaces_record_id"] == old and row["record_id"] != old
    assert "new record" in row["export_statement"]
    assert not (out / f"{old}.json").exists() and (out / R.SUPERSEDED_DIR / f"{old}.json").is_file()
    assert [p["record"] for p in R.upload_plan(out, None)] == [f"{row['record_id']}.json"]
    index = json.loads((out / R.EXPORT_INDEX).read_text())
    [entry] = index["records"]
    assert entry["record_id"] == row["record_id"] and entry["replaced_record_ids"] == [old]
