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
    zpath = tmp_path / "SYN_wrapped.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for p in sorted(root.rglob("*")):
            name = f"{root.name}/{p.relative_to(root).as_posix()}"
            if p.is_dir():
                zf.writestr(name + "/", b"")
            else:
                zf.write(p, name)
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


def test_in_file_stats_skip_units_with_dir_stats_alignment_and_exported_copies():
    class U:
        def __init__(self, stem, source_type, run_candidate, scans=()):
            self.stem, self.acquisition_path, self.source_type = stem, stem, source_type
            self.run_candidate, self.scans = run_candidate, scans

    text = spec_text("SYN_U", [(1, GSCAN, True), (2, ASCAN, True), (3, GSCAN, True)])
    units = [U("SYN_ref_pellet", "standard_or_reference", False), U("SYN_al_align", "alignment", False),
             U("SYN_run", "spec_acquisition", True), U("SYN_run.dat", "spec_acquisition", True),
             U("SYN_dir_run", "spec_acquisition", True)]
    read = []
    got = HI._in_file_scan_stats(units, scan_stats_by_stem={"SYN_dir_run": ["x"]},
                                 read_text=lambda p: read.append(p) or text)
    assert sorted(got) == ["SYN_ref_pellet", "SYN_run"] and sorted(read) == ["SYN_ref_pellet", "SYN_run"]
    assert [s.scan_path for s in got["SYN_run"]] == ["SYN_run#S1", "SYN_run#S3"]
    assert all(s.rows == len(GRID) for s in got["SYN_run"])
    assert HI._in_file_scan_stats(units[:1], scan_stats_by_stem={}, read_text=lambda p: None) == {}


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
