"""LOCAL-4: consolidated questions (questions.json v2). Synthetic only."""

from __future__ import annotations

import json
import shutil

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from tests_support_records import pristine_bundle  # noqa: F401


@pytest.fixture()
def grouped(pristine_bundle, tmp_path):
    bdir = tmp_path / "b"
    shutil.copytree(pristine_bundle, bdir)
    M.group(bdir)
    return bdir


def _by_path(payload, path, kind="missing_value"):
    return [q for q in payload["questions"] if q["target_field_path"] == path and q["kind"] == kind]


def test_a_shared_value_is_asked_once_at_experiment_scope(grouped):
    b = M.load(grouped)
    p = Q.consolidate(b)
    env = _by_path(p, "context.environment")
    assert len(env) == 1 and env[0]["scope"] == "experiment"
    assert env[0]["applies_to"]["groups"] == len(b["record_groups"]) == 9
    assert len(env[0]["targets"]) == 9 and "answer once, or per group" in env[0]["text"]
    assert env[0]["allowed_values"] == ["operando", "in_situ", "ex_situ", "in_silico"]
    producer = _by_path(p, "attribution.produced_by.group")[0]
    hint = next(h for h in producer["hints"] if h["kind"] == "folder_name")
    assert "never an answer" in hint["note"]


def test_differing_answers_keep_the_question_id_and_say_they_differ(grouped):
    """DEC-91 (replaces "a differing answered value splits the question per group"): a question's
    scope is read from what the FILES record, never from answers, so two differing answers leave the
    question for the remaining groups under the SAME id — and its text says the answers differ."""
    b = M.load(grouped)
    before = _by_path(Q.consolidate(b), "context.environment")
    env = [m for m in b["missing_values"] if m["target_field_path"] == "context.environment"]
    M.decide(grouped, target_ids=[env[0]["value_id"]], decision="correct", value="ex_situ", by="S", orcid=None)
    M.decide(grouped, target_ids=[env[1]["value_id"]], decision="correct", value="in_situ", by="S", orcid=None)
    p = Q.consolidate(M.load(grouped))
    asked = _by_path(p, "context.environment")
    assert [q["question_id"] for q in asked] == [before[0]["question_id"]] and asked[0]["scope"] == "experiment"
    assert {t["id"] for t in asked[0]["targets"]} == {t["id"] for t in before[0]["targets"]} - {env[0]["value_id"], env[1]["value_id"]}
    assert "Answers already given for this field elsewhere differ (2 distinct value(s) answered" in asked[0]["text"]
    assert asked[0]["answers_differ"] is True and "answers given so far DIFFER" in asked[0]["answer_command"]
    assert before[0]["answers_differ"] is False and "Answers already given" not in before[0]["text"]


def test_differing_file_readings_with_no_answer_say_nothing_about_answers(grouped):
    """L1: the note needs at least one answer; differing FILE readings alone never produce it."""
    import copy

    b = M.load(grouped)
    q = _by_path(Q.consolidate(b), "context.environment")[0]
    for value in ("ex_situ", "in_situ"):  # two differing recorded readings, in memory only
        c = copy.deepcopy(b["candidates"][0])
        c.update(candidate_id=f"cand-x{value}", target_field_path="context.environment", value=value, value_state="unmapped")
        b["candidates"].append(c)
    for x in Q.consolidate(b)["questions"]:
        assert "Answers already given" not in x["text"] and x.get("answers_differ") in (False, None), x["question_id"]
    assert q["question_id"]


def test_questions_are_deduplicated_ordered_and_fewer_than_v1(grouped):
    b = M.load(grouped)
    p = Q.consolidate(b)
    keys = [(q["scope"], q["kind"], q["target_field_path"], q.get("partition")) for q in p["questions"] if q["kind"] != "resolve_conflict"]
    assert len(keys) == len(set(keys))
    ids = [q["question_id"] for q in p["questions"]]
    assert len(ids) == len(set(ids))
    assert [q["tier"] for q in p["questions"]] == sorted(q["tier"] for q in p["questions"])
    assert p["counts"]["total"] < p["counts"]["fine_grained_v1"] + len(b["conflicts"])
    # every question with an answer has a command; an informational one (no answer can reach the
    # record: an array path, or no write route) says so instead of offering one
    assert all(q["answer_command"].startswith("isaac bundle decide <bundle_dir> --question ")
               for q in p["questions"] if not q.get("informational"))
    assert all(q["answer_command"].startswith("# nothing to answer") and q["allowed_decisions"] == []
               for q in p["questions"] if q.get("informational"))
    assert all(q["why"] for q in p["questions"])


def test_answering_once_records_one_decision_per_target_and_a_group_can_override(grouped, capsys):
    p = Q.consolidate(M.load(grouped))
    q = _by_path(p, "context.environment")[0]
    code = cli.main(["bundle", "decide", str(grouped), "--question", q["question_id"], "--decision", "correct",
                     "--value", "ex_situ", "--by", "S"])
    assert code == 0
    decisions = M.load(grouped)["scientist_decisions"]
    assert sorted(d["target"]["id"] for d in decisions) == sorted(t["id"] for t in q["targets"])
    assert len({d["batch_id"] for d in decisions}) == 1
    scope = next(iter(q["per_scope_targets"]))
    code = cli.main(["bundle", "decide", str(grouped), "--target", q["per_scope_targets"][scope][0], "--decision", "correct",
                     "--value", "in_situ", "--by", "S"])
    assert code == 0
    assert M.load(grouped)["scientist_decisions"][-1]["value"] == "in_situ"  # the later, per-group answer wins


def test_optional_values_are_one_question_per_scope_answered_per_field(grouped, capsys):
    p = Q.consolidate(M.load(grouped))
    optional = [q for q in p["questions"] if q["kind"] == "optional_values"]
    assert optional and all(not q["blocking"] for q in optional)
    q = next(q for q in optional if "system.facility.beamline" in q["fields"])
    assert Q.targets_for(p, q["question_id"]) == []  # a field must be named
    ids = Q.targets_for(p, q["question_id"], field="system.facility.beamline")
    assert ids == q["fields"]["system.facility.beamline"]


def test_the_questions_command_pages_and_filters(grouped, capsys):
    code = cli.main(["bundle", "questions", str(grouped), "--blocking-only", "--limit", "3"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["returned"] <= 3 and all(q["blocking"] for q in out["questions"])
    assert out["minimum_for_one_group"]["plus_decisions"]
    gid = M.load(grouped)["record_groups"][0]["group_id"]
    code = cli.main(["bundle", "questions", str(grouped), "--scope", f"group:{gid}"])
    out = json.loads(capsys.readouterr().out)
    assert all(q["scope"] in ("experiment", f"group:{gid}") for q in out["questions"])


# --- real-format self-test findings D3-D5, reproduced synthetically ------------------------------


def test_d3_a_record_field_stated_for_only_some_runs_is_still_askable_for_the_others():
    import dataclasses

    import isaac_api.historical_import as hist
    from isaac_api.local_import import bundle as B

    ev: dict = {}
    reading, candidates = hist.read_local_archive(hist.archive_root_for("bl15_synthetic_semantics_corpus"), source_id="S", evidence_sink=ev)
    tech = next(c for c in candidates if c.candidate_id in reading.shared_candidate_ids and c.target_field_path == "system.technique")
    # move the beamtime reading onto run 1 only: the other eight runs state no technique
    rest = [c for c in candidates if c is not tech]
    n0 = len(reading.units[0].candidate_ids)
    moved = rest[:n0] + [tech] + rest[n0:]
    units = list(reading.units)
    units[0] = dataclasses.replace(units[0], candidate_ids=tuple(units[0].candidate_ids) + (tech.candidate_id,))
    reading = dataclasses.replace(reading, units=tuple(units),
                                  shared_candidate_ids=tuple(i for i in reading.shared_candidate_ids if i != tech.candidate_id))
    bundle = B.build_bundle(reading, moved, evidence_by_source=ev, source_kind="folder", created_utc="2026-10-28T00:00:00Z")
    assert any(m["target_field_path"] == "system.technique" and m["run_id"] is None for m in bundle["missing_values"])
    assert B.validate_bundle(bundle) == []


def test_d4_allowed_values_come_from_the_pinned_vocabulary_when_the_schema_has_no_enum(grouped, tmp_path, monkeypatch):
    """D4, since audit round 2: the PINNED vocabulary is the repository's verbatim copy at the pinned commit
    (bundle.allowed_values) — the list decide checks — never whatever an installed checkout's file says, so
    an installed validator cannot make a question offer a list decide would refuse."""
    from isaac_api.local_import import portal as P
    import sys as _sys

    up = tmp_path / "up"
    (up / "portal").mkdir(parents=True)
    (up / "portal" / "validation.py").write_text("")
    (up / "schema").mkdir()
    (up / ".git").mkdir()
    (up / ".git" / "HEAD").write_text("a1cb1c8" + "0" * 33 + "\n")
    (up / "schema" / "isaac_record_v1.json").write_text((Q.B._vendored_schema and json.dumps(Q.B._vendored_schema())))
    (up / "data").mkdir()
    (up / "data" / "vocabulary.json").write_text(json.dumps({"Sample": {"sample.sample_form": {"values": ["powder", "pellet", "film"]}}}))
    monkeypatch.setenv(P.DIR_ENV, str(up))
    monkeypatch.setenv(P.PYTHON_ENV, _sys.executable)
    p = Q.consolidate(M.load(grouped))
    form = [q for q in p["questions"] if q["target_field_path"] == "sample.sample_form"]
    B = Q.B
    pinned = B.allowed_values("sample.sample_form")
    assert pinned and "powder" in pinned and pinned != ["powder", "pellet", "film"]
    assert form and all(q["allowed_values"] == pinned for q in form)
    assert all(B.value_problem("sample.sample_form", v) is None for v in pinned)


def test_d5_a_group_list_holds_only_experiment_questions_that_reach_that_group():
    payload = {"questions": [
        {"question_id": "Q-a", "scope": "experiment", "blocking": True, "per_scope_targets": {"group:g1": ["m1"]}},
        {"question_id": "Q-b", "scope": "experiment", "blocking": True, "per_scope_targets": {"group:g2": ["m2"]}},
        {"question_id": "Q-c", "scope": "experiment", "blocking": True, "per_scope_targets": {"experiment": ["m3"]}},
        {"question_id": "Q-d", "scope": "group:g1", "blocking": True, "per_scope_targets": {"group:g1": ["m4"]}},
    ]}
    assert [q["question_id"] for q in Q.filter_questions(payload, scope="group:g1")] == ["Q-a", "Q-c", "Q-d"]


def test_d6_a_disagreement_about_a_required_field_is_a_blocking_question(grouped):
    b = M.load(grouped)
    cf = next(c for c in b["conflicts"] if c["candidate_id"])
    cand = next(c for c in b["candidates"] if c["candidate_id"] == cf["candidate_id"])
    p = Q.consolidate(b)
    q = next(q for q in p["questions"] if q["targets"] == [{"kind": "conflict", "id": cf["conflict_id"]}])
    required = Q.B._required_for(cand["target_field_path"] or "", list(Q.B.required_record_paths()) + list(Q.B.PORTAL_REQUIRED_PATHS))
    assert q["blocking"] is bool(required)
    # and one about acquisition time (not required) is never blocking
    timing = [q for q in p["questions"] if q["kind"] == "resolve_conflict" and q["target_field_path"] == "timestamps.acquired_start_utc"]
    assert timing and not any(q["blocking"] for q in timing)


def test_d6_a_conflict_on_a_required_path_blocks(grouped):
    b = M.load(grouped)
    cf = next(c for c in b["conflicts"] if c["candidate_id"] and c["kind"] == "field_disagreement")
    cand = next(c for c in b["candidates"] if c["candidate_id"] == cf["candidate_id"])
    cand["target_field_path"] = "system.technique"  # the BL15-2 2021 shape: a disputed technique
    q = next(q for q in Q.consolidate(b)["questions"] if q["targets"] == [{"kind": "conflict", "id": cf["conflict_id"]}])
    assert q["blocking"] and q["tier"] == Q.TIER_BLOCKING and q["allowed_values"]
