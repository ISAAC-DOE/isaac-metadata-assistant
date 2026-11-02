"""c14f MED-1 and LOW-5: a sheet adopted again after the scientist ruled. Synthetic only (SYN_/ZZ names).

From a real walk (counts only): adopting the same sheet again after a new reading listed every one of 16
Disagreements rows as "awaits your ruling" with empty cells, though 14 were settled by the scientist's decisions; the
skill reads every disagreement back, so they would have been asked again. Now:

* a row whose field a scientist's confirming decision answers for every run it names says "already recorded: <value>
  (<date>); leave blank to keep", counted apart in the adopt summary and the import preview; a blank ruling keeps it;
* the "The sheet still says 'X' … answered since with `Y`" sentence is said with or without ``--by``, and a word
  answered for every run is listed apart, never as a word to keep or to draft;
* the import summary says "N decision(s) (from M cell(s)) already recorded", never cells and decisions mixed.
"""

from __future__ import annotations

import json
import re

import openpyxl

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import template as T

from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    THEIRS, WHO, _adopt, _adopt_json, _d, _import, _their_sheet, corpus, grouped, grouped_base, ticking)

ENV = "context.environment"
WORD = "aqueous_electrochemistry"


def _rule(xlsx, out, rulings: dict) -> None:
    """Type the scientist's rulings (``{disagreement id: value}``) in the Disagreements sheet."""
    wb = openpyxl.load_workbook(xlsx)
    wd = wb["Disagreements"]
    rows = {wd[f"A{r}"].value: r for r in range(2, wd.max_row + 1)}
    for did, value in rulings.items():
        wd[f"H{rows[did]}"] = value
    wb.save(out)


def _ruled(grouped, tmp_path, capsys, *adopt_args):
    """Adopt their sheet, rule two rows (the environment word, the dropped minus sign), and import them."""
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    first = tmp_path / "adopted.xlsx"
    code, _text, err = _adopt(grouped, theirs, first, capsys, *adopt_args)
    assert code == 0, err
    a = _adopt_json(grouped, theirs, tmp_path / "first.json.xlsx", capsys)
    env, minus = _d(a, "Environment", kind="not_allowed"), _d(a, "Potential (V)", run_id="run-005")
    _rule(first, tmp_path / "ruled.xlsx", {env["id"]: "in_situ", minus["id"]: -0.8})
    code, _rep, err = _import(grouped, tmp_path / "ruled.xlsx", capsys, "--apply")
    assert code == 0, err
    return theirs, a, env, minus


def test_adopting_again_marks_the_rows_already_ruled_and_a_blank_ruling_keeps_them(grouped, tmp_path, capsys, ticking):
    theirs, first, env, minus = _ruled(grouped, tmp_path, capsys)
    again = tmp_path / "adopted2.xlsx"
    a = _adopt_json(grouped, theirs, again, capsys)
    assert len(a["disagreements"]) == len(first["disagreements"])  # the same rows: their sheet still says it
    settled = {d["header"]: d for d in a["disagreements"] if d["already_recorded"]}
    assert set(settled) == {"Environment", "Potential (V)"}
    assert settled["Environment"]["already_recorded"]["values"] == ["in_situ"]
    assert re.fullmatch(r"already recorded: 'in_situ' \(2099-01-01\); leave blank to keep",
                        settled["Environment"]["already_recorded"]["statement"])
    assert settled["Potential (V)"]["already_recorded"]["statement"].startswith("already recorded: -0.8 (")
    assert not [d for d in a["disagreements"] if d["header"] == "pH"][0]["already_recorded"]  # never ruled: still asked
    # the Disagreements sheet says it on the row, and the ruling cell stays EMPTY
    wd = openpyxl.load_workbook(again)["Disagreements"]
    row = next(r for r in range(2, wd.max_row + 1) if wd[f"A{r}"].value == settled["Environment"]["id"])
    assert wd[f"B{row}"].value.startswith("already recorded: 'in_situ' (") and wd[f"H{row}"].value is None
    assert "adopt again" in wd[f"H{row}"].comment.text
    # the summary counts them apart, and never says every row awaits a ruling
    code, text, err = _adopt(grouped, theirs, tmp_path / "adopted3.xlsx", capsys)
    assert code == 0, err
    n = len(a["disagreements"])
    assert f"Disagreements already recorded: 2 of {n} (each says what is recorded; a blank ruling keeps it); {n - 2} await" in text
    assert "await your ruling, 1 already recorded (a blank ruling keeps it)" in text
    assert "[already recorded: 'in_situ' (" in text
    # the import preview: a blank ruling on a settled row keeps the value, listed apart, never as awaiting a ruling
    before = (grouped / "bundle.json").read_bytes()
    code, rep, err = _import(grouped, again, capsys)
    assert code == 0, err
    assert {x["id"] for x in rep["disagreements_already_recorded"]} == {d["id"] for d in settled.values()}
    assert not {x["id"] for x in rep["awaiting_ruling"]} & {d["id"] for d in settled.values()}
    assert {x["id"] for x in rep["awaiting_ruling"]} == {d["id"] for d in a["disagreements"] if not d["already_recorded"]}
    capsys.readouterr()
    assert cli.main(["bundle", "template", "import", str(grouped), str(again), "--by", WHO]) == 0
    text = capsys.readouterr().out
    assert "Disagreements already recorded (left blank, so the recorded value is kept" in text
    assert "2 disagreement(s) already recorded (blank: kept)" in text
    assert (grouped / "bundle.json").read_bytes() == before
    # --apply records nothing for them
    n0 = len(M.load(grouped)["scientist_decisions"])
    code, rep, err = _import(grouped, again, capsys, "--apply")
    assert code == 0, err
    assert rep["recorded"] == 0 and len(M.load(grouped)["scientist_decisions"]) == n0


def test_without_a_name_a_word_answered_since_is_said_and_listed_apart(grouped, tmp_path, capsys, ticking):
    theirs, *_ = _ruled(grouped, tmp_path, capsys, "--by", WHO)  # vr-00001 kept from their sheet, then ruled in_situ
    a = _adopt_json(grouped, theirs, tmp_path / "again.xlsx", capsys)  # no --by
    not_kept = a["vocabulary_requests_not_kept"]
    assert not_kept["words"] == [] and [w["term"] for w in not_kept["answered_since"]] == [WORD]
    [w] = not_kept["answered_since"]
    assert w["answered_since"]["every_run"] is True and w["answered_since"]["runs"] == 8
    code, text, err = _adopt(grouped, theirs, tmp_path / "again2.xlsx", capsys)
    assert code == 0, err
    assert f"The sheet still says '{WORD}' for {ENV} on 8 run(s), but it was answered since with `in_situ`" in text
    assert "Off-list values were not kept as requests: no name given" not in text  # nothing left to keep
    assert T.ANSWERED_SINCE_HEADING in text
    # with the name: the same word is not under "propose-terms can draft it", but apart
    code, text, err = _adopt(grouped, theirs, tmp_path / "again3.xlsx", capsys, "--by", WHO)
    assert code == 0, err
    assert "Kept as vocabulary requests" not in text and T.ANSWERED_SINCE_HEADING in text
    assert "[vr-00001, kept earlier]" in text and "answered since with `in_situ`" in text


def test_a_run_they_asked_for_the_word_again_is_not_said_as_answered(grouped, tmp_path, capsys, ticking):
    """Their sheet's request was answered for all 8 runs; then they kept their own word again for one run."""
    theirs, *_ = _ruled(grouped, tmp_path, capsys, "--by", WHO)
    target = next(m for m in M.load(grouped)["missing_values"] if m["target_field_path"] == ENV and m["run_id"] == "run-001")
    capsys.readouterr()
    assert cli.main(["bundle", "decide", str(grouped), "--target", target["value_id"], "--decision", "correct",
                     "--value", WORD, "--as-said", "--by", WHO]) == 0
    a = _adopt_json(grouped, theirs, tmp_path / "again.xlsx", capsys)  # no --by
    not_kept = a["vocabulary_requests_not_kept"]
    assert not_kept["answered_since"] == [] and [w["term"] for w in not_kept["words"]] == [WORD]
    [w] = not_kept["words"]
    assert w["answered_since"]["every_run"] is False and w["answered_since"]["runs"] == 7
    code, text, err = _adopt(grouped, theirs, tmp_path / "again2.xlsx", capsys)
    assert code == 0, err
    assert "Off-list values were not kept as requests: no name given (1 word(s)" in text
    assert f"The sheet still says '{WORD}' for {ENV} on 7 run(s)" in text and T.ANSWERED_SINCE_HEADING not in text


def test_without_a_name_an_unanswered_word_is_still_listed_as_not_kept(grouped, tmp_path, capsys):
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    a = _adopt_json(grouped, theirs, tmp_path / "adopted.xlsx", capsys)
    assert [w["term"] for w in a["vocabulary_requests_not_kept"]["words"]] == [WORD]
    assert a["vocabulary_requests_not_kept"]["answered_since"] == []
    assert not [d for d in a["disagreements"] if d["already_recorded"]]


def test_the_import_summary_counts_decisions_and_their_cells_apart(grouped, tmp_path, capsys, ticking):
    theirs = _their_sheet(grouped, tmp_path / THEIRS)
    out = tmp_path / "adopted.xlsx"
    _adopt_json(grouped, theirs, out, capsys)
    code, _rep, err = _import(grouped, out, capsys, "--apply")
    assert code == 0, err
    code, rep, err = _import(grouped, out, capsys)
    assert code == 0, err
    already = rep["already_decided_same_value"]
    cells = {x["cell"].split(" via ", 1)[0] for x in already}
    assert len(already) > len(cells) > 0  # a Configurations Technique cell reaches several runs
    capsys.readouterr()
    assert cli.main(["bundle", "template", "import", str(grouped), str(out), "--by", WHO]) == 0
    text = capsys.readouterr().out
    assert f"{len(already)} decision(s) (from {len(cells)} cell(s)) already recorded;" in text
    assert "already decided with the same value" not in text
    assert json.dumps(rep)  # the JSON report keeps its key
