"""Polish r1-a review: the reviewer's probes as tests. SYNTHETIC only: every scan, name, Athena project and value
below is invented; the chemical formulas are only names a scientist might give.

* (HIGH) Names never make a calibration on a group's OWN edge apply: it always needs ``--accept-shift``, whatever its
  size and names. Names give only a hint, from a closed list (a pure element, said "its names say it is S"); any other
  name is said "ISAAC cannot tell from its names that this is a pure element". ``calibration_proposed`` is never true
  for a compound, a mixture or an unknown. A separate in-scan foil channel keeps its own rules.
* (M2) A chosen Athena version survives ISAAC's own result id moving (a params file, a calibration): it is resolved
  by its provenance on any result of the group; one that no longer resolves is said, never carried to another curve.
* (M3) Re-choosing another version after one was approved says the order (reject the old, then approve the new) and
  the old result's sentence no longer says it is the scientist's choice.
* (M4) The fixed-E0 flag reads no names: only ISAAC E0s (QC passed) that differ by 0.5 eV or more, of different Athena
  curves, of live groups. (M5) A stored, decided result it would flag is said apart, by its own id.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import mutations as M
from isaac_api.local_import.processing import reference as REF

from test_local_import_polish_r1a import (CHEM, STEM, _calibration_of, _calibrations, _processing, _results, _step,
                                          _sulfur_case, _versions_case, _with_result)
from test_local_import_records import BY, bdir, fake_upstream, pristine  # noqa: F401  (fixtures)

#: the reviewer's names that the first r1-a build read as a pure element (probe_names2.py): every one a compound, a
#: mineral, a ligand, a label or a form ISAAC cannot vouch for
REVIEWER_FALSE_NAMES = [
    "ref_B", "Standard_C", "std_K", "sample_B", "ref_V", "Ti_anatase", "Ti_rutile", "S_gypsum", "Zn_ZIF8", "Cu_EDTA",
    "Fe_acac", "S_DMSO", "Ce_ceria", "Al_alumina", "S8_electrolyte", "S_cysteine", "Fe_heme", "Pt_NP", "Fe_ox", "Cu_II",
    "Mo_S2", "Na_thio", "Na_S", "Fe(III)", "Co_SO4", "CdS_QD", "S_alpha", "S_sublimed",
]
PURE_ELEMENT_NAMES = [
    ("sulfur", "S", None), ("elemental sulfur", "S", None), ("Sref", "S", None), ("S_K", "S", "K"),
    ("Cu foil", "Cu", None), ("FeFoil", "Fe", None), ("CU FOIL", "Cu", None), ("sulphur", "S", None),
    ("S8_powder", "S", None), ("Mo_L3", "Mo", "L3"), ("05_Sref_005", "S", None), ("Fe_K_foil", "Fe", "K"),
]


# --- HIGH: a group's own edge always needs --accept-shift; names are a hint -------------------------------------


@pytest.mark.parametrize("name", REVIEWER_FALSE_NAMES)
def test_a_reviewer_false_proposal_name_is_never_proposed_nor_applied_without_accept_shift(name):
    c = REF.calibrant_identity([name])
    assert c["kind"] == "unknown" and c["element"] is None
    step = _step([2471.2, 2471.2], [400.0, 380.0], calibrant=[name])
    r = REF.reading(step)
    assert r["reference_proposed"] is True and r["calibration_proposed"] is False
    assert "ISAAC cannot tell from its names that this is a pure element" in r["reference_statement"]
    w = REF.would_apply(step, "S", "K", warn_eV=2.0)  # +0.8 eV: inside the 2 eV guard
    assert w["shown"] == "+0.8" and w["needs_size_confirmation"] and w["needs_calibrant_confirmation"]
    assert ("ISAAC cannot tell from its names that this is a pure element; " + CHEM
            + ". Only if it is a pure element, approve with --accept-shift +0.8.") in w["statement"]


@pytest.mark.parametrize("name, element, edge", PURE_ELEMENT_NAMES)
def test_a_clear_pure_element_name_gets_the_hint_and_still_needs_accept_shift(name, element, edge):
    c = REF.calibrant_identity([name])
    assert (c["kind"], c["element"], c["edge"]) == ("element", element, edge)
    step = _step([2471.6, 2471.6], [400.0, 380.0], calibrant=[name])
    assert REF.reading(step)["calibration_proposed"] is True
    w = REF.would_apply(step, element, edge or "K", warn_eV=2.0)
    if w["shift_eV"] is not None and not w["implausible"]:
        assert w["needs_size_confirmation"] and w["needs_calibrant_confirmation"]
        assert f"its names say it is {element}; if so, approve with --accept-shift {w['shown']}." in w["statement"]


def test_the_reading_says_the_shift_its_names_give_when_they_name_the_edge():
    r = REF.reading(_step([2471.6, 2471.6], [400.0, 380.0], calibrant=["S_K"]))
    assert "its names say it is S; if so, approve with --accept-shift +0.4." in r["reference_statement"]
    assert "Names read: 'S_K'." in r["reference_statement"]


def test_an_approved_element_the_names_do_not_give_is_said_and_needs_accept_shift(bdir):
    # names say iron; the approval names copper K: refused without --accept-shift, the mismatch said
    gid = _with_result(bdir, _step([8980.0, 8980.0], [400.0, 380.0], calibrant=["Fe_foil"]))
    args = dict(target_ids=[gid], decision="approve_calibration", value=None, element="Cu", edge="K", **BY)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, **args)
    said = str(exc.value)
    assert "its names say it is Fe, not Cu; check the element" in said and "Nothing was recorded" in said
    assert _calibrations(bdir) == []
    w = REF.would_apply(_step([8980.0, 8980.0], [400.0, 380.0], calibrant=["Fe_foil"]), "Cu", "K", warn_eV=2.0)
    M.decide(bdir, **args, accept_shift=float(w["shown"]))
    [d] = _calibrations(bdir)
    assert d["value"] == {"accepted_shift_eV": float(w["shown"])}


def test_a_separate_foil_channel_keeps_its_rules():
    # an in-scan reference channel: never judged by names; a small shift needs no --accept-shift, two scans required
    step = _step([2471.6, 2471.6], [40.0, 40.0], calibrant=["Mo_S2"], source=REF.IN_SCAN)
    assert REF.reading(step)["calibration_proposed"] is True
    w = REF.would_apply(step, "S", "K", warn_eV=2.0)
    assert not w["needs_size_confirmation"] and not w["needs_calibrant_confirmation"]
    assert "its names" not in w["statement"]
    one = _step([2471.6, 2400.0], [40.0, 1.0], source=REF.IN_SCAN)
    assert REF.reading(one)["reference_proposed"] is False
    big = REF.would_apply(_step([2468.0, 2468.0], [40.0, 40.0], source=REF.IN_SCAN), "S", "K", warn_eV=2.0)
    assert big["needs_size_confirmation"] and not big["needs_calibrant_confirmation"]


def test_an_older_own_edge_approval_keeps_applying_for_an_already_approved_result():
    # a step stored before names were read (no reference_calibrant), its shift applied without --accept-shift
    old = _step([2471.6], [400.0])
    old["outcome"].update({"applied": True, "applied_shift_eV": 0.4, "reference": {"element": "S", "edge": "K"}})
    c = REF.carried_shift(old)
    assert c["confirmed"] is True and c["statement"].startswith("This curve carries the approved calibration shift")
    # a new decision on it follows the rule
    assert REF.would_apply(old, "S", "K", warn_eV=2.0)["needs_size_confirmation"] is True
    # a step that read the names and carries an unconfirmed shift is said as unconfirmed
    new = _step([2471.6], [400.0], calibrant=["S_std"])
    new["outcome"].update({"applied": True, "applied_shift_eV": 0.4, "reference": {"element": "S", "edge": "K"}})
    assert REF.carried_shift(new)["confirmed"] is False
    assert REF.carried_shift(new, {"accepted_shift_eV": 0.4})["confirmed"] is True


@pytest.mark.parametrize("stem", ["05_Mo_S2_std_005", "05_S_cysteine_std_005", "05_ref_B_005"])
def test_processing_never_applies_a_false_proposal_names_own_edge_without_accept_shift(tmp_path, stem):
    _processing()
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root, _ = _sulfur_case(tmp_path, stem, 2471.2)
    r, cal = _calibration_of(run_process(bdir, source_root=root))
    assert cal["outcome"]["calibration_proposed"] is False and REF.NOT_NAMED_ELEMENT_FLAG in r["review_flags"]
    approval = {"element": "S", "edge": "K", "decided_by": "SYN Scientist", "decision_id": "d-syn"}
    r2, cal = _calibration_of(run_process(bdir, source_root=root, calibration_approvals={r["group_id"]: approval}))
    assert not cal["outcome"]["applied"] and REF.CALIBRANT_NOT_CONFIRMED_FLAG in cal["flags"]
    assert "ISAAC cannot tell from its names" in r2["qc"]["statements"]["calibration_approval_not_applied"]


# --- M2 / M3: a chosen Athena version --------------------------------------------------------------------------


def _select(bdir, isa, version_id):
    M.decide(bdir, target_ids=[isa["result_id"]], decision="select_athena_version", value=version_id, **BY)


def test_a_selection_survives_a_new_isaac_result_id(tmp_path, capsys):
    _processing()
    bdir, root = _versions_case(tmp_path)
    M.process(bdir, source=str(root))
    [isa] = _results(bdir, "isaac_protocol")
    v02 = isa["athena_versions"][1]
    _select(bdir, isa, v02["version_id"])
    pf = tmp_path / "p.json"
    pf.write_text(json.dumps({"qc": {"warn_pre_edge_noise": 0.019}}))
    M.process(bdir, source=str(root), params_file=str(pf))
    capsys.readouterr()
    fresh = next(r for r in _results(bdir, "isaac_protocol") if r["result_id"] != isa["result_id"])
    [ath] = _results(bdir, "scientist_athena")
    assert ath["run_id"] == fresh["run_id"] != isa["run_id"]
    assert ath["result_id"] == f"proc-{fresh['group_id']}-{fresh['run_id']}-athena-v02"
    assert ath["inputs"][0]["relative_path"].endswith("SYN_two.prj")
    said = ath["qc"]["statements"]["athena_version_selected"]
    assert f"made on an earlier ISAAC result of this group, {isa['result_id']}" in said and "carried over" in said
    assert ath["result_id"] in fresh["qc"]["statements"]["athena_version_selected"]


def test_a_selection_that_no_longer_resolves_is_said_not_carried_over(tmp_path, capsys):
    _processing()
    from test_local_import_polish_c10m import _prj
    from test_local_import_processing import GRID, mu_edge

    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root = _versions_case(tmp_path)
    M.process(bdir, source=str(root))
    [isa] = _results(bdir, "isaac_protocol")
    _select(bdir, isa, isa["athena_versions"][1]["version_id"])
    # the chosen curve is re-made (another data hash) and ISAAC's own id moves (a params file)
    _prj(root / "bt" / "b" / "SYN_two.prj", [(f"{STEM}_merged", GRID, mu_edge(GRID, 4972.0) * 1e-2)])
    pf = tmp_path / "p.json"
    pf.write_text(json.dumps({"qc": {"warn_pre_edge_noise": 0.019}}))
    out = run_process(bdir, source_root=root, params_file=str(pf), bundle=M.load(bdir))
    capsys.readouterr()
    fresh = next(r for r in out["processing_results"] if r["source"] == "isaac_protocol")
    assert fresh["result_id"] != isa["result_id"] and len(fresh["athena_versions"]) == 2
    assert not [r for r in out["processing_results"] if r["source"] == "scientist_athena"]
    note = out["athena_selections_not_carried_over"]
    assert note["results"][0]["result_id"] == fresh["result_id"]
    said = fresh["qc"]["statements"]["athena_selection_not_carried_over"]
    assert "not carried over to another curve and the question is asked again" in said
    assert note["statement"] in out["summary"]["lines"]


def test_reselecting_after_an_approval_says_the_order_and_the_old_result_stops_claiming_the_choice(tmp_path, capsys):
    _processing()
    from isaac_api.local_import.processing import run as RUN
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root = _versions_case(tmp_path)
    M.process(bdir, source=str(root))
    [isa] = _results(bdir, "isaac_protocol")
    v01, v02 = isa["athena_versions"]
    _select(bdir, isa, v02["version_id"])
    M.process(bdir, source=str(root))
    [a2] = _results(bdir, "scientist_athena")
    M.decide(bdir, target_ids=[a2["result_id"]], decision="approve", value=None, qc_status="valid", **BY)
    _select(bdir, isa, v01["version_id"])
    out = M.process(bdir, source=str(root))
    capsys.readouterr()
    ath = {r["result_id"]: r for r in _results(bdir, "scientist_athena")}
    new_id = f"proc-{isa['group_id']}-{isa['run_id']}-athena-v01"
    assert set(ath) == {a2["result_id"], new_id} and ath[a2["result_id"]]["state"] == "scientist_confirmed"
    order = f"reject {a2['result_id']} first, then approve {new_id}"
    assert order in ath[new_id]["qc"]["statements"]["athena_version_selected"]
    assert any(order in line for line in out["summary"]["lines"])
    # the stored, approved result is kept as it is; the note isaac process returns for it (applied by
    # apply_kept_result_notes, outside the hashed files) flags it and drops the claim that it is the choice
    payload = run_process(bdir, source_root=root, bundle=M.load(bdir))
    [note] = [n for n in payload["kept_result_notes"] if n["result_id"] == a2["result_id"]]
    kept = M.load(bdir)["processing_results"]
    assert RUN.apply_kept_result_notes(kept, payload["kept_result_notes"]) == 1
    old = next(r for r in kept if r["result_id"] == a2["result_id"])
    assert RUN.VERSION_NOT_CHOSEN_FLAG in old["review_flags"]
    for said in (old["qc"]["statements"]["athena_version_selected"], old["athena_version_selected"]["statement"]):
        assert "This result is that version" not in said and "no longer the scientist's choice" in said
        assert order in said
    assert old["athena_version_selected"]["superseded_by_result_id"] == new_id


# --- M4 / M5: the fixed-E0 flag ---------------------------------------------------------------------------------


def _pair(gid, athena_e0, isaac_e0, *, verdict="pass", curve=None, state="needs_review", run="r-0000000000000001"):
    curve = curve or f"{gid}_merged"
    return [
        {"group_id": gid, "run_id": run, "source": "isaac_protocol", "outputs": {"e0_eV": isaac_e0},
         "qc": {"verdict": verdict}, "result_id": f"proc-{gid}-{run}-isaac", "state": state},
        {"group_id": gid, "run_id": run, "source": "scientist_athena", "outputs": {"e0_eV": athena_e0}, "qc": {},
         "inputs": [{"relative_path": "SYN.prj", "athena_group": curve}], "result_id": f"proc-{gid}-{run}-athena",
         "state": state},
    ]


def _groups(*pairs):
    return [{"group_id": gid, "_stems": [stem], "basis": {}, "status": "proposed"} for gid, stem in pairs]


def _fixed(results, groups, bundle=None):
    from isaac_api.local_import.processing import run as RUN

    return RUN.possibly_fixed_athena_e0(results, bundle or {}, groups)


@pytest.mark.parametrize("a, b", [("SYN_CoSO4_5wt_001", "SYN_CoSO4_0p5wt_001"), ("SYN_MOF_Ar_001", "SYN_MOF_N2_001"),
                                  ("SYN_Li2S_pellet", "SYN_Li2S_in_BN"), ("SYN_Fe_foil", "SYN_Fe_foil_K")])
def test_the_same_sample_named_two_ways_is_not_flagged(a, b):
    results = _pair("g1", 2482.50, 2482.62) + _pair("g2", 2482.50, 2482.58)
    assert _fixed(results, _groups(("g1", a), ("g2", b))) is None
    assert not any("athena_e0_possibly_fixed" in (r.get("review_flags") or ()) for r in results)


def test_differing_isaac_e0s_are_flagged_and_the_question_says_what_fired():
    from isaac_api.local_import.processing import run as RUN

    results = _pair("g1", 2472.0, 2472.05) + _pair("g2", 2472.0, 2473.55)
    out = _fixed(results, _groups(("g1", "SYN_S"), ("g2", "SYN_MOF_0V")))
    assert out["results"] == ["proc-g1-r-0000000000000001-athena", "proc-g2-r-0000000000000001-athena"]
    q = results[1]["questions"][0]
    assert q["code"] == RUN.FIXED_E0_QUESTION and "span 1.50 eV" in q["text"] and "own edges differ" not in q["text"]
    # r3-b M3: true for pass or warn (an ISAAC E0 whose QC warned is compared too)
    assert "(each with a QC verdict of pass or warn) span 1.50 eV" in results[1]["qc"]["statements"][RUN.FIXED_E0_FLAG]
    assert "QC passed" not in results[1]["qc"]["statements"][RUN.FIXED_E0_FLAG] and "QC passed" not in q["text"]


def test_a_noisy_or_failed_isaac_e0_and_one_curve_in_two_groups_are_not_flagged():
    # an ISAAC E0 whose QC did not pass is no measurement to compare
    noisy = _pair("g1", 2472.0, 2472.05) + _pair("g2", 2472.0, 2471.1, verdict="fail")
    assert _fixed(noisy, _groups(("g1", "SYN_rep1"), ("g2", "SYN_rep2"))) is None
    # the SAME Athena curve matched to two groups is one curve, not an E0 shared across curves
    one = _pair("g1", 2472.0, 2472.05, curve="SYN_S_merged") + _pair("g2", 2472.0, 2474.0, curve="SYN_S_merged")
    assert _fixed(one, _groups(("g1", "SYN_S_a"), ("g2", "SYN_S_b"))) is None


def test_stored_results_of_superseded_non_live_or_rejected_groups_are_not_counted():
    fresh = _pair("g1", 2472.0, 2472.05)
    for status, extra, state in (("rejected", {}, "needs_review"), ("proposed", {"superseded": True}, "needs_review"),
                                 ("proposed", {}, "rejected")):
        stored = _pair("g9", 2472.0, 2474.0, state=state)
        bundle = {"processing_results": stored,
                  "record_groups": [{"group_id": "g9", "status": status}],
                  "superseded_record_groups": [{"group_id": "g9"}] if extra else []}
        assert _fixed([dict(r) for r in fresh], _groups(("g1", "SYN_S")), bundle) is None, (status, extra, state)
    # NEGATIVE CONTROL: a live group's stored result is counted, and said apart by its own id
    stored = _pair("g9", 2472.0, 2474.0)
    out = _fixed([dict(r) for r in fresh], _groups(("g1", "SYN_S")),
                 {"processing_results": stored, "record_groups": [{"group_id": "g9", "status": "proposed"}]})
    assert out["results"] == ["proc-g1-r-0000000000000001-athena"]
    assert [k["result_id"] for k in out["kept_results"]] == ["proc-g9-r-0000000000000001-athena"]


def test_a_decided_result_is_said_apart_and_never_listed_as_flagged():
    from isaac_api.local_import.processing import run as RUN

    # g2's Athena result was approved earlier; this run makes the same id again, which `isaac process` does not store
    approved = _pair("g2", 2472.0, 2473.55, state="scientist_confirmed")
    bundle = {"processing_results": approved, "record_groups": [{"group_id": "g1", "status": "proposed"},
                                                                {"group_id": "g2", "status": "proposed"}],
              "scientist_decisions": [{"decision": "approve", "decision_id": "d-1",
                                       "target": {"kind": "processing_result", "id": approved[1]["result_id"]}}]}
    results = _pair("g1", 2472.0, 2472.05) + _pair("g2", 2472.0, 2473.55)
    out = _fixed(results, _groups(("g1", "SYN_S"), ("g2", "SYN_MOF_0V")), bundle)
    assert out["results"] == ["proc-g1-r-0000000000000001-athena"]  # only what is stored carries the flag
    [kept] = out["kept_results"]
    assert kept["statement"].startswith(f"Athena: approved result {approved[1]['result_id']} carries a possibly fixed "
                                        "Athena E0")
    assert kept["statement"].endswith("ask the scientist whether it was measured.")
    assert RUN.FIXED_E0_FLAG not in (results[3].get("review_flags") or ())
    stored = [dict(r) for r in approved]
    assert RUN.apply_kept_result_notes(stored, out["kept_result_notes"]) == 1
    assert RUN.FIXED_E0_FLAG in stored[1]["review_flags"] and stored[1]["state"] == "scientist_confirmed"
    assert "kept as it was decided (scientist_confirmed)" in stored[1]["qc"]["statements"][RUN.FIXED_E0_FLAG]
    assert stored[1]["athena_e0_possibly_fixed"]["statement"] == kept["statement"]
