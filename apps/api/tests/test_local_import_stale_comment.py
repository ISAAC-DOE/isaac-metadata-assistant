"""A comment line left over from an earlier run is flagged, never offered as a stated value (audit of 18 Nov 2026,
rule 8, the safety half).

At the beamline the comment lines of an SSRL XDC scan are typed once and stay until someone retypes them. A run whose
comment line is IDENTICAL to the line an earlier run was acquired with, while the potential its own name writes has
changed, most likely carries the earlier run's comment. What these pin (``suggestions.STALE_COMMENT_RULE_ID``):

* such a line is flagged on the run (``comment_possibly_stale``, naming the run the line first appeared on and both
  name potentials), in acquisition order, through an unbroken chain of identical lines;
* the set-point (and the scale) the comment rule would read from it is NOT offered: the candidate has no value and
  says why; the electrolyte the same line states is still read (the name gives no reason to doubt it);
* a line that changes with the name, a name whose potential comes back to the first run's, and runs with no
  potential in the name are not flagged;
* an AI reading that cites a flagged line for the set-point as "stated" is loaded as "inferred", with the flag.

SYNTHETIC files only.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import suggestions as S

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_reader_ssrl_xdc import make_scan  # noqa: E402

SETPOINT = "context.electrochemistry.potential_setpoint_V"
SCALE = "context.electrochemistry.potential_scale"
NAME = "context.electrochemistry.electrolyte.name"
PLAIN = "-0.3 V vs RHE"


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


def _stamp(minute: int) -> str:
    return datetime(2099, 7, 14, 10, minute, 0).strftime("%a %b %d %H:%M:%S %Y")


#: name -> (minute acquired, comment lines), in acquisition order
RUNS = {
    "12_SYNZZ_1MSYN_m300mV_040": (0, ("1x1 mm", "0.1 M KOH", PLAIN)),      # the line is written for this run
    "13_SYNZZ_1MSYN_m150mV_041": (10, ("1x1 mm", "0.1 M KOH", PLAIN)),     # the same line, another potential: stale
    "14_SYNZZ_1MSYN_m450mV_042": (20, ("1x1 mm", "0.1 M KOH", PLAIN)),     # still the same line: stale (a chain)
    "15_SYNZZ_1MSYN_m300mV_043": (30, ("1x1 mm", "0.1 M KOH", PLAIN)),     # the name is back at the first run's: not stale
    "16_SYNZZ_1MSYN_m600mV_044": (40, ("1x1 mm", "0.1 M KOH", "-0.6 V vs RHE")),  # retyped with the name: not stale
    "17_SYNZZ_dry_045": (50, ("1x1 mm", "0.1 M KOH", "-0.6 V vs RHE")),    # no potential in the name: nothing to compare
}


@pytest.fixture()
def bundle(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL43_2100-16_ZZ"
    for stem, (minute, lines) in RUNS.items():
        make_scan(src / f"{stem}_A.001", timestamp=_stamp(minute), free_text=lines)
    out = tmp_path / "out"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    capsys.readouterr()
    data = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(data) == []
    return data


def _run(data: dict, stem: str) -> dict:
    return next(r for r in data["runs"] if r["stem"] == stem)


def _flags(data: dict, stem: str) -> list[dict]:
    return [a for a in _run(data, stem)["other_relationships"]["anomalies"] if a.get("kind") == S.STALE_COMMENT_KIND]


def _cand(data: dict, stem: str, path: str) -> dict:
    rid = _run(data, stem)["run_id"]
    # the comment line's own candidate: since 1.16.0 a run's name may give a second one for the set-point
    # (suggestions.NAME_POTENTIAL_RULE_ID, the scientists' rule that the potential is inferable from the experiment)
    [c] = [c for c in data["candidates"] if c["run_id"] == rid and c["target_field_path"] == path
           and B.is_header_comment_candidate(c)]
    return c


def _name_cand(data: dict, stem: str) -> dict | None:
    rid = _run(data, stem)["run_id"]
    return next((c for c in data["candidates"] if c["run_id"] == rid and c["target_field_path"] == SETPOINT
                 and c["rule"].startswith(S.NAME_POTENTIAL_RULE_ID)), None)


def test_a_line_identical_to_an_earlier_runs_under_another_name_potential_is_flagged(bundle):
    assert _flags(bundle, "12_SYNZZ_1MSYN_m300mV_040") == []
    for stem, token in (("13_SYNZZ_1MSYN_m150mV_041", "m150mV"), ("14_SYNZZ_1MSYN_m450mV_042", "m450mV")):
        [flag] = _flags(bundle, stem)
        assert flag["locator"] == "line:11" and flag["source_relative_path"] == f"{stem}_A.001"
        assert flag["rule_id"] == S.STALE_COMMENT_RULE_ID and flag["severity"] == "flag"
        # it names the run the line first appeared on, and both potentials the names write
        assert "12_SYNZZ_1MSYN_m300mV_040" in flag["detail"] and "m300mV" in flag["detail"] and token in flag["detail"]
        assert repr(PLAIN) in flag["detail"] and "possibly" in flag["detail"]


def test_a_flagged_line_offers_no_set_point_and_no_scale_but_still_its_electrolyte(bundle):
    first = _cand(bundle, "12_SYNZZ_1MSYN_m300mV_040", SETPOINT)
    assert first["value"] == -0.3 and _cand(bundle, "12_SYNZZ_1MSYN_m300mV_040", SCALE)["value"] == "RHE"
    for stem in ("13_SYNZZ_1MSYN_m150mV_041", "14_SYNZZ_1MSYN_m450mV_042"):
        for path in (SETPOINT, SCALE):
            c = _cand(bundle, stem, path)
            assert c["value"] is None and c["value_state"] == B.STATE_NEEDS_REVIEW
            reason = c["state_basis"]["not_proposable_reason"]
            assert "possibly" in reason and "12_SYNZZ_1MSYN_m300mV_040" in reason and "not offered" in reason
            assert all(e["relation"] == "context" for e in c["evidence"])
        assert _cand(bundle, stem, NAME)["value"] == "KOH"  # the electrolyte line is another line, read as before


def test_the_flag_reaches_the_scientist_also_when_the_line_never_parsed_to_a_value(tmp_path, capsys):
    """The line is free text the comment rule reads NO value from (a potential glued to its scale inside a sentence).
    Its candidate asked for the value before; it must also say the line is possibly another run's."""
    src = tmp_path / "src" / "SYN_BL43_2100-21_ZZ"
    line = "SYN sample A in 1M KOH 0Vrhe"
    make_scan(src / "14_SYNZZ_1MKOH_0V_095_A.001", timestamp=_stamp(0), free_text=("1x1 mm", line))
    make_scan(src / "15_SYNZZ_1MKOH_m600mV_096_A.001", timestamp=_stamp(10), free_text=("1x1 mm", line))
    assert cli.main(["import", str(src), "--out", str(tmp_path / "out")]) == 0
    capsys.readouterr()
    data = json.loads((tmp_path / "out" / "bundle.json").read_text())
    assert B.validate_bundle(data) == []
    copy = _cand(data, "15_SYNZZ_1MKOH_m600mV_096", SETPOINT)
    assert copy["value"] is None  # as before: no value is read from such a line
    # 1.16.0: the first run's name (0V) writes what its line mentions, so the NAME offers the set-point (the
    # scientists' rule: the potential is inferable from the experiment) and the line no longer asks for it
    first = _name_cand(data, "14_SYNZZ_1MKOH_0V_095")
    assert first["value"] == 0.0 and "possibly" not in first["state_basis"]["not_proposable_reason"]
    assert "confirms the reading" in first["state_basis"]["not_proposable_reason"]
    # the copy's name writes another number than the line: the name offers nothing either
    assert _name_cand(data, "15_SYNZZ_1MKOH_m600mV_096")["value"] is None
    reason = copy["state_basis"]["not_proposable_reason"]
    assert len(_flags(data, "15_SYNZZ_1MKOH_m600mV_096")) == 1
    assert "possibly left over" in reason and "14_SYNZZ_1MKOH_0V_095" in reason and "m600mV" in reason
    assert "mentions a potential" in reason  # and still what it said before: the value is asked
    assert "neither is preferred" in reason and "fresher" not in reason


def test_the_note_prefers_neither_the_line_nor_the_name(bundle):
    reason = _cand(bundle, "13_SYNZZ_1MSYN_m150mV_041", SETPOINT)["state_basis"]["not_proposable_reason"]
    assert "both shown" in reason and "neither is preferred" in reason and "fresher" not in reason


def test_what_is_not_stale_is_read_as_before(bundle):
    for stem, volts in (("15_SYNZZ_1MSYN_m300mV_043", -0.3), ("16_SYNZZ_1MSYN_m600mV_044", -0.6), ("17_SYNZZ_dry_045", -0.6)):
        assert _flags(bundle, stem) == []
        assert _cand(bundle, stem, SETPOINT)["value"] == volts and _cand(bundle, stem, SCALE)["value"] == "RHE"


def test_acquisition_order_is_the_scans_own_times_not_the_names(tmp_path, capsys):
    """The run whose name sorts LAST was acquired FIRST: its line is the original, the other run's is the copy."""
    src = tmp_path / "src" / "SYN_BL43_2100-17_ZZ"
    make_scan(src / "20_SYNZZ_m150mV_051_A.001", timestamp=_stamp(30), free_text=("1x1 mm", PLAIN))
    make_scan(src / "21_SYNZZ_m300mV_052_A.001", timestamp=_stamp(5), free_text=("1x1 mm", PLAIN))
    assert cli.main(["import", str(src), "--out", str(tmp_path / "out")]) == 0
    capsys.readouterr()
    data = json.loads((tmp_path / "out" / "bundle.json").read_text())
    assert _flags(data, "21_SYNZZ_m300mV_052") == [] and len(_flags(data, "20_SYNZZ_m150mV_051")) == 1
    assert _cand(data, "21_SYNZZ_m300mV_052", SETPOINT)["value"] == -0.3
    assert _cand(data, "20_SYNZZ_m150mV_051", SETPOINT)["value"] is None


def test_an_ai_reading_of_a_flagged_line_is_loaded_as_inferred_never_stated(bundle):
    stem = "13_SYNZZ_1MSYN_m150mV_041"
    findings = {"format": S.READINGS_FORMAT, "findings": [
        {"field_path": SETPOINT, "value": -0.3, "strength": "stated", "quote": PLAIN, "reasoning": "the comment line",
         "source": {"path": f"{stem}_A.001", "locator": "line 11"}, "applies_to": {"scope": "runs", "runs": [stem]}},
        {"field_path": SETPOINT, "value": -0.3, "strength": "stated", "quote": PLAIN, "reasoning": "the comment line",
         "source": {"path": "12_SYNZZ_1MSYN_m300mV_040_A.001", "locator": "line 11"},
         "applies_to": {"scope": "runs", "runs": ["12_SYNZZ_1MSYN_m300mV_040"]}},
    ]}
    plan = S.readings_to_interpretations(bundle, findings, model_id="syn-model")
    stale = [f for _t, f in plan["planned"] if f["source_path"].startswith(stem)]
    fresh = [f for _t, f in plan["planned"] if f["source_path"].startswith("12_")]
    assert stale and all(f["strength"] == "inferred" and "possibly stale" in f["rationale"] for f in stale)
    assert fresh and all(f["strength"] == "stated" and "possibly stale" not in f["rationale"] for f in fresh)
