"""Every guard in :mod:`isaac_api.bl15.archive`, one test each.

**EVERY ADVERSARIAL ARCHIVE IS BUILT HERE, IN THE TEST, WITH :mod:`zipfile`.** Nothing
malicious is committed to this repository — a checked-in zip bomb or traversal archive
is a thing a future reader, editor, antivirus scanner or CI cache has to be told about
forever, and it is unnecessary: the bytes that express these attacks are a few lines of
``zipfile`` plus, twice, a deliberate patch of the central directory.

**THE REAL CORPUS IS NOT COMMITTED AND IS NOT REQUIRED.** Two tests read it when
``ISAAC_BL15_CORPUS_DIR`` / ``ISAAC_BL15_CORPUS_ZIP`` point at a folder and a ZIP the
reader holds themselves, and **skip** otherwise, with a message saying so. No absolute
path to anybody's home directory appears in this file: an earlier repository-wide guard
was withdrawn precisely because twelve legitimate fixture paths tripped it, and a test
that hardcodes one reader's Downloads folder is a test that only ever passes for them.

Two shapes this file deliberately uses everywhere:

* **Every refusal test asserts the inventory CAME BACK.** A guard that raises is not a
  guard, it is an outage: the scientist loses the other 1,191 files because one member
  was crafted. So each test checks the reason AND that ``entries``/``refused`` are a
  usable answer.
* **Negative controls sit beside the positives.** ``..hidden`` must NOT be refused as
  traversal, a flat ZIP must NOT have a prefix stripped, and a legitimate high-ratio
  member under the ceiling must NOT be refused. A guard with no negative control is
  indistinguishable from a guard that refuses everything.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import struct
import zipfile
from pathlib import Path

import pytest

from isaac_api.bl15 import archive
from isaac_api.bl15.inventory import (
    REFUSAL_ABSOLUTE_PATH,
    REFUSAL_COMPRESSION_RATIO,
    REFUSAL_PATH_TOO_LONG,
    REFUSAL_PATH_TRAVERSAL,
    REFUSAL_REASONS,
    REFUSAL_SYMLINK,
    REFUSAL_TOO_DEEP,
    REFUSAL_TOO_LARGE,
    REFUSAL_TOO_MANY_ENTRIES,
    REFUSAL_TOTAL_TOO_LARGE,
    REFUSAL_UNDECODABLE,
    REFUSAL_UNREADABLE,
    ArchiveLimits,
)

# --- helpers -----------------------------------------------------------------


def _reasons(inventory) -> list[str]:
    return [r["reason"] for r in inventory.refused]


def _refusal_for(inventory, path: str) -> dict:
    for entry in inventory.refused:
        if entry["archive_path"] == path:
            return entry
    raise AssertionError(
        f"no refusal for {path!r}; refusals were "
        f"{[(r['archive_path'], r['reason']) for r in inventory.refused]}"
    )


def _zip_with(tmp_path: Path, members: dict, *, name: str = "a.zip", compress=zipfile.ZIP_STORED) -> Path:
    """A ZIP built from ``{member_name: bytes}``, written through ``zipfile``."""
    target = tmp_path / name
    with zipfile.ZipFile(target, "w", compress) as zf:
        for member, payload in members.items():
            zf.writestr(member, payload)
    return target


def _zip_with_raw_names(tmp_path: Path, members: dict, *, name: str = "a.zip") -> Path:
    """A ZIP whose member names bypass ``writestr``'s own normalisation.

    ``ZipFile.writestr`` is happy to store ``../x`` but rewrites some separators, so a
    traversal or absolute member is written through an explicit :class:`ZipInfo` whose
    ``filename`` is set afterwards. That is exactly how a crafted archive arrives.
    """
    target = tmp_path / name
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as zf:
        for member, payload in members.items():
            info = zipfile.ZipInfo("placeholder")
            info.filename = member
            zf.writestr(info, payload)
    return target


def _small_tree(root: Path) -> None:
    """A synthetic folder shaped like the real corpus, at a thousandth the size.

    It reproduces the three anomalies the characterization document names, because a
    walker tested only on a flat directory of distinct files would not exercise the
    parts that matter: an extensionless file beside an extensionless file of a different
    KIND, a scan directory holding a byte-identical copy of its root acquisition file,
    and a scan directory with no scan children at all.
    """
    root.mkdir(parents=True, exist_ok=True)
    acquisition = b"#F 01_SYNTH_sampleA\n#E 4102444800\n#O0  mono  sx\n#P0 1.0 2.0\n"
    (root / "01_SYNTH_sampleA").write_bytes(acquisition)
    scan_dir = root / "01_SYNTH_sampleA_dir"
    scan_dir.mkdir()
    # The measured anomaly: every `*_dir` also holds a byte-identical copy.
    (scan_dir / "01_SYNTH_sampleA").write_bytes(acquisition)
    (scan_dir / "01_SYNTH_sampleA_001.dat").write_bytes(b"#S 1 gscan\n#L energy I1\n1 2\n")
    (root / "02_SYNTH_sampleB").write_bytes(b"#F 02_SYNTH_sampleB\n")
    # A measurement with zero scan children: `_dir` exists and holds only the copy.
    empty_ish = root / "02_SYNTH_sampleB_dir"
    empty_ish.mkdir()
    (empty_ish / "02_SYNTH_sampleB").write_bytes(b"#F 02_SYNTH_sampleB\n")
    (root / "readme.txt").write_bytes(b"# SYNTHETIC-BEAMTIME\nelement Xx\n")
    (root / "run01.mac").write_bytes(b"newfile 01_SYNTH_sampleA\nSynth_xas 0.5 2\n")
    # Extensionless MACRO beside an extensionless ACQUISITION -- 2.1 in the
    # characterization document, and the reason classification is content-led.
    (root / "runsynth").write_bytes(b"qdo Synth_XAS.mac\n")


# --- the folder walk, and the properties the contract requires ---------------


def test_a_small_folder_tree_is_complete_sorted_deterministic_and_relative(tmp_path):
    root = tmp_path / "corpus"
    _small_tree(root)

    first = archive.inventory_folder(root, root_label="synthetic mini corpus")
    second = archive.inventory_folder(root, root_label="synthetic mini corpus")

    paths = [e.archive_path for e in first.entries]
    on_disk = sorted(
        str(p.relative_to(root)).replace(os.sep, "/")
        for p in root.rglob("*")
        if p.is_file()
    )

    # COMPLETE: every file on disk, and nothing else.
    assert paths == on_disk
    assert first.refused == ()
    assert first.truncated_reason is None

    # SORTED, and stated as its own assertion rather than inferred from the line
    # above, because `on_disk` is sorted too and the two could agree while both
    # being in some other order.
    assert paths == sorted(paths)

    # DETERMINISTIC, byte-for-byte, which is what `to_state` is for.
    assert json.dumps(first.to_state(), sort_keys=True) == json.dumps(
        second.to_state(), sort_keys=True
    )

    # NEVER ABSOLUTE. Checked three ways because one absolute path in an audit
    # trail leaks the reader's filesystem into a scientist's evidence.
    for entry in first.entries:
        assert not entry.archive_path.startswith("/")
        assert not entry.archive_path.startswith("\\")
        assert ".." not in entry.archive_path.split("/")
        assert str(root) not in entry.archive_path

    assert first.total_bytes == sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def test_source_record_fields_are_derived_from_the_relative_path(tmp_path):
    root = tmp_path / "corpus"
    _small_tree(root)
    inventory = archive.inventory_folder(root, root_label="x")
    by_path = inventory.by_path()

    nested = by_path["01_SYNTH_sampleA_dir/01_SYNTH_sampleA_001.dat"]
    assert nested.basename == "01_SYNTH_sampleA_001.dat"
    assert nested.extension == "dat"
    assert nested.parent_dir == "01_SYNTH_sampleA_dir"
    assert nested.depth == 1

    # The extensionless pair from 2.1: `extension` is "" for both, which is why it
    # is recorded and deliberately not used to classify.
    assert by_path["runsynth"].extension == ""
    assert by_path["01_SYNTH_sampleA"].extension == ""
    assert by_path["runsynth"].parent_dir == ""
    assert by_path["runsynth"].depth == 0


def test_duplicate_groups_come_from_content_and_keep_every_member(tmp_path):
    root = tmp_path / "corpus"
    _small_tree(root)
    inventory = archive.inventory_folder(root, root_label="x")

    # Two groups: each `_dir` holds a byte-identical copy of its root file.
    assert inventory.duplicate_groups == (
        ("01_SYNTH_sampleA", "01_SYNTH_sampleA_dir/01_SYNTH_sampleA"),
        ("02_SYNTH_sampleB", "02_SYNTH_sampleB_dir/02_SYNTH_sampleB"),
    )
    # KEPT, not dropped: every grouped path is still an entry.
    listed = {e.archive_path for e in inventory.entries}
    for group in inventory.duplicate_groups:
        for member in group:
            assert member in listed


def test_similar_names_with_different_content_are_not_fused(tmp_path):
    """The `run29.mac` / `run29.mac.mac` case, which a name heuristic would merge."""
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "run29.mac").write_bytes(b"newfile a\n")
    (root / "run29.mac.mac").write_bytes(b"newfile b\n")
    inventory = archive.inventory_folder(root, root_label="x")
    assert inventory.duplicate_groups == ()
    assert len(inventory.entries) == 2


# --- traversal and absolute paths -------------------------------------------


@pytest.mark.parametrize(
    "member",
    [
        "../../etc/passwd",
        "../etc/passwd",
        "good/../../escape.txt",
        "a/b/../../../out.txt",
        "..\\..\\windows\\system32\\x.txt",
    ],
)
def test_a_zip_member_with_a_dotdot_segment_is_refused_as_traversal(tmp_path, member):
    zip_path = _zip_with_raw_names(tmp_path, {member: b"payload"})
    inventory = archive.inventory_zip(zip_path, root_label="crafted")

    assert inventory.entries == ()
    assert _reasons(inventory) == [REFUSAL_PATH_TRAVERSAL]
    # The inventory CAME BACK and names what it refused.
    assert member in inventory.refused[0]["archive_path"]
    assert "'..'" in inventory.refused[0]["detail"]


def test_a_traversal_member_alongside_good_members_loses_only_itself(tmp_path):
    zip_path = _zip_with_raw_names(
        tmp_path, {"readme.txt": b"ok\n", "../escape": b"bad\n", "data.dat": b"ok\n"}
    )
    inventory = archive.inventory_zip(zip_path, root_label="crafted")
    assert [e.archive_path for e in inventory.entries] == ["data.dat", "readme.txt"]
    assert _reasons(inventory) == [REFUSAL_PATH_TRAVERSAL]
    assert inventory.truncated_reason is None


def test_a_name_merely_STARTING_with_dots_is_not_traversal(tmp_path):
    """NEGATIVE CONTROL. ``..hidden`` is a legal filename, not an escape."""
    zip_path = _zip_with_raw_names(
        tmp_path, {"..hidden": b"a", "..d/..f.txt": b"b", "./plain.txt": b"c"}
    )
    inventory = archive.inventory_zip(zip_path, root_label="ordinary")
    assert inventory.refused == ()
    assert [e.archive_path for e in inventory.entries] == [
        "..d/..f.txt",
        "..hidden",
        "plain.txt",
    ]


@pytest.mark.parametrize(
    "member",
    [
        "/etc/passwd",
        "C:\\Windows\\System32\\drivers\\etc\\hosts",
        "c:/windows/x.txt",
        "\\\\fileserver\\share\\x.txt",
    ],
)
def test_an_absolute_zip_member_is_refused(tmp_path, member):
    zip_path = _zip_with_raw_names(tmp_path, {member: b"payload"})
    inventory = archive.inventory_zip(zip_path, root_label="crafted")
    assert inventory.entries == ()
    assert _reasons(inventory) == [REFUSAL_ABSOLUTE_PATH]
    assert "absolute" in inventory.refused[0]["detail"]


def test_nothing_is_written_outside_the_archive_and_resolve_within_proves_containment(tmp_path):
    root = tmp_path / "corpus"
    _small_tree(root)
    sibling = tmp_path / "SENTINEL_MUST_NOT_EXIST"

    zip_path = _zip_with_raw_names(
        tmp_path, {"../SENTINEL_MUST_NOT_EXIST": b"x", "ok.txt": b"y"}
    )
    archive.inventory_zip(zip_path, root_label="crafted")
    # The whole class is unreachable because the ZIP walk never extracts.
    assert not sibling.exists()

    assert archive.resolve_within(root, "readme.txt") == (root / "readme.txt").resolve()
    with pytest.raises(ValueError):
        archive.resolve_within(root, "../escape")


# --- symlinks ----------------------------------------------------------------


def test_a_symlinked_file_in_a_folder_walk_is_refused_and_not_followed(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    secret = tmp_path / "outside.txt"
    secret.write_bytes(b"SHOULD-NOT-BE-READ")
    (root / "real.txt").write_bytes(b"ok\n")
    (root / "link.txt").symlink_to(secret)

    inventory = archive.inventory_folder(root, root_label="x")

    assert [e.archive_path for e in inventory.entries] == ["real.txt"]
    assert _refusal_for(inventory, "link.txt")["reason"] == REFUSAL_SYMLINK
    # Not followed: the target's bytes are nowhere in the inventory.
    target_digest = hashlib.sha256(b"SHOULD-NOT-BE-READ").hexdigest()
    assert all(e.content_sha256 != target_digest for e in inventory.entries)


def test_a_symlink_loop_in_a_folder_walk_terminates(tmp_path):
    """``ln -s . loop`` is an ordinary filesystem, not a crafted archive.

    A walk that followed directory symlinks would never return, so this test would
    hang rather than fail — which is itself the report.
    """
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "real.txt").write_bytes(b"ok\n")
    (root / "loop").symlink_to(root)
    (root / "up").symlink_to(tmp_path)

    inventory = archive.inventory_folder(root, root_label="x")

    assert [e.archive_path for e in inventory.entries] == ["real.txt"]
    assert sorted(_reasons(inventory)) == [REFUSAL_SYMLINK, REFUSAL_SYMLINK]
    assert _refusal_for(inventory, "loop")["reason"] == REFUSAL_SYMLINK
    assert _refusal_for(inventory, "up")["reason"] == REFUSAL_SYMLINK


def test_an_archive_root_that_is_itself_a_symlink_is_refused(tmp_path):
    real = tmp_path / "real"
    _small_tree(real)
    link = tmp_path / "link"
    link.symlink_to(real)
    inventory = archive.inventory_folder(link, root_label="x")
    assert inventory.entries == ()
    assert _reasons(inventory) == [REFUSAL_SYMLINK]


def test_a_zip_member_marked_as_a_symlink_is_refused(tmp_path):
    """External attributes carrying ``S_IFLNK``; the member's content is a PATH."""
    zip_path = tmp_path / "links.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("real.txt", b"ok\n")
        link = zipfile.ZipInfo("evil-link")
        link.create_system = 3  # Unix, so the mode bits are meaningful
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, b"/etc/passwd")

    inventory = archive.inventory_zip(zip_path, root_label="crafted")

    assert [e.archive_path for e in inventory.entries] == ["real.txt"]
    assert _refusal_for(inventory, "evil-link")["reason"] == REFUSAL_SYMLINK
    # The target path was never read as if it were a source.
    assert all(
        e.content_sha256 != hashlib.sha256(b"/etc/passwd").hexdigest()
        for e in inventory.entries
    )


def test_a_zip_member_marked_as_a_device_node_is_refused_as_unreadable(tmp_path):
    zip_path = tmp_path / "odd.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("real.txt", b"ok\n")
        node = zipfile.ZipInfo("device")
        node.create_system = 3
        node.external_attr = (stat.S_IFCHR | 0o666) << 16
        zf.writestr(node, b"")
    inventory = archive.inventory_zip(zip_path, root_label="crafted")
    assert [e.archive_path for e in inventory.entries] == ["real.txt"]
    assert _refusal_for(inventory, "device")["reason"] == REFUSAL_UNREADABLE


def test_a_fifo_in_a_folder_walk_is_refused_rather_than_opened(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "real.txt").write_bytes(b"ok\n")
    try:
        os.mkfifo(root / "pipe")
    except (AttributeError, OSError):  # pragma: no cover - platform without mkfifo
        pytest.skip("this platform cannot create a FIFO")
    inventory = archive.inventory_folder(root, root_label="x")
    assert [e.archive_path for e in inventory.entries] == ["real.txt"]
    assert _refusal_for(inventory, "pipe")["reason"] == REFUSAL_UNREADABLE
    assert "not a regular file" in _refusal_for(inventory, "pipe")["detail"]


# --- per-entry size ----------------------------------------------------------


def test_an_oversized_folder_file_is_refused_with_its_size_and_the_ceiling(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "small.txt").write_bytes(b"a" * 10)
    (root / "big.bin").write_bytes(b"b" * 5_000)

    inventory = archive.inventory_folder(
        root, root_label="x", limits=ArchiveLimits(max_entry_bytes=1_000)
    )

    assert [e.archive_path for e in inventory.entries] == ["small.txt"]
    refusal = _refusal_for(inventory, "big.bin")
    assert refusal["reason"] == REFUSAL_TOO_LARGE
    assert "5000" in refusal["detail"] and "1000" in refusal["detail"]
    # A per-entry refusal does NOT truncate the inventory.
    assert inventory.truncated_reason is None


def test_an_oversized_zip_member_is_refused_with_its_size_and_the_ceiling(tmp_path):
    zip_path = _zip_with(tmp_path, {"small.txt": b"a" * 10, "big.bin": b"b" * 5_000})
    inventory = archive.inventory_zip(
        zip_path, root_label="x", limits=ArchiveLimits(max_entry_bytes=1_000)
    )
    assert [e.archive_path for e in inventory.entries] == ["small.txt"]
    refusal = _refusal_for(inventory, "big.bin")
    assert refusal["reason"] == REFUSAL_TOO_LARGE
    assert "5000" in refusal["detail"] and "1000" in refusal["detail"]


# --- the two ceilings that TRUNCATE -----------------------------------------


def test_the_total_byte_ceiling_stops_the_walk_and_marks_it_incomplete(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    for name in ("a.txt", "b.txt", "c.txt"):
        (root / name).write_bytes(b"x" * 100)

    inventory = archive.inventory_folder(
        root, root_label="x", limits=ArchiveLimits(max_total_bytes=150)
    )

    assert [e.archive_path for e in inventory.entries] == ["a.txt"]
    assert inventory.total_bytes == 100
    assert inventory.truncated_reason == REFUSAL_TOTAL_TOO_LARGE
    refusal = _refusal_for(inventory, "b.txt")
    assert refusal["reason"] == REFUSAL_TOTAL_TOO_LARGE
    assert "150" in refusal["detail"]
    assert "incomplete" in refusal["detail"]
    # `to_state` carries the incompleteness, which is what a reconstruction reads.
    assert inventory.to_state()["truncated_reason"] == REFUSAL_TOTAL_TOO_LARGE


def test_the_entry_count_ceiling_stops_the_walk_and_keeps_a_deterministic_prefix(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    for name in ("e.txt", "a.txt", "d.txt", "b.txt", "c.txt"):
        (root / name).write_bytes(b"x")

    inventory = archive.inventory_folder(
        root, root_label="x", limits=ArchiveLimits(max_entries=2)
    )

    # SORTED order decides which entries survive, not directory iteration order.
    assert [e.archive_path for e in inventory.entries] == ["a.txt", "b.txt"]
    assert inventory.truncated_reason == REFUSAL_TOO_MANY_ENTRIES
    refusal = _refusal_for(inventory, "")
    assert refusal["reason"] == REFUSAL_TOO_MANY_ENTRIES
    assert "3" in refusal["detail"] and "2" in refusal["detail"]


def test_the_entry_count_ceiling_applies_to_a_zip_too(tmp_path):
    zip_path = _zip_with(tmp_path, {n: b"x" for n in ("e", "a", "d", "b", "c")})
    inventory = archive.inventory_zip(
        zip_path, root_label="x", limits=ArchiveLimits(max_entries=2)
    )
    assert [e.archive_path for e in inventory.entries] == ["a", "b"]
    assert inventory.truncated_reason == REFUSAL_TOO_MANY_ENTRIES


# --- decompression ratio, and the archive that lies about it -----------------


def test_an_honest_zip_bomb_is_refused_on_its_declared_ratio_before_any_read(tmp_path):
    zip_path = _zip_with(
        tmp_path,
        {"bomb.txt": b"\0" * 2_000_000, "ok.txt": b"hello"},
        compress=zipfile.ZIP_DEFLATED,
    )
    with zipfile.ZipFile(zip_path) as zf:
        info = zf.getinfo("bomb.txt")
        declared_ratio = info.file_size / max(info.compress_size, 1)
    assert declared_ratio > 100, f"fixture is not a bomb: {declared_ratio:.1f}:1"

    inventory = archive.inventory_zip(
        zip_path,
        root_label="crafted",
        limits=ArchiveLimits(max_compression_ratio=100, max_entry_bytes=8_000_000),
    )

    assert [e.archive_path for e in inventory.entries] == ["ok.txt"]
    refusal = _refusal_for(inventory, "bomb.txt")
    assert refusal["reason"] == REFUSAL_COMPRESSION_RATIO
    assert "100:1" in refusal["detail"]


def test_a_legitimately_compressible_member_under_the_ceiling_is_accepted(tmp_path):
    """NEGATIVE CONTROL: text compresses well and must not be refused for it."""
    zip_path = _zip_with(
        tmp_path, {"spectrum.dat": b"1 2\n" * 5_000}, compress=zipfile.ZIP_DEFLATED
    )
    inventory = archive.inventory_zip(zip_path, root_label="ordinary")
    assert [e.archive_path for e in inventory.entries] == ["spectrum.dat"]
    assert inventory.refused == ()


def _lie_about_file_size(zip_path: Path, member: str, lie: int) -> int:
    """Patch ``file_size`` DOWN in both the local header and the central directory.

    This is the attack the declared-size pre-check cannot see: the archive says the
    member is tiny, and its compressed stream expands to megabytes. Returns the true
    size so the test can assert against it.
    """
    with zipfile.ZipFile(zip_path) as zf:
        true_size = zf.getinfo(member).file_size
    raw = zip_path.read_bytes()
    pattern = struct.pack("<I", true_size)
    assert raw.count(pattern) == 2, (
        "expected the true size in exactly the local header and the central "
        f"directory, found {raw.count(pattern)}"
    )
    zip_path.write_bytes(raw.replace(pattern, struct.pack("<I", lie)))
    return true_size


def test_a_member_LYING_about_its_size_cannot_expand_past_the_ceiling(tmp_path):
    """The declared sizes are not trusted, and this is the test that proves it.

    Without the byte counter in :func:`archive._read_zip_member` the only thing
    stopping this member would be ``zipfile``'s own trust in the central directory —
    i.e. the attacker's number. Here the archive declares 16 bytes and the stream
    expands to 3 MB; the read stops at the cap, having materialised nothing larger,
    and the member is refused.
    """
    zip_path = _zip_with(
        tmp_path, {"liar.bin": b"\0" * 3_000_000}, compress=zipfile.ZIP_DEFLATED
    )
    true_size = _lie_about_file_size(zip_path, "liar.bin", 16)

    with zipfile.ZipFile(zip_path) as zf:
        info = zf.getinfo("liar.bin")
        assert info.file_size == 16, "the fixture did not actually lie"
        # The pre-check CANNOT catch it: a declared 16 bytes from ~3 KB compressed
        # is a ratio below 1, and 16 is under any entry ceiling.
        assert info.file_size / max(info.compress_size, 1) < 1

    limits = ArchiveLimits(max_entry_bytes=200_000, max_compression_ratio=1_000)
    inventory = archive.inventory_zip(zip_path, root_label="crafted", limits=limits)

    assert inventory.entries == ()
    refusal = _refusal_for(inventory, "liar.bin")
    assert refusal["reason"] in (REFUSAL_COMPRESSION_RATIO, REFUSAL_TOO_LARGE)
    assert "expanded past" in refusal["detail"]
    # And nothing anywhere in the inventory accounts for 3 MB.
    assert inventory.total_bytes == 0
    assert true_size == 3_000_000


def test_the_probe_descriptor_preserves_everything_the_read_depends_on(tmp_path):
    """``ZipInfo`` is a ``__slots__`` class, so the copy goes through pickling.

    A copy that silently lost ``header_offset`` would make every member read the
    WRONG BYTES while raising nothing, so the four load-bearing attributes are
    asserted here rather than assumed to survive whichever interpreter CI runs
    (3.11) versus the one this was measured on (3.12).
    """
    zip_path = _zip_with(
        tmp_path, {"a.txt": b"a" * 50, "b.txt": b"b" * 60}, compress=zipfile.ZIP_DEFLATED
    )
    with zipfile.ZipFile(zip_path) as zf:
        for name, declared in (("a.txt", 50), ("b.txt", 60)):
            info = zf.getinfo(name)
            probe = archive._probe_info(info, 999)
            for attribute in archive._PROBE_CRITICAL:
                assert getattr(probe, attribute) == getattr(info, attribute), attribute
            assert probe.file_size == 999
            assert probe.CRC is None
            # The ORIGINAL is untouched: the walk still has the archive's own
            # declaration to compare the read against.
            assert info.file_size == declared
            assert info.CRC is not None


def test_a_member_lying_about_its_size_the_other_way_is_refused_as_unreadable(tmp_path):
    """A member that COMPLETES under the cap but disagrees with its declaration.

    Here the lie is small enough that the read finishes, so the catch is the
    read-versus-declared comparison rather than the cap. Both paths exist because
    either alone leaves a hole.
    """
    zip_path = _zip_with(
        tmp_path, {"short.bin": b"Z" * 4_000}, compress=zipfile.ZIP_DEFLATED
    )
    _lie_about_file_size(zip_path, "short.bin", 12)

    inventory = archive.inventory_zip(
        zip_path,
        root_label="crafted",
        limits=ArchiveLimits(max_entry_bytes=1_000_000, max_compression_ratio=1_000_000),
    )
    assert inventory.entries == ()
    refusal = _refusal_for(inventory, "short.bin")
    assert refusal["reason"] == REFUSAL_UNREADABLE
    assert "12" in refusal["detail"] and "4000" in refusal["detail"]


# --- depth and path length ---------------------------------------------------


def test_a_path_deeper_than_the_ceiling_is_refused_and_not_descended(tmp_path):
    root = tmp_path / "corpus"
    (root / "a" / "b" / "c").mkdir(parents=True)
    (root / "top.txt").write_bytes(b"x")
    (root / "a" / "one.txt").write_bytes(b"x")
    (root / "a" / "b" / "c" / "deep.txt").write_bytes(b"x")

    inventory = archive.inventory_folder(
        root, root_label="x", limits=ArchiveLimits(max_depth=1)
    )

    assert [e.archive_path for e in inventory.entries] == ["a/one.txt", "top.txt"]
    refusal = _refusal_for(inventory, "a/b/c")
    assert refusal["reason"] == REFUSAL_TOO_DEEP
    assert "2" in refusal["detail"] and "1" in refusal["detail"]
    # NOT DESCENDED: the file below the refused directory was never enumerated.
    assert _reasons(inventory) == [REFUSAL_TOO_DEEP]
    assert not any("deep.txt" in r["archive_path"] for r in inventory.refused)


def test_a_zip_member_deeper_than_the_ceiling_is_refused(tmp_path):
    zip_path = _zip_with(tmp_path, {"a/b/c/d.txt": b"x", "ok.txt": b"y"})
    inventory = archive.inventory_zip(
        zip_path, root_label="x", limits=ArchiveLimits(max_depth=2)
    )
    assert [e.archive_path for e in inventory.entries] == ["ok.txt"]
    assert _refusal_for(inventory, "a/b/c/d.txt")["reason"] == REFUSAL_TOO_DEEP


def test_a_path_longer_than_the_ceiling_is_refused(tmp_path):
    zip_path = _zip_with(tmp_path, {"short": b"x", "y" * 40: b"x"})
    inventory = archive.inventory_zip(
        zip_path, root_label="x", limits=ArchiveLimits(max_path_chars=10)
    )
    assert [e.archive_path for e in inventory.entries] == ["short"]
    refusal = _refusal_for(inventory, "y" * 40)
    assert refusal["reason"] == REFUSAL_PATH_TOO_LONG
    assert "40" in refusal["detail"] and "10" in refusal["detail"]


# --- unreadable --------------------------------------------------------------


def test_a_corrupt_zip_returns_an_inventory_carrying_the_refusal_and_does_not_raise(tmp_path):
    zip_path = _zip_with(tmp_path, {"a.txt": b"hello", "b.txt": b"world"})
    raw = zip_path.read_bytes()
    # Truncate the central directory off the end.
    zip_path.write_bytes(raw[: len(raw) // 2])

    inventory = archive.inventory_zip(zip_path, root_label="damaged archive")

    assert inventory.entries == ()
    assert _reasons(inventory) == [REFUSAL_UNREADABLE]
    assert "could not be opened" in inventory.refused[0]["detail"]
    assert inventory.root_label == "damaged archive"


def test_a_file_that_is_not_a_zip_at_all_is_refused_rather_than_raising(tmp_path):
    not_a_zip = tmp_path / "notes.txt"
    not_a_zip.write_bytes(b"this is not a zip file\n")
    inventory = archive.inventory_zip(not_a_zip, root_label="x")
    assert inventory.entries == ()
    assert _reasons(inventory) == [REFUSAL_UNREADABLE]


def test_a_corrupt_zip_MEMBER_is_refused_while_its_siblings_survive(tmp_path):
    # Deliberately POORLY compressible, and deterministic: `b"d" * 4000` deflates
    # to about twenty bytes, so corrupting "offsets 5..25 of the compressed
    # stream" walked straight past the member and into the central directory,
    # breaking the whole archive. That version of this test failed for a reason
    # that had nothing to do with the guard it was written for.
    noisy = bytes((i * 167 + 13) % 256 for i in range(8_000))
    zip_path = _zip_with(
        tmp_path,
        {"good.txt": b"g" * 200, "damaged.bin": noisy},
        compress=zipfile.ZIP_DEFLATED,
    )
    raw = bytearray(zip_path.read_bytes())
    with zipfile.ZipFile(zip_path) as zf:
        info = zf.getinfo("damaged.bin")
    assert info.compress_size > 200, (
        f"the fixture compressed to {info.compress_size} bytes; the corruption "
        "window below would overrun the member"
    )
    # The local header's own field lengths are READ rather than assumed: a
    # hardcoded `+30 + len(filename)` ignores the extra field.
    head = raw[info.header_offset : info.header_offset + 30]
    name_len, extra_len = struct.unpack("<2H", head[26:30])
    start = info.header_offset + 30 + name_len + extra_len
    for offset in range(start + 20, start + 120):
        raw[offset] ^= 0xFF
    zip_path.write_bytes(bytes(raw))

    inventory = archive.inventory_zip(zip_path, root_label="x")

    assert [e.archive_path for e in inventory.entries] == ["good.txt"]
    assert _refusal_for(inventory, "damaged.bin")["reason"] == REFUSAL_UNREADABLE


def test_an_unreadable_folder_file_is_refused_while_its_siblings_survive(tmp_path):
    if os.geteuid() == 0:  # pragma: no cover - root ignores the mode bits
        pytest.skip("running as root; file permissions do not restrict reads")
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "ok.txt").write_bytes(b"ok\n")
    locked = root / "locked.txt"
    locked.write_bytes(b"secret\n")
    locked.chmod(0o000)
    try:
        inventory = archive.inventory_folder(root, root_label="x")
    finally:
        locked.chmod(0o600)
    assert [e.archive_path for e in inventory.entries] == ["ok.txt"]
    assert _refusal_for(inventory, "locked.txt")["reason"] == REFUSAL_UNREADABLE


def test_an_unreadable_subdirectory_is_refused_while_the_rest_survives(tmp_path):
    if os.geteuid() == 0:  # pragma: no cover
        pytest.skip("running as root; directory permissions do not restrict listing")
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "ok.txt").write_bytes(b"ok\n")
    shut = root / "shut"
    shut.mkdir()
    (shut / "inside.txt").write_bytes(b"x")
    shut.chmod(0o000)
    try:
        inventory = archive.inventory_folder(root, root_label="x")
    finally:
        shut.chmod(0o700)
    assert [e.archive_path for e in inventory.entries] == ["ok.txt"]
    assert _refusal_for(inventory, "shut")["reason"] == REFUSAL_UNREADABLE


def test_a_missing_root_is_refused_rather_than_raising(tmp_path):
    inventory = archive.inventory_folder(tmp_path / "nope", root_label="x")
    assert inventory.entries == ()
    assert _reasons(inventory) == [REFUSAL_UNREADABLE]
    inventory = archive.inventory_zip(tmp_path / "nope.zip", root_label="x")
    assert _reasons(inventory) == [REFUSAL_UNREADABLE]


def test_a_root_that_is_a_file_is_refused_rather_than_walked(tmp_path):
    plain = tmp_path / "plain.txt"
    plain.write_bytes(b"x")
    inventory = archive.inventory_folder(plain, root_label="x")
    assert _reasons(inventory) == [REFUSAL_UNREADABLE]
    assert "not a directory" in inventory.refused[0]["detail"]


# --- every refusal is a named reason with a number in it ---------------------


def test_every_refusal_this_file_can_produce_names_a_declared_reason(tmp_path):
    zip_path = _zip_with_raw_names(
        tmp_path,
        {
            "ok.txt": b"x",
            "../escape": b"x",
            "/absolute": b"x",
            "a/b/c/d/deep.txt": b"x",
            "z" * 300: b"x",
            "huge.bin": b"H" * 4_000,
        },
    )
    inventory = archive.inventory_zip(
        zip_path,
        root_label="x",
        limits=ArchiveLimits(max_depth=2, max_path_chars=64, max_entry_bytes=1_000),
    )
    assert inventory.refused, "the fixture produced no refusals"
    for refusal in inventory.refused:
        assert set(refusal) == {"archive_path", "reason", "detail"}
        assert refusal["reason"] in REFUSAL_REASONS
        assert isinstance(refusal["detail"], str) and refusal["detail"]
    assert {
        REFUSAL_PATH_TRAVERSAL,
        REFUSAL_ABSOLUTE_PATH,
        REFUSAL_TOO_DEEP,
        REFUSAL_PATH_TOO_LONG,
        REFUSAL_TOO_LARGE,
    } <= set(_reasons(inventory))


def test_the_ceiling_refusals_state_the_measured_number_and_the_ceiling(tmp_path):
    """A refusal detail that is only a label is the banned pattern, one layer down."""
    zip_path = _zip_with(tmp_path, {"big.bin": b"B" * 4_321})
    inventory = archive.inventory_zip(
        zip_path, root_label="x", limits=ArchiveLimits(max_entry_bytes=1_234)
    )
    detail = _refusal_for(inventory, "big.bin")["detail"]
    assert "4321" in detail  # measured
    assert "1234" in detail  # ceiling


# --- the wrapper-directory rule ---------------------------------------------


def test_a_zip_of_a_folder_inventories_identically_to_the_folder(tmp_path):
    root = tmp_path / "SynthCorpus"
    _small_tree(root)
    zip_path = tmp_path / "wrapped.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, f"SynthCorpus/{path.relative_to(root)}")

    folder = archive.inventory_folder(root, root_label="label")
    from_zip = archive.inventory_zip(zip_path, root_label="label")

    assert [e.archive_path for e in folder.entries] == [
        e.archive_path for e in from_zip.entries
    ]
    assert folder.duplicate_groups == from_zip.duplicate_groups
    assert json.dumps(folder.to_state(), sort_keys=True) == json.dumps(
        from_zip.to_state(), sort_keys=True
    )

    # And the opt-out keeps the wrapper, which is what makes the stripping visible
    # rather than magic.
    unstripped = archive.inventory_zip(
        zip_path, root_label="label", strip_common_root=False
    )
    assert all(
        e.archive_path.startswith("SynthCorpus/") for e in unstripped.entries
    )


@pytest.mark.parametrize(
    "names,expected",
    [
        (["Corpus/a.txt", "Corpus/b/c.txt"], "Corpus"),
        (["a.txt", "b.txt"], None),  # flat: nothing to strip
        (["One/a.txt", "Two/b.txt"], None),  # two top-level folders
        (["Corpus/a.txt", "stray.txt"], None),  # one folder plus a root file
        ([], None),
        (["Corpus/a.txt"], "Corpus"),
    ],
)
def test_the_wrapper_rule_is_narrow(names, expected):
    assert archive.common_root_prefix(names) == expected


# --- decoding ----------------------------------------------------------------


def test_plain_utf8_is_decoded_and_disclosed_as_utf8():
    decoded = archive.decode_source_bytes("#F ok\nmotor 1\n".encode("utf-8"))
    assert decoded is not None
    assert decoded.encoding == "utf-8"
    assert decoded.had_bom is False
    assert decoded.text.startswith("#F ok")


def test_a_bom_is_stripped_and_disclosed_as_utf8_sig():
    """The real beamtime notes file begins ``EF BB BF`` (measured 2026-09-16)."""
    raw = b"\xef\xbb\xbfSample 1 JK3 in acid\n"
    decoded = archive.decode_source_bytes(raw)
    assert decoded is not None
    assert decoded.encoding == "utf-8-sig"
    assert decoded.had_bom is True
    # The mark is GONE from the text, which is the whole point: a reader matching
    # on the first token must not have to know about an invisible character.
    assert decoded.text == "Sample 1 JK3 in acid\n"
    assert "\ufeff" not in decoded.text


def test_latin1_is_the_last_resort_and_is_disclosed_as_such():
    raw = b"caf\xe9 0.5 M\n"  # not valid UTF-8
    assert raw.decode("utf-8", errors="ignore") != raw.decode("latin-1")
    decoded = archive.decode_source_bytes(raw)
    assert decoded is not None
    assert decoded.encoding == "latin-1"
    assert decoded.text == "café 0.5 M\n"


def test_bytes_holding_a_NUL_are_undecodable_rather_than_mojibake():
    """``latin-1`` cannot fail, so without this test the reason is unreachable."""
    assert archive.decode_source_bytes(b"PK\x03\x04\x00\x00binary") is None
    assert archive.decode_source_bytes(b"%PDF-1.7\n\x00\x00\x00") is None
    # NEGATIVE CONTROL: high bytes alone are not binary.
    assert archive.decode_source_bytes(b"\xe9\xe8\xe7") is not None


def test_a_head_read_that_cuts_a_multibyte_sequence_still_decodes_as_utf8():
    text = "energy µ" * 2_000
    raw = text.encode("utf-8")
    for cut in range(len(raw) - 8, len(raw)):
        chunk = raw[:cut]
        decoded = archive.decode_source_bytes(chunk, allow_partial_tail=True)
        assert decoded is not None
        # The disclosed encoding is a property of the FILE, not of where the cut
        # happened to land.
        assert decoded.encoding == "utf-8", f"cut at {cut} fell through to latin-1"


# --- bounded reading --------------------------------------------------------


@pytest.mark.parametrize("as_zip", [False, True])
def test_read_source_text_returns_exactly_one_of_text_and_a_refusal(tmp_path, as_zip):
    root = tmp_path / "corpus"
    _small_tree(root)
    if as_zip:
        source = tmp_path / "c.zip"
        with zipfile.ZipFile(source, "w") as zf:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zf.write(path, str(path.relative_to(root)))
        inventory = archive.inventory_zip(source, root_label="x")
    else:
        source = root
        inventory = archive.inventory_folder(root, root_label="x")

    for entry in inventory.entries:
        text, reason = archive.read_source_text(
            inventory, entry.archive_path, source_root=source
        )
        assert (text is None) != (reason is None), (
            f"{entry.archive_path}: exactly one of text and reason must be set, "
            f"got text={text is not None} reason={reason!r}"
        )
        assert reason is None
        assert text is not None and text.startswith(("#", "newfile", "qdo"))


def test_a_path_the_walk_never_accepted_cannot_be_read(tmp_path):
    """This is what makes every guard in the walk TRANSITIVE.

    A reader that could name a member by hand would bypass the traversal, size and
    ratio refusals entirely — so the read path is keyed off the inventory, not off
    the caller's string.
    """
    root = tmp_path / "corpus"
    _small_tree(root)
    (root / "..secret").write_bytes(b"not inventoried under this name\n")
    inventory = archive.inventory_folder(
        root, root_label="x", limits=ArchiveLimits(max_entries=3)
    )
    assert inventory.truncated_reason == REFUSAL_TOO_MANY_ENTRIES

    dropped = "readme.txt"
    assert dropped not in inventory.by_path()
    text, reason = archive.read_source_text(inventory, dropped, source_root=root)
    assert text is None
    assert reason == REFUSAL_UNREADABLE

    text, reason = archive.read_source_text(
        inventory, "../outside.txt", source_root=root
    )
    assert text is None and reason == REFUSAL_UNREADABLE


def test_reading_a_file_that_changed_since_the_walk_is_refused(tmp_path):
    root = tmp_path / "corpus"
    _small_tree(root)
    inventory = archive.inventory_folder(root, root_label="x")
    (root / "readme.txt").write_bytes(b"# REWRITTEN AFTER THE WALK\n")

    text, reason = archive.read_source_text(inventory, "readme.txt", source_root=root)
    assert text is None
    assert reason == REFUSAL_UNREADABLE


def test_reading_through_a_symlink_that_appeared_after_the_walk_is_refused(tmp_path):
    root = tmp_path / "corpus"
    _small_tree(root)
    inventory = archive.inventory_folder(root, root_label="x")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"SHOULD-NOT-BE-READ")
    (root / "readme.txt").unlink()
    (root / "readme.txt").symlink_to(outside)

    text, reason = archive.read_source_text(inventory, "readme.txt", source_root=root)
    assert text is None
    assert reason == REFUSAL_SYMLINK


def test_an_undecodable_entry_is_refused_as_undecodable_not_as_unreadable(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "notes.docx").write_bytes(b"PK\x03\x04\x00\x00\x00binary-office-file")
    inventory = archive.inventory_folder(root, root_label="x")
    assert len(inventory.entries) == 1

    text, reason = archive.read_source_text(inventory, "notes.docx", source_root=root)
    assert text is None
    assert reason == REFUSAL_UNDECODABLE


@pytest.mark.parametrize("as_zip", [False, True])
def test_read_source_head_is_bounded_and_says_when_it_truncated(tmp_path, as_zip):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "big").write_bytes(b"#F big\n" + b"x" * 50_000)
    (root / "small").write_bytes(b"#F small\n")
    if as_zip:
        source = tmp_path / "c.zip"
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(root / "big", "big")
            zf.write(root / "small", "small")
        inventory = archive.inventory_zip(source, root_label="x")
    else:
        source = root
        inventory = archive.inventory_folder(root, root_label="x")

    limits = ArchiveLimits(head_bytes=64)
    head, reason = archive.read_source_head(inventory, "big", source_root=source, limits=limits)
    assert reason is None
    assert len(head) <= 64
    assert head.startswith("#F big")

    decoded, reason = archive.read_source_decoded(
        inventory, "big", source_root=source, limits=limits, head_only=True
    )
    assert reason is None and decoded.truncated is True

    decoded, reason = archive.read_source_decoded(
        inventory, "small", source_root=source, limits=limits, head_only=True
    )
    assert reason is None and decoded.truncated is False
    assert decoded.text == "#F small\n"


def test_the_first_line_is_what_distinguishes_a_macro_from_an_acquisition(tmp_path):
    """The classifier's whole job, and why a head read exists.

    ``run29`` and ``alignment`` both have no extension and are different KINDS; in
    the real corpus ``alignment`` is 1.6 MB, so reading it whole to learn its first
    line would be the wrong shape.
    """
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "runsynth").write_bytes(b"qdo Synth_XAS.mac\nnewfile 01_x\n" + b"# pad\n" * 500)
    (root / "alignsynth").write_bytes(b"#F alignsynth\n#E 4102444800\n" + b"1 2\n" * 500)
    inventory = archive.inventory_folder(root, root_label="x")
    limits = ArchiveLimits(head_bytes=32)

    macro, _ = archive.read_source_head(inventory, "runsynth", source_root=root, limits=limits)
    acquisition, _ = archive.read_source_head(
        inventory, "alignsynth", source_root=root, limits=limits
    )
    assert macro.splitlines()[0] == "qdo Synth_XAS.mac"
    assert acquisition.splitlines()[0] == "#F alignsynth"


# --- nothing is executed -----------------------------------------------------


def test_the_module_states_that_nothing_is_executed_and_imports_nothing_that_could(tmp_path):
    """A ``.mac`` is text. Asserted over the module's own source, not its docstring.

    The docstring claim is checked too, because a future reader looking for the
    boundary reads the docstring first — but the load-bearing half is the absence of
    any execution primitive in the source.
    """
    source = Path(archive.__file__).read_text(encoding="utf-8")
    assert "NOTHING IN THIS MODULE IS EVER EXECUTED" in archive.__doc__
    assert "A ``.mac`` file is SPEC macro source" in archive.__doc__

    # Comments and docstrings legitimately contain the word "exec" in prose, so the
    # assertion is over CALL shapes and IMPORTS, not over the substring.
    import ast

    tree = ast.parse(source)
    forbidden_modules = {"subprocess", "pty", "shlex", "importlib", "runpy", "ctypes"}
    # Split by CALL SHAPE, because `re.compile` is an attribute call and is
    # entirely legitimate while a bare `compile(...)` is not.
    forbidden_bare = {"eval", "exec", "compile", "__import__"}
    forbidden_attrs = {
        "system",
        "popen",
        "execv",
        "execve",
        "spawnv",
        "spawnl",
        "check_output",
        "check_call",
        "Popen",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_modules, alias.name
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") not in forbidden_modules, node.module
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_bare, node.func.id
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_attrs, node.func.attr

    # And a macro really is read as text, with its commands intact and inert.
    root = tmp_path / "corpus"
    _small_tree(root)
    inventory = archive.inventory_folder(root, root_label="x")
    text, reason = archive.read_source_text(inventory, "run01.mac", source_root=root)
    assert reason is None
    assert text.splitlines()[0] == "newfile 01_SYNTH_sampleA"


# --- the real corpus, when the reader holds it ------------------------------

_CORPUS_DIR = os.environ.get("ISAAC_BL15_CORPUS_DIR")
_CORPUS_ZIP = os.environ.get("ISAAC_BL15_CORPUS_ZIP")
_NO_CORPUS = (
    "the real BL15-2 corpus is not committed (CLAUDE.md §6); set "
    "ISAAC_BL15_CORPUS_DIR / ISAAC_BL15_CORPUS_ZIP to a copy you hold to run this"
)


@pytest.mark.skipif(not _CORPUS_DIR, reason=_NO_CORPUS)
def test_no_absolute_path_reaches_a_source_record_over_the_real_corpus_walk():
    root = Path(_CORPUS_DIR)
    if not root.is_dir():
        pytest.skip(f"{_CORPUS_DIR} is not a directory")
    inventory = archive.inventory_folder(root, root_label="BL15-2 real corpus")

    assert inventory.entries, "the walk found nothing"
    root_text = str(root)
    for entry in inventory.entries:
        assert not entry.archive_path.startswith(("/", "\\"))
        assert root_text not in entry.archive_path
        assert ".." not in entry.archive_path.split("/")
        assert entry.parent_dir == "" or not entry.parent_dir.startswith("/")
    # And no absolute path hides in a refusal detail either.
    for refusal in inventory.refused:
        assert root_text not in refusal["detail"]
        assert root_text not in refusal["archive_path"]


@pytest.mark.skipif(
    not (_CORPUS_DIR and _CORPUS_ZIP), reason=_NO_CORPUS
)
def test_the_real_corpus_and_its_zip_inventory_identically():
    root, zip_path = Path(_CORPUS_DIR), Path(_CORPUS_ZIP)
    if not root.is_dir() or not zip_path.is_file():
        pytest.skip("the corpus paths do not both exist")
    folder = archive.inventory_folder(root, root_label="same")
    from_zip = archive.inventory_zip(zip_path, root_label="same")
    assert {e.archive_path: e.content_sha256 for e in folder.entries} == {
        e.archive_path: e.content_sha256 for e in from_zip.entries
    }
    assert folder.duplicate_groups == from_zip.duplicate_groups
    assert folder.total_bytes == from_zip.total_bytes
    assert json.dumps(folder.to_state(), sort_keys=True) == json.dumps(
        from_zip.to_state(), sort_keys=True
    )


# --- the inventory's own state shape ----------------------------------------


def test_to_state_is_a_summary_and_never_carries_an_entry_path_list(tmp_path):
    root = tmp_path / "corpus"
    _small_tree(root)
    state = archive.inventory_folder(root, root_label="my import").to_state()
    assert set(state) == {
        "root_label",
        "entry_count",
        "total_bytes",
        "refused",
        "truncated_reason",
        "duplicate_group_count",
    }
    assert state["root_label"] == "my import"
    assert state["entry_count"] == 8
    assert state["duplicate_group_count"] == 2
    # `root_label` is the scientist's label and never a filesystem path.
    assert str(root) not in json.dumps(state)


def test_an_empty_folder_is_an_empty_inventory_not_an_error(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    inventory = archive.inventory_folder(root, root_label="x")
    assert inventory.entries == ()
    assert inventory.refused == ()
    assert inventory.total_bytes == 0
    assert inventory.truncated_reason is None
    assert inventory.duplicate_groups == ()


def test_an_empty_zip_is_an_empty_inventory_not_an_error(tmp_path):
    zip_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zip_path, "w"):
        pass
    inventory = archive.inventory_zip(zip_path, root_label="x")
    assert inventory.entries == ()
    assert inventory.refused == ()
    assert inventory.truncated_reason is None


def test_a_zip_directory_entry_is_not_an_inventory_entry(tmp_path):
    zip_path = tmp_path / "dirs.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("folder/", b"")
        zf.writestr("folder/file.txt", b"x")
    inventory = archive.inventory_zip(
        zip_path, root_label="x", strip_common_root=False
    )
    assert [e.archive_path for e in inventory.entries] == ["folder/file.txt"]
    assert inventory.refused == ()
