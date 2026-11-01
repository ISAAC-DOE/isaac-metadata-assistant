"""Skill polish, cycle 1: an empty `bundle validate` is "nothing checked", never "all passed".
Synthetic only."""

from __future__ import annotations

import json
from pathlib import Path

import isaac_api.workspace as ws
from isaac_api.local_import import cli

SEMANTICS = ws.REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"


def test_validate_with_no_confirmed_group_says_so_and_does_not_exit_zero(tmp_path, capsys):
    bdir = tmp_path / "b"
    assert cli.main(["import", str(SEMANTICS), "--out", str(bdir)]) == 0
    assert cli.main(["bundle", "group", str(bdir)]) == 0  # proposed only: nothing confirmed
    capsys.readouterr()
    code = cli.main(["bundle", "validate", str(bdir)])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["verdicts"] == {}
    assert "no record group is confirmed" in out["nothing_validated"]
