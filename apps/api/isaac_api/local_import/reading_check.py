"""THE QUOTE CHECK: every finding of a reading pass is held against the file it cites. Reads only; writes nothing.

A Claude reading pass (``isaac.reading_findings``, ``bundle annotate --from-readings``) cites, for each finding, a
file under the imported folder, a locator and a verbatim quote. This module checks the quote mechanically, so a
misremembered or invented quote never reaches a bundle as an AI reading:

* **Plain text** (a logbook ``.txt``, a readme, a SPEC file, a macro): the quote must occur within
  :data:`LINE_TOLERANCE` lines of the line a ``line N`` / ``lines N-M`` locator names. A quote found ELSEWHERE in the
  file fails, and the result says the line it was found at, so the reader fixes the locator. A SPEC header locator
  with no line (``#C``, ``scan 5 #C``) is checked against the file's ``#`` header lines (that scan's, when it names
  one). A locator that names no line is checked against the whole file.
* **Documents** (``.docx`` / ``.pptx`` / ``.xlsx``): against :mod:`isaac_api.local_import.extract`'s text, the text a
  reader is told to read, produced again here in a temporary folder that is removed afterwards (images are not
  written; every sheet is paged to its end).
* **PDFs**: against the text layer ``pypdf`` (the ``reading`` extra) gives, page by page. A ``page N`` locator is
  checked on that page and fails when the quote is on another page (saying which); any other locator searches the
  whole document and reports the page. A page with no text layer (a scan) cannot be checked, and neither can any
  PDF without ``pypdf`` installed: the finding fails, saying why.
* **Comparison**: whitespace runs collapse to one space; non-breaking spaces, curly quotes and dashes compare as
  their plain forms (:func:`normalise`). Case is kept: a quote is verbatim.
* **The path**: relative to the imported folder. An absolute path, a ``..`` part (a file beside the folder too), a
  symbolic link anywhere along the path, or anything that is not a regular file is refused. When the cited file is
  one of the bundle's sources, its bytes must still be the ones the import read (``content_sha256``).

The check is a property of ``annotate --from-readings`` (its preview reports it per finding, its ``--apply`` records
no finding that fails it; there is no flag to skip it) and of ``bundle check-readings`` (the same report alone).
A pass says the quote is in the file near where the reader said: never that the reading is right.
"""

from __future__ import annotations

import bisect
import dataclasses
import hashlib
import os
import re
import unicodedata
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

#: How many lines either side of a locator's line a quote may start on and still pass.
LINE_TOLERANCE = 3
#: The widest ``lines N-M`` range a locator may name: a wider one would let almost any quote pass.
MAX_LINE_SPAN = 20
#: A quote shorter than BOTH of these could match by chance (``K``, ``in situ``): it fails.
MIN_QUOTE_WORDS = 3
MIN_QUOTE_CHARS = 12
#: ... unless it is (nearly) a WHOLE short line: its locator names one line or at most this many, and the quote
#: covers at least :data:`SHORT_QUOTE_LINE_SHARE` of one of those lines' normalised text ("Ar sat" as its own line).
SHORT_QUOTE_MAX_LINES = 3
SHORT_QUOTE_LINE_SHARE = 0.8
#: The most bytes of one cited plain-text file read for the check.
MAX_TEXT_BYTES = 64 << 20
#: Documents whose text is the extractor's.
EXTRACTED_SUFFIXES = (".docx", ".pptx", ".xlsx")
#: The most pages of one sheet the check reads (each at most ``Limits.max_page_rows`` rows).
MAX_SHEET_PAGES = 200
#: The most pages of one PDF read for the check.
MAX_PDF_PAGES = 2_000
#: How to install the PDF reader, said when it is missing.
PDF_INSTALL = 'scripts/setup_isaac_local.sh (or: .venv/bin/python -m pip install -e ".[reading]")'
NO_TEXT_LAYER = "no text layer, so its quotes cannot be checked: tell the scientist what the page says instead"
_PAGE_RE = re.compile(r"(?<![A-Za-z])(?:pages?|pp?\.)\s*[:#]?\s*(?P<n>\d+)\b", re.I)
#: The most occurrences of one quote looked at when it is found away from the locator.
_MAX_HITS = 50

PASS = "pass"
FAIL = "fail"

#: A line reference in every form a reader writes: ``line 12``, ``line:12``, ``line12``, ``Line #12``, ``l. 12``,
#: ``ll. 4-9``, ``lines 4-9``, ``lines 1379–1391``, ``lines 4..9``, ``lines 4 to 9``, ``row 12`` (a text file's row is
#: its line); never an Igor ``history line N``, and never a bare ``L`` + number: ``L3`` in ``Ir L3-edge note, line 151``
#: is an absorption edge, not line 3 (``l.`` needs its dot). A locator holding a number that is none of these FAILS.
_LINE_RE = re.compile(
    r"(?<![A-Za-z])(?<!history )(?:lines?|rows?|ll?\.)\s*[.:#]?\s*#?\s*(?P<first>\d+)"
    r"(?:\s*(?:-|–|—|\.\.|to)\s*(?P<last>\d+))?(?!\d)", re.I)
#: A document locator the extractor's text can be held to: a paragraph, a table, a slide, a sheet's row.
_DOC_RE = re.compile(r"(?<![A-Za-z])(?P<kind>paragraphs?|paras?\.?|¶|tables?|slides?|rows?)\s*[.:#]?\s*#?\s*(?P<n>\d+)\b", re.I)
_SHEET_RE = re.compile(r"\bsheet\s*[:=]?\s*(?:\"(?P<q>[^\"]+)\"|'(?P<s>[^']+)'|(?P<w>[^\s,;]+))", re.I)
#: A SPEC header named in a locator: ``#C``, ``#S 5``, ``header #O3``.
_HEADER_RE = re.compile(r"#(?P<key>[A-Za-z]{1,3})\d*\b")
#: The scan a header locator names: ``scan 5`` or ``#S 5``.
_SCAN_RE = re.compile(r"(?:\bscan\s+|#S\s+)(?P<n>\d+)\b", re.I)
_LINE_BREAK_RE = re.compile(r"\r\n|\r|\n")
_PLAIN = str.maketrans({
    " ": " ", " ": " ", " ": " ", " ": " ", "\t": " ",
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    "﻿": None, "​": None,
})
_SPACE_RE = re.compile(r"\s+")


def normalise(text: Any) -> str:
    """``text`` as quotes are compared: plain spaces, quotes and dashes, whitespace runs collapsed, trimmed."""
    return _SPACE_RE.sub(" ", str(text).translate(_PLAIN)).strip()


def file_lines(text: str) -> list[str]:
    """``text``'s lines as the readers number them (``\\r\\n``, ``\\r``, ``\\n``; a final break ends the last line)."""
    lines = _LINE_BREAK_RE.split(text)
    return lines[:-1] if lines and lines[-1] == "" else lines


class _Index:
    """The normalised text of a list of lines, joined by one space, with where each line starts in it."""

    def __init__(self, lines: list[str], numbers: list[int] | None = None):
        self.starts: list[int] = []
        self.numbers: list[int] = []
        parts: list[str] = []
        at = 0
        for i, line in enumerate(lines):
            n = normalise(line)
            if not n:
                continue
            if parts:
                at += 1
            self.starts.append(at)
            self.numbers.append(numbers[i] if numbers is not None else i + 1)
            parts.append(n)
            at += len(n)
        self.text = " ".join(parts)

    def hits(self, quote: str) -> list[int]:
        """The line numbers each occurrence of ``quote`` STARTS on (at most :data:`_MAX_HITS`)."""
        out, pos = [], self.text.find(quote)
        while pos >= 0 and len(out) < _MAX_HITS:
            k = bisect.bisect_right(self.starts, pos) - 1
            out.append(self.numbers[k] if k >= 0 else 1)
            pos = self.text.find(quote, pos + 1)
        return out


@dataclasses.dataclass
class _Text:
    lines: list[str] | None
    via: str  # "text" | "extractor" | "pdf"
    problem: str | None = None
    pages: list[str] | None = None  # a PDF's text, one string per page ("" for a page with no text layer)
    units: list[dict] | None = None  # a document's paragraphs, tables, slides or sheet rows (``document_units``)


def _entry_named(parent: Path, part: str) -> str | None:
    """The name ``part`` has in folder ``parent``, as the folder spells it: itself, its Unicode-normalised twin (macOS
    stores names decomposed), or, only where the file system itself finds ``part`` (a case-insensitive one), the one
    entry that differs from it in case alone. ``None`` when there is no such entry."""
    try:
        names = os.listdir(parent)
    except OSError:
        return None
    if part in names:
        return part
    nfc = unicodedata.normalize("NFC", part)
    same = [n for n in names if unicodedata.normalize("NFC", n) == nfc]
    if len(same) == 1:
        return same[0]
    if (parent / part).exists():
        folded = [n for n in names if unicodedata.normalize("NFC", n).casefold() == nfc.casefold()]
        if len(folded) == 1:
            return folded[0]
    return None


def canonical_cited(root: Path, rel: str) -> tuple[Path | None, str | None, str | None]:
    """``(path, canonical, None)`` for a cited path that is a regular file under ``root`` reached through no symbolic
    link, ``canonical`` its path relative to ``root`` as the folder spells it (``./a.txt``, ``a.txt/`` and, on a
    case-insensitive disk, ``A.TXT`` are all ``a.txt``: the bundle's sources are looked up by it), else
    ``(None, None, why)``."""
    path, why = resolve_cited(root, rel)
    if path is None:
        return None, None, why
    parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".")]
    here, actual = Path(root), []
    for part in parts:
        name = _entry_named(here, part)
        if name is None:
            return None, None, "no such file in the imported folder"
        actual.append(name)
        here = here / name
    return here, "/".join(actual), None


def resolve_cited(root: Path, rel: str) -> tuple[Path | None, str | None]:
    """``(path, None)`` for a cited path that is a regular file under ``root`` reached through no symbolic link,
    else ``(None, why)``."""
    if not isinstance(rel, str) or not rel.strip():
        return None, "source.path is empty"
    if "\x00" in rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        return None, "source.path must be relative to the imported folder, never absolute"
    parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts:
        return None, "source.path names no file"
    if ".." in parts:
        return None, ("source.path leaves the imported folder (a `..` part): only files inside it can be quote-checked, "
                      "so a finding citing a file beside it is not loaded; tell the scientist what that file says instead")
    try:
        base = Path(root)
        if base.is_symlink() or not base.is_dir():
            return None, ("the imported folder is not a folder here (after a ZIP import, unzip it and pass the folder "
                          "with --root)")
        here = base
        for k, part in enumerate(parts, 1):
            here = here / part
            if here.is_symlink():
                return None, f"source.path goes through a symbolic link ({PurePosixPath(*parts[:k])}); it is not followed"
        if not here.exists():
            return None, "no such file in the imported folder"
        if not here.is_file():
            return None, "source.path is not a regular file"
        resolved, top = here.resolve(), base.resolve()
        if resolved != top and top not in resolved.parents:
            return None, "source.path resolves outside the imported folder"
    except OSError as exc:
        return None, f"the file cannot be opened ({type(exc).__name__})"
    return here, None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _plain_text(path: Path) -> _Text:
    size = path.stat().st_size
    if size > MAX_TEXT_BYTES:
        return _Text(None, "text", f"the file is {size:,} bytes, over the {MAX_TEXT_BYTES:,}-byte bound of the quote check")
    raw = path.read_bytes()
    if b"\x00" in raw[:8192]:
        return _Text(None, "text", "the file is not text (a NUL byte) and not a document the extractor reads")
    return _Text(file_lines(_decode(raw)), "text")


def document_units(path: Path, rel: str) -> tuple[list[dict] | None, str | None]:
    """The extractor's text of a ``.docx``/``.pptx``/``.xlsx`` as units a locator can name, or ``(None, why)``:
    ``{"kind": "paragraph"|"table"|"slide"|"row", "n": int, "alt": [other numbers it may be cited by], "sheet",
    "text"}``. A paragraph is numbered both as the document counts it and as the extractor's text shows it (empty
    ones left out); a table both from 1 and as the text file labels it (from 0); every sheet is paged to its end.
    Run in a temporary folder that is removed before this returns; no image is written."""
    from . import extract as X

    limits = dataclasses.replace(X.DEFAULT_LIMITS, max_images=0, max_total_image_bytes=0)
    units: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="isaac-quote-check-") as tmp:
        out = Path(tmp)
        name = PurePosixPath(rel).name
        manifest = X.extract_source(path, out, source_relative_path=name, limits=limits)
        if manifest.get("status") != X.STATUS_EXTRACTED:
            return None, f"the extractor did not read it ({manifest.get('status')}: {manifest.get('reason') or 'no text'})"
        shown = 0
        for b in manifest.get("blocks") or ():
            if b.get("type") == "paragraph":
                if (b.get("text") or "").strip():
                    shown += 1
                    units.append({"kind": "paragraph", "n": int(b.get("paragraph_index") or 0) + 1, "alt": [shown],
                                  "text": b["text"]})
            elif b.get("type") == "table":
                t = int(b.get("table_index") or 0)
                units.append({"kind": "table", "n": t + 1, "alt": [t],
                              "text": " ".join(" | ".join(c for c in row) for row in b.get("rows") or ())})
            elif b.get("type") == "slide":
                parts = []
                for sh in b.get("shapes") or ():
                    if sh.get("type") == "text":
                        parts.append(sh.get("text") or "")
                    elif sh.get("type") == "table":
                        parts += [" | ".join(row) for row in sh.get("rows") or ()]
                if b.get("speaker_notes"):
                    parts.append(b["speaker_notes"])
                units.append({"kind": "slide", "n": int(b.get("slide") or 0), "alt": [], "text": " ".join(parts)})

        def rows_of(sheet: Mapping) -> None:
            for r in sheet.get("preview_rows") or ():
                units.append({"kind": "row", "n": int(r.get("row") or 0), "alt": [], "sheet": sheet.get("name"),
                              "text": " | ".join(X._sheet_cell_text(c) for c in r.get("cells") or ())})

        for sheet in manifest.get("sheets") or ():
            rows_of(sheet)
            rest, pages = sheet.get("read_rest"), 0
            while rest and pages < MAX_SHEET_PAGES:
                pages += 1
                page = X.SheetPage(sheet=rest["sheet"], rows_offset=rest["rows_offset"],
                                   rows_limit=min(int(rest["rows_limit"]), limits.max_page_rows) or limits.max_page_rows)
                more = X.extract_source(path, out, source_relative_path=name, limits=limits, page=page)
                got = next((x for x in more.get("sheets") or () if x.get("name") == rest["sheet"]), None)
                if got is None:
                    break
                rows_of(got)
                nxt = got.get("read_rest")
                rest = nxt if nxt and nxt.get("rows_offset", 0) > rest["rows_offset"] else None
    if not any(normalise(u["text"]) for u in units):
        return None, "the extractor returned no text for it"
    return units, None


def _text_of(path: Path, rel: str) -> _Text:
    suffix = path.suffix.lower()
    if suffix in EXTRACTED_SUFFIXES:
        units, problem = document_units(path, rel)
        return _Text([] if units is not None else None, "extractor", problem, units=units)
    if suffix == ".pdf":
        pages, problem = pdf_pages(path)
        return _Text([], "pdf", problem, pages)
    return _plain_text(path)


def pdf_pages(path: Path) -> tuple[list[str] | None, str | None]:
    """A PDF's text layer, one string per page (``""`` where a page has none), or ``(None, why)``. Needs ``pypdf``
    (the ``reading`` extra); it reads the file and runs nothing in it."""
    try:
        import pypdf
    except ImportError:
        return None, f"reading a PDF's text needs the PDF reader (pypdf), which is not installed. Install it: {PDF_INSTALL}"
    try:
        reader = pypdf.PdfReader(str(path))
        if reader.is_encrypted:
            return None, "the PDF is encrypted, so its text cannot be read for the check"
        if len(reader.pages) > MAX_PDF_PAGES:
            return None, f"the PDF has {len(reader.pages):,} pages, over the {MAX_PDF_PAGES:,}-page bound of the quote check"
        return [(page.extract_text() or "") for page in reader.pages], None
    except Exception as exc:  # a malformed PDF: pypdf raises many kinds; never a crash, always a reason
        return None, f"the PDF could not be read ({type(exc).__name__})"


def _check_pdf(row: dict, entry: _Text, quote: str, locator: str) -> dict:
    pages = entry.pages or []
    texts = [normalise(p) for p in pages]
    found = [i + 1 for i, t in enumerate(texts) if quote in t]
    wanted = _PAGE_RE.search(locator)
    if wanted:
        n = int(wanted.group("n"))
        if n < 1 or n > len(pages):
            return {**row, "result": FAIL, "reason": f"the locator names page {n} and the PDF has {len(pages)} page(s)"}
        if not texts[n - 1]:
            return {**row, "result": FAIL, "reason": f"page {n}: {NO_TEXT_LAYER}"}
        if n in found:
            return {**row, "result": PASS, "at": f"page {n} of the PDF's text (the page cited)"}
        if found:
            return {**row, "result": FAIL, "reason": (f"not on page {n}: the quote is on page {', '.join(map(str, found[:5]))}. "
                                                      "Fix the locator to the page the quote is on")}
        return {**row, "result": FAIL, "reason": f"not found on page {n}, nor anywhere in the PDF's text"}
    if re.search(r"\d", locator):
        return {**row, "result": FAIL, "reason": (f"the locator ({locator[:80]}) holds a number but is not a page reference: "
                                                  "write `page N`, or a locator with no number to search the whole PDF")}
    if found:
        return {**row, "result": PASS, "at": f"page {found[0]} of the PDF's text (the locator names no page: the whole PDF was searched)"}
    if not any(texts):
        return {**row, "result": FAIL, "reason": f"every page: {NO_TEXT_LAYER}"}
    blank = sum(1 for t in texts if not t)
    return {**row, "result": FAIL, "reason": ("not found in the PDF's text" + (
        f" ({blank} of its {len(pages)} pages have no text layer: {NO_TEXT_LAYER})" if blank else ""))}


def _header_lines(lines: list[str], locator: str) -> tuple[list[str], list[int], str]:
    """The ``#`` header lines a SPEC header locator names (one scan's when it names one), their numbers, and how."""
    scan = _SCAN_RE.search(locator)
    want = int(scan.group("n")) if scan else None
    keep, numbers, inside = [], [], want is None
    for i, line in enumerate(lines, 1):
        s = line.lstrip()
        if s.startswith("#S"):
            m = re.match(r"#S\s+(\d+)", s)
            inside = want is None or bool(m and int(m.group(1)) == want)
        if inside and s.startswith("#"):
            keep.append(line)
            numbers.append(i)
    how = f"the header lines of scan {want}" if want is not None else "the file's header lines"
    return keep, numbers, how


#: A SPEC header line's key: ``#C``, ``#O3``.
_HEADER_LINE_KEY = re.compile(r"#(?P<key>[A-Za-z]{1,3})\d*\s*")


def _header_keys(locator: str) -> list[str]:
    """The SPEC header keys a locator names (``scan 2 #C`` -> ``["C"]``); ``#S`` only names the scan, unless it is
    the only key."""
    keys = list(dict.fromkeys(m.group("key") for m in _HEADER_RE.finditer(locator)))
    return [k for k in keys if k != "S"] or keys


def line_locator(locator: str) -> tuple[int, int] | None:
    """``(first, last)`` of the line reference a locator holds (:data:`_LINE_RE`), or ``None``."""
    m = _LINE_RE.search(locator)
    if not m:
        return None
    first = int(m.group("first"))
    return first, int(m.group("last") or first)


def _check_document(row: dict, units: list[dict], quote: str, locator: str) -> dict:
    """A ``.docx``/``.pptx``/``.xlsx`` quote: on the unit its locator names (a paragraph, table, slide or sheet row),
    else anywhere in the document, said as "found in document, locator not checked"."""
    def where(u: Mapping) -> str:
        return f"{u['kind']} {u['n']}" + (f" of sheet {u['sheet']!r}" if u.get("sheet") else "")

    found = [u for u in units if quote in normalise(u["text"])]
    whole = quote in normalise(" ".join(u["text"] for u in units))
    m = _DOC_RE.search(locator)
    if m:
        kind = m.group("kind").lower().rstrip(".s")
        kind = {"para": "paragraph", "¶": "paragraph"}.get(kind, kind)
        n = int(m.group("n"))
        sheet = _SHEET_RE.search(locator)
        sheet_name = (sheet.group("q") or sheet.group("s") or sheet.group("w")) if sheet else None
        named = [u for u in units if u["kind"] == kind and (u["n"] == n or n in u["alt"])
                 and (sheet_name is None or str(u.get("sheet")) == sheet_name)]
        if named:
            hit = next((u for u in named if u in found), None)
            if hit is not None:
                return {**row, "result": PASS, "at": f"{where(hit)} of the extractor's text (the {kind} cited)"}
            said = ", ".join(where(u) for u in found[:3])
            return {**row, "result": FAIL, "reason": (f"not in {kind} {n} of the extractor's text" + (
                f": the quote is in {said}. Fix the locator" if said else ", nor in any one part of the document"))}
        held = [u for u in units if u["kind"] == kind]
        if held:
            return {**row, "result": FAIL, "reason": (f"the extractor's text of the document has no {kind} {n}"
                                                     + (f" in sheet {sheet_name!r}" if sheet_name else "")
                                                     + f" ({len(held)} {kind}(s)): fix the locator")}
        # the document has no part of that kind (a .docx has no rows, a sheet no paragraphs): the locator is not checked
    if found or whole:
        at = where(found[0]) if found else "across parts"
        return {**row, "result": PASS, "at": f"found in document, locator not checked ({at} of the extractor's text)"}
    return {**row, "result": FAIL, "reason": "not found in the extractor's text of the document (whitespace, quotes and dashes compared plainly)"}


def check_one(finding: Any, root: Path, *, fid: str, sources_by_path: Mapping[str, Mapping] | None = None,
              cache: dict | None = None) -> dict:
    """One finding's result: ``{"finding", "path", "locator", "result": "pass"|"fail", "at"|"reason"}``, with
    ``canonical_path`` (the path as the folder spells it) once it resolves, and ``source_not_imported: true`` when
    ``sources_by_path`` is given and the file is none of them (no hash ties it to what the import read)."""
    cache = {} if cache is None else cache
    f = finding if isinstance(finding, Mapping) else {}
    source = f.get("source") if isinstance(f.get("source"), Mapping) else {}
    rel, locator = source.get("path"), str(source.get("locator") or "")
    row: dict = {"finding": fid, "path": rel, "locator": locator or None}

    def fail(reason: str) -> dict:
        return {**row, "result": FAIL, "reason": reason}

    quote = normalise(f.get("quote") or "")
    if not quote:
        return fail("the finding has no quote")
    short = len(quote.split()) < MIN_QUOTE_WORDS and len(quote) < MIN_QUOTE_CHARS
    too_short = (f"the quote is too short to tell apart (at least {MIN_QUOTE_WORDS} words or {MIN_QUOTE_CHARS} "
                 f"characters), unless it is a whole short line cited by its own line (`line N`, or a range of at most "
                 f"{SHORT_QUOTE_MAX_LINES} lines): quote more, verbatim")
    if not isinstance(rel, str):
        return fail("the finding has no source.path")
    if ("path", rel) not in cache:
        cache[("path", rel)] = canonical_cited(root, rel)
    path, canonical, problem = cache[("path", rel)]
    if path is None:
        return fail(problem or "the file cannot be opened")
    row["canonical_path"] = canonical
    src = (sources_by_path or {}).get(canonical)
    if sources_by_path and src is None:
        row["source_not_imported"] = True
    if canonical not in cache:
        want = (src or {}).get("content_sha256")
        try:
            if want and _sha256(path) != want:
                entry: Any = "the file's bytes changed since the import: the quote is checked against the file the import read"
            else:
                entry = _text_of(path, canonical)
        except OSError as exc:
            entry = f"the file cannot be read ({type(exc).__name__})"
        cache[canonical] = entry
    entry = cache[canonical]
    if isinstance(entry, str):
        return fail(entry)
    span = line_locator(locator)
    # a short quote is checked only against a few lines a locator names: `line N` (at most SHORT_QUOTE_MAX_LINES),
    # or a SPEC header key (`scan 2 #C`): that scan's lines of that key
    header_keys = _header_keys(locator) if span is None else []
    if short and not (entry.via == "text" and entry.lines is not None
                      and ((span and span[1] - span[0] + 1 <= SHORT_QUOTE_MAX_LINES) or header_keys)):
        return fail(too_short)
    if entry.via == "pdf":
        return _check_pdf(row, entry, quote, locator) if entry.pages is not None else fail(entry.problem or "the PDF has no text")
    if entry.via == "extractor":
        return _check_document(row, entry.units, quote, locator) if entry.units else fail(entry.problem or "the document has no text")
    if entry.lines is None:
        return fail(entry.problem or "the file has no text")
    lines = entry.lines
    if span:
        first, last = span
        if last < first:
            return fail(f"the locator's range ends (line {last}) before it starts (line {first})")
        if last - first + 1 > MAX_LINE_SPAN:
            return fail(f"the locator's range of {last - first + 1} lines is too wide to check (at most {MAX_LINE_SPAN}): "
                        "cite the line the quote starts on")
        if first < 1 or first > len(lines):
            return fail(f"the locator names line {first} and the file has {len(lines)} line(s)")
        if short:
            # A SHORT QUOTE PASSES ONLY AS (NEARLY) A WHOLE LINE THE LOCATOR NAMES: never a fragment of a longer line
            for n in range(first, min(last, len(lines)) + 1):
                text = normalise(lines[n - 1])
                if quote in text and len(quote) >= SHORT_QUOTE_LINE_SHARE * len(text):
                    return {**row, "result": PASS, "at": f"line {n} (the line cited; a short quote, the whole line)"}
            return fail(f"the quote is too short to tell apart (at least {MIN_QUOTE_WORDS} words or {MIN_QUOTE_CHARS} "
                        f"characters) and is only part of the line cited (a short quote must be at least "
                        f"{SHORT_QUOTE_LINE_SHARE:.0%} of its line): quote more of the line, verbatim")
        idx = cache.setdefault(("index", canonical), _Index(lines))
        hits = idx.hits(quote)
        near = [h for h in hits if first - LINE_TOLERANCE <= h <= last + LINE_TOLERANCE]
        if near:
            named = f"line {first}" if last == first else f"lines {first}-{last}"
            said = "the line cited" if first <= near[0] <= last else f"within {LINE_TOLERANCE} lines of {named}"
            return {**row, "result": PASS, "at": f"line {near[0]} ({said})"}
        if hits:
            others = ", ".join(str(h) for h in hits[:5])
            return fail(f"not within {LINE_TOLERANCE} lines of line {first}: the quote is at line {others}. Fix the "
                        "locator to the line the quote is on")
        return fail(f"not found within {LINE_TOLERANCE} lines of line {first}, nor anywhere in the file "
                    "(whitespace, quotes and dashes compared plainly; case kept)")
    if _HEADER_RE.search(locator) or "header" in locator.lower():
        keep, numbers, how = _header_lines(lines, locator)
        if short:
            # A SHORT QUOTE PASSES ONLY AS (NEARLY) THE WHOLE TEXT OF ONE CITED HEADER LINE (`#C Ar sat` for "Ar sat")
            for line, n in zip(keep, numbers):
                m = _HEADER_LINE_KEY.match(line.strip())
                body = normalise(line.strip()[m.end():]) if m and m.group("key") in header_keys else ""
                if body and quote in body and len(quote) >= SHORT_QUOTE_LINE_SHARE * len(body):
                    return {**row, "result": PASS, "at": f"line {n} ({how}; a short quote, the whole #{m.group('key')} line)"}
            return fail(f"the quote is too short to tell apart (at least {MIN_QUOTE_WORDS} words or {MIN_QUOTE_CHARS} "
                        f"characters) and is not the whole text of a {' / '.join('#' + k for k in header_keys)} line in "
                        f"{how}: quote more of the line, verbatim")
        hits = _Index(keep, numbers).hits(quote) if keep else []
        if hits:
            return {**row, "result": PASS, "at": f"line {hits[0]} ({how})"}
        return fail(f"not found in {how}")
    if re.search(r"\d", locator):
        return fail(f"the locator ({locator[:80]}) holds a number but is not a line reference: write `line N` (or "
                    f"`lines N-M`, at most {MAX_LINE_SPAN} lines) for the line the quote is on")
    idx = cache.setdefault(("index", canonical), _Index(lines))
    hits = idx.hits(quote)
    if hits:
        return {**row, "result": PASS, "at": f"line {hits[0]} (the locator names no line: the whole file was searched)"}
    return fail("not found in the file (whitespace, quotes and dashes compared plainly; case kept)")


#: How many imported sources (smallest first) :func:`holds_an_imported_source` hashes before it gives up.
MAX_ROOT_PROBES = 20


def holds_an_imported_source(root: Path, sources: Iterable[Mapping]) -> bool:
    """Whether ``root`` holds at least one of the bundle's sources with the bytes the import read (its path under
    ``root`` and its ``content_sha256``): what ties a ``--root`` to the bundle when it records no root. The
    :data:`MAX_ROOT_PROBES` smallest sources present under ``root`` are hashed, through :func:`resolve_cited` (no
    symbolic link, nothing outside ``root``)."""
    hashed = sorted((s for s in sources if isinstance(s, Mapping) and s.get("content_sha256")
                     and isinstance(s.get("relative_path"), str)), key=lambda s: int(s.get("size_bytes") or 0))
    probed = 0
    for s in hashed:
        path, _ = resolve_cited(Path(root), s["relative_path"])
        if path is None:
            continue
        probed += 1
        try:
            if _sha256(path) == s["content_sha256"]:
                return True
        except OSError:
            pass
        if probed >= MAX_ROOT_PROBES:
            break
    return False


def check_findings(findings: Iterable[Any], root: Path, *, sources: Iterable[Mapping] = ()) -> list[dict]:
    """Every finding's result, in file order, ids as ``annotate --from-readings`` numbers them (``finding-001``)."""
    by_path = {s.get("relative_path"): s for s in sources if isinstance(s, Mapping)}
    cache: dict = {}
    return [check_one(f, Path(root), fid=f"finding-{i + 1:03d}", sources_by_path=by_path, cache=cache)
            for i, f in enumerate(findings)]


def report(results: list[dict], *, root_label: str | None) -> dict:
    """The printed report: counts, every failure in full, every pass on one short row."""
    failed = [r for r in results if r["result"] == FAIL]
    loose = sum(1 for r in results if r.get("source_not_imported"))

    def short(r: Mapping) -> dict:
        if r["result"] != PASS:
            return dict(r)
        out = {"finding": r["finding"], "result": PASS, "at": r["at"]}
        if r.get("canonical_path") and r["canonical_path"] != r.get("path"):
            out["canonical_path"] = r["canonical_path"]
        if r.get("source_not_imported"):
            out["source_not_imported"] = True
        return out

    return {
        "checked": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "root": root_label,
        **({"source_not_imported": loose,
            "source_not_imported_note": ("files under the folder that are none of the bundle's sources (added or changed "
                                         "after the import, or a file it refused): no hash ties their text to what the "
                                         "import read; say so when you report what they hold")} if loose else {}),
        "statement": (
            (f"Every quote was found in its file, near its locator ({len(results)} checked). A pass says the quote is "
             "there, never that the reading is right." if not failed else
             f"{len(failed)} of {len(results)} quotes were not found as cited: those findings are not loaded. Fix each "
             "(the quote, verbatim, or its locator) in the findings file and load it again; there is no way to skip "
             "the check.") if results else "The findings file holds no finding."),
        "results": [short(r) for r in results],
    }
