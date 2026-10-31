"""Polish c11-r: review findings on c11-a. SYNTHETIC files only: every scan, project and value is invented (``SYN_``/ZZ).

* (H1) A run kept as one file per scan states no scan index. c11-a numbered its scans 1..N by POSITION, which is
  wrong when files are missing (001, 002, 004) or names are unpadded (``S_10`` sorted before ``S_2``). A scan's
  number is read from its file name (``_(\\d+).<ext>``, the rule ``bl15/relate.py`` states: read, never by
  position); when any name states none, or two share one, no number is known and the sentence is neutral.
* (H2) ``scan_subset_note`` worked from the stored ``scientist_selected_subset_of_scans`` flag of an older build:
  when every number is known and the label names exactly the merged scans it says nothing; when the numbers are
  not known it is neutral, whatever was stored.
* (M1) With some indexes stated and some not, the Athena ``scans_used`` statement compared the label with only the
  known numbers and said "includes scans 2-3, which ISAAC did not merge" although all 3 were merged.
* (M2) A decision kept on an old result whose fresh result now skips an all-zero scan is said, one line per group.
* (M3/LOW) docs; the all-zero rule's version; export's per-row warnings capped.
* A merged scan whose signal is exactly zero at points where another merged scan's is not is said and flagged; it
  is merged unchanged and no result id moves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R

SUBSET = "scientist_selected_subset_of_scans"
REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / ".claude" / "skills" / "isaac-historical-import"


def _pair(names, chosen, *, flagged=True, skipped=()):
    """An ISAAC result of one run whose inputs are the files ``names`` (no stated index) and its Athena sibling."""
    inputs = [{"source_id": f"s{k}", "scan": None, "relative_path": f"SYN_dir/{n}"} for k, n in enumerate(names)]
    for k in skipped:
        inputs[k]["skip_reason"] = "too_few_points"
    isa = {"group_id": "g1", "source": "isaac_protocol", "run_id": "r-1", "inputs": inputs}
    ath = {"group_id": "g1", "source": "scientist_athena", "run_id": "r-1",
           "comparison": {"flags": [SUBSET] if flagged else [], "athena_scan_selection": chosen}}
    return {"processing_results": [isa, ath]}, ath


# --- H1: the number is read from the file name, never counted by position -----------------------------------------


def test_the_scan_number_is_read_from_the_file_name():
    names = ["SYN_001.txt", "SYN_002.txt", "SYN_004.txt"]
    assert B.input_scan_numbers([{"relative_path": f"d/{n}"} for n in names]) == ([1, 2, 4], B.SCAN_NUMBERS_FROM_FILE_NAME)
    unpadded = sorted(f"S_{n}.dat" for n in range(1, 11))  # S_1, S_10, S_2, ...
    numbers, _ = B.input_scan_numbers([{"relative_path": n} for n in unpadded])
    assert numbers == [1, 10, 2, 3, 4, 5, 6, 7, 8, 9]
    # a name that states no number, or two that state the same one in one run: NO number is known
    assert B.input_scan_numbers([{"relative_path": "SYN_001.txt"}, {"relative_path": "SYN_last.txt"}]) == ([None, None], None)
    assert B.input_scan_numbers([{"relative_path": "a/SYN_001.txt"}, {"relative_path": "b/SYN_001.dat"}]) == ([None, None], None)
    # ... but the same number in two runs is two scans
    two = [{"source_id": "a", "relative_path": "a/SYN_001.txt"}, {"source_id": "b", "relative_path": "b/SYN_001.txt"}]
    assert B.input_scan_numbers(two, {"a": "run-a", "b": "run-b"}) == ([1, 1], B.SCAN_NUMBERS_FROM_FILE_NAME)
    # a stated index wins, as before
    assert B.input_scan_numbers([{"scan": 7, "relative_path": "SYN_001.txt"}]) == ([7], "stated")


def test_probe_gap_label_1_to_3_names_scan_3_the_run_does_not_list():
    bundle, ath = _pair(["SYN_001.txt", "SYN_002.txt", "SYN_004.txt"], [1, 2, 3])
    note = M.scan_subset_note(bundle, ath)
    assert "names scan(s) 3, which the run's 3 listed scans do not include" in note
    assert "did not merge" not in note


def test_probe_gap_label_4_is_listed_and_merged():
    bundle, ath = _pair(["SYN_001.txt", "SYN_002.txt", "SYN_004.txt"], [4])
    note = M.scan_subset_note(bundle, ath)
    assert "uses only scans 4 of the 3 scan(s) ISAAC merged" in note
    assert "do not include" not in note and "did not merge" not in note


def test_probe_files_5_to_8_label_5_6_is_part_of_the_merge():
    bundle, ath = _pair([f"SYN_{n:03d}.txt" for n in (5, 6, 7, 8)], [5, 6])
    note = M.scan_subset_note(bundle, ath)
    assert "uses only scans 5, 6 of the 4 scan(s) ISAAC merged" in note
    assert "do not include" not in note and "did not merge" not in note


def test_probe_unpadded_names_sorted_with_s2_skipped():
    names = sorted(f"S_{n}.dat" for n in range(1, 11))
    bundle, ath = _pair(names, [1, 2], skipped=[names.index("S_2.dat")])
    note = M.scan_subset_note(bundle, ath)
    assert "uses a different set of scans (1, 2) from the 9 scan(s) ISAAC merged, including scan(s) 2 that ISAAC did " \
           "not merge" in note
    assert "uses only" not in note


def test_names_without_a_number_or_with_a_repeated_one_are_neutral():
    for names in (["SYN_001.txt", "SYN_end.txt"], ["SYN_001.txt", "SYN_001.dat"]):
        bundle, ath = _pair(names, [1])
        note = M.scan_subset_note(bundle, ath)
        assert note.endswith("its E0 and curve describe those scans, which may not be ISAAC's merge.")
        assert "uses only" not in note and "did not merge" not in note


# --- H2: never trust the stored flag alone --------------------------------------------------------------------------


@pytest.mark.parametrize("flagged", [True, False])
def test_a_label_naming_every_merged_scan_says_nothing_whatever_was_stored(flagged):
    # an older build stored the flag for a one-file-per-scan run with label 1-3 (its numbers were unknown then)
    bundle, ath = _pair([f"SYN_{n:03d}.txt" for n in (1, 2, 3)], [1, 2, 3], flagged=flagged)
    assert M.scan_subset_note(bundle, ath) is None


@pytest.mark.parametrize("flagged", [True, False])
def test_unknown_numbers_give_the_neutral_sentence_whatever_was_stored(flagged):
    bundle, ath = _pair(["SYN_a.txt", "SYN_b.txt", "SYN_c.txt"], [1, 2, 3], flagged=flagged)
    note = M.scan_subset_note(bundle, ath)
    assert note and "may not be ISAAC's merge" in note and "not the full merge" not in note


def test_no_selection_and_no_flag_says_nothing():
    bundle, ath = _pair([f"SYN_{n:03d}.txt" for n in (1, 2)], [], flagged=False)
    assert M.scan_subset_note(bundle, ath) is None


# --- processing (numpy + xraylarch) -----------------------------------------------------------------------------


def _processing():
    pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")


def _named_case(tmp_path, names, label, *, stated=None, zero_from=None):
    """ONE run ``01_SYN_ZZ1`` whose scans are the files ``names`` (stating no index, as one file per scan does, or
    the indexes ``stated``); an Athena project of one group ``label`` (none when ``None``). ``zero_from``: {scan
    position (0-based): first point index} whose signal is exactly zero from that point on."""
    from test_local_import_polish_c10m import _prj
    from test_local_import_processing import GRID, _sha, fluo_scan, make_case, mu_edge, spec_file

    tmp_path.mkdir(parents=True, exist_ok=True)
    texts = []
    for k in range(len(names)):
        cols = fluo_scan(k + 1)
        if zero_from and k in zero_from:
            cols["vortDT"] = cols["vortDT"].copy()
            cols["vortDT"][zero_from[k]:] = 0.0
        texts.append(spec_file(cols))
    bdir, root, bundle = make_case(tmp_path, [("01_SYN_ZZ1", texts, {"sample_name": "ZZ1"})])
    by_sid = {s["source_id"]: s for s in bundle["sources"]}
    for k, (sc, name) in enumerate(zip(bundle["runs"][0]["scans"], names)):
        new = f"01_SYN_ZZ1_dir/{name}"
        (root / sc["relative_path"]).rename(root / new)
        sc["relative_path"] = by_sid[sc["source_id"]]["relative_path"] = new
        by_sid[sc["source_id"]]["content_sha256"] = _sha(root / new)
        sc["scan_index"] = stated[k] if stated else None
    if label:
        _prj(root / "SYN.prj", [(label, GRID, mu_edge(GRID) * 1e-2)])
        bundle["unread_files"].append({"source_id": "prj-SYN", "relative_path": "SYN.prj"})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


def _process(bdir, root):
    from test_local_import_polish_c10m import _process as run

    return run(bdir, root)


def test_processing_reads_the_numbers_from_the_file_names(tmp_path):
    _processing()
    bdir, root = _named_case(tmp_path / "gap", ["01_SYN_ZZ1_001.dat", "01_SYN_ZZ1_002.dat", "01_SYN_ZZ1_004.dat"],
                             "01_SYN_ZZ1_1-3")
    _, isa, ath = _process(bdir, root)
    assert SUBSET in isa["comparison"]["flags"]  # before: positions 1-3 "agreed" with the label, no flag
    said = ath["qc"]["statements"]["scans_used"]
    assert "It names scan 3, which the run's 3 listed scans do not include" in said and "did not merge" not in said
    assert "names scan(s) 3, which the run's 3 listed scans do not include" in M.scan_subset_note(
        {"processing_results": [isa, ath]}, ath)

    bdir, root = _named_case(tmp_path / "five", [f"01_SYN_ZZ1_{n:03d}.dat" for n in (5, 6, 7, 8)], "01_SYN_ZZ1_5-6")
    _, isa, ath = _process(bdir, root)
    said = ath["qc"]["statements"]["scans_used"]
    assert "It covers only scans 5-6 of the 4 scans ISAAC merged" in said
    assert "each scan's number is read from its file name" in said and "do not include" not in said
    assert isa["comparison"]["metrics"].get("rms_norm_same_scans_same_params") is not None


def test_mixed_stated_and_missing_indexes_never_say_not_merged(tmp_path):
    _processing()
    names = [f"01_SYN_ZZ1_{n:03d}.dat" for n in (1, 2, 3)]
    bdir, root = _named_case(tmp_path, names, "01_SYN_ZZ1_2-3", stated=[1, None, None])
    _, isa, ath = _process(bdir, root)
    said = ath["qc"]["statements"]["scans_used"]
    assert "did not merge" not in said and "different set" not in said and "covers only" not in said
    assert "The run's scans do not all state a scan number, so whether these are the scans ISAAC merged is not known." in said
    assert SUBSET in isa["comparison"]["flags"]
    note = M.scan_subset_note({"processing_results": [isa, ath]}, ath)
    assert "may not be ISAAC's merge" in note and "did not merge" not in note


def test_a_merged_scan_with_zero_signal_points_is_said_flagged_and_moves_no_id(tmp_path, monkeypatch):
    _processing()
    from isaac_api.local_import.processing import run as RUN
    from test_local_import_processing import GRID

    names = [f"01_SYN_ZZ1_{n:03d}.dat" for n in (1, 2, 3)]
    k = 22
    bdir, root = _named_case(tmp_path / "a", names, None, zero_from={2: k})
    _, isa, _ = _process(bdir, root)
    assert [i.get("skip_reason") for i in isa["inputs"]] == [None, None, None]  # merged, never skipped
    assert isa["inputs"][2]["diagnostics"]["signal_zero_points"] == GRID.size - k
    assert isa["inputs"][0]["diagnostics"]["signal_zero_points"] == 0
    said = isa["qc"]["statements"]["merged_scan_zero_signal_points"]
    assert said == (f"01_SYN_ZZ1_003.dat's signal (vortDT) is zero at {GRID.size - k} of {GRID.size} points (from "
                    f"{GRID[k]:.1f} eV on); it is merged unchanged. A person checks whether the beam was lost.")
    assert RUN.ZERO_SIGNAL_POINTS_FLAG in isa["review_flags"]
    # NOT in qc.json (hashed into the run id): the same data without the sentence gives the same id
    qc = next(f for f in isa["outputs"]["files"] if f["role"] == "qc")
    assert "merged_scan_zero_signal_points" not in (bdir / qc["relative_path"]).read_text()
    monkeypatch.setattr(RUN, "_zero_signal_points_statement", lambda *a, **k: None)
    bdir2, root2 = _named_case(tmp_path / "b", names, None, zero_from={2: k})
    _, isa2, _ = _process(bdir2, root2)
    assert isa2["result_id"] == isa["result_id"] and RUN.ZERO_SIGNAL_POINTS_FLAG not in isa2["review_flags"]


def test_zero_points_shared_by_every_scan_or_a_single_scan_are_not_flagged(tmp_path):
    _processing()
    from isaac_api.local_import.processing import run as RUN

    names = [f"01_SYN_ZZ1_{n:03d}.dat" for n in (1, 2)]
    bdir, root = _named_case(tmp_path / "both", names, None, zero_from={0: 200, 1: 200})
    _, isa, _ = _process(bdir, root)
    assert RUN.ZERO_SIGNAL_POINTS_FLAG not in isa["review_flags"]
    assert "merged_scan_zero_signal_points" not in (isa["qc"].get("statements") or {})
    bdir, root = _named_case(tmp_path / "one", names[:1], None, zero_from={0: 200})
    _, isa, _ = _process(bdir, root)
    assert RUN.ZERO_SIGNAL_POINTS_FLAG not in isa["review_flags"]
    bdir, root = _named_case(tmp_path / "none", names, None)
    _, isa, _ = _process(bdir, root)
    assert RUN.ZERO_SIGNAL_POINTS_FLAG not in isa["review_flags"]


def test_the_all_zero_rule_is_named_in_the_rule_versions():
    from isaac_api.local_import.processing import core as C
    from isaac_api.local_import.processing import protocol as P

    assert C.SIGNAL_ALL_ZERO_RULE_ID == "isaac.xas.skip_signal_all_zero.v0"
    assert C.SIGNAL_ALL_ZERO_RULE_ID in P.RULE_VERSIONS_SINCE_PROTOCOL_VERSION["rule_ids"]
    assert P.PROTOCOL_VERSION == "0.1.0"


# --- M2: a decision kept on an old result whose fresh result now leaves out an all-zero scan -----------------------


def _result(rid, skip=None):
    inputs = [{"source_id": f"src-{n}", "relative_path": f"SYN_dir/SYN_{n:03d}.dat"} for n in (1, 2, 3)]
    if skip:
        inputs[2]["skip_reason"] = "signal_all_zero"
    return {"result_id": rid, "group_id": "g1", "source": "isaac_protocol", "inputs": inputs}


def _decision(rid, decision="approve"):
    return {"decision_id": "dec-1", "target": {"kind": "processing_result", "id": rid}, "decision": decision,
            "decided_by": {"name": "SYN Scientist"}}


def test_a_kept_approval_whose_fresh_result_skips_an_all_zero_scan_is_said():
    old, new = _result("proc-g1-aaa-isaac"), _result("proc-g1-bbb-isaac", skip=True)
    bundle = {"scientist_decisions": [_decision(old["result_id"])]}
    [line] = M.decided_results_with_a_new_all_zero_skip(bundle, [old], [new])
    assert line["decided_result_id"] == "proc-g1-aaa-isaac" and line["new_result_id"] == "proc-g1-bbb-isaac"
    assert line["left_out"] == ["SYN_dir/SYN_003.dat"]
    said = line["statement"]
    assert said.startswith("Group g1: proc-g1-aaa-isaac (approve by SYN Scientist) merged SYN_003.dat, whose signal is "
                           "zero at every point; this build leaves it out, so the fresh curve is a new result, "
                           "proc-g1-bbb-isaac. The scientist can approve the new curve")
    assert said.endswith("The old approval still stands on proc-g1-aaa-isaac until they change it.")
    # NEGATIVE CONTROLS: no decision, or a fresh result that skips nothing new, says nothing
    assert M.decided_results_with_a_new_all_zero_skip({"scientist_decisions": []}, [old], [new]) == []
    assert M.decided_results_with_a_new_all_zero_skip(bundle, [old], [_result("proc-g1-ccc-isaac")]) == []
    assert M.decided_results_with_a_new_all_zero_skip(bundle, [_result(old["result_id"], skip=True)], [new]) == []


def test_process_says_it_in_its_reply(tmp_path, monkeypatch):
    from isaac_api.local_import.processing import cli_entry

    bdir = tmp_path / "b"
    old = _result("proc-g1-aaa-isaac")
    fresh = _result("proc-g1-bbb-isaac", skip=True)

    def fake(bundle_dir, **_k):
        return {"status": "processed", "summary": {"lines": []}, "processing_results": [dict(fresh)]}

    monkeypatch.setattr(cli_entry, "run_process", fake)
    state = {"record_groups": [{"group_id": "g1", "status": "proposed"}],
             "processing_results": [{**old, "state": "scientist_confirmed"}],
             "scientist_decisions": [_decision(old["result_id"])]}

    def fake_mutate(_dir, change):
        return change(state)

    monkeypatch.setattr(M, "load", lambda _d: dict(state))
    monkeypatch.setattr(M, "mutate", fake_mutate)
    out = M.process(bdir)
    assert out["kept_decided"] == 1 and out["new"] == 1
    [line] = out["decided_results_with_a_scan_now_left_out"]
    assert line["statement"] in out["summary"]["lines"]


# --- LOW: export's per-row warnings are capped like every other list ------------------------------------------------


from test_local_import_records import _decide_everything, _portal, bdir, pristine  # noqa: E402,F401  (fixtures)


def test_export_caps_a_rows_warnings_and_counts_them(bdir, tmp_path, monkeypatch):
    _decide_everything(bdir)
    R.build_records(bdir)
    monkeypatch.setattr(R, "WARNINGS_SHOWN", 0)
    out = R.export_records(bdir, tmp_path / "out", run_portal=_portal("publish"))
    [row] = out["exported"]
    assert row["warnings"] == [] and row["warnings_total"] == 1 and row["warnings_omitted"] == 1
    assert "validate <bundle_dir> --full" in row["warnings_full_list"]
    assert out["records_written_with_warnings"] == 1  # still counted when none is printed


# --- M3: the docs say it ------------------------------------------------------------------------------------------------


def test_the_docs_say_how_to_see_every_warning():
    commands = (SKILL / "reference" / "commands.md").read_text()
    records = (SKILL / "reference" / "records-and-validation.md").read_text()
    for text in (commands, records):
        for term in ("validate --full", "warnings_full_list", "group_exportable", "exported[].warnings",
                     "records_written_with_warnings"):
            assert term in text, term
    skill = (SKILL / "SKILL.md").read_text()
    assert "only 5 warnings show by default; `validate --full` lists all" in skill
    assert len(skill.splitlines()) <= 250


def test_the_processing_reference_names_the_file_and_says_zero_points():
    text = (SKILL / "reference" / "grouping-and-processing.md").read_text()
    assert "merged_scan_has_zero_signal_points" in text
    assert "naming the file as the statement does" in text and "scan 8's signal" not in text
    assert "it is merged unchanged" in text and "never leave it out yourself" in text
