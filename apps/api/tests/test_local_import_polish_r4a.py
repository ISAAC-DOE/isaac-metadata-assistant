"""r4-a: XAS processing issues found on a real BL15-2 Ir L3 HERFD beamtime (87 runs, electrochemistry and chemical
standards), fixed on SYNTHETIC data only (every name and value below is invented).

* H1 — a calibration was proposed from reference channels whose pre-edge noise was about zero (edge step / noise
  1e13-1e14) and from usable edges 6 eV apart; an approval applied -1.2 eV to a chemical standard whose "reference
  edge" was its own E0.
* H2 — one scan's spike became the record's white line and E0, and the on-edge glitch rule shielded it.
* M6 — a dead scan could not be left out of a merge.
* L1 — ``process --group`` listed every other group's stored fixed-E0 result.
* L6 — ``channel_choice_needs_review`` had no sentence.

The stdlib tests run without numpy, larch or xraydb; the processing tests skip cleanly without them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import mutations as M
from isaac_api.local_import.processing import protocol as P
from isaac_api.local_import.processing import reference as REF

from test_local_import_records import BY, bdir, pristine  # noqa: F401  (fixtures)


def _step(e0s, snrs, source="in_scan_reference_channel", **outcome):
    return {"step": "calibration", "params": {"reference_min_edge_snr": 10.0, "max_plausible_shift_eV": 25.0},
            "outcome": {"reference_source": source, "reference_e0_per_scan_eV": list(e0s),
                        "reference_snr_per_scan": list(snrs), **outcome}}


# --- H1: the stored-step reading (stdlib) ---------------------------------------------------------------------------


def test_a_reference_channel_with_no_noise_is_not_usable():
    # invented: two "usable" scans at 1e13 / 4e13 times their noise, the others below the threshold of 10
    step = _step([11208.4, 11231.7, 11219.0, 11222.0], [1.3e13, 4.2e13, 2.0, 3.5])
    r = REF.reading(step)
    assert r["reference_proposed"] is False and r["calibration_proposed"] is False
    assert r["reference_scans_usable"] == 0 and r["reference_scans_degenerate"] == 2
    said = r["reference_statement"]
    assert said.startswith("2 scans' reference channels have an edge step more than 1,000,000 times their pre-edge noise")
    assert "not a measured edge" in said and "no reference is proposed" in said
    w = REF.would_apply(step, "Ir", "L3")
    assert w["shift_eV"] is None and "not counted as usable" in w["statement"]
    # one degenerate scan beside one good one: one usable scan is too few for an in-scan reference
    r1 = REF.reading(_step([11216.0, 11230.0], [400.0, 9e13]))
    assert r1["reference_proposed"] is False and r1["reference_scans_usable"] == 1
    assert "Only 1 of 2 scans shows a usable reference edge" in r1["reference_statement"]
    # a non-finite ratio is never usable either
    assert REF.degenerate_snr(float("inf")) and REF.degenerate_snr(2e6) and not REF.degenerate_snr(9.9e5)
    assert not REF.degenerate_snr(None)


def test_usable_edges_that_disagree_are_not_proposed_and_need_accept_shift():
    step = _step([11213.1, 11219.2, 11220.0, 11221.0], [10.4, 11.0, 2.0, 1.5])
    r = REF.reading(step)
    # the edge is read (approvable), but ISAAC does not offer it as the calibration
    assert r["reference_proposed"] is True and r["calibration_proposed"] is False and r["reference_edges_disagree"]
    assert r["reference_e0_spread_eV"] == pytest.approx(6.1) and r["reference_max_spread_eV"] == 0.5
    said = r["reference_statement"]
    assert "2 of 4 scans show a usable reference edge" in said
    assert ("Its usable edges spread 6.10 eV (11213.1 to 11219.2 eV; median 11216.2 eV of 2 scans), more than the 0.5 "
            "eV they may differ by (qc.warn_reference_e0_spread_eV), so ISAAC does not propose it as the reference") in said
    assert "Approve only if the reference is what you name, with --accept-shift <the shift approving shows>" in said
    # a small shift needs --accept-shift too, whatever its size
    w = REF.would_apply(step, "Ir", "L3", warn_eV=2.0)
    assert w["shown"] == "-1.2" and w["needs_size_confirmation"] and not w["needs_calibrant_confirmation"]
    assert "median 11216.2 eV of 2 scans" in w["statement"]
    assert "Approve only if the reference is what you name, with --accept-shift -1.2, whatever its size." in w["statement"]
    done = REF.would_apply(step, "Ir", "L3", warn_eV=2.0, accepted=-1.2)
    assert "You confirmed the shift's size (--accept-shift), so processing applies it." in done["statement"]
    assert "Approve only if" not in done["statement"]
    # a reference group's own signal is judged by the same rule
    own = REF.reading(_step([11215.0, 11217.0], [300.0, 300.0], source="reference_group_own_signal"))
    assert own["calibration_proposed"] is False and own["reference_edges_disagree"]
    # a stored stricter level is read (never a looser one)
    tight = _step([11215.0, 11215.3], [300.0, 300.0], reference_max_spread_eV=0.2)
    assert REF.reading(tight)["calibration_proposed"] is False
    loose = _step([11215.0, 11216.0], [300.0, 300.0], reference_max_spread_eV=2.0)
    assert REF.reading(loose)["calibration_proposed"] is False
    # edges that agree are offered as before
    assert REF.reading(_step([11215.0, 11215.3], [300.0, 300.0]))["calibration_proposed"] is True


def test_a_good_foil_is_still_proposed_and_the_reply_says_the_spread():
    step = _step([11216.2, 11216.4, 11216.3, 11240.0], [400.0, 380.0, 410.0, 2.0])
    r = REF.reading(step)
    assert r["reference_proposed"] and r["reference_scans_usable"] == 3
    assert "reference_scans_degenerate" not in r and "reference_edges_disagree" not in r
    assert "reference_at_sample_e0_eV" not in r
    w = REF.would_apply(step, "Ir", "L3", warn_eV=2.0)
    assert w["shown"] == "-1.3" and not w["needs_size_confirmation"]
    assert "That reference edge is the median of 3 usable scans (11216.3 eV, spread 0.20 eV)." in w["statement"]


def test_a_reference_edge_at_the_samples_own_e0_is_said_and_needs_its_size_confirmed():
    step = _step([11216.3, 11216.4], [400.0, 380.0], sample_e0_eV=11216.2)
    r = REF.reading(step)
    assert r["reference_proposed"] and r["reference_at_sample_e0_eV"] == pytest.approx(11216.2)
    assert "the reference channel may be seeing the sample" in r["reference_statement"]
    w = REF.would_apply(step, "Ir", "L3", warn_eV=2.0)
    assert w["shown"] == "-1.3" and w["needs_size_confirmation"] and not w["needs_calibrant_confirmation"]
    assert "may be seeing the sample" in w["statement"] and "--accept-shift -1.3" in w["statement"]
    done = REF.would_apply(step, "Ir", "L3", warn_eV=2.0, accepted=-1.3)
    assert "--accept-shift -1.3)" not in done["statement"]
    # 1 eV away from the sample's E0 is not "at" it
    far = REF.reading(_step([11216.3, 11216.4], [400.0, 380.0], sample_e0_eV=11217.4))
    assert "reference_at_sample_e0_eV" not in far and "seeing the sample" not in far["reference_statement"]


def test_a_carried_shift_from_edges_that_disagree_is_unconfirmed_until_its_size_is():
    step = _step([11213.1, 11219.2], [10.4, 11.0], applied=True, applied_shift_eV=-1.2,
                 reference={"element": "Ir", "edge": "L3", "basis": "scientist_decision"})
    c = REF.carried_shift(step, warn_eV=2.0, group_id="g1", result_id="p1")
    assert c is not None and not c["confirmed"]
    assert "spread over 6.10 eV" in c["reason"] and "--accept-shift -1.2" in c["statement"]
    assert REF.carried_shift({**step, "outcome": {**step["outcome"], "accepted_shift_eV": -1.2}}, warn_eV=2.0)["confirmed"]


def test_the_r4a_rules_are_named_outside_the_hashed_files():
    ids = P.RULE_VERSIONS_SINCE_PROTOCOL_VERSION["rule_ids"]
    for rule in (REF.DEGENERATE_RULE_ID, REF.SPREAD_RULE_ID, REF.NEAR_SAMPLE_RULE_ID):
        assert rule in ids
    assert ids == sorted(ids)


def test_a_params_file_cannot_loosen_the_reference_spread_rule():
    said = REF.ignored_overrides({"qc": {"warn_reference_e0_spread_eV": 3.0}})
    assert len(said) == 1 and "still not proposed, and approving it still needs --accept-shift" in said[0]
    assert REF.ignored_overrides({"qc": {"warn_reference_e0_spread_eV": 0.3}}) == []
    assert REF.effective_max_spread_eV(3.0) == 0.5 and REF.effective_max_spread_eV(0.3) == 0.3


# --- H1: approve_calibration on a stored result ---------------------------------------------------------------------


def _with_result(bdir: Path, e0s, snrs, **outcome) -> str:
    b = M.load(bdir)
    run = b["runs"][0]
    b["record_groups"].append({"group_id": "g1", "experiment_key": "exp", "member_run_keys": [run["run_key"]],
                               "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}},
                               "split_reasons": [], "status": "proposed", "questions": []})
    b["processing_results"].append(
        {"result_id": "p1", "group_id": "g1", "protocol_id": "isaac.xas.v0", "protocol_version": "0.1",
         "protocol_status": "draft_unreviewed", "source": "isaac_protocol", "inputs": [],
         "steps": [_step(e0s, snrs, **outcome), {"step": "qc", "params": {"warn_energy_shift_eV": 2.0}, "outcome": {}, "flags": []}],
         "outputs": {"files": [], "e0_eV": 11216.0, "edge_step": 1.0, "points": 21},
         "qc": {"metrics": {}, "verdict": "warn"}, "comparison": None, "state": "needs_review"})
    M.save_bundle(bdir, b)
    return "g1"


def _calibrations(bdir):
    return [d for d in M.load(bdir)["scientist_decisions"] if d["decision"] == "approve_calibration"]


def test_approve_calibration_is_refused_for_a_degenerate_reference(bdir):
    gid = _with_result(bdir, [11208.4, 11231.7, 11219.0], [1.3e13, 4.2e13, 2.0])
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=[gid], decision="approve_calibration", value=None, element="Ir", edge="L3", **BY)
    assert "pre-edge noise" in str(exc.value) and "Nothing was recorded" in str(exc.value)
    assert _calibrations(bdir) == []


def test_approve_calibration_of_edges_that_disagree_needs_accept_shift_whatever_the_size(bdir):
    gid = _with_result(bdir, [11213.1, 11219.2, 11220.0], [10.4, 11.0, 2.0])
    args = dict(target_ids=[gid], decision="approve_calibration", value=None, element="Ir", edge="L3", **BY)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, **args)  # -1.2 eV: under the warning level, still refused without --accept-shift
    said = str(exc.value)
    assert "Its usable edges spread 6.10 eV" in said and "median 11216.2 eV of 2 scans" in said
    assert "--accept-shift -1.2" in said and "Nothing was recorded" in said
    with pytest.raises(M.MutationRefused):
        M.decide(bdir, **args, accept_shift=1.0)
    assert _calibrations(bdir) == []
    out = M.decide(bdir, **args, accept_shift=-1.2)
    assert "approving applies -1.2 eV" in out["statement"] and "spread 6.10 eV" in out["statement"]
    [d] = _calibrations(bdir)
    assert d["value"] == {"accepted_shift_eV": -1.2}


def test_approve_calibration_of_a_good_foil_says_the_spread(bdir):
    gid = _with_result(bdir, [11216.2, 11216.4, 11216.3], [400.0, 380.0, 410.0])
    out = M.decide(bdir, target_ids=[gid], decision="approve_calibration", value=None, element="Ir", edge="L3", **BY)
    assert "approving applies -1.3 eV" in out["statement"] and "spread 0.20 eV" in out["statement"]
    assert len(_calibrations(bdir)) == 1


def test_approve_calibration_of_a_reference_at_the_sample_e0_needs_accept_shift(bdir):
    gid = _with_result(bdir, [11216.3, 11216.4], [400.0, 380.0], sample_e0_eV=11216.2)
    args = dict(target_ids=[gid], decision="approve_calibration", value=None, element="Ir", edge="L3", **BY)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, **args)
    assert "may be seeing the sample" in str(exc.value) and "--accept-shift -1.3" in str(exc.value)
    assert _calibrations(bdir) == []
    out = M.decide(bdir, **args, accept_shift=-1.3)
    assert "approving applies -1.3 eV" in out["statement"]


# --- H1: processing (numpy + larch) ---------------------------------------------------------------------------------


def _proc():
    pytest.importorskip("numpy", reason="needs the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="needs the optional `processing` extra (xraylarch)")
    import test_local_import_processing as T

    return T


def _ref_scan(T, seed, ref_e0, *, e0=None, ref_noise=0.002, degenerate=False):
    """A fluorescence scan with an in-scan reference (I1/I2) edge at ``ref_e0``: noisy (``ref_noise``), or a step whose
    pre-edge noise is about zero (``degenerate``: a channel that is not counting)."""
    import numpy as np

    cols = T.fluo_scan(seed, e0=T.E0 if e0 is None else e0, ref_e0=ref_e0)
    if degenerate:
        rng = np.random.default_rng(200 + seed)
        cols["I2"] = cols["I1"] * np.exp(-np.where(T.GRID >= ref_e0, 1.5, 0.5)) + rng.uniform(0, 1e-5, T.GRID.size)
    else:
        rng = np.random.default_rng(100 + seed)
        mu_ref = T.mu_edge(T.GRID, ref_e0, step=1.0, offset=0.5) + rng.normal(0, ref_noise, T.GRID.size)
        cols["I2"] = cols["I1"] * np.exp(-mu_ref)
    return T.spec_file(cols)


def _cal(r):
    return next(s for s in r["steps"] if s["step"] == "calibration")


def _hashed(bdir, r, role):
    f = next(f for f in r["outputs"]["files"] if f["role"] == role)
    return json.loads((bdir / f["relative_path"]).read_text())


def _approval(gid, **extra):
    return {gid: {"element": "Ti", "edge": "K", "decided_by": "SYN Scientist", "decision_id": "d-1", **extra}}


def test_processing_a_degenerate_reference_is_not_proposed_nor_applied(tmp_path):
    T = _proc()
    scans = [_ref_scan(T, s, T.E0 + 8.0 + s, degenerate=True) for s in (1, 2, 3)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    o = _cal(r)["outcome"]
    assert o["reference_proposed"] is False and o["reference_scans_degenerate"] == 3 and o["reference_scans_usable"] == 0
    assert REF.DEGENERATE_FLAG in r["review_flags"] and "calibration_shift_awaiting_approval" not in r["review_flags"]
    assert "pre-edge noise" in o["reference_statement"]
    # hashed as the earlier rule read it (the three edges' median and spread): an unchanged curve keeps its id
    hashed = _hashed(bdir, r, "params")["calibration"]
    assert hashed["measured_reference_e0_eV"] == pytest.approx(T.E0 + 10.0, abs=0.6)
    assert "reference_scans_degenerate" not in hashed and hashed["computed_shift_eV"] is None
    # ...and the verdict reads the same spread, so the result keeps the id the earlier rule gave it
    assert "reference_e0_drift" in r["qc"]["reasons"] and o["reference_e0_spread_eV"] == hashed["reference_e0_spread_eV"]
    e0 = r["outputs"]["e0_eV"]
    r2 = T.isaac(T.run_process(bdir, source_root=root, calibration_approvals=_approval(r["group_id"], accepted_shift_eV=-10.0)))
    o2 = _cal(r2)["outcome"]
    assert not o2["applied"] and o2["applied_shift_eV"] == 0.0 and r2["outputs"]["e0_eV"] == pytest.approx(e0)
    said = r2["qc"]["statements"]["calibration_approval_not_applied"]
    assert "d-1" in said and "is not applied" in said and "pre-edge noise" in said


def test_processing_reference_edges_that_disagree_apply_only_with_their_size_confirmed(tmp_path):
    T = _proc()
    # a foil drifting between scans: edges 1 eV apart, a small shift (-1.0 eV) that still needs --accept-shift
    scans = [_ref_scan(T, 1, T.E0 + 0.5, ref_noise=0.001), _ref_scan(T, 2, T.E0 + 1.5, ref_noise=0.001)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    o = _cal(r)["outcome"]
    assert o["reference_proposed"] is True and o["calibration_proposed"] is False and o["reference_edges_disagree"]
    assert REF.SPREAD_FLAG in r["review_flags"] and "calibration_shift_awaiting_approval" not in r["review_flags"]
    assert "Its usable edges spread 1.00 eV" in o["reference_statement"]
    e0 = r["outputs"]["e0_eV"]
    shift = REF.would_apply(_cal(r), "Ti", "K")["shown"]
    assert float(shift) == pytest.approx(-1.0, abs=0.3)
    plain = T.isaac(T.run_process(bdir, source_root=root, calibration_approvals=_approval(r["group_id"])))
    assert not _cal(plain)["outcome"]["applied"] and plain["outputs"]["e0_eV"] == pytest.approx(e0)
    assert REF.SPREAD_NOT_CONFIRMED_FLAG in plain["review_flags"]
    said = plain["qc"]["statements"]["calibration_approval_not_applied"]
    assert "d-1" in said and "spread 1.00 eV" in said and f"--accept-shift {shift}" in said
    ok = T.isaac(T.run_process(bdir, source_root=root,
                               calibration_approvals=_approval(r["group_id"], accepted_shift_eV=float(shift))))
    o2 = _cal(ok)["outcome"]
    assert o2["applied"] and REF.SPREAD_NOT_CONFIRMED_FLAG not in ok["review_flags"]
    assert ok["outputs"]["e0_eV"] == pytest.approx(e0 + o2["applied_shift_eV"], abs=0.01)
    assert "The scientist confirmed the shift's size" in o2["reference_statement"]


def test_processing_a_good_foil_is_proposed_and_applied_as_before(tmp_path):
    T = _proc()
    scans = [_ref_scan(T, s, T.E0 + 1.0, ref_noise=0.001) for s in (1, 2, 3)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    o = _cal(r)["outcome"]
    assert o["reference_proposed"] and o["reference_scans_usable"] == 3
    assert not {REF.DEGENERATE_FLAG, REF.SPREAD_FLAG, REF.NEAR_SAMPLE_FLAG} & set(r["review_flags"])
    assert "sample_e0_eV" in o and "sample_e0_eV" not in _hashed(bdir, r, "params")["calibration"]
    r2 = T.isaac(T.run_process(bdir, source_root=root, calibration_approvals=_approval(r["group_id"])))
    o2 = _cal(r2)["outcome"]
    assert o2["applied"] and o2["applied_shift_eV"] == pytest.approx(-1.0, abs=0.3)


def test_processing_a_reference_edge_at_the_samples_e0_is_applied_only_with_its_size_confirmed(tmp_path):
    T = _proc()
    scans = [_ref_scan(T, s, T.E0 + 1.0, e0=T.E0 + 1.0, ref_noise=0.001) for s in (1, 2, 3)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    o = _cal(r)["outcome"]
    assert o["reference_proposed"] and REF.NEAR_SAMPLE_FLAG in r["review_flags"]
    assert "may be seeing the sample" in o["reference_statement"]
    shift = REF.would_apply(_cal(r), "Ti", "K")["shown"]
    plain = T.isaac(T.run_process(bdir, source_root=root, calibration_approvals=_approval(r["group_id"])))
    assert not _cal(plain)["outcome"]["applied"] and REF.NEAR_SAMPLE_NOT_CONFIRMED_FLAG in plain["review_flags"]
    assert "may be seeing the sample" in plain["qc"]["statements"]["calibration_approval_not_applied"]
    ok = T.isaac(T.run_process(bdir, source_root=root,
                               calibration_approvals=_approval(r["group_id"], accepted_shift_eV=float(shift))))
    assert _cal(ok)["outcome"]["applied"]


# --- H2: one scan's spike is never the record's white line, and the on-edge rule never shields it --------------------

SYN_IR_E0 = 11216.0  # an invented edge position near an Ir L3 edge (eV)


def _herfd_grid(np):
    return np.concatenate([np.arange(11150.0, 11200.0, 2.0), np.arange(11200.0, 11240.0, 0.25),
                           np.arange(11240.0, 11350.0, 1.0)])


def _herfd(np, e, *, shift=0.0, white_line=1.0):
    """A HERFD-like curve: a sharp arctan edge with a tall, narrow white line just above it (invented shape)."""
    x = e - shift
    return (0.05 + (0.5 + np.arctan((x - SYN_IR_E0) / 0.7) / np.pi)
            + white_line * 1.8 * np.exp(-0.5 * ((x - SYN_IR_E0 - 1.6) / 1.1) ** 2))


def _five_scans(np, e, *, spike=1000.0):
    """Five scans (the third 0.2 eV off the others, heights 2 % apart); the fourth (position 3) carries a spike
    ``spike`` times its own value over the white line (11217-11219 eV)."""
    M = np.vstack([_herfd(np, e, shift=(0.2 if s == 2 else 0.0), white_line=1 + 0.02 * (s - 2))
                   + np.random.default_rng(s).normal(0, 0.003, e.size) for s in range(5)])
    if spike:
        wl = (e >= SYN_IR_E0 + 1.0) & (e <= SYN_IR_E0 + 3.0)
        M[3, wl] *= spike
    return M


def test_one_scans_spike_at_the_white_line_sets_the_merge_and_is_found():
    T = _proc()
    np = T.np
    from isaac_api.local_import.processing import core as C

    e = _herfd_grid(np)
    M = _five_scans(np, e)
    dom = C.single_scan_dominance(M, e, np)
    assert dom is not None and dom["scan_position"] == 3 and dom["ratio"] > 100
    assert SYN_IR_E0 + 1.0 <= dom["departs_eV"][0] <= dom["departs_eV"][1] <= SYN_IR_E0 + 3.0
    dg = C.deglitch(M, e, T.P.resolve_params(), np)
    one = C.glitch_points_from_one_scan(dg["point_flags"], e, M, np)
    assert one and {s for s, _ in one} == {3}
    mean = C.merge(M, dg["point_flags"], None, np)["mean"]
    ok = np.isfinite(mean)
    shielded = C.glitch_points_on_edge(dg["point_flags"], e, e[ok], mean[ok], SYN_IR_E0, np)
    judged = C.glitch_points_on_edge(dg["point_flags"], e, e[ok], mean[ok], SYN_IR_E0, np, M=M)
    assert any(at and s == 3 for s, _, at in shielded)  # v0: the spike on the white line was "on the edge"
    assert not any(at and (s, en) in one for s, en, at in judged)  # v1: one scan's glitch, never the edge
    # the same five scans without the spike: no scan sets the merge, and the jittered scan stays on the edge
    clean = _five_scans(np, e, spike=0.0)
    assert C.single_scan_dominance(clean, e, np) is None
    dg0 = C.deglitch(clean, e, T.P.resolve_params(), np)
    assert C.glitch_points_from_one_scan(dg0["point_flags"], e, clean, np) == set()


def test_a_scan_that_is_larger_everywhere_or_dead_does_not_set_the_merge():
    T = _proc()
    np = T.np
    from isaac_api.local_import.processing import core as C

    e = _herfd_grid(np)
    M = _five_scans(np, e, spike=0.0)
    gain = M.copy()
    gain[1] *= 30.0  # a gain step: larger everywhere, left to the outlier check
    assert C.single_scan_dominance(gain, e, np) is None
    two = np.vstack([M[0], np.where(e > 11230.0, 0.0, M[1] * 0.01)])  # two scans, one of them dead
    assert C.single_scan_dominance(two, e, np) is None
    assert C.single_scan_dominance(M[:1], e, np) is None


def _herfd_case(T, tmp_path, M, e, stem="01_SYN_ZZ1"):
    np = T.np
    i0 = np.full(e.size, 1.0e5)
    scans = [T.spec_file({"energy": e, "I0": i0, "vortDT": M[s] * i0 * 0.01}) for s in range(M.shape[0])]
    return T.make_case(tmp_path, [(stem, scans, {"sample_name": "ZZ1"})])


def test_processing_fails_a_curve_one_scan_sets_and_counts_its_points_on_the_edge_as_glitches(tmp_path):
    T = _proc()
    np = T.np
    e = _herfd_grid(np)
    bdir_, root, _ = _herfd_case(T, tmp_path, _five_scans(np, e), e)
    r = T.isaac(T.run_process(bdir_, source_root=root))
    q = r["qc"]
    assert q["verdict"] == "fail" and "edge_from_single_scan" in q["reasons"] and q["metrics"]["single_scan_span_ratio"] > 100
    assert "edge_from_single_scan" in r["review_flags"]
    said = q["statements"]["edge_from_single_scan"]
    assert said.startswith("One scan sets this merged curve: with 01_SYN_ZZ1_004.dat left out")
    assert "not usable as it is" in said and "belongs in the merge" in said
    # the spike's points on the white line are one scan's glitches: said apart, never "the check cannot judge them"
    one = q["statements"]["glitch_points_from_one_scan"]
    assert "come from one scan alone: 01_SYN_ZZ1_004.dat" in one and "counted as glitches" in one
    n_one = q["metrics"]["glitch_points_from_one_scan_on_edge"]
    assert n_one >= 3
    step = T.step(r, "deglitch")["outcome"]
    assert len(step["flagged_points_from_one_scan_on_edge"]) == n_one
    spikes = {(p["source_id"], p["energy_eV"]) for p in step["flagged_points_from_one_scan_on_edge"]}
    assert all(SYN_IR_E0 + 1.0 <= en <= SYN_IR_E0 + 3.0 for _, en in spikes)
    assert not spikes & {(p["source_id"], p["energy_eV"]) for p in step.get("flagged_points_on_edge") or ()}
    if "glitch_points_on_edge" in q["statements"]:
        assert f"{n_one} more on the edge are from one scan alone" in q["statements"]["glitch_points_on_edge"]
    assert step["glitch_edge_rule_id"].endswith(".v1")
    # the verdict is in the hashed qc.json (the curve fails): this result has a new id; the new sentences are not
    qc_file = next(f for f in r["outputs"]["files"] if f["role"] == "qc")
    text = (bdir_ / qc_file["relative_path"]).read_text()
    assert "edge_from_single_scan" in text and "glitch_points_from_one_scan" not in text


def test_processing_the_same_scans_without_the_spike_are_unchanged(tmp_path):
    T = _proc()
    np = T.np
    e = _herfd_grid(np)
    bdir_, root, _ = _herfd_case(T, tmp_path, _five_scans(np, e, spike=0.0), e)
    r = T.isaac(T.run_process(bdir_, source_root=root))
    q = r["qc"]
    assert "single_scan_span_ratio" not in q["metrics"] and "edge_from_single_scan" not in q["reasons"]
    assert "glitch_points_from_one_scan" not in (q.get("statements") or {})
    assert "flagged_points_from_one_scan_on_edge" not in T.step(r, "deglitch")["outcome"]


# --- M6: a named scan can be left out of a group's merge by a params file ------------------------------------------


def test_the_exclude_scans_section_is_read_apart_and_never_in_the_hashed_params():
    assert P.scan_exclusions(None) == {} and P.scan_exclusions({"qc": {"warn_min_scans": 3}}) == {}
    got = P.scan_exclusions({"exclude_scans": {"rg-1": ["a.dat", " b.dat ", "a.dat"], "rg-2": "c.dat#2"}})
    assert got == {"rg-1": ["a.dat", "b.dat"], "rg-2": ["c.dat#2"]}
    # resolve_params leaves it out: params.json of every other group is unchanged (no id moves)
    assert P.resolve_params({"exclude_scans": {"rg-1": ["a.dat"]}}) == P.resolve_params()
    for bad in ({"exclude_scans": ["a.dat"]}, {"exclude_scans": {"rg-1": []}}, {"exclude_scans": {"rg-1": [3]}}):
        with pytest.raises(ValueError, match="exclude_scans must be"):
            P.resolve_params(bad)


def _dead_from(T, seed, k):
    cols = T.fluo_scan(seed)
    cols["vortDT"] = T.np.where(T.np.arange(T.GRID.size) >= k, 0.0, cols["vortDT"])
    return T.spec_file(cols)


def test_processing_leaves_a_named_scan_out_and_says_how_from_the_zero_signal_statement(tmp_path):
    T = _proc()
    zz1 = [T.spec_file(T.fluo_scan(1)), T.spec_file(T.fluo_scan(2)), _dead_from(T, 3, 22)]
    zz2 = [T.spec_file(T.fluo_scan(s)) for s in (4, 5)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", zz1, {"sample_name": "ZZ1"}),
                                           ("02_SYN_ZZ2", zz2, {"sample_name": "ZZ2"})])
    first = T.run_process(bdir, source_root=root)
    a, other = (T.isaac(first, i) for i in (0, 1))
    if "01_SYN_ZZ1" not in a["inputs"][0]["relative_path"]:
        a, other = other, a
    gid = a["group_id"]
    said = a["qc"]["statements"]["merged_scan_zero_signal_points"]
    shape = {"exclude_scans": {gid: ["01_SYN_ZZ1_003.dat"]}}
    assert json.dumps(shape) in said
    assert f"`isaac process <bundle_dir> --source <the beamtime folder you imported> --group {gid} --params-file" in said
    # the scientist's answer, written as the sentence says, re-processes the group without that scan
    pf = tmp_path / "exclude.json"
    pf.write_text(json.dumps(shape))
    b = T.isaac(T.run_process(bdir, source_root=root, params_file=pf, group_ids=[gid]))
    assert b["group_id"] == gid and b["result_id"] != a["result_id"]
    assert [i.get("skip_reason") for i in b["inputs"]] == [None, None, "scans_excluded_by_params_file"]
    assert b["inputs"][2]["excluded_as"] == "01_SYN_ZZ1_003.dat"
    assert b["qc"]["metrics"]["scans_used"] == 2 and b["qc"]["metrics"]["scans_excluded_by_params_file"] == 1
    assert "merged_scan_zero_signal_points" not in b["qc"]["statements"]
    assert "scans_excluded_by_params_file" in b["review_flags"]
    assert b["qc"]["statements"]["scans_excluded_by_params_file"].startswith(
        "1 of 3 listed scans was left out of the merge by the params file (exclude_scans): 01_SYN_ZZ1_003.dat (scan 3).")
    params = _hashed(bdir, b, "params")
    assert params["excluded_scans"] == [{"source_id": b["inputs"][2]["source_id"], "relative_path": b["inputs"][2]["relative_path"],
                                         "scan": 3, "named_as": "01_SYN_ZZ1_003.dat"}]
    assert "exclude_scans" not in params["params"] and params["changed_from_default"] == []
    # the other group, processed with the same params file, keeps its id (its params.json is unchanged)
    again = T.run_process(bdir, source_root=root, params_file=pf)
    assert other["result_id"] in {r["result_id"] for r in again["processing_results"]}
    assert "excluded_scans" not in _hashed(bdir, other, "params")


def test_processing_says_an_exclusion_that_names_no_scan(tmp_path):
    T = _proc()
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", [T.spec_file(T.fluo_scan(s)) for s in (1, 2)], {"sample_name": "ZZ1"})])
    gid = T.isaac(T.run_process(bdir, source_root=root))["group_id"]
    r = T.isaac(T.run_process(bdir, source_root=root, params={"exclude_scans": {gid: ["SYN_typo.dat"]}}))
    said = r["qc"]["statements"]["scans_excluded_by_params_file"]
    assert "names 'SYN_typo.dat' for this group, which matches none of its scans" in said
    assert r["qc"]["metrics"]["scans_used"] == 2 and "scans_excluded_by_params_file" not in r["qc"]["metrics"]


def test_the_outlier_and_single_scan_statements_say_how_to_leave_the_scan_out(tmp_path):
    T = _proc()
    np = T.np
    e = _herfd_grid(np)
    bdir_, root, _ = _herfd_case(T, tmp_path, _five_scans(np, e), e)
    r = T.isaac(T.run_process(bdir_, source_root=root))
    hint = json.dumps({"exclude_scans": {r["group_id"]: ["01_SYN_ZZ1_004.dat"]}})
    assert hint in r["qc"]["statements"]["edge_from_single_scan"]
    assert '"01_SYN_ZZ1_004.dat"' in r["qc"]["statements"]["outlier_scans"]
    pf = tmp_path / "exclude.json"
    pf.write_text(hint)
    fixed = T.isaac(T.run_process(bdir_, source_root=root, params_file=pf, group_ids=[r["group_id"]]))
    assert "edge_from_single_scan" not in fixed["qc"]["reasons"] and fixed["qc"]["metrics"]["scans_used"] == 4


# --- L1: `process --group` says other groups' stored fixed-E0 results as one count ---------------------------------


def test_with_named_groups_only_their_stored_fixed_e0_results_are_listed():
    from isaac_api.local_import.processing import run as RUN
    from test_local_import_polish_r1ar import _groups, _pair

    stored = [r for g, e in (("g7", 2474.0), ("g8", 2475.0), ("g9", 2476.0)) for r in _pair(g, 2472.0, e)]
    bundle = {"processing_results": stored,
              "record_groups": [{"group_id": g, "status": "proposed"} for g in ("g1", "g7", "g8", "g9")]}
    out = RUN.possibly_fixed_athena_e0(_pair("g1", 2472.0, 2472.05), bundle, _groups(("g1", "SYN_S")))
    kept = out["kept_results"]
    assert [k["group_id"] for k in kept] == ["g7", "g8", "g9"]
    every = RUN.kept_fixed_e0_lines(kept, None)
    assert len(every) == 3 and all("carries a possibly fixed Athena E0" in x for x in every)
    named = RUN.kept_fixed_e0_lines(kept, {"g1", "g8"})
    assert len(named) == 2 and "proc-g8-" in named[0]
    assert named[1].startswith("Athena: 2 more stored results of 2 groups not processed now carry a possibly fixed")
    assert RUN.kept_fixed_e0_lines(kept, {"g1"})[0].startswith("Athena: 3 more stored results of 3 groups")
    assert RUN.kept_fixed_e0_lines(kept[:1], {"g1"}) == [
        "Athena: 1 more stored result of 1 group not processed now carries a possibly fixed Athena E0 (flag "
        "athena_e0_possibly_fixed); `isaac bundle list <bundle_dir> processing-results` lists them. Ask the scientist "
        "whether each E0 was measured before approving one."]


# --- L6: channel_choice_needs_review is said ------------------------------------------------------------------------


def test_the_channel_choice_flag_has_a_sentence():
    from isaac_api.local_import.processing.channels import ChannelChoice, needs_review_statement

    c = ChannelChoice(energy="energy", mode="fluorescence", signal_columns=["vortDT"], i0="I0",
                      basis={"basis": "channel_name_priority", "candidate": "vortDT",
                             "bl15_signal_selection_not_used": "SYN_no_proposal"},
                      alternatives=[{"mode": "fluorescence", "columns": ["vortDT"], "candidate": "vortDT"},
                                    {"mode": "fluorescence", "columns": ["PIPS"], "candidate": "PIPS"},
                                    {"mode": "transmission", "columns": ["I0", "I1"], "candidate": "transmission"}])
    said = needs_review_statement(c)
    assert said.startswith("ISAAC chose the fluorescence channel (vortDT)/I0 by column name (the first fluorescence "
                           "name present, 'vortDT'), not from a reading of the data")
    assert "the BL15-2 signal selector did not propose one it could use (SYN_no_proposal)" in said
    assert "The scan also has: fluorescence PIPS, transmission I0+I1." in said
    assert "A person confirms this is the channel the measurement used" in said


def test_processing_says_the_channel_choice_flag(tmp_path):
    T = _proc()
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", [T.spec_file(T.fluo_scan(s)) for s in (1, 2)], {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    assert "channel_choice_needs_review" in r["review_flags"]
    assert r["qc"]["statements"]["channel_choice_needs_review"].startswith("ISAAC chose the fluorescence channel (vortDT)/I0")
    qc_file = next(f for f in r["outputs"]["files"] if f["role"] == "qc")
    assert "channel_choice_needs_review" not in (bdir / qc_file["relative_path"]).read_text()  # hashed: no id moves
