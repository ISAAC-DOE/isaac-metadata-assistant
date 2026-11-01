"""``collect_all_generic``: every reader's sniff over not-yet-claimed files, deterministic
precedence, each file claimed at most once, claims recorded. SYNTHETIC files only."""

from __future__ import annotations

from pathlib import Path

import pytest

from isaac_api.local_import import readers
from isaac_api.local_import.readers import mca, ssrl_xdc, two_column, xdi, xes_tab

from test_local_import_reader_mca import make_mca
from test_local_import_reader_ssrl_xdc import make_scan
from test_local_import_reader_two_column import make_two
from test_local_import_reader_xdi import make_xdi
from test_local_import_reader_xes_tab import make_xes


def build(root: Path) -> Path:
    make_scan(root / "bt" / "run_a_A.001")
    make_scan(root / "bt" / "run_a_A.002")
    (root / "bt" / "run_a").mkdir()
    (root / "bt" / "run_a" / "SYN_context.txt").write_text("context only\n")
    make_xdi(root / "proc" / "norm_one.nor")
    make_mca(root / "mca" / "spec_one.mca")
    make_xes(root / "xes" / "scan_x_1.txt")
    make_xes(root / "xes" / "scan_x_2.txt")
    make_two(root / "two" / "plain.txt")
    (root / "misc").mkdir()
    (root / "misc" / "unknown.bin").write_bytes(bytes(range(40)))
    (root / "misc" / "notes.txt").write_text("free text, not a table\nsecond line\n")
    return root


def test_the_precedence_is_the_documented_fixed_order():
    assert [name for name, _ in readers.READERS] == ["ssrl_xdc", "xdi", "mca", "xes_tab", "two_column"]
    assert readers.collect_all_generic.__module__ == "isaac_api.local_import.readers"


def test_each_file_is_claimed_by_exactly_one_reader_and_the_rest_are_unclaimed(tmp_path):
    root = build(tmp_path / "root")
    u = readers.collect_all_generic(root)
    by_reader = {}
    for c in u.claims:
        by_reader.setdefault(c["reader"], []).append(c["relative_path"])
    assert sorted(by_reader["ssrl_xdc"]) == ["bt/run_a/SYN_context.txt", "bt/run_a_A.001", "bt/run_a_A.002"]
    assert by_reader["xdi"] == ["proc/norm_one.nor"] and by_reader["mca"] == ["mca/spec_one.mca"]
    assert sorted(by_reader["xes_tab"]) == ["xes/scan_x_1.txt", "xes/scan_x_2.txt"]
    assert by_reader["two_column"] == ["two/plain.txt"]
    paths = [c["relative_path"] for c in u.claims]
    assert len(paths) == len(set(paths)), "a file was claimed twice"
    assert sorted(u.unclaimed) == ["misc/notes.txt", "misc/unknown.bin"]
    assert u.duplicate_claims == [] and u.files_seen == len(paths) + len(u.unclaimed)


def test_runs_come_back_in_precedence_order_with_distinct_keys(tmp_path):
    u = readers.collect_all_generic(build(tmp_path / "root"))
    assert [r.profile for r in u.runs] == ["ssrl_xdc_v1", "xdi_v1", "mca_v1", "xes_tab_v1", "two_column_v1"]
    assert len({r.run_key for r in u.runs}) == len(u.runs)
    assert all(r.reader_id for r in u.runs)


def test_the_result_is_deterministic(tmp_path):
    root = build(tmp_path / "root")
    a, b = readers.collect_all_generic(root), readers.collect_all_generic(root)
    assert [r.run_key for r in a.runs] == [r.run_key for r in b.runs] and a.claims == b.claims and a.unclaimed == b.unclaimed


def test_files_a_deterministic_reader_already_read_are_skipped_never_claimed(tmp_path):
    root = build(tmp_path / "root")
    u = readers.collect_all_generic(root, skip=["xes/scan_x_1.txt", "two/plain.txt", "not/in/the/folder"])
    claimed = {c["relative_path"] for c in u.claims}
    assert "xes/scan_x_1.txt" not in claimed and "two/plain.txt" not in claimed
    assert "xes/scan_x_2.txt" in claimed
    assert "xes/scan_x_1.txt" not in u.unclaimed  # skipped is not "unclaimed": someone else read it
    assert u.skipped == 2


def test_an_earlier_reader_wins_a_file_a_later_one_would_also_accept(tmp_path):
    root = tmp_path / "root"
    # An XDI-signed file named `.txt` is also not two-column text; an `.mca` is not xes. The shared
    # case: a file two sniffers accept. A two-column-looking file with an XDI first line is XDI.
    (root).mkdir()
    (root / "x.txt").write_text("# XDI/1.0 Athena/0.9\n# Column.1: a\n#-------\n# a b\n1 2\n3 4\n")
    assert xdi.sniff(root / "x.txt") and not two_column.sniff(root / "x.txt")
    shared = make_xes(root / "y_1.txt", header="xes0\txes1", rows=("1\t2", "3\t4"))
    assert xes_tab.sniff(shared) and not two_column.sniff(shared)  # tab header is not two numbers
    u = readers.collect_all_generic(root)
    claims = {c["relative_path"]: c["reader"] for c in u.claims}
    assert claims == {"x.txt": "xdi", "y_1.txt": "xes_tab"}


def test_a_numbered_file_with_a_near_miss_signature_is_reported_unparsed_with_its_reader(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    content = b"SSRL EXAFS Data Collector 4.0\nrest\n"
    (root / "bad_A.001").write_bytes(content)
    u = readers.collect_all_generic(root)
    assert u.runs == [] and u.unparsed == [{"relative_path": "bad_A.001", "reason_code": "signature_not_recognised", "size_bytes": len(content), "reader": "ssrl_xdc"}]
    assert u.unclaimed == ["bad_A.001"]


def test_symlinks_are_refused_everywhere(tmp_path):
    root = build(tmp_path / "root")
    outside = tmp_path / "outside"
    make_two(outside / "hidden.txt")
    (root / "link.txt").symlink_to(outside / "hidden.txt")
    u = readers.collect_all_generic(root)
    assert any(f["relative_path"] == "link.txt" and f["reason"] == "symlink_not_followed" for f in u.refused)
    assert "link.txt" not in {c["relative_path"] for c in u.claims} and "link.txt" not in u.unclaimed


def test_a_symlinked_root_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError):
        readers.collect_all_generic(link)


def test_the_entry_ceiling_is_counted(tmp_path):
    from isaac_api.bl15.inventory import ArchiveLimits
    from isaac_api.local_import.readers._common import Limits

    root = tmp_path / "root"
    for i in range(6):
        make_two(root / f"f{i}.txt")
    u = readers.collect_all_generic(root, Limits(archive=ArchiveLimits(max_entries=4)))
    assert u.files_seen == 4 and u.truncation["files_not_considered"] == 2


def test_nothing_is_written(tmp_path):
    root = build(tmp_path / "root")
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    readers.collect_all_generic(root)
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before


def test_every_reader_module_has_the_same_contract():
    for name, module in readers.READERS:
        assert callable(module.sniff) and callable(module.read) and callable(module.collect_from_files), name
        assert module.READER_ID and module.PROFILE_ID and module.READER_VERSION, name
