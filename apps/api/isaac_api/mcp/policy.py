"""What the MCP tool layer may do, expressed as DATA rather than as discipline.

THE ONE-WAY INVARIANT
=====================
MCP is one-way (``docs/mcp-capability-audit.md`` §1): a scientist's own Claude
calls ISAAC's tools. It does not give ISAAC inference, and it is not a path for a
model to reach into the truth plane. Nothing in this package imports
``isaac_records``; every effect it can have is an HTTP-shaped call into
``isaac_api``'s own already-gated routes, and those routes keep every precondition
they have today. ``test_mcp_boundaries.py`` scans this package's imports and fails
if that ever stops being true.

WHY "NO SUBMIT" IS A TYPE PROBLEM AND NOT A COMMENT
===================================================
The capability audit's §5 says never build a ``submit_record`` tool, a delete
tool, a migration tool, or anything that changes governance. A comment saying so
is worth nothing the first time somebody adds a route. So the refusal is spread
across four independent structures, each of which alone stops it:

1. :class:`Scope` has exactly two members. There is no ``SUBMIT`` value, so a
   tool cannot declare that it needs one and a deployment cannot grant one — the
   permission is not a string that can be typed, it is an enum member that does
   not exist.
2. :data:`OPERATIONS` is a closed table of ``(method, path)`` pairs. The client
   in ``client.py`` takes an operation *id* and looks it up here; it will not
   issue a request that is not in this table, so a tool cannot reach a route by
   constructing a path.
3. :data:`ALLOWED_METHODS` omits ``DELETE`` and ``PUT`` entirely, so no
   allowlist entry can express unrestricted destructive deletion even if one were
   added.
4. :data:`PERMITTED_TOOL_NAMES` is a closed set, and :data:`FORBIDDEN_TOOL_TOKENS`
   /:data:`FORBIDDEN_PATH_TOKENS` are checked at import. A module that registers
   ``isaac_submit_record`` — or an operation whose path contains ``/export`` —
   fails to import, in the application and in CI, before any test runs.

The two token sets are the part that survives a future author who is not reading
this docstring: they turn "we decided not to" into an ``ImportError``.

WHY THE SCOPES DO NOT NEST
==========================
``DRAFT_WRITE`` deliberately does not imply ``READ``. Implication is convenient
and it is also how a caller ends up holding a permission nobody granted, so a
deployment that wants a read-write agent grants both explicitly and a reader that
was never granted the write scope cannot acquire it by being upgraded.
"""

from __future__ import annotations

import inspect
import types
import typing
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

__all__ = [
    "ALLOWED_METHODS",
    "FORBIDDEN_PATH_TOKENS",
    "FORBIDDEN_TOOL_TOKENS",
    "OPERATIONS",
    "PERMITTED_TOOL_NAMES",
    "Operation",
    "Scope",
    "forbidden_tool_reason",
    "parse_scope",
    "run_list_query_parameters",
]


class Scope(Enum):
    """Every permission this server can express. There are two, on purpose.

    The string values are namespaced because a hosted OAuth binding will hand
    them to a token issuer as OAuth scope strings, and an unnamespaced ``read``
    would collide with every other resource server at the institution.
    """

    #: See records, runs, evidence, and validation findings. Writes nothing.
    READ = "isaac:read"
    #: Change *draft* content — add a run, correct an answered field, edit a
    #: run's own fields. It does not, and cannot, finalise anything: the
    #: operations it unlocks are enumerated in :data:`OPERATIONS` and none of
    #: them mints an official record.
    DRAFT_WRITE = "isaac:draft.write"


def parse_scope(raw: str) -> Scope | None:
    """The :class:`Scope` for a scope string, or ``None`` if there is no such scope.

    ``None`` rather than a raise, because every caller here fails closed on it,
    and because the string arrives from configuration: ``isaac:submit`` must
    resolve to nothing at all rather than to an error a caller might catch and
    treat as "unknown, allow".
    """
    for scope in Scope:
        if scope.value == raw:
            return scope
    return None


#: The HTTP methods an allowlist entry may use. ``DELETE`` and ``PUT`` are absent,
#: which is what makes "no unrestricted destructive deletion" a property of the
#: table's shape rather than of its current contents.
ALLOWED_METHODS = frozenset({"GET", "POST", "PATCH"})

#: Substrings that may never appear in a registered tool's name. Checked
#: case-insensitively at import time by :func:`forbidden_tool_reason`.
#:
#: ``export`` is in here alongside ``submit``. Export is the operation that mints
#: an official ISAAC record and its evidence sidecar — it is the finalisation this
#: slice is forbidden to expose, whatever it is called on a given screen — so the
#: token that would name it is banned rather than left to be recognised.
FORBIDDEN_TOOL_TOKENS = frozenset(
    {
        "approve",
        "delete",
        "destroy",
        "drop",
        "export",
        "finalis",
        "finaliz",
        "governance",
        "grant",
        "migrat",
        "publish",
        "purge",
        "remove",
        "reset",
        "revoke",
        "signoff",
        "sign_off",
        "submit",
        "truncate",
    }
)

#: Substrings that may never appear in an allowlisted operation's path template.
#: This is the same refusal as :data:`FORBIDDEN_TOOL_TOKENS` applied one layer
#: down, so a permitted-looking tool name cannot be pointed at a forbidden route.
#:
#: ``database`` and ``verification`` are here because those routes read the
#: production-derived corpus (``CLAUDE.md`` §15, gates G2/G3); ``uploads`` because
#: ingestion is refused deployment-wide; ``tutorial/sessions`` because session
#: lifecycle belongs to the deployment binding, not to a tool argument.
FORBIDDEN_PATH_TOKENS = frozenset(
    {
        "database",
        "demo",
        "export",
        "migrat",
        "reset",
        "submit",
        "tutorial/sessions",
        "uploads",
        "verification",
    }
)


@dataclass(frozen=True)
class Operation:
    """One route this server is permitted to call, and the scope it costs.

    ``scope`` is a property of the OPERATION, not of the HTTP verb.
    ``check_run`` is a ``POST`` and requires only :attr:`Scope.READ`, because the
    route writes nothing and does not advance any revision — the API's own
    description and ``test_run_api.py``'s invariant 5 both say so. Deriving the
    permission from the verb would have made a read cost a write scope, which
    teaches a caller to ask for the write scope it does not need.
    """

    id: str
    method: str
    path_template: str
    scope: Scope
    #: Whether this operation changes stored state. Reported to clients as the
    #: MCP ``readOnlyHint`` annotation — which the spec is explicit is a HINT and
    #: never enforcement (audit §4). The enforcement is :attr:`scope`.
    mutates: bool
    summary: str
    #: Query parameters this operation accepts. Anything else is refused by the
    #: client before a request is built.
    query_parameters: frozenset[str] = frozenset()
    #: Whether the operation requires an ``If-Match`` precondition. The optimistic
    #: concurrency contract is the API's (``428`` absent / ``400`` malformed /
    #: ``412`` stale); this flag only lets the tool layer refuse before the round
    #: trip and describe the requirement in the tool schema.
    requires_if_match: bool = False


# --------------------------------------------------------------------------
# The run-list filter set is DERIVED from the route, never transcribed
# --------------------------------------------------------------------------
#
# `GET /experiments/{id}/runs` grew a bounded page (`limit`/`offset`) and is
# growing relevance filters on other branches. Transcribing its parameter list
# here would create a second copy free to drift: the tool would advertise a
# filter the route does not have (FastAPI ignores unknown query parameters, so
# the call would succeed and silently return an unfiltered list — a tool lying
# about what it did), or omit one the route does have.
#
# So the set is read off the route's own signature. The allowlist below is not
# the source of the set; it is the REVIEW GATE on it. A parameter the route grows
# that is not in the allowlist raises at import rather than being exposed
# unreviewed, which is the fail-closed direction for a filter that might one day
# select on something per-record.

#: Run-list query parameters this package is permitted to expose, pending review.
#: ``q``, ``overrides`` and ``exported`` are listed because they are the relevance
#: filters the run-list route is gaining; whether they are actually exposed
#: depends entirely on whether the route in THIS checkout has them.
RUN_LIST_QUERY_ALLOWLIST = frozenset({"limit", "offset", "q", "overrides", "exported"})


@dataclass(frozen=True)
class QueryParameter:
    """A query parameter derived from a route signature."""

    name: str
    json_type: str
    description: str
    minimum: int | None = None
    maximum: int | None = None
    #: The closed set of values, when the route's own annotation is a `Literal`.
    #: Carried so the tool schema REFUSES a value the route would reject, instead
    #: of forwarding it and letting a model read a 422 as "no runs matched".
    enum: tuple[str, ...] | None = None


def _json_type_for(annotation: object) -> tuple[str, tuple[str, ...] | None] | None:
    """The JSON Schema type for a route parameter, and its value set if closed.

    Returns ``(json_type, enum_or_None)``, or ``None`` when the annotation cannot
    be rendered — which the caller turns into a refusal rather than a guess.

    ``Literal`` IS HANDLED, and it is not a nicety. The run-list route grew
    ``overrides: Literal["any", "none"] | None`` when server-side filtering
    landed, and this reader refused it — correctly, and loudly, at import. Falling
    back to a bare ``"string"`` would have been the quiet wrong answer: the tool
    would advertise a free-text parameter, a model would send ``"all"``, and the
    route's 422 would reach it as a failed call rather than as "that is not one of
    the two things this filter accepts". A closed set in the schema is the whole
    difference between a model that can use the filter and one that guesses at it.
    """
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        members = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(members) != 1:
            return None
        annotation = members[0]
        origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        values = typing.get_args(annotation)
        # Only an all-string literal renders cleanly; a mixed-type one would need
        # a JSON Schema this reader does not build, so it refuses instead.
        if values and all(isinstance(v, str) for v in values):
            return "string", tuple(values)
        return None
    # bool before int: bool is a subclass of int and would otherwise be "integer".
    if annotation is bool:
        return "boolean", None
    if annotation is int:
        return "integer", None
    if annotation is str:
        return "string", None
    return None


def run_list_query_parameters() -> tuple[QueryParameter, ...]:
    """The run-list route's own query parameters, read off its signature.

    Raises ``RuntimeError`` when the route carries a parameter that is not in
    :data:`RUN_LIST_QUERY_ALLOWLIST`, or one whose type this reader cannot render
    as a JSON Schema type. Both are refusals to guess: exposing a parameter whose
    meaning has not been reviewed, or one whose schema would be wrong, is worse
    than not exposing it.
    """
    from ..routes import list_runs  # local: keeps module import order flexible

    found: list[QueryParameter] = []
    hints = typing.get_type_hints(list_runs, include_extras=True)
    for name, parameter in inspect.signature(list_runs).parameters.items():
        annotation = hints.get(name, parameter.annotation)
        # `__metadata__` rather than `get_origin(...) is Annotated`: what
        # `get_origin` returns for an `Annotated[...]` alias has changed between
        # supported Python versions, and this attribute has not.
        if not hasattr(annotation, "__metadata__"):
            continue
        base, *metadata = typing.get_args(annotation)
        query = next(
            (m for m in metadata if type(m).__name__ == "Query"),
            None,
        )
        if query is None:
            continue
        if name not in RUN_LIST_QUERY_ALLOWLIST:
            raise RuntimeError(
                f"the run-list route exposes an unreviewed query parameter {name!r}; "
                "add it to RUN_LIST_QUERY_ALLOWLIST only after deciding it is safe "
                "for an agent to filter on"
            )
        rendered = _json_type_for(base)
        if rendered is None:
            raise RuntimeError(
                f"cannot render run-list query parameter {name!r} as a JSON Schema "
                f"type (annotation {base!r})"
            )
        json_type, enum = rendered
        minimum, maximum = _bounds(query)
        found.append(
            QueryParameter(
                name=name,
                json_type=json_type,
                enum=enum,
                description=str(getattr(query, "description", "") or "").strip(),
                minimum=minimum,
                maximum=maximum,
            )
        )
    return tuple(found)


def _bounds(query: object) -> tuple[int | None, int | None]:
    """``(ge, le)`` for a FastAPI ``Query``, wherever this version keeps them.

    FastAPI moved numeric constraints onto an ``annotated_types`` metadata list;
    older versions kept ``ge``/``le`` as attributes. Both are read, and a bound
    this cannot find is reported as ABSENT rather than guessed — an invented
    ``maximum`` in a tool schema would refuse a page size the route accepts.
    """
    minimum = getattr(query, "ge", None)
    maximum = getattr(query, "le", None)
    for constraint in getattr(query, "metadata", None) or ():
        if minimum is None:
            minimum = getattr(constraint, "ge", None)
        if maximum is None:
            maximum = getattr(constraint, "le", None)
    return (
        minimum if isinstance(minimum, int) else None,
        maximum if isinstance(maximum, int) else None,
    )


def _run_list_query_names() -> frozenset[str]:
    return frozenset(p.name for p in run_list_query_parameters())


# --------------------------------------------------------------------------
# The closed operation table
# --------------------------------------------------------------------------

def _operations() -> tuple[Operation, ...]:
    return (
        Operation(
            id="list_experiments",
            method="GET",
            path_template="/api/experiments",
            scope=Scope.READ,
            mutates=False,
            summary="One summary row per experiment in the caller's workspace scope.",
        ),
        Operation(
            id="get_experiment",
            method="GET",
            path_template="/api/experiments/{experiment_id}",
            scope=Scope.READ,
            mutates=False,
            summary="One experiment's detail, with its current ETag.",
        ),
        Operation(
            id="list_runs",
            method="GET",
            path_template="/api/experiments/{experiment_id}/runs",
            scope=Scope.READ,
            mutates=False,
            summary="A bounded page of a record's runs.",
            query_parameters=_run_list_query_names(),
        ),
        Operation(
            id="get_run",
            method="GET",
            path_template="/api/experiments/{experiment_id}/runs/{run_id}",
            scope=Scope.READ,
            mutates=False,
            summary="One run, with the run's own ETag.",
        ),
        Operation(
            id="create_run",
            method="POST",
            path_template="/api/experiments/{experiment_id}/runs",
            scope=Scope.DRAFT_WRITE,
            mutates=True,
            # NOT "one empty run" — the same false claim `isaac_create_run`'s tool
            # description carried, in the catalog entry beside it. The FIRST run adopts
            # the record's per-run content; only a LATER run is empty. Nothing reads
            # this field today, which is precisely why it drifted unnoticed.
            summary="Add one run to a record; the first adopts its per-run content.",
            requires_if_match=True,
        ),
        Operation(
            id="update_run_draft",
            method="PATCH",
            path_template="/api/experiments/{experiment_id}/runs/{run_id}",
            scope=Scope.DRAFT_WRITE,
            mutates=True,
            summary="Write run-level draft values on one run.",
            requires_if_match=True,
        ),
        Operation(
            id="correct_record_field",
            method="POST",
            path_template="/api/experiments/{experiment_id}/edit",
            scope=Scope.DRAFT_WRITE,
            mutates=True,
            summary="Correct an already-answered record-level draft field.",
            requires_if_match=True,
        ),
        # THE FOUR OPERATIONS THAT ANSWER THE QUESTIONS ISAAC IS ASKING.
        #
        # Until these existed the tool surface could add a run and write its five
        # `RUN_WRITABLE_FIELD_PATHS`, and could correct a record-level field that
        # had ALREADY been answered — so an agent could not answer an OPEN blocking
        # question at all, at either level. On a record created through ISAAC's own
        # Create Experiment path that is every question it has: `/edit` refuses a
        # field nothing has answered yet (`422`, no editable field), and the
        # spectrum, QC verdict, descriptors and asset hashes are not among the five
        # PATCH accepts. The gap was recorded in `docs/mcp-capability-audit.md`
        # §5A before it was closed, rather than closed quietly.
        #
        # Two levels, because the levels are not interchangeable and the API says
        # so: once a record has runs, its own `/answers` REFUSES a run-owned key
        # with `409 belongs_to_a_run` rather than writing a value no exported
        # record reads. Exposing only the record level would have handed an agent a
        # refusal it could not act on.
        # DISCOVERY, and it is not optional decoration. Without it the write
        # operations below are unusable: the keys an answer is submitted under come
        # from this route and nowhere else, and `get_experiment` does not carry
        # them. Shipping the writes alone would have meant a tool whose description
        # named an endpoint this server may not call.
        Operation(
            id="list_questions",
            method="GET",
            path_template="/api/experiments/{experiment_id}/pending",
            scope=Scope.READ,
            mutates=False,
            summary=(
                "The record's open blocking questions, each with the key an answer "
                "is submitted under and the run that owns it."
            ),
        ),
        Operation(
            id="answer_record_question",
            method="POST",
            path_template="/api/experiments/{experiment_id}/answers",
            scope=Scope.DRAFT_WRITE,
            mutates=True,
            summary="Answer a record's own open blocking questions.",
            requires_if_match=True,
        ),
        Operation(
            id="answer_run_question",
            method="POST",
            path_template="/api/experiments/{experiment_id}/runs/{run_id}/answers",
            scope=Scope.DRAFT_WRITE,
            mutates=True,
            summary="Answer one run's open blocking questions.",
            requires_if_match=True,
        ),
        Operation(
            id="correct_run_field",
            method="POST",
            path_template="/api/experiments/{experiment_id}/runs/{run_id}/edit",
            scope=Scope.DRAFT_WRITE,
            mutates=True,
            summary="Correct a value one run has already confirmed.",
            requires_if_match=True,
        ),
        Operation(
            id="check_run",
            method="POST",
            path_template="/api/experiments/{experiment_id}/runs/{run_id}/check",
            scope=Scope.READ,
            mutates=False,
            summary=(
                "The draft and official verdicts for the record one run would "
                "export. Writes nothing and advances no revision."
            ),
        ),
        Operation(
            id="get_evidence",
            method="GET",
            path_template="/api/experiments/{experiment_id}/evidence",
            scope=Scope.READ,
            mutates=False,
            summary="The field-by-field evidence trail for a record.",
        ),
    )


def _validated(operations: tuple[Operation, ...]) -> Mapping[str, Operation]:
    seen: dict[str, Operation] = {}
    for op in operations:
        if op.id in seen:
            raise RuntimeError(f"duplicate MCP operation id {op.id!r}")
        if op.method not in ALLOWED_METHODS:
            raise RuntimeError(
                f"MCP operation {op.id!r} uses method {op.method!r}, which is not in "
                f"ALLOWED_METHODS {sorted(ALLOWED_METHODS)}"
            )
        lowered = op.path_template.lower()
        for token in sorted(FORBIDDEN_PATH_TOKENS):
            if token in lowered:
                raise RuntimeError(
                    f"MCP operation {op.id!r} targets {op.path_template!r}, which "
                    f"contains the forbidden path token {token!r}"
                )
        if not op.path_template.startswith("/api/"):
            raise RuntimeError(
                f"MCP operation {op.id!r} targets {op.path_template!r}, which is not "
                "under /api/"
            )
        if op.mutates and not op.requires_if_match:
            raise RuntimeError(
                f"MCP operation {op.id!r} mutates state without an If-Match "
                "precondition; a lost update is not an acceptable default"
            )
        if op.mutates and op.scope is not Scope.DRAFT_WRITE:
            raise RuntimeError(
                f"MCP operation {op.id!r} mutates state but costs {op.scope.value!r}"
            )
        seen[op.id] = op
    return MappingProxyType(seen)


#: Every route this server may call, keyed by operation id. Closed and frozen:
#: ``client.py`` resolves an id through this mapping and refuses anything else, so
#: an operation that is not here is unreachable rather than merely unused.
OPERATIONS: Mapping[str, Operation] = _validated(_operations())


#: Every tool that may be registered. Closed, and checked both ways at import by
#: ``tools.py`` — a tool missing from the registry fails, and a tool in the
#: registry that is not named here fails.
PERMITTED_TOOL_NAMES = frozenset(
    {
        "isaac_list_experiments",
        "isaac_get_experiment",
        "isaac_list_runs",
        "isaac_get_run",
        "isaac_create_run",
        "isaac_list_questions",
        "isaac_update_draft",
        # Answering an OPEN blocking question, at whichever level owns it. Added
        # deliberately as a reviewed widening of this set, which is what the
        # `forbidden_tool_reason` check exists to force.
        "isaac_answer_questions",
        "isaac_check_run",
        "isaac_inspect_evidence",
    }
)


def forbidden_tool_reason(name: str) -> str | None:
    """Why ``name`` may not be a tool name, or ``None`` if it may.

    Two independent refusals, and the order matters for the error message: a name
    carrying a forbidden token is reported as such even if somebody has also added
    it to :data:`PERMITTED_TOOL_NAMES`, so widening the permitted set is not a way
    to smuggle a forbidden capability past the check.
    """
    lowered = name.lower()
    for token in sorted(FORBIDDEN_TOOL_TOKENS):
        if token in lowered:
            return (
                f"the tool name {name!r} contains the forbidden capability token "
                f"{token!r}; this server exposes no finalisation, deletion, "
                "migration or governance capability (docs/mcp-capability-audit.md §5)"
            )
    if name not in PERMITTED_TOOL_NAMES:
        return (
            f"the tool name {name!r} is not in PERMITTED_TOOL_NAMES; adding a tool "
            "is a reviewed change to that set, not a registration"
        )
    return None
