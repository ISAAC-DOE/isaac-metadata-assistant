"""Earlier answers (``answer_memory``): what a scientist confirmed on an EARLIER beamtime, offered as a hint on a new one.

Pinned:
* OPT-IN: with the memory off nothing is written (no file), nothing is suggested and ``learn`` is refused.
* The round trip across two synthetic beamtimes: an answer on A is a hint beside B's matching question, in the
  suggestions' hint style; confirming it records a normal decision by the person answering now, whose note says it
  was confirmed from the earlier answer.
* Scope: a sample fact never crosses to another sample, and only when a research group or organization is confirmed
  on BOTH beamtimes and equal; a beamline fact never to another beamline (``BL11-2`` is never ``BL1-12``, an
  ambiguous ``BL152`` matches nothing); a people fact only within the same organization or group; a key the new
  bundle does not hold yet is no match.
* WHEN: only decisions a write ADDS while the memory is on are stored (never one recorded before opt-in, never by a
  dry run or a preview); a forgotten entry or beamtime is not re-learned from the bundle's existing decisions;
  ``learn`` (the scientist's explicit yes, ``--by``) is the one way to remember earlier decisions. Workbook and
  template imports applied while on are remembered, as the skill docs say.
* An unreadable memory file is removed by ``forget --all`` (and only that file at the configured path).
* An earlier answer shown is recorded in the bundle's ``exposures`` log, as the parser values a page shows are.
* The top-level ``isaac`` entry point dispatches ``answer-memory``.
* Disagreeing earlier answers are all shown and said to disagree.
* ``defer`` ("I don't know"), ``reject`` and unconfirmed parser values are never stored; a withdrawn answer is
  forgotten when the bundle is learned again.
* The hint is additive: question ids, counts, blocking, hints and text are unchanged, and it never sets a value.
* The file lives outside the repository and every bundle; a test never reaches the real ``~/.isaac``.

SYNTHETIC ``SYN_`` / ``ZZ`` files only (the repository's multi-operator semantics corpus).
"""

from __future__ import annotations

import hashlib
import io
import json
import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl

import pytest
from fastapi.testclient import TestClient

from isaac_api import local_bundles as LB
from isaac_api.app import create_app
from isaac_api.local_import import answer_memory as AM
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from tests_support_records import SEMANTICS

ANGEL = "SYN Angel"
BOB = "SYN Bob"
NOW = "SYN Scientist"
FORM = "sample.sample_form"
GROUP = "attribution.produced_by.group"
LAB = "SYN Lab"
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def _vendored_schema_basis(tmp_path_factory):
    """The vendored schema basis (no portal validator), as CI runs, so the question set is the one pinned here."""
    d = tmp_path_factory.mktemp("no-validator")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(d))
        mp.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(d / "python"))
        yield


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Three synthetic beamtimes of the same corpus, each its own import (its own bundle id). Folder names carry no
    ``BL`` token, so the SPEC header fingerprint (SSRL BL15-2) is undisputed."""
    root = tmp_path_factory.mktemp("am")
    out = {}
    for name in ("SYN_2100-01_Alpha", "SYN_2100-02_Beta", "SYN_2100-03_Gamma"):
        src = root / "src" / name
        shutil.copytree(SEMANTICS, src)
        b = root / "built" / name
        with contextlib.redirect_stdout(io.StringIO()):
            assert cli.main(["import", str(src), "--out", str(b)]) == 0
        M.group(b)
        out[name] = b
    return out


@pytest.fixture()
def bundles(built, tmp_path):
    return {k[len("SYN_2100-0x_"):].lower(): shutil.copytree(v, tmp_path / "work" / v.name) for k, v in built.items()}


@pytest.fixture()
def memory(tmp_path, monkeypatch):
    path = tmp_path / "home" / ".isaac" / "answer-memory.json"
    monkeypatch.setenv(AM.MEMORY_ENV, str(path))
    return path


def _cli(argv, capsys=None):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main([str(a) for a in argv])
    text = buf.getvalue()
    return code, (json.loads(text) if text.strip().startswith("{") else text)


def _sample_of(bdir: Path, q) -> str | None:
    ctx = AM.Context(M.load(bdir))
    kind = {t["id"]: t["kind"] for t in q["targets"]}
    ids = {json.dumps(ctx.sample_of_run(r)) for t in kind for r in ctx.runs_of_target(kind[t], t)}
    return json.loads(ids.pop())["sample_name"] if len(ids) == 1 else None


def _form_q(bdir: Path, sample: str):
    return next(q for q in Q.consolidate(M.load(bdir))["questions"]
                if q.get("target_field_path") == FORM and _sample_of(bdir, q) == sample)


def _qid(bdir, path):
    return next(q["question_id"] for q in Q.consolidate(M.load(bdir))["questions"] if q.get("target_field_path") == path)


def _facility_qid(bdir):
    return next(q["question_id"] for q in Q.consolidate(M.load(bdir))["questions"]
                if q["kind"] == "optional_values" and "system.facility.beamline" in (q.get("fields") or {}))


def _answer(bdir, qid, value, by, *extra):
    code, out = _cli(["bundle", "decide", bdir, "--question", qid, "--decision", "correct", "--value", value, "--by", by,
                      *extra])
    assert code == 0, out
    return out


def _page(bdir) -> dict:
    code, out = _cli(["bundle", "questions", bdir, "--limit", "200", "--with-targets"])
    assert code == 0
    return out


def _earlier(page: dict, qid: str) -> list[dict]:
    return next(q for q in page["questions"] if q["question_id"] == qid).get("earlier_answers") or []


def _on(by=ANGEL):
    code, out = _cli(["answer-memory", "on", "--by", by])
    assert code == 0, out
    return out


def _group(bdir, name=LAB, by=ANGEL):
    """The beamtime's research group: a sample fact is offered only when one is confirmed on BOTH beamtimes."""
    return _answer(bdir, _qid(bdir, GROUP), name, by)


def _entries(memory, field=None) -> list[dict]:
    if not memory.exists():
        return []
    return [e for e in json.loads(memory.read_text())["entries"] if field is None or e["field"] == field]


# --- opt-in ---------------------------------------------------------------------------------------------------------

def test_off_by_default_writes_nothing_and_suggests_nothing(bundles, memory):
    a, b = bundles["alpha"], bundles["beta"]
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    assert not memory.exists() and not memory.parent.exists()
    code, out = _cli(["answer-memory", "status"])
    assert code == 0 and out["enabled"] is False and out["file_exists"] is False
    # off with no file writes nothing; learn is refused while off
    assert _cli(["answer-memory", "off"])[0] == 0 and not memory.exists()
    assert _cli(["answer-memory", "learn", a, "--by", ANGEL])[0] == 2 and not memory.exists()
    page = _page(b)
    assert not any("earlier_answers" in q for q in page["questions"])
    assert "earlier_answers" not in json.dumps(page["minimum_for_one_group"])


def test_turning_it_on_needs_a_name_and_off_stops_writing_and_suggesting(bundles, memory):
    assert _cli(["answer-memory", "on", "--by", " "])[0] == 2 and not memory.exists()
    _on()
    a, b = bundles["alpha"], bundles["beta"]
    _group(a)
    _group(b, by=NOW)
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    assert _cli(["answer-memory", "list", "--field", FORM])[1]["total"] == 1
    assert _earlier(_page(b), _form_q(b, "zz1")["question_id"])  # shown while on
    assert _cli(["answer-memory", "off"])[0] == 0
    _answer(a, _form_q(a, "zz2")["question_id"], "powder", ANGEL)
    assert _cli(["answer-memory", "list", "--field", FORM])[1]["total"] == 1  # nothing new while off
    assert not _earlier(_page(b), _form_q(b, "zz1")["question_id"])  # and nothing shown


def test_the_file_never_lives_in_the_repository_or_a_bundle_and_a_test_never_reaches_home(bundles, monkeypatch,
                                                                                            tmp_path):
    monkeypatch.setenv(AM.MEMORY_ENV, str(ROOT / "answer-memory.json"))
    code, _ = _cli(["answer-memory", "on", "--by", ANGEL])
    assert code == 2 and not (ROOT / "answer-memory.json").exists()
    monkeypatch.setenv(AM.MEMORY_ENV, str(bundles["alpha"] / "notes" / "answer-memory.json"))
    assert _cli(["answer-memory", "on", "--by", ANGEL])[0] == 2
    assert not (bundles["alpha"] / "notes").exists()
    # under pytest without the variable the memory is off: nothing read or written in the real home folder
    monkeypatch.delenv(AM.MEMORY_ENV)
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    assert AM.memory_path() is None and AM.is_enabled() is False
    assert _cli(["answer-memory", "on", "--by", ANGEL])[0] == 2
    assert not (tmp_path / "fake-home").exists()


# --- the round trip -------------------------------------------------------------------------------------------------

def test_round_trip_across_two_beamtimes(bundles, memory):
    a, b = bundles["alpha"], bundles["beta"]
    _on()
    _group(a)
    _group(b, by=NOW)
    out = _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    assert out["answer_memory"]["remembered"] == 1
    (entry,) = _entries(memory, FORM)
    assert {k: entry[k] for k in ("field", "value", "by", "beamtime", "scope_class", "scope")} == {
        "field": FORM, "value": "pellet", "by": ANGEL, "beamtime": "SYN_2100-01_Alpha", "scope_class": "sample",
        "scope": {"sample": {"sample_name": "zz1"}, "research_group": LAB}}
    assert "/" not in entry["beamtime"] and str(a) not in memory.read_text()  # a folder NAME, never a path

    page = _page(b)
    qid = _form_q(b, "zz1")["question_id"]
    (hint,) = _earlier(page, qid)
    assert hint["kind"] == "earlier_answer" and hint["literal"] == "pellet" and hint["entry_id"] == entry["entry_id"]
    assert hint["said"].startswith(f"Earlier answer: pellet — {ANGEL}, ")
    assert hint["said"].endswith(f"beamtime SYN_2100-01_Alpha (same sample zz1, research group {LAB})")
    assert hint["disagrees"] is False
    q = next(x for x in page["questions"] if x["question_id"] == qid)
    assert "A hint, never an answer" in q["earlier_answers_statement"]
    # the minimum for one group names it too, beside the question it answers
    assert "earlier_answer" in json.dumps(page["minimum_for_one_group"])

    # the person answering now confirms it: their own decision, with where it came from in the note
    before = len(M.load(b)["scientist_decisions"])
    out = _answer(b, qid, "pellet", NOW, "--from-earlier-answer", entry["entry_id"])
    bundle = M.load(b)
    new = bundle["scientist_decisions"][before:]
    assert new and all(d["decided_by"]["name"] == NOW and d["value"] == "pellet" and d["decision"] == "correct"
                       for d in new)
    assert all(d["note"].startswith(AM.PROVENANCE_PREFIX + f" ({entry['entry_id']})") and ANGEL in d["note"]
               for d in new)
    # ...and is remembered as B's own answer too
    assert {e["beamtime"] for e in _entries(memory, FORM)} == {"SYN_2100-01_Alpha", "SYN_2100-02_Beta"}


def test_confirming_from_an_earlier_answer_is_refused_for_another_value_or_field(bundles, memory):
    a, b = bundles["alpha"], bundles["beta"]
    _on()
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    entry_id = _entries(memory, FORM)[0]["entry_id"]
    before = len(M.load(b)["scientist_decisions"])
    qid = _form_q(b, "zz1")["question_id"]
    code, _ = _cli(["bundle", "decide", b, "--question", qid, "--decision", "correct", "--value", "powder",
                    "--by", NOW, "--from-earlier-answer", entry_id])
    assert code == 2
    code, _ = _cli(["bundle", "decide", b, "--question", _qid(b, "attribution.produced_by.group"), "--decision",
                    "correct", "--value", "pellet", "--by", NOW, "--from-earlier-answer", entry_id])
    assert code == 2
    code, _ = _cli(["bundle", "decide", b, "--question", qid, "--decision", "correct", "--value", "pellet",
                    "--by", NOW, "--from-earlier-answer", "am-000000000000"])
    assert code == 2
    assert len(M.load(b)["scientist_decisions"]) == before


# --- scope ---------------------------------------------------------------------------------------------------------

def test_a_sample_fact_never_crosses_to_another_sample(bundles, memory):
    a, b = bundles["alpha"], bundles["beta"]
    _on()
    _group(a)
    _group(b, by=NOW)
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    page = _page(b)
    assert _earlier(page, _form_q(b, "zz1")["question_id"])
    for other in ("zz2", "zz3"):
        assert not _earlier(page, _form_q(b, other)["question_id"])
    # every hint on the page is for the one sample answered
    assert {h["matched_on"] for q in page["questions"] for h in q.get("earlier_answers") or ()} == {
        f"same sample zz1, research group {LAB}"}


def test_a_sample_fact_is_not_offered_to_another_research_group(bundles, memory):
    a, b = bundles["alpha"], bundles["beta"]
    _on()
    _answer(a, _qid(a, "attribution.produced_by.group"), "SYN Lab A", ANGEL)
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    _answer(b, _qid(b, "attribution.produced_by.group"), "SYN Lab B", NOW)
    assert not _earlier(_page(b), _form_q(b, "zz1")["question_id"])


def test_a_beamline_fact_never_crosses_to_another_beamline(bundles, memory):
    a, b, c = bundles["alpha"], bundles["beta"], bundles["gamma"]
    _on()
    fq = _facility_qid(a)
    _answer(a, fq, "SSRL", ANGEL, "--field", "system.facility.facility_name")
    _answer(a, fq, "BL15-2", ANGEL, "--field", "system.facility.beamline")
    _answer(a, fq, "SYN endstation 1", ANGEL, "--field", "system.facility.endstation")
    code, out = _cli(["bundle", "decide", a, "--target", "experiment", "--decision", "set_clock_time_zone",
                      "--value", "America/Los_Angeles", "--by", ANGEL])
    assert code == 0, out
    fields = {e["field"]: e for e in json.loads(memory.read_text())["entries"]}
    assert fields["system.facility.endstation"]["scope"] == {"beamline": {"facility": "SSRL", "beamline": "BL15-2"}}
    assert fields[AM.CLOCK_ZONE_FIELD]["value"] == "America/Los_Angeles"
    # the facility and beamline themselves are keyed by the SPEC headers' fingerprint
    assert fields["system.facility.beamline"]["scope_class"] == "spec_fingerprint"

    # B: nothing confirmed yet: the fingerprint matches, so facility and beamline are hinted; the endstation is not
    # (each question's id is read once: an answered field leaves it, its id stays)
    fq_b, fq_c = _facility_qid(b), _facility_qid(c)

    def field_hints(bdir, qid):
        q = next((x for x in _page(bdir)["questions"] if x["question_id"] == qid), {})
        return {h["field"]: h["literal"] for h in q.get("earlier_answers") or ()}

    assert field_hints(b, fq_b) == {"system.facility.facility_name": "SSRL", "system.facility.beamline": "BL15-2"}
    # B confirms ANOTHER beamline: the endstation and the clock zone of BL15-2 are never offered
    _answer(b, fq_b, "SSRL", NOW, "--field", "system.facility.facility_name")
    _answer(b, fq_b, "BL4-3", NOW, "--field", "system.facility.beamline")
    assert field_hints(b, fq_b) == {}
    entries = json.loads(memory.read_text())["entries"]
    assert not AM.earlier_answers_for(entries, AM.Context(M.load(b)), AM.CLOCK_ZONE_FIELD, None)
    # C confirms the same one, written differently ("15-2"): both are offered
    _answer(c, fq_c, "SSRL", NOW, "--field", "system.facility.facility_name")
    _answer(c, fq_c, "15-2", NOW, "--field", "system.facility.beamline")
    assert field_hints(c, fq_c) == {"system.facility.endstation": "SYN endstation 1"}
    entries = json.loads(memory.read_text())["entries"]
    (zone,) = AM.earlier_answers_for(entries, AM.Context(M.load(c)), AM.CLOCK_ZONE_FIELD, None)
    assert zone["literal"] == "America/Los_Angeles" and zone["matched_on"] == "same beamline SSRL BL15-2"


def test_people_facts_match_only_the_same_organization_or_group(bundles, memory):
    a, b, c = bundles["alpha"], bundles["beta"], bundles["gamma"]
    _on()
    _answer(a, _qid(a, "attribution.produced_by.organization"), "SYN University", ANGEL)
    _answer(a, _qid(a, "attribution.produced_by.group"), "SYN Lab", ANGEL)
    group_q, org_q = _qid(b, "attribution.produced_by.group"), _qid(b, "attribution.produced_by.organization")
    # nothing recorded in B yet: no key to match on, so no hint (never a guess from another group)
    page = _page(b)
    assert not _earlier(page, group_q) and not _earlier(page, org_q)
    _answer(b, org_q, "SYN University", NOW)
    assert [h["literal"] for h in _earlier(_page(b), group_q)] == ["SYN Lab"]
    _answer(c, _qid(c, "attribution.produced_by.organization"), "SYN Other Institute", NOW)
    assert not _earlier(_page(c), _qid(c, "attribution.produced_by.group"))


def test_disagreeing_earlier_answers_are_all_shown_and_said_to_disagree(bundles, memory):
    a, b, c = bundles["alpha"], bundles["beta"], bundles["gamma"]
    _on()
    for bdir, who in ((a, ANGEL), (b, NOW), (c, BOB)):
        _group(bdir, by=who)
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    _answer(c, _form_q(c, "zz1")["question_id"], "powder", BOB)
    page = _page(b)
    qid = _form_q(b, "zz1")["question_id"]
    hints = _earlier(page, qid)
    assert sorted(h["literal"] for h in hints) == ["pellet", "powder"]
    assert all(h["disagrees"] for h in hints)
    statement = next(q for q in page["questions"] if q["question_id"] == qid)["earlier_answers_statement"]
    assert statement.startswith(f"Earlier answers disagree for {FORM}: ") and AM.DISAGREE_NOTE in statement


# --- what is never stored ------------------------------------------------------------------------------------------

def test_rejects_dont_knows_and_unconfirmed_values_are_never_stored(bundles, memory):
    a = bundles["alpha"]
    _on()
    for sample, decision in (("zz2", "defer"), ("zz3", "reject")):
        code, out = _cli(["bundle", "decide", a, "--question", _form_q(a, sample)["question_id"], "--decision", decision,
                          "--by", ANGEL])
        assert code == 0, out
    assert _entries(memory) == []
    # a parser value no person confirmed is never an entry, whatever the bundle holds
    assert all(e["decision"] in ("confirm", "correct", "set_clock_time_zone") for e in AM.entries_from_bundle(M.load(a)))
    assert AM.entries_from_bundle(M.load(a)) == []
    # an answer later withdrawn ("I don't know") is forgotten when the bundle is learned again
    qid = _form_q(a, "zz1")["question_id"]
    _answer(a, qid, "pellet", ANGEL)
    assert len(_entries(memory)) == 1
    assert _cli(["bundle", "decide", a, "--question", qid, "--decision", "defer", "--by", ANGEL])[0] == 0
    assert _entries(memory) == []


def test_list_and_forget(bundles, memory):
    a = bundles["alpha"]
    _on()
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    _answer(a, _form_q(a, "zz2")["question_id"], "powder", ANGEL)
    listed = _cli(["answer-memory", "list", "--field", FORM])[1]
    assert listed["total"] == 2 and all(e["said"].startswith("Earlier answer: ") for e in listed["entries"])
    first = listed["entries"][0]["entry_id"]
    assert _cli(["answer-memory", "forget", "--entry", first])[1]["forgotten"] == 1
    assert _cli(["answer-memory", "forget", "--entry", first])[0] == 2  # gone
    assert _cli(["answer-memory", "forget", "--beamtime", "SYN_2100-01_Alpha"])[1]["entries"] == 0
    assert _cli(["answer-memory", "forget"])[0] == 2  # names nothing
    assert _cli(["answer-memory", "status"])[1]["enabled"] is True  # forgetting keeps the setting


# --- additive, never a value ---------------------------------------------------------------------------------------

def _without_hint(q: dict) -> dict:
    return {k: v for k, v in q.items() if k not in ("earlier_answers", "earlier_answers_statement")}


def test_ids_counts_blocking_and_text_are_unchanged_with_the_memory_present(bundles, memory):
    a, b = bundles["alpha"], bundles["beta"]
    _group(b, by=NOW)  # B's group, recorded while the memory is off
    plain = _page(b)
    _on()
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    _group(a)
    hinted = _page(b)
    assert any(q.get("earlier_answers") for q in hinted["questions"])
    assert [q["question_id"] for q in hinted["questions"]] == [q["question_id"] for q in plain["questions"]]
    for key in ("counts", "total", "returned"):
        assert hinted[key] == plain[key]
    assert [_without_hint(q) for q in hinted["questions"]] == plain["questions"]
    # the payload Claude's other commands read is the same object, whatever the memory holds
    assert Q.consolidate(M.load(b)) == Q.consolidate(M.load(b))


def test_the_hint_never_sets_a_value(bundles, memory):
    a, b = bundles["alpha"], bundles["beta"]
    _on()
    _group(a)
    _group(b, by=NOW)
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    before = M.load(b)
    assert any(_earlier(_page(b), q["question_id"]) for q in [_form_q(b, "zz1")])
    after = M.load(b)
    assert after["scientist_decisions"] == before["scientist_decisions"]
    assert after["missing_values"] == before["missing_values"] and after["candidates"] == before["candidates"]
    still = _form_q(b, "zz1")  # still asked, still blocking
    assert still["blocking"] is True


# --- the Local Imports page's API ----------------------------------------------------------------------------------

def test_the_page_shows_the_hint_and_records_a_confirmed_one_with_its_origin(bundles, memory, monkeypatch, tmp_path):
    a, b = bundles["alpha"], bundles["beta"]
    _on()
    _group(a)
    _group(b, by=NOW)
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    root = tmp_path / "served"
    root.mkdir()
    shutil.copytree(b, root / "beta")
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(root))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    LB._check_memo.clear()
    client = TestClient(create_app(), base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123),
                        headers={LB.LOCAL_HEADER: "1"})
    qid = _form_q(root / "beta", "zz1")["question_id"]
    page = client.get("/api/local-bundles/beta/questions").json()
    q = next(x for x in page["questions"] if x["question_id"] == qid)
    (shown,) = q["display"]["earlier_answers"]
    assert shown["value"] == "pellet" and shown["said"].startswith("Earlier answer: pellet")
    others = [x for x in page["questions"] if x["question_id"] != qid]
    assert all("earlier_answers" not in x["display"] for x in others if x.get("target_field_path") == FORM)
    version = page["bundle"]["bundle_version"]
    body = {"decision": "correct", "value": "pellet", "by": NOW, "expected_version": version,
            "from_earlier_answer": shown["entry_id"]}
    refused = client.post(f"/api/local-bundles/beta/questions/{qid}/answer", json={**body, "value": "powder"})
    assert refused.status_code == 422 and refused.json()["error"] == "earlier_answer_refused"
    r = client.post(f"/api/local-bundles/beta/questions/{qid}/answer", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["answer_memory"]["remembered"] >= 1
    recorded = [d for d in M.load(root / "beta")["scientist_decisions"]
                if d["decided_by"]["name"] == NOW and d.get("value") == "pellet"]
    assert recorded and all(d["note"].startswith(AM.PROVENANCE_PREFIX) for d in recorded)


def test_the_memory_file_digest_is_unchanged_by_reading(bundles, memory):
    a, b = bundles["alpha"], bundles["beta"]
    _on()
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    digest = hashlib.sha256(memory.read_bytes()).hexdigest()
    _page(b)
    _cli(["answer-memory", "list"])
    _cli(["answer-memory", "status"])
    assert hashlib.sha256(memory.read_bytes()).hexdigest() == digest


# --- review follow-ups (17 Nov) -------------------------------------------------------------------------------------

def _subprocess_env(memory: Path) -> dict:
    """A child interpreter finds this tree's packages as the test process does, and the memory at ``memory`` (never
    the real ~/.isaac)."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT / "apps" / "api")]),
           AM.MEMORY_ENV: str(memory)}
    env.pop("PYTEST_CURRENT_TEST", None)
    return env


def test_the_top_level_isaac_entry_dispatches_answer_memory(memory, capsys):
    """HIGH: ``isaac answer-memory ...`` failed with "invalid choice": the top-level entry point never routed it."""
    from isaac_records import cli as isaac_cli

    assert "answer-memory" in isaac_cli.LOCAL_IMPORT_COMMANDS
    capsys.readouterr()
    assert isaac_cli.main(["answer-memory", "status"]) == 0
    assert json.loads(capsys.readouterr().out)["enabled"] is False
    assert isaac_cli.main(["answer-memory", "on", "--by", ANGEL]) == 0
    assert json.loads(capsys.readouterr().out)["enabled"] is True and memory.is_file()
    # the real entry, as a separate interpreter runs it (`python -m isaac_records.cli`, what the `isaac` script calls)
    done = subprocess.run([sys.executable, "-m", "isaac_records.cli", "answer-memory", "status"], capture_output=True,
                          text=True, env=_subprocess_env(memory), timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["enabled"] is True and json.loads(done.stdout)["path"] == str(memory)


def test_a_sample_fact_needs_a_group_or_organization_confirmed_on_both_sides(bundles, memory):
    """MED: a missing research group or organization on EITHER side is no match (strict)."""
    a, b, c = bundles["alpha"], bundles["beta"], bundles["gamma"]
    _on()
    _group(a)
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)  # A: group confirmed
    _answer(c, _form_q(c, "zz1")["question_id"], "powder", BOB)    # C: no group, no organization
    # B holds neither yet: A's answer (group only on A's side) is not offered, nor C's (neither side)
    assert not _earlier(_page(b), _form_q(b, "zz1")["question_id"])
    _group(b, by=NOW)
    # B now has the group: A's (same group) is offered; C's (missing on C's side) still is not
    assert [h["literal"] for h in _earlier(_page(b), _form_q(b, "zz1")["question_id"])] == ["pellet"]
    entries = _entries(memory, FORM)
    ctx_b = AM.Context(M.load(b))
    want = ctx_b.scope_for(AM.SCOPE_SAMPLE, {"sample_name": "zz1"})
    c_entry = next(e for e in entries if e["beamtime"] == "SYN_2100-03_Gamma")
    assert not AM._matches(c_entry, want)
    assert not AM._matches({**c_entry, "scope": {**c_entry["scope"], "organization": "SYN University"}}, want)
    # a key present on both sides that differs is no match either
    a_entry = next(e for e in entries if e["beamtime"] == "SYN_2100-01_Alpha")
    assert not AM._matches({**a_entry, "scope": {**a_entry["scope"], "research_group": "SYN Other Lab"}}, want)


def test_a_sample_fact_given_under_group_and_organization_needs_both_confirmed():
    """LOW: group A at university U answered "S1"; a beamtime where only U is confirmed must not see it, because
    another group at U could own a different "S1"."""
    entry = {"scope_class": AM.SCOPE_SAMPLE,
             "scope": {"sample": {"sample_name": "s1"}, "research_group": "SYN Lab A", "organization": "SYN University"}}
    only_org = {"sample": {"sample_name": "s1"}, "organization": "SYN University"}
    assert not AM._matches(entry, only_org)
    assert not AM._matches(entry, {**only_org, "research_group": "SYN Lab B"})
    assert AM._matches(entry, {**only_org, "research_group": "SYN Lab A"})
    # symmetric: an answer recorded under the organization alone is not offered to a beamtime that has a group
    # confirmed (its group is unknown, so it could be another group's), only to one at the same organization alone
    org_entry = {"scope_class": AM.SCOPE_SAMPLE, "scope": {"sample": {"sample_name": "s1"}, "organization": "SYN University"}}
    assert not AM._matches(org_entry, {**only_org, "research_group": "SYN Lab B"})
    assert AM._matches(org_entry, only_org)


def test_forget_all_removes_an_unreadable_file_and_the_error_names_a_command_that_works(memory):
    """MED: a corrupt file could never be cleared (``forget --all`` parsed it first), and the error pointed there."""
    memory.parent.mkdir(parents=True)
    memory.write_text('{"format": "isaac.answer_memory", "entries": [', encoding="utf-8")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code, _ = _cli(["answer-memory", "status"])
    assert code == 2 and "forget --all" in err.getvalue()
    assert _cli(["answer-memory", "forget", "--entry", "am-000000000000"])[0] == 2 and memory.exists()
    code, out = _cli(["answer-memory", "forget", "--all"])
    assert code == 0 and out["removed_unreadable_file"] is True and not memory.exists()
    code, out = _cli(["answer-memory", "status"])
    assert code == 0 and out["enabled"] is False and out["file_exists"] is False
    _on()  # and a new one starts
    assert _cli(["answer-memory", "status"])[1]["enabled"] is True


def test_forget_all_never_removes_a_file_that_is_not_an_answer_memory(memory):
    memory.parent.mkdir(parents=True)
    memory.write_text('{"something": "else"}', encoding="utf-8")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code, _ = _cli(["answer-memory", "forget", "--all"])
    assert code == 2 and memory.read_text() == '{"something": "else"}'
    assert AM.MEMORY_ENV in err.getvalue()  # it says what to do instead


def test_decisions_recorded_before_opt_in_are_never_learned_unless_the_scientist_says_learn(bundles, memory):
    """MED: any write re-learned EVERY person decision in the bundle, including those recorded before opt-in."""
    a = bundles["alpha"]
    _group(a)
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)  # before opt-in
    _on()
    out = _answer(a, _form_q(a, "zz2")["question_id"], "powder", ANGEL)
    assert out["answer_memory"]["remembered"] == 1
    assert [(e["field"], e["value"]) for e in _entries(memory)] == [(FORM, "powder")]
    # a defer re-learns nothing either
    assert _cli(["bundle", "decide", a, "--question", _form_q(a, "zz3")["question_id"], "--decision", "defer",
                 "--by", ANGEL])[0] == 0
    assert [(e["field"], e["value"]) for e in _entries(memory)] == [(FORM, "powder")]
    # `learn` is the scientist's explicit yes: it needs their name
    assert _cli(["answer-memory", "learn", a, "--by", " "])[0] == 2
    assert len(_entries(memory)) == 1
    code, out = _cli(["answer-memory", "learn", a, "--by", ANGEL])
    assert code == 0, out
    assert {(e["field"], e["value"]) for e in _entries(memory)} == {(FORM, "powder"), (FORM, "pellet"), (GROUP, LAB)}


def test_a_dry_run_and_a_preview_write_nothing_to_the_memory(bundles, memory, monkeypatch, tmp_path):
    a = bundles["alpha"]
    _on()
    _group(a)
    digest = hashlib.sha256(memory.read_bytes()).hexdigest()
    root = tmp_path / "served"
    root.mkdir()
    shutil.copytree(a, root / "alpha")
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(root))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    LB._check_memo.clear()
    client = TestClient(create_app(), base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123),
                        headers={LB.LOCAL_HEADER: "1"})
    qid = _form_q(root / "alpha", "zz1")["question_id"]
    version = client.get("/api/local-bundles/alpha/questions").json()["bundle"]["bundle_version"]
    for decision in ("correct", "defer"):
        r = client.post(f"/api/local-bundles/alpha/questions/{qid}/answer",
                        json={"decision": decision, "by": ANGEL, "dry_run": True, "expected_version": version,
                              **({"value": "pellet"} if decision == "correct" else {})})
        assert r.status_code == 200, r.text
        assert r.json()["dry_run"] is True and "answer_memory" not in r.json()
    assert hashlib.sha256(memory.read_bytes()).hexdigest() == digest
    # a workbook preview (no --apply) writes nothing either
    xlsx = _workbook(a, tmp_path / "SYN_answers.xlsx", {_form_q(a, "zz1")["question_id"]: "pellet"})
    code, out = _cli(["bundle", "answers", "import", a, xlsx, "--by", ANGEL, "--json"])
    assert code == 0 and out["applied"] is False and "answer_memory" not in out
    assert hashlib.sha256(memory.read_bytes()).hexdigest() == digest


def test_a_forgotten_beamtime_or_entry_is_not_learned_again_from_existing_decisions(bundles, memory):
    """MED: a later write undid `forget --beamtime` (it re-learned the whole bundle)."""
    a = bundles["alpha"]
    q1, q2, q3 = (_form_q(a, s)["question_id"] for s in ("zz1", "zz2", "zz3"))
    org = "attribution.produced_by.organization"
    _on()
    _group(a)
    _answer(a, q1, "pellet", ANGEL)
    _answer(a, q2, "powder", ANGEL)
    assert _cli(["answer-memory", "forget", "--beamtime", "SYN_2100-01_Alpha"])[1]["entries"] == 0
    _answer(a, q3, "film", ANGEL)  # a NEW decision: only it is stored
    assert [(e["field"], e["value"]) for e in _entries(memory)] == [(FORM, "film")]
    (film,) = _entries(memory)
    assert _cli(["answer-memory", "forget", "--entry", film["entry_id"]])[1]["forgotten"] == 1
    _answer(a, _qid(a, org), "SYN University", ANGEL)
    assert [(e["field"], e["value"]) for e in _entries(memory)] == [(org, "SYN University")]  # nothing came back
    # a new decision on a forgotten target after the forget is stored
    _answer(a, q1, "film", ANGEL)
    assert {(e["field"], e["value"]) for e in _entries(memory)} == {(org, "SYN University"), (FORM, "film")}


def test_an_answer_given_before_the_group_is_confirmed_becomes_reusable_once_it_is(bundles, memory):
    """The scope keys are the bundle's own and are refreshed at its next write (never its forgotten entries)."""
    a, b = bundles["alpha"], bundles["beta"]
    _on()
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    (entry,) = _entries(memory, FORM)
    assert entry["scope"] == {"sample": {"sample_name": "zz1"}}
    _group(a)
    (refreshed,) = _entries(memory, FORM)
    assert refreshed["scope"]["research_group"] == LAB and refreshed["entry_id"] == entry["entry_id"]
    _group(b, by=NOW)
    assert [h["literal"] for h in _earlier(_page(b), _form_q(b, "zz1")["question_id"])] == ["pellet"]


def test_beamline_matching_is_conservative():
    """LOW: stripping everything but letters and digits made BL11-2 match BL1-12."""
    key = AM.beamline_key
    assert key("BL11-2") == "11-2" and key("BL1-12") == "1-12" and key("BL11-2") != key("BL1-12")
    assert key("BL15-2") == key("bl15-2") == key("15-2") == key("SSRL BL15–2") == "15-2"
    assert key("BL152") is None and key("62b") is None  # no separator: ambiguous, never mapped to BL15-2
    assert key("BL15-2 / BL4-3") is None  # two beamlines
    assert key("BL7") == "7"

    def entry(bl):
        return {"scope_class": AM.SCOPE_BEAMLINE, "scope": {"beamline": {"facility": "SSRL", "beamline": bl}}}

    def want(bl):
        return {"beamline": {"facility": "ssrl", "beamline": bl}}

    assert AM._matches(entry("BL15-2"), want("15-2"))
    assert not AM._matches(entry("BL11-2"), want("BL1-12"))
    assert not AM._matches(entry("BL152"), want("BL152"))  # ambiguous on both sides: still no match
    assert not AM._matches(entry("BL152"), want("BL15-2"))


def test_a_beamline_fact_for_bl11_2_is_never_offered_on_bl1_12(bundles, memory):
    a, b = bundles["alpha"], bundles["beta"]
    _on()
    fq = _facility_qid(a)
    _answer(a, fq, "SSRL", ANGEL, "--field", "system.facility.facility_name")
    _answer(a, fq, "BL11-2", ANGEL, "--field", "system.facility.beamline")
    _answer(a, fq, "SYN endstation 1", ANGEL, "--field", "system.facility.endstation")
    fq_b = _facility_qid(b)
    _answer(b, fq_b, "SSRL", NOW, "--field", "system.facility.facility_name")
    _answer(b, fq_b, "BL1-12", NOW, "--field", "system.facility.beamline")
    q = next((x for x in _page(b)["questions"] if x["question_id"] == fq_b), {})
    assert "system.facility.endstation" not in {h["field"] for h in q.get("earlier_answers") or ()}


def test_an_earlier_answer_shown_is_recorded_in_the_bundles_exposures(bundles, memory):
    """LOW: the earlier-answer values shown to Claude were not in the bundle's log of what was shown."""
    a, b = bundles["alpha"], bundles["beta"]
    _page(b)
    assert not [x for x in M.load(b).get("exposures") or () if x["command"] == AM.EXPOSURE_COMMAND]  # off: none
    _on()
    _group(a)
    _group(b, by=NOW)
    _answer(a, _form_q(a, "zz1")["question_id"], "pellet", ANGEL)
    q = _form_q(b, "zz1")
    _page(b)
    logged = {(x["target"]["kind"], x["target"]["id"]) for x in M.load(b)["exposures"]
              if x["command"] == AM.EXPOSURE_COMMAND}
    assert {(t["kind"], t["id"]) for t in q["targets"]} <= logged
    assert cli.main(["bundle", "check", str(b)]) == 0


QHEAD = ["Ref", "Beamline", "Beamtime", "Folder", "Blocks export?", "Topic", "Applies to", "Record (run names)",
         "Question", "Suggested answer (NOT confirmed)", "Suggested by", "File (inside the beamtime folder)",
         "Where in the file", "Text in the file", "Other readings or alternatives", "Allowed answers", "YOUR ANSWER",
         "Your notes", "ISAAC question ID"]


def _workbook(bdir: Path, path: Path, answers: dict) -> Path:
    """A synthetic question workbook: one blocking tab, ``answers`` {question id: YOUR ANSWER}."""
    folder = M.load(bdir)["source_root"]["label"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "2 Missing (blocks export)"
    ws["A1"] = "SYN title line"
    for c, h in enumerate(QHEAD, start=1):
        ws.cell(2, c, h)
    for i, (qid, ans) in enumerate(answers.items(), start=3):
        row = {"Ref": f"2-{i:04d}", "Folder": folder, "Topic": "Sample form (powder, film, ...)", "YOUR ANSWER": ans,
               "ISAAC question ID": qid}
        for c, h in enumerate(QHEAD, start=1):
            if h in row:
                ws.cell(i, c, row[h])
    wb.save(path)
    return path


def test_an_applied_workbook_import_is_remembered(bundles, memory, tmp_path):
    """The skill docs: "every applied template or workbook import, is remembered" (only its new decisions)."""
    a = bundles["alpha"]
    _on()
    xlsx = _workbook(a, tmp_path / "SYN_answers.xlsx", {_form_q(a, "zz1")["question_id"]: "pellet"})
    code, out = _cli(["bundle", "answers", "import", a, xlsx, "--by", ANGEL, "--json", "--apply"])
    assert code == 0 and out["applied"] is True, out
    assert out["answer_memory"]["remembered"] == 1
    assert [(e["field"], e["value"], e["by"]) for e in _entries(memory)] == [(FORM, "pellet", ANGEL)]
    # replaying it adds no decision, so the memory is not written
    digest = hashlib.sha256(memory.read_bytes()).hexdigest()
    code, out = _cli(["bundle", "answers", "import", a, xlsx, "--by", ANGEL, "--json", "--apply"])
    assert code == 0 and "answer_memory" not in out
    assert hashlib.sha256(memory.read_bytes()).hexdigest() == digest


def test_an_applied_template_import_is_remembered(bundles, memory, tmp_path):
    a = bundles["alpha"]
    _on()
    xlsx = tmp_path / "SYN_template.xlsx"
    assert _cli(["bundle", "template", "export", a, "--out", xlsx])[0] == 0
    ctx = AM.Context(M.load(a))
    run_id = next(r for r in sorted(ctx.group_of_run) if ctx.sample_of_run(r) == {"sample_name": "zz1"})
    wb = openpyxl.load_workbook(xlsx)
    row = next(int(v[1]) for v in wb["_isaac"].iter_rows(values_only=True) if v[0] == "File List" and v[2] == run_id)
    col = next(c.column for r in wb["File List"].iter_rows(max_row=3) for c in r if c.value == "Sample Form")
    wb["File List"].cell(row, col, "pellet")
    wb.save(xlsx)
    code, out = _cli(["bundle", "template", "import", a, xlsx, "--by", ANGEL, "--json"])
    assert code == 0 and out["applied"] is False and not memory.read_text().count('"pellet"')  # a preview: nothing
    code, out = _cli(["bundle", "template", "import", a, xlsx, "--by", ANGEL, "--json", "--apply"])
    assert code == 0 and out["applied"] is True, out
    assert out["answer_memory"]["remembered"] >= 1
    assert {(e["field"], e["value"]) for e in _entries(memory)} == {(FORM, "pellet")}
