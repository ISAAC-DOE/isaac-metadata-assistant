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

1. :class:`Scope` is a CLOSED ENUM and none of its members means "may finalise".
   ~~"has exactly two members"~~ — **corrected 2026-09-01, when a third was added
   (:attr:`Scope.PROPOSALS_WRITE`), and kept struck rather than reworded because a
   reader who trusts a count stops checking the property.** The count was never the
   guarantee; the CLOSEDNESS is. There is no ``SUBMIT`` value, so a tool cannot
   declare that it needs one and a deployment cannot grant one — the permission is
   not a string that can be typed, it is an enum member that does not exist.
   ``test_mcp_boundaries.test_a_scope_named_submit_cannot_be_expressed_at_all``
   enumerates the members rather than counting them.
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

``PROPOSALS_WRITE`` (added 2026-09-01) does not nest with either of them, in
either direction, and that is the reason it exists rather than a property it
happens to have: an agent that may record a SUGGESTION must not thereby be able to
change draft content, and an agent that may change draft content must not silently
acquire the suggestion channel. Three scopes, no implications, every grant
explicit.
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
    "DESTRUCTIVE_TOKENS",
    "FORBIDDEN_PATH_TOKENS",
    "FORBIDDEN_TOOL_TOKENS",
    "OPERATIONS",
    "PERMITTED_TOOL_NAMES",
    "WRITE_SCOPES",
    "Operation",
    "Scope",
    "changes_query_parameters",
    "forbidden_tool_reason",
    "parse_scope",
    "pending_query_parameters",
    "proposal_list_query_parameters",
    "proposal_target_field_paths",
    "proposal_value_byte_ceiling",
    "run_list_query_parameters",
]


class Scope(Enum):
    """Every permission this server can express. A closed set, on purpose.

    ~~"There are two, on purpose."~~ — **there are three since 2026-09-01, and the
    old sentence is struck rather than edited because this file has twice made a
    COUNT carry a guarantee that belongs to the CLOSEDNESS.** What is on purpose,
    and is unchanged, is that the set is closed, that no member means "may
    finalise", and that no member implies another.

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
    #: Record an ingestion PROPOSAL — a suggestion awaiting a person's judgement.
    #:
    #: WHY IT IS NOT ``DRAFT_WRITE``, which is the whole reason it exists.
    #: ``DRAFT_WRITE`` changes draft content directly; this changes nothing a
    #: draft, an export or a submission reads. ``docs/ingestion-proposal-contract.md``
    #: §5 **I1** and **I2** make a proposal inert to ``export.transform`` and to
    #: ``submissions.content_signature``, and §7 puts it at ``state["proposals"]``,
    #: OUTSIDE ``draft``, so the inertness is structural rather than asserted. That
    #: inertness is precisely what makes this the safe channel for model-derived
    #: output — and giving that channel ``DRAFT_WRITE`` would hand it the unsafe one
    #: alongside. Contract §4: *"The model-derived channel gets the weakest scope
    #: that works."*
    #:
    #: IT UNLOCKS EXACTLY ONE OPERATION, ``create_proposal``. It unlocks no read,
    #: no draft write, and — permanently — no acceptance: reviewing a proposal is
    #: not in :data:`OPERATIONS` at any scope, and ``accept`` is in
    #: :data:`FORBIDDEN_TOOL_TOKENS`, so the name for it is an ``ImportError``.
    #:
    #: **IT IS GRANTED ALONGSIDE ``READ``, NOT INSTEAD OF IT, AND THAT IS A
    #: CORRECTION.** §4's table concludes *"a deployment granting only
    #: `isaac:proposals.write` can create a proposal and read nothing else"*, and
    #: this scope was briefly built to satisfy that literally. **Measured, it is
    #: not achievable**: the create route's precondition is the RECORD's ``ETag``,
    #: the route's own ``412`` discloses ``current_version``, and one further
    #: request then stores a proposal — so the propose-only shape leaks and
    #: bootstraps, while withholding the disclosure would make it inert instead.
    #: ``tools.Tool.required_scopes`` carries the transcript. The clause is
    #: **reported to the contract's owner as needing amendment** and is not edited
    #: from here. What the scope is FOR is untouched and is the whole of its value:
    #: it separates *may propose* from ``DRAFT_WRITE``'s *may change draft content
    #: directly*, so a suggesting agent never acquires the ability to write values.
    PROPOSALS_WRITE = "isaac:proposals.write"


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


#: The scopes that MAY cost a mutation. Named here so the property has a definition
#: rather than living inside :func:`_validated`'s literal and inside a test's.
#:
#: IT IS NOT "every scope except ``READ``", and the difference is the point. Written
#: that way, a fourth member added tomorrow would silently become permitted to mutate
#: by saying nothing. Written as an enumeration, a scope that is to unlock a write has
#: to be added here — which is a reviewed edit to this file — and a scope added and
#: forgotten unlocks nothing at all. Fail-closed on the direction that matters.
WRITE_SCOPES = frozenset({Scope.DRAFT_WRITE, Scope.PROPOSALS_WRITE})


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
#: ``accept`` is here for the reason ``approve`` is, and it was MISSING while
#: ``approve`` was present — which is a gap of exactly one synonym. ISAAC's own
#: conflict-resolution vocabulary is *accept a proposal*, not *approve* one
#: (``conflict_resolution.py``), so the name a future author would reach for to
#: expose that capability is ``isaac_accept_proposal`` — and it would have sailed
#: past this set. Added so that it is an ``ImportError`` rather than a review miss.
#: Nothing registered today contains the substring, checked before adding it.
FORBIDDEN_TOOL_TOKENS = frozenset(
    {
        "accept",
        "approve",
        "delete",
        "destroy",
        "discard",
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
#:
#: ~~"This is the same refusal as :data:`FORBIDDEN_TOOL_TOKENS` applied one layer
#: down, so a permitted-looking tool name cannot be pointed at a forbidden route."~~
#: **CORRECTED 2026-08-26 — that sentence was FALSE for the destructive verbs, which
#: are the ones it most needed to be true for.** Measured: ``delete``, ``destroy``,
#: ``drop``, ``purge`` and ``remove`` were all in the TOOL set and NONE of them was
#: in this one, while ``POST .../runs/{run_id}/remove`` and
#: ``POST .../assets/{asset_id}/remove`` had existed as routes for some time — so a
#: tool named anything innocuous could have been pointed at either of them and this
#: layer would not have said a word. ``POST .../experiments/{id}/discard`` would have
#: been a third. The five are added here, together with ``discard``, and the claim is
#: kept struck through rather than reworded because the point of the two lists is
#: that the relationship between them is checkable — and this one went unchecked.
#:
#: **THE TWO SETS ARE STILL NOT EQUAL, AND MUST NOT BE MADE EQUAL.** ``database``,
#: ``uploads``, ``verification``, ``demo`` and ``tutorial/sessions`` are path-only,
#: deliberately: they name ROUTES whose subject matter is off limits, not verbs a
#: tool might be called. ``approve``, ``finalis``/``finaliz``, ``governance``,
#: ``grant``, ``publish``, ``revoke``, ``signoff``/``sign_off`` and ``truncate`` are
#: tool-only, because no route path carries them. What IS now asserted, by
#: ``test_mcp_boundaries``, is the narrower and checkable property: every
#: DESTRUCTIVE verb appears in BOTH sets.
#:
#: ``database`` and ``verification`` are here because those routes read the
#: production-derived corpus (``CLAUDE.md`` §15, gates G2/G3); ``uploads`` because
#: ingestion is refused deployment-wide; ``tutorial/sessions`` because session
#: lifecycle belongs to the deployment binding, not to a tool argument.
#:
#: NONE of the six added verbs collides with any permitted operation path — checked
#: before they were added, and re-checked continuously by ``_validated``, which
#: refuses at import time if a permitted path ever contains one. So this costs
#: nothing today and refuses a whole class of route tomorrow.
#:
#: ~~"any of the eleven permitted operation paths"~~ — the count was wrong when it was
#: written (there were thirteen) and would have gone wrong again on 2026-09-01 (there
#: are seventeen). It is replaced by the PROPERTY, which is what ``_validated``
#: actually enforces, for the reason ``tools.py``'s own docstring gives: *"a
#: hand-maintained tally in a safety comment drifts"*.
FORBIDDEN_PATH_TOKENS = frozenset(
    {
        "database",
        "delete",
        "demo",
        "destroy",
        "discard",
        "drop",
        "export",
        "migrat",
        "purge",
        "remove",
        "reset",
        "submit",
        "tutorial/sessions",
        "uploads",
        "verification",
    }
)

#: The verbs that must appear in BOTH sets above. Named once, here, so the property
#: has a definition rather than living only inside a test's literal.
#:
#: It is deliberately NOT "the intersection of the two sets" — that would be a
#: tautology no drift could break. It is the class of verb that must never name a
#: tool AND must never name a route a tool can reach, and it is the exact class the
#: correction above records having been enforced in only one of the two places.
DESTRUCTIVE_TOKENS = frozenset(
    {"delete", "destroy", "discard", "drop", "purge", "remove"}
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

#: Pending-list query parameters this package is permitted to expose, reviewed the same
#: way the run-list set is and for the same reason: the derivation below reads the ROUTE,
#: and this frozenset is the REVIEW GATE on what the route is allowed to teach the tool.
#:
#: WHAT WAS REVIEWED, because "it is only paging" is not a review. All three BOUND a read
#: that the route answers COMPLETELY by default. `run_id` is a filter on a value the
#: agent already holds — `isaac_list_questions` returns `run_id` on every entry, and
#: `isaac_list_runs` lists them — so it selects nothing the caller could not already see,
#: and an UNKNOWN run is refused by the route rather than answered with an empty page, so
#: it cannot be used to probe for ids. `offset`/`limit` carry no record content at all.
#: None of the three can widen a response, name a field, or select on scientific content:
#: the route's own `pending_page.record_total` keeps reporting the WHOLE record's open
#: question count, so a bounded read can never be mistaken for the record's state.
#:
#: `q` IS DELIBERATELY ABSENT. The pending route does not have it today; listing it
#: pre-emptively (as the run-list set does) would be pre-approving a free-text selector
#: over question text, and that is a different question from paging — it is the one this
#: gate exists to stop being answered by accident.
PENDING_QUERY_ALLOWLIST = frozenset({"run_id", "offset", "limit"})

#: Proposal-list query parameters this package is permitted to expose. Same review gate,
#: same reason.
#:
#: WHAT WAS REVIEWED. All three BOUND or FILTER a list the route already bounds by
#: default — unlike ``GET .../runs`` and ``GET .../pending``, `GET .../proposals` returns
#: a WINDOW when `limit` is omitted, deliberately (contract §10 DEC-5). `state` selects on
#: a LIFECYCLE state from the server's own closed set, never on content: it cannot name a
#: field, a value, a note or a scientist. `after` is a cursor a previous window returned,
#: and one this record does not hold is REFUSED (`422 unknown_cursor`) rather than treated
#: as the start of the list, so it cannot be used to probe for ids. `limit` carries no
#: record content at all.
#:
#: THERE IS NO `q` HERE AND NONE IS PRE-APPROVED. The proposal list has no free-text
#: selector today; listing one pre-emptively would be pre-approving a search over a
#: scientist's own words, since a proposal's excerpt is derived from a note's verbatim
#: text. That is the question this gate exists to stop being answered by accident.
#: `order` was ADDED 2026-09-02 and reviewed on the same ground as `state`: it names
#: no field, selects on no scientific content, and widens no response — it chooses
#: between the two directions of a total order the server already computes, and both
#: return the same rows. It is exposed because WITHOUT it an agent reading a record
#: that holds more proposals than one window cannot reach the newest proposal at all
#: without walking every page, which is the same defect on the tool surface that the
#: panel had on the website.
PROPOSAL_LIST_QUERY_ALLOWLIST = frozenset({"state", "limit", "after", "order"})

#: Change-feed query parameters this package is permitted to expose.
#:
#: WHAT WAS REVIEWED. `cursor` is opaque BY CONTRACT (`change_feed.encode_cursor`): it
#: carries a version, a scope digest and a position, no record content, and a cursor
#: minted for a different record or a different workspace scope is REFUSED rather than
#: answered from the wrong order. `limit` is CLAMPED by the route rather than refused,
#: and the effective value is reported back, so an agent cannot be silently truncated.
#: Neither can name a field, select on scientific content, or widen a response: the feed
#: serves ids, positions, timestamps and — for a proposal — a lifecycle state, and
#: nothing else.
CHANGES_QUERY_ALLOWLIST = frozenset({"cursor", "limit"})


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
    #: The route's own ``max_length``, when it declares one. CARRIED BECAUSE IT WAS
    #: DROPPED: the tool schema built from these rendered ``minimum``/``maximum`` for
    #: integers and nothing at all for strings, so ``isaac_list_runs``' ``q`` — which
    #: the route bounds at ``RUN_QUERY_MAX`` — was published as an UNBOUNDED string and
    #: `validate_arguments` had nothing to check. A 60 KB value was forwarded, echoed
    #: back in the refusal body, and past ~64 KB failed URL construction as an
    #: unhandled error rather than as a refusal. Same derivation rule as everything
    #: else here: read off the route, never invented.
    max_length: int | None = None


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


def _query_parameters(
    route, allowlist: frozenset[str], what: str
) -> tuple[QueryParameter, ...]:
    """One route's own query parameters, read off its signature and gated by ``allowlist``.

    ONE READER FOR EVERY GATED ROUTE, and it is shared rather than copied for exactly the
    reason the derivation exists at all: a second copy of this walk is a second place the
    ``Annotated``/``Query``/``Literal`` handling can drift, and the copy that drifts is the
    one publishing a wrong schema to an external agent.

    Raises ``RuntimeError`` when the route carries a parameter that is not in
    ``allowlist``, or one whose type this reader cannot render as a JSON Schema type. Both
    are refusals to guess: exposing a parameter whose meaning has not been reviewed, or
    one whose schema would be wrong, is worse than not exposing it.
    """
    found: list[QueryParameter] = []
    hints = typing.get_type_hints(route, include_extras=True)
    for name, parameter in inspect.signature(route).parameters.items():
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
        if name not in allowlist:
            raise RuntimeError(
                f"the {what} route exposes an unreviewed query parameter {name!r}; "
                f"add it to the {what} allowlist only after deciding it is safe "
                "for an agent to filter on"
            )
        rendered = _json_type_for(base)
        if rendered is None:
            raise RuntimeError(
                f"cannot render {what} query parameter {name!r} as a JSON Schema "
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
                max_length=_max_length(query),
            )
        )
    return tuple(found)


def run_list_query_parameters() -> tuple[QueryParameter, ...]:
    """The run-list route's own query parameters, gated by
    :data:`RUN_LIST_QUERY_ALLOWLIST`."""
    from ..routes import list_runs  # local: keeps module import order flexible

    return _query_parameters(list_runs, RUN_LIST_QUERY_ALLOWLIST, "run-list")


def pending_query_parameters() -> tuple[QueryParameter, ...]:
    """The pending-list route's own query parameters, gated by
    :data:`PENDING_QUERY_ALLOWLIST`.

    WHY THIS EXISTS. ``isaac_list_questions`` exposed the UNBOUNDED read only, while the
    route it calls had grown ``run_id``, ``offset`` and ``limit``. A record's question set
    grows with its runs — at 1,000 runs ``GET /pending`` measured **1.78 MB** — so an
    agent working on ONE run had no way to ask for one run's questions and was forced to
    download the whole record's set to find them. The tool is not made bounded by this;
    the route's default is unchanged and still complete. What changes is that the client
    can now ASK, which is the same distinction the HTTP route draws.
    """
    from ..routes import get_pending  # local: keeps module import order flexible

    return _query_parameters(get_pending, PENDING_QUERY_ALLOWLIST, "pending-list")


def proposal_list_query_parameters() -> tuple[QueryParameter, ...]:
    """The proposal-list route's own query parameters, gated by
    :data:`PROPOSAL_LIST_QUERY_ALLOWLIST`."""
    from ..routes import list_proposals  # local: keeps module import order flexible

    return _query_parameters(
        list_proposals, PROPOSAL_LIST_QUERY_ALLOWLIST, "proposal-list"
    )


def changes_query_parameters() -> tuple[QueryParameter, ...]:
    """The change-feed route's own query parameters, gated by
    :data:`CHANGES_QUERY_ALLOWLIST`."""
    from ..routes import get_changes  # local: keeps module import order flexible

    return _query_parameters(get_changes, CHANGES_QUERY_ALLOWLIST, "changes")


def proposal_target_field_paths() -> tuple[str, ...]:
    """The official field paths a proposal may target, READ OFF THE ROUTE MODULE.

    Same derivation rule as every query-parameter set here, and it matters more than
    usual: ``routes.PROPOSAL_TARGET_PATHS`` is itself derived — the note-mappable paths
    that some write operation in this build accepts a value at — so it WIDENS on its own
    the day one of the seven currently-unwritable paths gains a route. Transcribing the
    18 into a published tool schema would create a second copy free to drift, and the
    copy that drifts is the one an external agent reads before choosing a target.

    Published as a closed ``enum`` in ``isaac_propose_field_value``'s schema so a wrong
    path is refused HERE, naming every permitted one, rather than reaching the route and
    coming back as a ``422`` an agent has to interpret. A closed set also needs no length
    bound — its longest member is the bound — which is why this returns the values rather
    than a maximum.
    """
    from ..routes import PROPOSAL_TARGET_PATHS  # local: keeps import order flexible

    return tuple(sorted(PROPOSAL_TARGET_PATHS))


def proposal_value_byte_ceiling() -> int:
    """The bytes ``proposed_value`` and ``rule`` may occupy TOGETHER, off the route.

    Read rather than transcribed, for the reason the route itself reads it from
    ``_MAX_NOTE_BYTES``: *"a proposal whose ceiling was lower than its source's would
    refuse a value read out of a note this application had already accepted"*, and a
    third copy would be free to drift from both.

    IT IS A JOINT BYTE CEILING AND ``maxLength`` IS A PER-STRING CHARACTER COUNT, so
    they are not the same quantity and this is used as an UPPER bound only. Every UTF-8
    string of *n* characters occupies at least *n* bytes, so a ``rule`` longer than this
    many characters cannot possibly fit under the joint ceiling — publishing it as
    ``maxLength`` therefore refuses nothing the route would have accepted. The tighter,
    exact check stays where it can be exact: at the route, as ``422 value_too_large``,
    measured over the rendered pair.
    """
    from ..routes import _MAX_PROPOSAL_BYTES  # local: keeps import order flexible

    return _MAX_PROPOSAL_BYTES


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


def _max_length(query: object) -> int | None:
    """The route's declared string length bound, or ``None``.

    Read exactly as :func:`_bounds` reads ``ge``/``le``, and for the same reason: this
    FastAPI keeps it as an ``annotated_types.MaxLen`` in ``Query.metadata`` while older
    versions kept a ``max_length`` attribute, and a reader that knows only one of them
    silently reports NO bound — which is how an unbounded string reaches a published
    tool schema. A bound this cannot find is reported as absent rather than guessed;
    what the caller does with an absent one is the caller's decision, and
    ``tools._query_schema`` refuses rather than publishes.
    """
    # AN ``int`` FROM EITHER SOURCE, NOT "THE FIRST NON-``None``". Those differ, and the
    # difference is a live upgrade hazard rather than a hypothetical: on the installed
    # FastAPI the bound lives ONLY in ``metadata`` as an ``annotated_types.MaxLen``, and
    # ``Query(max_length=200)`` has no ``max_length`` attribute at all. A version that
    # parks a SENTINEL there instead (``PydanticUndefined`` is the obvious candidate)
    # would satisfy a ``found is None`` test, stop the metadata scan before it started,
    # and report NO bound — which ``tools._query_schema`` then turns into a
    # ``RuntimeError`` that takes ``create_app()`` down at import for every MCP
    # deployment. Requiring an ``int`` makes a sentinel simply not a bound.
    for candidate in (
        getattr(query, "max_length", None),
        *(getattr(c, "max_length", None) for c in getattr(query, "metadata", None) or ()),
    ):
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            return candidate
    return None


def _run_list_query_names() -> frozenset[str]:
    return frozenset(p.name for p in run_list_query_parameters())


def _pending_query_names() -> frozenset[str]:
    return frozenset(p.name for p in pending_query_parameters())


def _proposal_list_query_names() -> frozenset[str]:
    return frozenset(p.name for p in proposal_list_query_parameters())


def _changes_query_names() -> frozenset[str]:
    return frozenset(p.name for p in changes_query_parameters())


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
            query_parameters=_pending_query_names(),
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
        # THE INGESTION-PROPOSAL SURFACE, AND THE ONE OPERATION DELIBERATELY ABSENT
        # FROM IT.
        #
        # `docs/ingestion-proposal-contract.md` §4 strikes its own "MCP: no new tool"
        # in ONE direction only, and this table is where the amendment and the part
        # that survives it both live. What is added: a bounded read of the list, a
        # read of one, a CREATE at its own weakest-that-works scope, and the change
        # feed that lets an agent notice a person answered.
        #
        # WHAT IS NOT ADDED, AND MUST NEVER BE:
        # `POST .../proposals/{proposal_id}/review`. It is the operation that
        # ACCEPTS — it writes a scientific value through the manual writers, and it
        # is the one transition that requires a trusted human. Contract §4: *"No
        # accept, review, supersede, withdraw, finalize, export or Submit tool may
        # exist at any scope, and `POST .../proposals/{id}/review` must never appear
        # in an MCP `OPERATIONS` entry."* Its absence from this tuple is the
        # enforcement; `accept` in `FORBIDDEN_TOOL_TOKENS` is the second, independent
        # one, and `test_mcp_boundaries` asserts both rather than trusting this
        # comment.
        #
        # AND THE ROUTES COMMENT THAT SAYS OTHERWISE IS NOW STALE, NAMED HERE RATHER
        # THAN LEFT FOR A READER TO TRIP OVER: `routes.py`'s section 7c opens *"NO
        # MCP TOOL, AND NO PROPOSAL IN AN MCP-REACHABLE PAYLOAD"*. Its FIRST half is
        # superseded by the amendment above. Its SECOND half is unchanged and still
        # enforced — no `proposals` key is added to `GET /api/experiments/{id}`,
        # which `isaac_get_experiment` reaches (contract DEC-7); these are DEDICATED
        # operations, which is a reviewed widening rather than a silent one.
        Operation(
            id="list_proposals",
            method="GET",
            path_template="/api/experiments/{experiment_id}/proposals",
            scope=Scope.READ,
            mutates=False,
            summary="One bounded window of a record's ingestion proposals.",
            query_parameters=_proposal_list_query_names(),
        ),
        Operation(
            id="get_proposal",
            method="GET",
            path_template="/api/experiments/{experiment_id}/proposals/{proposal_id}",
            scope=Scope.READ,
            mutates=False,
            summary="One ingestion proposal, with its derived staleness reads.",
        ),
        Operation(
            id="create_proposal",
            method="POST",
            path_template="/api/experiments/{experiment_id}/proposals",
            # THE ONLY OPERATION THIS SCOPE UNLOCKS, and the only operation that
            # costs it. Not `DRAFT_WRITE`: creating a proposal writes no draft
            # content, mints no evidence and is inert to export — see
            # `Scope.PROPOSALS_WRITE`.
            scope=Scope.PROPOSALS_WRITE,
            # It DOES mutate: the proposal is stored inside the experiment's own
            # state document, so the record's `rev` and ETag move. `mutates` is about
            # whether stored state changes, not about whether a scientific value
            # does, and conflating those is how a write ends up without a
            # precondition.
            mutates=True,
            summary="Record one suggested value for a record field, awaiting review.",
            requires_if_match=True,
        ),
        Operation(
            id="get_changes",
            method="GET",
            path_template="/api/experiments/{experiment_id}/changes",
            scope=Scope.READ,
            mutates=False,
            summary=(
                "A bounded page of the record's coalescing state feed, from a cursor."
            ),
            query_parameters=_changes_query_names(),
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
        # ~~`op.scope is not Scope.DRAFT_WRITE`~~ — widened 2026-09-01 to
        # :data:`WRITE_SCOPES`, which is an ENUMERATION and not "anything but READ".
        # The property being kept is unchanged and is the one that matters: a
        # mutation may never cost a read scope, so a write cannot hide behind one.
        # What changed is that there is now more than one write scope, and which
        # scopes may carry a mutation is a reviewed list rather than a default.
        if op.mutates and op.scope not in WRITE_SCOPES:
            raise RuntimeError(
                f"MCP operation {op.id!r} mutates state but costs {op.scope.value!r}, "
                f"which is not one of {sorted(s.value for s in WRITE_SCOPES)}"
            )
        seen[op.id] = op
    return MappingProxyType(seen)


#: Every route this server may call, keyed by operation id. Closed and frozen:
#: ``client.py`` resolves an id through this mapping and refuses anything else, so
#: an operation that is not here is unreachable rather than merely unused.
OPERATIONS: Mapping[str, Operation] = _validated(_operations())


#: A DOCUMENTATION DEFECT IN THE SPECIFYING CONTRACT, RECORDED RATHER THAN RESOLVED
#: SILENTLY. ``docs/ingestion-proposal-contract.md`` **§4 Operations, line 323 at
#: `7ff8194`** heads its table *the amended surface — three tools, least privilege* and
#: its cells name FOUR, across three rows: the middle row names ``isaac_list_proposals``
#: and ``isaac_get_proposal`` together. The CELLS are the specification and they are what
#: this file implements; the heading's count is wrong. It is reported to the document's
#: owner rather than edited from here, and it is written down so nobody later reads the
#: mismatch as this package having added a tool the contract did not authorise.
#:
#: ~~"§10.2's table"~~ — **every citation in this slice originally pointed at §10.2, and
#: the note reporting a wrong count was itself filed against the wrong section.** §10.2
#: is *The thirteen decisions* (line 681) and says nothing about the MCP surface; the
#: surface, the scope table and the "read nothing else" clause are all §4 (lines 210–343).
#: Re-derive rather than trusting either number::
#:
#:     git show 7ff8194:docs/ingestion-proposal-contract.md | grep -n '^## \|^### '
#:
#: The **DEC-N** citations elsewhere in this package are unaffected and correct: those
#: decisions really are in §10.2.
#:
#: **THIS NOTE IS DELIBERATELY OUTSIDE THE FROZENSET BELOW, AND THAT IS NOT
#: TYPOGRAPHY.** ``apps/web/src/__tests__/connect-your-agent.test.tsx`` parses this
#: file with ``PERMITTED_TOOL_NAMES = frozenset\(\s*\{([^}]*)\}`` and then harvests
#: every double-quoted string inside the braces. A comment carrying a quoted phrase
#: therefore READ AS A TOOL NAME: the phrase was inside the set for one revision and
#: the frontend suite reported 15 permitted tools, one of them the heading it was
#: quoting. The spec's parser is hardened in the same change; keeping quoted prose out
#: of the literal is the other half, and costs nothing.
#:
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
        # THE INGESTION-PROPOSAL SURFACE (2026-09-01), a reviewed widening of this
        # set under `docs/ingestion-proposal-contract.md` §4. Four names, and the
        # names matter: not one of them contains `accept`, `approve`, `submit`,
        # `export` or any other member of `FORBIDDEN_TOOL_TOKENS` — checked by
        # `forbidden_tool_reason` at import for every one of them, and asserted
        # again over the registry by `test_mcp_boundaries`. The count discrepancy in
        # the contract's own heading is recorded above this frozenset, deliberately
        # OUTSIDE it — see the note there.
        "isaac_propose_field_value",
        "isaac_list_proposals",
        "isaac_get_proposal",
        "isaac_get_changes",
    }
)


#: ~~``RESULT_CARRIES_NO_RECORD_CONTENT``~~ — **A SET OF TOOLS EXEMPT FROM ALSO COSTING
#: ``READ``. BUILT 2026-09-01, WITHDRAWN THE SAME DAY, AND RECORDED HERE RATHER THAN
#: DELETED, because "a write tool that needs no read scope" is a design a future author
#: will reach for and the reason it fails here is a measurement, not taste.**
#:
#: Its one member was ``isaac_propose_field_value``, on the argument that its handler
#: returned a built projection carrying no record content, which made §4's *"a deployment
#: granting only `isaac:proposals.write` can create a proposal and read nothing else"*
#: true rather than aspirational. An independent review confirmed the projection was
#: genuine and then measured the branch it did not cover — see
#: ``tools.Tool.required_scopes`` for the transcript. In summary: the route's own ``412``
#: hands a propose-only caller ``current_version``, the next request succeeds and stores
#: a proposal, the success envelope's ``etag`` sustains the session, and an
#: ``invalid_span`` refusal returns ``note_text_length`` — the true length of a
#: scientist's verbatim note.
#:
#: **THE FIX IS NOT A BIGGER PROJECTION.** This route's precondition is the RECORD's
#: ``ETag``; a principal that may not read the record cannot legitimately obtain one, so
#: withholding the ``412``'s ``current_version`` would make the sentence true and the
#: deployment shape inert. A capability that cannot work is not least privilege.
#: ``isaac_propose_field_value`` therefore costs ``{READ, PROPOSALS_WRITE}`` like every
#: other write tool, and the exemption mechanism is gone rather than left empty — an
#: unused closed set with an import-time guard is machinery protecting nothing, which is
#: what ``oauth.py`` records deleting ``scopes_expressible`` for.


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
