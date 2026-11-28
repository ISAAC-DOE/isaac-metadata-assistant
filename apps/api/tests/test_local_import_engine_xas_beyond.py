"""isaac.xas.v1 1.1.0 (28 Nov 2026): the fixes and improvements measured on six real beamtimes (N1-N7, I1-I6).

SYNTHETIC scans only (the helpers of test_local_import_engine_xas: invented logistic edges at the tabulated Ir L3 energy,
an invented I0 glitch, every header SYNTHETIC FIXTURE; samples ZZ1..., the scientist Quillfeather). Rules under test:
a standard's measurement mode is measured, never taken from its role (N1); no raw exception text reaches a record
(N7); a glitch whose shifts do not track the sample is not used, and no record then claims an alignment (N2); the
beamtime zero never comes from a coarse-grid group (N3); a joint, sign-consistent dose test over the spots (N4); a
judged dose check that found nothing says so (N6); the ratio-shape window starts before the white line, and a spot
split by the shape screen is judged as a whole (N5); the verification statement is in every processed record.
"""

from __future__ import annotations

import json

import pytest

np = pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")
pytest.importorskip("scipy", reason="the xas-analysis engine needs scipy")
pytest.importorskip("yaml", reason="the xas-analysis engine needs pyyaml (the optional `processing` extra)")

import test_local_import_engine_xas as T  # noqa: E402

from isaac_api.local_import.processing import core as C  # noqa: E402
from isaac_api.local_import.processing import engine_xas as EX  # noqa: E402

BY = {"by": "R. Quillfeather (SYNTHETIC)", "orcid": None}


@pytest.fixture(autouse=True)
def _engine_on(monkeypatch):
    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v1")


def _payload(bdir):
    return json.loads((bdir / "processing" / "processing_results.json").read_text())


# --- N1: a standard's mode is measured -------------------------------------------------------------------------------


def test_a_standard_measured_in_fluorescence_is_reduced_in_fluorescence_not_as_transmission(tmp_path):
    """A standard (role reference, a `std` token) whose I1 is a positive intensity, so its channel choice takes
    ln(I0/I1) first, but whose ln(I0/I1) has no edge while its fluorescence does: the engine's own mode test reads it
    as fluorescence, and it is reduced in fluorescence (v0's channel choice reduced it as a flat ln(I0/I1))."""
    std = [T.scan_cols(70 + k, d=d) for k, d in enumerate([0.02, -0.01, 0.03])]     # I1 = 3 counts, flat: no edge
    bdir, _ = T.imported(tmp_path, T._two_groups() + [("03_SYN_ZZ3_std_005", 13, std)])
    r = T.by_run(T.v1_results(bdir), "03_SYN_ZZ3_std")
    mm = r["measurement_mode"]
    assert mm["mode"] == "fluorescence", mm
    assert mm["standard_mode_test"]["decided"] == "fluorescence"
    assert mm["standard_mode_test"]["rule_id"] == EX.STANDARD_MODE_RULE_ID
    assert "reduced in fluorescence" in mm["statement"] and "ln(I0/I1)" in mm["statement"]
    assert r["channel_choice"]["mode"] == "fluorescence" and "vortDT" in json.dumps(r["channel_choice"])
    assert r["qc"]["verdict"] != "fail", r["qc"]
    assert 0.5 < r["outputs"]["edge_step"] / by_step(T.v1_results(bdir), "02_SYN_ZZ2") < 2.0
    assert r["group_id"] not in _payload(bdir)[EX.BEAMTIME_KEY]["transmission_standards_on_v1"]


def by_step(results, prefix):
    return T.by_run(results, prefix)["outputs"]["edge_step"]


def test_a_standard_measured_in_transmission_stays_on_ln_i0_i1_and_says_the_test(tmp_path):
    std = [T._std_cols(70 + k, d) for k, d in enumerate([0.04, -0.03, 0.06])]
    bdir, _ = T.imported(tmp_path, T._two_groups() + [("03_SYN_ZZ3_std_005", 13, std)])
    r = T.by_run(T.v1_results(bdir), "03_SYN_ZZ3_std")
    assert r["measurement_mode"]["mode"] == "transmission"
    assert "mode test" in r["measurement_mode"]["basis"], r["measurement_mode"]


def test_a_standard_whose_ln_i0_i1_steps_stays_in_transmission_even_with_a_fluorescence_edge(tmp_path):
    """Review of 28 Nov, 3: a pellet standard measured in transmission whose fluorescence channel also shows the edge,
    and whose name does not say transmission: its ln(I0/I1) steps across the edge, so it stays on transmission."""
    std = [T.scan_cols(70 + k, d=d, trans_step=0.6) for k, d in enumerate([0.04, -0.03, 0.06])]   # both edges
    bdir, _ = T.imported(tmp_path, T._two_groups() + [("03_SYN_ZZ3_std_005", 13, std)])
    r = T.by_run(T.v1_results(bdir), "03_SYN_ZZ3_std")
    assert r["measurement_mode"]["mode"] == "transmission", r["measurement_mode"]
    assert "ln(I0/I1) steps" in r["measurement_mode"]["basis"] or "mode test" in r["measurement_mode"]["basis"]


# --- N7: plain reasons ----------------------------------------------------------------------------------------------


def test_a_known_exception_becomes_a_plain_sentence_and_the_raw_text_goes_to_the_log_only(capsys):
    C.set_diagnostics(None)
    said = C.plain_error(ValueError("mback_xrs: need >= 3 pre-edge and post-edge points."), "normalisation")
    assert said.startswith("normalisation could not be completed: the merged curve has too few points")
    assert "ValueError" not in said and "mback_xrs" not in said
    assert "ValueError: mback_xrs" in capsys.readouterr().err
    other = C.plain_error(RuntimeError("ZZ9 internal"), "processing this group")
    assert "RuntimeError" not in other and "ZZ9" not in other and "processing log" in other
    assert C.plain_error(KeyError("I1"), "x") == "x could not be completed: the scan has no 'I1' column, which this step needs"
    internal = C.plain_error(KeyError("anchor_eV"), "x")        # the software's own key: never "the data have no"
    assert "software error" in internal and "anchor_eV" not in internal and "the data have no" not in internal


def test_a_missing_part_is_said_as_missing_never_as_a_missing_file_and_the_detail_goes_to_the_diagnostics(tmp_path):
    log = tmp_path / C.DIAGNOSTICS_FILE
    C.set_diagnostics(log)
    try:
        said = C.plain_error(ValueError("Offsets block not found"), "reading ZZ1")
        assert said == "reading ZZ1 could not be completed: the data have no 'Offsets block', which this step needs"
        assert "file" not in said
        assert "a file the step needs could not be found" in C.plain_error(FileNotFoundError("No such file: ZZ1"), "x")
        generic = C.plain_error(RuntimeError("ZZ9 internal"), "x")
        assert f"processing/{C.DIAGNOSTICS_FILE}" in generic and "ZZ9" not in generic
    finally:
        C.set_diagnostics(None)
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert [x["detail"] for x in lines][0] == "ValueError: Offsets block not found"
    assert lines[-1]["detail"] == "RuntimeError: ZZ9 internal"
    C.set_diagnostics(log)                                       # a new run starts the file afresh
    try:
        assert not log.exists()
    finally:
        C.set_diagnostics(None)


def test_a_normalisation_that_raises_says_why_in_plain_words(monkeypatch):
    import xas_analysis.model.mback_xrs as MB

    def boom(*a, **k):
        raise ValueError("mback_xrs: need >= 3 pre-edge and post-edge points.")

    monkeypatch.setattr(MB, "mback_xrs", boom)
    E = np.arange(11165.0, 11500.0, 1.0)
    nm = EX.normalize_once(E, np.ones(E.size), np.ones(E.size),
                           {"element": "Ir", "edge": "L3", "E_edge_eV": T.E_EDGE, "basis": "SYN"}, {}, np)
    assert "ValueError" not in nm["error"] and "too few points in the pre-edge or the post-edge" in nm["error"]


# --- N2: the glitch is checked against the sample --------------------------------------------------------------------


def _hold(seed, shifts, ds):
    recs = []
    for k, (s, d) in enumerate(zip(shifts, ds)):
        c = T.scan_cols(seed + k, d=d)
        recs.append({"E": c["absev"], "IF": c["vortDT"], "I0": c["I0"], "scan_id": f"ZZ{seed}#{k + 1}",
                     "alignment": {"ok": True, "shift_eV": s, "route": "glitch_I0"}})
    return {"scope": None, "recs": recs, "stems": [f"ZZ{seed}"], "group_id": f"rg-zz{seed}"}


def test_glitch_shifts_that_track_the_sample_are_trusted_and_ones_that_do_not_are_not():
    rng = np.random.default_rng(3)
    bt = {"edge": {"E_edge_eV": T.E_EDGE}}
    ds = [rng.uniform(-0.08, 0.08, 6) for _ in range(3)]
    tracks = {f"g{i}": _hold(100 + 10 * i, list(-d + rng.normal(0, 0.003, 6)), list(d)) for i, d in enumerate(ds)}
    chk = EX.glitch_check(bt, tracks, np)
    assert chk["trusted"] is True and chk["outcome"] == "tracks_sample", chk
    loose = {f"g{i}": _hold(200 + 10 * i, list(rng.uniform(-0.08, 0.08, 6)), [0.0] * 6) for i in range(3)}
    chk = EX.glitch_check(bt, loose, np)
    assert chk["trusted"] is False and chk["outcome"] == "does_not_track_sample", chk
    assert "so no scan is aligned on it (every shift is 0)" in chk["statement"]
    tiny = {f"g{i}": _hold(300 + 10 * i, list(rng.uniform(-0.001, 0.001, 6)), list(rng.uniform(-0.03, 0.03, 6)))
            for i in range(3)}
    assert EX.glitch_check(bt, tiny, np)["outcome"] == "too_small_to_matter"


def test_the_glitch_check_judges_only_its_own_edge_and_never_unaligns_another_edge():
    rng = np.random.default_rng(5)
    bt = {"edge": {"E_edge_eV": T.E_EDGE}}
    loose = {f"g{i}": _hold(400 + 10 * i, list(rng.uniform(-0.08, 0.08, 6)), [0.0] * 6) for i in range(3)}
    other = {"g0": T.E_EDGE, "g1": T.E_EDGE, "g2": T.E_EDGE, "zz_other": 11564.0}
    loose["zz_other"] = _hold(450, list(rng.uniform(-0.08, 0.08, 6)), [0.0] * 6)
    chk = EX.glitch_check(bt, loose, np, edge_of=other)
    assert chk["outcome"] == "not_applied_mixed_edges" and chk["trusted"] is None, chk
    assert chk["groups_at_other_edges"] == ["zz_other"] and chk["holds"] == 3


def _loose_glitch(seed, g):
    """A SYN scan whose sample sits still (no mono offset) while its I0 glitch is ``g`` eV off: the glitch does not
    track the monochromator."""
    c = T.scan_cols(seed)
    E = c["absev"]
    base = 1e5 * (1 - 0.0004 * (E - 11165))
    I0 = base * (1 - 0.06 * np.exp(-((E - T.GLITCH - g) / 0.22) ** 2))
    c["vortDT"] = c["vortDT"] * I0 / c["I0"]
    c["I0"] = I0
    return c


def test_a_glitch_that_does_not_track_the_sample_is_not_used_and_no_record_claims_an_alignment(tmp_path):
    rng = np.random.default_rng(11)
    runs = [(f"0{i + 1}_SYN_ZZ{i + 1}_060mV", 9 + i, [_loose_glitch(10 * i + k, float(rng.uniform(-0.12, 0.12)))
                                                       for k in range(5)]) for i in range(3)]
    bdir, _ = T.imported(tmp_path, runs)
    bt = _payload(bdir)[EX.BEAMTIME_KEY]
    assert bt["glitch_check"]["trusted"] is False, bt["glitch_check"]
    for r in T.v1_results(bdir):
        route = r[EX.REFERENCE_KEY]["routes"][0]
        assert route["mode"] == "none" and route.get("untrusted_glitch") is True
        assert EX.NO_REFERENCE_FLAG in r["review_flags"]
        assert r[EX.REFERENCE_KEY]["statement"].startswith("NO RELIABLE PER-SCAN ENERGY REFERENCE")
        assert all(x["shift_eV"] == 0.0 for x in r[EX.SHIFTS_KEY]["rows"])
        assert r[EX.SHIFTS_KEY]["statement"].startswith("No scan was aligned")
        cal = next(s for s in r["steps"] if s["step"] == "calibration")["outcome"]
        assert cal["alignment"]["scans_aligned"] == 0 and cal["alignment"]["statement"].startswith("No per-scan alignment")
        assert "ONE beamtime reference" not in r[EX.SHIFTS_KEY]["statement"]


def test_a_glitch_that_tracks_the_mono_is_still_used(tmp_path):
    bdir, _ = T.imported(tmp_path, T._two_groups())
    bt = _payload(bdir)[EX.BEAMTIME_KEY]
    assert bt["glitch_check"]["trusted"] is True and bt["routes"][0]["route"]["mode"] == "glitch_I0"


def _one_foil_beamtime(glitch):
    return [("01_SYN_Irfoil_calib_b", 8, [T._foil_scan(2, 0.0)]),
            ("02_SYN_ZZ2_060mV", 9, [T.scan_cols(20 + k, glitch=glitch, d=d) for k, d in enumerate(T.REF_D)]),
            ("03_SYN_ZZ3_060mV", 12, [T.scan_cols(30 + k, glitch=glitch, d=d) for k, d in enumerate(T.SMP_D)])]


def test_one_usable_foil_scan_and_no_glitch_aligns_nothing_and_says_why(tmp_path):
    bdir, _ = T.imported(tmp_path, _one_foil_beamtime(glitch=False))
    bt = _payload(bdir)[EX.BEAMTIME_KEY]
    assert bt["calibration"]["mode"] == "foil_timeline", bt["calibration"]
    route = bt["routes"][0]
    assert route["route"]["mode"] == "none" and route["one_foil_scan"] is True
    r = T.by_run(T.v1_results(bdir), "03_SYN_ZZ3")
    assert r[EX.REFERENCE_KEY]["statement"].startswith("NO RELIABLE PER-SCAN ENERGY REFERENCE: Only one usable foil")
    assert all(x["shift_eV"] == 0.0 for x in r[EX.SHIFTS_KEY]["rows"]) and EX.NO_REFERENCE_FLAG in r["review_flags"]


def test_one_usable_foil_scan_never_beats_a_glitch_the_scans_carry(tmp_path, monkeypatch):
    """The survey proposes a timeline from one foil scan (as on the real S K beamtime, where it saw no glitch): one
    point cannot measure drift, and most scans carry the glitch, so the glitch is used (review of 28 Nov, 6: deleting
    that rule must fail a test)."""
    import xas_analysis.survey as SV

    real = SV.survey_files

    def foil_first(files, docs, folder=""):
        rep = real(files, docs, folder)
        foil = next((f for f in files if f.role == "foil"), None)
        if foil is not None:
            rep.setdefault("recommendation", {})["calibration"] = {
                "mode": "foil_timeline", "method": "shape", "foils": [{"spec": foil.name, "ref_signal": "ln(I0/I1)"}],
                "foil_window_eV": [T.E_EDGE - 6, T.E_EDGE + 6], "shape_window_eV": [T.E_EDGE - 8, T.E_EDGE + 24],
                "max_shift_eV": 2.0}
        return rep

    monkeypatch.setattr(SV, "survey_files", foil_first)
    bdir, _ = T.imported(tmp_path, _one_foil_beamtime(glitch=True))
    bt = _payload(bdir)[EX.BEAMTIME_KEY]
    assert bt["routes"][0]["route"]["mode"] == "glitch_I0", bt["routes"][0]
    assert any("1 usable foil scan(s): one point cannot measure" in x for x in bt["consensus_said"])
    r = T.by_run(T.v1_results(bdir), "03_SYN_ZZ3")
    err = T._shift_errors(r, T.SMP_D, float(np.median(T.REF_D)))
    assert max(abs(e) for e in err) < 5.0, err


def test_one_foil_scan_never_claims_a_drift_alignment():
    """A foil timeline with one usable foil scan: route none, every shift 0, said (unit level on the route)."""
    info = {"route": {"mode": "none", "basis": "foil_timeline_fewer_than_two_scans"}, "anchor_eV": 0.0,
            "one_foil_scan": True, "statement": "Only one usable foil scan in this beamtime (ZZ0_foil#1, edge 4966.1 eV): "
                                                "one point cannot measure the monochromator's drift, so no scan is aligned."}
    al = EX._align_rec({"scan_id": "ZZ1#1"}, [info], {}, {}, np)
    assert al["unreferenced"] and al["shift_eV"] == 0.0
    view = EX._reference_view({"routes": [info]}, [])
    assert view["statement"].startswith("NO RELIABLE PER-SCAN ENERGY REFERENCE: Only one usable foil scan")


# --- N3: the beamtime zero ------------------------------------------------------------------------------------------


def _coarse(c):
    """The same SYN scan on a coarse grid at the glitch (every other point of the 0.25 eV region)."""
    E = c["absev"]
    k = np.arange(E.size)
    keep = ~((E >= 11205) & (E < 11240)) | (k % 2 == 0)
    return {n: v[keep] for n, v in c.items()}


def test_the_beamtime_zero_never_comes_from_a_coarse_grid_group(tmp_path):
    ref = [_coarse(T.scan_cols(10 + k, d=d)) for k, d in enumerate(T.REF_D)]
    smp = [T.scan_cols(20 + k, d=d) for k, d in enumerate(T.SMP_D)]
    bdir, _ = T.imported(tmp_path, [("01_SYN_ZZ1_060mV", 9, ref), ("02_SYN_ZZ2_060mV", 11, smp)])
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    route = r[EX.REFERENCE_KEY]["routes"][0]
    zero = route["zero"]
    assert zero["rule_id"] == EX.ZERO_RULE_ID and zero["groups"] == ["02_SYN_ZZ2_060mV"], zero
    assert [x["name"] for x in zero["coarse_groups_skipped"]] == ["01_SYN_ZZ1_060mV"]
    assert route["reference_name"] == "02_SYN_ZZ2_060mV" and "coarse grid" in route["reference_moved"]
    # the zero is the median of ZZ2's anchors: each scan's shift is that minus its own offset (within 5 meV)
    err = T._shift_errors(r, T.SMP_D, float(np.median(T.SMP_D)))
    assert max(abs(e) for e in err) < 5.0, err
    assert "earliest fine-grid anchors" in r[EX.REFERENCE_KEY]["statement"]
    coarse = T.by_run(T.v1_results(bdir), "01_SYN_ZZ1")[EX.REFERENCE_KEY]      # its OWN record says so (review, 7)
    assert coarse["coarse_grid"]["step_eV"] == pytest.approx(0.5, abs=0.01)
    assert "coarse grid at the anchor" in coarse["statement"] and "does not set the beamtime zero" in coarse["statement"]
    assert "coarse_grid" not in r[EX.REFERENCE_KEY]


def test_no_fine_grid_anchor_near_the_calibration_falls_back_and_says_so(tmp_path):
    """Re-review E: the only fine-grid group starts more than 6 h after the first scan, so the zero stays the earliest
    (coarse) group's median, and the record says so."""
    ref = [_coarse(T.scan_cols(10 + k, d=d)) for k, d in enumerate(T.REF_D)]
    smp = [T.scan_cols(20 + k, d=d) for k, d in enumerate(T.SMP_D)]
    bdir, _ = T.imported(tmp_path, [("01_SYN_ZZ1_060mV", 9, ref), ("02_SYN_ZZ2_060mV", 17, smp)])
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    zero = r[EX.REFERENCE_KEY]["routes"][0]["zero"]
    assert zero["fallback"] is True and zero["groups"] == ["01_SYN_ZZ1_060mV"], zero
    assert "Too few validated fine-grid anchors within 6 h" in r[EX.REFERENCE_KEY]["statement"]


def test_a_fine_grid_earliest_group_keeps_its_zero(tmp_path):
    bdir, _ = T.imported(tmp_path, T._two_groups())
    route = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")[EX.REFERENCE_KEY]["routes"][0]
    assert route["zero"]["groups"] == ["01_SYN_ZZ1_060mV"] and not route["zero"]["coarse_groups_skipped"]


# --- N4 / N6: the joint dose test -----------------------------------------------------------------------------------


def _per(ds, noise):
    return {f"spot {i + 1}": {"d12": d, "noise12": noise, "scans": ["a", "b"]} for i, d in enumerate(ds)}


def test_the_joint_dose_test_is_sign_consistent_and_never_carried_by_one_spot():
    j = EX.joint_dose_test(_per([-0.03, -0.028, -0.032, -0.03], 0.012))     # 2.5 sigma each, joint 5
    assert j["beyond"] and j["direction"] == -1 and j["z"] == pytest.approx(-5.0, abs=0.01)
    assert not EX.joint_dose_test(_per([-0.06, 0.03, -0.05, -0.04], 0.012))["beyond"]        # mixed signs
    one = EX.joint_dose_test(_per([-0.2, -0.001, -0.002, -0.001], 0.012))                     # one spot carries it
    assert abs(one["z"]) > 5 and one["z_without_strongest_spot"] > -2.0 and not one["beyond"]
    assert not EX.joint_dose_test(_per([-0.008, -0.009, -0.008, -0.009], 0.001))["beyond"]   # under the 1 % floor
    assert EX.DOSE_NULL_CALIBRATION["null_bias_over_null_sd_median"]["beamtime A (2021, BL15-2 Ir L3)"] == 0.0


def test_a_drop_at_every_spot_that_only_two_pass_alone_is_asked_about_and_nothing_is_dropped(tmp_path):
    """Two scans per spot; the white line falls in the second scan at EVERY spot, beyond 3 sigma at two of the four and
    under it at the other two (three measured groups of a 2021 Ir L3 beamtime): the per-spot rule needs most spots and stayed
    silent; the joint test catches it, and the rule ASKS (two scans cannot tell damage from settling)."""
    runs = T._dose_run(lambda j, k: 3.0 - (0.25 if k // 2 < 2 else 0.1) * j, per_spot=2,
                       noise_of=lambda j, k: 1.5e-2)
    bdir, _ = T.imported(tmp_path, runs)
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    d = T._dose(r)
    assert d["outcome"] == "question", d
    assert sum(1 for x in d["per_spot"].values() if x["kind"] not in ("none", EX.DOSE_JOINT_ONLY)) <= 2   # alone
    assert sum(1 for x in d["per_spot"].values() if x["kind"] == EX.DOSE_JOINT_ONLY) >= 2   # shown, own kind
    assert d["joint"]["beyond"] and d["joint"]["same_sign"] and d["joint"]["direction"] == -1
    assert "joint z" in d["statement"]
    assert EX.DOSE_QUESTION_FLAG in r["review_flags"]
    assert all(x["decision"] == "keep" for x in r[EX.DECISIONS_KEY]["rows"] if x.get("spot"))


def test_spots_counted_only_by_the_joint_test_make_a_question_never_a_drop(tmp_path):
    """Review of 28 Nov, 1: two spots measured three times GROW on their own, two measured twice show a small drop
    that passes only with the others. The joint test counts all four; a change found only together decides nothing:
    a question, no scan dropped at any spot, and the two joint-only spots carry their own kind."""
    sz = [SPOT4[0]] * 3 + [SPOT4[1]] * 3 + [SPOT4[2]] * 2 + [SPOT4[3]] * 2
    wls = [3.0, 2.7, 2.4, 3.0, 2.7, 2.4, 3.0, 2.97, 3.0, 2.97]
    bdir, _ = T.imported(tmp_path, T._spot_run(sz, [T.scan_cols(700 + k, wl=w, scale=20.0) for k, w in enumerate(wls)]))
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    d = T._dose(r)
    assert d["outcome"] == "question" and d["joint"]["beyond"], d
    kinds = {lab: x["kind"] for lab, x in d["per_spot"].items()}
    assert kinds == {"spot 1": "grows", "spot 2": "grows", "spot 3": EX.DOSE_JOINT_ONLY, "spot 4": EX.DOSE_JOINT_ONLY}
    codes = {y["code"] for x in r[EX.DECISIONS_KEY]["rows"] for y in x["reasons"]}
    assert not codes & {EX.DOSE_CODE, EX.SETTLING_CODE}
    assert "only 2 of 4 spots pass on their own" in d["why"]


def _trend_run(extra):
    """Two scans per spot on a white line falling scan after scan across the run (every raw scan-1 -> scan-2
    difference about -5 %); ``extra``: {scan index k: an added white-line change}."""
    return T._dose_run(lambda j, k: 3.0 - 0.15 * k - extra.get(k, 0.0), per_spot=2, noise_of=lambda j, k: 1.5e-2)


def test_a_change_the_global_trend_explains_is_said_as_the_samples_evolution(tmp_path):
    """Review of 28 Nov, 2: beyond the noise before the trend is taken out, not after, and NO spot passes on its own
    after it: the sample's evolution, said; no question, no bulk-approval refusal."""
    bdir, _ = T.imported(tmp_path, _trend_run({}))
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    d = T._dose(r)
    assert d["outcome"] == EX.DOSE_EVOLUTION, d
    assert d["joint_before_trend"]["beyond"] and not d["joint"]["beyond"]
    assert all(x["kind"] == "none" for x in d["per_spot"].values())
    assert "after the trend is taken out" in d["statement"] and "+0.0" not in d["statement"]
    assert EX.DOSE_QUESTION_FLAG not in r["review_flags"]


def test_a_spot_that_passes_alone_after_the_trend_is_named_never_promoted_and_never_called_evolution(tmp_path):
    """Re-review of 28 Nov, A: when a spot passes on its own after the trend (as in one measured group), the trend does not
    explain it: not 'the sample's evolution', not a question; the no-change line names the spot and its direction."""
    bdir, _ = T.imported(tmp_path, _trend_run({5: 0.2}))
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    d = T._dose(r)
    assert d["outcome"] == EX.DOSE_NO_CHANGE, d
    assert "spot 3 falls" in d["statement"] and "evolution" not in d["statement"]
    assert EX.DOSE_QUESTION_FLAG not in r["review_flags"]


def test_spots_that_pass_alone_in_both_directions_are_named_with_their_directions(tmp_path):
    bdir, _ = T.imported(tmp_path, _trend_run({5: 0.2, 3: -0.2}))
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    d = T._dose(r)
    assert d["outcome"] == EX.DOSE_NO_CHANGE, d
    assert "spot 2 rises" in d["statement"] and "spot 3 falls" in d["statement"], d["statement"]
    assert EX.DOSE_QUESTION_FLAG not in r["review_flags"]


def test_a_judged_dose_check_that_finds_nothing_says_so_in_one_line(tmp_path):
    runs = T._dose_run(lambda j: 3.0, per_spot=2, noise_of=lambda j, k: 1.5e-2)
    bdir, _ = T.imported(tmp_path, runs)
    d = T._dose(T.by_run(T.v1_results(bdir), "02_SYN_ZZ2"))
    assert d["outcome"] == EX.DOSE_NO_CHANGE and not d["joint"]["beyond"], d
    assert d["statement"].startswith("Beam damage judged at 4 spots") and d["statement"].endswith(").")
    assert "\n" not in d["statement"] and len(d["statement"]) < 250


# --- N5 / I5: the ratio window and a spot judged as a whole -----------------------------------------------------------


def test_the_ratio_shape_window_starts_at_the_edge_except_pt_l3():
    grid = np.arange(11160.0, 11800.0, 1.0)
    ir = EX.ratio_screens(11215.0, grid, {}, {"element": "Ir", "edge": "L3"})["ratio_shape"]["window_eV"]
    pt = EX.ratio_screens(11564.0, grid + 400, {}, {"element": "Pt", "edge": "L3"})["ratio_shape"]["window_eV"]
    assert ir[0] == 11215.0 and pt[0] == 11570.0


SPOT4 = (-7.45, -7.15, -6.85, -6.55)


def _two_per_spot(wl_first, wl_second):
    """Four spots, two scans each; the THIRD spot (scans 5, 6: neither the first scans of the run nor the last) has
    the white lines ``wl_first``, ``wl_second``; the others 3.0."""
    sz = [s for s in SPOT4 for _ in range(2)]
    cols = [T.scan_cols(500 + k, wl=(wl_first if k == 4 else wl_second if k == 5 else 3.0), scale=20.0, noise=6e-3)
            for k in range(8)]
    return T._spot_run(sz, cols)


def _three_per_spot(first, second, *, at=2):
    """Four spots, three scans each; spot ``at`` (0-based) has the white lines ``first``, ``first``, ``second`` (the
    third scan off-shape); the others 3.0."""
    sz = [s for s in SPOT4 for _ in range(3)]
    cols = [T.scan_cols(800 + k, wl=(first if k in (3 * at, 3 * at + 1) else second if k == 3 * at + 2 else 3.0),
                        scale=20.0, noise=6e-3) for k in range(12)]
    return T._spot_run(sz, cols)


def test_a_spot_whose_two_kept_scans_differ_like_its_off_shape_scan_is_left_out_whole(tmp_path):
    bdir, _ = T.imported(tmp_path, _three_per_spot(2.75, 2.62))
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    for k in (7, 8, 9):
        assert rows[k]["decision"] == "drop", rows[k]["reasons"]
        assert [y["code"] for y in rows[k]["reasons"]] == ["spot_differs_as_a_whole"], rows[k]["reasons"]
    assert all(rows[k]["decision"] == "keep" for k in (1, 2, 3, 4, 5, 6, 10, 11, 12))
    assert r["spots"]["outcome"] == "spot_differs_as_a_whole" and r["spots"]["whole_rule_id"] == EX.SPOT_WHOLE_RULE_ID


def test_one_kept_scan_at_the_spot_is_asked_never_dropped(tmp_path):
    """Review of 28 Nov (one measured group): ONE kept scan that differs is too few to drop a whole spot: asked."""
    bdir, _ = T.imported(tmp_path, _two_per_spot(2.8, 2.68))   # scan 6 off-shape; scan 5 not, but lower too
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert rows[5]["decision"] == "keep", rows[5]["reasons"]
    assert any(n["code"] == "spot_may_differ_as_a_whole" and n["decides"] is False for n in rows[5]["notes"])
    assert not any(y["code"] == "spot_differs_as_a_whole" for x in rows.values() for y in x["reasons"])
    assert r["spots"]["asked_as_a_whole"] and EX.SPOTS_DISAGREE_FLAG in r["review_flags"]
    said = r["qc"]["statements"][EX.SPOTS_DISAGREE_FLAG]          # worded for THIS case (re-review B)
    assert said.startswith("A SPOT MAY DIFFER AS A WHOLE (the other spots agree; this is not an even split)")
    assert EX.SPOTS_DISAGREE_FLAG in r["qc"]["reasons"]


def test_a_differing_spot_that_is_also_the_first_scans_is_asked_never_dropped_as_a_whole(tmp_path):
    bdir, _ = T.imported(tmp_path, _three_per_spot(2.75, 2.62, at=0))
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    assert not any(y["code"] == "spot_differs_as_a_whole" for x in r[EX.DECISIONS_KEY]["rows"] for y in x["reasons"])


def test_an_off_shape_scan_alone_at_its_spot_leaves_its_spot_mate_kept(tmp_path):
    bdir, _ = T.imported(tmp_path, _two_per_spot(3.0, 2.68))
    r = T.by_run(T.v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert rows[5]["decision"] == "keep", rows[5]["reasons"]
    assert not any(n["code"] == "spot_may_differ_as_a_whole" for x in rows.values() for n in x["notes"])
    assert not any(y["code"] == "spot_differs_as_a_whole" for x in rows.values() for y in x["reasons"])


# --- the version and the scoped verification statement -------------------------------------------------------------


def test_every_processed_record_carries_the_scoped_verification_and_stays_draft_unreviewed(tmp_path):
    bdir, _ = T.imported(tmp_path, T._two_groups())
    for r in T.v1_results(bdir):
        assert r["protocol_status"] == "draft_unreviewed" and r["protocol_version"] == EX.PROTOCOL_VERSION
        v = r[EX.ENGINE_KEY]["verification"]
        assert v == EX.PROTOCOL_VERIFICATION and v["status"] == "checked_against_two_independent_reductions_not_reviewed"
        assert v["statement"].startswith("Checked against two independent reductions; not yet reviewed.")
        assert "have not reviewed this protocol" in v["statement"]
        params = json.loads((bdir / next(f["relative_path"] for f in r["outputs"]["files"] if f["role"] == "params"))
                            .read_text())
        assert params["verification"] == EX.PROTOCOL_VERIFICATION
    assert EX.PROTOCOL_VERSION != "1.0.0"
    assert EX.SMOOTH_DRIFT["enabled"] is False          # I1 was measured and left off (see PROTOCOL_VERIFICATION)
