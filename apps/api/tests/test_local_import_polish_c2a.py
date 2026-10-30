"""Skill polish, cycle 2 (processing, measured on a real BL6-2c beamtime). Synthetic only.

* An Athena group the scientist imported as ALREADY-NORMALISED data (Athena's ``is_nor``) is not
  normalised again: larch's ``read_athena(do_preedge=True)`` re-ran the pre-edge fit over a
  post-edge range of zero width (``nor1 == nor2``), widened to 2 eV and fitted with a cubic, which
  gave an edge step of 25228 for a spectrum spanning 2.5 and a flattened curve sloping to -1.3. The
  stored spectrum IS the scientist's normalised curve (step 1 by definition).
* An edge step larger than twice the spectrum's whole range is never a ``pass``: QC fails
  ``edge_step_implausible`` with a plain sentence, and such an Athena curve is not compared,
  not overlaid and not preferred.
* A merge that keeps a scan which ends early warns ``scans_truncated``, with the counts and the
  scan named, and the result carries ``scan_range_truncated``.
* ``bundle list processing-results`` names each Athena version (id, project, group, label);
  ``bundle show <dir> processing-result <id>`` prints one result compactly (no arrays).
* A record's ``measurement.processing.steps`` lists only what was applied: an unapplied
  calibration and a one-scan "merge" are not processing steps.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R

from test_local_import_capture_decisions import _prov
from test_local_import_records import (  # noqa: F401  (fixtures)
    BY,
    SEMANTICS,
    _decide_everything,
    bdir,
    pristine,
)

np = pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")

import larch.xafs as xafs  # noqa: E402

from isaac_api.local_import.processing import core as C  # noqa: E402
from isaac_api.local_import.processing.cli_entry import run_process  # noqa: E402

from test_local_import_processing import E0, GRID, fluo_scan, isaac, make_case, spec_file, step  # noqa: E402

FINE = np.arange(4900.0, 5100.0 + 1e-9, 0.25)


def _normalised(seed=1, noise=0.01):
    """A SYNTHETIC already-normalised spectrum (pre-edge 0, post-edge 1) with noise."""
    rng = np.random.default_rng(seed)
    return 0.5 + np.arctan((FINE - E0) / 0.5) / np.pi + rng.normal(0, noise, FINE.size)


def _prj(path: Path, label: str, mu, args: dict) -> None:
    """An Athena project holding one group, its Athena args overridden by ``args``."""
    from larch import Group
    from larch.io import AthenaProject

    prj = AthenaProject()
    g = Group(energy=FINE, mu=mu, label=label, filename=label)
    xafs.pre_edge(g, pre1=-50, pre2=-30, norm1=60, norm2=130, nnorm=2)
    prj.add_group(g)
    next(iter(prj.groups.values())).args.update(args)
    prj.save(str(path))


#: what the real project stated: a post-edge range of zero width and a cubic
DEGENERATE = {"bkg_nor1": "120.0", "bkg_nor2": "120.0", "bkg_nnorm": "3"}


def _case(tmp_path, args, stem="01_SYN_ZZ1"):
    scans = [spec_file(fluo_scan(s)) for s in (1, 2)]
    bdir, root, bundle = make_case(tmp_path, [(stem, scans, {"sample_name": "ZZ1"})])
    _prj(root / "SYN.prj", f"{stem}.nor", _normalised(), args)
    bundle["unread_files"].append({"source_id": "prj-1", "relative_path": "SYN.prj"})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


def _results(out):
    isa = isaac(out)
    sci = next(r for r in out["processing_results"] if r["source"] == "scientist_athena")
    return isa, sci


# --- 1. Athena: already-normalised data, implausible edge steps --------------------------------------


def test_the_degenerate_post_edge_fit_really_gives_an_absurd_step():
    """The fixture reproduces the measured failure (otherwise the tests below prove nothing)."""
    from larch import Group

    g = Group()
    xafs.pre_edge(FINE, _normalised(), group=g, e0=E0, pre1=-50, pre2=-30, norm1=120.0, norm2=120.0, nnorm=3)
    assert g.edge_step > 1000


def test_an_athena_group_imported_as_normalised_data_is_used_as_stored(tmp_path):
    bdir, root = _case(tmp_path, {"is_nor": "1", **DEGENERATE})
    isa, sci = _results(run_process(bdir, source_root=root))
    assert sci["qc"]["metrics"]["edge_step"] == 1.0 and sci["qc"]["verdict"] != "fail"
    assert "already normalised" in sci["steps"][0]["params"]["reproduced_with"]
    cmp_ = isa["comparison"]
    assert cmp_["athena_ref"]["athena_data"] == "already_normalized"
    assert cmp_["verdict"] == "agree", cmp_
    assert "edge_step_scale_differs" not in cmp_["flags"] and "athena_disagrees" not in isa["review_flags"]
    # the overlay file is the scientist's stored curve, not a re-normalisation of it
    f = next(bdir / x["relative_path"] for x in isa["outputs"]["files"] if x["role"] == "athena_normalized")
    rows = [line.split(",") for line in f.read_text().splitlines()[2:]]
    assert float(rows[-1][1]) == pytest.approx(_normalised()[-1], abs=1e-6)
    assert float(rows[-1][2]) == pytest.approx(_normalised()[-1], abs=1e-6)


def test_an_implausible_athena_edge_step_is_a_fail_never_compared(tmp_path):
    bdir, root = _case(tmp_path, DEGENERATE)  # not flagged as normalised: larch's re-fit is all there is
    isa, sci = _results(run_process(bdir, source_root=root))
    assert sci["qc"]["metrics"]["edge_step"] > 1000
    assert sci["qc"]["verdict"] == "fail" and "edge_step_implausible" in sci["qc"]["reasons"]
    said = sci["qc"]["statements"]["edge_step_implausible"]
    assert "times the spectrum's whole range" in said and "nor1" in said
    assert sci["preferred_for_record"] is False
    cmp_ = isa["comparison"]
    assert cmp_["verdict"] == "not_comparable" and "athena_edge_step_implausible" in cmp_["flags"]
    assert "rms_norm" not in cmp_["metrics"] and "athena_disagrees" not in isa["review_flags"]
    assert cmp_["reason"].startswith("The scientist's Athena normalisation was not compared")


def test_edge_step_plausibility_bound():
    mu = np.concatenate([np.zeros(10), np.full(10, 2.5)])
    assert C.edge_step_implausible(2.4, mu, np) is None
    assert C.edge_step_implausible(4.9, mu, np) is None
    bad = C.edge_step_implausible(25228.58, mu, np)
    assert bad["ratio"] == pytest.approx(25228.58 / 2.5) and bad["max_ratio"] == C.EDGE_STEP_MAX_RANGE_RATIO
    assert C.edge_step_implausible(None, mu, np) is None  # a missing step fails on its own (edge_step_not_positive)
    flat = C.edge_step_implausible(1.0, np.zeros(10), np)
    assert flat["ratio"] is None and "flat" in flat["statement"]
    q = {"qc": {"fail_min_points": 20, "fail_i0_nonpositive_fraction": 0.5, "warn_pre_edge_noise": 0.05, "warn_scan_spread": 0.05,
                "warn_energy_shift_eV": 5, "warn_reference_e0_spread_eV": 1, "saturation_run_points": 5, "warn_min_scans": 2}}
    for ratio in (bad["ratio"], None):  # a flat spectrum's ratio is null: still a fail
        verdict, reasons = C.qc_verdict({"scans_used": None, "points": 200, "edge_step": 25228.58, "edge_step_implausible": ratio}, q)
        assert verdict == "fail" and "edge_step_implausible" in reasons
    assert C.qc_verdict({"scans_used": None, "points": 200, "edge_step": 1.0}, q) == ("pass", [])


# --- 3. a truncated scan is said ---------------------------------------------------------------------


def test_a_truncated_scan_warns_with_the_counts(tmp_path):
    short = GRID[:60]
    scans = [spec_file(fluo_scan(1)), spec_file(fluo_scan(2)), spec_file(fluo_scan(3, e=short))]
    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = isaac(run_process(bdir, source_root=root))
    assert r["qc"]["metrics"]["truncated_scans"] == 1 and r["qc"]["metrics"]["scans_used"] == 3
    assert r["qc"]["verdict"] == "warn" and "scans_truncated" in r["qc"]["reasons"]
    assert "scan_range_truncated" in r["review_flags"]
    said = r["qc"]["statements"]["scans_truncated"]
    sid = step(r, "merge")["outcome"]["truncated_scans"][0]
    assert said.startswith("1 of 3 scans used ends early") and sid in said and f"{short[-1]:.3f}" in said


def test_a_group_with_no_truncated_scan_says_nothing_new(tmp_path):
    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(fluo_scan(s)) for s in (1, 2)], {"sample_name": "ZZ1"})])
    r = isaac(run_process(bdir, source_root=root))
    assert "statements" not in r["qc"] and "scan_range_truncated" not in r["review_flags"]
    assert "edge_step_implausible" not in r["qc"]["metrics"]


# --- 2. Athena versions are findable -----------------------------------------------------------------


def _run(capsys, *argv):
    code = cli.main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def _with_versions(bdir: Path) -> None:
    _decide_everything(bdir)
    b = M.load(bdir)
    r = next(x for x in b["processing_results"] if x["result_id"] == "p1")
    r["athena_versions"] = [
        {"version_id": f"g1-v{n:02d}", "provenance": {**_prov(n), "scan_selection": [1, 3, 4, 5, 8]},
         "comparison": {"verdict": "differs", "flags": ["e0_differs"], "metrics": {"rms_norm": 0.1, "e0_delta_eV": 2.0, "overlap_eV": [1.0, 2.0]}}}
        for n in (1, 2)
    ]
    r["steps"] = [
        {"step": "merge", "params": {}, "outcome": {"n_scans": 2, "grid_eV": [1000.0, 1100.0], "truncated_scans": [],
                                                    "scan_rms": [0.1] * 12}, "flags": []},
        {"step": "normalize", "params": {}, "outcome": {"e0_eV": 1012.0}, "flags": []},
    ]
    M.save_bundle(bdir, b)


def test_list_processing_results_names_the_athena_versions(bdir, capsys):
    _with_versions(bdir)
    code, out, _ = _run(capsys, "bundle", "list", str(bdir), "processing-results")
    [row] = json.loads(out)["items"]
    assert code == 0 and row["athena_versions"] == 2
    first = row["athena_version_choices"][0]
    assert set(first) == {"version_id", "project", "group", "label"}
    assert first["version_id"] == "g1-v01" and first["project"] == "SYN_project_1.prj"  # the file name
    assert first["group"] == "SYN_grp_1" and first["label"] is None  # this provenance states no label


def test_show_processing_result_is_compact(bdir, capsys):
    _with_versions(bdir)
    code, out, _ = _run(capsys, "bundle", "show", str(bdir), "processing-result", "p1")
    view = json.loads(out)
    assert code == 0 and view["result_id"] == "p1" and view["group_id"] == "g1"
    assert [v["version_id"] for v in view["athena_versions"]] == ["g1-v01", "g1-v02"]
    v = view["athena_versions"][0]
    assert v["project"] == _prov(1)["prj_relative_path"] and v["comparison"]["verdict"] == "differs"
    assert v["scan_selection"] == "1,3-5,8"  # scan numbers are said whole, as ranges
    merge = next(s for s in view["steps"] if s["step"] == "merge")
    assert merge["outcome"]["grid_eV"] == [1000.0, 1100.0]
    assert merge["outcome"]["scan_rms"] == "12 values (not shown)"

    def lists(o):
        if isinstance(o, dict):
            return [x for v in o.values() for x in lists(v)]
        if isinstance(o, list):
            return [o] + [x for v in o for x in lists(v)]
        return []

    assert all(len(lst) <= 20 for lst in lists(view))  # no raw arrays
    code, _, err = _run(capsys, "bundle", "show", str(bdir), "processing-result", "nope")
    assert code != 0 and "No processing-result" in err


# --- 4. a record lists only the steps that were applied -----------------------------------------------


def _steps(bdir: Path, steps) -> list[str] | None:
    b = M.load(bdir)
    next(x for x in b["processing_results"] if x["result_id"] == "p1")["steps"] = steps
    M.save_bundle(bdir, b)
    R.build_records(bdir)
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    return (draft["fields"].get("measurement.processing.steps") or {}).get("value")


CAL_NOT_APPLIED = {"step": "calibration", "params": {}, "outcome": {"applied": False, "reference_source": None}, "flags": []}
MERGE = {"step": "merge", "params": {}, "outcome": {"n_scans": 3}, "flags": []}
NORM = {"step": "normalize", "params": {}, "outcome": {"e0_eV": 1012.0}, "flags": []}


def test_record_processing_steps_list_only_what_was_applied(bdir):
    _decide_everything(bdir)
    assert _steps(bdir, [CAL_NOT_APPLIED, MERGE, NORM]) == ["spectrum_merging", "normalization"]
    applied = {**CAL_NOT_APPLIED, "outcome": {"applied": True, "applied_shift_eV": 1.5}}
    assert _steps(bdir, [applied, MERGE, NORM]) == ["calibration", "spectrum_merging", "normalization"]
    one = {**MERGE, "outcome": {"n_scans": 1}}
    assert _steps(bdir, [CAL_NOT_APPLIED, one, NORM]) == ["normalization"]
