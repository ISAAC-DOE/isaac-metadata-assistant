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
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

#: How many lines either side of a locator's line a quote may start on and still pass.
LINE_TOLERANCE = 3
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
NO_TEXT_LAYER = "no text layer; quote from a text copy or report it instead"
_PAGE_RE = re.compile(r"\bpages?\s*[: ]?\s*(?P<n>\d+)\b", re.I)
#: The most occurrences of one quote looked at when it is found away from the locator.
_MAX_HITS = 50

PASS = "pass"
FAIL = "fail"

#: ``line 12``, ``line:12``, ``lines 4-9``, ``lines 1379–1391``, ``lines 4..9``; never an Igor ``history line N``.
_LINE_RE = re.compile(r"(?<!history )\blines?\s*[: ]\s*(?P<first>\d+)(?:\s*(?:-|–|—|\.\.|to)\s*(?P<last>\d+))?", re.I)
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


def document_lines(path: Path, rel: str) -> tuple[list[str] | None, str | None]:
    """The extractor's text of a ``.docx``/``.pptx``/``.xlsx`` (every sheet paged to its end), as lines, or
    ``(None, why)``. Written to a temporary folder that is removed before this returns; no image is written."""
    from . import extract as X

    limits = dataclasses.replace(X.DEFAULT_LIMITS, max_images=0, max_total_image_bytes=0)
    lines: list[str] = []
    with tempfile.TemporaryDirectory(prefix="isaac-quote-check-") as tmp:
        out = Path(tmp)
        manifest = X.extract_source(path, out, source_relative_path=PurePosixPath(rel).name, limits=limits)
        if manifest.get("status") != X.STATUS_EXTRACTED:
            return None, f"the extractor did not read it ({manifest.get('status')}: {manifest.get('reason') or 'no text'})"
        files = [manifest.get("text_file")] if manifest.get("text_file") else []
        for sheet in manifest.get("sheets") or ():
            files.append(sheet.get("text_file"))
            rest, pages = sheet.get("read_rest"), 0
            while rest and pages < MAX_SHEET_PAGES:
                pages += 1
                page = X.SheetPage(sheet=rest["sheet"], rows_offset=rest["rows_offset"],
                                   rows_limit=min(int(rest["rows_limit"]), limits.max_page_rows) or limits.max_page_rows)
                more = X.extract_source(path, out, source_relative_path=PurePosixPath(rel).name, limits=limits, page=page)
                got = next((s for s in more.get("sheets") or () if s.get("name") == rest["sheet"]), None)
                if got is None:
                    break
                files.append(got.get("text_file"))
                nxt = got.get("read_rest")
                rest = nxt if nxt and nxt.get("rows_offset", 0) > rest["rows_offset"] else None
        for name in files:
            if name:
                lines += file_lines((out / name).read_text(encoding="utf-8", errors="replace"))
    if not lines:
        return None, "the extractor returned no text for it"
    return lines, None


def _text_of(path: Path, rel: str) -> _Text:
    suffix = path.suffix.lower()
    if suffix in EXTRACTED_SUFFIXES:
        lines, problem = document_lines(path, rel)
        return _Text(lines, "extractor", problem)
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


def check_one(finding: Any, root: Path, *, fid: str, sources_by_path: Mapping[str, Mapping] | None = None,
              cache: dict | None = None) -> dict:
    """One finding's result: ``{"finding", "path", "locator", "result": "pass"|"fail", "at"|"reason"}``."""
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
    if not isinstance(rel, str):
        return fail("the finding has no source.path")
    key = rel
    if key not in cache:
        path, problem = resolve_cited(root, rel)
        entry: Any = problem
        if path is not None:
            src = (sources_by_path or {}).get(rel)
            want = (src or {}).get("content_sha256")
            try:
                if want and _sha256(path) != want:
                    entry = "the file's bytes changed since the import: the quote is checked against the file the import read"
                else:
                    entry = _text_of(path, rel)
            except OSError as exc:
                entry = f"the file cannot be read ({type(exc).__name__})"
        cache[key] = entry
    entry = cache[key]
    if isinstance(entry, str):
        return fail(entry)
    if entry.via == "pdf":
        return _check_pdf(row, entry, quote, locator) if entry.pages is not None else fail(entry.problem or "the PDF has no text")
    if entry.lines is None:
        return fail(entry.problem or "the file has no text")
    lines = entry.lines
    line_match = _LINE_RE.search(locator)
    if entry.via == "extractor":
        idx = cache.setdefault(("index", key), _Index(lines))
        hits = idx.hits(quote)
        if hits:
            return {**row, "result": PASS, "at": f"the extractor's text of the document (its line {hits[0]})"}
        return fail("not found in the extractor's text of the document (whitespace, quotes and dashes compared plainly)")
    if line_match:
        first = int(line_match.group("first"))
        last = max(first, int(line_match.group("last") or first))
        if first < 1 or first > len(lines):
            return fail(f"the locator names line {first} and the file has {len(lines)} line(s)")
        idx = cache.setdefault(("index", key), _Index(lines))
        hits = idx.hits(quote)
        near = [h for h in hits if first - LINE_TOLERANCE <= h <= last + LINE_TOLERANCE]
        if near:
            span = f"line {first}" if last == first else f"lines {first}-{last}"
            where = "the line cited" if first <= near[0] <= last else f"within {LINE_TOLERANCE} lines of {span}"
            return {**row, "result": PASS, "at": f"line {near[0]} ({where})"}
        if hits:
            others = ", ".join(str(h) for h in hits[:5])
            return fail(f"not within {LINE_TOLERANCE} lines of line {first}: the quote is at line {others}. Fix the "
                        "locator to the line the quote is on")
        return fail(f"not found within {LINE_TOLERANCE} lines of line {first}, nor anywhere in the file "
                    "(whitespace, quotes and dashes compared plainly; case kept)")
    if _HEADER_RE.search(locator) or "header" in locator.lower():
        keep, numbers, how = _header_lines(lines, locator)
        hits = _Index(keep, numbers).hits(quote) if keep else []
        if hits:
            return {**row, "result": PASS, "at": f"line {hits[0]} ({how})"}
        return fail(f"not found in {how}")
    idx = cache.setdefault(("index", key), _Index(lines))
    hits = idx.hits(quote)
    if hits:
        return {**row, "result": PASS, "at": f"line {hits[0]} (the locator names no line: the whole file was searched)"}
    return fail("not found in the file (whitespace, quotes and dashes compared plainly; case kept)")


def check_findings(findings: Iterable[Any], root: Path, *, sources: Iterable[Mapping] = ()) -> list[dict]:
    """Every finding's result, in file order, ids as ``annotate --from-readings`` numbers them (``finding-001``)."""
    by_path = {s.get("relative_path"): s for s in sources if isinstance(s, Mapping)}
    cache: dict = {}
    return [check_one(f, Path(root), fid=f"finding-{i + 1:03d}", sources_by_path=by_path, cache=cache)
            for i, f in enumerate(findings)]


def report(results: list[dict], *, root_label: str | None) -> dict:
    """The printed report: counts, every failure in full, every pass on one short row."""
    failed = [r for r in results if r["result"] == FAIL]
    return {
        "checked": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "root": root_label,
        "statement": (
            (f"Every quote was found in its file, near its locator ({len(results)} checked). A pass says the quote is "
             "there, never that the reading is right." if not failed else
             f"{len(failed)} of {len(results)} quotes were not found as cited: those findings are not loaded. Fix each "
             "(the quote, verbatim, or its locator) in the findings file and load it again; there is no way to skip "
             "the check.") if results else "The findings file holds no finding."),
        "results": [({"finding": r["finding"], "result": PASS, "at": r["at"]} if r["result"] == PASS else r) for r in results],
    }
