"""Polish r3-b: a real-data run on an SSRL BL4-3 Ti K-edge beamtime (four Athena projects, Ti foils), reproduced here.
SYNTHETIC only: every scan, name, Athena project and value below is invented and named ``SYN_``.

* (H3) The scientist's own Athena merge named BEFORE the run name (``merge4_<base>``, ``merge_<base>``: the group's run
  name, or its shared base name without the run counter) is matched and preferred over the per-scan groups beside it,
  so ISAAC never averages those and never says the scientist made no merge. Per-scan groups of EVERY run of a merged
  group form one set (told apart by run and scan). When ISAAC averages, the Athena result's steps say so (a merge
  step: a record lists ``spectrum_merging``).
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import records as R


def _processing():
    pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")


def _case(tmp_path, stems, athena_groups, *, scans=2):
    """ONE group of the runs ``stems`` (``scans`` scans each) and a project ``SYN.prj`` of ``athena_groups``
    (label, mu factor)."""
    _processing()
    from test_local_import_processing import GRID, _athena_prj, fluo_scan, make_case, mu_edge, spec_file

    runs = [(s, [spec_file(fluo_scan(10 * i + j)) for j in range(1, scans + 1)], {"sample_name": "ZZ1"})
            for i, s in enumerate(stems)]
    bdir, root, bundle = make_case(tmp_path, runs)
    if len(stems) > 1:
        bundle["record_groups"] = [{"group_id": "g-merged", "experiment_key": "e", "role": "sample",
                                    "member_run_keys": [r["run_key"] for r in bundle["runs"]],
                                    "basis": {"sample": {}, "technique": {}, "environment": {}, "conditions": {}},
                                    "split_reasons": [], "status": B.STATE_SCIENTIST_CONFIRMED, "questions": []}]
    _athena_prj(root / "SYN.prj", [(label, GRID, mu_edge(GRID) * k) for label, k in athena_groups])
    bundle["unread_files"].append({"source_id": "prj-SYN", "relative_path": "SYN.prj"})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


def _process(bdir, root, **kw):
    from isaac_api.local_import.processing.cli_entry import run_process

    out = run_process(bdir, source_root=root, **kw)
    isa = [r for r in out["processing_results"] if r["source"] == "isaac_protocol"]
    ath = [r for r in out["processing_results"] if r["source"] == "scientist_athena"]
    return out, isa, ath


def _record_steps(result) -> list[str]:
    """What a record lists as ``measurement.processing.steps`` for this result (records.py's own rule)."""
    out = []
    for step in result.get("steps") or ():
        token = R.PROCESSING_STEP_VOCABULARY.get(step.get("step"))
        if token and token not in out and R.step_was_applied(step):
            out.append(token)
    return out


# --- H3: the scientist's own Athena merge ------------------------------------------------------------------------


ONE_RUN = "01_SYN_TiON_dry_016"
PER_SCAN = [(f"{ONE_RUN}_A.001", 1.0e-2), (f"{ONE_RUN}_A.002", 1.01e-2), (f"{ONE_RUN}_A.003", 1.02e-2)]


@pytest.mark.parametrize("merge_label", ["merge3_01_SYN_TiON_dry", "merge_01_SYN_TiON_dry", f"merge_{ONE_RUN}"])
def test_a_merge_named_before_the_base_name_is_the_scientists_merge_and_is_preferred(tmp_path, merge_label):
    bdir, root = _case(tmp_path, [ONE_RUN], PER_SCAN + [(merge_label, 1.005e-2)], scans=3)
    out, [isa], [ath] = _process(bdir, root)
    [inp] = ath["inputs"]
    assert inp["athena_group"] != "" and inp["scan"] == merge_label and inp["match_kind"] == "scientist_merge"
    assert "per_scan_set" not in inp and inp["scans_basis"] == "not_stated"
    assert "isaac_computed_mean_of_scientist_per_scan_curves" not in ath["review_flags"]
    assert "isaac_did_not_change_scientist_values" in ath["review_flags"]
    assert isa["comparison"]["athena_ref"]["match_kind"] == "scientist_merge"
    assert isa["comparison"]["athena_ref"]["merge_rule"] == "isaac.athena.scientist_merge_label.v0"
    said = ath["qc"]["statements"]["scans_used"]
    assert f"its label names it the scientist's merge of run {ONE_RUN}" in said
    # the scientist merged: the record lists the merge, never "ISAAC averaged"
    assert _record_steps(ath) == ["normalization", "spectrum_merging"]
    assert ath["preferred_for_record"] is True and "athena_versions" not in isa


def test_without_a_merge_the_per_scan_set_is_averaged_and_its_steps_say_so(tmp_path):
    bdir, root = _case(tmp_path, [ONE_RUN], PER_SCAN, scans=3)
    _, [isa], [ath] = _process(bdir, root)
    assert ath["inputs"][0]["match_kind"] == "per_scan_set"
    merge = next(s for s in ath["steps"] if s["step"] == "merge")
    assert merge["params"]["made_by"] == "ISAAC" and merge["outcome"]["n_scans"] == 3
    assert _record_steps(ath) == ["normalization", "spectrum_merging"]


def test_a_merge_label_naming_another_sample_is_not_matched(tmp_path):
    bdir, root = _case(tmp_path, [ONE_RUN], PER_SCAN + [("merge_01_SYN_TiON_wet", 1.005e-2)], scans=3)
    _, _, [ath] = _process(bdir, root)
    assert ath["inputs"][0]["match_kind"] == "per_scan_set"  # the other sample's merge stays unmatched


TWO_RUNS = ("11_SYN_ZZ1_dry_091", "11_SYN_ZZ1_dry_092")
BOTH_RUNS = [(f"{s}_A.{n:03d}", 1e-2 + 1e-4 * (2 * i + n)) for i, s in enumerate(TWO_RUNS) for n in (1, 2)]


def test_a_two_run_groups_merge_named_after_its_base_name_covers_both_runs(tmp_path):
    bdir, root = _case(tmp_path, TWO_RUNS, BOTH_RUNS + [("merge_11_SYN_ZZ1_dry", 1.003e-2)])
    _, [isa], [ath] = _process(bdir, root)
    assert ath["inputs"][0]["scan"] == "merge_11_SYN_ZZ1_dry" and ath["inputs"][0]["match_kind"] == "scientist_merge"
    cov = ath["comparison"]["athena_covers"]
    assert cov["runs"] == list(TWO_RUNS) and cov["group_runs"] == list(TWO_RUNS)
    assert "scientist_selected_subset_of_scans" not in ath["comparison"]["flags"]
    assert ath["preferred_for_record"] is True and "athena_versions" not in isa


def test_a_two_run_merge_named_after_one_run_covers_only_that_run(tmp_path):
    bdir, root = _case(tmp_path, TWO_RUNS, BOTH_RUNS + [(f"merge_{TWO_RUNS[0]}", 1.003e-2)])
    _, _, [ath] = _process(bdir, root)
    assert ath["comparison"]["athena_covers"]["runs"] == [TWO_RUNS[0]]
    assert ath["preferred_for_record"] is False  # a curve of one of the two runs does not describe the group


def test_per_scan_groups_of_every_run_of_a_two_run_group_form_one_set(tmp_path):
    bdir, root = _case(tmp_path, TWO_RUNS, BOTH_RUNS)
    _, [isa], [ath] = _process(bdir, root)
    [inp] = ath["inputs"]
    assert inp["match_kind"] == "per_scan_set" and "athena_versions" not in isa
    assert inp["per_scan_set"]["runs"] == [TWO_RUNS[0], TWO_RUNS[0], TWO_RUNS[1], TWO_RUNS[1]]
    assert inp["per_scan_set"]["scans"] == [1, 2, 1, 2]
    said = ath["qc"]["statements"]["scans_used"]
    assert f"one each for scans 1-2 of run {TWO_RUNS[0]} and scans 1-2 of run {TWO_RUNS[1]}" in said
    assert ath["comparison"]["athena_covers"]["runs"] == list(TWO_RUNS)
    assert ath["preferred_for_record"] is True
    assert _record_steps(ath) == ["normalization", "spectrum_merging"]


def test_base_names_drop_only_a_counter():
    from isaac_api.local_import.processing import athena as A

    assert A.base_names(["11_x_dry_091", "11_x_dry_092"]) == {"11_x_dry"}
    assert A.base_names(["01_SYN_ZZ1", "02_SYN_ZZ1"]) == {"syn_zz1"}
    assert A.base_names(["22_x_dry_016"]) == {"22_x_dry"} and A.base_names(["22_x_dry_016_A"]) == {"22_x_dry"}
    assert A.base_names(["22_x_dry"]) == {"22_x_dry"}
    # runs that differ in a word, not a number, share no base name
    assert A.base_names(["11_x_dry_091", "11_x_wet_092"]) == set()
