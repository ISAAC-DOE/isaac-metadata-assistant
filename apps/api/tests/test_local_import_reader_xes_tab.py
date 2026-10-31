"""The tab-separated ``xes<N>`` reader, on SYNTHETIC files only (bare-CR line breaks included)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from isaac_api.local_import.readers import xes_tab


def make_xes(path: Path, *, header: str = "xes0\txes2\txes9", rows: tuple[str, ...] = ("100.5\t39318\t8", "101.5\t39257\t6", "102.5\t39237\t7"), eol: str = "\r") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((eol.join([header, *rows]) + eol).encode("ascii"))
    return path


@pytest.mark.parametrize("eol", ["\r", "\r\n", "\n"])
def test_all_three_line_breaks_parse_identically(tmp_path, eol):
    scan = xes_tab.read(make_xes(tmp_path / "a_1.txt", eol=eol))
    assert scan.header_names == ["xes0", "xes2", "xes9"] and scan.rows[1] == [101.5, 39257.0, 6.0] and scan.anomalies == []


@pytest.mark.parametrize(
    "header",
    ["xes0\txes2", "xes0\txes2\txes9\textra", "xes\txes2", "XES0\txes2", "xes0 xes2 xes9", "xes0,xes2,xes9", "xes0\t\txes2", "time\tcounts", "xes0"],
)
def test_sniff_rejects_near_miss_headers(tmp_path, header):
    p = make_xes(tmp_path / "n_1.txt", header=header, rows=("1\t2\t3",))
    if header in ("xes0\txes2",):
        assert xes_tab.sniff(p)  # two names is the minimum a real header can have here
        return
    assert not xes_tab.sniff(p)
    with pytest.raises(ValueError):
        xes_tab.read(p)


def test_sniff_rejects_binary_and_missing(tmp_path):
    p = tmp_path / "b.txt"
    p.write_bytes(b"xes0\txes2\x00\x00")
    assert not xes_tab.sniff(p) and not xes_tab.sniff(tmp_path / "absent")


def test_the_header_is_a_literal_statement_and_no_technique_is_assigned(tmp_path):
    scan = xes_tab.read(make_xes(tmp_path / "a_1.txt"))
    assert scan.header_line.key == "xes_header" and scan.header_line.locator == "line:1"
    assert scan.header_line.literal == "xes0\txes2\txes9" and scan.header_line.tokens == ["xes0", "xes2", "xes9"]
    root = tmp_path / "root"
    make_xes(root / "a_1.txt")
    [run] = xes_tab.collect_from_files(_files(root)).runs
    assert run.role_hints["technique"] is None
    assert not any(k in vars(scan) for k in ("technique", "energy", "unit", "detector"))


def test_a_wrong_width_row_and_a_non_numeric_cell_are_flagged(tmp_path):
    scan = xes_tab.read(make_xes(tmp_path / "a_1.txt", rows=("1\t2\t3", "4\t5", "6\tX\t8")))
    assert {"row_width_mismatch", "non_numeric_cell"} <= {a.kind for a in scan.anomalies}
    assert scan.rows[2] == [6.0, None, 8.0]


def test_a_header_only_file_is_flagged_no_data(tmp_path):
    scan = xes_tab.read(make_xes(tmp_path / "a_1.txt", rows=()))
    assert [a.kind for a in scan.anomalies] == ["no_data"]


def test_oversize_file_is_refused_by_the_bound(tmp_path):
    with pytest.raises(ValueError, match="bound"):
        xes_tab.read(make_xes(tmp_path / "a_1.txt"), max_bytes=10)


def _files(root: Path):
    from isaac_api.local_import.readers._common import walk
    from isaac_api.bl15.inventory import ArchiveLimits

    return walk(root, ArchiveLimits(), [], {})


def test_repeat_files_group_into_one_run_by_directory_and_name(tmp_path):
    root = tmp_path / "root"
    for i in (1, 3, 2):
        make_xes(root / "d" / f"sample_run_{i}.txt")
    make_xes(root / "d" / "other_run_1.txt")
    make_xes(root / "e" / "sample_run_1.txt")
    result = xes_tab.collect_from_files(_files(root))
    keys = {r.run_key: r for r in result.runs}
    assert set(keys) == {"xes_tab_v1:d/sample_run", "xes_tab_v1:d/other_run", "xes_tab_v1:e/sample_run"}
    assert [s["scan_index"] for s in keys["xes_tab_v1:d/sample_run"].scans] == [1, 2, 3]
    assert keys["xes_tab_v1:d/sample_run"].scans[0]["sha256"] == hashlib.sha256((root / "d/sample_run_1.txt").read_bytes()).hexdigest()
    assert len(result.consumed) == 5 and all(role == "scan" for _, role in result.consumed)


def test_a_same_name_file_is_attached_by_name_only_and_not_consumed(tmp_path):
    root = tmp_path / "root"
    make_xes(root / "d" / "run7_1.txt")
    (root / "d" / "run7").write_text("#F something\n")
    [run] = xes_tab.collect_from_files(_files(root)).runs
    assert [(c["relative_path"], c["role"], c["parsed"]) for c in run.companions] == [("d/run7", "same_name_file", False)]
    consumed = xes_tab.collect_from_files(_files(root)).consumed
    assert ("d/run7", "same_name_file") not in consumed


def test_an_xes_header_on_a_file_not_named_with_an_index_is_its_own_run(tmp_path):
    root = tmp_path / "root"
    make_xes(root / "odd name.txt")
    [run] = xes_tab.collect_from_files(_files(root)).runs
    assert run.label == "odd name" and run.scan_indices == [0]


def test_a_plain_txt_without_the_header_is_not_collected(tmp_path):
    root = tmp_path / "root"
    (root / "a_1.txt").parent.mkdir()
    (root / "a_1.txt").write_text("hello\tworld\n1\t2\n")
    assert xes_tab.collect_from_files(_files(root)).runs == []


def test_scan_header_differences_are_reported(tmp_path):
    root = tmp_path / "root"
    make_xes(root / "r_1.txt")
    make_xes(root / "r_2.txt", header="xes0\txes3\txes9")
    [run] = xes_tab.collect_from_files(_files(root)).runs
    assert run.header_differences == ["xes_header"]
