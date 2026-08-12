"""The eight tools, their schemas, and the registry that refuses a ninth.

READ-MOSTLY BY CONSTRUCTION
===========================
Six of the eight are reads. The two writes touch DRAFT content only — add a run,
write draft values — and both require the ``If-Match`` precondition the API
already enforces, so an agent working from a stale read loses the race rather
than the scientist losing an edit.

Nothing here finalises. There is no export tool, no delete tool, no migration
tool and no governance tool; ``policy.py`` explains why that is four structures
rather than four omissions.

THE CONFIRMATION IS THE CALLER'S ASSERTION, NOT THIS LAYER'S
============================================================
``update_draft`` requires ``confirmed_by_user`` as an explicit argument and passes
it through unchanged. It would have been one line to hard-code ``true`` and it is
the wrong line: ``confirmed_by_user`` is what the API records as the *evidence*
for a value that has no other support, and a layer that sets it on the caller's
behalf manufactures a confirmation nobody gave. Passing ``false`` earns the API's
own ``422 confirmation_required``, which is the honest outcome and is pinned as a
refusal test.

ANNOTATIONS ARE HINTS; SCOPES ARE THE GATE
==========================================
Each tool publishes ``readOnlyHint``/``destructiveHint``/``idempotentHint``
because clients render them, and the MCP specification is explicit that they are
hints a client MAY act on — never enforcement (audit §4). The enforcement is the
scope check in ``server.py`` and the operation allowlist in ``client.py``, both of
which run whatever a client does with the annotation.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping

from .client import ApiResult, IsaacApiClient
from .policy import (
    OPERATIONS,
    PERMITTED_TOOL_NAMES,
    Scope,
    forbidden_tool_reason,
    run_list_query_parameters,
)

__all__ = [
    "InvalidArguments",
    "TOOLS",
    "Tool",
    "ToolContext",
    "ToolOutcome",
    "registered_tool_names",
    "validate_arguments",
]

#: Argument names a tool schema may never declare. Each is a way a caller could
#: try to state who it is, what it may do, or where the request should go —
#: exactly the claims the server must make for itself. Checked at import.
RESERVED_ARGUMENT_NAMES = frozenset(
    {
        "authorisation",
        "authorization",
        "credential",
        "header",
        "headers",
        "method",
        "operation",
        "operation_id",
        "path",
        "principal",
        "scope",
        "scopes",
        "session",
        "session_id",
        "subject",
        "token",
        "tutorial_session",
        "tutorial_session_id",
        "url",
        "workspace",
    }
)


class InvalidArguments(Exception):
    """A tool call's arguments did not match the tool's declared input schema."""


@dataclass(frozen=True)
class ToolContext:
    """Everything a handler is allowed to know. Note what is absent: the app, the
    environment, and any way to reach a route that is not an allowlisted operation."""

    client: IsaacApiClient


@dataclass(frozen=True)
class ToolOutcome:
    payload: dict
    is_error: bool = False


Handler = Callable[[ToolContext, Mapping[str, Any]], Awaitable[ToolOutcome]]


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    scope: Scope
    #: Every operation this tool may reach. Validated against the allowlist at
    #: import, and validated to cost no more than :attr:`scope`.
    operation_ids: tuple[str, ...]
    input_schema: dict
    handler: Handler
    read_only: bool
    idempotent: bool

    def annotations(self) -> dict:
        return {
            "title": self.title,
            "readOnlyHint": self.read_only,
            "destructiveHint": False,
            "idempotentHint": self.idempotent,
            "openWorldHint": False,
        }

    def descriptor(self) -> dict:
        """The ``tools/list`` entry for this tool."""
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": _deep_copy(self.input_schema),
            "annotations": self.annotations(),
            # Not part of the MCP schema; ISAAC states the scope a call costs so a
            # client can see, before calling, that a tool it was not granted exists
            # and why it will be refused.
            "_isaac": {
                "requiredScope": self.scope.value,
                "operations": list(self.operation_ids),
            },
        }


# --------------------------------------------------------------------------
# A small, total argument validator
# --------------------------------------------------------------------------
#
# Deliberately not a JSON Schema library: this package adds no dependency, and the
# schemas it has to check are eight fixed objects of scalars. What it does support
# is exactly what those schemas use, and anything it meets that it does not
# understand is a RAISE rather than a pass — an unknown keyword must not silently
# become "no constraint".

_TYPE_CHECKS: Mapping[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    # bool first: `isinstance(True, int)` is True, and an agent sending `true` for
    # `limit` must be refused rather than paging by 1.
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
}

_SUPPORTED_KEYWORDS = frozenset(
    {"type", "description", "enum", "minimum", "maximum", "minLength", "maxLength", "minProperties"}
)


def validate_arguments(schema: Mapping[str, Any], arguments: Mapping[str, Any]) -> dict:
    """``arguments`` checked against ``schema``, or :class:`InvalidArguments`.

    Returns a plain dict of the accepted arguments — never the caller's mapping,
    so a handler cannot be handed something with a surprising ``__getitem__``.
    """
    if not isinstance(arguments, Mapping):
        raise InvalidArguments("arguments must be an object")
    properties: Mapping[str, Any] = schema.get("properties", {})
    required = set(schema.get("required", ()))

    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        raise InvalidArguments(
            f"unknown argument(s) {unknown}; this tool accepts "
            f"{sorted(properties)}"
        )
    missing = sorted(required - set(arguments))
    if missing:
        raise InvalidArguments(f"missing required argument(s) {missing}")

    accepted: dict[str, Any] = {}
    for name, value in arguments.items():
        spec = properties[name]
        extra_keywords = set(spec) - _SUPPORTED_KEYWORDS
        if extra_keywords:  # pragma: no cover - guarded at import by _validate_tool
            raise InvalidArguments(
                f"the schema for {name!r} uses keyword(s) {sorted(extra_keywords)} "
                "this validator does not implement"
            )
        expected = spec["type"]
        if not _TYPE_CHECKS[expected](value):
            raise InvalidArguments(f"{name!r} must be of type {expected}")
        if "enum" in spec and value not in spec["enum"]:
            raise InvalidArguments(f"{name!r} must be one of {spec['enum']}")
        if expected == "string":
            if len(value) < spec.get("minLength", 0):
                raise InvalidArguments(
                    f"{name!r} must be at least {spec['minLength']} character(s)"
                )
            if "maxLength" in spec and len(value) > spec["maxLength"]:
                raise InvalidArguments(
                    f"{name!r} must be at most {spec['maxLength']} characters"
                )
        if expected == "integer":
            if "minimum" in spec and value < spec["minimum"]:
                raise InvalidArguments(f"{name!r} must be >= {spec['minimum']}")
            if "maximum" in spec and value > spec["maximum"]:
                raise InvalidArguments(f"{name!r} must be <= {spec['maximum']}")
        if expected == "object" and len(value) < spec.get("minProperties", 0):
            raise InvalidArguments(
                f"{name!r} must name at least {spec['minProperties']} field(s)"
            )
        accepted[name] = value
    return accepted


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in value]
    return value


def _object_schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        # The single most load-bearing line in every schema here: it is what makes
        # an injected `scopes` or `tutorial_session_id` a validation error rather
        # than an ignored key.
        "additionalProperties": False,
    }


_EXPERIMENT_ID = {
    "type": "string",
    "minLength": 1,
    "maxLength": 128,
    "description": "The record's id, as returned by isaac_list_experiments.",
}
_RUN_ID = {
    "type": "string",
    "minLength": 1,
    "maxLength": 128,
    "description": "The run's id, as returned by isaac_list_runs.",
}


# --------------------------------------------------------------------------
# Result shaping
# --------------------------------------------------------------------------

def _ok(operation_id: str, result: ApiResult, data: Any = None) -> ToolOutcome:
    return ToolOutcome(
        {
            "operation": operation_id,
            "status": result.status,
            "etag": result.etag,
            "data": result.body if data is None else data,
        }
    )


def _failed(operation_id: str, result: ApiResult) -> ToolOutcome:
    """A route's own refusal, reported as the API stated it.

    The API's error bodies are already typed and already carefully worded — the
    ``428``/``412`` precondition contract, ``422 unrecognized_field``,
    ``404 experiment_not_found``. Restating them here would be a second copy free
    to drift, and a softer one, so the body is passed through and only the
    envelope is added.
    """
    body = result.body if isinstance(result.body, dict) else {"detail": result.body}
    return ToolOutcome(
        {
            "operation": operation_id,
            "status": result.status,
            "error": body.get("error", "request_refused"),
            "data": body,
        },
        is_error=True,
    )


def _settle(operation_id: str, result: ApiResult, data: Any = None) -> ToolOutcome:
    return _ok(operation_id, result, data) if result.ok else _failed(operation_id, result)


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------

async def _list_experiments(ctx: ToolContext, args: Mapping[str, Any]) -> ToolOutcome:
    result = await ctx.client.call("list_experiments")
    return _settle("list_experiments", result)


async def _get_experiment(ctx: ToolContext, args: Mapping[str, Any]) -> ToolOutcome:
    result = await ctx.client.call(
        "get_experiment", path_params={"experiment_id": args["experiment_id"]}
    )
    return _settle("get_experiment", result)


async def _list_runs(ctx: ToolContext, args: Mapping[str, Any]) -> ToolOutcome:
    query = {k: v for k, v in args.items() if k != "experiment_id"}
    result = await ctx.client.call(
        "list_runs",
        path_params={"experiment_id": args["experiment_id"]},
        query=query,
    )
    return _settle("list_runs", result)


async def _get_run(ctx: ToolContext, args: Mapping[str, Any]) -> ToolOutcome:
    result = await ctx.client.call(
        "get_run",
        path_params={
            "experiment_id": args["experiment_id"],
            "run_id": args["run_id"],
        },
    )
    return _settle("get_run", result)


async def _create_run(ctx: ToolContext, args: Mapping[str, Any]) -> ToolOutcome:
    body: dict[str, Any] = {}
    if "label" in args:
        body["label"] = args["label"]
    result = await ctx.client.call(
        "create_run",
        path_params={"experiment_id": args["experiment_id"]},
        json_body=body,
        if_match=args["if_match"],
    )
    return _settle("create_run", result)


async def _update_draft(ctx: ToolContext, args: Mapping[str, Any]) -> ToolOutcome:
    """One tool, two operations, chosen by whether a run is named.

    Draft content lives at two levels and they take different preconditions: a
    run-level write needs THE RUN's ETag, a record-level correction needs the
    RECORD's. Splitting this into two tools would have been defensible; keeping it
    as one keeps "update the draft" a single idea for the caller, and the
    ``if_match`` description states which tag each branch wants, because getting
    that wrong is the most likely way a caller sees a ``412``.
    """
    run_id = args.get("run_id")
    if run_id is None:
        if "label" in args:
            return ToolOutcome(
                {
                    "operation": "correct_record_field",
                    "status": 0,
                    "error": "label_requires_run",
                    "data": {
                        "message": (
                            "`label` renames a run, so it is only meaningful with "
                            "`run_id`. A record's title is not draft content and is "
                            "not writable through this server."
                        )
                    },
                },
                is_error=True,
            )
        result = await ctx.client.call(
            "correct_record_field",
            path_params={"experiment_id": args["experiment_id"]},
            json_body={
                "confirmed_by_user": args["confirmed_by_user"],
                "answers": args["fields"],
            },
            if_match=args["if_match"],
        )
        return _settle("correct_record_field", result)

    body: dict[str, Any] = {
        "confirmed_by_user": args["confirmed_by_user"],
        "fields": args["fields"],
    }
    if "label" in args:
        body["label"] = args["label"]
    result = await ctx.client.call(
        "update_run_draft",
        path_params={"experiment_id": args["experiment_id"], "run_id": run_id},
        json_body=body,
        if_match=args["if_match"],
    )
    return _settle("update_run_draft", result)


async def _check_run(ctx: ToolContext, args: Mapping[str, Any]) -> ToolOutcome:
    result = await ctx.client.call(
        "check_run",
        path_params={
            "experiment_id": args["experiment_id"],
            "run_id": args["run_id"],
        },
    )
    return _settle("check_run", result)


async def _inspect_evidence(ctx: ToolContext, args: Mapping[str, Any]) -> ToolOutcome:
    result = await ctx.client.call(
        "get_evidence", path_params={"experiment_id": args["experiment_id"]}
    )
    return _settle("get_evidence", result)


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------

def _run_list_schema() -> dict:
    """``isaac_list_runs``'s schema, with the filters the ROUTE actually has.

    See ``policy.run_list_query_parameters`` for why this is derived rather than
    written down. The practical consequence: a filter that lands on the run-list
    route (and passes the allowlist review gate) is exposed here with the route's
    own description, and one that has not landed yet is not advertised — so the
    tool never claims a filter it would silently drop.
    """
    properties: dict[str, Any] = {"experiment_id": dict(_EXPERIMENT_ID)}
    for parameter in run_list_query_parameters():
        spec: dict[str, Any] = {
            "type": parameter.json_type,
            "description": parameter.description or f"The route's {parameter.name} parameter.",
        }
        if parameter.enum is not None:
            # THE CLOSED SET TRAVELS INTO THE SCHEMA, so `_check_argument` refuses a
            # value the route would reject rather than forwarding it. Without this a
            # model sending `overrides="all"` gets the route's 422 back as a failed
            # call, which reads like "the filter is broken" rather than "that is not
            # one of the two values this filter has".
            spec["enum"] = list(parameter.enum)
        if parameter.minimum is not None:
            spec["minimum"] = parameter.minimum
        if parameter.maximum is not None:
            spec["maximum"] = parameter.maximum
        properties[parameter.name] = spec
    return _object_schema(properties, ["experiment_id"])


def _tools() -> tuple[Tool, ...]:
    return (
        Tool(
            name="isaac_list_experiments",
            title="List records",
            description=(
                "List the records in this workspace: id, title, derived status, how "
                "many blocking questions are open, how many fields carry evidence, "
                "and whether the record has been exported. Read-only, and it states "
                "no validity verdict. If the list may be short the response carries "
                "an `incomplete` object saying so — treat a short list as evidence "
                "about this read, never as an inventory."
            ),
            scope=Scope.READ,
            operation_ids=("list_experiments",),
            input_schema=_object_schema({}, []),
            handler=_list_experiments,
            read_only=True,
            idempotent=True,
        ),
        Tool(
            name="isaac_get_experiment",
            title="Read one record",
            description=(
                "One record's detail: status, revision metadata, workflow position "
                "and counts. The returned `etag` is the RECORD's current revision "
                "and is what `isaac_create_run` and a record-level "
                "`isaac_update_draft` require in `if_match`."
            ),
            scope=Scope.READ,
            operation_ids=("get_experiment",),
            input_schema=_object_schema(
                {"experiment_id": dict(_EXPERIMENT_ID)}, ["experiment_id"]
            ),
            handler=_get_experiment,
            read_only=True,
            idempotent=True,
        ),
        Tool(
            name="isaac_list_runs",
            title="List a record's runs",
            description=(
                "A bounded page of a record's runs, each with its own draft fields, "
                "its resolved view of the record-level values it inherits, and its "
                "own revision. The response states `total` (runs that exist), "
                "`returned` and `offset`, so a short page is visibly a page rather "
                "than a complete list. Paging is not snapshot-consistent: compare "
                "`experiment_version` across pages and re-read from the start when "
                "it moves. Read-only."
            ),
            scope=Scope.READ,
            operation_ids=("list_runs",),
            input_schema=_run_list_schema(),
            handler=_list_runs,
            read_only=True,
            idempotent=True,
        ),
        Tool(
            name="isaac_get_run",
            title="Read one run",
            description=(
                "One run: its own draft fields, the record-level content it "
                "inherits (resolved on read, never copied down), and its revision. "
                "The returned `etag` is THE RUN's revision and is what a run-level "
                "`isaac_update_draft` requires — the record's tag will not match it."
            ),
            scope=Scope.READ,
            operation_ids=("get_run",),
            input_schema=_object_schema(
                {"experiment_id": dict(_EXPERIMENT_ID), "run_id": dict(_RUN_ID)},
                ["experiment_id", "run_id"],
            ),
            handler=_get_run,
            read_only=True,
            idempotent=True,
        ),
        Tool(
            name="isaac_create_run",
            title="Add a run to a record",
            description=(
                "Add one run — one measurement condition — to a record. The new run "
                "starts EMPTY: no record-level value is copied into it and no "
                "scientific value is invented. Requires the RECORD's current `etag` "
                "in `if_match`; omitted is refused, stale is refused with nothing "
                "written."
            ),
            scope=Scope.DRAFT_WRITE,
            operation_ids=("create_run",),
            input_schema=_object_schema(
                {
                    "experiment_id": dict(_EXPERIMENT_ID),
                    "if_match": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 256,
                        "description": (
                            "The RECORD's current ETag, exactly as isaac_get_experiment "
                            "returned it."
                        ),
                    },
                    "label": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 200,
                        "description": (
                            "Optional name for the run. Omit it and the server "
                            "assigns the next `Run N`."
                        ),
                    },
                },
                ["experiment_id", "if_match"],
            ),
            handler=_create_run,
            read_only=False,
            # Adding a run is not idempotent: the same call twice adds two runs.
            # The `if_match` precondition is what makes a RETRY safe, not this flag.
            idempotent=False,
        ),
        Tool(
            name="isaac_update_draft",
            title="Write draft values",
            description=(
                "Write draft values on a record, recording a user confirmation for "
                "each. Name a `run_id` to write that run's own run-level fields "
                "(supply THE RUN's etag); omit it to correct an already-answered "
                "record-level field (supply the RECORD's etag).\n\n"
                "`confirmed_by_user` must be sent explicitly and is passed through "
                "unchanged — it is what ISAAC records as the support for a value "
                "that has no other evidence, so it is the caller's assertion that "
                "the scientist confirmed it, not this server's. Send `false` and the "
                "write is refused.\n\n"
                "Every key in `fields` must be a real official field path at the "
                "level you are writing. An invented, misspelt or wrong-level path is "
                "refused naming it, and NOTHING in the request is written. No value "
                "is ever invented. Re-submitting a value the draft already holds is "
                "a no-op and does not advance the revision. This does not export, "
                "finalise or submit anything."
            ),
            scope=Scope.DRAFT_WRITE,
            operation_ids=("update_run_draft", "correct_record_field"),
            input_schema=_object_schema(
                {
                    "experiment_id": dict(_EXPERIMENT_ID),
                    "run_id": {
                        **_RUN_ID,
                        "description": (
                            "Optional. Present: write this run's own fields. Absent: "
                            "correct an already-answered record-level field."
                        ),
                    },
                    "if_match": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 256,
                        "description": (
                            "Required. THE RUN's ETag when `run_id` is given, the "
                            "RECORD's ETag when it is not."
                        ),
                    },
                    "confirmed_by_user": {
                        "type": "boolean",
                        "description": (
                            "Required. True only if the scientist confirmed these "
                            "values. It is recorded as the evidence for them."
                        ),
                    },
                    "fields": {
                        "type": "object",
                        "minProperties": 1,
                        "description": (
                            "Official field paths to values. A null value clears "
                            "that field."
                        ),
                    },
                    "label": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 200,
                        "description": "Optional new name for the run. Requires `run_id`.",
                    },
                },
                ["experiment_id", "if_match", "confirmed_by_user", "fields"],
            ),
            handler=_update_draft,
            read_only=False,
            idempotent=True,
        ),
        Tool(
            name="isaac_check_run",
            title="Check a run",
            description=(
                "Check the official record one run WOULD export — its own content "
                "plus what it inherits — and return the no-guessing draft verdict, "
                "the official ISAAC schema verdict, and the run's open blocking "
                "questions. Writes nothing, exports nothing, and advances no "
                "revision. Both verdicts come from the same deterministic core the "
                "command line uses; an advisory warning never turns a pass into a "
                "failure."
            ),
            scope=Scope.READ,
            operation_ids=("check_run",),
            input_schema=_object_schema(
                {"experiment_id": dict(_EXPERIMENT_ID), "run_id": dict(_RUN_ID)},
                ["experiment_id", "run_id"],
            ),
            handler=_check_run,
            read_only=True,
            idempotent=True,
        ),
        Tool(
            name="isaac_inspect_evidence",
            title="Inspect a record's evidence",
            description=(
                "The field-by-field evidence trail for a record: each official path, "
                "its value, the kind of support behind it, and the source file and "
                "locator cited. For an exported record the trail is read from the "
                "evidence sidecar; otherwise from the draft's own evidence "
                "envelopes, which are that sidecar's source. Read-only."
            ),
            scope=Scope.READ,
            operation_ids=("get_evidence",),
            input_schema=_object_schema(
                {"experiment_id": dict(_EXPERIMENT_ID)}, ["experiment_id"]
            ),
            handler=_inspect_evidence,
            read_only=True,
            idempotent=True,
        ),
    )


def _validate_tool(tool: Tool) -> None:
    reason = forbidden_tool_reason(tool.name)
    if reason is not None:
        raise RuntimeError(reason)
    if not tool.operation_ids:
        raise RuntimeError(f"tool {tool.name!r} declares no operation")
    for operation_id in tool.operation_ids:
        operation = OPERATIONS.get(operation_id)
        if operation is None:
            raise RuntimeError(
                f"tool {tool.name!r} declares operation {operation_id!r}, which is "
                "not in the allowlist"
            )
        if operation.scope is not tool.scope:
            raise RuntimeError(
                f"tool {tool.name!r} costs {tool.scope.value!r} but operation "
                f"{operation_id!r} costs {operation.scope.value!r}; a tool must cost "
                "exactly what its operations cost, so a write cannot hide behind a "
                "read scope and a read cannot demand a write scope"
            )
        if operation.mutates and tool.read_only:
            raise RuntimeError(
                f"tool {tool.name!r} is annotated readOnlyHint but reaches the "
                f"mutating operation {operation_id!r}"
            )
    schema = tool.input_schema
    if schema.get("additionalProperties") is not False:
        raise RuntimeError(
            f"tool {tool.name!r} must declare additionalProperties: false, or a "
            "caller can send an argument nobody validated"
        )
    for name, spec in schema.get("properties", {}).items():
        if name in RESERVED_ARGUMENT_NAMES:
            raise RuntimeError(
                f"tool {tool.name!r} declares the reserved argument {name!r}: "
                "identity, permission and routing are decided by the server, never "
                "supplied by the caller"
            )
        unsupported = set(spec) - _SUPPORTED_KEYWORDS
        if unsupported:
            raise RuntimeError(
                f"tool {tool.name!r} argument {name!r} uses schema keyword(s) "
                f"{sorted(unsupported)} the argument validator does not implement"
            )
        if spec.get("type") not in _TYPE_CHECKS:
            raise RuntimeError(
                f"tool {tool.name!r} argument {name!r} has unsupported type "
                f"{spec.get('type')!r}"
            )
    for name in schema.get("required", ()):
        if name not in schema.get("properties", {}):
            raise RuntimeError(
                f"tool {tool.name!r} requires undeclared argument {name!r}"
            )


def _registry() -> Mapping[str, Tool]:
    registry: dict[str, Tool] = {}
    for tool in _tools():
        if tool.name in registry:
            raise RuntimeError(f"duplicate MCP tool {tool.name!r}")
        _validate_tool(tool)
        registry[tool.name] = tool
    # BOTH DIRECTIONS. `_validate_tool` refuses a tool that is not permitted; this
    # refuses a permitted name that nothing registers, so the closed set cannot rot
    # into a list of names with no relationship to what the server serves.
    missing = sorted(PERMITTED_TOOL_NAMES - set(registry))
    if missing:
        raise RuntimeError(
            f"PERMITTED_TOOL_NAMES lists {missing}, which no tool registers"
        )
    return MappingProxyType(registry)


#: Every tool this server has, permitted or not yet granted to a given caller.
TOOLS: Mapping[str, Tool] = _registry()


def registered_tool_names() -> frozenset[str]:
    """Every registered tool name, regardless of scope.

    The negative control in ``test_mcp_boundaries.py`` enumerates THIS rather than
    a ``tools/list`` response, because ``tools/list`` is filtered by the caller's
    scopes and a forbidden tool could hide behind a scope nobody was granted.
    """
    return frozenset(TOOLS)
