"""The SSRL EXAFS Data Collector 4.0 reader, on SYNTHETIC files built in ``tmp_path``.

Every value below is invented. What these pin: the header is parsed literally and nothing is
interpreted, irregularities are FLAGGED rather than raised or repaired, no time zone is ever
assigned, repeat scans group under one run, companions attach as context, symlinks are never
followed, and a near-miss signature is not a scan.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from isaac_api.local_import.readers import ssrl_xdc as x

COLUMNS = ["Real time clock", "Requested Energy", "Achieved Energy", "I0", "I1", "Spare", "Spare"]


def make_scan(
    path: Path,
    *,
    points: int = 4,
    declared_points: int | None = None,
    declared_cols: int | None = None,
    columns: list[str] | None = None,
    energies: list[float] | None = None,
    bad_cell: tuple[int, int] | None = None,
    short_row: int | None = None,
    timestamp: str = "Sun Jul 27 14:11:47 2025",
    free_text: tuple[str, ...] = ("1x1 mm beam", "synthetic sample line"),
    eol: str = "\n",
) -> Path:
    cols = columns if columns is not None else COLUMNS
    energies = energies if energies is not None else [4900.0 + 10 * i for i in range(points)]
    lines = [
        x.SIGNATURE.ljust(40),
        timestamp.ljust(40),
        f"PTS: {declared_points if declared_points is not None else points:>10} COLS: {declared_cols if declared_cols is not None else len(cols):>10}",
        "synthetic.det".ljust(40),
        "synthetic.rgn".ljust(40),
        "99 token_a  0.000 0 X 1.500000 777".ljust(60),
        "5 1000 600 RST 0 0".ljust(60),
        "gain line literal".ljust(60),
        *free_text,
        "",
        "Weights: ",
        " " + "  ".join(["1.000"] * len(cols)),
        "Offsets: ",
        " " + "  ".join(["0.000"] * len(cols)),
        "Data: ",
        *[c.ljust(18) for c in cols],
        "",
    ]
    for i in range(points):
        e = energies[i]
        cells = [f"{i}.0"] + [f"{e:.3f}", f"{e + 0.01:.3f}"] + [f"{100 + i + k}.0" for k in range(len(cols) - 3)]
        cells = cells[: len(cols)]
        if bad_cell and bad_cell[0] == i:
            cells[bad_cell[1]] = "N/A"
        if short_row == i:
            cells = cells[:-2]
        lines.append(" ".join(cells))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((eol.join(lines) + eol).encode("latin-1"))
    return path


def kinds(scan: x.XdcScan) -> set[str]:
    return {a.kind for a in scan.anomalies}


# --- sniff ----------------------------------------------------------------------------------


def test_sniff_accepts_the_exact_signature_with_either_line_ending(tmp_path):
    assert x.sniff(make_scan(tmp_path / "a_A.001"))
    assert x.sniff(make_scan(tmp_path / "b_A.001", eol="\r\n"))


@pytest.mark.parametrize(
    "first_line",
    [
        b"SSRL - EXAFS Data Collector 4.0",  # the binary variant's signature
        b"SSRL EXAFS Data Collector 4.0",  # one space
        b"ssrl   exafs data collector 4.0",  # case
        b"SSRL   EXAFS Data Collector 4.1",  # another version
        b"SSRL   EXAFS Data Collector 4.0 extra",
        b"  SSRL   EXAFS Data Collector 4.0",  # leading blanks
        b"XSSRL   EXAFS Data Collector 4.0",
        b"SSRL   EXAFS Data Collector 4",
        b"",
    ],
)
def test_sniff_rejects_near_miss_signatures(tmp_path, first_line):
    p = tmp_path / "n_A.001"
    p.write_bytes(first_line + b"\nrest\n")
    assert not x.sniff(p)
    with pytest.raises(ValueError):
        x.read(p)


def test_sniff_rejects_the_binary_variant_with_nul_bytes(tmp_path):
    p = tmp_path / "b.001"
    p.write_bytes(b"SSRL   EXAFS Data Collector 4.0\x00\x00binary rest")
    assert not x.sniff(p)


def test_sniff_on_a_missing_file_is_false_not_an_error(tmp_path):
    assert x.sniff(tmp_path / "absent") is False


# --- the header and the data ----------------------------------------------------------------


def test_the_header_is_parsed_literally_and_each_item_has_a_locator(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", points=5))
    assert scan.version == "4.0"
    assert (scan.points_declared, scan.cols_declared, scan.points_found, scan.cols_found) == (5, 7, 5, 7)
    assert scan.detector_file == "synthetic.det" and scan.region_file == "synthetic.rgn"
    by_key = {h.key: h for h in scan.header_lines}
    assert by_key["signature"].locator == "line:1" and by_key["timestamp"].locator == "line:2"
    assert by_key["header_line_6_tokens"].tokens == ["99", "token_a", "0.000", "0", "X", "1.500000", "777"]
    assert by_key["header_line_7_tokens"].tokens == ["5", "1000", "600", "RST", "0", "0"]
    assert by_key["header_line_8_literal"].literal == "gain line literal"
    assert [h.literal for h in scan.free_text_lines] == ["1x1 mm beam", "synthetic sample line"]
    assert [h.locator for h in scan.free_text_lines] == ["line:9", "line:10"]
    assert by_key["weights"].tokens == ["1.000"] * 7 and scan.weights == [1.0] * 7 and scan.offsets == [0.0] * 7
    assert by_key["column_names"].tokens == COLUMNS and scan.column_names == COLUMNS
    assert scan.anomalies == [] or kinds(scan) == {"duplicate_column_names"}


def test_nothing_in_the_header_is_given_a_meaning(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001"))
    keys = {h.key for h in scan.header_lines}
    assert "header_line_6_tokens" in keys
    for forbidden in ("edge", "mono", "monochromator", "beamline", "element", "sample", "energy_range", "unit"):
        assert not any(forbidden in k for k in keys)
        assert not any(forbidden in f for f in vars(scan))


def test_the_numeric_data_is_parsed_into_floats(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", points=3))
    assert len(scan.rows) == 3 and all(len(r) == 7 for r in scan.rows)
    assert scan.rows[1][1] == 4910.0 and all(isinstance(c, float) for c in scan.rows[0])
    assert scan.energy_check == {"column": "Requested Energy", "checked": True, "direction": "increasing", "overall_direction": "increasing", "breaks": 0}


def test_crlf_files_parse_the_same(tmp_path):
    lf = x.read(make_scan(tmp_path / "a_A.001"))
    crlf = x.read(make_scan(tmp_path / "b_A.001", eol="\r\n"))
    assert lf.rows == crlf.rows and lf.column_names == crlf.column_names and lf.free_text_lines[0].literal == crlf.free_text_lines[0].literal


# --- timestamp and timezone -----------------------------------------------------------------


def test_the_timestamp_is_naive_and_the_zone_is_never_assigned(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001"))
    assert scan.timestamp_literal == "Sun Jul 27 14:11:47 2025"
    assert scan.timestamp_parsed == datetime(2025, 7, 27, 14, 11, 47)
    assert scan.timestamp_parsed.tzinfo is None
    assert scan.timezone == "not_stated"
    [run] = _collect_one(tmp_path)
    assert run.scans[0]["timezone"] == "not_stated" and "+" not in run.scans[0]["timestamp_naive"] and "Z" not in run.scans[0]["timestamp_naive"]


def test_an_unparseable_timestamp_is_flagged_and_kept_verbatim(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", timestamp="sometime last week"))
    assert scan.timestamp_parsed is None and scan.timestamp_literal == "sometime last week"
    assert "timestamp_unparsed" in kinds(scan)


def test_a_weekday_that_does_not_match_the_date_is_flagged(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", timestamp="Mon Jul 27 14:11:47 2025"))  # 27 Jul 2025 is a Sunday
    assert "timestamp_weekday_mismatch" in kinds(scan)


# --- anomalies are flagged, never raised or repaired ----------------------------------------


def test_a_points_mismatch_is_flagged_with_both_numbers(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", points=4, declared_points=9))
    [flag] = [a for a in scan.anomalies if a.kind == "points_mismatch"]
    assert "9" in flag.detail and "4" in flag.detail and flag.locator == "line:3"
    assert scan.points_found == 4  # not repaired to the declared number


def test_a_columns_mismatch_is_flagged(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", declared_cols=9))
    assert "columns_mismatch" in kinds(scan)


def test_a_non_numeric_cell_is_flagged_not_a_crash(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", points=4, bad_cell=(2, 3)))
    [flag] = [a for a in scan.anomalies if a.kind == "non_numeric_cell"]
    assert flag.locator.startswith("line:") and "column 4" in flag.detail
    assert scan.rows[2][3] is None and scan.rows[2][1] == 4920.0  # the rest of the row survives


def test_a_short_row_is_flagged(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", points=4, short_row=1))
    assert "row_column_count_mismatch" in kinds(scan)


def test_a_non_monotonic_energy_grid_is_flagged(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", points=5, energies=[4900, 4910, 4905, 4920, 4930]))
    assert "energy_not_monotonic" in kinds(scan)
    assert scan.energy_check["direction"] == "not_monotonic" and scan.energy_check["breaks"] == 1
    assert scan.rows[2][1] == 4905.0  # the data is left exactly as it was


def test_a_descending_grid_that_stays_descending_is_fine(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", points=4, energies=[5000, 4990, 4980, 4970]))
    assert "energy_not_monotonic" not in kinds(scan) and scan.energy_check["direction"] == "decreasing"


def test_no_energy_column_means_not_checked_not_failed(tmp_path):
    scan = x.read(make_scan(tmp_path / "s_A.001", columns=["Real time clock", "I0", "I1"]))
    assert scan.energy_check["checked"] is False and "energy_not_monotonic" not in kinds(scan)


def test_a_truncated_header_is_flagged_and_does_not_raise(tmp_path):
    p = tmp_path / "t_A.001"
    p.write_bytes((x.SIGNATURE + "\nSun Jul 27 14:11:47 2025\nPTS: 3 COLS: 2\n").encode())
    scan = x.read(p)
    assert "header_incomplete" in kinds(scan) and "no_data" in kinds(scan)
    assert scan.points_found == 0


def test_an_oversize_file_is_refused_by_the_bound(tmp_path):
    p = make_scan(tmp_path / "s_A.001")
    with pytest.raises(ValueError, match="bound"):
        x.read(p, max_bytes=100)


# --- collecting runs ------------------------------------------------------------------------


def _collect_one(tmp_path: Path) -> list[x.GenericRun]:
    root = tmp_path / "root"
    make_scan(root / "run_one_A.001")
    return x.collect_generic_runs(root)


def test_repeat_scans_group_into_one_run_in_scan_order(tmp_path):
    root = tmp_path / "root"
    for i in (3, 1, 2):
        make_scan(root / f"sample_a_A.{i:03d}", points=3 + i)
    [run] = x.collect_generic_runs(root)
    assert run.label == "sample_a" and run.profile == "ssrl_xdc_v1" and run.directory == ""
    assert [s["scan_index"] for s in run.scans] == [1, 2, 3] == run.scan_indices
    assert [s["points"] for s in run.scans] == [4, 5, 6]
    assert run.scans[0]["relative_path"] == "sample_a_A.001"
    assert run.scans[0]["sha256"] == hashlib.sha256((root / "sample_a_A.001").read_bytes()).hexdigest()
    assert run.scans[0]["columns"] == COLUMNS and run.run_key == "ssrl_xdc_v1:sample_a"


def test_every_header_item_becomes_a_statement_with_a_locator_and_a_source(tmp_path):
    root = tmp_path / "root"
    make_scan(root / "n_A.001")
    make_scan(root / "n_A.002")
    [run] = x.collect_generic_runs(root)
    first = [s for s in run.statements if s["source_relative_path"] == "n_A.001"]
    keys = [s["key"] for s in first]
    for needed in ("signature", "timestamp", "points_cols", "detector_file", "region_file", "header_line_6_tokens", "header_line_7_tokens", "header_line_8_literal", "free_text", "weights", "offsets", "column_names"):
        assert needed in keys, needed
    assert all(s["locator"].startswith("line:") and s["literal"] is not None for s in run.statements)
    assert {s["scan_index"] for s in run.statements} == {1, 2}
    assert run.header_differences == []  # two identical headers (the timestamp is excluded as expected to differ)


def test_a_header_that_differs_between_repeat_scans_is_reported_by_key(tmp_path):
    root = tmp_path / "root"
    make_scan(root / "n_A.001", free_text=("beam one",))
    make_scan(root / "n_A.002", free_text=("beam one",))
    # change the detector line of the second only
    p = root / "n_A.002"
    p.write_bytes(p.read_bytes().replace(b"synthetic.det", b"another.det!"))
    [run] = x.collect_generic_runs(root)
    assert run.header_differences == ["detector_file"]


def test_same_name_in_two_folders_makes_two_runs_with_distinct_keys(tmp_path):
    root = tmp_path / "root"
    make_scan(root / "one" / "same_A.001")
    make_scan(root / "two" / "same_A.001")
    runs = x.collect_generic_runs(root)
    assert len(runs) == 2 and len({r.run_key for r in runs}) == 2
    assert {r.run_key for r in runs} == {"ssrl_xdc_v1:one/same", "ssrl_xdc_v1:two/same"}


def test_companions_attach_from_the_same_stem_the_same_named_folder_and_the_binary_folder(tmp_path):
    root = tmp_path / "root"
    make_scan(root / "run7_A.001")
    (root / "run7").mkdir()
    (root / "run7" / "region.rgn").write_text("r")
    (root / "run7" / "det.det").write_text("d")
    (root / "run7" / "exp.exp").write_text("e")
    (root / "run7" / "SYN_context.txt").write_text("p")
    (root / "run7.exp").write_text("sibling")
    (root / "binary").mkdir()
    (root / "binary" / "run7.001").write_bytes(b"SSRL - EXAFS Data Collector 4.0\x00bin")
    (root / "binary" / "other.001").write_bytes(b"x")
    make_scan(root / "other_A.001")
    runs = {r.label: r for r in x.collect_generic_runs(root)}
    roles = {c["relative_path"]: c["role"] for c in runs["run7"].companions}
    assert roles == {
        "run7/region.rgn": "region",
        "run7/det.det": "detector",
        "run7/exp.exp": "experiment",
        "run7/SYN_context.txt": "other_context",
        "run7.exp": "experiment",
        "binary/run7.001": "binary_original",
    }
    assert all(c["parsed"] is False and len(c["sha256"]) == 64 for c in runs["run7"].companions)
    assert [c["relative_path"] for c in runs["other"].companions] == ["binary/other.001"]


def test_a_symlinked_file_and_a_symlinked_folder_are_never_followed(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    make_scan(outside / "hidden_A.001")
    root.mkdir()
    make_scan(root / "real_A.001")
    (root / "link_A.001").symlink_to(outside / "hidden_A.001")
    (root / "linkdir").symlink_to(outside, target_is_directory=True)
    result = x.collect_generic(root)
    assert [r.label for r in result.runs] == ["real"]
    reasons = {(f["relative_path"], f["reason"]) for f in result.refused}
    assert ("link_A.001", "symlink_not_followed") in reasons and ("linkdir", "symlink_not_followed") in reasons


def test_a_symlinked_root_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError):
        x.collect_generic(link)


def test_a_numbered_file_with_the_wrong_signature_is_listed_as_unparsed_not_dropped(tmp_path):
    root = tmp_path / "root"
    make_scan(root / "good_A.001")
    (root / "bad_A.001").write_bytes(b"SSRL - EXAFS Data Collector 4.0\x00not text")
    (root / "near_A.001").write_text("SSRL EXAFS Data Collector 4.0\n")
    result = x.collect_generic(root)
    assert [r.label for r in result.runs] == ["good"]
    assert {(u["relative_path"], u["reason_code"]) for u in result.unparsed} == {
        ("bad_A.001", "signature_not_recognised"),
        ("near_A.001", "signature_not_recognised"),
    }


def test_a_scan_over_the_size_bound_is_unparsed_with_its_size(tmp_path):
    root = tmp_path / "root"
    make_scan(root / "big_A.001")
    result = x.collect_generic(root, x.Limits(max_scan_bytes=100))
    assert result.runs == [] and result.unparsed[0]["reason_code"] == "file_too_large" and result.unparsed[0]["size_bytes"] > 100


def test_the_entry_ceiling_counts_what_it_did_not_consider(tmp_path):
    from isaac_api.bl15.inventory import ArchiveLimits

    root = tmp_path / "root"
    for i in range(6):
        make_scan(root / f"r{i}_A.001")
    result = x.collect_generic(root, x.Limits(archive=ArchiveLimits(max_entries=4)))
    assert result.files_seen == 4 and result.truncation["files_not_considered"] == 2 and len(result.runs) == 4


def test_a_gap_in_the_scan_numbers_is_noted(tmp_path):
    root = tmp_path / "root"
    make_scan(root / "g_A.001")
    make_scan(root / "g_A.003")
    [run] = x.collect_generic_runs(root)
    gap = [a for a in run.anomalies if a["kind"] == "scan_index_gap"]
    assert len(gap) == 1 and "[2]" in gap[0]["detail"] and gap[0]["severity"] == "note"


def test_anomalies_carry_their_source_file_and_scan(tmp_path):
    root = tmp_path / "root"
    make_scan(root / "a_A.001")
    make_scan(root / "a_A.002", declared_points=99)
    [run] = x.collect_generic_runs(root)
    flagged = [a for a in run.anomalies if a["kind"] == "points_mismatch"]
    assert [(a["source_relative_path"], a["scan_index"]) for a in flagged] == [("a_A.002", 2)]


def test_the_collector_writes_nothing(tmp_path):
    root = tmp_path / "root"
    make_scan(root / "w_A.001")
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    x.collect_generic_runs(root)
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before


def test_the_reader_imports_no_network_web_or_process_module():
    source = Path(x.__file__).read_text(encoding="utf-8")
    for needle in ("import requests", "import httpx", "urllib", "socket", "fastapi", "subprocess", "os.system", "eval(", "exec("):
        assert needle not in source, needle
