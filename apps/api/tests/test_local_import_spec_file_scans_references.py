"""A standard or reference SPEC file whose `<stem>_dir` folder is empty lists the `#S` energy scans inside the file
(rule ``spec_file_energy_scans_v1``), and the HERFD channel selector reads those same blocks, so the reference is
processed with the channel the selector proposes rather than by column-name priority.

Every file here is SYNTHETIC: invented names (SYN_*), an invented element (Zz), invented values, built in
``tmp_path``. No real data.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from isaac_api import historical_import as HI
from isaac_api import spec_file_scans as SFS
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli

GRID = [5000.0 + 1.0 * k for k in range(120)]
GSCAN = "gscan absev 5000 5119 1 0.5"
ASCAN = "ascan synSy -1 1 10 0.5"
COLUMNS = ("absev", "I0", "I1", "vortDT", "vortDT2")


def _rows(scale: float) -> list[str]:
    out = []
    for k, e in enumerate(GRID):
        mu = 0.2 + (1.5 if k >= 60 else 0.0) + 0.001 * (k % 3)
        i0 = 100000.0
        # vortDT carries the edge; vortDT2 counts nothing; I1 is a flat, positive transmission detector
        out.append(f"{e:.2f} {i0:.1f} {i0 * 0.5:.1f} {mu * i0 * 0.01 * scale:.3f} 0.0")
    return out


def spec_text(stem: str, blocks) -> str:
    """A synthetic SPEC file: ``blocks`` = [(#S number, command, with rows?)]."""
    lines = [f"#F {stem}", "#E 4102445400", "#D Fri Jan 01 00:00:00 2100",
             "#C SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value is invented.", ""]
    for number, command, with_rows in blocks:
        lines += [f"#S {number}  {command}", "#D Fri Jan 01 00:00:00 2100", f"#N {len(COLUMNS)}", "#L " + "  ".join(COLUMNS)]
        if with_rows:
            lines += _rows(1.0 + 0.1 * number)
        lines.append("")
    return "\n".join(lines) + "\n"


REF = "SYN_REF_pellet_01"
ALIGN = "SYN_align_01"
SAMPLE = "SYN_QQ1_acid_01"


def _folder(tmp_path: Path, label="SSRL_BL152_2100-01_SYN") -> Path:
    root = tmp_path / label
    root.mkdir()
    (root / "readme.txt").write_text("# SYNTHETIC FIXTURE\nZz\n")
    # a reference pellet: an EMPTY `_dir`, three energy scans and one alignment scan in the combined file
    (root / REF).write_text(spec_text(REF, [(1, GSCAN, True), (2, ASCAN, True), (3, GSCAN, True), (4, GSCAN, True)]))
    (root / f"{REF}_dir").mkdir()
    # an alignment file: its scans are never listed as a run's scans
    (root / ALIGN).write_text(spec_text(ALIGN, [(1, GSCAN, True), (2, GSCAN, True)]))
    # a sample run with `_dir` exports: read from them, as before
    (root / SAMPLE).write_text(spec_text(SAMPLE, [(1, GSCAN, True), (2, GSCAN, True)]))
    (root / f"{SAMPLE}_dir").mkdir()
    for k in (1, 2):
        (root / f"{SAMPLE}_dir" / f"{SAMPLE}_{k:03d}.dat").write_text(
            "\n".join([f"#S {k}  {GSCAN}", "#L " + "  ".join(COLUMNS)] + _rows(1.0)) + "\n")
    return root


def _import(tmp_path: Path, root: Path, name="out") -> dict:
    out = tmp_path / name
    assert cli.main(["import", str(root), "--out", str(out)]) == cli.EXIT_OK
    return json.loads((out / "bundle.json").read_text(encoding="utf-8"))


def _run(bundle, stem):
    return next(r for r in bundle["runs"] if r["stem"] == stem)


# --- the shared splitter ----------------------------------------------------------------------------


def test_the_block_texts_are_exactly_the_scans_the_rule_lists():
    text = spec_text(REF, [(1, GSCAN, True), (2, ASCAN, True), (3, GSCAN, False), (5, GSCAN, True)])
    numbers, left_out = SFS.spec_file_scans(text)
    blocks = SFS.spec_file_scan_blocks(text)
    assert numbers == [1, 5] == [n for n, _ in blocks]
    assert [(x["scan"], x["why"]) for x in left_out] == [("2", "not an energy scan (ascan)"), ("3", "no data rows")]
    # each block runs from its own `#S` line to the next one, and holds only its own rows
    first, last = blocks[0][1], blocks[1][1]
    assert first.startswith(f"#S 1  {GSCAN}") and "#S 2" not in first and len(_rows(1.0)) == sum(
        1 for ln in first.splitlines() if ln and not ln.startswith("#"))
    assert last.startswith(f"#S 5  {GSCAN}")
    # the local import uses the same functions, not a copy of them
    assert B.spec_file_scans is SFS.spec_file_scans and B.SPEC_FILE_SCANS_RULE_ID == SFS.SPEC_FILE_SCANS_RULE_ID


def test_the_gate_takes_references_and_run_candidates_and_never_alignment():
    assert SFS.lists_in_file_scans("standard_or_reference", False)
    assert SFS.lists_in_file_scans("spec_acquisition", True)
    assert not SFS.lists_in_file_scans("spec_acquisition", False)
    assert not SFS.lists_in_file_scans("alignment", False)
    assert not SFS.lists_in_file_scans("alignment", True)


# --- A: the import rule -----------------------------------------------------------------------------


def test_a_reference_with_an_empty_dir_lists_the_energy_scans_inside_its_spec_file(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path))
    run = _run(bundle, REF)
    assert run["source_type"] == "standard_or_reference" and run["run_candidate"] is False
    acq = run["acquisition_source_id"]
    assert run["scans"] == [{"source_id": acq, "relative_path": REF, "scan_index": n} for n in (1, 3, 4)]
    assert run["scan_count"] == 3
    said = run["other_relationships"]["scans_in_spec_file"]
    assert said["rule_id"] == B.SPEC_FILE_SCANS_RULE_ID and said["scans"] == [1, 3, 4]
    assert said["left_out"] == [{"scan": "2", "command": "ascan", "why": "not an energy scan (ascan)"}]
    assert said["scan_dir_present_empty"] is True
    assert said["statement"].startswith("Its `<stem>_dir` folder exists but holds no scan file, so this run's scans")
    assert "#S 1, 3, 4" in said["statement"] and "#S 2 (not an energy scan (ascan))" in said["statement"]
    assert B.validate_bundle(bundle) == []


def test_an_alignment_file_stays_at_zero_scans(tmp_path):
    run = _run(_import(tmp_path, _folder(tmp_path)), ALIGN)
    assert run["source_type"] == "alignment"
    assert run["scans"] == [] and run["scan_count"] == 0
    assert "scans_in_spec_file" not in run["other_relationships"]


def test_a_run_with_dir_exports_is_unchanged(tmp_path):
    run = _run(_import(tmp_path, _folder(tmp_path)), SAMPLE)
    assert [s["relative_path"] for s in run["scans"]] == [f"{SAMPLE}_dir/{SAMPLE}_{k:03d}.dat" for k in (1, 2)]
    assert "scans_in_spec_file" not in run["other_relationships"]


def test_a_missing_dir_is_not_said_to_be_empty(tmp_path):
    root = _folder(tmp_path)
    (root / f"{REF}_dir").rmdir()
    said = _run(_import(tmp_path, root), REF)["other_relationships"]["scans_in_spec_file"]
    assert said["scans"] == [1, 3, 4] and "scan_dir_present_empty" not in said
    assert said["statement"].startswith("No scan file was found in a `<stem>_dir` folder")


def test_a_dir_holding_only_os_metadata_is_empty_and_one_holding_a_file_is_not(tmp_path):
    root = _folder(tmp_path)
    assert B._scan_dir_present_empty(root, REF, REF) is True
    (root / f"{REF}_dir" / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    assert B._scan_dir_present_empty(root, REF, REF) is True
    (root / f"{REF}_dir" / "SYN_other.txt").write_text("SYNTHETIC\n")
    assert B._scan_dir_present_empty(root, REF, REF) is False
    assert B._scan_dir_present_empty(None, REF, REF) is False


def test_a_wrapped_zip_with_a_directory_entry_says_the_dir_is_empty(tmp_path):
    root = _folder(tmp_path)
    zpath = _zip_of(root, tmp_path / "SYN_wrapped.zip", dir_entries=True)
    zipped, folder = _import(tmp_path, zpath, "z"), _import(tmp_path, root, "f")
    assert _run(zipped, REF)["scans"] == _run(folder, REF)["scans"]
    assert _run(zipped, REF)["other_relationships"]["scans_in_spec_file"]["scan_dir_present_empty"] is True


# --- A2: the HERFD selector reads the same in-file scans --------------------------------------------


def test_the_selector_proposes_vortdt_for_in_file_scans(tmp_path):
    bundle = _import(tmp_path, _folder(tmp_path))
    sel = _run(bundle, REF)["signal_selection"]
    assert sel["status"] == "proposed" and sel["primary_channel"] == "vortDT"
    assert sel["reason_code"] == "single_live_channel_and_established_element"
    vort = next(c for c in sel["channels"] if c["channel"] == "vortDT")
    assert vort["scans_present"] == 3 and vort["liveness"] == "live"  # #S 1, 3, 4 — not the alignment scan #S 2
    # an alignment file is not read for in-file scans, so it has nothing to select from
    assert _run(bundle, ALIGN)["signal_selection"]["reason_code"] == "no_candidate_channel"
    # a run with `_dir` exports is read from them
    sample = next(c for c in _run(bundle, SAMPLE)["signal_selection"]["channels"] if c["channel"] == "vortDT")
    assert sample["scans_present"] == 2


class _Unit:
    def __init__(self, stem, source_type, run_candidate, scans=(), path=None):
        self.stem, self.acquisition_path, self.source_type = stem, path or stem, source_type
        self.run_candidate, self.scans = run_candidate, scans


def test_in_file_stats_take_exactly_the_units_the_rule_reads():
    text = spec_text("SYN_U", [(1, GSCAN, True), (2, ASCAN, True), (3, GSCAN, True)])
    units = [_Unit("SYN_ref_pellet", "standard_or_reference", False), _Unit("SYN_al_align", "alignment", False),
             _Unit("SYN_run", "spec_acquisition", True), _Unit("SYN_run.dat", "spec_acquisition", True),
             _Unit("SYN_dir_run", "spec_acquisition", True, scans=("one export",)),
             _Unit("SYN_unlisted", "spec_acquisition", True),
             _Unit("SYN_up", "spec_acquisition", True, path="../SYN_up")]
    known = {u.acquisition_path for u in units} - {"SYN_unlisted"}
    read = []
    got = HI._in_file_scan_stats(units, known_paths=known, read_text=lambda p: read.append(p) or text)
    assert sorted(got) == ["SYN_ref_pellet", "SYN_run"] and sorted(read) == ["SYN_ref_pellet", "SYN_run"]
    assert [s.scan_path for s in got["SYN_run"]] == ["SYN_run#S1", "SYN_run#S3"]
    assert all(s.rows == len(GRID) for s in got["SYN_run"])
    # the selector's gate IS the rule's gate: same answer unit by unit
    stems = {u.stem for u in units}
    for u in units:
        reads = SFS.reads_in_file_scans(source_type=u.source_type, run_candidate=u.run_candidate, scan_count=len(u.scans),
                                        acquisition_path=u.acquisition_path, known_paths=known, stem=u.stem, stems=stems)
        assert reads == (u.acquisition_path in got), u.stem


def test_a_file_that_cannot_be_read_gives_the_selector_no_scans_as_the_run_lists_none():
    unit = _Unit("SYN_ref_pellet", "standard_or_reference", False)

    def boom(path):
        raise OSError("SYN unreadable")

    assert HI._in_file_scan_stats([unit], known_paths={unit.acquisition_path}, read_text=boom) == {"SYN_ref_pellet": []}
    assert HI._in_file_scan_stats([unit], known_paths={unit.acquisition_path}, read_text=lambda p: None) == {
        "SYN_ref_pellet": []}


def test_the_gate_refuses_a_listed_scan_an_unsafe_path_and_a_path_the_walk_did_not_list():
    ok = dict(source_type="standard_or_reference", run_candidate=False, scan_count=0, acquisition_path="SYN_a/SYN_ref",
              known_paths={"SYN_a/SYN_ref"})
    assert SFS.in_file_scans_apply(**ok)
    assert not SFS.in_file_scans_apply(**{**ok, "scan_count": 1})
    assert not SFS.in_file_scans_apply(**{**ok, "known_paths": set()})
    for bad in ("../SYN_ref", "/SYN_ref", "C:SYN_ref", None, ""):
        assert not SFS.in_file_scans_apply(**{**ok, "acquisition_path": bad, "known_paths": {bad}})


def test_when_the_gate_refuses_the_run_lists_no_scan_and_the_selector_reads_none(tmp_path, monkeypatch):
    # the mismatch the shared gate exists to prevent: a unit the rule does not read must not get a channel from
    # in-file scans its run does not list. Both sides call the one gate, so refusing it refuses both.
    monkeypatch.setattr(SFS, "in_file_scans_apply", lambda **kw: False)
    run = _run(_import(tmp_path, _folder(tmp_path)), REF)
    assert run["scans"] == [] and run["scan_count"] == 0
    assert run["signal_selection"]["reason_code"] == "no_candidate_channel"


def _zip_of(root: Path, zpath: Path, *, dir_entries: bool) -> Path:
    with zipfile.ZipFile(zpath, "w") as zf:
        for p in sorted(root.rglob("*")):
            name = f"{root.name}/{p.relative_to(root).as_posix()}"
            if p.is_dir():
                if dir_entries:
                    zf.writestr(name + "/", b"")
            else:
                zf.write(p, name)
    return zpath


def test_a_zip_root_gives_the_same_scans_and_signal_selection_as_the_folder(tmp_path):
    root = _folder(tmp_path)
    zipped = _import(tmp_path, _zip_of(root, tmp_path / "SYN_plain.zip", dir_entries=False), "z")
    folder = _import(tmp_path, root, "f")
    for stem in (REF, ALIGN, SAMPLE):
        assert _run(zipped, stem)["scans"] == _run(folder, stem)["scans"]
        assert _run(zipped, stem)["signal_selection"] == _run(folder, stem)["signal_selection"]
    assert _run(zipped, REF)["signal_selection"]["primary_channel"] == "vortDT"


def test_a_dir_of_empty_subfolders_and_os_files_is_empty_in_a_folder_and_in_a_zip(tmp_path):
    root = _folder(tmp_path)
    (root / f"{REF}_dir" / "SYN_sub" / "SYN_deeper").mkdir(parents=True)
    (root / f"{REF}_dir" / "SYN_sub" / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    with_dirs = _zip_of(root, tmp_path / "SYN_dirs.zip", dir_entries=True)
    without_dirs = _zip_of(root, tmp_path / "SYN_nodirs.zip", dir_entries=False)
    assert B._scan_dir_present_empty(root, REF, REF) is True
    assert B._scan_dir_present_empty(with_dirs, REF, REF) is True
    # no directory entries: only the OS file shows the folder is there, and it holds nothing else
    assert B._scan_dir_present_empty(without_dirs, REF, REF) is True
    # a file anywhere below makes it not empty, in all three
    (root / f"{REF}_dir" / "SYN_sub" / "SYN_deeper" / "SYN_other.txt").write_text("SYNTHETIC\n")
    assert B._scan_dir_present_empty(root, REF, REF) is False
    assert B._scan_dir_present_empty(_zip_of(root, tmp_path / "SYN_dirs2.zip", dir_entries=True), REF, REF) is False
    assert B._scan_dir_present_empty(_zip_of(root, tmp_path / "SYN_nodirs2.zip", dir_entries=False), REF, REF) is False


def test_a_zip_with_no_directory_entries_does_not_see_an_empty_dir(tmp_path):
    root = _folder(tmp_path)  # REF's `_dir` is truly empty: a ZIP without directory entries holds no trace of it
    zpath = _zip_of(root, tmp_path / "SYN_nodirs.zip", dir_entries=False)
    assert B._scan_dir_present_empty(zpath, REF, REF) is False
    said = _run(_import(tmp_path, zpath, "z"), REF)["other_relationships"]["scans_in_spec_file"]
    assert said["scans"] == [1, 3, 4] and "scan_dir_present_empty" not in said


def test_an_indented_s_line_starts_a_block_for_the_splitter_and_for_processing(tmp_path):
    from isaac_api.local_import.processing.readers import read_scan_file

    text = spec_text(REF, [(1, GSCAN, True), (2, ASCAN, True), (3, GSCAN, True)]).replace(
        f"#S 3  {GSCAN}", f"   #S 3  {GSCAN}").replace("\n", "\r\n")
    assert SFS.spec_file_scans(text) == ([1, 3], [{"scan": "2", "command": "ascan", "why": "not an energy scan (ascan)"}])
    path = tmp_path / "SYN_indented"
    path.write_bytes(text.encode("utf-8"))
    for number, block in SFS.spec_file_scan_blocks(text):
        table = read_scan_file(path, scan=number)
        assert table.error is None and f"scan_block_read:{number}" in table.notes
        rows = [ln for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        assert table.n_rows == len(rows) == len(GRID)


def test_processing_uses_vortdt_over_i0_on_absev_for_the_reference(tmp_path, capsys):
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
    key = _run(b, REF)["run_key"]
    gid = next(g["group_id"] for g in b["record_groups"] if key in g["member_run_keys"])
    [res] = [r for r in b["processing_results"] if r["group_id"] == gid and r["source"] == "isaac_protocol"]
    assert [i["scan"] for i in res["inputs"]] == [1, 3, 4]
    assert all(i["channel"] == "(vortDT)/I0" and f"scan_block_read:{i['scan']}" in i["reader_notes"] for i in res["inputs"])
    choice = res["channel_choice"]
    assert choice["energy"] == "absev" and choice["signal_columns"] == ["vortDT"] and choice["i0"] == "I0"
    assert choice["basis"]["basis"] == "bl15_signal_selection"
    assert (res.get("applicability") or {}).get("status") != B.NOT_APPLICABLE
