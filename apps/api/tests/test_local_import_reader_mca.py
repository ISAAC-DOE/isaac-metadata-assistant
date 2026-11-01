"""The PyMca ``.mca`` reader, on SYNTHETIC files only."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from isaac_api.local_import.readers import mca
from isaac_api.local_import.readers._common import walk
from isaac_api.bl15.inventory import ArchiveLimits


def make_mca(path: Path, *, channels: int = 12, values: int | None = None, per_line: int = 5, second_block: bool = False, eol: str = "\n") -> Path:
    n = channels if values is None else values
    vals = [f"{0.1 * (i + 1):.4g}" for i in range(n)]
    chunks = [vals[i : i + per_line] for i in range(0, n, per_line)] or [[]]
    lines = ["#F /synthetic/dir/file_name", "#D Thu Jan  1 00:00:00 2099", "", "#S 1 (synthetic title 2.1 DTC)", "#D Thu Jan  1 00:00:00 2099", "#@MCA %16C", f"#@CHANN {channels} 100 {99 + channels} 1", "#@CALIB 0 1 0"]
    for k, chunk in enumerate(chunks):
        prefix = "@A " if k == 0 else ""
        tail = " \\" if k < len(chunks) - 1 else " "
        lines.append(prefix + " ".join(chunk) + tail)
    lines += ["", ""]
    if second_block:
        lines += ["#S 2 (another)", "#@MCA %16C", "@A 1 2 3"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(eol.join(lines).encode("ascii"))
    return path


def kinds(f: mca.McaFile) -> set[str]:
    return {a.kind for a in f.anomalies}


def _files(root: Path):
    return walk(root, ArchiveLimits(), [], {})


def test_sniff_accepts_a_real_shaped_file(tmp_path):
    assert mca.sniff(make_mca(tmp_path / "a.mca"))
    assert mca.sniff(make_mca(tmp_path / "b.MCA", eol="\r\n"))


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("a.txt", "#F x\n#@MCA %16C\n@A 1 2\n"),  # wrong extension
        ("b.mca", "#F x\n#@CHANN 2 1 2 1\n@A 1 2\n"),  # no #@MCA
        ("c.mca", "#F x\n#@MCA %16C\n#@CHANN 2 1 2 1\n"),  # no @A
        ("d.mca", "F x\n#@MCA %16C\n@A 1 2\n"),  # first line not '#F '
        ("e.mca", "#Fx\n#@MCA %16C\n@A 1 2\n"),
        ("f.mca", ""),
    ],
)
def test_sniff_rejects_near_misses(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    assert not mca.sniff(p)
    with pytest.raises(ValueError):
        mca.read(p)


def test_a_spec_acquisition_with_a_dat_extension_is_not_claimed(tmp_path):
    p = tmp_path / "scan.dat"
    p.write_text("#F x\n#@MCA %16C\n@A 1 2\n")
    assert not mca.sniff(p)


def test_header_lines_are_literal_statements(tmp_path):
    f = mca.read(make_mca(tmp_path / "a.mca"))
    by = {h.key: h for h in f.header_lines}
    assert by["mca_file_path"].literal == "/synthetic/dir/file_name" and by["mca_file_path"].locator == "line:1"
    assert by["scan_title"].literal.startswith("S 1 (synthetic title")
    assert by["channels"].tokens == ["12", "100", "111", "1"] and by["calibration"].tokens == ["0", "1", "0"]
    assert [h.key for h in f.header_lines].count("date") == 2


def test_the_array_is_read_across_continuation_lines(tmp_path):
    f = mca.read(make_mca(tmp_path / "a.mca", channels=12, per_line=5))
    assert len(f.counts) == 12 and f.channels_declared == 12 and f.anomalies == []
    assert f.counts[0] == pytest.approx(0.1) and f.counts[11] == pytest.approx(1.2)
    assert f.calibration == [0.0, 1.0, 0.0] and f.channel_range == [100.0, 111.0, 1.0]


def test_a_channel_count_mismatch_is_flagged_not_repaired(tmp_path):
    f = mca.read(make_mca(tmp_path / "a.mca", channels=12, values=9))
    assert "channel_count_mismatch" in kinds(f) and len(f.counts) == 9


def test_a_second_block_is_flagged_as_not_read(tmp_path):
    f = mca.read(make_mca(tmp_path / "a.mca", second_block=True))
    assert "additional_block_not_read" in kinds(f) and len(f.counts) == 12


def test_a_non_numeric_value_is_flagged(tmp_path):
    p = make_mca(tmp_path / "a.mca", channels=5, per_line=5)
    p.write_text(p.read_text().replace("0.2", "oops", 1))
    f = mca.read(p)
    assert "non_numeric_cell" in kinds(f) and f.counts[1] is None


def test_the_reader_does_not_give_the_spectrum_a_meaning(tmp_path):
    f = mca.read(make_mca(tmp_path / "a.mca"))
    assert not any(k in vars(f) for k in ("element", "energy", "unit", "sample", "technique"))


def test_collect_makes_one_run_per_file_with_path_and_hash(tmp_path):
    root = tmp_path / "root"
    make_mca(root / "d" / "one.mca")
    make_mca(root / "d" / "two.mca")
    (root / "d" / "notes.txt").write_text("x")
    result = mca.collect_from_files(_files(root))
    assert [r.run_key for r in result.runs] == ["mca_v1:d/one", "mca_v1:d/two"]
    scan = result.runs[0].scans[0]
    assert scan["relative_path"] == "d/one.mca" and scan["points"] == 12 and scan["channels_declared"] == 12
    assert scan["sha256"] == hashlib.sha256((root / "d/one.mca").read_bytes()).hexdigest()
    assert result.consumed == [("d/one.mca", "scan"), ("d/two.mca", "scan")]


def test_oversize_file_is_refused_by_the_bound(tmp_path):
    with pytest.raises(ValueError, match="bound"):
        mca.read(make_mca(tmp_path / "a.mca"), max_bytes=20)
    result = mca.collect_from_files(_files(tmp_path), Limits_small())
    assert result.unparsed and result.unparsed[0]["reason_code"] == "file_too_large"


def Limits_small():
    from isaac_api.local_import.readers._common import Limits

    return Limits(max_scan_bytes=20)
