"""c16d (M3): a record written without its start time because the clock zone was deferred says so. Synthetic only.

On a real BL4-3 beamtime the scientist deferred the instrument clock's time zone ("I don't know"), so no start time
went into any record — and ``validate``, ``export``, the evidence files and ``upload --dry-run`` said nothing about
it; export said "Every confirmed group was exported".

What these pin: while the clock answer is ``defer``, every record whose runs' scan headers write a local start time
carries the warning "start time left out: instrument clock zone deferred (question <id>)" at validate and export;
its evidence sidecar keeps the same line under ``notes`` (written by local_import, after the truth plane's
``build_sidecar``); the upload dry run says it per record and once in its statement. No defer, no warning; a zone
answer ends it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_reader_ssrl_xdc import make_scan
from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _cand, _decide_everything, _portal, bdir, fake_upstream, pristine)

WHO = "SYNTHETIC TEST"
LINE = f"start time left out: instrument clock zone deferred (question {Q.CLOCK_QUESTION_ID})"
START = "timestamps.acquired_start_utc"


def _defer_clock(out: Path) -> None:
    M.decide_question(out, question_id=Q.CLOCK_QUESTION_ID, decision="defer", value=None, by=WHO, orcid=None)


def _start_warnings(out: Path) -> list[dict]:
    R.build_records(out)
    return [w for w in R.validate_records(out, full=True).get("warnings") or () if w["code"] == R.START_TIME_WARNING]


@pytest.fixture()
def xdc(tmp_path) -> Path:
    src = tmp_path / "src" / "SYN_bt43"
    for name in ("01_SYNelS_015", "03_SYNmof_dry_017"):
        make_scan(src / f"{name}_A.001")
    out = tmp_path / "bundle"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    M.group(out)
    for g in M.load(out)["record_groups"]:
        M.decide(out, target_ids=[g["group_id"]], decision="confirm", value=None, by=WHO, orcid=None)
    return out


def test_the_clock_question_id_is_the_one_the_question_is_asked_under(xdc):
    [q] = [q for q in Q.consolidate(M.load(xdc))["questions"] if q["kind"] == "clock_time_zone"]
    assert q["question_id"] == Q.CLOCK_QUESTION_ID


def test_validate_says_the_start_time_is_left_out_while_the_zone_is_deferred(xdc):
    assert not _start_warnings(xdc)  # not deferred: the clock question is asked (optional), no warning
    _defer_clock(xdc)
    got = _start_warnings(xdc)
    assert len(got) == 2 and {w["text"] for w in got} == {LINE}
    assert all("set_clock_time_zone" in w["command"] for w in got)
    M.decide(xdc, target_ids=["experiment"], decision="set_clock_time_zone", value="UTC", by=WHO, orcid=None)
    assert not _start_warnings(xdc)  # a zone answers it


def _exportable_without_start(bdir: Path, monkeypatch) -> None:
    """The records fixture's exportable group, its start time rejected, its run's start time read as an instrument
    clock time (``records.local_clock_runs``, as for an SSRL XDC run) and the clock zone deferred (that fixture has
    no XDC run, so no clock question: the deferral is stood in for; the XDC test above records a real one)."""
    _decide_everything(bdir)
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_cand(b, START, "run-001")["candidate_id"]], decision="reject", value=None, **BY)
    monkeypatch.setattr(R, "local_clock_runs", lambda bundle: {"run-001"})
    monkeypatch.setattr(M, "clock_zone_deferral", lambda bundle: {"by": WHO, "decided_utc": None, "decision_id": None})
    R.build_records(bdir)


def test_export_the_sidecar_and_the_dry_run_say_it(bdir, tmp_path, monkeypatch, capsys):
    _exportable_without_start(bdir, monkeypatch)
    out = tmp_path / "records"
    result = R.export_records(bdir, out, run_portal=_portal("publish"))
    [row] = result["exported"]
    assert f"Written without the start time: {LINE}" in row["warnings"]
    assert "written with a warning that still applies" in result["outcome"]
    sidecar = json.loads((out / f"{row['record_id']}.evidence.json").read_text())
    assert sidecar["notes"] == [LINE]
    assert START not in json.loads((out / f"{row['record_id']}.json").read_text()).get("timestamps", {})
    capsys.readouterr()
    assert cli.main(["bundle", "upload", str(out), "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    [rec] = plan["records"]
    assert rec["notes"] == [LINE] and f"{LINE} (1 record(s); records[].notes)." in plan["statement"]


def test_without_a_defer_the_sidecar_has_no_notes(bdir, tmp_path):
    _decide_everything(bdir)
    R.build_records(bdir)
    out = tmp_path / "records"
    [row] = R.export_records(bdir, out, run_portal=_portal("publish"))["exported"]
    assert "notes" not in json.loads((out / f"{row['record_id']}.evidence.json").read_text())
    assert not [w for w in row.get("warnings") or () if "start time" in w]
