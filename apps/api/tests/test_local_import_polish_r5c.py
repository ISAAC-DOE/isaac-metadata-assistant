"""Polish r5c: real-data findings on mutations, records and the CLI. SYNTHETIC only: every name, scan, Athena
version and value below is invented.

* (C1) Choosing an Athena version that is not the approved result says so in the ``select_athena_version`` reply, and
  ``build-records``, ``validate`` and ``export`` warn ``athena_version_no_longer_chosen`` until it is settled.
* (C2) A merged group's id follows its runs only (the same merges in another order give the same group); an id a
  regroup already stored stays.
* (C3) The sample a merge needs confirmed is the record's material name, and its command and sentence say so.
* (C4) A bulk call names every target it refuses, in one refusal.
* (C5) ``records_written`` counts only the records this export wrote (new or replacing); ``records_ready`` all.
* (C6) A set-point nobody answered lists its potential scale as missing too; a warning's ``also_needs`` and
  ``also_command`` reach the printed ``warnings`` rows.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_capture_decisions import _combined, _grouped_stems
from test_local_import_records import (BY, _decide_everything, _portal, bdir, fake_upstream,  # noqa: F401  (fixtures)
                                       pristine)

SYN = "SYNTHETIC TEST"


# --- C1: the approved curve is not the version chosen last ------------------------------------------------------


def _with_versions(bdir_):
    """The approved ISAAC result p1 lists two invented Athena versions."""
    b = M.load(bdir_)
    p1 = next(r for r in b["processing_results"] if r["result_id"] == "p1")
    p1["athena_versions"] = [
        {"version_id": f"g1-v0{n}", "provenance": {"prj_relative_path": f"SYN_{n}.prj", "athena_group": "SYN_merged",
                                                   "data_sha256_prefix": f"{n}" * 12}} for n in (1, 2)]
    M.save_bundle(bdir_, b)


def test_choosing_a_version_after_approving_isaacs_curve_is_said_and_warned(bdir):
    _decide_everything(bdir)
    _with_versions(bdir)
    out = M.decide(bdir, target_ids=["p1"], decision="select_athena_version", value="g1-v02", **BY)
    [said] = out["approved_result_not_chosen"]
    assert said["approved_result_id"] == "p1" and said["chosen_value"] == "g1-v02" and said["chosen_result_id"] is None
    assert "The record carries the E0 and curve of p1, not of g1-v02" in out["statement"]
    assert "ISAAC's own curve" in out["statement"] and "isaac process <bundle_dir>" in out["statement"]
    built = R.build_records(bdir)
    assert any(w["code"] == R.ATHENA_NOT_CHOSEN_WARNING for w in built["warnings"])
    v = R.validate_records(bdir, run_portal=_portal("publish"))
    [w] = [w for w in v["warnings"] if w["code"] == R.ATHENA_NOT_CHOSEN_WARNING]
    assert w["group_id"] == "g1" and "--target p1 --decision reject" in w["command"]
    assert v["exportable"] == 1  # a warning, never a refusal
    ex = R.export_records(bdir, bdir.parent / "out", run_portal=_portal("publish"))
    [row] = ex["exported"]
    assert any(x.startswith("Written with an approved curve that is not the chosen Athena version")
               for x in row["warnings"])


def test_choosing_a_version_before_approving_isaacs_curve_is_the_scientists_later_word(bdir):
    from test_local_import_records import _add_group

    _add_group(bdir)
    _with_versions(bdir)
    M.decide(bdir, target_ids=["p1"], decision="select_athena_version", value="g1-v02", **BY)
    M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="valid", **BY)
    b = M.load(bdir)
    p1 = next(r for r in b["processing_results"] if r["result_id"] == "p1")
    assert R.athena_choice_mismatch(b, "g1", p1) is None


def _ath(version, decision_id, state="scientist_confirmed"):
    return {"result_id": f"proc-g1-r-{'0' * 16}-athena-{version}", "group_id": "g1", "source": "scientist_athena",
            "athena_version_id": f"g1-{version}", "state": state,
            "athena_version_selected": {"decision_id": decision_id}}


def _select(decision_id, version):
    return {"decision_id": decision_id, "decision": B.ATHENA_SELECT_DECISION, "value": f"g1-{version}",
            "target": {"kind": "processing_result", "id": f"proc-g1-r-{'0' * 16}-isaac"},
            "athena_version_provenance": {"prj_relative_path": f"SYN_{version}.prj", "athena_group": "SYN_m",
                                          "data_sha256_prefix": version * 6}}


def test_an_approved_version_that_is_no_longer_the_choice_names_both_steps():
    v02 = _ath("v02", "d-00001")
    v01 = _ath("v01", "d-00003", state="needs_review")
    bundle = {"scientist_decisions": [_select("d-00001", "v02"),
                                      {"decision_id": "d-00002", "decision": "approve",
                                       "target": {"kind": "processing_result", "id": v02["result_id"]}},
                                      _select("d-00003", "v01")],
              "processing_results": [v02, v01]}
    m = R.athena_choice_mismatch(bundle, "g1", v02)
    assert m["approved_version_id"] == "g1-v02" and m["chosen_value"] == "g1-v01"
    assert m["chosen_result_id"] == v01["result_id"]
    text = R.athena_choice_text(m, "g1")
    assert f"reject {v02['result_id']}" in text and f"then approve {v01['result_id']}" in text
    # the approved version IS the latest choice: nothing to say
    same = {**bundle, "scientist_decisions": bundle["scientist_decisions"][:2]}
    assert R.athena_choice_mismatch(same, "g1", v02) is None


def test_reselecting_after_an_approval_is_said_by_the_select_reply_itself(tmp_path, capsys):
    from test_local_import_polish_r1a import _processing, _results, _versions_case

    _processing()
    bdir_, root = _versions_case(tmp_path)
    M.process(bdir_, source=str(root))
    [isa] = _results(bdir_, "isaac_protocol")
    v01, v02 = isa["athena_versions"]
    M.decide(bdir_, target_ids=[isa["result_id"]], decision="select_athena_version", value=v02["version_id"], **BY)
    M.process(bdir_, source=str(root))
    [a2] = _results(bdir_, "scientist_athena")
    M.decide(bdir_, target_ids=[a2["result_id"]], decision="approve", value=None, qc_status="valid", **BY)
    out = M.decide(bdir_, target_ids=[isa["result_id"]], decision="select_athena_version", value=v01["version_id"], **BY)
    capsys.readouterr()
    [said] = out["approved_result_not_chosen"]
    assert said["approved_result_id"] == a2["result_id"] and said["chosen_value"] == v01["version_id"]
    assert f"reject {a2['result_id']}" in out["statement"]


# --- C2: a merged group's id follows its runs ---------------------------------------------------------------------


STEMS = ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_400mV_again"]


def _merged_id(tmp_path, name, *, earlier_answers: int):
    b = _grouped_stems(tmp_path / name, STEMS)
    g1, g2 = M.load(b)["record_groups"]
    for _ in range(earlier_answers):  # other answers first: the merge decision gets another id
        M.decide(b, target_ids=["experiment"], decision="defer", value=None, by=SYN, orcid=None)
        M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=SYN, orcid=None,
                 positions=[9])
    M.decide(b, target_ids=[g2["group_id"]], decision="merge", value=None, by=SYN, orcid=None,
             merge_with=[g1["group_id"]])
    M.group(b, regroup=True)
    [c] = _combined(b)
    return b, c


def test_the_same_merge_in_another_order_gives_the_same_group_id(tmp_path):
    b, first = _merged_id(tmp_path, "a", earlier_answers=0)
    _, later = _merged_id(tmp_path, "b", earlier_answers=2)
    assert first["merged_by_decision"]["decision_id"] != later["merged_by_decision"]["decision_id"]
    assert first["group_id"] == later["group_id"]
    assert first["group_id"] == G.group_id_for(G.experiment_key_of(M.load(b)),
                                               list(first["member_run_keys"]) + [M.MERGED_ID_MARKER])


def test_a_merged_group_id_stored_before_r5_stays(tmp_path):
    b, c = _merged_id(tmp_path, "a", earlier_answers=0)
    bundle = M.load(b)
    exp_key = G.experiment_key_of(bundle)
    legacy = G.group_id_for(exp_key, list(c["member_run_keys"]) + [f"merged-by:{c['merged_by_decision']['decision_id']}"])
    assert legacy != c["group_id"]
    for g in bundle["record_groups"]:
        if g["group_id"] == c["group_id"]:
            g["group_id"] = legacy  # as a regroup before r5 stored it
    M.save_bundle(b, bundle)
    M.group(b, regroup=True)
    [again] = _combined(b)
    assert again["group_id"] == legacy


def test_a_later_merge_of_runs_whose_merged_group_was_rejected_is_proposed_again():
    members = ["rk-1", "rk-2"]
    first = {"decision_id": "d-00001"}
    gid = M.merge_group_id_for("exp", members, first)
    taken = {gid: {"group_id": gid, "status": "rejected", "merged_by_decision": {"decision_id": "d-00001"}}}
    assert M.merge_group_id_for("exp", members, first, taken=taken) == gid  # this decision's own ruling: H1
    later = M.merge_group_id_for("exp", members, {"decision_id": "d-00009"}, taken=taken)
    assert later != gid  # a newer merge is not read as the earlier ruling
    assert M.merge_group_id_for("exp", list(reversed(members)), first) == gid


# --- C3: the merge's sample is the record's material name -------------------------------------------------------


def test_the_merge_sample_step_says_it_is_the_records_material_name(tmp_path):
    b = _grouped_stems(tmp_path, ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_400mV_newspot"])
    g1, g2 = M.load(b)["record_groups"]
    M.decide(b, target_ids=[g1["group_id"]], decision="merge", value=None, by=SYN, orcid=None,
             merge_with=[g2["group_id"]])
    [nc] = M.group(b, regroup=True)["merge_decisions_not_combined"]
    assert M.SAMPLE_STEP_SAID in nc["reason"]
    samples = [c for c in nc["next_commands"] if "--decision correct" in c]
    assert samples and all(M.MATERIAL_NAME_PLACEHOLDER in c for c in samples)
    assert "<the sample>" not in nc["reason"]


def test_the_merge_sample_step_names_what_sibling_runs_of_the_sample_carry():
    def cand(cid, run, lit):
        return {"candidate_id": cid, "run_id": run, "target_field_path": M.MERGE_SAMPLE_PATH, "value": None,
                "value_state": "scientist_confirmed", "eligibility_for_official_record": {"eligible": True},
                "evidence": [{"literal_value": lit}]}

    bundle = {"runs": [{"run_key": f"k{i}", "run_id": f"run-{i}"} for i in (1, 2, 3)],
              "candidates": [cand("c1", "run-1", "ZZ3"), cand("c2", "run-2", "ZZ3"), cand("c3", "run-3", "ZZ3")],
              "missing_values": [], "conflicts": [],
              "scientist_decisions": [{"decision_id": "d-00001", "decision": "correct", "value": "SYN full (ZZ3)",
                                       "target": {"kind": "candidate", "id": "c3"}}]}
    hint = M.material_name_hint(bundle, [{"member_run_keys": ["k1"]}, {"member_run_keys": ["k2"]}])
    assert hint == " (other runs whose files name this sample (ZZ3) carry 'SYN full (ZZ3)')"
    assert M.material_name_hint({**bundle, "scientist_decisions": []}, [{"member_run_keys": ["k1"]}]) == ""


# --- C4: a bulk refusal names every refused target ---------------------------------------------------------------


def test_a_bulk_refusal_names_every_refused_target_and_one_keeps_its_own_sentence():
    held = [("p-a", "p-a carries an outlier scan: SYN one. Nothing was recorded."),
            ("p-b", "p-b carries one scan's glitch on the edge. Nothing was recorded.")]
    text = M.bulk_refusal(held, 5, "approve")
    assert text.startswith("2 of the 5 targets of this approve cannot be recorded in one call, so nothing was recorded.")
    assert "(1) p-a carries an outlier scan: SYN one. (2) p-b carries" in text
    assert "without these 2 (p-a, p-b)" in text
    assert M.bulk_refusal(held[:1], 5, "approve") == held[0][1]


def test_a_bulk_confirm_names_every_target_it_refuses(bdir):
    from test_local_import_records import _add_group

    _add_group(bdir)
    b = M.load(bdir)
    unvalued = [c["candidate_id"] for c in b["candidates"] if c.get("value") is None][:2]
    if len(unvalued) < 2:
        pytest.skip("the fixture has fewer than two candidates with no value")
    valued = next(c["candidate_id"] for c in b["candidates"] if c.get("value") is not None)
    before = len(b["scientist_decisions"])
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=[unvalued[0], valued, unvalued[1]], decision="confirm", value=None, **BY)
    said = str(exc.value)
    assert said.startswith("2 of the 3 targets") and unvalued[0] in said and unvalued[1] in said
    assert len(M.load(bdir)["scientist_decisions"]) == before


# --- C5: records_written counts only what this export wrote ------------------------------------------------------


def test_an_unchanged_reexport_writes_nothing_and_says_so(bdir, tmp_path):
    _decide_everything(bdir)
    out = tmp_path / "records"
    first = R.export_records(bdir, out, run_portal=_portal("publish"))
    n = first["records_ready"]
    assert n >= 1 and first["records_written"] == n and first["records_unchanged"] == 0
    again = R.export_records(bdir, out, run_portal=_portal("publish"))
    assert (again["records_ready"], again["records_written"], again["records_unchanged"]) == (n, 0, n)
    assert "records_written_with_warnings" not in again
    assert "were written with a warning" not in again["outcome"]


def test_the_outcome_counts_warned_records_written_apart_from_unchanged_ones(tmp_path):
    text = R.export_outcome(3, 0, 0, tmp_path, warned=1, unchanged=2, warned_unchanged=2)
    assert "1 record(s) were written with a warning that still applies" in text
    assert "2 unchanged record(s) still carry a warning that applies" in text
    assert "were written with a warning" not in R.export_outcome(2, 0, 0, tmp_path, unchanged=2, warned_unchanged=2)


# --- C6: the scale beside a missing set-point; also_needs in the rows -----------------------------------------------


def test_a_missing_setpoint_lists_its_scale_as_missing_with_why():
    report = {"missing_required": [{"path": R.SETPOINT_PATH, "from": R.FROM_AN_ANSWER}], "filled": []}
    [extra] = Q._companions_missing(report)
    assert extra["path"] == R.SCALE_PATH and extra["asked_with"] == R.SETPOINT_PATH
    report["missing_required"].append(extra)
    assert Q._companions_missing(report) == []  # listed once
    assert Q._answer_missing(report) == [R.SETPOINT_PATH, R.SCALE_PATH]
    assert R.SCALE_PATH in Q._required_because(report)


def test_warning_rows_keep_the_second_step():
    w = {"group_id": "g1", "code": R.STATED_POTENTIAL_WARNING, "text": "SYN both", "command": "SYN scale",
         "also_needs": R.SETPOINT_PATH, "also_command": "SYN set-point"}
    [row] = R.warning_summary([w])["warnings"]
    assert row["also_needs"] == R.SETPOINT_PATH and row["also_command"] == "SYN set-point"
    [plain] = R.warning_summary([{k: w[k] for k in ("group_id", "code", "text", "command")}])["warnings"]
    assert "also_needs" not in plain


def test_the_docs_say_the_new_counts_and_warning():
    from pathlib import Path

    skill = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "isaac-historical-import"
    records = (skill / "reference" / "records-and-validation.md").read_text()
    main = (skill / "SKILL.md").read_text()
    for term in ("records_ready", R.ATHENA_NOT_CHOSEN_WARNING, "also_command"):
        assert term in records and term in main, term
    assert json.dumps(M.MATERIAL_NAME_PLACEHOLDER) and "material-name answer" in (
        skill / "reference" / "grouping-and-processing.md").read_text()


# --- r5c review: MED-1, MED-2, LOW-1..LOW-4 ------------------------------------------------------------------------


def _two_results(bdir_):
    import copy

    from test_local_import_records import _add_group

    _add_group(bdir_)
    b = M.load(bdir_)
    p1 = next(r for r in b["processing_results"] if r["result_id"] == "p1")
    g1 = next(g for g in b["record_groups"] if g["group_id"] == "g1")
    p2 = {**copy.deepcopy(p1), "result_id": "p2", "group_id": "g2"}
    g2 = {**copy.deepcopy(g1), "group_id": "g2", "member_run_keys": [b["runs"][1]["run_key"]]}
    b["record_groups"].append(g2)
    b["processing_results"].append(p2)
    M.save_bundle(bdir_, b)


def test_a_bulk_approve_without_qc_status_is_refused_once_as_a_call(bdir):
    _two_results(bdir)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=["p1", "p2"], decision="approve", value=None, **BY)
    said = str(exc.value)
    assert said.count("needs --qc-status") == 1 and "targets of this" not in said and "The others" not in said
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=["g1", "g2"], decision="confirm", value=None, qc_status="valid", **BY)
    assert str(exc.value).count("--qc-status") == 1 and "targets of this" not in str(exc.value)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=["p1", "p2"], decision="approve", value=None, qc_status="valid", e0_measured=True, **BY)
    assert str(exc.value).count("--e0-measured applies only") == 1 and "no target of this call" in str(exc.value)


def test_a_bulk_refusal_merges_identical_reasons_and_offers_no_others_when_all_are_refused():
    held = [("p-a", "p-a is held: SYN reason. Nothing was recorded."), ("p-b", "p-b is held: SYN reason.")]
    text = M.bulk_refusal(held, 2, "approve")
    assert "p-a, p-b: <this target> is held: SYN reason." in text
    assert "The others are not refused" not in text and "Decide each of them as its reason says." in text
    mixed = M.bulk_refusal(held + [("p-c", "p-c differs.")], 5, "approve")
    assert "(1) p-a, p-b:" in mixed and "(2) p-c differs." in mixed and "without these 3 (p-a, p-b, p-c)" in mixed


def test_an_unknown_id_in_a_bulk_call_is_named_with_the_other_refused_targets(bdir):
    _two_results(bdir)
    b = M.load(bdir)
    valued = next(c["candidate_id"] for c in b["candidates"] if c.get("value") is not None)
    unvalued = next(c["candidate_id"] for c in b["candidates"] if c.get("value") is None)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=[valued, "cand-SYN-none", unvalued], decision="confirm", value=None, **BY)
    said = str(exc.value)
    assert said.startswith("2 of the 3 targets") and "cand-SYN-none" in said and unvalued in said
    assert exc.value.code == 6  # the unknown id's exit code
    with pytest.raises(M.MutationRefused) as one:
        M.decide(bdir, target_ids=[valued, "cand-SYN-none"], decision="confirm", value=None, **BY)
    assert str(one.value) == "No target with id 'cand-SYN-none' in this bundle." and one.value.code == 6


def _default_athena_case(inputs):
    ath = {"result_id": "proc-g1-r-" + "0" * 16 + "-athena", "group_id": "g1", "source": "scientist_athena",
           "state": "scientist_confirmed", "inputs": inputs}
    isa = {"result_id": "proc-g1-r-" + "0" * 16 + "-isaac", "group_id": "g1", "source": "isaac_protocol",
           "state": "needs_review"}
    bundle = {"scientist_decisions": [
        {"decision_id": "d-00001", "decision": "approve", "target": {"kind": "processing_result", "id": ath["result_id"]}},
        {"decision_id": "d-00002", "decision": B.ATHENA_SELECT_DECISION, "value": "g1-v01",
         "target": {"kind": "processing_result", "id": isa["result_id"]},
         "athena_version_provenance": {"prj_relative_path": "SYN_a.prj", "athena_group": "SYN_X",
                                       "data_sha256_prefix": "abc"}}],
        "processing_results": [ath, isa]}
    return bundle, ath


def test_the_default_athena_result_is_called_an_athena_curve_and_its_own_curve_is_no_mismatch():
    bundle, ath = _default_athena_case([{"relative_path": "SYN_b.prj", "athena_group": "SYN_Y", "used": True}])
    m = R.athena_choice_mismatch(bundle, "g1", ath)
    text = R.athena_choice_text(m, "g1")
    assert m["approved_kind"] == "athena" and "ISAAC's own curve" not in text
    assert "the scientist's Athena curve from another project or Athena group" in text
    assert "to keep this curve, reject it and approve it again" in text
    same, ath2 = _default_athena_case([{"relative_path": "SYN_a.prj", "athena_group": "SYN_X", "used": True}])
    assert R.athena_choice_mismatch(same, "g1", ath2) is None


def test_keeping_an_approved_version_means_choosing_it_again():
    v02 = _ath("v02", "d-00001")
    bundle = {"scientist_decisions": [_select("d-00001", "v02"),
                                      {"decision_id": "d-00002", "decision": "approve",
                                       "target": {"kind": "processing_result", "id": v02["result_id"]}},
                                      _select("d-00003", "v01")],
              "processing_results": [v02]}
    text = R.athena_choice_text(R.athena_choice_mismatch(bundle, "g1", v02), "g1")
    assert "to keep this curve, choose g1-v02 again" in text and "--decision select_athena_version --value g1-v02" in text


def test_the_mismatch_reads_only_what_the_choices_index_holds():
    """MED-2: given the index, the mismatch reads no decision log and no result list of the bundle."""
    v02 = _ath("v02", "d-00001")
    full = {"scientist_decisions": [_select("d-00001", "v02"),
                                    {"decision_id": "d-00002", "decision": "approve",
                                     "target": {"kind": "processing_result", "id": v02["result_id"]}},
                                    _select("d-00003", "v01")],
            "processing_results": [v02]}
    choices = R.athena_choices(full)

    class NoScan(dict):
        def get(self, key, default=None):
            if key in ("scientist_decisions", "processing_results"):
                raise AssertionError(f"read {key}")
            return super().get(key, default)

    assert R.athena_choice_mismatch(NoScan(), "g1", v02, choices, {})["chosen_value"] == "g1-v01"


def test_the_commands_doc_names_both_warning_counts():
    from pathlib import Path

    commands = (Path(__file__).resolve().parents[3] / ".claude" / "skills" / "isaac-historical-import" / "reference"
                / "commands.md").read_text()
    assert "records_ready_with_warnings" in commands and "records_written_with_warnings" in commands
