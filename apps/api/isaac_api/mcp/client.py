"""The only way this package can reach ISAAC, and the last place a call is refused.

WHY THE ALLOWLIST IS ENFORCED HERE AND NOT IN THE TOOLS
=======================================================
A tool that builds its own URL is a tool that can be made to build a different
one. :meth:`AsgiApiClient.call` takes an operation *id*, resolves it through the
frozen :data:`~.policy.OPERATIONS` table, and refuses anything it does not find —
so the set of routes this package can reach is a property of that table rather
than of the tools that happen to exist today. A buggy or malicious tool cannot
issue ``POST /api/experiments/{id}/export``, because there is no code path from a
tool to a request that does not pass through the table.

Three narrower refusals sit alongside it, each closing a way an argument could
become a URL or a header:

* **Path parameters are pattern-checked, not escaped.** ``../`` and ``%2e%2e``
  fail the character class rather than being encoded into something the router
  then normalises. Record and run ids are ULIDs; nothing legitimate needs a
  character outside ``[A-Za-z0-9._~-]``.
* **Query parameters are allowlisted per operation** from the route's own
  signature, so a filter the route does not implement cannot be sent — FastAPI
  ignores unknown query parameters, which would otherwise let a tool report a
  filtered list it never filtered.
* **The caller cannot supply headers.** There is no header argument. ``If-Match``
  is a typed parameter, and the worked-example session header is written from the
  principal, so a tool cannot address a scope it was not bound to.

IN-PROCESS, BY ASGI, WITH NO NETWORK AND NO CREDENTIAL
======================================================
The transport is ``httpx.ASGITransport`` against the FastAPI application object —
already a dependency (``pyproject.toml`` ``[api]``), so this package adds none.
**This client** opens no socket and resolves no DNS, and nothing it does leaves
the machine.

*Scoped rather than deleted, because an earlier revision said "the whole suite
runs offline" and that was read as "no test binds a socket".* One test does:
``test_mcp_transport.py::test_a_real_client_over_a_real_loopback_socket_completes_a_session``
runs a uvicorn server on ``127.0.0.1`` with an ephemeral port, because a
kernel-supplied peer address is the only thing that can prove the loopback guard
reads one. It is still offline in the sense that matters — the bind is loopback
and no packet leaves the host — but "no socket is opened" is a claim about this
module, not about the suite.

The calls go through the real router, the real dependencies (including
``tutorial_scope``), the real precondition machinery and the real exception
handlers, which is the point: the MCP layer inherits ISAAC's gates instead of
re-implementing them.

ONE DELIBERATE NON-BEHAVIOUR: THE APP'S OWN API KEY
====================================================
When ``ISAAC_UI_API_KEY`` is set, ``ApiKeyAuthMiddleware`` guards every route. This
client does **not** hold that key and does not read that variable. A ``401`` from
the application is surfaced as a typed refusal naming the condition, rather than
being papered over by plumbing the shared secret through a second consumer. Which
credential an MCP caller presents, and how it relates to the app's key and to the
Authentik edge, is decision **D2** — unanswered — and this is what "unwired" looks
like at the code level.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx

from ..config import base_path
from .policy import OPERATIONS, Operation

__all__ = ["ApiRefusal", "ApiResult", "AsgiApiClient", "IsaacApiClient"]

#: Path-parameter predicate: the id shape, not a character class.
#:
#: ~~``re.compile(r"^[A-Za-z0-9._~-]{1,128}$")``~~ — **REPLACED, because it admitted
#: ``.`` and ``..`` and those are not characters, they are PATH SEGMENTS.** The old
#: comment called the class "deliberately narrow" and said the three extra
#: characters were there "so a legitimate id shape change does not require a
#: security review"; ``.`` was one of the three, and admitting it is what let a dot
#: segment through. Measured, twice, before this changed:
#:
#: * ``isaac_get_run(run_id="..")`` returned ``isError: false`` and handed the agent
#:   the **record** detail — ``httpx`` resolved ``/api/experiments/{id}/runs/..``
#:   to ``/api/experiments/{id}`` — so a run read silently became a record read.
#: * ``isaac_get_run(run_id=".")`` likewise reached ``GET .../runs``, the LIST.
#: * ``isaac_update_draft(run_id="..")`` reached ``PATCH /api/experiments/{id}``,
#:   **a route that is not in** :data:`~.policy.OPERATIONS` **at all**. It was inert
#:   only because that route's body model happened to reject the payload with a
#:   ``422`` — an accident of two unrelated schemas, not a boundary.
#:
#: EVERY EXISTING REJECTION CASE MISSED IT, and that is the useful part.
#: ``test_the_client_refuses_a_path_parameter_it_would_have_had_to_escape`` and
#: ``test_a_path_parameter_cannot_be_bent_into_another_route`` between them try
#: ``../../etc/passwd``, ``abc/../../x``, ``%2e%2e%2f``, ``../export``,
#: ``..%2fexport``, ``x/../../export``, ``a b``, ``a\nb`` and ``""`` — and every
#: one of them fails on the ``/``, the ``%``, the space, the newline or the
#: emptiness. **Not one of them fails on the dot**, so a bare ``..`` walked
#: through a suite that looked like it was testing exactly this.
#:
#: THE SHAPE IS VERIFIED, NOT ASSUMED. Both placeholders this layer can render —
#: measured over every entry in :data:`~.policy.OPERATIONS`, which declares
#: ``experiment_id`` and ``run_id`` and no other — name ids that
#: ``isaac_records.ids.new_record_id`` minted, and ``workspace`` creates a run with
#: the same function it uses for a record. So this is the workspace's own
#: ``RECORD_ID_RE``, not an approximation of it.
#:
#: IT IS RESTATED RATHER THAN IMPORTED, AND THAT IS NOT AN OVERSIGHT.
#: ``test_nothing_in_the_mcp_package_imports_the_truth_path`` forbids this package
#: from importing ``isaac_records`` at all (``CLAUDE.md`` §13): the MCP layer
#: reaches ISAAC only through ISAAC's own HTTP routes, so that a tool can never
#: call a validator, an exporter or a writer around the route that decides whether
#: it may. Importing one regex would be a small breach of a boundary whose value is
#: that it has no small breaches. The copy is instead pinned to the original BY
#: TEST — ``test_mcp_path_parameters_are_record_ids.py`` asserts this pattern and
#: ``isaac_records.ids.RECORD_ID_RE`` accept and reject exactly the same strings —
#: which is the same trade every other deliberate duplicate in this repository
#: makes, and it is the one that keeps the drift visible in a diff.
#:
#: ``\A…\Z`` AND NOT ``^…$``, for the reason ``isaac_records.ids`` gives at length:
#: Python's ``$`` also matches immediately before a trailing newline, so ``^…$``
#: would admit a 27-character id ending in ``\n`` at the boundary whose whole job
#: is to decide what a path segment may contain.
#:
#: WHAT THIS DELIBERATELY DOES NOT DO. It does not touch the HTTP routes'
#: ``ExperimentId``, which stays a 128-character bound and answers ``404`` for a
#: well-formed id this workspace does not hold — an id-FORMAT check on a public
#: route is a product change, and ``routes._EXPERIMENT_ID_MAX_LENGTH``'s own note
#: says so. The MCP boundary is allowed to be strictly narrower than the API it
#: calls; that is what a boundary is for.
_PATH_PARAM = re.compile(r"\A[0-9A-Z]{26}\Z")

_PATH_PARAM_DESCRIPTION = "a 26-character Crockford-base32 record or run id"

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")

#: Request timeout for the in-process call. It cannot hit the network, but a route
#: that deadlocks must not hang an agent forever.
_TIMEOUT_SECONDS = 30.0


class ApiRefusal(Exception):
    """This client refused to make, or to interpret, a call. Never a route's 4xx.

    A route's own refusal (``404``, ``412``, ``422``) is a RESULT — it is the
    API answering — and comes back as an :class:`ApiResult` for the tool to
    report. This exception is for the calls that were never made.
    """

    def __init__(self, code: str, message: str, *, data: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = dict(data or {})


@dataclass(frozen=True)
class ApiResult:
    """One answered call: the status, the parsed body, and the ETag if there was one."""

    status: int
    body: Any
    etag: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class IsaacApiClient(Protocol):
    """The seam a tool sees. One method, and it cannot express a free-form request."""

    async def call(
        self,
        operation_id: str,
        *,
        path_params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        if_match: str | None = None,
    ) -> ApiResult: ...


@dataclass
class AsgiApiClient:
    """In-process ASGI client, hard-bound to :data:`~.policy.OPERATIONS`."""

    app: Any
    #: Written into ``X-Isaac-Tutorial-Session`` on every request. Comes from the
    #: principal; there is no argument by which a tool can change it.
    tutorial_session_id: str | None = None

    async def call(
        self,
        operation_id: str,
        *,
        path_params: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        if_match: str | None = None,
    ) -> ApiResult:
        operation = OPERATIONS.get(operation_id)
        if operation is None:
            raise ApiRefusal(
                "operation_not_allowlisted",
                f"{operation_id!r} is not an operation this server may call.",
                data={"operation_id": operation_id},
            )
        path = self._render_path(operation, path_params or {})
        params = self._render_query(operation, query or {})
        headers = self._render_headers(operation, if_match)

        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://isaac.invalid",
            timeout=_TIMEOUT_SECONDS,
        ) as http:
            response = await http.request(
                operation.method,
                path,
                params=params or None,
                json=dict(json_body) if json_body is not None else None,
                headers=headers,
            )

        if response.status_code == 401:
            raise ApiRefusal(
                "upstream_unauthenticated",
                "The ISAAC API refused this call as unauthenticated. The MCP layer "
                "deliberately does not hold the application's own API key: which "
                "credential an MCP caller presents is decision D2, which is "
                "outstanding (docs/mcp-capability-audit.md §3, §6).",
                data={"operation_id": operation_id},
            )
        return ApiResult(
            status=response.status_code,
            body=_parse(response),
            etag=response.headers.get("etag"),
        )

    # -- request construction, each step a refusal rather than a coercion ------

    def _render_path(self, operation: Operation, supplied: Mapping[str, str]) -> str:
        expected = set(_PLACEHOLDER.findall(operation.path_template))
        extra = set(supplied) - expected
        if extra:
            raise ApiRefusal(
                "unexpected_path_parameter",
                f"{operation.id!r} takes no path parameter(s) {sorted(extra)!r}.",
                data={"operation_id": operation.id, "unexpected": sorted(extra)},
            )
        rendered = operation.path_template
        for name in sorted(expected):
            value = supplied.get(name)
            if not isinstance(value, str) or not _PATH_PARAM.match(value):
                raise ApiRefusal(
                    "invalid_path_parameter",
                    f"{name!r} must be {_PATH_PARAM_DESCRIPTION} — 26 characters "
                    "from [0-9A-Z], and nothing else. `.` and `..` are refused "
                    "because they are path segments rather than id characters. The "
                    "value was refused before a request was built; it was not "
                    "escaped and retried.",
                    data={"operation_id": operation.id, "parameter": name},
                )
            rendered = rendered.replace("{" + name + "}", value)
        return f"{base_path()}{rendered}"

    def _render_query(
        self, operation: Operation, supplied: Mapping[str, Any]
    ) -> dict[str, Any]:
        unknown = set(supplied) - set(operation.query_parameters)
        if unknown:
            raise ApiRefusal(
                "unsupported_query_parameter",
                f"{operation.id!r} does not accept the query parameter(s) "
                f"{sorted(unknown)!r}. This API IGNORES unknown query parameters, so "
                "sending one would return an unfiltered result that looks filtered.",
                data={
                    "operation_id": operation.id,
                    "unsupported": sorted(unknown),
                    "supported": sorted(operation.query_parameters),
                },
            )
        rendered: dict[str, Any] = {}
        for name, value in supplied.items():
            if value is None:
                continue
            if isinstance(value, bool):
                rendered[name] = "true" if value else "false"
            elif isinstance(value, (int, str)):
                rendered[name] = value
            else:
                raise ApiRefusal(
                    "invalid_query_parameter",
                    f"{name!r} must be a string, integer or boolean.",
                    data={"operation_id": operation.id, "parameter": name},
                )
        return rendered

    def _render_headers(self, operation: Operation, if_match: str | None) -> dict[str, str]:
        headers = {"accept": "application/json"}
        if if_match is not None:
            if not isinstance(if_match, str) or not if_match.strip():
                raise ApiRefusal(
                    "invalid_if_match",
                    "if_match must be a non-empty string — the ETag a read returned.",
                    data={"operation_id": operation.id},
                )
            if "\n" in if_match or "\r" in if_match:
                raise ApiRefusal(
                    "invalid_if_match",
                    "if_match must not contain line breaks.",
                    data={"operation_id": operation.id},
                )
            # ── THE WILDCARD IS REFUSED HERE, AND THE HTTP API'S ACCEPTANCE OF IT IS
            # ── DELIBERATE AND UNCHANGED. ────────────────────────────────────────────
            # `If-Match: *` means "I have no validator; apply this iff the resource
            # exists" (RFC 9110). `routes._check_if_match` implements exactly that and
            # returns `None` for it, which is correct for an HTTP client that genuinely
            # has no validator and is documented in that function's own docstring. This
            # refusal does NOT change it and must not be read as a reason to.
            #
            # THIS LAYER MAKES A STRONGER PROMISE THAN HTTP DOES, and the promise was
            # measurably false. `policy._validated` REFUSES TO IMPORT if any mutating
            # operation lacks `requires_if_match` — "a lost update is not an acceptable
            # default" — and this module's `tools.py` states the resulting property to
            # the reader: "every write ... requires the If-Match precondition the API
            # already enforces — so an agent working from a stale read loses the race
            # rather than the scientist losing an edit." An independent security review
            # measured the hole on 2026-08-24: an agent holding a STALE ETag gets `412
            # stale_write`, and the identical call with `*` returns `200` and silently
            # overwrites an already-confirmed `measurement.series` correction, with no
            # conflict recorded anywhere. The import-time guard was satisfied by the
            # header being PRESENT; it cannot see what the header says.
            #
            # WHY IT MATTERS MORE HERE THAN OVER PLAIN HTTP. `*` is the canonical idiom
            # for "I have no validator", which is precisely the state a confused model
            # is in — and `if_match` is published to that model as an unconstrained
            # `{"type": "string", "minLength": 1, "maxLength": 256}`. A single character
            # is a shorter path out of a retry loop than re-reading the record, and the
            # agent is not the person whose edit is destroyed.
            #
            # ONLY THE BARE `*` IS TESTED, because only the bare `*` reaches the
            # wildcard branch: `routes._check_if_match` compares the STRIPPED header to
            # `"*"` exactly, and any list form (`"*,"`, `'*, "x.1"'`) falls through to
            # `_STRONG_TAG_RE` — `\A"[^"\\]+"\Z` — which `*` cannot match, so the HTTP
            # API already answers `400 malformed`. Refusing a wider shape here would be
            # guarding against something the server does not accept.
            if if_match.strip() == "*":
                raise ApiRefusal(
                    "invalid_if_match",
                    "if_match must be a validator a read returned — the `etag` from "
                    "isaac_get_experiment or isaac_get_run. `*` means \"apply this "
                    "whatever the record now says\", which would overwrite a change "
                    "made since your last read without reporting a conflict. This "
                    "server does not make blind writes on an agent's behalf: read the "
                    "record again and send the etag it returns.",
                    data={"operation_id": operation.id},
                )
            headers["if-match"] = if_match
        if self.tutorial_session_id is not None:
            headers["x-isaac-tutorial-session"] = self.tutorial_session_id
        return headers


def _parse(response: httpx.Response) -> Any:
    """The JSON body, or a fixed shape when there is not one.

    A non-JSON body is not interpolated into the result — an HTML error page from
    a middleware would otherwise reach a model as though it were data.
    """
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return {
            "error": "unparseable_response",
            "message": "The ISAAC API returned a body that is not JSON.",
        }
