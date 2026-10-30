"""Audit round 2 on the local import, each pinned by a defect-shaped test. Synthetic fixture only.

H1. what a question / the template / the local screen OFFERS is exactly what ``decide`` accepts and the
    export validates against (``bundle.allowed_values``: the portal's pinned list), never the website
    schema's narrower one; an older build's eligibility under the old list is re-derived and logged.
M3. a target whose extracted value its field refuses is never offered ``confirm`` (asked again, or in a
    mixed question), and the local screen's Accept never offers what ``decide`` would refuse.
Lows / messages: the QC note for a status that says something is wrong; the nearest group never names
    a decision already made, never an exportable group, and keeps to ``--scope``; the technique question
    speaks of THIS import; a recorded ZIP is called a ZIP; the processing remedy names ``--source``; the
    schema-drift note does not claim an exportable record is blocked.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

import isaac_api.workspace as ws
from isaac_api import local_bundles as LB
from isaac_api import schema_proposal_rules as SR
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import portal as P
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import import template as T

SEMANTICS = ws.REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
BY = dict(by="Synthetic Scientist", orcid=None)
TECH_Q = "Q-1e7239d292"  # system.technique, experiment scope (pinned in test_question_ids_of_the_grouped_corpus_are_pinned)
SETPOINT = "context.electrochemistry.potential_setpoint_V"
SETPOINT_Q = "Q-ed7a7df8a4"  # the setpoint of group rg-5c543646b51968e0, extracted 0.1


@pytest.fixture(scope="module")
def grouped(tmp_path_factory):
    out = tmp_path_factory.mktemp("round2") / "bundle"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def b(grouped, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(grouped, target)
    return target


def _bytes(bdir: Path) -> bytes:
    return (bdir / "bundle.json").read_bytes()


def _clear_caches():
    B._pinned_vocabulary.cache_clear()
    B._list_moved_paths.cache_clear()


@pytest.fixture()
def list_patch(monkeypatch):
    """Replace ``bundle.allowed_values`` for some paths (caches cleared before and after)."""
    real = B.allowed_values

    def apply(overrides: dict):
        monkeypatch.setattr(B, "allowed_values", lambda path: list(overrides[path]) if path in overrides else real(path))
        _clear_caches()

    yield apply
    monkeypatch.setattr(B, "allowed_values", real)
    _clear_caches()


# --- H1. offered = accepted = what the export validates against ----------------------------------------

CLOSED = ("system.technique", "context.electrochemistry.cell_type", "sample.sample_form", "sample.material.provenance",
          "context.reaction.drive", "context.reaction.catalysis", "context.environment", B.CONTROL_MODE_PATH)


def test_the_technique_question_lists_EPR_and_decide_records_it(b, capsys):
    q = Q.question(Q.consolidate(M.load(b)), TECH_Q)
    assert "EPR" in q["allowed_values"]
    code = cli.main(["bundle", "decide", str(b), "--question", TECH_Q, "--decision", "correct", "--value", "EPR",
                     "--by", "X"])
    assert code == 0, capsys.readouterr().err
    tech = [c for c in M.load(b)["candidates"] if c["target_field_path"] == "system.technique" and c["run_id"] is None]
    assert tech and all(c["eligibility_for_official_record"]["eligible"] for c in tech)


@pytest.mark.parametrize("path", CLOSED)
def test_every_offered_value_is_accepted_and_nothing_off_the_list_is(path):
    allowed = B.allowed_values(path)
    assert allowed, path
    assert T.rule_for_path(path)["allowed"] == allowed  # the template and the local screen's value_rule
    assert all(B.value_problem(path, v) is None for v in allowed)
    assert B.value_problem(path, "SYNTHETIC_not_listed") is not None


def test_the_lists_the_reviewer_named_are_the_export_targets():
    assert B.value_problem("context.electrochemistry.cell_type", "not_reported") is None
    assert "galvanostatic_cycling" in B.allowed_values("system.technique")
    # closed only by the portal's vocabulary: decide refuses what the portal would refuse
    for path, ok in (("sample.sample_form", "powder"), ("sample.material.provenance", "commercial"),
                     ("context.reaction.drive", "electrochemical"), ("context.reaction.catalysis", "heterogeneous")):
        assert B.value_problem(path, ok) is None
        assert "not one of the schema's allowed values" in B.value_problem(path, ok.upper())


def test_questions_offer_exactly_the_shared_list(grouped):
    payload = Q.consolidate(M.load(grouped))
    seen = 0
    for q in payload["questions"]:
        if q.get("target_field_path") and q["kind"] in ("missing_value", "confirm_value", "resolve_conflict"):
            assert q["allowed_values"] == B.allowed_values(q["target_field_path"]), q["question_id"]
            seen += 1
        for f, values in (q.get("field_allowed_values") or {}).items():
            assert values == B.allowed_values(f)
    assert seen


def test_the_local_screen_offers_the_shared_list(grouped):
    bundle = M.load(grouped)
    q = Q.question(Q.consolidate(bundle), TECH_Q)
    display, _ = LB.describe_question(bundle, q, folder="x")
    assert display["value_rule"]["allowed"] == B.allowed_values("system.technique")


def test_the_list_is_the_pinned_portal_contract():
    """The repository's vocabulary copy is the commit the export validates against; when the pinned validator is
    installed, its file is that copy byte for byte, and every writable path's list is its schema's enum and
    vocabulary list, intersected — exactly what its two gates accept."""
    assert SR.PORTAL_SNAPSHOT_COMMIT == P.PINNED_COMMIT
    where = P.locate()
    if not where.get("available"):
        pytest.skip("the pinned portal validator is not installed")
    installed = Path(where["dir"]) / "data" / "vocabulary.json"
    assert installed.read_bytes() == Path(SR.PORTAL_SNAPSHOT_FILE).read_bytes()
    upstream = P.upstream_schema(where)
    vocab = {k: e["values"] for sec in json.loads(installed.read_text()).values() for k, e in sec.items()
             if isinstance(e, dict) and e.get("values") and k not in B._PORTAL_UNCHECKED_CATEGORIES}
    for path in sorted(B._writable_paths()):
        node = Q._node(upstream, path)
        enum = node.get("enum") if node else None
        lists = [x for x in (enum, vocab.get(path)) if x is not None]
        expected = [v for v in lists[0] if all(v in x for x in lists[1:])] if lists else None
        assert (B.allowed_values(path) is None) == (expected is None), path
        if expected is not None:
            assert sorted(B.allowed_values(path)) == sorted(expected), path


def _older_build_decision(bundle: dict, kind: str, tid: str, value, n: int) -> None:
    bundle["scientist_decisions"].append({
        "decision_id": f"d-{n:05d}", "target": {"kind": kind, "id": tid}, "decision": "correct",
        "value": value, "chosen_reading_index": None,
        "decided_by": {"name": "Older Build", "basis": "self_reported_local_user", "identity": "local_unverified",
                       "orcid_claimed": None},
        "decided_utc": "2026-10-28T00:00:00Z", "method": "scientist_answer", "note": None, "batch_id": None})


def test_an_older_builds_eligibility_under_the_website_list_is_rederived_and_logged(b, monkeypatch, capsys):
    """An older build judged values by the vendored enum alone: EPR was stored confirmed but NOT eligible, and an
    off-vocabulary sample form confirmed AND eligible. The bundle still loads (STALE, not INVALID), and the next
    write re-derives both and logs each in eligibility_rederived."""
    bundle = M.load(b)
    tech = next(c for c in bundle["candidates"] if c["target_field_path"] == "system.technique" and c["run_id"] is None)
    form = next(m for m in bundle["missing_values"] if m["target_field_path"] == "sample.sample_form")
    vendored = {p: list((B._schema_node(p) or {}).get("enum") or []) or None for p in ("system.technique", "sample.sample_form")}
    real = B.allowed_values
    monkeypatch.setattr(B, "allowed_values", lambda p: vendored[p] if p in vendored else real(p))
    _clear_caches()
    _older_build_decision(bundle, "candidate", tech["candidate_id"], "EPR", 1)
    _older_build_decision(bundle, "missing_value", form["value_id"], "bulk_thing", 2)
    M.save_bundle(b, bundle)  # as the older build wrote it
    monkeypatch.setattr(B, "allowed_values", real)
    _clear_caches()
    stored = M.load(b)
    errors, stale = B.validate_allowing_stale(stored)
    assert not errors
    moved = {(s["id"], s["eligible_before"], s["eligible_now"]) for s in stale}
    assert moved == {(tech["candidate_id"], False, True), (form["value_id"], True, False)}
    assert cli.main(["bundle", "check", str(b)]) == cli.EXIT_INVALID  # STALE (no exit code of its own), not INVALID
    out = capsys.readouterr().out
    assert out.startswith("STALE:") and "format stays the same" in out and "upgraded from" not in out
    # any write re-derives them, under the lock, and logs each one
    env = next(m for m in stored["missing_values"] if m["target_field_path"] == "context.environment")
    M.decide(b, target_ids=[env["value_id"]], decision="correct", value="ex_situ", **BY)
    after = M.load(b)
    assert not B.validate_bundle(after)
    logged = {(r["id"], r["eligible_now"]) for r in after["eligibility_rederived"]}
    assert logged == {(tech["candidate_id"], True), (form["value_id"], False)}
    now = {o.get("candidate_id") or o.get("value_id"): o for o in after["candidates"] + after["missing_values"]}
    assert now[tech["candidate_id"]]["eligibility_for_official_record"]["eligible"] is True
    assert now[form["value_id"]]["eligibility_for_official_record"]["eligible"] is False
    assert not B.allowed_list_rederivations(after)  # logged once: the next write finds nothing to re-derive


# --- M3. confirm is never offered where decide refuses it ------------------------------------------------


def _unfit_setpoint_bundle(b: Path, list_patch) -> dict:
    """The group's setpoint (extracted 0.1) was confirmed; a list now excludes 0.1 (as an older build's
    confirm of an off-list extracted value): the answer is unfit, so the question is asked again."""
    q = Q.question(Q.consolidate(M.load(b)), SETPOINT_Q)
    M.decide(b, target_ids=[t["id"] for t in q["targets"]], decision="confirm", value=None, **BY)
    list_patch({SETPOINT: [5.0]})
    bundle = M.load(b)
    B.apply_derivations(bundle)
    return bundle


def test_an_unfit_confirmed_extracted_value_is_asked_again_with_correct_only(b, list_patch):
    bundle = _unfit_setpoint_bundle(b, list_patch)
    q = Q.question(Q.consolidate(bundle), SETPOINT_Q)
    assert q is not None and q["asked_again"] and q["reason"] == "answer_not_eligible_for_official_record"
    assert q["allowed_decisions"] == list(Q.VALUELESS_DECISIONS)
    assert "--decision correct" in q["answer_command"] and "--decision confirm" not in q["answer_command"]
    assert q["confirmable_scopes"] == [] and q["targets_with_an_unfit_value"] == 1
    # what is offered matches decide: confirm is refused, a correction on the list is accepted
    with pytest.raises(M.MutationRefused):
        M.record_decision(copy.deepcopy(bundle), target_ids=[t["id"] for t in q["targets"]], decision="confirm", value=None, **BY)
    M.record_decision(copy.deepcopy(bundle), target_ids=[t["id"] for t in q["targets"]], decision="correct", value=5.0, **BY)


def test_the_local_screen_never_offers_accept_for_an_unfit_extracted_value(b, list_patch):
    bundle = _unfit_setpoint_bundle(b, list_patch)
    q = Q.question(Q.consolidate(bundle), SETPOINT_Q)
    display, _ = LB.describe_question(bundle, q, folder="x")
    assert display["distinct_extracted_values"] == []
    assert not any(s["has_unanimous_value"] for s in display["scopes"])


def test_a_mixed_question_offers_confirm_only_where_decide_accepts_it(grouped, list_patch):
    """Two runs in one group, extracted 0.9 and 1.0; the list takes only 1.0. `decide` refuses a confirm of the
    whole question (it checks every target), so no whole-question confirm is offered — not by the command, not
    by the screen's Accept."""
    bundle = M.load(grouped)
    by_key = {r["run_id"]: r["run_key"] for r in bundle["runs"]}
    setpoint = {c["run_id"]: c for c in bundle["candidates"] if c["target_field_path"] == SETPOINT}
    a, z = next((r, s) for r in setpoint for s in setpoint if setpoint[r]["value"] == 0.9 and setpoint[s]["value"] == 1.0)
    keep = next(g for g in bundle["record_groups"] if by_key[a] in g["member_run_keys"])
    gone = next(g for g in bundle["record_groups"] if by_key[z] in g["member_run_keys"])
    keep["member_run_keys"] = keep["member_run_keys"] + gone["member_run_keys"]
    bundle["record_groups"].remove(gone)  # in memory only: one group holding both runs
    list_patch({SETPOINT: [1.0]})
    q = next(x for x in Q.consolidate(bundle)["questions"]
             if x["kind"] == "confirm_value" and x["target_field_path"] == SETPOINT and x["scope"] == f"group:{keep['group_id']}")
    assert len(q["targets"]) == 2 and q["targets_with_an_unfit_value"] == 1
    assert "confirm" in q["allowed_decisions"] and q["confirmable_scopes"] == []
    assert "--only <scope>" in q["answer_command"] and "confirmable_scopes" in q["answer_command"]
    with pytest.raises(M.MutationRefused):  # what a whole-question confirm would meet
        M.record_decision(copy.deepcopy(bundle), target_ids=[t["id"] for t in q["targets"]], decision="confirm", value=None, **BY)
    display, _ = LB.describe_question(bundle, q, folder="x")
    assert display["distinct_extracted_values"] == []
    assert not any(s["has_unanimous_value"] for s in display["scopes"])


def test_a_fit_question_still_offers_confirm(grouped):
    bundle = M.load(grouped)
    q = Q.question(Q.consolidate(bundle), SETPOINT_Q)
    assert q["confirmable_scopes"] == list(q["per_scope_targets"]) and "--decision confirm" in q["answer_command"]
    display, _ = LB.describe_question(bundle, q, folder="x")
    assert [v["value"] for v in display["distinct_extracted_values"]] == [0.1]


# --- QC note ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["compromised", "failed"])
def test_a_qc_status_that_says_something_is_wrong_needs_a_note(b, capsys, status):
    before = _bytes(b)
    code = cli.main(["bundle", "decide", str(b), "--target", "p-anything", "--decision", "approve",
                     "--qc-status", status, "--by", "X"])
    err = capsys.readouterr().err
    assert code == 2 and "--qc-note" in err and "Nothing was recorded" in err
    assert _bytes(b) == before
    with pytest.raises(M.MutationRefused, match="--qc-note"):
        M.decide(b, target_ids=["p-anything"], decision="approve", value=None, qc_status=status, qc_note="   ", **BY)


def test_a_valid_or_pending_qc_status_needs_no_note():
    assert M.qc_note_problem("valid", None) is None and M.qc_note_problem("pending", None) is None
    assert M.qc_note_problem("compromised", "edge region noisy") is None


# --- the nearest group -----------------------------------------------------------------------------------


def _approved(bundle: dict, gid: str) -> None:
    bundle.setdefault("processing_results", []).append(
        {"result_id": f"p-{gid}", "group_id": gid, "source": "isaac_protocol", "state": B.STATE_SCIENTIST_CONFIRMED,
         "applicability": {"status": "applicable"}})


def test_the_nearest_group_never_names_a_decision_already_made(grouped):
    bundle = M.load(grouped)
    gid = bundle["record_groups"][0]["group_id"]
    bundle["record_groups"][0]["status"] = B.STATE_SCIENTIST_CONFIRMED
    _approved(bundle, gid)
    got = Q.minimum_answers_for_one_group(Q.consolidate(bundle), bundle, scope=f"group:{gid}")
    assert got["group_id"] == gid and got["plus_decisions"] == []


def test_the_nearest_group_keeps_to_the_scope_asked_for(grouped):
    bundle = M.load(grouped)
    payload = Q.consolidate(bundle)
    for g in Q.live_groups(bundle):
        assert Q.minimum_answers_for_one_group(payload, bundle, scope=f"group:{g['group_id']}")["group_id"] == g["group_id"]
    assert Q.minimum_answers_for_one_group(payload, bundle, scope="group:rg-none") is None


def _answer_the_minimum(bdir, nearest) -> None:
    """Answer exactly the nearest group's questions (at their --only scope) with synthetic values, on disk."""
    payload = Q.consolidate(M.load(bdir))
    for x in nearest["questions"]:
        q = Q.question(payload, x["question_id"])
        field = x["fields"][0] if q["kind"] == "optional_values" else None
        allowed = (q.get("field_allowed_values") or {}).get(field) if field else q.get("allowed_values")
        M.decide_question(bdir, question_id=q["question_id"], only=x["only"], field=field, decision="correct",
                          value=allowed[0] if allowed else "synthetic answer", by="S", orcid=None)


def _confirmed_and_approved(bdir, gids) -> dict:
    bundle = M.load(bdir)
    for x in bundle["record_groups"]:
        if x["group_id"] in gids:
            x["status"] = B.STATE_SCIENTIST_CONFIRMED
            _approved(bundle, x["group_id"])
    return bundle


def test_the_nearest_group_is_never_one_with_nothing_left(grouped, tmp_path):
    """"Nothing left" is the record composer's word (every required field filled), never a question list's."""
    grouped = shutil.copytree(grouped, tmp_path / "b")  # answered on disk: never the shared module bundle
    first = Q.minimum_answers_for_one_group(Q.consolidate(M.load(grouped)), M.load(grouped))
    done = first["group_id"]
    _answer_the_minimum(grouped, first)
    bundle = _confirmed_and_approved(grouped, {done})
    got = Q.minimum_answers_for_one_group(Q.consolidate(bundle), bundle)
    assert got["group_id"] != done and got["groups_with_nothing_left"] == 1
    every = {g["group_id"] for g in M.load(grouped)["record_groups"]}
    for _ in range(len(every)):
        bundle = _confirmed_and_approved(grouped, every)
        nearest = Q.minimum_answers_for_one_group(Q.consolidate(bundle), bundle)
        if nearest["group_id"] is None:
            break
        assert nearest["questions"] and not nearest["unasked_required"]
        _answer_the_minimum(grouped, nearest)
    assert nearest["group_id"] is None and nearest["plus_decisions"] == [] and "export" in nearest["statement"]
    assert nearest["groups_with_nothing_left"] == len(every)


# --- wording ---------------------------------------------------------------------------------------------


def test_the_technique_question_says_how_to_answer_it_here(grouped):
    from isaac_api.bl15 import evidence as ev
    from isaac_api.bl15 import mapping as mp

    q = Q.question(Q.consolidate(M.load(grouped)), TECH_Q)
    assert "Add to Experiment" not in q["text"] and "yours to choose here" in q["text"]
    assert "Add to Experiment" in mp.CONCEPT_SUMMARIES[ev.CONCEPT_ACQUISITION_METHOD]  # the hosted text is unchanged


def test_an_older_bundles_hosted_wording_is_replaced_on_save(b):
    bundle = M.load(b)
    from isaac_api.bl15 import evidence as ev
    from isaac_api.bl15 import mapping as mp

    hosted = mp.CONCEPT_SUMMARIES[ev.CONCEPT_ACQUISITION_METHOD]
    techs = [c for c in bundle["candidates"] if c["state_basis"].get("not_proposable_summary") == B.LOCAL_TECHNIQUE_REASON]
    assert techs
    for c in techs:
        c["state_basis"]["not_proposable_summary"] = hosted  # as an older build stored it
    assert B.refresh_local_write_summaries(bundle) == len(techs)
    assert all(c["state_basis"]["not_proposable_summary"] == B.LOCAL_TECHNIQUE_REASON for c in techs)


def test_a_recorded_zip_is_called_a_zip_not_a_missing_folder(tmp_path, capsys):
    archive = Path(shutil.make_archive(str(tmp_path / "beamtime"), "zip", root_dir=SEMANTICS.parent, base_dir=SEMANTICS.name))
    out = tmp_path / "bundle"
    assert cli.main(["import", str(archive), "--out", str(out), "--record-local-root"]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    capsys.readouterr()
    assert cli.main(["process", str(out)]) == 2
    err = capsys.readouterr().err
    assert "is a ZIP file" in err and "not an existing folder" not in err and "--source" in err


def test_the_processing_remedy_names_the_source_process_needs():
    for proc in ({"result": "p1"}, {}):
        assert "isaac process <bundle_dir> --source <the beamtime folder you imported>" in R.processing_remedy(proc)
    assert "--qc-note" in R.processing_remedy({"awaiting_approval": ["p1"]})


def test_the_schema_drift_note_does_not_say_an_exportable_record_is_blocked():
    where = P.locate()
    if not where.get("available"):
        pytest.skip("the pinned portal validator is not installed")
    record = {"context": {"temperature_K": None, "temperature_basis": "not_reported"}}
    drift = R.schema_drift(record, P.upstream_schema(where))
    assert "blocked by schema drift unless" not in drift["temperature"]
    assert "does NOT block the local export" in drift["temperature"]
