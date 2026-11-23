"""``isaac bundle site export`` / ``isaac bundle site import``: a bundle's open questions as plain cards for the
question site, and the site's answers read back as decisions (docs/question-site-contract.md).

Synthetic only: the bundle is the multi-operator fixture imported under a fake folder name; every answers file,
suggestions file, image and site template is built here. No real bundle, folder, sample or person is used.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from isaac_api.local_import import answer_memory as AM
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import plain_questions as P
from isaac_api.local_import import question_context as QC
from isaac_api.local_import import question_site as S
from isaac_api.local_import import question_site_hints as H
from isaac_api.local_import import question_site_import as SI
from isaac_api.local_import import questions as Q

from tests_support_records import SEMANTICS


@pytest.fixture(scope="module", autouse=True)
def _vendored_schema_basis(tmp_path_factory):
    """Pin the VENDORED schema basis (no portal validator installed, as in CI), so the question set is the one these
    tests expect whatever is installed on the machine. Module-scoped: in place before the module's bundles are built."""
    d = tmp_path_factory.mktemp("no-validator")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(d))
        mp.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(d / "python"))
        yield


FOLDER = "SYN_BL00_2100-01_Synthetic"
WHO = "SYN Scientist"
AT = "2100-02-01T10:00:00Z"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
ENVIRONMENT = "context.environment"
MATERIAL = "sample.material.name"
COVERS_3 = "One answer covers all 3 measurements; if any differs, add a note and nothing is recorded until it has been read."
FORM = "sample.sample_form"
GROUP = "attribution.produced_by.group"


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    root = tmp_path_factory.mktemp("qs")
    src = root / FOLDER
    shutil.copytree(SEMANTICS, src)
    out = root / "bundle"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    M.group(out)
    return out


@pytest.fixture(scope="module")
def exported(base, tmp_path_factory):
    """One default export of a copy of the bundle: ``(bundle_dir, out_dir, report, site_data)``."""
    root = tmp_path_factory.mktemp("qs-export")
    bdir = root / "bundle"
    shutil.copytree(base, bdir)
    report = S.export_site(bdir, root / "site", site_template=root / "no-template")
    return bdir, root / "site", report, json.loads((root / "site" / "data" / "site-data.json").read_text())


@pytest.fixture()
def work(exported, tmp_path):
    """A fresh copy of the exported bundle with its site-data: ``(bundle_dir, site_data_path, site_data)``."""
    bdir, out, _report, data = exported
    d = tmp_path / "work" / "bundle"
    shutil.copytree(bdir, d)
    return d, out / "data" / "site-data.json", data


def _digest(d: Path) -> str:
    return hashlib.sha256((d / "bundle.json").read_bytes()).hexdigest()


def _card(data, path, *, title_has=None, n=0):
    hits = [c for c in data["cards"] if (c["field"] or {}).get("path") == path
            and (title_has is None or title_has in c["title"])]
    return hits[n]


def _answer(card, action, value=None, *, typed=False, note="", by=WHO, at=AT):
    return {"card_id": card["card_id"], "action": action, "value": value, "typed": typed, "note": note, "by": by, "at": at}


def _answers_file(tmp_path, data, answers, name="answers.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"format": SI.ANSWERS_FORMAT_ID, "format_version": "1.0.0", "bundle_id": data["bundle_id"],
                                "bundle_version": data["bundle_version"], "exported_at": AT, "answers": answers,
                                "log": []}))
    return path


def _sentences(text: str) -> int:
    """How many sentences ``text`` holds ("no. 01" is an abbreviation, not an end)."""
    return len(re.findall(r"[.!?](?:\s|$)", text.replace("no. ", "no ")))


def _decisions(bdir):
    return M.load(bdir).get("scientist_decisions") or []


def _open(bdir):
    return Q.consolidate(M.load(bdir))["questions"]


# --- the export: shape, collapsing, wording -----------------------------------------------------------------------------


def test_the_export_writes_the_contract_shape(exported):
    bdir, out, report, data = exported
    assert data["format"] == "isaac.question_site" and data["format_version"] == "1.0.0"
    assert data["bundle_id"] == M.load(bdir)["bundle_id"] and data["bundle_version"] == M.bundle_version(bdir)
    assert data["title"] == FOLDER and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", data["generated_at"])
    assert data["totals"] == {"records": 9, "cards": len(data["cards"]),
                              "blocking_cards": sum(1 for c in data["cards"] if c["blocking"])}
    used = {c["section"] for c in data["cards"]}
    assert [s["id"] for s in data["sections"]] == [s["id"] for s in S.SECTIONS if s["id"] in used]
    keys = {"card_id", "section", "blocking", "audience", "title", "detail", "field", "applies_to", "unblocks", "answer",
            "suggestion", "context", "covers"}
    for c in data["cards"]:
        assert set(c) == keys, c["title"]
        assert re.fullmatch(r"C-[0-9a-f]{10}", c["card_id"])
        assert c["answer"]["kind"] in ("choice", "text", "number", "yes_no")
        assert c["applies_to"]["count"] == len(c["applies_to"]["items"]) + c["applies_to"].get("more", 0)
        assert len(c["context"]) <= S.MAX_CONTEXT
    assert len({c["card_id"] for c in data["cards"]}) == len(data["cards"])
    assert report["cards"] == len(data["cards"]) and sorted(p.name for p in out.iterdir()) == ["data"]
    assert "only data/ was written" in report["site_template_note"]


def test_every_blocking_question_is_on_a_card_and_blocking_cards_come_first_widest_first(exported):
    bdir, _out, report, data = exported
    blocking = {q["question_id"] for q in _open(bdir) if q.get("blocking")}
    covered = {qid for c in data["cards"] for cover in c["covers"] for qid in cover["questions"]}
    assert blocking <= covered  # every one, the members of a sample question too (its cover names them)
    # C1: counted as `bundle questions` counts them, each member of a sample question as that one question
    members = {q["question_id"] for q in _open(bdir) if q.get("asked_for_sample_by")}
    assert report["blocking_questions_covered"] == report["questions_blocking"] == len(blocking - members)
    order = [(not c["blocking"], -c["unblocks"]) for c in data["cards"]]
    assert order == sorted(order)
    assert all(c["blocking"] for c in data["cards"])  # the default export: only what blocks (and the dose question)


def test_a_same_reading_group_is_one_card_answered_by_one_call(exported):
    bdir, _out, _report, data = exported
    qs = [q for q in _open(bdir) if q.get("target_field_path") == MATERIAL and q.get("same_reading_group")]
    groups = {q["same_reading_group"] for q in qs}
    cards = [c for c in data["cards"] if (c["field"] or {}).get("path") == MATERIAL]
    assert len(qs) == 9 and len(groups) == 3 and len(cards) == 3  # nine questions, three asks
    by_id = {q["question_id"]: q for q in _open(bdir)}
    for c in cards:
        (cover,) = c["covers"]
        members = [q["question_id"] for q in qs if q["question_id"] in cover["questions"]]
        # C1: the one call is the sample question, which asks the sample once and answers its three members
        family = by_id[cover["question_id"]]
        assert family["sample_family"]["member_questions"] == sorted(members) and len(members) == 3
        assert cover["same_reading"] is False and cover["only_scopes"] is None
        assert c["applies_to"]["count"] == 3 and c["unblocks"] == 3 and c["section"] == "samples"
        assert cover["on_value"] == {"decision": "correct"} and cover["on_dont_know"] == {"decision": "defer"}


def test_different_sample_tokens_are_never_one_card(exported):
    _bdir, _out, _report, data = exported
    titles = sorted(c["title"] for c in data["cards"] if (c["field"] or {}).get("path") == MATERIAL)
    assert titles == ["What material is sample ZZ1?", "What material is sample ZZ2?", "What material is sample ZZ3?"]
    forms = [c for c in data["cards"] if (c["field"] or {}).get("path") == FORM]
    assert sorted(c["title"] for c in forms) == [f"What form was sample ZZ{n} (no. 0{n}) in?" for n in (1, 2, 3)]
    assert len({c["covers"][0]["question_id"] for c in forms}) == 3  # each its own question: never joined
    for c in forms:
        assert c["applies_to"]["summary"].startswith("3 measurements of sample ZZ")


def test_a_question_asked_for_the_whole_beamtime_is_one_card_per_sample(exported, work, tmp_path):
    """Review C1(a): "was this done operando …?" is asked of every measurement at once by the command line. One
    click must not record it for samples whose honest answer differs, so the site asks it once per sample the
    grouping states, each card answered for exactly that sample's groups."""
    bdir, _out, _report, data = exported
    q = next(x for x in _open(bdir) if x.get("target_field_path") == ENVIRONMENT)
    assert q["scope"] == "experiment" and len(q["per_scope_targets"]) == 9
    cards = [c for c in data["cards"] if (c["field"] or {}).get("path") == ENVIRONMENT]
    assert sorted(c["title"] for c in cards) == [
        f"Was sample ZZ{n} measured operando, in situ, ex situ or in silico?" for n in (1, 2, 3)]
    scopes = [sc for c in cards for sc in c["covers"][0]["only_scopes"]]
    assert sorted(scopes) == sorted(q["per_scope_targets"]) and len(set(scopes)) == 9  # every group once, none twice
    for c in cards:
        (cover,) = c["covers"]
        assert cover["question_id"] == q["question_id"] and len(cover["only_scopes"]) == 3 and not cover["same_reading"]
        assert c["applies_to"]["count"] == 3 and c["unblocks"] == 3 and c["section"] == "samples"
        assert c["applies_to"]["summary"].startswith("3 measurements of sample ZZ") and len(c["applies_to"]["items"]) == 3
        assert c["detail"] == f"{P.NONE_SAY} {COVERS_3}"
        assert c["card_id"] == S.card_id(ENVIRONMENT, [f"{q['question_id']}@{sc}" for sc in cover["only_scopes"]])
    assert len({c["card_id"] for c in cards}) == 3
    # one card's answer is recorded for its own sample's three groups and no other
    wdir, site_data, _ = work
    one = next(c for c in cards if "ZZ2" in c["title"])
    rep = SI.import_answers(wdir, _answers_file(tmp_path, data, [_answer(one, "value", "in_situ")]), site_data=site_data, apply=True)
    assert rep["counts"]["recorded"] == 1 and len(_decisions(wdir)) == 3
    still = Q.question(Q.consolidate(M.load(wdir)), q["question_id"])
    assert sorted(still["per_scope_targets"]) == sorted(set(q["per_scope_targets"]) - set(one["covers"][0]["only_scopes"]))
    again = SI.import_answers(wdir, _answers_file(tmp_path, data, [_answer(one, "value", "in_situ")]), site_data=site_data, apply=True)
    assert again["counts"]["already_recorded"] == 1 and len(_decisions(wdir)) == 3


def test_groups_with_no_stated_sample_are_cards_of_their_own():
    def group(name=None):
        return {"basis": {"sample": {"sample_name": {"value": name}} if name else {}}}

    view = SimpleNamespace(groups={"rg-a": group("syn1"), "rg-b": group("syn1"), "rg-c": group("syn2"), "rg-d": group(),
                                   "rg-e": group()}, cands={}, exportable=["rg-a", "rg-b", "rg-c", "rg-d"])
    scopes = [f"group:{g}" for g in view.groups]
    q = {"question_id": "Q-syn0000009", "kind": "missing_value", "scope": "experiment", "blocking": True, "partition": None,
         "target_field_path": ENVIRONMENT, "allowed_decisions": ["correct", "defer"], "targets": [],
         "per_scope_targets": {sc: [f"miss-{n}"] for n, sc in enumerate(scopes)}}
    assert S._scope_parts(view, q, scopes) == [(["group:rg-a", "group:rg-b"], False), (["group:rg-c"], False),
                                               (["group:rg-d"], True), (["group:rg-e"], True)]
    units, left = S._units(view, [q], ())
    assert [(u["only_scopes"], u["identified"], u["lone"]) for u in units] == [
        (["group:rg-a", "group:rg-b"], True, False), (["group:rg-c"], True, False), (["group:rg-d"], False, True)]
    assert left == {"about a measurement that cannot become a record": 1}  # rg-e can never export: not asked
    assert S._scope_parts(view, q, scopes[:2]) == [(None, False)]  # one sample: the question as it is asked
    assert S._scope_parts(view, {**q, "answers_differ": True}, scopes[:2]) == [(["group:rg-a"], True), (["group:rg-b"], True)]
    # a same-reading group that asks for a value is split the same way; one that confirms each file's own value is not
    def sr(n, gid, **kw):
        return {"question_id": f"Q-syn000001{n}", "kind": "confirm_value", "scope": f"group:{gid}", "blocking": True,
                "target_field_path": "context.electrochemistry.reaction", "allowed_decisions": ["confirm", "correct", "defer"],
                "same_reading_group": "SR-syn", "per_scope_targets": {f"group:{gid}": [f"cand-{n}"]},
                "targets": [{"kind": "candidate", "id": f"cand-{n}"}], **kw}
    asks = [sr(1, "rg-a", no_value=True), sr(2, "rg-c", no_value=True), sr(3, "rg-d", no_value=True)]
    assert [len(u["questions"]) for u in S._units(view, asks, ())[0]] == [1, 1, 1]
    confirms = [sr(1, "rg-a"), sr(2, "rg-c"), sr(3, "rg-d")]
    (whole,) = S._units(view, confirms, ())[0]
    assert whole["same_reading"] and len(whole["questions"]) == 3


def test_a_card_never_hides_what_one_answer_reaches():
    """Review C1(b): a card that reaches more measurements than it lists shows every sample with its count and an
    example, and every measurement that names no sample, and states the total."""
    def group(name=None):
        return {"member_run_ids": [], "basis": {"sample": {"sample_name": {"value": name}} if name else {}}}

    names = {f"rg-{n:02d}": ("syn1" if n < 30 else "syn2" if n < 43 else None) for n in range(45)}
    view = SimpleNamespace(groups={g: group(v) for g, v in names.items()}, cands={}, runs={})
    view.group_name = lambda gid: f"file_{gid}"
    card = {"_groups": list(names), "applies_to": {"count": 45, "summary": "All 45 records", "items": ["x"] * 40, "more": 5}}
    S._show_everything(view, card)
    assert card["applies_to"]["breakdown"] == [
        {"label": "sample syn1", "count": 30, "example": "file_rg-00"}, {"label": "sample syn2", "count": 13, "example": "file_rg-30"},
        {"label": "no sample named in the files", "count": 1, "example": "file_rg-43"},
        {"label": "no sample named in the files", "count": 1, "example": "file_rg-44"}]
    (table,) = card["_first_context"]
    assert table["label"] == "Everything one answer covers: 45 measurements" and len(table["rows"]) == 4
    assert table["rows"][2] == ["no sample named in the files", "1", "file_rg-43"]
    small = {"_groups": list(names)[:40], "applies_to": {"count": 40, "items": ["x"] * 40}}
    S._show_everything(view, small)
    assert "breakdown" not in small["applies_to"] and "_first_context" not in small


def test_an_answer_with_a_note_on_a_card_for_several_measurements_is_held(base, tmp_path, capsys):
    """Review C1(c): "operando, except the pellet" must never be recorded as operando for all. The answer is held
    until a person has read the note; a card about one measurement has no exception to name and is applied."""
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    S.export_site(bdir, tmp_path / "site", include=("optional",), site_template=tmp_path / "none")
    site_data = tmp_path / "site" / "data" / "site-data.json"
    data = json.loads(site_data.read_text())
    env = _card(data, ENVIRONMENT, title_has="ZZ1")
    single = next(c for c in data["cards"] if c["title"] == "Is the applied potential 0.1 V for this measurement?")
    form = _card(data, FORM, title_has="ZZ3")
    answers = _answers_file(tmp_path, data, [
        _answer(env, "value", "operando", note="SYN: all but the first file"),
        _answer(single, "accept", 0.1, note="SYN: checked against the logbook"),
        _answer(form, "dont_know", note="SYN: ask the student"), _answer(_card(data, "system.domain"), "value", "experimental")])
    before = _digest(bdir)
    preview = SI.import_answers(bdir, answers, site_data=site_data)
    assert [a["outcome"] for a in preview["answers"]] == ["held", "would_record", "held", "would_record"] and _digest(bdir) == before
    rep = SI.import_answers(bdir, answers, site_data=site_data, apply=True)
    assert [a["outcome"] for a in rep["answers"]] == ["held", "recorded", "held", "recorded"]
    held = rep["answers"][0]
    assert held["reason"] == SI.HELD_REASON.format(n=3, card_id=env["card_id"]) and "decisions" not in held
    assert [n["note"] for n in rep["notes"]] == ["SYN: all but the first file", "SYN: checked against the logbook", "SYN: ask the student"]
    assert {d["decision"] for d in _decisions(bdir)} == {"confirm", "correct"} and len(_decisions(bdir)) == 2
    text = SI.render_report(rep)
    assert "Held: the note may name exceptions (not applied) (2)" in text and f"--note-read {env['card_id']}" in text
    # the note was read and names no exception: the answer is applied as it was given
    args = ["bundle", "site", "import", str(bdir), str(answers), "--site-data", str(site_data), "--apply"]
    assert cli.main([*args, "--note-read", env["card_id"], "--json"]) == 0
    again = json.loads(capsys.readouterr().out)
    assert [a["outcome"] for a in again["answers"]] == ["recorded", "already_recorded", "held", "already_recorded"]
    assert sum(1 for d in _decisions(bdir) if d["value"] == "operando") == 3


def test_a_reading_of_the_samples_is_not_offered_for_a_file_that_names_no_sample():
    """Review C1: the suggestion "operando" was read for the samples in the cell. A card about a file that states
    no sample (a pellet standard, an average) shows it as context, never as a one-click answer."""
    def card(lone, groups):
        return {"field": {"path": ENVIRONMENT}, "_questions": [{"question_id": "Q-syn0000001"}], "_groups": groups,
                "_lone": lone, "applies_to": {"count": len(groups), "summary": "SYN", "items": list(groups)},
                "answer": {"kind": "choice", "options": [{"value": v, "label": v} for v in ("operando", "ex_situ")]},
                "suggestion": None, "detail": "", "_lead": "", "covers": [{"on_value": {"decision": "correct"}, "on_accept": None}]}

    quote = [{"quote": "SYN: measured operando in the cell", "file": "syn.txt", "locator": "line 2"}]
    entry = {"field": ENVIRONMENT, "applies_to": "beamtime: the SYN sample groups", "question_ids": ["Q-syn0000001"],
             "suggested_value": "operando", "alternatives": [], "confidence": "high", "evidence": quote, "reasoning": "SYN."}
    sample, odd = card(False, ["rg-a", "rg-b"]), card(True, ["rg-z"])
    rows = H.apply([sample, odd], [H.normalise(entry, 0)], lambda answer, path, s: answer)
    assert sample["suggestion"]["value"] == "operando" and sample["covers"][0]["on_accept"] == {"decision": "correct", "value": "operando"}
    assert odd["suggestion"] is None and odd["covers"][0]["on_accept"] is None
    assert odd["_extra_context"][0]["label"] == ("A reading of your files suggests “operando” "
                                                 "(read for the samples in general, not for this file)")
    assert rows == [{"entry": 0, "suggested_on": 1, "context_on": 1}]
    named = card(True, ["rg-z"])  # an entry that names this very group is a reading of this file
    H.apply([named], [H.normalise({**entry, "applies_to": {"group_ids": ["rg-z", "rg-y"]}}, 0)], lambda answer, path, s: answer)
    assert named["suggestion"]["value"] == "operando"


def test_a_question_asked_once_for_groups_that_may_differ_is_one_card_per_group():
    """``partition == "sample=unrecorded"``: the files name no sample, so each group gets its own card, answered
    with ``only_scopes`` = that group (never one answer for all of them)."""
    q = {"question_id": "Q-syn0000001", "kind": "missing_value", "scope": "experiment", "blocking": True,
         "partition": "sample=unrecorded", "target_field_path": MATERIAL, "allowed_decisions": ["correct", "defer"],
         "per_scope_targets": {"group:rg-syn-a": ["miss-1"], "group:rg-syn-b": ["miss-2"]}, "targets": []}
    units, left = S._units(SimpleNamespace(groups={}), [q], ())
    assert [u["only_scopes"] for u in units] == [["group:rg-syn-a"], ["group:rg-syn-b"]] and not left
    assert S.card_id(MATERIAL, ["Q-syn0000001@group:rg-syn-a"]) != S.card_id(MATERIAL, ["Q-syn0000001@group:rg-syn-b"])


def test_one_token_naming_two_materials_is_split_by_the_groupings_own_sample_identity():
    """Two groups share a file-name token but the grouping reads another thickness for one: two cards, each answered
    question by question (a part of a same-reading group cannot use the one same-reading call)."""
    def group(loading):
        return {"basis": {"sample": {"sample_name": {"value": "synfilm"}, "loading_or_thickness": {"value": loading}}}}

    def q(n, gid):
        return {"question_id": f"Q-syn000000{n}", "kind": "confirm_value", "scope": f"group:{gid}", "blocking": True,
                "target_field_path": MATERIAL, "allowed_decisions": ["correct", "defer"], "same_reading_group": "SR-syn",
                "per_scope_targets": {f"group:{gid}": [f"cand-{n}"]}, "targets": [], "no_value": True}

    view = SimpleNamespace(groups={"rg-a": group("1nm"), "rg-b": group("1nm"), "rg-c": group("5nm")}, cands={})
    units, _left = S._units(view, [q(1, "rg-a"), q(2, "rg-b"), q(3, "rg-c")], ())
    assert [[m["question_id"] for m in u["questions"]] for u in units] == [["Q-syn0000001", "Q-syn0000002"], ["Q-syn0000003"]]
    assert all(u["each"] and not u["same_reading"] for u in units)
    same = SimpleNamespace(groups={"rg-a": group("1nm"), "rg-b": group("1nm"), "rg-c": group("1nm")}, cands={})
    (one,) = S._units(same, [q(1, "rg-a"), q(2, "rg-b"), q(3, "rg-c")], ())[0]
    assert one["same_reading"] and not one["each"] and len(one["questions"]) == 3


def test_a_member_with_no_stated_identity_is_its_own_part_and_the_split_survives():
    """Review I3: a 1 nm film, a 5 nm film and a group whose files state no sample at all share one token. The
    unidentified one is nobody's sample: it is a card of its own, and the two films stay two cards."""
    def group(loading):
        return {"basis": {"sample": {"sample_name": {"value": "synfilm"}, "loading_or_thickness": {"value": loading}}}}

    def q(n, gid):
        return {"question_id": f"Q-syn000000{n}", "kind": "confirm_value", "scope": f"group:{gid}", "blocking": True,
                "target_field_path": MATERIAL, "allowed_decisions": ["correct", "defer"], "same_reading_group": "SR-syn",
                "per_scope_targets": {f"group:{gid}": [f"cand-{n}"]}, "targets": [], "no_value": True}

    groups = {"rg-a": group("1nm"), "rg-b": group("5nm"), "rg-c": {"basis": {}}, "rg-d": {"basis": {"sample": {}}},
              "rg-e": {"basis": {"sample": {"sample_name": {"kind": "conflicting", "value": "synfilm"}}}}}
    view = SimpleNamespace(groups=groups, cands={})
    units, _left = S._units(view, [q(n, g) for n, g in enumerate(groups, start=1)], ())
    assert [[m["question_id"][-1] for m in u["questions"]] for u in units] == [["1"], ["2"], ["3"], ["4"], ["5"]]
    assert all(u["each"] and not u["same_reading"] for u in units)
    one_film = SimpleNamespace(groups={"rg-a": group("1nm"), "rg-b": group("1nm"), "rg-c": {"basis": {}}}, cands={})
    units, _left = S._units(one_film, [q(1, "rg-a"), q(2, "rg-b"), q(3, "rg-c")], ())
    assert [[m["question_id"][-1] for m in u["questions"]] for u in units] == [["1", "2"], ["3"]]
    # no member states an identity: the same-reading group is all there is, and it stays one card
    none = SimpleNamespace(groups={"rg-a": {"basis": {}}, "rg-b": {"basis": {}}}, cands={})
    (whole,) = S._units(none, [q(1, "rg-a"), q(2, "rg-b")], ())[0]
    assert whole["same_reading"] and len(whole["questions"]) == 2


def test_titles_and_details_are_plain_words(base, tmp_path):
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    S.export_site(bdir, tmp_path / "site", include=("optional", "approvals"), site_template=tmp_path / "none")
    data = json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())
    assert len(data["cards"]) > 30 and {c["answer"]["kind"] for c in data["cards"]} == {"choice", "text", "number", "yes_no"}
    paths = {(c["field"] or {}).get("path") for c in data["cards"]} - {None}
    for c in data["cards"]:
        title, detail = c["title"], c["detail"]
        assert P.not_plain(title) is None and P.not_plain(S._without_quotes(detail)) is None, (title, detail)
        assert title.endswith("?") and _sentences(title) == 1, title  # one sentence
        assert _sentences(S._without_quotes(detail)) <= 2, detail
        for text in (title, detail):
            assert "--" not in text and "isaac " not in text and not re.search(r"\bQ-[0-9a-f]{10}\b|\brg-[0-9a-f]+", text)
            assert not any(p in text for p in paths), (text, "a field path")
            assert not re.search(r"\b(confirm|correct|defer|decide)\b", text), text  # no decision names


def test_not_plain_names_what_it_found():
    assert "field path" in P.not_plain("What is the context.environment?")
    assert "flag" in P.not_plain("Answer with --same-reading")
    assert "decision" in P.not_plain("Use set_dose_reading here")
    assert "id" in P.not_plain("See Q-0123456789")
    assert "command" in P.not_plain("Run isaac bundle decide")
    assert P.not_plain("Was this done operando, in situ, ex situ or in silico?") is None
    assert P.not_plain("Is the applied potential 0.8 V for these 3 measurements?") is None
    assert P.ask_for(ENVIRONMENT, ["operando", "ex_situ"], subject="this measurement") == "Was this measurement done operando or ex situ?"
    assert P.ask_for(ENVIRONMENT, ["operando", "ex_situ"], subject="sample ZZ1", names_sample=True) == (
        "Was sample ZZ1 measured operando or ex situ?")


def test_a_kind_with_no_plain_wording_is_left_out_and_counted(base, tmp_path):
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    report = S.export_site(bdir, tmp_path / "site", include=("optional",), site_template=tmp_path / "none")
    data = json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())
    absorber = next(q for q in _open(bdir) if q["kind"] == "confirm_absorber")
    covered = {qid for c in data["cards"] for cover in c["covers"] for qid in cover["questions"]}
    assert absorber["question_id"] not in covered
    assert report["left_out"]["no plain wording for this kind of question yet (confirm absorber)"] == 1
    assert report["left_out"]["for information only: nothing is asked"] >= 1
    assert sum(report["left_out"].values()) + report["questions_covered"] == report["questions_open"]


def test_the_plain_words_are_the_local_websites(exported):
    """The Python tables are a port of ``apps/web/src/lib/plainQuestions.ts``: read that file and compare, so the
    question site and the local website keep saying the same thing."""
    ts = (Path(cli.__file__).resolve().parents[4] / "apps/web/src/lib/plainQuestions.ts").read_text(encoding="utf-8")

    def table(name):
        body = re.search(rf"const {name}: Readonly<Record<string, string>> = \{{(.*?)\n\}};", ts, re.S).group(1)
        return dict(re.findall(r"'([^']+)':\s*'([^']*)'", body))

    assert table("FIELD_ASK") == dict(P.FIELD_ASK)
    assert table("FIELD_NOUN") == dict(P.FIELD_NOUN)
    assert table("CHOICE_ASK") == dict(P.CHOICE_ASK)
    vague = re.search(r"const VAGUE = new Set\(\[(.*?)\]\)", ts).group(1)
    assert set(re.findall(r"'([^']+)'", vague)) == set(P.VAGUE)
    assert f"{P.NONE_SAY}`" in ts  # the missing-value sentence, word for word
    _bdir, _out, _report, data = exported
    env = _card(data, ENVIRONMENT)
    assert P.field_ask(ENVIRONMENT, [o["value"] for o in env["answer"]["options"]]) == (
        "Was this done operando, in situ, ex situ or in silico?")
    assert env["title"] == "Was sample ZZ1 measured operando, in situ, ex situ or in silico?"
    assert env["detail"].startswith(P.NONE_SAY) and _card(data, "system.domain")["title"] == P.field_ask("system.domain")
    assert P.field_noun("context.temperature_K") == "temperature" and P.field_noun("sample.material.name") == "sample material"
    assert P.field_noun("a.b.widget_name") == "widget name" and P.field_noun("x.thing.name") == "thing name"


# --- covers: every call a card lists is checked by a dry run -----------------------------------------------------------


def test_every_cover_is_a_call_the_decide_path_would_record(exported, tmp_path):
    bdir, _out, _report, data = exported
    before = _digest(bdir)
    tmp = tmp_path / "copy"
    tmp.mkdir()
    shutil.copy2(bdir / "bundle.json", tmp / "bundle.json")
    # C1: a sample question's cover also names its members, whose targets are its own
    members = {m for q in _open(bdir) for m in (q.get("sample_family") or {}).get("member_questions") or ()}
    for c in data["cards"]:
        for cover in c["covers"]:
            got = S.run_call(S.cover_call(cover, cover["on_dont_know"]), tmp, by=WHO, note=None, dry_run=True)
            asked = [q for q in cover["questions"] if q not in members]
            assert got["dry_run"] is True and len(got["recorded"]) >= len(asked), c["title"]
            value = c["answer"]["options"][0]["value"] if c["answer"]["options"] else "SYN value"
            got = S.run_call(S.cover_call(cover, cover["on_value"], value), tmp, by=WHO, note=None, dry_run=True)
            assert got["recorded"], c["title"]
    assert _digest(bdir) == before and _digest(tmp) == hashlib.sha256((bdir / "bundle.json").read_bytes()).hexdigest()


def test_a_question_no_call_can_answer_is_left_out_and_counted(base, tmp_path, monkeypatch):
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    stuck = next(q for q in _open(bdir) if q.get("target_field_path") == GROUP)
    real = S._dry

    def dry(plan, tmp):
        if plan.get("question_id") == stuck["question_id"]:
            return "SYN refusal: this question takes no answer now. More words."
        return real(plan, tmp)

    monkeypatch.setattr(S, "_dry", dry)
    report = S.export_site(bdir, tmp_path / "site", site_template=tmp_path / "none")
    data = json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())
    assert not [c for c in data["cards"] if (c["field"] or {}).get("path") == GROUP]
    assert report["left_out"]["no call can answer it now (SYN refusal: this question takes no answer now)"] == 1
    assert len(report["left_out"]) == 2  # that, and the questions not needed to export
    assert report["blocking_questions_covered"] == report["questions_blocking"] - 1


def test_a_per_group_question_the_beamtime_wide_answer_settles_is_not_asked_twice(exported):
    """The beamtime-wide technique question and the per-group ones that read one macro name: answering the first
    settles the others (simulated on a copy), so only the first is a card."""
    bdir, _out, report, data = exported
    technique = [c for c in data["cards"] if (c["field"] or {}).get("path") == "system.technique"]
    per_group = [q for q in _open(bdir) if q.get("target_field_path") == "system.technique" and q["scope"] != "experiment"]
    assert len(technique) == 1 and technique[0]["section"] == "beamtime" and len(per_group) == 6
    assert not any(q.get("blocking") for q in per_group)  # here they do not block, so they were never asked
    assert not [k for k in report["left_out"] if k.startswith("settled by")]


# --- images ------------------------------------------------------------------------------------------------------------


def test_image_copy_takes_a_png_and_names_it_by_its_hash(tmp_path):
    base_dir, img = tmp_path / "src", tmp_path / "out" / "img"
    (base_dir / "plots").mkdir(parents=True)
    (base_dir / "plots" / "curve.png").write_bytes(PNG)
    (base_dir / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    rel = S.copy_image(base_dir, "plots/curve.png", img)
    assert rel == f"img/{hashlib.sha256(PNG).hexdigest()}.png" and (tmp_path / "out" / rel).read_bytes() == PNG
    assert S.copy_image(base_dir, "photo.jpg", img).endswith(".jpg")
    assert S.copy_image(base_dir, "plots/curve.png", img) == rel and len(list(img.iterdir())) == 2


@pytest.mark.parametrize("name,content", [
    ("notes.png", b"SYN: this is text, not an image"),
    ("drawing.png", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>"),
    ("drawing.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
    ("data.csv", b"a,b\n1,2\n"),
    ("photo.png", b"\xff\xd8\xff\xe0" + b"\x00" * 32),  # a JPEG named .png: its bytes are not what its name says
])
def test_image_copy_refuses_what_is_not_a_png_or_jpeg(tmp_path, name, content):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / name).write_bytes(content)
    with pytest.raises(QC.ContextFileRefused):
        S.copy_image(tmp_path / "src", name, tmp_path / "img")
    assert not (tmp_path / "img").exists()


def test_image_copy_refuses_a_path_out_of_the_folder(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "secret.png").write_bytes(PNG)
    (tmp_path / "src" / "link.png").symlink_to(tmp_path / "secret.png")
    for rel in ("../secret.png", "link.png", "/etc/hosts", "missing.png"):
        with pytest.raises(QC.ContextFileRefused):
            S.copy_image(tmp_path / "src", rel, tmp_path / "img")


def test_a_cards_images_are_copied_and_stale_ones_removed(tmp_path):
    view = SimpleNamespace(bundle_dir=tmp_path / "bundle")
    (view.bundle_dir / "processing").mkdir(parents=True)
    (view.bundle_dir / "processing" / "plot.png").write_bytes(PNG)
    (view.bundle_dir / "processing" / "plot.svg").write_bytes(b"<svg></svg>")
    images: list[str] = []
    items = [{"kind": "plot", "label": "SYN curve", "source": "SYN", "path": "processing/plot.png", "base": "bundle", "alt": "SYN"},
             {"kind": "plot", "label": "SYN svg", "path": "processing/plot.svg", "base": "bundle"},
             {"kind": "image", "label": "SYN listed only", "path": "photo.png", "base": "source"},
             {"kind": "plot", "label": "SYN none", "not_shown": "this result has no plot"},
             {"kind": "quote", "label": "SYN logbook", "source": "SYN", "quote": "SYN line", "path": "syn.txt", "locator": "line 1"},
             {"kind": "quote", "label": "SYN logbook", "source": "SYN", "quote": "SYN line 2", "path": "syn.txt", "locator": "line 2"},
             {"kind": "example_files", "label": "SYN names", "names": ["a", "b"], "total": 5},
             {"kind": "table_row", "label": "SYN row", "cells": {"File Number": "1"}}]
    got = S._site_context(items, view, tmp_path / "out" / "data" / "img", images)
    assert [i["kind"] for i in got] == ["image", "quotes", "values", "values"]
    assert got[0]["image"] == f"img/{hashlib.sha256(PNG).hexdigest()}.png" and images == [got[0]["image"]]
    assert [q["quote"] for q in got[1]["items"]] == ["SYN line", "SYN line 2"]
    assert got[2] == {"kind": "values", "label": "SYN names", "source": None, "columns": ["File"], "rows": [["a"], ["b"]], "more": 3}
    assert got[3]["columns"] == ["File Number"] and got[3]["rows"] == [["1"]]


# --- where the export may be written -------------------------------------------------------------------------------------


def test_the_export_refuses_an_out_inside_a_git_working_tree(base, tmp_path, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    for out in (repo / "site", repo / "deep" / "er" / "site", repo):
        with pytest.raises(S.SiteRefused) as exc:
            S.export_site(base, out)
        assert exc.value.code == S.EXIT_OUTPUT_REFUSED and "git working tree" in str(exc.value)
    assert sorted(p.name for p in repo.iterdir()) == [".git"]  # nothing written
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /somewhere/else\n")  # a linked worktree's .git is a file
    assert cli.main(["bundle", "site", "export", str(base), "--out", str(worktree / "site")]) == S.EXIT_OUTPUT_REFUSED
    assert "git working tree" in capsys.readouterr().err and not (worktree / "site").exists()
    here = Path(cli.__file__).resolve().parent  # this repository itself
    assert S.git_tree_of(here) is not None and S.out_problem(here / "site-out", base) is not None


def test_the_export_refuses_the_bundle_folder_and_a_missing_bundle(base, tmp_path):
    for out in (base, base / "site", base.parent):
        with pytest.raises(S.SiteRefused) as exc:
            S.export_site(base, out)
        assert exc.value.code == S.EXIT_OUTPUT_REFUSED
    with pytest.raises(S.SiteRefused) as exc:
        S.export_site(tmp_path / "no-bundle", tmp_path / "site")
    assert exc.value.code == S.EXIT_NOT_FOUND
    with pytest.raises(S.SiteRefused):
        S.export_site(base, tmp_path / "site", include=("everything",))


def test_the_site_template_is_copied_without_its_tests_sample_data_or_local_files(base, tmp_path):
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    template = tmp_path / "template"
    for rel, text in {"index.html": "<p>SYN site</p>", "app.js": "// SYN", "api/answers.js": "// SYN",
                      ".vercelignore": "# SYN\ntest/\nsyn-local.txt\nlib/scratch\n", "syn-local.txt": "SYN",
                      "lib/scratch/x.js": "// SYN", "lib/syn-local.txt": "SYN",
                      "lib/data/kept.js": "// a nested folder named data is the site's own code",
                      "data/site-data.json": "{\"SYN\": \"sample\"}", "data/img/sample.png": "x", "test/fixture.txt": "SYN",
                      "dev-server.js": "// SYN", ".env.example": "SYN=1", "README.md": "SYN", ".vercel/project.json": "{}",
                      ".env.local": "SYN_PASSWORD=syn", ".dev-store.json": "{}", ".impeccable/notes.md": "SYN", "vercel.json": "{}",
                      "node_modules/pkg/index.js": "// SYN", "api/node_modules/x.js": "// SYN"}.items():
        (template / rel).parent.mkdir(parents=True, exist_ok=True)
        (template / rel).write_text(text)
    report = S.export_site(bdir, tmp_path / "site", site_template=template)
    got = sorted(str(p.relative_to(tmp_path / "site")) for p in (tmp_path / "site").rglob("*") if p.is_file())
    assert got == [".vercelignore", "api/answers.js", "app.js", "data/site-data.json", "index.html", "lib/data/kept.js",
                   "vercel.json"]
    assert json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())["format"] == "isaac.question_site"
    assert report["site_template"] == str(template) and "deploys as it is" in report["site_template_note"]


def test_the_export_records_what_it_shows_and_nothing_else(base, tmp_path):
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    before = M.load(bdir)
    report = S.export_site(bdir, tmp_path / "site", site_template=tmp_path / "none")
    after = M.load(bdir)
    mine = [e for e in after["exposures"] if e["command"] == S.EXPOSURE_COMMAND]
    assert len(mine) == report["exposures_recorded"] > 0
    assert len(after["exposures"]) == len(before.get("exposures") or ()) + len(mine)
    for key in ("scientist_decisions", "candidates", "missing_values", "conflicts", "record_groups"):
        assert after.get(key) == before.get(key), key
    assert sorted(p.name for p in bdir.iterdir() if p.name != ".bundle.lock") == sorted(
        p.name for p in base.iterdir() if p.name != ".bundle.lock")
    again = S.export_site(bdir, tmp_path / "site", site_template=tmp_path / "none")
    assert again["exposures_recorded"] == report["exposures_recorded"]
    assert len(M.load(bdir)["exposures"]) == len(after["exposures"])  # shown again: nothing new to record
    one = json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())
    assert [c["card_id"] for c in one["cards"]] == [c["card_id"] for c in json.loads(json.dumps(one))["cards"]]


def test_card_ids_are_stable_from_one_export_to_the_next(exported, base, tmp_path):
    _bdir, _out, _report, data = exported
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    S.export_site(bdir, tmp_path / "site", site_template=tmp_path / "none")
    again = json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())
    assert [c["card_id"] for c in again["cards"]] == [c["card_id"] for c in data["cards"]]
    c = _card(data, FORM)
    assert c["card_id"] == S.card_id(FORM, [c["covers"][0]["question_id"]])


# --- suggestions ---------------------------------------------------------------------------------------------------------


def test_a_value_the_files_give_is_a_suggestion_that_accept_confirms(base, tmp_path):
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    S.export_site(bdir, tmp_path / "site", include=("optional",), site_template=tmp_path / "none")
    data = json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())
    card = next(c for c in data["cards"] if c["title"] == "Is the applied potential 0.8 V for these 3 measurements?")
    s = card["suggestion"]
    # a potential read from the token '800mV' is ISAAC's reading of it: likely, and to be checked (review, minor)
    assert (s["value"], s["label"], s["basis"], s["confidence"]) == (0.8, "0.8 V", "files", "medium")
    assert s["reason"] == "Read from '800mV' in your files as 0.8 V; likely, please check." and s["evidence"][0]["quote"] == "800mV"
    assert S._same_written("0.8", 0.8) and S._same_written("Ex_Situ", "ex_situ") and not S._same_written("800mV", 0.8)
    assert card["covers"][0]["on_accept"] == {"decision": "confirm", "value": None} and card["covers"][0]["same_reading"]
    assert card["answer"]["kind"] == "number" and card["answer"]["unit"] == "V" and not card["blocking"]
    assert card["section"] == "optional"
    path = _answers_file(tmp_path, data, [_answer(card, "accept", 0.8)])
    rep = SI.import_answers(bdir, path, site_data=tmp_path / "site" / "data" / "site-data.json", apply=True)
    assert rep["counts"]["recorded"] == 1
    mine = [d for d in _decisions(bdir) if d["decision"] == "confirm"]
    assert len(mine) == 3 and all(d["decided_by"]["name"] == f"{WHO} (question site)" for d in mine)


def _suggest(base, tmp_path, entries, include=()):
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    (tmp_path / "hints.json").write_text(json.dumps(entries))
    report = S.export_site(bdir, tmp_path / "site", suggestions=tmp_path / "hints.json", include=include,
                           site_template=tmp_path / "none")
    return bdir, report, json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())


def test_a_suggestions_file_in_the_contracts_shape(base, exported, tmp_path):
    _b, _o, _r, plain = exported
    form = _card(plain, FORM, title_has="ZZ1")
    hint = {"value": "pellet", "confidence": "medium", "basis": "logbook", "reason": "The SYN logbook says so.",
            "evidence": [{"quote": "SYN pressed pellet", "file": "syn-logbook.txt", "locator": "line 3"}]}
    entries = {"suggestions": [
        {"question_id": form["covers"][0]["question_id"], "suggestion": hint},
        {"field": MATERIAL, "applies_to": "zz2", "suggestion": {**hint, "value": "SYN oxide", "basis": "reading"}},
        {"field": ENVIRONMENT, "suggestion": {**hint, "value": "in_situ", "basis": "general_knowledge", "confidence": "high"}},
        {"field": "system.domain", "suggestion": {**hint, "value": "experimental", "basis": "general_knowledge",
                                                  "confidence": "low", "reason": "Use --decision correct here."}},
        {"field": GROUP, "suggestion": {"value": "SYN group", "confidence": "certain", "basis": "rule", "reason": "SYN.",
                                        "evidence": hint["evidence"]}},
        {"field": "no.such.field", "suggestion": hint},
    ]}
    _bdir, report, data = _suggest(base, tmp_path, entries)
    got = _card(data, FORM, title_has="ZZ1")
    assert got["suggestion"] == {**hint, "label": "pellet"} and got["covers"][0]["on_accept"] == {"decision": "correct", "value": "pellet"}
    assert got["answer"]["common"][0] == "pellet" and got["detail"] == COVERS_3  # a hint found what no parser did
    assert _card(data, FORM, title_has="ZZ2")["suggestion"] is None
    oxide = _card(data, MATERIAL, title_has="ZZ2")
    assert oxide["suggestion"]["value"] == "SYN oxide" and oxide["suggestion"]["basis"] == "reading"
    assert _card(data, MATERIAL, title_has="ZZ1")["suggestion"] is None
    assert all(_card(data, p)["suggestion"] is None for p in (ENVIRONMENT, "system.domain", GROUP))
    problems = [r.get("problem") for r in report["suggestions_file"]]
    assert problems[:2] == [None, None] and "never a high-confidence" in problems[2] and "not plain words" in problems[3]
    assert "confidence is not one of" in problems[4] and problems[5] == "no card of this export matches it"
    assert report["with_suggestion"] == 2


def test_a_suggestions_file_in_a_reading_audits_shape(base, exported, tmp_path):
    bdir0, _o, _r, plain = exported
    form1, form2 = _card(plain, FORM, title_has="ZZ1"), _card(plain, FORM, title_has="ZZ2")
    material = _card(plain, MATERIAL, title_has="ZZ3")
    groups = {q["question_id"]: [s[6:] for s in q["per_scope_targets"]] for q in _open(bdir0)}
    quote = [{"quote": "SYN quoted line: a pressed pellet", "file": "syn-logbook.txt", "locator": "line 9"}]
    entries = [
        {"field": FORM, "applies_to": {"sample_token": "ZZ1", "group_ids": ["rg-none"]}, "confidence": "high",
         "question_ids": [form1["covers"][0]["question_id"]], "suggested_value": "pellet", "alternatives": ["film", "SYN remark"],
         "evidence": quote, "reasoning": "First SYN sentence. Second SYN sentence. Third SYN sentence.", "general_knowledge_note": None},
        {"field": FORM, "applies_to": {"group_ids": groups[form2["covers"][0]["question_id"]] + ["rg-more"]}, "question_ids": [],
         "suggested_value": "pressed disc", "alternatives": [], "confidence": "medium", "evidence": quote, "reasoning": "SYN."},
        {"field": MATERIAL, "applies_to": {"group_ids": []}, "question_ids": material["covers"][0]["questions"],
         "suggested_value": "SYN oxide (ZZ3)", "alternatives": ["SYN pellet", "drop the question: SYN prose"], "confidence": "high",
         "evidence": quote, "reasoning": "It fills sample.material.name for these runs. More."},
        {"field": "system.domain", "applies_to": "beamtime (all groups)", "question_ids": [], "suggested_value": "experimental",
         "alternatives": [], "confidence": "high", "evidence": quote, "reasoning": "SYN measured files."},
        {"field": "processing: is this SYN thing right?", "applies_to": "beamtime", "question_ids": [],
         "suggested_value": "SYN free text", "alternatives": [], "confidence": "medium", "evidence": quote, "reasoning": "SYN."},
        {"field": ENVIRONMENT, "applies_to": "beamtime", "question_ids": [], "suggested_value": None, "alternatives": [],
         "confidence": "low", "evidence": quote, "reasoning": "SYN: nothing certain."},
    ]
    _bdir, report, data = _suggest(base, tmp_path, entries)
    one = _card(data, FORM, title_has="ZZ1")
    assert one["suggestion"] == {"value": "pellet", "label": "pellet", "confidence": "high", "basis": "reading",
                                 "reason": "First SYN sentence. Second SYN sentence.", "evidence": quote}
    assert one["answer"]["common"][:2] == ["pellet", "film"] and "SYN remark" not in one["answer"]["common"]
    # a value off the field's list is never a one-click answer: it is shown beside the card, as quotes
    two = _card(data, FORM, title_has="ZZ2")
    assert two["suggestion"] is None and two["covers"][0]["on_accept"] is None
    assert two["context"][0] == {"kind": "quotes", "source": H.READING_SOURCE, "items": quote,
                                 "label": "A reading of your files suggests “pressed disc” (not on this field's list)"}
    # a text card: the value is the suggestion, the alternatives are named in the detail
    three = _card(data, MATERIAL, title_has="ZZ3")
    assert three["suggestion"]["value"] == "SYN oxide (ZZ3)" and three["suggestion"]["reason"] == H.GENERIC_REASON
    assert three["detail"] == f"Your files only write 'ZZ3'. {COVERS_3}"  # what one answer covers comes first
    assert _card(data, "system.domain")["suggestion"]["value"] == "experimental"  # beamtime-wide, by field
    env = _card(data, ENVIRONMENT)
    assert env["suggestion"] is None and env["context"][0]["label"] == "From your files, found by a reading"
    rows = report["suggestions_file"]
    # the beamtime-wide environment entry with no value is context on each of the three per-sample cards
    assert [(r["suggested_on"], r["context_on"]) for r in rows] == [(1, 0), (0, 1), (1, 0), (1, 0), (0, 0), (0, 3)]
    assert rows[4]["problem"] == "no card of this export matches it"  # no processing card in this export
    for c in data["cards"]:
        assert P.not_plain(c["title"]) is None and P.not_plain(S._without_quotes(c["detail"])) is None


def test_an_entry_for_some_of_a_cards_questions_is_never_the_whole_cards_suggestion():
    """Review I1: a card answers two questions (two electrodes). An entry naming one of them is context only; two
    entries naming both, with the same value, are the suggestion at the LOWER of their confidences."""
    def card():
        return {"field": {"path": MATERIAL}, "_questions": [{"question_id": "Q-syn0000001"}, {"question_id": "Q-syn0000002"}],
                "_groups": ["rg-a", "rg-b"], "applies_to": {"count": 2, "summary": "SYN", "items": ["a", "b"]},
                "answer": {"kind": "text", "options": []}, "suggestion": None, "detail": "", "_lead": "",
                "covers": [{"on_value": {"decision": "correct"}, "on_accept": None},
                           {"on_value": {"decision": "correct"}, "on_accept": None}]}

    quote = [{"quote": "SYN oxide film", "file": "syn.txt", "locator": "line 1"}]

    def entry(n, qids, confidence):
        return H.normalise({"field": MATERIAL, "applies_to": {"group_ids": []}, "question_ids": qids,
                            "suggested_value": "SYN oxide film", "alternatives": [], "confidence": confidence,
                            "evidence": quote, "reasoning": f"SYN reason {n}."}, n)

    def keep(answer, path, sug):
        return answer

    part = card()
    rows = H.apply([part], [entry(0, ["Q-syn0000001"], "high")], keep)
    assert part["suggestion"] is None and all(c["on_accept"] is None for c in part["covers"])
    assert part["_extra_context"][0]["label"].endswith("(read for only some of these measurements)")
    assert rows == [{"entry": 0, "suggested_on": 0, "context_on": 1}]
    both = card()
    rows = H.apply([both], [entry(0, ["Q-syn0000001"], "high"), entry(1, ["Q-syn0000002"], "low")], keep)
    assert both["suggestion"]["confidence"] == "low" and both["suggestion"]["reason"] == "SYN reason 1."
    assert all(c["on_accept"] == {"decision": "correct", "value": "SYN oxide film"} for c in both["covers"])
    assert [r["suggested_on"] for r in rows] == [1, 1]
    one = card()
    H.apply([one], [entry(0, ["Q-syn0000001", "Q-syn0000002", "Q-syn0000009"], "medium")], keep)
    assert one["suggestion"]["confidence"] == "medium"


def test_a_files_label_must_say_its_value_and_a_file_cannot_claim_basis_files():
    card = {"field": {"path": ENVIRONMENT}, "_questions": [{"question_id": "Q-syn0000001"}], "_groups": ["rg-a"],
            "applies_to": {"count": 1, "summary": "SYN", "items": ["a"]}, "suggestion": None, "detail": "", "_lead": "",
            "answer": {"kind": "choice", "options": [{"value": "in_situ", "label": "in situ"}, {"value": "operando", "label": "operando"}]},
            "covers": [{"on_value": {"decision": "correct"}, "on_accept": None}]}
    quote = [{"quote": "SYN in situ", "file": "syn.txt", "locator": "line 1"}]

    def entry(**s):
        return H.normalise({"question_id": "Q-syn0000001", "suggestion": {"value": "in_situ", "confidence": "low",
                                                                           "basis": "logbook", "reason": "SYN.", "evidence": quote, **s}}, 0)

    lying, honest = dict(card), {**card}
    H.apply([lying], [entry(label="operando")], lambda a, p, x: a)
    assert lying["suggestion"]["label"] == "in situ" and lying["covers"][0]["on_accept"]["value"] == "in_situ"
    H.apply([honest], [entry(label="In Situ")], lambda a, p, x: a)
    assert honest["suggestion"]["label"] == "In Situ"
    assert H.entry_problem(entry(basis="files")).startswith("a suggestions file cannot say the files give the value")


def test_a_high_suggestion_needs_a_quote_that_holds_the_value_and_none_without_evidence_is_offered():
    """Review I2: "high" is earned by a quote that holds the value (or a synonym the entry states). Without one the
    card says "medium"; an entry that quotes nothing is not used at all (a hint is shown with its line)."""
    def card():
        return {"field": {"path": ENVIRONMENT}, "_questions": [{"question_id": "Q-syn0000001"}], "_groups": ["rg-a"],
                "applies_to": {"count": 1, "summary": "SYN", "items": ["a"]}, "suggestion": None, "detail": "", "_lead": "",
                "answer": {"kind": "choice", "options": [{"value": "in_situ", "label": "in situ"}, {"value": "operando", "label": "operando"}]},
                "covers": [{"on_value": {"decision": "correct"}, "on_accept": None}]}

    def entry(quote, **kw):
        return H.normalise({"field": ENVIRONMENT, "applies_to": "beamtime", "question_ids": [], "suggested_value": "in_situ",
                            "alternatives": [], "confidence": "high", "reasoning": "SYN.",
                            "evidence": [{"quote": quote, "file": "syn.txt", "locator": "line 1"}] if quote else [], **kw}, 0)

    def keep(answer, path, sug):
        return answer

    results = {}
    for name, e in (("value", entry("SYN measured in situ in the cell")), ("raw", entry("SYN in_situ")),
                    ("other", entry("SYN measured in the cell")), ("synonym", entry("SYN measured in the cell", synonyms=["in the cell"]))):
        c = card()
        H.apply([c], [e], keep)
        results[name] = c["suggestion"]["confidence"]
    assert results == {"value": "high", "raw": "high", "other": "medium", "synonym": "high"}
    bare, c = entry(None), card()
    rows = H.apply([c], [bare], keep)
    assert c["suggestion"] is None and rows[0]["problem"].startswith("it quotes no evidence")
    contract = H.normalise({"field": ENVIRONMENT, "suggestion": {"value": "operando", "confidence": "high", "basis": "logbook",
                                                                 "reason": "SYN logbook."}}, 0)
    assert H.entry_problem(contract).startswith("it quotes no evidence")


def test_a_file_suggestion_the_decide_path_refuses_is_shown_as_context(base, exported, tmp_path):
    _b, _o, _r, plain = exported
    domain = _card(plain, "system.domain")
    entries = [{"field": "timestamps.acquired_start_utc / acquired_end_utc", "applies_to": "beamtime", "question_ids": [],
                "suggested_value": "the SYN local clock plus seven hours", "alternatives": [], "confidence": "medium",
                "evidence": [{"quote": "SYN #D line", "file": "syn.dat", "locator": "line 3"}], "reasoning": "SYN."},
               {"question_id": domain["covers"][0]["question_id"],
                "suggestion": {"value": "experimental", "confidence": "low", "basis": "rule", "reason": "SYN rule.",
                               "evidence": [{"quote": "SYN experimental run", "file": "syn.txt", "locator": "line 1"}]}}]
    _bdir, report, data = _suggest(base, tmp_path, entries, include=("optional",))
    starts = [c for c in data["cards"] if (c["field"] or {}).get("path") == "timestamps.acquired_start_utc"]
    assert starts and all(c["suggestion"] is None and c["covers"][0]["on_accept"] is None for c in starts)
    assert starts[0]["context"][0]["label"] == ("A reading of your files suggests “the SYN local clock plus seven hours” "
                                                "(not a value this field takes as it stands)")
    assert {d["title"] for d in report["suggestions_dropped"]} == {c["title"] for c in starts}
    assert _card(data, "system.domain")["suggestion"]["basis"] == "rule"


def test_hint_entries_are_matched_most_specific_first():
    card = {"field": {"path": FORM}, "_questions": [{"question_id": "Q-syn0000001"}], "_groups": ["rg-a", "rg-b"],
            "applies_to": {"count": 2, "summary": "2 measurements of sample SYN1 (no. 01)", "items": ["syn_a", "syn_b"]},
            "_sample": "SYN1 (no. 01)"}

    def reading(**kw):
        return H.normalise({"field": FORM, "question_ids": [], "applies_to": "beamtime", "suggested_value": "pellet",
                            "confidence": "high", "evidence": [], "reasoning": "SYN.", **kw}, 0)

    assert H._rank(reading(question_ids=["Q-syn0000001"]), card) == 1
    assert H._rank(reading(applies_to={"group_ids": ["rg-a", "rg-b", "rg-c"]}), card) == 2
    assert H._rank(reading(applies_to={"group_ids": ["rg-a"]}), card) is None  # the card is about more than it names
    assert H._rank(reading(), card) == 3 and H._rank(reading(field=MATERIAL), card) is None
    assert H._rank(reading(field="processing: SYN?"), card) is None  # no record field: never on a value card
    for applies, rank in (("SYN1", 2), ("syn1 (no. 01)", 2), ("syn_a", 2), (["syn_a", "syn_b", "syn_c"], 2), ("SYN2", None),
                          (["syn_a"], None), ("all", 3)):
        entry = H.normalise({"field": FORM, "applies_to": applies, "suggestion": {"value": "pellet"}}, 0)
        assert H._rank(entry, card) == rank, applies
    dose = {"field": None, "_target_id": S.DOSE_TARGET_ID, "_is_dose": True, "_questions": [], "_groups": ["rg-a"]}
    assert H._rank(reading(field="processing: is it beam damage or settling?"), dose) == 3
    assert H._rank(reading(field="processing: may filters be merged?"), dose) is None
    assert H._rank(reading(field="grouping: SYN", question_ids=[S.DOSE_TARGET_ID]), dose) == 1
    parts = H.normalise({"field": "context.electrochemistry.electrolyte", "applies_to": "beamtime", "question_ids": [],
                         "suggested_value": {"name": "SYN salt", "concentration_M": 0.1}, "confidence": "high"}, 0)
    name_card = {**card, "field": {"path": "context.electrochemistry.electrolyte.name"}}
    assert H._rank(parts, name_card) == 3 and H._value_for(parts, name_card) == "SYN salt"
    by_file = H.normalise({"field": FORM, "applies_to": "beamtime", "question_ids": [], "confidence": "high",
                           "suggested_value": {"SYNDIR/syn_a.mca": "pellet", "syn_b": "film"}}, 0)
    one_file = {**card, "applies_to": {"count": 1, "summary": "syn_a", "items": ["syn_a"]}}
    assert H._value_for(by_file, one_file) == "pellet" and H._value_for(by_file, card) is None
    assert H.two_sentences("One. Two. Three.") == "One. Two." and H.two_sentences("word " * 200) == ""
    assert H.two_sentences("Short one. Word " + "word " * 100 + "end.") == "Short one."


def test_an_ai_reading_loaded_into_the_bundle_becomes_a_suggestion_with_its_quote(base, tmp_path):
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    q = next(x for x in _open(bdir) if x.get("target_field_path") == FORM and "zz1" in (x.get("partition") or ""))
    for target in q["targets"]:
        M.annotate(bdir, target_id=target["id"], value="pellet", rationale="SYN reading", model_id="syn-model",
                   excerpt_locator="line 4", source_id=None, blind=False)
    hints = [h for h in Q.question(Q.consolidate(M.load(bdir)), q["question_id"])["hints"] if h["kind"] == "ai_suggestion"]
    assert [h["literal"] for h in hints] == ["pellet"]
    S.export_site(bdir, tmp_path / "site", site_template=tmp_path / "none")
    data = json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())
    card = _card(data, FORM, title_has="ZZ1")
    s = card["suggestion"]
    assert (s["value"], s["basis"], s["confidence"]) == ("pellet", "reading", "low") and "AI reading" in s["reason"]
    assert card["covers"][0]["on_accept"] == {"decision": "correct", "value": "pellet"}
    assert card["detail"] == COVERS_3 and card["answer"]["common"][0] == "pellet"
    assert _card(data, FORM, title_has="ZZ2")["suggestion"] is None
    # a reading of only some of a card's measurements is not offered for all of them
    q3 = next(x for x in _open(bdir) if x.get("target_field_path") == FORM and "zz3" in (x.get("partition") or ""))
    M.annotate(bdir, target_id=q3["targets"][0]["id"], value="film", rationale="SYN", model_id="syn-model",
               excerpt_locator="line 5", source_id=None, blind=False)
    S.export_site(bdir, tmp_path / "site", site_template=tmp_path / "none")
    data = json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())
    assert _card(data, FORM, title_has="ZZ3")["suggestion"] is None


# --- the processing card ------------------------------------------------------------------------------------------------


@pytest.fixture()
def dosed(base, tmp_path, monkeypatch):
    """The bundle with a processing result carrying the open dose question for its first two record groups (the
    fixture is not processed, so ``questions.curve_result`` is given synthetic results for them)."""
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    gids = [g["group_id"] for g in M.load(bdir)["record_groups"]][:2]

    def curve_result(bundle, gid):
        if gid not in gids:
            return None
        return {"result_id": f"proc-{gid}-syn", "group_id": gid, "state": "needs_review",
                "review_flags": ["protocol_draft_unreviewed", S.DOSE_QUESTION_FLAG],
                "dose_damage": {"outcome": "question", "spots_measured_more_than_once": 2, "why": "SYN reason",
                                "per_spot": {"spot 1": {"kind": "two_scans", "d12": -0.05, "direction": -1},
                                             "spot 2": {"kind": "none", "d12": -0.001, "direction": 0}}}}

    monkeypatch.setattr(Q, "curve_result", curve_result)
    return bdir, gids


def test_the_dose_question_is_one_beamtime_wide_processing_card(dosed, tmp_path):
    bdir, gids = dosed
    quote = [{"quote": "SYN: discard the first scan", "file": "syn-logbook.txt", "locator": "line 7"}]
    (tmp_path / "hints.json").write_text(json.dumps([
        {"field": "processing: beam damage, or was the sample still settling?", "applies_to": "beamtime", "question_ids": [],
         "suggested_value": "SYN: no single answer", "alternatives": ["settling"], "confidence": "medium", "evidence": quote,
         "reasoning": "SYN."}]))
    report = S.export_site(bdir, tmp_path / "site", suggestions=tmp_path / "hints.json", site_template=tmp_path / "none")
    data = json.loads((tmp_path / "site" / "data" / "site-data.json").read_text())
    (card,) = [c for c in data["cards"] if c["section"] == "processing"]
    assert card == data["cards"][-1] and not card["blocking"] and card["audience"] == "processing" and card["field"] is None
    assert card["title"] == ("At 2 of 4 spots measured more than once, the white line drops after the first scan: "
                             "is that beam damage?")
    assert card["answer"]["options"][2]["label"] == "Not beam damage: every scan is judged by the other rules"
    assert card["detail"].startswith("Seen in 2 of 9 measurements;") and P.not_plain(card["detail"]) is None
    assert [o["value"] for o in card["answer"]["options"]] == ["beam_damage", "first_scan_settling", "not_beam_damage"]
    assert set(o["value"] for o in card["answer"]["options"]) == set(B.DOSE_READINGS) and not card["answer"]["allow_text"]
    assert card["covers"] == [{"question_id": None, "same_reading": False, "only_scopes": None, "field": None,
                               "on_accept": None, "on_value": {"decision": "set_dose_reading"}, "on_dont_know": None,
                               "target": {"target": "experiment", "decision": "set_dose_reading"}, "questions": []}]
    assert card["applies_to"]["count"] == 2 and card["context"][0]["rows"][0][2] == "-5.0 %"
    # an entry about no record field is context on the processing card: quotes only, never a suggestion
    assert card["suggestion"] is None and card["context"][1] == {
        "kind": "quotes", "label": "From your files, found by a reading", "source": H.READING_SOURCE, "items": quote}
    assert report["cards_by_section"]["processing"] == 1 and report["suggestions_file"][0]["context_on"] == 1

    site_data = tmp_path / "site" / "data" / "site-data.json"
    answers = _answers_file(tmp_path, data, [_answer(card, "value", "first_scan_settling", note="SYN: see the logbook"),])
    rep = SI.import_answers(bdir, answers, site_data=site_data, apply=True)  # a note on a card for two measurements
    assert rep["answers"][0]["outcome"] == "held" and not _decisions(bdir)
    rep = SI.import_answers(bdir, answers, site_data=site_data, apply=True, notes_read=[card["card_id"]])
    assert rep["counts"]["recorded"] == 1 and rep["notes"][0]["note"] == "SYN: see the logbook"
    (d,) = [x for x in _decisions(bdir) if x["decision"] == "set_dose_reading"]
    assert d["target"] == {"kind": "experiment", "id": "experiment"} and d["value"] == "first_scan_settling"
    assert d["decided_by"]["name"] == f"{WHO} (question site)"
    # asked again after another reading was recorded: reported, never put over it; "I don't know" records nothing
    other = _answers_file(tmp_path, data, [_answer(card, "value", "beam_damage")], "other.json")
    rep = SI.import_answers(bdir, other, site_data=site_data, apply=True)
    assert rep["answers"][0]["outcome"] == "no_longer_asked" and "answered since" in rep["answers"][0]["reason"]
    unsure = _answers_file(tmp_path, data, [_answer(card, "dont_know")], "unsure.json")
    rep = SI.import_answers(bdir, unsure, site_data=site_data, apply=True)
    assert rep["answers"][0]["outcome"] == "nothing_to_record"
    assert len([x for x in _decisions(bdir) if x["decision"] == "set_dose_reading"]) == 1
    S.export_site(bdir, tmp_path / "site2", site_template=tmp_path / "none")  # decided: the card is gone
    again = json.loads((tmp_path / "site2" / "data" / "site-data.json").read_text())
    assert not [c for c in again["cards"] if c["section"] == "processing"]


# --- the import -----------------------------------------------------------------------------------------------------------


def _mixed(data):
    """One answer of each kind: a picked value, a typed value, a typed off-list word, "I don't know", a note."""
    return [
        _answer(_card(data, "system.domain"), "value", "experimental"),
        _answer(_card(data, GROUP), "value", "SYN Research Group", typed=True),
        _answer(_card(data, ENVIRONMENT), "value", "in a glovebox", typed=True),
        _answer(_card(data, MATERIAL, title_has="ZZ1"), "dont_know"),
        _answer(_card(data, FORM, title_has="ZZ2"), "value", "pellet", at="2100-02-01T11:30:00Z"),
    ]


def test_the_preview_writes_nothing(work, tmp_path, capsys):
    bdir, site_data, data = work
    answers = _answers_file(tmp_path, data, _mixed(data))
    before, files = _digest(bdir), sorted(p.name for p in bdir.iterdir())
    rep = SI.import_answers(bdir, answers, site_data=site_data)
    assert rep["applied"] is False and rep["statement"].startswith("Preview, nothing written: 4 answer(s) would be recorded of 5")
    assert rep["counts"]["would_record"] == 4 and rep["counts"]["would_keep_vocabulary_request"] == 1
    assert rep["counts"]["would_change_the_bundle"] == 5 and rep["counts"]["changed_the_bundle"] == 0
    assert _digest(bdir) == before and sorted(p.name for p in bdir.iterdir()) == files and not _decisions(bdir)
    assert cli.main(["bundle", "site", "import", str(bdir), str(answers), "--site-data", str(site_data)]) == 0
    out = capsys.readouterr().out
    assert "preview: nothing written" in out and "Would be applied (4)" in out and "Notes to read" not in out
    # C1: the sample's material card is ONE question (the sample question), so its call needs no --same-reading
    material = _card(data, MATERIAL, title_has="ZZ1")["covers"][0]["question_id"]
    assert material in out and "--as-said" in out and _digest(bdir) == before


def test_apply_records_the_right_decisions_under_the_right_name_with_the_cards_note(work, tmp_path):
    bdir, site_data, data = work
    answers = _answers_file(tmp_path, data, _mixed(data))
    rep = SI.import_answers(bdir, answers, site_data=site_data, apply=True)
    assert rep["applied"] and rep["counts"]["recorded"] == 4 and rep["counts"]["vocabulary_request_kept"] == 1
    decisions = _decisions(bdir)
    who = {d["decided_by"]["name"] for d in decisions}
    assert who == {f"{WHO} (question site)"}
    by_value = {}
    for d in decisions:
        by_value.setdefault((d["decision"], json.dumps(d.get("value"))), []).append(d)
    assert sorted((k[0], k[1], len(v)) for k, v in by_value.items()) == [
        ("correct", '"SYN Research Group"', 1), ("correct", '"experimental"', 1), ("correct", '"pellet"', 3),
        ("defer", "null", 3)]
    domain = _card(data, "system.domain")
    (d,) = by_value[("correct", '"experimental"')]
    assert d["note"] == f'question site card {domain["card_id"]} "Is this experimental or computational work?", answered {AT}'
    form = _card(data, FORM, title_has="ZZ2")
    assert {x["note"] for x in by_value[("correct", '"pellet"')]} == {
        f'question site card {form["card_id"]} "What form was sample ZZ2 (no. 02) in?", answered 2100-02-01T11:30:00Z'}
    assert rep["notes"] == []
    left = {q["question_id"] for q in _open(bdir) if q.get("blocking")}
    for card, gone in ((domain, True), (form, True), (_card(data, MATERIAL, title_has="ZZ1"), False)):
        assert all((qid not in left) == gone for qid in card["covers"][0]["questions"]), card["title"]
    text = SI.render_report(rep)
    assert "APPLIED" in text and "Applied (4)" in text and "Kept as a vocabulary request" in text


def test_dont_know_records_defer_for_every_question_of_the_card(work, tmp_path):
    bdir, site_data, data = work
    card = _card(data, MATERIAL, title_has="ZZ3")
    rep = SI.import_answers(bdir, _answers_file(tmp_path, data, [_answer(card, "dont_know")]), site_data=site_data, apply=True)
    assert rep["answers"][0]["outcome"] == "recorded"
    decisions = _decisions(bdir)
    assert [d["decision"] for d in decisions] == ["defer"] * 3 and all(d.get("value") is None for d in decisions)
    asked = {q["question_id"]: q for q in _open(bdir)}
    assert all(asked[qid].get("deferred") and asked[qid]["blocking"] for qid in card["covers"][0]["questions"])
    # deferred questions are not asked again by default; --include deferred asks them
    report = S.export_site(bdir, tmp_path / "site", site_template=tmp_path / "none")
    # C1: one question (the sample question; its three members are counted as it)
    assert report["left_out"]["answered \"I don't know\" earlier (add --include deferred to ask again)"] == 1
    again = S.export_site(bdir, tmp_path / "site2", include=("deferred",), site_template=tmp_path / "none")
    assert again["cards"] == report["cards"] + 1 and not [k for k in again["left_out"] if "earlier" in k]


def test_a_typed_word_off_the_list_is_kept_as_a_vocabulary_request_and_a_picked_one_is_not(work, tmp_path):
    bdir, site_data, data = work
    env = _card(data, ENVIRONMENT)
    assert env["answer"]["kind"] == "choice" and env["answer"]["allow_text"]
    typed = _answers_file(tmp_path, data, [_answer(env, "value", "in a glovebox", typed=True)])
    rep = SI.import_answers(bdir, typed, site_data=site_data, apply=True)
    assert rep["answers"][0]["outcome"] == "vocabulary_request_kept" and "--as-said" in rep["answers"][0]["decisions"][0]["command"]
    bundle = M.load(bdir)
    (request,) = bundle["vocabulary_requests"]
    assert request["field_path"] == ENVIRONMENT and request["term"] == "in a glovebox"
    assert request["requested_by"]["name"] == f"{WHO} (question site)" and env["card_id"] in request["note"]
    assert not bundle.get("scientist_decisions")  # a request is not a decision and not a value
    assert any(q["question_id"] == env["covers"][0]["question_id"] and q["blocking"] for q in _open(bdir))
    picked = _answers_file(tmp_path, data, [_answer(env, "value", "under a hood", typed=False)], "picked.json")
    rep = SI.import_answers(bdir, picked, site_data=site_data, apply=True)
    assert rep["answers"][0]["outcome"] == "refused" and "not one of the schema's allowed values" in rep["answers"][0]["reason"]
    assert len(M.load(bdir)["vocabulary_requests"]) == 1
    listed = _answers_file(tmp_path, data, [_answer(env, "value", "in_situ", typed=True)], "listed.json")
    rep = SI.import_answers(bdir, listed, site_data=site_data, apply=True)
    assert rep["answers"][0]["outcome"] == "recorded" and {d["value"] for d in _decisions(bdir)} == {"in_situ"}


def test_accept_is_refused_when_the_card_has_no_suggestion_or_another_one(base, exported, tmp_path):
    _b, _o, _r, plain = exported
    form = _card(plain, FORM, title_has="ZZ1")
    hint = {"value": "pellet", "confidence": "medium", "basis": "logbook", "reason": "The SYN logbook says so.",
            "evidence": [{"quote": "SYN pellet", "file": "syn.txt", "locator": "line 1"}]}
    bdir, _report, data = _suggest(base, tmp_path, [{"question_id": form["covers"][0]["question_id"], "suggestion": hint}])
    site_data = tmp_path / "site" / "data" / "site-data.json"
    card = _card(data, FORM, title_has="ZZ1")
    before = _digest(bdir)
    bad = _answers_file(tmp_path, data, [_answer(card, "accept", "film"),
                                         _answer(_card(data, FORM, title_has="ZZ2"), "accept", "pellet")])
    rep = SI.import_answers(bdir, bad, site_data=site_data, apply=True)
    assert [a["outcome"] for a in rep["answers"]] == ["refused", "refused"]
    assert "is now 'pellet', not the 'film' that was accepted" in rep["answers"][0]["reason"]
    assert "shows no suggestion to accept" in rep["answers"][1]["reason"]
    assert _digest(bdir) == before and "Refused (2)" in SI.render_report(rep)
    # the site-data changed under the answer (exported again with another hint): the old accept is refused
    changed = json.loads(site_data.read_text())
    _card(changed, FORM, title_has="ZZ1")["suggestion"]["value"] = "film"
    (tmp_path / "changed.json").write_text(json.dumps(changed))
    good = _answers_file(tmp_path, data, [_answer(card, "accept", "pellet")], "good.json")
    rep = SI.import_answers(bdir, good, site_data=tmp_path / "changed.json", apply=True)
    assert rep["answers"][0]["outcome"] == "refused" and _digest(bdir) == before
    rep = SI.import_answers(bdir, good, site_data=site_data, apply=True)
    assert rep["answers"][0]["outcome"] == "recorded"
    assert {(d["decision"], d["value"]) for d in _decisions(bdir)} == {("correct", "pellet")} and len(_decisions(bdir)) == 3


def test_a_card_the_bundle_no_longer_asks_is_reported_not_applied(work, tmp_path):
    bdir, site_data, data = work
    form, domain = _card(data, FORM, title_has="ZZ1"), _card(data, "system.domain")
    material = _card(data, MATERIAL, title_has="ZZ2")
    # answered since on the command line, with other values than the site's answers give
    M.decide_question(bdir, question_id=form["covers"][0]["question_id"], decision="correct", value="film", by="SYN Other", orcid=None)
    M.decide_question(bdir, question_id=material["covers"][0]["question_id"], decision="correct", value="SYN oxide",
                      by="SYN Other", orcid=None)  # C1: the sample question answers the whole sample
    before = _digest(bdir)
    answers = _answers_file(tmp_path, data, [_answer(form, "value", "pellet"), _answer(material, "value", "SYN nitride", typed=True),
                                             _answer(material, "dont_know", at="2100-01-01T00:00:00Z"),
                                             _answer(domain, "value", "experimental")])
    preview = SI.import_answers(bdir, answers, site_data=site_data)
    rep = SI.import_answers(bdir, answers, site_data=site_data, apply=True)
    for r in (preview, rep):
        got = {a["card_id"]: a["outcome"] for a in r["answers"] if a["outcome"] != "superseded"}
        assert got == {form["card_id"]: "no_longer_asked", material["card_id"]: "no_longer_asked",
                       domain["card_id"]: "would_record" if r is preview else "recorded"}
        assert [a["outcome"] for a in r["answers"]].count("superseded") == 1  # the earlier of two answers to one card
        assert r["bundle_changed_since_export"] is True
    stale = next(a for a in rep["answers"] if a["card_id"] == form["card_id"])
    assert stale["reason"] == "it was answered since with another answer, which is kept"
    assert "Cards no longer asked (not applied) (2)" in SI.render_report(rep)
    values = {(d["decided_by"]["name"], d["value"]) for d in _decisions(bdir)}
    assert values == {("SYN Other", "film"), ("SYN Other", "SYN oxide"), (f"{WHO} (question site)", "experimental")}
    assert _digest(bdir) != before
    # a card of another export, an unknown action, a name that is no name
    odd = _answers_file(tmp_path, data, [
        {**_answer(domain, "value", "x"), "card_id": "C-0000000000"}, {**_answer(form, "value", "pellet"), "action": "maybe"},
        _answer(_card(data, GROUP), "value", "SYN group", by="  ")], "odd.json")
    rep = SI.import_answers(bdir, odd, site_data=site_data, apply=True)
    assert [a["outcome"] for a in rep["answers"]] == ["refused"] * 3
    assert [a["reason"].split(" (")[0] for a in rep["answers"]] == [
        "not a card of this site-data.json", "its action is not one of accept, value, dont_know",
        "the answer names no person to record it under"]


def test_a_second_apply_records_nothing(work, tmp_path):
    bdir, site_data, data = work
    answers = _answers_file(tmp_path, data, _mixed(data))
    first = SI.import_answers(bdir, answers, site_data=site_data, apply=True)
    assert first["counts"]["changed_the_bundle"] == 5
    after, n = _digest(bdir), len(_decisions(bdir))
    for _ in range(2):
        again = SI.import_answers(bdir, answers, site_data=site_data, apply=True)
        assert again["counts"] == {**again["counts"], "answers": 5, "already_recorded": 5, "changed_the_bundle": 0,
                                   "would_change_the_bundle": 0}
        assert "recorded" not in again["counts"] and again["statement"].startswith("Recorded 0 answer(s) of 5")
        assert _digest(bdir) == after and len(_decisions(bdir)) == n and len(M.load(bdir)["vocabulary_requests"]) == 1
    preview = SI.import_answers(bdir, answers, site_data=site_data)
    assert preview["counts"]["already_recorded"] == 5 and _digest(bdir) == after
    assert "Already recorded (nothing new) (5)" in SI.render_report(preview)


def test_apply_refuses_a_bundle_in_a_runs_folder(exported, tmp_path, capsys):
    bdir0, out, _report, data = exported
    bdir = tmp_path / "_runs_v99" / "bundle"
    shutil.copytree(bdir0, bdir)
    answers = _answers_file(tmp_path, data, _mixed(data))
    site_data = out / "data" / "site-data.json"
    before = _digest(bdir)
    with pytest.raises(S.SiteRefused) as exc:
        SI.import_answers(bdir, answers, site_data=site_data, apply=True)
    assert exc.value.code == S.EXIT_OUTPUT_REFUSED and "_runs_v99" in str(exc.value) and "Nothing was recorded" in str(exc.value)
    assert cli.main(["bundle", "site", "import", str(bdir), str(answers), "--site-data", str(site_data), "--apply"]) == 4
    assert "_runs" in capsys.readouterr().err and _digest(bdir) == before
    preview = SI.import_answers(bdir, answers, site_data=site_data)  # a preview is allowed: it writes nothing
    assert preview["counts"]["would_record"] == 4 and _digest(bdir) == before


def test_files_that_are_not_this_bundles_are_refused_whole(work, tmp_path):
    bdir, site_data, data = work
    before = _digest(bdir)
    good = _answers_file(tmp_path, data, _mixed(data))
    other = tmp_path / "other.json"
    other.write_text(json.dumps({**json.loads(good.read_text()), "bundle_id": "01SYNOTHERBUNDLE"}))
    wrong_format = tmp_path / "wrong.json"
    wrong_format.write_text(json.dumps({**json.loads(good.read_text()), "format": "isaac.something_else"}))
    newer = tmp_path / "newer.json"
    newer.write_text(json.dumps({**json.loads(good.read_text()), "format_version": "2.0.0"}))
    (tmp_path / "not.json").write_text("SYN not json")
    for answers, sd in ((other, site_data), (wrong_format, site_data), (newer, site_data), (tmp_path / "not.json", site_data),
                        (tmp_path / "missing.json", site_data), (good, good), (site_data, site_data)):
        with pytest.raises(S.SiteRefused) as exc:
            SI.import_answers(bdir, answers, site_data=sd, apply=True)
        assert exc.value.code == S.EXIT_INPUT_REFUSED and "Nothing was recorded" in str(exc.value)
    with pytest.raises(S.SiteRefused) as exc:
        SI.import_answers(tmp_path / "no-bundle", good, site_data=site_data)
    assert exc.value.code == S.EXIT_NOT_FOUND and _digest(bdir) == before


def test_alternatives_are_values_the_quotes_hold_and_a_per_file_card_takes_only_its_files_quotes():
    """Review I5: reader prose ("drop the question …") is never shown as something the files write, and a value
    keyed by file name is shown with that file's quotes only, never another file's header."""
    def card(item):
        return {"field": {"path": MATERIAL}, "_questions": [{"question_id": "Q-syn0000001"}], "_groups": ["rg-a"],
                "applies_to": {"count": 1, "summary": item, "items": [item]}, "suggestion": None, "detail": "", "_lead": "",
                "answer": {"kind": "text", "options": []}, "covers": [{"on_value": {"decision": "correct"}, "on_accept": None}]}

    def keep(answer, path, sug):
        return answer

    quotes = [{"quote": "SYN oxide film, also called SYN layer", "file": "syn.txt", "locator": "line 1"}]
    prose = H.normalise({"field": MATERIAL, "applies_to": "beamtime", "question_ids": [], "suggested_value": "SYN oxide film",
                         "alternatives": ["SYN layer", "drop the question: reclassify the SYN files"], "confidence": "high",
                         "evidence": quotes, "reasoning": "SYN."}, 0)
    c = card("syn_a")
    H.apply([c], [prose], keep)
    public = {k: v for k, v in c.items() if not k.startswith("_") or k == "_alt"}  # what the site is sent
    assert c["_alt"] == "Your files also write “SYN layer”." and "drop the question" not in json.dumps(public)
    per_file = H.normalise({"field": MATERIAL, "applies_to": "beamtime", "question_ids": [], "confidence": "medium",
                            "suggested_value": {"SYNDIR/syn_a.mca": "SYN oxide", "SYNDIR/syn_b.mca": "SYN standard"},
                            "alternatives": ["drop the question"], "reasoning": "About both files. Recommended: drop it.",
                            "evidence": [{"quote": "#F SYNDIR/syn_b.mca header", "file": "SYNDIR/syn_b.mca", "locator": "line 1"},
                                         {"quote": "SYN oxide average", "file": "SYNDIR/syn_a.mca", "locator": "line 4"}]}, 0)
    a, b, other = card("syn_a"), card("syn_b"), card("syn_c")
    H.apply([a, b, other], [per_file], keep)
    assert a["suggestion"]["value"] == "SYN oxide" and [x["file"] for x in a["suggestion"]["evidence"]] == ["SYNDIR/syn_a.mca"]
    assert a["suggestion"]["reason"] == H.GENERIC_REASON and "_alt" not in a
    assert b["suggestion"]["value"] == "SYN standard" and [x["file"] for x in b["suggestion"]["evidence"]] == ["SYNDIR/syn_b.mca"]
    assert other["suggestion"] is None
    lone = H.normalise({**{k: v for k, v in per_file.items() if k != "n"}, "field": MATERIAL, "applies_to": "beamtime",
                        "question_ids": [], "confidence": "medium", "reasoning": "SYN.",
                        "suggested_value": {"SYNDIR/syn_a.mca": "SYN oxide"},
                        "evidence": [{"quote": "#F SYNDIR/syn_b.mca header", "file": "SYNDIR/syn_b.mca", "locator": "line 1"}]}, 0)
    c = card("syn_a")
    H.apply([c], [lone], keep)
    assert c["suggestion"] is None  # no quote from this file: nothing offered, nothing shown as its evidence


def test_a_yes_no_card_shows_every_value_one_yes_confirms():
    """Review I4: a yes over proposed labels confirms all of them, so every distinct value is shown with its count and
    an example file; a label with more values than a card can show is left out."""
    proposals = [{"group_id": f"rg-{n}", "value": f"SYN-{n % 3}", "first_file": f"syn_{n:02d}"} for n in range(20)]
    q = {"question_id": "Q-syn0000001", "kind": "condition_label", "label": "sample_id", "target_field_path": "sample.sample_id",
         "proposals": proposals, "allowed_decisions": ["confirm", "correct", "reject"]}
    view = SimpleNamespace(exportable=[p["group_id"] for p in proposals], live=[], groups={})
    view.reach = lambda gids: list(gids)
    view.group_name = lambda gid: gid
    card = S._label_card(view, {"named": q, "questions": [q]})
    (table,) = card["context"]
    assert table["columns"] == ["Proposed", "Measurements", "For example"] and "more" not in table
    assert table["rows"] == [["SYN-0", "7", "syn_00"], ["SYN-1", "7", "syn_01"], ["SYN-2", "6", "syn_02"]]
    assert table["label"] == "Every value proposed from the file names (20 measurements)"
    many = {**q, "proposals": [{**p, "value": f"SYN-{n}"} for n, p in enumerate(proposals)]}
    with pytest.raises(S._LeftOut, match="more than 12 different proposed values"):
        S._label_card(view, {"named": many, "questions": [many]})


def test_a_yes_no_card_records_yes_and_reports_no(base, tmp_path):
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    S.export_site(bdir, tmp_path / "site", include=("optional", "approvals"), site_template=tmp_path / "none")
    site_data = tmp_path / "site" / "data" / "site-data.json"
    data = json.loads(site_data.read_text())
    labels = [c for c in data["cards"] if c["title"].startswith("Should the record describe the sample's history as")]
    groups = [c for c in data["cards"] if c["covers"][0]["target"] and c["covers"][0]["target"]["decision"] == "confirm"]
    assert len(labels) == 2 and len(groups) == 9 and all(c["answer"]["kind"] == "yes_no" for c in labels + groups)
    assert all(c["section"] == "records" and c["blocking"] and c["unblocks"] == 1 for c in groups)
    assert groups[0]["context"] and groups[0]["context"][0]["kind"] == "values"
    yes, no = labels
    answers = _answers_file(tmp_path, data, [
        _answer(yes, "value", "yes"), _answer(no, "value", "no", note="SYN: the number is millivolts"),
        _answer(groups[0], "value", True), _answer(groups[1], "value", False, note="SYN: split these"),
        _answer(groups[2], "value", "perhaps"), _answer(groups[3], "dont_know")])
    rep = SI.import_answers(bdir, answers, site_data=site_data, apply=True)
    assert [a["outcome"] for a in rep["answers"]] == ["recorded", "nothing_to_record", "recorded", "nothing_to_record",
                                                      "refused", "nothing_to_record"]
    assert [n["note"] for n in rep["notes"]] == ["SYN: the number is millivolts", "SYN: split these"]
    bundle = M.load(bdir)
    status = {g["group_id"]: g["status"] for g in bundle["record_groups"]}
    assert status[groups[0]["covers"][0]["target"]["target"]] == "scientist_confirmed"
    assert status[groups[1]["covers"][0]["target"]["target"]] == "proposed"
    confirmed = [d for d in bundle["scientist_decisions"] if d["target"]["kind"] == "record_group"]
    assert len(confirmed) == 1 and confirmed[0]["decision"] == "confirm"
    again = SI.import_answers(bdir, answers, site_data=site_data, apply=True)
    assert [a["outcome"] for a in again["answers"]][:3] == ["already_recorded", "nothing_to_record", "already_recorded"]


# --- remembering ----------------------------------------------------------------------------------------------------------


def test_remember_writes_to_the_answer_memory_only_when_the_scientist_turned_it_on(work, tmp_path, monkeypatch):
    bdir, site_data, data = work
    memory = tmp_path / "memory" / "answer-memory.json"
    monkeypatch.setenv(AM.MEMORY_ENV, str(memory))
    first = _answers_file(tmp_path, data, [_answer(_card(data, FORM, title_has="ZZ1"), "value", "pellet")])
    rep = SI.import_answers(bdir, first, site_data=site_data, apply=True, remember=True)
    assert rep["counts"]["recorded"] == 1 and "is off, so nothing was remembered" in rep["answer_memory"]["statement"]
    assert not memory.exists()  # never turned on for them
    AM.set_enabled(True, by=WHO)
    second = _answers_file(tmp_path, data, [_answer(_card(data, FORM, title_has="ZZ2"), "value", "film")], "second.json")
    rep = SI.import_answers(bdir, second, site_data=site_data, apply=True)  # on, but --remember not given
    assert rep["counts"]["recorded"] == 1 and "answer_memory" not in rep and not AM.load(memory)["entries"]
    third = _answers_file(tmp_path, data, [_answer(_card(data, FORM, title_has="ZZ3"), "value", "powder")], "third.json")
    preview = SI.import_answers(bdir, third, site_data=site_data, remember=True)
    assert "Preview: nothing is remembered" in preview["answer_memory"]["statement"] and not AM.load(memory)["entries"]
    rep = SI.import_answers(bdir, third, site_data=site_data, apply=True, remember=True)
    entries = AM.load(memory)["entries"]
    assert rep["answer_memory"]["remembered"] == 1 and [(e["field"], e["value"]) for e in entries] == [(FORM, "powder")]
    assert entries[0]["by"] == f"{WHO} (question site)" and entries[0]["beamtime"] == FOLDER
    assert "Remembered on this computer" in SI.render_report(rep)


# --- the command line --------------------------------------------------------------------------------------------------


def test_the_commands_run_end_to_end(base, tmp_path, capsys):
    bdir = tmp_path / "bundle"
    shutil.copytree(base, bdir)
    out = tmp_path / "site"
    assert cli.main(["bundle", "site", "export", str(bdir), "--out", str(out), "--site-template", str(tmp_path / "none")]) == 0
    printed = capsys.readouterr()
    assert "Question site export: SYN_BL00_2100-01_Synthetic" in printed.out and "Cards by section:" in printed.out
    assert "13 card(s), 13 blocking; they cover 11 of 124 open question(s) (11 of 11 blocking)." in printed.out  # C1: 9 per-measurement sample-name questions are 3 sample questions
    assert "checking card 1 of 13" in printed.err
    assert cli.main(["bundle", "site", "export", str(bdir), "--out", str(out), "--include", "optional", "--json",
                     "--site-template", str(tmp_path / "none")]) == 0
    printed = capsys.readouterr()
    report = json.loads(printed.out)
    assert report["format"] == "isaac.question_site_export" and report["include"] == ["optional"] and not printed.err
    assert report["cards_by_section"]["optional"] > 10 and report["cards"] == sum(report["cards_by_section"].values())
    site_data = out / "data" / "site-data.json"
    data = json.loads(site_data.read_text())
    answers = _answers_file(tmp_path, data, [_answer(_card(data, "system.domain"), "value", "experimental")])
    args = ["bundle", "site", "import", str(bdir), str(answers), "--site-data", str(site_data)]
    assert cli.main([*args, "--apply", "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["format"] == "isaac.question_site_import" and rep["counts"]["recorded"] == 1
    assert rep["answers"][0]["decisions"][0]["command"].startswith(f"isaac bundle decide {bdir} --question Q-")
    assert cli.main([*args, "--apply"]) == 0 and "Already recorded (nothing new) (1)" in capsys.readouterr().out
    assert cli.main(["bundle", "site", "import", str(bdir), str(answers)]) == cli.EXIT_USAGE  # --site-data is required
    assert cli.main(["bundle", "site", "export", str(bdir)]) == cli.EXIT_USAGE  # --out is required
    capsys.readouterr()
    (tmp_path / "bad.json").write_text("SYN")
    assert cli.main(["bundle", "site", "export", str(bdir), "--out", str(out), "--suggestions", str(tmp_path / "bad.json")]) == 3
    assert "is not JSON" in capsys.readouterr().err


# --- review of #343: no path outside the import reaches the site; "high" rests only on a shown quote ---------------

def test_evidence_from_outside_the_import_is_never_shown_or_counted():
    from isaac_api.local_import import question_site_hints as SH

    assert SH.in_import("logbook.txt") and SH.in_import("sub/dir/run01.dat") and SH.in_import(None)
    for outside in ("/Users/someone/repo/docs/notes.md", "../Shared_Template.xlsx", "a/../../b.txt", "~/x.txt", "C:/x.txt"):
        assert not SH.in_import(outside), outside
    items = [
        {"quote": "held at 1.0 V", "file": "notes.txt", "locator": "line 3"},
        {"quote": "held at 1.0 V", "file": "notes.txt", "locator": "line 3"},  # the same quote twice
        {"quote": "operando", "file": "/Users/someone/repo/docs/answers.md", "locator": "line 55"},
        {"quote": "Example Lab", "file": "../Template.xlsx", "locator": "row 4"},
        {"quote": "", "file": "notes.txt"},
    ]
    assert SH.clean_evidence(items) == [{"quote": "held at 1.0 V", "file": "notes.txt", "locator": "line 3"}]


def test_high_needs_a_shown_quote_that_holds_the_value():
    from isaac_api.local_import import question_site_hints as SH

    card = {"answer": {"options": [{"value": "operando", "label": "operando"}]}}
    shown_elsewhere = {"synonyms": [], "suggestion": {"evidence": [
        {"quote": "spectra taken during the hold", "file": "notes.txt"},
        {"quote": "operando", "file": "/Users/someone/repo/docs/answers.md"}]}}
    assert not SH._quotes_value(shown_elsewhere, "operando", card), "a quote from outside the import never counts"
    hidden = {"synonyms": [], "suggestion": {"evidence": [{"quote": f"line {i}", "file": "n.txt"} for i in range(SH.MAX_EVIDENCE)]
                                              + [{"quote": "operando", "file": "n.txt"}]}}
    assert not SH._quotes_value(hidden, "operando", card), "a quote the card does not show never counts"
    shown = {"synonyms": [], "suggestion": {"evidence": [{"quote": "measured operando", "file": "n.txt"}]}}
    assert SH._quotes_value(shown, "operando", card)


def test_the_export_drops_any_quote_citing_a_path_outside_the_import():
    from isaac_api.local_import import question_site as S

    cards = [{"context": [{"kind": "quotes", "items": [{"quote": "q", "file": "/Users/someone/x.md"}]},
                          {"kind": "quotes", "items": [{"quote": "kept", "file": "run01.dat"}]}],
              "suggestion": {"evidence": [{"quote": "e", "file": "../T.xlsx"}, {"quote": "f", "file": "log.txt"}]}}]
    assert S._no_outside_paths(cards) == 2
    assert cards[0]["context"] == [{"kind": "quotes", "items": [{"quote": "kept", "file": "run01.dat"}]}]
    assert cards[0]["suggestion"]["evidence"] == [{"quote": "f", "file": "log.txt"}]


def test_a_value_derived_by_a_rule_is_worded_with_its_evidence_never_an_empty_quote():
    from isaac_api.local_import import question_site as S

    cand = {"evidence": [
        {"relation": "supports", "relative_path": "01_FAKE_run", "locator": "line 36 header #P0 column 2", "literal_value": "9999.0",
         "normalization": [{"step": "derive", "rule_id": "isaac.suggest.technique_from_configuration.v1"}]},
        {"relation": "context", "relative_path": "01_FAKE_run", "locator": "line 28 header #S", "literal_value": "gscan energy 1 2 3",
         "normalization": []},
        {"relation": "supports", "relative_path": "02_FAKE_run", "locator": "line 36 header #P0 column 2", "literal_value": "9999.0",
         "normalization": [{"step": "derive", "rule_id": "isaac.suggest.technique_from_configuration.v1"}]}]}
    ev = S._derived_evidence(cand)
    assert [e["file"] for e in ev] == ["01_FAKE_run", "02_FAKE_run"] and ev[0]["quote"] == "9999.0"
    reason = S._derived_reason(cand, "HERFD-XAS")
    assert "9999.0 eV" in reason and "Likely, please check" in reason and "Your files write ." not in reason
    assert S._derived_evidence({"evidence": []}) == []
