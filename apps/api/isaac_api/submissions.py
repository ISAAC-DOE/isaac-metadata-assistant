"""The SUBMISSION domain: pure functions over export units. No I/O, no database.

WHAT LIVES HERE AND WHAT DOES NOT
=================================
This module answers four questions about a set of :class:`~isaac_api.workspace.
ExportUnit` objects, and nothing else:

  * :func:`content_signature` — what is the stable identity of this content?
  * :func:`conflict_summary` — which fields carry conflicting evidence?
  * :func:`field_values` / :func:`address_changes` — what changed since last time?
  * :func:`blocker_report` — why is this not submittable?

Every one of them is a pure function of its arguments. Nothing here opens a
connection, reads the filesystem, reads the environment, mints an id, or reads a
clock — the write path (:mod:`isaac_api.submission_store`) does all of that, and
keeping the split sharp is what makes these four testable without a database and
without a fixture workspace.

**It computes no verdict the truth core does not already produce.**
:func:`blocker_report` calls ``exp.pending_count()`` and
``isaac_records.export.export_draft`` — the same two checks the export route
already gates on — and reshapes their answers. It adds no rule of its own, and it
must never grow one: a submission is refused for exactly the reasons an export is
refused, and inventing a fifth reason here would create a state a scientist could
not resolve through any surface this application offers.

THE ONE DECISION IN THIS MODULE THAT IS NOT MECHANICAL
======================================================
``conflicting_evidence`` is **recorded and disclosed, never gated on**, and the
reason is measured rather than stylistic. ``evidence_classify._classify_entry``
rule 1 flags a field the moment two distinct non-null answers are recorded for it.
``routes._apply_run_field`` **appends** a ``user_confirmation`` entry every time and
never replaces one, and no route in this application removes an evidence entry. So
a scientist who answers a question, notices a typo, and answers it again has
manufactured a conflict **they cannot clear through any surface this build offers**.
Gating submission on it would be a permanent block produced by correcting a
mistake. :func:`conflict_summary` therefore reports it, the submission row stores
it, and the response discloses it — and none of that stops the submission.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from isaac_records.export import export_draft

from . import evidence_classify
from . import serialize
from .workspace import REPO_ROOT

__all__ = [
    "CHANGE_ADDED",
    "CHANGE_KINDS",
    "CHANGE_MODIFIED",
    "CHANGE_REMOVED",
    "CONFLICT_SCOPE",
    "SIGNATURE_SCOPE",
    "TRUST_BASIS_UNATTRIBUTED",
    "UnitBlocker",
    "address_changes",
    "address_value_changes",
    "blocker_report",
    "canonical_json",
    "conflict_summary",
    "content_signature",
    "field_values",
    "present_field_values",
    "unit_membership_changes",
    "unit_payloads",
    "units_by_id",
]


#: The trust basis recorded when NOBODY was established for a write.
#:
#: **Deliberately defined here and NOT added to
#: :data:`isaac_api.identity.RECOGNISED_TRUST_BASES`.** That set is the set of bases
#: a :class:`~isaac_api.identity.HumanActor` may CLAIM, and "nobody" is not a
#: person: widening it would make ``HumanActor(subject="x",
#: trust_basis="unattributed")`` constructible, which is precisely the shape —
#: a name nothing vouched for — that the whole identity seam exists to refuse.
#:
#: The database CHECK admits three values (this one plus the two recognised bases)
#: and pairs it with ``(trust_basis = 'unattributed') = (subject IS NULL)``, so an
#: unattributed row can never carry a name and a named row can never claim this
#: basis.
TRUST_BASIS_UNATTRIBUTED = "unattributed"

#: What :func:`content_signature` covers, echoed into the API response so a reader
#: never has to infer the scope of a digest from its name.
SIGNATURE_SCOPE = "export_unit_ids_and_drafts"

#: What :func:`conflict_summary` looked at. Same reason.
CONFLICT_SCOPE = "draft_field_evidence"

CHANGE_ADDED = "added"
CHANGE_REMOVED = "removed"
CHANGE_MODIFIED = "modified"

#: Exactly the three values ``isaac_revision_changes.change_kind`` admits. Named
#: here so the Python and the SQL cannot drift; a test asserts the migration's CHECK
#: lists these three and no others.
CHANGE_KINDS: tuple[str, ...] = (CHANGE_ADDED, CHANGE_REMOVED, CHANGE_MODIFIED)


def canonical_json(value: Any) -> str:
    """One deterministic text form for any JSON value.

    ``sort_keys`` so key order cannot change a digest, ``separators`` with no
    whitespace so indentation cannot either, and ``ensure_ascii=False`` so a
    non-ASCII character has ONE encoding rather than two that hash differently
    depending on which writer produced the document.

    NO ``default=`` HANDLER, DELIBERATELY. Every draft in this application has
    round-tripped through JSON on the way out of the workspace file or the database,
    so a non-serialisable value is unreachable; adding a stringifying fallback would
    make two genuinely different objects hash identically in exchange for tolerating
    a state that cannot occur. If one ever does occur, a ``TypeError`` naming it is
    a better outcome than a signature that quietly means less than it says.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def unit_payloads(units: Sequence[Any]) -> list[dict]:
    """The signature-relevant projection of each export unit, ordered by unit id.

    ``unit_id`` is ``ExportUnit.target_id`` — a run's id for an experiment with
    runs, the experiment's own id for one without — and ``draft`` is the FULLY
    RESOLVED draft that unit would export, inheritance and overrides already
    applied. Those two are the whole of what becomes an official ISAAC record, which
    is why they are the whole of what the signature covers.

    Sorted by ``unit_id`` rather than left in ``sorted_runs()`` order on purpose:
    ``sorted_runs`` orders on ``(ordinal, created_utc, id)``, so REORDERING two runs
    changes that sequence without changing a single record. A signature that moved
    on a reorder would refuse a re-submission of content that is byte-identical
    record for record.
    """
    return sorted(
        (
            {
                "unit_id": unit.target_id,
                "run_id": unit.run_id,
                "draft": unit.draft,
            }
            for unit in units
        ),
        key=lambda payload: payload["unit_id"],
    )


def content_signature(experiment_id: str, units: Sequence[Any]) -> str:
    """The stable sha256 identity of what a submission would publish.

    WHAT IT COVERS: the experiment id, and each export unit's id and fully resolved
    draft. Nothing else.

    WHAT IT DELIBERATELY EXCLUDES, AND WHY EACH EXCLUSION IS LOAD-BEARING:

    * ``rev``, ``updated_utc``, ``generation`` — they move on every save, including
      saves that change no record. A signature carrying them would differ between
      two submissions of identical science.
    * ``record_id`` — it is ``None`` before materialisation and set after it, on the
      very same content. Including it would mean the signature computed BEFORE the
      artifacts are written differs from the one computed AFTER, so a retry after a
      partial failure would look like new content and would write a second
      submission for one act. **Stability across materialisation is the property
      this exclusion exists to provide**, and it is what makes the signature usable
      as the natural idempotency key.

      *M4 — ONE DEGRADED CASE IN WHICH IT CAN STILL MOVE, AND IT IS NOT EXCLUDABLE
      HERE.* A unit's composed draft carries sibling ``links``, and
      ``workspace._linkable`` deliberately returns ``None`` for a MATERIALISED record
      that cannot be read or whose own ``record_id`` disagrees with the file carrying
      it — rather than falling back to the draft, which would restore a fabricated
      link. Such a unit drops out of its sibling group, the links composed into its
      siblings' drafts change, and the signature moves with them. So the claim holds
      **whenever every materialised record is readable and self-consistent**, which
      is every non-degraded case; against a corrupted or hand-edited artifact a retry
      can legitimately compute a different signature and record a second submission.
    * ``title`` — a record's title is workspace metadata and reaches no official
      record. Renaming a record and re-submitting therefore does NOT produce a new
      submission, and that is the honest answer: the content that was published is
      unchanged. Stated here because it is the one exclusion a reader might expect
      to go the other way.

    The digest is over :func:`canonical_json`, so it is stable across Python
    versions, dict insertion order, and whitespace.
    """
    payload = {
        "experiment_id": experiment_id,
        "scope": SIGNATURE_SCOPE,
        "units": unit_payloads(units),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def field_values(draft: Mapping[str, Any] | None) -> dict[str, str]:
    """``address -> canonical JSON of that field's value``, for present values only.

    A field is PRESENT when its envelope carries a non-``None`` ``value``. An
    envelope with ``value: null`` — the shape a ``needs_confirmation`` blocker has —
    is absent here rather than present-and-null, so answering a blocker reads as
    ``added`` and clearing an answer reads as ``removed``, which is what a reader
    means by both words.

    THE SCOPE IS NARROW AND IS THE SAME ONE ``0003_revisions.sql`` WRITES DOWN. Only
    ``draft["fields"]`` is examined. Evidence entries, run overrides, answer logs,
    assets and implicit claims are NOT compared, and neither is anything nested
    inside a value beyond that value's canonical form. So an empty change set means
    "no field value differed", never "nothing changed".
    """
    fields = (draft or {}).get("fields")
    if not isinstance(fields, dict):
        return {}
    out: dict[str, str] = {}
    for address, envelope in fields.items():
        if not isinstance(address, str) or not address:
            continue
        if not isinstance(envelope, dict):
            continue
        value = envelope.get("value")
        if value is None:
            continue
        out[address] = canonical_json(value)
    return out


def address_changes(
    previous: Mapping[str, Mapping[str, Any] | None] | None,
    current: Mapping[str, Mapping[str, Any] | None],
) -> list[tuple[str, str, str]]:
    """``(unit_id, address, change_kind)`` triples, sorted, for two unit->draft maps.

    ``previous`` of ``None`` means there is no comparable predecessor — the first
    revision of an experiment, or one whose stored predecessor could not be read.
    **It yields an EMPTY list, not "everything was added"**, and the difference
    matters: an initial submission did not ADD three hundred fields to anything, and
    a caller must be able to tell "nothing differed" from "there was nothing to
    differ from". The route discloses which of the two happened; this function
    simply does not invent a baseline it was not given.

    A unit present in one map and absent from the other contributes one row per
    field value it holds, so adding a run reads as that run's fields being added.
    """
    if previous is None:
        return []
    out: list[tuple[str, str, str]] = []
    for unit_id in sorted(set(previous) | set(current)):
        was = field_values(previous.get(unit_id))
        now = field_values(current.get(unit_id))
        for address in sorted(set(was) | set(now)):
            if address not in was:
                out.append((unit_id, address, CHANGE_ADDED))
            elif address not in now:
                out.append((unit_id, address, CHANGE_REMOVED))
            elif was[address] != now[address]:
                out.append((unit_id, address, CHANGE_MODIFIED))
    return out


def present_field_values(draft: Mapping[str, Any] | None) -> dict[str, Any]:
    """The SAME addresses :func:`field_values` reports, carrying the RAW values.

    :func:`field_values` returns each value's canonical JSON *text*, which is what a
    change comparison needs and is deliberately all it needs. A surface that shows a
    scientist what a field used to hold needs the value itself, so that it can be
    rendered by the same rules every other value on that surface is rendered by
    (one line for a scalar; "cannot be shown in one line" for an object).

    **IT IS NOT A SECOND DEFINITION OF "PRESENT".** The presence rule is
    :func:`field_values`' rule, restated in one place and pinned in another:
    ``test_revision_history`` asserts, over a matrix of drafts, that
    ``{k: canonical_json(v) for k, v in present_field_values(d).items()}`` equals
    ``field_values(d)`` exactly. If the two ever diverge, that test fails rather
    than a diff quietly disagreeing with the change log stored beside it.
    """
    fields = (draft or {}).get("fields")
    if not isinstance(fields, dict):
        return {}
    out: dict[str, Any] = {}
    for address, envelope in fields.items():
        if not isinstance(address, str) or not address:
            continue
        if not isinstance(envelope, dict):
            continue
        value = envelope.get("value")
        if value is None:
            continue
        out[address] = value
    return out


def address_value_changes(
    previous: Mapping[str, Mapping[str, Any] | None] | None,
    current: Mapping[str, Mapping[str, Any] | None],
) -> list[dict]:
    """:func:`address_changes`, plus the two values — for a surface, not for a row.

    Returns dicts of ``{unit_id, address, change_kind, previous_value,
    current_value}``, in the SAME order and with the SAME membership as
    :func:`address_changes`. That equality is not asserted by construction — the two
    functions are written out separately — it is asserted by test, over a matrix of
    inputs, because a diff shown to a scientist that disagreed with the change rows
    stored in ``isaac_revision_changes`` would be the worse kind of wrong: both
    plausible, and only one of them written down.

    WHY NOT SIMPLY EXTEND :func:`address_changes`. That function is on the
    SUBMISSION WRITE PATH — its output becomes ``isaac_revision_changes`` rows inside
    the one durable transaction — and this slice adds a read surface. Changing the
    shape a write path emits in order to serve a screen is how a read requirement
    ends up embedded in a durable record. So the write path is left exactly as it
    was, and the drift risk that creates is paid for with a test rather than with a
    refactor.

    ``previous`` of ``None`` yields an empty list for the reason
    :func:`address_changes` yields one: **there was nothing to compare against**, and
    that is not the same statement as "nothing changed". Every caller must disclose
    which of the two it is reporting.

    THE VALUES ARE THE DRAFT'S OWN, UNTRANSFORMED. Nothing here rounds, formats,
    truncates, units-converts or summarises a scientific value; a value too large or
    too structured to render is a rendering decision made where the rendering happens.
    """
    if previous is None:
        return []
    out: list[dict] = []
    for unit_id in sorted(set(previous) | set(current)):
        was_text = field_values(previous.get(unit_id))
        now_text = field_values(current.get(unit_id))
        was_raw = present_field_values(previous.get(unit_id))
        now_raw = present_field_values(current.get(unit_id))
        for address in sorted(set(was_text) | set(now_text)):
            if address not in was_text:
                kind = CHANGE_ADDED
            elif address not in now_text:
                kind = CHANGE_REMOVED
            elif was_text[address] != now_text[address]:
                kind = CHANGE_MODIFIED
            else:
                continue
            out.append(
                {
                    "unit_id": unit_id,
                    "address": address,
                    "change_kind": kind,
                    # `None` HERE MEANS "NOT RECORDED AT THAT POINT", and it can only
                    # occur on the side the change kind already says is absent —
                    # `field_values` excludes an envelope whose `value` is null, so a
                    # present value is never `None`. The two facts therefore agree
                    # rather than needing a reader to reconcile them.
                    "previous_value": was_raw.get(address),
                    "current_value": now_raw.get(address),
                }
            )
    return out


def unit_membership_changes(
    previous: Mapping[str, Any] | None, current: Mapping[str, Any]
) -> dict:
    """Which export units this record gained and lost since a stored revision.

    An export unit is a RUN for a record that has them, and the record itself for one
    that does not (``workspace.ExportUnit``), so for the fan-out case this is exactly
    "which runs were added and which were removed".

    IT IS REPORTED SEPARATELY FROM THE FIELD CHANGES RATHER THAN FOLDED INTO THEM.
    :func:`address_changes` already contributes one ``added``/``removed`` row per
    field value a unit holds, so a removed run appears there as forty removed fields
    — which is true, and is not the sentence a reader wants first. "One run was
    removed" and "forty values are no longer recorded" are the same event described
    at two altitudes, and a surface that only had the second would make the reader
    reconstruct the first.

    ``previous`` of ``None`` yields empty lists and ``comparable: false``, for the
    reason :func:`address_changes` yields an empty list: there was no baseline.
    """
    if previous is None:
        return {"comparable": False, "added": [], "removed": [], "unchanged": []}
    was = set(previous)
    now = set(current)
    return {
        "comparable": True,
        "added": sorted(now - was),
        "removed": sorted(was - now),
        "unchanged": sorted(now & was),
    }


def conflict_summary(units: Sequence[Any]) -> dict:
    """Which fields carry conflicting evidence, per unit. RECORDED, NEVER GATING.

    Reuses :func:`isaac_api.evidence_classify.classify_fields`, which is the one
    definition of ``conflicting_evidence`` in this application — recomputing the
    rule here would create a second definition that could disagree with the one the
    Evidence screen shows.

    THE OUTPUT CARRIES ADDRESSES AND COUNTS, NEVER VALUES. The conflicting values
    are in the revision snapshot beside this row; copying them into a disclosure
    column would put scientific content into a field whose job is navigation, and
    would give the same value two places to live.

    ``gating`` is stated IN THE DATA rather than left to documentation, because this
    object is stored and is read back by surfaces that were not written today. A
    reader who finds a non-zero count must be able to see, from the object itself,
    that it did not block anything.
    """
    affected: list[dict] = []
    total = 0
    for unit in units:
        addresses = sorted(
            entry["field"]
            for entry in evidence_classify.classify_fields(unit.draft)
            if entry.get("classification") == "conflicting_evidence"
            and isinstance(entry.get("field"), str)
        )
        if not addresses:
            continue
        total += len(addresses)
        affected.append(
            {
                "unit_id": unit.target_id,
                "run_id": unit.run_id,
                "addresses": addresses,
            }
        )
    return {
        "scope": CONFLICT_SCOPE,
        "gating": "disclosed_not_gated",
        "conflicting_field_count": total,
        "affected_units": affected,
    }


class UnitBlocker(dict):
    """One unit's reason for not being submittable. A plain ``dict`` subclass.

    A ``dict`` rather than a dataclass because it goes straight into a JSON response
    body and a dataclass would need a second serialiser; a NAMED type rather than a
    bare dict so the shape has somewhere to be documented.
    """


def blocker_report(exp: Any, units: Sequence[Any]) -> dict:
    """Why this experiment cannot be submitted, per unit. Writes nothing.

    THE GATE IS EXACTLY EXPORT-READINESS AND NOTHING MORE:

      1. ``exp.pending_count() == 0`` over ALL units — every unanswered blocker, the
         experiment's own and its runs'.
      2. Every unit's ``export_draft`` DRY RUN passes.

    Those are the same two conditions ``Experiment.export_ready()`` composes into a
    boolean; this returns the same answer with the per-unit detail a refusal needs,
    so a scientist is told WHICH run refused rather than only THAT one did.

    **M5 — THE HEADING USED TO READ "EXACTLY THE EXISTING EXPORT GATE", AND THAT
    OVERSTATED IT BY ONE CONDITION.** It is exactly ``Experiment.export_ready()``,
    which is not the same as what ``POST /api/experiments/{id}/export`` enforces:
    that route has no ``pending_count()`` check anywhere and will publish a record
    with unanswered questions. So submission adds no rule beyond export-readiness,
    but it is stricter than the export ROUTE by condition 1. The wording is corrected
    rather than deleted because the claim it makes — "no fifth reason, no Submit
    Anyway" — is the one that matters and is still true.

    ``export_draft`` is called WITHOUT ``record_id``, matching
    ``Experiment._all_units_pass_dry_run`` exactly. Passing the id would
    additionally fail any unit whose id is not a ULID, which would make this
    stricter than the readiness the rest of the application reports — a gate that
    refuses what ``status()`` calls ``ready_to_export`` is a gate nobody can satisfy.

    THERE IS NO OVERRIDE, NO FORCE PARAMETER AND NO "SUBMIT ANYWAY", by contract §3
    D4: a required validation failure on any run blocks the whole submission. This
    function has no argument by which one could be requested.

    NEVER RAISES. ``export_draft`` is a pure transform plus two validations, but a
    malformed persisted draft is a reachable input, and a submission refusal that
    500s tells the reader nothing. A unit whose dry run raises is reported as
    blocked, naming the exception CLASS only — never its message, which can carry a
    filesystem path.
    """
    pending = list(exp.pending())
    unit_blockers: list[UnitBlocker] = []
    for unit in units:
        try:
            result = export_draft(unit.draft, REPO_ROOT)
            ok = bool(result.ok)
            errors = _dry_run_errors(result)
        except Exception as exc:  # noqa: BLE001 - see the docstring
            ok = False
            errors = [f"the export gate could not be evaluated ({type(exc).__name__})"]
        if ok:
            continue
        unit_blockers.append(
            UnitBlocker(
                {
                    "unit_id": unit.target_id,
                    "run_id": unit.run_id,
                    "run_label": unit.run_label,
                    "errors": errors,
                }
            )
        )
    return {
        "pending_count": len(pending),
        "pending": pending,
        "failing_units": unit_blockers,
        "blocked": bool(pending) or bool(unit_blockers),
    }


def _dry_run_errors(result: Any) -> list:
    """The flat error list for one dry run, official errors first. JSON-READY.

    Mirrors ``routes._flat_export_errors``' precedence — official errors when the
    record was built and refused, otherwise the draft errors that stopped it being
    built at all — rather than importing it, because importing from ``routes`` into
    a domain module would make the domain depend on the HTTP layer.

    IT READS THE SERIALISED REPORT, NOT THE RAW ONE, AND THAT IS NOT A DETAIL.
    ``ExportResult.official_report.errors`` holds ``OfficialError`` DATACLASSES, and
    the first version of this function returned them straight into a response body.
    ``json.dumps`` raised ``TypeError: Object of type OfficialError is not JSON
    serializable`` inside Starlette's renderer, so the refusal that exists to
    explain WHY a submission was blocked arrived as a bare HTTP 500 — measured, not
    theorised. ``serialize.export_result_to_dict`` is the one place this project
    turns those reports into JSON, and going through it is what makes the two
    branches of the refusal produce the same shape.
    """
    payload = serialize.export_result_to_dict(result)
    official = payload.get("official_report")
    if official and official.get("errors"):
        return list(official["errors"])
    draft_report = payload.get("draft_report")
    if draft_report is not None and not getattr(result.draft_report, "ok", True):
        return list(draft_report.get("errors") or [])
    return []


def units_by_id(units: Iterable[Any]) -> dict[str, dict]:
    """``unit_id -> resolved draft``, the shape :func:`address_changes` compares."""
    return {unit.target_id: unit.draft for unit in units}
