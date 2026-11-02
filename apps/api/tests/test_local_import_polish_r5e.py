"""r5 real-data walk, fixer E (questions / template). Synthetic data only.

M1  A sample field asked per group because each group's partition is its whole file name (``sample_name_stem``) is
    batched: groups whose names share every SAMPLE token (never a counter, a set-point, a pH, an electrolyte or another
    condition) share a ``same_reading_group``, answered with ``--same-reading``. A related reading made for another
    sample's group is no hint.
H1  The potential scale and the control mode stay asked per group (DEC-90). For each, the groups whose own AI readings
    of the field agree are batched (``same_reading_by_field``), answered with ``--field <path> --same-reading``; never
    an open-circuit run with a potential hold, a reference or ex-situ group, or a group with differing or no readings.
L1  A temperature, duration, gas or state word, or a code like ``3MOF``, is a sample token unless the parser read it.
L2  A °F value and a range each have their own refusal; ``℃`` is read as °C.
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
    ("SYNcat_10MNaOH_m800mV_OCV_again_2", ["SYNcat"]),
    ("ZZ_0p5VRHE_100mMHClO4_1M", ["ZZ"]),
    ("01_02_pH2_400mV", []),
])
def test_sample_tokens_leave_out_conditions_counters_and_numbers(stem, tokens):
    assert G.sample_name_tokens(stem) == tokens


def test_a_token_the_runs_parser_read_as_a_condition_is_no_sample_token():
    assert G.sample_name_tokens("Q4_SYNcat_5wp", read_as_condition={"5wp"}) == ["Q4", "SYNcat"]
    assert G.sample_name_tokens("PtC_400C_01", read_as_condition={"400c"}) == ["PtC"]


#: r5e L1: a temperature, duration, gas or state word, or a code like 3MOF, can name the sample: these names differ
@pytest.mark.parametrize("a, b", [
    ("SYNPtC_400C_01", "SYNPtC_600C_01"), ("SYNTiO2_2h", "SYNTiO2_12h"), ("SYNPt_H2", "SYNPt_O2"),
    ("SYNNiFe_fresh", "SYNNiFe_aged"), ("SYNIrO2_3MOF", "SYNIrO2_5MOF"),
])
def test_names_that_differ_in_a_token_no_parser_read_as_a_condition_keep_their_sample_tokens_apart(a, b):
    assert G.sample_name_tokens(a) != G.sample_name_tokens(b)
    qs, bundle = _hand([a, b])
    Q._note_shared_sample_tokens(qs, bundle)
    assert not any(q.get("same_reading_group") for q in qs)


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


# --- H1: scale and mode stay per group; groups whose own AI readings agree are batched per field ---------------------

#: one OPEN-CIRCUIT run among potential holds; every group is its own (DEC-90: scale and mode are asked per group)
H1_STEMS = ["Q4_01_SYNcat_pH2_400mV", "Q4_02_SYNcat_pH2_1400mV", "Q4_03_SYNcat_pH2_OCV", "Q4_04_SYNcat_pH2_600mV",
            "Q4_05_SYNcat_pH2_800mV", "Q4_06_SYNcat_pH2_200mV"]


@pytest.fixture(scope="module")
def holds_pristine(tmp_path_factory):
    b = _grouped_stems(tmp_path_factory.mktemp("r5e-h1"), H1_STEMS)
    bd = M.load(b)
    src = {s["source_id"]: s for s in bd["sources"]}
    said = {"Q4_01": "RHE", "Q4_02": "RHE", "Q4_03": "RHE", "Q4_04": "Ag/AgCl", "Q4_06": "RHE"}  # Q4_05: no reading
    findings = []
    for r in bd["runs"]:
        value = next((v for k, v in said.items() if r["stem"].startswith(k)), None)
        if value:
            findings.append({"field_path": SCALE, "value": value, "applies_to": {"scope": "runs", "runs": [r["run_id"]]},
                             "source": {"path": src[r["acquisition_source_id"]]["relative_path"], "locator": "header line 3"},
                             "quote": f"vs {value}", "strength": "stated", "reasoning": "the scan header names the scale"})
    rep = M.annotate_from_readings(b, {"format": "isaac.reading_findings", "findings": findings},
                                   model_id="synthetic-model", apply=True)
    assert rep["interpretations"] >= 5, rep
    return b


@pytest.fixture()
def holds(holds_pristine, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(holds_pristine, target)
    return target


def _per_group(p, field):
    return [q for q in p["questions"] if q["kind"] == "optional_values" and q["scope"].startswith("group:")
            and field in q["fields"]]


def _stem_of_group(b, q):
    keys = next(g["member_run_keys"] for g in b["record_groups"] if g["group_id"] == q["scope"][len("group:"):])
    return next(r["stem"] for r in b["runs"] if r["run_key"] == keys[0])


def test_scale_and_mode_stay_per_group_and_agreeing_groups_share_a_batch_for_the_field(holds):
    b = M.load(holds)
    p = Q.consolidate(b)
    assert not Q._is_shared(SCALE) and not Q._is_shared(MODE)  # DEC-90: never asked once for the beamtime
    qs = _per_group(p, SCALE)
    assert len(qs) == 6 and all(MODE in q["fields"] for q in qs)
    batch = {}
    for q in qs:
        batch.setdefault(((q.get("same_reading_by_field") or {}).get(SCALE) or {}).get("same_reading_group"), []).append(
            _stem_of_group(b, q)[:5])
    # the three RHE potential holds; never the open-circuit run (RHE too), Ag/AgCl, or the group with no reading
    assert sorted(batch.pop(None)) == ["Q4_03", "Q4_04", "Q4_05"]
    [(_, batched)] = batch.items()
    assert sorted(batched) == ["Q4_01", "Q4_02", "Q4_06"]
    q = next(q for q in qs if (q.get("same_reading_by_field") or {}).get(SCALE))
    sr = q["same_reading_by_field"][SCALE]
    assert sr["same_reading_count"] == 3 and f"--same-reading --field {SCALE}" in sr["same_reading_command"]
    assert "groups' own AI readings all suggest 'RHE'" in q["text"]
    assert not any((x.get("same_reading_by_field") or {}).get(MODE) for x in qs)  # no reading of the mode: none
    assert "same_reading_group" not in q  # the question itself is in no batch: only its field


def test_a_reference_group_is_never_batched_in(holds):
    b = M.load(holds)
    gid = next(q["scope"][len("group:"):] for q in _per_group(Q.consolidate(b), SCALE)
               if (q.get("same_reading_by_field") or {}).get(SCALE))
    next(g for g in b["record_groups"] if g["group_id"] == gid)["role"] = "reference"
    qs = _per_group(Q.consolidate(b), SCALE)
    left = [q for q in qs if (q.get("same_reading_by_field") or {}).get(SCALE)]
    assert len(left) == 2 and all(q["scope"] != f"group:{gid}" for q in left)


def test_batching_moves_no_question_id(holds, monkeypatch):
    b = M.load(holds)
    after = {q["question_id"]: (q["scope"], q["targets"]) for q in Q.consolidate(b)["questions"]}
    monkeypatch.setattr(Q, "_note_agreeing_field_hints", lambda questions, bundle: None)
    assert after == {q["question_id"]: (q["scope"], q["targets"]) for q in Q.consolidate(b)["questions"]}


def test_one_same_reading_answer_records_the_field_for_its_batch_only_and_each_group_stays_answerable(holds):
    qs = _per_group(Q.consolidate(M.load(holds)), SCALE)
    q = next(q for q in qs if (q.get("same_reading_by_field") or {}).get(SCALE))
    with pytest.raises(M.MutationRefused, match="give --field"):  # batched for one field, so it names it
        M._same_reading_targets(M.load(holds), q["question_id"], None, MODE, "correct", "potentiostatic")
    got = M.decide_question(holds, question_id=q["question_id"], field=SCALE, decision="correct", value="RHE",
                            by=WHO, orcid=None, same_reading=True)
    assert "--same-reading answered 3 question(s)" in got["statement"], got["statement"]
    b = M.load(holds)
    left = sorted(_stem_of_group(b, x)[:5] for x in _per_group(Q.consolidate(b), SCALE))
    assert left == ["Q4_03", "Q4_04", "Q4_05"]
    # a group outside the batch is answered on its own question id, with --field, as before
    other = next(x for x in _per_group(Q.consolidate(b), SCALE) if _stem_of_group(b, x).startswith("Q4_04"))
    M.decide_question(holds, question_id=other["question_id"], field=SCALE, decision="correct", value="Ag/AgCl",
                      by=WHO, orcid=None)
    assert len(_per_group(Q.consolidate(M.load(holds)), SCALE)) == 2


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
    ("25 °C", 298.15, True), ("25°C", 298.15, True), ("25 ℃", 298.15, True), ("-10 ºC", 263.15, True), ("25 degC", 298.15, True),
    ("298.15 K", 298.15, False), ("300 K", 300, False),
])
def test_a_temperature_is_read_with_its_unit(raw, kelvin, converted):
    value, why, conversion = T.parse_temperature(raw)
    assert why is None and value == pytest.approx(kelvin) and bool(conversion) == converted
    if converted:
        assert conversion["typed"] == raw.strip() and conversion["kelvin"] == pytest.approx(kelvin)


@pytest.mark.parametrize("raw, why", [("77 °F", T.TEMPERATURE_FAHRENHEIT_REFUSAL), ("77 ℉", T.TEMPERATURE_FAHRENHEIT_REFUSAL),
                                      ("25-30 °C", T.TEMPERATURE_RANGE_REFUSAL), ("25 to 30 C", T.TEMPERATURE_RANGE_REFUSAL),
                                      ("25–30°C", T.TEMPERATURE_RANGE_REFUSAL)])
def test_a_fahrenheit_value_and_a_range_each_say_why(raw, why):
    assert T.parse_temperature(raw) == (None, why, None)


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
