"""A ~1,000-deep request body crashed the ``422`` handler, before any route ran.

THE DEFECT, AND WHERE IT ACTUALLY WAS
=====================================
A body of ~1,000-deep nested JSON returned an unhandled **500** on most POSTs in
this application, ``POST .../discard`` among them. The crash was in none of them.
Traceback, measured::

    fastapi/exception_handlers.py:25  request_validation_exception_handler
    fastapi/encoders.py:322           jsonable_encoder
    ...                               (recursing)
    RecursionError: maximum recursion depth exceeded

FastAPI's default ``RequestValidationError`` handler renders the ``422`` by
calling ``jsonable_encoder`` over ``exc.errors()``, and every error echoes the
offending ``input`` back to the caller. ``jsonable_encoder`` recurses once per
level. **So the handler that exists to refuse a bad body was destroyed by it**, and
the route function was never entered.

SEVERITY, STATED PRECISELY, BECAUSE THE TWO HALVES HAVE DIFFERENT REMEDIES
==========================================================================
This is **error-shape and availability, not integrity.** The record survives at
every depth — asserted below at 50, 200, 500, 1,000 and 2,000 — because nothing
reaches a handler. What the caller loses is the typed refusal: a ``500`` with no
``detail`` says "this server is broken", where the truth is "your body is not one
this operation accepts", and it says it on a path where an operator would then go
looking for a defect in the route.

The shape matters and is asserted in §1: it is only reachable when the body FAILS
validation, because that is what makes the framework echo it. A deep value inside
a body that VALIDATES never enters this path at all — measured, and asserted, so
nobody later "fixes" a crash that was never there.

WHAT THE FIX BOUNDS, AND WHAT IT DELIBERATELY DOES NOT
======================================================
It bounds what is **echoed**, never what is **accepted**. An error whose ``input``
is deeper than ``_MAX_ECHOED_BODY_DEPTH`` has that member — and only that member —
replaced by a marker. ``type``, ``loc``, ``msg`` and ``url`` are untouched, so the
caller still learns which validator refused and where.

For every other request the handler is **byte-identical to FastAPI's default**,
which is what lets it be registered application-wide without renegotiating the
``422`` contract of ~70 operations. §2 asserts that byte-identity directly against
the framework's own handler rather than trusting it, because "identical except
when…" is exactly the kind of claim that is published unchecked.

IT REUSES THE EXISTING DEPTH PREDICATE
=======================================
``routes._value_depth_within`` already exists, is already the application's depth
guard (``_is_storable_value``, the ``/answers`` and ``/edit`` screens), and is
ITERATIVE on purpose — "a guard that crashes on the attack it guards against is not
a guard", as its own docstring puts it. That is what makes it usable here, where a
recursive depth check would merely move the crash one function earlier. A second
depth predicate was not added.

The LIMIT is a second number, and that is deliberate rather than sloppy:
``_MAX_VALUE_DEPTH``'s own docstring says *"IF THIS GUARD IS EVER REUSED FOR
ANOTHER FIELD SET, re-derive it"* — it is headroom for five run-level scalars,
whereas this bounds a whole request BODY, which legitimately wraps such a value in
one or two more containers. §3 pins the derivation at both ends.
"""

from __future__ import annotations

import copy

import pytest

import isaac_api.workspace as ws
from isaac_api.routes import _MAX_ECHOED_BODY_DEPTH, _MAX_VALUE_DEPTH

#: Comfortably past the measured crash floor of 972.
CRASHING_DEPTH = 1200


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    return ws


@pytest.fixture()
def client(workspace):
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _make(experiment_id: str):
    exp = ws.create_experiment(
        "Deep-body fixture",
        {"kind": "synthetic"},
        copy.deepcopy(ws._full_draft()),
        id=experiment_id,
    )
    exp.save_versioned()
    return exp


def _nested(depth: int) -> str:
    return "[" * depth + "1" + "]" * depth


def _etag(client, experiment_id: str) -> str:
    return client.get(f"/api/experiments/{experiment_id}").headers["ETag"]


def _post_raw(client, experiment_id: str, raw_body: str):
    return client.post(
        f"/api/experiments/{experiment_id}/discard",
        content=raw_body,
        headers={
            "If-Match": _etag(client, experiment_id),
            "content-type": "application/json",
        },
    )


# =============================================================================
# 1. The refusal is typed, at every depth, and the record survives
# =============================================================================


@pytest.mark.parametrize("depth", [50, 200, 500, 1000, 2000])
def test_a_deeply_nested_body_is_a_TYPED_422_and_never_a_500(client, depth):
    """The headline. ``1000`` and ``2000`` returned an unhandled ``500`` before."""
    experiment_id = f"01DEEPBODY{depth:016d}"[:26]
    _make(experiment_id)

    response = _post_raw(client, experiment_id, _nested(depth))

    assert response.status_code == 422, response.text
    assert "detail" in response.json(), response.text
    # And the record is untouched — this was never an integrity defect.
    assert ws.load_experiment(experiment_id) is not None


def test_the_refusal_still_says_WHICH_validator_refused_and_WHERE(client):
    """Redaction must not have cost the caller the information they need.

    Only ``input`` is replaced. ``type``, ``loc`` and ``msg`` survive, so the
    remedy is still legible — which is the entire difference between this and the
    ``500`` it replaces.
    """
    _make("01DEEPBODYLEGIBLE000000001")

    body = _post_raw(client, "01DEEPBODYLEGIBLE000000001", _nested(CRASHING_DEPTH)).json()

    (error,) = body["detail"]
    assert error["type"] == "dict_type"
    assert error["loc"] == ["body"]
    assert "valid dict" in error["msg"]
    assert error["input"] == {
        "omitted": "too_deeply_nested",
        "max_depth": _MAX_ECHOED_BODY_DEPTH,
    }


def test_the_omitted_marker_does_not_leak_the_value_it_replaces(client):
    """A marker that embedded a prefix of the body would not be an omission."""
    _make("01DEEPBODYNOLEAK0000000001")

    text = _post_raw(
        client, "01DEEPBODYNOLEAK0000000001", "[" * CRASHING_DEPTH + '"SENTINEL"' + "]" * CRASHING_DEPTH
    ).text

    assert "SENTINEL" not in text
    assert "[[[" not in text


def test_a_deep_value_inside_a_VALID_body_never_reached_this_path_at_all(client):
    """The shape control, and the reason the report's first repro was misleading.

    ``{"confirmed_by_user": true, "deep": [[[…1000…]]]}`` VALIDATES as a ``dict``,
    so the framework never builds a validation error and never echoes anything.
    That request succeeded before this fix and succeeds after it. Asserting this
    keeps a future reader from "fixing" a crash on a path that never had one — and
    from mistaking the discard's success for the defect.
    """
    _make("01DEEPBODYVALID00000000001")

    response = _post_raw(
        client,
        "01DEEPBODYVALID00000000001",
        '{"confirmed_by_user": true, "deep": %s}' % _nested(CRASHING_DEPTH),
    )

    assert response.status_code == 200, response.text
    assert ws.load_experiment("01DEEPBODYVALID00000000001") is None


def test_the_crash_was_APPLICATION_WIDE_and_so_is_the_fix(client):
    """It was never a discard defect; it was the default handler.

    Asserted over several unrelated operations so that a future change which moved
    the guard into one route fails here.
    """
    _make("01DEEPBODYWIDE000000000001")
    tag = _etag(client, "01DEEPBODYWIDE000000000001")
    headers = {"If-Match": tag, "content-type": "application/json"}
    deep = _nested(CRASHING_DEPTH)

    for path in (
        "/api/experiments",
        "/api/experiments/01DEEPBODYWIDE000000000001/answers",
        "/api/experiments/01DEEPBODYWIDE000000000001/edit",
        "/api/experiments/01DEEPBODYWIDE000000000001/runs",
    ):
        response = client.post(path, content=deep, headers=headers)
        assert response.status_code != 500, (path, response.text)
        assert response.status_code == 422, (path, response.status_code)


# =============================================================================
# 2. Byte-identical to FastAPI's default for everything else
# =============================================================================


def test_a_SHALLOW_validation_error_is_byte_identical_to_FASTAPIS_OWN_HANDLER(client):
    """The claim that lets this be registered application-wide, checked as a claim.

    The replacement handler is run against the framework's original over the same
    exception, and the two bodies are compared. Anything but equality means ~70
    operations' ``422`` contract moved.
    """
    import asyncio
    import json

    from fastapi.exception_handlers import request_validation_exception_handler
    from fastapi.exceptions import RequestValidationError

    from isaac_api.routes import request_validation_error_handler

    exc = RequestValidationError(
        [
            {
                "type": "dict_type",
                "loc": ("body",),
                "msg": "Input should be a valid dictionary",
                "input": [1, {"a": ["b", 2]}, None],
            }
        ]
    )

    ours = asyncio.run(request_validation_error_handler(None, exc))
    theirs = asyncio.run(request_validation_exception_handler(None, exc))

    assert ours.status_code == theirs.status_code == 422
    assert json.loads(ours.body) == json.loads(theirs.body)
    assert ours.body == theirs.body


def test_a_REAL_shallow_bad_body_still_echoes_its_input(client):
    """The same property end-to-end: normal ``422`` bodies are unchanged."""
    _make("01DEEPBODYSHALLOW000000001")

    body = _post_raw(client, "01DEEPBODYSHALLOW000000001", '["not", "a", "dict"]').json()

    (error,) = body["detail"]
    assert error["input"] == ["not", "a", "dict"], (
        "a shallow input stopped being echoed — the bound is not supposed to reach it"
    )


# =============================================================================
# 3. The bound itself
# =============================================================================


def test_the_bound_sits_between_its_two_measurements():
    """Both ends of the derivation, so neither can drift unremarked.

    The floor: a stored value is already capped at ``_MAX_VALUE_DEPTH``, so the
    echo bound must exceed it or a legitimately-storable value could not be quoted
    back. The ceiling: the shallowest top-level body measured to crash the encoder
    was 972, and the bound must stay well under it.
    """
    assert _MAX_ECHOED_BODY_DEPTH > _MAX_VALUE_DEPTH
    assert _MAX_ECHOED_BODY_DEPTH * 4 < 972


def test_the_predicate_is_the_APPLICATIONS_EXISTING_ONE_and_cannot_itself_recurse():
    """No second depth guard was introduced, and the shared one is iterative.

    A recursive depth check would raise ``RecursionError`` on the exact input it
    was added to describe, moving the crash one frame earlier rather than removing
    it. Exercised at a depth that would destroy a recursive implementation.
    """
    from isaac_api.routes import _value_depth_within

    deep: object = 1
    for _ in range(5000):
        deep = [deep]

    assert _value_depth_within(deep, _MAX_ECHOED_BODY_DEPTH) is False
    assert _value_depth_within([[1]], _MAX_ECHOED_BODY_DEPTH) is True
