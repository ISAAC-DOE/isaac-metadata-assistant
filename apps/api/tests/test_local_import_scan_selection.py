"""Scan selection (``isaac.xas.scan_selection_proposal.v0``) on SYNTHETIC HERFD-like scans only.

Every spectrum here is an invented arctan edge with a Gaussian white line, counted with Poisson statistics; every
name is SYN_*. No real file name or value. Rules under test (the beamline scientist's): normalised data are never
merged (each scan is normalised alone, with the series' one parameter set, only to judge it); an intensity drop alone
never excludes a scan (an edge-step change is an observation); every exclusion is a proposal, never a drop, and moves
no result id until the scientist names it in ``exclude_scans``.
"""

from __future__ import annotations

import json
import re

import pytest

np = pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")
pytest.importorskip("scipy", reason="scan selection needs scipy (a dependency of xraylarch)")

from isaac_api.local_import.processing import core as C  # noqa: E402
from isaac_api.local_import.processing import protocol as P  # noqa: E402
from isaac_api.local_import.processing import run as RUN  # noqa: E402

E0 = 4966.0  # synthetic edge (eV); invented
#: the nominal points, shaped like a HERFD gscan: 5 eV before the edge, 0.1 eV across it, 1 eV after, then a post-edge
#: of 5 eV steps reaching 284 eV above E0 (the series post-edge line from E0+100 then has a realistic lever arm)
GRID = np.concatenate([np.arange(4900.0, 4955.0, 5.0), np.arange(4955.0, 4990.0, 0.1),
                       np.arange(4990.0, 5040.0, 1.0), np.arange(5040.0, 5251.0, 5.0)])
#: the achieved (encoder) energy scatters about the nominal point, a different draw in every scan
JITTER_EV = 0.02
I0 = 1.0e5


def shape(e, *, e0=E0, shift=0.0, wl=0.8, wl_width=1.5):
    """The normalised SYN spectrum: an arctan edge plus a Gaussian white line 3 eV above the edge."""
    x = e - e0 - shift
    return 0.5 + np.arctan(x / 1.0) / np.pi + wl * np.exp(-0.5 * ((x - 3.0) / wl_width) ** 2)


def counts(seed, *, e=GRID, scale=1.0, shift=0.0, wl=0.8, extra_noise=0.0, i0_factor=None, add=None):
    """Integer SYN counts (pre-edge ~100, step ~900 at I0 = 1e5) with Poisson noise; ``extra_noise`` adds Gaussian
    noise in units of the counting noise; ``i0_factor`` scales I0 AND the counts (a beam dip mu divides out); ``add``
    adds a departure in edge-step units."""
    rng = np.random.default_rng(seed)
    e = np.sort(e + rng.normal(0, JITTER_EV, e.size))
    i0 = np.full(e.size, I0) * (i0_factor if i0_factor is not None else 1.0)
    rate = (0.001 + 0.009 * shape(e, shift=shift, wl=wl)) * scale
    if add is not None:
        rate = rate + 0.009 * scale * add
    lam = rate * i0
    n = rng.poisson(lam).astype(float)
    if extra_noise:
        n = np.clip(np.round(n + rng.normal(0, extra_noise * np.sqrt(lam + 1))), 0, None)
    return {"energy": e, "I0": np.round(i0), "vortDT": n, "spear": np.full(e.size, 500.0)}


def scan_dicts(cols_list):
    return [{"key": k, "number": k + 1, "energy": c["energy"], "mu": c["vortDT"] / c["I0"], "counts": c["vortDT"],
             "i0": c["I0"], "ring": c["spear"], "i0_nonpositive": 0, "setup": {}, "seed": 1000 + k}
            for k, c in enumerate(cols_list)]


def select(cols_list, e0=E0):
    return C.scan_selection(scan_dicts(cols_list), e0, np)


def by_number(out):
    return {s["number"]: s for s in out["scans"]}


def at(e):
    return int(np.argmin(np.abs(GRID - e)))


# --- noise -----------------------------------------------------------------------------------------------------------


def test_a_counting_noise_edge_has_an_excess_noise_factor_near_one():
    out = select([counts(s) for s in range(6)])
    F = [s["metrics"]["F_post"] for s in out["scans"]]
    assert 0.85 < float(np.median(F)) < 1.2 and all(0.6 < f < 1.5 for f in F), F
    for s in out["scans"]:
        assert s["metrics"]["noise_model"] == "counting_statistics"
        assert s["proposal"] == C.PROPOSAL_INCLUDE  # (a shape said below the merge noise is still an include)


def test_injected_noise_is_excess_noise_and_a_look():
    cols = [counts(s) for s in range(5)] + [counts(99, extra_noise=3.0)]
    out = by_number(select(cols))
    noisy = out[6]
    assert noisy["metrics"]["F_post"] > C.SEL_EXCESS_NOISE_LOOK
    assert "excess_noise" in noisy["reasons"] and noisy["proposal"] != C.PROPOSAL_INCLUDE
    assert all("excess_noise" not in out[k]["reasons"] for k in range(1, 6))


def test_a_signal_that_is_not_counts_gets_no_excess_noise_factor():
    assert C.counting_noise(np.array([1.5, 2.0]), np.array([10.0, 10.0]), np) is None
    assert C.counting_noise(np.array([1.0, 2.0]), np.array([10.0, 10.0]), np) is not None
    cols = [counts(s) for s in range(4)]
    dicts = scan_dicts(cols)
    for d in dicts:
        d["counts"] = d["counts"] * 1.0001  # a float signal (e.g. dead-time corrected)
    out = C.scan_selection(dicts, E0, np)
    assert {s["metrics"]["noise_model"] for s in out["scans"]} == {"measured_scatter"}
    assert all(s["metrics"]["F_post"] is None for s in out["scans"])


# --- an intensity change is an observation, never a reason -------------------------------------------------------------


def test_a_60_percent_step_loss_with_the_same_shape_includes_every_scan_and_is_only_observed():
    scales = np.linspace(1.0, 0.4, 8)
    out = select([counts(10 + k, scale=float(sc)) for k, sc in enumerate(scales)])
    assert [s["proposal"] for s in out["scans"]] == [C.PROPOSAL_INCLUDE] * 8
    assert out["evolving_metrics"] == [] and out["stable_window"] is None
    ch = out["edge_step_change"]["relative"]
    assert -0.65 < ch < -0.55
    [obs] = out["group_observations"]
    assert re.search(r"edge step fell (5[5-9]|6[0-5])% from scan 1 to scan 8", obs), obs
    assert "possible dissolution or detachment" in obs
    assert "Not a reason to leave a scan out" in obs


# --- trend, change point and the stable window ----------------------------------------------------------------------


def test_a_0p6_eV_lead_in_gives_the_stable_window():
    cols = [counts(20 + k, shift=0.6 if k < 2 else 0.0) for k in range(9)]
    out = select(cols)
    assert out["stable_window"] == [3, 4, 5, 6, 7, 8, 9]
    assert "delta_eV" in out["evolving_metrics"] or "wl_e_eV" in out["evolving_metrics"]
    got = by_number(out)
    for k in (1, 2):
        assert got[k]["proposal"] == C.PROPOSAL_EXCLUDE and "before_stable_window" in got[k]["reasons"]
    for k in range(3, 10):
        assert got[k]["proposal"] == C.PROPOSAL_INCLUDE, (k, got[k]["reasons"])


def test_a_drift_under_the_floor_is_not_flagged():
    cols = [counts(30 + k, shift=0.1 * k / 7) for k in range(8)]  # 0.1 eV in all: under the 0.15 eV floor
    out = select(cols)
    assert out["evolving_metrics"] == [] and out["stable_window"] is None
    assert [s["proposal"] for s in out["scans"]] == [C.PROPOSAL_INCLUDE] * 8


def _coarse_grid(step):
    return np.concatenate([np.arange(4900.0, 4955.0, 5.0), np.arange(4955.0, 4990.0, step),
                           np.arange(4990.0, 5040.0, 1.0), np.arange(5040.0, 5251.0, 5.0)])


@pytest.mark.parametrize("step", [0.35, 0.5])
def test_identical_scans_on_a_coarse_grid_are_never_said_shifted(step):
    """Review HIGH 3: the shift fit favours fractional shifts (up to ~0.4 of the point spacing); a shift, or a change
    of shift, under the points' resolution is never said."""
    grid = _coarse_grid(step)
    assert C.shift_resolution(grid, E0, np) == pytest.approx(step, rel=0.05)
    said = []
    for g in range(12):
        out = C.scan_selection(scan_dicts([counts(1000 * g + k, e=grid) for k in range(8)]), E0, np)
        assert out["evolving_metrics"] == [], (g, out["change_point"])
        said += [r for s in out["scans"] for r in s["reasons"]]
        assert all(s["proposal"] == C.PROPOSAL_INCLUDE for s in out["scans"]), g
    assert "energy_shifted" not in said


def test_many_independent_stable_groups_almost_never_evolve():
    """Review LOW 10: 100 independent stable groups, in time order: at most 1 % is said to evolve."""
    flagged = 0
    for g in range(100):
        out = select([counts(5000 + 10 * g + k) for k in range(6)])
        flagged += bool(out["evolving_metrics"])
    assert flagged <= 1, flagged


def test_a_four_scan_step_at_start():
    """Four scans: a large step at the start (1.5 eV) is a change of state with a stable window; a 0.6 eV one is under
    what the step test can call significant with 4 scans, and the scan is still said (energy_shifted), never silently
    included."""
    big = select([counts(140 + k, shift=1.5 if k == 0 else 0.0) for k in range(4)])
    assert big["stable_window"] == [2, 3, 4], (big["change_point"], big["evolving_metrics"])
    got = by_number(big)
    assert got[1]["proposal"] == C.PROPOSAL_EXCLUDE and "before_stable_window" in got[1]["reasons"]
    assert all(got[k]["proposal"] == C.PROPOSAL_INCLUDE for k in (2, 3, 4))
    small = by_number(select([counts(140 + k, shift=0.6 if k == 0 else 0.0) for k in range(4)]))
    assert small[1]["proposal"] == C.PROPOSAL_LOOK and "energy_shifted" in small[1]["reasons"]


def test_random_order_false_positives_are_at_most_one_percent():
    rng = np.random.default_rng(7)
    flagged = trials = 0
    for g in range(6):
        out = select([counts(100 * g + k, wl=0.8 + 0.01 * rng.normal()) for k in range(8)])
        shape_ok = [{"m": s["metrics"]} for s in out["scans"] if "delta_eV" in s["metrics"]]
        assert len(shape_ok) == 8 and out["evolving_metrics"] == []
        for _ in range(50):
            order = rng.permutation(len(shape_ok))
            evo, _, _ = C.detect_evolution([shape_ok[i] for i in order], np)
            flagged += bool(evo)
            trials += 1
    assert flagged / trials <= 0.01, (flagged, trials)


# --- artifacts --------------------------------------------------------------------------------------------------------


def _with(add_at, amount, width=1):
    add = np.zeros(GRID.size)
    i = at(add_at)
    add[i:i + width] = amount
    return add


def test_a_spike_is_an_artifact_to_look_at():
    cols = [counts(40 + k) for k in range(5)] + [counts(49, add=_with(E0 + 30, 0.6))]
    got = by_number(select(cols))
    s6 = got[6]
    arts = [a for a in s6["metrics"]["artifacts"] if a["kind"] == "spike"]
    assert len(arts) == 1 and arts[0]["points"] == 1 and arts[0]["in_xanes"]
    assert "artifact_spike" in s6["reasons"] and s6["proposal"] == C.PROPOSAL_LOOK
    assert all(got[k]["proposal"] == C.PROPOSAL_INCLUDE for k in range(1, 6))


def test_a_three_point_bump_is_a_diffraction_peak():
    cols = [counts(50 + k) for k in range(5)] + [counts(59, add=_with(E0 + 45, 0.5, width=3))]
    s6 = by_number(select(cols))[6]
    arts = [a for a in s6["metrics"]["artifacts"] if a["kind"] == "diffraction_peak"]
    assert len(arts) == 1 and arts[0]["points"] == 3 and arts[0]["amplitude_norm"] > 0
    assert "artifact_diffraction_peak" in s6["reasons"]


def _dip(to):
    f = np.ones(GRID.size)
    i = at(E0 + 60)
    f[i:i + 5] = to
    return f


def test_an_i0_dip_to_40_percent_is_a_beam_drop_to_look_at():
    cols = [counts(60 + k) for k in range(5)] + [counts(69, i0_factor=_dip(0.4))]
    s6 = by_number(select(cols))[6]
    [a] = [a for a in s6["metrics"]["artifacts"] if a["kind"] == "beam_drop_divided_out"]
    assert a["min_i0_fraction"] == pytest.approx(0.4, abs=0.03)
    assert "beam_drop" in s6["reasons"] and s6["proposal"] == C.PROPOSAL_LOOK


def test_an_i0_dip_to_80_percent_is_said_and_included():
    cols = [counts(70 + k) for k in range(5)] + [counts(79, i0_factor=_dip(0.8))]
    s6 = by_number(select(cols))[6]
    [a] = [a for a in s6["metrics"]["artifacts"] if a["kind"] == "beam_drop_divided_out"]
    assert a["min_i0_fraction"] == pytest.approx(0.8, abs=0.03)
    assert "beam_dip_divided_out" in s6["reasons"] and s6["proposal"] == C.PROPOSAL_INCLUDE


# --- completeness, few scans, merge SNR --------------------------------------------------------------------------------


def test_an_aborted_scan_is_proposed_for_leaving_out():
    short = {k: v[:at(E0 + 40)] for k, v in counts(89).items()}
    got = by_number(select([counts(80 + k) for k in range(4)] + [short]))
    assert got[5]["proposal"] == C.PROPOSAL_EXCLUDE and got[5]["reasons"] == ["incomplete_scan"]
    assert all(got[k]["proposal"] == C.PROPOSAL_INCLUDE for k in range(1, 5))


def test_a_group_whose_scans_all_stop_before_the_series_window_is_not_judged():
    """A XANES-only (or calibration) design: no scan reaches E0+150, so none is proposed, never all of them."""
    short = [{k: v[:at(E0 + 120)] for k, v in counts(130 + k).items()} for k in range(4)]
    out = select(short)
    assert out["status"] == "not_evaluated" and "nothing is proposed" in out["detail"]
    assert {s["proposal"] for s in out["scans"]} == {C.PROPOSAL_NOT_EVALUATED}
    assert {tuple(s["reasons"]) for s in out["scans"]} == {("series_window_not_reached",)}


def test_two_scans_that_disagree_are_both_to_look_at_and_two_that_agree_are_included():
    agree = select([counts(90), counts(91)])
    assert [s["proposal"] for s in agree["scans"]] == [C.PROPOSAL_INCLUDE] * 2
    differ = select([counts(92), counts(93, shift=1.0)])
    assert [s["reasons"] for s in differ["scans"]] == [["two_scans_disagree"]] * 2
    assert {s["proposal"] for s in differ["scans"]} == {C.PROPOSAL_LOOK}


def test_three_scans_the_odd_one_and_a_change():
    odd = by_number(select([counts(94), counts(95, shift=1.0), counts(96)]))
    assert odd[2]["reasons"] == ["odd_one_of_three"] and odd[2]["proposal"] == C.PROPOSAL_LOOK
    assert odd[1]["proposal"] == odd[3]["proposal"] == C.PROPOSAL_INCLUDE
    change = select([counts(97), counts(98, shift=0.7), counts(99, shift=1.4)])
    assert all("three_scans_change" in s["reasons"] for s in change["scans"])


def test_a_scan_that_lowers_the_merged_snr_is_a_look_never_an_exclusion():
    cols = [counts(110 + k) for k in range(5)] + [counts(119, extra_noise=6.0)]
    out = select(cols)
    s6 = by_number(out)[6]
    vs = s6["metrics"]["vs_stable"]
    assert vs["merge_snr_with"] < vs["merge_snr_without"] * C.SEL_SNR_LOWERED
    assert "lowers_merge_snr" in s6["reasons"] and s6["proposal"] == C.PROPOSAL_LOOK
    said = s6["said"][s6["reasons"].index("lowers_merge_snr")]
    assert "weaker" in said and "not wrong" in said


def test_a_30_percent_step_with_fixed_noise_and_the_same_shape_is_never_proposed_for_leaving_out():
    """Review HIGH 2: an intensity drop alone never excludes a scan (fixed, non-counting noise: the weak scan lowers the
    raw merge's SNR)."""
    rng = np.random.default_rng(3)
    scans = []
    for k, scale in enumerate([1, 1, 1, 1, 1, 0.3]):
        e = np.sort(GRID + rng.normal(0, JITTER_EV, GRID.size))
        mu = (0.1 + 0.9 * shape(e)) * scale + rng.normal(0, 0.01, GRID.size)
        scans.append({"key": k, "number": k + 1, "energy": e, "mu": mu, "counts": None, "i0": None, "ring": None,
                      "i0_nonpositive": 0, "setup": {}, "seed": k})
    out = C.scan_selection(scans, E0, np)
    assert all(s["proposal"] != C.PROPOSAL_EXCLUDE for s in out["scans"])
    weak = by_number(out)[6]
    assert weak["metrics"]["noise_model"] == "measured_scatter"
    assert weak["proposal"] in (C.PROPOSAL_INCLUDE, C.PROPOSAL_LOOK)


# --- transmission (review HIGH 1) ------------------------------------------------------------------------------------


def _transmission(seed, *, integer=True, i0=1.0e6):
    rng = np.random.default_rng(seed)
    e = np.sort(GRID + rng.normal(0, JITTER_EV, GRID.size))
    mu = 0.3 + 1.5 * shape(e)
    I0 = rng.poisson(np.full(e.size, i0)).astype(float)
    It = rng.poisson(I0 * np.exp(-mu)).astype(float)
    if not integer:
        I0, It = I0 * 1.000001e-9, It * 1.000001e-9  # currents, not counts
    return {"key": seed, "number": seed + 1, "energy": e, "mu": np.log(I0 / It), "counts": It, "i0": I0,
            "ring": None, "i0_nonpositive": 0, "setup": {}, "seed": seed, "mode": "transmission"}


def test_perfect_poisson_transmission_scans_have_an_excess_noise_factor_near_one():
    out = C.scan_selection([_transmission(k) for k in range(6)], E0, np)
    F = [s["metrics"]["F_post"] for s in out["scans"]]
    assert {s["metrics"]["noise_model"] for s in out["scans"]} == {"counting_statistics"}
    assert 0.8 < float(np.median(F)) < 1.25 and all(0.6 < f < 1.5 for f in F), F
    assert all("excess_noise" not in s["reasons"] for s in out["scans"])
    assert all(s["proposal"] == C.PROPOSAL_INCLUDE for s in out["scans"])


def test_transmission_counting_noise_is_the_log_ratio_formula_and_only_for_counts():
    it, i0 = np.array([100.0, 400.0]), np.array([1.0e4, 1.0e4])
    got = C.counting_noise(it, i0, np, mode="transmission")
    assert got == pytest.approx(np.sqrt(1 / it + 1 / i0))
    assert C.counting_noise(it, i0 + 0.5, np, mode="transmission") is None  # I0 is not counts
    assert C.counting_noise(it, i0, np, mode="signal_only") is None
    out = C.scan_selection([_transmission(k, integer=False) for k in range(4)], E0, np)
    assert {s["metrics"]["noise_model"] for s in out["scans"]} == {"measured_scatter"}


def test_the_output_is_json_safe():
    out = select([counts(120 + k) for k in range(4)])
    json.dumps(out, allow_nan=False)


# --- the pipeline: files, ids, the hint, approvals ---------------------------------------------------------------------


def _proc():
    import test_local_import_processing as T

    return T


def spec(cols, *, command="gscan energy 4900 4955 5 4990 0.1 5040 1 5250 5 0.5", setup="emiss=9000.0 filter=10"):
    names = list(cols)
    lines = ["#F SYN", "#C SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value is invented.",
             f"#S 1  {command}", f"#P0 dummy0=4 {setup} SYNx=1", "#L " + "  ".join(names)]
    for row in zip(*(cols[n] for n in names)):
        lines.append(" ".join(f"{v:.6f}" for v in row))
    return "\n".join(lines) + "\n"


def _case(tmp_path, groups):
    T = _proc()
    return T.make_case(tmp_path, [(stem, texts, {"sample_name": stem.split("_")[-1]}) for stem, texts in groups])


def _two_groups(tmp_path):
    aborted = {k: v[:25] for k, v in counts(209).items()}  # 25 points: in the merge (>= 20), stops below the edge
    return _case(tmp_path, [("01_SYN_ZZ1", [spec(counts(200 + k)) for k in range(4)] + [spec(aborted)]),
                            ("02_SYN_ZZ2", [spec(counts(300 + k)) for k in range(4)])])


def _by_stem(payload):
    out = {}
    for r in payload["processing_results"]:
        if r["source"] == "isaac_protocol":
            out[r["inputs"][0]["relative_path"].split("/")[0]] = r
    return out


def test_a_proposal_is_attached_after_the_run_id_and_said(tmp_path):
    T = _proc()
    bdir, root, _ = _two_groups(tmp_path)
    payload = T.run_process(bdir, source_root=root)
    assert payload["format_version"] == "0.3.0"
    [series] = payload[RUN.SCAN_SERIES_KEY]["series"]
    assert series["command"] == "gscan energy" and abs(series["e0_eV"] - E0) < 2.0
    got = _by_stem(payload)
    a, b = got["01_SYN_ZZ1_dir"], got["02_SYN_ZZ2_dir"]
    sel = a[RUN.SCAN_SELECTION_KEY]
    assert sel["rule_id"] == C.SCAN_SELECTION_RULE_ID and sel["e0_basis"] == "series"
    assert sel["exclude_proposed"] == ["01_SYN_ZZ1_005.dat"] and sel["open"]
    row = next(x for x in sel["scans"] if x["file"] == "01_SYN_ZZ1_005.dat")
    assert row["proposal"] == C.PROPOSAL_EXCLUDE and row["reasons"] == ["incomplete_scan"]
    assert RUN.SCAN_SELECTION_FLAG in a["review_flags"] and RUN.SCAN_SELECTION_FLAG not in b["review_flags"]
    said = a["qc"]["statements"]["scan_selection"]
    assert "nothing was left out of this merge" in said and "the merge stays raw mu" in said
    assert '{"exclude_scans": {"' + a["group_id"] + '": ["01_SYN_ZZ1_005.dat"]}}' in said
    assert T.step(a, "merge")["outcome"]["n_scans"] == 5  # a proposal, never a drop
    assert C.SCAN_SELECTION_RULE_ID in a["rule_versions"]["rule_ids"]
    for f in a["outputs"]["files"]:  # never in a hashed file
        if f["role"] in ("qc", "params"):
            assert "scan_selection" not in (bdir / f["relative_path"]).read_text()


def test_merged_csv_and_run_id_are_byte_identical_with_the_feature_on(tmp_path, monkeypatch):
    T = _proc()
    on_dir, off_dir = tmp_path / "on", tmp_path / "off"
    on_dir.mkdir()
    off_dir.mkdir()
    b_on, root_on, _ = _two_groups(on_dir)
    b_off, root_off, _ = _two_groups(off_dir)
    on = _by_stem(T.run_process(b_on, source_root=root_on))
    monkeypatch.setattr(RUN, "SCAN_SELECTION_ENABLED", False)
    off_payload = T.run_process(b_off, source_root=root_off)
    off = _by_stem(off_payload)
    assert RUN.SCAN_SERIES_KEY not in off_payload
    assert on.keys() == off.keys()
    for k in on:
        assert on[k]["run_id"] == off[k]["run_id"] and on[k]["result_id"] == off[k]["result_id"]
        assert RUN.SCAN_SELECTION_KEY in on[k] and RUN.SCAN_SELECTION_KEY not in off[k]
        files_on = {f["role"]: f for f in on[k]["outputs"]["files"]}
        files_off = {f["role"]: f for f in off[k]["outputs"]["files"]}
        for role in ("merged", "normalized", "qc", "params"):
            assert files_on[role]["sha256"] == files_off[role]["sha256"]
            assert (b_on / files_on[role]["relative_path"]).read_bytes() == (b_off / files_off[role]["relative_path"]).read_bytes()


def test_the_hint_s_exclude_scans_moves_exactly_one_id(tmp_path):
    T = _proc()
    bdir, root, _ = _two_groups(tmp_path)
    first = _by_stem(T.run_process(bdir, source_root=root))
    said = first["01_SYN_ZZ1_dir"]["qc"]["statements"]["scan_selection"]
    snippet = json.loads(re.search(r'(\{"exclude_scans": .*?\]\}\})', said).group(1))
    again = _by_stem(T.run_process(bdir, source_root=root, params=snippet))
    moved = [k for k in first if first[k]["result_id"] != again[k]["result_id"]]
    assert moved == ["01_SYN_ZZ1_dir"]
    a = again["01_SYN_ZZ1_dir"]
    assert T.step(a, "merge")["outcome"]["n_scans"] == 4
    row = next(x for x in a[RUN.SCAN_SELECTION_KEY]["scans"] if x["file"] == "01_SYN_ZZ1_005.dat")
    assert row["proposal"] == RUN.LEFT_OUT and row["reasons"] == [RUN.EXCLUDED_REASON]
    assert not a[RUN.SCAN_SELECTION_KEY]["open"] and RUN.SCAN_SELECTION_FLAG not in a["review_flags"]
    assert a[RUN.SCAN_SELECTION_KEY]["already_excluded"] == ["01_SYN_ZZ1_005.dat"]


def test_motor_scans_are_never_proposed(tmp_path):
    T = _proc()
    assert not RUN._is_energy_scan(("ascan", "Sz")) and not RUN._is_energy_scan(("a2scan", "Sx"))
    assert RUN._is_energy_scan(("gscan", "energy")) and RUN._is_energy_scan(("ascan", "energy"))
    assert RUN._is_energy_scan(None)
    motor = spec(counts(409), command="ascan  mono 4900 5250  237 0.5")  # columns like an energy scan, a motor scan
    bdir, root, _ = _case(tmp_path, [("01_SYN_ZZ1", [spec(counts(400 + k)) for k in range(4)] + [motor])])
    r = _by_stem(T.run_process(bdir, source_root=root))["01_SYN_ZZ1_dir"]
    sel = r[RUN.SCAN_SELECTION_KEY]
    row = next(x for x in sel["scans"] if x["file"] == "01_SYN_ZZ1_005.dat")
    assert row["proposal"] == RUN.NOT_EVALUATED and row["reasons"] == ["not_an_energy_scan"]
    assert "01_SYN_ZZ1_005.dat" not in sel["exclude_proposed"] + sel["needs_look"]
    assert T.step(r, "merge")["outcome"]["n_scans"] == 5  # said, never dropped


def test_a_setup_that_differs_is_a_look():
    dicts = scan_dicts([counts(500 + k) for k in range(5)])
    for d in dicts:
        d["setup"] = {"emiss": 9000.0, "filter": 10.0}
    dicts[4]["setup"] = {"emiss": 9000.0, "filter": 20.0}
    got = by_number(C.scan_selection(dicts, E0, np))
    assert "setup_differs_filter" in got[5]["reasons"] and got[5]["proposal"] != C.PROPOSAL_INCLUDE
    assert all("setup_differs_filter" not in got[k]["reasons"] for k in range(1, 5))
    assert RUN._header_setup(["#P0 dummy0=4 energy=11.0 emiss=9175.4 filter=10 Sx=1"]) == {"emiss": 9175.4, "filter": 10.0}


def test_the_rule_is_named_outside_the_hashed_params():
    ids = P.RULE_VERSIONS_SINCE_PROTOCOL_VERSION["rule_ids"]
    assert C.SCAN_SELECTION_RULE_ID in ids and ids == sorted(ids)
    flat = json.dumps(P.DEFAULT_PARAMS)
    assert "scan_selection" not in flat and "SEL_" not in flat


def _imported(tmp_path):
    """Two SYN runs, each an acquisition file of ``#S`` blocks beside its per-scan files, imported, grouped and
    processed through the bundle commands; the first run's last scan stopped after 25 points."""
    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M

    root = tmp_path / "SYN_beamtime"
    runs = (("01_SYN_ZZ1", [counts(200 + k) for k in range(4)] + [{k: v[:25] for k, v in counts(209).items()}]),
            ("02_SYN_ZZ2", [counts(300 + k) for k in range(4)]))
    for stem, cols in runs:
        d = root / f"{stem}_dir"
        d.mkdir(parents=True)
        blocks = []
        for j, c in enumerate(cols, start=1):
            text = spec(c).replace("#S 1 ", f"#S {j} ")
            (d / f"{stem}_{j:03d}.dat").write_text(text)
            blocks.append("\n".join(ln for ln in text.splitlines() if not ln.startswith("#F")))
        (root / stem).write_text(f"#F {stem}\n#E 1\n\n" + "\n\n".join(blocks) + "\n")
    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    M.group(out)
    M.process(out, source=str(root))
    return out


def test_a_bulk_approval_is_refused_while_proposals_are_open_and_one_approval_records_them(tmp_path, capsys):
    from isaac_api.local_import import mutations as M
    from test_local_import_records import BY

    bdir = _imported(tmp_path)
    capsys.readouterr()
    isaac = {r["inputs"][0]["relative_path"]: r for r in M.load(bdir)["processing_results"]
             if r["source"] == "isaac_protocol" and len(r["inputs"]) > 1}
    a, other = isaac["01_SYN_ZZ1"], isaac["02_SYN_ZZ2"]
    assert a[RUN.SCAN_SELECTION_KEY]["exclude_proposed"] == ["01_SYN_ZZ1#5"]  # one scan of a multi-scan file
    problem = M.bulk_approve_problem(a)
    assert problem and "open scan-selection proposals" in problem and '"01_SYN_ZZ1#5"' in problem
    assert M.bulk_approve_problem(other) is None
    ids = [M.B.processing_id(a), M.B.processing_id(other)]
    with pytest.raises(M.MutationRefused, match="open scan-selection proposals"):
        M.decide(bdir, target_ids=ids, decision="approve", value=None, qc_status="valid", **BY)
    out = M.decide(bdir, target_ids=[ids[0]], decision="approve", value=None, qc_status="valid", **BY)
    assert ids[0] in out["recorded"]
    note = next(d for d in M.load(bdir)["scientist_decisions"] if d["target"]["id"] == ids[0])["note"]
    assert "scan-selection proposals still open" in note and "(incomplete_scan)" in note
    assert M.scan_selection_note(other) is None


# --- guards and the series pass (review M4, M5) ------------------------------------------------------------------------


def test_a_failing_series_pass_is_recorded_and_never_fails_processing(tmp_path, monkeypatch):
    T = _proc()
    bdir, root, _ = _two_groups(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("SYN injected failure")

    monkeypatch.setattr(RUN, "scan_selection_series", boom)
    payload = T.run_process(bdir, source_root=root)
    assert "SYN injected failure" in payload[RUN.SCAN_SERIES_KEY]["error"]
    for r in _by_stem(payload).values():
        sel = r[RUN.SCAN_SELECTION_KEY]
        assert sel["status"] == "not_evaluated" and "series pass failed" in sel["detail"]
        assert RUN.SCAN_SELECTION_FLAG not in r["review_flags"] and r["qc"]["verdict"] in ("pass", "warn")


def test_a_failing_proposal_or_sentence_is_recorded_and_never_fails_processing(tmp_path, monkeypatch):
    T = _proc()
    bdir, root, _ = _two_groups(tmp_path)
    clean = {k: r["result_id"] for k, r in _by_stem(T.run_process(bdir, source_root=root)).items()}

    def boom(*a, **k):
        raise ValueError("SYN injected failure")

    for target, mod in (("scan_selection", C), ("_scan_selection_statement", RUN)):
        with monkeypatch.context() as m:
            m.setattr(mod, target, boom)
            got = _by_stem(T.run_process(bdir, source_root=root))
        for k, r in got.items():
            sel = r[RUN.SCAN_SELECTION_KEY]
            assert sel["status"] == "not_evaluated" and "SYN injected failure" in sel["detail"], target
            assert r["result_id"] == clean[k] and RUN.SCAN_SELECTION_FLAG not in r["review_flags"]


def test_the_series_pass_hashes_no_file_again_and_a_group_run_reuses_the_stored_series(tmp_path, monkeypatch):
    T = _proc()
    calls: dict = {}
    real = RUN.sha256_file

    def counting(path):
        calls[str(path)] = calls.get(str(path), 0) + 1
        return real(path)

    monkeypatch.setattr(RUN, "sha256_file", counting)
    (tmp_path / "off").mkdir()
    b_off, r_off, _ = _two_groups(tmp_path / "off")
    with monkeypatch.context() as m:
        m.setattr(RUN, "SCAN_SELECTION_ENABLED", False)
        T.run_process(b_off, source_root=r_off)
    off = {k.replace(str(r_off), ""): v for k, v in calls.items() if k.startswith(str(r_off))}
    calls.clear()
    bdir, root, _ = _two_groups(tmp_path)
    first = T.run_process(bdir, source_root=root)
    on = {k.replace(str(root), ""): v for k, v in calls.items() if k.startswith(str(root))}
    assert on and on == off  # each source file hashed as often as without the feature: once by the merge's own read
    assert first[RUN.SCAN_SERIES_KEY]["reused"] is False
    gid = _by_stem(first)["01_SYN_ZZ1_dir"]["group_id"]
    calls.clear()
    again = T.run_process(bdir, source_root=root, group_ids=[gid])
    ser = again[RUN.SCAN_SERIES_KEY]
    assert ser["reused"] is True and "reused" in ser["statement"]
    assert not any("02_SYN_ZZ2" in k for k in calls)  # no other group's file was read for the series
    a0, a1 = _by_stem(first)["01_SYN_ZZ1_dir"], _by_stem(again)["01_SYN_ZZ1_dir"]
    assert a1["result_id"] == a0["result_id"]
    assert a1[RUN.SCAN_SELECTION_KEY]["e0_series_eV"] == a0[RUN.SCAN_SELECTION_KEY]["e0_series_eV"]
    assert a1[RUN.SCAN_SELECTION_KEY]["exclude_proposed"] == a0[RUN.SCAN_SELECTION_KEY]["exclude_proposed"]


def test_the_series_is_named_as_a_scan_template_series(tmp_path):
    T = _proc()
    bdir, root, _ = _two_groups(tmp_path)
    payload = T.run_process(bdir, source_root=root)
    assert payload[RUN.SCAN_SERIES_KEY]["meaning"] == RUN.SERIES_MEANING
    a = _by_stem(payload)["01_SYN_ZZ1_dir"]
    assert a[RUN.SCAN_SELECTION_KEY]["series_meaning"] == RUN.SERIES_MEANING
    assert "scan-template series (all samples measured with the same scan command)" in a["qc"]["statements"]["scan_selection"]
