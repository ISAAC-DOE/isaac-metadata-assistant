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

WHAT THIS FILE DELIBERATELY DOES NOT DO: open a database connection. No test here
sets `PGHOST`, and none may. The private mode is exercised in its refusing state,
which is what an environment without the libpq variables must produce.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from isaac_api import db_provider, routes, verification
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
    """It takes no argument, so no request-derived value can reach the provider."""
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
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No libpq variables -> a status word, not a traceback and not a hang.

    This is the state every CI run and every developer machine is in, and it is
    also the state a pod is in if the database is not configured. It must be a
    calm refusal.
    """
    for var in ("PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE", "PGPORT"):
        monkeypatch.delenv(var, raising=False)

    body = _settle(client, f"?mode={PRIVATE}")

    # `refused` SPECIFICALLY, and the precision is the second guard on the wire.
    # The two failure words are not interchangeable here, and MEASURED to differ:
    #   * provider built, gates unmet          -> `refused`
    #   * no provider_factory at all           -> `unavailable`
    # So asserting `refused` proves the application actually CONSTRUCTED a
    # provider and let it run its own gates, rather than merely holding a
    # non-None attribute. Accepting `unavailable` here would let the whole wire
    # be deleted while this test stayed green.
    assert body.get("status") == "refused", (
        f"expected 'refused' (provider built, environment gates unmet), got "
        f"{body.get('status')!r} -- 'unavailable' means no provider was built at all"
    )
    # Whatever the word, it must never carry a corpus it did not read. A pending
    # report nulls these blocks rather than zeroing them, and the distinction is
    # the point: `None` says "not measured", `0` would say "measured, none found".
    official = body.get("official_validation")
    assert official is None or not official.get("passing")
    assert (body.get("metadata") or {}).get("corpus_size") in (None, 0)


def test_a_refused_private_report_leaks_no_environment_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal names a gate, never a host, a user, a password or a path."""
    monkeypatch.setenv("PGHOST", "sentinel-host-must-never-be-served.invalid")
    monkeypatch.setenv("PGUSER", "sentinel-user-must-never-be-served")
    monkeypatch.setenv("PGPASSWORD", "sentinel-password-must-never-be-served")
    monkeypatch.setenv("PGDATABASE", "sentinel-database-must-never-be-served")

    body = _settle(client, f"?mode={PRIVATE}")
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
