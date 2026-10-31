"""Polish c10-m: walkthrough findings on a real BL4-3 beamtime (an electrochemistry series), reproduced here.
SYNTHETIC files only: every scan and Athena project below is invented and named ``SYN_``.

* (MED-1) The scientist's per-scan Athena groups of ONE run, kept in two projects, are read as one SET per project
  (``per_scan_set``), never as "N different Athena versions" of single scans. The walkthrough's 42-scan group was
  asked to choose among 20 single-scan "versions": its scans 1-22 sat in one project and 1-25 in another, with
  the same raw data but another normalisation; collapsing them by data hash alone mixed the two projects, and the
  one-project rule then listed every scan as a version. Now each project's set is one version, and the
  result-of-record question is asked only between those genuinely different sets. A set of only some of the
  run's scans is flagged ``scientist_selected_subset_of_scans`` and says so ("scans 1-2 of the 4 scans ISAAC
  merged"), as a label-selected subset always was.
* (MED-2) With a group in scope (``--scope group:<id>``, or the minimum's ``only``), an experiment-wide question
  leads with the AI suggestion read for THAT group's runs (its text and its hint order); its id and its unscoped
  text are unchanged.
* (LOW-5) The minimum's ``recommended`` names each question once, ``warnings`` states each sentence once, and a
  potential written in a scan header is labelled as the header's, not the file name's.
* (LOW-6) A question asked once for the whole beamtime counts the groups it reaches (``groups_count``), as
  ``decide`` says it reaches them.
* (LOW-7) A result with no usable scan because its only scan has too few points says so in a plain sentence, and
  its scans line is not empty; its result id does not move.
"""

from __future__ import annotations

import json
import shutil

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

SUBSET = "scientist_selected_subset_of_scans"


# --- MED-1: per-scan Athena groups in two projects ---------------------------------------------------------------


def _processing():
    pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")


def _prj(path, groups, *, norm1=60.0, norm2=130.0):
    """An Athena project of ``groups`` (label, energy, mu), each normalised with these post-edge bounds."""
    import larch.xafs as xafs
    from larch import Group
    from larch.io import AthenaProject

    path.parent.mkdir(parents=True, exist_ok=True)
    prj = AthenaProject()
    for label, e, mu in groups:
        g = Group(energy=e, mu=mu, label=label, filename=label)
        xafs.pre_edge(g, pre1=-50, pre2=-30, norm1=norm1, norm2=norm2, nnorm=2)
        prj.add_group(g)
    prj.save(str(path))


def _case(tmp_path, projects, *, scans=4):
    """ONE run ``01_SYN_ZZ1`` of ``scans`` scans, and ``projects``: {path: ([scan numbers], norm1)} of per-scan
    Athena groups ``01_SYN_ZZ1_A.00N`` (scan N's curve is the same raw data in every project)."""
    from test_local_import_processing import GRID, fluo_scan, make_case, mu_edge, spec_file

    bdir, root, bundle = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(fluo_scan(s)) for s in range(1, scans + 1)],
                                               {"sample_name": "ZZ1"})])
    for rel, (numbers, norm1) in projects.items():
        _prj(root / rel, [(f"01_SYN_ZZ1_A.{n:03d}", GRID, mu_edge(GRID) * (1e-2 + 1e-4 * n)) for n in numbers], norm1=norm1)
        bundle["unread_files"].append({"source_id": f"prj-{rel}", "relative_path": rel})
    (bdir / "bundle.json").write_text(json.dumps(bundle))
    return bdir, root


def _process(bdir, root):
    from isaac_api.local_import.processing.cli_entry import run_process

    out = run_process(bdir, source_root=root)
    isa = next(r for r in out["processing_results"] if r["source"] == "isaac_protocol")
    ath = next((r for r in out["processing_results"] if r["source"] == "scientist_athena"), None)
    return out, isa, ath


def test_per_scan_groups_in_two_projects_are_two_sets_not_a_version_per_scan(tmp_path):
    _processing()
    bdir, root = _case(tmp_path, {"a/SYN_day1.prj": ([1, 2], 60.0), "b/SYN_merge.prj": ([1, 2, 3], 90.0)})
    out, isa, ath = _process(bdir, root)
    assert ath is None and isa["athena_result_of_record"] is None
    versions = isa["athena_versions"]
    # one version per project: each project's per-scan groups are ONE set, never one version per scan
    assert [v["provenance"]["prj_relative_path"] for v in versions] == ["a/SYN_day1.prj", "b/SYN_merge.prj"]
    assert [v["provenance"]["scan_selection"] for v in versions] == [[1, 2], [1, 2, 3]]
    assert [v["provenance"]["per_scan_set"]["athena_groups"] for v in versions] == [
        ["d_01_SYN_ZZ1_A_001", "d_01_SYN_ZZ1_A_002"], ["d_01_SYN_ZZ1_A_001", "d_01_SYN_ZZ1_A_002", "d_01_SYN_ZZ1_A_003"]]
    [q] = isa["questions"]
    assert q["text"].startswith("2 different Athena versions of this measurement exist.")
    # each is a subset of the run's 4 scans
    assert all(SUBSET in v["comparison"]["flags"] for v in versions)
    assert all(v["comparison"]["athena_scan_selection"] == v["provenance"]["scan_selection"] for v in versions)
    assert out["athena"]["record_groups_with_unselected_versions"] == 1


def test_the_same_per_scan_groups_in_two_projects_are_one_set(tmp_path):
    _processing()
    bdir, root = _case(tmp_path, {"a/SYN_day1.prj": ([1, 2], 60.0), "b/SYN_copy.prj": ([1, 2], 60.0)})
    out, isa, ath = _process(bdir, root)
    assert "athena_versions" not in isa and ath is not None
    assert ath["inputs"][0]["scans_basis"] == "per_scan_set" and ath["inputs"][0]["scans"] == [1, 2]
    assert out["athena"]["record_groups_with_unselected_versions"] == 0


def test_per_scan_groups_of_some_of_the_runs_scans_are_flagged_a_subset(tmp_path):
    _processing()
    bdir, root = _case(tmp_path, {"SYN.prj": ([1, 2], 60.0)})
    _, isa, ath = _process(bdir, root)
    assert ath["inputs"][0]["scans_basis"] == "per_scan_set"
    assert SUBSET in isa["comparison"]["flags"] and isa["comparison"]["athena_scan_selection"] == [1, 2]
    said = ath["qc"]["statements"]["scans_used"]
    assert said.startswith("The scientist's curve is ISAAC's mean of 2 per-scan Athena groups, one each for scans 1-2")
    assert "It covers only scans 1-2 of the 4 scans ISAAC merged" in said
    # one run: preferred, as a label-selected subset of one run always was
    assert ath["preferred_for_record"] is True
    note = M.scan_subset_note({"processing_results": [isa, ath]}, ath)
    assert note and "scans 1, 2 of the 4 scan(s) ISAAC merged" in note


def test_per_scan_groups_of_every_scan_are_not_a_subset(tmp_path):
    _processing()
    bdir, root = _case(tmp_path, {"SYN.prj": ([1, 2], 60.0)}, scans=2)
    _, isa, ath = _process(bdir, root)
    assert SUBSET not in isa["comparison"]["flags"]
    assert ath["qc"]["statements"]["scans_used"] == (
        "The scientist's curve is ISAAC's mean of 2 per-scan Athena groups, one each for scans 1-2 (read from their "
        "labels). ISAAC's own curve for this group merges 2 of 2 listed scans.")


# --- LOW-7: the only scan has too few points ---------------------------------------------------------------------


def test_a_scan_with_too_few_points_says_so_and_the_id_does_not_move(tmp_path):
    _processing()
    import hashlib

    from isaac_api.local_import.processing import run as RUN
    from test_local_import_processing import GRID, fluo_scan, make_case, spec_file

    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", [spec_file(fluo_scan(1, e=GRID[:2]))], {"sample_name": "ZZ1"})])
    _, isa, _ = _process(bdir, root)
    assert isa["failure"] == {"code": "no_usable_scan", "detail": "too_few_points"}
    assert isa["qc"]["statements"]["no_usable_scan"] == (
        "The only scan has 2 usable points; at least 5 are needed, so there is no curve to process.")
    # the id is the failure's, exactly as before: the sentence and the counts are outside it
    rid = RUN.run_id_for(isa["group_id"], [], [("failure", hashlib.sha256(b"no_usable_scan:too_few_points").hexdigest())])
    assert isa["result_id"] == f"proc-{isa['group_id']}-{rid}-isaac"
    assert cli._scans_line(isa) == "0 of 1 scans used; 1 skipped (too_few_points)"


def test_several_scans_with_too_few_points_are_counted(tmp_path):
    _processing()
    from test_local_import_processing import GRID, fluo_scan, make_case, spec_file

    scans = [spec_file(fluo_scan(1, e=GRID[:2])), spec_file(fluo_scan(2, e=GRID[:3]))]
    bdir, root, _ = make_case(tmp_path, [("01_SYN_ZZ1", scans, {"sample_name": "ZZ1"})])
    _, isa, _ = _process(bdir, root)
    assert isa["qc"]["statements"]["no_usable_scan"] == (
        "No scan could be used: 2 have too few usable points (2, 3); at least 5 are needed, so there is no curve to "
        "process.")


# --- MED-2: a group in scope leads with the AI suggestion read for its runs --------------------------------------


from test_local_import_polish_c4a import _groups  # noqa: E402
from test_local_import_records import BY, _miss, bdir, pristine  # noqa: E402,F401  (fixtures)

ENV = "context.environment"


def _annotated(bdir, values):
    """One group per run (g0, g1, ...); the AI reads ``values[n]`` for run n's context.environment."""
    b = M.load(bdir)
    _groups(b, *((f"g{n}", r) for n, r in enumerate(b["runs"])))
    M.save_bundle(bdir, b)
    for n, value in enumerate(values):
        M.annotate(bdir, target_id=_miss(b, ENV, b["runs"][n]["run_id"]), value=value, excerpt_locator=f"line {n + 2}",
                   source_id=None, model_id="synthetic", blind=False, rationale="synthetic")
    return M.load(bdir)


def _env_question(rows):
    return next(q for q in rows if q["target_field_path"] == ENV and q["scope"] == "experiment")


def test_a_group_in_scope_leads_with_the_suggestion_read_for_its_runs(bdir):
    b = M.load(bdir)
    assert len(b["runs"]) >= 3
    b = _annotated(bdir, ["ex_situ", "in_situ", "in_situ"])
    payload = Q.consolidate(b)
    whole = _env_question(payload["questions"])
    assert "An AI reading of the files suggests 'in_situ', read for 2 of" in whole["text"]
    assert [h["literal"] for h in whole["hints"] if h["kind"] == "ai_suggestion"] == ["in_situ", "ex_situ"]
    mine = _env_question(Q.filter_questions(payload, scope="group:g0"))
    assert mine["question_id"] == whole["question_id"]
    assert "An AI reading of the files suggests 'ex_situ', read for 1 of" in mine["text"]
    assert "; 1 other AI suggestion(s) differ" in mine["text"] and "'in_situ'" not in mine["text"]
    assert [h["literal"] for h in mine["hints"] if h["kind"] == "ai_suggestion"] == ["ex_situ", "in_situ"]
    # the unscoped question is unchanged, and so is a group whose runs read the leading suggestion
    assert _env_question(Q.consolidate(b)["questions"]) == whole == _env_question(payload["questions"])
    assert _env_question(Q.filter_questions(payload, scope="group:g1"))["text"] == whole["text"]


def test_the_minimum_names_the_suggestion_read_for_its_group(bdir):
    b = _annotated(bdir, ["ex_situ", "in_situ", "in_situ"])
    payload = Q.consolidate(b)
    qid = _env_question(payload["questions"])["question_id"]
    minimum = Q.minimum_answers_for_one_group(payload, b, scope="group:g0")
    [entry] = [e for e in minimum["questions"] if e["question_id"] == qid]
    assert entry["only"] == "group:g0"
    assert entry["ai_suggestion"].startswith("An AI reading of the files suggests 'ex_situ', read for 1 of")


# --- LOW-6: groups_count is the reach ----------------------------------------------------------------------------


def test_a_beamtime_question_counts_every_group_it_reaches(bdir, capsys):
    _annotated(bdir, [])
    b = M.load(bdir)
    capsys.readouterr()
    assert cli.main(["bundle", "questions", str(bdir), "--limit", "200"]) == 0
    page = json.loads(capsys.readouterr().out)["questions"]
    live = len(Q.live_groups(b))
    who = next(q for q in page if q["target_field_path"] == "attribution.produced_by.group" and q["scope"] == "experiment")
    assert who["groups_count"] == who["applies_to"]["groups"] == live
    for q in page:
        assert q["groups_count"] == q["applies_to"]["groups"]


# --- LOW-5: the minimum's recommendation, once, with each reading labelled ---------------------------------------


from test_local_import_polish_c8b import (  # noqa: E402,F401  (fixtures)
    SCALE, SETPOINT, _confirm_groups, _run_id, _warnings_of, grouped, grouped_pristine, imported, src)


def test_the_minimum_recommends_each_question_once_and_states_each_warning_once(grouped):
    b = _confirm_groups(grouped)
    gid = next(g["group_id"] for g in b["record_groups"] if _run_id(b, "SYN_cat_500mV_101") in g["member_run_ids"])
    minimum = Q.minimum_answers_for_one_group(Q.consolidate(b), b, scope=f"group:{gid}")
    rec = minimum["recommended"]
    assert sorted(f for r in rec for f in r["fields"]) == sorted([SCALE, SETPOINT])
    assert len({r["question_id"] for r in rec}) == len(rec)
    assert len(minimum["warnings"]) == len(set(minimum["warnings"])) == 1


def test_a_potential_in_a_scan_header_is_labelled_the_headers(grouped):
    b = _confirm_groups(grouped)
    [w] = _warnings_of(grouped, b, "SYN_cat_500mV_101")
    text = w["text"]
    assert text.startswith("the file names and scan headers state a potential (500mV in SYN_cat_500mV_101_A.001; "
                           "0.5Vrhe in the scan header of SYN_cat_500mV_101_A.001)")
    assert "0.5Vrhe is written in the scan header" in text
