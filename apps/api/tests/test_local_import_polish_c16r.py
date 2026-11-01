"""c16-r: review fixes for the BL4-3 scan-header readings and the new grouping proposals. Synthetic only (SYN names,
invented lines).

The review of c16a-d found:

* (HIGH) the comment-line parser misread set-points — ``–0.3 V`` (an en dash) and ``- 0.3 V`` as +0.3 V, ``-0,3 V``
  as 3.0 V, ``-0.3 to 0.2 V`` as 0.2 V, ``-0.3/-0.5 V`` as -0.5 V, ``scan 10 mV s-1`` as 0.01 V, and an E1/2, an
  onset, an OCP, a cell voltage or a pre-reduction potential as the set-point — and the confirm question showed only
  the matched fragment ("The files give `0.2` V (from: '0.2 V')"); a reference electrode's filling (``Ag/AgCl 3M
  KCl``) was read as the electrolyte; the template read other lines than the rule (line 8, the gain line, too);
* (M1) the extra candidates pushed a 680-run XDC beamtime past the 4000-candidate bound: the import exited 5;
* (M2) in a bundle built before header readings, the name/header warning could never clear;
* (M3) "different potentials" was said when a scale was missing or the scales differed;
* (M4) a renamed run's ``.exp`` DATA_FILE moved it under another sample's base name; (L4) the ``.exp`` was read
  whole, with control characters, and a path-like DATA_FILE kept its folders;
* (M5) the up-front counter question reopened in an answered bundle, with an example already ruled on;
* (L6) a record written without its start time said nothing while the clock question was not answered at all;
* (L1) a re-import over a bundle did not say that the old answers and ids do not carry over.
"""

from __future__ import annotations

import io
import json
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import import template as T
from isaac_api.local_import.readers import ssrl_xdc as x

from test_local_import_reader_ssrl_xdc import make_scan

WHO = "SYNTHETIC TEST"
NAME, CONC, PH = ("context.electrochemistry.electrolyte.name", "context.electrochemistry.electrolyte.concentration_M",
                  "context.electrochemistry.pH")
SETPOINT, SCALE = "context.electrochemistry.potential_setpoint_V", "context.electrochemistry.potential_scale"


def _read(line: str) -> dict:
    return {r["path"]: r["value"] for r in Q.header_comment_readings(line)}


def _quiet(*argv: str) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = cli.main(list(argv))
    return rc, buf.getvalue()


# --- HIGH: the parser ------------------------------------------------------------------------------------


@pytest.mark.parametrize("line", ["\u20130.3 V vs RHE", "\u22120.3 V vs RHE", "E=-0.3V vs RHE"])
def test_every_minus_a_header_writes_is_a_minus(line):
    assert _read(line) == {SETPOINT: -0.3, SCALE: "RHE"}


@pytest.mark.parametrize("line", [
    "-0,3 V vs RHE", "0,3 V vs RHE",  # a comma decimal: never 3.0 V
    "-0.3 to 0.2 V", "-0.3 V to 0.2 V", "0.1 V vs RHE to -0.5 V vs RHE", "CV from 0.05 to 1.2 V vs RHE",  # ranges
    "-0.3/-0.5 V vs RHE", "-0.3 V vs RHE / -0.5 V",  # after a slash
    "pH 1.3 - 0.3 V vs RHE", "+-0.3 V vs RHE", "\u00b10.3 V", "1e-1 V",  # a sign or a number not plain
    "E1/2 = 0.8 V", "E1/2 0.8 V vs RHE", "Eonset 0.9V vs RHE", "Ecell 1.5V", "1.5 V cell voltage",
    "OCP 0.9 V vs RHE", "at OCP (0.9 V vs RHE)", "OCV 0.85 V", "open circuit 0.9 V",
    "amplitude 10 mV", "dE 10 mV", "LSV -0.3 V vs RHE", "sweep to -0.3 V",
    "pre-reduced at -0.5 V vs RHE", "after -0.5 V vs RHE", "held at -0.3 V vs RHE after CA at 0.1 V",
    "-0.3 V vs RHE for 10 min then OCP", "-0.3 V vs RHE -> -0.5 V vs RHE",
    # r1d: a sign apart from its number, a hyphen (U+2010), brackets, a label or a date beside it: not a plain form
    "\u20100.3 V vs RHE", "- 0.3 V vs RHE", "E = - 0.3 V vs RHE", "(-0.3 V vs RHE)", "Ewe -0.3V", "step -0.3 V",
    "2019-05-12 -0.3 V vs RHE",
])
def test_a_line_that_does_not_state_one_set_point_plainly_gives_no_value(line):
    [got] = [r for r in Q.header_comment_readings(line) if r["path"] == SETPOINT]
    assert got["value"] is None and got["ambiguous"] and got["why"]
    assert SCALE not in _read(line)  # no scale is read beside a potential that was not


@pytest.mark.parametrize("line", ["scan 10 mV s-1", "50 mV s^-1", "10 mV/s", "2 V/s scan rate", "0.5 V/dec", "-0.3 V/s"])
def test_a_rate_is_no_potential(line):
    assert _read(line)[SETPOINT] is None  # r1d: the line mentions volts, so the set-point is asked, with no value


@pytest.mark.parametrize("line,volts", [("-0.3 V vs RHE", -0.3), ("E -0.3V", -0.3), ("held at -0.3 V", -0.3),
                                        ("100mM NaClO4 pH1.3 He; -0.3 V vs RHE", -0.3), ("-300 mV vs RHE", -0.3),
                                        ("2019-05-12, -0.3 V vs RHE", -0.3), ("+0.5 V vs RHE", 0.5), ("0 V", 0.0)])
def test_a_plain_set_point_still_reads(line, volts):
    assert _read(line)[SETPOINT] == volts


def test_the_reading_keeps_the_whole_line_as_its_literal():
    line = "100mM NaClO4 pH1.3 He; -0.3 V vs RHE"
    assert {r["literal"] for r in Q.header_comment_readings(line)} == {line}


@pytest.mark.parametrize("line", ["-1.2 V vs Ag/AgCl 3M KCl", "0.5 M Na2SO4 standard", "3 M KCl filling",
                                  "1 M KOH, reference Hg/HgO", "0.1 M KCl sat. SCE"])
def test_an_electrolyte_beside_a_reference_or_standard_word_gives_no_value(line):
    got = {r["path"]: r for r in Q.header_comment_readings(line)}
    assert got[NAME]["value"] is None and got[CONC]["value"] is None
    assert got[NAME]["ambiguous"] and got[NAME]["why"] == Q.HEADER_UNREAD_WHY


def test_the_potential_beside_a_reference_filling_still_reads():
    got = _read("-1.2 V vs Ag/AgCl, 3M KCl")  # r1d: each its own segment
    assert (got[SETPOINT], got[SCALE]) == (-1.2, "Ag/AgCl")


# --- the import: whole lines, the comment lines only, and the confirm question ---------------------------


def _with_line_8(path: Path, text: str) -> None:
    """``make_scan`` writes ``gain line literal`` on line 8 (the reader's gain line): put ``text`` there."""
    path.write_bytes(path.read_bytes().replace(b"gain line literal", text.encode("latin-1")))


@pytest.fixture(scope="module")
def imported(tmp_path_factory) -> dict:
    src = tmp_path_factory.mktemp("c16r") / "SYN_bt43"
    make_scan(src / "01_SYNmof_plain_015_A.001", free_text=("100 mM NaClO4, pH 1.3, He; -0.3 V vs RHE",))
    make_scan(src / "02_SYNmof_range_016_A.001", free_text=("0.1 M KOH", "CV from 0.05 to 1.2 V vs RHE"))
    make_scan(src / "03_SYNmof_ref_017_A.001", free_text=("-1.2 V vs Ag/AgCl, 3M KCl",))
    _with_line_8(make_scan(src / "04_SYNmof_gain_018_A.001", free_text=("SYN spare",)), "-0.5 V vs RHE")
    out = tmp_path_factory.mktemp("c16r-out") / "bundle"
    assert _quiet("import", str(src), "--out", str(out))[0] == 0
    b = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(b) == []
    return {"out": out, "bundle": b}


def _run(b: dict, label: str) -> dict:
    return next(r for r in b["runs"] if r["label"] == label)


def _cands(b: dict, label: str) -> dict:
    rid = _run(b, label)["run_id"]
    return {c["target_field_path"]: c for c in b["candidates"] if c["run_id"] == rid and B.is_header_comment_candidate(c)}


def test_the_evidence_is_the_whole_line_and_its_number(imported):
    got = _cands(imported["bundle"], "01_SYNmof_plain_015")
    line = "100 mM NaClO4, pH 1.3, He; -0.3 V vs RHE"
    assert {p: c["value"] for p, c in got.items()} == {NAME: "NaClO4", CONC: 0.1, PH: 1.3, SETPOINT: -0.3, SCALE: "RHE"}
    for c in got.values():
        assert [(e["literal_value"], e["locator"]) for e in c["evidence"]] == [(line, "line:9")]


def test_a_range_gives_a_candidate_with_no_value_that_quotes_the_line(imported):
    got = _cands(imported["bundle"], "02_SYNmof_range_016")
    assert got[SETPOINT]["value"] is None and SCALE not in got
    reason = got[SETPOINT]["state_basis"]["not_proposable_reason"]
    assert "The comment line 'CV from 0.05 to 1.2 V vs RHE' (line 10 of 02_SYNmof_range_016_A.001)" in reason
    assert got[NAME]["value"] == "KOH"  # the other line is read as before


def test_a_reference_filling_is_not_the_electrolyte(imported):
    got = _cands(imported["bundle"], "03_SYNmof_ref_017")
    assert got[NAME]["value"] is None and got[CONC]["value"] is None
    assert (got[SETPOINT]["value"], got[SCALE]["value"]) == (-1.2, "Ag/AgCl")


def test_line_8_the_gain_line_is_not_read(imported):
    b = imported["bundle"]
    assert not _cands(b, "04_SYNmof_gain_018")
    assert T.header_potential_readings(b, _run(b, "04_SYNmof_gain_018")) == []


def test_the_template_reads_the_same_lines_with_the_same_parser_as_the_rule(imported):
    b = imported["bundle"]
    for label in ("01_SYNmof_plain_015", "02_SYNmof_range_016", "03_SYNmof_ref_017", "04_SYNmof_gain_018"):
        cand = _cands(b, label).get(SETPOINT)
        heads = T.header_potential_readings(b, _run(b, label))
        if cand is None or cand["value"] is None:
            assert heads == [], label  # no value for the rule: no file reading for the template either
        else:
            assert [(h["value"], h["literal"], h["locator"]) for h in heads] == [
                (cand["value"], e["literal_value"], e["locator"]) for e in cand["evidence"]], label


def test_the_confirm_question_quotes_the_line_and_says_what_to_check(imported):
    cand = _cands(imported["bundle"], "01_SYNmof_plain_015")[SETPOINT]
    text = Q._confirmed_value_text(SETPOINT, [cand])
    assert text == (" The files give `-0.3` V (read by pattern from the comment line '100 mM NaClO4, pH 1.3, He; -0.3 V "
                    "vs RHE' (line 9 of 01_SYNmof_plain_015_A.001); check it is the potential held during this scan); "
                    "`confirm` records exactly that.")


# --- M1: a large XDC beamtime imports ---------------------------------------------------------------------


def test_a_680_run_beamtime_imports_and_says_how_many_runs_were_not_read(tmp_path):
    src = tmp_path / "SYN"
    for i in range(680):
        make_scan(src / f"SYNs{i:04d}_x_{i:03d}_A.001", free_text=("100mM NaClO4 pH1.3", "-0.3 V vs RHE"))
    out = tmp_path / "b"
    rc, said = _quiet("import", str(src), "--out", str(out))
    assert rc == 0, said
    b = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(b) == [] and len(b["candidates"]) <= B.MAX_CANDIDATES
    read = {c["run_id"] for c in b["candidates"] if B.is_header_comment_candidate(c)}
    skipped = b["counts"][B.HEADER_COMMENT_RUNS_NOT_READ]
    assert skipped == 680 - len(read) > 0
    line = f"{skipped} SSRL XDC run(s) had their scan-header comment lines NOT read into values"
    assert line in said and line in (out / "summary.md").read_text()
    # every run still has its start time candidate (ids unchanged: they come first)
    assert sum(1 for c in b["candidates"] if B.is_local_clock_start(c)) == 680


def test_a_small_beamtime_counts_nothing_left_out(imported):
    assert B.HEADER_COMMENT_RUNS_NOT_READ not in imported["bundle"]["counts"]


# --- M2 / M3: the name/header warning ---------------------------------------------------------------------


LABEL = "05_SYNmof_m150mV_021"


@pytest.fixture()
def old_bundle(tmp_path, monkeypatch) -> Path:
    """What a build before the comment rule made: no candidate holds the scan header's reading."""
    monkeypatch.setattr(B, "_xdc_comment_candidates", lambda *a, **k: [])
    src = tmp_path / "SYN_bt43"
    for i in (1, 2):
        make_scan(src / f"{LABEL}_A.{i:03d}", free_text=("100mM NaClO4 pH1.3", "-300mV vs RHE"))
    out = tmp_path / "bundle"
    assert _quiet("import", str(src), "--out", str(out))[0] == 0
    M.group(out)
    return out


def _carried(volts: float) -> dict:
    return {SETPOINT: {"value": volts, "status": "scientist_confirmed", "evidence": []},
            SCALE: {"value": "RHE", "status": "scientist_confirmed", "evidence": []}}


def test_in_an_old_bundle_a_later_ruling_on_the_records_set_point_clears_the_warning(old_bundle):
    b = M.load(old_bundle)
    rid = _run(b, LABEL)["run_id"]
    group = next(g for g in b["record_groups"] if g["member_run_ids"] == [rid])
    [miss] = [m["value_id"] for m in b["missing_values"] if m["run_id"] == rid and m["target_field_path"] == SETPOINT]
    M.decide(old_bundle, target_ids=[miss], decision="correct", value=-0.15, by=WHO, orcid=None)  # e.g. a sheet's value
    [w] = R._potential_sources_warnings(M.load(old_bundle), group, {rid}, _carried(-0.15))
    assert w["targets"] == [miss]
    assert w["command"] == (f'isaac bundle decide <bundle_dir> --target {miss} --decision confirm --value -0.15 --json '
                            '--by "<your name>"')
    assert "rule on the record's own set-point instead" in w["text"]
    assert R.REIMPORT_CAVEAT in w["text"] and "a filled workbook do not carry over" in w["text"]
    assert "(miss-NNNN, cand-NNNN, the question ids) name other things there" in w["text"]
    # the warning's own command, made after it was shown, is a ruling (the same volts: the file name is right)
    M.decide(old_bundle, target_ids=[miss], decision="confirm", value=-0.15, by=WHO, orcid=None)
    assert R._potential_sources_warnings(M.load(old_bundle), group, {rid}, _carried(-0.15)) == []


def test_a_ruling_made_with_the_command_after_a_confirm_is_recorded_too(old_bundle):
    b = M.load(old_bundle)
    rid = _run(b, LABEL)["run_id"]
    group = next(g for g in b["record_groups"] if g["member_run_ids"] == [rid])
    [miss] = [m["value_id"] for m in b["missing_values"] if m["run_id"] == rid and m["target_field_path"] == SETPOINT]
    M.decide(old_bundle, target_ids=[miss], decision="confirm", value=-0.3, by=WHO, orcid=None)
    [w] = R._potential_sources_warnings(M.load(old_bundle), group, {rid}, _carried(-0.3))
    assert "--decision correct --value -0.3 --json" in w["command"]  # unlike the latest, so it is recorded
    got = M.decide(old_bundle, target_ids=[miss], decision="correct", value=-0.3, by=WHO, orcid=None)
    assert got["recorded"] == [miss]
    assert R._potential_sources_warnings(M.load(old_bundle), group, {rid}, _carried(-0.3)) == []


def test_no_scale_on_the_name_is_never_called_different_potentials(old_bundle):
    b = M.load(old_bundle)
    rid = _run(b, LABEL)["run_id"]
    group = next(g for g in b["record_groups"] if g["member_run_ids"] == [rid])
    [miss] = [m["value_id"] for m in b["missing_values"] if m["run_id"] == rid and m["target_field_path"] == SETPOINT]
    M.decide(old_bundle, target_ids=[miss], decision="correct", value=-0.15, by=WHO, orcid=None)
    [w] = R._potential_sources_warnings(M.load(old_bundle), group, {rid}, _carried(-0.15))
    assert "write different numbers (file name m150mV;" in w["text"]
    assert "file name: no scale; scan header: RHE)" in w["text"] and "different potentials" not in w["text"]


@pytest.mark.parametrize("names,heads,said", [
    ("RHE", "RHE", "state different potentials (file name 0p2Vrhe; scan header '0.5 V vs RHE'; both on RHE)"),
    ("no scale", "no scale", "write different numbers (file name 0p2Vrhe; scan header '0.5 V vs RHE'; file name: no scale; scan header: no scale)"),
    ("Ag/AgCl", "RHE", "write different numbers (file name 0p2Vrhe; scan header '0.5 V vs RHE'; file name: Ag/AgCl; scan header: RHE)"),
])
def test_only_one_named_scale_on_both_sides_is_a_disagreement(names, heads, said):
    w = {"run_id": "run-1", "names": ["0p2Vrhe"], "headers": ["'0.5 V vs RHE'"], "carried_V": 0.2, "carried_scale": None,
         "same_scale": names == heads and names != "no scale", "name_scale": names, "header_scale": heads,
         "targets": ["cand-0001"], "command": "<cmd>"}
    assert said in R.potential_sources_text(w)


# --- M4 / L4: the .exp DATA_FILE --------------------------------------------------------------------------


def test_a_renamed_runs_exp_never_moves_it_under_another_samples_base_name(tmp_path):
    src = tmp_path / "SYN"
    for name in ("01_SYNa_015", "01_SYNa_016", "02_SYNb_017"):
        make_scan(src / f"{name}_A.001")
    (src / "01_SYNa_015.exp").write_bytes(b"DATA_FILE 01_SYNa\x1b[31m\x00\n")
    (src / "02_SYNb_017.exp").write_bytes(b"DATA_FILE 01_SYNa\n")  # its .exp still names another acquisition
    out = tmp_path / "b"
    assert _quiet("import", str(src), "--out", str(out))[0] == 0
    assert _quiet("bundle", "group", str(out))[0] == 0
    b = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(b) == []
    runs = {r["run_key"]: r["label"] for r in b["runs"]}
    groups = {g["group_id"]: g for g in b["record_groups"]}
    got = [sorted(runs[k] for gid in m["group_ids"] for k in groups[gid]["member_run_keys"]) for m in b["merge_candidates"]]
    assert got == [["01_SYNa_015", "01_SYNa_016"]]
    [flagged] = [g for g in b["record_groups"] if G.EXP_NAME_DIFFERS_FLAG in g["flags"]]
    assert flagged["exp_data_file_differs"] == [{"run_key": next(k for k, v in runs.items() if v == "02_SYNb_017"),
                                                 "stem": "02_SYNb_017", "exp_data_file": "01_SYNa"}]


def test_the_data_file_is_used_only_when_it_is_the_runs_own_name():
    assert G.base_name_key("03_SYNx_dry_017", "03_SYNx_dry") == "03_synx_dry"
    assert G.base_name_key("03_SYNx_dry_017", "03_synx_DRY") == "03_synx_dry"  # casefolded
    assert G.base_name_key("03_SYNx_dry_017", "SYN_other") == "03_synx_dry"  # another name: the run's own
    assert G.exp_data_file_agrees("03_SYNx_dry_017", "03_SYNx_dry") and not G.exp_data_file_agrees("03_SYNx_dry_017", "x")


@pytest.mark.parametrize("raw,want", [
    (b"EXPT_TYPE SYN\rDATA_FILE 01_SYNa\rCOMMENTS1 SYN comment\r", ("01_SYNa", "line:2")),  # CR line ends
    (b"EXPT_TYPE SYN\r\nDATA_FILE 01_SYNa\r\n", ("01_SYNa", "line:2")),
    (b"DATA_FILE = C:\\xdc\\data\\01_SYNa.dat\n", ("01_SYNa", "line:1")),  # a path: its base name
    (b"DATA_FILE /data/SYN/01_SYNa.dat\n", ("01_SYNa", "line:1")),
    (b"DATA_FILE 01_SYNa\x1b[31mX\x07\n", ("01_SYNaX", "line:1")),  # control characters removed
    (b"DATA_FILE 01\x00_SYNa\n", ("01_SYNa", "line:1")),
    (b"DATA_FILE\nDATA_FILE   \n", None),
    (b"DATA_FILE \x07\nDATA_FILE 01_SYNa\n", ("01_SYNa", "line:2")),  # a value of control characters only is none
])
def test_the_exp_data_file_line_is_read_cleanly(tmp_path, raw, want):
    p = tmp_path / "x.exp"
    p.write_bytes(raw)
    got = x._exp_data_file("x.exp", {"x.exp": (p, len(raw))}, [{"relative_path": "x.exp", "role": "experiment"}])
    assert (None if got is None else (got["literal"], got["locator"])) == want


def test_an_exp_larger_than_its_bound_is_not_read_whatever_size_was_listed(tmp_path):
    p = tmp_path / "x.exp"
    p.write_bytes(b"DATA_FILE 01_SYNa\n" + b"X" * x.MAX_EXP_BYTES)
    assert x._exp_data_file("x.exp", {"x.exp": (p, 10)}, [{"relative_path": "x.exp", "role": "experiment"}]) is None


# --- M5: the up-front counter question in an answered bundle -----------------------------------------------


RUNS = ("01_SYNelS_015", "01_SYNelS_016", "03_SYNmofA_dry_017", "03_SYNmofA_dry_018")  # last tokens at 3 and 4


@pytest.fixture()
def counter_bundle(tmp_path) -> Path:
    src = tmp_path / "SYN_bt43"
    for name in RUNS:
        make_scan(src / f"{name}_A.001", free_text=("SYNTHETIC comment line",))
    out = tmp_path / "b"
    assert _quiet("import", str(src), "--out", str(out))[0] == 0
    assert _quiet("bundle", "group", str(out))[0] == 0
    return out


def _counter_q(out: Path) -> list[dict]:
    return [q for q in Q.consolidate(M.load(out))["questions"] if q["kind"] == "naming_counter_positions"]


def test_a_position_ruled_not_a_counter_is_not_asked_again_nor_its_example_shown(counter_bundle):
    [q] = _counter_q(counter_bundle)
    assert q["question_id"] == Q.COUNTER_QUESTION_ID and q["last_token_positions"] == [3, 4]
    M.decide(counter_bundle, target_ids=["experiment"], decision=B.NOT_COUNTER_DECISION, value=None, by=WHO,
             orcid=None, positions=[3])
    for regroup in (False, True):
        if regroup:
            assert _quiet("bundle", "group", str(counter_bundle), "--regroup")[0] == 0
        [q] = _counter_q(counter_bundle)
        assert q["question_id"] == Q.COUNTER_QUESTION_ID  # the same id throughout
        assert q["last_token_positions"] == [4]  # what a "no" names now
        assert all("SYNelS" not in n for n in q["example_names"]["-1"])  # never the family already ruled on
        assert "03_SYNmofA_dry_[017]" in q["example_names"]["-1"]


def test_with_every_last_position_ruled_either_way_the_question_stays_closed(counter_bundle):
    M.decide(counter_bundle, target_ids=["experiment"], decision=B.NOT_COUNTER_DECISION, value=None, by=WHO,
             orcid=None, positions=[3])
    M.decide(counter_bundle, target_ids=["experiment"], decision="set_counter_positions", value=None, by=WHO,
             orcid=None, positions=[4])
    assert not _counter_q(counter_bundle)
    assert _quiet("bundle", "group", str(counter_bundle), "--regroup")[0] == 0
    assert not _counter_q(counter_bundle)
    assert not [gq for gq in M.load(counter_bundle).get("grouping_questions") or ()
                if gq.get("kind") == "naming_counter_positions"]


# --- L6 / L1 ------------------------------------------------------------------------------------------------


def test_a_record_without_its_start_time_says_so_while_the_clock_question_is_unanswered(counter_bundle):
    for g in M.load(counter_bundle)["record_groups"]:
        M.decide(counter_bundle, target_ids=[g["group_id"]], decision="confirm", value=None, by=WHO, orcid=None)
    R.build_records(counter_bundle)
    got = [w for w in R.validate_records(counter_bundle, full=True).get("warnings") or () if w["code"] == R.START_TIME_WARNING]
    assert len(got) == len(RUNS)
    assert {w["text"] for w in got} == {f"start time left out: instrument clock zone not answered yet (question {Q.CLOCK_QUESTION_ID})"}
    assert R.written_without(got[0]).startswith("Written without the start time: start time left out")


def test_a_re_import_over_a_bundle_says_its_answers_and_ids_do_not_carry_over(counter_bundle, tmp_path):
    src = tmp_path / "SYN_bt43"
    rc, said = _quiet("import", str(src), "--out", str(counter_bundle), "--force")
    assert rc == 0 and f"It replaces the bundle that was in {counter_bundle}: {R.REIMPORT_CAVEAT}." in said
    rc, said = _quiet("import", str(src), "--out", str(tmp_path / "fresh"))
    assert rc == 0 and R.REIMPORT_CAVEAT not in said
