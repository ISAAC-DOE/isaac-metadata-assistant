"""Polish r3-d: review findings on r3-b's XAS processing and Athena handling, reproduced here.
SYNTHETIC only: every scan, name, Athena project and value below is invented (``SYN_``, ``ZZ``, ``QQ``).

* (MED-1) A merged group of XDAC runs whose stems end in ``_A`` (``…_016_A`` + ``…_017_A``) has the base name without
  the counter AND its letter, so the scientist's ``merge4_<base>`` is matched again.
* (MED-2) The per-scan groups beside the scientist's merge are never dropped silently: the set they form is listed
  and said as set aside, and when it covers every scan of the group the merge is compared with its mean; a merge that
  differs from it (stale, partial) is no longer preferred, and the scientist is asked which is the result of record.
* (MED-3) A foil the earlier rule proposed (a ``foil`` word, one symbol, an edge stated) whose name holds a word the
  reading does not know keeps that reference and its computed shift in the hashed outcome (no result id moves), and
  is still not proposed. A foil thickness (``7um``) is neutral.
* (MED-4) SYN / ZZ, the markers of invented names, are neutral words of the name reading.
* (L-1) A group's own data edge is looked for only near its Athena E0, so one glitch far away is never its edge.
* (L-2) Where this group's ISAAC QC failed, another sample's group with an ISAAC E0 counts by its own data edge; and
  "this group's edge is at the E0" is read from this curve's own data edge, in the Athena E0's frame.
* (L-3) A lone one-letter symbol beside a channel word (``B_trans``, ``S_fluo``, ``C_I1``) is not a pure element.
* (L-5) A scan label is read against the longest run stem first.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import bundle as B

from test_local_import_polish_r3b import FIXED, _athena_pair, _entry, _fixed_e0, _group, _process


def _processing():
    pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")


def _case(tmp_path, stems, athena_groups, *, scans=2):
    """ONE group of the runs ``stems`` (``scans`` scans each) and a project ``SYN.prj`` of ``athena_groups``
    (label, mu factor, edge offset in eV from the synthetic E0)."""
    _processing()
    from test_local_import_processing import E0, GRID, _athena_prj, fluo_scan, make_case, mu_edge, spec_file

    runs = [(s, [spec_file(fluo_scan(10 * i + j)) for j in range(1, scans + 1)], {"sample_name": "ZZ1"})
            for i, s in enumerate(stems)]
    bdir, root, bundle = make_case(tmp_path, runs)
    if len(stems) > 1:
        bundle["record_groups"] = [{"group_id": "g-merged", "experiment_key": "e", "role": "sample",
                                    "member_run_keys": [r["run_key"] for r in bundle["runs"]],
                                    "basis": {"sample": {}, "technique": {}, "environment": {}, "conditions": {}},
                                    "split_reasons": [], "status": B.STATE_SCIENTIST_CONFIRMED, "questions": []}]
    _athena_prj(root / "SYN.prj", [(label, GRID, mu_edge(GRID, E0 + shift) * k) for label, k, shift in athena_groups])
    bundle["unread_files"].append({"source_id": "prj-SYN", "relative_path": "SYN.prj"})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


# --- MED-1: a two-run XDAC group's base name drops the counter's letter too --------------------------------------


def test_base_name_of_two_xdac_runs_drops_the_letter_after_the_counter():
    from isaac_api.local_import.processing import athena as A

    assert A.base_names(["22_x_dry_016_A", "22_x_dry_017_A"]) == {"22_x_dry"}
    assert A.base_names(["22_x_dry_016_A"]) == {"22_x_dry"}  # as for one run
    # a lone letter that IS the name, or letters that differ, are not a counter's
    assert A.base_names(["01_x", "02_x"]) == {"x"} and A.base_names(["x_1_a", "x_2_b"]) == set()


XDAC_RUNS = ("22_SYN_ZZ1_dry_016_A", "22_SYN_ZZ1_dry_017_A")
XDAC_SCANS = [(f"{s}.{n:03d}", 1e-2 + 1e-4 * (2 * i + n), 0.0) for i, s in enumerate(XDAC_RUNS) for n in (1, 2)]


def test_a_two_run_xdac_groups_merge_named_after_its_base_name_is_matched(tmp_path):
    bdir, root = _case(tmp_path, XDAC_RUNS, XDAC_SCANS + [("merge4_22_SYN_ZZ1_dry", 1.003e-2, 0.0)])
    _, [isa], [ath] = _process(bdir, root)
    [inp] = ath["inputs"]
    assert inp["scan"] == "merge4_22_SYN_ZZ1_dry" and inp["match_kind"] == "scientist_merge"
    assert ath["comparison"]["athena_covers"]["runs"] == list(XDAC_RUNS)
    assert ath["preferred_for_record"] is True and "athena_versions" not in isa
    # the per-scan groups of both runs beside it are said as set aside, and agree with it
    [aside] = ath["athena_per_scan_sets_set_aside"]
    assert aside["per_scan_groups"] == 4 and aside["covers_every_scan_of_group"] is True
    assert aside["comparison"]["verdict"] == "agree"


# --- MED-2: a stale or partial merge never silently beats a complete per-scan set ---------------------------------


ONE_RUN = "01_SYN_ZZ1_dry_016"
PER_SCAN = [(f"{ONE_RUN}_A.{n:03d}", 1e-2 + 1e-4 * n, 0.0) for n in (1, 2, 3)]


def test_a_merge_that_agrees_with_the_full_set_beside_it_stays_preferred_and_the_set_is_said(tmp_path):
    from isaac_api.local_import.processing import run as RUN

    bdir, root = _case(tmp_path, [ONE_RUN], PER_SCAN + [("merge_01_SYN_ZZ1_dry", 1.003e-2, 0.0)], scans=3)
    _, [isa], [ath] = _process(bdir, root)
    assert ath["inputs"][0]["match_kind"] == "scientist_merge" and ath["preferred_for_record"] is True
    [aside] = ath["athena_per_scan_sets_set_aside"]
    assert aside["provenance"]["per_scan_set"]["scans"] == [1, 2, 3] and aside["covers_every_scan_of_group"] is True
    assert aside["comparison"]["verdict"] == "agree"
    said = ath["qc"]["statements"][RUN.SET_ASIDE_STATEMENT]
    assert said.startswith(f"The 3 per-scan Athena groups beside it in SYN.prj ('{ONE_RUN}_A.001' …) were set aside")
    assert "agrees with the merge" in said
    assert RUN.MERGE_DIFFERS_FROM_SET_FLAG not in ath["review_flags"] and not ath.get("questions")


def test_a_stale_merge_that_differs_from_the_full_set_is_not_preferred_and_asked(tmp_path):
    from isaac_api.local_import.processing import run as RUN

    stale = ("merge2_01_SYN_ZZ1_dry", 1.2e-2, 3.0)  # an older merge: its edge 3 eV from the per-scan groups'
    bdir, root = _case(tmp_path, [ONE_RUN], PER_SCAN + [stale], scans=3)
    _, [isa], [ath] = _process(bdir, root)
    assert ath["inputs"][0]["scan"] == "merge2_01_SYN_ZZ1_dry"  # still the scientist's merge, so no id moves
    assert ath["preferred_for_record"] is False and RUN.MERGE_DIFFERS_FROM_SET_FLAG in ath["review_flags"]
    [aside] = ath["athena_per_scan_sets_set_aside"]
    assert aside["comparison"]["verdict"] == "differs" and "e0_differs" in aside["comparison"]["flags"]
    assert aside["comparison"]["metrics"]["e0_delta_eV"] == pytest.approx(3.0, abs=0.6)
    said = ath["qc"]["statements"][RUN.SET_ASIDE_STATEMENT]
    assert "The scientist's merge 'merge2_01_SYN_ZZ1_dry' differs from the mean of the 3 per-scan groups beside it" in said
    assert "ask which is the result of record" in said
    [q] = [q for q in ath["questions"] if q["code"] == RUN.MERGE_OR_SET_QUESTION]
    assert "Which is the result of record: the merge, or the per-scan groups?" in q["text"]


def test_a_set_that_does_not_cover_every_scan_is_said_but_not_compared(tmp_path):
    from isaac_api.local_import.processing import run as RUN

    bdir, root = _case(tmp_path, [ONE_RUN], PER_SCAN[:2] + [("merge2_01_SYN_ZZ1_dry", 1.2e-2, 3.0)], scans=3)
    _, _, [ath] = _process(bdir, root)
    [aside] = ath["athena_per_scan_sets_set_aside"]
    assert aside["covers_every_scan_of_group"] is False and "comparison" not in aside
    said = ath["qc"]["statements"][RUN.SET_ASIDE_STATEMENT]
    assert "were set aside" in said and "do not cover every scan of this group" in said
    assert ath["preferred_for_record"] is True and RUN.MERGE_DIFFERS_FROM_SET_FLAG not in ath["review_flags"]


def test_without_a_merge_nothing_is_said_set_aside(tmp_path):
    from isaac_api.local_import.processing import run as RUN

    bdir, root = _case(tmp_path, [ONE_RUN], PER_SCAN, scans=3)
    _, _, [ath] = _process(bdir, root)
    assert ath["inputs"][0]["match_kind"] == "per_scan_set"
    assert "athena_per_scan_sets_set_aside" not in ath and RUN.SET_ASIDE_STATEMENT not in ath["qc"]["statements"]


# --- MED-3 / MED-4 / L-3: the name reading and the hashed calibration ---------------------------------------------


def _foil(tmp_path, stem):
    _processing()
    from test_local_import_processing import _foil_xdac, make_case
    from isaac_api.local_import.processing.cli_entry import run_process

    t = tmp_path / stem
    t.mkdir()
    unread = {f"{stem}_A.001": _foil_xdac("TiK_SYNTHETIC_region.rgn", 1), f"{stem}_A.002": _foil_xdac("TiK_SYNTHETIC_region.rgn", 2)}
    bdir, root, _ = make_case(t, [], unread=unread)
    r = run_process(bdir, source_root=root)["unread_acquisition_results"][0]
    cal = next(s for s in r["steps"] if s["step"] == "calibration")
    hashed = json.loads((bdir / "processing" / r["group_id"] / r["run_id"] / "params.json").read_text())["calibration"]
    return r, cal, hashed


@pytest.mark.parametrize("stem", ["SYN_Ti_foil", "Ti_foil_QQ_016"])
def test_a_foil_the_earlier_rule_proposed_keeps_its_hashed_reference_and_shift_but_is_not_proposed(tmp_path, stem):
    from isaac_api.local_import.processing import reference as REF

    r, cal, hashed = _foil(tmp_path, stem)
    o = cal["outcome"]
    # hashed exactly as the earlier rule wrote it: the reference, its reason and the computed shift
    assert hashed["reference"]["element"] == "Ti" and hashed["reference"]["edge"] == "K"
    assert hashed["reference"]["evidence"][0] == {"kind": "name_token", "name": f"{stem}_A", "element": "Ti"}
    assert hashed["unconfirmed_reason"] == "proposed_not_approved"
    assert hashed["computed_shift_eV"] == pytest.approx(-3.0, abs=0.6) and hashed["applied_shift_eV"] == 0.0
    # ... and still not proposed: the reading cannot tell, so nothing awaits an approval
    assert o["calibration_proposed"] is False and REF.NOT_NAMED_ELEMENT_FLAG in cal["flags"]
    assert "calibration_shift_awaiting_approval" not in cal["flags"]
    # the scientist is given the shift they confirm with --accept-shift
    assert f"Only if it is a pure element, approve with --accept-shift {REF.shown(o['computed_shift_eV'])}." in o["reference_statement"]


@pytest.mark.parametrize("stem", ["Ti_foil_7um_016", "SYN_Ti_foil_I1_016", "ZZ_Ti_foil_0p5mm_016"])
def test_a_thickness_and_the_syn_zz_markers_say_nothing_of_the_chemistry(tmp_path, stem):
    from isaac_api.local_import.processing import reference as REF

    r, cal, hashed = _foil(tmp_path, stem)
    assert (cal["outcome"]["reference_calibrant"]["kind"], cal["outcome"]["reference_calibrant"]["element"]) == ("element", "Ti")
    assert cal["outcome"]["calibration_proposed"] is True and REF.NOT_NAMED_ELEMENT_FLAG not in cal["flags"]
    assert hashed["reference"]["element"] == "Ti" and hashed["unconfirmed_reason"] == "proposed_not_approved"


@pytest.mark.parametrize("name, element", [("SYN_Ti_foil", "Ti"), ("ZZ_S_std", "S"), ("ZZ1_Cu_foil_10um", "Cu"),
                                           ("Ti_foil_7p5um", "Ti"), ("Cu_foil_50nm", "Cu"), ("SYN_TiO2_std", None),
                                           ("QQ_Ti_foil", None)])
def test_the_syn_and_zz_markers_and_a_thickness_are_neutral_words(name, element):
    from isaac_api.local_import.processing import reference as REF

    c = REF.calibrant_identity([name])
    assert (c["kind"], c["element"]) == (("element", element) if element else ("unknown", None)), name


@pytest.mark.parametrize("name", ["B_trans", "S_trans", "C_I1", "S_fluo", "SYN_K_lytle", "V_PIPS_016"])
def test_a_one_letter_symbol_beside_a_channel_word_is_not_a_pure_element(name):
    from isaac_api.local_import.processing import reference as REF

    assert REF.calibrant_identity([name])["kind"] == "unknown", name


@pytest.mark.parametrize("name, element", [("S_ref_trans", "S"), ("S_foil_I0", "S"), ("Ti_trans", "Ti"), ("S", "S"),
                                           ("Ti_foil_I1_016", "Ti")])
def test_with_a_foil_or_ref_word_or_two_letters_a_channel_word_stays_neutral(name, element):
    from isaac_api.local_import.processing import reference as REF

    c = REF.calibrant_identity([name])
    assert (c["kind"], c["element"]) == ("element", element), name


# --- L-1: a glitch far from the Athena E0 is never the group's own edge -------------------------------------------


def test_a_glitch_far_from_the_athena_e0_is_not_the_groups_own_edge():
    _processing()
    import numpy as np
    from larch.xafs import find_e0
    from test_local_import_processing import GRID, mu_edge
    from isaac_api.local_import.processing import athena as A

    mu = mu_edge(GRID, 4970.4).copy()
    mu[300] += 3.0  # one glitch at 5050 eV
    assert abs(find_e0(GRID, mu) - 4970.4) > 50  # over the whole curve, the glitch is "the edge"
    assert A._data_e0(GRID, mu, 4970.0, np) == pytest.approx(4970.4, abs=0.6)
    # an edge outside the window still reads far from the E0
    assert abs(A._data_e0(GRID, mu_edge(GRID, 4940.0), 4990.0, np) - 4990.0) > A.DATA_E0_WINDOW_EV / 2
    assert A._data_e0(GRID, mu, None, np) is None


# --- L-2: the fixed-E0 flag when this group's ISAAC QC failed, and in the Athena E0's own frame ------------------


OWN = _group("g04", "04_SYN_ZZ_dry_016")


def test_with_this_groups_isaac_qc_failed_a_partner_with_an_isaac_e0_counts_by_its_own_edge():
    results = _athena_pair("g04", FIXED, 4979.2, "04_SYN_ZZ_dry_016", verdict="fail")
    g05 = _group("g05", "05_SYN_QQ_020")
    isaac05 = {"group_id": "g05", "run_id": "r-2", "source": "isaac_protocol", "outputs": {"e0_eV": 4981.0},
               "qc": {"verdict": "pass"}, "result_id": "x", "state": "needs_review"}
    far = _entry("05_SYN_QQ_020", FIXED, edge=4981.0)
    out = _fixed_e0([*results, isaac05], [OWN, g05], [far])
    assert out and out["results"] == ["proc-g04-r-0000000000000001-athena"]
    [found] = results[1]["athena_e0_possibly_fixed"]["same_project"]["athena_groups"]
    assert found["basis"] == "own_data_edge" and "(its own edge at 4981.000 eV)" in results[1]["qc"]["statements"]["athena_e0_possibly_fixed"]
    # NEGATIVE CONTROL: that partner's own data puts its edge at the E0: no evidence
    again = _athena_pair("g04", FIXED, 4979.2, "04_SYN_ZZ_dry_016", verdict="fail")
    assert _fixed_e0([*again, isaac05], [OWN, g05], [_entry("05_SYN_QQ_020", FIXED, edge=FIXED + 0.1)]) is None


def test_this_curves_edge_at_the_e0_is_read_from_its_own_data_in_the_athena_frame():
    partner = _entry("05_SYN_QQ_020", FIXED, edge=4981.0)
    # ISAAC's uncalibrated E0 happens to sit at the Athena E0, while this curve's own data puts its edge 3 eV away
    results = _athena_pair("g04", FIXED, FIXED + 0.2, "04_SYN_ZZ_dry_016")
    mine = _entry("04_SYN_ZZ_dry_016", FIXED, edge=FIXED + 3.0)
    out = _fixed_e0(results, [OWN], [mine, partner])
    assert out and out["results"] == ["proc-g04-r-0000000000000001-athena"]
    # the other way round: its own data's edge IS at the E0 (whatever ISAAC's frame says): no setting
    results = _athena_pair("g04", FIXED, FIXED - 3.0, "04_SYN_ZZ_dry_016")
    assert _fixed_e0(results, [OWN], [_entry("04_SYN_ZZ_dry_016", FIXED, edge=FIXED + 0.1), partner]) is None


# --- L-5: a scan label is read against the longest run stem first ---------------------------------------------------


def test_a_scan_label_is_read_against_the_longest_stem_first():
    from isaac_api.local_import.processing import athena as A

    assert A._selection_of_run("x_dry_2_003", ["x_dry", "x_dry_2"]) == (1, [3])
    assert A._selection_of_run("x_dry_2_003", ["x_dry_2", "x_dry"]) == (0, [3])
    assert A._selection_of_run("x_dry_5_6", ["x_dry", "x_dry_2"]) == (0, [5, 6])
