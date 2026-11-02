"""r5-a: processing / Athena fixes found on real beamtimes, on SYNTHETIC spectra and SYN_* names only.

A1 the scientist's Athena curve is judged by the post-edge level check; A2 a merged-away group takes no part in the
Athena name match; A3 several merges beside per-scan groups list the per-scan groups as one set, never a version per
scan; A4 Athena's ``is_merge`` flag ('e', 'n', 'k') is read; A5 scans left out for too few points are said (not an
energy scan / stopped), and aborted fragments are kept out of merges; A6 with fewer than 3 scans no flagged point is
counted as a glitch.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import mutations as M


def _proc():
    pytest.importorskip("numpy", reason="needs the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="needs the optional `processing` extra (xraylarch)")
    import test_local_import_processing as T

    return T


# --- A4: Athena's is_merge flag --------------------------------------------------------------------------------------


def test_is_merge_text_flags_are_read():
    from isaac_api.local_import.processing import athena as A

    for v in ("e", "n", "k", "E", "1", 1, "1.0", True):
        assert A.merge_flag(v) is True, v
    for v in ("", "  ", "0", 0, "0.0", None, False, "nan"):
        assert A.merge_flag(v) is False, v
    # a group flagged is_merge with no merge word in its name is the scientist's merge
    assert A.is_scientist_merge({"is_merge": A.merge_flag("e"), "names": ["syn_zz1_combined"]})


# --- A2 / A3: the name match -----------------------------------------------------------------------------------------


def _entry(T, label, prj, *, scale=1.0, is_merge=False, nor1=60.0):
    np = T.np
    mu = T.mu_edge(T.GRID) * 1e-2 * scale
    return {"names": [__import__("isaac_api.local_import.processing.athena", fromlist=["x"]).normalise_name(label)],
            "label": label, "group_name": label.lower(), "prj_relative_path": prj, "prj_source_id": None,
            "is_merge": is_merge, "energy": T.GRID.copy(), "mu": mu, "norm": mu / 0.015, "flat": mu / 0.015,
            "e0_eV": T.E0, "edge_step": 0.015, "params": {"nor1": nor1, "nor2": 130.0},
            "data_hash": f"h-{label}-{scale}", "non_finite_values": [], "energy_frame_known": True,
            "channel_expression": {}}


def test_a_merged_away_group_takes_no_part_in_the_match():
    T = _proc()
    from isaac_api.local_import.processing import athena as A

    live = {"group_id": "rg-live", "_stems": ["11_SYN_ZZ_091", "11_SYN_ZZ_092"], "_has_scans": True,
            "status": "scientist_confirmed"}
    dead = {"group_id": "rg-dead", "_stems": ["11_SYN_ZZ_091"], "_has_scans": True, "status": "merged"}
    entries = [_entry(T, "11_SYN_ZZ_091_A.001", "SYN.prj"), _entry(T, "11_SYN_ZZ_091_A.002", "SYN.prj", scale=1.01),
               _entry(T, "11_SYN_ZZ_092_A.001", "SYN.prj", scale=1.02), _entry(T, "11_SYN_ZZ_092_A.002", "SYN.prj", scale=1.03),
               _entry(T, "merge_11_SYN_ZZ", "SYN.prj", scale=1.015, is_merge=True)]
    matched, notes, versions = A.match_with_versions([live, dead], entries, T.np)
    assert list(matched) == ["rg-live"] and matched["rg-live"]["label"] == "merge_11_SYN_ZZ"
    assert not [n for n in notes if n["code"] == "athena_group_matches_several_record_groups"]
    assert matched["rg-live"]["_sets_aside"][0]["per_scan_set"]["scans"] == [1, 2, 1, 2]
    assert A.entry_groups([live, dead], entries) == {i: "rg-live" for i in range(5)}
    # NEGATIVE CONTROL: a split group is merged away too; a rejected one still takes part (its runs are in no live group)
    assert not A.takes_part({**dead, "status": "split"}) and A.takes_part({**dead, "status": "rejected"})
    _, notes2, _ = A.match_with_versions([live, {**dead, "status": "rejected"}], entries, T.np)
    assert any(n["code"] == "athena_group_matches_several_record_groups" for n in notes2)


def test_several_merges_beside_per_scan_groups_list_the_per_scan_groups_as_one_set():
    T = _proc()
    from isaac_api.local_import.processing import athena as A

    g = {"group_id": "rg-g", "_stems": ["11_SYN_ZZ_091", "11_SYN_ZZ_092"], "_has_scans": True}
    per_scan = [_entry(T, f"11_SYN_ZZ_09{r}_A.00{s}", "SYN_a.prj", scale=1 + 0.01 * (2 * r + s))
                for r in (1, 2) for s in (1, 2)]
    merges = [_entry(T, "merge_11_SYN_ZZ", "SYN_a.prj", scale=1.05, is_merge=True),
              _entry(T, "merge_11_SYN_ZZ", "SYN_b.prj", scale=1.05, is_merge=True, nor1=80.0)]
    merges[1]["data_hash"] = merges[0]["data_hash"]  # the same curve normalised another way in another project
    matched, _, versions = A.match_with_versions([g], per_scan + merges, T.np)
    assert matched == {}
    kinds = sorted(v["_match_kind"] for v in versions["rg-g"])
    assert kinds == ["per_scan_set", "scientist_merge", "scientist_merge"]
    s = next(v for v in versions["rg-g"] if v["_match_kind"] == "per_scan_set")
    assert s["per_scan_set"]["scans"] == [1, 2, 1, 2] and len(s["per_scan_set"]["athena_groups"]) == 4
    # NEGATIVE CONTROL: per-scan groups that form no set (two of one scan) stay listed one by one, never dropped
    loose = [_entry(T, "11_SYN_ZZ_091_A.001", "SYN_a.prj"), _entry(T, "11_SYN_ZZ_091_A.001", "SYN_c.prj", scale=1.2)]
    _, _, v2 = A.match_with_versions([g], loose + merges, T.np)
    assert len(v2["rg-g"]) == 4 and "per_scan_set" not in {v["_match_kind"] for v in v2["rg-g"]}


# --- A1: the scientist's Athena curve and the post-edge level --------------------------------------------------------


def test_the_post_edge_level_check_judges_an_athena_curve():
    T = _proc()
    from isaac_api.local_import.processing import run as R

    good = _entry(T, "01_SYN_ZZ1", "SYN.prj")
    good["norm"] = (good["mu"] - good["mu"][0]) / 0.015
    assert R.athena_post_edge_level(good, T.np) is None
    bad = dict(good, edge_step=1.0, norm=(good["mu"] - good["mu"][0]) * 80 / 0.015)  # a step that is not the jump
    bad["mu"] = good["mu"][0] + bad["norm"] * 1.0
    found = R.athena_post_edge_level(bad, T.np)
    assert found and found["level"] > 2 and found["statement"].startswith("This is the scientist's Athena curve")
    # NEGATIVE CONTROLS: an already-normalised curve (own check) and an unknown energy frame are not judged here
    assert R.athena_post_edge_level({**bad, "already_normalized": True}, T.np) is None
    assert R.athena_post_edge_level({**bad, "energy_frame_known": False}, T.np) is None


def test_an_athena_curve_whose_post_edge_level_is_far_from_1_fails_qc_and_is_not_preferred(tmp_path, monkeypatch):
    T = _proc()
    from isaac_api.local_import.processing import athena as A

    real = A.load_project

    def scaled(*args, **kwargs):
        entries, notes = real(*args, **kwargs)
        for e in entries:  # the scientist's normalised curve, scaled as a fixed edge step of 1 would leave it
            e["norm"], e["flat"] = e["norm"] * 80, e["flat"] * 80
            e["mu"] = e["mu"][0] + e["norm"] * (e["edge_step"] or 1.0) + 0 * e["mu"]
        return entries, notes

    monkeypatch.setattr(A, "load_project", scaled)
    bdir, root = T._athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1_1-2", T.GRID, T.mu_edge(T.GRID) * 1e-2)]})
    out = T.run_process(bdir, source_root=root)
    sci = next(r for r in out["processing_results"] if r["source"] == "scientist_athena")
    assert sci["qc"]["verdict"] == "fail" and "post_edge_not_at_1" in sci["qc"]["reasons"]
    assert sci["qc"]["metrics"]["post_edge_level"] > 2 and "post_edge_not_at_1" in sci["qc"]["statements"]
    assert sci["preferred_for_record"] is False and "athena_post_edge_not_at_1" in sci["review_flags"]
    assert M.unusable_curve_reasons(sci) == ["post_edge_not_at_1"]  # decide refuses to approve it


def test_a_plain_athena_curve_still_passes(tmp_path):
    T = _proc()
    bdir, root = T._athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1_1-2", T.GRID, T.mu_edge(T.GRID) * 1e-2)]})
    out = T.run_process(bdir, source_root=root)
    sci = next(r for r in out["processing_results"] if r["source"] == "scientist_athena")
    assert "post_edge_level" not in sci["qc"]["metrics"] and sci["preferred_for_record"] is True


# --- A5: scans left out for too few points; aborted fragments ---------------------------------------------------------


def _motor_scan(T, n=41):
    """A SPEC ascan of a SYN motor: the energy column holds one value at every point."""
    import numpy as np

    cols = {"SYNm": np.linspace(0, 4, n), "energy": np.full(n, T.E0 + 20.0), "I0": np.full(n, 1.0e5),
            "vortDT": np.linspace(1.0, 2.0, n) * 1e3}
    return T.spec_file(cols).replace("#S 1 gscan synthetic", "#S 3  ascan  SYNm 0 4  40 1")


def _fragment(T, n=6):
    cols = T.fluo_scan(9)
    return T.spec_file({k: v[:n] for k, v in cols.items()})


def test_an_aborted_fragment_is_kept_out_of_the_merge_and_a_motor_scan_is_said(tmp_path):
    T = _proc()
    scans = [T.spec_file(T.fluo_scan(s)) for s in (1, 2)] + [_fragment(T), _motor_scan(T)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    why = [i.get("skip_reason") for i in r["inputs"]]
    assert why == [None, None, "aborted_scan_fragment", "too_few_points"]
    assert r["qc"]["metrics"]["scans_used"] == 2 and r["qc"]["metrics"]["scans_skipped_aborted_fragment"] == 1
    assert "scans_skipped_aborted_fragment" in r["qc"]["reasons"] and r["qc"]["verdict"] == "warn"
    assert T.step(r, "merge")["outcome"]["n_scans"] == 2
    frag = r["qc"]["statements"]["aborted_scan_fragment"]
    assert "01_SYN_ZZ1_003.dat (6 points)" in frag and "at least 20 points" in frag
    few = r["qc"]["statements"]["scans_skipped_too_few_points"]
    assert "1 is not an energy scan" in few and "ascan SYNm" in few and "01_SYN_ZZ1_004.dat" in few
    assert "the energy column (energy) holds only 1 distinct value over 41 points" in few
    qc_file = next(f for f in r["outputs"]["files"] if f["role"] == "qc")
    text = (bdir / qc_file["relative_path"]).read_text()
    assert "scans_skipped_too_few_points" not in text and "aborted_scan_fragment" not in text  # said after the run id
    assert "isaac.xas.skip_aborted_scan_fragment.v0" in r["rule_versions"]["rule_ids"]


def test_short_scans_alone_are_not_fragments_and_a_stopped_scan_is_said(tmp_path):
    T = _proc()
    import numpy as np

    # NEGATIVE CONTROL: no scan has enough points, so none is a fragment (the merge then fails on its own)
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", [_fragment(T, 12), _fragment(T, 15)], {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    assert "aborted_scan_fragment" not in {i.get("skip_reason") for i in r["inputs"]}
    # a scan that stopped after 2 points beside a full one: said as stopped, not as a motor scan
    cols = T.fluo_scan(3)
    two = T.spec_file({k: np.asarray(v)[:2] for k, v in cols.items()})
    (tmp_path / "b").mkdir()
    b2, r2, _ = T.make_case(tmp_path / "b", [("02_SYN_ZZ2", [T.spec_file(T.fluo_scan(1)), two], {"sample_name": "ZZ2"})])
    res = T.isaac(T.run_process(b2, source_root=r2))
    few = res["qc"]["statements"]["scans_skipped_too_few_points"]
    assert few.startswith("1 of 2 listed scans were used; 1 was left out because it has too few points.")
    assert "stopped after fewer than 5 usable points (an aborted scan): 02_SYN_ZZ2_002.dat (2 points)" in few
    assert "not an energy scan" not in few


def test_a_kept_approval_whose_fresh_result_leaves_out_a_fragment_is_said():
    inputs = [{"source_id": f"src-{n}", "relative_path": f"SYN_dir/SYN_{n:03d}.dat"} for n in (1, 2, 3)]
    old = {"result_id": "proc-g1-aaa-isaac", "group_id": "g1", "source": "isaac_protocol", "inputs": inputs}
    new = {**old, "result_id": "proc-g1-bbb-isaac", "inputs": [*inputs[:2], {**inputs[2], "skip_reason": "aborted_scan_fragment"}]}
    bundle = {"scientist_decisions": [{"decision_id": "dec-1", "target": {"kind": "processing_result", "id": old["result_id"]},
                                       "decision": "approve", "decided_by": {"name": "SYN Scientist"}}]}
    [line] = M.decided_results_with_a_new_all_zero_skip(bundle, [old], [new])
    assert "merged SYN_003.dat, a scan that stopped after too few points to merge (an aborted fragment); this build " \
           "leaves it out" in line["statement"]


# --- A6: fewer than 3 scans: no flagged point is counted as a glitch ---------------------------------------------------


def test_with_few_scans_no_flagged_point_is_counted_as_a_glitch():
    _proc()
    from isaac_api.local_import.processing import run as R

    points = [(0, 4966.0, True), (0, 5050.0, False), (1, 5060.0, False)]
    few = R._glitch_points_on_edge(points, 4966.0, ["SYN_001.dat", "SYN_002.dat"], few_scans=True)
    assert few["off_edge"] is None and few["unjudged"] == 3 and few["on_edge"] == 1
    assert "none of the 3 flagged points is counted as a glitch" in few["statement"]
    assert "off the edge and counted as glitches" not in few["statement"]
    # NEGATIVE CONTROL: with enough scans the off-edge points are glitches, as before
    many = R._glitch_points_on_edge(points, 4966.0, ["SYN_001.dat", "SYN_002.dat"])
    assert many["off_edge"] == 2 and "unjudged" not in many and "off the edge and counted as glitches" in many["statement"]


def test_a_two_scan_result_reports_its_flags_as_unjudged(tmp_path):
    T = _proc()
    scans = [T.spec_file(T.fluo_scan(1, spike=132)), T.spec_file(T.fluo_scan(2, spike=20))]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    m, said = r["qc"]["metrics"], r["qc"].get("statements") or {}
    assert m["glitch_points"] >= 1 and "glitch_check_few_scans" in said
    assert "glitch_points_off_edge" not in m
    if "glitch_points_on_edge" in said:
        assert m["glitch_points_unjudged"] == m["glitch_points"]
        assert "off the edge and counted as glitches" not in said["glitch_points_on_edge"]
        assert "is counted as a glitch." in said["glitch_points_on_edge"]
    qc_file = next(f for f in r["outputs"]["files"] if f["role"] == "qc")
    assert "glitch_points_unjudged" not in json.loads((bdir / qc_file["relative_path"]).read_text())["metrics"]


# --- A7: usable reference edges that disagree are not proposed -------------------------------------------------------


def _ref_step(e0s, snrs, source="in_scan_reference_channel"):
    return {"step": "calibration", "params": {"reference_min_edge_snr": 10.0, "max_plausible_shift_eV": 25.0},
            "outcome": {"reference_source": source, "reference_e0_per_scan_eV": list(e0s),
                        "reference_snr_per_scan": list(snrs)}}


def test_reference_edges_that_disagree_are_not_proposed_and_no_shift_is_offered_by_naming():
    from isaac_api.local_import.processing import reference as REF

    step = _ref_step([11205.0, 11214.0, 11225.0], [40.0, 35.0, 50.0])  # invented: "usable" edges 20 eV apart
    r = REF.reading(step)
    assert r["reference_edges_disagree"] and r["reference_proposed"] is False and r["calibration_proposed"] is False
    assert r["reference_edge_usable"] is True
    said = r["reference_statement"]
    assert "ISAAC does not propose it as the reference" in said and "Naming its element and edge gives the shift" not in said
    # still approvable with --accept-shift: the shift is computed from it
    w = REF.would_apply(step, "Ir", "L3")
    assert w["shift_eV"] is not None and w["needs_size_confirmation"]
    # NEGATIVE CONTROL: edges that agree are proposed, and naming the edge is said
    ok = REF.reading(_ref_step([11215.0, 11215.2, 11215.1], [40.0, 35.0, 50.0]))
    assert ok["reference_proposed"] is True and "Naming its element and edge gives the shift" in ok["reference_statement"]


def test_one_degenerate_reference_scan_is_said_with_an_apostrophe_s():
    from isaac_api.local_import.processing import reference as REF

    one = REF.reading(_ref_step([11215.0, 11230.0, 11215.2], [400.0, 9e13, 380.0]))["reference_statement"]
    assert one.startswith("1 scan's reference channel has an edge step more than 1,000,000 times its pre-edge noise")
    two = REF.reading(_ref_step([11215.0, 11230.0, 11231.0], [400.0, 9e13, 8e13]))["reference_statement"]
    assert two.startswith("2 scans' reference channels have")


def test_a_processed_result_with_disagreeing_reference_edges_says_not_proposed(tmp_path):
    T = _proc()
    import test_local_import_polish_c12cal as C12

    scans = [C12._ref_scan(T, 1, T.E0 + 0.5, ref_noise=0.001), C12._ref_scan(T, 2, T.E0 + 1.5, ref_noise=0.001)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    cal = T.step(r, "calibration")
    o = cal["outcome"]
    assert o["reference_edges_disagree"] and o["reference_proposed"] is False
    assert "Naming its element and edge" not in o["reference_statement"]
    params = next(f for f in r["outputs"]["files"] if f["role"] == "params")
    assert "reference_proposed" not in (bdir / params["relative_path"]).read_text()  # outside the hashed files


# --- review H1: the scientist's normalisation is rebuilt from the project's stored step ------------------------------


def _bkg(**kw):
    from types import SimpleNamespace

    return SimpleNamespace(**kw)


def _edge(T, step=0.015):
    import numpy as np

    e = T.GRID.copy()
    line = 0.002 + 1.0e-5 * (e - T.E0)
    mu = line + step * (0.5 + np.arctan((e - T.E0) / 0.5) / np.pi)
    return e, mu, line


def test_the_project_stored_step_and_line_rebuild_the_curve():
    T = _proc()
    import numpy as np
    from isaac_api.local_import.processing import athena as A

    e, mu, line = _edge(T)
    larch_step = 0.0003  # a re-fit that went wrong: the curve made with it sits 50 steps above the line
    larch_norm = (mu - line) / larch_step
    params = {"step": 0.015, "fixstep": 0.0, "flatten": 1.0, "pre1": -60.0, "pre2": -30.0}
    post_c = (0.002 + 0.015, 1.0e-5)  # the project's post-edge line: pre-edge line + step at E0, the same slope
    bkg = _bkg(slope=1.0e-5, int=0.002 - 1.0e-5 * T.E0, nc0=post_c[0] - post_c[1] * T.E0, nc1=post_c[1], nc2=0.0, nc3=0.0)
    got = A.athena_normalisation(e, mu, larch_norm, larch_norm, larch_step, T.E0, bkg, params, np)
    assert got["edge_step"] == 0.015 and got["said"]["pre_edge_line"] == "project" and got["said"]["flattened_with"] == "project"
    post = e > T.E0 + 60
    assert abs(float(got["norm"][post].mean()) - 1.0) < 0.02 and abs(float(got["flat"][post].mean()) - 1.0) < 0.02
    assert "ISAAC used the project's stored step" in got["said"]["statement"]
    assert "not the scientist's processing" in got["said"]["statement"]
    # a line that does not describe the data (another program's default, slope 0, intercept 7): larch's line is used
    bad = _bkg(slope=0.0, int=7.0, nc0=0.0, nc1=0.0, nc2=0.0, nc3=0.0)
    got2 = A.athena_normalisation(e, mu, larch_norm, larch_norm, larch_step, T.E0, bad, params, np)
    assert got2["said"]["pre_edge_line"] == "larch" and got2["said"]["flattened_with"] == "larch, scaled"
    assert abs(float(got2["norm"][post].mean()) - 1.0) < 0.02
    # NEGATIVE CONTROLS: steps that agree within 1 %, no stored step, a negative one: larch's curve stands
    assert A.athena_normalisation(e, mu, larch_norm, larch_norm, 0.01505, T.E0, bkg, params, np) is None
    assert A.athena_normalisation(e, mu, larch_norm, larch_norm, larch_step, T.E0, bkg, {**params, "step": None}, np) is None
    assert A.athena_normalisation(e, mu, larch_norm, larch_norm, larch_step, T.E0, bkg, {**params, "step": -2.0}, np) is None


def test_a_project_whose_stored_step_differs_is_rebuilt_said_and_judged_on_its_own_curve(tmp_path, monkeypatch):
    T = _proc()
    from larch import Group
    from larch.io import AthenaProject

    real_prj = T._athena_prj

    def stored_twice(path, groups):  # the project stores twice the step larch's re-fit gives (synthetic)
        prj = AthenaProject()
        for label, e, mu in groups:
            g = Group(energy=e, mu=mu, label=label, filename=label)
            T.xafs.pre_edge(g, pre1=-50, pre2=-30, norm1=60, norm2=130, nnorm=2)
            g.edge_step = g.edge_step * 2
            prj.add_group(g)
        prj.save(str(path))

    monkeypatch.setattr(T, "_athena_prj", stored_twice)
    bdir, root = T._athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1_1-2", T.GRID, T.mu_edge(T.GRID) * 1e-2)]})
    monkeypatch.setattr(T, "_athena_prj", real_prj)
    out = T.run_process(bdir, source_root=root)
    sci = next(r for r in out["processing_results"] if r["source"] == "scientist_athena")
    assert "athena_renormalisation_differs" in sci["review_flags"]
    said = sci["qc"]["statements"]["athena_renormalisation_differs"]
    assert "the project stores" in said and "not the scientist's processing" in said
    ren = sci["renormalised_from_project"]
    assert ren["project_edge_step"] == pytest.approx(2 * ren["larch_edge_step"])
    assert sci["outputs"]["edge_step"] == pytest.approx(ren["project_edge_step"])
    # the curve written for the record is the rebuilt one: it sits at about half a step after the edge
    import numpy as np

    f = next(x for x in sci["outputs"]["files"] if x["role"] == "athena_normalized")
    rows = [ln.split(",") for ln in (bdir / f["relative_path"]).read_text().splitlines() if ln and ln[0].isdigit()]
    e, n = np.array([float(r[0]) for r in rows]), np.array([float(r[1]) for r in rows])
    assert abs(float(n[e > T.E0 + 60].mean()) - 0.5) < 0.05
    assert "post_edge_level" not in sci["qc"]["metrics"]  # 0.5 is within 0 to 2: judged on the rebuilt curve


def test_a_per_scan_set_says_its_members_were_rebuilt():
    T = _proc()
    from isaac_api.local_import.processing import athena as A

    a, b = _entry(T, "01_SYN_ZZ1_001", "SYN.prj"), _entry(T, "01_SYN_ZZ1_002", "SYN.prj", scale=1.01)
    a[A.RENORMALISED_KEY] = {"larch_edge_step": 0.001, "project_edge_step": 0.015, "statement": "x"}
    s = A._per_scan_set([a, b], ["01_SYN_ZZ1"], T.np)
    r = s[A.RENORMALISED_KEY]
    assert r["members_rebuilt"] == 1 and r["members"] == 2 and "before taking the mean" in r["statement"]
    assert A._per_scan_set([b, _entry(T, "01_SYN_ZZ1_001", "SYN.prj")], ["01_SYN_ZZ1"], T.np).get(A.RENORMALISED_KEY) is None


# --- review M1 / M2: decided results kept as they were are said --------------------------------------------------------


def test_a_decided_athena_result_that_now_fails_the_post_edge_check_gets_a_kept_note(tmp_path, monkeypatch):
    T = _proc()
    from isaac_api.local_import.processing import athena as A

    real = A.load_project

    def scaled(*args, **kwargs):
        entries, notes = real(*args, **kwargs)
        for e in entries:
            e["norm"], e["flat"] = e["norm"] * 80, e["flat"] * 80
            e["mu"] = e["mu"][0] + e["norm"] * (e["edge_step"] or 1.0) + 0 * e["mu"]
        return entries, notes

    monkeypatch.setattr(A, "load_project", scaled)
    bdir, root = T._athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1_1-2", T.GRID, T.mu_edge(T.GRID) * 1e-2)]})
    out = T.run_process(bdir, source_root=root)
    sci = next(r for r in out["processing_results"] if r["source"] == "scientist_athena")
    [note] = [n for n in out["kept_result_notes"] if n["result_id"] == sci["result_id"]]
    assert note["add_review_flags"] == ["athena_post_edge_not_at_1"]
    assert "decided before this check" in note["statements"]["post_edge_not_at_1"]
    from isaac_api.local_import.processing.run import apply_kept_result_notes

    stored = {"result_id": sci["result_id"], "qc": {"verdict": "pass", "statements": {}}, "review_flags": []}
    assert apply_kept_result_notes([stored], out["kept_result_notes"]) == 1
    assert "athena_post_edge_not_at_1" in stored["review_flags"] and stored["qc"]["verdict"] == "pass"


def _res(rid, run, source="isaac_protocol", **kw):
    return {"result_id": rid, "group_id": "g1", "run_id": run, "source": source, "inputs": [{"source_id": "s1"}], **kw}


def test_a_decided_result_whose_group_moved_to_another_run_is_said():
    old = _res("proc-g1-r-a-isaac", "r-a", athena_versions=[{}, {}, {}])
    new = _res("proc-g1-r-b-isaac", "r-b")
    new_ath = _res("proc-g1-r-b-athena", "r-b", source="scientist_athena",
                   inputs=[{"relative_path": "SYN.prj", "athena_group": "merge_syn"}],
                   review_flags=["athena_renormalisation_differs"])
    bundle = {"scientist_decisions": [{"decision_id": "dec-1", "target": {"kind": "processing_result", "id": old["result_id"]},
                                       "decision": "approve", "decided_by": {"name": "SYN Scientist"}}]}
    [line] = M.decided_results_on_an_older_run(bundle, [old], [old], [new, new_ath])
    assert line["decided_result_id"] == "proc-g1-r-a-isaac" and line["new_result_id"] == "proc-g1-r-b-isaac"
    said = line["statement"]
    assert "matched differently now (3 versions listed before, matched to merge_syn in SYN.prj now)" in said
    assert "rebuilt from its project's stored edge step" in said
    assert "The approval still stands on the old curve" in said
    # NEGATIVE CONTROLS: no decision; the same run; a line already said (a scan now left out)
    assert M.decided_results_on_an_older_run({"scientist_decisions": []}, [old], [old], [new]) == []
    assert M.decided_results_on_an_older_run(bundle, [old], [old], [_res("proc-g1-r-a-isaac", "r-a")]) == []
    assert M.decided_results_on_an_older_run(bundle, [old], [old], [new], said={old["result_id"]}) == []
    [plain] = M.decided_results_on_an_older_run(bundle, [_res(old["result_id"], "r-a")], [_res(old["result_id"], "r-a")], [new])
    assert "its curve, or a file its id is made from, changed" in plain["statement"]


# --- review L1: the sets beside several merges are built per project --------------------------------------------------


def test_the_sets_beside_several_merges_are_built_per_project_from_every_candidate():
    T = _proc()
    from isaac_api.local_import.processing import athena as A

    g = {"group_id": "rg-g", "_stems": ["01_SYN_ZZ1"], "_has_scans": True}
    a1, a2 = _entry(T, "01_SYN_ZZ1_001", "SYN_a.prj"), _entry(T, "01_SYN_ZZ1_002", "SYN_a.prj", scale=1.01)
    b1 = dict(a1, prj_relative_path="SYN_b.prj")  # the same curve, the same parameters, in another project
    b2 = _entry(T, "01_SYN_ZZ1_002", "SYN_b.prj", scale=1.01, nor1=80.0)  # another normalisation of scan 2
    merges = [_entry(T, "merge_01_SYN_ZZ1", "SYN_a.prj", scale=1.005, is_merge=True),
              _entry(T, "merge_01_SYN_ZZ1", "SYN_b.prj", scale=1.006, is_merge=True)]
    _, _, versions = A.match_with_versions([g], [a1, a2, b1, b2] + merges, T.np)
    kinds = sorted(v["_match_kind"] for v in versions["rg-g"])
    # project b's set is formed from both its groups (its scan 1 is not lost to project a's identical copy)
    assert kinds == ["per_scan_set", "per_scan_set", "scientist_merge", "scientist_merge"]
    assert sorted(v["prj_relative_path"] for v in versions["rg-g"] if v["_match_kind"] == "per_scan_set") == ["SYN_a.prj", "SYN_b.prj"]


# --- review L3: glitch_points_unjudged whenever the few-scan sentence is said ----------------------------------------


def test_glitch_points_unjudged_is_present_whenever_the_few_scan_sentence_is(tmp_path):
    T = _proc()
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", [T.spec_file(T.fluo_scan(1, spike=20))], {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    m, said = r["qc"]["metrics"], r["qc"]["statements"]
    assert "glitch_check_few_scans" in said and m["glitch_points_unjudged"] == m["glitch_points"] >= 1


def test_a_degenerate_larch_refit_is_replaced_by_the_project_stored_step(tmp_path):
    _proc()
    import test_local_import_polish_c2a as C2

    bdir, root = C2._case(tmp_path, C2.DEGENERATE)  # the project stores the step its curve was made with
    isa, sci = C2._results(C2.run_process(bdir, source_root=root))
    assert sci["qc"]["metrics"]["edge_step"] < 10 and "edge_step_implausible" not in sci["qc"]["reasons"]
    assert sci["renormalised_from_project"]["larch_edge_step"] > 1000
    assert "athena_renormalisation_differs" in sci["review_flags"]
