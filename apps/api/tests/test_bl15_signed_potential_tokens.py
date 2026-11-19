"""Signed and special potential tokens in a file name (audit of 18 Nov 2026, rule 10).

The token reader read ``850mV`` and left ``m850mV`` and ``-850mV`` unread, so a run held at a negative potential
had no potential at all. What these pin:

* a leading ``m`` or ``-`` on a potential token is a minus sign (``m800mV`` -0.8 V, ``-500mV`` -0.5 V, ``m0V`` 0 V,
  ``m0p15V`` -0.15 V), read under its own named rule; an unsigned token keeps the rule it always had;
* ``OCV`` / ``OCP`` is open circuit: never a magnitude;
* a name that writes two levels marked ``Pos`` / ``Neg`` is a pulsed step: NO token of it is one set-point;
* when a name has several potential tokens the LAST is the condition; an earlier one is not read as a value;
* a potential inside another word (``after1200mVCycling``, ``300mVvsRHE``) is read as before.

SYNTHETIC names only.
"""

from __future__ import annotations

import pytest

from isaac_api.bl15 import filenames
from isaac_api.bl15.evidence import CONCEPT_POTENTIAL_MAGNITUDE, CONCEPT_UNKNOWN_TOKEN

from test_bl15_readers import _synthetic_record


def _read(stem: str):
    result = filenames.read_filename(_synthetic_record(stem), stem=stem)
    assert result.refused_reason is None
    return result


def _potentials(stem: str) -> list[tuple[str, float]]:
    return [(e.raw_literal, e.normalized_value) for e in _read(stem).evidence if e.concept == CONCEPT_POTENTIAL_MAGNITUDE]


def _unknown(stem: str) -> dict[str, str | None]:
    return {e.raw_literal: e.normalization_rule for e in _read(stem).evidence if e.concept == CONCEPT_UNKNOWN_TOKEN}


@pytest.mark.parametrize("token, volts", [
    ("m800mV", -0.8), ("-500mV", -0.5), ("m1000mV", -1.0), ("M250mv", -0.25), ("m0p15V", -0.15), ("m1V", -1),
    ("m0V", 0), ("m0mV", 0.0), ("-0mV", 0.0),
])
def test_a_leading_m_or_minus_is_a_minus_sign(token, volts):
    [(literal, value)] = _potentials(f"11_02_SYNZZ_{token}")
    assert literal == token and value == volts
    assert str(value) not in ("-0.0", "-0")  # zero is zero, never minus zero
    item = next(e for e in _read(f"11_02_SYNZZ_{token}").evidence if e.concept == CONCEPT_POTENTIAL_MAGNITUDE)
    assert item.unit == "V" and item.normalization_rule == filenames.RULE_SIGNED_POTENTIAL
    assert "minus" in filenames.RULE_SIGNED_POTENTIAL


@pytest.mark.parametrize("token, volts, rule", [
    ("850mV", 0.85, "RULE_MILLIVOLT_TO_VOLT"), ("1p2V", 1.2, "RULE_P_DECIMAL_VOLT"), ("2V", 2, "RULE_BARE_VOLT"),
    ("060mV", 0.06, "RULE_MILLIVOLT_TO_VOLT"),
])
def test_an_unsigned_token_reads_as_it_always_did(token, volts, rule):
    result = _read(f"11_02_SYNZZ_{token}")
    [item] = [e for e in result.evidence if e.concept == CONCEPT_POTENTIAL_MAGNITUDE]
    assert item.normalized_value == volts and item.normalization_rule == getattr(filenames, rule)


@pytest.mark.parametrize("stem", ["SYNfilm_on_ZZ_OCV", "SYNfilm_on_ZZ_OCP_4", "SYNfilm_on_ZZ_ocv"])
def test_open_circuit_is_never_a_magnitude(stem):
    assert _potentials(stem) == []
    assert filenames.name_potential(stem.split("_")).kind == filenames.NAME_OPEN_CIRCUIT


def test_the_last_potential_token_is_the_condition():
    # open circuit first, then a held potential: the held potential is the condition
    assert _potentials("SYNfilm_on_ZZ_OCV_5_m1000mV") == [("m1000mV", -1.0)]
    assert _potentials("SYNfilm_on_ZZ_OCV_1_1200mV") == [("1200mV", 1.2)]
    # two plain tokens: only the last is read; the earlier one stays an unread token that says why
    assert _potentials("SYNZZ_400mV_then_m300mV") == [("m300mV", -0.3)]
    assert _unknown("SYNZZ_400mV_then_m300mV")["400mV"] == filenames.RULE_LAST_POTENTIAL_TOKEN
    reading = filenames.name_potential("SYNfilm_on_ZZ_OCV_5_m1000mV".split("_"))
    assert (reading.kind, reading.index, reading.volts) == (filenames.NAME_SETPOINT, 5, -1.0)


@pytest.mark.parametrize("stem, levels", [
    ("SYNNPs_on_ZZ_17_1200mVPos_m400mVNeg", [("1200mVPos", 1.2), ("m400mVNeg", -0.4)]),
    ("SYNNPs_on_ZZ_3_14c_1200mVpos_m700mV_35mlmin", [("1200mVpos", 1.2), ("m700mV", -0.7)]),
])
def test_two_levels_are_a_pulsed_step_never_one_set_point(stem, levels):
    assert _potentials(stem) == []  # neither level is THE potential
    unknown = _unknown(stem)
    for literal, _ in levels:
        assert unknown[literal] == filenames.RULE_PULSED_LEVELS
    reading = filenames.name_potential(stem.split("_"))
    assert reading.kind == filenames.NAME_PULSED and reading.volts is None
    assert [(lv.token, lv.volts) for lv in reading.levels] == levels


@pytest.mark.parametrize("stem, expected", [
    ("01_04_SYNZZ_after1200mVCycling_060mV", [("060mV", 0.06)]),  # the cycling word is its own statement
    ("SYNNPs_04_E2_1000mV_oxidation_1400mVvsRHE", [("1000mV", 1.0)]),  # a scale glued on: not read here, as before
    ("71_07_SYNZZ_0p5nm_AsIs_NoElectrolyte", []),
    ("SYN_mV_m_V_mmV", []),
])
def test_a_potential_inside_another_word_is_read_as_before(stem, expected):
    assert _potentials(stem) == expected


def test_no_potential_token_gives_no_reading():
    reading = filenames.name_potential("11_02_SYNZZ_dry".split("_"))
    assert reading.kind is None and reading.volts is None and reading.levels == ()
