"""Final-review findings (C1, I1, I2, I4, I5 + minors) and the processing interface change
(calibration approvals, approvals bound to file hashes), each reproduced synthetically."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import portal as P
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from tests_support_records import BY, decide_everything, fake_upstream_env, pristine_bundle  # noqa: F401


def _portal(outcome="publish"):
    return lambda record: {"status": "ran", "result": {"valid": True, "errors": [], "warnings": []}, "outcome": outcome, "held": [], "verdict": outcome}


def _with_group(bdir: Path) -> None:
    b = M.load(bdir)
    run = b["runs"][0]
    gdir = bdir / "processing" / "g1"
    gdir.mkdir(parents=True)
    spec = gdir / "normalized.csv"
    spec.write_text("# synthetic\nenergy_eV,norm,flat\n" + "\n".join(f"{1000 + 5 * i},{i / 20:.3f},{i / 20:.3f}" for i in range(21)) + "\n")
    b["record_groups"] = [{"group_id": "g1", "experiment_key": "e", "member_run_keys": [run["run_key"]],
                           "basis": {"sample": None, "technique": None, "environment": None, "conditions": {}},
                           "split_reasons": [], "status": "proposed", "questions": []}]
    b["processing_results"] = [{"result_id": "p1", "group_id": "g1", "protocol_id": "isaac.xas.v0", "protocol_version": "0.1",
                                "protocol_status": "draft_unreviewed", "source": "isaac_protocol", "inputs": [], "steps": [],
                                "outputs": {"files": [{"role": "normalized", "relative_path": "processing/g1/normalized.csv",
                                                       "sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}],
                                            "e0_eV": 1050.0, "edge_step": 1.0, "points": 21},
                                "qc": {"metrics": {}, "verdict": "pass"}, "comparison": None, "state": "candidate_extracted"}]
    M.save_bundle(bdir, b)


@pytest.fixture()
def bdir(pristine_bundle, tmp_path):
    target = tmp_path / "b"
    shutil.copytree(pristine_bundle, target)
    return target


# --- C1: on-disk drafts and overrides are never trusted --------------------------------------------


def test_c1_a_hand_written_draft_with_no_decisions_exports_nothing(bdir, tmp_path, fake_upstream_env):
    drafts = bdir / "drafts"
    drafts.mkdir()
    fake = {"meta": {"record_type": "evidence", "record_domain": "characterization", "source_type": "facility"},
            "fields": {"sample.material.name": {"value": "FABRICATED-BY-AI", "status": "verified",
                                                "evidence": [{"source_type": "user_confirmation", "question": "q", "answer": "a", "timestamp": "2026-01-01T00:00:00Z"}]}}}
    (drafts / "g1.draft.json").write_text(json.dumps(fake))
    (drafts / "g1.composition.json").write_text(json.dumps({"record_overrides": {}}))
    result = R.export_records(bdir, tmp_path / "out", run_portal=_portal())
    assert result["exported"] == []
    assert not (tmp_path / "out").exists()


def test_c1_a_tampered_draft_is_ignored_and_flagged(bdir, tmp_path, fake_upstream_env):
    _with_group(bdir)
    decide_everything(bdir, add_group=False)
    R.build_records(bdir)
    path = bdir / "drafts" / "g1.draft.json"
    draft = json.loads(path.read_text())
    draft["fields"]["sample.material.name"]["value"] = "FABRICATED-BY-AI"
    path.write_text(json.dumps(draft))
    v = R.validate_records(bdir, run_portal=_portal())
    assert v["on_disk_drafts_ignored_because_they_differ"] == ["g1"]
    out = R.export_records(bdir, tmp_path / "out", run_portal=_portal())
    record = json.loads((tmp_path / "out" / out["exported"][0]["record"]).read_text())
    assert record["sample"]["material"]["name"] == "ZZ1 synthetic"
    assert "FABRICATED-BY-AI" not in json.dumps(record)


def test_c1_record_overrides_are_an_allowlist():
    draft = {"meta": {"record_type": "evidence", "record_domain": "characterization", "source_type": "facility"}, "fields": {}}
    with pytest.raises(R.RecordsRefused):
        R.compose_record(draft, {"record_overrides": {"sample.material.name": "X"}}, record_id="0" * 26, now="1970-01-01T00:00:00Z")
    with pytest.raises(R.RecordsRefused):
        R.compose_record(draft, {"record_overrides": {"context.temperature_K": 298}}, record_id="0" * 26, now="1970-01-01T00:00:00Z")
    rec = R.compose_record(draft, {"record_overrides": {"context.temperature_K": None}}, record_id="0" * 26, now="1970-01-01T00:00:00Z")
    assert rec["context"]["temperature_K"] is None


# --- I1: build/validate/export read only a VALIDATED bundle ----------------------------------------------


@pytest.mark.parametrize("command", [["bundle", "build-records"], ["bundle", "validate"], ["bundle", "export", "--out", "OUT"]])
def test_i1_an_edited_eligibility_is_refused_by_every_record_command(bdir, tmp_path, capsys, command):
    b = json.loads((bdir / "bundle.json").read_text())
    c = next(c for c in b["candidates"] if c["target_field_path"])
    c["eligibility_for_official_record"] = {"eligible": True, "reason": "edited"}
    (bdir / "bundle.json").write_bytes(B.encode(b))
    argv = [a if a != "OUT" else str(tmp_path / "out") for a in command]
    code = cli.main(argv[:2] + [str(bdir)] + argv[2:])
    err = capsys.readouterr().err
    assert code == 1 and "does not meet v1" in err and "eligibility" in err


# --- I2: processing outputs stay inside the bundle, verified ---------------------------------------------


def test_i2_an_escaping_processing_output_is_refused(bdir, tmp_path):
    _with_group(bdir)
    b = M.load(bdir)
    b["processing_results"][0]["outputs"]["files"][0]["relative_path"] = "../../ESCAPED.txt"
    assert any("outside the bundle" in e or "relative_path" in e for e in B.validate_bundle(b))
    (tmp_path / "ESCAPED.txt").write_text("x")
    assert R.contained_file(bdir, "../../ESCAPED.txt") is None
    (bdir / "link.txt").symlink_to(tmp_path / "ESCAPED.txt")
    assert R.contained_file(bdir, "link.txt") is None


def test_i2_export_refuses_to_copy_an_artifact_whose_hash_changed(bdir, tmp_path, fake_upstream_env):
    _with_group(bdir)
    decide_everything(bdir, add_group=False)
    out = R.export_records(bdir, tmp_path / "out", run_portal=_portal())
    assert out["exported"][0]["artifacts"] == ["processing/g1/normalized.csv"]
    (bdir / "processing" / "g1" / "normalized.csv").write_text("energy_eV,norm\n1,2\n")
    out = R.export_records(bdir, tmp_path / "out2", run_portal=_portal())
    assert out["exported"] == [] or all(isinstance(a, dict) for a in out["exported"][0]["artifacts"])


# --- I5: groups are presentable through the CLI --------------------------------------------------------------


def test_i5_groups_can_be_listed_and_shown_and_the_mirror_stays_fresh(bdir, capsys):
    code = cli.main(["bundle", "group", str(bdir)])
    printed = json.loads(capsys.readouterr().out)
    assert code == 0 and "isaac bundle list <bundle_dir> groups" in printed["read_them_with"]
    code = cli.main(["bundle", "list", str(bdir), "groups", "--limit", "3"])
    page = json.loads(capsys.readouterr().out)
    assert code == 0 and page["total"] == 9 and {"group_id", "status", "members"} <= set(page["items"][0])
    assert M.load(bdir)["exposures"] == []  # plain fields: no values printed
    gid = page["items"][0]["group_id"]
    assert cli.main(["bundle", "show", str(bdir), "group", gid]) == 0
    capsys.readouterr()
    assert M.load(bdir)["exposures"]  # the basis readings are values: recorded
    assert cli.main(["bundle", "list", str(bdir), "merge-candidates"]) == 0
    mirror = json.loads((bdir / "record_groups.json").read_text())
    assert mirror["record_groups"] == M.load(bdir)["record_groups"]


# --- calibration approval + approvals bound to files -------------------------------------------------------


def test_no_calibration_decision_means_no_approval_is_passed_and_a_decision_is(bdir, monkeypatch):
    from isaac_api.local_import.processing import cli_entry

    M.group(bdir)
    seen = {}
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: seen.update(k) or {"status": "processed", "processing_results": [], "summary": {}})
    M.process(bdir)
    assert seen["calibration_approvals"] == {}
    gid = M.load(bdir)["record_groups"][0]["group_id"]
    with pytest.raises(M.MutationRefused):
        M.decide(bdir, target_ids=[gid], decision="approve_calibration", value=None, element="Zz9", edge="K", **BY)
    M.decide(bdir, target_ids=[gid], decision="approve_calibration", value=None, element="Ir", edge="L3", **BY)
    b = M.load(bdir)
    assert next(g for g in b["record_groups"] if g["group_id"] == gid)["status"] == "proposed"  # not a status decision
    M.process(bdir)
    approval = seen["calibration_approvals"][gid]
    assert approval["element"] == "Ir" and approval["edge"] == "L3" and approval["decided_by"] == BY["by"]
    assert approval["decision_id"] == b["scientist_decisions"][-1]["decision_id"]


def test_an_approval_binds_to_the_exact_files_it_saw(bdir, fake_upstream_env):
    _with_group(bdir)
    decide_everything(bdir, add_group=False)
    d = next(d for d in M.load(bdir)["scientist_decisions"] if d["target"]["id"] == "p1")
    assert d["approved_files"][0]["relative_path"] == "processing/g1/normalized.csv"
    b = M.load(bdir)
    b["processing_results"][0]["outputs"]["files"][0]["sha256"] = "0" * 64  # the result now names other bytes
    M.save_bundle(bdir, b)
    R.build_records(bdir)
    comp = json.loads((bdir / "drafts" / "g1.composition.json").read_text())
    assert "binds to different files" in comp["processing"]["approval"]
    assert "measurement.series" in {m["path"] for m in comp["missing_required"]}


# --- minors ---------------------------------------------------------------------------------------------------


def test_the_test_marker_is_a_fixed_constant_in_notes_only(bdir, fake_upstream_env):
    _with_group(bdir)
    decide_everything(bdir, add_group=False)
    R.build_records(bdir, test_marker=True)
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    assert draft["series"][0]["notes"] == R.TEST_MARKER and draft["qc"]["notes"] == R.TEST_MARKER
    assert "sample.material.notes" not in draft["fields"]
    assert not any(e.get("answer") == R.TEST_MARKER for env in draft["fields"].values() for e in env["evidence"])


def test_a_validator_checkout_off_the_pin_is_unavailable_and_there_is_no_override(fake_upstream_env, monkeypatch):
    assert P.locate()["available"] is True and P.locate()["pinned_commit"] == P.PINNED_COMMIT
    (fake_upstream_env / ".git" / "HEAD").write_text("b" * 40 + "\n")
    where = P.locate()
    assert where["available"] is False and "not the pinned" in where["reason"]
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PIN", "bbbbbbb")  # the removed override does nothing
    assert P.locate()["available"] is False
    assert not hasattr(P, "PIN_ENV")


def test_export_reports_ignored_drafts_and_says_when_nothing_was_exported(bdir, tmp_path, fake_upstream_env, capsys):
    drafts = bdir / "drafts"
    drafts.mkdir()
    (drafts / "hand.draft.json").write_text(json.dumps({"meta": {}, "fields": {}}))
    code = cli.main(["bundle", "export", str(bdir), "--out", str(tmp_path / "out")])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["exported"] == [] and out["statement"] == "Nothing was exported."
    assert out["on_disk_drafts_ignored_with_no_confirmed_group"] == ["hand"]
    _with_group(bdir)
    decide_everything(bdir, add_group=False)
    R.build_records(bdir)
    path = drafts / "g1.draft.json"
    d = json.loads(path.read_text())
    d["fields"]["sample.material.name"]["value"] = "FABRICATED"
    path.write_text(json.dumps(d))
    out = R.export_records(bdir, tmp_path / "out2", run_portal=_portal())
    assert out["on_disk_drafts_ignored_because_they_differ"] == ["g1"] and len(out["exported"]) == 1


def test_the_self_test_marker_state_lives_in_the_bundle_not_in_drafts_index(bdir, tmp_path, fake_upstream_env):
    _with_group(bdir)
    decide_everything(bdir, add_group=False)
    R.build_records(bdir, test_marker=True)
    assert M.load(bdir)["self_test"] == {"test_marker": True, "set_by": "isaac bundle build-records"}
    index = bdir / "drafts" / "index.json"
    data = json.loads(index.read_text())
    data["test_marker"] = False  # tampering the side file changes nothing
    index.write_text(json.dumps(data))
    out = R.export_records(bdir, tmp_path / "out", run_portal=_portal())
    record = json.loads((tmp_path / "out" / out["exported"][0]["record"]).read_text())
    assert record["measurement"]["qc"]["notes"] == R.TEST_MARKER
    R.build_records(bdir)  # a plain build clears it
    assert M.load(bdir)["self_test"]["test_marker"] is False


def test_decide_reports_a_missing_targets_file_and_bad_json_as_messages(bdir, tmp_path, capsys):
    assert cli.main(["bundle", "decide", str(bdir), "--targets-file", str(tmp_path / "nope.txt"), "--decision", "confirm", "--by", "S"]) == 6
    assert "cannot be read" in capsys.readouterr().err
    assert cli.main(["bundle", "decide", str(bdir), "--target", "cand-0002", "--decision", "confirm", "--by", "S", "--split-into", "{bad"]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_questions_before_grouping_say_runs_not_groups(bdir):
    p = Q.consolidate(M.load(bdir))
    env = next(q for q in p["questions"] if q["target_field_path"] == "context.environment")
    assert "run(s), not yet grouped" in env["text"] and "group(s)" not in env["text"].split("—")[0]


# --- engine derivations are recorded and VERIFIED (real-data regression, both classes) ----------------------


class _Item:
    def __init__(self, raw, normalized, rule):
        self.raw_literal, self.normalized_value, self.normalization_rule = raw, normalized, rule
        self.parser_id, self.unit = "synthetic_reader_v1", None


def _evidence(rule: str, value, raw, normalized, norm_rule):
    import isaac_api.historical_import as hist

    c = hist.SemanticCandidate(
        candidate_id="u::x", kind="field", determinism="deterministic", rule=rule, supporting_source_ids=("S",),
        supporting_statements=({"key": "k", "value": raw, "locator": "notes.txt · line 3"},),
        target_field_path="context.environment", proposed_value=value,
    )
    index = {("k", "notes.txt · line 3"): _Item(raw, normalized, norm_rule)}
    evidence, _ = B._evidence_for(c, "cand-0001", "k", ["notes.txt"], {"notes.txt": "src-0001"}, index)
    return {"rule": rule, "evidence": evidence, "value": value}


@pytest.mark.parametrize(
    "label, value, raw, normalized, norm_rule, rule",
    [
        # class 1: a lexicon member picked out of a STRUCTURED logbook reading
        ("lexicon_member", "flow_cell", "SYNTHETIC: measured in the flow cell",
         {"member": "flow_cell", "term": "flow cell", "status": "matched"},
         "bl15.notes.cell_type_statement.v1: lexicon", "bl15.notes.cell_type_statement.v1: a logbook sentence names the cell"),
        # class 2: a STORED RULE derives the value from a reading (dry sample -> ex_situ)
        ("stored_rule", "ex_situ", "dry", None, None,
         "bl15.environment.dry_sample_is_ex_situ.v1: a dry sample is measured ex situ"),
    ],
)
def test_an_engine_derivation_is_recorded_as_a_verifiable_step(label, value, raw, normalized, norm_rule, rule):
    cand = _evidence(rule, value, raw, normalized, norm_rule)
    steps = cand["evidence"][0]["normalization"]
    assert steps[-1]["step"] == "derive" and steps[-1]["rule_id"] == rule.split(":")[0] and steps[-1]["to"] == value
    assert json.dumps(value) in B.witnessed_values(cand)


def test_a_derive_step_naming_another_rule_or_an_unwitnessed_source_launders_nothing():
    cand = _evidence("bl15.environment.dry_sample_is_ex_situ.v1: x", "ex_situ", "dry", None, None)
    step = cand["evidence"][0]["normalization"][-1]
    step["rule_id"] = "made.up.rule.v1"
    assert json.dumps("ex_situ") not in B.witnessed_values(cand)
    step["rule_id"], step["from"] = "bl15.environment.dry_sample_is_ex_situ.v1", "nothing any file says"
    assert json.dumps("ex_situ") not in B.witnessed_values(cand)


def test_a_value_with_no_named_rule_gets_no_step():
    cand = _evidence("Read from 1 source, exactly as written.", "invented", "dry", None, None)
    assert cand["evidence"][0]["normalization"] == [] and json.dumps("invented") not in B.witnessed_values(cand)


# --- set_counter_positions -----------------------------------------------------------------------------------


def test_set_counter_positions_is_validated_idempotent_and_superseded(bdir, capsys):
    argv = ["bundle", "decide", str(bdir), "--target", "experiment", "--decision", "set_counter_positions", "--by", "S"]
    assert cli.main(argv + ["--positions", "2"]) == 0
    d = M.load(bdir)["scientist_decisions"][-1]
    assert d["decision"] == "set_counter_positions" and d["target"] == {"kind": "experiment", "id": "experiment"}
    assert d["positions"] == [2] and d["decided_by"]["identity"] == "local_unverified" and d["decision_id"]
    assert cli.main(argv + ["--positions", "2"]) == 0  # replay: no new entry
    assert len(M.load(bdir)["scientist_decisions"]) == 1
    for bad in ("0", "-2", "a", "1,2,3,4,5,6,7,8,9"):  # 1.9.0: -1 (`last`) is the last token, accepted
        assert cli.main(argv + ["--positions", bad]) == 2
    assert cli.main(argv + ["--positions", "2,3"]) == 0
    b = M.load(bdir)
    assert len(b["scientist_decisions"]) == 2 and M.counter_positions(b) == [2, 3]  # later supersedes, all kept
    assert B.check_bundle(bdir) == []
    capsys.readouterr()


def test_the_grouping_counter_question_is_surfaced_with_its_command(bdir):
    b = M.load(bdir)
    b["grouping_questions"] = [{"kind": "naming_counter_positions", "text": "Which filename positions are counters?"}]
    M.save_bundle(bdir, b)
    q = next(q for q in Q.consolidate(M.load(bdir))["questions"] if q["kind"] == "naming_counter_positions")
    assert q["scope"] == "experiment"
    assert "--target experiment --decision set_counter_positions --positions" in q["answer_command"]
    assert "isaac bundle group <bundle_dir> --regroup" in q["answer_command"]


def test_every_decision_needs_a_decider_name_and_counter_positions_ignore_one_without(bdir):
    M.decide(bdir, target_ids=["experiment"], decision="set_counter_positions", value=None, positions=[2], **BY)
    b = M.load(bdir)
    forged = dict(b["scientist_decisions"][-1], decision_id="d-99999", positions=[3],
                  decided_by={"name": "", "basis": "self_reported_local_user", "identity": "local_unverified", "orcid_claimed": None})
    b["scientist_decisions"].append(forged)
    assert any("no decider name" in e for e in B.validate_bundle(b))
    assert M.counter_positions(b) == [2]  # the nameless one is ignored
    for bad in ("", "   ", "a\x00b", "x" * 201):
        with pytest.raises(M.MutationRefused):
            M.decide(bdir, target_ids=["experiment"], decision="set_counter_positions", value=None, positions=[3], by=bad, orcid=None)


def test_a_proposed_group_with_condition_violations_is_invalid(bdir):
    M.group(bdir)
    b = M.load(bdir)
    assert all("condition_violations" in g for g in b["record_groups"])
    b["record_groups"][0]["condition_violations"] = [{"condition": "potential", "values": ["a", "b"]}]
    assert any("condition violations" in e for e in B.validate_bundle(b))
