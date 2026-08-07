"""Shared fixtures for ``apps/api/tests``.

Autouse seam-neutralizer (P24.9-impl-4)
----------------------------------------
``apps/api/isaac_api/data/memory-snapshot.json`` is now a real, committed
sanitized snapshot (P24.9-impl-4). Per ``isaac_api.memory._resolve_reader_choice``'s
documented precedence, its mere presence on disk makes
``memory.get_default_reader()`` select :class:`~isaac_api.memory.SanitizedSnapshotSource`
over it by default — ahead of ``ISAAC_MEMORY_DIR`` and the repo's
``graphify-out/`` fallback (precedence step 2, ahead of steps 3/4).

Most of ``apps/api/tests`` predates that file's existence and drives the
*live-graph* provider deliberately (via ``ISAAC_MEMORY_DIR`` pointed at a
synthetic fixture, or an absent ``graphify-out/``), asserting on
``provider_kind == "local-graph"`` and related shapes. Those tests are not
wrong — they intentionally exercise precedence steps 3/4 and must keep doing
so regardless of whether a packaged snapshot happens to exist in the
checkout. So every test gets the packaged-snapshot precedence step
neutralized by default: ``memory._PACKAGED_SNAPSHOT`` is pointed at a path
that is guaranteed not to exist (a name under ``tmp_path``, never created),
so ``_resolve_reader_choice()`` falls through to
``ISAAC_MEMORY_SNAPSHOT`` / ``ISAAC_MEMORY_DIR`` / ``graphify-out/`` exactly as
before that file existed. The memoized ``_default_reader``/``_default_choice``
are also reset so ``get_default_reader()`` re-resolves for every test instead
of reusing a reader instance memoized by an earlier test.

A test that specifically wants to exercise the packaged-snapshot step itself
(none currently do outside ``test_snapshot_source.py``'s own seam tests, which
already monkeypatch ``memory._PACKAGED_SNAPSHOT`` explicitly to whatever path
they need) can simply monkeypatch ``memory._PACKAGED_SNAPSHOT`` again to
override this fixture's value — monkeypatch calls stack, so the last one set
within a test wins.

This fixture does not touch the real snapshot file itself, nor any of the
truth/export/validation path; it only neutralizes a *default-selection* seam
in ``isaac_api.memory`` for the duration of each test.

Worked-example scope helpers
----------------------------

The five canonical example records used to be materialised into the NORMAL
workspace by ``ensure_seeded()``, which every read called. They now exist ONLY
inside an isolated worked-example session
(``<workspace>/_tutorial/<session_id>/``), and the normal workspace is never
auto-seeded.

Most of this package's tests used a canonical id purely as a convenient handle to
a working record. They are re-pointed at a worked-example session rather than
weakened: every assertion still asserts exactly what it asserted before, about the
same five records, with the same strength — only the SCOPE those records live in
has changed. The two helpers below are how:

* :func:`tutorial_client` — a ``TestClient`` that has opened a session and sends
  ``X-Isaac-Tutorial-Session`` on every request. Because scope is resolved from a
  HEADER and the ``/api/experiments/{id}`` URL shape is unchanged, a migrated test's
  requests are byte-identical apart from that header.
* :class:`ScopedWorkspace` — ``isaac_api.workspace`` with its scope-aware functions
  pre-bound to one session, for the tests that drive the store directly instead of
  over HTTP.
"""

from __future__ import annotations

import functools

import pytest
from fastapi.testclient import TestClient

from isaac_api import experiment_repository as _repo
from isaac_api import memory
from isaac_api import workspace as _ws
from isaac_api.routes import TUTORIAL_SESSION_HEADER


@pytest.fixture(autouse=True)
def _neutralize_packaged_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "_PACKAGED_SNAPSHOT", tmp_path / "nonexistent-packaged-snapshot.json")
    monkeypatch.setattr(memory, "_default_reader", None)
    monkeypatch.setattr(memory, "_default_choice", None)
    yield


@pytest.fixture(autouse=True)
def _clear_storage_observation():
    """No test may inherit another's durable-storage outage.

    ``experiment_repository`` records the last durable-storage failure in a MODULE
    GLOBAL, deliberately — it is how ``/api/health`` reports a database problem
    without opening a connection. A module global is also process state that
    survives a test, so a case that simulates an outage would otherwise leave
    ``storage_status`` reporting ``durable: false`` for every case that ran after
    it, and the resulting failure would name an innocent test.

    Cleared BEFORE and AFTER: before, so a test's starting state is stated rather
    than inherited; after, so a failing test cannot poison the rest of the run.
    """
    _repo.forget_storage_failure()
    yield
    _repo.forget_storage_failure()


def tutorial_client(app, **kwargs) -> TestClient:
    """A ``TestClient`` bound to a freshly opened worked-example session.

    Opens the session over the real HTTP surface (so the test exercises the same
    creation path a browser would), then pins the session header as a client
    default. ``client.tutorial_session_id`` carries the id for a test that also needs
    to reach the store directly, and ``client.tutorial_record_ids`` the ids the
    server reported materialising.

    The workspace env var must already be set (every fixture in this package points
    ``ISAAC_UI_WORKSPACE`` at a ``tmp_path``); the worked-example root is DERIVED from
    it, so no second variable exists or is needed.
    """
    client = TestClient(app, **kwargs)
    response = client.post("/api/tutorial/sessions")
    assert response.status_code == 201, response.text
    body = response.json()
    client.headers[TUTORIAL_SESSION_HEADER] = body["session_id"]
    client.tutorial_session_id = body["session_id"]
    client.tutorial_record_ids = body["record_ids"]
    return client


def bind_tutorial_session(client: TestClient) -> TestClient:
    """Open a worked-example session via the STORE (no HTTP) and pin it on ``client``.

    For a test that enables API-key authentication. :func:`tutorial_client` opens the
    session over HTTP, which that deployment would refuse with a 401; and pinning the
    key as a client default would destroy the very 401 such a test is asserting. So
    the session is created in-process and only its header is pinned. The scope the
    request lands in is identical either way.
    """
    session_id, record_ids = _ws.create_tutorial_session()
    client.headers[TUTORIAL_SESSION_HEADER] = session_id
    client.tutorial_session_id = session_id
    client.tutorial_record_ids = record_ids
    return client


class ScopedWorkspace:
    """``isaac_api.workspace`` with its scope-aware functions bound to one session.

    Attribute access falls through to the live module, so every constant
    (``SEED_READY_ID``, ``CANONICAL_IDS``, ``NEEDS_ATTENTION``, …) and every
    scope-free function behaves exactly as before, and a ``monkeypatch.setattr(ws,
    …)`` in a test is still observed here because lookup happens per call.

    The names in :data:`_SCOPED` are the functions that take a ``session_id``; they
    come back pre-bound to this session. ``workspace_root`` is remapped to this
    session's root, because for a direct-store test "the root my records are in" is
    what every existing use of it means.

    Deliberately NOT a way to weaken anything: it changes which directory a call
    reads, never what the call returns for that directory.
    """

    #: Functions taking a keyword ``session_id``.
    _SCOPED = frozenset(
        {
            "list_experiments",
            "load_experiment",
            "record_lock",
            "reset_to_canonical_seed",
            "create_experiment",
            "ensure_tutorial_seeded",
            "_load_all_experiments",
            "_materialise_seed",
            "_existing_generation",
            "_canonical_state_counts",
            "_remove_experiment_dir",
        }
    )

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    def __getattr__(self, name: str):
        attr = getattr(_ws, name)
        if name in self._SCOPED:
            return functools.partial(attr, session_id=self.session_id)
        if name == "workspace_root":
            return lambda: _ws.scope_root(self.session_id)
        if name == "_experiment_dirs":
            return lambda: _ws._experiment_dirs(_ws.scope_root(self.session_id))
        return attr


def open_tutorial_scope() -> ScopedWorkspace:
    """Open a worked-example session and return the store bound to it (no HTTP)."""
    session_id, _ = _ws.create_tutorial_session()
    return ScopedWorkspace(session_id)


def client_ws(client: TestClient) -> ScopedWorkspace:
    """The store bound to the session THIS client is using.

    Use this instead of :func:`tutorial_ws` in a test that has a client and would
    otherwise open a second session (which :func:`tutorial_ws` rejects, on purpose).
    """
    return ScopedWorkspace(client.tutorial_session_id)


def tutorial_ws() -> ScopedWorkspace:
    """The store bound to THE worked-example session in this test's workspace.

    Every fixture in this package points ``ISAAC_UI_WORKSPACE`` at its own
    ``tmp_path`` and opens exactly one session inside it, so "the session" is
    unambiguous. This is how a test that previously reached the store directly —
    ``ws.load_experiment(ws.SEED_READY_ID)`` — is re-pointed without threading a
    session id through every helper it happens to use: the assertion is unchanged,
    the directory it reads is not.

    The single-session assertion is load-bearing rather than convenience: it fails
    loudly if a test ever opens two sessions, instead of silently picking one and
    making the test's meaning depend on directory ordering.
    """
    namespace = _ws.tutorial_namespace_root()
    sessions = (
        sorted(p.name for p in namespace.iterdir() if p.is_dir())
        if namespace.is_dir()
        else []
    )
    assert len(sessions) == 1, (
        f"expected exactly one worked-example session in this workspace, found "
        f"{sessions!r} — a test with more than one must name the session it means"
    )
    return ScopedWorkspace(sessions[0])
