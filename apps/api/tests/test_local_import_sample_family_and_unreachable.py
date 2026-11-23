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


# --- review of #350 ------------------------------------------------------------------------------------------------


def _latest_value(bdir, target_id):
    got = [d for d in M.load(bdir).get("scientist_decisions") or () if (d.get("target") or {}).get("id") == target_id]
    return got[-1].get("value") if got else None


def _zz1(bdir):
    fam = next(f for f in _families(Q.consolidate(M.load(bdir))) if f["sample_family"]["sample"] == "ZZ1")
    members = {q["question_id"]: q for q in Q.consolidate(M.load(bdir))["questions"]
               if q["question_id"] in fam["sample_family"]["member_questions"]}
    return fam, [members[m] for m in fam["sample_family"]["member_questions"]]


def test_finding_1_a_question_that_holds_a_record_or_feeds_a_label_is_always_listed(grouped, capsys):
    # never hidden, whatever else holds for it
    for flag in ("completeness", "label_question"):
        assert Q.not_listed_reason({"kind": "resolve_conflict", "no_record_field": True, flag: {"x": 1}}) is None
        assert Q.not_listed_reason({"informational": True, flag: "Q-x"}) is None
    payload = Q.consolidate(M.load(grouped))
    rows = Q.filter_questions(payload, scope=None, blocking_only=False)
    kept = [q for q in rows if q.get("completeness") or q.get("label_question")]
    assert any(q.get("label_question") for q in kept), "the synthetic corpus has a disagreement a label is read from"
    code, out, err = _run(capsys, "bundle", "questions", grouped, "--limit", "200", "--each-group")
    assert code == 0, err
    listed = {q["question_id"] for q in json.loads(out)["questions"]}
    assert {q["question_id"] for q in kept} <= listed
    # --distinguishing-only lists every question of the completeness tier, none counted away
    code, out, _ = _run(capsys, "bundle", "questions", grouped, "--limit", "200", "--distinguishing-only")
    page = json.loads(out)
    assert "not_listed" not in page
    assert page["total"] == len([q for q in rows if q.get("completeness") and not q.get("outside_live_groups")])


def test_finding_2_an_electrode_answered_on_its_own_keeps_its_answer_from_the_cli(grouped, capsys):
    fam, members = _zz1(grouped)
    own = [t["id"] for t in members[0]["targets"]]
    assert _run(capsys, "bundle", "decide", grouped, "--question", members[0]["question_id"], "--decision", "correct",
                "--value", "SYN own oxide", "--by", WHO)[0] == 0
    # the sample question, still open for the other two, records on theirs only
    code, _out, err = _run(capsys, "bundle", "decide", grouped, "--question", fam["question_id"], "--decision",
                           "correct", "--value", "SYN shared oxide", "--by", WHO)
    assert code == 0, err
    assert all(_latest_value(grouped, t) == "SYN own oxide" for t in own)
    assert all(_latest_value(grouped, t["id"]) == "SYN shared oxide" for m in members[1:] for t in m["targets"])
    # answered again once every target is answered: refused, nothing changes
    code, _out, err = _run(capsys, "bundle", "decide", grouped, "--question", fam["question_id"], "--decision",
                           "correct", "--value", "SYN third oxide", "--by", WHO)
    assert code != 0 and "never changes an answer" in err
    assert all(_latest_value(grouped, t) == "SYN own oxide" for t in own)


def test_finding_2_once_one_member_is_left_the_sample_question_records_on_it_alone(grouped, capsys):
    fam, members = _zz1(grouped)
    for m, value in zip(members[:2], ("SYN first", "SYN second")):
        assert _run(capsys, "bundle", "decide", grouped, "--question", m["question_id"], "--decision", "correct",
                    "--value", value, "--by", WHO)[0] == 0
    assert fam["question_id"] not in {q["question_id"] for q in Q.consolidate(M.load(grouped))["questions"]}
    code, _out, err = _run(capsys, "bundle", "decide", grouped, "--question", fam["question_id"], "--decision",
                           "correct", "--value", "SYN last", "--by", WHO)
    assert code == 0, err
    assert [_latest_value(grouped, m["targets"][0]["id"]) for m in members] == ["SYN first", "SYN second", "SYN last"]


def _screen(pristine, tmp_path, monkeypatch):
    root = tmp_path / "bundles"
    root.mkdir()
    shutil.copytree(pristine, root / "alpha")
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(root))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    LB._check_memo.clear()
    return root / "alpha", TestClient(create_app(), **LOCAL)


def _version(client):
    return next(b for b in client.get("/api/local-bundles").json()["bundles"] if b["name"] == "alpha")["bundle_version"]


def test_finding_2_an_electrode_answered_on_its_own_keeps_its_answer_from_the_screen(pristine, tmp_path, monkeypatch):
    bdir, client = _screen(pristine, tmp_path, monkeypatch)
    fam, members = _zz1(bdir)
    for qid, value in ((members[0]["question_id"], "SYN own oxide"), (fam["question_id"], "SYN shared oxide")):
        r = client.post(f"/api/local-bundles/alpha/questions/{qid}/answer",
                        json={"decision": "correct", "value": value, "by": WHO, "expected_version": _version(client)})
        assert r.status_code == 200, r.text
    assert all(_latest_value(bdir, t["id"]) == "SYN own oxide" for t in members[0]["targets"])
    assert all(_latest_value(bdir, t["id"]) == "SYN shared oxide" for m in members[1:] for t in m["targets"])


def test_finding_3_the_screen_folds_the_members_as_the_cli_does(pristine, tmp_path, monkeypatch, capsys):
    bdir, client = _screen(pristine, tmp_path, monkeypatch)
    page = client.get("/api/local-bundles/alpha/questions").json()
    fams = _families(Q.consolidate(M.load(bdir)))
    members = {m for f in fams for m in f["sample_family"]["member_questions"]}
    ids = {q["question_id"] for q in page["questions"]}
    assert {f["question_id"] for f in fams} <= ids and not members & ids
    assert page["asked_once_per_sample"] == len(members) and "each_group=true" in page["asked_once_per_sample_statement"]
    every = client.get("/api/local-bundles/alpha/questions", params={"each_group": True}).json()
    assert members <= {q["question_id"] for q in every["questions"]}
    # the same count as the command line (which also folds the per-group start-time questions this screen nests)
    code, out, err = _run(capsys, "bundle", "questions", bdir, "--limit", "200", "--no-context")
    assert code == 0, err
    cli_page = json.loads(out)
    assert page["total"] == cli_page["total"] + cli_page.get("answered_at_once", 0)
    assert page["not_listed"] == cli_page["not_listed"]


def _hand_family(path, numbers, *, settled=True):
    """Three groups of ONE sample (JK2), told apart only by their number: a question each."""
    from isaac_api.local_import.grouping import SAMPLE_NUMBER_KEY

    groups, questions, written = [], [], {}
    for i, n in enumerate(numbers):
        gid = f"rg-{i}"
        groups.append({"group_id": gid, "status": "proposed",
                       "basis": {"sample": {"sample_name": {"value": "jk2"}, SAMPLE_NUMBER_KEY: {"value": n}}}})
        written[gid] = [("sample_name", "JK2"), (SAMPLE_NUMBER_KEY, n) if settled else ("file-name number", n, "x"),
                        ("sample_name_stem", f"jk2_{n}_stem")]
        questions.append({"question_id": f"Q-{i}", "kind": "missing_value", "scope": f"group:{gid}", "tier": 1,
                          "blocking": True, "target_field_path": path, "targets": [{"kind": "missing_value", "id": f"m{i}"}],
                          "per_scope_targets": {f"group:{gid}": [f"m{i}"]}, "applies_to": {"runs": 1},
                          "allowed_decisions": ["correct", "defer"], "text": "Q.", "hints": []})
    return questions, {"record_groups": groups}, written


def test_finding_4_the_question_names_the_electrodes_and_only_the_material_and_form_are_grouped():
    from isaac_api.local_import import plain_questions as P

    qs, bundle, written = _hand_family("sample.sample_form", ["02", "03", "04"])
    (fam,) = Q._sample_family_questions(qs, bundle, written)
    assert fam["text"].startswith("What is the sample form (sample.sample_form) of the JK2 electrodes (no. 02, 03, 04)? ")
    assert "One answer applies to each of them" in fam["text"] and "this question never changes it" in fam["text"]
    assert fam["sample_family"]["objects"] == "the JK2 electrodes (no. 02, 03, 04)"
    assert P.ask_for("sample.sample_form", subject=fam["sample_family"]["objects"], plural=True, names_sample=True) == (
        "What form were the JK2 electrodes (no. 02, 03, 04) in?")
    # numbers nobody said are electrodes are not called electrodes
    qs, bundle, written = _hand_family("sample.sample_form", ["02", "03"], settled=False)
    (fam,) = Q._sample_family_questions(qs, bundle, written)
    assert "electrodes (no." not in fam["text"] and "whether they name electrodes is not yet said" in fam["text"]
    assert fam["sample_family"]["objects"] is None
    # a field that can differ from one object to the next is never asked once
    for path in ("sample.geometry.geometric_area_cm2", "sample.electrode_type", "sample.composition",
                 "sample.library.plate_id", "sample.sample_id", "sample.material.notes"):
        qs, bundle, written = _hand_family(path, ["02", "03", "04"])
        assert Q._sample_family_questions(qs, bundle, written) == [], path
    assert {p for p in Q.SAMPLE_FAMILY_FIELDS} == {"sample.sample_form", "sample.material.name",
                                                   "sample.material.formula", "sample.material.provenance"}


def test_finding_5_only_the_number_is_quoted_as_a_number():
    qs, bundle, written = _hand_family("sample.material.name", ["02", "03"])
    (fam,) = Q._sample_family_questions(qs, bundle, written)
    assert fam["sample_family"]["numbers"] == ["02", "03"] and "stem" not in fam["text"]


def test_finding_6_the_not_listed_line_says_what_holds_for_each_reason():
    said = Q.not_listed([{"all_groups_cannot_export": True}, {"informational": True}], "--x")["not_listed_statement"]
    assert "some can after processing again" in said and "As the bundle stands" in said
    assert "No answer to them reaches a record" not in said


# --- re-review of #350 ---------------------------------------------------------------------------------------------


def _site_answer(tmp_path, data, card, value, name, at="2100-02-01T10:00:00Z"):
    from isaac_api.local_import import question_site_import as SI

    path = tmp_path / name
    path.write_text(json.dumps({
        "format": SI.ANSWERS_FORMAT_ID, "format_version": "1.0.0", "bundle_id": data["bundle_id"],
        "bundle_version": data["bundle_version"], "exported_at": "2100-02-01T10:00:00Z", "log": [],
        "answers": [{"card_id": card["card_id"], "action": "value", "value": value, "typed": True, "note": "",
                     "by": WHO, "at": at}]}))
    return path


def test_a_site_answer_records_on_the_last_open_member_and_never_over_an_own_answer(grouped, tmp_path):
    """Leftover 1: once only one member is open the sample question leaves the open list; a site answer to its card
    still records on that member (as decide --question does), and never on the ones answered on their own."""
    from isaac_api.local_import import question_site_import as SI

    S.export_site(grouped, tmp_path / "site", site_template=tmp_path / "no-template")
    site_data = tmp_path / "site" / "data" / "site-data.json"
    data = json.loads(site_data.read_text())
    fam, members = _zz1(grouped)
    card = next(c for c in data["cards"] if c["covers"][0]["question_id"] == fam["question_id"])
    for m, value in zip(members[:2], ("SYN first", "SYN second")):
        M.decide_question(grouped, question_id=m["question_id"], decision="correct", value=value, by=WHO, orcid=None)
    assert fam["question_id"] not in {q["question_id"] for q in Q.consolidate(M.load(grouped))["questions"]}
    rep = SI.import_answers(grouped, _site_answer(tmp_path, data, card, "SYN site oxide", "a.json"),
                            site_data=site_data, apply=True)
    assert rep["answers"][0]["outcome"] == "recorded", rep["answers"][0]
    assert [_latest_value(grouped, m["targets"][0]["id"]) for m in members] == ["SYN first", "SYN second",
                                                                               "SYN site oxide"]
    # every member answered: another answer is reported, never recorded over theirs
    rep = SI.import_answers(grouped, _site_answer(tmp_path, data, card, "SYN later oxide", "b.json", at="2100-02-02T10:00:00Z"),
                            site_data=site_data, apply=True)
    assert rep["answers"][0]["outcome"] == "no_longer_asked"
    assert rep["answers"][0]["reason"] == "it was answered since with another answer, which is kept"
    assert _latest_value(grouped, members[2]["targets"][0]["id"]) == "SYN site oxide"


def test_a_card_names_file_name_numbers_as_the_question_does():
    """Leftover 2: numbers nobody said are electrodes are listed on the card too, never left out."""
    qs, bundle, written = _hand_family("sample.sample_form", ["02", "03"], settled=False)
    (fam,) = Q._sample_family_questions(qs, bundle, written)
    assert fam["sample_family"]["named"] == "sample JK2 (file-name numbers 02, 03)"
    subject, plural, sample = S._subject(None, {"named": fam, "only_scopes": None}, [], "sample.sample_form")
    assert (subject, plural, sample) == ("sample JK2 (file-name numbers 02, 03)", False, "JK2")
    qs, bundle, written = _hand_family("sample.sample_form", ["02", "03"])
    (fam,) = Q._sample_family_questions(qs, bundle, written)
    assert S._subject(None, {"named": fam, "only_scopes": None}, [], "sample.sample_form")[:2] == (
        "the JK2 electrodes (no. 02, 03)", True)
