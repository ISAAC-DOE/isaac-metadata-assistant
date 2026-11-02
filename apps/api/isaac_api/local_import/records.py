"""From a reviewed bundle to official ISAAC records — compose, validate, export, dry-run.

``isaac bundle build-records`` — one ISAAC DRAFT (the repository's envelope format,
``draft_validator`` / ``export``) per ``scientist_confirmed`` record group. Values come
ONLY from:

* candidates that are ``scientist_confirmed`` AND eligible (decision value applied);
* ``missing_values`` a scientist answered (``confirm``/``correct`` with a value);
* the group's processing result a scientist APPROVED (series, qc, the E0 descriptor).

Beamtime-scope confirmed values (facility, beamline, technique, ...) apply to every
record EXCEPT ``context.environment``, ``context.electrochemistry.reaction`` and
``context.electrochemistry.cell_type`` (DEC-69: never filled from a beamtime fact).
Two confirmed values that differ for one path inside a group fill nothing and are
listed. Every required value nobody supplied stays a ``status: missing`` envelope and
is listed — nothing is defaulted, no temperature is assumed.

``isaac bundle validate`` — per draft: ``validate_draft`` → export DRY RUN through
``isaac_records.export.export_draft`` (writes nothing) → ``validate_official`` +
``check_exactness`` (vendored v1.05) → the OFFLINE upstream portal check
(:mod:`.portal`). Every error and warning is kept verbatim in
``validation/<group_id>.json`` with a plain-English summary. A disagreement between the
vendored and upstream schemas is reported as ``blocked_by_schema_drift`` — "blocked" for the WEBSITE's
vendored v1.05 schema only, which gates nothing here (the verdict is the portal schema's and the portal's).

``isaac bundle export`` — writes ``<ULID>.json`` + ``<ULID>.evidence.json`` ONLY for a
record that passes official validation AND whose portal outcome is ``publish``.

``isaac bundle upload --dry-run`` — prints what WOULD be sent. No network call, ever;
without ``--dry-run`` it refuses.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from . import bundle as B
from . import labels as L

DRAFTS_DIR = "drafts"
VALIDATION_DIR = "validation"
#: Never filled from a beamtime-scope value (DEC-69).
RUN_ONLY_PATHS = frozenset(
    {"context.environment", "context.electrochemistry.reaction", "context.electrochemistry.cell_type"}
)
SETPOINT_PATH = "context.electrochemistry.potential_setpoint_V"
SCALE_PATH = "context.electrochemistry.potential_scale"
SETPOINT_NEEDS_SCALE = ("a potential setpoint needs its confirmed potential_scale; the number alone does not say what it "
                        "is relative to")
SETPOINT_GROUP_NEEDS_SCALE = ("another run of this record group has this potential setpoint without its confirmed "
                              "potential_scale, so the group's setpoint is not filled")
#: c12-q: why the COMPANION is the missing item when a required field's confirmed value is held back beside it
#: (:data:`bundle.COMPOSES_ONLY_WITH`): the ``required_because`` of the companion's missing-required entry.
HELD_NEEDS_COMPANION = ("the record requires {path}, whose confirmed value ({value}) goes into the record only beside a "
                        "confirmed {companion} for every run it comes from (the number alone does not say what it is "
                        "relative to); answer {companion} and the confirmed value goes in: answering {path} again "
                        "changes nothing")
#: Why a value an ANSWER SLOT holds (``bundle.is_answer_slot``: one run's answer to a field asked once for the
#: whole beamtime) is not filled for a group some of whose runs have no answer for it (e.g. after a merge).
SLOT_NOT_EVERY_RUN = ("this answer was given for {answered} of this record group's {total} runs only (a per-run answer "
                      "to a field the import asks once for the whole beamtime: it belongs to those runs); {lacking} "
                      "{have} no answer for {path}, so the group fills nothing for it until every run has the same "
                      "answer: {how}")
#: The composer's ``from`` for a required value only an answer supplies (``questions.FROM_AN_ANSWER``).
FROM_AN_ANSWER = "a scientist's answer"
#: A file-name token that states a potential: a number with ``V`` / ``mV`` (``400mV``, ``m800mV``, ``1p2V``,
#: ``-0.5V``). Only RECOGNISES the statement, to warn that the record will not carry it: no value is read from it.
_POTENTIAL_TOKEN = re.compile(r"^(?:m|n|neg|minus|-|\+)?\d+(?:[p.]\d+)?m?V$", re.IGNORECASE)
STATED_POTENTIAL_WARNING = "stated_potential_not_in_record"
#: c16c: a record carries a set-point while a member run's FILE NAME and SCAN HEADER state different potentials and
#: no scientist has ruled on the header's reading (a decision on its candidate): the disagreement stays said.
POTENTIAL_SOURCES_WARNING = "potential_sources_disagree"
#: c16d: a record of runs whose scan headers write a local clock start time, written without it because the
#: scientist deferred the instrument clock's time zone ("I don't know"): said at validate, export, in the evidence
#: sidecar and the upload dry run, never left for the reader to notice.
START_TIME_WARNING = "start_time_left_out"
#: r5c C1: the approved processing result a record carries is not the Athena version the scientist's LATEST
#: ``select_athena_version`` names (a version approved before another was chosen, or ISAAC's own result approved before
#: a version was chosen): the record would carry a curve that is not the result of record. A warning, never a refusal.
ATHENA_NOT_CHOSEN_WARNING = "athena_version_no_longer_chosen"
#: r6h H2: a member run's ``macro_setpoint_disagrees`` conflict (a macro and the file name state other set-points for
#: one measurement) is unanswered: the record goes out with the file's set-point (or none) while that is open.
MACRO_SETPOINT_WARNING = "macro_setpoint_unanswered"
#: r6h H3: an in-situ record carries no electrolyte, cell type or control mode (what it was measured in).
IN_SITU_WARNING = "in_situ_conditions_not_in_record"
START_TIME_LEFT_OUT = "start time left out: instrument clock zone deferred (question {question})"
#: c16-r L6: the same, while the clock question has no answer at all (neither a zone nor a defer)
START_TIME_LEFT_OUT_UNANSWERED = "start time left out: instrument clock zone not answered yet (question {question})"
#: r4-b L5: the same, for a run whose start-time readings disagree (a SPEC `#D` local time beside its `#E` epoch) and
#: nobody has settled it: the UTC reading the files give is offered only inside that question
START_TIME_LEFT_OUT_CONFLICT = ("start time left out: the start-time disagreement is unanswered (question {question}; it "
                                "offers the UTC reading the files give, e.g. a scan's #E epoch)")
#: r6 review L3: ...while the beamtime-wide start-time question (questions.STATED_UTC_START_QUESTION_ID) reaches it too
START_TIME_LEFT_OUT_AT_ONCE = " Or answer every such group at once: question {beamtime}."
#: r6 review M2: a record that carries no start time because its runs were given DIFFERENT start times (a merged group,
#: each run its own): the composer fills nothing, and the record says so
START_TIME_LEFT_OUT_DIFFER = ("start time left out: this group's runs were given different start times ({values}); say "
                              "which run's start the record takes{question}")


@functools.lru_cache(maxsize=512)
def required_members_with(path: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """``((object path, its required members), ...)`` for each OPTIONAL object above ``path`` (below a record
    section) whose schema lists members it requires: once a record carries ``path``, it carries that object, and
    the object's ``required`` members with it — the schema's own rule, read from the vendored schema the
    composer's required list is read from (``bundle.required_record_paths``). The electrolyte is the case met:
    ``context.electrochemistry.electrolyte`` requires ``name`` AND ``concentration_M``, so a record with a name
    and no concentration fails the official schema. An array path is never one (composed from structured blocks)."""
    if "[]" in path:
        return ()
    parts = path.split(".")
    out = []
    for n in range(2, len(parts)):
        obj = ".".join(parts[:n])
        node = B._schema_node(obj) or {}
        req = node.get("required") if node.get("type") == "object" else None
        if isinstance(req, list) and req:
            out.append((obj, tuple(str(r) for r in req)))
    return tuple(out)


def _object_member_requirements(fields: Mapping[str, Mapping]) -> list[dict]:
    """The members an object the draft carries requires and the draft lacks: ``[{path, from, required_because}]``
    (:func:`required_members_with`), each once, in path order. A field the draft holds only as a ``missing``
    envelope carries nothing, so it requires nothing."""
    present = {p for p, env in fields.items() if (env or {}).get("status") != "missing"}
    out: dict[str, dict] = {}
    for p in sorted(present):
        for obj, members in required_members_with(p):
            for m in members:
                member = f"{obj}.{m}"
                if member in out or any(q == member or q.startswith(member + ".") for q in present):
                    continue
                out[member] = {"path": member, "from": FROM_AN_ANSWER,
                               "required_because": (f"the record carries {p}, so it carries {obj}, which the schema "
                                                    f"requires to hold {' and '.join(members)}")}
    return list(out.values())


def _id_key(target_id: str) -> str:
    return "value_id" if str(target_id).startswith("miss-") else "candidate_id"


def plain_record_note(note: str, group_id: str | None) -> str:
    """``note`` as a RECORD'S notes say it (c12-q LOW): without the import's internal group id (``for group
    rg-…``: in a record the curve is that record's own) and without the flag code in brackets
    (``(scientist_selected_subset_of_scans)``), which the sentence around it already says in words."""
    from .mutations import SCAN_SUBSET_FLAG

    if group_id:
        note = note.replace(f" for group {group_id} ", " ")
    return note.replace(f" ({SCAN_SUBSET_FLAG})", "")


def _present(fields: Mapping[str, Mapping], path: str) -> Mapping | None:
    """The envelope the draft CARRIES at ``path``, or ``None``: a ``missing`` placeholder carries nothing."""
    env = fields.get(path)
    return env if isinstance(env, Mapping) and env.get("status") != "missing" else None


def _said(value: Any, path: str) -> str:
    """A confirmed value as a sentence says it: a number at a volts path (``…_V``) as ``0.4 V``, else as JSON."""
    if path.endswith("_V") and isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g} V"
    return json.dumps(value)


#: How a required schema object is asked for as a scalar field.
REQUIRED_AS_FIELD = {"sample.material": "sample.material.name"}
#: Required paths that come from an approved processing result, not from fields.
STRUCTURED_REQUIRED = frozenset({"measurement.series", "measurement.qc.status", "descriptors.outputs"})
META = {"record_type": "evidence", "record_domain": "characterization", "source_type": "facility"}
#: DEC-76: an engine target path -> its home in the portal's (upstream) schema.
FIELD_REMAP = {"context.electrochemistry.reaction": "context.reaction.name"}
#: Approved processing step -> the upstream vocabulary token (measurement.processing.steps),
#: exactly as `data/vocabulary.json` @ a1cb1c8 spells it. `deglitch` and `qc` have none.
PROCESSING_STEP_VOCABULARY = {"calibration": "calibration", "merge": "spectrum_merging", "normalize": "normalization"}


def step_was_applied(step: Mapping) -> bool:
    """A processing step a record may list: one that CHANGED the data. A calibration whose shift was not
    applied (``outcome.applied`` false: no approved reference) and a "merge" of one scan are not; a
    step whose outcome states neither is listed as before."""
    outcome = step.get("outcome") if isinstance(step.get("outcome"), Mapping) else {}
    if step.get("step") == "calibration" and "applied" in outcome:
        return outcome["applied"] is True
    if step.get("step") == "merge" and isinstance(outcome.get("n_scans"), int):
        return outcome["n_scans"] > 1
    return True


PORTAL_VALIDATE = "/portal/api/validate"
PORTAL_RECORDS = "/portal/api/records"


class RecordsRefused(ValueError):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def _repo_root() -> Path:
    from .. import workspace as ws

    return ws.REPO_ROOT


# --- composition ----------------------------------------------------------------------------


def _vouched_by(candidate: Mapping, e: Mapping) -> set[str]:
    """The values ONE witness vouches for (JSON-canonical): :func:`bundle.witnessed_values` applied
    to that witness alone (its literal, its reader normalisations, and a ``derive`` step naming the
    candidate's own rule from a literal it states)."""
    return B.witnessed_values({"rule": candidate.get("rule"), "evidence": [e]})


#: ``provenance`` on the confirmation entry of a composed candidate value.
PROVENANCE_CONFIRMED = "scientist_confirmation"
PROVENANCE_CORRECTED = "scientist_correction"


def _instant(text: Any):
    """A zoned ISO-8601 instant as an aware ``datetime``, or ``None`` (a local time with no zone is NOT one)."""
    from datetime import datetime

    if not isinstance(text, str) or not text.strip():
        return None
    raw = text.strip()
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def same_value(path: str | None, a: Any, b: Any) -> bool:
    """Whether ``a`` and ``b`` are the SAME value for the field at ``path`` — what the evidence's
    ``relation`` and a confirmation's ``provenance`` are judged by. Numbers numerically (``1`` and ``1.0``
    are one value; the parser's reading is compared in the unit the parser normalised it to, the field's
    own, never re-converted here); a ``*_utc`` field's zoned instants as instants
    (``2100-01-01T00:10:00Z`` = ``2100-01-01T00:10:00+00:00``); a string otherwise EXACTLY (no case,
    space or fuzzy matching); anything else by its canonical JSON."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        if a == b:
            return True
        if path and path.endswith("_utc"):
            ia, ib = _instant(a), _instant(b)
            return ia is not None and ib is not None and ia == ib
        return False
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _vouches_for(candidate: Mapping, e: Mapping, path: str | None, value: Any) -> bool:
    """Whether ONE witness states ``value`` (:func:`same_value` against each value it vouches for)."""
    for canon in _vouched_by(candidate, e):
        try:
            stated = json.loads(canon)
        except ValueError:
            continue
        if same_value(path, stated, value):
            return True
    return False


#: r5 B1: what a record says of a notes sentence that names the cell only in passing (``bundle.passing_witness_term``)
PASSING_WITNESS_NOTE = ("the notes name the cell here only in passing, in a sentence about something else: it does not "
                        "state the value of record")


def _witnesses(candidate: Mapping, value: Any = None, decision: Mapping | None = None,
               zone_confirmed: Any = None) -> list[dict]:
    """The file's own statements for a composed candidate value, each with its ``relation``.

    ``relation`` is ALWAYS carried (``supports`` / ``contradicts`` / ``context``), never dropped. When
    the composed value is the parser's own value it is the relation the import recorded. When a
    scientist's decision gave ANOTHER value (``correct``, or a reading chosen on its conflict), the
    recorded relation was about the parser's value, not this one: it is kept as
    ``relation_to_parser_value`` and ``relation`` says whether the quote states the value of record
    (``supports``) or another value (``contradicts``) — a quote of the old value is never presented
    as support for the new one. r7 J4: a local clock time with no zone beside a UTC value of record is
    ``not_comparable`` (:data:`NOT_COMPARABLE`), never "contradicts". r7 review: once the clock's zone is
    confirmed and the witness carries its conversion (:data:`bundle.LOCAL_CLOCK_CONVERT_STEP`), the reading IS an
    instant and is compared as one. ``zone_confirmed``: a zero-argument callable (read only when needed) or a bool;
    ``None`` trusts the conversion step alone."""
    out = []
    path = candidate.get("target_field_path")
    # the SAME value (same_value: numerically, as an instant, or exactly) is not a replacement
    replaced = decision is not None and not same_value(path, value, candidate.get("value"))
    for e in candidate["evidence"]:
        if e["method"] == "ai_interpretation":
            continue  # an interpretation is not observed evidence
        entry = {
            "source_type": "document",
            "source_file": e["relative_path"] or "(unlocated)",
            "locator": e["locator"],
            "quote": e["literal_value"] if isinstance(e["literal_value"], str) else json.dumps(e["literal_value"]),
            "method": e["method"],
            "method_id": e["method_id"],
            "relation": e.get("relation"),
        }
        if B.passing_witness_term(candidate, e) is not None:
            # r5 B1: the notes name the cell only in passing here: never cited as support for any value of record
            entry["relation_to_parser_value"] = e.get("relation")
            entry["relation"] = "context"
            entry["note"] = PASSING_WITNESS_NOTE
        elif replaced:
            entry["relation_to_parser_value"] = e.get("relation")
            entry["relation"] = "supports" if _vouches_for(candidate, e, path, value) else "contradicts"
            if entry["relation"] == "contradicts" and _zone_less_clock(path, e.get("literal_value"), value) and not (
                    _converted_with_zone(e) and _zone_said(zone_confirmed)):
                # r7 J4: a local clock time with no zone is not an instant: it neither supports nor contradicts one
                entry["relation"] = NOT_COMPARABLE
                entry["note"] = NOT_COMPARABLE_NOTE
            elif entry["relation"] == "contradicts":
                entry["note"] = ("the file states another value; the value of record is the scientist's decision, "
                                 "not this quote")
        out.append(entry)
    return out


#: r7 J4: the ``relation`` of a witness that states a local clock time with no time zone, beside a UTC value of record.
NOT_COMPARABLE = "not_comparable"
NOT_COMPARABLE_NOTE = ("a local clock time with no time zone: not comparable with the UTC value of record until the "
                       "clock's time zone is stated")


def _converted_with_zone(e: Mapping) -> bool:
    """r7 review: the witness carries a local-clock-to-UTC conversion under a confirmed zone."""
    return any(isinstance(n, Mapping) and n.get("step") == B.LOCAL_CLOCK_CONVERT_STEP for n in e.get("normalization") or ())


def _zone_said(zone_confirmed: Any) -> bool:
    """Whether the instrument clock's zone is confirmed (``None``: not known here, so the conversion step is trusted)."""
    if zone_confirmed is None:
        return True
    return bool(zone_confirmed() if callable(zone_confirmed) else zone_confirmed)


def _zone_less_clock(path: str | None, literal: Any, value: Any) -> bool:
    """r7 J4: whether ``literal`` is a date and time with NO zone (a SPEC ``#D`` line, ``Sat Nov 13 20:52:09 2021``) while
    the value of record of the ``*_utc`` field at ``path`` is a zoned instant: the two cannot be compared."""
    if not (path and path.endswith("_utc") and isinstance(literal, str)) or _instant(value) is None:
        return False
    if _instant(literal) is not None or literal.strip().isdigit():  # an instant, or an epoch: comparable
        return False
    if B.read_xdc_literal(" ".join(literal.split())) is not None:
        return True
    from datetime import datetime

    try:
        return datetime.fromisoformat(literal.strip()).tzinfo is None
    except ValueError:
        return False


def _candidate_confirmation(candidate: Mapping, decision: Mapping, value: Any, path: str, witnesses: Sequence[Mapping]) -> dict:
    """The scientist's confirmation of a composed candidate value, with its PROVENANCE: a
    ``scientist_correction`` (``correct``, or a value no file witness states) names the value it
    replaced (``previous_value``, the parser's); a ``scientist_confirmation`` is of a value the files state.
    A ``correct`` whose value IS the parser's (:func:`same_value`: ``1`` for ``1.0``, ``...Z`` for
    ``...+00:00``) changed nothing: it is a confirmation, with no ``previous_value``."""
    entry = _confirmation({**decision, "value": value}, f"Confirm {path}")
    stated = any(w.get("relation") == "supports" for w in witnesses)
    changed = not same_value(path, value, candidate.get("value"))
    corrected = (decision.get("decision") == "correct" and changed) or not stated
    entry["provenance"] = PROVENANCE_CORRECTED if corrected else PROVENANCE_CONFIRMED
    if changed:
        entry["previous_value"] = candidate.get("value")
        entry["previous_value_basis"] = ("the parser's value for this candidate" if candidate.get("value") is not None
                                         else "the parser gave no single value (the sources disagree or state none)")
    return entry


def _confirmation(decision: Mapping, question: str) -> dict:
    by = decision.get("decided_by") or {}
    entry = {
        "source_type": "user_confirmation",
        "question": question,
        "answer": decision.get("value") if isinstance(decision.get("value"), str) else json.dumps(decision.get("value")),
        "timestamp": decision.get("decided_utc"),
        "decision_id": decision.get("decision_id"),
        "decided_by": by.get("name"),
        "identity": by.get("identity", "local_unverified"),
    }
    if by.get("orcid_claimed"):
        entry["orcid_claimed"] = by["orcid_claimed"]["value"]
    return entry


def _absorber_implicit(bundle: Mapping, group: Mapping, absorber_decisions: Mapping | None = None) -> list[dict]:
    """``implicit[]`` entries ``absorbing_element`` and ``edge`` for one group, or ``[]``."""
    from . import suggestions as S

    sug = S.absorber_for_group(bundle, group)
    decision = (S.absorber_decisions(bundle) if absorber_decisions is None else absorber_decisions).get(group["group_id"])
    witnesses = [
        {"source_type": "document", "source_file": w.get("relative_path") or "(unlocated)", "locator": w.get("locator"),
         "quote": w.get("literal") or f"{w.get('element') or ''} {w.get('edge') or ''}".strip(),
         "quote_basis": "the file's own statement" if w.get("literal") else f"as the {w.get('role') or 'reader'} rule recorded it, not a literal",
         "method": "stored_rule", "method_id": S.ABSORBER_RULE_ID}
        for w in sug["witnesses"]
    ]
    if decision is None and not witnesses:
        return []
    out = []
    for about, key in (("absorbing_element", "element"), ("edge", "edge")):
        evidence = list(witnesses) or [{"source_type": "derivation", "rule": f"{S.ABSORBER_RULE_ID}: no file states it"}]
        value = None
        if decision is not None:
            value = decision.get(key)
            evidence.append(_confirmation({**decision, "value": value}, f"What is the {about.replace('_', ' ')}?"))
        else:
            evidence.append({"source_type": "derivation",
                             "rule": f"{S.ABSORBER_RULE_ID}: the files suggest {sug[key] or 'nothing single'} ({sug['status']}); "
                                     "needs a scientist's confirmation (set_absorber)"})
        out.append({"about": about, "value": value, "evidence": evidence})
    return out


#: The processing output contract (LOCAL-P ``processing/run.py``, ``normalized.csv``):
#: a ``#`` banner, then the header ``energy_eV,norm,flat``. Columns are selected BY NAME.
SERIES_ENERGY_COLUMN = "energy_eV"
SERIES_SIGNAL_COLUMN = "norm"
SPECTRUM_ROLES = ("normalized", "normalized_spectrum")


def _read_series_file(path: Path) -> tuple[list[float], list[float]] | str:
    """``(energy, normalised mu)`` from a processing output, or the REASON it was refused.

    A header line names the columns and they are selected by name (energy_eV, norm);
    ``flat`` is not read. A headerless file of exactly two numeric columns is still read
    as (energy, signal). Blank cells and non-numeric rows refuse the file — nothing is
    guessed or interpolated."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return f"the file could not be read ({type(exc).__name__})"
    rows = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if not rows:
        return "the file holds no data rows"
    first = [c.strip() for c in rows[0].replace("\t", ",").split(",")] if "," in rows[0] or "\t" in rows[0] else rows[0].split()

    def numeric(cells):
        try:
            [float(c) for c in cells]
            return True
        except ValueError:
            return False

    if numeric(first):
        xi, yi, data = 0, 1, rows
        if len(first) != 2:
            return f"a headerless file must have exactly two numeric columns; it has {len(first)}"
    else:
        if SERIES_ENERGY_COLUMN not in first or SERIES_SIGNAL_COLUMN not in first:
            return f"the header {first!r} does not name {SERIES_ENERGY_COLUMN!r} and {SERIES_SIGNAL_COLUMN!r}"
        xi, yi, data = first.index(SERIES_ENERGY_COLUMN), first.index(SERIES_SIGNAL_COLUMN), rows[1:]
    xs: list[float] = []
    ys: list[float] = []
    for n, row in enumerate(data, 1):
        cells = [c.strip() for c in row.split(",")] if "," in row else row.split()
        try:
            xs.append(float(cells[xi]))
            ys.append(float(cells[yi]))
        except (ValueError, IndexError):
            return f"data row {n} has no number in the {SERIES_ENERGY_COLUMN}/{SERIES_SIGNAL_COLUMN} columns"
    return (xs, ys) if xs else "the file holds no data rows"


def composition_index(bundle: Mapping, decision_of: Mapping[tuple[str, str], Mapping] | None = None) -> dict:
    """What :func:`compose_group` reads from the WHOLE bundle (the decision log, the conflicts, the processing
    results), read once. A caller composing many groups of ONE bundle builds it once and passes it to each
    call, so composing every group is linear in the bundle, not (groups x decisions); the result is exactly
    what each call would build for itself. Never reused across a change to the bundle. ``decision_of``:
    :func:`bundle._decisions_by_target` of this bundle, when the caller already built it."""
    from . import suggestions as S

    results = bundle.get("processing_results") or ()
    return {
        "decisions": B._decisions_by_target(bundle.get("scientist_decisions") or ()) if decision_of is None else decision_of,
        "conflict_ids_of": B.conflict_ids_by_candidate(bundle),
        "processing_blocked": B.processing_blocked_groups(bundle),
        # read only for an approved result: none, nothing to read
        "processing_state": (B.processing_state_decisions(bundle)
                             if any(r.get("state") == B.STATE_SCIENTIST_CONFIRMED for r in results) else {}),
        "absorber": S.absorber_decisions(bundle),
        "processing_of": _processing_by_group(bundle),
        "runs_by_key": {r["run_key"]: r for r in bundle["runs"]},
        # every value by its id (a group's own values are among them: the same objects): its run, and its kind
        "run_of": {**{c["candidate_id"]: c["run_id"] for c in bundle["candidates"]},
                   **{m["value_id"]: m["run_id"] for m in bundle["missing_values"]}},
        "obj_of": {**{c["candidate_id"]: ("candidate", c) for c in bundle["candidates"]},
                   **{m["value_id"]: ("missing_value", m) for m in bundle["missing_values"]}},
        # read when first needed, then kept: B.required_record_paths(control_mode=...) per mode (it reads the
        # schema file each call), and B.clock_zone_decision (only a confirmed local-clock start time asks for it)
        "required_by_mode": {},
        # read from the WHOLE bundle here, never lazily inside compose_group: a group is composed from its own
        # values only, so a lazy read would keep the first group's view for every group
        "memo": {"local_clock_runs": local_clock_runs(bundle), "open_start_conflicts": (opened := open_start_conflicts(bundle)),
                 "athena_choices": athena_choices(bundle),
                 # r6 review L3: which open start-time disagreements the beamtime-wide question reaches (whole bundle)
                 "beamtime_start_reach": _beamtime_start_reach(bundle, opened) if opened else set()},
    }


_ISAAC_RESULT_ID = re.compile(r"^proc-(?P<group>.+)-r-[0-9a-f]{16}-isaac$")


def athena_choices(bundle: Mapping) -> dict:
    """r5c C1: ``{group_id: (latest select_athena_version decision, its position in the log)}``, the choice made on
    any ISAAC result of the group (as ``isaac process`` reads it: by the result's group, or its id's), plus what
    :func:`athena_choice_mismatch` reads, so a caller composing many groups reads the bundle ONCE (r5c review MED-2):
    ``"_position"`` (every decision id's position), ``"_select_by_id"`` (each select decision by id) and
    ``"_athena_of"`` (each group's Athena-version results). ``{}`` when no version was ever chosen."""
    decisions = bundle.get("scientist_decisions") or ()
    if not any(d.get("decision") == B.ATHENA_SELECT_DECISION for d in decisions):
        return {}
    results = bundle.get("processing_results") or ()
    group_of = {B.processing_id(r): r.get("group_id") for r in results if r.get("source") == "isaac_protocol"}
    out: dict = {"_position": {}, "_select_by_id": {}, "_athena_of": {}}
    for r in results:
        if r.get("source") == "scientist_athena" and r.get("athena_version_id"):
            out["_athena_of"].setdefault(r.get("group_id"), []).append(r)
    for i, d in enumerate(decisions):
        out["_position"][d.get("decision_id")] = i
        t = d.get("target") or {}
        if d.get("decision") != B.ATHENA_SELECT_DECISION or t.get("kind") != "processing_result":
            continue
        out["_select_by_id"][d.get("decision_id")] = d
        m = _ISAAC_RESULT_ID.match(str(t.get("id")))
        gid = group_of.get(t.get("id")) or (m.group("group") if m else None)
        if gid:
            out[gid] = (d, i)
    return out


def _choice_identity(decision: Mapping | None) -> str | None:
    """The version a ``select_athena_version`` names, by its own provenance (never its positional id)."""
    if not isinstance(decision, Mapping):
        return None
    prov = decision.get("athena_version_provenance")
    if isinstance(prov, Mapping):
        return json.dumps({k: prov.get(k) for k in B.ATHENA_IDENTITY_KEYS}, sort_keys=True)
    return json.dumps({"decision_id": decision.get("decision_id")})


def _same_project_curve(result: Mapping, decision: Mapping) -> bool:
    """r5c review LOW-1: an Athena result with no version id (the default ``…-athena`` result) that USES the curve the
    choice names: one of its used inputs is that project file and that Athena group."""
    prov = decision.get("athena_version_provenance")
    if not isinstance(prov, Mapping) or not prov.get("prj_relative_path") or not prov.get("athena_group"):
        return False
    return any(i.get("relative_path") == prov["prj_relative_path"] and i.get("athena_group") == prov["athena_group"]
               and i.get("used", True) for i in result.get("inputs") or () if isinstance(i, Mapping))


def athena_choice_mismatch(bundle: Mapping, group_id: str, approved: Mapping, choices: Mapping | None = None,
                           state: Mapping | None = None) -> dict | None:
    """r5c C1: what is wrong when the ONE approved result of ``group_id`` is not the Athena version the scientist's
    latest choice names, else ``None``: ``{approved_result_id, approved_version_id, approved_kind, chosen_value,
    choice_decision_id, chosen_result_id}``. An approved Athena-version result of ANOTHER version is always a mismatch;
    an approved result that is no chosen version (ISAAC's own, or the default Athena result of another curve) only when
    the choice was recorded AFTER its approval (approving it after choosing a version is the scientist's later word, as
    the skill says). ``choices`` (:func:`athena_choices`) and ``state`` (``bundle.processing_state_decisions``): read
    once by a caller deciding many groups; never re-read here."""
    choices = athena_choices(bundle) if choices is None else choices
    got = choices.get(group_id)
    if not got:
        return None
    latest, at = got
    want = _choice_identity(latest)
    pid = B.processing_id(approved)
    by_id = choices["_select_by_id"]
    athena = approved.get("source") == "scientist_athena"
    if athena and approved.get("athena_version_id"):
        made = (approved.get("athena_version_selected") or {}).get("decision_id")
        if made is not None and _choice_identity(by_id.get(made)) == want:
            return None
    else:
        if athena and _same_project_curve(approved, latest):
            return None  # the default Athena result IS the chosen curve
        approval = (B.processing_state_decisions(bundle) if state is None else state).get(("processing_result", pid))
        if approval is None or choices["_position"].get(approval.get("decision_id"), -1) > at:
            return None
    chosen = [r for r in choices["_athena_of"].get(group_id, ())
              if _choice_identity(by_id.get((r.get("athena_version_selected") or {}).get("decision_id"))) == want
              and r.get("state") != B.STATE_REJECTED]
    return {"approved_result_id": pid, "approved_version_id": approved.get("athena_version_id"),
            "approved_kind": "athena_version" if approved.get("athena_version_id") else ("athena" if athena else "isaac"),
            "chosen_value": latest.get("value"), "choice_decision_id": latest.get("decision_id"),
            "choice_target_id": (latest.get("target") or {}).get("id"),
            "chosen_result_id": B.processing_id(chosen[0]) if chosen else None}


def athena_choice_text(m: Mapping, group_id: str) -> str:
    """The plain sentences for :func:`athena_choice_mismatch`: what the record carries, the steps that make it carry
    the chosen version, and (r5c review LOW-2) the step that keeps the approved curve (each a command to run only with
    the scientist's answer)."""
    kind = m.get("approved_kind") or ("athena_version" if m.get("approved_version_id") else "isaac")
    what = {"athena_version": f"Athena version {m.get('approved_version_id')}",
            "athena": "the scientist's Athena curve from another project or Athena group"}.get(kind, "ISAAC's own curve")
    reject = f'isaac bundle decide <bundle_dir> --target {m["approved_result_id"]} --decision reject --by "<your name>"'
    approve_again = (f'isaac bundle decide <bundle_dir> --target {m["approved_result_id"]} --decision approve '
                     '--qc-status <status> --by "<your name>"')
    if kind == "athena_version" and m.get("choice_target_id"):
        # a version result is kept by choosing its version again (re-approving it leaves the later choice standing)
        keep = (f"choose {m['approved_version_id']} again (`isaac bundle decide <bundle_dir> --target "
                f"{m['choice_target_id']} --decision select_athena_version --value {m['approved_version_id']} "
                '--by "<your name>"`)')
    else:
        keep = f"reject it and approve it again (`{reject}`, then `{approve_again}`)"
    if m.get("chosen_result_id"):
        steps = (f"reject {m['approved_result_id']} (`{reject}`), then approve {m['chosen_result_id']} "
                 f'(`isaac bundle decide <bundle_dir> --target {m["chosen_result_id"]} --decision approve --qc-status '
                 '<status> --by "<your name>"`)')
    else:
        steps = (f"run `isaac process <bundle_dir> --source <the beamtime folder you imported> --group {group_id}` "
                 f"(it builds the chosen version's own result), then reject {m['approved_result_id']} (`{reject}`), "
                 "then approve the new result")
    return (f"The approved result {m['approved_result_id']} is {what}. The scientist's latest choice of the result of "
            f"record is {m['chosen_value']} ({m['choice_decision_id']}). The record carries the E0 and curve of "
            f"{m['approved_result_id']}, not of {m['chosen_value']}. To carry the chosen version: {steps}. Or, to keep "
            f"this curve, {keep}. Ask the scientist before each step.")


def _processing_by_group(bundle: Mapping) -> dict[str, list]:
    out: dict[str, list] = {}
    for r in bundle.get("processing_results") or ():
        out.setdefault(r["group_id"], []).append(r)
    return out


def _unconfirmed_carried_shift(bundle: Mapping, result: Mapping, index: Mapping) -> dict | None:
    """:func:`processing.reference.carried_shift` of an approved ISAAC result when its curve carries a calibration
    shift the current rules would not apply and the scientist has not confirmed (``None`` otherwise)."""
    if result.get("source") != "isaac_protocol":
        return None
    steps = {s.get("step"): s for s in result.get("steps") or () if isinstance(s, Mapping)}
    cal = steps.get("calibration")
    if cal is None or not (cal.get("outcome") or {}).get("applied"):
        return None
    from .mutations import calibration_approvals
    from .processing import reference as REF

    memo = index.setdefault("memo", {})
    if "calibration_approvals" not in memo:
        memo["calibration_approvals"] = calibration_approvals(bundle)
    warn = ((steps.get("qc") or {}).get("params") or {}).get("warn_energy_shift_eV")
    c = REF.carried_shift(cal, memo["calibration_approvals"].get(result.get("group_id")), warn_eV=warn,
                          group_id=result.get("group_id"), result_id=B.processing_id(result))
    return c if c is not None and not c["confirmed"] else None


def compose_group(bundle: Mapping, group: Mapping, bundle_dir: Path, index: dict | None = None) -> tuple[dict, dict]:
    """``(draft, composition_report)`` for ONE scientist-confirmed record group. ``index``
    (:func:`composition_index` of this same bundle) saves re-reading the whole bundle per group."""
    if index is None:
        index = composition_index(bundle)
    decisions = index["decisions"]
    runs_by_key = index["runs_by_key"]
    member_runs = [runs_by_key[k] for k in group["member_run_keys"] if k in runs_by_key]
    member_ids = {r["run_id"] for r in member_runs}
    # r5 B5 (review H1): a run the group keeps as CONTEXT (an exported file of a run, its data not merged) is no
    # measurement run: its values fill nothing, and a field is covered when every MEASUREMENT run is (no question asks
    # about a context run, so counting it would leave a field unfillable)
    context_keys = set(group.get("context_run_keys") or ())
    measured_ids = {r["run_id"] for r in member_runs if r["run_key"] not in context_keys}
    report: dict[str, Any] = {
        "group_id": group["group_id"],
        "member_run_ids": sorted(member_ids),
        "filled": [],
        "disagreements": [],
        "missing_required": [],
        "not_composed": [],
        "processing": None,
    }
    proposals: dict[str, list[tuple[Any, list, str]]] = {}

    def _confirmed_but_unfit(obj: Mapping, id_key: str) -> None:
        # A scientist's answer the official field cannot hold (e.g. "-0.8 V" for a number) is
        # never composed; it is SAID, so it cannot vanish from the record unseen.
        if obj["value_state"] == B.STATE_SCIENTIST_CONFIRMED and (obj["run_id"] in measured_ids or obj["run_id"] is None):
            report["not_composed"].append({id_key: obj[id_key], "path": obj["target_field_path"],
                                           "reason": obj["eligibility_for_official_record"]["reason"]})

    zone_memo: list[bool] = []

    def zone_confirmed() -> bool:
        # r7 review: read once per composition, and only when a converted #D witness needs it
        if not zone_memo:
            zone_memo.append(B.clock_zone_decision(bundle) is not None)
        return zone_memo[0]

    for c in bundle["candidates"]:
        if not c["eligibility_for_official_record"]["eligible"]:
            _confirmed_but_unfit(c, "candidate_id")
            continue
        in_group = c["run_id"] in measured_ids
        beamtime = c["run_id"] is None
        if not (in_group or beamtime):
            continue
        path = c["target_field_path"]
        if beamtime and path in RUN_ONLY_PATHS:
            report["not_composed"].append({"candidate_id": c["candidate_id"], "reason": "DEC-69: a beamtime fact never fills this run-level field"})
            continue
        if "[]" in path:
            report["not_composed"].append({"candidate_id": c["candidate_id"], "path": path, "reason": "an array path; composed only from structured blocks"})
            continue
        d = B.candidate_decision(bundle, c, decisions, index["conflict_ids_of"])
        value = B.final_value(c["value"], d, c.get("readings"))
        witnesses = _witnesses(c, value, d, zone_confirmed)
        evidence = witnesses + [_candidate_confirmation(c, d, value, path, witnesses)]
        if B.is_local_clock_start(c) and d.get("decision") == "confirm":
            # The value is the file's local clock time converted under the zone a scientist stated
            # for the INSTRUMENT CLOCK: that statement is part of the value's evidence. (A `correct`
            # gives its own UTC value, so no zone stands behind it.) DEFENCE IN DEPTH: the zone is
            # credited ONLY when the composed value IS what the rule produced under that zone and
            # the confirmation is bound to it — never for a value the rule did not give.
            memo = index["memo"]
            if "clock_zone" not in memo:
                memo["clock_zone"] = B.clock_zone_decision(bundle)
            zone_d = memo["clock_zone"]
            binding = d.get("clock_zone_binding") or {}
            produced = B.local_clock_start(c, zone_d)["value"] if zone_d is not None else None
            if (zone_d is not None and produced is not None and value == produced
                    and binding.get("value") == produced and binding.get("zone") == zone_d.get("value")):
                evidence.append(_confirmation(zone_d, B.CLOCK_ZONE_QUESTION)
                                | {"rule_id": B.CLOCK_ZONE_RULE_ID, "local_time": (c.get("local_clock") or {}).get("local_time")})
        # DEC-76: the reaction's home in the portal's schema is context.reaction.name;
        # context.electrochemistry.reaction is deprecated there.
        proposals.setdefault(FIELD_REMAP.get(path, path), []).append((value, evidence, c["candidate_id"]))

    for m in bundle["missing_values"]:
        if not m["eligibility_for_official_record"]["eligible"]:
            _confirmed_but_unfit(m, "value_id")
            continue
        if not (m["run_id"] in measured_ids or m["run_id"] is None):
            continue
        d = decisions[("missing_value", m["value_id"])]
        value = B.final_value(None, d)
        asked = L.slot_question_text(m) if L.is_label_slot(m) else f"What is {m['target_field_path']}?"
        proposals.setdefault(FIELD_REMAP.get(m["target_field_path"], m["target_field_path"]), []).append(
            (value, [_confirmation(d, asked)], m["value_id"])
        )

    run_of = index["run_of"]

    fields: dict[str, dict] = {}
    for path, options in sorted(proposals.items()):
        distinct = {json.dumps(v, sort_keys=True) for v, _, _ in options}
        if len(distinct) > 1:
            report["disagreements"].append(
                {"path": path, "values": [v for v, _, _ in options], "from": [i for _, _, i in options],
                 "reason": "confirmed values differ inside one record group; nothing is filled"}
            )
            continue
        value = options[0][0]
        evidence = [e for _, ev, _ in options for e in ev]
        fields[path] = {"value": value, "status": "verified", "evidence": evidence}
        report["filled"].append({"path": path, "from": [i for _, _, i in options]})
    # AN ANSWER SLOT BELONGS TO ITS RUN (c7-r MED-3): a slot holds one run's answer to a field the import asks once for
    # the whole beamtime. A group (a merged one, say) fills the field from slots only when EVERY member run is covered
    # — by a slot or an answer of its own (the same value, or the check above already said they differ), or by the
    # beamtime-wide answer — never one run's answer stretched over runs no one answered.
    obj_of_any = index["obj_of"]
    held_by_slots: dict[str, str] = {}
    for f in list(report["filled"]):
        # a condition label's slot (labels.py) belongs to its run the same way
        slots = [i for i in f["from"] if obj_of_any.get(i, (None, None))[0] == "missing_value"
                 and (B.is_answer_slot(obj_of_any[i][1]) or L.is_label_slot(obj_of_any[i][1]))]
        covered = {run_of.get(i) for i in f["from"]}
        if not slots or None in covered or not (measured_ids - covered):
            continue
        path = f["path"]
        lacking = sorted(measured_ids - covered)
        qid = next((q for i in slots if (q := B.answer_slot_question(obj_of_any[i][1]) or L.slot_question(obj_of_any[i][1]))),
                   None)
        how = (f"`isaac bundle decide <bundle_dir> --question {qid} --only group:{group['group_id']} --decision correct "
               '--value <value> --by "<your name>"` (it records every run of this group), or answer that question for '
               "the whole beamtime" if qid else
               f"answer it for this group (`isaac bundle questions <bundle_dir> --scope group:{group['group_id']}`)")
        reason = SLOT_NOT_EVERY_RUN.format(answered=len(measured_ids & covered), total=len(measured_ids),
                                           lacking=", ".join(lacking[:5]) + ("…" if len(lacking) > 5 else ""),
                                           have="has" if len(lacking) == 1 else "have", path=path, how=how)
        del fields[path]
        report["filled"].remove(f)
        held_by_slots[path] = reason
        for i in f["from"]:
            report["not_composed"].append({_id_key(i): i, "path": path, "reason": reason})
    # A SET-POINT NEEDS ITS SCALE (interim decision, pending domain-owner review): the number alone
    # does not say what it is relative to. AFTER the disagreement check above (so differing
    # set-points are a disagreement, never hidden by this gate), an agreed set-point is filled only
    # when EVERY run it comes from has an eligible scale filled in this draft (or the scale is
    # beamtime-wide). If any run lacks one, NONE is filled: each of its own values says why.
    # c12-q: what was held, and by which companion: when the record REQUIRES the held field, the missing item is the
    # companion (answering the held value again changes nothing), so the required list below names it instead.
    held_by_companion: dict[str, tuple[str, Any]] = {}
    for path, companion in B.COMPOSES_ONLY_WITH.items():
        if path not in fields:
            continue
        from_ids = next(f for f in report["filled"] if f["path"] == path)["from"]
        covered = {run_of.get(i) for _, _, i in proposals.get(companion, ())} if companion in fields else set()
        lacking = [i for i in from_ids if not (run_of.get(i) in covered or None in covered)]
        if lacking:
            held_by_companion[path] = (companion, fields[path]["value"])
            del fields[path]
            report["filled"] = [f for f in report["filled"] if f["path"] != path]
            for i in from_ids:
                report["not_composed"].append({_id_key(i): i, "path": path,
                                               "reason": SETPOINT_NEEDS_SCALE if i in lacking else SETPOINT_GROUP_NEEDS_SCALE})
    # NEVER SILENT: a composed value on a path the build that first stored this bundle could not
    # write, whose GOVERNING decision was made before this build upgraded the bundle (under the old
    # wording, "this build cannot write it yet"). A decision made after the upgrade, under the
    # corrected wording, is not listed: the scientist answered knowing the field is written.
    obj_of = index["obj_of"]
    report["composed_only_by_this_build"] = []
    for f in report["filled"]:
        for i in f["from"]:
            kind, obj = obj_of.get(i, (None, None))
            if obj is None:
                continue
            d = (B.candidate_decision(bundle, obj, decisions, index["conflict_ids_of"]) if kind == "candidate"
                 else decisions.get(("missing_value", i)))
            u = B.upgraded_before(bundle, obj.get("target_field_path"), d)
            if u is not None:
                report["composed_only_by_this_build"].append({
                    _id_key(i): i, "path": f["path"], "decision_id": d.get("decision_id"),
                    "from_format_version": u["from_format_version"],
                    "reason": (f"confirmed ({d.get('decision_id')}) before this build upgraded the bundle from "
                               f"{u['from_format_version']}, when the build said it could not write {obj.get('target_field_path')}; "
                               "the confirmation was about the value, so it composes now"),
                })

    # THE CONDITION LABELS that are no scalar field (labels.py): the beamtime tag goes into the draft's tags; the
    # follows label names a run, so its link is resolved to that run's record id at export (export_records)
    taken = L.take_from_fields(fields, report)
    draft: dict[str, Any] = {
        "meta": dict(META),
        "fields": fields,
        "assets": [],
        "descriptors_outputs": [],
        "links": [],
        "implicit": [],
        "block_evidence": {},
    }
    if taken.get("tags"):
        draft["tags"] = taken["tags"]
        draft["block_evidence"]["tags"] = taken["tags_evidence"]
    if taken.get("follows"):
        report["follows"] = taken["follows"]

    # THE ABSORBER (sidecar only: the official schema has no field for it). A scientist's
    # set_absorber decision gives the value; otherwise the files' suggestion is carried with
    # value null, exactly as the hosted path carries an unconfirmed edge.
    absorber = _absorber_implicit(bundle, group, index["absorber"])
    if absorber:
        draft["implicit"] += absorber
        report["absorber"] = {"element": absorber[0]["value"], "edge": absorber[1]["value"],
                              "confirmed": absorber[0]["value"] is not None}

    # processing (series, qc, E0 descriptor) — ONLY an approved result
    chose_other = None  # r5c C1: the approved result is not the scientist's latest Athena choice
    mine = list(index["processing_of"].get(group["group_id"], ()))
    approved = [r for r in mine if r["state"] == B.STATE_SCIENTIST_CONFIRMED and not B.processing_not_applicable(r)]
    # A group whose LATEST result says the protocol does not apply cannot get an approved
    # curve from it: that is a blocking reason in its own words, never a fake approval.
    latest_na = index["processing_blocked"].get(group["group_id"])
    not_applicable = [latest_na] if latest_na else []
    blocked_by_protocol = latest_na is not None
    if len(approved) > 1:
        # NEVER "no processing result": there are two (or more), and the record uses exactly one of them
        report["processing"] = {"used": None, "reason": "more than one approved processing result; a person chooses one",
                                "group_id": group["group_id"], "approved_results": [B.processing_id(r) for r in approved]}
    elif approved and (approved[0].get("outputs") or {}).get("files") and unusable_curve_reasons(approved[0]):
        # c8-r: AN APPROVAL AN OLDER BUILD LET THROUGH for a curve whose QC says it is NOT A USABLE SPECTRUM
        # (mutations.UNUSABLE_CURVE_REASONS; `decide` refuses that approval now). Nothing from it composes — no
        # series, QC status, steps or E0 — so the record is blocked, as an approved result with no curve is.
        r = approved[0]
        reasons = unusable_curve_reasons(r)
        statements = (r.get("qc") or {}).get("statements") or {}
        report["processing"] = {
            "used": None, "result": B.processing_id(r), "group_id": group["group_id"],
            "unusable_curve": ", ".join(reasons),
            **({"unusable_curve_said": " ".join(str(statements[x]) for x in reasons if statements.get(x))}
               if any(statements.get(x) for x in reasons) else {}),
            "reason": "the approved processing result is not a usable spectrum; nothing from it is used",
        }
    elif approved and (carried := _unconfirmed_carried_shift(bundle, approved[0], index)) is not None:
        # c12-r: AN APPROVAL AN OLDER BUILD LET THROUGH for a curve that carries a calibration shift the current rules
        # would not apply (an in-scan reference usable in one scan; a large shift whose size nobody confirmed). It is
        # kept on re-processing (decided), so nothing from it composes until the scientist confirms the size
        # (approve_calibration --accept-shift) or rejects the result: never exported silently.
        r = approved[0]
        report["processing"] = {
            "used": None, "result": B.processing_id(r), "group_id": group["group_id"],
            "calibration_unconfirmed": carried["statement"], "calibration_unconfirmed_shift_eV": carried["applied_shift_eV"],
            "reason": "the approved processing result carries a calibration shift that is now unconfirmed; nothing from it is used",
        }
    elif approved:
        r = approved[0]
        pid = B.processing_id(r)
        chose_other = athena_choice_mismatch(bundle, group["group_id"], r, index["memo"].get("athena_choices") or {},
                                             index["processing_state"])
        # the APPROVAL (latest state decision): a later select_athena_version never stands in for it
        d = index["processing_state"][("processing_result", pid)]
        conf = _confirmation({**d, "value": f"approved {pid}"}, f"Approve processing result {pid}")
        used: dict[str, Any] = {"result": pid, "group_id": group["group_id"]}
        files = (r.get("outputs") or {}).get("files") or []
        if not files:
            # approved before `decide` refused it: a result with NO CURVE. Re-processing with the same
            # parameters gives the same result, so the remedy must not say "re-run and approve"
            used["no_curve"] = no_curve_cause(r)
            if reprocess_cannot_help(r):
                used["no_retry"] = True  # r5f L1: (a key only when true)
        bound = d.get("approved_files")
        current = [{"role": f.get("role"), "relative_path": f.get("relative_path"), "sha256": f.get("sha256")} for f in files]
        if bound is not None and json.dumps(bound, sort_keys=True) != json.dumps(current, sort_keys=True):
            # The approval names other files than the result now lists: nothing is used.
            files = []
            used["approval"] = "the approval binds to different files than this result now lists; not used"
        roles = (("athena_normalized",) if r.get("source") == "scientist_athena" else ()) + SPECTRUM_ROLES
        spectrum = next((f for role in roles for f in files if f.get("role") == role), None)
        if spectrum is not None:
            fpath = contained_file(Path(bundle_dir), spectrum["relative_path"])
            if fpath is not None and hashlib.sha256(fpath.read_bytes()).hexdigest() == spectrum["sha256"]:
                cols = _read_series_file(fpath)
                if isinstance(cols, str):
                    used["series"] = f"not used: {cols}"
                    cols = None
                if cols:
                    sid = f"{group['group_id']}_normalized"
                    draft["series"] = [
                        {
                            "series_id": sid,
                            "independent_variables": [{"name": "incident_energy", "unit": "eV", "values": cols[0]}],
                            "channels": [{"name": "absorption", "unit": "mu_normalized", "role": "primary_signal", "values": cols[1]}],
                        }
                    ]
                    draft["block_evidence"][f"series:{sid}"] = [
                        conf,
                        {"source_type": "document", "source_file": spectrum["relative_path"], "locator": f"sha256 {spectrum['sha256']}", "quote": f"{len(cols[0])} points"},
                    ]
                    used["series"] = spectrum["relative_path"]
                elif "series" not in used:
                    used["series"] = "not used: no data"
            else:
                used["series"] = "the normalised file is missing or its sha256 differs; not used"
        steps = []
        for step in r.get("steps") or ():
            token = PROCESSING_STEP_VOCABULARY.get(step.get("step"))
            if token and token not in steps and step_was_applied(step):
                steps.append(token)
        if steps:
            fields["measurement.processing.steps"] = {"value": steps, "status": "verified", "evidence": [conf]}
            used["processing_steps"] = steps
        verdict = (r.get("qc") or {}).get("verdict")
        if d.get("qc_status"):
            # D2: a person STATED the QC status when approving; it wins over any mapping.
            draft["qc"] = {"status": d["qc_status"]}
            if d.get("qc_note"):
                draft["qc"]["evidence"] = d["qc_note"]
            draft["block_evidence"]["qc:status"] = [
                conf,
                {**_confirmation({**d, "value": d["qc_status"]}, "What is the measurement's QC status?"),
                 "processing_qc": d.get("qc_evidence")},
            ]
            used["qc"] = f"stated by a scientist: {d['qc_status']}"
        else:
            # I4: the QC status is NEVER mapped from the protocol's verdict (CLAUDE.md §5);
            # a person states it when approving.
            used["qc"] = (
                f"no QC status was stated (protocol verdict {verdict!r}); a person states it: "
                f"isaac bundle decide <bundle_dir> --target {pid} --decision approve --qc-status <value> --by \"<name>\""
            )
        e0 = (r.get("outputs") or {}).get("e0_eV")
        if isinstance(e0, (int, float)):
            sigma = (r.get("outputs") or {}).get("e0_uncertainty_eV")
            uncertainty = (
                {"sigma": sigma, "unit": "eV", "basis": "reported"}
                if isinstance(sigma, (int, float))
                else {"sigma": None, "basis": "not_reported"}
            )
            label, generated_by, source, definition = (
                f"{r['protocol_id']}@{r['protocol_version']}",
                {"agent": r["protocol_id"], "version": str(r["protocol_version"])},
                "auto",
                "E0 reported by the scientist-approved processing result.",
            )
            evidence = [conf]
            if r.get("source") == "scientist_athena":
                ref = next(iter(r.get("inputs") or ()), {}) or {}
                # THE PROJECT'S FILE NAME ONLY in the record: a folder name can carry a sample's or a person's
                # name. Where the project is in the beamtime goes to the evidence sidecar, as every source file does.
                prj = PurePosixPath(str(ref.get("relative_path") or "")).name or None
                members = ref.get("per_scan_set") if isinstance(ref.get("per_scan_set"), Mapping) else {}
                groups = [str(g) for g in members.get("athena_groups") or ()]
                if ref.get("match_kind") == "per_scan_set":
                    # A SET OF THE SCIENTIST'S PER-SCAN GROUPS (athena._per_scan_set): ISAAC's protocol AVERAGED
                    # their normalisations and E0s. That is an ISAAC computation, never the scientist's merge and
                    # never values "read unchanged"; the descriptor is ISAAC's (auto) and names the set.
                    n = len(groups) or len(members.get("labels") or ()) or None
                    which = f" (groups {', '.join(groups)}" + (f", in {prj})" if prj else ")") if groups else (f" (in {prj})" if prj else "")
                    of = f"{n} of the scientist's" if n else "the scientist's"
                    by = f"computed by ISAAC {r['protocol_id']} {r['protocol_version']}"
                    label = (f"{r['protocol_id']}@{r['protocol_version']}:mean of athena:{prj or 'project'}#"
                             + ("+".join(groups) if groups else f"{ref.get('athena_group') or 'group'}+per-scan groups"))
                    generated_by = {"agent": r["protocol_id"], "version": str(r["protocol_version"]), "notes": (
                        f"The mean of {of} per-scan Athena normalisations{which}, {by}: the scientist kept one "
                        "Athena group per scan, and ISAAC averaged their curves and E0s. It is not a merge the "
                        "scientist made; a scientist approved it. generated_utc is when a scientist approved "
                        "ISAAC's mean of them, not when the Athena processing was done.")}
                    definition = (f"Mean E0 of {of} per-scan Athena normalisations, {by}; approved by a "
                                  "scientist. Not a merge the scientist made.")
                else:
                    # THE SCIENTIST'S OWN ATHENA PROCESSING made this E0 and curve; ISAAC's protocol only read them
                    # (unchanged), so the descriptor is attributed to Athena and its value is imported, never "auto"
                    where = ", ".join(x for x in (prj, f"Athena group {ref['athena_group']}"
                                                  if ref.get("athena_group") else None) if x)
                    label = f"athena:{prj or 'project'}" + (f"#{ref['athena_group']}" if ref.get("athena_group") else "")
                    # generated_utc (REQUIRED by the schema) is the approval's time: the bundle holds no date for the
                    # Athena processing itself, so the notes say which time it is rather than let it read as the
                    # scientist's processing date
                    generated_by = {"agent": "Athena", "notes": (
                        f"The scientist's own Athena processing{f' ({where})' if where else ''}: E0 and the normalised "
                        f"curve are the scientist's values, read unchanged by ISAAC ({r['protocol_id']} "
                        f"{r['protocol_version']}) and approved by a scientist. generated_utc is when a scientist "
                        "approved ISAAC's reading of it, not when the Athena processing was done.")}
                    source = "imported"
                    definition = "E0 from the scientist's own Athena processing, approved by a scientist; ISAAC did not change it."
                from .mutations import scan_subset_note

                subset = scan_subset_note(bundle, r)
                if subset:
                    generated_by["notes"] += " " + plain_record_note(subset, r.get("group_id"))
                    used["scan_selection"] = subset
                tie = r.get("athena_match_tie") if isinstance(r.get("athena_match_tie"), Mapping) else None
                if tie:
                    # r6 review M1: an Athena curve the SCIENTIST tied to its group (params athena_match), not one its
                    # name matched: said in the record (the project's file name only) and the params file that records
                    # the tie is evidence (sidecar)
                    tied_in = PurePosixPath(str(tie.get("project") or "")).name or "its project"
                    generated_by["notes"] += (f" The scientist tied Athena group '{tie.get('athena_label') or tie.get('athena_group')}'"
                                              f" in {tied_in} to this group by their params file (athena_match); its "
                                              "name is not the group's scan name.")
                    if tie.get("params_file"):
                        evidence.append({"source_type": "document", "source_file": tie["params_file"],
                                         "locator": "athena_match",
                                         "quote": f"{tie.get('project')} / {tie.get('athena_group')}"})
                if ref.get("relative_path"):
                    named = groups or ([str(ref["athena_group"])] if ref.get("athena_group") else [])
                    evidence.append({"source_type": "document", "source_file": ref["relative_path"],
                                     "locator": ("Athena group" + ("s " if len(named) > 1 else " ") + ", ".join(named))
                                     if named else "Athena project"})
            draft["descriptors_outputs"] = [
                {
                    "label": label,
                    # the approval's time, in the record body (the pinned schema requires generated_utc): a result
                    # approved again with the same curves composes another body, so its record gets a new id (c15c)
                    "generated_utc": d.get("decided_utc"),
                    "generated_by": generated_by,
                    "descriptors": [
                        {
                            "name": "edge_position",
                            "kind": "absolute",
                            "source": source,
                            "value": e0,
                            "unit": "eV",
                            "uncertainty": uncertainty,
                            "definition": definition,
                            "evidence": evidence,
                        }
                    ],
                }
            ]
        report["processing"] = used
    elif blocked_by_protocol:
        app = not_applicable[-1]["applicability"]
        report["processing"] = {
            "used": None,
            "reason": f"{B.NO_PROTOCOL_COVERS} ({app.get('reason_code')}): {app.get('statement')}",
            "not_applicable": {"result_id": B.processing_id(not_applicable[-1]), "reason_code": app.get("reason_code"),
                               "what_the_data_states": app.get("what_the_data_states")},
        }
    else:
        report["processing"] = {"used": None, "reason": "no scientist-approved processing result for this group",
                                "group_id": group["group_id"],
                                "awaiting_approval": [B.processing_id(r) for r in mine
                                                      if r.get("state") in B.PROCESSING_UNDECIDED_STATES
                                                      and not B.processing_not_applicable(r)
                                                      and (r.get("outputs") or {}).get("files")
                                                      and not unusable_curve_reasons(r)],
                                # c8-a: undecided, with a curve whose QC says it is not a usable spectrum
                                # (mutations.UNUSABLE_CURVE_REASONS): `decide` refuses to approve them, so they are
                                # never offered for approval
                                "unusable_curve_results": {B.processing_id(r): ", ".join(unusable_curve_reasons(r))
                                                           for r in mine
                                                           if r.get("state") in B.PROCESSING_UNDECIDED_STATES
                                                           and not B.processing_not_applicable(r)
                                                           and (r.get("outputs") or {}).get("files")
                                                           and unusable_curve_reasons(r)},
                                # undecided but with NO CURVE: `decide` refuses to approve them, so they are
                                # never offered for approval
                                "no_curve_results": {B.processing_id(r): no_curve_cause(r) for r in mine
                                                     if r.get("state") in B.PROCESSING_UNDECIDED_STATES
                                                     and not B.processing_not_applicable(r)
                                                     and not (r.get("outputs") or {}).get("files")},
                                # r5f L1: those of them whose group processing again cannot help
                                # (a key only when there is one, so a draft's processing section stays what it was)
                                **({"no_retry_results": ids} if (ids := [
                                    B.processing_id(r) for r in mine
                                    if r.get("state") in B.PROCESSING_UNDECIDED_STATES
                                    and not B.processing_not_applicable(r)
                                    and not (r.get("outputs") or {}).get("files")
                                    and reprocess_cannot_help(r)]) else {}),
                                # a result a scientist REJECTED exists: "none exists" would send them to re-run
                                "rejected": [B.processing_id(r) for r in mine if r.get("state") == B.STATE_REJECTED]}

    # what the record requires and nobody supplied: stays missing, listed. The control mode is the
    # one this DRAFT carries — a confirmed, schema-fitting answer that composed (1.5.0: locally
    # answerable). A potentiostatic draft without a composed set-point (none answered, or held back
    # by the scale gate above) is therefore incomplete, never exported. A galvanostatic draft needs
    # context.electrochemistry.current_setpoint_mA_cm2 (answerable since 1.7.0, DEC-92): it composes
    # like any eligible answer, with no companion gate (bundle.COMPOSES_ONLY_WITH has no entry for it),
    # and only as a number exactly as answered. No mode is derived from a set-point, nor a set-point
    # from a mode, nor a current density from a current and an area: an unanswered mode requires nothing.
    control = fields.get(B.CONTROL_MODE_PATH, {}).get("value")
    mode = control if isinstance(control, str) else None
    by_mode = index["required_by_mode"]
    if mode not in by_mode:
        by_mode[mode] = tuple(B.required_record_paths(control_mode=mode))
    required = list(by_mode[mode])
    required += list(B.PORTAL_REQUIRED_PATHS)
    if "context.reaction.name" in fields:
        required += list(B.REACTION_REQUIRED_PATHS)
    report["record_overrides"] = {}
    if "context.temperature_K" not in fields:
        # DEC-76: an unknown temperature is written the way the portal's schema says —
        # temperature_K null with temperature_basis not_reported. Never a default value.
        nobody = [m["value_id"] for m in bundle["missing_values"]
                  if m["target_field_path"] == "context.temperature_K" and m["run_id"] in measured_ids]
        fields["context.temperature_basis"] = {
            "value": "not_reported",
            "status": "inferred",
            "evidence": [
                {
                    "source_type": "derivation",
                    "rule": (
                        "DEC-76: no source in this import and no scientist answer states a "
                        "temperature for this record, so temperature_K is null and "
                        "temperature_basis is not_reported. Nothing is defaulted."
                    ),
                    "missing_value_ids": nobody,
                }
            ],
        }
        report["record_overrides"]["context.temperature_K"] = None
        report["temperature"] = "not_reported (temperature_K null)"
    for req in required:
        if req == "context.temperature_K" and "context.temperature_K" in report["record_overrides"]:
            continue
        if req in STRUCTURED_REQUIRED:
            present = {
                "measurement.series": bool(draft.get("series")),
                "measurement.qc.status": bool((draft.get("qc") or {}).get("status")),
                "descriptors.outputs": bool(draft.get("descriptors_outputs")),
            }[req]
            if not present:
                report["missing_required"].append(
                    {"path": req, "from": "an approved processing result"}
                    | ({"blocked": B.NO_PROTOCOL_COVERS} if blocked_by_protocol and not approved else {})
                )
            continue
        field = REQUIRED_AS_FIELD.get(req, req)
        if field in held_by_companion and field not in fields:
            # c12-q MED-1: A CONFIRMED VALUE HELD BACK BY ITS COMPANION (a set-point with no confirmed scale): the
            # companion is what is missing. The held field is NOT listed (answering it again changes nothing): the
            # companion is, with why, so validate, the questions and the minimum name the scale and its command.
            companion, value = held_by_companion[field]
            if not any(m["path"] == companion for m in report["missing_required"]):
                if _present(fields, companion) is None:
                    fields[companion] = {"value": None, "status": "missing", "evidence": []}
                report["missing_required"].append({
                    "path": companion, "from": FROM_AN_ANSWER,
                    "required_because": HELD_NEEDS_COMPANION.format(path=field, value=_said(value, field), companion=companion)})
            continue
        if not any(p == field or p.startswith(field + ".") for p in fields):
            fields[field] = {"value": None, "status": "missing", "evidence": []}
            report["missing_required"].append({"path": field, "from": "a scientist's answer",
                                               **({"reason": held_by_slots[field]} if field in held_by_slots else {})})
    # WHAT AN OBJECT THE RECORD CARRIES REQUIRES (the schema's own rule, known before validation): an electrolyte
    # name makes concentration_M required. Listed like any other required value, so build-records, the questions
    # and the minimum say it, never only `validate`'s official-schema error.
    for need in _object_member_requirements(fields):
        fields[need["path"]] = {"value": None, "status": "missing", "evidence": []}
        report["missing_required"].append(need)
    from . import questions as Q  # c8-b: the conditions generic runs' names and headers state (questions.py)

    # r5c C6: A REQUIRED FIELD NOBODY ANSWERED THAT GOES IN ONLY BESIDE ITS COMPANION (a set-point with no confirmed
    # potential scale): the companion is listed missing NOW, beside it, as the questions' minimum already asks it
    # (questions._companions_missing, the same entry and why). Appended last, so the questions read the same list.
    report["missing_required"] += Q._companions_missing(report)

    # r6h H2: the control mode the record carries (``questions`` says a set-point's why from it); nothing is read here
    report["control_mode"] = (fields[B.CONTROL_MODE_PATH].get("value") if _present(fields, B.CONTROL_MODE_PATH) is not None
                              else None)
    # the conditions a run's names or headers state, of the MEASUREMENT runs only (a context run is asked nothing)
    report["warnings"] = (_stated_potential_warnings(bundle, group, measured_ids, fields, proposals,
                                                     held_by_scale=held_by_companion.get(SETPOINT_PATH, (None,))[0] == SCALE_PATH)
                          + _potential_sources_warnings(bundle, group, measured_ids, fields)
                          + _macro_setpoint_warnings(bundle, group, measured_ids, fields, index["memo"])
                          + Q.open_circuit_warnings(bundle, group, measured_ids, fields)
                          + _in_situ_warnings(bundle, group, [r for r in member_runs if r["run_id"] in measured_ids], fields,
                                              index["memo"])
                          + _start_time_warnings(bundle, group, measured_ids, fields, index["memo"],
                                                 disagreements=report["disagreements"]))
    if chose_other is not None:
        # r5c C1: the record carries an approved result that is not the version the scientist chose last: said at
        # build-records, validate and export (on the record's row), never silent
        report["warnings"].append({"code": ATHENA_NOT_CHOSEN_WARNING, "group_id": group["group_id"],
                                   "path": "measurement.series", "needs": "measurement.series", "targets": [],
                                   **chose_other, "command": f'isaac bundle decide <bundle_dir> --target '
                                   f'{chose_other["approved_result_id"]} --decision reject --by "<your name>"',
                                   "text": athena_choice_text(chose_other, group["group_id"])})
    return draft, report


def _stated_potentials(bundle: Mapping, member_ids: set) -> list[dict]:
    """Each potential a member run's FILE NAME states, as the import already holds it: a set-point candidate read
    from a file-name token (its literal and the volts it was read as), or an unmapped file-name token shaped like a
    potential (:data:`_POTENTIAL_TOKEN`, its literal only: nothing is read from it). Bundle order, each once."""
    from . import questions as Q  # c8-b: a generic run's file names and scan headers (no candidate holds them)

    out, seen, header = [], set(), []
    for c in bundle["candidates"]:
        if c.get("run_id") not in member_ids:
            continue
        if B.is_header_comment_candidate(c) and c.get("target_field_path") == SETPOINT_PATH:
            # c16b: a set-point read from a scan-header comment line (it needs review): stated by the HEADER
            value = c.get("value") if isinstance(c.get("value"), (int, float)) and not isinstance(c.get("value"), bool) else None
            for e in c.get("evidence") or ():
                lit = e.get("literal_value")
                if (lit, c["run_id"]) in seen or not isinstance(lit, str):
                    continue
                seen.add((lit, c["run_id"]))
                # c16-r: the literal is the whole comment line; what it states is read by the rule's own parser
                got = next((x for x in Q.header_comment_readings(lit) if x["path"] == SETPOINT_PATH), None) or {}
                header.append({"literal": lit, "relative_path": e.get("relative_path"), "candidate_id": c["candidate_id"],
                               "read_as_V": value, "value_state": c.get("value_state"), "stated_in": "scan header",
                               "locator": e.get("locator"), "run_id": c["run_id"], "runs": [c["run_id"]],
                               "volts": got.get("value"), **({"scale": got["scale"]} if got.get("scale") else {}),
                               # r3a H2: what a line read with no value mentions, to compare only
                               **({"mentions": Q.header_potential_mentions(lit)} if got.get("value") is None else {})})
            continue
        for e in c.get("evidence") or ():
            if e.get("method") == "ai_interpretation" or not str(e.get("locator") or "").startswith("filename token"):
                continue
            lit = e.get("literal_value")
            if c.get("target_field_path") == SETPOINT_PATH:
                value = c.get("value") if isinstance(c.get("value"), (int, float)) and not isinstance(c.get("value"), bool) else None
            elif c.get("statement_key") == "unknown_token" and isinstance(lit, str) and _POTENTIAL_TOKEN.match(lit):
                value = None
            else:
                continue
            key = (lit, value)  # one statement however many of the run's files repeat it
            if key not in seen:
                seen.add(key)
                out.append({"literal": lit, "relative_path": e.get("relative_path"), "candidate_id": c["candidate_id"],
                            "read_as_V": value, "value_state": c.get("value_state")})
    return out + Q.stated_potentials_beyond_candidates(bundle, member_ids) + header  # the names first, as before


def _stated_potential_warnings(bundle: Mapping, group: Mapping, member_ids: set, fields: Mapping,
                               proposals: Mapping[str, list], *, held_by_scale: bool = False) -> list[dict]:
    """A WARNING (never a refusal) for a group whose file names state a potential that its record will not carry:
    the condition that defines the record would be silently absent. Why it is absent — no confirmed potential
    scale (a set-point composes only beside one, :data:`bundle.COMPOSES_ONLY_WITH`) or no confirmed set-point —
    and the command that lets it in (``targets``: the open scale / set-point values of the member runs). When the
    scale is missing AND no set-point was read from the names or answered, BOTH steps are named (``also_needs``,
    ``also_targets``, ``also_command``: the set-point), so the scientist is not sent round twice. A record
    that carries a set-point gets none; so does one whose file names state no potential, and so does one whose
    set-point is itself listed as missing (a required value nobody answered: the missing list already says it). A
    confirmed set-point held back until its scale is answered is NOT listed (c12-q: the scale is), so it warns; a
    ``missing`` placeholder for the scale carries no scale. r4-b L2: ``held_by_scale``: the set-point is confirmed and
    held back by its scale (some run of the group has none, while another's fills the field), so the SCALE is what is
    missing, as its ``required_because`` says, never "until the potential set-point is confirmed"."""
    if SETPOINT_PATH in fields:
        return []
    stated = _stated_potentials(bundle, member_ids)
    if not stated:
        return []
    answered = [v for v, _, _ in proposals.get(SETPOINT_PATH, ()) if isinstance(v, (int, float)) and not isinstance(v, bool)]
    scale_missing = _present(fields, SCALE_PATH) is None or held_by_scale

    def open_targets(path: str) -> list[str]:
        return [o.get("candidate_id") or o.get("value_id")
                for o in list(bundle["candidates"]) + list(bundle["missing_values"])
                if o.get("target_field_path") == path and o.get("run_id") in member_ids
                and o.get("value_state") in (B.STATE_MISSING, B.STATE_NEEDS_REVIEW, B.STATE_CANDIDATE_EXTRACTED)]

    valued = {c["candidate_id"] for c in bundle["candidates"] if c.get("value") is not None}

    def command_for(path: str, targets: Sequence[str]) -> str:
        # r1d: a candidate with no value (a comment line not written plainly) is answered with its value, not confirmed
        if targets and targets[0] in valued and path == SETPOINT_PATH:
            command = f'isaac bundle decide <bundle_dir> --target {targets[0]} --decision confirm --by "<your name>"'
        elif targets:
            command = (f"isaac bundle decide <bundle_dir> --target {targets[0]} --decision correct --value "
                       + ("<potential scale>" if path == SCALE_PATH else "<volts> --json") + ' --by "<your name>"')
        else:
            command = f"isaac bundle questions <bundle_dir> --scope group:{group['group_id']}   # answer {path} there"
        if len(targets) > 1:
            command += f"   # and the same for {', '.join(targets[1:4])}{'…' if len(targets) > 4 else ''}"
        return command

    needs = SCALE_PATH if scale_missing else SETPOINT_PATH
    targets = open_targets(needs)
    w = {"code": STATED_POTENTIAL_WARNING, "group_id": group["group_id"], "path": SETPOINT_PATH, "needs": needs,
         "stated": stated, "answered_V": answered, "targets": targets, "command": command_for(needs, targets)}
    # BOTH STEPS AT ONCE: no scale, and NO set-point value read from the names (the potential is an unread token,
    # e.g. `m500mV` kept as unknown_token) nor answered: confirming the scale alone would only move the warning on
    # to the set-point, so both are named now, each with its command
    unread = not answered and all(s.get("read_as_V") is None for s in stated)
    # c16b: a set-point read from a scan-header comment line still needs review: confirming the scale alone would
    # move the warning on to it, so both are named now, as for an unread one
    header_read = not answered and not unread and all(
        s.get("read_as_V") is None or (s.get("stated_in") == "scan header" and s.get("value_state") == B.STATE_NEEDS_REVIEW)
        for s in stated)
    if header_read:
        w["setpoint_needs_review"] = True
        unread = True
    also = open_targets(SETPOINT_PATH) if scale_missing and unread else []
    if also:
        w.update(also_needs=SETPOINT_PATH, also_targets=also, also_command=command_for(SETPOINT_PATH, also))
    return [{**w, "text": potential_warning_text(w)}]


def _potential_sources_warnings(bundle: Mapping, group: Mapping, member_ids: set, fields: Mapping) -> list[dict]:
    """A :data:`POTENTIAL_SOURCES_WARNING` (never a refusal) for a record that CARRIES a set-point while a member run's
    file name and scan header write different numbers (``m150mV`` and ``-300 mV vs RHE``) — a disagreement of the
    files the template's typed value does not settle by itself. Unresolved, and so warned, until a scientist rules
    (:func:`_setpoint_ruled`): on the header's reading (its ``bundle.XDC_COMMENT_RULE_ID`` candidate: confirm or
    correct it), or — in a bundle imported before those candidates existed, which has no reading to decide — on the
    record's own set-point target, by a decision recorded after the one that gave the record its set-point (the
    warning, which shows the header's words, can only be shown after that one). The re-import alternative says what
    a new bundle does not carry over. A record without a set-point gets the stated-potential warning instead, which
    names the same disagreement (``questions.stated_potential_notes``).

    r3c: a header candidate whose latest answer is ``reject`` says its line states no set-point: that line is not
    compared (a reject, like a defer, is no ruling on the set-point). And THE RECORD AGAINST THE RUN'S OWN FILE NAME
    (``m300mV`` while the record carries -0.6 V) is warned whatever the header rulings say, until a value decision
    is recorded for THAT RUN ALONE (:func:`_ruled_for_run_alone`): an answer given to several runs at once
    (``--same-reading``, a bulk decide, a beamtime value) was not made looking at this run's name."""
    from . import questions as Q
    from .template import header_potential_mentions, header_potential_readings

    if _present(fields, SETPOINT_PATH) is None:
        return []
    carried = fields[SETPOINT_PATH].get("value") if isinstance(fields.get(SETPOINT_PATH), Mapping) else None
    scale = fields[SCALE_PATH].get("value") if isinstance(fields.get(SCALE_PATH), Mapping) else None
    carried_v = (round(float(carried), 9) if isinstance(carried, (int, float)) and not isinstance(carried, bool)
                 else None)
    latest = _latest_decisions(bundle)
    out = []
    for r in Q._generic_member_runs(bundle, member_ids):
        names = [t for t in Q._name_tokens(r) if _POTENTIAL_TOKEN.match(t)]
        name_v = {round(v, 9) for v in map(Q._token_volts, names) if v is not None}
        held_all = [c for c in bundle.get("candidates") or () if c.get("run_id") == r["run_id"]
                    and B.is_header_comment_candidate(c) and c.get("target_field_path") == SETPOINT_PATH]
        # r3c: a line the scientist said states no set-point (a reject of its header candidate) is not compared
        rejected = {(e.get("relative_path"), e.get("locator")) for c in held_all
                    if (latest.get(c["candidate_id"]) or {}).get("decision") == "reject" for e in c.get("evidence") or ()}
        held = [c for c in held_all if (latest.get(c["candidate_id"]) or {}).get("decision") != "reject"]
        heads = [h for h in header_potential_readings(bundle, r) if (h["relative_path"], h["locator"]) not in rejected]
        head_v = {round(h["value"], 9) for h in heads}
        # r3a H2: a value-less header line's MENTIONS (``0Vrhe``), EACH compared with the file name's potential and
        # the record's set-point: any one that differs from either is a disagreement (none is picked as the value)
        lines = [h for h in header_potential_mentions(bundle, r) if (h["relative_path"], h["locator"]) not in rejected]
        not_name = [m for h in lines for m in h["mentions"] if name_v and round(m["volts"], 9) not in name_v]
        not_carried = [m for h in lines for m in h["mentions"] if carried_v is not None and round(m["volts"], 9) != carried_v]
        odd = not_name + not_carried
        # r3c HIGH: the record's set-point against this run's own file name, settled only by a ruling on this run
        record_vs_name = (bool(name_v) and carried_v is not None and carried_v not in name_v
                          and not _ruled_for_run_alone(bundle, r["run_id"], latest))
        files_differ = bool(odd) or bool(name_v and head_v and not name_v & head_v)
        if not files_differ and not record_vs_name:
            continue
        ruled, own = _setpoint_ruled(bundle, r["run_id"], held) if files_differ else (True, None)
        if ruled and not record_vs_name:
            continue
        name_scales = {(Q.header_potential(t) or {}).get("scale") for t in names}
        head_scales = {h.get("scale") for h in heads} | {m.get("scale") for h in lines for m in h["mentions"]}
        if held:
            command = (f'isaac bundle decide <bundle_dir> --target {held[0]["candidate_id"]} --decision confirm '
                       '--by "<your name>"' if held[0].get("value") is not None and not record_vs_name else
                       f'isaac bundle decide <bundle_dir> --target {held[0]["candidate_id"]} --decision correct '
                       '--value <volts> --json --by "<your name>"')
        elif own is not None:
            # a decision unlike the latest one on that target, so it is recorded even with the same volts
            again = "correct" if own["latest"] == "confirm" else "confirm"
            shown = f"{carried:g}" if isinstance(carried, (int, float)) and not isinstance(carried, bool) else "<volts>"
            command = (f'isaac bundle decide <bundle_dir> --target {own["target"]} --decision {again} --value {shown} '
                       '--json --by "<your name>"')
        elif record_vs_name and (mine := _run_setpoint_targets(bundle, r["run_id"])):
            command = (f'isaac bundle decide <bundle_dir> --target {mine[0]} --decision correct --value <volts> --json '
                       '--by "<your name>"')
        elif record_vs_name:
            command = f"isaac bundle questions <bundle_dir> --scope run:{r['run_id']}"
        else:
            command = REIMPORT_COMMAND
        out.append({"code": POTENTIAL_SOURCES_WARNING, "group_id": group["group_id"], "path": SETPOINT_PATH,
                    "needs": SETPOINT_PATH, "run_id": r["run_id"],
                    "targets": ([c["candidate_id"] for c in held] or ([own["target"]] if own is not None else [])
                                or (_run_setpoint_targets(bundle, r["run_id"])[:1] if record_vs_name else [])),
                    "names": list(dict.fromkeys(names)), "headers": list(dict.fromkeys(
                        repr(h["literal"]) + (f" at {h['locator']} of {h['relative_path']}" if h.get("relative_path") else "")
                        for h in heads)), "carried_V": carried, "carried_scale": scale,
                    "mentions": _mention_lines(lines, not_name, not_carried),
                    # r3c MED-1: the scale only the DIFFERING mentions write (never one another mention has)
                    "mention_scale": Q.written_scales({m.get("scale") for m in odd}),
                    "headers_disagree": bool(name_v and head_v and not name_v & head_v),
                    "same_scale": name_scales == head_scales and None not in name_scales,
                    "name_scale": Q.written_scales(name_scales), "header_scale": Q.written_scales(head_scales),
                    "no_header_reading": not held_all, "command": command,
                    **({"files_ruled": True} if ruled else {}),
                    **({"record_differs_from_name": True, "file_name_V": sorted(name_v)} if record_vs_name else {})})
    return [{**w, "text": potential_sources_text(w)} for w in out]


def _latest_decisions(bundle: Mapping) -> dict[str, Mapping]:
    """``target id -> the latest decision on it`` (candidates and missing values)."""
    out: dict[str, Mapping] = {}
    for d in bundle.get("scientist_decisions") or ():
        t = d.get("target") or {}
        if t.get("kind") in ("candidate", "missing_value") and t.get("id"):
            out[t["id"]] = d
    return out


def _run_setpoint_targets(bundle: Mapping, run_id: str) -> list[str]:
    """The set-point targets that are THIS run's own (a candidate or missing value with its ``run_id``), header
    candidates first."""
    objs = [o for o in list(bundle.get("candidates") or ()) + list(bundle.get("missing_values") or ())
            if o.get("target_field_path") == SETPOINT_PATH and o.get("run_id") == run_id]
    objs.sort(key=lambda o: not B.is_header_comment_candidate(o))
    return [o.get("candidate_id") or o.get("value_id") for o in objs]


def _ruled_for_run_alone(bundle: Mapping, run_id: str, latest: Mapping[str, Mapping]) -> bool:
    """r3c HIGH: whether the latest decision on one of this run's OWN set-point targets is a value decision
    (:data:`_VALUE_DECISIONS`) recorded for this run alone: on its own, or in a batch whose every target is this
    run's. An answer given to several runs at once (``--same-reading``, a bulk ``decide``) is not."""
    mine = set(_run_setpoint_targets(bundle, run_id))
    if not mine:
        return False
    run_of = {o.get("candidate_id") or o.get("value_id"): o.get("run_id")
              for o in list(bundle.get("candidates") or ()) + list(bundle.get("missing_values") or ())}
    batches: dict[str, set] = {}
    for d in bundle.get("scientist_decisions") or ():
        if d.get("batch_id"):
            batches.setdefault(d["batch_id"], set()).add(run_of.get((d.get("target") or {}).get("id")))
    for tid in mine:
        d = latest.get(tid)
        if d is None or d.get("decision") not in _VALUE_DECISIONS:
            continue
        if not d.get("batch_id") or batches.get(d["batch_id"]) == {run_id}:
            return True
    return False


def _mention_lines(lines: Sequence[Mapping], not_name: Sequence[Mapping], not_carried: Sequence[Mapping]) -> list[dict]:
    """r3a H2: the header lines a :data:`POTENTIAL_SOURCES_WARNING` names by what they MENTION, one per line text
    (a run's scans repeat it): ``{line, literals, differ_name, differ_carried, where}``, the mentions that differ
    from the file name's potential and from the record's set-point, each QUOTED as written around it (r3c MED-1)."""
    out: dict[str, dict] = {}

    def said(m: Mapping) -> str:
        return m.get("quote") or m["literal"]

    for h in lines:
        got = out.setdefault(h["line"], {"line": h["line"], "literals": [said(m) for m in h["mentions"]],
                                         "differ_name": [said(m) for m in h["mentions"] if m in not_name],
                                         "differ_carried": [said(m) for m in h["mentions"] if m in not_carried],
                                         "where": []})
        got["where"].append(f"{h['locator']} of {h['relative_path']}")
    return list(out.values())


#: c16-r M2: the re-import a bundle built before scan-header readings existed is offered, and what it does not keep.
REIMPORT_COMMAND = "isaac import <the beamtime folder> --out <a new bundle folder>"
REIMPORT_CAVEAT = ("a new bundle starts with no answers: the decisions recorded here and a filled workbook do not carry "
                   "over to it, and the ids printed for this bundle (miss-NNNN, cand-NNNN, the question ids) name other "
                   "things there")
#: the decisions that state a value for a target (a ruling on what it carries)
_VALUE_DECISIONS = ("confirm", "correct", "provide_value", "choose_reading")


def _setpoint_ruled(bundle: Mapping, run_id: str, held: Sequence[Mapping]) -> tuple[bool, dict | None]:
    """``(ruled, own)`` for a run whose file name and scan header write different numbers (c16-r M2). RULED when a
    scientist decided every header set-point candidate the run holds (``held``), or — with none held, a bundle built
    before the comment rule — when the record's own set-point target for the run (a set-point candidate or missing
    value of that run, else of the whole beamtime) carries a value decision recorded AFTER the one that first gave
    it a value: the warning showing the header's words appears only once the record carries a set-point, so that
    later decision was made with it in view. ``own``: ``{target, latest}`` of that target (``None`` when it has no
    value decision), for the command."""
    decisions = [d for d in bundle.get("scientist_decisions") or () if (d.get("target") or {}).get("kind") in ("candidate", "missing_value")]
    if held:
        # r3c LOW-1: only a confirm or a correct is a ruling on the set-point (a defer or a reject is not), as the
        # latest answer on the candidate
        latest = {d["target"]["id"]: d.get("decision") for d in decisions if d["target"]["kind"] == "candidate"}
        return all(latest.get(c["candidate_id"]) in ("confirm", "correct") for c in held), None
    objs = [o for o in list(bundle.get("candidates") or ()) + list(bundle.get("missing_values") or ())
            if o.get("target_field_path") == SETPOINT_PATH and not B.is_header_comment_candidate(o)]
    for scope in (run_id, None):
        for o in objs:
            if o.get("run_id") != scope:
                continue
            tid = o.get("candidate_id") or o.get("value_id")
            said = [d for d in decisions if d["target"]["id"] == tid and d.get("decision") in _VALUE_DECISIONS]
            if said:
                return len(said) > 1, {"target": tid, "latest": said[-1].get("decision")}
    return False, None


def local_clock_runs(bundle: Mapping) -> set[str]:
    """The runs whose start time waits on the instrument clock's zone (a ``bundle.XDC_START_RULE_ID`` candidate).
    A beamtime-wide candidate (no run) names no run, so it is skipped before its rule is read: a group is composed
    with every beamtime-wide candidate beside its own, and reading each one's rule per group was quadratic."""
    return {c["run_id"] for c in bundle.get("candidates") or () if c.get("run_id") is not None and B.is_local_clock_start(c)}


def _start_time_warnings(bundle: Mapping, group: Mapping, member_ids: set, fields: Mapping,
                         memo: dict | None = None, disagreements: Sequence[Mapping] = ()) -> list[dict]:
    """A :data:`START_TIME_WARNING` for a record that carries no start time while a member run's scan headers write
    one (``bundle.XDC_START_RULE_ID``) and the latest answer to the clock question is ``defer``: the record goes out
    without it, and says so. c16-r L6: so does one while the clock question has no answer yet (no zone, no defer),
    in its own words. A zone answered ends both."""
    from . import questions as Q
    from .mutations import clock_zone_deferral

    if _present(fields, B.XDC_START_PATH) is not None:
        return []
    memo = {} if memo is None else memo
    differ = next((d for d in disagreements if d.get("path") == B.XDC_START_PATH), None)
    if differ is not None:
        return _start_time_differ_warnings(bundle, group, member_ids, differ)
    if "local_clock_runs" not in memo:  # r4-c: read once per composition, never once per group
        memo["local_clock_runs"] = local_clock_runs(bundle)
    if not memo["local_clock_runs"] & set(member_ids):
        return _start_time_conflict_warnings(bundle, group, member_ids, memo)
    if clock_zone_deferral(bundle) is not None:
        unanswered = False
    elif B.clock_zone_decision(bundle) is None:
        unanswered = True
    else:
        return []
    text = (START_TIME_LEFT_OUT_UNANSWERED if unanswered else START_TIME_LEFT_OUT).format(question=Q.CLOCK_QUESTION_ID)
    return [{"code": START_TIME_WARNING, "group_id": group["group_id"], "path": B.XDC_START_PATH,
             "needs": B.XDC_START_PATH, "targets": [], "question_id": Q.CLOCK_QUESTION_ID, "text": text,
             "command": B.CLOCK_ZONE_COMMAND, **({"unanswered": True} if unanswered else {})}]


def _start_time_differ_warnings(bundle: Mapping, group: Mapping, member_ids: set, differ: Mapping) -> list[dict]:
    """r6 review M2: a :data:`START_TIME_WARNING` for a record whose runs were given different start times (the
    composer's disagreement: it fills nothing), named by the group's first start-time question when it has one."""
    from . import questions as Q

    start = {c["candidate_id"] for c in bundle.get("candidates") or () if c.get("target_field_path") == B.XDC_START_PATH}
    cf = next((cf for cf in bundle.get("conflicts") or () if cf.get("run_ids") and cf["run_ids"][0] in member_ids
               and (cf.get("candidate_id") or "") in start), None)
    qid = Q._qid(f"group:{group['group_id']}", "resolve_conflict", cf["conflict_id"]) if cf is not None else None
    values = list(dict.fromkeys(str(v) for v in differ.get("values") or ()))
    w = {"code": START_TIME_WARNING, "group_id": group["group_id"], "path": B.XDC_START_PATH,
         "needs": B.XDC_START_PATH, "targets": list(differ.get("from") or ()), "question_id": qid, "differ": True,
         "values": values[:5]}
    if qid:
        w["command"] = f"isaac bundle show question <bundle_dir> {qid}"
    return [{**w, "text": start_time_text(w)}]


def start_time_text(w: Mapping) -> str:
    """The plain sentence of a :data:`START_TIME_WARNING` (each of its cases)."""
    if w.get("differ"):
        return START_TIME_LEFT_OUT_DIFFER.format(values=", ".join(w.get("values") or ()),
                                                 question=f" (question {w['question_id']})" if w.get("question_id") else "")
    text = (START_TIME_LEFT_OUT_CONFLICT if w.get("conflict") else START_TIME_LEFT_OUT_UNANSWERED if w.get("unanswered")
            else START_TIME_LEFT_OUT).format(question=w["question_id"])
    if w.get("beamtime_question_id"):
        text += START_TIME_LEFT_OUT_AT_ONCE.format(beamtime=w["beamtime_question_id"])
    return text


def open_start_conflicts(bundle: Mapping) -> list[Mapping]:
    """The start-time conflicts still open (conflicting or needing review), each naming its run."""
    start = {c["candidate_id"] for c in bundle.get("candidates") or () if c.get("target_field_path") == B.XDC_START_PATH}
    return [cf for cf in bundle.get("conflicts") or () if cf.get("run_ids") and (cf.get("candidate_id") or "") in start
            and cf.get("value_state") in (B.STATE_CONFLICTING, B.STATE_NEEDS_REVIEW)]


def _start_time_conflict_warnings(bundle: Mapping, group: Mapping, member_ids: set, memo: dict | None = None) -> list[dict]:
    """r4-b L5: a :data:`START_TIME_WARNING` for a record that carries no start time because a member run's start-time
    readings disagree and that disagreement is unanswered (a SPEC beamtime, with no clock-zone question to defer): the
    record goes out without it and says why, at validate, export, in its evidence file and the upload dry run, as
    for the deferred clock zone (c16d). Named by the question this group asks it in. ``memo``: the composition
    index's, so the open start-time disagreements are found once per bundle, not once per group."""
    from . import questions as Q

    memo = {} if memo is None else memo
    if "open_start_conflicts" not in memo:
        memo["open_start_conflicts"] = open_start_conflicts(bundle)
    for cf in memo["open_start_conflicts"]:
        if cf["run_ids"][0] in member_ids:
            qid = Q._qid(f"group:{group['group_id']}", "resolve_conflict", cf["conflict_id"])
            if "beamtime_start_reach" not in memo:
                memo["beamtime_start_reach"] = _beamtime_start_reach(bundle, memo["open_start_conflicts"])
            w = {"code": START_TIME_WARNING, "group_id": group["group_id"], "path": B.XDC_START_PATH,
                 "needs": B.XDC_START_PATH, "targets": [cf["conflict_id"]], "question_id": qid, "conflict": True,
                 "command": f"isaac bundle show question <bundle_dir> {qid}",
                 **({"beamtime_question_id": Q.STATED_UTC_START_QUESTION_ID}
                    if cf["conflict_id"] in memo["beamtime_start_reach"] else {})}
            return [{**w, "text": start_time_text(w)}]
    return []


def _macro_setpoint_warnings(bundle: Mapping, group: Mapping, member_ids: set, fields: Mapping,
                             memo: dict | None = None) -> list[dict]:
    """r6h H2: a :data:`MACRO_SETPOINT_WARNING` (never a refusal) for a record whose member run has an OPEN
    ``macro_setpoint_disagrees`` conflict (a macro names the measurement with another set-point than its file name):
    the record carries whatever set-point the run's own answers give (or none), while which one is right is the
    scientist's open question. Said at build-records, validate and export until the conflict's own question is
    answered; no value is read from either side here. ``memo``: the composition index's, so the open conflicts are
    found once per bundle, not once per group."""
    from . import questions as Q

    memo = {} if memo is None else memo
    if "open_macro_conflicts" not in memo:
        memo["open_macro_conflicts"] = [
            cf for cf in bundle.get("conflicts") or () if cf.get("kind") == B.MACRO_SETPOINT_CONFLICT_KIND
            and cf.get("run_ids") and cf.get("value_state") in (B.STATE_CONFLICTING, B.STATE_NEEDS_REVIEW)]
    out = []
    carried = (fields.get(SETPOINT_PATH) or {}).get("value") if _present(fields, SETPOINT_PATH) is not None else None
    for cf in memo["open_macro_conflicts"]:
        if cf["run_ids"][0] not in member_ids or len(cf.get("readings") or ()) < 2:
            continue
        qid = Q._qid(f"group:{group['group_id']}", "resolve_conflict", cf["conflict_id"])
        file_r, macro_r = cf["readings"][0], cf["readings"][1]
        out.append({"code": MACRO_SETPOINT_WARNING, "group_id": group["group_id"], "path": SETPOINT_PATH,
                    "needs": SETPOINT_PATH, "targets": [], "conflict_id": cf["conflict_id"], "run_id": cf["run_ids"][0],
                    "question_id": qid, "file_name_V": file_r.get("value"), "macro_V": macro_r.get("value"),
                    "file_name": ((file_r.get("witnesses") or [{}])[0] or {}).get("relative_path"),
                    "macro": ((macro_r.get("witnesses") or [{}])[0] or {}).get("relative_path"), "carried_V": carried,
                    "command": (f"isaac bundle decide <bundle_dir> --question {qid} --decision confirm --value "
                                f"<{file_r.get('value')} or {macro_r.get('value')}> --json --by \"<your name>\"")})
    return [{**w, "text": macro_setpoint_text(w)} for w in out]


def macro_setpoint_text(w: Mapping) -> str:
    """The plain sentence for a :data:`MACRO_SETPOINT_WARNING`, ending with its command (a template: the scientist's
    answer is the value)."""
    carried = w.get("carried_V")
    now = (f"the record carries {_said(carried, SETPOINT_PATH)} now" if isinstance(carried, (int, float))
           and not isinstance(carried, bool) else "the record carries no set-point now")
    return (f"the macro {w.get('macro')} states {w.get('macro_V')} V for this "
            f"measurement and the file name {w.get('file_name')} states {w.get('file_name_V')} V; {now}, and which one is "
            f"right is unanswered (question {w['question_id']}). Ask the scientist, then: {w['command']}")


#: r6h H3: what an in-situ record is measured IN, with the words a sentence names each by.
IN_SITU_FIELDS = (("context.electrochemistry.electrolyte.name", "electrolyte"),
                  ("context.electrochemistry.cell_type", "cell type"),
                  (B.CONTROL_MODE_PATH, "control mode"))
IN_SITU_PH = ("context.electrochemistry.pH", "pH")
#: r6h review LOW 2: the environments a measurement is done IN (``operando`` too).
IN_SITU_ENVIRONMENTS = ("in_situ", "operando")
#: A file-name token that STATES an in-situ condition: a concentration written onto its electrolyte (``10MNaOH``,
#: ``100mMHClO4``: the formula checked by ``template.electrolyte_formula``), a pH (``pH12``) or open circuit (``OCV``).
#: Quoted in the warning only; never read as a value.
_IN_SITU_NAME_TOKENS = (re.compile(r"\d+(?:[p.]\d+)?(?:mM|uM|\u00b5M|M)(?P<formula>[A-Z][A-Za-z0-9()]{2,})"),
                        re.compile(r"pH\d+(?:[p.]\d+)?", re.IGNORECASE), re.compile(r"OC[VP]", re.IGNORECASE))


#: r7 J5: the control modes an open-circuit name token (``OCV``, ``OCP``) does not contradict.
_OPEN_CIRCUIT_MODES = ("open_circuit", "mixed")
_OPEN_CIRCUIT_TOKEN = _IN_SITU_NAME_TOKENS[2]


def _in_situ_statements(member_runs: Sequence[Mapping]) -> list[dict]:
    """Each in-situ condition a member run's FILE NAME states (:data:`_IN_SITU_NAME_TOKENS`), once per literal, in run
    order: ``{literal, relative_path, run_id}``. Quoted only."""
    from . import questions as Q
    from .template import electrolyte_formula

    out, seen = [], set()
    for r in member_runs:
        first = next((sc.get("relative_path") for sc in r.get("scans") or () if sc.get("relative_path")), None) or r.get("stem")
        for tok in Q._name_tokens(r):
            m = next((m for p in _IN_SITU_NAME_TOKENS if (m := p.fullmatch(tok))), None)
            if m is None or tok in seen or ("formula" in m.groupdict() and not electrolyte_formula(m.group("formula"))):
                continue
            seen.add(tok)
            out.append({"literal": tok, "relative_path": first, "run_id": r["run_id"]})
    return out


def _in_situ_warnings(bundle: Mapping, group: Mapping, member_runs: Sequence[Mapping], fields: Mapping,
                      memo: dict | None = None) -> list[dict]:
    """r6h H3: an :data:`IN_SITU_WARNING` (never a refusal) for a record whose confirmed environment is ``in_situ`` or
    ``operando``, of an electrochemical measurement (an electrochemistry field, or a file name stating a condition or a
    potential), while it carries no electrolyte, cell type or control mode (any of :data:`IN_SITU_FIELDS`; its pH is named too
    when it carries none): what the measurement was done in would be silently absent. It quotes what the member runs'
    file names state (``10MNaOH``), never reads a value from them, and names, per field, the open targets whose
    question asks it (``fields``: ``{path, targets, command}``; ``records.with_question_commands`` makes each command
    the question's, and the questions' minimum recommends them). ``memo``: the open targets per run and field, read
    once per composition."""
    env = _present(fields, "context.environment")
    if env is None or env.get("value") not in IN_SITU_ENVIRONMENTS:
        return []
    lacking = [(p, word) for p, word in IN_SITU_FIELDS if _present(fields, p) is None]
    if not lacking:
        return []
    # r6h review LOW 2: only for an ELECTROCHEMICAL measurement: the record carries an electrochemistry field, or a
    # member run's file name states a condition or a potential (an in-situ gas or heating cell asks none of these)
    from . import questions as Q

    stated = _in_situ_statements(member_runs)
    mode = _present(fields, B.CONTROL_MODE_PATH)
    if mode is not None and mode.get("value") not in _OPEN_CIRCUIT_MODES:
        # r7 J5: a series-name token that says open circuit (``OCV``) is not quoted when the record's confirmed control
        # mode says otherwise (``potentiostatic``): the name is the sample series', not this measurement's
        stated = [x for x in stated if not _OPEN_CIRCUIT_TOKEN.fullmatch(x["literal"])]
    if not (stated or any(k.startswith("context.electrochemistry.") and _present(fields, k) is not None for k in fields)
            or any(_POTENTIAL_TOKEN.match(t) for r in member_runs for t in Q._name_tokens(r))):
        return []
    if _present(fields, IN_SITU_PH[0]) is None:
        lacking.append(IN_SITU_PH)
    memo = {} if memo is None else memo
    cands, missing = bundle.get("candidates") or [], bundle.get("missing_values") or []
    held = memo.get("in_situ_open_targets")
    # read once per LIST composed from: the whole bundle (validate, export) once; questions.compositions' per-group
    # view (only its members' rows) once per group. The lists are kept with the index, so an identity is never reused.
    if held is None or held[0] is not cands or held[1] is not missing:
        wanted = {p for p, _ in IN_SITU_FIELDS} | {IN_SITU_PH[0]}
        by: dict[tuple, list[str]] = {}
        for o in [*cands, *missing]:
            if o.get("target_field_path") in wanted and o.get("value_state") in (
                    B.STATE_MISSING, B.STATE_NEEDS_REVIEW, B.STATE_CANDIDATE_EXTRACTED):
                by.setdefault((o.get("run_id"), o["target_field_path"]), []).append(o.get("candidate_id") or o.get("value_id"))
        held = memo["in_situ_open_targets"] = (cands, missing, by)
    by = held[2]
    rids = [r["run_id"] for r in member_runs]
    each = []
    for path, word in lacking:
        targets = [t for rid in [*rids, None] for t in by.get((rid, path), ())]
        each.append({"path": path, "word": word, "targets": targets,
                     "command": f"isaac bundle questions <bundle_dir> --scope group:{group['group_id']}   # answer {path} there"})
    w = {"code": IN_SITU_WARNING, "group_id": group["group_id"], "path": lacking[0][0], "needs": lacking[0][0],
         "targets": each[0]["targets"], "command": each[0]["command"], "fields": each,
         "stated": stated, "environment": env.get("value")}
    return [{**w, "text": in_situ_text(w)}]


def in_situ_text(w: Mapping) -> str:
    """The plain sentence for an :data:`IN_SITU_WARNING`, ending with the command(s) that ask each field."""
    words = [f["word"] for f in w.get("fields") or ()]
    named = ", ".join(words[:-1]) + f" or {words[-1]}" if len(words) > 1 else (words[0] if words else "")
    stated = w.get("stated") or ()
    said = ("; the file names state " + ", ".join(f"{s['literal']} ({s['relative_path']})" for s in stated[:3])
            + (f" and {len(stated) - 3} more" if len(stated) > 3 else "") + " (quoted, never read as a value)"
            if stated else "; no file name states them")
    # each question once, with the fields it asks here (the commands differ only in --field), then the first command
    asked: dict[str, list[str]] = {}
    for f in w.get("fields") or ():
        m = re.search(r"--question (Q-[0-9a-f]+)", f["command"])
        asked.setdefault(m.group(1) if m else f["command"], []).append(f["word"])
    where = "; ".join(f"question {k} ({', '.join(v)})" if k.startswith("Q-") else f"{', '.join(v)}: {k}"
                      for k, v in asked.items())
    first = (w.get("fields") or [{}])[0].get("command") or w.get("command")
    kind = "an operando" if w.get("environment") == "operando" else "an in-situ"
    return (f"{kind} record that carries no {named}: what it was measured in would be absent from the record{said}. "
            f"Ask the scientist ({where}), e.g. {first}")


def _beamtime_start_reach(bundle: Mapping, open_conflicts: Sequence[Mapping]) -> set[str]:
    """r6 review L3: the OPEN start-time disagreements the beamtime-wide start-time question reaches while it is asked
    (``questions.stated_utc_reach``, two or more groups), else none: a warning on one of them names that question too."""
    from . import questions as Q

    reach = Q.stated_utc_reach(bundle)
    open_ids = {cf["conflict_id"] for cf in open_conflicts}
    reached = {cid: r["group_id"] for cid, r in reach.items() if cid in open_ids and r["reading"] is not None}
    return set(reached) if len(set(reached.values())) >= Q._STATED_UTC_MIN_GROUPS else set()


def potential_sources_text(w: Mapping) -> str:
    """The plain sentence for a :data:`POTENTIAL_SOURCES_WARNING`, ending with its command. c16-r M3: "state
    different potentials" only when both name the SAME scale; else they "write different numbers", each one's scale
    said (a number without a scale may be the same potential on another scale). r3c HIGH: a record whose set-point
    differs from the run's own file name, with no value recorded for that run alone, is said too (on its own once
    the files' disagreement is ruled)."""
    carried = w.get("carried_V")
    volts = f"{carried:g} V" if isinstance(carried, (int, float)) and not isinstance(carried, bool) else "a set-point"
    said = volts + (f" on {w['carried_scale']}" if w.get("carried_scale") else "")
    if w.get("record_differs_from_name"):
        # r3c HIGH: the record against the run's OWN file name, said on its own once the files' disagreement is ruled
        own = (f"the record carries {said} for {w['run_id']}, but its file name writes {'/'.join(w['names'][:3])} "
               f"({', '.join(f'{v:g} V' for v in w.get('file_name_V') or ())}), and no value was recorded for this run "
               "on its own (an answer given to several runs at once, with --same-reading, a bulk decide or a beamtime "
               "value, was not made looking at this run's name): record the set-point this run was held at, for it "
               f"alone, whichever is right (the file name's or {volts}): {w['command']}")
        if w.get("files_ruled"):
            return own
        tail = f" Also: {own}."
    else:
        tail = ""
    return _potential_sources_text(w, said) + tail


def _potential_sources_text(w: Mapping, said: str) -> str:
    """:func:`potential_sources_text` for the files' own disagreement (file name, scan header, record)."""
    from . import questions as Q

    sources = f"file name {'/'.join(w['names'][:3])}; scan header {'; '.join(w['headers'][:3])}"
    if w.get("same_scale"):
        differ = f"state different potentials ({sources}; both on {w['name_scale']})"
    else:
        differ = f"write different numbers ({sources}; file name: {w['name_scale']}; scan header: {w['header_scale']})"
    head = f"the file name and the scan header of {w['run_id']} {differ}, and the record carries {said}"
    if any(h["differ_name"] or h["differ_carried"] for h in w.get("mentions") or ()) and not w.get("headers_disagree"):
        # r3a H2: a header line read with NO value, said plainly by what it writes, beside the file name's and the
        # record's; never "state a potential" (that reads as agreement)
        lines = w["mentions"]
        written = "; ".join(f"{Q.mentions_said([{'literal': x} for x in h['literals']])} (its line {h['line']!r} at "
                            + ", ".join(h["where"][:2]) + (", …" if len(h["where"]) > 2 else "") + ")" for h in lines[:3])
        differ: dict[tuple, list[str]] = {}
        for key, whose in (("differ_name", "the file name's"), ("differ_carried", "the record's")):
            if lits := tuple(dict.fromkeys(x for h in lines for x in h[key])):
                differ.setdefault(lits, []).append(whose)
        differing = [f"{Q.mentions_said([{'literal': x} for x in lits])} {'differs' if len(lits) == 1 else 'differ'} "
                     f"from {' and '.join(whose)}" for lits, whose in differ.items()]
        head = (f"the scan header of {w['run_id']} writes {written}"
                + (f", the file name writes {'/'.join(w['names'][:3])}" if w.get("names") else "")
                + f", and the record carries {said}: {'; '.join(differing)} ("
                # r3c MED-1: the scale the differing mentions write, never one only another mention has
                + (f"file name: {w['name_scale']}; scan header: {w.get('mention_scale') or w['header_scale']}"
                   if w.get("names") else f"scan header: {w.get('mention_scale') or w['header_scale']}")
                + "). No value is read from that header line (not written in a plain form)")
        if w.get("targets") and not w.get("no_header_reading"):
            reject = w["command"].split(" --decision ")[0] + ' --decision reject --by "<your name>"'
            return (f"{head}; no one has ruled on it yet: "
                    + ("give the potential the run was held at (--decision correct --value <volts> --json): "
                       if "--decision correct" in w["command"] else "confirm the header's reading or correct it: ")
                    + w["command"] + f"; or reject the header reading if this line states no set-point: {reject}")
    if w.get("targets") and not w.get("no_header_reading"):
        return (f"{head}; no one has ruled on the scan header's reading yet: confirm it if the header is right, or "
                "correct it (--decision correct --value <volts> --json) to the potential the run was held at: "
                f"{w['command']}")
    if w.get("targets"):
        return (f"{head}; this bundle was imported before scan-header potentials were read as values, so rule on the "
                "record's own set-point instead: record it again (the same volts if the file name is right, the "
                f"header's if it is) with {w['command']}. Or re-import the beamtime ({REIMPORT_COMMAND}), but "
                f"{REIMPORT_CAVEAT}.")
    return (f"{head}; this bundle was imported before scan-header potentials were read as values, so there is no "
            f"reading to rule on: re-import the beamtime to rule on it ({w['command']}); {REIMPORT_CAVEAT}.")


def potential_warning_text(w: Mapping) -> str:
    """The plain sentence for a :data:`STATED_POTENTIAL_WARNING` warning, ending with its command."""
    from . import questions as Q  # c8-b: open circuit, and what scan headers state (questions.py)

    if w.get("code") == POTENTIAL_SOURCES_WARNING:
        return potential_sources_text(w)
    if w.get("code") == MACRO_SETPOINT_WARNING:
        return macro_setpoint_text(w)
    if w.get("code") == IN_SITU_WARNING:
        return in_situ_text(w)
    if w.get("code") == ATHENA_NOT_CHOSEN_WARNING:
        return athena_choice_text(w, w["group_id"])
    if w.get("code") == START_TIME_WARNING:
        return start_time_text(w)
    if w.get("open_circuit"):
        return Q.open_circuit_text(w)
    extra = Q.stated_potential_notes(w)
    # c16b: a set-point read from a scan header (it needs review) still says where it is written
    lits = "; ".join(Q.stated_literal(s)
                     + (f" in {'the scan header of ' if s.get('stated_in') == 'scan header' else ''}{s['relative_path']}"
                        if (s.get("read_as_V") is None or s.get("stated_in") == "scan header") and s.get("relative_path") else "")
                     + (f", read as {s['read_as_V']:g} V" if s.get("read_as_V") is not None else "")
                     for s in w["stated"][:3])
    if w.get("answered_V"):
        lits += "; the set-point answered for it: " + ", ".join(f"{v:g} V" for v in w["answered_V"][:3])
    if w.get("also_needs") and w.get("setpoint_needs_review"):
        # c16b: the set-point was read from a scan-header comment line and waits for review, as the scale does
        return (f"{Q.stated_opening(w, lits)} until the potential scale AND "
                f"the set-point read from the scan header are confirmed (or corrected).{extra} "
                f"Both: {w['also_command']}  ;  {w['command']}")
    if w.get("also_needs"):
        # no value was read for the set-point: the scientist gives the volts AND the scale, both commands now
        return (f"{Q.stated_opening(w, lits)} until the potential scale is "
                f"confirmed AND a set-point is given (no set-point value was read from the file names: give it in volts).{extra} "
                f"Both: {w['also_command']}  ;  {w['command']}")
    until = "the potential scale is confirmed" if w["needs"] == SCALE_PATH else "the potential set-point is confirmed"
    return (f"{Q.stated_opening(w, lits)} until {until}.{extra} "
            f"Do it: {w['command']}" if extra else
            f"{Q.stated_opening(w, lits)} until {until}: "
            f"{w['command']}")


def with_question_commands(bundle: Mapping, warnings: list[dict], payload: Mapping | None = None) -> list[dict]:
    """``warnings`` with each command answered through its consolidated question when one asks the value
    (``questions.command_for_targets``), and each ``text`` written. ``payload``: the questions, when built."""
    if not warnings:
        return warnings
    from . import questions as Q

    payload = payload or Q.consolidate(bundle)
    out = []
    for w in warnings:
        cmd = Q.command_for_targets(payload, w.get("targets") or (), w["needs"], w["group_id"]) or w["command"]
        w = {**w, "command": cmd}
        if w.get("fields"):
            # r6h H3: one command per field the warning names (an in-situ record's electrolyte, cell type, ...)
            w["fields"] = [{**f, "command": Q.command_for_targets(payload, f.get("targets") or (), f["path"], w["group_id"])
                            or f["command"]} for f in w["fields"]]
        if w.get("also_needs"):
            w["also_command"] = (Q.command_for_targets(payload, w.get("also_targets") or (), w["also_needs"], w["group_id"])
                                 or w["also_command"])
        out.append({**w, "text": potential_warning_text(w)})
    return out


#: The ONLY self-test marker (review minor): a fixed constant, never free text.
TEST_MARKER = "ISAAC SELF-TEST RECORD — NOT SCIENTIST-CONFIRMED — DO NOT UPLOAD"


def _apply_test_marker(draft: dict) -> list[str]:
    """Write :data:`TEST_MARKER` into the record's own NOTES fields (series notes, QC
    notes) — never as a field value with a confirmation it does not have."""
    placed = []
    for series in draft.get("series") or ():
        series["notes"] = TEST_MARKER
        placed.append("measurement.series[].notes")
    if draft.get("qc"):
        draft["qc"]["notes"] = TEST_MARKER
        placed.append("measurement.qc.notes")
    return placed


def contained_file(base: Path, relative: str) -> Path | None:
    """``base/relative`` if it is a regular file INSIDE ``base`` (no ``..``, no symlink
    escape), else ``None`` (review I2)."""
    if B._safe_relative(relative) is None:
        return None
    root = base.resolve()
    target = (base / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target if target.is_file() else None


def load_validated(bundle_dir: Path, *, allow_stale: bool = False) -> dict:
    """Load AND validate the bundle (review I1). A bundle that fails v1 is refused with the
    validator's own findings; nothing downstream reads an unvalidated bundle. A STALE bundle
    (eligibility an older build stored, ``bundle.stale_eligibility``) is refused with the
    remedy, unless ``allow_stale`` (``build-records``, which re-derives it under the lock)."""
    from . import mutations as M

    bundle = M.load(bundle_dir)
    errors, stale = B.validate_allowing_stale(bundle)
    if errors:
        raise RecordsRefused("The bundle does not meet v1, so nothing was composed:\n  - " + "\n  - ".join(errors[:20]), code=1)
    if stale and not allow_stale:
        raise RecordsRefused(
            f"The bundle is STALE: an older build stored {len(stale)} value(s) whose eligibility this build derives "
            f"differently (e.g. {stale[0]['id']}: {stale[0]['reason']}). Run `isaac bundle build-records` first: it "
            "re-derives them under the bundle lock and lists each one. Nothing was composed.", code=1)
    return bundle


def fresh_compositions(bundle_dir: Path, bundle: Mapping, *, test_marker: bool = False) -> list[tuple[str, dict, dict]]:
    """``(group_id, draft, composition)`` for every scientist-confirmed group, composed NOW
    from the validated bundle — the only thing validate and export trust (review C1)."""
    out = []
    for g in bundle.get("record_groups") or ():
        if g["status"] != "scientist_confirmed":
            continue
        draft, comp = compose_group(bundle, g, bundle_dir)
        if test_marker:
            comp["test_marker"] = {"text": TEST_MARKER, "placed": _apply_test_marker(draft)}
        out.append((g["group_id"], draft, comp))
    return out


def _on_disk_differs(bundle_dir: Path, group_id: str, draft: Mapping, comp: Mapping) -> bool:
    path = bundle_dir / DRAFTS_DIR / f"{group_id}.draft.json"
    if not path.is_file():
        return False
    try:
        disk = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return json.dumps(disk, sort_keys=True) != json.dumps(draft, sort_keys=True)


def build_records(bundle_dir: Path, *, test_marker: bool = False, full: bool = False) -> dict:
    from . import mutations as M

    bundle_dir = Path(bundle_dir)
    refusal = B.legacy_refusal(load_validated(bundle_dir, allow_stale=True))
    if refusal:  # a pre-1.2.0 bundle whose runs include the scientists' processed outputs
        raise RecordsRefused(refusal, code=2)

    def mark(b):  # the self-test state lives IN bundle.json, re-validated on write
        b["self_test"] = {"test_marker": bool(test_marker), "set_by": "isaac bundle build-records"}
        # the save re-derives any STALE eligibility under this lock and logs it (mutations.save_bundle)
        return B.stale_eligibility(b)

    rederived_now = M.mutate(bundle_dir, mark)
    bundle = load_validated(bundle_dir)
    groups = [g for g in bundle.get("record_groups") or () if g["status"] == "scientist_confirmed"]
    out_dir = bundle_dir / DRAFTS_DIR
    out_dir.mkdir(exist_ok=True)
    from .cli import _atomic_write, _json_bytes

    index = []
    composed = [(g, *compose_group(bundle, g, bundle_dir)) for g in groups]
    # THE WARNINGS (a stated condition the record will not carry), each command made its question's, once
    warned = with_question_commands(bundle, [w for _, _, report in composed for w in report.get("warnings") or ()])
    warnings_of: dict[str, list[dict]] = {}
    for w in warned:
        warnings_of.setdefault(w["group_id"], []).append(w)
    for g, draft, report in composed:
        report["warnings"] = warnings_of.get(g["group_id"], [])
        if test_marker:
            report["test_marker"] = {"text": TEST_MARKER, "placed": _apply_test_marker(draft)}
        _atomic_write(out_dir / f"{g['group_id']}.draft.json", _json_bytes(draft))
        _atomic_write(out_dir / f"{g['group_id']}.composition.json", _json_bytes(report))
        index.append(
            {
                "group_id": g["group_id"],
                "draft": f"{DRAFTS_DIR}/{g['group_id']}.draft.json",
                "filled": len(report["filled"]),
                "missing_required": [m["path"] for m in report["missing_required"]],
                "disagreements": len(report["disagreements"]),
                "complete": not report["missing_required"] and not report["disagreements"],
            }
            | ({"blocked": report["processing"]["reason"]} if (report.get("processing") or {}).get("not_applicable") else {})
            # why the processing-derived values are missing, in validate's and export's one word
            | ({"processing_blocker": processing_blocker(report.get("processing") or {})}
               if any(m.get("from") == "an approved processing result" for m in report["missing_required"])
               or (report.get("processing") or {}).get("not_applicable") else {})
            | ({"warnings": [w["text"] for w in report["warnings"]]} if report["warnings"] else {})
            # c12-r: the approved curve carries a shift that is now unconfirmed: said here, not only as a word
            | ({"calibration_unconfirmed": report["processing"]["calibration_unconfirmed"]}
               if (report.get("processing") or {}).get("calibration_unconfirmed") else {})
        )
    skipped = [
        {"group_id": g["group_id"], "status": g["status"], "reason": "only a scientist-confirmed record group becomes a draft"}
        for g in bundle.get("record_groups") or ()
        if g["status"] != "scientist_confirmed"
    ]
    result = {"drafts": index, "skipped_groups": skipped, "test_marker": bool(test_marker),
              "statement": "Drafts, not records. A draft with missing required values is incomplete and is never exported."}
    # c11-a: the warnings of complete drafts first; index.json (and --full) holds every one
    complete = [row["group_id"] for row in index if row["complete"]]
    result.update(warning_summary(warned, first=complete, marked="draft_complete", where=f"{DRAFTS_DIR}/index.json lists them all"))
    if rederived_now:
        result["eligibility_rederived_now"] = rederived_now
    every = {**result, **warning_summary(warned, first=complete, marked="draft_complete", full=True)}
    every.pop("warnings_omitted", None), every.pop("warnings_full_list", None)
    _atomic_write(out_dir / "index.json", _json_bytes(every))
    return every if full else result


# --- validation ----------------------------------------------------------------------------------


def _schema_error_keys(errors: Sequence[tuple[str, str]]) -> set[tuple[str, str]]:
    import re

    keys = set()
    for path, message in errors:
        m = re.match(r"'([^']+)' is a required property", message)
        keys.add((path.replace("/", ".").strip(".$") or "$", m.group(1) if m else message[:80]))
    return keys


def _portal_demands_undeclared(portal_check: Mapping | None) -> list[dict]:
    """Portal errors naming a field the VENDORED schema does not declare under a parent
    that forbids unknown keys — a requirement no v1.05 record can ever satisfy."""
    out = []
    result = (portal_check or {}).get("result") or {}
    for err in result.get("errors") or ():
        path = str(err.get("path") or "").replace("/", ".").strip(".")
        if not path or "." not in path:
            continue
        if B._schema_node(path) is not None:
            continue
        parent = B._schema_node(path.rsplit(".", 1)[0])
        if parent is not None and parent.get("additionalProperties") is False:
            out.append(
                {
                    "path": path,
                    "portal_code": err.get("code"),
                    "explanation": (
                        f"The upstream portal requires {path}; vendored v1.05 does not declare it "
                        "and forbids unknown keys there, so no record exported through the "
                        "vendored schema can satisfy both."
                    ),
                }
            )
    return out


def schema_drift(record: Mapping, upstream: Mapping | None, portal_check: Mapping | None = None) -> dict:
    """Vendored-vs-upstream disagreement about THIS record, both directions, plus the
    one known shape of drift: an unknown temperature (upstream: ``temperature_K: null`` +
    ``temperature_basis: not_reported``; vendored: a number is required, no basis field)."""
    from jsonschema import Draft202012Validator
    from isaac_records.official import validate_official

    if upstream is None:
        demanded = _portal_demands_undeclared(portal_check)
        return {
            "status": "upstream_schema_unavailable",
            "portal_requires_undeclared_fields": demanded,
            "blocked_by_schema_drift": bool(demanded),
        }
    vendored_errors = [(e.path, e.message) for e in validate_official(dict(record), _repo_root()).errors]
    upstream_errors = [
        (".".join(str(p) for p in err.absolute_path), err.message)
        for err in Draft202012Validator(upstream).iter_errors(record)
    ]
    v, u = _schema_error_keys(vendored_errors), _schema_error_keys(upstream_errors)
    out = {
        "status": "compared",
        "vendored_only": sorted(map(list, v - u)),
        "upstream_only": sorted(map(list, u - v)),
    }
    context = record.get("context") if isinstance(record.get("context"), Mapping) else None
    if context is not None and context.get("temperature_K") is None:
        probe = json.loads(json.dumps(record))
        probe["context"]["temperature_K"] = None
        probe["context"]["temperature_basis"] = "not_reported"
        up_ok = not any(
            "temperature" in ".".join(map(str, e.absolute_path)) + e.message
            for e in Draft202012Validator(upstream).iter_errors(probe)
        )
        v_ok = not any("temperature" in e.path + e.message for e in validate_official(probe, _repo_root()).errors)
        if up_ok and not v_ok:
            out["temperature"] = (
                "The temperature is unknown. The portal's pinned schema, which the local export validates "
                "against, accepts temperature_K: null with temperature_basis: not_reported, and the record "
                "says that; the website's older vendored v1.05 schema requires a number and has no "
                "temperature_basis. This does NOT block the local export: it only means the record does not "
                "pass the website schema, which is reported for information. Nothing is defaulted; a "
                "temperature a scientist states satisfies both."
            )
    demanded = _portal_demands_undeclared(portal_check)
    if demanded:
        out["portal_requires_undeclared_fields"] = demanded
    out["blocked_by_schema_drift"] = bool(
        out.get("vendored_only") or out.get("upstream_only") or out.get("temperature") or demanded
    )
    return out


def compose_record(draft: Mapping, composition: Mapping | None, *, record_id: str, now: str) -> dict:
    """The official-shape record for the PORTAL'S schema (DEC-76).

    Reuses the truth plane's own functions — ``isaac_records.export.transform`` and
    ``isaac_records.export.set_path`` — and does not edit them. ``export_draft`` is NOT
    used: its ``transform`` drops every null field, so it cannot write the upstream
    schema's ``temperature_K: null`` (with ``temperature_basis: not_reported``); that one
    shape is applied here from the composition's ``record_overrides`` after ``transform``.
    """
    from isaac_records.export import set_path, transform

    record = transform(dict(draft), record_id=record_id, now=now)
    for path, value in ((composition or {}).get("record_overrides") or {}).items():
        # ONLY the derivation this module owns (review C1): an unknown temperature is null.
        if path not in RECORD_OVERRIDE_ALLOWLIST or value != RECORD_OVERRIDE_ALLOWLIST[path]:
            raise RecordsRefused(f"record override {path!r}={value!r} is not a derivation this composer owns", code=1)
        set_path(record, path, value)
    return record


#: ``path -> the one value`` a composition may override after ``transform``.
RECORD_OVERRIDE_ALLOWLIST = {"context.temperature_K": None}


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def schemas_used(where: Mapping) -> dict:
    """Which schema each verdict used — sha and source, never a local path."""
    target = None
    if where.get("available"):
        target = {
            "source": "ISAAC-DOE/isaac-ai-ready-record (pinned upstream clone)",
            "commit": where.get("commit"),
            "pinned_commit": where.get("pinned_commit"),
            "schema_sha256": _sha256(Path(where["dir"]) / "schema" / "isaac_record_v1.json"),
            "gates": ["official schema", "exactness", "portal validate_record_full"],
        }
    return {
        "local_export_target": target,
        "website_schema": {
            "source": "vendored schema/isaac_record_v1.json (v1.05, July)",
            "schema_sha256": _sha256(_repo_root() / "schema" / "isaac_record_v1.json"),
            "gates": [],
            "statement": "Reported for information only. It does not gate the local export, and nothing here is claimed valid for the website.",
        },
    }


def validate_draft_file(draft: Mapping, *, run_portal, composition: Mapping | None = None) -> dict:
    """Every gate, verbatim, and which schema each used. ``verdict`` is the honest word.

    Gating (DEC-76): ISAAC's own ``validate_official`` and ``check_exactness`` with
    ``root`` = the pinned upstream clone, plus the offline portal check. The vendored
    v1.05 result is computed and reported as ``website_schema`` and gates nothing."""
    from isaac_records.draft_validator import validate_draft
    from isaac_records.exactness import check_exactness
    from isaac_records.official import validate_official

    from . import portal as P

    where = P.locate()
    dr = validate_draft(draft)
    missing = sorted(p for p, env in (draft.get("fields") or {}).items() if isinstance(env, dict) and env.get("status") == "missing")
    record = compose_record(draft, composition, record_id="0" * 26, now="1970-01-01T00:00:00Z")
    website = validate_official(record, _repo_root())
    target_official = target_exact = None
    if where.get("available"):
        upstream_root = Path(where["dir"])
        target_official = validate_official(record, upstream_root)
        target_exact = check_exactness(record, upstream_root)
    portal_check = run_portal(record)
    drift = schema_drift(record, P.upstream_schema(where), portal_check)
    pv = portal_check.get("verdict") or P.verdict_of(portal_check)
    proc = (composition or {}).get("processing") or {}
    blocked = proc.get("reason") if proc.get("not_applicable") else None
    # THE PROCESSING-DERIVED REQUIRED VALUES (measurement.series, measurement.qc.status,
    # descriptors.outputs) are not draft fields, so a draft without them has no `status: missing`
    # envelope for them; the composition lists them. They are missing here too, and the fix is the
    # processing result's approval — never "correct the value".
    from_processing = [m["path"] for m in (composition or {}).get("missing_required") or ()
                       if m.get("from") == "an approved processing result"]
    # c12-q: and every value the composition lists as an answer's to give, even one the draft holds no placeholder
    # for (a scale confirmed for some runs of the group, so the confirmed set-point it holds back needs it for the rest)
    from_answers = [m["path"] for m in (composition or {}).get("missing_required") or () if m.get("from") == FROM_AN_ANSWER]
    missing = sorted(set(missing) | set(from_processing) | set(from_answers))
    processing_fix = None if blocked or not from_processing else processing_remedy(proc)
    if missing or not dr.ok or blocked:
        verdict = "incomplete"
    elif target_official is None:
        verdict = P.VERDICT_UNAVAILABLE
    elif not (target_official.ok and target_exact.ok):
        verdict = "invalid_official"
    elif pv != "publish":
        verdict = pv if pv in (P.VERDICT_UNAVAILABLE, P.VERDICT_DEGRADED) else f"portal_{pv}"
    else:
        verdict = "exportable"
    result = (portal_check.get("result") or {}) if portal_check.get("status") == "ran" else {}
    used = schemas_used(where)
    commit = (used["local_export_target"] or {}).get("commit") or "unavailable"
    summary = [
        f"Draft checks: {'pass' if dr.ok else 'FAIL'} ({len(dr.errors)} error(s), {len(dr.warnings)} warning(s)).",
        f"Missing required values: {', '.join(missing) if missing else 'none'}.",
        *([f"Processing: {blocked}. The record's series, QC status and E0 cannot be supplied, so it stays incomplete."] if blocked else []),
        *([f"Processing: {', '.join(from_processing)} come from the group's processing result, and {processing_fix}"]
          if processing_fix else []),
        (
            f"Portal-target schema (upstream {commit[:12]}): {'pass' if target_official.ok else 'FAIL'} "
            f"({len(target_official.errors)} error(s)); exactness: {'pass' if target_exact.ok else 'FAIL'}."
            if target_official is not None
            else "Portal-target schema: not available — install the pinned validator. This is not a pass."
        ),
        (
            f"Upstream portal check: {portal_check.get('outcome')} "
            f"({len(result.get('errors') or [])} error(s), {len(result.get('warnings') or [])} warning(s))."
            if portal_check.get("status") == "ran"
            else f"Upstream portal check: not run — {portal_check.get('reason')}. This is not a pass."
        ),
        f"Website schema (vendored v1.05, July), for information only: {'pass' if website.ok else 'FAIL'} ({len(website.errors)} error(s)). Not claimed valid for the website.",
        "This is NOT an official record until `isaac bundle export` writes one, and nothing has been uploaded.",
    ]
    return {
        "verdict": verdict,
        "plain_summary": summary,
        "schemas_used": used,
        "draft_validation": {"ok": dr.ok, "errors": [list(e) for e in dr.errors], "warnings": [list(w) for w in dr.warnings]},
        "missing_required": missing,
        "missing_from_processing": from_processing,
        "processing_fix": processing_fix,
        "processing_blocker": processing_blocker(proc) if (blocked or from_processing) else None,
        "processing_blocked": blocked,
        "composition": {
            "reused": ["isaac_records.export.transform", "isaac_records.export.set_path", "isaac_records.export.build_sidecar"],
            "not_used": "isaac_records.export.export_draft (its transform drops null fields, so it cannot write temperature_K: null)",
            "record_overrides": dict((composition or {}).get("record_overrides") or {}),
        },
        "official_validation": (
            {"schema": "local_export_target", "ok": target_official.ok,
             "errors": [{"path": e.path, "message": e.message} for e in target_official.errors]}
            if target_official is not None else {"schema": "local_export_target", "ok": None, "errors": [], "status": "unavailable"}
        ),
        "exactness": (
            {"schema": "local_export_target", "ok": target_exact.ok, "errors": [str(e) for e in target_exact.errors]}
            if target_exact is not None else {"schema": "local_export_target", "ok": None, "errors": [], "status": "unavailable"}
        ),
        "website_schema": {
            "schema": "website_schema",
            "ok": website.ok,
            "errors": [{"path": e.path, "message": e.message} for e in website.errors],
            "gates_export": False,
        },
        "portal_check": portal_check,
        "schema_drift": drift,
    }


def reprocess_cannot_help(result: Mapping) -> bool:
    """:func:`mutations.reprocess_cannot_help` (imported here lazily, as this module imports mutations)."""
    from .mutations import reprocess_cannot_help as cannot

    return cannot(result)


def no_curve_cause(result: Mapping) -> str:
    """:func:`mutations.no_curve_cause` (imported here lazily, as this module imports mutations)."""
    from .mutations import no_curve_cause as cause

    return cause(result)


def unusable_curve_reasons(result: Mapping) -> list[str]:
    """:func:`mutations.unusable_curve_reasons` (imported here lazily, as this module imports mutations)."""
    from .mutations import unusable_curve_reasons as reasons

    return reasons(result)


def processing_blocker(processing: Mapping) -> str:
    """One word for why a group's processing-derived values are missing (the export's counts)."""
    if processing.get("not_applicable"):
        return "processing_not_applicable"
    if processing.get("approved_results"):
        return "more_than_one_approved_result"
    if processing.get("result"):
        if processing.get("calibration_unconfirmed"):
            return "approved_result_calibration_unconfirmed"
        if processing.get("no_curve"):
            return "approved_result_has_no_curve"
        return "approved_result_not_a_usable_spectrum" if processing.get("unusable_curve") else "approved_result_not_usable"
    if processing.get("awaiting_approval"):
        return "processing_awaiting_approval"
    if processing.get("unusable_curve_results"):
        return "processing_result_not_a_usable_spectrum"
    if processing.get("no_curve_results"):
        return "processing_result_has_no_curve"
    if processing.get("rejected"):
        return "processing_result_rejected"
    return "no_processing_result"


def processing_remedy(processing: Mapping) -> str:
    """The sentence saying how a group's processing-derived values get into its record."""
    from .mutations import reprocess_command

    waiting = list(processing.get("awaiting_approval") or ())
    rejected = list(processing.get("rejected") or ())
    gid = processing.get("group_id") or "<group id>"
    leave_out = f'leave the group out of the records (`isaac bundle decide <bundle_dir> --target {gid} --decision reject --by "<your name>"`)'
    no_curve = dict(processing.get("no_curve_results") or {})
    unusable = dict(processing.get("unusable_curve_results") or {})
    # c8-a: a result whose QC says its curve is not a usable spectrum is NEVER offered for approval (decide refuses it)
    not_offered = ("; ".join(f"{pid} is not offered for approval: its QC fails {why}, so its curve is not a usable "
                             "spectrum" for pid, why in list(unusable.items())[:3])
                   + (" …" if len(unusable) > 3 else "")) if unusable else ""
    several = list(processing.get("approved_results") or ())
    if several:
        # an older build let a second approval through; `decide` now refuses it. Re-processing changes nothing
        how_many = "two" if len(several) == 2 else str(len(several))
        return (f"{how_many} results approved for this group; approve exactly one: {', '.join(several)}. A record uses "
                "one processing result, so with more than one approved it uses none. Keep the one the record should "
                "use and withdraw the other approval: "
                + " / ".join(f'`isaac bundle decide <bundle_dir> --target {pid} --decision defer --by "<your name>"`'
                             for pid in several)
                + " (or --decision reject).")
    if processing.get("result") and processing.get("calibration_unconfirmed"):
        # c12-r: never "re-run and approve": the approved result is kept on re-processing, and so is its shift
        pid = processing["result"]
        said = processing["calibration_unconfirmed"]
        return (f"the approved result {pid} is not used: {said[0].lower() + said[1:]} Until one of these is done the "
                "record has no series, QC status or E0 and is not exported.")
    if processing.get("result") and processing.get("no_curve") and processing.get("no_retry"):
        # r5f L1: its scans share too few points: processing again cannot add any, so only withdraw or leave out
        pid = processing["result"]
        return (f"the approved result {pid} has no curve ({processing['no_curve']}): its scans share too few points to "
                "merge, and processing again cannot add points the scans do not have. Withdraw the approval "
                f'(`isaac bundle decide <bundle_dir> --target {pid} --decision reject --by "<your name>"`), or {leave_out}.')
    if processing.get("result") and processing.get("no_curve"):
        # NEVER "re-run and approve the new result": the same parameters give the same no-curve result
        pid = processing["result"]
        return (f"the approved result {pid} has no curve ({processing['no_curve']}): it was approved without an output "
                "file, and re-running `isaac process` with the same parameters gives the same result. Withdraw the "
                f'approval (`isaac bundle decide <bundle_dir> --target {pid} --decision reject --by "<your name>"`), then '
                f"either re-process the group with other parameters ({reprocess_command(gid)}) and approve the new result "
                f"if it has a curve, or {leave_out}.")
    if processing.get("result") and processing.get("unusable_curve"):
        # c8-r: approved before `decide` refused it; never "re-run and approve": the same parameters give the same curve
        pid = processing["result"]
        why = f" ({processing['unusable_curve_said']})" if processing.get("unusable_curve_said") else ""
        return (f"the approved result {pid} is not a usable spectrum: its QC fails {processing['unusable_curve']}{why}, "
                "so its curve does not describe the data and nothing from it goes into the record (it was approved "
                "before `decide` refused such an approval). Re-running `isaac process` with the same parameters gives "
                "the same result. Withdraw the approval: reject the result "
                f'(`isaac bundle decide <bundle_dir> --target {pid} --decision reject --by "<your name>"`), or mark it '
                f"needs_changes (`--target {pid} --decision needs_changes`) and re-process the group with a setting the "
                f"scientist chooses ({reprocess_command(gid)}), then approve the new result if its curve is usable; "
                f"or {leave_out}.")
    if processing.get("result"):
        said = "; ".join(f"{k}: {processing[k]}" for k in ("series", "qc", "approval") if processing.get(k))
        return (f"the approved result {processing['result']} did not supply them" + (f" ({said})" if said else "")
                + ". Re-run `isaac process <bundle_dir> --source <the beamtime folder you imported>` and approve the new result, stating its QC status.")
    if waiting:
        return ("no processing result is approved yet: review the draft processing and approve it, stating its QC status: "
                + " / ".join(f'`isaac bundle decide <bundle_dir> --target {pid} --decision approve --qc-status <value> --by "<your name>"`'
                             for pid in waiting[:3])
                + (f" (and {len(waiting) - 3} more)" if len(waiting) > 3 else "")
                + '; a QC status of compromised or failed also needs --qc-note "<what and why>"'
                + ". Correcting a value does not supply them."
                + (f" ({not_offered}.)" if not_offered else ""))
    if unusable:
        ids = list(unusable)
        return (f"its processing result cannot be approved: {not_offered}. Re-running `isaac process` with the same "
                f"parameters gives the same result. Reject it "
                f'(`isaac bundle decide <bundle_dir> --target {ids[0]} --decision reject --by "<your name>"`), or mark it '
                f"needs_changes (`--target {ids[0]} --decision needs_changes`) and re-process the group with a setting "
                f"the scientist chooses ({reprocess_command(gid)}), then approve the new result if its curve is usable; "
                f"or {leave_out}.")
    if no_curve and set(no_curve) <= set(processing.get("no_retry_results") or ()):
        # r5f L1: the scans share too few points; no params file adds any
        ids = list(no_curve)
        said = "; ".join(f"{pid} ({cause})" for pid, cause in list(no_curve.items())[:3]) + (" …" if len(ids) > 3 else "")
        return (f"its processing result has no curve, so there is nothing to approve: {said}. Its scans share too few "
                "points to merge, and processing again, with these or other parameters, cannot add points the scans do "
                "not have. Reject the result "
                f'(`isaac bundle decide <bundle_dir> --target {ids[0]} --decision reject --by "<your name>"`), and {leave_out} '
                "unless a scientist knows these scans belong with others.")
    if no_curve:
        ids = list(no_curve)
        said = "; ".join(f"{pid} ({cause})" for pid, cause in list(no_curve.items())[:3]) + (" …" if len(ids) > 3 else "")
        return (f"its processing result has no curve, so there is nothing to approve: {said}. Re-running `isaac process` "
                "with the same parameters gives the same result. Reject it "
                f'(`isaac bundle decide <bundle_dir> --target {ids[0]} --decision reject --by "<your name>"`), then either '
                f"re-process the group with other parameters ({reprocess_command(gid)}) and approve the new result if it "
                f"has a curve, or {leave_out}.")
    if rejected:
        return (f"its processing result was rejected ({', '.join(rejected[:3])}{' …' if len(rejected) > 3 else ''}), and "
                "no other result is waiting for approval. Re-running `isaac process` with the same parameters keeps the "
                f"rejected result as it is. Either re-process the group with other parameters ({reprocess_command(gid)}) "
                f"and approve the new result, stating its QC status, or {leave_out}.")
    return ("no processing result exists for this group: run `isaac process <bundle_dir> --source <the beamtime folder you imported>`, then approve the result "
            '(`isaac bundle decide <bundle_dir> --target <result id> --decision approve --qc-status <value> --by "<your name>"`).')


#: How many not-exportable groups ``validate`` (and a compact ``build-records``) name with their reasons.
REASONS_SHOWN = 3
#: The plain-summary lines that say nothing about why ONE group is not exportable (left off the compact rows).
_BOILERPLATE_PREFIXES = ("Website schema (vendored", "This is NOT an official record")


#: How many warnings ``build-records`` and ``validate`` print in full (``warnings_total`` counts them all).
WARNINGS_SHOWN = 5


def warning_rank(code: str | None) -> int:
    """r5f M6: how much a warning matters when only the first few are printed: 0 = a stated value left out of the
    record, or a value its sources disagree about (r6h H2: a macro's set-point too), or a portal warning; 1 = anything
    else; 2 = the routine start-time note. Only ORDERS the short list: nothing is dropped, and ``--full`` keeps the
    original order."""
    code = str(code or "")
    if code in (STATED_POTENTIAL_WARNING, POTENTIAL_SOURCES_WARNING, ATHENA_NOT_CHOSEN_WARNING,
                MACRO_SETPOINT_WARNING) or code.startswith("portal:"):
        return 0
    return 2 if code == START_TIME_WARNING else 1


def warning_summary(warned: Sequence[Mapping], *, first: Iterable[str] | None = None, full: bool = False,
                    marked: str = "group_exportable", where: str | None = None) -> dict:
    """``{"warnings": [{group_id, code, text, command}, ...], "warnings_total": n}`` for the reply, or ``{}``.

    c11-a: a warning is never invisible. The warnings of the groups in ``first`` (exportable, or a complete draft)
    come FIRST, each row saying so (``marked``: true or false), so a record about to be written is never the 68th of
    73 warnings; ``full`` prints every one; when some are left out, ``warnings_full_list`` says how to see them."""
    if not warned:
        return {}
    lead = set(first) if first is not None else None
    ordered = ([w for w in warned if w["group_id"] in lead] + [w for w in warned if w["group_id"] not in lead]
               if lead is not None else list(warned))
    if not full:
        # r5f M6: SEVERITY first (a stated value left out of a record before the routine start-time note), so the five
        # shown are never five copies of the note while a stated value is left out; at equal severity the exportable
        # groups' warnings (``first``) still lead (c11-a)
        ordered = sorted(ordered, key=lambda w: (warning_rank(w.get("code")), lead is not None and w["group_id"] not in lead))
    shown = ordered if full else ordered[:WARNINGS_SHOWN]
    # r5c C6: a warning that names two steps keeps the second (``also_needs``, ``also_command``): SKILL.md Step 8 and
    # records-and-validation.md tell the agent to read them
    rows = [{k: w[k] for k in ("group_id", "code", "text", "command")}
            | {k: w[k] for k in ("also_needs", "also_command") if w.get(k)}
            | ({marked: w["group_id"] in lead} if lead is not None else {}) for w in shown]
    out: dict = {"warnings": rows, "warnings_total": len(warned)}
    if len(shown) < len(warned):
        out["warnings_omitted"] = len(warned) - len(shown)
        out["warnings_full_list"] = ("Pass --full to print every warning" + (f"; {where}" if where else "") + ".")
    return out


#: A question id as the warnings print it (``Q-`` and ten hex digits): the one part of a start-time note that differs
#: between records.
_QUESTION_ID_IN_TEXT = re.compile(r"\bQ-[0-9a-f]{6,}\b")
#: r8 LOW: the parts of an in-situ note that differ between records: the file names it quotes, and the group its
#: command names. Folded by code (:func:`fold_key`), with the count, every file name and every quoted token kept.
_IN_SITU_LEAD = "what it was measured in would be absent from the record"
_IN_SITU_STATED = re.compile(r"; the file names state (?P<said>.*?) \(quoted, never read as a value\)")
_IN_SITU_ITEM = re.compile(r"(?P<tok>[^\s,;()]+) \((?P<file>[^()]*)\)")
_GROUP_ID_IN_TEXT = re.compile(r"\brg-[0-9a-f]{6,}\b")


def fold_key(text: Any) -> str:
    """The text a warning is said once under: its question id as ``<question id>``; an in-situ note also without the
    file names it quotes and with its group as ``<group id>`` (r8: the same note on ten records was said ten times)."""
    t = _QUESTION_ID_IN_TEXT.sub("<question id>", str(text))
    if _IN_SITU_LEAD in t:
        t = _GROUP_ID_IN_TEXT.sub("<group id>", _IN_SITU_STATED.sub("; the file names state <tokens> (quoted)", t))
    return t


def group_by_text(per_record: Iterable[Iterable[str]]) -> list[dict]:
    """r5f L3: the same warning on many records, said ONCE: ``[{text, records, example_question}]`` over the lists of
    warning texts of each record (a text counts once per record). Two texts are the same when they differ only in the
    question id they name; ``text`` shows the first with its id as ``<question id>``, and ``example_question`` is that
    first id (``None`` when the text names none). Most records first, ties in first-seen order."""
    per_record = [list(texts) for texts in per_record]
    seen: dict[str, dict] = {}
    for texts in per_record:
        for key in dict.fromkeys(fold_key(t) for t in texts):
            row = seen.setdefault(key, {"text": key, "records": 0, "example_question": None})
            row["records"] += 1
    # the example id: the first one a text names, in the order the records were given
    for texts in per_record:
        for t in texts:
            m = _QUESTION_ID_IN_TEXT.search(str(t))
            row = seen.get(fold_key(t))
            if m and row is not None and row["example_question"] is None:
                row["example_question"] = m.group(0)
            said = _IN_SITU_STATED.search(str(t)) if row is not None and _IN_SITU_LEAD in str(t) else None
            if said:
                # r8 LOW: the in-situ note, said once, keeps every file name and every token it quotes
                for item in _IN_SITU_ITEM.finditer(said.group("said")):
                    row.setdefault("files", [])
                    row.setdefault("quoted", [])
                    if item.group("file") not in row["files"]:
                        row["files"].append(item.group("file"))
                    if item.group("tok") not in row["quoted"]:
                        row["quoted"].append(item.group("tok"))
    return sorted(seen.values(), key=lambda r: -r["records"])


def grouped_sentence(rows: Sequence[Mapping]) -> str:
    """One sentence for :func:`group_by_text` rows: each text once, with how many records carry it and one example."""
    return "; ".join(f"{r['text']} ({r['records']} record(s)" + (f", e.g. question {r['example_question']}" if r["example_question"] else "")
                     + (f"; the file names state {', '.join(r['quoted'])}, in {', '.join(r['files'])}" if r.get("quoted") else "")
                     + ")" for r in rows)


def warnings_outcome_sentence(rows: Sequence[Mapping]) -> str:
    """The sentence ``export``'s ``outcome`` adds for :func:`group_by_text` rows: at most :data:`WARNINGS_SHOWN` kinds,
    then how many more there are (the structured ``warnings_by_text`` keeps every one)."""
    more = len(rows) - WARNINGS_SHOWN
    return (" Warnings that apply, each said once: " + grouped_sentence(rows[:WARNINGS_SHOWN])
            + (f"; and {more} more kind{'' if more == 1 else 's'}" if more > 0 else "") + " (`warnings_by_text`).")


def portal_warnings_of(report: Mapping) -> list[dict]:
    """r4-b M7: the upstream portal validator's own WARNINGS for one record (``portal_check.result.warnings``, kept
    verbatim in ``validation/<group>.json``), as ``[{code, path, message}]``; ``[]`` when it did not run. A warning
    never changes the verdict (``publish`` with warnings is still exportable); it is said, not hidden."""
    pc = report.get("portal_check") or {}
    if pc.get("status") != "ran":
        return []
    out = []
    for w in (pc.get("result") or {}).get("warnings") or ():
        if isinstance(w, Mapping):
            out.append({"code": str(w.get("code") or "PORTAL_WARNING"), "path": w.get("path"),
                        "message": str(w.get("message") or w.get("code") or "")})
        else:
            out.append({"code": "PORTAL_WARNING", "path": None, "message": str(w)})
    return out


def portal_warning_summary(by_group: Mapping[str, Sequence[Mapping]]) -> list[dict]:
    """r4-b M7: each distinct portal warning ONCE (its code and message), with how many records it is on and the first
    of their groups: what ``validate`` and ``export`` print instead of the same warning on 78 records."""
    seen: dict[tuple, dict] = {}
    for gid, ws in by_group.items():
        for w in ws:
            row = seen.setdefault((w["code"], w["message"]), {**w, "records": 0, "group_ids": []})
            if gid not in row["group_ids"]:
                row["records"] += 1
                row["group_ids"].append(gid)
    return [{**r, "group_ids": r["group_ids"][:REASONS_SHOWN],
             "text": f"The portal validator warns on {r['records']} record(s) ({r['code']}"
                     + (f", {r['path']}" if r.get("path") else "") + f"): {r['message']}"}
            for r in sorted(seen.values(), key=lambda r: (-r["records"], r["code"]))]


#: What a warning's ``path`` is called in ``export``'s "Written without …" line (else the path itself).
WRITTEN_WITHOUT_NAMES = {SETPOINT_PATH: "the potential set-point", B.CONTROL_MODE_PATH: "the open-circuit condition"}


def written_without(w: Mapping) -> str:
    """``export``'s line for a record WRITTEN while warning ``w`` still applies: "Written without the potential
    set-point: <the warning's sentence>" (c11-a: an export is never silent about a condition the record lacks)."""
    if w.get("code") == POTENTIAL_SOURCES_WARNING:
        return f"Written with a potential its files disagree about: {w['text']}"
    if w.get("code") == START_TIME_WARNING:
        return f"Written without the start time: {w['text']}"
    if w.get("code") == MACRO_SETPOINT_WARNING:
        return f"Written with a set-point its macro disagrees about: {w['text']}"
    if w.get("code") == IN_SITU_WARNING:
        return f"Written without what it was measured in: {w['text']}"
    if w.get("code") == ATHENA_NOT_CHOSEN_WARNING:
        return f"Written with an approved curve that is not the chosen Athena version: {w['text']}"
    name = WRITTEN_WITHOUT_NAMES.get(w.get("path"), w.get("path") or "a stated condition")
    return f"Written without {name}: {w['text']}"


def first_official_error(report: Mapping) -> str | None:
    """``"<path>: <message>"`` of the first error the portal-target schema gave (else the portal check's first
    schema error), or ``None``: the words ``Portal-target schema … FAIL (1 error(s))`` stood for."""
    errors = list((report.get("official_validation") or {}).get("errors") or ())
    if not errors:
        errors = list((((report.get("portal_check") or {}).get("result") or {}).get("schema_errors")) or ())
    if not errors:
        return None
    e = errors[0]
    return f"{e.get('path')}: {e.get('message')}" if isinstance(e, Mapping) else str(e)


def refusal_counts(rows: Sequence[Mapping]) -> tuple[dict[str, int], dict[str, int]]:
    """``(by_reason, missing_required_by_field)`` over rows carrying ``verdict``, ``processing_blocker`` and
    ``missing_required``: the counts ``export`` (``refused_by_reason``) and ``validate`` (``by_reason``) print."""
    by_reason: dict[str, int] = {}
    by_field: dict[str, int] = {}
    for row in rows:
        for key in filter(None, (row.get("verdict"), row.get("processing_blocker"))):
            by_reason[key] = by_reason.get(key, 0) + 1
        for path in row.get("missing_required") or ():
            by_field[path] = by_field.get(path, 0) + 1
    return (dict(sorted(by_reason.items(), key=lambda kv: (-kv[1], kv[0]))),
            dict(sorted(by_field.items(), key=lambda kv: (-kv[1], kv[0]))))


def plain_reasons(summary: Sequence[str]) -> list[str]:
    """A group's plain-summary lines without the two that are the same for every group."""
    return [line for line in summary if not str(line).startswith(_BOILERPLATE_PREFIXES)]


def validate_records(bundle_dir: Path, *, run_portal=None, full: bool = False) -> dict:
    """Validate a FRESH composition of every confirmed group (review C1/I1). An on-disk
    draft that differs from it is flagged and never used."""
    from . import portal as P
    from .cli import _atomic_write, _json_bytes

    run_portal = run_portal or P.run_portal_check
    bundle_dir = Path(bundle_dir)
    bundle = load_validated(bundle_dir)
    marked = _was_marked(bundle)
    out_dir = bundle_dir / VALIDATION_DIR
    out_dir.mkdir(exist_ok=True)
    verdicts, stale, not_exportable = {}, [], []
    portal_warned: dict[str, list[dict]] = {}
    fresh = fresh_compositions(bundle_dir, bundle, test_marker=marked)
    warned = with_question_commands(bundle, [w for _, _, comp in fresh for w in comp.get("warnings") or ()])
    for group_id, draft, composition in fresh:
        if _on_disk_differs(bundle_dir, group_id, draft, composition):
            stale.append(group_id)
        report = validate_draft_file(draft, run_portal=run_portal, composition=composition)
        report["group_id"] = group_id
        report["composed_from"] = "the validated bundle, now (an on-disk draft is never trusted)"
        report["on_disk_draft_differs"] = group_id in stale
        report["warnings"] = [w for w in warned if w["group_id"] == group_id]
        _atomic_write(out_dir / f"{group_id}.json", _json_bytes(report))
        verdicts[group_id] = report["verdict"]
        if pw := portal_warnings_of(report):
            portal_warned[group_id] = pw
        if report["verdict"] != "exportable":
            not_exportable.append({"group_id": group_id, "verdict": report["verdict"],
                                   "missing_required": report["missing_required"],
                                   "processing_blocker": report["processing_blocker"],
                                   "reasons": plain_reasons(report["plain_summary"]),
                                   **({"first_official_error": e} if (e := first_official_error(report)) else {})})
    out: dict = {}
    if verdicts:
        # WHY, COUNTED, FIRST (1.9.x polish): the verdict map alone meant opening every validation file to explain it
        by_reason, by_field = refusal_counts(not_exportable)
        out.update(
            exportable=sum(1 for v in verdicts.values() if v == "exportable"),
            not_exportable=len(not_exportable),
            by_reason=by_reason,
            missing_required_by_field=by_field,
            not_exportable_first=[{k: row[k] for k in ("group_id", "verdict", "reasons", "first_official_error") if k in row}
                                  for row in not_exportable[:REASONS_SHOWN]],
            not_exportable_omitted=max(0, len(not_exportable) - REASONS_SHOWN),
            reports=f"{VALIDATION_DIR}/<group_id>.json holds each group's full report (every gate, verbatim).",
        )
    # r8: the condition labels' own warnings (two ready records ISAAC cannot tell apart; a label not proposed)
    warned = warned + L.record_warnings(bundle, fresh, [g for g, v in verdicts.items() if v == "exportable"])
    out.update(warning_summary(warned, first=[g for g, v in verdicts.items() if v == "exportable"], full=full,
                               where=f"{VALIDATION_DIR}/<group_id>.json lists each group's"))
    if portal_warned:
        # r4-b M7: the portal validator's own warnings, each ONCE with its record count (before: only in
        # validation/<group>.json, "publish (0 error(s), 2 warning(s))", and never said here)
        said = portal_warning_summary(portal_warned)
        out["portal_warnings"] = said
        portal_rows = [{"group_id": None, "code": f"portal:{w['code']}", "text": w["text"], "command": None,
                        "records": w["records"]} for w in said]
        rows = list(out.get("warnings") or ())
        total = int(out.get("warnings_total") or 0) + len(portal_rows)
        if full:
            rows += portal_rows
        else:
            # r5f M6: a portal warning ranks with the severe ones, ahead of the routine start-time note
            rows = sorted(rows + portal_rows, key=lambda w: warning_rank(w.get("code")))[:WARNINGS_SHOWN]
        out["warnings"] = rows
        out["warnings_total"] = total
        if len(rows) < total:
            out["warnings_omitted"] = total - len(rows)
            out.setdefault("warnings_full_list", "Pass --full to print every warning; "
                           f"{VALIDATION_DIR}/<group_id>.json lists each group's.")
        else:
            out.pop("warnings_omitted", None), out.pop("warnings_full_list", None)
    from .propose_terms import pending_vocabulary

    pending = pending_vocabulary(bundle, fresh, verdicts)
    if pending:
        # A MISSING VALUE WAITING ON A PROPOSAL IS SAID (1.10.0): the scientist gave a word the list lacks
        out["pending_vocabulary"] = pending
    out.update(verdicts=verdicts, on_disk_drafts_ignored_because_they_differ=stale)
    if not verdicts:
        # an empty verdict list is "nothing checked", never "everything passed"
        out["nothing_validated"] = ("No record draft to validate: no record group is confirmed yet. Confirm the groups "
                                    "(`isaac bundle decide --decision confirm`), then run `isaac bundle build-records`.")
    return out


def _was_marked(bundle: Mapping) -> bool:
    """True when ``build-records --test-marker`` set the self-test state in bundle.json."""
    return bool((bundle.get("self_test") or {}).get("test_marker"))


# --- export ----------------------------------------------------------------------------------------


#: The export's own bookkeeping, in a SUBFOLDER of ``--out`` so nothing that reads ``--out/*.json`` as the
#: records (``upload_plan``, the self-test, a scientist's own script) ever mistakes it for one.
EXPORT_STATE_DIR = "isaac-export"
#: In ``--out``: which record id each exported group's record got, keyed by bundle and group, with the
#: hash of what it was composed from. Not a record.
EXPORT_INDEX = f"{EXPORT_STATE_DIR}/index.json"
EXPORT_INDEX_FORMAT = "isaac.local-export-index"
#: In ``--out``: where a record a re-export REPLACED is moved (never deleted; never in an upload plan).
SUPERSEDED_DIR = f"{EXPORT_STATE_DIR}/superseded"
#: In ``--out``: where a record is moved when its group, exported before, is NOT exportable now (refused by
#: a gate, or no longer a scientist-confirmed group): nothing replaces it, so it is WITHDRAWN, not
#: superseded. Kept (never deleted), never in an upload plan. A later export of the same record body restores
#: it under its id at the top level (and its copy here is then removed: the record is back at the top).
WITHDRAWN_DIR = f"{EXPORT_STATE_DIR}/withdrawn"


def content_sha256(draft: Mapping, composition: Mapping | None) -> str:
    """What a record is composed FROM — the draft and the composer's own overrides — hashed. The
    record id and the export time are not part of it, so an unchanged group hashes the same."""
    basis = {"draft": draft, "record_overrides": dict((composition or {}).get("record_overrides") or {})}
    return "sha256:" + hashlib.sha256(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


#: The record id and export time :func:`body_sha256` composes its probe record with (never written anywhere).
SUBSTANCE_PROBE_ID, SUBSTANCE_PROBE_AT = "SUBSTANCE-PROBE", "1970-01-01T00:00:00Z"


def body_sha256(record: Mapping, artifacts: Sequence[Sequence[Any]], *, exported_utc: Any = None) -> str:
    """What decides a record's id (H1, c15c review MED): the record BODY the portal stores, without its own record id
    and export time, plus its artifacts' bytes (upload sends none; kept as a cautious extra), hashed. The evidence
    sidecar is not part of it: the same value recorded again, by another operator or citing another source file,
    composes the same body, so the record keeps its id and only its sidecar is rewritten (``evidence_changed``).
    A body that differs gets a new id. ``exported_utc``: the time the record was composed with (default: the probe's).

    ``descriptors.outputs[].generated_utc`` IS part of the body: the pinned schema requires it, and the composer
    writes the processing approval's time there (:func:`compose_group`). A processing result approved again with the
    same curves therefore composes another body, and gets a new id; this is left as it is."""
    body = dict(record)
    body.pop("record_id", None)
    stamps = dict(body.get("timestamps") or {})
    if stamps.get("created_utc") == (exported_utc or SUBSTANCE_PROBE_AT):
        stamps["created_utc"] = None  # the export time transform() defaulted it to, not a value of the record
    body["timestamps"] = stamps
    basis = {"record": body, "artifacts": sorted([str(a[0]), str(a[1])] for a in artifacts)}
    return "sha256:" + hashlib.sha256(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _earlier_files(out: Path, rid: Any) -> Path | None:
    """Where an earlier export's ``<rid>.json`` is now: the top of ``--out``, or :data:`WITHDRAWN_DIR`; or ``None``."""
    for where in (out, out / WITHDRAWN_DIR):
        if (where / f"{rid}.json").is_file():
            return where
    return None


def _body_on_disk(out: Path, earlier: Mapping) -> str | None:
    """:func:`body_sha256` of the files an earlier export wrote for ``earlier`` (an index entry from a build that did
    not keep it), read where they are now; ``None`` when they cannot be read."""
    rid = earlier.get("record_id")
    where = _earlier_files(out, rid)
    if where is None:
        return None
    try:
        record = json.loads((where / f"{rid}.json").read_text(encoding="utf-8"))
        base = where / f"{rid}.artifacts"
        artifacts = ([(p.relative_to(base).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
                      for p in sorted(base.rglob("*")) if p.is_file() and not p.is_symlink()]
                     if base.is_dir() and not base.is_symlink() else [])
    except (OSError, ValueError):
        return None
    if not (isinstance(record, dict) and record.get("record_id") == rid):
        return None
    return body_sha256(record, artifacts, exported_utc=earlier.get("exported_utc"))


#: An evidence entry's keys, in plain words, for ``evidence_changed``; any other key is named as it is spelled.
EVIDENCE_KEY_WORDS = {
    "decided_by": "who confirmed it", "identity": "the confirmer's identity", "orcid_claimed": "the confirmer's ORCID",
    "decision_id": "the decision id", "timestamp": "the decision time", "question": "the question asked",
    "answer": "the answer", "source_type": "the kind of source", "source_file": "the source file",
    "source_id": "the source", "locator": "where in the file", "quote": "the quoted text", "relation": "how the source "
    "relates to the value", "provenance": "whether it was confirmed or corrected", "previous_value": "the value it "
    "replaced", "note": "the note", "method": "the reading method",
    "(entries added or removed)": "entries added or removed", "(the value)": "the value",
}
#: How many ``evidence_changed`` lines an export row shows (``evidence_changed_total`` counts them all).
EVIDENCE_CHANGES_SHOWN = 10


def _differing_keys(old: Any, new: Any) -> set[str]:
    """The dict keys, at any depth, whose values differ between ``old`` and ``new`` (a list's entries matched by
    content, the rest compared in order; ``"(entries added or removed)"`` when its length differs)."""
    if old == new:
        return set()
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        out: set[str] = set()
        for k in set(old) | set(new):
            if k not in old or k not in new or not isinstance(old[k], (Mapping, list)):
                if old.get(k) != new.get(k):
                    out.add(str(k))
            else:
                out |= _differing_keys(old[k], new[k]) or ({str(k)} if old[k] != new[k] else set())
        return out
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return {"(entries added or removed)"}
        # entries matched by content first, so a reordered list differs in nothing and only unmatched ones are compared
        unmatched_old, unmatched_new = list(old), []
        for b in new:
            if b in unmatched_old:
                unmatched_old.remove(b)
            else:
                unmatched_new.append(b)
        out = set()
        for a, b in zip(unmatched_old, unmatched_new):
            out |= _differing_keys(a, b)
        return out
    return {"(the value)"}


def evidence_changes(old: Mapping | None, new: Mapping) -> list[str]:
    """``["<evidence key>: <what differs, in plain words>", ...]`` between an earlier sidecar and a new one, for the
    keys whose evidence differs (and its schemas); one line saying so when the earlier one could not be read."""
    if old is None:
        return ["the earlier evidence file could not be read, so it was written anew"]
    lines = []
    old_ev, new_ev = old.get("evidence") or {}, new.get("evidence") or {}
    for key in sorted(set(old_ev) | set(new_ev)):
        if key not in old_ev or key not in new_ev:
            lines.append(f"{key}: {'evidence added' if key not in old_ev else 'evidence removed'}")
        elif (diff := _differing_keys(old_ev[key], new_ev[key])):
            lines.append(f"{key}: " + ", ".join(sorted(EVIDENCE_KEY_WORDS.get(k, k) for k in diff)))
    if old.get("schemas_used") != new.get("schemas_used"):
        lines.append("the schemas used to validate it")
    if old.get("notes") != new.get("notes"):
        lines.append("its notes on what the record is written without")
    return lines


def _read_export_index(out: Path) -> dict:
    path = out / EXPORT_INDEX
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"format": EXPORT_INDEX_FORMAT, "records": []}
    except (OSError, ValueError) as exc:
        raise RecordsRefused(f"{path} cannot be read ({type(exc).__name__}); nothing was exported. It records which record "
                             "id each group was given, so a re-export reuses it: restore it, or export to a new --out.", code=1)
    if not isinstance(data, dict) or data.get("format") != EXPORT_INDEX_FORMAT or not isinstance(data.get("records"), list):
        raise RecordsRefused(f"{path} is not an ISAAC export index; nothing was exported. Export to a new --out.", code=1)
    from isaac_records.ids import is_record_id

    # EVERY record id the index names becomes a FILE NAME in --out (an unchanged re-export rewrites
    # <id>.json, a replaced or withdrawn one is moved): one that is not a record id is refused, whole.
    for r in data["records"]:
        ids = [r.get("record_id"), *(r.get("replaced_record_ids") or ())] if isinstance(r, Mapping) else [None]
        if not isinstance(r, Mapping) or not isinstance(r.get("replaced_record_ids") or [], list) or any(
                not (isinstance(x, str) and is_record_id(x)) for x in ids if x is not None):
            raise RecordsRefused(f"{path} names a record id that is not an ISAAC record id; nothing was exported. "
                                 "Restore the index, or export to a new --out.", code=1)
    return data


def _move_superseded(out: Path, record_id: str, into: str = SUPERSEDED_DIR) -> list[str]:
    """Move a replaced (or, ``into`` :data:`WITHDRAWN_DIR`, a withdrawn) record's files out of ``--out``'s
    top level, so no upload plan lists them. A copy already there under the same name is replaced by
    the newer one (the same record id names the same record)."""
    from isaac_records.ids import is_record_id

    if not is_record_id(record_id):
        return []
    moved = []
    dest = out / into
    for name in (f"{record_id}.json", f"{record_id}.evidence.json", f"{record_id}.artifacts"):
        src = out / name
        if src.exists() and not src.is_symlink():
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / name
            # only ever the SAME record (an id is reused only for the same record body, body_sha256), withdrawn again
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
            shutil.move(str(src), str(target))
            moved.append(f"{into}/{name}")
    return moved


def _artifact_sources(bundle: Mapping, bundle_dir: Path, group_id: str) -> list[tuple[dict, Path | None]]:
    """Each output file of the group's scientist-confirmed processing result, with its file in the bundle, or
    ``None`` when it is outside the bundle, missing, or not the bytes the result recorded (I2)."""
    out = []
    for r in bundle.get("processing_results") or ():
        if r["group_id"] == group_id and r["state"] == B.STATE_SCIENTIST_CONFIRMED:
            for f in (r.get("outputs") or {}).get("files") or ():
                src = contained_file(bundle_dir, f["relative_path"])
                if src is not None and hashlib.sha256(src.read_bytes()).hexdigest() != f.get("sha256"):
                    src = None
                out.append((f, src))
    return out


def _remove_withdrawn_copy(out: Path, record_id: str) -> list[str]:
    """c15c LOW 2: a withdrawn record restored under its id (the same record body) is back at the top of ``--out``:
    its copy in :data:`WITHDRAWN_DIR` is removed, so one id names one set of files. Returns what was removed."""
    from isaac_records.ids import is_record_id

    if not is_record_id(record_id):
        return []
    removed = []
    for name in (f"{record_id}.json", f"{record_id}.evidence.json", f"{record_id}.artifacts"):
        target = out / WITHDRAWN_DIR / name
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()
        else:
            continue
        removed.append(f"{WITHDRAWN_DIR}/{name}")
    return removed


def _withdrawal_statement(record_id: str, exported_utc: Any, moved: Sequence[str], why: str) -> str:
    where = (f"its files were moved to {WITHDRAWN_DIR}/ (kept, never in an upload plan)" if moved
             else "no file of it is at the top of --out (nothing to move)")
    return (f"Record {record_id}, exported for this group on {exported_utc}, is WITHDRAWN: {why}, so it is no longer "
            f"what the bundle composes; {where}. Do not upload it. If it was already uploaded, the portal still holds it.")


def export_records(bundle_dir: Path, out: Path, *, run_portal=None) -> dict:
    """Write ONLY records that pass the portal-target official validation AND whose portal
    outcome is ``publish`` (DEC-76). Every gate is re-run here; a stale validation file is
    never trusted. The record is composed with ``export.transform`` and its sidecar with
    ``export.build_sidecar`` — the truth plane's own functions, unedited.

    RE-EXPORT IS IDEMPOTENT: ``--out``'s :data:`EXPORT_INDEX` keeps, per bundle and group, the record
    id its record got and the :func:`content_sha256` it was composed from. Exporting an UNCHANGED group
    again reuses that id and export time, so the files are rewritten byte for byte and no second record
    appears. A group whose draft changed but whose record body did not (H1: the same value recorded again, by
    another operator or citing another source; :func:`body_sha256`) is unchanged too: the same id and record bytes,
    and its evidence sidecar is rewritten when its bytes differ (``evidence_refreshed``, ``evidence_changed`` saying
    what). A group whose record body CHANGED gets a new id; the record it replaces is moved to ``superseded/`` (kept,
    never in an upload plan) and the result says so (``replaced``). A group exported before that is NOT
    exportable now — refused by a gate, or no longer a scientist-confirmed group — has its record moved to
    ``withdrawn/`` (kept, never in an upload plan; nothing replaces it), its index entry marked
    ``withdrawn_utc``, and the result lists it under ``withdrawn`` (and on its ``refused`` row). Exporting
    the same record body again later restores it under the same id, and its withdrawn copy is removed."""
    from isaac_records.export import build_sidecar
    from isaac_records.ids import new_record_id
    from isaac_records.official import validate_official

    from . import portal as P
    from .cli import _atomic_write

    run_portal = run_portal or P.run_portal_check
    bundle_dir, out = Path(bundle_dir), Path(out)
    bundle = load_validated(bundle_dir)
    label_of = group_labels(bundle)  # r7 J6: each row names its first member file
    exported, refused = [], []
    said_each_record: list[list[str]] = []
    portal_warned: dict[str, list[dict]] = {}
    index = _read_export_index(out) if out.is_dir() else {"format": EXPORT_INDEX_FORMAT, "records": []}
    bundle_id = bundle.get("bundle_id")
    prior_of = {(r.get("bundle_id"), r.get("group_id")): r for r in index["records"] if isinstance(r, Mapping)}
    fresh = fresh_compositions(bundle_dir, bundle, test_marker=_was_marked(bundle))
    confirmed = {gid for gid, _, _ in fresh}
    # FOLLOWS LINKS (labels.py): a link names its target's record id, so the record a group follows is exported
    # first, and the link is resolved to the id that export gave it (or keeps). The id is part of the later record's
    # body: when the earlier record gets a new id, so does the later one.
    key_of_run = {r["run_id"]: r["run_key"] for r in bundle.get("runs") or ()}
    run_group = {key_of_run[rid]: gid for gid, _, comp in fresh for rid in comp.get("member_run_ids") or ()
                 if rid in key_of_run}
    fresh = L.order_by_follows(fresh, run_group)
    drafts_by_gid = {gid: d for gid, d, _ in fresh}
    minted: dict[str, str] = {}
    withdrawn: list[dict] = []
    # c11-a: a record written while a warning still applies says so on its row ("Written without …"), never silent
    warned = with_question_commands(bundle, [w for _, _, comp in fresh for w in comp.get("warnings") or ()])

    def withdraw(earlier: dict, why: str) -> dict:
        """Move an earlier export's record to WITHDRAWN_DIR and mark its index entry; the row's keys."""
        from .mutations import now_utc

        rid = earlier["record_id"]
        moved = _move_superseded(out, rid, WITHDRAWN_DIR) if out.is_dir() else []
        if not earlier.get("withdrawn_utc") or moved:
            earlier["withdrawn_utc"] = now_utc()
            earlier["withdrawn_reason"] = why
            (out / EXPORT_STATE_DIR).mkdir(parents=True, exist_ok=True)
            _atomic_write(out / EXPORT_INDEX, (json.dumps(index, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        info = {"previously_exported_record_id": rid, "withdrawn": True, "withdrawn_record_id": rid, "withdrawn_files": moved,
                "previously_exported_statement": _withdrawal_statement(rid, earlier.get("exported_utc"), moved, why)}
        withdrawn.append({"group_id": earlier.get("group_id"), "record_id": rid, "withdrawn_files": moved, "reason": why})
        return info
    stale = [gid for gid, d, c in fresh if _on_disk_differs(bundle_dir, gid, d, c)]
    orphans = sorted(
        p.name[: -len(".draft.json")] for p in (bundle_dir / DRAFTS_DIR).glob("*.draft.json")
        if p.name[: -len(".draft.json")] not in confirmed
    ) if (bundle_dir / DRAFTS_DIR).is_dir() else []
    for group_id, draft, composition in fresh:
        link, link_evidence, link_left_out = L.follows_link(group_id, draft, composition, run_group=run_group,
                                                            drafts=drafts_by_gid, minted=minted)
        if link is not None:
            draft = L.with_link(draft, link, link_evidence)
        report = validate_draft_file(draft, run_portal=run_portal, composition=composition)
        if report["verdict"] != "exportable":
            row = {"group_id": group_id, **_label(label_of, group_id), "verdict": report["verdict"],
                   "summary": report["plain_summary"],
                   "missing_required": report["missing_required"], "processing_blocker": report["processing_blocker"]}
            earlier = prior_of.get((bundle_id, group_id))
            if earlier is not None and earlier.get("record_id"):
                # WITHDRAWN, never left in place: the record an earlier export wrote for this group is moved
                # out of --out's top level, so `upload --dry-run` no longer lists it, and the row says so
                row.update(withdraw(earlier, f"this export refused the group ({report['verdict']})"))
            refused.append(row)
            continue
        where = P.locate()
        from .mutations import now_utc

        digest = content_sha256(draft, composition)
        prior = prior_of.get((bundle_id, group_id))
        sources = _artifact_sources(bundle, bundle_dir, group_id)
        probe = compose_record(draft, composition, record_id=SUBSTANCE_PROBE_ID, now=SUBSTANCE_PROBE_AT)
        body = body_sha256(probe, [(f["relative_path"], f["sha256"]) for f, src in sources if src is not None])
        # H1: the id follows the record BODY. The draft may change while the body does not (the same value recorded
        # again, by anyone, citing any source): the same record id, and only its evidence sidecar may be rewritten.
        # c15c LOW 1: the body is compared even when the draft is the same, since a newer build may compose another
        # body from it; only an index entry from a build that kept no body hash falls back to the draft hash (and,
        # when that differs, to the record it wrote)
        same_body = False
        if prior is not None and prior.get("record_id"):
            if prior.get("body_sha256"):
                same_body = prior["body_sha256"] == body
            else:
                same_body = prior.get("content_sha256") == digest or (
                    (_body_on_disk(out, prior) if out.is_dir() else None) == body)
        if same_body:
            rid, at, status = prior["record_id"], prior.get("exported_utc") or now_utc(), "unchanged"
        else:
            rid, at, status = new_record_id(), now_utc(), ("replaced" if prior is not None else "new")
        record = compose_record(draft, composition, record_id=rid, now=at)
        if not validate_official(record, Path(where["dir"])).ok:  # the minted record, re-checked
            refused.append({"group_id": group_id, "verdict": "invalid_official", "summary": ["the minted record failed re-validation"]})
            continue
        sidecar = build_sidecar(dict(draft), record)
        sidecar["schemas_used"] = report["schemas_used"]
        left_out = [w["text"] for w in warned if w["group_id"] == group_id
                    and w.get("code") in (START_TIME_WARNING, IN_SITU_WARNING)]
        if link_left_out:
            left_out.append(L.NOT_WRITTEN_FOLLOWS.format(why=link_left_out))
        if left_out:
            # c16d: what the record is written WITHOUT, said in its evidence file in plain words (never silently);
            # r7 J5: an in-situ record's missing conditions too, so `upload --dry-run` lists them
            sidecar["notes"] = left_out
        # when the sidecar was written: the record's export time, kept while its evidence is unchanged (so an
        # unchanged re-export is byte for byte), and now when the evidence file is rewritten (c15c LOW 1)
        sidecar["generated_utc"] = (prior.get("sidecar_generated_utc") or at) if status == "unchanged" else at
        changed_evidence: list[str] = []
        if status == "unchanged":
            # c15c LOW 2: "refreshed" only when the evidence file's bytes differ from the one written before
            earlier_dir = _earlier_files(out, rid) if out.is_dir() else None
            try:
                earlier_bytes = (earlier_dir / f"{rid}.evidence.json").read_bytes() if earlier_dir is not None else None
            except OSError:
                earlier_bytes = None
            if earlier_bytes is None and prior.get("content_sha256") == digest:
                pass  # nothing to compare with, and nothing changed: written as before
            elif earlier_bytes != (json.dumps(sidecar, indent=2) + "\n").encode("utf-8"):
                try:
                    earlier_sidecar = json.loads(earlier_bytes) if earlier_bytes is not None else None
                except ValueError:
                    earlier_sidecar = None
                changed_evidence = evidence_changes(earlier_sidecar if isinstance(earlier_sidecar, Mapping) else None,
                                                    sidecar) or ["the evidence file differed only in its layout or time"]
                sidecar["generated_utc"] = now_utc()
        out.mkdir(parents=True, exist_ok=True)
        moved = _move_superseded(out, prior["record_id"]) if status == "replaced" and prior.get("record_id") else []
        record_path, sidecar_path = out / f"{rid}.json", out / f"{rid}.evidence.json"
        _atomic_write(record_path, (json.dumps(record, indent=2) + "\n").encode("utf-8"))
        _atomic_write(sidecar_path, (json.dumps(sidecar, indent=2) + "\n").encode("utf-8"))
        artifacts = []
        for f, src in sources:
            if src is None:
                artifacts.append({"relative_path": f.get("relative_path"), "refused": "outside the bundle, missing, or sha256 mismatch"})
                continue
            base = (out / f"{rid}.artifacts").resolve()
            dest = (base / f["relative_path"]).resolve()
            try:
                dest.relative_to(base)
            except ValueError:
                artifacts.append({"relative_path": f.get("relative_path"), "refused": "would land outside --out"})
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            artifacts.append(f["relative_path"])
        row = {"group_id": group_id, **_label(label_of, group_id), "record_id": rid, "record": record_path.name,
               "sidecar": sidecar_path.name,
               "artifacts": artifacts, "schemas_used": report["schemas_used"], "export": status,
               "statement": "Valid for the portal's pinned schema; NOT claimed valid for the website."}
        still = [written_without(w) for w in sorted((w for w in warned if w["group_id"] == group_id),
                                                    key=lambda w: warning_rank(w.get("code")))]
        if link_left_out:
            still.append(L.NOT_WRITTEN_FOLLOWS.format(why=link_left_out))
        if link is not None:
            row["follows"] = {"target": link["target"], "basis": link["basis"]}
        said_each_record.append(list(still))  # r5f L3: grouped by text for the summary below (rows keep their own)
        if pw := portal_warnings_of(report):
            # r4-b M7: a record the portal validator warns about says so on its row
            portal_warned[group_id] = pw
            still += [f"Written with a portal validator warning ({w['code']}): {w['message']}" for w in pw]
        if still:
            # c11-r: capped like every other list (count + the first few); `validate --full` lists every one
            row["warnings"] = still[:WARNINGS_SHOWN]
            row["warnings_total"] = len(still)
            if len(still) > WARNINGS_SHOWN:
                row["warnings_omitted"] = len(still) - WARNINGS_SHOWN
                row["warnings_full_list"] = "`isaac bundle validate <bundle_dir> --full` lists every warning."
        if changed_evidence:
            row["evidence_refreshed"] = True
            row["evidence_changed"] = changed_evidence[:EVIDENCE_CHANGES_SHOWN]
            row["evidence_changed_total"] = len(changed_evidence)
            shown = "; ".join(changed_evidence[:3]) + (f"; and {len(changed_evidence) - 3} more (evidence_changed)"
                                                       if len(changed_evidence) > 3 else "")
            row["export_statement"] = (f"Unchanged since its export at {at}: the same record id, the record rewritten byte "
                                       f"for byte. The evidence file was rewritten: {shown}. No record value changed, "
                                       "and no second record was made.")
        elif status == "unchanged":
            row["export_statement"] = (f"Unchanged since its export at {at}: the same record id, rewritten byte for byte. "
                                       "No second record was made.")
        if status == "unchanged":
            if prior.get("withdrawn_utc"):
                row["restored_from_withdrawn"] = True
                row["export_statement"] += (f" It had been withdrawn ({prior['withdrawn_utc']}); the group is exportable "
                                            "again with the same record body, so the record is back at the top of "
                                            f"--out, and its copy in {WITHDRAWN_DIR}/ was removed.")
                row["withdrawn_copy_removed"] = _remove_withdrawn_copy(out, rid)
        elif status == "replaced":
            row["replaces_record_id"] = prior.get("record_id")
            row["superseded_files"] = moved
            row["export_statement"] = (f"The group changed since record {prior.get('record_id')} was exported, so this is a "
                                       f"new record; the old one was moved to {SUPERSEDED_DIR}/ (kept, never in an upload "
                                       "plan). If the old record was already uploaded, the portal still holds it.")
        exported.append(row)
        minted[group_id] = rid
        entry = {"bundle_id": bundle_id, "group_id": group_id, **_label(label_of, group_id), "record_id": rid,
                 "content_sha256": digest,
                 "body_sha256": body, "exported_utc": at, "sidecar_generated_utc": sidecar["generated_utc"],
                 "replaced_record_ids": ([*(prior.get("replaced_record_ids") or []), prior.get("record_id")]
                                         if status == "replaced" else list((prior or {}).get("replaced_record_ids") or [])),
                 # r5f L3: what the portal validator warned about this record, kept so the dry run can say it once
                 **({"portal_warnings": [{"code": w["code"], "path": w["path"], "message": w["message"]} for w in pw]}
                    if (pw := portal_warnings_of(report)) else {})}
        index["records"] = [r for r in index["records"]
                            if not (isinstance(r, Mapping) and (r.get("bundle_id"), r.get("group_id")) == (bundle_id, group_id))]
        index["records"].append(entry)
        prior_of[(bundle_id, group_id)] = entry
        (out / EXPORT_STATE_DIR).mkdir(exist_ok=True)
        _atomic_write(out / EXPORT_INDEX, (json.dumps(index, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    # A group exported before that is no longer a scientist-confirmed group at all (rejected, merged,
    # regrouped away) is not composed, so it is not in `refused`: its record is withdrawn just the same.
    for (b_id, g_id), earlier in list(prior_of.items()):
        if b_id == bundle_id and g_id not in confirmed and earlier.get("record_id"):
            withdraw(earlier, "the group is no longer a scientist-confirmed record group of this bundle")
    # r5c C5: a record is WRITTEN by this run only when it is new or replaces an earlier one; an unchanged record
    # (the same id, rewritten byte for byte) is ready, not written. ``records_ready`` counts both.
    written_now = [row for row in exported if row.get("export") != "unchanged"]
    unchanged_rows = [row for row in exported if row.get("export") == "unchanged"]
    result = {
        # SAID PLAINLY FIRST (1.9.x polish): the exit code is 1 whenever any group is refused, even when records
        # were written, so a reader of the exit code alone would take "wrote 3, refused 75" for "nothing exported"
        "outcome": export_outcome(len(exported), len(refused), len(withdrawn), out,
                                  warned=sum(1 for row in written_now if row.get("warnings_total")),
                                  unchanged=len(unchanged_rows),
                                  replaced=sum(1 for row in exported if row.get("export") == "replaced"),
                                  warned_unchanged=sum(1 for row in unchanged_rows if row.get("warnings_total"))),
        "records_ready": len(exported),
        "records_written": len(written_now),
        # r2-a L2: of the ready ones, those whose body is unchanged since their export (the same id, rewritten byte
        # for byte); they are not counted as written
        "records_unchanged": len(unchanged_rows),
        **({"records_written_with_warnings": n} if (n := sum(1 for row in written_now if row.get("warnings_total"))) else {}),
        **({"records_ready_with_warnings": n} if (n := sum(1 for row in exported if row.get("warnings_total"))) else {}),
        "groups_refused": len(refused),
        "exported": exported,
        "refused": refused,
        "withdrawn": withdrawn,
        "on_disk_drafts_ignored_because_they_differ": stale,
        "on_disk_drafts_ignored_with_no_confirmed_group": orphans,
    }
    if (said_once := group_by_text(said_each_record)):
        # r5f L3: the same warning on every record is said once here, with its record count and one example question;
        # each row of `exported` keeps its own `warnings`
        result["warnings_by_text"] = said_once
        result["outcome"] += warnings_outcome_sentence(said_once)
    if portal_warned:
        # r4-b M7: each portal warning once, with how many of the records written carry it
        result["portal_warnings"] = portal_warning_summary(portal_warned)
        result["outcome"] += (" The portal validator warned on the records ready: "
                              + "; ".join(f"{w['code']} ({w['records']} record(s))" for w in result["portal_warnings"])
                              + " (`portal_warnings`).")
    name_partial_groups([r["group_id"] for r in exported], said_each_record, result.get("warnings_by_text") or [],
                        portal_warned, result.get("portal_warnings") or [])
    if not exported:
        # SAID PLAINLY: with nothing written there is nothing for `upload --dry-run` to show
        result["statement"] = (
            (f"Nothing was exported, so there is nothing to dry-run: {out} was not created." if not out.is_dir() else
             f"Nothing was exported by this run; `upload --dry-run` on {out} lists only records an earlier export left there.")
            + " `isaac bundle validate <bundle_dir>` says what each group still needs.")
    return result


def name_partial_groups(group_ids: Sequence[str], said_each_record: Sequence[Sequence[str]], by_text: list[dict],
                        portal_warned: Mapping[str, Sequence[Mapping]], portal_rows: list[dict]) -> None:
    """r6h review LOW 1: a warning on SOME of the ready records (not all) names EVERY one of their groups
    (``group_ids``), in ``warnings_by_text`` and ``portal_warnings`` alike: the default ``export`` reply lists only the
    first few repeated rows, so a count alone would not say which records lack the condition. ``group_ids`` and
    ``said_each_record``: the exported rows' groups and their warning texts, in the same order."""
    n = len(group_ids)
    for row in by_text:
        if row["records"] < n:
            row["group_ids"] = [g for g, texts in zip(group_ids, said_each_record)
                                if row["text"] in {fold_key(t) for t in texts}]
    for row in portal_rows:
        if row["records"] < n:
            row["group_ids"] = [g for g, ws in portal_warned.items()
                                if any((w["code"], w["message"]) == (row["code"], row["message"]) for w in ws)]


def export_outcome(written: int, refused: int, withdrawn: int, out: Path, *, warned: int = 0, unchanged: int = 0,
                   replaced: int = 0, warned_unchanged: int = 0) -> str:
    """One sentence: what ``export`` wrote and refused, and what its exit code means for that (and, c11-a, how many
    records were written with a warning that still applies: each row's ``warnings`` says what it lacks). ``written``
    counts every record READY in ``--out`` from this run (the reply's ``records_ready``); r2-a L2: of them
    ``unchanged`` are the same record as at their export (same id, rewritten byte for byte) and ``replaced`` replace an
    earlier record, so the sentence never says "wrote 7" when nothing new was written. r5c C5: ``warned`` counts only
    the records NEWLY written with a warning; ``warned_unchanged`` the unchanged ones that still carry one."""
    fresh = written - unchanged
    counts = (f" ({unchanged} unchanged since their export, {fresh} written"
              + (f", {replaced} of them replacing an earlier record" if replaced else "") + ")") if written else ""
    text = f"{written} record(s) ready{counts}, refused {refused} group(s)."
    if written and refused:
        text += (f" The exit code is 1 because some groups were refused; the {written} record(s) ready are valid "
                 f"for the portal's pinned schema and are in {out}.")
    elif refused:
        text += " Nothing was written (exit 1)."
    elif written:
        text += " Every confirmed group was exported (exit 0)."
    if warned:
        text += (f" {warned} record(s) were written with a warning that still applies: each says what the record is "
                 "written without (`exported[].warnings`).")
    if warned_unchanged:
        text += (f" {warned_unchanged} unchanged record(s) still carry a warning that applies "
                 "(`exported[].warnings`).")
    if withdrawn:
        text += f" {withdrawn} earlier record(s) were withdrawn (see `withdrawn`)."
    return text


# --- upload (dry run only) -------------------------------------------------------------------------


def upload_plan(records_dir: Path, portal_url: str | None) -> list[dict]:
    """Exactly what an upload WOULD send. Reads record files; opens no socket and never
    reads the token (the Authorization header names where it would come from)."""
    base = (portal_url or "<portal-url>").rstrip("/")
    replaces = _replaced_by(Path(records_dir))
    labels = _labels_in_index(Path(records_dir))
    plan = []
    paths = [p for p in sorted(Path(records_dir).glob("*.json")) if not p.name.endswith(".evidence.json")]
    for path in L.order_records_by_links(paths, _link_targets(paths)):
        body = path.read_bytes()
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer <from $ISAAC_PORTAL_TOKEN, not read>",
        }
        meta = {"body_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest()}
        plan.append(
            {
                "record": path.name,
                # r7 J6: which sample or file the record is of, as the export index names it (first member file)
                **_label(labels, path.name[: -len(".json")]),
                "requests": [
                    {"method": "POST", "url": base + PORTAL_VALIDATE, "headers": headers, **meta},
                    {"method": "POST", "url": base + PORTAL_RECORDS, "headers": headers, **meta,
                     "only_if": "the validate response is valid with outcome publish"},
                ],
            }
        )
        notes = _sidecar_notes(path.with_name(path.name[: -len(".json")] + ".evidence.json"))
        if notes:
            # c16d: what the record is written WITHOUT (its evidence file's notes), said before an upload too
            plan[-1]["notes"] = notes
        if old := replaces.get(path.name[: -len(".json")]):
            # H1: SAID BEFORE AN UPLOAD, never only in the export's output: a replaced record already uploaded stays
            # on the portal, so uploading this one adds a second record for the same group
            plan[-1]["replaces_record_ids"] = old
            many = len(old) > 1
            plan[-1]["replaces_statement"] = (
                f"This record replaces {'earlier exports' if many else 'an earlier export'} of the same group: "
                + "; ".join(f"{x} ({_where_now(Path(records_dir), x)})" for x in old)
                + f". If {'any of them was' if many else 'it was'} already uploaded, the portal still holds it, and "
                "uploading this one adds a second record for the same group.")
    return plan


def _link_targets(paths: Sequence[Path]) -> dict[str, list[str]]:
    """``{record id: [the record ids its links name]}``, read from the record files (an unreadable one names none)."""
    out: dict[str, list[str]] = {}
    for path in paths:
        try:
            record = json.loads(path.read_bytes())
        except (OSError, ValueError):
            continue
        links = record.get("links") if isinstance(record, Mapping) else None
        targets = [x["target"] for x in links or () if isinstance(x, Mapping) and isinstance(x.get("target"), str)] \
            if isinstance(links, list) else []
        if targets:
            out[path.name[: -len(".json")]] = targets
    return out


def upload_summary(plan: Sequence[Mapping], records_dir: Path, portal_url: str | None) -> dict:
    """r5f L3: what the dry run says ONCE about every record in ``plan``: ``{statement, notes_by_text,
    portal_warnings}``. The statement leads with how many records, how many requests each and where to
    (``74 records, 2 requests each, to <portal>``), says that nothing was sent, then each distinct note (the
    start-time note, which differs between records only in its question id) once, with its record count and one
    example question, and each portal warning once. A record's own ``notes`` stay in ``plan``. Reads files only."""
    base = (portal_url or "<portal-url>").rstrip("/")
    n = len(plan)
    per_request = {len(p.get("requests") or ()) for p in plan}
    each = f"{next(iter(per_request))} request{'' if per_request == {1} else 's'} each" if len(per_request) == 1 else None
    lead = f"{n} record{'' if n == 1 else 's'}" + (f", {each}" if each else "") + f", to {base}."
    notes = group_by_text(p.get("notes") or () for p in plan)
    ids = {Path(p["record"]).stem for p in plan}
    portal = _portal_warnings_in_index(Path(records_dir), ids)
    statement = lead + " Nothing was sent. The token is never read or printed."
    if notes:
        statement += " What these records are written without, each said once: " + grouped_sentence(notes) + " (records[].notes)."
    if portal:
        statement += (" The portal validator warned, each said once: "
                      + "; ".join(f"{w['code']}" + (f" at {w['path']}" if w.get("path") else "") + f": {w['message']} ({w['records']} record(s))"
                                  for w in portal) + " (portal_warnings).")
    return {"statement": statement, "notes_by_text": notes, **({"portal_warnings": portal} if portal else {})}


def _portal_warnings_in_index(records_dir: Path, record_ids: set[str]) -> list[dict]:
    """The portal validator's warnings the export recorded for ``record_ids`` (:data:`EXPORT_INDEX`), each distinct one
    once with how many of those records carry it; ``[]`` when the index is missing or says none."""
    try:
        index = json.loads((records_dir / EXPORT_INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    seen: dict[tuple, dict] = {}
    for r in (index.get("records") if isinstance(index, Mapping) else None) or ():
        if not (isinstance(r, Mapping) and r.get("record_id") in record_ids and isinstance(r.get("portal_warnings"), list)):
            continue
        for w in r["portal_warnings"]:
            if isinstance(w, Mapping):
                row = seen.setdefault((w.get("code"), w.get("path"), w.get("message")),
                                      {"code": w.get("code"), "path": w.get("path"), "message": w.get("message"), "records": set()})
                row["records"].add(r["record_id"])
    return [{**r, "records": len(r["records"])} for r in sorted(seen.values(), key=lambda r: (-len(r["records"]), str(r["code"])))]


def group_labels(bundle: Mapping) -> dict[str, str]:
    """r7 J6: ``{group_id: label}``: a short name a scientist knows each group by, its first member file (a run's
    stem; a run kept as context only when the group has no other). Said on export and dry-run rows."""
    runs = {r["run_key"]: r for r in bundle.get("runs") or ()}
    context = B.context_run_ids(bundle)
    out: dict[str, str] = {}
    for g in bundle.get("record_groups") or ():
        members = [runs[k] for k in g.get("member_run_keys") or () if k in runs]
        first = next((r for r in members if r["run_id"] not in context), members[0] if members else None)
        if first is not None:
            out[g["group_id"]] = str(first.get("stem") or first["run_id"])
    return out


def _label(labels: Mapping[str, str], key: str) -> dict:
    """``{"label": ...}`` for a row, or ``{}`` when none is known."""
    return {"label": labels[key]} if labels.get(key) else {}


def _labels_in_index(records_dir: Path) -> dict[str, str]:
    """r7 J6: ``{record_id: label}`` from ``records_dir``'s :data:`EXPORT_INDEX` (``{}`` when it has none)."""
    try:
        index = json.loads((records_dir / EXPORT_INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = index.get("records") if isinstance(index, Mapping) else None
    return {r["record_id"]: r["label"] for r in rows or () if isinstance(r, Mapping)
            and isinstance(r.get("record_id"), str) and isinstance(r.get("label"), str)}


def _sidecar_notes(path: Path) -> list[str]:
    """The ``notes`` an evidence sidecar carries (what its record is written without), or ``[]``."""
    try:
        notes = json.loads(path.read_text(encoding="utf-8")).get("notes")
    except (OSError, ValueError, AttributeError):
        return []
    return [n for n in notes if isinstance(n, str)] if isinstance(notes, list) else []


def _where_now(records_dir: Path, record_id: str) -> str:
    """Where a replaced record's file is now, in ``records_dir``: :data:`SUPERSEDED_DIR`, :data:`WITHDRAWN_DIR`, or
    neither."""
    for where in (SUPERSEDED_DIR, WITHDRAWN_DIR):
        if (records_dir / where / f"{record_id}.json").is_file():
            return f"in {where}/"
    return f"no longer in {SUPERSEDED_DIR}/ or {WITHDRAWN_DIR}/"


def _replaced_by(records_dir: Path) -> dict[str, list[str]]:
    """``record id -> the record ids it replaced``, from ``records_dir``'s :data:`EXPORT_INDEX`; ``{}`` when there is
    none or it cannot be read (the dry run lists the records all the same)."""
    try:
        index = json.loads((records_dir / EXPORT_INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = index.get("records") if isinstance(index, Mapping) else None
    return {r["record_id"]: [x for x in r["replaced_record_ids"] if isinstance(x, str)]
            for r in rows or () if isinstance(r, Mapping) and isinstance(r.get("record_id"), str)
            and isinstance(r.get("replaced_record_ids"), list) and r["replaced_record_ids"]}
