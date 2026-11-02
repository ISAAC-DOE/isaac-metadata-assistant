"""r5f: fixes found by reading real beamtime walks. Synthetic only.

* M6   ``validate`` (and ``build-records``) rank warnings before they print the first five: a stated value left out of
       the record, or a portal warning, comes before the routine start-time note; ``--full`` keeps its order.
* M7   a macro's declared name that states another set-point than the file acquired in its place is raised as a
       set-point disagreement that affects the record, when run number AND timing tie the two; else nothing.
* L1   a result that fails ``too_few_common_points`` has a statement and scan counts, and no remedy offers
       re-processing it.
* L2   the skipped-scan sentence names the file, not the source id.
* L3   the upload dry run and ``export`` say the same warning once, with a count and one example question.
* L4   a spaced request is answered once its one-word form exists.
* L6   ``decide --as-said`` that kept the word exits 0 and says so first.
* the save of a bundle encodes it once and reads the schema once per control mode per refresh.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import isaac_api.historical_import as hist
import isaac_api.workspace as ws
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import.processing import run as PR

from test_local_import_vocabulary_requests import (  # noqa: F401  (fixtures)
    REACTION, WHO, _miss, _report, _said, _term, b, pristine_bundle,
)

FIXTURE = ws.REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
SETPOINT = "context.electrochemistry.potential_setpoint_V"
NOW = "2026-10-28T00:00:00Z"


# --- M6 ---------------------------------------------------------------------------------------------


def _w(group: str, code: str, n: int = 0) -> dict:
    return {"group_id": group, "code": code, "text": f"{code} {n}", "command": f"cmd {n}"}


def test_the_five_warnings_shown_put_a_value_left_out_before_the_start_time_note():
    warned = [_w(f"rg-{i}", R.START_TIME_WARNING, i) for i in range(8)] + [
        _w("rg-8", R.STATED_POTENTIAL_WARNING, 8), _w("rg-9", R.STATED_POTENTIAL_WARNING, 9)]
    out = R.warning_summary(warned, first=[])
    shown = [w["code"] for w in out["warnings"]]
    assert len(shown) == R.WARNINGS_SHOWN and shown[:2] == [R.STATED_POTENTIAL_WARNING] * 2
    assert shown[2:] == [R.START_TIME_WARNING] * 3
    assert out["warnings_total"] == 10 and out["warnings_omitted"] == 5


def test_full_keeps_every_warning_in_the_original_order():
    warned = [_w(f"rg-{i}", R.START_TIME_WARNING, i) for i in range(8)] + [_w("rg-8", R.STATED_POTENTIAL_WARNING, 8)]
    out = R.warning_summary(warned, first=[], full=True)
    assert [w["group_id"] for w in out["warnings"]] == [w["group_id"] for w in warned]
    assert "warnings_omitted" not in out


def test_at_equal_severity_an_exportable_groups_warnings_still_lead():
    warned = [_w("rg-b", R.STATED_POTENTIAL_WARNING, 1), _w("rg-a", R.STATED_POTENTIAL_WARNING, 2),
              _w("rg-b", R.START_TIME_WARNING, 3), _w("rg-a", R.START_TIME_WARNING, 4)]
    out = R.warning_summary(warned, first=["rg-a"])
    assert [(w["group_id"], w["code"]) for w in out["warnings"]] == [
        ("rg-a", R.STATED_POTENTIAL_WARNING), ("rg-b", R.STATED_POTENTIAL_WARNING),
        ("rg-a", R.START_TIME_WARNING), ("rg-b", R.START_TIME_WARNING)]


def test_a_value_left_out_of_a_group_that_is_not_exportable_still_beats_the_note_on_exportable_ones():
    warned = [_w(f"rg-{i}", R.START_TIME_WARNING, i) for i in range(6)] + [_w("rg-x", R.STATED_POTENTIAL_WARNING, 9)]
    out = R.warning_summary(warned, first=[f"rg-{i}" for i in range(6)])
    assert out["warnings"][0]["group_id"] == "rg-x" and out["warnings"][0]["group_exportable"] is False


def test_warning_rank_puts_a_portal_warning_with_the_severe_ones():
    assert R.warning_rank("portal:NO_DATA_OWNER") == R.warning_rank(R.STATED_POTENTIAL_WARNING) == 0
    assert R.warning_rank(R.START_TIME_WARNING) > R.warning_rank("something_else") > R.warning_rank(R.STATED_POTENTIAL_WARNING)


# --- M7 ---------------------------------------------------------------------------------------------


def _write_run(root: Path, stem: str, epoch: int) -> None:
    """One SYNTHETIC SPEC acquisition named ``stem`` (its ``#F`` and ``#E`` rewritten) with its two scan files."""
    src = "04_02_ZZ2_base_after500Cycling_filter20_800mV"
    text = (FIXTURE / src).read_text().replace(f"#F {src}", f"#F {stem}")
    lines = text.split("\n")
    lines[1] = f"#E {epoch}"
    (root / stem).write_text("\n".join(lines))
    (root / f"{stem}_dir").mkdir()
    for scan in sorted((FIXTURE / f"{src}_dir").iterdir()):
        (root / f"{stem}_dir" / scan.name.replace(src, stem)).write_text(scan.read_text())


def _corpus(tmp_path: Path, *, acquired=None, declared=None, macros=None, name="corpus") -> Path:
    """Three runs. By default run2's macro says 800mV and the file acquired between run1 and run3 says 700mV."""
    root = tmp_path / name
    root.mkdir()
    shutil.copy(FIXTURE / "Zz_XAS.mac", root / "Zz_XAS.mac")
    acquired = acquired or [("01_01_ZZ1_acid_fresh_filter10_100mV", 4102445400),
                            ("02_01_ZZ1_acid_fresh_filter10_700mV", 4102446000),
                            ("03_01_ZZ1_acid_fresh_filter10_400mV", 4102446600)]
    for stem, epoch in acquired:
        _write_run(root, stem, epoch)
    declared = declared or {1: "01_01_ZZ1_acid_fresh_filter10_100mV", 2: "02_01_ZZ1_acid_fresh_filter10_800mV",
                            3: "03_01_ZZ1_acid_fresh_filter10_400mV"}
    for n, stem in declared.items():
        (root / f"run{n}.mac").write_text(f"# SYNTHETIC FIXTURE -- read as TEXT, never executed.\nqdo Zz_XAS.mac\nnewfile {stem}\n")
    return root


def _build(root: Path) -> dict:
    ev: dict = {}
    reading, candidates = hist.read_local_archive(root, source_id="S", evidence_sink=ev)
    return B.build_bundle(reading, candidates, evidence_by_source=ev, source_kind="folder", created_utc=NOW)


def _links(bundle: dict) -> list[dict]:
    return [c for c in bundle["conflicts"] if c["kind"] == B.MACRO_SETPOINT_CONFLICT_KIND]


def test_a_macro_and_a_file_name_that_state_other_set_points_are_raised_when_run_and_time_tie_them(tmp_path):
    bundle = _build(_corpus(tmp_path))
    [cf] = _links(bundle)
    assert [r["value"] for r in cf["readings"]] == [0.7, 0.8]
    assert cf["readings"][1]["witnesses"][0]["relative_path"] == "run2.mac"
    # the macro's own conflicts are untouched, and the new one comes last: every existing id stands
    kinds = [c["kind"] for c in bundle["conflicts"]]
    assert "macro_declared_never_acquired" in kinds and "acquired_never_declared" in kinds
    assert bundle["conflicts"][-1] is cf and cf["conflict_id"] == f"conf-{len(bundle['conflicts']):03d}"
    assert B.validate_bundle(bundle) == []
    q = next(x for x in Q.consolidate(bundle)["questions"] if {"kind": "conflict", "id": cf["conflict_id"]} in x["targets"])
    assert q["affects_record"] is True and q["target_field_path"] == SETPOINT and q["kind"] == "resolve_conflict"
    assert "run2.mac" in q["text"] and "0.8 V" in q["text"] and "0.7 V" in q["text"]
    # the macro's own question still says it affects no record: its id and that wording are unchanged
    old = next(x for x in Q.consolidate(bundle)["questions"] if x["text"].startswith("The sources disagree (macro_declared_never_acquired"))
    assert old["affects_record"] is False


def test_the_same_corpus_without_the_macro_mismatch_raises_nothing(tmp_path):
    root = _corpus(tmp_path, acquired=[("01_01_ZZ1_acid_fresh_filter10_100mV", 4102445400),
                                       ("02_01_ZZ1_acid_fresh_filter10_800mV", 4102446000),
                                       ("03_01_ZZ1_acid_fresh_filter10_400mV", 4102446600)])
    assert _links(_build(root)) == []


def test_a_file_outside_the_time_slot_between_the_neighbours_is_not_linked(tmp_path):
    root = _corpus(tmp_path, acquired=[("01_01_ZZ1_acid_fresh_filter10_100mV", 4102445400),
                                       ("02_01_ZZ1_acid_fresh_filter10_700mV", 4102450000),  # after run3's file
                                       ("03_01_ZZ1_acid_fresh_filter10_400mV", 4102446600)])
    assert _links(_build(root)) == []


def test_two_undeclared_files_in_the_slot_are_not_guessed_between(tmp_path):
    root = _corpus(tmp_path, acquired=[("01_01_ZZ1_acid_fresh_filter10_100mV", 4102445400),
                                       ("02_01_ZZ1_acid_fresh_filter10_700mV", 4102446000),
                                       ("02_01_ZZ1_acid_fresh_filter10_650mV", 4102446100),
                                       ("03_01_ZZ1_acid_fresh_filter10_400mV", 4102446600)])
    assert _links(_build(root)) == []


def test_a_name_that_differs_in_more_than_the_potential_is_not_linked(tmp_path):
    root = _corpus(tmp_path, declared={1: "01_01_ZZ1_acid_fresh_filter10_100mV", 2: "02_09_ZZ1_acid_fresh_filter10_800mV",
                                       3: "03_01_ZZ1_acid_fresh_filter10_400mV"})
    assert _links(_build(root)) == []


def test_a_macro_without_both_neighbours_is_not_linked(tmp_path):
    root = _corpus(tmp_path, declared={1: "01_01_ZZ1_acid_fresh_filter10_100mV", 2: "02_01_ZZ1_acid_fresh_filter10_800mV"})
    assert _links(_build(root)) == []


def test_potential_token_volts_reads_only_a_clean_token():
    assert B._potential_token_volts("800mV") == 0.8 and B._potential_token_volts("m800mV") == -0.8
    assert B._potential_token_volts("1p2V") == 1.2 and B._potential_token_volts("000mV") == 0.0
    assert B._potential_token_volts("pH12") is None and B._potential_token_volts("800mVx") is None


def test_answering_the_set_point_disagreement_is_the_scientists_and_the_bundle_stays_valid(tmp_path):
    root = _corpus(tmp_path)
    out = tmp_path / "bundle"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    [cf] = _links(M.load(out))
    q = next(x for x in Q.consolidate(M.load(out))["questions"] if {"kind": "conflict", "id": cf["conflict_id"]} in x["targets"])
    assert cli.main(["bundle", "decide", str(out), "--question", q["question_id"], "--decision", "confirm", "--value", "0.8",
                     "--json", "--by", WHO]) == 0
    assert B.check_bundle(out) == []


# --- M7, the review: order of answers, macros that declare several files, folders, provenance -------------


def _imported(tmp_path: Path):
    out = tmp_path / "bundle"
    assert cli.main(["import", str(_corpus(tmp_path)), "--out", str(out)]) == 0
    b = M.load(out)
    [cf] = _links(b)
    qs = Q.consolidate(b)["questions"]
    qm = next(x for x in qs if {"kind": "conflict", "id": cf["conflict_id"]} in x["targets"])
    qv = next(x for x in qs if x["kind"] == "confirm_value" and cf["candidate_id"] in json.dumps(x["targets"]))
    return out, cf, qm, qv


def _macro_question(out: Path, cf: dict) -> list[dict]:
    return [x for x in Q.consolidate(M.load(out))["questions"] if {"kind": "conflict", "id": cf["conflict_id"]} in x["targets"]]


def _governing(out: Path, cf: dict):
    b = M.load(out)
    cand = next(c for c in b["candidates"] if c["candidate_id"] == cf["candidate_id"])
    return B.candidate_decision(b, cand)


def test_confirming_the_file_name_value_first_leaves_the_macro_question_open(tmp_path):
    out, cf, qm, qv = _imported(tmp_path)
    assert cli.main(["bundle", "decide", str(out), "--question", qv["question_id"], "--decision", "confirm", "--by", WHO]) == 0
    [open_q] = _macro_question(out, cf)
    assert open_q["affects_record"] is True and open_q["tier"] == qm["tier"] and not open_q.get("covered_by_decisions")


def test_the_macro_answer_wins_over_a_later_bare_confirm_of_the_candidate(tmp_path):
    out, cf, qm, qv = _imported(tmp_path)
    assert cli.main(["bundle", "decide", str(out), "--question", qm["question_id"], "--decision", "confirm", "--value", "0.8",
                     "--json", "--by", WHO]) == 0
    assert cli.main(["bundle", "decide", str(out), "--question", qv["question_id"], "--decision", "confirm", "--by", WHO]) == 0
    d = _governing(out, cf)
    assert d["target"] == {"kind": "conflict", "id": cf["conflict_id"]} and d["value"] == 0.8
    assert B.check_bundle(out) == []


def test_a_later_correction_with_a_value_on_the_candidate_is_the_scientists_new_word(tmp_path):
    out, cf, qm, qv = _imported(tmp_path)
    assert cli.main(["bundle", "decide", str(out), "--question", qm["question_id"], "--decision", "confirm", "--value", "0.8",
                     "--json", "--by", WHO]) == 0
    assert cli.main(["bundle", "decide", str(out), "--target", cf["candidate_id"], "--decision", "correct", "--value", "0.75",
                     "--json", "--by", WHO]) == 0
    assert _governing(out, cf)["value"] == 0.75


def test_the_candidates_question_says_what_the_macro_states_and_names_the_question_that_settles_it(tmp_path):
    out, cf, qm, qv = _imported(tmp_path)
    assert "run2.mac states 0.8 V" in qv["text"] and "the file name states 0.7 V" in qv["text"] and qm["question_id"] in qv["text"]


def _multi(tmp_path: Path, acquired, macros, name="multi") -> Path:
    root = tmp_path / name
    root.mkdir()
    shutil.copy(FIXTURE / "Zz_XAS.mac", root / "Zz_XAS.mac")
    for stem, epoch in acquired:
        _write_run(root, stem, epoch)
    for fn, stems in macros.items():
        (root / fn).write_text("# SYNTHETIC FIXTURE -- read as TEXT, never executed.\nqdo Zz_XAS.mac\n" + "".join(f"newfile {x}\n" for x in stems))
    return root


P = "ZZ1_acid_fresh_filter10"


def test_a_neighbour_macro_that_declares_two_files_sets_no_window(tmp_path):
    root = _multi(tmp_path, [(f"01_01_{P}_100mV", 4102445400), (f"03_01_{P}_400mV", 4102446600), (f"02_01_{P}_700mV", 4102447200),
                             (f"03_02_{P}_500mV", 4102447800)],
                  {"run1.mac": [f"01_01_{P}_100mV"], "run2.mac": [f"02_01_{P}_800mV"],
                   "run3.mac": [f"03_01_{P}_400mV", f"03_02_{P}_500mV"]})
    assert _links(_build(root)) == []  # run3.mac declares two files: its start is not one time, and the 700mV file is inside it


def test_a_macro_that_declares_two_names_is_not_linked_either(tmp_path):
    root = _multi(tmp_path, [(f"01_01_{P}_100mV", 4102445400), (f"02_01_{P}_700mV", 4102446000), (f"03_01_{P}_400mV", 4102446600)],
                  {"run1.mac": [f"01_01_{P}_100mV"], "run2.mac": [f"02_01_{P}_800mV", f"02_01_{P}_900mV"], "run3.mac": [f"03_01_{P}_400mV"]})
    assert _links(_build(root)) == []


def test_run_numbers_of_different_folders_are_not_mixed(tmp_path):
    root = tmp_path / "twofolders"
    root.mkdir()
    shutil.copy(FIXTURE / "Zz_XAS.mac", root / "Zz_XAS.mac")
    (root / "day1").mkdir()
    (root / "day2").mkdir()
    for stem, ep in [(f"01_01_{P}_100mV", 4102445400), (f"03_01_{P}_400mV", 4102446600)]:
        _write_run(root / "day1", stem, ep)
    for stem, ep in [("01_01_B_100mV", 4102535400), (f"02_01_{P}_700mV", 4102446000), ("03_01_B_400mV", 4102536600)]:
        _write_run(root / "day2", stem, ep)
    for folder, n, stem in [("day1", 1, f"01_01_{P}_100mV"), ("day1", 3, f"03_01_{P}_400mV"), ("day2", 1, "01_01_B_100mV"),
                            ("day2", 2, f"02_01_{P}_800mV"), ("day2", 3, "03_01_B_400mV")]:
        (root / folder / f"run{n}.mac").write_text(f"qdo Zz_XAS.mac\nnewfile {stem}\n")
    assert _links(_build(root)) == []  # day2's neighbours are 1.2 days away from the 700mV file's own folder slot


def test_the_same_run_number_twice_in_one_folder_links_nothing(tmp_path):
    root = _corpus(tmp_path)
    (root / "run01.mac").write_text(f"qdo Zz_XAS.mac\nnewfile 01_01_ZZ1_acid_fresh_filter10_100mV\n")  # a second "run 1"
    assert _links(_build(root)) == []


def test_the_files_own_reading_must_be_what_the_candidate_holds(tmp_path):
    root = _corpus(tmp_path)
    ev: dict = {}
    reading, candidates = hist.read_local_archive(root, source_id="S", evidence_sink=ev)
    bundle = B.build_bundle(reading, candidates, evidence_by_source=ev, source_kind="folder", created_utc=NOW)
    [cf] = _links(bundle)
    assert "Same run number" not in cf["explanation"] and "tie the two to one measurement" in cf["explanation"]
    bad = [dict(c, value=0.65) if c["candidate_id"] == cf["candidate_id"] else c for c in bundle["candidates"]]
    assert B._macro_setpoint_conflicts(bundle["runs"], [c for c in bundle["conflicts"] if c["kind"] != B.MACRO_SETPOINT_CONFLICT_KIND],
                                       bad, bundle["sources"]) == []


def test_the_unknown_candidate_check_holds_for_every_kind_and_the_exemption_is_the_set_point_only(tmp_path):
    b = _build(_corpus(tmp_path))
    [cf] = _links(b)
    x = copy.deepcopy(b)
    next(c for c in x["conflicts"] if c["conflict_id"] == cf["conflict_id"])["candidate_id"] = "cand-9999"
    assert any("unknown candidate cand-9999" in e for e in B.validate_bundle(x))
    x = copy.deepcopy(b)
    cand = next(c for c in x["candidates"] if c["value"] is not None and c["target_field_path"] not in (None, SETPOINT) and c["run_id"]
                and c["state_basis"]["unresolved_reason"] is None)
    fake = {**copy.deepcopy(cf), "conflict_id": f"conf-{len(x['conflicts']) + 1:03d}", "candidate_id": cand["candidate_id"]}
    x["conflicts"].append(fake)
    assert any("records no disagreement" in e for e in B.validate_bundle(x))
    assert B.validate_bundle(b) == []


def test_no_older_legacy_question_id_moves(tmp_path):
    b = _build(_corpus(tmp_path))
    ids = [q["target"]["id"] for q in b["questions"]]
    assert b["questions"][-1]["target"]["id"] == _links(b)[0]["conflict_id"] and len(ids) == len(set(ids))


# --- L1, L2 -----------------------------------------------------------------------------------------


def _failed_result(extra_inputs=()):
    res = {"group_id": "rg-synthetic", "inputs": [{"source_id": "src-1", "used": True}, {"source_id": "src-2", "used": True}, *extra_inputs],
           "qc": {}, "steps": []}
    return PR._fail_too_few_common(res, 2, 14, 20)


def test_too_few_common_points_has_a_statement_and_the_scan_counts():
    out = _failed_result()
    assert out["failure"] == {"code": "too_few_common_points", "detail": "14"}
    said = out["qc"]["statements"]["too_few_common_points"]
    assert "2 of 2 listed scans were used" in said and "share 14 points" in said and "at least 20" in said
    assert "cannot add points" in said
    assert out["qc"]["metrics"]["scans_listed"] == 2 and out["qc"]["metrics"]["scans_used"] == 2
    assert out["qc"]["metrics"]["reprocess_cannot_help"] is True
    assert cli._scans_line(out) == "2 of 2 scans used"


def test_a_single_short_scan_says_its_own_points():
    res = {"group_id": "rg-synthetic", "inputs": [{"source_id": "src-1", "used": True}], "qc": {}, "steps": []}
    out = PR._fail_too_few_common(res, 1, 14, 20)
    assert out["qc"]["statements"]["too_few_common_points"].startswith("1 of 1 listed scan was used, and it has 14 usable points; the merge needs at least 20.")
    assert out["qc"]["metrics"]["reprocess_cannot_help"] is True


def test_cannot_help_is_not_said_when_a_scan_left_out_has_more_points():
    out = _failed_result([{"source_id": "src-3", "used": False, "skip_reason": "scan_lacks_chosen_columns", "diagnostics": {"points_read": 90}}])
    said = out["qc"]["statements"]["too_few_common_points"]
    assert "cannot add points" not in said and "1 scan left out of the merge has more points" in said
    assert out["qc"]["metrics"]["reprocess_cannot_help"] is False
    assert not M.reprocess_cannot_help(out)
    smaller = _failed_result([{"source_id": "src-3", "used": False, "skip_reason": "too_few_points", "diagnostics": {"points_read": 5}}])
    assert smaller["qc"]["metrics"]["reprocess_cannot_help"] is True


def test_the_failure_id_does_not_move_with_the_statement():
    plain = PR._fail({"group_id": "rg-synthetic", "inputs": [], "qc": {}, "steps": []}, "too_few_common_points", "14")
    assert _failed_result()["result_id"] == plain["result_id"]


def test_no_remedy_offers_re_processing_only_when_it_cannot_help():
    stuck, open_ = _failed_result(), _failed_result([{"source_id": "src-3", "used": False, "diagnostics": {"points_read": 90}}])
    assert M.reprocess_cannot_help(stuck) and not M.reprocess_cannot_help(open_)
    assert not M.reprocess_cannot_help({"failure": {"code": "no_edge"}, "qc": {"metrics": {"reprocess_cannot_help": True}}})
    assert not M.reprocess_cannot_help({"failure": {"code": "too_few_common_points"}, "qc": {"metrics": {}}})  # an older result
    said = R.processing_remedy({"group_id": "rg-synthetic", "no_curve_results": {"proc-x": "too_few_common_points: 14"}, "no_retry_results": ["proc-x"]})
    assert "--params-file" not in said and "cannot add points" in said and "--decision reject" in said
    assert "--params-file" in R.processing_remedy({"group_id": "rg-synthetic", "no_curve_results": {"proc-x": "too_few_common_points: 14"}})
    assert "--params-file" in R.processing_remedy({"group_id": "rg-synthetic", "no_curve_results": {"proc-x": "no_output_file"}})
    refusal = M.no_curve_refusal({**stuck, "result_id": "proc-x"})
    assert "--params-file" not in refusal and "cannot add points" in refusal and "--decision reject" in refusal
    assert "--params-file" in M.no_curve_refusal({**open_, "result_id": "proc-x"})


def test_the_skipped_scan_sentence_names_the_file_not_the_source_id():
    inputs = [{"source_id": "src-1", "relative_path": "S1_dir/S1_001.txt", "used": True},
              {"source_id": "src-1052", "relative_path": "S1_dir/S1_004.txt", "scan": None, "skip_reason": "scan_lacks_chosen_columns"},
              {"source_id": "src-1053", "relative_path": "S2.dat", "scan": 3, "skip_reason": "scan_lacks_chosen_columns"}]
    said = PR._skipped_scans_statement(inputs, SimpleNamespace(energy="E", signal_name="S"), 1)
    assert "S1_dir/S1_004.txt" in said and "S2.dat (scan 3)" in said and "src-1052" not in said and "src-1053" not in said


# --- L3 ---------------------------------------------------------------------------------------------

NOTE = "start time left out: the start-time disagreement is unanswered (question {q}; it offers the UTC reading)"


def test_the_same_warning_on_many_records_is_said_once_with_a_count_and_one_example():
    rows = group_rows = R.group_by_text([[NOTE.format(q=f"Q-{i:010x}"), "another note"] for i in range(1, 4)] + [[NOTE.format(q="Q-ffffffffff")]])
    assert [r["records"] for r in rows] == [4, 3]
    assert rows[0]["example_question"] == "Q-0000000001" and "<question id>" in rows[0]["text"]
    assert rows[1]["example_question"] is None
    said = R.grouped_sentence(group_rows)
    assert said.count("start time left out") == 1 and "(4 record(s), e.g. question Q-0000000001)" in said
    # a generator is read once, never twice
    assert R.group_by_text(([NOTE.format(q=f"Q-{i:010x}")] for i in range(1, 3)))[0]["example_question"] == "Q-0000000001"


def _records_dir(tmp_path: Path, n: int = 3) -> Path:
    d = tmp_path / "records"
    (d / R.EXPORT_STATE_DIR).mkdir(parents=True)
    index = []
    for i in range(n):
        rid = f"01SYNTHETIC{i:014d}"
        (d / f"{rid}.json").write_text(json.dumps({"record_id": rid}))
        (d / f"{rid}.evidence.json").write_text(json.dumps({"notes": [NOTE.format(q=f"Q-{i + 1:010x}")]}))
        index.append({"record_id": rid, "replaced_record_ids": [],
                      "portal_warnings": [{"code": "NO_DATA_OWNER", "path": "attribution/contributors", "message": "No data_owner."}]})
    (d / R.EXPORT_INDEX).write_text(json.dumps({"format": R.EXPORT_INDEX_FORMAT, "records": index}))
    return d


def test_the_dry_run_leads_with_the_count_and_says_each_note_and_portal_warning_once(tmp_path, capsys):
    d = _records_dir(tmp_path, 3)
    capsys.readouterr()
    assert cli.main(["bundle", "upload", str(d), "--dry-run", "--portal-url", "https://portal.example/"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["statement"].startswith("3 records, 2 requests each, to https://portal.example. Nothing was sent.")
    assert out["statement"].count("start time left out") == 1 and "(3 record(s), e.g. question Q-0000000001)" in out["statement"]
    assert out["statement"].count("NO_DATA_OWNER") == 1 and "(3 record(s))" in out["statement"]
    assert out["network_calls"] == 0 and len(out["records"]) == 3 and out["portal_warnings"][0]["records"] == 3
    assert all(r["notes"] for r in out["records"])  # a record's own notes stay in its row
    assert len(out["statement"]) < 1000


def test_the_dry_run_statement_does_not_grow_with_the_number_of_records(tmp_path, capsys):
    small, large = _records_dir(tmp_path / "a", 2), _records_dir(tmp_path / "b", 40)
    said = []
    for d in (small, large):
        capsys.readouterr()
        assert cli.main(["bundle", "upload", str(d), "--dry-run"]) == 0
        said.append(json.loads(capsys.readouterr().out)["statement"])
    assert abs(len(said[1]) - len(said[0])) < 40 and said[1].startswith("40 records, 2 requests each, to <portal-url>.")


def test_the_dry_run_without_an_export_index_names_no_portal_warning_and_still_leads(tmp_path, capsys):
    d = _records_dir(tmp_path, 2)
    (d / R.EXPORT_INDEX).unlink()
    capsys.readouterr()
    assert cli.main(["bundle", "upload", str(d), "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["statement"].startswith("2 records, 2 requests each, to <portal-url>.") and "portal_warnings" not in out


# --- L4, L6 -----------------------------------------------------------------------------------------


def test_a_spaced_request_is_answered_once_its_one_word_form_is_kept(b, capsys):
    assert _said(b, capsys, "--target", _miss(b, REACTION)["value_id"], "--decision", "correct", "--value", "cathodic corrosion")[0] == 0
    report = _report(b, capsys)
    assert report["totals"]["need_one_word"] == 1
    assert _said(b, capsys, "--target", _miss(b, REACTION, 1)["value_id"], "--decision", "correct", "--value", "cathodic_corrosion")[0] == 0
    report = _report(b, capsys)
    spaced = _term(report, REACTION, "cathodic corrosion")["draft"]
    assert report["totals"]["need_one_word"] == 0 and "ask" not in spaced and spaced["drafted"] is False
    assert spaced["one_word_form_given"] == "cathodic_corrosion" and "one word" in spaced["reason"]
    assert _term(report, REACTION, "cathodic_corrosion")["draft"]["drafted"] is True


def test_merge_after_the_one_word_form_no_longer_says_a_term_needs_one(b, capsys, tmp_path):
    out = tmp_path / "terms.json"
    assert _said(b, capsys, "--target", _miss(b, REACTION)["value_id"], "--decision", "correct", "--value", "cathodic corrosion")[0] == 0
    capsys.readouterr()
    assert cli.main(["bundle", "propose-terms", str(b), "--out", str(out)]) == 0
    assert "1 term(s) need a one-word form (ask)." in capsys.readouterr().out
    assert _said(b, capsys, "--target", _miss(b, REACTION, 1)["value_id"], "--decision", "correct", "--value", "cathodic_corrosion")[0] == 0
    capsys.readouterr()
    assert cli.main(["bundle", "propose-terms", str(b), "--out", str(out), "--merge"]) == 0
    assert "need a one-word form" not in capsys.readouterr().out
    merged = json.loads(out.read_text(encoding="utf-8"))
    assert merged["totals"]["need_one_word"] == 0
    assert _term(merged, REACTION, "cathodic corrosion")["draft"]["one_word_form_given"] == "cathodic_corrosion"


def test_a_spaced_request_whose_one_word_form_is_on_the_list_says_it_is_on_the_list(b, capsys):
    from isaac_api.local_import import propose_terms as P

    env = "context.environment"
    assert _said(b, capsys, "--target", _miss(b, env)["value_id"], "--decision", "correct", "--value", "ex situ")[0] == 0
    entry = _term(_report(b, capsys), env, "ex situ")
    assert "ask" not in entry["draft"] and entry["draft"]["one_word_form_given"] == "ex_situ"
    assert "on the field's list" in entry["draft"]["reason"] and "scientist has given" not in entry["draft"]["reason"]


def test_the_export_outcome_names_at_most_five_warning_kinds_and_counts_the_rest():
    rows = [{"text": f"w{i}", "records": 3, "example_question": None} for i in range(8)]
    said = R.warnings_outcome_sentence(rows)
    assert said.count("record(s)") == R.WARNINGS_SHOWN and "w4" in said and "w5" not in said and "and 3 more kinds" in said
    assert "more kind" not in R.warnings_outcome_sentence(rows[:5])


def test_a_spaced_request_with_no_one_word_form_still_asks(b, capsys):
    assert _said(b, capsys, "--target", _miss(b, REACTION)["value_id"], "--decision", "correct", "--value", "cathodic corrosion")[0] == 0
    draft = _term(_report(b, capsys), REACTION, "cathodic corrosion")["draft"]
    assert "ask" in draft and "one_word_form_given" not in draft


def test_as_said_that_kept_the_word_exits_0_and_says_so_first(b, capsys):
    capsys.readouterr()
    code = cli.main(["bundle", "decide", str(b), "--target", _miss(b, REACTION)["value_id"], "--decision", "correct",
                     "--value", "cathodic corrosion", "--as-said", "--by", WHO])
    out, err = capsys.readouterr()
    said = json.loads(out)
    assert code == 0 and err == ""
    assert said["vocabulary_request_kept"].startswith("vr-") and said["decision_recorded"] is False
    assert said["statement"].startswith("'cathodic corrosion' is kept as a vocabulary request")
    assert "No decision and no value was recorded" in said["statement"]
    assert not said["statement"].startswith("Nothing was recorded")
    [req] = M.load(b)["vocabulary_requests"]
    assert req["term"] == "cathodic corrosion"


def test_an_off_list_word_without_as_said_still_exits_2_and_keeps_nothing(b, capsys):
    capsys.readouterr()
    before = (b / "bundle.json").read_bytes()
    code = cli.main(["bundle", "decide", str(b), "--target", _miss(b, REACTION)["value_id"], "--decision", "correct",
                     "--value", "cathodic corrosion", "--by", WHO])
    out, err = capsys.readouterr()
    assert code == 2 and out == "" and "repeat with --as-said" in err
    assert (b / "bundle.json").read_bytes() == before


def test_the_library_still_raises_when_the_word_is_kept(b):
    with pytest.raises(M.OffListRefused) as got:
        M.decide(b, target_ids=[_miss(b, REACTION)["value_id"]], decision="correct", value="cathodic corrosion", by=WHO,
                 orcid=None, as_said=True)
    assert got.value.kept and got.value.kept["new"] is True and got.value.kept_statement().startswith("'cathodic corrosion'")


# --- the save --------------------------------------------------------------------------------------------


def test_a_save_encodes_the_bundle_once_and_reads_the_schema_once_per_control_mode(b, monkeypatch):
    encoded, schema_reads = [], []
    real_encode, real_required = B.encode, B.required_record_paths
    monkeypatch.setattr(B, "encode", lambda bundle: (encoded.append(1), real_encode(bundle))[1])
    monkeypatch.setattr(B, "required_record_paths", lambda *a, **k: (schema_reads.append(k.get("control_mode")), real_required(*a, **k))[1])
    M.decide(b, target_ids=[_miss(b, REACTION)["value_id"]], decision="defer", value=None, by=WHO, orcid=None)
    assert len(encoded) == 1
    # before: once per missing value (hundreds); now once per control mode for each refresh of the questions
    assert len(M.load(b)["missing_values"]) > 50 and len(schema_reads) <= 4
