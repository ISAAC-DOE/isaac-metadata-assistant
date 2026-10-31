"""c14j: a ruling is tied to the sheet only against the decision that governs now. Synthetic only (SYN_/ZZ names).

* MED-1: ``template adopt`` keeps, per Disagreements row, the decisions it read (``_isaac`` ``governing_decisions``);
  a ruling that keeps the recorded value is tied to the sheet only when it was made against the decision that governs
  now (for a workbook adopted before they were kept: when it was adopted at or after that decision). A stale
  workbook's ruling is "already recorded", so two workbooks imported in turn never flip-flop.
* LOW-1: the summary says tied rulings beside the decisions recorded, counted by ruling cell ("1 ruling cell kept
  the same value and is now tied to your sheet (9 targets)", c14k LOW-5), and never lists them as replacing a file
  reading.
* LOW-2: a ruling takes its target from a File List cell typed with the same (recorded) value.
"""

from __future__ import annotations

import json

import openpyxl

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import template as T

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    PH, THEIRS, WHO, _adopt_json, _cand, _d, _import, _their_sheet, corpus, grouped, grouped_base, ticking)
from test_local_import_polish_c14g_adopt import _rule
from test_local_import_polish_c14h_adopt import _edit_ph, _ruled_ph, _ruling_notes


def _import_text(bdir, xlsx, capsys, *extra):
    capsys.readouterr()
    code = cli.main(["bundle", "template", "import", str(bdir), str(xlsx), "--by", WHO, *extra])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _decisions_on(grouped, tid):
    return [d for d in M.load(grouped)["scientist_decisions"] if d["target"]["id"] == tid]


def _governing(xlsx, did):
    """The ``governing_decisions`` adopt kept in ``_isaac`` for disagreement ``did``."""
    entry = next(e for e in T._marker(openpyxl.load_workbook(xlsx))["disagreements"] if e["id"] == did)
    return T._marker_governing(entry)


def _edit_column(path, header, old, new) -> None:
    """The scientist edits their own sheet: every ``header`` cell reading ``old`` now reads ``new``."""
    wb = openpyxl.load_workbook(path)
    wf = wb["File List"]
    col = [c.value for c in wf[1]].index(header) + 1
    for r in range(2, wf.max_row + 1):
        if wf.cell(r, col).value == old:
            wf.cell(r, col).value = new
    wb.save(path)


def _edited_and_ruled_again(grouped, tmp_path, capsys, *extra):
    """Rule 2 (their 2; the file 12) in ruled.xlsx; they edit the cell to 3, adopt again and rule 2 again."""
    theirs, _ = _ruled_ph(grouped, tmp_path, capsys, 2)
    _edit_ph(theirs, 2, 3)
    again = tmp_path / "again.xlsx"
    ph = _d(_adopt_json(grouped, theirs, again, capsys), "pH", run_id="run-007")
    assert ph["recorded_note"].startswith("recorded `2` (")
    _rule(again, tmp_path / "again_ruled.xlsx", {ph["id"]: 2})
    return theirs, ph, tmp_path / "again_ruled.xlsx"


def _settled(grouped, theirs, out, capsys, header, **kw):
    return _d(_adopt_json(grouped, theirs, out, capsys), header, **kw)["already_recorded"]


# --- MED-1 ----------------------------------------------------------------------------------------------------


def test_two_workbooks_imported_in_turn_tie_once_then_change_nothing(grouped, tmp_path, capsys, ticking):
    theirs, ph, current = _edited_and_ruled_again(grouped, tmp_path, capsys)
    stale = tmp_path / "ruled.xlsx"
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    [first] = _decisions_on(grouped, tid)
    assert _governing(current, ph["id"]) == [first["decision_id"]]
    assert _governing(stale, ph["id"]) == []  # nothing was recorded when it was adopted
    code, rep, err = _import(grouped, current, capsys, "--apply")
    assert code == 0, err
    assert len(rep["rulings_tied_to_sheet"]) == 1 and rep["recorded"] == 1
    for x in (stale, current, stale, current):
        code, rep, err = _import(grouped, x, capsys, "--apply")
        assert code == 0, err
        assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"], x.name
        assert [a["target"]["id"] for a in rep["already_decided_same_value"]].count(tid) == 1
    assert len(_decisions_on(grouped, tid)) == 2
    # the stale workbook, imported last, leaves the current sheet's row settled
    assert _settled(grouped, theirs, tmp_path / "now.xlsx", capsys, "pH", run_id="run-007")["statement"].startswith(
        "already recorded: 2 (")


def test_a_whole_beamtime_ruling_ties_every_target_it_reaches(grouped, tmp_path, capsys, ticking):
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    bl = _d(_adopt_json(grouped, theirs, first, capsys), "Beamline/Instrument")
    _rule(first, tmp_path / "ruled.xlsx", {bl["id"]: "BL99"})
    code, rep, err = _import(grouped, tmp_path / "ruled.xlsx", capsys, "--apply")
    assert code == 0, err
    reached = {d["target"]["id"] for d in rep["decisions"] if d["target_field_path"] == bl["path"]}
    assert len(reached) > 1
    theirs2 = _their_sheet(grouped, tmp_path / THEIRS, beamline="63c")
    again = tmp_path / "again.xlsx"
    bl2 = _d(_adopt_json(grouped, theirs2, again, capsys), "Beamline/Instrument")
    assert bl2["recorded_note"].startswith("recorded `BL99` (")
    log = M.load(grouped)["scientist_decisions"]
    assert set(_governing(again, bl2["id"])) == {d["decision_id"] for d in log if d["target"]["id"] in reached}
    _rule(again, tmp_path / "again_ruled.xlsx", {bl2["id"]: "BL99"})
    code, text, err = _import_text(grouped, tmp_path / "again_ruled.xlsx", capsys, "--apply")
    assert code == 0, err
    # LOW-1: one ruling, said as part of the decisions recorded; never as replacing a file reading
    summary = next(line for line in text.splitlines() if line.startswith("Summary:"))
    assert (f"; {len(reached)} decision(s) recorded, including 1 ruling cell that kept the same value and is now tied "
            f"to your sheet ({len(reached)} targets); ") in summary
    assert "replace or contradict a file reading" not in summary
    for tid in reached:
        assert len(_decisions_on(grouped, tid)) == 2
    code, rep, err = _import(grouped, tmp_path / "ruled.xlsx", capsys, "--apply")  # the stale one: nothing
    assert code == 0, err
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    code, rep, err = _import(grouped, tmp_path / "again_ruled.xlsx", capsys, "--apply")
    assert code == 0, err
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    assert _settled(grouped, theirs2, tmp_path / "now.xlsx", capsys, "Beamline/Instrument")["statement"].startswith(
        "already recorded: 'BL99' (")


def test_an_electrolyte_concentration_ruled_again_after_an_edit_ties_it(grouped, tmp_path, capsys, ticking):
    """Their "0.1 M KOH" ruled KOH and 0.1; they edit it to "0.2 M KOH"; they rule the concentration 0.1 again."""
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    el = _d(_adopt_json(grouped, theirs, first, capsys), "Electrolyte", kind="name_only")
    _rule(first, tmp_path / "name.xlsx", {el["id"]: "KOH"})
    _rule(tmp_path / "name.xlsx", tmp_path / "both.xlsx", {el["id"]: 0.1}, column=T.DISAGREE_CONC_COLUMN)
    assert _import(grouped, tmp_path / "both.xlsx", capsys, "--apply")[0] == 0
    _edit_column(theirs, "Electrolyte", "0.1 M KOH", "0.2 M KOH")
    again = tmp_path / "again.xlsx"
    el2 = _d(_adopt_json(grouped, theirs, again, capsys), "Electrolyte", kind="name_only")
    assert el2["recorded_note"].startswith("name recorded: 'KOH'; concentration recorded `0.1` (")
    log = M.load(grouped)["scientist_decisions"]
    conc_ids = {d["decision_id"] for d in log if f"(your concentration ruling on disagreement {el['id']}:" in str(d.get("note"))}
    name_ids = {d["decision_id"] for d in log if f"(your ruling on disagreement {el['id']}:" in str(d.get("note"))}
    assert conc_ids and name_ids and set(_governing(again, el2["id"])) == conc_ids | name_ids
    _rule(again, tmp_path / "again_ruled.xlsx", {el2["id"]: 0.1}, column=T.DISAGREE_CONC_COLUMN)
    code, rep, err = _import(grouped, tmp_path / "again_ruled.xlsx", capsys, "--apply")
    assert code == 0, err
    assert rep["rulings_tied_to_sheet"] and {t["header"] for t in rep["rulings_tied_to_sheet"]} == {
        next(c.header for c in T.FILE_COLUMNS if c.path == T.ELECTROLYTE_CONC_PATH)}
    assert rep["recorded"] == len(rep["rulings_tied_to_sheet"]) == len(conc_ids)
    for x in ("both.xlsx", "again_ruled.xlsx"):  # either one again: nothing more
        code, rep, err = _import(grouped, tmp_path / x, capsys, "--apply")
        assert code == 0, err
        assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"], x
    statement = _settled(grouped, theirs, tmp_path / "now.xlsx", capsys, "Electrolyte", kind="name_only")["statement"]
    assert statement.startswith("already recorded: name 'KOH', concentration 0.1 M (")


def test_a_candidate_governed_by_its_conflicts_decision_ties(grouped, tmp_path, capsys, ticking):
    """The file's pH 12 is confirmed through a conflict on the candidate; their sheet says 2; they rule 12."""
    bundle = M.load(grouped)
    cand = _cand(bundle, PH, "run-007")
    model = next(cf for cf in bundle["conflicts"] if cf["kind"] == "field_disagreement")
    bundle["conflicts"].append({**json.loads(json.dumps(model)), "conflict_id": "conf-900", "candidate_id": cand["candidate_id"],
                                "engine_conflict_id": "ZZ_synthetic::pH", "subject": "pH", "run_ids": ["run-007"]})
    sb = cand["state_basis"]
    sb["resolved_by_rule"] = "ZZ_synthetic_rule"  # a conflict a rule resolved: the candidate keeps its value 12
    sb["review_status"], sb["proposable"] = B.review_status_from_basis(cand)
    cand["extracted_state"] = B._extracted_from_status(sb["review_status"], sb["proposable"])
    M.save_bundle(grouped, bundle)
    M.decide(grouped, target_ids=["conf-900"], decision="correct", value=12, by=WHO, orcid=None)
    [via] = _decisions_on(grouped, "conf-900")
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    ph = _d(_adopt_json(grouped, theirs, first, capsys), "pH", run_id="run-007")
    assert ph["recorded_note"].startswith("recorded `12` (")
    assert _governing(first, ph["id"]) == [via["decision_id"]]
    _rule(first, tmp_path / "ruled.xlsx", {ph["id"]: 12})
    code, rep, err = _import(grouped, tmp_path / "ruled.xlsx", capsys, "--apply")
    assert code == 0, err
    [tied] = rep["rulings_tied_to_sheet"]
    assert tied["target"]["id"] == cand["candidate_id"] and tied["decision_id"] == via["decision_id"]
    code, rep, err = _import(grouped, tmp_path / "ruled.xlsx", capsys, "--apply")
    assert code == 0, err
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    assert _settled(grouped, theirs, tmp_path / "now.xlsx", capsys, "pH", run_id="run-007")["statement"].startswith(
        "already recorded: 12 (")


def test_supersede_with_a_tie_ties_once_and_a_stale_workbook_changes_nothing(grouped, tmp_path, capsys, ticking):
    theirs, ph, current = _edited_and_ruled_again(grouped, tmp_path, capsys)
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    code, rep, err = _import(grouped, current, capsys, "--apply", "--supersede")
    assert code == 0, err
    [tied] = rep["rulings_tied_to_sheet"]
    assert tied["target"]["id"] == tid and not rep["clashes"]
    for x in (tmp_path / "ruled.xlsx", current):
        code, rep, err = _import(grouped, x, capsys, "--apply", "--supersede")
        assert code == 0, err
        assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"], x.name
    assert len(_decisions_on(grouped, tid)) == 2
    assert _settled(grouped, theirs, tmp_path / "now.xlsx", capsys, "pH", run_id="run-007")["statement"].startswith(
        "already recorded: 2 (")


def _adopted_before_governing_was_kept(xlsx, out, exported_utc) -> None:
    """``xlsx`` as a build before c14j wrote it (no ``governing_decisions``), adopted at ``exported_utc``."""
    wb = openpyxl.load_workbook(xlsx)
    wm = wb["_isaac"]
    [(r0, c0)] = [(c.row, c.column) for row in wm.iter_rows() for c in row if c.value == "governing_decisions"]
    for r in range(r0, wm.max_row + 1):
        wm.cell(r, c0).value = None
    [r1] = [c.row for row in wm.iter_rows() for c in row if c.column == 1 and c.value == "exported_utc"]
    wm.cell(r1, 2).value = exported_utc
    for row in wm.iter_rows():  # c14l: nor the decision log's length at adopt (kept from c14l on)
        if row[0].value == "decisions_at_adopt":
            row[0].value = row[1].value = None
    wb.save(out)


def test_a_workbook_adopted_before_the_governing_decisions_were_kept_ties_by_time(grouped, tmp_path, capsys, ticking):
    theirs, ph, current = _edited_and_ruled_again(grouped, tmp_path, capsys)
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    [first] = _decisions_on(grouped, tid)
    older, newer = tmp_path / "older.xlsx", tmp_path / "newer.xlsx"
    _adopted_before_governing_was_kept(current, older, "2098-12-31T23:59:59Z")  # before the decision: stale
    _adopted_before_governing_was_kept(current, newer, first["decided_utc"])  # at the decision: made against it
    assert T._marker_governing(next(e for e in T._marker(openpyxl.load_workbook(older))["disagreements"])) is None
    code, rep, err = _import(grouped, older, capsys, "--apply")
    assert code == 0, err
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    # c14k MED-1: a stale ruling is listed apart, never folded into "already recorded"
    assert tid not in [a["target"]["id"] for a in rep["already_decided_same_value"]]
    assert [s["target"]["id"] for s in rep["stale_rulings"]] == [tid]
    code, rep, err = _import(grouped, newer, capsys, "--apply")
    assert code == 0, err
    [tied] = rep["rulings_tied_to_sheet"]
    assert tied["target"]["id"] == tid and tied["decision_id"] == first["decision_id"]
    code, rep, err = _import(grouped, older, capsys, "--apply")  # the tie is later than either workbook
    assert code == 0, err
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    assert len(_decisions_on(grouped, tid)) == 2


def test_rules_against_now_reads_the_kept_ids_then_the_time():
    prior = {"decision_id": "d-0002", "decided_utc": "2099-01-01T00:00:05Z"}
    assert T._rules_against_now({"ruled_against": ["d-0001", "d-0002"]}, prior, None)
    assert not T._rules_against_now({"ruled_against": []}, prior, "2100-01-01T00:00:00Z")  # the ids, never the time
    assert not T._rules_against_now({"ruled_against": ["d-0001"]}, prior, "2100-01-01T00:00:00Z")
    assert T._rules_against_now({}, prior, "2099-01-01T00:00:05Z")
    assert not T._rules_against_now({}, prior, "2099-01-01T00:00:04Z")
    assert not T._rules_against_now({}, prior, None) and not T._rules_against_now({}, {"decision_id": "d"}, "2099-01-01T00:00:00Z")
    assert T._marker_governing({"governing_decisions": '["d-0001"]'}) == ["d-0001"]
    assert T._marker_governing({"governing_decisions": "[]"}) == []
    assert T._marker_governing({}) is None and T._marker_governing({"governing_decisions": "damaged"}) == [T.GOVERNING_DAMAGED]


# --- LOW-2 ----------------------------------------------------------------------------------------------------


def test_a_file_list_cell_with_the_recorded_value_does_not_pre_empt_the_ruling(grouped, tmp_path, capsys, ticking):
    theirs, ph, current = _edited_and_ruled_again(grouped, tmp_path, capsys)
    wb = openpyxl.load_workbook(current)
    wf = wb["File List"]
    col = next(c.column for c in wf[1] if c.value == "pH")
    row = next(int(v[1]) for v in wb["_isaac"].iter_rows(values_only=True) if v[0] == "File List" and v[2] == "run-007")
    wf.cell(row, col).value = 2  # they also typed the recorded value there
    wb.save(current)
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    code, rep, err = _import(grouped, current, capsys, "--apply")
    assert code == 0, err
    [tied] = rep["rulings_tied_to_sheet"]
    assert tied["target"]["id"] == tid and tied["cell"].startswith("'Disagreements'!")
    assert tid not in [a["target"]["id"] for a in rep["already_decided_same_value"]]
    assert _ruling_notes(grouped)[-1]["note"].endswith("'File List'!H8 = 3)")
    assert _settled(grouped, theirs, tmp_path / "now.xlsx", capsys, "pH", run_id="run-007")["statement"].startswith(
        "already recorded: 2 (")
