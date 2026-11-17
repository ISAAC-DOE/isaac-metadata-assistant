"""``bundle show processing-result`` and ``bundle list processing-results`` say the scan-selection proposal and the
comparison with the scientists' quick merges, and the review plot marks the proposed scans by their real scan number.

Measured gap this pins (a demo dry run on a real BL15-2 beamtime): ``show processing-result`` printed neither block, and
the skill may not open ``processing/processing_results.json``, so the scientist could not be told how their own quick
merge compared; the plot named scans by position ("scan 1..9" for scans 1, 3..10) and did not mark the proposals.
SYNTHETIC values and SYN names only.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import cli

FILE = "SYN_ZZ9_{:03d}.dat"


def _row(n, proposal, reasons=(), said=(), metrics=None):
    return {"file": FILE.format(n), "relative_path": f"SYN_ZZ9_dir/{FILE.format(n)}", "source_id": f"src-{n:03d}",
            "scan": n, "exclude_as": FILE.format(n), "proposal": proposal, "reasons": list(reasons), "said": list(said),
            "metrics": metrics if metrics is not None else {"edge_snr": 10.0 + n, "chi2_nu_shifted": 1.0}}


def _result(n_scans=10, *, extra_rows=None, quick=True):
    """An ISAAC result over SYN scans 1..n, scan 2 an aborted fragment, scans 1, 3, 4 proposed for leaving out."""
    rows = [_row(1, "exclude_proposed", ["before_stable_window"], ["the sample was still changing (SYN)"]),
            _row(2, "left_out", ["aborted_scan_fragment"], ["not in this merge"]),
            _row(3, "exclude_proposed", ["before_stable_window"], ["the sample was still changing (SYN)"]),
            _row(4, "exclude_proposed", ["before_stable_window"], ["the sample was still changing (SYN)"]),
            _row(5, "include"),
            _row(6, "include", ["differs_below_merge_noise"], ["shape differs but would move the merge only 0.5 x"])]
    rows += [_row(n, "include") for n in range(7, n_scans + 1)]
    rows += extra_rows or []
    inputs = [{"source_id": x["source_id"], "relative_path": x["relative_path"], "scan": x["scan"],
               "used": x["proposal"] != "left_out", **({"skip_reason": "aborted_scan_fragment"} if x["proposal"] == "left_out" else {})}
              for x in rows]
    r = {"result_id": "proc-rg-syn-r-0000000000000001-isaac", "group_id": "rg-syn", "source": "isaac_protocol",
         "state": "proposed", "qc": {"verdict": "warn", "reasons": [], "metrics": {"scans_listed": len(rows), "scans_used": len(rows) - 1},
                                     "statements": {"scan_selection": "Scan selection (SYN sentence)."}},
         "review_flags": ["scan_selection_proposed"], "inputs": inputs, "steps": [], "outputs": {"files": []},
         "scan_selection": {
             "rule_id": "isaac.xas.scan_selection_proposal.v0", "status": "evaluated", "open": True,
             "constants": {"SEL_SYN": 1}, "e0_series_eV": 4966.0, "e0_basis": "series",
             "series_id": "gscan energy 4900-5250 eV", "scans": rows,
             "trend": {"wl_e_eV": {"n": 9, "p": 0.01}}, "change_point": {"wl_e_eV": {"leading_scans": 3}},
             "evolving_metrics": ["wl_e_eV"], "stable_window": [FILE.format(n) for n in range(5, n_scans + 1)],
             "edge_step_change": {"first": 1.0, "last": 1.6, "relative": 0.6},
             "group_observations": ["edge step grew 60% from scan 1 to scan 10 (SYN). Not a reason to leave a scan out: the merge is raw mu."],
             "merge_snr": {"proposed": 29.0, "all_complete": 35.0},
             "exclude_proposed": [FILE.format(n) for n in (1, 3, 4)], "needs_look": [], "already_excluded": []},
    }
    if quick:
        r["scientist_quick_merges"] = [{
            "rule_id": "isaac.processed_output.quick_merge_compare.v0", "processed_output_id": "po-syn",
            "relative_path": "MERGE/SYN_ZZ9.txt", "source_id": "src-900",
            "matched_by": {"rule_id": "isaac.processed_output.link_by_legacy_number.v0", "run_id": "run-001",
                           "run_key": "SYN@sha256:00", "status": "proposed"},
            "role": "rough_reference", "preferred_for_record": False, "treated_as_truth": False,
            "assumptions": ["column 1 is read as energy in eV (SYN)", "column 2 is read as the merged signal (mu)"],
            "verdict": "differs", "normalization": "normalized_with_isaac_parameters",
            "metrics": {"rms_norm": 0.08, "e0_delta_eV": 0.2, "e0_isaac_eV": 4966.0, "e0_found_in_it_eV": 4965.8,
                        "edge_step_isaac": 1.6, "edge_step_scientist": 1.8, "overlap_points": 200, "points": 201,
                        "pre_edge_mean": 0.01, "energy_eV": [4900.0, 5250.0]},
            "raw_comparison": {"median_ratio_to_isaac_merged_mu": 1.1, "relative_rms_residual": 0.015, "statement": "SYN"},
            "tolerances": {"agree_rms_norm": 0.05, "agree_e0_delta_eV": 1.0},
            "scan_subset_hint": {"tried": True, "subsets_tried": 511, "subsets_that_rebuild": 1, "applied": False,
                                 "scans_not_in_it": [FILE.format(n) for n in (1, 3, 4)], "statement": "HINT ONLY, never applied (SYN)"},
            "statement": "A rough reference: the scientists' quick merge at the beamline (SYN).",
        }]
    return r


def _view(r, **kw):
    return cli._processing_result_view({"record_groups": []}, r, **kw)


def _lists(o):
    if isinstance(o, dict):
        return [x for v in o.values() for x in _lists(v)]
    if isinstance(o, list):
        return [o] + [x for v in o for x in _lists(v)]
    return []


def test_show_says_the_scan_selection_by_real_scan_number_with_reasons_and_sentences():
    sel = _view(_result())["scan_selection"]
    assert sel["status"] == "evaluated" and sel["open"] is True and sel["applied"] is False
    assert sel["stable_window"] == "scans 5-10"
    assert sel["observations"][0].startswith("edge step grew 60%")
    assert sel["counts"] == {"exclude_proposed": 3, "left_out": 1, "include": 6}
    assert sel["included_without_remark"] == "scans 5,7-10"  # plain includes are one line, never a row each
    by = {x["scan"]: x for x in sel["scans"]}
    assert sorted(by) == [1, 2, 3, 4, 6]  # every scan with a remark, by its real number
    assert by[1]["proposal"] == "exclude_proposed" and by[1]["reasons"] == ["before_stable_window"]
    assert by[1]["said"] == "the sample was still changing (SYN)" and by[1]["exclude_as"] == FILE.format(1)
    assert by[2]["proposal"] == "left_out" and "exclude_as" not in by[2]
    assert by[6]["reasons"] == ["differs_below_merge_noise"]
    # metrics stay out by default
    assert all("metrics" not in x for x in sel["scans"]) and "merge_snr" not in sel and "trend" not in sel


def test_show_full_adds_every_row_and_the_metrics():
    sel = _view(_result(), full=True)["scan_selection"]
    assert [x["scan"] for x in sel["scans"]] == list(range(1, 11)) and "included_without_remark" not in sel
    assert sel["scans"][0]["metrics"]["edge_snr"] == 11.0 and sel["merge_snr"]["proposed"] == 29.0
    assert sel["edge_step_change"]["relative"] == 0.6


def test_show_bounds_the_rows_and_says_what_it_left_out():
    extra = [_row(n, "needs_look", ["excess_noise"], ["over 2 x counting noise"]) for n in range(11, 41)]
    view = _view(_result(extra_rows=extra))
    sel = view["scan_selection"]
    assert len(sel["scans"]) == cli.SELECTION_ROWS_SHOWN
    assert {1, 3, 4} <= {x["scan"] for x in sel["scans"]}  # the proposals for leaving out come first
    assert sel["scans_not_shown"] == 35 - cli.SELECTION_ROWS_SHOWN and "--full" in sel["scans_not_shown_note"]
    assert all(len(lst) <= 20 for lst in _lists(view))  # no raw arrays, as for the rest of the view


def test_show_says_the_quick_merge_as_a_rough_reference_with_its_key_metrics():
    [q] = _view(_result())["scientist_quick_merges"]
    assert q["file"] == "MERGE/SYN_ZZ9.txt" and q["verdict"] == "differs" and q["role"] == "rough_reference"
    assert q["preferred_for_record"] is False and q["treated_as_truth"] is False
    assert q["matched_by"] == {"rule_id": "isaac.processed_output.link_by_legacy_number.v0", "run_id": "run-001",
                               "status": "proposed"}
    assert q["assumptions"][0].startswith("column 1 is read as energy")
    assert q["metrics"]["rms_norm"] == 0.08 and q["metrics"]["e0_delta_eV"] == 0.2
    assert "pre_edge_mean" not in q["metrics"] and "energy_eV" not in q["metrics"]  # key metrics only
    assert q["raw_comparison"] == {"median_ratio_to_isaac_merged_mu": 1.1, "relative_rms_residual": 0.015}
    assert q["scan_subset_hint"]["scans_not_in_it"] == "scans 1,3-4" and q["scan_subset_hint"]["applied"] is False
    assert "rough reference" in q["statement"]
    full = _view(_result(), full=True)["scientist_quick_merges"][0]
    assert full["metrics"]["pre_edge_mean"] == 0.01


def test_a_result_with_neither_block_prints_neither():
    r = _result(quick=False)
    del r["scan_selection"]
    view = _view(r)
    assert "scan_selection" not in view and "scientist_quick_merges" not in view
    row = cli._row("processing-results", r)
    assert "scan_selection" not in row and "quick_merge_agreement" not in row


def test_a_not_evaluated_proposal_says_its_detail_and_proposes_nothing():
    r = _result(quick=False)
    r["scan_selection"] = {"rule_id": "isaac.xas.scan_selection_proposal.v0", "status": "not_evaluated",
                           "detail": "the series pass failed (SYN)", "open": False, "scans": [],
                           "exclude_proposed": [], "needs_look": []}
    sel = _view(r)["scan_selection"]
    assert sel["status"] == "not_evaluated" and sel["detail"] == "the series pass failed (SYN)" and sel["scans"] == []
    assert cli._row("processing-results", r)["scan_selection"] == "not evaluated (nothing proposed)"


def test_the_list_row_says_both_in_a_few_words():
    row = cli._row("processing-results", _result())
    assert row["scan_selection"] == "proposes leaving out 3 of 9 merged scans (scans 1,3-4); not applied"
    assert row["quick_merge_agreement"] == "differs (rough reference)"
    r = _result(quick=False)
    for x in r["scan_selection"]["scans"]:
        if x["proposal"] == "exclude_proposed":
            x["proposal"], x["reasons"] = "include", []
    assert cli._row("processing-results", r)["scan_selection"] == "nothing proposed (9 merged scans judged)"


def test_scans_whose_numbers_repeat_are_named_by_file():
    r = _result(quick=False)
    for x, i in zip(r["scan_selection"]["scans"], r["inputs"]):
        x["scan"] = i["scan"] = 1  # several runs, each restarting its numbering
    assert FILE.format(3) in cli._row("processing-results", r)["scan_selection"]


def test_the_quick_merge_key_is_the_processing_modules():
    from isaac_api.local_import.processing import quick_merge as QM

    assert QM.RESULT_KEY == "scientist_quick_merges"


# --- the review plot: real scan numbers, proposals marked, ids unmoved ---------------------------------------------


def test_the_legend_marks_a_proposal_and_a_flag():
    from isaac_api.local_import.processing import plot as PL

    label, style = PL.scan_style(0, label="scan 1", proposal="exclude_proposed", flagged=False)
    assert label == "scan 1 (proposed: leave out)" and style["ls"] == "--"
    label, style = PL.scan_style(1, label="scan 3", proposal="needs_look", flagged=True)
    assert label == "scan 3 (proposed: look at) (flagged)" and style["ls"] == "-."
    label, style = PL.scan_style(2, label="scan 5", proposal="include", flagged=False)
    assert label == "scan 5" and "ls" not in style
    assert PL.scan_style(3, label=None, proposal=None, flagged=False)[0] == "scan position 4"


def _proc_case(tmp_path):
    pytest.importorskip("numpy", reason="needs the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="needs the optional `processing` extra (xraylarch)")
    pytest.importorskip("scipy", reason="scan selection needs scipy (a dependency of xraylarch)")
    import test_local_import_scan_selection as S

    short = {k: v[:10] for k, v in S.counts(250).items()}  # scan 2: too few points, never merged
    aborted = {k: v[:25] for k, v in S.counts(209).items()}  # scan 6: merged, stops below the edge
    scans = [S.spec(S.counts(200)), S.spec(short)] + [S.spec(S.counts(201 + k)) for k in range(3)] + [S.spec(aborted)]
    return S._case(tmp_path, [("01_SYN_ZZ1", scans)])


def _isaac(payload):
    return next(r for r in payload["processing_results"] if r["source"] == "isaac_protocol")


def test_the_plot_names_scans_by_real_number_and_marks_the_proposal(tmp_path, monkeypatch):
    bdir, root, _ = _proc_case(tmp_path)
    from isaac_api.local_import.processing import plot as PL
    from test_local_import_processing import run_process

    seen = []
    real = PL.review_plot
    monkeypatch.setattr(PL, "review_plot", lambda path, **kw: seen.append(kw) or real(path, **kw))
    r = _isaac(run_process(bdir, source_root=root))
    [kw] = seen
    assert [i.get("skip_reason") for i in r["inputs"]][1] == "aborted_scan_fragment"  # never merged
    assert kw["scan_labels"] == ["scan 1", "scan 3", "scan 4", "scan 5", "scan 6"]  # never "scan 1..5"
    assert kw["scan_proposals"][-1] == "exclude_proposed" and kw["scan_proposals"][0] == "include"
    assert kw["merge_note"] == "The merge is raw mu of all 5 scans used; scan-selection proposals are NOT applied."
    assert any(f["role"] == "plot" for f in r["outputs"]["files"])


def test_marking_the_plot_moves_no_id_and_no_merged_byte(tmp_path, monkeypatch):
    from isaac_api.local_import.processing import run as RUN
    from test_local_import_processing import run_process

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    b_on, root_on, _ = _proc_case(tmp_path / "a")
    b_off, root_off, _ = _proc_case(tmp_path / "b")
    on = _isaac(run_process(b_on, source_root=root_on))
    monkeypatch.setattr(RUN, "_plot_scan_marks", lambda *a, **k: {})  # the plot as it was drawn before
    off = _isaac(run_process(b_off, source_root=root_off))
    assert on["run_id"] == off["run_id"] and on["result_id"] == off["result_id"]
    f_on = {f["role"]: f for f in on["outputs"]["files"]}
    f_off = {f["role"]: f for f in off["outputs"]["files"]}
    for role in ("merged", "normalized", "qc", "params"):
        assert (b_on / f_on[role]["relative_path"]).read_bytes() == (b_off / f_off[role]["relative_path"]).read_bytes()
    assert f_on["plot"]["sha256"] != f_off["plot"]["sha256"]  # the plot changed; it is not hashed into any id


def test_marks_that_fail_never_lose_the_plot(monkeypatch):
    from isaac_api.local_import.processing import run as RUN

    def boom(*a, **k):
        raise RuntimeError("SYN")

    monkeypatch.setattr(RUN, "_plot_scan_marks_unguarded", boom)
    assert RUN._plot_scan_marks([], [], [], None, excl=False, flagged=False) == {}


def test_show_on_a_processed_bundle_prints_both_lines(tmp_path, capsys):
    pytest.importorskip("numpy", reason="needs the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="needs the optional `processing` extra (xraylarch)")
    pytest.importorskip("scipy", reason="scan selection needs scipy (a dependency of xraylarch)")
    import test_local_import_scan_selection as S
    from isaac_api.local_import import mutations as M

    bdir = S._imported(tmp_path)
    capsys.readouterr()
    r = next(x for x in M.load(bdir)["processing_results"]
             if x["source"] == "isaac_protocol" and x["inputs"][0]["relative_path"] == "01_SYN_ZZ1")
    assert cli.main(["bundle", "show", str(bdir), "processing-result", M.B.processing_id(r)]) == 0
    sel = json.loads(capsys.readouterr().out)["scan_selection"]
    [row] = [x for x in sel["scans"] if x["proposal"] == "exclude_proposed"]
    assert row["scan"] == 5 and row["reasons"] == ["incomplete_scan"] and row["exclude_as"] == "01_SYN_ZZ1#5"
    assert cli.main(["bundle", "list", str(bdir), "processing-results", "--limit", "50"]) == 0
    rows = {x["result_id"]: x for x in json.loads(capsys.readouterr().out)["items"]}
    assert rows[M.B.processing_id(r)]["scan_selection"].startswith("proposes leaving out 1 of 5 merged scans (scan 5)")
