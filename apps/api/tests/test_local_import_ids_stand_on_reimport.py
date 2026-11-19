"""Every id the build before gave stands when this build re-imports the same files (review of PR 339, finding C).

This build fills slots the build before left empty: the record-level technique (``suggestions.TECHNIQUE_RULE_ID``)
and the set-point of a run whose name writes a signed potential (``bl15.filenames.signed_potential.v1``). A filled
slot must not shift every later id. What these pin, by importing the same synthetic folder with the new readings
switched off (the build before) and on:

* every VALUE id the build before gave names the same run and field, or is no longer asked (its number stays unused);
* every CANDIDATE id the build before gave names the same run and statement; the candidates this build adds are
  numbered after all of them, in the list's order;
* the value ids and candidate ids are each unique and in order.

SYNTHETIC files only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from isaac_api.bl15 import filenames
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import suggestions as S

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_e2e_import_questions import xdc  # noqa: E402
from test_local_import_technique_from_configuration import macros, spec_run  # noqa: E402

SETPOINT = "context.electrochemistry.potential_setpoint_V"
TECHNIQUE = "system.technique"


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


def _spec_beamtime(src: Path) -> Path:
    """Three runs on an emission line, the MIDDLE one at a negative potential, declared by a run macro."""
    stems = ("11_01_SYN_filter10_100mV", "12_01_SYN_filter10_m800mV", "13_02_SYN_filter10_300mV")
    for stem in stems:
        spec_run(src, stem)
    macros(src, stems)
    return src


def _xdc_beamtime(src: Path) -> Path:
    for stem in ("03_SYNZZ_1x1mm_081", "04_SYNZZ_dry_082", "05_SYNZZ_wet_083"):
        xdc(src / f"{stem}_A.001", free_text=("1x1 mm", "0.1 M KOH", "-0.3 V vs RHE"))
        (src / stem).mkdir(parents=True)
        (src / stem / "SYNtemplate_exp1.exp").write_text(f"EXPT_TYPE:\tXAS\nDATA_FILE:\t{stem.rsplit('_', 1)[0]}\n")
    return src


def _ids(src: Path, out: Path, capsys) -> dict:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    capsys.readouterr()
    data = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(data) == []
    key_of = {r["run_id"]: r["run_key"] for r in data["runs"]}
    return {
        "values": {m["value_id"]: (key_of.get(m["run_id"]), m["target_field_path"]) for m in data["missing_values"]},
        "candidates": {c["candidate_id"]: (key_of.get(c["run_id"]), c["statement_key"]) for c in data["candidates"]},
        "value_order": [m["value_id"] for m in data["missing_values"]],
        "candidate_order": [c["candidate_id"] for c in data["candidates"]],
        "data": data,
    }


def _both(build, tmp_path, capsys, monkeypatch) -> tuple[dict, dict]:
    src = build(tmp_path / "src" / "SYN_BL00_2100-22_ZZ")
    now = _ids(src, tmp_path / "now", capsys)
    # the build before: no signed token is read, and the instrument configuration suggests no technique
    monkeypatch.setattr(filenames, "_SIGN", re.compile(r"(?!)"))
    monkeypatch.setattr(S, "technique_candidate", lambda *a, **k: None)
    before = _ids(src, tmp_path / "before", capsys)
    return before, now


def _number(i: str) -> int:
    return int(i.split("-")[1])


@pytest.mark.parametrize("build", [_spec_beamtime, _xdc_beamtime], ids=["spec", "xdc"])
def test_every_id_the_build_before_gave_names_what_it_named(build, tmp_path, capsys, monkeypatch):
    before, now = _both(build, tmp_path, capsys, monkeypatch)
    # something was newly filled, or the test shows nothing
    added = [c for c in now["data"]["candidates"] if c["candidate_id"] not in before["candidates"]]
    assert added and {c["target_field_path"] for c in added} <= {SETPOINT, TECHNIQUE}
    # VALUE ids: the same slot, or not asked any more; never another slot
    moved = {i: (slot, now["values"][i]) for i, slot in before["values"].items() if i in now["values"] and now["values"][i] != slot}
    assert moved == {}
    gone = {slot for i, slot in before["values"].items() if i not in now["values"]}
    assert gone <= {(c_run, c["target_field_path"]) for c in added
                    for c_run in [next((r["run_key"] for r in now["data"]["runs"] if r["run_id"] == c["run_id"]), None)]}
    # CANDIDATE ids: every one the build before gave is still that run's statement
    assert {i: now["candidates"].get(i) for i in before["candidates"]} == before["candidates"]
    assert min(_number(c["candidate_id"]) for c in added) > max(map(_number, before["candidates"]))
    # in order, each once
    for order in (now["value_order"], now["candidate_order"]):
        numbers = [_number(i) for i in order]
        assert numbers == sorted(set(numbers))
    assert [_number(i) for i in now["candidate_order"]] == list(range(1, len(now["candidate_order"]) + 1))


def test_the_signed_set_point_is_on_its_run_and_after_every_older_candidate(tmp_path, capsys, monkeypatch):
    before, now = _both(_spec_beamtime, tmp_path, capsys, monkeypatch)
    data = now["data"]
    run = next(r for r in data["runs"] if r["stem"] == "12_01_SYN_filter10_m800mV")
    [c] = [c for c in data["candidates"] if c["run_id"] == run["run_id"] and c["target_field_path"] == SETPOINT]
    assert c["value"] == -0.8 and c["candidate_id"] in run["candidate_ids"]
    assert _number(c["candidate_id"]) > max(map(_number, before["candidates"]))
    # the set-point slot it fills kept its number: no value id names another slot (shown above), and the run has none
    assert not [m for m in data["missing_values"] if m["run_id"] == run["run_id"] and m["target_field_path"] == SETPOINT]
