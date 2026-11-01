"""r3c: the review of r3a's scan-header mentions, same-reading answers, folder ``.exp`` and excerpts. Synthetic only.

What these pin:

* HIGH: runs whose FILE NAMES read a field differently (``m600mV`` / ``m300mV``) never share a ``same_reading_group``
  whatever comment line they share; ``--same-reading`` is refused, all or nothing, for a value a member's file name
  contradicts, and names each member's file; a record whose set-point differs from a run's own file name is warned
  until a value is recorded for that run alone (an answer given to several runs at once does not settle it);
* MED-1: a voltage that is no set-point (a rate, a detector's, an amplitude, an over-potential, open circuit, over
  5 V, an exponent's or a comma decimal's tail) is no mention; a mention is quoted as written around it, the scale
  said is the differing mention's own, and the warning offers rejecting the header reading;
* MED-2: a mention contradicts a typed value only with a scale, or as its line's only mention; a cell adopted before
  mentions were compared is recorded with the mention as a note, never newly held back;
* MED-3: one ``.exp`` that several runs of a folder take their DATA_FILE from is a template, never "each run's own";
* MED-4: ``bundle excerpt`` numbers lines as the readers do (a form feed is no line break) and checks the line shown
  holds the evidence's words;
* LOW: a defer or reject is no ruling on the set-point (a reject drops its line from the comparison); a group is
  keyed on every evidence line, counts only listed questions and says an answered question is answered; the local
  questions screen hides questions outside live groups as the CLI does; a long excerpt range is joined only to the cap.
"""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from isaac_api import local_bundles as LB
from isaac_api.app import create_app
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import import template as T

from test_local_import_polish_r3a import CARRIED, SETPOINT, WHO, _group, _header_cands, _import, _rid, _typed
from test_local_import_reader_ssrl_xdc import make_scan

SCALE = "context.electrochemistry.potential_scale"
LINE = "Sample A in 1M KOH 0Vrhe"
SIX, SIX2, THREE = "01_SYNti_m600mV_096", "02_SYNti_m600mV_097", "03_SYNti_m300mV_098"


def _setpoint_questions(b: dict) -> list[dict]:
    return [q for q in Q.consolidate(b)["questions"] if q["target_field_path"] == SETPOINT]


@pytest.fixture()
def shared(tmp_path):
    """Three runs whose scan headers write one line; two file names say -0.6 V, one -0.3 V."""
    src = tmp_path / "SYN_bt43"
    for label in (SIX, SIX2, THREE):
        make_scan(src / f"{label}_A.001", free_text=("SYN gain 1e8", LINE))
    return _import(src, tmp_path / "bundle")


# --- HIGH: one shared line never gives runs whose names differ one set-point -------------------------------------


def test_runs_whose_file_names_differ_never_share_a_same_reading_group(shared):
    b = M.load(shared)
    run_of = {c["candidate_id"]: c["run_id"] for c in b["candidates"]}
    qs = {run_of[q["targets"][0]["id"]]: q for q in _setpoint_questions(b)}
    six = [qs[_rid(b, label)] for label in (SIX, SIX2)]
    three = qs[_rid(b, THREE)]
    assert len({q["same_reading_group"] for q in six}) == 1 and six[0]["same_reading_count"] == 2
    assert "same_reading_group" not in three
    text = six[0]["text"]
    assert f"the files: {SIX}_A.001, {SIX2}_A.001" in text and "their file names read alike for this field (-0.6)" in text
    assert [m["file_name"] for m in six[0]["same_reading_members"]] == [f"{SIX}_A.001", f"{SIX2}_A.001"]


def test_same_reading_is_refused_for_a_value_a_members_file_name_contradicts(shared):
    b = M.load(shared)
    q = next(q for q in _setpoint_questions(b) if q.get("same_reading_group"))
    before = len(b.get("scientist_decisions") or ())
    with pytest.raises(M.MutationRefused) as got:
        M.decide_question(shared, question_id=q["question_id"], same_reading=True, decision="correct", value=-0.3,
                          by=WHO, orcid=None)
    said = str(got.value)
    assert f"{SIX}_A.001 (" in said and f"{SIX2}_A.001 (" in said and "its file name writes m600mV" in said
    assert said.endswith("Nothing was recorded.")
    assert len(M.load(shared).get("scientist_decisions") or ()) == before  # all or nothing


def test_the_same_reading_reply_names_each_members_file(shared):
    q = next(q for q in _setpoint_questions(M.load(shared)) if q.get("same_reading_group"))
    got = M.decide_question(shared, question_id=q["question_id"], same_reading=True, decision="correct", value=-0.6,
                            by=WHO, orcid=None)
    assert len(got["recorded"]) == 2
    assert [m["file_name"] for m in got["same_reading_members"]] == [f"{SIX}_A.001", f"{SIX2}_A.001"]
    assert f"--same-reading answered 2 question(s), for: {SIX}_A.001, {SIX2}_A.001." in got["statement"]


def test_same_reading_on_an_answered_question_says_it_is_answered(shared):
    q = next(q for q in _setpoint_questions(M.load(shared)) if q.get("same_reading_group"))
    M.decide_question(shared, question_id=q["question_id"], same_reading=True, decision="correct", value=-0.6,
                      by=WHO, orcid=None)
    with pytest.raises(M.MutationRefused, match=f"Question {q['question_id']} is already answered"):
        M.decide_question(shared, question_id=q["question_id"], same_reading=True, decision="correct", value=-0.6,
                          by=WHO, orcid=None)


def _both_setpoints(out: Path, *labels: str, value: float = -0.6) -> list[str]:
    """One decide for several runs' header candidates at once (a batch)."""
    b = M.load(out)
    rids = {_rid(b, label) for label in labels}
    ids = [c["candidate_id"] for c in _header_cands(b, SETPOINT) if c["run_id"] in rids]
    M.decide(out, target_ids=ids, decision="correct", value=value, by=WHO, orcid=None)
    return ids


def test_a_record_differing_from_its_runs_file_name_is_warned_after_an_answer_for_several_runs(shared):
    _both_setpoints(shared, SIX, THREE)
    b = M.load(shared)
    three, six = _rid(b, THREE), _rid(b, SIX)
    assert R._potential_sources_warnings(b, _group(b, six), {six}, CARRIED) == []  # the record agrees with its name
    [w] = R._potential_sources_warnings(b, _group(b, three), {three}, CARRIED)
    assert w["record_differs_from_name"] and w["files_ruled"] and w["file_name_V"] == [-0.3]
    assert w["text"].startswith(f"the record carries -0.6 V on RHE for {three}, but its file name writes m300mV (-0.3 V), "
                                "and no value was recorded for this run on its own")
    assert "--decision correct --value <volts> --json" in w["command"]


def test_a_value_recorded_for_that_run_alone_settles_it(shared):
    _both_setpoints(shared, SIX, THREE)
    b = M.load(shared)
    three = _rid(b, THREE)
    [cand] = [c for c in _header_cands(b, SETPOINT) if c["run_id"] == three]
    assert len(R._potential_sources_warnings(b, _group(b, three), {three}, CARRIED)) == 1
    # the same volts, restated for this run alone: a new statement (never "nothing new recorded")
    got = M.decide(shared, target_ids=[cand["candidate_id"]], decision="correct", value=-0.6, by=WHO, orcid=None)
    assert got["recorded"] == [cand["candidate_id"]]
    b = M.load(shared)
    assert R._potential_sources_warnings(b, _group(b, three), {three}, CARRIED) == []


def test_validate_warns_once_the_record_carries_the_set_point(shared):
    _both_setpoints(shared, SIX, THREE)
    b = M.load(shared)
    ids = [m["value_id"] for m in b["missing_values"] if m["target_field_path"] == SCALE]
    ids += [c["candidate_id"] for c in b["candidates"] if c["target_field_path"] == SCALE]
    M.decide(shared, target_ids=ids, decision="correct", value="RHE", by=WHO, orcid=None)
    R.build_records(shared)
    got = [w for w in R.validate_records(shared, full=False).get("warnings") or ()
           if w["code"] == R.POTENTIAL_SOURCES_WARNING]
    b = M.load(shared)
    assert [w["group_id"] for w in got] == [_group(b, _rid(b, THREE))["group_id"]]
    assert got[0]["text"].startswith(f"the record carries -0.6 V on RHE for {_rid(b, THREE)}, but its file name writes")


# --- MED-1: what is a mention ------------------------------------------------------------------------------------


@pytest.mark.parametrize("line", ["5 mV/s", "10 mV s-1", "20 mV s^-1", "PMT 900V", "50mV amplitude", "eta = 300 mV",
                                  "η=0.3 V", "overpotential 300 mV", "held at OCP (0.95 V)", "E=0.3V OCP",
                                  "Ti foil 5 um, I0 1 V gain", "HV 1.2 V", "detector 1 V", "bias 0.5V", "scan rate 20 mV",
                                  "1e-3 V", "1E-3 V", "1,5 V", "x10^-3 V", "x10^3 V", "6 V", "SYN 12 V supply"])
def test_a_voltage_that_is_no_set_point_is_no_mention(line):
    assert Q.header_potential_mentions(line) == [], line


def test_a_set_point_beside_such_a_voltage_is_still_a_mention():
    assert [m["literal"] for m in Q.header_potential_mentions("1M KOH -0.6 V_RHE, 5 mV/s")] == ["-0.6 V_RHE"]
    assert [m["literal"] for m in Q.header_potential_mentions("-0.6V_RHE 50mV amplitude")] == ["-0.6V_RHE"]
    assert [m["literal"] for m in Q.header_potential_mentions("PMT 900V, 1M KOH 0.2Vrhe")] == ["0.2Vrhe"]
    assert [m["literal"] for m in Q.header_potential_mentions("CV 10 mV/s 0.5Vrhe")] == ["0.5Vrhe"]
    assert [m["volts"] for m in Q.header_potential_mentions("12V_RHE")] == [12.0]  # a scale: whatever its size


def test_a_mention_is_quoted_as_written_around_it():
    [m] = Q.header_potential_mentions("SYN E(0.3V)")
    assert (m["literal"], m["quote"]) == ("0.3V", "E(0.3V)")


@pytest.fixture()
def two_kinds(tmp_path):
    src = tmp_path / "SYN_bt43"
    make_scan(src / f"{SIX}_A.001", free_text=("SYN gain 1e8", "1M KOH -0.6Vrhe and 0.4 V"))
    return _import(src, tmp_path / "bundle")


def test_the_scale_said_is_the_differing_mentions_own(two_kinds):
    b = M.load(two_kinds)
    rid = _rid(b, SIX)
    [w] = R._potential_sources_warnings(b, _group(b, rid), {rid}, CARRIED)
    assert "'0.4 V' differs from the file name's and the record's (file name: no scale; scan header: no scale)" in w["text"]


def test_the_warning_offers_rejecting_the_header_reading(two_kinds):
    b = M.load(two_kinds)
    rid = _rid(b, SIX)
    [cand] = [c for c in _header_cands(b, SETPOINT) if c["run_id"] == rid]
    [w] = R._potential_sources_warnings(b, _group(b, rid), {rid}, CARRIED)
    assert ("or reject the header reading if this line states no set-point: isaac bundle decide <bundle_dir> --target "
            f"{cand['candidate_id']} --decision reject") in w["text"]


# --- LOW-1: a defer or a reject is no ruling ---------------------------------------------------------------------


def test_a_defer_is_no_ruling_and_a_reject_drops_only_its_line(two_kinds):
    b = M.load(two_kinds)
    rid = _rid(b, SIX)
    [cand] = [c for c in _header_cands(b, SETPOINT) if c["run_id"] == rid]
    M.decide(two_kinds, target_ids=[cand["candidate_id"]], decision="defer", value=None, by=WHO, orcid=None)
    b = M.load(two_kinds)
    assert R._setpoint_ruled(b, rid, [cand]) == (False, None)
    assert len(R._potential_sources_warnings(b, _group(b, rid), {rid}, CARRIED)) == 1
    M.decide(two_kinds, target_ids=[cand["candidate_id"]], decision="reject", value=None, by=WHO, orcid=None)
    b = M.load(two_kinds)
    assert R._setpoint_ruled(b, rid, [cand]) == (False, None)
    # the line states no set-point, said the scientist: not compared; the record still is, with the file name
    assert R._potential_sources_warnings(b, _group(b, rid), {rid}, CARRIED) == []
    off = {**CARRIED, SETPOINT: {**CARRIED[SETPOINT], "value": -0.3}}
    [w] = R._potential_sources_warnings(b, _group(b, rid), {rid}, off)
    assert w["record_differs_from_name"] and "'0.4 V'" not in w["text"]


# --- MED-2: which mentions contradict a typed value, and a cell adopted before them ---------------------------


@pytest.fixture()
def unscaled(tmp_path):
    src = tmp_path / "SYN_bt43"
    make_scan(src / "01_SYNti_dry_096_A.001", free_text=("SYN gain 1e8", "SYN 0.5 V and 1.6 V"))
    make_scan(src / "02_SYNti_wet_097_A.001", free_text=("SYN gain 1e8", "SYN at 0.5 V"))
    return _import(src, tmp_path / "bundle")


def _mention_rows(rep: dict) -> list[str]:
    return [line for x in rep["replaces_or_contradicts_a_file_reading"] if x["target_field_path"] == SETPOINT
            for line in x["readings"] if "a mention" in line]


def test_two_unscaled_mentions_of_one_line_contradict_no_typed_value(unscaled, tmp_path, capsys):
    assert _mention_rows(_typed(unscaled, tmp_path, "01_SYNti_dry_096", 0.8, capsys)) == []


def test_a_lines_only_mention_contradicts_a_typed_value(unscaled, tmp_path, capsys):
    [line] = _mention_rows(_typed(unscaled, tmp_path, "02_SYNti_wet_097", 0.8, capsys))
    assert "writes '0.5 V' in its line 'SYN at 0.5 V'" in line


def _their_sheet(bdir: Path, path: Path, potentials: dict[str, float]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Campaign Info"
    ws["A1"] = "ISAAC Campaign Metadata"
    wb.create_sheet("Configurations").append(["Config ID", "Technique"])
    wf = wb.create_sheet("File List")
    wf.append(["Folder Name", "Potential (V)", "Potential Scale"])
    for r in M.load(bdir)["runs"]:
        if r["label"] in potentials:
            wf.append([r["stem"], potentials[r["label"]], "RHE"])
    wb.save(path)
    return path


def test_a_cell_adopted_before_mentions_were_compared_is_recorded_with_the_mention_as_a_note(tmp_path, capsys,
                                                                                            monkeypatch):
    src = tmp_path / "SYN_bt43"
    make_scan(src / f"{SIX}_A.001", free_text=("SYN gain 1e8", LINE))
    out = _import(src, tmp_path / "bundle")
    theirs = _their_sheet(out, tmp_path / "SYN_theirs.xlsx", {SIX: -0.6})
    adopted = tmp_path / "adopted.xlsx"
    with monkeypatch.context() as m:  # adopt as it ran before r3a compared header mentions
        m.setattr(T, "header_potential_mentions", lambda bundle, run: [])
        capsys.readouterr()
        assert cli.main(["bundle", "template", "adopt", str(out), str(theirs), "--out", str(adopted), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["adopted"]["cells_adopted"] >= 1
    # adopted now, the mention ('0Vrhe') differs, and has a scale: a Disagreements row
    capsys.readouterr()
    assert cli.main(["bundle", "template", "adopt", str(out), str(theirs), "--out", str(tmp_path / "fresh.xlsx"),
                     "--json"]) == 0
    fresh = json.loads(capsys.readouterr().out)["adopted"]
    assert [d for d in fresh["disagreements"] if d.get("path") == SETPOINT]
    capsys.readouterr()
    assert cli.main(["bundle", "template", "import", str(out), str(adopted), "--by", WHO, "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    rid = _rid(M.load(out), SIX)
    assert [d for d in rep["decisions"] if d["target_field_path"] == SETPOINT and d["run_id"] == rid]
    assert not [x for x in rep["awaiting_ruling"] if x["target_field_path"] == SETPOINT]
    [named] = [x for x in rep["replaces_or_contradicts_a_file_reading"] if x["target_field_path"] == SETPOINT]
    assert named["outcome"] == "recorded_with_mention_note" and "'0Vrhe'" in named["readings"][0]
    capsys.readouterr()
    assert cli.main(["bundle", "template", "import", str(out), str(adopted), "--by", WHO]) == 0
    assert "a scan-header mention is no value read, so it is a note, not a hold" in capsys.readouterr().out


# --- MED-3: one .exp several runs take their DATA_FILE from -------------------------------------------------------


def test_one_exp_shared_by_a_folders_runs_is_said_to_be_a_template(tmp_path):
    src = tmp_path / "SYN_bt43"
    d = src / "mixed"
    for stem in ("SYNti_m600mV_096", "SYNti_m600mV_097", "SYNfoo_dry_001"):
        make_scan(d / f"{stem}_A.001", free_text=("SYN gain 1e8", "SYN comment"))
    (d / "template.exp").write_text("DATA_FILE SYNti_m600mV\n")
    b = M.load(_import(src, tmp_path / "bundle"))
    [mc] = b["merge_candidates"]
    [caution] = [c for c in mc["caution"] if c["code"] == G.CAUTION_NOTHING_CLASSIFIED]
    assert caution["data_file_shared"] == ["mixed/template.exp"]
    assert ("one .exp in their folder (mixed/template.exp) names SYNti_m600mV (DATA_FILE); that is a template, not "
            "evidence they are one measurement") in caution["statement"]
    assert "merging them could make one wrong record" in caution["statement"]
    assert "each run's own .exp" not in caution["statement"]


# --- MED-4 / LOW-4: excerpt lines as the readers number them ----------------------------------------------------


@pytest.mark.parametrize("odd", ["\x0c", "\x85", "\x1c", "\x1d", "\x1e", "\x0b"])
def test_excerpt_labels_the_line_the_readers_numbered(tmp_path, odd):
    src = tmp_path / "SYN_bt43"
    make_scan(src / f"{SIX}_A.001", free_text=(f"SYN gain{odd}1e8", LINE, "SYN note"))
    out = _import(src, tmp_path / "bundle")
    b = M.load(out)
    [cand] = _header_cands(b, SETPOINT)
    [hit] = M.excerpt(b, cand["candidate_id"], source=str(src))["excerpts"]
    assert f"   10: {LINE}" in hit["text"].split("\n") and "note" not in hit


def test_excerpt_says_when_the_line_shown_lacks_the_evidences_words(tmp_path):
    src = tmp_path / "SYN_bt43"
    make_scan(src / f"{SIX}_A.001", free_text=("SYN gain 1e8", LINE, "SYN note"))
    out = _import(src, tmp_path / "bundle")
    b = M.load(out)
    [cand] = _header_cands(b, SETPOINT)
    cand["evidence"][0]["locator"] = "line:11"  # a locator one line off the words it was read with
    [hit] = M.excerpt(b, cand["candidate_id"], source=str(src))["excerpts"]
    assert hit["note"].startswith("line 11 as read now does not contain the text the import read there")
    assert LINE not in hit["note"]  # never the evidence's words, only the file's own lines


def test_a_long_range_is_joined_only_to_the_cap():
    lines = ["x" * 50] * 5000
    body, last = M._joined_within(lines, 1, 5000, M.MAX_EXCERPT_CHARS)
    assert M.MAX_EXCERPT_CHARS < len(body) < M.MAX_EXCERPT_CHARS + 60 and last < 100


def test_a_target_line_cut_partway_says_so(tmp_path, monkeypatch):
    src = tmp_path / "SYN_bt43"
    make_scan(src / f"{SIX}_A.001", free_text=("SYN gain 1e8", "SYN " + "y" * 5000))
    out = _import(src, tmp_path / "bundle")
    b = M.load(out)
    cand = next(c for c in b["candidates"] if any(e.get("locator") for e in c["evidence"]))
    real = M._locators
    monkeypatch.setattr(M, "_locators", lambda c: [{k: v for k, v in x.items() if k != "literal_value"}
                                                   | {"locator": "line:10"} for x in real(c)][:1])
    [hit] = M.excerpt(b, cand["candidate_id"], source=str(src))["excerpts"]
    assert hit["truncated"] and "line 10, the one the locator names, is cut at the 4000 characters shown" in hit["note"]


# --- LOW-2: a group is keyed on every line, and counts only the listed questions ----------------------------


def _q(qid: str, cid: str, **more) -> dict:
    return {"question_id": qid, "kind": "confirm_value", "no_value": True, "target_field_path": SETPOINT,
            "targets": [{"kind": "candidate", "id": cid}], "text": "SYN.",
            "answer_command": f"isaac bundle decide <bundle_dir> --question {qid} --decision correct", **more}


def _cand(cid: str, run_id: str, *lines: str) -> dict:
    return {"candidate_id": cid, "run_id": run_id, "rule": f"{B.XDC_COMMENT_RULE_ID}: synthetic",
            "evidence": [{"literal_value": x, "relative_path": f"{run_id}.001"} for x in lines]}


def test_a_group_is_keyed_on_every_evidence_line_and_counts_only_live_questions():
    bundle = {"runs": [{"run_id": f"run-00{i}", "stem": f"SYN_dry_00{i}"} for i in range(1, 6)], "sources": []}
    cands = {"c1": _cand("c1", "run-001", "L1", "L2"), "c2": _cand("c2", "run-002", "L1", "L3"),
             "c3": _cand("c3", "run-003", "L1", "L2"), "c4": _cand("c4", "run-004", "L1", "L2"),
             "c5": _cand("c5", "run-005", "L1", "L2")}
    qs = [_q("Q-1", "c1"), _q("Q-2", "c2"), _q("Q-3", "c3"), _q("Q-4", "c4", outside_live_groups=True),
          _q("Q-5", "c5", outside_live_groups=True)]
    Q._note_same_reading_groups(qs, cands, bundle)
    by = {q["question_id"]: q for q in qs}
    assert "same_reading_group" not in by["Q-2"]  # its first line agrees, its second does not
    assert by["Q-1"]["same_reading_group"] == by["Q-3"]["same_reading_group"] and by["Q-1"]["same_reading_count"] == 2
    assert "the same comment lines ('L1', 'L2')" in by["Q-1"]["text"]
    assert by["Q-4"]["same_reading_group"] != by["Q-1"]["same_reading_group"]  # the hidden ones apart


# --- LOW-3: the local questions screen hides what the CLI hides ---------------------------------------------------


def test_the_questions_screen_hides_questions_outside_live_groups_as_the_cli_does(tmp_path, monkeypatch, capsys):
    root = tmp_path / "bundles"
    src = tmp_path / "SYN_bt43"
    for stem in ("align_SYNfoil_001", "SYNti_dry_015", "SYNti_wet_016"):
        make_scan(src / f"{stem}_A.001", free_text=("SYN gain 1e8", LINE))
    out = root / "alpha"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    M.group(out)
    [align] = [g for g in M.load(out)["record_groups"] if g["role"] == "alignment"]
    M.decide(out, target_ids=[align["group_id"]], decision="reject", value=None, by=WHO, orcid=None)
    capsys.readouterr()
    assert cli.main(["bundle", "questions", str(out), "--limit", "200"]) == 0
    page_cli = json.loads(capsys.readouterr().out)
    monkeypatch.setenv(LB.LOCAL_BUNDLES_ENV, str(root))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    LB._check_memo.clear()
    client = TestClient(create_app(), base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50123),
                        headers={LB.LOCAL_HEADER: "1"})
    page = client.get("/api/local-bundles/alpha/questions").json()
    assert page["hidden_outside_live_groups"] == page_cli["hidden_outside_live_groups"] > 0
    assert page["total"] == page_cli["total"]
    assert "include_outside_live_groups=true lists them" in page["hidden_outside_live_groups_statement"]
    assert "on a field each record takes from its own runs" in page["hidden_outside_live_groups_statement"]
    every = client.get("/api/local-bundles/alpha/questions", params={"include_outside_live_groups": True}).json()
    assert "hidden_outside_live_groups" not in every
    assert every["total"] == page["total"] + page["hidden_outside_live_groups"]
