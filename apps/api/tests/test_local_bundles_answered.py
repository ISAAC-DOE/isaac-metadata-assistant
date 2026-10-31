"""Polish c8-web: an ANSWERED question on the local Local Imports page, as the command line has it. SYNTHETIC bundles
only (the committed multi-operator corpus, grouped); no real data.

Pinned, each by behaviour and against the CLI on a copy of the same bundle:

* The answer route answers an answered question again, as ``isaac bundle decide --question`` does: a later decision
  replaces an earlier one (byte for byte the CLI's write), a repeat records nothing, a refused value is refused with
  nothing written, and a stale ``expected_version`` is a 412 with nothing written.
* ``GET …/questions/answered`` lists what ``isaac bundle show question`` shows as ``status: answered``, with its
  ``current_answers`` (who, when, value, how many targets), and records EXACTLY the exposures that command records.
* Re-answering a whole absorber question from the page says which per-group answers it leaves as they are
  (``kept_per_group_answers``), in the dry run and in the write.
* An id that is neither open nor answered is still a 404.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api import local_bundles as LB
from isaac_api.app import create_app
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from tests_support_records import pristine_bundle  # noqa: F401

BY = "Synthetic Scientist"
LATER = "Another Synthetic Scientist"
FIXED_UTC = "2099-01-01T00:00:00Z"
LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123), headers={LB.LOCAL_HEADER: "1"})


@pytest.fixture(scope="module")
def grouped_bundle(pristine_bundle, tmp_path_factory):
    out = tmp_path_factory.mktemp("grouped-c8") / "bundle"
    shutil.copytree(pristine_bundle, out)
    M.group(out)
    return out


@pytest.fixture()
def root(tmp_path, grouped_bundle, monkeypatch):
    r = tmp_path / "bundles"
    r.mkdir()
    for name in ("alpha", "beta"):
        shutil.copytree(grouped_bundle, r / name)
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(r))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    monkeypatch.setattr(M, "now_utc", lambda: FIXED_UTC)
    LB._check_memo.clear()
    return r


@pytest.fixture()
def client(root):
    return TestClient(create_app(), **LOCAL)


def _files(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file() and p.name != ".bundle.lock"}


def _version(client, name="alpha"):
    return next(b for b in client.get("/api/local-bundles").json()["bundles"] if b["name"] == name)["bundle_version"]


def _question(bdir: Path, pred):
    return next(q for q in Q.consolidate(M.load(bdir))["questions"] if pred(q))


def _env(bdir):
    return _question(bdir, lambda q: q["target_field_path"] == "context.environment" and q["kind"] == "missing_value")


def _answer(client, qid, **body):
    return client.post(f"/api/local-bundles/alpha/questions/{qid}/answer",
                       json={"by": BY, "expected_version": _version(client), **body})


def _decide(bdir, qid, *argv, by=BY):
    assert cli.main(["bundle", "decide", str(bdir), "--question", qid, *argv, "--by", by]) == 0


def _exposures(bdir):
    return [(e["target"]["kind"], e["target"]["id"]) for e in M.load(bdir).get("exposures") or ()]


# --- answering an answered question again ---------------------------------------------------------


def test_a_later_answer_replaces_an_earlier_one_byte_for_byte_as_the_cli(client, root, capsys):
    q = _env(root / "alpha")
    qid = q["question_id"]
    assert _answer(client, qid, decision="correct", value="ex_situ").status_code == 200
    assert Q.question(Q.consolidate(M.load(root / "alpha")), qid) is None  # no longer open
    # the page used to answer 404 here; it now resolves the answered question as decide does
    dry = _answer(client, qid, decision="correct", value="in_situ", by=LATER, dry_run=True)
    assert dry.status_code == 200, dry.text
    assert sorted(dry.json()["would_record"]) == sorted(t["id"] for t in q["targets"])
    assert dry.json()["by_scope"] and dry.json()["would_say"].startswith("Would record")
    w = _answer(client, qid, decision="correct", value="in_situ", by=LATER)
    assert w.status_code == 200, w.text
    assert sorted(w.json()["result"]["recorded"]) == sorted(t["id"] for t in q["targets"])
    # the same two answers through the command line, on the copy
    _decide(root / "beta", qid, "--decision", "correct", "--value", "ex_situ")
    _decide(root / "beta", qid, "--decision", "correct", "--value", "in_situ", by=LATER)
    capsys.readouterr()
    assert _files(root / "alpha") == _files(root / "beta")
    seen = Q.answered_question(M.load(root / "alpha"), qid)
    assert seen["status"] == "answered"
    assert [(a["value"], a["by"]) for a in seen["current_answers"]] == [("in_situ", LATER)]


def test_a_repeat_records_nothing(client, root, capsys):
    qid = _env(root / "alpha")["question_id"]
    assert _answer(client, qid, decision="correct", value="ex_situ").status_code == 200
    decisions = len(M.load(root / "alpha")["scientist_decisions"])
    dry = _answer(client, qid, decision="correct", value="ex_situ", dry_run=True).json()
    assert dry["would_record"] == [] and dry["unchanged"] and dry["by_scope"] == []
    assert dry["would_say"].startswith("Nothing would be recorded")
    w = _answer(client, qid, decision="correct", value="ex_situ")
    assert w.status_code == 200, w.text
    assert w.json()["result"]["recorded"] == [] and w.json()["result"]["unchanged"]
    assert len(M.load(root / "alpha")["scientist_decisions"]) == decisions
    _decide(root / "beta", qid, "--decision", "correct", "--value", "ex_situ")
    _decide(root / "beta", qid, "--decision", "correct", "--value", "ex_situ")
    capsys.readouterr()
    assert _files(root / "alpha") == _files(root / "beta")


def test_a_refused_re_answer_writes_nothing_and_says_the_cli_reason(client, root, capsys):
    qid = _env(root / "alpha")["question_id"]
    assert _answer(client, qid, decision="correct", value="ex_situ").status_code == 200
    before = (root / "alpha" / "bundle.json").read_bytes()
    off_list = _answer(client, qid, decision="correct", value="on_the_moon")
    assert off_list.status_code == 422 and off_list.json()["error"] == "value_refused"
    wrong = _answer(client, qid, decision="set_absorber", element="Fe", edge="K")
    assert wrong.status_code == 422
    _decide(root / "beta", qid, "--decision", "correct", "--value", "ex_situ")
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(root / "beta"), "--question", qid, "--decision", "set_absorber",
                     "--element", "Fe", "--edge", "K", "--by", BY]) != 0
    assert wrong.json()["message"].strip() in capsys.readouterr().err  # the CLI's own sentence
    assert (root / "alpha" / "bundle.json").read_bytes() == before


def test_a_stale_version_on_an_answered_question_is_412_and_nothing_is_written(client, root, capsys):
    qid = _env(root / "alpha")["question_id"]
    assert _answer(client, qid, decision="correct", value="ex_situ").status_code == 200
    shown = _version(client)
    _decide(root / "alpha", qid, "--decision", "correct", "--value", "in_situ", by="Someone at the terminal")
    capsys.readouterr()
    after_cli = (root / "alpha" / "bundle.json").read_bytes()
    url = f"/api/local-bundles/alpha/questions/{qid}/answer"
    for dry in (True, False):
        r = client.post(url, json={"decision": "correct", "value": "ex_situ", "by": BY, "expected_version": shown,
                                   "dry_run": dry})
        assert r.status_code == 412 and r.json()["error"] == "stale_bundle_version"
        assert r.json()["current_version"] == M.bundle_version(root / "alpha")
    assert (root / "alpha" / "bundle.json").read_bytes() == after_cli
    r = client.post(url, json={"decision": "correct", "value": "ex_situ", "by": BY})
    assert r.status_code == 428


def test_an_id_neither_open_nor_answered_is_404(client, root):
    r = _answer(client, "Q-0000000000", decision="correct", value="ex_situ")
    assert r.status_code == 404 and r.json()["error"] == "not_found_in_bundle"


# --- the answered questions, as `bundle show question` shows them ---------------------------------


def test_the_answered_list_shows_current_answers_and_records_exactly_the_cli_exposures(client, root, capsys):
    env = _env(root / "alpha")
    conf = _question(root / "alpha", lambda q: q["kind"] == "confirm_value" and Q.confirm_value_shown(M.load(root / "alpha"), q))
    for bdir in (root / "alpha", root / "beta"):
        _decide(bdir, env["question_id"], "--decision", "correct", "--value", "ex_situ")
        _decide(bdir, conf["question_id"], "--decision", "confirm")
    capsys.readouterr()
    assert _exposures(root / "alpha") == _exposures(root / "beta")
    page = client.get("/api/local-bundles/alpha/questions/answered")
    assert page.status_code == 200, page.text
    body = page.json()
    ids = [q["question_id"] for q in body["questions"]]
    assert env["question_id"] in ids and conf["question_id"] in ids and body["total"] == len(ids)
    for qid in ids:
        assert cli.main(["bundle", "show", str(root / "beta"), "question", qid]) == 0
        shown = json.loads(capsys.readouterr().out)
        q = next(x for x in body["questions"] if x["question_id"] == qid)
        assert shown["status"] == q["status"] == "answered"
        assert shown["current_answers"] == q["current_answers"]
    # EXACTLY the exposures `bundle show question` recorded, and the same bytes
    assert body["exposures_recorded"] > 0
    assert set(_exposures(root / "alpha")) == set(_exposures(root / "beta"))
    assert _files(root / "alpha") == _files(root / "beta")
    assert body["bundle"]["bundle_version"] == M.bundle_version(root / "alpha")
    e = next(x for x in body["questions"] if x["question_id"] == env["question_id"])
    (a,) = e["current_answers"]
    assert (a["decision"], a["value"], a["by"], a["decided_utc"], a["targets"]) == (
        "correct", "ex_situ", BY, FIXED_UTC, len(env["targets"]))
    # its display shows no scope's own suggestions and no per-run agreement: only what the command shows
    assert all(not s["own_suggestions"] and not s["per_target"] for s in e["display"]["scopes"])
    again = client.get("/api/local-bundles/alpha/questions/answered").json()
    assert again["exposures_recorded"] == 0
    assert again["bundle"]["bundle_version"] == body["bundle"]["bundle_version"]
    # filtered and paged
    only = client.get("/api/local-bundles/alpha/questions/answered", params={"kind": "confirm_value"}).json()
    assert [q["question_id"] for q in only["questions"]] == [conf["question_id"]]
    paged = client.get("/api/local-bundles/alpha/questions/answered", params={"limit": 1, "offset": 1}).json()
    assert paged["returned"] == 1 and paged["omitted_before"] == 1 and paged["total"] == len(ids)


def test_an_open_question_is_not_in_the_answered_list_and_a_deferred_one_stays_open(client, root, capsys):
    q = _env(root / "alpha")
    assert client.get("/api/local-bundles/alpha/questions/answered").json()["total"] == 0
    _decide(root / "alpha", q["question_id"], "--decision", "defer")
    capsys.readouterr()
    assert client.get("/api/local-bundles/alpha/questions/answered").json()["total"] == 0


def test_the_answered_list_is_absent_without_the_variable(root, monkeypatch):
    monkeypatch.delenv(LB.LOCAL_BUNDLES_ENV)
    assert TestClient(create_app(), **LOCAL).get("/api/local-bundles/alpha/questions/answered").status_code == 404


# --- the absorber question answered again for all its groups -------------------------------------


def test_re_answering_the_whole_absorber_question_says_the_per_group_answers_it_keeps(client, root, capsys):
    q = _question(root / "alpha", lambda x: x["kind"] == "confirm_absorber")
    qid = q["question_id"]
    groups = [t["id"] for t in q["targets"]]
    if len(groups) < 2:
        pytest.skip("this grouping asks the absorber of fewer than two groups")
    assert _answer(client, qid, decision="set_absorber", element="Fe", edge="K").status_code == 200
    assert _answer(client, qid, decision="set_absorber", element="Au", edge="L3", only=f"group:{groups[0]}").status_code == 200
    listed = client.get("/api/local-bundles/alpha/questions/answered", params={"kind": "confirm_absorber"}).json()
    (shown,) = listed["questions"]
    assert {(a["element"], a["edge"], a["targets"]) for a in shown["current_answers"]} == {
        ("Fe", "K", len(groups) - 1), ("Au", "L3", 1)}
    kept = [{"group_id": groups[0], "element": "Au", "edge": "L3"}]
    dry = _answer(client, qid, decision="set_absorber", element="Co", edge="K", dry_run=True)
    assert dry.status_code == 200, dry.text
    assert dry.json()["kept_per_group_answers"] == kept and groups[0] not in dry.json()["would_record"]
    w = _answer(client, qid, decision="set_absorber", element="Co", edge="K")
    assert w.status_code == 200, w.text
    assert w.json()["result"]["kept_per_group_answers"] == kept
    assert f"{groups[0]} keeps Au L3" in w.json()["result"]["statement"]
