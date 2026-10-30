"""Polish c4-r: review findings on c4-a/c4-b. Synthetic only.

* (1) A record whose approved result is a SET of the scientist's per-scan Athena groups (``per_scan_set``:
  ISAAC averaged them) never says the values were "read unchanged by ISAAC": its E0 descriptor is the mean of
  N of the scientist's per-scan Athena normalisations, computed by ISAAC's protocol (``source: auto``), and its
  label names the set. One matched Athena group still reads as the scientist's own, imported.
* (2) Nothing exported names the Athena project's folder: the record says the project's FILE NAME only; the
  path within the beamtime is in the evidence sidecar, as the sidecar names every other source file.
* (3) ``extract --out`` inside ``--root``, inside the file's own folder, or inside a bundle is refused.
* (c) A beamtime-wide question whose template cells hold DIFFERENT values gives no command per value.
* (d) The refusal to approve a second result says when the approved one's approval no longer matches its
  files, and approving it again then binds it to its current files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import extract as ex
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R

from test_local_import_extract import make_docx
from test_local_import_polish_c4a import ATHENA_PRJ, _add_athena, _approve, _exported
from test_local_import_records import (  # noqa: F401  (fixtures)
    BY, _decide_everything, _portal, bdir, fake_upstream, pristine)
from test_local_import_template_adopt import corpus, grouped, grouped_base  # noqa: F401  (fixtures)

FOLDER = "Syn_Person_ZZ1_norm"  # a folder name that could carry a sample's or a person's name


def _athena_inputs(bdir, **change):
    b = M.load(bdir)
    p2 = next(r for r in b["processing_results"] if r["result_id"] == "p2")
    p2["inputs"] = [dict(p2["inputs"][0], **change)]
    M.save_bundle(bdir, b)


def _approve_athena(bdir):
    M.decide(bdir, target_ids=["p1"], decision="defer", value=None, **BY)
    _approve(bdir, "p2")


def _record_and_sidecar(bdir, tmp_path):
    R.build_records(bdir)
    out = tmp_path / "records"
    # the export is schema-gated (draft checks + the portal-target schema); the portal itself is the stand-in
    result = R.export_records(bdir, out, run_portal=_portal("publish"))
    assert len(result["exported"]) == 1, result
    rid = result["exported"][0]["record_id"]
    return json.loads((out / f"{rid}.json").read_text()), json.loads((out / f"{rid}.evidence.json").read_text())


# --- (1) a per-scan set is ISAAC's mean, never "read unchanged" ----------------------------------------------


def test_a_per_scan_set_descriptor_says_isaac_computed_the_mean_of_the_named_groups(bdir, tmp_path):
    _decide_everything(bdir)
    _add_athena(bdir, subset=False)
    _athena_inputs(bdir, scan="SYN_ZZ1_001 [+2 per-scan groups]", athena_group="syn_zz1_001", match_kind="per_scan_set",
                   per_scan_set={"athena_groups": ["syn_zz1_001", "syn_zz1_002", "syn_zz1_003"],
                                 "labels": ["SYN_ZZ1_001", "SYN_ZZ1_002", "SYN_ZZ1_003"], "scans": [1, 2, 3]})
    _approve_athena(bdir)
    record, _ = _record_and_sidecar(bdir, tmp_path)
    [out] = record["descriptors"]["outputs"]
    notes = out["generated_by"]["notes"]
    assert "mean of 3 of the scientist's per-scan Athena normalisations (groups syn_zz1_001, syn_zz1_002, syn_zz1_003" in notes
    assert "computed by ISAAC isaac.xas.synthetic" in notes and "not a merge the scientist made" in notes
    assert "read unchanged" not in notes and ATHENA_PRJ in notes
    assert out["generated_by"]["agent"] == "isaac.xas.synthetic" and out["generated_by"]["version"] == "0.1"
    assert "syn_zz1_001+syn_zz1_002+syn_zz1_003" in out["label"] and "mean" in out["label"]
    [e0] = out["descriptors"]
    assert e0["source"] == "auto" and e0["value"] == 1013.5
    assert "ISAAC did not change it" not in e0["definition"] and "computed by ISAAC" in e0["definition"]


def test_a_per_scan_set_from_an_older_build_with_no_member_list_still_says_isaac_computed_it(bdir, tmp_path):
    _decide_everything(bdir)
    _add_athena(bdir, subset=False)
    _athena_inputs(bdir, scan="SYN_ZZ1_001 [+1 per-scan groups]", athena_group="syn_zz1_001", match_kind="per_scan_set")
    _approve_athena(bdir)
    [out] = _exported(bdir, tmp_path)["descriptors"]["outputs"]
    assert "read unchanged" not in out["generated_by"]["notes"] and "computed by ISAAC" in out["generated_by"]["notes"]
    assert out["descriptors"][0]["source"] == "auto"


def test_one_matched_athena_group_is_still_the_scientists_own_imported_value(bdir, tmp_path):
    _decide_everything(bdir)
    _add_athena(bdir, subset=False)
    _approve_athena(bdir)
    [out] = _exported(bdir, tmp_path)["descriptors"]["outputs"]
    assert out["generated_by"]["agent"] == "Athena" and "read unchanged by ISAAC" in out["generated_by"]["notes"]
    assert out["label"] == f"athena:{ATHENA_PRJ}#syn_zz1_2_3" and out["descriptors"][0]["source"] == "imported"


# --- (2) the record names the project's file name, never its folders -----------------------------------------


@pytest.mark.parametrize("kind", ["exact", "per_scan_set"])
def test_the_record_names_the_athena_project_by_file_name_only(bdir, tmp_path, kind):
    _decide_everything(bdir)
    _add_athena(bdir, subset=False)
    extra = {"per_scan_set": {"athena_groups": ["g_1", "g_2"], "labels": ["a", "b"], "scans": [1, 2]}} if kind == "per_scan_set" else {}
    _athena_inputs(bdir, relative_path=f"{FOLDER}/sub/{ATHENA_PRJ}", match_kind=kind, **extra)
    _approve_athena(bdir)
    record, sidecar = _record_and_sidecar(bdir, tmp_path)
    assert FOLDER not in json.dumps(record)
    [out] = record["descriptors"]["outputs"]
    assert ATHENA_PRJ in out["label"] and ATHENA_PRJ in out["generated_by"]["notes"]
    # the sidecar names the project where it is in the beamtime, as it names every source file
    assert f"{FOLDER}/sub/{ATHENA_PRJ}" in json.dumps(sidecar)


# --- (1) the result of a per-scan set names its member groups ------------------------------------------------


def test_a_per_scan_set_result_names_its_member_groups_and_does_not_say_unchanged(tmp_path):
    pytest.importorskip("larch", reason="needs the optional `processing` extra")
    from isaac_api.local_import.processing.cli_entry import run_process
    from test_local_import_processing import GRID, _athena_case, mu_edge

    groups = [("01_SYN_ZZ1_001", GRID, mu_edge(GRID) * 1e-2), ("01_SYN_ZZ1_002", GRID, mu_edge(GRID) * 1.01e-2)]
    bdir, root = _athena_case(tmp_path, {"SYN.prj": groups})
    sci = next(r for r in run_process(bdir, source_root=root)["processing_results"] if r["source"] == "scientist_athena")
    [ref] = sci["inputs"]
    assert ref["match_kind"] == "per_scan_set"
    members = ref["per_scan_set"]
    assert members["labels"] == ["01_SYN_ZZ1_001", "01_SYN_ZZ1_002"] and members["scans"] == [1, 2]
    assert len(members["athena_groups"]) == 2 and members["athena_groups"][0] == ref["athena_group"]
    assert "isaac_did_not_change_scientist_values" not in sci["review_flags"]
    assert "isaac_computed_mean_of_scientist_per_scan_curves" in sci["review_flags"]


# --- (3) extract --out inside the source folder or a bundle is refused ----------------------------------------


def _doc(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return make_docx(path)


def _extract(capsys, argv):
    capsys.readouterr()
    code = ex.main(argv)
    return code, capsys.readouterr()


@pytest.mark.parametrize("where", ["root", "file_folder", "bundle", "bundle_subfolder"])
def test_extract_refuses_an_out_inside_the_source_or_a_bundle(tmp_path, capsys, where):
    root = tmp_path / "beamtime"
    src = _doc(root / "notes" / "n.docx")
    bundle = tmp_path / "bdl"
    bundle.mkdir()
    (bundle / "bundle.json").write_text("{}")
    out = {"root": root / "extracted", "file_folder": src.parent / "x",
           "bundle": bundle / "extracted", "bundle_subfolder": bundle / "a" / "b"}[where]
    argv = [str(src), "--out", str(out)] + (["--root", str(root)] if where == "root" else [])
    code, said = _extract(capsys, argv)
    assert code == 3 and said.out == ""
    assert "--out" in said.err and "refused" in said.err
    assert not out.exists()


def test_extract_refuses_an_out_inside_root_from_a_bundle_list(tmp_path, capsys):
    root = tmp_path / "beamtime"
    _doc(root / "n.docx")
    unread = tmp_path / "unread_files.json"
    unread.write_text(json.dumps({"unread_files": [{"relative_path": "n.docx", "reason_code": "x"}]}))
    code, said = _extract(capsys, ["--from-bundle", str(unread), "--root", str(root), "--out", str(root / "o")])
    assert code == 3 and "inside --root" in said.err and not (root / "o").exists()


def test_extract_writes_to_a_notes_folder_beside_the_bundle(tmp_path, capsys):
    root = tmp_path / "beamtime"
    src = _doc(root / "n.docx")
    (tmp_path / "bdl").mkdir()
    (tmp_path / "bdl" / "bundle.json").write_text("{}")
    code, said = _extract(capsys, [str(src), "--root", str(root), "--out", str(tmp_path / "bdl-notes" / "extracted")])
    assert code == 0, said.err


def test_the_paging_hint_quotes_the_sheet_name_for_the_shell(tmp_path, capsys):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bob's list"
    for i in range(1, 80):
        ws.append([f"S_{i:02d}", i])
    root = tmp_path / "root"
    root.mkdir()
    wb.save(root / "s.xlsx")
    code, said = _extract(capsys, [str(root / "s.xlsx"), "--root", str(root), "--out", str(tmp_path / "out")])
    assert code == 0, said.err
    [sheet] = json.loads(said.out)["sheets"]
    text = Path(sheet["text_file"]).read_text(encoding="utf-8")
    hint = next(ln for ln in text.splitlines() if "NOT in this file: page them" in ln)
    assert "--sheet 'Bob'\"'\"'s list'" in hint and '"Bob\'s list"' not in hint
    assert sheet["read_rest"]["command"].startswith(sys.executable)


# --- (d) a stale approval is said, and approving again rebinds it ---------------------------------------------


def _make_p1_stale(bdir):
    b = M.load(bdir)
    p1 = next(r for r in b["processing_results"] if r["result_id"] == "p1")
    p1["outputs"]["files"][0]["sha256"] = "0" * 64  # p1 now lists other bytes than its approval saw
    M.save_bundle(bdir, b)


def test_the_refusal_says_when_the_approved_results_approval_no_longer_matches_its_files(bdir):
    _decide_everything(bdir)
    _add_athena(bdir)
    _make_p1_stale(bdir)
    with pytest.raises(M.MutationRefused) as exc:
        _approve(bdir, "p2")
    said = str(exc.value)
    assert "p1's approval no longer matches its files" in said and "no record uses it" in said
    assert "nothing more to do" not in said
    assert "--target p1 --decision approve" in said and "Nothing was recorded" in said


def test_the_refusal_still_says_keep_it_when_the_approval_matches(bdir):
    _decide_everything(bdir)
    _add_athena(bdir)
    with pytest.raises(M.MutationRefused) as exc:
        _approve(bdir, "p2")
    assert "keep p1 (nothing more to do)" in str(exc.value) and "no longer matches" not in str(exc.value)


def test_approving_a_stale_approval_again_binds_it_to_the_current_files(bdir):
    _decide_everything(bdir)
    _make_p1_stale(bdir)
    out = _approve(bdir, "p1")
    assert out["recorded"] == ["p1"]
    d = [d for d in M.load(bdir)["scientist_decisions"] if d["target"] == {"kind": "processing_result", "id": "p1"}][-1]
    assert d["approved_files"][0]["sha256"] == "0" * 64
    # restating it once more, with nothing changed, records nothing
    assert _approve(bdir, "p1")["unchanged"] == ["p1"]


# --- (c) a beamtime-wide question whose cells differ gives no command per value ------------------------------


def test_cells_with_different_values_for_a_beamtime_wide_question_give_no_command_per_value(grouped, tmp_path, capsys):
    from test_local_import_polish_c3t import _export, _fill, _text
    from test_local_import_polish_c4b import TECH, _beamtime_question
    from test_local_import_template_adopt import _col, _import, _row_of

    q = _beamtime_question(M.load(grouped), TECH)
    xlsx = _export(grouped, tmp_path)
    r1, r2 = _row_of(xlsx, "run-001"), _row_of(xlsx, "run-002")
    filled = _fill(xlsx, tmp_path / "f.xlsx", {
        ("Configurations", "A2"): "C1", ("Configurations", "B2"): "XAS",
        ("Configurations", "A3"): "C2", ("Configurations", "B3"): "XES",
        ("File List", f"{_col('Config ID')}{r1}"): "C1", ("File List", f"{_col('Config ID')}{r2}"): "C2"})
    code, rep, err = _import(grouped, filled, capsys)
    assert code == 0, err
    asked = rep["asked_beamtime_wide"]
    assert {a["value"] for a in asked} == {"XAS", "XES"} and {a["question_id"] for a in asked} == {q["question_id"]}
    for a in asked:
        # no command that records one cell's value: running each in turn would leave the last one standing
        assert "--value XAS" not in a["command"] and "--value XES" not in a["command"]
        assert a["values_differ"] == ["'XAS'", "'XES'"]
        assert "the scientist says which applies" in a["reason"]

    code, text = _text(grouped, filled, capsys)
    assert code == 0
    lines = [ln for ln in text.splitlines() if ln.startswith("  Technique") and q["question_id"] in ln]
    assert len(lines) == 1, lines
    assert "2 different values ('XAS', 'XES')" in lines[0] and "the scientist must say which applies" in lines[0]
    assert "--value XAS" not in lines[0] and "--value XES" not in lines[0]


def test_cells_that_agree_on_a_beamtime_wide_question_still_give_its_command(grouped, tmp_path, capsys):
    from test_local_import_polish_c3t import _export, _fill
    from test_local_import_polish_c4b import TECH
    from test_local_import_template_adopt import _col, _import, _row_of

    xlsx = _export(grouped, tmp_path)
    r1, r2 = _row_of(xlsx, "run-001"), _row_of(xlsx, "run-002")
    filled = _fill(xlsx, tmp_path / "f.xlsx", {
        ("Configurations", "A2"): "C1", ("Configurations", "B2"): "XAS",
        ("File List", f"{_col('Config ID')}{r1}"): "C1", ("File List", f"{_col('Config ID')}{r2}"): "C1"})
    code, rep, err = _import(grouped, filled, capsys)
    assert code == 0, err
    assert len(rep["asked_beamtime_wide"]) == 2 and all("--value XAS" in a["command"] for a in rep["asked_beamtime_wide"])
    assert all("values_differ" not in a for a in rep["asked_beamtime_wide"])
    assert TECH == rep["asked_beamtime_wide"][0]["target_field_path"]
