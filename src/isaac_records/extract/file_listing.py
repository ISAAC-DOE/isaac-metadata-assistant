"""Deterministic parser for the raw scan file listing (``raw_scan_listing.txt``).

Turns a fake ``ls -R`` style listing (see ``tests/fixtures/synthetic``) into asset
candidates for the draft ``assets[]`` block, per ``docs/extraction.md`` (§1 line
parse, §2/§3 ``file_listing`` evidence, §5 asset destinations). It provides asset
**URIs** only and NEVER computes or invents a ``sha256`` — the hash is a downstream
``user_confirmation`` blocker (§4/§8), so :class:`AssetCandidate` has no sha256
field at all.

Public entry points:
  - :func:`parse_file_listing` — the list of :class:`AssetCandidate`.
  - :func:`archive_root` — the ``ssrl-archive://…`` root, for the 3B builder.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _field
from pathlib import Path

_ARCHIVE_SCHEME = "ssrl-archive://"

# Extension -> (content_role, media_type). The three recognized product kinds.
_RAW_EXT = ".h5"
_MEDIA_TYPES = {
    ".h5": "application/x-hdf5",
    ".xdi": "text/plain",
    ".ipynb": "application/x-ipynb+json",
}
_CONTENT_ROLE = {
    ".xdi": "reduction_product",
    ".ipynb": "processing_script",
}


@dataclass(frozen=True)
class AssetCandidate:
    """One asset candidate parsed from a file listing.

    Deliberately carries NO ``sha256`` — hashing is a downstream blocker resolved
    by ``/isaac-complete`` (docs/extraction.md §4/§8), never at extraction time.
    """

    asset_id: str
    content_role: str
    uri: str
    media_type: str | None = None
    evidence: tuple = _field(default_factory=tuple)


def _evidence(source_file: str, locator: str, quote: str | None) -> dict:
    """One ``file_listing`` evidence entry (models.evidence shape; drops Nones)."""
    entry = {
        "source_type": "file_listing",
        "source_file": source_file,
        "locator": locator,
        "quote": quote,
    }
    return {k: v for k, v in entry.items() if v is not None}


def _read_listing(path: Path):
    """Parse the listing into ``(root, header_line, entries)``.

    ``root`` is the shortest ``ssrl-archive://`` directory header (the archive
    root); ``header_line`` maps each directory URI to the 1-based line its header
    appears on; ``entries`` is a list of ``(dir_uri, filename, line_no)`` for FILE
    lines only (sub-directory names, ending in ``/``, are dropped).
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    current_dir: str | None = None
    header_line: dict[str, int] = {}
    roots: list[str] = []
    entries: list[tuple[str, str, int]] = []
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            current_dir = None
            continue
        if line.startswith("#"):
            continue
        if line.startswith(_ARCHIVE_SCHEME) and line.endswith(":"):
            current_dir = line[:-1]  # strip the trailing ':'
            header_line.setdefault(current_dir, line_no)
            roots.append(current_dir)
            continue
        if current_dir is not None and not line.endswith("/"):
            entries.append((current_dir, line, line_no))
    root = min(roots, key=len) if roots else None
    return root, header_line, entries


def archive_root(path) -> str | None:
    """Return the ``ssrl-archive://…`` archive root, or ``None`` if none is listed."""
    root, _, _ = _read_listing(Path(path))
    return root


def parse_file_listing(path) -> list[AssetCandidate]:
    """Parse the file listing into asset candidates.

    Recognizes three product kinds by extension:
      - ``raw/*.h5``      -> ONE ``raw_data_pointer`` per raw directory (the scan
        set), ``uri`` = the raw directory URI;
      - ``reduced/*.xdi`` -> a ``reduction_product`` (uri = the file);
      - ``notebooks/*.ipynb`` -> a ``processing_script`` (uri = the file).

    Each candidate carries one ``file_listing`` evidence entry and no ``sha256``.
    """
    path = Path(path)
    source_file = path.name
    _root, header_line, entries = _read_listing(path)

    candidates: list[AssetCandidate] = []
    raw_dirs: dict[str, list[tuple[str, int]]] = {}

    for dir_uri, name, line_no in entries:
        ext = Path(name).suffix.lower()
        if ext == _RAW_EXT:
            raw_dirs.setdefault(dir_uri, []).append((name, line_no))
        elif ext in _CONTENT_ROLE:
            uri = dir_uri + name  # dir_uri ends with '/'
            locator = f"line {line_no}, {dir_uri}"
            candidates.append(
                AssetCandidate(
                    asset_id=Path(name).stem,
                    content_role=_CONTENT_ROLE[ext],
                    uri=uri,
                    media_type=_MEDIA_TYPES.get(ext),
                    evidence=(_evidence(source_file, locator, name),),
                )
            )

    # One raw_data_pointer per raw directory, pointing at the directory (the whole
    # scan set), evidenced by the directory header and a representative listed file.
    for dir_uri, files in raw_dirs.items():
        first_name, first_line = files[0]
        cite_line = header_line.get(dir_uri, first_line)
        locator = f"line {cite_line}, {dir_uri}"
        candidates.append(
            AssetCandidate(
                asset_id="raw_scan_set",
                content_role="raw_data_pointer",
                uri=dir_uri,
                media_type=_MEDIA_TYPES.get(_RAW_EXT),
                evidence=(_evidence(source_file, locator, first_name),),
            )
        )

    return candidates


__all__ = ["AssetCandidate", "parse_file_listing", "archive_root"]
