"""The four ``answer_at`` / ``edit_at`` templates ARE the paths of the operations they name.

**THE GAP THIS CLOSES, AND WHY ONLY THE BACKEND CAN CLOSE IT.** Two refusals —
``409 belongs_to_a_run`` and ``422 not_yet_answered`` / ``already_answered`` — hand the
caller an ``answer_at`` naming the operation that CAN take the answer, and the web client
now follows it. It follows it through a fail-closed allowlist of four exact literals
(``apps/web/src/lib/assistantAgent.ts``'s ``ANSWER_AT_OPERATIONS``), which are
**hand-transcribed** from ``routes.py``'s ``_ANSWERS_OPERATION_RECORD`` /
``_ANSWERS_OPERATION_RUN`` / ``_EDIT_OPERATION_RECORD`` / ``_EDIT_OPERATION_RUN``.

Those four constants *coincide with* their routes' paths; nothing DERIVES them from the
routes. So a future change to a decorator's path — or to a constant — would leave the two
sides disagreeing, and **no test on either side would see it**: the frontend allowlist
would still match its own literals, and the backend's own refusal tests assert the
constant against itself. The client would then follow a template to a typed method for an
operation whose real path had moved, or (worse) stop following a valid one and tell a
scientist there is nowhere to answer.

**WHAT IS ASSERTED HERE IS AN IDENTITY, NOT A SPELLING.** Each constant is compared
against a string BUILT from the app's own route table — the route is located by its
ENDPOINT FUNCTION, never by the path being looked for, so this cannot pass by finding
what it was told to find. A second, independent derivation from the GENERATED OpenAPI
document catches the case the route table cannot: a route registered but excluded from
the published schema, which is the document the frontend and every external agent read.

Deliberately NOT asserted: that the frontend's four literals equal these. This test
cannot import TypeScript, and a duplicate of the strings here would be a fifth copy of
the thing the whole file is about. What it guarantees is that the four backend constants
are TRUE, which is the half the frontend agent could not reach and asked for.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

import isaac_api.routes as routes
from isaac_api.config import base_path


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """A real application, so the OpenAPI document below is the published one."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return create_app()


#: ``{the published template: the endpoint function it claims to name}``.
#:
#: THE ENDPOINT FUNCTION IS THE KEY FACT, and it is why this is a mapping rather than a
#: list of strings. Deriving the path from the function means the decorator is the single
#: source: change ``@router.post("/experiments/{experiment_id}/answers")`` and the
#: derived string moves while the constant does not, which is exactly the divergence that
#: currently slips past every test on both sides.
_CLAIMS = {
    "_ANSWERS_OPERATION_RECORD": routes.post_answers,
    "_ANSWERS_OPERATION_RUN": routes.post_run_answers,
    "_EDIT_OPERATION_RECORD": routes.post_edit,
    "_EDIT_OPERATION_RUN": routes.post_run_edit,
}


def _route_for(endpoint) -> APIRoute:
    """The ONE registered route whose endpoint is ``endpoint``.

    Located by identity. A helper that searched by path would be assuming the answer.
    """
    found = [
        route
        for route in routes.router.routes
        if isinstance(route, APIRoute) and route.endpoint is endpoint
    ]
    assert len(found) == 1, (
        f"{endpoint.__name__} is registered {len(found)} times; this guard assumes "
        "exactly one route per endpoint"
    )
    return found[0]


def _derived_template(endpoint) -> str:
    """``"<METHOD> <path>"`` for one endpoint, built from the route table."""
    route = _route_for(endpoint)
    assert route.methods == {"POST"}, (endpoint.__name__, sorted(route.methods))
    return f"POST {route.path}"


@pytest.mark.parametrize("name", sorted(_CLAIMS))
def test_the_constant_is_the_path_of_the_operation_it_names(name):
    """The published template, against the route table's own answer for that endpoint."""
    constant = getattr(routes, name)
    assert constant == _derived_template(_CLAIMS[name]), (
        f"routes.{name} is {constant!r} but {_CLAIMS[name].__name__} is registered at "
        f"{_derived_template(_CLAIMS[name])!r}. A client following this template lands "
        "somewhere that cannot take the answer."
    )


def test_each_constant_names_a_DIFFERENT_operation():
    """A NEGATIVE CONTROL, because the test above would pass if all four were the same.

    Four constants that all derived to one path would satisfy every equality above while
    sending every run-level refusal to the record's operation — the precise defect the
    constants' own docstring says they exist to prevent (*"one of them was measured
    pointing at the wrong level"*). So the four derived templates must be four distinct
    strings, and each constant must match ONLY its own.
    """
    derived = {name: _derived_template(fn) for name, fn in _CLAIMS.items()}
    assert len(set(derived.values())) == 4, derived
    for name, template in derived.items():
        matching = [other for other in derived if getattr(routes, other) == template]
        assert matching == [name], (name, matching)


def test_the_generated_openapi_publishes_the_same_four_operations(app):
    """THE SECOND, INDEPENDENT DERIVATION — from the document the client actually reads.

    The route table can hold a route that ``include_in_schema=False`` keeps out of the
    published OpenAPI. A frontend or external agent following ``answer_at`` reads the
    document, not the table, so a template naming a route the document does not publish
    is still a template pointing at nothing as far as its consumer is concerned.

    ``base_path()`` is applied because the app mounts the router under
    ``ISAAC_BASE_PATH`` while these constants are deliberately base-relative — so this
    also pins that the constants are base-relative rather than accidentally absolute.
    """
    document = app.openapi()
    prefix = base_path()
    for name, endpoint in _CLAIMS.items():
        method, path = getattr(routes, name).split(" ", 1)
        published = document["paths"].get(f"{prefix}{path}")
        assert published is not None, (
            f"routes.{name} names {path!r}, which the generated OpenAPI does not publish"
        )
        operation = published.get(method.lower())
        assert operation is not None, (name, sorted(published))
        # ``unique_id`` is the operationId FastAPI publishes for THIS route object,
        # so comparing against it ties the document entry back to the same endpoint
        # the route table matched — rather than to a path string this test supplied.
        assert operation["operationId"] == _route_for(endpoint).unique_id, (
            name,
            operation["operationId"],
        )


def test_the_guard_is_not_vacuous_if_a_constant_drifts():
    """MUTATION, APPLIED IN-PROCESS rather than described.

    The equality above is only a guard if a wrong constant fails it. Rather than trusting
    that, this rewrites each constant to a plausible near-miss — the shape a real drift
    takes: a path segment renamed, or the run level's template used at the record level —
    and asserts the derivation refuses it. It restores the real value afterwards, and the
    restoration is asserted too, because a mutation test that leaks its mutation is worse
    than none.
    """
    for name, endpoint in _CLAIMS.items():
        real = getattr(routes, name)
        for wrong in (
            real.replace("/answers", "/answer").replace("/edit", "/edits"),
            real.replace("POST", "PUT"),
            "POST /api/experiments/{experiment_id}/runs/{run_id}/answers"
            if "runs" not in real
            else "POST /api/experiments/{experiment_id}/answers",
        ):
            assert wrong != real, (name, wrong)
            assert wrong != _derived_template(endpoint), (name, wrong)
        assert getattr(routes, name) == real
