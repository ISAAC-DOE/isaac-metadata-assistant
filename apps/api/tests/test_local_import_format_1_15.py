"""Bundle format 1.15.0: the import rules of the second round of the 18 Nov 2026 audit are disclosed.

A 1.15.0 build reads, at import, what a 1.14.0 build did not. Only a re-import applies it. What these pin:

* the version is bumped by the existing mechanism (``FORMAT_VERSION``, ``_VERSION_ORDER``, the schema's enum and its
  per-version block), and a 1.14.0 bundle stays valid;
* ``CHANGES_ADDED_IN["1.15.0"]`` names each rule by its id and says only a re-import applies them;
* the first write of a 1.14.0 bundle by this build appends ONE ``format_upgrades`` entry whose statement says so,
  and the longest such statement still fits the schema.

SYNTHETIC files only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.bl15 import classify as C
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import suggestions as S

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_quick_merges import _spec_run  # noqa: E402


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


RULES = (S.NAME_POTENTIAL_RULE_ID, S.OPEN_CIRCUIT_RULE_ID, C.PROCESSED_TITLE_RULE_ID, B.TITLE_LINK_RULE_ID, *B.NOT_A_CONFLICT_RULES)


def test_the_version_is_bumped_by_the_existing_mechanism():
    assert B.FORMAT_VERSION == "1.15.0" == B._VERSION_ORDER[-1] and B._VERSION_ORDER[-2] == "1.14.0"
    schema = B.bundle_schema()
    assert schema["properties"]["format_version"]["enum"][-2:] == ["1.14.0", "1.15.0"]
    assert "1.15.0" in schema["properties"]["format_version"]["description"]
    blocks = [b for b in schema.get("allOf") or ()
              if (b.get("if") or {}).get("properties", {}).get("format_version", {}).get("const") == "1.15.0"]
    assert blocks and blocks[0]["then"]["required"] == ["processed_outputs"]


def test_the_change_note_names_each_rule_and_what_a_re_import_does():
    note = B.CHANGES_ADDED_IN["1.15.0"]
    for rule in RULES:
        assert rule in note, rule
    assert "re-import" in note
    assert B.changes_since("1.14.0") == [note]


def test_an_older_bundle_is_told_on_its_first_write(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL00_2100-24_ZZ"
    _spec_run(src, "21_01_SYN_filter10_m800mV")
    out = tmp_path / "out"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    capsys.readouterr()
    data = json.loads((out / "bundle.json").read_text())
    data["format_version"] = "1.14.0"  # what a 1.14.0 build wrote (its shape is the same)
    (out / "bundle.json").write_text(json.dumps(data))
    assert B.validate_bundle(json.loads((out / "bundle.json").read_text())) == []  # a 1.14.0 bundle stays valid
    M.decide(out, target_ids=["experiment"], decision="defer", value=None, by="SYN Scientist", orcid=None)
    saved = json.loads((out / "bundle.json").read_text())
    assert saved["format_version"] == "1.15.0" and B.validate_bundle(saved) == []
    [u] = [u for u in saved.get("format_upgrades") or () if u.get("from_format_version") == "1.14.0"]
    assert B.CHANGES_ADDED_IN["1.15.0"] in u["statement"]
