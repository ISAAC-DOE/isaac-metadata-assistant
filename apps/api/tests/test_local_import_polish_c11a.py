"""Polish c11-a: walkthrough findings on a real BL15-2 beamtime (one file per scan), reproduced here.
SYNTHETIC files only: every scan, Athena project and value below is invented and named ``SYN_``.

* (HIGH) A run kept as one file per scan (``<stem>_dir/<stem>_001.txt``) states no scan index, so its inputs hold
  ``scan: None``. The Athena subset note compared the label's scan numbers with that empty set and said the curve
  used "a different set of scans … including scan(s) 1, 3, 4, 5, 6, 8 that ISAAC did not merge" although ISAAC had
  merged all 8; the sentence reached the exported record's notes. Such a run's scans are numbered 1..N in the
  order listed, the rule the import already states for a run that states no scan index
  (``bundle._scan_numbers``); a scan is said not merged only when the numbers are known, and a number the run
  does not list is said to be one.
* (MED-2) A warning that a record will not carry a stated condition is never invisible: ``validate`` lists the
  warnings of exportable groups first and ``--full`` prints every one; ``export`` lists, per record written, the
  warnings that still apply.
* (MED-3) A scan whose signal is zero at every point is skipped (``signal_all_zero``), counted and named, and the
  rest are merged; when every scan is, there is no curve.
* (LOW-4) ``reveal`` of a UTC instant against a reading with no time zone is "not comparable", with a note.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R

SUBSET = "scientist_selected_subset_of_scans"
REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / ".claude" / "skills" / "isaac-historical-import"


# --- HIGH: one file per scan ---------------------------------------------------------------------------------------


def _pair(inputs, chosen):
    isa = {"group_id": "g1", "source": "isaac_protocol", "run_id": "r-1", "inputs": inputs}
    ath = {"group_id": "g1", "source": "scientist_athena", "run_id": "r-1",
           "comparison": {"flags": [SUBSET], "athena_scan_selection": chosen}}
    return {"processing_results": [isa, ath]}, ath


def test_one_file_per_scan_inputs_are_numbered_in_order_and_a_subset_is_only_part_of_the_merge():
    bundle, ath = _pair([{"scan": None, "relative_path": f"SYN_dir/SYN_{n:03d}.txt"} for n in range(1, 9)],
                        [1, 3, 4, 5, 6, 8])
    note = M.scan_subset_note(bundle, ath)
    assert "did not merge" not in note and "different set" not in note
    assert note.startswith("The scientist's Athena curve for group g1 uses only scans 1, 3, 4, 5, 6, 8 of the 8 scan(s) "
                           "ISAAC merged")
    # the numbering is said, never hidden
    assert "the run states no scan index; its 8 scans are numbered 1-8 in the order listed" in note


def test_one_file_per_scan_a_skipped_scan_is_known_and_said_not_merged():
    inputs = [{"scan": None}, {"scan": None, "skip_reason": "too_few_points"}, {"scan": None}]
    bundle, ath = _pair(inputs, [1, 2])
    note = M.scan_subset_note(bundle, ath)
    assert "uses a different set of scans (1, 2) from the 2 scan(s) ISAAC merged, including scan(s) 2 that ISAAC did " \
           "not merge" in note
    assert "numbered 1-3 in the order listed" in note


def test_a_label_number_the_run_does_not_list_is_said_to_be_one_never_not_merged():
    bundle, ath = _pair([{"scan": None} for _ in range(9)], [2468])
    note = M.scan_subset_note(bundle, ath)
    assert "did not merge" not in note
    assert "names scan(s) 2468, which the run's 9 listed scans do not include" in note


def test_scans_without_known_numbers_never_claim_a_scan_was_not_merged():
    # some inputs state an index and some do not: the numbers are not known
    bundle, ath = _pair([{"scan": 1}, {"scan": None}, {"scan": None}], [1, 3])
    note = M.scan_subset_note(bundle, ath)
    assert "did not merge" not in note and "different set" not in note
    assert "uses scans 1, 3 of the 3 scan(s) ISAAC merged" in note


def test_stated_scan_indexes_are_unchanged():
    # NEGATIVE CONTROL (the c10-r sentences): a stated index is used as stated
    bundle, ath = _pair([{"scan": 1}, {"scan": 2}, {"scan": 3, "skip_reason": "too_few_points"}], [1, 2, 3])
    assert M.scan_subset_note(bundle, ath).startswith(
        "The scientist's Athena curve for group g1 uses a different set of scans (1, 2, 3) from the 2 scan(s) ISAAC "
        "merged, including scan(s) 3 that ISAAC did not merge")
    bundle, ath = _pair([{"scan": 1}, {"scan": 2}], [1])
    note = M.scan_subset_note(bundle, ath)
    assert "uses only scans 1 of the 2 scan(s) ISAAC merged" in note and "numbered" not in note


def _processing():
    pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")


def _label_case(tmp_path, label, *, scans=3, per_file=True, zero=()):
    """ONE run ``01_SYN_ZZ1`` of ``scans`` scans (``per_file``: the scans state no index, as one file per scan does)
    and an Athena project with one group ``label``. Scans in ``zero`` have a signal of zero at every point."""
    from test_local_import_polish_c10m import _prj
    from test_local_import_processing import GRID, fluo_scan, make_case, mu_edge, spec_file

    tmp_path.mkdir(parents=True, exist_ok=True)
    texts = []
    for s in range(1, scans + 1):
        cols = fluo_scan(s)
        if s in zero:
            cols["vortDT"] = cols["vortDT"] * 0.0
        texts.append(spec_file(cols))
    bdir, root, bundle = make_case(tmp_path, [("01_SYN_ZZ1", texts, {"sample_name": "ZZ1"})])
    if per_file:
        for sc in bundle["runs"][0]["scans"]:
            sc["scan_index"] = None
    if label:
        _prj(root / "SYN.prj", [(label, GRID, mu_edge(GRID) * 1e-2)])
        bundle["unread_files"].append({"source_id": "prj-SYN", "relative_path": "SYN.prj"})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


def _process(bdir, root):
    from test_local_import_polish_c10m import _process as run

    return run(bdir, root)


@pytest.mark.parametrize("per_file", [True, False], ids=["one-file-per-scan", "stated-index"])
def test_processing_numbers_the_scans_the_same_in_both_layouts(tmp_path, per_file):
    _processing()
    bdir, root = _label_case(tmp_path / "part", "01_SYN_ZZ1_1-2", per_file=per_file)
    _, isa, ath = _process(bdir, root)
    assert isa["inputs"][0]["scan"] == (None if per_file else 1)  # what the bundle states is kept as stated
    assert SUBSET in isa["comparison"]["flags"] and isa["comparison"]["athena_scan_selection"] == [1, 2]
    said = ath["qc"]["statements"]["scans_used"]
    assert "It covers only scans 1-2 of the 3 scans ISAAC merged" in said and "did not merge" not in said
    # the diagnostic on the same scans is computed in both layouts
    assert isa["comparison"]["metrics"].get("rms_norm_same_scans_same_params") is not None
    note = M.scan_subset_note({"processing_results": [isa, ath]}, ath)
    assert "uses only scans 1, 2 of the 3 scan(s) ISAAC merged" in note and "did not merge" not in note
    assert ("numbered 1-3 in the order listed" in note) is per_file
    # a label naming every scan is not a subset in either layout (before: always one for one file per scan)
    bdir, root = _label_case(tmp_path / "all", "01_SYN_ZZ1_1-3", per_file=per_file)
    _, isa, ath = _process(bdir, root)
    assert SUBSET not in isa["comparison"]["flags"]
    assert M.scan_subset_note({"processing_results": [isa, ath]}, ath) is None


def test_processing_says_a_label_scan_the_run_does_not_list(tmp_path):
    _processing()
    bdir, root = _label_case(tmp_path, "01_SYN_ZZ1_2468")
    _, isa, ath = _process(bdir, root)
    said = ath["qc"]["statements"]["scans_used"]
    assert "did not merge" not in said
    assert "It names scan 2468, which the run's 3 listed scans do not include" in said


# --- MED-3: a scan whose signal is zero at every point ------------------------------------------------------------


def test_an_all_zero_scan_is_skipped_named_and_the_rest_merged(tmp_path):
    _processing()
    bdir, root = _label_case(tmp_path, None, scans=3, zero=(3,))
    _, isa, _ = _process(bdir, root)
    assert [i.get("skip_reason") for i in isa["inputs"]] == [None, None, "signal_all_zero"]
    m = isa["qc"]["metrics"]
    assert m["scans_used"] == 2 and m["scans_skipped_signal_all_zero"] == 1 and m["signal_all_zero_scans"] == 0
    assert "signal_all_zero" not in isa["qc"]["reasons"] and "scans_skipped_signal_all_zero" in isa["qc"]["reasons"]
    assert isa["qc"]["verdict"] == "warn"
    said = isa["qc"]["statements"]["scans_skipped_signal_all_zero"]
    assert said.startswith("2 of 3 listed scans were used. 1 was left out because its signal (vortDT) is zero at every "
                           "point: 01_SYN_ZZ1_003.dat")
    assert "the curve merges the other 2" in said
    assert cli._scans_line(isa) == "2 of 3 scans used; 1 skipped (signal_all_zero)"
    merged = (bdir / next(f["relative_path"] for f in isa["outputs"]["files"] if f["role"] == "merged")).read_text()
    rows = [line for line in merged.splitlines() if line and not line.startswith("#")][1:]
    assert rows and {line.split(",")[-1] for line in rows} == {"2"}  # every point averages the 2 live scans
    # the sentence is in qc.json (hashed into the result id): only a group with such a scan has a new id


def test_a_group_without_an_all_zero_scan_has_no_new_key(tmp_path):
    _processing()
    bdir, root = _label_case(tmp_path, None, scans=2)
    _, isa, _ = _process(bdir, root)
    assert "scans_skipped_signal_all_zero" not in isa["qc"]["metrics"]
    assert "scans_skipped_signal_all_zero" not in (isa["qc"].get("statements") or {})


def test_every_scan_all_zero_has_no_curve_and_cannot_be_approved(tmp_path):
    _processing()
    from isaac_api.local_import.processing import run as RUN

    bdir, root = _label_case(tmp_path, None, scans=2, zero=(1, 2))
    _, isa, _ = _process(bdir, root)
    # no scan carries a live signal, so no channel forms: a failure with no curve, as before
    assert isa["failure"]["code"] == "signal_channel_dead" and not (isa.get("outputs") or {}).get("files")
    # the existing no-curve refusal applies (decide refuses an approval of a result with no output file)
    assert "has no curve to approve" in M.no_curve_refusal(isa)
    # when a channel did form and every scan's signal is zero, the sentence says so in words
    inputs = [{"skip_reason": "signal_all_zero"}, {"skip_reason": "signal_all_zero"}]
    assert RUN._no_usable_scan_statement(inputs, [], signal="vortDT") == (
        "No scan could be used: the signal (vortDT) is zero at every point in both scans, so there is no curve to "
        "process.")
    assert RUN._no_usable_scan_statement(inputs[:1], [], signal="vortDT") == (
        "The only scan's signal (vortDT) is zero at every point, so there is no curve to process.")


def test_the_processing_reference_says_signal_all_zero():
    text = (SKILL / "reference" / "grouping-and-processing.md").read_text()
    assert "`signal_all_zero`" in text and "the curve uses the other scans" in text


# --- MED-2: warnings are never invisible --------------------------------------------------------------------------


def _w(gid, n):
    return {"group_id": gid, "code": "stated_potential_not_in_record", "text": f"{gid} warning {n}", "command": "c",
            "path": "context.electrochemistry.potential_setpoint_V", "needs": "context.electrochemistry.potential_setpoint_V"}


def test_the_warnings_of_exportable_groups_come_first_and_full_prints_them_all():
    warned = [_w(f"g{i}", i) for i in range(8)]
    shown = R.warning_summary(warned, first={"g7"})
    assert shown["warnings"][0]["group_id"] == "g7" and len(shown["warnings"]) == R.WARNINGS_SHOWN
    assert shown["warnings_total"] == 8 and shown["warnings_omitted"] == 3
    assert "--full" in shown["warnings_full_list"]
    full = R.warning_summary(warned, first={"g7"}, full=True)
    assert len(full["warnings"]) == 8 and "warnings_omitted" not in full
    assert [w["group_id"] for w in full["warnings"]] == ["g7", "g0", "g1", "g2", "g3", "g4", "g5", "g6"]


def test_the_written_without_line_names_the_condition():
    line = R.written_without(_w("g1", 1))
    assert line.startswith("Written without the potential set-point: ") and line.endswith("g1 warning 1")


from test_local_import_records import BY, _cand, _decide_everything, _portal, bdir, pristine  # noqa: E402,F401  (fixtures)


def test_export_lists_per_record_written_the_warnings_that_still_apply(bdir, tmp_path):
    # the synthetic corpus' file names state a potential (100mV) and no potential scale is confirmed: g1 exports
    # with that warning still applying
    _decide_everything(bdir)
    R.build_records(bdir)
    out = R.export_records(bdir, tmp_path / "out", run_portal=_portal("publish"))
    [row] = out["exported"]
    [line] = row["warnings"]
    assert line.startswith("Written without the potential set-point: ") and "100mV" in line
    assert out["records_written_with_warnings"] == 1
    assert "1 record(s) were written with a warning that still applies" in out["outcome"]


def test_validate_lists_an_exportable_groups_warning_and_full_prints_all(bdir, monkeypatch, capsys):
    from isaac_api.local_import import portal as P

    _decide_everything(bdir)
    monkeypatch.setattr(P, "run_portal_check", _portal("publish"))
    built = R.build_records(bdir, full=True)
    assert built["warnings"][0]["group_id"] == "g1" and built["warnings"][0]["draft_complete"] is True
    assert built["warnings_total"] == len(built["warnings"])
    assert json.loads((bdir / "drafts" / "index.json").read_text())["warnings_total"] == built["warnings_total"]
    v = R.validate_records(bdir)
    assert v["verdicts"]["g1"] == "exportable"
    assert v["warnings"][0]["group_id"] == "g1" and v["warnings"][0]["group_exportable"] is True
    assert cli.main(["bundle", "validate", str(bdir), "--full"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["warnings_total"] == len(printed["warnings"])


# --- LOW-4: a UTC instant against a reading with no time zone -----------------------------------------------------


def test_reveal_of_a_utc_value_against_a_zone_less_reading_is_not_comparable(bdir):
    b = M.load(bdir)
    c = _cand(b, "timestamps.acquired_start_utc", "run-001")
    assert c["value"].endswith("+00:00")
    naive = c["value"][: -len("+00:00")]
    M.annotate(bdir, target_id=c["candidate_id"], value=naive, excerpt_locator="line 2",
               source_id=c["evidence"][0]["source_id"], model_id="m", blind=True, rationale="")
    M.annotate(bdir, target_id=c["candidate_id"], value=c["value"][: -len("+00:00")] + "Z", excerpt_locator="line 2",
               source_id=c["evidence"][0]["source_id"], model_id="m", blind=True, rationale="")
    zone_less, zoned = M.reveal(bdir, c["candidate_id"])["ai_readings"]
    assert zone_less["agrees_with_parser"] is None and zone_less["relation"] is None
    assert zone_less["compared_as"] == "instant"
    assert "the reading names no time zone; the file's value is UTC" in zone_less["comparison_note"]
    # NEGATIVE CONTROL: the same instant with its zone still agrees
    assert zoned["agrees_with_parser"] is True and "compared_as" not in zoned


def test_the_blind_crosscheck_reference_says_what_to_write_for_an_epoch_target():
    text = (SKILL / "reference" / "blind-crosscheck.md").read_text()
    assert "`#E`" in text and "the UTC instant" in text and "local time with its zone" in text
