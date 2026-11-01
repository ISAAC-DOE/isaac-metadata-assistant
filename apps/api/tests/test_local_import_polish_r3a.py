"""r3a: what a real-data run on an SSRL BL4-3 Ti K-edge beamtime found. Synthetic only (invented lines, SYN names).

BL4-3 scan headers write a sample, an electrolyte and a potential glued into one comment line (``Sample A in 1M KOH
0Vrhe``), so every comment line gives the whitelist rule no value. What these pin:

* H1: ``bundle excerpt`` of a candidate shows the line its ``line:N`` locator names, and says so when it cannot.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

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

