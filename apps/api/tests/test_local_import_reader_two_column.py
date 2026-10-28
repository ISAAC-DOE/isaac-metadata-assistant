"""The headerless two-column numeric reader, on SYNTHETIC files only."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from isaac_api.bl15.inventory import ArchiveLimits
from isaac_api.local_import.readers import two_column
from isaac_api.local_import.readers._common import Limits, walk


def make_two(path: Path, lines: tuple[str, ...] = ("100.5  2.5e-05", "101.5  3.5e-05", "102.5  1e-05"), eol: str = "\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((eol.join(lines) + eol).encode("ascii"))
    return path


def _files(root: Path):
    return walk(root, ArchiveLimits(), [], {})


@pytest.mark.parametrize("eol", ["\n", "\r\n", "\r"])
def test_sniff_and_read_accept_the_real_shape_with_any_line_break(tmp_path, eol):
    p = make_two(tmp_path / "a.txt", eol=eol)
    assert two_column.sniff(p)
    data = two_column.read(p)
    assert data.rows == [[100.5, 2.5e-05], [101.5, 3.5e-05], [102.5, 1e-05]]


@pytest.mark.parametrize(
    "lines",
    [
        ("energy  value", "1 2", "3 4"),  # a header
        ("1 2 3", "4 5 6"),  # three columns
        ("1", "2"),  # one column
        ("1 2", "3 x"),  # a non-number
        ("1 2",),  # a single line is not enough to call it a table
        ("# comment", "1 2", "3 4"),
        ("1,2", "3,4"),
    ],
)
def test_sniff_rejects_near_misses(tmp_path, lines):
    p = make_two(tmp_path / "n.txt", lines)
    assert not two_column.sniff(p)
    with pytest.raises(ValueError):
        two_column.read(p)


def test_sniff_requires_a_txt_extension_and_rejects_binary(tmp_path):
    assert not two_column.sniff(make_two(tmp_path / "a.dat"))
    b = tmp_path / "b.txt"
    b.write_bytes(b"1 2\n3 4\x00\n")
    assert not two_column.sniff(b) and not two_column.sniff(tmp_path / "absent.txt")


def test_the_file_is_flagged_no_header_and_columns_are_positions_not_names(tmp_path):
    root = tmp_path / "root"
    make_two(root / "d" / "sample.txt")
    data = two_column.read(root / "d" / "sample.txt")
    assert [(a.kind, a.severity) for a in data.anomalies] == [("no_header", "note")]
    [run] = two_column.collect_from_files(_files(root)).runs
    assert run.scans[0]["columns"] == ["column_1", "column_2"] and run.statements == []
    assert any(a["kind"] == "no_header" for a in run.anomalies)
    assert run.role_hints["no_header"] is True


def test_nothing_is_called_an_energy_or_an_intensity(tmp_path):
    root = tmp_path / "root"
    make_two(root / "s.txt")
    [run] = two_column.collect_from_files(_files(root)).runs
    text = repr(run.__dict__).lower()
    for word in ("energy", "intensity", "absorption", "mu"):
        assert word not in text.replace("column", "")


def test_one_run_per_file_with_collision_free_keys(tmp_path):
    root = tmp_path / "root"
    make_two(root / "one" / "same.txt")
    make_two(root / "two" / "same.txt")
    keys = [r.run_key for r in two_column.collect_from_files(_files(root)).runs]
    assert keys == ["two_column_v1:one/same", "two_column_v1:two/same"]


def test_path_hash_and_point_count_are_recorded(tmp_path):
    root = tmp_path / "root"
    make_two(root / "a.txt")
    [run] = two_column.collect_from_files(_files(root)).runs
    scan = run.scans[0]
    assert scan["relative_path"] == "a.txt" and scan["points"] == 3
    assert scan["sha256"] == hashlib.sha256((root / "a.txt").read_bytes()).hexdigest()


def test_oversize_file_is_unparsed_with_its_size(tmp_path):
    root = tmp_path / "root"
    make_two(root / "a.txt")
    result = two_column.collect_from_files(_files(root), Limits(max_scan_bytes=5))
    assert result.runs == [] and result.unparsed[0]["reason_code"] == "file_too_large"
    with pytest.raises(ValueError, match="bound"):
        two_column.read(root / "a.txt", max_bytes=5)


def test_a_late_bad_line_beyond_the_sniffed_head_is_flagged_when_read(tmp_path):
    long_lines = tuple(f"{i}.5 {i}.25" for i in range(1, 600))
    q = make_two(tmp_path / "b.txt", long_lines)
    assert two_column.sniff(q)
    q.write_bytes(q.read_bytes() + b"9 8 7\nabc def\n")
    assert two_column.sniff(q)  # the 4 KiB head still looks like a table; the bad lines are further on
    data = two_column.read(q)
    assert {"row_width_mismatch", "non_numeric_cell"} <= {a.kind for a in data.anomalies}
    assert data.rows[-1][0] is None
