"""P31.1 — safe CSV ingress limits + read-only typed preview builder.

This is the NON-truth ingestion boundary for the "ISAAC campaign metadata sheet
(CSV)" — the narrow ``section,field,value,unit,notes`` long format the existing
:mod:`isaac_records.extract.structured` parser reads. It is deliberately NOT an
"arbitrary CSV" reader (see the Phase-31 plan §8 CSV v1 contract).

Responsibilities (all pure / non-mutating / stdlib-only, Graphify-free):

  * centralize every ingress/parse LIMIT constant in ONE place (so the route and
    the parser never drift),
  * decode a RAW request body deterministically (utf-8-sig strict; reject empty /
    invalid-UTF-8 / any NUL byte),
  * validate the CSV v1 header + row/column/cell shape into STABLE typed error
    codes (never a raw exception / stack trace),
  * sanitize a client-supplied ``X-Filename`` into a bounded, path-free basename
    used ONLY for evidence attribution/display (never a path, id, or value),
  * build a READ-ONLY typed preview of FIELD_MAP-mapped candidates via the
    in-memory :func:`parse_structured_text` adaptation.

It performs NO Workspace mutation, writes NOTHING to disk, guesses nothing, and
leaks no server path / secret / stack trace. The truth path is untouched.
"""

from __future__ import annotations

import csv
import io

from isaac_records.extract.structured import parse_structured_text

# --- centralized limits (the ONLY source; imported by the route + tests) ------

#: Max RAW request-body size. Also the max decoded-character budget (§8). 256 KB.
MAX_BODY_BYTES = 256 * 1024
#: Max data rows (excluding the header row). §8.
MAX_ROWS = 500
#: Max header columns. §8.
MAX_HEADERS = 64
#: Max characters in any single cell (header or data). §8.
MAX_CELL_CHARS = 4 * 1024
#: Max mapped candidates surfaced in one preview. §8.
MAX_CANDIDATES = 200
#: Max characters kept for the sanitized display basename.
MAX_FILENAME_CHARS = 128

#: Stable identity of the deterministic parser behind this preview.
FORMAT = "isaac_campaign_csv"
PARSER_ID = "isaac.extract.structured"
PARSER_VERSION = "1"

#: The default display basename when the client sends no (usable) ``X-Filename``.
DEFAULT_SOURCE_NAME = "upload.csv"

#: The recognized CSV v1 header columns; anything else is a non-actionable WARNING.
_KNOWN_HEADERS = frozenset({"section", "field", "value", "unit", "notes"})
#: Required header columns (at least these two must be present). §8.
_REQUIRED_HEADERS = ("field", "value")

#: Separator characters (ASCII + common unicode look-alikes) that must never
#: survive into a display basename — otherwise a crafted ``X-Filename`` could read
#: as a path segment somewhere downstream.
_SEP_CHARS = "/\\⁄∕／∖＼"


class CsvIngestError(Exception):
    """A typed, safe CSV-ingress rejection carrying a STABLE code + HTTP status.

    ``code`` is one of the frozen ingress error codes; ``message`` is a short,
    human-readable, path-free/secret-free explanation. Never wraps a raw
    exception object — only a curated message.
    """

    def __init__(self, code: str, http_status: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.message = message


def safe_source_name(x_filename: str | None) -> str:
    """Sanitize a client ``X-Filename`` into a bounded, path-free basename.

    The raw ``text/csv`` body has no filename, so this is purely client-supplied
    display metadata. The result is used ONLY for evidence attribution/display —
    never as a filesystem path, a record id, or a value. Strips control/NUL chars,
    reduces any path (ASCII or unicode separators, ``..`` traversal) to its final
    component, bounds the length, and falls back to :data:`DEFAULT_SOURCE_NAME`
    when nothing safe remains.
    """
    if not x_filename:
        return DEFAULT_SOURCE_NAME
    # 1. Drop C0/C1 control chars and DEL (incl. NUL) — never let them display.
    name = "".join(ch for ch in x_filename if ch >= " " and ch != "\x7f")
    # 2. Normalize every separator look-alike to "/", then take the last segment.
    for sep in _SEP_CHARS:
        name = name.replace(sep, "/")
    name = name.rsplit("/", 1)[-1]
    # 3. Strip surrounding whitespace/dots so "..", "." and ".hidden" traversal
    #    fragments cannot leak through.
    name = name.strip().strip(".").strip()
    # 4. Reject anything that still is not a plain basename.
    if not name or any(sep in name for sep in _SEP_CHARS):
        return DEFAULT_SOURCE_NAME
    # 5. Bound the length (keep the tail so an extension, if any, survives).
    if len(name) > MAX_FILENAME_CHARS:
        name = name[-MAX_FILENAME_CHARS:]
    return name


def decode_body(raw: bytes) -> str:
    """Decode a raw CSV body deterministically, or raise a typed error.

    utf-8-sig strict (a leading BOM is tolerated; no charset auto-detection).
    Rejects an empty body, invalid UTF-8, and any embedded NUL byte.
    """
    if not raw:
        raise CsvIngestError("empty_file", 400, "The request body is empty.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvIngestError(
            "invalid_encoding", 400, "The body is not valid UTF-8 text."
        )
    if "\x00" in text:
        raise CsvIngestError("nul_byte", 400, "The body contains a NUL byte.")
    return text


def _read_all_rows(text: str) -> list[list[str]]:
    """Parse the CSV into rows with standard dialect (comma, standard quoting).

    NO ``csv.Sniffer`` / no delimiter inference. A malformed CSV structure raises
    a typed ``invalid_csv`` rather than a raw ``csv.Error``.
    """
    try:
        return list(csv.reader(io.StringIO(text)))
    except csv.Error:
        raise CsvIngestError("invalid_csv", 422, "The body is not well-formed CSV.")


def _validate_header(header: list[str]) -> tuple[int, list[dict]]:
    """Validate the header row; return ``(recognized_count, unknown_warnings)``.

    Header cells are case-normalized + trimmed. Enforces: no empty header, no
    duplicate header, header count ≤ :data:`MAX_HEADERS`, and the required columns
    present. Unknown EXTRA columns become non-actionable WARNINGS (never mapped).
    """
    normalized = [h.strip().lower() for h in header]
    if len(normalized) > MAX_HEADERS:
        raise CsvIngestError(
            "too_many_columns",
            422,
            f"Header has more than {MAX_HEADERS} columns.",
        )
    if any(h == "" for h in normalized):
        raise CsvIngestError("empty_header", 422, "A header column name is empty.")
    if len(set(normalized)) != len(normalized):
        raise CsvIngestError(
            "duplicate_header", 422, "A header column name is duplicated."
        )
    missing = [h for h in _REQUIRED_HEADERS if h not in normalized]
    if missing:
        raise CsvIngestError(
            "missing_required_header",
            422,
            "Required header column(s) missing: " + ", ".join(missing) + ".",
        )
    recognized_count = sum(1 for h in normalized if h in _KNOWN_HEADERS)
    unknown_warnings = [
        {
            "code": "unknown_header",
            "header": h,
            "message": f"Unknown column {h!r} is ignored (never mapped).",
        }
        for h in normalized
        if h not in _KNOWN_HEADERS
    ]
    return recognized_count, unknown_warnings


# --- P31.2 reconciliation helpers (pure, deterministic) -----------------------

#: The literal CSV column a mapped value comes from in the v1 long format.
_VALUE_COLUMN = "value"

_RECONCILE_EXPLANATIONS = {
    "matches_current": "This value matches the current record; no change is needed.",
    "conflicts_with_current": (
        "This value differs from the current record. The record is left unchanged "
        "and this disagreement needs human review."
    ),
    "absent_from_record": (
        "The record has no confirmed value here; this value is unconfirmed and was "
        "not written to the record."
    ),
}


def _field_label(path: str) -> str:
    """Derive a safe human display name from an official dotted path's LAST segment.

    Deterministic and path-free: ``system.facility.beamline`` -> ``"Beamline"``,
    ``sample.composition.CuO2_mass_fraction`` -> ``"CuO2 Mass Fraction"``. Only the
    final segment is used, then ``_`` splits into words whose first letter is
    upper-cased WITHOUT lower-casing the rest (so ``CuO2`` is preserved). The result
    can never contain a ``.`` or ``/`` — it never leaks a path.
    """
    segment = path.rsplit(".", 1)[-1]
    words = [w for w in segment.split("_") if w]
    return " ".join(w[:1].upper() + w[1:] for w in words)


def _is_number(x) -> bool:
    """True for a real JSON number (int/float) — but NOT ``bool``."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _normalized_equal(a, b) -> bool:
    """Compare two values: numerically when BOTH are numbers, else trimmed strings."""
    if _is_number(a) and _is_number(b):
        return float(a) == float(b)
    return str(a).strip() == str(b).strip()


def _is_blank(v) -> bool:
    """A missing/empty value: ``None`` or an all-whitespace string."""
    return v is None or (isinstance(v, str) and v.strip() == "")


def _reconcile(path: str, proposed, record_fields: dict) -> tuple[str, object]:
    """Classify a proposed value against the current record value at ``path``.

    Returns ``(reconciliation_state, current_value)``. NO mutation; a pure read of
    the caller-supplied record view. Callers must not pass a blank proposed value:
    build_preview skips blank cells before reconciling, so a blank never reaches
    here to be mislabeled.
    """
    entry = record_fields.get(path)
    current = entry.get("value") if isinstance(entry, dict) else None
    if entry is None or _is_blank(current):
        return "absent_from_record", current
    if _normalized_equal(current, proposed):
        return "matches_current", current
    return "conflicts_with_current", current


def build_preview(
    text: str,
    *,
    source_name: str,
    source_record_rev: int,
    experiment_id: str | None = None,
    record_fields: dict | None = None,
) -> dict:
    """Validate CSV v1 + build the READ-ONLY typed RECONCILIATION preview.

    P31.2 (reconciliation-only): each FIELD_MAP-mapped candidate is compared —
    without any mutation, rev bump, or write — against the CURRENT authoritative
    value at its official path (supplied by the caller as ``record_fields``:
    ``path -> {"value": <current or None>, "classification": <P28 class or None>}``)
    and classified ``matches_current`` / ``conflicts_with_current`` /
    ``absent_from_record``. No winner is selected; both the proposed and current
    values are preserved.

    Order: parse rows → header validation → cell/row limits → in-memory FIELD_MAP
    mapping → candidate limit → reconciliation enrichment → typed preview. Every
    candidate's ``value_state`` is ``"candidate"`` (a preview proposes, never
    confirms).
    """
    record_fields = record_fields or {}
    rows = _read_all_rows(text)
    if not rows:
        raise CsvIngestError("empty_file", 400, "The CSV has no rows.")

    header, data_rows = rows[0], rows[1:]

    # Cell length across EVERY cell (header + data): fail closed on an oversized
    # cell before any mapping work.
    for row in rows:
        for cell in row:
            if len(cell) > MAX_CELL_CHARS:
                raise CsvIngestError(
                    "cell_too_long",
                    422,
                    f"A cell exceeds the {MAX_CELL_CHARS}-character limit.",
                )

    recognized_count, unknown_warnings = _validate_header(header)

    if len(data_rows) > MAX_ROWS:
        raise CsvIngestError(
            "too_many_rows", 422, f"More than {MAX_ROWS} data rows."
        )

    # In-memory deterministic mapping (FIELD_MAP only; unmapped rows skipped,
    # never guessed). Reuses the SAME parser code path as the file-based reader.
    fields = parse_structured_text(text, source_name=source_name)
    if len(fields) > MAX_CANDIDATES:
        raise CsvIngestError(
            "candidate_limit_exceeded",
            422,
            f"More than {MAX_CANDIDATES} candidate fields.",
        )

    candidates: list[dict] = []
    summary = {
        "matches_current": 0,
        "conflicts_with_current": 0,
        "absent_from_record": 0,
    }
    for f in fields:
        # A blank sheet cell for a mapped field proposes NO value — it must NOT
        # create a reconciliation item (never a fabricated match/conflict, and
        # never a contradictory "absent" item that still carries a current value).
        # It stays out of `candidates` and the summary; the skipped-row warning is
        # computed from `fields` (below), so its count is unaffected.
        if _is_blank(f.value):
            continue
        state, current_value = _reconcile(f.path, f.value, record_fields)
        summary[state] += 1
        rf_entry = record_fields.get(f.path)
        classification = (
            rf_entry.get("classification")
            if isinstance(rf_entry, dict) and rf_entry.get("classification")
            else "unknown"
        )
        candidates.append(
            {
                "field": f.path,
                "proposed_value": f.value,
                # A preview PROPOSES; it never confirms. Always "candidate".
                "value_state": "candidate",
                "status": f.status,  # verified | needs_confirmation (from _coerce)
                "locator": f.evidence[0]["locator"] if f.evidence else "",
                "source_format": "csv",
                # --- P31.2 reconciliation enrichment (read-only) --------------
                "experiment_id": experiment_id,
                "field_label": _field_label(f.path),
                "current_value": current_value,
                "reconciliation_state": state,
                "column": _VALUE_COLUMN,
                "source_name": source_name,
                "parser_id": PARSER_ID,
                "parser_version": PARSER_VERSION,
                "source_record_rev": source_record_rev,
                # Freshly built == current; the client detects staleness by a rev
                # mismatch against the live record.
                "stale": False,
                # The CURRENT record field's P28 evidence-support class (NOT the
                # raw CSV status): describes how well the record value is backed.
                "evidence_classification": classification,
                "explanation": _RECONCILE_EXPLANATIONS[state],
            }
        )

    warnings: list[dict] = []
    # Report skipped-unmapped-row COUNT only — never the unmapped field name/value.
    non_blank_data_rows = sum(
        1 for r in data_rows if len(r) > _field_col_index(header) and r[_field_col_index(header)].strip()
    )
    skipped = max(non_blank_data_rows - len(fields), 0)
    if skipped:
        warnings.append(
            {
                "code": "unmapped_fields_skipped",
                "count": skipped,
                "message": "Unrecognized field rows were skipped (never guessed).",
            }
        )

    return {
        "format": FORMAT,
        "source_name": source_name,
        "parser_id": PARSER_ID,
        "parser_version": PARSER_VERSION,
        "source_record_rev": source_record_rev,
        "row_count": len(data_rows),
        "recognized_header_count": recognized_count,
        "unknown_header_warnings": unknown_warnings,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "reconciliation_summary": summary,
        "warnings": warnings,
    }


def _field_col_index(header: list[str]) -> int:
    """Index of the ``field`` column in the (validated) header, else a large int."""
    normalized = [h.strip().lower() for h in header]
    return normalized.index("field") if "field" in normalized else len(normalized) + 1


__all__ = [
    "MAX_BODY_BYTES",
    "MAX_ROWS",
    "MAX_HEADERS",
    "MAX_CELL_CHARS",
    "MAX_CANDIDATES",
    "MAX_FILENAME_CHARS",
    "FORMAT",
    "PARSER_ID",
    "PARSER_VERSION",
    "DEFAULT_SOURCE_NAME",
    "CsvIngestError",
    "safe_source_name",
    "decode_body",
    "build_preview",
]
