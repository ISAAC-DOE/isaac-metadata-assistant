"""A ZIP given AS THE ROOT of ``isaac import`` is read by the generic readers, and a ZIP of a folder
imports exactly as the folder does. SYNTHETIC files only: every name below is invented
(``SAMPLEX``, ``SAMPLEY``, ``XXCALIB``, ``SYNBT``; element ``Zz``/``Xx``; dated 2025/2099).

What these pin:

* the members the generic readers see are the ENGINE's members of that ZIP, under the engine's own
  relative paths (the member path, a "compress this folder" wrapper stripped, no ``<zip>!/``), so the
  engine's ``skip`` set, the bundle's sources and every generic claim are one set of strings;
* folder vs ZIP-of-that-folder parity (an SSRL XDC 4.0 ``_A`` series with ``binary/`` companions, a 2.0
  bare series, a calibration reference, an XDI file, a Larch session, an Athena ``.prj`` that
  ``process`` reads later): the same runs, run ids, candidates, missing values, questions and groups —
  only the fields that name the source kind differ;
* ``__MACOSX/`` is left out as the engine leaves it out; an AppleDouble ``._`` file outside it is an
  ordinary file in both;
* the engine's guards apply (``..`` member, oversized member, too many members, a corrupt member), the
  import continues past them, and a staged member whose bytes differ is never read;
* a ZIP among the top-level ZIP's members is not opened (the engine does not open it either);
* the staging directory is gone afterwards, even when a reader raises.

A folder import is unchanged: ``test_local_import_xdc_v2_and_bare_names.py::
test_every_id_the_build_before_gave_stands_and_new_ones_only_follow`` pins folder imports' ids against the
build before, and ``test_local_import_nested_zip.py`` pins a folder holding a ZIP (and, in
``test_a_zip_root_import_is_unchanged_a_zip_member_that_is_a_zip_stays_a_plain_entry``, the engine's
walk of a ZIP root); both run unchanged. The parity tests below import every folder through the
unchanged folder path.
"""

from __future__ import annotations

import copy
import gzip
import json
import os
import zipfile
from pathlib import Path

import pytest

import isaac_api.historical_import as hist
from isaac_api.bl15 import archive
from isaac_api.bl15.inventory import ArchiveLimits
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli, readers
from isaac_api.local_import import grouping as G
from isaac_api.local_import.readers import Limits

from test_local_import_reader_larch_session import make_session_text
from test_local_import_reader_ssrl_xdc import make_scan
from test_local_import_reader_two_column import make_two
from test_local_import_reader_xdi import make_xdi
from test_local_import_xdc_v2_and_bare_names import BINARY_V2, BINARY_V4, make_v2

APPLEDOUBLE = b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        synthetic resource fork"


# --- fixtures ---------------------------------------------------------------------------------------------------


def beamtime(src: Path) -> Path:
    """A synthetic SSRL beamtime folder that exercises every generic reader the parity has to cover."""
    # an SSRL XDC 4.0 `_A` series with its companions and binary originals
    make_scan(src / "SAMPLEX_A.001", free_text=("0.1 M KOH, pH 13, -0.3 V vs RHE",))
    make_scan(src / "SAMPLEX_A.002", free_text=("0.1 M KOH, pH 13, -0.3 V vs RHE",), timestamp="Sun Jul 27 14:31:47 2025")
    (src / "SAMPLEX.rgn").write_text("r")
    (src / "SAMPLEX.det").write_text("d")
    (src / "SAMPLEX.exp").write_text("COMMENTS1 synthetic\nDATA_FILE SAMPLEX\n")
    (src / "binary").mkdir()
    (src / "binary" / "SAMPLEX.001").write_bytes(BINARY_V4)
    (src / "binary" / "SAMPLEX.002").write_bytes(BINARY_V4)
    # a 2.0 bare series in a sub-folder, with a binary original beside it
    make_v2(src / "sub" / "SAMPLEY_040.001", timestamp="Sun May 17 16:21:05 2099", free_text=("E = 0.7 V vs RHE",))
    make_v2(src / "sub" / "SAMPLEY_040.002", timestamp="Sun May 17 16:41:05 2099")
    (src / "sub" / "binary").mkdir()
    (src / "sub" / "binary" / "SAMPLEY_040.001").write_bytes(BINARY_V2)
    # a calibration reference
    make_v2(src / "XXCALIB_901.001", timestamp="Sun May 17 15:00:00 2099")
    # a file and a folder whose names sort differently as paths and as folder entries ("b" < "b.txt" < "b/")
    make_scan(src / "b" / "SAMPLEW_A.001", timestamp="Mon Jul 28 10:00:00 2025")
    make_two(src / "b.txt")
    # an XDI file, a Larch session and an Athena project (read later by `process`, unread at import)
    make_xdi(src / "proc" / "SAMPLEZ.nor")
    (src / "proc" / "SAMPLEZ.larix").write_bytes(gzip.compress(make_session_text().encode()))
    (src / "proc" / "SYN_project.prj").write_bytes(gzip.compress(b"synthetic athena project, not a real one"))
    (src / "notes.txt").write_text("synthetic notes, not data\n")
    return src


def zip_of(folder: Path, dest: Path, *, wrapper: str | None = None, extra: dict[str, bytes] | None = None,
           compression: int = zipfile.ZIP_DEFLATED) -> Path:
    """A ZIP holding every file of ``folder``, under ``wrapper/`` when given ("compress this folder")."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=compression) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                rel = path.relative_to(folder).as_posix()
                zf.write(path, f"{wrapper}/{rel}" if wrapper else rel)
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return dest


def run_import(root: Path, out: Path, capsys=None) -> dict:
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    if capsys is not None:
        capsys.readouterr()
    data = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    assert B.validate_bundle(data) == []
    return data


#: Fields that legitimately differ between a folder and a ZIP of it: they name the source and the moment.
def comparable(bundle: dict, *, drop_unread: tuple[str, ...] = ()) -> dict:
    b = copy.deepcopy(bundle)
    for key in ("bundle_id", "created_utc", "source_root"):
        b.pop(key)
    b["experiment"].pop("label")
    b["validation"]["bundle_schema"].pop("checked_utc")
    if drop_unread:
        kept = [u for u in b["unread_files"] if u["relative_path"] not in drop_unread]
        dropped = len(b["unread_files"]) - len(kept)
        b["unread_files"] = kept
        b["counts"]["unread_files"] -= dropped
        b["readiness"]["blocking"]["unread_files"] -= dropped
    return b


def same_groups_but_for_the_label(zipped: dict, folder: dict) -> bool:
    """The proposed record groups are the same groups. Their ids are NOT: a group id hashes the experiment key,
    which is ``source_root.label`` (``SYNBT.zip`` vs ``SYNBT``; ``grouping.experiment_key_of``), as it already did
    for a ZIP of an engine-read beamtime. So the ids are re-derived from the folder's key before comparing."""
    zk, fk = G.experiment_key_of(zipped), G.experiment_key_of(folder)
    assert zk != fk
    zg, fg = G.propose_record_groups(zipped), G.propose_record_groups(folder)
    assert zg and len(zg) == len(fg)
    text = json.dumps(zg, sort_keys=True)
    for g in zg:
        assert g["group_id"] == G.group_id_for(zk, g["member_run_keys"])
        text = text.replace(g["group_id"], G.group_id_for(fk, g["member_run_keys"]))
    text = text.replace(json.dumps(zk), json.dumps(fk))
    return json.loads(text) == json.loads(json.dumps(fg, sort_keys=True))


def unread(bundle: dict) -> dict:
    return {u["relative_path"]: u for u in bundle["unread_files"]}


# --- the member-path convention ---------------------------------------------------------------------------------


def test_the_generic_readers_see_the_engines_paths_for_a_wrapped_zip(tmp_path):
    src = beamtime(tmp_path / "src" / "SYNBT")
    z = zip_of(src, tmp_path / "zips" / "SYNBT.zip", wrapper="SYNBT")
    reading, _ = hist.read_local_archive(z, source_id="x")
    engine_paths = [m["archive_path"] for m in reading.manifest]
    assert "SAMPLEX_A.001" in engine_paths and "sub/SAMPLEY_040.001" in engine_paths
    assert not any(p.startswith("SYNBT/") or "!/" in p for p in engine_paths)
    u = readers.collect_all_generic_zip(z)
    claimed = [c["relative_path"] for c in u.claims]
    assert claimed and set(claimed) <= set(engine_paths)
    assert set(claimed) | set(u.unclaimed) == set(engine_paths)
    assert u.nested_zips == [] and u.staging_failures == []
    # the same strings, in the same order, as the folder's own generic walk
    f = readers.collect_all_generic(src)
    assert u.claims == f.claims and u.unclaimed == f.unclaimed
    assert [r.run_key for r in u.runs] == [r.run_key for r in f.runs] and u.late_run_keys == f.late_run_keys


def test_files_are_offered_in_the_folder_walks_order_not_string_order(tmp_path):
    src = beamtime(tmp_path / "src" / "SYNBT")
    z = zip_of(src, tmp_path / "SYNBT.zip")
    staged: list[list[str]] = []
    real = readers._collect

    def spy(base, files, *a, **kw):
        staged.append([rel for rel, _p, _s in files])
        return real(base, files, *a, **kw)

    readers._collect = spy
    try:
        readers.collect_all_generic(src)
        readers.collect_all_generic_zip(z)
    finally:
        readers._collect = real
    folder_order, zip_order = staged
    assert zip_order == folder_order
    assert zip_order.index("b/SAMPLEW_A.001") < zip_order.index("b.txt")  # "b" < "b.txt", unlike sorted(paths)


# --- parity -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("wrapper", [None, "SYNBT"], ids=["flat", "one-top-level-folder"])
def test_a_zip_of_a_folder_imports_exactly_as_the_folder(tmp_path, capsys, wrapper):
    src = beamtime(tmp_path / "src" / "SYNBT")
    folder = run_import(src, tmp_path / "out-folder", capsys)
    z = zip_of(src, tmp_path / "zips" / "SYNBT.zip", wrapper=wrapper)
    zipped = run_import(z, tmp_path / "out-zip", capsys)

    # what the scientist cares about, spelled out
    assert [(r["run_id"], r["run_key"], r["stem"]) for r in zipped["runs"]] == [
        (r["run_id"], r["run_key"], r["stem"]) for r in folder["runs"]]
    stems = {r["stem"] for r in folder["runs"]}
    assert {"SAMPLEX", "SAMPLEY_040", "XXCALIB_901", "SAMPLEW"} <= stems
    assert [(c["candidate_id"], c["run_id"], c["target_field_path"], c["value"]) for c in zipped["candidates"]] == [
        (c["candidate_id"], c["run_id"], c["target_field_path"], c["value"]) for c in folder["candidates"]]
    assert [m["value_id"] for m in zipped["missing_values"]] == [m["value_id"] for m in folder["missing_values"]]
    assert [q["question_id"] for q in zipped["questions"]] == [q["question_id"] for q in folder["questions"]]
    assert [s["relative_path"] for s in zipped["sources"]] == [s["relative_path"] for s in folder["sources"]]
    assert same_groups_but_for_the_label(zipped, folder)
    assert zipped["processed_outputs"] == folder["processed_outputs"] and folder["processed_outputs"]
    # the analysis file and the Athena project are what they are in the folder
    by_path = {s["relative_path"]: s for s in zipped["sources"]}
    assert by_path["proc/SAMPLEZ.larix"]["reader"]["reader_id"] == "larch_session_v1"
    assert unread(zipped)["proc/SYN_project.prj"] == unread(folder)["proc/SYN_project.prj"]
    # and everything else, field for field
    assert comparable(zipped) == comparable(folder)
    assert zipped["source_root"]["kind"] == "zip" and folder["source_root"]["kind"] == "folder"
    assert zipped["source_root"]["label"] == "SYNBT.zip"


def test_without_the_generic_readers_the_zip_imported_no_runs(tmp_path, capsys, monkeypatch):
    """The defect, stated: with the generic readers left out of a ZIP root (the build before), the same ZIP imports
    none of these runs; the engine alone reads none of them."""
    src = beamtime(tmp_path / "src" / "SYNBT")
    z = zip_of(src, tmp_path / "SYNBT.zip", wrapper="SYNBT")
    fixed = run_import(z, tmp_path / "out-fixed", capsys)
    assert len(fixed["runs"]) >= 4
    monkeypatch.setattr(readers, "collect_all_generic_zip", lambda *_a, **_kw: None)
    assert run_import(z, tmp_path / "out-before", capsys)["runs"] == []


# --- __MACOSX/ and AppleDouble ----------------------------------------------------------------------------------


def test_macosx_is_left_out_and_an_appledouble_file_is_ordinary_in_both(tmp_path, capsys):
    src = beamtime(tmp_path / "src" / "SYNBT")
    (src / "._SAMPLEX_A.001").write_bytes(APPLEDOUBLE)  # copied through a FAT volume: a file in the folder
    folder = run_import(src, tmp_path / "out-folder", capsys)
    scan = (src / "SAMPLEX_A.001").read_bytes()
    z = zip_of(src, tmp_path / "SYNBT.zip", wrapper="SYNBT", extra={
        "__MACOSX/SYNBT/._SAMPLEX_A.001": APPLEDOUBLE,
        "__MACOSX/SYNBT/sub/._SAMPLEY_040.001": APPLEDOUBLE,
        # a readable scan inside __MACOSX/ is still Finder's tree: never read, by the engine or the readers
        "__MACOSX/SYNBT/SAMPLEV_A.001": scan,
        "SYNBT/.DS_Store": b"\x00\x00\x00\x01Bud1synthetic",
    })
    zipped = run_import(z, tmp_path / "out-zip", capsys)
    rows = unread(zipped)
    assert rows["__MACOSX/"]["reason_code"] == "operating_system_metadata"
    assert ".DS_Store" in rows
    assert not any(s["relative_path"].startswith("__MACOSX") for s in zipped["sources"])
    assert "SAMPLEV" not in {r["stem"] for r in zipped["runs"]}
    assert "._SAMPLEX_A.001" in {s["relative_path"] for s in zipped["sources"]}
    assert unread(zipped)["._SAMPLEX_A.001"] == unread(folder)["._SAMPLEX_A.001"]
    assert comparable(zipped, drop_unread=("__MACOSX/", ".DS_Store")) == comparable(folder)


# --- the engine's guards ----------------------------------------------------------------------------------------


def test_a_traversal_member_is_refused_by_both_and_the_import_continues(tmp_path, capsys):
    src = beamtime(tmp_path / "src" / "SYNBT")
    scan = (src / "SAMPLEX_A.001").read_bytes()
    folder = run_import(src, tmp_path / "out-folder", capsys)
    z = zip_of(src, tmp_path / "SYNBT.zip", extra={"../SAMPLEU_A.001": scan, "/abs/SAMPLET_A.001": scan})
    u = readers.collect_all_generic_zip(z)
    assert {r["reason"] for r in u.refused} >= {"path_traversal", "absolute_path"}
    assert not any("SAMPLEU" in c["relative_path"] or "SAMPLET" in c["relative_path"] for c in u.claims)
    zipped = run_import(z, tmp_path / "out-zip", capsys)
    assert {r["stem"] for r in zipped["runs"]} == {r["stem"] for r in folder["runs"]}
    assert not any("SAMPLEU" in s["relative_path"] or "SAMPLET" in s["relative_path"] for s in zipped["sources"])
    hostile = [u for u in zipped["unread_files"] if u["relative_path"] not in unread(folder)]
    assert len(hostile) == 2 and {u["reason_code"] for u in hostile} >= {"path_traversal"}
    assert not any("SAMPLEU" in str(u) or "SAMPLET" in str(u) for u in hostile)  # names withheld (§8)
    assert comparable(zipped, drop_unread=tuple(u["relative_path"] for u in hostile)) == comparable(folder)


def _refusals(rows) -> set[tuple[str, str]]:
    return {(str(r.get("archive_path") if "archive_path" in r else r.get("relative_path")), r["reason"]) for r in rows}


def test_small_limits_refuse_exactly_what_the_engine_walk_refuses(tmp_path):
    src = beamtime(tmp_path / "src" / "SYNBT")
    make_scan(src / "big" / "SAMPLEBIG_A.001", points=400)  # the one oversized member
    z = zip_of(src, tmp_path / "SYNBT.zip", wrapper="SYNBT")
    big = (src / "big" / "SAMPLEBIG_A.001").stat().st_size
    for small in (
        ArchiveLimits(max_entry_bytes=big - 1),
        ArchiveLimits(max_entries=5),
        ArchiveLimits(max_total_bytes=4000),
    ):
        engine = archive.inventory_zip(z, root_label="SYNBT.zip", limits=small, refuse_duplicates=True)
        u = readers.collect_all_generic_zip(z, limits=Limits(archive=small))
        assert _refusals(u.refused) == _refusals(engine.refused) and engine.refused
        assert {rel for rel in u.unclaimed} | {c["relative_path"] for c in u.claims} == {e.archive_path for e in engine.entries}
    oversize = readers.collect_all_generic_zip(z, limits=Limits(archive=ArchiveLimits(max_entry_bytes=big - 1)))
    assert ("big/SAMPLEBIG_A.001", "entry_too_large") in _refusals(oversize.refused)
    assert "SAMPLEBIG" not in {r.label for r in oversize.runs} and "SAMPLEX" in {r.label for r in oversize.runs}


def _corrupt_member(z: Path, name: str) -> None:
    """Flip one byte of a STORED member's data, so its CRC no longer matches."""
    with zipfile.ZipFile(z) as zf:
        info = zf.getinfo(name)
    raw = bytearray(z.read_bytes())
    name_len = int.from_bytes(raw[info.header_offset + 26 : info.header_offset + 28], "little")
    extra_len = int.from_bytes(raw[info.header_offset + 28 : info.header_offset + 30], "little")
    at = info.header_offset + 30 + name_len + extra_len + 40
    raw[at] ^= 0xFF
    z.write_bytes(bytes(raw))


def test_a_corrupt_member_is_refused_like_the_engine_and_the_rest_imports(tmp_path, capsys):
    src = beamtime(tmp_path / "src" / "SYNBT")
    z = zip_of(src, tmp_path / "SYNBT.zip", compression=zipfile.ZIP_STORED)
    _corrupt_member(z, "XXCALIB_901.001")
    engine = archive.inventory_zip(z, root_label="SYNBT.zip", refuse_duplicates=True)
    assert ("XXCALIB_901.001", "unreadable") in _refusals(engine.refused)
    u = readers.collect_all_generic_zip(z)
    assert _refusals(u.refused) == _refusals(engine.refused)
    assert "XXCALIB_901.001" not in {c["relative_path"] for c in u.claims} | set(u.unclaimed)
    zipped = run_import(z, tmp_path / "out", capsys)
    stems = {r["stem"] for r in zipped["runs"]}
    assert "XXCALIB_901" not in stems and {"SAMPLEX", "SAMPLEY_040", "SAMPLEW"} <= stems


def test_staged_bytes_that_differ_from_the_walk_are_never_read(tmp_path, capsys, monkeypatch):
    src = beamtime(tmp_path / "src" / "SYNBT")
    z = zip_of(src, tmp_path / "SYNBT.zip", wrapper="SYNBT")
    real = archive.iter_zip_member_bytes

    def tampered(path, members, limits=ArchiveLimits()):
        for member, data in real(path, members, limits):
            if member == "SYNBT/XXCALIB_901.001":
                yield member, data + b"tampered"
            elif member == "SYNBT/notes.txt":
                yield member, None
            else:
                yield member, data

    monkeypatch.setattr(readers._archive, "iter_zip_member_bytes", tampered)
    u = readers.collect_all_generic_zip(z)
    assert {f["relative_path"]: f["reason"].split(";")[0] for f in u.staging_failures} == {
        "XXCALIB_901.001": "the staged bytes do not match the digest the walk recorded",
        "notes.txt": "the member could not be read again for the generic readers",
    }
    assert "XXCALIB_901" not in {r.label for r in u.runs}
    zipped = run_import(z, tmp_path / "out", capsys)
    assert unread(zipped)["XXCALIB_901.001"]["reason_code"] == "member_not_staged"
    assert "XXCALIB_901" not in {r["stem"] for r in zipped["runs"]}


# --- a ZIP inside the top-level ZIP -----------------------------------------------------------------------------


def test_a_zip_among_the_members_is_not_opened_like_the_engine(tmp_path, capsys):
    src = beamtime(tmp_path / "src" / "SYNBT")
    inner = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("SAMPLEIN_A.001", (src / "SAMPLEX_A.001").read_bytes())
    z = zip_of(src, tmp_path / "SYNBT.zip", wrapper="SYNBT", extra={"SYNBT/sub/Box.zip": inner.read_bytes()})
    reading, _ = hist.read_local_archive(z, source_id="x")
    engine_paths = {m["archive_path"] for m in reading.manifest}
    assert "sub/Box.zip" in engine_paths and not any("!/" in p for p in engine_paths)
    u = readers.collect_all_generic_zip(z)
    assert u.nested_zips == [] and "sub/Box.zip" in u.unclaimed
    assert not any("!/" in c["relative_path"] for c in u.claims)
    zipped = run_import(z, tmp_path / "out", capsys)
    assert "SAMPLEIN" not in {r["stem"] for r in zipped["runs"]}
    assert "sub/Box.zip" in unread(zipped)
    assert not any("!/" in s["relative_path"] for s in zipped["sources"])


# --- the staging directory --------------------------------------------------------------------------------------


def _spy_staging(monkeypatch) -> list[Path]:
    seen: list[Path] = []
    real = readers._zip_root_members

    def spy(zip_path, staging, *a, **kw):
        seen.append(Path(staging))
        out = real(zip_path, staging, *a, **kw)
        assert out and all(Path(p).is_file() and Path(p).is_relative_to(Path(staging).resolve()) for _r, p, _s in out)
        assert {Path(p).parent.name for _r, p, _s in out} == {"z0001"}
        assert all(Path(p).name.startswith("m") for _r, p, _s in out)
        return out

    monkeypatch.setattr(readers, "_zip_root_members", spy)
    return seen


def test_the_staging_directory_is_removed_afterwards(tmp_path, capsys, monkeypatch):
    src = beamtime(tmp_path / "src" / "SYNBT")
    z = zip_of(src, tmp_path / "SYNBT.zip", wrapper="SYNBT")
    seen = _spy_staging(monkeypatch)
    run_import(z, tmp_path / "out", capsys)
    assert len(seen) == 1 and not seen[0].exists()
    assert sorted(os.listdir(tmp_path)) == ["SYNBT.zip", "out", "src"]  # nothing written beside the source


def test_the_staging_directory_is_removed_when_a_reader_raises(tmp_path, monkeypatch):
    src = beamtime(tmp_path / "src" / "SYNBT")
    z = zip_of(src, tmp_path / "SYNBT.zip")
    seen = _spy_staging(monkeypatch)

    def boom(*_a, **_kw):
        raise RuntimeError("synthetic reader failure")

    monkeypatch.setattr(readers.xdi, "collect_from_files", boom)
    with pytest.raises(RuntimeError, match="synthetic reader failure"):
        readers.collect_all_generic_zip(z)
    assert len(seen) == 1 and not seen[0].exists()


def test_a_root_that_is_not_a_regular_zip_file_is_refused(tmp_path):
    with pytest.raises(ValueError, match="existing file that is not a symlink"):
        readers.collect_all_generic_zip(tmp_path / "missing.zip")
    z = zip_of(beamtime(tmp_path / "src"), tmp_path / "a.zip")
    link = tmp_path / "link.zip"
    link.symlink_to(z)
    with pytest.raises(ValueError, match="existing file that is not a symlink"):
        readers.collect_all_generic_zip(link)
