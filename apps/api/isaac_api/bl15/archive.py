"""The SAFE walk: a folder or a ZIP in, an :class:`~.inventory.ArchiveInventory` out.

**NOTHING IN THIS MODULE IS EVER EXECUTED.** A ``.mac`` file is SPEC macro source
and this package reads it as TEXT — ``qdo``, ``mv``, ``def`` and ``newfile`` are
tokens on a line, never commands. No ``subprocess``, no ``eval``, no ``exec``, no
``import`` of anything a source names, no shell. The same holds for every other
source kind: a file found in a historical archive is bytes to be decoded and read,
and that is the whole of what happens to it here.

WHAT THIS MODULE IS FOR, AND THE BOUNDARY IT DRAWS
==================================================

``historical_import`` already draws one boundary — a ``SourceParser`` never opens a
file, it is handed text. This module is the thing that does the opening, and it is
the ONLY thing in :mod:`isaac_api.bl15` that touches the filesystem or a ZIP. Every
reader downstream takes a :class:`~.inventory.SourceRecord` plus text a CALLER
obtained through :func:`read_source_text`, so a reader cannot be the place a
path-traversal or a zip bomb lands: by the time a reader runs, the walk has already
refused anything it would not want to see.

That concentration is deliberate. It means the security surface of the whole
historical-import feature is **this file**, and it can be reviewed and tested as
one thing rather than audited once per reader.

THE GUARDS, AND WHY EACH ONE EXISTS
===================================

Each is refused with a named reason from :mod:`.inventory` and a ``detail`` string
carrying the MEASURED number and the ceiling — never a bare label, because *"this
file was skipped"* without a number is the "Upload -> Spinner -> Mysterious JSON"
pattern ``HIST-004`` bans, one layer down.

``REFUSAL_PATH_TRAVERSAL``
    A member named ``../../etc/passwd``, or any member with a ``..`` SEGMENT after
    normalisation. Note "segment": a file legitimately named ``..hidden`` or a
    directory ``..d`` is NOT traversal and is not refused. Nothing here writes
    outside anything, because **nothing here writes at all** — no extraction, no
    temporary directory, no staging copy. A ZIP member is read from the ZIP in
    place (:func:`_read_zip_member`), which removes the entire class of defect
    rather than guarding against it. :func:`resolve_within` exists for a caller
    that later chooses to materialise a file, and asserts containment against a
    resolved root.

``REFUSAL_ABSOLUTE_PATH``
    ``/etc/passwd``, ``C:\\Windows\\...``, or a UNC ``\\\\host\\share``. The ZIP
    format says member names are relative and forward-slashed; a name that is not
    is a crafted archive, not a portability quirk.

``REFUSAL_SYMLINK``
    A symlink is never followed, in either walker. In a folder walk every
    :func:`os.scandir` test passes ``follow_symlinks=False`` and a symlinked
    DIRECTORY is refused rather than descended — a symlink loop would otherwise
    never terminate, which is a denial of service reachable by an ordinary
    ``ln -s . loop`` and not only by a crafted archive. In a ZIP, a member whose
    external attributes carry a Unix mode with ``S_IFLNK`` is refused; its
    "content" is a target PATH, and reading it as a source would put a filesystem
    path where a scientist expects a measurement.

``REFUSAL_TOO_LARGE`` / ``REFUSAL_COMPRESSION_RATIO``
    Per entry. The ZIP case is checked THREE times and the reason is in the
    ordering: a cheap pre-check against the central directory's declared sizes,
    then a hard cap on the bytes actually decompressed, then a comparison of what
    was read against what was declared. **The declared sizes are not trusted** —
    see :func:`_read_zip_member`.

``REFUSAL_TOTAL_TOO_LARGE`` / ``REFUSAL_TOO_MANY_ENTRIES``
    These are the two ceilings that STOP the walk and set
    :attr:`ArchiveInventory.truncated_reason`, rather than refusing one entry and
    continuing. That distinction is the contract's: a per-entry refusal leaves the
    inventory COMPLETE and honest about one skipped file, while these two leave it
    INCOMPLETE, and a reconstruction over an incomplete inventory must say so.

``REFUSAL_TOO_DEEP`` / ``REFUSAL_PATH_TOO_LONG``
    Bound a crafted tree. The real corpus is 1 level deep with a longest
    archive-relative path of 127 characters (measured 2026-09-16), so both
    ceilings are bounds a real corpus clears rather than numbers tuned to it.

``REFUSAL_UNREADABLE``
    A permission error, a corrupted ZIP member, a truncated central directory, a
    file that vanished between enumeration and reading, a member whose bytes
    disagree with its own declared size or CRC. **A corrupt ZIP returns an
    inventory carrying the refusal; it does not raise.** A scientist handed
    "0 entries, 1 refusal: the archive could not be opened" knows what happened;
    a scientist handed a stack trace does not.

``REFUSAL_UNDECODABLE``
    Reached through :func:`read_source_text`, not the walk. See
    :func:`decode_source_bytes` for why a NUL byte is the test and why ``latin-1``
    is not a licence to read a PDF.

DETERMINISM IS A REQUIREMENT, NOT A NICETY
==========================================

Two walks of the same archive produce byte-identical
:meth:`~.inventory.ArchiveInventory.to_state` output, and a folder and a ZIP of
that same folder produce the same :attr:`~.inventory.SourceRecord.archive_path`
set. Both walkers therefore share :func:`_inventory_from_candidates`: names are
enumerated first (cheap, no reads), sorted, and only THEN are the size and byte
ceilings applied in that sorted order — so which entries a truncated walk kept
does not depend on directory iteration order or on the order members happen to
sit in a ZIP's central directory.
"""

from __future__ import annotations

import codecs
import copy
import hashlib
import os
import re
import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .inventory import (
    REFUSAL_ABSOLUTE_PATH,
    REFUSAL_COMPRESSION_RATIO,
    REFUSAL_PATH_TOO_LONG,
    REFUSAL_PATH_TRAVERSAL,
    REFUSAL_SYMLINK,
    REFUSAL_TOO_DEEP,
    REFUSAL_TOO_LARGE,
    REFUSAL_TOO_MANY_ENTRIES,
    REFUSAL_TOTAL_TOO_LARGE,
    REFUSAL_UNDECODABLE,
    REFUSAL_UNREADABLE,
    ArchiveInventory,
    ArchiveLimits,
    SourceRecord,
)

__all__ = [
    "ARCHIVE_WALKER_ID",
    "DecodedSource",
    "common_root_prefix",
    "decode_source_bytes",
    "inventory_folder",
    "inventory_zip",
    "read_source_decoded",
    "read_source_head",
    "read_source_text",
    "resolve_within",
]

#: Recorded so a caller that wants to say WHICH walk produced an inventory has
#: one string to use. Nothing is stamped automatically.
ARCHIVE_WALKER_ID = "bl15.archive/v1"

#: Bytes per read while hashing or capping. Not a limit; just the buffer.
_CHUNK = 64 * 1024

#: A drive-lettered Windows path (``C:\\x``, ``c:/x``). Checked because a ZIP
#: written by a non-conforming tool can carry one and it is absolute.
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")

#: Exceptions a damaged or crafted ZIP can raise out of ``zipfile``. Caught as a
#: set rather than ``Exception`` so a genuine defect in this module still raises
#: instead of being reported to a scientist as "your archive is unreadable".
_ZIP_ERRORS = (
    zipfile.BadZipFile,
    OSError,
    EOFError,
    zlib.error,
    ValueError,
    RuntimeError,
    NotImplementedError,
)


# --- path normalisation ------------------------------------------------------


@dataclass(frozen=True)
class _NameVerdict:
    """The outcome of looking at a member NAME, before anything is read."""

    archive_path: str | None
    reason: str | None
    detail: str | None


def _normalise_member_name(raw: object, limits: ArchiveLimits) -> _NameVerdict:
    """Archive-relative, forward-slashed, normalised — or a refusal reason.

    Backslashes are treated as separators as well as forward slashes. A ZIP
    written to the specification uses ``/`` only, so a name containing ``\\`` is
    already non-conforming; splitting on both means a crafted ``..\\..\\etc`` is
    seen as traversal rather than as one long odd filename. The cost is that a
    file legitimately containing a backslash in its NAME is read as two segments,
    which no source in this corpus family does and which fails safe.
    """
    if raw is None or not str(raw).strip():
        return _NameVerdict(None, REFUSAL_UNREADABLE, "the member has no name")

    name = str(raw)

    if name.startswith("/") or name.startswith("\\") or _DRIVE.match(name):
        return _NameVerdict(
            None,
            REFUSAL_ABSOLUTE_PATH,
            f"member name {name!r} is absolute; archive members must be relative",
        )

    segments: list[str] = []
    for segment in re.split(r"[\\/]+", name):
        if segment in ("", "."):
            # `./foo` and `a//b` are produced by ordinary archivers and mean
            # nothing; they are dropped, not refused.
            continue
        if segment == "..":
            return _NameVerdict(
                None,
                REFUSAL_PATH_TRAVERSAL,
                f"member name {name!r} contains a '..' segment; "
                "it would resolve outside the archive root",
            )
        segments.append(segment)

    if not segments:
        return _NameVerdict(
            None, REFUSAL_UNREADABLE, f"member name {name!r} normalises to nothing"
        )

    archive_path = "/".join(segments)

    if len(archive_path) > limits.max_path_chars:
        return _NameVerdict(
            None,
            REFUSAL_PATH_TOO_LONG,
            f"path is {len(archive_path)} characters; "
            f"the ceiling is {limits.max_path_chars}",
        )

    depth = len(segments) - 1
    if depth > limits.max_depth:
        return _NameVerdict(
            None,
            REFUSAL_TOO_DEEP,
            f"path is {depth} level(s) below the archive root; "
            f"the ceiling is {limits.max_depth}",
        )

    return _NameVerdict(archive_path, None, None)


def resolve_within(root: Path, archive_path: str) -> Path:
    """``root / archive_path``, resolved, PROVEN to be inside ``root``.

    Nothing in this module extracts, so nothing in this module calls this on a
    write path. It exists because a future caller that chooses to materialise a
    source needs one place where containment is asserted rather than assumed, and
    because a folder read must not be talked into going through a symlinked
    parent that appeared after enumeration.

    Raises :class:`ValueError` rather than returning a refusal: a containment
    failure here is not a scientist-visible condition about their data, it is a
    caller using this function wrongly or a filesystem that changed underneath.
    """
    resolved_root = root.resolve()
    candidate = (resolved_root / archive_path).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError(f"{archive_path!r} resolves outside the archive root")
    return candidate


# --- decoding ----------------------------------------------------------------


@dataclass(frozen=True)
class DecodedSource:
    """Text, and WHICH encoding produced it, so a caller can disclose both.

    :attr:`encoding` is not cosmetic. ``latin-1`` succeeding means every byte was
    mapped to a code point and NOTHING was validated — a reader handed such text
    is reading a guess about the file's character set, and a surface that shows a
    value read that way should be able to say so. That is why the encoding travels
    with the text instead of being discarded at the decode site.
    """

    text: str
    #: ``"utf-8"``, ``"utf-8-sig"`` or ``"latin-1"``.
    encoding: str
    #: True when the bytes began with a UTF-8 BOM, which was stripped.
    had_bom: bool
    #: Bytes considered. For a head read this is at most ``limits.head_bytes``.
    byte_count: int
    #: True when this is a head read that stopped at the ceiling, so the caller
    #: knows the text is a prefix and not the file.
    truncated: bool = False


def decode_source_bytes(
    data: bytes, *, allow_partial_tail: bool = False
) -> DecodedSource | None:
    """UTF-8, then UTF-8-with-BOM, then ``latin-1``; ``None`` if none of them.

    **The order only makes sense with an explicit BOM test, and this is that
    test.** Plain UTF-8 decoding SUCCEEDS on a BOM'd file and leaves a ``U+FEFF``
    sitting in front of the first real character — so "try UTF-8 first, then
    UTF-8-with-BOM" would never reach the second codec, and every reader
    downstream would have to strip the mark itself or match on a header key that
    had silently gained an invisible character. The real beamtime notes file
    ``250411 BL 15 IrOx NP HERFD acid base.txt`` begins ``EF BB BF`` (measured
    2026-09-16), so this is the corpus's actual behaviour and not a hypothetical:
    the BOM is detected, stripped, and DISCLOSED as ``utf-8-sig``.

    **Why a NUL byte is the refusal test.** ``latin-1`` cannot fail — all 256 byte
    values map to code points — so without a positive test
    :data:`~.inventory.REFUSAL_UNDECODABLE` would be unreachable and the ``.docx``
    and ``.pdf`` in this corpus would decode into mojibake that a reader would
    then cheerfully parse. A NUL byte is the cheapest signal that a file is not
    text, it is what ``git`` itself uses, and it is measured here: both binary
    members of the real corpus carry NUL bytes in their first 8 KB, and **all
    1,190 other files carry none** — so the test separates exactly the right two
    files and no others.

    ``allow_partial_tail`` is for a head read, where the ceiling can fall in the
    middle of a multi-byte sequence. Up to three trailing bytes are dropped to
    find a valid boundary; without that a head read of a UTF-8 file would
    intermittently fall through to ``latin-1`` depending on where the cut landed,
    which would make the DISCLOSED encoding a function of the ceiling rather than
    of the file.
    """
    if b"\x00" in data:
        return None

    had_bom = data.startswith(codecs.BOM_UTF8)
    body = data[len(codecs.BOM_UTF8) :] if had_bom else data
    utf8_label = "utf-8-sig" if had_bom else "utf-8"

    trims = (0, 1, 2, 3) if allow_partial_tail else (0,)
    for trim in trims:
        chunk = body[: len(body) - trim] if trim else body
        try:
            return DecodedSource(
                text=chunk.decode("utf-8"),
                encoding=utf8_label,
                had_bom=had_bom,
                byte_count=len(data),
            )
        except UnicodeDecodeError:
            continue

    try:
        return DecodedSource(
            text=body.decode("latin-1"),
            encoding="latin-1",
            had_bom=had_bom,
            byte_count=len(data),
        )
    except UnicodeDecodeError:  # pragma: no cover - latin-1 maps every byte
        return None


# --- reading one entry's bytes ----------------------------------------------


@dataclass(frozen=True)
class _Bytes:
    data: bytes | None
    reason: str | None
    detail: str | None


#: The ``ZipInfo`` attributes ``ZipFile.open`` needs in order to locate and
#: decompress a member. Verified on the probe copy below.
_PROBE_CRITICAL = ("orig_filename", "header_offset", "compress_type", "compress_size")


def _probe_info(info: zipfile.ZipInfo, file_size: int) -> zipfile.ZipInfo:
    """A copy of ``info`` whose ``file_size`` is ours and whose CRC is disarmed.

    **Why a copy at all** is explained in :func:`_read_zip_member`: ``zipfile``
    stops reading at the declared ``file_size``, so reading through the archive's
    own number would make the central directory the thing protecting us.

    **Why the copy is VERIFIED.** :class:`zipfile.ZipInfo` is a ``__slots__``
    class with no ``__dict__``, so :func:`copy.copy` reaches its state through the
    pickle protocol rather than through a plain attribute copy. That works on the
    interpreter this was measured on (3.12.3) and is expected to work on the 3.11
    CI runs, but "expected to" is not a measurement — and a copy that silently
    lost ``header_offset`` would make every member read the WRONG BYTES while
    raising nothing. So the four attributes the read depends on are compared, and
    a mismatch raises here rather than producing a plausible wrong answer.
    """
    probe = copy.copy(info)
    for attribute in _PROBE_CRITICAL:
        if getattr(probe, attribute) != getattr(info, attribute):
            raise RuntimeError(
                f"copying a ZipInfo did not preserve {attribute!r} on this "
                "interpreter; refusing to read a member through an incomplete "
                "descriptor"
            )
    probe.file_size = file_size
    # Deliberately disabled: `zipfile` would compare the CRC against our own
    # inflated declaration and raise. The caller recomputes it over the bytes it
    # actually holds, which is the check we wanted in the first place.
    probe.CRC = None
    return probe


def _read_capped_stream(stream, cap: int, *, want: int | None = None) -> tuple[bytes | None, int]:
    """Read at most ``cap`` bytes, returning ``None`` if the stream had more.

    Returns ``(data_or_None, bytes_seen)``. ``bytes_seen`` is ``limit + 1`` in the
    refusal case, which is what the caller reports: the exact size is not knowable
    without reading past the ceiling, which is the thing being refused.
    """
    seen = 0
    chunks: list[bytes] = []
    limit = cap if want is None else min(cap, want)
    while True:
        chunk = stream.read(_CHUNK)
        if not chunk:
            break
        seen += len(chunk)
        if seen > limit:
            if want is not None:
                # A head read WANTED a prefix: stopping at it is success.
                chunks.append(chunk)
                return b"".join(chunks)[:limit], limit
            return None, limit + 1
        chunks.append(chunk)
    return b"".join(chunks), seen


def _read_zip_member(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, limits: ArchiveLimits
) -> _Bytes:
    """Decompress ONE member without trusting a single number it declares.

    THREE independent bounds, in this order, because each catches something the
    others cannot:

    1. **The declared-size pre-check** (in :func:`_inventory_from_candidates`)
       refuses an honestly-declared oversized or high-ratio member for FREE,
       before a byte is decompressed. Cheap, and sufficient for a well-formed
       archive.
    2. **A hard cap on bytes actually produced.** This is the one that matters,
       and it is why the read goes through a COPY of the :class:`zipfile.ZipInfo`
       whose ``file_size`` is set to ``cap + 1``. ``zipfile`` itself stops at the
       declared ``file_size``, so a member declaring 16 bytes while its stream
       expands to 5 MB would be TRUNCATED by the standard library — and the
       defence would then be the library's trust in the central directory rather
       than ours. Inflating our working copy removes that trust: the byte counter
       here is what stops the read, at ``cap + 1``, having materialised nothing
       larger. Measured 2026-09-16 on Python 3.12.3 against exactly that archive
       (``file_size`` patched to 16 over a 5 MB deflate stream): refused at the
       cap, ``data is None``.
    3. **What was read versus what was declared.** If the member completes under
       the cap but its length or CRC-32 disagrees with the central directory, the
       archive is lying or damaged and the member is
       :data:`~.inventory.REFUSAL_UNREADABLE` — stated with both numbers. This is
       where the CRC check step 2 had to switch off comes back: it is recomputed
       with :func:`zlib.crc32` over the bytes we actually hold, which is a
       stronger position than trusting the library to have checked a length we
       had already decided not to believe.

    The cap is ``min(max_entry_bytes, compress_size * max_compression_ratio)``.
    ``compress_size`` is the one number a lying archive cannot inflate for free:
    the compressed bytes are physically present in the file.
    """
    ratio_cap = max(int(info.compress_size), 1) * limits.max_compression_ratio
    cap = min(limits.max_entry_bytes, ratio_cap)

    probe = _probe_info(info, cap + 1)

    try:
        with zf.open(probe, "r") as stream:
            data, _seen = _read_capped_stream(stream, cap)
    except _ZIP_ERRORS as exc:
        return _Bytes(
            None,
            REFUSAL_UNREADABLE,
            f"the member could not be decompressed: {type(exc).__name__}",
        )

    if data is None:
        if ratio_cap <= limits.max_entry_bytes:
            return _Bytes(
                None,
                REFUSAL_COMPRESSION_RATIO,
                f"the member expanded past {cap} bytes from "
                f"{info.compress_size} compressed byte(s) — over the "
                f"{limits.max_compression_ratio}:1 ceiling — while declaring "
                f"{info.file_size} bytes",
            )
        return _Bytes(
            None,
            REFUSAL_TOO_LARGE,
            f"the member expanded past {cap} bytes while declaring "
            f"{info.file_size}; the ceiling is {limits.max_entry_bytes}",
        )

    if len(data) != int(info.file_size):
        return _Bytes(
            None,
            REFUSAL_UNREADABLE,
            f"the member declares {info.file_size} bytes and produced "
            f"{len(data)}; the archive's own directory is wrong",
        )

    if info.CRC is not None and (zlib.crc32(data) & 0xFFFFFFFF) != (
        int(info.CRC) & 0xFFFFFFFF
    ):
        return _Bytes(
            None,
            REFUSAL_UNREADABLE,
            "the member's CRC-32 does not match its bytes; it is damaged",
        )

    return _Bytes(data, None, None)


def _read_folder_file(path: Path, limits: ArchiveLimits) -> _Bytes:
    """Read one file from a folder, bounded, never through a symlink."""
    try:
        if path.is_symlink():
            return _Bytes(
                None,
                REFUSAL_SYMLINK,
                "the path became a symlink after it was enumerated; "
                "it was not followed",
            )
        with open(path, "rb") as fh:
            data, _seen = _read_capped_stream(fh, limits.max_entry_bytes)
    except OSError as exc:
        return _Bytes(
            None,
            REFUSAL_UNREADABLE,
            f"the file could not be read: {type(exc).__name__}",
        )
    if data is None:
        return _Bytes(
            None,
            REFUSAL_TOO_LARGE,
            f"the file grew past {limits.max_entry_bytes} bytes while being "
            "read, the per-entry ceiling",
        )
    return _Bytes(data, None, None)


# --- candidate enumeration ---------------------------------------------------


@dataclass(frozen=True)
class _Candidate:
    archive_path: str
    #: Declared size. For a folder this is ``st_size``; for a ZIP it is the
    #: central directory's ``file_size``, which is NOT trusted for the read.
    declared_size: int
    #: ``None`` for a folder candidate.
    zip_info: zipfile.ZipInfo | None
    #: ``None`` for a ZIP candidate.
    fs_path: Path | None


def _name_scan_ceiling(limits: ArchiveLimits) -> int:
    """How many NAMES may be enumerated before the walk gives up.

    Enumeration happens before any ceiling can be applied in sorted order, so it
    needs its own bound, or a crafted tree with ten million empty files would
    exhaust memory in phase 1 while every per-entry guard sat unused in phase 2.
    Ten times ``max_entries`` (floor 50,000) keeps the sort-then-truncate
    behaviour for any archive within an order of magnitude of the ceiling — which
    covers every real case — and refuses rather than dies beyond it.
    """
    return max(limits.max_entries * 10, 50_000)


def _folder_candidates(
    root: Path, limits: ArchiveLimits
) -> tuple[list[_Candidate], list[dict], str | None]:
    """Depth-first, name-sorted, never following a symlink of any kind."""
    candidates: list[_Candidate] = []
    refused: list[dict] = []
    truncated: str | None = None
    ceiling = _name_scan_ceiling(limits)

    def record(archive_path: str, reason: str, detail: str) -> None:
        refused.append(
            {"archive_path": archive_path, "reason": reason, "detail": detail}
        )

    def walk(directory: Path, prefix: str) -> None:
        nonlocal truncated
        if truncated:
            return
        try:
            with os.scandir(directory) as scanner:
                entries = sorted(scanner, key=lambda e: e.name)
        except OSError as exc:
            record(
                prefix.rstrip("/"),
                REFUSAL_UNREADABLE,
                f"the directory could not be listed: {type(exc).__name__}",
            )
            return

        for entry in entries:
            if truncated:
                return
            relative = f"{prefix}{entry.name}"
            verdict = _normalise_member_name(relative, limits)
            try:
                is_symlink = entry.is_symlink()
            except OSError:
                is_symlink = False
            if is_symlink:
                # Refused whether it points at a file or a directory, and the
                # directory case is the load-bearing one: `ln -s . loop` makes an
                # unterminating walk out of an ordinary filesystem.
                record(
                    verdict.archive_path or relative,
                    REFUSAL_SYMLINK,
                    "the entry is a symbolic link; it was not followed",
                )
                continue
            if verdict.reason:
                record(relative, verdict.reason, verdict.detail or "")
                continue
            archive_path = verdict.archive_path or relative
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                stat_result = entry.stat(follow_symlinks=False)
            except OSError as exc:
                record(
                    archive_path,
                    REFUSAL_UNREADABLE,
                    f"the entry could not be inspected: {type(exc).__name__}",
                )
                continue
            if is_dir:
                walk(Path(entry.path), f"{archive_path}/")
                continue
            if not stat.S_ISREG(stat_result.st_mode):
                # A FIFO, socket or device node is not a source. Reading one can
                # block forever, which is why it is refused by KIND and not left
                # to the size ceiling.
                record(
                    archive_path,
                    REFUSAL_UNREADABLE,
                    "the entry is not a regular file",
                )
                continue
            if len(candidates) >= ceiling:
                truncated = REFUSAL_TOO_MANY_ENTRIES
                return
            candidates.append(
                _Candidate(
                    archive_path=archive_path,
                    declared_size=int(stat_result.st_size),
                    zip_info=None,
                    fs_path=Path(entry.path),
                )
            )

    walk(root, "")
    return candidates, refused, truncated


def common_root_prefix(names: Iterable[str]) -> str | None:
    """The ONE wrapper directory a "compress this folder" ZIP adds, or ``None``.

    **Why this exists, stated plainly because it is the one place the two walkers
    would otherwise disagree.** Archiving a folder produces member names
    ``Corpus/readme.txt``, while walking the extracted folder produces
    ``readme.txt``. Measured on the real archive (2026-09-16): every one of the
    1,194 members of ``SSRL_BL152_2025-04_Sokaras_IrOxBase.zip`` begins
    ``SSRL_BL152_2025-04_Sokaras_IrOxBase/``. Without stripping it, the same
    corpus read two ways gives a different ``archive_path`` for every file, and
    every piece of evidence, every duplicate group and every locator would depend
    on which container the scientist happened to hand over.

    The rule is deliberately narrow: strip only when EVERY member has at least
    two segments and they ALL share the same first segment. A flat ZIP is
    untouched; a ZIP with two top-level folders is untouched; a ZIP with one
    top-level folder and one stray root file is untouched. The wrapper's name is
    not lost information — the scientist's own ``root_label`` is what names the
    import, and the wrapper is an artifact of how they zipped it.
    """
    first: str | None = None
    saw_any = False
    for name in names:
        segments = [s for s in re.split(r"[\\/]+", str(name)) if s not in ("", ".")]
        if not segments:
            continue
        saw_any = True
        if len(segments) < 2:
            return None
        if first is None:
            first = segments[0]
        elif segments[0] != first:
            return None
    return first if saw_any else None


def _zip_candidates(
    zf: zipfile.ZipFile, limits: ArchiveLimits, *, strip_common_root: bool
) -> tuple[list[_Candidate], list[dict], str | None]:
    candidates: list[_Candidate] = []
    refused: list[dict] = []
    truncated: str | None = None
    ceiling = _name_scan_ceiling(limits)

    infos = sorted(zf.infolist(), key=lambda i: i.filename)
    prefix = (
        common_root_prefix(i.filename for i in infos if not i.is_dir())
        if strip_common_root
        else None
    )

    for info in infos:
        if truncated:
            break
        raw = info.filename
        verdict = _normalise_member_name(raw, limits)
        if verdict.reason:
            refused.append(
                {
                    "archive_path": _display_name(raw),
                    "reason": verdict.reason,
                    "detail": verdict.detail or "",
                }
            )
            continue
        archive_path = verdict.archive_path or ""
        if prefix:
            if archive_path == prefix:
                continue
            if archive_path.startswith(prefix + "/"):
                archive_path = archive_path[len(prefix) + 1 :]

        mode = (int(info.external_attr) >> 16) & 0xFFFF
        # **THE FILE-TYPE BITS ARE OFTEN ABSENT, AND READING THEIR ABSENCE AS A
        # TYPE IS A REAL DEFECT THIS CODE HAD.** `ZipFile.writestr(name, data)`
        # stores `external_attr = 0o600 << 16` — permission bits only, with
        # `S_IFMT` zero — and the real BL15-2 archive stores `external_attr = 0`
        # for all 1,194 members (`create_system` 0, i.e. MS-DOS/FAT, which has no
        # Unix mode at all). A first version here refused any member whose mode
        # was not `S_ISREG`, which refused **every ordinary member of every ZIP
        # written by `zipfile` itself**. So the type is consulted only when the
        # archive actually recorded one.
        file_type = stat.S_IFMT(mode)
        if file_type == stat.S_IFLNK:
            # Its "content" is a target path, not a source. Refused by KIND:
            # reading it would put a filesystem path where a measurement belongs.
            refused.append(
                {
                    "archive_path": archive_path or _display_name(raw),
                    "reason": REFUSAL_SYMLINK,
                    "detail": "the member is recorded as a symbolic link; "
                    "it was not followed",
                }
            )
            continue

        if info.is_dir():
            continue
        if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
            refused.append(
                {
                    "archive_path": archive_path or _display_name(raw),
                    "reason": REFUSAL_UNREADABLE,
                    "detail": f"the member's recorded type {oct(file_type)} is "
                    "neither a regular file nor a directory",
                }
            )
            continue
        if not archive_path:
            refused.append(
                {
                    "archive_path": _display_name(raw),
                    "reason": REFUSAL_UNREADABLE,
                    "detail": "the member name is empty once normalised",
                }
            )
            continue
        if len(candidates) >= ceiling:
            truncated = REFUSAL_TOO_MANY_ENTRIES
            break
        candidates.append(
            _Candidate(
                archive_path=archive_path,
                declared_size=int(info.file_size),
                zip_info=info,
                fs_path=None,
            )
        )

    return candidates, refused, truncated


def _display_name(raw: object) -> str:
    """A refused member still needs a handle, and it must not read as a path.

    A traversal or absolute member name is exactly the thing that must not be
    echoed as if it were usable. It is reported verbatim but bounded, so a
    scientist can see WHAT was refused without the string growing without limit.
    """
    text = str(raw)
    return text if len(text) <= 256 else text[:253] + "..."


# --- the shared second phase -------------------------------------------------


def _inventory_from_candidates(
    *,
    root_label: str,
    candidates: list[_Candidate],
    refused: list[dict],
    truncated: str | None,
    limits: ArchiveLimits,
    zf: zipfile.ZipFile | None,
) -> ArchiveInventory:
    """Apply the size and byte ceilings in SORTED order, then hash.

    Sorting before the ceilings — rather than applying them as names arrive — is
    what makes a truncated walk deterministic. Directory iteration order and ZIP
    central-directory order are both arbitrary; which entries a walk that hit
    ``max_entries`` kept must not be.
    """
    candidates = sorted(candidates, key=lambda c: c.archive_path)

    if len(candidates) > limits.max_entries:
        dropped = len(candidates) - limits.max_entries
        candidates = candidates[: limits.max_entries]
        truncated = REFUSAL_TOO_MANY_ENTRIES
        refused.append(
            {
                "archive_path": "",
                "reason": REFUSAL_TOO_MANY_ENTRIES,
                "detail": f"{dropped} entr(ies) past the {limits.max_entries} "
                "ceiling were not inventoried",
            }
        )

    entries: list[SourceRecord] = []
    total = 0

    for candidate in candidates:
        path = candidate.archive_path

        if candidate.declared_size > limits.max_entry_bytes:
            refused.append(
                {
                    "archive_path": path,
                    "reason": REFUSAL_TOO_LARGE,
                    "detail": f"the entry declares {candidate.declared_size} "
                    f"bytes; the ceiling is {limits.max_entry_bytes}",
                }
            )
            continue

        info = candidate.zip_info
        if info is not None:
            declared_ratio = int(info.file_size) / max(int(info.compress_size), 1)
            if declared_ratio > limits.max_compression_ratio:
                refused.append(
                    {
                        "archive_path": path,
                        "reason": REFUSAL_COMPRESSION_RATIO,
                        "detail": f"the member declares {info.file_size} bytes "
                        f"from {info.compress_size} compressed "
                        f"({declared_ratio:.1f}:1); the ceiling is "
                        f"{limits.max_compression_ratio}:1",
                    }
                )
                continue

        if total + candidate.declared_size > limits.max_total_bytes:
            truncated = REFUSAL_TOTAL_TOO_LARGE
            refused.append(
                {
                    "archive_path": path,
                    "reason": REFUSAL_TOTAL_TOO_LARGE,
                    "detail": f"the walk had accepted {total} bytes and this "
                    f"entry declares {candidate.declared_size}, over the "
                    f"{limits.max_total_bytes} total ceiling; the inventory is "
                    "incomplete from here on",
                }
            )
            break

        if info is not None and zf is not None:
            read = _read_zip_member(zf, info, limits)
        else:
            assert candidate.fs_path is not None
            read = _read_folder_file(candidate.fs_path, limits)

        if read.data is None:
            refused.append(
                {
                    "archive_path": path,
                    "reason": read.reason or REFUSAL_UNREADABLE,
                    "detail": read.detail or "",
                }
            )
            continue

        measured = len(read.data)
        if total + measured > limits.max_total_bytes:
            truncated = REFUSAL_TOTAL_TOO_LARGE
            refused.append(
                {
                    "archive_path": path,
                    "reason": REFUSAL_TOTAL_TOO_LARGE,
                    "detail": f"the walk had accepted {total} bytes and this "
                    f"entry measured {measured}, over the "
                    f"{limits.max_total_bytes} total ceiling; the inventory is "
                    "incomplete from here on",
                }
            )
            break

        basename = path.rsplit("/", 1)[-1]
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        extension = basename.rsplit(".", 1)[1].lower() if "." in basename else ""
        entries.append(
            SourceRecord(
                archive_path=path,
                basename=basename,
                extension=extension,
                size_bytes=measured,
                content_sha256=hashlib.sha256(read.data).hexdigest(),
                parent_dir=parent,
                depth=path.count("/"),
            )
        )
        total += measured

    refused.sort(key=lambda r: (r["archive_path"], r["reason"], r["detail"]))

    return ArchiveInventory(
        root_label=root_label,
        entries=tuple(entries),
        refused=tuple(refused),
        total_bytes=total,
        truncated_reason=truncated,
        duplicate_groups=_duplicate_groups(entries),
    )


def _duplicate_groups(
    entries: Iterable[SourceRecord],
) -> tuple[tuple[str, ...], ...]:
    """Groups of paths sharing one ``content_sha256``. Every member is KEPT.

    Identity is the content digest and nothing else. The real corpus makes both
    halves of that necessary: 92 of the 94 ``*_dir`` directories hold a
    byte-identical copy of their root acquisition file (96 groups over 193 files,
    measured), which a name heuristic would miss, while ``run29.mac`` and
    ``run29.mac.mac`` have DIFFERENT content and a name heuristic would fuse
    them. Dropping a member would delete a file the scientist actually has; the
    only consequence of grouping is that the copies must not be counted as two
    independent witnesses to the same statement.
    """
    by_digest: dict[str, list[str]] = {}
    for entry in entries:
        by_digest.setdefault(entry.content_sha256, []).append(entry.archive_path)
    groups = [tuple(sorted(paths)) for paths in by_digest.values() if len(paths) > 1]
    return tuple(sorted(groups))


# --- the two entry points ----------------------------------------------------


def inventory_folder(
    root: Path,
    *,
    root_label: str,
    limits: ArchiveLimits = ArchiveLimits(),
) -> ArchiveInventory:
    """Inventory an extracted folder. Never follows a symlink, never writes.

    A ``root`` that is missing, is not a directory, or is itself a symlink comes
    back as an inventory with one :data:`~.inventory.REFUSAL_UNREADABLE` (or
    :data:`~.inventory.REFUSAL_SYMLINK`) rather than as an exception, for the
    same reason a corrupt ZIP does: the scientist chose the folder and is owed a
    readable answer about it.
    """
    root = Path(root)
    try:
        if root.is_symlink():
            return ArchiveInventory(
                root_label=root_label,
                refused=(
                    {
                        "archive_path": "",
                        "reason": REFUSAL_SYMLINK,
                        "detail": "the archive root is a symbolic link; "
                        "it was not followed",
                    },
                ),
            )
        if not root.is_dir():
            return ArchiveInventory(
                root_label=root_label,
                refused=(
                    {
                        "archive_path": "",
                        "reason": REFUSAL_UNREADABLE,
                        "detail": "the archive root is not a directory",
                    },
                ),
            )
    except OSError as exc:
        return ArchiveInventory(
            root_label=root_label,
            refused=(
                {
                    "archive_path": "",
                    "reason": REFUSAL_UNREADABLE,
                    "detail": "the archive root could not be inspected: "
                    f"{type(exc).__name__}",
                },
            ),
        )

    candidates, refused, truncated = _folder_candidates(root, limits)
    return _inventory_from_candidates(
        root_label=root_label,
        candidates=candidates,
        refused=refused,
        truncated=truncated,
        limits=limits,
        zf=None,
    )


def inventory_zip(
    zip_path: Path,
    *,
    root_label: str,
    limits: ArchiveLimits = ArchiveLimits(),
    strip_common_root: bool = True,
) -> ArchiveInventory:
    """Inventory a ZIP **without extracting it**.

    Members are read from the archive in place. Nothing is written anywhere, so
    zip-slip is not guarded against so much as made unreachable — there is no
    destination for a ``../`` to escape into. The traversal and absolute-path
    guards still run, and still refuse, because the scientist is owed the fact
    that the archive CONTAINED such a member: silently normalising it away would
    hide a crafted archive rather than report one.

    ``strip_common_root`` — see :func:`common_root_prefix`. Left on by default
    because a "compress this folder" ZIP is the shape a scientist actually hands
    over, and off it the same corpus read two ways produces two different path
    sets.
    """
    zip_path = Path(zip_path)
    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except _ZIP_ERRORS as exc:
        return ArchiveInventory(
            root_label=root_label,
            refused=(
                {
                    "archive_path": "",
                    "reason": REFUSAL_UNREADABLE,
                    "detail": "the archive could not be opened: "
                    f"{type(exc).__name__}",
                },
            ),
        )
    try:
        try:
            candidates, refused, truncated = _zip_candidates(
                zf, limits, strip_common_root=strip_common_root
            )
        except _ZIP_ERRORS as exc:
            return ArchiveInventory(
                root_label=root_label,
                refused=(
                    {
                        "archive_path": "",
                        "reason": REFUSAL_UNREADABLE,
                        "detail": "the archive's central directory could not be "
                        f"read: {type(exc).__name__}",
                    },
                ),
            )
        return _inventory_from_candidates(
            root_label=root_label,
            candidates=candidates,
            refused=refused,
            truncated=truncated,
            limits=limits,
            zf=zf,
        )
    finally:
        zf.close()


# --- bounded reading, for the readers ---------------------------------------


def read_source_decoded(
    inventory: ArchiveInventory,
    archive_path: str,
    *,
    source_root: Path,
    limits: ArchiveLimits = ArchiveLimits(),
    head_only: bool = False,
) -> tuple[DecodedSource | None, str | None]:
    """The full form: text WITH its encoding, or a refusal reason. Never both.

    **Only an entry the walk ACCEPTED can be read.** A path that is not in
    ``inventory.by_path()`` is refused, which is what makes every guard in the
    walk transitive: a reader cannot reach a member that was refused for
    traversal, size or ratio by asking for it by name afterwards.

    On a full read the bytes are re-hashed and compared against
    :attr:`~.inventory.SourceRecord.content_sha256`. A mismatch means the archive
    changed between the walk and the read, and it is
    :data:`~.inventory.REFUSAL_UNREADABLE` — text read from a file that is no
    longer the file the inventory described would carry a locator pointing at
    content nobody can reproduce. A head read cannot make that comparison and
    does not pretend to.
    """
    entry = inventory.by_path().get(archive_path)
    if entry is None:
        return None, REFUSAL_UNREADABLE

    source_root = Path(source_root)
    want = limits.head_bytes if head_only else None
    data: bytes

    if source_root.is_dir():
        # **THE SYMLINK TEST COMES FIRST, AND THE ORDER IS THE POINT.** A symlink
        # planted after the walk usually points OUTSIDE the root, so
        # `resolve_within` would also catch it — but it would report
        # `path_traversal`, which describes the consequence and not the cause. The
        # lexical join is tested before anything is resolved so the reason names
        # what actually happened; containment is then still proven, because a
        # symlink pointing INSIDE the root is contained and a traversal that is
        # not a symlink still has to be refused.
        try:
            if (source_root / archive_path).is_symlink():
                return None, REFUSAL_SYMLINK
        except OSError:
            return None, REFUSAL_UNREADABLE
        try:
            target = resolve_within(source_root, archive_path)
        except ValueError:
            return None, REFUSAL_PATH_TRAVERSAL
        try:
            if target.is_symlink():
                return None, REFUSAL_SYMLINK
            if not target.is_file():
                return None, REFUSAL_UNREADABLE
            with open(target, "rb") as fh:
                read_data, _seen = _read_capped_stream(
                    fh, limits.max_entry_bytes, want=want
                )
        except OSError:
            return None, REFUSAL_UNREADABLE
        if read_data is None:
            return None, REFUSAL_TOO_LARGE
        data = read_data
    else:
        try:
            zf = zipfile.ZipFile(source_root, "r")
        except _ZIP_ERRORS:
            return None, REFUSAL_UNREADABLE
        try:
            info = _locate_zip_member(zf, archive_path)
            if info is None:
                return None, REFUSAL_UNREADABLE
            if head_only:
                head = _read_zip_head(zf, info, limits)
                if head is None:
                    return None, REFUSAL_UNREADABLE
                data = head
            else:
                read = _read_zip_member(zf, info, limits)
                if read.data is None:
                    return None, read.reason or REFUSAL_UNREADABLE
                data = read.data
        finally:
            zf.close()

    if not head_only and hashlib.sha256(data).hexdigest() != entry.content_sha256:
        return None, REFUSAL_UNREADABLE

    decoded = decode_source_bytes(data, allow_partial_tail=head_only)
    if decoded is None:
        return None, REFUSAL_UNDECODABLE
    if head_only:
        decoded = DecodedSource(
            text=decoded.text,
            encoding=decoded.encoding,
            had_bom=decoded.had_bom,
            byte_count=decoded.byte_count,
            truncated=len(data) >= limits.head_bytes
            and len(data) < entry.size_bytes,
        )
    return decoded, None


def _locate_zip_member(
    zf: zipfile.ZipFile, archive_path: str
) -> zipfile.ZipInfo | None:
    """Find the member for an inventory path, re-deriving the stripped wrapper.

    The wrapper prefix is recomputed from the archive rather than remembered on
    the inventory, because :class:`~.inventory.ArchiveInventory` has no field for
    it and inventing one would change a contract this slice does not own.
    Recomputing is cheap (names only) and cannot drift from what the walk did,
    since it is the same function over the same input.
    """
    infos = [i for i in zf.infolist() if not i.is_dir()]
    prefix = common_root_prefix(i.filename for i in infos)
    wanted = f"{prefix}/{archive_path}" if prefix else archive_path
    for info in infos:
        verdict = _normalise_member_name(info.filename, ArchiveLimits())
        if verdict.archive_path == wanted:
            return info
    return None


def _read_zip_head(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, limits: ArchiveLimits
) -> bytes | None:
    """The first ``head_bytes`` of a member, without decompressing the rest."""
    probe = _probe_info(info, limits.head_bytes + 1)
    try:
        with zf.open(probe, "r") as stream:
            return stream.read(limits.head_bytes)
    except _ZIP_ERRORS:
        return None


def read_source_text(
    inventory: ArchiveInventory,
    archive_path: str,
    *,
    source_root: Path,
    limits: ArchiveLimits = ArchiveLimits(),
) -> tuple[str | None, str | None]:
    """``(text, refusal_reason)`` — exactly one of the two is set, always.

    Use :func:`read_source_decoded` when the caller wants to DISCLOSE which
    encoding produced the text, which any surface showing a value read through
    ``latin-1`` should.
    """
    decoded, reason = read_source_decoded(
        inventory, archive_path, source_root=source_root, limits=limits
    )
    return (decoded.text if decoded else None), reason


def read_source_head(
    inventory: ArchiveInventory,
    archive_path: str,
    *,
    source_root: Path,
    limits: ArchiveLimits = ArchiveLimits(),
) -> tuple[str | None, str | None]:
    """The first ``limits.head_bytes`` decoded, for a content-led classifier.

    The corpus is why a classifier needs this rather than the whole file:
    ``run29`` has no extension and is a MACRO, ``alignment`` has no extension and
    is a 1.6 MB SPEC ACQUISITION. Telling them apart needs the first line, not
    1.6 MB.
    """
    decoded, reason = read_source_decoded(
        inventory,
        archive_path,
        source_root=source_root,
        limits=limits,
        head_only=True,
    )
    return (decoded.text if decoded else None), reason
