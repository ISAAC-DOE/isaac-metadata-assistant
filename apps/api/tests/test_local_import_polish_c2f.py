"""Skill polish, cycle 2 (F): a reference group whose transmission channel is not positive. SYNTHETIC only.

Measured on a real BL4-3 beamtime: dilute standards (``std_*`` groups, sucrose pellets) are named as
standards, so they take role ``reference`` and the transmission channel ``ln(I0/I1)`` first, but they
were measured in fluorescence and their I1 is negative at every point. Every point was dropped and the
result said ``too_few_points`` for a 303-point scan.

* A scan whose chosen signal is non-finite (I0 or I1 not positive) is skipped as ``signal_not_finite``,
  with its ``points_read`` and ``nonfinite_dropped``, never ``too_few_points``; a scan that really has
  few points still says ``too_few_points``.
* When transmission leaves fewer than ``merge.min_points`` finite points in EVERY scan of the group, the
  next alternative channel (fluorescence) is used, flagged ``channel_fallback_transmission_not_positive``
  with a plain statement of what was tried and why it was abandoned; QC is at least ``warn``.
* Transmission that works in any scan is kept: no fallback.
* The curve made by the fallback is a NEW result id; a scientist's decision on the earlier failure stays
  on that failure and never carries over to the new curve.

Every spectrum is an invented arctan edge; every name is SYN_*.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")

from isaac_api.local_import import cli  # noqa: E402
from isaac_api.local_import import mutations as M  # noqa: E402
from isaac_api.local_import.processing import core as C  # noqa: E402
from isaac_api.local_import.processing import protocol as P  # noqa: E402
from isaac_api.local_import.processing import run as RUN  # noqa: E402
from isaac_api.local_import.processing.channels import choose_channels  # noqa: E402
from isaac_api.local_import.processing.cli_entry import run_group, run_process  # noqa: E402
from isaac_api.local_import.processing.readers import parse_text  # noqa: E402

from test_local_import_processing import GRID, isaac, make_case, mu_edge, xdac_file  # noqa: E402

BY = dict(by="Synthetic Scientist", orcid="0000-0002-1825-0097")
FALLBACK = "channel_fallback_transmission_not_positive"


def std_scan(seed, *, i1_positive=False, fluorescence=True, e=GRID):
    """A dilute standard: fluorescence carries the edge; I1 is negative (offset-subtracted) unless asked."""
    rng = np.random.default_rng(seed)
    i0 = np.full(e.size, 1.0e5)
    mu = mu_edge(e) + rng.normal(0, 0.002, e.size)
    i1 = i0 * np.exp(-mu) if i1_positive else np.full(e.size, -40.0) + rng.normal(0, 1.0, e.size)
    cols = {"Achieved Energy": e, "I0": i0, "I1": i1}
    if fluorescence:
        for k in (1, 2, 3):
            cols[f"SCA1_{k}"] = mu * i0 * 0.003 + rng.normal(0, 0.5, e.size)
    return cols


def _case(tmp_path, scans, stem="08_SYN_std_ZZ_sucrose"):
    bdir, root, _ = make_case(tmp_path, [(stem, [xdac_file(s) for s in scans], {"sample_name": "ZZ"})])
    groups = run_group(bdir)
    assert [g["role"] for g in groups["record_groups"]] == ["reference"]
    return bdir, root


# --- 1. a non-finite signal is named as such -------------------------------------------------------


def test_a_scan_whose_signal_is_never_finite_says_signal_not_finite_with_its_counts(tmp_path):
    bdir, root = _case(tmp_path, [std_scan(1, fluorescence=False), std_scan(2, fluorescence=False)])
    r = isaac(run_process(bdir, source_root=root))
    assert r["failure"] == {"code": "no_usable_scan", "detail": "signal_not_finite"}
    assert r["channel_choice"]["signal_name"] == "ln(I0/I1)" and FALLBACK not in r["review_flags"]  # nothing to fall back to
    for entry in r["inputs"]:
        assert entry["skip_reason"] == "signal_not_finite" and entry["used"] is False
        assert (entry["diagnostics"]["points_read"], entry["diagnostics"]["nonfinite_dropped"]) == (GRID.size, GRID.size)
    m = r["qc"]["metrics"]
    assert (m["points_read"], m["nonfinite_dropped"]) == (2 * GRID.size, 2 * GRID.size)


def test_a_scan_with_really_few_points_still_says_too_few_points(tmp_path):
    short = {k: v[:3] for k, v in std_scan(1, i1_positive=True, fluorescence=False).items()}
    bdir, root = _case(tmp_path, [short])
    r = isaac(run_process(bdir, source_root=root))
    assert r["failure"] == {"code": "no_usable_scan", "detail": "too_few_points"}
    assert r["inputs"][0]["skip_reason"] == "too_few_points" and "diagnostics" not in r["inputs"][0]
    assert r["qc"]["metrics"] == {}


# --- 2. fall back to fluorescence, never silently ---------------------------------------------------


def test_transmission_not_positive_in_every_scan_falls_back_to_fluorescence_and_says_so(tmp_path):
    bdir, root = _case(tmp_path, [std_scan(1), std_scan(2), std_scan(3)])
    r = isaac(run_process(bdir, source_root=root))
    cc = r["channel_choice"]
    assert cc["mode"] == "fluorescence" and cc["signal_name"] == "(SCA1_1+SCA1_2+SCA1_3)/I0"
    assert FALLBACK in cc["flags"] and FALLBACK in r["review_flags"]
    fb = cc["basis"]["fallback_from"]
    assert fb["mode"] == "transmission" and fb["signal_name"] == "ln(I0/I1)" and fb["min_points"] == 20
    assert [(s["points_read"], s["nonfinite_dropped"]) for s in fb["scans"]] == [(GRID.size, GRID.size)] * 3
    assert "ln(I0/I1)" in fb["statement"] and "not positive" in fb["statement"] and "(SCA1_1+SCA1_2+SCA1_3)/I0" in fb["statement"]
    assert [i["used"] for i in r["inputs"]] == [True] * 3 and {i["channel"] for i in r["inputs"]} == {cc["signal_name"]}
    assert not any("skip_reason" in i for i in r["inputs"])
    # a curve, judged; the fallback alone keeps it from a pass
    assert r["outputs"]["edge_step"] and r["outputs"]["edge_step"] > 0 and r["outputs"]["files"]
    assert r["qc"]["verdict"] in ("warn", "fail") and FALLBACK in r["qc"]["reasons"]
    assert r["qc"]["statements"][FALLBACK] == fb["statement"]
    assert r["qc"]["metrics"]["channel_fallback"] == "transmission_not_positive"
    qc = json.loads((bdir / next(f["relative_path"] for f in r["outputs"]["files"] if f["role"] == "qc")).read_text())
    assert qc["statements"][FALLBACK] == fb["statement"]


def test_a_fallback_alone_makes_a_clean_curve_warn_not_pass():
    params = P.resolve_params()
    clean = {"scans_used": 3, "points": 400, "edge_step": 1.0, "pre_edge_noise": 0.001}
    assert C.qc_verdict(clean, params) == ("pass", [])
    assert C.qc_verdict({**clean, "channel_fallback": "transmission_not_positive"}, params) == ("warn", [FALLBACK])


def test_transmission_that_works_in_one_scan_is_kept_no_fallback(tmp_path):
    bdir, root = _case(tmp_path, [std_scan(1), std_scan(2, i1_positive=True)])
    r = isaac(run_process(bdir, source_root=root))
    cc = r["channel_choice"]
    assert cc["signal_name"] == "ln(I0/I1)" and "fallback_from" not in cc["basis"]
    assert FALLBACK not in r["review_flags"] and FALLBACK not in r["qc"]["reasons"]
    assert [i.get("skip_reason") for i in r["inputs"]] == ["signal_not_finite", None]
    assert "channel_fallback" not in r["qc"]["metrics"] and "statements" not in r["qc"]


def test_transmission_that_works_everywhere_is_unchanged(tmp_path):
    bdir, root = _case(tmp_path, [std_scan(1, i1_positive=True), std_scan(2, i1_positive=True)])
    r = isaac(run_process(bdir, source_root=root))
    assert r["channel_choice"]["signal_name"] == "ln(I0/I1)" and r["channel_choice"]["basis"]["rule"] == "reference: transmission first"
    assert FALLBACK not in r["review_flags"] and "statements" not in r["qc"]
    assert all(i["used"] and "skip_reason" not in i for i in r["inputs"])


def test_choose_channels_can_leave_out_a_mode():
    params = P.resolve_params()
    t = parse_text(xdac_file(std_scan(1)))
    assert choose_channels(t, params=params, role="reference").mode == "transmission"
    c = choose_channels(t, params=params, role="reference", exclude_modes=("transmission",))
    assert c.mode == "fluorescence" and c.signal_columns == ["SCA1_1", "SCA1_2", "SCA1_3"]
    assert {a["mode"] for a in c.alternatives} == {"fluorescence", "transmission"}  # still listed for review


# --- 3. a decision on the earlier failure never moves to the new curve ------------------------------

XDAC_COLUMNS = ["Real time clock", "Requested Energy", "Achieved Energy", "I0", "I1", "SCA1_1", "SCA1_2", "SCA1_3"]


def _xdac(path: Path, cols: dict) -> None:
    """A SYNTHETIC SSRL EXAFS Data Collector 4.0 file (the layout the engine reader claims)."""
    n = len(cols["Achieved Energy"])
    cols = {"Real time clock": np.arange(n, dtype=float), "Requested Energy": cols["Achieved Energy"], **cols}
    names = [c for c in XDAC_COLUMNS if c in cols]
    lines = ["SSRL   EXAFS Data Collector 4.0".ljust(40), "Sun Jul 27 14:11:47 2025".ljust(40),
             f"PTS: {n:>10} COLS: {len(names):>10}", "synthetic.det".ljust(40), "synthetic.rgn".ljust(40),
             "99 token_a  0.000 0 X 1.500000 777".ljust(60), "5 1000 600 RST 0 0".ljust(60), "gain line literal".ljust(60),
             "SYNTHETIC FIXTURE", "", "Weights: ", " " + "  ".join(["1.000"] * len(names)), "Offsets: ",
             " " + "  ".join(["0.000"] * len(names)), "Data: ", *[c.ljust(18) for c in names], ""]
    lines += [" ".join(f"{cols[c][i]:.4f}" for c in names) for i in range(n)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("latin-1"))


def test_a_decision_on_the_earlier_failure_stays_on_it_and_the_new_curve_is_undecided(tmp_path, capsys):
    root = tmp_path / "SYN_beamtime"
    for k in (1, 2):
        _xdac(root / "bt" / f"08_SYN_std_ZZ_sucrose_030_A.00{k}", std_scan(k))
    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    capsys.readouterr()
    M.group(out)
    [g] = [g for g in M.load(out)["record_groups"] if g.get("role") == "reference"]
    # what the code before this fix stored for the group: a failure with no curve, then a scientist's decision on it
    old = RUN._fail(RUN._base(g, "isaac_protocol"), "no_usable_scan", "too_few_points")
    b = M.load(out)
    b["processing_results"] = [*(b.get("processing_results") or ()), {**old, "state": "needs_review"}]
    M.save_bundle(out, b)
    M.decide(out, target_ids=[old["result_id"]], decision="reject", value=None, note="transmission is wrong for this pellet", **BY)
    M.process(out, source=str(root))
    b = M.load(out)
    mine = [r for r in b["processing_results"] if r["group_id"] == g["group_id"] and r["source"] == "isaac_protocol"]
    kept = next(r for r in mine if r["result_id"] == old["result_id"])
    new = next(r for r in mine if r["result_id"] != old["result_id"])
    assert kept["failure"]["detail"] == "too_few_points" and kept["state"] == "rejected"
    assert FALLBACK in new["review_flags"] and new["outputs"]["files"] and new["state"] == "needs_review"
    targets = {d["target"]["id"] for d in b.get("scientist_decisions") or () if d["target"]["kind"] == "processing_result"}
    assert old["result_id"] in targets and new["result_id"] not in targets
