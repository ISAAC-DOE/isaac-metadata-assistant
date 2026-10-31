"""LOCAL-P: the full CLI path for the counter-position question, on a SYNTHETIC folder.

`isaac import` -> `isaac bundle group` -> `isaac bundle questions` shows the counter
question -> `isaac bundle decide --target experiment --decision set_counter_positions
--positions 2 --by "SYNTHETIC TEST"` -> `isaac bundle group --regroup` -> the merge
candidate became one proposed group. Every file is invented (built from the committed
synthetic fixture corpus, names SYN*/Q4*).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import cli

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "bl15" / "semantics" / "multi_operator_corpus"
SRC_STEM = "01_01_ZZ1_acid_after500Cycling_filter10_100mV"
STEMS = ["Q4_02_SYNcat_pH2_400mV", "Q4_03_SYNcat_pH2_400mV"]


def _folder(root: Path) -> Path:
    src = root / "src"
    src.mkdir()
    acq = (FIXTURE / SRC_STEM).read_text().replace("01_01_ZZ1_acid_beforeCycling_filter10_100mV", SRC_STEM)
    scan = (FIXTURE / f"{SRC_STEM}_dir" / f"{SRC_STEM}_001.dat").read_text()
    (src / "Zz_XAS.mac").write_text((FIXTURE / "Zz_XAS.mac").read_text())
    for stem in STEMS:
        (src / stem).write_text(acq.replace(SRC_STEM, stem))
        d = src / f"{stem}_dir"
        d.mkdir()
        for i in (1, 2):  # scan-file indices the engine misreads as the sample number
            (d / f"{stem}_{i:03d}.txt").write_text(scan.replace(SRC_STEM, stem))
    return src


def _run(argv, capsys):
    rc = cli.main(argv)
    out = capsys.readouterr().out
    return rc, out


def _bundle(b: Path) -> dict:
    return json.loads((b / "bundle.json").read_text())


def test_counter_question_decide_and_regroup_through_the_cli(tmp_path, capsys):
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    before = _bundle(b)
    assert [len(g["member_run_keys"]) for g in before["record_groups"]] == [1, 1]
    (mc,) = before["merge_candidates"]
    assert [r["code"] for r in mc["reasons"]] == ["numeric_name_token_differs"]
    (gq,) = before["grouping_questions"]
    assert gq["kind"] == "naming_counter_positions" and gq["positions"] == [2]

    rc, out = _run(["bundle", "questions", str(b), "--scope", "experiment", "--limit", "200"], capsys)
    assert rc == 0
    asked = [q for q in json.loads(out)["questions"] if q["kind"] == "naming_counter_positions"]
    assert len(asked) == 1 and asked[0]["answered"] is False and "2nd" in asked[0]["text"]

    rc, _ = _run(["bundle", "decide", str(b), "--target", "experiment", "--decision", "set_counter_positions", "--positions", "2", "--by", "SYNTHETIC TEST"], capsys)
    assert rc == 0
    assert _run(["bundle", "group", str(b), "--regroup"], capsys)[0] == 0
    after = _bundle(b)
    (g,) = after["record_groups"]
    assert len(g["member_run_keys"]) == 2 and g["status"] == "proposed"
    assert g["counter_positions_basis"] == after["scientist_decisions"][-1]["decision_id"]
    assert after["merge_candidates"] == [] and after["grouping_questions"] == []
    assert _run(["bundle", "check", str(b)], capsys)[0] == 0


def test_electrodes_numbered_first_stay_apart_through_the_real_importer(tmp_path, capsys, monkeypatch):
    """Independent review of the leading-number fix: the importer sets `legacy_number` FROM the
    leading token, so a rule trusting it re-merged every electrode on real data while every
    synthetic test (legacy unset) passed. This goes through `isaac import` itself."""
    if not FIXTURE.is_dir():
        pytest.skip("synthetic fixture corpus not present")
    monkeypatch.setattr(__import__(__name__), "STEMS", ["02_01_SYNcat_pH2_400mV", "05_01_SYNcat_pH2_400mV"])
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert _run(["import", str(src), "--out", str(b)], capsys)[0] == 0
    assert _run(["bundle", "group", str(b)], capsys)[0] == 0
    bundle = _bundle(b)
    assert sorted(r.get("legacy_number") for r in bundle["runs"] if r.get("scan_count")) == [2, 5]  # the real shape
    assert [len(g["member_run_keys"]) for g in bundle["record_groups"]] == [1, 1]
    assert len(bundle["merge_candidates"]) == 1
    (gq,) = bundle["grouping_questions"]
    assert gq["kind"] == "naming_counter_positions" and 1 in gq["positions"]
