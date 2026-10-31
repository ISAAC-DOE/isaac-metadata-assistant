"""Polish c12-r: review findings on c12-cal. SYNTHETIC only: every scan, name and value is invented (``SYN_``/ZZ).

* (H1) A result approved under an older build may carry a calibration shift the current rules would not apply (an
  in-scan reference usable in 1 of 16 scans; a large shift whose size nobody confirmed). It is kept on re-processing
  (decided), so its curve still carries the shift. `show processing-result` says so with the way out (re-approve with
  --accept-shift, or reject the result), build-records / validate block that group until the scientist does one of
  them (never exported silently), and `approve_calibration --accept-shift <the carried size>` is how they confirm it.
  A re-processed result whose approval the current rules did not apply names that approval in a sentence.
* (H2) A run of zeros whose counts come back is said as a possible lost beam (with the flag) when it is at least 5 %
  of the scan (and 3 points); runs of 1-2 points are isolated dropouts; runs in between are counted with no claim.
* (M1) A params file may make the size confirmation and the in-scan SNR rule stricter, never looser; an ignored
  override is said.
* (M2/LOW) commands.md names --accept-shift; a null spread over a hashed 0.0 is explained; a shift near the warning
  level is shown and compared to 0.01 eV; the protocol doc says why a reference group needs 1 usable scan and an
  in-scan channel 2.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R
from isaac_api.local_import.processing import reference as REF

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _decide_everything, _portal, bdir, fake_upstream, pristine)
import test_local_import_polish_c12cal as C

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / ".claude" / "skills" / "isaac-historical-import"

#: the real-beamtime shape (1 of 16 in-scan scans usable), approved as Ti K by an older build: -8.6 eV baked in
E0S = [4964.6, 4974.599] + [4970.0] * 14
SNRS = [3.5, 10.46] + [2.0] * 14


def _baked(e0s=E0S, snrs=SNRS, applied=-8.599, accepted=None):
    step = C._step(e0s, snrs)
    step["outcome"].update({"reference": {"element": "Ti", "edge": "K", "basis": "scientist_decision",
                                          "decided_by": "SYN Scientist", "decision_id": "d-old"},
                            "reference_approved": True, "computed_shift_eV": applied, "applied_shift_eV": applied,
                            "applied": True})
    if accepted is not None:
        step["outcome"]["accepted_shift_eV"] = accepted
    return step


# --- H1: the shift a curve carries (stdlib) -------------------------------------------------------------------------


def test_a_shift_baked_in_from_one_usable_scan_is_said_as_unconfirmed():
    c = REF.carried_shift(_baked(), None, warn_eV=2.0, group_id="g1", result_id="p1")
    assert c["confirmed"] is False and c["shown"] == "-8.6"
    said = c["statement"]
    assert said.startswith("This curve carries -8.6 eV that is now unconfirmed: it was approved from a reference edge "
                           "usable in 1 of 16 scans")
    assert "--target g1 --decision approve_calibration --element Ti --edge K --accept-shift -8.6" in said
    assert "--target p1 --decision reject" in said
    # the scientist confirming that exact size (their latest approval) confirms it; another size does not
    assert REF.carried_shift(_baked(), {"accepted_shift_eV": -8.6}, warn_eV=2.0)["confirmed"] is True
    assert REF.carried_shift(_baked(), {"accepted_shift_eV": -8.0}, warn_eV=2.0)["confirmed"] is False


def test_a_large_shift_approved_without_its_size_is_unconfirmed_and_a_confirmed_one_is_not():
    two = ([4974.5, 4974.7], [40.0, 35.0])
    c = REF.carried_shift(_baked(*two), None, warn_eV=2.0)
    assert not c["confirmed"] and "more than the protocol's 2 eV warning level and its size was never confirmed" in c["reason"]
    assert REF.carried_shift(_baked(*two, accepted=-8.6), None)["confirmed"] is True
    # a small shift from ONE in-scan scan is unconfirmed too (no reference is proposed from one scan)
    assert REF.carried_shift(_baked([4966.205], [500.0], applied=-0.205), None)["confirmed"] is False
    foil = _baked([4966.205], [500.0], applied=-0.205)
    foil["outcome"]["reference_source"] = "reference_group_own_signal"
    assert REF.carried_shift(foil, None)["statement"] == "This curve carries the approved calibration shift of -0.2 eV (Ti K)."
    not_applied = _baked()
    not_applied["outcome"].update(applied=False, applied_shift_eV=0.0)
    assert REF.carried_shift(not_applied, None) is None


def test_an_approval_the_current_rules_did_not_apply_is_named():
    too_few = _baked()
    too_few["outcome"].update(applied=False, applied_shift_eV=0.0, computed_shift_eV=None)
    too_few["flags"] = [REF.TOO_FEW_FLAG]
    said = REF.approval_not_applied(too_few)
    assert said.startswith("The calibration approval d-old (Ti K, by SYN Scientist) is not applied: only 1 of 16 scans")
    assert "this curve carries no calibration shift" in said
    big = _baked([4974.5, 4974.7], [40.0, 35.0])
    big["outcome"].update(applied=False, applied_shift_eV=0.0)
    big["flags"] = [REF.SIZE_NOT_CONFIRMED_FLAG]
    said = REF.approval_not_applied(big, 2.0)
    assert "the shift it gives, -8.6 eV, is more than the protocol's 2 eV warning level and its size was not confirmed" in said
    assert "--accept-shift -8.6" in said
    assert REF.approval_not_applied({**big, "flags": []}) is None


# --- M1 + LOW 3: thresholds only stricter, and the size near the warning level ----------------------------------


def test_overrides_may_only_make_the_rules_stricter():
    assert REF.effective_warn_eV(30) == 2.0 and REF.effective_warn_eV(1.0) == 1.0 and REF.effective_warn_eV(None) == 2.0
    assert REF.effective_min_snr(0.1) == 10.0 and REF.effective_min_snr(20) == 20.0
    assert REF.effective_min_snr(0.1, "reference_group_own_signal") == 0.1
    said = REF.ignored_overrides({"qc": {"warn_energy_shift_eV": 30}, "calibration": {"reference_min_edge_snr": 0.1}})
    assert len(said) == 2
    assert said[0].startswith("The params file sets calibration.reference_min_edge_snr to 0.1, below the protocol's 10")
    assert "qc.warn_energy_shift_eV to 30, above the protocol's 2 eV" in said[1]
    assert REF.ignored_overrides({"qc": {"warn_energy_shift_eV": 1.0}, "calibration": {"reference_min_edge_snr": 20}}) == []
    # a stored step's low SNR no longer makes noise a reference
    step = C._step([4964.6, 4985.5, 4970.0], [0.6, 3.5, 2.0])
    step["params"]["reference_min_edge_snr"] = 0.1
    assert REF.reading(step)["reference_proposed"] is False
    # the would-apply reading takes the protocol's warning level over a higher one
    w = REF.would_apply(C._step([4974.5, 4974.7], [40.0, 35.0]), "Ti", "K", warn_eV=30)
    assert w["needs_size_confirmation"] and w["warn_energy_shift_eV"] == 2.0


def test_a_shift_near_the_warning_level_is_shown_and_compared_to_a_hundredth():
    assert REF.shown(2.04) == "+2.04" and REF.shown(-1.96) == "-1.96" and REF.shown(-8.6) == "-8.6"
    assert REF.shown(0.04) == "0.0" and REF.shown(-0.2) == "-0.2"
    assert REF.exceeds_warn(2.04) and not REF.exceeds_warn(2.004) and not REF.exceeds_warn(-1.96)
    w = REF.would_apply(C._step([4963.96, 4963.96], [40, 40]), "Ti", "K")
    assert w["shown"] == "+2.04" and w["needs_size_confirmation"]
    assert "sits 2.04 eV below" in w["statement"] and "--accept-shift +2.04" in w["statement"]
    under = REF.would_apply(C._step([4964.04, 4964.04], [40, 40]), "Ti", "K")
    assert under["shown"] == "+1.96" and not under["needs_size_confirmation"]


# --- H1: decide, show, build-records and validate on a stored decided result ---------------------------------------


def _approved_with_baked_shift(bdir: Path) -> str:
    """Everything decided (g1 confirmed, p1 approved as valid), then p1 given the calibration step an older build
    wrote when it baked in -8.6 eV: what such a bundle looks like now."""
    _decide_everything(bdir)
    b = M.load(bdir)
    p1 = next(r for r in b["processing_results"] if r["result_id"] == "p1")
    p1["steps"].insert(0, _baked())
    M.save_bundle(bdir, b)
    assert next(r for r in M.load(bdir)["processing_results"] if r["result_id"] == "p1")["state"] == "scientist_confirmed"
    return "g1"


_decided = _approved_with_baked_shift


def test_approve_calibration_confirms_the_size_a_decided_curve_carries(bdir):
    gid = _decided(bdir)
    args = dict(target_ids=[gid], decision="approve_calibration", value=None, element="Ti", edge="K", **BY)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, **args)
    said = str(exc.value)
    assert "Only 1 of 16 scans shows a usable reference edge" in said
    assert "The approved result p1 carries -8.6 eV from an earlier approval" in said and "--accept-shift -8.6" in said
    with pytest.raises(M.MutationRefused):
        M.decide(bdir, **args, accept_shift=-8.0)
    assert C._calibrations(bdir) == []
    out = M.decide(bdir, **args, accept_shift=-8.6)
    assert "You confirmed the -8.6 eV that the approved result p1 carries (Ti K)" in out["statement"]
    assert M.calibration_approvals(M.load(bdir))[gid]["accepted_shift_eV"] == -8.6


def test_show_says_the_curve_carries_an_unconfirmed_shift(bdir, capsys):
    gid = _decided(bdir)
    assert cli.main(["bundle", "show", str(bdir), "processing-result", "p1"]) == 0
    cal = json.loads(capsys.readouterr().out)["calibration"]
    assert cal["applied_shift_eV"] == pytest.approx(-8.599) and cal["would_apply"] == []
    assert cal["carried_shift"]["confirmed"] is False
    assert "This curve carries -8.6 eV that is now unconfirmed" in cal["carried_shift"]["statement"]
    assert "--accept-shift -8.6" in cal["carried_shift"]["statement"]
    # LOW 1: one usable scan: null spread, said against the hashed files' 0.0
    assert cal["reference_e0_spread_eV"] is None
    assert "fewer than 2 usable reference scans" in cal["reference_e0_spread_note"]
    assert "predate this rule" in cal["reference_e0_spread_note"]
    M.decide(bdir, target_ids=[gid], decision="approve_calibration", value=None, element="Ti", edge="K",
             accept_shift=-8.6, **BY)
    assert cli.main(["bundle", "show", str(bdir), "processing-result", "p1"]) == 0
    assert json.loads(capsys.readouterr().out)["calibration"]["carried_shift"]["confirmed"] is True


def test_a_record_whose_curve_carries_an_unconfirmed_shift_is_blocked_until_confirmed(bdir, tmp_path):
    _approved_with_baked_shift(bdir)
    out = R.build_records(bdir)
    [row] = out["drafts"]
    assert row["processing_blocker"] == "approved_result_calibration_unconfirmed"
    assert row["calibration_unconfirmed"].startswith("This curve carries -8.6 eV that is now unconfirmed")
    comp = json.loads((bdir / "drafts" / "g1.composition.json").read_text())
    assert comp["processing"]["result"] == "p1"
    assert "This curve carries -8.6 eV that is now unconfirmed" in comp["processing"]["calibration_unconfirmed"]
    R.validate_records(bdir, run_portal=_portal("publish"))
    report = json.loads((bdir / "validation" / "g1.json").read_text())
    assert report["verdict"] == "incomplete" and report["processing_blocker"] == "approved_result_calibration_unconfirmed"
    text = " ".join(report["plain_summary"])
    assert "the approved result p1 is not used: this curve carries -8.6 eV that is now unconfirmed" in text
    assert "--accept-shift -8.6" in text and "--target p1 --decision reject" in text
    assert R.export_records(bdir, tmp_path / "out", run_portal=_portal("publish"))["exported"] == []
    # the scientist confirms the size: the record composes again
    M.decide(bdir, target_ids=["g1"], decision="approve_calibration", value=None, element="Ti", edge="K",
             accept_shift=-8.6, **BY)
    R.build_records(bdir)
    comp = json.loads((bdir / "drafts" / "g1.composition.json").read_text())
    assert "calibration_unconfirmed" not in comp["processing"] and comp["processing"]["series"] == "processing/g1_norm.txt"
    assert "calibration" in comp["processing"]["processing_steps"]


def test_rejecting_the_result_instead_leaves_the_usual_remedy(bdir):
    _approved_with_baked_shift(bdir)
    M.decide(bdir, target_ids=["p1"], decision="reject", value=None, **BY)
    R.build_records(bdir)
    R.validate_records(bdir, run_portal=_portal("publish"))
    assert json.loads((bdir / "validation" / "g1.json").read_text())["processing_blocker"] == "processing_result_rejected"


# --- H2: zero runs ---------------------------------------------------------------------------------------------------


def _said(signal_rows, n=None):
    np = pytest.importorskip("numpy")
    from isaac_api.local_import.processing import run as RUN

    size = n or len(signal_rows[0])
    scans = [C._zsa(np, [5.0] * size)] + [C._zsa(np, s) for s in signal_rows]
    entries = C._entries(*[f"SYN_{k:03d}.txt" for k in range(1, len(scans) + 1)])
    return (RUN._zero_signal_points_statement(entries, scans, "s", np),
            RUN._isolated_zero_points_statement(entries, scans, "s", np),
            RUN._short_zero_runs_statement(entries, scans, "s", np))


def test_a_long_run_of_zeros_whose_counts_come_back_is_said_as_a_possible_lost_beam():
    lost, isolated, short = _said([[5.0] * 5 + [0.0] * 30 + [5.0] * 5])
    assert lost == ("SYN_002.txt's signal (s) is zero at 30 of 40 points (30 in a row from 11105.0 to 11134.0 eV, after "
                    "which the counts come back); it is merged unchanged. A person checks whether the beam was lost.")
    assert isolated is None and short is None


def test_runs_are_isolated_short_or_a_possible_lost_beam_by_length():
    def scan(n, runs):
        s = [5.0] * n
        for st, k in runs:
            s[st:st + k] = [0.0] * k
        return s

    # 1-2 points: isolated dropouts, even when 2 points are 20 % of a short scan
    lost, isolated, short = _said([scan(100, [(10, 1), (40, 2)])])
    assert lost is None and short is None and "(3 points in all, at most 2 in a row)" in isolated
    assert _said([scan(10, [(4, 2)])])[0] is None
    # 3-4 points under 5 % of the scan: counted, no dropout claim, no lost beam
    lost, isolated, short = _said([scan(100, [(10, 4), (50, 1)])])
    assert lost is None and "1 point in all" in isolated
    assert short.startswith("1 merged scan has 1 short run of points where the signal (s) is exactly zero")
    assert "dropout" not in short and "beam" not in short and "at most 4 in a row" in short
    # 5 % of the scan (and 3 points or more): a possible lost beam, mid-scan
    lost, isolated, short = _said([scan(100, [(10, 5)])])
    assert "5 in a row from 11110.0 to 11114.0 eV" in lost and isolated is None and short is None
    assert "3 in a row" in _said([scan(40, [(10, 3)])])[0]
    # the counts stopping (zeros to the scan's end) is the lost-beam sentence as before
    assert "from 11118.0 eV on" in _said([scan(40, [(18, 22)])])[0]


def test_the_real_measurement_that_sets_the_threshold_is_in_the_doc():
    from isaac_api.local_import.processing import run as RUN

    assert RUN.BEAM_LOSS_MIN_FRACTION == 0.05 and RUN.BEAM_LOSS_MIN_POINTS == 3 and RUN.ISOLATED_MAX_POINTS == 2
    doc = (REPO / "docs" / "xas-processing-protocol-v0.md").read_text()
    assert "merged_scan_short_zero_runs" in doc and "30 of 74" in doc and "5 %" in doc


# --- processing (numpy + larch) --------------------------------------------------------------------------------------


def test_processing_ignores_a_looser_override_and_names_the_approval_not_applied(tmp_path):
    T = C._proc()
    scans = [C._ref_scan(T, s, T.E0 + 8.0) for s in (1, 2)]
    bdir_, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    loose = {"qc": {"warn_energy_shift_eV": 30}}
    gid = T.isaac(T.run_process(bdir_, source_root=root, params=loose))["group_id"]
    plain = {gid: {"element": "Ti", "edge": "K", "decided_by": "SYN Scientist", "decision_id": "d-1"}}
    out = T.run_process(bdir_, source_root=root, params=loose, calibration_approvals=plain)
    r = T.isaac(out)
    o = C._cal(r)["outcome"]
    assert not o["applied"] and REF.SIZE_NOT_CONFIRMED_FLAG in r["review_flags"]
    said = r["qc"]["statements"]
    assert "qc.warn_energy_shift_eV to 30" in said["params_override_ignored"]
    assert said["calibration_approval_not_applied"].startswith("The calibration approval d-1 (Ti K, by SYN Scientist) is "
                                                                "not applied: the shift it gives")
    assert any("qc.warn_energy_shift_eV to 30" in line for line in out["summary"]["lines"])
    qc_file = next(f for f in r["outputs"]["files"] if f["role"] == "qc")
    hashed = (bdir_ / qc_file["relative_path"]).read_text()  # hashed: no id moves for the sentences
    assert "calibration_approval_not_applied" not in hashed and "params_override_ignored" not in hashed


def test_processing_a_low_snr_override_never_makes_noise_an_in_scan_reference(tmp_path):
    T = C._proc()
    scans = [C._ref_scan(T, 1, T.E0 + 8.0)] + [C._ref_scan(T, s, T.E0 + 8.0, ref_noise=0.4) for s in (2, 3, 4)]
    bdir_, root, _ = T.make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    r = T.isaac(T.run_process(bdir_, source_root=root, params={"calibration": {"reference_min_edge_snr": 0.1}}))
    o = C._cal(r)["outcome"]
    assert o["reference_scans_usable"] == 1 and o["reference_proposed"] is False and o["reference_e0_spread_eV"] is None
    assert "reference_min_edge_snr to 0.1" in r["qc"]["statements"]["params_override_ignored"]
    gid = r["group_id"]
    approved = {gid: {"element": "Ti", "edge": "K", "decided_by": "SYN Scientist", "decision_id": "d-2"}}
    r2 = T.isaac(T.run_process(bdir_, source_root=root, calibration_approvals=approved))
    assert "only 1 of 4 scans" in r2["qc"]["statements"]["calibration_approval_not_applied"]


# --- M2 + LOW 2: the skill and the doc -------------------------------------------------------------------------------


def test_commands_name_accept_shift_and_the_doc_says_why_one_scan_or_two():
    commands = (SKILL / "reference" / "commands.md").read_text()
    assert "[--accept-shift <eV>]" in commands
    assert "approve_calibration` (needs `--element` and `--edge`; a shift above 2 eV also needs `--accept-shift" in commands
    doc = (REPO / "docs" / "xas-processing-protocol-v0.md").read_text()
    assert REF.STRICTER_ONLY_RULE_ID in doc and "calibration_approval_not_applied" in doc
    assert "approved_result_calibration_unconfirmed" in doc
    assert "Why one scan for a reference group and two for an in-scan channel" in doc
