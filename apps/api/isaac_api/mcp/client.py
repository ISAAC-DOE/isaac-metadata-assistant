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

#: Path-parameter character class. Deliberately narrow: ULIDs and the run ids this
#: application mints are alphanumeric, and the three extra characters are there so
#: a legitimate id shape change does not require a security review.
_PATH_PARAM = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")

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
                    f"{name!r} must be 1–128 characters from [A-Za-z0-9._~-]. The "
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
