"""The CORS method allowlist must cover every method the app's routes use.

This file exists because it did not, and a shipped route was unreachable from
every browser that talks to the API cross-origin.

The defect: ``create_app`` configured ``CORSMiddleware`` with
``allow_methods=["GET", "POST", "DELETE", "OPTIONS"]``, and the Run API added the
repository's first ``PATCH`` route. A browser answers a cross-origin ``PATCH``
with a preflight; Starlette's ``CORSMiddleware`` refused it — ``400 Bad Request``,
"Disallowed CORS method" — so the ``PATCH`` was never sent at all. Measured in
Chrome as four consecutive ``OPTIONS .../runs/<run_id> 400`` in the uvicorn log
with the run's stored value never moving off ``rev 1``.

Why no existing test caught it, which is the part worth designing against:

* the backend suite drives ``TestClient``, which issues no preflight unless a test
  writes the ``OPTIONS`` request by hand;
* the frontend suite mocks ``fetch``, so no CORS layer is involved;
* and the hosted deployment serves the SPA and the API from ONE origin, where a
  preflight never happens — so the bug is invisible exactly where the app is
  deployed and total everywhere it is developed and end-to-end tested.

So a test that pins ``PATCH`` alone would only re-fight the last war. The guard
below DERIVES the required method set from the application's own route table: the
next route that introduces ``PUT`` fails a test instead of silently becoming
unreachable. ``test_the_guard_fails_when_a_route_uses_an_unlisted_method`` is the
negative control for that claim, kept as a permanent test rather than run once,
because a guard that enumerates nothing would otherwise pass forever.

Nothing here touches the truth plane, reads real data, or opens a connection.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

DEV_ORIGIN = "http://localhost:5173"

# The path a preflight is sent to is immaterial: Starlette's CORSMiddleware answers
# preflights itself, before routing, so the verdict depends only on the configured
# allowlist. A real, always-present path is used so a typo cannot make the request
# meaningless in some future where that stops being true.
PROBE_PATH = "/api/health"

# The route that broke, as registered (router prefix included, ISAAC_BASE_PATH unset).
RUN_PATCH_PATH = "/api/experiments/{experiment_id}/runs/{run_id}"

_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"}
)

# HEAD is excluded from the requirement, deliberately, for two independent reasons.
# (1) It is not this application's choice: ``starlette.routing.Route.__init__``
# appends HEAD to any route declaring GET, so HEAD appears in the derived set for
# routes that never asked for it — requiring it would assert a framework behaviour,
# not a property of this app. (2) It would be vacuous anyway: HEAD is a
# CORS-safelisted method under the Fetch standard, so a browser never needs the
# allowlist's permission to send one. OPTIONS is likewise not required of a route:
# it is the preflight itself.
_NOT_REQUIRED_OF_ROUTES = frozenset({"HEAD", "OPTIONS"})


def _make_app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_UI_CORS_ORIGINS", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def app(tmp_path, monkeypatch):
    return _make_app(tmp_path, monkeypatch)


# --- deriving the requirement from the app itself ------------------------------


def _registered_methods(app) -> set[str]:
    """Every HTTP method reachable in the app's own route table.

    Walked, never listed. The walk is written against three shapes so it survives
    a FastAPI upgrade rather than quietly returning less: a plain route exposes
    ``.methods``; a mount or router exposes ``.routes``; and FastAPI 0.139 wraps an
    included router in a private ``_IncludedRouter`` whose sub-routes hang off
    ``.original_router``. All three are followed, each guarded with ``getattr`` so
    a version that drops one still enumerates the others.

    ``_route_table_enumeration_is_not_vacuous`` is what keeps a walk that finds
    nothing from making every assertion built on this function trivially true.
    """
    methods: set[str] = set()
    seen: set[int] = set()

    def walk(routes) -> None:
        for route in routes or ():
            if id(route) in seen:
                continue
            seen.add(id(route))
            methods.update(getattr(route, "methods", None) or ())
            walk(getattr(route, "routes", None))
            inner = getattr(route, "original_router", None)
            if inner is not None:
                walk(getattr(inner, "routes", None))

    walk(app.routes)
    return methods


def _documented_methods(app) -> set[str]:
    """The same set derived a second, independent way — from the OpenAPI document.

    Used only as a cross-check on the walk. It is not a substitute for it: routes
    registered with ``include_in_schema=False`` (the SPA fallback) never appear
    here, which is why the walk is the thing the guard actually uses.
    """
    return {
        operation.upper()
        for operations in app.openapi()["paths"].values()
        for operation in operations
        if operation.upper() in _HTTP_METHODS
    }


def _required_methods(app) -> set[str]:
    return _registered_methods(app) - _NOT_REQUIRED_OF_ROUTES


def _allowed_by_preflight(client: TestClient, method: str):
    """Send a real CORS preflight for ``method``; return (status, allowed methods)."""
    res = client.options(
        PROBE_PATH,
        headers={
            "Origin": DEV_ORIGIN,
            "Access-Control-Request-Method": method,
        },
    )
    raw = res.headers.get("access-control-allow-methods", "")
    return res.status_code, {part.strip() for part in raw.split(",") if part.strip()}


def _methods_the_browser_would_be_refused(client: TestClient, methods) -> set[str]:
    refused = set()
    for method in sorted(methods):
        status, allowed = _allowed_by_preflight(client, method)
        if status != 200 or method not in allowed:
            refused.add(method)
    return refused


# --- the guard -----------------------------------------------------------------


def test_route_table_enumeration_is_not_vacuous(app):
    """A superset assertion over an empty set passes forever. This forbids that.

    Two independent derivations of the app's method set must agree, with the walk
    the broader of the two (it also sees ``HEAD`` and unschema'd routes). If a
    FastAPI upgrade changes the route-table shape so the walk stops finding the
    included router, this fails here rather than turning the real guard green.
    """
    documented = _documented_methods(app)
    assert documented, "the OpenAPI document declares no operations at all"
    walked = _registered_methods(app)
    assert documented <= walked, (
        "the route-table walk missed methods the OpenAPI document declares: "
        f"{sorted(documented - walked)}"
    )
    # The bug's own verb, asserted through the derivation rather than beside it:
    # if PATCH ever stops being reachable through the walk, the guard below has
    # stopped guarding the thing it was written for.
    assert "PATCH" in walked


def test_cors_allows_every_method_the_route_table_registers(app):
    """The durable fix: ``allow_methods`` ⊇ the methods the app's routes use.

    Asserted behaviourally — one real preflight per method — rather than by
    reading the middleware's configuration, so it holds whatever the allowlist is
    spelled as and wherever it comes from.
    """
    client = TestClient(app)
    required = _required_methods(app)
    refused = _methods_the_browser_would_be_refused(client, required)
    assert refused == set(), (
        "these methods are used by registered routes but refused at CORS preflight, "
        f"making those routes unreachable from any cross-origin browser: {sorted(refused)}. "
        "Add them to allow_methods in isaac_api.app.create_app."
    )


def test_the_guard_fails_when_a_route_uses_an_unlisted_method(tmp_path, monkeypatch):
    """Negative control, kept permanently: prove the guard above can go red.

    A route using a method absent from ``allow_methods`` must be detected. ``PUT``
    is used because the app has no ``PUT`` route and none is planned, so this
    stays a synthetic probe rather than a second assertion about real behaviour.
    """
    app = _make_app(tmp_path, monkeypatch)

    def _probe() -> dict:  # pragma: no cover - never called; only its method matters
        return {}

    app.add_api_route(
        "/api/_cors_guard_negative_control",
        _probe,
        methods=["PUT"],
        include_in_schema=False,
    )
    client = TestClient(app)

    required = _required_methods(app)
    assert "PUT" in required, "the walk did not see the route just added"
    refused = _methods_the_browser_would_be_refused(client, required)
    assert "PUT" in refused, (
        "a route using an unlisted method was NOT flagged — the guard in "
        "test_cors_allows_every_method_the_route_table_registers cannot fail"
    )


# --- the specific regression ---------------------------------------------------


def test_cors_preflight_for_the_run_patch_route_succeeds(app):
    """The test that would have caught the shipped bug, standing on its own.

    The path is checked against the OpenAPI document first, so this cannot pass by
    preflighting a URL that no longer exists — the preflight itself is answered
    before routing and would happily succeed against a nonsense path.
    """
    paths = app.openapi()["paths"]
    assert RUN_PATCH_PATH in paths and "patch" in paths[RUN_PATCH_PATH], (
        f"no PATCH route registered at {RUN_PATCH_PATH}"
    )

    client = TestClient(app)
    res = client.options(
        "/api/experiments/EXP01/runs/RUN01",
        headers={
            "Origin": DEV_ORIGIN,
            "Access-Control-Request-Method": "PATCH",
            # Autosave sends both; a header the allowlist refuses fails the
            # preflight just as surely as a method it refuses.
            "Access-Control-Request-Headers": "content-type, if-match",
        },
    )
    assert res.status_code == 200, (
        f"autosave preflight refused: {res.status_code} {res.text!r}"
    )
    allowed = {
        part.strip()
        for part in res.headers.get("access-control-allow-methods", "").split(",")
        if part.strip()
    }
    assert "PATCH" in allowed, f"Access-Control-Allow-Methods is {sorted(allowed)}"
    assert res.headers.get("access-control-allow-origin") == DEV_ORIGIN
