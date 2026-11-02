"""r7-k: the scientist's Athena merges and why a group has new results, on SYNTHETIC spectra and SYN_* names only.

K1 a merge that matches no group and has no near name is named (label, project, the groups beside it) in the process
reply and the summary line, and ``bundle list <dir> athena-merges`` pages them all. K2 a new run made by a params file
says so ("the params file's exclude_scans leaves …", "… athena_match ties …"); "this build" only when nothing the params
file does explains it; no stale flag name. K3 a hint never crosses run numbers (``01_05`` / ``03_04``), names the run
numbers that differ, ranks the same numbers first; Athena's reference channels ("  Ref <name>") are no sample merges.
K4 a chosen Athena version has its own plot with its curve overlaid. K5 a params file's ``athena_ignore`` sets a merge
aside (said once, nothing else changes). K6 an Athena group whose name matches several groups is said, as a hint that
they may be one sample (never merged by ISAAC).
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


def _group(gid, *stems, status="scientist_confirmed"):
    return {"group_id": gid, "_stems": list(stems), "_has_scans": True, "status": status}


def _merge(label, prj="SYN.prj", data=None):
    A = _A()
    return {"names": [A.normalise_name(label)], "label": label, "group_name": label.strip().lower(),
            "prj_relative_path": prj, "is_merge": True, "data_hash": data or f"h-{label}-{prj}"}


def _hint(label, *groups):
    A = _A()
    return [c["group_id"] for c in A.near_name_candidates(_merge(label), list(groups))]


# --- K3: hints never cross run numbers; reference channels are no merges ---------------------------------------------


def test_a_hint_never_crosses_electrode_or_run_numbers_and_names_the_ones_that_differ():
    A = _A()
    g0105 = _group("rg-0105", "01_05_SYN_jk1c_after_600mV")
    g0304 = _group("rg-0304", "03_04_SYN_jk1c_after_600mV")
    # the same words under other run numbers is another run: never a hint, however alike
    assert _hint("merge_01_05_SYN_jk1c_after_600mV_x", g0105, g0304) == ["rg-0105"]
    assert _hint("merge_04_11_SYN_k_1800mV6_8", _group("rg-0404", "04_04_SYN_k_600mV"),
                 _group("rg-0408", "04_08_SYN_k_1200mV"), _group("rg-0411", "04_11_SYN_k_1800mV")) == ["rg-0411"]
    # a merge of runs 03 and 05 still hints the group of run 05 (one number, named by the merge)
    assert _hint("merge_03_05_SYN_pellet", _group("rg-05", "05_SYN_pellet")) == ["rg-05"]
    # review L3: one more number after the same electrode and run is the same run (01_12_13 / 01_12)
    assert _hint("merge_01_12_13_SYN_k_2000mV", _group("rg-0112", "01_12_SYN_k_2000mV"),
                 _group("rg-0212", "02_12_SYN_k_2000mV")) == ["rg-0112"]
    # the same run numbers rank first; a group without a run number is still a likeness hint
    got = _hint("merge_07_SYN_x_dry_spot3", _group("rg-07", "07_SYN_x_dry_spot3b"), _group("rg-nn", "SYN_x_dry_spot3"))
    assert got[0] == "rg-07" and "rg-nn" in got
    # the run numbers one names and the other does not are named
    [c] = A.near_name_candidates(_merge("merge_04_11_SYN_q"), [_group("rg-04", "04_SYN_q_z")])
    assert c["differs_in"]["merge"][0] == "11" and c["same_run_numbers"] is False
    # NEGATIVE CONTROL: the r6 veto on other digits is unchanged
    assert _hint("merge_SYNNiO_pH7_m200mV", _group("rg-F", "03_SYNNiO_pH7_m300mV")) == []


def test_athenas_reference_channels_are_counted_never_listed_or_hinted():
    A = _A()
    from isaac_api.local_import.processing import run as RUN

    groups = [_group("rg-0105", "01_05_SYN_jk1c_600mV"), _group("rg-0304", "03_04_SYN_jk1c_600mV")]
    ref = _merge("  Ref 01_05_SYN_jk1c_600mV")
    real = _merge("merge_01_05_SYN_jk1c_600mV_spt")
    assert A.is_reference_channel(ref) and not A.is_reference_channel(real)
    assert not A.is_reference_channel(_merge("Refined_SYN_x"))  # a word, not Athena's "Ref <name>"
    # review L2: Athena's exact form only (two spaces, "Ref", a space)
    assert not any(A.is_reference_channel(_merge(x)) for x in ("Ref SYN_x", "  ref SYN_x", " Ref SYN_x", "   Ref SYN_x"))
    assert A.near_name_candidates(ref, groups) == []
    items = A.unmatched_merges(groups, [ref, real])
    assert [i["athena_label"] for i in items] == [real["label"]]
    refs = A.unmatched_reference_channels(groups, [ref, real])
    assert [r["athena_label"] for r in refs] == ["Ref 01_05_SYN_jk1c_600mV"]
    line = RUN.unmatched_merges_line(items, reference_channels=len(refs))
    assert "1 more Athena group(s) that match no group are reference channels" in line
    assert RUN.unmatched_merges_line([], reference_channels=3).startswith("Athena: 3 Athena group(s)")
    # a leading "ref" word is no part of a merge's name when its run numbers are read
    [c] = A.near_name_candidates(_merge("merge_ref_01_05_SYN_jk1c_600mV_b"), groups)
    assert c["group_id"] == "rg-0105" and c["same_run_numbers"]


# --- K1: every unmatched merge is named, and paged -------------------------------------------------------------------


def test_the_line_names_a_merge_with_no_near_name_and_the_groups_beside_it():
    from isaac_api.local_import import mutations as M
    from isaac_api.local_import.processing import run as RUN

    groups = [_group("rg-a", "10_SYN_anatase_low"), _group("rg-b", "11_SYN_rutile")]
    entries = [{**_merge("10_SYN_anatase_low", "SYN/day1.prj"), "is_merge": False}, _merge("merge5", "SYN/day1.prj")]
    items = _A().unmatched_merges(groups, entries)
    RUN.project_groups(items, groups, entries)
    assert items[0]["groups_in_project"] == ["rg-a"]
    line = RUN.unmatched_merges_line(items)
    assert "1 have no near name: 'merge5' (day1.prj, beside the Athena groups of rg-a)" in line
    assert "athena-merges` lists every one" in line and "processing_results.json" not in line
    # the reply lists at most 10 compact rows and says how to page the rest
    many = [{**items[0], "athena_label": f"merge{k}"} for k in range(13)]
    reply = M.unmatched_merges_reply({"unmatched_merges": many})
    assert reply["total"] == 13 and len(reply["merges"]) == 10 and "--offset 10" in reply["more"]
    assert reply["merges"][0] == {"athena_label": "merge0", "projects": ["SYN/day1.prj"], "athena_group": "merge5",
                                  "near_groups": [], "groups_in_project": ["rg-a"]}
    assert M.unmatched_merges_reply({}) is None


def test_process_replies_with_the_merges_and_bundle_list_pages_them(tmp_path, capsys):
    _proc()
    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M
    from test_local_import_polish_r6g import MERGE, _tie_case

    bdir, root = _tie_case(tmp_path)
    out = M.process(bdir, source=str(root))
    capsys.readouterr()
    [row] = out["athena_unmatched_merges"]["merges"]
    assert row["athena_label"] == MERGE and row["near_groups"] and row["projects"] == ["bt/SYN.prj"]
    assert cli.main(["bundle", "list", str(bdir), "athena-merges"]) == 0
    page = json.loads(capsys.readouterr().out)
    assert page["kind"] == "athena-merges" and page["total"] == 1 and page["items"] == [row] and "capped" not in page
    # review L5: the true count is stored beside the kept list, and a capped list says so
    path = bdir / "processing" / "processing_results.json"
    data = json.loads(path.read_text())
    assert data["athena"]["unmatched_merges_total"] == 1
    data["athena"]["unmatched_merges_total"] = 612
    path.write_text(json.dumps(data))
    assert cli.main(["bundle", "list", str(bdir), "athena-merges"]) == 0
    assert json.loads(capsys.readouterr().out)["capped"] == "612 merges match no group; the first 1 are kept and listed"
    # NEGATIVE CONTROL: a bundle never processed lists nothing and says so
    other = tmp_path / "SYN_other"
    from test_local_import_polish_r6g import STEM
    from test_local_import_polish_c2f import _xdac, std_scan

    _xdac(other / "src" / f"{STEM}_A.001", std_scan(1, i1_positive=True))
    assert cli.main(["import", str(other / "src"), "--out", str(other / "out")]) == 0
    capsys.readouterr()
    assert cli.main(["bundle", "list", str(other / "out"), "athena-merges"]) == 0
    page = json.loads(capsys.readouterr().out)
    assert page["total"] == 0 and page["statement"].startswith("Not processed yet")


# --- K5: the scientist sets a merge aside -----------------------------------------------------------------------------


def test_the_params_ignore_section_is_checked_and_kept_out_of_the_resolved_params():
    from isaac_api.local_import.processing import protocol as P

    assert P.athena_ignores(None) == [] and P.athena_ignores({}) == []
    one = {"project": "a.prj", "athena_group": "m5"}
    assert P.athena_ignores({"athena_ignore": one}) == [one] == P.athena_ignores({"athena_ignore": [one]})
    for bad in ([], {"rg-1": [one]}, [{"project": "a.prj"}], [{"project": " ", "athena_group": "g"}], "m5"):
        with pytest.raises(ValueError, match="athena_ignore must be"):
            P.athena_ignores({"athena_ignore": bad})
    assert P.resolve_params({"athena_ignore": [one]}) == P.resolve_params(None)  # no params.json moves


def test_a_merge_set_aside_and_its_copies_are_no_longer_listed():
    A = _A()
    groups = [_group("rg-a", "10_SYN_anatase")]
    entries = [_merge("merge5", "SYN/a.prj", data="d"), _merge("merge5", "SYN/b.prj", data="d"),
               {**_merge("10_SYN_anatase", "SYN/a.prj"), "is_merge": False}]
    ignored, rows = A.resolve_ignores([{"project": "a.prj", "athena_group": "merge5"},
                                       {"project": "a.prj", "athena_group": "10_SYN_anatase"},
                                       {"project": "z.prj", "athena_group": "merge5"}], entries, groups)
    assert ignored == {0} and [r["status"] for r in rows] == ["ignored", "not_unmatched", "not_found"]
    assert A.unmatched_merges(groups, entries, ignored=ignored) == []
    assert len(A.unmatched_merges(groups, entries)[0]["in"]) == 2
    from isaac_api.local_import.processing import run as RUN

    line = RUN.athena_ignore_line(rows)
    assert line.startswith("Athena: 1 merge(s) the scientist set aside") and "nothing was set aside" in line
    assert RUN.athena_ignore_line([]) is None
    # review L4: one the same params file ties to a group is "tied", never set aside
    got, rows = A.resolve_ignores([{"project": "a.prj", "athena_group": "merge5"}], entries, groups, tied={0: ["rg-a"]})
    assert got == set() and rows[0]["status"] == "tied" and "the tie stands" in rows[0]["statement"]


def test_process_with_athena_ignore_lists_nothing_and_moves_no_id(tmp_path, capsys):
    _proc()
    from isaac_api.local_import import mutations as M
    from isaac_api.local_import.processing import run as RUN
    from test_local_import_polish_r6g import MERGE, _tie_case

    bdir, root = _tie_case(tmp_path)
    M.process(bdir, source=str(root))
    before = sorted(r["result_id"] for r in M.load(bdir)["processing_results"])
    params = tmp_path / "SYN_ignore.json"
    params.write_text(json.dumps({"athena_ignore": [{"project": "SYN.prj", "athena_group": MERGE}]}))
    out = M.process(bdir, source=str(root), params_file=str(params))
    capsys.readouterr()
    results = M.load(bdir)["processing_results"]
    assert sorted(r["result_id"] for r in results) == before
    assert "athena_unmatched_merges" not in out
    assert not any("A merge exists but was not matched" in line for line in out["summary"]["lines"])
    [said] = [line for line in out["summary"]["lines"] if "set aside as no group's" in line]
    assert MERGE in said
    assert not any(RUN.UNMATCHED_MERGE_KEY in (r.get("review_flags") or ()) for r in results)


# --- K6: an Athena group whose name fits several groups ----------------------------------------------------------------


def test_a_merge_that_fits_several_groups_is_said_as_a_hint_never_merged():
    T = _proc()
    A = _A()
    from isaac_api.local_import.processing import run as RUN

    groups = [_group("rg-091", "11_SYN_tion_dry_091"), _group("rg-092", "11_SYN_tion_dry_092")]
    mu = T.mu_edge(T.GRID) * 1e-2
    entry = {"names": ["merge_11_syn_tion_dry"], "label": "merge_11_SYN_tion_dry", "group_name": "merge_11_syn_tion_dry",
             "prj_relative_path": "SYN/a.prj", "prj_source_id": None, "is_merge": True, "energy": T.GRID.copy(),
             "mu": mu, "norm": mu / 0.015, "flat": mu / 0.015, "e0_eV": T.E0, "edge_step": 0.015,
             "params": {}, "data_hash": "m", "non_finite_values": [], "energy_frame_known": True}
    matched, notes, _ = A.match_with_versions(groups, [entry, {**entry, "prj_relative_path": "SYN/b.prj"}], T.np)
    assert matched == {} and len(notes) == 2
    bundle = {"merge_candidates": [{"merge_candidate_id": "mc-SYN", "status": "proposed", "group_ids": ["rg-092", "rg-091"]}]}
    line = RUN.several_groups_line(notes, groups, bundle)
    assert line.startswith("Athena: 1 of the scientist's Athena group(s) match several record groups")
    assert "'merge_11_SYN_tion_dry' (a.prj, b.prj) matches rg-091, rg-092" in line
    assert "may be one sample" in line and "merge candidate mc-SYN" in line and "Only on their yes" in line
    # NEGATIVE CONTROLS: a rejected group is no hint of one sample; no such note, no line
    gone = [groups[0], {**groups[1], "status": "rejected"}]
    assert "may be one sample" not in RUN.several_groups_line(notes, gone, bundle)
    assert RUN.several_groups_line([], groups, bundle) is None


# --- K2: a new run made by the params file says so -------------------------------------------------------------------


def _res(rid, run, source="isaac_protocol", **kw):
    return {"result_id": rid, "group_id": "g1", "run_id": run, "source": source, "inputs": [{"source_id": "s1"}], **kw}


def _bundle(rid, what="needs_changes"):
    return {"scientist_decisions": [{"decision_id": "dec-1", "target": {"kind": "processing_result", "id": rid},
                                     "decision": what, "decided_by": {"name": "SYN Scientist"}}]}


EXCL = "scans_excluded_by_params_file"


def test_the_line_says_the_params_file_left_a_scan_out_never_this_build():
    from isaac_api.local_import import mutations as M

    old = _res("proc-g1-r-a-isaac", "r-a", inputs=[{"relative_path": "d/SYN_x_004.txt"}, {"relative_path": "d/SYN_x_005.txt"}])
    new = _res("proc-g1-r-b-isaac", "r-b", inputs=[{"relative_path": "d/SYN_x_004.txt"},
                                                   {"relative_path": "d/SYN_x_005.txt", "skip_reason": EXCL,
                                                    "excluded_as": "SYN_x_005.txt"}])
    [line] = M.decided_results_on_an_older_run(_bundle(old["result_id"]), [old], [old], [new])
    said = line["statement"]
    assert "the group has new results (proc-g1-r-b-isaac) because the params file's exclude_scans leaves SYN_x_005.txt out" in said
    assert "this build" not in said
    # the other way: the params file that left it out was not passed
    [back] = M.decided_results_on_an_older_run(_bundle(new["result_id"]), [new], [new], [_res(old["result_id"], "r-c", inputs=old["inputs"])])
    assert "exclude_scans that left SYN_x_005.txt out was not passed this time" in back["statement"]


def test_the_line_says_the_params_file_ties_the_curve_and_drops_the_flag_name():
    from isaac_api.local_import import mutations as M

    old = _res("proc-g1-r-a-isaac", "r-a", athena_versions=[{}] * 7)
    new = _res("proc-g1-r-b-isaac", "r-b")
    tied = _res("proc-g1-r-b-athena", "r-b", source="scientist_athena",
                inputs=[{"relative_path": "SYN/a.prj", "athena_group": "d_syn_6_8", "match_kind": "named_by_scientist"}],
                renormalised_from_project={"material": True})
    [line] = M.decided_results_on_an_older_run(_bundle(old["result_id"], "approve"), [old], [old], [new, tied])
    said = line["statement"]
    assert ("because the params file's athena_match ties the scientist's Athena group d_syn_6_8 in SYN/a.prj to this "
            "group (7 versions listed before)") in said
    assert "matched differently" not in said and "athena_renormalisation_differs" not in said and "this build" not in said
    # NEGATIVE CONTROL (r5 M2): with no params file the match and the rebuilt curve are said, in words only
    plain = dict(tied, inputs=[{"relative_path": "SYN/a.prj", "athena_group": "merge_syn"}])
    old = _res("proc-g1-r-a-isaac", "r-a", athena_versions=[{}] * 7)  # a line is said once per run: a fresh one
    [line] = M.decided_results_on_an_older_run(_bundle(old["result_id"]), [old], [old], [new, plain])
    assert "matched differently now" in line["statement"] and "as Athena makes it." in line["statement"]
    assert "(athena_renormalisation_differs)" not in line["statement"]


def _two_runs(tmp_path, a, b):
    for run, p in (("r-a", a), ("r-b", b)):
        d = tmp_path / "processing" / "g1" / run
        d.mkdir(parents=True)
        (d / "params.json").write_text(json.dumps(p))
    return _res("proc-g1-r-a-isaac", "r-a"), _res("proc-g1-r-b-isaac", "r-b")


@pytest.mark.parametrize("a, b, said", [
    # the params file sets it now
    ({"params": {"qc": {"k": 3}}, "changed_from_default": []}, {"params": {"qc": {"k": 5}}, "changed_from_default": ["qc.k"]},
     "because the params file sets qc.k."),
    # review M1: it set it before and was not passed this time
    ({"params": {"qc": {"k": 5}}, "changed_from_default": ["qc.k"]}, {"params": {"qc": {"k": 3}}, "changed_from_default": []},
     "because the params file that set qc.k was not passed this time"),
    # review M1: no params file either time: the build changed the default, or added a parameter
    ({"params": {"qc": {"k": 3}}, "changed_from_default": []}, {"params": {"qc": {"k": 5}}, "changed_from_default": []},
     "because this build added or changed the default of qc.k."),
    ({"params": {"qc": {"k": 3}}, "changed_from_default": []},
     {"params": {"qc": {"k": 3, "new": 1}}, "changed_from_default": []},
     "because this build added or changed the default of qc.new."),
])
def test_a_parameter_is_said_by_who_changed_it(tmp_path, a, b, said):
    from isaac_api.local_import import mutations as M

    old, new = _two_runs(tmp_path, a, b)
    [line] = M.decided_results_on_an_older_run(_bundle(old["result_id"]), [old], [old], [new], bundle_dir=tmp_path)
    assert said in line["statement"]
    assert ("params file" in said) != ("this build" in line["statement"])


def test_without_the_run_folders_nothing_is_guessed(tmp_path):
    from isaac_api.local_import import mutations as M

    old, new = _res("proc-g1-r-a-isaac", "r-a"), _res("proc-g1-r-b-isaac", "r-b")
    [line] = M.decided_results_on_an_older_run(_bundle(old["result_id"]), [old], [old], [new])
    assert "changed with this build" in line["statement"]


def test_exclusions_are_read_from_each_runs_params_json(tmp_path):
    from isaac_api.local_import import mutations as M

    # review L1: run r-a's ISAAC result was replaced earlier; its params.json still says what it left out
    excl = {"params": {"qc": {"k": 3}}, "excluded_scans": [{"relative_path": "d/SYN_x_005.txt", "named_as": "SYN_x_005.txt"}]}
    for run in ("r-a", "r-c"):
        d = tmp_path / "processing" / "g1" / run
        d.mkdir(parents=True)
        (d / "params.json").write_text(json.dumps(excl))
    old = _res("proc-g1-r-a-athena", "r-a", source="scientist_athena",
               inputs=[{"relative_path": "SYN/a.prj", "athena_group": "merge_syn"}])
    other = _res("proc-g1-r-b-isaac", "r-b", inputs=[{"relative_path": "d/SYN_x_005.txt", "skip_reason": EXCL}])
    new = _res("proc-g1-r-c-isaac", "r-c", inputs=[{"relative_path": "d/SYN_x_005.txt", "skip_reason": EXCL,
                                                    "excluded_as": "SYN_x_005.txt"}])
    [line] = M.decided_results_on_an_older_run(_bundle(old["result_id"]), [old, other], [old], [new], bundle_dir=tmp_path)
    assert "exclude_scans" not in line["statement"]  # the same scan was left out both times


def test_other_rule_versions_are_the_builds_reason_beside_the_params_file():
    from isaac_api.local_import import mutations as M

    # review L1b: rule versions are not hashed, but a new rule is still the build's doing
    old = _res("proc-g1-r-a-isaac", "r-a", rule_versions={"rule_ids": ["isaac.syn.a.v0"]},
               inputs=[{"relative_path": "d/SYN_x_005.txt"}])
    new = _res("proc-g1-r-b-isaac", "r-b", rule_versions={"rule_ids": ["isaac.syn.a.v0", "isaac.syn.b.v0"]},
               inputs=[{"relative_path": "d/SYN_x_005.txt", "skip_reason": EXCL, "excluded_as": "SYN_x_005.txt"}])
    [line] = M.decided_results_on_an_older_run(_bundle(old["result_id"]), [old], [old], [new])
    said = line["statement"]
    assert "exclude_scans leaves SYN_x_005.txt out" in said
    assert "this build processes it under other rules (isaac.syn.b.v0)" in said


# --- K4: the chosen version's own plot ----------------------------------------------------------------------------------


def test_a_chosen_athena_version_has_its_own_plot_with_its_curve(tmp_path, capsys):
    _proc()
    from isaac_api.local_import import mutations as M
    from isaac_api.local_import.processing import run as RUN
    from test_local_import_polish_r1a import _results, _versions_case
    from test_local_import_records import BY

    bdir, root = _versions_case(tmp_path)
    M.process(bdir, source=str(root))
    [isa] = _results(bdir, "isaac_protocol")
    v02 = isa["athena_versions"][1]
    M.decide(bdir, target_ids=[isa["result_id"]], decision="select_athena_version", value=v02["version_id"], **BY)
    M.process(bdir, source=str(root))
    capsys.readouterr()
    [isa2] = _results(bdir, "isaac_protocol")
    [ath] = _results(bdir, "scientist_athena")
    assert isa2["result_id"] == isa["result_id"]  # no id moves
    plot = next(f["relative_path"] for f in ath["outputs"]["files"] if f["role"] == "plot")
    assert plot.endswith(f"{isa['run_id']}/plot_athena_v02.png") and (bdir / plot).is_file()
    assert ath[RUN.VERSION_PLOT_KEY] == plot and plot in ath["qc"]["statements"][RUN.VERSION_PLOT_KEY]
    assert next(f["relative_path"] for f in isa2["outputs"]["files"] if f["role"] == "plot").endswith("/plot.png")
    # an approved version result is kept as it was, and still names its plot after the next process
    M.decide(bdir, target_ids=[ath["result_id"]], decision="approve", value=None, qc_status="valid", **BY)
    M.process(bdir, source=str(root))
    capsys.readouterr()
    [kept] = _results(bdir, "scientist_athena")
    assert kept["result_id"] == ath["result_id"] and kept[RUN.VERSION_PLOT_KEY] == plot
