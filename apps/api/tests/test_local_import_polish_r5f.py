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


# --- L1, L2 -----------------------------------------------------------------------------------------


def _failed_result():
    res = {"group_id": "rg-synthetic", "inputs": [{"source_id": "src-1"}, {"source_id": "src-2"}], "qc": {}, "steps": []}
    return PR._fail_too_few_common(res, 2, 14, 20)


def test_too_few_common_points_has_a_statement_and_the_scan_counts():
    out = _failed_result()
    assert out["failure"] == {"code": "too_few_common_points", "detail": "14"}
    said = out["qc"]["statements"]["too_few_common_points"]
    assert "2 of 2 listed scans were used" in said and "share 14 points" in said and "at least 20" in said
    assert "cannot add points" in said
    assert out["qc"]["metrics"]["scans_listed"] == 2 and out["qc"]["metrics"]["scans_used"] == 2
    assert cli._scans_line(out) == "2 of 2 scans used"


def test_a_single_short_scan_says_its_own_points():
    res = {"group_id": "rg-synthetic", "inputs": [{"source_id": "src-1"}], "qc": {}, "steps": []}
    said = PR._fail_too_few_common(res, 1, 14, 20)["qc"]["statements"]["too_few_common_points"]
    assert said.startswith("1 of 1 listed scan was used, and it has 14 usable points; the merge needs at least 20.")


def test_the_failure_id_does_not_move_with_the_statement():
    plain = PR._fail({"group_id": "rg-synthetic", "inputs": [], "qc": {}, "steps": []}, "too_few_common_points", "14")
    assert _failed_result()["result_id"] == plain["result_id"]


def test_no_remedy_offers_re_processing_a_group_whose_scans_share_too_few_points():
    from isaac_api.local_import.mutations import reprocess_cannot_help

    assert reprocess_cannot_help("too_few_common_points: 14") and reprocess_cannot_help(["too_few_common_points"])
    assert not reprocess_cannot_help("no_edge") and not reprocess_cannot_help([])
    said = R.processing_remedy({"group_id": "rg-synthetic", "no_curve_results": {"proc-x": "too_few_common_points: 14"}})
    assert "--params-file" not in said and "cannot add points" in said and "--decision reject" in said
    other = R.processing_remedy({"group_id": "rg-synthetic", "no_curve_results": {"proc-x": "no_output_file"}})
    assert "--params-file" in other
    refusal = M.no_curve_refusal({"result_id": "proc-x", "group_id": "rg-synthetic", "failure": {"code": "too_few_common_points", "detail": "14"},
                                  "qc": {"verdict": "fail"}})
    assert "--params-file" not in refusal and "cannot add points" in refusal and "--decision reject" in refusal


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
