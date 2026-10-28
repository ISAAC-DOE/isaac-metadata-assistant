"""Shared synthetic helpers for the record-composition tests (not a test module)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import isaac_api.workspace as ws
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import portal as P

REPO_ROOT = ws.REPO_ROOT
SEMANTICS = REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"
BY = dict(by="Synthetic Scientist", orcid=None)


def upstream_like_schema() -> dict:
    """The vendored schema plus the upstream shapes the composer writes (synthetic)."""
    schema = json.loads((REPO_ROOT / "schema" / "isaac_record_v1.json").read_text())
    props = schema["properties"]
    props["attribution"]["properties"]["produced_by"] = {
        "type": "object", "additionalProperties": False,
        "properties": {"group": {"type": "string"}, "organization": {"type": "string"},
                       "people": {"type": "array", "items": {"type": "string"}}},
    }
    ctx = props["context"]
    ctx["properties"]["temperature_K"] = {"type": ["number", "null"]}
    ctx["properties"]["temperature_basis"] = {"type": "string", "enum": ["stated", "room_temperature", "not_reported"]}
    return schema


@pytest.fixture()
def fake_upstream_env(tmp_path_factory, monkeypatch):
    up = tmp_path_factory.mktemp("upstream")
    (up / "portal").mkdir()
    (up / "portal" / "validation.py").write_text("# synthetic stand-in; never executed\n")
    (up / "schema").mkdir()
    (up / ".git").mkdir()
    (up / ".git" / "HEAD").write_text("a1cb1c8" + "0" * 33 + "\n")
    (up / "schema" / "isaac_record_v1.json").write_text(json.dumps(upstream_like_schema()))
    monkeypatch.setenv(P.DIR_ENV, str(up))
    monkeypatch.setenv(P.PYTHON_ENV, sys.executable)
    return up


@pytest.fixture(scope="module")
def pristine_bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp("pristine") / "bundle"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    return out


def decide_everything(bdir: Path, *, add_group: bool = True) -> None:
    """Confirm group g1 / approve p1 (both must exist) and answer every required value."""
    b = M.load(bdir)

    def miss(path, run_id):
        return next(m["value_id"] for m in b["missing_values"] if m["target_field_path"] == path and m["run_id"] == run_id)

    def cand(path, run_id):
        return next(c for c in b["candidates"] if c["target_field_path"] == path and c["run_id"] == run_id)

    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="valid", **BY)
    M.decide(bdir, target_ids=[cand("sample.material.name", "run-001")["candidate_id"]], decision="correct", value="ZZ1 synthetic", **BY)
    M.decide(bdir, target_ids=[cand("system.technique", None)["candidate_id"]], decision="correct", value="HERFD-XAS", **BY)
    for path, value in [("system.domain", "experimental"), ("attribution.produced_by.group", "Synthetic group"),
                        ("attribution.produced_by.organization", "Synthetic University")]:
        M.decide(bdir, target_ids=[miss(path, None)], decision="correct", value=value, **BY)
    for path, value in [("sample.sample_form", "powder"), ("context.environment", "ex_situ")]:
        M.decide(bdir, target_ids=[miss(path, "run-001")], decision="correct", value=value, **BY)
