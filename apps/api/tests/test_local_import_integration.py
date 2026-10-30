"""LOCAL-3: generic-reader runs in the bundle, and `isaac bundle group` / `isaac process`
persisted through the bundle writer. Synthetic only; LOCAL-P's processing is mocked
where it would need scientific libraries."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import isaac_api.workspace as ws
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

REPO_ROOT = ws.REPO_ROOT
SEMANTICS = REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
XDI = (
    "# XDI/1.0 SYNTHETIC/0.1\n# Column.1: energy eV\n# Column.2: mutrans\n# Element.symbol: Zz\n"
    "# ///\n# SYNTHETIC fixture, not instrument output\n#----\n# energy mutrans\n"
    "1000 0.1\n1005 0.2\n1010 0.4\n"
)


def _import(capsys, root: Path, out: Path) -> dict:
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    capsys.readouterr()
    return json.loads((out / "bundle.json").read_text())


@pytest.fixture()
def mixed(tmp_path):
    root = tmp_path / "corpus"
    shutil.copytree(SEMANTICS, root)
    (root / "extra").mkdir()
    (root / "extra" / "zz_scan.xdi").write_text(XDI)
    return root


# --- (a) generic-reader runs ---------------------------------------------------------------------


def test_files_the_engine_did_not_read_become_generic_runs(mixed, tmp_path, capsys):
    plain = _import(capsys, SEMANTICS, tmp_path / "plain")
    bundle = _import(capsys, mixed, tmp_path / "out")
    generic = [r for r in bundle["runs"] if r["source_type"].startswith("generic:")]
    assert len(bundle["runs"]) == len(plain["runs"]) + 1 and len(generic) == 1
    run = generic[0]
    assert run["run_key"] == "xdi_v1:extra/zz_scan"
    assert run["reader"] == {"reader_id": "xdi_reader_v1", "profile": "xdi_v1", "profile_version": "1",
                             "statements_total": run["reader"]["statements_total"], "statements_kept": run["reader"]["statements_kept"]}
    assert run["scans"][0]["relative_path"] == "extra/zz_scan.xdi" and run["scans"][0]["source_id"]
    assert run["candidate_ids"] == []  # no statement maps to a field: there is no rule for it
    assert all(u["relative_path"] != "extra/zz_scan.xdi" for u in bundle["unread_files"])
    assert B.validate_bundle(bundle) == []


def test_generic_statements_are_source_recorded_evidence_not_values(mixed, tmp_path, capsys):
    bundle = _import(capsys, mixed, tmp_path / "out")
    run = next(r for r in bundle["runs"] if r["source_type"].startswith("generic:"))
    entries = [e for e in bundle["extended_context"] if e.get("run_id") == run["run_id"]]
    assert entries and len(entries) == run["reader"]["statements_kept"]
    for e in entries:
        assert e["value_state"] == "source_recorded" and e["is_official_field_value"] is False
        assert e["official_path"] is None and e["parser_id"] == "xdi_reader_v1"
    assert not any(c["run_id"] == run["run_id"] for c in bundle["candidates"])


def test_a_generic_run_gets_the_same_missing_value_questions(mixed, tmp_path, capsys):
    bundle = _import(capsys, mixed, tmp_path / "out")
    run = next(r for r in bundle["runs"] if r["source_type"].startswith("generic:"))
    asked = [q for q in bundle["questions"] if q["kind"] == "missing_value" and q["run_id"] == run["run_id"]]
    assert asked and all(m["value"] is None for m in bundle["missing_values"] if m["run_id"] == run["run_id"])


def test_a_zip_is_not_walked_by_the_generic_readers(tmp_path, capsys):
    import zipfile

    archive = tmp_path / "c.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("c/zz_scan.xdi", XDI)
    bundle = _import(capsys, archive, tmp_path / "out")
    assert bundle["runs"] == [] and any(u["relative_path"] == "zz_scan.xdi" for u in bundle["unread_files"])


# --- (b) group / process ---------------------------------------------------------------------------


@pytest.fixture()
def bdir(tmp_path, capsys):
    out = tmp_path / "bundle"
    _import(capsys, SEMANTICS, out)
    return out


def test_group_persists_proposed_record_groups_through_the_writer(bdir, capsys):
    code = cli.main(["bundle", "group", str(bdir)])
    assert code == 0
    b = M.load(bdir)
    assert b["record_groups"] and all(g["status"] == "proposed" for g in b["record_groups"])
    assert B.check_bundle(bdir) == []
    run_keys = {r["run_key"] for r in b["runs"]}
    assert all(set(g["member_run_keys"]) <= run_keys for g in b["record_groups"])
    assert cli.main(["bundle", "group", str(bdir)]) == 2  # already grouped: refused without --regroup


def test_regroup_keeps_a_decided_group(bdir):
    M.group(bdir)
    first = M.load(bdir)["record_groups"][0]["group_id"]
    M.decide(bdir, target_ids=[first], decision="confirm", value=None, by="S", orcid=None)
    M.group(bdir, regroup=True)
    groups = {g["group_id"]: g for g in M.load(bdir)["record_groups"]}
    assert groups[first]["status"] == "scientist_confirmed"


def _fake_result(group_id: str) -> dict:
    return {
        "group_id": group_id, "protocol_id": "isaac.xas.v0", "protocol_version": "0.1",
        "protocol_status": "draft_unreviewed", "source": "isaac_protocol", "inputs": [], "steps": [],
        "outputs": {"files": [], "e0_eV": None, "edge_step": None, "points": None},
        "qc": {"metrics": {}, "verdict": "warn"}, "comparison": None, "state": "scientist_confirmed",
    }


def test_process_persists_undecided_results_and_never_self_approves(bdir, monkeypatch):
    from isaac_api.local_import.processing import cli_entry

    M.group(bdir)
    gid = M.load(bdir)["record_groups"][0]["group_id"]
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: {"status": "processed", "processing_results": [_fake_result(gid), _fake_result("rg-not-in-bundle")], "summary": {}})
    result = M.process(bdir)
    assert result["new"] == 1
    stored = M.load(bdir)["processing_results"]
    assert len(stored) == 1 and stored[0]["state"] == "needs_review"  # a result claiming confirmation is not one
    assert B.check_bundle(bdir) == []


def test_process_without_its_libraries_says_processing_not_installed(bdir, monkeypatch, capsys):
    from isaac_api.local_import.processing import cli_entry

    M.group(bdir)
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: {"status": "processing_unavailable", "missing": ["larch"]})
    code = cli.main(["process", str(bdir)])
    err = capsys.readouterr().err
    assert code == 2 and "processing not installed" in err and "larch" in err
    # the word the skill and the self-test look for, and the one fix
    assert "processing_unavailable" in err and "setup_isaac_local.sh --with-processing" in err


def test_process_before_grouping_is_refused(bdir, capsys):
    assert cli.main(["process", str(bdir)]) == 2


def test_isaac_dispatches_process(bdir, monkeypatch, capsys):
    from isaac_api.local_import.processing import cli_entry
    from isaac_records import cli as isaac_cli

    M.group(bdir)
    monkeypatch.setattr(cli_entry, "run_process", lambda *a, **k: {"status": "processed", "processing_results": [], "summary": {}})
    assert isaac_cli.main(["process", str(bdir)]) == 0
