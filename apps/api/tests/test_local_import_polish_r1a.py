"""Polish r1-a: three XAS-processing findings from a real BL4-3 sulfur K-edge run. SYNTHETIC only: every scan, name,
Athena project and value below is invented (``SYN_``); the chemical formulas are only names a scientist might give.

* (H1) A compound standard's own edge is never offered as the energy calibration. A chemical standard is not an
  energy calibrant: its edge sits where its chemistry puts it, and "S K" would move it onto elemental sulfur's
  tabulated edge (measured: +1.2 eV for a MoS2 standard, inside the 2 eV guard). Only a reference group whose sample
  is named as a pure element is proposed; a compound, a mixture or an unknown identity is not (said why), and an
  approval of its own edge needs ``--accept-shift`` whatever the size.
* (M4) Choosing an Athena version as the result of record (``select_athena_version``) gives that version its own
  approvable Athena result on the next ``isaac process`` (built as every Athena result is); approving it makes the
  record carry that version's E0. Measured: a 42-scan group's chosen merge (E0 2473.114) changed nothing, and the
  record kept ISAAC's 2472.958.
* (M5) An Athena E0 identical across groups of one beamtime whose own edges differ is likely a fixed normalisation
  setting, not a measured edge position: each such Athena result is flagged ``athena_e0_possibly_fixed``, is not
  preferred for the record, says why and asks whether the E0 was measured or set. Measured: elemental S, a dry MOF
  and the MOF at 0 V all carried Athena E0 2471.901 eV; ISAAC measured 2472.958 eV for the last.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import mutations as M
from isaac_api.local_import.processing import reference as REF

from test_local_import_records import BY, bdir, pristine  # noqa: F401  (fixtures)

LEGACY_OUTCOME_KEYS = [
    "reference_source", "reference_e0_per_scan_eV", "reference_snr_per_scan", "measured_reference_e0_eV",
    "reference_e0_spread_eV", "reference", "reference_approved", "unconfirmed_reason", "tabulated_edge_eV",
    "tabulated_edge_source", "computed_shift_eV", "applied_shift_eV", "applied", "per_scan_alignment_shifts_eV", "method",
]


def _processing():
    pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")


# --- H1: what a reference group's sample is named as (stdlib) --------------------------------------------------


@pytest.mark.parametrize("names, kind, element", [
    (["SYN_CoSO4_5wt_sucrose_std"], "compound", None),
    (["SYN_MoS2_0.5wt_std"], "compound", None),
    (["SYN_Na2S2O3_std"], "compound", None),
    (["05_SYN_CoO_std_005"], "compound", None),
    (["SYN_Zz_oxide_std"], "compound", None),
    (["SYN_S_in_sucrose_std"], "mixture", None),
    (["SYN_S_std", "S"], "element", "S"),
    (["SYN_S8_std"], "element", "S"),
    (["SYN_Ti_foil_A"], "element", "Ti"),
    (["01_SYN_Cofoil_std_005"], "element", "Co"),
    (["31_SYN_Ti_foil_I2_120"], "element", "Ti"),  # I2 is a detector, never iodine
    (["SYN_STD_REF"], "unknown", None),  # capitals with no digit are never a formula
    (["SYN_Ti_Co_std"], "unknown", None),  # two elements: which is it?
    ([], "unknown", None),
])
def test_a_reference_groups_sample_is_read_from_its_names_only(names, kind, element):
    c = REF.calibrant_identity(names)
    assert (c["kind"], c["element"]) == (kind, element)
    assert c["rule_id"] == REF.CALIBRANT_RULE_ID and c["statement"]


def _step(e0s, snrs, calibrant=None, source="reference_group_own_signal"):
    step = {"step": "calibration", "params": {"reference_min_edge_snr": 10.0, "max_plausible_shift_eV": 25.0},
            "outcome": {"reference_source": source, "reference_e0_per_scan_eV": list(e0s),
                        "reference_snr_per_scan": list(snrs)}}
    if calibrant is not None:
        step["outcome"]["reference_calibrant"] = REF.calibrant_identity(calibrant)
    return step


def test_a_compound_standards_own_edge_is_read_but_not_proposed_and_needs_its_size_confirmed():
    step = _step([2470.8, 2470.8], [400.0, 380.0], calibrant=["SYN_MoS2_std"])
    r = REF.reading(step)
    assert r["reference_proposed"] is True and r["calibration_proposed"] is False
    assert REF.CHEMICAL_STANDARD in r["reference_statement"] and "MoS2" in r["reference_statement"]
    assert "Naming its element and edge" not in r["reference_statement"]
    w = REF.would_apply(step, "S", "K", warn_eV=2.0)
    assert w["shown"] == "+1.2" and w["needs_size_confirmation"] and w["needs_calibrant_confirmation"]
    assert "--accept-shift +1.2" in w["statement"] and "whatever the size" in w["statement"]
    # NEGATIVE CONTROLS: elemental sulfur, and a step stored before the rule (no reference_calibrant), as before
    for same in (_step([2471.6], [400.0], calibrant=["SYN_S_std"]), _step([2471.6], [400.0])):
        assert REF.reading(same)["calibration_proposed"] is True
        w = REF.would_apply(same, "S", "K", warn_eV=2.0)
        assert w["shown"] == "+0.4" and not w["needs_size_confirmation"] and not w["needs_calibrant_confirmation"]
    # an in-scan reference channel is never judged by the group's name
    assert REF.reading(_step([2470.8, 2470.8], [40.0, 40.0], calibrant=["SYN_MoS2_std"],
                             source=REF.IN_SCAN))["calibration_proposed"] is True


def _with_result(bdir: Path, step) -> str:
    b = M.load(bdir)
    run = b["runs"][0]
    b["record_groups"].append({"group_id": "g1", "experiment_key": "exp", "member_run_keys": [run["run_key"]],
                               "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}},
                               "split_reasons": [], "status": "proposed", "questions": []})
    b["processing_results"].append(
        {"result_id": "p1", "group_id": "g1", "protocol_id": "isaac.xas.v0", "protocol_version": "0.1",
         "protocol_status": "draft_unreviewed", "source": "isaac_protocol", "inputs": [],
         "steps": [step, {"step": "qc", "params": {"warn_energy_shift_eV": 2.0}, "outcome": {}, "flags": []}],
         "outputs": {"files": [], "e0_eV": 2470.8, "edge_step": 1.0, "points": 21},
         "qc": {"metrics": {}, "verdict": "pass"}, "comparison": None, "state": "needs_review"})
    M.save_bundle(bdir, b)
    return "g1"


def _calibrations(bdir):
    return [d for d in M.load(bdir)["scientist_decisions"] if d["decision"] == "approve_calibration"]


def test_an_explicit_own_edge_calibration_of_a_compound_needs_accept_shift_however_small(bdir):
    gid = _with_result(bdir, _step([2470.8, 2470.8], [400.0, 380.0], calibrant=["SYN_MoS2_std"]))
    args = dict(target_ids=[gid], decision="approve_calibration", value=None, element="S", edge="K", **BY)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, **args)
    said = str(exc.value)
    assert "approving applies +1.2 eV" in said and REF.CHEMICAL_STANDARD in said
    assert "--accept-shift +1.2" in said and "Nothing was recorded" in said
    assert _calibrations(bdir) == []
    out = M.decide(bdir, **args, accept_shift=1.2)
    assert "approving applies +1.2 eV" in out["statement"] and "You confirmed that size" in out["statement"]
    [d] = _calibrations(bdir)
    assert d["value"] == {"accepted_shift_eV": 1.2}


def test_elemental_sulfurs_own_edge_is_approved_as_before(bdir):
    gid = _with_result(bdir, _step([2471.6], [400.0], calibrant=["SYN_S_std"]))
    out = M.decide(bdir, target_ids=[gid], decision="approve_calibration", value=None, element="S", edge="K", **BY)
    assert "approving applies +0.4 eV" in out["statement"]
    [d] = _calibrations(bdir)
    assert d["value"] is None


# --- H1 through processing (numpy + larch) ------------------------------------------------------------------------


def _sulfur_case(tmp_path, stem, e0):
    import numpy as np

    from test_local_import_processing import make_case, mu_edge, spec_file

    grid = np.arange(2420.0, 2620.0 + 1e-9, 0.5)

    def scan(seed):
        rng = np.random.default_rng(seed)
        i0 = np.full(grid.size, 1.0e5)
        mu = mu_edge(grid, e0) + rng.normal(0, 0.001, grid.size)
        return spec_file({"energy": grid, "I0": i0, "I1": i0 * np.exp(-mu)})

    return make_case(tmp_path, [(stem, [scan(1), scan(2)], {})])


def _calibration_of(payload):
    r = next(r for r in payload["processing_results"] if r["source"] == "isaac_protocol")
    return r, next(s for s in r["steps"] if s["step"] == "calibration")


def test_processing_never_proposes_a_compound_standards_own_edge(tmp_path):
    _processing()
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root, _ = _sulfur_case(tmp_path, "05_SYN_MoS2_std_005", 2470.8)
    r, cal = _calibration_of(run_process(bdir, source_root=root))
    o = cal["outcome"]
    assert o["reference_source"] == REF.OWN_SIGNAL and o["reference_proposed"] is True
    assert o["calibration_proposed"] is False and o["reference_calibrant"]["kind"] == "compound"
    assert REF.CHEMICAL_STANDARD in o["reference_statement"]
    assert REF.NOT_A_CALIBRANT_FLAG in r["review_flags"]
    # said outside the hashed files: params.json keeps exactly the calibration keys it had (no id moves)
    params = json.loads(next(bdir / f["relative_path"] for f in r["outputs"]["files"] if f["role"] == "params").read_text())
    assert list(params["calibration"]) == LEGACY_OUTCOME_KEYS


def test_processing_still_proposes_elemental_sulfur(tmp_path):
    _processing()
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root, _ = _sulfur_case(tmp_path, "05_SYN_S_std_005", 2471.6)
    r, cal = _calibration_of(run_process(bdir, source_root=root))
    o = cal["outcome"]
    assert o["calibration_proposed"] is True and o["reference_calibrant"]["kind"] == "element"
    assert "Naming its element and edge gives the shift" in o["reference_statement"]
    assert REF.NOT_A_CALIBRANT_FLAG not in r["review_flags"]
    approval = {"element": "S", "edge": "K", "decided_by": "SYN Scientist"}
    _, cal = _calibration_of(run_process(bdir, source_root=root, calibration_approvals={r["group_id"]: approval}))
    assert cal["outcome"]["applied"] and cal["outcome"]["applied_shift_eV"] == pytest.approx(0.4, abs=0.2)


def test_a_compound_whose_identity_is_unknown_is_not_proposed_either(tmp_path):
    _processing()
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root, _ = _sulfur_case(tmp_path, "05_SYN_ZZ_std_005", 2470.8)
    _, cal = _calibration_of(run_process(bdir, source_root=root))
    o = cal["outcome"]
    assert o["calibration_proposed"] is False and o["reference_calibrant"]["kind"] == "unknown"
    assert "do not state that its sample is a pure element" in o["reference_statement"]


def test_an_approved_compound_own_edge_is_applied_only_with_its_size_confirmed(tmp_path):
    _processing()
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root, _ = _sulfur_case(tmp_path, "05_SYN_MoS2_std_005", 2470.8)
    r, _ = _calibration_of(run_process(bdir, source_root=root))
    gid = r["group_id"]
    approval = {"element": "S", "edge": "K", "decided_by": "SYN Scientist", "decision_id": "d-syn"}
    r2, cal = _calibration_of(run_process(bdir, source_root=root, calibration_approvals={gid: approval}))
    assert not cal["outcome"]["applied"] and REF.CALIBRANT_NOT_CONFIRMED_FLAG in cal["flags"]
    said = r2["qc"]["statements"]["calibration_approval_not_applied"]
    assert said.startswith("The calibration approval d-syn (S K, by SYN Scientist) is not applied")
    shift = cal["outcome"]["computed_shift_eV"]
    assert 0 < shift < 2.0  # inside the 2 eV guard: before this rule it was applied with no size confirmed
    assert REF.CHEMICAL_STANDARD in said and f"--accept-shift {REF.shown(shift)}" in said
    confirmed = {**approval, "accepted_shift_eV": round(shift, 1)}
    _, cal = _calibration_of(run_process(bdir, source_root=root, calibration_approvals={gid: confirmed}))
    assert cal["outcome"]["applied"] and cal["outcome"]["applied_shift_eV"] == pytest.approx(shift)


# --- M4: the chosen Athena version becomes an approvable result --------------------------------------------------

STEM = "08_SYN_ZZ_pellet_030"


def _versions_case(tmp_path):
    """One imported run (2 synthetic XDAC scans, edge at 4966 eV) and TWO Athena projects whose merged group of it
    differs (edges at 4966 and 4969 eV): two versions, none selected."""
    from test_local_import_polish_c10m import _prj
    from test_local_import_polish_c2f import _xdac, std_scan
    from test_local_import_processing import GRID, mu_edge

    from isaac_api.local_import import cli

    root = tmp_path / "SYN_beamtime"
    for k in (1, 2):
        _xdac(root / "bt" / f"{STEM}_A.00{k}", std_scan(k, i1_positive=True))
    _prj(root / "bt" / "a" / "SYN_one.prj", [(f"{STEM}_merged", GRID, mu_edge(GRID, 4966.0) * 1e-2)])
    _prj(root / "bt" / "b" / "SYN_two.prj", [(f"{STEM}_merged", GRID, mu_edge(GRID, 4969.0) * 1e-2)])
    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    M.group(out)
    return out, root


def _results(bdir, source):
    return [r for r in M.load(bdir)["processing_results"] if r["source"] == source]


def test_choosing_an_athena_version_then_approving_it_gives_the_record_its_e0(tmp_path, capsys):
    _processing()
    from isaac_api.local_import import records as R

    bdir, root = _versions_case(tmp_path)
    out = M.process(bdir, source=str(root))
    capsys.readouterr()
    [isa] = _results(bdir, "isaac_protocol")
    assert _results(bdir, "scientist_athena") == [] and len(isa["athena_versions"]) == 2
    assert "processing this group again gives that version its own Athena result" in isa["questions"][0]["text"]
    # NEVER "matched no record group" when the group lists the scientist's versions
    assert not any("matched no record group" in line for line in out["summary"]["lines"])
    v02 = isa["athena_versions"][1]
    assert v02["provenance"]["prj_file_name"] == "SYN_two.prj"
    M.decide(bdir, target_ids=[isa["result_id"]], decision="select_athena_version", value=v02["version_id"], **BY)
    M.process(bdir, source=str(root))
    [isa] = _results(bdir, "isaac_protocol")
    [ath] = _results(bdir, "scientist_athena")
    assert ath["athena_version_id"] == v02["version_id"] and ath["result_id"] == f"proc-{isa['group_id']}-{isa['run_id']}-athena-v02"
    assert ath["inputs"][0]["relative_path"].endswith("SYN_two.prj") and ath["state"] == "needs_review"
    assert ath["outputs"]["e0_eV"] == pytest.approx(4969.0, abs=0.6)
    assert abs(ath["outputs"]["e0_eV"] - isa["outputs"]["e0_eV"]) > 2.0
    assert [f["role"] for f in ath["outputs"]["files"]][0] == "athena_normalized"
    assert "approving it makes the record carry its E0" in ath["qc"]["statements"]["athena_version_selected"]
    assert ath["result_id"] in isa["qc"]["statements"]["athena_version_selected"]
    assert isa["athena_result_of_record"] == v02["version_id"]
    group = next(g for g in M.load(bdir)["record_groups"] if g["group_id"] == isa["group_id"])
    # before the approval the record carries no E0 from either result
    draft, _ = R.compose_group(M.load(bdir), group, bdir)
    assert not draft.get("descriptors_outputs")
    M.decide(bdir, target_ids=[ath["result_id"]], decision="approve", value=None, qc_status="valid", **BY)
    draft, report = R.compose_group(M.load(bdir), group, bdir)
    [d] = draft["descriptors_outputs"][0]["descriptors"]
    assert d["name"] == "edge_position" and d["value"] == pytest.approx(ath["outputs"]["e0_eV"])
    assert d["source"] == "imported" and "SYN_two.prj" in draft["descriptors_outputs"][0]["label"]
    assert report["processing"]["result"] == ath["result_id"]


def test_without_a_choice_no_version_result_is_made(tmp_path, capsys):
    _processing()
    bdir, root = _versions_case(tmp_path)
    M.process(bdir, source=str(root))
    M.process(bdir, source=str(root))
    capsys.readouterr()
    assert _results(bdir, "scientist_athena") == []


# --- M5: an Athena E0 that is the same in several groups -------------------------------------------------------


def _fixed_e0_case(tmp_path, edges, athena_e0s):
    """One run per edge (2 synthetic scans each, different samples) and ONE Athena project holding each run's curve,
    normalised with the E0 given (a number set in Athena, not found from the curve)."""
    import larch.xafs as xafs
    from larch import Group
    from larch.io import AthenaProject

    from test_local_import_processing import GRID, fluo_scan, make_case, mu_edge, spec_file

    tmp_path.mkdir(parents=True, exist_ok=True)
    runs = [(f"0{k}_SYN_ZZ{k}", [spec_file(fluo_scan(s, e0=e0)) for s in (1, 2)], {"sample_name": f"ZZ{k}"})
            for k, e0 in enumerate(edges, start=1)]
    bdir, root, bundle = make_case(tmp_path, runs)
    prj = AthenaProject()
    for (stem, _, _), e0, fixed in zip(runs, edges, athena_e0s):
        g = Group(energy=GRID, mu=mu_edge(GRID, e0) * 1e-2, label=stem, filename=stem)
        xafs.pre_edge(g, e0=fixed, pre1=-50, pre2=-30, norm1=60, norm2=130, nnorm=2)
        prj.add_group(g)
    prj.save(str(root / "SYN_fixed.prj"))
    bundle["unread_files"].append({"source_id": "prj-fixed", "relative_path": "SYN_fixed.prj"})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


def _athena_results(payload):
    return [r for r in payload["processing_results"] if r["source"] == "scientist_athena"]


def test_one_athena_e0_in_three_groups_whose_own_edges_differ_is_flagged(tmp_path):
    _processing()
    from isaac_api.local_import.processing import run as RUN
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root = _fixed_e0_case(tmp_path, [4966.0, 4968.0, 4970.0], [4967.0] * 3)
    out = run_process(bdir, source_root=root)
    ath = _athena_results(out)
    assert len(ath) == 3 and {round(r["outputs"]["e0_eV"], 3) for r in ath} == {4967.0}
    for r in ath:
        assert RUN.FIXED_E0_FLAG in r["review_flags"] and r["preferred_for_record"] is False
        said = r["qc"]["statements"][RUN.FIXED_E0_FLAG]
        assert said.startswith("The scientist's Athena E0 here, 4967.000 eV, is exactly the Athena E0 of 2 other groups")
        assert "likely a fixed normalisation setting" in said and "measured or set" in said
        info = r["athena_e0_possibly_fixed"]
        assert info["rule_id"] == RUN.FIXED_E0_RULE_ID and len(info["groups"]) == 3 and info["isaac_e0_spread_eV"] > 3.0
        assert [q["code"] for q in r["questions"]] == [RUN.FIXED_E0_QUESTION]
    assert out["athena"]["e0_possibly_fixed"]["results"] == [r["result_id"] for r in ath]
    assert any(line.startswith("Athena: 3 of the scientist's Athena result(s) carry an E0 identical")
               for line in out["summary"]["lines"])


def test_a_single_group_and_different_athena_e0s_are_not_flagged(tmp_path):
    _processing()
    from isaac_api.local_import.processing import run as RUN
    from isaac_api.local_import.processing.cli_entry import run_process

    one, root = _fixed_e0_case(tmp_path / "one", [4966.0], [4967.0])
    [r] = _athena_results(run_process(one, source_root=root))
    assert RUN.FIXED_E0_FLAG not in r["review_flags"] and r["preferred_for_record"] is True
    assert "athena_e0_possibly_fixed" not in r and not r.get("questions")
    # NEGATIVE CONTROL: three groups, each with its own Athena E0
    three, root = _fixed_e0_case(tmp_path / "three", [4966.0, 4968.0, 4970.0], [4966.1, 4968.1, 4970.1])
    out = run_process(three, source_root=root)
    assert not any(RUN.FIXED_E0_FLAG in r["review_flags"] for r in _athena_results(out))
    assert "e0_possibly_fixed" not in out["athena"]


def test_an_identical_athena_e0_with_the_same_own_edge_is_not_flagged(tmp_path):
    _processing()
    from isaac_api.local_import.processing import run as RUN
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root = _fixed_e0_case(tmp_path, [4966.0, 4966.0], [4966.0, 4966.0])
    assert not any(RUN.FIXED_E0_FLAG in r["review_flags"] for r in _athena_results(run_process(bdir, source_root=root)))
