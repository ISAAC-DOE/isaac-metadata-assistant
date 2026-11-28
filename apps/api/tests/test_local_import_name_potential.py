"""The potential a run's NAME states, as a suggestion (audit of 18 Nov 2026, rule 10).

What these pin:

* an SSRL XDC run's name was never read for a potential: its last potential token is now a candidate that NEEDS
  REVIEW (``suggestions.NAME_POTENTIAL_RULE_ID``), negative when written ``m…`` or ``-…``;
* a comment line of the same run that writes the same potential confirms the reading, and says so; one that writes
  a DIFFERENT potential is shown beside it and neither is offered (the comment line's own candidate loses its value
  too);
* ``OCV`` suggests the control mode ``open_circuit`` and no set-point; two levels marked ``Pos`` / ``Neg`` are a
  pulsed step and no set-point is offered;
* a SPEC run's negative token is read by the engine's token reader (one candidate, not two);
* nothing is confirmed; nothing is eligible but (1.22.0, DEC-100 fix round) a SPEC run's one signed name token, which
  fills its set-point, and an open-circuit token, which fills the control mode, both yellow deductions; every bundle is
  schema-valid, and the candidates that existed keep their ids.

SYNTHETIC files only: every name, line and value below is invented.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R
from isaac_api.local_import import suggestions as S

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_e2e_import_questions import xdc  # noqa: E402
from test_local_import_quick_merges import _spec_run  # noqa: E402

SETPOINT = "context.electrochemistry.potential_setpoint_V"
MODE = "context.electrochemistry.control_mode"


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


XDC_RUNS = {
    # name                                  comment lines
    "07_SYNZZ_100mMSYN_m300mV_023": ("1x1mm", "100mM SYNsalt", "-0.3 V vs RHE"),   # the pair that confirms the sign
    "08_SYNZZ_100mMSYN_m150mV_024": ("1x1mm", "SYN sample line"),                  # the name alone
    "09_SYNZZ_100mMSYN_m450mV_025": ("1x1mm", "-0.2 V vs RHE"),                    # the comment writes another value
    "10_SYNZZ_100mMSYN_OCV_026": ("1x1mm", "SYN sample line"),
    "11_SYNZZ_1200mVPos_m400mVNeg_027": ("1x1mm", "SYN sample line"),
    "12_SYNZZ_100mMSYN_500mV_028": ("1x1mm", "SYN sample in 1M SYN 0.5Vrhe"),      # a mention the comment rule reads no value from
    "13_SYNZZ_dry_029": ("1x1mm", "SYN sample line"),
    "14_SYNZZ_100mMSYN_m0V_030": ("1x1mm", "SYN sample in 1M SYN 0V vs RHE"),
    "15_SYNZZ_OCV_3_m500mV_031": ("1x1mm", "SYN sample line"),                     # open circuit, THEN a held potential
    "16_SYNZZ_800V_032": ("1x1mm", "SYN sample line"),                             # too large to be an electrode potential
}


def _import(src: Path, out: Path, capsys) -> dict:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    capsys.readouterr()
    data = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(data) == []
    return data


@pytest.fixture()
def bl43(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL43_2099-02_ZZ"
    for stem, lines in XDC_RUNS.items():
        xdc(src / f"{stem}_A.001", free_text=lines)
    return _import(src, tmp_path / "out", capsys), tmp_path / "out"


def _of(data: dict, stem: str, path: str, key: str | None = None) -> list[dict]:
    rid = next(r["run_id"] for r in data["runs"] if r["stem"] == stem)
    return [c for c in data["candidates"] if c["run_id"] == rid and c["target_field_path"] == path
            and (key is None or c["statement_key"] == key)]


def _name(data: dict, stem: str) -> dict:
    [c] = _of(data, stem, SETPOINT, S.NAME_POTENTIAL_KEY)
    return c


def test_a_name_potential_is_a_suggestion_that_needs_review(bl43):
    data, _ = bl43
    for stem, volts in (("07_SYNZZ_100mMSYN_m300mV_023", -0.3), ("08_SYNZZ_100mMSYN_m150mV_024", -0.15),
                        ("12_SYNZZ_100mMSYN_500mV_028", 0.5), ("14_SYNZZ_100mMSYN_m0V_030", 0.0),
                        ("15_SYNZZ_OCV_3_m500mV_031", -0.5)):
        c = _name(data, stem)
        assert c["value"] == volts and str(c["value"]) != "-0.0"
        assert c["value_state"] == B.STATE_NEEDS_REVIEW and not c["eligibility_for_official_record"]["eligible"]
        assert c["rule"].startswith(S.NAME_POTENTIAL_RULE_ID) and c["state_basis"]["proposable"] is False
        first = c["evidence"][0]
        assert first["relation"] == "supports" and first["locator"].startswith("filename token ")
        index = int(first["locator"].split()[2])
        assert stem.split("_")[index] == first["literal_value"]  # the locator names the token it read
        assert first["normalization"][0]["to"] == volts and first["normalization"][0]["unit"] == "V"
        run = next(r for r in data["runs"] if r["stem"] == stem)
        assert c["candidate_id"] in run["candidate_ids"]
        assert not [m for m in data["missing_values"] if m["run_id"] == run["run_id"] and m["target_field_path"] == SETPOINT]
    assert "minus sign" in _name(data, "08_SYNZZ_100mMSYN_m150mV_024")["state_basis"]["not_proposable_reason"]


def test_a_comment_line_with_the_same_potential_confirms_the_reading(bl43):
    data, _ = bl43
    c = _name(data, "07_SYNZZ_100mMSYN_m300mV_023")
    reason = c["state_basis"]["not_proposable_reason"]
    assert "'-0.3 V vs RHE'" in reason and "confirms the reading" in reason
    assert [e["literal_value"] for e in c["evidence"] if e["relation"] == "context"] == ["-0.3 V vs RHE"]
    # the comment line's own candidate is untouched: it keeps the value it read
    [line] = _of(data, "07_SYNZZ_100mMSYN_m300mV_023", SETPOINT, "scan_header_potential")
    assert line["value"] == -0.3
    # a mention the comment rule reads no value from still confirms the name (0.5Vrhe beside 500mV), and gives no
    # second, value-less candidate asking for the same number: the line is evidence on the name's candidate
    mention = _name(data, "12_SYNZZ_100mMSYN_500mV_028")
    assert "confirms the reading" in mention["state_basis"]["not_proposable_reason"]
    assert _of(data, "12_SYNZZ_100mMSYN_500mV_028", SETPOINT) == [mention]
    assert [e["literal_value"] for e in mention["evidence"][1:]] == ["SYN sample in 1M SYN 0.5Vrhe"]
    # and the pair is what a run with no comment of its own cites for the sign
    alone = _name(data, "08_SYNZZ_100mMSYN_m150mV_024")["state_basis"]["not_proposable_reason"]
    assert "1 run(s) write the same sign both ways" in alone and "m300mV" in alone and "'-0.3 V vs RHE'" in alone


def test_a_name_and_a_comment_that_differ_are_both_shown_and_neither_is_offered(bl43):
    data, _ = bl43
    name = _name(data, "09_SYNZZ_100mMSYN_m450mV_025")
    [line] = _of(data, "09_SYNZZ_100mMSYN_m450mV_025", SETPOINT, "scan_header_potential")
    for c in (name, line):
        assert c["value"] is None and c["value_state"] == B.STATE_NEEDS_REVIEW
        reason = c["state_basis"]["not_proposable_reason"]
        assert "m450mV (-0.45 V)" in reason and "'-0.2 V vs RHE'" in reason and "neither is offered" in reason
        assert all(e["relation"] == "context" for e in c["evidence"])
    assert name["state_basis"]["not_proposable_reason"] == line["state_basis"]["not_proposable_reason"]


def test_open_circuit_suggests_the_control_mode_and_no_set_point(bl43):
    data, _ = bl43
    stem = "10_SYNZZ_100mMSYN_OCV_026"
    assert _of(data, stem, SETPOINT) == []
    [c] = _of(data, stem, MODE)
    assert c["value"] == "open_circuit" and c["statement_key"] == S.OPEN_CIRCUIT_KEY
    # inverted at 1.22.0 (DEC-100 fix round, R1a): the build's own open-circuit suggestion now FILLS the mode, as a
    # yellow deduction (isaac.fill.control_mode_from_setpoint.v1), never green
    assert c["rule"].startswith(S.OPEN_CIRCUIT_RULE_ID)
    assert c["value_state"] == B.STATE_FILLED and c["fill"] == {"rule_id": B.FILL_CONTROL_MODE_RULE_ID,
                                                                 "value": "open_circuit"}
    assert B.value_colour(c["value_state"], c["fill"]["rule_id"]) == B.COLOUR_YELLOW
    assert c["evidence"][0]["literal_value"] == "OCV" and "no set-point applies" in c["state_basis"]["not_proposable_reason"]
    assert B.value_problem(MODE, c["value"]) is None  # one of the schema's own control modes
    # open circuit followed by a held potential: the potential is the condition, not open circuit
    assert _of(data, "15_SYNZZ_OCV_3_m500mV_031", MODE) == []


def test_a_pulsed_name_offers_no_set_point_and_says_the_levels(bl43):
    data, _ = bl43
    c = _name(data, "11_SYNZZ_1200mVPos_m400mVNeg_027")
    assert c["value"] is None and c["observed_literals"] == ["1200mVPos", "m400mVNeg"]
    reason = c["state_basis"]["not_proposable_reason"]
    assert "pulsed step" in reason and "1200mVPos (1.2 V)" in reason and "m400mVNeg (-0.4 V)" in reason


def test_no_potential_in_the_name_and_an_implausible_one(bl43):
    data, _ = bl43
    assert _of(data, "13_SYNZZ_dry_029", SETPOINT) == [] and _of(data, "13_SYNZZ_dry_029", MODE) == []
    big = _name(data, "16_SYNZZ_800V_032")
    assert big["value"] is None and "larger than an electrode potential" in big["state_basis"]["not_proposable_reason"]


def test_the_candidates_that_existed_keep_their_ids(bl43):
    data, _ = bl43
    ids = [c["candidate_id"] for c in data["candidates"]]
    assert ids == [f"cand-{i:04d}" for i in range(1, len(ids) + 1)]
    new = [i for i, c in enumerate(data["candidates"])
           if B._rule_id(c["rule"]) in (S.NAME_POTENTIAL_RULE_ID, S.OPEN_CIRCUIT_RULE_ID)]
    assert new == list(range(len(ids) - len(new), len(ids)))  # after every start-time and comment candidate


def test_the_stated_potential_warning_names_the_token_once_with_what_it_reads_as(bl43, capsys):
    data, out = bl43
    assert cli.main(["bundle", "group", str(out)]) == 0
    capsys.readouterr()
    data = M.load(out)
    rid = next(r["run_id"] for r in data["runs"] if r["stem"] == "08_SYNZZ_100mMSYN_m150mV_024")
    stated = R._stated_potentials(data, {rid})
    assert [(s["literal"], s["read_as_V"]) for s in stated] == [("m150mV", -0.15)]
    assert stated[0]["candidate_id"] == _name(data, "08_SYNZZ_100mMSYN_m150mV_024")["candidate_id"]


def test_confirming_a_name_potential_is_one_decision(bl43):
    data, out = bl43
    c = _name(data, "08_SYNZZ_100mMSYN_m150mV_024")
    M.decide(out, target_ids=[c["candidate_id"]], decision="confirm", value=None, by="SYN Scientist", orcid=None)
    after = M.load(out)
    assert B.validate_bundle(after) == []
    done = next(x for x in after["candidates"] if x["candidate_id"] == c["candidate_id"])
    assert done["value_state"] == B.STATE_SCIENTIST_CONFIRMED and done["value"] == -0.15


# --- SPEC runs: the engine's token reader reads the sign; open circuit and a pulse are said here ---------------------


@pytest.fixture()
def spec(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL00_2100-03_ZZ"
    for stem in ("21_01_SYN_m800mV", "22_01_SYN_850mV", "23_01_SYN_OCV", "24_01_SYN_1200mVPos_m400mVNeg",
                 "25_01_SYN_OCV_m1000mV"):
        _spec_run(src, stem)
    return _import(src, tmp_path / "out", capsys)


def test_a_spec_run_at_a_negative_potential_has_one_candidate_with_its_sign(spec):
    for stem, volts in (("21_01_SYN_m800mV", -0.8), ("22_01_SYN_850mV", 0.85), ("25_01_SYN_OCV_m1000mV", -1.0)):
        [c] = _of(spec, stem, SETPOINT)
        assert c["value"] == volts and c["statement_key"] == "potential_magnitude"
        assert B._rule_id(c["rule"]) != S.NAME_POTENTIAL_RULE_ID  # the engine's own candidate, not a second one
        # inverted at 1.22.0 (DEC-100 fix round, R2): the one signed token of the run's own name FILLS the set-point, a
        # yellow deduction (isaac.fill.setpoint_from_file_name.v1), its sign kept
        assert c["value_state"] == B.STATE_FILLED and c["fill"] == {"rule_id": B.FILL_SETPOINT_NAME_RULE_ID, "value": volts}


def test_a_spec_run_at_open_circuit_or_pulsed_says_so(spec):
    [mode] = _of(spec, "23_01_SYN_OCV", MODE)
    assert mode["value"] == "open_circuit" and _of(spec, "23_01_SYN_OCV", SETPOINT) == []
    assert _of(spec, "25_01_SYN_OCV_m1000mV", MODE) == []
    [pulsed] = _of(spec, "24_01_SYN_1200mVPos_m400mVNeg", SETPOINT)
    assert pulsed["value"] is None and "pulsed step" in pulsed["state_basis"]["not_proposable_reason"]


# --- ids: what the build before gave stands --------------------------------------------------------------------------


def test_every_id_the_build_before_gave_names_what_it_named(tmp_path, capsys, monkeypatch):
    """A re-import by this build against one by a build without the name rule (the rule switched off): every candidate
    id names the same (run, field, key) or is the comment line the name now answers (same id, no field), every value
    id the same (run, field), and the name's candidates are numbered after every other."""
    src = tmp_path / "src" / "SYN_BL43_2099-02_ZZ"
    for stem, lines in XDC_RUNS.items():
        xdc(src / f"{stem}_A.001", free_text=lines)
    now = _import(src, tmp_path / "now", capsys)
    with monkeypatch.context() as mp:
        mp.setattr(S, "name_potential_candidates", lambda *a, **k: [])
        before = _import(src, tmp_path / "before", capsys)
    stem = {r["run_id"]: r["stem"] for r in now["runs"]}
    assert stem == {r["run_id"]: r["stem"] for r in before["runs"]}
    got = {c["candidate_id"]: c for c in now["candidates"]}
    for c in before["candidates"]:
        n = got[c["candidate_id"]]
        assert (n["run_id"], n["statement_key"]) == (c["run_id"], c["statement_key"])
        if n["target_field_path"] != c["target_field_path"]:
            # the one change: a value-less comment line whose run's name now offers the set-point
            assert n["target_field_path"] is None and c["target_field_path"] == SETPOINT and c["value"] is None
            assert n["state_basis"]["not_proposable_reason"] == B.SETPOINT_IN_NAME_REASON
            assert stem[n["run_id"]] in ("12_SYNZZ_100mMSYN_500mV_028", "14_SYNZZ_100mMSYN_m0V_030")
    new = [c for c in now["candidates"] if c["candidate_id"] not in {x["candidate_id"] for x in before["candidates"]}]
    assert new and all(c["rule"].startswith((S.NAME_POTENTIAL_RULE_ID, S.OPEN_CIRCUIT_RULE_ID)) for c in new)
    assert min(int(c["candidate_id"][5:]) for c in new) == len(before["candidates"]) + 1
    was = {m["value_id"]: (m["run_id"], m["target_field_path"]) for m in before["missing_values"]}
    for m in now["missing_values"]:
        assert was.get(m["value_id"]) == (m["run_id"], m["target_field_path"]), m["value_id"]
