"""A body carrying a value JSON cannot represent returned **500** on 25 operations.

THE ATTACK, AND WHAT IT FOUND
=============================
This file was written as an attack pass, not as a regression guard: the sweep below
was run against ``main`` at ``c2a93a7`` BEFORE any fix existed, and it succeeded.
**210 probes, 79 unhandled ``500``s, across 25 of the application's 71 operations** —
every operation whose request body is validated by a Pydantic model, plus every
operation reachable with a top-level scalar body.

The five shapes that did it, all of which a client can put on the wire and none of
which ``JSON.stringify`` can produce (they need a hand-written body, which is what an
attacker sends):

============================  ==========================================
shape                         example body
============================  ==========================================
``NaN``                       ``{"zzz_probe": NaN}``
``Infinity``                  ``{"zzz_probe": Infinity}``
a lone surrogate in a VALUE   ``{"zzz_probe": "\\ud800"}``
a lone surrogate in a KEY     ``{"\\ud800": 1}``
a top-level scalar of either  ``NaN`` / ``"\\ud800"``
============================  ==========================================

THE CAUSE IS ONE FUNCTION, AND IT IS THE ONE THAT EXISTS TO REFUSE BAD BODIES
=============================================================================
Not a route. ``routes.request_validation_error_handler`` renders the ``422`` by
echoing each validator error — including the offending ``input``, and including a
``loc`` built from the offending KEY — and Starlette renders a response with::

    json.dumps(content, ensure_ascii=False, allow_nan=False, …).encode("utf-8")

``allow_nan=False`` raises ``ValueError`` on ``NaN``/``Infinity``; ``ensure_ascii=False``
means the ``.encode("utf-8")`` raises ``UnicodeEncodeError`` on a lone surrogate. So
**the handler that exists to refuse a body was destroyed by the body it was
describing** — which is, precisely, the defect that handler was written to fix for a
different input shape. Its own docstring records the depth case; the representability
case was not screened.

Measured tracebacks, both from ``raise_server_exceptions=True`` against ``c2a93a7``::

    ValueError: Out of range float values are not JSON compliant: nan
    UnicodeEncodeError: 'utf-8' codec can't encode character '\\ud800' in position 153

WHY THE APPLICATION'S EXISTING GUARDS DID NOT COVER IT
======================================================
They cover the *write* path and they cover it well. ``_is_storable_value`` /
``_render_exactly_as_a_response_would`` refuse ``NaN``, ``Infinity`` and lone
surrogates at ``/answers``, ``/edit``, the run routes, notes, assets and labels —
``test_run_api.py`` and ``test_answers_size_and_depth.py`` pin all of it. Every one of
those guards runs **inside a route function**. The crash happens **before any route
function is entered**, in the shared exception handler, so no route-level guard could
ever have seen it. ``test_deeply_nested_body_is_refused_not_crashed.py`` is the only
file that reaches this handler at all, and it bounds DEPTH, which is a different
property of the same echo.

SEVERITY, STATED PRECISELY RATHER THAN INFLATED
===============================================
**Error-shape and availability, not integrity.** Nothing is written on any of the 79
paths — the crash is in the refusal, and the refusal is reached because validation
already failed. What a caller loses is the typed refusal: a ``500`` with no ``detail``
says *"this server is broken"* where the truth is *"your body is not one this
operation accepts"*, and an operator reading it goes looking for a defect in a route
that was never entered. That is the same severity the depth defect had, argued the
same way, and it is the reason this is a fix rather than an incident.

THE FIX, AND WHY IT CANNOT MOVE ANY RESPONSE THAT WORKS TODAY
=============================================================
One check, in the same handler, after the encode and before the response: render the
finished content exactly as Starlette will, and if that raises, replace it with a
typed body that quotes **nothing** from the request. The substitution is reachable
**only** on content whose render raises — which is exactly the set that used to
produce a ``500`` — so no ``422`` that renders today changes by a byte, and
``test_deeply_nested_body_is_refused_not_crashed.py``'s byte-identity assertion
against FastAPI's own handler still holds.

It screens the WHOLE content rather than each error's ``input``, and that is not
laziness: the ``surrogate-key`` shape puts the offending character in ``loc``, not in
``input``, so a per-``input`` screen would have fixed four of the five shapes and left
the fifth returning ``500``. The check *is* the render, so it cannot disagree with it.

EVERYTHING HERE IS SYNTHETIC. No file outside the test's own ``tmp_path`` workspace is
read or written, no database connection is opened, and no request leaves the process.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# --- the five shapes, as RAW BYTES ------------------------------------------
# Raw bytes rather than `json=`: `json.dumps` in the client would either refuse
# these or re-escape them, so a test that built the body with a serializer would be
# testing the serializer. An attacker writes the bytes.
UNREPRESENTABLE = {
    "nan": b'{"zzz_probe": NaN}',
    "infinity": b'{"zzz_probe": Infinity}',
    "negative-infinity": b'{"zzz_probe": -Infinity}',
    "lone-surrogate-in-a-value": rb'{"zzz_probe": "\ud800"}',
    "lone-surrogate-in-a-key": rb'{"\ud800": 1}',
    "top-level-nan": b"NaN",
    "top-level-lone-surrogate": rb'"\ud800"',
}

#: The operations measured to answer ``500`` on ``c2a93a7``, as ``(method, path)``
#: with the path exactly as the OpenAPI document spells it. Transcribed from the
#: attack run, not guessed, and asserted below to still be operations this
#: application publishes — so an operation that is renamed or removed makes this
#: list fail loudly rather than silently shrink.
CRASHED_ON_MAIN = (
    ("PATCH", "/api/experiments/{experiment_id}"),
    ("PATCH", "/api/experiments/{experiment_id}/assets/{asset_id}"),
    ("PATCH", "/api/experiments/{experiment_id}/runs/{run_id}"),
    ("POST", "/api/assistant/ask"),
    ("POST", "/api/assistant/memory/query"),
    ("POST", "/api/demo/reset"),
    ("POST", "/api/demo/run"),
    ("POST", "/api/experiments"),
    ("POST", "/api/experiments/{experiment_id}/answers"),
    ("POST", "/api/experiments/{experiment_id}/assets"),
    ("POST", "/api/experiments/{experiment_id}/assets/{asset_id}/remove"),
    ("POST", "/api/experiments/{experiment_id}/assistant/query"),
    ("POST", "/api/experiments/{experiment_id}/conflicts/resolve"),
    ("POST", "/api/experiments/{experiment_id}/discard"),
    ("POST", "/api/experiments/{experiment_id}/edit"),
    ("POST", "/api/experiments/{experiment_id}/notes"),
    ("POST", "/api/experiments/{experiment_id}/notes/{note_id}/review"),
    ("POST", "/api/experiments/{experiment_id}/runs"),
    ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/answers"),
    ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/edit"),
    ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/overrides"),
    ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/overrides/clear"),
    ("POST", "/api/experiments/{experiment_id}/runs/{run_id}/remove"),
    ("POST", "/api/experiments/{experiment_id}/transcript"),
    ("POST", "/api/transcription"),
)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def client(app):
    # `raise_server_exceptions=False` so an unhandled exception surfaces as the 500
    # a real client would see, which is what the assertions are about.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def targets(client):
    """One of everything the swept paths need to address, all server-minted."""
    eid = client.post("/api/experiments", json={"title": "attack surface"}).json()["id"]

    def etag() -> str:
        return client.get(f"/api/experiments/{eid}").headers["ETag"]

    run = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "run A"},
        headers={"If-Match": etag()},
    )
    assert run.status_code == 201, run.text
    note = client.post(
        f"/api/experiments/{eid}/notes",
        json={"text": "a note", "source": "typed_note"},
        headers={"If-Match": etag()},
    )
    assert note.status_code == 201, note.text
    session = client.post("/api/tutorial/sessions")
    assert session.status_code == 201, session.text
    return {
        "{experiment_id}": eid,
        "{run_id}": run.json()["run"]["id"],
        "{note_id}": note.json()["note"]["id"],
        # No asset is created: `/assets/{asset_id}` crashed on `main` with an id
        # that addresses nothing, which is the point — the crash is above the
        # route, so whether the target exists is irrelevant to it.
        "{asset_id}": "an-asset-that-does-not-exist",
        "{session_id}": session.json()["session_id"],
        "{revision_no}": "1",
        "{concept_id}": "a-concept-that-does-not-exist",
        "_etag": etag,
    }


def _url(path: str, targets) -> str:
    for placeholder, value in targets.items():
        if placeholder.startswith("{"):
            path = path.replace(placeholder, value)
    return path


# =============================================================================
# 1. the sweep — every write operation, every shape
# =============================================================================


@pytest.mark.parametrize("shape", sorted(UNREPRESENTABLE))
def test_no_write_operation_answers_500_to_an_unrepresentable_body(
    client, app, targets, shape
):
    """THE ATTACK ITSELF, over every ``POST``/``PATCH`` this application publishes.

    Driven off ``app.openapi()`` rather than a transcribed list, so an operation
    added tomorrow is swept the day it exists. A ``501`` is accepted (a provider
    seam this deployment has not configured — an honest refusal), and every other
    answer must be a client-blaming 4xx: the body IS the client's fault, and
    saying ``500`` about it blames the wrong party and hides which validator
    refused.

    Measured on ``c2a93a7`` BEFORE the fix: **79 of 210 probes answered 500**,
    across 25 distinct operations. Measured after: 0.

    MUTATION: narrowing ``request_validation_error_handler``'s render-check arm
    from ``except (ValueError, TypeError, RecursionError)`` to
    ``except ZeroDivisionError`` — so the check runs and catches nothing — turns
    this RED::

        AssertionError: ('POST', '/api/assistant/memory/query', 500, 'Internal Server Error')
        assert 500 != 500
          +  where 500 = <Response [500 Internal Server Error]>.status_code
    """
    doc = app.openapi()
    probed = 0
    for path, operations in sorted(doc["paths"].items()):
        url = _url(path, targets)
        for method in sorted(operations):
            if method.upper() in ("GET", "DELETE", "HEAD", "OPTIONS"):
                continue
            probed += 1
            response = client.request(
                method.upper(),
                url,
                content=UNREPRESENTABLE[shape],
                headers={
                    "If-Match": targets["_etag"](),
                    "content-type": "application/json",
                },
            )
            assert response.status_code != 500, (
                method.upper(),
                path,
                response.status_code,
                response.text[:200],
            )
            assert response.status_code < 500 or response.status_code == 501, (
                method.upper(),
                path,
                response.status_code,
            )
    # The sweep must actually have swept something. Without this the test passes
    # against an application with no write operations at all.
    assert probed >= 30, probed


def test_every_operation_the_attack_crashed_is_still_an_operation_this_app_publishes(
    app,
):
    """The transcribed list is checked against reality, so it cannot rot silently.

    A list of "operations that used to crash" is worth nothing if one of them was
    renamed and the entry now names a path the sweep never visits: the file would
    keep reporting 25 covered operations while covering 24.

    MUTATION: adding ``("POST", "/api/experiments/{experiment_id}/nonexistent")``
    to ``CRASHED_ON_MAIN`` turns this RED::

        AssertionError: /api/experiments/{experiment_id}/nonexistent
        assert '/api/experiments/{experiment_id}/nonexistent' in
               {'/api/health': {'get': {…}}, …}
    """
    paths = app.openapi()["paths"]
    for method, path in CRASHED_ON_MAIN:
        assert path in paths, path
        assert method.lower() in paths[path], (method, path)
    assert len(set(CRASHED_ON_MAIN)) == 25, len(set(CRASHED_ON_MAIN))


# =============================================================================
# 2. the refusal is TYPED, not merely non-500
# =============================================================================


@pytest.mark.parametrize("shape", sorted(UNREPRESENTABLE))
def test_the_refusal_is_a_typed_422_that_says_what_was_wrong(client, shape):
    """Non-500 is not enough: the caller must learn the body was refused, and why.

    ``POST /api/experiments`` is the exemplar because it is the operation a first
    request hits and because its model sets ``extra="forbid"``, so every shape
    here reaches the validator rather than a route guard.

    MUTATION: renaming the fallback entry's ``type``/``loc`` keys (to ``zzz``
    and ``zzzloc``) turns this RED::

        assert entry["type"], entry
        E   KeyError: 'type'
    """
    response = client.request(
        "POST",
        "/api/experiments",
        content=UNREPRESENTABLE[shape],
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422, (shape, response.status_code, response.text)
    body = response.json()
    assert isinstance(body["detail"], list) and body["detail"], body
    # Every entry names a validator and a location, which is the 422 contract the
    # other ~70 operations already publish.
    for entry in body["detail"]:
        assert entry["type"], entry
        assert entry["loc"], entry
        assert entry["msg"], entry


def test_the_fallback_refusal_quotes_nothing_from_the_request(client):
    """The body that could not be rendered is not smuggled into the refusal.

    A refusal that quoted the offending value back would re-introduce the very
    crash it replaces the moment somebody changed how it was escaped. The
    fallback therefore names the CLASS of problem and nothing else — no key, no
    value, no offset.

    MUTATION: interpolating the raw body into the fallback ``msg`` turns this
    RED::

        AssertionError: assert 'zzz_secret_marker' not in '{"detail":[{"type":…
    """
    response = client.request(
        "POST",
        "/api/experiments",
        content=rb'{"zzz_secret_marker": "\ud800"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert "zzz_secret_marker" not in response.text
    assert "\\ud800" not in response.text
    assert "ud800" not in response.text


def test_the_fallback_names_the_class_of_problem_so_it_is_not_passing_by_silence(
    client,
):
    """The negative control for the test above: quoting nothing is easy to achieve
    by saying nothing. The refusal must still be actionable.

    MUTATION: emptying the fallback's ``msg`` turns this RED::

        AssertionError: {"detail":[{"type":"not_representable_in_json","loc":["body"],"msg":""}]}
        assert 'nothing was written' in '{"detail":[{"type":"not_representable_in_json","loc":["body"],"msg":""}]}'
    """
    response = client.request(
        "POST",
        "/api/experiments",
        content=b'{"zzz_probe": NaN}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    rendered = response.text.lower()
    assert "json" in rendered, response.text
    assert "nothing was written" in rendered, response.text


# =============================================================================
# 3. nothing is written, on any of the crashing paths
# =============================================================================


def test_an_unrepresentable_body_writes_nothing_and_does_not_move_the_revision(
    client, targets
):
    """The severity claim in the module docstring, asserted rather than argued.

    The record is read before and after every shape is thrown at every write
    operation that REFUSES the body, and the whole stored document — not just a
    field — must be byte-identical.

    **THE ROUTE LIST IS NARROWER THAN "every write route", AND THE REASON IS A
    MEASUREMENT, NOT A CONVENIENCE.** ``POST .../runs`` and ``POST .../notes`` take
    an untyped ``dict`` body and IGNORE keys they do not recognise, so
    ``{"zzz_probe": NaN}`` is a perfectly ordinary create request with no label —
    it legitimately writes a run. Including them turned the first version of this
    test red for a reason that had nothing to do with the defect, which is worth
    recording: a sweep that asserts "nothing was written" across routes with
    different body contracts is asserting something false about some of them.
    Every route listed below refuses the body outright.

    MUTATION: adding ``f"/api/experiments/{eid}/runs"`` back to the list turns
    this RED at the per-request status assertion, BEFORE the state comparison —
    which is the measurement being recorded, not a regression::

        AssertionError: ('/api/experiments/01M19MFNCS04R54YMHTTPBPJ19/runs', 201)
        assert 400 <= 201
    """
    import json

    import isaac_api.workspace as ws

    eid = targets["{experiment_id}"]
    before = json.dumps(ws.load_experiment(eid).to_state(), sort_keys=True)

    for payload in UNREPRESENTABLE.values():
        for path in (
            f"/api/experiments/{eid}/answers",
            f"/api/experiments/{eid}/edit",
            f"/api/experiments/{eid}/assets",
            f"/api/experiments/{eid}/discard",
            f"/api/experiments/{eid}/conflicts/resolve",
        ):
            response = client.post(
                path,
                content=payload,
                headers={
                    "If-Match": targets["_etag"](),
                    "content-type": "application/json",
                },
            )
            assert 400 <= response.status_code < 500, (path, response.status_code)

    after = json.dumps(ws.load_experiment(eid).to_state(), sort_keys=True)
    assert after == before


# =============================================================================
# 4. the fix cannot have moved a response that already worked
# =============================================================================


def test_an_ordinary_validation_error_is_untouched_by_the_new_check(client):
    """The whole basis for registering this application-wide: a renderable ``422``
    is byte-identical to what it was, because the substitution is reachable only
    on content whose render raises.

    A missing required field is the most common ``422`` in the product, and it
    still echoes the input it always echoed.

    MUTATION: making the fallback unconditional (``raise ValueError`` in place of
    the render check, so every validation error takes it) turns this RED::

        assert 'Field required' in '{"detail":[{"type":"not_representable_in_json",
        "loc":["body"],"msg":"The request body carries a value JSON cannot rep…
        Nothing was read and nothing was written."}]}'
    """
    response = client.post("/api/experiments", json={})
    assert response.status_code == 422, response.text
    assert "Field required" in response.text, response.text
    assert "not_representable" not in response.text, response.text


def test_the_depth_bound_still_fires_and_is_not_replaced_by_the_new_one(client):
    """Two different defects, two different markers, and the first must survive.

    A deep body renders fine once the depth substitution has replaced ``input``,
    so it must reach the ``too_deeply_nested`` marker and NOT the new fallback —
    otherwise the new check would have silently taken over a case the older one
    describes better.

    MUTATION: disabling the depth substitution (``and False`` in place of the
    ``_value_depth_within`` test) turns this RED::

        assert 'too_deeply_nested' in '{"detail":[{"type":"missing","loc":["body",
        "title"],"msg":"Field required","input":{"zzz_probe":[[[[[…]]]]]}}, …
        {"type":"extra_forbidden","loc":["body","zzz_probe"], …}]}'
    """
    deep = b'{"zzz_probe": ' + b"[" * 200 + b"]" * 200 + b"}"
    response = client.request(
        "POST",
        "/api/experiments",
        content=deep,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert "too_deeply_nested" in response.text, response.text


def test_the_render_check_is_the_same_call_starlette_makes(client):
    """The claim that makes "cannot move a working response" provable rather than
    plausible: the guard is not an approximation of the render, it IS the render.

    Asserted against the module's own transcription of Starlette's call, which
    already carries a docstring recording that an earlier approximation of it was
    wrong in exactly this way (``ensure_ascii`` omitted).

    MUTATION: changing ``_render_exactly_as_a_response_would`` to pass
    ``ensure_ascii=True, allow_nan=True`` turns this RED::

        Failed: DID NOT RAISE any of (ValueError, TypeError)
    """
    import json

    from isaac_api import routes
    from starlette.responses import JSONResponse

    for value in (float("nan"), float("inf"), "\ud800"):
        content = {"detail": [{"input": value}]}
        with pytest.raises((ValueError, TypeError)):
            routes._render_exactly_as_a_response_would(content)
        with pytest.raises((ValueError, TypeError)):
            JSONResponse(status_code=422, content=content)
    # And it renders what Starlette renders, byte for byte, for a value that works.
    ok = {"detail": [{"input": "ordinary", "n": 1.5}]}
    assert routes._render_exactly_as_a_response_would(ok) == JSONResponse(
        status_code=422, content=ok
    ).body
    assert json.loads(routes._render_exactly_as_a_response_would(ok)) == ok


# =============================================================================
# 5. THE SECOND CRASH SITE — a refusal that NAMES the key it is refusing
# =============================================================================
#
# Found only after the handler above was fixed, because it was hidden behind it on
# every operation whose body is validated by a model. Three helpers build their own
# `422` from an untyped `dict` and echo the offending KEY, so `{"\ud800": 1}` put a
# lone surrogate into a `JSONResponse` and raised inside the refusal itself. Five
# operations, one shared remedy (`routes._echoable_key`).


UNRENDERABLE_KEY_ROUTES = (
    "/api/assistant/ask",
    "/api/experiments/{eid}/conflicts/resolve",
    "/api/experiments/{eid}/notes",
    "/api/experiments/{eid}/notes/{note_id}/review",
    "/api/experiments/{eid}/transcript",
)


@pytest.mark.parametrize("template", UNRENDERABLE_KEY_ROUTES)
def test_a_refusal_that_names_a_key_survives_a_key_it_cannot_name(
    client, targets, template
):
    """The five operations that crashed inside their own ``422``.

    Each refuses an unrecognised body key and publishes it. A key JSON cannot
    represent therefore destroyed the refusal — measured as an unhandled ``500``
    on ``c2a93a7``, from the code path that was making exactly the right decision.

    MUTATION: reverting ``_unknown_note_keys`` to ``sorted(str(key) for key in
    body if key not in allowed)`` turns the three note-family rows RED (and leaves
    the other two passing, which is how the three helpers were told apart)::

        AssertionError: ('/api/experiments/01M19MFHS8JJZ53PNW3MYW2P8J/notes',
                         'Internal Server Error')
        assert 500 != 500
        1 failed, 2 passed
    """
    url = template.format(eid=targets["{experiment_id}"], note_id=targets["{note_id}"])
    response = client.post(
        url,
        content=rb'{"\ud800": 1}',
        headers={
            "If-Match": targets["_etag"](),
            "content-type": "application/json",
        },
    )
    assert response.status_code != 500, (url, response.text[:200])
    assert response.status_code == 422, (url, response.status_code, response.text[:200])
    assert response.json()["error"] == "unrecognized_field", response.text


def test_the_placeholder_replaces_the_key_and_quotes_none_of_it(client, targets):
    """What the refusal says instead, and what it must not say.

    The published key is the fixed placeholder, and no fragment of the real key —
    escaped or otherwise — reaches the body.

    MUTATION: returning an escaped prefix of the key instead of the placeholder
    (``'ud800-' + key.encode('utf-8', 'backslashreplace').decode()[:8]``) turns
    this RED::

        assert 'ud800-\\ud800' == '<a key this response cannot quote>'
          - <a key this response cannot quote>
          + ud800-\\ud800
    """
    from isaac_api import routes

    response = client.post(
        f"/api/experiments/{targets['{experiment_id}']}/notes",
        content=rb'{"\ud800": 1}',
        headers={
            "If-Match": targets["_etag"](),
            "content-type": "application/json",
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["key"] == routes.UNRENDERABLE_KEY_PLACEHOLDER, body
    assert body["keys"] == [routes.UNRENDERABLE_KEY_PLACEHOLDER], body
    assert "ud800" not in response.text


def test_an_ordinary_unrecognised_key_is_still_named_verbatim(client, targets):
    """The negative control, and the reason the fix is not a blanket redaction.

    Naming the key is the whole value of the refusal: a caller who sent
    ``reviewd_by`` must be told which key was wrong. Only a key that cannot be
    rendered is replaced.

    MUTATION: making ``_echoable_key`` always return the placeholder (an
    unconditional ``raise`` in place of the render call) turns this RED::

        assert '<a key this response cannot quote>' == 'reviewd_by'
          - reviewd_by
          + <a key this response cannot quote>
    """
    response = client.post(
        f"/api/experiments/{targets['{experiment_id}']}/notes",
        json={"text": "n", "source": "typed_note", "reviewd_by": "someone"},
        headers={"If-Match": targets["_etag"]()},
    )
    assert response.status_code == 422, response.text
    assert response.json()["key"] == "reviewd_by", response.text


def test_membership_is_decided_on_the_real_key_not_on_the_placeholder(client, targets):
    """A subtle way the fix could have been wrong, pinned so it stays right.

    If ``_echoable_key`` had been applied BEFORE the ``key not in allowed`` test,
    two unrenderable keys would collapse to one placeholder and — worse — a
    placeholder that happened to match an accepted name would make an
    unrenderable key *accepted*. The refusal below proves the real key was the one
    tested: an unrenderable key is still refused, and it is refused even when the
    rest of the body is a perfectly valid note.

    MUTATION: dropping unrenderable keys from the refused set instead of naming
    them (``and _echoable_key(key) != UNRENDERABLE_KEY_PLACEHOLDER`` added to
    ``_unknown_note_keys``' filter) turns this RED — the note is CREATED and the
    unrenderable key is silently swallowed::

        AssertionError: {"note":{"id":"01M19MGCFW82J3QK4V4C3Q4RNF", … }}
        assert 201 == 422
    """
    response = client.post(
        f"/api/experiments/{targets['{experiment_id}']}/notes",
        content=rb'{"text": "n", "source": "typed_note", "\ud800": 1}',
        headers={
            "If-Match": targets["_etag"](),
            "content-type": "application/json",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrecognized_field", response.text


def test_the_helper_is_the_same_predicate_as_the_handlers_check(client):
    """One definition of "can this be published", used in both places.

    A second, independently-written predicate is how the two crash sites would
    drift apart — one accepting what the other refuses.

    MUTATION: giving ``_echoable_key`` its own ``json.dumps(key)`` with default
    ``ensure_ascii`` turns this RED, because a lone surrogate then renders and the
    real key is published again::

        assert '\\ud800' == '<a key this response cannot quote>'
          - <a key this response cannot quote>
          + \\ud800
    """
    from isaac_api import routes

    assert routes._echoable_key("ordinary") == "ordinary"
    assert routes._echoable_key(1) == "1"
    assert routes._echoable_key("\ud800") == routes.UNRENDERABLE_KEY_PLACEHOLDER
    # And the placeholder is itself publishable, or the fix would crash on its own
    # replacement.
    routes._render_exactly_as_a_response_would(routes.UNRENDERABLE_KEY_PLACEHOLDER)
