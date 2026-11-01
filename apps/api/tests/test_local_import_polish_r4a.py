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


def test_usable_edges_that_disagree_are_not_one_reference():
    step = _step([11213.1, 11219.2, 11220.0, 11221.0], [10.4, 11.0, 2.0, 1.5])
    r = REF.reading(step)
    assert r["reference_proposed"] is False and r["reference_edges_disagree"] is True
    assert r["reference_e0_spread_eV"] == pytest.approx(6.1) and r["reference_max_spread_eV"] == 0.5
    said = r["reference_statement"]
    assert "2 of 4 scans show a usable reference edge" in said and "spread over 6.10 eV (11213.1 to 11219.2 eV)" in said
    assert "more than the 0.5 eV they may differ by (qc.warn_reference_e0_spread_eV)" in said
    assert "no reference is proposed" in said
    # a reference group's own signal is judged by the same rule
    own = REF.reading(_step([11215.0, 11217.0], [300.0, 300.0], source="reference_group_own_signal"))
    assert own["reference_proposed"] is False and own["reference_edges_disagree"]
    # a stored stricter level is read (never a looser one)
    tight = _step([11215.0, 11215.3], [300.0, 300.0], reference_max_spread_eV=0.2)
    assert REF.reading(tight)["reference_proposed"] is False
    loose = _step([11215.0, 11216.0], [300.0, 300.0], reference_max_spread_eV=2.0)
    assert REF.reading(loose)["reference_proposed"] is False


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


def test_a_carried_shift_from_a_reference_no_longer_proposed_is_unconfirmed():
    step = _step([11213.1, 11219.2], [10.4, 11.0], applied=True, applied_shift_eV=-1.2,
                 reference={"element": "Ir", "edge": "L3", "basis": "scientist_decision"})
    c = REF.carried_shift(step, warn_eV=2.0, group_id="g1", result_id="p1")
    assert c is not None and not c["confirmed"]
    assert "spread over 6.10 eV" in c["reason"] and "--accept-shift -1.2" in c["statement"]


def test_the_r4a_rules_are_named_outside_the_hashed_files():
    ids = P.RULE_VERSIONS_SINCE_PROTOCOL_VERSION["rule_ids"]
    for rule in (REF.DEGENERATE_RULE_ID, REF.SPREAD_RULE_ID, REF.NEAR_SAMPLE_RULE_ID):
        assert rule in ids
    assert ids == sorted(ids)


def test_a_params_file_cannot_loosen_the_reference_spread_rule():
    said = REF.ignored_overrides({"qc": {"warn_reference_e0_spread_eV": 3.0}})
    assert len(said) == 1 and "still not proposed" in said[0]
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


def test_approve_calibration_is_refused_for_edges_that_disagree(bdir):
    gid = _with_result(bdir, [11213.1, 11219.2, 11220.0], [10.4, 11.0, 2.0])
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=[gid], decision="approve_calibration", value=None, element="Ir", edge="L3",
                 accept_shift=1.0, **BY)
    assert "spread over 6.10 eV" in str(exc.value) and "Nothing was recorded" in str(exc.value)
    assert _calibrations(bdir) == []


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


def test_processing_reference_edges_that_disagree_are_not_proposed_nor_applied(tmp_path):
    T = _proc()
    scans = [_ref_scan(T, 1, T.E0 + 8.0), _ref_scan(T, 2, T.E0 + 14.0)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    o = _cal(r)["outcome"]
    assert o["reference_proposed"] is False and o["reference_edges_disagree"] is True
    assert REF.SPREAD_FLAG in r["review_flags"] and "reference_e0_drift" in r["qc"]["reasons"]
    assert "spread over 6.00 eV" in o["reference_statement"]
    e0 = r["outputs"]["e0_eV"]
    r2 = T.isaac(T.run_process(bdir, source_root=root, calibration_approvals=_approval(r["group_id"], accepted_shift_eV=-11.0)))
    assert not _cal(r2)["outcome"]["applied"] and r2["outputs"]["e0_eV"] == pytest.approx(e0)
    curve = [{f["role"]: f["sha256"] for f in x["outputs"]["files"]}["normalized"] for x in (r, r2)]
    assert curve[0] == curve[1]  # nothing applied: the same curve (the approval itself is in the hashed step)


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
