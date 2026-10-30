"""Skill polish, cycle 3 (questions that could not be answered, and records that said less than they seemed to).
SYNTHETIC fixtures only.

* A conflict none of whose readings the field takes (local clock times with no zone for a ``*_utc`` field, or
  readings off a closed list) says so, shows the UTC readings the bundle already holds for the same run, and its
  ``answer_command`` is ``correct --value <…>``: an answer ``decide`` accepts. Its id is unchanged.
* A beamtime-wide conflict that reaches every record counts the groups it reaches (``applies_to.groups`` agrees
  with ``blocks_groups``).
* ``decide --question`` resolves an ANSWERED question too (a later decision replaces an earlier one; a repeat is
  harmless; the same checks), and ``bundle show question`` shows it with its current answer.
* A member the schema requires of an object the record carries (an electrolyte name makes ``concentration_M``
  required) is listed by the record composer, so ``build-records``, the questions and ``minimum_for_one_group``
  say it before ``validate`` does; ``validate``'s compact reply carries each group's first official error.
* A group whose file names state a potential that the record will not carry is WARNED about, with the command
  that lets it in; ``minimum_for_one_group`` recommends the scale question (not blocking).
* ``reveal`` compares an AI reading given as text with a numeric parser value numerically, and says so.
* Every question id of the synthetic grouped bundle is unchanged by all of this.
"""

from __future__ import annotations

import copy
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

from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, SEMANTICS, _cand, _decide_everything, _portal, bdir, fake_upstream, pristine,
)

SETPOINT = "context.electrochemistry.potential_setpoint_V"
SCALE = "context.electrochemistry.potential_scale"
CONC = "context.electrochemistry.electrolyte.concentration_M"
NAME = "context.electrochemistry.electrolyte.name"
#: The synthetic grouped bundle's question ids, taken with the build BEFORE this cycle (sha256 of the sorted ids).
GOLDEN_IDS = (114, "3bf65cb80750510688304b08df0911fcc0bb57debff05686dbaf46b01e50321e")


def _run(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


@pytest.fixture(scope="module")
def grouped_pristine(tmp_path_factory):
    out = tmp_path_factory.mktemp("c3q") / "grouped"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def grouped(grouped_pristine, tmp_path):
    target = tmp_path / "grouped"
    shutil.copytree(grouped_pristine, target)
    return target


def _group_of_run(b, run_id):
    key = next(r["run_key"] for r in b["runs"] if r["run_id"] == run_id)
    return next(g["group_id"] for g in b["record_groups"] if key in g["member_run_keys"])


def _miss(b, path, run_id):
    return next(m["value_id"] for m in b["missing_values"] if m["target_field_path"] == path and m["run_id"] == run_id)


def _q(payload, qid):
    return next(q for q in payload["questions"] if q["question_id"] == qid)


def _conflict_q(payload, conflict_id):
    return next(q for q in payload["questions"] if q["targets"] == [{"kind": "conflict", "id": conflict_id}])


# --- 0. ids ---------------------------------------------------------------------------------------------------


def test_every_question_id_of_the_synthetic_grouped_bundle_is_unchanged(grouped):
    ids = sorted(q["question_id"] for q in Q.consolidate(M.load(grouped))["questions"])
    assert (len(ids), hashlib.sha256("\n".join(ids).encode()).hexdigest()) == GOLDEN_IDS


# --- 1. a start-time conflict of local clock times is answerable ------------------------------------------------


def _start_conflict(b):
    cands = {c["candidate_id"]: c for c in b["candidates"]}
    return next(cf for cf in b["conflicts"]
                if (cands.get(cf["candidate_id"]) or {}).get("target_field_path") == "timestamps.acquired_start_utc")


def test_a_start_time_conflict_of_zoneless_times_shows_the_utc_reading_the_bundle_holds(grouped):
    b = M.load(grouped)
    cf = _start_conflict(b)
    [rid] = cf["run_ids"]
    epoch = next(c for c in b["candidates"] if c["run_id"] == rid and c["target_field_path"] == "timestamps.acquired_start_utc"
                 and c["candidate_id"] != cf["candidate_id"] and c["value"])
    q = _conflict_q(Q.consolidate(b), cf["conflict_id"])
    assert q["question_id"] == "Q-fec1234155"  # the id the scientist's workbook may name: unchanged
    assert "no time zone" in q["text"] and "cannot be recorded" in q["text"]
    assert epoch["value"] in q["text"] and epoch["candidate_id"] in q["text"]
    assert q["readings_that_fit_the_field"] == 0
    assert [u["candidate_id"] for u in q["utc_readings"]] == [epoch["candidate_id"]]
    assert q["utc_readings"][0]["value"] == epoch["value"] and q["utc_readings"][0]["locator"]
    assert any(h["kind"] == "utc_reading" and h["candidate_id"] == epoch["candidate_id"] for h in q["hints"])
    assert all(h.get("fits_field") is False for h in q["hints"] if h["kind"] == "reading")
    assert "--decision correct --value <UTC instant" in q["answer_command"] and "<one reading>" not in q["answer_command"]
    assert epoch["value"] in q["answer_command"]  # named in its comment, never as a ready-to-run value
    assert "--value " + epoch["value"] not in q["answer_command"]


def test_the_start_time_conflict_is_answered_with_the_utc_reading_and_a_local_reading_is_still_refused(grouped, capsys):
    b = M.load(grouped)
    cf = _start_conflict(b)
    q = _conflict_q(Q.consolidate(b), cf["conflict_id"])
    local = cf["readings"][0]["value"]
    code, _, err = _run(capsys, "bundle", "decide", grouped, "--question", q["question_id"], "--decision", "confirm",
                        "--value", local, "--by", "S")
    assert code == 2 and "UTC instant with a zone" in err
    utc = q["utc_readings"][0]["value"]
    code, out, err = _run(capsys, "bundle", "decide", grouped, "--question", q["question_id"], "--decision", "correct",
                          "--value", utc, "--by", "S")
    assert code == 0, err
    assert json.loads(out)["recorded"] == [cf["conflict_id"]]
    cand = next(c for c in M.load(grouped)["candidates"] if c["candidate_id"] == cf["candidate_id"])
    assert cand["value_state"] == B.STATE_SCIENTIST_CONFIRMED and cand["eligibility_for_official_record"]["eligible"]


def test_a_conflict_with_no_utc_reading_held_asks_for_the_utc_start_itself(grouped):
    b = M.load(grouped)
    cf = _start_conflict(b)
    b["candidates"] = [c for c in b["candidates"] if not (c["run_id"] in cf["run_ids"] and c["statement_key"] == "acquisition_epoch")]
    q = _conflict_q(Q.consolidate(b), cf["conflict_id"])
    assert q["utc_readings"] == [] and "no time zone" in q["text"] and "give the UTC start" in q["text"]
    assert "--decision correct --value <UTC instant, YYYY-MM-DDTHH:MM:SSZ>" in q["answer_command"]


# --- 2. a conflict whose readings are off the field's list -----------------------------------------------------


def _beamtime_technique_conflict(b):
    """conf-015 (no runs, no field) made the BL15-2 2019 shape: a beamtime technique disagreement whose readings
    are macro names and Python helper lines, none an allowed technique."""
    tech = _cand(b, "system.technique", None)
    cf = next(c for c in b["conflicts"] if not c["run_ids"] and c["value_state"] == B.STATE_CONFLICTING)
    cf["candidate_id"] = tech["candidate_id"]
    for r, text in zip(cf["readings"], ("Pt_XAS.mac", "extract_voltage_and_save(target_directory,")):
        r["value"] = text
    return cf


def test_a_conflict_whose_readings_are_off_the_list_is_answered_with_an_allowed_value(grouped):
    b = M.load(grouped)
    cf = _beamtime_technique_conflict(b)
    q = _conflict_q(Q.consolidate(b), cf["conflict_id"])
    assert q["question_id"] == "Q-3344ced19f"  # unchanged by what the conflict is about
    assert q["blocking"] and q["target_field_path"] == "system.technique"
    assert q["readings_that_fit_the_field"] == 0 and "none of these readings is a value" in q["text"].casefold()
    assert "XAS" in q["text"] and q["allowed_values"]
    assert "--decision correct --value <allowed value>" in q["answer_command"] and "<one reading>" not in q["answer_command"]
    assert "allowed_values" in q["answer_command"]
    assert "utc_readings" not in q


def test_a_beamtime_conflict_counts_every_group_it_reaches(grouped):
    b = M.load(grouped)
    cf = _beamtime_technique_conflict(b)
    q = _conflict_q(Q.consolidate(b), cf["conflict_id"])
    live = len(Q.live_groups(b))
    assert q["applies_to"]["groups"] == live == q["blocks_groups"]
    assert q["applies_to"]["beamtime_wide"] is True


def test_a_conflict_with_a_reading_that_fits_still_offers_confirm_of_one_reading(grouped):
    b = M.load(grouped)
    cf = _beamtime_technique_conflict(b)
    cf["readings"][0]["value"] = "XAS"
    q = _conflict_q(Q.consolidate(b), cf["conflict_id"])
    assert q["readings_that_fit_the_field"] == 1
    assert "--decision confirm --value <one reading>" in q["answer_command"]
    assert "1 of the" in q["text"] and "cannot be recorded" in q["text"]


# --- 3. an answered question can be answered again ------------------------------------------------------------


def _beamline_question(payload):
    return next(q for q in payload["questions"] if q["kind"] == "optional_values" and "system.facility.beamline" in q.get("fields", {}))


def test_decide_question_answers_an_answered_field_again_and_a_repeat_is_harmless(grouped, capsys):
    q = _beamline_question(Q.consolidate(M.load(grouped)))
    ids = q["fields"]["system.facility.beamline"]
    argv = ["bundle", "decide", grouped, "--question", q["question_id"], "--field", "system.facility.beamline",
            "--decision", "correct", "--value", "BL15-2", "--by", "S"]
    code, out, _ = _run(capsys, *argv)
    assert code == 0 and sorted(json.loads(out)["recorded"]) == sorted(ids)
    code, out, err = _run(capsys, *argv)  # the field is answered now: the repeat resolves it and records nothing
    assert code == 0, err
    assert json.loads(out)["recorded"] == [] and sorted(json.loads(out)["unchanged"]) == sorted(ids)
    argv[argv.index("BL15-2")] = "BL 15-2"
    code, out, err = _run(capsys, *argv)  # a later decision replaces the earlier one
    assert code == 0, err and sorted(json.loads(out)["recorded"]) == sorted(ids)
    latest = B._decisions_by_target(M.load(grouped)["scientist_decisions"])
    assert {latest[("missing_value", i)]["value"] for i in ids} == {"BL 15-2"}


def test_an_answered_question_keeps_the_same_checks(grouped, capsys):
    payload = Q.consolidate(M.load(grouped))
    env = next(q for q in payload["questions"] if q["target_field_path"] == "context.environment" and q["kind"] == "missing_value")
    assert _run(capsys, "bundle", "decide", grouped, "--question", env["question_id"], "--decision", "correct",
                "--value", "ex_situ", "--by", "S")[0] == 0
    assert env["question_id"] not in {q["question_id"] for q in Q.consolidate(M.load(grouped))["questions"]}
    before = len(M.load(grouped)["scientist_decisions"])
    code, _, err = _run(capsys, "bundle", "decide", grouped, "--question", env["question_id"], "--decision", "correct",
                        "--value", "ex situ", "--by", "S")
    assert code == 2 and "allowed values" in err.casefold()
    assert len(M.load(grouped)["scientist_decisions"]) == before
    code, _, err = _run(capsys, "bundle", "decide", grouped, "--question", env["question_id"], "--decision",
                        "set_absorber", "--element", "Pt", "--edge", "L3", "--by", "S")
    assert code == 2 and "does not answer" in err
    code, out, _ = _run(capsys, "bundle", "decide", grouped, "--question", env["question_id"], "--decision", "correct",
                        "--value", "in_situ", "--by", "S")
    assert code == 0 and sorted(json.loads(out)["recorded"]) == sorted(t["id"] for t in env["targets"])


def test_an_unknown_question_is_still_not_found(grouped, capsys):
    code, _, err = _run(capsys, "bundle", "decide", grouped, "--question", "Q-0000000000", "--decision", "correct",
                        "--value", "x", "--by", "S")
    assert code == 6 and "Q-0000000000" in err


def test_show_question_shows_an_answered_question_with_its_current_answer(grouped, capsys):
    payload = Q.consolidate(M.load(grouped))
    env = next(q for q in payload["questions"] if q["target_field_path"] == "context.environment" and q["kind"] == "missing_value")
    assert _run(capsys, "bundle", "decide", grouped, "--question", env["question_id"], "--decision", "correct",
                "--value", "ex_situ", "--by", "Synthetic Scientist")[0] == 0
    code, out, err = _run(capsys, "bundle", "show", grouped, "question", env["question_id"])
    assert code == 0, err
    shown = json.loads(out)
    assert shown["question_id"] == env["question_id"] and shown["status"] == "answered"
    [answer] = shown["current_answers"]
    assert answer["decision"] == "correct" and answer["value"] == "ex_situ" and answer["targets"] == len(env["targets"])
    assert answer["by"] == "Synthetic Scientist" and answer["decision_id"]
    assert "--question " + env["question_id"] in shown["answer_command"]


def test_show_question_of_an_open_question_says_it_is_open(grouped, capsys):
    q = _beamline_question(Q.consolidate(M.load(grouped)))
    code, out, _ = _run(capsys, "bundle", "show", grouped, "question", q["question_id"])
    assert code == 0 and json.loads(out).get("status", "open") == "open"


# --- 4. a member an object the record carries requires ---------------------------------------------------------


def _with_electrolyte_name(bdir_: Path, run_id: str = "run-007") -> str:
    b = M.load(bdir_)
    gid = _group_of_run(b, run_id)
    M.decide(bdir_, target_ids=[gid], decision="confirm", value=None, **BY)
    M.decide(bdir_, target_ids=[_miss(b, NAME, run_id)], decision="correct", value="KOH", **BY)
    return gid


def test_the_composer_lists_the_concentration_an_electrolyte_name_makes_required(grouped):
    gid = _with_electrolyte_name(grouped)
    result = R.build_records(grouped)
    row = next(d for d in result["drafts"] if d["group_id"] == gid)
    assert CONC in row["missing_required"] and not row["complete"]
    report = json.loads((grouped / "drafts" / f"{gid}.composition.json").read_text())
    entry = next(m for m in report["missing_required"] if m["path"] == CONC)
    assert entry["from"] == Q.FROM_AN_ANSWER and NAME in entry["required_because"]


def test_nothing_is_required_of_an_electrolyte_the_record_does_not_carry(grouped):
    b = M.load(grouped)
    gid = _group_of_run(b, "run-007")
    M.decide(grouped, target_ids=[gid], decision="confirm", value=None, **BY)
    report = Q.compositions(M.load(grouped))[gid]
    assert CONC not in {m["path"] for m in report["missing_required"]}


def test_the_concentration_question_blocks_that_group_and_the_minimum_names_it(grouped):
    gid = _with_electrolyte_name(grouped)
    b = M.load(grouped)
    payload = Q.consolidate(b)
    target = _miss(b, CONC, "run-007")
    q = next(q for q in payload["questions"] if any(t["id"] == target for t in q["targets"]))
    assert q["blocking"] and q["blocks_group_ids"] == [gid] and CONC in q["required_fields"]
    minimum = Q.minimum_answers_for_one_group(payload, b, scope=f"group:{gid}")
    entry = next(e for e in minimum["questions"] if e["question_id"] == q["question_id"])
    assert CONC in entry["fields"] and NAME in entry["required_because"][CONC]
    assert CONC in minimum["missing_required_now"]


def test_validate_names_each_groups_first_official_error(bdir, fake_upstream):
    schema_file = fake_upstream / "schema" / "isaac_record_v1.json"
    schema = json.loads(schema_file.read_text())
    schema["properties"]["sample"]["properties"]["material"].setdefault("required", []).append("formula")
    schema_file.write_text(json.dumps(schema))
    _decide_everything(bdir)
    R.build_records(bdir)
    v = R.validate_records(bdir, run_portal=_portal("publish"))
    [row] = v["not_exportable_first"]
    assert row["verdict"] == "invalid_official"
    assert row["first_official_error"] == "sample.material: 'formula' is a required property"


# --- 5. a potential the file names state, which the record will not carry ---------------------------------------


def test_a_stated_potential_without_a_scale_is_warned_about_with_the_command(grouped):
    b = M.load(grouped)
    gid = _group_of_run(b, "run-001")
    M.decide(grouped, target_ids=[gid], decision="confirm", value=None, **BY)
    result = R.build_records(grouped)
    [w] = [w for w in result["warnings"] if w["group_id"] == gid]
    assert w["code"] == "stated_potential_not_in_record"
    assert "the file names state a potential (100mV, read as 0.1 V)" in w["text"]
    assert "until the potential scale is confirmed" in w["text"]
    scale_q = next(q for q in Q.consolidate(M.load(grouped))["questions"]
                   if _miss(b, SCALE, "run-001") in (q.get("fields") or {}).get(SCALE, ()))
    assert w["command"].startswith(f"isaac bundle decide <bundle_dir> --question {scale_q['question_id']} --field {SCALE}")
    assert w["command"] in w["text"]
    row = next(d for d in result["drafts"] if d["group_id"] == gid)
    assert row["warnings"] == [w["text"]]


def test_validate_warns_too_and_the_minimum_recommends_the_scale_question(grouped, monkeypatch):
    from isaac_api.local_import import portal as P

    b = M.load(grouped)
    gid = _group_of_run(b, "run-001")
    M.decide(grouped, target_ids=[gid], decision="confirm", value=None, **BY)
    monkeypatch.setattr(P, "run_portal_check", _portal("publish"))
    R.build_records(grouped)
    v = R.validate_records(grouped)
    assert any(w["group_id"] == gid and "100mV" in w["text"] for w in v["warnings"])
    payload = Q.consolidate(M.load(grouped))
    minimum = Q.minimum_answers_for_one_group(payload, M.load(grouped), scope=f"group:{gid}")
    [rec] = minimum["recommended"]
    assert rec["fields"] == [SCALE] and rec["blocking"] is False and "100mV" in rec["why"]
    assert rec["question_id"] not in {e["question_id"] for e in minimum["questions"]} or minimum["blocking_questions"]
    assert minimum["warnings"] and "100mV" in minimum["warnings"][0]


def test_no_warning_once_the_scale_and_the_set_point_are_confirmed(grouped):
    b = M.load(grouped)
    gid = _group_of_run(b, "run-001")
    M.decide(grouped, target_ids=[gid], decision="confirm", value=None, **BY)
    M.decide(grouped, target_ids=[_miss(b, SCALE, "run-001")], decision="correct", value="RHE", **BY)
    M.decide(grouped, target_ids=[_cand(b, SETPOINT, "run-001")["candidate_id"]], decision="confirm", value=None, **BY)
    report = Q.compositions(M.load(grouped))[gid]
    assert SETPOINT in {f["path"] for f in report["filled"]} and not report.get("warnings")


def test_a_scale_alone_still_warns_until_the_set_point_is_confirmed(grouped):
    b = M.load(grouped)
    gid = _group_of_run(b, "run-001")
    M.decide(grouped, target_ids=[gid], decision="confirm", value=None, **BY)
    M.decide(grouped, target_ids=[_miss(b, SCALE, "run-001")], decision="correct", value="RHE", **BY)
    [w] = Q.compositions(M.load(grouped))[gid]["warnings"]
    assert "until the potential set-point is confirmed" in w["text"] and "100mV" in w["text"]


def test_an_unread_file_name_potential_token_is_warned_about_by_its_literal_with_the_answer_held_back(grouped):
    b = M.load(grouped)
    gid = _group_of_run(b, "run-001")
    g = next(x for x in b["record_groups"] if x["group_id"] == gid)
    g["status"] = B.STATE_SCIENTIST_CONFIRMED
    # the BL15-2 2019 shape: the potential is an unread file-name token (`m800mV`) and the set-point was answered
    setpoint = _cand(b, SETPOINT, "run-001")
    token = copy.deepcopy(setpoint)
    token.update(candidate_id="cand-9999", target_field_path=None, statement_key="unknown_token", value=None,
                 observed_literals=["m800mV"], value_state="unmapped")
    token["evidence"] = [{**token["evidence"][0], "literal_value": "m800mV", "statement_key": "unknown_token"}]
    b["candidates"].append(token)
    setpoint["evidence"] = [{**e, "locator": "line 9 #C comment"} for e in setpoint["evidence"]]  # not a file name
    setpoint.update(value_state=B.STATE_SCIENTIST_CONFIRMED, eligibility_for_official_record={"eligible": True, "reason": "test"})
    b["scientist_decisions"].append({"decision_id": "d-09999", "target": {"kind": "candidate", "id": setpoint["candidate_id"]},
                                     "decision": "correct", "value": -0.8, "decided_by": {"name": "S"}})
    report = R.compose_group(b, g, grouped)[1]
    [w] = report["warnings"]
    assert "m800mV" in w["text"] and "-0.8 V" in w["text"] and "until the potential scale is confirmed" in w["text"]


# --- 6. reveal compares a number given as text numerically --------------------------------------------------------


def test_reveal_compares_a_numeric_reading_given_as_text_numerically(bdir):
    b = M.load(bdir)
    c = _cand(b, SETPOINT, "run-001")
    assert c["value"] == 0.1
    src = c["evidence"][0]["source_id"]
    for value in ("0.1", "0.10", "0.2", "about 0.1"):
        M.annotate(bdir, target_id=c["candidate_id"], value=value, excerpt_locator="filename token 6", source_id=src,
                   model_id="m", blind=True, rationale="")
    same, padded, other, words = M.reveal(bdir, c["candidate_id"])["ai_readings"]
    assert same["agrees_with_parser"] is True and same["relation"] == "supports" and same["compared_as"] == "number"
    assert "as text" in same["comparison_note"] and "--json" in same["comparison_note"]
    assert padded["agrees_with_parser"] is True
    assert other["agrees_with_parser"] is False and other["relation"] == "contradicts" and other["compared_as"] == "number"
    assert words["agrees_with_parser"] is False and "compared_as" not in words


def test_reveal_of_a_text_field_still_compares_exactly(bdir):
    b = M.load(bdir)
    c = _cand(b, "timestamps.acquired_start_utc", "run-001")
    M.annotate(bdir, target_id=c["candidate_id"], value=c["value"], excerpt_locator="line 2",
               source_id=c["evidence"][0]["source_id"], model_id="m", blind=True, rationale="")
    [r] = M.reveal(bdir, c["candidate_id"])["ai_readings"]
    assert r["agrees_with_parser"] is True and "compared_as" not in r
