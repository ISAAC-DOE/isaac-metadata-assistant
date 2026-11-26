"""The quote check on loading a reading pass, and scan notes (bundle 1.12.0).

* ``annotate --from-readings`` holds every finding's quote against the file it cites under the imported folder:
  near a ``line N`` locator (within ``reading_check.LINE_TOLERANCE`` lines), in the extractor's text for a
  document, in the header lines for a SPEC header locator. ``--apply`` records no finding whose quote is not
  found, and refuses outright with no folder to check against; there is no flag to skip it.
* A path outside the folder, or through a symbolic link, is refused.
* A ``scan_note`` finding is kept in ``bundle["scan_notes"]``: listed, shown on its run, read by
  ``scan_notes.scan_notes_for_run``; an older bundle without the section still validates.
* ``bundle check-readings`` prints the same report.

SYNTHETIC ``SYN_`` files only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import reading_check as RC
from isaac_api.local_import import scan_notes as SN
from isaac_api.local_import import suggestions as S

from test_local_import_extract import make_docx
from test_local_import_suggestions import _beamtime

#: A synthetic logbook: the quotes below are on the lines named.
LOGBOOK = [f"synthetic filler line {n}" for n in range(1, 41)]
LOGBOOK[9] = "SYN_cell was measured in situ in the synthetic cell"  # line 10
LOGBOOK[19] = "File 27: discard the first scan,   the synthetic beam was unstable"  # line 20
LOGBOOK[20] = "start from scan #5 and ignore scan 8 (went to open circuit)"  # line 21
LOGBOOK[29] = "potentiostat jumped to 2.5 V during this file"  # line 30
DOCX_BODY = ("<w:p><w:r><w:t>Synthetic notes heading</w:t></w:r></w:p>"
             "<w:p><w:r><w:t>The SYN_cell sample sat in a synthetic “flow” cell</w:t></w:r></w:p>")


def _run(argv, capsys):
    code = cli.main(argv)
    return code, capsys.readouterr().out


@pytest.fixture()
def beamtime(tmp_path, capsys):
    bt = _beamtime(tmp_path / "src")
    (bt / "SYN_logbook.txt").write_text("\n".join(LOGBOOK) + "\n", encoding="utf-8")
    make_docx(bt / "SYN_notes.docx", body_xml=DOCX_BODY)
    out = tmp_path / "out"
    assert _run(["import", str(bt), "--out", str(out)], capsys)[0] == 0
    assert _run(["bundle", "group", str(out)], capsys)[0] == 0
    return bt, out


def _finding(**over) -> dict:
    f = {"field_path": "context.environment", "value": "in_situ",
         "applies_to": {"scope": "runs", "runs": ["SYN_cell"]},
         "source": {"path": "SYN_logbook.txt", "locator": "line 10"},
         "quote": "SYN_cell was measured in situ", "strength": "stated", "reasoning": "synthetic"}
    f.update(over)
    return f


def _note(**over) -> dict:
    f = {"kind": "scan_note", "applies_to": {"scope": "runs", "runs": ["SYN_cell"]}, "action": "exclude", "scans": [1],
         "reason": "the synthetic beam was unstable", "source": {"path": "SYN_logbook.txt", "locator": "line 20"},
         "quote": "discard the first scan, the synthetic beam was unstable", "strength": "stated", "reasoning": "synthetic"}
    f.update(over)
    return f


def _file(*findings) -> dict:
    return {"format": S.READINGS_FORMAT, "findings": list(findings)}


def _load(out: Path) -> dict:
    return json.loads((out / "bundle.json").read_text())


# --- the quote check --------------------------------------------------------------------------------------------


def test_a_quote_not_in_the_cited_file_is_refused_on_apply_and_the_good_one_is_recorded(beamtime):
    bt, out = beamtime
    f = _file(_finding(), _finding(quote="SYN_cell was measured ex situ", value="ex_situ"))
    preview = M.annotate_from_readings(out, f, model_id="m", apply=False, root=bt)
    assert preview["quote_check"]["passed"] == 1 and preview["quote_check"]["failed"] == 1
    assert [r["result"] for r in preview["quote_check"]["results"]] == ["pass", "fail"]
    done = M.annotate_from_readings(out, f, model_id="m", apply=True, root=bt)
    assert done["applied"] is True and done["interpretations"] == 1
    assert done["refused"] == 1 and done["refused_by_reason"] == {"quote_not_found": 1}
    [s] = done["skipped"]
    assert s["finding"] == "finding-002" and s["refused"] == "quote_not_found" and "not found" in s["reason"]
    assert [i["proposed_value"] for i in _load(out)["ai_interpretations"]] == ["in_situ"]


def test_apply_refuses_without_a_folder_to_check_against_and_has_no_skip_flag(beamtime, tmp_path, capsys):
    bt, out = beamtime
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(_file(_finding())))
    before = (out / "bundle.json").read_bytes()
    code, _ = _run(["bundle", "annotate", str(out), "--from-readings", str(path), "--model", "m", "--apply"], capsys)
    assert code != 0 and (out / "bundle.json").read_bytes() == before
    code, text = _run(["bundle", "annotate", str(out), "--from-readings", str(path), "--model", "m"], capsys)
    assert code == 0 and json.loads(text)["quote_check"]["run"] is False
    flags = {o for a in cli.build_parser()._subparsers._group_actions[0].choices["bundle"]._subparsers._group_actions[0]
             .choices["annotate"]._actions for o in a.option_strings}
    assert not [f for f in flags if "check" in f or "skip" in f or "force" in f]
    code, text = _run(["bundle", "annotate", str(out), "--from-readings", str(path), "--model", "m", "--apply",
                       "--root", str(bt)], capsys)
    assert code == 0 and json.loads(text)["interpretations"] == 1


@pytest.mark.parametrize(("locator", "ok"), [("line 10", True), ("line 13", True), ("line 7", True), ("lines 8-9", True),
                                             ("line 14", False), ("line 6", False), ("line 99", False)])
def test_a_quote_passes_within_three_lines_of_its_locator_and_fails_further_away(beamtime, locator, ok):
    bt, _ = beamtime
    [r] = RC.check_findings([_finding(source={"path": "SYN_logbook.txt", "locator": locator})], bt)
    assert (r["result"] == RC.PASS) is ok
    if not ok and locator != "line 99":
        assert "the quote is at line 10" in r["reason"]


def test_whitespace_and_typographic_marks_compare_plainly_but_case_is_kept(beamtime):
    bt, _ = beamtime
    ok = _note(quote="discard the first scan, the synthetic beam was unstable")  # 3 spaces and a no-break space in the file
    spans = _note(source={"path": "SYN_logbook.txt", "locator": "lines 20-21"},
                  quote="was unstable start from scan #5")  # across two lines
    cased = _note(quote="Discard the first scan")
    assert [r["result"] for r in RC.check_findings([ok, spans, cased], bt)] == ["pass", "pass", "fail"]


def test_a_docx_quote_is_checked_against_the_extractors_text(beamtime):
    bt, _ = beamtime
    good = _finding(source={"path": "SYN_notes.docx", "locator": "paragraph 2"}, quote='sat in a synthetic "flow" cell')
    bad = _finding(source={"path": "SYN_notes.docx", "locator": "paragraph 2"}, quote="sat in a synthetic static cell")
    a, b = RC.check_findings([good, bad], bt)
    assert a["result"] == RC.PASS and "extractor" in a["at"]
    assert b["result"] == RC.FAIL and "extractor" in b["reason"]


def make_pdf(path: Path, pages: list[str | None]) -> Path:
    """A minimal hand-written PDF: one page per entry, its text drawn in Helvetica (``None``: a page with no text
    layer, as a scan has). Offsets in the cross-reference table are computed, so pypdf reads it strictly."""
    n = len(pages)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            ("<< /Type /Pages /Kids [" + " ".join(f"{4 + 2 * k} 0 R" for k in range(n)) + f"] /Count {n} >>").encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for k, text in enumerate(pages):
        body = b"" if text is None else ("BT /F1 12 Tf 72 720 Td (" + text.replace("\\", "\\\\").replace("(", "\\(")
                                         .replace(")", "\\)") + ") Tj ET").encode("latin-1")
        objs.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                     f"/Contents {5 + 2 * k} 0 R >>").encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream")
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for k, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % k + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))
    return path


PDF_PAGES = ["Synthetic logbook page one", "SYN_cell was measured in situ in the synthetic cell", None]


def _pdf(bt: Path, locator: str, quote: str = "SYN_cell was measured in situ") -> dict:
    make_pdf(bt / "SYN_logbook.pdf", PDF_PAGES)
    [r] = RC.check_findings([_finding(source={"path": "SYN_logbook.pdf", "locator": locator}, quote=quote)], bt)
    return r


def test_a_pdf_quote_is_checked_on_the_page_cited_or_anywhere_and_says_where(beamtime):
    pytest.importorskip("pypdf")
    bt, _ = beamtime
    r = _pdf(bt, "page 2")
    assert r["result"] == RC.PASS and r["at"].startswith("page 2")
    r = _pdf(bt, "the step table")
    assert r["result"] == RC.PASS and r["at"].startswith("page 2") and "whole PDF" in r["at"]
    r = _pdf(bt, "page 1")
    assert r["result"] == RC.FAIL and "the quote is on page 2" in r["reason"]
    r = _pdf(bt, "page 2", quote="SYN_cell was measured ex situ")
    assert r["result"] == RC.FAIL and "nor anywhere" in r["reason"]
    r = _pdf(bt, "page 9")
    assert r["result"] == RC.FAIL and "3 page(s)" in r["reason"]


def test_a_pdf_page_with_no_text_layer_is_refused_with_the_reason(beamtime):
    pytest.importorskip("pypdf")
    bt, out = beamtime
    r = _pdf(bt, "page 3")
    assert r["result"] == RC.FAIL and r["reason"] == f"page 3: {RC.NO_TEXT_LAYER}"
    make_pdf(bt / "SYN_scan.pdf", [None, None])
    [r] = RC.check_findings([_finding(source={"path": "SYN_scan.pdf", "locator": "p. 1"})], bt)
    assert r["result"] == RC.FAIL and RC.NO_TEXT_LAYER in r["reason"]
    done = M.annotate_from_readings(out, _file(_finding(source={"path": "SYN_logbook.pdf", "locator": "page 3"})),
                                    model_id="m", apply=True, root=bt)
    assert done["interpretations"] == 0 and done["refused_by_reason"] == {"quote_not_found": 1}


def test_without_the_pdf_reader_a_pdf_quote_is_refused_naming_the_install(beamtime, monkeypatch):
    import builtins

    bt, _ = beamtime
    real = builtins.__import__

    def no_pypdf(name, *a, **kw):
        if name == "pypdf" or name.startswith("pypdf."):
            raise ImportError("synthetic: pypdf missing")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_pypdf)
    r = _pdf(bt, "page 2")
    assert r["result"] == RC.FAIL and "not installed" in r["reason"] and ".[reading]" in r["reason"]


def test_a_file_that_is_not_a_pdf_is_refused_never_raised(beamtime):
    pytest.importorskip("pypdf")
    bt, _ = beamtime
    (bt / "SYN_proposal.pdf").write_bytes(b"%PDF-1.4\n% synthetic, no objects\n")
    [r] = RC.check_findings([_finding(source={"path": "SYN_proposal.pdf", "locator": "page 1"})], bt)
    assert r["result"] == RC.FAIL and "PDF" in r["reason"]


def test_a_spec_header_locator_is_checked_against_that_scans_header_lines(tmp_path):
    (tmp_path / "SYN_spec.dat").write_text("#F SYN\n#S 1 synthetic\n#C first synthetic comment\n1 2\n"
                                           "#S 2 synthetic\n#C mono reset synthetic\n3 4\n", encoding="utf-8")
    cite = {"path": "SYN_spec.dat", "locator": "scan 2 #C"}
    a, b, c = RC.check_findings([_finding(source=cite, quote="mono reset synthetic"),
                                 _finding(source=cite, quote="first synthetic comment"),
                                 _finding(source={"path": "SYN_spec.dat", "locator": "#C"}, quote="first synthetic comment")],
                                tmp_path)
    assert (a["result"], b["result"], c["result"]) == (RC.PASS, RC.FAIL, RC.PASS)
    assert "scan 2" in b["reason"]


def test_a_path_outside_the_folder_or_through_a_symbolic_link_is_refused(beamtime, tmp_path):
    bt, out = beamtime
    (bt.parent / "SYN_beside.txt").write_text("SYN_cell was measured in situ\n")
    (bt / "SYN_link.txt").symlink_to(bt.parent / "SYN_beside.txt")
    os.symlink(bt.parent, bt / "SYN_dirlink")
    cases = ["../SYN_beside.txt", str(bt.parent / "SYN_beside.txt"), "SYN_link.txt", "SYN_dirlink/SYN_beside.txt",
             "proc/../../SYN_beside.txt", "SYN_missing.txt"]
    results = RC.check_findings([_finding(source={"path": p, "locator": "line 1"}) for p in cases], bt)
    assert all(r["result"] == RC.FAIL for r in results)
    reasons = [r["reason"] for r in results]
    assert "leaves the imported folder" in reasons[0] and "never absolute" in reasons[1]
    assert "symbolic link" in reasons[2] and "symbolic link" in reasons[3] and "leaves" in reasons[4]
    done = M.annotate_from_readings(out, _file(_finding(source={"path": "../SYN_beside.txt", "locator": "line 1"})),
                                    model_id="m", apply=True, root=bt)
    assert done["interpretations"] == 0 and done["refused_by_reason"] == {"quote_not_found": 1}


def test_a_changed_source_file_fails_the_check(beamtime):
    bt, out = beamtime
    bundle = _load(out)
    src = next(s for s in bundle["sources"] if s["relative_path"] == "SYN_logbook.txt")
    assert src.get("content_sha256")
    (bt / "SYN_logbook.txt").write_text("\n".join(LOGBOOK) + "\nan added synthetic line\n", encoding="utf-8")
    [r] = RC.check_findings([_finding()], bt, sources=bundle["sources"])
    assert r["result"] == RC.FAIL and "changed since the import" in r["reason"]


def test_an_unknown_run_and_an_off_list_value_are_refused(beamtime):
    bt, out = beamtime
    f = _file(_finding(applies_to={"scope": "runs", "runs": ["SYN_no_such_run"]}), _finding(value="In_Situ"))
    done = M.annotate_from_readings(out, f, model_id="m", apply=True, root=bt)
    assert done["interpretations"] == 0
    assert done["refused_by_reason"] == {"not_allowed_value": 1, "unknown_run": 1}
    off = next(s for s in done["skipped"] if s["refused"] == "not_allowed_value")
    assert "'in_situ'" in off["reason"]


# --- check-readings ---------------------------------------------------------------------------------------------


def test_check_readings_prints_the_same_report_and_exits_1_on_a_failed_quote(beamtime, tmp_path, capsys):
    bt, out = beamtime
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(_file(_finding(), _note())))
    bad.write_text(json.dumps(_file(_finding(), _finding(quote="never written in the synthetic logbook"))))
    code, text = _run(["bundle", "check-readings", str(out), str(good), "--root", str(bt)], capsys)
    report = json.loads(text)
    assert code == 0 and (report["checked"], report["passed"], report["failed"]) == (2, 2, 0)
    assert report["root"] == bt.name and all(r["result"] == "pass" and r["at"] for r in report["results"])
    code, text = _run(["bundle", "check-readings", str(out), str(bad), "--root", str(bt)], capsys)
    report = json.loads(text)
    assert code == 1 and report["failed"] == 1 and report["results"][1]["finding"] == "finding-002"
    assert report["results"][1]["path"] == "SYN_logbook.txt" and "not found" in report["results"][1]["reason"]
    preview = M.annotate_from_readings(out, json.loads(bad.read_text()), model_id="m", apply=False, root=bt)
    assert {k: v for k, v in preview["quote_check"].items()} == report
    code, _ = _run(["bundle", "check-readings", str(out), str(good)], capsys)
    assert code == 2  # no folder to check against


# --- scan notes -------------------------------------------------------------------------------------------------


def test_scan_notes_round_trip_through_apply_list_show_and_the_accessor(beamtime, capsys):
    bt, out = beamtime
    notes = _file(
        _note(),
        _note(action="start_from", scans=[5], reason="start from #5", source={"path": "SYN_logbook.txt", "locator": "line 21"},
              quote="start from scan #5"),
        _note(action="flag", scans=[], reason="the potentiostat jumped", source={"path": "SYN_logbook.txt", "locator": "line 30"},
              quote="potentiostat jumped to 2.5 V during this file"),
    )
    preview = M.annotate_from_readings(out, notes, model_id="m", apply=False, root=bt)
    assert preview["scan_notes"] == 3 and preview["quote_check"]["failed"] == 0 and "scan_notes" not in _load(out)
    done = M.annotate_from_readings(out, notes, model_id="m", apply=True, root=bt)
    assert done["scan_notes"] == 3 and done["interpretations"] == 0
    bundle = _load(out)
    assert bundle["format_version"] == B.FORMAT_VERSION == "1.20.0" and B.validate_bundle(bundle) == []
    rid = next(r["run_id"] for r in bundle["runs"] if r["stem"] == "SYN_cell")
    got = SN.scan_notes_for_run(bundle, rid)
    assert [(n["action"], n["scans"]) for n in got] == [("exclude", [1]), ("start_from", [5]), ("flag", [])]
    assert all(n["source_path"] == "SYN_logbook.txt" and n["quote"] and n["model_id"] == "m" for n in got)
    assert SN.scan_notes_for_run(bundle, "run-999") == []
    code, text = _run(["bundle", "list", str(out), "scan-notes"], capsys)
    listed = json.loads(text)
    assert code == 0 and listed["total"] == 3 and listed["items"][0]["runs"] == ["SYN_cell"]
    assert listed["items"][1] == {**listed["items"][1], "action": "start_from", "scans": [5], "cited": "SYN_logbook.txt line 21"}
    code, text = _run(["bundle", "show", str(out), "run", rid], capsys)
    shown = json.loads(text)
    assert code == 0 and [n["scan_note_id"] for n in shown["scan_notes"]] == [n["scan_note_id"] for n in got]
    assert "never a decision" in shown["scan_notes_note"]
    again = M.annotate_from_readings(out, notes, model_id="m", apply=True, root=bt)
    assert again["scan_notes"] == 0 and again["scan_notes_already_recorded"] == 3
    assert len(_load(out)["scan_notes"]) == 3


@pytest.mark.parametrize(("over", "reason"), [
    ({"action": "start_from", "scans": [5, 6]}, "exactly ONE"),
    ({"action": "flag", "scans": [2]}, "names no scan numbers"),
    ({"action": "keep_only", "scans": []}, "non-empty list"),
    ({"action": "drop"}, "`action` must be one of"),
    ({"scans": [0]}, "whole scan numbers"),
    ({"scans": [True]}, "whole scan numbers"),
    ({"reason": " "}, "needs `reason`"),
    ({"strength": "likely"}, "needs `strength`"),
    ({"applies_to": {"scope": "experiment"}}, "scope must be `runs`"),
])
def test_a_malformed_scan_note_is_skipped_never_normalised(beamtime, over, reason):
    bt, out = beamtime
    done = M.annotate_from_readings(out, _file(_note(**over)), model_id="m", apply=True, root=bt)
    assert done["scan_notes"] == 0
    [s] = done["skipped"]
    assert reason in s["reason"]
    assert not _load(out).get("scan_notes")


def test_a_scan_note_naming_an_unknown_run_or_with_a_wrong_quote_is_refused(beamtime):
    bt, out = beamtime
    done = M.annotate_from_readings(out, _file(_note(applies_to={"scope": "runs", "runs": ["SYN_nothing"]}),
                                               _note(quote="discard the last scan")), model_id="m", apply=True, root=bt)
    assert done["scan_notes"] == 0 and done["refused_by_reason"] == {"quote_not_found": 1, "unknown_run": 1}


def test_an_older_bundle_without_scan_notes_still_validates_and_the_section_is_checked(beamtime):
    bt, out = beamtime
    bundle = _load(out)
    older = json.loads(json.dumps(bundle))
    older.pop("scan_notes", None)
    older["format_version"] = "1.11.0"
    assert B.validate_bundle(older) == []
    M.annotate_from_readings(out, _file(_note()), model_id="m", apply=True, root=bt)
    held = _load(out)
    bad = json.loads(json.dumps(held))
    bad["scan_notes"][0]["action"] = "flag"  # a flag names no scans: this one names [1]
    assert any("scan_notes" in e for e in B.validate_bundle(bad))
    bad = json.loads(json.dumps(held))
    bad["scan_notes"][0]["run_ids"] = ["run-999"]
    assert any("names a run not in this bundle" in e for e in B.validate_bundle(bad))


# --- review fixes: locators, aliases, short quotes, documents, the root, conflicting notes -----------------------


@pytest.mark.parametrize(("locator", "ok", "said"), [
    ("lines 1-100000", False, "too wide"),
    ("lines 1-21", False, "too wide"),
    ("lines 1-20", True, None),
    ("line10", True, None), ("Line #10", True, None), ("l. 10", True, None), ("L10", True, None),
    ("row 10", True, None), ("ll. 9-11", True, None), ("Lines 8 to 12", True, None),
    ("line30", False, "the quote is at line 10"),
    ("step 27 of the table", False, "not a line reference"),
    ("entry 3", False, "not a line reference"),
])
def test_a_line_locator_is_parsed_strictly_and_a_wide_or_unreadable_one_fails(beamtime, locator, ok, said):
    bt, _ = beamtime
    [r] = RC.check_findings([_finding(source={"path": "SYN_logbook.txt", "locator": locator})], bt)
    assert (r["result"] == RC.PASS) is ok, r
    if said:
        assert said in r["reason"]


def test_a_locator_without_any_number_still_searches_the_whole_file(beamtime):
    bt, _ = beamtime
    [r] = RC.check_findings([_finding(source={"path": "SYN_logbook.txt", "locator": "the sample section"})], bt)
    assert r["result"] == RC.PASS and "whole file" in r["at"]


@pytest.mark.parametrize("quote", ["in", "SYN_cell", "in situ"])
def test_a_quote_too_short_to_tell_apart_fails(beamtime, quote):
    bt, _ = beamtime
    [r] = RC.check_findings([_finding(quote=quote)], bt)
    assert r["result"] == RC.FAIL and "too short" in r["reason"]


@pytest.mark.parametrize(("line", "quote", "locator", "ok"), [
    ("Ar sat", "Ar sat", "line 5", True),                      # a whole short line, cited to it
    ("  Purge Ar.  ", "Purge Ar.", "lines 4-6", True),         # in a range of at most 3 lines
    ("Ar sat", "Ar sat", "lines 2-6", False),                  # a wider range
    ("Ar sat", "Ar sat", "line 7", False),                     # near, but not the line cited
    ("Ar sat", "Ar sat", "the gas remark", False),             # no line: a whole-file search
    ("the electrolyte held 0.1 M K and a synthetic buffer", "K", "line 5", False),  # a fragment of a long line
])
def test_a_short_quote_passes_only_as_the_whole_line_it_cites(tmp_path, line, quote, locator, ok):
    lines = [f"synthetic filler line {n}" for n in range(1, 11)]
    lines[4] = line
    (tmp_path / "SYN_short.txt").write_text("\n".join(lines) + "\n")
    [r] = RC.check_findings([_finding(source={"path": "SYN_short.txt", "locator": locator}, quote=quote)], tmp_path)
    assert (r["result"] == RC.PASS) is ok, r
    if not ok:
        assert "too short" in r["reason"]


def test_path_aliases_of_an_imported_source_still_get_its_hash_check_and_source_id(beamtime):
    bt, out = beamtime
    bundle = _load(out)
    src = next(s for s in bundle["sources"] if s["relative_path"] == "SYN_logbook.txt")
    aliases = ["./SYN_logbook.txt", "SYN_logbook.txt/", ".//SYN_logbook.txt"]
    if (bt / "syn_logbook.TXT").exists():  # a case-insensitive file system (macOS)
        aliases.append("syn_logbook.TXT")
    good = RC.check_findings([_finding(source={"path": a, "locator": "line 10"}) for a in aliases], bt, sources=bundle["sources"])
    assert all(r["result"] == RC.PASS and r["canonical_path"] == "SYN_logbook.txt" and not r.get("source_not_imported")
               for r in good)
    done = M.annotate_from_readings(out, _file(_note(source={"path": "./SYN_logbook.txt", "locator": "line 20"})),
                                    model_id="m", apply=True, root=bt)
    [n] = _load(out)["scan_notes"]
    assert done["scan_notes"] == 1 and n["source_id"] == src["source_id"] and n["source_path"] == "SYN_logbook.txt"
    (bt / "SYN_logbook.txt").write_text("\n".join(LOGBOOK) + "\nan added synthetic line\n", encoding="utf-8")
    bad = RC.check_findings([_finding(source={"path": a, "locator": "line 10"}) for a in aliases], bt, sources=bundle["sources"])
    assert all(r["result"] == RC.FAIL and "changed since the import" in r["reason"] for r in bad)


def test_a_file_the_import_did_not_read_is_marked_source_not_imported(beamtime):
    bt, out = beamtime
    (bt / "SYN_added_later.txt").write_text("SYN_cell was measured in situ, written after the import\n")
    [r] = RC.check_findings([_finding(source={"path": "SYN_added_later.txt", "locator": "line 1"})], bt,
                            sources=_load(out)["sources"])
    assert r["result"] == RC.PASS and r["source_not_imported"] is True
    report = RC.report([r], root_label=bt.name)
    assert report["results"][0]["source_not_imported"] is True and report["source_not_imported"] == 1


DOCX_SECTIONS = ("<w:p><w:r><w:t>Synthetic heading one</w:t></w:r></w:p>"
                 "<w:p><w:r><w:t>Synthetic paragraph two says nothing</w:t></w:r></w:p>"
                 "<w:p><w:r><w:t>Synthetic paragraph three says nothing</w:t></w:r></w:p>"
                 "<w:p><w:r><w:t>SYN_cell was kept under synthetic argon</w:t></w:r></w:p>"
                 "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>File 27</w:t></w:r></w:p></w:tc>"
                 "<w:tc><w:p><w:r><w:t>synthetic step table cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>")


@pytest.mark.parametrize(("locator", "ok", "said"), [
    ("paragraph 4", True, "paragraph 4"),
    ("para. 4", True, "paragraph 4"),
    ("paragraph 1", False, "paragraph 4"),
    ("the argon remark", True, "locator not checked"),
])
def test_a_docx_paragraph_locator_is_honoured(beamtime, locator, ok, said):
    bt, _ = beamtime
    make_docx(bt / "SYN_sections.docx", body_xml=DOCX_SECTIONS)
    [r] = RC.check_findings([_finding(source={"path": "SYN_sections.docx", "locator": locator},
                                      quote="kept under synthetic argon")], bt)
    assert (r["result"] == RC.PASS) is ok, r
    assert said in (r.get("at") or r.get("reason"))


def test_a_docx_table_and_an_xlsx_row_locator_are_honoured(beamtime):
    pytest.importorskip("openpyxl")
    from test_local_import_extract import make_xlsx

    bt, _ = beamtime
    make_docx(bt / "SYN_sections.docx", body_xml=DOCX_SECTIONS)
    make_xlsx(bt / "SYN_sheet.xlsx", rows=6)
    rows = RC.check_findings([
        _finding(source={"path": "SYN_sections.docx", "locator": "table 1"}, quote="synthetic step table cell"),
        _finding(source={"path": "SYN_sections.docx", "locator": "table 3"}, quote="synthetic step table cell"),
        _finding(source={"path": "SYN_sheet.xlsx", "locator": "sheet Data row 4"}, quote="r4c1 | r4c2 | r4c3"),
        _finding(source={"path": "SYN_sheet.xlsx", "locator": "row 5"}, quote="r4c1 | r4c2 | r4c3"),
    ], bt)
    assert [r["result"] for r in rows] == [RC.PASS, RC.FAIL, RC.PASS, RC.FAIL]
    assert "row 4" in rows[3]["reason"]


def test_root_must_be_the_folder_the_bundle_records_or_names(beamtime, tmp_path, capsys):
    bt, out = beamtime
    other = tmp_path / "SYN_other_folder"
    other.mkdir()
    (other / "SYN_logbook.txt").write_text("\n".join(LOGBOOK) + "\n")
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(_file(_finding())))
    code, _ = _run(["bundle", "check-readings", str(out), str(findings), "--root", str(other)], capsys)
    assert code == 2  # not the folder the bundle was imported from (its name differs)
    with pytest.raises(M.MutationRefused, match="not the folder"):
        M.annotate_from_readings(out, _file(_finding()), model_id="m", apply=True, root=other)
    rec = tmp_path / "recorded"
    assert _run(["import", str(bt), "--out", str(rec), "--record-local-root"], capsys)[0] == 0
    twin = tmp_path / "twin" / bt.name
    twin.mkdir(parents=True)
    (twin / "SYN_logbook.txt").write_text("\n".join(LOGBOOK) + "\n")
    code, _ = _run(["bundle", "check-readings", str(rec), str(findings), "--root", str(twin)], capsys)
    assert code == 2  # same name, but not the recorded folder
    code, _ = _run(["bundle", "check-readings", str(rec), str(findings)], capsys)
    assert code == 0  # the recorded root is used


def test_the_consent_reference_no_longer_says_to_cite_beside_folder_files():
    text = (Path(__file__).resolve().parents[3] / ".claude/skills/isaac-historical-import/reference/"
            "data-flow-and-consent.md").read_text(encoding="utf-8")
    assert "../<name>" not in text


def test_conflicting_scan_notes_for_one_run_are_flagged_in_the_accessor_show_and_list(beamtime, capsys):
    bt, out = beamtime
    notes = _file(
        _note(action="exclude", scans=[3]),
        _note(action="keep_only", scans=[3, 4], reason="keep 3 and 4"),
        _note(action="start_from", scans=[5], source={"path": "SYN_logbook.txt", "locator": "line 21"}, quote="start from scan #5"),
        _note(action="start_from", scans=[6], source={"path": "SYN_logbook.txt", "locator": "line 21"}, quote="start from scan #5"),
    )
    assert M.annotate_from_readings(out, notes, model_id="m", apply=True, root=bt)["scan_notes"] == 4
    bundle = _load(out)
    rid = next(r["run_id"] for r in bundle["runs"] if r["stem"] == "SYN_cell")
    got = SN.scan_notes_for_run(bundle, rid)
    ids = [n["scan_note_id"] for n in got]
    assert all(n["conflicts"] for n in got)
    assert any(c["with"] == ids[1] and "3" in c["why"] for c in got[0]["conflicts"])
    assert any(c["with"] == ids[3] for c in got[2]["conflicts"])
    pairs = SN.scan_note_conflicts(bundle, rid)
    assert {frozenset((c["notes"][0], c["notes"][1])) for c in pairs} >= {frozenset(ids[:2]), frozenset(ids[2:])}
    code, text = _run(["bundle", "show", str(out), "run", rid], capsys)
    assert code == 0 and json.loads(text)["scan_note_conflicts"]
    code, text = _run(["bundle", "list", str(out), "scan-notes"], capsys)
    assert code == 0 and all(i["conflicts"] for i in json.loads(text)["items"])


def test_a_scan_note_over_the_run_bound_is_refused_alone(beamtime, monkeypatch):
    bt, out = beamtime
    monkeypatch.setattr(SN, "MAX_RUNS_PER_NOTE", 1)
    two = [r["run_id"] for r in _load(out)["runs"]][:2]
    assert len(two) == 2
    done = M.annotate_from_readings(out, _file(_note(applies_to={"scope": "runs", "runs": two}), _note()),
                                    model_id="m", apply=True, root=bt)
    assert done["scan_notes"] == 1
    [s] = done["skipped"]
    assert s["finding"] == "finding-001" and "split it" in s["reason"]


def test_a_scan_note_on_a_run_outside_every_live_group_is_kept_and_marked(beamtime):
    bt, out = beamtime
    bundle = _load(out)
    rid = next(r["run_id"] for r in bundle["runs"] if r["stem"] == "SYN_cell")
    key = next(r["run_key"] for r in bundle["runs"] if r["run_id"] == rid)
    gid = next(g["group_id"] for g in bundle["record_groups"] if key in g["member_run_keys"])
    M.decide(out, target_ids=[gid], decision="reject", value=None, by="SYNTHETIC TEST", orcid=None)
    done = M.annotate_from_readings(out, _file(_note()), model_id="m", apply=True, root=bt)
    assert done["scan_notes"] == 1 and done["scan_notes_on_runs_not_live"] == 1
    [n] = SN.scan_notes_for_run(_load(out), rid)
    assert n["run_live"] is False
