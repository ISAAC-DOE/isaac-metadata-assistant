"""Polish r3-b: a real-data run on an SSRL BL4-3 Ti K-edge beamtime (four Athena projects, Ti foils), reproduced here.
SYNTHETIC only: every scan, name, Athena project and value below is invented and named ``SYN_``.

* (H3) The scientist's own Athena merge named BEFORE the run name (``merge4_<base>``, ``merge_<base>``: the group's run
  name, or its shared base name without the run counter) is matched and preferred over the per-scan groups beside it,
  so ISAAC never averages those and never says the scientist made no merge. Per-scan groups of EVERY run of a merged
  group form one set (told apart by run and scan). When ISAAC averages, the Athena result's steps say so (a merge
  step: a record lists ``spectrum_merging``).
* (M2) A foil's names are read ONCE for "which element is proposed" and "is it named as a pure element": words of how
  it was measured (calib, a beam size, I0-I3, trans, fluor, PIPS, Lytle, run counters) are neutral and ``Tifoil`` is
  Ti + foil, so ``33_Ti_foil_I1`` and ``01_Tifoil_calib_1x3mm`` are proposed AND said as Ti. A sentence shows the real
  shift or none, never a placeholder. A confirmed (``--accept-shift``) own-edge calibration clears
  ``own_signal_not_named_as_pure_element``; without it nothing is applied (the safety rule stands).
* (L8) Once the scientist confirmed the shift, the sentence no longer asks "only if it is a pure element".
* (M3) The fixed-E0 flag reads every Athena group of the result's own project, matched or not (groups rejected before
  processing too): another SAMPLE's group (repeats of one sample, named the same apart from counters, never count) whose
  own edge is not at that E0 (its ISAAC E0 differs, or else its own data's edge does). Its sentence says "QC pass or
  warn", never "QC passed".
* (M5) After ``process --group``, the Athena statement speaks of the groups processed NOW and counts the project's
  Athena groups that match any record group (this run's match over every group, and the stored results); it never
  says "matched no record group" while other groups hold matched Athena results.
* (M4) An outlier scan is named by its file, with the energy range where it departs from the other scans, its signal
  there as a share of theirs and what merging it did, and the scientist is asked whether it belongs in the merge.
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


# --- M2: ONE name reading for "which element is proposed" and "is it named as a pure element" --------------------


from isaac_api.local_import.processing import reference as REF  # noqa: E402


@pytest.mark.parametrize("name", ["33_Ti_foil_I1", "01_Tifoil_calib_1x3mm", "Ti_foil_trans_PIPS_run2", "Ti_foil_Lytle_I0",
                                  "02_Ti_foil_0p5x1mm_fluor", "Ti_foil_transDet_016_A", "33_Ti_foil_A.001"])
def test_how_a_foil_was_measured_says_nothing_of_its_chemistry(name):
    c = REF.calibrant_identity([name])
    assert (c["kind"], c["element"]) == ("element", "Ti"), name


@pytest.mark.parametrize("name", ["SYN_TiO2_calib_1x3mm", "Ti_foil_A", "calib_B_1x3mm", "TiN_foil_I1", "Ti_Co_foil_I0"])
def test_a_measurement_word_never_makes_a_compound_or_a_label_pure(name):
    assert REF.calibrant_identity([name])["kind"] == "unknown", name


def _reference_case(tmp_path, stem, *, e0_offset=0.2, element_evidence=True):
    _processing()
    from test_local_import_processing import E0, GRID, make_case, mu_edge, spec_file
    import numpy as np

    def scan(seed):
        rng = np.random.default_rng(seed)
        i0 = np.full(GRID.size, 1.0e5)
        i1 = i0 * np.exp(-(mu_edge(GRID, E0 + e0_offset) + rng.normal(0, 0.0005, GRID.size)))
        return spec_file({"energy": GRID, "I0": i0, "I1": i1})

    bdir, root, bundle = make_case(tmp_path, [(stem, [scan(1), scan(2)], {"sample_name": stem})])
    bundle["record_groups"] = [{"group_id": "g-ref", "experiment_key": "e", "role": "reference",
                                "member_run_keys": [bundle["runs"][0]["run_key"]],
                                "basis": {"sample": {}, "technique": {}, "environment": {}, "conditions": {}},
                                "split_reasons": [], "status": "proposed", "questions": []}]
    if element_evidence:
        bundle["experiment"]["element_evidence"] = [{"element": "Ti", "edge": "K", "source_id": "src-001-a",
                                                     "locator": "SYN region file"}]
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


def _cal(result):
    return next(s for s in result["steps"] if s["step"] == "calibration")


@pytest.mark.parametrize("stem", ["33_Ti_foil_I1", "01_Tifoil_calib_1x3mm"])
def test_a_foil_named_with_measurement_words_is_proposed_and_said_as_ti_with_the_shift(tmp_path, stem):
    bdir, root = _reference_case(tmp_path, stem)
    _, [isa], _ = _process(bdir, root)
    cal = _cal(isa)
    o = cal["outcome"]
    assert (o["reference"]["element"], o["reference"]["edge"]) == ("Ti", "K")
    assert o["reference"]["evidence"][0]["kind"] == "name_reading"
    assert REF.NOT_NAMED_ELEMENT_FLAG not in cal["flags"] and o["calibration_proposed"] is True
    said = o["reference_statement"]
    shift = REF.shown(o["computed_shift_eV"])
    assert f"its names say it is Ti; if so, approve with --accept-shift {shift}." in said
    assert "cannot tell" not in said and "<the shift shown>" not in said
    w = REF.would_apply(cal, "Ti", "K", warn_eV=2.0)
    assert "cannot tell" not in w["statement"] and w["needs_calibrant_confirmation"]  # still --accept-shift


def test_with_no_edge_stated_no_shift_is_said_and_no_placeholder_either(tmp_path):
    bdir, root = _reference_case(tmp_path, "01_Tifoil_calib_1x3mm", element_evidence=False)
    _, [isa], _ = _process(bdir, root)
    o = _cal(isa)["outcome"]
    assert o["computed_shift_eV"] is None and o["unconfirmed_reason"].startswith("edge_not_stated_uniquely")
    said = o["reference_statement"]
    assert "<the shift shown>" not in said and "approve with --accept-shift" not in said
    assert REF.NO_SHIFT_YET in said and "its names say it is Ti" in said


def test_a_confirmed_own_edge_calibration_clears_the_names_flag_and_stops_asking(tmp_path):
    from isaac_api.local_import.processing.edges import edge_energy

    bdir, root = _reference_case(tmp_path, "05_SYN_TiO2_std", e0_offset=1.0)
    _, [isa], _ = _process(bdir, root)
    cal = _cal(isa)
    assert REF.NOT_NAMED_ELEMENT_FLAG in cal["flags"] and REF.NOT_NAMED_ELEMENT_FLAG in isa["review_flags"]
    shift = round(edge_energy("Ti", "K")[0] - cal["outcome"]["measured_reference_e0_eV"], 1)
    approval = {"element": "Ti", "edge": "K", "decided_by": "SYN Scientist", "decision_id": "d-syn", "accepted_shift_eV": shift}
    _, [isa2], _ = _process(bdir, root, calibration_approvals={"g-ref": approval})
    cal2 = _cal(isa2)
    assert cal2["outcome"]["applied"] is True
    assert REF.NOT_NAMED_ELEMENT_FLAG not in cal2["flags"] and REF.NOT_NAMED_ELEMENT_FLAG not in isa2["review_flags"]
    said = cal2["outcome"]["reference_statement"]
    assert "The scientist confirmed this group's own edge as the energy calibration (Ti K) by SYN Scientist" in said
    assert "cannot tell" not in said and "Only if" not in said
    # without its size confirmed nothing is applied and the flag stays (the safety rule)
    _, [isa3], _ = _process(bdir, root, calibration_approvals={"g-ref": {**approval, "accepted_shift_eV": None}})
    assert _cal(isa3)["outcome"]["applied"] is False and REF.NOT_NAMED_ELEMENT_FLAG in _cal(isa3)["flags"]


# --- L8: the reply that records a confirmed own-edge calibration asks nothing again --------------------------------


def test_would_apply_with_the_confirmed_shift_does_not_ask_again():
    step = {"step": "calibration", "params": {"reference_min_edge_snr": 10.0, "max_plausible_shift_eV": 25.0},
            "outcome": {"reference_source": REF.OWN_SIGNAL, "reference_e0_per_scan_eV": [2470.8, 2470.8],
                        "reference_snr_per_scan": [400.0, 380.0],
                        "reference_calibrant": REF.calibrant_identity(["SYN_MoS2_std"])}}
    asked = REF.would_apply(step, "S", "K", warn_eV=2.0)["statement"]
    assert "ISAAC cannot tell" in asked and "Only if it is a pure element, approve with --accept-shift +1.2." in asked
    done = REF.would_apply(step, "S", "K", warn_eV=2.0, accepted=1.2)
    assert "cannot tell" not in done["statement"] and "Only if" not in done["statement"]
    assert "with its size confirmed (--accept-shift +1.2), processing applies it" in done["statement"]
    # a size that is not the shift is not a confirmation: it is asked as before
    assert "ISAAC cannot tell" in REF.would_apply(step, "S", "K", warn_eV=2.0, accepted=0.5)["statement"]


# --- M3: the fixed-E0 flag reads every Athena group of the result's own project ----------------------------------


def _athena_pair(gid, athena_e0, isaac_e0, label, *, verdict="pass", run="r-0000000000000001"):
    return [
        {"group_id": gid, "run_id": run, "source": "isaac_protocol", "outputs": {"e0_eV": isaac_e0},
         "qc": {"verdict": verdict}, "result_id": f"proc-{gid}-{run}-isaac", "state": "needs_review"},
        {"group_id": gid, "run_id": run, "source": "scientist_athena", "outputs": {"e0_eV": athena_e0}, "qc": {},
         "inputs": [{"relative_path": "athena_10_SYN.prj", "athena_group": label.lower(), "scan": label}],
         "result_id": f"proc-{gid}-{run}-athena", "state": "needs_review"},
    ]


def _entry(label, e0, prj="athena_10_SYN.prj", *, edge=4980.0):
    """One Athena group read from ``prj``: its E0 and where its own stored data puts its edge (``edge``)."""
    from isaac_api.local_import.processing import athena as A

    return {"prj_relative_path": prj, "group_name": label.lower(), "label": label, "names": [A.normalise_name(label)],
            "e0_eV": e0, "is_merge": False, "data_e0_eV": edge}


def _group(gid, stem, status="proposed"):
    return {"group_id": gid, "_stems": [stem], "_has_scans": True, "basis": {}, "status": status}


FIXED = 4977.440
LIVE = _group("g04", "04_SYN_TiON_dry_016")
REJECTED = [_group("g05", "05_SYN_TiO2_anatase_020", "rejected"), _group("g07", "07_SYN_TiON_wet_031", "rejected"),
            _group("g10", "10_SYN_Ti2O3_044", "rejected")]


def _fixed_e0(results, groups, entries, bundle=None):
    from isaac_api.local_import.processing import run as RUN

    return RUN.possibly_fixed_athena_e0(results, bundle or {}, groups, entries)


def test_one_projects_e0_given_to_rejected_groups_flags_the_live_groups_result():
    from isaac_api.local_import.processing import run as RUN

    results = _athena_pair("g04", FIXED, 4979.20, "04_SYN_TiON_dry_016_A.001")
    entries = [_entry("04_SYN_TiON_dry_016_A.001", FIXED), _entry("05_SYN_TiO2_anatase_020", FIXED, edge=4980.1),
               _entry("07_SYN_TiON_wet_031", FIXED, edge=4979.4), _entry("merge_10_SYN_Ti2O3", FIXED, edge=4975.9)]
    # the old comparison (other Athena RESULTS only) saw nothing: the other groups were rejected before processing
    assert _fixed_e0([dict(r) for r in results], [LIVE, *REJECTED], ()) is None
    out = _fixed_e0(results, [LIVE, *REJECTED], entries)
    assert out["results"] == ["proc-g04-r-0000000000000001-athena"]
    ath = results[1]
    assert RUN.FIXED_E0_FLAG in ath["review_flags"] and ath["preferred_for_record"] is False
    said = ath["qc"]["statements"][RUN.FIXED_E0_FLAG]
    assert said.startswith("The scientist's Athena E0 here, 4977.440 eV, is exactly the Athena E0 of 3 other Athena "
                           "groups of other samples in the same project (athena_10_SYN.prj:")
    assert "'05_SYN_TiO2_anatase_020' (its own edge at 4980.100 eV)" in said and "ISAAC measures 4979.200 eV here" in said
    assert "QC passed" not in said
    info = ath["athena_e0_possibly_fixed"]["same_project"]["athena_groups"]
    assert {f["group_id"] for f in info} == {"g05", "g07", "g10"}
    [q] = ath["questions"]
    assert q["code"] == RUN.FIXED_E0_QUESTION and "3 other Athena groups of other samples" in q["text"]
    assert "other samples in the same Athena project" in out["statement"]


def test_repeats_of_one_sample_in_the_project_are_not_other_samples():
    results = _athena_pair("g04", FIXED, 4979.20, "merge4_04_SYN_TiON_dry")
    entries = [_entry(f"04_SYN_TiON_dry_{run:03d}_A.{n:03d}", FIXED) for run in (16, 17, 18) for n in (1, 2)]
    entries += [_entry("merge4_04_SYN_TiON_dry", FIXED), _entry("04_SYN_TiON_dry_sum", FIXED)]
    assert _fixed_e0(results, [LIVE], entries) is None
    assert "athena_e0_possibly_fixed" not in (results[1].get("review_flags") or ())


def test_an_e0_where_the_edges_are_is_no_setting():
    # other samples whose OWN data put their edge at that E0: two samples' edges on one grid point, not a setting
    results = _athena_pair("g04", FIXED, 4979.20, "04_SYN_TiON_dry_016")
    on_edge = [_entry("05_SYN_TiO2_anatase_020", FIXED, edge=FIXED + 0.1), _entry("07_SYN_TiON_wet_031", FIXED, edge=FIXED)]
    assert _fixed_e0([dict(r) for r in results], [LIVE, *REJECTED], on_edge) is None
    # ISAAC measures THIS group's edge at that E0: it is where its edge is, whatever other groups carry
    here = _athena_pair("g04", FIXED, FIXED + 0.2, "04_SYN_TiON_dry_016")
    assert _fixed_e0(here, [LIVE, *REJECTED], [_entry("05_SYN_TiO2_anatase_020", FIXED, edge=4980.1)]) is None
    # NEGATIVE CONTROL: one other sample whose own edge is elsewhere is enough
    out = _fixed_e0([dict(r) for r in results], [LIVE, *REJECTED], [_entry("05_SYN_TiO2_anatase_020", FIXED, edge=4980.1)])
    assert out and out["results"] == ["proc-g04-r-0000000000000001-athena"]


def test_where_the_other_groups_have_an_isaac_e0_it_must_differ():
    results = _athena_pair("g04", FIXED, 4979.20, "04_SYN_TiON_dry_016")
    near = (_athena_pair("g05", 4970.0, 4979.30, "x", run="r-0000000000000002")[:1]
            + _athena_pair("g07", 4970.0, 4979.10, "y", run="r-0000000000000003")[:1])
    entries = [_entry("05_SYN_TiO2_anatase_020", FIXED), _entry("07_SYN_TiON_wet_031", FIXED)]
    groups = [LIVE, _group("g05", "05_SYN_TiO2_anatase_020"), _group("g07", "07_SYN_TiON_wet_031")]
    # their own data's edge (4980.0) is not consulted: the ISAAC E0 that exists decides, and it does not differ
    assert _fixed_e0([dict(r) for r in results] + near, groups, entries) is None
    far = _athena_pair("g05", 4970.0, 4981.0, "x", run="r-0000000000000002")[:1]
    out = _fixed_e0([dict(r) for r in results] + far, groups, entries)
    assert out and out["results"] == ["proc-g04-r-0000000000000001-athena"]


def _fixed_prj(path, groups, *, e0):
    import larch.xafs as xafs
    from larch import Group
    from larch.io import AthenaProject

    prj = AthenaProject()
    for label, e, mu in groups:
        g = Group(energy=e, mu=mu, label=label, filename=label)
        xafs.pre_edge(g, e0=e0, pre1=-50, pre2=-30, norm1=60, norm2=110, nnorm=2)
        prj.add_group(g)
    prj.save(str(path))


def test_an_athena_e0_shared_with_rejected_groups_is_flagged_end_to_end(tmp_path):
    _processing()
    from test_local_import_processing import GRID, _athena_prj, fluo_scan, make_case, mu_edge, spec_file

    stems = ["04_SYN_TiON_dry_016", "05_SYN_TiO2_anatase_020", "07_SYN_TiON_wet_031", "10_SYN_Ti2O3_044"]
    runs = [(s, [spec_file(fluo_scan(10 * i + j)) for j in (1, 2)], {"sample_name": s}) for i, s in enumerate(stems)]
    bdir, root, bundle = make_case(tmp_path, runs)
    bundle["record_groups"] = [{"group_id": f"g{i}", "experiment_key": "e", "role": "sample",
                                "member_run_keys": [r["run_key"]], "basis": {"sample": {}, "technique": {},
                                                                              "environment": {}, "conditions": {}},
                                "split_reasons": [], "status": "proposed" if i == 0 else "rejected", "questions": []}
                               for i, r in enumerate(bundle["runs"])]
    # one project: four samples' groups, every one normalised with ONE E0 typed in Athena (4977.44 eV), while their
    # own edges sit at 4966, 4969, 4972 and 4975 eV
    _fixed_prj(root / "athena_10_SYN.prj", [(s, GRID, mu_edge(GRID, 4966.0 + 3 * i) * 1e-2) for i, s in enumerate(stems)],
               e0=4977.44)
    bundle["unread_files"].append({"source_id": "prj-SYN", "relative_path": "athena_10_SYN.prj"})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    out, [isa], [ath] = _process(bdir, root, skip_group_ids=["g1", "g2", "g3"])
    assert ath["group_id"] == "g0" and ath["outputs"]["e0_eV"] == pytest.approx(4977.44, abs=1e-3)
    assert "athena_e0_possibly_fixed" in ath["review_flags"] and ath["preferred_for_record"] is False
    assert out["athena"]["e0_possibly_fixed"]["results"] == [ath["result_id"]]
    found = ath["athena_e0_possibly_fixed"]["same_project"]["athena_groups"]
    assert [f["athena_label"] for f in found] == stems[1:] and all(f["isaac_e0_eV"] is None for f in found)


def test_one_projects_measured_e0s_of_several_samples_are_not_flagged_end_to_end(tmp_path):
    # NEGATIVE CONTROL: the same samples, each normalised at its own edge (all at 4966 eV, so one E0 for all)
    _processing()
    from test_local_import_processing import GRID, _athena_prj, fluo_scan, make_case, mu_edge, spec_file

    stems = ["04_SYN_TiON_dry_016", "05_SYN_TiO2_anatase_020", "07_SYN_TiON_wet_031", "10_SYN_Ti2O3_044"]
    runs = [(s, [spec_file(fluo_scan(10 * i + j)) for j in (1, 2)], {"sample_name": s}) for i, s in enumerate(stems)]
    bdir, root, bundle = make_case(tmp_path, runs)
    bundle["record_groups"] = [{"group_id": f"g{i}", "experiment_key": "e", "role": "sample",
                                "member_run_keys": [r["run_key"]], "basis": {"sample": {}, "technique": {},
                                                                              "environment": {}, "conditions": {}},
                                "split_reasons": [], "status": "proposed" if i == 0 else "rejected", "questions": []}
                               for i, r in enumerate(bundle["runs"])]
    _athena_prj(root / "athena_10_SYN.prj", [(s, GRID, mu_edge(GRID) * (1e-2 + 1e-4 * i)) for i, s in enumerate(stems)])
    bundle["unread_files"].append({"source_id": "prj-SYN", "relative_path": "athena_10_SYN.prj"})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    out, _, [ath] = _process(bdir, root, skip_group_ids=["g1", "g2", "g3"])
    assert "athena_e0_possibly_fixed" not in ath["review_flags"] and "e0_possibly_fixed" not in out["athena"]


# --- M5: `process --group` never says no Athena group matched while other groups' did -----------------------------


def _two_groups(tmp_path):
    """Two imported runs of two samples (synthetic XDAC scans), grouped, and one project: an exact match for the first
    run, another sample's group, and a near miss of the second run's name."""
    _processing()
    from test_local_import_polish_c10m import _prj
    from test_local_import_polish_c2f import _xdac, std_scan
    from test_local_import_processing import GRID, mu_edge

    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M

    root = tmp_path / "SYN_beamtime"
    stems = ["08_SYN_ZZ_pellet_030", "09_SYN_QQ_film_031"]
    for i, stem in enumerate(stems):
        for k in (1, 2):
            _xdac(root / "bt" / f"{stem}_A.00{k}", std_scan(10 * i + k, i1_positive=True))
    _prj(root / "bt" / "SYN.prj", [(stems[0], GRID, mu_edge(GRID) * 1e-2), ("SYN_other_sample", GRID, mu_edge(GRID) * 2e-2),
                                   (f"{stems[1]}_again", GRID, mu_edge(GRID) * 3e-2)])
    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    M.group(out)
    return out, root, stems


def test_process_group_scopes_the_athena_statement_to_the_groups_processed_now(tmp_path):
    from isaac_api.local_import import mutations as M

    bdir, root, stems = _two_groups(tmp_path)
    full = M.process(bdir, source=str(root))
    assert not any("matched no record group" in line for line in full["summary"]["lines"])
    groups = M.load(bdir)["record_groups"]
    assert len(groups) == 2
    by_stem = {r["run_key"]: r["stem"] for r in M.load(bdir)["runs"]}
    g_a, g_b = (next(g["group_id"] for g in groups if by_stem[g["member_run_keys"][0]] == s) for s in stems)
    out = M.process(bdir, source=str(root), group_ids=[g_b])
    [line] = [x for x in out["summary"]["lines"] if x.startswith("Athena:")]
    assert line.startswith("Athena: none of the 1 group(s) processed now has an Athena match under rule "
                           "isaac.athena.match_by_name.v1")
    assert "of the 3 Athena group(s) read, 1 match a record group" in line and "2 match none" in line
    assert "1 of those begin with a group's scan name but end in a suffix the rule does not accept ('_again')" in line
    assert "matched no record group" not in line and "No ISAAC result was compared" not in line
    assert line.endswith("No ISAAC result processed now was compared with the scientist's Athena processing.")
    # g-a's matched Athena result is kept as stored
    assert any(r["source"] == "scientist_athena" and r["group_id"] == g_a for r in M.load(bdir)["processing_results"])


def test_a_stored_match_counts_even_when_this_run_matches_nothing(tmp_path):
    from isaac_api.local_import.processing import run as RUN

    entries = [{"prj_relative_path": "SYN.prj", "group_name": "old_name", "label": "old_name", "names": ["old_name"]},
               {"prj_relative_path": "SYN.prj", "group_name": "x", "label": "x", "names": ["x"]}]
    groups = [{"group_id": "g1", "_stems": ["01_SYN_ZZ1"], "_has_scans": True}]
    stored = [{"source": "scientist_athena", "group_id": "g9", "inputs": [{"relative_path": "SYN.prj", "athena_group": "old_name"}]}]
    line = RUN.athena_match_statement(groups, entries, matched={}, notes=[], processed={"g1"}, stored=stored)
    assert "of the 2 Athena group(s) read, 1 match a record group" in line and "matched no record group" not in line
    # nothing matched anywhere: the line is the one it always was
    assert RUN.athena_match_statement(groups, entries, matched={}, notes=[], processed={"g1"}).startswith(
        "Athena: 2 Athena group(s) were read and matched no record group")


# --- M4: an outlier scan is named, not only counted -----------------------------------------------------------------


def test_a_scan_whose_signal_dies_is_named_with_where_and_what_merging_it_did(tmp_path):
    _processing()
    import numpy as np
    from test_local_import_processing import GRID, fluo_scan, make_case, spec_file

    def dying(seed):
        cols = fluo_scan(seed)
        cols["vortDT"] = np.where(GRID > 4985.0, cols["vortDT"] * 0.05, cols["vortDT"])  # the counts fall to 5 %
        return cols

    scans = [spec_file(fluo_scan(1)), spec_file(fluo_scan(2)), spec_file(dying(3)), spec_file(fluo_scan(4))]
    bdir, root, _ = make_case(tmp_path, [("01_SYN_TiON_dry_016", scans, {"sample_name": "ZZ1"})])
    _, [isa], _ = _process(bdir, root)
    dg = next(s for s in isa["steps"] if s["step"] == "deglitch")
    assert "outlier_scans_flagged" in dg["flags"] and len(dg["outcome"]["outlier_scans"]) == 1
    said = isa["qc"]["statements"]["outlier_scans"]
    assert said.startswith("01_SYN_TiON_dry_016_003.dat departs from the other scans' median from 4985.")
    assert "its signal there is about 5% of theirs" in said
    assert "it is merged unchanged, so the merged curve there is about 24% lower than the other scans' median" in said
    assert said.endswith("Ask the scientist whether this scan belongs in the merge (a beam loss, a sample that moved or "
                         "a detector that stopped counting would not).")
    # said outside the hashed qc.json: the file keeps what it had (no id moves)
    qc = json.loads(next(bdir / f["relative_path"] for f in isa["outputs"]["files"] if f["role"] == "qc").read_text())
    assert "outlier_scans" not in (qc.get("statements") or {})


def test_scans_that_agree_get_no_outlier_sentence(tmp_path):
    _processing()
    from test_local_import_processing import fluo_scan, make_case, spec_file

    bdir, root, _ = make_case(tmp_path, [("01_SYN_TiON_dry_016", [spec_file(fluo_scan(k)) for k in (1, 2, 3, 4)],
                                          {"sample_name": "ZZ1"})])
    _, [isa], _ = _process(bdir, root)
    assert "outlier_scans" not in (isa["qc"].get("statements") or {})
