"""Skill polish r6 (fixer I: questions). SYNTHETIC fixtures only.

I1  Each group's start-time disagreement (#D local clock times with no zone) already offered the UTC instant the run's
    own file states (#E, an epoch). One beamtime-wide question now answers them all: `confirm` records, for every group
    it reaches, that group's OWN #E instant. It states its reach (how many groups, and which open ones it does not
    reach, with why). Each per-group question keeps its id and stays answerable. Never for a local clock time converted
    with a zone (BL4-3 XDC, DEC-87..89).
I2  `bundle group` says each not-a-measurement group's cannot_export_reason exactly as `bundle list groups` does.
I3  A question that would block only a group that cannot become a record (every run not a measurement run) is not
    blocking, and the payload names such groups once.
I4  `annotate --target` refuses a reading that says the files state nothing ("not stated"): it would be shown as an
    AI suggestion of a value. A word off a field's list is still kept (propose-terms drafts it).
I5  A sentence that names a cell only in passing, behind many per-group questions, is quoted once.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from test_local_import_records import BY, SEMANTICS

START = B.XDC_START_PATH
CELL = "context.electrochemistry.cell_type"
NOTES = "2099 SYNTHETIC semantics notes.txt"
PASSING = "SYNTHETIC: the spare grids are kept on the bench beside the flow cell."
#: runs whose second scan's #D line is moved a day, so their #D lines disagree (a start-time conflict per group)
DISAGREE = ("02_01_ZZ1_acid_after500Cycling_filter10_200mV", "06_03_ZZ3_alk_fresh_f30_900mV",
            "07_03_ZZ3_alk_fresh_f30_1000mV")
#: a run whose #E line is removed: its files state no UTC instant
NO_EPOCH = "07_03_ZZ3_alk_fresh_f30_1000mV"


def _run(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def _corpus(tmp: Path) -> Path:
    src = tmp / "corpus"
    shutil.copytree(SEMANTICS, src)
    for stem in DISAGREE:
        scan = next((src / f"{stem}_dir").glob("*_002.dat"))
        text = scan.read_text(encoding="utf-8")
        assert "#D Fri Jan 01 00:00:00 2100" in text
        scan.write_text(text.replace("#D Fri Jan 01 00:00:00 2100", "#D Sat Jan 02 00:00:00 2100", 1), encoding="utf-8")
    main = src / NO_EPOCH
    lines = main.read_text(encoding="utf-8").splitlines(keepends=True)
    main.write_text("".join(x for x in lines if not x.startswith("#E ")), encoding="utf-8")
    notes = src / NOTES
    text = notes.read_text(encoding="utf-8")
    notes.write_text(text.replace("SYNTHETIC: held at room temperature throughout\n",
                                  f"SYNTHETIC: held at room temperature throughout\n{PASSING}\n", 1), encoding="utf-8")
    return src


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("r6i")
    out = tmp / "grouped"
    assert cli.main(["import", str(_corpus(tmp)), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def grouped(pristine, tmp_path):
    target = tmp_path / "grouped"
    shutil.copytree(pristine, target)
    return target


def _start_questions(payload):
    return [q for q in payload["questions"] if q["kind"] == "resolve_conflict" and q["target_field_path"] == START
            and q.get("affects_record")]


def _beamtime(payload):
    return Q.question(payload, Q.STATED_UTC_START_QUESTION_ID)


def _epoch_of_run(b, run_id):
    return next(c for c in b["candidates"] if c["run_id"] == run_id and c["target_field_path"] == START
                and c["statement_key"] == "acquisition_epoch")


def _run_of(b, conflict_id):
    return next(cf["run_ids"][0] for cf in b["conflicts"] if cf["conflict_id"] == conflict_id)


# --- I1 ------------------------------------------------------------------------------------------------------------


def test_one_beamtime_question_offers_each_groups_own_utc_instant_and_states_its_reach(grouped):
    b = M.load(grouped)
    payload = Q.consolidate(b)
    per_group = _start_questions(payload)
    assert len(per_group) == 4  # the fixture's own disagreement plus the three made here
    q = _beamtime(payload)
    assert q is not None and q["kind"] == Q.STATED_UTC_START_KIND and q["scope"] == "experiment"
    assert q["allowed_decisions"] == ["confirm"] and "--decision confirm" in q["answer_command"]
    # it reaches every group whose run states one #E instant, and names the one that states none
    assert q["applies_to"]["groups"] == 3 and q["answers_at_once"] == 3
    [missed] = q["not_reached"]
    no_epoch_q = next(x for x in per_group if x["question_id"] == missed["question_id"])
    assert "no #E line" in missed["reason"] and missed["group_id"] == no_epoch_q["scope"][len("group:"):]
    assert "It reaches 3 group(s)" in q["text"] and "does not reach 1 group(s)" in q["text"]
    assert missed["question_id"] in q["text"]
    # each target is a per-group conflict, and each per-group question names the beamtime one
    reached = [x for x in per_group if x["question_id"] != missed["question_id"]]
    assert sorted(t["id"] for t in q["targets"]) == sorted(x["targets"][0]["id"] for x in reached)
    assert all(x["answered_at_once_by"] == q["question_id"] and q["question_id"] in x["text"] for x in reached)
    assert "answered_at_once_by" not in no_epoch_q
    # the values it would record are each run's own #E reading
    for t in q["targets"]:
        assert q["stated_utc_candidates"][t["id"]] == _epoch_of_run(b, _run_of(b, t["id"]))["candidate_id"]


def test_the_per_group_question_ids_are_unchanged_by_the_beamtime_question(grouped, monkeypatch):
    b = M.load(grouped)
    for mode in ({}, {"include_answered": True}):
        with_it = {q["question_id"]: q for q in Q.consolidate(b, **mode)["questions"]}
        monkeypatch.setattr(Q, "_STATED_UTC_MIN_GROUPS", 10 ** 6)
        without = {q["question_id"]: q for q in Q.consolidate(b, **mode)["questions"]}
        monkeypatch.undo()
        assert set(with_it) - set(without) == {Q.STATED_UTC_START_QUESTION_ID}
        assert set(without) <= set(with_it)
        for qid, q in without.items():
            assert (with_it[qid]["kind"], with_it[qid]["scope"], with_it[qid]["targets"]) == (q["kind"], q["scope"], q["targets"])


def test_confirm_records_each_runs_own_instant_once_and_keeps_every_question_answerable(grouped, capsys):
    q = _beamtime(Q.consolidate(M.load(grouped)))
    code, out, err = _run(capsys, "bundle", "decide", grouped, "--question", q["question_id"], "--decision", "confirm",
                          "--by", "S")
    assert code == 0, err
    reply = json.loads(out)
    assert reply["recorded_starts_total"] == 3 and reply["groups_recorded"] == 3
    assert "Recorded the start time of 3 group(s)" in reply["statement"] and "Not reached: 1 group(s)" in reply["statement"]
    b = M.load(grouped)
    decisions = B._decisions_by_target(b["scientist_decisions"])
    values = set()
    for t in q["targets"]:
        d = decisions[("conflict", t["id"])]
        own = _epoch_of_run(b, _run_of(b, t["id"]))
        assert d["decision"] == "correct" and d["value"] == own["value"]  # each run keeps its own value
        assert q["question_id"] in d["note"] and own["candidate_id"] in d["note"]
        values.add(d["value"])
    assert len(values) == 3
    # the reached per-group questions leave the open list; the one not reached stays
    payload = Q.consolidate(b)
    assert [x["question_id"] for x in _start_questions(payload)] == [q["not_reached"][0]["question_id"]]
    assert _beamtime(payload) is None
    # every per-group id still resolves (answered), and a later per-group answer replaces the beamtime one there
    answered = Q.consolidate(b, include_answered=True)
    assert Q.question(answered, q["question_id"]) is not None
    seen = Q.answered_question(b, q["question_id"])
    assert seen["status"] == "answered" and seen["answered_targets"] == 3 and seen["current_answers_total"] == 3
    assert "Each group holds its own start time" in seen["statement"]
    one = next(x for x in _start_questions(answered) if x.get("answered_at_once_by"))
    later = "2100-01-03T00:00:00Z"
    M.decide_question(grouped, question_id=one["question_id"], decision="correct", value=later, **BY)
    after = B._decisions_by_target(M.load(grouped)["scientist_decisions"])
    assert after[("conflict", one["targets"][0]["id"])]["value"] == later
    # confirming the beamtime question again keeps that group's own answer, and records nothing new
    again = M.decide_question(grouped, question_id=q["question_id"], decision="confirm", value=None, **BY)
    assert again["recorded_starts_total"] == 0 and "Nothing new recorded" in again["statement"]
    kept = {x["conflict_id"]: x for x in again["kept_their_own"]}
    assert kept[one["targets"][0]["id"]]["same"] is False
    assert again["kept_their_own_total"] == 3 and "1 run(s) hold another start of their own" in again["statement"]
    assert "2 run(s) already held that same instant" in again["statement"]


def test_a_group_answered_before_keeps_its_own_answer(grouped):
    payload = Q.consolidate(M.load(grouped))
    q = _beamtime(payload)
    first = next(x for x in _start_questions(payload) if x.get("answered_at_once_by"))
    M.decide_question(grouped, question_id=first["question_id"], decision="correct", value="2100-01-05T00:00:00Z", **BY)
    out = M.decide_question(grouped, question_id=q["question_id"], decision="confirm", value=None, **BY)
    assert out["recorded_starts_total"] == 2 and "1 other group(s) already held a start-time answer" in out["statement"]
    assert out["kept_their_own"] == []  # it was not asked here: the open question reaches only open groups
    asked = _beamtime(Q.consolidate(M.load(grouped)))
    assert asked is None  # every reached group is answered now
    d = B._decisions_by_target(M.load(grouped)["scientist_decisions"])[("conflict", first["targets"][0]["id"])]
    assert d["value"] == "2100-01-05T00:00:00Z"


def test_only_one_group_a_dry_run_and_a_value_are_handled(grouped):
    b = M.load(grouped)
    q = _beamtime(Q.consolidate(b))
    scope = sorted(q["per_scope_targets"])[0]
    before = (Path(grouped) / "bundle.json").read_bytes()
    dry = M.decide_question(grouped, question_id=q["question_id"], decision="confirm", value=None, dry_run=True, **BY)
    assert dry["dry_run"] is True and dry["recorded_starts_total"] == 3 and dry["statement"].startswith("Would record")
    assert (Path(grouped) / "bundle.json").read_bytes() == before
    with pytest.raises(M.MutationRefused, match="--value"):
        M.decide_question(grouped, question_id=q["question_id"], decision="confirm", value="2100-01-01T00:00:00Z", **BY)
    with pytest.raises(M.MutationRefused):
        M.decide_question(grouped, question_id=q["question_id"], decision="correct", value="2100-01-01T00:00:00Z", **BY)
    assert (Path(grouped) / "bundle.json").read_bytes() == before
    out = M.decide_question(grouped, question_id=q["question_id"], decision="confirm", value=None, only=scope, **BY)
    assert out["recorded_starts_total"] == 1 and out["recorded_starts"][0]["group_id"] == scope[len("group:"):]


def test_a_local_clock_time_converted_with_a_zone_is_never_a_stated_utc_instant():
    """BL4-3 XDC (DEC-87..89): a start converted with the zone a scientist gave is not an instant a file states."""
    reading = {"candidate_id": "cand-x", "value": "2100-01-01T08:00:00Z", "rule_id": B.CLOCK_ZONE_RULE_ID,
               "value_state": B.STATE_CANDIDATE_EXTRACTED}
    got, why = Q.stated_utc_reading([reading], ["run-x"])
    assert got is None and "not an instant a file states in UTC" in why
    epoch = {**reading, "rule_id": "bl15.spec.epoch_to_utc_iso.v1"}
    assert Q.stated_utc_reading([epoch], ["run-x"])[0] == epoch
    assert Q.stated_utc_reading([{**epoch, "value_state": B.STATE_REJECTED}], ["run-x"])[0] is None
    assert Q.stated_utc_reading([epoch], ["run-x", "run-y"])[0] is None


def test_readings_that_differ_are_refused_and_said_apart_from_no_epoch():
    """r6 review L1, L2: every usable UTC reading must give the same instant; #E readings that disagree are said so."""
    epoch = {"candidate_id": "c1", "value": "2100-01-01T00:00:00Z", "rule_id": "bl15.spec.epoch_to_utc_iso.v1",
             "value_state": B.STATE_CANDIDATE_EXTRACTED}
    other = {**epoch, "candidate_id": "c2", "value": "2100-01-02T00:00:00Z"}
    got, why = Q.stated_utc_reading([epoch, other], ["r"])
    assert got is None and "#E readings disagree (2 different instants)" in why
    got, why = Q.stated_utc_reading([epoch, {**other, "rule_id": "some.other.rule"}], ["r"])
    assert got is None and "2 different UTC readings" in why  # not only among #E readings
    assert "no #E line" in Q.stated_utc_reading([], ["r"])[1]


def _d_conflict(file_t, scan1_t, scan2_t="Fri Jan 01 03:00:00 2100"):
    return {"readings": [
        {"value": file_t, "witnesses": [{"source_id": "src-1", "locator": "line 3 header #D"}]},
        {"value": scan1_t, "witnesses": [{"source_id": "src-1", "locator": "line 8 header #D (scan 1)"},
                                         {"source_id": "src-2", "locator": "line 2 header #D"}]},
        {"value": scan2_t, "witnesses": [{"source_id": "src-1", "locator": "line 90 header #D (scan 2)"}]}]}


def test_the_gap_from_file_creation_to_the_first_scan_is_read_on_one_clock_and_bounded():
    """r6 review M1: #E is when the file was created; a run whose first scan started more than 10 min later is left out."""
    epoch = {"candidate_id": "c1", "value": "2100-01-01T00:00:00Z", "rule_id": "bl15.spec.epoch_to_utc_iso.v1",
             "value_state": B.STATE_CANDIDATE_EXTRACTED, "source_id": "src-1"}
    near = _d_conflict("Fri Jan 01 00:00:00 2100", "Fri Jan 01 00:01:38 2100")
    assert Q.file_to_first_scan_gap(near, "src-1") == 98
    got, _ = Q.stated_utc_reading([epoch], ["r"], near)
    assert got["gap_s"] == 98
    far = _d_conflict("Fri Jan 01 00:00:00 2100", "Fri Jan 01 00:20:00 2100")
    got, why = Q.stated_utc_reading([epoch], ["r"], far)
    assert got is None and "20 min after the file was created (more than 10 min)" in why
    assert Q.file_to_first_scan_gap(far, "src-other") is None
    assert "do not show both" in Q.stated_utc_reading([epoch], ["r"], {"readings": []})[1]


def test_the_question_says_e_is_the_file_creation_and_leaves_out_a_late_first_scan(grouped):
    b = M.load(grouped)
    q = _beamtime(Q.consolidate(b))
    assert "#E is when the file was created, not when the first scan started" in q["text"]
    assert "at most 0 s later" in q["text"] and q["largest_file_to_first_scan_s"] == 0
    assert q["max_file_to_first_scan_s"] == Q.MAX_FILE_TO_FIRST_SCAN_S and "more than 10 min later is left out" in q["text"]
    assert "protocol review (DEC-89)" in q["text"]
    # one run's first scan 20 min after its file was created: left out, with why
    late = q["targets"][0]["id"]
    cf = next(c for c in b["conflicts"] if c["conflict_id"] == late)
    for r in cf["readings"]:
        r["witnesses"] = [w for w in r["witnesses"] if "(scan" not in w["locator"]]
    src = next(w["source_id"] for r in cf["readings"] for w in r["witnesses"] if w["locator"].endswith("header #D"))
    cf["readings"].append({"reading_index": 9, "value": "Fri Jan 01 00:20:00 2100",
                           "witnesses": [{"source_id": src, "relative_path": "x", "locator": "line 8 header #D (scan 1)"}]})
    after = _beamtime(Q.consolidate(b))
    assert late not in {t["id"] for t in after["targets"]}
    assert any("20 min after the file was created" in x["reason"] for x in after["not_reached"])


def test_a_group_with_two_runs_is_not_reached_and_its_record_says_it_has_no_start(grouped, monkeypatch):
    """r6 review M2: a merged group would record two starts and the record take none: it is left out, and a record
    whose runs were given different starts says it ships without one."""
    monkeypatch.setattr(Q, "_STATED_UTC_MIN_GROUPS", 1)  # three groups in the fixture: two are merged here
    b = M.load(grouped)
    q = _beamtime(Q.consolidate(b))
    first, second = sorted(q["per_scope_targets"])[:2]
    keys = {g["group_id"]: g for g in b["record_groups"]}
    g1, g2 = keys[first[len("group:"):]], keys[second[len("group:"):]]
    g1["member_run_keys"] = list(g1["member_run_keys"]) + list(g2["member_run_keys"])
    g2["status"] = "rejected"
    merged = Q.consolidate(b)
    after = _beamtime(merged)
    assert first not in after["per_scope_targets"]
    [miss] = [x for x in after["not_reached"] if x["group_id"] == g1["group_id"]]
    assert len(miss["question_ids"]) == 2 and "say which run's start the record takes" in miss["reason"]
    assert len({x["group_id"] for x in after["not_reached"]}) == len(after["not_reached"])  # counted per group
    # each run given its own start: the composer fills nothing, and the record says so
    for qid in miss["question_ids"]:
        cf = Q.question(merged, qid)["targets"][0]["id"]
        M.record_decision(b, target_ids=[cf], decision="correct",
                          value=f"2100-01-0{1 + miss['question_ids'].index(qid)}T00:00:00Z", **BY)
    b = B.apply_derivations(b)
    report = Q.compositions(b)[g1["group_id"]]
    [w] = [w for w in report["warnings"] if w["code"] == "start_time_left_out"]
    assert w["differ"] and "given different start times" in w["text"] and "which run's start" in w["text"]
    assert w["question_id"] in miss["question_ids"]


def test_the_start_time_warning_names_the_beamtime_question_while_it_is_asked(grouped):
    """r6 review L3."""
    b = M.load(grouped)
    q = _beamtime(Q.consolidate(b))
    reports = Q.compositions(b)
    named = [w for r in reports.values() for w in r["warnings"] if w["code"] == "start_time_left_out"]
    reached = {t["id"] for t in q["targets"]}
    assert named
    for w in named:
        if w["targets"][0] in reached:
            assert w["beamtime_question_id"] == q["question_id"] and q["question_id"] in w["text"]
        else:
            assert "beamtime_question_id" not in w and q["question_id"] not in w["text"]
    # the Local Imports page, which does not show the beamtime question, leaves its sentence off
    per = next(x for x in Q.consolidate(b)["questions"] if x.get("answered_at_once_by"))
    shown = Q.without_answered_at_once(per)
    assert q["question_id"] in per["text"] and q["question_id"] not in shown["text"]


def test_the_listing_folds_the_per_group_questions_and_lists_them_on_request(grouped, capsys):
    code, out, err = _run(capsys, "bundle", "questions", grouped, "--limit", "200")
    assert code == 0, err
    page = json.loads(out)
    ids = [q["question_id"] for q in page["questions"]]
    assert Q.STATED_UTC_START_QUESTION_ID in ids
    assert page["answered_at_once"] == 3 and "--each-group" in page["answered_at_once_statement"]
    listed_start = [q for q in page["questions"] if q["kind"] == "resolve_conflict" and q["target_field_path"] == START]
    assert len(listed_start) == 1  # the group it does not reach
    beamtime = next(q for q in page["questions"] if q["question_id"] == Q.STATED_UTC_START_QUESTION_ID)
    assert "stated_utc_candidates" not in beamtime and beamtime["targets_count"] == 3
    code, out, _ = _run(capsys, "bundle", "questions", grouped, "--limit", "200", "--each-group")
    every = json.loads(out)
    assert "answered_at_once" not in every
    assert len([q for q in every["questions"] if q["kind"] == "resolve_conflict" and q["target_field_path"] == START]) == 4
    # a group's own list shows its own start-time question, not the beamtime one
    scope = sorted(Q.question(Q.consolidate(M.load(grouped)), Q.STATED_UTC_START_QUESTION_ID)["per_scope_targets"])[0]
    code, out, _ = _run(capsys, "bundle", "questions", grouped, "--scope", scope, "--limit", "200")
    kinds = [q["kind"] for q in json.loads(out)["questions"]]
    assert Q.STATED_UTC_START_KIND not in kinds and "resolve_conflict" in kinds


def test_one_group_alone_asks_no_beamtime_question(tmp_path):
    out = tmp_path / "plain"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    payload = Q.consolidate(M.load(out))
    assert len(_start_questions(payload)) == 1 and _beamtime(payload) is None


# --- I2 ------------------------------------------------------------------------------------------------------------


def test_group_and_list_groups_say_one_cannot_export_reason(grouped):
    b = M.load(grouped)
    live = Q.live_groups(b)
    keys = {r["run_key"]: r for r in b["runs"]}
    scanless, plain = live[0], live[1]
    for k in scanless["member_run_keys"]:
        keys[k]["scan_count"] = 0
    not_measured = {scanless["group_id"]: ["sample.sample_form"], plain["group_id"]: ["sample.sample_form"]}
    by_group, said = Q.not_a_measurement_reasons(b, not_measured)
    assert by_group == {scanless["group_id"]: "no_scans", plain["group_id"]: "not_a_measurement_run"}
    assert "not_a_measurement_run for 1" in said and "no_scans for 1" in said and scanless["group_id"] in said
    rows = cli.group_list_extras(b)
    assert rows[scanless["group_id"]]["cannot_export_reason"] == "no_scans"
    assert Q.cannot_export_reasons(b, not_measured)[scanless["group_id"]] == "no_scans"


# --- I3 ------------------------------------------------------------------------------------------------------------


def test_a_question_blocking_only_a_group_that_cannot_export_is_not_blocking(grouped, monkeypatch):
    b = M.load(grouped)
    payload = Q.consolidate(b)
    blocking = [q for q in payload["questions"] if q["blocking"] and q["scope"].startswith("group:")
                and q.get("blocks_group_ids") == [q["scope"][len("group:"):]]]
    assert blocking
    gid = blocking[0]["scope"][len("group:"):]
    real = Q.not_a_measurement_groups
    monkeypatch.setattr(Q, "not_a_measurement_groups",
                        lambda bundle, groups=None, reports=None: {gid: ["sample.sample_form"]} if groups is not None
                        else real(bundle, groups))
    after = Q.consolidate(b)
    for q in blocking[:3]:
        if q["scope"] != f"group:{gid}":
            continue
        now = Q.question(after, q["question_id"])
        assert now["blocking"] is False and now["cannot_export_groups"] == [gid]
        assert "cannot become a record" in now["why"]
    basis = after["blocking_basis"]["record_composer"]
    assert gid in basis["groups_that_cannot_export"] and "No question counts as blocking" in basis["cannot_export_statement"]
    assert after["counts"]["blocking"] < payload["counts"]["blocking"]
    # ids unchanged
    assert sorted(q["question_id"] for q in after["questions"]) == sorted(q["question_id"] for q in payload["questions"])


# --- I4 ------------------------------------------------------------------------------------------------------------


def test_a_reading_that_says_nothing_is_stated_is_refused_and_a_word_off_the_list_is_kept(grouped):
    b = M.load(grouped)
    target = next(c["candidate_id"] for c in b["candidates"] if c["target_field_path"] == CELL)
    kw = dict(excerpt_locator=None, source_id=None, model_id="syn", rationale="t")
    for blind, said in ((True, "not stated"), (False, "Not stated."), (True, "unknown")):
        with pytest.raises(M.MutationRefused, match="state no value"):
            M.annotate(grouped, target_id=target, value=said, blind=blind, **kw)
    assert not M.load(grouped).get("ai_interpretations")
    assert M.annotate(grouped, target_id=target, value="flow_cell", blind=True, **kw)["proposed_value"] == "flow_cell"
    # a word off the list is still kept: propose-terms drafts it as a vocabulary request
    assert M.annotate(grouped, target_id=target, value="PEEK spectro cell", blind=False, **kw)["proposed_value"]
    open_target = next(c["candidate_id"] for c in b["candidates"] if c["target_field_path"] == "sample.material.name")
    with pytest.raises(M.MutationRefused):
        M.annotate(grouped, target_id=open_target, value="not specified", blind=False, **kw)


def test_a_listed_value_is_kept_whatever_its_case_and_a_findings_file_skips_nothing_stated(grouped, monkeypatch):
    """r6 review L4 and M3."""
    monkeypatch.setattr(B, "allowed_values", lambda path: ["yes", "no", "unknown"] if path == "x.field" else None)
    from isaac_api.local_import import suggestions as S
    assert S.nothing_stated_reason("Unknown", "x.field") is None
    assert S.nothing_stated_reason("unknown", "y.field") is not None
    monkeypatch.undo()
    b = M.load(grouped)
    run = next(r for r in b["runs"] if r["run_candidate"])
    findings = {"format": "isaac.reading_findings", "findings": [
        {"id": "f1", "field_path": CELL, "value": "not stated", "applies_to": {"scope": "runs", "runs": [run["stem"]]},
         "source": {"path": NOTES, "locator": "line 1"}, "quote": "SYNTHETIC"}]}
    out = M.annotate_from_readings(grouped, findings, model_id="syn", apply=True)
    assert out["interpretations"] == 0
    assert any("state no value" in s["reason"] for s in out["skipped"])
    assert not M.load(grouped).get("ai_interpretations")


# --- I5 ------------------------------------------------------------------------------------------------------------


def test_a_sentence_named_in_passing_is_quoted_once(grouped):
    payload = Q.consolidate(M.load(grouped))
    asked = [q for q in payload["questions"] if q["target_field_path"] == CELL and q.get("no_value")
             and "only in passing" in q["text"]]
    assert len(asked) >= 2
    quoting = [q for q in asked if PASSING in q["text"]]
    assert len(quoting) == 1 and quoting[0]["text"].count(PASSING) == 1
    lead = quoting[0]["question_id"]
    for q in asked:
        if q["question_id"] != lead:
            assert f"the same sentence question {lead} quotes" in q["text"]
        # the words stay on the question's own hint, once (no related reading repeats that same line)
        assert [h["kind"] for h in q["hints"] if PASSING in json.dumps(h)] == ["file_literal"]
