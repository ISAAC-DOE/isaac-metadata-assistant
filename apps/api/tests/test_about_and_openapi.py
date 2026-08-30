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
    # WITH NO `PGHOST` THIS IS STILL `ephemeral`, AND THAT IS THE POINT OF THE
    # THREE TESTS BELOW. It is no longer a literal — it is the repository's own
    # answer — but on a developer machine and in CI the repository resolves to
    # the filesystem, so the derived value and the retired literal agree. This
    # assertion therefore CANNOT distinguish the fix from the defect, and a
    # regression to a hardcoded `"ephemeral"` would leave it green. The
    # `durable` / `unavailable` branches are covered separately, and one of
    # them is written specifically to fail against the retired literal.
    assert body["persistence"] == "ephemeral"
    assert body["data_regime"] == "synthetic-only"
    assert body["core"] == "isaac_records"
    assert isinstance(body["app_version"], str) and body["app_version"]


# --- `persistence` is DERIVED, and the local value cannot prove it -------------
#
# THE DEFECT THESE TESTS EXIST FOR. `GET /api/about` served
# `"persistence": "ephemeral"` as a hardcoded literal. On the hosted deployment
# that was FALSE and the SAME PROCESS contradicted it: `GET /api/health` reported
# `experiment_storage.state: "durable"`, and two experiments created 17 and 18
# days earlier were still being served (`docs/evidence/hosted-qa-2026-08-27.md`
# §3). The operation's published description asserted the two "can never
# disagree" while they disagreed in production.
#
# WHY THE SUITE ABOVE COULD NOT SEE IT, AND WHY THAT IS NOT A TESTING FAILURE.
# Every test in this file runs with `PGHOST` unset, so
# `experiment_repository._postgres_available` is false, the repository resolves
# to the filesystem, and `"ephemeral"` is the TRUE answer. The literal and the
# derivation agree on every developer machine and in CI. Only a
# Postgres-configured deployment can falsify the literal — which is exactly the
# environment no test in this repository is permitted to create, because
# connecting to a database is out of scope by project rule.
#
# SO THE STATE IS INJECTED, NOT CONFIGURED. These tests monkeypatch
# `experiment_repository.storage_status`, which is the one function `/health`
# already serves verbatim and the one `/about` now reads. NOTHING here sets
# `PGHOST`, opens a connection, or reaches a database: the whole point of
# `storage_status` is that it opens nothing, and substituting it keeps that
# property absolutely rather than by inspection.
#
# `test_about_reports_durable_when_the_repository_does` is the NEGATIVE CONTROL.
# It is the one test in this file that FAILS against the retired literal, and it
# is why the `== "ephemeral"` assertion above is allowed to stay.


def _pin_storage_state(monkeypatch, state: str) -> None:
    """Make `storage_status` report one state, opening nothing.

    The whole block is substituted rather than only `state`, because `/health`
    serves this dict verbatim and a half-real dict would let a test assert
    agreement between two halves of one fabricated value. Every key is spelled
    out so the shape stays the shape the route contract publishes.
    """
    from isaac_api import experiment_repository

    monkeypatch.setattr(
        experiment_repository,
        "storage_status",
        lambda env=None: {
            "configured": state != "ephemeral",
            "backend": "postgres" if state == "durable" else "filesystem",
            "durable": state == "durable",
            "state": state,
            "run_projection": {"authoritative": False, "last_pass": None},
        },
    )


def test_about_reports_durable_when_the_repository_does(client, monkeypatch):
    """THE NEGATIVE CONTROL. Fails against the hardcoded `"ephemeral"` literal.

    Against the defect this reads::

        AssertionError: assert 'ephemeral' == 'durable'

    which is the hosted defect reproduced in a unit test, with no database
    anywhere near it.
    """
    _pin_storage_state(monkeypatch, "durable")
    assert client.get("/api/about").json()["persistence"] == "durable"


def test_about_reports_unavailable_when_the_repository_does(client, monkeypatch):
    """The third state, which is neither reassuring nor ephemeral.

    `unavailable` means a database IS configured and experiment records are NOT
    reaching it. Reporting `ephemeral` there would be the mirror image of the
    original defect — it would tell a reader their work is going somewhere
    temporary while saying nothing about the database that is failing them.

    ~~"in fact it is not being accepted at all"~~ — corrected in review, before
    this file was a day old, because it is the same over-reading of `state` that
    the copy defect downstream came from. `unavailable` has TWO causes and only
    one of them refuses the write; see
    `test_the_pgdatabase_gate_degrades_to_a_working_create_that_is_not_durable`
    below, which measures the other.
    """
    _pin_storage_state(monkeypatch, "unavailable")
    assert client.get("/api/about").json()["persistence"] == "unavailable"


@pytest.mark.parametrize("state", ["ephemeral", "durable", "unavailable"])
def test_about_and_health_cannot_disagree_about_persistence(client, monkeypatch, state):
    """The property the published description now claims, asserted directly.

    The description says the two operations "cannot disagree about it". That was
    an intention while `/about` held a literal; it is a consequence now that both
    read the same function. This asserts the consequence in all three states
    rather than trusting the sentence.

    AND IT IS EXACTLY AS BOUNDED AS THE SENTENCE NOW IS. Both requests are served
    by ONE process here, which is the only scope in which the claim holds:
    `storage_status` reads `storage_failure()`, which `experiment_repository`'s
    module docstring documents as process-local ("each replica observes its own
    failures"). Nothing in this repository can test across replicas, so the
    published sentence says "within one server process" rather than resting on a
    test whose single-process scope is invisible in its name.
    """
    _pin_storage_state(monkeypatch, state)
    about = client.get("/api/about").json()
    health = client.get("/api/health").json()
    assert about["persistence"] == health["experiment_storage"]["state"] == state


# --- `unavailable` has TWO causes, and copy that assumes one of them is false --
#
# THE DEFECT THIS PINS. The change that derived `persistence` also rewrote the
# five governance surfaces that render it, and the `unavailable` copy asserted
# "Creating an experiment fails outright rather than storing one temporarily, so
# nothing is put somewhere for a while and then lost." `lib/labels.ts` carried
# the same belief already ("Creating an experiment will not work until it does").
#
# That is true when the database is SELECTED and not answering. It is false when
# the `PGDATABASE` gate refuses the configured NAME: `_postgres_available()`
# returns False, `repository()` hands back `FilesystemExperimentRepository`, and
# the create SUCCEEDS into the working directory — which its own docstring
# documents as the intended degradation. A scientist whose operator mistyped
# `PGDATABASE` is told the create fails, gets a record, and concludes it is
# durable.
#
# NO DATABASE IS CONTACTED, and that is enforced rather than reasoned about:
# `db_write.connect_psycopg2` is replaced by a raiser, so if the gate ever stops
# refusing this configuration the test fails loudly instead of opening a socket.
# The one function under test opens nothing by design.


@pytest.fixture()
def _clean_storage_observation():
    """`_storage_failure` is a MODULE GLOBAL, so it must not leak either way.

    One of these tests deliberately induces a durable-write failure. Without this
    the observation would survive into every later test in the process and make
    `storage_status()` report `unavailable` for reasons that test knows nothing
    about — the same shape of cross-test leak the schema-cache fixture in
    `test_system_enum_fields.py` exists to prevent.
    """
    from isaac_api import experiment_repository

    experiment_repository.forget_storage_failure()
    yield
    experiment_repository.forget_storage_failure()


def test_the_pgdatabase_gate_degrades_to_a_working_create_that_is_not_durable(
    tmp_path, monkeypatch, _clean_storage_observation
):
    """`state: unavailable`, `backend: filesystem`, and `POST /api/experiments` -> 201.

    The two facts a surface must not collapse: the state says records are not
    reaching a configured database, and the create nevertheless succeeds — into
    storage the same block reports as `durable: false`.
    """
    from fastapi.testclient import TestClient

    from isaac_api import db_write, experiment_repository
    from isaac_api.app import create_app

    def _never(*args, **kwargs):
        raise AssertionError("this test must not open a database connection")

    monkeypatch.setattr(db_write, "connect_psycopg2", _never)
    monkeypatch.setenv("PGHOST", "db.example.invalid")
    monkeypatch.setenv("PGDATABASE", "not_the_expected_name")
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)

    status = experiment_repository.storage_status()
    assert status["state"] == "unavailable"
    assert status["backend"] == "filesystem"
    assert status["configured"] is True
    assert status["durable"] is False
    assert isinstance(
        experiment_repository.repository(),
        experiment_repository.FilesystemExperimentRepository,
    )

    local = TestClient(create_app(), raise_server_exceptions=False)
    assert local.get("/api/about").json()["persistence"] == "unavailable"
    created = local.post("/api/experiments", json={"title": "degraded create"})
    # THE ASSERTION THE RETIRED COPY WOULD HAVE FAILED.
    assert created.status_code == 201, created.text
    listed = local.get("/api/experiments").json()["experiments"]
    assert [row["id"] for row in listed] == [created.json()["id"]]


def test_the_selected_database_not_answering_refuses_the_create(
    tmp_path, monkeypatch, _clean_storage_observation
):
    """The OTHER cause of the same state, so the pair is measured and not assumed.

    Same `state`, opposite outcome: `backend: postgres` and a typed `503` having
    written nothing. Still no connection — the connector itself is what raises.
    """
    from fastapi.testclient import TestClient

    from isaac_api import db_recon, db_write, experiment_repository
    from isaac_api.app import create_app

    class _Down(Exception):
        pass

    def _down(*args, **kwargs):
        raise _Down("no connection is attempted in this test")

    monkeypatch.setattr(db_write, "connect_psycopg2", _down)
    monkeypatch.setenv("PGHOST", "db.example.invalid")
    monkeypatch.setenv("PGDATABASE", db_recon.EXPECTED_DATABASE)
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)

    local = TestClient(create_app(), raise_server_exceptions=False)
    created = local.post("/api/experiments", json={"title": "refused create"})
    assert created.status_code == 503, created.text
    assert created.json()["error"] == "experiment_storage_unavailable"

    status = experiment_repository.storage_status()
    assert status["state"] == "unavailable"
    assert status["backend"] == "postgres"
    assert local.get("/api/experiments").json()["experiments"] == []


def test_about_persistence_is_always_one_of_the_three_named_states(client):
    """No fourth value, and the names are the repository's own constants — not a
    second copy of three strings that could drift from the ones `/health` uses."""
    from isaac_api.experiment_repository import (
        STORAGE_STATE_DURABLE,
        STORAGE_STATE_EPHEMERAL,
        STORAGE_STATE_UNAVAILABLE,
    )

    assert client.get("/api/about").json()["persistence"] in {
        STORAGE_STATE_DURABLE,
        STORAGE_STATE_EPHEMERAL,
        STORAGE_STATE_UNAVAILABLE,
    }


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
    # 39 -> 40: `POST /api/experiments`, the durable Create Experiment path. It is
    # the first record-creation operation this API has ever published.
    # 40 -> 45: the Run HTTP API. The Run domain model already existed in
    # `workspace` (one run exports one official record); these five operations
    # expose it — list, add, read, edit, and check one run.
    # 45 -> 47: the run OVERRIDE operations. The override machinery also already
    # existed in `workspace` (`set_run_override` / `clear_run_override`, with
    # `Override` recording what it displaced) and had NO caller outside its own
    # tests; these two expose it — record one, and clear one.
    # 47 -> 51: Unmapped Notes. Unlike the two entries above, this model did NOT
    # already exist in `workspace` — `isaac_api/notes.py` is new — but the storage
    # does: a note lives inside the experiment's own state document exactly as a
    # run does, and no table or migration was added. The four operations are list,
    # capture, read one, and perform one review act on one.
    #
    # 51 -> 52: `POST /api/experiments/{experiment_id}/submit`, the scientist's
    # submission. It is deliberately a SEPARATE operation from the export beside it
    # rather than a flag on it: exporting is a mechanical transform anyone can run,
    # and submitting is an attributable declaration by a named person, so deriving
    # one from the other would attribute a declaration nobody made.
    #
    # THE TWO ENTRIES ABOVE ARRIVED ON SEPARATE BRANCHES AND BOTH COUNTED FROM 47.
    # Notes wrote 51, submission wrote 48, and the merge of the two is neither: it
    # is 47 + 4 + 1. This is the same shape as the a11y total that two branches each
    # raised by seven, and the fix is the same — the number is MEASURED from
    # `create_app().openapi()` after the merge, never carried across it.
    #
    # MEASURED from `create_app().openapi()` on the MERGED tree. The arithmetic is
    # deliberately not shown, because doing the arithmetic is how this goes wrong:
    # four slices have now raised this literal from 52 for real, different additions
    # — the asset slice, the transcript slice, run removal
    # (`POST .../runs/{run_id}/remove`), and this one, which adds the two CONFLICT
    # RESOLUTION operations: read the disagreements a record's own evidence carries,
    # and record which competing answer a scientist stands behind.
    #
    # Both sides of this merge conflict carried a number that was correct for its own
    # branch and wrong for the merge. Neither was kept. `create_app().openapi()` is
    # the authority and was re-run on the merged tree.
    #
    # 66 -> 68: the two RUN-LEVEL WRITE operations,
    # `POST .../runs/{run_id}/answers` and `.../edit`. They exist because a spectrum, a
    # QC verdict, a descriptor and an asset hash belong to the run that measured them —
    # the record's own `/answers` now refuses them with `409 belongs_to_a_run` once runs
    # exist, and refusing without somewhere to send the answer would leave a multi-run
    # record unfinishable.
    #
    # 68 -> 69: `POST /api/assistant/ask`, the assistant SEAM operation. It answers
    # `501` in every deployment — the deterministic fake is deliberately unreachable
    # through a booted application — and it exists so that "is there a native
    # assistant?" is answered by the server rather than by a string compiled into
    # the browser bundle. It is not `POST /api/assistant/memory/query`, which is the
    # shipped deterministic Q&A and involves no provider.
    #
    # 69 -> 70: `PATCH /api/experiments/{experiment_id}`, the rename. Until it
    # existed, `title` was written exactly once — by `POST /api/experiments` — and no
    # operation could change it, so with `0001_experiments` applied to the hosted
    # database a typo made at create time was durable and permanent. It writes the
    # title and nothing else; the free-text note the create operation accepts is
    # deliberately NOT editable here, because it is stored at `source.description`,
    # which `workspace.classify_experiment` also reads as a provenance marker.
    #
    # 70 -> 71: `POST /api/experiments/{experiment_id}/discard`. Until it existed,
    # `POST /api/experiments` could create a record and NOTHING could take one away
    # — the reset one file over says so in its own description ("there is
    # deliberately no general per-experiment delete operation"), and that sentence
    # is still true: this is a narrow domain operation, not a generic delete. It
    # refuses, writing nothing, anything that has ever been submitted, has exported
    # under its own identity, has an exported run, has a published artifact on disk,
    # or is a built-in worked example. It is a `POST .../discard` rather than an
    # HTTP `DELETE` deliberately — a `DELETE` verb on `/experiments/{id}` would tell
    # every client the resource is generically deletable, which is exactly what was
    # not authorized.
    #
    #
    # 71 -> 75: PERSISTENT INGESTION PROPOSALS — list, create, read one, and perform
    # one review act on one. Four operations, the same shape as the four Unmapped
    # Notes operations one section over, and for the same reason: this is the
    # destination for the VALUED half of a proposal, which until now did not survive
    # the request. `providers/extraction.py`'s `FieldCandidate` is a valued proposal
    # deliberately never stored; a note carries the target and the rule and
    # deliberately carries no value. These four close that gap and no other.
    #
    # NO TABLE AND NO MIGRATION WAS ADDED. A proposal lives at `state["proposals"]`
    # inside the experiment's own state document, beside `notes`, so `db_write.
    # OWNED_TABLES` is unchanged — the first scope extension in `CLAUDE.md` §15 that
    # adds none, deliberately.
    #
    # MEASURED from `create_app().openapi()`, not derived from the line above it.
    assert checked == 75, f"expected 75 documented operations, found {checked}"


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
    about the payload. Every operation states what its success body represents.

    Checked against the operation's DECLARED success code rather than a hard-coded
    `200`, because not every success is a `200` — opening a worked-example session is
    `201` and discarding one is `204`. The exactly-one assertion is deliberate and is
    strictly stronger than the previous form: an operation with two success codes has
    an ambiguous contract, and this now says so instead of silently checking one of
    them.
    """
    schema = client.get("/api/openapi").json()
    for path, method, op in _operations(schema):
        success_codes = sorted(c for c in op["responses"] if c.startswith("2"))
        assert len(success_codes) == 1, (
            f"{method.upper()} {path} declares {success_codes} as success codes; "
            "exactly one is expected"
        )
        success = op["responses"][success_codes[0]]
        assert success.get("description", "").strip() not in ("", "Successful Response"), (
            f"{method.upper()} {path} still has the default "
            f"{success_codes[0]} description"
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
#:
#: `503` APPEARS ON 24 OPERATIONS, AND IT USED TO APPEAR ON ONE. That one was
#: `POST /api/experiments`, for its write — while `workspace.load_experiment`
#: raises the same durable-storage outage on every read that resolves a record by
#: id, and `Experiment.save` on every write. So this table said
#: `["200", "304", "401", "404", "422"]` for `GET /api/experiments/{experiment_id}`
#: and the deployed application answered `503`, which is a contract that denies a
#: state its own implementation produces. The set was DERIVED — every handler that
#: reaches `ws.load_experiment` or a write-through save — not chosen by taste.
#:
#: THREE RECORD-TOUCHING OPERATIONS ARE DELIBERATELY NOT IN IT, and each absence
#: is a claim that can be checked. `POST /api/demo/run` and `POST /api/demo/reset`
#: refuse `scope is None` BEFORE they touch a record, so every read they make
#: carries a session id, and a session-scope read never consults the database
#: (`workspace.load_experiment` returns `None` for a session miss without
#: hydrating). `GET /api/experiments` degrades instead of failing, on purpose, and
#: discloses that it did — see its `incomplete` block.
EXPECTED_RESPONSE_CODES: dict[tuple[str, str], list[str]] = {
    ("/api/about", "get"): ["200", "401"],
    ("/api/assistant/memory/query", "post"): ["200", "400", "401", "422"],
    # 412/428 are the R1 reset precondition: `plan_digest` stale / omitted. They
    # mirror the per-record If-Match convention on the mutation routes below, which
    # is why they read the same here.
    # 404 on every scope-resolving operation is the fail-closed arm of the
    # worked-example session header: present but naming no existing session. It is
    # never answered from the ordinary workspace instead.
    ("/api/demo/reset", "post"): [
        "200", "401", "403", "404", "409", "412", "422", "428",
    ],
    ("/api/demo/run", "post"): ["200", "401", "404", "409", "422"],
    ("/api/experiments", "get"): ["200", "401", "404", "422"],
    # 201 rather than 200: the response describes a resource that did not exist
    # before the request. 409 is the ORDINARY-SCOPE requirement — the mirror image
    # of `/api/demo/run`'s `tutorial_scope_required`: this operation refuses when a
    # worked-example session header IS present, because a session is discarded on a
    # timer and a record a person created must not inherit that.
    # `503` is the durable-storage outage: this deployment stores experiments in
    # its own database and that database did not take the write. It is documented
    # rather than left as an undeclared failure because it is REACHABLE on the
    # deployed pod — `PGHOST` is set there and the migration is applied by an
    # operator, so there is a window in which the table does not exist yet. The
    # create fails; it is never quietly degraded to an ephemeral write.
    # `412` is the durable compare-and-swap REFUSING the write — a different
    # condition from `503` and deliberately not folded into it: the database
    # answered, and declined. On this route it needs an id collision, so it is
    # documented because the response is declared and reachable through the app's
    # `DurableWriteConflict` handler, not because it is expected. It carries no
    # `400`/`428` companions, unlike the record write operations, because a create
    # has no `If-Match` to be malformed or omitted.
    ("/api/experiments", "post"): ["201", "401", "404", "409", "412", "422", "503"],
    ("/api/experiments/{experiment_id}", "get"): ["200", "304", "401", "404", "422", "503"],
    # The rename. `409` is the worked-example refusal, and it is the same code
    # `POST /api/experiments` documents for the same reason: this operation acts on
    # the ordinary workspace only. The 400/412/428 trio is the shared `If-Match`
    # precondition block every record write carries.
    (
        "/api/experiments/{experiment_id}",
        "patch",
    ): ["200", "400", "401", "404", "409", "412", "422", "428", "503"],
    # 409: `belongs_to_a_run`. An independent review found all three of these routes
    # emitting a live 409 that this table did not list — so the guard that exists to
    # pin the contract was certifying one that omitted a status a client will see.
    ("/api/experiments/{experiment_id}/answers", "post"): ["200", "400", "401", "404", "409", "412", "422", "428", "503"],
    ("/api/experiments/{experiment_id}/artifacts", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/assistant/query", "post"): ["200", "400", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/audit", "post"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/draft", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/edit", "post"): ["200", "400", "401", "404", "409", "412", "422", "428", "503"],
    ("/api/experiments/{experiment_id}/evidence", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/evidence-classification", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/export", "post"): ["200", "400", "401", "404", "409", "412", "422", "428", "503"],
    # THE SAME NINE AS THE EXPORT BESIDE IT, and the overlap is not a coincidence:
    # submit runs the export gate unchanged and materialises through the same
    # helper, so every refusal export can produce, submit can produce. The `400` is
    # a malformed `If-Match` OR a malformed `Idempotency-Key` — both are malformed
    # HEADERS, which is why they share a code rather than one of them being a 422.
    # The `409` carries six distinct `error` values (see the operation's own
    # description); the `503` is "this deployment cannot record a submission at
    # all", which is a different fact from the shared storage-outage 503 and says so
    # in its body.
    ("/api/experiments/{experiment_id}/submit", "post"): ["200", "400", "401", "404", "409", "412", "422", "428", "503"],
    # The three submission-history READS. 503 is declared because it is REACHABLE
    # and is the operation's normal answer on a deployment whose history migration
    # an operator has not applied — which is the hosted one. It covers both 503s
    # these handlers can produce (see `routes._R_REVISION_HISTORY_UNAVAILABLE`).
    # 404 on the two per-revision operations is TWO facts, distinguished by the
    # body's `error`: no such record, and no such revision on a record that exists.
    ("/api/experiments/{experiment_id}/revisions", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/revisions/{revision_no}", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/revisions/{revision_no}/diff", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/ingestion/csv/preview", "post"): ["200", "400", "401", "403", "404", "412", "413", "422", "428", "503"],
    ("/api/experiments/{experiment_id}/pending", "get"): ["200", "401", "404", "422", "503"],
    # The two-dimension provenance view. One `404` covers both "no such record"
    # and "this record has no such run" — the bodies differ (`experiment_not_found`
    # vs `run_not_found`), the documented status does not.
    ("/api/experiments/{experiment_id}/provenance", "get"): ["200", "401", "404", "422", "503"],
    # Unmapped Notes. The split is the Run API's, for the Run API's reason: a note
    # is stored INSIDE the experiment's own document, so capturing one and reviewing
    # one both REWRITE THE RECORD and carry the record's `If-Match` with the whole
    # 400/412/428 set. There is deliberately no per-note validator, and deliberately
    # NO DELETE — dismissal is a review act on the review operation, so it appears
    # here as a `200` on a POST and not as a `204` anywhere.
    # The ASSET REFERENCE API. The library lives in the experiment's draft and the
    # associations live in each run's draft — both inside the one experiment document
    # — so all three writes carry the RECORD's `If-Match` and the whole 400/412/428
    # set with it, exactly as `POST .../runs` does. There is no DELETE: removal is a
    # sub-path POST, matching `.../notes/{id}/review` and `.../overrides/clear`.
    ("/api/experiments/{experiment_id}/assets", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/assets", "post"): ["201", "400", "401", "404", "412", "422", "428", "503"],
    ("/api/experiments/{experiment_id}/assets/{asset_id}", "patch"): ["200", "400", "401", "404", "412", "422", "428", "503"],
    ("/api/experiments/{experiment_id}/assets/{asset_id}/remove", "post"): ["200", "400", "401", "404", "412", "422", "428", "503"],
    # CONFLICT RESOLUTION. The read is the only surface that shows a scientist the
    # competing values, so it is a plain read with the record's `ETag`. Recording a
    # decision REWRITES THE RECORD — one record-level list inside the experiment's
    # own document holds run-scoped decisions too — so it carries the RECORD's
    # `If-Match` and the whole 400/412/428 set with it, exactly as capturing a note
    # does, and there is deliberately no separate validator for a decision. Its
    # `422` covers the missing confirmation, an unknown or non-conflicting address,
    # an unknown run, an unknown outcome or `chosen_from`, a `candidate` value that
    # is none of the competing answers, and a wrong-typed body; on every one of them
    # nothing is written. There is NO DELETE: a decision is revised, which appends.
    ("/api/experiments/{experiment_id}/conflicts", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/conflicts/resolve", "post"): ["200", "400", "401", "404", "412", "422", "428", "503"],
    # PERSISTENT INGESTION PROPOSALS. The split is the Notes API's, for the Notes
    # API's reason: a proposal is stored INSIDE the experiment's own document, so
    # creating one and reviewing one both REWRITE THE RECORD and carry the record's
    # `If-Match` with the whole 400/412/428 set. There is deliberately no per-proposal
    # validator, and deliberately NO DELETE — rejecting, superseding and withdrawing
    # are review acts on the review operation, so they appear here as a `200` on a
    # POST and not as a `204` anywhere.
    #
    # THE CREATE IS THE ONE POST IN THIS TABLE THAT CREATES AND DOES NOT ANSWER `201`,
    # and that is deliberate rather than an oversight — see the comment above the
    # route. It has TWO outcomes: it mints a proposal, or it finds one already
    # carrying the caller's `client_request_key` and mints nothing. An operation-level
    # `201` would assert that this operation creates, which is false of the second, and
    # `test_every_success_response_has_its_own_description` (rightly) refuses the two
    # success codes that would let it say both. The status says the request succeeded;
    # the body's `deduplicated` says which happened.
    #
    # The review POST's `409` carries four distinct refusals — `human_actor_required`,
    # `proposal_stale`, `target_run_removed` and `target_scope_mismatch` — and every
    # one of them writes nothing. The two reads take no `If-Match` because they write
    # nothing; the list's `422` is its own `unknown_cursor` refusal as well as the
    # framework's parameter validation, which is why the operation declares it.
    ("/api/experiments/{experiment_id}/proposals", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/proposals", "post"): [
        "200", "400", "401", "404", "412", "422", "428", "503",
    ],
    ("/api/experiments/{experiment_id}/proposals/{proposal_id}", "get"): [
        "200", "401", "404", "422", "503",
    ],
    ("/api/experiments/{experiment_id}/proposals/{proposal_id}/review", "post"): [
        "200", "400", "401", "404", "409", "412", "422", "428", "503",
    ],
    ("/api/experiments/{experiment_id}/notes", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/notes", "post"): ["201", "400", "401", "404", "412", "422", "428", "503"],
    ("/api/experiments/{experiment_id}/notes/{note_id}", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/notes/{note_id}/review", "post"): ["200", "400", "401", "404", "412", "422", "428", "503"],
    # Transcript capture. Storing a finalized transcript REWRITES THE RECORD — every
    # segment of it becomes a note inside the record's own document — so it carries
    # the record's `If-Match` and the whole 400/412/428 set, exactly as capturing a
    # note does. Its `422` covers the finalize gate, an unknown body key, an unknown
    # run, the segment ceiling and a retention state this build cannot enforce; on
    # every one of them nothing is stored.
    ("/api/experiments/{experiment_id}/transcript", "post"): ["200", "400", "401", "404", "412", "422", "428", "503"],
    # The Run API. Adding a run REWRITES THE RECORD, so `POST .../runs` carries the
    # record's `If-Match` and the whole 400/412/428 set with it. `PATCH
    # .../runs/{run_id}` carries THE RUN's instead — the same three codes, a
    # different validator. The two read operations and the check take none, because
    # they write nothing.
    ("/api/experiments/{experiment_id}/runs", "get"): ["200", "401", "404", "422", "503"],
    # 409: `already_exported_without_runs`.
    ("/api/experiments/{experiment_id}/runs", "post"): ["201", "400", "401", "404", "409", "412", "422", "428", "503"],
    ("/api/experiments/{experiment_id}/runs/{run_id}", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/runs/{run_id}", "patch"): ["200", "400", "401", "404", "412", "422", "428", "503"],
    # The two override operations carry THE RUN's `If-Match` exactly as the run PATCH
    # does, so they carry the same 400/412/428 set. Their `422` is the address gate,
    # the payload-shape gate and the missing confirmation; on every one of them
    # nothing is written.
    ("/api/experiments/{experiment_id}/runs/{run_id}/overrides", "post"): ["200", "400", "401", "404", "412", "422", "428", "503"],
    ("/api/experiments/{experiment_id}/runs/{run_id}/overrides/clear", "post"): ["200", "400", "401", "404", "412", "422", "428", "503"],
    # The two RUN-LEVEL WRITE operations. Same code set as the record's `/answers` and
    # `/edit`, because they are the same operation on a different entity — including the
    # `412` that a RUN's own `If-Match` produces, which is what keeps a client editing
    # run B from being defeated by a concurrent write to run A.
    ("/api/experiments/{experiment_id}/runs/{run_id}/answers", "post"): [
        "200", "400", "401", "404", "412", "422", "428", "503",
    ],
    ("/api/experiments/{experiment_id}/runs/{run_id}/edit", "post"): [
        "200", "400", "401", "404", "412", "422", "428", "503",
    ],
    ("/api/experiments/{experiment_id}/runs/{run_id}/check", "post"): ["200", "401", "404", "422", "503"],
    # Removing a run REWRITES THE RECORD — a run lives inside the record's document
    # — so this carries the RECORD's `If-Match` and the whole 400/412/428 set with
    # it, exactly as `POST .../runs` and `POST .../assets/{id}/remove` do. There is
    # no DELETE: removal is a sub-path POST, the shape every other removal in this
    # API uses. The `409` is its own refusal and appears on no other run operation:
    # the run has been exported, so removing it would orphan a written official
    # record, and it is refused with nothing written.
    ("/api/experiments/{experiment_id}/runs/{run_id}/remove", "post"): ["200", "400", "401", "404", "409", "412", "422", "428", "503"],
    # DISCARD. The same code set as run removal, and for the same reasons: it
    # rewrites nothing but removes the whole record, so it carries the RECORD's
    # `If-Match` and the whole 400/412/428 set. There is no `DELETE` verb — removal
    # is a sub-path POST, the shape every other removal in this API uses, and a
    # `DELETE` on `/experiments/{id}` would advertise a generic deletability that
    # was never authorized.
    #
    # THE `409` CARRIES SIX DISTINCT REFUSALS and the `503` carries TWO DIFFERENT
    # FACTS, which is why neither is collapsible into the other. The 409s are all
    # about the RECORD (submitted, exported, an exported run, a published artifact
    # on disk, a canonical example, or the database's own foreign key refusing);
    # the 503s are about the SERVER (durable storage did not accept the removal, or
    # the submission history could not be read so the one question that decides
    # this has no answer). Every one of the eight writes nothing.
    ("/api/experiments/{experiment_id}/discard", "post"): ["200", "400", "401", "404", "409", "412", "422", "428", "503"],
    ("/api/experiments/{experiment_id}/source-preview", "get"): ["200", "400", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/validate", "post"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/warnings", "get"): ["200", "401", "404", "422", "503"],
    ("/api/experiments/{experiment_id}/warnings", "post"): ["200", "401", "404", "422", "503"],
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
    # The model-seam capability report. A read of this build's own constants: it
    # opens no connection and reads no credential, so it has no failure of its own
    # to document.
    ("/api/providers/capabilities", "get"): ["200", "401"],
    # `501` is the seam having no provider in this deployment — a statement about
    # the deployment, not a fault and not a wait. `422` is the SEPARATE case of a
    # request that supplied nothing to work on. They are deliberately different
    # codes: a caller who retried the first would be waiting for a decision nobody
    # has made.
    ("/api/transcription", "post"): ["200", "401", "422", "501"],
    # THE ASSISTANT SEAM, and its codes are deliberately the transcription seam's.
    # 501 = no provider is configured in this deployment, which is an institutional
    # decision and not a wait; 422 = the request is not askable, or the context it
    # supplied does not cover the question. Collapsing the two would tell a client
    # to retry something nobody has decided to build.
    ("/api/assistant/ask", "post"): ["200", "401", "422", "501"],
    # 409 = a reconnaissance scan is already running; nothing is connected to.
    ("/api/runtime/database/recon", "get"): ["200", "401", "409"],
    ("/api/schema", "get"): ["200", "401"],
    ("/api/runtime/records", "get"): ["200", "401", "404", "422"],
    # 422 joins the pair when the route gains its `mode` query parameter: FastAPI
    # documents a validation response for any operation that takes one. It is a
    # SHAPE error only -- an unrecognised mode is not a 422, it is a 200 carrying
    # `status: "refused"`, because refusing is a result the reader must see
    # rather than a malformed request.
    ("/api/runtime/verification", "get"): ["200", "401", "422"],
    ("/api/search", "get"): ["200", "401", "404", "422"],
    ("/api/tutorial/sessions", "post"): ["201", "401"],
    ("/api/tutorial/sessions/{session_id}", "delete"): ["204", "401", "422"],
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
    # `plan_digest` (R1) is the execute precondition. It is deliberately NOT required
    # by the schema: `preview` has no precondition, so requiring it at the model level
    # would reject a perfectly valid preview. The route enforces it for `execute`
    # only, and enforces it fail-closed (omitted -> 428, no mutation).
    #
    # NOTE ON THE NAME. It is `plan_digest`, not `plan_token`, because
    # `test_openapi_contains_no_secret_or_infra_host_strings` forbids the substring
    # "token" anywhere in the generated document — a blunt credential-leak scan with
    # a deliberate no-exception policy. Weakening that scan to spell a
    # non-credential field name the industry way would be the wrong trade.
    "DemoResetRequest": {
        "properties": ["confirmation", "mode", "plan_digest"],
        "required": ["mode"],
    },
    # `extra="forbid"` is what makes "no client-supplied record id" a property of
    # the contract rather than of the handler remembering not to read one, so the
    # SHORTNESS of this property list is the assertion that matters: two fields, one
    # required, and anything else is a 422.
    "CreateExperimentRequest": {
        "properties": ["description", "title"],
        "required": ["title"],
    },
    # The rename. ONE property, and the shortness is again the assertion: `title`
    # and nothing else. `description` is deliberately absent — the create operation
    # accepts one and stores it at `source.description`, which
    # `workspace.classify_experiment` also reads as the provenance marker deciding
    # whether a record belongs to the managed demo dataset. `extra="forbid"` is what
    # makes "a rename does not write a deletion classifier" a property of the
    # contract rather than of the handler remembering not to read the key.
    "RenameExperimentRequest": {"properties": ["title"], "required": ["title"]},
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


# --- the removed temporary identity probe stays removed -------------------------
#
# `POST /api/runtime/identity/probe` was a TEMPORARY identity-observation probe
# (Workstream B, 2026-08-01). It was observed once against hosted commit `d521dd7`
# / image `v0.0.42` and then deleted, together with `isaac_api/identity_probe.py`,
# its test module, and `docs/identity-probe.md`.
#
# This lives beside the three pinned contracts above deliberately: those pins say
# what the generated document DOES contain, and they were each edited by the
# removal. This one says what it must NOT contain, which no count can express — a
# future edit could re-add the route and simply bump `36` back to `37`, and every
# pin above would still pass. The route was an ingress-configuration oracle and,
# after segment matching landed, a containment oracle over all seven candidate
# headers; re-introducing it silently is the failure mode worth a dedicated test.
#
# Deliberately asserts 404, NOT 405: 405 would mean the path still exists with a
# different method allowlist, i.e. a partial removal.

_REMOVED_PROBE_PATH = "/api/runtime/identity/probe"


def test_removed_identity_probe_route_is_not_reachable(client):
    posted = client.post(_REMOVED_PROBE_PATH, json={})
    assert posted.status_code == 404, (
        f"POST {_REMOVED_PROBE_PATH} returned {posted.status_code}, not 404 — the "
        "temporary identity probe is back, or was only partly removed "
        "(405 would mean the path still exists)"
    )
    # No method survives either: a bare path with no handlers is 404 for all verbs.
    assert client.get(_REMOVED_PROBE_PATH).status_code == 404


def test_removed_identity_probe_is_absent_from_the_generated_contract(client):
    schema = client.get("/api/openapi").json()
    assert _REMOVED_PROBE_PATH not in schema["paths"]
    assert "IdentityProbeRequest" not in schema["components"]["schemas"]
    # Substring sweep over the whole serialized document, so a rename, a $ref, a
    # tag, or prose mentioning the probe is caught as well as the path key.
    document = json.dumps(schema)
    for needle in ("identity/probe", "IdentityProbeRequest", "ISAAC_IDENTITY_PROBE"):
        assert needle not in document, (
            f"{needle!r} is still published in the generated OpenAPI document"
        )


def test_the_removed_probe_route_table_is_clean(client):
    """Checked at the route table rather than the document, because a
    re-introduction carrying `include_in_schema=False` would be invisible to the
    generated schema — which is exactly how the probe was nearly shipped the
    first time. Uses `_walk_api_routes`: `include_router` nests the routes, so a
    flat pass over `app.routes` finds none of them and would pass vacuously."""
    paths = {route.path for route in _walk_api_routes(client.app)}
    assert paths, "the route walk found nothing — this check would pass vacuously"
    assert _REMOVED_PROBE_PATH not in paths
