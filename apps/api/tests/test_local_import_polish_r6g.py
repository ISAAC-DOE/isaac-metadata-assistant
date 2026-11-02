"""r6-g: the scientist's Athena results, on SYNTHETIC spectra and SYN_* names only.

G1 a scientist's merge whose name matches no record group is listed (process summary and each group its name is
near), with near-name hints that never match; the scientist ties one to a group by name in a params file
(``athena_match``). G2 the processing-results ``scans`` line of a per-scan set over several runs names each run's
scans. G3 ``bundle show processing-result`` prints how the Athena curve was made, and a set names how many of its
members were made each way. G4 larch's different reading of a project is said once per bundle, not flagged on each
result; it is still recorded on each.
"""

from __future__ import annotations

import json

import pytest


def _proc():
    pytest.importorskip("numpy", reason="needs the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="needs the optional `processing` extra (xraylarch)")
    import test_local_import_processing as T

    return T


def _A():
    from isaac_api.local_import.processing import athena as A

    return A


def _entry(T, label, prj, *, scale=1.0, is_merge=False, data=None):
    A = _A()
    mu = T.mu_edge(T.GRID) * 1e-2 * scale
    return {"names": [A.normalise_name(label)], "label": label, "group_name": label.lower(), "prj_relative_path": prj,
            "prj_source_id": None, "is_merge": is_merge, "energy": T.GRID.copy(), "mu": mu, "norm": mu / 0.015,
            "flat": mu / 0.015, "e0_eV": T.E0, "edge_step": 0.015, "params": {"nor1": 60.0, "nor2": 130.0},
            "data_hash": data or f"h-{label}-{scale}", "non_finite_values": [], "energy_frame_known": True,
            "channel_expression": {}}


def _group(gid, *stems, status="scientist_confirmed"):
    return {"group_id": gid, "_stems": list(stems), "_has_scans": True, "status": status}


GROUPS = [_group("rg-07", "07_SYN_ZZ_pH1_m300mV_023"), _group("rg-08", "08_SYN_std_0p5wt_sucrose_029", "08_SYN_std_0p5wt_sucrose_030"),
          _group("rg-12", "12_SYN_E2_pH1_m300mV_spot2_040"), _group("rg-13", "13_SYN_E2_pH1_m150mV_spot2_041"),
          _group("rg-14", "14_SYN_E2_pH1_m150mV_spot2_042")]


# --- G1: merges that match no group ----------------------------------------------------------------------------------


def test_an_unmatched_merge_is_listed_with_near_name_hints_and_never_matched():
    T = _proc()
    A = _A()
    entries = [_entry(T, "merge4_12_SYN_E2_pH1_m300mV_spt2", "SYN_day2.prj", is_merge=True),
               _entry(T, "merge4_08_SYN_std_0p5wt_sugar_spot1", "SYN_day2.prj", is_merge=True),
               _entry(T, "merge4_SYN_E2_pH1_m150mV_spot2", "SYN_day2.prj", is_merge=True),
               _entry(T, "merge16", "SYN_day2.prj", is_merge=True)]
    matched, notes, versions = A.match_with_versions(GROUPS, entries, T.np)
    # NEVER A FUZZY MATCH: nothing is matched, listed or noted for any group
    assert matched == {} and versions == {} and notes == []
    items = {i["athena_label"]: i for i in A.unmatched_merges(GROUPS, entries)}
    assert set(items) == {e["label"] for e in entries}
    assert [c["group_id"] for c in items["merge4_12_SYN_E2_pH1_m300mV_spt2"]["candidates"]] == ["rg-12"]
    c = items["merge4_08_SYN_std_0p5wt_sugar_spot1"]["candidates"]
    assert [x["group_id"] for x in c] == ["rg-08"] and c[0]["shares_run_number"] and "0p5wt" in c[0]["shared_tokens"]
    # no run number in the name: the names alike are hints, both of them (the scientist decides)
    assert {x["group_id"] for x in items["merge4_SYN_E2_pH1_m150mV_spot2"]["candidates"]} >= {"rg-13", "rg-14"}
    assert items["merge16"]["candidates"] == [] and items["merge16"]["merge_name"] == ""
    assert all(i["hint_rule"] == A.UNMATCHED_HINT_RULE_ID for i in items.values())


def test_only_merges_that_match_no_group_are_listed():
    T = _proc()
    A = _A()
    entries = [_entry(T, "merge_07_SYN_ZZ_pH1_m300mV_023", "SYN.prj", is_merge=True),  # matches by name
               _entry(T, "07_SYN_ZZ_pH1_m300mV_spt", "SYN.prj"),  # no merge: not listed
               _entry(T, "merge22_07_SYN_ZZ_pH1_m300V", "SYN_a.prj", is_merge=True, data="same"),
               _entry(T, "merge22_07_SYN_ZZ_pH1_m300V", "SYN_b.prj", is_merge=True, data="same")]
    items = A.unmatched_merges(GROUPS, entries)
    # the same label and data in two projects is ONE merge, naming both projects
    assert len(items) == 1 and [i["prj_relative_path"] for i in items[0]["in"]] == ["SYN_a.prj", "SYN_b.prj"]
    assert [c["group_id"] for c in items[0]["candidates"]] == ["rg-07"]
    # a merged-away group is never a candidate
    gone = [_group("rg-07", "07_SYN_ZZ_pH1_m300mV_023", status="merged")] + GROUPS[1:]
    assert A.unmatched_merges(gone, entries[2:])[0]["candidates"] == []


def test_the_scientist_ties_a_merge_by_name_in_the_params_file():
    T = _proc()
    A = _A()
    from isaac_api.local_import.processing import protocol as P

    entries = [_entry(T, "12_SYN_E2_pH1_m300mV_spot2_040_A.001", "SYN_day2.prj"),
               _entry(T, "12_SYN_E2_pH1_m300mV_spot2_040_A.002", "SYN_day2.prj", scale=1.01),
               _entry(T, "merge4_12_SYN_E2_pH1_m300mV_spt2", "SYN/SYN_day2.prj", is_merge=True, data="m"),
               _entry(T, "merge4_12_SYN_E2_pH1_m300mV_spt2", "SYN/SYN_day3.prj", is_merge=True, data="m")]
    ties = P.athena_match_ties({"athena_match": {"rg-12": [{"project": "SYN_day2.prj",
                                                            "athena_group": "merge4_12_SYN_E2_pH1_m300mV_spt2"}],
                                                 "rg-gone": {"project": "SYN_day2.prj", "athena_group": "x"},
                                                 "rg-13": [{"project": "SYN_day9.prj", "athena_group": "x"}]}})
    by_entry, rows = A.resolve_ties(ties, entries, GROUPS)
    # the project's FILE NAME alone fits one project here; the tie is exact on project and group
    assert by_entry == {2: ["rg-12"]}
    assert {r["group_id"]: r["status"] for r in rows} == {"rg-12": "tied", "rg-gone": "no_live_group", "rg-13": "not_found"}
    matched, _, versions = A.match_with_versions(GROUPS, entries, T.np, ties=by_entry)
    # the tied merge is the group's one merge: preferred over the per-scan groups beside it, which are set aside
    m = matched["rg-12"]
    assert m["label"] == "merge4_12_SYN_E2_pH1_m300mV_spt2" and m["_match_kind"] == A.TIED_KIND and not versions
    assert m["_sets_aside"] and A.entry_groups(GROUPS, entries, ties=by_entry)[2] == "rg-12"
    # its copy in another project (same label and data) is the same merge: no longer listed as unmatched
    assert A.unmatched_merges(GROUPS, entries, tied=by_entry) == []
    # NEGATIVE CONTROL: a name that fits two Athena groups ties nothing
    two = [entries[2], {**entries[2], "prj_relative_path": "SYN_other/SYN_day2.prj"}]
    got, rows2 = A.resolve_ties({"rg-12": [{"project": "SYN_day2.prj", "athena_group": entries[2]["label"]}]}, two, GROUPS)
    assert got == {} and rows2[0]["status"] == "several"


def test_the_params_section_is_checked_and_kept_out_of_the_resolved_params():
    from isaac_api.local_import.processing import protocol as P

    assert P.athena_match_ties(None) == {} and P.athena_match_ties({}) == {}
    for bad in ([], {"rg-1": []}, {"rg-1": [{"project": "a.prj"}]}, {"rg-1": [{"project": "", "athena_group": "g"}]},
                {"rg-1": [{"project": "a.prj", "athena_group": "g", "extra": 1}]}):
        with pytest.raises(ValueError, match="athena_match must be"):
            P.athena_match_ties({"athena_match": bad})
    tie = {"athena_match": {"rg-1": [{"project": "a.prj", "athena_group": "g"}]}}
    assert P.resolve_params(tie) == P.resolve_params(None)  # no other result's params.json moves


def _case_with_merge(T, tmp_path, name, extra=()):
    d = tmp_path / name
    d.mkdir()
    mu = T.mu_edge(T.GRID) * 1e-2
    groups = [("01_SYN_ZZ1_1-2", T.GRID, mu), *extra]
    return T._athena_case(d, {"SYN.prj": groups})


def test_process_says_a_merge_exists_but_was_not_matched_and_no_id_moves(tmp_path):
    T = _proc()
    from isaac_api.local_import.processing import run as RUN

    mu = T.mu_edge(T.GRID) * 1e-2
    bdir0, root0 = _case_with_merge(T, tmp_path, "plain")
    plain = T.run_process(bdir0, source_root=root0)
    bdir, root = _case_with_merge(T, tmp_path, "merge", [("merge4_01_SYN_ZZ1_spt", T.GRID, mu * 1.02)])
    out = T.run_process(bdir, source_root=root)
    # NO ID MOVES: the unmatched merge is said after the run id, never in a hashed file
    assert sorted(r["result_id"] for r in out["processing_results"]) == sorted(r["result_id"] for r in plain["processing_results"])
    [item] = out["athena"]["unmatched_merges"]
    assert item["athena_label"] == "merge4_01_SYN_ZZ1_spt" and [c["group_id"] for c in item["candidates"]]
    line = out["athena"]["unmatched_merges_statement"]
    assert "A merge exists but was not matched" in line and "hint only, never matched" in line and line in out["summary"]["lines"]
    isaac = next(r for r in out["processing_results"] if r["source"] == "isaac_protocol")
    said = isaac["qc"]["statements"][RUN.UNMATCHED_MERGE_KEY]
    assert "merge4_01_SYN_ZZ1_spt" in said and '"athena_match"' in said and RUN.UNMATCHED_MERGE_KEY in isaac["review_flags"]
    [q] = [q for q in isaac["questions"] if q["code"] == RUN.UNMATCHED_MERGE_QUESTION]
    assert "this group's merge" in q["text"]
    # the stored results `isaac process` keeps get the same sentence (outside the hashed files)
    assert {n["result_id"] for n in out["kept_result_notes"]} >= {isaac["result_id"]}
    # the Athena result is still the scientist's per-scan curve it was: the merge was not used
    sci = next(r for r in out["processing_results"] if r["source"] == "scientist_athena")
    assert sci["inputs"][0]["scan"] == "01_SYN_ZZ1_1-2"
    # NEGATIVE CONTROL: without the merge nothing is said
    assert "unmatched_merges" not in plain["athena"]
    assert not any(RUN.UNMATCHED_MERGE_KEY in (r.get("review_flags") or ()) for r in plain["processing_results"])


def test_process_uses_a_merge_the_scientist_tied_and_records_the_tie(tmp_path):
    T = _proc()
    mu = T.mu_edge(T.GRID) * 1e-2
    bdir, root = _case_with_merge(T, tmp_path, "tie", [("merge4_01_SYN_ZZ1_spt", T.GRID, mu * 1.02)])
    before = T.run_process(bdir, source_root=root)
    gid = before["processing_results"][0]["group_id"]
    tie = {"athena_match": {gid: [{"project": "SYN.prj", "athena_group": "merge4_01_SYN_ZZ1_spt"}],
                            "rg-SYN-none": [{"project": "SYN.prj", "athena_group": "merge4_01_SYN_ZZ1_spt"}]}}
    out = T.run_process(bdir, source_root=root, params=tie)
    sci = next(r for r in out["processing_results"] if r["source"] == "scientist_athena")
    assert sci["inputs"][0]["scan"] == "merge4_01_SYN_ZZ1_spt" and sci["inputs"][0]["match_kind"] == "named_by_scientist"
    assert sci["comparison"]["athena_ref"]["named_by"] == "params athena_match"
    assert "named it as this group's in the params file's athena_match" in sci["qc"]["statements"]["scans_used"]
    assert "unmatched_merges" not in out["athena"]
    rows = {r["group_id"]: r["status"] for r in out["athena"]["athena_match"]}
    assert rows == {gid: "tied", "rg-SYN-none": "no_live_group"}
    assert any("rg-SYN-none" in line and "nothing was tied" in line for line in out["summary"]["lines"])
    isaac = next(r for r in out["processing_results"] if r["source"] == "isaac_protocol")
    params = json.loads(next(bdir / f["relative_path"] for f in isaac["outputs"]["files"] if f["role"] == "params").read_text())
    assert params["athena_match"] == [{"project": "SYN.prj", "athena_group": sci["inputs"][0]["athena_group"]}]
    # the group's curve changed (another Athena curve), so its run id moves; the scientist approves the new result
    assert isaac["result_id"] != next(r for r in before["processing_results"] if r["source"] == "isaac_protocol")["result_id"]


# --- G2: the scans line of a set over several runs -------------------------------------------------------------------


def test_the_scans_line_of_a_set_over_several_runs_names_each_run():
    from isaac_api.local_import import cli

    r = {"source": "scientist_athena", "inputs": [{"scans_basis": "per_scan_set", "scans": [1, 2, 1, 2, 3, 4],
                                                   "per_scan_set": {"runs": ["SYN_a_007"] * 2 + ["SYN_a_008"] * 4}}]}
    assert cli._scans_line(r) == ("6 per-scan groups from 2 runs: scans 1-2 of run SYN_a_007; scans 1-4 of run SYN_a_008 "
                                  "(averaged by ISAAC)")
    one = {"source": "scientist_athena", "inputs": [{"scans_basis": "per_scan_set", "scans": [1, 2, 1],
                                                     "per_scan_set": {"runs": ["SYN_a_019"] * 2 + ["SYN_a_020"]}}]}
    assert cli._scans_line(one).endswith("scans 1-2 of run SYN_a_019; scan 1 of run SYN_a_020 (averaged by ISAAC)")
    # NEGATIVE CONTROL: one run's set reads as before
    r["inputs"][0]["per_scan_set"] = {}
    assert cli._scans_line(r) == "scans 1-4 (the scientist's per-scan groups, averaged by ISAAC)"


# --- G3: how the Athena curve was made -------------------------------------------------------------------------------


def test_show_prints_how_the_curve_was_made_and_a_set_names_its_basis():
    T = _proc()
    A = _A()
    from isaac_api.local_import import cli

    r = {"result_id": "proc-g-r-0-athena", "group_id": "g", "source": "scientist_athena", "inputs": [],
         "steps": [{"step": "normalize", "params": {"reproduced_with": "SYN way"}, "flags": [], "outcome": {}},
                   {"step": "qc", "params": {}, "flags": [], "outcome": {}}]}
    view = cli._processing_result_view({"record_groups": []}, r)
    assert view["steps"][0]["reproduced_with"] == "SYN way" and "reproduced_with" not in view["steps"][1]
    a, b, c = (_entry(T, f"01_SYN_ZZ1_00{k}", "SYN.prj", scale=1 + k / 100) for k in (1, 2, 3))
    for e, basis in ((a, A.BASIS_STORED), (b, A.BASIS_REFIT), (c, A.BASIS_STORED)):
        e[A.BASIS_KEY] = basis
        e[A.RENORMALISED_KEY] = {"basis": basis, "larch_edge_step": 0.01, "project_edge_step": 0.015,
                                 "post_edge_difference_from_larch": 0.05, "material": True, "statement": "x"}
    s = A._per_scan_set([a, b, c], ["01_SYN_ZZ1"], T.np)
    assert s[A.BASIS_COUNTS_KEY] == {A.BASIS_STORED: 2, A.BASIS_REFIT: 1}
    said = s[A.RENORMALISED_KEY]["statement"]
    assert "2 from the project's stored values" in said and "1 by Athena's own re-fit" in said
    assert s[A.RENORMALISED_KEY]["material"] is True


# --- G4: larch's different reading is said once ----------------------------------------------------------------------


def test_larchs_reading_is_recorded_on_each_result_and_said_once(tmp_path, monkeypatch):
    T = _proc()
    A = _A()
    from isaac_api.local_import.processing import run as RUN

    real = A.load_project

    def differing(*args, **kwargs):
        entries, notes = real(*args, **kwargs)
        for e in entries:  # larch's reading gave another curve, 5 % of the step at the post-edge
            e[A.RENORMALISED_KEY] = {"rule_id": A.ATHENA_RENORM_RULE_ID, "basis": A.BASIS_STORED, "larch_edge_step": 0.0143,
                                     "project_edge_step": 0.015, "edge_step": 0.015, "max_difference_from_larch": 0.06,
                                     "post_edge_difference_from_larch": 0.05, "material": True, "statement": "SYN said"}
        return entries, notes

    monkeypatch.setattr(A, "load_project", differing)
    bdir, root = T._athena_case(tmp_path, {"SYN.prj": [("01_SYN_ZZ1_1-2", T.GRID, T.mu_edge(T.GRID) * 1e-2)]})
    out = T.run_process(bdir, source_root=root)
    sci = next(r for r in out["processing_results"] if r["source"] == "scientist_athena")
    assert A.ATHENA_RENORM_FLAG not in sci["review_flags"] and A.ATHENA_RENORM_FLAG not in sci["qc"]["statements"]
    rec = sci[A.RENORMALISED_KEY]
    assert "material" in rec and "post_edge_difference_from_larch" in rec and "statement" not in rec
    [line] = [x for x in out["summary"]["lines"] if "larch's own reading" in x]
    assert "for 1 of the 1 Athena results" in line and "not flagged on each result" in line
    # the count: material ones by the post-edge difference; a record without the key (before r6) counts as material
    rows = [{"source": "scientist_athena", A.RENORMALISED_KEY: {"material": False}},
            {"source": "scientist_athena", A.RENORMALISED_KEY: {"larch_edge_step": 1.0}},
            {"source": "scientist_athena"}, {"source": "isaac_protocol", A.RENORMALISED_KEY: {"material": True}}]
    said = RUN.renormalisation_line(rows)
    assert "for 2 of the 3 Athena results" in said and "1 of them differ" in said
    assert RUN.renormalisation_line([{"source": "scientist_athena"}]) is None


def test_the_post_edge_difference_decides_what_is_material():
    T = _proc()
    A = _A()
    np = T.np
    X = np.arange(0.0, 200.0, 1.0)
    norm = np.where(X >= 100, 1.0, 0.0)
    params = {"nor1": 50.0, "nor2": 90.0}
    assert A._post_edge_gap(X, norm, norm * 1.01, 100.0, params, np) == pytest.approx(0.01)
    assert A._post_edge_gap(X, norm, norm * 1.05, 100.0, params, np) == pytest.approx(0.05)
    # a difference only below the edge is not at the post-edge
    low = norm.copy()
    low[X < 90] += 0.5
    assert A._post_edge_gap(X, norm, low, 100.0, params, np) == 0.0
    assert A._post_edge_gap(X, norm, norm, 100.0, {"nor1": None, "nor2": 90.0}, np) is None
    assert A.renorm_material({"material": False}) is False and A.renorm_material({"x": 1}) is True
    assert A.renorm_material(None) is False


# --- review M2: hints that point at the wrong group, or hide the right one ------------------------------------------


def _hint(label, *groups):
    A = _A()
    return [c["group_id"] for c in A.near_name_candidates({"label": label, "names": [A.normalise_name(label)],
                                                           "is_merge": True}, list(groups))]


def test_hints_count_a_run_number_only_at_the_start_and_veto_other_digits():
    A = _A()
    # a number at the end of the merge's name is no run number: the group alike is the hint, never group 02
    assert _hint("merge_SYNFeO_m300mV_2", _group("rgA", "07_SYNFeO_m300mV"), _group("rgB", "02_SYNFeO_dry")) == ["rgA"]
    # scans 1-4 named after the sample are no run numbers either
    assert _hint("merge3_SYNCoS_1_4", _group("rgC", "05_SYNCoS_k9"), _group("rgD", "01_SYNCoS_k9"),
                 _group("rgE", "04_SYNCoS_k9")) == []
    # another potential, or another spot, is another sample: vetoed, never a likeness
    assert _hint("merge_SYNNiO_pH7_m200mV", _group("rgF", "03_SYNNiO_pH7_m300mV")) == []
    assert _hint("merge_SYNmos2_s1", _group("rgH", "09_SYNmos2_s2")) == []
    # a typo is not vetoed, and the difference is named
    [c] = A.near_name_candidates({"label": "merge_SYNmos2_spt2", "names": ["merge_synmos2_spt2"], "is_merge": True},
                                 [_group("rgJ", "09_SYNmos2_spot2")])
    assert c["differs_in"] == {"merge": ["spt2"], "group": ["spot2"]}
    # a run-number hint never hides a likeness hint
    got = _hint("merge_07_SYN_x_dry_spot3", _group("rg07", "07_SYN_x_wet"), _group("rg08", "08_SYN_x_dry_spot3"))
    assert got[0] == "rg07" and "rg08" in got
    # a rejected group is never hinted
    assert _hint("merge_SYN_x_sample", _group("rgI", "01_SYN_x_sample", status="rejected")) == []


def test_a_rejected_group_cannot_be_tied_and_a_tie_says_what_it_takes_from_another_group():
    T = _proc()
    A = _A()
    entries = [_entry(T, "07_SYN_ZZ_pH1_m300mV_023_merged", "SYN.prj", is_merge=True)]  # matches rg-07 by name
    groups = [*GROUPS, _group("rg-no", "99_SYN_no", status="rejected")]
    _, rows = A.resolve_ties({"rg-no": [{"project": "SYN.prj", "athena_group": entries[0]["label"]}]}, entries, groups)
    assert rows[0]["status"] == "no_live_group"
    by_entry, rows = A.resolve_ties({"rg-12": [{"project": "SYN.prj", "athena_group": entries[0]["label"]}]}, entries, groups)
    assert by_entry == {0: ["rg-12"]} and rows[0]["also_matches_by_name"] == ["rg-07"]
    assert "also matches rg-07" in rows[0]["statement"]
    matched, _, _ = A.match_with_versions(groups, entries, T.np, ties=by_entry)
    assert list(matched) == ["rg-12"]


def test_the_scientists_no_stops_the_hint_for_that_group():
    T = _proc()
    A = _A()
    entries = [_entry(T, "merge4_12_SYN_E2_pH1_m300mV_spt2", "SYN_a.prj", is_merge=True, data="m"),
               _entry(T, "merge4_12_SYN_E2_pH1_m300mV_spt2", "SYN_b.prj", is_merge=True, data="m")]
    nots, rows = A.resolve_ties({"rg-12": [{"project": "SYN_a.prj", "athena_group": entries[0]["label"]}]}, entries,
                                GROUPS, not_this=True)
    assert rows[0]["status"] == "not_this_group" and "is not rg-12's" in rows[0]["statement"]
    [item] = A.unmatched_merges(GROUPS, entries, not_this=nots)
    # still listed (it matches no group), but no longer hinted for rg-12, its copy in SYN_b.prj included
    assert item["candidates"] == [] and item["not_this_group"] == ["rg-12"]


# --- review M1: a tie is recorded where the approval and the record are -------------------------------------------


STEM = "12_SYN_ZZ_pellet_040"
MERGE = "merge4_12_SYN_ZZ_pelet_spt2"


def _tie_case(tmp_path):
    from test_local_import_polish_c2f import _xdac, std_scan
    from test_local_import_polish_c10m import _prj

    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M

    T = _proc()
    root = tmp_path / "SYN_beamtime"
    for k in (1, 2):
        _xdac(root / "bt" / f"{STEM}_A.00{k}", std_scan(k, i1_positive=True))
    _prj(root / "bt" / "SYN.prj", [(MERGE, T.GRID, T.mu_edge(T.GRID, 4966.2) * 1e-2)])
    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    M.group(out)
    return out, root


def _of(bdir, source):
    from isaac_api.local_import import mutations as M

    return [r for r in M.load(bdir)["processing_results"] if r["source"] == source]


def test_a_tied_merge_is_approved_on_its_own_and_its_approval_and_record_say_the_tie(tmp_path, capsys):
    from isaac_api.local_import import mutations as M
    from isaac_api.local_import import records as R
    from isaac_api.local_import.processing import run as RUN

    from test_local_import_records import BY

    bdir, root = _tie_case(tmp_path)
    first = M.process(bdir, source=str(root))
    assert any("A merge exists but was not matched" in line for line in first["summary"]["lines"])
    [isa0] = _of(bdir, "isaac_protocol")
    assert RUN.UNMATCHED_MERGE_KEY in isa0["review_flags"]
    gid = isa0["group_id"]
    params = tmp_path / "SYN_params.json"
    params.write_text(json.dumps({"athena_match": {gid: [{"project": "bt/SYN.prj", "athena_group": MERGE}]}}))
    M.process(bdir, source=str(root), params_file=str(params))
    capsys.readouterr()
    ath = next(r for r in _of(bdir, "scientist_athena") if r["state"] == "needs_review")
    assert ath["inputs"][0]["match_kind"] == "named_by_scientist" and RUN.TIED_FLAG in ath["review_flags"]
    tie = ath[RUN.TIE_KEY]
    assert tie["project"] == "bt/SYN.prj" and tie["params_file"].endswith("params.json")
    assert "athena_match" in json.loads((bdir / tie["params_file"]).read_text())
    # the merge is tied: the group is no longer hinted, and ISAAC's fresh result is not asked again
    isa = next(r for r in _of(bdir, "isaac_protocol") if r["run_id"] == ath["run_id"])
    assert RUN.UNMATCHED_MERGE_KEY not in isa["review_flags"]
    assert not any(q["code"] == RUN.UNMATCHED_MERGE_QUESTION for q in isa.get("questions") or ())
    # a bulk approval refuses it: it is read and approved on its own
    with pytest.raises(M.MutationRefused, match="tied to its group by the params file"):
        M.decide(bdir, target_ids=[ath["result_id"], isa["result_id"]], decision="approve", value=None,
                 qc_status="valid", **BY)
    M.decide(bdir, target_ids=[ath["result_id"]], decision="approve", value=None, qc_status="valid", **BY)
    [d] = [d for d in M.load(bdir)["scientist_decisions"] if (d.get("target") or {}).get("id") == ath["result_id"]]
    assert f"Athena group '{MERGE}' in bt/SYN.prj was tied to this group by the scientist's params file" in d["note"]
    group = next(g for g in M.load(bdir)["record_groups"] if g["group_id"] == gid)
    draft, _ = R.compose_group(M.load(bdir), group, bdir)
    out = draft["descriptors_outputs"][0]
    assert f"The scientist tied Athena group '{MERGE}' in SYN.prj to this group" in out["generated_by"]["notes"]
    assert "bt/" not in out["generated_by"]["notes"]  # the project's file name only in the record
    ev = out["descriptors"][0]["evidence"]
    assert any(e.get("source_file") == tie["params_file"] and e.get("locator") == "athena_match" for e in ev)
    # the next process without the params file says the tie was not passed, and never "no Athena curve"
    again = M.process(bdir, source=str(root))
    capsys.readouterr()
    lines = [x["statement"] for x in again.get("decided_results_on_an_older_run") or ()]
    [line] = [x for x in lines if ath["result_id"] in x]
    assert "the params file's athena_match for this group was not passed this time" in line
    # the group's merge was tied in its decided result: the hint and question are not offered again
    fresh = [r for r in _of(bdir, "isaac_protocol") if r["run_id"] != ath["run_id"]]
    assert fresh and not any(RUN.UNMATCHED_MERGE_KEY in r["review_flags"] for r in fresh)


def test_a_kept_result_loses_the_sentence_once_its_merge_is_tied():
    from isaac_api.local_import.processing import run as RUN

    stored = [{"result_id": "proc-g1-r-a-isaac", "group_id": "g1", "review_flags": [RUN.UNMATCHED_MERGE_KEY, "x"],
               "qc": {"statements": {RUN.UNMATCHED_MERGE_KEY: "SYN said", "other": "kept"}}}]
    notes = RUN.say_unmatched_merges([], [], stored=stored)
    assert RUN.apply_kept_result_notes(stored, notes) == 1
    assert stored[0]["review_flags"] == ["x"] and stored[0]["qc"]["statements"] == {"other": "kept"}


def test_show_prints_the_renormalisation_record_and_the_summary_names_material_results():
    from isaac_api.local_import import cli
    from isaac_api.local_import.processing import run as RUN

    rec = {"material": True, "post_edge_difference_from_larch": 0.05}
    r = {"result_id": "proc-g-r-0-athena", "group_id": "g", "source": "scientist_athena", "inputs": [], "steps": [],
         "renormalised_from_project": rec}
    assert cli._processing_result_view({"record_groups": []}, r)["renormalised_from_project"] == rec
    assert "renormalised_from_project" not in cli._processing_result_view({"record_groups": []}, {**r, "renormalised_from_project": None})
    assert "post-edge range: proc-g-r-0-athena." in RUN.renormalisation_line([r])
