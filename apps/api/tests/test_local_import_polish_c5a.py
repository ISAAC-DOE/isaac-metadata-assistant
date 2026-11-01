"""Polish c5-a: walkthrough findings on one real beamtime, reproduced on the synthetic corpus. Synthetic only.

* (MED1) An ANSWERED absorber question is resolved again under its id: a repeat records nothing (exit 0), a
  per-group override (``--only group:<id>``, a reference foil) is recorded, ``bundle show question`` shows it with
  ``status`` and its current answers, and the same checks apply. The counter question and the clock-zone
  question too: each kind that dropped out of the open list once answered.
* (MED2) A potential the file names state with NO set-point read from them (an ``unknown_token``) and no confirmed
  scale is warned about with BOTH steps and both commands, so the scientist is not sent round twice.
* (LOW3) The counter question shows real file names of the bundle with the asked position's token marked.
* (LOW6) An imported Athena E0 descriptor says what its ``generated_utc`` is (when a scientist approved ISAAC's
  reading of it), not that the scientist made the Athena processing then.
* (LOW7) Every decide reply starts with a plain ``statement`` ("Fe K recorded for 9 groups").
* Every open question id is unchanged; answered ones keep the id they were asked with.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_grouping_cli import FIXTURE, _folder
from test_local_import_polish_c3q import GOLDEN_IDS, SCALE, SETPOINT, _group_of_run, _miss
from test_local_import_polish_c4a import _add_athena, _approve, _exported
from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, SEMANTICS, _cand, _decide_everything, bdir, fake_upstream, pristine)

WHO = "Synthetic Scientist"
ABSORBER = "Q-be8c05cb9f"  # the synthetic grouped corpus: the files state Zz L3 for its 9 groups
COUNTER = "Q-36dcf727f3"  # _qid("experiment", "naming_counter_positions", "rgq-experiment-counter-positions")
ZONE = "Q-5b4328bd6a"  # _qid("experiment", "clock_time_zone", "instrument_clock")


def _run(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


@pytest.fixture(scope="module")
def grouped_pristine(tmp_path_factory):
    out = tmp_path_factory.mktemp("c5a") / "grouped"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def grouped(grouped_pristine, tmp_path):
    target = tmp_path / "grouped"
    shutil.copytree(grouped_pristine, target)
    return target


@pytest.fixture()
def syn(tmp_path):
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert cli.main(["import", str(src), "--out", str(b)]) == 0
    M.group(b)
    return b


@pytest.fixture()
def xdc(tmp_path):
    from test_local_import_xdc_start_time import _import, stamp

    x = _import(tmp_path / "xdc", {"SYN_alpha_A.001": stamp("2099-07-14T10:23:45"), "SYN_beta_A.001": stamp("2099-07-15T10:00:00")})
    M.group(x)
    return x


def _ids(payload) -> list[str]:
    return sorted(q["question_id"] for q in payload["questions"])


def _absorber_argv(bdir, element="Fe", edge="K", *extra):
    return ["bundle", "decide", bdir, "--question", ABSORBER, "--decision", "set_absorber", "--element", element,
            "--edge", edge, *extra, "--by", WHO]


# --- MED1: an answered absorber question is resolved again ----------------------------------------------------


def test_an_answered_absorber_question_is_answered_again_and_a_repeat_records_nothing(grouped, capsys):
    q = Q.question(Q.consolidate(M.load(grouped)), ABSORBER)
    groups = [t["id"] for t in q["targets"]]
    assert q["kind"] == "confirm_absorber" and len(groups) == 9
    code, out, err = _run(capsys, *_absorber_argv(grouped))
    assert code == 0, err
    assert sorted(json.loads(out)["recorded"]) == sorted(groups)
    assert Q.question(Q.consolidate(M.load(grouped)), ABSORBER) is None  # answered: no longer open
    held = len(M.load(grouped)["scientist_decisions"])
    code, out, err = _run(capsys, *_absorber_argv(grouped))  # the walkthrough's "No open question" (exit 6)
    assert code == 0, err
    reply = json.loads(out)
    assert reply["recorded"] == [] and sorted(reply["unchanged"]) == sorted(groups)
    assert len(M.load(grouped)["scientist_decisions"]) == held
    # a reference foil in one group: the per-group override is recorded for that group alone
    code, out, err = _run(capsys, *_absorber_argv(grouped, "Au", "L3", "--only", f"group:{groups[0]}"))
    assert code == 0, err
    assert json.loads(out)["recorded"] == [groups[0]]
    S = __import__("isaac_api.local_import.suggestions", fromlist=["absorber_decisions"])
    got = {g: (d["element"], d["edge"]) for g, d in S.absorber_decisions(M.load(grouped)).items()}
    assert got[groups[0]] == ("Au", "L3") and {got[g] for g in groups[1:]} == {("Fe", "K")}


def test_an_answered_absorber_question_keeps_the_same_checks(grouped, capsys):
    assert _run(capsys, *_absorber_argv(grouped))[0] == 0
    held = len(M.load(grouped)["scientist_decisions"])
    code, _, err = _run(capsys, "bundle", "decide", grouped, "--question", ABSORBER, "--decision", "confirm", "--by", WHO)
    assert code == 2 and "does not answer" in err  # never a bulk confirm of the record GROUPS it targets
    code, _, err = _run(capsys, *_absorber_argv(grouped, "Fe", "Q9"))
    assert code == 2 and "--edge" in err
    code, _, err = _run(capsys, *_absorber_argv(grouped, "Fe", "K", "--only", "group:rg-0000000000000000"))
    assert code == 6 and ABSORBER in err
    assert len(M.load(grouped)["scientist_decisions"]) == held


def test_a_repeat_after_the_group_was_confirmed_still_records_nothing(grouped, capsys):
    b = M.load(grouped)
    gid = Q.question(Q.consolidate(b), ABSORBER)["targets"][0]["id"]
    assert _run(capsys, *_absorber_argv(grouped, "Fe", "K", "--only", f"group:{gid}"))[0] == 0
    M.decide(grouped, target_ids=[gid], decision="confirm", value=None, by=WHO, orcid=None)
    held = len(M.load(grouped)["scientist_decisions"])
    code, out, err = _run(capsys, *_absorber_argv(grouped, "Fe", "K", "--only", f"group:{gid}"))
    assert code == 0, err
    assert json.loads(out)["recorded"] == [] and json.loads(out)["unchanged"] == [gid]
    assert len(M.load(grouped)["scientist_decisions"]) == held


def test_show_question_shows_an_answered_absorber_question_with_its_current_answers(grouped, capsys):
    groups = [t["id"] for t in Q.question(Q.consolidate(M.load(grouped)), ABSORBER)["targets"]]
    assert _run(capsys, *_absorber_argv(grouped))[0] == 0
    assert _run(capsys, *_absorber_argv(grouped, "Au", "L3", "--only", f"group:{groups[0]}"))[0] == 0
    code, out, err = _run(capsys, "bundle", "show", grouped, "question", ABSORBER)
    assert code == 0, err
    shown = json.loads(out)
    assert shown["question_id"] == ABSORBER and shown["kind"] == "confirm_absorber" and shown["status"] == "answered"
    assert shown["answered_targets"] == 9
    fe, au = shown["current_answers"]
    assert (fe["decision"], fe["element"], fe["edge"], fe["targets"], fe["by"]) == ("set_absorber", "Fe", "K", 8, WHO)
    assert (au["element"], au["edge"], au["targets"]) == ("Au", "L3", 1) and au["decision_id"]


def test_a_partly_answered_absorber_question_is_open_and_lists_its_answer(grouped, capsys):
    groups = [t["id"] for t in Q.question(Q.consolidate(M.load(grouped)), ABSORBER)["targets"]]
    assert _run(capsys, *_absorber_argv(grouped, "Au", "L3", "--only", f"group:{groups[0]}"))[0] == 0
    shown = json.loads(_run(capsys, "bundle", "show", grouped, "question", ABSORBER)[1])
    assert shown["status"] == "open" and shown["answered_targets"] == 1
    assert [(a["element"], a["targets"]) for a in shown["current_answers"]] == [("Au", 1)]
    # the open question still answers the rest; re-answering the answered group through it works too
    code, out, err = _run(capsys, *_absorber_argv(grouped, "Fe", "K", "--only", f"group:{groups[0]}"))
    assert code == 0, err
    assert json.loads(out)["recorded"] == [groups[0]]


# --- MED1: the other kinds that dropped out once answered -------------------------------------------------------


def test_an_answered_counter_question_is_resolved_again_and_shown(syn, capsys):
    (q,) = [q for q in Q.consolidate(M.load(syn))["questions"] if q["kind"] == "naming_counter_positions"]
    assert q["question_id"] == COUNTER
    argv = ["bundle", "decide", syn, "--question", COUNTER, "--decision", B.NOT_COUNTER_DECISION, "--by", WHO]
    assert _run(capsys, *argv)[0] == 0
    assert Q.question(Q.consolidate(M.load(syn)), COUNTER) is None
    code, out, err = _run(capsys, *argv)  # was "No open question" (exit 6)
    assert code == 0, err
    assert json.loads(out)["recorded"] == [] and json.loads(out)["unchanged"] == ["experiment"]
    shown = json.loads(_run(capsys, "bundle", "show", syn, "question", COUNTER)[1])
    assert shown["status"] == "answered" and shown["positions"] == [2]
    [a] = shown["current_answers"]
    assert a["decision"] == B.NOT_COUNTER_DECISION and a["positions"] == [2] and a["by"] == WHO
    # a later answer replaces it through the same id, with the same checks
    code, _, err = _run(capsys, "bundle", "decide", syn, "--question", COUNTER, "--decision", "set_absorber",
                        "--element", "Fe", "--edge", "K", "--by", WHO)
    assert code == 2 and "does not answer" in err
    code, out, err = _run(capsys, "bundle", "decide", syn, "--question", COUNTER, "--decision", "set_counter_positions",
                          "--positions", "2", "--by", WHO)
    assert code == 0, err
    assert json.loads(out)["recorded"] == ["experiment"]
    assert M.counter_positions(M.load(syn)) == [2]


def test_the_counter_question_is_shown_after_the_regroup_that_applied_its_answer(syn, capsys):
    M.decide(syn, target_ids=["experiment"], decision="set_counter_positions", value=None, by=WHO, orcid=None, positions=[2])
    M.group(syn, regroup=True)
    assert not [g for g in M.load(syn).get("grouping_questions") or () if g.get("kind") == "naming_counter_positions"]
    code, out, err = _run(capsys, "bundle", "show", syn, "question", COUNTER)
    assert code == 0, err
    shown = json.loads(out)
    assert shown["status"] == "answered" and shown["current_answers"][0]["positions"] == [2]
    code, out, err = _run(capsys, "bundle", "decide", syn, "--question", COUNTER, "--decision", "set_counter_positions",
                          "--positions", "2", "--by", WHO)
    assert code == 0, err
    assert json.loads(out)["unchanged"] == ["experiment"]


def test_an_answered_clock_zone_question_is_resolved_again_and_shown(xdc, capsys):
    assert Q.question(Q.consolidate(M.load(xdc)), ZONE)["kind"] == "clock_time_zone"
    argv = ["bundle", "decide", xdc, "--question", ZONE, "--decision", B.CLOCK_ZONE_DECISION, "--value", "UTC", "--by", WHO]
    assert _run(capsys, *argv)[0] == 0
    assert Q.question(Q.consolidate(M.load(xdc)), ZONE) is None
    code, out, err = _run(capsys, *argv)
    assert code == 0, err
    assert json.loads(out)["unchanged"] == ["experiment"]
    code, _, err = _run(capsys, *argv[:-4], "--value", "PST", "--by", WHO)
    assert code == 2 and "Nothing was recorded" in err  # the same checks
    code, out, err = _run(capsys, *argv[:-4], "--value", "America/Los_Angeles", "--by", WHO)
    assert code == 0, err
    assert json.loads(out)["recorded"] == ["experiment"]
    shown = json.loads(_run(capsys, "bundle", "show", xdc, "question", ZONE)[1])
    assert shown["status"] == "answered" and [a["value"] for a in shown["current_answers"]] == ["America/Los_Angeles"]


def test_an_unknown_question_is_still_not_found(grouped, capsys):
    for argv in (["bundle", "decide", grouped, "--question", "Q-0000000000", "--decision", "set_absorber", "--element", "Fe",
                  "--edge", "K", "--by", WHO], ["bundle", "show", grouped, "question", "Q-0000000000"]):
        code, _, err = _run(capsys, *argv)
        assert code == 6 and "Q-0000000000" in err


# --- ids --------------------------------------------------------------------------------------------------------


def test_open_ids_are_unchanged_and_an_answered_question_keeps_its_id(grouped, capsys):
    payload = Q.consolidate(M.load(grouped))
    ids = _ids(payload)
    assert (len(ids), hashlib.sha256("\n".join(ids).encode()).hexdigest()) == GOLDEN_IDS
    assert _run(capsys, *_absorber_argv(grouped))[0] == 0
    b = M.load(grouped)
    assert set(_ids(Q.consolidate(b))) == set(ids) - {ABSORBER}
    assert set(_ids(Q.consolidate(b, include_answered=True))) >= set(ids)


# --- MED2: both steps named when no set-point was read ----------------------------------------------------------


def _unread_potential(grouped):
    """IN MEMORY: run-001's set-point turned into an unread file-name token (`m500mV`, kept as `unknown_token`) with
    the set-point asked as a missing value — the BL6-2c shape (`…_m500mV`) — and its group confirmed."""
    b = M.load(grouped)
    gid = _group_of_run(b, "run-001")
    sp = _cand(b, SETPOINT, "run-001")
    sp.update(target_field_path=None, statement_key="unknown_token", value=None, observed_literals=["m500mV"],
              value_state="unmapped")
    sp["evidence"] = [{**e, "literal_value": "m500mV", "statement_key": "unknown_token"} for e in sp["evidence"]]
    slot = copy.deepcopy(next(m for m in b["missing_values"] if m["target_field_path"] == SCALE and m["run_id"] == "run-001"))
    slot.update(value_id="miss-9999", target_field_path=SETPOINT)
    b["missing_values"].append(slot)
    _answer(b, gid, "confirm")
    return b, gid


def _answer(b, tid, decision, value=None):
    M.record_decision(b, target_ids=[tid], decision=decision, value=value, by=WHO, orcid=None)
    B.refresh_questions(b)
    B.apply_derivations(b)


def _warning(b, gid, grouped):
    g = next(x for x in b["record_groups"] if x["group_id"] == gid)
    [w] = R.with_question_commands(b, R.compose_group(b, g, grouped)[1]["warnings"])
    return w


def test_an_unread_potential_without_a_scale_names_both_steps_and_both_commands(grouped):
    b, gid = _unread_potential(grouped)
    w = _warning(b, gid, grouped)
    assert w["code"] == "stated_potential_not_in_record" and "m500mV" in w["text"]
    assert w["needs"] == SCALE and w["also_needs"] == SETPOINT and w["also_targets"] == ["miss-9999"]
    assert "set-point" in w["text"] and "scale" in w["text"] and "no set-point value was read" in w["text"]
    payload = Q.consolidate(b)
    scale_q = Q.command_for_targets(payload, [_miss(b, SCALE, "run-001")], SCALE, gid)
    setpoint_q = Q.command_for_targets(payload, ["miss-9999"], SETPOINT, gid)
    assert w["command"] == scale_q and w["also_command"] == setpoint_q
    assert scale_q in w["text"] and setpoint_q in w["text"] and f"--field {SETPOINT}" in w["text"]
    assert "--json" in setpoint_q  # volts are a number


def test_after_the_scale_only_the_set_point_is_left(grouped):
    b, gid = _unread_potential(grouped)
    _answer(b, _miss(b, SCALE, "run-001"), "correct", "RHE")
    w = _warning(b, gid, grouped)
    assert w["needs"] == SETPOINT and "also_needs" not in w
    assert "until the potential set-point is confirmed" in w["text"] and "scale" not in w["text"]


def test_a_set_point_already_answered_names_the_scale_alone(grouped):
    b, gid = _unread_potential(grouped)
    _answer(b, "miss-9999", "correct", -0.5)
    w = _warning(b, gid, grouped)
    assert w["needs"] == SCALE and "also_needs" not in w and "-0.5 V" in w["text"]
    assert "until the potential scale is confirmed:" in w["text"]


def test_a_set_point_read_from_the_name_still_names_the_scale_alone(grouped):
    b = M.load(grouped)
    gid = _group_of_run(b, "run-001")
    _answer(b, gid, "confirm")
    w = _warning(b, gid, grouped)  # 100mV, read as 0.1 V: the c3-q warning, unchanged
    assert w["needs"] == SCALE and "also_needs" not in w and "read as 0.1 V" in w["text"]


def test_the_minimum_recommends_both_questions(grouped):
    b, gid = _unread_potential(grouped)
    minimum = Q.minimum_answers_for_one_group(Q.consolidate(b), b, scope=f"group:{gid}")
    assert sorted(f for r in minimum["recommended"] for f in r["fields"]) == sorted([SCALE, SETPOINT])
    assert all(not r["blocking"] and "m500mV" in r["why"] and SETPOINT in r["why"] for r in minimum["recommended"])


# --- LOW3: the counter question shows real names ----------------------------------------------------------------


def test_the_counter_question_shows_real_file_names_with_the_asked_token_marked(syn):
    (q,) = [q for q in Q.consolidate(M.load(syn))["questions"] if q["kind"] == "naming_counter_positions"]
    assert q["question_id"] == COUNTER and q["positions"] == [2]
    assert "XX_02" not in q["text"]
    assert "Q4_[02]_SYNcat_pH2_400mV" in q["text"] and "Q4_[03]_SYNcat_pH2_400mV" in q["text"]
    [hint] = [h for h in q["hints"] if h["kind"] == "grouping"]
    assert hint["literal"] == ["Q4_[02]_SYNcat_pH2_400mV", "Q4_[03]_SYNcat_pH2_400mV"]
    assert q["example_names"] == {"2": ["Q4_[02]_SYNcat_pH2_400mV", "Q4_[03]_SYNcat_pH2_400mV"]}


def test_a_marked_name_keeps_its_separators_and_signs():
    assert Q._marked_token("SYNfilm_on_Au_OCV_15_1500mV", 4) == "SYNfilm_on_Au_[OCV]_15_1500mV"
    assert Q._marked_token("Pt-C_x_-50mV.dat", 4) == "Pt-C_x_[-50mV].dat"
    assert Q._marked_token("a_b", 3) is None


# --- LOW6: the Athena descriptor's time is explained ------------------------------------------------------------


def test_an_imported_athena_descriptor_says_its_time_is_the_approval_in_isaac(bdir, tmp_path):
    _decide_everything(bdir)
    _add_athena(bdir, subset=False)
    M.decide(bdir, target_ids=["p1"], decision="defer", value=None, **BY)
    _approve(bdir, "p2")
    [out] = _exported(bdir, tmp_path)["descriptors"]["outputs"]
    approval = next(d for d in reversed(M.load(bdir)["scientist_decisions"]) if d["decision"] == "approve")
    assert out["generated_utc"] == approval["decided_utc"]  # required by the schema: kept, and now explained
    notes = out["generated_by"]["notes"]
    assert "generated_utc is when a scientist approved ISAAC's reading of it" in notes
    assert "not when the Athena processing was done" in notes


# --- LOW7: a plain statement first -------------------------------------------------------------------------------


def test_every_decide_reply_starts_with_a_plain_statement(grouped, capsys):
    code, out, _ = _run(capsys, *_absorber_argv(grouped))
    reply = json.loads(out)
    assert code == 0 and next(iter(reply)) == "statement"
    assert reply["statement"] == "Fe K recorded for 9 groups." and len(reply["recorded"]) == 9
    reply = json.loads(_run(capsys, *_absorber_argv(grouped))[1])
    assert reply["statement"] == "Nothing new recorded: 9 groups already have Fe K."
    env = next(q for q in Q.consolidate(M.load(grouped))["questions"]
               if q["target_field_path"] == "context.environment" and q["kind"] == "missing_value")
    runs = len({m["run_id"] for m in M.load(grouped)["missing_values"] if m["value_id"] in {t["id"] for t in env["targets"]}})
    reply = json.loads(_run(capsys, "bundle", "decide", grouped, "--question", env["question_id"], "--decision", "defer",
                            "--by", WHO)[1])
    assert next(iter(reply)) == "statement" and reply["statement"] == f"deferred for {runs} runs: environment."
    assert reply["recorded"]  # the ids stay, for --json consumers


def test_a_statement_already_said_is_kept_and_moved_first(syn, capsys):
    (q,) = [q for q in Q.consolidate(M.load(syn))["questions"] if q["kind"] == "naming_counter_positions"]
    reply = json.loads(_run(capsys, "bundle", "decide", syn, "--question", q["question_id"], "--decision",
                            B.NOT_COUNTER_DECISION, "--by", WHO)[1])
    assert next(iter(reply)) == "statement" and "Grouping is unchanged by this answer" in reply["statement"]


def test_a_value_answer_says_the_value_and_the_field(bdir):
    b = M.load(bdir)
    cid = _cand(b, "timestamps.acquired_start_utc", "run-001")["candidate_id"]
    reply = M.decide(bdir, target_ids=[cid], decision="confirm", value=None, **BY)
    assert reply["statement"] == "confirmed for 1 run: acquired start utc."
    reply = M.decide(bdir, target_ids=[_miss(b, "system.domain", None)], decision="correct", value="experimental", **BY)
    assert reply["statement"] == "'experimental' recorded for the whole beamtime: domain."


def test_re_answering_the_whole_absorber_question_keeps_a_per_group_answer(grouped, capsys):
    """Review (cycle 5): answer for all, override one group, then re-run the answer for all — the override
    was silently undone. It is now kept and named; `--only` is the way to change it."""
    S = __import__("isaac_api.local_import.suggestions", fromlist=["absorber_decisions"])
    groups = [t["id"] for t in Q.question(Q.consolidate(M.load(grouped)), ABSORBER)["targets"]]
    assert _run(capsys, *_absorber_argv(grouped))[0] == 0
    assert _run(capsys, *_absorber_argv(grouped, "Au", "L3", "--only", f"group:{groups[0]}"))[0] == 0
    code, out, err = _run(capsys, *_absorber_argv(grouped))  # Fe K for all, again
    assert code == 0, err
    reply = json.loads(out)
    assert reply["kept_per_group_answers"] == [{"group_id": groups[0], "element": "Au", "edge": "L3"}]
    assert f"{groups[0]} keeps Au L3" in reply["statement"]
    got = {g: (d["element"], d["edge"]) for g, d in S.absorber_decisions(M.load(grouped)).items()}
    assert got[groups[0]] == ("Au", "L3") and {got[g] for g in groups[1:]} == {("Fe", "K")}
    # changing the whole question's answer still leaves the override alone
    assert _run(capsys, *_absorber_argv(grouped, "Co", "K"))[0] == 0
    got = {g: (d["element"], d["edge"]) for g, d in S.absorber_decisions(M.load(grouped)).items()}
    assert got[groups[0]] == ("Au", "L3") and {got[g] for g in groups[1:]} == {("Co", "K")}
