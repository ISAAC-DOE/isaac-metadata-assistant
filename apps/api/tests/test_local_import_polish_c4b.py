"""Polish c4-b: walkthrough findings on one real beamtime, reproduced on the synthetic corpus. Synthetic only.

* (2) A template cell whose field this bundle asks ONCE for the whole beamtime (a shared conflict, a
  beamtime candidate) is not "recorded nowhere": the preview names that question and its command.
* (5) ``python -m isaac_api.local_import.extract`` on a spreadsheet writes each sheet's rows to a text file
  under ``--out`` and prints a compact manifest naming it; a cut sheet's ``read_rest.command`` starts with
  the interpreter that ran it (``python`` may not be on PATH).
* (4) A reading finding on a field path this bundle does not hold suggests the nearest real path(s) and,
  for a facility field, lists the facility paths there are.
* (8) A ``bundle list groups`` row marks a member that is the scientist's exported/processed file.
* (10b) A crosscheck-plan locator of a scan file with no scan number never reads "scan None".
* (11) The import's conflict count is said plainly.
* (12) A list cut by ``--limit`` says how to read the rest.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from isaac_api.local_import import cli
from isaac_api.local_import import extract as ex
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import suggestions as S
from isaac_api.local_import import template as T

from test_local_import_polish_c3t import _export, _fill, _sheet, _text
from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    WHO, _col, _import, _row_of, corpus, grouped, grouped_base)

TECH = "system.technique"


def _beamtime_question(b, path):
    """The synthetic corpus asks the technique once for the beamtime (a shared macro's name) and per run
    only for the runs whose files state a macro; run-001..003 have no run target."""
    ids = {c["candidate_id"] for c in b["candidates"] if c["target_field_path"] == path and c["run_id"] is None}
    return next(q for q in Q.consolidate(b)["questions"]
                if q.get("target_field_path") == path and ids & {t["id"] for t in q["targets"]})


# --- (2) a field asked beamtime-wide is never "recorded nowhere" ----------------------------------


def test_a_technique_cell_answered_by_the_beamtime_question_names_that_question(grouped, tmp_path, capsys):
    b = M.load(grouped)
    assert not [c for c in b["candidates"] if c["target_field_path"] == TECH and c["run_id"] == "run-001"]
    assert not [m for m in b["missing_values"] if m["target_field_path"] == TECH and m["run_id"] == "run-001"]
    q = _beamtime_question(b, TECH)
    xlsx = _export(grouped, tmp_path)
    r1 = _row_of(xlsx, "run-001")
    filled = _fill(xlsx, tmp_path / "f.xlsx", {("Configurations", "A2"): "C1", ("Configurations", "B2"): "XAS",
                                               ("File List", f"{_col('Config ID')}{r1}"): "C1"})
    code, rep, err = _import(grouped, filled, capsys)
    assert code == 0, err
    assert not [n for n in rep["recorded_nowhere"] if n["header"] == "Technique"]
    [asked] = rep["asked_beamtime_wide"]
    assert asked["question_id"] == q["question_id"] and asked["target_field_path"] == TECH
    assert asked["run_id"] == "run-001" and asked["value"] == "XAS" and asked["answered"] is False
    assert asked["command"].startswith(f"isaac bundle decide <bundle_dir> --question {q['question_id']}")
    assert "--value XAS" in asked["command"] and f"--by '{WHO}'" in asked["command"]

    code, text = _text(grouped, filled, capsys)
    assert code == 0
    assert "recorded nowhere: this run has no" not in text
    line = next(ln for ln in text.splitlines() if ln.startswith("  Technique") and q["question_id"] in ln)
    # the Configurations cell is named once (c7-s L2), however many File List rows reach it
    assert asked["command"] in line and "('Configurations'!B2)" in line
    assert "1 cell(s) asked once for the whole beamtime" in text
    assert not M.load(grouped)["scientist_decisions"]  # a preview

    # answered since: the line says so, and still gives the command that changes it
    M.record_decision(b, target_ids=[t["id"] for t in q["targets"]], decision="correct", value="XAS", by=WHO, orcid=None)
    M.save_bundle(grouped, b)
    code, rep, err = _import(grouped, filled, capsys)
    assert code == 0, err
    [asked] = rep["asked_beamtime_wide"]
    assert asked["answered"] is True and asked["question_id"] == q["question_id"]


# --- (5) the extractor writes each sheet to a text file and prints a compact manifest --------------


def _extract(capsys, argv):
    capsys.readouterr()
    code = ex.main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_a_spreadsheet_goes_to_text_files_and_the_printed_manifest_is_compact(tmp_path, capsys):
    root, path = _sheet(tmp_path, rows=78)
    out = tmp_path / "out"
    code, printed, err = _extract(capsys, [str(path), "--root", str(root), "--out", str(out)])
    assert code == 0, err
    m = json.loads(printed)
    sheet = next(s for s in m["sheets"] if s["name"] == "File List")
    # no row of the sheet is printed: each sheet names the file its rows went to
    assert "preview_rows" not in sheet and "header_rows" not in sheet and "S_02_dir" not in printed
    text_file = Path(sheet["text_file"])
    assert text_file.is_file() and out in text_file.parents
    text = text_file.read_text(encoding="utf-8")
    assert "S_02_dir | 0.2" in text and "S_50_dir" in text and "S_51_dir" not in text  # the cap is kept
    assert "rows 51..78 are NOT in this file" in text
    # the next page, exactly as printed, with the interpreter that ran it
    rest = sheet["read_rest"]
    assert rest["command"].startswith(f"{sys.executable} -m isaac_api.local_import.extract ")
    assert "--sheet 'File List' --rows-offset 50 --rows-limit 50" in rest["command"]
    notes = next(s for s in m["sheets"] if s["name"] == "Notes")
    assert Path(notes["text_file"]).read_text(encoding="utf-8").count("only") == 1
    assert notes["text_file"] != sheet["text_file"]

    code, printed, err = _extract(capsys, [str(path), "--root", str(root), "--out", str(out),
                                           "--sheet", "File List", "--rows-offset", "50", "--rows-limit", "50"])
    assert code == 0, err
    [page] = json.loads(printed)["sheets"]
    paged = Path(page["text_file"]).read_text(encoding="utf-8")
    assert "S_51_dir | 5.1" in paged and "S_78_dir" in paged and "S_50_dir" not in paged
    assert page["text_file"] != sheet["text_file"]  # one page does not overwrite the first
    assert "NOT in this file" not in paged and "read_rest" not in page


def test_the_library_manifest_still_holds_the_rows(tmp_path):
    root, path = _sheet(tmp_path, rows=12)
    m = ex.extract_source(path, tmp_path / "out")
    sheet = next(s for s in m["sheets"] if s["name"] == "File List")
    assert sheet["preview_rows"][0]["cells"] == ["Folder Name", "Potential (V)"]
    assert (tmp_path / "out" / sheet["text_file"]).is_file()


# --- (4) a finding on a path this bundle does not hold suggests the real one -----------------------


def _finding(path, value="SYN-7"):
    return {"format": "isaac.reading_findings", "findings": [
        {"field_path": path, "value": value, "applies_to": {"scope": "experiment"},
         "source": {"path": ".", "locator": "folder name"}, "quote": "SYN_BL99_beamtime", "strength": "inferred",
         "reasoning": "a name"}]}


def test_a_finding_on_a_short_facility_path_names_the_system_facility_paths(grouped):
    b = M.load(grouped)
    held = {m["target_field_path"] for m in b["missing_values"]} | {c["target_field_path"] for c in b["candidates"]}
    facility = sorted(p for p in held if p and p.startswith("system.facility."))
    assert "system.facility.beamline" in facility
    plan = S.readings_to_interpretations(b, _finding("facility.beamline"), model_id="synthetic-model")
    [skip] = plan["skipped"]
    assert skip["did_you_mean"] == ["system.facility.beamline"]
    assert "did you mean system.facility.beamline?" in skip["reason"]
    assert all(p in skip["reason"] for p in facility)
    assert "Kept in the findings file only" in skip["reason"]
    # the right path is placed
    assert not S.readings_to_interpretations(b, _finding("system.facility.beamline"), model_id="m")["skipped"]


def test_a_finding_on_an_unknown_path_suggests_by_its_last_segment_or_says_none(grouped):
    b = M.load(grouped)
    [skip] = S.readings_to_interpretations(b, _finding("sample.form", "film"), model_id="m")["skipped"]
    assert "sample.sample_form" in skip["did_you_mean"]
    [skip] = S.readings_to_interpretations(b, _finding("zzz.qqq", "x"), model_id="m")["skipped"]
    assert skip["did_you_mean"] == [] and "did you mean" not in skip["reason"]
    assert "system.facility" not in skip["reason"]  # the facility list is for a facility field only


# --- (8) a group row marks the exported/processed member -----------------------------------------


def test_a_group_row_marks_a_member_that_is_an_exported_file(grouped):
    b = copy.deepcopy(M.load(grouped))
    g, other = b["record_groups"][:2]
    runs = {r["run_key"]: r for r in b["runs"]}
    # the shape grouping gives an exported file joined to its run's group: a member, and context
    ctx = other["member_run_keys"][0]
    g["member_run_keys"] = [*g["member_run_keys"], ctx]
    g["context_run_keys"] = [ctx]
    rows = cli.group_list_extras(b)
    assert rows[g["group_id"]]["exported_file"] == [runs[ctx]["stem"]]
    assert rows[g["group_id"]]["exported_file_note"].startswith("the scientist's exported/processed file")
    assert all("exported_file" not in r for gid, r in rows.items() if gid != g["group_id"])


# --- (10b) crosscheck locators of a scan file with no scan number ---------------------------------


def test_a_crosscheck_locator_never_reads_scan_none(grouped):
    b = copy.deepcopy(M.load(grouped))
    run = b["runs"][0]
    run["scans"] = [dict(s, scan_index=None) for s in run["scans"]][:1]
    run["signal_selection"] = run.get("signal_selection") or {"synthetic": True}
    items = [i for i in M.crosscheck_plan(b)["items"] if i["target"] == {"kind": "run", "id": run["run_id"]}]
    locators = [loc["locator"] for i in items for loc in i["locators"]]
    assert locators and not [x for x in locators if "None" in x]
    assert "the scan file (one scan, no scan number)" in locators
    assert "the scan file's channel columns (one scan, no scan number)" in locators


# --- (11) the conflict count, plainly ---------------------------------------------------------------


def test_the_conflict_breakdown_says_where_the_sources_disagree_plainly(grouped):
    b = M.load(grouped)
    said = cli._conflict_breakdown(b)
    assert said and " on the " not in said
    n = b["counts"]["conflicting_candidates"]
    assert f"{n} where the sources disagree on a value" in said or f"on {n} value(s) the sources disagree about" in said


# --- (12) a cut list says how to read the rest ------------------------------------------------------


def test_a_cut_list_says_how_many_more_and_the_offset(grouped, capsys):
    capsys.readouterr()
    assert cli.main(["bundle", "list", str(grouped), "runs", "--limit", "4"]) == 0
    page = json.loads(capsys.readouterr().out)
    left = page["total"] - 4
    assert page["omitted_after"] == left and page["more"] == f"{left} more: --offset 4"
    assert cli.main(["bundle", "list", str(grouped), "runs", "--limit", "4", "--offset", str(page["total"] - 1)]) == 0
    assert "more" not in json.loads(capsys.readouterr().out)
    assert cli.main(["bundle", "crosscheck-plan", str(grouped), "--limit", "3"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["more"] == f"{plan['omitted_after']} more: --offset 3"
