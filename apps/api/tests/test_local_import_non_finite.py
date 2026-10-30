"""A non-finite number (NaN, Infinity, -Infinity) is never an answer.

Python's ``json`` reads ``NaN`` / ``Infinity`` / ``-Infinity`` (and ``1e999``) as floats that the
schema's ``number`` type check would accept, and writes them back as bare tokens that are NOT
standard JSON. So ``decide --json`` refuses to store one, no write may add one, and eligibility never
accepts one for any field. A bundle an older build already wrote one into is never bricked: ``bundle
check`` names it (that build's check called it VALID, silently), and a corrective answer or any other
write succeeds. Processing turns a non-finite number into null and names it on the result.

SYNTHETIC files only (the grouping CLI fixture).
"""

from __future__ import annotations

import json
import math

import openpyxl
import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

from test_local_import_control_mode import _col, _export, _import, _miss, _row_of
from test_local_import_grouping_cli import _folder

BY = "SYNTHETIC TEST"
NUMERIC = ("context.electrochemistry.current_setpoint_mA_cm2", "context.electrochemistry.potential_setpoint_V",
           "context.electrochemistry.pH", "context.electrochemistry.electrolyte.concentration_M")
TOKENS = ("NaN", "Infinity", "-Infinity", "1e999")


@pytest.fixture()
def grouped(tmp_path):
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert cli.main(["import", str(src), "--out", str(b)]) == 0
    M.group(b)
    return b


@pytest.mark.parametrize("path", NUMERIC)
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_a_non_finite_number_is_never_eligible(path, value):
    problem = B.value_problem(path, value)
    assert problem is not None and "not a finite number" in problem
    fit = B.eligibility_for_official_record(B.STATE_SCIENTIST_CONFIRMED, target_field_path=path, value=value,
                                            writable_paths=frozenset({path}))
    assert fit["eligible"] is False and "not a finite number" in fit["reason"]
    assert B.value_problem(path, -5.0) is None  # a finite number still is


@pytest.mark.parametrize("token", TOKENS)
def test_decide_refuses_to_store_a_non_finite_number(grouped, token, capsys):
    vid = _miss(M.load(grouped), NUMERIC[0], "run-001")["value_id"]
    before = (grouped / "bundle.json").read_bytes()
    capsys.readouterr()
    code = cli.main(["bundle", "decide", str(grouped), "--target", vid, "--decision", "correct",
                     f"--value={token}", "--json", "--by", BY])
    err = capsys.readouterr().err
    assert code != 0 and "not a finite number" in err and "nothing was recorded" in err
    assert (grouped / "bundle.json").read_bytes() == before  # nothing written
    with pytest.raises(M.MutationRefused, match="not a finite number"):
        M.parse_value(token, True)
    assert M.parse_value(token, False) == token  # as TEXT it is stored, and the type check keeps it out


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_a_non_finite_value_given_through_the_python_api_is_refused_at_save(grouped, value):
    vid = _miss(M.load(grouped), NUMERIC[0], "run-001")["value_id"]
    before = (grouped / "bundle.json").read_bytes()
    with pytest.raises(M.MutationRefused, match="would add a non-finite number.*scientist_decisions/0/value"):
        M.decide(grouped, target_ids=[vid], decision="correct", value=value, by=BY, orcid=None)
    assert (grouped / "bundle.json").read_bytes() == before


def _as_the_previous_build_stored_it(b, path, run_id, token):
    """A bundle as the 1.6.0 build wrote it after `decide --json --value=NaN`: the decision's value is
    the bare JSON token, and the stored eligibility says eligible (that build's type check let it through)."""
    vid = _miss(M.load(b), path, run_id)["value_id"]
    M.decide(b, target_ids=[vid], decision="correct", value=0.25, by=BY, orcid=None)
    data = json.loads((b / "bundle.json").read_text())
    data["missing_values"] = [m for m in data["missing_values"] if m["target_field_path"] != CURRENT]  # 1.6.0 had none
    data["format_version"] = "1.6.0"
    B.refresh_questions(data)
    B.apply_derivations(data)
    text = json.dumps(data)
    [d] = [d for d in data["scientist_decisions"] if d["target"]["id"] == vid]
    # write the token directly, as Python's json did for the older build
    text = text.replace(json.dumps(d)[:-1], json.dumps({**d, "value": "SYNTHETIC_TOKEN"})[:-1].replace('"SYNTHETIC_TOKEN"', token), 1)
    (b / "bundle.json").write_text(text)
    assert token in (b / "bundle.json").read_text()
    return vid


CURRENT = "context.electrochemistry.current_setpoint_mA_cm2"


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_a_bundle_already_holding_a_non_finite_answer_is_named_never_bricked_and_can_be_corrected(grouped, token, capsys):
    path = "context.temperature_K"
    vid = _as_the_previous_build_stored_it(grouped, path, "run-001", token)
    # check: STALE (the stored "eligible" is refused now), with the value NAMED — never a silent VALID, no crash
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(grouped)]) == cli.EXIT_INVALID
    out = capsys.readouterr().out
    assert out.startswith("STALE:") and vid in out and "non-finite" in out
    assert "NON-FINITE: bundle.json holds 1" in out and "still the latest answer" in out
    # an UNRELATED write succeeds: the stored token never blocks a write
    other = _miss(M.load(grouped), "context.environment", "run-001")["value_id"]
    M.decide(grouped, target_ids=[other], decision="correct", value="in_situ", by=BY, orcid=None)
    assert _miss(M.load(grouped), path, "run-001")["eligibility_for_official_record"]["eligible"] is False
    # a CORRECTIVE answer on the same target succeeds and makes it eligible again
    assert cli.main(["bundle", "decide", str(grouped), "--target", vid, "--decision", "correct",
                     "--value=298.15", "--json", "--by", BY]) == 0
    m = _miss(M.load(grouped), path, "run-001")
    assert m["value_state"] == B.STATE_SCIENTIST_CONFIRMED and m["eligibility_for_official_record"]["eligible"] is True
    # the status is honest: valid, the old token still NAMED, as replaced
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(grouped)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("VALID:") and "NON-FINITE: bundle.json holds 1" in out and "replaced by the later decision" in out
    # ...and a write still cannot ADD one
    with pytest.raises(M.MutationRefused, match="non-finite"):
        M.decide(grouped, target_ids=[other], decision="correct", value=math.nan, by=BY, orcid=None)


def test_new_non_finite_paths_compares_against_the_stored_file():
    stored = {"scientist_decisions": [{"value": math.nan}], "questions": [{"hints": [math.inf]}]}
    same = {"scientist_decisions": [{"value": math.nan}, {"value": 1.0}], "questions": [{}, {"hints": [math.inf]}]}
    assert B.new_non_finite_paths(same, stored) == []  # old ones, a derived copy moved: nothing new
    more = {"scientist_decisions": [{"value": math.nan}, {"value": math.nan}], "questions": [], "candidates": [{"value": math.nan}]}
    assert B.new_non_finite_paths(more, stored) == ["scientist_decisions/1/value", "candidates/0/value"]
    assert B.new_non_finite_paths(stored, None) == ["scientist_decisions/0/value", "questions/0/hints/0"]


def test_the_template_refuses_non_finite_cells(grouped, tmp_path, capsys):
    xlsx = _export(grouped, tmp_path)
    wb = openpyxl.load_workbook(xlsx)
    column = _col("Current Set-point (mA/cm2)")
    r1, r2 = _row_of(xlsx, "run-001"), _row_of(xlsx, "run-002")
    cells = {f"{column}{r1}": "NaN", f"{column}{r2}": "1e999",
             f"{_col('pH')}{r1}": "Infinity", f"{_col('pH')}{r2}": "-Infinity"}
    for ref, text in cells.items():
        wb["File List"][ref] = text
    wb.save(tmp_path / "f.xlsx")
    code, rep = _import(grouped, tmp_path / "f.xlsx", capsys, "--apply")
    assert code == 0 and rep["recorded"] == 0
    assert sorted(c["cell"] for c in rep["invalid_cells"]) == sorted(f"'File List'!{ref}" for ref in cells)
    bd = M.load(grouped)
    assert bd["scientist_decisions"] == []  # nothing recorded for any of them
    assert all(_miss(bd, NUMERIC[0], r)["value_state"] == B.STATE_MISSING for r in ("run-001", "run-002"))
    assert not list(B.non_finite_numbers(bd))


# --- processing: a non-finite number becomes null and is NAMED (never bricks `bundle process`) ------------


def _prj_with(tmp_path, replacements):
    """A synthetic Athena project whose background parameters carry the TEXT ``nan`` (as a real
    project can), written the way Athena stores them (gzipped `@args`)."""
    import gzip
    import re

    import test_local_import_processing as TP

    bdir, root = TP._athena_case(tmp_path, {"Athena/SYN.prj": [("01_SYN_ZZ1_1-2", TP.GRID, TP.mu_edge(TP.GRID) * 1e-2)]})
    prj = root / "Athena" / "SYN.prj"
    text = gzip.decompress(prj.read_bytes()).decode()
    for key, literal in replacements.items():
        text, n = re.subn(rf"('bkg_{key}',\s*)'[^']*'", rf"\1'{literal}'", text)
        assert n == 1, key
    prj.write_bytes(gzip.compress(text.encode()))
    return bdir, root


def test_a_nan_athena_parameter_becomes_null_and_is_named_on_the_result(tmp_path):
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root = _prj_with(tmp_path, {"step": "nan", "flatten": "nan"})
    out = run_process(bdir, source_root=root)
    assert list(B.non_finite_numbers(out)) == []  # nothing non-finite reaches a result
    [sci] = [r for r in out["processing_results"] if r["source"] == "scientist_athena"]
    assert "athena_value_not_finite" in sci["review_flags"]
    assert {"params.step", "params.flatten"} <= set(sci["non_finite_values"]["paths"])
    normalize = next(s for s in sci["steps"] if s["step"] == "normalize")
    assert normalize["params"]["step"] is None and normalize["params"]["flatten"] is None


def test_a_nan_energy_shift_keeps_the_group_with_no_energy_axis_and_says_so(tmp_path):
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root = _prj_with(tmp_path, {"eshift": "nan"})
    out = run_process(bdir, source_root=root)
    assert list(B.non_finite_numbers(out)) == []
    isa, sci = out["processing_results"]  # KEPT: the scientist's result is not dropped
    assert sci["source"] == "scientist_athena" and "athena_energy_frame_unknown" in sci["review_flags"]
    assert "params.eshift" in sci["non_finite_values"]["paths"]
    assert sci["outputs"]["e0_eV"] is None and sci["preferred_for_record"] is False  # never preferred by default
    assert sci["comparison"]["verdict"] == "not_comparable" and "athena_energy_frame_unknown" in sci["comparison"]["flags"]
    assert "athena_energy_frame_unknown" in isa["review_flags"]
    assert not [f for f in isa["outputs"]["files"] if f["role"] == "athena_normalized"]  # no curve in an unknown frame
    assert any(n["code"] == "athena_group_eshift_not_finite" for n in out["athena"]["notes"])


def _two_versions(tmp_path, nan_second):
    """The reviewer's case: one record group, two Athena projects (2021, 2023) of it."""
    import gzip
    import re

    import test_local_import_processing as TP

    a = TP.mu_edge(TP.GRID) * 1e-2
    b = TP.mu_edge(TP.GRID, TP.E0 + 0.3) * 1e-2
    bdir, root = TP._athena_case(tmp_path, {"Athena/SYN_2021.prj": [("01_SYN_ZZ1", TP.GRID, a)],
                                            "Athena/SYN_2023.prj": [("01_SYN_ZZ1", TP.GRID, b)]})
    if nan_second:
        prj = root / "Athena" / "SYN_2023.prj"
        text, n = re.subn(r"('bkg_eshift',\s*)'[^']*'", r"\1'nan'", gzip.decompress(prj.read_bytes()).decode())
        assert n == 1
        prj.write_bytes(gzip.compress(text.encode()))
    return bdir, root


def test_a_nan_energy_shift_on_one_of_two_versions_never_makes_the_scientists_choice(tmp_path):
    from isaac_api.local_import.processing.cli_entry import run_process

    def listing(out):
        [r] = out["processing_results"]  # several versions: only the ISAAC result, which lists them
        return r, [(v["version_id"], v["provenance"]["prj_file_name"]) for v in r["athena_versions"]]

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    bdir, root = _two_versions(tmp_path / "a", False)
    clean_r, clean = listing(run_process(bdir, source_root=root))
    bdir, root = _two_versions(tmp_path / "b", True)
    out = run_process(bdir, source_root=root)
    assert list(B.non_finite_numbers(out)) == []
    r, nan = listing(out)
    assert nan == clean and len(nan) == 2  # both versions still listed, same ids
    assert r["athena_result_of_record"] is None and "athena_result_of_record_not_selected" in r["review_flags"]
    [q] = r["questions"]
    assert q["code"] == "which_athena_version_is_result_of_record" and q["version_ids"] == [v for v, _ in nan]
    v2023 = next(v for v in r["athena_versions"] if v["provenance"]["prj_file_name"] == "SYN_2023.prj")
    assert v2023["flags"] == ["athena_energy_frame_unknown"] and "params.eshift" in v2023["non_finite_values"]
    assert v2023["comparison"]["verdict"] == "not_comparable"
    assert v2023["provenance"]["data_sha256_prefix"] == next(  # identity intact: select_athena_version still binds to it
        v for v in clean_r["athena_versions"] if v["provenance"]["prj_file_name"] == "SYN_2023.prj")["provenance"]["data_sha256_prefix"]
    assert "athena_energy_frame_unknown" in r["review_flags"]  # stated on the stored result, not only in the run notes


def test_a_non_finite_e0_or_edge_step_is_named_on_the_athena_entry(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy", reason="needs the optional `processing` extra")

    from isaac_api.local_import.processing import athena as A

    bdir, root = _prj_with(tmp_path, {})
    prj = root / "Athena" / "SYN.prj"
    import larch.io

    real_read = larch.io.AthenaProject.read

    def read_then_nan(self, *args, **kwargs):
        out = real_read(self, *args, **kwargs)
        for g in self.groups.values():
            g.e0, g.edge_step = math.nan, math.inf  # what larch gives for a curve it cannot place
        return out

    monkeypatch.setattr(larch.io.AthenaProject, "read", read_then_nan)
    [entry], _ = A.load_project(prj, "Athena/SYN.prj", None, np)
    assert entry["e0_eV"] is None and entry["edge_step"] is None
    assert {"e0_eV", "edge_step"} <= set(entry["non_finite_values"])


def test_a_nan_in_the_scientists_curve_gives_a_null_noise_named_on_the_result(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy", reason="needs the optional `processing` extra")

    from isaac_api.local_import.processing import athena as A
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root = _prj_with(tmp_path, {})
    real = A.load_project

    def with_nan_norm(*args, **kwargs):
        entries, notes = real(*args, **kwargs)
        for e in entries:
            e["norm"] = np.full_like(e["norm"], np.nan)
        return entries, notes

    monkeypatch.setattr(A, "load_project", with_nan_norm)
    out = run_process(bdir, source_root=root)
    assert list(B.non_finite_numbers(out)) == []
    [sci] = [r for r in out["processing_results"] if r["source"] == "scientist_athena"]
    assert sci["qc"]["metrics"]["pre_edge_noise"] is None
    assert "qc.metrics.pre_edge_noise" in sci["non_finite_values"]["paths"]


def test_the_last_guard_nulls_and_names_any_non_finite_number_in_a_result():
    from isaac_api.local_import.processing import run as RUN

    r = {"review_flags": ["x"], "qc": {"metrics": {"a": math.nan, "b": 1.0}}, "steps": [{"outcome": {"v": [math.inf, 2.0]}}]}
    RUN._null_non_finite(r)
    assert r["qc"]["metrics"] == {"a": None, "b": 1.0} and r["steps"][0]["outcome"]["v"] == [None, 2.0]
    assert r["non_finite_values"]["paths"] == ["qc.metrics.a", "steps.0.outcome.v.0"] and "value_not_finite" in r["review_flags"]


def test_run_process_applies_the_last_guard_to_every_result(tmp_path, monkeypatch):
    from isaac_api.local_import.processing import run as RUN
    from isaac_api.local_import.processing.cli_entry import run_process

    bdir, root = _prj_with(tmp_path, {})
    real = RUN.process_group

    def with_a_nan(*args, **kwargs):
        out = real(*args, **kwargs)
        out[0]["qc"]["metrics"]["SYNTHETIC_metric"] = math.nan  # a computation a later change gets wrong
        return out

    monkeypatch.setattr(RUN, "process_group", with_a_nan)
    out = run_process(bdir, source_root=root)
    assert list(B.non_finite_numbers(out)) == []
    first = out["processing_results"][0]
    assert first["qc"]["metrics"]["SYNTHETIC_metric"] is None and "qc.metrics.SYNTHETIC_metric" in first["non_finite_values"]["paths"]
