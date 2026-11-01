"""r3a: what a real-data run on an SSRL BL4-3 Ti K-edge beamtime found. Synthetic only (invented lines, SYN names).

BL4-3 scan headers write a sample, an electrolyte and a potential glued into one comment line (``Sample A in 1M KOH
0Vrhe``), so every comment line gives the whitelist rule no value. What these pin:

* H1: ``bundle excerpt`` of a candidate shows the line its ``line:N`` locator names, and says so when it cannot;
* H2: a potential a value-less header line MENTIONS (``0Vrhe``) is compared, never offered: against the file name's
  (``m600mV``) and the typed value, warned at validate until a scientist rules, and never said to agree.
"""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import import template as T

from test_local_import_reader_ssrl_xdc import make_scan

WHO = "SYNTHETIC TEST"
SETPOINT = "context.electrochemistry.potential_setpoint_V"


def _import(src: Path, out: Path) -> Path:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    M.group(out)
    for g in M.load(out)["record_groups"]:
        M.decide(out, target_ids=[g["group_id"]], decision="confirm", value=None, by=WHO, orcid=None)
    return out


def _header_cands(b: dict, path: str) -> list[dict]:
    return [c for c in b["candidates"] if B.is_header_comment_candidate(c) and c["target_field_path"] == path]


# --- H1: excerpt shows the line a candidate's locator names ------------------------------------------------------


@pytest.fixture(scope="module")
def excerpted(tmp_path_factory):
    root = tmp_path_factory.mktemp("r3a-h1")
    src = root / "SYN_bt43"
    make_scan(src / "01_SYNti_m600mV_096_A.001", free_text=("SYN gain 1e8", "Sample A in 1M KOH 0Vrhe", "SYN note"))
    return src, _import(src, root / "bundle")


def test_excerpt_of_a_header_comment_candidate_shows_its_line(excerpted):
    src, out = excerpted
    b = M.load(out)
    [cand] = _header_cands(b, SETPOINT)
    assert cand["evidence"][0]["locator"] == "line:10"
    got = M.excerpt(b, cand["candidate_id"], source=str(src))
    [hit] = got["excerpts"]
    assert hit["locator"] == "line:10" and hit["lines"] == [7, 13] and "note" not in hit
    assert "   10: Sample A in 1M KOH 0Vrhe" in hit["text"].splitlines()


@pytest.mark.parametrize("locator,first,last", [("line:10", 10, None), ("line 3", 3, None),
                                                ("command 2 (lines 4-9)", 4, "9")])
def test_every_line_locator_the_readers_write_is_read(locator, first, last):
    m = M._LINE_RE.search(locator)
    assert m is not None and int(m.group("first")) == first and m.group("last") == last


def test_a_locator_that_names_no_file_line_is_not_read_as_one():
    assert M._LINE_RE.search("history line 4") is None  # an Igor history line is not a line of the file
    assert M._LINE_RE.search("record 3 (wave note)") is None


def test_a_line_past_the_end_of_the_file_is_refused_not_replaced_by_the_first_lines(excerpted, monkeypatch):
    src, out = excerpted
    b = M.load(out)
    [cand] = _header_cands(b, SETPOINT)
    monkeypatch.setattr(M, "_locators", lambda c: [{"source_id": e["source_id"], "relative_path": e["relative_path"],
                                                    "locator": "line:900"} for e in c["evidence"]][:1])
    [hit] = M.excerpt(b, cand["candidate_id"], source=str(src))["excerpts"]
    assert "lines" not in hit and hit["refused"].startswith("the locator names line 900 and the file has ")


def test_a_locator_with_no_line_says_the_first_lines_are_shown(excerpted, monkeypatch):
    src, out = excerpted
    b = M.load(out)
    [cand] = _header_cands(b, SETPOINT)
    monkeypatch.setattr(M, "_locators", lambda c: [{"source_id": e["source_id"], "relative_path": e["relative_path"],
                                                    "locator": "record 3"} for e in c["evidence"]][:1])
    [hit] = M.excerpt(b, cand["candidate_id"], source=str(src))["excerpts"]
    assert hit["lines"] == [1, 7] and hit["note"] == "the locator (record 3) names no line of the file: its first lines are shown"


# --- H2: a potential a value-less header line mentions is compared, never offered --------------------------------


WRONG, SAME, TWO = "01_SYNti_m600mV_096", "02_SYNti_m600mV_097", "03_SYNti_1p6V_098"
LINES = {WRONG: "Sample A in 1M KOH 0Vrhe", SAME: "Sample A in 1M KOH -0.6Vrhe", TWO: "SYN 0.5 V then 1.6 V vs RHE"}


@pytest.fixture()
def glued(tmp_path):
    src = tmp_path / "SYN_bt43"
    for label, line in LINES.items():
        for i in (1, 2):
            make_scan(src / f"{label}_A.{i:03d}", free_text=("SYN gain 1e8", line))
    return _import(src, tmp_path / "bundle")


def _rid(b: dict, label: str) -> str:
    return next(r["run_id"] for r in b["runs"] if r["label"] == label)


def _group(b: dict, rid: str) -> dict:
    return next(g for g in b["record_groups"] if g["member_run_ids"] == [rid])


CARRIED = {SETPOINT: {"value": -0.6, "status": "scientist_confirmed", "evidence": []},
           "context.electrochemistry.potential_scale": {"value": "RHE", "status": "scientist_confirmed", "evidence": []}}


def test_every_potential_a_line_mentions_is_kept_and_none_is_picked():
    assert [(m["literal"], m["volts"], m["scale"]) for m in Q.header_potential_mentions("Sample A in 1M KOH 0Vrhe")] == [
        ("0Vrhe", 0.0, "RHE")]
    assert [m["literal"] for m in Q.header_potential_mentions("SYN 0.5 V then 1.6 V vs RHE")] == ["0.5 V", "1.6 V vs RHE"]
    assert [m["volts"] for m in Q.header_potential_mentions("in 1M KOH 0.5Vrhe; -300 mV vs Ag/AgCl")] == [0.5, -0.3]
    for none in ("PMT 0.8 kV", "5 µV noise", "5 Volts", "1M KOH", "V K-edge"):
        assert Q.header_potential_mentions(none) == [], none


def test_a_mention_is_never_offered_as_a_value(glued):
    b = M.load(glued)
    for label in LINES:
        run = next(r for r in b["runs"] if r["label"] == label)
        assert T.header_potential_readings(b, run) == []
    assert all(c["value"] is None for c in _header_cands(b, SETPOINT))


def test_a_file_name_and_a_header_mention_that_differ_are_warned_at_validate(glued):
    b = M.load(glued)
    rid = _rid(b, WRONG)
    [w] = R._potential_sources_warnings(b, _group(b, rid), {rid}, CARRIED)
    assert w["code"] == R.POTENTIAL_SOURCES_WARNING
    assert w["text"].startswith(f"the scan header of {rid} writes '0Vrhe' (its line 'Sample A in 1M KOH 0Vrhe' at line:10 "
                                f"of {WRONG}_A.001, line:10 of {WRONG}_A.002), the file name writes m600mV, and the record "
                                "carries -0.6 V on RHE: '0Vrhe' differs from the file name's and the record's")
    assert "state a potential" not in w["text"] and "--decision correct --value <volts> --json" in w["command"]


def test_matching_mentions_are_not_warned(glued):
    b = M.load(glued)
    rid = _rid(b, SAME)
    assert R._potential_sources_warnings(b, _group(b, rid), {rid}, CARRIED) == []


def test_each_of_several_mentions_is_compared(glued):
    b = M.load(glued)
    rid = _rid(b, TWO)
    carried = {**CARRIED, SETPOINT: {**CARRIED[SETPOINT], "value": 1.6}}
    [w] = R._potential_sources_warnings(b, _group(b, rid), {rid}, carried)
    assert "writes '0.5 V' and '1.6 V vs RHE' (its line" in w["text"]
    assert "'0.5 V' differs from the file name's and the record's" in w["text"] and "'1.6 V vs RHE' differs" not in w["text"]


def test_a_ruling_on_the_header_line_clears_the_warning(glued):
    b = M.load(glued)
    rid = _rid(b, WRONG)
    [cand] = [c for c in _header_cands(b, SETPOINT) if c["run_id"] == rid]
    M.decide(glued, target_ids=[cand["candidate_id"]], decision="correct", value=-0.6, by=WHO, orcid=None)
    assert R._potential_sources_warnings(M.load(glued), _group(b, rid), {rid}, CARRIED) == []


def test_build_records_never_says_a_differing_file_name_and_header_state_one_potential(glued):
    R.build_records(glued)
    got = {w["group_id"]: w["text"] for w in R.validate_records(glued, full=False).get("warnings") or ()
           if w["code"] == R.STATED_POTENTIAL_WARNING}
    b = M.load(glued)
    wrong, same = got[_group(b, _rid(b, WRONG))["group_id"]], got[_group(b, _rid(b, SAME))["group_id"]]
    assert wrong.startswith("the file names and scan headers write different potentials (m600mV in ")
    assert f"{_rid(b, WRONG)}: the scan header writes '0Vrhe', the file name writes m600mV" in wrong
    assert "state a potential" not in wrong
    assert same.startswith("the file names and scan headers state a potential (m600mV in ")
    assert "different" not in same


def _typed(out: Path, tmp_path: Path, label: str, volts: float, capsys) -> dict:
    xlsx = tmp_path / "t.xlsx"
    assert cli.main(["bundle", "template", "export", str(out), "--out", str(xlsx)]) == 0
    wb = openpyxl.load_workbook(xlsx)
    rid = _rid(M.load(out), label)
    row = next(int(v[1]) for v in wb["_isaac"].iter_rows(values_only=True) if v[0] == "File List" and v[2] == rid)
    header = next(r for r in range(1, 10) if any(c.value == "Potential (V)" for c in wb["File List"][r]))
    col = {c.value: c.column_letter for c in wb["File List"][header] if c.value}
    wb["File List"][f"{col['Potential (V)']}{row}"] = volts
    wb["File List"][f"{col['Potential Scale']}{row}"] = "RHE"
    wb.save(xlsx)
    capsys.readouterr()
    assert cli.main(["bundle", "template", "import", str(out), str(xlsx), "--by", WHO, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_the_template_preview_names_a_header_mention_the_typed_value_contradicts(glued, tmp_path, capsys):
    rep = _typed(glued, tmp_path, WRONG, -0.6, capsys)
    lines = [line for x in rep["replaces_or_contradicts_a_file_reading"] if x["target_field_path"] == SETPOINT
             for line in x["readings"]]
    assert (f"contradicts the scan header, which writes '0Vrhe' in its line 'Sample A in 1M KOH 0Vrhe' at line:10 of "
            f"{WRONG}_A.001 (a mention: no value is read from it)") in lines


def test_the_template_preview_lists_no_mention_that_agrees(glued, tmp_path, capsys):
    rep = _typed(glued, tmp_path, SAME, -0.6, capsys)
    assert not [x for x in rep["replaces_or_contradicts_a_file_reading"] if x["target_field_path"] == SETPOINT]
