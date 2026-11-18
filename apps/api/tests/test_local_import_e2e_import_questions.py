"""The import, grouping and question problems an end-to-end run on five real beamtimes found (18 Nov 2026). SYNTHETIC
files only: every name is ``SYN``/``ZZ``-prefixed or an invented counter, every value is invented.

1. **BL4-3 alignment, foil and calibration runs are not measurement runs.** An SSRL EXAFS Data Collector (XDC) run
   named like an alignment (``align_data_071``, ``00_Tifoil_rough_072``), a reference foil (``31_Ti_foil_I1_120``,
   ``01_Tifoil_calib_075``) or whose every scan header says so (``Alignment experiment``, an ``align.argn`` region
   file, a ``Ti foil`` comment line) is marked ``run_candidate: false`` at import, as the SPEC classifier marks an
   alignment file, so its group says ``cannot_export_reason: not_a_measurement_run``, record questions do not span
   it and it is never "the nearest group to a record". A standard (``std_``) and a foil ELECTRODE named with a
   condition stay measurements.
2. **Technique hints never show code.** A macro or script name (``ZzL3_xas`` from a ``def`` line, ``Zz_XAS.mac``
   from a ``qdo`` line, ``syn_helper(dir,`` from a Python helper) is not a technique: it is left out of the hints of
   every ``system.technique`` question, and the question says how many it left out. Question ids are unchanged.
3. **A file-name number is not called an electrode before anyone says so.** In ``ZZNPs_on_Au_3_10_m1000mV`` the
   importer's ordinal rule reads ``10`` as the "sample or electrode number" (the rule holds where a name LEADS with
   its run number, DEC-47). The sample question says "file-name number '10' (the 5th token of …)" instead, and a
   ``set_counter_positions`` answer naming that position takes the number out of the group's sample reading.
4. **The nearest group** prefers a sample group over a reference or alignment group that needs as many answers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import suggestions as S

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_import_reader_ssrl_xdc import make_scan  # noqa: E402
from test_local_import_quick_merges import _spec_run  # noqa: E402

WHO = "SYN Scientist"


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    """The vendored schema basis (no portal validator installed, as in CI)."""
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


def xdc(path: Path, *, free_text=("1x1 mm beam", "SYN sample line"), region="synthetic.rgn",
        detector="synthetic.det") -> Path:
    """An XDC 4.0 text scan with the given region and detector file names (header lines 5 and 4)."""
    make_scan(path, free_text=free_text)
    raw = path.read_text(encoding="latin-1")
    raw = raw.replace("synthetic.rgn".ljust(40), region.ljust(40), 1).replace("synthetic.det".ljust(40), detector.ljust(40), 1)
    path.write_text(raw, encoding="latin-1")
    return path


def _import_and_group(src: Path, out: Path, capsys) -> dict:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    capsys.readouterr()
    data = M.load(out)
    assert B.validate_bundle(data) == []
    return data


# --- 1. XDC alignment, foil and calibration runs ------------------------------------------------------------------

#: HEADER evidence only takes a run out of the measurements (run_candidate false)
NOT_MEASUREMENT = {
    "SYNscan_090": "alignment",               # every scan says "Alignment experiment" / align.argn
    "SYNscan_091": "reference",               # every scan's comment line is "Ti foil"
}
#: a NAME only PROPOSES a role (as for SPEC): the run stays a measurement and its group can become a record
NAME_PROPOSED = {
    "00_Tifoil_rough_072": "alignment",      # `rough` beside a foil token
    "01_Tifoil_calib_1x3mm_075": "reference",  # an element + foil, and calib
    "31_Ti_foil_I1_120": "reference",          # a `foil` token
    "align_data_071": "alignment",            # `align`
}
#: names that put a foil, a substrate or a support beside a sample word or a condition, or only LOOK like a word
#: of the rule: no proposal, plain samples
SAMPLE_NAMES = ("Cu_on_Ti_foil_01", "SYN_Pt_foil_annealed_500C_02", "NiFoil_pristine", "Cufoil_after_cycling",
                "foil_supported_Pt_NPs", "aligned_SYNCNT_03", "Pt_rough_02", "calibrated_ZnO_film")
MEASUREMENT = ("03_SYNZZ_1x1mm_081", "29_SYN_std_ZZ_sucrose_116", "12_SYNZZ_Nifoil_electrode_1MKOH_500mV_093",
               "SYNscan_092", "std_Ti_foil", *SAMPLE_NAMES, *NAME_PROPOSED)


def _bl43(src: Path) -> Path:
    for stem in (*NAME_PROPOSED, *SAMPLE_NAMES, "std_Ti_foil"):
        xdc(src / f"{stem}_A.001")
    xdc(src / "SYNscan_090_A.001", free_text=("Alignment experiment", "trans_e.adet"), region="align.argn",
        detector="xsp7sca1.adet")
    xdc(src / "SYNscan_091_A.001", free_text=("i0 2e8 100pA", "1x2 mm beam", "Ti foil"), region="TiEdge_Foil.rgn")
    xdc(src / "SYNscan_091_A.002", free_text=("i0 2e8 100pA", "1x2 mm beam", "Ti foil"), region="TiEdge_Foil.rgn")
    for stem in ("03_SYNZZ_1x1mm_081", "29_SYN_std_ZZ_sucrose_116", "12_SYNZZ_Nifoil_electrode_1MKOH_500mV_093"):
        xdc(src / f"{stem}_A.001")
    # header evidence on ONE scan of two is not enough: the run stays a measurement
    xdc(src / "SYNscan_092_A.001", free_text=("Alignment experiment",), region="align.argn")
    xdc(src / "SYNscan_092_A.002", free_text=("SYN ZZ sample in 1M KOH",), region="SYN_XANES.rgn")
    return src


@pytest.fixture()
def bl43(tmp_path, capsys):
    src = _bl43(tmp_path / "src" / "SYN_BL43_2099-01_ZZ")
    return _import_and_group(src, tmp_path / "out", capsys), tmp_path / "out"


def _group_of(data):
    return {g["member_run_keys"][0].split(":", 1)[1]: g for g in data["record_groups"]}


def test_only_header_evidence_takes_an_xdc_run_out_of_the_measurements(bl43):
    data, _ = bl43
    by_stem = {r["stem"]: r for r in data["runs"]}
    assert set(by_stem) == set(NOT_MEASUREMENT) | set(MEASUREMENT)
    for stem, role in NOT_MEASUREMENT.items():
        run = by_stem[stem]
        assert run["run_candidate"] is False, stem
        said = run["other_relationships"]["not_a_measurement"]
        assert said["role"] == role and said["rule_id"] == G.XDC_NOT_MEASUREMENT_RULE_ID, stem
        assert said["basis"] == "scan_header" and said["evidence"]
    for stem in MEASUREMENT:
        assert by_stem[stem]["run_candidate"] is True, stem
        assert "not_a_measurement" not in by_stem[stem]["other_relationships"], stem
    header = by_stem["SYNscan_090"]["other_relationships"]["not_a_measurement"]
    assert {e["source_relative_path"] for e in header["evidence"]} == {"SYNscan_090_A.001"}
    # no missing value is asked of a run that is not a measurement; a name-proposed run is asked as any other
    ids = {by_stem[s]["run_id"] for s in NOT_MEASUREMENT}
    assert not [m for m in data["missing_values"] if m["run_id"] in ids]
    for stem in NAME_PROPOSED:
        assert [m for m in data["missing_values"] if m["run_id"] == by_stem[stem]["run_id"]], stem


def test_a_name_only_proposes_a_role_said_as_judged_from_the_name(bl43):
    data, out = bl43
    role_of = _group_of(data)
    rows = cli.group_list_extras(data)
    reasons = Q.cannot_export_reasons(data)
    for stem, role in NAME_PROPOSED.items():
        g = role_of[stem]
        assert g["role"] == role and g["role_basis"]["basis"] in ("name_token", "element_name_token"), stem
        assert rows[g["group_id"]]["role_proposed"] == {"role": role, "judged_from": "file name",
                                                         "token": g["role_basis"]["token"], "note": G.NAME_ROLE_NOTE}
        assert g["group_id"] not in reasons, stem  # it can still become a record
    assert "say if this is a sample" in G.NAME_ROLE_NOTE
    for stem in SAMPLE_NAMES:
        assert role_of[stem]["role"] == "sample", stem
        assert "role_proposed" not in rows[role_of[stem]["group_id"]], stem
    assert role_of["std_Ti_foil"]["role"] == "reference"  # a standard: proposed as one, still a measurement
    for stem, role in NOT_MEASUREMENT.items():
        assert role_of[stem]["role"] == role and role_of[stem]["role_basis"]["basis"] == "scan_header", stem
        assert reasons.get(role_of[stem]["group_id"]) == "not_a_measurement_run", stem
    for stem in MEASUREMENT:
        assert role_of[stem]["group_id"] not in reasons, stem


def test_a_name_proposed_group_the_scientist_confirms_is_composed_like_any_record(bl43):
    data, out = bl43
    g = _group_of(data)["31_Ti_foil_I1_120"]
    M.decide(out, target_ids=[g["group_id"]], decision="confirm", value=None, by=WHO, orcid=None)
    data = M.load(out)
    assert g["group_id"] not in Q.not_a_measurement_groups(data)
    assert g["group_id"] not in Q.cannot_export_reasons(data)
    payload = Q.consolidate(data)
    reached = {sc[len("group:"):] for q in payload["questions"] if q.get("target_field_path") == "sample.material.name"
               for sc in q["per_scope_targets"] if sc.startswith("group:")}
    assert g["group_id"] in reached  # its sample question is asked, so an answer reaches its record


def test_record_questions_skip_only_header_excluded_groups_and_the_nearest_group_is_a_sample(bl43):
    data, _ = bl43
    payload = Q.consolidate(data)
    measured = {g["group_id"] for g in data["record_groups"]
                if g["member_run_keys"][0].split(":", 1)[1] in MEASUREMENT}
    for path in ("sample.material.name", "sample.sample_form", "context.environment"):
        qs = [q for q in payload["questions"] if q.get("target_field_path") == path and q["kind"] == "missing_value"]
        assert qs, path
        reached = {sc[len("group:"):] for q in qs for sc in q["per_scope_targets"] if sc.startswith("group:")}
        assert reached <= measured, path
        assert sum(q["applies_to"]["groups"] for q in qs) == len(measured), path
    minimum = Q.minimum_answers_for_one_group(payload, data)
    nearest = next(g for g in data["record_groups"] if g["group_id"] == minimum["group_id"])
    assert nearest["role"] == "sample" and nearest["group_id"] in measured


def test_the_summary_says_why_a_run_is_not_a_run(bl43):
    _, out = bl43
    summary = (out / "summary.md").read_text()
    assert "not a run (alignment)" in summary and "not a run (reference)" in summary


@pytest.mark.parametrize("stem, expected", [
    ("align_data_071", "alignment"),
    ("SYN_alignment_3", "alignment"),
    ("00_Zrfoil_rough_072", "alignment"),
    ("align_rough_01", "alignment"),
    ("01_Tifoil_calib_1x3mm_075", "reference"),
    ("31_Ti_foil_I2_120", "reference"),
    ("00_S_SYN_calib_001", "reference"),
    ("SCALIB_901", "reference"),
    ("08_std_ZZSO4_sucrose_029", "reference"),  # a standard: the shared reference words, still a measurement
    ("std_Ti_foil", "reference"),
    *[(stem, None) for stem in SAMPLE_NAMES],
    ("12_SYN_Nifoil_electrode_1MKOH_500mV", None),
    ("O4_01_SYNNPs_pH2_400mV_calib", None),
    ("SYN_roughness_study", None),
    ("SYN_rough_002", None),
    ("SYNsample_01", None),
    ("ZZcalibration_curve_sample", None),
])
def test_the_xdc_name_rule_proposes_only_whole_words_and_never_beside_a_sample_word(stem, expected):
    got = G.xdc_name_role(stem)
    assert (got or (None,))[0] == expected
    assert G.xdc_not_a_measurement(stem, []) is None  # a name alone never takes a run out


@pytest.mark.parametrize("stem, statements, expected", [
    # header evidence: every scan must carry it
    ("SYN_01", [{"key": "free_text", "literal": "Alignment experiment", "source_relative_path": "a.001", "locator": "line:9"}], "alignment"),
    ("SYN_01", [{"key": "region_file", "literal": "align.argn", "source_relative_path": "a.001", "locator": "line:5"}], "alignment"),
    ("SYN_01", [{"key": "header_line_8_literal", "literal": "Alignment experiment", "source_relative_path": "a.001", "locator": "line:8"}], "alignment"),
    ("std_Ti_foil", [{"key": "free_text", "literal": "Ti foil", "source_relative_path": "a.001", "locator": "line:10"}], "reference"),
    ("SYN_01", [{"key": "free_text", "literal": "Cu foil", "source_relative_path": "a.001", "locator": "line:10"}], "reference"),
    ("SYN_01", [{"key": "free_text", "literal": "SYN sample A next to the Ti foil", "source_relative_path": "a.001", "locator": "line:10"}], None),
    ("SYN_01", [{"key": "region_file", "literal": "TiEdge_Foil.rgn", "source_relative_path": "a.001", "locator": "line:5"}], None),
    ("SYN_01", [{"key": "free_text", "literal": "Alignment experiment", "source_relative_path": "a.001", "locator": "line:9"},
                {"key": "free_text", "literal": "SYN sample", "source_relative_path": "a.002", "locator": "line:9"}], None),
])
def test_the_header_rule_needs_every_scan(stem, statements, expected):
    got = G.xdc_not_a_measurement(stem, statements)
    assert (got or {}).get("role") == expected


# --- 2. technique hints never show code ---------------------------------------------------------------------------


@pytest.mark.parametrize("literal, locator, path, code", [
    # code that names no technique: left out
    ("trigger", "line 1 `def`", "trigger.mac", True),
    ("extract_voltage_and_save(target_directory,", "line 5 `def`", "extract_names.py", True),
    ("list_folders_to_csv", "line 9 `def`", "extract_names.py", True),
    ("syn_helper", "line 4", "notes.txt", True),
    ("scans/SYN_run/plot.py", "line 2", "notes.txt", True),
    ("1x1 mm beam", "line:9", "SYN_A.001", False),  # no technique word, but no code either: kept
    # a technique word, found FIRST, keeps the hint however it is written
    ("IrL3_xas", "line 1 `def`", "Ir_XAS.mac", False),
    ("Pt_XAS.mac", "line 1 `qdo` (before any newfile declaration)", "run34.mac", True),  # a macro file: a path
    ("HERFD_XAS", "line:9", "SYN_A.001", False),
    ("Kbeta_XES", "filename token 1", "SYN_Kbeta_XES_01", False),
    ("cyclic_voltammetry", "line:9", "SYN_A.001", False),  # the schema's own values
    ("uv_vis", "line:9", "SYN_A.001", False),
    ("XANES,EXAFS", "line:9", "SYN_A.001", False),
    ("fluorescence XAS (Lytle)", "line:9", "SYN_A.001", False),
    ("XAS", "filename token 2", "SYN_XAS_01", False),
    ("HERFD-XAS", "line:9", "SYN_A.001", False),
    ("Pt L3 XANES in fluorescence", "line:9", "SYN_A.001", False),
])
def test_a_technique_hint_is_kept_only_when_it_names_a_technique(literal, locator, path, code):
    assert S.technique_hint_is_code({"literal": literal, "locator": locator, "relative_path": path}) is code


@pytest.fixture(scope="module")
def semantics(tmp_path_factory):
    from test_local_import_records import SEMANTICS

    out = tmp_path_factory.mktemp("e2e_sem") / "grouped"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    assert cli.main(["bundle", "group", str(out)]) == 0
    return out


def test_no_technique_question_shows_a_macro_name_as_a_hint_and_ids_are_unchanged(semantics):
    payload = Q.consolidate(M.load(semantics))
    tech = [q for q in payload["questions"] if q.get("target_field_path") == "system.technique"]
    assert {q["question_id"] for q in tech} >= {"Q-1e7239d292", "Q-fcaac501d9", "Q-d5ac0f28c7"}  # ids unchanged
    hidden = 0
    for q in tech:
        for h in q["hints"]:
            assert h["kind"] not in ("file_literal", "related_reading", "reading") or not S.technique_hint_is_code(h), h
        hidden += q.get("code_hints_left_out", 0)
        if q.get("code_hints_left_out"):
            assert "macro or script name" in q["text"]
            if not [h for h in q["hints"] if h["kind"] in ("file_literal", "related_reading", "reading")]:
                assert "see the hints" not in q["text"]
    assert hidden
    # a macro name that NAMES a technique is kept (a technique word is looked for first), cited where it was read
    kept = [h for q in tech for h in q["hints"] if h["kind"] == "file_literal"]
    assert ("ZzL3_xas", "Zz_XAS.mac", "line 3 `def`") in {(h["literal"], h["relative_path"], h["locator"]) for h in kept}


# --- 3. a file-name number is not an electrode before anyone says so ------------------------------------------------


def _counters(src: Path) -> Path:
    # two names whose 5th token is the run counter 10 under different electrodes (3 and 5), and one more of 3
    for stem in ("ZZNPs_on_Au_3_10_m1000mV", "ZZNPs_on_Au_5_10_400mV", "ZZNPs_on_Au_3_11_1500mV"):
        _spec_run(src, stem)
    return src


@pytest.fixture()
def counters(tmp_path, capsys):
    src = _counters(tmp_path / "src" / "SYN_BL62_2099-01_Counters")
    _import_and_group(src, tmp_path / "out", capsys)
    return tmp_path / "out"


def _sample_questions(payload, path="sample.material.name"):
    return [q for q in payload["questions"] if q.get("target_field_path") == path and q["kind"] == "missing_value"]


def test_before_any_answer_the_sample_question_does_not_call_the_number_an_electrode(counters):
    data = M.load(counters)
    readings = {c["observed_literals"][0] for c in data["candidates"] if c["statement_key"] == "sample_or_electrode_number"}
    assert "10" in readings  # the importer's ordinal reading, unchanged
    [shared] = [q for q in _sample_questions(Q.consolidate(data)) if q["applies_to"]["groups"] == 2]
    assert "electrode number" not in shared["text"]
    assert "file-name number '10'" in shared["text"] and "5th token" in shared["text"]
    assert "whether it names an electrode or counts runs is not yet said" in shared["text"]


def test_a_dec47_name_that_leads_with_its_run_number_keeps_its_words():
    # the wording rule: the second number of a name that LEADS with a number is the DEC-47 electrode reading
    assert Q.sample_number_words("05_06_SYNZZ_acid_400mV", {"locator": "filename token 1 [chars 3..5]",
                                                           "relative_path": "05_06_SYNZZ_acid_400mV"}) is None
    words = Q.sample_number_words("ZZNPs_on_Au_3_10_m1000mV", {"locator": "filename token 4 [chars 14..16]",
                                                              "relative_path": "ZZNPs_on_Au_3_10_m1000mV"})
    assert words == ("file-name number", "the 5th token of ZZNPs_on_Au_3_10_m1000mV; whether it names an electrode or "
                                         "counts runs is not yet said")


def test_a_confirmed_counter_position_takes_the_number_out_of_the_sample_reading(counters, capsys):
    before = {g["group_id"]: g for g in M.load(counters)["record_groups"]}
    assert any("sample_or_electrode_number" in g["basis"]["sample"] for g in before.values())
    assert cli.main(["bundle", "decide", str(counters), "--target", "experiment", "--decision", "set_counter_positions",
                     "--positions", "5", "--by", WHO]) == 0
    assert cli.main(["bundle", "group", str(counters), "--regroup"]) == 0
    capsys.readouterr()
    data = M.load(counters)
    assert B.validate_bundle(data) == []
    stems = {r["run_key"]: r["stem"] for r in data["runs"]}
    for g in data["record_groups"]:
        if g.get("status") in ("rejected", "split", "merged"):
            continue
        sample = g["basis"]["sample"]
        assert "sample_or_electrode_number" not in sample, g["member_run_keys"]
        assert sample["sample_name_stem"]["sample_key_basis"] == "name_stem"
        assert "10" not in sample["sample_name_stem"]["value"].split("_")
        issue = [i for i in g["engine_reading_issues"] if i["code"] == G.COUNTER_READ_AS_SAMPLE_NUMBER]
        assert issue and issue[0]["position"] == 5, [stems[k] for k in g["member_run_keys"]]
    payload = Q.consolidate(data)
    for q in _sample_questions(payload):
        assert "'10'" not in q["text"] and "electrode number" not in q["text"]
        assert q["applies_to"]["groups"] == 1  # electrodes 3 and 5 no longer share one "sample reading"


def _number_candidate(stem, *, truncated, extra=()):
    own = {"locator": "filename token 4 [chars 14..16]", "relative_path": stem, "literal_value": "10"}
    scan = {"locator": "filename token 4 [chars 14..16]", "relative_path": f"{stem}_dir/{stem}_1.txt", "literal_value": "10"}
    return {"candidate_id": "cand-0001", "statement_key": "sample_or_electrode_number", "observed_literals": ["10"],
            "evidence": [own, scan, *extra], "evidence_truncated": truncated}


@pytest.mark.parametrize("truncated, extra, found", [
    (False, (), True),
    (True, (), True),  # cut witnesses: one literal at one token index, so the rest read it there too
    (True, ({"locator": "filename token 6 [chars 30..32]", "relative_path": "x_dir/x_10.txt", "literal_value": "10"},), False),
])
def test_a_counter_reading_is_recognised_also_when_its_witnesses_were_cut(truncated, extra, found):
    stem = "ZZNPs_on_Au_3_10_m1000mV"
    issue = G._counter_read_as_sample_number(_number_candidate(stem, truncated=truncated, extra=extra), {"stem": stem},
                                             [5], {"decision_id": "d-00001"})
    assert (issue is not None) is found
    if found:
        assert issue["position"] == 5 and issue["effective_reading"] is None
    assert G._counter_read_as_sample_number(_number_candidate(stem, truncated=False), {"stem": stem}, [4],
                                            {"decision_id": "d-00001"}) is None  # another position: not this number
    last = "ZZNPs_on_Au_3_10"  # the number is the LAST token here
    assert G._counter_read_as_sample_number(_number_candidate(last, truncated=False), {"stem": last}, [5],
                                            {"decision_id": "d-00001"}) is not None
    assert G._counter_read_as_sample_number(_number_candidate(last, truncated=False), {"stem": last},
                                            [G.LAST_POSITION], {"decision_id": "d-00001"}) is None  # `last`: not applied


# --- 4. the nearest group ------------------------------------------------------------------------------------------


def test_the_nearest_group_prefers_a_sample_group_when_a_reference_group_needs_as_many_answers(tmp_path, capsys):
    src = tmp_path / "src" / "SYN_BL43_2099-02_ZZ"
    xdc(src / "00_SYN_std_ZZ_001_A.001")       # a standard: a measurement, role reference, first in order
    xdc(src / "01_SYNZZ_1x1mm_002_A.001")      # a sample
    data = _import_and_group(src, tmp_path / "out", capsys)
    roles = [g["role"] for g in data["record_groups"]]
    assert roles == ["reference", "sample"]
    minimum = Q.minimum_answers_for_one_group(Q.consolidate(data), data)
    assert next(g for g in data["record_groups"] if g["group_id"] == minimum["group_id"])["role"] == "sample"
