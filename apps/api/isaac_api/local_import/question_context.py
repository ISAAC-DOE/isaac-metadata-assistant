"""BEAMTIME CONTEXT for a consolidated question: what the files, the logbook readings and the processing hold that
helps a scientist answer it. EVIDENCE, NEVER A VALUE.

``bundle questions`` (compact), ``bundle show question`` (full) and the local-only Local Imports page add a
``context`` list to each question: at most :data:`MAX_ITEMS` items, each ``{kind, label, source, ...}``. It is
ADDITIVE: a question's id, blocking status, counts and ``text`` are exactly as before, nothing is set, chosen or
suggested by it, and it is computed after the counts and the paging. Every item says where it came from
(``source``); an AI reading is said to be one ("not file evidence").

Item kinds (:data:`KINDS`):

* ``quote``: one source text line, verbatim, with its file (``path``) and ``locator``: from an AI reading of the
  files (``origin: ai_reading``; its quote as the reader gave it), the parser's evidence (``origin: parser``), or a
  line of a document the extract tool read (``origin: document``).
* ``values``: a small table (``columns``, ``rows``, ``rows_total``) of what the files hold for the question's runs:
  each run's potential as its name writes it, filter, emission energy, stage position Sx/Sy/Sz, scan files, the
  ``#D`` local time beside the ``#E`` epoch with the offset they imply; or a group's scan proposals, its curve's
  edge, its quick-merge comparison.
* ``plot``: the processing plot of THE result the question concerns (the one an approval would name:
  ``questions.curve_result``; never a rejected or an older one), ``path`` inside the bundle folder, ``base: bundle``.
  That result with no plot, or a plot file that is no PNG or JPEG inside the bundle folder, is said so: ``not_shown``
  and no path; no other plot is shown in its place.
* ``image``: an image from the beamtime's documents: written by ``isaac_api.local_import.extract`` under the bundle's
  notes folder (``base: notes``), or an image file of the imported folder (``base: source``, listed, not served).
* Only a PNG or JPEG is ever shown or served, by suffix AND first bytes (:func:`resolve_context_file`). An SVG can
  carry script: a plot or image that is one (by name or bytes) is ``not_shown: "SVG"``, never served or opened.
* ``example_files``: a few file names (``names``, ``total``).
* ``table_row``: a logbook step-table row the parser linked to a run (``cells``).

THE RELEVANCE RULES (:data:`RULES`, by :func:`theme_of`; deterministic, in this order):

* ``environment`` (every ``context.*`` field: environment, control mode, potential and its scale, electrolyte, pH,
  cell type, reaction, atmosphere, temperature; an optional-values question with any of them): the logbook quotes
  about those runs' conditions, the logbook step-table rows linked to them, the potentials (and pH, electrolyte, scan
  files) their names state, and the group's processing plot.
* ``sample`` (every ``sample.*`` field: material, form, formula, provenance, id): the quotes about the sample, the
  document images whose neighbouring text (4 lines before, 2 after, never a table) or file name names the sample as
  the files write it, then those that use a sample word (:data:`SAMPLE_WORDS`; no other image is shown), and each
  run's sample reading and stage position.
* ``clock`` (the instrument clock's zone, the start-time questions): each run's ``#D`` local time beside its ``#E``
  epoch, and the offset the two imply, shown as a VALUE. Never a zone: the scientist decides (CLAUDE.md §5).
* ``curve`` (the absorber, ``measurement.*``, ``descriptors.*``; curve approval and QC status, via the minimum): the
  group's plot, its scan proposals and scan decisions, its quick-merge (MERGE) comparison, and the runs' setup
  (filter, emission energy, scan files); for the absorber, each group's curve edge.
* ``naming`` (the counter question, condition labels, ``assets[].uri``): example file names.
* ``technique`` (``system.technique``): the parser's evidence lines and example file names.
* ``group`` (confirming a group, a merge candidate): the member runs' conditions side by side.
* ``people`` (``attribution.*``: the group, the organization): WHO IS NAMED IN THE FILES, as quotes: the AI readings
  about those fields, then the lines of the extracted documents that name someone (``prepared by …``, ``…’s
  Availability``, ``the … group``, ``… has sent``, an ``Authors:`` key; :func:`_names_people`), at most
  :data:`MAX_PEOPLE_QUOTES`. Evidence only: no name is suggested as the answer.

Anything else carries no context. Bounds: :data:`MAX_ITEMS` items, :data:`MAX_QUOTES` quotes of at most
:data:`QUOTE_CHARS` characters, :data:`MAX_ROWS` table rows, :data:`MAX_IMAGES` images, :data:`MAX_PLOTS` plots,
:data:`MAX_NAMES` file names. Nothing here reads a source file: only what the bundle stores, the processing
outputs inside it and the extract tool's output in the notes folder (a notes folder that is a symlink, or not beside
its bundle, is not read; each ``text.md`` is read once per version, at most :data:`TEXT_MD_MAX_BYTES`, and only when
its folder holds an image or a ``people`` question asks).

EXPOSURES are recorded for exactly what is PRINTED, compact or full (:func:`_finish`): a value in a row, quote or item
cut by a bound, or a value a cell's length cuts off, records nothing, so it stays blind for a later cross-check.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

KINDS = ("quote", "values", "plot", "image", "example_files", "table_row")
MAX_ITEMS = 6
MAX_QUOTES = 3
QUOTE_CHARS = 240
CELL_CHARS = 60
MAX_ROWS = 8
MAX_IMAGES = 2
MAX_PLOTS = 1
MAX_NAMES = 5
MAX_TABLE_ROWS = 2
#: The compact form `bundle questions` prints: fewer rows and quotes, shorter quotes (`bundle show question` is full).
COMPACT_ROWS = 3
COMPACT_QUOTE_CHARS = 160
#: Image files a context item may show (and the local endpoint may serve): PNG and JPEG only, by suffix AND by their
#: bytes. An SVG is never shown or served (it can carry script): it is named, ``not_shown: "SVG"``.
SERVED_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
IMAGE_SUFFIXES = tuple(SERVED_TYPES)
#: Image files of the imported folder a context may NAME (never served).
LISTED_IMAGE_SUFFIXES = IMAGE_SUFFIXES + (".svg",)
CONTEXT_FILE_MAX_BYTES = 25 * 1024 * 1024
NOT_SHOWN_SVG = "SVG"
#: How much of an extracted ``text.md`` is read (once per version of the file: :data:`_DOC_CACHE`).
TEXT_MD_MAX_BYTES = 2_000_000
EXPOSURE_COMMAND = "bundle questions (context)"

NOTE = ("Context: what the files, the readings and the processing hold for this question, to help the scientist "
        "answer it. It is evidence, never the answer: nothing is set or chosen by it.")
AI_SOURCE = "an AI reading of the files (not file evidence; the quote is as the reader gave it)"
PARSER_SOURCE = "ISAAC's parser"
PROCESSING_SOURCE = "ISAAC's processing (a draft protocol, not yet reviewed)"

RULES: Mapping[str, tuple[str, ...]] = {
    "environment": ("quote", "table_row", "values", "plot"),
    "sample": ("quote", "image", "values"),
    "clock": ("values",),
    "curve": ("plot", "values", "quote"),
    "naming": ("example_files",),
    "technique": ("quote", "example_files"),
    "group": ("values",),
    "people": ("quote",),
}

_START_PATH = "timestamps.acquired_start_utc"
_POTENTIAL = "context.electrochemistry.potential_setpoint_V"
_PH = "context.electrochemistry.pH"
_ELECTROLYTE = "context.electrochemistry.electrolyte.name"
_SAMPLE_NAME = "sample.material.name"
_EPOCH_RULE = "bl15.spec.epoch_to_utc_iso.v1"
_SPEC_TIME = "%a %b %d %H:%M:%S %Y"
_MOTOR = re.compile(r"motor `(S[xyz])`")
_LINE = re.compile(r"\bline (\d+)\b")
_IMAGE_NAME = re.compile(r"^(\d+)_[0-9a-f]+\.(png|jpe?g|svg)$", re.IGNORECASE)
_SCAN_SOURCES = ("spec_acquisition", "scan", "spec_scan", "scan_export")


def theme_of(q: Mapping) -> str | None:
    """Which rule a question's context follows (:data:`RULES`), or ``None`` (no context)."""
    kind, path = q.get("kind"), q.get("target_field_path")
    if kind in ("clock_time_zone", "stated_utc_start_times") or path == _START_PATH:
        return "clock"
    if kind in ("naming_counter_positions", "condition_label"):
        return "naming"
    if kind == "confirm_absorber":
        return "curve"
    if kind == "optional_values":
        fields = list((q.get("fields") or {}).keys())
        if any(f.startswith("context.") for f in fields):
            return "environment"
        if any(f.startswith("sample.") for f in fields):
            return "sample"
        return None
    if not isinstance(path, str):
        return None
    if path.startswith(("measurement.", "descriptors.")):
        return "curve"
    if path.startswith("assets"):
        return "naming"
    if path.startswith("context."):
        return "environment"
    if path.startswith("sample."):
        return "sample"
    if path == "system.technique":
        return "technique"
    if path.startswith("attribution."):
        return "people"
    return None


def _fields_of(q: Mapping) -> list[str]:
    if q.get("kind") == "optional_values":
        return sorted((q.get("fields") or {}).keys())
    return [q["target_field_path"]] if isinstance(q.get("target_field_path"), str) else []


def _clip(text: Any, n: int) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _printed(joined: str, value: str, n: int) -> bool:
    """Whether :func:`_clip` of ``joined`` to ``n`` characters prints (at least the start of) ``value``."""
    s, v = " ".join(joined.split()), " ".join(str(value).split())
    at = s.find(v)
    return at >= 0 and (len(s) <= n or at < len(s[: n - 1].rstrip()))


def _line_of(locator: Any) -> int | None:
    m = _LINE.search(str(locator or ""))
    return int(m.group(1)) if m else None


def notes_dir_of(bundle_dir: Path | None) -> Path | None:
    """The working-notes folder beside a bundle (``<bundle>-notes``; SKILL.md Rule 0), or ``None``."""
    if bundle_dir is None:
        return None
    return Path(bundle_dir).parent / f"{Path(bundle_dir).name}-notes"


def notes_root(bundle_dir: Path | None) -> Path | None:
    """The notes folder when it is one to read from: a real folder (not a symlink) directly beside its bundle."""
    notes = notes_dir_of(bundle_dir)
    try:
        if notes is None or notes.is_symlink() or not notes.is_dir():
            return None
        return notes if notes.resolve(strict=True).parent == Path(bundle_dir).resolve(strict=True).parent else None
    except OSError:
        return None


# --- the image files a context may show -------------------------------------------------------------------------

def image_format(head: bytes) -> str | None:
    """``png``, ``jpeg`` or ``svg`` by a file's first bytes (its magic), or ``None``."""
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    low = head[:512].lstrip().lower()
    if low.startswith(b"<svg") or (low.startswith(b"<?xml") and b"<svg" in head.lower()) or b"<svg" in low[:256]:
        return "svg"
    return None


def _sniff(path: Path) -> str | None:
    try:
        with path.open("rb") as fh:
            return image_format(fh.read(2048))
    except OSError:
        return None


def _shown_as(suffix: str, fmt: str | None) -> str | None:
    """Why a file is not shown (``"SVG"``), ``""`` when it is, or ``None`` when it is no image to name at all."""
    if fmt == "svg" or suffix == ".svg":
        return NOT_SHOWN_SVG
    expected = "png" if suffix == ".png" else "jpeg" if suffix in (".jpg", ".jpeg") else None
    return "" if expected is not None and fmt == expected else None


class ContextFileRefused(Exception):
    def __init__(self, status: int, error: str, message: str):
        super().__init__(message)
        self.status, self.error, self.message = status, error, message


def resolve_context_file(base: Path, rel: str) -> tuple[Path, str]:
    """``(file, media type)`` of the image ``rel`` names inside ``base``, or :class:`ContextFileRefused`. ``rel`` is a
    relative POSIX path: no ``..``, ``.`` or empty part, no absolute, home or drive path, no backslash or NUL; its
    suffix one of :data:`SERVED_TYPES`; no part of it (and not ``base``) a symlink; it resolves inside ``base`` to a
    regular file of at most :data:`CONTEXT_FILE_MAX_BYTES` whose FIRST BYTES are the image its suffix says (a PNG or a
    JPEG: an SVG, whatever its name, is refused). Only that last check reads the file (its first bytes)."""

    def refuse(status: int, error: str, message: str):
        raise ContextFileRefused(status, error, message)

    if not isinstance(rel, str) or not rel or "\x00" in rel or "\\" in rel or ":" in rel:
        refuse(400, "path_refused", "The path must be a plain relative path inside the folder.")
    pure = PurePosixPath(rel)
    if pure.is_absolute() or rel.startswith(("/", "~")) or any(part in ("", ".", "..") for part in rel.split("/")):
        refuse(400, "path_refused", "The path must be a plain relative path inside the folder (no `..`, no absolute path).")
    suffix = pure.suffix.lower()
    if suffix not in SERVED_TYPES:
        refuse(415, "type_refused", "Only a PNG or JPEG image is served (never an SVG).")
    if base.is_symlink() or not base.is_dir():
        refuse(404, "file_not_found", "No such image in this bundle.")
    root = base.resolve(strict=True)
    here = base
    for part in pure.parts:
        here = here / part
        if here.is_symlink():
            refuse(403, "symlink_refused", "A path through a symbolic link is not served.")
    try:
        target = here.resolve(strict=True)
        target.relative_to(root)
    except (OSError, ValueError):
        refuse(404, "file_not_found", "No such image in this bundle.")
    if not target.is_file():
        refuse(404, "file_not_found", "No such image in this bundle.")
    if target.stat().st_size > CONTEXT_FILE_MAX_BYTES:
        refuse(413, "file_too_large", "This image is larger than the page shows.")
    if _shown_as(suffix, _sniff(target)) != "":
        refuse(415, "type_refused", "Only a PNG or JPEG image is served, and its bytes must be the image its name says.")
    return target, SERVED_TYPES[suffix]


def _inside(root: Path | None, rel: Any) -> Path | None:
    """The file ``rel`` names inside ``root`` when :func:`resolve_context_file` serves it, else ``None``."""
    if root is None or not isinstance(rel, str):
        return None
    try:
        return resolve_context_file(root, rel)[0]
    except (ContextFileRefused, OSError):
        return None


# --- extracted document text, read once per version ---------------------------------------------------------------

#: ``(path, mtime_ns, size) -> {"captions": {marker: (before, near)}, "people": [(line_no, line)]}``: what one
#: ``text.md`` holds for a context, derived from ONE capped read (:data:`TEXT_MD_MAX_BYTES`) and kept while the file is
#: unchanged (at most :data:`_DOC_CACHE_MAX` documents), so a page does not re-read every document per request.
_DOC_CACHE: dict[tuple, dict] = {}
_DOC_CACHE_MAX = 256


def _read_capped(path: Path) -> str:
    with path.open("rb") as fh:
        return fh.read(TEXT_MD_MAX_BYTES).decode("utf-8", errors="replace")


def _doc(path: Path) -> dict:
    empty = {"captions": {}, "people": []}
    try:
        if path.is_symlink() or not path.is_file():
            return empty
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
        if key in _DOC_CACHE:
            return _DOC_CACHE[key]
        lines = _read_capped(path).splitlines()
    except OSError:
        return empty
    captions = {line.strip(): _image_text(lines, line.strip()) for line in lines if line.startswith("[image ")}
    people = [(n + 1, line.strip(), at) for n, line in enumerate(lines) if (at := _names_people(line.strip())) is not None]
    out = {"captions": captions, "people": people}
    if len(_DOC_CACHE) >= _DOC_CACHE_MAX:
        _DOC_CACHE.pop(next(iter(_DOC_CACHE)))
    _DOC_CACHE[key] = out
    return out


#: A line NAMES SOMEONE (the ``people`` rule) when it says who did something (``prepared by Ana``), whose something it
#: is (``Ana’s Availability``, ``Ana's samples``), a named group or lab (``the Ana group``), that someone did it
#: (``Ana has sent``, ``Ana added``), or it is a key or list of people (``Authors:``, ``Operators:``). A name is a
#: capitalised word that is not a common sentence opener. Deterministic; never a value.
def _name(n: int) -> str:
    return rf"(?P<name{n}>(?-i:[A-Z][a-z]+(?:[-'’][A-Za-z][a-z]+)?))"


_PEOPLE = re.compile(
    r"\b(?:prepared|made|written|measured|sent|run|synthesi[sz]ed|provided|brought|recorded|taken|collected|"
    rf"analy[sz]ed|supervised|led)\s+by\s+{_name(1)}"
    rf"|\b{_name(2)}[’']s\s+(?:availability|schedule|notes|samples?|group|lab|shift|cell|electrodes?)\b"
    rf"|\b{_name(3)}\s+(?:group|lab|team)\b"
    rf"|\b{_name(4)}\s+(?:(?:has|have)\s+)?(?:sent|added|prepared|synthesi[sz]ed|brought|provided)\b"
    r"|(?P<list>^\s*(?:authors?|operators?|people|users?|team|key\s*\(?(?:authors?|people|names?)\)?)\s*[:=])",
    re.IGNORECASE)
_NOT_A_NAME = frozenset({"the", "this", "that", "these", "those", "then", "it", "we", "i", "you", "they", "he", "she",
                         "please", "here", "there", "also", "someone", "everyone", "nobody", "who", "which", "what",
                         "standards", "sample", "samples", "cell", "ink", "solution", "beam", "data", "file", "files",
                         "and", "or", "if", "when", "once", "after", "before", "a", "an", "our", "my", "your", "their"})


def _names_people(line: str) -> int | None:
    """Where one line of a document NAMES SOMEONE by :data:`_PEOPLE` (the match's start), or ``None``. A name is a
    capitalised word, not a common sentence opener (the pattern's words ignore case, the name's capital does not)."""
    s = line.strip()
    if not s or s.startswith(("[image", "[table")):
        return None
    for m in _PEOPLE.finditer(s):
        if m.group("list"):
            return m.start()
        names = [v for k, v in m.groupdict().items() if v and k.startswith("name")]
        if any(n.casefold() not in _NOT_A_NAME for n in names):
            return m.start()
    return None
    for m in _PEOPLE.finditer(s):
        name = m.group("name") if "name" in m.groupdict() else None
        names = [v for k, v in m.groupdict().items() if v and k.startswith("name")]
        if not names and m.group(0).rstrip().endswith((":", "=")):
            return True
        if any(n[0].isupper() and n.casefold() not in _NOT_A_NAME for n in names or ([name] if name else [])):
            return True
    return False


class Index:
    """What one bundle holds, indexed once for every question of a page."""

    def __init__(self, bundle: Mapping, bundle_dir: Path | None = None):
        from . import questions as Q

        self.bundle = bundle
        self.bundle_dir = Path(bundle_dir) if bundle_dir is not None else None
        self.notes_dir = notes_dir_of(self.bundle_dir)
        self.runs = {r["run_id"]: r for r in bundle.get("runs") or () if r.get("run_id")}
        self.sources = {s["source_id"]: s for s in bundle.get("sources") or () if s.get("source_id")}
        self.cands = {c["candidate_id"]: c for c in bundle.get("candidates") or () if c.get("candidate_id")}
        self.missing = {m["value_id"]: m for m in bundle.get("missing_values") or () if m.get("value_id")}
        self.conflicts = {c["conflict_id"]: c for c in bundle.get("conflicts") or () if c.get("conflict_id")}
        self.groups = {g["group_id"]: g for g in bundle.get("record_groups") or () if g.get("group_id")}
        self.live = [g for g in Q.live_groups(bundle)]
        self.group_of_run: dict[str, str] = {}
        for g in self.live:
            for rid in g.get("member_run_ids") or ():
                self.group_of_run.setdefault(rid, g["group_id"])
        self.cands_of_run: dict[str, list[Mapping]] = {}
        for c in self.cands.values():
            if c.get("run_id"):
                self.cands_of_run.setdefault(c["run_id"], []).append(c)
        self.ai_of_run: dict[str, list[Mapping]] = {}
        for i in bundle.get("ai_interpretations") or ():
            for rid in self._ai_runs(i):
                self.ai_of_run.setdefault(rid, []).append(i)
        self.results_of_group: dict[str, list[Mapping]] = {}
        for r in bundle.get("processing_results") or ():
            if r.get("group_id"):
                self.results_of_group.setdefault(r["group_id"], []).append(r)
        self._images: list[dict] | None = None

    # -- runs ---------------------------------------------------------------------------------------------------
    def _ai_runs(self, i: Mapping) -> list[str]:
        t = i.get("target") or {}
        if i.get("run_ids"):
            return [r for r in i["run_ids"] if isinstance(r, str)]
        k, tid = t.get("kind"), t.get("id")
        if k == "candidate":
            return [r for r in [(self.cands.get(tid) or {}).get("run_id")] if r]
        if k == "missing_value":
            return [r for r in [(self.missing.get(tid) or {}).get("run_id")] if r]
        if k == "record_group":
            return list((self.groups.get(tid) or {}).get("member_run_ids") or ())
        if k == "run":
            return [tid] if tid else []
        return []

    def ai_field(self, i: Mapping) -> str | None:
        if isinstance(i.get("field_path"), str):
            return i["field_path"]
        t = i.get("target") or {}
        if t.get("kind") == "candidate":
            return (self.cands.get(t.get("id")) or {}).get("target_field_path")
        if t.get("kind") == "missing_value":
            return (self.missing.get(t.get("id")) or {}).get("target_field_path")
        return None

    def runs_of_target(self, kind: str | None, tid: str) -> list[str]:
        if kind == "candidate":
            return [r for r in [(self.cands.get(tid) or {}).get("run_id")] if r]
        if kind == "missing_value":
            return [r for r in [(self.missing.get(tid) or {}).get("run_id")] if r]
        if kind == "conflict":
            return list((self.conflicts.get(tid) or {}).get("run_ids") or ())
        if kind == "record_group":
            return list((self.groups.get(tid) or {}).get("member_run_ids") or ())
        if kind == "run":
            return [tid]
        return []

    def runs_of_question(self, q: Mapping) -> list[str]:
        """The question's runs in live groups, in run order (a beamtime-wide target: every live group's runs)."""
        found: list[str] = []
        for t in q.get("targets") or ():
            if t.get("kind") == "experiment":
                found = [r for g in self.live for r in g.get("member_run_ids") or ()]
                break
            found += self.runs_of_target(t.get("kind"), t.get("id"))
        scope = q.get("scope") or ""
        if scope.startswith("group:"):
            mine = set((self.groups.get(scope[6:]) or {}).get("member_run_ids") or ())
            found = [r for r in found if r in mine] or list(mine)
        if not found and scope.startswith("group:"):
            found = list((self.groups.get(scope[6:]) or {}).get("member_run_ids") or ())
        order = {rid: n for n, rid in enumerate(self.runs)}
        live = set(self.group_of_run)
        kept = [r for r in dict.fromkeys(found) if r in self.runs and (r in live or not live)]
        return sorted(kept, key=lambda r: order.get(r, 1 << 30))

    def groups_of_runs(self, runs: Sequence[str]) -> list[str]:
        return list(dict.fromkeys(self.group_of_run[r] for r in runs if r in self.group_of_run))

    def run_name(self, rid: str) -> str:
        r = self.runs.get(rid) or {}
        return str(r.get("stem") or r.get("label") or rid)

    def source_path(self, sid: Any, fallback: Any = None) -> str | None:
        s = self.sources.get(sid) or {}
        return s.get("relative_path") or (str(fallback) if fallback else None)

    def is_scan_source(self, sid: Any) -> bool:
        s = self.sources.get(sid) or {}
        st = str((s.get("classification") or {}).get("source_type") or "")
        return st in _SCAN_SOURCES or st.startswith("spec") or "scan" in st

    # -- per-run file values ------------------------------------------------------------------------------------
    def _cands(self, rid: str, *, key: str | None = None, path: str | None = None) -> list[Mapping]:
        return [c for c in self.cands_of_run.get(rid) or ()
                if (key is None or c.get("statement_key") == key) and (path is None or c.get("target_field_path") == path)]

    def literals(self, rid: str, *, key: str | None = None, path: str | None = None, shown: list | None = None) -> str:
        """The distinct values the files write for ``rid`` (as written, at most 3), or ``""``; adding to ``shown`` the
        candidates whose value the cell PRINTS (one cut off by the 3 or by the cell's length is not shown)."""
        pairs: list[tuple[str, str]] = []
        for c in self._cands(rid, key=key, path=path):
            # one value written with and without its unit (`9175.4`, `9175.4 eV`) is one value
            pairs += [(re.sub(r"\s*eV$", "", str(x)), c["candidate_id"]) for x in c.get("observed_literals") or ()
                      if x is not None]
        vals = list(dict.fromkeys(v for v, _ in pairs))
        if not vals:
            return ""
        joined = ", ".join(vals[:3]) + (f" (+{len(vals) - 3} more)" if len(vals) > 3 else "")
        if shown is not None:
            printed = {v for v in vals[:3] if _printed(joined, v, CELL_CHARS)}
            shown += [("candidate", cid) for v, cid in pairs if v in printed]
        return _clip(joined, CELL_CHARS)

    def potential(self, rid: str, shown: list) -> str:
        """The potential a run's NAME writes, with the volts the parser read it as (a reading, never confirmed)."""
        for c in self._cands(rid, path=_POTENTIAL):
            ev = next((e for e in c.get("evidence") or () if str(e.get("locator") or "").startswith("filename")), None)
            lit = (ev or {}).get("literal_value") or next(iter(c.get("observed_literals") or ()), None)
            if lit is None:
                continue
            v = c.get("value")
            joined = f"'{lit}'" + (f" (read as {v:g} V)" if isinstance(v, (int, float)) else "")
            if _printed(joined, f"'{lit}'", CELL_CHARS):
                shown.append(("candidate", c["candidate_id"]))
            return _clip(joined, CELL_CHARS)
        return ""

    def stage(self, rid: str, shown: list) -> dict[str, str]:
        """Sx/Sy/Sz as the scan headers' ``#P`` lines state them (distinct values, in scan order); adding to ``shown``
        the candidates whose value a cell prints."""
        by: dict[str, list[tuple[str, str]]] = {}
        for c in self._cands(rid, key="sample_position"):
            for e in c.get("evidence") or ():
                m = _MOTOR.search(str(e.get("locator") or ""))
                if m and e.get("literal_value") is not None:
                    # a macro line writes the motor before its value (`Sz -5.5`): the value alone
                    by.setdefault(m.group(1), []).append(
                        (str(e["literal_value"]).removeprefix(m.group(1)).strip(), c["candidate_id"]))
        out = {}
        for motor, pairs in by.items():
            d = list(dict.fromkeys(v for v, _ in pairs))
            joined = " / ".join(d[:3]) + (" …" if len(d) > 3 else "")
            printed = {v for v in d[:3] if _printed(joined, v, CELL_CHARS)}
            shown += list(dict.fromkeys(("candidate", cid) for v, cid in pairs if v in printed))
            out[motor] = _clip(joined, CELL_CHARS)
        return out

    def scan_files(self, rid: str) -> str:
        r = self.runs.get(rid) or {}
        n = r.get("scan_count")
        return str(n) if isinstance(n, int) else (str(len(r.get("scans") or ())) if r.get("scans") else "")

    def clock(self, rid: str, shown: list) -> dict | None:
        """The file header's ``#D`` local time beside its ``#E`` epoch (UTC), and the offset they imply (local − UTC).
        A local-clock start (an SSRL XDC header) has no epoch: no offset."""
        from . import bundle as B

        epoch = None
        for c in self._cands(rid, path=_START_PATH):
            ev = next((e for e in c.get("evidence") or () if "#E" in str(e.get("locator") or "")), None)
            if ev is not None and isinstance(c.get("value"), str):
                epoch = (c, ev)
                break
        local = None
        for c in self._cands(rid, key="acquisition_timestamp"):
            evs = [e for e in c.get("evidence") or () if e.get("literal_value")]
            if not evs:
                continue
            if B.is_local_clock_start(c):
                ev = next((e for e in evs if e.get("relation") == "supports"), evs[0])
            elif epoch is not None:
                # the #D in the same header as the #E: the first #D after the #E line in that file
                e_src, e_line = epoch[1].get("source_id"), _line_of(epoch[1].get("locator")) or 0
                same = [e for e in evs if e.get("source_id") == e_src and "#D" in str(e.get("locator") or "")
                        and (_line_of(e.get("locator")) or 0) >= e_line]
                ev = min(same, key=lambda e: _line_of(e.get("locator")) or 0) if same else None
            else:
                ev = evs[0]
            if ev is not None:
                local = (c, ev)
                break
        if local is None and epoch is None:
            return None
        row: dict = {"run": self.run_name(rid), "_shown": shown}
        if local is not None:
            shown.append(("candidate", local[0]["candidate_id"]))
            row["local"] = f"{local[1]['literal_value']} ({local[1].get('locator')})"
        if epoch is not None:
            shown.append(("candidate", epoch[0]["candidate_id"]))
            row["epoch"] = f"{epoch[0]['value']} (from '{epoch[1].get('literal_value')}', {epoch[1].get('locator')})"
        row["offset"] = _offset(local[1]["literal_value"] if local else None, epoch[0]["value"] if epoch else None)
        return row

    # -- processing ---------------------------------------------------------------------------------------------
    def result_for(self, gid: str) -> Mapping | None:
        """THE result a question about the group's curve concerns: the one an approval would name
        (``questions.curve_result``: the approved one, else the latest undecided one offered for approval), never a
        rejected or an older one; ``None`` when there is none. Whether it has a plot is :func:`_plot_items`' to say."""
        from . import questions as Q

        return Q.curve_result(self.bundle, gid)

    # -- images -------------------------------------------------------------------------------------------------
    def images(self) -> list[dict]:
        """Every image the extract tool wrote under the notes folder (with the document it came from and the text
        line before it), then the image files of the imported folder. Computed once per page; a document's text is
        read only when its folder holds an image, once per version of the file (:data:`_DOC_CACHE`). A notes folder
        that is a symlink, or is not beside its bundle, is not read. Each image says ``shown``: ``""`` (a PNG or JPEG
        whose bytes are one) or why not (``"SVG"``); a file whose bytes are no image is left out."""
        if self._images is not None:
            return self._images
        out: list[dict] = []
        by_sha = {str(s.get("content_sha256") or "")[:12]: s for s in self.sources.values() if s.get("content_sha256")}
        root = notes_root(self.bundle_dir)
        base = root / "extracted" if root is not None else None
        if base is not None and base.is_dir() and not base.is_symlink():
            for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.is_symlink()):
                files = [(f, m) for f in sorted(d.iterdir()) if (m := _IMAGE_NAME.match(f.name))
                         and f.is_file() and not f.is_symlink()]
                if not files:
                    continue
                captions = _doc(d / "text.md")["captions"]
                doc = (by_sha.get(d.name) or {}).get("relative_path")
                for f, m in files:
                    shown = _shown_as(f.suffix.lower(), _sniff(f))
                    if shown is None:
                        continue
                    before, near = captions.get(f"[image img-{m.group(1)}]", (None, ""))
                    out.append({"path": f"extracted/{d.name}/{f.name}", "base": "notes", "document": doc,
                                "before": before, "near": near, "shown": shown})
        for s in self.sources.values():
            rel = str(s.get("relative_path") or "")
            if PurePosixPath(rel).suffix.lower() in LISTED_IMAGE_SUFFIXES:
                out.append({"path": rel, "base": "source", "document": None, "before": None, "near": rel, "shown": ""})
        self._images = out
        return out

    def people_lines(self) -> list[dict]:
        """The lines of the extracted documents that name someone (:func:`_names_people`), in document order."""
        out: list[dict] = []
        by_sha = {str(s.get("content_sha256") or "")[:12]: s for s in self.sources.values() if s.get("content_sha256")}
        root = notes_root(self.bundle_dir)
        base = root / "extracted" if root is not None else None
        if base is None or not base.is_dir() or base.is_symlink():
            return out
        for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.is_symlink()):
            doc = (by_sha.get(d.name) or {}).get("relative_path")
            for n, line, at in _doc(d / "text.md")["people"]:
                out.append({"document": doc, "dir": d.name, "line": n, "text": line, "at": at})
        return out


def _plot_file(r: Mapping) -> str | None:
    return next((f.get("relative_path") for f in (r.get("outputs") or {}).get("files") or ()
                 if f.get("role") == "plot" and isinstance(f.get("relative_path"), str)), None)


def _image_text(lines: Sequence[str], marker: str) -> tuple[str | None, str]:
    """The non-empty text line before an image's marker in ``text.md``, and its NEIGHBOURING TEXT: the 4 lines before
    it and the 2 after, each side stopping at another image or a table (a table beside an image is not about it)."""
    at = next((n for n, line in enumerate(lines) if line.strip() == marker), None)
    if at is None:
        return None, ""

    def stop(line: str) -> bool:
        return line.startswith(("[image", "[table"))

    before_lines: list[str] = []
    for n in range(at - 1, max(-1, at - 9), -1):
        if stop(lines[n]):
            break
        if lines[n].strip():
            before_lines.insert(0, lines[n].strip())
        if len(before_lines) >= 4:
            break
    after_lines: list[str] = []
    for n in range(at + 1, min(len(lines), at + 6)):
        if stop(lines[n]):
            break
        if lines[n].strip():
            after_lines.append(lines[n].strip())
        if len(after_lines) >= 2:
            break
    before = before_lines[-1] if before_lines else None
    return (_clip(before, 120) if before else None), " ".join(before_lines + after_lines)


def _offset(local_literal: Any, utc_iso: Any) -> str:
    """The offset a ``#D`` local time and a ``#E`` UTC instant imply (local − UTC), as ``UTC−07:00``; or why none."""
    if not local_literal:
        return "none: no #D local time held"
    if not utc_iso:
        return "none: no #E epoch in this file"
    try:
        local = datetime.strptime(str(local_literal), _SPEC_TIME)
        utc = datetime.fromisoformat(str(utc_iso).replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return "none: the #D time does not parse"
    minutes = round((local - utc).total_seconds() / 60)
    if abs(minutes) > 14 * 60:
        return f"none: the two differ by {minutes / 60:.1f} h (not one instant)"
    sign = "+" if minutes >= 0 else "−"
    return f"UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


# --- items ------------------------------------------------------------------------------------------------------

def _values_item(label: str, source: str, rows: Sequence[Mapping], columns: Sequence[tuple[str, str]],
                 note: str | None = None, total: int | None = None) -> dict | None:
    """A ``values`` table: only the columns some row fills, at most :data:`MAX_ROWS` rows."""
    keep = [(k, title) for k, title in columns if any(r.get(k) for r in rows)]
    if not rows or len(keep) < 2:
        return None
    # each printed row's exposures (``_row_shown``, cut with the rows; :func:`_finish` records and drops it)
    return {"kind": "values", "label": label, "source": source, "columns": [t for _, t in keep],
            "rows": [[str(r.get(k) or "") for k, _ in keep] for r in rows[:MAX_ROWS]],
            "rows_total": total if total is not None else len(rows), **({"note": note} if note else {}),
            "_row_shown": [list(r.get("_shown") or ()) for r in rows[:MAX_ROWS]]}


def _quote_items(idx: Index, runs: Sequence[str], fields: Sequence[str], prefix: str | None, q: Mapping,
                 label: str | None = None) -> list[dict]:
    """The text lines about the question's runs for its fields (then any field of the theme): AI readings first
    (logbook files before scan files), then the parser's evidence read from a notes line; never one the question's
    own hints already quote; at most :data:`MAX_QUOTES`."""
    have = {(h.get("source_path"), str(h.get("locator")), h.get("quote")) for h in q.get("hints") or ()
            if h.get("kind") == "ai_suggestion"}
    want = set(fields)

    def rank(f: str | None) -> int | None:
        if f in want:
            return 0
        if prefix and isinstance(f, str) and f.startswith(prefix):
            return 1
        return None

    found: list[tuple[tuple, dict]] = []
    seen: set = set()
    for rid in runs:
        for i in idx.ai_of_run.get(rid) or ():
            r = rank(idx.ai_field(i))
            if r is None or not i.get("quote"):
                continue
            ref = (i.get("source_refs") or [{}])[0]
            path = i.get("source_path") or idx.source_path(ref.get("source_id"))
            loc = i.get("excerpt_locator") or ref.get("locator")
            key = (path, str(loc), i.get("quote"))
            if key in have or key[2] in seen:
                continue
            seen.add(key[2])
            found.append(((r, idx.is_scan_source(ref.get("source_id")), len(found)), {
                "kind": "quote", "label": label or (f"{'The logbook' if not idx.is_scan_source(ref.get('source_id')) else 'A file'} "
                                                    f"on the {_field_words(idx.ai_field(i))}"),
                "source": AI_SOURCE, "origin": "ai_reading", "path": path, "locator": loc,
                "quote": _clip(i["quote"], QUOTE_CHARS), "field": idx.ai_field(i),
                **({"strength": i["strength"]} if i.get("strength") else {}),
                **({"quote_check": i["quote_check"]} if isinstance(i.get("quote_check"), (str, Mapping)) else {})}))
        for c in idx.cands_of_run.get(rid) or ():
            r = rank(c.get("target_field_path"))
            if r is None:
                continue
            for e in c.get("evidence") or ():
                loc = str(e.get("locator") or "")
                lit = e.get("literal_value")
                if not lit or not loc.startswith("line ") or idx.is_scan_source(e.get("source_id")) or lit in seen:
                    continue
                seen.add(lit)
                found.append(((r, False, len(found) + 1000), {
                    "_shown": [("candidate", c["candidate_id"])],
                    "kind": "quote", "label": label or f"The logbook on the {_field_words(c.get('target_field_path'))}",
                    "source": f"{PARSER_SOURCE}, which read this line ({e.get('relation') or 'supports'})",
                    "origin": "parser", "path": idx.source_path(e.get("source_id"), e.get("relative_path")),
                    "locator": loc, "quote": _clip(lit, QUOTE_CHARS), "field": c.get("target_field_path")}))
    return [item for _, item in sorted(found, key=lambda x: x[0])][:MAX_QUOTES]


def _field_words(path: Any) -> str:
    if not isinstance(path, str):
        return "conditions"
    leaf = path.rsplit(".", 1)[-1]
    words = {"potential_setpoint_V": "potential", "potential_scale": "potential scale", "pH": "pH",
             "cell_type": "cell", "control_mode": "control mode", "environment": "environment",
             "temperature_K": "temperature", "atmosphere": "atmosphere", "sample_form": "sample form",
             "concentration_M": "electrolyte concentration", "sample_id": "sample id"}
    if path == _ELECTROLYTE:
        return "electrolyte"
    if path == _SAMPLE_NAME:
        return "sample material"
    return words.get(leaf, leaf.replace("_", " "))


def _table_rows(idx: Index, runs: Sequence[str]) -> list[dict]:
    out = []
    for rid in runs:
        for row in (idx.runs.get(rid) or {}).get("note_rows") or ():
            loc = str(row.get("locator") or "")
            col = re.search(r"column `([^`]+)`", loc)
            out.append({"kind": "table_row", "label": f"The logbook's step table, for {idx.run_name(rid)}",
                        "source": f"{PARSER_SOURCE}, which linked this table row to the run by its number",
                        "path": idx.source_path(row.get("source_id")), "locator": loc,
                        "cells": {(col.group(1) if col else "value"): _clip(row.get("value"), CELL_CHARS)}})
            if len(out) >= MAX_TABLE_ROWS:
                return out
    return out


def _plot_items(idx: Index, groups: Sequence[str]) -> list[dict]:
    """The plot of THE result each group's question concerns (:meth:`Index.result_for`), at most :data:`MAX_PLOTS`.
    A result with no plot, an SVG plot, or a plot file that is not a PNG or JPEG inside the bundle folder is said so
    (``not_shown``), with no other plot in its place."""
    out = []
    for gid in groups:
        r = idx.result_for(gid)
        if r is None:
            continue
        path = _plot_file(r)
        name = _group_words(idx, gid)
        verdict = ((r.get("qc") or {}).get("verdict")) if isinstance(r.get("qc"), Mapping) else None
        item = {"kind": "plot", "label": f"ISAAC's merged curve for {name}", "source": PROCESSING_SOURCE,
                "group_id": gid, "result_id": r.get("result_id"), **({"qc_verdict": verdict} if verdict else {})}
        if not path:
            item["not_shown"] = "this result has no plot"
        elif PurePosixPath(path).suffix.lower() == ".svg" or (
                idx.bundle_dir is not None and _sniff_inside(idx.bundle_dir, path) == "svg"):
            item["not_shown"] = NOT_SHOWN_SVG
        elif idx.bundle_dir is not None and _inside(idx.bundle_dir, path) is None:
            item["not_shown"] = "its plot file is not in the bundle folder"
        else:
            item.update({"path": path, "base": "bundle",
                         "alt": f"Processing plot of the merged XAS curve for {name}"
                                + (f" (quality check: {verdict})" if verdict else "") + "."})
        out.append(item)
        if len(out) >= MAX_PLOTS:
            break
    return out


def _sniff_inside(root: Path, rel: str) -> str | None:
    """The image format of ``rel`` when it is a plain path to a regular file inside ``root`` (never followed out)."""
    pure = PurePosixPath(rel)
    if pure.is_absolute() or any(p in ("", ".", "..") for p in rel.split("/")) or "\\" in rel:
        return None
    here = Path(root)
    for part in pure.parts:
        here = here / part
        if here.is_symlink():
            return None
    return _sniff(here) if here.is_file() else None


def _group_words(idx: Index, gid: str) -> str:
    runs = (idx.groups.get(gid) or {}).get("member_run_ids") or ()
    first = idx.run_name(runs[0]) if runs else gid
    return f"{first}" + (f" and {len(runs) - 1} more run(s)" if len(runs) > 1 else "")


#: An image is about the sample when the text around it (or its file name) names the question's sample as the files
#: write it, or one of these words (the sample rule; nothing else is guessed about what an image shows).
#: Whole words only (a plural too): ``film`` is not ``filmed``. Not ``foil``: a foil is usually the reference foil.
SAMPLE_WORDS = ("sample", "electrode", "pellet", "powder", "film", "catalyst", "ink", "loading", "nanoparticle")


def _token(word: str, *, plural: bool = False) -> re.Pattern:
    """``word`` as a whole token: not inside another word or number (``_`` and punctuation separate tokens)."""
    return re.compile(rf"(?<![^\W_]){re.escape(word)}{'(?:e?s)?' if plural else ''}(?![^\W_])", re.IGNORECASE)


_SAMPLE_WORD_RES = tuple(_token(w, plural=True) for w in SAMPLE_WORDS)


def _image_items(idx: Index, runs: Sequence[str]) -> list[dict]:
    names = set()
    for rid in runs:
        for c in idx._cands(rid, path=_SAMPLE_NAME):
            names.update(str(x).strip() for x in c.get("observed_literals") or () if len(str(x).strip()) >= 2)
    tokens = [_token(n) for n in sorted(names)]

    def rank(im: Mapping) -> int | None:
        near = str(im.get("near") or "")
        if any(t.search(near) for t in tokens):
            return 0
        if any(w.search(near) for w in _SAMPLE_WORD_RES):
            return 1
        return None

    ranked = sorted(((r, n, im) for n, im in enumerate(idx.images()) if (r := rank(im)) is not None),
                    key=lambda x: (x[0], 0 if x[2]["base"] == "notes" else 1, x[1]))
    out = []
    for _, _, im in ranked[:MAX_IMAGES]:
        doc = im.get("document")
        where = (f"'{doc}', extracted by ISAAC's extract tool" if doc else
                 "a document, extracted by ISAAC's extract tool" if im["base"] == "notes" else
                 "an image file in the imported folder")
        alt = (f"Image from {doc or im['path']}" + (f", after the line '{im['before']}'" if im.get("before") else ""))
        out.append({"kind": "image", "label": "An image from the beamtime's documents", "source": where,
                    "path": im["path"], "base": im["base"], **({"document": doc} if doc else {}),
                    **({"text_before": im["before"]} if im.get("before") else {}),
                    **({"not_shown": im["shown"]} if im.get("shown") else {"alt": alt + "."})})
    return out


def _example_files(idx: Index, runs: Sequence[str], q: Mapping) -> dict | None:
    names = [str(n) for n in q.get("example_names") or () if n][:MAX_NAMES] if q.get("example_names") else []
    pool = runs or list(idx.runs)
    for rid in pool:
        if len(names) >= MAX_NAMES:
            break
        n = idx.run_name(rid)
        if n not in names:
            names.append(n)
    if not names:
        return None
    return {"kind": "example_files", "label": "Some of the file names", "source": "the imported folder's file names",
            "names": names, "total": max(len(pool), len(names))}


def _run_rows(idx: Index, runs: Sequence[str], cols: Sequence[str]) -> list[dict]:
    """One row per run (at most :data:`MAX_ROWS`), each with the exposures of the values it prints (``_shown``)."""
    rows = []
    for rid in runs[:MAX_ROWS]:
        shown = []
        row: dict = {"run": idx.run_name(rid), "_shown": shown}
        if "potential" in cols:
            row["potential"] = idx.potential(rid, shown)
        if "ph" in cols:
            row["ph"] = idx.literals(rid, path=_PH, shown=shown)
        if "electrolyte" in cols:
            row["electrolyte"] = idx.literals(rid, path=_ELECTROLYTE, shown=shown)
        if "sample" in cols:
            row["sample"] = idx.literals(rid, path=_SAMPLE_NAME, shown=shown)
        if "history" in cols:
            row["history"] = idx.literals(rid, key="cycling_state", shown=shown) or idx.literals(
                rid, key="before_after_state", shown=shown)
        if "filter" in cols:
            row["filter"] = idx.literals(rid, key="filter", shown=shown)
        if "emission" in cols:
            row["emission"] = idx.literals(rid, key="emission_energy", shown=shown)
        if "stage" in cols:
            row.update({k.lower(): v for k, v in idx.stage(rid, shown).items()})
        if "scans" in cols:
            row["scans"] = idx.scan_files(rid)
        rows.append(row)
    return rows


_COLUMNS = (("run", "Run"), ("sample", "Sample (as the name writes it)"), ("potential", "Potential (from the name)"),
            ("ph", "pH (as written)"), ("electrolyte", "Electrolyte (as written)"), ("history", "History (as written)"),
            ("filter", "Filter"), ("emission", "Emission energy (eV)"), ("sx", "Sx"), ("sy", "Sy"), ("sz", "Sz"),
            ("scans", "Scan files"))


def _run_values(idx: Index, runs: Sequence[str], cols: Sequence[str], label: str) -> dict | None:
    rows = _run_rows(idx, runs, cols)
    return _values_item(label, f"{PARSER_SOURCE}, from the file names and scan headers", rows, _COLUMNS,
                        total=len(runs))


def _clock_item(idx: Index, runs: Sequence[str], q: Mapping) -> dict | None:
    rows = [r for r in (idx.clock(rid, []) for rid in runs[: MAX_ROWS * 4]) if r][:MAX_ROWS]
    if q.get("kind") == "clock_time_zone":
        # the clock question's runs have no epoch: other runs of the beamtime that state both are shown too
        others = [rid for rid in idx.runs if rid not in set(runs)]
        extra = [r for r in (idx.clock(rid, []) for rid in others[: MAX_ROWS * 4]) if r and r.get("epoch")]
        rows = (rows + extra)[:MAX_ROWS]
    total = sum(1 for rid in runs if rid in idx.runs)
    return _values_item(
        "Each run's local clock time beside its epoch", f"{PARSER_SOURCE}, from the scan file headers",
        rows, (("run", "Run"), ("local", "#D local time (no zone)"), ("epoch", "#E epoch, in UTC"),
               ("offset", "Offset they imply")),
        note=("The offset is only what the two header lines imply (local minus UTC). It is a value, not a time zone: "
              "no zone is suggested, and the scientist says which zone the clock was set to."),
        total=max(total, len(rows)))


def _curve_items(idx: Index, groups: Sequence[str], runs: Sequence[str], q: Mapping) -> list[dict]:
    from .processing.quick_merge import RESULT_KEY

    out: list[dict] = []
    out += _plot_items(idx, groups)
    gid = groups[0] if groups else None
    r = idx.result_for(gid) if gid else None
    if q.get("kind") == "confirm_absorber":
        rows = []
        for g in groups:
            res = idx.result_for(g)
            e0 = ((res or {}).get("outputs") or {}).get("e0_eV")
            if isinstance(e0, (int, float)):
                rows.append({"group": _group_words(idx, g), "e0": f"{e0:.1f}"})
        item = _values_item("Where each group's curve has its edge", PROCESSING_SOURCE, rows,
                            (("group", "Group"), ("e0", "Edge position E0 (eV)")), total=len(groups),
                            note="The edge ISAAC's processing found; which element and edge it is stays the scientist's word.")
        if item:
            out.append(item)
    if r is not None:
        sel = r.get("scan_selection") if isinstance(r.get("scan_selection"), Mapping) else {}
        rows = [{"file": s.get("file"), "proposal": str(s.get("proposal") or "").replace("_", " "),
                 "why": _clip("; ".join(str(x) for x in s.get("said") or s.get("reasons") or ()), CELL_CHARS)}
                for s in sel.get("scans") or () if s.get("proposal") and s.get("proposal") not in ("keep", "include")]
        decided = [d for d in idx.bundle.get("scientist_decisions") or ()
                   if (d.get("target") or {}).get("kind") in ("processing_result", "scan", "scans")
                   and str((d.get("target") or {}).get("id") or "").find(gid or "\0") >= 0]
        rows += [{"file": str((d.get("target") or {}).get("id")), "proposal": f"decided: {d.get('decision')}",
                  "why": _clip(d.get("note") or "", CELL_CHARS)} for d in decided[-2:]]
        item = _values_item("Scans proposed for leaving out or a look, and scan decisions", PROCESSING_SOURCE, rows,
                            (("file", "Scan"), ("proposal", "Proposal or decision"), ("why", "Why")),
                            note="A proposal only: a scan is left out only on the scientist's word.")
        if item:
            out.append(item)
        qms = [x for x in r.get(RESULT_KEY) or () if isinstance(x, Mapping)]
        rows = [{"file": x.get("relative_path"), "verdict": x.get("verdict"), "said": _clip(x.get("statement") or "", 120)}
                for x in qms[:2]]
        cmp_ = r.get("comparison") if isinstance(r.get("comparison"), Mapping) else None
        if cmp_:
            rows.append({"file": "their Athena curve", "verdict": cmp_.get("verdict"), "said": _clip(cmp_.get("reason") or "", 120)})
        item = _values_item("Their own quick merge (MERGE) compared with ISAAC's curve", PROCESSING_SOURCE, rows,
                            (("file", "File"), ("verdict", "Comparison"), ("said", "What it says")),
                            note="A rough reference only, never the answer key.")
        if item:
            out.append(item)
    setup = _run_values(idx, runs, ("filter", "emission", "scans"), "Each run's setup, from the scan headers")
    if setup:
        out.append(setup)
    return out


#: The label of every quote of the ``people`` rule.
PEOPLE_LABEL = "Who is named in the files"
MAX_PEOPLE_QUOTES = 4
#: A people quote starts at most this many characters before the words that name someone.
PEOPLE_LEAD_CHARS = 60
DOCUMENT_SOURCE = "the text ISAAC's extract tool read from the document (verbatim)"


def _people_items(idx: Index, runs: Sequence[str], fields: Sequence[str], q: Mapping) -> list[dict]:
    """WHO THE FILES NAME, for a group or organization question: the AI readings (and parser lines) about the
    question's ``attribution.*`` fields, then the document lines that name someone (:func:`_names_people`): evidence,
    never the answer; at most :data:`MAX_PEOPLE_QUOTES`."""
    # the readings and lines about who: of the question's runs, and (a beamtime-wide question has none) of any run
    items = _quote_items(idx, runs or list(idx.runs), fields, "attribution.", q, label=PEOPLE_LABEL)
    seen = {i.get("quote") for i in items}
    have = {h.get("quote") for h in q.get("hints") or () if h.get("kind") == "ai_suggestion"}
    # an AI reading about who with no run (the experiment as its target), its field the question's first
    unrun = [i for i in idx.bundle.get("ai_interpretations") or ()
             if not idx._ai_runs(i) and str(idx.ai_field(i) or "").startswith("attribution.") and i.get("quote")]
    for i in sorted(unrun, key=lambda i: idx.ai_field(i) not in set(fields)):
        quote = _clip(i["quote"], QUOTE_CHARS)
        if quote in seen or i["quote"] in have:
            continue
        seen.add(quote)
        ref = (i.get("source_refs") or [{}])[0]
        items.append({"kind": "quote", "label": PEOPLE_LABEL, "source": AI_SOURCE, "origin": "ai_reading",
                      "path": i.get("source_path") or idx.source_path(ref.get("source_id")),
                      "locator": i.get("excerpt_locator") or ref.get("locator"), "quote": quote,
                      "field": idx.ai_field(i), **({"strength": i["strength"]} if i.get("strength") else {})})
    for line in idx.people_lines():
        if len(items) >= MAX_PEOPLE_QUOTES:
            break
        # verbatim, from a little before the name (a long line's name is kept in the compact form's shorter quote)
        start = max(0, line["at"] - PEOPLE_LEAD_CHARS)
        start = line["text"].rfind(" ", 0, start) + 1 if start else 0
        quote = ("…" if start else "") + _clip(line["text"][start:], QUOTE_CHARS - (1 if start else 0))
        if quote in seen:
            continue
        seen.add(quote)
        items.append({"kind": "quote", "label": PEOPLE_LABEL, "source": DOCUMENT_SOURCE, "origin": "document",
                      "path": line["document"] or f"extracted/{line['dir']}/text.md",
                      "locator": f"line {line['line']} of its extracted text", "quote": quote})
    return items[:MAX_PEOPLE_QUOTES]


def _build(q: Mapping, idx: Index, theme: str | None) -> list[dict]:
    """The context of one question by :data:`RULES`, uncut: items may carry their exposures (``_shown``, and
    ``_row_shown`` for a table's rows) for :func:`_finish`."""
    theme = theme or theme_of(q)
    if theme is None:
        return []
    runs = idx.runs_of_question(q)
    groups = idx.groups_of_runs(runs)
    fields = _fields_of(q)
    items: list[dict] = []
    if theme == "environment":
        items += _quote_items(idx, runs, fields, "context.", q)
        items += _table_rows(idx, runs)
        v = _run_values(idx, runs, ("potential", "ph", "electrolyte", "scans"), "What each run's files state")
        items += [v] if v else []
        items += _plot_items(idx, groups)
    elif theme == "sample":
        items += _quote_items(idx, runs, fields, "sample.", q)
        items += _image_items(idx, runs)
        v = _run_values(idx, runs, ("sample", "stage", "scans"), "Each run's sample reading and stage position")
        items += [v] if v else []
    elif theme == "clock":
        v = _clock_item(idx, runs, q)
        items += [v] if v else []
    elif theme == "curve":
        items += _curve_items(idx, groups, runs, q)
        items += _quote_items(idx, runs, fields, None, q) if fields else []
    elif theme == "naming":
        v = _example_files(idx, runs, q)
        items += [v] if v else []
    elif theme == "technique":
        for rid in runs[:MAX_ROWS]:
            for c in idx._cands(rid, path="system.technique"):
                for e in c.get("evidence") or ():
                    if e.get("literal_value") and not str(e.get("locator") or "").startswith("filename") and len(
                            [i for i in items if i["kind"] == "quote"]) < MAX_QUOTES:
                        if any(i.get("quote") == e["literal_value"] for i in items):
                            continue
                        items.append({"kind": "quote", "label": "A line the technique was read from",
                                      "source": PARSER_SOURCE, "origin": "parser",
                                      "path": idx.source_path(e.get("source_id"), e.get("relative_path")),
                                      "locator": e.get("locator"), "quote": _clip(e["literal_value"], QUOTE_CHARS),
                                      "_shown": [("candidate", c["candidate_id"])]})
        v = _example_files(idx, runs, q)
        items += [v] if v else []
    elif theme == "group":
        v = _run_values(idx, runs, ("potential", "history", "filter", "emission", "stage", "scans"),
                        "The runs' conditions side by side")
        items += [v] if v else []
    elif theme == "people":
        items += _people_items(idx, runs, fields, q)
    return items


def _finish(items: Sequence[Mapping], full: bool) -> tuple[list[dict], list[tuple[str, str]]]:
    """``(items, shown)``: the items AS PRINTED (at most :data:`MAX_ITEMS`; :func:`compact` unless ``full``) and the
    exposures of exactly what they print: a cut row, quote or item records nothing."""
    printed = [dict(i) for i in items[:MAX_ITEMS]]
    if not full:
        printed = compact(printed)
    shown: list[tuple[str, str]] = []
    for it in printed:
        shown += it.pop("_shown", None) or []
        for row in it.pop("_row_shown", None) or []:
            shown += row
    return printed, list(dict.fromkeys(shown))


def context_for(q: Mapping, idx: Index, shown: list, *, theme: str | None = None, full: bool = True) -> list[dict]:
    """The context of one question by :data:`RULES` as printed (full, or :func:`compact`), adding to ``shown`` every
    candidate whose file value it PRINTS (an exposure, as a page's parser values are), and nothing it cuts."""
    items, more = _finish(_build(q, idx, theme), full)
    shown += more
    return items


def compact(items: Sequence[Mapping]) -> list[dict]:
    """The form `bundle questions` prints: at most :data:`COMPACT_ROWS` table rows and shorter quotes."""
    out = []
    for it in items:
        c = dict(it)
        if c.get("kind") == "values":
            c["rows"] = list(c.get("rows") or ())[:COMPACT_ROWS]
            if "_row_shown" in c:
                c["_row_shown"] = list(c["_row_shown"])[:COMPACT_ROWS]
            c.pop("note", None)
        if c.get("kind") == "quote":
            c["quote"] = _clip(c.get("quote") or "", COMPACT_QUOTE_CHARS)
        if c.get("kind") in ("plot", "image"):
            c.pop("alt", None)
        out.append(c)
    return out


def annotate(questions: Sequence[Mapping], bundle: Mapping, bundle_dir: Path | None = None, *,
             full: bool = True, idx: Index | None = None) -> tuple[list[dict], list[tuple[str, str]]]:
    """``(questions, shown)``: each question with ``context`` ADDED where its rule finds any (a copy: ids, blocking,
    counts and text unchanged), and the candidates whose values that context states."""
    idx = idx or Index(bundle, bundle_dir)
    shown: list[tuple[str, str]] = []
    out = []
    for q in questions:
        items = context_for(q, idx, shown, full=full)
        out.append({**q, "context": items} if items else dict(q))
    return out, list(dict.fromkeys(shown))


def annotate_minimum(minimum: Mapping | None, payload: Mapping, bundle: Mapping, bundle_dir: Path | None = None, *,
                     full: bool = False, idx: Index | None = None) -> tuple[Mapping | None, list[tuple[str, str]]]:
    """``minimum_for_one_group`` with each question's context (for the scope it is answered at, ``only``) and a
    ``decision_context`` for its decisions: confirming the group (the runs' conditions side by side) and approving
    its processing result (the curve rule: plot, scan proposals and decisions, the quick-merge comparison)."""
    if not minimum or not minimum.get("group_id"):
        return minimum, []
    idx = idx or Index(bundle, bundle_dir)
    shown: list[tuple[str, str]] = []
    by_id = {q["question_id"]: q for q in payload.get("questions") or ()}
    out = copy.deepcopy(dict(minimum))
    gid = out["group_id"]
    for m in out.get("questions") or ():
        q = by_id.get(m.get("question_id"))
        if q is None:
            continue
        only = m.get("only") or f"group:{gid}"
        if (q.get("per_scope_targets") or {}).get(only) is not None:
            ids = set(q["per_scope_targets"][only])
            q = {**q, "targets": [t for t in q.get("targets") or () if t.get("id") in ids]}
        q = {**q, "scope": only if only.startswith("group:") else q.get("scope")}
        items = context_for(q, idx, shown, full=full)
        if items:
            m["context"] = items
    group_q = {"kind": "record_group", "scope": f"group:{gid}", "targets": [{"kind": "record_group", "id": gid}]}
    decisions: dict[str, list] = {}
    said = [str(x) for x in out.get("plus_decisions") or ()]
    if "confirm the group" in said:
        items = context_for(group_q, idx, shown, theme="group", full=full)
        if items:
            decisions["confirm_the_group"] = items
    if "approve its processing result" in said:
        items = context_for({**group_q, "target_field_path": "measurement.qc.status"}, idx, shown, theme="curve", full=full)
        if items:
            decisions["approve_its_processing_result"] = items
    if decisions:
        out["decision_context"] = decisions
    return out, list(dict.fromkeys(shown))


def merge_candidate_context(bundle: Mapping, mc: Mapping, bundle_dir: Path | None = None) -> tuple[list[dict], list]:
    """A merge candidate's context: its groups' runs' conditions side by side (the ``group`` rule)."""
    idx = Index(bundle, bundle_dir)
    gids = [g for g in mc.get("group_ids") or () if isinstance(g, str)]
    q = {"kind": "merge_candidate", "targets": [{"kind": "record_group", "id": g} for g in gids]}
    shown: list = []
    return context_for(q, idx, shown, theme="group"), list(dict.fromkeys(shown))


def with_files(items: Sequence[Mapping], bundle_dir: Path | None) -> list[dict]:
    """For the command line: each plot or image inside the bundle or its notes folder with ``open_with_read``, the
    absolute file Claude opens with the Read tool (a page never shows a path on this computer). The path is checked as
    the local endpoint checks it (:func:`resolve_context_file`: a plain relative path, no symlink, a PNG or JPEG inside
    that folder, the notes folder a real folder beside its bundle); an item whose path fails is LEFT OUT. An item
    ``not_shown`` (an SVG, a result with no plot) and an image of the imported folder get no file to open."""
    if bundle_dir is None:
        return [dict(i) for i in items]
    bdir = Path(bundle_dir).resolve()
    roots = {"bundle": bdir if bdir.is_dir() else None, "notes": notes_root(bdir)}
    out = []
    for i in items:
        i = dict(i)
        if i.get("kind") in ("plot", "image") and i.get("base") in roots and i.get("path") is not None \
                and not i.get("not_shown"):
            target = _inside(roots[i["base"]], i["path"])
            if target is None:
                continue
            i["open_with_read"] = str(target)
        out.append(i)
    return out


def files_in(context: Iterable[Mapping]) -> list[str]:
    return [str(i["path"]) for i in context if i.get("kind") in ("plot", "image") and i.get("path")]
