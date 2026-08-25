"""``isaac_list_questions`` must expose the bounds its route has — and keep its default.

WHY THIS FILE EXISTS. ``GET /experiments/{id}/pending`` grew ``run_id``, ``offset`` and
``limit``; ``isaac_list_questions`` reaches that route and exposed **none** of them, so an
external agent working on ONE run of a large record had exactly one way to find that run's
questions: download the whole record's set and filter client-side. The scale envelope puts
that response at **1.78 MB at 1,000 runs**
(``docs/evidence/scale-envelope-2026-08-25.md`` §1). The route's own OpenAPI description
already told an HTTP client it could ask for less; the published MCP contract — a
SEPARATE document, read by agents that never see the OpenAPI — did not.

TWO THINGS ARE ASSERTED, AND THE SECOND IS THE ONE THAT KEEPS THE FIRST HONEST:

1. the three parameters are exposed, DERIVED from the route rather than transcribed, with
   the route's own bounds and its own descriptions, and the policy's query-parameter
   review gate covers them exactly as it covers ``list_runs``';
2. **the default did not move.** ``experiment_id`` alone still returns every open question
   with no ``pending_page`` block, and the tool description does not tell an agent its
   complete list is a window. Bounding is something a caller ASKS for; a tool that started
   truncating by default would be the silent truncation the bound exists to prevent, and a
   tool that CLAIMED to truncate when it does not would be the mirror-image lie.
"""

from __future__ import annotations

import inspect
import typing

import pytest

import isaac_api.routes as routes
from isaac_api.mcp import policy
from isaac_api.mcp.policy import OPERATIONS
from isaac_api.mcp.tools import TOOLS

from isaac_api.mcp.server import INVALID_PARAMS

from test_mcp_server import (  # the established MCP harness, reused rather than rebuilt
    app,  # noqa: F401 — fixture
    call,
    payload,
    rpc,
    reader,  # noqa: F401 — fixture
    session_id,  # noqa: F401 — fixture
    write_only,  # noqa: F401 — fixture
    writer,  # noqa: F401 — fixture
    denied,
)

#: The seed with open `series` and `descriptor` questions and nothing else.
PARTIAL_ID = "01SYNTHXANESSEED0000000002"
_BOUNDS = ("run_id", "offset", "limit")


# --- 1. the parameters are exposed, and DERIVED ---------------------------------


def test_the_tool_exposes_the_routes_own_bounding_parameters():
    schema = TOOLS["isaac_list_questions"].input_schema
    assert set(schema["properties"]) == {"experiment_id", *_BOUNDS}, schema["properties"]
    # ONLY the id is required. Every bound is optional because the route's default IS
    # the complete answer; a required `limit` would make paging mandatory.
    assert schema["required"] == ["experiment_id"]
    assert schema["additionalProperties"] is False

    assert schema["properties"]["run_id"]["type"] == "string"
    assert schema["properties"]["offset"] == {
        **schema["properties"]["offset"],
        "type": "integer",
        "minimum": 0,
    }
    assert schema["properties"]["limit"]["type"] == "integer"
    assert schema["properties"]["limit"]["minimum"] == 1
    # The CEILING travels, so the tool refuses a page size the route would 422 rather
    # than forwarding it and letting a model read the refusal as "no questions matched".
    assert schema["properties"]["limit"]["maximum"] == routes.PENDING_PAGE_MAX


def test_the_parameter_set_is_read_off_the_route_and_not_transcribed():
    """THE ANTI-DRIFT PROPERTY, asserted against ``inspect`` rather than against a list.

    A transcribed set is a second copy free to drift, and FastAPI IGNORES unknown query
    parameters — so a tool advertising a parameter the route lost would keep succeeding
    while silently returning an unfiltered result, which is a tool lying about what it
    did. The set must equal what the route's signature actually declares.
    """
    hints = typing.get_type_hints(routes.get_pending, include_extras=True)
    declared = set()
    for name, parameter in inspect.signature(routes.get_pending).parameters.items():
        annotation = hints.get(name, parameter.annotation)
        if not hasattr(annotation, "__metadata__"):
            continue
        _base, *metadata = typing.get_args(annotation)
        if any(type(m).__name__ == "Query" for m in metadata):
            declared.add(name)

    assert declared == set(_BOUNDS), declared
    assert {p.name for p in policy.pending_query_parameters()} == declared
    assert OPERATIONS["list_questions"].query_parameters == frozenset(declared)


def test_the_descriptions_are_the_routes_own_words():
    """Not paraphrased. The route's description is the reviewed sentence, and an agent
    reading the tool schema must be reading the same statement an HTTP client reads."""
    schema = TOOLS["isaac_list_questions"].input_schema
    assert schema["properties"]["run_id"]["description"] == routes._PENDING_RUN_ID_DESC
    assert schema["properties"]["offset"]["description"] == routes._PENDING_OFFSET_DESC
    assert schema["properties"]["limit"]["description"] == routes._PENDING_LIMIT_DESC


def test_the_review_gate_covers_the_pending_route_too(monkeypatch):
    """THE GATE, and it is the reason this is derived at all.

    A parameter the route grows that has NOT been reviewed must raise at import-time
    rather than be exposed. Asserted by narrowing the allowlist, which is the only way to
    exercise the refusal without inventing a route parameter — and it proves the gate is
    load-bearing rather than a set that happens to contain everything.
    """
    monkeypatch.setattr(policy, "PENDING_QUERY_ALLOWLIST", frozenset({"offset", "limit"}))
    with pytest.raises(RuntimeError) as excinfo:
        policy.pending_query_parameters()
    assert "run_id" in str(excinfo.value)
    assert "pending-list" in str(excinfo.value)


def test_q_is_not_pre_approved_for_the_pending_route():
    """The run-list allowlist pre-approves ``q`` because that route is gaining it. The
    pending allowlist deliberately does NOT: a free-text selector over question text is a
    different decision from paging, and pre-approving it would let it ship unreviewed."""
    assert policy.PENDING_QUERY_ALLOWLIST == frozenset({"run_id", "offset", "limit"})
    assert "q" not in policy.PENDING_QUERY_ALLOWLIST
    assert "q" in policy.RUN_LIST_QUERY_ALLOWLIST


def test_an_unsupported_query_parameter_is_refused_before_a_request_is_built(reader):
    """``additionalProperties: false`` is the first gate and the client's own
    ``_render_query`` is the second. Either way the call never reaches the route, because
    the route would IGNORE the unknown parameter and answer as if it had been honoured.

    It surfaces as a JSON-RPC ``INVALID_PARAMS`` rather than an ``isError`` result, which
    is the stronger of the two: the argument never became a tool call at all.
    """
    envelope = rpc(
        reader,
        "tools/call",
        {
            "name": "isaac_list_questions",
            "arguments": {"experiment_id": PARTIAL_ID, "q": "spectrum"},
        },
    )
    assert envelope.get("error", {}).get("code") == INVALID_PARAMS, envelope


# --- 2. the default did not move ------------------------------------------------


def test_sending_only_the_id_still_answers_completely_with_no_page_block(writer):
    """THE DEFAULT, unchanged. One `pending` key, the whole set, nothing new to
    interpret — which is the entire point of leaving it alone."""
    data = payload(writer, "isaac_list_questions", experiment_id=PARTIAL_ID)["data"]
    assert {q["id"] for q in data["pending"]} == {"series", "descriptor"}
    assert "pending_page" not in data, data.get("pending_page")


def test_the_tool_does_not_tell_an_agent_its_complete_list_is_a_window():
    """THE NEGATIVE CONTROL. ``_BOUNDED_PENDING_NOTE``'s marker belongs to the four
    operations whose responses ARE windowed whether the caller asked or not. This tool's
    default is complete, so carrying that sentence would be a false claim — and would
    make the sentence meaningless by making it universal."""
    description = TOOLS["isaac_list_questions"].description
    assert "IS A WINDOW, NOT THE RECORD'S WHOLE SET" not in description
    # …while still telling the agent the bounds exist and how to read a page it asked for.
    for name in _BOUNDS:
        assert f"`{name}`" in description, name
    assert "pending_page" in description
    assert "record_total" in description


# --- 3. the bounds actually work, end to end ------------------------------------


def _run_ids(writer, experiment_id: str) -> list[str]:
    rows = payload(writer, "isaac_list_runs", experiment_id=experiment_id)["data"]["runs"]
    return [r["id"] for r in rows]


def _with_two_runs(writer) -> tuple[str, list[str]]:
    for label in ("Run A", "Run B"):
        payload(
            writer,
            "isaac_create_run",
            experiment_id=PARTIAL_ID,
            if_match=payload(writer, "isaac_get_experiment", experiment_id=PARTIAL_ID)[
                "etag"
            ],
            label=label,
        )
    return PARTIAL_ID, _run_ids(writer, PARTIAL_ID)


def test_a_run_filter_returns_that_runs_questions_and_still_reports_the_record(writer):
    """THE CAPABILITY. And the second assertion is the safety half: a filtered read
    reports the WHOLE record's open count, so it can never be mistaken for the record's
    state."""
    experiment_id, run_ids = _with_two_runs(writer)
    whole = payload(writer, "isaac_list_questions", experiment_id=experiment_id)["data"]
    filtered = payload(
        writer, "isaac_list_questions", experiment_id=experiment_id, run_id=run_ids[0]
    )["data"]

    assert {q["run_id"] for q in filtered["pending"]} == {run_ids[0]}
    assert len(filtered["pending"]) < len(whole["pending"])
    assert filtered["pending_page"]["record_total"] == len(whole["pending"])
    assert filtered["pending_page"]["complete"] is True


def test_a_limit_returns_a_page_that_states_what_it_withheld(writer):
    experiment_id, _run_ids = _with_two_runs(writer)
    whole = payload(writer, "isaac_list_questions", experiment_id=experiment_id)["data"]
    page = payload(
        writer, "isaac_list_questions", experiment_id=experiment_id, limit=1
    )["data"]

    assert len(page["pending"]) == 1
    assert page["pending_page"]["total"] == len(whole["pending"])
    assert page["pending_page"]["returned"] == 1
    assert page["pending_page"]["withheld"] == len(whole["pending"]) - 1
    assert page["pending_page"]["complete"] is False


def test_paging_reaches_every_question_exactly_once(writer):
    experiment_id, _run_ids = _with_two_runs(writer)
    whole = payload(writer, "isaac_list_questions", experiment_id=experiment_id)["data"]
    seen: list[tuple] = []
    total = len(whole["pending"])
    # A BOUNDED loop rather than `while True`: the termination condition is the thing
    # under test, so a walk that never terminated would hang the suite instead of
    # failing it.
    for offset in range(0, total + 2, 2):
        page = payload(
            writer,
            "isaac_list_questions",
            experiment_id=experiment_id,
            offset=offset,
            limit=2,
        )["data"]
        seen.extend((q.get("run_id"), q["id"]) for q in page["pending"])
        if page["pending_page"]["withheld"] == 0:
            break
    else:  # pragma: no cover - the loop above must break
        raise AssertionError("paging never reported the set exhausted")
    assert seen == [(q.get("run_id"), q["id"]) for q in whole["pending"]]
    assert len(seen) == len(set(seen))


def test_an_unknown_run_is_refused_rather_than_answered_with_an_empty_list(reader):
    """A filter that silently matched nothing would let an agent read ``total: 0`` as
    "this run has no open questions". The route refuses; the refusal must surface."""
    result = call(
        reader, "isaac_list_questions", experiment_id=PARTIAL_ID, run_id="01NOSUCHRUN"
    )
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 404, result["structuredContent"]


def test_a_limit_over_the_routes_ceiling_never_leaves_the_client(reader):
    """The ceiling is in the schema, so the refusal happens HERE — no request is built and
    the route's 422 never has to be interpreted by a model."""
    envelope = rpc(
        reader,
        "tools/call",
        {
            "name": "isaac_list_questions",
            "arguments": {
                "experiment_id": PARTIAL_ID,
                "limit": routes.PENDING_PAGE_MAX + 1,
            },
        },
    )
    assert envelope.get("error", {}).get("code") == INVALID_PARAMS, envelope
    assert "500" in envelope["error"]["message"], envelope["error"]


def test_the_bounded_read_is_still_denied_to_a_write_only_caller(write_only):
    """The bounds are not a way around the scope check."""
    denied(write_only, "isaac_list_questions", experiment_id=PARTIAL_ID, limit=1)
