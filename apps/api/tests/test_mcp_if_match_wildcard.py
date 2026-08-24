"""``If-Match: *`` through MCP was a real lost update. This pins the refusal.

THE DEFECT, measured by an independent security review on 2026-08-24.

``mcp/policy.py`` refuses to IMPORT if any mutating operation lacks
``requires_if_match`` — *"a lost update is not an acceptable default"* — and
``mcp/tools.py``'s own header states the property that guard is supposed to buy:
*"every one requires the ``If-Match`` precondition the API already enforces — so an
agent working from a stale read loses the race rather than the scientist losing an
edit."* Both were satisfied by the header being PRESENT. Neither can see what it says.

``client._render_headers`` rejected only an empty/whitespace value and a CRLF
injection, so ``*`` passed. Over HTTP that is correct and deliberate — RFC 9110 says
``*`` matches iff the resource exists, and ``routes._check_if_match`` implements
exactly that, with a docstring saying so. The consequence at the MCP layer was
measured end to end: an agent holding a STALE etag is refused with ``412
stale_write``, and the identical call with ``*`` returns ``200`` and silently
overwrites an already-confirmed value, with no conflict recorded anywhere.

WHY THIS LAYER AND NOT THE HTTP LAYER. ``*`` is the canonical idiom for "I have no
validator", which is precisely the state a confused model is in — and ``if_match`` is
published to that model as an unconstrained ``{"type": "string", "minLength": 1,
"maxLength": 256}``. One character is a shorter path out of a retry loop than
re-reading the record, and the agent is not the person whose edit is destroyed. The
MCP layer makes the stronger promise, so the MCP layer keeps it.

WHAT THIS FILE DELIBERATELY ALSO PINS: that the HTTP API's acceptance of ``If-Match:
*`` did NOT change. A fix that "tightened" both would be a silent contract change to
a documented, deliberate behaviour, and would not be discoverable from the MCP tests
alone — so the negative control lives here, beside the refusal it constrains.

Nothing here opens a network connection, reads real data, or touches a database.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from isaac_api.mcp.client import ApiRefusal, AsgiApiClient
from isaac_api.mcp.policy import OPERATIONS
from isaac_api.mcp.tools import TOOLS

#: A synthetic id of the shape the path parameter accepts. It does not have to
#: resolve: the wildcard refusal is raised while the request is being CONSTRUCTED, so
#: no request is issued and no record is consulted. Using a real id would make these
#: cases depend on a seeded workspace for no added strength.
_ID = "01SYNTHXANESSEED0000000001"
_RUN_ID = "01SYNTHXANESRUN00000000001"

#: EVERY MUTATING OPERATION, with the path parameters its template declares. There are
#: six across the three tools that publish ``if_match`` — ``isaac_update_draft`` and
#: ``isaac_answer_questions`` each drive several, choosing by whether ``run_id`` was
#: given — so parametrising over TOOLS would have exercised three of six paths while
#: reading as though it covered them all.
#: :func:`test_every_mutating_operation_is_covered_by_this_file` derives the set from
#: the policy registry and asserts this tuple equals it.
_WILDCARD_CASES = (
    ("create_run", {"experiment_id": _ID}),
    ("update_run_draft", {"experiment_id": _ID, "run_id": _RUN_ID}),
    ("correct_record_field", {"experiment_id": _ID}),
    ("answer_record_question", {"experiment_id": _ID}),
    ("answer_run_question", {"experiment_id": _ID, "run_id": _RUN_ID}),
    ("correct_run_field", {"experiment_id": _ID, "run_id": _RUN_ID}),
)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return create_app()


# ==========================================================================
# 1. the refusal
# ==========================================================================

@pytest.mark.parametrize("operation_id,path_params", _WILDCARD_CASES)
def test_the_client_refuses_the_if_match_wildcard(app, operation_id, path_params):
    """BEFORE THE FIX every one of these built a request carrying ``if-match: *`` and
    issued it; against a record that exists, that is the ``200``-and-overwrite the
    review measured.

    These cases assert the REFUSAL rather than the overwrite, and the ids are
    deliberately synthetic: the refusal is raised while the request is being
    CONSTRUCTED, so nothing is issued and no record is consulted. The
    write-actually-happens half is what
    :func:`test_a_real_etag_still_writes_and_a_stale_one_still_loses_the_race` drives
    against a real record — this is the same placement every other ``_render_*``
    refusal uses, and the reason the message can say "nothing was written" without
    needing to prove a rollback.
    """
    client = AsgiApiClient(app)
    with pytest.raises(ApiRefusal) as raised:
        asyncio.run(client.call(operation_id, path_params=path_params, if_match="*"))
    assert raised.value.code == "invalid_if_match"
    assert raised.value.data["operation_id"] == operation_id


@pytest.mark.parametrize("surrounded", (" * ", "\t*", "*\t"))
def test_whitespace_does_not_smuggle_the_wildcard_past_the_refusal(app, surrounded):
    """``routes._check_if_match`` STRIPS before comparing, so ``" * "`` is the
    wildcard to the server. A refusal that compared the raw string would refuse the
    bare form and pass the padded one, which is worse than not refusing at all: the
    test would be green and the hole would be one space wide.
    """
    client = AsgiApiClient(app)
    with pytest.raises(ApiRefusal) as raised:
        asyncio.run(
            client.call(
                "create_run",
                path_params={"experiment_id": _ID},
                if_match=surrounded,
            )
        )
    assert raised.value.code == "invalid_if_match"


def test_the_refusal_says_what_a_valid_value_IS_and_why_the_wildcard_is_not_one(app):
    """A refusal a model cannot act on sends it looking for a different bypass.

    So the message names the operations that produce a valid value and states the
    consequence in the scientist's terms rather than in HTTP's. It deliberately does
    NOT say "use a strong validator", which is true and useless to the caller.
    """
    client = AsgiApiClient(app)
    with pytest.raises(ApiRefusal) as raised:
        asyncio.run(
            client.call(
                "correct_record_field",
                path_params={"experiment_id": _ID},
                if_match="*",
                json_body={"confirmed_by_user": True, "answers": {"edge": "L3"}},
            )
        )
    message = raised.value.message
    assert "isaac_get_experiment" in message
    assert "conflict" in message
    assert "blind writes" in message


# ==========================================================================
# 2. the refusal is NARROW: a real validator still works, a stale one still 412s
# ==========================================================================

def test_a_real_etag_still_writes_and_a_stale_one_still_loses_the_race(app):
    """THE CONTROL THAT MAKES THE REFUSAL MEAN SOMETHING.

    A guard that refused every ``if_match`` would pass the test above and break the
    server. This drives the ordinary path end to end through the same client: read
    the record, write with the etag it returned (accepted), then replay the now-stale
    etag (``412 stale_write``). That second outcome is the behaviour the wildcard was
    letting a caller skip, so it is asserted here rather than assumed.
    """
    http = TestClient(app)
    created = http.post("/api/experiments", json={"title": "wildcard control"})
    assert created.status_code == 201, created.text
    experiment_id = created.json()["id"]

    client = AsgiApiClient(app)
    read = asyncio.run(
        client.call("get_experiment", path_params={"experiment_id": experiment_id})
    )
    etag = read.etag
    assert etag, read.body

    accepted = asyncio.run(
        client.call(
            "create_run",
            path_params={"experiment_id": experiment_id},
            if_match=etag,
            json_body={"label": "Run A"},
        )
    )
    assert accepted.status == 201, accepted.body

    stale = asyncio.run(
        client.call(
            "create_run",
            path_params={"experiment_id": experiment_id},
            if_match=etag,
            json_body={"label": "Run B"},
        )
    )
    assert stale.status == 412, stale.body
    assert stale.body["error"] == "stale_write"


# ==========================================================================
# 3. the HTTP API is UNCHANGED — this is the half a future "cleanup" would break
# ==========================================================================

def test_the_HTTP_api_still_accepts_the_wildcard_because_that_is_deliberate(app):
    """``routes._check_if_match``'s docstring documents ``*`` -> proceed, and RFC 9110
    defines it as "matches iff the resource exists". That is a correct answer to an
    HTTP client that genuinely has no validator, and this fix does not touch it.

    It is pinned HERE, next to the MCP refusal, because that is where somebody would
    later "make the two consistent" — and consistency in that direction is a silent
    change to a documented API contract that the MCP tests would applaud.
    """
    http = TestClient(app)
    created = http.post("/api/experiments", json={"title": "http wildcard"})
    assert created.status_code == 201, created.text
    experiment_id = created.json()["id"]

    accepted = http.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": "Run A"},
        headers={"If-Match": "*"},
    )
    assert accepted.status_code == 201, accepted.text


# ==========================================================================
# 4. the published contract says so
# ==========================================================================

def _if_match_descriptions() -> dict[str, str]:
    out: dict[str, str] = {}
    for name, tool in TOOLS.items():
        prop = (tool.input_schema.get("properties") or {}).get("if_match")
        if prop is not None:
            out[name] = prop.get("description", "")
    return out


def test_every_tool_that_declares_if_match_says_the_wildcard_is_refused():
    """THE ARGUMENT DESCRIPTION IS THE ONLY PART OF THIS A MODEL READS BEFORE CALLING.

    The schema is ``{"type": "string", "minLength": 1, "maxLength": 256}`` — nothing
    in it can express "must be a validator a read returned", and JSON Schema has no
    way to say it. So the contract has to be prose, and the prose has to be on every
    tool that takes the argument: a model that reads one tool's description does not
    thereby read another's.
    """
    descriptions = _if_match_descriptions()
    assert set(descriptions) == {
        "isaac_create_run",
        "isaac_update_draft",
        "isaac_answer_questions",
    }, sorted(descriptions)
    for name, text in descriptions.items():
        assert "`*` is refused" in text, (name, text)
        assert "conflict" in text, (name, text)


def test_every_mutating_operation_is_covered_by_this_file():
    """THE COVERAGE IS DERIVED, NOT COUNTED.

    ``policy._validated`` already guarantees every mutating operation declares
    ``requires_if_match``; this asserts that the set of such operations is exactly the
    set this file exercises. A fourth write added later turns THIS red rather than
    shipping with an unguarded wildcard and a green suite — which is the same remedy
    ``tools.py``'s own header adopted after a hand-maintained tally drifted.
    """
    mutating = {op.id for op in OPERATIONS.values() if op.mutates}
    assert mutating == {case[0] for case in _WILDCARD_CASES}, sorted(mutating)


def test_the_three_tools_that_publish_if_match_drive_exactly_those_operations():
    """THE OTHER HALF OF THE COVERAGE CLAIM, and the one that caught this file's own
    first draft.

    That draft parametrised over three cases named after the TOOLS and asserted they
    equalled the mutating-operation set; the sets were three and six, and the file read
    as though it covered every write while exercising half of them. Tools are not
    operations here: ``isaac_update_draft`` and ``isaac_answer_questions`` each dispatch
    to several, choosing by whether ``run_id`` was supplied.
    """
    published = {
        op_id
        for tool in TOOLS.values()
        if (tool.input_schema.get("properties") or {}).get("if_match")
        for op_id in tool.operation_ids
    }
    assert published == {op.id for op in OPERATIONS.values() if op.mutates}
