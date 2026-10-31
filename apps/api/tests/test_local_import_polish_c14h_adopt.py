"""c14h: a re-adopted sheet's ruling is tied to the value it was made on. Synthetic only (SYN_/ZZ names).

* MED-1: a ruling settles its Disagreements row in a later adopt of the sheet only while the sheet's cell still holds
  the value the ruling was made on (the decision note says it: ``... 'File List'!H8 = 2``). A cell the scientist edits
  since is a new disagreement and awaits a ruling; so does a row whose ruling's note predates that value. The import
  reads the sheet's value from the ``_isaac`` sheet, never from the Disagreements sheet's column D, which the scientist
  can edit, so typing the recorded value there settles nothing.
* LOW-1: a sheet word kept for only some of its runs cites only the cells that said it for them, and nothing is kept
  (or refused at the request limit) for a word every run of which was answered since.
* LOW-2: a ruling cell says ``--supersede`` when ANY run of the row holds its own answer.
"""

from __future__ import annotations

import json

import openpyxl

from isaac_api.local_import import bundle as B
from isaac_api.local_import import mutations as M
from isaac_api.local_import import template as T

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    PH, THEIRS, WHO, _adopt, _adopt_json, _cand, _d, _import, _their_sheet, corpus, grouped, grouped_base, ticking)
from test_local_import_polish_c14g_adopt import RUNS, _answered_word, _row_of, _rule


def _edit_ph(path, old, new) -> None:
    """The scientist edits their own sheet: every pH cell reading ``old`` now reads ``new`` (same file name)."""
    wb = openpyxl.load_workbook(path)
    wf = wb["File List"]
    col = [c.value for c in wf[1]].index("pH") + 1
    for r in range(2, wf.max_row + 1):
        if wf.cell(r, col).value == old:
            wf.cell(r, col).value = new
    wb.save(path)


def _ruled_ph(grouped, tmp_path, capsys, ruling):
    """Their sheet says pH 2 for run-007 (the file reads 12); the scientist rules ``ruling`` and it is recorded."""
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    ph = _d(_adopt_json(grouped, theirs, first, capsys), "pH", run_id="run-007")
    assert ph["their_value"] == 2 and ph["already_recorded"] is None
    _rule(first, tmp_path / "ruled.xlsx", {ph["id"]: ruling})
    code, rep, err = _import(grouped, tmp_path / "ruled.xlsx", capsys, "--apply")
    assert code == 0, err
    return theirs, ph


def _ruling_notes(grouped):
    return [d for d in M.load(grouped)["scientist_decisions"] if "ruling on disagreement" in str(d.get("note"))]


# --- MED-1 ----------------------------------------------------------------------------------------------------


def test_a_ruling_note_names_the_value_it_was_made_on(grouped, tmp_path, capsys, ticking):
    _ruled_ph(grouped, tmp_path, capsys, 12)
    [d] = _ruling_notes(grouped)
    # c14m MED-3: the adoption's id follows the provenance
    assert d["note"].split(" (adopt id ")[0].endswith(
        f"(your ruling on disagreement {d['note'].split('disagreement ')[1].split(':')[0]}: {THEIRS} 'File List'!H8 = 2)")


def test_an_unedited_sheet_adopted_again_after_a_ruling_is_settled(grouped, tmp_path, capsys, ticking):
    theirs, _ = _ruled_ph(grouped, tmp_path, capsys, 12)  # ruled for the file's 12 over the sheet's 2
    again = tmp_path / "again.xlsx"
    ph = _d(_adopt_json(grouped, theirs, again, capsys), "pH", run_id="run-007")
    assert ph["already_recorded"]["statement"].startswith("already recorded: 12 (") and ph["recorded_note"] is None
    code, rep, err = _import(grouped, again, capsys)
    assert code == 0, err
    assert ph["id"] in [x["id"] for x in rep["disagreements_already_recorded"]]
    assert ph["id"] not in [x["id"] for x in rep["awaiting_ruling"]]


def test_a_cell_edited_after_its_ruling_awaits_a_ruling_again(grouped, tmp_path, capsys, ticking):
    """v1 says pH 2 (the file reads 12); they rule 2; then they edit the same cell to 3, keep the file name, re-adopt."""
    theirs, _ = _ruled_ph(grouped, tmp_path, capsys, 2)
    _edit_ph(theirs, 2, 3)
    again = tmp_path / "again.xlsx"
    ph = _d(_adopt_json(grouped, theirs, again, capsys), "pH", run_id="run-007")
    assert ph["their_value"] == 3 and ph["their_cells"] == ["'File List'!H8"]
    assert ph["already_recorded"] is None
    assert ph["recorded_note"] == "recorded `2` (2099-01-01); your sheet says `3`: rule which"
    code, rep, err = _import(grouped, again, capsys)
    assert code == 0, err
    assert not rep["disagreements_already_recorded"]
    [waiting] = [x for x in rep["awaiting_ruling"] if x["id"] == ph["id"]]
    assert waiting["their_value"] == 3
    assert waiting["why"].startswith("recorded `2` (2099-01-01); your sheet says `3`: rule which")


def test_a_ruling_noted_before_the_value_was_kept_awaits_a_ruling(grouped, tmp_path, capsys, ticking):
    """A ruling recorded by an import that did not yet name the value (``... 'File List'!H8)``) is not read as a
    ruling on this disagreement: the row awaits one (the safe direction)."""
    theirs, _ = _ruled_ph(grouped, tmp_path, capsys, 12)
    bundle = M.load(grouped)
    [d] = [d for d in bundle["scientist_decisions"] if "ruling on disagreement" in str(d.get("note"))]
    d["note"] = d["note"].replace(" = 2)", ")")
    M.save_bundle(grouped, bundle)
    again = tmp_path / "again.xlsx"
    ph = _d(_adopt_json(grouped, theirs, again, capsys), "pH", run_id="run-007")
    assert ph["already_recorded"] is None
    assert ph["recorded_note"] == "recorded `12` (2099-01-01); your sheet says `2`: rule which"
    code, rep, err = _import(grouped, again, capsys)
    assert code == 0, err
    assert ph["id"] in [x["id"] for x in rep["awaiting_ruling"]]
    assert not rep["disagreements_already_recorded"]


def test_typing_the_recorded_value_in_column_d_settles_nothing(grouped, tmp_path, capsys, ticking):
    """The file's pH 12 is confirmed, then their sheet says 2. Column D (their value, shown) is edited to 12 with the
    ruling left blank: the import reads their value from `_isaac`, so the row still awaits a ruling."""
    M.decide(grouped, target_ids=[_cand(M.load(grouped), PH, "run-007")["candidate_id"]], decision="confirm", value=None,
             by=WHO, orcid=None)
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    out = tmp_path / "adopted.xlsx"
    ph = _d(_adopt_json(grouped, theirs, out, capsys), "pH", run_id="run-007")
    assert ph["already_recorded"] is None
    wb = openpyxl.load_workbook(out)
    wd = wb["Disagreements"]
    row = next(r for r in range(2, wd.max_row + 1) if wd[f"A{r}"].value == ph["id"])
    assert wd[f"D{row}"].value == 2
    wd[f"D{row}"] = 12
    wb.save(tmp_path / "edited.xlsx")
    code, rep, err = _import(grouped, tmp_path / "edited.xlsx", capsys)
    assert code == 0, err
    assert not rep["disagreements_already_recorded"]
    [waiting] = [x for x in rep["awaiting_ruling"] if x["id"] == ph["id"]]
    assert waiting["their_value"] == 2  # as adopt kept it, not as column D now reads
    assert waiting["why"].startswith("recorded `12` (2099-01-01); your sheet says `2`: rule which")


def test_a_workbook_adopted_before_the_value_was_kept_settles_nothing(grouped, tmp_path, capsys, ticking):
    """An `_isaac` sheet with no their_value column (adopt before c14h): column D is shown, but settles no row."""
    M.decide(grouped, target_ids=[_cand(M.load(grouped), PH, "run-007")["candidate_id"]], decision="correct", value=2,
             by=WHO, orcid=None)
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    out = tmp_path / "adopted.xlsx"
    ph = _d(_adopt_json(grouped, theirs, out, capsys), "pH", run_id="run-007")
    assert ph["already_recorded"]["statement"].startswith("already recorded: 2 (")  # the sheet agrees with it
    code, rep, err = _import(grouped, out, capsys)
    assert code == 0, err
    assert ph["id"] in [x["id"] for x in rep["disagreements_already_recorded"]]
    wb = openpyxl.load_workbook(out)
    wm = wb["_isaac"]
    [(r0, c0)] = [(c.row, c.column) for row in wm.iter_rows() for c in row if c.value == "their_value"]
    assert json.loads(wm.cell(r0 + 1, c0).value) is not None
    for r in range(r0, wm.max_row + 1):
        wm.cell(r, c0).value = None
    wb.save(tmp_path / "legacy.xlsx")
    code, rep, err = _import(grouped, tmp_path / "legacy.xlsx", capsys)
    assert code == 0, err
    assert ph["id"] not in [x["id"] for x in rep["disagreements_already_recorded"]]
    [waiting] = [x for x in rep["awaiting_ruling"] if x["id"] == ph["id"]]
    assert waiting["their_value"] == 2


def test_ruled_here_needs_the_same_value():
    note = "template x.xlsx 'Disagreements'!H4 (your ruling on disagreement D3: SYN_their.xlsx 'File List'!H8 = {})"
    log = [{"note": note.format("2")}, {"note": note.format('"0.1 M ZZ"')},
           {"note": "template x.xlsx 'Disagreements'!H4 (your ruling on disagreement D3: SYN_their.xlsx 'File List'!H8)"},
           {"note": note.format("not json")}]
    where = ("SYN_their.xlsx", "'File List'!H8")
    assert T._ruled_here(log, 0, (*where, 2)) and T._ruled_here(log, 0, (*where, 2.0))
    assert not T._ruled_here(log, 0, (*where, 3)) and not T._ruled_here(log, 0, (*where, "2"))  # a number is not text
    assert T._ruled_here(log, 1, (*where, "0.1 M ZZ")) and not T._ruled_here(log, 1, (*where, "0.2 M ZZ"))
    assert not T._ruled_here(log, 2, (*where, 2))  # an old-format note: not ruled here
    assert not T._ruled_here(log, 3, (*where, "not json"))


# --- LOW-1 ----------------------------------------------------------------------------------------------------


def test_a_word_kept_for_a_new_run_cites_only_that_runs_cell(grouped, tmp_path, capsys, ticking):
    _answered_word(grouped, tmp_path, capsys)
    more = _their_sheet(grouped, tmp_path / "SYN_more.xlsx", rows=[*RUNS, "run-009"])
    code, text, err = _adopt(grouped, more, tmp_path / "more.xlsx", capsys, "--by", WHO)
    assert code == 0, err
    reqs = M.load(grouped)["vocabulary_requests"]
    assert reqs[1]["run_ids"] == ["run-009"] and reqs[1]["source"]["cells"] == ["'File List'!F10"]
    [line] = [x for x in text.splitlines() if "'aqueous_electrochemistry' for 1 run(s)" in x]
    assert "('File List'!F10) [vr-00002]" in line
    # the same sheet adopted again keeps nothing new
    code, text, err = _adopt(grouped, more, tmp_path / "more2.xlsx", capsys, "--by", WHO)
    assert code == 0, err
    assert [r["request_id"] for r in M.load(grouped)["vocabulary_requests"]] == ["vr-00001", "vr-00002"]


def test_a_word_answered_for_every_run_is_not_kept_even_at_the_request_limit(grouped, tmp_path, capsys, ticking,
                                                                             monkeypatch):
    """No request is kept (and then taken back) for a word every run of which was answered since, so a bundle at the
    request limit does not refuse the adopt."""
    _answered_word(grouped, tmp_path, capsys)
    monkeypatch.setattr(B, "MAX_VOCABULARY_REQUESTS", len(M.load(grouped)["vocabulary_requests"]))
    fewer = _their_sheet(grouped, tmp_path / "SYN_fewer.xlsx", rows=RUNS[:7])
    code, text, err = _adopt(grouped, fewer, tmp_path / "fewer.xlsx", capsys, "--by", WHO)
    assert code == 0, err
    assert [r["request_id"] for r in M.load(grouped)["vocabulary_requests"]] == ["vr-00001"]
    assert T.ANSWERED_SINCE_HEADING in text


def test_cells_for_runs_follow_each_cells_runs():
    rows = T.off_list_requests([
        {"path": "p", "value": "w", "header": "H", "cells": ["A1", "A2", "A3"], "run_ids": ["r1", "r2", "r3"],
         "cell_runs": {"A1": ["r1"], "A2": ["r2"], "A3": ["r3"]}},
        {"path": "p", "value": "w", "header": "H", "cell": "B4", "run_id": "r4"},
    ])
    [row] = rows
    assert row["cells"] == ["A1", "A2", "A3", "B4"] and row["run_ids"] == ["r1", "r2", "r3", "r4"]
    assert T.cells_for_runs(row, ["r2", "r4"]) == ["A2", "B4"]
    assert T.cells_for_runs(row, row["run_ids"]) == row["cells"]


# --- LOW-2 ----------------------------------------------------------------------------------------------------


def test_supersede_is_said_when_any_run_holds_its_own_answer():
    """run-1 holds its own answer and the beamtime-wide one; run-2 only the beamtime-wide one."""
    path = "context.electrochemistry.potential_scale"
    mixed = {(path, "run-1"): [("RHE", "2099-01-01T00:00:01Z", 0)], (path, None): [("RHE", "2099-01-01T00:00:01Z", 1)]}
    rec = T.recorded_ruling(mixed, path, ["run-1", "run-2"], "run", their_value="RHE")
    assert rec["settled"] is True and rec["run_own"] is True
    wide = {(path, None): [("RHE", "2099-01-01T00:00:01Z", 1)]}
    assert T.recorded_ruling(wide, path, ["run-1", "run-2"], "run", their_value="RHE")["run_own"] is False
