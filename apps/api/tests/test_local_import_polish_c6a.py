"""Polish c6-a: three walkthrough findings on the local-first import. Synthetic only.

* (HIGH1) A value whose ONLY evidence is a notes (logbook) sentence about the WHOLE beamtime — no sample section
  lists the run, the sentence names no sample — is beamtime context, never a silent extracted value of a run
  (the skill's Rule 6). It is held for review (``needs_review``), so every group it reaches is asked, with the
  sentence shown. A sample section's own statement still reads as that section's runs' value. A bundle an
  older build stored is held the same way when it is loaded and saved, and keeps every question id.
* (HIGH2) A question ``confirm`` can answer states the exact value (and unit) ``confirm`` records.
* (LOW5) A sample question asked once for several groups names their sample reading as the files write it.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

from test_local_import_records import BY, SEMANTICS

CELL = "context.electrochemistry.cell_type"
SETPOINT = "context.electrochemistry.potential_setpoint_V"
NOTES = "2099 SYNTHETIC semantics notes.txt"
#: Before any sample section: about the whole beamtime, and not about any measurement's cell.
BEAMTIME_SENTENCE = "SYNTHETIC: the spare grids are kept on the bench beside the flow cell."
#: Inside the `Sample 2` section: that section's own statement.
SECTION_SENTENCE = "SYNTHETIC: measured in an H-cell."


def _corpus(tmp: Path) -> Path:
    src = tmp / "corpus"
    shutil.copytree(SEMANTICS, src)
    notes = src / NOTES
    text = notes.read_text(encoding="utf-8")
    text = text.replace("SYNTHETIC: held at room temperature throughout\n",
                        f"SYNTHETIC: held at room temperature throughout\n{BEAMTIME_SENTENCE}\n", 1)
    text = text.replace("Operator: Operator Beta (synthetic)\n", f"Operator: Operator Beta (synthetic)\n{SECTION_SENTENCE}\n", 1)
    assert BEAMTIME_SENTENCE in text and SECTION_SENTENCE in text
    notes.write_text(text, encoding="utf-8")
    return src


@pytest.fixture(scope="module")
def noted_pristine(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("c6a")
    out = tmp / "grouped"
    assert cli.main(["import", str(_corpus(tmp)), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def noted(noted_pristine, tmp_path):
    target = tmp_path / "grouped"
    shutil.copytree(noted_pristine, target)
    return target


@pytest.fixture(scope="module")
def plain_pristine(tmp_path_factory):
    out = tmp_path_factory.mktemp("c6a_plain") / "grouped"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


def _cells(b):
    return [c for c in b["candidates"] if c["target_field_path"] == CELL]


def _group_of(b):
    by_key = {r["run_key"]: r["run_id"] for r in b["runs"]}
    return {by_key[k]: g["group_id"] for g in Q.live_groups(b) for k in g.get("member_run_keys") or () if k in by_key}


# --- HIGH1: a beamtime-wide notes statement is held for review -------------------------------------------------


def test_a_beamtime_wide_notes_statement_is_held_and_a_section_statement_is_not(noted):
    b = M.load(noted)
    cells = _cells(b)
    held = [c for c in cells if c["value"] == "flow_cell"]
    own = [c for c in cells if c["value"] == "h_cell"]
    assert held and own
    for c in held:
        assert c["observed_literals"] == [BEAMTIME_SENTENCE]
        assert (c["extracted_state"], c["value_state"]) == ("needs_review", "needs_review"), c["candidate_id"]
        sb = c["state_basis"]
        assert (sb["review_status"], sb["proposable"]) == ("needs_review", False)
        assert sb["not_proposable_reason"] == B.BEAMTIME_WIDE_REASON
        assert "whole beamtime" in sb["not_proposable_summary"]
        assert c["eligibility_for_official_record"]["eligible"] is False
    for c in own:
        # the Sample 2 section's own sentence overrides the beamtime's for its runs, and is read as their value
        assert c["observed_literals"] == [SECTION_SENTENCE]
        assert c["extracted_state"] == "candidate_extracted"
    on_disk = B.load_bundle(noted)
    assert B.validate_bundle(on_disk) == []
    assert on_disk["counts"]["needs_review"] == sum(1 for c in on_disk["candidates"] if c["value_state"] == "needs_review")


def test_every_group_the_statement_reaches_is_asked_with_the_sentence_and_the_value(noted):
    b = M.load(noted)
    group_of = _group_of(b)
    held = {c["candidate_id"]: c for c in _cells(b) if c["value"] == "flow_cell"}
    reached = {group_of[c["run_id"]] for c in held.values() if c["run_id"] in group_of}
    assert len(reached) >= 2
    asked = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_value" and q["target_field_path"] == CELL]
    asked_groups = {q["scope"].split(":", 1)[1] for q in asked if any(t["id"] in held for t in q["targets"])}
    assert asked_groups == reached
    for q in asked:
        if not any(t["id"] in held for t in q["targets"]):
            continue
        assert "`flow_cell`" in q["text"] and BEAMTIME_SENTENCE in q["text"], q["text"]
        assert "whole beamtime" in q["text"]
        assert "confirm" in q["allowed_decisions"]
    own = {c["candidate_id"] for c in _cells(b) if c["value"] == "h_cell"}
    assert not [q for q in asked if any(t["id"] in own for t in q["targets"])]  # an extracted optional value is not asked


def test_confirm_records_exactly_the_value_the_question_states(noted):
    b = M.load(noted)
    held = {c["candidate_id"] for c in _cells(b) if c["value"] == "flow_cell"}
    q = next(q for q in Q.consolidate(b)["questions"]
             if q["kind"] == "confirm_value" and q["target_field_path"] == CELL and held & {t["id"] for t in q["targets"]})
    M.decide_question(noted, question_id=q["question_id"], decision="confirm", value=None, **BY)
    after = {c["candidate_id"]: c for c in M.load(noted)["candidates"]}
    for t in q["targets"]:
        c = after[t["id"]]
        assert c["value_state"] == "scientist_confirmed" and c["value"] == "flow_cell"
        assert c["eligibility_for_official_record"]["eligible"] is True


def _as_an_older_build_stored_it(b: dict) -> dict:
    """The bundle as the build before this fix stored it: the beamtime-wide value silently extracted."""
    old = copy.deepcopy(b)
    for c in old["candidates"]:
        if c["state_basis"].get("not_proposable_reason") == B.BEAMTIME_WIDE_REASON:
            c["state_basis"].update(review_status="ready", proposable=True, not_proposable_reason=None, not_proposable_summary=None)
            c["extracted_state"] = "candidate_extracted"
    B.refresh_questions(old)
    B.apply_derivations(old)
    return old


def test_an_older_bundle_is_held_on_load_keeps_every_question_id_and_is_saved_held(noted):
    old = _as_an_older_build_stored_it(B.load_bundle(noted))
    assert B.validate_bundle(old) == []  # what an older build stored stays valid
    assert any(c["extracted_state"] == "candidate_extracted" and c["value"] == "flow_cell" for c in _cells(old))
    (Path(noted) / B.BUNDLE_FILE).write_bytes(B.encode(old))
    before = {q["question_id"] for q in Q.consolidate(B.load_bundle(noted))["questions"]}
    loaded = M.load(noted)
    assert all(c["extracted_state"] == "needs_review" for c in _cells(loaded) if c["value"] == "flow_cell")
    after = {q["question_id"] for q in Q.consolidate(loaded)["questions"]}
    assert before <= after and after - before  # nothing disappears; the groups it reaches are now asked
    M.save_bundle(noted, loaded)
    stored = B.load_bundle(noted)
    assert B.validate_bundle(stored) == []
    assert all(c["extracted_state"] == "needs_review" for c in _cells(stored) if c["value"] == "flow_cell")
    assert stored["format_version"] == B.FORMAT_VERSION  # the stored shape is unchanged: no format bump


def test_a_notes_statement_that_names_a_section_or_a_sample_is_not_beamtime_wide():
    def cand(to):
        return {"kind": "field", "value": "flow_cell", "candidate_id": "cand-0001",
                "state_basis": {"proposable": True, "resolved_by_rule": None, "unresolved_reason": None},
                "evidence": [{"method": "deterministic_parser", "relation": "supports",
                              "normalization": [{"step": "normalize", "rule_id": "bl15.notes.cell_type_statement.v1", "to": to}]}]}

    wide = {"member": "flow_cell", "section": None, "file_numbers": [], "named_samples": [], "unscoped": False}
    assert B.beamtime_wide_statement(cand(wide))
    assert not B.beamtime_wide_statement(cand({**wide, "section": "Sample 2", "file_numbers": [4, 5]}))
    assert not B.beamtime_wide_statement(cand({**wide, "named_samples": [3], "named_sample_file_numbers": {"3": [6]}}))
    filename = cand(wide)
    filename["evidence"][0]["normalization"][0]["rule_id"] = "bl15.filenames.millivolt_to_volt.v1"
    assert not B.beamtime_wide_statement(filename)  # a run's own file is not a notes statement


def test_the_committed_corpus_has_no_beamtime_wide_statement_and_nothing_moves(plain_pristine):
    b = B.load_bundle(plain_pristine)
    assert not [c for c in b["candidates"] if B.beamtime_wide_statement(c)]
    assert B.hold_beamtime_wide_statements(copy.deepcopy(b)) == []


# --- HIGH2: a confirm question states what confirm records -----------------------------------------------------


def test_every_confirmable_question_states_the_value_and_unit_confirm_records(plain_pristine):
    b = B.load_bundle(plain_pristine)
    cand = {c["candidate_id"]: c for c in b["candidates"]}
    asked = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_value" and "confirm" in q["allowed_decisions"]]
    assert asked
    for q in asked:
        for t in q["targets"]:
            c = cand[t["id"]]
            if c["value"] is None:
                continue
            shown = f"`{c['value']}`" if isinstance(c["value"], str) else f"`{json.dumps(c['value'])}`"
            assert shown in q["text"], (q["question_id"], q["text"])
    q = next(q for q in asked if q["target_field_path"] == SETPOINT and [cand[t["id"]]["value"] for t in q["targets"]] == [0.1])
    # a unit conversion: the file says 100mV, confirm records 0.1 in a field whose unit is the volt
    assert "`0.1` V" in q["text"] and "'100mV'" in q["text"], q["text"]
    assert q["text"].startswith("Is the extracted potential setpoint V")


def test_a_question_whose_targets_differ_states_each_value(plain_pristine):
    b = copy.deepcopy(B.load_bundle(plain_pristine))
    setpoints = [c for c in b["candidates"] if c["target_field_path"] == SETPOINT and c["value"] in (0.1, 0.2)]
    group_of = _group_of(b)
    one = group_of[setpoints[0]["run_id"]]
    for c in setpoints:  # put both readings in one group: one question, two values
        g = next(g for g in b["record_groups"] if g["group_id"] == group_of[c["run_id"]])
        key = next(r["run_key"] for r in b["runs"] if r["run_id"] == c["run_id"])
        if g["group_id"] != one:
            g["member_run_keys"].remove(key)
            next(x for x in b["record_groups"] if x["group_id"] == one)["member_run_keys"].append(key)
    q = next(q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_value" and q["target_field_path"] == SETPOINT
             and q["scope"] == f"group:{one}")
    assert "`0.1` V" in q["text"] and "`0.2` V" in q["text"] and "each target's own value" in q["text"], q["text"]


# --- LOW5: the sample reading, as the files write it -------------------------------------------------------------


def test_a_sample_question_for_several_groups_names_the_reading_as_written(plain_pristine):
    b = B.load_bundle(plain_pristine)
    shared = [q for q in Q.consolidate(b)["questions"] if (q.get("partition") or "").startswith("sample=")
              and q["partition"] != "sample=unrecorded"]
    assert shared
    for q in shared:
        reading = json.loads(q["partition"].split("=", 1)[1])
        assert "sample name 'ZZ" in q["text"], q["text"]
        assert reading["sample_name"].upper() in q["text"]
    form = next(q for q in shared if q["kind"] == "missing_value" and '"zz1"' in q["partition"])
    assert "with the same sample reading (sample name 'ZZ1'" in form["text"], form["text"]


def test_a_start_time_question_states_the_utc_value_confirm_records_and_its_local_source(tmp_path):
    from test_local_import_xdc_start_time import LA, _import, _start_of, _zone, stamp

    out = _import(tmp_path, {"SYN_summer_A.001": stamp("2099-07-14T10:23:45")})
    _zone(out, LA)
    b = M.load(out)
    start = _start_of(b, "SYN_summer")
    q = next(q for q in Q.consolidate(b)["questions"] if q["kind"] == "confirm_value"
             and {"kind": "candidate", "id": start["candidate_id"]} in q["targets"])
    assert "`2099-07-14T17:23:45Z`" in q["text"] and "from the local clock time '" in q["text"], q["text"]
