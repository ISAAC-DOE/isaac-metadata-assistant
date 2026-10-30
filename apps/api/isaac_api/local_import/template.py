"""The ISAAC metadata template round trip: ``isaac bundle template export|import``.

A scientist fills ONE workbook per beamtime with what no file states (facility, beamline,
environment, cell type, reaction, sample form ...). The workbook has the sheets and header
rows of ISAAC's own metadata template (Campaign Info, Configurations, File List,
Vocabulary), plus two sheets ISAAC adds:

* ``ISAAC Suggestions`` (visible): for each answer cell, what the import already holds —
  an extracted value or literal with its file and locator, a hint from the consolidated
  questions, or an AI reading. Evidence beside the blank cell; never in it.
* ``_isaac`` (hidden): the format id and version, the ``bundle_id``, the export time, which
  row is which run, and which column is which official field.

EXPORT never writes a value into an answer cell. Printing the suggestions shows parser
values, so the export records an exposure first (as ``bundle show`` does).

IMPORT refuses any workbook whose ``_isaac`` sheet is missing or names another bundle — so
the example values in ISAAC's raw template can never be imported as answers. It reads only
non-empty answer cells, validates each one (an enum column must hold an allowed value
exactly; a numeric column must hold a number), and turns each valid cell into scientist
decisions through :func:`mutations.record_decision` — the same code as ``isaac bundle
decide``. Each decision's note cites its cell. Without ``apply`` nothing is written. A cell
that would change an earlier scientist decision is a clash and is skipped unless
``supersede``. A column with no official field, or no target in this bundle, is reported
with its cells: nothing is dropped silently, and no mapping is guessed.
"""

from __future__ import annotations

import math
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import bundle as B

FORMAT_ID = "isaac.metadata_template"
#: 1.2.0: File List gains the ISAAC-added column "Control Mode" (``context.electrochemistry.control_mode``,
#: locally answerable since bundle 1.5.0), after pH. A 1.1.0 workbook is still read: its columns
#: are the ones 1.1.0 wrote (:data:`COLUMNS_ADDED_IN`), and nothing past pH is read from it.
#: 1.3.0: File List gains the ISAAC-added column "Current Set-point (mA/cm2)"
#: (``context.electrochemistry.current_setpoint_mA_cm2``, locally answerable since bundle 1.7.0,
#: DEC-92), after Control Mode. A 1.2.0 workbook is read up to Control Mode, a 1.1.0 one up to pH.
#: 1.4.0: the template can FINISH a record. Every field the record composer requires a scientist to
#: supply has a cell: Campaign Info gains "Your group", "Your organization" (``attribution.produced_by.*``)
#: and "Domain" (``system.domain``), appended after the template's own five rows; File List gains
#: "Reaction Drive" and "Reaction Catalysis" (``context.reaction.*``, required once a run states a
#: reaction), appended after the current set-point. Campaign Info's "Organization" was always the
#: FACILITY's (``system.facility.organization``) and now says so; a 1.3.0 workbook, which still reads
#: "Organization" and has five rows, imports as it did (:func:`campaign_fields_of`).
FORMAT_VERSION = "1.4.0"

SHEET_CAMPAIGN = "Campaign Info"
SHEET_CONFIG = "Configurations"
SHEET_FILES = "File List"
SHEET_VOCAB = "Vocabulary"
SHEET_SUGGEST = "ISAAC Suggestions"
SHEET_MARKER = "_isaac"

EXIT_USAGE = 2
EXIT_INPUT_REFUSED = 3
EXIT_OUTPUT_REFUSED = 4
EXIT_NOT_FOUND = 6

#: Rows of the Configurations sheet that carry the Technique and Config ID dropdowns.
CONFIG_ROWS = 50
_SUGGESTION_CHARS = 3_000
_SUGGESTIONS_PER_CELL = 4
_NUMBER_RE = re.compile(r"\A[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\Z")


class TemplateRefused(ValueError):
    """Nothing was read or written. ``code`` is the exit code."""

    def __init__(self, message: str, code: int = EXIT_USAGE):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Column:
    header: str
    path: str | None
    #: why there is no official field (``path is None`` only)
    why_none: str | None = None
    #: a column ISAAC adds AFTER the template's own columns (labelled as such in the workbook)
    isaac_added: bool = False
    #: a note shown on the header cell
    note: str | None = None
    #: other labels the SAME cell had in another template version (same cell, same path): an
    #: already-exported workbook still imports
    aliases: tuple[str, ...] = ()


# ISAAC's own template: sheet names and header text, in its order. No example value.
CAMPAIGN_TITLE = "ISAAC Campaign Metadata"
CAMPAIGN_FIRST_ROW = 3
_FACILITY_ORG_NOTE = ("The organization that RUNS the facility (e.g. SLAC / SSRL for SSRL), not yours: your own "
                      "institution goes in 'Your organization (who produced the data)'.")
#: Campaign Info as template 1.3.0 and earlier wrote it: the template's own five rows.
CAMPAIGN_FIELDS_1_3: tuple[Column, ...] = (
    Column("Facility Name", "system.facility.facility_name"),
    Column("Organization", "system.facility.organization", aliases=("Facility organization (e.g. SLAC / SSRL)",)),
    Column("Beamline/Instrument", "system.facility.beamline"),
    Column("Start Date", None, "the schema has no campaign start date (timestamps.acquired_start_utc is each run's own UTC instant)"),
    Column("Proposal ID", None, "the schema has no proposal id field"),
)
#: 1.4.0: the facility's organization says whose it is, and the record-scope fields the composer
#: requires (the producer, the domain) follow the template's own rows. Rows are read by position,
#: so a row is only ever APPENDED.
CAMPAIGN_FIELDS: tuple[Column, ...] = (
    CAMPAIGN_FIELDS_1_3[0],
    Column("Facility organization (e.g. SLAC / SSRL)", "system.facility.organization", note=_FACILITY_ORG_NOTE,
           aliases=("Organization",)),
    *CAMPAIGN_FIELDS_1_3[2:],
    Column("Your group (who produced the data)", "attribution.produced_by.group", isaac_added=True,
           note=("Added by ISAAC (not in ISAAC's base template). The group or PI that produced these data, as you "
                 "would write it on the record. ISAAC never takes it from a folder name.")),
    Column("Your organization (who produced the data)", "attribution.produced_by.organization", isaac_added=True,
           note=("Added by ISAAC (not in ISAAC's base template). YOUR institution (e.g. your university), "
                 "not the facility's: that is 'Facility organization'.")),
    Column("Domain", "system.domain", isaac_added=True,
           note="Added by ISAAC (not in ISAAC's base template). One of the listed values; beamline data are 'experimental'."),
)


def campaign_fields_of(version: Any) -> tuple[Column, ...]:
    """The Campaign Info rows a workbook of template ``version`` has, in order: 1.3.0 and earlier
    (or an unreadable version) have the template's five, with the facility's organization labelled
    "Organization"."""
    have = _version_key(version)
    return CAMPAIGN_FIELDS if have is not None and have >= (1, 4, 0) else CAMPAIGN_FIELDS_1_3


CONFIG_COLUMNS: tuple[Column, ...] = (
    Column("Config ID", None, "a key that joins File List rows to this sheet; not itself a value"),
    Column("Technique", "system.technique"),
    Column("Mode", None, "the schema has no acquisition-mode field"),
    Column("Primary Signal Channel", None, "a channel choice, not a schema field"),
    Column("Normalization Channel", None, "a channel choice, not a schema field"),
    Column("Detectors", None, "the schema has no detector field"),
    Column("Energy Calibration", None, "the schema has no calibration-note field"),
    Column("Beamline Setup", None, "the schema has no setup-note field"),
    Column("Notes", None, "free notes; no schema field"),
)
FILE_COLUMNS: tuple[Column, ...] = (
    Column("File Name", None, "identifies the row's run; not a value"),
    Column("Config ID", None, "a key that joins this row to a Configurations row; not itself a value"),
    Column("Sample Name", "sample.material.name"),
    Column("Sample Formula", "sample.material.formula"),
    Column("Sample Form", "sample.sample_form"),
    Column("Environment", "context.environment"),
    Column("Reaction", "context.electrochemistry.reaction"),
    Column("Cell Type", "context.electrochemistry.cell_type"),
    Column("Flow Mode", "context.transport.flow_mode"),
    Column("Electrolyte", "context.electrochemistry.electrolyte.name",
           note="The electrolyte NAME only (e.g. KOH). Its concentration goes in 'Electrolyte Concentration (M)', the pH in 'pH'."),
    Column("Potential (V)", "context.electrochemistry.potential_setpoint_V"),
    Column("Potential Scale", "context.electrochemistry.potential_scale"),
    Column("Gas Feed", None, "no single schema field (feed phase and feed composition are separate fields)"),
    # ISAAC's additions, after the template's own columns: "0.1 M KOH" is two schema fields.
    Column("Electrolyte Concentration (M)", "context.electrochemistry.electrolyte.concentration_M", isaac_added=True,
           note="Added by ISAAC (not in ISAAC's base template). A number in mol/L, e.g. 0.1 for 0.1 M KOH."),
    Column("pH", "context.electrochemistry.pH", isaac_added=True,
           note="Added by ISAAC (not in ISAAC's base template). A number."),
    Column("Control Mode", B.CONTROL_MODE_PATH, isaac_added=True,
           note=("Added by ISAAC (not in ISAAC's base template). How the cell was driven for this run, written "
                 "exactly as one of the listed values. Leave it blank if no cell was driven or nobody knows.")),
    Column("Current Set-point (mA/cm2)", B.CURRENT_SETPOINT_PATH, isaac_added=True,
           note=("Added by ISAAC (not in ISAAC's base template). For a galvanostatic run: the commanded current "
                 "DENSITY in mA/cm2, a number, with its sign as stated. Not a total current in mA: ISAAC never "
                 "divides by an electrode area. Leave it blank if you do not know it.")),
    Column("Reaction Drive", "context.reaction.drive", isaac_added=True,
           note=("Added by ISAAC (not in ISAAC's base template). For a run that states a reaction: what drove it, "
                 "exactly as one of the listed values (e.g. electrochemical). Leave it blank otherwise.")),
    Column("Reaction Catalysis", "context.reaction.catalysis", isaac_added=True,
           note=("Added by ISAAC (not in ISAAC's base template). For a run that states a reaction: its catalysis, "
                 "exactly as one of the listed values (e.g. heterogeneous). Leave it blank otherwise.")),
)
#: File List columns a later template version added: ``header -> version``. A workbook of an older
#: version does not have them; its import reads only the columns that version wrote. Such a
#: column is only ever APPENDED: cells are read by position, so one inserted mid-sheet would shift them.
COLUMNS_ADDED_IN: Mapping[str, str] = {"Control Mode": "1.2.0", "Current Set-point (mA/cm2)": "1.3.0",
                                       "Reaction Drive": "1.4.0", "Reaction Catalysis": "1.4.0"}


def _version_key(version: Any) -> tuple[int, ...] | None:
    try:
        return tuple(int(x) for x in str(version).split("."))
    except ValueError:
        return None


def file_columns_of(version: Any) -> tuple[Column, ...]:
    """The File List columns a workbook of template ``version`` has, in order. An unreadable
    version gets none of the later columns: a cell is read only where its column is known."""
    have = _version_key(version)
    return tuple(c for c in FILE_COLUMNS
                 if c.header not in COLUMNS_ADDED_IN or (have is not None and have >= _version_key(COLUMNS_ADDED_IN[c.header])))
#: The electrolyte is one reading in the files ("0.1 M KOH") but two fields here: each column's
#: suggestions also show the AI readings of the other, whole, so the scientist can split it.
_SIBLING_PATHS = {
    "context.electrochemistry.electrolyte.name": ("context.electrochemistry.electrolyte.concentration_M",),
    "context.electrochemistry.electrolyte.concentration_M": ("context.electrochemistry.electrolyte.name",),
}
#: Vocabulary sheet: ISAAC's six lists in the template's order, plus Technique (for the
#: Configurations dropdown). The VALUES are bundle.allowed_values (what decide accepts and export validates against).
VOCAB_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Sample Form", "sample.sample_form"),
    ("Environment", "context.environment"),
    ("Cell Type", "context.electrochemistry.cell_type"),
    ("Flow Mode", "context.transport.flow_mode"),
    ("Potential Scale", "context.electrochemistry.potential_scale"),
    ("Reaction", "context.electrochemistry.reaction"),
    ("Technique", "system.technique"),
    ("Control Mode", B.CONTROL_MODE_PATH),  # ISAAC-added (1.2.0), after ISAAC's own lists
    ("Domain", "system.domain"),  # ISAAC-added (1.4.0): Campaign Info
    ("Reaction Drive", "context.reaction.drive"),  # ISAAC-added (1.4.0): File List
    ("Reaction Catalysis", "context.reaction.catalysis"),
)
_ID_COLUMNS = ("File Name", "Config ID")


def _openpyxl():
    try:
        import openpyxl  # core dependency (pyproject `dependencies`)
    except ImportError as exc:  # pragma: no cover
        raise TemplateRefused(f"openpyxl is not installed: {exc}", code=EXIT_USAGE) from exc
    return openpyxl


def _letter(i: int) -> str:
    from openpyxl.utils import get_column_letter

    return get_column_letter(i)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- what each field accepts ------------------------------------------------------------------


def field_rules() -> dict[str, dict]:
    """``path -> {allowed, numeric, integer, in_schema}`` for every template path (:func:`rule_for_path`),
    read once from the schema the local export targets (``questions._target_schema``)."""
    from . import questions as Q

    schema, _basis = Q._target_schema()
    paths = {c.path for c in (*CAMPAIGN_FIELDS, *CAMPAIGN_FIELDS_1_3, *CONFIG_COLUMNS, *FILE_COLUMNS) if c.path}
    paths |= {p for _, p in VOCAB_COLUMNS}
    return {path: rule_for_path(path, schema=schema) for path in sorted(paths)}


def rule_for_path(path: str, *, schema: Mapping | None = None) -> dict:
    """What one field accepts. ``allowed`` is :func:`bundle.allowed_values` — THE list ``decide`` and
    eligibility accept and the export validates against, the same one every question offers — and
    the type is read from the target schema, then the vendored one. Used by the template import and
    by the local questions screen, so a value typed in either is parsed the same way
    (:func:`parse_answer`) and an offered value is never one ``decide`` refuses."""
    from . import questions as Q

    if schema is None:
        schema, _basis = Q._target_schema()
    node = Q._node(schema, path) or B._schema_node(path)
    enum = B.allowed_values(path)
    declared = node.get("type") if isinstance(node, Mapping) else None
    types = declared if isinstance(declared, list) else [declared] if declared else []
    return {
        "allowed": list(enum) if enum else None,
        "numeric": any(t in ("number", "integer") for t in types),
        "integer": "integer" in types and "number" not in types,
        "in_schema": node is not None,
    }


def parse_answer(raw: Any, rule: Mapping | None) -> tuple[Any, str | None]:
    """``(value, None)`` or ``(None, why it is refused)`` for one typed answer: the template import's
    own cell parsing (:func:`_parse`), so a number is stored as a number exactly as ``--json`` would
    store it, and an enum field takes only one of its allowed values, written exactly."""
    return _parse(raw, rule)


def _parse(raw: Any, rule: Mapping | None) -> tuple[Any, str | None]:
    """``(value, None)`` or ``(None, why it is refused)``. Nothing is coerced into another value:
    surrounding spaces are trimmed, and that is all."""
    if isinstance(raw, bool):
        return None, "a TRUE/FALSE cell; this field does not take one"
    if isinstance(raw, datetime):
        return None, "Excel stored a date here; this field takes text or a number. Format the cell as Text and retype it"
    numeric = bool(rule and rule["numeric"])
    if numeric:
        if isinstance(raw, (int, float)):
            value = raw
        elif isinstance(raw, str) and _NUMBER_RE.match(raw.strip()):
            text = raw.strip()
            value = int(text) if re.fullmatch(r"[+-]?\d+", text) else float(text)
        else:
            return None, f"not a number: {raw!r}"
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None, "not a finite number"
        if rule["integer"] and not (isinstance(value, int) or float(value).is_integer()):
            return None, f"this field takes a whole number; got {raw!r}"
        if rule["integer"]:
            value = int(value)
        return value, None
    if not isinstance(raw, str):
        return None, (f"Excel stored a number ({raw!r}) where text is expected, which can lose leading zeros or "
                      "digits. Format the cell as Text and retype it")
    value = raw.strip()
    if not value:
        return None, None
    allowed = rule["allowed"] if rule else None
    if allowed and value not in allowed:
        near = [a for a in allowed if isinstance(a, str) and a.casefold() == value.casefold()]
        hint = f" (did you mean {near[0]!r}? it must be written exactly)" if near else ""
        return None, f"{value!r} is not an allowed value{hint}; allowed: {', '.join(map(str, allowed))}"
    return value, None


# --- what the bundle holds ----------------------------------------------------------------------


def _live_group_of(bundle: Mapping) -> dict[str, str]:
    """``run_key -> group_id`` of the first live (proposed or confirmed) group holding it."""
    group_of: dict[str, str] = {}
    for g in bundle.get("record_groups") or ():
        if g.get("status") in B.LIVE_GROUP_STATUSES:
            for key in g.get("member_run_keys") or ():
                group_of.setdefault(key, g["group_id"])
    return group_of


def live_run_ids(bundle: Mapping) -> set[str]:
    group_of = _live_group_of(bundle)
    return {r["run_id"] for r in bundle["runs"] if r["run_key"] in group_of}


def live_rows(bundle: Mapping) -> list[dict]:
    """One row per run that belongs to a live record group (proposed or confirmed), in run order.

    ROW IDENTITY IS UNIQUE. A row is named by its acquisition file's path in the import, as the
    bundle records it (``SampleA/scan_001`` and ``SampleB/scan_001`` stay apart). Where two runs
    still share that path (one file holding two acquisitions), the run's label is added. If the
    names still repeat, the export is refused: a scientist could not tell the rows apart."""
    group_of = _live_group_of(bundle)
    sources = {s["source_id"]: s for s in bundle["sources"]}
    rows = []
    for run in bundle["runs"]:
        gid = group_of.get(run["run_key"])
        if gid is None:
            continue
        rel = (sources.get(run.get("acquisition_source_id")) or {}).get("relative_path")
        rows.append({
            "run_id": run["run_id"],
            "run_key": run["run_key"],
            "group_id": gid,
            "file_name": rel or str(run.get("stem") or run["run_id"]),
            "label": run.get("label"),
            "relative_path": rel,
        })
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["file_name"]] = counts.get(r["file_name"], 0) + 1
    for r in rows:
        if counts[r["file_name"]] > 1 and r["label"]:
            r["file_name"] = f"{r['file_name']} · {r['label']}"
    seen: dict[str, list[str]] = {}
    for r in rows:
        seen.setdefault(r["file_name"], []).append(r["run_id"])
    repeated = {name: ids for name, ids in seen.items() if len(ids) > 1}
    if repeated:
        name, ids = next(iter(sorted(repeated.items())))
        raise TemplateRefused(
            f"{len(repeated)} File List name(s) would repeat (e.g. {name!r} for runs {', '.join(ids)}): the file path and "
            "the run label do not tell these runs apart, so a scientist could not tell which row is which. No template "
            "was written.",
            code=EXIT_INPUT_REFUSED,
        )
    return rows


class _Index:
    def __init__(self, bundle: Mapping):
        self.bundle = bundle
        self.missing_by_path: dict[str, list[dict]] = {}
        self.missing_by_run: dict[tuple, list[dict]] = {}
        self.cands_by_path: dict[str, list[dict]] = {}
        self.cands_by_run: dict[tuple, list[dict]] = {}
        for m in bundle["missing_values"]:
            self.missing_by_path.setdefault(m["target_field_path"], []).append(m)
            self.missing_by_run.setdefault((m["run_id"], m["target_field_path"]), []).append(m)
        for c in bundle["candidates"]:
            if c["target_field_path"]:
                self.cands_by_path.setdefault(c["target_field_path"], []).append(c)
                self.cands_by_run.setdefault((c["run_id"], c["target_field_path"]), []).append(c)
        self.paths = set(self.missing_by_path) | set(self.cands_by_path)
        self.sources = {s["source_id"]: s for s in bundle["sources"]}

    def status(self, col: Column) -> tuple[str, str | None]:
        """``(status, reason)``: mapped | no_official_field | no_target_in_bundle."""
        if col.path is None:
            return "no_official_field", col.why_none
        if col.path not in self.paths:
            return "no_target_in_bundle", f"this bundle holds no missing value or extracted value for {col.path}"
        return "mapped", None


# --- export -------------------------------------------------------------------------------------


def _ev_where(index: _Index, ev: Mapping | None) -> str:
    if not ev:
        return "no locator recorded"
    path = ev.get("relative_path") or (index.sources.get(ev.get("source_id") or "") or {}).get("relative_path")
    return f"{path or '(source)'} @ {ev.get('locator') or '(no locator)'}"


def _shown(value: Any) -> str:
    text = repr(value) if not isinstance(value, str) else f"'{value}'"
    return text if len(text) <= 120 else text[:119] + "…"


class _Suggester:
    """What ISAAC already has for one cell. Every candidate or conflict whose value is shown is
    collected in :attr:`exposed`, recorded before the workbook is written."""

    def __init__(self, bundle: Mapping, index: _Index, *, live: set[str]):
        from . import questions as Q

        self.index = index
        self.live = live
        self.exposed: list[tuple[str, str]] = []
        self.hints_of: dict[str, list[dict]] = {}
        self.field_hints_of: dict[str, list[dict]] = {}
        payload = Q.consolidate(bundle)
        for q in payload["questions"]:
            for t in q["targets"]:
                if t["kind"] == "missing_value" and q.get("hints"):
                    self.hints_of.setdefault(t["id"], q["hints"])
            # an OPTIONAL field (the facility's name, organization, beamline) is asked in an optional-values
            # question, whose hints are per field (``field_hints``), not on the question: without these the
            # facility hints (the folder's name, the acquisition system's column names) never reached the sheet.
            # An AI reading is not a hint from the files: it is shown from the target's own interpretations.
            for path, hints in (q.get("field_hints") or {}).items():
                files = [h for h in hints if h.get("kind") != "ai_suggestion"]
                if files:
                    self.field_hints_of.setdefault(path, files)
        self.run_of_candidate = {c["candidate_id"]: c["run_id"] for c in bundle["candidates"]}
        self.ai_of: dict[tuple[str, str], list[dict]] = {}
        for i in bundle.get("ai_interpretations") or ():
            t = i.get("target") or {}
            self.ai_of.setdefault((str(t.get("kind")), str(t.get("id"))), []).append(i)

    def _expose(self, kind: str, tid: str | None) -> None:
        if tid and (kind, tid) not in self.exposed:
            self.exposed.append((kind, tid))

    def _ai(self, kind: str, tid: str, label: str = "") -> list[str]:
        out = []
        for i in self.ai_of.get((kind, tid), [])[:2]:
            ref = (i.get("source_refs") or [{}])[0] if i.get("source_refs") else {}
            where = i.get("source_path") or (self.index.sources.get(ref.get("source_id") or "") or {}).get("relative_path")
            loc = i.get("excerpt_locator") or ref.get("locator")
            # THE WHOLE READING, never clipped: "0.1 M KOH" must reach both electrolyte columns intact.
            value = i.get("proposed_value")
            shown = f"'{value}'" if isinstance(value, str) else repr(value)
            out.append(f"AI suggestion ({(i.get('model') or {}).get('model_id')}, needs review){label}: {shown}"
                       + (f" — {where or '(source)'} @ {loc or '(no locator)'}" if (where or loc) else ""))
        return out

    def _candidate(self, c: Mapping) -> list[str]:
        ev = next((e for e in c["evidence"] if e["method"] != "ai_interpretation"), None)
        if c["value"] is not None:
            what = f"extracted {_shown(c['value'])}"
        elif c["observed_literals"]:
            what = f"literal {_shown(c['observed_literals'][0])} (no value derived)"
        else:
            return self._ai("candidate", c["candidate_id"])
        self._expose("candidate", c["candidate_id"])
        return [f"{what} [{c['value_state']}] — {_ev_where(self.index, ev)}", *self._ai("candidate", c["candidate_id"])]

    def _row_hints(self, hints: Sequence[Mapping], run_id: str) -> list[Mapping]:
        """The hints of a consolidated question that are THIS run's own evidence. A beamtime-wide
        question (e.g. the environment of every run) carries readings of OTHER runs ("'dry' in
        run 83") and beamtime-wide hints (the folder's name) as context; beside one row's cell
        those read as that row's evidence, so they are not shown there. The row's own AI
        readings are shown from its own targets (:meth:`_ai`)."""
        return [h for h in hints if h.get("candidate_id") and self.run_of_candidate.get(h["candidate_id"]) == run_id]

    def _missing(self, m: Mapping, *, with_hints: bool = True, row_of: str | None = None) -> list[str]:
        """``row_of``: the File List row's run — its cell shows only that run's own hints. The
        Campaign Info block (``row_of=None``) shows the question's beamtime-wide hints."""
        out = []
        if with_hints:
            hints = self.hints_of.get(m["value_id"]) or self.field_hints_of.get(m["target_field_path"], [])
            if row_of is not None:
                hints = self._row_hints(hints, row_of)
            for h in hints[:2]:
                if h.get("candidate_id"):
                    self._expose("candidate", h["candidate_id"])
                src = (self.index.sources.get(h.get("source_id") or "") or {}).get("relative_path")
                where = f"{src} @ {h.get('locator') or '(no locator)'}" if src else (h.get("locator") or "(source)")
                out.append(f"hint ({h.get('kind')}, never an answer): {_shown(h.get('literal'))} — {where}")
        return out + self._ai("missing_value", m["value_id"])

    def for_run(self, run_id: str, path: str) -> str:
        lines: list[str] = []
        for c in self.index.cands_by_run.get((run_id, path), []):
            lines += self._candidate(c)
        for m in self.index.missing_by_run.get((run_id, path), []):
            lines += self._missing(m, row_of=run_id)
        for other in _SIBLING_PATHS.get(path, ()):
            label = f" of {other.rsplit('.', 2)[-2]}.{other.rsplit('.', 1)[-1]} (the same reading; split it)"
            sib = [x for c in self.index.cands_by_run.get((run_id, other), []) for x in self._ai("candidate", c["candidate_id"], label)]
            sib += [x for m in self.index.missing_by_run.get((run_id, other), []) for x in self._ai("missing_value", m["value_id"], label)]
            # the same reading recorded on both fields is shown once
            lines += [x for x in dict.fromkeys(sib) if x.replace(label, "") not in lines]
        return self._join(lines)

    def for_campaign(self, path: str) -> str:
        lines: list[str] = []
        for c in self.index.cands_by_run.get((None, path), []):
            lines += self._candidate(c)
        values: dict[str, int] = {}
        for c in self.index.cands_by_path.get(path, []):
            if c["run_id"] is not None and c["value"] is not None:
                values[_shown(c["value"])] = values.get(_shown(c["value"]), 0) + 1
                self._expose("candidate", c["candidate_id"])
        if values:
            lines.append("extracted per run: " + "; ".join(f"{v} in {n} run(s)" for v, n in sorted(values.items())[:5]))
        missing = [m for m in self.index.missing_by_path.get(path, []) if m["run_id"] is None or m["run_id"] in self.live]
        if missing:
            lines += self._missing(missing[0])
        if not lines:
            return ""  # nothing to show: no evidence is not a suggestion
        if missing:
            lines.insert(0, f"no source states it for {len(missing)} target(s) of the File List runs; your answer fills all of them")
        return self._join(lines)

    @staticmethod
    def _join(lines: list[str]) -> str:
        if not lines:
            return ""
        text = "\n".join(lines[:_SUGGESTIONS_PER_CELL])
        if len(lines) > _SUGGESTIONS_PER_CELL:
            text += f"\n… {len(lines) - _SUGGESTIONS_PER_CELL} more"
        return text if len(text) <= _SUGGESTION_CHARS else text[: _SUGGESTION_CHARS - 1] + "…"


def _write_atomic(path: Path, workbook) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    try:
        workbook.save(tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def export_template(bundle_dir: Path, out: Path, *, suggestions: bool = True, force: bool = False) -> dict:
    """Write the template for ``bundle_dir`` to ``out``. Answer cells are left EMPTY."""
    from . import mutations as M

    openpyxl = _openpyxl()
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation

    out = Path(out).expanduser()
    if out.suffix.lower() != ".xlsx":
        raise TemplateRefused("--out must name a .xlsx file.", code=EXIT_USAGE)
    if out.exists() and (out.is_dir() or not force):
        raise TemplateRefused(
            f"{out} already exists. A filled template would be overwritten; pass --force to replace it. Nothing was written.",
            code=EXIT_OUTPUT_REFUSED,
        )
    if not out.parent.is_dir():
        raise TemplateRefused(f"No directory {out.parent}. Nothing was written.", code=EXIT_OUTPUT_REFUSED)
    try:
        bundle = M.load(Path(bundle_dir))
    except M.MutationRefused as exc:
        raise TemplateRefused(str(exc), code=exc.code) from exc
    rows = live_rows(bundle)
    if not rows:
        raise TemplateRefused(
            "This bundle has no live record groups, so there is no run to list. Run `isaac bundle group "
            "<bundle_dir>` first. Nothing was written.",
            code=EXIT_USAGE,
        )
    index = _Index(bundle)
    rules = field_rules()

    wb = openpyxl.Workbook()
    bold = Font(bold=True)
    wrap = Alignment(wrap_text=True, vertical="top")

    # Campaign Info: the labels, EMPTY answer cells.
    ws = wb.active
    ws.title = SHEET_CAMPAIGN
    ws["A1"] = CAMPAIGN_TITLE
    ws["A1"].font = bold
    for i, col in enumerate(CAMPAIGN_FIELDS):
        label = ws.cell(row=CAMPAIGN_FIRST_ROW + i, column=1, value=col.header)
        label.font = Font(italic=col.isaac_added)
        if col.note:
            label.comment = Comment(col.note, "ISAAC")
        ws.cell(row=CAMPAIGN_FIRST_ROW + i, column=2).number_format = "@"
    instructions = (
        "Instructions:",
        "1. Fill in Campaign Info above. One answer applies to every run listed in File List.",
        "   'Facility organization' is the facility's (e.g. SLAC / SSRL); 'Your organization' and 'Your group' are who produced the data.",
        "2. Configurations: add one row per setup (Config ID, Technique, ...).",
        "3. File List: one row per run ISAAC found, named by its file's path. Do not edit File Name or reorder rows.",
        "4. Choose each row's Config ID, then fill what you know. Leave a cell blank if you do not know.",
        "5. Electrolyte is the NAME only (e.g. KOH). Put 0.1 M in 'Electrolyte Concentration (M)' as 0.1, and the pH in 'pH'.",
        "   Those two columns, 'Control Mode', 'Current Set-point (mA/cm2)', 'Reaction Drive' and 'Reaction Catalysis', after Gas Feed,",
        "   are added by ISAAC; they are not in ISAAC's base template. Drive and catalysis are needed for a run that states a reaction.",
        "6. 'ISAAC Suggestions' shows what the files already say, with where. It is evidence, not an answer.",
        "7. Then: isaac bundle template import <bundle_dir> <this file> --by \"<your name>\" (preview), add --apply to record.",
    )
    first_instruction = CAMPAIGN_FIRST_ROW + len(CAMPAIGN_FIELDS) + 2
    for i, line in enumerate(instructions):
        ws.cell(row=first_instruction + i, column=1, value=line)
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 48

    # Configurations: header only.
    wc = wb.create_sheet(SHEET_CONFIG)
    for j, col in enumerate(CONFIG_COLUMNS, start=1):
        wc.cell(row=1, column=j, value=col.header).font = bold
        wc.column_dimensions[_letter(j)].width = 20
        for r in range(2, 2 + CONFIG_ROWS):
            wc.cell(row=r, column=j).number_format = "@"

    # File List: one row per live-group run; File Name only.
    wf = wb.create_sheet(SHEET_FILES)
    for j, col in enumerate(FILE_COLUMNS, start=1):
        head = wf.cell(row=1, column=j, value=col.header)
        head.font = Font(bold=True, italic=col.isaac_added)
        if col.note:
            head.comment = Comment(col.note, "ISAAC")
        wf.column_dimensions[_letter(j)].width = 18
    wf.column_dimensions["A"].width = 48
    for i, row in enumerate(rows, start=2):
        wf.cell(row=i, column=1, value=row["file_name"])
        for j, col in enumerate(FILE_COLUMNS[1:], start=2):
            rule = rules.get(col.path or "")
            if not (rule and rule["numeric"]):
                wf.cell(row=i, column=j).number_format = "@"
    wf.freeze_panes = "B2"
    last = 1 + len(rows)

    # Vocabulary: ISAAC's own lists (target schema / pinned vocabulary), hidden as in ISAAC's template.
    wv = wb.create_sheet(SHEET_VOCAB)
    vocab_ref: dict[str, str] = {}
    for j, (header, path) in enumerate(VOCAB_COLUMNS, start=1):
        wv.cell(row=1, column=j, value=header).font = bold
        allowed = (rules.get(path) or {}).get("allowed") or []
        for i, v in enumerate(allowed, start=2):
            wv.cell(row=i, column=j, value=v)
        if allowed:
            vocab_ref[path] = f"{SHEET_VOCAB}!${_letter(j)}$2:${_letter(j)}${1 + len(allowed)}"
    wv.sheet_state = "hidden"

    def dropdown(sheet, path: str | None, ref: str) -> None:
        if path in vocab_ref:
            dv = DataValidation(type="list", formula1=vocab_ref[path], allow_blank=True, showErrorMessage=True,
                                errorTitle="Not an allowed value", error="Choose a value from the list.")
        elif path and (rules.get(path) or {}).get("numeric"):
            dv = DataValidation(type="decimal", operator="between", formula1="-1E+300", formula2="1E+300",
                                allow_blank=True, showErrorMessage=True, errorTitle="Not a number", error="Enter a number.")
        else:
            return
        sheet.add_data_validation(dv)
        dv.add(ref)

    for j, col in enumerate(FILE_COLUMNS, start=1):
        dropdown(wf, col.path, f"{_letter(j)}2:{_letter(j)}{last}")
    for j, col in enumerate(CONFIG_COLUMNS, start=1):
        dropdown(wc, col.path, f"{_letter(j)}2:{_letter(j)}{1 + CONFIG_ROWS}")
    for i, col in enumerate(CAMPAIGN_FIELDS):
        dropdown(ws, col.path, f"B{CAMPAIGN_FIRST_ROW + i}")
    cfg = DataValidation(type="list", formula1=f"'{SHEET_CONFIG}'!$A$2:$A${1 + CONFIG_ROWS}", allow_blank=True)
    wf.add_data_validation(cfg)
    cfg.add(f"B2:B{last}")

    # ISAAC Suggestions: the File List layout, evidence in each cell; then the campaign block.
    suggester = _Suggester(bundle, index, live={r["run_id"] for r in rows}) if suggestions else None
    coverage: dict[str, int] = {}
    wsg = wb.create_sheet(SHEET_SUGGEST)
    for j, col in enumerate(FILE_COLUMNS, start=1):
        wsg.cell(row=1, column=j, value=col.header).font = bold
        wsg.column_dimensions[_letter(j)].width = 36
    for i, row in enumerate(rows, start=2):
        wsg.cell(row=i, column=1, value=f"{row['run_id']} · group {row['group_id']} · {row['relative_path'] or row['file_name']}")
        if suggester is None:
            continue
        for j, col in enumerate(FILE_COLUMNS, start=1):
            if col.header == "Config ID":
                text = suggester.for_run(row["run_id"], "system.technique")
                text = ("Technique: " + text) if text else ""
                key = "Configurations/Technique"
            elif col.path:
                text = suggester.for_run(row["run_id"], col.path)
                key = f"{SHEET_FILES}/{col.header}"
            else:
                continue
            if text:
                cell = wsg.cell(row=i, column=j, value=text)
                cell.alignment = wrap
                coverage[key] = coverage.get(key, 0) + 1
    block = last + 3
    wsg.cell(row=block, column=1, value=SHEET_CAMPAIGN).font = bold
    for i, col in enumerate(CAMPAIGN_FIELDS, start=1):
        wsg.cell(row=block + i, column=1, value=col.header)
        if suggester is not None and col.path:
            text = suggester.for_campaign(col.path)
            if text:
                wsg.cell(row=block + i, column=2, value=text).alignment = wrap
                coverage[f"{SHEET_CAMPAIGN}/{col.header}"] = 1
    if suggester is None:
        wsg.cell(row=block + len(CAMPAIGN_FIELDS) + 2, column=1,
                 value="Exported with --no-suggestions: no parser value is shown, so no exposure was recorded.")
    wsg.freeze_panes = "B2"

    # _isaac: the marker and the mappings.
    exported = _now_utc()
    wm = wb.create_sheet(SHEET_MARKER)
    meta = [
        ("format", FORMAT_ID), ("format_version", FORMAT_VERSION), ("bundle_id", bundle["bundle_id"]),
        ("bundle_format_version", bundle.get("format_version")), ("exported_utc", exported),
        ("notice", "Written by `isaac bundle template export`. Do not edit this sheet: import reads it to know "
                   "which row is which run and which column is which official field."),
    ]
    r = 1
    wm.cell(row=r, column=1, value="[meta]")
    for k, v in meta:
        r += 1
        wm.cell(row=r, column=1, value=k)
        wm.cell(row=r, column=2, value=v)
    r += 2
    wm.cell(row=r, column=1, value="[rows]")
    r += 1
    for j, h in enumerate(("sheet", "row", "run_id", "run_key", "group_id", "file_name"), start=1):
        wm.cell(row=r, column=j, value=h)
    for i, row in enumerate(rows, start=2):
        r += 1
        for j, v in enumerate((SHEET_FILES, i, row["run_id"], row["run_key"], row["group_id"], row["file_name"]), start=1):
            wm.cell(row=r, column=j, value=v)
    r += 2
    wm.cell(row=r, column=1, value="[columns]")
    r += 1
    for j, h in enumerate(("sheet", "cell_or_column", "header", "target_field_path", "status", "accepts"), start=1):
        wm.cell(row=r, column=j, value=h)
    columns_report = []

    def column_row(sheet, where, col):
        nonlocal r
        status, reason = index.status(col)
        rule = rules.get(col.path or "") or {}
        accepts = ("one of: " + ", ".join(map(str, rule["allowed"]))) if rule.get("allowed") else (
            "a number" if rule.get("numeric") else "text")
        r += 1
        for j, v in enumerate((sheet, where, col.header, col.path, status, accepts), start=1):
            wm.cell(row=r, column=j, value=v)
        columns_report.append({"sheet": sheet, "where": where, "header": col.header, "target_field_path": col.path,
                               "status": status, "reason": reason})

    for i, col in enumerate(CAMPAIGN_FIELDS):
        column_row(SHEET_CAMPAIGN, f"B{CAMPAIGN_FIRST_ROW + i}", col)
    for j, col in enumerate(CONFIG_COLUMNS, start=1):
        column_row(SHEET_CONFIG, _letter(j), col)
    for j, col in enumerate(FILE_COLUMNS, start=1):
        column_row(SHEET_FILES, _letter(j), col)
    wm.sheet_state = "hidden"

    # THE SUGGESTIONS PRINT PARSER VALUES: that is an exposure, recorded before the file exists.
    if suggester is not None and suggester.exposed:
        try:
            M.expose_and_load(Path(bundle_dir), suggester.exposed, "bundle template export")
        except M.MutationRefused as exc:
            raise TemplateRefused(f"Nothing written: {exc}", code=exc.code) from exc
    _write_atomic(out, wb)
    return {
        "written": str(out),
        "format": FORMAT_ID,
        "format_version": FORMAT_VERSION,
        "bundle_id": bundle["bundle_id"],
        "exported_utc": exported,
        "file_list_rows": len(rows),
        "sheets": list(wb.sheetnames),
        "hidden_sheets": [n for n in wb.sheetnames if wb[n].sheet_state == "hidden"],
        "bundle_dir": str(bundle_dir),
        "columns": columns_report,
        "suggestions": {"shown": suggester is not None, "cells_by_column": coverage,
                        "exposures_recorded": len(suggester.exposed) if suggester else 0},
        "statement": "Every answer cell is empty. ISAAC Suggestions is evidence, not an answer.",
    }


def render_export_summary(result: Mapping) -> str:
    """The short text ``template export`` prints: where, how many rows, which sheets, how to import.
    The column mapping is in ``--json`` (and in the workbook's hidden ``_isaac`` sheet)."""
    hidden = set(result.get("hidden_sheets") or ())
    visible = [n for n in result.get("sheets") or () if n not in hidden]
    mapped = [c for c in result["columns"] if c["status"] == "mapped"]
    not_here = [c for c in result["columns"] if c["status"] == "no_target_in_bundle"]
    sug = result["suggestions"]
    lines = [
        f"Wrote {result['written']} (template {result['format_version']}, bundle {result['bundle_id']}).",
        f"{result['file_list_rows']} File List row(s), one per run of a live record group. Sheets: {', '.join(visible)}"
        + (f" (hidden: {', '.join(n for n in result['sheets'] if n in hidden)})." if hidden else "."),
        f"{len(mapped)} answer cell(s)/column(s) map to a field of this bundle; {len(not_here)} map to a field this bundle "
        "holds no target for, and the rest to no official field (--json lists every column).",
        (f"ISAAC Suggestions: {sum(sug['cells_by_column'].values())} cell(s) of evidence; "
         f"{sug['exposures_recorded']} exposure(s) recorded." if sug["shown"] else
         "ISAAC Suggestions: not shown (--no-suggestions); no exposure recorded."),
        result["statement"],
        f"When it is filled: isaac bundle template import {result.get('bundle_dir') or '<bundle_dir>'} {result['written']} "
        '--by "<your name>"   (a preview; add --apply to record)',
    ]
    return "\n".join(lines)


# --- import -------------------------------------------------------------------------------------


def _marker(wb) -> dict:
    if SHEET_MARKER not in wb.sheetnames:
        raise TemplateRefused(
            "This workbook has no `_isaac` sheet, so ISAAC cannot tell which bundle, run or field any cell "
            "belongs to (ISAAC's blank template also holds example values that are not answers). Run "
            "`isaac bundle template export <bundle_dir> --out <file.xlsx>` and fill that file. Nothing was recorded.",
            code=EXIT_INPUT_REFUSED,
        )
    ws = wb[SHEET_MARKER]
    meta: dict[str, Any] = {}
    rows: dict[int, dict] = {}
    columns: list[dict] = []
    section = None
    header: list[str] = []
    for values in ws.iter_rows(values_only=True):
        first = values[0] if values else None
        if first in ("[meta]", "[rows]", "[columns]"):
            section, header = first, []
            continue
        if first is None:
            continue
        if section == "[meta]":
            meta[str(first)] = values[1] if len(values) > 1 else None
        elif section in ("[rows]", "[columns]"):
            if not header:
                header = [str(v) for v in values if v is not None]
                continue
            entry = dict(zip(header, values))
            if section == "[rows]":
                try:
                    rows[int(entry["row"])] = entry
                except (TypeError, ValueError, KeyError) as exc:
                    raise TemplateRefused(f"The `_isaac` sheet's row mapping is damaged ({entry!r}). Re-export the template.",
                                          code=EXIT_INPUT_REFUSED) from exc
            else:
                columns.append(entry)
    return {"meta": meta, "rows": rows, "columns": columns}


def _cell_ref(sheet: str, ref: str) -> str:
    return f"'{sheet}'!{ref}"


def _read_workbook(xlsx: Path):
    openpyxl = _openpyxl()
    import warnings
    from zipfile import BadZipFile

    xlsx = Path(xlsx).expanduser()
    if not xlsx.is_file():
        raise TemplateRefused(f"No file at {xlsx}.", code=EXIT_NOT_FOUND)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return openpyxl.load_workbook(xlsx, data_only=False)
    except (BadZipFile, OSError, KeyError, ValueError) as exc:
        raise TemplateRefused(f"{xlsx.name} is not a readable .xlsx workbook ({type(exc).__name__}). Nothing was recorded.",
                              code=EXIT_INPUT_REFUSED) from exc


def _raw(cell) -> tuple[Any, str | None]:
    """The cell's typed value, or a refusal for a formula. ``(None, None)`` = empty."""
    if cell.data_type == "f" or (isinstance(cell.value, str) and cell.value.startswith("=")):
        return None, "a formula, not a value: type the value itself"
    value = cell.value
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    return value, None


def read_cells(wb, marker: Mapping, bundle: Mapping, file_label: str) -> dict:
    """Every non-empty answer cell, parsed and validated, as ``planned`` / ``invalid`` /
    ``unmapped`` / ``nowhere`` entries. Pure: decides nothing."""
    index = _Index(bundle)
    rules = field_rules()
    by_header = {(c.get("sheet"), c.get("header")): c for c in marker["columns"]}
    known = {c.header: c for c in (*CAMPAIGN_FIELDS, *CONFIG_COLUMNS, *FILE_COLUMNS)}
    out: dict[str, list] = {"cells": [], "invalid": [], "unmapped": {}, "nowhere": [], "rows_refused": []}
    for name in (SHEET_CAMPAIGN, SHEET_CONFIG, SHEET_FILES):
        if name not in wb.sheetnames:
            raise TemplateRefused(f"The workbook has no {name!r} sheet. Re-export the template.", code=EXIT_INPUT_REFUSED)

    def cite(sheet, ref):
        return f"template {file_label} {_cell_ref(sheet, ref)}"

    def unmapped(sheet, col: Column, ref: str, value: Any, reason: str | None = None):
        status, why = index.status(col)
        key = f"{sheet}/{col.header}"
        entry = out["unmapped"].setdefault(key, {
            "sheet": sheet, "header": col.header, "target_field_path": col.path,
            "reason": ("recorded nowhere: no official field" + (f" ({col.why_none})" if col.why_none else ""))
            if status == "no_official_field" else f"recorded nowhere: {why}",
            "cells": [],
        })
        entry["cells"].append({"cell": _cell_ref(sheet, ref), "value": value, **({"note": reason} if reason else {})})

    def check_header(sheet, ws, where: str, col: Column, label_cell: str | None = None):
        labels = (col.header, *col.aliases)  # an alias is the same cell and path under another version's label
        mapped = next((by_header[(sheet, h)] for h in labels if (sheet, h) in by_header), None)
        if mapped is None or str(mapped.get("cell_or_column")) != where or mapped.get("target_field_path") != col.path:
            raise TemplateRefused(
                f"The `_isaac` sheet does not map {sheet!r} {col.header!r} to {where} as this build writes it. "
                "Re-export the template with this build.", code=EXIT_INPUT_REFUSED)
        shown = ws[label_cell].value if label_cell else ws[f"{where}1"].value
        if (shown or "").strip() not in labels:
            raise TemplateRefused(
                f"{_cell_ref(sheet, label_cell or where + '1')} should read {col.header!r} but reads {shown!r}: "
                "the columns were moved or renamed, so no cell can be mapped safely. Re-export the template.",
                code=EXIT_INPUT_REFUSED)

    def take(sheet, ref, col: Column, raw: Any, *, run: Mapping | None, scope: str, via: str | None = None):
        rule = rules.get(col.path or "")
        value, why = _parse(raw, rule)
        if why:
            if not any(i["cell"] == _cell_ref(sheet, ref) for i in out["invalid"]):  # a Technique cell many rows reach
                out["invalid"].append({"cell": _cell_ref(sheet, ref), "header": col.header, "value": raw, "reason": why})
            return
        if value is None:
            return
        status, reason = index.status(col)
        if status != "mapped":
            unmapped(sheet, col, ref, value)
            return
        note = cite(sheet, ref) + (f" (via {via})" if via else "")
        out["cells"].append({"cell": _cell_ref(sheet, ref) + (f" via {via}" if via else ""), "sheet": sheet,
                             "header": col.header, "path": col.path, "value": value, "scope": scope,
                             "run_id": run["run_id"] if run else None, "note": note})

    # Campaign Info: the rows THIS workbook's version wrote (1.3.0 and earlier: five, "Organization")
    wsc = wb[SHEET_CAMPAIGN]
    workbook_version = (marker.get("meta") or {}).get("format_version")
    for i, col in enumerate(campaign_fields_of(workbook_version)):
        row = CAMPAIGN_FIRST_ROW + i
        check_header(SHEET_CAMPAIGN, wsc, f"B{row}", col, label_cell=f"A{row}")
        raw, why = _raw(wsc[f"B{row}"])
        if why:
            out["invalid"].append({"cell": _cell_ref(SHEET_CAMPAIGN, f"B{row}"), "header": col.header, "value": wsc[f"B{row}"].value, "reason": why})
            continue
        if raw is None:
            continue
        out["read"] = out.get("read", 0) + 1
        if col.path is None:
            unmapped(SHEET_CAMPAIGN, col, f"B{row}", raw)
        else:
            take(SHEET_CAMPAIGN, f"B{row}", col, raw, run=None, scope="experiment")

    # Configurations: read every row; Technique reaches a run through File List's Config ID.
    wcf = wb[SHEET_CONFIG]
    for j, col in enumerate(CONFIG_COLUMNS, start=1):
        check_header(SHEET_CONFIG, wcf, _letter(j), col)
    configs: dict[str, dict] = {}
    duplicate: set[str] = set()
    for r in range(2, wcf.max_row + 1):
        cid_raw, _ = _raw(wcf.cell(row=r, column=1))
        cid = str(cid_raw).strip() if cid_raw is not None else None
        cells = {}
        for j, col in enumerate(CONFIG_COLUMNS, start=1):
            raw, why = _raw(wcf.cell(row=r, column=j))
            ref = f"{_letter(j)}{r}"
            if why:
                out["invalid"].append({"cell": _cell_ref(SHEET_CONFIG, ref), "header": col.header, "value": wcf[ref].value, "reason": why})
                continue
            if raw is None:
                continue
            out["read"] = out.get("read", 0) + 1
            cells[col.header] = (ref, raw)
        if not cells:
            continue
        if not cid:
            for header, (ref, raw) in cells.items():
                out["invalid"].append({"cell": _cell_ref(SHEET_CONFIG, ref), "header": header, "value": raw,
                                       "reason": "this Configurations row has no Config ID, so no run can refer to it"})
            continue
        if cid in configs:
            duplicate.add(cid)
        configs[cid] = {"row": r, "cells": cells}
        for header, (ref, raw) in cells.items():
            col = known[header]
            if col.path is None and header != "Config ID":
                unmapped(SHEET_CONFIG, col, ref, raw)
    for cid in duplicate:
        out["invalid"].append({"cell": _cell_ref(SHEET_CONFIG, f"A{configs[cid]['row']}"), "header": "Config ID", "value": cid,
                               "reason": "this Config ID is defined on more than one row, so which row a File List row means is unknown"})

    # File List
    wfl = wb[SHEET_FILES]
    file_columns = file_columns_of(workbook_version)
    for j, col in enumerate(file_columns, start=1):
        check_header(SHEET_FILES, wfl, _letter(j), col)
    runs = {r["run_id"]: r for r in bundle["runs"]}
    rows = marker["rows"]
    # ROW IDENTITY MUST BE UNIQUE in the mapping itself, or a moved row could match a wrong run.
    for key in ("file_name", "run_id"):
        seen: dict[str, int] = {}
        for rnum, entry in sorted(rows.items()):
            v = str(entry.get(key))
            if v in seen:
                raise TemplateRefused(
                    f"The `_isaac` sheet names {key} {v!r} on rows {seen[v]} and {rnum}, so a row's run cannot be "
                    "told apart. Re-export the template. Nothing was recorded.", code=EXIT_INPUT_REFUSED)
            seen[v] = rnum
    row_of_name = {str(e.get("file_name")): rnum for rnum, e in rows.items()}
    # the runs a Campaign Info answer reaches: the File List's runs that are still in a live group
    out["file_list_run_ids"] = {str(e.get("run_id")) for e in rows.values()} & live_run_ids(bundle)
    max_row = max([wfl.max_row, *rows]) if rows else wfl.max_row
    for r in range(2, max_row + 1):
        entry = rows.get(r)
        values = []
        for j, col in enumerate(file_columns, start=1):
            raw, why = _raw(wfl.cell(row=r, column=j))
            values.append((col, f"{_letter(j)}{r}", raw, why))
        # A cell typed where a LATER template version has a column this workbook's version does not
        # (e.g. past pH in a 1.1.0 workbook) is not read, and is SAID, never dropped silently.
        for j, col in enumerate(FILE_COLUMNS[len(file_columns):], start=len(file_columns) + 1):
            raw = wfl.cell(row=r, column=j).value
            if raw is not None and not (isinstance(raw, str) and not raw.strip()):
                out["nowhere"].append({
                    "cell": _cell_ref(SHEET_FILES, f"{_letter(j)}{r}"), "header": col.header, "value": raw,
                    "reason": (f"this workbook is template {workbook_version!r}, which has no column {_letter(j)} "
                               f"({col.header} was added in {COLUMNS_ADDED_IN.get(col.header)}), so the cell is not "
                               "read; re-export the template to answer it"),
                })
        answered = [v for v in values[1:] if v[2] is not None or v[3]]
        if entry is None:
            if answered:
                out["rows_refused"].append({"row": r, "reason": "ISAAC did not export this row, so it names no run; its cells are recorded nowhere",
                                            "cells": [_cell_ref(SHEET_FILES, ref) for _, ref, _, _ in answered]})
            continue
        run = runs.get(str(entry.get("run_id")))
        name_cell = wfl.cell(row=r, column=1).value
        # EXACT match, not trimmed or case-folded: the name is the row's identity.
        if run is None or not isinstance(name_cell, str) or name_cell != str(entry.get("file_name")):
            elsewhere = row_of_name.get(name_cell) if isinstance(name_cell, str) else None
            if answered:
                out["rows_refused"].append({
                    "row": r,
                    "reason": (f"File Name reads {name_cell!r} but ISAAC exported {entry.get('file_name')!r} on this row"
                               + (f" ({name_cell!r} was exported on row {elsewhere}: rows were reordered)" if elsewhere else
                                  " (the name was edited)")
                               + ", so the row's run is unknown; nothing on it is recorded")
                    if run is not None else f"the run {entry.get('run_id')!r} is not in this bundle",
                    "cells": [_cell_ref(SHEET_FILES, ref) for _, ref, _, _ in answered],
                })
            continue
        for col, ref, raw, why in values[1:]:
            if why:
                out["invalid"].append({"cell": _cell_ref(SHEET_FILES, ref), "header": col.header, "value": wfl[ref].value, "reason": why})
                continue
            if raw is None:
                continue
            out["read"] = out.get("read", 0) + 1
            if col.header == "Config ID":
                cid = str(raw).strip()
                if cid in duplicate:
                    continue  # reported on the Configurations row
                config = configs.get(cid)
                if config is None:
                    out["invalid"].append({"cell": _cell_ref(SHEET_FILES, ref), "header": col.header, "value": raw,
                                           "reason": f"no Configurations row has Config ID {cid!r}"})
                    continue
                tech = config["cells"].get("Technique")
                if tech is not None:
                    take(SHEET_CONFIG, tech[0], known["Technique"], tech[1], run=run, scope="run",
                         via=_cell_ref(SHEET_FILES, ref))
                continue
            take(SHEET_FILES, ref, col, raw, run=run, scope="run")
    # Technique cells of configurations no row refers to: read, but they reach no run.
    used = {str(wfl.cell(row=r, column=2).value).strip() for r in rows if wfl.cell(row=r, column=2).value is not None}
    for cid, config in configs.items():
        tech = config["cells"].get("Technique")
        if tech is not None and cid not in used and cid not in duplicate:
            out["nowhere"].append({"cell": _cell_ref(SHEET_CONFIG, tech[0]), "header": "Technique", "value": tech[1],
                                   "reason": f"no File List row chose Config ID {cid!r}, so it reaches no run"})
    return out


def _same_value(a: Any, b: Any) -> bool:
    """Equal as values: numbers by number (``0.1 == 0.1``, ``1 == 1.0``), everything else by type
    and value. ``True`` is not ``1``; ``"0.1"`` is not ``0.1``."""
    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    if num(a) and num(b):
        return a == b
    return type(a) is type(b) and a == b


def _prior(bundle: Mapping, kind: str, obj: Mapping, latest: Mapping) -> Mapping | None:
    if kind == "candidate":
        return B.candidate_decision(bundle, obj, latest)
    return latest.get((kind, obj["value_id"]))


def plan_and_record(bundle: dict, cells: Mapping, *, by: str, orcid: str | None, supersede: bool) -> dict:
    """Turn read cells into decisions ON ``bundle`` (in memory) through
    :func:`mutations.record_decision`. The caller saves it (``--apply``) or discards it (preview)."""
    from . import mutations as M

    index = _Index(bundle)
    latest = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    report: dict[str, list] = {"decisions": [], "clashes": [], "already": [], "refused": [], "nowhere": list(cells["nowhere"]),
                               "left_alone": [], "campaign_not_filled": []}
    reached = cells.get("file_list_run_ids") or set()
    planned: list[tuple[dict, str, str, Mapping, str]] = []  # (cell, decision, kind, obj, target_id)
    for cell in cells["cells"]:
        path, value = cell["path"], cell["value"]
        targets: list[tuple[str, str, Mapping, str]] = []
        if cell["scope"] == "experiment":
            outside = []
            for m in index.missing_by_path.get(path, []):
                if m["run_id"] is None or m["run_id"] in reached:  # record scope, or a File List run
                    targets.append(("correct", "missing_value", m, m["value_id"]))
                else:
                    outside.append(m)
            if outside:
                report["campaign_not_filled"].append({
                    "cell": cell["cell"], "target_field_path": path, "targets": len(outside),
                    "run_ids": sorted({m["run_id"] for m in outside})[:20],
                    "reason": "these runs are not in the template's File List or no longer in a live record group, so a "
                              "Campaign Info answer does not reach them; nothing was recorded for them",
                })
            extracted = [c for c in index.cands_by_path.get(path, [])]
            if extracted:
                report["left_alone"].append({
                    "cell": cell["cell"], "target_field_path": path, "candidates": len(extracted),
                    "reason": "a Campaign Info answer fills only the targets no source states; these extracted values "
                              "are left for you to confirm or correct per run",
                })
        else:
            for m in index.missing_by_run.get((cell["run_id"], path), []):
                targets.append(("correct", "missing_value", m, m["value_id"]))
            for c in index.cands_by_run.get((cell["run_id"], path), []):
                targets.append(("confirm" if _same_value(c["value"], value) else "correct", "candidate", c, c["candidate_id"]))
        if not targets:
            report["nowhere"].append({"cell": cell["cell"], "header": cell["header"], "value": value,
                                      "reason": f"this run has no missing or extracted value for {path} in this bundle"})
            continue
        for decision, kind, obj, tid in targets:
            planned.append((cell, decision, kind, obj, tid))

    # Two cells of THIS workbook giving one target different values: neither is recorded.
    values_of: dict[str, set[str]] = {}
    for cell, _d, _k, _o, tid in planned:
        values_of.setdefault(tid, set()).add(repr(cell["value"]))
    split = {tid for tid, vs in values_of.items() if len(vs) > 1}
    calls: dict[tuple, list[str]] = {}
    seen_target: set[str] = set()
    for cell, decision, kind, obj, tid in planned:
        if tid in split:
            report["clashes"].append({"cell": cell["cell"], "target": {"kind": kind, "id": tid}, "value": cell["value"],
                                      "reason": "another cell of this workbook gives this target a different value; neither is recorded"})
            continue
        if tid in seen_target:
            continue
        seen_target.add(tid)
        prior = _prior(bundle, kind, obj, latest)
        if prior is not None and prior.get("decision") in (B.CONFIRMING_DECISIONS | {"reject"}):
            base = obj.get("value") if kind == "candidate" else None
            before = B.final_value(base, prior)
            if _same_value(before, cell["value"]) and prior.get("decision") != "reject":
                report["already"].append({"cell": cell["cell"], "target": {"kind": kind, "id": tid}, "value": cell["value"],
                                          "decided_by": (prior.get("decided_by") or {}).get("name"), "decision_id": prior.get("decision_id")})
                continue
            if not supersede:
                report["clashes"].append({
                    "cell": cell["cell"], "target": {"kind": kind, "id": tid}, "value": cell["value"],
                    "existing": {"decision": prior.get("decision"), "value": before, "decision_id": prior.get("decision_id"),
                                 "decided_by": (prior.get("decided_by") or {}).get("name")},
                    "reason": "an earlier scientist decision gives a different value; skipped (pass --supersede to record this one)",
                })
                continue
        call = calls.setdefault((cell["cell"], decision), {"cell": cell, "decision": decision, "tids": []})
        call["tids"].append(tid)
        report["decisions"].append({"cell": cell["cell"], "sheet": cell["sheet"], "header": cell["header"],
                                    "target": {"kind": kind, "id": tid}, "target_field_path": cell["path"],
                                    "run_id": obj.get("run_id"), "decision": decision, "value": cell["value"]})

    recorded: list[str] = []
    unchanged: list[str] = []
    refused_targets: set[str] = set()
    for call in calls.values():
        cell, decision, tids = call["cell"], call["decision"], call["tids"]
        try:
            res = M.record_decision(bundle, target_ids=tids, decision=decision, value=cell["value"], by=by, orcid=orcid,
                                    note=cell["note"])
        except M.MutationRefused as exc:
            report["refused"].append({"cell": cell["cell"], "targets": tids, "decision": decision, "reason": str(exc)})
            refused_targets.update(tids)
            continue
        recorded += res["recorded"]
        unchanged += res["unchanged"]
    report["decisions"] = [d for d in report["decisions"] if d["target"]["id"] not in refused_targets]
    report["recorded_target_ids"] = recorded
    report["unchanged_target_ids"] = unchanged
    return report


def import_template(bundle_dir: Path, xlsx: Path, *, by: str, orcid: str | None = None,
                    apply: bool = False, supersede: bool = False) -> dict:
    """Read a filled template. Preview (default) writes nothing; ``apply`` records."""
    from . import mutations as M

    problem = B.decider_name_problem(by)
    if problem:
        raise TemplateRefused(f"--by is required: the name of the person whose answers these are (this one {problem}).")
    if orcid is not None and not M.ORCID_RE.fullmatch(orcid):
        raise TemplateRefused("--orcid must look like 0000-0000-0000-0000 (last character may be X).")
    xlsx = Path(xlsx).expanduser()
    wb = _read_workbook(xlsx)
    marker = _marker(wb)
    meta = marker["meta"]
    if meta.get("format") != FORMAT_ID:
        raise TemplateRefused(f"The `_isaac` sheet names format {meta.get('format')!r}, not {FORMAT_ID}. Run "
                              "`isaac bundle template export` and fill that file. Nothing was recorded.", code=EXIT_INPUT_REFUSED)
    if str(meta.get("format_version") or "").split(".")[0] != FORMAT_VERSION.split(".")[0]:
        raise TemplateRefused(f"Template version {meta.get('format_version')!r} is not readable by this build "
                              f"({FORMAT_VERSION}). Re-export the template. Nothing was recorded.", code=EXIT_INPUT_REFUSED)
    try:
        current = M.load(Path(bundle_dir))
    except M.MutationRefused as exc:
        raise TemplateRefused(str(exc), code=exc.code) from exc
    if meta.get("bundle_id") != current["bundle_id"]:
        raise TemplateRefused(
            f"This template was exported from bundle {meta.get('bundle_id')!r}, not this one "
            f"({current['bundle_id']}). Run `isaac bundle template export {bundle_dir} --out <file.xlsx>` and fill "
            "that file. Nothing was recorded.", code=EXIT_INPUT_REFUSED)

    def run(bundle):
        cells = read_cells(wb, marker, bundle, xlsx.name)
        report = plan_and_record(bundle, cells, by=by, orcid=orcid, supersede=supersede)
        return cells, report

    if apply:
        with M.locked(Path(bundle_dir)):
            bundle = M.load(Path(bundle_dir))
            cells, report = run(bundle)
            if report["recorded_target_ids"]:  # nothing recorded: the bundle is not rewritten
                M.save_bundle(Path(bundle_dir), bundle)
    else:
        cells, report = run(current)  # in memory only; nothing is saved
    return {
        "applied": apply,
        "template": xlsx.name,
        "bundle_id": current["bundle_id"],
        "exported_utc": meta.get("exported_utc"),
        "cells_read": cells.get("read", 0),
        "decisions": report["decisions"],
        "recorded": len(report["recorded_target_ids"]) if apply else 0,
        "would_record": len(report["recorded_target_ids"]),
        "unchanged": len(report["unchanged_target_ids"]),
        "already_decided_same_value": report["already"],
        "invalid_cells": cells["invalid"],
        "clashes": report["clashes"],
        "refused": report["refused"],
        "unmapped_columns": list(cells["unmapped"].values()),
        "recorded_nowhere": report["nowhere"],
        "rows_refused": cells["rows_refused"],
        "extracted_values_left_alone": report["left_alone"],
        "campaign_not_filled": report["campaign_not_filled"],
        "statement": ("Recorded as scientist decisions (identity: self_reported_local_user, unverified)."
                      if apply else "PREVIEW: nothing was written. Add --apply to record these decisions."),
    }


#: How many cells a compact report names per column before it says how many more.
_CELLS_SHOWN = 3


def _decision_lines(rep: Mapping) -> list[str]:
    """One line per Campaign Info cell, Configurations cell, or File List column: how many
    decisions it gives, of which kind, to which field."""
    groups: dict[str, dict] = {}
    for d in rep["decisions"]:
        sheet = d.get("sheet") or ""
        if sheet == SHEET_FILES:
            key = f"{SHEET_FILES} / {d.get('header')}"
        else:
            key = f"{d['cell'].split(' via ', 1)[0]} {d.get('header') or ''}".rstrip()
        g = groups.setdefault(key, {"path": d["target_field_path"], "n": 0, "kinds": {}, "runs": set(), "values": set(),
                                    "per_row": sheet == SHEET_FILES or " via " in d["cell"]})
        g["n"] += 1
        g["kinds"][d["decision"]] = g["kinds"].get(d["decision"], 0) + 1
        g["values"].add(repr(d["value"]))
        if d.get("run_id"):
            g["runs"].add(d["run_id"])
    out = []
    for key, g in groups.items():
        kinds = ", ".join(f"{k} {n}" for k, n in sorted(g["kinds"].items()))
        rows = f" over {len(g['runs'])} row(s)" if g["per_row"] else ""
        value = f" = {next(iter(g['values']))}" if len(g["values"]) == 1 else f"; {len(g['values'])} distinct values"
        out.append(f"  {key} -> {g['path']}: {g['n']} decision(s){rows} ({kinds}){value}")
    return out


def _grouped_cells(items: Sequence[Mapping], *, key: str = "header") -> list[str]:
    """One line per column (and reason) with a few of its cells named, for a long list of cells."""
    groups: dict[tuple, list[str]] = {}
    for x in items:
        groups.setdefault((x.get(key), x.get("reason")), []).append(x.get("cell") or f"row {x.get('row')}")
    out = []
    for (header, reason), cells in groups.items():
        more = f" and {len(cells) - _CELLS_SHOWN} more" if len(cells) > _CELLS_SHOWN else ""
        out.append(f"  {header}: {len(cells)} cell(s) ({', '.join(cells[:_CELLS_SHOWN])}{more}): {reason}")
    return out


def render_report(rep: Mapping, *, full: bool = False) -> str:
    """Plain text for the terminal. COMPACT by default: one line per cell or column with its number
    of decisions, then every invalid cell, clash, refusal and refused row in full, and the totals.
    ``full``: one line per decision and per cell, as ``--json`` holds them."""
    lines = []
    add = lines.append
    add(("APPLIED" if rep["applied"] else "PREVIEW (nothing written)") + f": template {rep['template']} -> bundle {rep['bundle_id']}")
    add("")
    verb = "recorded" if rep["applied"] else "would record"
    if full:
        add(f"Decisions ({verb}):")
        for d in rep["decisions"]:
            where = f" {d['run_id']}" if d.get("run_id") else ""
            add(f"  {d['cell']}: {d['decision']} {d['target']['kind']} {d['target']['id']}{where} {d['target_field_path']} = {d['value']!r}")
    else:
        add(f"Decisions ({verb}), one line per cell or column:")
        lines += _decision_lines(rep)
    if not rep["decisions"]:
        add("  (none)")
    in_full = [("Invalid cells (recorded as nothing)", "invalid_cells"), ("Clashes (skipped)", "clashes"),
               ("Refused", "refused"), ("Rows refused", "rows_refused")]
    if full:
        in_full.insert(3, ("Recorded nowhere (no target for that run/field)", "recorded_nowhere"))
    for title, key in in_full:
        if rep[key]:
            add("")
            add(f"{title}:")
            for x in rep[key]:
                add(f"  {x.get('cell', 'row ' + str(x.get('row')))}: {x.get('reason')}"
                    + (f" (value {x['value']!r})" if "value" in x else ""))
    if rep["recorded_nowhere"] and not full:
        add("")
        add("Recorded nowhere (no target for that run/field):")
        lines += _grouped_cells(rep["recorded_nowhere"])
    if rep["unmapped_columns"]:
        add("")
        add("Unmapped columns:")
        for u in rep["unmapped_columns"]:
            if full:
                add(f"  {u['sheet']} / {u['header']}: {u['reason']}")
                for c in u["cells"]:
                    add(f"    {c['cell']} = {c['value']!r}")
            else:
                cells = [c["cell"] for c in u["cells"]]
                more = f" and {len(cells) - _CELLS_SHOWN} more" if len(cells) > _CELLS_SHOWN else ""
                add(f"  {u['sheet']} / {u['header']}: {len(cells)} cell(s) ({', '.join(cells[:_CELLS_SHOWN])}{more}); {u['reason']}")
    if rep.get("campaign_not_filled"):
        add("")
        add("Campaign Info answers not filled for runs outside the File List:")
        for x in rep["campaign_not_filled"]:
            add(f"  {x['cell']} {x['target_field_path']}: {x['targets']} target(s) (runs {', '.join(map(str, x['run_ids']))}); {x['reason']}")
    if rep["extracted_values_left_alone"]:
        add("")
        add("Extracted values left alone:")
        for x in rep["extracted_values_left_alone"]:
            add(f"  {x['cell']} {x['target_field_path']}: {x['candidates']} extracted value(s); {x['reason']}")
    add("")
    add(
        f"Summary: {rep['cells_read']} cells read; {rep['recorded'] if rep['applied'] else rep['would_record']} decision(s) "
        f"{verb}; {rep['unchanged']} unchanged; {len(rep['already_decided_same_value'])} already decided with the same value; "
        f"{len(rep['invalid_cells'])} invalid; {len(rep['clashes'])} clash(es); {len(rep['refused'])} refused; "
        f"{sum(len(u['cells']) for u in rep['unmapped_columns'])} cell(s) in {len(rep['unmapped_columns'])} unmapped column(s); "
        f"{len(rep['recorded_nowhere'])} recorded nowhere; {len(rep['rows_refused'])} row(s) refused."
    )
    add(rep["statement"])
    if not full:
        add("(--full lists every decision and cell; --json prints the whole report.)")
    return "\n".join(lines)
