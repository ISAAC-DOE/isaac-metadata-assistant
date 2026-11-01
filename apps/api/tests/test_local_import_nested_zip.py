"""A ``.zip`` found INSIDE a folder import is walked one level deep, through the SAME guarded ZIP
walk a top-level ZIP import gets. SYNTHETIC archives only (``FAKE_SAMPLE``, element ``Xx``)."""

from __future__ import annotations

import json
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path

import pytest

import isaac_api.historical_import as hist
import isaac_api.workspace as ws
from isaac_api.bl15 import archive
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli, readers
from isaac_api.local_import.readers import larch_session as L

from test_local_import_reader_igor_pxp import make_pxp
from test_local_import_reader_larch_session import make_session_text
from test_local_import_reader_xdi import make_xdi

SEMANTICS = ws.REPO_ROOT / "tests/fixtures/bl15/semantics/multi_operator_corpus"


def make_zip(path: Path, members: dict[str, bytes | str], *, stored: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    kind = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(path, "w", compression=kind) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def xdi_bytes(tmp_path: Path) -> bytes:
    return make_xdi(tmp_path / "scratch.nor").read_bytes()


def run_import(tmp_path: Path, root: Path, capsys, name: str = "out") -> tuple[Path, dict]:
    out = tmp_path / name
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    capsys.readouterr()
    return out, json.loads((out / "bundle.json").read_text(encoding="utf-8"))


def unread(bundle: dict) -> dict[str | None, dict]:
    return {u["relative_path"]: u for u in bundle["unread_files"]}


# --- the walk reuses the top-level ZIP's guards -----------------------------------------------------


def test_members_are_inventoried_under_names_that_name_the_archive(tmp_path):
    folder = tmp_path / "bt"
    make_zip(folder / "d" / "Box.zip", {"a.txt": "FAKE_SAMPLE", "sub/b.txt": "second"})
    inventory, containers = archive.expand_nested_zips(archive.inventory_folder(folder, root_label="bt"), folder)
    paths = [e.archive_path for e in inventory.entries]
    assert paths == ["d/Box.zip", "d/Box.zip!/a.txt", "d/Box.zip!/sub/b.txt"]
    member = inventory.by_path()["d/Box.zip!/sub/b.txt"]
    assert member.basename == "b.txt" and member.parent_dir == "d/Box.zip!/sub" and member.depth == 3
    assert containers["d/Box.zip"].walked and containers["d/Box.zip"].member_count == 2
    # a member is read through the guarded reader, and only if the walk accepted it
    text, refusal = archive.read_source_text(inventory, "d/Box.zip!/sub/b.txt", source_root=folder)
    assert (text, refusal) == ("second", None)
    assert archive.read_source_text(inventory, "d/Box.zip!/not-there.txt", source_root=folder)[1] == "unreadable"


def test_the_hosted_walk_does_not_open_nested_zips_unless_asked(tmp_path):
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {"a.txt": "x"})
    assert [e.archive_path for e in hist._inventory_of(folder, root_label="bt").entries] == ["Box.zip"]
    nested = hist._inventory_of(folder, root_label="bt", nested_archives=True)
    assert [e.archive_path for e in nested.entries] == ["Box.zip", "Box.zip!/a.txt"]


def test_a_traversal_member_is_refused_and_its_name_is_withheld_in_the_bundle(tmp_path, capsys):
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {"../../escape.txt": "x", "ok.txt": "FAKE_SAMPLE"})
    out, bundle = run_import(tmp_path, folder, capsys)
    assert B.validate_bundle(bundle) == []
    rows = [u for u in bundle["unread_files"] if u["reason_code"] == "path_traversal"]
    assert len(rows) == 1 and rows[0]["relative_path"] is None and "escape.txt" not in rows[0]["reason"]
    assert "Box.zip!/ok.txt" in {s["relative_path"] for s in bundle["sources"]}
    assert not (tmp_path / "escape.txt").exists() and not (folder.parent / "escape.txt").exists()


def test_an_absolute_member_is_refused(tmp_path):
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {"/abs/evil.txt": "x", "ok.txt": "y"})
    inventory, _ = archive.expand_nested_zips(archive.inventory_folder(folder, root_label="bt"), folder)
    assert [r["reason"] for r in inventory.refused] == ["absolute_path"]
    assert [e.archive_path for e in inventory.entries] == ["Box.zip", "Box.zip!/ok.txt"]


def test_an_oversized_member_is_refused_by_its_declared_size(tmp_path):
    folder = tmp_path / "bt"
    # compressible enough to fit the folder walk's own ceiling, below the 1000:1 ratio bound,
    # and 9 MB once declared: refused by size, not by ratio
    block = bytes(range(256)) * 4
    make_zip(folder / "Box.zip", {"big.bin": block * 8_800, "ok.txt": "y"})
    assert (folder / "Box.zip").stat().st_size < 1_000_000
    inventory, _ = archive.expand_nested_zips(archive.inventory_folder(folder, root_label="bt"), folder)
    rows = {r["archive_path"]: r for r in inventory.refused}
    assert rows["Box.zip!/big.bin"]["reason"] == "entry_too_large" and "8000000" in rows["Box.zip!/big.bin"]["detail"]
    assert "ratio" not in rows["Box.zip!/big.bin"]["detail"]
    assert "Box.zip!/ok.txt" in inventory.by_path()


def test_a_compression_ratio_bomb_member_is_refused(tmp_path, capsys):
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {"zeros.txt": b"\0" * 6_000_000, "ok.txt": "FAKE_SAMPLE"})
    out, bundle = run_import(tmp_path, folder, capsys)
    assert unread(bundle)["Box.zip!/zeros.txt"]["reason_code"] == "compression_ratio"
    assert B.validate_bundle(bundle) == []


def test_a_symlink_member_is_refused_not_followed(tmp_path):
    folder = tmp_path / "bt"
    folder.mkdir()
    with zipfile.ZipFile(folder / "Box.zip", "w") as zf:
        info = zipfile.ZipInfo("link.txt")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
        zf.writestr("ok.txt", "y")
    inventory, _ = archive.expand_nested_zips(archive.inventory_folder(folder, root_label="bt"), folder)
    assert [(r["archive_path"], r["reason"]) for r in inventory.refused] == [("Box.zip!/link.txt", "symlink")]


def test_depth_is_one_a_zip_inside_a_zip_is_listed_unread_and_never_opened(tmp_path, capsys):
    folder = tmp_path / "bt"
    inner = make_zip(tmp_path / "inner.zip", {"deep.txt": "FAKE_SAMPLE"}).read_bytes()
    make_zip(folder / "Outer.zip", {"Inner.zip": inner, "top.txt": "y"})
    out, bundle = run_import(tmp_path, folder, capsys)
    row = unread(bundle)["Outer.zip!/Inner.zip"]
    assert row["reason_code"] == "nested_archive_too_deep" and "one level" in row["reason"]
    paths = {s["relative_path"] for s in bundle["sources"]}
    assert "Outer.zip!/top.txt" in paths and not any("deep.txt" in p for p in paths)
    assert B.validate_bundle(bundle) == []


def test_a_zip_that_will_not_open_stays_unread_with_the_walks_reason(tmp_path, capsys):
    folder = tmp_path / "bt"
    folder.mkdir()
    (folder / "Broken.zip").write_bytes(b"PK\x03\x04 this is not really a zip")
    out, bundle = run_import(tmp_path, folder, capsys)
    row = unread(bundle)["Broken.zip"]
    assert row["reason_code"] == "reader_refused" and "could not be opened" in row["reason"]
    src = next(s for s in bundle["sources"] if s["relative_path"] == "Broken.zip")
    assert src["reader"]["content_read"] is False and src["reader"]["reader_id"] == archive.NESTED_ZIP_READER_ID


def test_nested_zips_share_the_folders_entry_budget(tmp_path):
    folder = tmp_path / "bt"
    for i in range(3):
        make_zip(folder / f"Box{i}.zip", {f"m{j}.txt": "x" for j in range(4)})
    limits = archive.ArchiveLimits(max_entries=8)
    inventory, containers = archive.expand_nested_zips(
        archive.inventory_folder(folder, root_label="bt", limits=limits), folder, limits=limits
    )
    assert len(inventory.entries) <= 8 and inventory.truncated_reason == "too_many_entries"
    assert any(r["reason"] == "too_many_entries" for r in inventory.refused)


# --- members are read exactly as loose files are -----------------------------------------------------------


def test_a_corpus_in_a_zip_reconstructs_the_same_runs_as_the_same_corpus_loose(tmp_path, capsys):
    loose = tmp_path / "loose"
    shutil.copytree(SEMANTICS, loose)
    zipped = tmp_path / "zipped"
    zipped.mkdir()
    with zipfile.ZipFile(zipped / "Box.zip", "w") as zf:
        for p in sorted(SEMANTICS.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(SEMANTICS).as_posix())
    _, a = run_import(tmp_path, loose, capsys, "a")
    _, b = run_import(tmp_path, zipped, capsys, "b")
    assert len(a["runs"]) == len(b["runs"]) > 0
    assert sorted(r["stem"] for r in a["runs"]) == sorted(r["stem"] for r in b["runs"])
    assert B.validate_bundle(b) == []
    container = next(s for s in b["sources"] if s["relative_path"] == "Box.zip")
    assert container["reader"]["reader_id"] == "nested_zip_walk_v1" and container["reader"]["content_read"] is True
    assert "Box.zip" not in unread(b)
    assert {"reader_id": "nested_zip_walk_v1", "version": "1"} in b["generator"]["readers"]


def test_athena_exports_in_a_zip_become_processed_outputs_exactly_as_loose_ones_do(tmp_path, capsys):
    data = xdi_bytes(tmp_path)
    loose = tmp_path / "loose"
    (loose / "d").mkdir(parents=True)
    (loose / "d" / "FAKE_one.nor").write_bytes(data)
    zipped = tmp_path / "zipped"
    make_zip(zipped / "d" / "Box.zip", {"FAKE_one.nor": data})
    _, a = run_import(tmp_path, loose, capsys, "a")
    _, b = run_import(tmp_path, zipped, capsys, "b")
    assert a["counts"]["processed_output_files"] == b["counts"]["processed_output_files"] == 1
    assert [f["relative_path"] for po in b["processed_outputs"] for f in po["files"]] == ["d/Box.zip!/FAKE_one.nor"]
    assert b["runs"] == [] and a["runs"] == []
    assert "d/Box.zip!/FAKE_one.nor" not in unread(b)
    assert B.validate_bundle(b) == []


def test_analysis_files_inside_a_nested_zip_are_read_and_are_never_runs(tmp_path, capsys):
    folder = tmp_path / "bt"
    session = make_session_text().encode()
    import gzip

    make_zip(folder / "Box.zip", {"s.larix": gzip.compress(session), "e.pxp": make_pxp()})
    out, bundle = run_import(tmp_path, folder, capsys)
    by_path = {s["relative_path"]: s for s in bundle["sources"]}
    assert by_path["Box.zip!/s.larix"]["reader"]["reader_id"] == "larch_session_v1"
    assert by_path["Box.zip!/e.pxp"]["reader"]["reader_id"] == "igor_pxp_v1"
    assert unread(bundle) == {}
    assert bundle["runs"] == [] and bundle["processed_outputs"] == [] and bundle["record_groups"] == []
    assert cli.main(["bundle", "check", str(out)]) == 0


def test_staging_is_deleted_before_the_collection_returns(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {"FAKE_one.nor": xdi_bytes(tmp_path)})
    collection = readers.collect_all_generic(folder)
    assert [c["relative_path"] for c in collection.claims] == ["Box.zip!/FAKE_one.nor"]
    assert list(scratch.iterdir()) == []
    assert collection.nested_zips == [
        {"relative_path": "Box.zip", "walked": True, "members": 1, "refused": 0, "detail": ""}
    ]


def test_a_directory_whose_name_merely_contains_a_bang_is_not_a_nested_zip(tmp_path):
    folder = tmp_path / "bt"
    (folder / "Hello!").mkdir(parents=True)
    (folder / "Hello!" / "a.txt").write_text("FAKE_SAMPLE")
    inventory, containers = archive.expand_nested_zips(archive.inventory_folder(folder, root_label="bt"), folder)
    assert containers == {} and archive.split_nested_path("Hello!/a.txt") is None
    assert archive.read_source_text(inventory, "Hello!/a.txt", source_root=folder) == ("FAKE_SAMPLE", None)
    assert archive.split_nested_path("a/B.ZIP!/c/d.txt") == ("a/B.ZIP", "c/d.txt")


def test_a_zip_root_import_is_unchanged_a_zip_member_that_is_a_zip_stays_a_plain_entry(tmp_path):
    inner = make_zip(tmp_path / "i.zip", {"x.txt": "y"}).read_bytes()
    outer = make_zip(tmp_path / "Outer.zip", {"Inner.zip": inner, "t.txt": "z"})
    names = [e.archive_path for e in hist._inventory_of(outer, root_label="Outer.zip").entries]
    assert names == ["Inner.zip", "t.txt"]


def test_the_new_readers_import_only_the_standard_library():
    """CI does not install the `processing` extra: neither reader may import numpy or larch."""
    import ast
    import isaac_api.local_import.readers as pkg

    allowed = {"__future__", "json", "re", "struct", "zlib", "pathlib", "typing", "_common"}
    for name in ("larch_session", "igor_pxp"):
        tree = ast.parse((Path(pkg.__file__).parent / f"{name}.py").read_text())
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                roots.add("_common" if node.level and node.module == "_common" else (node.module or "").split(".")[0])
        assert roots <= allowed, (name, roots - allowed)
    assert L.READER_ID == "larch_session_v1" and archive.NESTED_ZIP_READER_ID == "nested_zip_walk_v1"


# --- review round: staging, collisions, duplicates, cache, budget ------------------------------------------


def _claimed(collection) -> list[str]:
    return sorted(c["relative_path"] for c in collection.claims)


def test_a_member_called_x_beside_x_slash_y_does_not_crash_staging(tmp_path, capsys):
    data = xdi_bytes(tmp_path)
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {"x": data, "x/y": data})
    collection = readers.collect_all_generic(folder)
    assert _claimed(collection) == ["Box.zip!/x", "Box.zip!/x/y"] and collection.staging_failures == []
    out, bundle = run_import(tmp_path, folder, capsys)  # the whole import must not raise
    assert B.validate_bundle(bundle) == []


def test_a_name_segment_longer_than_the_file_system_allows_does_not_crash_the_import(tmp_path, capsys):
    data = xdi_bytes(tmp_path)
    long_name = "n" * 300 + ".nor"
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {long_name: data, "ok.nor": data})
    out, bundle = run_import(tmp_path, folder, capsys)
    assert B.validate_bundle(bundle) == []
    files = [f["relative_path"] for po in bundle["processed_outputs"] for f in po["files"]]
    assert f"Box.zip!/{long_name}" in files and "Box.zip!/ok.nor" in files


def test_a_member_that_cannot_be_staged_is_reported_and_the_import_continues(tmp_path, capsys, monkeypatch):
    data = xdi_bytes(tmp_path)
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {"bad.nor": data, "good.nor": data})
    real = Path.write_bytes

    def flaky(self, payload):
        if self.name.endswith("000001.nor"):
            raise OSError(36, "File name too long")
        return real(self, payload)

    monkeypatch.setattr(Path, "write_bytes", flaky)
    out, bundle = run_import(tmp_path, folder, capsys)
    assert B.validate_bundle(bundle) == []
    row = unread(bundle)["Box.zip!/bad.nor"]
    assert row["reason_code"] == "member_not_staged" and "could not be staged" in row["reason"]
    assert "Box.zip!/good.nor" not in unread(bundle)


def test_members_that_differ_only_by_case_or_unicode_form_stage_at_distinct_paths(tmp_path):
    import unicodedata

    folder = tmp_path / "bt"
    nfc, nfd = unicodedata.normalize("NFC", "café.txt"), unicodedata.normalize("NFD", "café.txt")
    make_zip(folder / "Box.zip", {"A.txt": "UPPER", "a.txt": "lower", nfc: "composed", nfd: "decomposed"})
    staging = tmp_path / "stage"
    staging.mkdir()
    out = readers._expand_nested_zips(
        [("Box.zip", folder / "Box.zip", (folder / "Box.zip").stat().st_size)], staging, readers.Limits(), [], [], []
    )
    members = [(rel, path) for rel, path, _ in out if "!/" in rel]
    assert len(members) == 4
    folded = {unicodedata.normalize("NFC", str(p.relative_to(staging))).lower() for _, p in members}
    assert len(folded) == 4, "a case-insensitive or normalising volume would merge two of these"
    for rel, path in members:
        assert path.read_text() == {"A.txt": "UPPER", "a.txt": "lower", nfc: "composed", nfd: "decomposed"}[rel.split("!/")[1]]
        assert path.suffix == ".txt"


def test_staged_bytes_that_do_not_match_the_walks_digest_are_refused_not_read(tmp_path, monkeypatch):
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {"FAKE_one.nor": xdi_bytes(tmp_path)})
    real = Path.write_bytes
    monkeypatch.setattr(Path, "write_bytes", lambda self, data: real(self, data[:-1] + b"?"))
    collection = readers.collect_all_generic(folder)
    assert collection.claims == [] and collection.runs == []
    assert [f["relative_path"] for f in collection.staging_failures] == ["Box.zip!/FAKE_one.nor"]
    assert "do not match" in collection.staging_failures[0]["reason"]


def test_a_member_written_twice_or_spelled_two_ways_is_refused_not_a_bundle_crash(tmp_path, capsys):
    import warnings

    folder = tmp_path / "bt"
    folder.mkdir()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # zipfile warns about the duplicate name it is asked to write
        with zipfile.ZipFile(folder / "Box.zip", "w") as zf:
            zf.writestr("a.txt", "FIRST")
            zf.writestr("a.txt", "SECOND")
            zf.writestr("./b.txt", "B1")
            zf.writestr("b.txt", "B2")
            zf.writestr("fine.txt", "FAKE_SAMPLE")
    out, bundle = run_import(tmp_path, folder, capsys)  # exit 0, not 5
    assert B.validate_bundle(bundle) == []
    rows = [u for u in bundle["unread_files"] if u["reason_code"] == "duplicate_path"]
    assert sorted(u["relative_path"] for u in rows) == ["Box.zip!/a.txt", "Box.zip!/a.txt", "Box.zip!/b.txt", "Box.zip!/b.txt"]
    paths = [s["relative_path"] for s in bundle["sources"]]
    assert "Box.zip!/fine.txt" in paths and "Box.zip!/a.txt" not in paths and "Box.zip!/b.txt" not in paths
    assert len(paths) == len(set(paths))


def test_a_real_folder_named_like_a_nested_path_wins_and_the_member_is_refused(tmp_path, capsys):
    folder = tmp_path / "bt"
    make_zip(folder / "a.zip", {"m.txt": "FROM THE ZIP"})
    (folder / "a.zip!").mkdir()
    (folder / "a.zip!" / "m.txt").write_text("FROM THE FOLDER")
    out, bundle = run_import(tmp_path, folder, capsys)
    assert B.validate_bundle(bundle) == []
    paths = [s["relative_path"] for s in bundle["sources"]]
    assert paths.count("a.zip!/m.txt") == 1
    assert unread(bundle)["a.zip!/m.txt"]["reason_code"] == "duplicate_path"


def test_a_zip_root_import_with_a_duplicate_member_no_longer_fails_but_the_hosted_default_is_unchanged(tmp_path, capsys):
    import warnings

    path = tmp_path / "Box.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("a.txt", "FIRST")
            zf.writestr("a.txt", "SECOND")
            zf.writestr("ok.txt", "FAKE_SAMPLE")
    assert [e.archive_path for e in hist._inventory_of(path, root_label="Box.zip").entries].count("a.txt") == 2
    out, bundle = run_import(tmp_path, path, capsys)
    assert B.validate_bundle(bundle) == []
    assert [u["reason_code"] for u in bundle["unread_files"] if u["relative_path"] == "a.txt"] == ["duplicate_path"] * 2


def test_reading_many_members_indexes_the_zip_once_not_once_per_read(tmp_path, monkeypatch):
    n = 400
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {f"d/s{i:04d}.txt": f"line {i}\n" for i in range(n)})
    inventory, _ = archive.expand_nested_zips(archive.inventory_folder(folder, root_label="bt"), folder)
    archive.close_nested_cache()
    calls = {"n": 0}
    real = archive._normalise_member_name

    def counting(raw, limits):
        calls["n"] += 1
        return real(raw, limits)

    monkeypatch.setattr(archive, "_normalise_member_name", counting)
    for e in inventory.entries[1:101]:
        assert archive.read_source_text(inventory, e.archive_path, source_root=folder)[1] is None
    assert calls["n"] <= 2 * n, f"{calls['n']} name normalisations for 100 reads of a {n}-member ZIP"
    archive.close_nested_cache()


def test_the_local_reading_closes_the_zips_its_reads_kept_open(tmp_path):
    folder = tmp_path / "bt"
    make_zip(folder / "Box.zip", {"a.txt": "FAKE_SAMPLE"})
    hist.read_local_archive(folder, source_id="src-test")
    assert archive._NESTED_CACHE == {}


def test_a_symlink_spelled_like_a_nested_path_is_reported_as_a_symlink(tmp_path):
    folder = tmp_path / "bt"
    (folder / "Box.zip!").mkdir(parents=True)
    (folder / "Box.zip!" / "y.txt").write_text("FAKE_SAMPLE")
    inventory = archive.inventory_folder(folder, root_label="bt")
    assert "Box.zip!/y.txt" in inventory.by_path()
    outside = tmp_path / "outside.txt"
    outside.write_text("elsewhere")
    (folder / "Box.zip!" / "y.txt").unlink()
    (folder / "Box.zip!" / "y.txt").symlink_to(outside)
    assert archive.read_source_text(inventory, "Box.zip!/y.txt", source_root=folder) == (None, "symlink")


def test_the_generic_staging_budget_is_the_engines_budget(tmp_path):
    folder = tmp_path / "bt"
    (folder).mkdir()
    (folder / "big.bin").write_bytes(b"\x01" * 1000)
    make_zip(folder / "Box.zip", {"m.txt": "x" * 600}, stored=True)
    zip_size = (folder / "Box.zip").stat().st_size
    arch = archive.ArchiveLimits(max_total_bytes=1000 + zip_size + 300)  # 300 bytes left for members
    inventory, containers = archive.expand_nested_zips(
        archive.inventory_folder(folder, root_label="bt", limits=arch), folder, limits=arch
    )
    assert not [e for e in inventory.entries if "!/" in e.archive_path]
    collection = readers.collect_all_generic(folder, readers.Limits(archive=arch))
    assert collection.nested_zips[0]["members"] == 0 and collection.nested_zips[0]["refused"] >= 1
    roomy = archive.ArchiveLimits(max_total_bytes=1000 + zip_size + 700)
    again = readers.collect_all_generic(folder, readers.Limits(archive=roomy))
    assert again.nested_zips[0]["members"] == 1
