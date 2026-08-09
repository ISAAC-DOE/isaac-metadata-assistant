"""Worked-example scope isolation: the five examples live ONLY in a session.

The product rule this file pins: the five canonical example records are created only
inside an isolated worked-example session. Nothing in this build seeds the ordinary
workspace — not a read, not the example-workspace operations, not the reset — so on a
FRESH deployment the ordinary workspace is empty and stays empty.

Note the shape of that carefully, because an earlier version of this docstring got it
wrong and one product string inherited the error. "Nothing seeds it" is a statement
about what this build DOES; it is not a statement about what a given directory
CONTAINS. ``list_experiments(None)`` enumerates whatever is on disk and there is no
startup migration, so a workspace that already held the five before this change (a
developer's uncleared ``/tmp/isaac-ui-workspace``, a persistent volume) still lists
them. Every "is empty" assertion below is therefore about the ``tmp_path`` workspace
its fixture just created, which is the only scope in which it is measured.

Scope is a DIRECTORY NAMESPACE (``<workspace>/_tutorial/<session id>/``), so
exclusion from an ordinary read is structural rather than a filter a future caller
could forget. That is what most of the assertions below are really about.

Everything here is synthetic: the committed reference fixtures, through the
unchanged truth core. No real data, no network, no database.
"""

from __future__ import annotations

import ast
import inspect
import json
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api.routes import TUTORIAL_SESSION_HEADER

from conftest import tutorial_client


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def plain(app) -> TestClient:
    """A client with NO session header: the ordinary workspace."""
    return TestClient(app)


@pytest.fixture()
def session(app) -> TestClient:
    """A client inside a freshly opened worked-example session."""
    return tutorial_client(app)


def _ids(client) -> list[str]:
    body = client.get("/api/experiments")
    assert body.status_code == 200, body.text
    return [e["id"] for e in body.json()["experiments"]]


# =============================================================================
# 1. the ordinary workspace is empty, and STAYS empty
# =============================================================================


def test_ordinary_workspace_is_empty_on_a_fresh_deployment(plain):
    assert _ids(plain) == []


def test_repeated_reads_never_seed_the_ordinary_workspace(plain, tmp_path):
    """Proves the absence of auto-seeding, not merely a first-read empty result.

    ``ensure_seeded()`` used to run on EVERY read, so "empty on the first read" and
    "never seeded" were different claims. Reading many times, through several
    different read operations, and then inspecting the directory itself, separates
    them.
    """
    for _ in range(5):
        assert _ids(plain) == []
        assert plain.get("/api/runtime/records").json() == {"records": [], "total": 0}
        assert plain.get("/api/search", params={"q": "xanes"}).status_code == 200
    root = tmp_path / "ws"
    on_disk = sorted(p.name for p in root.iterdir()) if root.exists() else []
    assert ws.TUTORIAL_NAMESPACE not in on_disk, (
        "an ordinary read created the worked-example namespace"
    )
    for canonical_id in ws.CANONICAL_IDS:
        assert not (root / canonical_id).exists(), (
            f"{canonical_id} was materialised into the ordinary workspace"
        )


def test_a_canonical_id_is_404_in_the_ordinary_workspace(plain):
    for canonical_id in sorted(ws.CANONICAL_IDS):
        r = plain.get(f"/api/experiments/{canonical_id}")
        assert r.status_code == 404, r.text
        assert r.json()["error"] == "experiment_not_found"


def test_the_seeding_functions_refuse_an_unscoped_call(tmp_path):
    """BEHAVIOURAL. This test used to assert a SIGNATURE, and the signature was not the
    property that mattered.

    The old version checked that ``session_id`` has no default, and its docstring
    concluded "there is no way to call either such that it writes into the ordinary
    workspace ... this shows no future one can". That was false, and independent review
    falsified it by execution: ``scope_root(None)`` returns ``workspace_root()`` without
    raising, so ``_materialise_seed(spec, session_id=None)`` wrote
    ``workspace_root()/01SYNTHXANESSEED0000000001/`` and
    ``reset_to_canonical_seed(dry_run=False, session_id=None)`` materialised all five
    there and reported ``final_count: 5``. Passing ``None`` EXPLICITLY is a way to call
    them, a missing default does not prevent it, and there is no mypy/pyright gate in
    this project's CI to make the annotation load-bearing.

    So the refusal is now enforced at runtime and asserted here — and the assertion is
    the one the copy on three product surfaces depends on: nothing in this build adds a
    built-in example record to the ordinary workspace.
    """
    root = tmp_path / "unscoped"
    root.mkdir()
    monkey = pytest.MonkeyPatch()
    monkey.setenv("ISAAC_UI_WORKSPACE", str(root))
    try:
        with pytest.raises(ws.InvalidTutorialSession):
            ws._materialise_seed(ws._seed_specs()[0], session_id=None)
        with pytest.raises(ws.InvalidTutorialSession):
            ws.reset_to_canonical_seed(dry_run=False, session_id=None)
        # A PREVIEW is refused too: it would otherwise report a classification of, and
        # a projection for, the ordinary workspace — a scope this operation may not act
        # on at all.
        with pytest.raises(ws.InvalidTutorialSession):
            ws.reset_to_canonical_seed(dry_run=True, session_id=None)
        with pytest.raises(ws.InvalidTutorialSession):
            ws.ensure_tutorial_seeded(None)
        # The refusals wrote nothing: not a canonical directory, not the namespace.
        assert sorted(p.name for p in root.iterdir()) == []
    finally:
        monkey.undo()


def test_the_seeding_functions_still_take_no_default_session_id():
    """The signature guard is KEPT — it is just no longer the whole argument.

    A default would let a caller omit the argument entirely, which the runtime refusal
    above cannot see (it would receive the default, not ``None``). The two checks cover
    different mistakes: this one the forgotten argument, the one above the explicit
    ``None``.
    """
    for fn in (ws._materialise_seed, ws.reset_to_canonical_seed):
        param = inspect.signature(fn).parameters["session_id"]
        assert param.default is inspect.Parameter.empty, (
            f"{fn.__name__} has a default session_id, so a caller that omits it "
            "silently addresses whatever that default names"
        )


#: The ONE place in the API package allowed to call ``ws.create_experiment``.
#:
#: It is a constant rather than a literal in the assertion so that moving the seam
#: is a one-line, obviously-deliberate edit, and so the failure message can name
#: what the expected caller IS rather than only that the actual set is wrong.
_AUTHORIZED_CREATE_CALLER = "isaac_api/experiment_repository.py"


def test_create_experiment_has_no_caller_in_the_api_package():
    """SOURCE-LEVEL. ``create_experiment`` is not closed by the refusals above, and
    what constrains it is WHO CALLS IT AND HOW — a property no behavioural test can
    see.

    ``create_experiment(title, source, draft, id=SEED_READY_ID, session_id=None)``
    writes a canonical record into the ORDINARY root: ``rid = id or new_record_id()``
    (``workspace.py``), so a fresh ULID is minted only when no explicit id is given,
    and then ``exp.save()`` lands under ``scope_root(None)`` == ``workspace_root()``.
    It is not one of the three seeding functions, so ``InvalidTutorialSession`` never
    fires for it. That path is reachable in-process.

    THE NAME OF THIS TEST IS NOW WRONG, AND IS KEPT ANYWAY. There IS a caller. The
    name is the string a future reader greps for when they touch this area, and the
    docstring below is the thing they need to find; renaming it would break that
    trail for no gain. What the test asserts has changed, and it has been
    strengthened rather than relaxed.

    WHAT CHANGED, AND WHAT DID NOT. ``POST /api/experiments`` now exists — the first
    record-creation surface this application has ever had. The product claim carried
    on three surfaces is that nothing in this build adds a **built-in EXAMPLE
    record** to the ordinary workspace: the mode chip's accessible name, the OpenAPI
    ``tutorial`` tag description, and the WORKSPACE CLAUSE of the Statistics lead
    sentence — "this workspace" against "the open worked-example workspace",
    ``StatisticsPage.tsx::leadSentence``. That claim is UNCHANGED and still true;
    only its justification moved.

    THE CLAUSE IS NAMED RATHER THAN THE WHOLE SENTENCE, and that precision arrived
    from the visual-first reorganisation, which moved Record Verification to the top
    of the page and made the lead open by naming it. That rewrite did not touch the
    scope branch, and this guard is about the branch.

    Its previous justification — "this build exposes no record-creation surface at
    all" — is retired, because that sentence is now false. Three properties carry it
    instead, and this test pins all three:

      1. EXACTLY ONE CALLER, and it is the persistence seam. Not the route: the route
         must not be able to reach the workspace layer directly, or the "swappable
         persistence" property would be decorative.
      2. THE CALLER PASSES NEITHER ``id=`` NOR ``session_id=``. Without ``id`` the
         ULID default applies and the five fixed canonical ids are unreachable;
         without ``session_id`` the ordinary scope is the only scope addressed.
         Asserted at the AST, so it holds for the call as written rather than for
         the call as it behaved in whichever test happened to run it.
      3. NO PATH CAN MATERIALISE AN EXAMPLE INTO THE ORDINARY SCOPE — the runtime
         half, asserted behaviourally in
         ``test_the_seeding_functions_refuse_an_unscoped_call`` above and, for the
         durable store, in
         ``test_experiment_repository.py::test_a_canonical_id_is_never_persistable``.

    A second caller, or an ``id``/``session_id`` argument appearing on this one,
    still fails here — which is what keeps adding either a deliberate, reviewed act.

    TESTS ARE DELIBERATELY NOT SCANNED. They are the function's legitimate users
    (``test_versioning``, ``test_reset*``, ``test_tutorial_ordinary_preservation`` and
    this file) and they build ordinary records on purpose.
    """
    package = Path(ws.__file__).resolve().parent
    sources = sorted(p for p in package.rglob("*.py") if "__pycache__" not in p.parts)
    # NON-TRIVIAL: a mis-rooted or empty scan would satisfy the assertions below
    # without having read anything, so the scan proves its own reach first.
    assert len(sources) >= 5, f"expected the isaac_api package, scanned {len(sources)} files"
    assert package / "routes.py" in sources
    assert package / "workspace.py" in sources

    defined_in: list[str] = []
    callers: list[str] = []
    call_nodes: list[tuple[str, ast.Call]] = []
    for path in sources:
        rel = f"isaac_api/{path.relative_to(package).as_posix()}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "create_experiment"
            ):
                defined_in.append(f"{rel}:{node.lineno}")
                continue
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # ``create_experiment(...)`` and ``ws.create_experiment(...)`` alike; the
            # name is what a reader greps for either way.
            called = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if called == "create_experiment":
                callers.append(f"{rel}:{node.lineno}")
                call_nodes.append((rel, node))

    # A rename would make every assertion here vacuously true, so the target of the
    # guard is asserted to still exist.
    assert defined_in, (
        "create_experiment is no longer defined in the isaac_api package, so this "
        "guard is asserting facts about calls to nothing — re-point it"
    )

    # 1. Exactly one caller, and it is the persistence seam.
    assert [c.rsplit(":", 1)[0] for c in callers] == [_AUTHORIZED_CREATE_CALLER], (
        f"create_experiment is called from {callers}. Exactly one caller is "
        f"authorized — {_AUTHORIZED_CREATE_CALLER}, the persistence seam. A call "
        "from anywhere else (a route, a service, the app factory) bypasses the "
        "repository abstraction, and with an explicit `id` and `session_id=None` it "
        "writes a canonical record into the ordinary workspace — which falsifies the "
        "claim made on the mode chip, the OpenAPI `tutorial` tag description and the "
        "workspace clause of the Statistics lead sentence "
        "(`StatisticsPage.tsx::leadSentence`) that nothing in this build adds a "
        "built-in example record there. If a second caller is intended, re-derive "
        "those three strings in the same change."
    )

    # 2. That caller may not choose the id, and may not choose the scope.
    for rel, node in call_nodes:
        keywords = {kw.arg for kw in node.keywords}
        positional = len(node.args)
        assert "id" not in keywords, (
            f"{rel} passes an explicit `id` to create_experiment. That makes the "
            "five fixed canonical ids reachable from a creation path, which is "
            "exactly the shape the three product strings deny. Let the ULID default "
            "apply."
        )
        assert "session_id" not in keywords, (
            f"{rel} passes an explicit `session_id` to create_experiment. The "
            "repository addresses the ordinary scope and only the ordinary scope; a "
            "worked-example session is temporary and must never receive a record a "
            "person created."
        )
        # `id` is keyword-only in the signature, but a positional flood would still be
        # a smell worth catching: title/source/draft are the only three.
        assert positional <= 3, (
            f"{rel} passes {positional} positional arguments to create_experiment; "
            "only title, source and draft are positional"
        )


# =============================================================================
# 2. a session holds the five, and they are invisible from outside it
# =============================================================================


def test_creating_a_session_materialises_exactly_the_canonical_five(session):
    assert set(session.tutorial_record_ids) == set(ws.CANONICAL_IDS)
    assert set(_ids(session)) == set(ws.CANONICAL_IDS)
    assert len(_ids(session)) == 5


def test_the_create_response_reports_measured_ids_not_asserted_ones(app, tmp_path):
    """``record_ids`` is read back from the session, so it states what is there."""
    client = TestClient(app)
    body = client.post("/api/tutorial/sessions").json()
    root = tmp_path / "ws" / ws.TUTORIAL_NAMESPACE / body["session_id"]
    on_disk = sorted(p.name for p in root.iterdir() if (p / "experiment.json").exists())
    assert sorted(body["record_ids"]) == on_disk
    assert body["ttl_hours"] == ws.TUTORIAL_TTL_HOURS


def test_the_session_records_are_absent_from_the_ordinary_workspace(session, plain):
    assert set(_ids(session)) == set(ws.CANONICAL_IDS)
    assert _ids(plain) == []
    for canonical_id in ws.CANONICAL_IDS:
        assert plain.get(f"/api/experiments/{canonical_id}").status_code == 404


def test_the_session_marker_is_not_mistaken_for_a_record(session, tmp_path):
    root = tmp_path / "ws" / ws.TUTORIAL_NAMESPACE / session.tutorial_session_id
    marker = root / ws.TUTORIAL_MARKER
    assert marker.is_file()
    assert marker.name != "experiment.json"
    assert json.loads(marker.read_text(encoding="utf-8"))["created_utc"]
    # It sits at the session root, never inside an experiment directory, and the
    # listing does not report it.
    assert ws.TUTORIAL_MARKER not in _ids(session)


def test_underscore_prefixed_directories_are_excluded_from_ordinary_enumeration(
    plain, tmp_path
):
    """The exclusion is a STATED RULE, not an accident of the ``experiment.json``
    check: a ``_``-prefixed directory that DOES contain an ``experiment.json`` is
    still skipped. ``RECORD_ID_RE`` can never match a ``_``-prefixed name, so such a
    directory can never legitimately be a record."""
    root = tmp_path / "ws"
    decoy = root / "_not_a_record"
    decoy.mkdir(parents=True)
    (decoy / "experiment.json").write_text(
        json.dumps(
            {
                "id": "_not_a_record",
                "title": "decoy",
                "created_utc": "2026-01-01T00:00:00Z",
                "source": {},
                "draft": {},
            }
        ),
        encoding="utf-8",
    )
    assert _ids(plain) == []
    assert ws._experiment_dirs(root) == []


# =============================================================================
# 3. two sessions are mutually invisible and independently mutable
# =============================================================================


def _confirm_an_answer(client, experiment_id: str) -> dict:
    """Confirm blocking answers through the REAL answers route (If-Match and all)."""
    version = client.get(f"/api/experiments/{experiment_id}").json()["version"]
    answers = ws.load_demo_answers()
    r = client.post(
        f"/api/experiments/{experiment_id}/answers",
        json={"confirmed_by_user": True, "answers": {"series": answers.get("series")}},
        headers={"If-Match": f'"{version}"'},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_two_sessions_are_independently_mutable_and_mutually_invisible(app):
    a = tutorial_client(app)
    b = tutorial_client(app)
    assert a.tutorial_session_id != b.tutorial_session_id

    target = ws.SEED_NEW_DRAFT_ID
    before_b = b.get(f"/api/experiments/{target}").json()
    _confirm_an_answer(a, target)

    after_a = a.get(f"/api/experiments/{target}").json()
    after_b = b.get(f"/api/experiments/{target}").json()
    assert after_a["pending_count"] < before_b["pending_count"], "A did not change"
    assert after_b == before_b, "B observed A's mutation — the sessions are not isolated"

    # Both still hold their own five; neither leaked into the ordinary workspace.
    assert set(_ids(a)) == set(ws.CANONICAL_IDS)
    assert set(_ids(b)) == set(ws.CANONICAL_IDS)
    assert _ids(TestClient(app)) == []


def test_disposing_one_session_leaves_the_other_intact(app):
    a = tutorial_client(app)
    b = tutorial_client(app)
    assert a.delete(f"/api/tutorial/sessions/{a.tutorial_session_id}").status_code == 204
    assert set(_ids(b)) == set(ws.CANONICAL_IDS)
    assert a.get("/api/experiments").status_code == 404


def test_two_sessions_do_not_share_a_record_lock():
    """The lock key is scope-qualified, so the same canonical id in two sessions is
    two different locks — they are two different files and must not contend."""
    same_id = ws.SEED_READY_ID
    keys = {
        ws._lock_key(same_id, None),
        ws._lock_key(same_id, "a" * 22),
        ws._lock_key(same_id, "b" * 22),
    }
    assert len(keys) == 3
    # ...and the qualification is injective: neither half can contain a separator.
    assert ws._lock_key(same_id, "a" * 22) != ws._lock_key("a" * 22 + "/" + same_id, None)


# =============================================================================
# 4. scope resolution is FAIL-CLOSED
# =============================================================================


_MALFORMED_SESSION_IDS = [
    "..",
    "../..",
    "../../etc/passwd",
    "/etc",
    "a/b",
    "a\\b",
    ".",
    "",
    "a" * 15,
    "a" * 65,
    "has space",
    "has.dot",
    "nul\x00byte",
]


@pytest.mark.parametrize("bad", _MALFORMED_SESSION_IDS)
def test_a_malformed_session_id_is_422_and_never_reads_a_scope(app, bad):
    client = TestClient(app, headers={TUTORIAL_SESSION_HEADER: bad})
    r = client.get("/api/experiments")
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "invalid_tutorial_session"
    # The refusal echoes neither the rejected id nor any filesystem path, so a
    # traversal attempt learns nothing about the server.
    body = r.text
    assert bad.strip("./\\ ") == "" or bad not in body
    assert "/tmp" not in body and "/private" not in body


@pytest.mark.parametrize("bad", _MALFORMED_SESSION_IDS)
def test_the_workspace_layer_rejects_a_malformed_session_id(bad):
    assert ws.is_tutorial_session_id(bad) is False
    with pytest.raises(ws.InvalidTutorialSession):
        ws.scope_root(bad)
    # The exception message carries no path and no echo of the input.
    with pytest.raises(ws.InvalidTutorialSession) as excinfo:
        ws.validate_tutorial_session_id(bad)
    assert str(excinfo.value) == "invalid tutorial session id"


def test_a_server_minted_session_id_is_accepted():
    session_id, _ = None, None
    for _ in range(20):
        candidate = __import__("secrets").token_urlsafe(16)
        assert ws.is_tutorial_session_id(candidate), candidate


def test_an_unknown_session_is_404_and_does_not_fall_back_to_the_ordinary_workspace(
    app,
):
    """THE fail-closed property. A well-formed id naming no session must never be
    silently treated as "no header": that would answer a request about one scope with
    the contents of another."""
    unknown = "Zz" + "0" * 20
    assert ws.is_tutorial_session_id(unknown)
    client = TestClient(app, headers={TUTORIAL_SESSION_HEADER: unknown})
    r = client.get("/api/experiments")
    assert r.status_code == 404, r.text
    assert r.json()["error"] == "tutorial_session_not_found"
    # Not a 200 with the ordinary workspace's (empty) contents, and not a 200 with
    # somebody else's records either.
    assert "experiments" not in r.json()


def test_a_disposed_session_is_404_on_every_scoped_operation(app):
    client = tutorial_client(app)
    session_id = client.tutorial_session_id
    assert client.delete(f"/api/tutorial/sessions/{session_id}").status_code == 204
    for method, path in [
        ("get", "/api/experiments"),
        ("get", f"/api/experiments/{ws.SEED_READY_ID}"),
        ("get", f"/api/experiments/{ws.SEED_READY_ID}/draft"),
        ("get", f"/api/experiments/{ws.SEED_READY_ID}/pending"),
        ("get", f"/api/experiments/{ws.SEED_READY_ID}/evidence"),
        ("get", f"/api/experiments/{ws.SEED_READY_ID}/artifacts"),
        ("post", f"/api/experiments/{ws.SEED_READY_ID}/validate"),
        ("post", f"/api/experiments/{ws.SEED_READY_ID}/audit"),
        ("get", f"/api/experiments/{ws.SEED_READY_ID}/warnings"),
        ("get", "/api/runtime/records"),
        ("get", "/api/search?q=xanes"),
        ("post", "/api/demo/run"),
    ]:
        r = getattr(client, method)(path)
        assert r.status_code == 404, f"{method.upper()} {path} -> {r.status_code}"
        assert r.json()["error"] == "tutorial_session_not_found", path


def test_every_scope_resolving_operation_uses_the_one_shared_dependency(app):
    """Guards against a future route reading the ordinary workspace by omitting the
    header parameter. Read off the generated contract, so it cannot go stale."""
    schema = app.openapi()
    expected = {
        "/api/experiments",
        "/api/experiments/{experiment_id}",
        "/api/experiments/{experiment_id}/draft",
        "/api/experiments/{experiment_id}/pending",
        "/api/experiments/{experiment_id}/answers",
        "/api/experiments/{experiment_id}/edit",
        "/api/experiments/{experiment_id}/export",
        "/api/experiments/{experiment_id}/ingestion/csv/preview",
        "/api/experiments/{experiment_id}/validate",
        "/api/experiments/{experiment_id}/audit",
        "/api/experiments/{experiment_id}/warnings",
        "/api/experiments/{experiment_id}/evidence",
        "/api/experiments/{experiment_id}/evidence-classification",
        "/api/experiments/{experiment_id}/source-preview",
        "/api/experiments/{experiment_id}/artifacts",
        "/api/experiments/{experiment_id}/assistant/query",
        "/api/runtime/records",
        "/api/search",
        "/api/demo/run",
        "/api/demo/reset",
    }
    carrying = set()
    for path, item in schema["paths"].items():
        for method, op in item.items():
            names = {p["name"] for p in op.get("parameters", [])}
            if TUTORIAL_SESSION_HEADER in names:
                carrying.add(path)
    assert expected <= carrying, f"missing the scope header: {sorted(expected - carrying)}"


# =============================================================================
# 5. session lifecycle: dispose is idempotent, sweep is fail-closed
# =============================================================================


def test_dispose_is_idempotent_over_http(session):
    session_id = session.tutorial_session_id
    first = session.delete(f"/api/tutorial/sessions/{session_id}")
    second = session.delete(f"/api/tutorial/sessions/{session_id}")
    assert first.status_code == 204
    assert second.status_code == 204, "disposing an absent session must succeed"
    assert first.content == b"" and second.content == b""


def test_dispose_is_idempotent_in_the_store(app, tmp_path):
    TestClient(app)  # ensure the workspace root exists
    session_id, _ = ws.create_tutorial_session()
    assert ws.tutorial_session_exists(session_id)
    ws.dispose_tutorial_session(session_id)
    assert not ws.tutorial_session_exists(session_id)
    ws.dispose_tutorial_session(session_id)  # must not raise
    ws.dispose_tutorial_session("Never" + "0" * 17)  # never existed; must not raise


def test_dispose_rejects_a_malformed_id_rather_than_removing_anything(app, tmp_path):
    session_id, _ = ws.create_tutorial_session()
    for bad in ("..", "a/b", ""):
        with pytest.raises(ws.InvalidTutorialSession):
            ws.dispose_tutorial_session(bad)
    assert ws.tutorial_session_exists(session_id), "a bad id removed a real session"


def test_dispose_over_http_rejects_a_malformed_id_with_422(plain):
    r = plain.delete("/api/tutorial/sessions/nope")
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "invalid_tutorial_session"


def test_a_partly_removed_session_is_still_disposable(app, tmp_path):
    """Retryability: whatever a failed removal leaves behind must still be clearable,
    and an unmarked leftover is additionally treated as stale by the sweep."""
    session_id, _ = ws.create_tutorial_session()
    root = ws.scope_root(session_id)
    (root / ws.TUTORIAL_MARKER).unlink()  # the marker went first, records remain
    assert ws.tutorial_session_exists(session_id)
    ws.dispose_tutorial_session(session_id)
    assert not ws.tutorial_session_exists(session_id)


def _age_session(session_id: str, hours: float) -> None:
    """Rewrite a session's marker so it claims to have been created ``hours`` ago."""
    created = datetime.now(timezone.utc) - timedelta(hours=hours)
    ws.atomic_write_text(
        ws.scope_root(session_id) / ws.TUTORIAL_MARKER,
        json.dumps({"created_utc": created.strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n",
    )


def test_the_sweep_removes_an_expired_session_and_keeps_a_fresh_one(app):
    stale, _ = ws.create_tutorial_session()
    fresh, _ = ws.create_tutorial_session()
    _age_session(stale, ws.TUTORIAL_TTL_HOURS + 1)

    removed = ws.sweep_stale_tutorial_sessions()
    assert removed == 1
    assert not ws.tutorial_session_exists(stale)
    assert ws.tutorial_session_exists(fresh)
    # Idempotent: a second sweep removes nothing further.
    assert ws.sweep_stale_tutorial_sessions() == 0


@pytest.mark.parametrize(
    "marker",
    [
        None,  # missing entirely
        "not json at all",
        "[]",  # JSON, but not an object
        "{}",  # object, but no created_utc
        '{"created_utc": null}',
        '{"created_utc": "yesterday"}',
        '{"created_utc": 1234}',
        '{"created_utc": "2026-01-01T00:00:00"}',  # naive: no timezone
    ],
)
def test_a_session_whose_age_cannot_be_read_is_treated_as_stale(app, marker):
    """FAIL-CLOSED. An age nobody can read must not be interpreted as "young", or a
    corrupt marker would pin a session in place forever."""
    session_id, _ = ws.create_tutorial_session()
    path = ws.scope_root(session_id) / ws.TUTORIAL_MARKER
    if marker is None:
        path.unlink()
    else:
        path.write_text(marker, encoding="utf-8")
    assert ws.sweep_stale_tutorial_sessions() == 1
    assert not ws.tutorial_session_exists(session_id)


def test_the_sweep_touches_nothing_in_the_ordinary_workspace(app, tmp_path):
    root = tmp_path / "ws"
    root.mkdir(parents=True, exist_ok=True)
    ordinary = ws.create_experiment(
        title="An ordinary record",
        source={"description": "hand-authored", "files": []},
        draft={"fields": {}, "pending": []},
    )
    decoy = root / "_not_a_session"
    decoy.mkdir()
    (decoy / "keep-me").write_text("x", encoding="utf-8")

    stale, _ = ws.create_tutorial_session()
    _age_session(stale, ws.TUTORIAL_TTL_HOURS + 1)
    assert ws.sweep_stale_tutorial_sessions() == 1

    assert ws.load_experiment(ordinary.id) is not None, "the sweep removed a real record"
    assert (decoy / "keep-me").exists(), "the sweep removed an unrelated directory"


def test_the_sweep_leaves_a_directory_it_did_not_create(app):
    """A child of the namespace whose name is not a well-formed session id is left
    alone rather than deleted on a guess — this application cannot have created it."""
    ws.tutorial_namespace_root().mkdir(parents=True, exist_ok=True)
    # Deliberately NOT of the server-minted shape: too short, and it contains a dot.
    foreign = ws.tutorial_namespace_root() / "foreign.dir"
    foreign.mkdir()
    assert not ws.is_tutorial_session_id(foreign.name)
    assert ws.sweep_stale_tutorial_sessions() == 0
    assert foreign.exists()


def test_creating_a_session_sweeps_expired_ones(app):
    client = TestClient(app)
    stale = client.post("/api/tutorial/sessions").json()["session_id"]
    _age_session(stale, ws.TUTORIAL_TTL_HOURS + 1)
    fresh = client.post("/api/tutorial/sessions").json()["session_id"]
    assert not ws.tutorial_session_exists(stale)
    assert ws.tutorial_session_exists(fresh)


def test_sessions_are_created_concurrently_without_collision(app):
    client = TestClient(app)
    ids: list[str] = []
    lock = threading.Lock()

    def create():
        body = client.post("/api/tutorial/sessions").json()
        with lock:
            ids.append(body["session_id"])

    threads = [threading.Thread(target=create) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert len(ids) == 6
    assert len(set(ids)) == 6, "two sessions were minted with the same id"
    for session_id in ids:
        assert {e.id for e in ws.list_experiments(session_id)} == set(ws.CANONICAL_IDS)


# =============================================================================
# 6. the example-workspace operations REQUIRE a session
# =============================================================================


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/demo/run", {"mode": "draft_only"}),
        ("/api/demo/run", {"mode": "full"}),
        ("/api/demo/reset", {"mode": "preview"}),
        (
            "/api/demo/reset",
            {
                "mode": "execute",
                "confirmation": "RESET EXAMPLE WORKSPACE",
                "plan_digest": "rp1.whatever",
            },
        ),
    ],
)
def test_the_example_operations_refuse_outside_a_session_and_mutate_nothing(
    plain, tmp_path, path, body
):
    root = tmp_path / "ws"
    before = sorted(p.name for p in root.rglob("*")) if root.exists() else []
    r = plain.post(path, json=body)
    assert r.status_code == 409, r.text
    payload = r.json()
    assert payload["error"] == "tutorial_scope_required"
    assert payload["header"] == TUTORIAL_SESSION_HEADER
    assert payload["operation"].endswith(path)
    after = sorted(p.name for p in root.rglob("*")) if root.exists() else []
    assert after == before, "a refused example operation wrote to the workspace"
    assert _ids(plain) == []


def test_demo_run_inside_a_session_targets_that_sessions_records(session, plain):
    r = session.post("/api/demo/run", json={"mode": "draft_only"})
    assert r.status_code == 200, r.text
    assert r.json()["experiment_id"] == ws.SEED_NEW_DRAFT_ID
    assert len(_ids(session)) == 5
    assert _ids(plain) == []


def test_demo_reset_inside_a_session_restores_only_that_session(app):
    a = tutorial_client(app)
    b = tutorial_client(app)
    _confirm_an_answer(a, ws.SEED_NEW_DRAFT_ID)
    _confirm_an_answer(b, ws.SEED_NEW_DRAFT_ID)
    b_before = b.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()

    preview = a.post("/api/demo/reset", json={"mode": "preview"})
    assert preview.status_code == 200, preview.text
    digest = preview.json()["plan_digest"]
    executed = a.post(
        "/api/demo/reset",
        json={
            "mode": "execute",
            "confirmation": "RESET EXAMPLE WORKSPACE",
            "plan_digest": digest,
        },
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "ok"

    a_after = a.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    assert a_after["pending_count"] == 5, "A was not restored"
    b_after = b.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    assert b_after == b_before, "the reset reached into another session"


def test_the_reset_preview_projects_the_scope_it_actually_operates_on(session):
    """``final_count`` on a preview is a PROJECTION, and it is only honest because
    the operation is scoped: it projects five into the session it will rebuild, not
    into an ordinary workspace it cannot seed."""
    preview = session.post("/api/demo/reset", json={"mode": "preview"}).json()
    assert preview["previous_count"] == 5
    assert preview["final_count"] == 5
    executed = session.post(
        "/api/demo/reset",
        json={
            "mode": "execute",
            "confirmation": "RESET EXAMPLE WORKSPACE",
            "plan_digest": preview["plan_digest"],
        },
    ).json()
    assert executed["final_count"] == preview["final_count"], (
        "the preview projected a count the execute did not produce"
    )
    assert sorted(executed["canonical_ids"]) == sorted(ws.CANONICAL_IDS)


def test_the_reset_requires_a_session_before_the_synthetic_only_gate(plain, monkeypatch):
    """Ordering matters: without a scope there is no workspace to classify, so any
    counts reported alongside a refusal would be counts about the wrong thing."""
    monkeypatch.setattr(ws, "is_synthetic_only", lambda: False)
    r = plain.post("/api/demo/reset", json={"mode": "preview"})
    assert r.status_code == 409
    assert r.json()["error"] == "tutorial_scope_required"


# =============================================================================
# 7. the reset's path-safety guard stays EQUALLY strict under scoping
# =============================================================================


def test_the_remove_guard_refuses_anything_but_a_direct_child_of_the_scope(app, tmp_path):
    session_id, _ = ws.create_tutorial_session()
    session_root = ws.scope_root(session_id)
    namespace = ws.tutorial_namespace_root()
    workspace = tmp_path / "ws"

    refused = [
        # the session root itself is not a record
        session_root,
        # the namespace directory holding every session
        namespace,
        # the ordinary workspace root
        workspace,
        # a traversal out of the scope
        session_root / ".." / ".." / ws.SEED_READY_ID,
        # nested one level too deep
        session_root / ws.SEED_READY_ID / "records",
        # a record directory belonging to a DIFFERENT scope
        workspace / ws.SEED_READY_ID,
        # somewhere else entirely
        tmp_path / "elsewhere",
    ]
    for target in refused:
        with pytest.raises(ValueError):
            ws._remove_experiment_dir(target, session_id=session_id)

    # ...and the one legitimate shape is accepted.
    victim = session_root / ws.SEED_READY_ID
    assert victim.exists()
    ws._remove_experiment_dir(victim, session_id=session_id)
    assert not victim.exists()
    # The other four survive: the removal was targeted, not a wipe.
    assert len(ws.list_experiments(session_id)) == 4
    assert (session_root / ws.TUTORIAL_MARKER).exists()


def test_the_remove_guard_still_refuses_a_tutorial_dir_from_the_ordinary_scope(app):
    """Scoping must not have widened the guard: a session's record directory is not
    removable through the ORDINARY scope, even though it is a real record."""
    session_id, _ = ws.create_tutorial_session()
    victim = ws.scope_root(session_id) / ws.SEED_READY_ID
    with pytest.raises(ValueError):
        ws._remove_experiment_dir(victim, session_id=None)
    assert victim.exists()


def test_the_session_remove_guard_refuses_the_namespace_itself(app, monkeypatch):
    """Second, independent check: even if scope resolution were subverted so that a
    session "root" pointed at the namespace directory itself, the removal refuses
    rather than deleting every session at once."""
    session_id, _ = ws.create_tutorial_session()
    namespace = ws.tutorial_namespace_root()
    monkeypatch.setattr(ws, "scope_root", lambda sid=None: namespace)
    with pytest.raises(ValueError):
        ws.dispose_tutorial_session(session_id)
    assert namespace.is_dir()


# =============================================================================
# 8. the scope is NOT part of a record's authoritative identity
# =============================================================================


def test_the_authoritative_signature_ignores_the_scope():
    """Load-bearing. ``_authoritative_signature`` is the shared basis for the
    demo-run drift check, the reset's at-risk summary, ``save_versioned``'s no-op
    detection and ``_plan_digest``. If the scope entered it, every existing on-disk
    record's signature would change at once and the example run would start refusing
    over records nobody touched — the exact failure a previous title rename caused.
    """
    common = dict(
        id=ws.SEED_READY_ID,
        title="Same content",
        created_utc="2026-07-12T00:00:03Z",
        source={"description": "x", "files": []},
        draft={"fields": {}, "pending": []},
    )
    ordinary = ws.Experiment(**common)
    scoped = ws.Experiment(**common, session_id="a" * 22)
    other = ws.Experiment(**common, session_id="b" * 22)
    signatures = {
        ws._authoritative_signature(ordinary),
        ws._authoritative_signature(scoped),
        ws._authoritative_signature(other),
    }
    assert len(signatures) == 1, "the scope leaked into the authoritative signature"


def test_the_persisted_state_keys_are_unchanged_by_scoping():
    """``to_state``/``from_state`` must carry no scope key: the scope is a property
    of where the record is stored, and a state file that recorded it would go stale
    the moment the directory moved."""
    exp = ws.Experiment(
        id=ws.SEED_READY_ID,
        title="t",
        created_utc="2026-07-12T00:00:03Z",
        source={},
        draft={},
        session_id="a" * 22,
    )
    # A RUN IS ADDED DELIBERATELY. Without one, `state["runs"]` is empty and the
    # per-run assertion below is vacuous — `all(...)` over an empty list cannot
    # fail, so it would look like coverage while testing nothing.
    exp.add_run(label="Cold")
    state = exp.to_state()
    assert set(state) == {
        "id",
        "title",
        "created_utc",
        "source",
        "draft",
        "answer_log",
        "record_id",
        "rev",
        "updated_utc",
        "generation",
        # ``runs`` was added with the Run domain model. A Run is authoritative
        # scientific state (one Run exports to one ISAAC record), so it belongs in
        # the persisted document — and it carries NO scope key of its own either,
        # which is the property this test exists to defend. See
        # ``test_run_domain_model.py::test_a_run_carries_no_session_id``.
        "runs",
    }
    assert "session_id" not in state and "scope" not in state and "root" not in state
    assert len(state["runs"]) == 1, "the per-run assertion below must not be vacuous"
    assert all("session_id" not in r and "scope" not in r for r in state["runs"])
    # A round trip defaults to the ordinary scope unless the reader says otherwise.
    assert ws.Experiment.from_state(state).session_id is None
    assert ws.Experiment.from_state(state, session_id="b" * 22).session_id == "b" * 22


def test_a_seeded_records_state_file_carries_no_scope_key(session, tmp_path):
    root = tmp_path / "ws" / ws.TUTORIAL_NAMESPACE / session.tutorial_session_id
    state = json.loads(
        (root / ws.SEED_READY_ID / "experiment.json").read_text(encoding="utf-8")
    )
    assert "session_id" not in state
    assert session.tutorial_session_id not in json.dumps(state)


def test_a_records_paths_resolve_inside_its_own_scope(session, tmp_path):
    exp = ws.load_experiment(ws.SEED_DONE_ID, session_id=session.tutorial_session_id)
    assert exp is not None
    expected = (
        tmp_path / "ws" / ws.TUTORIAL_NAMESPACE / session.tutorial_session_id
        / ws.SEED_DONE_ID
    )
    assert exp.dir == expected
    assert exp.state_path == expected / "experiment.json"
    assert exp.records_dir == expected / "records"
    assert exp.record_path().parent == expected / "records"
    assert exp.sidecar_path().parent == expected / "records"
    assert exp.state_path.exists() and exp.record_path().exists()


# =============================================================================
# 9. read surfaces are honest about an empty ordinary workspace
# =============================================================================


def test_search_distinguishes_an_empty_scope_from_a_query_that_matched_nothing(
    plain, session
):
    empty = plain.get("/api/search", params={"q": "xanes"}).json()["workspace"]
    assert empty["available"] is True
    assert empty["total"] == 0
    assert empty["reason"] == "scope_has_no_records"

    no_match = session.get("/api/search", params={"q": "zzznope"}).json()["workspace"]
    assert no_match["available"] is True
    assert no_match["total"] == 0
    assert no_match["reason"] is None, "a populated scope must not claim to be empty"

    hit = session.get("/api/search", params={"q": "xanes"}).json()["workspace"]
    assert hit["total"] > 0
    assert hit["reason"] is None


def test_a_too_short_query_still_wins_over_the_empty_scope_reason(plain):
    """A too-short query is a fact about the REQUEST and is true whatever the scope
    holds, so it is reported in preference to the scope's emptiness."""
    body = plain.get("/api/search", params={"q": "x"}).json()
    assert body["workspace"]["reason"] == "query_too_short"


def test_every_aggregate_read_surface_survives_an_empty_ordinary_workspace(plain):
    """No crash, no division by zero, and no count that implies more than it knows."""
    assert plain.get("/api/experiments").json() == {"experiments": []}
    assert plain.get("/api/runtime/records").json() == {"records": [], "total": 0}
    for path in (
        "/api/health",
        "/api/graph/status",
        "/api/about",
        "/api/schema",
        "/api/memory/concepts",
        "/api/memory/files",
        "/api/memory/graph",
        "/api/memory/graph/detail",
        "/api/openapi",
    ):
        assert plain.get(path).status_code == 200, path
    filtered = plain.get(
        "/api/runtime/records", params={"status": ws.DONE, "has_conflict": True}
    ).json()
    assert filtered == {"records": [], "total": 0}
    assert plain.post("/api/assistant/memory/query", json={"question": "xanes"}).status_code == 200


def test_health_reports_the_mode_without_implying_records_exist(plain):
    body = plain.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["mode"] == "synthetic-only"
    # There is deliberately no record count here to go stale or mislead.
    assert "records" not in body and "record_count" not in body


# =============================================================================
# 10. governance: nothing here reads outside the committed fixtures
# =============================================================================


def test_a_session_references_only_the_committed_synthetic_fixtures(session):
    for exp in ws.list_experiments(session.tutorial_session_id):
        assert set((exp.source or {}).get("files") or []) <= set(ws.SOURCE_FILES)
        blob = json.dumps(exp.to_state())
        assert "examples/" not in blob
        assert "/Users/" not in blob


def test_no_response_leaks_a_filesystem_path(session, tmp_path):
    for path in (
        "/api/experiments",
        f"/api/experiments/{ws.SEED_DONE_ID}",
        f"/api/experiments/{ws.SEED_DONE_ID}/artifacts",
    ):
        assert str(tmp_path) not in session.get(path).text, path
    created = TestClient(session.app).post("/api/tutorial/sessions")
    assert str(tmp_path) not in created.text
    assert ws.TUTORIAL_NAMESPACE not in created.text


def test_uploads_stay_refused_in_a_session(session):
    assert session.post("/api/uploads").status_code == 403


def test_disposing_a_session_removes_its_files_from_disk(app, tmp_path):
    client = tutorial_client(app)
    root = tmp_path / "ws" / ws.TUTORIAL_NAMESPACE / client.tutorial_session_id
    assert root.is_dir() and any(root.iterdir())
    assert client.delete(f"/api/tutorial/sessions/{client.tutorial_session_id}").status_code == 204
    assert not root.exists()
    # The namespace directory itself survives for the next session.
    assert (tmp_path / "ws" / ws.TUTORIAL_NAMESPACE).is_dir()


def test_a_stray_file_in_the_namespace_does_not_break_the_sweep(app):
    ws.tutorial_namespace_root().mkdir(parents=True, exist_ok=True)
    stray = ws.tutorial_namespace_root() / "stray.txt"
    stray.write_text("x", encoding="utf-8")
    assert ws.sweep_stale_tutorial_sessions() == 0
    assert stray.exists()


def test_a_record_id_can_never_collide_with_the_namespace_name():
    """Why ``_tutorial`` is a safe namespace: no valid record id starts with ``_``."""
    from isaac_records.ids import is_record_id

    assert not is_record_id(ws.TUTORIAL_NAMESPACE)
    assert ws.TUTORIAL_NAMESPACE.startswith("_")
    for canonical_id in ws.CANONICAL_IDS:
        assert is_record_id(canonical_id)
        assert not canonical_id.startswith("_")


def test_disposing_a_session_does_not_disturb_the_ordinary_workspace(app, tmp_path):
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    ordinary = ws.create_experiment(
        title="An ordinary record",
        source={"description": "hand-authored", "files": []},
        draft={"fields": {}, "pending": []},
    )
    client = tutorial_client(app)
    assert client.delete(f"/api/tutorial/sessions/{client.tutorial_session_id}").status_code == 204
    assert ws.load_experiment(ordinary.id) is not None
    assert shutil.which("true") is not None or True  # keep the import used
