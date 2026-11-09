"""SSRL XDC 2.0 text scans, bare ``NAME.NNN`` scan names, a slit size that is no potential, and element-prefixed
calibration names — on SYNTHETIC files only (every name below is invented: ``SYN…``, ``ZZ…``; dated 2099 or 2025).

What these pin:

* the reader accepts the CLOSED set of signatures {2.0, 4.0} (CRLF too), records each scan's stated version, and
  still refuses every other version and the binary variant of both;
* a bare ``NAME.NNN`` file that passes the text sniff is a scan of the run ``NAME`` (companions and ``.exp`` as for
  ``_A`` runs); one that fails it (a binary original) is left exactly as before;
* ``X.NNN`` beside ``X_A.NNN`` are two runs, never one: the ``_A`` run keeps ``X`` and every ``X``-named companion,
  the bare one is ``X.NNN`` with none, and both carry an anomaly naming the other;
* bare runs come after every other run, so they renumber nothing; a 4.0 ``_A``-only import is pinned;
* ``1v x 3H mm`` (a size) is no potential mention and no set-point; genuine forms keep their readings;
* an element symbol + ``calib`` / ``foil`` (``SCALIB_901``, ``FeFOIL``) is proposed as a reference, with guards.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import grouping as G
from isaac_api.local_import import questions as Q
from isaac_api.local_import import readers
from isaac_api.local_import.readers import ssrl_xdc as x

from test_local_import_reader_ssrl_xdc import make_scan
from test_local_import_reader_two_column import make_two

V2 = "SSRL   EXAFS Data Collector 2.0"
V2_COLUMNS = ["Real time clock", "Requested Energy", "Achieved Energy", "I0", "I1", "diode", "FF"]
BINARY_V2 = b"SSRL - EXAFS Data Collector 2.0\x00\x00binary rest"
BINARY_V4 = b"SSRL - EXAFS Data Collector 4.0\x00\x00binary rest"


def make_v2(path: Path, **kw) -> Path:
    """A 2.0 text scan: the 4.0 layout with the 2.0 signature and CRLF line endings."""
    kw.setdefault("eol", "\r\n")
    kw.setdefault("columns", V2_COLUMNS)
    kw.setdefault("timestamp", "Sun May 17 16:21:05 2099")
    make_scan(path, **kw)
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b"SSRL   EXAFS Data Collector 4.0", V2.encode("ascii"), 1))
    return path


def _runs(root: Path) -> dict[str, x.GenericRun]:
    return {r.label: r for r in x.collect_generic_runs(root)}


# --- FIX 1: the 2.0 signature ----------------------------------------------------------------------------------


def test_the_accepted_signatures_are_exactly_two_and_four(tmp_path):
    assert x.ACCEPTED_VERSIONS == ("2.0", "4.0")
    assert set(x.SIGNATURES.values()) == {V2, "SSRL   EXAFS Data Collector 4.0"}
    assert x.sniff(make_v2(tmp_path / "SYN_v2_A.001"))
    assert x.sniff(make_v2(tmp_path / "SYN_v2lf_A.001", eol="\n"))
    for i, first in enumerate((
        b"SSRL   EXAFS Data Collector 2.1",
        b"SSRL   EXAFS Data Collector 3.0",
        b"SSRL   EXAFS Data Collector 1.0",
        b"SSRL   EXAFS Data Collector 4.1",
        b"SSRL   EXAFS Data Collector 2",
        b"SSRL   EXAFS Data Collector 2.0 extra",
        b"SSRL EXAFS Data Collector 2.0",
        b"SSRL - EXAFS Data Collector 2.0",
        b"ssrl   exafs data collector 2.0",
    )):
        p = tmp_path / f"near{i}_A.001"
        p.write_bytes(first + b"\r\nrest\r\n")
        assert not x.sniff(p), first
    for i, binary in enumerate((BINARY_V2, BINARY_V4)):
        p = tmp_path / f"bin{i}_A.001"
        p.write_bytes(binary)
        assert not x.sniff(p)
        with pytest.raises(ValueError, match="not an SSRL EXAFS Data Collector 2.0 or 4.0 text scan"):
            x.read(p)


def test_a_v2_scan_reads_with_the_same_layout_and_states_its_version(tmp_path):
    p = make_v2(tmp_path / "SYNSAMP_040.001", points=5, free_text=("SYN sample line", "slits= 1v x 3H mm"))
    scan = x.read(p)
    assert scan.version == "2.0" and scan.anomalies == []
    assert scan.points_declared == scan.points_found == 5 and scan.column_names == V2_COLUMNS
    assert scan.timestamp_literal == "Sun May 17 16:21:05 2099" and scan.timezone == "not_stated"
    keyed = {h.key: h for h in scan.header_lines}
    assert keyed["signature"].literal == V2
    assert keyed["header_line_8_literal"].literal == "gain line literal" and keyed["header_line_8_literal"].tokens is None
    assert [h.line for h in scan.free_text_lines] == [9, 10]
    assert x.read(make_scan(tmp_path / "SYN_v4_A.001")).version == "4.0"


def test_a_2_0_scan_in_a_4_0_series_stays_out_of_the_run_as_before_and_is_named(tmp_path):
    make_v2(tmp_path / "SYNMIX_A.001", free_text=("pH 13",))
    make_scan(tmp_path / "SYNMIX_A.002")
    make_v2(tmp_path / "SYNMIX_A.003")
    result = x.collect_generic(tmp_path)
    [run] = result.runs
    assert [s["relative_path"] for s in run.scans] == ["SYNMIX_A.002"] and {s["version"] for s in run.scans} == {"4.0"}
    assert not [st for st in run.statements if st["source_relative_path"] != "SYNMIX_A.002" and st["key"] != "exp_data_file"]
    assert [(u["relative_path"], u["reason_code"]) for u in result.unparsed] == [
        ("SYNMIX_A.001", "signature_not_recognised"), ("SYNMIX_A.003", "signature_not_recognised")]
    [flag] = [a for a in run.anomalies if a["kind"] == x.V2_IN_V4_KIND]
    assert flag["severity"] == "flag" and "SYNMIX_A.001, SYNMIX_A.003" in flag["detail"] and "NOT read" in flag["detail"]


def test_a_series_with_only_2_0_scans_is_read_and_states_each_version(tmp_path):
    make_v2(tmp_path / "SYNV2_A.001")
    make_v2(tmp_path / "SYNV2_A.002")
    run = _runs(tmp_path)["SYNV2"]
    assert [s["version"] for s in run.scans] == ["2.0", "2.0"] and run.header_differences == []


# --- FIX 2: bare NAME.NNN names --------------------------------------------------------------------------------


def test_bare_v2_text_scans_are_one_run_with_their_companions(tmp_path):
    root = tmp_path / "SYNbt"
    make_v2(root / "SYNSAMP_040.002", points=3)
    make_v2(root / "SYNSAMP_040.001", points=4)
    (root / "SYNSAMP_040.rgn").write_text("r")
    (root / "SYNSAMP_040.det").write_text("d")
    (root / "SYNSAMP_040.exp").write_text("COMMENTS1 x\r\nDATA_FILE SYNSAMP\r\n")
    (root / "binary").mkdir()
    (root / "binary" / "SYNSAMP_040.001").write_bytes(BINARY_V2)
    result = x.collect_generic(root)
    [run] = result.runs
    assert run.label == "SYNSAMP_040" and run.run_key == "ssrl_xdc_v1:SYNSAMP_040" and run.scan_indices == [1, 2]
    assert [s["relative_path"] for s in run.scans] == ["SYNSAMP_040.001", "SYNSAMP_040.002"]
    assert [s["points"] for s in run.scans] == [4, 3] and {s["version"] for s in run.scans} == {"2.0"}
    assert {c["relative_path"]: c["role"] for c in run.companions} == {
        "SYNSAMP_040.rgn": "region", "SYNSAMP_040.det": "detector", "SYNSAMP_040.exp": "experiment",
        "binary/SYNSAMP_040.001": "binary_original"}
    [data_file] = [s for s in run.statements if s["key"] == "exp_data_file"]
    assert data_file["literal"] == "SYNSAMP" and data_file["locator"] == "line:2"
    assert result.unparsed == [] and not [a for a in run.anomalies if a["kind"] == x.COLLISION_KIND]


def test_a_bare_binary_original_is_left_as_before_and_never_listed(tmp_path):
    root = tmp_path / "SYNbt"
    make_scan(root / "SYNRUN_A.001")
    (root / "binary").mkdir()
    (root / "binary" / "SYNRUN.001").write_bytes(BINARY_V4)
    (root / "binary" / "SYNRUN.002").write_bytes(BINARY_V2)
    (root / "SYNLOOSE.003").write_bytes(BINARY_V4)  # a binary bare name outside binary/: not a scan, not listed
    result = x.collect_from_files(readers.walk(root, x.Limits().archive, [], {}))
    assert [r.label for r in result.runs] == ["SYNRUN"] and result.late_runs == [] and result.unparsed == []
    assert {c["relative_path"]: c["role"] for c in result.runs[0].companions} == {
        "binary/SYNRUN.001": "binary_original", "binary/SYNRUN.002": "binary_original"}
    assert "SYNLOOSE.003" not in {rel for rel, _ in result.consumed}


def test_a_bare_text_file_where_a_runs_companions_are_looked_for_stays_its_companion(tmp_path):
    root = tmp_path / "SYNbt"
    make_scan(root / "SYNRUN_A.001")
    make_v2(root / "binary" / "SYNRUN.001")  # a TEXT file in binary/: still the run's binary original, as before
    (root / "binary" / "SYNRUN.002").write_bytes(BINARY_V4)
    make_v2(root / "SYNRUN" / "SYNINNER.001")  # a text file in the run's same-named folder: still context, as before
    make_v2(root / "SYNLONE" / "SYNLONE_IN.001")  # no run SYNLONE beside the folder: a bare series of its own
    result = x.collect_from_files(readers.walk(root, x.Limits().archive, [], {}))
    assert [r.run_key for r in result.runs] == ["ssrl_xdc_v1:SYNRUN"]
    assert [r.run_key for r in result.late_runs] == ["ssrl_xdc_v1:SYNLONE/SYNLONE_IN"]
    assert {c["relative_path"]: c["role"] for c in result.runs[0].companions} == {
        "binary/SYNRUN.001": "binary_original", "binary/SYNRUN.002": "binary_original",
        "SYNRUN/SYNINNER.001": "other_context"}
    consumed = [rel for rel, _ in result.consumed]
    assert len(consumed) == len(set(consumed)) and result.unparsed == []


def test_a_bare_series_is_a_parent_for_its_own_binary_folder(tmp_path):
    root = tmp_path / "SYNbt"
    make_v2(root / "SYNBARE.001")
    make_v2(root / "binary" / "SYNBARE.001")
    [run] = x.collect_generic_runs(root)
    assert run.run_key == "ssrl_xdc_v1:SYNBARE"
    assert [(c["relative_path"], c["role"]) for c in run.companions] == [("binary/SYNBARE.001", "binary_original")]


def test_an_oversized_bare_text_scan_is_listed_with_its_size(tmp_path):
    root = tmp_path / "SYNbt"
    make_v2(root / "SYNBIG.001")
    result = x.collect_generic(root, x.Limits(max_scan_bytes=100))
    assert result.runs == [] and [(u["relative_path"], u["reason_code"]) for u in result.unparsed] == [("SYNBIG.001", "file_too_large")]


def _collision_folder(root: Path) -> Path:
    make_scan(root / "SYNCAL_039_A.001")
    make_scan(root / "SYNCAL_039_A.002")
    make_v2(root / "SYNCAL_039.001")
    make_v2(root / "SYNCAL_039.002")
    (root / "SYNCAL_039.rgn").write_text("r")
    (root / "SYNCAL_039.exp").write_text("DATA_FILE SYNCAL\n")
    (root / "SYNCAL_039").mkdir()
    (root / "SYNCAL_039" / "SYN_context.txt").write_text("c")
    (root / "binary").mkdir()
    (root / "binary" / "SYNCAL_039.001").write_bytes(BINARY_V4)
    return root


def test_x_and_x_a_in_one_folder_are_two_runs_and_the_a_run_keeps_its_name_and_companions(tmp_path):
    root = _collision_folder(tmp_path / "SYNbt")
    result = x.collect_from_files(readers.walk(root, x.Limits().archive, [], {}))
    [a_run] = result.runs
    [bare] = result.late_runs
    assert (a_run.label, a_run.run_key) == ("SYNCAL_039", "ssrl_xdc_v1:SYNCAL_039")
    assert (bare.label, bare.run_key) == ("SYNCAL_039.NNN", "ssrl_xdc_v1:SYNCAL_039.NNN")
    assert [s["relative_path"] for s in a_run.scans] == ["SYNCAL_039_A.001", "SYNCAL_039_A.002"]
    assert [s["relative_path"] for s in bare.scans] == ["SYNCAL_039.001", "SYNCAL_039.002"]
    assert {c["relative_path"] for c in a_run.companions} == {
        "SYNCAL_039.rgn", "SYNCAL_039.exp", "SYNCAL_039/SYN_context.txt", "binary/SYNCAL_039.001"}
    assert bare.companions == [] and not [s for s in bare.statements if s["key"] == "exp_data_file"]
    assert [s["literal"] for s in a_run.statements if s["key"] == "exp_data_file"] == ["SYNCAL"]
    [a_flag] = [a for a in a_run.anomalies if a["kind"] == x.COLLISION_KIND]
    [b_flag] = [a for a in bare.anomalies if a["kind"] == x.COLLISION_KIND]
    assert "SYNCAL_039.NNN" in a_flag["detail"] and "not merged" in a_flag["detail"] and a_flag["severity"] == "flag"
    assert "SYNCAL_039_A.NNN" in b_flag["detail"] and "A scientist decides" in b_flag["detail"]
    consumed = [rel for rel, _ in result.consumed]
    assert len(consumed) == len(set(consumed))
    # deterministic: the same folder gives the same runs again
    again = x.collect_from_files(readers.walk(root, x.Limits().archive, [], {}))
    assert [(r.run_key, r.companions) for r in again.runs + again.late_runs] == [(r.run_key, r.companions) for r in (a_run, bare)]


def test_a_collision_is_found_without_case_and_its_companions_are_compared_so_too(tmp_path):
    root = tmp_path / "SYNbt"
    make_scan(root / "syncal_041_A.001")
    make_v2(root / "SYNCAL_041.001")
    (root / "SYNCAL_041.rgn").write_text("r")  # named like the bare series: the _A run's, as the collision is found
    (root / "SYNCAL_041.exp").write_text("DATA_FILE syncal\n")
    (root / "binary").mkdir()
    (root / "binary" / "SYNCAL_041.001").write_bytes(BINARY_V4)
    runs = _runs(root)
    assert sorted(runs) == ["SYNCAL_041.NNN", "syncal_041"]
    assert all(any(a["kind"] == x.COLLISION_KIND for a in r.anomalies) for r in runs.values())
    assert {c["relative_path"] for c in runs["syncal_041"].companions} == {
        "SYNCAL_041.rgn", "SYNCAL_041.exp", "binary/SYNCAL_041.001"}
    assert [s["literal"] for s in runs["syncal_041"].statements if s["key"] == "exp_data_file"] == ["syncal"]
    assert runs["SYNCAL_041.NNN"].companions == []


def test_no_two_runs_ever_share_a_run_key(tmp_path):
    root = tmp_path / "SYNbt"
    make_scan(root / "SYNK_A.001")
    make_v2(root / "SYNK.001")  # collides with SYNK_A: becomes SYNK.NNN ...
    make_v2(root / "SYNK.NNN.001")  # ... which a bare series of that very name already holds
    result = x.collect_from_files(readers.walk(root, x.Limits().archive, [], {}))
    keys = [r.run_key for r in result.runs + result.late_runs]
    assert len(keys) == len(set(keys)) == 3
    assert keys == ["ssrl_xdc_v1:SYNK", "ssrl_xdc_v1:SYNK.NNN-2", "ssrl_xdc_v1:SYNK.NNN"]
    flagged = {r.run_key for r in result.runs + result.late_runs if any(a["kind"] == x.COLLISION_KIND for a in r.anomalies)}
    assert flagged == {"ssrl_xdc_v1:SYNK", "ssrl_xdc_v1:SYNK.NNN-2"}


def test_the_same_name_in_another_folder_is_no_collision(tmp_path):
    root = tmp_path / "SYNbt"
    make_scan(root / "one" / "SYNCAL_042_A.001")
    make_v2(root / "two" / "SYNCAL_042.001")
    runs = x.collect_generic_runs(root)
    assert [r.run_key for r in runs] == ["ssrl_xdc_v1:one/SYNCAL_042", "ssrl_xdc_v1:two/SYNCAL_042"]
    assert not [a for r in runs for a in r.anomalies if a["kind"] == x.COLLISION_KIND]


def test_runs_reader_1_0_0_did_not_find_come_after_every_other_reader(tmp_path):
    root = tmp_path / "SYNbt"
    make_v2(root / "aa" / "SYNAAA.001")  # a bare series: sorts FIRST by folder, still comes last
    make_v2(root / "ab" / "SYNV2_A.001")  # a 2.0-only _A series: late too
    make_v2(root / "ac" / "SYNMIX_A.001")  # a 2.0 + 4.0 _A series: 1.0.0 found it (its 4.0 scan only), in its place
    make_scan(root / "ac" / "SYNMIX_A.002")
    make_scan(root / "zz" / "SYNZZZ_A.001")
    make_two(root / "SYNtwo.txt")
    u = readers.collect_all_generic(root)
    assert [(r.profile, r.label) for r in u.runs] == [
        ("ssrl_xdc_v1", "SYNMIX"), ("ssrl_xdc_v1", "SYNZZZ"), ("two_column_v1", "SYNtwo"),
        ("ssrl_xdc_v1", "SYNV2"), ("ssrl_xdc_v1", "SYNAAA")]
    assert u.late_run_keys == ["ssrl_xdc_v1:ab/SYNV2", "ssrl_xdc_v1:aa/SYNAAA"]
    assert "aa/SYNAAA.001" in {c["relative_path"] for c in u.claims} and "aa/SYNAAA.001" not in u.unclaimed


def _import(src: Path, out: Path) -> dict:
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    data = json.loads((out / "bundle.json").read_text())
    assert B.validate_bundle(data) == []
    return data


def test_a_bare_v2_folder_imports_runs_with_start_times_and_valid_bundles(tmp_path):
    src = tmp_path / "src" / "SYNbt2010"
    make_v2(src / "SYNSAMP_040.001", timestamp="Sun May 17 16:21:05 2099")
    make_v2(src / "SYNSAMP_040.002", timestamp="Sun May 17 16:41:05 2099")
    make_v2(src / "SCALIB_901.001", timestamp="Sun May 17 15:00:00 2099")
    data = _import(src, tmp_path / "out")
    assert [(r["run_id"], r["stem"]) for r in data["runs"]] == [("run-001", "SCALIB_901"), ("run-002", "SYNSAMP_040")]
    starts = {c["run_id"]: c for c in data["candidates"] if B.is_local_clock_start(c)}
    assert set(starts) == {"run-001", "run-002"}
    assert "2.0 or 4.0" in starts["run-001"]["rule"]
    roles = {g["member_run_keys"][0]: g["role"] for g in G.propose_record_groups(data)}
    assert roles == {"ssrl_xdc_v1:SCALIB_901": "reference", "ssrl_xdc_v1:SYNSAMP_040": "sample"}


def test_the_collision_folder_imports_two_runs_and_shows_the_flag_on_both(tmp_path):
    src = _collision_folder(tmp_path / "src" / "SYNbt")
    data = _import(src, tmp_path / "out")
    by_stem = {r["stem"]: r for r in data["runs"]}
    assert [r["stem"] for r in data["runs"]] == ["SYNCAL_039", "SYNCAL_039.NNN"]
    assert by_stem["SYNCAL_039"]["run_id"] == "run-001"
    for r in by_stem.values():
        assert [a["kind"] for a in r["other_relationships"]["anomalies"] if a["kind"] == x.COLLISION_KIND] == [x.COLLISION_KIND]
    assert by_stem["SYNCAL_039.NNN"]["other_relationships"]["companions"] == []


# --- a 4.0 `_A`-only import is unchanged (pinned against the build before these fixes) -------------------------


def _a_only_folder(src: Path) -> Path:
    make_scan(src / "SYNSAMP_001_A.001", free_text=("0.1 M HClO4, pH 1.3, -0.3 V vs RHE",))
    make_scan(src / "SYNSAMP_001_A.002", free_text=("0.1 M HClO4, pH 1.3, -0.3 V vs RHE",), timestamp="Sun Jul 27 14:31:47 2025")
    make_scan(src / "SYNSAMP_002_A.001", free_text=("Sample A in 1M KOH 0Vrhe",), timestamp="Mon Jul 28 10:00:00 2025")
    make_scan(src / "sub" / "SYNFOIL_003_A.001")
    make_scan(src / "sub" / "SYNOTHER_004_A.001", free_text=("E = -0.2 V (RHE)",))
    (src / "SYNSAMP_001.rgn").write_text("r")
    (src / "SYNSAMP_001.exp").write_text("DATA_FILE SYNSAMP\n")
    (src / "binary").mkdir()
    (src / "binary" / "SYNSAMP_001.001").write_bytes(BINARY_V4)
    (src / "binary" / "SYNSAMP_002.001").write_bytes(BINARY_V4)
    (src / "sub" / "SYNNOTE.007").write_bytes(b"\x00\x01not text")
    return src


def _mixed_version(src: Path) -> Path:  # H1: a mixed series that sorts FIRST and whose 2.0 scans state new fields
    make_scan(src / "xdc" / "SYN0_000_A.001", free_text=("dry powder",))
    make_v2(src / "xdc" / "SYN0_000_A.002", free_text=("pH 13", "0.1 M KOH"))
    make_scan(src / "xdc" / "SYNA_001_A.001", free_text=("-0.3 V vs RHE",))
    make_v2(src / "xdc" / "SYNA_001_A.002", free_text=("E = 0.7 V vs RHE",))
    make_scan(src / "xdc" / "SYNB_002_A.001")
    make_v2(src / "a" / "SYNOLD_A.001", free_text=("-0.2 V vs RHE",))  # 2.0 only: a new, late run
    return src


def _a_plus_bare(src: Path) -> Path:  # H2: a bare series beside `_A` runs with comment candidates
    make_scan(src / "SYNX_A.001", free_text=("-0.3 V vs RHE", "0.1 M HClO4"))
    make_scan(src / "SYNZ_A.001", free_text=("pH 1.3",))
    make_scan(src / "aa" / "SYNY.001", free_text=("-0.1 V vs RHE",))
    return src


def _collision_mixed(src: Path) -> Path:  # a collided pair, a bare series sorting first, a later `_A` run
    make_scan(src / "SYNCAL_039_A.001", free_text=("-0.3 V vs RHE",))
    make_v2(src / "SYNCAL_039.001", free_text=("-0.4 V vs RHE",))
    (src / "SYNCAL_039.rgn").write_text("r")
    make_scan(src / "AAA" / "SYNAAA.001", free_text=("pH 2",))
    make_scan(src / "zzz" / "SYNQ_A.001", free_text=("0.1 M HClO4, pH 1.3",))
    return src


def _parents(src: Path) -> Path:  # M1: bare text files where a run's companions are looked for
    make_scan(src / "SYNX_A.001", free_text=("-0.3 V vs RHE",))
    make_scan(src / "SYNX" / "SYNinner.001")
    make_scan(src / "binary" / "SYNX.001")
    return src


SCENARIOS = {"a_only": _a_only_folder, "mixed_version": _mixed_version, "a_plus_bare": _a_plus_bare,
             "collision_mixed": _collision_mixed, "parents": _parents}


def _digest(rows) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def id_summary(name: str, tmp_path: Path) -> dict:
    """What an import of scenario ``name`` gives: its runs, candidates and missing values IN ORDER (each with what it
    is), and its question ids and proposed groups. Generated on bd38c535 by running this function there."""
    data = _import(SCENARIOS[name](tmp_path / "src" / "SYNbt"), tmp_path / "out")
    qs = json.loads((tmp_path / "out" / "questions.json").read_text())["questions"]
    key_of = {r["run_id"]: r["run_key"] for r in data["runs"]}
    return {
        "runs": [[r["run_id"], r["run_key"], r["stem"], r["other_relationships"]["companions"]] for r in data["runs"]],
        "candidates": [[c["candidate_id"], key_of.get(c["run_id"]), c["target_field_path"], c["value"]]
                       for c in data["candidates"]],
        "missing": [[m["value_id"], key_of.get(m["run_id"]), m["target_field_path"]] for m in data["missing_values"]],
        "questions": sorted(q["question_id"] for q in qs),
        "groups": sorted([g["group_id"], g["role"], g["member_run_keys"]] for g in G.propose_record_groups(data)),
    }


def base_pin(summary: dict) -> dict:
    """The pinned form of a summary: lengths and digests of the ordered parts, and the question and group ids."""
    out = {part: [len(summary[part]), _digest(summary[part])] for part in ("runs", "candidates", "missing")}
    return {**out, "questions": summary["questions"], "groups": [g[0] for g in summary["groups"]]}


#: :func:`base_pin` of :func:`id_summary` as the build BEFORE the 2.0 / bare-name changes (bd38c535) gave it, per
#: scenario. Every run, candidate and missing value it had keeps its id AND what it is (the first N of each sequence
#: are those N, unchanged), every question id stands, and every group it proposed is still proposed.
BASE_PINS: dict = {'a_only': {'candidates': [14, '6a15bdaf6d059333'],
            'groups': ['rg-24333b7f8035885e', 'rg-6098e1d04ec64ded', 'rg-971c505d1bf3bb51', 'rg-f14f275c41887578'],
            'missing': [102, 'a466e84380626a0e'],
            'questions': ['Q-022948a41b', 'Q-0247123296', 'Q-053fe7781b', 'Q-1116b6497f', 'Q-2991ec8448',
                          'Q-2d666c4721', 'Q-2d73f98be4', 'Q-308f52703b', 'Q-36106ed842', 'Q-3ebd86baeb',
                          'Q-3ec9492979', 'Q-42697d9fc8', 'Q-456d87f0a8', 'Q-4c06a3da1b', 'Q-4c2d609f23',
                          'Q-4e5032e315', 'Q-5b4328bd6a', 'Q-5f23f0459b', 'Q-7d393da8fc', 'Q-8de9f25cd3',
                          'Q-994aa26655', 'Q-9d10c7c6ef', 'Q-9d5ac9103f', 'Q-9f8a7c53a0', 'Q-a350f1f2e4',
                          'Q-a9092e983c', 'Q-b7373c4500', 'Q-c5f717329d', 'Q-c8162306c2', 'Q-e7bdcfb24f',
                          'Q-ecce70710b', 'Q-f12b05fb72', 'Q-f6879d84e2'],
            'runs': [4, '94949c2351b4f44f']},
 'a_plus_bare': {'candidates': [7, '448b81a67822f2d4'],
                 'groups': ['rg-6b35b3abbae54cb5', 'rg-eb53d4528925d1c7'],
                 'missing': [53, 'bba321c71f817fde'],
                 'questions': ['Q-053fe7781b', 'Q-1116b6497f', 'Q-308f52703b', 'Q-36106ed842', 'Q-42697d9fc8',
                               'Q-456d87f0a8', 'Q-4c06a3da1b', 'Q-4c2d609f23', 'Q-5b4328bd6a', 'Q-5f23f0459b',
                               'Q-8de9f25cd3', 'Q-994aa26655', 'Q-9d10c7c6ef', 'Q-9d5ac9103f', 'Q-b7373c4500',
                               'Q-c1524efd29', 'Q-c5f717329d', 'Q-c8162306c2', 'Q-ecce70710b', 'Q-f12b05fb72'],
                 'runs': [2, 'f0f1645210f6f3ed']},
 'collision_mixed': {'candidates': [7, '9770c67a4597386f'],
                     'groups': ['rg-0b6ea60706b8eb7d', 'rg-6b25bd84f6450b11'],
                     'missing': [53, '38269602ba3181f9'],
                     'questions': ['Q-053fe7781b', 'Q-1116b6497f', 'Q-2d73f98be4', 'Q-308f52703b', 'Q-36106ed842',
                                   'Q-42697d9fc8', 'Q-4c2d609f23', 'Q-5b4328bd6a', 'Q-5f23f0459b', 'Q-7d393da8fc',
                                   'Q-8de9f25cd3', 'Q-994aa26655', 'Q-9d10c7c6ef', 'Q-9d5ac9103f', 'Q-b7373c4500',
                                   'Q-c1524efd29', 'Q-c5f717329d', 'Q-c8162306c2', 'Q-ecce70710b', 'Q-f12b05fb72'],
                     'runs': [2, '353467d9a4f50da2']},
 'mixed_version': {'candidates': [5, 'fb901e62cd1b1c52'],
                   'groups': ['rg-4ec23f9df9119ee6', 'rg-4fbd10387d8eb154', 'rg-965a642776a26dfd'],
                   'missing': [83, 'a2012113c0e72d7f'],
                   'questions': ['Q-053fe7781b', 'Q-2991ec8448', 'Q-2d666c4721', 'Q-308f52703b', 'Q-36106ed842',
                                 'Q-42697d9fc8', 'Q-45e85d54c6', 'Q-4c2d609f23', 'Q-5b4328bd6a', 'Q-5f23f0459b',
                                 'Q-8de9f25cd3', 'Q-9d10c7c6ef', 'Q-9d5ac9103f', 'Q-a350f1f2e4', 'Q-b7373c4500',
                                 'Q-c5f717329d', 'Q-c8162306c2', 'Q-e7bdcfb24f', 'Q-ecce70710b', 'Q-f12b05fb72',
                                 'Q-f6879d84e2'],
                   'runs': [3, 'b0888a5462b139ca']},
 'parents': {'candidates': [3, '07cc4456daf8e0c8'],
             'groups': ['rg-6b35b3abbae54cb5'],
             'missing': [29, '2e8999c9c7e25c86'],
             'questions': ['Q-1116b6497f', 'Q-308f52703b', 'Q-36106ed842', 'Q-4c2d609f23', 'Q-5b4328bd6a',
                           'Q-8de9f25cd3', 'Q-994aa26655', 'Q-9d10c7c6ef', 'Q-9d5ac9103f', 'Q-b7373c4500',
                           'Q-c5f717329d', 'Q-c8162306c2', 'Q-f12b05fb72'],
             'runs': [1, '7d7d1ea8291a646c']}}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_id_the_build_before_gave_stands_and_new_ones_only_follow(name, tmp_path):
    pin = BASE_PINS[name]
    now = id_summary(name, tmp_path)
    for part in ("runs", "candidates", "missing"):
        n, digest = pin[part]
        assert len(now[part]) >= n and _digest(now[part][:n]) == digest, part
    assert set(pin["questions"]) <= set(now["questions"])
    assert set(pin["groups"]) <= {g[0] for g in now["groups"]}
    if name in ("a_only", "parents"):  # nothing new to find: everything is as it was
        assert base_pin(now) == pin
    if name == "mixed_version":  # the 2.0 scans in 4.0 series change nothing; the 2.0-only run only follows
        assert [r[1] for r in now["runs"]][pin["runs"][0]:] == ["ssrl_xdc_v1:a/SYNOLD"]
        values = {(c[1], c[2]): c[3] for c in now["candidates"]}
        assert values[("ssrl_xdc_v1:xdc/SYNA_001", POT)] == -0.3
        assert ("ssrl_xdc_v1:xdc/SYN0_000", "context.electrochemistry.pH") not in values


# --- FIX 3: a slit size is no potential ------------------------------------------------------------------------

POT = "context.electrochemistry.potential_setpoint_V"


def _pot(line: str) -> list:
    return [r["value"] for r in Q.header_comment_readings(line) if r["path"] == POT]


@pytest.mark.parametrize("line", [
    "slits= 1v x 3H mm", "beam 3x1 (1 v x 3 H)", "slit 0.5v x 4h", "1 v x 3 h um", "slits 1v x 3h; beam",
    "slits 1v×3h", "slit 1v*3h", "spot 3H x 1v mm", "1V  x  3H mm", "beam (1 V x 3 H) mm", "slits 1v X 3h",
    "1v x 3h µm", "slit 1.0 V x 10.0 H", "slits: 3H x 1v",
])
def test_a_dimension_is_no_potential_mention_and_no_set_point(line):
    assert _pot(line) == []
    assert Q.header_potential_mentions(line) == []
    assert Q.header_potentials_in_line(line) == []
    assert Q.dimension_spans(line)


@pytest.mark.parametrize("line,value,scale", [
    ("-0.3 V vs RHE", -0.3, "RHE"),
    ("0V vs RHE", 0.0, "RHE"),
    ("-0.0V vs RHE", 0.0, "RHE"),
    ("-300 mV vs RHE", -0.3, "RHE"),
    ("0.5 V vs. Ag/AgCl", 0.5, "Ag/AgCl"),
    ("beam 1 x 3 mm, -0.3 V vs RHE", -0.3, "RHE"),
])
def test_a_plain_set_point_still_reads(line, value, scale):
    got = [r for r in Q.header_comment_readings(line) if r["path"] == POT]
    assert [(r["value"], r["scale"]) for r in got] == [(value, scale)]
    assert Q.dimension_spans(line) == []


@pytest.mark.parametrize("line,literal", [
    ("0.1 M NaClO4 pH 1 -0.15V vs RHE scans", "-0.15V vs RHE"),
    ("0Vrhe", "0Vrhe"),
    ("Sample A in 1M KOH 0Vrhe", "0Vrhe"),
    ("0.5 V vs RHE x 3 scans", "0.5 V vs RHE"),
])
def test_a_mention_still_mentions(line, literal):
    assert _pot(line) == [None]
    assert [m["literal"] for m in Q.header_potential_mentions(line)] == [literal]


@pytest.mark.parametrize("line,literal", [
    ("0.6 V x 2 cycles", "0.6 V"), ("0.5V x 3", "0.5V"), ("1.2V*2 scans", "1.2V"), ("pot 0.3 V x 1h hold", "0.3 V"),
    ("10 x 1 mV", "1 mV"), ("1V x 3 mm", "1V"), ("3 x 1v", "1v"), ("1v x 3v", "1v"), ("E = 1v x 3h", "1v"),
    ("slits 1v by 3h mm", "1v"),
    # review M1: an hour, a sign, a label, or no unit and no slit word keeps the mention
    ("-0.3 V x 2h", "-0.3 V"), ("0.5 V x 1 h", "0.5 V"), ("1.2 V x 3h;", "1.2 V"), ("chrono 0.9V x 2h", "0.9V"),
    ("CA at -0.3V x 2h", "-0.3V"), ("Ehold 0.5V x 2h", "0.5V"), ("1 V x 3 H", "1 V"), ("(1 v x 3 H)", "1 v"),
    ("3H x 1v", "1v"), ("1v×3h", "1v"), ("1V x 3H", "1V"),
    # a slit / beam / spot word in ANOTHER segment does not make a size
    ("beam on; 0.5 V x 2h", "0.5 V"), ("slit open, 0.5 V x 2 h", "0.5 V"), ("spot 2, 0.9V x 1h", "0.9V"),
])
def test_a_doubtful_product_keeps_the_mention_the_build_before_gave(line, literal):
    assert Q.dimension_spans(line) == []
    assert _pot(line) == [None]
    assert literal in [m["literal"] for m in Q.header_potential_mentions(line)]


def test_a_size_beside_a_set_point_keeps_the_mention_reads_no_value_and_says_why():
    line = "slits 1v x 3h, -0.3 V vs RHE"
    [got] = [r for r in Q.header_comment_readings(line) if r["path"] == POT]
    assert got["value"] is None and got["why"] == Q.HEADER_SIZE_WHY  # conservative: no value from a line with a size
    assert [m["literal"] for m in Q.header_potential_mentions(line)] == ["-0.3 V vs RHE"]
    said = Q.header_unread_text(POT, line, "line:9", "SYN_A.001")
    assert "beside a size it writes ('1v x 3h', whose v is an axis, not volts)" in said
    assert "beside a size" not in Q.header_unread_text(POT, "-0.3 V x 2 cycles", "line:9", "SYN_A.001")
    assert "1v x 3H mm" in B.XDC_COMMENT_RULE and B.XDC_COMMENT_RULE_ID == "ssrl_xdc_header_comment_v1"


def test_an_hour_beside_a_set_point_drops_no_mention_and_says_no_size():
    line = "-0.3V vs RHE, 0.5 V x 1 h"
    assert Q.dimension_spans(line) == []
    [got] = [r for r in Q.header_comment_readings(line) if r["path"] == POT]
    assert got["value"] is None and got["why"] == Q.HEADER_UNREAD_WHY
    assert [m["literal"] for m in Q.header_potential_mentions(line)] == ["-0.3V vs RHE", "0.5 V"]


@pytest.mark.parametrize("line", ["5 mV/s", "10 mV s-1", "PMT 900V", "eta = 300 mV", "50mV amplitude", "OCP (0.95 V)"])
def test_the_existing_rate_and_context_exclusions_stand(line):
    assert Q.header_potential_mentions(line) == []
    assert Q.dimension_spans(line) == []


# --- FIX 4: an element symbol + calib / foil is a reference -----------------------------------------------------


@pytest.mark.parametrize("name,token", [
    ("SCALIB_901", "scalib"), ("FeFOIL", "fefoil"), ("CuFoil_01", "cufoil"), ("ZZ_PtFoil_2", "ptfoil"),
    ("SYN_Sccalib", "sccalib"), ("ZnFoils", "znfoils"), ("SCalibration_1", "scalibration"), ("SYN_Nifoil3", "nifoil3"),
    ("Aucalib", "aucalib"), ("SYN_Bicalib", "bicalib"),
    # calib after ANY element symbol but No, one-letter symbols included (pinned: `calib` alone is already a reference
    # token under the prefix rule, so a symbol glued before it adds little risk)
    ("Hcalib_01", "hcalib"), ("Ocalib", "ocalib"), ("Kcalib", "kcalib"), ("Ucalib", "ucalib"),
])
def test_an_element_symbol_glued_to_calib_or_foil_is_a_reference_with_its_own_basis(name, token):
    assert G.role_from_name(name) == (G.ROLE_REFERENCE, token)
    role, basis = G.run_role({"stem": name, "source_type": "generic:ssrl_xdc_v1"})
    assert role == G.ROLE_REFERENCE
    assert (basis["rule_id"], basis["basis"], basis["token"]) == (G.ELEMENT_ROLE_RULE_ID, G.ELEMENT_ROLE_BASIS, token)


@pytest.mark.parametrize("name", [
    "Recalib_01", "SYN_recalibrated", "SCALE_01", "Scalibur_3", "SYN_sample_040", "Xfoil_1", "ZZfoil", "Hfoilage",
    "SYNcalibA", "NiFoil_1MKOH_0p5V", "CuFoil_0V", "PtFoil_pH13", "SYN_Qcalib", "SYNSAMP_040",
    # review M3: no calibration-foil element, a no-word, or a word that makes the foil something else
    "SYN_nofoil", "nocalib_01", "Nocalib", "Alfoil_filter", "Kapton_Alfoil_window", "Ptfoil_electrode", "NiFoil_KOH",
    "Infoil", "Cfoil", "Bfoil", "Nifoil_electrode_1", "Cufoil_working", "PtFoil_WE", "Cufoil_cell", "SYN_Aufoil_tape",
    "Nifoil_sample", "Aufoil_cathode", "Ptfoil_anode", "Nifoil_RE", "Cufoil_CE", "Cufoil_counter_2",
])
def test_the_element_rule_guards(name):
    assert G.role_from_name(name) is None
    assert G.name_role(name) is None


def test_the_existing_prefix_and_alignment_rules_and_their_basis_are_unchanged():
    assert G.role_from_name("foil_Cu") == (G.ROLE_REFERENCE, "foil")
    assert G.role_from_name("SYN_calibXYZ") == (G.ROLE_REFERENCE, "calibxyz")
    assert G.role_from_name("SYN_ref_1") == (G.ROLE_REFERENCE, "ref")
    assert G.role_from_name("align_SCALIB") == (G.ROLE_ALIGNMENT, "align")
    assert G.role_from_name("CuFoil_ref") == (G.ROLE_REFERENCE, "ref")
    for name in ("Cu_foil", "CuFoil_ref", "SYN_calib_2", "align_SCALIB"):
        _role, basis = G.run_role({"stem": name, "source_type": "generic:ssrl_xdc_v1", "acquisition_source_id": "src-1"})
        assert basis == {"rule_id": G.ROLE_RULE_ID, "basis": "name_token", "token": G.role_from_name(name)[1],
                         "name": name, "source_id": "src-1"}
    [g] = G.groups_from_generic_runs([{"stem": "SCALIB_901", "scans": []}], experiment_key="SYN")
    assert g["role"] == G.ROLE_REFERENCE and g["role_basis"]["rule_id"] == G.ELEMENT_ROLE_RULE_ID


# --- M2: an Athena name that fits either run of a collided pair is never linked ----------------------------------


def test_an_athena_group_named_like_a_collided_run_is_ambiguous():
    from isaac_api.local_import.processing import athena as A

    groups = [{"group_id": "rg-a", "_stems": ["SYNCAL_039"], "member_scans": [{}]},
              {"group_id": "rg-b", "_stems": ["SYNCAL_039.NNN"], "member_scans": [{}]},
              {"group_id": "rg-c", "_stems": ["SYNOTHER"], "member_scans": [{}]}]
    labels = ["SYNCAL_039.001", "SYNCAL_039_A.001", "SYNCAL_039", "SYNCAL_039.NNN", "SYNOTHER_001"]
    entries = [{"names": [A.normalise_name(lab)], "label": lab, "prj_relative_path": "SYN.prj", "data_hash": str(i)}
               for i, lab in enumerate(labels)]
    assert A.entry_groups(groups, entries) == {4: "rg-c"}
    matched, notes, _versions = A.match_with_versions(groups, entries)
    assert sorted(matched) == ["rg-c"]
    several = [n for n in notes if n["code"] == "athena_group_matches_several_record_groups"]
    assert [n["athena_label"] for n in several] == labels[:4] and all(n["group_ids"] == ["rg-a", "rg-b"] for n in several)
    # a pair kept in ONE group (the scientist merged them) is no ambiguity
    one = [{"group_id": "rg-ab", "_stems": ["SYNCAL_039", "SYNCAL_039.NNN"], "member_scans": [{}]}]
    assert A.entry_groups(one, entries[:1]) == {0: "rg-ab"}
