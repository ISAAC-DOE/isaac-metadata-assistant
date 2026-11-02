"""r5 real-data walk, fixer E (questions / template). Synthetic data only.

M1  A sample field asked per group because each group's partition is its whole file name (``sample_name_stem``) is
    batched: groups whose names share every SAMPLE token (never a counter, a set-point, a pH, an electrolyte or another
    condition) share a ``same_reading_group``, answered with ``--same-reading``. A related reading made for another
    sample's group is no hint.
M2  The potential scale and the control mode are asked once for the beamtime, beside the cell type.
M3  ``template adopt`` says which Configurations columns it did not read, with their values, and shows the channel the
    scientist's Configurations row states beside a processing result that chose its channel by name (a hint only).
M4  The template has Temperature and Gas Atmosphere columns. A temperature is typed with its unit; °C is converted to
    kelvin and shown in the import preview; a bare number is refused (no unit is guessed).
M5  The deprecated cell type ``three_electrode`` is marked wherever it is listed, and the import preview warns.
L6  ``0mV`` and ``000mV`` are one value: one batch (fixed in r5b; kept here as a regression test).
"""

from __future__ import annotations

import copy
import json
import shutil

import openpyxl
import pytest

from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import template as T

from test_local_import_capture_decisions import _grouped_stems
from test_local_import_polish_r5b import _setpoint_questions
from test_local_import_template_adopt import (  # noqa: F401  (fixtures)
    _adopt, _adopt_json, _their_sheet, corpus, grouped, grouped_base,
)

WHO = "SYNTHETIC TEST"
NAME, FORM = "sample.material.name", "sample.sample_form"
SCALE, MODE, CELL = Q.SCALE_PATH, Q.CONTROL_MODE_PATH, "context.electrochemistry.cell_type"
TEMP, ATMOSPHERE = T.TEMPERATURE_PATH, "context.thermodynamics.atmosphere"
#: names whose sample no source states (the scan index read as a sample number): each group is partitioned by its name
STEMS = ["Q4_01_SYNcat_5wp_pH2_400mV", "Q4_02_SYNcat_5wp_pH2_1400mV", "Q4_03_SYNcat_5wp_pH2_000mV",
         "Q5_01_SYNcat_5wp_pH12_400mV", "Q5_02_SYNcat_5wp_pH12_0mV", "Q3_01_SYNcat_5wt_pH2_500mV"]


@pytest.fixture(scope="module")
def stems_pristine(tmp_path_factory):
    return _grouped_stems(tmp_path_factory.mktemp("r5e"), STEMS)


@pytest.fixture()
def stems(stems_pristine, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(stems_pristine, target)
    return target


def _sample_questions(payload, path):
    return [q for q in payload["questions"] if q["kind"] == "missing_value" and q["target_field_path"] == path]


def _stem_of(b, q):
    run_of = {m["value_id"]: m["run_id"] for m in b["missing_values"]}
    stem = {r["run_id"]: r["stem"] for r in b["runs"]}
    return [stem[run_of[t["id"]]] for t in q["targets"]]


# --- M1: sample questions batched by the sample tokens their names share ----------------------------------------------


@pytest.mark.parametrize("stem, tokens", [
    ("Q4_06_SYNcat_5wp_pH2_000mV", ["Q4", "SYNcat", "5wp"]),
    ("SYNcat_10MNaOH_m800mV_25C_Ar_OCV_again_2", ["SYNcat"]),
    ("ZZ_0p5VRHE_100mMHClO4_30min_CO2sat_after_10_cycles", ["ZZ"]),
    ("Co_SYN_1M_dry", ["Co", "SYN"]),  # cobalt is no gas; a concentration and a state are no sample
    ("01_02_pH2_400mV", []),
])
def test_sample_tokens_leave_out_conditions_counters_and_numbers(stem, tokens):
    assert G.sample_name_tokens(stem) == tokens


def test_a_token_the_runs_parser_read_as_a_condition_is_no_sample_token():
    assert G.sample_name_tokens("Q4_SYNcat_5wp", read_as_condition={"5wp"}) == ["Q4", "SYNcat"]


def test_groups_whose_names_share_every_sample_token_share_one_same_reading_group(stems):
    b = M.load(stems)
    p = Q.consolidate(b)
    for path in (NAME, FORM):
        qs = _sample_questions(p, path)
        assert len(qs) == 6 and all(q["partition"].startswith('sample={"sample_name_stem"') for q in qs)
        by_group: dict = {}
        for q in qs:
            by_group.setdefault(q.get("same_reading_group"), []).append(_stem_of(b, q)[0])
        q4 = sorted(s for g, ss in by_group.items() if g for s in ss if s.startswith("Q4"))
        assert len(q4) == 3 and len({g for g, ss in by_group.items() for s in ss if s.startswith("Q4")}) == 1
        assert sorted(len(ss) for g, ss in by_group.items() if g) == [2, 3]  # Q4 apart from Q5: never one batch
        assert by_group[None] == ["Q3_01_SYNcat_5wt_pH2_500mV"]  # 5wt is not 5wp: alone
    q = next(q for q in _sample_questions(p, NAME) if q.get("same_reading_count") == 3)
    assert "share the same sample tokens ('Q4' 'SYNcat' '5wp'" in q["text"], q["text"]
    assert f"--question {q['question_id']} --same-reading --decision correct" in q["same_reading_command"]
    assert q["shared_sample_tokens"] == ["Q4", "SYNcat", "5wp"]
    assert {m["file_name"] for m in q["same_reading_members"]} == {s for s in STEMS if s.startswith("Q4")}
    # name and form are batched apart
    assert q["same_reading_group"] not in {x.get("same_reading_group") for x in _sample_questions(p, FORM)}


def test_question_ids_scopes_and_targets_do_not_move(stems, monkeypatch):
    b = M.load(stems)
    after = {q["question_id"]: (q["scope"], q["targets"]) for q in Q.consolidate(b)["questions"]}
    monkeypatch.setattr(Q, "_note_shared_sample_tokens", lambda questions, bundle: None)
    before = {q["question_id"]: (q["scope"], q["targets"]) for q in Q.consolidate(b)["questions"]}
    assert after == before


def test_one_same_reading_answer_reaches_every_group_of_its_batch_and_no_other(stems):
    p = Q.consolidate(M.load(stems))
    q = next(q for q in _sample_questions(p, NAME) if q.get("same_reading_count") == 3)
    got = M.decide_question(stems, question_id=q["question_id"], decision="correct", value="SYNTHETIC catalyst",
                            by=WHO, orcid=None, same_reading=True)
    assert "--same-reading answered 3 question(s)" in got["statement"], got["statement"]
    b = M.load(stems)
    left = _sample_questions(Q.consolidate(b), NAME)
    assert sorted(s for x in left for s in _stem_of(b, x)) == sorted(s for s in STEMS if not s.startswith("Q4"))


def _hand(stems_by_group):
    runs = [{"run_id": f"r{i}", "stem": s} for i, s in enumerate(stems_by_group)]
    mvs = [{"value_id": f"m{i}", "run_id": f"r{i}", "target_field_path": NAME} for i in range(len(runs))]
    qs = [{"question_id": f"Q-{i}", "kind": "missing_value", "scope": "experiment", "target_field_path": NAME,
           "partition": 'sample={"sample_name_stem": "%s"}' % s.casefold(), "targets": [{"kind": "missing_value", "id": f"m{i}"}],
           "text": "Q.", "answer_command": f'isaac bundle decide <bundle_dir> --question Q-{i} --decision correct --value <value>'}
          for i, s in enumerate(stems_by_group)]
    return qs, {"runs": runs, "missing_values": mvs, "candidates": []}


@pytest.mark.parametrize("names", [
    ["01_01_pH2_400mV", "02_01_pH2_400mV"],        # nothing but a condition and numbers: never joined on a pH
    ["X1_01_SYNcat_pH2", "X2_01_SYNcat_pH2"],      # a differing sample code keeps them apart
])
def test_names_that_share_only_conditions_or_differ_in_a_sample_token_are_never_batched(names):
    qs, bundle = _hand(names)
    Q._note_shared_sample_tokens(qs, bundle)
    assert not any(q.get("same_reading_group") for q in qs)


def test_only_a_partition_by_the_whole_name_is_batched_here():
    qs, bundle = _hand(["X1_01_SYNcat", "X1_02_SYNcat"])
    Q._note_shared_sample_tokens(qs, bundle)
    assert qs[0]["same_reading_group"] == qs[1]["same_reading_group"]
    qs, bundle = _hand(["X1_01_SYNcat", "X1_02_SYNcat"])
    for q in qs:
        q["partition"] = 'sample={"sample_name": "x1"}'
    Q._note_shared_sample_tokens(qs, bundle)
    assert not any(q.get("same_reading_group") for q in qs)


def test_a_reading_made_for_another_samples_group_is_no_hint(stems):
    b = M.load(stems)
    q3 = next(g for g in b["record_groups"] if g["basis"]["sample"].get("sample_name_stem", {}).get("value", "").startswith("q3"))
    run_of_key = {r["run_key"]: r["run_id"] for r in b["runs"]}
    rid = run_of_key[q3["member_run_keys"][0]]
    # the Q3 group records its own sample reading, and a reading of the name is made for its run
    template = next(c for c in b["candidates"] if c["run_id"] == rid and c.get("observed_literals"))
    cand = {**copy.deepcopy(template), "candidate_id": "cand-zz9", "target_field_path": NAME, "statement_key": "sample_name",
            "observed_literals": ["ZZ9"], "value": None}
    b["candidates"].append(cand)
    q3["basis"]["sample"] = {"sample_name": {"value": "zz9", "kind": "literal", "candidate_ids": ["cand-zz9"]}}
    p = Q.consolidate(b)
    others = [q for q in _sample_questions(p, NAME) + _sample_questions(p, FORM) if "zz9" not in q["partition"]]
    assert len(others) == 10 and not any(h.get("literal") == "ZZ9" for q in others for h in q["hints"])
    # its own group's question still shows it
    own = [q for q in p["questions"] if q.get("target_field_path") == NAME and "zz9" in str(q.get("partition"))]
    assert any(h.get("literal") == "ZZ9" for q in own for h in q["hints"])


# --- M2: scale and mode asked once for the beamtime ---------------------------------------------------------------------


def test_scale_and_mode_are_asked_once_for_the_beamtime_beside_the_cell_type(stems):
    p = Q.consolidate(M.load(stems))
    [beamtime] = [q for q in p["questions"] if q["kind"] == "optional_values" and q["scope"] == "experiment"
                  and q["partition"] is None]
    assert {SCALE, MODE, CELL} <= set(beamtime["fields"])
    assert not any(f in q["fields"] for q in p["questions"] if q["kind"] == "optional_values" and q is not beamtime
                   for f in (SCALE, MODE))


def test_moving_scale_and_mode_changes_no_question_id(stems, monkeypatch):
    b = M.load(stems)
    after = {q["question_id"] for q in Q.consolidate(b)["questions"]}
    monkeypatch.setattr(Q, "SHARED_PATHS", tuple(p for p in Q.SHARED_PATHS if p not in (SCALE, MODE)))
    assert after == {q["question_id"] for q in Q.consolidate(b)["questions"]}


def test_one_answer_records_the_scale_for_every_run(stems):
    p = Q.consolidate(M.load(stems))
    [beamtime] = [q for q in p["questions"] if q["kind"] == "optional_values" and q["scope"] == "experiment"
                  and q["partition"] is None]
    M.decide_question(stems, question_id=beamtime["question_id"], field=SCALE, decision="correct", value="RHE",
                      by=WHO, orcid=None)
    b = M.load(stems)
    scales = [m for m in b["missing_values"] if m["target_field_path"] == SCALE and m["run_id"]]
    assert scales and all(m["value_state"] == "scientist_confirmed" for m in scales)
    assert not any(SCALE in (q.get("fields") or {}) for q in Q.consolidate(b)["questions"])


# --- M3: their Configurations sheet -------------------------------------------------------------------------------------


def _with_config_columns(path):
    wb = openpyxl.load_workbook(path)
    wc = wb["Configurations"]
    wc.delete_rows(1, wc.max_row)
    wc.append(["Config ID", "Technique", "Mode", "Primary Signal Channel", "Normalization Channel", "Energy Calibration"])
    wc.append(["Config_A", "HERFD-XAS", "SYN fluorescence", "SYN_FF1", "I0", "SYN foil at 9999.0 eV"])
    wb.save(path)
    return path


def test_adopt_says_which_configurations_columns_it_did_not_read(grouped, tmp_path, capsys):
    theirs = _with_config_columns(_their_sheet(grouped, tmp_path / "SYN_their_metadata.xlsx"))
    a = _adopt_json(grouped, theirs, tmp_path / "out.xlsx", capsys)
    got = {c["header"]: c for c in a["their_config_columns_not_read"]}
    assert set(got) == {"Mode", "Primary Signal Channel", "Normalization Channel", "Energy Calibration"}
    assert got["Primary Signal Channel"]["values"] == [{"config_id": "Config_A", "cell": "'Configurations'!D2", "value": "SYN_FF1"}]
    assert got["Mode"]["reason"].startswith("no official field")
    code, text, _ = _adopt(grouped, theirs, tmp_path / "out2.xlsx", capsys)
    assert code == 0 and "Your Configurations columns not read (4;" in text
    assert "E 'Normalization Channel' (Config_A 'I0')" in text, text


def _processed(flags, state="needs_review", configs=("Config_A",)):
    runs = [{"run_id": f"run-{i}", "run_key": f"k{i}"} for i in range(len(configs))]
    bundle = {"runs": runs,
              "record_groups": [{"group_id": "g1", "member_run_keys": [r["run_key"] for r in runs], "status": "proposed"}],
              "processing_results": [{"result_id": "p1", "group_id": "g1", "state": state, "review_flags": flags,
                                      "qc": {"statements": {"channel_choice_needs_review": (
                                          "ISAAC chose the fluorescence channel (SYN_DTC)/I0 by column name (the first "
                                          "fluorescence name present), not from a reading of the data.")}}}]}
    return bundle, {r["run_id"]: c for r, c in zip(runs, configs)}


STATED = {"Config_A": {"primary signal channel": ("'Configurations'!D2", "SYN_FF1"),
                       "normalization channel": ("'Configurations'!E2", "I0")},
          "Config_B": {"primary signal channel": ("'Configurations'!D3", "I1")}}


def test_the_channel_their_sheet_states_is_shown_beside_a_channel_chosen_by_name():
    bundle, config_of_run = _processed(["channel_choice_needs_review"])
    [h] = T.channel_hints(bundle, config_of_run, STATED)
    assert (h["isaac_chose"], h["primary_signal_channel"], h["normalization_channel"]) == ("fluorescence (SYN_DTC)/I0", "SYN_FF1", "I0")
    assert "never an answer" in h["note"]
    [line] = T._channel_hint_lines([h])
    assert "chose fluorescence (SYN_DTC)/I0 by column name" in line and "Primary Signal Channel 'SYN_FF1'" in line


@pytest.mark.parametrize("flags, state, configs", [
    ([], "needs_review", ("Config_A",)),                                  # chosen by the selector: nothing to show
    (["channel_choice_needs_review"], "rejected", ("Config_A",)),         # a rejected result
    (["channel_choice_needs_review"], "needs_review", ("Config_A", "Config_B")),  # its runs chose two rows
])
def test_no_channel_hint_without_one_stated_channel_for_a_live_result(flags, state, configs):
    bundle, config_of_run = _processed(flags, state, configs)
    assert T.channel_hints(bundle, config_of_run, STATED) == []


# --- M4: temperature and gas atmosphere ---------------------------------------------------------------------------------


@pytest.mark.parametrize("raw, kelvin, converted", [
    ("25 °C", 298.15, True), ("25°C", 298.15, True), ("-10 ºC", 263.15, True), ("25 degC", 298.15, True),
    ("298.15 K", 298.15, False), ("300 K", 300, False),
])
def test_a_temperature_is_read_with_its_unit(raw, kelvin, converted):
    value, why, conversion = T.parse_temperature(raw)
    assert why is None and value == pytest.approx(kelvin) and bool(conversion) == converted
    if converted:
        assert conversion["typed"] == raw.strip() and conversion["kelvin"] == pytest.approx(kelvin)


@pytest.mark.parametrize("raw", [25, 25.0, "25", "warm", "-300 °C", "0 K"])
def test_a_temperature_without_a_unit_or_below_absolute_zero_is_refused(raw):
    value, why, _ = T.parse_temperature(raw)
    assert value is None and why
    if not isinstance(raw, str) or raw == "25":
        assert why == T.TEMPERATURE_UNIT_REFUSAL


def test_the_template_has_temperature_and_gas_atmosphere_appended():
    headers = [c.header for c in T.FILE_COLUMNS]
    assert headers[-2:] == ["Temperature", "Gas Atmosphere"]
    assert {c.header: c.path for c in T.FILE_COLUMNS}["Temperature"] == TEMP
    assert {c.header: c.path for c in T.FILE_COLUMNS}["Gas Atmosphere"] == ATMOSPHERE
    assert T.FORMAT_VERSION == "1.5.0"
    assert [c.header for c in T.file_columns_of("1.4.0")][-1] == "Reaction Catalysis"


def _exported(b, tmp_path):
    out = tmp_path / "t.xlsx"
    assert cli.main(["bundle", "template", "export", str(b), "--out", str(out)]) == 0
    return out


def _col(header):
    return T._letter([c.header for c in T.FILE_COLUMNS].index(header) + 1)


def test_a_celsius_value_is_converted_shown_in_the_preview_and_recorded_in_kelvin(stems, tmp_path):
    x = _exported(stems, tmp_path)
    wb = openpyxl.load_workbook(x)
    ws = wb["File List"]
    ws[f"{_col('Temperature')}2"], ws[f"{_col('Temperature')}3"] = "25 °C", 25
    ws[f"{_col('Gas Atmosphere')}2"] = "Ar"
    wb.save(x)
    rep = T.import_template(stems, x, by=WHO)
    [conv] = rep["unit_conversions"]
    assert conv["cell"] == f"'File List'!{_col('Temperature')}2" and conv["kelvin"] == pytest.approx(298.15)
    assert any(c["cell"] == f"'File List'!{_col('Temperature')}3" and c["reason"] == T.TEMPERATURE_UNIT_REFUSAL
               for c in rep["invalid_cells"])
    text = T.render_report(rep)
    assert "Would convert to kelvin (you typed °C; read each back before --apply):" in text
    assert f"'File List'!{_col('Temperature')}2" in text and "'25 °C' -> 298.15 K" in text
    temps = [d for d in rep["decisions"] if d["target_field_path"] == TEMP]
    assert [d["value"] for d in temps] == [pytest.approx(298.15)]
    assert any(d["target_field_path"] == ATMOSPHERE and d["value"] == "Ar" for d in rep["decisions"])
    rep = T.import_template(stems, x, by=WHO, apply=True)
    b = M.load(stems)
    [m] = [m for m in b["missing_values"] if m["target_field_path"] == TEMP and m["value_state"] == "scientist_confirmed"]
    d = next(d for d in b["scientist_decisions"] if (d.get("target") or {}).get("id") == m["value_id"])
    assert d["value"] == pytest.approx(298.15)


def _with_columns(path, extra):
    wb = openpyxl.load_workbook(path)
    wf = wb["File List"]
    start = wf.max_column + 1
    for k, (header, value) in enumerate(extra):
        wf.cell(row=1, column=start + k, value=header)
        for r in range(2, wf.max_row):  # every run row (the last row names no run)
            wf.cell(row=r, column=start + k, value=value)
    wb.save(path)
    return path


def test_adopt_reads_a_temperature_header_that_states_its_unit_and_never_guesses_one(grouped, tmp_path, capsys):
    theirs = _with_columns(_their_sheet(grouped, tmp_path / "SYN_their_metadata.xlsx"),
                           [("Temperature (°C)", 25), ("Gas atmosphere", "Ar")])
    a = _adopt_json(grouped, theirs, tmp_path / "out.xlsx", capsys)
    mapped = {m["header"]: m["to"] for m in a["their_columns_mapped"]}
    assert mapped["Temperature (°C)"] == "Temperature" and mapped["Gas atmosphere"] == "Gas Atmosphere"
    # their own `Temperature ©` (the sheet's last own column) states no unit: not read, and said why
    [c] = [c for c in a["their_columns_not_read"] if c["header"] == "Temperature ©"]
    assert c["reason"] == T.TEMPERATURE_NO_UNIT_REASON
    ws = openpyxl.load_workbook(tmp_path / "out.xlsx")["File List"]
    temps = {ws[f"{_col('Temperature')}{r}"].value for r in range(2, ws.max_row + 1)} - {None}
    assert temps == {"25 °C"}  # written as typed, with the unit the header states: the import converts it
    assert {ws[f"{_col('Gas Atmosphere')}{r}"].value for r in range(2, ws.max_row + 1)} - {None} == {"Ar"}
    code, text, _ = _adopt(grouped, theirs, tmp_path / "out2.xlsx", capsys)
    assert code == 0 and "'©' is not read as °C" in text


# --- M5: the deprecated cell type ---------------------------------------------------------------------------------------


def test_adopt_marks_the_deprecated_cell_type_where_it_lists_the_allowed_values(grouped, tmp_path, capsys):
    theirs = _with_columns(_their_sheet(grouped, tmp_path / "SYN_their_metadata.xlsx"),
                           [("Cell Type", "SYN_static_cell")])
    a = _adopt_json(grouped, theirs, tmp_path / "out.xlsx", capsys)
    assert "three_electrode" in a["allowed_values"]["Cell Type"]  # still allowed: the list is unchanged
    assert a["deprecated_values"]["Cell Type"]["three_electrode"].startswith("deprecated: use ")
    wd = openpyxl.load_workbook(tmp_path / "out.xlsx")["Disagreements"]
    listed = next(wd.cell(row=r, column=2).value for r in range(1, wd.max_row + 1) if wd.cell(row=r, column=1).value == "Cell Type")
    assert "three_electrode (deprecated: use " in listed
    code, text, _ = _adopt(grouped, theirs, tmp_path / "out2.xlsx", capsys)
    assert code == 0 and "three_electrode (deprecated: use " in text


def test_the_import_preview_warns_about_a_deprecated_term(stems, tmp_path):
    x = _exported(stems, tmp_path)
    wb = openpyxl.load_workbook(x)
    wb["File List"][f"{_col('Cell Type')}2"] = "three_electrode"
    wb.save(x)
    rep = T.import_template(stems, x, by=WHO)
    [d] = rep["deprecated_terms"]
    assert (d["value"], d["cells"]) == ("three_electrode", [f"'File List'!{_col('Cell Type')}2"])
    text = T.render_report(rep)
    assert "Deprecated terms (would be recorded as you typed them; the portal warns about each):" in text
    assert "DEPRECATED_CELL_TYPE" in text
    assert any(x["target_field_path"] == CELL and x["value"] == "three_electrode" for x in rep["decisions"])  # still recorded


def test_the_questions_page_names_the_deprecated_term_beside_its_field(stems, capsys):
    capsys.readouterr()
    assert cli.main(["bundle", "questions", str(stems), "--limit", "200"]) == 0
    page = json.loads(capsys.readouterr().out)
    assert "three_electrode" in page["allowed_values_by_field"][CELL]
    assert page["deprecated_values_by_field"][CELL]["three_electrode"].startswith("deprecated: use ")


# --- L6: 0mV and 000mV are one value ------------------------------------------------------------------------------------


def test_zero_written_two_ways_is_one_batch(monkeypatch):
    cands, qs, bundle = _setpoint_questions([("0mV", 0.0), ("000mV", 0.0), ("400mV", 0.4)])
    monkeypatch.setattr(Q, "file_name_readings",
                        lambda bundle, run, path: T.name_token_readings([run["stem"]], path))
    Q._note_shared_reading_groups(qs, cands, bundle, {})
    assert qs[0]["same_reading_group"] == qs[1]["same_reading_group"] and "same_reading_group" not in qs[2]
