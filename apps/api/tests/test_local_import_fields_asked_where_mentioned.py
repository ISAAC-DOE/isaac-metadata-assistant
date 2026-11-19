"""A field of one beamtime's standard is asked only where a source mentions it (audit of 18 Nov 2026, item 9).

``sample.composition.CuO2_mass_fraction``, ``sample.composition.sucrose_mass_fraction`` and
``sample.geometry.pellet_diameter_mm`` describe a diluted pellet standard. They were asked of every measurement run
of every beamtime. What these pin (``suggestions.MENTION_GATE_RULE_ID``): each is asked of a run only when that run's
own name, scan-header comment line or parsed readings mention it; every other optional field is asked as before.

SYNTHETIC files only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import suggestions as S

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_e2e_import_questions import xdc  # noqa: E402
from test_local_import_quick_merges import _spec_run  # noqa: E402

CUO2, SUCROSE, PELLET = S.MENTION_GATED_FIELDS


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


def _asked(src: Path, out: Path, capsys) -> dict[str, set[str]]:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    capsys.readouterr()
    data = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(data) == []
    stem = {r["run_id"]: r["stem"] for r in data["runs"]}
    asked: dict[str, set[str]] = {s: set() for s in stem.values()}
    for m in data["missing_values"]:
        if m["run_id"]:
            asked[stem[m["run_id"]]].add(m["target_field_path"])
    return asked


def test_the_three_fields_are_gated_and_named_from_the_writable_set():
    assert {CUO2, SUCROSE, PELLET} <= set(B._writable_paths())
    assert S.asks_field(PELLET, "05_SYN_std_ZZ_pellet") and not S.asks_field(PELLET, "05_SYN_film_on_ZZ")
    assert S.asks_field(SUCROSE, "ZZ 5wt% Sucrose") and S.asks_field(SUCROSE, "std_ZZ_sugar") and not S.asks_field(SUCROSE, "ZZ foil")
    assert S.asks_field(CUO2, "SYN CuO2 standard") and not S.asks_field(CUO2, "SYN CuO standard")
    assert S.asks_field("context.electrochemistry.pH", "") and S.asks_field("sample.sample_form", None)  # never gated


def test_an_xdc_run_is_asked_a_pellet_field_only_where_its_name_or_comment_mentions_it(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL43_2100-13_ZZ"
    xdc(src / "03_SYNZZ_film_1x1mm_081_A.001")                                              # mentions none
    xdc(src / "25_std_SYNZZ_5wt_sugar_064_A.001", free_text=("1x4mm", "SYNZZ 5wt% sucrose pellet"))  # name and comment
    xdc(src / "26_SYNZZ_std_065_A.001", free_text=("1x4mm", "pellet"))                         # the comment line alone
    asked = _asked(src, tmp_path / "out", capsys)
    assert asked["03_SYNZZ_film_1x1mm_081"].isdisjoint({CUO2, SUCROSE, PELLET})
    assert {SUCROSE, PELLET} <= asked["25_std_SYNZZ_5wt_sugar_064"] and CUO2 not in asked["25_std_SYNZZ_5wt_sugar_064"]
    assert PELLET in asked["26_SYNZZ_std_065"] and SUCROSE not in asked["26_SYNZZ_std_065"]
    # every other optional field is asked of all three, as before
    others = set.intersection(*asked.values())
    assert {"sample.sample_form", "context.electrochemistry.pH", "sample.material.formula"} <= others


def test_a_value_that_is_not_asked_keeps_its_number_so_every_other_id_stands(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL43_2100-15_ZZ"
    xdc(src / "03_SYNZZ_film_1x1mm_081_A.001")
    xdc(src / "25_std_SYNZZ_5wt_sugar_064_A.001", free_text=("1x4mm", "SYNZZ 5wt% sucrose pellet"))
    assert cli.main(["import", str(src), "--out", str(tmp_path / "out")]) == 0
    capsys.readouterr()
    data = json.loads((tmp_path / "out" / "bundle.json").read_text())
    ids = [int(m["value_id"].split("-")[1]) for m in data["missing_values"]]
    assert ids == sorted(set(ids))  # unique, in order
    # the film run's three unasked values left gaps: the pellet run's ids are what they were when all were asked
    by = {(m["run_id"], m["target_field_path"]): m["value_id"] for m in data["missing_values"]}
    runs = {r["stem"]: r["run_id"] for r in data["runs"]}
    film, pellet = runs["03_SYNZZ_film_1x1mm_081"], runs["25_std_SYNZZ_5wt_sugar_064"]
    for path in (SUCROSE, PELLET):
        assert (film, path) not in by
        assert int(by[(pellet, path)].split("-")[1]) - 1 not in ids  # the number before it is the film run's, unused


def test_a_spec_run_is_asked_a_pellet_field_only_where_its_name_mentions_it(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL00_2100-14_ZZ"
    _spec_run(src, "21_01_SYN_filter10")
    _spec_run(src, "22_02_SYNsucrose_filter10")
    asked = _asked(src, tmp_path / "out", capsys)
    assert asked["21_01_SYN_filter10"].isdisjoint({CUO2, SUCROSE, PELLET})
    assert SUCROSE in asked["22_02_SYNsucrose_filter10"] and PELLET not in asked["22_02_SYNsucrose_filter10"]
