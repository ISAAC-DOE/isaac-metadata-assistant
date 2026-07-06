"""CLI behavior: export writes record + sidecar, gating, audit, new-id."""

import json
import re
import shutil
from pathlib import Path

import pytest

from isaac_records.cli import main

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "tests" / "fixtures" / "cuo_xanes_draft.json"


def test_export_writes_record_and_sidecar(tmp_path, capsys):
    records = tmp_path / "records"
    code = main(["--root", str(ROOT), "export", str(DRAFT), "--records-dir", str(records)])
    assert code == 0, capsys.readouterr().out
    jsons = list(records.glob("*.json"))
    assert len(jsons) == 2
    record = next(p for p in jsons if not p.name.endswith(".evidence.json"))
    sidecar = next(p for p in jsons if p.name.endswith(".evidence.json"))
    assert record.stem == sidecar.name[: -len(".evidence.json")]
    data = json.loads(record.read_text())
    assert data["isaac_record_version"] == "1.05"


def test_blocked_export_writes_nothing(tmp_path, capsys):
    bad = tmp_path / "bad_draft.json"
    draft = json.loads(DRAFT.read_text())
    draft["fields"]["context.temperature_K"]["evidence"] = []  # no-guessing violation
    bad.write_text(json.dumps(draft))
    records = tmp_path / "records"
    code = main(["--root", str(ROOT), "export", str(bad), "--records-dir", str(records)])
    assert code == 1
    assert not records.exists() or not list(records.glob("*.json"))
    assert "nothing exported" in capsys.readouterr().out.lower()


def test_validate_autodetects_draft_vs_record(tmp_path, capsys):
    assert main(["--root", str(ROOT), "validate", str(DRAFT)]) == 0
    out = capsys.readouterr().out
    assert "Draft validation" in out

    example = ROOT / "tests" / "fixtures" / "official" / "ex_situ_xanes_cuo2_record.json"
    assert main(["--root", str(ROOT), "validate", str(example)]) == 0
    assert "official ISAAC schema" in capsys.readouterr().out


def test_audit_reports_official_validity_and_coverage(tmp_path, capsys):
    records = tmp_path / "records"
    main(["--root", str(ROOT), "export", str(DRAFT), "--records-dir", str(records)])
    code = main(["--root", str(ROOT), "audit", "--records-dir", str(records)])
    out = capsys.readouterr().out
    assert code == 0
    assert "PASS" in out
    assert "evidence" in out


def test_new_id_is_ulid(capsys):
    assert main(["--root", str(ROOT), "new-id"]) == 0
    assert re.fullmatch(r"[0-9A-Z]{26}", capsys.readouterr().out.strip())
