"""Skill polish, cycle 3 (processing, measured on two real SSRL BL4-3 beamtimes). Synthetic only.

* ATHENA NAMES THAT ARE XDC SCAN FILES (``isaac.athena.match_by_name.v1``). On BL4-3 the scientists'
  Athena groups are named after the scan FILE they hold, ``<run stem>_A.001`` (the SSRL EXAFS Data
  Collector writes a run's scans as ``<stem>_A.NNN``): 161 + 29 Athena groups matched no record group
  under v0. v1 accepts exactly that suffix (``_A.NNN`` / ``_a_NNN``, any case) as naming the run, and
  reads it as scan NNN; nothing looser (no prefix or substring match), and an Athena name that fits
  two record groups still matches neither, with a note.
* JUNK OR MIS-NORMALISED ISAAC CURVES FAIL. A curve whose post-edge level, measured from the pre-edge
  line (since v1 both at each energy and held at E0; see test_local_import_polish_c3r1), is not between 0 and 2 edge steps (``post_edge_not_at_1``), or whose edge step is not 5
  times the pre-edge scatter (``no_edge``), fails with a plain sentence instead of warning.
* A REFERENCE FOIL WHOSE ln(I0/I1) FAILS THOSE CHECKS tries the reference channel: ln(I1/I2), or
  ln(I0/I2) when I1 is not a positive intensity — only for a foil said to be on I2 or one whose I1 is
  not positive, recorded and flagged, never silent.
"""

from __future__ import annotations

import json

import pytest

np = pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")

from isaac_api.local_import.processing import athena as A  # noqa: E402
from isaac_api.local_import.processing import run as RUN  # noqa: E402
from isaac_api.local_import.processing.cli_entry import run_process  # noqa: E402

from test_local_import_processing import GRID, _athena_case, isaac, mu_edge  # noqa: E402

# --- 1. Athena names that are XDC scan files -----------------------------------------------------------


def test_the_xdc_scan_file_suffix_names_the_run():
    stem = "03_syn_dry_015"
    for name in ("03_SYN_dry_015_A.001", "03_syn_dry_015_a_001", "03_SYN_DRY_015_a.012"):
        assert A._match_kind([A.normalise_name(name)], stem) == "xdc_scan_file", name
    # nothing looser: another letter, no separator, a word, or more after the number
    for name in ("03_SYN_dry_015_B.001", "03_SYN_dry_015_A001", "03_SYN_dry_015_Ab.001", "03_SYN_dry_015_A.001_x",
                 "03_SYN_dry_0150_A.001", "x03_SYN_dry_015_A.001"):
        assert A._match_kind([A.normalise_name(name)], stem) is None, name
    # the v0 shapes are unchanged
    assert A._match_kind(["03_syn_dry_015"], stem) == "exact" and A._match_kind(["03_syn_dry_015_001"], stem) == "suffix"
    assert A.MATCH_RULE_ID == "isaac.athena.match_by_name.v1"


def test_an_xdc_scan_file_name_selects_that_scan():
    assert A.scan_selection("03_SYN_dry_015_A.001", ["03_SYN_dry_015"]) == [1]
    assert A.scan_selection("03_SYN_dry_015_a_012.xmu", ["03_SYN_dry_015"]) == [12]
    assert A.scan_selection("SYN_x_A.003", ["SYN_x_A"]) == [3]  # unchanged: a stem that ends in A
    assert A.scan_selection("03_SYN_dry_015_B.001", ["03_SYN_dry_015"]) is None


def test_an_xdc_name_that_fits_two_record_groups_matches_neither():
    entry = {"names": ["syn_x_a_001"], "label": "SYN_x_A.001", "prj_relative_path": "SYN.prj", "data_hash": "h", "is_merge": False}
    groups = [{"group_id": "g-x", "_stems": ["SYN_x"], "_has_scans": True},      # SYN_x + _A.001
              {"group_id": "g-xa", "_stems": ["SYN_x_A"], "_has_scans": True}]   # SYN_x_A + _001
    matched, notes = A.match(groups, [entry], np)
    assert matched == {}
    assert notes == [{"code": "athena_group_matches_several_record_groups", "athena_label": "SYN_x_A.001",
                      "prj_relative_path": "SYN.prj", "group_ids": ["g-x", "g-xa"]}]


def test_an_athena_group_named_after_one_xdc_scan_file_is_compared(tmp_path):
    bdir, root = _athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1_A.001", GRID, mu_edge(GRID) * 1e-2)]})
    out = run_process(bdir, source_root=root)
    isa = isaac(out)
    ref = isa["comparison"]["athena_ref"]
    assert ref["match_kind"] == "xdc_scan_file" and ref["match_rule"] == "isaac.athena.match_by_name.v1"
    assert isa["comparison"]["athena_scan_selection"] == [1]
    assert "scientist_selected_subset_of_scans" in isa["comparison"]["flags"]  # the group has scans 1 and 2
    assert out["athena"]["match_rule"] == "isaac.athena.match_by_name.v1" and out["athena"]["record_groups_matched"] == 1
    assert [r["source"] for r in out["processing_results"]] == ["isaac_protocol", "scientist_athena"]


def test_one_athena_group_per_xdc_scan_file_is_compared_as_a_set(tmp_path):
    groups = [("01_SYN_ZZ1_A.001", GRID, mu_edge(GRID) * 1e-2), ("01_SYN_ZZ1_A.002", GRID, mu_edge(GRID) * 1.01e-2)]
    bdir, root = _athena_case(tmp_path, {"SYN.prj": groups})
    isa = isaac(run_process(bdir, source_root=root))
    assert isa["comparison"]["athena_ref"]["match_kind"] == "per_scan_set"
    assert "athena_versions" not in isa


def test_the_no_match_line_names_only_suffixes_the_rule_does_not_accept():
    groups = [{"group_id": "g1", "_stems": ["03_SYN_dry_015"], "_has_scans": True}]
    entries = [{"names": ["03_syn_dry_015_b_001"], "label": "x"}, {"names": ["unrelated"], "label": "z"}]
    line = RUN.athena_match_statement(groups, entries, matched={}, notes=[])
    assert "isaac.athena.match_by_name.v1" in line and "_A.001" in line
    assert "1 of them" in line and "'_b_001'" in line
    # a name the rule accepts is never said to end in a suffix it does not accept (it was ambiguous)
    line = RUN.athena_match_statement(groups, [{"names": ["03_syn_dry_015_a_001"], "label": "y"}], matched={},
                                      notes=[{"code": "athena_group_matches_several_record_groups"}])
    assert "does not accept" not in line and "1 matched several record groups" in line


# --- 2. junk or mis-normalised curves fail -------------------------------------------------------------

from isaac_api.local_import.processing import core as C  # noqa: E402
from isaac_api.local_import.processing import protocol as P  # noqa: E402

from test_local_import_processing import E0, fluo_scan, make_case, spec_file  # noqa: E402

FLAT_PRE = np.zeros(GRID.size)


def test_post_edge_level_fails_a_step_that_does_not_describe_the_jump():
    mu = mu_edge(GRID, step=1.5, offset=0.0)
    pre = np.zeros(GRID.size)
    ok = C.post_edge_level_implausible(GRID, mu, pre, E0, 1.5, np, norm1=60.0, norm2=130.0)
    assert ok is None
    low = C.post_edge_level_implausible(GRID, mu, pre, E0, 0.6, np, norm1=60.0, norm2=130.0)
    assert low["level"] == pytest.approx(1.5 / 0.6 + 0.0001 * 95 / 0.6, rel=0.02) and low["rule_id"] == C.POST_EDGE_LEVEL_RULE_ID
    assert "2.5" in low["statement"] and "edge steps above the pre-edge line" in low["statement"]
    falling = C.post_edge_level_implausible(GRID, 2.0 - mu, pre + 2.0, E0, 1.5, np, norm1=60.0, norm2=130.0)
    assert falling["level"] < 0 and "below the pre-edge line" in falling["statement"]
    # too few points in the window: not judged
    assert C.post_edge_level_implausible(GRID, mu, pre, E0, 0.6, np, norm1=133.5, norm2=134.0) is None
    assert C.POST_EDGE_LEVEL_RANGE == (0.0, 2.0)


def test_no_edge_when_the_step_is_not_five_times_the_pre_edge_scatter():
    assert C.no_edge(0.5, 0.1) is None and C.no_edge(0.5, None) is None
    bad = C.no_edge(0.7, 0.41)
    assert bad["edge_to_noise"] == pytest.approx(1 / 0.41) and bad["min_multiple"] == C.EDGE_MIN_NOISE_MULTIPLE == 5.0
    assert "2.44 times" in bad["statement"]
    q = P.resolve_params()
    base = {"scans_used": 2, "points": 200, "edge_step": 1.0}
    assert C.qc_verdict(base, q) == ("pass", [])
    assert C.qc_verdict({**base, "edge_to_pre_edge_noise": 2.4}, q) == ("fail", ["no_edge"])
    assert C.qc_verdict({**base, "post_edge_level": 2.5}, q) == ("fail", ["post_edge_not_at_1"])


def _falling_scan(seed):
    rng = np.random.default_rng(seed)
    i0 = np.full(GRID.size, 1.0e5)
    mu = 2.0 - mu_edge(GRID) + rng.normal(0, 0.002, GRID.size)  # the signal FALLS at the edge
    return {"energy": GRID, "I0": i0, "vortDT": mu * i0 * 0.01}


def test_a_curve_that_falls_at_the_edge_fails_with_a_plain_sentence(tmp_path):
    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(_falling_scan(s)) for s in (1, 2)], {"sample_name": "ZZ1"})])
    r = isaac(run_process(bdir, source_root=root))
    assert r["qc"]["metrics"]["edge_step"] > 0  # larch's edge step is |jump|: the step alone does not say it
    assert r["qc"]["verdict"] == "fail" and "post_edge_not_at_1" in r["qc"]["reasons"]
    assert r["qc"]["metrics"]["post_edge_level"] < 0
    assert "below the pre-edge line" in r["qc"]["statements"]["post_edge_not_at_1"]


def test_a_curve_with_no_edge_fails_no_edge(tmp_path):
    def noise(seed):
        rng = np.random.default_rng(seed)
        i0 = np.full(GRID.size, 1.0e5)
        return {"energy": GRID, "I0": i0, "vortDT": (1.0 + rng.normal(0, 0.05, GRID.size)) * i0 * 0.01}

    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(noise(s)) for s in (1, 2)], {"sample_name": "ZZ1"})])
    r = isaac(run_process(bdir, source_root=root))
    assert r["qc"]["verdict"] == "fail" and "no_edge" in r["qc"]["reasons"], r["qc"]
    assert r["qc"]["metrics"]["edge_to_pre_edge_noise"] < 5
    assert "times the pre-edge scatter" in r["qc"]["statements"]["no_edge"]


def test_a_good_curve_carries_none_of_the_new_checks(tmp_path):
    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(fluo_scan(s)) for s in (1, 2)], {"sample_name": "ZZ1"})])
    r = isaac(run_process(bdir, source_root=root))
    assert r["qc"]["verdict"] in ("pass", "warn")
    assert not {"post_edge_level", "edge_to_pre_edge_noise"} & set(r["qc"]["metrics"])
    assert set(r["qc"].get("statements") or ()) <= {"glitch_check_few_scans"}  # c12-cal: the few-scan glitch sentence only


# --- 3. a foil on I2 tries the reference channel --------------------------------------------------------


def _foil_scan(seed, *, i1_dead=True):
    """A SYNTHETIC foil measured on I2: I2 = I0 * exp(-mu_foil); I1 dead (a few counts drifting up with
    energy, some negative: ln(I0/I1) falls, with no edge — the measured shape) or live (I1 = I0 *
    exp(-mu_foil), so ln(I0/I1) is the foil)."""
    rng = np.random.default_rng(seed)
    i0 = np.full(GRID.size, 1.0e5)
    trans = np.exp(-mu_edge(GRID, step=1.0, offset=0.5))
    i1 = (2.0 + 20.0 * (GRID - GRID[0]) / (GRID[-1] - GRID[0]) + rng.normal(0, 2.0, GRID.size)) if i1_dead else i0 * trans
    return {"energy": GRID, "I0": i0, "I1": i1, "I2": i0 * 0.5 * trans * (1 + rng.normal(0, 1e-4, GRID.size))}


def test_a_foil_on_i2_whose_i1_is_dead_uses_ln_i0_i2_flagged(tmp_path):
    bdir, root, _ = make_case(tmp_path, [("31_SYN_Zz_foil_I2_120", [spec_file(_foil_scan(s)) for s in (1, 2)], {})])
    r = isaac(run_process(bdir, source_root=root))
    cc = r["channel_choice"]
    assert cc["signal_name"] == "ln(I0/I2)" and "channel_fallback_reference_channel" in cc["flags"]
    fb = cc["basis"]["fallback_from"]
    assert fb["signal_name"] == "ln(I0/I1)" and fb["reason_code"] == "transmission_failed_edge_checks"
    assert set(fb["failed_checks"]) & {"no_edge", "post_edge_not_at_1"}
    tried = {t["signal_name"]: t for t in fb["tried"]}
    assert tried["ln(I1/I2)"]["outcome"] == "not_tried" and "I1" in tried["ln(I1/I2)"]["reason"]
    assert tried["ln(I0/I2)"]["outcome"] == "used"
    assert "ln(I0/I1)" in fb["statement"] and "ln(I0/I2)" in fb["statement"] and "a person confirms" in fb["statement"]
    assert r["qc"]["verdict"] == "warn" and "channel_fallback_transmission_failed_edge_checks" in r["qc"]["reasons"]
    assert r["qc"]["statements"]["channel_fallback_reference_channel"] == fb["statement"]
    assert abs(r["qc"]["metrics"]["e0_eV"] - E0) < 1.5


def test_a_foil_whose_ln_i0_i1_passes_keeps_it(tmp_path):
    bdir, root, _ = make_case(tmp_path, [("31_SYN_Zz_foil_I2_120", [spec_file(_foil_scan(s, i1_dead=False)) for s in (1, 2)], {})])
    r = isaac(run_process(bdir, source_root=root))
    assert r["channel_choice"]["signal_name"] == "ln(I0/I1)" and "fallback_from" not in r["channel_choice"]["basis"]
    assert "channel_fallback_reference_channel" not in r["channel_choice"]["flags"]


def test_no_reference_channel_when_the_name_does_not_say_i2_and_i1_is_live(tmp_path):
    def scan(seed):
        rng = np.random.default_rng(seed)
        i0 = np.full(GRID.size, 1.0e5)
        trans = np.exp(-mu_edge(GRID, step=1.0, offset=0.5))
        # I1 positive and live but flat noise: ln(I0/I1) has no edge; I2 has one
        return {"energy": GRID, "I0": i0, "I1": 5.0e4 * (1 + rng.normal(0, 0.05, GRID.size)), "I2": i0 * 0.5 * trans}

    bdir, root, _ = make_case(tmp_path, [("02_SYN_Zz_foil_122", [spec_file(scan(s)) for s in (1, 2)], {})])
    r = isaac(run_process(bdir, source_root=root))
    assert r["channel_choice"]["signal_name"] == "ln(I0/I1)" and r["qc"]["verdict"] == "fail"
    assert "fallback_from" not in r["channel_choice"]["basis"]


def test_a_scan_ending_too_soon_above_e0_warns_and_its_level_is_not_judged(tmp_path):
    short = GRID[GRID <= E0 + 20]  # a calibration-style scan: ends 20 eV above E0
    mu = mu_edge(short, step=1.5, offset=0.0)
    assert C.post_edge_level_implausible(short, mu, np.zeros(short.size), E0, 0.3, np, norm1=8.0, norm2=20.0) is None
    found = C.post_edge_window_too_short(short, E0, np)
    assert found["post_e0_span_eV"] == pytest.approx(20.0) and found["min_span_eV"] == C.POST_EDGE_MIN_SPAN_EV == 50.0
    assert "ends 20 eV above E0" in found["statement"] and "edge position is still usable" in found["statement"]
    assert C.post_edge_window_too_short(GRID, E0, np) is None
    q = P.resolve_params()
    assert C.qc_verdict({"scans_used": 2, "points": 200, "edge_step": 1.0, "post_edge_span_eV": 20.0}, q) == ("warn", ["post_edge_window_too_short"])
    scans = [spec_file(fluo_scan(s, e=short)) for s in (1, 2)]
    bdir, root, _ = make_case(tmp_path, [("01_SYN_Zz_foil_calib_075", scans, {})])
    r = isaac(run_process(bdir, source_root=root))
    assert "post_edge_not_at_1" not in r["qc"]["reasons"] and "post_edge_window_too_short" in r["qc"]["reasons"]
    assert r["qc"]["verdict"] == "warn" and r["qc"]["metrics"]["post_edge_span_eV"] < 50
    assert "edge position is still usable" in r["qc"]["statements"]["post_edge_window_too_short"]
