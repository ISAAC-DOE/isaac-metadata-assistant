"""Skill polish, cycle 1 (questions): "blocking" and the nearest group agree with the record composer,
the CLI page is compact by default, a deferred question is marked, an AI reading is never worded as file
evidence, and a conflict no record field holds is not counted as affecting a record. Synthetic only."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from tests_support_records import BY, fake_upstream_env, pristine_bundle  # noqa: F401


def _portal(outcome="publish"):
    return lambda record: {"status": "ran", "result": {"valid": True, "errors": [], "warnings": []}, "outcome": outcome,
                           "held": [], "verdict": outcome}


def _spectrum(bdir: Path, gid: str) -> dict:
    gdir = bdir / "processing" / gid
    gdir.mkdir(parents=True, exist_ok=True)
    spec = gdir / "normalized.csv"
    spec.write_text("# synthetic\nenergy_eV,norm,flat\n" + "\n".join(f"{1000 + 5 * i},{i / 20:.3f},{i / 20:.3f}" for i in range(21)) + "\n")
    return {"role": "normalized", "relative_path": f"processing/{gid}/normalized.csv", "sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}


def _group(gid: str, run_keys) -> dict:
    return {"group_id": gid, "experiment_key": "e", "member_run_keys": list(run_keys),
            "basis": {"sample": None, "technique": None, "environment": None, "conditions": {}},
            "split_reasons": [], "status": "proposed", "questions": []}


def _result(gid: str, files, verdict="pass", reasons=None) -> dict:
    return {"result_id": f"p-{gid}", "group_id": gid, "protocol_id": "isaac.xas.v0", "protocol_version": "0.1",
            "protocol_status": "draft_unreviewed", "source": "isaac_protocol", "inputs": [], "steps": [],
            "outputs": {"files": list(files), "e0_eV": 1050.0 if files else None, "edge_step": 1.0 if files else None,
                        "points": 21 if files else None},
            "qc": {"metrics": {}, "verdict": verdict, **({"reasons": reasons} if reasons else {})},
            "comparison": None, "state": "candidate_extracted"}


@pytest.fixture()
def bdir(pristine_bundle, tmp_path):
    target = tmp_path / "b"
    shutil.copytree(pristine_bundle, target)
    return target


@pytest.fixture()
def one_group(bdir):
    """g1 = run-001 with an approvable curve; every other run stays ungrouped."""
    b = M.load(bdir)
    b["record_groups"] = [_group("g1", [b["runs"][0]["run_key"]])]
    b["processing_results"] = [_result("g1", [_spectrum(bdir, "g1")])]
    M.save_bundle(bdir, b)
    return bdir


def _ids(payload) -> set[str]:
    return {q["question_id"] for q in payload["questions"]}


#: A synthetic answer per required field (never read from the files).
_SYNTHETIC = {"sample.material.name": "ZZ1 synthetic", "system.technique": "HERFD-XAS",
              "attribution.produced_by.group": "Synthetic group", "attribution.produced_by.organization": "Synthetic University"}


def _answer(bdir: Path, q: dict, only: str | None, field: str | None) -> None:
    path = field or q["target_field_path"]
    allowed = (q.get("field_allowed_values") or {}).get(path) if field else q.get("allowed_values")
    value = _SYNTHETIC.get(path) or (allowed[0] if allowed else "synthetic answer")
    M.decide_question(bdir, question_id=q["question_id"], only=only, field=field, decision="correct", value=value, **BY)


# --- 1. blocking and the nearest group agree with the record composer ---------------------------------------


def test_answering_exactly_the_minimum_makes_that_group_exportable(one_group, fake_upstream_env):
    bdir = one_group
    b = M.load(bdir)
    payload = Q.consolidate(b)
    nearest = Q.minimum_answers_for_one_group(payload, b, bundle_dir=bdir)
    assert nearest["group_id"] == "g1"
    assert nearest["unasked_required"] == []
    assert nearest["blocking_questions"] == len(nearest["questions"]) > 0
    # what the group's own blocking list says is exactly the minimum (the two agree)
    scoped = {q["question_id"] for q in Q.filter_questions(payload, scope="group:g1", blocking_only=True)}
    assert scoped == {x["question_id"] for x in nearest["questions"]}
    for x in nearest["questions"]:
        q = Q.question(payload, x["question_id"])
        _answer(bdir, q, x["only"], (x.get("fields") or [None])[0] if q["kind"] == "optional_values" else None)
    assert nearest["plus_decisions"] == ["confirm the group", "approve its processing result"]
    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=["p-g1"], decision="approve", value=None, qc_status="valid", **BY)
    verdicts = R.validate_records(bdir, run_portal=_portal())["verdicts"]
    assert verdicts == {"g1": "exportable"}, json.loads((bdir / "validation" / "g1.json").read_text())["plain_summary"]
    b = M.load(bdir)
    done = Q.minimum_answers_for_one_group(Q.consolidate(b), b, bundle_dir=bdir)
    assert done["group_id"] is None and done["groups_with_nothing_left"] == 1


def test_a_required_field_no_question_asks_is_a_blocking_item_with_its_command(one_group):
    """A group whose runs the import asked nothing about (no measurement run: the alignment group on the real
    data) still lacks what the composer requires: that is said, with the command, and such a group is never
    "the nearest" while another exists."""
    bdir = one_group
    b = M.load(bdir)
    alignment = b["runs"][1]
    alignment["run_candidate"] = False
    b["missing_values"] = [m for m in b["missing_values"] if m["run_id"] != alignment["run_id"]]
    b["record_groups"].append(_group("g-align", [alignment["run_key"]]))
    b["record_groups"][-1]["status"] = B.STATE_SCIENTIST_CONFIRMED
    b["processing_results"].append(_result("g-align", [_spectrum(bdir, "g-align")]))
    payload = Q.consolidate(b)
    got = Q.minimum_answers_for_one_group(payload, b, scope="group:g-align", bundle_dir=bdir)
    asked = {(f, x["question_id"]) for x in got["questions"] for f in x["fields"]}
    unasked = {u["path"]: u for u in got["unasked_required"]}
    composed = {m["path"] for m in R.compose_group(b, b["record_groups"][-1], bdir)[1]["missing_required"]
                if m["from"] == "a scientist's answer"}
    assert composed == {f for f, _ in asked} | set(unasked)  # every missing field is named, once
    assert "sample.sample_form" in unasked and "context.environment" in unasked
    assert "--target g-align --decision reject" in unasked["sample.sample_form"]["command"]
    assert "not a measurement run" in unasked["sample.sample_form"]["reason"]
    assert got["blocked"]
    assert Q.minimum_answers_for_one_group(payload, b, bundle_dir=bdir)["group_id"] == "g1"


def test_a_group_whose_curve_failed_is_never_the_nearest_while_another_exists(one_group):
    bdir = one_group
    b = M.load(bdir)
    b["record_groups"].append(_group("g-fail", [b["runs"][1]["run_key"]]))
    b["record_groups"][-1]["status"] = B.STATE_SCIENTIST_CONFIRMED  # one decision fewer than g1
    b["processing_results"].append(_result("g-fail", [], verdict="fail", reasons=["too_few_common_points"]))
    payload = Q.consolidate(b)
    assert Q.minimum_answers_for_one_group(payload, b, bundle_dir=bdir)["group_id"] == "g1"
    alone = Q.minimum_answers_for_one_group(payload, b, scope="group:g-fail", bundle_dir=bdir)
    assert "approve its processing result" not in alone["plus_decisions"]
    assert "too_few_common_points" in alone["blocked"]


def test_a_latest_result_with_no_output_file_is_never_offered_for_approval(one_group):
    """`decide --decision approve` refuses a result with no output file: the nearest never names that approval (even
    when an OLDER undecided result has a curve — the latest is the one decided on), names the real steps instead, and
    such a group is never the nearest while another exists."""
    bdir = one_group
    b = M.load(bdir)
    b["record_groups"].append(_group("g-none", [b["runs"][1]["run_key"]]))
    b["record_groups"][-1]["status"] = B.STATE_SCIENTIST_CONFIRMED
    older = _result("g-none", [_spectrum(bdir, "g-none")])
    older["result_id"] = "p-g-none-old"
    latest = _result("g-none", [], verdict=None)
    latest["inputs"] = [{"source_id": "s", "scan": 1, "used": False, "skip_reason": "no_usable_scan"}]
    b["processing_results"] += [older, latest]
    payload = Q.consolidate(b)
    alone = Q.minimum_answers_for_one_group(payload, b, scope="group:g-none", bundle_dir=bdir)
    assert not any("approve" in d for d in alone["plus_decisions"])
    assert "no output file" in alone["blocked"] and "no_usable_scan" in alone["blocked"]
    assert "--target p-g-none --decision reject|needs_changes" in alone["blocked"] and "--target g-none --decision reject" in alone["blocked"]
    assert Q.minimum_answers_for_one_group(payload, b, bundle_dir=bdir)["group_id"] == "g1"


def test_the_composer_is_run_on_each_groups_own_values_with_an_identical_result(pristine_bundle, tmp_path):
    """compositions() hands compose_group only a group's members' and the beamtime values (all it reads): the
    reports are byte-identical to composing from the whole bundle."""
    bdir = tmp_path / "g"
    shutil.copytree(pristine_bundle, bdir)
    M.group(bdir)
    b = M.load(bdir)
    fast = Q.compositions(b, bdir)
    whole = {g["group_id"]: R.compose_group(b, g, bdir)[1] for g in Q.live_groups(b)}
    assert json.dumps(fast, sort_keys=True, default=str) == json.dumps(whole, sort_keys=True, default=str)


def test_reaction_drive_and_catalysis_block_only_once_the_composer_requires_them(one_group):
    bdir = one_group
    b = M.load(bdir)
    # a reaction statement the files hold for run-001, NOT confirmed (in memory): the composer requires nothing more
    c = json.loads(json.dumps(next(c for c in b["candidates"] if c["run_id"] == "run-001" and c["target_field_path"])))
    c.update(candidate_id="cand-rx", target_field_path="context.electrochemistry.reaction", value="OER", value_state=B.STATE_NEEDS_REVIEW)
    b["candidates"].append(c)
    conditional = [q for q in Q.consolidate(b)["questions"] if q["target_field_path"] in B.REACTION_REQUIRED_PATHS]
    assert conditional and not any(q["blocking"] for q in conditional)
    assert all("context.reaction.name" in q["why"] for q in conditional)
    # once a reaction is confirmed for the group, the composer requires drive and catalysis: they block, under the
    # ids they already had
    before = Q.consolidate(M.load(bdir))
    b = M.load(bdir)
    rx = next(m["value_id"] for m in b["missing_values"] if m["target_field_path"] == "context.electrochemistry.reaction" and m["run_id"] == "run-001")
    M.decide(bdir, target_ids=[rx], decision="correct", value="OER", **BY)
    b = M.load(bdir)
    after = Q.consolidate(b)
    assert _ids(before) - {q["question_id"] for q in before["questions"] if q["targets"] == [{"kind": "missing_value", "id": rx}]} <= _ids(after)
    needed = {m["path"] for m in R.compose_group(b, b["record_groups"][0], bdir)[1]["missing_required"]}
    assert set(B.REACTION_REQUIRED_PATHS) <= needed
    for path in B.REACTION_REQUIRED_PATHS:
        asking = [q for q in after["questions"] if "group:g1" in q["per_scope_targets"]
                  and (q["target_field_path"] == path or path in (q.get("fields") or {}))]
        assert asking and all(q["blocking"] for q in asking), path
    nearest = Q.minimum_answers_for_one_group(after, b, bundle_dir=bdir)
    assert set(B.REACTION_REQUIRED_PATHS) <= {f for x in nearest["questions"] for f in x["fields"]}


def test_questions_only_about_runs_in_no_live_group_do_not_block_and_are_not_counted(pristine_bundle, tmp_path):
    bdir = tmp_path / "g"
    shutil.copytree(pristine_bundle, bdir)
    M.group(bdir)
    gid = M.load(bdir)["record_groups"][0]["group_id"]
    M.decide(bdir, target_ids=[gid], decision="reject", value=None, **BY)
    b = M.load(bdir)
    after = Q.consolidate(b)
    gone = [q for q in after["questions"] if q["scope"].startswith("run:")]
    assert gone and not any(q["blocking"] for q in gone)
    assert all(q["outside_live_groups"] for q in gone if q["kind"] == "missing_value")
    assert after["counts"]["blocking"] == sum(q["blocking"] for q in after["questions"])
    env = next(q for q in after["questions"] if q["target_field_path"] == "context.environment" and q["kind"] == "missing_value")
    assert env["applies_to"]["groups"] == len(Q.live_groups(b))
    assert env["applies_to"]["runs_outside_live_groups"] >= 1 and "in no live record group" in env["text"]


# --- 2. a compact page by default ------------------------------------------------------------------------------


def test_the_cli_page_is_compact_by_default_and_full_with_targets(pristine_bundle, tmp_path, capsys):
    bdir = tmp_path / "g"
    shutil.copytree(pristine_bundle, bdir)
    M.group(bdir)
    gid = M.load(bdir)["record_groups"][0]["group_id"]
    assert cli.main(["bundle", "questions", str(bdir), "--scope", f"group:{gid}"]) == 0
    compact = json.loads(capsys.readouterr().out)
    assert cli.main(["bundle", "questions", str(bdir), "--scope", f"group:{gid}", "--with-targets"]) == 0
    full = json.loads(capsys.readouterr().out)
    assert [q["question_id"] for q in compact["questions"]] == [q["question_id"] for q in full["questions"]]
    for small, big in zip(compact["questions"], full["questions"]):
        assert "targets" not in small and "per_scope_targets" not in small
        assert small["targets_count"] == len(big["targets"]) and small["scopes_count"] == len(big["per_scope_targets"])
        # the groups it reaches (c10-m): at least its group scopes, every live group for a beamtime-wide one
        assert small["groups_count"] == big["applies_to"]["groups"] >= sum(k.startswith("group:") for k in big["per_scope_targets"])
        if big["kind"] == "optional_values":
            assert small["fields"] == {f: len(ids) for f, ids in big["fields"].items()}
    # the counts are the scope's; the whole bundle's are under their own key
    assert compact["counts"]["total"] == compact["total"] and compact["counts_whole_bundle"]["total"] > compact["total"]
    assert cli.main(["bundle", "questions", str(bdir), "--scope", f"group:{gid}", "--blocking-only"]) == 0
    assert compact["counts"]["blocking"] == json.loads(capsys.readouterr().out)["total"]  # blocking for THIS group
    assert len(json.dumps(compact)) < len(json.dumps(full))


# --- 3. "I don't know" is visible ---------------------------------------------------------------------------


def test_a_deferred_question_is_marked_sorted_last_and_can_be_left_out(pristine_bundle, tmp_path, capsys):
    bdir = tmp_path / "g"
    shutil.copytree(pristine_bundle, bdir)
    M.group(bdir)
    p = Q.consolidate(M.load(bdir))
    first = next(q for q in p["questions"] if q["blocking"])
    M.decide_question(bdir, question_id=first["question_id"], decision="defer", value=None, **BY)
    p = Q.consolidate(M.load(bdir))
    q = Q.question(p, first["question_id"])
    assert q["blocking"] and q["deferred"]["by"] == BY["by"] and q["deferred"]["decided_utc"]
    assert p["counts"]["deferred"] == 1 and p["counts"]["blocking"] == sum(x["blocking"] for x in p["questions"])
    blocking = [x["question_id"] for x in p["questions"] if x["blocking"]]
    assert blocking[-1] == first["question_id"]  # still blocking, still counted: asked after the others
    assert cli.main(["bundle", "questions", str(bdir), "--blocking-only", "--skip-deferred", "--limit", "200"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert first["question_id"] not in {x["question_id"] for x in out["questions"]}
    assert out["skipped_deferred"] == 1 and out["counts"]["deferred"] == 1


# --- 4. an AI reading is never worded as file evidence --------------------------------------------------------


def test_an_ai_reading_is_never_called_a_suggestion_from_the_files(bdir):
    b = M.load(bdir)
    q = next(q for q in Q.consolidate(b)["questions"] if q["kind"] == "missing_value" and q["target_field_path"] == "sample.sample_form")
    tid = q["targets"][0]["id"]
    b.setdefault("ai_interpretations", []).append({
        "interpretation_id": "ai-1", "target": {"kind": "missing_value", "id": tid}, "proposed_value": "powder",
        "source_refs": [{"source_id": b["sources"][0]["source_id"], "locator": "line 1"}], "source_path": b["sources"][0].get("relative_path"),
        "quote": "pellet", "strength": "weak", "model": {"model_id": "synthetic-model"}})
    asked = Q.question(Q.consolidate(b), q["question_id"])
    assert "Suggested from the files" not in asked["text"]
    assert "AI reading" in asked["text"] and "not file evidence" in asked["text"]
    hint = next(h for h in asked["hints"] if h["kind"] == "ai_suggestion")
    assert "Not file evidence" in hint["note"]


# --- 5. a conflict no record field holds does not affect a record ---------------------------------------------


def test_a_conflict_with_no_record_field_is_counted_apart_and_says_so(one_group):
    b = M.load(one_group)
    p = Q.consolidate(b)
    fieldless = [q for q in p["questions"] if q["kind"] == "resolve_conflict" and q["target_field_path"] is None]
    assert fieldless
    for q in fieldless:
        assert q["tier"] != Q.TIER_CONFLICT and not q["blocking"] and q["affects_record"] is False
        assert "carries whichever reading you choose" not in q["why"] and "no record field" in q["why"]
    assert p["counts"]["conflicts_without_a_record_field"] == len(fieldless)
    assert p["counts"]["conflicts_affecting_a_record"] == sum(q["tier"] == Q.TIER_CONFLICT for q in p["questions"])
