"""Polish c12-cal: a calibration shift is never baked in from noise, and its size is confirmed. SYNTHETIC only: every
scan, name and value is invented (``SYN_``/ZZ).

* (HIGH) An in-scan reference channel whose edge is usable (edge step / pre-edge noise >= 10) in only ONE scan of
  many is not a reference: no reference is proposed, no shift is applied even under an approval, the spread is
  null (not 0.0), and the usable/listed counts are said. Measured on a real beamtime: 1 of 16 scans at 10.5, the
  others 0.6-3.5, and an approval baked in -8.6 eV.
* (HIGH) ``approve_calibration`` says the shift it would apply, against the named element/edge's tabulated edge,
  before anything is recorded; a shift above ``qc.warn_energy_shift_eV`` needs ``--accept-shift <the value shown>``
  (else refused, nothing recorded), and processing applies such a shift only with the confirmed size. Smaller shifts
  behave as before.
* (MED) With fewer than 3 scans the glitch check compares neighbouring points and flags real features (white line,
  oscillations): a sentence says so beside the count; no verdict and no id moves.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import.processing import protocol as P
from isaac_api.local_import.processing import reference as REF

from test_local_import_records import BY, bdir, pristine  # noqa: F401  (fixtures)

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / ".claude" / "skills" / "isaac-historical-import"
#: the calibration outcome's keys as hashed into params.json before c12-cal (an unchanged curve keeps its id)
LEGACY_OUTCOME_KEYS = [
    "reference_source", "reference_e0_per_scan_eV", "reference_snr_per_scan", "measured_reference_e0_eV",
    "reference_e0_spread_eV", "reference", "reference_approved", "unconfirmed_reason", "tabulated_edge_eV",
    "tabulated_edge_source", "computed_shift_eV", "applied_shift_eV", "applied", "per_scan_alignment_shifts_eV", "method",
]


# --- the stored-step reading (stdlib; no numpy) ---------------------------------------------------------------------


def _step(e0s, snrs, source="in_scan_reference_channel"):
    return {"step": "calibration", "params": {"reference_min_edge_snr": 10.0, "max_plausible_shift_eV": 25.0},
            "outcome": {"reference_source": source, "reference_e0_per_scan_eV": list(e0s),
                        "reference_snr_per_scan": list(snrs)}}


def test_one_usable_in_scan_scan_proposes_no_reference_and_has_no_spread():
    e0s = [4964.6, 4974.599, 4985.5] + [4970.0] * 13
    snrs = [3.5, 10.46, 0.6] + [2.0] * 12 + [None]
    r = REF.reading(_step(e0s, snrs))
    assert (r["reference_scans_usable"], r["reference_scans_listed"], r["reference_proposed"]) == (1, 16, False)
    assert r["reference_e0_spread_eV"] is None and r["measured_reference_e0_eV"] == pytest.approx(4974.599)
    assert "Only 1 of 16 scans shows a usable reference edge" in r["reference_statement"]
    assert "no reference is proposed" in r["reference_statement"]
    w = REF.would_apply(_step(e0s, snrs), "Ti", "K")
    assert w["shift_eV"] is None and "Only 1 of 16 scans" in w["statement"]


def test_two_usable_scans_propose_and_say_the_would_be_shift():
    r = REF.reading(_step([4974.5, 4974.7, 4990.0], [40.0, 35.0, 2.0]))
    assert r["reference_proposed"] and r["reference_scans_usable"] == 2 and r["reference_e0_spread_eV"] == pytest.approx(0.2)
    w = REF.would_apply(_step([4974.5, 4974.7, 4990.0], [40.0, 35.0, 2.0]), "Ti", "K", warn_eV=2.0)
    assert w["shown"] == "-8.6" and w["needs_size_confirmation"] and not w["implausible"]
    assert "sits 8.6 eV above Ti K's tabulated 4966.0 eV; approving applies -8.6 eV" in w["statement"]
    assert "--accept-shift -8.6" in w["statement"]
    # a reference group's own signal needs only one scan; a small shift needs no size confirmation
    foil = REF.would_apply(_step([4966.205], [500.0], source="reference_group_own_signal"), "Ti", "K", warn_eV=2.0)
    assert foil["shown"] == "-0.2" and not foil["needs_size_confirmation"]
    assert REF.reading(_step([4966.205], [500.0], source="reference_group_own_signal"))["reference_e0_spread_eV"] is None


def test_the_shift_size_matches_to_a_tenth_of_an_ev():
    assert REF.shift_size_confirmed("-8.6", -8.599) and REF.shift_size_confirmed(-8.6, -8.64)
    assert not REF.shift_size_confirmed(-8.5, -8.599) and not REF.shift_size_confirmed("abc", -8.6)
    assert not REF.shift_size_confirmed(None, -8.6)


def test_the_rules_are_named_outside_the_hashed_files():
    ids = P.RULE_VERSIONS_SINCE_PROTOCOL_VERSION["rule_ids"]
    assert REF.IN_SCAN_MIN_RULE_ID in ids and REF.SHIFT_SIZE_RULE_ID in ids


# --- decide approve_calibration (a real bundle with a stored result) ----------------------------------------------


def _with_result(bdir: Path, e0s, snrs, *, source="in_scan_reference_channel") -> str:
    b = M.load(bdir)
    run = b["runs"][0]
    b["record_groups"].append({"group_id": "g1", "experiment_key": "exp", "member_run_keys": [run["run_key"]],
                               "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}},
                               "split_reasons": [], "status": "proposed", "questions": []})
    b["processing_results"].append(
        {"result_id": "p1", "group_id": "g1", "protocol_id": "isaac.xas.v0", "protocol_version": "0.1",
         "protocol_status": "draft_unreviewed", "source": "isaac_protocol", "inputs": [],
         "steps": [_step(e0s, snrs, source), {"step": "qc", "params": {"warn_energy_shift_eV": 2.0}, "outcome": {}, "flags": []}],
         "outputs": {"files": [], "e0_eV": 4978.0, "edge_step": 1.0, "points": 21},
         "qc": {"metrics": {}, "verdict": "warn"}, "comparison": None, "state": "needs_review"})
    M.save_bundle(bdir, b)
    return "g1"


def _calibrations(bdir):
    return [d for d in M.load(bdir)["scientist_decisions"] if d["decision"] == "approve_calibration"]


def test_approve_calibration_is_refused_when_no_reference_is_proposed(bdir):
    gid = _with_result(bdir, [4964.6, 4974.599] + [4970.0] * 14, [3.5, 10.46] + [2.0] * 14)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=[gid], decision="approve_calibration", value=None, element="Ti", edge="K", **BY)
    assert "Only 1 of 16 scans shows a usable reference edge" in str(exc.value) and "Nothing was recorded" in str(exc.value)
    assert _calibrations(bdir) == []


def test_a_large_shift_needs_accept_shift_matching_the_shift_shown(bdir):
    gid = _with_result(bdir, [4974.5, 4974.7], [40.0, 35.0])
    args = dict(target_ids=[gid], decision="approve_calibration", value=None, element="Ti", edge="K", **BY)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, **args)
    said = str(exc.value)
    assert "sits 8.6 eV above Ti K's tabulated 4966.0 eV; approving applies -8.6 eV" in said
    assert "--accept-shift -8.6" in said and "Nothing was recorded" in said
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, **args, accept_shift=-8.5)
    assert "-8.5" in str(exc.value) and "-8.6" in str(exc.value) and "Nothing was recorded" in str(exc.value)
    assert _calibrations(bdir) == []
    out = M.decide(bdir, **args, accept_shift=-8.6)
    assert "approving applies -8.6 eV" in out["statement"]
    [d] = _calibrations(bdir)
    assert d["value"] == {"accepted_shift_eV": -8.6}
    assert M.calibration_approvals(M.load(bdir))[gid]["accepted_shift_eV"] == -8.6


def test_a_small_shift_is_approved_as_before_and_said(bdir):
    gid = _with_result(bdir, [4966.205], [500.0], source="reference_group_own_signal")
    out = M.decide(bdir, target_ids=[gid], decision="approve_calibration", value=None, element="Ti", edge="K", **BY)
    assert "approving applies -0.2 eV" in out["statement"] and "calibration Ti K approved" in out["statement"]
    [d] = _calibrations(bdir)
    assert d["value"] is None and "accepted_shift_eV" not in M.calibration_approvals(M.load(bdir))[gid]


def test_accept_shift_goes_with_approve_calibration_only(bdir):
    gid = _with_result(bdir, [4966.205], [500.0], source="reference_group_own_signal")
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=[gid], decision="confirm", value=None, accept_shift=-0.2, **BY)
    assert "--accept-shift goes with" in str(exc.value)


def test_without_a_result_the_reply_says_the_size_rule(pristine, tmp_path):
    import shutil

    target = tmp_path / "b2"
    shutil.copytree(pristine, target)
    M.group(target)
    gid = M.load(target)["record_groups"][0]["group_id"]
    out = M.decide(target, target_ids=[gid], decision="approve_calibration", value=None, element="Ir", edge="L3", **BY)
    assert "no processing result" in out["statement"] and "--accept-shift" in out["statement"]


def test_the_cli_takes_accept_shift_and_show_says_the_reference(bdir, capsys):
    gid = _with_result(bdir, [4974.5, 4974.7], [40.0, 35.0])
    code = cli.main(["bundle", "decide", str(bdir), "--target", gid, "--decision", "approve_calibration",
                     "--element", "Ti", "--edge", "K", "--by", BY["by"]])
    err = capsys.readouterr().err
    assert code != 0 and "--accept-shift -8.6" in err
    assert cli.main(["bundle", "decide", str(bdir), "--target", gid, "--decision", "approve_calibration",
                     "--element", "Ti", "--edge", "K", "--accept-shift", "-8.6", "--by", BY["by"]]) == 0
    capsys.readouterr()
    assert cli.main(["bundle", "show", str(bdir), "processing-result", "p1"]) == 0
    view = json.loads(capsys.readouterr().out)
    cal = view["calibration"]
    assert cal["reference_proposed"] and cal["reference_scans_usable"] == 2 and cal["reference_scans_listed"] == 2
    [w] = cal["would_apply"]
    assert (w["element"], w["edge"], w["shown"], w["basis"]) == ("Ti", "K", "-8.6", "approved")
    assert "approving applies -8.6 eV" in w["statement"]


def test_show_names_the_groups_absorber_as_a_possible_reference(bdir, capsys):
    gid = _with_result(bdir, [4974.5, 4974.7], [40.0, 35.0])
    M.decide(bdir, target_ids=[gid], decision="set_absorber", value=None, element="Ti", edge="K", **BY)
    assert cli.main(["bundle", "show", str(bdir), "processing-result", "p1"]) == 0
    [w] = json.loads(capsys.readouterr().out)["calibration"]["would_apply"]
    assert w["basis"] == "group_absorber" and w["shown"] == "-8.6"


# --- the skill and the protocol doc ---------------------------------------------------------------------------------


def test_the_skill_says_the_counts_and_the_shift_before_asking():
    ref = (SKILL / "reference" / "grouping-and-processing.md").read_text()
    for term in ("reference_proposed", "reference_edge_in_too_few_scans", "--accept-shift", "would_apply",
                 "glitch_check_few_scans", "calibration_shift_size_not_confirmed"):
        assert term in ref, term
    skill = (SKILL / "SKILL.md").read_text()
    assert len(skill.splitlines()) <= 250
    assert "how many scans show a reference edge and the shift it would apply" in skill
    assert "glitch_check_few_scans" in skill
    doc = (REPO / "docs" / "xas-processing-protocol-v0.md").read_text()
    assert REF.IN_SCAN_MIN_RULE_ID in doc and REF.SHIFT_SIZE_RULE_ID in doc and "glitch_check_few_scans" in doc


# --- processing (numpy + larch) -------------------------------------------------------------------------------------


def _proc():
    pytest.importorskip("numpy", reason="needs the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="needs the optional `processing` extra (xraylarch)")
    import test_local_import_processing as T

    return T


def _ref_scan(T, seed, ref_e0, ref_noise=0.0, *, n=None):
    import numpy as np

    cols = T.fluo_scan(seed, ref_e0=ref_e0)
    if ref_noise:
        rng = np.random.default_rng(100 + seed)
        mu_ref = T.mu_edge(T.GRID, ref_e0, step=1.0, offset=0.5) + rng.normal(0, ref_noise, T.GRID.size)
        cols["I2"] = cols["I1"] * np.exp(-mu_ref)
    return T.spec_file(cols)


def _cal(r):
    return next(s for s in r["steps"] if s["step"] == "calibration")


def _params_cal(bdir, r):
    f = next(f for f in r["outputs"]["files"] if f["role"] == "params")
    return json.loads((bdir / f["relative_path"]).read_text())["calibration"]


def test_processing_one_usable_reference_scan_no_shift_even_when_approved(tmp_path):
    T = _proc()
    scans = [_ref_scan(T, 1, T.E0 + 8.0)] + [_ref_scan(T, s, T.E0 + 8.0, ref_noise=0.4) for s in (2, 3, 4)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    o = _cal(r)["outcome"]
    assert o["reference_scans_usable"] == 1 and o["reference_scans_listed"] == 4 and o["reference_proposed"] is False
    assert o["reference_e0_spread_eV"] is None and r["qc"]["metrics"]["reference_e0_spread_eV"] is None
    assert "Only 1 of 4 scans shows a usable reference edge" in o["reference_statement"]
    assert REF.TOO_FEW_FLAG in r["review_flags"] and o["computed_shift_eV"] is None
    # the hashed params.json keeps exactly the keys (and the 1-scan value) it had: an unchanged curve keeps its id
    hashed = _params_cal(bdir, r)
    assert list(hashed) == LEGACY_OUTCOME_KEYS and hashed["reference_e0_spread_eV"] == 0.0
    qc_file = next(f for f in r["outputs"]["files"] if f["role"] == "qc")
    assert json.loads((bdir / qc_file["relative_path"]).read_text())["metrics"]["reference_e0_spread_eV"] == 0.0
    e0 = r["outputs"]["e0_eV"]
    approved = {r["group_id"]: {"element": "Ti", "edge": "K", "decided_by": "SYN Scientist", "decision_id": "d-1"}}
    r2 = T.isaac(T.run_process(bdir, source_root=root, calibration_approvals=approved))
    o2 = _cal(r2)["outcome"]
    assert not o2["applied"] and o2["applied_shift_eV"] == 0.0 and o2["computed_shift_eV"] is None
    assert r2["outputs"]["e0_eV"] == pytest.approx(e0) and REF.TOO_FEW_FLAG in r2["review_flags"]


def test_processing_a_large_approved_shift_is_applied_only_with_its_size_confirmed(tmp_path):
    T = _proc()
    scans = [_ref_scan(T, s, T.E0 + 8.0) for s in (1, 2)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    o = _cal(r)["outcome"]
    assert o["reference_proposed"] and o["reference_scans_usable"] == 2 and o["reference_e0_spread_eV"] is not None
    assert list(_params_cal(bdir, r)) == LEGACY_OUTCOME_KEYS
    e0 = r["outputs"]["e0_eV"]
    gid = r["group_id"]
    shift = REF.would_apply(_cal(r), "Ti", "K")["shown"]
    assert float(shift) == pytest.approx(-8.0, abs=0.6)
    plain = {gid: {"element": "Ti", "edge": "K", "decided_by": "SYN Scientist", "decision_id": "d-1"}}
    r2 = T.isaac(T.run_process(bdir, source_root=root, calibration_approvals=plain))
    o2 = _cal(r2)["outcome"]
    assert not o2["applied"] and REF.SIZE_NOT_CONFIRMED_FLAG in r2["review_flags"]
    assert r2["outputs"]["e0_eV"] == pytest.approx(e0)
    wrong = {gid: {**plain[gid], "accepted_shift_eV": float(shift) + 1.0}}
    assert not _cal(T.isaac(T.run_process(bdir, source_root=root, calibration_approvals=wrong)))["outcome"]["applied"]
    ok = {gid: {**plain[gid], "accepted_shift_eV": float(shift)}}
    r3 = T.isaac(T.run_process(bdir, source_root=root, calibration_approvals=ok))
    o3 = _cal(r3)["outcome"]
    assert o3["applied"] and o3["accepted_shift_eV"] == float(shift)
    assert r3["outputs"]["e0_eV"] == pytest.approx(e0 + o3["applied_shift_eV"], abs=0.01)


def test_processing_a_small_approved_shift_is_applied_as_before(tmp_path):
    T = _proc()
    scans = [_ref_scan(T, s, T.E0 + 1.0) for s in (1, 2)]
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    gid = T.isaac(T.run_process(bdir, source_root=root))["group_id"]
    ok = {gid: {"element": "Ti", "edge": "K", "decided_by": "SYN Scientist", "decision_id": "d-1"}}
    r = T.isaac(T.run_process(bdir, source_root=root, calibration_approvals=ok))
    o = _cal(r)["outcome"]
    assert o["applied"] and "accepted_shift_eV" not in o and REF.SIZE_NOT_CONFIRMED_FLAG not in r["review_flags"]
    assert list(_params_cal(bdir, r)) == LEGACY_OUTCOME_KEYS


def test_processing_says_the_few_scan_glitch_check_flags_real_features(tmp_path):
    T = _proc()
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", [T.spec_file(T.fluo_scan(1, spike=150))], {"sample_name": "ZZ1"}),
                                           ("02_SYN_ZZ2", [T.spec_file(T.fluo_scan(s)) for s in (1, 2, 3)], {"sample_name": "ZZ2"})])
    out = T.run_process(bdir, source_root=root)
    by_stem = {}
    for r in out["processing_results"]:
        if r["source"] == "isaac_protocol":
            by_stem[r["inputs"][0]["relative_path"].split("/")[0]] = r
    one = by_stem["01_SYN_ZZ1_dir"]
    n = one["qc"]["metrics"]["glitch_points"]
    assert n >= 1 and one["qc"]["verdict"] == "warn" and "glitches_flagged" in one["qc"]["reasons"]
    said = one["qc"]["statements"]["glitch_check_few_scans"]
    assert said.startswith("With 1 scan, the glitch check compares neighbouring points")
    assert f"these {n} flag" in said and "not by themselves evidence of glitches" in said
    qc_file = next(f for f in one["outputs"]["files"] if f["role"] == "qc")
    assert "glitch_check_few_scans" not in (bdir / qc_file["relative_path"]).read_text()  # hashed: no id moves
    three = by_stem["02_SYN_ZZ2_dir"]
    assert "glitch_check_few_scans" not in (three["qc"].get("statements") or {})


def test_a_hash_of_the_params_file_is_what_the_result_names(tmp_path):
    T = _proc()
    bdir, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", [_ref_scan(T, 1, T.E0 + 8.0)], {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir, source_root=root))
    for f in r["outputs"]["files"]:
        assert hashlib.sha256((bdir / f["relative_path"]).read_bytes()).hexdigest() == f["sha256"]
