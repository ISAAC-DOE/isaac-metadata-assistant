"""Make the files ``isaac import`` could not read readable for Claude, with provenance.

``isaac import`` writes ``unread_files.json``: every file no deterministic reader handled.
Real beamtime folders hold Word and PowerPoint documents (with figures embedded in them),
spreadsheets, PDFs, images and instrument binaries. This module turns each of those into
something a later, local Claude Code step can read, and says exactly what it did and did
not do. It reads on the scientist's machine, imports no web framework, opens no network
connection and executes nothing it reads.

WHAT IT PRODUCES (one manifest per file; ``extract_source``)
============================================================
Every manifest carries ``source_relative_path``, ``source_sha256``, ``extractor``,
``extractor_version`` and a ``truncation`` block of counters: *nothing is ever cut without
a counter saying how much*. ``status`` is one of:

* ``extracted``     text and/or embedded images were pulled out; ``read_with`` is
  ``extractor`` for the text and ``claude_read_tool`` for each written image.
* ``read_with_claude`` the file itself is something Claude Code's Read tool opens natively
  (a PDF, a PNG/JPEG/TIFF/HEIC, or a plain-text file of any extension). ``page_ranges`` splits
  a PDF into runs of at most 20 pages. A text file gets a bounded head preview and a line
  count; whether it IS text is decided by two mechanical tests (no NUL byte in the first
  8 KiB, and it decodes as UTF-8), never by what its extension or contents seem to mean.
* ``unreadable``    this build cannot read it; ``reason`` and the size say why. NEVER a guess:
  an unknown binary is not described, summarised or sniffed beyond its leading bytes. A zip
  archive is listed (names and sizes, bounded) but never extracted.
* ``refused``       a safety bound stopped the read (size, member count, a bad zip member);
  ``refusals`` names what and why.

Formats: ``.docx`` / ``.pptx`` (text in reading order, tables as rows, every embedded image
with sha256, position and alt text/caption), ``.xlsx`` (sheets, dimensions, a bounded cell
preview, formulas as formulas, merged ranges; a sheet cut at the preview bound says in its ``read_rest``
exactly how to page the rest with ``--sheet``/``--rows-offset``/``--rows-limit``), ``.pdf`` (page count and metadata only),
images (dimensions where cheap), everything else unreadable.

WHAT IT WILL NOT DO
===================
* It never follows an external relationship (a linked image, a hyperlink target, an OLE
  link): they are counted and their targets are not recorded or opened.
* It never extracts a zip member by the name the archive gave it. Images are written under
  names this module generates (``<n>_<sha8>.<ext>``) inside one directory per source, so a
  ``../`` member cannot write anywhere, and a member with an absolute or escaping name,
  a duplicate name, an encryption flag, or a size or ratio past the bound is refused and
  counted with its name withheld.
* It never loads an unbounded document: every limit is a field of :class:`Limits`, appears
  in the manifest's ``limits`` block, and each cut is counted in ``truncation``.
* It does not interpret science. Alt text and captions are copied as the document wrote
  them, and the extracted text is source evidence, not a value.

Reading XML here uses the standard library parser after refusing any part that declares a
DOCTYPE or an ENTITY (the entity-expansion attacks), on top of the size caps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zipfile
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from xml.etree import ElementTree as ET

EXTRACTOR_ID = "isaac-local-extract"
EXTRACTOR_VERSION = "1.0.0"

READ_WITH_EXTRACTOR = "extractor"
READ_WITH_CLAUDE = "claude_read_tool"

STATUS_EXTRACTED = "extracted"
STATUS_READ_WITH_CLAUDE = "read_with_claude"
STATUS_UNREADABLE = "unreadable"
STATUS_REFUSED = "refused"

#: Pages per slice handed to Claude Code's Read tool (it reads at most 20 per request).
PDF_PAGES_PER_RANGE = 20

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".heic")
#: Formats Claude Code's Read tool opens as an image. Others found embedded in a document
#: (EMF, WMF, SVG, ...) are written out but flagged as needing conversion.
CLAUDE_READABLE_IMAGE_FORMATS = frozenset({"png", "jpeg", "gif", "webp"})


@dataclass(frozen=True)
class Limits:
    """Every bound this module applies. Published in each manifest under ``limits``."""

    max_source_bytes: int = 1 << 30  # 1 GiB: the whole file
    max_hash_bytes: int = 4 << 30  # a file past this is not hashed (sha256 null, said so)
    max_zip_members: int = 5_000
    max_zip_total_uncompressed: int = 1 << 30
    max_xml_member_bytes: int = 64 << 20
    max_image_bytes: int = 128 << 20
    max_images: int = 500
    max_total_image_bytes: int = 1 << 30
    max_compression_ratio: int = 2_000  # only enforced for members over 1 MiB
    max_blocks: int = 5_000  # paragraphs + tables (docx) / text shapes + tables (pptx)
    max_text_chars: int = 400_000  # total characters returned for one document
    max_paragraph_chars: int = 20_000
    max_table_rows: int = 200
    max_table_cols: int = 50
    max_cell_chars: int = 2_000
    max_slides: int = 500
    max_sheets: int = 25
    max_preview_rows: int = 50
    max_page_rows: int = 500  # the most rows one page of a sheet returns (``--rows-limit``)
    max_preview_cols: int = 30
    max_preview_cell_chars: int = 500
    max_merged_ranges: int = 200
    max_merge_scan_bytes: int = 64 << 20
    pdf_scan_bytes: int = 32 << 20  # head+tail scanned for metadata; objects streams bounded
    pdf_objstm_inflate_bytes: int = 8 << 20
    pdf_max_object_streams: int = 400
    pdf_max_page_ranges: int = 200
    text_sniff_bytes: int = 8192
    max_text_preview_lines: int = 40
    max_text_preview_line_chars: int = 300
    max_text_count_bytes: int = 64 << 20
    max_archive_listing_names: int = 100
    max_archive_members_scanned: int = 20_000


DEFAULT_LIMITS = Limits()


# --- small helpers --------------------------------------------------------------------------


def _sha256_file(path: Path, limits: Limits) -> tuple[str | None, int]:
    """Stream the file. Returns ``(hexdigest or None, size)``; ``None`` past the hash bound."""
    size = path.stat().st_size
    if size > limits.max_hash_bytes:
        return None, size
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest(), size


def _clip(text: str, limit: int, counters: dict[str, int], key: str) -> str:
    """``text`` cut to ``limit`` characters, counting what was cut under ``key``."""
    if len(text) <= limit:
        return text
    counters[key] = counters.get(key, 0) + (len(text) - limit)
    return text[:limit]


def _new_manifest(path: Path, rel: str, kind: str, digest: str | None, size: int, limits: Limits) -> dict:
    return {
        "source_relative_path": rel,
        "source_sha256": digest,
        "source_size_bytes": size,
        "source_extension": path.suffix.lower(),
        "kind": kind,
        "status": STATUS_UNREADABLE,
        "read_with": None,
        "extractor": EXTRACTOR_ID,
        "extractor_version": EXTRACTOR_VERSION,
        "truncation": {},
        "refusals": [],
        "limits": asdict(limits),
        "notes": [],
    }


def _refuse(manifest: dict, code: str, detail: str) -> None:
    manifest["refusals"].append({"code": code, "detail": detail})


def _safe_relative(raw: Any) -> str | None:
    """A path usable as a source label, or ``None`` when it is absolute or escapes."""
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        return None
    p = PurePosixPath(raw)
    if p.is_absolute() or any(part in ("..",) for part in p.parts):
        return None
    return str(p)


# --- zip safety -----------------------------------------------------------------------------


class _SafeZip:
    """A zip opened for bounded, name-safe reading. Members are only ever READ, never
    extracted by name; every refusal is recorded on the manifest with the name withheld."""

    def __init__(self, path: Path, manifest: dict, limits: Limits) -> None:
        self.manifest = manifest
        self.limits = limits
        self.zf = zipfile.ZipFile(path)
        self.members: dict[str, zipfile.ZipInfo] = {}
        self._admit()

    def close(self) -> None:
        self.zf.close()

    def _admit(self) -> None:
        infos = self.zf.infolist()
        m, lim = self.manifest, self.limits
        trunc = m["truncation"]
        if len(infos) > lim.max_zip_members:
            trunc["zip_members_not_admitted"] = len(infos) - lim.max_zip_members
            _refuse(
                m,
                "too_many_members",
                f"the archive holds {len(infos)} members; only the first {lim.max_zip_members} were considered",
            )
            infos = infos[: lim.max_zip_members]
        total = 0
        for info in infos:
            name = info.filename
            if info.is_dir():
                continue
            safe = _safe_relative(name)
            if safe is None or name != safe:
                _refuse(m, "unsafe_member_name", "a member whose name is absolute, escapes the archive, or is not plain was refused; its name is withheld")
                continue
            if safe in self.members:
                _refuse(m, "duplicate_member_name", "a second member with an already-seen name was refused; its name is withheld")
                continue
            if info.flag_bits & 0x1:
                _refuse(m, "encrypted_member", "an encrypted member was refused; nothing was read from it")
                continue
            if info.file_size > lim.max_image_bytes and not safe.lower().endswith(".xml"):
                _refuse(m, "member_too_large", f"a member declares {info.file_size} bytes, over the {lim.max_image_bytes}-byte bound")
                continue
            if info.file_size > lim.max_xml_member_bytes and safe.lower().endswith((".xml", ".rels")):
                _refuse(m, "member_too_large", f"an XML member declares {info.file_size} bytes, over the {lim.max_xml_member_bytes}-byte bound")
                continue
            if info.file_size > (1 << 20) and info.compress_size > 0 and info.file_size / info.compress_size > lim.max_compression_ratio:
                _refuse(m, "compression_ratio", "a member's compression ratio is past the bound; it was refused unread")
                continue
            total += info.file_size
            if total > lim.max_zip_total_uncompressed:
                _refuse(m, "archive_too_large", "the declared uncompressed total is past the bound; later members were refused")
                trunc["zip_members_not_admitted"] = trunc.get("zip_members_not_admitted", 0) + 1
                continue
            self.members[safe] = info

    def read(self, name: str, cap: int) -> bytes | None:
        """The member's bytes, or ``None`` if absent or refused. A member that inflates past
        ``cap`` (a header that lied about its size) is refused, not truncated."""
        info = self.members.get(name)
        if info is None:
            return None
        try:
            with self.zf.open(info) as fh:
                data = fh.read(cap + 1)
        except (zipfile.BadZipFile, RuntimeError, OSError, zlib.error) as exc:
            _refuse(self.manifest, "member_unreadable", f"a member could not be read ({type(exc).__name__})")
            return None
        if len(data) > cap:
            _refuse(self.manifest, "member_inflated_past_bound", "a member inflated past its bound and was refused")
            return None
        return data

    def xml(self, name: str) -> ET.Element | None:
        data = self.read(name, self.limits.max_xml_member_bytes)
        if data is None:
            return None
        head = data[:4096].upper()
        if b"<!DOCTYPE" in head or b"<!ENTITY" in data[:65536].upper():
            _refuse(self.manifest, "xml_declares_entities", "an XML part declares a DOCTYPE or ENTITY and was not parsed")
            return None
        try:
            return ET.fromstring(data)
        except ET.ParseError:
            _refuse(self.manifest, "xml_not_well_formed", "an XML part was not well-formed and was not read")
            return None


# --- XML namespaces and relationships -------------------------------------------------------

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "v": "urn:schemas-microsoft-com:vml",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
}


def _q(prefix: str, local: str) -> str:
    return f"{{{NS[prefix]}}}{local}"


def _relationships(zs: _SafeZip, rels_name: str, base_dir: str, counters: dict[str, int]) -> dict[str, dict]:
    """``{relationship id: {"target": archive path, "type": ...}}`` for INTERNAL targets only.

    An ``External`` relationship is counted in ``counters["external_relationships_not_followed"]``
    and its target is dropped, so no URL or UNC path reaches the manifest or is ever opened.
    """
    root = zs.xml(rels_name)
    out: dict[str, dict] = {}
    if root is None:
        return out
    for rel in root.findall(_q("rel", "Relationship")):
        rid = rel.get("Id")
        target = rel.get("Target")
        if not rid or target is None:
            continue
        if (rel.get("TargetMode") or "").lower() == "external":
            counters["external_relationships_not_followed"] = counters.get("external_relationships_not_followed", 0) + 1
            continue
        resolved = _resolve_target(base_dir, target)
        if resolved is None:
            counters["relationship_targets_outside_archive"] = counters.get("relationship_targets_outside_archive", 0) + 1
            continue
        out[rid] = {"target": resolved, "type": (rel.get("Type") or "").rsplit("/", 1)[-1]}
    return out


def _resolve_target(base_dir: str, target: str) -> str | None:
    if "\\" in target or "\x00" in target:
        return None
    if target.startswith("/"):
        parts = target.lstrip("/").split("/")
    else:
        parts = [p for p in base_dir.split("/") if p] + target.split("/")
    stack: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not stack:
                return None
            stack.pop()
        else:
            stack.append(part)
    return "/".join(stack) or None


# --- image bytes: dimensions, format, writing ------------------------------------------------


def _image_format_and_size(data: bytes) -> tuple[str | None, int | None, int | None]:
    """Format by magic bytes and pixel dimensions where they are a few header bytes away."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
            w, h = struct.unpack(">II", data[16:24])
            return "png", w, h
        if data[:3] == b"\xff\xd8\xff":
            return "jpeg", *_jpeg_size(data)
        if data[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", data[6:10])
            return "gif", w, h
        if data[:2] == b"BM" and len(data) >= 26:
            w, h = struct.unpack("<ii", data[18:26])
            return "bmp", abs(w), abs(h)
        if data[:4] in (b"II*\x00", b"MM\x00*"):
            return "tiff", *_tiff_size(data)
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "webp", None, None
        if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
            return "heic", None, None
        if data[:4] == b"\xd7\xcd\xc6\x9a":
            return "wmf", None, None
        if len(data) >= 44 and data[:4] == b"\x01\x00\x00\x00" and data[40:44] == b" EMF":
            return "emf", None, None
        head = data[:512].lstrip().lower()
        if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:2048].lower()):
            return "svg", None, None
    except (struct.error, IndexError):
        pass
    return None, None, None


def _jpeg_size(data: bytes) -> tuple[int | None, int | None]:
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xFF:
            i += 1
            continue
        seglen = struct.unpack(">H", data[i + 2 : i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        i += 2 + seglen
    return None, None


def _tiff_size(data: bytes) -> tuple[int | None, int | None]:
    little = data[:2] == b"II"
    e = "<" if little else ">"
    off = struct.unpack(e + "I", data[4:8])[0]
    if off + 2 > len(data):
        return None, None
    count = struct.unpack(e + "H", data[off : off + 2])[0]
    w = h = None
    for k in range(min(count, 64)):
        entry = data[off + 2 + 12 * k : off + 14 + 12 * k]
        if len(entry) < 12:
            break
        tag, typ = struct.unpack(e + "HH", entry[:4])
        if tag in (256, 257):
            val = struct.unpack(e + ("H" if typ == 3 else "I"), entry[8:10] if typ == 3 else entry[8:12])[0]
            if tag == 256:
                w = val
            else:
                h = val
    return w, h


_EXT_FOR_FORMAT = {
    "png": "png", "jpeg": "jpg", "gif": "gif", "bmp": "bmp", "tiff": "tif", "webp": "webp",
    "heic": "heic", "wmf": "wmf", "emf": "emf", "svg": "svg",
}


class _ImageSink:
    """Writes embedded images into ONE directory, under names this module generates."""

    def __init__(self, directory: Path, manifest: dict, limits: Limits) -> None:
        self.directory = directory
        self.manifest = manifest
        self.limits = limits
        self.by_member: dict[str, dict] = {}
        self.skipped: set[str] = set()
        self.images: list[dict] = []
        self.total_bytes = 0

    def add(self, zs: _SafeZip, member: str) -> dict | None:
        """The record for ``member`` (written once, however many places use it), or ``None``."""
        if member in self.by_member:
            return self.by_member[member]
        if member in self.skipped:
            return None  # already refused and counted once; a second reference is not a second loss
        lim, trunc = self.limits, self.manifest["truncation"]
        self.skipped.add(member)
        if len(self.images) >= lim.max_images:
            trunc["images_not_written"] = trunc.get("images_not_written", 0) + 1
            return None
        data = zs.read(member, lim.max_image_bytes)
        if data is None:
            trunc["images_not_written"] = trunc.get("images_not_written", 0) + 1
            return None
        if self.total_bytes + len(data) > lim.max_total_image_bytes:
            trunc["images_not_written"] = trunc.get("images_not_written", 0) + 1
            _refuse(self.manifest, "image_budget", "the total image bytes bound was reached; later images were not written")
            return None
        fmt, w, h = _image_format_and_size(data)
        digest = hashlib.sha256(data).hexdigest()
        ext = _EXT_FOR_FORMAT.get(fmt or "", None)
        if ext is None:
            suffix = PurePosixPath(member).suffix.lower().lstrip(".")
            ext = suffix if re.fullmatch(r"[a-z0-9]{1,5}", suffix or "") else "bin"
        index = len(self.images) + 1
        filename = f"{index:03d}_{digest[:8]}.{ext}"
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / filename).write_bytes(data)
        self.total_bytes += len(data)
        record = {
            "image_id": f"img-{index:03d}",
            "file": f"{self.directory.name}/{filename}",
            "sha256": digest,
            "size_bytes": len(data),
            "format": fmt,
            "width_px": w,
            "height_px": h,
            "archive_member": member,
            "read_with": READ_WITH_CLAUDE if fmt in CLAUDE_READABLE_IMAGE_FORMATS else None,
            "locations": [],
        }
        if record["read_with"] is None:
            record["note"] = (
                "not a format Claude's Read tool opens directly; convert it (for example to PNG) before reading"
                if fmt
                else "format not recognised from its leading bytes; written unread"
            )
        self.skipped.discard(member)
        self.by_member[member] = record
        self.images.append(record)
        return record


# --- text extraction helpers ----------------------------------------------------------------


def _w_paragraph_text(p: ET.Element) -> str:
    out: list[str] = []
    for el in p.iter():
        if el.tag == _q("w", "t"):
            out.append(el.text or "")
        elif el.tag == _q("w", "tab"):
            out.append("\t")
        elif el.tag in (_q("w", "br"), _q("w", "cr")):
            out.append("\n")
    return "".join(out)


def _a_paragraph_text(p: ET.Element) -> str:
    out: list[str] = []
    for el in p.iter():
        if el.tag == _q("a", "t"):
            out.append(el.text or "")
        elif el.tag == _q("a", "br"):
            out.append("\n")
    return "".join(out)


class _TextBudget:
    def __init__(self, limits: Limits, counters: dict[str, int]) -> None:
        self.limits = limits
        self.counters = counters
        self.chars = 0
        self.blocks = 0

    def take_block(self) -> bool:
        if self.blocks >= self.limits.max_blocks:
            self.counters["blocks_not_returned"] = self.counters.get("blocks_not_returned", 0) + 1
            return False
        self.blocks += 1
        return True

    def take_text(self, text: str, per_item_limit: int, key: str) -> str:
        text = _clip(text, per_item_limit, self.counters, key)
        room = self.limits.max_text_chars - self.chars
        if len(text) > room:
            self.counters["text_chars_past_document_bound"] = self.counters.get("text_chars_past_document_bound", 0) + (len(text) - max(room, 0))
            text = text[: max(room, 0)]
        self.chars += len(text)
        return text


def _table_rows(tbl: ET.Element, cell_tag: str, row_tag: str, para_tag: str, text_of, budget: _TextBudget, lim: Limits, counters: dict[str, int]) -> list[list[str]]:
    rows: list[list[str]] = []
    all_rows = [r for r in tbl.iter(row_tag)]
    if len(all_rows) > lim.max_table_rows:
        counters["table_rows_not_returned"] = counters.get("table_rows_not_returned", 0) + (len(all_rows) - lim.max_table_rows)
    for row in all_rows[: lim.max_table_rows]:
        cells = [c for c in row.findall(cell_tag)]
        if len(cells) > lim.max_table_cols:
            counters["table_cols_not_returned"] = counters.get("table_cols_not_returned", 0) + (len(cells) - lim.max_table_cols)
        out_row: list[str] = []
        for cell in cells[: lim.max_table_cols]:
            text = "\n".join(text_of(p) for p in cell.iter(para_tag))
            out_row.append(budget.take_text(text, lim.max_cell_chars, "cell_chars_not_returned"))
        rows.append(out_row)
    return rows


def _alt_of(el: ET.Element | None) -> dict[str, str]:
    """``descr`` / ``title`` / ``name`` of a drawing's non-visual properties, verbatim."""
    out: dict[str, str] = {}
    if el is None:
        return out
    for key in ("descr", "title", "name"):
        value = el.get(key)
        if value:
            out[key] = value[:2000]
    return out


# --- .docx ----------------------------------------------------------------------------------


def _extract_docx(path: Path, manifest: dict, out_dir: Path, limits: Limits) -> None:
    zs = _SafeZip(path, manifest, limits)
    try:
        trunc = manifest["truncation"]
        rels = _relationships(zs, "word/_rels/document.xml.rels", "word", trunc)
        root = zs.xml("word/document.xml")
        if root is None:
            manifest["notes"].append("word/document.xml is absent or was refused; no text was read")
            manifest["status"] = STATUS_REFUSED if manifest["refusals"] else STATUS_UNREADABLE
            manifest["reason"] = "the document body could not be read"
            return
        body = root.find(_q("w", "body"))
        blocks: list[dict] = []
        sink = _ImageSink(out_dir / manifest["_dirname"], manifest, limits)
        budget = _TextBudget(limits, trunc)
        para_index = -1
        table_index = -1
        pending: list[tuple[dict, dict]] = []  # (image record, location) awaiting a caption

        def images_in(el: ET.Element, location: dict) -> list[dict]:
            found: list[dict] = []
            for blip in el.iter(_q("a", "blip")):
                rid = blip.get(_q("r", "embed"))
                link = blip.get(_q("r", "link"))
                if link:
                    trunc["external_images_not_followed"] = trunc.get("external_images_not_followed", 0) + 1
                if not rid:
                    continue
                alt = {}
                for anc in el.iter(_q("wp", "docPr")):
                    alt = _alt_of(anc)
                    break
                found.append(_place_image(sink, zs, rels, rid, location, alt))
            for im in el.iter(_q("v", "imagedata")):
                rid = im.get(_q("r", "id"))
                if rid:
                    found.append(_place_image(sink, zs, rels, rid, location, {"title": im.get("title", "")} if im.get("title") else {}))
            return [f for f in found if f]

        for child in list(body) if body is not None else []:
            if child.tag == _q("w", "p"):
                para_index += 1
                style_el = child.find(f"{_q('w', 'pPr')}/{_q('w', 'pStyle')}")
                style = style_el.get(_q("w", "val")) if style_el is not None else None
                location = {"block_index": len(blocks), "paragraph_index": para_index, "table_index": None}
                imgs = images_in(child, location)
                text = _w_paragraph_text(child)
                if not text.strip() and not imgs:
                    continue
                if not budget.take_block():
                    continue
                block: dict[str, Any] = {
                    "type": "paragraph",
                    "paragraph_index": para_index,
                    "style": style,
                    "text": budget.take_text(text, limits.max_paragraph_chars, "paragraph_chars_not_returned"),
                }
                if imgs:
                    block["images"] = [i["image_id"] for i in imgs]
                    for i in imgs:
                        pending.append((i, location))
                blocks.append(block)
            elif child.tag == _q("w", "tbl"):
                table_index += 1
                location = {"block_index": len(blocks), "paragraph_index": None, "table_index": table_index}
                imgs = images_in(child, location)
                if not budget.take_block():
                    continue
                rows = _table_rows(child, _q("w", "tc"), _q("w", "tr"), _q("w", "p"), _w_paragraph_text, budget, limits, trunc)
                block = {"type": "table", "table_index": table_index, "rows": rows}
                if imgs:
                    block["images"] = [i["image_id"] for i in imgs]
                blocks.append(block)
        # Captions: the text of the ADJACENT block (before or after) when it is a paragraph in a
        # caption style. Adjacent means next to it in reading order, so a table between two
        # paragraphs separates them.
        for record, location in pending:
            at = location["block_index"]
            caption = None
            for neighbour in (at + 1, at - 1):
                nb = blocks[neighbour] if 0 <= neighbour < len(blocks) else None
                if nb and nb["type"] == "paragraph" and (nb.get("style") or "").lower().startswith("caption") and nb["text"].strip():
                    caption = nb["text"]
                    break
            if caption is not None:
                for loc in record["locations"]:
                    if loc["block_index"] == at and "caption" not in loc:
                        loc["caption"] = caption
        # Every other image in word/media, written even if no body paragraph points at it.
        for member in sorted(zs.members):
            if member.startswith("word/media/"):
                sink.add(zs, member)
        for name in sorted(zs.members):
            if re.match(r"word/(header|footer|footnotes|endnotes|comments)\d*\.xml$", name):
                trunc["parts_not_read"] = trunc.get("parts_not_read", 0) + 1
        manifest["blocks"] = blocks
        manifest["images"] = sink.images
        manifest["text_file"] = _write_text(out_dir, manifest, blocks, kind="docx")
        manifest["status"] = STATUS_EXTRACTED
        manifest["read_with"] = READ_WITH_EXTRACTOR
        manifest["counts"] = {
            "paragraphs": para_index + 1,
            "tables": table_index + 1,
            "blocks_returned": len(blocks),
            "images": len(sink.images),
        }
        if trunc.get("parts_not_read"):
            manifest["notes"].append("headers, footers, footnotes, endnotes and comments are not read; their count is in truncation.parts_not_read")
    finally:
        zs.close()


def _place_image(sink: _ImageSink, zs: _SafeZip, rels: dict[str, dict], rid: str, location: dict, alt: dict) -> dict | None:
    rel = rels.get(rid)
    if rel is None:
        sink.manifest["truncation"]["image_references_unresolved"] = sink.manifest["truncation"].get("image_references_unresolved", 0) + 1
        return None
    record = sink.add(zs, rel["target"])
    if record is None:
        return None
    entry = dict(location)
    if alt:
        entry["alt_text"] = alt
    record["locations"].append(entry)
    return record


# --- .pptx ----------------------------------------------------------------------------------


def _extract_pptx(path: Path, manifest: dict, out_dir: Path, limits: Limits) -> None:
    zs = _SafeZip(path, manifest, limits)
    try:
        trunc = manifest["truncation"]
        pres = zs.xml("ppt/presentation.xml")
        prels = _relationships(zs, "ppt/_rels/presentation.xml.rels", "ppt", trunc)
        if pres is None:
            manifest["status"] = STATUS_REFUSED if manifest["refusals"] else STATUS_UNREADABLE
            manifest["reason"] = "ppt/presentation.xml is absent or was refused"
            return
        slide_ids = [el.get(_q("r", "id")) for el in pres.iter(_q("p", "sldId"))]
        order = [prels[rid]["target"] for rid in slide_ids if rid in prels]
        if len(order) > limits.max_slides:
            trunc["slides_not_read"] = len(order) - limits.max_slides
            order = order[: limits.max_slides]
        sink = _ImageSink(out_dir / manifest["_dirname"], manifest, limits)
        budget = _TextBudget(limits, trunc)
        slides: list[dict] = []
        blocks: list[dict] = []
        for number, member in enumerate(order, 1):
            sroot = zs.xml(member)
            if sroot is None:
                trunc["slides_unreadable"] = trunc.get("slides_unreadable", 0) + 1
                continue
            base = str(PurePosixPath(member).parent)
            srels = _relationships(zs, f"{base}/_rels/{PurePosixPath(member).name}.rels", base, trunc)
            shapes: list[dict] = []
            tree = sroot.find(f".//{_q('p', 'spTree')}")

            def walk(node: ET.Element) -> None:
                for el in node:
                    if el.tag == _q("p", "sp"):
                        paras = [_a_paragraph_text(p) for p in el.iter(_q("a", "p"))]
                        text = "\n".join(t for t in paras if t.strip())
                        if text and budget.take_block():
                            cnv = el.find(f"{_q('p', 'nvSpPr')}/{_q('p', 'cNvPr')}")
                            shapes.append({"type": "text", "shape": (cnv.get("name") if cnv is not None else None), "text": budget.take_text(text, limits.max_paragraph_chars, "paragraph_chars_not_returned")})
                    elif el.tag == _q("p", "pic"):
                        cnv = el.find(f"{_q('p', 'nvPicPr')}/{_q('p', 'cNvPr')}")
                        blip = el.find(f".//{_q('a', 'blip')}")
                        if blip is not None:
                            if blip.get(_q("r", "link")):
                                trunc["external_images_not_followed"] = trunc.get("external_images_not_followed", 0) + 1
                            rid = blip.get(_q("r", "embed"))
                            if rid:
                                rec = _place_image(sink, zs, srels, rid, {"slide": number, "shape_index": len(shapes)}, _alt_of(cnv))
                                if rec:
                                    shapes.append({"type": "image", "image_id": rec["image_id"]})
                    elif el.tag == _q("p", "graphicFrame"):
                        tbl = el.find(f".//{_q('a', 'tbl')}")
                        if tbl is not None and budget.take_block():
                            shapes.append({"type": "table", "rows": _table_rows(tbl, _q("a", "tc"), _q("a", "tr"), _q("a", "p"), _a_paragraph_text, budget, limits, trunc)})
                        elif tbl is None:
                            trunc["graphic_frames_not_read"] = trunc.get("graphic_frames_not_read", 0) + 1
                    elif el.tag == _q("p", "grpSp"):
                        walk(el)

            if tree is not None:
                walk(tree)
            notes_text = None
            for rel in srels.values():
                if rel["type"] == "notesSlide":
                    nroot = zs.xml(rel["target"])
                    if nroot is not None:
                        paras = [_a_paragraph_text(p) for p in nroot.iter(_q("a", "p"))]
                        notes_text = budget.take_text("\n".join(t for t in paras if t.strip()), limits.max_paragraph_chars, "paragraph_chars_not_returned") or None
                    break
            slide = {"slide": number, "shapes": shapes}
            if notes_text:
                slide["speaker_notes"] = notes_text
            slides.append(slide)
            blocks.append({"type": "slide", **slide})
        for member in sorted(zs.members):
            if member.startswith("ppt/media/"):
                sink.add(zs, member)
        for name in zs.members:
            if name.startswith(("ppt/charts/", "ppt/embeddings/", "ppt/diagrams/")) and not name.endswith(".rels"):
                trunc["chart_or_embedded_parts_not_read"] = trunc.get("chart_or_embedded_parts_not_read", 0) + 1
        manifest["slides"] = slides
        manifest["images"] = sink.images
        manifest["text_file"] = _write_text(out_dir, manifest, blocks, kind="pptx")
        manifest["status"] = STATUS_EXTRACTED
        manifest["read_with"] = READ_WITH_EXTRACTOR
        manifest["counts"] = {"slides": len(slides), "images": len(sink.images)}
        if trunc.get("chart_or_embedded_parts_not_read"):
            manifest["notes"].append("charts, diagrams and embedded objects are not read; their count is in truncation")
    finally:
        zs.close()


def _write_text(out_dir: Path, manifest: dict, blocks: list[dict], kind: str) -> str | None:
    """A reading-order Markdown rendering of the returned blocks, for the Read tool."""
    lines: list[str] = []
    for b in blocks:
        if b["type"] == "paragraph":
            if b.get("text"):
                lines.append(b["text"])
            for img in b.get("images", []):
                lines.append(f"[image {img}]")
        elif b["type"] == "table":
            lines.append(f"[table {b['table_index']}]")
            for row in b["rows"]:
                lines.append(" | ".join(c.replace("\n", " ") for c in row))
        elif b["type"] == "slide":
            lines.append(f"## Slide {b['slide']}")
            for shape in b["shapes"]:
                if shape["type"] == "text":
                    lines.append(shape["text"])
                elif shape["type"] == "image":
                    lines.append(f"[image {shape['image_id']}]")
                elif shape["type"] == "table":
                    lines.append("[table]")
                    for row in shape["rows"]:
                        lines.append(" | ".join(c.replace("\n", " ") for c in row))
            if b.get("speaker_notes"):
                lines.append(f"(speaker notes) {b['speaker_notes']}")
        lines.append("")
    directory = out_dir / manifest["_dirname"]
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "text.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    return f"{directory.name}/text.md"


# --- .xlsx ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class SheetPage:
    """Which rows of which sheet to return: ``rows_offset`` rows are skipped, then up to ``rows_limit``
    (default ``max_preview_rows``, at most ``max_page_rows``) are returned. ``sheet=None``: every sheet."""

    sheet: str | None = None
    rows_offset: int = 0
    rows_limit: int | None = None


def _extract_xlsx(path: Path, manifest: dict, out_dir: Path, limits: Limits, page: SheetPage | None = None) -> None:
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover - openpyxl is a declared dependency
        manifest["reason"] = "openpyxl is not installed"
        return
    zs = _SafeZip(path, manifest, limits)
    trunc = manifest["truncation"]
    try:
        # Sheet member names and merged ranges are read from the package directly, because a
        # read-only workbook exposes neither merged cells nor the member a sheet lives in.
        wb_xml = zs.xml("xl/workbook.xml")
        wb_rels = _relationships(zs, "xl/_rels/workbook.xml.rels", "xl", trunc)
        sheet_member: dict[str, str] = {}
        hidden: dict[str, str] = {}
        if wb_xml is not None:
            for sh in wb_xml.iter(_q("m", "sheet")):
                name, rid = sh.get("name"), sh.get(_q("r", "id"))
                if name and rid in wb_rels:
                    sheet_member[name] = wb_rels[rid]["target"]
                if name and sh.get("state") in ("hidden", "veryHidden"):
                    hidden[name] = sh.get("state")
        merged_by_sheet: dict[str, Any] = {}
        for name, member in sheet_member.items():
            merged_by_sheet[name] = _merged_ranges(zs, member, limits, trunc)
        sink = _ImageSink(out_dir / manifest["_dirname"], manifest, limits)
        for member in sorted(zs.members):
            if member.startswith("xl/media/"):
                sink.add(zs, member)
        if sink.images:
            manifest["images"] = sink.images
        for name in zs.members:
            if name.startswith(("xl/charts/", "xl/drawings/")) and name.endswith(".xml"):
                trunc["chart_or_drawing_parts_not_read"] = trunc.get("chart_or_drawing_parts_not_read", 0) + 1
        refusals_before = len(manifest["refusals"])
    finally:
        zs.close()

    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # openpyxl warns about extensions it drops; they are not read
            wb = load_workbook(path, read_only=True, data_only=False)
    except Exception as exc:  # noqa: BLE001 - any parse failure is reported, never raised
        manifest["status"] = STATUS_UNREADABLE
        manifest["reason"] = f"openpyxl could not open the workbook ({type(exc).__name__})"
        return
    sheets: list[dict] = []
    page = page or SheetPage()
    offset = max(0, page.rows_offset)
    window = min(page.rows_limit or limits.max_preview_rows, limits.max_page_rows)
    try:
        names = list(wb.sheetnames)
        if page.sheet is not None and page.sheet not in names:
            manifest["status"] = STATUS_REFUSED
            manifest["reason"] = f"the workbook has no sheet named {page.sheet!r}; its sheets: {', '.join(names)}"
            _refuse(manifest, "no_such_sheet", manifest["reason"])
            return
        chosen = [page.sheet] if page.sheet is not None else names[: limits.max_sheets]
        if page.sheet is None and len(names) > limits.max_sheets:
            trunc["sheets_not_read"] = len(names) - limits.max_sheets
        for name in chosen:
            ws = wb[name]
            dims = None
            try:
                dims = ws.calculate_dimension()
            except Exception:  # noqa: BLE001
                dims = None
            rows: list[dict] = []
            cell_trunc = 0
            col_cut = 0
            nonempty_rows = 0
            for r_idx, row in enumerate(ws.iter_rows(min_row=offset + 1, max_row=offset + window, values_only=True), offset + 1):
                if len(row) > limits.max_preview_cols:
                    col_cut += len(row) - limits.max_preview_cols
                cells: list[Any] = []
                for v in row[: limits.max_preview_cols]:
                    cells.append(_cell_value(v, limits, counter=trunc))
                while cells and cells[-1] is None:
                    cells.pop()
                if cells:
                    nonempty_rows += 1
                    rows.append({"row": r_idx, "cells": cells})
            rows_in_sheet = _rows_in(dims)
            rows_cut = max(0, rows_in_sheet - (offset + window)) if rows_in_sheet is not None else None
            if rows_cut:
                trunc["preview_rows_not_returned"] = trunc.get("preview_rows_not_returned", 0) + rows_cut
            last = min(offset + window, rows_in_sheet) if rows_in_sheet is not None else offset + window
            sheets.append(
                {
                    "name": name,
                    "rows_in_sheet": rows_in_sheet,
                    "rows_returned": f"{offset + 1}..{last}" if last > offset else "none",
                    **({"rows_before_this_page": offset} if offset else {}),
                    "preview_rows_not_returned": rows_cut,
                    # A CUT SHEET IS NOT READ: its next page, exactly (``main`` adds the whole command).
                    **({"read_rest": {"sheet": name, "rows_offset": offset + window, "rows_limit": window,
                                      "rows_remaining": rows_cut}} if rows_cut else {}),
                    "state": hidden.get(name, "visible"),
                    "dimensions": dims,
                    "preview_bounds": {"rows": limits.max_preview_rows, "columns": limits.max_preview_cols, "cell_chars": limits.max_preview_cell_chars},
                    **({"header_rows": rows[:3],
                        "header_rows_note": "the first non-empty rows by position; not a claim that they are headers"} if not offset else {}),
                    "preview_rows": rows,
                    "preview_nonempty_rows": nonempty_rows,
                    "preview_columns_not_returned": col_cut,
                    "merged_ranges": merged_by_sheet.get(name),
                    "formulas_shown_as": "formula text beginning with '='; cached results are not read",
                }
            )
            if col_cut:
                trunc["preview_columns_not_returned"] = trunc.get("preview_columns_not_returned", 0) + col_cut
    finally:
        wb.close()
    manifest["sheets"] = sheets
    manifest["status"] = STATUS_EXTRACTED
    manifest["read_with"] = READ_WITH_EXTRACTOR
    manifest["counts"] = {"sheets": len(names), "sheets_returned": len(sheets), "images": len(manifest.get("images") or [])}
    if refusals_before:
        manifest["notes"].append("some package members were refused while reading; see refusals")
    cut = [s for s in sheets if s.get("read_rest")]
    manifest["notes"].append(
        (f"Each sheet's preview is the first {window} rows by {limits.max_preview_cols} columns. " if not offset else
         f"Each sheet returned holds rows {offset + 1}..{offset + window} by {limits.max_preview_cols} columns. ")
        + (f"{len(cut)} sheet(s) are cut, and the rows past the cut are NOT read: page each with --sheet <name> "
           "--rows-offset <read_rest.rows_offset> --rows-limit <read_rest.rows_limit> (each sheet's read_rest says exactly)."
           if cut else "No sheet was cut.")
    )


def _rows_in(dimensions: str | None) -> int | None:
    """The last row number of a dimension string such as ``A1:C5``; ``None`` when unknown."""
    if not dimensions:
        return None
    m = re.search(r"[A-Za-z]+(\d+)(?::[A-Za-z]+(\d+))?$", dimensions)
    if not m:
        return None
    return int(m.group(2) or m.group(1))


def _cell_value(v: Any, limits: Limits, counter: dict[str, int]) -> Any:
    if v is None or isinstance(v, (bool, int)):
        return v
    if isinstance(v, float):
        return v if v == v and v not in (float("inf"), float("-inf")) else str(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    text = v if isinstance(v, str) else f"<{type(v).__name__}>"
    return _clip(text, limits.max_preview_cell_chars, counter, "preview_cell_chars_not_returned")


def _merged_ranges(zs: _SafeZip, member: str, limits: Limits, counters: dict[str, int]) -> Any:
    """Merged ranges of one sheet, read by streaming the sheet XML; bounded and said so."""
    info = zs.members.get(member)
    if info is None:
        return None
    if info.file_size > limits.max_merge_scan_bytes:
        counters["merged_scans_skipped_sheet_too_large"] = counters.get("merged_scans_skipped_sheet_too_large", 0) + 1
        return {"scanned": False, "reason": "sheet XML is larger than the merge-scan bound"}
    ranges: list[str] = []
    total = 0
    try:
        with zs.zf.open(info) as fh:
            head = fh.read(4096)
        if b"<!DOCTYPE" in head.upper() or b"<!ENTITY" in head.upper():
            return {"scanned": False, "reason": "sheet XML declares entities"}
        with zs.zf.open(info) as fh:
            for _event, el in ET.iterparse(fh, events=("end",)):
                if el.tag == _q("m", "mergeCell"):
                    total += 1
                    if len(ranges) < limits.max_merged_ranges:
                        ref = el.get("ref")
                        if ref:
                            ranges.append(ref)
                el.clear()
    except (ET.ParseError, zipfile.BadZipFile, OSError, zlib.error):
        return {"scanned": False, "reason": "sheet XML could not be scanned"}
    if total > len(ranges):
        counters["merged_ranges_not_returned"] = counters.get("merged_ranges_not_returned", 0) + (total - len(ranges))
    return {"scanned": True, "total": total, "ranges": ranges}


# --- .pdf (metadata only) -------------------------------------------------------------------

_PDF_STRING = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>")


def _pdf_decode(raw: bytes) -> str | None:
    """A PDF literal or hex string as text; never guesses past UTF-16BE/PDFDoc(latin-1)."""
    try:
        if raw.startswith(b"("):
            body = raw[1:-1]
            body = re.sub(rb"\\([nrtbf()\\])", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}.get(m.group(1), m.group(1)), body)
            body = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), body)
        else:
            hexed = re.sub(rb"\s", b"", raw[1:-1])
            if len(hexed) % 2:
                hexed += b"0"
            body = bytes.fromhex(hexed.decode("ascii"))
        if body.startswith(b"\xfe\xff"):
            return body[2:].decode("utf-16-be", "replace")
        return body.decode("latin-1")
    except (ValueError, UnicodeDecodeError):
        return None


def _pdf_scan(path: Path, limits: Limits, trunc: dict[str, int]) -> tuple[bytes, bool]:
    """Head and tail of the file (bounded), as one buffer, and whether it was all read."""
    size = path.stat().st_size
    half = limits.pdf_scan_bytes // 2
    with path.open("rb") as fh:
        if size <= limits.pdf_scan_bytes:
            return fh.read(), True
        head = fh.read(half)
        fh.seek(size - half)
        tail = fh.read(half)
    trunc["pdf_bytes_not_scanned"] = size - limits.pdf_scan_bytes
    return head + b"\n" + tail, False


def _pdf_objstm_texts(buf: bytes, limits: Limits, trunc: dict[str, int]) -> list[bytes]:
    """Inflate (bounded) the PDF 1.5 object streams in ``buf`` so a page tree or info
    dictionary held inside one is visible. Nothing else is decoded."""
    out: list[bytes] = []
    count = 0
    for m in re.finditer(rb"/Type\s*/ObjStm", buf):
        if count >= limits.pdf_max_object_streams:
            trunc["pdf_object_streams_not_inflated"] = trunc.get("pdf_object_streams_not_inflated", 0) + 1
            continue
        s = buf.find(b"stream", m.end())
        if s < 0:
            continue
        s += len(b"stream")
        if buf[s : s + 2] == b"\r\n":
            s += 2
        elif buf[s : s + 1] in (b"\n", b"\r"):
            s += 1
        e = buf.find(b"endstream", s)
        if e < 0:
            continue
        count += 1
        d = zlib.decompressobj()
        try:
            out.append(d.decompress(buf[s:e], limits.pdf_objstm_inflate_bytes))
        except zlib.error:
            trunc["pdf_object_streams_not_inflated"] = trunc.get("pdf_object_streams_not_inflated", 0) + 1
    return out


def _extract_pdf(path: Path, manifest: dict, limits: Limits) -> None:
    trunc = manifest["truncation"]
    buf, whole = _pdf_scan(path, limits, trunc)
    if not buf.lstrip()[:5] == b"%PDF-":
        manifest["status"] = STATUS_UNREADABLE
        manifest["reason"] = "the file does not begin with a PDF header"
        return
    version = re.match(rb"%PDF-(\d\.\d)", buf.lstrip())
    haystack = [buf, *_pdf_objstm_texts(buf, limits, trunc)]
    pages: int | None = None
    basis = None
    for chunk in haystack:
        for m in re.finditer(rb"/Linearized\s+[\d.]+.*?/N\s+(\d+)", chunk, re.S):
            n = int(m.group(1))
            if pages is None or n > pages:
                pages, basis = n, "linearization dictionary /N"
        for m in re.finditer(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)|/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", chunk, re.S):
            n = int(m.group(1) or m.group(2))
            if pages is None or n > pages:
                pages, basis = n, "page tree /Count"
    if pages is None:
        counted = sum(len(re.findall(rb"/Type\s*/Page\b(?!s)", c)) for c in haystack)
        if counted:
            pages, basis = counted, "count of /Type /Page objects"
    if not whole and pages is not None:
        manifest["notes"].append("only the head and tail of a large file were scanned, so the page count may be incomplete")
    metadata: dict[str, str] = {}
    for chunk in haystack:
        for key in (b"Title", b"Author", b"Subject", b"Keywords", b"Creator", b"Producer", b"CreationDate", b"ModDate"):
            if key.decode() in metadata:
                continue
            m = re.search(rb"/" + key + rb"\s*(" + _PDF_STRING.pattern + rb")", chunk)
            if m:
                val = _pdf_decode(m.group(1))
                if val:
                    metadata[key.decode()] = val[:500]
    encrypted = bool(re.search(rb"/Encrypt\b", buf))
    manifest["status"] = STATUS_READ_WITH_CLAUDE
    manifest["read_with"] = READ_WITH_CLAUDE
    manifest["pdf"] = {
        "version": version.group(1).decode() if version else None,
        "page_count": pages,
        "page_count_basis": basis,
        "metadata": metadata,
        "encrypted": encrypted,
        "text_extracted": False,
    }
    ranges: list[str] = []
    if pages:
        total_ranges = (pages + PDF_PAGES_PER_RANGE - 1) // PDF_PAGES_PER_RANGE
        for i in range(min(total_ranges, limits.pdf_max_page_ranges)):
            start = i * PDF_PAGES_PER_RANGE + 1
            ranges.append(f"{start}-{min(pages, start + PDF_PAGES_PER_RANGE - 1)}")
        if total_ranges > len(ranges):
            trunc["page_ranges_not_listed"] = total_ranges - len(ranges)
    manifest["page_ranges"] = ranges
    manifest["notes"].append("No text was extracted. Open the PDF with Claude Code's Read tool, at most 20 pages per request, using page_ranges.")
    if encrypted:
        manifest["notes"].append("The PDF declares encryption; the Read tool may not be able to open it.")
    if pages is None:
        manifest["notes"].append("The page count could not be determined from the bytes scanned; it is null, not zero.")


# --- images ---------------------------------------------------------------------------------


def _extract_image(path: Path, manifest: dict) -> None:
    with path.open("rb") as fh:
        head = fh.read(1 << 20)
    fmt, w, h = _image_format_and_size(head)
    manifest["status"] = STATUS_READ_WITH_CLAUDE
    manifest["read_with"] = READ_WITH_CLAUDE
    manifest["image"] = {"format": fmt, "width_px": w, "height_px": h}
    if w is None:
        manifest["notes"].append("dimensions were not available from the file header")
    if path.suffix.lower() in (".tif", ".tiff", ".heic"):
        manifest["notes"].append("Claude's Read tool may not open this format; if it cannot, convert it to PNG first (for example with sips on macOS).")
    if fmt is None:
        manifest["notes"].append("the leading bytes do not match any image format this module recognises; the file is passed on unchanged")


# --- dispatch -------------------------------------------------------------------------------

_DOCX = (".docx",)
_PPTX = (".pptx",)
_XLSX = (".xlsx",)


def _kind_of(ext: str) -> str:
    if ext in _DOCX:
        return "docx"
    if ext in _PPTX:
        return "pptx"
    if ext in _XLSX:
        return "xlsx"
    if ext == ".pdf":
        return "pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "unknown"


def extract_source(
    path: str | Path,
    out_dir: str | Path,
    *,
    source_relative_path: str | None = None,
    limits: Limits = DEFAULT_LIMITS,
    page: SheetPage | None = None,
) -> dict:
    """Read one file into a manifest (and, for documents, text and images under ``out_dir``).

    ``source_relative_path`` is the label the manifest carries; it defaults to the file's
    NAME, never its absolute path. It must be relative and may not contain ``..``.
    Never raises on a bad file: the manifest's ``status`` says what happened.
    """
    src = Path(path)
    out = Path(out_dir)
    rel = source_relative_path if source_relative_path is not None else src.name
    if _safe_relative(rel) is None:
        raise ValueError("source_relative_path must be relative and may not escape the source root")
    if src.is_symlink() or not src.is_file():
        raise ValueError("the source must be an existing regular file (symlinks are not followed)")
    digest, size = _sha256_file(src, limits)
    kind = _kind_of(src.suffix.lower())
    manifest = _new_manifest(src, rel, kind, digest, size, limits)
    if digest is None:
        manifest["notes"].append("the file is larger than the hash bound; source_sha256 is null")
    manifest["_dirname"] = (digest or hashlib.sha256(rel.encode()).hexdigest())[:12]
    if size > limits.max_source_bytes and kind in ("docx", "pptx", "xlsx"):
        manifest["status"] = STATUS_REFUSED
        manifest["reason"] = f"the file is {size} bytes, over the {limits.max_source_bytes}-byte bound for a document"
        _refuse(manifest, "source_too_large", manifest["reason"])
        manifest.pop("_dirname", None)
        return manifest
    try:
        if kind == "docx":
            _extract_docx(src, manifest, out, limits)
        elif kind == "pptx":
            _extract_pptx(src, manifest, out, limits)
        elif kind == "xlsx":
            _extract_xlsx(src, manifest, out, limits, page)
        elif kind == "pdf":
            _extract_pdf(src, manifest, limits)
        elif kind == "image":
            _extract_image(src, manifest)
        elif not _extract_text(src, manifest, limits):
            _unreadable(src, manifest, limits)
    except zipfile.BadZipFile:
        manifest["status"] = STATUS_UNREADABLE
        manifest["reason"] = f"the {kind} file is not a readable zip package"
    except (OSError, ET.ParseError, ValueError, struct.error) as exc:
        manifest["status"] = STATUS_UNREADABLE
        manifest["reason"] = f"reading failed ({type(exc).__name__})"
    if manifest["status"] == STATUS_EXTRACTED and manifest["refusals"]:
        manifest["notes"].append("some parts of the file were refused and are listed in refusals")
    manifest.pop("_dirname", None)
    return manifest


def _extract_text(src: Path, manifest: dict, limits: Limits) -> bool:
    """A plain-text file: bounded head preview and line count. ``False`` when it is not text.

    Two mechanical tests and nothing else: no NUL byte in the first ``text_sniff_bytes`` bytes,
    and those bytes decode as UTF-8 (a multibyte character cut at the end of the sample is
    tolerated). The content is NOT interpreted, so no meaning is attached to it here.
    """
    with src.open("rb") as fh:
        head = fh.read(limits.text_sniff_bytes)
    if not head:
        return False
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        if exc.start < len(head) - 4:
            return False
    manifest["kind"] = "text"
    trunc = manifest["truncation"]
    lines: list[str] = []
    line_count = 0
    counted = 0
    complete = True
    with src.open("rb") as fh:
        for raw in fh:
            counted += len(raw)
            line_count += 1
            if len(lines) < limits.max_text_preview_lines:
                text = raw.decode("utf-8", "replace").rstrip("\r\n")
                lines.append(_clip(text, limits.max_text_preview_line_chars, trunc, "preview_line_chars_not_returned"))
            if counted > limits.max_text_count_bytes:
                complete = False
                break
    manifest["status"] = STATUS_READ_WITH_CLAUDE
    manifest["read_with"] = READ_WITH_CLAUDE
    manifest["text"] = {
        "encoding": "utf-8",
        "sniff": "no NUL byte in the first %d bytes and they decode as UTF-8" % limits.text_sniff_bytes,
        "line_count": line_count if complete else None,
        "line_count_note": None if complete else "counting stopped at the byte bound; the file has more lines",
        "preview_lines": lines,
        "preview_bound": {"lines": limits.max_text_preview_lines, "line_chars": limits.max_text_preview_line_chars},
    }
    if line_count > len(lines):
        trunc["preview_lines_not_returned"] = line_count - len(lines)
    manifest["notes"].append(
        "A plain-text file. Open it with Claude Code's Read tool (offset and limit for a long file); only the first "
        f"{limits.max_text_preview_lines} lines are shown here."
    )
    return True


def _list_archive(src: Path, manifest: dict, limits: Limits) -> None:
    """Names and sizes of a zip's members, bounded. Nothing is extracted or read."""
    try:
        zf = zipfile.ZipFile(src)
    except zipfile.BadZipFile:
        return
    with zf:
        infos = zf.infolist()
        scanned = infos[: limits.max_archive_members_scanned]
        if len(infos) > len(scanned):
            manifest["truncation"]["archive_members_not_scanned"] = len(infos) - len(scanned)
        by_ext: dict[str, int] = {}
        names: list[str] = []
        withheld = 0
        for info in scanned:
            if info.is_dir():
                continue
            safe = _safe_relative(info.filename)
            if safe is None:
                withheld += 1
                continue
            e = PurePosixPath(safe).suffix.lower() or "(none)"
            by_ext[e] = by_ext.get(e, 0) + 1
            if len(names) < limits.max_archive_listing_names:
                names.append(safe)
        files = sum(by_ext.values()) + withheld
        if files - withheld > len(names):
            manifest["truncation"]["archive_names_not_listed"] = files - withheld - len(names)
        manifest["archive_listing"] = {
            "members_total": len(infos),
            "files": files,
            "names_withheld_unsafe": withheld,
            "extensions": dict(sorted(by_ext.items(), key=lambda kv: -kv[1])),
            "names": names,
        }


def _unreadable(src: Path, manifest: dict, limits: Limits = DEFAULT_LIMITS) -> None:
    with src.open("rb") as fh:
        lead = fh.read(8)
    manifest["status"] = STATUS_UNREADABLE
    ext = src.suffix.lower()
    if ext in (".doc", ".ppt", ".xls"):
        manifest["reason"] = "a legacy binary Office format this build does not read; save it as .docx/.pptx/.xlsx to read it"
    else:
        manifest["reason"] = "no reader in this build for this file type; its content was not interpreted or guessed"
    manifest["leading_bytes_hex"] = lead.hex()
    if lead[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        _list_archive(src, manifest, limits)
        if "archive_listing" in manifest:
            manifest["reason"] = (
                "a zip archive: its member names and sizes are listed, nothing is extracted. Unzip it into the source "
                "folder and run isaac import on that folder to read its contents"
            )


# --- batch: the unread files of a bundle ----------------------------------------------------


def extract_unread(
    unread_files: Iterable[dict],
    root: str | Path,
    out_dir: str | Path,
    *,
    limit: int | None = None,
    limits: Limits = DEFAULT_LIMITS,
) -> dict:
    """Run :func:`extract_source` over a bundle's ``unread_files`` entries.

    Each entry's ``relative_path`` is validated and resolved INSIDE ``root`` (no ``..``, no
    symlink on the way); an entry whose path was withheld (``null``) or that no longer exists
    is reported, not skipped silently. ``limit`` bounds the batch and the cut is counted.
    """
    base = Path(root).resolve()
    entries = list(unread_files)
    cut = 0
    if limit is not None and len(entries) > limit:
        cut = len(entries) - limit
        entries = entries[:limit]
    results: list[dict] = []
    for entry in entries:
        rel = entry.get("relative_path") if isinstance(entry, dict) else None
        safe = _safe_relative(rel)
        if safe is None:
            results.append({"source_relative_path": None, "status": STATUS_REFUSED, "reason": "the bundle withheld this path or it is not a safe relative path", "reason_code": entry.get("reason_code") if isinstance(entry, dict) else None})
            continue
        target = base / safe
        try:
            resolved_ok = target.resolve().is_relative_to(base) and not any(p.is_symlink() for p in [target, *target.parents] if p != base and base in p.parents or p == target)
        except OSError:
            resolved_ok = False
        if not resolved_ok or not target.is_file() or target.is_symlink():
            results.append({"source_relative_path": safe, "status": STATUS_UNREADABLE, "reason": "the file is no longer at this path under the source root, or is a symlink", "reason_code": entry.get("reason_code")})
            continue
        manifest = extract_source(target, out_dir, source_relative_path=safe, limits=limits)
        manifest["bundle_reason_code"] = entry.get("reason_code")
        results.append(manifest)
    return {
        "extractor": EXTRACTOR_ID,
        "extractor_version": EXTRACTOR_VERSION,
        "extractions": results,
        "total_entries": len(results) + cut,
        "truncation": {"entries_not_processed": cut},
        "by_status": _count(r.get("status") for r in results),
    }


def _count(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


# --- CLI ------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m isaac_api.local_import.extract",
        description="Turn a file `isaac import` could not read into something Claude can read, with provenance. Prints a JSON manifest to stdout.",
    )
    p.add_argument("file", nargs="?", help="one file to extract")
    p.add_argument("--out", required=True, help="directory for extracted images and text")
    p.add_argument("--root", help="the source folder; the manifest's source_relative_path is the file's path under it")
    p.add_argument("--from-bundle", metavar="UNREAD_JSON", help="extract every entry of an unread_files.json (needs --root)")
    p.add_argument("--limit", type=int, help="with --from-bundle: process at most this many entries")
    p.add_argument("--sheet", help="a spreadsheet: return only this sheet (page it with --rows-offset/--rows-limit)")
    p.add_argument("--rows-offset", type=int, default=0, help="with --sheet: skip this many rows (a cut sheet's read_rest says how many)")
    p.add_argument("--rows-limit", type=int, help=f"with --sheet: return at most this many rows (default {DEFAULT_LIMITS.max_preview_rows}, "
                                                  f"at most {DEFAULT_LIMITS.max_page_rows})")
    p.add_argument("--show-limits", action="store_true", help="include every bound applied (the Limits block) in each manifest")
    return p


def _with_commands(manifest: dict, args) -> None:
    """Each cut sheet's ``read_rest`` gets the exact command that reads its next page."""
    import shlex

    base = ["python", "-m", "isaac_api.local_import.extract", args.file, "--out", args.out]
    if args.root:
        base += ["--root", args.root]
    for sheet in manifest.get("sheets") or ():
        rest = sheet.get("read_rest")
        if rest:
            rest["command"] = shlex.join([*base, "--sheet", rest["sheet"], "--rows-offset", str(rest["rows_offset"]),
                                          "--rows-limit", str(rest["rows_limit"])])


def _trim_limits(doc: dict, show: bool) -> None:
    """The fixed ``limits`` block (every bound, ~1.5 KB) is the same in every manifest: printed only on
    ``--show-limits``. What was cut is still in ``truncation`` and each sheet's ``read_rest``."""
    if show:
        return
    for m in [doc, *(doc.get("extractions") or ())]:
        if isinstance(m, dict) and m.pop("limits", None) is not None:
            m["limits_shown"] = "no (--show-limits prints every bound); every cut is counted in truncation"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    paging = args.sheet is not None or args.rows_offset or args.rows_limit is not None
    if paging and (args.from_bundle or not args.file):
        print("--sheet, --rows-offset and --rows-limit page one spreadsheet: give the file, not --from-bundle", file=sys.stderr)
        return 2
    if paging and Path(args.file).suffix.lower() != ".xlsx":
        print("--sheet, --rows-offset and --rows-limit page a .xlsx spreadsheet only", file=sys.stderr)
        return 2
    if (args.rows_offset or args.rows_limit is not None) and args.sheet is None:
        print("--rows-offset and --rows-limit need --sheet <name> (a cut sheet's read_rest names it)", file=sys.stderr)
        return 2
    if args.rows_offset < 0 or (args.rows_limit is not None and not 1 <= args.rows_limit <= DEFAULT_LIMITS.max_page_rows):
        print(f"--rows-offset must be >= 0 and --rows-limit 1..{DEFAULT_LIMITS.max_page_rows}", file=sys.stderr)
        return 2
    try:
        if args.from_bundle:
            if not args.root:
                print("--from-bundle needs --root", file=sys.stderr)
                return 2
            doc = json.loads(Path(args.from_bundle).read_text(encoding="utf-8"))
            entries = doc.get("unread_files", doc) if isinstance(doc, dict) else doc
            if not isinstance(entries, list):
                print("the unread files document has no list of entries", file=sys.stderr)
                return 2
            result = extract_unread(entries, args.root, out, limit=args.limit)
        elif args.file:
            rel = None
            if args.root:
                try:
                    rel = str(Path(args.file).resolve().relative_to(Path(args.root).resolve()))
                except ValueError:
                    print("the file is not inside --root", file=sys.stderr)
                    return 3
            page = SheetPage(args.sheet, args.rows_offset, args.rows_limit) if paging else None
            result = extract_source(args.file, out, source_relative_path=rel, page=page)
            _with_commands(result, args)
        else:
            print("give a file, or --from-bundle with --root", file=sys.stderr)
            return 2
    except (ValueError, OSError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    _trim_limits(result, args.show_limits)
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
