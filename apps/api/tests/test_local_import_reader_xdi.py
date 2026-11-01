"""The XDI/1.0 reader (Athena / Demeter processed outputs), on SYNTHETIC files only."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from isaac_api.local_import.readers import xdi


def make_xdi(
    path: Path,
    *,
    first_line: str = "# XDI/1.0 Athena/0.9.24",
    fields: tuple[str, ...] = ("Element.edge: K", "Element.symbol: Zz", "Column.1: energy eV", "Column.2: norm", "Athena.e0: 1234.5"),
    comments: tuple[str, ...] | None = ("A synthetic fit comment.", "Second comment line."),
    column_header: str | None = "#   e         norm",
    rows: tuple[str, ...] = ("  100.0   0.1", "  101.0   0.2", "  102.0   0.3"),
    separator: bool = True,
    eol: str = "\r\n",
) -> Path:
    lines = [first_line, *[f"# {f}" for f in fields]]
    if comments is not None:
        lines.append("# ///")
        lines.extend(f"# {c}" for c in comments)
    if separator:
        lines.append("#------------------------")
    if column_header is not None:
        lines.append(column_header)
    lines.extend(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((eol.join(lines) + eol).encode("latin-1"))
    return path


def kinds(f: xdi.XdiFile) -> set[str]:
    return {a.kind for a in f.anomalies}


# --- sniff ----------------------------------------------------------------------------------


@pytest.mark.parametrize("first", ["# XDI/1.0 Athena/0.9.24", "# XDI/1.0 Demeter/0.9.26", "# XDI/1.0", "#\tXDI/1.0\tAthena/0.9.26"])
def test_sniff_accepts_the_real_first_line_shapes(tmp_path, first):
    assert xdi.sniff(make_xdi(tmp_path / "a.nor", first_line=first))


@pytest.mark.parametrize(
    "first",
    ["XDI/1.0 Athena/0.9", "# xdi/1.0 Athena/0.9", "# XDI/1 Athena", "# XDI/1.0x", "#XDI/1.0", "## XDI/1.0 A", "# Not XDI/1.0", "# XDI/ 1.0", ""],
)
def test_sniff_rejects_near_miss_first_lines(tmp_path, first):
    p = tmp_path / "n.nor"
    p.write_bytes((first + "\nrest\n").encode())
    assert not xdi.sniff(p)
    with pytest.raises(ValueError):
        xdi.read(p)


def test_sniff_rejects_binary_and_missing_files(tmp_path):
    p = tmp_path / "b.nor"
    p.write_bytes(b"# XDI/1.0 Athena/0.9\x00\x00")
    assert not xdi.sniff(p) and not xdi.sniff(tmp_path / "absent")


# --- parse ----------------------------------------------------------------------------------


def test_fields_are_literal_statements_with_locators(tmp_path):
    f = xdi.read(make_xdi(tmp_path / "a.nor"))
    assert f.version == "1.0" and f.application_literal == "Athena/0.9.24"
    by = {(x.namespace, x.key): x for x in f.fields}
    assert by[("Element", "edge")].value == "K" and by[("Element", "edge")].locator == "line:2"
    assert by[("Athena", "e0")].value == "1234.5"
    keys = {h.key for h in f.header_lines}
    assert {"xdi_version", "Element.edge", "Athena.e0", "comment", "column_names"} <= keys
    assert f.declared_columns == {1: "energy eV", 2: "norm"}


def test_comment_block_columns_and_rows(tmp_path):
    f = xdi.read(make_xdi(tmp_path / "a.nor"))
    assert [c.literal for c in f.comment_lines] == ["A synthetic fit comment.", "Second comment line."]
    assert f.column_names == ["e", "norm"] and f.column_header.locator.startswith("line:")
    assert f.rows == [[100.0, 0.1], [101.0, 0.2], [102.0, 0.3]]
    assert f.anomalies == []


def test_fortran_exponents_parse_and_crlf_lf_and_cr_agree(tmp_path):
    rows = ("  11540.122   0.67503164E-03  -0.94148088E-03",)
    a = xdi.read(make_xdi(tmp_path / "a.nor", rows=rows, column_header="# e a b", fields=("Column.1: e", "Column.2: a", "Column.3: b")))
    b = xdi.read(make_xdi(tmp_path / "b.nor", rows=rows, column_header="# e a b", fields=("Column.1: e", "Column.2: a", "Column.3: b"), eol="\n"))
    c = xdi.read(make_xdi(tmp_path / "c.nor", rows=rows, column_header="# e a b", fields=("Column.1: e", "Column.2: a", "Column.3: b"), eol="\r"))
    assert a.rows == b.rows == c.rows == [[11540.122, 0.00067503164, -0.00094148088]]


def test_role_hints_state_only_what_the_file_says(tmp_path):
    f = xdi.read(make_xdi(tmp_path / "x.xmu", first_line="# XDI/1.0 Demeter/0.9.24", fields=("Demeter.output_filetype: multicolumn mu(E)", "Column.1: k")))
    assert f.role_hints == {
        "processed_by": "Demeter",
        "application_version": "0.9.24",
        "demeter_output_filetype": "multicolumn mu(E)",
        "has_athena_fields": False,
        "extension": ".xmu",
    }
    bare = xdi.read(make_xdi(tmp_path / "y.xmu", first_line="# XDI/1.0", fields=()))
    assert bare.role_hints["processed_by"] is None and bare.role_hints["demeter_output_filetype"] is None


def test_nothing_about_normalisation_is_concluded_from_a_name_or_extension(tmp_path):
    f = xdi.read(make_xdi(tmp_path / "x.nor", column_header="# e norm flat"))
    assert not any("normal" in str(v).lower() for v in f.role_hints.values() if v is not None)
    assert not any("normal" in k or "state" in k for k in f.role_hints)


# --- anomalies ------------------------------------------------------------------------------


def test_a_column_count_mismatch_is_flagged_not_repaired(tmp_path):
    f = xdi.read(make_xdi(tmp_path / "a.nor", column_header="# e norm extra"))
    assert "column_count_mismatch" in kinds(f) and f.column_names == ["e", "norm", "extra"]


def test_declared_columns_that_disagree_with_the_rows_are_flagged(tmp_path):
    f = xdi.read(make_xdi(tmp_path / "a.nor", fields=("Column.1: k", "Column.2: energy", "Column.4: name")))
    assert "declared_columns_differ" in kinds(f) and "declared_column_numbers_not_contiguous" in kinds(f)


def test_a_non_numeric_cell_and_a_ragged_row_are_flagged(tmp_path):
    f = xdi.read(make_xdi(tmp_path / "a.nor", rows=("1 2", "3 N/A", "5 6 7")))
    assert {"non_numeric_cell", "row_width_varies"} <= kinds(f)
    assert f.rows[1] == [3.0, None]


def test_a_missing_separator_or_data_is_flagged_and_does_not_raise(tmp_path):
    assert "no_separator" in kinds(xdi.read(make_xdi(tmp_path / "a.nor", separator=False, column_header=None)))
    assert "no_data" in kinds(xdi.read(make_xdi(tmp_path / "b.nor", rows=())))
    assert "no_column_header" in kinds(xdi.read(make_xdi(tmp_path / "c.nor", column_header=None)))


def test_a_comment_inside_the_data_is_not_read_as_data(tmp_path):
    f = xdi.read(make_xdi(tmp_path / "a.nor", rows=("1 2", "# stray", "3 4")))
    assert f.rows == [[1.0, 2.0], [3.0, 4.0]] and "comment_inside_data" in kinds(f)


def test_a_duplicate_column_declaration_is_flagged(tmp_path):
    f = xdi.read(make_xdi(tmp_path / "a.nor", fields=("Column.1: e", "Column.1: again", "Column.2: n")))
    assert "duplicate_column_declaration" in kinds(f)


def test_oversize_file_is_refused_by_the_bound(tmp_path):
    with pytest.raises(ValueError, match="bound"):
        xdi.read(make_xdi(tmp_path / "a.nor"), max_bytes=20)


# --- collecting -----------------------------------------------------------------------------


def test_collect_groups_by_directory_and_stem_with_paths_and_hashes(tmp_path):
    root = tmp_path / "root"
    for ext in (".nor", ".peak", ".nder"):
        make_xdi(root / "d" / f"sample_one{ext}")
    make_xdi(root / "d" / "sample_two.xmu", first_line="# XDI/1.0 Demeter/0.9.24")
    make_xdi(root / "other" / "sample_one.nor")
    runs = {r.run_key: r for r in xdi.collect_processed_outputs(root)}
    assert set(runs) == {"xdi_v1:d/sample_one", "xdi_v1:d/sample_two", "xdi_v1:other/sample_one"}
    one = runs["xdi_v1:d/sample_one"]
    assert sorted(s["extension"] for s in one.scans) == [".nder", ".nor", ".peak"]
    assert one.scans[0]["sha256"] == hashlib.sha256((root / one.scans[0]["relative_path"]).read_bytes()).hexdigest()
    assert one.profile == "xdi_v1" and one.role_hints["processed_by"] == ["Athena"] and one.role_hints["extensions"] == [".nder", ".nor", ".peak"]
    assert runs["xdi_v1:d/sample_two"].role_hints["processed_by"] == ["Demeter"]


def test_collect_ignores_non_xdi_files_and_never_follows_symlinks(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    make_xdi(outside / "hidden.nor")
    make_xdi(root / "real.nor")
    (root / "plain.nor").write_text("# not xdi\n1 2\n")
    (root / "link.nor").symlink_to(outside / "hidden.nor")
    assert [r.label for r in xdi.collect_processed_outputs(root)] == ["real"]


def test_collect_reports_anomalies_with_their_file(tmp_path):
    root = tmp_path / "root"
    make_xdi(root / "bad.nor", column_header="# e norm extra")
    [run] = xdi.collect_processed_outputs(root)
    flagged = [a for a in run.anomalies if a["kind"] == "column_count_mismatch"]
    assert flagged and flagged[0]["source_relative_path"] == "bad.nor"
