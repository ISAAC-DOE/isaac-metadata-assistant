"""c16b (M1): what a BL4-3 scan header's comment lines state. Synthetic only (SYN names, invented lines).

On a real BL4-3 beamtime the comment lines of each scan header (lines 8-12, the ``.exp`` COMMENTS1-4) held the
electrolyte, pH, potential with its scale, and gas (``100mM NaClO4 pH1.3 He``, ``-0.3 V vs RHE``), and only the
start time was read. ``vs RHE`` was no scale, ``-0.3 V`` (with a space) was not seen at all, and a warning said
"file name m150mV, scan header -300mV), on the same scale" when the header named RHE and the name no scale.

What these pin (rule ``ssrl_xdc_header_comment_v1``): each line is read by pattern into candidates that NEED
REVIEW (never proposable, never confirmed): electrolyte name and concentration, pH, potential and its scale, in
every accepted spelling; nothing past line 12, no gas (no write route), no value from a line naming two potentials;
scans that disagree give no value; the warning names each source's scale, or says one is unstated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

from test_local_import_reader_ssrl_xdc import make_scan

NAME, CONC, PH = ("context.electrochemistry.electrolyte.name", "context.electrochemistry.electrolyte.concentration_M",
                  "context.electrochemistry.pH")
SETPOINT, SCALE = "context.electrochemistry.potential_setpoint_V", "context.electrochemistry.potential_scale"


def _read(line: str) -> dict:
    return {r["path"]: r["value"] for r in Q.header_comment_readings(line)}


@pytest.mark.parametrize("line", ["-0.3 V vs RHE", "-0.3V vs. RHE", "-300 mV vs RHE", "-300mV vs RHE",
                                  "E = -0.3 V versus RHE", "-0.3V_RHE", "−0.3 V vs RHE"])
def test_every_spelling_of_a_potential_on_rhe_reads_the_same(line):
    assert _read(line) == {SETPOINT: -0.3, SCALE: "RHE"}


def test_a_potential_with_no_scale_reads_no_scale_and_a_bias_is_no_potential():
    assert _read("-300mV") == {SETPOINT: -0.3}
    assert _read("-300 mV") == {SETPOINT: -0.3}
    assert _read("detector 1500V bias") == {}
    assert _read("0.1 V vs NHE") == {SETPOINT: 0.1}  # NHE is not a scale the record takes: kept as written only
    assert _read("0.1 V vs RHE then 0.5 V vs RHE") == {SETPOINT: None}  # two potentials in one line: no value


def test_the_electrolyte_line_reads_name_concentration_and_ph_never_the_gas():
    assert _read("100mM NaClO4 pH1.3 He") == {NAME: "NaClO4", CONC: 0.1, PH: 1.3}
    assert _read("0.5 M H2SO4, pH 0.3") == {NAME: "H2SO4", CONC: 0.5, PH: 0.3}
    assert _read("He atmosphere") == {}
    assert _read("0.1 M KOH + 0.5 M NaCl") == {}  # two concentrations: which is the electrolyte is not read


def test_header_potentials_in_line_keeps_the_literal_as_written():
    [p] = Q.header_potentials_in_line("100mM NaClO4 -0.3 V vs RHE He")
    assert (p["literal"], p["scale"], p["volts"]) == ("-0.3 V vs RHE", "RHE", -0.3)


# --- the import ------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def imported(tmp_path_factory) -> dict:
    src = tmp_path_factory.mktemp("c16b") / "SYN_bt43"
    comments = ("100mM NaClO4 pH1.3 He", "-0.3 V vs RHE", "SYN spare 3", "SYN spare 4", "-0.9 V vs RHE")  # lines 9-13
    for i in (1, 2):
        make_scan(src / f"04_SYNmof_wet_019_A.{i:03d}", free_text=comments)
        make_scan(src / f"05_SYNmof_m150mV_021_A.{i:03d}", free_text=("100mM NaClO4 pH1.3", "-300mV vs RHE"))
    make_scan(src / "06_SYNmof_mix_022_A.001", free_text=("-0.3 V vs RHE",))
    make_scan(src / "06_SYNmof_mix_022_A.002", free_text=("-0.4 V vs RHE",))
    make_scan(src / "07_SYNfoil_023_A.001", free_text=("1x1 mm beam",))
    make_scan(src / "08_SYNmof_two_024_A.001", free_text=("-0.3 V vs RHE (was -0.5 V vs RHE)",))
    out = tmp_path_factory.mktemp("c16b-out") / "bundle"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    b = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(b) == []
    return {"out": out, "bundle": b}


def _cands(b: dict, label: str) -> dict:
    rid = next(r["run_id"] for r in b["runs"] if r["label"] == label)
    return {c["target_field_path"]: c for c in b["candidates"] if c["run_id"] == rid and B.is_header_comment_candidate(c)}


def test_each_field_a_comment_line_states_is_a_candidate_that_needs_review(imported):
    got = _cands(imported["bundle"], "04_SYNmof_wet_019")
    assert {p: c["value"] for p, c in got.items()} == {NAME: "NaClO4", CONC: 0.1, PH: 1.3, SETPOINT: -0.3, SCALE: "RHE"}
    for c in got.values():
        assert c["value_state"] == B.STATE_NEEDS_REVIEW and c["state_basis"]["proposable"] is False
        assert c["eligibility_for_official_record"]["eligible"] is False
        assert c["rule"].startswith(B.XDC_COMMENT_RULE_ID)
        assert [e["relative_path"] for e in c["evidence"]] == ["04_SYNmof_wet_019_A.001", "04_SYNmof_wet_019_A.002"]
        assert all(e["method_id"] == B.XDC_COMMENT_RULE_ID for e in c["evidence"])
    assert got[SETPOINT]["evidence"][0]["locator"] == "line:10"
    assert got[SETPOINT]["observed_literals"] == ["-0.3 V vs RHE"]  # line 13 (-0.9 V) is past the comment lines


def test_the_start_time_candidates_keep_their_ids(imported):
    b = imported["bundle"]
    starts = [c["candidate_id"] for c in b["candidates"] if B.is_local_clock_start(c)]
    assert starts == [f"cand-{i:04d}" for i in range(1, len(starts) + 1)]


def test_scans_stating_different_values_give_a_candidate_with_no_value(imported):
    got = _cands(imported["bundle"], "06_SYNmof_mix_022")
    assert got[SETPOINT]["value"] is None and "-0.3 V vs RHE; -0.4 V vs RHE" in got[SETPOINT]["state_basis"]["not_proposable_reason"]
    assert got[SCALE]["value"] == "RHE"
    assert not _cands(imported["bundle"], "07_SYNfoil_023")
    two = _cands(imported["bundle"], "08_SYNmof_two_024")
    assert two[SETPOINT]["value"] is None and SCALE not in two
    assert "more than one potential (-0.3 V vs RHE; -0.5 V vs RHE)" in two[SETPOINT]["state_basis"]["not_proposable_reason"]


def test_the_warning_names_each_sources_scale_never_the_same_scale(imported):
    b = imported["bundle"]
    rid = next(r["run_id"] for r in b["runs"] if r["label"] == "05_SYNmof_m150mV_021")
    group = {"group_id": "rg-syn", "member_run_keys": [], "member_run_ids": [rid]}
    [w] = R._stated_potential_warnings(b, group, {rid}, {}, {})
    text = R.potential_warning_text(w)
    assert "same scale" not in text and "no reader reads the set-point" not in text
    assert f"({rid}: file name m150mV, scan header -300mV vs RHE; the scan header names RHE, the file name no scale)" in text
    assert "read from that free-text line, the set-point and the scale need your review" in text


def test_neither_scale_stated_is_said_so():
    text = Q.stated_potential_notes({"stated": [
        {"literal": "m150mV", "stated_in": "file name", "runs": ["run-1"]},
        {"literal": "-300mV", "stated_in": "scan header", "runs": ["run-1"]}]})
    assert "neither names its scale" in text and "same scale" not in text
