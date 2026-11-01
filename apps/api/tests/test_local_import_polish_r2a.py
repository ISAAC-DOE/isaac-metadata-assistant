"""Polish r2-a: findings from a real-data run on an SSRL Pt L3 HERFD beamtime (223 SPEC runs). SYNTHETIC only: every
scan, name and value below is invented (``SYN_``/ZZ); the HERFD-like spectrum is an arctan edge plus a Gaussian white
line, not a measurement.

* (MED 1) With 4-5 scans the glitch check flagged points at E0 and on the white line (a sub-eV jitter between scans
  moves the steepest points by many robust scales): flagged points within 5 eV of E0 or where the merged curve is
  steep are listed apart and said as points on the edge, not glitches. The stored count, flag and verdict are those
  first written (qc.json is hashed into the result id), so no result id moves.
* (MED 2) A potentiostatic group with no set-point and no confirmed scale: the minimum said 1 answer (the set-point)
  and asked for the scale only after it. Both are named and counted now, and the scale question blocks the group.
"""

from __future__ import annotations

import io
import json
import shlex
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _cand, _decide_everything, _miss, _portal, bdir, fake_upstream, pristine)
from test_local_import_reader_ssrl_xdc import make_scan

POT = "context.electrochemistry.potential_setpoint_V"
SCALE = "context.electrochemistry.potential_scale"


def _quiet(*argv: str) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = cli.main(list(argv))
    return rc, buf.getvalue()


def _questions(bdir_: Path, *extra: str) -> dict:
    rc, out = _quiet("bundle", "questions", str(bdir_), *extra)
    assert rc == 0, out
    return json.loads(out)


def _proc():
    pytest.importorskip("numpy", reason="needs the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="needs the optional `processing` extra (xraylarch)")
    import test_local_import_processing as T

    return T


# --- MED 1: flagged points on the edge are not glitches ----------------------------------------------------------

SYN_E0 = 11564.0  # an invented edge position near a Pt L3 edge (eV)


def _herfd_grid(np):
    return np.concatenate([np.arange(11500.0, 11550.0, 2.0), np.arange(11550.0, 11590.0, 0.25), np.arange(11590.0, 11700.0, 1.0)])


def _herfd(np, e, *, shift=0.0, white_line=1.0):
    """A HERFD-like curve: a sharp arctan edge with a tall, narrow white line just above it (invented shape)."""
    x = e - shift
    return 0.05 + (0.5 + np.arctan((x - SYN_E0) / 0.7) / np.pi) + white_line * 1.8 * np.exp(-0.5 * ((x - SYN_E0 - 1.6) / 1.1) ** 2)


def _herfd_scans(np, e, *, spike_at=None):
    """Five scans; the third sits 0.2 eV off the others (energy jitter), heights vary by 2 %; optionally one spike."""
    M = np.vstack([_herfd(np, e, shift=(0.2 if s == 2 else 0.0), white_line=1 + 0.02 * (s - 2))
                   + np.random.default_rng(s).normal(0, 0.003, e.size) for s in range(5)])
    if spike_at is not None:
        M[3, int(np.searchsorted(e, spike_at))] += 0.3
    return M


def test_flagged_points_at_e0_and_on_the_white_line_are_on_the_edge():
    T = _proc()
    np = T.np
    from isaac_api.local_import.processing import core as C

    e = _herfd_grid(np)
    M = _herfd_scans(np, e, spike_at=11578.75)
    dg = C.deglitch(M, e, T.P.resolve_params(), np)
    assert dg["method"] == "cross_scan_median" and dg["flagged_points_total"] >= 3  # the edge IS flagged (stored as before)
    mean = C.merge(M, np=np)["mean"]
    points = C.glitch_points_on_edge(dg["point_flags"], e, e, mean, SYN_E0, np)
    assert len(points) == dg["flagged_points_total"]
    on = [en for _, en, edge in points if edge]
    off = [en for _, en, edge in points if not edge]
    assert on and all(abs(en - SYN_E0) <= 5.0 for en in on)
    assert off == [pytest.approx(11578.75)]  # a real spike off the edge stays a glitch
    # a spike ON a flat stretch is never made "steep" by itself: its own point is left out of its slope
    flat = np.linspace(0.0, 1.0, 50)
    spiky = flat.copy()
    spiky[30] += 5.0
    flags = np.zeros((1, 50), dtype=bool)
    flags[0, 30] = True
    assert C.glitch_points_on_edge(flags, np.arange(50.0), np.arange(50.0), spiky, None, np) == [(0, 30.0, False)]


def test_processing_lists_points_on_the_edge_apart_and_keeps_the_hashed_files(tmp_path):
    T = _proc()
    np = T.np
    e = _herfd_grid(np)
    M = _herfd_scans(np, e)
    i0 = np.full(e.size, 1.0e5)
    scans = [T.spec_file({"energy": e, "I0": i0, "vortDT": M[s] * i0 * 0.01}) for s in range(5)]
    bdir_, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir_, source_root=root))
    m = r["qc"]["metrics"]
    # stored as first written: the count, the reason and the verdict
    assert m["glitch_points"] >= 3 and r["qc"]["verdict"] == "warn" and "glitches_flagged" in r["qc"]["reasons"]
    assert m["glitch_points_on_edge"] == m["glitch_points"] and m["glitch_points_off_edge"] == 0
    said = r["qc"]["statements"]["glitch_points_on_edge"]
    assert f"{m['glitch_points']} of the {m['glitch_points']} flagged points lie on the edge" in said
    assert "points on the edge, not counted as glitches" in said and "(01_SYN_ZZ1_003.dat)" in said  # the jittered scan
    assert "No point off the edge is flagged" in said and "within 5 eV of E0" in said
    step = T.step(r, "deglitch")["outcome"]
    assert len(step["flagged_points_on_edge"]) == m["glitch_points"]
    assert all(abs(p["energy_eV"] - r["outputs"]["e0_eV"]) <= 5.0 for p in step["flagged_points_on_edge"])
    qc_file = next(f for f in r["outputs"]["files"] if f["role"] == "qc")
    text = (bdir_ / qc_file["relative_path"]).read_text()
    assert "on_edge" not in text and "glitches_flagged" in text  # hashed: no id moves
    # the compact row carries the split beside the stored count
    from isaac_api.local_import import cli

    row = cli._row("processing-results", r)
    assert row["metrics"]["glitch_points_on_edge"] == m["glitch_points"] and row["metrics"]["glitch_points_off_edge"] == 0


def test_a_result_with_no_point_on_the_edge_is_unchanged(tmp_path):
    T = _proc()
    bdir_, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", [T.spec_file(T.fluo_scan(s, spike=(300 if s == 1 else None))) for s in range(4)],
                                             {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir_, source_root=root))
    assert r["qc"]["metrics"]["glitch_points"] >= 1  # the spike sits 84 eV above the edge
    assert "glitch_points_on_edge" not in r["qc"]["metrics"] and "glitch_points_on_edge" not in (r["qc"].get("statements") or {})
    assert "flagged_points_on_edge" not in T.step(r, "deglitch")["outcome"]


# --- MED 2: a set-point and its scale are asked together -------------------------------------------------------


def _potentiostatic_no_setpoint(bdir_: Path) -> None:
    _decide_everything(bdir_)
    b = M.load(bdir_)
    M.decide(bdir_, target_ids=[_miss(b, B.CONTROL_MODE_PATH, "run-001")], decision="correct", value="potentiostatic", **BY)


def test_the_minimum_names_and_counts_the_setpoint_and_its_scale_together(bdir):
    _potentiostatic_no_setpoint(bdir)
    qs = _questions(bdir, "--scope", "group:g1", "--blocking-only")
    minimum = qs["minimum_for_one_group"]
    assert minimum["group_id"] == "g1"
    assert minimum["missing_required_now"] == [POT, SCALE]
    assert minimum["blocking_questions"] == 2 and len(minimum["questions"]) == 2
    by_field = {e["fields"][0]: e for e in minimum["questions"]}
    assert set(by_field) == {POT, SCALE}
    assert "asked now with it, so the scientist is not asked twice" in by_field[SCALE]["required_because"][SCALE]
    assert f"--field {SCALE}" in by_field[SCALE]["command"]
    # the scale question blocks this group now, so --blocking-only lists it beside the set-point's
    listed = {q["question_id"]: q for q in qs["questions"]}
    assert by_field[SCALE]["question_id"] in listed and listed[by_field[SCALE]["question_id"]]["blocking"] is True
    assert by_field[POT]["question_id"] in listed

    # answer the scale first, with the command the minimum named: only the set-point is left, counted once
    argv = shlex.split(by_field[SCALE]["command"].replace("<bundle_dir>", str(bdir))
                       .replace("<one of its allowed values>", "RHE").replace("<your name>", "Synthetic Scientist"))
    assert _quiet(*argv[1:])[0] == 0
    after = _questions(bdir, "--scope", "group:g1", "--blocking-only")["minimum_for_one_group"]
    assert after["missing_required_now"] == [POT] and after["blocking_questions"] == 1


def test_a_confirmed_setpoint_still_names_only_the_scale(bdir):
    # the c12-q state is unchanged: a confirmed set-point held back by its scale names the scale alone
    _potentiostatic_no_setpoint(bdir)
    M.decide(bdir, target_ids=[_cand(M.load(bdir), POT, "run-001")["candidate_id"]], decision="confirm", value=None, **BY)
    minimum = _questions(bdir, "--scope", "group:g1", "--blocking-only")["minimum_for_one_group"]
    assert minimum["missing_required_now"] == [SCALE] and minimum["blocking_questions"] == 1
