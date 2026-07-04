"""CLI behavior: export gating, audit, required-fields, graphify-independence."""

import json
import shutil
import sys
from pathlib import Path

import pytest

from isaac_records.cli import main

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "golden_cuo_xas.json"


@pytest.fixture
def draft(tmp_path):
    path = tmp_path / "draft.json"
    shutil.copy(GOLDEN_PATH, path)
    return path


def test_export_moves_valid_record(draft, tmp_path, capsys):
    records_dir = tmp_path / "records"
    code = main(["--root", str(ROOT), "export", str(draft), "--records-dir", str(records_dir)])
    assert code == 0, capsys.readouterr().out
    assert not draft.exists()
    assert (records_dir / "isaac-2026-cuo-xas-0001.json").exists()


def test_export_blocked_by_validation_errors(draft, tmp_path, capsys):
    record = json.loads(draft.read_text(encoding="utf-8"))
    record["technique"]["xas"]["detection_mode"]["status"] = "needs_confirmation"
    draft.write_text(json.dumps(record), encoding="utf-8")

    records_dir = tmp_path / "records"
    code = main(["--root", str(ROOT), "export", str(draft), "--records-dir", str(records_dir)])
    assert code == 1
    assert draft.exists(), "a blocked export must leave the draft untouched"
    assert not (records_dir / "isaac-2026-cuo-xas-0001.json").exists()
    assert "Export blocked" in capsys.readouterr().out


def test_export_refuses_to_overwrite_existing_record(draft, tmp_path):
    records_dir = tmp_path / "records"
    assert main(["--root", str(ROOT), "export", str(draft), "--records-dir", str(records_dir)]) == 0
    duplicate = tmp_path / "draft2.json"
    shutil.copy(GOLDEN_PATH, duplicate)
    assert main(["--root", str(ROOT), "export", str(duplicate), "--records-dir", str(records_dir)]) == 1
    assert duplicate.exists()


def test_audit_reports_pass_and_fail(tmp_path, capsys):
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    shutil.copy(GOLDEN_PATH, records_dir / "good.json")
    bad = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    bad["technique"]["xas"]["absorbing_element"] = {"value": None, "status": "missing", "evidence": []}
    (records_dir / "bad.json").write_text(json.dumps(bad), encoding="utf-8")

    code = main(["--root", str(ROOT), "audit", "--records-dir", str(records_dir)])
    out = capsys.readouterr().out
    assert code == 1
    assert "PASS  good.json" in out
    assert "FAIL  bad.json" in out
    assert "FINALIZATION_INCOMPLETE" in out


def test_validate_with_evidence_map(capsys):
    code = main(["--root", str(ROOT), "validate", str(GOLDEN_PATH), "--finalize", "--evidence"])
    out = capsys.readouterr().out
    assert code == 0
    assert "PASS" in out
    assert "sample.formula" in out
    assert "user_confirmation" in out


def test_required_fields_matches_technique_case_insensitively(capsys):
    code = main(["--root", str(ROOT), "required-fields", "--technique", "xas"])
    out = capsys.readouterr().out
    assert code == 0
    assert "technique.xas.absorbing_element" in out
    assert "raw_data.uris" in out


def test_core_never_imports_graphify():
    # The pipeline must work with Graphify entirely absent: the deterministic
    # core is not allowed to depend on it, even optionally.
    assert not any(name == "graphify" or name.startswith("graphify.") for name in sys.modules)
