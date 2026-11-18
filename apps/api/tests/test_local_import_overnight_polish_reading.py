"""Overnight polish (18 Nov 2026), the reading pass's quote check and the ``people`` context rule. SYNTHETIC files and
invented names only (``SYN_`` files, the surname ``Smith``).

1. **An element edge is not a line.** ``L3`` in ``Ir L3-edge note, line 10`` is never read as line 3: only the
   ``line``, ``l.`` and ``row`` forms are line references.
2. **A short ``#C`` line cited by its scan** (``scan 2 #C``) passes when that scan's ``#C`` line is the quote.
3. **The troubleshooting reference** no longer says to quote a text copy: a page with no text layer cannot be
   checked, and the reader says what it holds instead.
4. **``bundle list scan-notes``** compares a row's note with the other notes on its runs, never every pair.
5. **A ``--root`` with no recorded root** must have the imported folder's name AND hold at least one imported source
   with the bytes the import read.
6. **The people rule** finds ``Samples prepared by Smith`` and flags no line that names no one (``Hydroxyl group``,
   ``Methyl group``, ``Beamline Sent``, ``Ir's samples``).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from isaac_api.local_import import question_context as QC
from isaac_api.local_import import reading_check as RC
from isaac_api.local_import import scan_notes as SN

from test_local_import_reading_check import LOGBOOK, _file, _finding, _run, beamtime  # noqa: F401

REPO = Path(__file__).resolve().parents[3]


# --- 1. an element edge is not a line ----------------------------------------------------------------------------


@pytest.mark.parametrize(("locator", "span"), [
    ("Ir L3-edge note, line 151", (151, 151)),
    ("L3 edge", None), ("L10", None), ("K-edge, L2", None),
    ("l. 10", (10, 10)), ("ll. 9-11", (9, 11)), ("row 4", (4, 4)), ("line12", (12, 12)), ("Lines 8 to 12", (8, 12)),
])
def test_an_element_edge_token_is_never_a_line_reference(locator, span):
    assert RC.line_locator(locator) == span


def test_a_quote_cited_beside_an_edge_token_is_checked_at_its_line(beamtime):
    bt, _ = beamtime
    [r] = RC.check_findings([_finding(source={"path": "SYN_logbook.txt", "locator": "Zz L3-edge note, line 10"})], bt)
    assert r["result"] == RC.PASS and r["at"].startswith("line 10"), r


# --- 2. a short #C line cited by its scan ------------------------------------------------------------------------


def _spec(tmp_path: Path) -> Path:
    (tmp_path / "SYN_spec.dat").write_text("#F SYN\n#S 1 synthetic\n#C SYN first\n1 2\n"
                                           "#S 2 synthetic\n#C Ar sat\n3 4\n", encoding="utf-8")
    return tmp_path


def test_a_short_comment_line_cited_by_its_scan_passes_when_that_scans_line_is_the_quote(tmp_path):
    root = _spec(tmp_path)
    ok, other_scan, fragment = RC.check_findings([
        _finding(source={"path": "SYN_spec.dat", "locator": "scan 2 #C"}, quote="Ar sat"),
        _finding(source={"path": "SYN_spec.dat", "locator": "scan 1 #C"}, quote="Ar sat"),
        _finding(source={"path": "SYN_spec.dat", "locator": "scan 2 #C"}, quote="Ar"),
    ], root)
    assert ok["result"] == RC.PASS and "scan 2" in ok["at"], ok
    assert other_scan["result"] == RC.FAIL
    assert fragment["result"] == RC.FAIL and "too short" in fragment["reason"]


# --- 3. the troubleshooting reference ----------------------------------------------------------------------------


def test_no_surface_says_to_quote_a_text_copy():
    text = (REPO / ".claude/skills/isaac-historical-import/reference/troubleshooting.md").read_text(encoding="utf-8")
    assert "text copy" not in text
    assert "text copy" not in RC.NO_TEXT_LAYER


# --- 4. list_row is not quadratic per row -------------------------------------------------------------------------


def test_a_scan_note_row_compares_its_note_with_the_others_only(monkeypatch):
    notes = [{"scan_note_id": f"sn-{i:03d}", "run_ids": ["run-001"], "action": "keep_only", "scans": [i]}
             for i in range(40)]
    bundle = {"runs": [{"run_id": "run-001", "stem": "SYN_run"}], "record_groups": [], "scan_notes": notes}
    calls = []
    real = SN._conflict
    monkeypatch.setattr(SN, "_conflict", lambda a, b: calls.append(1) or real(a, b))
    row = SN.list_row(bundle, notes[0])
    assert row["conflicts"] == [n["scan_note_id"] for n in notes[1:]]
    assert len(calls) <= len(notes) - 1, len(calls)


# --- 5. --root with no recorded root: the name AND the bytes ------------------------------------------------------


def test_a_root_with_the_imported_name_but_other_bytes_is_refused(beamtime, tmp_path, capsys):
    bt, out = beamtime
    findings = tmp_path / "f.json"
    findings.write_text(json.dumps(_file(_finding())))
    look_alike = tmp_path / "elsewhere" / bt.name
    look_alike.mkdir(parents=True)
    (look_alike / "SYN_logbook.txt").write_text("\n".join(LOGBOOK) + "\nSYN a line the import never read\n")
    code, _ = _run(["bundle", "check-readings", str(out), str(findings), "--root", str(look_alike)], capsys)
    err = capsys.readouterr().err
    assert code == 2, err
    code, text = _run(["bundle", "check-readings", str(out), str(findings), "--root", str(bt)], capsys)
    assert code == 0 and json.loads(text)["passed"] == 1


# --- 6. the people rule ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("line", ["Samples prepared by Smith", "the Smith group", "Smith's samples", "Smith has sent",
                                  "Authors: SYN"])
def test_a_line_naming_someone_is_found(line):
    assert QC._names_people(line) is not None


@pytest.mark.parametrize("line", ["Hydroxyl group", "Methyl group", "Beamline Sent", "Ir's samples",
                                  "the methyl group was reduced"])
def test_a_line_naming_no_one_is_not_flagged(line):
    assert QC._names_people(line) is None


def test_the_people_rule_has_no_code_after_its_return():
    assert "return True" not in inspect.getsource(QC._names_people)
