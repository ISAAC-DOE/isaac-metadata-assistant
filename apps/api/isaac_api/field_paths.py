"""The field-path derivations the write routes enforce — WITHOUT FastAPI.

MOVED HERE VERBATIM FROM ``routes.py`` (2026-10-28, slice LOCAL-1) so the
historical-import engine (``historical_import.read_archive``) can answer "which
official paths does this build have a write route for, and at which scope?"
without importing ``routes`` — a 30,000-line FastAPI module — and therefore
without a web server stack. ``routes`` re-exports every name below as the SAME
object, so ``routes.PROPOSAL_TARGET_PATHS is field_paths.PROPOSAL_TARGET_PATHS``
and every existing reader and test is unchanged. The long commentary on why each
set is shaped as it is still sits beside the re-export in ``routes.py``, where it
was written; the code it describes is here.

NOTHING HERE IS NEW: each expression is the one ``routes`` evaluated, in the same
order, over the same inputs (``extract.structured.FIELD_MAP``, the vendored
schema, ``workspace``'s level split, ``proposals``' writer ids).

This module must never import ``fastapi``, ``starlette``, ``pydantic`` or
``isaac_api.routes``; ``test_local_import_engine.py`` asserts that in a fresh
subprocess.
"""

from __future__ import annotations

import functools
import json
from types import MappingProxyType
from typing import Mapping

from isaac_records.extract.structured import FIELD_MAP as EXTRACTOR_FIELD_MAP
from isaac_records.official import schema_path

from . import proposals
from . import workspace as ws
from .workspace import REPO_ROOT


@functools.lru_cache(maxsize=1)
def _record_enum_fields() -> Mapping[str, tuple]:
    """Record-level official field paths the schema CLOSES with an enum -> its values.

    THE DEFECT THIS EXISTS TO CLOSE, measured over HTTP on a record created through
    ``POST /api/experiments`` with one run, at every write route this application has::

        system.domain     /edit 422  /answers 422  PATCH run 422  run/edit 422
                          run/answers 422          run/overrides 422 not_overridable
        system.technique  /edit 422  /answers 422  PATCH run 422  run/edit 422
                          run/answers 422          run/overrides 200

    Both are declared REQUIRED by ``properties.system.required`` in the vendored
    official schema, and neither could be set ON THE RECORD by any request. The one
    accepting route is a RUN's override — which records a DIVERGENCE from an inherited
    value the record does not hold, and which makes that run stop inheriting the
    record's implicit derivations. It is not a way to say what the record is.

    The consequence was worse than an absence, and ``CLAUDE.md`` §11 already records it:
    ``system`` is NOT top-level-required, so a record carrying neither field exports
    cleanly — but a record carrying ``technique`` (or a facility field) and no
    ``domain`` fails official validation with ``'domain' is a required property`` and
    could not be repaired except by clearing what had been entered.

    WHY THIS IS NOT THE DERIVATION §5 FORBIDS. Prior sessions declined this work on the
    premise that ``domain`` would have to be DERIVED from ``technique``, which would
    mean authoring a 37-entry scientific classification that exists nowhere in this
    repository. That premise is avoidable and is not adopted here. Both fields are
    CLOSED ENUMS declared by the official schema itself, and a scientist CHOOSING one
    of the schema's own values is a user confirmation over a bounded set — not an
    inference, not a guess, and not a judgement this application makes. Nothing is
    derived, nothing is defaulted, and neither field is inferred from the other: a
    record given only one keeps the other missing, and stays blocked, which is correct.

    DERIVED FROM THE SCHEMA, NOT TRANSCRIBED, and the derivation is doing real work
    rather than showing off. THREE gates, all necessary, all read from the vendored
    document at runtime:

    1. the node declares ``enum`` — so the admissible values are a closed set the
       schema itself publishes, and a refusal can name them without this module
       holding an opinion about what they should be;
    2. the parent declares the key ``required`` — which is what makes the field worth
       a write path at all, and what keeps the OPTIONAL enum leaves out (the eleven
       ``context.electrochemistry.*`` ones, the seven ``computation.method.*`` ones);
    3. ``workspace.field_level`` classifies the path ``experiment`` — so a RUN-level
       enum (``context.environment``) and an unclassified one (``record_type``,
       ``measurement.qc.status``) are excluded here. Those two have their own owners:
       ``context.environment`` is written on the run by ``PATCH .../runs/{run_id}``,
       and ``measurement.qc.status`` is the ``qc`` answer key.

    Measured over the vendored v1.05 document, those three gates yield EXACTLY
    ``system.domain`` and ``system.technique`` — the two paths this slice is about —
    and ``test_system_enum_fields.py`` re-derives that rather than asserting it, so a
    schema refresh that adds a fourth is visible instead of silent.

    Transcribing the 37 techniques instead would put a second copy of the schema's
    vocabulary in this file, free to drift from the document ``CLAUDE.md`` §1 makes the
    authority. Reading it means the gate FOLLOWS a schema refresh.

    THE CACHE MAKES THE FAIL-CLOSED ANSWER STICK, exactly as :func:`_official_block_type`
    records for itself, and the direction is why that is acceptable. An unreadable or
    unparseable schema yields an EMPTY mapping, so no path is recognised, every write is
    refused as ``unrecognized_field``, and nothing is stored — and ``lru_cache`` will
    hold that empty answer for the life of the process rather than for one request. That
    is refusing writes that would have been accepted, never accepting writes that should
    have been refused. Worth saying out loud so nobody debugs it twice.

    THE RESULT IS READ-ONLY BECAUSE IT IS SHARED. Every call returns the SAME object,
    which is the point of the cache, and a caller that added a path to it would widen
    this application's write surface for the life of the process. ``official.py`` records
    the same hazard for its own loader and accepts it (*"Python cannot prevent that"*)
    because it hands back a fresh object every time; this one cannot, so the mapping is
    wrapped and its values are tuples.
    """
    try:
        schema = json.loads(schema_path(REPO_ROOT).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # unreadable or unparseable vendored schema
        return MappingProxyType({})
    found: dict[str, tuple] = {}

    def walk(node: object, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        properties = node.get("properties")
        if not isinstance(properties, dict):
            return
        required = node.get("required")
        required = set(required) if isinstance(required, list) else set()
        for key, child in properties.items():
            if not isinstance(key, str) or not isinstance(child, dict):
                continue
            path = f"{prefix}.{key}" if prefix else key
            values = child.get("enum")
            if (
                isinstance(values, list)
                and key in required
                and ws.field_level(path) == ws.LEVEL_EXPERIMENT
            ):
                found[path] = tuple(values)
            walk(child, path)

    walk(schema, "")
    return MappingProxyType(found)


RUN_CHOSEN_ENUM_PATH_NAMES: tuple[str, ...] = (
    "context.electrochemistry.reaction",
    "context.electrochemistry.cell_type",
)


@functools.lru_cache(maxsize=1)
def _run_chosen_enum_fields() -> Mapping[str, tuple]:
    """``path -> the schema's own enum`` for :data:`RUN_CHOSEN_ENUM_PATH_NAMES`. Read-only."""
    try:
        schema = json.loads(schema_path(REPO_ROOT).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # unreadable or unparseable vendored schema
        return MappingProxyType({})
    found: dict[str, tuple] = {}
    for path in RUN_CHOSEN_ENUM_PATH_NAMES:
        node: object = schema
        for segment in path.split("."):
            properties = node.get("properties") if isinstance(node, dict) else None
            node = properties.get(segment) if isinstance(properties, dict) else None
        values = node.get("enum") if isinstance(node, dict) else None
        if (
            isinstance(values, list)
            and values
            and all(isinstance(v, str) for v in values)
            and ws.field_level(path) == ws.LEVEL_RUN
        ):
            found[path] = tuple(values)
    return MappingProxyType(found)


RUN_WRITABLE_FIELD_PATHS: frozenset[str] = frozenset(
    path
    for path, _coercer in EXTRACTOR_FIELD_MAP.values()
    if ws.field_level(path) == ws.LEVEL_RUN
) | frozenset(_run_chosen_enum_fields())


RECORD_WRITABLE_FIELD_PATHS: frozenset[str] = frozenset(
    path
    for path, _coercer in EXTRACTOR_FIELD_MAP.values()
    if ws.field_level(path) == ws.LEVEL_EXPERIMENT
)


#: THE RECORD-LEVEL BLOCK ADDRESSES the record itself may be given a payload at.
#:
#: FILTERED, NOT COPIED, exactly as :data:`EXPERIMENT_OVERRIDABLE_ADDRESSES` filtered it
#: inline before: iterating ``EXPERIMENT_LEVEL_BLOCKS`` alone would be tautological, so
#: the comprehension runs over BOTH block tuples and lets ``block_level`` decide. Moving
#: ``tags`` between those tuples therefore updates this set from the one place the
#: classification lives.
RECORD_WRITABLE_BLOCK_ADDRESSES: frozenset[str] = frozenset(
    ws.block_address(key)
    for key in (*ws.EXPERIMENT_LEVEL_BLOCKS, *ws.RUN_LEVEL_BLOCKS)
    if ws.block_level(key) == ws.LEVEL_EXPERIMENT
)


#: THE COMPLETE SET OF NAMESPACED ADDRESSES A RUN MAY RECORD AN OVERRIDE AT.
#:
#: Now COMPOSED from the two constants above rather than re-deriving them, so the
#: address set this route enforces and the path set the RECORD-level write routes
#: enforce cannot disagree about what "experiment-level" means. The value is unchanged —
#: ``test_run_api.py::test_the_overridable_set_is_derived_from_the_field_map`` recomputes
#: it from ``EXTRACTOR_FIELD_MAP`` and still passes — and the long argument for each gate
#: now lives on the constants that apply it.
EXPERIMENT_OVERRIDABLE_ADDRESSES: frozenset[str] = frozenset(
    ws.field_address(path) for path in RECORD_WRITABLE_FIELD_PATHS
) | RECORD_WRITABLE_BLOCK_ADDRESSES


NOTE_MAPPABLE_FIELD_PATHS: frozenset[str] = frozenset(
    path for path, _coercer in EXTRACTOR_FIELD_MAP.values()
) | frozenset(_run_chosen_enum_fields())


NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT: frozenset[str] = frozenset(
    path
    for path in NOTE_MAPPABLE_FIELD_PATHS
    if path in RUN_WRITABLE_FIELD_PATHS
    or ws.field_address(path) in EXPERIMENT_OVERRIDABLE_ADDRESSES
    or path in _record_enum_fields()
)


PROPOSAL_TARGET_PATHS: frozenset[str] = NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT


def _proposal_writer_for(path: str) -> str | None:
    """WHICH existing writer applies a value at ``path``, or ``None`` if none does.

    ONE derivation, used three times — by the import-time guard below, by the create
    route to decide whether the proposal needs a run, and by the review route to
    dispatch the write. Three copies of this branch would be three chances for the
    set a route ADMITS and the set it can APPLY to disagree, which is exactly the
    divergence the guard exists to catch.

    THE ENUM CLAUSE IS FIRST, AND THE ORDER IS THE RULE. `system.technique` is BOTH a
    record-level closed enum and a member of `EXPERIMENT_OVERRIDABLE_ADDRESSES`, and
    its run override returns 200 **while accepting off-enum values** — a pre-existing
    divergence `CLAUDE.md` §11 records and deliberately leaves alone. An accepted
    proposal at that path must therefore route through `_apply_record_fields`,
    which checks the enum, and not through the override, which does not. Reversing
    these two clauses would silently inherit a hole this feature must not widen.

    THE FIRST CLAUSE IS ``_record_enum_fields()`` AND NOT ``_record_writable_fields()``,
    WHICH LOOKS LIKE THE DEFECT THE SAME SESSION FIXED IN
    ``NOTE_MAPPABLE_PATHS_WRITABLE_ON_THE_RECORD`` AND IS NOT. An independent review
    raised exactly that, correctly observing that two served keys now answer "which
    paths are the RECORD's" differently — ``record_writable_field_paths`` says 13 and
    ``record_scoped_target_field_paths`` says 1. Widening this clause was MEASURED and
    REJECTED, and the reason is recorded here so nobody re-derives it as an improvement:

    this function maps a PATH to a writer, and :data:`_PROPOSAL_WRITER_SCOPE` then makes
    that writer's scope the path's scope. Returning the record writer for the twelve
    sample/facility paths would therefore make them ``record``-scoped, and the create
    route refuses a proposal that names a run at a record-scoped target
    (``target_is_record_scoped``). **A run override could then never be PROPOSED for a
    sample or facility value** — which is precisely what an override is for, and what
    ``7822b13``'s own message calls "a RUN's deliberate DIVERGENCE". The widening would
    close a documentation gap by deleting a capability.

    The honest fix is a writer chosen from ``(path, run_id)`` rather than from ``path``
    alone, so one path can carry a record-scoped proposal AND a run-scoped one. That is
    a real design change with its own tests and is deliberately NOT done here. Two
    smaller things ARE done, because they are what actually misled a reader: the
    ``target_requires_a_run`` refusal no longer claims "a value at this path is written
    on a RUN" (false since the record answers operation accepted these paths), and it
    now names the operation that does accept them.

    A SECOND THING A WIDENING WOULD HAVE TO CARRY, recorded because it is not obvious:
    :func:`_apply_accepted_proposal`'s record branch reads
    ``_record_enum_fields().get(path) or ()`` and refuses when ``value not in allowed``.
    For a path with no enum that set is empty, so EVERY value would be refused
    ``not_an_allowed_value`` with an empty ``allowed`` list. The branch would need
    ``if allowed and value not in allowed`` plus the storability/declared-type checks
    :func:`_refuse_a_record_value_the_record_cannot_hold` performs, or a proposal would
    be able to write a wrong-typed value that ``POST .../answers`` refuses.
    """
    if path in _record_enum_fields():
        return proposals.APPLIED_VIA_RECORD_ENUM
    if path in RUN_WRITABLE_FIELD_PATHS:
        return proposals.APPLIED_VIA_RUN_FIELD
    if ws.field_address(path) in EXPERIMENT_OVERRIDABLE_ADDRESSES:
        return proposals.APPLIED_VIA_RUN_OVERRIDE
    return None


#: The scope each writer works at. `record` means the proposal must NOT name a run;
#: `run` means it must. Derived from what the writers are rather than asserted:
#: `_apply_record_fields` writes the RECORD's own field map, and the other two
#: are a run's.
_PROPOSAL_WRITER_SCOPE: Mapping[str, str] = MappingProxyType(
    {
        proposals.APPLIED_VIA_RECORD_ENUM: "record",
        proposals.APPLIED_VIA_RUN_FIELD: "run",
        proposals.APPLIED_VIA_RUN_OVERRIDE: "run",
    }
)
