"""LOCAL-P: draft XAS processing protocol ``isaac.xas.v0`` on SYNTHETIC spectra.

Every spectrum here is an invented arctan edge (+ noise); every name is SYN_*. No real
data. Needs the optional ``processing`` extra (numpy + xraylarch).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")

import larch.xafs as xafs  # noqa: E402

from isaac_api.local_import import grouping as G  # noqa: E402
from isaac_api.local_import.processing import athena as A  # noqa: E402
from isaac_api.local_import.processing import core as C  # noqa: E402
from isaac_api.local_import.processing import protocol as P  # noqa: E402
from isaac_api.local_import.processing.channels import choose_channels  # noqa: E402
from isaac_api.local_import.processing.cli_entry import run_group, run_process  # noqa: E402
from isaac_api.local_import.processing.edges import EDGE_TABLE_EV, edge_energy  # noqa: E402
from isaac_api.local_import.processing.evaluate import evaluate_folder  # noqa: E402
from isaac_api.local_import.processing.readers import parse_text, read_scan_file  # noqa: E402
from isaac_api.local_import.processing.run import process_bundle  # noqa: E402

E0 = 4966.0  # synthetic edge position (eV); values are invented
GRID = np.arange(4900.0, 5100.0 + 1e-9, 0.5)


def mu_edge(e, e0=E0, step=1.5, offset=0.2, width=0.5):
    return offset + 0.0001 * (e - e[0]) + step * (0.5 + np.arctan((e - e0) / width) / np.pi)


def spec_file(cols: dict, title="SYN") -> str:
    names = list(cols)
    lines = [f"#F {title}", "#C SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value is invented.", "#S 1 gscan synthetic", "#L " + "  ".join(names)]
    for row in zip(*(cols[n] for n in names)):
        lines.append(" ".join(f"{v:.6f}" for v in row))
    return "\n".join(lines) + "\n"


def xdac_file(cols: dict, region="SYN_region.rgn") -> str:
    head = ["SSRL   EXAFS Data Collector 4.0", "SYNTHETIC FIXTURE", f"PTS: {len(next(iter(cols.values())))} COLS: {len(cols)}", "syn.det", region, "", "Data:"]
    body = [" ".join(f"{v:.4f}" for v in row) for row in zip(*cols.values())]
    return "\n".join(head + list(cols) + [""] + body) + "\n"


def fluo_scan(seed, *, e=GRID, e0=E0, spike=None, noise=0.002, ref_e0=None):
    rng = np.random.default_rng(seed)
    i0 = np.full(e.size, 1.0e5)
    mu = mu_edge(e, e0) + rng.normal(0, noise, e.size)
    if spike is not None:
        mu[spike] += 0.5
    cols = {"energy": e, "I0": i0, "vortDT": mu * i0 * 0.01}
    if ref_e0 is not None:
        i1 = np.full(e.size, 5.0e4)
        cols["I1"] = i1
        cols["I2"] = i1 * np.exp(-mu_edge(e, ref_e0, step=1.0, offset=0.5))
    return cols


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make_case(tmp_path, runs, *, label="SYN_beamtime", unread=None):
    """runs: [(stem, [scan text...], conditions dict)] -> (bundle_dir, source_root, bundle)."""
    root = tmp_path / label
    root.mkdir()
    sources, b_runs, cands = [], [], []
    n = 0
    for i, (stem, scans, conds) in enumerate(runs, start=1):
        (root / stem).write_text(f"#F {stem}\n")
        acq = f"src-{i:03d}-a"
        sources.append({"source_id": acq, "relative_path": stem, "content_sha256": _sha(root / stem), "classification": {"confidence": "content"}})
        sc = []
        for j, text in enumerate(scans, start=1):
            rel = f"{stem}_dir/{stem}_{j:03d}.dat"
            (root / rel).parent.mkdir(exist_ok=True)
            (root / rel).write_text(text)
            sid = f"src-{i:03d}-{j:02d}"
            sources.append({"source_id": sid, "relative_path": rel, "content_sha256": _sha(root / rel), "classification": {"confidence": "content"}})
            sc.append({"source_id": sid, "relative_path": rel, "scan_index": j})
        ids = []
        for key, val in conds.items():
            n += 1
            ids.append(f"cand-{n:04d}")
            cands.append({"candidate_id": ids[-1], "run_id": f"run-{i:03d}", "statement_key": key, "value": None, "observed_literals": [val], "extracted_state": "needs_review", "value_state": "needs_review", "evidence": []})
        b_runs.append({"run_id": f"run-{i:03d}", "run_key": f"{stem}@sha256:{i:064x}", "stem": stem, "source_type": "spec_acquisition", "acquisition_source_id": acq, "scan_count": len(sc), "scans": sc, "candidate_ids": ids, "legacy_number_shared": False})
    unread_files = []
    for rel, text in (unread or {}).items():
        (root / rel).write_text(text)
        sid = f"src-u-{len(unread_files):03d}"
        sources.append({"source_id": sid, "relative_path": rel, "content_sha256": _sha(root / rel), "classification": {"confidence": "content"}})
        unread_files.append({"source_id": sid, "relative_path": rel})
    bundle = {"bundle_id": "syn-bundle", "source_root": {"label": label}, "runs": b_runs, "candidates": cands, "sources": sources, "unread_files": unread_files, "experiment": {"element_evidence": []}}
    bdir = tmp_path / "bundle"
    bdir.mkdir()
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root, bundle


def isaac(payload, i=0):
    return [r for r in payload["processing_results"] if r["source"] == "isaac_protocol"][i]


def step(result, name):
    return next(s for s in result["steps"] if s["step"] == name)


# --- numeric steps ---------------------------------------------------------------------------


def test_normalization_recovers_a_known_edge_step():
    rng = np.random.default_rng(1)
    mu = mu_edge(GRID, step=1.5) + rng.normal(0, 0.002, GRID.size)
    nm = C.normalize(GRID, mu, P.resolve_params(), np, xafs)
    assert abs(nm["edge_step"] - 1.5) / 1.5 < 0.03
    assert abs(nm["e0_eV"] - E0) < 1.0
    rp = nm["resolved_params"]
    assert rp["pre2"] == -30.0 and rp["nnorm"] == 2 and rp["norm1"] == pytest.approx(min(100.0, 0.4 * (GRID[-1] - rp["e0"])), abs=1.0)
    assert np.allclose(nm["flat"][GRID > E0 + 60], 1.0, atol=0.03)


def test_merge_math_n_mean_stderr():
    M = np.array([[1.0, 2.0, 3.0], [3.0, 4.0, 5.0], [2.0, 3.0, np.nan]])
    mg = C.merge(M, np=np)
    assert mg["n"].tolist() == [3, 3, 2]
    assert np.allclose(mg["mean"], [2.0, 3.0, 4.0])
    assert np.allclose(mg["std"], [1.0, 1.0, np.sqrt(2.0)])
    assert np.allclose(mg["stderr"], [1 / np.sqrt(3), 1 / np.sqrt(3), 1.0])


def test_deglitch_flags_but_does_not_drop_by_default():
    params = P.resolve_params()
    M = np.vstack([mu_edge(GRID) + np.random.default_rng(s).normal(0, 0.002, GRID.size) for s in range(4)])
    M[1, 300] += 0.5
    dg = C.deglitch(M, GRID, params, np)
    assert dg["method"] == "cross_scan_median"
    assert dg["point_flags"][1, 300] and dg["flagged_points_total"] == 1  # the edge itself is not flagged
    kept = C.merge(M, np=np)["mean"][300]
    assert kept == pytest.approx(M[:, 300].mean())
    dropped = C.merge(M, dg["point_flags"], np=np)["mean"][300]
    assert dropped == pytest.approx(np.delete(M[:, 300], 1).mean())


def test_deglitch_local_method_for_two_scans_and_outlier_scans():
    params = P.resolve_params()
    M = np.vstack([mu_edge(GRID) + np.random.default_rng(s).normal(0, 0.002, GRID.size) for s in range(2)])
    M[0, 50] += 0.5
    dg = C.deglitch(M, GRID, params, np)
    assert dg["method"] == "local_neighbour_interpolation" and dg["point_flags"][0, 50]
    M5 = np.vstack([mu_edge(GRID) + np.random.default_rng(s).normal(0, 0.002 * (40 if s == 3 else 1), GRID.size) for s in range(5)])
    assert C.deglitch(M5, GRID, params, np)["scan_flags"] == [False, False, False, True, False]


def test_truncated_scan_keeps_the_full_grid_and_counts_n():
    scans = [{"energy": GRID, "mu": mu_edge(GRID)}, {"energy": GRID[:100], "mu": mu_edge(GRID[:100])}]
    grid, info = C.common_grid(scans, np)
    assert grid.size == GRID.size and info["truncated_scan_positions"] == [1]
    n = C.merge(C.interpolate(scans, grid, np), np=np)["n"]
    assert n[:100].tolist() == [2] * 100 and set(n[100:].tolist()) == {1}


def test_edge_snapshot_matches_xraydb():
    xraydb = pytest.importorskip("xraydb", reason="xraydb ships with xraylarch")
    for (el, edge), value in EDGE_TABLE_EV.items():
        assert xraydb.xray_edge(el, edge).energy == pytest.approx(value)
    assert edge_energy("Ti", "K")[0] == pytest.approx(4966.0)


# --- readers and channels --------------------------------------------------------------------


def test_readers_cr_line_endings_duplicates_width_and_binary(tmp_path):
    t = parse_text("energy\tI0\tI0\r1.0\t2.0\t3.0\r2.0\t3.0\r3.0\t4.0\t5.0\r")
    assert t.format_id == "delimited_columns" and t.labels == ["energy", "I0", "I0#2"]
    assert "cr_line_endings" in t.notes and "rows_width_mismatch_skipped:1" in t.notes and t.n_rows == 2
    x = parse_text(xdac_file({"Requested Energy": [1.0, 2.0], "Achieved Energy": [1.1, 2.1], "I0": [5.0, 5.0]}, region="ZzK_SYNTHETIC_region.rgn"))
    assert x.format_id == "ssrl_xdac" and x.labels == ["Requested Energy", "Achieved Energy", "I0"] and "ZzK_SYNTHETIC_region.rgn" in x.header_lines
    b = tmp_path / "SYN.001"
    b.write_bytes(b"\x00\x01binary")
    assert read_scan_file(b).error == "binary_content"


def test_channels_prefer_achieved_energy_and_flag_missing_i0_and_icr():
    params = P.resolve_params()
    t = parse_text(spec_file({"energy": GRID[:10], "absev": GRID[:10] + 1, "I0": np.ones(10), "vortDT": np.ones(10)}))
    c = choose_channels(t, params=params)
    assert c.energy == "absev" and c.basis["energy_alternatives"] == ["energy"] and "energy_column_alternatives" in c.flags
    t2 = parse_text(spec_file({"energy": GRID[:10], "vortDT": np.ones(10)}))
    c2 = choose_channels(t2, params=params)
    assert c2.mode == "signal_only" and "i0_missing" in c2.flags
    xd = parse_text(xdac_file({"Achieved Energy": GRID[:10], "I0": np.ones(10), "I1": np.ones(10), "I2": np.ones(10), "SCA1_1": np.ones(10), "SCA1_2": np.zeros(10), "ICR1_1": np.ones(10)}))
    c3 = choose_channels(xd, params=params)
    assert c3.energy == "Achieved Energy" and c3.signal_columns == ["SCA1_1"] and c3.reference_pair == ["I1", "I2"]
    assert {"dead_time_correction_not_applied", "dead_detector_elements_excluded", "channel_choice_needs_review"} <= set(c3.flags)
    assert {a["mode"] for a in c3.alternatives} == {"fluorescence", "transmission"}
    ref = choose_channels(xd, params=params, role="reference")
    assert ref.mode == "transmission" and ref.signal_name == "ln(I0/I1)"


# --- end to end ------------------------------------------------------------------------------


def test_end_to_end_repeats_merge_outputs_hashed_and_relative(tmp_path):
    runs = [
        ("01_SYN_ZZ1_acid", [spec_file(fluo_scan(1)), spec_file(fluo_scan(2, spike=120))], {"sample_name": "ZZ1", "electrolyte_or_medium": "acid"}),
        ("02_SYN_ZZ1_acid", [spec_file(fluo_scan(3)), spec_file(fluo_scan(4))], {"sample_name": "ZZ1", "electrolyte_or_medium": "acid"}),
    ]
    bdir, root, _ = make_case(tmp_path, runs)
    groups = run_group(bdir)
    assert len(groups["record_groups"]) == 1 and (bdir / "record_groups.json").is_file()
    out = run_process(bdir, source_root=root)
    r = isaac(out)
    assert r["protocol_id"] == "isaac.xas.v0" and r["protocol_status"] == "draft_unreviewed" and r["state"] == "needs_review"
    assert [i["used"] for i in r["inputs"]] == [True] * 4
    assert step(r, "merge")["outcome"]["n_scans"] == 4
    dg = step(r, "deglitch")["outcome"]
    assert dg["would_exclude"]["points"] >= 1 and dg["excluded"] is False
    assert abs(r["outputs"]["edge_step"] - 0.015) / 0.015 < 0.05  # vortDT = mu * I0 * 0.01, mu/I0 -> step 1.5 * 0.01
    roles = {f["role"] for f in r["outputs"]["files"]}
    assert roles == {"merged", "normalized", "qc", "params", "plot"}
    for f in r["outputs"]["files"]:
        assert not Path(f["relative_path"]).is_absolute() and ".." not in f["relative_path"]
        assert f["relative_path"].startswith(f"processing/{r['group_id']}/")
        assert _sha(bdir / f["relative_path"]) == f["sha256"]
    out_path = {f["role"]: bdir / f["relative_path"] for f in r["outputs"]["files"]}
    assert all(f["relative_path"].startswith(f"processing/{r['group_id']}/{r['run_id']}/") for f in r["outputs"]["files"])
    merged = out_path["merged"].read_text().splitlines()
    assert merged[1] == "energy_eV,mu_mean,mu_std,mu_stderr,n_scans"
    assert r["qc"]["verdict"] in ("pass", "warn") and "glitches_flagged" in r["qc"]["reasons"]
    assert "calibration_reference_unconfirmed" in r["review_flags"]
    params = json.loads(out_path["params"].read_text())
    assert params["protocol_status"] == "draft_unreviewed" and "deglitch.exclude_flagged" in params["needs_scientist_approval"]
    saved = json.loads((bdir / "processing" / "processing_results.json").read_text())
    assert saved["summary"]["groups"] == 1


def test_source_hash_mismatch_is_skipped_not_used(tmp_path):
    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(fluo_scan(1)), spec_file(fluo_scan(2))], {"sample_name": "ZZ1"})])
    (root / "01_SYN_ZZ1_dir" / "01_SYN_ZZ1_002.dat").write_text(spec_file(fluo_scan(9)))
    r = isaac(run_process(bdir, source_root=root))
    assert r["inputs"][1]["skip_reason"] == "source_hash_mismatch" and step(r, "merge")["outcome"]["n_scans"] == 1


def test_calibration_shift_needs_a_scientist_approval_not_a_params_file(tmp_path):
    scans = [spec_file(fluo_scan(s, ref_e0=E0 + 2.0)) for s in (1, 2)]
    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = isaac(run_process(bdir, source_root=root))
    cal = step(r, "calibration")
    assert cal["outcome"]["reference_source"] == "in_scan_reference_channel"
    assert cal["outcome"]["measured_reference_e0_eV"] == pytest.approx(E0 + 2.0, abs=0.6)
    assert cal["outcome"]["applied_shift_eV"] == 0.0 and "calibration_reference_unconfirmed" in cal["flags"]
    e0_unshifted = r["outputs"]["e0_eV"]
    gid = r["group_id"]
    # a params file only PROPOSES: shift computed, NOT applied, labelled params_file_value
    proposed = {"calibration": {"proposed_reference": {"element": "Ti", "edge": "K"}}}
    r2 = isaac(run_process(bdir, source_root=root, params=proposed))
    c2 = step(r2, "calibration")
    assert c2["outcome"]["reference"]["basis"] == "params_file_value" and not c2["outcome"]["reference_approved"]
    assert c2["outcome"]["computed_shift_eV"] == pytest.approx(-2.0, abs=0.6) and not c2["outcome"]["applied"]
    assert {"calibration_shift_awaiting_approval", "calibration_reference_unconfirmed"} <= set(c2["flags"])
    # the v0 key name is read as a proposal too, never as a confirmation
    legacy = isaac(run_process(bdir, source_root=root, params={"calibration": {"confirmed_reference": {"element": "Ti", "edge": "K"}}}))
    assert step(legacy, "calibration")["outcome"]["reference"]["basis"] == "params_file_value" and not step(legacy, "calibration")["outcome"]["applied"]
    # an approval without a named decider is ignored
    r3 = isaac(run_process(bdir, source_root=root, calibration_approvals={gid: {"element": "Ti", "edge": "K", "decided_by": " "}}))
    assert not step(r3, "calibration")["outcome"]["applied"] and "calibration_approval_incomplete_ignored" in step(r3, "calibration")["flags"]
    # the scientist's processing-approval decision applies it
    ok = {gid: {"element": "Ti", "edge": "K", "decided_by": "SYN Scientist", "decision_id": "dec-syn-1"}}
    r4 = isaac(run_process(bdir, source_root=root, calibration_approvals=ok))
    c4 = step(r4, "calibration")["outcome"]
    assert c4["applied"] and c4["reference"]["basis"] == "scientist_decision" and c4["reference"]["decided_by"] == "SYN Scientist"
    assert c4["tabulated_edge_eV"] == pytest.approx(4966.0)
    assert r4["outputs"]["e0_eV"] == pytest.approx(e0_unshifted + c4["applied_shift_eV"], abs=0.01)


def test_a_rerun_never_overwrites_an_earlier_runs_outputs(tmp_path):
    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(fluo_scan(1)), spec_file(fluo_scan(2))], {"sample_name": "ZZ1"})])
    r1 = isaac(run_process(bdir, source_root=root))
    before = {f["relative_path"]: f["sha256"] for f in r1["outputs"]["files"]}
    mtimes = {p: (bdir / p).stat().st_mtime_ns for p in before}
    same = isaac(run_process(bdir, source_root=root))
    assert same["run_id"] == r1["run_id"] and same["result_id"] == r1["result_id"]
    assert {p: (bdir / p).stat().st_mtime_ns for p in before} == mtimes  # identical run: nothing rewritten
    r2 = isaac(run_process(bdir, source_root=root, params={"normalize": {"pre2": -40.0}}))
    assert r2["run_id"] != r1["run_id"] and r2["result_id"] != r1["result_id"]
    assert r2["prior_run_ids"] == [r1["run_id"]]
    for p, h in before.items():  # the earlier (possibly approved) result is untouched
        assert hashlib.sha256((bdir / p).read_bytes()).hexdigest() == h
    assert all(".." not in f["relative_path"] for f in r2["outputs"]["files"])
    assert not list((bdir / "processing" / r1["group_id"]).glob(".staging-*"))
    assert (bdir / "processing" / r1["group_id"] / r1["run_id"] / "result.json").is_file()


def _foil_xdac(region, seed):
    rng = np.random.default_rng(seed)
    i0 = np.full(GRID.size, 1.0e5)
    i1 = i0 * np.exp(-(mu_edge(GRID, E0 + 3.0) + rng.normal(0, 0.001, GRID.size)))
    return xdac_file({"Requested Energy": GRID, "Achieved Energy": GRID, "I0": i0, "I1": i1}, region=region)


def test_foil_name_evidence_proposes_the_reference_but_only_an_approval_applies_it(tmp_path):
    unread = {"SYN_Ti_foil_A.001": _foil_xdac("TiK_SYNTHETIC_region.rgn", 1), "SYN_Ti_foil_A.002": _foil_xdac("TiK_SYNTHETIC_region.rgn", 2)}
    bdir, root, _ = make_case(tmp_path, [], unread=unread)
    out = run_process(bdir, source_root=root)
    r = out["unread_acquisition_results"][0]
    assert r["group_kind"] == "unread_acquisition" and r["channel_choice"]["mode"] == "transmission"
    cal = step(r, "calibration")
    o = cal["outcome"]
    assert o["reference"]["basis"] == "stated_by_evidence" and (o["reference"]["element"], o["reference"]["edge"]) == ("Ti", "K")
    assert o["computed_shift_eV"] == pytest.approx(-3.0, abs=0.6) and not o["applied"]
    assert "calibration_shift_awaiting_approval" in cal["flags"]
    approved = run_process(bdir, source_root=root, calibration_approvals={r["group_id"]: {"element": "Ti", "edge": "K", "decided_by": "SYN Scientist"}})
    o2 = step(approved["unread_acquisition_results"][0], "calibration")["outcome"]
    assert o2["applied"] and o2["applied_shift_eV"] == pytest.approx(-3.0, abs=0.6)

    tmp2 = tmp_path / "noedge"
    tmp2.mkdir()
    unread2 = {"SYN_Ti_foil_A.001": _foil_xdac("SYN_region.rgn", 1)}
    bdir2, root2, _ = make_case(tmp2, [], unread=unread2)
    r2 = run_process(bdir2, source_root=root2)["unread_acquisition_results"][0]
    c2 = step(r2, "calibration")
    assert not c2["outcome"]["applied"] and "calibration_reference_unconfirmed" in c2["flags"]
    assert c2["outcome"]["unconfirmed_reason"].startswith("edge_not_stated_uniquely")


# --- Athena-first ----------------------------------------------------------------------------


def _athena_prj(path: Path, groups):
    from larch import Group
    from larch.io import AthenaProject

    prj = AthenaProject()
    for label, e, mu in groups:
        g = Group(energy=e, mu=mu, label=label, filename=label)
        xafs.pre_edge(g, pre1=-50, pre2=-30, norm1=60, norm2=130, nnorm=2)
        prj.add_group(g)
    prj.save(str(path))


def _athena_case(tmp_path, groups, stem="01_SYN_ZZ1"):
    scans = [spec_file(fluo_scan(s)) for s in (1, 2)]
    bdir, root, bundle = make_case(tmp_path, [(stem, scans, {"sample_name": "ZZ1"})])
    for rel, gs in groups.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        _athena_prj(p, gs)
        bundle["unread_files"].append({"source_id": f"prj-{rel}", "relative_path": rel})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


def test_version_provenance_states_years_from_the_path_only():
    e = {"prj_relative_path": "SYN_norm/SYN_project_2099rev_2098rev.prj", "label": "SYN_x_1-3", "group_name": "g", "is_merge": False, "params": {}, "data_hash": "ab" * 32}
    p = A.version_provenance(e, ["SYN_x"])
    assert p["years_stated_in_path"] == ["2098", "2099"] and p["scan_selection"] == [1, 2, 3]
    assert p["prj_file_name"] == "SYN_project_2099rev_2098rev.prj"
    assert A.version_provenance({**e, "prj_relative_path": "SYN_v_2021_2023.prj"}, ["SYN_x"])["years_stated_in_path"] == ["2021", "2023"]


def test_protocol_questions_are_machine_readable_and_reach_params_json(tmp_path):
    ids = [q["question_id"] for q in P.PROTOCOL_QUESTIONS]
    assert len(ids) == len(set(ids)) and all(q["status"] == "open" and q["text"] and q["affects"] for q in P.PROTOCOL_QUESTIONS)
    topics = {q["topic"] for q in P.PROTOCOL_QUESTIONS}
    assert {"energy_column", "grouping.new_spot", "calibration.foil_shift_to_samples", "athena.e0_frame"} <= topics
    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(fluo_scan(1))], {"sample_name": "ZZ1"})])
    out = run_process(bdir, source_root=root)
    r = isaac(out)
    params = json.loads(next(bdir / f["relative_path"] for f in r["outputs"]["files"] if f["role"] == "params").read_text())
    assert params["protocol_questions"] == P.PROTOCOL_QUESTIONS == out["protocol"]["protocol_questions"]


def test_name_matching_rules_and_scan_selection():
    assert A.normalise_name("SYN Run-01.txt") == "syn_run_01"
    assert A._match_kind(["01_syn_zz1"], "01_syn_zz1") == "exact"
    assert A._match_kind(["01_syn_zz1_5_6"], "01_syn_zz1") == "suffix"
    assert A._match_kind(["01_syn_zz1_merged"], "01_syn_zz1") == "suffix"
    assert A._match_kind(["01_syn_zz1_again"], "01_syn_zz1") is None
    assert A.scan_selection("01_SYN_ZZ1_5-6", ["01_SYN_ZZ1"]) == [5, 6]
    assert A.scan_selection("01_SYN_ZZ1_1-3_7", ["01_SYN_ZZ1"]) == [1, 2, 3, 7]
    assert A.scan_selection("SYN_x_A.003", ["SYN_x_A"]) == [3]
    assert A.scan_selection("01_SYN_ZZ1_again", ["01_SYN_ZZ1"]) is None


def test_athena_match_agree_and_scientist_result_preferred(tmp_path):
    mean = mu_edge(GRID) * 1e-2
    bdir, root = _athena_case(tmp_path, {"Athena/SYN.prj": [("01_SYN_ZZ1_1-2", GRID, mean)]})
    out = run_process(bdir, source_root=root)
    res = [r for r in out["processing_results"]]
    assert [r["source"] for r in res] == ["isaac_protocol", "scientist_athena"]
    isa, sci = res
    assert isa["comparison"]["verdict"] == "agree" and isa["comparison"]["athena_scan_selection"] == [1, 2]
    assert abs(isa["comparison"]["metrics"]["e0_delta_eV"]) <= 1.0 and isa["comparison"]["metrics"]["rms_norm"] <= 0.05
    assert sci["preferred_for_record"] is True and isa["preferred_for_record"] is False
    assert sci["steps"][0]["params"]["nor1"] == pytest.approx(60.0) and sci["state"] == "needs_review"
    assert sci["inputs"][0]["relative_path"] == "Athena/SYN.prj"
    assert "athena_normalized" in {f["role"] for f in isa["outputs"]["files"]}


def test_athena_differs_when_the_scientist_spectrum_is_shifted(tmp_path):
    bdir, root = _athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1", GRID, mu_edge(GRID, E0 + 3.0) * 1e-2)]})
    isa = isaac(run_process(bdir, source_root=root))
    assert isa["comparison"]["verdict"] == "differs" and "e0_differs" in isa["comparison"]["flags"]
    assert "athena_disagrees" in isa["review_flags"]


def test_athena_not_comparable_on_a_tiny_overlap(tmp_path):
    e = GRID[(GRID > 5080)]
    bdir, root = _athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1", e, mu_edge(e) * 1e-2)]})
    isa = isaac(run_process(bdir, source_root=root))
    assert isa["comparison"]["verdict"] == "not_comparable" and "overlap_too_small" in isa["comparison"]["flags"]


def test_athena_ambiguous_projects_mean_no_match(tmp_path):
    bdir, root = _athena_case(
        tmp_path,
        {"a/SYN_v1.prj": [("01_SYN_ZZ1", GRID, mu_edge(GRID) * 1e-2)], "b/SYN_v2.prj": [("01_SYN_ZZ1", GRID, mu_edge(GRID, E0 + 3) * 1e-2)]},
    )
    out = run_process(bdir, source_root=root)
    assert [r["source"] for r in out["processing_results"]] == ["isaac_protocol"]
    isa = out["processing_results"][0]
    assert isa["comparison"] is None and isa["athena_result_of_record"] is None
    assert any(n["code"] == "several_athena_groups_for_record_group" for n in out["athena"]["notes"])
    # every version listed with its stated provenance and compared; none selected
    vs = isa["athena_versions"]
    assert [v["provenance"]["prj_relative_path"] for v in vs] == ["a/SYN_v1.prj", "b/SYN_v2.prj"]
    assert vs[0]["provenance"]["prj_file_name"] == "SYN_v1.prj" and vs[0]["provenance"]["params"]["nor1"] == pytest.approx(60.0)
    assert {v["comparison"]["verdict"] for v in vs} <= {"agree", "differs", "not_comparable"} and vs[0]["comparison"]["verdict"] == "agree"
    assert vs[1]["comparison"]["verdict"] == "differs"
    q = isa["questions"][0]
    assert q["code"] == "which_athena_version_is_result_of_record" and q["version_ids"] == [v["version_id"] for v in vs]
    assert "athena_result_of_record_not_selected" in isa["review_flags"]
    roles = {f["role"] for f in isa["outputs"]["files"]}
    assert {"athena_version_01", "athena_version_02"} <= roles
    assert out["athena"]["record_groups_with_unselected_versions"] == 1


def test_athena_per_scan_groups_are_compared_as_a_set(tmp_path):
    groups = [("01_SYN_ZZ1_001", GRID, mu_edge(GRID) * 1e-2), ("01_SYN_ZZ1_002", GRID, mu_edge(GRID) * 1.01e-2)]
    bdir, root = _athena_case(tmp_path, {"SYN.prj": groups})
    out = run_process(bdir, source_root=root)
    isa = isaac(out)
    assert isa["comparison"]["athena_ref"]["match_kind"] == "per_scan_set"
    sci = out["processing_results"][1]
    assert sci["source"] == "scientist_athena"


def test_evaluation_harness_counts(tmp_path):
    bdir, root = _athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1", GRID, mu_edge(GRID) * 1e-2)]})
    run_process(bdir, source_root=root)
    rep = evaluate_folder(tmp_path)
    assert rep["files"] == 1
    o = rep["overall"]
    assert o["groups"] == 1 and o["athena_matched"] == 1 and o["comparison_verdicts"] == {"agree": 1}
    assert o["rms_norm"]["n"] == 1


def test_grouping_from_bundle_is_reused_by_processing(tmp_path):
    bdir, root, bundle = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(fluo_scan(1))], {"sample_name": "ZZ1"})])
    gid = G.propose_record_groups(bundle)[0]["group_id"]
    out = process_bundle(bdir, source_root=root, bundle=bundle, created_utc="2026-10-28T00:00:00Z")
    assert out["processing_results"][0]["group_id"] == gid and out["groups_origin"] == "proposed_now"
    assert "single_scan" in out["processing_results"][0]["qc"]["reasons"]


def test_zero_scan_runs_do_not_make_athena_matches_ambiguous():
    # Real-world shape: an exported ``x.dat`` became a zero-scan run whose name normalises
    # like the real run ``x``; it must not steal or block the match.
    entry = {"names": ["syn_run_7"], "label": "SYN_run_7.nor", "prj_relative_path": "SYN.prj", "data_hash": "h", "is_merge": False}
    groups = [
        {"group_id": "rg-real", "_stems": ["SYN_run_7"], "_has_scans": True},
        {"group_id": "rg-export", "_stems": ["SYN_run_7.dat"], "_has_scans": False},
    ]
    matched, notes = A.match(groups, [entry], np)
    assert list(matched) == ["rg-real"] and notes == []
