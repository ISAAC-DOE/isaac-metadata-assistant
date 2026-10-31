"""c14i: a ruling that keeps the value already recorded is tied to the sheet. Synthetic only (SYN_/ZZ names).

* MED-1: a Disagreements ruling whose value is already recorded, but not by a ruling on their cell as it reads now
  (they edited the cell since, or the value came from a file confirmed with ``decide``), is recorded again with the
  ruling's note ("of which 1 ruling (1 target) kept the same value, now tied to your sheet"), so the next adopt reads
  the row as ruled; the same workbook imported again records nothing more.
* LOW-1: a yes/no or a date value ruled on settles too (the note's value text is the sheet's).
* LOW-2: a ruling read from a workbook adopted before ``_isaac`` kept their value names no value in its note (never
  the editable column D).
* LOW-3: a vocabulary request an earlier build kept for some runs while citing every cell is the same request.
"""

from __future__ import annotations

import datetime as dt

import openpyxl

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import template as T

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    PH, THEIRS, WHO, _adopt, _adopt_json, _cand, _d, _import, _their_sheet, corpus, grouped, grouped_base, ticking)
from test_local_import_polish_c14g_adopt import RUNS, _answered_word, _rule
from test_local_import_polish_c14h_adopt import _edit_ph, _ruled_ph, _ruling_notes

TIED = "now tied to your sheet"


def _import_text(bdir, xlsx, capsys, *extra):
    capsys.readouterr()
    code = cli.main(["bundle", "template", "import", str(bdir), str(xlsx), "--by", WHO, *extra])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _ph_decisions(grouped):
    tid = _cand(M.load(grouped), PH, "run-007")["candidate_id"]
    return [d for d in M.load(grouped)["scientist_decisions"] if d["target"]["id"] == tid]


def _ties_then_settles(grouped, theirs, ruled, ph_id, value, capsys, tmp_path):
    """Import the ruling (tied, recorded once), re-adopt (settled), import it again (nothing more)."""
    code, text, err = _import_text(grouped, ruled, capsys)
    assert code == 0, err
    assert "Rulings to be recorded with the same value, now tied to your sheet" in text
    assert " decision(s) would record, of which 1 ruling (1 target) keeps the same value, to be tied to your sheet;" in text
    before = len(_ph_decisions(grouped))
    code, rep, err = _import(grouped, ruled, capsys, "--apply")
    assert code == 0, err
    [tied] = rep["rulings_tied_to_sheet"]
    assert tied["value"] == value and tied["run_id"] == "run-007" and tied["header"] == "pH"
    assert not [c for c in rep["clashes"] if c["target"]["id"] == tied["target"]["id"]]
    assert not [a for a in rep["already_decided_same_value"] if a["target"]["id"] == tied["target"]["id"]]
    ph = _ph_decisions(grouped)
    assert len(ph) == before + 1 and ph[-1]["value"] == value and ph[-1]["decision_id"] != tied["decision_id"]
    code, text, err = _import_text(grouped, ruled, capsys, "--apply")  # the same workbook again: nothing more
    assert code == 0, err
    assert TIED not in text and "0 decision(s) recorded" in text
    code, rep, err = _import(grouped, ruled, capsys, "--apply")
    assert code == 0, err
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"]
    assert [a for a in rep["already_decided_same_value"] if a["target"]["id"] == tied["target"]["id"]]
    assert len(_ph_decisions(grouped)) == before + 1
    again = _d(_adopt_json(grouped, theirs, tmp_path / "settled.xlsx", capsys), "pH", run_id="run-007")
    assert again["already_recorded"]["statement"].startswith(f"already recorded: {value} (")
    code, rep, err = _import(grouped, tmp_path / "settled.xlsx", capsys)
    assert code == 0, err
    assert again["id"] in [x["id"] for x in rep["disagreements_already_recorded"]]
    assert again["id"] not in [x["id"] for x in rep["awaiting_ruling"]]


# --- MED-1 ----------------------------------------------------------------------------------------------------


def test_ruling_the_kept_value_again_after_an_edit_ties_it_to_the_sheet(grouped, tmp_path, capsys, ticking):
    """Rule 2 (their 2, the file 12); they edit the cell to 3; they rule 2 again."""
    theirs, _ = _ruled_ph(grouped, tmp_path, capsys, 2)
    _edit_ph(theirs, 2, 3)
    again = tmp_path / "again.xlsx"
    ph = _d(_adopt_json(grouped, theirs, again, capsys), "pH", run_id="run-007")
    assert ph["recorded_note"].startswith("recorded `2` (")
    _rule(again, tmp_path / "again_ruled.xlsx", {ph["id"]: 2})
    _ties_then_settles(grouped, theirs, tmp_path / "again_ruled.xlsx", ph["id"], 2, capsys, tmp_path)
    assert _ruling_notes(grouped)[-1]["note"].endswith("'File List'!H8 = 3)")


def test_ruling_for_a_file_value_confirmed_before_the_sheet_ties_it(grouped, tmp_path, capsys, ticking):
    """The file's pH 12 is confirmed; their sheet says 2; they rule 12 (keep the file's)."""
    M.decide(grouped, target_ids=[_cand(M.load(grouped), PH, "run-007")["candidate_id"]], decision="confirm", value=None,
             by=WHO, orcid=None)
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    ph = _d(_adopt_json(grouped, theirs, first, capsys), "pH", run_id="run-007")
    assert ph["recorded_note"].startswith("recorded `12` (")
    _rule(first, tmp_path / "ruled.xlsx", {ph["id"]: 12})
    _ties_then_settles(grouped, theirs, tmp_path / "ruled.xlsx", ph["id"], 12, capsys, tmp_path)
    assert _ruling_notes(grouped)[-1]["note"].endswith("'File List'!H8 = 2)")


def test_a_plain_cell_matching_the_recorded_value_records_nothing(grouped, tmp_path, capsys, ticking):
    """Only a ruling is tied: a File List cell typed with the value already recorded stays "already recorded"."""
    M.decide(grouped, target_ids=[_cand(M.load(grouped), PH, "run-007")["candidate_id"]], decision="correct", value=5,
             by=WHO, orcid=None)
    template = tmp_path / "template.xlsx"
    capsys.readouterr()
    assert cli.main(["bundle", "template", "export", str(grouped), "--out", str(template)]) == 0
    wb = openpyxl.load_workbook(template)
    wf = wb["File List"]
    col = next(c.column for c in wf[1] if c.value == "pH")
    row = next(int(v[1]) for v in wb["_isaac"].iter_rows(values_only=True) if v[0] == "File List" and v[2] == "run-007")
    wf.cell(row, col).value = 5
    wb.save(template)
    code, rep, err = _import(grouped, template, capsys, "--apply")
    assert code == 0, err
    assert rep["recorded"] == 0 and not rep["rulings_tied_to_sheet"] and len(rep["already_decided_same_value"]) == 1


# --- LOW-1 ----------------------------------------------------------------------------------------------------


def test_a_yes_no_or_a_date_ruled_on_is_ruled_here():
    where = ("SYN_their.xlsx", "'File List'!H8")
    for value in (True, False, dt.datetime(2099, 1, 2, 3, 4)):
        note = ("template x.xlsx 'Disagreements'!H4 (your ruling on disagreement D3: SYN_their.xlsx 'File List'!H8 = "
                f"{T._ruled_on_text(value)})")
        assert T._ruled_here([{"note": note}], 0, (*where, value)), value
        back, kept = T._marker_their_value({"their_value": T._ruled_on_text(value)})
        assert kept and T._ruled_here([{"note": note}], 0, (*where, back)), value  # as the import reads it back
    yes = "template x.xlsx 'Disagreements'!H4 (your ruling on disagreement D3: SYN_their.xlsx 'File List'!H8 = true)"
    assert not T._ruled_here([{"note": yes}], 0, (*where, False))
    assert not T._ruled_here([{"note": yes}], 0, (*where, 1))


# --- LOW-2 ----------------------------------------------------------------------------------------------------


def test_a_ruling_from_a_workbook_adopted_before_the_value_was_kept_names_no_value(grouped, tmp_path, capsys, ticking):
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    out = tmp_path / "adopted.xlsx"
    ph = _d(_adopt_json(grouped, theirs, out, capsys), "pH", run_id="run-007")
    wb = openpyxl.load_workbook(out)
    wm = wb["_isaac"]
    [(r0, c0)] = [(c.row, c.column) for row in wm.iter_rows() for c in row if c.value == "their_value"]
    for r in range(r0, wm.max_row + 1):
        wm.cell(r, c0).value = None
    wd = wb["Disagreements"]
    row = next(r for r in range(2, wd.max_row + 1) if wd[f"A{r}"].value == ph["id"])
    wd[f"D{row}"] = 99  # the scientist's edit of column D is never written into the note
    wd[f"H{row}"] = 12
    wb.save(tmp_path / "legacy.xlsx")
    code, rep, err = _import(grouped, tmp_path / "legacy.xlsx", capsys, "--apply")
    assert code == 0, err
    [d] = _ruling_notes(grouped)
    assert d["note"].endswith(f"{THEIRS} 'File List'!H8)") and " = " not in d["note"]


# --- LOW-3 ----------------------------------------------------------------------------------------------------


def test_a_request_kept_earlier_citing_every_cell_is_the_same_request(grouped, tmp_path, capsys, ticking):
    _answered_word(grouped, tmp_path, capsys)
    more = _their_sheet(grouped, tmp_path / "SYN_more.xlsx", rows=[*RUNS, "run-009"])
    assert _adopt(grouped, more, tmp_path / "more.xlsx", capsys, "--by", WHO)[0] == 0
    bundle = M.load(grouped)
    req = bundle["vocabulary_requests"][1]
    assert req["run_ids"] == ["run-009"] and req["source"]["cells"] == ["'File List'!F10"]
    req["source"]["cells"] = [f"'File List'!F{r}" for r in range(2, 11)]  # as a build before c14h kept it
    M.save_bundle(grouped, bundle)
    code, text, err = _adopt(grouped, more, tmp_path / "more2.xlsx", capsys, "--by", WHO)
    assert code == 0, err
    reqs = M.load(grouped)["vocabulary_requests"]
    assert [r["request_id"] for r in reqs] == ["vr-00001", "vr-00002"]
    # another request is never read as the same one: other runs, or a cell it does not cite
    entry = dict(field_path=req["field_path"], term=req["term"], by=WHO, run_ids=["run-008"],
                 source={"kind": req["source"]["kind"], "command": req["source"]["command"], "file": "SYN_more.xlsx",
                         "cells": ["'File List'!F10"]})
    assert M.vocabulary_request_kept(M.load(grouped), **entry) is None
    entry.update(run_ids=["run-009"], source={**entry["source"], "cells": ["'File List'!F11"]})
    assert M.vocabulary_request_kept(M.load(grouped), **entry) is None
    entry.update(source={**entry["source"], "cells": ["'File List'!F3"]})
    assert M.vocabulary_request_kept(M.load(grouped), **entry)["request_id"] == "vr-00002"
