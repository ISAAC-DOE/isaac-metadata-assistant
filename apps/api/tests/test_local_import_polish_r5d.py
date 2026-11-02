"""r5d: a SPEC run with no ``<stem>_dir`` folder lists the energy scans inside its SPEC file (H1), and the SPEC
headers' own fingerprint (account and column names) is a beamline hint beside the folder's name (H2).

Every file here is SYNTHETIC: invented names (SYN_*), invented values, built in ``tmp_path``. No real data.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import suggestions as S
from isaac_api.local_import import template as T
from isaac_api.local_import.processing.readers import parse_text, read_scan_file

GRID = [1000.0 + 2.5 * k for k in range(40)]


def _rows(columns: int, scale: float = 1.0) -> list[str]:
    out = []
    for k, e in enumerate(GRID):
        signal = (100 if k < 20 else 1000) * scale
        out.append(" ".join([f"{e:.1f}", "10000"] + [f"{signal:.1f}"] * (columns - 2)))
    return out


def spec_text(stem: str, blocks, *, account="SYNLAB\\b_user62", columns=("synmono", "I0", "FF1", "FF2", "DTC_FF1")) -> str:
    """A synthetic SPEC acquisition: ``blocks`` = [(#S number, command, rows?, scale)]."""
    lines = [f"#F {stem}", "#E 4102445400", "#D Fri Jan 01 00:00:00 2100", f"#C spec  User = {account}",
             "#C SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value is invented.", "#O0     synmono   synemiss", ""]
    for number, command, with_rows, scale in blocks:
        lines += [f"#S {number}  {command}", "#D Fri Jan 01 00:00:00 2100", "#T 0.5  (Seconds)", "#P0 1000.0 900.0",
                  f"#N {len(columns)}", "#L " + "  ".join(columns)]
        if with_rows:
            lines += _rows(len(columns), scale)
        lines.append("")
    return "\n".join(lines) + "\n"


GSCAN = "gscan synmono 1000 1100 2.5 0.5"


def _folder(tmp_path: Path, label="SSRL_BL152_2100-01_SYN", account="SYNLAB\\b_user62",
            columns=("synmono", "I0", "FF1", "FF2", "DTC_FF1")) -> Path:
    root = tmp_path / label
    root.mkdir()
    # no `_dir` folder: three energy scans, one alignment scan, one aborted energy scan
    (root / "SYN_ZZ1_acid_01").write_text(spec_text("SYN_ZZ1_acid_01", [
        (1, GSCAN, True, 1.0), (2, "ascan synSy -1 1 10 0.5", True, 1.0), (3, GSCAN, True, 2.0),
        (4, GSCAN, False, 1.0), (5, GSCAN, True, 3.0)], account=account, columns=columns))
    # a `_dir` folder of one-scan exports: read from it, as before
    stem = "SYN_ZZ2_base_01"
    (root / stem).write_text(spec_text(stem, [(1, GSCAN, True, 1.0), (2, GSCAN, True, 1.0)], account=account, columns=columns))
    (root / f"{stem}_dir").mkdir()
    for k in (1, 2):
        (root / f"{stem}_dir" / f"{stem}_{k:03d}.dat").write_text(
            "\n".join([f"#S {k}  {GSCAN}", "#L " + "  ".join(columns)] + _rows(len(columns))) + "\n")
    # no `_dir` folder and no energy scan with data: truly no scan anywhere
    (root / "SYN_ZZ3_none_01").write_text(spec_text("SYN_ZZ3_none_01", [
        (1, "ascan synSy -1 1 10 0.5", True, 1.0), (2, GSCAN, False, 1.0)], account=account, columns=columns))
    return root


def _import(tmp_path: Path, root: Path, name="out") -> dict:
    out = tmp_path / name
    assert cli.main(["import", str(root), "--out", str(out)]) == cli.EXIT_OK
    return json.loads((out / "bundle.json").read_text(encoding="utf-8"))


def _run(bundle, stem):
    return next(r for r in bundle["runs"] if r["stem"] == stem)


# --- H1: the scans inside a SPEC file ---------------------------------------------------------------


def test_spec_file_scans_takes_energy_scans_with_rows_and_names_the_rest():
    text = spec_text("SYN_X", [(1, GSCAN, True, 1.0), (2, "a2scan synSx 0 1 synSz 0 1 10 0.5", True, 1.0),
                               (3, GSCAN, False, 1.0), (7, GSCAN, True, 1.0)])
    numbers, left_out = B.spec_file_scans(text)
    assert numbers == [1, 7]
    assert [(x["scan"], x["why"]) for x in left_out] == [("2", "not an energy scan (a2scan)"), ("3", "no data rows")]


def test_a_repeated_scan_number_names_no_single_scan():
    text = spec_text("SYN_X", [(1, GSCAN, True, 1.0), (2, GSCAN, True, 1.0), (1, GSCAN, True, 1.0)])
    numbers, left_out = B.spec_file_scans(text)
    assert numbers == [2]
    assert [x["scan"] for x in left_out] == ["1", "1"] and all("more than once" in x["why"] for x in left_out)


def test_a_run_without_a_dir_folder_lists_the_scans_inside_its_spec_file(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path))
    run = _run(bundle, "SYN_ZZ1_acid_01")
    acq = run["acquisition_source_id"]
    assert run["scans"] == [{"source_id": acq, "relative_path": "SYN_ZZ1_acid_01", "scan_index": n} for n in (1, 3, 5)]
    assert run["scan_count"] == 3
    said = run["other_relationships"]["scans_in_spec_file"]
    assert said["rule_id"] == B.SPEC_FILE_SCANS_RULE_ID and said["scans"] == [1, 3, 5]
    assert "#S 1, 3, 5" in said["statement"] and "#S 2 (not an energy scan (ascan))" in said["statement"]
    assert "#S 4 (no data rows)" in said["statement"]
    # a run WITH a `_dir` folder keeps its one-scan exports, unchanged
    other = _run(bundle, "SYN_ZZ2_base_01")
    assert [s["relative_path"] for s in other["scans"]] == [f"SYN_ZZ2_base_01_dir/SYN_ZZ2_base_01_{k:03d}.dat" for k in (1, 2)]
    assert "scans_in_spec_file" not in other["other_relationships"]
    assert B.validate_bundle(bundle) == []


def test_a_run_with_no_scan_anywhere_still_lists_none_and_says_why(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path))
    run = _run(bundle, "SYN_ZZ3_none_01")
    assert run["scans"] == [] and run["scan_count"] == 0
    said = run["other_relationships"]["scans_in_spec_file"]
    assert said["scans"] == [] and "holds no energy scan with data rows" in said["statement"]


def test_a_zip_of_the_folder_lists_the_same_spec_file_scans(tmp_path):
    root = _folder(tmp_path)
    zpath = tmp_path / "SYN_beamtime.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(root).as_posix())
    folder, zipped = _import(tmp_path, root, "a"), _import(tmp_path, zpath, "b")
    assert _run(zipped, "SYN_ZZ1_acid_01")["scans"] == _run(folder, "SYN_ZZ1_acid_01")["scans"]


def test_a_changed_file_is_not_read_for_its_scans(tmp_path, monkeypatch):
    root = _folder(tmp_path)
    real = B._read_source_bytes
    monkeypatch.setattr(B, "_read_source_bytes", lambda r, rel, **k: (real(r, rel, **k) or b"") + b"\n# changed\n")
    run = _run(_import(tmp_path, root), "SYN_ZZ1_acid_01")
    assert run["scans"] == [] and "scans_in_spec_file" not in run["other_relationships"]


def test_the_reader_reads_one_block_of_a_file_of_several(tmp_path):
    path = tmp_path / "SYN_multi"
    path.write_text(spec_text("SYN_multi", [(1, GSCAN, True, 1.0), (2, GSCAN, True, 2.0), (3, GSCAN, True, 3.0)]))
    one, three = read_scan_file(path, scan=1), read_scan_file(path, scan=3)
    assert one.error is None and three.error is None and one.n_rows == three.n_rows == len(GRID)
    assert three.columns["FF1"][-1] == 3 * one.columns["FF1"][-1]
    assert "scan_block_read:3" in three.notes and "multiple_scan_blocks_first_read" not in three.notes
    assert read_scan_file(path, scan=9).error == "scan_not_in_file:9"
    assert read_scan_file(path).notes == ["multiple_scan_blocks_first_read"]  # no scan asked: unchanged
    twice = tmp_path / "SYN_twice"
    twice.write_text(spec_text("SYN_twice", [(1, GSCAN, True, 1.0), (1, GSCAN, True, 2.0)]))
    assert read_scan_file(twice, scan=1).error == "scan_number_repeated:1"
    # a file of one block is read whole whatever scan is asked (a one-scan export names its scan by file name)
    single = parse_text("\n".join([f"#S 1  {GSCAN}", "#L synmono I0 FF1"] + ["1000.0 1 2", "1002.5 1 2"]), scan=4)
    assert single.error is None and single.n_rows == 2


def test_processing_reads_each_spec_file_scan_at_its_own_block(tmp_path, capsys):
    pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
    pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")
    from isaac_api.local_import import mutations as M

    root = _folder(tmp_path)
    _import(tmp_path, root)
    out = tmp_path / "out"
    M.group(out)
    M.process(out, source=str(root))
    capsys.readouterr()
    b = M.load(out)
    key = _run(b, "SYN_ZZ1_acid_01")["run_key"]
    gid = next(g["group_id"] for g in b["record_groups"] if key in g["member_run_keys"])
    [res] = [r for r in b["processing_results"] if r["group_id"] == gid and r["source"] == "isaac_protocol"]
    assert [i["scan"] for i in res["inputs"]] == [1, 3, 5]
    assert all(f"scan_block_read:{i['scan']}" in i["reader_notes"] for i in res["inputs"])
    assert (res.get("applicability") or {}).get("status") != B.NOT_APPLICABLE


# --- H2: the SPEC headers' fingerprint, beside the folder's name ---------------------------------------


def test_the_fingerprint_names_another_beamline_than_the_folder_and_says_so(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path))
    fp = bundle["experiment"]["acquisition_system"]["fingerprint"]
    assert fp["rule_id"] == B.ACQUISITION_FINGERPRINT_RULE_ID
    assert fp["spec_accounts"] == [{"literal": "SYNLAB\\b_user62", "files": 3}]
    [m] = fp["matches"]
    assert (m["beamline"], m["branch_stated"], m["accounts_seen"]) == ("BL6-2", False, ["SYNLAB\\b_user62"])
    assert set(m["channels_seen"]) == {"FF1", "FF2", "DTC_FF1"}
    assert fp["contradicts_build_default"] is True
    assert fp["disagrees_with_folder_name"]["beamline"] == "BL152"
    assert "the two hints disagree" in fp["statement"] and "never answers" in fp["statement"]
    # the build's default system is unchanged: it is still applied, and said
    assert bundle["experiment"]["acquisition_system"]["system_id"] == "ssrl_bl152_spec_vortex_channels"


def test_the_beamline_hints_quote_both_sources_and_put_the_headers_first(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path))
    hints = S.facility_hints(bundle)
    assert [h["kind"] for h in hints] == ["acquisition_fingerprint", "folder_name"]
    assert hints[0]["literal"] == "SSRL BL6-2" and "'SYNLAB\\b_user62' in 3 file(s)" in hints[0]["locator"]
    assert all("never an answer" in h["note"] and "disagree" in h["note"] for h in hints)


def test_adopt_says_the_hints_disagree_instead_of_presenting_the_folder_as_the_hint(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path))
    lines = T.facility_hint_lines(bundle, T.BEAMLINE_PATH, "62b")
    assert lines[0].startswith("the files' hints disagree with each other about the beamline")
    assert any(line.startswith("differs from a hint: the imported folder's name 'SSRL_BL152_2100-01_SYN'")
               for line in lines)
    assert any(line.startswith("agrees with a hint: the SPEC headers' fingerprint (the SPEC account") for line in lines)
    # the folder's beamline typed back is still a disagreement: the SPEC headers name another one
    lines = T.facility_hint_lines(bundle, T.BEAMLINE_PATH, "BL15-2")
    assert any(line.startswith("differs from a hint: the SPEC headers' fingerprint") for line in lines)
    assert any(line.startswith("agrees with a hint: the imported folder's name") for line in lines)
    # a facility acronym both hints name: no disagreement
    assert T.facility_hint_lines(bundle, T.FACILITY_NAME_PATH, "SSRL") == []


def test_a_hint_with_no_branch_agrees_with_any_branch_of_its_beamline():
    r = {"value": "BL6-2", "branch_stated": False}
    assert T._hint_agrees(r, "62b") and T._hint_agrees(r, "BL6-2c") and T._hint_agrees(r, "BL 6-2")
    assert not T._hint_agrees(r, "BL15-2") and not T._hint_agrees({"value": "BL6-2c"}, "62b")
    assert T.without_branch("62b") == "62" and T.without_branch("BL6-2c") == "6-2" and T.without_branch("BL15-2") == "BL15-2"


def test_the_beamline_question_says_the_hints_disagree(tmp_path):
    from isaac_api.local_import import questions as Q

    bundle = _import(tmp_path, _folder(tmp_path))
    said = S.beamline_hints_sentence(bundle)
    assert said.startswith(" The files' beamline hints disagree") and "ask the scientist which beamline" in said
    asking = [q for q in Q.consolidate(bundle)["questions"]
              if "system.facility.beamline" in (q.get("fields") or {}) or q.get("target_field_path") == "system.facility.beamline"]
    assert asking and all(said in q["text"] for q in asking)


def test_a_folder_name_alone_keeps_its_one_line(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path, account="synlocal", columns=("synmono", "I0", "synfluo")))
    fp = bundle["experiment"]["acquisition_system"]["fingerprint"]
    assert fp["matches"] == [] and fp["spec_accounts"] == [{"literal": "synlocal", "files": 3}]
    assert "no beamline hint" in fp["statement"]
    assert [h["kind"] for h in S.facility_hints(bundle)] == ["folder_name"]
    assert S.beamline_hints_sentence(bundle) == ""
    assert T.facility_hint_lines(bundle, T.BEAMLINE_PATH, "62b") == [
        "differs from a hint: the imported folder's name 'SSRL_BL152_2100-01_SYN' names beamline 'BL152' "
        "(compared as '152', yours '62b'); a hint, never an answer"]


def test_a_matching_fingerprint_agrees_with_the_folder_and_the_default(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path, account="specadm", columns=("synmono", "I0", "vortDT", "vortDT2")))
    fp = bundle["experiment"]["acquisition_system"]["fingerprint"]
    assert [m["beamline"] for m in fp["matches"]] == ["BL15-2"]
    assert fp["contradicts_build_default"] is False and "disagrees_with_folder_name" not in fp
    assert S.beamline_hints_sentence(bundle) == ""
    assert T.facility_hint_lines(bundle, T.BEAMLINE_PATH, "BL15-2") == []


def test_a_spec_file_holding_several_scans_is_no_scan_files_own_index():
    from isaac_api.local_import import grouping as G

    run = {"scans": [{"source_id": "src-1", "relative_path": "SYN_A", "scan_index": n} for n in (1, 3, 5)]
           + [{"source_id": "src-2", "relative_path": "SYN_B_dir/SYN_B_004.dat", "scan_index": None}]}
    assert G._scan_file_indexes(run) == {"src-2": 4}


def test_a_folder_naming_no_beamline_still_hears_that_the_default_does_not_fit(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path, label="SYN_beamtime_2100"))
    fp = bundle["experiment"]["acquisition_system"]["fingerprint"]
    assert fp["contradicts_build_default"] is True and "disagrees_with_folder_name" not in fp
    said = S.beamline_hints_sentence(bundle)
    assert "reads every import as BL15-2 data by default" in said and "ask the scientist which beamline" in said


def test_a_fingerprint_of_the_shown_acquisition_system_is_not_said_twice(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path, account="specadm", columns=("synmono", "I0", "vortDT", "vortDT2")))
    assert [h["kind"] for h in S.facility_hints(bundle)] == ["acquisition_system", "folder_name"]
