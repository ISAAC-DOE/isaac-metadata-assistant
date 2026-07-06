"""Deterministic structured-sheet parser (CSV + XLSX).

Hermetic: reads only the committed synthetic CSV fixture and builds a throwaway
`.xlsx` in ``tmp_path`` from the generator's ``_build_xlsx``. Never touches
``examples/``. Asserts values, types (string vs number), single-entry spreadsheet
evidence with precise locators, and that no field was invented.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from isaac_records.extract import FIELD_MAP, parse_contributors, parse_structured

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "tests" / "fixtures" / "synthetic" / "mock_campaign.csv"


def _by_path(fields):
    return {f.path: f for f in fields}


def _load_generator():
    """Import scripts/make_synthetic_examples.py for its ``_build_xlsx`` helper."""
    src = REPO_ROOT / "scripts" / "make_synthetic_examples.py"
    spec = importlib.util.spec_from_file_location("_make_synthetic_examples", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_csv_scalar_values_and_types():
    by = _by_path(parse_structured(CSV_PATH))

    # A string stays a string (must NOT be coerced to a number).
    beamline = by["system.facility.beamline"]
    assert beamline.value == "15-2"
    assert isinstance(beamline.value, str)

    formula = by["sample.material.formula"]
    assert formula.value == "CuO2"
    assert isinstance(formula.value, str)

    # A declared-numeric field is coerced to a NUMBER.
    temp = by["context.temperature_K"]
    assert temp.value == 298
    assert isinstance(temp.value, int) and not isinstance(temp.value, bool)
    assert temp.unit == "K"

    # Floats and ints coerce per FIELD_MAP.
    cuo2 = by["sample.composition.CuO2_mass_fraction"]
    assert cuo2.value == pytest.approx(0.001)
    assert isinstance(cuo2.value, float)

    pellet = by["sample.geometry.pellet_diameter_mm"]
    assert pellet.value == pytest.approx(7.0)
    assert isinstance(pellet.value, float)
    assert pellet.unit == "mm"

    n_scans = by["system.configuration.n_scans"]
    assert n_scans.value == 6
    assert isinstance(n_scans.value, int)

    # Open-namespace configuration string kept verbatim.
    assert by["system.configuration.spectrometer_geometry"].value == "Von_Hamos"
    assert by["timestamps.acquired_start_utc"].value == "2099-03-01T18:30:00Z"


def test_every_field_verified_with_one_spreadsheet_evidence():
    fields = parse_structured(CSV_PATH)
    for f in fields:
        assert f.status == "verified", f
        assert len(f.evidence) == 1, f
        e = f.evidence[0]
        assert e["source_type"] == "spreadsheet"
        assert e["source_file"] == "mock_campaign.csv"
        assert e["locator"].startswith("Sheet '")
        assert "field=" in e["locator"]
        assert e.get("quote") is not None

    by = _by_path(fields)
    beam_ev = by["system.facility.beamline"].evidence[0]
    assert beam_ev["locator"] == "Sheet 'Campaign Info', field=beamline"
    assert beam_ev["quote"] == "15-2"


def test_temperature_accepts_int_or_float(tmp_path):
    # Committed CSV: 298 -> int (a JSON number), NOT coerced to float.
    by = _by_path(parse_structured(CSV_PATH))
    temp = by["context.temperature_K"]
    assert temp.value == 298
    assert isinstance(temp.value, int) and not isinstance(temp.value, bool)

    # A fractional temperature -> float (still a JSON number).
    frac = tmp_path / "frac.csv"
    frac.write_text(
        "section,field,value,unit,notes\n"
        "Configurations,temperature_K,298.5,K,\n"
        "Campaign Info,beamline,15-2,,\n"
        "Sample,formula,CuO2,,\n",
        encoding="utf-8",
    )
    fby = _by_path(parse_structured(frac))
    ftemp = fby["context.temperature_K"]
    assert ftemp.value == pytest.approx(298.5)
    assert isinstance(ftemp.value, float)
    assert ftemp.status == "verified"

    # Regression: strings are never coerced to numbers.
    assert fby["system.facility.beamline"].value == "15-2"
    assert isinstance(fby["system.facility.beamline"].value, str)
    assert fby["sample.material.formula"].value == "CuO2"
    assert isinstance(fby["sample.material.formula"].value, str)


def test_no_field_invented():
    fields = parse_structured(CSV_PATH)
    by = _by_path(fields)
    targets = {path for path, _py in FIELD_MAP.values()}

    # Every emitted path is a known FIELD_MAP target (nothing fabricated).
    assert set(by) <= targets

    # Exactly the 25 mapped rows present in the sheet (experimenters +
    # incident-energy + qc_status are NOT emitted as scalar fields).
    assert len(fields) == 25

    # Experimenters never leak into fields.
    assert not any("experimenter" in p for p in by)
    assert not any(p.startswith("attribution") for p in by)


def test_contributors_are_separate_from_fields():
    contribs = parse_contributors(CSV_PATH)
    assert {c["name"] for c in contribs} == {"Ada Lovelace", "Grace Hopper"}
    for c in contribs:
        assert c["role"] == "curated_record"
        assert isinstance(c["evidence"], list) and len(c["evidence"]) == 1
        assert c["evidence"][0]["source_type"] == "spreadsheet"
        assert c["evidence"][0]["source_file"] == "mock_campaign.csv"


def test_xlsx_matches_csv_with_cell_locators(tmp_path):
    pytest.importorskip("openpyxl")
    gen = _load_generator()
    xlsx_path = tmp_path / "mock_campaign.xlsx"
    gen._build_xlsx(xlsx_path)

    csv_by = _by_path(parse_structured(CSV_PATH))
    xlsx_by = _by_path(parse_structured(xlsx_path))

    # Same set of fields, same values and units as the CSV.
    assert set(xlsx_by) == set(csv_by)
    for path, xf in xlsx_by.items():
        assert xf.value == csv_by[path].value, path
        assert xf.unit == csv_by[path].unit, path
        assert xf.status == "verified"

    # XLSX locators carry the real A1 cell address of the value cell (column B).
    for xf in xlsx_by.values():
        e = xf.evidence[0]
        assert e["source_type"] == "spreadsheet"
        assert e["source_file"] == "mock_campaign.xlsx"
        assert "cell " in e["locator"]

    assert xlsx_by["system.facility.facility_name"].evidence[0]["locator"] == (
        "Sheet 'Campaign Info', cell B2"
    )
    assert xlsx_by["system.facility.beamline"].evidence[0]["locator"] == (
        "Sheet 'Campaign Info', cell B5"
    )
