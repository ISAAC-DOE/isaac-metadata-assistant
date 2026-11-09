"""A scientist's filled-in QUESTION WORKBOOK, read back into a bundle (``isaac bundle answers import``).

The question workbook is the spreadsheet of ISAAC questions a scientist is sent: one tab per kind of question, a
header row, an id column (``ISAAC question ID``) and a yellow ``YOUR ANSWER`` column. This module reads the answers
back and maps each one to the exact ``isaac bundle decide`` it stands for:

* ``yes`` / ``ok`` accepts the suggestion shown on that row (a confirm, or a correct with the shown value when it is
  exactly a value ISAAC offers for the question now);
* a typed value is a ``correct`` with that value, parsed as the template import parses a cell
  (:func:`template._parse_for`) and checked by the decide path itself (``bundle.allowed_values``): a word that is off
  the field's list is kept as a vocabulary request exactly as ``decide --as-said`` keeps it (it is the scientist's
  own word), never recorded as a value;
* a blank cell is skipped. Nothing is inferred for a row the scientist left blank.

Rows that are free text (rules ``R*``, new questions ``N*``, Claude's rule proposals ``CR*``) and the Athena merges
tab are REPORTED, never applied: a person (or Claude with the scientist) translates them. "same for all" in a note
is reported, never expanded.

Preview is the default and writes nothing (every decision is dry-run through the decide path on a temporary copy of
``bundle.json``, so not even a lock file is created in the bundle folder). ``apply`` records each decision through
:func:`mutations.decide_question` / :func:`mutations.decide`, with ``--by`` and a note citing the workbook cell; a
second run records nothing new (the decide path's own idempotency). ``apply`` refuses a bundle inside a folder whose
name starts with ``_runs`` (the protected real bundles): apply to a copy first.

Tabs and columns are found from each tab's HEADER ROW, never from tab titles: see :data:`TAB_KINDS`. The titles of the
format as first sent are listed in :data:`KNOWN_TAB_TITLES` for the report only.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import bundle as B
from . import template as T

FORMAT_ID = "isaac.workbook_answers_import"
FORMAT_VERSION = "1.0.0"

EXIT_USAGE = 2
EXIT_INPUT_REFUSED = 3
EXIT_OUTPUT_REFUSED = 4
EXIT_NOT_FOUND = 6

#: the protected real bundles live in folders named ``_runs…``: ``--apply`` refuses any path with such a part
PROTECTED_PREFIX = "_runs"


class AnswersRefused(T.TemplateRefused):
    """The workbook or the call is refused as a whole; nothing was recorded. ``code`` is the exit code."""


# --- the format: headers (casefolded, whitespace collapsed) -------------------------------------------------------

HEADER_SCAN_ROWS = 10
H_REF = "ref"
H_ANSWER = "your answer"
H_NOTES = ("your notes", "notes")
H_ID = ("isaac question id",)
H_FOLDER = "folder"
H_TOPIC = "topic"
H_QUESTION = "question"
H_KIND = "kind"
#: the shown suggestion: a prefix of the header ("Suggested answer (NOT confirmed)", "Claude proposes")
H_SUGGESTION = ("suggested answer", "claude proposes")
#: a proposal's own statement of what "ok" records ("sets sample.sample_form = 'powder'")
H_OK_RECORDS = "what 'ok' records"
#: a per-record row names the collapsed row (its Ref) that answers it together with others
H_COVERED = "covered by collapsed row"
#: an explicit field path, when a workbook carries one (optional)
H_FIELD = ("field path", "isaac field")
H_PROJECTS = "athena project file(s)"
H_LABEL = "athena group label"
H_STORED = "athena group (as stored)"
H_NEAR = "near name"  # prefix: "Near name (hint only, never matched)"

#: how a tab is read, decided from its header row alone
TAB_KINDS = {
    "info": "no header row with Ref / YOUR ANSWER / ISAAC question ID (a read-me or start page): not read",
    "no_answer": "a header row but no YOUR ANSWER column: its ids are counted and resolved, nothing is read",
    "questions": "YOUR ANSWER and ISAAC question ID columns: each answered row maps to a bundle decide",
    "free_text": "YOUR ANSWER and Ref but no id column (rules, new questions): reported, never applied",
    "athena_merges": "YOUR ANSWER with Athena project and group columns: reported with params-file entries, never applied",
    "unknown": "a YOUR ANSWER column but neither Ref nor an id column: reported, not read",
}

#: the tab titles of the question workbook as first sent (29 Oct to 8 Nov 2026). Reported only (``title_known``):
#: every tab is read by its header row, whatever its title.
KNOWN_TAB_TITLES = (
    "Start here", "Read Me", "0 New since 29 Oct", "Athena merges", "1 Rules and protocol", "Claude's proposals (say ok)",
    "2 Missing (blocks export)", "2b Missing per record", "3 Confirm (blocks export)", "3b Confirm per record",
    "4 Conflicts (blocks export)", "5 File-name numbers", "6 Merge or keep apart", "7 Element and edge",
    "8 Clock time zone", "9 Confirm (optional)", "9b Confirm (opt) per record", "10 Conflicts (optional)",
    "11 Optional fields", "11b Optional per record", "12 Athena versions", "No answer needed",
)

#: a row's Topic -> the record field it asks, used ONLY where the row's question asks several fields at once (an
#: optional-values question) and the row names no field path itself. Keys are casefolded, whitespace collapsed.
TOPIC_FIELDS = {
    "applied potential (v)": "context.electrochemistry.potential_setpoint_V",
    "atmosphere or gas": "context.thermodynamics.atmosphere",
    "beamline": "system.facility.beamline",
    "catalysis type": "context.reaction.catalysis",
    "domain (experimental or computational)": "system.domain",
    "electrochemical cell type": "context.electrochemistry.cell_type",
    "electrochemical reaction": "context.electrochemistry.reaction",
    "electrolyte": "context.electrochemistry.electrolyte.name",
    "electrolyte concentration (m)": "context.electrochemistry.electrolyte.concentration_M",
    "electrolyte ph": "context.electrochemistry.pH",
    "endstation": "system.facility.endstation",
    "facility name": "system.facility.facility_name",
    "facility site": "system.facility.site",
    "facility's organization": "system.facility.organization",
    "feed composition": "context.transport.feed.composition",
    "gas or liquid feed flow rate": "context.transport.feed.flow_rate",
    "how the sample was made or mounted": "sample.material.provenance",
    "institution that produced the data": "attribution.produced_by.organization",
    "measurement end time": "timestamps.acquired_end_utc",
    "measurement environment (operando / in situ / ex situ)": "context.environment",
    "measurement start time": "timestamps.acquired_start_utc",
    "pellet diameter (mm)": "sample.geometry.pellet_diameter_mm",
    "potential reference scale (rhe, ag/agcl, ...)": "context.electrochemistry.potential_scale",
    "research group that produced the data": "attribution.produced_by.group",
    "sample form (powder, film, ...)": "sample.sample_form",
    "sample formula": "sample.material.formula",
    "sample material name": "sample.material.name",
    "technique (xas, herfd-xas, xes, ...)": "system.technique",
    "temperature (k)": T.TEMPERATURE_PATH,
    "what drives the reaction": "context.reaction.drive",
}
_COMPOSITION_TOPIC = re.compile(r"sample composition: (\S+) mass fraction")

#: answers that accept the row's shown suggestion
YES_WORDS = frozenset({"yes", "y", "ok", "okay"})
#: answers that decline it: reported, nothing recorded (a "no" is not a value)
NO_WORDS = frozenset({"no", "n"})
#: answers that say the scientist does not know: reported, nothing recorded (never turned into a defer)
UNSURE_WORDS = frozenset({"?", "??", "unsure", "not sure", "don't know", "dont know", "do not know", "i don't know",
                          "i dont know", "idk", "unknown", "n/a", "na"})
#: a note (or answer) asking to repeat an answer elsewhere: reported for a person to translate, never expanded
SAME_FOR_ALL = re.compile(r"\b(?:same\s+(?:for|as)\s+(?:all|every\w*|each|the\s+rest|others|above|below)|ditto)\b",
                          re.IGNORECASE)

VALUE_KINDS = frozenset({"missing_value", "confirm_value", "resolve_conflict", "optional_values"})
_EDGES = ("K", "L1", "L2", "L3", "M1", "M2", "M3", "M4", "M5")
_ABSORBER = re.compile(r"\s*([A-Za-z]{1,2})[\s,_-]+(K|L[1-3]|M[1-5])(?:[\s-]*edge)?\s*", re.IGNORECASE)
_OK_RECORDS = re.compile(r"(?:sets|confirms the value the files give:)\s+([A-Za-z_][\w.\[\]]*)\s*=\s*(.+?)\s*$")
_OK_ABSORBER = re.compile(r"absorber to ([A-Z][a-z]?)\s+(K|L[1-3]|M[1-5])\b")
_RG_ID = re.compile(r"rg-[0-9a-f]{16}")
_VERSION = re.compile(r"v?0*(\d{1,3})", re.IGNORECASE)

HOW_FREE_TEXT = ("Not applied: free text. Translate it with the scientist into `isaac bundle decide` calls (or a "
                 "params file for processing), say each one back, and record it only on their yes.")
HOW_ATHENA = ("Not applied: put the entry in a params file and run `isaac process <bundle_dir> --source <folder> "
              "--params-file <file>` only after the scientist confirms it (keep passing that file on later runs).")
HOW_SAME_FOR_ALL = ("Not expanded: say which rows they mean, and answer each of those rows (or the one question that "
                    "covers them) on their word.")


def _norm(text: Any) -> str:
    """A header or a word as compared: casefolded, curly quotes straightened, whitespace collapsed."""
    s = str(text).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(s.split()).casefold()


def _word(text: Any) -> str:
    """An answer as a word: :func:`_norm`, underscores and dashes as spaces, trailing punctuation dropped."""
    return re.sub(r"[\s_]+", " ", _norm(text).replace("-", " ")).strip(" .!")


def topic_field(topic: Any) -> str | None:
    """The record field a row's Topic names (:data:`TOPIC_FIELDS`), or ``None``."""
    if topic is None:
        return None
    key = _norm(topic)
    if key in TOPIC_FIELDS:
        return TOPIC_FIELDS[key]
    m = _COMPOSITION_TOPIC.fullmatch(key)
    if m:
        name = " ".join(str(topic).split()).split(": ", 1)[1].rsplit(" mass fraction", 1)[0]
        return f"sample.composition.{name}_mass_fraction"
    return None


def classify(raw: Any) -> str:
    """``blank`` / ``yes`` / ``no`` / ``unsure`` / ``value`` for one answer cell's typed content."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return "blank"
    if isinstance(raw, str):
        w = _word(raw)
        if w in YES_WORDS:
            return "yes"
        if w in NO_WORDS or re.match(r"no\b[\s,:;(]", _norm(raw)):
            return "no"
        if w in UNSURE_WORDS or _norm(raw) in UNSURE_WORDS:
            return "unsure"
    return "value"


# --- reading the workbook ------------------------------------------------------------------------------------------


def _find(header: Sequence[str], names: str | Sequence[str], *, prefix: bool = False) -> int | None:
    names = (names,) if isinstance(names, str) else tuple(names)
    for i, h in enumerate(header):
        if any(h == n or (prefix and h.startswith(n)) for n in names):
            return i
    return None


def _shown(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value)) if abs(value) < 1e15 else str(value)
    text = str(value).strip()
    return text or None


def read_tabs(wb) -> list[dict]:
    """Every tab of an openpyxl workbook: its kind (:data:`TAB_KINDS`, from its header row) and its rows, each with
    the cells this import reads (answer cell kept as the Cell, for its coordinate and formula check)."""
    tabs = []
    for ws in wb.worksheets:
        head_row, header = None, []
        for r in range(1, min(ws.max_row, HEADER_SCAN_ROWS) + 1):
            values = [_norm(c.value) if c.value is not None else "" for c in ws[r]]
            if any(v in (H_REF, H_ANSWER) or v in H_ID for v in values):
                head_row, header = r, values
                break
        tab = {"tab": ws.title, "title_known": ws.title in KNOWN_TAB_TITLES, "header_row": head_row, "rows": []}
        tabs.append(tab)
        if head_row is None:
            tab["kind"] = "info"
            continue
        col = {
            "ref": _find(header, H_REF), "answer": _find(header, H_ANSWER), "notes": _find(header, H_NOTES),
            "id": _find(header, H_ID), "folder": _find(header, H_FOLDER), "topic": _find(header, H_TOPIC),
            "question": _find(header, H_QUESTION), "kind": _find(header, H_KIND),
            "suggestion": _find(header, H_SUGGESTION, prefix=True), "ok_records": _find(header, H_OK_RECORDS),
            "covered_by": _find(header, H_COVERED), "field": _find(header, H_FIELD),
            "projects": _find(header, H_PROJECTS), "label": _find(header, H_LABEL), "stored": _find(header, H_STORED),
            "near": _find(header, H_NEAR, prefix=True),
        }
        if col["answer"] is None:
            kind = "no_answer"
        elif col["projects"] is not None and col["label"] is not None:
            kind = "athena_merges"
        elif col["id"] is not None:
            kind = "questions"
        elif col["ref"] is not None:
            kind = "free_text"
        else:
            kind = "unknown"
        tab["kind"] = kind
        tab["columns"] = {k: v for k, v in col.items() if v is not None}
        for cells in ws.iter_rows(min_row=head_row + 1):
            def get(name):
                i = col[name]
                return cells[i].value if i is not None and i < len(cells) else None

            if all(c.value is None for c in cells):
                continue
            answer_cell = cells[col["answer"]] if col["answer"] is not None and col["answer"] < len(cells) else None
            row = {
                "tab": ws.title, "row": cells[0].row, "ref": _shown(get("ref")), "id": _shown(get("id")),
                "folder": _shown(get("folder")), "topic": _shown(get("topic")), "question": _shown(get("question")),
                "kind": _shown(get("kind")), "suggestion": get("suggestion"), "ok_records": _shown(get("ok_records")),
                "covered_by": _shown(get("covered_by")), "field": _shown(get("field")), "notes": _shown(get("notes")),
                "projects": _shown(get("projects")), "label": _shown(get("label")), "stored": _shown(get("stored")),
                "near": _shown(get("near")),
                "cell": answer_cell.coordinate if answer_cell is not None else None,
            }
            if answer_cell is not None:
                row["answer"], row["answer_refusal"] = T._raw(answer_cell)
            else:
                row["answer"], row["answer_refusal"] = None, None
            tab["rows"].append(row)
    return tabs


# --- planning: one answered row -> bundle decide calls --------------------------------------------------------------


class _Ctx:
    """What planning reads from the bundle, read once."""

    def __init__(self, bundle: Mapping, *, folder: str | None, xlsx_name: str, bundle_arg: str, by: str,
                 orcid: str | None):
        from . import questions as Q

        self.bundle = bundle
        self.folder = folder
        self.xlsx_name = xlsx_name
        self.bundle_arg = bundle_arg
        self.by = by
        self.orcid = orcid
        self.payload = Q.consolidate(bundle, include_answered=True)
        self.questions = {q["question_id"]: q for q in self.payload.get("questions") or ()}
        self.candidates = {c.get("candidate_id"): c for c in bundle.get("candidates") or ()}
        self.groups = {g.get("group_id"): g for g in bundle.get("record_groups") or ()}
        self.merge_candidates = {m.get("merge_candidate_id"): m for m in bundle.get("merge_candidates") or ()}
        self.results = list(bundle.get("processing_results") or ())
        live = T._live_group_of(bundle)
        self.live_groups = set(live.values())
        self.stem_groups: dict[str, set[str]] = {}
        for run in bundle.get("runs") or ():
            gid = live.get(run.get("run_key"))
            if gid and run.get("stem"):
                self.stem_groups.setdefault(str(run["stem"]).strip(), set()).add(gid)
        self.schema, _ = Q._target_schema()
        self._rules: dict[str, dict] = {}

    def rule(self, path: str | None) -> dict | None:
        if not path:
            return None
        if path not in self._rules:
            self._rules[path] = T.rule_for_path(path, schema=self.schema)
        return self._rules[path]

    def note(self, row: Mapping, via: Mapping | None = None) -> str:
        cite = f"workbook {self.xlsx_name} '{row['tab']}'!{row['cell']}"
        return cite + (f" (collapsed row {row['ref']}, for row {via['ref']})" if via else "")

    def mine(self, row: Mapping) -> bool:
        return self.folder is None or row.get("folder") is None or row["folder"] == self.folder


def _where(row: Mapping) -> dict:
    return {"tab": row["tab"], "cell": row["cell"], "ref": row.get("ref")}


def _problem(row: Mapping, reason: str, *, kind: str = "needs_translation", via: Mapping | None = None,
             **extra) -> dict:
    return {**_where(row), "id": row.get("id"), "answer": _answer_text(row.get("answer")), "problem": kind,
            "reason": reason, **({"for_row": via["ref"]} if via else {}), **extra}


def _answer_text(raw: Any) -> Any:
    return raw.isoformat() if hasattr(raw, "isoformat") else raw


def _plan(row: Mapping, ctx: _Ctx, *, call: str, decision: str, via: Mapping | None = None, **kw) -> dict:
    plan = {
        **_where(row), **({"for_row": via["ref"]} if via else {}), "call": call,
        "question_id": kw.get("question_id"), "target_ids": list(kw.get("target_ids") or ()), "field": kw.get("field"),
        "decision": decision, "value": kw.get("value"), "element": kw.get("element"), "edge": kw.get("edge"),
        "positions": kw.get("positions"), "merge_with": kw.get("merge_with"), "as_said": bool(kw.get("as_said")),
        "record_field": kw.get("record_field"), "answer": _answer_text(row.get("answer")),
        "note": ctx.note(row, via), "follow_up": list(kw.get("follow_up") or ()),
    }
    plan["command"] = decide_command(ctx.bundle_arg, plan, by=ctx.by, orcid=ctx.orcid)
    return plan


def decide_command(bundle_arg: str, plan: Mapping, *, by: str, orcid: str | None = None) -> str:
    """The exact ``isaac bundle decide`` a planned decision is (what ``--apply`` runs through the same code path)."""
    q = shlex.quote
    parts = ["isaac bundle decide", q(bundle_arg)]
    if plan.get("question_id"):
        parts.append(f"--question {plan['question_id']}")
    parts += [f"--target {t}" for t in plan.get("target_ids") or ()]
    if plan.get("field"):
        parts.append(f"--field {plan['field']}")
    parts.append(f"--decision {plan['decision']}")
    value = plan.get("value")
    if value is not None:
        parts.append(f"--value={q(value)}" if isinstance(value, str) else f"--value={q(json.dumps(value))} --json")
    if plan.get("element"):
        parts.append(f"--element {plan['element']} --edge {plan['edge']}")
    if plan.get("positions"):
        parts.append("--positions " + ",".join(str(p) for p in plan["positions"]))
    if plan.get("merge_with"):
        parts.append("--merge-with " + " ".join(plan["merge_with"]))
    if plan.get("as_said"):
        parts.append("--as-said")
    parts.append(f"--by {q(by)}")
    if orcid:
        parts.append(f"--orcid {orcid}")
    parts.append(f"--note {q(plan['note'])}")
    return " ".join(parts)


def _field_for(row: Mapping, q: Mapping) -> tuple[str | None, str | None, str | None]:
    """``(record field, --field to pass, problem)`` for a value question's row."""
    stated = _OK_RECORDS.search(row.get("ok_records") or "")
    named = [p for p in (stated.group(1) if stated else None, row.get("field"), topic_field(row.get("topic"))) if p]
    if q["kind"] == "optional_values":
        fields = list(q.get("fields") or {})
        if not named and len(fields) == 1:
            return fields[0], fields[0], None
        if not named:
            return None, None, (f"the row's topic {row.get('topic')!r} names no field this import knows, and the "
                                f"question asks {len(fields)} fields ({', '.join(fields)}): answer it with "
                                "`bundle decide --question … --field <path>`")
        path = named[0]
        if path not in fields:
            return None, None, (f"this question no longer asks {path} (it asks: {', '.join(fields) or 'nothing'}); "
                                "the bundle changed since the workbook was made")
        return path, path, None
    path = q.get("target_field_path")
    for other in named:
        if path and other != path:
            return None, None, (f"the row names {other}, but question {q['question_id']} asks {path}: the bundle "
                                "changed since the workbook was made")
    return path, None, None


def _asked_now_by(row: Mapping, q: Mapping, ctx: "_Ctx") -> str | None:
    """The ONE other question of the same scope that asks the field the row names, when its own question no longer
    does (a pointer in the reason only: the answer is never moved to it)."""
    stated = _OK_RECORDS.search(row.get("ok_records") or "")
    path = next((p for p in (stated.group(1) if stated else None, row.get("field"), topic_field(row.get("topic"))) if p),
                None)
    if not path:
        return None
    hits = [o["question_id"] for o in ctx.questions.values() if o["question_id"] != q["question_id"]
            and o.get("scope") == q.get("scope") and (o.get("target_field_path") == path or path in (o.get("fields") or {}))]
    return hits[0] if len(hits) == 1 else None


def _offered(q: Mapping, path: str | None) -> list[Any]:
    """The values ISAAC offers for a question now: hint literals that carry a value, and a suggested value."""
    hints = list(q.get("hints") or ()) + list(((q.get("field_hints") or {}).get(path or "") or ()))
    out = []
    for h in hints:
        lit = h.get("literal") if isinstance(h, Mapping) else None
        if isinstance(lit, bool) or not isinstance(lit, (str, int, float)):
            continue
        if h.get("carries_value") is False or h.get("fits_field") is False or h.get("kind") == "grouping":
            continue
        out.append(lit)
    if q.get("suggested_value") is not None:
        out.append(q["suggested_value"])
    return out


def _parse(ctx: _Ctx, raw: Any, path: str | None) -> tuple[Any, str | None]:
    """A typed value, as the template import parses a cell, WITHOUT the allowed-list check: the decide path makes
    that check itself (and keeps an off-list word as a vocabulary request with --as-said)."""
    rule = ctx.rule(path)
    if rule is None:
        if isinstance(raw, str):
            return raw.strip(), None
        return raw, None
    return T._parse_for(raw, {**rule, "allowed": None}, path)


def _plan_value_row(row: Mapping, ans: str, raw: Any, q: Mapping, ctx: _Ctx, via: Mapping | None = None) -> list[dict]:
    """A missing value, a value to confirm, a conflict or an optional field. ``row`` is the row whose suggestion
    counts (a covered per-record row when ``via``, the collapsed row, holds the answer)."""
    cite = via or row
    path, field, problem = _field_for(row, q)
    if problem:
        asked = _asked_now_by(row, q, ctx)
        if asked:
            problem += (f"; question {asked} asks it for this scope now: answer it there if the scientist's answer "
                        "is for it (`bundle decide --question " + asked + " …`), not applied here")
        return [_problem(cite, problem, kind="not_resolving", via=row if via else None)]
    allowed = list(q.get("allowed_decisions") or ())
    common = dict(question_id=q["question_id"], field=field, record_field=path)
    if ans == "yes":
        shown = row.get("suggestion")
        if _shown(shown) is None:
            return [_problem(cite, "nothing is suggested on this row to accept: type the value itself",
                             via=row if via else None)]
        sug, why = _parse(ctx, shown if not isinstance(shown, str) else shown.strip(), path)
        if why:
            return [_problem(cite, f"the shown suggestion {_shown(shown)!r} is not a value this field takes ({why})",
                             via=row if via else None)]
        stated = _OK_RECORDS.search(row.get("ok_records") or "")
        if q["kind"] == "confirm_value" and "confirm" in allowed:
            cands = [ctx.candidates.get(t.get("id")) for t in q.get("targets") or () if t.get("kind") == "candidate"]
            if cands and all(c is not None and T.agrees_for(path, sug, c.get("value")) for c in cands):
                return [_plan(cite, ctx, call="question", decision="confirm", via=row if via else None, **common)]
        offered = _offered(q, path)
        if stated:
            lit = stated.group(2)
            offered.append(lit[1:-1] if len(lit) >= 2 and lit[0] == lit[-1] == "'" else lit)
        for lit in offered:
            parsed, bad = _parse(ctx, lit, path) if isinstance(lit, str) else (lit, None)
            if not bad and T.agrees_for(path, sug, parsed):
                if "correct" not in allowed:
                    break
                return [_plan(cite, ctx, call="question", decision="correct", value=sug, via=row if via else None,
                              **common)]
        return [_problem(cite, (f"the shown suggestion {_shown(shown)!r} is not a value ISAAC offers for {q['question_id']} "
                                "now (the bundle changed, or the text carries commentary): type the value itself"),
                         via=row if via else None)]
    if "correct" not in allowed:
        return [_problem(cite, f"question {q['question_id']} takes no typed value now (it allows: "
                               f"{', '.join(allowed) or 'no answer'})", kind="refused", via=row if via else None)]
    value, why = _parse(ctx, raw, path)
    if why or value is None:
        return [_problem(cite, f"not recorded: {why or 'empty'}", kind="invalid", via=row if via else None)]
    rule = ctx.rule(path)
    as_said = isinstance(value, str) and bool(rule and rule.get("allowed"))
    return [_plan(cite, ctx, call="question", decision="correct", value=value, as_said=as_said,
                  via=row if via else None, **common)]


def parse_absorber(text: Any) -> tuple[str, str] | None:
    """``(element, edge)`` from "Pt L3", "Co K-edge", "Fe, K"; ``None`` for anything else (an element alone too)."""
    if not isinstance(text, str):
        return None
    m = _ABSORBER.fullmatch(text)
    if not m:
        return None
    el = m.group(1)[0].upper() + m.group(1)[1:].lower()
    edge = m.group(2).upper()
    if el not in T.ELEMENT_SYMBOLS or edge not in _EDGES:
        return None
    return el, edge


def _plan_question(row: Mapping, ans: str, raw: Any, q: Mapping, ctx: _Ctx) -> list[dict]:
    kind = q.get("kind")
    if kind in VALUE_KINDS:
        return _plan_value_row(row, ans, raw, q, ctx)
    if kind == "confirm_absorber":
        text = raw if ans == "value" else _shown(row.get("suggestion"))
        stated = _OK_ABSORBER.search(row.get("ok_records") or "") if ans == "yes" else None
        pair = (stated.group(1), stated.group(2)) if stated else parse_absorber(text)
        if pair is None:
            return [_problem(row, f"{_shown(text)!r} is not an element and an edge (e.g. 'Pt L3'): the absorber needs both")]
        return [_plan(row, ctx, call="question", decision="set_absorber", question_id=q["question_id"],
                      element=pair[0], edge=pair[1])]
    if kind == "clock_time_zone":
        text = raw if ans == "value" else _shown(row.get("suggestion"))
        if not isinstance(text, str) or not text.strip():
            return [_problem(row, "nothing is suggested on this row to accept: type the time zone (an IANA name)")]
        return [_plan(row, ctx, call="question", decision="set_clock_time_zone", question_id=q["question_id"],
                      value=text.strip(), record_field=q.get("target_field_path"))]
    if kind == "naming_counter_positions":
        w = _word(raw) if ans == "value" else ""
        positions = [p for p in q.get("positions") or () if isinstance(p, int)]
        if w == "counter":
            if len(positions) != 1:
                return [_problem(row, f"the question asks about positions {positions}: say which of them are "
                                      "counters (`--positions`)")]
            return [_plan(row, ctx, call="target", decision="set_counter_positions", target_ids=["experiment"],
                          positions=positions,
                          follow_up=[f"isaac bundle group {shlex.quote(ctx.bundle_arg)} --regroup"])]
        if w == "sequence":
            return [_plan(row, ctx, call="question", decision="set_not_counter_positions", question_id=q["question_id"])]
        return [_problem(row, "answer 'counter' or 'sequence'; anything else (e.g. 'some of each') needs a person")]
    return [_problem(row, f"question {q['question_id']} is a {kind} question, which this import does not map: "
                          f"answer it with its own command ({q.get('answer_command') or 'bundle decide --question'})")]


def _plan_merge_candidate(row: Mapping, ans: str, raw: Any, ctx: _Ctx) -> list[dict]:
    mc = ctx.merge_candidates.get(row["id"])
    if mc is None:
        return [_problem(row, f"no merge candidate {row['id']} in this bundle (it was regrouped or re-imported)",
                         kind="not_resolving")]
    w = _word(raw) if ans == "value" else ""
    if w in ("keep apart", "keep separate", "apart"):
        return [_plan(row, ctx, call="target", decision="keep_apart", target_ids=[row["id"]])]
    if w == "merge":
        gids = [g for g in mc.get("group_ids") or ()]
        if len(gids) < 2:
            return [_problem(row, f"merge candidate {row['id']} names fewer than two groups", kind="refused")]
        return [_plan(row, ctx, call="target", decision="merge", target_ids=[gids[0]], merge_with=gids[1:],
                      follow_up=[f"isaac bundle group {shlex.quote(ctx.bundle_arg)} --regroup",
                                 "then confirm the combined group: isaac bundle decide <bundle_dir> --target <combined "
                                 "group> --decision confirm --by \"<name>\""])]
    return [_problem(row, "answer 'Merge' or 'Keep apart'")]


def _plan_athena_version(row: Mapping, ans: str, raw: Any, ctx: _Ctx) -> list[dict]:
    gid = row["id"]
    if gid not in ctx.groups:
        return [_problem(row, f"no record group {gid} in this bundle", kind="not_resolving")]
    results = [r for r in ctx.results if r.get("group_id") == gid and r.get("athena_versions")]
    if not results:
        return [_problem(row, f"record group {gid} has no Athena versions to choose from now", kind="not_resolving")]
    m = _VERSION.fullmatch(_word(raw)) if ans == "value" and isinstance(raw, (str, int)) else None
    if not m:
        return [_problem(row, "answer one listed version (v01, v02, …); 'none' or anything else needs a person")]
    vid = f"{gid}-v{int(m.group(1)):02d}"
    holding = [r for r in results if any(v.get("version_id") == vid for v in r["athena_versions"])]
    if len(holding) != 1:
        return [_problem(row, f"{vid} is listed by {len(holding)} processing results of {gid}, not one",
                         kind="not_resolving")]
    return [_plan(row, ctx, call="target", decision=B.ATHENA_SELECT_DECISION, target_ids=[B.processing_id(holding[0])],
                  value=vid)]


def _plan_row(row: Mapping, ans: str, ctx: _Ctx, covered: Mapping[str, list[dict]]) -> list[dict]:
    """The planned decisions (or the one problem) for an answered row of a questions tab."""
    raw = row["answer"]
    rid = row.get("id") or ""
    ref = row.get("ref")
    if (ref and ref in covered) or rid.startswith("G-"):
        rows = [c for c in covered.get(ref or "", ()) if ctx.mine(c)]
        if not rows:
            return [_problem(row, f"collapsed row {ref} covers no per-record row of this bundle in the workbook",
                             kind="not_resolving")]
        if ans == "value":
            shown = {_shown(c.get("suggestion")) for c in rows if _shown(c.get("suggestion")) is not None}
            if len(shown) > 1:
                return [_problem(row, f"its {len(rows)} records show different values, so this row takes 'yes' only "
                                      "(each record's own value); type a value per record on its own row",
                                 kind="refused")]
        out: list[dict] = []
        for c in rows:
            q = ctx.questions.get(c.get("id") or "")
            if q is None:
                out.append(_problem(row, f"no question {c.get('id')} in this bundle (open or answered)",
                                    kind="not_resolving", via=c))
            elif q.get("kind") not in VALUE_KINDS:
                out.append(_problem(row, f"row {c.get('ref')} is a {q.get('kind')} question: answer it on its own row",
                                    via=c))
            else:
                out += _plan_value_row(c, ans, raw, q, ctx, via=row)
        return out
    if rid.startswith("Q-"):
        q = ctx.questions.get(rid)
        if q is None:
            return [_problem(row, f"no question {rid} in this bundle (open or answered): the bundle changed since the "
                                  "workbook was made", kind="not_resolving")]
        return _plan_question(row, ans, raw, q, ctx)
    if rid.startswith("mc-"):
        return _plan_merge_candidate(row, ans, raw, ctx)
    if rid.startswith("rg-"):
        return _plan_athena_version(row, ans, raw, ctx)
    return [_problem(row, f"{rid!r} is not an id this import reads (Q-…, mc-…, rg-…, or a collapsed row's Ref)",
                     kind="not_resolving")]


def _free_text_kind(ref: str | None) -> str:
    ref = ref or ""
    if re.fullmatch(r"R\d+", ref):
        return "rule"
    if re.fullmatch(r"N\d+", ref):
        return "new_question"
    if re.fullmatch(r"CR\d+", ref):
        return "rule_proposal"
    return "free_text"


def _clip(text: Any, n: int = 240) -> Any:
    if not isinstance(text, str) or len(text) <= n:
        return text
    return text[: n - 1] + "…"


def _athena_entry(row: Mapping, ans: str, ctx: _Ctx) -> dict:
    """A reported Athena merges row: what the answer reads as, and the params-file entry to use (never applied)."""
    projects = [p for p in re.split(r"\s*[;\n]\s*", row.get("projects") or "") if p]
    group = row.get("stored") or row.get("label") or "<Athena group>"
    near = list(dict.fromkeys(_RG_ID.findall(row.get("near") or "")))

    def items():
        return [{"project": p, "athena_group": group} for p in projects or ["<project file>"]]

    raw = row["answer"]
    entry, reading = None, None
    w = _word(raw) if isinstance(raw, str) else ""
    if ans == "value" and w == "none":
        entry, reading = {"athena_ignore": items()}, "no group's: set it aside (athena_ignore)"
    elif ans == "no":
        if near:
            entry = {"athena_match_not": {g: items() for g in near}}
            reading = "not the near group(s) shown (athena_match_not)"
        else:
            reading = "a 'no' with no near group shown: ask whether it is any group's (athena_ignore) or which"
    elif ans == "yes":
        if len(near) == 1:
            entry, reading = {"athena_match": {near[0]: items()}}, f"the one near group shown, {near[0]}"
        else:
            reading = f"'yes' needs exactly one near group shown; this row shows {len(near)}: ask which group"
    elif ans == "value":
        text = str(raw).strip()
        gids = ({text} if text in ctx.live_groups else set()) | ctx.stem_groups.get(text, set())
        if len(gids) == 1:
            gid = next(iter(gids))
            entry, reading = {"athena_match": {gid: items()}}, f"record group {gid}"
        else:
            reading = (f"{text!r} names {len(gids)} live record groups of this bundle (by group id or run name), "
                       "not one: ask which group it is")
    else:
        reading = "not an answer this tab reads: ask"
    return {
        **_where(row), "projects": projects, "athena_group": group, "athena_label": row.get("label"),
        "answer": _answer_text(raw), "notes": row.get("notes"), "reading": reading, "params_entry": entry,
        "params_entries_to_use": {
            "athena_match": {"<group id>": items()}, "athena_match_not": {"<group id>": items()},
            "athena_ignore": items(),
        },
        "how": HOW_ATHENA,
    }


def _signature(plan: Mapping) -> str:
    return json.dumps([plan["decision"], plan.get("value"), plan.get("element"), plan.get("edge"),
                       plan.get("positions"), plan.get("merge_with")], sort_keys=True, default=str)


def _dedupe(plans: list[dict]) -> tuple[list[dict], list[dict]]:
    """One decision per question/target and field: the same answer from several cells is one decision (citing the
    first, listing the others); DIFFERENT answers for one are all left out and reported."""
    by_key: dict[str, list[dict]] = {}
    for p in plans:
        key = json.dumps([p["call"], p.get("question_id"), p.get("target_ids"), p.get("field")])
        by_key.setdefault(key, []).append(p)
    kept, clashes = [], []
    for group in by_key.values():
        if len({_signature(p) for p in group}) == 1:
            first = dict(group[0])
            if len(group) > 1:
                first["also_from"] = [f"'{p['tab']}'!{p['cell']}" for p in group[1:]]
            kept.append(first)
        else:
            cells = ", ".join(f"'{p['tab']}'!{p['cell']}" for p in group)
            for p in group:
                clashes.append({**{k: p[k] for k in ("tab", "cell", "ref")}, "answer": p.get("answer"),
                                "problem": "refused",
                                "reason": f"answered differently in {cells}: none of them is recorded; ask which holds"})
    return kept, clashes


# --- running a plan through the decide path ------------------------------------------------------------------------


def _run(plan: Mapping, bundle_dir: Path, *, by: str, orcid: str | None, dry_run: bool) -> dict:
    from . import mutations as M

    kw = dict(decision=plan["decision"], value=plan.get("value"), by=by, orcid=orcid, note=plan["note"],
              as_said=plan.get("as_said", False), dry_run=dry_run)
    if plan["call"] == "question":
        return M.decide_question(bundle_dir, question_id=plan["question_id"], field=plan.get("field"),
                                 element=plan.get("element"), edge=plan.get("edge"), **kw)
    return M.decide(bundle_dir, target_ids=plan["target_ids"], merge_with=plan.get("merge_with"),
                    positions=plan.get("positions"), **kw)


def _outcome(plan: dict, bundle_dir: Path, *, by: str, orcid: str | None, dry_run: bool) -> dict:
    from . import mutations as M
    from . import records as R

    try:
        result = _run(plan, bundle_dir, by=by, orcid=orcid, dry_run=dry_run)
    except M.OffListRefused as exc:
        if exc.kept is not None:
            return {"outcome": "vocabulary_request_kept", "new": bool(exc.kept.get("new")),
                    "request_id": exc.kept.get("request_id"), "statement": exc.kept_statement()}
        if dry_run and plan.get("as_said"):
            return {"outcome": "would_keep_vocabulary_request",
                    "statement": (f"{exc.problem.strip()} --apply keeps it as a vocabulary request in {by}'s name, as "
                                  "`decide --as-said` does (no decision, no value; nothing new if it is kept already)")}
        return {"outcome": "refused", "reason": str(exc)}
    except (M.MutationRefused, R.RecordsRefused) as exc:
        return {"outcome": "refused", "reason": str(exc)}
    recorded = result.get("recorded")
    if recorded is None:
        recorded = result.get("slots_recorded")
    n = len(recorded) if isinstance(recorded, (list, tuple)) else int(recorded or 0)
    return {"outcome": ("would_record" if dry_run else "recorded") if n else "unchanged", "targets": n,
            "statement": result.get("statement")}


# --- the import -------------------------------------------------------------------------------------------------


def protected_part(bundle_dir: Path) -> str | None:
    """The folder name starting with ``_runs`` the bundle sits in (resolved path), or ``None``."""
    for part in Path(bundle_dir).expanduser().resolve().parts:
        if part.startswith(PROTECTED_PREFIX):
            return part
    return None


def import_answers(bundle_dir: Path, xlsx: Path, *, by: str, orcid: str | None = None, apply: bool = False,
                   folder: str | None = None, bundle_arg: str | None = None) -> dict:
    """Read a filled question workbook against one bundle. Preview (default) writes nothing; ``apply`` records."""
    from . import mutations as M

    problem = B.decider_name_problem(by)
    if problem:
        raise AnswersRefused(f"--by is required: the name of the person whose answers these are (this one {problem}).")
    if orcid is not None and not M.ORCID_RE.fullmatch(orcid):
        raise AnswersRefused("--orcid must look like 0000-0000-0000-0000 (last character may be X).")
    bundle_dir = Path(bundle_dir).expanduser()
    if apply and (part := protected_part(bundle_dir)):
        raise AnswersRefused(
            f"--apply refuses a bundle inside {part!r}: folders named _runs… hold the protected real bundles. Copy "
            "the bundle folder (cp -R), apply to the copy, show the scientist what it recorded, and apply to a real "
            "bundle only on their word, from a folder not named _runs…. Nothing was recorded.", code=EXIT_OUTPUT_REFUSED)
    xlsx = Path(xlsx).expanduser()
    wb = T._read_workbook(xlsx)
    try:
        bundle = M.load(bundle_dir)
    except M.MutationRefused as exc:
        raise AnswersRefused(str(exc), code=exc.code) from exc
    tabs = read_tabs(wb)
    label = (bundle.get("source_root") or {}).get("label")
    folder = folder or (str(label) if label else None)
    uses_folder = any("folder" in (t.get("columns") or {}) for t in tabs if t["kind"] in ("questions", "athena_merges"))
    if folder is None and uses_folder:
        raise AnswersRefused("The bundle does not record its folder's name and the workbook has a Folder column: say "
                             "which folder's rows are this bundle's with --folder <name>. Nothing was recorded.")
    ctx = _Ctx(bundle, folder=folder, xlsx_name=xlsx.name, bundle_arg=bundle_arg or str(bundle_dir), by=by,
               orcid=orcid)

    covered: dict[str, list[dict]] = {}
    for t in tabs:
        for r in t["rows"]:
            if r.get("covered_by"):
                covered.setdefault(r["covered_by"], []).append(r)

    plans: list[dict] = []
    problems: list[dict] = []
    free_text: list[dict] = []
    athena: list[dict] = []
    same_for_all: list[dict] = []
    tab_rows: list[dict] = []
    unresolved_by_tab: dict[str, int] = {}
    q_rows = q_rows_here = q_unresolved = 0
    answered_here = answered_elsewhere = 0
    for t in tabs:
        info = {"tab": t["tab"], "kind": t["kind"], "title_known": t["title_known"], "rows": len(t["rows"]),
                "id_rows": 0, "for_this_bundle": 0, "other_beamtimes": 0, "answered": 0, "answered_other_beamtimes": 0,
                "decisions": 0, "problems": 0, "free_text": 0, "not_resolving": 0}
        tab_rows.append(info)
        if t["kind"] in ("info",):
            continue
        for r in t["rows"]:
            rid = r.get("id") or ""
            mine = ctx.mine(r)
            if rid:
                info["id_rows"] += 1
            info["for_this_bundle" if mine else "other_beamtimes"] += 1
            if rid.startswith("Q-"):
                q_rows += 1
                if mine:
                    q_rows_here += 1
                    if rid not in ctx.questions:
                        q_unresolved += 1
                        info["not_resolving"] += 1
                        unresolved_by_tab[t["tab"]] = unresolved_by_tab.get(t["tab"], 0) + 1
            raw = r.get("answer")
            ans = classify(raw)
            if t["kind"] == "no_answer":
                continue
            if ans == "blank" and r.get("answer_refusal") is None:
                if mine and r.get("notes") and SAME_FOR_ALL.search(r["notes"]):
                    same_for_all.append({**_where(r), "notes": r["notes"], "answer": None, "how": HOW_SAME_FOR_ALL})
                continue
            if not mine:
                info["answered_other_beamtimes"] += 1
                answered_elsewhere += 1
                continue
            info["answered"] += 1
            answered_here += 1
            for text, where in ((r.get("notes"), "notes"), (raw if isinstance(raw, str) else None, "answer")):
                if text and SAME_FOR_ALL.search(text):
                    same_for_all.append({**_where(r), where: text, "how": HOW_SAME_FOR_ALL})
                    break
            if t["kind"] == "unknown":
                problems.append(_problem(r, f"tab {t['tab']!r} has a YOUR ANSWER column but no Ref or id column: not "
                                            "read", kind="unknown_tab"))
                info["problems"] += 1
                continue
            if r.get("answer_refusal"):
                problems.append(_problem(r, r["answer_refusal"], kind="invalid"))
                info["problems"] += 1
                continue
            if t["kind"] == "athena_merges":
                athena.append(_athena_entry(r, ans, ctx))
                info["free_text"] += 1
                continue
            if t["kind"] == "free_text" or not rid:
                free_text.append({**_where(r), "kind": _free_text_kind(r.get("ref")), "topic": r.get("topic"),
                                  "question": _clip(r.get("question")), "answer": _answer_text(raw),
                                  "notes": r.get("notes"), "how": HOW_FREE_TEXT})
                info["free_text"] += 1
                continue
            if ans in ("no", "unsure"):
                problems.append(_problem(r, ("a 'no' is not a value: nothing is recorded; ask what the right value is"
                                             if ans == "no" else "they do not know: nothing is recorded (not a defer)"),
                                         kind="declined" if ans == "no" else "unsure"))
                info["problems"] += 1
                continue
            if isinstance(raw, str) and SAME_FOR_ALL.fullmatch(raw.strip()):
                problems.append(_problem(r, "'same for all' is not a value: " + HOW_SAME_FOR_ALL))
                info["problems"] += 1
                continue
            for item in _plan_row(r, ans, ctx, covered):
                if "problem" in item:
                    problems.append(item)
                    info["problems"] += 1
                    if item["problem"] == "not_resolving":
                        info.setdefault("answered_not_resolving", 0)
                        info["answered_not_resolving"] += 1
                else:
                    plans.append(item)

    plans, clashes = _dedupe(plans)
    problems += clashes
    for info in tab_rows:
        info["decisions"] = sum(1 for p in plans if p["tab"] == info["tab"])
        info["problems"] = sum(1 for p in problems if p["tab"] == info["tab"])

    if plans:
        if apply:
            for p in plans:
                p.update(_outcome(p, bundle_dir, by=by, orcid=orcid, dry_run=False))
        else:
            with tempfile.TemporaryDirectory(prefix="isaac-answers-") as tmp:
                shutil.copy2(B.bundle_path(bundle_dir), Path(tmp) / B.BUNDLE_FILE)
                for p in plans:
                    p.update(_outcome(p, Path(tmp), by=by, orcid=orcid, dry_run=True))

    outcomes: dict[str, int] = {}
    for p in plans:
        outcomes[p["outcome"]] = outcomes.get(p["outcome"], 0) + 1
    new_requests = sum(1 for p in plans if p["outcome"] == "vocabulary_request_kept" and p.get("new"))
    by_kind: dict[str, int] = {}
    for p in problems:
        by_kind[p["problem"]] = by_kind.get(p["problem"], 0) + 1
    counts = {
        "answered_rows": answered_here, "answered_rows_other_beamtimes": answered_elsewhere,
        "decisions": len(plans), **{f"decisions_{k}": v for k, v in sorted(outcomes.items())},
        "vocabulary_requests_new_recorded": new_requests, "not_applied": len(problems), "not_applied_by_kind": by_kind,
        "free_text_rows": len(free_text), "athena_merge_rows": len(athena), "same_for_all": len(same_for_all),
    }
    recorded = outcomes.get("recorded", 0)
    if not answered_here:
        statement = (f"Nothing to apply: no row for this bundle ({folder or 'every row'}) has an answer. "
                     f"{q_rows_here} question-id rows are this bundle's; {q_unresolved} of them do not resolve.")
    elif apply:
        statement = (f"Recorded {recorded} decision(s) of {len(plans)} (the rest: "
                     f"{', '.join(f'{v} {k}' for k, v in sorted(outcomes.items()) if k != 'recorded') or 'none'}); "
                     f"{new_requests} new vocabulary request(s) kept. {len(problems)} answer(s) not applied, "
                     f"{len(free_text)} free-text and {len(athena)} Athena-merge row(s) to translate by hand.")
    else:
        statement = (f"Preview, nothing written: {len(plans)} decision(s) planned "
                     f"({', '.join(f'{v} {k}' for k, v in sorted(outcomes.items())) or 'none'}); {len(problems)} "
                     f"answer(s) not applied, {len(free_text)} free-text and {len(athena)} Athena-merge row(s) to "
                     "translate by hand. Add --apply to record (a copy first).")
    return {
        "format": FORMAT_ID, "format_version": FORMAT_VERSION, "applied": apply, "workbook": xlsx.name,
        "bundle_id": bundle.get("bundle_id"), "folder": folder, "statement": statement, "counts": counts,
        "id_rows": {"question_id_rows": q_rows, "for_this_bundle": q_rows_here, "not_resolving": q_unresolved,
                    "not_resolving_by_tab": unresolved_by_tab},
        "tabs": tab_rows,
        "unknown_tabs": [i["tab"] for i in tab_rows if i["kind"] == "unknown"],
        "decisions": plans, "not_applied": problems, "free_text": free_text, "athena_merges": athena,
        "same_for_all": same_for_all,
    }


# --- text ------------------------------------------------------------------------------------------------------


def _lines(items: Iterable[Mapping], fmt) -> list[str]:
    return [fmt(i) for i in items]


def render_report(rep: Mapping) -> str:
    out = [f"Workbook answers: {rep['workbook']} -> bundle {rep['folder'] or rep['bundle_id']} "
           f"({'APPLIED' if rep['applied'] else 'preview: nothing written'})", rep["statement"], "", "By tab:"]
    for t in rep["tabs"]:
        if t["kind"] == "info":
            out.append(f"  '{t['tab']}' (info): not read")
            continue
        others = f", {t['other_beamtimes']} other beamtimes" if t["other_beamtimes"] else ""
        out.append(f"  '{t['tab']}' ({t['kind']}): {t['rows']} rows, {t['for_this_bundle']} this bundle's{others}; "
                   f"{t['answered']} answered, {t['decisions']} decision(s), {t['problems']} not applied, "
                   f"{t['free_text']} to translate; {t['not_resolving']} id(s) not resolving")
    ids = rep["id_rows"]
    out += ["", f"Question-id rows: {ids['question_id_rows']} in the workbook, {ids['for_this_bundle']} this bundle's, "
                f"{ids['not_resolving']} not resolving" + (f" ({ids['not_resolving_by_tab']})" if ids["not_resolving"] else "")]
    if rep["decisions"]:
        out += ["", f"Decisions ({len(rep['decisions'])}), each the exact `bundle decide` it is:"]
        for p in rep["decisions"]:
            tail = p.get("reason") or p.get("statement") or ""
            out.append(f"  '{p['tab']}'!{p['cell']} [{p.get('ref')}{', for ' + p['for_row'] if p.get('for_row') else ''}] "
                       f"{p['outcome']}: {p['command']}")
            if tail:
                out.append(f"      {_clip(tail, 400)}")
            for f in p.get("follow_up") or ():
                out.append(f"      then: {f}")
            if p.get("also_from"):
                out.append(f"      same answer also in: {', '.join(p['also_from'])}")
    if rep["not_applied"]:
        out += ["", f"Not applied ({len(rep['not_applied'])}):"]
        out += _lines(rep["not_applied"], lambda p: f"  '{p['tab']}'!{p['cell']} [{p.get('ref')}] {p['problem']}: "
                                                    f"{p['reason']} (answer: {p.get('answer')!r})")
    if rep["free_text"]:
        out += ["", f"Free-text rows ({len(rep['free_text'])}): {HOW_FREE_TEXT}"]
        out += _lines(rep["free_text"], lambda f: f"  '{f['tab']}'!{f['cell']} [{f.get('ref')}, {f['kind']}] "
                                                  f"{f.get('topic') or ''}: {f.get('answer')!r}"
                                                  + (f" (notes: {f['notes']!r})" if f.get("notes") else ""))
    if rep["athena_merges"]:
        out += ["", f"Athena merges ({len(rep['athena_merges'])}): {HOW_ATHENA}"]
        for a in rep["athena_merges"]:
            out.append(f"  '{a['tab']}'!{a['cell']} [{a.get('ref')}] {a['athena_label']!r} in "
                       f"{', '.join(a['projects'])}: {a['answer']!r} -> {a['reading']}")
            if a["params_entry"]:
                out.append(f"      params: {json.dumps(a['params_entry'], ensure_ascii=False)}")
    if rep["same_for_all"]:
        out += ["", f"'same for all' ({len(rep['same_for_all'])}): {HOW_SAME_FOR_ALL}"]
        out += _lines(rep["same_for_all"], lambda s: f"  '{s['tab']}'!{s['cell']} [{s.get('ref')}] "
                                                     f"{s.get('notes') or s.get('answer')!r}")
    if rep["unknown_tabs"]:
        out += ["", f"Unknown tabs (not read): {', '.join(rep['unknown_tabs'])}"]
    return "\n".join(out)
