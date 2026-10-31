"""c14g: when a re-adopted sheet's Disagreements row is settled. Synthetic only (SYN_/ZZ names).

* MED-1: a row is settled only when the value recorded equals the sheet's for every run, or was recorded by a ruling
  on this same disagreement in an earlier import of this sheet. A decision that only predates the sheet (the file's
  pH 12 confirmed, then the sheet says pH 2 for the first time) leaves the row awaiting: "recorded `12` (date); your
  sheet says `2`: rule which".
* MED-2: an Electrolyte row whose value states a concentration is settled only when the name AND the concentration
  are; with the name alone the concentration still awaits a ruling, and the import never drops it from every list.
* LOW-4: the ruling cell says ``--supersede`` only where the recorded value is the runs' own answer.
* LOW-6: with ``--by``, a sheet word whose runs changed is not kept again for runs answered since.
* LOW-7: a Campaign Info (whole-beamtime) row ruled earlier is settled.
"""

from __future__ import annotations

import openpyxl

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import template as T

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    PH, THEIRS, WHO, _adopt, _adopt_json, _cand, _d, _import, _their_sheet, corpus, grouped, grouped_base, ticking)

ENV = "context.environment"
WORD = "aqueous_electrochemistry"
RUNS = ["run-001", "run-002", "run-003", "run-004", "run-005", "run-006", "run-007", "run-008"]


def _rule(xlsx, out, rulings: dict, column: str = "H") -> None:
    wb = openpyxl.load_workbook(xlsx)
    wd = wb["Disagreements"]
    rows = {wd[f"A{r}"].value: r for r in range(2, wd.max_row + 1)}
    for did, value in rulings.items():
        wd[f"{column}{rows[did]}"] = value
    wb.save(out)


def _row_of(xlsx, did):
    wd = openpyxl.load_workbook(xlsx)["Disagreements"]
    return wd, next(r for r in range(2, wd.max_row + 1) if wd[f"A{r}"].value == did)


# --- MED-1 ----------------------------------------------------------------------------------------------------


def test_a_decision_older_than_the_sheet_leaves_the_row_awaiting(grouped, tmp_path, capsys, ticking):
    """The file's pH 12 for run-007 is confirmed; then their sheet says pH 2 for the first time."""
    M.decide(grouped, target_ids=[_cand(M.load(grouped), PH, "run-007")["candidate_id"]], decision="confirm", value=None,
             by=WHO, orcid=None)
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    out = tmp_path / "adopted.xlsx"
    a = _adopt_json(grouped, theirs, out, capsys)
    ph = _d(a, "pH", run_id="run-007")
    assert ph["already_recorded"] is None
    assert ph["recorded_note"] == "recorded `12` (2099-01-01); your sheet says `2`: rule which"
    wd, row = _row_of(out, ph["id"])
    assert wd[f"B{row}"].value.startswith("recorded `12` (2099-01-01); your sheet says `2`: rule which.")
    code, text, err = _adopt(grouped, theirs, tmp_path / "again.xlsx", capsys)
    assert code == 0, err
    assert "Disagreements already recorded" not in text and "[recorded `12` (2099-01-01); your sheet says `2`" in text
    code, rep, err = _import(grouped, out, capsys)
    assert code == 0, err
    [waiting] = [x for x in rep["awaiting_ruling"] if x["id"] == ph["id"]]
    assert waiting["why"].startswith("recorded `12` (2099-01-01); your sheet says `2`: rule which; readings:")
    assert not rep["disagreements_already_recorded"]


def test_a_ruling_from_an_earlier_import_of_the_sheet_settles_the_row(grouped, tmp_path, capsys, ticking):
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    ph = _d(_adopt_json(grouped, theirs, first, capsys), "pH", run_id="run-007")
    _rule(first, tmp_path / "ruled.xlsx", {ph["id"]: 12})
    assert _import(grouped, tmp_path / "ruled.xlsx", capsys, "--apply")[0] == 0
    again = _d(_adopt_json(grouped, theirs, tmp_path / "again.xlsx", capsys), "pH", run_id="run-007")
    assert again["already_recorded"]["settled"] is True and again["recorded_note"] is None
    assert again["already_recorded"]["statement"].startswith("already recorded: 12")


def test_a_recorded_value_equal_to_the_sheets_settles_the_row(grouped, tmp_path, capsys, ticking):
    """They said 2 themselves (decide), before the sheet: the sheet agrees with what is recorded."""
    M.decide(grouped, target_ids=[_cand(M.load(grouped), PH, "run-007")["candidate_id"]], decision="correct", value=2,
             by=WHO, orcid=None)
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    ph = _d(_adopt_json(grouped, theirs, tmp_path / "adopted.xlsx", capsys), "pH", run_id="run-007")
    assert ph["already_recorded"]["statement"].startswith("already recorded: 2 (")


def test_a_ruling_on_other_cells_does_not_settle_the_row(grouped, tmp_path, capsys, ticking):
    """The provenance is the same file AND cells: a ruling made for another sheet's cells is not this disagreement."""
    log = [{"note": "template x.xlsx 'Disagreements'!H4 (your ruling on disagreement D3: SYN_other.xlsx 'File List'!H8)"},
           {"note": "template x.xlsx 'Disagreements'!H4 (your ruling on disagreement D7: SYN_their.xlsx 'File List'!H8)"}]
    assert not T._ruled_here(log, 0, ("SYN_their.xlsx", "'File List'!H8"))
    assert T._ruled_here(log, 1, ("SYN_their.xlsx", "'File List'!H8"))  # the D number may change between adopts
    assert not T._ruled_here(log, 1, ("SYN_their.xlsx", "'File List'!H8, 'File List'!H9"))
    assert not T._ruled_here(log, 5, ("SYN_their.xlsx", "'File List'!H8"))


# --- MED-2 ----------------------------------------------------------------------------------------------------


def test_a_name_ruled_alone_leaves_the_concentration_awaiting(grouped, tmp_path, capsys, ticking):
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    el = _d(_adopt_json(grouped, theirs, first, capsys), "Electrolyte", kind="name_only")
    _rule(first, tmp_path / "name.xlsx", {el["id"]: "KOH"})
    code, rep, err = _import(grouped, tmp_path / "name.xlsx", capsys, "--apply")
    assert code == 0, err
    # the name is recorded; the concentration their sheet states is not dropped: it awaits a ruling
    [conc] = [x for x in rep["awaiting_ruling"] if x["id"] == el["id"]]
    assert conc["target_field_path"] == T.ELECTROLYTE_CONC_PATH
    assert conc["cell"].startswith(f"'Disagreements'!{T.DISAGREE_CONC_COLUMN}")
    again = tmp_path / "again.xlsx"
    el2 = _d(_adopt_json(grouped, theirs, again, capsys), "Electrolyte", kind="name_only")
    assert el2["already_recorded"] is None
    assert el2["recorded_note"] == "name recorded: 'KOH'; concentration awaits your ruling"
    code, rep, err = _import(grouped, again, capsys)
    assert code == 0, err
    assert [x["id"] for x in rep["disagreements_already_recorded"]] == [el2["id"]]  # the name is kept
    [waiting] = [x for x in rep["awaiting_ruling"] if x["id"] == el2["id"]]
    assert waiting["target_field_path"] == T.ELECTROLYTE_CONC_PATH
    assert waiting["why"] == "name recorded: 'KOH'; concentration awaits your ruling"
    # both ruled: settled
    _rule(again, tmp_path / "both.xlsx", {el2["id"]: 0.1}, column=T.DISAGREE_CONC_COLUMN)
    assert _import(grouped, tmp_path / "both.xlsx", capsys, "--apply")[0] == 0
    el3 = _d(_adopt_json(grouped, theirs, tmp_path / "third.xlsx", capsys), "Electrolyte", kind="name_only")
    assert el3["already_recorded"]["statement"].startswith("already recorded: name 'KOH', concentration 0.1 M (")
    code, rep, err = _import(grouped, tmp_path / "third.xlsx", capsys)
    assert code == 0, err
    assert not [x for x in rep["awaiting_ruling"] if x["id"] == el3["id"]]


# --- LOW-4 ----------------------------------------------------------------------------------------------------


def test_supersede_is_said_only_where_the_value_is_the_runs_own():
    path = "context.electrochemistry.potential_scale"  # takes a beamtime-wide answer
    own = {(path, "run-1"): [("RHE", "2099-01-01T00:00:01Z", 0)]}
    wide = {(path, None): [("RHE", "2099-01-01T00:00:01Z", 0)]}
    assert T.recorded_ruling(own, path, ["run-1"], "run", their_value="RHE")["run_own"] is True
    rec = T.recorded_ruling(wide, path, ["run-1"], "run", their_value="RHE")
    assert rec["settled"] is True and rec["run_own"] is False


def test_the_ruling_cell_of_a_settled_row_says_supersede(grouped, tmp_path, capsys, ticking):
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    env = _d(_adopt_json(grouped, theirs, first, capsys), "Environment", kind="not_allowed")
    _rule(first, tmp_path / "ruled.xlsx", {env["id"]: "in_situ"})
    assert _import(grouped, tmp_path / "ruled.xlsx", capsys, "--apply")[0] == 0
    again = tmp_path / "again.xlsx"
    env2 = _d(_adopt_json(grouped, theirs, again, capsys), "Environment", kind="not_allowed")
    assert env2["already_recorded"]["run_own"] is True
    wd, row = _row_of(again, env2["id"])
    assert "only with `template import --supersede`" in wd[f"H{row}"].comment.text
    # and that is true: a different ruling is a clash without it
    _rule(again, tmp_path / "other.xlsx", {env2["id"]: "ex_situ"})
    code, rep, err = _import(grouped, tmp_path / "other.xlsx", capsys)
    assert code == 0, err
    assert rep["clashes"] and rep["would_record"] == 0


# --- LOW-6 ----------------------------------------------------------------------------------------------------


def _answered_word(grouped, tmp_path, capsys):
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    assert _adopt(grouped, theirs, first, capsys, "--by", WHO)[0] == 0  # vr-00001: the word for 8 runs
    env = _d(_adopt_json(grouped, theirs, tmp_path / "a.xlsx", capsys), "Environment", kind="not_allowed")
    _rule(first, tmp_path / "ruled.xlsx", {env["id"]: "in_situ"})
    assert _import(grouped, tmp_path / "ruled.xlsx", capsys, "--apply")[0] == 0


def _term_draft(grouped, capsys):
    import json

    capsys.readouterr()
    assert cli.main(["bundle", "propose-terms", str(grouped)]) == 0
    report = json.loads(capsys.readouterr().out)
    return next(t for f in report["fields"] if f["field_path"] == ENV for t in f["terms"] if t["term"] == WORD)


def test_a_sheet_word_on_fewer_runs_is_not_kept_again_once_answered(grouped, tmp_path, capsys, ticking):
    _answered_word(grouped, tmp_path, capsys)
    fewer = _their_sheet(grouped, tmp_path / "SYN_fewer.xlsx", rows=RUNS[:7])  # other cells, other runs
    code, text, err = _adopt(grouped, fewer, tmp_path / "fewer.xlsx", capsys, "--by", WHO)
    assert code == 0, err
    assert [r["request_id"] for r in M.load(grouped)["vocabulary_requests"]] == ["vr-00001"]  # nothing new kept
    assert T.ANSWERED_SINCE_HEADING in text and "Kept as vocabulary requests" not in text
    t = _term_draft(grouped, capsys)
    assert t["draft"]["answered"] is True and t["draft"]["drafted"] is False


def test_a_sheet_word_on_a_new_run_is_kept_for_that_run_only(grouped, tmp_path, capsys, ticking):
    _answered_word(grouped, tmp_path, capsys)
    more = _their_sheet(grouped, tmp_path / "SYN_more.xlsx", rows=[*RUNS, "run-009"])
    code, text, err = _adopt(grouped, more, tmp_path / "more.xlsx", capsys, "--by", WHO)
    assert code == 0, err
    reqs = M.load(grouped)["vocabulary_requests"]
    assert [r["request_id"] for r in reqs] == ["vr-00001", "vr-00002"] and reqs[1]["run_ids"] == ["run-009"]
    assert "Kept as vocabulary requests" in text and "answered since with `in_situ`" in text
    t = _term_draft(grouped, capsys)
    assert t["draft"]["drafted"] is True and t["run_ids"] == ["run-009"]
    assert "answered_before_request" not in t["draft"]  # the answered runs are not read as "before" a fresh request


# --- LOW-7: a whole-beamtime row --------------------------------------------------------------------------------


def test_a_campaign_info_row_ruled_earlier_is_settled(grouped, tmp_path, capsys, ticking):
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    bl = _d(_adopt_json(grouped, theirs, first, capsys), "Beamline/Instrument")
    assert bl["scope"] == "experiment" and bl["already_recorded"] is None
    _rule(first, tmp_path / "ruled.xlsx", {bl["id"]: "BL99"})
    code, rep, err = _import(grouped, tmp_path / "ruled.xlsx", capsys, "--apply")
    assert code == 0, err
    assert rep["recorded"] > 0
    again = tmp_path / "again.xlsx"
    bl2 = _d(_adopt_json(grouped, theirs, again, capsys), "Beamline/Instrument")
    assert bl2["already_recorded"]["statement"].startswith("already recorded: 'BL99' (")
    code, rep, err = _import(grouped, again, capsys)
    assert code == 0, err
    assert bl2["id"] in [x["id"] for x in rep["disagreements_already_recorded"]]
    assert bl2["id"] not in [x["id"] for x in rep["awaiting_ruling"]]
