"""Skill polish r7 (fixer J: questions and records). SYNTHETIC fixtures only: every name and value is invented.

J1  A SPEC file started more than once writes an #E line each time. Its run then holds two start-time
    disagreements (#E and #D). The beamtime start-time question counts RUNS, not disagreements, and says "its file
    was started N times (#E at ...): say which is the start". The #E question asks that. The #D question no longer
    says "no UTC reading is held": it names the #E question and affects no record on its own.
J2  Every group with a cannot_export_reason (no processing protocol, no scan, not a measurement run) is blocked by
    nothing, and a question that reaches some says how many of its groups can become a record.
J3  A disagreement that reaches only such groups affects no record, and the beamtime start-time question leaves
    them out of not_reached.
J4  A #D local clock time with no zone is "not_comparable" with the UTC start of record, never "contradicts".
J5  An in-situ record's warning is in its evidence notes, so `upload --dry-run` lists it; an open-circuit name
    token is not quoted when the confirmed control mode says otherwise.
J6  export and dry-run rows carry a short label: the group's first member file.
J7  The counter question's run count leaves out runs kept as context.
J8  A group with no scan is `no_scans` before and after `isaac process`.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_records import (BY, SEMANTICS, _decide_everything, _miss, _portal, bdir,  # noqa: F401
                                       fake_upstream, pristine)

START = B.XDC_START_PATH
#: runs whose second scan's #D line is moved a day (a start-time disagreement each, reached by the beamtime question)
DISAGREE = ("02_01_ZZ1_acid_after500Cycling_filter10_200mV", "06_03_ZZ3_alk_fresh_f30_900mV")
#: a run whose file was started twice: a second header block, its #E 100 s and its #D lines 2 min later
RESTARTED = "07_03_ZZ3_alk_fresh_f30_1000mV"


def _corpus(tmp: Path) -> Path:
    src = tmp / "corpus"
    shutil.copytree(SEMANTICS, src)
    for stem in DISAGREE:
        scan = next((src / f"{stem}_dir").glob("*_002.dat"))
        text = scan.read_text(encoding="utf-8")
        scan.write_text(text.replace("#D Fri Jan 01 00:00:00 2100", "#D Sat Jan 02 00:00:00 2100", 1), encoding="utf-8")
    main = src / RESTARTED
    text = main.read_text(encoding="utf-8")
    again = re.sub(r"^#E (\d+)", lambda m: f"#E {int(m.group(1)) + 100}", text, flags=re.M)
    again = re.sub(r"^#D (.*) 00:(\d\d):(\d\d) 2100", lambda m: f"#D {m.group(1)} 00:{int(m.group(2)) + 2:02d}:{m.group(3)} 2100",
                   again, flags=re.M)
    main.write_text(text + "\n" + again, encoding="utf-8")
    return src


@pytest.fixture(scope="module")
def restarted_pristine(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("r7j")
    out = tmp / "grouped"
    assert cli.main(["import", str(_corpus(tmp)), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def grouped(restarted_pristine, tmp_path):
    target = tmp_path / "grouped"
    shutil.copytree(restarted_pristine, target)
    return target


def _start_questions(payload):
    return [q for q in payload["questions"] if q["kind"] == "resolve_conflict" and q["target_field_path"] == START]


def _restarted(b, payload):
    """``(#E question, #D question)`` of the restarted run's group."""
    rid = next(r["run_id"] for r in b["runs"] if r["stem"] == RESTARTED)
    cands = {c["candidate_id"]: c for c in b["candidates"]}
    by_key = {}
    for q in _start_questions(payload):
        cf = next(cf for cf in b["conflicts"] if cf["conflict_id"] == q["targets"][0]["id"])
        if cf["run_ids"] == [rid]:
            by_key[cands[cf["candidate_id"]]["statement_key"]] = q
    return by_key["acquisition_epoch"], by_key["acquisition_timestamp"]


def _na(gid: str, code: str) -> dict:
    return {"result_id": f"p-{gid}", "group_id": gid, "source": "isaac_protocol", "state": B.STATE_NEEDS_REVIEW,
            "applicability": {"status": B.NOT_APPLICABLE, "reason_code": code}}


def _ids(payload):
    return {q["question_id"]: (q["scope"], sorted(t["id"] for t in q["targets"])) for q in payload["questions"]}


# --- J1 ------------------------------------------------------------------------------------------------------------


def test_a_file_started_twice_is_said_so_and_its_run_is_counted_once(grouped):
    b = M.load(grouped)
    payload = Q.consolidate(b)
    epoch_q, clock_q = _restarted(b, payload)
    beamtime = Q.question(payload, Q.STATED_UTC_START_QUESTION_ID)
    [missed] = beamtime["not_reached"]
    assert missed["group_id"] == epoch_q["scope"][len("group:"):]
    assert missed["question_ids"] == [epoch_q["question_id"]]  # the #D question is asked by the #E one
    assert missed["reason"].startswith("its file was started 2 times (#E at line 2: ")
    assert "; line 55: " in missed["reason"] and missed["reason"].endswith(": say which is the start")
    assert "runs, each with its own" not in beamtime["text"] and missed["reason"] in beamtime["text"]
    # the #E question asks which header's instant is the start
    assert "Its file was started 2 times" in epoch_q["text"] and "which is the start?" in epoch_q["text"]
    assert "Which reading is right?" not in epoch_q["text"]
    assert epoch_q["tier"] == Q.TIER_CONFLICT and epoch_q["affects_record"]


def test_the_local_clock_question_names_the_utc_question_instead_of_saying_none_is_held(grouped):
    b = M.load(grouped)
    payload = Q.consolidate(b)
    epoch_q, clock_q = _restarted(b, payload)
    assert "No UTC reading of this start is held" not in clock_q["text"]
    assert f"Question {epoch_q['question_id']} asks which is the start" in clock_q["text"]
    assert clock_q["asked_by_question"] == epoch_q["question_id"]
    assert clock_q["tier"] == Q.TIER_OPTIONAL and clock_q["affects_record"] is False
    assert epoch_q["question_id"] in clock_q["why"]


def test_folding_changes_no_id_scope_or_target(grouped, monkeypatch):
    b = M.load(grouped)
    after = Q.consolidate(b)
    monkeypatch.setattr(Q, "_fold_into_file_restart", lambda *a: None)
    before = Q.consolidate(b)
    assert _ids(after) == _ids(before)
    assert after["counts"]["conflicts_affecting_a_record"] == before["counts"]["conflicts_affecting_a_record"] - 1


def test_answering_the_utc_question_settles_the_local_clock_one(grouped, capsys):
    b = M.load(grouped)
    epoch_q, clock_q = _restarted(b, Q.consolidate(b))
    cf = next(cf for cf in b["conflicts"] if cf["conflict_id"] == epoch_q["targets"][0]["id"])
    second = cf["readings"][1]["value"]
    assert cli.main(["bundle", "decide", str(grouped), "--question", epoch_q["question_id"], "--decision", "confirm",
                     "--value", second, "--by", BY["by"]]) == 0
    capsys.readouterr()
    after = Q.consolidate(M.load(grouped))
    now = Q.question(after, clock_q["question_id"])
    assert now["covered_by_decisions"] and now["affects_record"] is False
    assert now["asked_by_question"] == epoch_q["question_id"]
    assert Q.question(after, epoch_q["question_id"]) is None  # answered: no longer open


def _reach_bundle(conflicts):
    runs = [{"run_id": f"run-{i}", "run_key": f"k{i}", "stem": f"ZZ_{i}"} for i in (1, 2)]
    cands = [{"candidate_id": cf["candidate_id"], "run_id": cf["run_ids"][0], "target_field_path": START, "value": None,
              "value_state": "conflicting", "evidence": []} for cf in conflicts]
    return {"runs": runs, "record_groups": [{"group_id": "g", "status": "proposed", "member_run_keys": ["k1", "k2"]}],
            "candidates": cands, "conflicts": conflicts, "sources": []}


def _local(cid, cand, run):
    return {"conflict_id": cid, "candidate_id": cand, "run_ids": [run], "readings": [
        {"value": "Fri Jan 01 00:00:00 2100", "witnesses": [{"source_id": "s1", "locator": "line 3 header #D"}]},
        {"value": "Fri Jan 01 00:05:00 2100", "witnesses": [{"source_id": "s1", "locator": "line 9 header #D (scan 1)"}]}]}


def test_the_reach_counts_runs_not_disagreements():
    two_runs = Q.stated_utc_reach(_reach_bundle([_local("cf-1", "c-1", "run-1"), _local("cf-2", "c-2", "run-2")]))
    assert {r["reason"] for r in two_runs.values()} == {
        "the group has 2 runs, each with its own start-time disagreement: say which run's start the record takes"}
    one_run = Q.stated_utc_reach(_reach_bundle([_local("cf-1", "c-1", "run-1"), _local("cf-2", "c-2", "run-1")]))
    assert {r["reason"] for r in one_run.values()} == {
        "its run has 2 start-time disagreements: say which instant is the start"}


def test_file_restarts_reads_only_the_e_lines_of_one_file():
    cf = {"readings": [
        {"value": "2100-01-01T00:00:00+00:00", "witnesses": [{"source_id": "s1", "locator": "line 2 header #E"},
                                                             {"source_id": "s1", "locator": "line 40 header #E"}]},
        {"value": "2100-01-01T01:00:00+00:00", "witnesses": [{"source_id": "s1", "locator": "line 90 header #E"}]}]}
    # r7 review: two #E lines with the same instant are one start
    assert Q.file_restarts_said(cf) == ("its file was started 2 times (#E at line 2 and line 40: "
                                        "2100-01-01T00:00:00+00:00; line 90: 2100-01-01T01:00:00+00:00)")
    same = copy.deepcopy(cf)
    same["readings"][1]["value"] = same["readings"][0]["value"]
    assert Q.file_restarts_said(same) is None
    other = copy.deepcopy(cf)
    other["readings"][1]["witnesses"][0]["source_id"] = "s2"  # two files: not one file restarted
    assert Q.file_restarts(other) == []
    assert Q.file_restarts(_local("cf-1", "c-1", "run-1")) == []  # #D local clock times are not #E instants


# --- J2 / J3 / J8 ------------------------------------------------------------------------------------------------


def _beamtime_blocking(payload):
    return next(q for q in payload["questions"] if q["scope"] == "experiment" and q["blocking"]
                and (q.get("blocks_groups") or 0) >= 3)


def test_a_group_no_protocol_covers_is_blocked_by_nothing_and_a_batch_says_how_many_can_export(grouped):
    b = M.load(grouped)
    before = Q.consolidate(b)
    q = _beamtime_blocking(before)
    gid = q["blocks_group_ids"][0]
    b["processing_results"] = [*b["processing_results"], _na(gid, B.NA_NO_XAS_CHANNEL)]
    after = Q.consolidate(b)
    now = Q.question(after, q["question_id"])
    assert now["blocks_groups"] == q["blocks_groups"] - 1 and gid not in now["blocks_group_ids"]
    reached = now["applies_to"]["groups"]
    assert now["applies_to"]["groups_that_can_export"] == reached - 1
    assert (f"Only {reached - 1} of the {reached} groups it reaches can become a record; 1 cannot export as they stand "
            "(processing_not_applicable:no_xas_channel for 1 (no energy axis or absorption signal") in now["text"]
    basis = after["blocking_basis"]["record_composer"]
    assert basis["groups_that_cannot_export"] == {gid: "processing_not_applicable:no_xas_channel"}
    assert basis["cannot_export_by_reason"] == {"processing_not_applicable:no_xas_channel": 1}
    assert "No question counts as blocking for them" in basis["cannot_export_statement"]
    assert _ids(after) == _ids(before)  # ids, scopes and targets unchanged
    # every question that blocks only that group no longer blocks
    for x in before["questions"]:
        if x["blocking"] and x.get("blocks_group_ids") == [gid]:
            y = Q.question(after, x["question_id"])
            assert not y["blocking"] and "processing_not_applicable:no_xas_channel" in y["why"]


def test_a_scanless_group_is_no_scans_before_and_after_processing(grouped):
    b = M.load(grouped)
    gid = b["record_groups"][0]["group_id"]
    keys = set(b["record_groups"][0]["member_run_keys"])
    for r in b["runs"]:
        if r["run_key"] in keys:
            r["scan_count"] = 0
    assert Q.cannot_export_reasons(b)[gid] == "no_scans"
    b["processing_results"] = [*b["processing_results"], _na(gid, B.NA_NO_SCANS)]
    assert Q.cannot_export_reasons(b)[gid] == "no_scans"
    assert cli.group_list_extras(b)[gid]["cannot_export_reason"] == "no_scans"
    payload = Q.consolidate(b)
    assert payload["blocking_basis"]["record_composer"]["groups_that_cannot_export"] == {gid: "no_scans"}


def test_a_start_time_disagreement_of_a_group_that_cannot_export_affects_no_record(grouped):
    b = M.load(grouped)
    before = Q.consolidate(b)
    epoch_q, _ = _restarted(b, before)
    gid = epoch_q["scope"][len("group:"):]
    b["processing_results"] = [*b["processing_results"], _na(gid, B.NA_NO_XAS_CHANNEL)]
    after = Q.consolidate(b)
    now = Q.question(after, epoch_q["question_id"])
    assert now["tier"] == Q.TIER_OPTIONAL and now["affects_record"] is False and now["why"].startswith("Not a record")
    assert "Not a record as it stands: its group cannot export" in now["text"]
    beamtime = Q.question(after, Q.STATED_UTC_START_QUESTION_ID)
    assert beamtime["not_reached"] == [] and beamtime["not_a_record"] == [gid]
    assert "It leaves out 1 other group(s) that cannot become a record as they stand" in beamtime["text"]
    assert after["counts"]["conflicts_affecting_a_record"] < before["counts"]["conflicts_affecting_a_record"]
    assert _ids(after) == _ids(before)


def test_a_reached_group_that_cannot_export_keeps_the_beamtime_targets_and_is_counted(grouped):
    b = M.load(grouped)
    before = Q.consolidate(b)
    beamtime = Q.question(before, Q.STATED_UTC_START_QUESTION_ID)
    gid = next(iter(beamtime["per_scope_targets"]))[len("group:"):]
    b["processing_results"] = [*b["processing_results"], _na(gid, B.NA_NO_XAS_CHANNEL)]
    now = Q.question(Q.consolidate(b), Q.STATED_UTC_START_QUESTION_ID)
    assert now["targets"] == beamtime["targets"]
    n = beamtime["applies_to"]["groups"]
    assert now["applies_to"]["groups_that_can_export"] == n - 1
    assert f"Only {n - 1} of these {n} groups can become a record; 1 cannot export" in now["text"]


# --- J4 ------------------------------------------------------------------------------------------------------------


def test_a_zone_less_local_clock_reading_is_not_comparable_with_the_utc_start(grouped):
    b = M.load(grouped)
    clock = next(c for c in b["candidates"] if c["target_field_path"] == START
                 and c["statement_key"] == "acquisition_timestamp" and c["run_id"] == "run-001")
    out = R._witnesses(clock, "2100-01-01T08:00:00Z", {"decision": "correct"})
    assert out and all(w["relation"] == R.NOT_COMPARABLE and w["note"] == R.NOT_COMPARABLE_NOTE for w in out)
    epoch = next(c for c in b["candidates"] if c["target_field_path"] == START
                 and c["statement_key"] == "acquisition_epoch" and c["run_id"] == "run-001")
    other = R._witnesses(epoch, "2100-01-02T08:00:00Z", {"decision": "correct"})
    assert other and all(w["relation"] == "contradicts" for w in other)  # a UTC instant that differs still does
    assert R._zone_less_clock(START, "2100-01-01T00:00:00", "2100-01-01T08:00:00Z")
    assert not R._zone_less_clock(START, "2100-01-01T00:00:00+00:00", "2100-01-01T08:00:00Z")
    assert not R._zone_less_clock("sample.material.name", "Fri Jan 01 00:00:00 2100", "x")


# --- J5 / J6 -------------------------------------------------------------------------------------------------------


def test_an_in_situ_warning_is_in_the_evidence_notes_and_the_dry_run(bdir, tmp_path):
    _decide_everything(bdir)
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, "context.environment", "run-001")], decision="correct", value="in_situ", **BY)
    out = tmp_path / "records"
    res = R.export_records(bdir, out, run_portal=_portal("publish"))
    [row] = res["exported"]
    stem = next(r["stem"] for r in b["runs"] if r["run_id"] == "run-001")
    assert row["label"] == stem
    sidecar = json.loads((out / row["sidecar"]).read_text())
    assert any("an in-situ record" in n for n in sidecar["notes"])
    [plan] = R.upload_plan(out, None)
    assert plan["label"] == stem and any("an in-situ record" in n for n in plan["notes"])
    assert "an in-situ record" in R.upload_summary([plan], out, None)["statement"]


def test_a_refused_row_carries_its_label_too(bdir, tmp_path):
    _decide_everything(bdir, sample_form=False)
    res = R.export_records(bdir, tmp_path / "records", run_portal=_portal("publish"))
    stem = next(r["stem"] for r in M.load(bdir)["runs"] if r["run_id"] == "run-001")
    assert [r["label"] for r in res["refused"] if r["group_id"] == "g1"] == [stem]


def _in_situ_runs():
    return [{"run_id": "run-1", "stem": "ZZ9_01_SYNTH_OCV_10MNaOH_500mV", "scans": [{"relative_path": "ZZ9_01_SYNTH_OCV_10MNaOH_500mV"}]}]


def _fields(mode=None):
    out = {"context.environment": {"value": "in_situ", "status": "verified", "evidence": []}}
    if mode:
        out[B.CONTROL_MODE_PATH] = {"value": mode, "status": "verified", "evidence": []}
    return out


def test_an_open_circuit_name_token_is_not_quoted_when_the_confirmed_mode_says_otherwise():
    bundle = {"candidates": [], "missing_values": []}
    [held] = R._in_situ_warnings(bundle, {"group_id": "gz"}, _in_situ_runs(), _fields("potentiostatic"), {})
    assert [s["literal"] for s in held["stated"]] == ["10MNaOH"] and "state OCV" not in held["text"]
    [open_] = R._in_situ_warnings(bundle, {"group_id": "gz"}, _in_situ_runs(), _fields("open_circuit"), {})
    assert [s["literal"] for s in open_["stated"]] == ["OCV", "10MNaOH"] and "state OCV" in open_["text"]
    [none] = R._in_situ_warnings(bundle, {"group_id": "gz"}, _in_situ_runs(), _fields(), {})
    assert [s["literal"] for s in none["stated"]] == ["OCV", "10MNaOH"]


def test_group_labels_skip_a_run_kept_as_context(grouped):
    b = M.load(grouped)
    g = b["record_groups"][0]
    runs = {r["run_key"]: r for r in b["runs"]}
    extra = next(r for r in b["runs"] if r["run_key"] not in g["member_run_keys"])
    g["member_run_keys"] = [extra["run_key"], *g["member_run_keys"]]
    g["context_run_keys"] = [extra["run_key"]]
    assert R.group_labels(b)[g["group_id"]] == runs[g["member_run_keys"][1]]["stem"]


# --- J7 ------------------------------------------------------------------------------------------------------------


def test_the_counter_question_counts_no_context_run(grouped):
    b = M.load(grouped)
    b["grouping_questions"] = [{"id": "gq-syn", "kind": "naming_counter_positions", "positions": [1],
                                "text": "Which filename token positions are run or acquisition counters?"}]
    whole = next(q for q in Q.consolidate(b)["questions"] if q["kind"] == "naming_counter_positions")
    assert whole["applies_to"]["runs"] == len(b["runs"])
    g = b["record_groups"][0]
    extra = next(r for r in b["runs"] if r["run_key"] not in g["member_run_keys"])
    g["context_run_keys"] = [extra["run_key"]]
    now = next(q for q in Q.consolidate(b)["questions"] if q["kind"] == "naming_counter_positions")
    assert now["applies_to"]["runs"] == len(b["runs"]) - 1
    assert now["question_id"] == whole["question_id"]


# --- docs ----------------------------------------------------------------------------------------------------------


SKILL = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "isaac-historical-import"


def test_the_skill_docs_say_the_r7j_rules():
    ref = "\n".join(p.read_text(encoding="utf-8") for p in (SKILL / "reference").glob("*.md"))
    for said in ("started more than once", "groups_that_can_export", "not_comparable", "no_scans"):
        assert said in ref, said
    assert len((SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()) <= 250


# --- r7 review -----------------------------------------------------------------------------------------------------


def test_the_beamtime_start_question_affects_no_record_when_no_group_it_reaches_can_export(grouped):
    b = M.load(grouped)
    beamtime = Q.question(Q.consolidate(b), Q.STATED_UTC_START_QUESTION_ID)
    assert beamtime["affects_record"] and beamtime["tier"] == Q.TIER_CONFLICT
    gids = [scope[len("group:"):] for scope in beamtime["per_scope_targets"]]
    b["processing_results"] = [*b["processing_results"], *(_na(g, B.NA_NO_XAS_CHANNEL) for g in gids)]
    now = Q.question(Q.consolidate(b), Q.STATED_UTC_START_QUESTION_ID)
    assert now["targets"] == beamtime["targets"]
    assert now["affects_record"] is False and now["tier"] == Q.TIER_OPTIONAL and now["why"].startswith("Not a record")
    assert f"None of these {len(gids)} groups can become a record as they stand" in now["text"]


def test_a_no_xas_channel_group_says_named_channels_can_make_it_exportable(grouped):
    b = M.load(grouped)
    gid = b["record_groups"][0]["group_id"]
    b["processing_results"] = [*b["processing_results"], _na(gid, B.NA_NO_XAS_CHANNEL)]
    payload = Q.consolidate(b)
    said = "re-processing with the channels named (`isaac process --params-file`, channels.*) can make it exportable"
    assert said in payload["blocking_basis"]["record_composer"]["cannot_export_statement"]
    assert any(said in q["text"] for q in payload["questions"] if q.get("cannot_export_groups"))
    # a group with no scan is not told so
    other = b["record_groups"][1]["group_id"]
    b["processing_results"] = [_na(other, B.NA_NO_SCANS)]
    assert "channels.*" not in Q.consolidate(b)["blocking_basis"]["record_composer"]["cannot_export_statement"]


def test_a_local_clock_reading_converted_under_a_confirmed_zone_is_compared(grouped):
    b = M.load(grouped)
    clock = copy.deepcopy(next(c for c in b["candidates"] if c["target_field_path"] == START
                               and c["statement_key"] == "acquisition_timestamp" and c["run_id"] == "run-001"))
    for e in clock["evidence"]:
        e["normalization"] = [*(e.get("normalization") or ()),
                              {"step": B.LOCAL_CLOCK_CONVERT_STEP, "rule_id": "syn", "from": "x", "to": "y"}]
    later = "2100-01-02T08:00:00Z"
    assert all(w["relation"] == "contradicts" for w in R._witnesses(clock, later, {"decision": "correct"}, True))
    assert all(w["relation"] == "contradicts" for w in R._witnesses(clock, later, {"decision": "correct"}, lambda: True))
    assert all(w["relation"] == R.NOT_COMPARABLE for w in R._witnesses(clock, later, {"decision": "correct"}, False))
    assert all(w["relation"] == R.NOT_COMPARABLE for w in R._witnesses(clock, later, {"decision": "correct"},
                                                                       lambda: False))
