"""Polish c6-r: the review of c6-a on the local-first import. Synthetic only.

* (H1) A confirm question's text states every value ``confirm`` records, so ``bundle questions`` and ``bundle show
  question`` record an exposure for EVERY candidate whose value it prints — not only the hinted ones (hints are
  capped and one per literal) — as the web page does. A later ``annotate --blind`` is then never stored as blind.
* (M1) A read-only command (``bundle list`` / ``show`` / ``check``, the web page's reads) holds an older bundle's
  beamtime-wide notes value for review IN MEMORY, as ``mutations.load`` does, and writes nothing: the CLI and the
  web page give the same states and counts; the version stays the stored bytes' hash.
* (M2) A save that holds a value the STORED file gives as extracted logs each one in ``eligibility_rederived`` and
  says so in one stderr line; a later save logs nothing again.
* (L2) A field with no unit in its name is said with no unit unless it is known to carry none.
* (L3) A template reading of 0 / 0.0 is a value, not "no value".
* (L4) The answered counter question is worded from the regroup preview alone, computed only when its text is shown.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api import local_bundles as LB
from isaac_api.app import create_app
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import template as T

from test_local_import_polish_c5a import syn  # noqa: F401  (fixture)
from test_local_import_polish_c6a import (  # noqa: F401  (fixtures)
    CELL, SETPOINT, _as_an_older_build_stored_it, _group_of, noted_pristine, plain_pristine)

WHO = "Synthetic Scientist"
LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123), headers={LB.LOCAL_HEADER: "1"})


def _client(root: Path, monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(root))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    LB._check_memo.clear()
    return TestClient(create_app(), **LOCAL)


def _exposed(bdir: Path, command: str) -> set[str]:
    return {e["target"]["id"] for e in B.load_bundle(bdir).get("exposures") or ()
            if e["target"]["kind"] == "candidate" and e["command"] == command}


# --- H1: every value a confirm question states is an exposure ---------------------------------------------------


@pytest.fixture()
def nine(plain_pristine, tmp_path):
    """The synthetic corpus with every set-point run in ONE group: one confirm question, nine targets, six values
    (0.8 V for three of them, 1.0 V for two)."""
    root = tmp_path / "bundles"
    bdir = root / "nine"
    shutil.copytree(plain_pristine, bdir)
    b = B.load_bundle(bdir)
    sps = [c for c in b["candidates"] if c["target_field_path"] == SETPOINT and c["value"] is not None]
    group_of = _group_of(b)
    one = group_of[sps[0]["run_id"]]
    groups = {g["group_id"]: g for g in b["record_groups"]}
    for c in sps:
        key = next(r["run_key"] for r in b["runs"] if r["run_id"] == c["run_id"])
        if group_of[c["run_id"]] != one:
            groups[group_of[c["run_id"]]]["member_run_keys"].remove(key)
            groups[one]["member_run_keys"].append(key)
    assert B.validate_bundle(b) == []
    (bdir / B.BUNDLE_FILE).write_bytes(B.encode(b))
    return bdir


def _setpoint_question(bdir: Path) -> dict:
    (q,) = [q for q in Q.consolidate(M.load(bdir))["questions"]
            if q["kind"] == "confirm_value" and q["target_field_path"] == SETPOINT]
    return q


def test_the_nine_setpoint_question_states_values_its_hints_do_not_name(nine):
    q = _setpoint_question(nine)
    ids = {t["id"] for t in q["targets"]}
    assert len(ids) == 9
    for shown in ("`0.1` V", "`0.9` V", "`1.0` V", "`0.8` V (from: '800mV') for 3 target(s)", "for 2 target(s)"):
        assert shown in q["text"], q["text"]
    hinted = {h.get("candidate_id") for h in q["hints"]}
    assert ids - hinted  # what the exposures used to cover: the hints alone miss some printed values
    assert set(Q.confirm_value_shown(M.load(nine), q)) == ids


def test_bundle_questions_records_every_value_the_confirm_text_states(nine, capsys):
    q = _setpoint_question(nine)
    ids = {t["id"] for t in q["targets"]}
    assert cli.main(["bundle", "questions", str(nine), "--limit", str(cli.MAX_LIMIT)]) == 0
    page = json.loads(capsys.readouterr().out)
    assert q["question_id"] in {x["question_id"] for x in page["questions"]}
    assert ids <= _exposed(nine, "bundle questions")  # 0.9 V and 1.0 V, and each target sharing 0.8 V or 1.0 V
    # a later blind reading of a value the text showed is not stored as blind
    b = M.load(nine)
    c = next(c for c in b["candidates"] if c["candidate_id"] in ids and c["value"] == 1.0
             and c["candidate_id"] not in {h.get("candidate_id") for h in q["hints"]})
    src = next(e["source_id"] for e in c["evidence"] if e["method"] != "ai_interpretation")
    M.annotate(nine, target_id=c["candidate_id"], value="1.0", excerpt_locator=None, source_id=src, model_id="m",
               blind=True, rationale="")
    reading = M.load(nine)["ai_interpretations"][-1]
    assert reading["blind"] is False and "bundle questions" in reading["blind_basis"]


def test_bundle_show_question_records_every_value_the_confirm_text_states(nine, capsys):
    q = _setpoint_question(nine)
    ids = {t["id"] for t in q["targets"]}
    assert cli.main(["bundle", "show", str(nine), "question", q["question_id"]]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert "`0.9` V" in shown["text"] and "`1.0` V" in shown["text"]
    assert ids <= _exposed(nine, "bundle show question")


def test_the_web_page_records_the_same_confirm_text_exposures(nine, tmp_path, monkeypatch):
    q = _setpoint_question(nine)
    ids = {t["id"] for t in q["targets"]}
    client = _client(nine.parent, monkeypatch, tmp_path)
    r = client.get("/api/local-bundles/nine/questions")
    assert r.status_code == 200
    assert q["question_id"] in {x["question_id"] for x in r.json()["questions"]}
    assert ids <= _exposed(nine, "bundle questions")


def test_a_question_that_offers_no_confirm_records_no_value_from_its_text(plain_pristine):
    b = B.load_bundle(plain_pristine)
    for q in Q.consolidate(b)["questions"]:
        if q["kind"] != "confirm_value" or "confirm" not in q["allowed_decisions"]:
            assert Q.confirm_value_shown(b, q) == []


# --- M1 / M2: an older bundle, read and written -------------------------------------------------------------------


@pytest.fixture()
def older(noted_pristine, tmp_path):
    """A bundle as the build before c6-a stored it: the beamtime-wide notes value silently extracted."""
    bdir = tmp_path / "bundles" / "older"
    shutil.copytree(noted_pristine, bdir)
    old = _as_an_older_build_stored_it(B.load_bundle(bdir))
    (bdir / B.BUNDLE_FILE).write_bytes(B.encode(old))
    return bdir


def _held_ids(bdir: Path) -> set[str]:
    return {c["candidate_id"] for c in B.load_bundle(bdir)["candidates"]
            if c["extracted_state"] == "candidate_extracted" and B.beamtime_wide_statement(c)}


def _listed(capsys, bdir: Path, state: str) -> set[str]:
    assert cli.main(["bundle", "list", str(bdir), "candidates", "--state", state, "--no-values",
                     "--limit", str(cli.MAX_LIMIT)]) == 0
    return {row["candidate_id"] for row in json.loads(capsys.readouterr().out)["items"]}


def test_read_only_commands_hold_an_older_bundle_in_memory_and_write_nothing(older, capsys):
    held = _held_ids(older)
    assert held
    capsys.readouterr()
    extracted = _listed(capsys, older, "candidate_extracted")
    assert extracted and not extracted & held
    assert held <= _listed(capsys, older, "needs_review")
    assert cli.main(["bundle", "check", str(older)]) == 0
    out = capsys.readouterr().out
    loaded = M.load(older)
    assert f"needs_review {loaded['counts']['needs_review']}" in out
    assert B.held_statement(len(held)) in out and "nothing is written" in out
    cid = sorted(held)[0]
    assert cli.main(["bundle", "show", str(older), "candidate", cid]) == 0  # prints a value: an exposure is written
    shown = json.loads(capsys.readouterr().out)
    assert (shown["extracted_state"], shown["value_state"]) == ("needs_review", "needs_review")
    assert shown["state_basis"]["not_proposable_reason"] == B.BEAMTIME_WIDE_REASON


def test_list_and_check_write_nothing(older, capsys):
    v0 = M.bundle_version(older)
    _listed(capsys, older, "candidate_extracted")
    assert cli.main(["bundle", "check", str(older)]) == 0
    capsys.readouterr()
    assert M.bundle_version(older) == v0


def test_the_cli_and_the_web_page_agree_on_an_older_bundle(older, tmp_path, monkeypatch, capsys):
    held = _held_ids(older)
    v0 = M.bundle_version(older)
    loaded = M.load(older)
    assert B.validate_bundle(loaded) == []  # the in-memory hold moves the counts with the states
    assert loaded["counts"]["candidate_extracted"] == sum(c["value_state"] == "candidate_extracted" for c in loaded["candidates"])
    capsys.readouterr()
    cli_extracted = _listed(capsys, older, "candidate_extracted")
    client = _client(older.parent, monkeypatch, tmp_path)
    prog = client.get("/api/local-bundles/older/progress").json()
    assert prog["progress"]["check"]["status"] == "VALID"
    # c7-r MED-4: the one write a progress read makes is the exposures of the values its minimum's warnings state
    shown = prog["progress"]["exposures_recorded"]
    assert prog["bundle"]["bundle_version"] == (M.bundle_version(older) if shown else v0)
    v0 = prog["bundle"]["bundle_version"]
    values = prog["progress"]["values"]
    assert values["candidate_extracted"] == len(cli_extracted) == loaded["counts"]["candidate_extracted"]
    assert values["needs_review"] == loaded["counts"]["needs_review"]
    assert prog["progress"]["questions"] == Q.consolidate(loaded)["counts"]
    listing = next(b for b in client.get("/api/local-bundles").json()["bundles"] if b["name"] == "older")
    assert listing["counts"]["needs_review"] == loaded["counts"]["needs_review"]
    assert listing["readiness"]["blocking"]["needs_review"] == loaded["readiness"]["blocking"]["needs_review"]
    assert M.bundle_version(older) == v0  # the reads wrote nothing more
    page = client.get("/api/local-bundles/older/questions").json()
    assert {q["question_id"] for q in page["questions"]} == {q["question_id"] for q in Q.consolidate(loaded)["questions"]}
    assert held  # the held candidates are asked about on both
    asked = {t["id"] for q in page["questions"] if q["kind"] == "confirm_value" and q["target_field_path"] == CELL
             for t in q["targets"]}
    assert held <= asked


def test_a_save_that_holds_a_stored_extracted_value_logs_each_and_says_so_once(older, capsys):
    held = _held_ids(older)
    capsys.readouterr()
    M.mutate(older, lambda b: None)
    err = capsys.readouterr().err
    assert err.count(B.held_statement(len(held))) == 1, err
    stored = B.load_bundle(older)
    assert B.validate_bundle(stored) == []
    log = [r for r in stored.get("eligibility_rederived") or () if r["reason"] == B.BEAMTIME_WIDE_REDERIVED_REASON]
    assert {r["id"] for r in log} == held
    for r in log:
        assert (r["kind"], r["value_state"], r["eligible_before"], r["eligible_now"]) == ("candidate", "needs_review", False, False)
        assert r["target_field_path"] == CELL
    assert all(c["extracted_state"] == "needs_review" for c in stored["candidates"] if c["candidate_id"] in held)
    # held now as stored: a later save logs and says nothing
    M.mutate(older, lambda b: None)
    assert B.held_statement(len(held)) not in capsys.readouterr().err
    assert len(B.load_bundle(older)["eligibility_rederived"]) == len(stored["eligibility_rederived"])


def test_a_fresh_import_holds_without_a_log(noted_pristine, tmp_path, capsys):
    bdir = tmp_path / "fresh"
    shutil.copytree(noted_pristine, bdir)
    capsys.readouterr()
    M.mutate(bdir, lambda b: None)
    assert "beamtime-wide" not in capsys.readouterr().err
    assert not [r for r in B.load_bundle(bdir).get("eligibility_rederived") or ()
                if r["reason"] == B.BEAMTIME_WIDE_REDERIVED_REASON]


# --- L2: a unit only where the record carries it -------------------------------------------------------------------


def test_a_field_with_no_unit_in_its_name_is_said_without_the_readings_unit():
    reading = {"evidence": [{"normalization": [{"step": "normalize", "unit": "wt%"}]}]}
    assert Q._unit_of("sample.composition.mass_fraction", reading) is None
    assert "`12.5` wt%" not in Q._confirmed_value_text("sample.composition.mass_fraction",
                                                [{"value": 12.5, "observed_literals": ["12.5 wt%"], **reading}])
    assert Q._unit_of(SETPOINT, reading) == "V"  # the name fixes it
    assert Q._unit_of("context.electrochemistry.pH", {"evidence": []}) is None


# --- L3: zero is a value ------------------------------------------------------------------------------------------------


def test_a_zero_reading_is_compared_as_a_value():
    ad = T._Adopter.__new__(T._Adopter)
    ad.rules = {"x.numeric": {"numeric": True}}
    # '0' and 0.0 compare as one value; before, 0.0 counted as "no value" and the two were two
    assert T._compared_values(ad, [{"value": 0.0}, {"value": "0"}], "x.numeric") == ("0.0",)
    assert T._compared_values(ad, [{"value": 0}, {"value": "n/a"}], "x.numeric") == ("'n/a'", "0")


# --- L4: the answered counter question --------------------------------------------------------------------------------


@pytest.fixture()
def counter_answered(syn):
    """An answer given straight to `decide` (the grouping step never asked), with no regroup since (polish c6-l)."""
    bdir = syn
    b = M.load(bdir)
    b["grouping_questions"] = [g for g in b.get("grouping_questions") or () if g.get("kind") != "naming_counter_positions"]
    M.save_bundle(bdir, b)
    M.decide(bdir, target_ids=["experiment"], decision="set_counter_positions", value=None, by=WHO, orcid=None, positions=[2])
    return bdir


def _counter(payload):
    (q,) = [q for q in payload["questions"] if q["question_id"] == Q.COUNTER_QUESTION_ID]
    return q


def test_the_answered_counter_question_is_worded_from_the_preview_only(counter_answered, monkeypatch):
    b = M.load(counter_answered)
    text = _counter(Q.consolidate(b, include_answered=True))["text"]
    assert "not applied yet" in text and "no regroup has run" not in text and "did not ask" not in text
    assert M.counter_answer_preview(b)["statement"] in text
    # resolving targets alone never runs the preview (it proposes every group again)
    calls = []
    real = M.counter_answer_preview
    monkeypatch.setattr(M, "counter_answer_preview", lambda bundle: calls.append(1) or real(bundle))
    plain = _counter(Q.consolidate(b, include_answered=True, explain_counter=False))
    assert not calls and "counters? (Answered.)" in plain["text"]
    assert plain["targets"] == _counter(Q.consolidate(b, include_answered=True))["targets"]
    assert calls  # ...and shows it when the text is asked for
    calls.clear()
    Q.answered_question(b, "Q-0000000000")
    assert not calls  # another question's lookup does not
    seen = Q.answered_question(b, Q.COUNTER_QUESTION_ID)
    assert calls and "not applied yet" in seen["text"]

