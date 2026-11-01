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
with its cells: nothing is dropped silently, and no mapping is guessed. A cell that REPLACES an
extracted value, or contradicts the run's own file-name token (``m800mV``) or an AI reading of a file,
is named on its own line; one ``adopt`` copied from their sheet before that reading existed is not
recorded but awaits a ruling.

ADOPT (``isaac bundle template adopt``) reads the scientist's OWN filled copy of ISAAC's template
(no ``_isaac`` sheet) and writes this bundle's template from it: their value goes into an answer
cell only where no file reading contradicts it; every other one is a row of the ``Disagreements``
sheet with an empty "Your ruling" cell, which IMPORT reads for exactly the runs that row names. A row lists every
reading of its field (agreeing ones marked); a Campaign Info beamline or facility acronym that names another one
than a facility hint (the folder's name, the acquisition system's) is a row too; an Electrolyte row that states a
concentration takes it in its own ruling cell ("Your ruling: concentration (M)"). A ruling for a field the bundle
asks once for the whole beamtime is recorded per run (``mutations.run_answer_targets``), never beamtime-wide.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import secrets
import shlex
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
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
#: r3a L6: the label of the Campaign Info block's hint column on :data:`SHEET_SUGGEST` (not a File List header)
SUGGEST_CAMPAIGN_HEADER = "What the files say for this Campaign Info row (a hint, not an answer)"
SHEET_MARKER = "_isaac"
#: ``template adopt`` only: every value of the scientist's own sheet that a file reading contradicts, or
#: that the field does not take, with an empty "Your ruling" column (:data:`DISAGREE_RULING_COLUMN`).
SHEET_DISAGREE = "Disagreements"
DISAGREE_HEADERS = ("ID", "What", "Field", "Their value", "Their cell(s)", "File reading(s)", "Run(s)", "Your ruling",
                    "Where your ruling goes", "Your ruling: concentration (M)")
DISAGREE_RULING_COLUMN = "H"
#: c7-s: an Electrolyte row whose value also states a concentration ("0.01 M HClO4") takes TWO rulings, the name in
#: "Your ruling" and the concentration (mol/L) here, both recorded for exactly that row's runs. Appended after
#: "Where your ruling goes", so a workbook adopt wrote before it (nine columns) still imports as it did.
DISAGREE_CONC_COLUMN = "J"

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


ELECTROLYTE_NAME_PATH = "context.electrochemistry.electrolyte.name"
ELECTROLYTE_CONC_PATH = "context.electrochemistry.electrolyte.concentration_M"
POTENTIAL_PATH = "context.electrochemistry.potential_setpoint_V"
PH_PATH = "context.electrochemistry.pH"
#: A concentration's SHAPE in a text ("0.01 M HClO4", "1M KOH", "KOH 100 mM", and ``1e-3 M`` too): only RECOGNISES
#: that the text states one (a name cell refused as name only, a comment line that mentions a concentration). Its
#: number is never read from this match: :func:`electrolyte_statement` reads a statement, or nothing.
_CONCENTRATION_IN_NAME = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?|\.\d+)\s*(mM|\u00b5M|\u03bcM|M|mol\s*/\s*L)(?![A-Za-z])")
#: r1d: THE ELECTROLYTE GRAMMAR, one for the template and for the scan-header comment rule
#: (``questions.header_comment_readings``): a statement is read ONLY when the whole of it is ``<number> <unit>
#: <formula>`` or ``<formula> <number> <unit>``: the number a plain decimal (no exponent, no comma decimal, no
#: ``x10``), the unit ``M``, ``mM`` or ``mol/L``, the formula one :func:`electrolyte_formula` takes.
_STATED_CONCENTRATION = r"(?P<num>\d+(?:\.\d+)?|\.\d+)\s?(?P<unit>mM|M|mol\s*/\s*L)"
_ELECTROLYTE_STATEMENTS = (re.compile(_STATED_CONCENTRATION + r"\s+(?P<formula>\S+)"),
                           re.compile(r"(?P<formula>\S+)\s+" + _STATED_CONCENTRATION))
#: the element symbols an electrolyte formula is written in (the periodic table, 1-118)
ELEMENT_SYMBOLS = frozenset("""
    H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb
    Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au
    Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts
    Og""".split())
#: formulas of element symbols that are no electrolyte: a gas or atmosphere (no write route), or an acronym a
#: comment line writes (``PBS``, ``CV``, ``OCP``)
_NOT_AN_ELECTROLYTE = frozenset({"Ar", "He", "Ne", "Kr", "Xe", "N2", "O2", "H2", "Cl2", "CO2", "CO", "NH3", "CH4",
                                 "PBS", "CV", "CP", "OCP", "OCV", "CHES", "SYN", "CNT", "BN", "NP", "NPs"})
_FORMULA_PART = re.compile(r"([A-Z][a-z]?)\d*|\(|\)\d*")


def electrolyte_formula(text: str) -> bool:
    """Whether ``text`` is written as an electrolyte formula (r1d): real element symbols (:data:`ELEMENT_SYMBOLS`),
    digits and balanced brackets only, starting with a symbol, naming two elements or more (a bare element, ``Cu``
    or ``N2``, is none; ``HCl`` is two), and not a gas or an acronym (:data:`_NOT_AN_ELECTROLYTE`)."""
    if not text or not text[0].isupper() or text in _NOT_AN_ELECTROLYTE:
        return False
    at, depth, elements = 0, 0, set()
    while at < len(text):
        m = _FORMULA_PART.match(text, at)
        if m is None:
            return False
        if m.group(1) is not None:
            if m.group(1) not in ELEMENT_SYMBOLS:
                return False
            elements.add(m.group(1))
        else:
            depth += 1 if m.group(0) == "(" else -1
            if depth < 0:
                return False
        at = m.end()
    return depth == 0 and len(elements) >= 2


def electrolyte_statement(value: Any) -> dict | None:
    """``{"name", "number", "unit", "concentration_M"}`` of a text that is, as a whole, ONE electrolyte statement in
    the plain grammar (r1d; ``"0.5 M H2SO4"``, ``"KOH 100 mM"``, ``"0.1 mol/L KOH"``), else ``None`` — ``1e-3 M
    KCl``, ``0,1 M KOH``, ``KOH 1 M Ar``, ``0.1 M phosphate buffer`` and every sentence around a statement give
    nothing. ``number`` and ``unit`` are as written; ``concentration_M`` is in mol/L."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    for pattern in _ELECTROLYTE_STATEMENTS:
        m = pattern.fullmatch(text)
        if m is not None and electrolyte_formula(m.group("formula")):
            number = Decimal(m.group("num"))
            return {"name": m.group("formula"), "number": m.group("num"), "unit": m.group("unit"),
                    "concentration_M": float(number / 1000 if m.group("unit") == "mM" else number)}
    return None


def electrolyte_name_problem(value: Any) -> str | None:
    """Why an Electrolyte (name) cell holding a concentration is refused, or ``None``. The split is the
    scientist's: the number is named back to them, never moved into the concentration column (r1d: only a number
    :func:`electrolyte_statement` reads is named; any other is not repeated)."""
    if not isinstance(value, str) or not _CONCENTRATION_IN_NAME.search(value):
        return None
    got = electrolyte_statement(value)
    if got is None:
        return (f"name only: {value!r} also states a concentration; put it in 'Electrolyte Concentration (M)' in "
                "mol/L, and only the name here")
    if got["unit"] == "mM":
        return (f"name only: {value!r} also states a concentration ({got['number']} mM); put it in "
                "'Electrolyte Concentration (M)' in mol/L, and only the name here")
    return f"name only: put {got['number']} in 'Electrolyte Concentration (M)', and only the name here"


def electrolyte_statement_parts(value: Any) -> tuple[str, float] | None:
    """``(name, concentration in mol/L)`` of an electrolyte STATEMENT (``"0.5 M H2SO4"`` -> ``("H2SO4", 0.5)``;
    ``"KOH 100 mM"`` -> ``("KOH", 0.1)``), else ``None``: :func:`electrolyte_statement`, the grammar the scan-header
    comment rule reads too. The template asks the two apart (name only; the concentration in its own column), so a
    cell that is one part of a reading agrees with it; a statement with two concentrations, or not written plainly,
    is not split."""
    got = electrolyte_statement(value)
    return None if got is None else (got["name"], got["concentration_M"])


# --- file-name tokens: a READING to compare against, never a value ---------------------------------
#
# ``m800mV`` is -0.8 V in these beamtimes' naming, but the parser reads no value from it, so a typed
# 0.8 used to clash with nothing. These readings exist ONLY so ``template adopt`` and the import
# preview can say that a typed value contradicts the run's own file name. They are never offered,
# stored or recorded as a value.
_POTENTIAL_TOKEN = re.compile(r"(m?)(\d+)(?:p(\d+))?(mV|V)")
_PH_TOKEN = re.compile(r"pH(\d+)(?:p(\d+))?")
NAME_TOKEN_PATHS = (POTENTIAL_PATH, PH_PATH)


def _token_number(whole: str, frac: str | None) -> Decimal:
    return Decimal(f"{whole}.{frac}") if frac else Decimal(whole)


def name_token_readings(names: Sequence[str], path: str) -> list[dict]:
    """``[{value, token, name}]``: what the whole ``_``-separated tokens of ``names`` (a run's file
    and folder names) read as for ``path`` (potential: ``m?\d+(p\d+)?mV|V``, ``m`` = minus; pH:
    ``pH\d+``). One entry per distinct value; nothing for any other path."""
    if path not in NAME_TOKEN_PATHS:
        return []
    out: dict[str, dict] = {}
    for name in names:
        for token in re.split(r"[_\s]+", name or ""):
            if path == POTENTIAL_PATH and (m := _POTENTIAL_TOKEN.fullmatch(token)):
                volts = _token_number(m.group(2), m.group(3)) / (1000 if m.group(4) == "mV" else 1)
                value = float(-volts if m.group(1) else volts)
            elif path == PH_PATH and (m := _PH_TOKEN.fullmatch(token)):
                value = float(_token_number(m.group(1), m.group(2)))
            else:
                continue
            value = int(value) if path == PH_PATH and value.is_integer() else value
            out.setdefault(repr(float(value)), {"value": value, "token": token, "name": name})
    return list(out.values())


def run_names(bundle: Mapping, run: Mapping) -> list[str]:
    """The names a run's file is known by: its stem, and each part of its file's path (extension dropped)."""
    sources = {s["source_id"]: s for s in bundle["sources"]}
    rel = (sources.get(run.get("acquisition_source_id")) or {}).get("relative_path") or ""
    parts = [p for p in rel.split("/") if p]
    if parts:
        parts[-1] = parts[-1].rsplit(".", 1)[0] if "." in parts[-1] else parts[-1]
    return list(dict.fromkeys([str(run.get("stem") or ""), *parts]))


def header_potential_readings(bundle: Mapping, run: Mapping) -> list[dict]:
    """``[{value, literal, scale, relative_path, locator}]``: each potential a run's SCAN HEADER comment lines state
    as a value — a FILE READING to compare a typed set-point against (c16c), never a value itself. One per line.

    c16-r: the SAME lines (``bundle.is_xdc_comment_line``) and the SAME parser (``questions.header_comment_readings``)
    as the comment rule's candidates, so the two never disagree: a line that gives the rule no value (a range, OCP,
    a comma decimal, two potentials) gives no reading here either. ``literal`` is the whole line."""
    from .questions import header_comment_readings

    out, seen = [], set()
    for e in bundle.get("extended_context") or ():
        if (e.get("run_id") != run.get("run_id") or not B.is_xdc_comment_line(e.get("concept"), e.get("locator"))
                or not isinstance(e.get("raw_literal"), str)):
            continue
        for reading in header_comment_readings(e["raw_literal"]):
            key = (reading["literal"], e.get("relative_path"), e.get("locator"))
            if reading["path"] != POTENTIAL_PATH or reading["value"] is None or key in seen:
                continue
            seen.add(key)
            out.append({"value": reading["value"], "literal": reading["literal"], "scale": reading.get("scale"),
                        "relative_path": e.get("relative_path"), "locator": e.get("locator")})
    return out


def header_potential_mentions(bundle: Mapping, run: Mapping) -> list[dict]:
    """``[{line, relative_path, locator, mentions}]``: each scan-header comment line of a run that MENTIONS a potential
    the rule reads no value from (``Sample A in 1M KOH 0Vrhe``), with every potential it mentions
    (``questions.header_potential_mentions``: ``[{literal, scale, volts}]``). r3a H2: to COMPARE a file name's or a
    typed set-point against, never a value: the whitelist (:func:`header_potential_readings`) alone offers values.
    One per line and place."""
    from .questions import header_comment_readings, header_potential_mentions as mentioned

    out, seen = [], set()
    for e in bundle.get("extended_context") or ():
        if (e.get("run_id") != run.get("run_id") or not B.is_xdc_comment_line(e.get("concept"), e.get("locator"))
                or not isinstance(e.get("raw_literal"), str)):
            continue
        key = (e["raw_literal"], e.get("relative_path"), e.get("locator"))
        if key in seen or not any(r["path"] == POTENTIAL_PATH and r["value"] is None
                                  for r in header_comment_readings(e["raw_literal"])):
            continue
        seen.add(key)
        if got := mentioned(e["raw_literal"]):
            out.append({"line": e["raw_literal"].strip(), "relative_path": e.get("relative_path"),
                        "locator": e.get("locator"), "mentions": got})
    return out


# --- facility hints: a HINT to compare against, never a value ---------------------------------------
#
# The folder's name (``SSRL_BL152_2019-05_…``) and, when its scan headers match, the acquisition system's name are
# what ``ISAAC Suggestions`` shows beside the facility cells: hints, never answers. A Campaign Info beamline (or a
# facility acronym) that names ANOTHER beamline than such a hint is not adopted (``template adopt``) and is named in
# the import preview: ``62b`` beside ``BL152`` is a different beamline in any spelling, ``BL15-2`` / ``BL152`` /
# ``15-2`` / ``SSRL BL15–2`` are one, ``BL11-2`` and ``BL1-12`` two (:func:`same_beamline`). The organization that runs a facility is in no hint, so it is not compared.
BEAMLINE_PATH = "system.facility.beamline"
FACILITY_NAME_PATH = "system.facility.facility_name"
HINTED_PATHS = (BEAMLINE_PATH, FACILITY_NAME_PATH)
_BEAMLINE_TOKEN = re.compile(r"(?i)BL[-.]?\d+(?:[-.]\d+)?[a-z]?")
_FACILITY_TOKEN = re.compile(r"[A-Z][A-Za-z]{1,9}(?:-[A-Z0-9]{1,4})?")


_HINT_WHERE = {"folder_name": "the imported folder's name",
               "acquisition_system": "the acquisition system the scan headers' column names match"}


#: Every Unicode dash a scientist's sheet may hold (en and em dash, minus sign, hyphen variants): read as ``-``.
_DASHES = re.compile("[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d]")
#: The FIRST beamline-shaped token of a value (``BL15-2``, ``bl 15.2``, ``15-2``, ``62b``), a facility word around it
#: (``SSRL BL15-2``, ``BL15-2 (SSRL)``) ignored: its number, the number after a separator, and a trailing letter.
_BEAMLINE_SHAPE = re.compile(r"(?<![a-z0-9])(?:beamline|bl)?[\s_]*(\d+)(?:\s*[-.]\s*(\d+))?([a-z]?)(?![a-z0-9])")


def _beamline_parts(value: Any) -> tuple[str, int | None] | None:
    """``(digits and letter, separator position or None)`` of the first beamline-shaped token of ``value``
    (``SSRL BL15-2`` -> ``("152", 2)``, ``BL152`` -> ``("152", None)``, ``62b`` -> ``("62b", None)``), or ``None``
    when it holds none."""
    if not isinstance(value, str):
        return None
    m = _BEAMLINE_SHAPE.search(_DASHES.sub("-", value).casefold())
    if m is None:
        return None
    first, second, letter = m.group(1), m.group(2) or "", m.group(3) or ""
    return first + second + letter, (len(first) if second else None)


def beamline_form(value: Any) -> str | None:
    """A beamline as it is compared: the first beamline-shaped token, case-folded, a leading ``BL`` / ``beamline``
    and a facility word around it dropped, its separator kept as ``-`` (``BL15-2``, ``SSRL BL15–2``, ``bl 15.2`` and
    ``15-2`` are ``15-2``; ``BL152`` is ``152``; ``62b`` is ``62b``). A value with no such token: the whole value,
    separators dropped (it is then compared as written)."""
    parts = _beamline_parts(value)
    if parts is None:
        if not isinstance(value, str):
            return None
        return re.sub(r"[\s\-_.]", "", _DASHES.sub("-", value.strip().casefold())) or None
    digits, sep = parts
    return digits if sep is None else f"{digits[:sep]}-{digits[sep:]}"


def same_beamline(a: Any, b: Any) -> bool:
    """One beamline: the same digits and letter, split at the same place — or one of them written with no
    separator, which says nothing about where it splits (``BL152`` is ``BL15-2``; ``BL11-2`` is never ``BL1-12``,
    nor ``15-2`` ``1-52``)."""
    pa, pb = _beamline_parts(a), _beamline_parts(b)
    if pa is None or pb is None:
        fa, fb = beamline_form(a), beamline_form(b)
        return fa is not None and fa == fb
    return pa[0] == pb[0] and (pa[1] is None or pb[1] is None or pa[1] == pb[1])


def facility_hint_readings(bundle: Mapping, path: str) -> list[dict]:
    """``[{value, form, source}]``: the beamline (``BL\\d…``) or facility acronym (the word right before such a
    beamline: ``SSRL`` in ``SSRL_BL152``) each facility hint names, with the hint and where it comes from. Nothing
    for any other path, or for a hint that names neither."""
    if path not in HINTED_PATHS:
        return []
    from . import suggestions as S

    out: dict[tuple, dict] = {}
    for h in S.facility_hints(bundle):
        literal = str(h.get("literal") or "")
        tokens = [t for t in re.split(r"[_\s/,;()]+", _DASHES.sub("-", literal)) if t]
        for i, tok in enumerate(tokens):
            if not _BEAMLINE_TOKEN.fullmatch(tok):
                continue
            value = tok if path == BEAMLINE_PATH else (tokens[i - 1] if i and _FACILITY_TOKEN.fullmatch(tokens[i - 1]) else None)
            if value is None:
                continue
            form = beamline_form(value) if path == BEAMLINE_PATH else value.casefold()
            where = _HINT_WHERE.get(str(h.get("kind")), str(h.get("kind")))
            out.setdefault((form, literal), {"value": value, "form": form, "kind": "hint",
                                             "source": f"{where} {literal!r}"})
    return list(out.values())


def facility_hint_lines(bundle: Mapping, path: str, value: Any) -> list[str]:
    """One line per facility hint that names a DIFFERENT beamline (or facility acronym) than ``value``; empty when
    every hint agrees, none names one, or ``value`` is not comparable (a facility name of several words is never
    compared: a folder names an acronym, not a facility's full name)."""
    readings = facility_hint_readings(bundle, path)
    if not readings or not isinstance(value, str):
        return []
    if path == BEAMLINE_PATH:
        mine = beamline_form(value)
    else:
        mine = value.strip().casefold() if _FACILITY_TOKEN.fullmatch(value.strip()) else None
    if not mine:
        return []
    what = "beamline" if path == BEAMLINE_PATH else "facility"
    return [f"differs from a hint: {r['source']} names {what} {r['value']!r}"
            + (f" (compared as {r['form']!r}, yours {mine!r})" if path == BEAMLINE_PATH else "")
            + "; a hint, never an answer" for r in readings
            if (not same_beamline(r["value"], value) if path == BEAMLINE_PATH else r["form"] != mine)]


def _agrees(a: Any, b: Any) -> bool:
    """The same value: numbers by number (within rounding), text after trimming. A number never
    equals text."""
    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    if num(a) and num(b):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return False


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


def export_template(bundle_dir: Path, out: Path, *, suggestions: bool = True, force: bool = False,
                    _fill=None, _command: str = "bundle template export", _keep_off_list: Mapping | None = None) -> dict:
    """Write the template for ``bundle_dir`` to ``out``. Answer cells are left EMPTY.

    ``_fill`` (``template adopt`` only): called with the built workbook before anything is written;
    it may fill answer cells and add sheets, and returns a dict whose ``_exposed`` targets are recorded
    with the suggestions' before the file exists."""
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
    # r3a L6: the block's own column label — row 1's File List headers do not name these cells (column B is "Config
    # ID" there, and a facility hint read as one)
    wsg.cell(row=block, column=2, value=SUGGEST_CAMPAIGN_HEADER).font = bold
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

    filled = _fill(wb=wb, bundle=bundle, rows=rows, index=index, rules=rules, marker=wm) if _fill else None
    exposed = list(suggester.exposed) if suggester is not None else []
    for target in (filled or {}).pop("_exposed", ()):
        if target not in exposed:
            exposed.append(target)
    # THE SUGGESTIONS PRINT PARSER VALUES: that is an exposure, recorded before the file exists.
    if exposed:
        try:
            M.expose_and_load(Path(bundle_dir), exposed, _command)
        except M.MutationRefused as exc:
            raise TemplateRefused(f"Nothing written: {exc}", code=exc.code) from exc
    off_list = list((filled or {}).pop("_off_list", ()))
    if filled is not None and _keep_off_list is not None:
        filled["vocabulary_requests"] = []
        if off_list and not str(_keep_off_list.get("by") or "").strip():
            # NO NAME, NO REQUEST: a word is kept as someone's request only when they are named (`--by`, passed once
            # the scientist says the sheet is theirs); without one nothing is kept, and the summary says so
            # c14 MED-1: a word the scientist has since replaced with an allowed value (a request kept earlier, by
            # anyone, answered since) is said as such, whether or not a name is given, and listed apart
            words = [{k: r[k] for k in ("field_path", "term", "header", "cells", "run_ids")}
                     for r in off_list_requests(off_list)]
            say_answered_since(bundle, [(w, same_word_requests(bundle, w)) for w in words])
            filled["vocabulary_requests_not_kept"] = {
                "reason": "no name given",
                "words": [w for w in words if not (w.get("answered_since") or {}).get("every_run")],
                "answered_since": [w for w in words if (w.get("answered_since") or {}).get("every_run")],
            }
        elif off_list:
            # THEIR OFF-LIST WORDS ARE KEPT (template adopt), recorded before the file exists, as exposures are
            keep = dict(_keep_off_list)

            def change(b):
                kept = keep_off_list_cells(b, off_list, by=keep.get("by"), orcid=keep.get("orcid"), file=keep["file"],
                                           kind="adopted_sheet_cell", command=_command)
                return kept

            try:
                with M.locked(Path(bundle_dir)):
                    held = M.load(Path(bundle_dir))
                    kept = change(held)
                    if any(k["new"] for k in kept):
                        M.save_bundle(Path(bundle_dir), held)
            except M.MutationRefused as exc:
                raise TemplateRefused(f"Nothing written: {exc}", code=exc.code) from exc
            filled["vocabulary_requests"] = kept
    _write_atomic(out, wb)
    return {
        **({"adopted": filled} if filled is not None else {}),
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
    #: ``template adopt`` only: the Disagreements rows (``[disagreements]``) and where each adopted cell came from (``[adopted]``)
    extra: dict[str, list[dict]] = {"[disagreements]": [], "[adopted]": []}
    section = None
    header: list[str] = []
    for values in ws.iter_rows(values_only=True):
        first = values[0] if values else None
        if first in ("[meta]", "[rows]", "[columns]", *extra):
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
        elif section in extra:
            if not header:
                header = [str(v) for v in values if v is not None]
                continue
            extra[section].append(dict(zip(header, values)))
    return {"meta": meta, "rows": rows, "columns": columns, "disagreements": extra["[disagreements]"],
            "adopted": {str(e.get("cell")): e for e in extra["[adopted]"] if e.get("cell")}}


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
    meta = marker.get("meta") or {}
    out: dict[str, Any] = {"cells": [], "invalid": [], "unmapped": {}, "nowhere": [], "rows_refused": [], "awaiting_ruling": [],
                           "already_recorded": [], "off_list": [], "adopted_from": (marker.get("meta") or {}).get("adopted_from"),
                           "exported_utc": (marker.get("meta") or {}).get("exported_utc"),
                           # c14l MED-2: how many decisions the log held when `template adopt` wrote it
                           "decisions_at_adopt": (marker.get("meta") or {}).get("decisions_at_adopt"),
                           # c14m MED-2: a hash of the decisions it held then (:func:`decisions_fingerprint`); c14n LOW-5:
                           # a row kept with its value blanked is damaged ("" never matches), not a workbook without one
                           "decisions_fingerprint": "" if "decisions_fingerprint" in meta and meta["decisions_fingerprint"] is None
                           else meta.get("decisions_fingerprint"),
                           # c14m MED-3: this adoption's own id, which each of its rulings' notes carries
                           "adopt_id": _adopt_id((marker.get("meta") or {}).get("adopt_id"))}
    adopted = marker.get("adopted") or {}
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

    def take(sheet, ref, col: Column, raw: Any, *, run: Mapping | None, scope: str, via: str | None = None,
             because: str | None = None, ruling: tuple[str, str, Any] | None = None,
             against: Sequence[str] | None = None, adopt_id: str | None = None, shown: bool = False):
        rule = rules.get(col.path or "")
        value, why = _parse(raw, rule)
        if not why and col.path == ELECTROLYTE_NAME_PATH:
            why = electrolyte_name_problem(value)
        if why:
            if not any(i["cell"] == _cell_ref(sheet, ref) for i in out["invalid"]):  # a Technique cell many rows reach
                out["invalid"].append({"cell": _cell_ref(sheet, ref), "header": col.header, "value": raw, "reason": why})
            word = raw.strip() if isinstance(raw, str) else None
            if col.path and B.off_list_only(col.path, word):
                # ONLY off the field's list: a word the vocabulary lacks, kept as a vocabulary request (1.10.0)
                out["off_list"].append({"cell": _cell_ref(sheet, ref), "header": col.header, "path": col.path, "value": word,
                                        "run_id": run["run_id"] if run else None, "scope": scope})
            return
        if value is None:
            return
        status, reason = index.status(col)
        if status != "mapped":
            unmapped(sheet, col, ref, value)
            return
        note = cite(sheet, ref) + (f" (via {via})" if via else "") + (f" ({because})" if because else "")
        if because and adopt_id:
            note += _adopt_note(adopt_id)  # c14m MED-3: after the provenance, which :func:`_ruled_here` still reads
        origin = adopted.get(_cell_ref(sheet, ref)) if not because else None
        if origin:
            note += f" (adopted from {origin.get('their_file')} {origin.get('their_cell')})"
            if out["adopt_id"]:
                note += _adopt_note(out["adopt_id"])  # c14n MED-2: an adopted cell's answer names its adoption too
        out["cells"].append({"cell": _cell_ref(sheet, ref) + (f" via {via}" if via else ""), "sheet": sheet,
                             "header": col.header, "path": col.path, "value": value, "scope": scope,
                             "run_id": run["run_id"] if run else None, "note": note,
                             # c14i MED-1: a Disagreements ruling's (their file, their cells, their value)
                             **({"ruling": ruling} if ruling else {}),
                             # c14j MED-1: the decisions its row was ruled against (absent: adopted before they were kept)
                             **({"ruled_against": list(against)} if ruling and against is not None else {}),
                             # c15b H2: its row named the value recorded for this field when it was adopted
                             **({"shown": True} if ruling and shown else {}),
                             # ``template adopt`` copied it from their sheet (no file reading contradicted it then)
                             **({"adopted": {"their_file": origin.get("their_file"), "their_cell": origin.get("their_cell")}}
                                if origin else {}),
                             # c14n MED-2: the decisions its targets held at adopt (absent: adopted before they were kept)
                             **({"ruled_against": got} if origin and (got := _marker_governing(origin, ADOPTED_GOVERNING))
                                is not None else {})})

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
    answers_box: list[Any] = []  # the allowed answers, then their _Chains

    def recorded(e: Mapping, run_ids: Sequence[str], their_value: Any) -> dict:
        """:func:`ruling_state` of one ``_isaac`` disagreement row, against the bundle as it is before this import."""
        from . import propose_terms as P

        if not answers_box:  # read once, only when a ruling cell needs it
            paths = [str(x.get("target_field_path")) for x in marker.get("disagreements") or ()] + [ELECTROLYTE_CONC_PATH]
            answers_box.extend([P.allowed_answers(bundle, paths), _Chains(bundle)])
        path = e.get("target_field_path")
        return ruling_state(answers_box[0], answers_box[1].log, kind=e.get("kind"),
                            path=path, run_ids=run_ids, scope=str(e.get("scope")),
                            their_value=their_value, their_file=e.get("their_file"), their_cells=e.get("their_cells"),
                            beamtime=beamtime_reach(index, path, out["file_list_run_ids"]), chain_of=answers_box[1])

    _read_rulings(wb, marker, runs, known, take, out, recorded)
    return out


def _ruled_here(log: Sequence[Mapping], place: int, provenance: tuple[str, str, Any] | None) -> bool:
    """Whether decision ``log[place]`` is a ruling on THIS disagreement in an earlier import of this sheet: its note,
    which ``template import`` writes from the ruling cell (:func:`_read_rulings`), names "ruling on disagreement Dn: <their
    file> <their cells> = <their value>" for the same file and cells (the Dn number may change between adopts; the cells
    do not) and the value their sheet held there THEN agrees with the one it holds now (``provenance`` = (their file,
    their cells, their value); c14h MED-1: a cell the scientist edited since is a new disagreement, never settled by the
    old ruling). A note written before the value was kept (no `` = ``) is not a ruling here: the row awaits one.
    c14m MED-3: a note may end with the adoption's id (:func:`_adopt_note`) after that provenance; one without it
    (written before it was kept) reads as before."""
    if provenance is None or not (0 <= place < len(log)):
        return False
    note = (log[place] or {}).get("note") if isinstance(log[place], Mapping) else None
    their = re.escape(f"{provenance[0]} {provenance[1]}")
    found = isinstance(note, str) and re.search(
        rf"\(your (?:concentration )?ruling on disagreement D\d+: {their} = (.+?)\)(?:{_ADOPT_NOTE_RE})?$", note)
    if not found:
        return False
    if found.group(1) == _ruled_on_text(provenance[2]):
        return True  # c14i LOW-1: the same value as written (a yes/no or a date, which `_agrees` never equates)
    try:
        ruled_on = json.loads(found.group(1))
    except (ValueError, RecursionError):  # c14k LOW-1: a deeply nested value is not one either
        return False
    return _agrees(ruled_on, provenance[2])


def _ruled_here_old_form(log: Sequence[Mapping], place: int, provenance: tuple[str, str, Any] | None) -> bool:
    """c15b M7: whether ``log[place]`` is a ruling on THIS disagreement as a build before c14h wrote its note: "ruling on
    disagreement Dn: <their file> <their cells>", naming no value and no adoption. Read ONLY for settling a re-adopted row
    (:func:`recorded_ruling`, which says the cell's value then is not known); tying and superseding still read
    :func:`_ruled_here`, which never takes such a note."""
    if provenance is None or not (0 <= place < len(log)):
        return False
    note = (log[place] or {}).get("note") if isinstance(log[place], Mapping) else None
    their = re.escape(f"{provenance[0]} {provenance[1]}")
    return isinstance(note, str) and re.search(rf"\(your (?:concentration )?ruling on disagreement D\d+: {their}\)$", note) is not None


def _ruled_in_chain(log: Sequence[Mapping], chain: Sequence[int], provenance: tuple[str, str, Any] | None) -> bool:
    """c14k MED-1: whether any decision of ``chain`` (:class:`_Chains`: the unbroken same-value run ending at the
    decision that governs now, as places in ``log``) is a ruling on THIS disagreement as their cell reads now
    (:func:`_ruled_here`). Two sheets of theirs ruled the same value then both stay settled: the later tie extends the
    run, it never replaces the earlier ruling; a different value, a reject or a defer ends the run."""
    return any(_ruled_here(log, p, provenance) for p in chain)


#: c14m MED-3: how a ruling's note names the adoption it was ruled on (:func:`_adopt_note`, :func:`_note_adopt_id`)
_ADOPT_NOTE_RE = r" \(adopt id ([0-9a-f]{32})\)"


def _adopt_id(value: Any) -> str | None:
    """c14m MED-3: the ``_isaac`` ``adopt_id`` (32 hex digits, random per ``template adopt``), or ``None`` for a
    workbook adopted before it was kept, or a damaged value."""
    text = value.strip().lower() if isinstance(value, str) else None
    return text if text and re.fullmatch(r"[0-9a-f]{32}", text) else None


def _adopt_note(adopt_id: str) -> str:
    """c14m MED-3: appended to a ruling's note, after its provenance (:func:`_ruled_here` still reads it)."""
    return f" (adopt id {adopt_id})"


def _note_adopt_id(decision: Any) -> str | None:
    """c14m MED-3: the adoption a decision's ruling was made on (:func:`_adopt_note`), or ``None``."""
    note = decision.get("note") if isinstance(decision, Mapping) else None
    found = isinstance(note, str) and re.search(_ADOPT_NOTE_RE + "$", note)
    return found.group(1) if found else None


def _decider(decision: Any) -> str | None:
    """c14n MED-1: the name a decision was recorded by (``decided_by.name``), or ``None``."""
    who = decision.get("decided_by") if isinstance(decision, Mapping) else None
    name = who.get("name") if isinstance(who, Mapping) else None
    return name if isinstance(name, str) else None


def _on_day(decision: Any) -> str:
    """c15b L3: " (2099-01-01)", the day a decision was recorded, where prose once named its id; "" when unknown."""
    when = decision.get("decided_utc") if isinstance(decision, Mapping) else None
    return f" ({when[:10]})" if isinstance(when, str) and when else ""


def _whose(decision: Any) -> str:
    """c14n MED-1: "Name's" for the person who recorded ``decision``, or "another" when it names nobody."""
    name = _decider(decision)
    return f"{name}'s" if name else "another"


def _by_when(decision: Any) -> str:
    """c15b L3: a decision as prose names it, never by its id: "by Name, 2099-01-01" (who and the day, as known)."""
    name = _decider(decision)
    when = decision.get("decided_utc") if isinstance(decision, Mapping) else None
    day = when[:10] if isinstance(when, str) and when else None
    return ", ".join([f"by {name}" if name else "by someone unnamed", *([day] if day else [])])


def _source_of(decision: Any, adopt_id: str | None, by: str | None) -> str:
    """c15b M3: where the decision recorded now came from, from its note: this workbook (an earlier import of it, or
    another copy imported by someone else: the same ``adopt_id``), another adoption of a sheet (a ruling or an adopted
    cell with another id or none), a template import, or a decide."""
    note = decision.get("note") if isinstance(decision, Mapping) else None
    if adopt_id is not None and _note_adopt_id(decision) == adopt_id:
        return ("an earlier import of this workbook" if by is None or _decider(decision) == by
                else "another copy of this workbook")
    if isinstance(note, str) and ("ruling on disagreement D" in note or " (adopted from " in note):
        return "another adoption"
    if isinstance(note, str) and note.startswith("template "):
        return "a template import"
    return "a decide"


def _recorded_now(prior: Mapping, value: Any, adopt_id: str | None, by: str | None) -> str:
    """c15b M3: "recorded now: 'BL12' by Name (2099-01-01), from a decide": what a clash's target holds, who recorded it
    and where from, in every clash reason (no decision id: the skill never reads ids out; ``--json`` keeps them)."""
    name = _decider(prior)
    when = prior.get("decided_utc")
    day = f" ({when[:10]})" if isinstance(when, str) and when else ""
    what = "rejected" if prior.get("decision") == "reject" else _shown(value)
    return (f"recorded now: {what} by {name or 'someone unnamed'}{day}, from "
            f"{_source_of(prior, adopt_id, by)}")


def _ruled_on_text(value: Any) -> str:
    """Their sheet's value as a ruling's note and the ``_isaac`` sheet keep it (JSON: a number stays a number, text
    stays text; :func:`_ruled_here`, :func:`_marker_their_value`)."""
    return json.dumps(value, ensure_ascii=False, default=str)


def _marker_their_value(entry: Mapping) -> tuple[Any, bool]:
    """``(value, kept)``: their sheet's value for one ``_isaac`` disagreement row, as ``template adopt`` wrote it there
    (c14h MED-1), never the Disagreements sheet's column D, which the scientist can edit. ``kept`` is ``False`` for a
    workbook adopt wrote before the value was kept (or a damaged one)."""
    text = entry.get("their_value")
    if not isinstance(text, str):
        return None, False
    try:
        return json.loads(text), True
    except (ValueError, RecursionError):  # c14k LOW-1: a deeply nested value is damaged, never a crash
        return None, False


#: c14k LOW-2: what :func:`_marker_governing` reads from a damaged ``governing_decisions`` value; never a decision id,
#: and a ruling carrying it is never tied (:func:`_rules_against_now`), unlike ``[]`` (adopted with nothing recorded)
GOVERNING_DAMAGED = "(damaged)"
#: c14m MED-2: what a ruling's ``ruled_against`` holds when its workbook is unplaceable (:func:`_placed`): the bundle's
#: decisions changed since it was adopted, so the ids it was ruled against may name other decisions now
GOVERNING_UNPLACEABLE = "(unplaceable)"


#: c14n MED-2: the ``_isaac`` ``[adopted]`` column holding, per adopted answer cell, the decisions its targets held at
#: adopt (:func:`governing_decisions`, a JSON list): with --supersede it records over another value only when made
#: against the one recorded now (:func:`_rules_against_now`); read by :func:`_marker_governing` like a row's
ADOPTED_GOVERNING = "governing"
#: c15b H2: the ``_isaac`` ``[disagreements]`` column holding, per row, the fields whose recorded values its statement named
#: (a JSON list: "recorded `12`; your sheet says `2`: rule which" or "already recorded: …"). A ruling of a different value on
#: such a field, made against the value recorded now, is recorded without --supersede: the row asked for exactly it. A
#: workbook without the column (adopted before it was kept) still needs --supersede
RECORDED_SHOWN = "recorded_shown"


def _marker_governing(entry: Mapping, key: str = "governing_decisions") -> list[str] | None:
    """c14j MED-1: the decision ids one ``_isaac`` disagreement row was ruled against (:func:`governing_decisions`), or
    ``None`` for a workbook adopt wrote before they were kept (no ``governing_decisions`` column): its ruling ties by
    time instead (:func:`_rules_against_now`). c14k LOW-2: with the column there, a damaged value (empty, a bare
    string, an object, a deeply nested list, c14l LOW-1: a list with any element that is not a string) is
    ``[GOVERNING_DAMAGED]``: such a ruling is never tied, never placed by
    time, and never read as adopted with nothing recorded. ``key``: c14n MED-2, the ``[adopted]`` column
    (:data:`ADOPTED_GOVERNING`)."""
    if key not in entry:
        return None
    text = entry.get(key)
    if not isinstance(text, str):
        return [GOVERNING_DAMAGED]
    try:
        ids = json.loads(text)
    except (ValueError, RecursionError):  # c14k LOW-1
        return [GOVERNING_DAMAGED]
    # c14l LOW-1: a list holding anything but decision ids ([1], [null], [["d-1"]], ["d-1", 5]) is damaged too
    return ids if isinstance(ids, list) and all(isinstance(i, str) for i in ids) else [GOVERNING_DAMAGED]


def _marker_shown(entry: Mapping) -> list[str]:
    """c15b H2: the ``_isaac`` ``recorded_shown`` fields of one disagreement row (:data:`RECORDED_SHOWN`), or ``[]`` for a
    workbook adopted before it was kept or a damaged value: then no ruling of it is recorded over another value without
    ``--supersede``."""
    try:
        paths = json.loads(entry.get(RECORDED_SHOWN)) if isinstance(entry.get(RECORDED_SHOWN), str) else []
    except (ValueError, RecursionError):
        return []
    return [p for p in paths if isinstance(p, str)] if isinstance(paths, list) else []


def beamtime_reach(index: "_Index", path: str | None, runs: set[str]) -> list[str | None]:
    """The targets a Campaign Info answer for ``path`` reaches (:func:`plan_and_record`): a record-scope missing value
    (``None``) and each of ``runs`` (the File List's live runs) with a missing value of its own. Extracted values are
    left alone by such an answer, so they are not among them."""
    if not path:
        return []
    found = {m["run_id"] for m in index.missing_by_path.get(path, []) if m["run_id"] is None or m["run_id"] in runs}
    return ([None] if None in found else []) + sorted(r for r in found if r is not None)


def recorded_ruling(answers: Mapping, path: str | None, run_ids: Sequence[str], scope: str, *, their_value: Any = None,
                    provenance: tuple[str, str, Any] | None = None, log: Sequence[Mapping] = (),
                    beamtime: Sequence[str | None] | None = None, chain_of=None) -> dict | None:
    """What a Disagreements row's field already holds, when a scientist's confirming decision gives it an allowed value
    for every run the row names (``scope`` ``experiment``: the beamtime-wide answer), else ``None``. ``answers``:
    ``propose_terms.allowed_answers`` for the rows' fields (alias-aware; the only values a record takes).

    ``settled`` (c14 MED-1, c14g MED-1): only when, for every run, the value recorded EQUALS the sheet's
    (``their_value``) or was recorded by a ruling on this same disagreement in an earlier import of this sheet
    (:func:`_ruled_here`, ``provenance`` = (their file, their cells, their value)). Then "already recorded: 'in_situ'
    (2099-01-01); leave blank to keep". A decision that only predates the sheet (a file's pH 12 confirmed, then the
    sheet says pH 2 for the first time) settles nothing: "recorded `12` (2099-01-01); your sheet says `2`: rule which", and the row
    awaits the scientist's ruling. ``run_own``: some run the row names holds its own answer (c14h LOW-2: a different
    ruling clashes there, so it is recorded only with ``--supersede``), not only a beamtime-wide one.
    ``beamtime``: for a whole-beamtime row (``scope`` ``experiment``), the targets its answer reaches
    (:func:`beamtime_reach`; a Campaign Info ruling is recorded on each File List run's own target).
    ``chain_of`` (c14k MED-1, :class:`_Chains`): a ruling on this disagreement settles the row when it is ANY decision
    of the unbroken same-value run ending at the decision that governs (two sheets of theirs ruled the same value both
    stay settled); without it, only the governing decision is read."""
    from . import propose_terms as P

    if not path:
        return None
    chain = chain_of if chain_of is not None else (lambda place: [place])
    reach = _ruling_reach(run_ids, scope, beamtime)
    got = []
    per_run = []  # c15b M2: (target, its answers), for the runs each value is held by
    for rid in reach:
        here = P._answers_for_run(answers, path, rid)
        if not here:
            return None
        got += here
        per_run.append((rid, here))
    run_own = scope == "experiment" or None in reach or any(answers.get((P._fills(path), rid)) for rid in reach if rid)
    values = P._distinct([a[0] for a in got])
    timed = sorted((t, a[1]) for a in got if (t := P._utc(a[1])) is not None)
    when = timed[-1][1] if timed else None
    # c15b M7: a ruling an older build recorded on this row (its note names the cells but not the value they held then)
    # settles it too; the strict reading (:func:`_ruled_here`) still decides tying and superseding
    old_form = False
    settled = True
    for a in got:
        if (their_value is not None and _agrees(a[0], their_value)) or _ruled_in_chain(log, chain(a[2]), provenance):
            continue
        if any(_ruled_here_old_form(log, p, provenance) for p in chain(a[2])):
            old_form = True
            continue
        settled = False
    date = f" ({when[:10]})" if when else ""
    older = (", by your ruling on this row from an earlier build (it kept no copy of your cell's value then: if you "
             "changed that cell since, rule it again)") if old_form else ""
    statement = (f"already recorded: {', '.join(_shown(v) for v in values)}{date}{older}; leave blank to keep" if settled else
                 f"recorded {_values_by_runs(values, per_run)}{date}; your sheet says {P._shown([their_value])}: rule which")
    return {"values": values, "decided_utc": when, "runs": sum(1 for r in reach if r is not None), "settled": settled,
            "run_own": run_own, "statement": statement, **({"settled_by_older_ruling": True} if settled and old_form else {})}


def _values_by_runs(values: Sequence[Any], per_run: Sequence[tuple[str | None, Sequence[Any]]]) -> str:
    """c15b M2: the values a row's runs hold, as ``P._shown`` says them; when they differ, each with how many runs hold
    it ("`-0.8` (8 runs), `-0.6` (1 run)"), so a row half changed by a per-run command says which runs hold which.
    ``per_run``: each target the row reaches with its answers (:func:`recorded_ruling`; ``None``: the beamtime)."""
    from . import propose_terms as P

    if len(values) < 2 or not any(rid is not None for rid, _a in per_run):
        return P._shown(values)
    held: dict[str, set[str]] = {}
    for rid, here in per_run:
        if rid is not None:
            for a in here:
                held.setdefault(json.dumps(a[0], sort_keys=True, default=str), set()).add(rid)
    return ", ".join(f"`{v}`" + (f" ({n} run{'' if n == 1 else 's'})" if (n := len(held.get(
        json.dumps(v, sort_keys=True, default=str), ()))) else "") for v in values)


def _ruling_reach(run_ids: Sequence[str], scope: str, beamtime: Sequence[str | None] | None) -> list[str | None]:
    """The targets a Disagreements row's ruling reaches (:func:`recorded_ruling`): each run it names, or for a
    whole-beamtime row (``scope`` ``experiment``) ``beamtime`` (:func:`beamtime_reach`; the beamtime-wide answer)."""
    if scope == "experiment" or not run_ids:
        return list(beamtime) if beamtime else [None]
    return list(dict.fromkeys(run_ids))


def governing_decisions(answers: Mapping, log: Sequence[Mapping], paths: Sequence[str], run_ids: Sequence[str],
                        scope: str, beamtime: Sequence[str | None] | None = None) -> list[str]:
    """c14j MED-1: the ``decision_id`` of every scientist decision :func:`recorded_ruling` reads for a Disagreements row
    (the decision that governs each target its ruling reaches, for each of ``paths``; every target of a whole-beamtime
    row), sorted. ``template adopt`` keeps them in ``_isaac``: a ruling that keeps the recorded value is tied to the
    sheet only when one of them is in the same-value run that governs now (:func:`_rules_against_now`, c14k), never by
    a workbook adopted before that run began."""
    from . import propose_terms as P

    reach = _ruling_reach(run_ids, scope, beamtime)
    ids = {(log[a[2]] or {}).get("decision_id") for path in paths if path for rid in reach
           for a in P._answers_for_run(answers, path, rid) if 0 <= a[2] < len(log) and isinstance(log[a[2]], Mapping)}
    return sorted(i for i in ids if isinstance(i, str))


def _adopt_position(value: Any, log_length: int) -> int | None:
    """c14l MED-2: the ``_isaac`` ``decisions_at_adopt`` value (how many decisions the log held when ``template adopt``
    wrote the workbook), or ``None`` for a workbook adopted before it was kept, or a damaged value (not a whole number,
    or more decisions than the log holds now): such a workbook is read as before (:func:`_rules_against_now`).
    c14m LOW-3: only ASCII digits are a whole number here (``"²".isdigit()`` is true, and ``int("²")`` raises)."""
    if isinstance(value, str):
        text = value.strip()
        value = int(text) if text.isascii() and text.isdecimal() else None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= log_length:
        return None
    return value


def decisions_fingerprint(log: Sequence[Mapping], n: int) -> str:
    """c14m MED-2: a sha256 over the first ``n`` decisions of ``log`` (each one's ``decision_id``, ``decided_utc``,
    ``target``, ``decision`` and ``value``, as canonical JSON; ``n`` 0 hashes the empty prefix). ``template adopt``
    keeps it beside ``decisions_at_adopt``: a copied or restored bundle keeps its ``bundle_id``, and decision ids
    (``d-NNNNN``) repeat after a fork, so only this says the log still begins with the decisions the workbook saw."""
    rows = [[d.get(k) for k in ("decision_id", "decided_utc", "target", "decision", "value")] if isinstance(d, Mapping)
            else None for d in list(log)[:n]]
    text = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _placed(cells: Mapping, log: Sequence[Mapping]) -> tuple[int | None, bool]:
    """c14m MED-2: ``(adopted_at, unplaceable)`` of a workbook against the decision log it is imported into. A workbook
    that keeps a fingerprint (:func:`decisions_fingerprint`) is placed only when the log's first ``decisions_at_adopt``
    decisions hash to it; otherwise (copied or restored, a fork, a damaged value) it is UNPLACEABLE: neither its place
    nor its ``governing_decisions`` ids are trusted, so none of its rulings is tied or recorded over another value. A
    workbook adopted before the fingerprint was kept is placed as before (:func:`_adopt_position`)."""
    adopted_at = _adopt_position(cells.get("decisions_at_adopt"), len(log))
    kept = cells.get("decisions_fingerprint")
    if kept is None:
        return adopted_at, False
    if adopted_at is None or not isinstance(kept, str) or kept.strip().lower() != decisions_fingerprint(log, adopted_at):
        return None, True
    return adopted_at, False


def _since_adopt(place: int | None, decision: Mapping | None, adopted_at: int | None, exported_utc: Any) -> bool:
    """c14l MED-2: whether ``decision`` (``log[place]``) is KNOWN to have been recorded after the workbook was adopted:
    by its place in the decision log (``adopted_at``, :func:`_adopt_position`), or, for a workbook adopted before that
    was kept, only when its time is readable and strictly after the workbook's (``exported_utc``). Never by default."""
    from . import propose_terms as P

    if decision is None:
        return False
    if adopted_at is not None:
        return place is not None and place >= adopted_at
    made, decided = P._utc(exported_utc), P._utc(decision.get("decided_utc"))
    return made is not None and decided is not None and decided > made


def _rules_against_now(cell: Mapping, prior: Mapping, exported_utc: Any, chain: Sequence[Mapping] = (),
                       history: Sequence[Mapping] | None = None, *, adopted_at: int | None = None,
                       places: Mapping[int, int] | None = None, keeps: bool = True, adopt_id: str | None = None,
                       by: str | None = None) -> bool:
    """c14j MED-1: whether a Disagreements ruling (``cell``) was made against the value that governs its target now.
    ``chain`` (c14k MED-1, :class:`_Chains`): the decisions of the unbroken same-value run ending at ``prior``, the
    decision that governs now (``()``: ``prior`` alone). Made against it when the decisions its row read when adopted
    (``ruled_against``, :func:`governing_decisions`) include one of ``chain``, or, for a workbook adopted before they
    were kept, the workbook was adopted (``exported_utc``) at or after one of ``chain`` was decided. ``history``: every
    decision on the target (:meth:`_Chains.history`); a workbook adopted with NOTHING recorded for the target (none of
    ``history`` among ``ruled_against``) is tied when every decision recorded since is of that run (both their sheets
    adopted first, then imported in turn: no extra round), never when a different value, a reject or a defer came
    between. A stale workbook's ruling (adopted before that run of the value began) is never tied: it is listed apart
    (``stale_rulings``).

    c14l MED-2: ``adopted_at`` (:func:`_adopt_position`) places "recorded since" exactly: the decisions of ``history``
    at or after that place in the decision log (``places``: ``id(decision) -> place``), so a reject, a defer or an
    off-list value recorded BEFORE the workbook was adopted never stops a tie. Without it, every decision of
    ``history`` counts, as before. c14l MED-1: ``keeps`` ``False`` is a ruling that gives a DIFFERENT value, read
    before ``--supersede`` records it over ``prior``: made against ``prior`` only when one of ``chain`` was among the
    decisions it was ruled against, or (``adopted_at``) nothing was recorded on the target since the workbook was
    adopted (``prior`` was there to see); never by a run that only began since (it never saw that value).

    c14m MED-2: a ruling of an unplaceable workbook (:func:`_placed`, ``ruled_against`` ``[GOVERNING_UNPLACEABLE]``)
    is never made against it. c14m MED-3: one of ``chain`` recorded from THIS adoption (its note carries ``adopt_id``,
    :func:`_note_adopt_id`) means the scientist ruled the value recorded now on this very workbook: their correction is
    made against it. Another adoption of the same sheet has another id, so two of them never flip the value.

    c14n MED-1: only when that decision was made by ``by`` (this import's ``--by``; ``None``: not checked): copies of
    one workbook share its id, and a colleague's copy never saw the value its other holder recorded. c14n MED-2: an
    adopted File List cell (``ruled_against``: the decisions its targets held at adopt, or ``None`` for a workbook
    adopted before they were kept) is read the same way with ``keeps`` ``False``; without the ids but with
    ``adopted_at``, it is made against the value now only when nothing was recorded on the target since the adopt."""
    from . import propose_terms as P

    run = list(chain) or [prior]
    against = cell.get("ruled_against")
    if against is not None and (GOVERNING_DAMAGED in against or GOVERNING_UNPLACEABLE in against):
        return False  # c14k LOW-2: what it was ruled against cannot be read (c14m MED-2: nor trusted)
    if adopt_id is not None and any(_note_adopt_id(d) == adopt_id and (by is None or _decider(d) == by) for d in run):
        return True
    if against is None and not keeps and adopted_at is not None and places is not None and history is not None:
        return not [d for d in history if (p := places.get(id(d))) is None or p >= adopted_at]  # c14n MED-2
    if against is not None:
        if any(d.get("decision_id") in against for d in run):
            return True
        if history is None:
            return False
        if adopted_at is not None and places is not None:
            since = [d for d in history if (p := places.get(id(d))) is None or p >= adopted_at]
        elif not keeps:
            return False  # nothing places the workbook against the run that governs now
        else:
            since = list(history)
        if not keeps:
            return not since
        seen = [d for d in history if d.get("decision_id") in against]
        return not seen and {id(d) for d in since} <= {id(d) for d in run}
    # A workbook adopted before `governing_decisions` was kept: placed by its export time. This FAILS SAFE: an unreadable
    # time, or one before every decision of the run, never ties (the row is asked again at the next adopt; nothing is
    # recorded twice).
    made = P._utc(exported_utc)
    return made is not None and any((decided := P._utc(d.get("decided_utc"))) is not None and made >= decided for d in run)


class _Chains:
    """c14k MED-1: the decision log read as runs of one target's value. ``chains(place)``: the places in the decision
    log of the unbroken same-value run ENDING at ``log[place]`` (latest first): walking back through the decisions on
    its target while each is a confirming decision giving the same value (:func:`bundle.final_value`, compared by
    :func:`_same_value`); a different value, a reject or a defer ends it. A candidate's decisions are those naming it
    and those naming its conflicts, in decision-log order (what :func:`bundle.candidate_decision` reads); a missing
    value's, those naming it. ``before(place)``: the decision that ended the run (``None``: the run starts the log)."""

    def __init__(self, bundle: Mapping):
        self.log = list(bundle.get("scientist_decisions") or ())
        self._candidate_of = {cf.get("conflict_id"): cf.get("candidate_id") for cf in bundle.get("conflicts") or ()
                              if isinstance(cf, Mapping)}
        self._objs = {("candidate", c.get("candidate_id")): c for c in bundle.get("candidates") or () if isinstance(c, Mapping)}
        self._objs.update({("missing_value", m.get("value_id")): m for m in bundle.get("missing_values") or ()
                           if isinstance(m, Mapping)})
        self._places: dict[tuple, list[int]] = {}
        for i, d in enumerate(self.log):
            key = self._key(d)
            if key is not None:
                self._places.setdefault(key, []).append(i)
        self._cache: dict[int, tuple[list[int], int | None]] = {}

    def _key(self, d: Any) -> tuple | None:
        target = d.get("target") if isinstance(d, Mapping) else None
        if not isinstance(target, Mapping):
            return None
        kind, tid = target.get("kind"), target.get("id")
        if kind == "conflict":
            kind, tid = "candidate", self._candidate_of.get(tid)
        return (kind, tid) if kind in ("candidate", "missing_value") and tid is not None else None

    def _walk(self, place: int) -> tuple[list[int], int | None]:
        if place in self._cache:
            return self._cache[place]
        key = self._key(self.log[place]) if 0 <= place < len(self.log) else None
        if key is None:
            found: tuple[list[int], int | None] = ([place] if 0 <= place < len(self.log) else [], None)
        else:
            obj = self._objs.get(key) or {}
            base = obj.get("value") if key[0] == "candidate" else None

            def value(d: Mapping) -> Any:
                return B.final_value(base, d, obj.get("readings"))

            seq = self._places[key]
            now, run, ended = value(self.log[place]), [place], None
            for p in reversed(seq[:seq.index(place)]):
                d = self.log[p]
                if d.get("decision") not in B.CONFIRMING_DECISIONS or not _same_value(value(d), now):
                    ended = p
                    break
                run.append(p)
            found = (run, ended)
        self._cache[place] = found
        return found

    def __call__(self, place: int) -> list[int]:
        return self._walk(place)[0]

    def history(self, place: int) -> list[Mapping]:
        """Every decision on the target of ``log[place]`` (a candidate's with its conflicts'), in decision-log order."""
        key = self._key(self.log[place]) if 0 <= place < len(self.log) else None
        return [self.log[p] for p in self._places[key]] if key is not None else []

    def before(self, place: int) -> int | None:
        return self._walk(place)[1]


def ruling_state(answers: Mapping, log: Sequence[Mapping], *, kind: str | None, path: str | None, run_ids: Sequence[str],
                 scope: str, their_value: Any, their_file: str | None, their_cells: str | None,
                 beamtime: Sequence[str | None] | None = None, chain_of=None) -> dict:
    """How one Disagreements row stands against what is recorded (:func:`recorded_ruling`): ``already_recorded`` (the
    row is settled; a blank ruling keeps it), else ``recorded_note`` (said beside the row, which still awaits a ruling).
    An Electrolyte row whose value also states a concentration (kind ``name_only``, c14g MED-2) is settled only when the
    name AND the concentration are; with the name alone, ``name_recorded`` holds it and the concentration still awaits a
    ruling ("name recorded: 'KOH'; concentration awaits your ruling"). ``conc``: the concentration's own state.
    ``governing`` (c14j MED-1): :func:`governing_decisions` of the row (for a ``name_only`` row, its name's and its
    concentration's). ``chain_of``: :class:`_Chains` of the bundle (:func:`recorded_ruling`). ``shown`` (c15b H2): the
    fields whose recorded values the row's statement names (``_isaac`` ``recorded_shown``): a ruling of a different value
    on one of them, made against the value recorded now, is recorded without ``--supersede``."""
    paths = [path, ELECTROLYTE_CONC_PATH] if kind == "name_only" else [path]
    governing = governing_decisions(answers, log, [p for p in paths if p], run_ids, scope, beamtime)
    return {**_ruling_state(answers, log, kind=kind, path=path, run_ids=run_ids, scope=scope, their_value=their_value,
                            their_file=their_file, their_cells=their_cells, beamtime=beamtime, chain_of=chain_of),
            "governing": governing}


def _ruling_state(answers: Mapping, log: Sequence[Mapping], *, kind: str | None, path: str | None, run_ids: Sequence[str],
                  scope: str, their_value: Any, their_file: str | None, their_cells: str | None,
                  beamtime: Sequence[str | None] | None, chain_of=None) -> dict:
    """:func:`ruling_state` without ``governing``."""
    provenance = (str(their_file), str(their_cells), their_value) if their_file and their_cells else None
    common = dict(scope=scope, provenance=provenance, log=log, beamtime=beamtime, chain_of=chain_of)
    parts = electrolyte_statement_parts(their_value) if kind == "name_only" else None
    if parts is None:
        rec = recorded_ruling(answers, path, run_ids, their_value=their_value, **common)
        return {"already_recorded": rec if rec and rec["settled"] else None,
                "recorded_note": rec["statement"] if rec and not rec["settled"] else None,
                "shown": [path] if rec else []}
    name = recorded_ruling(answers, path, run_ids, their_value=parts[0], **common)
    conc = recorded_ruling(answers, ELECTROLYTE_CONC_PATH, run_ids, their_value=parts[1], **common)
    if name and name["settled"] and conc and conc["settled"]:
        when = max([w for w in (name["decided_utc"], conc["decided_utc"]) if w], default=None)
        both = {**name, "values": name["values"], "concentration_values": conc["values"], "decided_utc": when,
                "run_own": name["run_own"] or conc["run_own"],  # c14h LOW-2: either part's own answer clashes
                "statement": (f"already recorded: name {', '.join(_shown(v) for v in name['values'])}, concentration "
                              f"{', '.join(_shown(v) for v in conc['values'])} M" + (f" ({when[:10]})" if when else "")
                              + "; leave blank to keep")}
        return {"already_recorded": both, "recorded_note": None, "conc": conc, "shown": [path, ELECTROLYTE_CONC_PATH]}
    if name and name["settled"]:
        said = "awaits your ruling" if conc is None else conc["statement"]
        return {"already_recorded": None, "name_recorded": name, "conc": conc,
                "recorded_note": f"name recorded: {', '.join(_shown(v) for v in name['values'])}; concentration {said}",
                "shown": [path] + ([ELECTROLYTE_CONC_PATH] if conc else [])}
    return {"already_recorded": None, "conc": conc, "recorded_note": name["statement"] if name else None,
            "shown": [path] if name else []}


def _read_rulings(wb, marker: Mapping, runs: Mapping, known: Mapping[str, Column], take, out: dict,
                  recorded=None) -> None:
    """A workbook ``template adopt`` wrote: each Disagreements row's "Your ruling" cell, typed by the
    scientist, is read like an answer cell for exactly the targets ``_isaac`` names for that row. An
    empty ruling records nothing and is listed (``awaiting_ruling``), or, on a row whose field a scientist's decision
    already answers for every run it names (``recorded``: :func:`recorded_ruling`), keeps that value and is listed
    apart (``already_recorded``, c14 MED-1); nothing ISAAC chose is ever read from that sheet."""
    entries = marker.get("disagreements") or ()
    if not entries:
        return
    if SHEET_DISAGREE not in wb.sheetnames:
        raise TemplateRefused(f"The `_isaac` sheet lists disagreements but the workbook has no {SHEET_DISAGREE!r} sheet. "
                              "Run `template adopt` again. Nothing was recorded.", code=EXIT_INPUT_REFUSED)
    ws = wb[SHEET_DISAGREE]
    # a workbook adopt wrote before the concentration ruling column (nine columns) has no column J to read
    conc_column = str(ws[f"{DISAGREE_CONC_COLUMN}1"].value or "").strip() == DISAGREE_HEADERS[9]
    conc_col = next(c for c in FILE_COLUMNS if c.path == ELECTROLYTE_CONC_PATH)
    adopt_id = _adopt_id((marker.get("meta") or {}).get("adopt_id"))  # c14m MED-3: carried by each ruling's note
    for e in entries:
        try:
            row = int(e.get("row"))
        except (TypeError, ValueError):
            raise TemplateRefused(f"The `_isaac` sheet's disagreement mapping is damaged ({e!r}). Run `template adopt` "
                                  "again. Nothing was recorded.", code=EXIT_INPUT_REFUSED) from None
        did = str(e.get("id"))
        ref = f"{DISAGREE_RULING_COLUMN}{row}"
        conc_ref = f"{DISAGREE_CONC_COLUMN}{row}"
        shown = ws[f"A{row}"].value
        if shown != did:
            out["rows_refused"].append({"row": row, "cells": [_cell_ref(SHEET_DISAGREE, ref)],
                                        "reason": f"{_cell_ref(SHEET_DISAGREE, f'A{row}')} should read {did!r} but reads "
                                                  f"{shown!r}: the Disagreements rows were moved, so no ruling on it is read"})
            continue
        col = known.get(str(e.get("header")))
        if col is None or col.path != e.get("target_field_path"):
            raise TemplateRefused(f"The `_isaac` sheet maps disagreement {did} to a column this build does not know "
                                  f"({e.get('header')!r}). Run `template adopt` again. Nothing was recorded.",
                                  code=EXIT_INPUT_REFUSED)
        # c14h MED-1: their sheet's value as adopt kept it in `_isaac` (column D is the scientist's to edit); a workbook
        # adopt wrote before it was kept shows column D, but nothing it says settles a row
        their_value, kept = _marker_their_value(e)
        if not kept:
            their_value = ws[f"D{row}"].value
        # the note names the value the ruling was made on, so an edited cell of theirs is never settled by it; never
        # column D's (c14i LOW-2: a workbook adopted before the value was kept names no value, and settles nothing)
        tie = (str(e.get("their_file")), str(e.get("their_cells")), their_value) if e.get("their_cells") and kept else None
        against = _marker_governing(e)
        shown_paths = _marker_shown(e)  # c15b H2
        said_on = f" = {_ruled_on_text(their_value)}" if kept else ""
        provenance = f": {e.get('their_file')} {e.get('their_cells')}{said_on}" if e.get("their_cells") else ""
        because = f"your ruling on disagreement {did}{provenance}"
        runs_named = [] if e.get("scope") == "experiment" else [t for t in str(e.get("targets") or "").split(";") if t]

        def record(cell_ref: str, column: Column, raw: Any, why_said: str):
            out["read"] = out.get("read", 0) + 1
            if e.get("scope") == "experiment":
                take(SHEET_DISAGREE, cell_ref, column, raw, run=None, scope="experiment", because=why_said, ruling=tie,
                     against=against, adopt_id=adopt_id, shown=column.path in shown_paths)
                return
            for run_id in runs_named:
                run = runs.get(run_id)
                if run is None:
                    out["nowhere"].append({"cell": _cell_ref(SHEET_DISAGREE, cell_ref), "header": column.header, "value": raw,
                                           "reason": f"the run {run_id!r} is not in this bundle"})
                    continue
                take(SHEET_DISAGREE, cell_ref, column, raw, run=run, scope="run", because=why_said, ruling=tie,
                     against=against, adopt_id=adopt_id, shown=column.path in shown_paths)

        # M3: the CONCENTRATION of an electrolyte row ("0.01 M HClO4"), ruled in its own column, for the same runs
        craw = None
        if conc_column:
            craw, cwhy = _raw(ws[conc_ref])
            if cwhy:
                out["invalid"].append({"cell": _cell_ref(SHEET_DISAGREE, conc_ref), "header": conc_col.header,
                                       "value": ws[conc_ref].value, "reason": cwhy})
            elif craw is not None and e.get("kind") != "name_only":
                out["nowhere"].append({"cell": _cell_ref(SHEET_DISAGREE, conc_ref), "header": DISAGREE_HEADERS[9], "value": craw,
                                       "reason": f"only an Electrolyte row that also states a concentration takes a "
                                                 f"concentration ruling; {did} is about {col.header}"})
            elif craw is not None:
                record(conc_ref, conc_col, craw, f"your concentration ruling on disagreement {did}{provenance}")
        raw, why = _raw(ws[ref])
        if why:
            out["invalid"].append({"cell": _cell_ref(SHEET_DISAGREE, ref), "header": col.header, "value": ws[ref].value, "reason": why})
            continue
        state = recorded(e, runs_named, their_value) if recorded is not None and (
            raw is None or (e.get("kind") == "name_only" and conc_column and craw is None)) else {}
        if not kept:
            state = {k: v for k, v in state.items() if k not in ("already_recorded", "name_recorded")}

        def conc_awaits(why_said: str) -> None:
            # c14g MED-2: the concentration their sheet states is never dropped from every list
            out["awaiting_ruling"].append({"id": did, "cell": _cell_ref(SHEET_DISAGREE, conc_ref), "header": conc_col.header,
                                           "target_field_path": ELECTROLYTE_CONC_PATH, "their_value": their_value,
                                           "why": why_said})

        if raw is None:
            reading = ws[f"F{row}"].value
            settled = state.get("already_recorded") or state.get("name_recorded")
            if settled is not None:
                # a blank ruling on a row already settled keeps what is recorded: never read back as awaiting a ruling
                out["already_recorded"].append({"id": did, "cell": _cell_ref(SHEET_DISAGREE, ref), "header": col.header,
                                                "target_field_path": col.path, "their_value": their_value,
                                                "recorded": settled})
                if state.get("name_recorded") and craw is None:
                    conc_awaits(state["recorded_note"])
                continue
            said = ("readings: " + "; ".join(str(reading).splitlines())) if reading else ws[f"B{row}"].value
            out["awaiting_ruling"].append({"id": did, "cell": _cell_ref(SHEET_DISAGREE, ref), "header": col.header,
                                           "target_field_path": col.path, "their_value": their_value,
                                           "why": f"{state['recorded_note']}; {said}" if state.get("recorded_note") else said})
            continue
        if state and not ((state.get("conc") or {}).get("settled")):
            conc_awaits("the name is ruled here; the concentration your sheet states awaits your ruling in column "
                        f"{DISAGREE_CONC_COLUMN}")
        record(ref, col, raw, because)


def _same_value(a: Any, b: Any) -> bool:
    """Equal as values: numbers by number (``0.1 == 0.1``, ``1 == 1.0``), everything else by type
    and value. ``True`` is not ``1``; ``"0.1"`` is not ``0.1``."""
    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    if num(a) and num(b):
        return a == b
    return type(a) is type(b) and a == b


#: c14m MED-2: why a ruling of an unplaceable workbook (:func:`_placed`) is neither tied nor recorded over a value
UNPLACEABLE_REASON = "this bundle's decisions changed since the workbook was adopted (copied or restored?); adopt again"


def decide_command(target: str | Sequence[str] | None, decision: str, value: Any,
                   slot: tuple[str, str] | None = None) -> str:
    """c14m LOW-2: the ``isaac bundle decide`` command that records ``value`` on ``target`` now, outside the workbook
    (text as typed; any other value as JSON with ``--json``). ``confirm`` (a candidate whose extracted value it is)
    takes no value. c14n LOW-1: ``--value=<v>``, so a value that starts with "-" (``-0.5``, ``-x``) is never read as
    an option. c14n LOW-2: ``slot`` (question id, run id): ``target`` is a per-run answer slot this import added, which
    is dropped unless recorded, so the command answers that question for the run instead (``--only run:<id>``)."""
    shown = ("" if decision == "confirm" else f" --value={shlex.quote(value)}" if isinstance(value, str)
             else f" --value={shlex.quote(_ruled_on_text(value))} --json")
    if slot:
        where = f"--question {slot[0]} --only run:{slot[1]}"
    elif isinstance(target, (list, tuple)):  # c15b M2: one command for every target of a cell (--target per target)
        where = " ".join(f"--target {t}" for t in target) or "--target <target id>"
    else:
        where = f"--target {target or '<target id>'}"
    return f'isaac bundle decide <bundle_dir> {where} --decision {decision}{shown} --by "<your name>"'


def _or_decide(target: str | None, decision: str, value: Any, slot: tuple[str, str] | None = None) -> str:
    """c14m LOW-2: the end of every stale and clash reason: the immediate alternative, with the target filled in."""
    return f", or record this value directly: {decide_command(target, decision, value, slot)}"


def _already_there(value: Any, ruling: bool = True) -> str:
    """c14n LOW-3: how a stale reason ends when its ruling keeps the value recorded now: no command to record it.
    c15a LOW-3: only a Disagreements ruling has a row to settle by adopting again; an adopted cell has none, so the
    advice is dropped for it."""
    return f"the value is already {_shown(value)}" + (_ALREADY_TAIL if ruling else "")


#: c14n LOW-3: how a ruling's line ends when its target already holds the value (c15b M4 replaces it when another
#: target of the row still holds a different value)
_ALREADY_TAIL = "; adopt again to settle this row"


def _clash_count(clashes: Sequence[Mapping]) -> str:
    """c14p LOW-2: the summary's clashes, the targets held back with one (all or nothing, ``blocked_by``) apart.
    c15b M1: counted by cell, the targets in brackets: "2 cell(s) clash (286 target(s): 3 clash, 282 held back with them:
    all or nothing; 1 already hold the value)"."""
    if not clashes:
        return "0 clash(es)"
    # c15a LOW-3: a target that already holds the value (``holds_value``) is neither a clash nor held back
    holds = sum(1 for c in clashes if c.get("holds_value"))
    held = sum(1 for c in clashes if c.get("blocked_by") and not c.get("holds_value"))
    cells = len({c["cell"] for c in clashes})
    own = len(clashes) - held - holds
    parts = [f"{own} clash{'' if own == 1 else 'es'}"] + ([f"{held} held back with them: all or nothing"] if held else []) + (
        [f"{holds} already hold the value"] if holds else [])
    return f"{cells} cell(s) clash ({len(clashes)} target(s): {'; '.join(parts)})"


def _again(ruling: bool) -> str:
    """c14p LOW-3: how a gated cell not made against the value recorded now is settled. A Disagreements ruling is ruled
    again; an adopted answer cell has no row to rule on: a fresh adopt reads the value now, and --supersede records it."""
    return "Adopt again and rule against what is recorded now" if ruling else "Adopt again, then import with --supersede"


def _stale_reason(cell: Mapping, chain: Sequence[Mapping], chains: "_Chains", run: Sequence[int],
                  exported_utc: Any, *, adopted_at: int | None = None, keeps: bool = True,
                  target: str | None = None, decision: str = "correct", slot: tuple[str, str] | None = None,
                  adopt_id: str | None = None, by: str | None = None) -> str:
    """c14k MED-1: why a ruling that keeps the recorded value is not tied (:func:`plan_and_record`): its workbook was
    adopted before the run of that value began (``chain``, latest first; :class:`_Chains`). The decision that ended the
    previous run is named only when it is known to come after the workbook (not among the decisions it was ruled
    against; a workbook placed by time alone names none). c14l MED-2: "since" is said only when the decision log's
    place (``adopted_at``) or, without it, a readable time strictly after the workbook's proves it
    (:func:`_since_adopt`); a reject, a defer or a value recorded before the adopt is never said to have come since.
    c14l MED-1: ``keeps`` ``False``: a ruling giving a different value that ``--supersede`` does not record, because it
    was not made against the value recorded now (:func:`_rules_against_now`).

    c14m: an unplaceable workbook says so (MED-2, :data:`UNPLACEABLE_REASON`); a ruling refused because the scientist's
    own earlier ruling on this row, from another adoption of the same sheet, is what is recorded now names it (MED-3);
    a workbook adopted with nothing recorded on the target never says "made against an earlier value" (LOW-1); and every
    reason ends with the ``decide`` command for ``target`` (LOW-2, :func:`decide_command`; ``slot``: the per-run
    answer slot's question and run).

    c14n: a ruling that keeps the value recorded now offers no command, only "the value is already X; adopt again to
    settle this row" (LOW-3); a copy of this very workbook (``adopt_id``) whose other holder recorded the value now
    names them (MED-1; ``by`` is this import's ``--by``); and with no readable adopt id, the ruling recorded now is
    "a ruling on this row (d-N), from this sheet", never one "on another adoption" (LOW-4)."""
    from . import propose_terms as P

    alternative = _or_decide(target, decision, cell.get("value"), slot)
    # c15b L3: decisions are named by who recorded them and when, never by id (the entry's decision_id keeps it)
    first = f"{_decider(chain[-1]) or 'someone'} recorded the value now{_on_day(chain[-1])}"
    first_value = f"the value {_decider(chain[-1]) or 'someone'} recorded{_on_day(chain[-1])}"
    against = cell.get("ruled_against")
    adopted = bool(cell.get("adopted"))  # c14p LOW-3: an adopted answer cell, with no Disagreements row to rule on
    noun = "cell" if adopted else "ruling"
    if against is not None and GOVERNING_UNPLACEABLE in against:
        if keeps:
            return f"{UNPLACEABLE_REASON}; nothing is recorded for this {noun}: {_already_there(cell.get('value'), not adopted)}"
        return (f"{UNPLACEABLE_REASON}{', then import with --supersede' if adopted else ' and rule against what is recorded now'}"
                f"; nothing is recorded for this {noun}, even with --supersede, and the value recorded now is kept{alternative}")
    ended = chains.before(run[-1]) if run else None
    changed = chains.log[ended] if ended is not None else None
    since = ""
    if against is not None and GOVERNING_DAMAGED in against:
        if keeps:
            return ("ruled on a workbook whose `_isaac` governing_decisions value is damaged, so it is never tied; "
                    f"nothing is recorded for this {noun}: {_already_there(cell.get('value'), not adopted)}")
        return (f"{'adopted from' if adopted else 'ruled on'} a workbook whose `_isaac` governing_decisions value is "
                "damaged, so it is never recorded over another value, even with --supersede; the value recorded now is "
                f"kept and nothing is recorded for this {noun}. {_again(not adopted)}" + alternative)
    if (changed is not None and against is not None and changed.get("decision_id") not in against
            and _since_adopt(ended, changed, adopted_at, exported_utc)):
        since = (f", and the value was {'rejected' if changed.get('decision') == 'reject' else 'deferred'} since "
                 f"({_by_when(changed)})" if changed.get("decision") in ("reject", "defer")
                 else f", and a different value was recorded since ({_by_when(changed)})")
    if keeps:
        placed = against is not None or P._utc(exported_utc) is not None
        lead = (f"ruled on a workbook adopted before {first}" if placed
                else f"ruled on a workbook whose adoption time cannot be placed after {first}")
        return f"{lead}{since}; nothing is recorded for this {noun}: {_already_there(cell.get('value'), not adopted)}"
    tail = (" nothing is recorded for it, even with --supersede, and the value recorded now is kept. "
            + _again(not adopted) + alternative)
    here = "this cell" if adopted else "this row"
    # c14n MED-1: a copy of this very workbook (the same adopt id), imported by someone else, recorded the value now
    copy = next((chains.log[p] for p in run if adopt_id is not None and by is not None
                 and _note_adopt_id(chains.log[p]) == adopt_id and _decider(chains.log[p]) != by), None)
    if copy is not None:
        return (f"{_whose(copy)} {'import of' if adopted else 'ruling on'} {here}{_on_day(copy)}, from "
                f"another copy of this workbook, is what is recorded now; this {noun} was not made against it, so{tail}")
    # c14m MED-3: their own earlier ruling on this row, from another adoption of this sheet, governs now
    own = next((chains.log[p] for p in run if _ruled_here(chains.log, p, cell.get("ruling"))), None)
    if own is not None:
        if adopt_id is None:  # c14n LOW-4: no readable adopt id: which adoption it came from is not known
            return (f"a ruling on this row ({_by_when(own)}), from this sheet, is what is recorded now; this "
                    f"ruling was not made against it, so{tail}")
        mine = by is None or _decider(own) == by
        return (f"{'your earlier' if mine else _whose(own)} ruling on this row"
                f"{_on_day(own)} is what is recorded now; this ruling, on another adoption of the same "
                f"sheet, was not made against it, so{tail}")
    # a ruling read before --supersede: "adopted before" only when the log's place or the time proves it
    placed = bool(run) and _since_adopt(run[-1], chain[-1], adopted_at, exported_utc)
    history = chains.history(run[0]) if run else list(chain)
    if placed and against is not None and not any(d.get("decision_id") in against for d in history):
        # c14m LOW-1: adopted with nothing recorded on the target: there was no earlier value to rule against
        if adopted:
            return (f"this cell was adopted with nothing recorded here, before {first}, so it "
                    f"never saw it{since}:{tail}")
        return (f"ruled on a workbook adopted with nothing recorded here; this ruling was made before {first}, "
                f"so it never saw it{since}:{tail}")
    if adopted:
        lead = (f"this cell was adopted before {first}{since}, against an earlier value, so" if placed
                else f"this cell is not shown to have been adopted against {first_value}, so")
        return f"{lead}{tail}"
    lead = (f"ruled on a workbook adopted before {first}{since}; this ruling was made against an earlier value, so"
            if placed else f"ruled on a workbook not shown to have been adopted against {first_value}, so")
    return f"{lead}{tail}"


#: c15b M2: how a reason ends for a target of a cell that reaches several: never a per-target command, which would
#: record the value on that target alone and leave the row split; the cell's one command covers them all
_CELL_COMMAND_TAIL = ", or record this value for all {n} targets of this cell with one command ({key}: command)"
_OFFER = ", or record this value directly: "


def _by_cell_and_commands(report: dict, how_of: Mapping[tuple[str, str], str],
                          slot_of: Mapping[str, tuple[str, str]]) -> None:
    """c15b M1, M2, M4 (:func:`plan_and_record`): ``clashes_by_cell`` and ``stale_by_cell``, one entry per cell of the
    per-target ``clashes`` and ``stale`` lists (kept, per target, in ``--json``): how many targets and runs, how many
    clash, are held back with them, or already hold the value, the cell's own reason, and ONE command that records the
    value for every target of the cell that does not hold it (:func:`decide_command`; ``isaac bundle decide`` takes
    ``--target`` once per target). A per-target reason of a cell that reaches several targets ends by naming that
    command instead of its own. c15b M4: a target that already holds the value, in a cell another of whose targets
    still holds a different one, is never told adopting again settles the row: adopting again would still ask it."""
    def holding(x: Mapping) -> bool:
        reason = str(x.get("reason") or "")
        return bool(x.get("holds_value")) or _ALREADY_TAIL in reason or reason.endswith(
            f"the value is already {_shown(x['value'])}")

    # M4: a cell another of whose targets keeps a DIFFERENT recorded value after this import (its own clash, a stale
    # ruling over it, or a target held back that holds one)
    differs = {x["cell"] for key in ("clashes", "stale") for x in report[key]
               if not holding(x) and (x.get("existing") or x.get("decision_id"))}
    for key, out in (("clashes", "clashes_by_cell"), ("stale", "stale_by_cell")):
        groups: dict[str, list[dict]] = {}
        for x in report[key]:
            groups.setdefault(x["cell"], []).append(x)
        report[out] = []
        for name, xs in groups.items():
            holds = [x for x in xs if holding(x)]
            needs = [x for x in xs if x not in holds]
            own = next((x for x in needs if not x.get("blocked_by")), needs[0] if needs else xs[0])
            pairs = [(x["target"]["id"], how_of.get((name, x["target"]["id"]), "correct")) for x in needs]
            command = _cell_command(pairs, xs[0]["value"], slot_of) if pairs else None
            if name in differs:
                for x in holds:  # M4: adopting again would still find another target holding a different value
                    x["reason"] = str(x["reason"]).replace(_ALREADY_TAIL, (
                        "; another target of this row still holds a different value, so adopting again would ask it "
                        "again: adopt again and rule the row, or record the value for all of them with the cell's one "
                        "command"))
            if len(pairs) > 1 and command:  # one target to record: its own command is the cell's
                # a per-run answer slot is answered through its question one run at a time: its own command stays
                for x in (x for x in needs if x["target"]["id"] not in slot_of):
                    head, sep, _tail = str(x["reason"]).rpartition(_OFFER)
                    if sep:
                        x["reason"] = head + _CELL_COMMAND_TAIL.format(n=len(pairs), key=out)
            reason = str(own.get("reason") or "")
            report[out].append({
                "cell": name, "header": xs[0].get("header"), "value": xs[0]["value"], "targets": len(xs),
                "runs": len({x.get("run_id") for x in xs if x.get("run_id")}),
                "clashes": sum(1 for x in needs if not x.get("blocked_by")),
                "held_back": sum(1 for x in needs if x.get("blocked_by")), "hold_value": len(holds),
                "target_ids": [x["target"]["id"] for x in needs],
                "reason": reason.split(_OFFER, 1)[0].split(_CELL_COMMAND_TAIL.split("{", 1)[0], 1)[0],
                "command": command})


def _cell_command(pairs: Sequence[tuple[str, str]], value: Any, slot_of: Mapping[str, tuple[str, str]]) -> str:
    """c15b M2: the ``decide`` command(s) recording ``value`` for every target of ``pairs`` ((target, decision)) at once:
    one per decision, naming every target (a per-run answer slot the import added is answered through its question,
    one run at a time: ``--question <id> --only run:<id>``), joined by ``&&``: run as one shell line, each command
    records its own targets, so a refusal of the second leaves the first recorded (say "these commands")."""
    by_how: dict[str, list[str]] = {}
    slots = []
    for tid, how in pairs:
        if tid in slot_of:
            slots.append(decide_command(tid, how, value, slot_of[tid]))
        else:
            by_how.setdefault(how, []).append(tid)
    return " && ".join([decide_command(tids, how, value) for how, tids in by_how.items()] + slots)


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
    report: dict[str, list] = {"decisions": [], "clashes": [], "already": [], "tied": [], "stale": [], "refused": [],
                               "over_recorded": [],  # c15b H2: rulings the row asked for, recorded over the value now
                               "nowhere": list(cells["nowhere"]), "left_alone": [], "campaign_not_filled": [],
                               "contradictions": []}
    runs_by_id = {r["run_id"]: r for r in bundle["runs"]}
    contradicted: set[tuple[str, str]] = set()
    awaiting: list[dict] = []
    # a file reading is what adopt compares (:class:`_Adopter`): a parser value, a file-name token, an AI
    # reading of a FILE; an AI reading of the sheet the cells were adopted from is that sheet, not a file
    adopter = _Adopter(bundle, index, field_rules(), str(cells.get("adopted_from") or ""))

    def file_readings(cell: Mapping, decision: str, kind: str, obj: Mapping) -> list[str]:
        """What a file says against this cell for this target, one line each. A literal from which no value
        was derived (a macro's file name, a sample token) is not a reading of a value: answering it
        replaces nothing."""
        readings = []
        if decision == "correct" and kind == "candidate" and obj.get("value") is not None:
            ev = next((e for e in obj["evidence"] if e["method"] != "ai_interpretation"), None)
            # c16c: a value read from a scan-header comment line says so, with the header's own words
            said = (f", read from the scan header's {ev['literal_value']!r}" if ev is not None and B.is_header_comment_candidate(obj)
                    else "")
            readings.append(f"replaces extracted {_shown(obj['value'])}{said} — {_ev_where(index, ev)}")
        run = runs_by_id.get(obj.get("run_id") or "")
        if run is not None:
            for t in name_token_readings(run_names(bundle, run), cell["path"]):
                if not _agrees(t["value"], cell["value"]):
                    readings.append(f"contradicts the file name token {t['token']} ({t['value']!r}) in {t['name']}")
        for r in adopter.against(cell["value"], obj.get("run_id"), cell["path"]):
            if r["kind"] in ("ai_reading", "scan_header"):  # c16c: what a scan header states is a file reading
                readings.append(f"contradicts the {r['source']}: {_shown(r['value'])}")
            elif r["kind"] == "scan_header_mention":  # r3a H2: said as written, never as a value read
                readings.append(f"contradicts the {r['source']}")
        return readings

    def contradiction(cell: Mapping, obj: Mapping, readings: list[str], outcome: str) -> None:
        """A cell that REPLACES an extracted value, or contradicts the run's file-name token or an AI reading
        of a file, is named on its own line: a count of ``correct`` decisions never shows it. ``outcome``
        says what happens to it: ``recorded_as_typed`` (the scientist typed it, or ruled it) or
        ``awaiting_ruling`` (adopted from their sheet before the reading existed: not recorded)."""
        key = (cell["cell"], obj.get("run_id") or "")
        if readings and key not in contradicted:
            contradicted.add(key)
            report["contradictions"].append({"cell": cell["cell"], "run_id": obj.get("run_id"), "target_field_path": cell["path"],
                                             "value": cell["value"], "readings": readings, "outcome": outcome,
                                             **({"adopted": cell["adopted"]} if cell.get("adopted") else {})})

    report["asked_beamtime_wide"] = []
    asked_of: dict[str, dict | None] = {}
    payload_box: list[Mapping] = []

    def beamtime_question(path: str) -> dict | None:
        """The question that asks ``path`` ONCE for the whole beamtime, when this bundle holds the field only
        at experiment scope (a beamtime candidate, its shared conflict, a record-scope missing value): a run's
        cell has no target of its own then, and that question is what answers it (an answered question too,
        with the same id). ``None`` when no such question exists. Built once, only when a cell needs it."""
        if path in asked_of:
            return asked_of[path]
        from . import questions as Q

        ids = {m["value_id"] for m in index.missing_by_run.get((None, path), [])}
        ids |= {c["candidate_id"] for c in index.cands_by_run.get((None, path), [])}
        ids |= {cf["conflict_id"] for cf in bundle.get("conflicts") or () if cf.get("candidate_id") in ids}
        found = None
        if ids:
            if not payload_box:
                payload_box.append(Q.consolidate(bundle, include_answered=True, explain_counter=False))
            for q in payload_box[0]["questions"]:
                if q["kind"] not in Q.VALUE_KINDS or q.get("informational"):
                    continue
                hit = next((tids for field, tids in Q._value_paths(q) if field == path and ids.intersection(tids)), None)
                if hit is not None:
                    found = {"question_id": q["question_id"], "command": Q.scoped_answer_command(q, path),
                             "answered": any(tid in hit and d.get("decision") in (B.CONFIRMING_DECISIONS | {"reject"})
                                             for (_kind, tid), d in latest.items())}
                    break
        asked_of[path] = found
        return found

    file_list_runs = cells.get("file_list_run_ids") or set()  # c14p LOW-5: the runs the File List names
    planned: list[tuple[dict, str, str, Mapping, str]] = []  # (cell, decision, kind, obj, target_id)
    # H1: a Campaign Info beamline (or facility acronym) naming another one than a facility hint — named once per
    # cell (never once per run it fills); held back when adopt copied it, recorded when the scientist typed it
    hinted = {c["cell"]: lines for c in cells["cells"]
              if c["scope"] == "experiment" and (lines := facility_hint_lines(bundle, c["path"], c["value"]))}
    report["ruled_per_run"] = []
    slots_added: list[str] = []
    slot_of: dict[str, tuple[str, str]] = {}  # c14n LOW-2: an added slot's (question id, run id), for the command offered
    for cell in cells["cells"]:
        path, value = cell["path"], cell["value"]
        targets: list[tuple[str, str, Mapping, str]] = []
        if cell["scope"] == "experiment":
            outside = []
            for m in index.missing_by_path.get(path, []):
                if m["run_id"] is None or m["run_id"] in file_list_runs:  # record scope, or a File List run
                    targets.append(("correct", "missing_value", m, m["value_id"]))
                else:
                    outside.append(m)
            if outside:
                report["campaign_not_filled"].append({
                    "cell": cell["cell"], "target_field_path": path, "targets": len(outside),
                    "run_ids": sorted({m["run_id"] for m in outside})[:20], "runs": len({m["run_id"] for m in outside}),
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
            asked = beamtime_question(path) if cell["scope"] == "run" else None
            if asked is not None and cell["sheet"] == SHEET_DISAGREE and cell.get("run_id"):
                # M1(b): A RULING NAMES ITS RUNS. Its value is recorded for exactly them — on a per-run answer slot
                # when the import asks the field once for the beamtime (as `decide --question --only group:<id>`
                # does), never on the beamtime-wide target, which would reach every run of the beamtime
                ids, added = M.run_answer_targets(bundle, path, [cell["run_id"]], question_id=asked["question_id"],
                                                  how=f"their ruling {cell['cell'].split(' via ', 1)[0]}")
                slots_added += added
                slot_of.update({vid: (asked["question_id"], cell["run_id"]) for vid in added})
                slot_obj = {m["value_id"]: m for m in bundle["missing_values"]}
                for vid in ids:
                    targets.append(("correct", "missing_value", slot_obj[vid], vid))
                report["ruled_per_run"].append({"cell": cell["cell"], "header": cell["header"], "target_field_path": path,
                                                "run_id": cell["run_id"], "question_id": asked["question_id"],
                                                "answered": asked["answered"], "slots_added": len(added)})
            elif asked is not None:
                generic = asked["command"].replace('--by "<your name>"', f"--by {shlex.quote(by)}")
                command = generic
                if isinstance(value, str) and "--json" not in command:
                    # c14o LOW-3: `--value=<v>`, as every offered command says it, so `-x` is never read as an option
                    command = re.sub(r"--value <[^>]*>", lambda _m: f"--value={shlex.quote(value)}", command)
                report["asked_beamtime_wide"].append({
                    "cell": cell["cell"], "header": cell["header"], "value": value, "run_id": cell["run_id"],
                    "target_field_path": path, "question_id": asked["question_id"], "answered": asked["answered"],
                    "command": command, "_generic_command": generic,
                    "reason": (f"this bundle asks {path} once for the whole beamtime (question {asked['question_id']}"
                               + (", answered" if asked["answered"] else "") + "), not per run, so this cell is not "
                               "recorded; " + ("to change that answer" if asked["answered"] else "answer that question")
                               + f": {command}"),
                })
                continue
            else:
                report["nowhere"].append({"cell": cell["cell"], "header": cell["header"], "value": value,
                                          "reason": f"this run has no missing or extracted value for {path} in this bundle"})
                continue
        for decision, kind, obj, tid in targets:
            planned.append((cell, decision, kind, obj, tid))

    # ONE QUESTION, CELLS THAT DIFFER: one command per value would be wrong (running them in turn leaves the
    # last standing, for every run). The cells name the values; the scientist says which applies.
    by_question: dict[str, set[str]] = {}
    for x in report["asked_beamtime_wide"]:
        by_question.setdefault(x["question_id"], set()).add(repr(x["value"]))
    for x in report["asked_beamtime_wide"]:
        generic = x.pop("_generic_command")
        values = sorted(by_question[x["question_id"]])
        if len(values) > 1:
            x["command"], x["values_differ"] = generic, values
            x["reason"] = (f"this bundle asks {x['target_field_path']} once for the whole beamtime (question "
                           f"{x['question_id']}" + (", answered" if x["answered"] else "") + "), not per run, and this "
                           f"workbook's cells for it hold {len(values)} different values ({', '.join(values)}): nothing is "
                           "recorded, and the scientist says which applies to the whole beamtime, then: " + generic)

    # Two cells of THIS workbook giving one target different values: neither is recorded.
    values_of: dict[str, set[str]] = {}
    for cell, _d, _k, _o, tid in planned:
        values_of.setdefault(tid, set()).add(repr(cell["value"]))
    split = {tid for tid, vs in values_of.items() if len(vs) > 1}
    # c14j LOW-2: a target a Disagreements ruling reaches is that ruling's: a plain cell (read first, the File List) giving
    # it the same value never pre-empts it (its "already recorded" would leave the row asked again at every adopt)
    ruled = {tid for cell, _d, _k, _o, tid in planned if cell.get("ruling") and tid not in split}
    calls: dict[tuple, dict] = {}
    tied: set[str] = set()  # c14i MED-1: a ruling's same value, recorded again to tie it to their sheet
    chains = _Chains(bundle)  # c14k MED-1: the same-value run that ends at each target's governing decision
    place_of = {id(d): i for i, d in enumerate(chains.log)}
    # c14l MED-2: the decision log's length when the workbook was adopted ("recorded since" is a place, not a time);
    # c14m MED-2: trusted only while the log still begins with the decisions it held then (else unplaceable)
    adopted_at, unplaceable = _placed(cells, chains.log)
    # c14m MED-3: a decision this very adoption recorded (its note carries the id) was ruled against the value now
    # c14n MED-1: and by the same person (`--by`): a copy of the workbook shares its id
    # c14o LOW-2: the name compared is the stripped one, as `record_decision` stores it (`--by "Name "` is Name)
    placing = dict(adopted_at=adopted_at, places=place_of, adopt_id=None if unplaceable else cells.get("adopt_id"),
                   by=by.strip())

    def offer(tid: str, decision: str, value: Any) -> str:
        return _or_decide(tid, decision, value, slot_of.get(tid))  # c14n LOW-2

    stale_said = dict(adopted_at=adopted_at, adopt_id=placing["adopt_id"], by=placing["by"])
    seen_target: set[str] = set()
    # c14m MED-1: every target each Disagreements ruling cell reaches, as a `stale_rulings` entry would list it
    # c14o MED-1: every target each GATED cell reaches (an adopted Campaign Info, File List or Technique answer cell
    # too), keyed on that cell: a Technique cell is one per File List row ("… via 'File List'!B5"), as before
    reached: dict[str, list[dict]] = {}
    # c14o MED-2: the first target of each gated cell that clashed, which the all-or-nothing lines below name
    clashed: dict[str, dict] = {}
    noun_of = {c["cell"]: "ruling" if c["sheet"] == SHEET_DISAGREE else "cell" for c, *_rest in planned}
    # c14p MED-1: a stale ruling whose target already holds its value: listed, never a reason to hold back the rest
    keeps_value: set[tuple[str, str]] = set()
    # c15a LOW-1: the "seen" clash lines of each gated cell, rewritten when another target of the cell stops --supersede
    seen_lines: dict[str, list[tuple[dict, str, str, Any, str]]] = {}

    def clash(cell: Mapping, tid: str, run_id: str | None, why: str) -> None:
        """c14p LOW-1: the clash the all-or-nothing lines name; one --supersede would record ("seen") gives way to one
        it would not, so "Pass --supersede to record it for all of them" is said only when that is true of every one."""
        had = clashed.get(cell["cell"])
        if had is None or (had["why"] == "seen" and why != "seen"):
            clashed[cell["cell"]] = {"tid": tid, "run_id": run_id, "why": why}

    def reach(cell: Mapping, kind: str, obj: Mapping, tid: str, decision: str, prior: Mapping | None) -> None:
        reached.setdefault(cell["cell"], []).append({
            "cell": cell["cell"], "target": {"kind": kind, "id": tid}, "value": cell["value"], "run_id": obj.get("run_id"),
            "header": cell["header"], "decision_id": (prior or {}).get("decision_id"), "_decision": decision})

    for cell, decision, kind, obj, tid in planned:
        # c14n MED-2: an adopted File List cell is gated as a ruling is (a cell typed into the workbook, or one of a
        # template that was never adopted, is not: it records over another value with --supersede, as before)
        gated = cell["sheet"] == SHEET_DISAGREE or bool(cell.get("adopted"))
        if unplaceable and gated:
            cell = {**cell, "ruled_against": [GOVERNING_UNPLACEABLE]}  # c14m MED-2: its governing ids name nothing sure
        if tid in split:
            report["clashes"].append({"cell": cell["cell"], "target": {"kind": kind, "id": tid}, "value": cell["value"],
                                      "run_id": obj.get("run_id"), "header": cell["header"],
                                      "reason": "another cell of this workbook gives this target a different value; neither "
                                                "is recorded" + offer(tid, decision, cell["value"])})
            if gated:  # c14o MED-2: a clash of a gated cell, as one with an earlier decision is
                reach(cell, kind, obj, tid, decision, _prior(bundle, kind, obj, latest))
                clash(cell, tid, obj.get("run_id"), "split")
            continue
        if tid in seen_target or (tid in ruled and not cell.get("ruling")):
            continue
        seen_target.add(tid)
        prior = _prior(bundle, kind, obj, latest)
        if gated:
            reach(cell, kind, obj, tid, decision, prior)
        if prior is not None and prior.get("decision") in (B.CONFIRMING_DECISIONS | {"reject"}):
            base = obj.get("value") if kind == "candidate" else None
            before = B.final_value(base, prior)
            same = _same_value(before, cell["value"]) and prior.get("decision") != "reject"
            # c14k MED-1: the unbroken same-value run ending at the governing decision; a ruling on their cell anywhere
            # in it is this one, already recorded (another sheet's tie since extends the run, never replaces it)
            run = chains(place_of.get(id(prior), -1)) or []
            chain = [chains.log[p] for p in run] or [prior]
            untied = same and cell.get("ruling") and not _ruled_in_chain(chain, range(len(chain)), cell["ruling"])
            history = chains.history(run[0]) if run else [prior]
            if untied and _rules_against_now(cell, prior, cells.get("exported_utc"), chain, history, **placing):
                # c14i MED-1: a ruling that keeps the recorded value, which no ruling on their cell AS IT READS NOW
                # recorded (they edited it since, or the value came from a file or `decide`): recorded again, tied to
                # their sheet, or every later adopt would ask it again. c14j MED-1: only a ruling made against a
                # decision of that run (c14k MED-1); a stale workbook's is listed apart, below
                tied.add(tid)
                report["tied"].append({"cell": cell["cell"], "target": {"kind": kind, "id": tid}, "value": cell["value"],
                                       "run_id": obj.get("run_id"), "header": cell["header"],
                                       "decision_id": prior.get("decision_id"),
                                       "decided_by": (prior.get("decided_by") or {}).get("name"),
                                       "decided_utc": prior.get("decided_utc")})
            elif untied:
                # c14k MED-1: a ruling on a workbook adopted before this run of the value began: nothing is recorded,
                # and it is said apart (never "already recorded": the next adopt of this sheet still asks it)
                report["stale"].append({"cell": cell["cell"], "target": {"kind": kind, "id": tid}, "value": cell["value"],
                                        "run_id": obj.get("run_id"), "header": cell["header"],
                                        "decision_id": prior.get("decision_id"),
                                        "reason": _stale_reason(cell, chain, chains, run, cells.get("exported_utc"),
                                                                target=tid, decision=decision, slot=slot_of.get(tid),
                                                                **stale_said)})
                keeps_value.add((cell["cell"], tid))  # c14p MED-1: the target already holds this value
                continue
            elif same:
                report["already"].append({"cell": cell["cell"], "target": {"kind": kind, "id": tid}, "value": cell["value"],
                                          "decided_by": (prior.get("decided_by") or {}).get("name"), "decision_id": prior.get("decision_id")})
                continue
            else:
                # c14l MED-1: --supersede records a ruling over the value that governs only when the ruling was made
                # against it. A ruling on a workbook adopted before that value was recorded never saw it: recorded,
                # two such workbooks (one ruling each value) would flip the value at every import, forever
                # c14n MED-2: an adopted File List cell too: two of their sheets that differ, adopted cleanly, would
                # otherwise flip it at every import
                unseen = gated and not _rules_against_now(
                    cell, prior, cells.get("exported_utc"), chain, history, **placing, keeps=False)
                # c15b H2: A RULING THE ROW ASKED FOR. A Disagreements row that named the value recorded for this field
                # ("recorded `-0.8`; your sheet says `0.9`: rule which") asked for exactly this ruling: made against that
                # value (one of the same-value run that governs now is among the decisions the row read at adopt, and
                # the workbook is placeable), it is recorded over it without --supersede. A decision recorded since
                # the adopt (unseen), a copy, or another adoption's ruling still never flips it (c14l-c14p)
                asked = (cell["sheet"] == SHEET_DISAGREE and bool(cell.get("shown")) and not unplaceable and not unseen
                         and any(d.get("decision_id") in (cell.get("ruled_against") or ()) for d in chain))
                said_now = _recorded_now(prior, before, cells.get("adopt_id"), placing["by"])  # c15b M3
                if not supersede and not asked:
                    report["clashes"].append(entry := {
                        "cell": cell["cell"], "target": {"kind": kind, "id": tid}, "value": cell["value"],
                        "run_id": obj.get("run_id"), "header": cell["header"],
                        "existing": {"decision": prior.get("decision"), "value": before, "decision_id": prior.get("decision_id"),
                                     "decided_by": (prior.get("decided_by") or {}).get("name"),
                                     "decided_utc": prior.get("decided_utc"),
                                     "source": _source_of(prior, cells.get("adopt_id"), placing["by"])},
                        # c14p LOW-3: an adopted answer cell is "this cell", settled by adopting again then --supersede
                        "reason": (f"an earlier scientist decision gives a different value ({said_now}); skipped, and "
                                   "--supersede does not record it either: " + (UNPLACEABLE_REASON + (
                                       " and rule against what is recorded now" if noun_of[cell["cell"]] == "ruling"
                                       else ", then import with --supersede") if unplaceable else
                                       f"this {noun_of[cell['cell']]} was not made against the value recorded now. "
                                       + _again(noun_of[cell["cell"]] == "ruling"))
                                   + offer(tid, decision, cell["value"]) if unseen else
                                   # c14n LOW-6: the parenthesis closes before the command, so a pasted one ends cleanly
                                   f"an earlier scientist decision gives a different value ({said_now}); skipped (pass "
                                   "--supersede to record this one)" + offer(tid, decision, cell["value"])),
                    })
                    if gated:  # c14o MED-2
                        clash(cell, tid, obj.get("run_id"), "unseen" if unseen else "seen")
                        if not unseen:
                            seen_lines.setdefault(cell["cell"], []).append((entry, tid, decision, cell["value"], said_now))
                    continue
                if asked:  # c15 review: listed with --supersede too, so each one is read back
                    report["over_recorded"].append({"cell": cell["cell"], "target": {"kind": kind, "id": tid},
                                                    "value": cell["value"], "run_id": obj.get("run_id"),
                                                    "header": cell["header"], "recorded_now": before,
                                                    "decision_id": prior.get("decision_id"), "said": said_now})
                if unseen:
                    report["stale"].append({"cell": cell["cell"], "target": {"kind": kind, "id": tid}, "value": cell["value"],
                                            "run_id": obj.get("run_id"), "header": cell["header"],
                                            "decision_id": prior.get("decision_id"),
                                            "reason": _stale_reason(cell, chain, chains, run, cells.get("exported_utc"),
                                                                    keeps=False, target=tid, decision=decision,
                                                                    slot=slot_of.get(tid), **stale_said)})
                    continue
        if cell["cell"] in hinted and tid not in tied:  # c14j LOW-1: a tied ruling changes no value
            # once per cell: a Campaign Info answer fills every run's target, and one hint line covers them all
            key = (cell["cell"], "")
            if key not in contradicted:
                contradicted.add(key)
                outcome = "awaiting_ruling" if cell.get("adopted") else "recorded_as_typed"
                report["contradictions"].append({"cell": cell["cell"], "run_id": None, "target_field_path": cell["path"],
                                                 "value": cell["value"], "readings": hinted[cell["cell"]], "outcome": outcome,
                                                 "hint": True, **({"adopted": cell["adopted"]} if cell.get("adopted") else {})})
                if cell.get("adopted"):
                    origin = cell["adopted"]
                    awaiting.append({"id": None, "cell": cell["cell"], "header": cell["header"], "target_field_path": cell["path"],
                                     "run_id": None, "target": None, "their_value": cell["value"],
                                     "why": (f"adopted from {origin.get('their_file')} {origin.get('their_cell')}, but it "
                                             f"{'; '.join(hinted[cell['cell']])}. Run `isaac bundle template adopt` again: it "
                                             "lists this as a disagreement to rule on")})
            if cell.get("adopted"):
                continue
        readings = file_readings(cell, decision, kind, obj)
        if readings and cell.get("adopted"):
            # adopted because no file reading contradicted it THEN; one does now. The scientist never typed
            # this cell here, so it is not recorded until they rule (a fresh adopt lists it as a disagreement).
            origin = cell["adopted"]
            contradiction(cell, obj, readings, "awaiting_ruling")
            awaiting.append({"id": None, "cell": cell["cell"], "header": cell["header"], "target_field_path": cell["path"],
                             "run_id": obj.get("run_id"), "target": {"kind": kind, "id": tid}, "their_value": cell["value"],
                             "why": (f"adopted from {origin.get('their_file')} {origin.get('their_cell')}, but a file reading "
                                     f"now contradicts it: {'; '.join(readings)}. Run `isaac bundle template adopt` again: "
                                     "it lists this as a disagreement to rule on")})
            continue
        call = calls.setdefault((cell["cell"], decision, tid in tied), {"cell": cell, "decision": decision, "tids": [],
                                                                        "tie": tid in tied})
        call["tids"].append(tid)
        report["decisions"].append({"cell": cell["cell"], "sheet": cell["sheet"], "header": cell["header"],
                                    "target": {"kind": kind, "id": tid}, "target_field_path": cell["path"],
                                    "run_id": obj.get("run_id"), "decision": decision, "value": cell["value"]})
        if tid not in tied:  # c14j LOW-1: a tied ruling keeps the recorded value, so it replaces no file reading
            contradiction(cell, obj, readings, "recorded_as_typed")

    # c14m MED-1: A RULING CELL IS ALL OR NOTHING. When any target it reaches was not made against the value recorded
    # now (listed in `stale_rulings`), nothing is recorded for any of them, and every one is listed there (as two cells
    # of this workbook giving one target different values record neither): a whole-beamtime ruling is never applied
    # to some runs and not others
    # c14p MED-1: a target that already holds the ruling's value is listed ("the value is already …"), and never holds
    # back the rest: the value it keeps is the one the ruling gives every other target
    stale_cells = {x["cell"] for x in report["stale"]
                   if x["cell"] in reached and (x["cell"], x["target"]["id"]) not in keeps_value}
    if stale_cells:
        listed = {(x["cell"], x["target"]["id"]): x for x in report["stale"]}
        # c14n LOW-3: a target this cell would have tied, or that already holds its value, gets no command to record it
        holds = {(d["cell"], d["target"]["id"]) for key in ("tied", "already") for d in report[key]}
        report["stale"] = [x for x in report["stale"] if x["cell"] not in stale_cells]
        # c14p LOW-2: and its clashes (a target another cell of this workbook gives another value) are said once, here:
        # one target is never told both "--supersede records it" and "nothing is recorded, even with --supersede"
        report["clashes"] = [c for c in report["clashes"] if c["cell"] not in stale_cells]
        for name in (n for n in reached if n in stale_cells):
            first = next(x for x in reached[name] if (name, x["target"]["id"]) in listed
                         and (name, x["target"]["id"]) not in keeps_value)
            noun = noun_of[name]  # c14o MED-1: an adopted answer cell is no ruling
            for x in reached[name]:
                how = x.pop("_decision")
                report["stale"].append(listed.get((name, x["target"]["id"])) or {**x, "reason": (
                    f"this {noun} reaches {len(reached[name])} targets and is recorded for all of them or none, and "
                    f"{first['target']['id']}{' (' + first['run_id'] + ')' if first.get('run_id') else ''} was not made "
                    "against the value recorded there now (its own line says why); nothing is recorded for this one "
                    + (f"either, and {_already_there(x['value'], noun == 'ruling')}" if (name, x["target"]["id"]) in holds else
                       f"either. {_again(noun == 'ruling')}" + offer(x["target"]["id"], how, x["value"]))),
                    "blocked_by": first["target"]["id"]})
        for key in ("decisions", "tied", "already"):
            report[key] = [d for d in report[key] if d["cell"] not in stale_cells]
        calls = {k: c for k, c in calls.items() if k[0] not in stale_cells}

    # c14o MED-2: AND WHEN ANY TARGET IT REACHES CLASHES. A gated cell giving one of its targets a value another
    # scientist decision (or another cell of this workbook) contradicts records none of them: its other targets are
    # listed with the clash, each naming the target that clashed, so a whole-beamtime answer never records on 8 runs of
    # 9 (and a later --supersede import never keeps that split). A cell that reaches one target is unaffected
    clash_cells = {n for n in clashed if n in reached and n not in stale_cells and len(reached[n]) > 1}
    if clash_cells:
        # a target with a line of its own (its clash, or c14p MED-1 a stale ruling that keeps its value) keeps it
        listed = {(x["cell"], x["target"]["id"]) for key in ("clashes", "stale") for x in report[key]}
        holds = {(d["cell"], d["target"]["id"]) for key in ("tied", "already") for d in report[key]}
        for name in (n for n in reached if n in clash_cells):
            first = clashed[name]
            noun = noun_of[name]
            why = {"split": "gets a different value from another cell of this workbook",
                   "seen": "holds a different value, from an earlier scientist decision",
                   "unseen": "holds a different value this " + noun + " was not made against"}[first["why"]]
            # c14p LOW-1: "seen" only when every clash of the cell is one --supersede records (see `clash`)
            fix = {"split": "Give those cells one value" + (", or adopt again and rule against what is recorded now"
                                                            if noun == "ruling" else ", and import again"),
                   "seen": "Pass --supersede to record it for all of them" + (
                       ", or adopt again and rule against what is recorded now" if noun == "ruling" else ""),
                   "unseen": _again(noun == "ruling")}[first["why"]]
            if first["why"] != "seen":
                # c15a LOW-1: --supersede records none of this cell's targets while another is unseen or split, so a
                # "seen" line never says to pass it: it says what stops it, and offers adopting again
                for entry, tid, how, value, said in seen_lines.get(name, ()):
                    entry["reason"] = (
                        f"an earlier scientist decision gives a different value ({said}); skipped, and "
                        f"--supersede records none of "
                        f"this {noun}'s targets, because {first['tid']}{' (' + first['run_id'] + ')' if first.get('run_id') else ''} "
                        f"{why}. {fix}" + offer(tid, how, value))
            for x in reached[name]:
                how = x.pop("_decision")
                if (name, x["target"]["id"]) in listed:
                    continue
                report["clashes"].append({
                    "cell": name, "target": x["target"], "value": x["value"], "run_id": x["run_id"],
                    "header": x.get("header"), "decision_id": x.get("decision_id"),  # c15b M4: what it holds now
                    "blocked_by": first["tid"],  # c14p LOW-2: held back with that clash, not a clash of its own
                    **({"holds_value": True} if (name, x["target"]["id"]) in holds else {}),  # c15a LOW-3
                    "reason": (f"this {noun} reaches {len(reached[name])} targets and is recorded for all of them or none, "
                               f"and {first['tid']}{' (' + first['run_id'] + ')' if first.get('run_id') else ''} {why} "
                               "(its own line says why); nothing is recorded for this one "
                               + (f"either, and {_already_there(x['value'], noun == 'ruling')}"
                                  if (name, x["target"]["id"]) in holds else
                                  f"either. {fix}" + offer(x["target"]["id"], how, x["value"])))})
        for key in ("decisions", "tied", "already"):
            report[key] = [d for d in report[key] if d["cell"] not in clash_cells]
        calls = {k: c for k, c in calls.items() if k[0] not in clash_cells}

    recorded: list[str] = []
    unchanged: list[str] = []
    refused_targets: set[str] = set()
    for call in calls.values():
        cell, decision, tids = call["cell"], call["decision"], call["tids"]
        try:
            res = M.record_decision(bundle, target_ids=tids, decision=decision, value=cell["value"], by=by, orcid=orcid,
                                    note=cell["note"], record_unchanged=call["tie"])
        except M.MutationRefused as exc:
            report["refused"].append({"cell": cell["cell"], "targets": tids, "decision": decision, "reason": str(exc)})
            refused_targets.update(tids)
            continue
        recorded += res["recorded"]
        unchanged += res["unchanged"]
    report["decisions"] = [d for d in report["decisions"] if d["target"]["id"] not in refused_targets]
    report["tied"] = [t for t in report["tied"] if t["target"]["id"] not in refused_targets]
    # a per-run slot whose answer was not recorded (refused, a clash) is never left behind as an empty question
    gone = set(M.drop_unrecorded_slots(bundle, slots_added))
    report["decisions"] = [d for d in report["decisions"] if d["target"]["id"] not in gone]
    report["tied"] = [t for t in report["tied"] if t["target"]["id"] not in gone]
    report["over_recorded"] = [x for x in report["over_recorded"]
                               if (x["cell"], x["target"]["id"]) in {(d["cell"], d["target"]["id"]) for d in report["decisions"]}]
    # c15b M1, M2, M4: each cell's clashes and stale targets, ONE entry per cell, with one command for all its targets
    how_of = {(c["cell"], tid): d for c, d, _k, _o, tid in planned}
    _by_cell_and_commands(report, how_of, slot_of)
    kept = {(d["cell"], d.get("run_id") or "") for d in report["decisions"]}
    kept_cells = {d["cell"] for d in report["decisions"]}
    report["contradictions"] = [c for c in report["contradictions"]
                                if c["outcome"] == "awaiting_ruling" or (c["cell"], c.get("run_id") or "") in kept
                                or (c.get("hint") and c["cell"] in kept_cells)]
    report["ruled_per_run"] = _ruled_per_run_summary(bundle, report["ruled_per_run"], report["decisions"])
    # c7-r HIGH-1: A BEAMTIME-WIDE ANSWER DOES NOT REACH A GROUP THAT KEEPS ITS OWN. A Campaign Info value recorded on
    # a beamtime-wide target fills every group but one whose run holds a differing answer of its own (an answer slot
    # from `--only group:<id>` or a ruling, or its own target): that group's record would hold two values and fill
    # nothing. It is NAMED, with the command that changes it — never counted as reached, nor only listed as a clash.
    report["not_reached"] = []
    recorded_once = {(d["cell"], d["target_field_path"]): d["value"] for d in report["decisions"] if d.get("run_id") is None}
    if recorded_once:
        view = B.apply_derivations(copy.deepcopy(bundle))  # the states the save derives
        for (cell_name, path), value in recorded_once.items():
            asked = beamtime_question(path)
            for k in M.groups_keeping_their_own_answer(view, path, value,
                                                       question_id=asked["question_id"] if asked else None):
                report["not_reached"].append({"cell": cell_name, "target_field_path": path, "value": value, **k,
                                              "reason": M.not_reached_sentence(path, [k], lead="")})
    report["reaction_needs"] = reaction_followups(bundle, report["decisions"])
    report["awaiting_ruling"] = awaiting
    report["recorded_target_ids"] = recorded
    report["unchanged_target_ids"] = unchanged
    return report


REACTION_PATHS = ("context.electrochemistry.reaction", "context.reaction.name")


def _run_group_of(bundle: Mapping) -> dict[str, str]:
    """``run_id -> group_id`` of the first live group holding it."""
    by_key = _live_group_of(bundle)
    return {r["run_id"]: by_key[r["run_key"]] for r in bundle["runs"] if r["run_key"] in by_key}


def reaction_lacking(bundle: Mapping, run_ids: Sequence[str], answered_now: set[tuple[str, str]]) -> dict | None:
    """L3: a run that states a reaction needs its drive and catalysis (``bundle.REACTION_REQUIRED_PATHS``). For the
    runs ``run_ids`` that get a reaction now: ``{fields, runs, groups}`` still unanswered — no scientist-confirmed
    value for the run (or the beamtime) and none in ``answered_now`` (``(run_id, path)``) — or ``None``."""
    group_of = _run_group_of(bundle)
    objs = [*(bundle.get("candidates") or ()), *(bundle.get("missing_values") or ())]
    confirmed = {(o.get("run_id"), o.get("target_field_path")) for o in objs
                 if o.get("value_state") == B.STATE_SCIENTIST_CONFIRMED}
    lacking: dict[str, set[str]] = {}
    for rid in dict.fromkeys(run_ids):
        for path in B.REACTION_REQUIRED_PATHS:
            if (rid, path) in answered_now or (rid, path) in confirmed or (None, path) in confirmed:
                continue
            lacking.setdefault(path, set()).add(rid)
    if not lacking:
        return None
    runs = set().union(*lacking.values())
    return {"fields": sorted(lacking), "runs": len(runs), "groups": len({group_of[r] for r in runs if r in group_of})}


def reaction_followups(bundle: Mapping, decisions: Sequence[Mapping]) -> dict | None:
    """:func:`reaction_lacking` for the runs an import gives a reaction."""
    runs = [d["run_id"] for d in decisions if d.get("target_field_path") in REACTION_PATHS and d.get("run_id")]
    if not runs:
        return None
    return reaction_lacking(bundle, runs, {(d.get("run_id"), d.get("target_field_path")) for d in decisions})


def _reaction_needs_line(x: Mapping, verb: str) -> str:
    return (f"A reaction {verb} makes {' and '.join(x['fields'])} required for {x['groups']} group(s) ({x['runs']} run(s)) "
            "that have no answer for it yet: fill 'Reaction Drive' and 'Reaction Catalysis' (File List) for those runs, or "
            "answer their questions (`isaac bundle questions <bundle_dir>`).")


def _ruled_per_run_summary(bundle: Mapping, entries: Sequence[Mapping], decisions: Sequence[Mapping]) -> list[dict]:
    """One entry per ruling cell recorded per run for a field asked once for the beamtime: how many runs it reached,
    how many answer slots it added, and how many groups the beamtime-wide question still covers."""
    if not entries:
        return []
    recorded = {(d["cell"], d.get("run_id")) for d in decisions}
    group_of = _run_group_of(bundle)
    total = len({g for g in group_of.values()})
    out: dict[tuple, dict] = {}
    for x in entries:
        if (x["cell"], x["run_id"]) not in recorded:
            continue
        e = out.setdefault((x["cell"], x["question_id"]), {k: x[k] for k in ("cell", "header", "target_field_path",
                                                                           "question_id", "answered")} | {"runs": 0, "slots_added": 0})
        e["runs"] += 1
        e["slots_added"] += x["slots_added"]
    for e in out.values():
        touched = {group_of.get(d.get("run_id")) for d in decisions if d.get("target_field_path") == e["target_field_path"]}
        e["groups_left_to_the_question"] = max(total - len(touched - {None}), 0)
    return list(out.values())


def off_list_requests(cells: Sequence[Mapping]) -> list[dict]:
    """Off-list cells (``read_cells`` ``off_list``; adopt's not-allowed values) as ONE request per field and word:
    ``{field_path, term, header, cells, run_ids, scope}``. A cell of Campaign Info is about the whole beamtime.
    ``cell_runs`` (c14h LOW-1): each cell's runs (adopt's ``cell_runs``, else every run of its entry), so a request kept
    for only some runs cites only their cells (:func:`cells_for_runs`); never kept, never shown."""
    out: dict[tuple, dict] = {}
    for c in cells:
        row = out.setdefault((c["path"], c["value"]), {"field_path": c["path"], "term": c["value"], "header": c.get("header"),
                                                       "cells": [], "run_ids": [], "scope": "run", "cell_runs": {}})
        runs = c.get("run_ids") or ([c["run_id"]] if c.get("run_id") else [])
        for cell in c.get("cells") or [c["cell"]]:
            if cell not in row["cells"]:
                row["cells"].append(cell)
            reach = row["cell_runs"].setdefault(cell, [])
            reach += [rid for rid in (c.get("cell_runs") or {}).get(cell, runs) if rid not in reach]
        for rid in runs:
            if rid not in row["run_ids"]:
                row["run_ids"].append(rid)
    for row in out.values():
        row["scope"] = "run" if row["run_ids"] else "experiment"
    return list(out.values())


def cells_for_runs(row: Mapping, run_ids: Sequence[str]) -> list[str]:
    """The cells of an :func:`off_list_requests` row that said its word for any of ``run_ids`` (a cell for no run, of
    Campaign Info, reaches them all). All of them for the row's own runs."""
    want = set(run_ids)
    reach = row.get("cell_runs") or {}
    return [c for c in row["cells"] if not reach.get(c) or want & set(reach[c])]


def _shown_row(row: Mapping) -> dict:
    """An :func:`off_list_requests` row as said and reported: without its ``cell_runs``."""
    return {k: v for k, v in row.items() if k != "cell_runs"}


def keep_off_list_cells(bundle: dict, cells: Sequence[Mapping], *, by: str | None, orcid: str | None, file: str,
                        kind: str, command: str) -> list[dict]:
    """Keep each off-list word of a sheet as a vocabulary request on ``bundle`` (in memory; the caller saves):
    the rows of :func:`off_list_requests`, each with its ``request_id`` and whether it is ``new``. A request kept
    earlier whose runs have since been answered with an allowed value says so (``answered_since``): the same sheet
    imported again is not the scientist saying their word again, so nothing is stamped (only ``--as-said`` is).

    c14g LOW-6: a sheet word that is NOT the same request as before (its cells or runs changed) is read against every
    request kept for the same field and word (:func:`same_word_requests`, as with no name given): runs answered since
    are not asked again (a fresh request time would read those answers as "before" and draft the word again), so the
    new request names only the runs still unanswered, and none is kept when every run is answered."""
    from . import mutations as M

    kept, earlier = [], []
    for full in off_list_requests(cells):
        row = _shown_row(full)
        before = same_word_requests(bundle, row)

        def ask(run_ids: Sequence[str]) -> dict:
            # c14h LOW-1: a request kept for some of the runs cites only the cells that said the word for them
            return dict(field_path=row["field_path"], term=row["term"], by=by, orcid=orcid, run_ids=run_ids,
                        scope=row["scope"], source={"kind": kind, "command": command, "file": file,
                                                    "cells": cells_for_runs(full, run_ids)})

        same = M.vocabulary_request_kept(bundle, **ask(row["run_ids"]))  # read only: nothing kept to be taken back
        # c15b L4: the same request (field, word, runs, file and cells) kept under another name is not kept twice; a
        # request keeps one name (the bundle schema has no place for a second), so the second is said, not stored
        other = M.vocabulary_request_kept(bundle, **ask(row["run_ids"]), anyone=True) if same is None and by else None
        if same is not None or other is not None:
            found = same if same is not None else other
            kept.append({**row, "request_id": found["request_id"], "new": False,
                         **({"kept_by": (other.get("requested_by") or {}).get("name")} if other is not None else {})})
            earlier.append((kept[-1], found))
            continue
        probe = dict(row)
        say_answered_since(bundle, [(probe, before)])
        since = probe.get("answered_since")
        if since is None:
            request, new = M.keep_vocabulary_request(bundle, **ask(row["run_ids"]))
            kept.append({**row, "request_id": request["request_id"], "new": new})
            continue
        rest = [r for r in row["run_ids"] if r not in set(since["run_ids"])]
        if since["every_run"] or not rest:
            kept.append({**row, "request_id": before[-1]["request_id"], "new": False, "answered_since": since})
            continue
        request, new = M.keep_vocabulary_request(bundle, **ask(rest))
        kept.append({**row, "run_ids": rest, "cells": cells_for_runs(full, rest), "request_id": request["request_id"],
                     "new": new, "answered_since": since})
    say_answered_since(bundle, [(row, [request]) for row, request in earlier])
    return kept


def say_answered_since(bundle: Mapping, pairs: Sequence[tuple[dict, Sequence[Mapping]]]) -> None:
    """Add ``answered_since`` to each sheet word ``row`` whose ``requests`` (the one kept earlier, or, with no name
    given, every request for the same field and word) were answered since with an allowed value
    (``propose_terms.request_answered_runs``): ``{runs, values, every_run, statement}``. ``every_run``: each live run
    the row names is answered, so the word is not drafted and nothing is to do unless the scientist wants it kept.
    Read only; nothing is stamped (a sheet read again is not the scientist saying their word again)."""
    from . import propose_terms as P

    pairs = [(row, reqs) for row, reqs in pairs if reqs]
    if not pairs:
        return
    answers = P.allowed_answers(bundle, [row["field_path"] for row, _ in pairs])
    live, log = P.live_run_ids(bundle), list(bundle.get("scientist_decisions") or ())
    for row, requests in pairs:
        wanted = [r for r in row.get("run_ids") or () if live is None or r in live] or (
            [] if row.get("run_ids") else [None])
        answered: dict[str | None, list] = {}
        still: set[str | None] = set()  # a run another request of theirs still asks the word for is not answered
        for request in requests:
            st = P.request_answered_runs(request, answers, live=live, log=log)
            for rid, vs in st["answered"].items():
                answered.setdefault(rid, []).extend(vs)
            still |= {*st["needed"], *st["before"], *st["same"], *st["unknown"]}
        answered = {r: v for r, v in answered.items() if r not in still}
        if len(requests) > 1 or row.get("run_ids") != list(requests[0].get("run_ids") or ()):
            answered = {r: v for r, v in answered.items() if r in wanted}  # only what this row asks about
        if not answered:
            continue
        values = P._distinct([v for vs in answered.values() for v in vs])
        row["answered_since"] = {
            "runs": sum(1 for r in answered if r is not None), "run_ids": [r for r in answered if r is not None],
            "values": values,
            **({"whole_beamtime": True} if None in answered else {}),
            "every_run": bool(wanted) and all(r in answered for r in wanted),
            "statement": (f"The sheet still says {row['term']!r} for {row['field_path']} on {P._reach(list(answered))}, "
                          f"but it was answered since with {P._shown(values)}; to keep the word, "
                          f"`isaac bundle decide ... --value \"{row['term']}\" --as-said`.")}


def same_word_requests(bundle: Mapping, row: Mapping) -> list[Mapping]:
    """Every vocabulary request the bundle keeps for ``row``'s field and word, whoever kept it and wherever."""
    return [r for r in bundle.get("vocabulary_requests") or () if isinstance(r, Mapping)
            and r.get("field_path") == row["field_path"] and r.get("term") == row["term"]]


def _request_sections(items: Sequence[Mapping], applied: bool, heading: str) -> list[str]:
    """The kept (or, in a preview, to-be-kept) requests under ``heading``, and apart from them, under their own
    heading, the words answered since for every run (c14 MED-1): not drafted, so never under "propose-terms can
    draft it"."""
    open_ = [r for r in items if not (r.get("answered_since") or {}).get("every_run")]
    done = [r for r in items if (r.get("answered_since") or {}).get("every_run")]
    out = []
    if open_:
        out += ["", heading, *_request_lines(open_, applied)]
    if done:
        out += ["", ANSWERED_SINCE_HEADING, *_request_lines(done, applied)]
    return out


#: The heading for sheet words already replaced with an allowed value (c14 MED-1, LOW-6).
ANSWERED_SINCE_HEADING = ("Answered since (your sheet still says the word, but it was replaced with an allowed value for "
                          "every run named; not drafted; nothing to do unless you want your own word kept):")


def _request_lines(items: Sequence[Mapping], applied: bool) -> list[str]:
    """One line per kept (or, in a preview, to-be-kept) vocabulary request."""
    from . import propose_terms as P

    out = []
    for r in items:
        reach = f"{len(r['run_ids'])} run(s)" if r["run_ids"] else "the whole beamtime"
        more = f" and {len(r['cells']) - _CELLS_SHOWN} more" if len(r["cells"]) > _CELLS_SHOWN else ""
        tag = (f"{r['request_id']}{'' if r.get('new') else ', kept earlier'}" if applied and r.get("request_id") else
               "would be kept")
        if r.get("kept_by") and applied:  # c15b L4: kept once, under the name that asked first
            tag += f" by {r['kept_by']}; the same cells, so not kept again (a request keeps one name)"
        same = P.equivalent_term(r["field_path"], r["term"])
        out.append(f"  {r['header']} {r['term']!r} for {reach} ({', '.join(r['cells'][:_CELLS_SHOWN])}{more}) [{tag}]"
                   + (f"; use `{same}` (an existing term)" if same else ""))
        if r.get("answered_since"):
            out.append(f"     {r['answered_since']['statement']}")
    return out


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

    requests: list[dict] = []
    if apply:
        with M.locked(Path(bundle_dir)):
            bundle = M.load(Path(bundle_dir))
            cells, report = run(bundle)
            requests = keep_off_list_cells(bundle, cells["off_list"], by=by, orcid=orcid, file=xlsx.name,
                                           kind="template_cell", command="bundle template import")
            if report["recorded_target_ids"] or any(r["new"] for r in requests):  # nothing new: not rewritten
                M.save_bundle(Path(bundle_dir), bundle)
    else:
        cells, report = run(current)  # in memory only; nothing is saved
        requests = [{**_shown_row(r), "request_id": None, "new": None} for r in off_list_requests(cells["off_list"])]
        if requests and current.get("vocabulary_requests"):
            # what --apply would say of a request kept earlier and answered since, read from a copy (nothing is saved)
            import copy

            would = keep_off_list_cells(copy.deepcopy(current), cells["off_list"], by=by, orcid=orcid, file=xlsx.name,
                                        kind="template_cell", command="bundle template import")
            for row, w in zip(requests, would):
                if w.get("answered_since"):
                    row["answered_since"] = w["answered_since"]
    return _as_text_dates({  # an invalid cell is shown as read, and a date cell reads as a datetime
        "applied": apply,
        "template": xlsx.name,
        "bundle_id": current["bundle_id"],
        "exported_utc": meta.get("exported_utc"),
        "cells_read": cells.get("read", 0),
        "decisions": report["decisions"],
        "replaces_or_contradicts_a_file_reading": report["contradictions"],
        "awaiting_ruling": cells["awaiting_ruling"] + report["awaiting_ruling"],
        # c14 MED-1: a Disagreements row left blank whose field a scientist's decision already answers: kept as recorded
        "disagreements_already_recorded": cells["already_recorded"],
        "recorded": len(report["recorded_target_ids"]) if apply else 0,
        "would_record": len(report["recorded_target_ids"]),
        "unchanged": len(report["unchanged_target_ids"]),
        "already_decided_same_value": report["already"],
        # c14i MED-1: a ruling that keeps the value already recorded, recorded again so it is tied to their sheet
        "rulings_tied_to_sheet": report["tied"],
        # c14k MED-1: a ruling that keeps the recorded value, on a workbook adopted before that value's run began: not
        # tied, nothing recorded; adopting the sheet again settles it
        "stale_rulings": report["stale"],
        # c15b M1, M2: the same, one entry per cell, each with ONE command for every target of the cell
        "stale_by_cell": report["stale_by_cell"],
        # c15b H2: rulings a Disagreements row asked for ("… rule which"), recorded over the value recorded now
        "rulings_over_the_value_recorded": report["over_recorded"],
        "invalid_cells": cells["invalid"],
        # an invalid cell refused ONLY because its word is not on the field's list: kept as a vocabulary request
        "vocabulary_requests": requests,
        "clashes": report["clashes"],
        "clashes_by_cell": report["clashes_by_cell"],
        "refused": report["refused"],
        "unmapped_columns": list(cells["unmapped"].values()),
        "recorded_nowhere": report["nowhere"],
        # a run's cell for a field this bundle asks once for the beamtime: the question that answers it
        "asked_beamtime_wide": report["asked_beamtime_wide"],
        # a ruling for a field asked once for the beamtime: recorded per run, for exactly the runs its row names
        "ruled_per_run": report["ruled_per_run"],
        # a reaction recorded here makes drive and catalysis required where nothing answers them yet
        "reaction_needs": report["reaction_needs"],
        "rows_refused": cells["rows_refused"],
        "extracted_values_left_alone": report["left_alone"],
        "campaign_not_filled": report["campaign_not_filled"],
        # a beamtime-wide answer recorded here that a group's own, differing answer keeps from its record
        "not_reached": report["not_reached"],
        # c15b L2: an --apply that records no decision says so, never "Recorded as scientist decisions"
        "statement": ("PREVIEW: nothing was written. Add --apply to record these decisions." if not apply else
                      "Recorded as scientist decisions (identity: self_reported_local_user, unverified)."
                      if report["recorded_target_ids"] else
                      "Nothing new recorded: no scientist decision" + (
                          "; the vocabulary request(s) above were kept." if any(r.get("new") for r in requests) else ".")),
    })


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


def _beamtime_lines(items: Sequence[Mapping]) -> list[str]:
    """One line per column, question and command: the cells, the question asking the field once for the
    beamtime, and the command that answers it (with the cell's value, when the cells agree)."""
    groups: dict[tuple, dict] = {}
    for x in items:
        key = (x["header"], x["target_field_path"], x["question_id"], x["answered"], x["command"], tuple(x.get("values_differ") or ()))
        g = groups.setdefault(key, {"cells": [], "runs": set()})
        cell = x["cell"].split(" via ", 1)[0]
        if cell not in g["cells"]:  # one cell (a Technique reached through many rows) is named once
            g["cells"].append(cell)
        if x.get("run_id"):
            g["runs"].add(x["run_id"])
    out = []
    for (header, path, qid, answered, command, differ), g in groups.items():
        cells = g["cells"]
        more = f" and {len(cells) - _CELLS_SHOWN} more" if len(cells) > _CELLS_SHOWN else ""
        runs = f"{len(g['runs'])} run(s) from " if g["runs"] else ""
        line = f"  {header} -> {path}: {runs}{len(cells)} cell(s) ({', '.join(cells[:_CELLS_SHOWN])}{more}); question {qid}"
        if differ:
            # never one command per value: the scientist says which value applies to the whole beamtime
            line += (f": these cells hold {len(differ)} different values ({', '.join(differ)}), so the scientist must say "
                     "which applies" + (", then change the answer" if answered else ", then answer it") + f": {command}")
        else:
            line += (" (answered; to change it)" if answered else "") + f": {command}"
        out.append(line)
    return out


def _invalid_lines(items: Sequence[Mapping]) -> list[str]:
    """Compact: per column, its allowed values ONCE, then each distinct value with a few of its cells.
    The allowed list is not repeated per cell (``--full`` and ``--json`` keep each cell's whole reason)."""
    by_header: dict[str, dict] = {}
    for x in items:
        reason = str(x.get("reason") or "")
        short, sep, allowed = reason.partition("; allowed: ")
        h = by_header.setdefault(str(x.get("header")), {"allowed": None, "values": {}})
        if sep and h["allowed"] is None:
            h["allowed"] = allowed
        h["values"].setdefault((repr(x.get("value")), short if sep else reason), []).append(str(x.get("cell")))
    out = []
    for header, h in by_header.items():
        out.append(f"  {header}" + (f" (allowed: {h['allowed']}):" if h["allowed"] else ":"))
        for (value, reason), cells in h["values"].items():
            more = f" and {len(cells) - _CELLS_SHOWN} more" if len(cells) > _CELLS_SHOWN else ""
            reason = reason.replace(f"{value} is not an allowed value", "not an allowed value")
            out.append(f"    {value} in {len(cells)} cell(s) ({', '.join(cells[:_CELLS_SHOWN])}{more}): {reason}")
    return out


def _tied_summary(rep: Mapping) -> str:
    """c14j LOW-1: the rulings tied to their sheet (their decisions are among those recorded), counted by ruling cell,
    however many targets it reaches (a Campaign Info ruling reaches every File List run). c14k LOW-5: two counts, each
    with its own unit; c14l LOW-3: said as part of the decisions recorded: "N decision(s) recorded, including 1 ruling
    cell that kept the same value and is now tied to your sheet (9 targets)"."""
    tied = rep.get("rulings_tied_to_sheet") or ()
    if not tied:
        return ""
    rulings = len({str(x["cell"]).split(" via ", 1)[0] for x in tied})
    one = rulings == 1
    if rep["applied"]:
        said = f"kept the same value and {'is' if one else 'are'} now tied to your sheet"
    else:
        said = f"{'keeps' if one else 'keep'} the same value and {'is' if one else 'are'} to be tied to your sheet"
    return (f", including {rulings} ruling cell{'' if one else 's'} that {said} "
            f"({len(tied)} target{'s' if len(tied) != 1 else ''})")


def _cell_lines(items: Sequence[Mapping], what: str = "clash") -> list[str]:
    """c15b M1: one line per cell of ``clashes_by_cell`` / ``stale_by_cell``: its targets and runs, how many clash (or,
    for ``stale_by_cell``, are not tied: ``what``), are held back with them or already hold the value, its own reason,
    and one command for every target of it."""
    out = []
    for x in items:
        n = x["clashes"]
        parts = [(f"{n} clash{'' if n == 1 else 'es'}" if what == "clash" else f"{n} not tied") if n else "", f"{x['held_back']} held back with them"
                 if x["held_back"] else "", f"{x['hold_value']} already hold the value" if x["hold_value"] else ""]
        parts = [p for p in parts if p]
        runs = f" on {x['runs']} run(s)" if x["runs"] else ""
        head = f"  {x['cell']} {x.get('header') or ''} = {x['value']!r}: {x['targets']} target(s){runs}"
        detail = f" ({', '.join(parts)})" if x["targets"] > 1 and parts else ""
        many = " && " in (x.get("command") or "")
        tail = (f". {'These commands record' if many else 'One command records'} it for all {len(x['target_ids'])} of them: "
                f"{x['command']}" if x.get("command")
                and len(x["target_ids"]) > 1 else f", or record this value directly: {x['command']}" if x.get("command")
                else "")
        out.append(f"{head}{detail}: {x['reason']}{tail}")
    return out


def _over_lines(items: Sequence[Mapping]) -> list[str]:
    """c15b H2: one line per ruling cell recorded over the value recorded now: the runs and what each held."""
    groups: dict[str, list[Mapping]] = {}
    for x in items:
        groups.setdefault(x["cell"], []).append(x)
    out = []
    for name, xs in groups.items():
        was = sorted({_shown(x["recorded_now"]) for x in xs})
        runs = len({x["run_id"] for x in xs if x.get("run_id")})
        out.append(f"  {name} {xs[0].get('header') or ''} = {xs[0]['value']!r}: {len(xs)} target(s)"
                   + (f" on {runs} run(s)" if runs else "")
                   + (f", replacing what is {xs[0]['said']}" if len(xs) == 1 else f", replacing {', '.join(was)} recorded now"))
    return out


def _campaign_not_filled_lines(rep: Mapping, *, full: bool) -> list[str]:
    """The report's lines for ``campaign_not_filled``: with ``full`` one per cell, each with its runs; else (r3a L5)
    the same runs (a rejected group's, say) said ONCE with the cells they miss, never once per cell."""
    if full:
        return [f"  {x['cell']} {x['target_field_path']}: {x['targets']} target(s) (runs {', '.join(map(str, x['run_ids']))}); "
                f"{x['reason']}" for x in rep["campaign_not_filled"]]
    by_runs: dict[tuple, list[Mapping]] = {}
    for x in rep["campaign_not_filled"]:
        by_runs.setdefault(tuple(x["run_ids"]), []).append(x)
    out = []
    for runs, xs in by_runs.items():
        n = int(xs[0].get("runs") or len(runs))
        out.append(f"  {n} run(s) ({', '.join(map(str, runs[:_CELLS_SHOWN]))}{', …' if n > _CELLS_SHOWN else ''}; --full "
                   "lists them per cell): " + "; ".join(f"{x['cell']} {x['target_field_path']}" for x in xs)
                   + f"; {xs[0]['reason']}")
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
    if rep.get("replaces_or_contradicts_a_file_reading"):
        add("")
        add("Replaces or contradicts a file reading (one line each; read each back before --apply):")
        for x in rep["replaces_or_contradicts_a_file_reading"]:
            run = f" {x['run_id']}" if x.get("run_id") else ""
            if x.get("outcome") == "awaiting_ruling":
                said = "not recorded: adopted from your sheet before this reading, awaiting your ruling"
            else:
                said = ("recorded" if rep["applied"] else "would be recorded") + ": you typed it"
            add(f"  {x['cell']}{run} {x['target_field_path']} = {x['value']!r} [{said}]: {'; '.join(x['readings'])}")
    if rep.get("awaiting_ruling"):
        add("")
        add("Disagreements awaiting your ruling (nothing recorded for them):")
        for x in rep["awaiting_ruling"]:
            run = f" {x['run_id']}" if x.get("run_id") else ""
            add(f"  {x['id'] or '(not yet on the Disagreements sheet)'} {x['cell']}{run} {x['header']}: theirs {x['their_value']!r}; {x['why']}")
    if rep.get("rulings_tied_to_sheet"):
        add("")
        # c14k MED-1: true with the same-value run: a later adopt of THIS sheet reads them as ruled until a different
        # value, a reject or a defer is recorded for them (another sheet's tie keeps the value, so it does not)
        add(("Rulings recorded" if rep["applied"] else "Rulings to be recorded") + " with the same value, now tied to "
            "your sheet (the value does not change; adopting this sheet again reads them as ruled until a different "
            "value, a reject or a defer is recorded):")
        for x in rep["rulings_tied_to_sheet"]:  # c15b L3: no decision id here (--json keeps it)
            run = f" {x['run_id']}" if x.get("run_id") else ""
            add(f"  {x['cell']}{run} {x['header']} = {x['value']!r}")
    if rep.get("rulings_over_the_value_recorded"):
        add("")
        # c15b H2: a ruling its row asked for, made against the value recorded now, replaces it without --supersede
        add(("Rulings recorded" if rep["applied"] else "Rulings to be recorded") + " over the value recorded now (the "
            "row named it and asked for your ruling; read each back):")
        for x in _over_lines(rep["rulings_over_the_value_recorded"]):
            add(x)
    if rep.get("stale_rulings"):
        add("")
        # c14l LOW-2: neutral; each line's reason says why (adopted before the value recorded now, a damaged hidden
        # sheet, a ruling --supersede does not record over a value it never saw)
        add("Cells not tied to your sheet (nothing is recorded for them and the value recorded now is kept; each line "
            "says why):")
        if full:
            for x in rep["stale_rulings"]:
                run = f" {x['run_id']}" if x.get("run_id") else ""
                add(f"  {x['cell']}{run} {x['header']} = {x['value']!r}: {x['reason']}")
        else:  # c15b M1: one line per cell, with one command for all its targets
            lines += _cell_lines(rep.get("stale_by_cell") or (), "not tied")
    if rep.get("disagreements_already_recorded"):
        add("")
        add("Disagreements already recorded (left blank, so the recorded value is kept; nothing new is recorded for them):")
        for x in rep["disagreements_already_recorded"]:
            add(f"  {x['id']} {x['cell']} {x['header']}: theirs {x['their_value']!r}; {x['recorded']['statement']}")
    in_full = [("Clashes (skipped)", "clashes"), ("Refused", "refused"), ("Rows refused", "rows_refused")]
    if not full and rep["clashes"]:
        # c15b M1: one line per cell (a whole-beamtime cell reaches every run), with one command for all its targets
        in_full.remove(("Clashes (skipped)", "clashes"))
        add("")
        add("Clashes (skipped; one line per cell, --json lists every target):")
        lines += _cell_lines(rep.get("clashes_by_cell") or ())
    if full:
        in_full.insert(0, ("Invalid cells (recorded as nothing)", "invalid_cells"))
        in_full.insert(3, ("Recorded nowhere (no target for that run/field)", "recorded_nowhere"))
    elif rep["invalid_cells"]:
        add("")
        add("Invalid cells (recorded as nothing):")
        lines += _invalid_lines(rep["invalid_cells"])
    if rep.get("vocabulary_requests"):
        lines += _request_sections(rep["vocabulary_requests"], rep["applied"],
                                   ("Kept" if rep["applied"] else "With --apply, kept") + " as vocabulary requests (not "
                                   "decisions, not values: each is a word its field's list lacks; `isaac bundle "
                                   "propose-terms` can draft it):")
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
    if rep.get("asked_beamtime_wide"):
        add("")
        add("Asked once for the whole beamtime (these cells are not recorded; the question's command answers it):")
        if full:
            for x in rep["asked_beamtime_wide"]:
                add(f"  {x['cell']} {x.get('run_id') or ''} {x['header']} = {x['value']!r}: {x['reason']}")
        else:
            lines += _beamtime_lines(rep["asked_beamtime_wide"])
    if rep.get("ruled_per_run"):
        add("")
        add("Rulings for a field asked once for the whole beamtime (recorded for exactly the runs each row names):")
        for x in rep["ruled_per_run"]:
            slots = f" ({x['slots_added']} answer slot(s) added)" if x["slots_added"] else ""
            add(f"  {x['cell']} {x['header']} -> {x['target_field_path']}: recorded per run for {x['runs']} run(s) that have no "
                f"target of their own for it{slots}. Question {x['question_id']} "
                + ("(answered) " if x["answered"] else "") + f"still covers {x['groups_left_to_the_question']} group(s) this "
                "import records nothing for; if its beamtime-wide answer differs from this ruling, these runs' groups get two "
                "values and fill nothing for it.")
    if rep.get("not_reached"):
        add("")
        add("Not reached by a beamtime-wide answer (the group keeps its own answer, so its record fills nothing for the "
            "field until the two agree):")
        for x in rep["not_reached"]:
            add(f"  {x['cell']} {x['target_field_path']} = {x['value']!r}: {x['reason']}")
    if rep.get("reaction_needs"):
        add("")
        add("Then required: " + _reaction_needs_line(rep["reaction_needs"], "recorded by this import"))
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
        for line in _campaign_not_filled_lines(rep, full=full):
            add(line)
    if rep["extracted_values_left_alone"]:
        add("")
        add("Extracted values left alone:")
        for x in rep["extracted_values_left_alone"]:
            add(f"  {x['cell']} {x['target_field_path']}: {x['candidates']} extracted value(s); {x['reason']}")
    add("")
    # c14m MED-1: "not tied … (nothing recorded)" counts only the cells that recorded nothing (c15a LOW-2: rulings and adopted cells alike)
    unrecorded = ({str(x["cell"]).split(" via ", 1)[0] for x in rep.get("stale_rulings") or ()}
                  - {str(d["cell"]).split(" via ", 1)[0] for d in rep.get("decisions") or ()})
    add(
        f"Summary: {rep['cells_read']} cells read; {rep['recorded'] if rep['applied'] else rep['would_record']} decision(s) "
        f"{verb}{_tied_summary(rep)}; {rep['unchanged']} unchanged; {len(rep['already_decided_same_value'])} decision(s) (from "
        f"{len({str(x['cell']).split(' via ', 1)[0] for x in rep['already_decided_same_value']})} cell(s)) already recorded; "
        f"{len(rep['invalid_cells'])} invalid; {_clash_count(rep['clashes'])}; {len(rep['refused'])} refused; "
        f"{sum(len(u['cells']) for u in rep['unmapped_columns'])} cell(s) in {len(rep['unmapped_columns'])} unmapped column(s); "
        f"{len(rep['recorded_nowhere'])} recorded nowhere; {len(rep['rows_refused'])} row(s) refused"
        + (f"; {len({x['run_id'] for x in rep['asked_beamtime_wide']})} run(s) from "
           f"{len({x['cell'].split(' via ', 1)[0] for x in rep['asked_beamtime_wide']})} cell(s) asked once for the whole beamtime (its question answers them)"
           if rep.get("asked_beamtime_wide") else "")
        + (f"; {len(rep['replaces_or_contradicts_a_file_reading'])} replace or contradict a file reading"
           if rep.get("replaces_or_contradicts_a_file_reading") else "")
        + (f"; {len(rep['awaiting_ruling'])} disagreement(s) awaiting a ruling" if rep.get("awaiting_ruling") else "")
        + (f"; {len(unrecorded)} cell(s) not tied to your sheet (nothing recorded)" if unrecorded else "")
        + (f"; {len(rep['disagreements_already_recorded'])} disagreement(s) already recorded (blank: kept)"
           if rep.get("disagreements_already_recorded") else "")
        + (f"; {len({x['group_id'] for x in rep['not_reached']})} group(s) not reached by a beamtime-wide answer"
           if rep.get("not_reached") else "")
        + "."
    )
    add(rep["statement"])
    if not full:
        add("(--full lists every decision and cell; --json prints the whole report.)")
    return "\n".join(lines)


# --- adopt: the scientist's own filled copy of ISAAC's template ------------------------------------
#
# ``isaac bundle template adopt <bundle> <their.xlsx> --out <file.xlsx>``. A scientist who already filled
# ISAAC's metadata template (no ``_isaac`` sheet, File List keyed by their own folder names) should not
# retype it. Adopt writes the bundle's own template (:func:`export_template`) and copies THEIR value into
# an answer cell only when no file reading contradicts it; every value a reading contradicts, or that the
# field does not take, goes to the Disagreements sheet with an empty "Your ruling" column instead, so
# nothing that contradicts a file is imported until the scientist rules. ``template import`` then reads
# the answer cells and the rulings, and nothing else.

#: Their header (whitespace-collapsed, case-folded) -> this template's File List column, beyond an exact
#: header. ISAAC's template keys File List by "File Name"; filled copies key it by their folders.
THEIR_FILE_HEADER_ALIASES: Mapping[str, str] = {"folder name": "File Name", "sample": "Sample Name"}
_TAKEN_NAME_SUFFIX = "_dir"

#: ISAAC's BLANK metadata template (``ISAAC_Metadata_Template.xlsx`` as it is handed out) holds these example
#: values in Campaign Info (column B, by the label in column A) and these two example Configurations rows
#: (by header). Import never mistakes it for answers because it has no ``_isaac`` sheet (:func:`_marker`);
#: adopt reads exactly such workbooks, so it recognises the blank by these values: a copy whose Campaign
#: Info and Configurations still hold exactly them, and nothing else, is the blank, whatever its File List
#: holds (a later blank may ship example rows there).
BLANK_TEMPLATE_CAMPAIGN_EXAMPLES: Mapping[str, Any] = {
    "Facility Name": "SSRL", "Organization": "SLAC National Accelerator Laboratory", "Beamline/Instrument": "15-2",
    "Start Date": "2026-01-01", "Proposal ID": None}
BLANK_TEMPLATE_CONFIG_EXAMPLES: tuple[Mapping[str, Any], ...] = (
    {"Config ID": "Config_A", "Technique": "XAS", "Mode": "Fluorescence", "Primary Signal Channel": "VortDT",
     "Normalization Channel": "I0", "Detectors": "Canberra 100", "Energy Calibration": "Cu-Foil deriv=0 -> 8979eV",
     "Beamline Setup": "Standard Setup"},
    {"Config ID": "Config_B", "Technique": "XAS", "Mode": "Transmission", "Primary Signal Channel": "I1",
     "Normalization Channel": "I0", "Detectors": "Ion Chambers", "Energy Calibration": "Cu-Foil deriv=0 -> 8979eV",
     "Beamline Setup": "Changed detector"},
)


def _norm_header(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _blank_value(value: Any) -> Any:
    """A cell as the blank's example values are compared: text trimmed, a date as its ISO day, empty = None."""
    from datetime import date

    if isinstance(value, datetime) and value.time() == datetime.min.time():
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value.strip() or None
    return value


def _still_the_blank(wb) -> bool:
    """Campaign Info and Configurations hold exactly the blank's example values and nothing else."""
    from collections import Counter

    def pairs(items):
        return {(_norm_header(k), _blank_value(v)) for k, v in items if _blank_value(v) is not None}

    wc = wb[SHEET_CAMPAIGN]
    campaign = pairs((wc.cell(row=r, column=1).value, wc.cell(row=r, column=2).value) for r in range(2, wc.max_row + 1))
    if campaign != pairs(BLANK_TEMPLATE_CAMPAIGN_EXAMPLES.items()):
        return False
    wcf = wb[SHEET_CONFIG]
    header = [c.value for c in wcf[1]]
    rows = Counter(frozenset(p) for row in wcf.iter_rows(min_row=2) if (p := pairs(zip(header, (c.value for c in row)))))
    return rows == Counter(frozenset(pairs(r.items())) for r in BLANK_TEMPLATE_CONFIG_EXAMPLES)


def _as_text_dates(obj: Any) -> Any:
    """``obj`` with every date or datetime as its ISO text (a midnight datetime as its day), so the report
    prints as JSON. Nothing else changes."""
    from datetime import date

    if isinstance(obj, Mapping):
        return {k: _as_text_dates(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_as_text_dates(v) for v in obj]
    if isinstance(obj, date):
        return _blank_value(obj)
    return obj


def _refuse_unofficial(name: str, why: str) -> TemplateRefused:
    return TemplateRefused(
        f"{name} is not a filled copy of ISAAC's metadata template: {why}. `template adopt` reads only that template "
        f"(sheets {SHEET_CAMPAIGN!r}, {SHEET_CONFIG!r} and {SHEET_FILES!r}; {CAMPAIGN_TITLE!r} in {SHEET_CAMPAIGN} A1; "
        "a File List keyed by 'File Name' or 'Folder Name'). Nothing was written.", code=EXIT_INPUT_REFUSED)


def _their_sheet(wb, name: str) -> dict:
    """The parts of a filled official template adopt reads, or a plain refusal."""
    if SHEET_MARKER in wb.sheetnames:
        raise TemplateRefused(
            f"{name} has an `_isaac` sheet: it is a template ISAAC exported for a bundle, not the scientist's own "
            f"copy. Read it with `isaac bundle template import <bundle> {name} --by \"<name>\"`. Nothing was written.",
            code=EXIT_INPUT_REFUSED)
    missing = [s for s in (SHEET_CAMPAIGN, SHEET_CONFIG, SHEET_FILES) if s not in wb.sheetnames]
    if missing:
        raise _refuse_unofficial(name, f"it has no {', '.join(repr(m) for m in missing)} sheet")
    if str(wb[SHEET_CAMPAIGN]["A1"].value or "").strip() != CAMPAIGN_TITLE:
        raise _refuse_unofficial(name, f"{SHEET_CAMPAIGN} A1 reads {wb[SHEET_CAMPAIGN]['A1'].value!r}")
    wf = wb[SHEET_FILES]
    header = [c.value for c in wf[1]]
    if not header or _norm_header(header[0]) not in ("file name", "folder name"):
        raise _refuse_unofficial(name, f"File List A1 reads {header[0] if header else None!r}")
    names = [(r, wf.cell(row=r, column=1).value) for r in range(2, wf.max_row + 1)]
    names = [(r, str(v).strip()) for r, v in names if v is not None and str(v).strip()]
    if not names:
        raise TemplateRefused(
            f"{name} is ISAAC's blank metadata template (its File List names no file or folder): its other cells are "
            "the template's example values, not anyone's answers. Nothing was written.", code=EXIT_INPUT_REFUSED)
    if _still_the_blank(wb):
        raise TemplateRefused(
            f"{name} is ISAAC's blank metadata template: its Campaign Info and Configurations hold exactly the "
            "template's example values (Facility Name 'SSRL', Beamline/Instrument '15-2', Start Date 2026-01-01, "
            "Config_A and Config_B), so its File List rows are taken as examples too, not anyone's answers. If you "
            "did fill it, put your own values in Campaign Info and Configurations (or clear the examples) and adopt "
            "it again. Nothing was written.", code=EXIT_INPUT_REFUSED)
    return {"files": wf, "header": header, "names": names}


def _match_runs(bundle: Mapping, their_name: str) -> list[str]:
    """The run ids a File List row names: a run whose file sits DIRECTLY in a folder of that name, or whose
    file or stem IS that name (``<name>_dir`` also names the run ``<name>``: SPEC keeps the scan file beside
    its ``_dir`` folder). An ancestor folder (``raw``, a day's folder above the runs' own) names no run, so a
    row never takes every run below it. Exact names only: nothing is case-folded or guessed."""
    want = {their_name}
    if their_name.endswith(_TAKEN_NAME_SUFFIX) and len(their_name) > len(_TAKEN_NAME_SUFFIX):
        want.add(their_name[: -len(_TAKEN_NAME_SUFFIX)])
    sources = {s["source_id"]: s for s in bundle["sources"]}
    out = []
    for run in bundle["runs"]:
        rel = (sources.get(run.get("acquisition_source_id")) or {}).get("relative_path") or ""
        parts = [p for p in rel.split("/") if p]
        last = parts[-1] if parts else ""
        if ((len(parts) > 1 and parts[-2] == their_name) or rel in want or last in want or str(run.get("stem") or "") in want
                or (last.rsplit(".", 1)[0] in want if "." in last else False)):
            out.append(run["run_id"])
    return out


class _Adopter:
    """Reads their sheet against one bundle. Every reading compared is a file's (a parser value, a
    file-name token, an AI reading of a file); an AI reading OF THEIR SHEET is their sheet, so it is
    never compared."""

    def __init__(self, bundle: Mapping, index: _Index, rules: Mapping, their_file: str):
        self.bundle, self.index, self.rules, self.their_file = bundle, index, rules, their_file
        self.runs = {r["run_id"]: r for r in bundle["runs"]}
        self.ai_of: dict[tuple[str, str], list[dict]] = {}
        for i in bundle.get("ai_interpretations") or ():
            t = i.get("target") or {}
            self.ai_of.setdefault((str(t.get("kind")), str(t.get("id"))), []).append(i)
        self.exposed: list[tuple[str, str]] = []
        self.sheet_readings_skipped = 0

    def _is_their_sheet(self, i: Mapping) -> bool:
        paths = [i.get("source_path")] + [(self.index.sources.get(r.get("source_id") or "") or {}).get("relative_path")
                                          for r in i.get("source_refs") or ()]
        return any(p and Path(str(p)).name == self.their_file for p in paths)

    def _comparable(self, value: Any, path: str) -> Any:
        rule = self.rules.get(path) or {}
        if rule.get("numeric"):
            if isinstance(value, str) and _NUMBER_RE.match(value.strip()):
                return float(value.strip())
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        return value.strip() if isinstance(value, str) and value.strip() else None

    def readings(self, run_id: str | None, path: str) -> list[dict]:
        """``[{value, kind, source, target}]``: what the files say for one run (or, ``run_id=None``, for
        the whole beamtime), one entry per distinct value and source."""
        if run_id is None:
            cands = self.index.cands_by_path.get(path, [])
            missing = self.index.missing_by_path.get(path, [])
        else:
            cands = self.index.cands_by_run.get((run_id, path), []) + (
                self.index.cands_by_run.get((None, path), []) if path == "system.technique" else [])
            missing = self.index.missing_by_run.get((run_id, path), [])
        out: dict[tuple, dict] = {}
        for c in cands:
            if c["value"] is None:
                continue
            ev = next((e for e in c["evidence"] if e["method"] != "ai_interpretation"), None)
            out.setdefault((repr(c["value"]), "extracted"), {
                "value": c["value"], "kind": "extracted", "source": f"extracted from {_ev_where(self.index, ev)}",
                "target": ("candidate", c["candidate_id"])})
        if run_id is not None:
            for t in name_token_readings(run_names(self.bundle, self.runs[run_id]), path):
                out.setdefault((repr(float(t["value"])), "token"), {
                    "value": t["value"], "kind": "file_name_token", "source": f"file name token {t['token']} in {t['name']}"})
        if run_id is not None and path == POTENTIAL_PATH:
            # c16c: a potential the run's scan header states is a file reading too; a line a candidate already holds
            # (its value is the extracted reading above) is not listed twice
            held = {(e.get("relative_path"), e.get("locator")) for c in cands if c["value"] is not None for e in c["evidence"]}
            for h in header_potential_readings(self.bundle, self.runs[run_id]):
                if (h["relative_path"], h["locator"]) in held:
                    continue
                out.setdefault((repr(float(h["value"])), "scan_header"), {
                    "value": h["value"], "kind": "scan_header",
                    "source": f"scan header {h['literal']} at {h['locator']} of {h['relative_path']}"})
            # r3a H2: a potential a value-less header line only MENTIONS (``0Vrhe``) is compared too, each one
            # (never offered: no candidate holds it as a value)
            for h in header_potential_mentions(self.bundle, self.runs[run_id]):
                for m in h["mentions"]:
                    out.setdefault((repr(float(m["volts"])), "scan_header_mention"), {
                        "value": m["volts"], "kind": "scan_header_mention", "mention": m["literal"],
                        "source": (f"scan header, which writes {m['literal']!r} in its line {h['line']!r} at "
                                   f"{h['locator']} of {h['relative_path']} (a mention: no value is read from it)")})
        targets = [("candidate", c["candidate_id"]) for c in cands] + [("missing_value", m["value_id"]) for m in missing]
        for kind, tid in targets:
            for i in self.ai_of.get((kind, tid), []):
                if self._is_their_sheet(i):
                    self.sheet_readings_skipped += 1
                    continue
                value = self._comparable(i.get("proposed_value"), path)
                if value is None and path == ELECTROLYTE_CONC_PATH and electrolyte_statement_parts(i.get("proposed_value")):
                    value = i["proposed_value"].strip()  # the whole statement, compared by its concentration part
                if value is None:
                    continue
                where = i.get("source_path") or (self.index.sources.get(((i.get("source_refs") or [{}])[0]).get("source_id") or "") or {}).get("relative_path")
                source = f"AI reading ({(i.get('model') or {}).get('model_id')}) of {where or '(source)'} @ {i.get('excerpt_locator') or '(no locator)'}"
                out.setdefault((repr(value), source), {"value": value, "kind": "ai_reading", "source": source})
        return list(out.values())

    def _contradicts(self, r: Mapping, path: str, value: Any) -> bool:
        """Does reading ``r`` contradict ``value``? The electrolyte is one statement in the files ("0.5 M H2SO4")
        and two cells here, so a name equal to its name part, or a concentration equal to its concentration part,
        agrees; anything else about a name or concentration is a contradiction."""
        parts = electrolyte_statement_parts(r["value"]) if path in (ELECTROLYTE_NAME_PATH, ELECTROLYTE_CONC_PATH) else None
        if parts is not None:
            if path == ELECTROLYTE_NAME_PATH:
                return not (isinstance(value, str) and " ".join(value.split()) == parts[0])
            return not _agrees(parts[1], value)
        v = self._comparable(r["value"], path)
        return v is not None and not _agrees(v, value)

    def against(self, value: Any, run_id: str | None, path: str) -> list[dict]:
        """The readings that CONTRADICT ``value``. A candidate shown here is an exposure."""
        return self.compare(value, run_id, path)[0]

    def compare(self, value: Any, run_id: str | None, path: str) -> tuple[list[dict], list[dict]]:
        """``(contradicting, agreeing)``: EVERY reading of ``path`` for the run, split by whether it contradicts
        ``value`` (a Disagreements row lists both, so the scientist rules seeing all of them). A reading with no
        comparable value is in neither. A contradicting candidate is an exposure (it is always shown); an agreeing
        one is exposed by :meth:`expose` where it is shown."""
        pool = self.readings(run_id, path)
        if path in (ELECTROLYTE_NAME_PATH, ELECTROLYTE_CONC_PATH):
            # the statement is one reading of both cells, whichever of the two fields it was recorded on
            other = ELECTROLYTE_CONC_PATH if path == ELECTROLYTE_NAME_PATH else ELECTROLYTE_NAME_PATH
            seen = {(repr(r["value"]), r["source"]) for r in pool}
            pool += [r for r in self.readings(run_id, other)
                     if electrolyte_statement_parts(r["value"]) and (repr(r["value"]), r["source"]) not in seen]
        bad, good = [], []
        for r in pool:
            if self._contradicts(r, path, value):
                bad.append(r)
            elif self._comparable(r["value"], path) is not None or (
                    path in (ELECTROLYTE_NAME_PATH, ELECTROLYTE_CONC_PATH) and electrolyte_statement_parts(r["value"])):
                good.append(r)
        self.expose(bad)
        return bad, good

    def expose(self, readings: Sequence[Mapping]) -> None:
        for r in readings:
            if r.get("target") and r["target"] not in self.exposed:
                self.exposed.append(r["target"])


def _compared_values(ad: "_Adopter", readings: Sequence[Mapping], path: str) -> tuple[str, ...]:
    """The distinct values ``readings`` hold, as compared (``_comparable``: ``'0'`` and ``0.0`` are one), each a
    ``repr``. A reading with no comparable form keeps its own value; ``0`` / ``0.0`` is a value (L3, c6-r)."""
    return tuple(sorted({repr(r["value"] if (cv := ad._comparable(r["value"], path)) is None else cv) for r in readings}))


def _shown_reading(r: Mapping) -> str:
    return f"{_shown(r['value'])} ({r['source']})"


def _refs_shown(refs: Sequence[str], n: int = _CELLS_SHOWN, *, noun: str = "cells") -> str:
    more = f" and {len(refs) - n} more ({len(refs)} {noun})" if len(refs) > n else ""
    return ", ".join(refs[:n]) + more


def _loose(text: Any) -> str:
    """A value as an unread column is matched to an allowed one: case-folded, every non-alphanumeric dropped
    (``insitu``, ``in-situ`` and ``In Situ`` are all ``in_situ``'s ``insitu``)."""
    return re.sub(r"[^0-9a-z]", "", str(text).casefold())


def _unread_hint_text(h: Mapping, runs: int) -> str:
    rows = f" on {h['rows']} of these {runs} run(s)" if runs and h["rows"] < runs else ""
    return (f"your sheet's column {h['column']} ({h['header']!r}) says {h['value']!r} (= `{h['allowed_value']}`){rows} "
            "— a hint from a column adopt does not read, never adopted")


def _adopt_name_only_reason(value: Any) -> str | None:
    """Why an Electrolyte value that also states a concentration is not adopted, saying where each part of a
    ruling goes on THIS path: the scientist types only rulings here, so the name goes in "Your ruling" and the
    concentration in "Your ruling: concentration (M)". ISAAC never splits it for them."""
    if electrolyte_name_problem(value) is None:
        return None
    got = electrolyte_statement(value)
    stated = f"{got['number']} {got['unit']}" if got else "a concentration"
    return (f"name only: {value!r} also states a concentration ({stated}); rule with the NAME in 'Your ruling' and the "
            f"concentration in mol/L in '{DISAGREE_HEADERS[9]}' (column {DISAGREE_CONC_COLUMN}), both for this row's runs")


def adopt_template(bundle_dir: Path, their_xlsx: Path, out: Path, *, force: bool = False, suggestions: bool = True,
                   by: str | None = None, orcid: str | None = None) -> dict:
    """Write ``out``: the bundle's template with the scientist's own values where no file contradicts
    them, and a Disagreements sheet for every one a file contradicts or the field does not take. A value
    the field refuses ONLY because it is not on its list is also kept as a vocabulary request in ``by``'s
    name, recorded before the file is written; without ``by`` nothing is kept, and the result says so
    (``vocabulary_requests_not_kept``: "no name given")."""
    from . import mutations as M

    if by is not None and (problem := B.decider_name_problem(by)):
        raise TemplateRefused(f"--by must be the name of the person whose sheet it is (this one {problem}).", code=EXIT_USAGE)
    if orcid is not None and not M.ORCID_RE.fullmatch(orcid):
        raise TemplateRefused("--orcid must look like 0000-0000-0000-0000 (last character may be X).", code=EXIT_USAGE)
    their_xlsx = Path(their_xlsx).expanduser()
    wb_theirs = _read_workbook(their_xlsx)
    theirs = _their_sheet(wb_theirs, their_xlsx.name)
    their_file = their_xlsx.name

    def fill(*, wb, bundle, rows, index, rules, marker) -> dict:
        from openpyxl.comments import Comment
        from openpyxl.styles import PatternFill

        flag = PatternFill("solid", fgColor="FFE699")
        ad = _Adopter(bundle, index, rules, their_file)
        our_row = {r["run_id"]: i for i, r in enumerate(rows, start=2)}
        file_col = {c.header: j for j, c in enumerate(FILE_COLUMNS, start=1)}
        result: dict[str, Any] = {"their_file": their_file, "cells_adopted": 0, "disagreements": [], "not_adopted": [],
                                  "unmatched_rows": [], "unmatched_runs": [], "rows_matched": 0, "runs_matched": 0,
                                  "runs_on_several_rows": [], "rows_reaching_several_runs": [], "runs_outside_live_groups": [],
                                  "row_buckets": {"matched": 0, "shared_runs_only": 0, "outside_live_groups_only": 0, "no_run": 0},
                                  "their_columns_not_read": [],
                                  "their_columns_mapped": []}
        adopted_cells: list[tuple[str, str]] = []  # (our cell, their cell)
        # c14n MED-2: what each adopted answer cell reaches (its field, scope and runs), for its governing decisions
        adopted_reach: dict[str, dict] = {}
        adopted_paths: set[tuple[str | None, str]] = set()  # (run_id, path) of each adopted answer cell
        groups: dict[tuple, dict] = {}  # disagreement key -> entry

        def disagree(key, **entry):
            g = groups.get(key)
            if g is None:
                g = groups[key] = {**entry, "their_cells": [], "runs": [], "answer_cells": [], "readings": [],
                                   "unread_hints": {}, "cell_runs": {}}
            for k in ("their_cells", "runs", "answer_cells", "readings"):
                for v in entry.get("_" + k, ()):
                    if v not in g[k]:
                        g[k].append(v)
            for cell in entry.get("_their_cells", ()):  # c14h LOW-1: which runs each of their cells said it for
                reach = g["cell_runs"].setdefault(cell, [])
                reach += [rid for rid in entry.get("_runs", ()) if rid not in reach]
            for h in entry.get("_unread_hints", ()):
                g["unread_hints"][h] = g["unread_hints"].get(h, 0) + 1
            return g

        wf_theirs = theirs["files"]

        def unread_hints(their_row: int | None, allowed: Sequence | None) -> list[tuple]:
            """M4: ``[(column, header, their text, the allowed value it is)]`` — a column of THEIR row adopt does not
            read that holds, loosely written (``insitu``), one of the field's allowed values (``in_situ``). A hint
            beside the row, never adopted."""
            if their_row is None or not allowed:
                return []
            out = []
            for c in result["their_columns_not_read"]:
                text = wf_theirs[f"{c['column']}{their_row}"].value
                if not isinstance(text, str) or not text.strip():
                    continue
                match = next((a for a in allowed if isinstance(a, str) and _loose(a) == _loose(text)), None)
                if match is not None:
                    out.append((c["column"], c["header"], text.strip(), match))
            return out

        def judge(sheet, our_ref, col: Column, raw: Any, their_ref: str, run_id: str | None, their_row: int | None = None):
            """Adopt one of their cells into ``our_ref``, or record why not. ``run_id=None``: Campaign Info."""
            path = col.path
            rule = rules.get(path or "")
            if isinstance(raw, str) and raw.startswith("="):
                value, why = None, "a formula, not a value"
            else:
                value, why = _parse(raw, rule)
            kind = None
            if not why and path == ELECTROLYTE_NAME_PATH:
                why = _adopt_name_only_reason(value)
                kind = "name_only" if why else None
            runs = [run_id] if run_id else []
            target_cell = _cell_ref(sheet, our_ref)
            if why:
                allowed = rule.get("allowed") if rule else None
                not_allowed = bool(allowed) and isinstance(raw, str) and raw.strip() not in allowed
                kind = kind or ("not_allowed" if not_allowed else "invalid")
                shown_reason = "not an allowed value" if not_allowed else why.partition("; allowed: ")[0]
                disagree((kind, sheet, col.header, repr(raw)), kind=kind, sheet=sheet, header=col.header, path=path,
                         their_value=raw, reason=shown_reason, allowed=allowed if not_allowed else None,
                         scope="experiment" if run_id is None else "run",
                         _their_cells=[their_ref], _runs=runs, _answer_cells=[target_cell],
                         _unread_hints=unread_hints(their_row, allowed) if not_allowed else ())
                return
            bad, good = ad.compare(value, run_id, path)
            # H1: a Campaign Info beamline (or facility acronym) naming another one than the folder's name or the
            # acquisition system's — a hint, not a reading, but never adopted over it: the scientist rules
            hinted = facility_hint_lines(bundle, path, value) if run_id is None else []
            if bad or hinted:
                # one row per cell of theirs and the VALUES the files read (a scan file and its calibration
                # file under one folder name are one disagreement); every source is kept, the agreeing ones too
                kind = "file_reading" if bad else "hint"
                ad.expose(good)
                key = (kind, sheet, col.header, their_ref, _compared_values(ad, bad, path))
                disagree(key, kind=kind, sheet=sheet, header=col.header, path=path, their_value=value,
                         reason="a file reading says otherwise" if bad else "a hint names another one",
                         scope="experiment" if run_id is None else "run",
                         _readings=[f"differs: {_shown_reading(r)}" for r in bad] + hinted
                         + [f"agrees: {_shown_reading(r)}" for r in good],
                         _their_cells=[their_ref], _runs=runs, _answer_cells=[target_cell])
                return
            ws = wb[sheet]
            ws[our_ref] = value
            ws[our_ref].comment = Comment(f"From your sheet: {their_file} {their_ref}", "ISAAC")
            adopted_cells.append((target_cell, their_ref))
            if run_id is None:  # c15b M5: a Campaign Info answer reaches every File List run, on their rows or not
                result["campaign_cells_adopted"] = result.get("campaign_cells_adopted", 0) + 1
            adopted_reach[target_cell] = {"path": path, "scope": "run" if run_id else "experiment", "runs": runs}
            adopted_paths.add((run_id, path))
            result["cells_adopted"] += 1

        # Campaign Info: by label, whatever row it is on
        wc = wb_theirs[SHEET_CAMPAIGN]
        campaign_by_label = {}
        for col in CAMPAIGN_FIELDS:
            for label in (col.header, *col.aliases):
                campaign_by_label[_norm_header(label)] = col
        for r in range(1, wc.max_row + 1):
            label, raw = wc.cell(row=r, column=1).value, wc.cell(row=r, column=2).value
            col = campaign_by_label.get(_norm_header(label)) if label else None
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                continue
            their_ref = _cell_ref(SHEET_CAMPAIGN, f"B{r}")
            if col is None or col.path is None:
                result["not_adopted"].append({"cell": their_ref, "header": str(label), "value": raw,
                                              "reason": (f"no official field ({col.why_none})" if col else
                                                         "no row of this name in ISAAC's template")})
                continue
            if index.status(col)[0] != "mapped":
                result["not_adopted"].append({"cell": their_ref, "header": col.header, "value": raw,
                                              "reason": index.status(col)[1]})
                continue
            our_ref = f"B{CAMPAIGN_FIRST_ROW + list(CAMPAIGN_FIELDS).index(col)}"
            judge(SHEET_CAMPAIGN, our_ref, col, raw, their_ref, None)

        # Configurations: Config ID and Technique
        wcf = wb_theirs[SHEET_CONFIG]
        cfg_header = {_norm_header(c.value): j for j, c in enumerate(wcf[1], start=1) if c.value}
        configs: dict[str, dict] = {}
        if "config id" in cfg_header:
            for r in range(2, wcf.max_row + 1):
                cid = wcf.cell(row=r, column=cfg_header["config id"]).value
                if cid is None or not str(cid).strip():
                    continue
                tech = wcf.cell(row=r, column=cfg_header["technique"]).value if "technique" in cfg_header else None
                configs[str(cid).strip()] = {"technique": tech,
                                             "ref": _cell_ref(SHEET_CONFIG, f"{_letter(cfg_header.get('technique', 2))}{r}")}
        tech_col = next(c for c in CONFIG_COLUMNS if c.header == "Technique")
        wcfg = wb[SHEET_CONFIG]
        for i, (cid, cfg) in enumerate(configs.items(), start=2):
            wcfg.cell(row=i, column=1, value=cid)
            cfg["our_row"] = i

        # File List: their columns -> ours
        mapped: dict[int, Column] = {}
        seen_cols: dict[str, int] = {}
        for j, h in enumerate(theirs["header"], start=1):
            if j == 1 or h is None or not str(h).strip():
                continue
            nh = _norm_header(h)
            target = next((c for c in FILE_COLUMNS if _norm_header(c.header) == nh), None)
            via_alias = False
            if target is None and nh in THEIR_FILE_HEADER_ALIASES:
                target = next(c for c in FILE_COLUMNS if c.header == THEIR_FILE_HEADER_ALIASES[nh])
                via_alias = True
            if target is None or target.header == "File Name":
                result["their_columns_not_read"].append({"column": _letter(j), "header": str(h).strip(),
                                                         "reason": "no column of this name in ISAAC's template"})
                continue
            if target.header in seen_cols:
                result["their_columns_not_read"].append({"column": _letter(j), "header": str(h).strip(),
                                                         "reason": f"column {_letter(seen_cols[target.header])} already maps to {target.header!r}"})
                continue
            if target.path is None and target.header != "Config ID":
                result["their_columns_not_read"].append({"column": _letter(j), "header": str(h).strip(),
                                                         "reason": f"no official field ({target.why_none})"})
                continue
            seen_cols[target.header] = j
            mapped[j] = target
            result["their_columns_mapped"].append({"column": _letter(j), "header": str(h).strip(), "to": target.header,
                                                   **({"by_alias": True} if via_alias else {})})

        # rows -> runs
        live = set(our_row)
        rows_of_run: dict[str, list[int]] = {}
        runs_of_row: dict[int, list[str]] = {}
        for r, name in theirs["names"]:
            ids = _match_runs(bundle, name)
            runs_of_row[r] = ids
            for rid in ids:
                rows_of_run.setdefault(rid, []).append(r)
        # a row that reaches several runs (a scan beside its ``_dir`` calibration file, or a folder of runs) is
        # said with its count: one value of theirs goes to each of them
        result["rows_reaching_several_runs"] = [{"row": _cell_ref(SHEET_FILES, f"A{r}"), "name": name, "runs": len(runs_of_row[r]),
                                                 "run_ids": runs_of_row[r]} for r, name in theirs["names"] if len(runs_of_row[r]) > 1]
        several = {rid for rid, rs in rows_of_run.items() if len(rs) > 1}
        result["runs_on_several_rows"] = [{"run_id": rid, "rows": [_cell_ref(SHEET_FILES, f"A{r}") for r in rows_of_run[rid]],
                                           "reason": "more than one of your File List rows names this run, so neither is adopted for it"}
                                          for rid in sorted(several)]
        for r, name in theirs["names"]:
            ids = runs_of_row[r]
            here = [rid for rid in ids if rid in live and rid not in several]
            outside = [rid for rid in ids if rid not in live]
            if outside:
                result["runs_outside_live_groups"].append({"row": _cell_ref(SHEET_FILES, f"A{r}"), "name": name, "run_ids": outside})
            # EVERY ROW IN EXACTLY ONE BUCKET, the most specific that fits: a live run of its own, else only live runs
            # other rows also name, else only runs in no live record group, else no run
            bucket = ("matched" if here else "shared_runs_only" if any(rid in live for rid in ids)
                      else "outside_live_groups_only" if ids else "no_run")
            result["row_buckets"][bucket] += 1
            if not ids:
                result["unmatched_rows"].append({"row": _cell_ref(SHEET_FILES, f"A{r}"), "name": name})
                continue
            if here:
                result["rows_matched"] += 1
            for rid in here:
                orow = our_row[rid]
                for j, col in mapped.items():
                    raw = wf_theirs.cell(row=r, column=j).value
                    if raw is None or (isinstance(raw, str) and not raw.strip()):
                        continue
                    their_ref = _cell_ref(SHEET_FILES, f"{_letter(j)}{r}")
                    if col.header == "Config ID":
                        cid = str(raw).strip()
                        cfg = configs.get(cid)
                        our_ref = f"{_letter(file_col['Config ID'])}{orow}"
                        if cfg is None:
                            disagree(("invalid", SHEET_FILES, "Config ID", repr(raw)), kind="invalid", sheet=SHEET_FILES,
                                     header="Technique", path=tech_col.path, their_value=raw, allowed=None, scope="run",
                                     reason=f"your Configurations sheet has no Config ID {cid!r}",
                                     _their_cells=[their_ref], _runs=[rid], _answer_cells=[_cell_ref(SHEET_FILES, our_ref)])
                            continue
                        tech = cfg["technique"]
                        if tech is not None and str(tech).strip():
                            value, why = _parse(tech, rules.get(tech_col.path))
                            bad, good = ([], []) if why else ad.compare(value, rid, tech_col.path)
                            if why or bad:
                                ad.expose(good)
                                kind = "file_reading" if bad else ("not_allowed" if (rules.get(tech_col.path) or {}).get("allowed") else "invalid")
                                key = (kind, SHEET_CONFIG, "Technique", cfg["ref"], tuple(sorted({repr(b["value"]) for b in bad})))
                                disagree(key, kind=kind, sheet=SHEET_CONFIG, header="Technique", path=tech_col.path, their_value=tech,
                                         reason=("a file reading says otherwise" if bad else "not an allowed value" if kind == "not_allowed"
                                                 else why.partition("; allowed: ")[0]),
                                         _readings=[f"differs: {_shown_reading(b)}" for b in bad]
                                         + [f"agrees: {_shown_reading(b)}" for b in good], scope="run",
                                         allowed=(rules.get(tech_col.path) or {}).get("allowed") if kind == "not_allowed" else None,
                                         _their_cells=[cfg["ref"], their_ref], _runs=[rid], _answer_cells=[_cell_ref(SHEET_FILES, our_ref)])
                                continue
                            ours = _cell_ref(SHEET_CONFIG, f"B{cfg['our_row']}")
                            if wcfg[f"B{cfg['our_row']}"].value is None:
                                wcfg[f"B{cfg['our_row']}"] = value
                                wcfg[f"B{cfg['our_row']}"].comment = Comment(f"From your sheet: {their_file} {cfg['ref']}", "ISAAC")
                                adopted_cells.append((ours, cfg["ref"]))
                            # c14n MED-2: the Technique cell reaches every run whose row chose this Config ID
                            adopted_reach.setdefault(ours, {"path": tech_col.path, "scope": "run", "runs": []})["runs"].append(rid)
                        wb[SHEET_FILES][our_ref] = cid
                        wb[SHEET_FILES][our_ref].comment = Comment(f"From your sheet: {their_file} {their_ref}", "ISAAC")
                        adopted_cells.append((_cell_ref(SHEET_FILES, our_ref), their_ref))
                        result["cells_adopted"] += 1
                        continue
                    if index.status(col)[0] != "mapped":
                        result["not_adopted"].append({"cell": their_ref, "header": col.header, "value": raw, "run_id": rid,
                                                      "reason": index.status(col)[1]})
                        continue
                    judge(SHEET_FILES, f"{_letter(file_col[col.header])}{orow}", col, raw, their_ref, rid, their_row=r)
        matched_runs = {rid for rids in runs_of_row.values() for rid in rids if rid in live and rid not in several}
        result["runs_matched"] = len(matched_runs)
        result["unmatched_runs"] = [{"run_id": r["run_id"], "file_name": r["file_name"]} for r in rows if r["run_id"] not in matched_runs]

        # Disagreements: one row per disagreement; the answer cell stays EMPTY and says why
        order = {"file_reading": 0, "hint": 1, "name_only": 2, "not_allowed": 3, "invalid": 4}
        entries = sorted(groups.values(), key=lambda g: order[g["kind"]])
        # c14 MED-1: a row whose field the scientist already answered for every run it names says so (adopting again
        # after a new reading must not ask for rulings already given); a blank ruling there keeps the recorded value
        from . import propose_terms as P

        answers = P.allowed_answers(bundle, [g["path"] for g in entries if g["path"]] + [ELECTROLYTE_CONC_PATH]) if entries else {}
        chains = _Chains(bundle)  # c14k MED-1: a ruling anywhere in the same-value run settles its row
        for g in entries:
            st = ruling_state(answers, chains.log, kind=g["kind"], path=g["path"], run_ids=g["runs"], scope=g["scope"],
                              their_value=g["their_value"], their_file=their_file, their_cells=", ".join(g["their_cells"]),
                              beamtime=beamtime_reach(index, g["path"], live), chain_of=chains)
            g["already_recorded"], g["recorded_note"] = st["already_recorded"], st["recorded_note"]
            g["governing"] = st["governing"]
            g["shown"] = st.get("shown") or []  # c15b H2: the fields whose recorded values the row names
        wd = wb.create_sheet(SHEET_DISAGREE, index=wb.sheetnames.index(SHEET_SUGGEST))
        from openpyxl.styles import Alignment, Font

        for j, h in enumerate(DISAGREE_HEADERS, start=1):
            wd.cell(row=1, column=j, value=h).font = Font(bold=True)
            wd.column_dimensions[_letter(j)].width = 28 if h != "File reading(s)" else 60
        wd[f"{DISAGREE_RULING_COLUMN}1"].comment = Comment(
            "Type the value to record for this row, exactly as the field takes it (a number for a number field; one of "
            "the allowed values for a list). Leave it blank and nothing is recorded for it. ISAAC never picks a side.", "ISAAC")
        wd[f"{DISAGREE_CONC_COLUMN}1"].comment = Comment(
            "Only for an Electrolyte row whose value also states a concentration: the concentration in mol/L, a number "
            "(e.g. 0.01 for 0.01 M). It is recorded as Electrolyte Concentration (M) for exactly the runs of that row; the "
            "name goes in 'Your ruling'. Leave it blank on every other row.", "ISAAC")
        what = {"file_reading": "your value contradicts a file reading",
                "hint": "your value names another one than a hint (the folder's or the acquisition system's name; a hint, "
                        "not a file reading)",
                "name_only": "", "not_allowed": "", "invalid": "cannot be adopted as written: "}
        allowed_once: dict[str, list] = {}
        for i, g in enumerate(entries, start=1):
            g["id"] = f"D{i}"
            row = 1 + i
            g["row"] = row
            g["unread_hints"] = [{"column": c, "header": h, "value": v, "allowed_value": a, "rows": n}
                                 for (c, h, v, a), n in g["unread_hints"].items()]
            said = what[g["kind"]] if g["kind"] in ("file_reading", "hint") else what[g["kind"]] + g["reason"] + (
                " (each field's allowed values are listed once, below)" if g["kind"] == "not_allowed" else "")
            if g["unread_hints"]:
                said += ". " + "; ".join(_unread_hint_text(h, len(g["runs"])) for h in g["unread_hints"])
            if g["already_recorded"] or g["recorded_note"]:
                said = f"{(g['already_recorded'] or {}).get('statement') or g['recorded_note']}. {said}"
            values = (g["id"], said, g["header"], g["their_value"], _refs_shown(g["their_cells"]), "\n".join(g["readings"]) or None,
                      _refs_shown(g["runs"], noun="runs") if g["runs"] else "every File List run", None,
                      _refs_shown(g["answer_cells"]), None)
            for j, v in enumerate(values, start=1):
                c = wd.cell(row=row, column=j, value=v if not isinstance(v, str) or not v.startswith("=") else "'" + v)
                c.alignment = Alignment(wrap_text=True, vertical="top")
            wd[f"{DISAGREE_RULING_COLUMN}{row}"].number_format = "@" if not (rules.get(g["path"] or "") or {}).get("numeric") else "General"
            if g["already_recorded"]:
                rec = g["already_recorded"]
                # c14g LOW-4: a value that is the runs' own answer clashes with a different ruling; a beamtime-wide one
                # does not (the ruling is recorded for this row's runs, beside it)
                wd[f"{DISAGREE_RULING_COLUMN}{row}"].comment = Comment(
                    f"{rec['statement'][0].upper()}{rec['statement'][1:]}: a blank ruling records nothing new. "
                    + ("A different value here is recorded over it when you import (the preview names it); if the "
                       "value recorded changes before then, nothing is recorded for it: adopt again." if rec["run_own"]
                       else "It is a beamtime-wide answer: a different value here is recorded for this row's runs alone, "
                            "beside it (the import preview says what it records)."), "ISAAC")
            if g.get("allowed"):
                allowed_once.setdefault(g["header"], list(g["allowed"]))
            for ref in g["answer_cells"]:
                sheet, _, cell = ref.partition("!")
                ws = wb[sheet.strip("'")]
                ws[cell].fill = flag
                ws[cell].comment = Comment(
                    f"Not adopted ({g['id']} on the {SHEET_DISAGREE} sheet): your {their_file} {_refs_shown(g['their_cells'], 2)} "
                    f"has {_shown(g['their_value'])}; " + ("; ".join(g["readings"]) if g["readings"] else g["reason"])
                    + ". Rule on it there; this cell stays empty.", "ISAAC")
        if allowed_once:
            r = len(entries) + 3
            wd.cell(row=r, column=1, value="Allowed values (each field's list, once)").font = Font(bold=True)
            for k, (header, allowed) in enumerate(allowed_once.items(), start=1):
                wd.cell(row=r + k, column=1, value=header)
                wd.cell(row=r + k, column=2, value=", ".join(map(str, allowed)))
        if not entries:
            wd.cell(row=2, column=1, value="(no disagreements: every value of your sheet that ISAAC read agrees with the files or the files state nothing)")
        wd.freeze_panes = "A2"

        # _isaac: where each adopted cell came from, and what each Disagreements row's ruling reaches
        # c14n MED-2: and the decisions each adopted answer cell's targets held (:data:`ADOPTED_GOVERNING`)
        adopted_answers = P.allowed_answers(bundle, sorted({x["path"] for x in adopted_reach.values() if x["path"]}))
        r = marker.max_row + 2
        marker.cell(row=r, column=1, value="[adopted]")
        r += 1
        for j, h in enumerate(("cell", "their_file", "their_cell", ADOPTED_GOVERNING), start=1):
            marker.cell(row=r, column=j, value=h)
        for ours, their_ref in adopted_cells:
            r += 1
            x = adopted_reach.get(ours)
            governing = json.dumps(governing_decisions(
                adopted_answers, chains.log, [x["path"]], x["runs"], x["scope"],
                beamtime_reach(index, x["path"], live) if x["scope"] == "experiment" else None)) if x and x["path"] else None
            for j, v in enumerate((ours, their_file, their_ref, governing), start=1):
                marker.cell(row=r, column=j, value=v)
        r += 2
        marker.cell(row=r, column=1, value="[disagreements]")
        r += 1
        heads = ("id", "row", "kind", "header", "target_field_path", "scope", "targets", "their_file", "their_cells",
                 "their_value", "governing_decisions", RECORDED_SHOWN)
        for j, h in enumerate(heads, start=1):
            marker.cell(row=r, column=j, value=h)
        for g in entries:
            r += 1
            targets = ";".join(g["runs"]) if g["scope"] == "run" else "experiment"
            # c14h MED-1: their value, kept here where the scientist does not type (import reads it, not column D);
            # c14j MED-1: the decisions the row was ruled against (a JSON list, "[]" for none)
            for j, v in enumerate((g["id"], g["row"], g["kind"], g["header"], g["path"], g["scope"], targets, their_file,
                                   ", ".join(g["their_cells"]), _ruled_on_text(g["their_value"]),
                                   json.dumps(g["governing"]), json.dumps(g["shown"])), start=1):
                marker.cell(row=r, column=j, value=v)
        r += 2
        marker.cell(row=r, column=1, value="[meta]")  # read into the same meta as the first block
        marker.cell(row=r + 1, column=1, value="adopted_from")
        marker.cell(row=r + 1, column=2, value=their_file)
        # c14l MED-2: the decision log's length at adopt; a decision at or after this place was recorded since
        marker.cell(row=r + 2, column=1, value="decisions_at_adopt")
        marker.cell(row=r + 2, column=2, value=len(chains.log))
        # c14m MED-2: and a hash of those decisions: a copied, restored or forked bundle (same bundle_id, decision
        # ids that repeat) whose log no longer begins with them leaves the workbook unplaceable (:func:`_placed`)
        marker.cell(row=r + 3, column=1, value="decisions_fingerprint")
        marker.cell(row=r + 3, column=2, value=decisions_fingerprint(chains.log, len(chains.log)))
        # c14m MED-3: this adoption's own id, carried by each ruling's note: a scientist correcting a ruling they made
        # on this workbook rules against the value recorded now; another adoption of the same sheet has another id
        marker.cell(row=r + 4, column=1, value="adopt_id")
        marker.cell(row=r + 4, column=2, value=secrets.token_hex(16))

        result["disagreements"] = [{k: g[k] for k in ("id", "kind", "header", "path", "their_value", "their_cells", "readings",
                                                      "runs", "answer_cells", "reason", "scope", "unread_hints",
                                                      "already_recorded", "recorded_note")}
                                   | {"ruling_cell": _cell_ref(SHEET_DISAGREE, f"{DISAGREE_RULING_COLUMN}{g['row']}")}
                                   | ({"concentration_ruling_cell": _cell_ref(SHEET_DISAGREE, f"{DISAGREE_CONC_COLUMN}{g['row']}")}
                                      if g["kind"] == "name_only" else {})
                                   for g in entries]
        result["allowed_values"] = allowed_once
        # L3: a reaction (adopted, or to be ruled on its row) makes drive and catalysis required for its runs
        reaction_runs = [rid for rid, p in adopted_paths if p in REACTION_PATHS and rid] + [
            rid for g in entries if g["path"] in REACTION_PATHS for rid in g["runs"]]
        result["reaction_needs"] = reaction_lacking(bundle, reaction_runs, adopted_paths) if reaction_runs else None
        result["ai_readings_of_their_sheet_not_compared"] = ad.sheet_readings_skipped
        result["_exposed"] = ad.exposed
        # a not-allowed value that is ONLY off its field's list: a word the vocabulary lacks (1.10.0)
        result["_off_list"] = [{"path": g["path"], "value": g["their_value"].strip(), "header": g["header"],
                                "cells": list(g["their_cells"]), "run_ids": list(g["runs"]),
                                "cell_runs": {c: list(rs) for c, rs in g["cell_runs"].items()}}
                               for g in entries if g["kind"] == "not_allowed" and isinstance(g["their_value"], str)
                               and B.off_list_only(g["path"], g["their_value"].strip())]
        return result

    exported = export_template(bundle_dir, out, suggestions=suggestions, force=force, _fill=fill,
                               _command="bundle template adopt",
                               _keep_off_list={"by": by, "orcid": orcid, "file": their_file})
    exported["adopted"] = _as_text_dates(exported["adopted"])  # their cells as read: a date cell is a datetime
    exported["by"] = by  # c15b L1: the next command names them
    exported["statement"] = (f"Answer cells hold your sheet's value only where no file reading contradicts it; each cites "
                             f"its cell in {their_file}. Nothing that contradicts a file is in an answer cell: rule on each "
                             f"row of the {SHEET_DISAGREE} sheet (Your ruling), then `template import`.")
    return exported


def _await(n: int) -> str:
    """c15b L3: "1 awaits", "2 await"."""
    return "awaits" if n == 1 else "await"


def render_adopt_summary(result: Mapping) -> str:
    """Compact: rows matched, cells adopted, EVERY disagreement named (run, field, their value, the
    file's reading), not-allowed values with each field's allowed list once, unmatched rows."""
    a = result["adopted"]
    rb = a.get("row_buckets") or {}
    lines = [f"Wrote {result['written']} from {a['their_file']} (bundle {result['bundle_id']}).",
             f"Rows: {a['rows_matched']} of your {sum(rb.values()) or a['rows_matched'] + len(a['unmatched_rows'])} File List "
             f"rows matched {a['runs_matched']} run(s); "
             + (f"{rb['shared_runs_only']} row(s) name only runs another of your rows also names (nothing adopted from "
                "them); " if rb.get("shared_runs_only") else "")
             + (f"{rb['outside_live_groups_only']} row(s) name only runs in no live record group (nothing adopted from "
                "them; --json: runs_outside_live_groups); " if rb.get("outside_live_groups_only") else "")
             + f"{len(a['unmatched_rows'])} row(s) matched no run; {len(a['unmatched_runs'])} run(s) are on none of your rows"
             # c15b M5: a Campaign Info answer reaches every File List run, those on none of their rows too
             + (" (Campaign Info still applies to them: its answers reach every File List run)"
                if a["unmatched_runs"] and (a.get("campaign_cells_adopted") or any(
                    d.get("scope") == "experiment" for d in a["disagreements"])) else "") + ".",
             f"Cells adopted: {a['cells_adopted']} (each cites your cell)."]
    mapped = [f"{m['header']} -> {m['to']}" for m in a["their_columns_mapped"] if m.get("by_alias")]
    if mapped:
        lines.append("Columns read under ISAAC's name: " + "; ".join(mapped) + ".")
    if a["their_columns_not_read"]:
        lines.append(f"Your columns not read ({len(a['their_columns_not_read'])}): "
                     + ", ".join(f"{c['column']} {c['header']!r}" for c in a["their_columns_not_read"]) + ".")
    file_ds = [d for d in a["disagreements"] if d["kind"] == "file_reading"]
    hint_ds = [d for d in a["disagreements"] if d["kind"] == "hint"]
    other = [d for d in a["disagreements"] if d["kind"] not in ("file_reading", "hint")]
    settled = [d for d in a["disagreements"] if d.get("already_recorded")]
    if settled:
        # c14 MED-1: a row the scientist already ruled on (their decision stands for every run it names) is not asked again
        left = len(a["disagreements"]) - len(settled)
        lines.append(f"Disagreements already recorded: {len(settled)} of {len(a['disagreements'])} (each says what is "
                     f"recorded; a blank ruling keeps it); {left} {_await(left)} your ruling.")

    def waiting(ds: Sequence[Mapping]) -> str:
        done = sum(1 for d in ds if d.get("already_recorded"))
        return ("each awaits your ruling" if not done else
                f"{len(ds) - done} {_await(len(ds) - done)} your ruling, {done} already recorded (a blank ruling keeps it)")

    def recorded(d: Mapping) -> str:
        said = (d.get("already_recorded") or {}).get("statement") or d.get("recorded_note")
        return f" [{said}]" if said else ""

    lines.append("")
    lines.append(f"Disagreements with a file reading ({len(file_ds)}; not adopted, {waiting(file_ds)}; every reading "
                 "is listed, the agreeing ones too):")
    for d in file_ds:
        runs = _refs_shown(d["runs"], noun="runs") if d["runs"] else "every run"
        lines.append(f"  {d['id']} {runs} {d['header']}: yours {_shown(d['their_value'])} ({_refs_shown(d['their_cells'], 2)}); "
                     f"files: {'; '.join(d['readings'])}{recorded(d)}")
    if not file_ds:
        lines.append("  (none)")
    if hint_ds:
        lines.append("")
        lines.append(f"Disagreements with a hint ({len(hint_ds)}; not adopted, {waiting(hint_ds)}; a hint is not a file "
                     "reading, so say both and let the scientist rule):")
        for d in hint_ds:
            lines.append(f"  {d['id']} {d['header']}: yours {_shown(d['their_value'])} ({_refs_shown(d['their_cells'], 2)}); "
                         f"{'; '.join(d['readings'])}{recorded(d)}")
    if other:
        lines.append("")
        lines.append(f"Not adopted as written ({len(other)}; {waiting(other)}):")
        for d in other:
            reach = f"for {len(d['runs'])} run(s)" if d["runs"] else "for every File List run"
            lines.append(f"  {d['id']} {d['header']} {_shown(d['their_value'])} {reach}, from {len(d['their_cells'])} of your "
                         f"cell(s) ({_refs_shown(d['their_cells'], 2)}): {d['reason']}{recorded(d)}")
            for h in d.get("unread_hints") or ():
                lines.append(f"     hint: {_unread_hint_text(h, len(d['runs']))}")
        for header, allowed in a.get("allowed_values", {}).items():
            lines.append(f"  allowed for {header}: {', '.join(map(str, allowed))}")
    if a.get("vocabulary_requests"):
        lines += _request_sections(a["vocabulary_requests"], True, "Kept as vocabulary requests (not decisions, not "
                                   "values: each is a word its field's list lacks; `isaac bundle propose-terms` can draft it):")
    if a.get("vocabulary_requests_not_kept"):
        not_kept = a["vocabulary_requests_not_kept"]
        words = not_kept["words"]
        if words:
            lines.append("")
            lines.append(f"Off-list values were not kept as requests: no name given ({len(words)} word(s): "
                         + "; ".join(f"{w['header']} {w['term']!r}" for w in words[:10])
                         + (f" and {len(words) - 10} more" if len(words) > 10 else "")
                         + "). Pass --by only after the scientist says the sheet is theirs.")
            lines += [f"     {w['answered_since']['statement']}" for w in words if w.get("answered_since")]
        if not_kept.get("answered_since"):
            lines.append("")
            lines.append(ANSWERED_SINCE_HEADING)
            lines += [f"  {w['header']} {w['term']!r}: {w['answered_since']['statement']}" for w in not_kept["answered_since"]]
    for title, key, shown in (("Your rows that match no run", "unmatched_rows", lambda x: f"{x['row']} {x['name']}"),
                              ("Your rows that reach more than one run (each value goes to every one)", "rows_reaching_several_runs",
                               lambda x: f"{x['row']} {x['name']} -> {x['runs']} runs"),
                              ("Runs on none of your rows", "unmatched_runs", lambda x: x["file_name"]),
                              ("Runs on several of your rows (not adopted)", "runs_on_several_rows", lambda x: f"{x['run_id']} ({', '.join(x['rows'])})")):
        items = a[key]
        if items:
            more = f" and {len(items) - 10} more (--json lists all)" if len(items) > 10 else ""
            lines.append("")
            lines.append(f"{title} ({len(items)}): " + "; ".join(shown(x) for x in items[:10]) + more)
    if a["not_adopted"]:
        by_header: dict[str, list] = {}
        for x in a["not_adopted"]:
            by_header.setdefault(x["header"], []).append(x)
        lines.append(f"Cells with nowhere to go ({len(a['not_adopted'])}; not copied): " + "; ".join(
            f"{h} {len(xs)} cell(s) ({xs[0]['reason']})" for h, xs in by_header.items()) + ".")
    if a.get("reaction_needs"):
        lines.append(_reaction_needs_line(a["reaction_needs"], "(adopted, or once ruled on its Disagreements row)"))
    if a.get("ai_readings_of_their_sheet_not_compared"):
        lines.append(f"{a['ai_readings_of_their_sheet_not_compared']} AI reading(s) of your sheet itself were not compared: they are your sheet, not the files.")
    lines.append("")
    lines.append(result["statement"])
    # c15b L1: the name passed with --by, when one was
    who = shlex.quote(result["by"].strip()) if isinstance(result.get("by"), str) and result["by"].strip() else '"<your name>"'
    lines.append(f"Then: isaac bundle template import {result.get('bundle_dir') or '<bundle_dir>'} {result['written']} --by {who} "
                 "(a preview; add --apply to record).")
    return "\n".join(lines)
