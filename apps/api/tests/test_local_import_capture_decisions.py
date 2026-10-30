"""DEC-91 (bundle 1.6.0): question ids that survive answers, and three capture decisions.

* **Question-id stability.** Answering one consolidated question — or one group of it — leaves
  every OTHER open question's id unchanged: the open ids after are a subset of the ids before,
  except the documented unlocks (a stated clock zone unlocks the start-time confirmations it
  gives; a stated control mode makes its set-point required).
* **keep_apart** on a merge candidate: recorded, the candidate is no longer open, no group moves.
* **select_athena_version** on a processing result: only a listed version; state, QC and
  processed values untouched; the result's own question and flag drop out.
* **set_not_counter_positions**: "none of these positions is a counter"; grouping is unchanged
  by it, and the counter question drops out (as it now does after set_counter_positions too).
* **merge** is applied by the regroup as ONE combined group (tests in test_local_import_regroup_overlap).

SYNTHETIC fixtures only (the committed multi-operator corpus, the SYN counter folder, invented
XDC scans dated 2099).
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_grouping_cli import FIXTURE, _folder
from tests_support_records import SEMANTICS, pristine_bundle  # noqa: F401

BY = "SYNTHETIC TEST"
SETPOINT_PATHS = ("context.electrochemistry.potential_setpoint_V", "context.electrochemistry.current_setpoint_mA_cm2")


def _ids(payload) -> set[str]:
    return {q["question_id"] for q in payload["questions"]}


def _answer(bundle: dict, payload: dict, q: dict, *, partial: bool) -> tuple[str | None, bool]:
    """Answer ``q`` in memory (one scope of it when ``partial`` and it has several). Returns the
    field answered (optional values) and whether the answer was partial."""
    scopes = list(q["per_scope_targets"])
    only = scopes[0] if partial and len(scopes) > 1 else None
    field = sorted(q["fields"])[0] if q["kind"] == "optional_values" else None
    kw: dict = {}
    if q["kind"] in ("missing_value", "optional_values", "confirm_value", "resolve_conflict"):
        allowed = (q.get("field_allowed_values") or {}).get(field) if field else q.get("allowed_values")
        decision, value = "correct", (allowed[0] if allowed else "SYNTHETIC TEST VALUE")
    elif q["kind"] == "confirm_absorber":
        decision, value, kw = "set_absorber", None, {"element": "Fe", "edge": "K"}
    elif q["kind"] == "naming_counter_positions":
        decision, value, kw = B.NOT_COUNTER_DECISION, None, {"positions": q["positions"]}
    elif q["kind"] == "clock_time_zone":
        decision, value = B.CLOCK_ZONE_DECISION, "UTC"
    else:  # pragma: no cover - a new kind must be added here
        raise AssertionError(f"unhandled question kind {q['kind']}")
    targets = Q.targets_for(payload, q["question_id"], only, field)
    assert targets, q["question_id"]
    # `decide` refuses a value its field refuses (contract §25): a free-text answer where the field is a
    # zoned UTC instant or a number is tried in that shape instead (a refusal records nothing)
    for attempt in ([value] if decision != "correct" or allowed else [value, "2099-01-01T00:00:00Z", 1.0]):
        try:
            M.record_decision(bundle, target_ids=targets, decision=decision, value=attempt, by=BY, orcid=None, **kw)
            break
        except M.MutationRefused:
            if attempt == 1.0:
                raise
    B.refresh_questions(bundle)
    B.apply_derivations(bundle)
    return field, only is not None


def _unlock_allowed(answered: dict, field: str | None, new: dict) -> bool:
    """The documented unlocks (questions.py docstring): never a rename of an existing question."""
    if answered["kind"] == "clock_time_zone":
        return new["kind"] == "confirm_value" and new["target_field_path"] == B.XDC_START_PATH
    if B.CONTROL_MODE_PATH in (field, answered.get("target_field_path")):
        return new["kind"] == "missing_value" and new["target_field_path"] in SETPOINT_PATHS
    return False


def _check_every_kind(bundle: dict, per_bucket: int = 2) -> set[tuple[str, str]]:
    """Answer up to ``per_bucket`` questions of each (kind, partition class), fully and partially,
    each on a fresh copy; assert the ids that are open afterwards were open before."""
    payload = Q.consolidate(bundle)
    before = _ids(payload)
    buckets: dict[tuple[str, str], list[dict]] = {}
    for q in payload["questions"]:
        part = "none" if not q.get("partition") else ("sample=unrecorded" if q["partition"] == "sample=unrecorded" else "sample=<reading>")
        buckets.setdefault((q["kind"], part), []).append(q)
    for qs in buckets.values():
        for q in qs[:per_bucket]:
            for partial in (False, True):
                if partial and len(q["per_scope_targets"]) < 2:
                    continue
                b2 = copy.deepcopy(bundle)
                field, was_partial = _answer(b2, payload, q, partial=partial)
                after = Q.consolidate(b2)
                new = [x for x in after["questions"] if x["question_id"] not in before]
                bad = [(x["kind"], x["scope"], x["target_field_path"]) for x in new if not _unlock_allowed(q, field, x)]
                assert not bad, f"answering {q['question_id']} ({q['kind']}, partial={partial}) re-asked under new ids: {bad[:5]}"
                if was_partial or (q["kind"] == "optional_values" and len(q["fields"]) > 1):
                    assert q["question_id"] in _ids(after), f"partly answered {q['question_id']} lost its id"
    return set(buckets)


@pytest.fixture()
def grouped(pristine_bundle, tmp_path):
    bdir = tmp_path / "b"
    shutil.copytree(pristine_bundle, bdir)
    M.group(bdir)
    return bdir


def test_answering_any_question_leaves_every_other_open_id_unchanged(grouped, tmp_path):
    seen: set = set()
    bundle = M.load(grouped)
    seen |= _check_every_kind(bundle)
    # the same groups with NO sample reading in their basis: the `sample=unrecorded` question that
    # was re-asked group by group under new ids once one group was answered (the measured defect)
    stripped = copy.deepcopy(bundle)
    for g in stripped["record_groups"]:
        g["basis"]["sample"] = {}
    assert any(q["partition"] == "sample=unrecorded" for q in Q.consolidate(stripped)["questions"])
    seen |= _check_every_kind(stripped, per_bucket=10)
    # the counter question (SYN folder) and the clock-zone question (invented XDC scans)
    (tmp_path / "syn").mkdir()
    src, b = _folder(tmp_path / "syn"), tmp_path / "syn" / "bundle"
    assert cli.main(["import", str(src), "--out", str(b)]) == 0
    M.group(b)
    seen |= _check_every_kind(M.load(b))
    from test_local_import_xdc_start_time import _import, stamp

    x = _import(tmp_path / "xdc", {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45"), "SYN_beta_A.001": stamp("2099-07-15T10:00:00")})
    M.group(x)
    seen |= _check_every_kind(M.load(x))
    kinds = {k for k, _ in seen}
    assert kinds >= {"missing_value", "optional_values", "confirm_value", "resolve_conflict", "confirm_absorber",
                     "naming_counter_positions", "clock_time_zone"}, kinds
    assert ("missing_value", "sample=unrecorded") in seen and ("missing_value", "sample=<reading>") in seen


def test_the_measured_defect_one_sample_group_answered_keeps_the_unrecorded_question(grouped):
    """The exact shape measured on real data (+99 / +111 new ids): answering ONE group of a
    `sample=unrecorded` question re-asked the rest group by group. Now the rest keep the id."""
    bundle = M.load(grouped)
    for g in bundle["record_groups"]:
        g["basis"]["sample"] = {}
    payload = Q.consolidate(bundle)
    q = next(x for x in payload["questions"] if x["partition"] == "sample=unrecorded" and x["kind"] == "missing_value")
    scope = next(iter(q["per_scope_targets"]))
    M.record_decision(bundle, target_ids=Q.targets_for(payload, q["question_id"], scope), decision="correct",
                      value=(q.get("allowed_values") or ["SYNTHETIC TEST VALUE"])[0], by=BY, orcid=None)
    B.apply_derivations(bundle)
    after = Q.consolidate(bundle)
    assert _ids(after) <= _ids(payload)
    same = next(x for x in after["questions"] if x["question_id"] == q["question_id"])
    assert scope not in same["per_scope_targets"] and len(same["per_scope_targets"]) == len(q["per_scope_targets"]) - 1


# --- keep_apart ---------------------------------------------------------------------------------


@pytest.fixture()
def syn(tmp_path):
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert cli.main(["import", str(src), "--out", str(b)]) == 0
    M.group(b)
    return b


def test_keep_apart_records_the_statement_closes_the_candidate_and_changes_no_group(syn, capsys):
    before = M.load(syn)
    (mc,) = before["merge_candidates"]
    assert mc["status"] == "proposed"
    rc = cli.main(["bundle", "decide", str(syn), "--target", mc["merge_candidate_id"], "--decision", "keep_apart", "--by", BY])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and "No group was changed" in out["statement"]
    after = M.load(syn)
    (mc2,) = after["merge_candidates"]
    d = after["scientist_decisions"][-1]
    assert (d["target"], d["decision"]) == ({"kind": "merge_candidate", "id": mc["merge_candidate_id"]}, "keep_apart")
    assert mc2["status"] == "kept_apart" and mc2["kept_apart_by_decision_id"] == d["decision_id"]
    assert after["record_groups"] == before["record_groups"]  # NEGATIVE CONTROL: no group moves, none is confirmed
    assert [g["status"] for g in after["record_groups"]] == ["proposed", "proposed"]
    assert {k: v for k, v in mc2.items() if k not in ("status", "kept_apart_by_decision_id")} == {k: v for k, v in mc.items() if k != "status"}
    assert after["grouping_questions"] == before["grouping_questions"]
    assert cli.main(["bundle", "check", str(syn)]) == 0
    # idempotent; and a regroup that proposes the same candidate keeps it kept apart, same id
    M.decide(syn, target_ids=[mc["merge_candidate_id"]], decision="keep_apart", value=None, by=BY, orcid=None)
    assert len(M.load(syn)["scientist_decisions"]) == 1
    M.group(syn, regroup=True)
    (mc3,) = M.load(syn)["merge_candidates"]
    assert mc3["merge_candidate_id"] == mc["merge_candidate_id"] and mc3["status"] == "kept_apart"


def test_keep_apart_is_refused_on_anything_but_a_merge_candidate(syn):
    g = M.load(syn)["record_groups"][0]
    with pytest.raises(M.MutationRefused, match="`keep_apart` is not a decision for a record_group"):
        M.decide(syn, target_ids=[g["group_id"]], decision="keep_apart", value=None, by=BY, orcid=None)
    mc = M.load(syn)["merge_candidates"][0]
    with pytest.raises(M.MutationRefused, match="`merge` is not a decision for a merge_candidate"):
        M.decide(syn, target_ids=[mc["merge_candidate_id"]], decision="merge", value=None, by=BY, orcid=None)
    assert M.load(syn)["scientist_decisions"] == []


def test_a_kept_apart_candidate_a_regroup_drops_stays_resolvable(syn):
    mc = M.load(syn)["merge_candidates"][0]
    M.decide(syn, target_ids=[mc["merge_candidate_id"]], decision="keep_apart", value=None, by=BY, orcid=None)
    M.decide(syn, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[2])
    M.group(syn, regroup=True)  # the two runs become one group: the candidate is no longer proposed
    a = M.load(syn)
    assert a["merge_candidates"] == []
    assert [x["merge_candidate_id"] for x in a["superseded_merge_candidates"]] == [mc["merge_candidate_id"]]
    assert cli.main(["bundle", "check", str(syn)]) == 0
    bad = json.loads(json.dumps(a))
    bad["superseded_merge_candidates"] = []
    assert any("merge_candidate target" in e and "does not exist" in e for e in B.validate_bundle(bad))


# --- select_athena_version ----------------------------------------------------------------------


def _prov(n: int) -> dict:
    """An invented Athena version's own provenance (project file, group, data hash)."""
    return {"prj_relative_path": f"SYN_proc/SYN_project_{n}.prj", "athena_group": f"SYN_grp_{n}",
            "data_sha256_prefix": f"{n:016x}", "synthetic": True}


def _with_athena_result(bdir: Path) -> None:
    b = M.load(bdir)
    run = b["runs"][0]
    (bdir / "processing").mkdir(exist_ok=True)
    spec = bdir / "processing" / "g1_norm.txt"
    spec.write_text("# SYNTHETIC\n" + "\n".join(f"{1000 + 5 * i} {min(1.0, i / 10):.3f}" for i in range(21)) + "\n")
    b["record_groups"].append(
        {"group_id": "g1", "experiment_key": "exp", "member_run_keys": [run["run_key"]],
         "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}},
         "split_reasons": [], "status": "proposed", "questions": []})
    versions = [{"version_id": f"g1-v{n:02d}", "provenance": _prov(n), "comparison": {"verdict": "agrees"}} for n in (1, 2)]
    b["processing_results"].append(
        {"result_id": "p1", "group_id": "g1", "protocol_id": "isaac.xas.synthetic", "protocol_version": "0.1",
         "protocol_status": "draft_unreviewed", "source": "isaac_protocol",
         "inputs": [{"source_id": run["scans"][0]["source_id"], "scan": 1, "channel": "vortDT"}],
         "steps": [{"step": "normalize", "params": {}, "outcome": {}, "flags": []}],
         "outputs": {"files": [{"role": "normalized_spectrum", "relative_path": "processing/g1_norm.txt",
                                "sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}],
                     "e0_eV": 1012.0, "edge_step": 1.0, "points": 21},
         "qc": {"metrics": {"pre_edge_noise": 0.01}, "verdict": "pass"}, "comparison": None, "state": "candidate_extracted",
         "review_flags": ["protocol_draft_unreviewed", B.ATHENA_UNSELECTED_FLAG],
         "athena_versions": versions, "athena_result_of_record": None,
         "questions": [{"code": B.ATHENA_QUESTION_CODE,
                        "text": "2 different Athena versions of this measurement exist. Which one is the result of record? None is selected until you choose.",
                        "version_ids": ["g1-v01", "g1-v02"]}]})
    M.save_bundle(bdir, b)


@pytest.fixture()
def athena(pristine_bundle, tmp_path):
    bdir = tmp_path / "b"
    shutil.copytree(pristine_bundle, bdir)
    _with_athena_result(bdir)
    return bdir


def _p1(bdir):
    return next(r for r in M.load(bdir)["processing_results"] if r["result_id"] == "p1")


def test_an_unselected_result_is_re_derived_unchanged(athena):
    r = _p1(athena)
    assert r["athena_result_of_record"] is None and B.ATHENA_UNSELECTED_FLAG in r["review_flags"]
    assert [q["code"] for q in r["questions"]] == [B.ATHENA_QUESTION_CODE]
    assert cli.main(["bundle", "check", str(athena)]) == 0


def test_an_unlisted_athena_version_is_refused_and_nothing_is_recorded(athena, capsys):
    before = M.load(athena)
    for bad in ("g1-v03", "g2-v01", "", "G1-V01"):
        with pytest.raises(M.MutationRefused, match="not one of the Athena versions p1 lists|needs --value"):
            M.decide(athena, target_ids=["p1"], decision="select_athena_version", value=bad or None, by=BY, orcid=None)
    rc = cli.main(["bundle", "decide", str(athena), "--target", "p1", "--decision", "select_athena_version",
                   "--value", "g1-v09", "--by", BY])
    assert rc != 0 and "g1-v01, g1-v02" in capsys.readouterr().err
    assert M.load(athena) == before


def test_selecting_a_listed_version_sets_it_and_changes_no_state_qc_or_value(athena, capsys):
    before = _p1(athena)
    rc = cli.main(["bundle", "decide", str(athena), "--target", "p1", "--decision", "select_athena_version",
                   "--value", "g1-v02", "--by", BY])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and "QC status and processed values are unchanged" in out["statement"]
    after = _p1(athena)
    d = M.load(athena)["scientist_decisions"][-1]
    assert after["athena_result_of_record"] == "g1-v02"
    assert after["athena_result_of_record_basis"]["decision_id"] == d["decision_id"]
    assert after["athena_result_of_record_basis"]["decided_by"] == BY
    assert B.ATHENA_UNSELECTED_FLAG not in after["review_flags"] and after["questions"] == []  # the question drops out
    for key in ("state", "qc", "outputs", "steps", "inputs", "athena_versions", "comparison"):
        assert after[key] == before[key], key  # NEGATIVE CONTROL
    assert "qc_status" not in d
    assert cli.main(["bundle", "check", str(athena)]) == 0
    with pytest.raises(M.MutationRefused, match="--qc-status goes with --decision approve"):
        M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None, qc_status="valid")


def test_a_selection_never_stands_in_for_or_undoes_an_approval(athena):
    M.decide(athena, target_ids=["p1"], decision="approve", value=None, by=BY, orcid=None, qc_status="valid")
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)
    r = _p1(athena)
    assert r["state"] == B.STATE_SCIENTIST_CONFIRMED and r["athena_result_of_record"] == "g1-v01"
    approve = next(d for d in M.load(athena)["scientist_decisions"] if d["decision"] == "approve")
    assert B.processing_state_decisions(M.load(athena))[("processing_result", "p1")]["decision_id"] == approve["decision_id"]
    # replaying the approval is idempotent even though a selection was recorded after it
    M.decide(athena, target_ids=["p1"], decision="approve", value=None, by=BY, orcid=None, qc_status="valid")
    assert [d["decision"] for d in M.load(athena)["scientist_decisions"]] == ["approve", "select_athena_version"]
    # the latest selection wins; the earlier one is kept
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v02", by=BY, orcid=None)
    assert _p1(athena)["athena_result_of_record"] == "g1-v02" and _p1(athena)["state"] == B.STATE_SCIENTIST_CONFIRMED


def test_the_validator_refuses_a_hand_written_unlisted_selection(athena):
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)
    assert M.load(athena)["scientist_decisions"][-1]["athena_version_provenance"] == {
        k: _prov(1)[k] for k in B.ATHENA_IDENTITY_KEYS}
    bad = M.load(athena)
    bad["scientist_decisions"][-1]["athena_version_provenance"]["data_sha256_prefix"] = "f" * 16
    assert any("which is not one of the Athena versions p1 lists" in e for e in B.validate_bundle(bad))
    bad = M.load(athena)
    del bad["scientist_decisions"][-1]["athena_version_provenance"]
    bad["scientist_decisions"][-1]["value"] = "g1-v07"
    errors = B.validate_bundle(bad)
    assert any("selects 'g1-v07', which is not one of the Athena versions p1 lists" in e for e in errors)
    tampered = M.load(athena)
    tampered["processing_results"][-1]["athena_result_of_record"] = "g1-v02"
    assert any("athena_result_of_record is not what its select_athena_version decisions give" in e for e in B.validate_bundle(tampered))


def test_a_result_with_no_athena_versions_has_nothing_to_select(pristine_bundle, tmp_path):
    bdir = tmp_path / "b"
    shutil.copytree(pristine_bundle, bdir)
    _with_athena_result(bdir)
    b = M.load(bdir)
    for key in ("athena_versions", "athena_result_of_record", "questions"):
        b["processing_results"][-1].pop(key)
    b["processing_results"][-1]["review_flags"] = ["protocol_draft_unreviewed"]
    M.save_bundle(bdir, b)
    with pytest.raises(M.MutationRefused, match="lists no Athena versions"):
        M.decide(bdir, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)


# --- set_not_counter_positions ------------------------------------------------------------------


def _counter_q(bdir):
    return [q for q in Q.consolidate(M.load(bdir))["questions"] if q["kind"] == "naming_counter_positions"]


def test_no_counter_is_answerable_honest_about_grouping_and_the_question_drops_out(syn, capsys):
    before = M.load(syn)
    (q,) = _counter_q(syn)
    assert q["positions"] == [2] and B.NOT_COUNTER_DECISION in q["allowed_decisions"]
    assert B.NOT_COUNTER_DECISION in q["text"] and "grouping is unchanged" in q["text"]
    rc = cli.main(["bundle", "decide", str(syn), "--question", q["question_id"], "--decision", B.NOT_COUNTER_DECISION, "--by", BY])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and "Grouping is unchanged by this answer" in out["statement"]
    after = M.load(syn)
    d = after["scientist_decisions"][-1]
    assert d["target"] == {"kind": "experiment", "id": "experiment"} and d["not_counter_positions"] == [2] and "positions" not in d
    assert _counter_q(syn) == []  # drops out of the open list
    # NEGATIVE CONTROL: nothing about grouping moved, before or after a regroup
    assert after["record_groups"] == before["record_groups"] and after["merge_candidates"] == before["merge_candidates"]
    assert M.counter_positions(after) is None
    M.group(syn, regroup=True)
    again = M.load(syn)
    assert [g["member_run_keys"] for g in again["record_groups"]] == [g["member_run_keys"] for g in before["record_groups"]]
    assert [m["merge_candidate_id"] for m in again["merge_candidates"]] == [m["merge_candidate_id"] for m in before["merge_candidates"]]
    assert _counter_q(syn) == [] and cli.main(["bundle", "check", str(syn)]) == 0
    # a later answer that position 2 IS a counter takes over (latest statement per position)
    M.decide(syn, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[2])
    assert B.not_counter_positions(M.load(syn)) == {} and M.counter_positions(M.load(syn)) == [2]


def test_no_counter_is_refused_for_a_position_recorded_as_a_counter_and_needs_positions(syn):
    with pytest.raises(M.MutationRefused, match="--positions must be 1 to 8"):
        M.decide(syn, target_ids=["experiment"], decision=B.NOT_COUNTER_DECISION, value=None, by=BY, orcid=None)
    M.decide(syn, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[2])
    with pytest.raises(M.MutationRefused, match="recorded as run counters"):
        M.decide(syn, target_ids=["experiment"], decision=B.NOT_COUNTER_DECISION, value=None, by=BY, orcid=None, positions=[2])
    assert len(M.load(syn)["scientist_decisions"]) == 1


def test_an_answered_counter_question_drops_out_before_the_regroup_too(syn):
    (q,) = _counter_q(syn)
    M.decide(syn, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[2])
    assert _counter_q(syn) == []  # answered: not open, even before `group --regroup` applies it
    assert M.load(syn)["grouping_questions"][0]["positions"] == [2]  # the grouping step's own record is kept


# --- versioning ---------------------------------------------------------------------------------


def test_a_1_5_0_bundle_stays_readable_and_1_6_0_adds_nothing_writable(syn, capsys):
    b = M.load(syn)
    # as the 1.5.0 build made it: no current set-point answer slots (writable only since 1.7.0, DEC-92)
    b["missing_values"] = [m for m in b["missing_values"] if m["target_field_path"] != B.CURRENT_SETPOINT_PATH]
    b["format_version"] = "1.5.0"
    B.refresh_questions(b)
    B.apply_derivations(b)
    assert B.validate_bundle(b) == []
    (syn / "bundle.json").write_bytes(B.encode(b))
    assert cli.main(["bundle", "check", str(syn)]) == 0
    capsys.readouterr()
    M.decide(syn, target_ids=[b["merge_candidates"][0]["merge_candidate_id"]], decision="keep_apart", value=None, by=BY, orcid=None)
    after = M.load(syn)
    # the one upgrade entry names only 1.7.0's path: 1.6.0 made nothing newly writable
    assert after["format_version"] == B.FORMAT_VERSION
    assert [u["newly_writable_paths"] for u in after["format_upgrades"]] == [[B.CURRENT_SETPOINT_PATH]]
    assert capsys.readouterr().err.count("upgraded from 1.5.0") == 1


# --- review fixes: the merge path (H1, M1-M4) ------------------------------------------------------


def _stems_folder(root: Path, stems) -> Path:
    """The SYN counter folder with chosen run stems (every file invented)."""
    import test_local_import_grouping_cli as GC

    src = root / "src"
    src.mkdir(parents=True)
    acq = (FIXTURE / GC.SRC_STEM).read_text().replace("01_01_ZZ1_acid_beforeCycling_filter10_100mV", GC.SRC_STEM)
    scan = (FIXTURE / f"{GC.SRC_STEM}_dir" / f"{GC.SRC_STEM}_001.dat").read_text()
    (src / "Zz_XAS.mac").write_text((FIXTURE / "Zz_XAS.mac").read_text())
    for stem in stems:
        (src / stem).write_text(acq.replace(GC.SRC_STEM, stem))
        d = src / f"{stem}_dir"
        d.mkdir()
        for i in (1, 2):
            (d / f"{stem}_{i:03d}.txt").write_text(scan.replace(GC.SRC_STEM, stem))
    return src


def _grouped_stems(tmp_path: Path, stems) -> Path:
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    src, b = _stems_folder(tmp_path, stems), tmp_path / "bundle"
    assert cli.main(["import", str(src), "--out", str(b)]) == 0
    M.group(b)
    return b


def _merge(b: Path, target: str, others) -> dict:
    M.decide(b, target_ids=[target], decision="merge", value=None, by=BY, orcid=None, merge_with=list(others))
    return M.group(b, regroup=True)


def _combined(b: Path) -> list[dict]:
    return [g for g in M.load(b)["record_groups"] if g.get("merged_by_decision") and g["status"] in B.LIVE_GROUP_STATUSES]


@pytest.fixture()
def names_agree(monkeypatch):
    """For tests of the regroup's bookkeeping (H1, M3), not of the name check: the file-name
    blockers are taken out, as if the groups' names agreed token for token. Every other blocker stays."""
    orig = M._merge_blockers
    monkeypatch.setattr(M, "_merge_blockers", lambda *a: [r for r in orig(*a) if "file names" not in r])


@pytest.mark.parametrize("stems", [
    ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"],   # counter-shaped: still blocked, sent to the counter question
    ["Q4_SYNcat_pH2_1.02", "Q4_SYNcat_pH2_1.03"],            # decimals split on "." look zero-padded
    ["Q4_SYNcat_pH_7.02", "Q4_SYNcat_pH_7.05"],
    ["Q4_SYNcat_E_0.02_vsRHE", "Q4_SYNcat_E_0.03_vsRHE"],
    ["Q4_SYNcat_05_mM", "Q4_SYNcat_10_mM"],                  # unit words no list covered
    ["Q4_SYNcat_02_hrs", "Q4_SYNcat_03_hrs"],
    ["Q4_SYNcat_05_mg", "Q4_SYNcat_06_mg"],
    ["Q4_SYNcat_05_rpm", "Q4_SYNcat_09_rpm"],
    ["Q4_SYNcat_400_pH2", "Q4_SYNcat_500_pH2"],
    ["Q4_SYNcat_E_1", "Q4_SYNcat_E_2"],
    ["Q4_SYNcat_after_10_cycles", "Q4_SYNcat_after_500_cycles"],
    ["Q4_SYNcat_25_C", "Q4_SYNcat_80_C"],
    ["Q4_1_SYNcat_pH2_400mV", "Q4_10_SYNcat_pH2_400mV"],
    ["Q4_SYNcat_pH2_0.05V", "Q4_SYNcat_pH2_0.5V"],
    ["Q4_SYNcat_1MKOH_400mV", "Q4_SYNcat_0p1MKOH_400mV"],
    ["Q4_SYNcat_10ug_400mV", "Q4_SYNcat_50ug_400mV"],
    ["Q4_SYNcat_pH2_400mV", "Q4_SYNdog_pH2_400mV"],
    ["Q4_SYNcat_E1_pH2_400mV", "Q4_SYNcat_E2_pH2_400mV"],
    ["Q4_SYNcat_pH2_400mV_step01", "Q4_SYNcat_pH2_400mV_step02"],
    ["Q4_SYNcat_pH2_400mV_before", "Q4_SYNcat_pH2_400mV_after"],
    ["Q4_SYNcat_pH2_400mV", "Q4_SYNcat_pH2_400mV_newspot"],
])
@pytest.mark.parametrize("direction", [0, 1])
def test_a_merge_across_any_differing_name_token_fails_closed(tmp_path, stems, direction):
    """M1 (third review): ANY differing file-name token blocks — there is no exception by token shape.
    Each pair, merged either way round, keeps the candidate open with a reason naming the differing
    tokens and pointing to the counter question."""
    b = _grouped_stems(tmp_path, stems)
    g = M.load(b)["record_groups"]
    assert len(g) == 2
    target, other = (g[0], g[1]) if direction == 0 else (g[1], g[0])
    out = _merge(b, target["group_id"], [other["group_id"]])
    assert _combined(b) == [] and out["combined_by_merge_decision"] == []
    [nc] = out["merge_decisions_not_combined"]
    assert "file names" in nc["reason"] and "set_counter_positions" in nc["reason"]
    assert all(t in nc["reason"] for t in set(stems[0].split("_")) ^ set(stems[1].split("_")) if "." not in t)
    [mc] = [m for m in M.load(b)["merge_candidates"] if m["reasons"][0]["code"] == "scientist_decided_merge"]
    assert "were not combined" in mc["reasons"][0]["detail"]
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_no_shape_based_exception_exists_and_the_counter_question_joins_the_runs(tmp_path):
    """The mechanism for "this number is a counter" is the counter question, never the token's shape:
    02/03 is blocked as a merge, then set_counter_positions + regroup joins the runs (grouping does it)."""
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"])
    g1, g2 = M.load(b)["record_groups"]
    out = _merge(b, g1["group_id"], [g2["group_id"]])
    assert _combined(b) == [] and "differ at token 2 (02 / 03)" in out["merge_decisions_not_combined"][0]["reason"]
    M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by=BY, orcid=None, positions=[2])
    M.group(b, regroup=True)
    live = [x for x in M.load(b)["record_groups"] if x["status"] in B.LIVE_GROUP_STATUSES]
    assert [len(x["member_run_keys"]) for x in live] == [2] and not live[0].get("merged_by_decision")
    # and on the check itself: names differing only in a zero-padded fixed-width number are refused
    bundle = M.load(_grouped_stems(tmp_path / "again", ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"]))
    h1, h2 = bundle["record_groups"]
    combined = M._combine_for_merge([h1, h2], {"decision_id": "d-99999", "decided_by": {"name": BY}}, h1["group_id"], "exp")
    assert any("differ at token 2 (02 / 03)" in r for r in M._merge_blockers(bundle, {}, [h1, h2], combined))
    for g in (h1, h2):  # the same name for both: nothing about the names blocks
        next(r for r in bundle["runs"] if r["run_key"] == g["member_run_keys"][0])["stem"] = "Q4_02_SYNcat_pH2_400mV"
    assert not [r for r in M._merge_blockers(bundle, {}, [h1, h2], combined) if "file names" in r]


def test_a_combined_basis_keeps_what_the_groups_agree_on_with_both_evidence_ids(tmp_path):
    """M2: agreed readings (pH, potential ...) survive with the evidence ids of both groups; only the
    name stem is dropped."""
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"])
    g = M.load(b)["record_groups"]
    c = M._combine_for_merge(g, {"decision_id": "d-99999", "decided_by": {"name": BY}}, g[0]["group_id"], "exp")
    cond = c["basis"]["conditions"]
    assert cond["ph"]["value"] == 2 and "potential_magnitude" in cond
    for key, entry in cond.items():
        assert set(entry["candidate_ids"]) == set(g[0]["basis"]["conditions"][key]["candidate_ids"]) | set(g[1]["basis"]["conditions"][key]["candidate_ids"])
    assert c["merged_by_decision"]["basis_keys_dropped"] == ["sample.sample_name_stem"]


def test_a_combined_basis_keeps_an_agreed_sample_reading_and_the_questions_see_it(grouped):
    """M2 (unit): two groups of the same recorded sample — the combined basis keeps the sample (the
    questions' sample partition reads it), drops the potential they differ on, and the fail-closed
    check refuses them because that potential differs."""
    bundle = M.load(grouped)
    by_sample: dict = {}
    for g in bundle["record_groups"]:
        by_sample.setdefault(json.dumps(g["basis"]["sample"].get("sample_name", {}).get("value")), []).append(g)
    h1, h2 = next(v for v in by_sample.values() if len(v) > 1)[:2]
    combined = M._combine_for_merge([h1, h2], {"decision_id": "d-99999", "decided_by": {"name": BY}}, h1["group_id"], "exp")
    assert combined["basis"]["sample"]["sample_name"]["value"] == h1["basis"]["sample"]["sample_name"]["value"]
    assert set(combined["basis"]["sample"]["sample_name"]["candidate_ids"]) == (
        set(h1["basis"]["sample"]["sample_name"]["candidate_ids"]) | set(h2["basis"]["sample"]["sample_name"]["candidate_ids"]))
    assert "conditions.potential_magnitude" in combined["merged_by_decision"]["basis_keys_dropped"]
    bundle["record_groups"] = [x for x in bundle["record_groups"] if x["group_id"] not in (h1["group_id"], h2["group_id"])] + [combined]
    key = f"group:{combined['group_id']}"
    seen = [q for q in Q.consolidate(bundle)["questions"]
            if (q.get("partition") or "").startswith("sample={") and key in q["per_scope_targets"]]
    assert seen, "the combined group's sample questions are partitioned by its recorded sample"
    assert any("potential_magnitude" in r for r in M._merge_blockers(bundle, {}, [h1, h2], combined))


def test_rejecting_the_combined_group_then_regrouping_does_not_re_propose_it(tmp_path, names_agree):
    """H1: the combined id (runs + merge decision id) was re-proposed while the rejected combined
    group stayed in history, so the regroup raised `duplicate group_id`."""
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"])
    g1, g2 = M.load(b)["record_groups"]
    _merge(b, g1["group_id"], [g2["group_id"]])
    [c] = _combined(b)
    M.decide(b, target_ids=[c["group_id"]], decision="reject", value=None, by=BY, orcid=None)
    out = M.group(b, regroup=True)
    a = M.load(b)
    assert [x["status"] for x in a["record_groups"] if x["group_id"] == c["group_id"]] == ["rejected"]
    assert _combined(b) == [] and out["combined_by_merge_decision"] == []
    assert any("already decided (rejected)" in x["reason"] for x in out["merge_decisions_not_combined"])
    live = [x for x in a["record_groups"] if x["status"] in B.LIVE_GROUP_STATUSES]
    assert sorted(len(x["member_run_keys"]) for x in live) == [1, 1]  # the runs stay proposable, apart
    assert not [m for m in a["merge_candidates"] if m["reasons"][0]["code"] == "scientist_decided_merge"]
    M.group(b, regroup=True)  # and again: stable, no duplicate id
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_merging_the_combined_group_again_then_regrouping_combines_all_three(tmp_path, names_agree):
    """H1: a combined group merged again is history; the regroup proposes the new combination once."""
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV", "Q4_04_SYNcat_pH2_400mV"])
    g1, g2, g3 = M.load(b)["record_groups"]
    _merge(b, g1["group_id"], [g2["group_id"]])
    [c] = _combined(b)
    third = next(x for x in M.load(b)["record_groups"] if x["status"] == "proposed" and x["group_id"] != c["group_id"]
                 and set(x["member_run_keys"]) == set(g3["member_run_keys"]))
    _merge(b, c["group_id"], [third["group_id"]])
    [c2] = _combined(b)
    assert set(c2["member_run_keys"]) == set(g1["member_run_keys"]) | set(g2["member_run_keys"]) | set(g3["member_run_keys"])
    assert [x["status"] for x in M.load(b)["record_groups"] if x["group_id"] == c["group_id"]] == ["merged"]
    M.group(b, regroup=True)
    assert [x["group_id"] for x in _combined(b)] == [c2["group_id"]]
    assert cli.main(["bundle", "check", str(b)]) == 0


def test_a_merge_superseded_by_a_later_decision_on_its_group_is_not_applied(tmp_path):
    """M4 (status-merged guard): after merge, the scientist rejects the same group; no combination."""
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"])
    g1, g2 = M.load(b)["record_groups"]
    M.decide(b, target_ids=[g1["group_id"]], decision="merge", value=None, by=BY, orcid=None, merge_with=[g2["group_id"]])
    M.decide(b, target_ids=[g1["group_id"]], decision="reject", value=None, by=BY, orcid=None)
    out = M.group(b, regroup=True)
    assert _combined(b) == [] and out["combined_by_merge_decision"] == [] and out["merge_decisions_not_combined"] == []


def test_a_merge_with_a_confirmed_group_is_not_combined_and_says_why(tmp_path):
    """M4 (confirmed-group guard): its reason is stated, word for word."""
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"])
    g1, g2 = M.load(b)["record_groups"]
    M.decide(b, target_ids=[g2["group_id"]], decision="confirm", value=None, by=BY, orcid=None)
    out = _merge(b, g1["group_id"], [g2["group_id"]])
    assert _combined(b) == []
    assert [x["reason"] for x in out["merge_decisions_not_combined"]] == [
        "a run of it is in a confirmed group, whose runs are never re-proposed"]


@pytest.mark.parametrize("same", [False, True])
def test_differing_confirmed_run_answers_keep_a_merge_apart(tmp_path, same, names_agree):
    """M3: a confirmed, eligible run-level answer (here the control mode) that differs between the
    groups blocks the combination; the same answer does not."""
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"])
    modes = list((B._schema_node(B.CONTROL_MODE_PATH) or {}).get("enum") or [])
    assert len(modes) >= 2
    bun = M.load(b)
    g1, g2 = bun["record_groups"]
    for g, mode in ((g1, modes[0]), (g2, modes[0] if same else modes[1])):
        vid = next(m["value_id"] for m in bun["missing_values"]
                   if m["target_field_path"] == B.CONTROL_MODE_PATH and m["run_id"] in g["member_run_ids"])
        M.decide(b, target_ids=[vid], decision="correct", value=mode, by=BY, orcid=None)
    out = _merge(b, g1["group_id"], [g2["group_id"]])
    if same:
        assert len(_combined(b)) == 1
    else:
        assert _combined(b) == []
        assert [x["reason"] for x in out["merge_decisions_not_combined"]] == [
            f"confirmed answers for their runs differ ({B.CONTROL_MODE_PATH})"]


# --- review fixes: the Athena selection (M4, L3) ---------------------------------------------------


def test_the_record_cites_the_approval_never_a_later_selection(athena):
    """M4 (records.py): compose_group's processing confirmation is the APPROVE decision."""
    M.decide(athena, target_ids=["g1"], decision="confirm", value=None, by=BY, orcid=None)
    M.decide(athena, target_ids=["p1"], decision="approve", value=None, by=BY, orcid=None, qc_status="valid")
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v02", by=BY, orcid=None)
    bundle = M.load(athena)
    approve, select = (next(d["decision_id"] for d in bundle["scientist_decisions"] if d["decision"] == k)
                       for k in ("approve", "select_athena_version"))
    g = next(x for x in bundle["record_groups"] if x["group_id"] == "g1")
    draft, report = R.compose_group(bundle, g, athena)
    cited = [e.get("decision_id") for evs in draft["block_evidence"].values() for e in evs
             if e.get("source_type") == "user_confirmation" and "processing result p1" in str(e.get("question"))]
    assert cited and set(cited) == {approve} and select not in cited


def test_a_selection_changed_after_the_approval_is_noted_on_the_result(athena):
    """L3: visible, never wired into export."""
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)
    M.decide(athena, target_ids=["p1"], decision="approve", value=None, by=BY, orcid=None, qc_status="valid")
    assert "changed_after_approval" not in _p1(athena)["athena_result_of_record_basis"]
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v02", by=BY, orcid=None)
    note = _p1(athena)["athena_result_of_record_basis"]["changed_after_approval"]
    approve = next(d for d in M.load(athena)["scientist_decisions"] if d["decision"] == "approve")
    assert note["approval_decision_id"] == approve["decision_id"] and note["selected_at_approval"] == "g1-v01"
    assert _p1(athena)["state"] == B.STATE_SCIENTIST_CONFIRMED and cli.main(["bundle", "check", str(athena)]) == 0


@pytest.mark.parametrize("fresh_lists_it", [True, False])
def test_a_selection_alone_does_not_freeze_a_result_against_re_processing(athena, monkeypatch, fresh_lists_it):
    """L3: only a state decision keeps the old result; a selection keeps it only when the fresh result
    no longer lists the selected version (so the selection never points at nothing)."""
    from isaac_api.local_import.processing import cli_entry

    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v02", by=BY, orcid=None)
    fresh = copy.deepcopy(_p1(athena))
    fresh["steps"] = [{"step": "normalize", "params": {"fresh": True}, "outcome": {}, "flags": []}]
    if not fresh_lists_it:
        fresh["athena_versions"] = fresh["athena_versions"][:1]
    for k in ("athena_result_of_record_basis",):
        fresh.pop(k, None)
    fresh["state"] = "candidate_extracted"
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: {"processing_results": [fresh]})
    M.process(athena)
    r = _p1(athena)
    assert (r["steps"][0]["params"] == {"fresh": True}) is fresh_lists_it
    assert r["athena_result_of_record"] == "g1-v02"
    assert cli.main(["bundle", "check", str(athena)]) == 0


@pytest.mark.parametrize("change", ["renumbered", "inserted", "removed", "rehashed"])
def test_a_renumbering_re_processing_keeps_the_selection_on_the_same_curve(athena, monkeypatch, change):
    """Item 2 of the re-review: version ids are positional, so a project file added or removed
    renumbers them. The selection follows the version's provenance: re-pointed (and said so) when the
    same version moved; the OLD result kept when the fresh one no longer holds it."""
    from isaac_api.local_import.processing import cli_entry

    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v02", by=BY, orcid=None)
    fresh = copy.deepcopy(_p1(athena))
    fresh.pop("athena_result_of_record_basis", None)
    fresh["state"] = "candidate_extracted"
    fresh["steps"] = [{"step": "normalize", "params": {"fresh": True}, "outcome": {}, "flags": []}]
    if change == "renumbered":    # same two projects, other order: v02's curve is now v01
        provs = [_prov(2), _prov(1)]
    elif change == "inserted":    # a new project sorts first: every id shifts by one
        provs = [_prov(3), _prov(1), _prov(2)]
    elif change == "removed":     # the selected project is gone; another now holds the id g1-v02
        provs = [_prov(1), _prov(3)]
    else:                         # same file and group, different data: not the same curve
        provs = [_prov(1), {**_prov(2), "data_sha256_prefix": "e" * 16}]
    fresh["athena_versions"] = [{"version_id": f"g1-v{n:02d}", "provenance": p, "comparison": {}} for n, p in enumerate(provs, 1)]
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: {"processing_results": [fresh]})
    M.process(athena)
    r = _p1(athena)
    if change in ("renumbered", "inserted"):
        expect = "g1-v01" if change == "renumbered" else "g1-v03"
        assert r["steps"][0]["params"] == {"fresh": True}  # replaced by the fresh result
        assert r["athena_result_of_record"] == expect
        assert r["athena_result_of_record_basis"]["repointed"] == {**r["athena_result_of_record_basis"]["repointed"],
                                                                   "decision_value": "g1-v02", "now": expect}
    else:
        assert r["steps"][0]["params"] == {}  # NEGATIVE CONTROL: the old result is kept, its curve unchanged
        assert r["athena_result_of_record"] == "g1-v02" and "repointed" not in r["athena_result_of_record_basis"]
    assert cli.main(["bundle", "check", str(athena)]) == 0


# --- re-review item 1: the bare-number exception ------------------------------------------------------


@pytest.mark.parametrize("direction", [0, 1])
def test_a_not_counter_answer_before_a_merge_keeps_the_merge_apart(tmp_path, direction):
    b = _grouped_stems(tmp_path, ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"])
    M.decide(b, target_ids=["experiment"], decision=B.NOT_COUNTER_DECISION, value=None, by=BY, orcid=None, positions=[2])
    g = M.load(b)["record_groups"]
    target, other = (g[0], g[1]) if direction == 0 else (g[1], g[0])
    out = _merge(b, target["group_id"], [other["group_id"]])
    assert _combined(b) == []
    assert any("differ at token 2 (02 / 03)" in x["reason"] for x in out["merge_decisions_not_combined"])



def _renumber(athena: Path, monkeypatch, provs) -> None:
    """Re-process p1 with versions of these provenances (in this order), numbered afresh."""
    from isaac_api.local_import.processing import cli_entry

    fresh = copy.deepcopy(_p1(athena))
    fresh.pop("athena_result_of_record_basis", None)
    fresh["state"] = "candidate_extracted"
    fresh["athena_versions"] = [{"version_id": f"g1-v{n:02d}", "provenance": p, "comparison": {}} for n, p in enumerate(provs, 1)]
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: {"processing_results": [fresh]})
    M.process(athena)


def test_re_selecting_an_id_that_now_names_another_curve_is_recorded_not_unchanged(athena, monkeypatch):
    """M2 (third review): the repeat check compares the version's identity, not its positional id."""
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)
    _renumber(athena, monkeypatch, [_prov(2), _prov(1)])  # g1-v01 is now the OTHER curve
    assert _p1(athena)["athena_result_of_record"] == "g1-v02"  # the selection followed its curve
    res = M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)
    assert res["recorded"] == ["p1"] and res["unchanged"] == []
    d = M.load(athena)["scientist_decisions"][-1]
    assert d["athena_version_provenance"]["prj_relative_path"] == _prov(2)["prj_relative_path"]
    assert _p1(athena)["athena_result_of_record"] == "g1-v01"
    # and a true repeat (same id, same curve) is still unchanged
    assert M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)["unchanged"] == ["p1"]


def test_changed_after_approval_compares_identity_not_ids(athena, monkeypatch):
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)
    M.decide(athena, target_ids=["p1"], decision="approve", value=None, by=BY, orcid=None, qc_status="valid")
    _renumber(athena, monkeypatch, [_prov(3), _prov(1), _prov(2)])  # the approved selection is now g1-v02
    # the result was approved, so it is kept (a state decision freezes it): renumber a fresh copy instead
    b = M.load(athena)
    r = b["processing_results"][-1]
    r["athena_versions"] = [{"version_id": f"g1-v{n:02d}", "provenance": p, "comparison": {}} for n, p in enumerate([_prov(3), _prov(1), _prov(2)], 1)]
    M.save_bundle(athena, b)
    assert _p1(athena)["athena_result_of_record"] == "g1-v02"
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v02", by=BY, orcid=None)  # same curve, new id
    assert "changed_after_approval" not in _p1(athena)["athena_result_of_record_basis"]
    M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)  # old id, other curve
    note = _p1(athena)["athena_result_of_record_basis"]["changed_after_approval"]
    assert note["selected_at_approval"] == "g1-v01" and note["selected_at_approval_provenance"]["prj_relative_path"] == _prov(1)["prj_relative_path"]


def test_a_version_indistinguishable_by_identity_cannot_be_selected(athena):
    b = M.load(athena)
    r = b["processing_results"][-1]
    r["athena_versions"][1]["provenance"] = dict(r["athena_versions"][0]["provenance"])
    M.save_bundle(athena, b)
    with pytest.raises(M.MutationRefused, match="cannot be told apart from another listed version"):
        M.decide(athena, target_ids=["p1"], decision="select_athena_version", value="g1-v01", by=BY, orcid=None)
    assert not [d for d in M.load(athena)["scientist_decisions"] if d["decision"] == "select_athena_version"]
