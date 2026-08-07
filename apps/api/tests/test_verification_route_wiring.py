"""The wiring that makes the authorized private mode REACHABLE, and nothing more.

`test_verification_datastore_mode.py` proves the datastore mode's behaviour given
a provider. `test_db_provider.py` proves the provider's own gates. Neither proves
that the deployed application actually hands one over -- and for most of this
project's life it did not: `VerificationState` was constructed with no
`provider_factory`, so the private mode could not obtain records at all.

That was the correct default while the capability was unauthorized. Q19 approved
it on 2026-08-05, so the wire now exists, and this file is the guard on the wire
itself. Every test here fails if the factory is removed, if the route stops
accepting a mode, or if an unknown mode is quietly served the public corpus.

WHAT THIS FILE DELIBERATELY DOES NOT DO: open a database connection. The private
mode is exercised only in states that fail before a socket exists, and the tests
that drive it MEASURE `connections_opened == 0` on the provider the real factory
built rather than asserting it in prose.

That is stated this way because the earlier wording -- "no test here sets
`PGHOST`, and none may" -- was already untrue of the leak test below, which sets
a sentinel `PGHOST`. It is safe, but for a reason the old sentence did not give:
`PGDATABASE` is checked first and refuses, so `_drain` returns before `_connect`
is ever called. The invariant that matters is "no connection is opened", and it
is now checked instead of promised.

A SECOND CORRECTION IS BAKED INTO THIS FILE'S SHAPE. Every test that depends on
an environment builds its OWN `VerificationState`. Driving the process-wide
`routes._VERIFICATION_STATE` does not work: it rate-limits a restart to
`MIN_REFRESH_INTERVAL_SECONDS` (60) per mode, so once an earlier test has touched
the private mode, a later test's `monkeypatch.setenv` never reaches a provider and
the test observes a CACHED status word produced under the ambient environment. Two
tests here were vacuous exactly that way -- the anti-leak sentinels were never
seen by any provider. The local state still uses the REAL
`routes._verification_provider_factory`, because the wiring under test is the
application's, not a stub's.
"""

from __future__ import annotations

import inspect
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from isaac_api import db_provider, db_recon, routes, verification
from isaac_api.app import app

ROUTE = "/api/runtime/verification"
PRIVATE = verification.AUTHORIZED_PRIVATE_SAMPLE
PUBLIC = verification.PUBLIC_REFERENCE


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _settle(client: TestClient, query: str = "", limit: int = 240) -> dict:
    """Poll until the background sweep leaves `running`, or fail loudly.

    THE BUDGET IS 120 SECONDS AND THAT IS NOT PADDING. The public sweep costs
    ~19s of real validation work on an unloaded machine, and this file's earlier
    tests start it, so a later test can arrive mid-sweep. A first draft allowed
    20s -- barely more than the sweep itself -- and the file passed alone only
    when a previous file had already warmed the process-wide cache, and failed
    when run on its own. That is order dependence, and this repository already
    carries enough of it; the fix is a budget that reflects how long the work
    actually takes, never a looser assertion about what the work returns.
    """
    for _ in range(limit):
        body = client.get(ROUTE + query).json()
        if body.get("status") != "running":
            return body
        time.sleep(0.5)
    pytest.fail(f"{ROUTE}{query} never left 'running'")


def _local_state() -> tuple[verification.VerificationState, list[Any]]:
    """A private `VerificationState` wired to the REAL provider factory.

    Returns the state and the list of providers the factory produced, so a test
    can assert on what the application's own wiring actually built -- above all
    `connections_opened`, which is the only direct evidence that no socket was
    opened.

    The capture wrapper calls `routes._verification_provider_factory()` and
    returns its product unchanged; it is not a stub, and replacing the factory
    with one would defeat the purpose of the file.

    NOT given `min_refresh_interval_seconds=0`: with a zero interval and a
    non-`ok` outcome (which is every case here, since nothing may connect) each
    `get` starts a fresh sweep and the state answers `running` forever. MEASURED
    -- a first draft of this helper did exactly that and hung the poll loop. The
    default 60s is what lets a settled failure be observed at all.
    """
    built: list[Any] = []

    def _capturing_factory() -> Any:
        provider = routes._verification_provider_factory()
        built.append(provider)
        return provider

    state = verification.VerificationState(
        routes.REPO_ROOT, provider_factory=_capturing_factory
    )
    return state, built


def _settle_state(
    state: verification.VerificationState, mode: str, limit: int = 240
) -> dict:
    for _ in range(limit):
        body = state.get(mode)
        if body.get("status") != "running":
            return body
        time.sleep(0.5)
    pytest.fail(f"the {mode} sweep never left 'running'")


def _clear_libpq(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE", "PGPORT"):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# The wire itself
# ---------------------------------------------------------------------------


def test_the_application_supplies_a_provider_factory() -> None:
    """The single line that makes the private mode reachable.

    Asserted on the module-level state the route actually uses, not on a fresh
    instance a test built -- a test that constructs its own `VerificationState`
    would pass no matter how `routes.py` wires the real one.
    """
    assert routes._VERIFICATION_STATE._provider_factory is not None, (
        "the deployed VerificationState has no provider_factory, so the "
        "authorized private mode cannot obtain records and is unreachable"
    )


def test_the_factory_builds_the_datastore_provider_and_reads_only_the_environment() -> None:
    """It takes no argument, so no request-derived value can reach the provider.

    The arity is asserted on the SIGNATURE, not by calling it with no arguments.
    Calling it successfully proves only that every parameter has a default -- a
    factory that gained `def _f(mode: str = "public")` and used `mode` would keep
    a call-based check green while a request-derived value reached the provider.
    """
    assert inspect.signature(routes._verification_provider_factory).parameters == {}, (
        "the factory must take no parameter at all: a defaulted one is still a "
        "channel a caller-influenced value could travel down"
    )

    provider = routes._verification_provider_factory()
    assert isinstance(provider, db_provider.DatastoreRecordProvider)
    # Constructing it must not connect. A provider that has not run yet reports
    # `not_run`; anything else means construction did work it should not.
    assert provider.state == db_provider.STATE_NOT_RUN


def test_the_private_mode_is_offered_by_the_engine() -> None:
    assert PRIVATE in verification.VERIFICATION_MODES
    assert routes._VERIFICATION_STATE.default_mode == PUBLIC, (
        "the default must stay the public corpus: a caller who names no mode "
        "must never be given the datastore one"
    )


# ---------------------------------------------------------------------------
# The route's mode parameter
# ---------------------------------------------------------------------------


def test_the_route_accepts_each_offered_mode(client: TestClient) -> None:
    for mode in verification.VERIFICATION_MODES:
        body = client.get(f"{ROUTE}?mode={mode}").json()
        assert body.get("status") != "refused", f"{mode} was refused"


def test_an_unknown_mode_is_REFUSED_not_silently_served_the_public_corpus(
    client: TestClient,
) -> None:
    """The failure that would matter most: a typo answered with real numbers.

    A caller asking for a mode this build does not offer must learn that, not
    receive the public preflight's figures under their own label.
    """
    for bogus in ("bogus", "", "PUBLIC_REFERENCE", "authorized_private_sample "):
        body = client.get(f"{ROUTE}?mode={bogus}").json()
        assert body.get("status") == "refused", f"{bogus!r} was not refused"


def test_omitting_the_mode_reads_the_public_corpus(client: TestClient) -> None:
    body = _settle(client)
    assert body.get("status") == "ok"
    assert body["metadata"]["verification_mode"] == PUBLIC


# ---------------------------------------------------------------------------
# Fail-closed, without a database
# ---------------------------------------------------------------------------


def test_the_private_mode_fails_closed_when_the_environment_has_no_database(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """No libpq variables at all -> `refused`, and MEASURED to be that word.

    This is the state every CI run and every developer machine is in, and it is
    also the state a pod is in if the database is not configured. It must be a
    calm status word, not a traceback and not a hang.

    WHICH GATE FIRES HERE, because the word depends on it and the two words are
    not interchangeable: with `PGDATABASE` unset, `db_recon.check_env_gates`
    rejects it (`"" != "metadata_assistant"`) before anything is opened, which is
    `refused`. It is NOT refused because the host is unknown -- that condition
    produces `unavailable`, and the companion test below pins it. An earlier
    version of this test asserted `refused` for an environment it never actually
    installed, so the distinction was unmeasured.

    `refused` also proves the application CONSTRUCTED a provider and let it run
    its own gates: with no factory at all the mode settles to `unavailable`
    instead, so accepting either word would let the whole wire be deleted while
    this test stayed green.
    """
    _clear_libpq(monkeypatch)

    state, built = _local_state()
    body = _settle_state(state, PRIVATE)

    assert body.get("status") == "refused", (
        f"expected 'refused' (the PGDATABASE pin rejects an unset value before "
        f"anything opens), got {body.get('status')!r}"
    )
    assert len(built) == 1, "the wire must build exactly one provider for one sweep"
    assert built[0].refusal_gate == "pgdatabase_env"
    assert built[0].connections_opened == 0, "a refusal must open no connection"

    # Whatever the word, it must never carry a corpus it did not read. A pending
    # report nulls these blocks rather than zeroing them, and the distinction is
    # the point: `None` says "not measured", `0` would say "measured, none found".
    official = body.get("official_validation")
    assert official is None or not official.get("passing")
    assert (body.get("metadata") or {}).get("corpus_size") in (None, 0)


def test_a_pinned_database_with_no_host_is_UNAVAILABLE_not_refused(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the distinction, and the one the contract got wrong.

    `PGDATABASE` is set to exactly the expected name, so the pin PASSES; the
    connection then cannot be made because the host, user and password are
    absent. MEASURED: that is `unavailable`, never `refused`.

    Why it is worth a test of its own: the published description used to say the
    private mode "is refused rather than attempted when its environment gates are
    unmet", which reads as though a missing `PGHOST` refuses. It does not, and an
    operator reading that of a pod reporting `unavailable` would conclude the
    DRIVER is missing from the image rather than that the HOST is unset -- a
    wrong diagnosis of a one-variable misconfiguration.

    A NOTE ON WHICH GATE FIRES, so this test is not read as proving more than it
    does. `connect_psycopg2` imports the driver before it inspects the variables,
    so on a checkout WITHOUT `psycopg2` the gate is `driver` and on the deployed
    image (which installs the `api` extra) it is `connect`. Both are
    `unavailable`, which is exactly why the assertion is on the served word and
    not on the gate name: the word is the contract, and it is the same either
    way. Neither path opens a socket, which is asserted rather than assumed.

    THIS TEST DOES NOT SET `PGHOST`. It is the absence of a host that is under
    test, so no connection can be attempted even with a driver present.
    """
    _clear_libpq(monkeypatch)
    monkeypatch.setenv("PGDATABASE", db_recon.EXPECTED_DATABASE)

    state, built = _local_state()
    body = _settle_state(state, PRIVATE)

    assert body.get("status") == "unavailable", (
        f"expected 'unavailable' (the PGDATABASE pin passed; no connection could "
        f"be obtained), got {body.get('status')!r} -- 'refused' would mean an "
        f"environment gate rejected the run, and none did"
    )
    assert len(built) == 1
    assert built[0].refusal_gate in {"driver", "connect"}, (
        f"unexpected gate {built[0].refusal_gate!r}: this environment must fail "
        f"at the driver import or at the missing libpq variables, nowhere else"
    )
    assert built[0].connections_opened == 0, "no host was configured; nothing may open"
    assert (body.get("metadata") or {}).get("corpus_size") in (None, 0)


def test_a_refused_private_report_leaks_no_environment_detail(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal names a gate, never a host, a user, a password or a path.

    The sentinels are only meaningful if a provider actually READS them, which
    is why this test drives its own state: on the process-wide one the private
    mode's 60s refresh floor meant the sweep it observed had been started under
    the ambient environment and no provider ever saw a sentinel. It asserted
    nothing at all.

    Setting a sentinel `PGHOST` is safe here for a checked reason rather than a
    hoped-for one: `PGDATABASE` is a sentinel too, so the pin refuses first and
    `_drain` returns before `_connect` -- and `connections_opened == 0` below is
    the measurement of that, not a restatement of it.
    """
    monkeypatch.setenv("PGHOST", "sentinel-host-must-never-be-served.invalid")
    monkeypatch.setenv("PGUSER", "sentinel-user-must-never-be-served")
    monkeypatch.setenv("PGPASSWORD", "sentinel-password-must-never-be-served")
    monkeypatch.setenv("PGDATABASE", "sentinel-database-must-never-be-served")

    state, built = _local_state()
    body = _settle_state(state, PRIVATE)

    assert body.get("status") == "refused"
    assert len(built) == 1, "no provider was built, so no sentinel was ever read"
    assert built[0].connections_opened == 0, (
        "a sentinel host must never be dialled: the PGDATABASE pin refuses first"
    )

    blob = repr(body)
    for sentinel in (
        "sentinel-host-must-never-be-served",
        "sentinel-user-must-never-be-served",
        "sentinel-password-must-never-be-served",
        "sentinel-database-must-never-be-served",
    ):
        assert sentinel not in blob, f"{sentinel} reached the served payload"


# ---------------------------------------------------------------------------
# The public mode is unchanged by any of this
# ---------------------------------------------------------------------------


def test_the_public_mode_never_calls_the_provider_factory(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wiring the private mode must not make the ordinary read touch a datastore.

    The factory is replaced with one that fails the test if it is called at all,
    then the public sweep is driven to completion.
    """
    called: list[str] = []

    def _tripwire() -> db_provider.DatastoreRecordProvider:
        called.append("called")
        raise AssertionError("the public mode built a datastore provider")

    state = verification.VerificationState(
        routes.REPO_ROOT, provider_factory=_tripwire
    )
    for _ in range(240):
        body = state.get()
        if body.get("status") != "running":
            break
        time.sleep(0.5)
    else:  # pragma: no cover - only on a pathologically slow machine
        pytest.fail("the public sweep never settled")

    assert called == [], "the public mode must not construct a datastore provider"
    assert body["metadata"]["verification_mode"] == PUBLIC
