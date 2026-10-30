"""`isaac bundle group --regroup` keeps a scientist's BINDING group (confirmed / merged), and no
run may then sit in that kept group AND a fresh proposal (independent review of 05e11c2e,
measured here). A deferred or rejected group does not freeze its runs (review B-1), and the
proposal is made over the whole bundle (review B-2).

Scenario, all SYNTHETIC (reuses the counter-question CLI test's folder): two single-run groups;
the scientist confirms one; then answers the counter question, which would merge the two runs;
`--regroup` must not propose a fresh group that contains the confirmed group's run.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

from test_local_import_grouping_cli import FIXTURE, _folder, _run


def _memberships(bundle: dict) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    for g in bundle["record_groups"]:
        for rk in g["member_run_keys"]:
            seen.setdefault(rk, []).append(g["group_id"])
    return seen


def test_regroup_never_puts_a_kept_groups_run_in_a_fresh_group(tmp_path, capsys):
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    first = M.load(b)["record_groups"][0]
    grouped_before = set(_memberships(M.load(b)))
    assert len(first["member_run_keys"]) == 1 and len(grouped_before) == 2
    M.decide(b, target_ids=[first["group_id"]], decision="confirm", value=None, by="SYNTHETIC TEST", orcid=None)
    assert _run(["bundle", "decide", str(b), "--target", "experiment", "--decision", "set_counter_positions", "--positions", "2", "--by", "SYNTHETIC TEST"], capsys)[0] == 0
    assert _run(["bundle", "group", str(b), "--regroup"], capsys)[0] == 0
    after = json.loads((b / "bundle.json").read_text())
    doubled = {rk: gids for rk, gids in _memberships(after).items() if len(gids) > 1}
    assert doubled == {}
    kept = next(g for g in after["record_groups"] if g["group_id"] == first["group_id"])
    assert kept["status"] == "scientist_confirmed" and kept["member_run_keys"] == first["member_run_keys"]
    # and nothing went missing: the same runs are grouped as before the regroup
    assert set(_memberships(after)) == grouped_before
    assert _run(["bundle", "check", str(b)], capsys)[0] == 0
    # B-2: the proposal is made over the WHOLE bundle; where it would have joined the other
    # run to the confirmed group, that run is proposed alone and a merge candidate says so
    [rest] = [g for g in after["record_groups"] if g["group_id"] != first["group_id"]]
    assert rest["status"] == "proposed"
    [mc] = [m for m in after["merge_candidates"] if set(m["group_ids"]) == {rest["group_id"], first["group_id"]}]
    assert mc["reasons"][0]["code"] == "matches_binding_group" and mc["status"] == "proposed"
    assert mc["merge_candidate_id"] in rest["merge_candidate_ids"]
    # R-2: the fresh group is proposed from its REAL members only — nothing about the bound run
    bound = first["member_run_keys"][0]
    assert bound not in json.dumps({k: v for k, v in rest.items() if k != "merge_candidate_ids"})
    assert "multi_run_group" not in rest["flags"] and "merged_despite_engine_reading" not in rest["flags"]
    assert not any(q.get("code") == "confirm_repeats_merge" for q in rest.get("questions") or [])
    # the counter question is still the beamtime's (computed over the full bundle)
    assert [q.get("kind") for q in after["grouping_questions"]] == [q.get("kind") for q in M.load(b)["grouping_questions"]]


def test_a_bound_runs_zero_scan_export_is_offered_to_its_group_never_attached_elsewhere(tmp_path, capsys):
    """R-2: a confirmed run's exported file must not become CONTEXT of another group (its
    values would fill the wrong record), and no group may consist of exports alone."""
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    from isaac_api.local_import import bundle as B
    from isaac_api.local_import import grouping as G
    from isaac_api.local_import.processing import cli_entry

    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    first = M.load(b)["record_groups"][0]
    M.decide(b, target_ids=[first["group_id"]], decision="confirm", value=None, by="SYNTHETIC TEST", orcid=None)
    assert _run(["bundle", "decide", str(b), "--target", "experiment", "--decision", "set_counter_positions", "--positions", "2", "--by", "SYNTHETIC TEST"], capsys)[0] == 0
    bundle = M.load(b)
    bound = next(r for r in bundle["runs"] if r["run_key"] == first["member_run_keys"][0])
    export = json.loads(json.dumps(bound))
    export.update(run_key="SYN_export_of_bound", run_id="run-999", stem=bound["stem"] + ".dat", scans=[], scan_count=0,
                  candidate_ids=[], run_candidate=False, conflict_ids=[], shares_file_name_with=[], acquisition_source_id=None)
    bundle["runs"].append(export)
    # over the FULL bundle the export joins the 3-run group as context (the old reduced path kept that)
    full = cli_entry.build_groups_payload(bundle)
    assert any("SYN_export_of_bound" in (g.get("context_run_keys") or []) for g in full["record_groups"])
    (b / "bundle.json").write_bytes(B.encode(bundle))
    M.group(b, regroup=True)
    after = M.load(b)
    live = [g for g in after["record_groups"] if g["status"] in ("proposed", "scientist_confirmed")]
    assert not any("SYN_export_of_bound" in g["member_run_keys"] for g in live)
    runs = {r["run_key"]: r for r in after["runs"]}
    assert all(any(int(runs[k]["scan_count"] or 0) > 0 for k in g["member_run_keys"]) for g in live)
    [offer] = [m for m in after["merge_candidates"] if m.get("run_keys") == ["SYN_export_of_bound"]]
    assert offer["group_ids"] == [first["group_id"]] and offer["reasons"][0]["code"] == "matches_binding_group"
    assert B.validate_bundle(after) == []


def _decided_then_regrouped(tmp_path, capsys, decision: str) -> tuple[dict, dict]:
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    first = M.load(b)["record_groups"][0]
    M.decide(b, target_ids=[first["group_id"]], decision=decision, value=None, by="SYNTHETIC TEST", orcid=None)
    assert _run(["bundle", "decide", str(b), "--target", "experiment", "--decision", "set_counter_positions", "--positions", "2", "--by", "SYNTHETIC TEST"], capsys)[0] == 0
    assert _run(["bundle", "group", str(b), "--regroup"], capsys)[0] == 0
    assert _run(["bundle", "check", str(b)], capsys)[0] == 0
    return first, json.loads((b / "bundle.json").read_text())


@pytest.mark.parametrize("decision", ["defer", "reject"])
def test_a_deferred_or_rejected_group_does_not_freeze_its_runs_out_of_future_proposals(tmp_path, capsys, decision):
    """Review B-1: only a BINDING group (confirmed / merged) keeps its runs out of a regroup."""
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    first, after = _decided_then_regrouped(tmp_path, capsys, decision)
    live = [g for g in after["record_groups"] if g["status"] in ("proposed", "scientist_confirmed", "merged")]
    # the counter answer makes the two runs repeats: ONE fresh proposal holds both
    assert [len(g["member_run_keys"]) for g in live] == [2]
    assert first["member_run_keys"][0] in live[0]["member_run_keys"]
    if decision == "reject":
        kept = next(g for g in after["record_groups"] if g["group_id"] == first["group_id"])
        assert kept["status"] == "rejected"  # kept as the record of that decision
    else:
        assert first["group_id"] not in {g["group_id"] for g in after["record_groups"]}
        # the defer decision keeps its target, which is not a record
        [sup] = after["superseded_record_groups"]
        assert sup["group_id"] == first["group_id"] and sup["member_run_keys"] == first["member_run_keys"]


def test_the_validator_refuses_a_run_in_two_live_groups(tmp_path, capsys):
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    from isaac_api.local_import import bundle as B

    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    bundle = M.load(b)
    twin = json.loads(json.dumps(bundle["record_groups"][0]))
    twin["group_id"] = "rg-twin000000000000"
    bundle["record_groups"].append(twin)
    assert any("is in more than one live record group" in e for e in B.validate_bundle(bundle))
    twin["status"] = "rejected"  # history does not hold its runs
    assert not any("more than one live record group" in e for e in B.validate_bundle(bundle))



def test_a_merge_decision_is_history_and_its_runs_stay_proposable(tmp_path, capsys):
    """R-1: a `merged` group must not hold (freeze) its runs. DEC-91 (third review): these runs' names
    differ (02 / 03), so the merge is NOT combined — the candidate stays open, naming the token and
    pointing to the counter question, which is how the runs become one group."""
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    g1, g2 = M.load(b)["record_groups"][:2]
    M.decide(b, target_ids=[g1["group_id"]], decision="merge", value=None, by="SYNTHETIC TEST", orcid=None, merge_with=[g2["group_id"]])
    rc, out = _run(["bundle", "group", str(b), "--regroup"], capsys)
    assert rc == 0
    a = M.load(b)
    assert next(g for g in a["record_groups"] if g["group_id"] == g1["group_id"])["status"] == "merged"  # kept as history
    live = [g for g in a["record_groups"] if g["status"] in ("proposed", "scientist_confirmed")]
    assert {k for g in live for k in g["member_run_keys"]} >= set(g1["member_run_keys"]) | set(g2["member_run_keys"])
    [mc] = [m for m in a["merge_candidates"] if m["reasons"][0]["code"] == "scientist_decided_merge"]
    assert "differ at token 2 (02 / 03)" in mc["reasons"][0]["detail"] and "set_counter_positions" in mc["reasons"][0]["detail"]
    assert json.loads(out)["combined_by_merge_decision"] == []
    M.decide(b, target_ids=["experiment"], decision="set_counter_positions", value=None, by="SYNTHETIC TEST", orcid=None, positions=[2])
    assert _run(["bundle", "group", str(b), "--regroup"], capsys)[0] == 0
    [one] = [g for g in M.load(b)["record_groups"] if g["status"] == "proposed"]
    assert len(one["member_run_keys"]) == 2
    M.decide(b, target_ids=[one["group_id"]], decision="confirm", value=None, by="SYNTHETIC TEST", orcid=None)
    assert _run(["bundle", "check", str(b)], capsys)[0] == 0


def test_a_merge_across_a_differing_condition_is_not_combined_and_says_why(tmp_path, capsys):
    """Negative control (DEC-91): groups that differ in a CONDITION (here the potential) are not
    combined by a merge decision; the candidate says why, and no group holds both runs."""
    from tests_support_records import SEMANTICS

    b = tmp_path / "bundle"
    assert _run(["import", str(SEMANTICS), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    g1, g2 = M.load(b)["record_groups"][:2]
    M.decide(b, target_ids=[g1["group_id"]], decision="merge", value=None, by="SYNTHETIC TEST", orcid=None, merge_with=[g2["group_id"]])
    rc, out = _run(["bundle", "group", str(b), "--regroup"], capsys)
    assert rc == 0 and json.loads(out)["combined_by_merge_decision"] == []
    a = M.load(b)
    assert not any("merged_by_scientist_decision" in (g.get("flags") or ()) for g in a["record_groups"])
    [mc] = [m for m in a["merge_candidates"] if m["reasons"][0]["code"] == "scientist_decided_merge"]
    assert "were not combined" in mc["reasons"][0]["detail"] and "different conditions" in mc["reasons"][0]["detail"]
    assert "never combined" in mc["reasons"][0]["detail"]  # said plainly (1.9.0), with keeping them apart as the step
    live = [g for g in a["record_groups"] if g["status"] in ("proposed", "scientist_confirmed")]
    assert not any(set(g1["member_run_keys"]) | set(g2["member_run_keys"]) <= set(g["member_run_keys"]) for g in live)
    assert _run(["bundle", "check", str(b)], capsys)[0] == 0


def test_confirming_a_rejected_group_whose_run_was_re_proposed_names_the_proposal(tmp_path, capsys):
    """R-4: refused by decide itself, with the proposal to act on instead."""
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    first, after = _decided_then_regrouped(tmp_path, capsys, "reject")
    b = tmp_path / "bundle"
    [fresh] = [g for g in after["record_groups"] if g["status"] == "proposed"]
    with pytest.raises(M.MutationRefused, match=f"This group's run is now in proposal {fresh['group_id']}; confirm or reject that proposal instead"):
        M.decide(b, target_ids=[first["group_id"]], decision="confirm", value=None, by="SYNTHETIC TEST", orcid=None)
    M.decide(b, target_ids=[fresh["group_id"]], decision="confirm", value=None, by="SYNTHETIC TEST", orcid=None)
    assert _run(["bundle", "check", str(b)], capsys)[0] == 0


def test_processing_results_of_a_replaced_group_are_kept_with_its_superseded_entry(tmp_path, capsys, monkeypatch):
    """R-3: a result names a group in record_groups or superseded_record_groups, and is never deleted."""
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    from isaac_api.local_import import bundle as B
    from isaac_api.local_import.processing import cli_entry

    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    gids = [g["group_id"] for g in M.load(b)["record_groups"]]

    def fake(*a, **k):
        groups = [g["group_id"] for g in (k.get("bundle") or M.load(b))["record_groups"]]
        return {"status": "processed", "summary": {}, "processing_results": [
            {"result_id": f"proc-{g}-r-syn-isaac", "group_id": g, "protocol_id": "isaac.xas.v0", "protocol_version": "0.1",
             "protocol_status": "draft_unreviewed", "source": "isaac_protocol", "inputs": [], "steps": [],
             "outputs": {"files": [], "e0_eV": None, "edge_step": None, "points": None},
             "qc": {"metrics": {}, "verdict": "warn"}, "comparison": None, "state": "needs_review"} for g in groups]}

    monkeypatch.setattr(cli_entry, "run_process", fake)
    M.process(b)
    M.decide(b, target_ids=[gids[0]], decision="defer", value=None, by="SYNTHETIC TEST", orcid=None)
    assert _run(["bundle", "decide", str(b), "--target", "experiment", "--decision", "set_counter_positions", "--positions", "2", "--by", "SYNTHETIC TEST"], capsys)[0] == 0
    assert _run(["bundle", "group", str(b), "--regroup"], capsys)[0] == 0
    after = M.load(b)
    sup = {s["group_id"]: s for s in after["superseded_record_groups"]}
    assert set(sup) == set(gids)  # one named by a decision, the other by its result
    assert sorted(r["group_id"] for r in after["processing_results"]) == sorted(gids)  # none deleted
    assert all(sup[g]["processing_result_ids"] == [f"proc-{g}-r-syn-isaac"] for g in gids)
    M.process(b)  # a re-run keeps them too
    assert {r["group_id"] for r in M.load(b)["processing_results"]} >= set(gids)
    assert _run(["bundle", "check", str(b)], capsys)[0] == 0
    orphan = json.loads(json.dumps(M.load(b)))
    orphan["superseded_record_groups"] = []
    assert any("in neither record_groups nor superseded_record_groups" in e for e in B.validate_bundle(orphan))


def test_regroup_keeps_the_beamtime_sample_number_override_computed_over_the_full_bundle(tmp_path, monkeypatch):
    """Review M17: leaving a confirmed run out of the fresh proposal must not change how the
    sample number is classified. Four SYNTHETIC runs (A/1, B/1, A/2, B/2): the number is read
    beside two names twice, so it is `unknown` for the beamtime. Without B/2 it would not be,
    and A/1 vs A/2 would hard-split with no merge candidate."""
    from test_local_import_grouping import BASE, _bundle

    specs = [
        {"stem": f"{i:02d}_{n:02d}_SYN", "conds": dict(BASE, sample_name=("lit", name), sample_or_electrode_number=("lit", f"{n:02d}"))}
        for i, (name, n) in enumerate([("A", 1), ("B", 1), ("A", 2), ("B", 2)], start=1)
    ]
    state = _bundle(specs)
    monkeypatch.setattr(M, "mutate", lambda d, change: change(state))
    monkeypatch.setattr(M, "load", lambda d: state)

    def unknown_everywhere(groups):
        entries = [e for g in groups for sec in g["basis"].values() if isinstance(sec, dict) for k, e in sec.items() if k == "sample_or_electrode_number"]
        return bool(entries) and all(e["key_class"] == "unknown" for e in entries)

    M.group(tmp_path)
    first = list(state["record_groups"])
    assert unknown_everywhere(first)
    b2 = next(r["run_key"] for r in state["runs"] if r["stem"] == "04_02_SYN")
    confirmed = next(g for g in first if g["member_run_keys"] == [b2])
    confirmed["status"] = "scientist_confirmed"
    M.group(tmp_path, regroup=True)
    fresh = [g for g in state["record_groups"] if g["status"] == "proposed"]
    assert b2 not in {k for g in fresh for k in g["member_run_keys"]}
    assert unknown_everywhere(fresh)  # still the beamtime's classification
    a1, a2 = (next(g["group_id"] for g in fresh if g["member_run_keys"][0].startswith(s)) for s in ("01_01_SYN", "03_02_SYN"))
    assert any(set(mc["group_ids"]) == {a1, a2} and any(r.get("key") == "sample_or_electrode_number" for r in mc["reasons"] if r["code"] == "unknown_key_differs")
               for mc in state["merge_candidates"])


def _refs(b: dict) -> dict:
    ids = {g["group_id"] for g in b["record_groups"]}
    runs = {r["run_key"] for r in b["runs"]}
    mcids = [mc["merge_candidate_id"] for mc in b["merge_candidates"]]
    return {
        "bad_mc": [mc["merge_candidate_id"] for mc in b["merge_candidates"] if not set(mc["group_ids"]) <= ids or not set(mc.get("run_keys") or []) <= runs],
        "duplicate_mc_ids": len(mcids) - len(set(mcids)),
        "dangling": [x for g in b["record_groups"] for x in g.get("merge_candidate_ids") or [] if x not in mcids],
    }


def test_no_group_lists_a_merge_candidate_that_no_longer_exists_and_the_validator_says_so(tmp_path, capsys):
    """N-1 / N-2 (probe h): merge_candidate_ids is a DERIVED pointer, refreshed on kept groups."""
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    from isaac_api.local_import import bundle as B

    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    g1, g2 = M.load(b)["record_groups"][:2]
    M.decide(b, target_ids=[g1["group_id"]], decision="merge", value=None, by="SYNTHETIC TEST", orcid=None, merge_with=[g2["group_id"]])
    ids_seen = []
    for _ in range(3):
        assert _run(["bundle", "group", str(b), "--regroup"], capsys)[0] == 0
        a = M.load(b)
        ids_seen.append(([g["group_id"] for g in a["record_groups"]], sorted(m["merge_candidate_id"] for m in a["merge_candidates"])))
        assert _refs(a) == {"bad_mc": [], "duplicate_mc_ids": 0, "dangling": []}
    assert ids_seen[0] == ids_seen[1] == ids_seen[2]  # stable
    rp = next(g for g in a["record_groups"] if g["status"] == "proposed")  # DEC-91: not combined (names differ)
    M.decide(b, target_ids=[rp["group_id"]], decision="confirm", value=None, by="SYNTHETIC TEST", orcid=None)
    assert _run(["bundle", "group", str(b), "--regroup"], capsys)[0] == 0
    a = M.load(b)
    assert _refs(a) == {"bad_mc": [], "duplicate_mc_ids": 0, "dangling": []}
    assert _run(["bundle", "check", str(b)], capsys)[0] == 0
    # the validator refuses each kind of stale reference
    for mutate_, needle in (
        (lambda x: x["record_groups"][0].setdefault("merge_candidate_ids", []).append("mc-0000000000000000"), "that do not exist"),
        (lambda x: x["merge_candidates"].append({"merge_candidate_id": "mc-1111111111111111", "group_ids": ["rg-gone"], "run_keys": []}), "names a group not in record_groups"),
        (lambda x: x["merge_candidates"].append({"merge_candidate_id": "mc-2222222222222222", "group_ids": [x["record_groups"][0]["group_id"]], "run_keys": ["SYN_no_such_run"]}), "names a run not in runs"),
    ):
        bad = json.loads(json.dumps(a))
        mutate_(bad)
        assert any(needle in e for e in B.validate_bundle(bad)), needle


def test_the_counter_question_says_a_confirmed_groups_runs_are_not_merged_by_the_answer(tmp_path, capsys):
    """N-3: after a confirm, answering the counter question cannot merge the confirmed run."""
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    before = [q for q in M.load(b)["grouping_questions"] if q.get("kind") == "naming_counter_positions"]
    assert before and "not merged by the answer" not in before[0]["text"]
    first = M.load(b)["record_groups"][0]
    M.decide(b, target_ids=[first["group_id"]], decision="confirm", value=None, by="SYNTHETIC TEST", orcid=None)
    assert _run(["bundle", "group", str(b), "--regroup"], capsys)[0] == 0
    [q] = [q for q in M.load(b)["grouping_questions"] if q.get("kind") == "naming_counter_positions"]
    assert q["candidates_resolved_by_position"] == before[0]["candidates_resolved_by_position"]  # the beamtime's question
    assert q["candidates_resolved_by_position_excluding_confirmed"] == {}
    assert q["text"].endswith("Runs of a confirmed group are not merged by the answer; they are offered as a merge candidate instead.")
