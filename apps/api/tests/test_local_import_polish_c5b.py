"""Walkthrough findings on a real BL6-2c beamtime (polish c5-b). Synthetic only.

* The scientist's Athena result says which scans its curve used (the label's selection, the per-scan set,
  or "the project does not say"), carries a ``used`` input and no unexplained ``scans_used: null``; ISAAC's
  skipped scans get a sentence in ``qc.statements``, said AFTER the run id (``qc.json`` is hashed into it), so
  no result id moves. ``list processing-results`` rows and ``show processing-result`` carry a ``scans`` line.
* ``crosscheck-plan`` gives ``high_value_total`` (and names the categories) for "N of M high-value items".
* ``list unread`` says what ``read_by`` means once per page, with a short marker on the row.
* summary.md collapses a folder's identical unread lines and does not say "no value is confirmed" once a
  scientist has decided values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

from test_local_import_records import BY, _decide_everything, bdir, pristine  # noqa: F401  (fixtures)

SKILL = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "isaac-historical-import"


def _run(capsys, *argv):
    code = cli.main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


# --- 1. which scans each result used -------------------------------------------------------------------


def _processing_helpers():
    pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")
    import test_local_import_processing as P
    import test_local_import_processing_not_applicable as NA

    return P, NA


def _athena_run(tmp_path, label, *, stem="01_SYN_ZZ1"):
    P, _ = _processing_helpers()
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir_, root = P._athena_case(tmp_path, {"SYN.prj": [(label, P.GRID, P.mu_edge(P.GRID) * 1e-2)]}, stem=stem)
    out = run_process(bdir_, source_root=root)
    isa, sci = out["processing_results"]
    assert (isa["source"], sci["source"]) == ("isaac_protocol", "scientist_athena")
    return isa, sci


def test_an_athena_label_that_names_scans_says_which_and_marks_the_group_used(tmp_path):
    isa, sci = _athena_run(tmp_path, "01_SYN_ZZ1_1-2")
    [ref] = sci["inputs"]
    assert ref["used"] is True and ref["scans_basis"] == "label" and ref["scans"] == [1, 2]
    said = sci["qc"]["statements"]["scans_used"]
    assert "scans 1-2" in said and "label" in said and "ISAAC's own curve for this group merges 2 of 2 listed scans" in said
    assert sci["qc"]["metrics"]["scans_used"] is None and sci["qc"]["verdict"] == "pass"  # the verdict is not moved


def test_an_athena_label_naming_no_scan_says_the_project_does_not_say(tmp_path):
    isa, sci = _athena_run(tmp_path, "01_SYN_ZZ1")
    [ref] = sci["inputs"]
    assert ref["used"] is True and ref["scans_basis"] == "not_stated" and ref["scans"] is None
    said = sci["qc"]["statements"]["scans_used"]
    assert said.startswith("The project does not say which scans the scientist's curve used")
    assert "'01_SYN_ZZ1'" in said and "ISAAC's own curve for this group merges 2 of 2" in said
    assert "C:" not in said and "\\" not in said  # a file's name, never the scientist's folder path


def test_a_skipped_scan_gets_a_sentence_and_no_result_id_moves(tmp_path):
    P, NA = _processing_helpers()
    from isaac_api.local_import.processing import run as RUN

    scans = [P.spec_file(NA._motor_scan(1)), P.spec_file(P.fluo_scan(2)), P.spec_file(P.fluo_scan(3))]
    r = NA._one(tmp_path, scans)
    said = r["qc"]["statements"]["scans_skipped_lacking_chosen_columns"]
    assert said.startswith("2 of 3 listed scans were used. 1 was left out because it lacks the columns chosen for this group")
    assert "energy energy" in said and r["inputs"][0]["source_id"] in said and "motor or alignment" in said
    # qc.json is hashed into the run id, so the sentence is NOT in it: the result id is what it was before
    qc_file = next(f for f in r["outputs"]["files"] if f["role"] == "qc")
    root = Path(tmp_path)
    on_disk = json.loads(next(root.rglob(Path(qc_file["relative_path"]).name)).read_text())
    assert "scans_skipped_lacking_chosen_columns" not in (on_disk.get("statements") or {})
    assert r["result_id"].endswith(f"{r['run_id']}-isaac") and RUN.run_id_for  # id still content-addressed


def test_a_group_with_no_skipped_scan_has_no_skip_sentence(tmp_path):
    P, NA = _processing_helpers()
    r = NA._one(tmp_path, [P.spec_file(P.fluo_scan(2)), P.spec_file(P.fluo_scan(3))])
    assert "statements" not in r["qc"]


def test_list_row_and_show_carry_a_scans_line(bdir, capsys):
    _decide_everything(bdir)
    b = M.load(bdir)
    p1 = next(x for x in b["processing_results"] if x["result_id"] == "p1")
    p1["source"] = "isaac_protocol"
    p1["inputs"] = [{"source_id": "s1", "scan": 1, "used": True}, {"source_id": "s2", "scan": 2, "used": False, "skip_reason": "scan_lacks_chosen_columns"}]
    p1["qc"] = {**p1["qc"], "metrics": {"scans_listed": 2, "scans_used": 1}}
    sci = dict(p1, result_id="p1-athena", source="scientist_athena", preferred_for_record=False,
               inputs=[{"source_id": "prj", "used": True, "scans_basis": "not_stated", "scans": None}])
    sci2 = dict(sci, result_id="p1-athena2", inputs=[{"source_id": "prj", "used": True, "scans_basis": "label", "scans": [1, 3, 4, 5]}])
    b["processing_results"] += [sci, sci2]
    M.save_bundle(bdir, b)
    code, out, _ = _run(capsys, "bundle", "list", str(bdir), "processing-results")
    rows = {r["result_id"]: r for r in json.loads(out)["items"]}
    assert rows["p1"]["scans"] == "1 of 2 scans used; 1 skipped (scan_lacks_chosen_columns)"
    assert rows["p1-athena"]["scans"] == "the project does not say which scans"
    assert rows["p1-athena2"]["scans"].startswith("scans 1,3-5 (named by the Athena label")
    code, out, _ = _run(capsys, "bundle", "show", str(bdir), "processing-result", "p1-athena")
    shown = json.loads(out)
    assert shown["scans"] == "the project does not say which scans" and shown["inputs"]["used"] == 1


# --- 2. the cross-check's denominator -----------------------------------------------------------------


def test_the_plan_gives_the_high_value_denominator_and_names_the_categories(bdir):
    plan = M.crosscheck_plan(M.load(bdir))
    cats = plan["high_value_categories"]
    assert cats == ["sample_identity", "potential_or_reference_basis", "reaction", "environment", "cell_type", "acquisition_time"]
    hv = [i for i in plan["items"] if i["category"] in cats and i["excerptable"]]
    assert plan["high_value_total"] == len(hv) > 0
    assert plan["total"] > plan["high_value_total"]  # run_association and required_by_record are listed but not high-value
    assert plan["coverage"]["high_value_checked"] == 0 and plan["coverage"]["high_value_blind_checked"] == 0
    target = hv[0]["target"]["id"]
    M.annotate(bdir, target_id=target, value="x", excerpt_locator=None, source_id=None, model_id="syn", blind=False, rationale="t")
    after = M.crosscheck_plan(M.load(bdir))
    assert after["high_value_total"] == plan["high_value_total"]
    assert after["coverage"]["high_value_checked"] == 1 and after["coverage"]["high_value_blind_checked"] == 0
    assert f"1 of {plan['high_value_total']} high-value items (0 blind)" in after["coverage"]["high_value_statement"]


def test_the_blind_crosscheck_reference_names_the_denominator():
    text = (SKILL / "reference" / "blind-crosscheck.md").read_text(encoding="utf-8")
    assert "high_value_total" in text and "high_value_categories" in text and "coverage.high_value_checked" in text


def _unread(source_id: str, rel: str) -> dict:
    return {"relative_path": rel, "source_id": source_id, "source_type": "unknown", "reason_code": "no_reader_for_source_type",
            "reason": "This build has no reader for this kind of source.", "local_only": True}


# --- 3. list unread says read_by once -----------------------------------------------------------------


def test_list_unread_says_what_read_by_means_once(bdir, capsys):
    b = M.load(bdir)
    b["unread_files"] += [_unread(f"src-9{n:03d}", f"Norm/prj_{n}.prj") for n in range(30)]
    M.save_bundle(bdir, b)
    code, out, _ = _run(capsys, "bundle", "list", str(bdir), "unread", "--limit", "50")
    payload = json.loads(out)
    prj = [i for i in payload["items"] if i.get("read_by")]
    assert len(prj) == 30 and {i["read_by"] for i in prj} == {"isaac process"}
    assert payload["read_by_note"].count("Athena project") == 1 and "isaac process" in payload["read_by_note"]
    assert out.count("matched by name to record groups") == 1  # the long sentence is on the page, not on 30 rows
    code, out, _ = _run(capsys, "bundle", "list", str(bdir), "unread", "--limit", "5", "--offset", "0")
    first = json.loads(out)
    if not any(i.get("read_by") for i in first["items"]):
        assert "read_by_note" not in first


# --- 4. summary.md --------------------------------------------------------------------------------------


def test_summary_collapses_a_folders_repeated_unread_lines(bdir):
    b = M.load(bdir)
    b["unread_files"] = [_unread(f"src-8{n:03d}", f"Normalized/Igor aligned/2_SYNParticle_{n:02d}.itx") for n in range(10)]
    b["unread_files"].append(_unread("src-8999", "notes/readme.txt"))
    b["counts"]["unread_files"] = len(b["unread_files"])
    text = cli.render_summary(b)
    section = text.split("## Unread files", 1)[1].split("## Readiness", 1)[0]
    lines = [ln for ln in section.splitlines() if ln.startswith("- ")]
    assert len(lines) == 2
    assert lines[0] == "- Normalized/Igor aligned/: 10 files — no_reader_for_source_type"
    assert lines[1] == "- notes/readme.txt — no_reader_for_source_type"


def test_summary_after_decisions_does_not_say_nothing_is_confirmed(bdir):
    fresh = cli.render_summary(M.load(bdir))
    assert "Nothing" in fresh and "No value here is confirmed" in fresh  # an import with no decision says so
    _decide_everything(bdir)
    b = M.load(bdir)
    text = cli.render_summary(b)
    assert "No value here is confirmed" not in text and "Nothing\n> here is confirmed" not in text
    n = len(b["scientist_decisions"])
    assert f"Scientist decisions recorded: {n} (" in text and "confirm on record group" in text
    eligible = b["readiness"]["eligible_value_count"]
    assert f"{eligible} value(s) are eligible for an official record because a scientist decided them" in text
    assert "does not know whether a record has been exported" in text and "isaac-export/index.json" in text


def test_summary_tells_two_long_folders_apart_by_their_ends(bdir):
    b = M.load(bdir)
    root = "Normalized/Igor aligned and Athena normalized/2_SYNParticlesOnAu"
    b["unread_files"] = [_unread(f"src-7{n:03d}", f"{root}/PeakFits_{year}Renorm/f_{n}.pxp")
                         for year in (2021, 2023) for n in range(3)]
    b["counts"]["unread_files"] = len(b["unread_files"])
    section = cli.render_summary(b).split("## Unread files", 1)[1].split("## Readiness", 1)[0]
    lines = [ln for ln in section.splitlines() if ln.startswith("- ")]
    assert len(lines) == 2 and lines[0] != lines[1]
    assert lines[0].endswith("PeakFits_2021Renorm/: 3 files — no_reader_for_source_type") and "PeakFits_2023Renorm/: 3 files" in lines[1]
