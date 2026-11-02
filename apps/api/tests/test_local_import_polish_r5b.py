"""r5 real-data walk, fixer B (questions / template / notes reading). Synthetic data only.

B1  A notes sentence that names a cell only IN PASSING ("the spare grids are kept beside the flow cell") gives no cell
    type: the candidate keeps the sentence and carries no value, the question quotes it and asks (no confirm, no
    one-answer-for-all batch), and a record never cites it as support. A sentence ABOUT the cell is read as before.
B2  The counter question never shows the ``XX_02_…`` pattern: with no two names differing only at the asked token, one
    real name is shown with that token marked.
B3  Per-group confirm questions are batched by the VALUE they confirm (``0p8V`` and ``800mV`` are both 0.8 V).
B4  A group whose every run is not a measurement run (a reference standard) and whose record needs a field nothing can
    hold an answer for says so up front: ``cannot_export_reason: not_a_measurement_run``.
B5  A run a group keeps as CONTEXT (an exported file of a run) is in no question's targets, counts or reach, and is
    marked on its template File List row.
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
from isaac_api.local_import import records as R
from isaac_api.local_import import template as T

from test_local_import_polish_r4b import _hand_bundle
from test_local_import_records import BY, SEMANTICS, fake_upstream  # noqa: F401  (fixture)

CELL = "context.electrochemistry.cell_type"
SETPOINT = "context.electrochemistry.potential_setpoint_V"
NOTES = "2099 SYNTHETIC semantics notes.txt"
#: before any sample section, and about something else: the cell is named only in passing
PASSING = "SYNTHETIC: the spare grids are kept on the bench beside the flow cell."
#: inside the `Sample 2` section, about the measurement
SECTION = "SYNTHETIC: measured in an H-cell."


def _corpus(tmp: Path) -> Path:
    src = tmp / "corpus"
    shutil.copytree(SEMANTICS, src)
    notes = src / NOTES
    text = notes.read_text(encoding="utf-8")
    text = text.replace("SYNTHETIC: held at room temperature throughout\n",
                        f"SYNTHETIC: held at room temperature throughout\n{PASSING}\n", 1)
    text = text.replace("Operator: Operator Beta (synthetic)\n", f"Operator: Operator Beta (synthetic)\n{SECTION}\n", 1)
    assert PASSING in text and SECTION in text
    notes.write_text(text, encoding="utf-8")
    return src


@pytest.fixture(scope="module")
def passing_pristine(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("r5b")
    out = tmp / "grouped"
    assert cli.main(["import", str(_corpus(tmp)), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def passing(passing_pristine, tmp_path):
    target = tmp_path / "grouped"
    shutil.copytree(passing_pristine, target)
    return target


@pytest.fixture(scope="module")
def plain_pristine(tmp_path_factory):
    out = tmp_path_factory.mktemp("r5b_plain") / "grouped"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


@pytest.fixture()
def plain(plain_pristine, tmp_path):
    target = tmp_path / "plain"
    shutil.copytree(plain_pristine, target)
    return target


def _cells(b):
    return [c for c in b["candidates"] if c["target_field_path"] == CELL]


# --- B1: a cell named only in passing ------------------------------------------------------------------------------


@pytest.mark.parametrize("sentence, term, in_passing", [
    (PASSING, "flow cell", True),
    ("SYNTHETIC: ask the operator to rinse the flow cell tomorrow.", "flow cell", True),
    ("SYNTHETIC: the grids are in the drawer of the bench with the H-cell.", "H-cell", True),
    ("SYNTHETIC: Flow cell = 5 ml/min", "Flow cell", False),
    ("Cell: beaker cell", "beaker cell", False),
    ("Cell type = H-cell", "H-cell", False),
    (SECTION, "H-cell", False),
    ("SYNTHETIC: samples 3 and 4 were run in a flow cell.", "flow cell", False),
    ("SYNTHETIC: we used a beaker cell for every electrode.", "beaker cell", False),
    ("SYNTHETIC: a flow cell, later a coin cell.", "flow cell", False),
    ("SYNTHETIC: no term here", "flow cell", False),  # the term is not in the line: nothing is judged
])
def test_a_cell_named_in_passing_is_told_from_a_statement_about_the_cell(sentence, term, in_passing):
    assert B.cell_named_in_passing(sentence, term) is in_passing


def test_a_passing_mention_gives_no_value_and_a_section_statement_still_does(passing):
    b = M.load(passing)
    cells = _cells(b)
    gone = [c for c in cells if c["observed_literals"] == [PASSING]]
    own = [c for c in cells if c["observed_literals"] == [SECTION]]
    assert gone and own
    for c in gone:
        assert c["value"] is None
        assert (c["extracted_state"], c["value_state"]) == ("needs_review", "needs_review")
        assert c["state_basis"]["not_proposable_reason"] == B.PASSING_MENTION_REASON
        assert PASSING in c["state_basis"]["not_proposable_summary"]
        assert c["evidence"] and c["evidence"][0]["literal_value"] == PASSING  # the evidence is kept as it was read
        assert B.passing_reading_value(c) == "flow_cell"  # what the import recorded, for scopes and partitions
    for c in own:
        assert c["value"] == "h_cell" and c["extracted_state"] == "candidate_extracted"
    on_disk = B.load_bundle(passing)
    assert B.validate_bundle(on_disk) == []
    assert all(c["value"] is None for c in _cells(on_disk) if c["observed_literals"] == [PASSING])


def test_the_question_quotes_the_sentence_asks_and_offers_no_confirm_or_batch(passing):
    b = M.load(passing)
    gone = {c["candidate_id"] for c in _cells(b) if c["observed_literals"] == [PASSING]}
    asked = [q for q in Q.consolidate(b)["questions"]
             if q["target_field_path"] == CELL and gone & {t["id"] for t in q["targets"]}]
    assert len(asked) >= 2
    for q in asked:
        assert q["no_value"] is True
        assert "only in passing" in q["text"] and PASSING in q["text"], q["text"]
        assert "`flow_cell`" not in q["text"]
        assert "confirm" not in q["allowed_decisions"] and q["confirmable_scopes"] == []
        assert "same_reading_group" not in q  # one passing sentence is never one answer for every group
        assert all(not h.get("carries_value") for h in q["hints"] if h.get("kind") == "file_literal")
    with pytest.raises(M.MutationRefused):
        M.decide_question(passing, question_id=asked[0]["question_id"], decision="confirm", value=None, **BY)


def _as_an_older_build_stored_it(b: dict) -> dict:
    """The bundle as the build before r5 stored it: the passing mention's value kept (held for review)."""
    old = copy.deepcopy(b)
    for c in old["candidates"]:
        if c["state_basis"].get("not_proposable_reason") == B.PASSING_MENTION_REASON:
            c["value"] = "flow_cell"
            c["state_basis"].update(not_proposable_reason=B.BEAMTIME_WIDE_REASON, not_proposable_summary=B.BEAMTIME_WIDE_SUMMARY)
    B.apply_derivations(old)
    return old


def test_question_ids_and_groups_do_not_move_and_an_older_bundle_is_read_the_new_way(passing):
    old = _as_an_older_build_stored_it(B.load_bundle(passing))
    assert B.validate_bundle(old) == []
    (Path(passing) / B.BUNDLE_FILE).write_bytes(B.encode(old))
    raw = B.load_bundle(passing)
    assert any(c["value"] == "flow_cell" for c in _cells(raw) if c["observed_literals"] == [PASSING])
    before = {q["question_id"] for q in Q.consolidate(raw)["questions"]}
    loaded = M.load(passing)  # held in memory, as every reader holds it
    assert all(c["value"] is None for c in _cells(loaded) if c["observed_literals"] == [PASSING])
    assert {q["question_id"] for q in Q.consolidate(loaded)["questions"]} == before  # every id stays
    # a regroup partitions the runs as the import read them
    groups_before = sorted(g["group_id"] for g in Q.live_groups(loaded))
    M.save_bundle(passing, loaded)
    assert B.validate_bundle(B.load_bundle(passing)) == []
    M.group(passing, regroup=True)
    assert sorted(g["group_id"] for g in Q.live_groups(M.load(passing))) == groups_before


def test_a_value_already_confirmed_is_kept(passing, monkeypatch):
    old = _as_an_older_build_stored_it(B.load_bundle(passing))
    (Path(passing) / B.BUNDLE_FILE).write_bytes(B.encode(old))
    target = next(c["candidate_id"] for c in _cells(old) if c["observed_literals"] == [PASSING])
    # an older build recorded a confirm of the value (this build clears the value of an UNDECIDED candidate only)
    with monkeypatch.context() as m:
        m.setattr(B, "clear_passing_cell_mentions", lambda bundle: [])
        M.decide(passing, target_ids=[target], decision="confirm", value=None, **BY)
    kept = next(c for c in M.load(passing)["candidates"] if c["candidate_id"] == target)
    assert kept["value"] == "flow_cell" and kept["value_state"] == "scientist_confirmed"
    assert B.validate_bundle(B.load_bundle(passing)) == []


def test_a_record_never_cites_a_passing_mention_as_support():
    rule = "bl15.notes.cell_type_statement.v1"
    cand = {"target_field_path": CELL, "value": None, "rule": rule + ": a logbook sentence names the cell",
            "evidence": [{"method": "deterministic_parser", "relative_path": NOTES, "locator": "line 3 cell type statement",
                          "literal_value": PASSING, "method_id": "bl15_beamtime_notes_v1", "relation": "supports",
                          "normalization": [{"step": "normalize", "rule_id": rule, "from": PASSING,
                                             "to": {"term": "flow cell", "status": "member", "member": "flow_cell"}},
                                            {"step": "derive", "rule_id": rule, "from": {"term": "flow cell"}, "to": "flow_cell"}]}]}
    (w,) = R._witnesses(cand, "flow_cell", {"decision": "correct", "value": "flow_cell"})
    assert w["relation"] == "context" and w["note"] == R.PASSING_WITNESS_NOTE
    stated = {**cand, "evidence": [{**cand["evidence"][0], "literal_value": "SYNTHETIC: Flow cell = 5 ml/min",
                                    "normalization": [{**cand["evidence"][0]["normalization"][0],
                                                       "to": {"term": "Flow cell", "member": "flow_cell"}}]}]}
    (w,) = R._witnesses(stated, "flow_cell", None)
    assert w["relation"] == "supports"


# --- B2: the counter question shows a real name ----------------------------------------------------------------------


def test_the_counter_question_never_shows_the_placeholder(monkeypatch):
    bundle = _hand_bundle([["01_13_SYNa_cell", "03_12_SYNa_cell"]])
    got = Q._counter_examples(bundle, [1])
    assert got[1]["differ"] == [] and got[1]["one"] == "[01]_13_SYNa_cell"
    # no name with a number there at all: the position is named, the pattern goes
    assert Q._counter_examples(_hand_bundle([["SYNa_x", "SYNb_y"]]), [1]) == {}


def test_the_consolidated_counter_question_shows_a_marked_real_name(plain):
    b = M.load(plain)
    gq = {"id": "rgq-experiment-counter-positions", "kind": "naming_counter_positions", "positions": [1],
          "text": "In this beamtime, is the 1st token of the file names a run counter? (e.g. XX_02_… vs XX_03_…). Answer."}
    b["grouping_questions"] = [gq]
    b["merge_candidates"] = []
    q = next(q for q in Q.consolidate(b)["questions"] if q["kind"] == "naming_counter_positions")
    assert q["question_id"] == Q.COUNTER_QUESTION_ID  # the id never depends on the text
    assert "XX_0" not in q["text"] and "[" in q["text"], q["text"]


# --- B3: confirms batched by value -----------------------------------------------------------------------------------


def _setpoint_questions(literals_values):
    cands, qs, runs = {}, [], []
    for i, (lit, value) in enumerate(literals_values):
        cands[f"c{i}"] = {"candidate_id": f"c{i}", "run_id": f"r{i}", "value": value, "observed_literals": [lit],
                          "observed_literals_total": 1, "target_field_path": SETPOINT,
                          "evidence": [{"relative_path": f"SYN_{i}_{lit}.dat"}]}
        runs.append({"run_id": f"r{i}", "stem": f"SYN_{i}_{lit}"})
        qs.append({"question_id": f"Q-{i}", "kind": "confirm_value", "scope": f"group:g{i}", "target_field_path": SETPOINT,
                   "targets": [{"kind": "candidate", "id": f"c{i}"}], "text": "Q.", "targets_without_a_value": 0,
                   "targets_with_an_unfit_value": 0,
                   "answer_command": f'isaac bundle decide <bundle_dir> --question Q-{i} --decision confirm --by "<your name>"'})
    return cands, qs, {"runs": runs}


def test_equal_values_written_differently_share_one_batch(monkeypatch):
    cands, qs, bundle = _setpoint_questions([("0p8V", 0.8), ("800mV", 0.8), ("0p8V", 0.8), ("600mV", 0.6)])
    monkeypatch.setattr(Q, "file_name_readings", lambda bundle, run, path: [])
    Q._note_shared_reading_groups(qs, cands, bundle, {})
    assert qs[0]["same_reading_group"] == qs[1]["same_reading_group"] == qs[2]["same_reading_group"]
    assert qs[0]["same_reading_count"] == 3 and "same_reading_group" not in qs[3]
    assert "3 questions share this value (`0.8` V; the files write it '0p8V', '800mV')" in qs[0]["text"], qs[0]["text"]
    assert "--same-reading --decision confirm" in qs[1]["same_reading_command"]


def test_file_names_that_state_different_values_still_never_share_a_batch(monkeypatch):
    cands, qs, bundle = _setpoint_questions([("0p8V", 0.8), ("800mV", 0.8)])
    monkeypatch.setattr(Q, "file_name_readings",
                        lambda bundle, run, path: [{"value": 0.8 if run["run_id"] == "r0" else 1.5}])
    Q._note_shared_reading_groups(qs, cands, bundle, {})
    assert not any(q.get("same_reading_group") for q in qs)


def test_a_value_read_from_two_literals_is_not_batched_by_value(monkeypatch):
    cands, qs, bundle = _setpoint_questions([("0p8V", 0.8), ("800mV", 0.8)])
    cands["c0"]["observed_literals"], cands["c0"]["observed_literals_total"] = ["0p8V", "0.8 V"], 2
    monkeypatch.setattr(Q, "file_name_readings", lambda bundle, run, path: [])
    Q._note_shared_reading_groups(qs, cands, bundle, {})
    assert not any(q.get("same_reading_group") for q in qs)


# --- B4: a reference standard's group says up front that it is not a record ------------------------------------------


def _as_a_reference(b: dict) -> tuple[dict, str]:
    """``b`` with its first live group's runs marked not measurement runs, as the import marks a reference standard
    (``run_candidate: false``, and no missing value is made for them)."""
    g = Q.live_groups(b)[0]
    keys = set(g["member_run_keys"])
    rids = {r["run_id"] for r in b["runs"] if r["run_key"] in keys}
    for r in b["runs"]:
        if r["run_key"] in keys:
            r["run_candidate"] = False
    b["missing_values"] = [m for m in b["missing_values"] if m["run_id"] not in rids]
    return b, g["group_id"]


def test_a_reference_group_says_it_cannot_export_and_why(plain):
    b, gid = _as_a_reference(M.load(plain))
    got = Q.not_a_measurement_groups(b)
    assert gid in got and got[gid]
    row = cli.group_list_extras(b)[gid]
    assert row["cannot_export_reason"] == "not_a_measurement_run" and row["cannot_export_fields"] == got[gid]
    assert "not_a_measurement_run" in cli.CANNOT_EXPORT_NOTE
    others = [g["group_id"] for g in Q.live_groups(b) if g["group_id"] != gid]
    assert all(cli.group_list_extras(b)[o].get("cannot_export_reason") != "not_a_measurement_run" for o in others)
    # the minimum names the same fields as unanswerable
    minimum = Q.minimum_answers_for_one_group(Q.consolidate(b), b, scope=f"group:{gid}")
    assert {u["path"] for u in minimum["unasked_required"] if not u["answerable"]} == set(got[gid])
    # a measurement group says nothing new
    assert Q.not_a_measurement_groups(M.load(plain)) == {}


# --- B5: a run kept as context ---------------------------------------------------------------------------------------


def _with_context_run(b: dict) -> tuple[dict, str, str, str]:
    """``b`` (a copy) with its first live group also holding the second group's run as CONTEXT (the shape grouping gives
    an exported file joined to its run's group, ``export_kept_as_context``), the second group gone."""
    b = copy.deepcopy(b)
    keep, donor = Q.live_groups(b)[:2]
    ctx_key = donor["member_run_keys"][0]
    b["record_groups"] = [g for g in b["record_groups"] if g["group_id"] != donor["group_id"]]
    keep["member_run_keys"] = [*keep["member_run_keys"], ctx_key]
    keep["context_run_keys"] = [ctx_key]
    keep.setdefault("flags", []).append("export_kept_as_context")
    ctx_id = next(r["run_id"] for r in b["runs"] if r["run_key"] == ctx_key)
    return b, keep["group_id"], ctx_id, donor["group_id"]


def test_a_context_run_is_in_no_question_count_or_reach(plain):
    b, gid, ctx_id, _donor = _with_context_run(M.load(plain))
    assert B.context_run_ids(b) == {ctx_id}
    owned = {o.get("candidate_id") or o.get("value_id") for o in [*b["candidates"], *b["missing_values"]]
             if o.get("run_id") == ctx_id}
    assert owned
    payload = Q.consolidate(b)
    for q in payload["questions"]:
        assert not owned & {t["id"] for t in q["targets"]}, q["question_id"]
    measured = sum(1 for g in Q.live_groups(b) for k in g["member_run_keys"] if k not in set(g.get("context_run_keys") or ()))
    for q in payload["questions"]:
        assert q["applies_to"]["runs"] <= measured, q["question_id"]
    absorber = [q for q in payload["questions"] if q["kind"] == "confirm_absorber"]
    assert all(q["applies_to"]["runs"] <= measured for q in absorber)
    index = M.reach_index(b)
    assert all(ctx_id not in members for _g, members in index["live"])
    assert M._live_reach(b)[1] == measured
    # the group's own list asks nothing about the context run
    scoped = Q.filter_questions(payload, scope=f"group:{gid}")
    assert not any(owned & {t["id"] for t in q["targets"]} for q in scoped)


def test_surviving_question_ids_do_not_move_with_a_context_run(plain):
    b, gid, ctx_id, donor = _with_context_run(M.load(plain))
    asked = {q["question_id"]: q["scope"] for q in Q.consolidate(b)["questions"]}
    # the same bundle with the context run's own targets simply not there asks exactly the same questions, under the
    # same ids and scopes: a context run only takes away what was asked about it
    without = copy.deepcopy(b)
    without["candidates"] = [c for c in without["candidates"] if c["run_id"] != ctx_id]
    without["missing_values"] = [m for m in without["missing_values"] if m["run_id"] != ctx_id]
    without["conflicts"] = [cf for cf in without["conflicts"] if set(cf.get("run_ids") or ()) != {ctx_id}]
    assert {q["question_id"]: q["scope"] for q in Q.consolidate(without)["questions"]} == asked
    # ...and every question the plain bundle asks that has a target outside the context run is still asked, under its id
    pb = M.load(plain)
    owned = _owned(pb, ctx_id)
    plain_ids = {q["question_id"] for q in Q.consolidate(pb)["questions"]
                 if q["scope"] != f"group:{donor}"  # the context run's own group is gone, and its scope with it
                 and (not q["targets"] or any(t["id"] not in owned for t in q["targets"]))}
    assert plain_ids <= set(asked)


def _owned(b: dict, run_id: str) -> set[str]:
    return {o.get("candidate_id") or o.get("value_id") for o in [*b["candidates"], *b["missing_values"]]
            if o.get("run_id") == run_id}


def test_the_template_marks_a_context_row_and_records_nothing_from_it(plain, tmp_path):
    b, gid, ctx_id, _donor = _with_context_run(M.load(plain))
    M.save_bundle(plain, b)
    rows = T.live_rows(M.load(plain))
    assert [r["run_id"] for r in rows if r.get("context")] == [ctx_id]
    out = tmp_path / "t.xlsx"
    result = T.export_template(plain, out)
    assert result["file_list_context_rows"] == 1
    import openpyxl

    wb = openpyxl.load_workbook(out)
    ws = wb[T.SHEET_FILES]
    marked = [ws.cell(row=i, column=1) for i in range(2, ws.max_row + 1) if ws.cell(row=i, column=1).comment]
    assert len(marked) == 1 and marked[0].comment.text.startswith("Kept by its record group as context")
    assert marked[0].value == next(r["file_name"] for r in rows if r.get("context"))
