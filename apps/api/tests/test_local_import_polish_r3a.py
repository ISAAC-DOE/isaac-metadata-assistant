"""r3a: what a real-data run on an SSRL BL4-3 Ti K-edge beamtime found. Synthetic only (invented lines, SYN names).

BL4-3 scan headers write a sample, an electrolyte and a potential glued into one comment line (``Sample A in 1M KOH
0Vrhe``), so every comment line gives the whitelist rule no value. What these pin:

* H1: ``bundle excerpt`` of a candidate shows the line its ``line:N`` locator names, and says so when it cannot;
* H2: a potential a value-less header line MENTIONS (``0Vrhe``) is compared, never offered: against the file name's
  (``m600mV``) and the typed value, warned at validate until a scientist rules, and never said to agree;
* M1: with no ``<name>.exp``, the DATA_FILE of the ONLY ``.exp`` in the run's own folder (a reused template) is read,
  kept only when it is the run's own name minus its counter, and a merge candidate whose DATA_FILEs agree says so;
* M6: a no-value question says it asks for a value (``no_value``, the kind unchanged), and the per-run questions that
  quote one comment line for one field share a ``same_reading_group`` answered at once (``--same-reading``).
"""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl
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
SETPOINT = "context.electrochemistry.potential_setpoint_V"


def _import(src: Path, out: Path) -> Path:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    M.group(out)
    for g in M.load(out)["record_groups"]:
        M.decide(out, target_ids=[g["group_id"]], decision="confirm", value=None, by=WHO, orcid=None)
    return out


def _header_cands(b: dict, path: str) -> list[dict]:
    return [c for c in b["candidates"] if B.is_header_comment_candidate(c) and c["target_field_path"] == path]


# --- H1: excerpt shows the line a candidate's locator names ------------------------------------------------------


@pytest.fixture(scope="module")
def excerpted(tmp_path_factory):
    root = tmp_path_factory.mktemp("r3a-h1")
    src = root / "SYN_bt43"
    make_scan(src / "01_SYNti_m600mV_096_A.001", free_text=("SYN gain 1e8", "Sample A in 1M KOH 0Vrhe", "SYN note"))
    return src, _import(src, root / "bundle")


def test_excerpt_of_a_header_comment_candidate_shows_its_line(excerpted):
    src, out = excerpted
    b = M.load(out)
    [cand] = _header_cands(b, SETPOINT)
    assert cand["evidence"][0]["locator"] == "line:10"
    got = M.excerpt(b, cand["candidate_id"], source=str(src))
    [hit] = got["excerpts"]
    assert hit["locator"] == "line:10" and hit["lines"] == [7, 13] and "note" not in hit
    assert "   10: Sample A in 1M KOH 0Vrhe" in hit["text"].splitlines()


@pytest.mark.parametrize("locator,first,last", [("line:10", 10, None), ("line 3", 3, None),
                                                ("command 2 (lines 4-9)", 4, "9")])
def test_every_line_locator_the_readers_write_is_read(locator, first, last):
    m = M._LINE_RE.search(locator)
    assert m is not None and int(m.group("first")) == first and m.group("last") == last


def test_a_locator_that_names_no_file_line_is_not_read_as_one():
    assert M._LINE_RE.search("history line 4") is None  # an Igor history line is not a line of the file
    assert M._LINE_RE.search("record 3 (wave note)") is None


def test_a_line_past_the_end_of_the_file_is_refused_not_replaced_by_the_first_lines(excerpted, monkeypatch):
    src, out = excerpted
    b = M.load(out)
    [cand] = _header_cands(b, SETPOINT)
    monkeypatch.setattr(M, "_locators", lambda c: [{"source_id": e["source_id"], "relative_path": e["relative_path"],
                                                    "locator": "line:900"} for e in c["evidence"]][:1])
    [hit] = M.excerpt(b, cand["candidate_id"], source=str(src))["excerpts"]
    assert "lines" not in hit and hit["refused"].startswith("the locator names line 900 and the file has ")


def test_a_locator_with_no_line_says_the_first_lines_are_shown(excerpted, monkeypatch):
    src, out = excerpted
    b = M.load(out)
    [cand] = _header_cands(b, SETPOINT)
    monkeypatch.setattr(M, "_locators", lambda c: [{"source_id": e["source_id"], "relative_path": e["relative_path"],
                                                    "locator": "record 3"} for e in c["evidence"]][:1])
    [hit] = M.excerpt(b, cand["candidate_id"], source=str(src))["excerpts"]
    assert hit["lines"] == [1, 7] and hit["note"] == "the locator (record 3) names no line of the file: its first lines are shown"


# --- H2: a potential a value-less header line mentions is compared, never offered --------------------------------


WRONG, SAME, TWO = "01_SYNti_m600mV_096", "02_SYNti_m600mV_097", "03_SYNti_1p6V_098"
LINES = {WRONG: "Sample A in 1M KOH 0Vrhe", SAME: "Sample A in 1M KOH -0.6Vrhe", TWO: "SYN 0.5 V then 1.6 V vs RHE"}


@pytest.fixture()
def glued(tmp_path):
    src = tmp_path / "SYN_bt43"
    for label, line in LINES.items():
        for i in (1, 2):
            make_scan(src / f"{label}_A.{i:03d}", free_text=("SYN gain 1e8", line))
    return _import(src, tmp_path / "bundle")


def _rid(b: dict, label: str) -> str:
    return next(r["run_id"] for r in b["runs"] if r["label"] == label)


def _group(b: dict, rid: str) -> dict:
    return next(g for g in b["record_groups"] if g["member_run_ids"] == [rid])


CARRIED = {SETPOINT: {"value": -0.6, "status": "scientist_confirmed", "evidence": []},
           "context.electrochemistry.potential_scale": {"value": "RHE", "status": "scientist_confirmed", "evidence": []}}


def test_every_potential_a_line_mentions_is_kept_and_none_is_picked():
    assert [(m["literal"], m["volts"], m["scale"]) for m in Q.header_potential_mentions("Sample A in 1M KOH 0Vrhe")] == [
        ("0Vrhe", 0.0, "RHE")]
    assert [m["literal"] for m in Q.header_potential_mentions("SYN 0.5 V then 1.6 V vs RHE")] == ["0.5 V", "1.6 V vs RHE"]
    assert [m["volts"] for m in Q.header_potential_mentions("in 1M KOH 0.5Vrhe; -300 mV vs Ag/AgCl")] == [0.5, -0.3]
    for none in ("PMT 0.8 kV", "5 µV noise", "5 Volts", "1M KOH", "V K-edge"):
        assert Q.header_potential_mentions(none) == [], none


def test_a_mention_is_never_offered_as_a_value(glued):
    b = M.load(glued)
    for label in LINES:
        run = next(r for r in b["runs"] if r["label"] == label)
        assert T.header_potential_readings(b, run) == []
    assert all(c["value"] is None for c in _header_cands(b, SETPOINT))


def test_a_file_name_and_a_header_mention_that_differ_are_warned_at_validate(glued):
    b = M.load(glued)
    rid = _rid(b, WRONG)
    [w] = R._potential_sources_warnings(b, _group(b, rid), {rid}, CARRIED)
    assert w["code"] == R.POTENTIAL_SOURCES_WARNING
    assert w["text"].startswith(f"the scan header of {rid} writes '0Vrhe' (its line 'Sample A in 1M KOH 0Vrhe' at line:10 "
                                f"of {WRONG}_A.001, line:10 of {WRONG}_A.002), the file name writes m600mV, and the record "
                                "carries -0.6 V on RHE: '0Vrhe' differs from the file name's and the record's")
    assert "state a potential" not in w["text"] and "--decision correct --value <volts> --json" in w["command"]


def test_matching_mentions_are_not_warned(glued):
    b = M.load(glued)
    rid = _rid(b, SAME)
    assert R._potential_sources_warnings(b, _group(b, rid), {rid}, CARRIED) == []


def test_each_of_several_mentions_is_compared(glued):
    b = M.load(glued)
    rid = _rid(b, TWO)
    carried = {**CARRIED, SETPOINT: {**CARRIED[SETPOINT], "value": 1.6}}
    [w] = R._potential_sources_warnings(b, _group(b, rid), {rid}, carried)
    assert "writes '0.5 V' and '1.6 V vs RHE' (its line" in w["text"]
    assert "'0.5 V' differs from the file name's and the record's" in w["text"] and "'1.6 V vs RHE' differs" not in w["text"]


def test_a_ruling_on_the_header_line_clears_the_warning(glued):
    b = M.load(glued)
    rid = _rid(b, WRONG)
    [cand] = [c for c in _header_cands(b, SETPOINT) if c["run_id"] == rid]
    M.decide(glued, target_ids=[cand["candidate_id"]], decision="correct", value=-0.6, by=WHO, orcid=None)
    assert R._potential_sources_warnings(M.load(glued), _group(b, rid), {rid}, CARRIED) == []


def test_build_records_never_says_a_differing_file_name_and_header_state_one_potential(glued):
    R.build_records(glued)
    got = {w["group_id"]: w["text"] for w in R.validate_records(glued, full=False).get("warnings") or ()
           if w["code"] == R.STATED_POTENTIAL_WARNING}
    b = M.load(glued)
    wrong, same = got[_group(b, _rid(b, WRONG))["group_id"]], got[_group(b, _rid(b, SAME))["group_id"]]
    assert wrong.startswith("the file names and scan headers write different potentials (m600mV in ")
    assert f"{_rid(b, WRONG)}: the scan header writes '0Vrhe', the file name writes m600mV" in wrong
    assert "state a potential" not in wrong
    assert same.startswith("the file names and scan headers state a potential (m600mV in ")
    assert "different" not in same


def _typed(out: Path, tmp_path: Path, label: str, volts: float, capsys) -> dict:
    xlsx = tmp_path / "t.xlsx"
    assert cli.main(["bundle", "template", "export", str(out), "--out", str(xlsx)]) == 0
    wb = openpyxl.load_workbook(xlsx)
    rid = _rid(M.load(out), label)
    row = next(int(v[1]) for v in wb["_isaac"].iter_rows(values_only=True) if v[0] == "File List" and v[2] == rid)
    header = next(r for r in range(1, 10) if any(c.value == "Potential (V)" for c in wb["File List"][r]))
    col = {c.value: c.column_letter for c in wb["File List"][header] if c.value}
    wb["File List"][f"{col['Potential (V)']}{row}"] = volts
    wb["File List"][f"{col['Potential Scale']}{row}"] = "RHE"
    wb.save(xlsx)
    capsys.readouterr()
    assert cli.main(["bundle", "template", "import", str(out), str(xlsx), "--by", WHO, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_the_template_preview_names_a_header_mention_the_typed_value_contradicts(glued, tmp_path, capsys):
    rep = _typed(glued, tmp_path, WRONG, -0.6, capsys)
    lines = [line for x in rep["replaces_or_contradicts_a_file_reading"] if x["target_field_path"] == SETPOINT
             for line in x["readings"]]
    assert (f"contradicts the scan header, which writes '0Vrhe' in its line 'Sample A in 1M KOH 0Vrhe' at line:10 of "
            f"{WRONG}_A.001 (a mention: no value is read from it)") in lines


def test_the_template_preview_lists_no_mention_that_agrees(glued, tmp_path, capsys):
    rep = _typed(glued, tmp_path, SAME, -0.6, capsys)
    assert not [x for x in rep["replaces_or_contradicts_a_file_reading"] if x["target_field_path"] == SETPOINT]


# --- M1: the .exp DATA_FILE of a template reused under another name ----------------------------------------------


TEMPLATE = "AgL3_SYN_exp1.exp"


def _template_beamtime(root: Path, data_files: dict[str, str | None], *, extra_exp: bool = False) -> Path:
    """Each run in its own folder with a copy of one template .exp (``None``: no DATA_FILE line in it)."""
    src = root / "SYN_bt43"
    for name, data_file in data_files.items():
        for i in (1, 2):
            make_scan(src / name / f"{name}_A.{i:03d}", free_text=("SYN gain 1e8", "SYN comment"))
        (src / name / TEMPLATE).write_text("EXPT_TYPE SYN\n" + (f"DATA_FILE {data_file}\n" if data_file else "")
                                           + "COMMENTS1 SYNTHETIC\n")
        if extra_exp:
            (src / name / "SYN_other.exp").write_text(f"DATA_FILE {data_file}\n")
    return src


def _data_files(src: Path) -> dict[str, list[dict]]:
    return {r.label: [s for s in r.statements if s["key"] == "exp_data_file"] for r in x.collect_generic_runs(src)}


def test_the_only_exp_in_the_runs_own_folder_is_read(tmp_path):
    src = _template_beamtime(tmp_path, {"SYNti_m600mV_096": "SYNti_m600mV"})
    [st] = _data_files(src)["SYNti_m600mV_096"]
    assert (st["literal"], st["locator"], st["source_relative_path"]) == ("SYNti_m600mV", "line:2",
                                                                          f"SYNti_m600mV_096/{TEMPLATE}")
    [run] = x.collect_generic_runs(src)
    assert [(c["relative_path"], c["role"], c["parsed"]) for c in run.companions if c["role"] == "experiment"] == [
        (f"SYNti_m600mV_096/{TEMPLATE}", "experiment", True)]


def test_a_template_naming_another_acquisition_says_nothing(tmp_path):
    src = _template_beamtime(tmp_path, {"SYNti_m600mV_096": "AgL3_xas", "SYNti_m300mV_097": None})
    assert _data_files(src) == {"SYNti_m600mV_096": [], "SYNti_m300mV_097": []}
    out = _import(src, tmp_path / "bundle")
    assert not any(G.EXP_NAME_DIFFERS_FLAG in g["flags"] for g in M.load(out)["record_groups"])


def test_two_exp_files_in_the_folder_are_not_read(tmp_path):
    src = _template_beamtime(tmp_path, {"SYNti_m600mV_096": "SYNti_m600mV"}, extra_exp=True)
    assert _data_files(src) == {"SYNti_m600mV_096": []}


def test_the_exp_files_own_name_is_never_a_hint(tmp_path):
    src = tmp_path / "SYN_bt43"
    make_scan(src / "SYNti_m600mV_096" / "SYNti_m600mV_096_A.001")
    (src / "SYNti_m600mV_096" / "SYNti_m600mV.exp").write_text("EXPT_TYPE SYN\n")  # named like the run, no DATA_FILE
    assert _data_files(src) == {"SYNti_m600mV_096": []}


def test_the_runs_own_exp_is_still_the_one_read(tmp_path):
    src = _template_beamtime(tmp_path, {"SYNti_m600mV_096": "SYNti_m600mV"})
    (src / "SYNti_m600mV_096" / "SYNti_m600mV_096.exp").write_text("DATA_FILE SYNti_m600mV\n")
    [st] = _data_files(src)["SYNti_m600mV_096"]
    assert st["source_relative_path"] == "SYNti_m600mV_096/SYNti_m600mV_096.exp"


def test_a_merge_candidate_whose_data_files_agree_says_so(tmp_path):
    src = _template_beamtime(tmp_path, {"SYNti_m600mV_096": "SYNti_m600mV", "SYNti_m600mV_097": "SYNti_m600mV"})
    b = M.load(_import(src, tmp_path / "bundle"))
    [mc] = b["merge_candidates"]
    [caution] = [c for c in mc["caution"] if c["code"] == G.CAUTION_NOTHING_CLASSIFIED]
    assert caution["data_file"] == "SYNti_m600mV"
    assert "each run's own .exp file names the same acquisition (DATA_FILE SYNti_m600mV)" in caution["statement"]
    assert "nothing read from their files shows they are the same measurement" not in caution["statement"]
    assert caution["statement"] in mc["question"]["text"]


# --- M6: no-value questions that quote one comment line are answered at once -------------------------------------


NAME = "context.electrochemistry.electrolyte.name"
SAME_LINE = "Sample A in 1M KOH 0Vrhe"


@pytest.fixture()
def repeated(tmp_path):
    src = tmp_path / "SYN_bt43"
    for k in range(3):
        make_scan(src / f"0{k + 1}_SYNti_sample{k + 1}_m600mV_{96 + k:03d}_A.001", free_text=("SYN gain 1e8", SAME_LINE))
    make_scan(src / "09_SYNti_other_m600mV_099_A.001", free_text=("SYN gain 1e8", "Sample B in 1M KOH 0Vrhe"))
    return _import(src, tmp_path / "bundle")


def _name_questions(b: dict) -> list[dict]:
    return [q for q in Q.consolidate(b)["questions"] if q["target_field_path"] == NAME and q["kind"] == "confirm_value"]


def test_a_no_value_question_says_it_asks_for_a_value_under_its_kind(repeated):
    qs = _name_questions(M.load(repeated))
    assert len(qs) == 4 and all(q["no_value"] for q in qs)
    for q in qs:
        assert "There is nothing to confirm" not in q["text"] and "this asks for one (no_value)" in q["text"]
        assert q["allowed_decisions"] == list(Q.VALUELESS_DECISIONS)


def test_questions_that_quote_one_line_share_a_group_and_say_so(repeated):
    qs = _name_questions(M.load(repeated))
    same = [q for q in qs if SAME_LINE in q["text"]]
    [other] = [q for q in qs if q not in same]
    assert len(same) == 3 and len({q["same_reading_group"] for q in same}) == 1
    assert all(q["same_reading_count"] == 3 for q in same) and "same_reading_group" not in other
    q = same[0]
    assert f"--question {q['question_id']} --same-reading --decision correct" in q["same_reading_command"]
    assert "2 other question(s) ask the" in q["text"] and "template's File List columns are the easy path" in q["text"]


def test_one_decide_answers_every_question_of_the_group(repeated):
    qs = [q for q in _name_questions(M.load(repeated)) if SAME_LINE in q["text"]]
    ids_before = sorted(q["question_id"] for q in qs)
    got = M.decide_question(repeated, question_id=qs[0]["question_id"], same_reading=True, decision="correct",
                            value="KOH", by=WHO, orcid=None)
    targets = sorted(t["id"] for q in qs for t in q["targets"])
    assert sorted(got["recorded"]) == targets
    left = _name_questions(M.load(repeated))
    assert len(left) == 1 and left[0]["question_id"] not in ids_before  # the other line's question stays open


def test_same_reading_is_refused_where_it_does_not_apply(repeated, capsys):
    qs = _name_questions(M.load(repeated))
    [other] = [q for q in qs if SAME_LINE not in q["text"]]
    with pytest.raises(M.MutationRefused, match="names no same_reading_group"):
        M.decide_question(repeated, question_id=other["question_id"], same_reading=True, decision="correct",
                          value="KOH", by=WHO, orcid=None)
    same = next(q for q in qs if q.get("same_reading_group"))
    with pytest.raises(M.MutationRefused, match="does not take --only"):
        M.decide_question(repeated, question_id=same["question_id"], same_reading=True, only=same["scope"],
                          decision="correct", value="KOH", by=WHO, orcid=None)
    assert cli.main(["bundle", "decide", str(repeated), "--target", "cand-0001", "--same-reading", "--decision",
                     "correct", "--value", "KOH", "--by", WHO]) != 0
    assert "--same-reading goes with --question" in capsys.readouterr().err
