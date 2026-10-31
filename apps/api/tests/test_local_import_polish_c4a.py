"""Polish c4-a: one approved processing result per group, the Athena result's attribution, the nearest group
is one that can export, an AI reading says how many runs it was read for, reveal says why there is no
comparison. Synthetic only.

* A group can hold an ISAAC result and a result for the scientist's own Athena curve. Approving the second
  while the first is approved is REFUSED, naming the approved one and the options (keep it, or reject/defer it
  first): two approvals made the record composer use neither, and validate said "no processing result exists".
  A bundle that already holds two approvals (an older build allowed them) says "two results approved for this
  group; approve exactly one: <ids>", never "no processing result".
* The Athena curve's scan subset (``scientist_selected_subset_of_scans``) is said in a plain line when it is
  approved or named.
* An exported record whose approved result is the scientist's Athena curve attributes its E0 descriptor to
  Athena (``generated_by.agent``), not to ISAAC's protocol; an ISAAC result still names ``isaac.xas.v0``-style.
* ``minimum_for_one_group`` never names a group none of whose runs lists a scan while another group exists.
* An AI reading of fewer runs than the question asks about says so in the text ("read for 1 of 3 runs").
* ``reveal`` of a target the parser holds no value for says why there is no comparison.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _decide_everything, _miss, _portal, bdir, fake_upstream, pristine)

ATHENA_PRJ = "SYN_project.prj"


def _add_athena(bdir: Path, *, subset: bool = True) -> None:
    """A SYNTHETIC result for the scientist's own Athena curve beside ISAAC's ``p1`` (group g1)."""
    b = M.load(bdir)
    p1 = next(r for r in b["processing_results"] if r["result_id"] == "p1")
    spec = bdir / "processing" / "g1_athena_norm.txt"
    spec.write_text("# SYNTHETIC\n" + "\n".join(f"{1000 + 5 * i} {min(1.0, i / 9):.3f}" for i in range(21)) + "\n")
    p2 = copy.deepcopy(p1)
    p2.update(
        result_id="p2", source="scientist_athena", preferred_for_record=True, state="candidate_extracted",
        review_flags=["scientist_processed_data", "isaac_did_not_change_scientist_values"],
        inputs=[{"source_id": p1["inputs"][0]["source_id"], "scan": "SYN_ZZ1_2-3", "channel": "vortDT",
                 "relative_path": ATHENA_PRJ, "athena_group": "syn_zz1_2_3", "match_kind": "exact"}],
        outputs={"files": [{"role": "athena_normalized", "relative_path": "processing/g1_athena_norm.txt",
                            "sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}],
                 "e0_eV": 1013.5, "edge_step": 1.0, "points": 21},
        comparison={"verdict": "differs", "metrics": {},
                    "flags": ["normalized_shape_differs"] + (["scientist_selected_subset_of_scans"] if subset else []),
                    "athena_scan_selection": [2, 3] if subset else None},
    )
    p1["inputs"] = [dict(p1["inputs"][0], scan=n) for n in (1, 2, 3)]
    b["processing_results"].append(p2)
    M.save_bundle(bdir, b)


def _approve(bdir, pid):
    return M.decide(bdir, target_ids=[pid], decision="approve", value=None, qc_status="valid", **BY)


# --- 1. one approved processing result per group ------------------------------------------------------------


def test_approving_a_second_result_of_a_group_is_refused_naming_the_approved_one(bdir):
    _decide_everything(bdir)  # approves p1 (ISAAC)
    _add_athena(bdir)
    before = (bdir / "bundle.json").read_bytes()
    with pytest.raises(M.MutationRefused) as exc:
        _approve(bdir, "p2")
    said = str(exc.value)
    assert "p1 is already approved for group g1" in said
    assert "--target p1 --decision reject" in said and "--target p1 --decision defer" in said
    assert "keep p1" in said and "Nothing was recorded" in said
    assert (bdir / "bundle.json").read_bytes() == before
    # re-stating the approval of the approved result itself is never refused
    assert M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="valid", **BY)["unchanged"] == ["p1"]


def test_after_deferring_the_approved_result_the_other_can_be_approved_and_says_its_scan_subset(bdir):
    _decide_everything(bdir)
    _add_athena(bdir)
    M.decide(bdir, target_ids=["p1"], decision="defer", value=None, **BY)
    out = _approve(bdir, "p2")
    assert out["recorded"] == ["p2"]
    assert "scans 2, 3 of the 3" in out["statement"] and "scientist_selected_subset_of_scans" in out["statement"]


def test_two_results_of_one_group_in_one_call_are_refused(bdir):
    _decide_everything(bdir)
    _add_athena(bdir)
    M.decide(bdir, target_ids=["p1"], decision="defer", value=None, **BY)
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=["p1", "p2"], decision="approve", value=None, qc_status="valid", **BY)
    assert "p1 and p2 are both results of group g1" in str(exc.value)


def test_an_older_bundle_with_two_approvals_says_approve_exactly_one(bdir):
    _decide_everything(bdir)
    _add_athena(bdir)
    b = M.load(bdir)
    entry = copy.deepcopy(next(d for d in b["scientist_decisions"] if d["target"] == {"kind": "processing_result", "id": "p1"}))
    entry.update(decision_id=f"d-{len(b['scientist_decisions']) + 1:05d}", target={"kind": "processing_result", "id": "p2"})
    p2 = next(r for r in b["processing_results"] if r["result_id"] == "p2")
    entry["approved_files"] = [{k: f[k] for k in ("role", "relative_path", "sha256")} for f in p2["outputs"]["files"]]
    b["scientist_decisions"].append(entry)  # what an older build recorded: no refusal then
    M.save_bundle(bdir, b)
    R.build_records(bdir)
    v = R.validate_records(bdir, run_portal=_portal("publish"))
    assert v["by_reason"].get("more_than_one_approved_result") == 1 and "no_processing_result" not in v["by_reason"]
    report = json.loads((bdir / "validation" / "g1.json").read_text())
    assert report["processing_blocker"] == "more_than_one_approved_result"
    text = " ".join(report["plain_summary"])
    assert "two results approved for this group; approve exactly one: p1, p2" in text
    assert "no processing result exists" not in text and "run `isaac process`" not in text
    assert "--target p1 --decision defer" in text and "--target p2 --decision defer" in text


# --- 3. the Athena result's E0 descriptor names Athena -------------------------------------------------------


def _exported(bdir, tmp_path):
    R.build_records(bdir)
    out = tmp_path / "records"
    result = R.export_records(bdir, out, run_portal=_portal("publish"))
    assert len(result["exported"]) == 1, result
    return json.loads((out / f"{result['exported'][0]['record_id']}.json").read_text())


def test_an_exported_record_from_an_approved_athena_result_names_athena(bdir, tmp_path):
    _decide_everything(bdir)
    _add_athena(bdir)
    M.decide(bdir, target_ids=["p1"], decision="defer", value=None, **BY)
    _approve(bdir, "p2")
    [out] = _exported(bdir, tmp_path)["descriptors"]["outputs"]
    assert out["generated_by"]["agent"] == "Athena"
    assert "scientist's own Athena processing" in out["generated_by"]["notes"] and ATHENA_PRJ in out["generated_by"]["notes"]
    assert "isaac.xas" not in out["generated_by"]["agent"]
    assert "uses only scans 2, 3 of the 3 scan(s)" in out["generated_by"]["notes"]  # the subset, in the record
    [e0] = out["descriptors"]
    assert e0["value"] == 1013.5 and e0["source"] == "imported"


def test_an_exported_record_from_an_approved_isaac_result_names_the_protocol(bdir, tmp_path):
    _decide_everything(bdir)
    [out] = _exported(bdir, tmp_path)["descriptors"]["outputs"]
    assert out["generated_by"] == {"agent": "isaac.xas.synthetic", "version": "0.1"}
    assert out["descriptors"][0]["source"] == "auto"


# --- 6. the nearest group is one that can export -------------------------------------------------------------


def _groups(b, *specs):
    for gid, run in specs:
        b["record_groups"].append({"group_id": gid, "experiment_key": "exp", "member_run_keys": [run["run_key"]],
                                   "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}},
                                   "split_reasons": [], "status": "proposed", "questions": []})


def test_a_group_with_no_scans_is_never_the_nearest_while_another_exists(bdir):
    b = M.load(bdir)
    empty, full = b["runs"][0], b["runs"][1]
    empty["scan_count"], empty["scans"] = 0, []
    _groups(b, ("g0", empty), ("g1", full))  # g0 first: the old order tie-break chose it
    mfo = Q.minimum_answers_for_one_group(Q.consolidate(b), b)
    assert mfo["group_id"] == "g1" and "blocked" not in mfo


def test_when_only_a_group_with_no_scans_is_left_it_says_why(bdir):
    b = M.load(bdir)
    empty = b["runs"][0]
    empty["scan_count"], empty["scans"] = 0, []
    _groups(b, ("g0", empty))
    mfo = Q.minimum_answers_for_one_group(Q.consolidate(b), b)
    assert mfo["group_id"] == "g0"
    assert "approve its processing result" not in mfo["plus_decisions"]
    assert "none of its runs lists a scan" in mfo["blocked"] and "--target g0 --decision reject" in mfo["blocked"]


# --- 7. an AI reading of fewer runs says so -----------------------------------------------------------------


def test_an_ai_reading_of_fewer_runs_than_the_question_says_how_many(bdir):
    b = M.load(bdir)
    _groups(b, *((f"g{n}", r) for n, r in enumerate(b["runs"])))
    M.save_bundle(bdir, b)
    target = _miss(b, "context.environment", b["runs"][0]["run_id"])
    M.annotate(bdir, target_id=target, value="in_situ", excerpt_locator="line 2", source_id=None,
               model_id="synthetic", blind=False, rationale="synthetic")
    b = M.load(bdir)
    q = next(q for q in Q.consolidate(b)["questions"] if any(t["id"] == target for t in q["targets"]))
    runs = q["applies_to"]["runs"]
    assert runs > 1
    assert f"An AI reading of the files suggests 'in_situ', read for 1 of {runs} runs (not file evidence" in q["text"]
    [hint] = [h for h in q["hints"] if h["kind"] == "ai_suggestion"]
    assert hint["read_for"] == f"read for 1 of {runs} runs"


def test_an_ai_reading_of_every_run_says_no_count(bdir):
    b = M.load(bdir)
    _groups(b, *((f"g{n}", r) for n, r in enumerate(b["runs"])))
    M.save_bundle(bdir, b)
    q = next(q for q in Q.consolidate(b)["questions"] if q["target_field_path"] == "context.environment")
    for t in q["targets"]:
        M.annotate(bdir, target_id=t["id"], value="in_situ", excerpt_locator="line 2", source_id=None,
                   model_id="synthetic", blind=False, rationale="synthetic")
    q = next(x for x in Q.consolidate(M.load(bdir))["questions"] if x["question_id"] == q["question_id"])
    assert "An AI reading of the files suggests 'in_situ' (not file evidence" in q["text"] and "read for" not in q["text"]


# --- 10a. reveal says why there is no comparison ---------------------------------------------------------------


def test_reveal_with_no_parser_value_says_there_is_nothing_to_compare(bdir):
    b = M.load(bdir)
    target = _miss(b, "context.environment", b["runs"][0]["run_id"])
    M.annotate(bdir, target_id=target, value="in_situ", excerpt_locator=None, source_id=None,
               model_id="synthetic", blind=True, rationale="synthetic")
    [r] = M.reveal(bdir, target)["ai_readings"]
    assert r["agrees_with_parser"] is None and r["relation"] is None
    assert r["comparison_note"] == "the parser holds no value for this target, so there is nothing to compare"
