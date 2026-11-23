"""The clock zone from a SPEC header's #E / #D pair is SUGGESTED for the clock-zone question, never applied (bundle
1.16.0; audit of 18 Nov 2026, rule 4). SYNTHETIC files only.

A SPEC header writes the file's creation instant twice: ``#E <unix epoch>`` (UTC) and ``#D <local wall time>`` on the
next line, so their difference is the offset of the clock that wrote it. What these pin
(``bundle.CLOCK_OFFSET_RULE_ID``):

* the pairs are read with their places, the offset rounded to 15 minutes;
* where every pair fits the zone of the facility the SPEC headers name (daylight saving included), that zone is the
  question's ``suggested_value``, the pairs are its hints and the text gives the one command that confirms it;
* nothing is applied: the start times wait for the scientist's answer as before, and the question id is unchanged;
* pairs that fit no such zone suggest nothing and say why.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_quick_merges import _spec_run  # noqa: E402
from test_local_import_reader_ssrl_xdc import make_scan  # noqa: E402

UTC_D = "#D Mon Sep  9 01:46:40 2001"       # the fixture's #D: #E 1000000000 read as UTC
LA_D = "#D Sat Sep  8 18:46:40 2001"        # the same instant on a clock set to America/Los_Angeles (PDT)


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


def _beamtime(root: Path, local_d: str) -> Path:
    bt = root / "SYN_BL00_2100-28_Clock"
    _spec_run(bt, "SYN_cat_spec")
    for p in (bt / "SYN_cat_spec", bt / "SYN_cat_spec_dir" / "SYN_cat_spec"):
        p.write_text(p.read_text().replace(UTC_D, local_d, 1))
    make_scan(bt / "xdc" / "SYN_xdc_run_A.001", timestamp="Mon Sep 10 10:00:00 2001")
    return bt


def _grouped(tmp_path: Path, local_d: str) -> tuple[Path, dict]:
    out = tmp_path / "out"
    assert cli.main(["import", str(_beamtime(tmp_path / "src", local_d)), "--out", str(out)]) == 0
    M.group(out)
    b = M.load(out)
    assert B.validate_bundle(b) == []
    return out, b


def _clock_question(b: dict) -> dict:
    [q] = [q for q in Q.consolidate(b)["questions"] if q["kind"] == "clock_time_zone"]
    return q


def test_the_pair_is_read_with_its_places(tmp_path, capsys):
    _, b = _grouped(tmp_path, LA_D)
    [pair] = B.spec_clock_pairs(b)
    assert pair["epoch_literal"] == "#E 1000000000" and pair["local_literal"] == LA_D
    assert pair["epoch_locator"] == "line 2 header #E" and pair["local_locator"] == "line 3 header #D"
    assert pair["offset_minutes"] == -7 * 60 and pair["utc"] == "2001-09-09T01:46:40+00:00"


def test_another_instruments_clock_is_shown_never_suggested(tmp_path, capsys):
    """Review of PR 346, I4: the pairs are the SPEC computer's clock; the start times the question waits on are an
    SSRL XDC run's, written by another computer. The pairs are a labelled hint; no zone is suggested from them."""
    out, b = _grouped(tmp_path, LA_D)
    q = _clock_question(b)
    assert q["question_id"] == Q.CLOCK_QUESTION_ID  # the id stands
    assert q["suggested_value"] is None and "--value America" not in q["text"]
    [hint] = [h for h in q["hints"] if h["kind"] == "clock_offset_pair"]
    assert hint["epoch_literal"] == "#E 1000000000" and hint["local_literal"] == LA_D
    assert "SPEC computer's clock" in hint["note"] and "SPEC computer's clock" in q["text"] and "-7 h" in q["text"]
    assert B.clock_zone_decision(b) is None  # nothing applied
    assert all(c["value"] is None for c in b["candidates"] if B.is_local_clock_start(c))


def test_the_facility_zone_the_offsets_fit_is_suggested_for_the_same_clock(tmp_path, capsys):
    _, b = _grouped(tmp_path, LA_D)
    spec = [c for c in b["candidates"] if c["statement_key"] == "acquisition_epoch"]  # the pairs' own system
    got = B.clock_zone_suggestion(b, spec)
    assert got["value"] == "America/Los_Angeles" and "Suggested, not applied" in got["reason"] and "SSRL" in got["reason"]
    waiting = [c for c in b["candidates"] if B.is_local_clock_start(c)]
    assert B.clock_zone_suggestion(b, waiting)["value"] is None


def test_pairs_that_fit_no_facility_zone_suggest_nothing(tmp_path, capsys):
    _, b = _grouped(tmp_path, UTC_D)  # the clock ran on UTC: not the facility's zone
    spec = [c for c in b["candidates"] if c["statement_key"] == "acquisition_epoch"]
    got = B.clock_zone_suggestion(b, spec)
    assert got["value"] is None and "+0 h" in got["reason"] and "does not give" in got["reason"]


def test_without_a_pair_the_question_is_as_before(tmp_path, capsys):
    bt = tmp_path / "src" / "SYN_BL43_2100-29_Clock"
    make_scan(bt / "SYN_xdc_run_A.001")
    out = tmp_path / "out"
    assert cli.main(["import", str(bt), "--out", str(out)]) == 0
    M.group(out)
    q = _clock_question(M.load(out))
    assert q["suggested_value"] is None and "suggestion" not in q
    assert not [h for h in q["hints"] if h["kind"] == "clock_offset_pair"]
