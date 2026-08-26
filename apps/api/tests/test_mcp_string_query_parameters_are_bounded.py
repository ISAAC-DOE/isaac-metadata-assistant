"""No MCP tool may publish an UNBOUNDED string query parameter.

**THE DEFECT, MEASURED RATHER THAN REASONED ABOUT.** ``tools._query_schema`` builds the
gated tools' schemas from ``policy.QueryParameter``, which carried ``minimum`` and
``maximum`` and **not** ``max_length``. So every string parameter it produced was
published with no ``maxLength``, ``validate_arguments`` had nothing to check, and the
value was forwarded verbatim:

* ``isaac_list_runs``' ``q`` — bounded by its OWN route at ``RUN_QUERY_MAX`` — was
  advertised as unbounded, so a value the route refuses with ``422`` was accepted by the
  tool and spent a round trip to find that out;
* ``isaac_list_questions``' ``run_id`` — whose route declares no bound at all — accepted
  a 60 KB value, which came back inside the ``404 run_not_found`` body; past ~64 KB URL
  construction failed as an unhandled internal error rather than as a refusal.

**THE FIX IS DERIVATION FIRST AND A NAMED EXCEPTION SECOND, AND IT ADDS NO VALIDATION TO
ANY HTTP ROUTE.** ``QueryParameter`` now carries the route's ``max_length`` (``q`` -> 200,
from the route). ``run_id`` has none to carry, so it takes the bound this server ALREADY
publishes for the same identifier as a path parameter — ``_RUN_ID``'s 128, which
``client._render_path`` independently enforces there — declared in
``tools._DECLARED_STRING_BOUNDS``. A future string parameter with neither is a
``RuntimeError`` at schema-build time, not a quietly unbounded schema.

Changing ``GET /pending``'s own validation is a product change and is deliberately NOT
made: over HTTP a long ``run_id`` still answers ``404`` exactly as it did.
"""

from __future__ import annotations

import pytest

import isaac_api.routes as routes
from isaac_api.mcp import policy, tools
from isaac_api.mcp.server import INVALID_PARAMS
from isaac_api.mcp.tools import TOOLS

from test_mcp_server import (  # the established MCP harness, reused rather than rebuilt
    app,  # noqa: F401 — fixture
    payload,
    rpc,
    reader,  # noqa: F401 — fixture
    session_id,  # noqa: F401 — fixture
    write_only,  # noqa: F401 — fixture
    writer,  # noqa: F401 — fixture
)

PARTIAL_ID = "01SYNTHXANESSEED0000000002"


def _string_properties():
    """``(tool, name, spec)`` for every string property of every published tool."""
    for tool in TOOLS.values():
        for name, spec in tool.input_schema.get("properties", {}).items():
            if spec.get("type") == "string":
                yield tool.name, name, spec


def test_every_published_string_argument_carries_a_length_bound():
    """THE INVARIANT, over the WHOLE published surface rather than the two tools that
    were wrong.

    A per-tool assertion would have passed on the day the defect shipped — the schemas
    that were unbounded were built by a shared helper nobody was asserting over. Anything
    with a closed ``enum`` is exempt by construction: its longest member is its bound.
    """
    unbounded = [
        (tool, name)
        for tool, name, spec in _string_properties()
        if "maxLength" not in spec and "enum" not in spec
    ]
    assert not unbounded, unbounded


def test_the_bound_on_q_is_the_ROUTES_bound_rather_than_a_transcribed_number():
    """DERIVED, not copied. ``RUN_QUERY_MAX`` is read off the route module, so this fails
    the day the route moves its bound and the schema does not follow — which is the whole
    reason the derivation exists instead of a literal."""
    spec = TOOLS["isaac_list_runs"].input_schema["properties"]["q"]
    assert spec["maxLength"] == routes.RUN_QUERY_MAX
    assert any(
        p.name == "q" and p.max_length == routes.RUN_QUERY_MAX
        for p in policy.run_list_query_parameters()
    )


def test_run_ids_bound_is_the_one_this_server_already_publishes_for_a_run_id():
    """THE DECLARED BOUND IS NOT A NEW NUMBER. ``run_id`` is a PATH parameter in other
    tools, where it is ``_RUN_ID`` at 128; this asserts the query-parameter copy is the
    SAME object's bound rather than a second number that can drift from it."""
    spec = TOOLS["isaac_list_questions"].input_schema["properties"]["run_id"]
    assert spec["maxLength"] == tools._RUN_ID["maxLength"] == 128
    assert TOOLS["isaac_check_run"].input_schema["properties"]["run_id"]["maxLength"] == 128
    # …and it is genuinely absent from the ROUTE, which is why the declared map exists.
    assert all(
        p.max_length is None for p in policy.pending_query_parameters() if p.name == "run_id"
    )


def test_an_oversized_run_id_is_refused_before_a_request_is_built(reader):
    """OVER THE WIRE, because the schema is only a claim until the server enforces it.

    ``INVALID_PARAMS`` rather than an ``isError`` result is the stronger outcome: the
    argument never became a tool call, so nothing was forwarded and nothing was echoed.
    """
    envelope = rpc(
        reader,
        "tools/call",
        {
            "name": "isaac_list_questions",
            "arguments": {"experiment_id": PARTIAL_ID, "run_id": "x" * 129},
        },
    )
    assert envelope.get("error", {}).get("code") == INVALID_PARAMS, envelope
    assert "128" in envelope["error"]["message"], envelope["error"]


def test_an_oversized_q_is_refused_before_a_request_is_built(reader):
    envelope = rpc(
        reader,
        "tools/call",
        {
            "name": "isaac_list_runs",
            "arguments": {"experiment_id": PARTIAL_ID, "q": "x" * (routes.RUN_QUERY_MAX + 1)},
        },
    )
    assert envelope.get("error", {}).get("code") == INVALID_PARAMS, envelope


def test_a_run_id_at_the_bound_is_still_accepted(reader):
    """THE NEGATIVE CONTROL, and it is not decoration: a bound that refuses everything
    would pass every assertion above. A 128-character run id no record holds must reach
    the route and come back as the route's own ``404``, not as a schema refusal."""
    envelope = rpc(
        reader,
        "tools/call",
        {
            "name": "isaac_list_questions",
            "arguments": {"experiment_id": PARTIAL_ID, "run_id": "x" * 128},
        },
    )
    assert "error" not in envelope, envelope["error"]
    structured = envelope["result"]["structuredContent"]
    assert structured["status"] == 404, structured
    assert structured["error"] == "run_not_found", structured


def test_a_string_parameter_with_no_bound_anywhere_is_a_refusal_not_a_schema():
    """THE FAIL-CLOSED HALF, exercised rather than asserted about.

    The failure being closed here was SILENT — an unbounded schema looks exactly like a
    bounded one to everything except a large value — so the replacement must be loud. A
    synthetic ``QueryParameter`` with no route bound and no declared one is fed to the
    real builder; it must raise, and the message must name the parameter and both
    remedies.
    """
    invented = policy.QueryParameter(
        name="not_a_real_parameter", json_type="string", description="synthetic"
    )
    with pytest.raises(RuntimeError) as excinfo:
        tools._query_schema([invented])
    assert "not_a_real_parameter" in str(excinfo.value)
    assert "_DECLARED_STRING_BOUNDS" in str(excinfo.value)

    # …and the same parameter WITH a route bound builds fine, so the refusal is about the
    # missing bound and not about the parameter being unfamiliar.
    bounded = policy.QueryParameter(
        name="not_a_real_parameter",
        json_type="string",
        description="synthetic",
        max_length=7,
    )
    schema = tools._query_schema([bounded])
    assert schema["properties"]["not_a_real_parameter"]["maxLength"] == 7


def test_a_closed_set_needs_no_length_bound(reader):
    """``overrides`` is a ``Literal``, so it is exempt BY CONSTRUCTION rather than by
    being listed — and it must still work. If the exemption were removed, the schema build
    would raise at import and every MCP test would fail, so this pins the exemption's
    existence; the call pins that it did not become unusable."""
    spec = TOOLS["isaac_list_runs"].input_schema["properties"]["overrides"]
    assert spec["enum"] == ["any", "none"] and "maxLength" not in spec
    result = payload(reader, "isaac_list_runs", experiment_id=PARTIAL_ID, overrides="none")
    assert result["status"] == 200, result


def test_the_http_route_is_unchanged(client_over_http):
    """WHAT WAS DELIBERATELY NOT DONE. Adding validation to ``GET /pending`` is a product
    change and is not authorised here, so a long ``run_id`` must still be the route's own
    ``404`` — the MCP boundary got a bound; the HTTP route did not."""
    response = client_over_http.get(
        f"/api/experiments/{PARTIAL_ID}/pending", params={"run_id": "x" * 4096}
    )
    assert response.status_code == 404, response.status_code
    assert response.json()["error"] == "run_not_found", response.json()


@pytest.fixture()
def client_over_http(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app
    from conftest import tutorial_client

    return tutorial_client(create_app())


# --- the reader itself, at the seam a FastAPI upgrade moves -------------------


def test_the_bound_reader_takes_an_int_from_either_source_and_a_sentinel_from_neither():
    """`_max_length` must find an ``int``, not "the first non-``None``".

    RAISED BY INDEPENDENT REVIEW, and it is a live upgrade hazard rather than a
    hypothetical. On the installed FastAPI the bound exists ONLY as an
    ``annotated_types.MaxLen`` in ``Query.metadata``; ``Query(max_length=200)`` has no
    ``max_length`` attribute at all, so the legacy branch is unreachable today and
    nothing else exercises it. A version that parks a SENTINEL in that attribute would
    have satisfied a ``found is None`` guard, stopped the metadata scan before it
    started, reported NO bound, and — because `_query_schema` is fail-closed — taken
    `create_app()` down at import for every MCP deployment. Requiring an ``int`` makes
    a sentinel simply not a bound.

    ``bool`` is excluded explicitly: ``isinstance(True, int)`` is ``True`` in Python,
    and ``maxLength: 1`` published from a flag would be a silent refusal of every real
    value rather than a loud one.
    """
    from isaac_api.mcp.policy import _max_length

    class _Sentinel:
        pass

    def _q(**attrs):
        return type("Q", (), attrs)()

    def _meta(value):
        return [type("MaxLen", (), {"max_length": value})()]

    assert _max_length(_q(metadata=_meta(200))) == 200, "modern metadata form"
    assert _max_length(_q(max_length=200, metadata=())) == 200, "legacy attribute form"
    assert _max_length(_q(max_length=_Sentinel(), metadata=_meta(200))) == 200, (
        "a sentinel in the attribute must not mask a real bound in the metadata"
    )
    assert _max_length(_q(max_length=True, metadata=())) is None, "a bool is not a bound"
    assert _max_length(_q()) is None, "absent from both is absent"
