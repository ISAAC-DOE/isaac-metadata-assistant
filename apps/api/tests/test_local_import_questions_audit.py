"""Audit fixes to the consolidated questions (questions.json v2). SYNTHETIC fixtures only.

* A ``confirm_value`` question whose candidates carry NO value asks for the value ("What is X?"),
  cites the text the files hold, and never offers ``confirm`` (``decide`` refuses it there).
* A question about a path no answer can reach the record from (an array path, or a path this build
  has no write route for) is informational: kept under its id, answerable by nothing.
* A scientist's answer the record cannot take (not ``eligible_for_official_record``) is asked again,
  under the question's own id, with the reason and the allowed values.
* The absorber question's command is a template; the files' pair is a hint, never pre-filled.
* Consolidation is linear in the number of runs.
* The nearest group to export, and the progress page's processing blockers, are live groups only.
* A per-group question resting on the same file statement as its siblings names them, and does
  not block when a beamtime value (asked once at experiment scope) fills the field.

QUESTION IDS NEVER MOVE: a scientist's workbook is keyed on them (DEC-91). The pin below is the id
set of the committed multi-operator corpus, grouped, as it was before these fixes.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import time

import pytest

from isaac_api import local_bundles as LB
from isaac_api.local_import import bundle as B
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from tests_support_records import fake_upstream_env, pristine_bundle  # noqa: F401

BY = dict(by="Synthetic Scientist", orcid=None)
TECHNIQUE = "Q-1e7239d292"  # experiment: the beamtime macro's technique statement (no value)
TECHNIQUE_GROUP = "Q-fcaac501d9"  # one group's technique, from the same run01.mac line as 5 others
SAMPLE_NAME = "Q-06a397dcc5"  # group rg-5c54…: the filename token ZZ1 (no value)
ASSET_URI = "Q-b61cecdc7c"  # assets[].uri: an array path, never composed from an answer
SETPOINT = "Q-ed7a7df8a4"  # a valued candidate (0.1 V from "100mV")
ENVIRONMENT = "Q-f12b05fb72"  # missing context.environment, asked once for 9 groups
ABSORBER = "Q-be8c05cb9f"  # the files state Zz L3 (a beamtime-wide statement)


@pytest.fixture()
def grouped(pristine_bundle, tmp_path, fake_upstream_env):  # noqa: F811
    bdir = tmp_path / "b"
    shutil.copytree(pristine_bundle, bdir)
    M.group(bdir)
    return bdir


def _q(payload, qid):
    q = Q.question(payload, qid)
    assert q is not None, f"{qid} is not asked"
    return q


def _store_unfit_answer(bdir, target_ids, good, bad):
    """An OLDER bundle that holds an answer the record cannot take (a build that did not refuse it):
    record ``good`` through the public API, then rewrite it on disk to ``bad`` and re-derive."""
    M.decide(bdir, target_ids=target_ids, decision="correct", value=good, **BY)
    raw = json.loads((bdir / "bundle.json").read_text())
    for d in raw["scientist_decisions"]:
        if (d.get("target") or {}).get("id") in target_ids and d.get("value") == good:
            d["value"] = bad
    B.apply_derivations(raw)
    (bdir / "bundle.json").write_text(json.dumps(raw, indent=2))
    return M.load(bdir)


# --- ids never move ---------------------------------------------------------------------------


def test_question_ids_of_the_grouped_corpus_are_pinned(grouped):
    p = Q.consolidate(M.load(grouped))
    ids = sorted(q["question_id"] for q in p["questions"])
    assert len(ids) == 114
    assert hashlib.sha1("\n".join(ids).encode()).hexdigest() == "b23cc1074f8eff80bbb9c2b886300d9ebe993405"
    expected = {
        TECHNIQUE: ("confirm_value", "experiment", "system.technique"),
        TECHNIQUE_GROUP: ("confirm_value", "group:rg-218e228c04c04c4f", "system.technique"),
        SAMPLE_NAME: ("confirm_value", "group:rg-5c543646b51968e0", "sample.material.name"),
        ASSET_URI: ("confirm_value", "group:rg-5c543646b51968e0", "assets[].uri"),
        SETPOINT: ("confirm_value", "group:rg-5c543646b51968e0", "context.electrochemistry.potential_setpoint_V"),
        ENVIRONMENT: ("missing_value", "experiment", "context.environment"),
        ABSORBER: ("confirm_absorber", "experiment", None),
    }
    for qid, (kind, scope, path) in expected.items():
        q = _q(p, qid)
        assert (q["kind"], q["scope"], q["target_field_path"]) == (kind, scope, path)


# --- 1. a question about a value the files do not carry ----------------------------------------


def test_a_valueless_candidate_is_asked_for_its_value_and_never_offered_confirm(grouped):
    b = M.load(grouped)
    p = Q.consolidate(b)
    cand = {c["candidate_id"]: c for c in b["candidates"]}
    valueless = [q for q in p["questions"] if q["kind"] == "confirm_value"
                 and all(cand[t["id"]]["value"] is None for t in q["targets"])]
    assert len(valueless) >= 60
    for q in valueless:
        assert "confirm" not in q["allowed_decisions"] and "--decision confirm" not in q["answer_command"], q["question_id"]
        assert q["targets_without_a_value"] == len(q["targets"])
    tech = _q(p, TECHNIQUE)
    assert tech["blocking"] and tech["text"].startswith("What is the technique (system.technique)?")
    assert "Is the extracted" not in tech["text"]
    assert tech["allowed_decisions"] == ["correct", "reject", "defer"]
    # a TEMPLATE: a placeholder, never a value the agent could run on a vague "yes"
    assert "--decision correct --value <value> " in tech["answer_command"]
    assert not any(v in tech["answer_command"] for v in tech["allowed_values"])
    own = tech["hints"][0]  # the text the files hold for THIS question, cited
    assert (own["kind"], own["literal"], own["relative_path"], own["locator"]) == ("file_literal", "ZzL3_xas", "Zz_XAS.mac", "line 3 `def`")
    sample = _q(p, SAMPLE_NAME)
    assert sample["text"].startswith("What is the name (sample.material.name)?") and sample["hints"][0]["literal"] == "ZZ1"

    with pytest.raises(M.MutationRefused, match="does not answer"):
        M.decide_question(grouped, question_id=TECHNIQUE, decision="confirm", value=None, **BY)
    M.decide_question(grouped, question_id=TECHNIQUE, decision="correct", value="XAS", **BY)
    assert Q.question(Q.consolidate(M.load(grouped)), TECHNIQUE) is None


def test_a_valued_candidate_is_still_confirmed(grouped):
    q = _q(Q.consolidate(M.load(grouped)), SETPOINT)
    assert "confirm" in q["allowed_decisions"] and "--decision confirm" in q["answer_command"]
    assert q["text"].startswith("Is the extracted potential setpoint V") and q["targets_without_a_value"] == 0


def test_a_question_no_answer_can_reach_the_record_is_informational(grouped):
    p = Q.consolidate(M.load(grouped))
    info = [q for q in p["questions"] if q.get("informational")]
    assert {q["target_field_path"] for q in info} == {
        "assets[].uri", "measurement.series[].channels[].name",
        "measurement.series[].independent_variables[].values", "sample.sample_id"}
    assert len(info) == p["counts"]["informational"] == 37
    for q in info:
        assert q["blocking"] is False and q["lands_in_record"] is False and q["allowed_decisions"] == []
        assert q["answer_command"].startswith("# nothing to answer")
    flags = [bool(q.get("informational")) for q in p["questions"]]
    assert flags == sorted(flags)  # after every question that has an answer
    with pytest.raises(M.MutationRefused, match="does not answer"):
        M.decide_question(grouped, question_id=ASSET_URI, decision="correct", value="x", **BY)
    writable = B._writable_paths()
    for q in p["questions"]:  # every value question still offering an answer can land
        if q["kind"] in ("confirm_value", "missing_value") and q["allowed_decisions"]:
            assert "[]" not in q["target_field_path"] and q["target_field_path"] in writable, q["question_id"]


# --- 2. an answer the record cannot take is asked again ---------------------------------------


def test_an_answer_the_schema_refuses_is_asked_again_under_the_same_id(grouped):
    before = _q(Q.consolidate(M.load(grouped)), ENVIRONMENT)
    ids = [t["id"] for t in before["targets"]]
    b = _store_unfit_answer(grouped, ids, "ex_situ", "ex situ")
    assert all(m["value_state"] == B.STATE_SCIENTIST_CONFIRMED and not m["eligibility_for_official_record"]["eligible"]
               for m in b["missing_values"] if m["value_id"] in ids)
    q = _q(Q.consolidate(b), ENVIRONMENT)
    assert [t["id"] for t in q["targets"]] == ids and q["blocking"]
    assert q["reason"] == "answer_not_eligible_for_official_record" and len(q["asked_again"]) == 9
    assert {a["answered"] for a in q["asked_again"]} == {"ex situ"}
    assert "not one of the schema's allowed values" in q["asked_again"][0]["reason"]
    assert "ASKED AGAIN" in q["text"] and "operando, in_situ, ex_situ, in_silico" in q["text"]
    M.decide_question(grouped, question_id=ENVIRONMENT, decision="correct", value="ex_situ", **BY)
    assert Q.question(Q.consolidate(M.load(grouped)), ENVIRONMENT) is None


def test_a_confirmed_candidate_the_schema_refuses_is_asked_again_under_the_same_id(grouped):
    q = _q(Q.consolidate(M.load(grouped)), SETPOINT)
    [cid] = [t["id"] for t in q["targets"]]
    b = _store_unfit_answer(grouped, [cid], 0.1, "0.1 V")
    again = _q(Q.consolidate(b), SETPOINT)
    assert [t["id"] for t in again["targets"]] == [cid]
    assert again["asked_again"][0]["answered"] == "0.1 V" and "ASKED AGAIN" in again["text"]


def test_a_settled_conflict_the_record_cannot_take_is_asked_again_under_the_conflict_id(grouped):
    p = Q.consolidate(M.load(grouped))
    q = next(x for x in p["questions"] if x["kind"] == "resolve_conflict" and x["target_field_path"] == "timestamps.acquired_start_utc")
    [conflict] = [t["id"] for t in q["targets"]]
    b = _store_unfit_answer(grouped, [conflict], "2099-07-27T14:11:47Z", "2099-07-27 14:11:47")  # no zone
    after = Q.consolidate(b)
    again = _q(after, q["question_id"])
    assert again["asked_again"][0]["answered"] == "2099-07-27 14:11:47" and "UTC instant" in again["asked_again"][0]["reason"]
    assert {x["question_id"] for x in after["questions"]} == {x["question_id"] for x in p["questions"]}  # no new id


# --- 3. the absorber command is a template ----------------------------------------------------


def test_the_absorber_command_is_a_template_and_the_files_pair_is_a_hint(grouped):
    q = _q(Q.consolidate(M.load(grouped)), ABSORBER)
    assert "--element <El> --edge <K|L1-L3|M1-M5>" in q["answer_command"]
    assert "--element Zz" not in q["answer_command"] and "--edge L3" not in q["answer_command"]
    [hint] = [h for h in q["hints"] if h["kind"] == "suggested_absorber"]
    assert (hint["element"], hint["edge"], hint["basis"]) == ("Zz", "L3", "stated in the files") and "never the answer" in hint["note"]


# --- 4. linear consolidation ------------------------------------------------------------------


def _scaled(b: dict, copies: int) -> dict:
    out = copy.deepcopy(b)
    for k in range(1, copies):
        sfx = f"-x{k}"
        for r in b["runs"]:
            out["runs"].append({**copy.deepcopy(r), "run_id": r["run_id"] + sfx, "run_key": r["run_key"] + sfx})
        for c in b["candidates"]:
            out["candidates"].append({**copy.deepcopy(c), "candidate_id": c["candidate_id"] + sfx,
                                      "run_id": c["run_id"] and c["run_id"] + sfx})
        for m in b["missing_values"]:
            if m["run_id"] is not None:
                out["missing_values"].append({**copy.deepcopy(m), "value_id": m["value_id"] + sfx, "run_id": m["run_id"] + sfx})
        for g in b["record_groups"]:
            out["record_groups"].append({**copy.deepcopy(g), "group_id": g["group_id"] + sfx,
                                         "member_run_keys": [x + sfx for x in g["member_run_keys"]]})
    return out


def test_consolidation_of_thousands_of_runs_is_linear(grouped):
    """Measured before the fix (this corpus scaled up): 2,000 runs 7.9-10.7 s, 5,000 runs 276 s (a
    target-list membership test per target). After: 2,000 runs ~3 s, 5,000 runs ~9 s on a loaded
    machine. The bound is generous; the quadratic version needs ~45 s at 4,000 runs."""
    b = M.load(grouped)
    big = _scaled(b, 4000 // len(b["runs"]))
    assert len(big["runs"]) >= 3990
    start = time.perf_counter()
    p = Q.consolidate(big)
    elapsed = time.perf_counter() - start
    assert elapsed < 25, f"consolidate took {elapsed:.1f}s for {len(big['runs'])} runs"
    for q in p["questions"]:  # each target once, in first-seen order
        keys = [(t["kind"], t["id"]) for t in q["targets"]]
        assert len(keys) == len(set(keys)), q["question_id"]
        assert len(q.get("same_statement_as") or ()) <= 10 and len(q.get("same_reading_as") or ()) <= 10


# --- 5. live groups only ----------------------------------------------------------------------


def test_the_nearest_group_is_never_a_rejected_one(grouped):
    b = M.load(grouped)
    rejected = b["record_groups"][0]["group_id"]
    M.decide(grouped, target_ids=[rejected], decision="reject", value=None, **BY)
    b = M.load(grouped)
    nearest = Q.minimum_answers_for_one_group(Q.consolidate(b), b)
    assert nearest["group_id"] != rejected
    assert nearest["group_id"] in {g["group_id"] for g in Q.live_groups(b)}


def test_progress_counts_only_live_curves_awaiting_a_decision(grouped):
    M.decide(grouped, target_ids=[M.load(grouped)["record_groups"][0]["group_id"]], decision="reject", value=None, **BY)
    b = M.load(grouped)
    dead = b["record_groups"][0]["group_id"]
    g1, g2 = (g["group_id"] for g in b["record_groups"][1:3])  # live: only the first was rejected
    ok, na = {"status": "applicable"}, {"status": B.NOT_APPLICABLE, "reason_code": B.NA_NO_SCANS}
    b["processing_results"] = [
        {"result_id": "p-open", "group_id": g1, "source": "isaac_protocol", "state": B.STATE_NEEDS_REVIEW, "applicability": ok},
        {"result_id": "p-rejected", "group_id": g1, "source": "isaac_protocol", "state": B.STATE_REJECTED, "applicability": ok},
        {"result_id": "p-na", "group_id": g2, "source": "isaac_protocol", "state": B.STATE_NEEDS_REVIEW, "applicability": na},
        {"result_id": "p-dead", "group_id": dead, "source": "isaac_protocol", "state": B.STATE_NEEDS_REVIEW, "applicability": ok},
        {"result_id": "p-dead-na", "group_id": dead, "source": "isaac_protocol", "state": B.STATE_NEEDS_REVIEW, "applicability": na},
    ]
    blocks = LB.progress(grouped, b, {"status": "OK"})["blocks_export"]
    # counted BY GROUP (questions._curve): g1's open curve; g2's not-applicable result says no_scans, so it is
    # counted as a group with no scan, never as one without a protocol (as `bundle list groups` says it)
    assert "1 record group(s) have a processing result awaiting a decision and no approved curve." in blocks, blocks
    assert ("1 group(s) list no scan (no_scans), so there is nothing to process and they cannot become complete "
            "records as they stand.") in blocks, blocks
    assert not [s for s in blocks if "no applicable processing protocol" in s], blocks


# --- 6. one file statement asked per group ----------------------------------------------------


def test_a_per_group_question_on_a_beamtime_filled_field_names_its_siblings_and_does_not_block(grouped):
    p = Q.consolidate(M.load(grouped))
    per_group = [q for q in p["questions"] if q["target_field_path"] == "system.technique" and q["scope"].startswith("group:")]
    assert len(per_group) == 6 and TECHNIQUE_GROUP in {q["question_id"] for q in per_group}
    for q in per_group:
        assert q["blocking"] is False and q["covered_by"] == TECHNIQUE, q["question_id"]
        assert len(q["same_statement_as"]) == 5 and "run01.mac" in q["text"]
    assert _q(p, TECHNIQUE)["blocking"] is True
    sample = _q(p, SAMPLE_NAME)  # a run-level field with no beamtime value: still blocking, per group
    assert sample["blocking"] is True and len(sample["same_reading_as"]) == 2

    # the beamtime value REJECTED fills nothing: the per-group questions block again
    tech = next(c for c in M.load(grouped)["candidates"] if c["target_field_path"] == "system.technique" and c["run_id"] is None)
    M.decide(grouped, target_ids=[tech["candidate_id"]], decision="reject", value=None, **BY)
    again = _q(Q.consolidate(M.load(grouped)), TECHNIQUE_GROUP)
    assert again["blocking"] is True and "covered_by" not in again
