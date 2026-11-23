"""C1 and C3 (audit of 18 Nov 2026, findings 5 and 8; other beamtimes, rule 1). SYNTHETIC fixtures only.

C1  A sample field asked once per electrode or once per run (three ``sample.material.name`` questions for ZZ1, one per
    measurement) is asked ONCE per sample. Every member keeps its id and stays answerable; the sample question names
    its members and records one answer on every target of every run of the sample. The listing, the counts and the
    question site show the sample question, not its members.
C3  A question no answer takes to a record (for information only, a disagreement about a value no record field holds,
    one settled already, one only about groups that cannot become a record) is counted in one line, not listed, by
    ``isaac bundle questions`` and the local questions screen; ``--include-unreachable`` lists them. A blocking
    question is always listed.
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
from isaac_api.local_import import question_site as S
from isaac_api.local_import import questions as Q

from tests_support_records import SEMANTICS

MATERIAL = "sample.material.name"
WHO = "SYN Scientist"
LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123), headers={LB.LOCAL_HEADER: "1"})


@pytest.fixture(scope="module", autouse=True)
def _vendored_schema_basis(tmp_path_factory):
    """Pin the VENDORED schema basis (no portal validator installed, as in CI), so the question set is the same on
    every machine."""
    d = tmp_path_factory.mktemp("no-validator")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(d))
        mp.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(d / "python"))
        yield


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    out = tmp_path_factory.mktemp("c1c3") / "bundle"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def grouped(pristine, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(pristine, target)
    return target


def _run(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def _families(payload):
    return [q for q in payload["questions"] if q.get("sample_family")]


# --- C1 ------------------------------------------------------------------------------------------------------------


def test_a_sample_field_asked_per_measurement_is_asked_once_per_sample(grouped):
    payload = Q.consolidate(M.load(grouped))
    fams = _families(payload)
    assert sorted(f["sample_family"]["sample"] for f in fams) == ["ZZ1", "ZZ2", "ZZ3"]
    by_id = {q["question_id"]: q for q in payload["questions"]}
    for fam in fams:
        assert fam["target_field_path"] == MATERIAL and fam["scope"] == "experiment"
        members = [by_id[m] for m in fam["sample_family"]["member_questions"]]
        assert len(members) == 3 and fam["answers_at_once"] == 3
        # one sample: every member's groups are this sample's, and the sample question holds every member's target
        assert {t["id"] for m in members for t in m["targets"]} == {t["id"] for t in fam["targets"]}
        assert fam["blocking"] == any(m["blocking"] for m in members)
        for m in members:
            assert m["asked_for_sample_by"] == fam["question_id"]
            assert m["text"].endswith(Q.asked_for_sample_sentence(fam["question_id"]))
        assert f"sample {fam['sample_family']['sample']}" in fam["text"]
    # never across two samples
    owners = [m for f in fams for m in f["sample_family"]["member_questions"]]
    assert len(owners) == len(set(owners))


def test_no_existing_question_changes_its_id_or_targets(grouped, monkeypatch):
    with_families = Q.consolidate(M.load(grouped))
    monkeypatch.setattr(Q, "_sample_family_questions", lambda *a, **k: [])
    without = Q.consolidate(M.load(grouped))
    before = {q["question_id"]: q for q in without["questions"]}
    after = {q["question_id"]: q for q in with_families["questions"] if not q.get("sample_family")}
    assert set(before) == set(after)
    for qid, q in before.items():
        assert after[qid]["targets"] == q["targets"] and after[qid]["kind"] == q["kind"]
        assert after[qid]["scope"] == q["scope"]


def test_the_counts_count_a_sample_question_once(grouped, monkeypatch):
    payload = Q.consolidate(M.load(grouped))
    assert payload["counts"]["asked_once_per_sample"] == 9
    monkeypatch.setattr(Q, "_sample_family_questions", lambda *a, **k: [])
    without = Q.consolidate(M.load(grouped))
    # nine member questions become three sample questions
    assert payload["counts"]["blocking"] == without["counts"]["blocking"] - 6


def test_the_listing_shows_the_sample_question_and_lists_its_members_on_request(grouped, capsys):
    code, out, err = _run(capsys, "bundle", "questions", grouped, "--limit", "200")
    assert code == 0, err
    page = json.loads(out)
    ids = {q["question_id"] for q in page["questions"]}
    fams = _families(Q.consolidate(M.load(grouped)))
    members = {m for f in fams for m in f["sample_family"]["member_questions"]}
    assert {f["question_id"] for f in fams} <= ids and not members & ids
    assert page["asked_once_per_sample"] == 9 and "--each-group" in page["asked_once_per_sample_statement"]
    code, out, _ = _run(capsys, "bundle", "questions", grouped, "--limit", "200", "--each-group")
    every = json.loads(out)
    assert members <= {q["question_id"] for q in every["questions"]} and "asked_once_per_sample" not in every
    # a group's own list asks its own question, not the sample one
    scope = next(s for s in fams[0]["per_scope_targets"] if s.startswith("group:"))
    code, out, _ = _run(capsys, "bundle", "questions", grouped, "--scope", scope, "--limit", "200")
    listed = {q["question_id"] for q in json.loads(out)["questions"]}
    assert fams[0]["question_id"] not in listed and listed & set(fams[0]["sample_family"]["member_questions"])


def test_one_answer_records_the_value_on_every_run_of_the_sample(grouped, capsys):
    fam = next(f for f in _families(Q.consolidate(M.load(grouped))) if f["sample_family"]["sample"] == "ZZ1")
    code, _out, err = _run(capsys, "bundle", "decide", grouped, "--question", fam["question_id"], "--decision", "correct",
                           "--value", "SYN iridium oxide", "--by", WHO)
    assert code == 0, err
    after = Q.consolidate(M.load(grouped))
    open_ids = {q["question_id"] for q in after["questions"]}
    assert fam["question_id"] not in open_ids
    assert not open_ids & set(fam["sample_family"]["member_questions"])
    decided = [d for d in M.load(grouped).get("scientist_decisions") or () if "SYN iridium oxide" in json.dumps(d)]
    assert len(decided) == len(fam["targets"])
    # the other samples are still asked, each once
    assert sorted(f["sample_family"]["sample"] for f in _families(after)) == ["ZZ2", "ZZ3"]


def test_a_member_answered_on_its_own_keeps_the_sample_questions_id(grouped, capsys):
    fam = next(f for f in _families(Q.consolidate(M.load(grouped))) if f["sample_family"]["sample"] == "ZZ2")
    first = fam["sample_family"]["member_questions"][0]
    code, _out, err = _run(capsys, "bundle", "decide", grouped, "--question", first, "--decision", "correct",
                           "--value", "SYN ruthenium oxide", "--by", WHO)
    assert code == 0, err
    again = next(f for f in _families(Q.consolidate(M.load(grouped))) if f["sample_family"]["sample"] == "ZZ2")
    assert again["question_id"] == fam["question_id"]
    assert again["sample_family"]["member_questions"] == fam["sample_family"]["member_questions"][1:]


def test_the_question_site_asks_each_sample_once_and_its_cover_answers_every_member(grouped, tmp_path):
    report = S.export_site(grouped, tmp_path / "site", site_template=tmp_path / "no-template")
    data = json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())
    fams = _families(Q.consolidate(M.load(grouped)))
    cards = [c for c in data["cards"] if any(fam["question_id"] in (cv.get("questions") or ())
                                             for fam in fams for cv in c["covers"])]
    assert len(cards) == 3
    for fam in fams:
        card = next(c for c in cards if any(fam["question_id"] in (cv.get("questions") or ()) for cv in c["covers"]))
        answered = {q for cv in card["covers"] for q in cv.get("questions") or ()}
        assert set(fam["sample_family"]["member_questions"]) <= answered
    assert report["blocking_questions_covered"] == report["questions_blocking"]


# --- C3 ------------------------------------------------------------------------------------------------------------


def test_a_question_no_answer_takes_to_a_record_is_counted_not_listed(grouped, capsys):
    payload = Q.consolidate(M.load(grouped))
    hidden = [q for q in payload["questions"] if Q.not_listed_reason(q)]
    assert hidden and not any(q["blocking"] for q in hidden)
    code, out, err = _run(capsys, "bundle", "questions", grouped, "--limit", "200", "--each-group")
    assert code == 0, err
    page = json.loads(out)
    listed = {q["question_id"] for q in page["questions"]}
    assert not listed & {q["question_id"] for q in hidden}
    assert page["not_listed"] == len(hidden) == sum(page["not_listed_by_reason"].values())
    assert page["not_listed_statement"].startswith(f"{len(hidden)} not listed: ")
    assert "--include-unreachable" in page["not_listed_statement"]
    code, out, _ = _run(capsys, "bundle", "questions", grouped, "--limit", "200", "--each-group",
                        "--include-unreachable")
    every = json.loads(out)
    assert "not_listed" not in every and {q["question_id"] for q in hidden} <= {q["question_id"] for q in every["questions"]}
    # each keeps its id and stays shown
    code, out, err = _run(capsys, "bundle", "show", grouped, "question", hidden[0]["question_id"])
    assert code == 0, err


def test_a_blocking_question_is_always_listed():
    assert Q.not_listed_reason({"blocking": True, "informational": True}) is None
    assert Q.not_listed_reason({"blocking": False, "informational": True}) == Q.NOT_LISTED_REASONS[0][1]
    # "no record field" is a conflict's reason only
    assert Q.not_listed_reason({"kind": "missing_value", "no_record_field": True}) is None
    assert Q.not_listed_reason({"kind": "resolve_conflict", "no_record_field": True}) is not None
    assert Q.not_listed([], "--x") == {}


def test_the_local_questions_screen_counts_them_the_same_way(pristine, tmp_path, monkeypatch):
    root = tmp_path / "bundles"
    root.mkdir()
    shutil.copytree(pristine, root / "alpha")
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(root))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    LB._check_memo.clear()
    client = TestClient(create_app(), **LOCAL)
    page = client.get("/api/local-bundles/alpha/questions").json()
    hidden = [q for q in Q.consolidate(M.load(root / "alpha"))["questions"] if Q.not_listed_reason(q)]
    assert page["not_listed"] == len(hidden) and "include_unreachable=true" in page["not_listed_statement"]
    every = client.get("/api/local-bundles/alpha/questions", params={"include_unreachable": "true"}).json()
    assert "not_listed" not in every and every["total"] == page["total"] + len(hidden)
