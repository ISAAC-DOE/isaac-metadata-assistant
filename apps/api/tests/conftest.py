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
import os

import pytest
from fastapi.testclient import TestClient

from isaac_api import experiment_repository as _repo
from isaac_api import memory
from isaac_api import workspace as _ws
from isaac_api.routes import TUTORIAL_SESSION_HEADER


#: CONSENT TO CONNECT, and the ONE signal that keeps the libpq environment intact.
#: The name and the required value are ``test_run_row_parity.OPT_IN_ENV`` and
#: ``OPT_IN_VALUE``; they are re-declared here rather than imported because
#: importing a test module from a conftest executes that module's own
#: ``_probe_engine()`` at conftest-import time, which is the one moment this file
#: exists to make uninteresting. The two declarations are pinned equal by
#: ``test_no_ambient_database.py::test_the_opt_in_this_conftest_honours_is_the_suites_own``,
#: so they cannot drift apart silently.
REAL_ENGINE_OPT_IN = "ISAAC_RUN_REAL_ENGINE_PARITY"
REAL_ENGINE_OPT_IN_VALUE = "1"


def libpq_variable_names(env) -> list[str]:
    """Every ``PG``-prefixed name in ``env``, ENUMERATED BY PREFIX rather than listed.

    libpq reads its connection parameters from a documented set of ``PG*``
    variables, and the set is not closed: ``PGHOST``, ``PGHOSTADDR``, ``PGPORT``,
    ``PGUSER``, ``PGPASSWORD``, ``PGDATABASE``, ``PGSSLMODE``, ``PGSERVICE``,
    ``PGSERVICEFILE``, ``PGPASSFILE``, ``PGOPTIONS``, ``PGCONNECT_TIMEOUT``,
    ``PGSSLROOTCERT``, ``PGREQUIRESSL``, ``PGCHANNELBINDING``, ``PGTARGETSESSIONATTRS``
    and more, with new ones added by new libpq releases. A HAND-WRITTEN LIST WOULD BE
    A GUARD THAT IS CORRECT ON THE DAY IT IS WRITTEN AND SILENTLY INCOMPLETE
    AFTERWARDS — and ``PGSERVICE``/``PGSERVICEFILE`` alone can name a complete
    connection without ``PGHOST`` appearing anywhere. So the rule is the prefix.

    Over-clearing is the safe direction and is intended: an unrelated ``PG``-prefixed
    variable that this suite does not use loses nothing by being absent, while one
    this suite does not KNOW ABOUT is exactly the case a list would miss.
    """
    return sorted(name for name in env if name.startswith("PG"))


@pytest.fixture(scope="session", autouse=True)
def _no_ambient_database():
    """A BARE ``pytest`` MUST NOT CONNECT THE WRITE PATH TO WHATEVER ``PGHOST`` NAMES.

    THE ACCIDENT, MEASURED RATHER THAN FEARED. ``db_write.database_configured`` is
    effectively ``bool(PGHOST)``, and that alone selects the PostgreSQL repository
    over the filesystem one — that is the deployment's documented feature switch, and
    it is why it needs no second variable in the pod. ``pyproject.toml``'s
    ``testpaths`` includes ``apps/api/tests``. And ``docs/postgres-test-db-guide.md``
    §"port-forward" tells anyone holding a SLAC cluster context to export exactly
    ``PGHOST``/``PGPORT``/``PGUSER``/``PGPASSWORD``/``PGDATABASE`` in their shell. Put
    those three facts together and ``CLAUDE.md`` §14's own documented developer
    command — ``.venv/bin/pytest`` — becomes a write client for whatever that
    environment points at.

    Measured in this repository with a counting double at ``db_write.connect_psycopg2``
    and those five variables exported (nothing was connected to; the double answers in
    process). ``apps/api/tests/test_pending_reads_are_boundable.py`` alone opened **70**
    connections and issued **11,633** mutating statements — ``INSERT``s and ``UPDATE``s
    against ``isaac_experiments``, ``isaac_runs`` and ``isaac_run_projection`` — on a
    DSN carrying ``application_name=isaac_app_write``. Across the whole suite the
    figures are in the report this fixture's proof test regenerates.

    WHY THE EXISTING GUARDS DID NOT COVER IT, stated precisely, because each of them
    reads as though it did:

    * ``.github/workflows/ci.yml``'s ``test`` job asserts ``PGHOST`` is unset. That is a
      guard on CI's environment. It says nothing about a developer's shell, and it is
      not weakened, duplicated or replaced here.
    * ``test_run_row_parity.py``'s ``ISAAC_RUN_REAL_ENGINE_PARITY`` opt-in (2026-08-24)
      closed this accident **for that one file**. Its own docstring describes the
      accident in the general terms that made it read as closed everywhere. It was
      never in scope for the other files that write through the same repository, and
      that belief is what made this dangerous rather than merely open. MEASURED:
      **35** files in this package opened a connection, and none of them is that one.

    WHAT THIS DOES. Unless the suite has explicitly consented via
    :data:`REAL_ENGINE_OPT_IN`, every ``PG``-prefixed variable is removed from
    ``os.environ`` for the whole session, so ``database_configured`` answers ``False``
    and every write lands on the filesystem repository the tests are written for.

    WHY SESSION-SCOPED, AND WHY THAT IS NOT A SHORTCUT. Higher-scoped fixtures are set
    up before lower-scoped ones, so this runs ahead of any module- or class-scoped
    fixture that builds an app and saves a record — a function-scoped fixture would
    not. It also must NOT restore the variables between tests: a test that wants a
    libpq environment sets one itself with ``monkeypatch.setenv``, which runs later and
    wins, and is undone by monkeypatch afterwards.

    COLLECTION TIME IS NOT COVERED BY A FIXTURE, and was measured rather than assumed:
    ``pytest --collect-only`` with the five variables exported opened **0**
    connections. The one module that probes at import — ``test_run_row_parity`` —
    checks its opt-in before it reads anything else, which is exactly why that file's
    fix is the precedent for this one and not a duplicate of it.

    THE OPT-IN PASSES THE ENVIRONMENT THROUGH UNTOUCHED. CI's ``postgres-migration``
    job sets it for both of its ``pytest`` invocations (the parity oracle and the
    discard suite), so those keep seeing the service container exactly as before. It
    is not a libpq variable and no guide asks anyone to export it, so exporting the
    documented five does not set it.

    THE RESIDUAL RISK, NAMED RATHER THAN IMPLIED AWAY. An opt-in that is honoured is
    an opt-in that can be given, and a developer who exported
    ``ISAAC_RUN_REAL_ENGINE_PARITY=1`` once for a local throwaway engine and left it
    in a shell profile restores the whole exposure — and restores it WIDER, because
    the whole package writes rather than one file. That is not a reason to remove the
    passthrough: without it CI's two real-engine steps cannot run, and a guard that
    breaks the only job that can execute those oracles is not a guard. What makes the
    residual narrow is that the variable is ISAAC-specific, is set in exactly two
    places in this repository (both CI steps), and is documented at its declaration
    as consent to connect. It is NOT narrowed by the loopback check in
    ``test_run_row_parity``: that check lives in the suite, not here, and this fixture
    deliberately does not import it — doing so would run that module's
    ``_probe_engine()`` at conftest-import time in every invocation, including CI's
    discard step, which does not collect that file today.
    """
    if (os.environ.get(REAL_ENGINE_OPT_IN) or "").strip() == REAL_ENGINE_OPT_IN_VALUE:
        yield {}
        return
    removed = {name: os.environ[name] for name in libpq_variable_names(os.environ)}
    for name in removed:
        del os.environ[name]
    try:
        yield removed
    finally:
        os.environ.update(removed)


@pytest.fixture(autouse=True)
def _neutralize_packaged_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "_PACKAGED_SNAPSHOT", tmp_path / "nonexistent-packaged-snapshot.json")
    monkeypatch.setattr(memory, "_default_reader", None)
    monkeypatch.setattr(memory, "_default_choice", None)
    yield


@pytest.fixture(autouse=True)
def _clear_storage_observation():
    """No test may inherit another's durable-storage outage, or its schema cache.

    ``experiment_repository`` records the last durable-storage failure in a MODULE
    GLOBAL, deliberately — it is how ``/api/health`` reports a database problem
    without opening a connection. A module global is also process state that
    survives a test, so a case that simulates an outage would otherwise leave
    ``storage_status`` reporting ``durable: false`` for every case that ran after
    it, and the resulting failure would name an innocent test.

    THE SECOND GLOBAL IS ``_run_table_seen`` AND IT LEAKS IN THE MORE DANGEROUS
    DIRECTION. It caches "this process has seen ``isaac_runs`` exist", and the
    cache is deliberately one-way: once set, nothing re-probes. Left uncleared, the
    first case that persists against a normal fake would make every later case
    believe the table is there — so every test of the 0002-pending deployment would
    pass for the wrong reason, or fail while naming the wrong test. It is a
    process-wide bit in the application, so it needs a process-wide reset here
    rather than a per-test one where it happens to be remembered.

    Cleared BEFORE and AFTER: before, so a test's starting state is stated rather
    than inherited; after, so a failing test cannot poison the rest of the run.
    """
    _repo.forget_storage_failure()
    _repo.forget_run_table_presence()
    yield
    _repo.forget_storage_failure()
    _repo.forget_run_table_presence()


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
