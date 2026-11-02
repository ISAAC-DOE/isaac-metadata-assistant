"""c14g: a review of c14f's vocabulary-request wording. Synthetic only (SYN_/ZZ words).

* LOW-1: ``earlier_requests_answered_note`` names requests by what they are (open, answered since), never "new" and
  "earlier": the open one may be the older.
* LOW-2: ``decide``'s "still drafted" sentence reads ``propose-terms``' own report for the term (its readings counted
  as it counts them; a term it never drafts is "not drafted").
* LOW-3: a request whose runs are all in no live record group never makes an answered term count less.
"""

from __future__ import annotations

import json
from pathlib import Path

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

from test_local_import_vocabulary_requests import (  # noqa: F401  (fixtures)
    ENV, WHO, _env_sheet, _miss_of, _report, _said, _term, b, grouped, grouped_base, pristine_bundle, ticking)

WORD = "aqueous_electrochemistry"


def _vid(bdir: Path, run_id: str) -> str:
    return _miss_of(bdir, ENV, run_id)["value_id"]


def _out(bdir: Path, capsys, *args: str) -> dict:
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(bdir), *args, "--by", WHO]) == 0
    return json.loads(capsys.readouterr().out)


def _reading(bdir: Path, run_id: str, word: str) -> None:
    """An AI reading of ``word`` for one run's environment, which no scientist has answered."""
    assert cli.main(["bundle", "annotate", str(bdir), "--target", _vid(bdir, run_id), "--value", word,
                     "--model", "synthetic-test-model", "--excerpt-locator", "page 1 (synthetic)",
                     "--rationale", "synthetic test reading"]) == 0


def test_an_older_open_request_and_a_newer_answered_one_are_named_by_what_they_are(grouped, capsys, tmp_path, ticking):
    _env_sheet(grouped, tmp_path)  # vr-00001 on run-001 and run-002, never answered
    assert _said(grouped, capsys, "--target", _vid(grouped, "run-003"), "--decision", "correct", "--value", WORD)[0] == 0
    reply = _out(grouped, capsys, "--target", _vid(grouped, "run-003"), "--decision", "correct", "--value", "in_situ")
    assert (f"This answers your request for '{WORD}' (vr-00002); your other request(s) for it (vr-00001) are still "
            "drafted.") in reply["statement"]
    t = _term(_report(grouped, capsys), ENV, WORD)
    assert t["run_ids"] == ["run-001", "run-002"] and t["count"] == 1
    assert t["draft"]["earlier_requests_answered_note"] == (
        "The open request (vr-00001) is for 2 run(s); the request answered since (vr-00002, from an answer to isaac "
        "bundle decide, 1 run(s)) is not part of this draft.")
    assert "new request" not in t["draft"]["earlier_requests_answered_note"]


def test_decide_says_the_word_is_still_drafted_for_the_readings_propose_terms_counts(grouped, capsys, ticking):
    _reading(grouped, "run-002", WORD)
    assert _said(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", WORD)[0] == 0
    reply = _out(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", "in_situ")
    t = _term(_report(grouped, capsys), ENV, WORD)
    assert t["draft"]["drafted"] is True and t["by_origin"]["ai_reading"] == 1
    assert (f"This answers your request for '{WORD}' (vr-00001); it is still drafted for 1 reading(s) no scientist "
            "confirmed.") in reply["statement"]


def test_decide_never_says_drafted_for_a_term_propose_terms_does_not_draft(grouped, capsys, ticking):
    word = "ZZ aqueous phase"  # a space: the website refuses it as a term, so it is never drafted
    _reading(grouped, "run-002", word)
    assert _said(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", word)[0] == 0
    reply = _out(grouped, capsys, "--target", _vid(grouped, "run-001"), "--decision", "correct", "--value", "in_situ")
    draft = _term(_report(grouped, capsys), ENV, word)["draft"]
    assert draft["drafted"] is False and draft.get("answered") is not True and draft["ask"]
    assert f"This answers your request for '{word}' (vr-00001); it is not drafted." in reply["statement"]
    assert "still drafted" not in reply["statement"]


def test_a_request_in_no_live_group_never_shrinks_an_answered_terms_counts(grouped, capsys, tmp_path, ticking):
    _env_sheet(grouped, tmp_path)  # vr-00001 on run-001 and run-002
    for rid in ("run-001", "run-002"):
        _out(grouped, capsys, "--target", _vid(grouped, rid), "--decision", "correct", "--value", "in_situ")
    held = M.load(grouped)
    key_of = {r["run_id"]: r["run_key"] for r in held["runs"]}
    group = next(g for g in held["record_groups"] if g["status"] in B.LIVE_GROUP_STATUSES
                 and not {key_of["run-001"], key_of["run-002"]} & set(g["member_run_keys"]))
    gone = next(rid for rid, k in key_of.items() if k in group["member_run_keys"])
    M.keep_vocabulary_request(held, field_path=ENV, term=WORD, by=WHO, run_ids=[gone],
                              source={"kind": "decide_answer", "command": "bundle decide", "as_said": True})
    M.save_bundle(grouped, held)
    M.decide(grouped, target_ids=[group["group_id"]], decision="reject", value=None, by=WHO, orcid=None)
    t = _term(_report(grouped, capsys), ENV, WORD)
    d = t["draft"]
    assert d["answered"] is True and d["drafted"] is False and d["runs_in_no_live_group"] == 1
    assert t["count"] == 2 and t["run_ids"] == sorted(["run-001", "run-002", gone])  # all of it, as answered terms keep
    assert "answered_requests_apart" not in t
