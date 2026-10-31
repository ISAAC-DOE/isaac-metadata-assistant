"""c14f: what a vocabulary request says once it is answered, re-asked or waiting. Synthetic only (SYN_/ZZ words).

From a real walk on one beamtime (counts only, no data):

* MED-2: ``decide --as-said`` said "the field keeps what it has, or stays missing"; the reply now names the allowed
  value the record keeps meanwhile, or says the field stays missing when nothing allowed is held.
* MED-3: a word asked for again on one run carried the earlier, answered sheet request into its draft (runs 139,
  count 2, "partly answered for 138"). A draft now counts only open requests; the earlier one is said apart.
* LOW-1: ``--merge`` kept an answered term's description as one to read before filing; it is now kept only in case the
  word is asked for again, never to be filed, and counted apart.
* LOW-2: ``validate``'s ``pending_vocabulary`` says when the group still exports.
* LOW-3: the ``--out`` summary counts the terms that need a one-word form.
* LOW-4: ``decide`` says when its value answers an open request, read as ``propose-terms`` reads it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import propose_terms as P

from test_local_import_records import fake_upstream  # noqa: F401  (autouse: validate runs the export dry run)
from test_local_import_vocabulary_requests import (  # noqa: F401  (fixtures)
    CELL, ENV, KEPT, REACTION, WHO, _decide, _env_sheet, _miss_of, _report, _said, _term, b, grouped, grouped_base,
    pristine_bundle, ticking)

WORD = "aqueous_electrochemistry"
SKILL = Path(__file__).resolve().parents[3] / ".claude/skills/isaac-historical-import"


def _vid(bdir: Path, run_id: str, field: str = ENV) -> str:
    return _miss_of(bdir, field, run_id)["value_id"]


def _out(bdir: Path, capsys, *args: str) -> dict:
    """``decide`` that records: its printed reply."""
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(bdir), *args, "--by", WHO]) == 0
    return json.loads(capsys.readouterr().out)


# --- MED-3: a draft counts only open requests ----------------------------------------------------------------


def test_a_word_asked_again_is_a_draft_for_the_new_request_only(grouped, capsys, tmp_path, ticking):
    """The sheet asked for the word on two runs; both were answered since; the scientist asks for it again on one."""
    _env_sheet(grouped, tmp_path)  # vr-00001: the sheet's word on run-001 and run-002
    for rid in ("run-001", "run-002"):
        _out(grouped, capsys, "--target", _vid(grouped, rid), "--decision", "correct", "--value", "in_situ")
    assert _said(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", WORD)[0] == 2
    report = _report(grouped, capsys)
    t = _term(report, ENV, WORD)
    d = t["draft"]
    assert d["drafted"] is True and d["answered"] is False
    # the draft is the new request's: one run, one occurrence, its own citation (was: runs 2, count 2, both citations)
    assert t["runs"] == 1 and t["run_ids"] == ["run-001"] and t["count"] == 1 and t["by_origin"]["scientist_request"] == 1
    assert [c["ref"]["id"] for c in t["citations"]] == ["vr-00002"] and t["citations_total"] == 1
    assert t["answered_requests_apart"] == 1 and d["earlier_requests_answered"] == ["vr-00001"]
    # partly_answered is read over the open request only: nothing of it was answered after it was asked
    assert "partly_answered" not in d and d["runs_answered"] == 0 and report["totals"]["partly_answered"] == 0
    assert d["earlier_requests_answered_note"] == (
        "The new request is for 1 run(s) (which hold `in_situ` from before it); the earlier request (vr-00001, from a "
        "cell of the filled template, 2 run(s)) was answered since and is not part of this draft.")
    assert [n["request_id"] for n in t["answered_scientist_notes"]] == ["vr-00001"]
    assert [n["request_id"] for n in t["scientist_notes"]] == ["vr-00002"]


def test_partly_answered_counts_the_open_requests_runs_only(grouped, capsys, tmp_path, ticking):
    _env_sheet(grouped, tmp_path)  # vr-00001 on run-001, run-002: answered since for both
    for rid in ("run-001", "run-002"):
        _out(grouped, capsys, "--target", _vid(grouped, rid), "--decision", "correct", "--value", "in_situ")
    with pytest.raises(M.OffListRefused):  # vr-00002 on run-001 (holds in_situ from before) and run-003 (nothing)
        M.decide(grouped, target_ids=[_vid(grouped, "run-001"), _vid(grouped, "run-003")], decision="correct",
                 value=WORD, by=WHO, orcid=None, as_said=True)
    _out(grouped, capsys, "--target", _vid(grouped, "run-003"), "--decision", "correct", "--value", "ex_situ")
    d = _term(_report(grouped, capsys), ENV, WORD)["draft"]
    # run-002 belongs to the answered sheet request only: never counted as this draft's answered run
    assert d["runs_answered"] == 1 and d["answered_with"] == ["ex_situ"]
    assert d["partly_answered"].startswith("Partly answered since it was asked for: an allowed value (`ex_situ`) now "
                                           "stands for 1 run(s)")
    assert "The new request is for 2 run(s) (which hold `in_situ` from before it)" in d["earlier_requests_answered_note"]


def test_a_term_answered_throughout_keeps_its_counts(grouped, capsys, tmp_path, ticking):
    """Nothing still asks for it: not drafted, and what was asked is still counted (the earlier behaviour)."""
    _env_sheet(grouped, tmp_path)
    for rid in ("run-001", "run-002"):
        _out(grouped, capsys, "--target", _vid(grouped, rid), "--decision", "correct", "--value", "in_situ")
    t = _term(_report(grouped, capsys), ENV, WORD)
    assert t["draft"]["answered"] is True and t["runs"] == 2 and t["count"] == 1
    assert "answered_requests_apart" not in t and "earlier_requests_answered" not in t["draft"]


# --- MED-2: the reply names what the record keeps meanwhile --------------------------------------------------


def test_the_as_said_reply_names_the_value_the_record_keeps(grouped, capsys, ticking):
    _out(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", "in_situ")
    code, err = _said(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", WORD)
    assert code == 2 and KEPT in err
    assert "the record keeps `in_situ` meanwhile; ask whether that is acceptable until the term exists" in err
    assert "stays missing" not in err and "keeps what it has" not in err
    code, err = _said(grouped, capsys, "--target", _vid(grouped, "run-002"), "--decision", "correct", "--value", WORD)
    assert code == 2 and ("the field stays missing until the vocabulary has the term or you answer with an allowed value"
                          in err) and "meanwhile" not in err


def test_a_request_over_runs_holding_and_lacking_a_value_says_both(grouped, ticking):
    _decide_value = M.decide(grouped, target_ids=[_vid(grouped, "run-001")], decision="correct", value="in_situ",
                             by=WHO, orcid=None)
    assert _decide_value["recorded"]
    with pytest.raises(M.OffListRefused) as refused:
        M.decide(grouped, target_ids=[_vid(grouped, "run-001"), _vid(grouped, "run-002")], decision="correct",
                 value=WORD, by=WHO, orcid=None, as_said=True)
    assert ("for 1 run(s) the record keeps `in_situ` meanwhile; ask whether that is acceptable until the term exists; "
            "for 1 run(s) the field stays missing") in str(refused.value)


# --- LOW-4: decide says it answers an open request -------------------------------------------------------------


def test_decide_says_when_its_value_answers_an_open_request(grouped, capsys, ticking):
    assert _said(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", WORD)[0] == 2
    reply = _out(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", "in_situ")
    assert f"This answers your request for '{WORD}' (vr-00001); it is no longer drafted." in reply["statement"]
    assert reply["answers_requests"] == ["vr-00001"]
    assert _term(_report(grouped, capsys), ENV, WORD)["draft"]["answered"] is True  # what propose-terms reads too
    # the same value again answers nothing new: nothing said
    again = _out(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", "in_situ")
    assert "answers_requests" not in again and "This answers" not in (again.get("statement") or "")


def test_a_value_restated_after_the_word_says_it_answers_it(grouped, capsys, ticking):
    """in_situ, their word --as-said, in_situ again: the re-recorded value answers the request, and says so."""
    _out(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", "in_situ")
    assert _said(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", WORD)[0] == 2
    reply = _out(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", "in_situ")
    assert reply["recorded"] and f"This answers your request for '{WORD}' (vr-00001); it is no longer drafted." in reply["statement"]


def test_decide_says_what_still_drafts_the_word(grouped, capsys, ticking):
    for rid in ("run-001", "run-002"):
        assert _said(grouped, capsys, "--target", _vid(grouped, rid), "--decision", "correct", "--value", WORD)[0] == 2
    reply = _out(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", "in_situ")
    assert (f"This answers your request for '{WORD}' (vr-00001); your other request(s) for it (vr-00002) are still "
            "drafted.") in reply["statement"]
    assert _term(_report(grouped, capsys), ENV, WORD)["draft"]["drafted"] is True


# --- LOW-1 and LOW-3: the drafts file and its summary ----------------------------------------------------------


def test_merge_keeps_an_answered_terms_description_only_in_case_the_word_is_asked_again(grouped, capsys, tmp_path, ticking):
    assert _said(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", WORD)[0] == 2
    out = tmp_path / "terms.json"
    assert cli.main(["bundle", "propose-terms", str(grouped), "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["fields"][0]["terms"][0]["draft"]["portal_payload"]["body"]["description"] = "ZZ synthetic description text"
    out.write_text(json.dumps(doc), encoding="utf-8")
    _out(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", "in_situ")
    capsys.readouterr()
    assert cli.main(["bundle", "propose-terms", str(grouped), "--out", str(out), "--merge"]) == 0
    said = capsys.readouterr().out
    assert ("1 description(s) of terms answered since kept only in case the scientist asks for the word again (not to "
            "be filed)") in said and "descriptions in the file were kept" not in said
    assert "a description in the file was kept" not in said
    merged = json.loads(out.read_text(encoding="utf-8"))
    d = _term(merged, ENV, WORD)["draft"]
    assert d["earlier_description"] == "ZZ synthetic description text" and d["description_note"] == P.ANSWERED_DESCRIPTION_NOTE
    assert "not to be filed" in d["description_note"] and "before it is filed" not in d["description_note"]
    assert merged["merges"][-1]["descriptions_kept"] == 0 and merged["merges"][-1]["descriptions_kept_for_answered_terms"] == 1


def test_the_out_summary_counts_terms_that_need_a_one_word_form(b, capsys, tmp_path):
    target = next(m for m in M.load(b)["missing_values"] if m["target_field_path"] == REACTION and m["run_id"])
    assert _said(b, capsys, "--target", target["value_id"], "--decision", "correct", "--value", "ZZ cathodic corrosion")[0] == 2
    capsys.readouterr()
    assert cli.main(["bundle", "propose-terms", str(b), "--out", str(tmp_path / "terms.json")]) == 0
    assert "1 term(s) need a one-word form (ask)." in capsys.readouterr().out
    report = json.loads((tmp_path / "terms.json").read_text(encoding="utf-8"))
    assert report["totals"]["need_one_word"] == 1 and _term(report, REACTION, "ZZ cathodic corrosion")["draft"]["ask"]


# --- LOW-2: a pending word that does not block export says so --------------------------------------------------


def test_pending_vocabulary_says_when_the_group_still_exports():
    bundle = {"vocabulary_requests": [{"request_id": "vr-00001", "field_path": CELL, "term": "ZZ_static_cell",
                                       "run_ids": ["run-1", "run-2"]}]}
    fresh = [("rg-a", {}, {"member_run_ids": ["run-1"], "filled": []}),
             ("rg-b", {}, {"member_run_ids": ["run-2"], "filled": []})]
    [row] = P.pending_vocabulary(bundle, fresh, {"rg-a": "exportable", "rg-b": "exportable"})
    assert row["groups_exportable"] == 2
    assert row["statement"].endswith("or an allowed value. This does not block export; the record is written without it.")
    [row] = P.pending_vocabulary(bundle, fresh, {"rg-a": "exportable", "rg-b": "incomplete"})
    assert row["statement"].endswith(" For 1 of these group(s) this does not block export; the record is written without it.")
    [row] = P.pending_vocabulary(bundle, fresh, {"rg-a": "incomplete", "rg-b": "incomplete"})
    assert row["groups_exportable"] == 0 and "block" not in row["statement"]
    [row] = P.pending_vocabulary(bundle, fresh)  # called without verdicts: as before
    assert "groups_exportable" not in row and "block" not in row["statement"]


def test_validate_passes_its_verdicts_to_pending_vocabulary(grouped, capsys):
    from isaac_api.local_import import bundle as B
    from isaac_api.local_import import records as R

    held = M.load(grouped)
    group = next(g for g in held["record_groups"] if g["status"] in B.LIVE_GROUP_STATUSES)
    assert _decide(grouped, capsys, "--target", group["group_id"], "--decision", "confirm")[0] == 0
    run_id = next(r["run_id"] for r in held["runs"] if r["run_key"] == group["member_run_keys"][0])
    assert _said(grouped, capsys, "--target", _vid(grouped, run_id, CELL), "--decision", "correct",
                 "--value", "ZZ_static_cell")[0] == 2
    out = R.validate_records(grouped, run_portal=lambda record: {
        "status": "ran", "result": {"valid": True, "errors": [], "warnings": []}, "outcome": "publish", "held": [],
        "verdict": "publish"})
    [row] = out["pending_vocabulary"]
    exportable = out["verdicts"][group["group_id"]] == "exportable"
    assert row["groups_exportable"] == int(exportable)
    assert ("This does not block export" in row["statement"]) is exportable


# --- the skill says it ------------------------------------------------------------------------------------------


def test_the_skill_reference_has_words_for_each_new_output():
    qd = (SKILL / "reference/questions-and-decisions.md").read_text(encoding="utf-8")
    rv = (SKILL / "reference/records-and-validation.md").read_text(encoding="utf-8")
    assert "the record keeps `surface_oxidation` meanwhile" in qd and "the field stays missing (`bundle validate`" in qd
    assert "earlier_requests_answered_note" in qd and "This answers your request for" in qd
    assert "already recorded: 'in_situ'" in qd and "nothing to do unless you want your own word kept" in qd
    assert "name only runs in no live record group" in qd and "need a one-word form (ask)" in qd
    assert "not to be filed" in qd and re.search(r"decision\(s\) \(from M cell\(s\)\) already\s+recorded", qd)
    assert "this does not block export; the record is\nwritten without it" in rv and "`pending_vocabulary`" in rv
    assert len((SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()) <= 250
