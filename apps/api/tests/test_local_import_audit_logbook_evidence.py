"""Audit of 18 Nov 2026, finding 2: a logbook nobody read must never read as "the logbook has nothing", and a curve
approved before the evidence about its scans must be said. SYNTHETIC data only (``SYN_`` files, invented values).

(a) A processing result's logbook block says which of three things is true: no reading has been loaded for this
    beamtime although notes files are present; a reading was loaded and no note names these runs; or the notes.
    ``process``'s summary has one line for the first.
(b) ``approved_curve_older_than_evidence``: a scan note that lands on a run of a group whose result is already
    approved, or a newer result than the approved one, is a warning of ``build-records``, ``validate`` and ``export``
    that sorts first; a bulk approval refuses a result its group's evidence is newer than.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from isaac_api.local_import import approved_curve as AC
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R
from isaac_api.local_import import scan_notes as SN
from isaac_api.local_import import suggestions as S

from test_local_import_final_review import _portal, _with_group
from tests_support_records import BY, decide_everything, fake_upstream_env, pristine_bundle  # noqa: F401

LOGBOOK = ["SYNTHETIC LOGBOOK - every line is invented.",
           "Sample ZZ2 in the synthetic cell.",
           "File 02: start from scan #3, the first two were still evolving",
           "File 02: the synthetic potentiostat was noisy during this file",
           "File 01: the synthetic reference, nothing to remark"]


def _note(**over) -> dict:
    f = {"kind": "scan_note", "applies_to": {"scope": "runs", "runs": ["02_SYN_ZZ2_060mV"]}, "action": "start_from",
         "scans": [3], "reason": "the first two scans were still evolving",
         "source": {"path": "SYN_logbook.txt", "locator": "line 3"},
         "quote": "start from scan #3, the first two were still evolving", "strength": "stated", "reasoning": "synthetic"}
    f.update(over)
    return f


def _file(*findings) -> dict:
    return {"format": S.READINGS_FORMAT, "findings": list(findings)}


# --- (a) the three statements --------------------------------------------------------------------------------------


def _bundle(sources=(), unread=(), interpretations=(), notes=()) -> dict:
    return {"sources": [{"relative_path": p, "classification": {"source_type": t}} for p, t in sources],
            "unread_files": [{"relative_path": p} for p in unread],
            "ai_interpretations": list(interpretations), "scan_notes": list(notes), "runs": []}


def test_no_reading_loaded_beside_notes_files_is_its_own_state_and_names_the_files():
    b = _bundle(sources=[("SYN_logbook.txt", "beamtime_notes"), ("SYN_scan_001.dat", "scan_export")],
                unread=["SYN_logbook.docx"])
    st = SN.reading_state(b)
    assert st["state"] == SN.READING_NOT_LOADED
    assert st["notes_files"] == ["SYN_logbook.docx", "SYN_logbook.txt"] and st["findings_loaded"] == 0
    assert "No logbook reading has been loaded" in st["statement"]
    assert "SYN_logbook.txt" in st["statement"] and "SYN_scan_001.dat" not in st["statement"]
    # never the sentence that reads as "the logbook has nothing"
    assert "No logbook scan note names" not in st["statement"]


def test_a_loaded_reading_is_said_with_the_files_it_cites():
    b = _bundle(sources=[("SYN_logbook.txt", "beamtime_notes")],
                interpretations=[{"finding_id": "finding-001", "source_path": "SYN_logbook.txt"},
                                 {"blind": True}])  # a blind cross-check is no reading of the logbook
    st = SN.reading_state(b)
    assert st["state"] == SN.READING_LOADED and st["findings_loaded"] == 1 and st["files_cited"] == ["SYN_logbook.txt"]
    b = _bundle(sources=[("SYN_logbook.txt", "beamtime_notes")], interpretations=[{"blind": True}])
    assert SN.reading_state(b)["state"] == SN.READING_NOT_LOADED
    b = _bundle(sources=[("SYN_logbook.txt", "beamtime_notes")],
                notes=[{"scan_note_id": "sn-1", "source_path": "SYN_logbook.txt", "run_ids": ["run-001"]}])
    assert SN.reading_state(b)["state"] == SN.READING_LOADED


def test_a_folder_with_no_notes_file_and_no_reading_says_that():
    st = SN.reading_state(_bundle(sources=[("SYN_scan_001.dat", "scan_export")]))
    assert st["state"] == SN.NOTHING_TO_READ and "no notes" in st["statement"].lower()


np = pytest.importorskip("numpy", reason="the processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="the processing tests need the optional `processing` extra (xraylarch)")
pytest.importorskip("scipy", reason="the xas-analysis engine needs scipy")
pytest.importorskip("yaml", reason="the xas-analysis engine needs pyyaml")

import test_local_import_engine_xas as T  # noqa: E402
from isaac_api.local_import.processing import engine_xas as EX  # noqa: E402


@pytest.fixture()
def beamtime(tmp_path, monkeypatch):
    """Two SYN groups (4 and 8 scans) beside a SYN logbook; grouped, not processed, no reading loaded."""
    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v1")
    runs = [("01_SYN_ZZ1_060mV", 9, [T.scan_cols(10 + k) for k in range(4)]),
            ("02_SYN_ZZ2_060mV", 11, [T.scan_cols(60 + k) for k in range(8)])]
    root = tmp_path / "SYN_beamtime"
    T.write_beamtime(root, runs)
    (root / "SYN_logbook.txt").write_text("\n".join(LOGBOOK) + "\n", encoding="utf-8")
    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    M.group(out)
    return out, root


def _result(bdir, prefix):
    return T.by_run(T.v1_results(bdir), prefix)


def test_process_says_no_reading_was_loaded_once_and_on_each_result(beamtime):
    bdir, root = beamtime
    reply = M.process(bdir, source=str(root))
    lines = [x for x in reply["summary"]["lines"] if "No logbook reading has been loaded" in x]
    assert len(lines) == 1 and "SYN_logbook.txt" in lines[0], reply["summary"]["lines"]
    assert reply["logbook_reading"]["state"] == SN.READING_NOT_LOADED
    for prefix in ("01_SYN_ZZ1", "02_SYN_ZZ2"):
        lb = _result(bdir, prefix)[EX.LOGBOOK_KEY]
        assert lb["state"] == SN.READING_NOT_LOADED and lb["notes"] == []
        assert "No logbook reading has been loaded" in lb["statement"] and "SYN_logbook.txt" in lb["statement"]
        assert "No logbook scan note names these runs" not in lb["statement"]
    shown = EX.plain_result(_result(bdir, "02_SYN_ZZ2")) if hasattr(EX, "plain_result") else None
    if shown is not None:
        assert "No logbook reading has been loaded" in json.dumps(shown)


def test_after_a_reading_the_two_other_states_are_said_and_the_summary_line_is_gone(beamtime):
    bdir, root = beamtime
    done = M.annotate_from_readings(bdir, _file(_note()), model_id="SYN-MODEL", apply=True, root=root)
    assert done["scan_notes"] == 1
    reply = M.process(bdir, source=str(root))
    assert not [x for x in reply["summary"]["lines"] if "No logbook reading has been loaded" in x]
    assert reply["logbook_reading"]["state"] == SN.READING_LOADED
    named = _result(bdir, "02_SYN_ZZ2")[EX.LOGBOOK_KEY]
    assert named["state"] == "notes" and len(named["notes"]) == 1 and named["notes"][0]["drops"] == [1, 2]
    other = _result(bdir, "01_SYN_ZZ1")[EX.LOGBOOK_KEY]
    assert other["state"] == "read_no_note_for_these_runs" and other["notes"] == []
    assert "no scan note names these runs" in other["statement"] and "SYN_logbook.txt" in other["statement"]
    assert "No logbook reading has been loaded" not in other["statement"]


# --- (b) an approved curve older than its evidence ------------------------------------------------------------------


def _approve(bdir, result_id, group_id=None):
    if group_id:
        M.decide(bdir, target_ids=[group_id], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=[result_id], decision="approve", value=None, qc_status="valid", **BY)


def _stale(bdir, group_id):
    return AC.older_than_evidence(M.load(bdir), group_id)


def test_a_scan_note_landing_after_the_approval_is_warned_at_build_and_validate_first(beamtime):
    bdir, root = beamtime
    M.process(bdir, source=str(root))
    r = _result(bdir, "02_SYN_ZZ2")
    _approve(bdir, r["result_id"], r["group_id"])
    assert _stale(bdir, r["group_id"]) is None
    M.annotate_from_readings(bdir, _file(_note()), model_id="SYN-MODEL", apply=True, root=root)
    found = _stale(bdir, r["group_id"])
    assert found["approved_result_id"] == r["result_id"]
    assert [x["why"] for x in found["evidence"]] == ["scan_note_not_in_the_approved_curve"]
    built = R.build_records(bdir)
    [w] = [w for w in built["warnings"] if w["code"] == AC.WARNING]
    assert w["group_id"] == r["group_id"] and "start_from" in w["text"] and "isaac process" in w["command"]
    assert built["warnings"][0]["code"] == AC.WARNING                      # it sorts first
    v = R.validate_records(bdir)
    assert v["warnings"][0]["code"] == AC.WARNING
    report = json.loads((bdir / "validation" / f"{r['group_id']}.json").read_text())
    assert report["warnings"][0]["code"] == AC.WARNING
    assert R.warning_rank(AC.WARNING) < R.warning_rank(R.STATED_POTENTIAL_WARNING)


def test_processing_again_leaves_the_old_curve_approved_and_says_a_newer_result_exists(beamtime):
    bdir, root = beamtime
    M.process(bdir, source=str(root))
    r = _result(bdir, "02_SYN_ZZ2")
    _approve(bdir, r["result_id"], r["group_id"])
    M.annotate_from_readings(bdir, _file(_note()), model_id="SYN-MODEL", apply=True, root=root)
    reply = M.process(bdir, source=str(root), group_ids=[r["group_id"]])
    mine = [x for x in T.v1_results(bdir) if x["group_id"] == r["group_id"]]
    assert len(mine) == 2
    newer = next(x for x in mine if x["result_id"] != r["result_id"])
    found = _stale(bdir, r["group_id"])
    assert {x["why"] for x in found["evidence"]} == {"scan_note_not_in_the_approved_curve", "newer_result"}
    assert found["newer_result_ids"] == [newer["result_id"]]
    assert any(AC.WARNING in json.dumps(x) or "older than" in x for x in reply["summary"]["lines"]), reply["summary"]["lines"]
    # approving the newer result (after withdrawing the old approval) clears it
    M.decide(bdir, target_ids=[r["result_id"]], decision="reject", value=None, **BY)
    _approve(bdir, newer["result_id"])
    assert _stale(bdir, r["group_id"]) is None


def test_keeping_the_old_curve_is_the_scientists_call_and_clears_the_warning(beamtime):
    bdir, root = beamtime
    M.process(bdir, source=str(root))
    r = _result(bdir, "02_SYN_ZZ2")
    _approve(bdir, r["result_id"], r["group_id"])
    M.annotate_from_readings(bdir, _file(_note()), model_id="SYN-MODEL", apply=True, root=root)
    M.process(bdir, source=str(root), group_ids=[r["group_id"]])
    newer = next(x for x in T.v1_results(bdir) if x["group_id"] == r["group_id"] and x["result_id"] != r["result_id"])
    M.decide(bdir, target_ids=[newer["result_id"]], decision="reject", value=None, **BY)
    found = _stale(bdir, r["group_id"])
    assert [x["why"] for x in found["evidence"]] == ["scan_note_not_in_the_approved_curve"]
    said = AC.warning(found)
    assert "approve" in said["command"] and "isaac process" not in said["text"]  # it was processed again already
    done = M.decide(bdir, target_ids=[r["result_id"]], decision="approve", value=None, qc_status="valid", **BY)
    assert done["recorded"] == [r["result_id"]]          # a new statement, never "unchanged"
    assert _stale(bdir, r["group_id"]) is None


def test_one_approval_of_a_result_processed_before_its_scan_note_waits_for_processing(beamtime):
    bdir, root = beamtime
    M.process(bdir, source=str(root))
    r = _result(bdir, "02_SYN_ZZ2")
    M.decide(bdir, target_ids=[r["group_id"]], decision="confirm", value=None, **BY)
    M.annotate_from_readings(bdir, _file(_note()), model_id="SYN-MODEL", apply=True, root=root)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=[r["result_id"]], decision="approve", value=None, qc_status="valid", **BY)
    assert "processed without 1 logbook scan note" in str(exc.value) and "isaac process" in str(exc.value)


def _flag(**over):
    return _note(action="flag", scans=[], reason="the synthetic potentiostat was noisy",
                 source={"path": "SYN_logbook.txt", "locator": "line 4"},
                 quote="the synthetic potentiostat was noisy during this file", **over)


def test_a_flag_note_after_the_approval_stays_until_the_curve_is_approved_again(beamtime):
    """A flag changes no scan, so processing again makes the same curve: what is older is the person's approval."""
    bdir, root = beamtime
    M.process(bdir, source=str(root))
    r = _result(bdir, "02_SYN_ZZ2")
    _approve(bdir, r["result_id"], r["group_id"])
    M.annotate_from_readings(bdir, _file(_flag()), model_id="SYN-MODEL", apply=True, root=root)
    assert [x["why"] for x in _stale(bdir, r["group_id"])["evidence"]] == ["scan_note_not_in_the_approved_curve"]
    M.process(bdir, source=str(root), group_ids=[r["group_id"]])
    mine = [x for x in T.v1_results(bdir) if x["group_id"] == r["group_id"]]
    assert [x["result_id"] for x in mine] == [r["result_id"]]                 # the same curve, still approved
    assert len(mine[0][EX.LOGBOOK_KEY]["notes"]) == 1                          # ...which now lists the note
    # the clocks have one-second resolution and all of this ran inside one: the approval's own snapshot decides
    assert [x["why"] for x in _stale(bdir, r["group_id"])["evidence"]] == ["scan_note_after_the_approval"]
    M.decide(bdir, target_ids=[r["result_id"]], decision="approve", value=None, qc_status="valid", **BY)
    assert _stale(bdir, r["group_id"]) is None


def test_an_approval_an_older_build_recorded_falls_back_to_the_two_timestamps():
    group = {"group_id": "g", "member_run_ids": ["run-001"], "status": "scientist_confirmed"}
    result = {"result_id": "p", "group_id": "g", "source": "isaac_protocol", "outputs": {"files": [{"role": "normalized"}]}}
    approve = {"decision_id": "d-1", "target": {"kind": "processing_result", "id": "p"}, "decision": "approve",
               "decided_utc": "2026-01-02T00:00:00Z"}
    note = {"scan_note_id": "sn-1", "run_ids": ["run-001"], "action": "exclude", "scans": [8], "reason": "SYN",
            "source_path": "SYN_logbook.txt", "locator": "line 1", "quote": "SYN", "recorded_utc": "2026-01-03T00:00:00Z"}
    b = {"record_groups": [group], "processing_results": [result], "scientist_decisions": [approve],
         "scan_notes": [note], "runs": [{"run_id": "run-001", "stem": "SYN_run"}]}
    assert [e["why"] for e in AC.older_than_evidence(b, "g")["evidence"]] == ["scan_note_after_the_approval"]
    note["recorded_utc"] = "2026-01-01T00:00:00Z"
    assert AC.older_than_evidence(b, "g") is None                                # the note was there first
    assert AC.older_than_evidence({**b, "scientist_decisions": []}, "g") is None  # nothing approved, nothing said


def test_a_bulk_approval_refuses_a_result_processed_before_its_scan_note(beamtime, capsys):
    bdir, root = beamtime
    M.process(bdir, source=str(root))
    a, b_ = _result(bdir, "01_SYN_ZZ1"), _result(bdir, "02_SYN_ZZ2")
    M.annotate_from_readings(bdir, _file(_note()), model_id="SYN-MODEL", apply=True, root=root)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=[a["result_id"], b_["result_id"]], decision="approve", value=None,
                 qc_status="valid", **BY)
    said = str(exc.value)
    assert b_["result_id"] in said and "scan note" in said and "isaac process" in said
    assert not [d for d in M.load(bdir)["scientist_decisions"] if d["decision"] == "approve"]
    # processed again, the same bulk call goes through: both results list what the logbook says
    M.process(bdir, source=str(root))
    a, b_ = _result(bdir, "01_SYN_ZZ1"), _result(bdir, "02_SYN_ZZ2")
    M.decide(bdir, target_ids=[a["result_id"], b_["result_id"]], decision="approve", value=None, qc_status="valid", **BY)


# --- (b) through export, on a hand-built group (no processing extra needed for the logic) -------------------------


@pytest.fixture()
def bdir(pristine_bundle, tmp_path):
    target = tmp_path / "b"
    shutil.copytree(pristine_bundle, target)
    _with_group(target)
    decide_everything(target, add_group=False)
    return target


def _second_result(bdir):
    b = M.load(bdir)
    gdir = bdir / "processing" / "g1"
    spec = gdir / "normalized2.csv"
    spec.write_text("# synthetic\nenergy_eV,norm,flat\n" + "\n".join(f"{1000 + 5 * i},{i / 21:.3f},{i / 21:.3f}" for i in range(21)) + "\n")
    newer = json.loads(json.dumps(b["processing_results"][0]))
    newer.update(result_id="p2", state="needs_review")
    newer["outputs"]["files"][0].update(relative_path="processing/g1/normalized2.csv",
                                        sha256=hashlib.sha256(spec.read_bytes()).hexdigest())
    b["processing_results"].append(newer)
    M.save_bundle(bdir, b)


def test_export_repeats_the_warning_first_and_once(bdir, tmp_path, fake_upstream_env):
    out = R.export_records(bdir, tmp_path / "out", run_portal=_portal())
    assert out["records_written"] == 1 and AC.WARNING not in json.dumps(out)
    _second_result(bdir)
    v = R.validate_records(bdir, run_portal=_portal())
    assert v["warnings"][0]["code"] == AC.WARNING and v["exportable"] == 1
    out = R.export_records(bdir, tmp_path / "out", run_portal=_portal())
    row = out["exported"][0]
    assert row["warnings"][0].startswith("Written with an approved curve older than its evidence")
    assert "p2" in row["warnings"][0]
    assert out["older_than_evidence"]["records"] == 1 and out["older_than_evidence"]["group_ids"] == ["g1"]
    assert "approved curve older than its evidence" in out["outcome"]


def test_a_bulk_approval_refuses_the_older_of_two_results(bdir):
    _second_result(bdir)
    M.decide(bdir, target_ids=["p1"], decision="defer", value=None, **BY)   # the approval withdrawn: both undecided
    b = M.load(bdir)
    other = json.loads(json.dumps(b["record_groups"][0]))
    assert AC.approval_problem(b, b["processing_results"][0], bulk=True) is not None
    assert AC.approval_problem(b, b["processing_results"][1], bulk=True) is None
    assert AC.approval_problem(b, b["processing_results"][0], bulk=False) is None  # on its own, the person decides
    assert other["group_id"] == "g1"


# --- review of PR 342, finding 1: only the runs whose scans the result processed --------------------------------


def _hand_built(note_run: str, *, inputs=("run-001",)):
    """A group of run-001 (scans processed) and run-002 (a context run, or a member that gave no scan), one approved
    result whose inputs are only run-001's scans, and one scan note on ``note_run`` recorded after the approval."""
    runs = [{"run_id": "run-001", "run_key": "k1", "stem": "SYN_a"}, {"run_id": "run-002", "run_key": "k2", "stem": "SYN_b"}]
    group = {"group_id": "g", "member_run_keys": ["k1", "k2"], "context_run_keys": ["k2"], "status": "scientist_confirmed"}
    stem = {r["run_id"]: r["stem"] for r in runs}
    result = {"result_id": "p", "group_id": "g", "source": "isaac_protocol",
              "inputs": [{"scan_id": f"{stem[r]}#1", "source_id": f"src-{r}"} for r in inputs],
              "outputs": {"files": [{"role": "normalized"}]},
              "logbook_notes": {"available": True, "notes": [], "state": "read_no_note_for_these_runs"},
              "scan_notes_at_approval": {"decision_id": "d-1", "scan_note_ids": []}}
    approve = {"decision_id": "d-1", "target": {"kind": "processing_result", "id": "p"}, "decision": "approve",
               "decided_utc": "2026-01-02T00:00:00Z"}
    note = {"scan_note_id": "sn-1", "run_ids": [note_run], "action": "exclude", "scans": [1], "reason": "SYN",
            "source_path": "SYN_logbook.txt", "locator": "line 1", "quote": "SYN", "recorded_utc": "2026-01-03T00:00:00Z"}
    return {"record_groups": [group], "processing_results": [result], "scientist_decisions": [approve],
            "scan_notes": [note], "runs": runs}, result


@pytest.mark.parametrize("why", ["context_run", "member_with_no_scan"])
def test_a_note_on_a_run_whose_scans_were_not_processed_never_holds_an_approval(why):
    b, result = _hand_built("run-002")
    if why == "member_with_no_scan":
        b["record_groups"][0]["context_run_keys"] = []
    assert AC.unlisted_notes(b, result) == []
    assert AC.approval_problem(b, result, bulk=False) is None and AC.approval_problem(b, result, bulk=True) is None
    assert AC.older_than_evidence(b, "g") is None
    # the same note on the run whose scans WERE processed is evidence the curve lacks
    b, result = _hand_built("run-001")
    assert [e["scan_note_id"] for e in AC.unlisted_notes(b, result)] == ["sn-1"]
    assert AC.older_than_evidence(b, "g")["evidence"][0]["why"] == AC.NOT_IN_CURVE


def test_a_result_with_no_readable_inputs_falls_back_to_the_members_that_are_not_context():
    b, result = _hand_built("run-002", inputs=())
    assert AC.unlisted_notes(b, result) == []          # run-002 is a context run
    b, result = _hand_built("run-001", inputs=())
    assert [e["scan_note_id"] for e in AC.unlisted_notes(b, result)] == ["sn-1"]


# --- review of PR 342, finding 2: "processed again" means a curve that lists the note ----------------------------


def test_only_a_result_that_lists_the_note_lets_the_older_curve_be_kept_on_its_own():
    b, result = _hand_built("run-001")
    b["scientist_decisions"] = []                                 # nothing approved yet: the scientist is choosing
    older = {**json.loads(json.dumps(result)), "result_id": "p-before", "prior_run_ids": []}
    result["prior_run_ids"] = []
    # a later result processed (and rejected) BEFORE the note arrived lists no note: it does not count
    b["processing_results"].append({**json.loads(json.dumps(result)), "result_id": "p-later", "state": "rejected"})
    assert not AC.processed_again(b, result)
    said = AC.approval_problem(b, result, bulk=False)
    assert said is not None and "Process the group again" in said
    # a result whose logbook block lists the note does
    listing = json.loads(json.dumps(result))
    listing.update(result_id="p-with-note", logbook_notes={"available": True, "state": "notes", "notes": [
        {"scan_note_id": "sn-1", "run": "SYN_a", "action": "exclude", "scans": [1]}]})
    b["processing_results"].append(listing)
    assert AC.processed_again(b, result)
    assert AC.approval_problem(b, result, bulk=False) is None
    assert AC.approval_problem(b, result, bulk=True) is not None   # never in a bulk call
    assert older["result_id"] == "p-before"
