"""c16c (M2): a file-name versus scan-header potential disagreement survives the template. Synthetic only.

On a real BL4-3 beamtime a run named ``…_m150mV_…`` had ``-300 mV vs RHE`` in its scan header. The template
import preview for it listed only the AI reading against the typed value, never the header; after ``--apply``,
``validate`` printed 0 warnings, so the disagreement of the two files was gone.

What these pin: a potential the scan header states is a FILE READING in "Replaces or contradicts a file reading"
(as the header's read candidate, or as the header's own words where no candidate holds it); a record that carries
a set-point while the name and the header disagree is warned at validate until a scientist rules on the header's
reading; a bundle with no header reading to rule on (built before those readings) is told to re-import.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import openpyxl
import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R

from test_local_import_reader_ssrl_xdc import make_scan

WHO = "SYNTHETIC TEST"
SETPOINT = "context.electrochemistry.potential_setpoint_V"
LABEL = "05_SYNmof_m150mV_021"


def _beamtime(root: Path) -> Path:
    src = root / "SYN_bt43"
    for i in (1, 2):
        make_scan(src / f"{LABEL}_A.{i:03d}", free_text=("100mM NaClO4 pH1.3", "-300mV vs RHE"))
    return src


def _imported(root: Path, monkeypatch=None, *, without_header_readings=False) -> Path:
    if without_header_readings:  # what a build before the header-comment rule made (no candidate holds the header)
        monkeypatch.setattr(B, "_xdc_comment_candidates", lambda *a, **k: [])
    out = root / "bundle"
    assert cli.main(["import", str(_beamtime(root)), "--out", str(out)]) == 0
    M.group(out)
    b = M.load(out)
    for g in b["record_groups"]:
        M.decide(out, target_ids=[g["group_id"]], decision="confirm", value=None, by=WHO, orcid=None)
    return out


def _run_id(out: Path) -> str:
    return next(r["run_id"] for r in M.load(out)["runs"] if r["label"] == LABEL)


def _typed(out: Path, tmp_path: Path, volts: float, capsys, *extra) -> dict:
    xlsx = tmp_path / "t.xlsx"
    if xlsx.exists():  # the same filled sheet, imported again (`--apply` after the preview)
        capsys.readouterr()
        assert cli.main(["bundle", "template", "import", str(out), str(xlsx), "--by", WHO, "--json", *extra]) == 0
        return json.loads(capsys.readouterr().out)
    assert cli.main(["bundle", "template", "export", str(out), "--out", str(xlsx)]) == 0
    wb = openpyxl.load_workbook(xlsx)
    row = next(int(v[1]) for v in wb["_isaac"].iter_rows(values_only=True) if v[0] == "File List" and v[2] == _run_id(out))
    header = next(r for r in range(1, 10) if any(c.value == "Potential (V)" for c in wb["File List"][r]))
    col = {c.value: c.column_letter for c in wb["File List"][header] if c.value}
    wb["File List"][f"{col['Potential (V)']}{row}"] = volts
    wb["File List"][f"{col['Potential Scale']}{row}"] = "RHE"
    wb.save(xlsx)
    capsys.readouterr()
    assert cli.main(["bundle", "template", "import", str(out), str(xlsx), "--by", WHO, "--json", *extra]) == 0
    return json.loads(capsys.readouterr().out)


def _warnings(out: Path, code: str) -> list[dict]:
    R.build_records(out)
    return [w for w in R.validate_records(out, full=True).get("warnings") or () if w["code"] == code]


def _readings(rep: dict) -> list[str]:
    return [line for x in rep["replaces_or_contradicts_a_file_reading"] if x["target_field_path"] == SETPOINT
            for line in x["readings"]]


def test_the_preview_names_the_scan_headers_reading_the_typed_value_replaces(tmp_path, capsys):
    out = _imported(tmp_path)
    lines = _readings(_typed(out, tmp_path, -0.15, capsys))
    assert any(line.startswith("replaces extracted -0.3, read from the scan header's '-300mV vs RHE'") for line in lines)


def test_without_a_header_reading_the_header_is_still_a_file_reading_and_validate_keeps_warning(tmp_path, capsys, monkeypatch):
    out = _imported(tmp_path, monkeypatch, without_header_readings=True)
    rep = _typed(out, tmp_path, -0.15, capsys)
    assert f"contradicts the scan header -300mV vs RHE at line:10 of {LABEL}_A.001: -0.3" in _readings(rep)
    _typed(out, tmp_path, -0.15, capsys, "--apply")
    [w] = _warnings(out, R.POTENTIAL_SOURCES_WARNING)
    assert f"the file name and the scan header of {_run_id(out)} state different potentials (file name m150mV; " in w["text"]
    assert "-300mV vs RHE at line:10" in w["text"] and "the record carries -0.15 V on RHE" in w["text"]
    assert "re-import the beamtime" in w["text"]


def test_validate_warns_while_no_one_has_ruled_on_the_headers_reading(tmp_path, monkeypatch):
    out = _imported(tmp_path)
    b = M.load(out)
    rid = _run_id(out)
    group = next(g for g in b["record_groups"] if g["member_run_ids"] == [rid])
    carried = {SETPOINT: {"value": -0.15, "status": "scientist_confirmed", "evidence": []},
               "context.electrochemistry.potential_scale": {"value": "RHE", "status": "scientist_confirmed", "evidence": []}}
    [w] = R._potential_sources_warnings(b, group, {rid}, carried)
    cand = next(c for c in b["candidates"] if c["run_id"] == rid and B.is_header_comment_candidate(c)
                and c["target_field_path"] == SETPOINT)
    assert w["targets"] == [cand["candidate_id"]] and "no one has ruled on the scan header's reading yet" in w["text"]
    assert w["command"].startswith(f"isaac bundle decide <bundle_dir> --target {cand['candidate_id']} --decision confirm")
    assert R.written_without(w).startswith("Written with a potential its files disagree about: ")
    M.decide(out, target_ids=[cand["candidate_id"]], decision="correct", value=-0.15, by=WHO, orcid=None)
    assert R._potential_sources_warnings(M.load(out), group, {rid}, carried) == []  # ruled on: resolved


def test_a_record_without_a_setpoint_gets_the_stated_potential_warning_instead(tmp_path):
    out = _imported(tmp_path)
    assert not _warnings(out, R.POTENTIAL_SOURCES_WARNING)
    [w] = _warnings(out, R.STATED_POTENTIAL_WARNING)
    assert "file name m150mV, scan header -300mV vs RHE" in w["text"]
