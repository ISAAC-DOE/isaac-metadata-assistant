"""The technique, suggested from the instrument configuration (audit of 18 Nov 2026, rule 7).

What these pin (``suggestions.TECHNIQUE_RULE_ID``):

* an emission motor held on an emission line of the element whose absorption edge the energy scan crosses suggests
  ``HERFD-XAS`` for the beamtime: ONE candidate that NEEDS REVIEW, citing the header line that holds the motor and
  the tabulated line and edge (``readers.xray_tables``, a snapshot of xraydb);
* an SSRL XDC run's own experiment file stating ``EXPT_TYPE: XAS`` suggests ``XAS`` the same way;
* a macro's, a script's or a function's NAME is not a technique reading where the instrument states the technique:
  those candidates stop asking for the technique of each run (they stay as evidence), so the technique is asked once;
* an emission energy that is no line of the scanned element, or no emission motor at all, suggests nothing, and
  the macro names keep the place they had;
* ONE suggestion never swallows a run that states something else: a run whose emission motor is held OFF the line
  during its energy scan blocks the beamtime value, is named, and keeps its own technique question (the macro names
  keep targeting the technique whenever the suggestion has no value); runs that record nothing about it (no emission
  motor, no experiment file: processed or averaged files) are counted apart and named in the reason;
* runs whose configurations suggest different techniques give no value: both are shown, and the reason points only
  at the question it sits on;
* nothing is confirmed and every bundle is schema-valid (the table itself: test_local_import_xray_tables.py).

SYNTHETIC files only: invented names and counts; the only real numbers are tabulated X-ray line and edge energies.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import suggestions as S
from isaac_api.local_import.readers import xray_tables as X

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_e2e_import_questions import xdc  # noqa: E402
from test_local_import_quick_merges import FIX, SPEC_STEM  # noqa: E402

TECHNIQUE = "system.technique"
#: a synthetic HERFD beamtime at another element than any real one imported: copper K edge, K-alpha-1 line
EDGE = X.edge_energy("Cu", "K")
LINE = X.tables()["lines"]["Cu"]["Ka1"][0]


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


def spec_run(root: Path, stem: str, *, emission: float | None = LINE, edge: float = EDGE, motor: str = "emiss") -> None:
    """The committed synthetic SPEC acquisition under another name, its energy scan moved to cross ``edge`` and its
    emission motor (column 3 of ``#O0`` / ``#P0``) held at ``emission`` (``None``: the fixture's own invented 1050)."""
    spec = (FIX / "spec" / SPEC_STEM).read_text().replace(SPEC_STEM, stem)
    scan = (FIX / "scans" / f"{SPEC_STEM}_001.dat").read_text().replace(SPEC_STEM, stem)
    grid = f"gscan energy {edge - 30:g} {edge - 10:g} 5 {edge + 10:g} 1 {edge + 70:g} 2"
    assert "gscan energy 1000 1020 5 1040 1 1100 2" in spec
    spec = spec.replace("gscan energy 1000 1020 5 1040 1 1100 2", grid).replace("     emiss ", f" {motor:>9} ")
    scan = scan.replace("gscan energy 1000 1020 5 1040 1 1100 2", grid).replace("emiss=", f"{motor}=")
    if emission is not None:
        assert "#P0 4 1000.5 1050 10" in spec
        spec = spec.replace("#P0 4 1000.5 1050 10", f"#P0 4 {edge - 29.5:g} {emission:g} 10")
        scan = scan.replace(f"{motor}=1050", f"{motor}={emission:g}")
    (root / f"{stem}_dir").mkdir(parents=True)
    (root / stem).write_text(spec)
    (root / f"{stem}_dir" / stem).write_text(spec)
    (root / f"{stem}_dir" / f"{stem}_001.dat").write_text(scan)


def macros(root: Path, stems) -> None:
    """A run macro that includes the method macro and declares each run, as a beamtime folder has."""
    shutil.copyfile(FIX / "macros" / "Ir_XAS.mac", root / "Ir_XAS.mac")
    body = ["qdo Ir_XAS.mac", ""]
    for stem in stems:
        body += [f"newfile {stem}", "", "IrL3_xas 0.5      2 \t\t  1050       10", "trigger", ""]
    (root / "run1.mac").write_text("\n".join(body))


def _import(src: Path, out: Path, capsys, group: bool = True) -> dict:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    if group:
        assert cli.main(["bundle", "group", str(out)]) == 0
    capsys.readouterr()
    data = M.load(out)
    assert B.validate_bundle(data) == []
    return data


def _suggested(data: dict) -> list[dict]:
    return [c for c in data["candidates"] if B._rule_id(c["rule"]) == S.TECHNIQUE_RULE_ID]


STEMS = ("11_01_SYN_filter10_100mV", "12_01_SYN_filter10_200mV", "13_02_SYN_filter10_300mV")


@pytest.fixture()
def herfd(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL00_2100-04_ZZ"
    for stem in STEMS:
        spec_run(src, stem)
    macros(src, STEMS)
    return _import(src, tmp_path / "out", capsys), tmp_path / "out"


def test_an_emission_motor_on_a_line_of_the_scanned_edge_suggests_herfd(herfd):
    data, _ = herfd
    [c] = _suggested(data)
    assert (c["value"], c["run_id"], c["scope"], c["target_field_path"]) == ("HERFD-XAS", None, "beamtime", TECHNIQUE)
    # 1.18.0 (DEC-96): this build's instrument-configuration rule counts as isaac.fill.parser_exact.v1: FILLED and
    # eligible (no longer needs_review and ineligible: exactly the policy DEC-96 replaces); still held as a suggestion
    # by the readers (extracted_state), and any decision wins
    assert c["extracted_state"] == B.STATE_NEEDS_REVIEW
    assert c["value_state"] == B.STATE_FILLED and c["eligibility_for_official_record"]["eligible"]
    assert c["fill"] == {"rule_id": B.FILL_PARSER_EXACT_RULE_ID, "value": "HERFD-XAS"}
    assert B.value_problem(TECHNIQUE, c["value"]) is None  # one of the schema's own techniques
    reason = c["state_basis"]["not_proposable_reason"]
    assert f"{LINE:g} eV" in reason and "Cu Ka1" in reason and "Cu K absorption edge" in reason
    assert "3 of the 3 measurement runs that record it" in reason and X.source() in reason
    assert "other measurement run" not in reason  # every run records it: nothing to count apart
    assert "never from a macro" in reason
    first = c["evidence"][0]
    assert first["relation"] == "supports" and first["literal_value"] == f"{LINE:g}"
    assert "#P0" in first["locator"] and "emiss" in first["locator"]  # the header line that holds the motor
    assert first["normalization"][-1] == {"step": "derive", "rule_id": S.TECHNIQUE_RULE_ID, "from": f"{LINE:g}",
                                          "to": "HERFD-XAS", "unit": None}
    assert any("gscan energy" in str(e["literal_value"]) for e in c["evidence"])  # and the scan it was held during


def test_macro_names_stop_asking_for_the_technique_where_the_instrument_states_it(herfd):
    data, _ = herfd
    named = [c for c in data["candidates"] if c["statement_key"] == "acquisition_method"]
    assert named and all(c["target_field_path"] is None for c in named)  # kept as evidence, no longer a technique reading
    assert all(S.NOT_A_TECHNIQUE_REASON in c["state_basis"]["not_proposable_reason"] for c in named)
    assert {lit for c in named for lit in c["observed_literals"]} >= {"Ir_XAS.mac"}
    payload = Q.consolidate(data)
    # 1.18.0 (DEC-96): the suggestion is FILLED, so it is no longer asked; it stays addressable among the answered,
    # one beamtime question, with the instrument's technique in its text
    assert not [q for q in payload["questions"] if q.get("target_field_path") == TECHNIQUE]
    asked = [q for q in Q.consolidate(data, include_answered=True)["questions"] if q.get("target_field_path") == TECHNIQUE]
    assert len(asked) == 1 and asked[0]["scope"] == "experiment" and asked[0]["kind"] == "confirm_value"
    assert "HERFD-XAS" in asked[0]["text"]
    assert not [m for m in data["missing_values"] if m["target_field_path"] == TECHNIQUE]


def test_confirming_the_suggestion_is_one_decision_for_the_beamtime(herfd):
    data, out = herfd
    [c] = _suggested(data)
    M.decide(out, target_ids=[c["candidate_id"]], decision="confirm", value=None, by="SYN Scientist", orcid=None)
    after = M.load(out)
    assert B.validate_bundle(after) == []
    [done] = _suggested(after)
    assert done["value_state"] == B.STATE_SCIENTIST_CONFIRMED and done["eligibility_for_official_record"]["eligible"]


def test_an_emission_energy_that_is_no_line_of_the_scanned_element_suggests_nothing(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL00_2100-05_ZZ"
    spec_run(src, STEMS[0], emission=LINE + 40)       # 40 eV off the line
    spec_run(src, STEMS[1], emission=None)            # the fixture's invented 1050: no line at all
    spec_run(src, STEMS[2], edge=EDGE + 3000)         # the line is right, but the scan crosses no edge of that element
    macros(src, STEMS)
    data = _import(src, tmp_path / "out", capsys)
    assert _suggested(data) == []
    named = [c for c in data["candidates"] if c["statement_key"] == "acquisition_method" and c["run_id"]]
    assert named and all(c["target_field_path"] == TECHNIQUE for c in named)  # as before: the macro names keep their place


def test_a_run_held_off_the_line_blocks_the_beamtime_value_and_keeps_its_question(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL00_2100-18_ZZ"
    spec_run(src, STEMS[0])                          # on the line
    spec_run(src, STEMS[1], emission=LINE + 40)      # the motor is there, 40 eV off: it states something else
    spec_run(src, STEMS[2], emission=LINE + 40)
    macros(src, STEMS)
    data = _import(src, tmp_path / "out", capsys)
    [c] = _suggested(data)
    assert c["value"] is None and c["value_state"] == B.STATE_NEEDS_REVIEW
    reason = c["state_basis"]["not_proposable_reason"]
    assert "No technique is offered for the beamtime" in reason and "1 of the 3 measurement runs that record it" in reason
    assert STEMS[1] in reason and STEMS[2] in reason and f"{LINE + 40:g} eV" in reason  # the runs it does not rest on
    assert "of each record group" not in reason
    # nothing is swallowed: every run's macro-name candidate still asks for the technique, as before
    named = [c for c in data["candidates"] if c["statement_key"] == "acquisition_method" and c["run_id"]]
    assert len(named) == 3 and all(c["target_field_path"] == TECHNIQUE for c in named)
    groups = {q["scope"] for q in Q.consolidate(data)["questions"]
              if q.get("target_field_path") == TECHNIQUE and q["scope"].startswith("group:")}
    assert len(groups) == 3


def test_runs_that_record_nothing_are_counted_apart_and_named(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL00_2100-19_ZZ"
    spec_run(src, STEMS[0])
    spec_run(src, STEMS[1])
    spec_run(src, STEMS[2], motor="synmot")          # no emission motor at all (as an averaged or processed file)
    data = _import(src, tmp_path / "out", capsys)
    [c] = _suggested(data)
    assert c["value"] == "HERFD-XAS"
    reason = c["state_basis"]["not_proposable_reason"]
    assert "2 of the 2 measurement runs that record it" in reason
    assert "1 other measurement run records nothing about the technique" in reason and STEMS[2] in reason
    assert "does not rest on" in reason


def test_no_emission_motor_suggests_nothing(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL00_2100-06_ZZ"
    spec_run(src, STEMS[0], motor="synmot")
    assert _suggested(_import(src, tmp_path / "out", capsys)) == []


def test_runs_that_suggest_different_techniques_give_no_value_and_show_both(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL43_2100-07_ZZ"
    spec_run(src, STEMS[0])
    macros(src, STEMS[:1])
    xdc(src / "21_SYNZZ_dry_040_A.001")
    (src / "21_SYNZZ_dry_040.exp").write_text("ID:\t\tSYN_EXPT\nEXPT_TYPE:\tXAS\nDATA_FILE:\t21_SYNZZ_dry\n")
    data = _import(src, tmp_path / "out", capsys)
    [c] = _suggested(data)
    assert c["value"] is None and c["value_state"] == B.STATE_NEEDS_REVIEW
    reason = c["state_basis"]["not_proposable_reason"]
    assert "HERFD-XAS (1 run" in reason and "XAS (1 run" in reason and "No technique is offered for the beamtime" in reason
    # the reason points at no question that does not exist: it is answered where it stands, per group where they differ
    assert "of each record group" not in reason and "this question" in reason
    # and with no value nothing is taken from the macro names: the run's own candidate still asks
    named = [x for x in data["candidates"] if x["statement_key"] == "acquisition_method" and x["run_id"]]
    assert named and all(x["target_field_path"] == TECHNIQUE for x in named)


# --- SSRL XDC: the experiment file's EXPT_TYPE -----------------------------------------------------------------------


def _xdc_beamtime(src: Path, expt_type: str = "XAS") -> Path:
    for stem in ("03_SYNZZ_1x1mm_081", "04_SYNZZ_dry_082"):
        xdc(src / f"{stem}_A.001")
        # the run's own experiment file, in a folder of the run's name, under a reused template name
        (src / stem).mkdir(parents=True)
        (src / stem / "SYNtemplate_exp1.exp").write_text(
            f"ID:\t\tSYN_EXPT\nEXPT_TYPE:\t{expt_type}\nCOMMENTS1:\t\"SYN\"\nDATA_FILE:\t{stem.rsplit('_', 1)[0]}\n")
    xdc(src / "05_SYNZZ_wet_083_A.001")  # no experiment file: states nothing
    return src


def test_an_experiment_file_stating_xas_suggests_xas(tmp_path, capsys):
    data = _import(_xdc_beamtime(tmp_path / "src" / "SYN_BL43_2100-08_ZZ"), tmp_path / "out", capsys)
    [c] = _suggested(data)
    assert (c["value"], c["run_id"]) == ("XAS", None) and c["value_state"] == B.STATE_FILLED  # 1.18.0 (DEC-96)
    reason = c["state_basis"]["not_proposable_reason"]
    assert "EXPT_TYPE" in reason and "2 of the 2 measurement runs that record it" in reason
    assert "1 other measurement run records nothing about the technique" in reason and "05_SYNZZ_wet_083" in reason
    first = c["evidence"][0]
    assert (first["literal_value"], first["locator"]) == ("XAS", "line:2") and first["relative_path"].endswith(".exp")
    assert not [m for m in data["missing_values"] if m["target_field_path"] == TECHNIQUE]
    # 1.18.0 (DEC-96): filled, so not asked (no longer "one confirmation"); still found among the answered
    assert not [q for q in Q.consolidate(data)["questions"] if q.get("target_field_path") == TECHNIQUE]
    [asked] = [q for q in Q.consolidate(data, include_answered=True)["questions"] if q.get("target_field_path") == TECHNIQUE]
    assert asked["kind"] == "confirm_value"


def test_an_experiment_file_stating_another_word_blocks_the_value(tmp_path, capsys):
    src = _xdc_beamtime(tmp_path / "src" / "SYN_BL43_2100-20_ZZ")
    (src / "04_SYNZZ_dry_082" / "SYNtemplate_exp1.exp").write_text("EXPT_TYPE:\tSYNSCAN\nDATA_FILE:\t04_SYNZZ_dry\n")
    data = _import(src, tmp_path / "out", capsys)
    [c] = _suggested(data)
    reason = c["state_basis"]["not_proposable_reason"]
    assert c["value"] is None and "SYNSCAN" in reason and "04_SYNZZ_dry_082" in reason


def test_an_experiment_type_that_is_no_schema_technique_suggests_nothing(tmp_path, capsys):
    data = _import(_xdc_beamtime(tmp_path / "src" / "SYN_BL43_2100-09_ZZ", "SYNSCAN"), tmp_path / "out", capsys)
    assert _suggested(data) == []
    assert [m for m in data["missing_values"] if m["target_field_path"] == TECHNIQUE]  # asked as before
    # the literal is kept as what the file says
    assert [e for e in data["extended_context"] if e["concept"] == "exp_expt_type" and e["raw_literal"] == "SYNSCAN"]


# --- the lookup the suggestion uses (the table itself: test_local_import_xray_tables.py) ---------------------------


def test_the_lookup_reads_a_line_and_the_edge_it_fills():
    [hit] = [h for h in X.lines_near(LINE) if h["element"] == "Cu"]
    assert (hit["line"], hit["edge"]) == ("Ka1", "K") and X.edge_energy("Cu", hit["edge"]) == EDGE
    assert X.lines_near(LINE + 40) == [] or all(h["element"] != "Cu" for h in X.lines_near(LINE + 40))
    assert {"element": "Cu", "edge": "K", "energy_eV": EDGE} in X.edges_between(EDGE - 30, EDGE + 70)
    assert "xraydb" in X.source() and "Elam" in X.source()
