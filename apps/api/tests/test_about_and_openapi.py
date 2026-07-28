"""P36.4 — Settings "Help / About" + "API Documentation" backend routes.

Two read-only, mutation-free GET routes:

  - ``GET /api/about``   — non-sensitive app/provenance metadata, reusing the
    SAME authoritative sources ``/health`` uses (``__version__``,
    ``_build_commit()``, ``runtime_mode.runtime_mode()``) plus
    ``isaac_records.official.EXPECTED_VERSION`` (read-only import — the truth
    core is never modified here).
  - ``GET /api/openapi`` — the app's own generated OpenAPI schema
    (``request.app.openapi()``), reachable under the base-path-prefixed
    ``/api`` router so the frontend docs render correctly under a deployed
    base path. No hand-maintained duplicate API description.

Both must be base-path-correct (``ISAAC_BASE_PATH=/krish`` -> the routes move
to ``/krish/api/about`` / ``/krish/api/openapi``, matching every other route
in this module), GET-only, and side-effect free.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from isaac_api.routes import OPENAPI_TAGS, _build_commit
from isaac_records.official import EXPECTED_VERSION


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("ISAAC_BASE_PATH", raising=False)
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


# --- GET /api/about ------------------------------------------------------------


def test_about_returns_expected_non_sensitive_fields(client):
    r = client.get("/api/about")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "app_version",
        "build_commit",
        "record_schema_version",
        "runtime_mode",
        "persistence",
        "data_regime",
        "core",
    }
    assert body["record_schema_version"] == "1.05"
    assert body["record_schema_version"] == EXPECTED_VERSION
    assert body["runtime_mode"] == "synthetic-only"
    assert body["persistence"] == "ephemeral"
    assert body["data_regime"] == "synthetic-only"
    assert body["core"] == "isaac_records"
    assert isinstance(body["app_version"], str) and body["app_version"]


def test_about_build_commit_matches_build_commit_helper_when_unset(client):
    # No ISAAC_BUILD_COMMIT / RAILWAY_GIT_COMMIT_SHA set by the fixture -> None,
    # matching the live (uncached) `_build_commit()` read.
    r = client.get("/api/about")
    assert r.json()["build_commit"] == _build_commit()
    assert r.json()["build_commit"] is None


def test_about_build_commit_reuses_build_commit_helper_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "fakecommit0000aboutp364")
    from isaac_api.app import create_app

    c = TestClient(create_app())
    r = c.get("/api/about")
    assert r.json()["build_commit"] == "fakecommit0000aboutp364"
    assert r.json()["build_commit"] == _build_commit()


# --- no sensitive infra / secret / absolute-path leakage ------------------------

_FORBIDDEN_SUBSTRINGS = (
    "authentik",
    "ingress",
    "k8s",
    "kubernetes",
    "railway.app",
    "vercel.app",
    "127.0.0.1",
    "localhost",
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "/Users/",
    "/home/",
    "C:\\",
)


def test_about_contains_no_secret_or_infra_host_strings(client, tmp_path):
    r = client.get("/api/about")
    dumped = json.dumps(r.json()).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle.lower() not in dumped, f"unexpected leak: {needle!r} in {dumped!r}"
    # Never leaks the local workspace path used by this very test.
    assert str(tmp_path).lower() not in dumped


def test_about_is_get_only(client):
    assert client.post("/api/about").status_code == 405
    assert client.put("/api/about").status_code == 405
    assert client.delete("/api/about").status_code == 405


def test_about_mutates_nothing(client, tmp_path):
    ws_dir = tmp_path / "ws"
    before = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    client.get("/api/about")
    client.get("/api/about")
    after = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    assert after == before


# --- GET /api/openapi ------------------------------------------------------------


def test_openapi_returns_schema_with_paths(client):
    r = client.get("/api/openapi")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "openapi" in body
    assert "paths" in body
    assert isinstance(body["paths"], dict)


def test_openapi_includes_a_known_route(client):
    r = client.get("/api/openapi")
    paths = r.json()["paths"]
    assert "/api/health" in paths
    assert "get" in paths["/api/health"]
    # The new routes document themselves too.
    assert "/api/about" in paths
    assert "/api/openapi" in paths


def test_openapi_matches_root_openapi_json(client):
    """Same generated schema FastAPI already serves at the root — no second
    hand-maintained description."""
    root = client.get("/openapi.json").json()
    api = client.get("/api/openapi").json()
    assert api == root


def test_openapi_is_get_only(client):
    assert client.post("/api/openapi").status_code == 405


def test_openapi_mutates_nothing(client, tmp_path):
    ws_dir = tmp_path / "ws"
    before = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    client.get("/api/openapi")
    after = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    assert after == before


# --- base path (P36.4 must be base-path-correct, like every other /api route) ---


def test_about_and_openapi_base_path_prefixed(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.setenv("ISAAC_BASE_PATH", "/krish")
    from isaac_api.app import create_app

    c = TestClient(create_app())

    # Unprefixed no longer exists.
    assert c.get("/api/about").status_code == 404
    assert c.get("/api/openapi").status_code == 404

    r_about = c.get("/krish/api/about")
    assert r_about.status_code == 200
    assert r_about.json()["record_schema_version"] == "1.05"

    r_openapi = c.get("/krish/api/openapi")
    assert r_openapi.status_code == 200
    paths = r_openapi.json()["paths"]
    # Under a base path, the generated schema's own paths carry the prefix too.
    assert "/krish/api/health" in paths
    assert "/krish/api/about" in paths


# =============================================================================
# P36V PR3 — the generated OpenAPI document is a PUBLISHED SURFACE
# =============================================================================
#
# `GET /api/openapi` serves every route's summary, description, parameter and
# response prose to the API Documentation browser. Those are consumer-facing
# words, so they are held to the same two standards `/api/about` already is:
#
#   1. They must not leak infrastructure, credentials, or absolute paths — the
#      SAME `_FORBIDDEN_SUBSTRINGS` tuple above, applied to the WHOLE document
#      with no exception list. (P36R's closure recorded this scan as deferred.)
#   2. They must not publish internal implementation detail: a private helper
#      name, a dunder, or an internal phase/slice number.
#
# The last three tests pin the CONTRACT (status codes and component schemas) so a
# future "documentation improvement" cannot silently move it. In particular
# `test_operations_with_parameters_keep_the_validation_error_schema` guards a real
# trap: FastAPI SKIPS its own 422 entry when a route declares 422 itself, which
# would drop the `HTTPValidationError` content ref.

_METHODS = ("get", "post", "put", "delete", "patch")


def _operations(schema: dict):
    """Yield ``(path, method, operation)`` for every operation in the document."""
    for path, item in sorted(schema["paths"].items()):
        for method in _METHODS:
            if method in item:
                yield path, method, item[method]


def _walk_api_routes(node):
    """Every ``APIRoute`` reachable from an app/router, at any nesting depth.

    ``include_router`` wraps the included routes in an internal container, so a
    flat pass over ``app.routes`` finds none of them.
    """
    for route in getattr(node, "routes", []):
        if isinstance(route, APIRoute):
            yield route
        else:
            yield from _walk_api_routes(route)
    # ``include_router`` stores the included router on the container it inserts.
    included = getattr(node, "original_router", None)
    if included is not None:
        yield from _walk_api_routes(included)


def _route_function_names(app) -> dict:
    """``(path, method) -> endpoint function name`` straight from the route table."""
    names = {}
    for route in _walk_api_routes(app):
        for method in route.methods:
            names[(route.path, method.lower())] = route.name
    return names


def _fastapi_default_summary(function_name: str) -> str:
    """FastAPI's auto-generated summary: the de-snake-cased function name."""
    return function_name.replace("_", " ").title()


# --- 1. leak scan over the WHOLE generated document -----------------------------


def test_openapi_contains_no_secret_or_infra_host_strings(client, tmp_path):
    """The same forbidden-substring scan `/api/about` gets, applied to every word
    of the generated document — summaries, descriptions, parameter and response
    prose, tag descriptions, and the app-level description.

    Reuses `_FORBIDDEN_SUBSTRINGS` verbatim. There is deliberately NO exception
    list: a description that would trip this scan is a description to rewrite.
    """
    r = client.get("/api/openapi")
    assert r.status_code == 200, r.text
    dumped = json.dumps(r.json()).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle.lower() not in dumped, f"unexpected leak: {needle!r} in /api/openapi"
    # Never leaks the local workspace path used by this very test.
    assert str(tmp_path).lower() not in dumped


# --- 2. every operation is documented for a human ------------------------------


def test_every_operation_has_a_summary_that_is_not_the_function_name(client):
    """A real check, not a tautology: the summary must differ from FastAPI's
    auto-generated de-snake-cased endpoint-function name (`Post Assistant Memory
    Query`, `Demo Reset`, `Get Draft`), which is what an undocumented route gets.
    """
    schema = client.get("/api/openapi").json()
    names = _route_function_names(client.app)
    checked = 0
    for path, method, op in _operations(schema):
        summary = (op.get("summary") or "").strip()
        assert summary, f"{method.upper()} {path} has no summary"
        function_name = names.get((path, method))
        assert function_name, (
            f"could not resolve the endpoint function for {method.upper()} {path} — "
            "the route-table walk needs updating"
        )
        auto = _fastapi_default_summary(function_name)
        assert summary != auto, (
            f"{method.upper()} {path} still carries FastAPI's auto summary "
            f"{auto!r} (from `{function_name}`)"
        )
        checked += 1
    assert checked == 35, f"expected 35 documented operations, found {checked}"


def test_the_auto_summary_check_can_actually_fail(client):
    """Guards the guard: prove `_fastapi_default_summary` reproduces the string the
    test above rejects, so that check is meaningful rather than vacuous."""
    assert _fastapi_default_summary("post_assistant_memory_query") == (
        "Post Assistant Memory Query"
    )
    assert _fastapi_default_summary("demo_reset") == "Demo Reset"
    assert _fastapi_default_summary("get_draft") == "Get Draft"


def test_every_operation_has_a_description(client):
    schema = client.get("/api/openapi").json()
    for path, method, op in _operations(schema):
        description = (op.get("description") or "").strip()
        assert description, f"{method.upper()} {path} has no description"
        assert len(description) > 40, (
            f"{method.upper()} {path} description is too thin to be useful: "
            f"{description!r}"
        )


def test_every_success_response_has_its_own_description(client):
    """The default is the bare string "Successful Response", which says nothing
    about the payload. Every operation states what its success body represents."""
    schema = client.get("/api/openapi").json()
    for path, method, op in _operations(schema):
        success = op["responses"].get("200")
        assert success is not None, f"{method.upper()} {path} documents no 200"
        assert success.get("description", "").strip() not in ("", "Successful Response"), (
            f"{method.upper()} {path} still has the default 200 description"
        )


# --- 3. no internal implementation detail is published -------------------------

#: A private helper reference (`_build_commit()`, `_detail(`), a dunder
#: (`__version__`), or an internal phase/slice marker (`P36.4`, `Phase 31`).
_INTERNAL_MARKERS = (
    re.compile(r"(?<![A-Za-z0-9])_[a-z][a-z0-9_]*\s*\("),
    re.compile(r"__[a-z_]+__"),
    re.compile(r"(?<![A-Za-z0-9])P\d{2}(\.\d+[a-z]?)?(?![A-Za-z0-9])"),
    re.compile(r"(?i)\bphase\s*\d"),
)


def _documentation_strings(schema: dict):
    """Every consumer-facing prose string in the document, with its location."""
    out: list[tuple[str, str]] = []
    info = schema.get("info", {})
    for key in ("summary", "description"):
        if info.get(key):
            out.append((f"info.{key}", info[key]))
    for tag in schema.get("tags", []):
        if tag.get("description"):
            out.append((f"tags[{tag['name']}]", tag["description"]))
    for path, method, op in _operations(schema):
        where = f"{method.upper()} {path}"
        for key in ("summary", "description"):
            if op.get(key):
                out.append((f"{where} {key}", op[key]))
        for param in op.get("parameters", []):
            for holder, label in ((param, "param"), (param.get("schema") or {}, "param.schema")):
                if holder.get("description"):
                    out.append((f"{where} {label}:{param['name']}", holder["description"]))
        body = op.get("requestBody") or {}
        if body.get("description"):
            out.append((f"{where} requestBody", body["description"]))
        for media in (body.get("content") or {}).values():
            if (media.get("schema") or {}).get("description"):
                out.append((f"{where} requestBody.schema", media["schema"]["description"]))
        for code, resp in op["responses"].items():
            if resp.get("description"):
                out.append((f"{where} {code}", resp["description"]))
    return out


def test_no_published_documentation_leaks_internal_implementation_detail(client):
    schema = client.get("/api/openapi").json()
    strings = _documentation_strings(schema)
    # Sanity: the collector really did find the prose (a silent empty list would
    # make this test vacuous).
    assert len(strings) > 100, f"only collected {len(strings)} documentation strings"
    for where, text in strings:
        for pattern in _INTERNAL_MARKERS:
            match = pattern.search(text)
            assert match is None, (
                f"{where} publishes internal detail {match.group(0)!r}: {text!r}"
            )


def test_the_internal_marker_patterns_can_actually_match(client):
    """Guards the guard above: each pattern matches the thing it is meant to catch."""
    samples = ("calls _build_commit() first", "reads __version__", "P36.4 slice", "Phase 31")
    for sample in samples:
        assert any(p.search(sample) for p in _INTERNAL_MARKERS), sample
    # ...and does not fire on legitimate public vocabulary in the real prose.
    for benign in (
        "reason `query_too_short`",
        "`mode: \"draft_only\"`",
        "`confirmed_by_user: true`",
        "`GET /api/experiments`",
    ):
        assert not any(p.search(benign) for p in _INTERNAL_MARKERS), benign


# --- 4. tags carry the grouping, and every tag is registered --------------------


def test_every_operation_is_tagged_with_a_registered_tag(client):
    schema = client.get("/api/openapi").json()
    registered = {tag["name"] for tag in schema.get("tags", [])}
    assert registered, "the document registers no tag definitions"
    used = set()
    for path, method, op in _operations(schema):
        tags = op.get("tags") or []
        assert len(tags) == 1, f"{method.upper()} {path} carries tags {tags!r}, expected one"
        assert tags[0] in registered, f"{method.upper()} {path} uses unregistered tag {tags[0]!r}"
        used.add(tags[0])
    # No dead tag definitions either.
    assert used == registered, f"registered but unused: {sorted(registered - used)}"


def test_registered_tags_match_the_module_level_definitions(client):
    schema = client.get("/api/openapi").json()
    assert schema["tags"] == OPENAPI_TAGS
    names = [tag["name"] for tag in OPENAPI_TAGS]
    assert len(names) == len(set(names)), f"duplicate tag name in {names}"
    assert all(tag.get("description", "").strip() for tag in OPENAPI_TAGS)


# --- 5. the CONTRACT is pinned: status codes and component schemas --------------

#: Every operation's documented response codes. Documentation edits must not move
#: this: an entry changing here means the API contract moved, not its prose.
EXPECTED_RESPONSE_CODES: dict[tuple[str, str], list[str]] = {
    ("/api/about", "get"): ["200", "401"],
    ("/api/assistant/memory/query", "post"): ["200", "400", "401", "422"],
    ("/api/demo/reset", "post"): ["200", "401", "403", "409", "422"],
    ("/api/demo/run", "post"): ["200", "401", "422"],
    ("/api/experiments", "get"): ["200", "401"],
    ("/api/experiments/{experiment_id}", "get"): ["200", "304", "401", "404", "422"],
    ("/api/experiments/{experiment_id}/answers", "post"): [
        "200", "400", "401", "404", "412", "422", "428",
    ],
    ("/api/experiments/{experiment_id}/artifacts", "get"): ["200", "401", "404", "422"],
    ("/api/experiments/{experiment_id}/assistant/query", "post"): [
        "200", "400", "401", "404", "422",
    ],
    ("/api/experiments/{experiment_id}/audit", "post"): ["200", "401", "404", "422"],
    ("/api/experiments/{experiment_id}/draft", "get"): ["200", "401", "404", "422"],
    ("/api/experiments/{experiment_id}/edit", "post"): [
        "200", "400", "401", "404", "412", "422", "428",
    ],
    ("/api/experiments/{experiment_id}/evidence", "get"): ["200", "401", "404", "422"],
    ("/api/experiments/{experiment_id}/evidence-classification", "get"): [
        "200", "401", "404", "422",
    ],
    ("/api/experiments/{experiment_id}/export", "post"): [
        "200", "400", "401", "404", "409", "412", "422", "428",
    ],
    ("/api/experiments/{experiment_id}/ingestion/csv/preview", "post"): [
        "200", "400", "401", "403", "404", "412", "413", "422", "428",
    ],
    ("/api/experiments/{experiment_id}/pending", "get"): ["200", "401", "404", "422"],
    ("/api/experiments/{experiment_id}/source-preview", "get"): [
        "200", "400", "401", "404", "422",
    ],
    ("/api/experiments/{experiment_id}/validate", "post"): ["200", "401", "404", "422"],
    ("/api/experiments/{experiment_id}/warnings", "get"): ["200", "401", "404", "422"],
    ("/api/experiments/{experiment_id}/warnings", "post"): ["200", "401", "404", "422"],
    ("/api/graph/status", "get"): ["200", "401"],
    # health stays open to unauthenticated probes, so it documents no 401.
    ("/api/health", "get"): ["200"],
    ("/api/memory/concepts", "get"): ["200", "401"],
    ("/api/memory/concepts/{concept_id}", "get"): ["200", "401", "404", "422"],
    ("/api/memory/file", "get"): ["200", "400", "401", "404", "422"],
    ("/api/memory/files", "get"): ["200", "401"],
    ("/api/memory/graph", "get"): ["200", "401"],
    ("/api/memory/graph/detail", "get"): ["200", "401"],
    ("/api/openapi", "get"): ["200", "401"],
    ("/api/runtime/records", "get"): ["200", "401", "422"],
    ("/api/schema", "get"): ["200", "401"],
    ("/api/search", "get"): ["200", "401", "422"],
    ("/api/uploads", "post"): ["200", "401", "403"],
    ("/api/validate/record", "post"): ["200", "401", "413", "422"],
}


def test_documented_response_codes_match_the_pinned_contract(client):
    schema = client.get("/api/openapi").json()
    actual = {
        (path, method): sorted(op["responses"].keys())
        for path, method, op in _operations(schema)
    }
    assert actual == EXPECTED_RESPONSE_CODES


def test_health_is_the_only_operation_without_a_documented_401(client):
    """Matches `ApiKeyAuthMiddleware`, which keeps exactly `{base}/api/health`
    open when the deployment enables authentication."""
    schema = client.get("/api/openapi").json()
    without = [
        f"{method.upper()} {path}"
        for path, method, op in _operations(schema)
        if "401" not in op["responses"]
    ]
    assert without == ["GET /api/health"]


#: The generated component schemas. A documentation change must not add, remove,
#: rename, or re-require a single field.
EXPECTED_COMPONENT_SCHEMAS: dict[str, dict] = {
    "AssistantQueryRequest": {
        "properties": ["grounded_rev", "history", "question"],
        "required": ["question"],
    },
    "DemoResetRequest": {"properties": ["confirmation", "mode"], "required": ["mode"]},
    "HTTPValidationError": {"properties": ["detail"], "required": []},
    "ValidationError": {
        "properties": ["ctx", "input", "loc", "msg", "type"],
        "required": ["loc", "msg", "type"],
    },
}


def test_component_schemas_match_the_pinned_contract(client):
    schema = client.get("/api/openapi").json()
    components = schema["components"]["schemas"]
    actual = {
        name: {
            "properties": sorted((body.get("properties") or {}).keys()),
            "required": sorted(body.get("required") or []),
        }
        for name, body in components.items()
    }
    assert actual == EXPECTED_COMPONENT_SCHEMAS


def test_operations_with_parameters_keep_the_validation_error_schema(client):
    """FastAPI SKIPS generating its own 422 when a route declares 422 itself, which
    silently drops the `HTTPValidationError` content ref. Every operation that has
    a parameter or a request body must still carry that ref, so a future
    `responses={422: ...}` cannot quietly strip the framework's own contract."""
    schema = client.get("/api/openapi").json()
    for path, method, op in _operations(schema):
        if not (op.get("parameters") or op.get("requestBody")):
            continue
        response = op["responses"].get("422")
        assert response is not None, f"{method.upper()} {path} lost its 422"
        ref = response["content"]["application/json"]["schema"]["$ref"]
        assert ref == "#/components/schemas/HTTPValidationError", (
            f"{method.upper()} {path} 422 no longer references HTTPValidationError"
        )
