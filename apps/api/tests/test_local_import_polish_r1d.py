"""r1d: the scan-header comment rule reads a value ONLY from a line written in a plain form. Synthetic only (invented
lines, SYN names).

Several rounds of patching a reader of free text (rule ``ssrl_xdc_header_comment_v1``) still left realistic comment
lines read as confidently wrong values: ``1e-3 M KCl`` as 3 M, ``0,1 M KOH`` as 1 M, ``pH 1,3`` as 1, ``KOH 1 M
Ar`` as the electrolyte ``Ar``, ``NiFe - 1.55 V vs RHE`` as -1.55 V, ``eta = 300 mV`` / ``step 50 mV`` / ``rest
potential 0.9 V`` / ``Lytle offset 0.2 V`` as set-points, ``scan rate 10 mV.s-1`` as 0.01 V, ``salt bridge 3 M KCl``
as the electrolyte, ``pH 6.8-7.2`` as 6.8, ``1 000 mV`` as 0 V.

What these pin: the rule is a WHITELIST. A line is split into segments (``,`` ``;`` ``|``, two or more spaces); a value
is offered only where a whole segment is one strict statement (a set-point, a pH, an electrolyte) and nothing else in
the line makes it doubtful. Every probe line gives the right value or none — never a wrong one. A line that only
mentions a field gives a candidate with NO value that quotes the line and asks the scientist, answered with
``correct``. The template reads the same grammar (electrolyte statements, header set-points), so the two never
disagree.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import template as T

from test_local_import_reader_ssrl_xdc import make_scan

WHO = "SYNTHETIC TEST"
NAME, CONC, PH = ("context.electrochemistry.electrolyte.name", "context.electrochemistry.electrolyte.concentration_M",
                  "context.electrochemistry.pH")
SETPOINT, SCALE = "context.electrochemistry.potential_setpoint_V", "context.electrochemistry.potential_scale"
SHORT = {SETPOINT: "E", SCALE: "scale", PH: "pH", NAME: "name", CONC: "conc"}


def _offered(line: str) -> dict:
    return {SHORT[r["path"]]: r["value"] for r in Q.header_comment_readings(line) if r["value"] is not None}


#: every line of the review's two probe files, with what is offered for it ({} = no value offered)
PROBES = [
    ('Ecell=-0.3V vs RHE', {}),
    ('E = -0.30 V (RHE)', {'E': -0.3, 'scale': 'RHE'}),
    ('-0.3V RHE', {'E': -0.3, 'scale': 'RHE'}),
    ('-300 mV RHE', {'E': -0.3, 'scale': 'RHE'}),
    ('potential -0.3 V vs. RHE, 1600 rpm', {'E': -0.3, 'scale': 'RHE'}),
    ('held at -0.3 V vs RHE for 10 min', {}),
    ('chronoamperometry at -0.3V vs RHE', {}),
    ('-0.3 V vs RHE, iR corrected 85%', {}),
    ('pH 1.3 0.1 M HClO4 -0.3 V vs RHE', {}),
    ('0.1M KOH, -0.3V vs Hg/HgO', {'E': -0.3, 'scale': 'Hg/HgO'}),
    ('1 M KOH + 0.5 M EtOH', {}),
    ('-0.3V vs RHE (step 2 of 5)', {}),
    ('-0.3 V vs RHE @ 25 C', {}),
    ('V = -0.3', {}),
    ('-0.3', {}),
    ('0.3 V', {'E': 0.3}),
    ('+0.3 V vs RHE', {'E': 0.3, 'scale': 'RHE'}),
    ('\u22120.3 V vs RHE', {'E': -0.3, 'scale': 'RHE'}),
    ('-.3 V vs RHE', {'E': -0.3, 'scale': 'RHE'}),
    ('-0.3V vs RHE 10mA', {}),
    ('-0.3V vs RHE then 0.1V', {}),
    ('1.23 V vs RHE (OER)', {}),
    ('0 V vs RHE', {'E': 0.0, 'scale': 'RHE'}),
    ('-0 V', {'E': 0.0}),
    ('1e-3 M KCl', {}),
    ('100mM NaClO4 pH1.3 He', {}),
    ('0.5M H2SO4 sat. Ar', {}),
    ('50 mM phosphate buffer pH 7', {}),
    ('1x10-3 M KCl', {}),
    ('1E-2M HClO4', {}),
    ('5*10^-3 M CuSO4', {}),
    ('0,1 M KOH', {}),
    ('0,5M H2SO4 -0,3 V vs RHE', {}),
    ('KOH 1 M Ar', {}),
    ('HClO4 0.1M He', {}),
    ('NaClO4 100 mM N2', {}),
    ('H2SO4 0.5 M Cu', {}),
    ('KOH 1M OER', {}),
    ('salt bridge 3 M KCl', {}),
    ('RE: 3.5 M KCl, -0.4 V', {}),
    ('double junction 3M KCl', {}),
    ('1 M MeOH', {}),
    ('2 mM CuSO4', {'name': 'CuSO4', 'conc': 0.002}),
    ('precursor 0.2 M Ni(NO3)2', {}),
    ('0.1 M KOH in D2O', {}),
    ('1 M KOH diluted 10x', {}),
    ('0.1 mol/L KOH', {'name': 'KOH', 'conc': 0.1}),
    ('10 \xb5M CuSO4 in 0.1 M HClO4', {}),
    ('pH 1,3', {}),
    ('pH 6.8-7.2', {}),
    ('pH 7 to 10', {}),
    ('pH 13 (0.1 M KOH)', {}),
    ('pH ~7', {}),
    ('pH=12.5', {'pH': 12.5}),
    ('NiFe - 1.55 V vs RHE', {}),
    ('NiOOH \u2013 1.6 V vs RHE', {}),
    ('Sample A - 0.3 V vs RHE', {}),
    ('minus 0.3 V vs RHE', {}),
    ('negative 0.3 V', {}),
    ('(-)0.3 V vs RHE', {}),
    ('eta = 300 mV', {}),
    ('overpotential 0.35 V', {}),
    ('\u03b7=350mV', {}),
    ('\u0394E = 50 mV', {}),
    ('Delta E 10 mV', {}),
    ('potential steps of 100 mV', {}),
    ('step 50 mV', {}),
    ('scan rate 10 mV.s-1', {}),
    ('scan rate 5 mV sec-1', {}),
    ('scan rate 10 mV\xb7s\u207b\xb9', {}),
    ('10 mV per s', {}),
    ('rate 20 mV s\u207b\xb9', {}),
    ('Tafel 40 mV dec-1', {}),
    ('iR drop 20 mV', {}),
    ('rest potential 0.9 V vs RHE', {}),
    ('Eoc = 0.95 V vs RHE', {}),
    ('E_oc 0.9 V', {}),
    ('open-circuit 0.9 V', {}),
    ('galvanostatic 10 mA/cm2, 1.6 V vs RHE', {}),
    ('CP 10 mA cm-2 ~1.6 V vs RHE', {}),
    ('prereduced at -0.5 V vs RHE', {}),
    ('post-OER 1.6V vs RHE', {}),
    ('ex situ, 1.6 V vs RHE 2 h', {}),
    ('activated at 1.6 V vs RHE', {}),
    ('before: 1.2 V vs RHE', {}),
    ('previously -0.5 V', {}),
    ('Lytle offset 0.2 V', {}),
    ('amp bias 1.5 V', {}),
    ('PMT 0.8 kV', {}),
    ('HV 1.5 kV, -0.3 V vs RHE', {}),
    ('detector 900 V', {}),
    ('I0 2 V', {}),
    ('5 \xb5V noise', {}),
    ('-0.3 V vs RHE, 2 kV', {}),
    ('-0.3 V vs RHE / 5 \xb5V', {}),
    ('1 000 mV vs RHE', {}),
    ('0.5 V vs Li/Li+', {'E': 0.5}),
    ('0.5 V vs NHE', {'E': 0.5}),
    ('0.5 V vs MSE', {'E': 0.5}),
    ('-0.3 Vrhe', {}),
    ('-0.3 V_RHE', {}),
    ('-0.3V/RHE', {}),
    ('-0.3V(RHE)', {'E': -0.3, 'scale': 'RHE'}),
    ('E vs RHE = -0.3 V', {}),
    ('-0.3V_RHE', {}),
    ('m300mV', {}),
    ('0p5V_RHE', {}),
    ('-0.3 V vs RHE (-0.5 V vs Ag/AgCl)', {}),
    ('-0.3 V vs RHE, -.5 V vs Ag/AgCl', {}),
    ('-.3 V vs RHE; 0.1 V vs Ag/AgCl', {}),
    ('-0.3 V vs RHE, 5 V', {}),
    ('0.4 V vs RHE (corr.), 0.45 V (uncorr.)', {}),
    ('Ewe -0.3 V Ece 1.2 V', {}),
    ('-0.3V vs RHE, was 0.5V', {}),
    ('0.3 \xb1 0.01 V vs RHE', {}),
    ('0.3 V vs RHE \xb1 10 mV', {}),
    ('1.0-1.6 V vs RHE', {}),
    ('1.0 \u2013 1.6 V vs RHE', {}),
    ('0.3 V \u2013 0.5 V vs RHE', {}),
    ('-0.3 V vs RHE x 3', {}),
    ('-0.3V vs RHE 1600rpm 2019-05-12', {}),
    ('2019-05-12 -0.3 V vs RHE', {}),
    ('-0.3V vs RHE 12:30-13:00', {}),
    ('pH13-0.3V vs RHE', {}),
    ('at-0.3V vs RHE', {}),
    ('E=-0.3V vs RHE', {'E': -0.3, 'scale': 'RHE'}),
    ('E:-0.3 V vs RHE', {'E': -0.3, 'scale': 'RHE'}),
    ('@-0.3V vs RHE', {'E': -0.3, 'scale': 'RHE'}),
    ('~-0.3 V vs RHE', {}),
    ('-0.3 V vs RHE (approx.)', {}),
    ('V K-edge, 2 V vs RHE', {}),
    ('scan 3 V-K edge', {}),
    ('LiNiO2 charged 2.5 V', {}),
    ('0.6 V vs RHE 50 mV amplitude', {}),
    ('0.6V vs RHE, 5 mV steps', {}),
]

#: the review's own examples that are not probe lines above, and what is offered for each
REVIEW_EXAMPLES = [
    ("rest potential 0.9 V", {}), ("prereduced at -0.5 V", {}), ("post-OER 1.6V", {}), ("1 000 mV", {}),
    ("1  000 mV vs RHE", {}), ("-0,3 V vs RHE", {}), ("CV from 0.05 to 1.2 V vs RHE", {}), ("pH 7, 10 mM KCl", {
        "pH": 7.0, "name": "KCl", "conc": 0.01}),
]

POSITIVE = [
    ("-0.3 V vs RHE", {"E": -0.3, "scale": "RHE"}),
    ("E = -0.30 V (RHE)", {"E": -0.3, "scale": "RHE"}),
    ("-300 mV vs RHE", {"E": -0.3, "scale": "RHE"}),
    ("+0.3 V vs RHE", {"E": 0.3, "scale": "RHE"}),
    ("−0.3 V vs RHE", {"E": -0.3, "scale": "RHE"}),
    ("–0.3 V vs RHE", {"E": -0.3, "scale": "RHE"}),  # an en dash written onto its number
    ("-.3 V vs RHE", {"E": -0.3, "scale": "RHE"}),
    ("pH 1.3", {"pH": 1.3}),
    ("0.1 M HClO4", {"name": "HClO4", "conc": 0.1}),
    ("100 mM NaClO4", {"name": "NaClO4", "conc": 0.1}),
    ("KOH 1 M", {"name": "KOH", "conc": 1.0}),
    ("0.1 M HClO4, pH 1.3, -0.3 V vs RHE", {"name": "HClO4", "conc": 0.1, "pH": 1.3, "E": -0.3, "scale": "RHE"}),
    ("-0.3V vs RHE; pH 1.3 | 0.1 M HClO4", {"name": "HClO4", "conc": 0.1, "pH": 1.3, "E": -0.3, "scale": "RHE"}),
    ("0.1 M HClO4   -0.3 V vs RHE", {"name": "HClO4", "conc": 0.1, "E": -0.3, "scale": "RHE"}),  # two spaces split
    ("-1.2 V vs Ag/AgCl", {"E": -1.2, "scale": "Ag/AgCl"}),
    ("0.5 V vs NHE", {"E": 0.5}),  # a scale the record does not take: the set-point only, the scale is asked
    ("1 mM K4Fe(CN)6", {"name": "K4Fe(CN)6", "conc": 0.001}),
]


@pytest.mark.parametrize("line,want", PROBES + REVIEW_EXAMPLES + POSITIVE)
def test_every_line_gives_the_right_value_or_none(line, want):
    assert _offered(line) == want
    for r in Q.header_comment_readings(line):
        assert r["literal"] == line.strip()  # the whole line, what the scientist checks against
        if r["value"] is None:
            assert r["ambiguous"] and r["why"] == Q.HEADER_UNREAD_WHY


@pytest.mark.parametrize("line,asked", [
    ("100mM NaClO4 pH1.3 He", {NAME, CONC, PH}),  # no separators: nothing is a whole segment
    ("eta = 300 mV", {SETPOINT}), ("1e-3 M KCl", {NAME, CONC}), ("pH 6.8-7.2", {PH}), ("KOH 1 M Ar", {NAME, CONC}),
    ("pH 1,3", {PH}), ("scan rate 10 mV.s-1", {SETPOINT}), ("0.1 M HClO4, pH 1.3, -0.3 V vs RHE, 5 V", {SETPOINT}),
])
def test_a_field_a_line_only_mentions_is_asked_with_no_value(line, asked):
    got = {r["path"]: r["value"] for r in Q.header_comment_readings(line)}
    assert {p for p, v in got.items() if v is None} == asked


def test_a_line_that_mentions_nothing_gives_nothing():
    for line in ("1x1 mm beam", "He atmosphere", "V = -0.3", "PMT 0.8 kV", "5 µV noise", "synthetic sample line"):
        assert Q.header_comment_readings(line) == [], line


def test_segments_beside_a_comma_decimal_or_a_digit_group_are_not_read():
    assert Q.comment_segments("pH 1,3") == [("pH 1", False), ("3", False)]
    assert Q.comment_segments("1  000 mV") == [("1", False), ("000 mV", False)]
    assert Q.comment_segments("pH 1.3, 0.1 M HClO4") == [("pH 1.3", True), ("0.1 M HClO4", True)]
    assert Q.comment_segments("0.1 M HClO4, pH 1.3,-0.3 V") == [("0.1 M HClO4", True), ("pH 1.3", True),
                                                                 ("-0.3 V", True)]


# --- one grammar: the template reads electrolyte statements and header set-points the same way --------------------


@pytest.mark.parametrize("text", ["1e-3 M KCl", "0,1 M KOH", "KOH 1 M Ar", "1x10-3 M KCl", "1E-2M HClO4",
                                  "5*10^-3 M CuSO4", "salt bridge 3 M KCl", "1 M MeOH", "0.1 M phosphate buffer",
                                  "0.5 M Cu", "1 M N2", "0.1 M PBS", "0.1 M SYN-acid",
                                  "the cell was filled with 0.5M H2SO4"])
def test_the_template_splits_no_statement_the_rule_does_not_read(text):
    assert T.electrolyte_statement_parts(text) is None
    assert not _offered(text).get("conc")


def test_the_template_splits_what_the_rule_reads():
    for text, parts in (("0.5 M H2SO4", ("H2SO4", 0.5)), ("KOH 100 mM", ("KOH", 0.1)), ("0.1 mol/L KOH", ("KOH", 0.1)),
                        ("100mM NaClO4", ("NaClO4", 0.1)), ("0.2 M Ni(NO3)2", ("Ni(NO3)2", 0.2)),
                        ("1 M HCl", ("HCl", 1.0))):
        assert T.electrolyte_statement_parts(text) == parts
        assert (_offered(text)["name"], _offered(text)["conc"]) == parts


def test_a_name_cell_with_a_concentration_never_names_a_number_not_written_plainly():
    assert T.electrolyte_name_problem("1e-3 M KCl") == ("name only: '1e-3 M KCl' also states a concentration; put it in "
                                                        "'Electrolyte Concentration (M)' in mol/L, and only the name here")
    assert "put 1 in" not in T.electrolyte_name_problem("0,1 M KOH")
    assert T.electrolyte_name_problem("0.01 M HClO4") == ("name only: put 0.01 in 'Electrolyte Concentration (M)', and "
                                                          "only the name here")
    assert "(100 mM)" in T.electrolyte_name_problem("KOH 100 mM")
    assert T.electrolyte_name_problem("HClO4") is None


def test_an_electrolyte_formula_is_real_element_symbols():
    for good in ("HClO4", "KOH", "NaClO4", "H2SO4", "CuSO4", "Ni(NO3)2", "HCl", "K4Fe(CN)6", "LiPF6"):
        assert T.electrolyte_formula(good), good
    for bad in ("Ar", "He", "N2", "CO2", "CO", "NH3", "Cu", "OER", "HER", "PBS", "CV", "MeOH", "EtOH", "D2O", "Ni(NO3",
                "(NH4)2SO4", "koh", "SYN"):
        assert not T.electrolyte_formula(bad), bad


# --- the import: no-value candidates quote the line and are answered with correct ---------------------------------


def _quiet(*argv: str) -> int:
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return cli.main(list(argv))


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    src = tmp_path_factory.mktemp("r1d") / "SYN_bt43"
    make_scan(src / "01_SYNmof_eta_015_A.001", free_text=("eta = 300 mV",))
    make_scan(src / "02_SYNmof_plain_016_A.001", free_text=("0.1 M HClO4, pH 1.3, -0.3 V vs RHE",))
    make_scan(src / "03_SYNmof_run_017_A.001", free_text=("100mM NaClO4 pH1.3 He",))
    out = tmp_path_factory.mktemp("r1d-out") / "bundle"
    assert _quiet("import", str(src), "--out", str(out)) == 0
    assert _quiet("bundle", "group", str(out)) == 0
    assert B.validate_bundle(M.load(out)) == []
    return out


def _run(b: dict, label: str) -> dict:
    return next(r for r in b["runs"] if r["label"] == label)


def _cands(b: dict, label: str) -> dict:
    rid = _run(b, label)["run_id"]
    return {c["target_field_path"]: c for c in b["candidates"] if c["run_id"] == rid and B.is_header_comment_candidate(c)}


def test_a_plain_line_gives_every_value_it_states(imported):
    got = _cands(M.load(imported), "02_SYNmof_plain_016")
    assert {p: c["value"] for p, c in got.items()} == {NAME: "HClO4", CONC: 0.1, PH: 1.3, SETPOINT: -0.3, SCALE: "RHE"}
    assert all(c["value_state"] == B.STATE_NEEDS_REVIEW for c in got.values())


def test_a_line_that_only_mentions_a_field_quotes_it_and_asks(imported):
    b = M.load(imported)
    [eta] = _cands(b, "01_SYNmof_eta_015").values()
    assert eta["target_field_path"] == SETPOINT and eta["value"] is None
    said = ("the comment line 'eta = 300 mV' (line 9 of 01_SYNmof_eta_015_A.001) mentions a potential; ISAAC does not "
            "read a value from free text it cannot parse exactly; tell me the value held during this scan, or say it "
            "isn't stated")
    assert eta["state_basis"]["not_proposable_reason"] == said[:1].upper() + said[1:] + "."
    assert {p: c["value"] for p, c in _cands(b, "03_SYNmof_run_017").items()} == {NAME: None, CONC: None, PH: None}
    [q] = [q for q in Q.consolidate(b)["questions"] if any(t["id"] == eta["candidate_id"] for t in q["targets"])]
    assert said[1:] in q["text"] and q["allowed_decisions"] == list(Q.VALUELESS_DECISIONS)
    assert "--decision correct --value <value> --json" in q["answer_command"]
    got = M.decide(imported, target_ids=[eta["candidate_id"]], decision="correct", value=-0.3, by=WHO, orcid=None)
    assert got["recorded"] == [eta["candidate_id"]]


def test_the_template_reads_a_header_set_point_only_where_the_rule_does(imported):
    b = M.load(imported)
    assert T.header_potential_readings(b, _run(b, "01_SYNmof_eta_015")) == []
    [h] = T.header_potential_readings(b, _run(b, "02_SYNmof_plain_016"))
    assert (h["value"], h["scale"], h["literal"]) == (-0.3, "RHE", "0.1 M HClO4, pH 1.3, -0.3 V vs RHE")
