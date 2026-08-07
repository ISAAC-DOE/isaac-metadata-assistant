"""Safety tests for ``GET /api/runtime/database/recon`` and the health block.

NO real driver, NO socket, NO database. Every test drives a fake DBAPI
connection whose ``cursor().execute()`` is answered from a dict keyed by the
exact SQL string the service module publishes as a module constant. That is the
same technique ``tests/test_db_recon.py`` uses for the service itself; here it
is pointed at the HTTP surface, because the HTTP surface is where a leak would
actually reach a person.

What these tests are for
------------------------
The endpoint's whole job is to be NARROWER than the reconnaissance report:
aggregates only, per ``docs/postgres-test-db-guide.md`` ("Displaying record
content"), which keeps hosted per-record display CLOSED BY DEFAULT. So the
tests are weighted towards proving absence — no record id, no title, no
scientific value, no stored document, no credential, no driver text — plus the
operational guarantees that make a single read-only scan safe against a role
with a connection limit of five.

Mutation testing
----------------
Each safeguard below was verified by temporarily breaking it and confirming a
named test fails; the mapping is recorded in the slice report. A safeguard whose
mutation broke nothing would be a coverage gap, not a passing suite.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from isaac_api import db_recon, routes

from conftest import client_ws, tutorial_client

RECON_PATH = "/api/runtime/database/recon"

# --- obviously-fake sensitive content ----------------------------------------
# Every one of these must be absent from every response body.

FAKE_TITLE = "TOTALLY-FAKE Operando XANES of Sample ZZ-QQ-000"
FAKE_SAMPLE = "FAKE-CuO-NANOPOWDER-9999"
FAKE_VALUE = "8979.3-eV-FAKE-EDGE-VALUE"
FAKE_PERSON = "Notareal Person"
FAKE_DRIFT_KEY = "portal_only_drift_field"
FAKE_SPECIES_KEY = "CuO2_mass_fraction"
FAKE_CONFIG_KEY = "monochromator_crystal"
FAKE_VOCAB_TERM = "fake_vocab_term_zzqq"

FAKE_ULID_A = "01JQZ0FAKEREC0NAAAAAAAAAAA"
FAKE_ULID_B = "01JQZ0FAKEREC0NBBBBBBBBBBB"
FAKE_ULID_MISSING = "01JQZ0FAKEREC0NZZZZZZZZZZZ"

FAKE_HOST = "fake-host.invalid.example"
FAKE_PASSWORD = "not-a-real-password-1234"
FAKE_USER = "metadata_assistant"

SENSITIVE_STRINGS = (
    FAKE_TITLE,
    FAKE_SAMPLE,
    FAKE_VALUE,
    FAKE_PERSON,
    FAKE_DRIFT_KEY,
    FAKE_SPECIES_KEY,
    FAKE_CONFIG_KEY,
    FAKE_VOCAB_TERM,
    FAKE_ULID_A,
    FAKE_ULID_B,
    FAKE_ULID_MISSING,
    FAKE_HOST,
    FAKE_PASSWORD,
)

#: Exactly what the frozen allowlist promises.
EXPECTED_TOP_LEVEL_KEYS = {
    "status",
    "report_format_version",
    "app_commit",
    "schema_version",
    "schema_fingerprint",
    "generated_at",
    "database",
    "dataset",
    "integrity",
    "limitations",
}


def fake_record(record_id: str, *, link_to: str | None = None) -> dict:
    """A synthetic record shaped like a drifted production record."""
    record = {
        "isaac_record_version": "1.05",
        "record_id": record_id,
        "record_type": "evidence",
        "record_domain": "characterization",
        "source_type": "facility",
        "timestamps": {"created": "2026-01-01T00:00:00Z"},
        "sample": {
            "name": FAKE_SAMPLE,
            "notes": FAKE_VALUE,
            "composition": {FAKE_SPECIES_KEY: 0.7},
        },
        "system": {"configuration": {FAKE_CONFIG_KEY: FAKE_VALUE}},
        "attribution": {"created_by": FAKE_PERSON},
        "descriptors": [{"name": "edge_energy", "value": FAKE_VALUE}],
        "title": FAKE_TITLE,
        FAKE_DRIFT_KEY: {"nested": FAKE_VALUE},
    }
    if link_to is not None:
        record["links"] = [
            {"rel": "derived_from", "target": link_to, "basis": "same_sample_id"}
        ]
    return record


# --- fakes -------------------------------------------------------------------


class FakeCursor:
    def __init__(self, rows: dict, log: list, *, explode_on: str | None = None):
        self._rows = rows
        self._log = log
        self._last = None
        self._explode_on = explode_on
        self.closed = False

    def execute(self, sql, params=None):
        self._last = sql
        self._log.append((sql, params))
        if self._explode_on is not None and self._explode_on in str(sql):
            raise RuntimeError(
                f"FATAL: relation blew up for {FAKE_USER}@{FAKE_HOST} "
                f"password={FAKE_PASSWORD} value={FAKE_VALUE}"
            )

    def fetchall(self):
        return list(self._rows.get(self._last, []))

    def close(self):
        self.closed = True


class FakeConnection:
    """Minimal DBAPI-ish stand-in with the bookkeeping the tests assert on."""

    def __init__(self, rows: dict, *, explode_on: str | None = None):
        self._rows = rows
        self._explode_on = explode_on
        self.log: list = []
        self.cursors: list[FakeCursor] = []
        self.readonly_requested = False
        self.closed = False
        self.rolled_back = False
        self.committed = False

    def set_session(self, readonly=False, **kwargs):
        self.readonly_requested = bool(readonly)

    def cursor(self):
        cur = FakeCursor(self._rows, self.log, explode_on=self._explode_on)
        self.cursors.append(cur)
        return cur

    def rollback(self):
        self.rolled_back = True

    def commit(self):  # pragma: no cover - must never be called
        self.committed = True

    def close(self):
        self.closed = True


def base_rows(records=(FAKE_ULID_A, FAKE_ULID_B), *, link_to=None) -> dict:
    """A fully-passing row map; individual tests override single entries."""
    page = [
        (
            rid + " ",  # CHAR(26) blank padding, as Postgres returns it
            "evidence",
            "characterization",
            fake_record(rid, link_to=link_to),
        )
        for rid in records
    ]
    return {
        db_recon.Q_TRANSACTION_READ_ONLY: [("on",)],
        db_recon.Q_CURRENT_DATABASE: [("metadata_assistant",)],
        db_recon.Q_CURRENT_USER: [("metadata_assistant", "metadata_assistant")],
        db_recon.Q_SSL: [(True, "TLSv1.3", "TLS_AES_256_GCM_SHA384", 256)],
        db_recon.Q_RECORDS_TABLE_PRESENT: [(1,)],
        db_recon.Q_RECORDS_TABLE_OWNER: [("metadata_assistant",)],
        db_recon.Q_IS_SUPERUSER: [("off",)],
        db_recon.Q_SERVER_VERSION: [("18.0", "180000")],
        db_recon.Q_RECORD_COUNT: [(len(page),)],
        db_recon.Q_TABLE_INVENTORY: [("records",), ("vocabulary_cache",)],
        db_recon.Q_RECORDS_BY_TYPE: [("evidence", len(page))],
        db_recon.Q_RECORDS_BY_DOMAIN: [("characterization", len(page))],
        db_recon.Q_RECORDS_PAGE: page,
        db_recon.Q_VOCAB_TABLE_PRESENT: [(1,)],
        db_recon.Q_VOCAB_COLUMNS: [("id", "integer"), ("category", "character varying")],
        db_recon.Q_VOCAB_COUNT: [(1234,)],
        db_recon.vocab_group_sql("category"): [(FAKE_VOCAB_TERM, 900)],
    }


# --- fixtures ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_recon_state(monkeypatch):
    """Every test starts with an empty cache, no last-scan, and a free lock."""
    monkeypatch.setattr(routes, "_db_recon_cached_payload", None, raising=False)
    monkeypatch.setattr(routes, "_db_recon_cached_at", None, raising=False)
    monkeypatch.setattr(routes, "_db_recon_last", None, raising=False)
    monkeypatch.setattr(routes, "_DB_RECON_SCAN_LOCK", threading.Lock())
    yield


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    for name in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        monkeypatch.delenv(name, raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def configure_db(monkeypatch, **overrides):
    """Put the deployed pod's documented libpq contract into the environment."""
    env = {
        "PGHOST": FAKE_HOST,
        "PGPORT": "5432",
        "PGDATABASE": "metadata_assistant",
        "PGUSER": FAKE_USER,
        "PGPASSWORD": FAKE_PASSWORD,
    }
    env.update(overrides)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def install_connection(monkeypatch, connection, *, opened: list | None = None):
    """Replace the driver connect with one that hands back ``connection``."""

    def _connect(env):
        if opened is not None:
            opened.append(env)
        return connection

    monkeypatch.setattr(db_recon, "connect_psycopg2", _connect)
    return connection


def ok_scan(monkeypatch, rows=None, **kwargs):
    conn = FakeConnection(base_rows() if rows is None else rows, **kwargs)
    opened: list = []
    install_connection(monkeypatch, conn, opened=opened)
    return conn, opened


# =============================================================================
# 1. configuration is the feature switch — and it never connects speculatively
# =============================================================================


def test_not_configured_returns_a_sanitized_payload_and_never_connects(
    client, monkeypatch
):
    """No PGHOST: today's no-database behaviour is preserved exactly."""
    opened: list = []
    monkeypatch.setattr(
        db_recon,
        "connect_psycopg2",
        lambda env: opened.append(env) or pytest.fail("must not connect"),
    )
    r = client.get(RECON_PATH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "not_configured"
    assert body["database"]["configured"] is False
    assert body["database"]["classification"] is None
    assert body["dataset"] is None and body["integrity"] is None
    assert opened == []


@pytest.mark.parametrize(
    "missing", ["PGUSER", "PGPASSWORD", "PGPORT", "PGDATABASE"]
)
def test_partially_configured_env_still_treats_pghost_as_the_switch(
    client, monkeypatch, missing
):
    """The guide names PGHOST as THE switch. A partial env must not crash and
    must not be silently reported as 'no database'."""
    configure_db(monkeypatch, **{missing: None})
    conn, opened = ok_scan(monkeypatch)
    r = client.get(RECON_PATH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["database"]["configured"] is True
    assert body["status"] != "not_configured"
    for needle in SENSITIVE_STRINGS:
        assert needle not in r.text


def test_pghost_present_is_the_feature_switch(client, monkeypatch):
    configure_db(monkeypatch)
    conn, opened = ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    assert body["status"] == "ok"
    assert body["database"]["configured"] is True
    assert len(opened) == 1


def test_blank_pghost_is_not_configured(client, monkeypatch):
    configure_db(monkeypatch, PGHOST="   ")
    monkeypatch.setattr(
        db_recon, "connect_psycopg2", lambda env: pytest.fail("must not connect")
    )
    assert client.get(RECON_PATH).json()["status"] == "not_configured"


# =============================================================================
# 2. connection failures are reported as a class name and nothing else
# =============================================================================


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError(f"could not connect to server {FAKE_HOST}:5432 timed out"),
        RuntimeError(
            f"FATAL: password authentication failed for user {FAKE_USER} "
            f"password={FAKE_PASSWORD}"
        ),
        OSError(f"SSL SYSCALL error: certificate verify failed for {FAKE_HOST}"),
    ],
    ids=["connect_timeout", "auth_failure", "tls_verification_failure"],
)
def test_driver_failures_never_reach_the_response(client, monkeypatch, exc):
    configure_db(monkeypatch)

    def _boom(env):
        raise exc

    monkeypatch.setattr(db_recon, "connect_psycopg2", _boom)
    r = client.get(RECON_PATH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] in {"refused", "error"}
    assert body["database"]["refusal_class"] == type(exc).__name__
    for needle in (FAKE_HOST, FAKE_PASSWORD, FAKE_USER, "FATAL", "SSL SYSCALL"):
        assert needle not in r.text, needle
    assert "Traceback" not in r.text


def test_a_real_connect_refusal_reports_only_its_gate(client, monkeypatch):
    configure_db(monkeypatch)

    def _boom(env):
        raise db_recon.ConnectionRefused(f"could not connect to {FAKE_HOST}")

    monkeypatch.setattr(db_recon, "connect_psycopg2", _boom)
    body = client.get(RECON_PATH).json()
    assert body["status"] == "refused"
    assert body["database"]["refusal_gate"] == "connect"
    assert FAKE_HOST not in json.dumps(body)


def test_mid_scan_driver_exception_never_leaks_its_message(client, monkeypatch):
    configure_db(monkeypatch)
    conn = FakeConnection(base_rows(), explode_on="pg_stat_ssl")
    install_connection(monkeypatch, conn)
    r = client.get(RECON_PATH)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert body["database"]["refusal_class"] == "RuntimeError"
    for needle in SENSITIVE_STRINGS:
        assert needle not in r.text, needle
    assert conn.closed is True


# =============================================================================
# 3. the fail-closed gates, through the HTTP surface
# =============================================================================


@pytest.mark.parametrize(
    "key, value, gate",
    [
        ("Q_SSL", [], "tls"),
        ("Q_SSL", [(False, None, None, None)], "tls"),
        ("Q_SSL", [(None, None, None, None)], "tls"),
        ("Q_CURRENT_DATABASE", [("isaac_production",)], "current_database"),
        ("Q_CURRENT_USER", [("postgres", "postgres")], "current_user"),
        ("Q_CURRENT_USER", [("metadata_assistant", "postgres")], "current_user"),
        ("Q_RECORDS_TABLE_PRESENT", [(0,)], "records_table"),
        ("Q_TRANSACTION_READ_ONLY", [("off",)], "transaction_read_only"),
        ("Q_RECORDS_TABLE_OWNER", [("isaac_portal",)], "not_production_shaped"),
        ("Q_IS_SUPERUSER", [("on",)], "not_production_shaped"),
        ("Q_IS_SUPERUSER", [], "not_production_shaped"),
    ],
    ids=[
        "tls_row_absent_fails_closed",
        "tls_reported_off",
        "tls_unknown_fails_closed",
        "unexpected_database",
        "unexpected_current_user",
        "unexpected_session_user_set_role",
        "missing_records_table",
        "read_only_not_enforced_server_side",
        "wrong_table_owner",
        "superuser_session",
        "superuser_unprovable_fails_closed",
    ],
)
def test_each_gate_refuses_through_the_endpoint(client, monkeypatch, key, value, gate):
    configure_db(monkeypatch)
    rows = base_rows()
    rows[getattr(db_recon, key)] = value
    conn = FakeConnection(rows)
    install_connection(monkeypatch, conn)

    r = client.get(RECON_PATH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "refused", body
    assert body["database"]["refusal_gate"] == gate
    # A refusal must not carry a report.
    assert body["dataset"] is None and body["integrity"] is None
    assert conn.closed is True


def test_wrong_table_shape_is_a_parse_failure_not_a_crash(client, monkeypatch):
    """A `records` row whose `data` is not a JSON object must be counted."""
    configure_db(monkeypatch)
    rows = base_rows()
    rows[db_recon.Q_RECORDS_PAGE] = [
        (FAKE_ULID_A, "evidence", "characterization", fake_record(FAKE_ULID_A)),
        (FAKE_ULID_B, "evidence", "characterization", "{not valid json at all"),
    ]
    install_connection(monkeypatch, FakeConnection(rows))
    body = client.get(RECON_PATH).json()
    assert body["status"] == "ok"
    assert body["dataset"]["parse_failures"] == 1
    assert body["dataset"]["records_parsed"] == 1
    assert body["dataset"]["records_scanned"] == 2


def test_unexpected_pgdatabase_refuses_before_any_socket_is_opened(
    client, monkeypatch
):
    """I2: the env gates run BEFORE `connect_psycopg2`, not inside `run_recon`.

    `db_recon`'s module contract states "the env gates run before any socket is
    opened". That was true for the CLI and FALSE for this endpoint, which
    connected first and only reached `check_env_gates` inside `run_recon` — so
    a wrong `PGDATABASE` burned one of the role's five connections before
    refusing.

    The earlier version of this test asserted only `conn.log == []`. That is
    true of the broken ordering too, so it passed while the claim it appeared
    to defend was false. The connection COUNT is the assertion that has teeth.
    """
    configure_db(monkeypatch, PGDATABASE="isaac_production")
    conn = FakeConnection(base_rows())
    opened: list = []
    install_connection(monkeypatch, conn, opened=opened)
    body = client.get(RECON_PATH).json()
    assert body["status"] == "refused"
    assert body["database"]["refusal_gate"] == "pgdatabase_env"
    assert opened == [], "no socket may be opened once the env gate refuses"
    assert conn.cursors == [], "no cursor may be created either"
    assert conn.log == [], "no statement may run once the env gate refused"


def test_the_env_gate_still_runs_inside_run_recon_as_defence_in_depth(monkeypatch):
    """I2: hoisting the gate must not REMOVE it from the shared service.

    `check_env_gates` is pure and idempotent, so both callers keep it. A future
    edit that deletes the copy inside `run_recon` would silently un-gate the
    CLI and any other caller.
    """
    with pytest.raises(db_recon.ReconRefusal) as exc:
        db_recon.run_recon(
            FakeConnection(base_rows()),
            env={"PGDATABASE": "isaac_production"},
            salt="s",
            require_opt_in=False,
        )
    assert exc.value.gate == "pgdatabase_env"


def test_the_endpoint_does_not_require_the_cli_opt_in_variable(client, monkeypatch):
    """The pod is never given ISAAC_RUN_SLAC_DB_RECON; demanding it would make
    this route permanently dead rather than safe."""
    configure_db(monkeypatch)
    monkeypatch.delenv("ISAAC_RUN_SLAC_DB_RECON", raising=False)
    ok_scan(monkeypatch)
    assert client.get(RECON_PATH).json()["status"] == "ok"


def test_read_only_enforcement_is_verified_server_side(client, monkeypatch):
    configure_db(monkeypatch)
    conn, _ = ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    assert body["database"]["gates"]["transaction_read_only"] is True
    assert body["integrity"]["transaction_read_only"] is True
    # the driver was also asked, and the session statements were issued
    assert conn.readonly_requested is True
    issued = [sql for sql, _ in conn.log]
    for statement in db_recon.SESSION_READ_ONLY_STATEMENTS:
        assert statement in issued
    assert db_recon.Q_TRANSACTION_READ_ONLY in issued


def test_every_gate_boolean_is_reported(client, monkeypatch):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    gates = client.get(RECON_PATH).json()["database"]["gates"]
    assert gates == {
        "database_identity": True,
        "current_user": True,
        "session_user": True,
        "tls": True,
        "records_table_present": True,
        "transaction_read_only": True,
        "not_production_shaped": True,
    }


# =============================================================================
# 4. the SQL that is issued: allowlisted, parameterized, read-only, no DML/DDL
# =============================================================================


def test_the_statement_allowlist_rejects_every_write(client):
    for sql in (
        "INSERT INTO records (record_id) VALUES ('x')",
        "UPDATE records SET data = '{}'",
        "DELETE FROM records",
        "DROP TABLE records",
        "CREATE TABLE t (id int)",
        "ALTER TABLE records ADD COLUMN x int",
        "TRUNCATE records",
        "GRANT ALL ON records TO public",
        "SELECT 1; DROP TABLE records",
        "SELECT * INTO backup FROM records",
    ):
        with pytest.raises(db_recon.UnsafeStatement):
            db_recon.assert_read_only_sql(sql)


def test_every_statement_issued_is_read_only_or_an_allowlisted_session_set(
    client, monkeypatch
):
    configure_db(monkeypatch)
    conn, _ = ok_scan(monkeypatch)
    client.get(RECON_PATH)
    assert conn.log, "the scan issued nothing at all"
    for sql, _params in conn.log:
        classification = db_recon.classify_statement(sql)
        assert classification in {"read", "session"}, (classification, sql)
        if classification == "session":
            assert sql in db_recon.SESSION_READ_ONLY_STATEMENTS


def test_no_dml_and_no_ddl_is_an_observation_not_a_claim(client, monkeypatch):
    configure_db(monkeypatch)
    conn, _ = ok_scan(monkeypatch)
    integrity = client.get(RECON_PATH).json()["integrity"]
    assert integrity["dml_statements_issued"] == 0
    assert integrity["ddl_statements_issued"] == 0
    # the counters are real: they counted the reads that DID happen
    assert integrity["read_statements_issued"] > 0
    assert integrity["session_statements_issued"] == len(
        db_recon.SESSION_READ_ONLY_STATEMENTS
    )
    assert sum(1 for sql, _ in conn.log if db_recon.classify_statement(sql) == "dml") == 0
    assert sum(1 for sql, _ in conn.log if db_recon.classify_statement(sql) == "ddl") == 0


def test_the_dml_counter_can_actually_count(client):
    """Guards the guard: an auditing proxy that counted nothing would make the
    two zeros above meaningless."""
    audit = db_recon.StatementAudit()
    for sql in ("INSERT INTO records VALUES (1)", "DROP TABLE records", "SELECT 1"):
        audit.record(sql)
    assert audit.as_dict()["dml"] == 1
    assert audit.as_dict()["ddl"] == 1
    assert audit.as_dict()["read"] == 1


def test_record_values_are_bound_as_parameters_never_interpolated(
    client, monkeypatch
):
    configure_db(monkeypatch)
    conn, _ = ok_scan(monkeypatch)
    client.get(RECON_PATH)
    page = [entry for entry in conn.log if entry[0] == db_recon.Q_RECORDS_PAGE]
    assert page, "the record page query was never issued"
    for sql, params in page:
        assert "%s" in sql, "the fetch bound must be a placeholder, not a literal"
        assert params is not None and isinstance(params, tuple)
    # And the one identifier interpolation is shape-guarded.
    with pytest.raises(db_recon.UnsafeStatement):
        db_recon.vocab_group_sql("category; DROP TABLE records")


# =============================================================================
# 5. resource discipline: one connection, always closed, rollback-safe
# =============================================================================


def test_exactly_one_connection_per_scan_and_it_is_closed(client, monkeypatch):
    configure_db(monkeypatch)
    conn, opened = ok_scan(monkeypatch)
    client.get(RECON_PATH)
    assert len(opened) == 1
    assert conn.closed is True
    assert conn.rolled_back is True
    assert conn.committed is False


def test_the_cursor_is_closed_on_success_and_on_exception(client, monkeypatch):
    configure_db(monkeypatch)
    conn, _ = ok_scan(monkeypatch)
    client.get(RECON_PATH)
    assert conn.cursors and all(c.closed for c in conn.cursors)

    conn2 = FakeConnection(base_rows(), explode_on="pg_stat_ssl")
    install_connection(monkeypatch, conn2)
    routes._db_recon_cached_payload = None
    routes._db_recon_cached_at = None
    client.get(RECON_PATH)
    assert conn2.cursors and all(c.closed for c in conn2.cursors)
    assert conn2.closed is True


def test_the_connection_is_closed_on_a_gate_refusal_too(client, monkeypatch):
    configure_db(monkeypatch)
    rows = base_rows()
    rows[db_recon.Q_SSL] = []
    conn = FakeConnection(rows)
    install_connection(monkeypatch, conn)
    client.get(RECON_PATH)
    assert conn.closed is True
    assert conn.rolled_back is True


def test_a_close_that_itself_raises_cannot_break_the_response(client, monkeypatch):
    configure_db(monkeypatch)

    class Nasty(FakeConnection):
        def close(self):
            raise RuntimeError(f"close blew up {FAKE_PASSWORD}")

        def rollback(self):
            raise RuntimeError(f"rollback blew up {FAKE_PASSWORD}")

    install_connection(monkeypatch, Nasty(base_rows()))
    r = client.get(RECON_PATH)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert FAKE_PASSWORD not in r.text


# =============================================================================
# 6. concurrency and caching: the connection limit is 5, we use at most 1
# =============================================================================


def test_a_scan_already_in_progress_is_409_and_opens_no_connection(
    client, monkeypatch
):
    configure_db(monkeypatch)
    opened: list = []
    monkeypatch.setattr(
        db_recon,
        "connect_psycopg2",
        lambda env: opened.append(env) or pytest.fail("must not connect"),
    )
    routes._DB_RECON_SCAN_LOCK.acquire()
    try:
        r = client.get(RECON_PATH)
    finally:
        routes._DB_RECON_SCAN_LOCK.release()
    assert r.status_code == 409
    body = r.json()
    assert body["status"] == "busy"
    assert body["database"]["refusal_gate"] == "concurrent_scan"
    assert set(body) == EXPECTED_TOP_LEVEL_KEYS
    assert opened == []


class RecordingLock:
    """A lock that records exactly how ``acquire`` was called."""

    def __init__(self, *, held: bool = False):
        self.calls: list[dict] = []
        self._held = held

    def acquire(self, blocking=True, timeout=-1):
        self.calls.append({"blocking": blocking, "timeout": timeout})
        if self._held:
            return False
        self._held = True
        return True

    def release(self):
        self._held = False


def test_the_lock_is_acquired_non_blocking(client, monkeypatch):
    """A queued second caller would hold a request thread waiting on a database
    round trip. The acquire must be non-blocking with NO timeout — a "short"
    blocking wait is still a wait, and is not what this contract promises."""
    configure_db(monkeypatch)
    lock = RecordingLock()
    monkeypatch.setattr(routes, "_DB_RECON_SCAN_LOCK", lock)
    ok_scan(monkeypatch)
    assert client.get(RECON_PATH).json()["status"] == "ok"
    assert lock.calls == [{"blocking": False, "timeout": -1}]


def test_a_held_lock_answers_immediately_without_waiting(client, monkeypatch):
    configure_db(monkeypatch)
    monkeypatch.setattr(db_recon, "connect_psycopg2", lambda env: pytest.fail("no"))
    lock = RecordingLock(held=True)
    monkeypatch.setattr(routes, "_DB_RECON_SCAN_LOCK", lock)

    started = time.monotonic()
    r = client.get(RECON_PATH)
    elapsed = time.monotonic() - started

    assert r.status_code == 409
    assert lock.calls == [{"blocking": False, "timeout": -1}]
    assert elapsed < 0.5, f"the endpoint waited {elapsed:.3f}s on the scan lock"


def test_a_real_held_lock_does_not_hang_a_request_thread(client, monkeypatch):
    """The same guarantee through the real `threading.Lock`, off the main thread."""
    configure_db(monkeypatch)
    monkeypatch.setattr(db_recon, "connect_psycopg2", lambda env: pytest.fail("no"))
    routes._DB_RECON_SCAN_LOCK.acquire()
    try:
        done = []

        def call():
            done.append(client.get(RECON_PATH).status_code)

        thread = threading.Thread(target=call)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), "the endpoint blocked on the scan lock"
    finally:
        routes._DB_RECON_SCAN_LOCK.release()
    assert done == [409]


def test_the_lock_is_released_even_when_the_scan_refuses(client, monkeypatch):
    configure_db(monkeypatch)
    rows = base_rows()
    rows[db_recon.Q_SSL] = []
    install_connection(monkeypatch, FakeConnection(rows))
    client.get(RECON_PATH)
    assert routes._DB_RECON_SCAN_LOCK.acquire(blocking=False)
    routes._DB_RECON_SCAN_LOCK.release()


def test_a_repeat_call_inside_the_ttl_opens_no_second_connection(
    client, monkeypatch
):
    configure_db(monkeypatch)
    opened: list = []
    conn = FakeConnection(base_rows())
    install_connection(monkeypatch, conn, opened=opened)
    first = client.get(RECON_PATH).json()
    second = client.get(RECON_PATH).json()
    assert len(opened) == 1, "the TTL cache did not prevent a second connection"
    assert first == second


def test_an_expired_cache_rescans(client, monkeypatch):
    configure_db(monkeypatch)
    opened: list = []
    install_connection(monkeypatch, FakeConnection(base_rows()), opened=opened)
    client.get(RECON_PATH)
    # age the cache past the TTL
    routes._db_recon_cached_at = (
        routes._db_recon_cached_at - routes._DB_RECON_CACHE_TTL_SECONDS - 1.0
    )
    install_connection(monkeypatch, FakeConnection(base_rows()), opened=opened)
    client.get(RECON_PATH)
    assert len(opened) == 2


def test_a_failed_scan_is_not_cached(client, monkeypatch):
    configure_db(monkeypatch)
    rows = base_rows()
    rows[db_recon.Q_SSL] = []
    opened: list = []
    install_connection(monkeypatch, FakeConnection(rows), opened=opened)
    assert client.get(RECON_PATH).json()["status"] == "refused"
    install_connection(monkeypatch, FakeConnection(base_rows()), opened=opened)
    assert client.get(RECON_PATH).json()["status"] == "ok"
    assert len(opened) == 2


def test_the_cache_hands_out_copies_not_the_stored_object(client, monkeypatch):
    """A caller that mutated the served dict would poison every later response."""
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    client.get(RECON_PATH)
    served = routes._db_recon_cache_get()
    served["dataset"]["total_records"] = 999_999
    served["status"] = "tampered"
    again = routes._db_recon_cache_get()
    assert again["dataset"]["total_records"] == 2
    assert again["status"] == "ok"
    assert routes._db_recon_cached_payload["dataset"]["total_records"] == 2
    # and the HTTP surface still serves the untampered report
    assert client.get(RECON_PATH).json()["dataset"]["total_records"] == 2


# =============================================================================
# 7. the projection: exactly the frozen keys, and nothing sensitive
# =============================================================================


def test_the_response_has_exactly_the_frozen_top_level_key_set(client, monkeypatch):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    assert set(body) == EXPECTED_TOP_LEVEL_KEYS
    assert set(body) == set(routes._DB_RECON_RESPONSE_KEYS)


@pytest.mark.parametrize(
    "scenario",
    ["ok", "not_configured", "refused", "busy"],
)
def test_every_response_shape_uses_the_same_frozen_key_set(
    client, monkeypatch, scenario
):
    if scenario == "not_configured":
        r = client.get(RECON_PATH)
    elif scenario == "busy":
        configure_db(monkeypatch)
        routes._DB_RECON_SCAN_LOCK.acquire()
        try:
            r = client.get(RECON_PATH)
        finally:
            routes._DB_RECON_SCAN_LOCK.release()
    else:
        configure_db(monkeypatch)
        rows = base_rows()
        if scenario == "refused":
            rows[db_recon.Q_SSL] = []
        install_connection(monkeypatch, FakeConnection(rows))
        r = client.get(RECON_PATH)
    assert set(r.json()) == EXPECTED_TOP_LEVEL_KEYS, scenario


# --- I3: the caveats travel with the numbers they qualify --------------------


def _response_for_shape(client, monkeypatch, shape):
    """One response per status the operation can produce. Helper for I3/M4."""
    if shape == "not_configured":
        return client.get(RECON_PATH)
    configure_db(monkeypatch)
    if shape == "busy":
        routes._DB_RECON_SCAN_LOCK.acquire()
        try:
            return client.get(RECON_PATH)
        finally:
            routes._DB_RECON_SCAN_LOCK.release()
    if shape == "error":
        install_connection(
            monkeypatch, FakeConnection(base_rows(), explode_on="pg_stat_ssl")
        )
        return client.get(RECON_PATH)
    rows = base_rows()
    if shape == "refused":
        rows[db_recon.Q_SSL] = []
    install_connection(monkeypatch, FakeConnection(rows))
    return client.get(RECON_PATH)


ALL_RESPONSE_SHAPES = ("ok", "not_configured", "busy", "refused", "error")


@pytest.mark.parametrize("shape", ALL_RESPONSE_SHAPES)
def test_every_response_shape_carries_the_honesty_limitations(
    client, monkeypatch, shape
):
    """I3: `db_recon.HONEST_NOTES` was dropped entirely by the projection.

    The served report showed a bare `gates: {not_production_shaped: true, tls:
    true}` with no caveat, from which a reader would reasonably conclude the
    app had VERIFIED it is not talking to production. It cannot, and the
    module's own notes say so — the production check is a tripwire and TLS is
    encrypted but unauthenticated. Rendering a backstop as a guarantee is the
    defect; the caveats now travel with the numbers, in EVERY shape.
    """
    r = _response_for_shape(client, monkeypatch, shape)
    body = r.json()
    assert body["status"] == (
        "ok"
        if shape == "ok"
        else "error"
        if shape == "error"
        else shape
    ), shape
    limitations = body["limitations"]
    assert isinstance(limitations, list) and limitations, shape
    assert all(isinstance(item, str) and item.strip() for item in limitations), shape


@pytest.mark.parametrize(
    "needle",
    [
        # 1. the production gate is a tripwire, and the real guarantee is external
        "TRIPWIRE, not proof",
        "cannot be verified from inside a connection",
        # 2. TLS is encrypted, not authenticated
        "pg_stat_ssl",
        "encrypts WITHOUT verifying the server certificate",
        # 3. server_version is server-controlled and shape-gated (I1)
        "server_version is a server-controlled string",
        # 4. the no-write guarantee, and what the row counts are NOT (I4/M2)
        "verified read-only",
        "SELECT-only allowlist",
        "CONCURRENCY CHECK, not as a mutation proof",
        "rows_modified is therefore any writer's net delta",
        # 5. aggregates only; per-record display is closed (M2/M4 scope)
        "AGGREGATES ONLY",
        "closed by default",
    ],
)
def test_the_limitations_state_each_thing_the_gates_cannot_establish(
    client, monkeypatch, needle
):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    text = " ".join(client.get(RECON_PATH).json()["limitations"])
    assert needle in text


def test_the_limitations_are_a_constant_not_a_derived_value(client, monkeypatch):
    """I3: fixed module-level code constants — no data path, no interpolation.

    Byte-identical across two independent scans is what proves it: anything
    derived from the report, the environment or the clock would differ.
    """
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    first = client.get(RECON_PATH).json()["limitations"]
    # Defeat the TTL cache so the second call is a real second projection.
    monkeypatch.setattr(routes, "_db_recon_cached_payload", None, raising=False)
    monkeypatch.setattr(routes, "_db_recon_cached_at", None, raising=False)
    ok_scan(monkeypatch)
    second = client.get(RECON_PATH).json()["limitations"]
    assert first == second
    assert first == list(routes._DB_RECON_LIMITATIONS)
    # And identical in a completely different shape, too.
    assert client.get(RECON_PATH).json()["limitations"] == first


# --- M4: the last line of defence is unconditional ---------------------------


@pytest.mark.parametrize("shape", ALL_RESPONSE_SHAPES)
def test_the_leak_scan_runs_over_every_response_shape(client, monkeypatch, shape):
    """M4: the scan ran only on the success path.

    `not_configured`, `refused`, `error` and `busy` bypassed it. They are safe
    by construction today — every string in them is a code constant — but a
    "last line of defence" that is conditional on the outcome is not one.
    """
    scanned: list[str] = []
    leaf_sets: list[tuple[str, ...]] = []
    original = db_recon.scan_for_leaks

    def recording(text, *, env, allow_raw_ids, leaves):
        scanned.append(text)
        leaf_sets.append(tuple(leaves))
        return original(text, env=env, allow_raw_ids=allow_raw_ids, leaves=leaves)

    monkeypatch.setattr(db_recon, "scan_for_leaks", recording)
    r = _response_for_shape(client, monkeypatch, shape)
    assert scanned, f"{shape}: the response was returned without a leak scan"
    assert json.dumps(r.json(), sort_keys=True) in [
        json.dumps(json.loads(t), sort_keys=True) for t in scanned
    ], shape

    # AND the leaves actually passed are the payload's, not an empty tuple.
    #
    # Requiring `leaves` stops a caller OMITTING it. It does not stop a caller
    # passing `()`, which is legal, silently reinstates the escaping defect in
    # the endpoint, and — before this assertion existed — left the whole suite
    # green: the only thing that went red was a content-hash drift test, which
    # CLAUDE.md §17 tells the author to regenerate. So the production wiring was
    # protected by a file digest rather than by a behavioural test.
    for text, leaves in zip(scanned, leaf_sets):
        expected = db_recon.string_leaves(json.loads(text))
        assert set(leaves) == set(expected), (
            f"{shape}: scan_for_leaks was called with leaves={leaves!r}, which is "
            f"not the scanned payload's string leaves — a value containing a "
            f"JSON-escaped character would be invisible to this scan"
        )
        assert leaves, f"{shape}: leaves was empty; the decoded-leaf scan is a no-op"


def test_a_tripped_scan_on_a_failure_envelope_still_returns_the_frozen_shape(
    client, monkeypatch
):
    """The guard's own fallback must not recurse and must stay in-shape."""
    configure_db(monkeypatch)
    monkeypatch.setattr(
        db_recon,
        "scan_for_leaks",
        lambda text, *, env, allow_raw_ids, leaves: ["synthetic"],
    )
    install_connection(monkeypatch, FakeConnection({}))
    r = client.get(RECON_PATH)
    body = r.json()
    assert set(body) == EXPECTED_TOP_LEVEL_KEYS
    assert body["status"] == "error"
    assert body["database"]["refusal_gate"] == "leak_scan"


def test_no_record_id_no_title_no_scientific_value_no_full_json(
    client, monkeypatch
):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    text = client.get(RECON_PATH).text
    for needle in SENSITIVE_STRINGS:
        assert needle not in text, needle
    # not even a digest LIST — only its count
    body = json.loads(text)
    assert "record_id_digests" not in json.dumps(body)
    assert isinstance(body["dataset"]["record_id_digest_count"], int)


def test_no_secret_no_env_value_no_connection_detail(client, monkeypatch):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    text = client.get(RECON_PATH).text
    lowered = text.lower()
    for needle in (
        FAKE_HOST,
        FAKE_PASSWORD,
        "pgpassword",
        "pghost",
        "postgresql://",
        "postgres://",
        "sslmode",
        "connect_timeout",
    ):
        assert needle.lower() not in lowered, needle
    body = json.loads(text)
    assert "host" not in body["database"]
    assert "port" not in body["database"]
    assert "user" not in body["database"]
    assert "current_user" not in body["database"]


def test_structural_path_lists_are_excluded(client, monkeypatch):
    """`structure.distinct_signatures[].paths` is in the report and must NOT be
    in the response: a path list is a description of every record's shape."""
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    dumped = json.dumps(body)
    assert "distinct_signatures" not in dumped
    assert "path_presence" not in dumped
    assert "masked_key_segments" not in dumped
    # The schema-side path projection that DOES survive carries only names the
    # public vendored schema already publishes — that is the whole redaction
    # policy — plus JSON Schema keywords and array indices.
    declared, _ = db_recon.load_schema_vocabulary(routes.REPO_ROOT)
    allowed = (
        declared
        | db_recon._SCHEMA_KEYWORDS
        | {
            db_recon.ARRAY_SEGMENT,
            db_recon.MASK_OPEN_MAP_KEY,
            db_recon.MASK_UNDECLARED_KEY,
            db_recon.MASK_NON_IDENTIFIER,
            "$",
        }
    )
    for entry in body["dataset"]["by_schema_path"]:
        for segment in entry["schema_path"].split("/"):
            assert segment.isdigit() or segment in allowed, segment


def test_vocabulary_values_are_excluded_and_so_is_the_row_count(
    client, monkeypatch
):
    """The service's own notes concede a lowercase slug cannot be PROVEN to be a
    vocabulary term rather than data, so no term value is emitted — and the row
    COUNT is a cardinality of production-derived rows that the owner's guide
    does not enumerate, so only presence survives (G3)."""
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    dumped = json.dumps(body)
    assert FAKE_VOCAB_TERM not in dumped
    assert "grouped" not in dumped
    assert body["dataset"]["vocabulary_cache_present"] is True
    assert "vocabulary_term_count" not in body["dataset"]
    assert "1234" not in dumped


def test_the_vocabulary_presence_flag_is_false_when_the_table_is_absent(
    client, monkeypatch
):
    """Presence must be OBSERVED, not hardcoded — otherwise the coarser field
    would be a constant wearing a reachability field's name."""
    configure_db(monkeypatch)
    rows = base_rows()
    rows[db_recon.Q_VOCAB_TABLE_PRESENT] = [(0,)]
    install_connection(monkeypatch, FakeConnection(rows))
    body = client.get(RECON_PATH).json()
    assert body["status"] == "ok"
    assert body["dataset"]["vocabulary_cache_present"] is False


def test_raw_record_ids_are_never_requested(client, monkeypatch):
    configure_db(monkeypatch)
    captured = {}
    original = db_recon.run_recon

    def spy(connection, **kwargs):
        captured.update(kwargs)
        return original(connection, **kwargs)

    monkeypatch.setattr(db_recon, "run_recon", spy)
    ok_scan(monkeypatch)
    client.get(RECON_PATH)
    assert captured["emit_raw_record_ids"] is False
    assert captured["require_opt_in"] is False


def test_the_dataset_counts_are_the_documented_aggregates(client, monkeypatch):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    dataset = client.get(RECON_PATH).json()["dataset"]
    assert dataset["total_records"] == 2
    assert dataset["expected_seed_rows"] == 30
    assert dataset["seed_count_matches"] is False
    assert dataset["records_scanned"] == 2
    assert dataset["records_parsed"] == 2
    assert dataset["parse_failures"] == 0
    assert (
        dataset["records_passing_full_schema"] + dataset["records_failing_full_schema"]
        == 2
    )
    assert dataset["by_record_type"] == [{"value": "evidence", "count": 2}]
    assert dataset["by_record_domain"] == [{"value": "characterization", "count": 2}]
    assert dataset["total_validation_issues"] >= 1  # the fixture is drifted


def test_the_dataset_block_has_exactly_the_frozen_key_set(client, monkeypatch):
    """The `dataset` block is where a record-derived aggregate would re-appear.

    Freezing only the TOP-LEVEL keys left `dataset` open: four record-derived
    aggregates shipped inside it in v0.0.32 without tripping a single contract
    test. The block is now built key-by-key from `_DB_RECON_DATASET_KEYS`, and
    this asserts the served set matches it exactly — no extra, none missing.
    """
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    dataset = client.get(RECON_PATH).json()["dataset"]
    assert set(dataset) == set(routes._DB_RECON_DATASET_KEYS)
    assert list(dataset) == list(routes._DB_RECON_DATASET_KEYS), "order is frozen too"
    for withheld in routes._DB_RECON_WITHHELD_AGGREGATES:
        assert withheld not in dataset


def test_the_integrity_block_has_exactly_the_frozen_key_set(client, monkeypatch):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    integrity = client.get(RECON_PATH).json()["integrity"]
    assert set(integrity) == set(routes._DB_RECON_INTEGRITY_KEYS)


def test_the_database_block_has_exactly_the_frozen_key_set(client, monkeypatch):
    """The THIRD nested block, closed for the same reason as the other two.

    `dataset` and `integrity` were frozen by the G3 narrowing, but `database`
    was left a hand-written dict literal — which is the *same* structural gap
    that let five unauthorized aggregates ship inside `dataset` in v0.0.32,
    merely relocated one block over. Nothing in `database` is record-derived
    today; this asserts it stays that way by construction rather than by
    everyone remembering.
    """
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    database = client.get(RECON_PATH).json()["database"]
    assert set(database) == set(routes._DB_RECON_DATABASE_KEYS)
    assert list(database) == list(routes._DB_RECON_DATABASE_KEYS), "order is frozen too"
    assert set(database["gates"]) == set(routes._DB_RECON_GATE_KEYS)


def test_an_unlisted_database_key_fails_closed_rather_than_being_served(
    client, monkeypatch
):
    """Same contract as the `dataset` guard: REFUSE, never silently drop."""
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    monkeypatch.setattr(
        routes,
        "_DB_RECON_DATABASE_KEYS",
        tuple(k for k in routes._DB_RECON_DATABASE_KEYS if k != "configured"),
    )
    body = client.get(RECON_PATH).json()
    assert body["status"] == "error"
    assert body["dataset"] is None


def test_an_unlisted_gate_name_fails_closed_rather_than_being_served(
    client, monkeypatch
):
    """A gate name reaching the response unlisted must stop the report."""
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    monkeypatch.setattr(
        routes,
        "_DB_RECON_GATE_KEYS",
        tuple(k for k in routes._DB_RECON_GATE_KEYS if k != "tls"),
    )
    body = client.get(RECON_PATH).json()
    assert body["status"] == "error"
    assert body["dataset"] is None


def test_the_withheld_list_is_a_constant_naming_every_withheld_aggregate(
    client, monkeypatch
):
    """The narrowing must be VISIBLE. A silent projection change is
    indistinguishable from a scan that found nothing."""
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    dataset = client.get(RECON_PATH).json()["dataset"]
    assert dataset["withheld_pending_visibility_decision"] == list(
        routes._DB_RECON_WITHHELD_AGGREGATES
    )
    assert set(dataset["withheld_pending_visibility_decision"]) == {
        "by_instance_path",
        "distinct_structural_signatures",
        "total_link_count",
        "dangling_link_count",
        "vocabulary_term_count",
    }


def test_the_limitations_name_the_narrowing_against_the_owners_list(
    client, monkeypatch
):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    text = " ".join(client.get(RECON_PATH).json()["limitations"])
    assert "record counts, counts by type and domain, validation totals" in text
    assert "withheld pending an explicit visibility decision" in text
    assert "by_rule_family, by_schema_path" in text


def test_an_unlisted_dataset_key_fails_closed_rather_than_being_served(
    client, monkeypatch
):
    """Guards the guard: the allowlist must REFUSE, not silently drop.

    A dropped key would let a future edit believe it had shipped a field while
    callers never saw it; a served key would be the leak this exists to stop.
    Neither: the projection raises, and `_db_recon_scan` converts that into the
    sanitized `projection` failure envelope.
    """
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    monkeypatch.setattr(
        routes,
        "_DB_RECON_DATASET_KEYS",
        tuple(k for k in routes._DB_RECON_DATASET_KEYS if k != "total_records"),
    )
    body = client.get(RECON_PATH).json()
    assert body["status"] == "error"
    assert body["database"]["refusal_gate"] == "projection"
    assert body["dataset"] is None


@pytest.mark.parametrize(
    "link_to",
    [None, FAKE_ULID_A, FAKE_ULID_MISSING],
    ids=["no_links", "resolvable_link", "dangling_link"],
)
def test_link_derived_counts_are_never_projected(client, monkeypatch, link_to):
    """G3: `total_link_count` / `dangling_link_count` are derived from
    `data->'links'`, which means reading the stored documents.

    The owner's guide authorises "record counts, counts by type and domain,
    validation totals, schema version, database reachability". A link count is
    none of those. The guide's only mention of dangling links sits under
    "Gotchas to code around" — an instruction for CODE, not an authorization to
    DISPLAY — so it must not be read as one.

    This test FAILS against the shipped v0.0.32 projection, which emitted both.
    """
    configure_db(monkeypatch)
    rows = base_rows(link_to=link_to)
    install_connection(monkeypatch, FakeConnection(rows))
    body = client.get(RECON_PATH).json()
    assert body["status"] == "ok"
    dataset = body["dataset"]
    assert "total_link_count" not in dataset
    assert "dangling_link_count" not in dataset
    # The names appear ONLY in the withheld list, never as a served value.
    served = {
        k: v
        for k, v in dataset.items()
        if k != "withheld_pending_visibility_decision"
    }
    assert "link_count" not in json.dumps(served)
    assert FAKE_ULID_MISSING not in json.dumps(body)
    # and the withholding is STATED rather than silent
    assert "total_link_count" in dataset["withheld_pending_visibility_decision"]
    assert "dangling_link_count" in dataset["withheld_pending_visibility_decision"]


def test_instance_paths_are_never_projected(client, monkeypatch):
    """G3: `by_instance_path` is a path through the stored RECORD.

    Every segment is masked against the public schema, so nothing is *named*
    that the schema does not already publish — but the fact that a path is
    POPULATED can only be produced by reading a stored document, and with a
    documented seed of 30 rows an `error_count` of 1 at a specific path is a
    per-record fact wearing aggregate clothing. The schema-side counterpart
    (`by_schema_path`) is retained; this one is not.

    This test FAILS against the shipped v0.0.32 projection.
    """
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    dataset = body["dataset"]
    assert "by_instance_path" not in dataset
    assert "failing_instance_paths" not in json.dumps(body)
    assert "instance_path" not in json.dumps(
        {k: v for k, v in dataset.items() if k != "withheld_pending_visibility_decision"}
    )
    assert "by_instance_path" in dataset["withheld_pending_visibility_decision"]
    # the retained, schema-side breakdowns still carry the drift signal
    assert isinstance(dataset["by_rule_family"], list)
    assert isinstance(dataset["by_schema_path"], list)


def test_distinct_structural_signature_count_is_never_projected(
    client, monkeypatch
):
    """G3: a count of distinct record SHAPES is a record-derived structural
    fact. It is an integer, which is exactly why it looked harmless: over a
    30-row corpus it still reports how heterogeneous the stored documents are,
    and the owner's guide enumerates no such aggregate.

    This test FAILS against the shipped v0.0.32 projection.
    """
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    dataset = body["dataset"]
    assert "distinct_structural_signatures" not in dataset
    assert "signature" not in json.dumps(
        {k: v for k, v in dataset.items() if k != "withheld_pending_visibility_decision"}
    )
    assert (
        "distinct_structural_signatures"
        in dataset["withheld_pending_visibility_decision"]
    )


def test_the_service_still_computes_what_the_endpoint_withholds(monkeypatch):
    """The narrowing is a PROJECTION boundary, not a deletion.

    `run_recon` keeps computing the structure/link aggregates for
    `scripts/db_recon.py`, which the Dockerfile COPY allowlist keeps out of the
    image. If this ever stops being true the withholding has been implemented
    by removing the capability instead of by bounding the response, and the
    two entry points have silently diverged.
    """
    report = db_recon.run_recon(
        FakeConnection(base_rows(link_to=FAKE_ULID_MISSING)),
        env={"PGDATABASE": "metadata_assistant"},
        salt="fixed-test-salt",
        require_opt_in=False,
    )
    assert report["records"]["links"]["total_link_count"] == 2
    assert report["records"]["links"]["dangling_link_count"] == 2
    assert isinstance(report["structure"]["distinct_signature_count"], int)
    assert report["validation"]["failing_instance_paths"] is not None
    assert report["vocabulary_cache"]["row_count"] == 1234


def test_the_cli_wrapper_is_absent_from_the_container_image():
    """The wider report may exist only where no application route can reach it.

    `scripts/db_recon.py` is the only consumer of the withheld aggregates. The
    Dockerfile's COPY is an explicit ALLOWLIST and names exactly one file out of
    `scripts/`, so the wrapper is not in the image and cannot be invoked in the
    pod — which is the only place the database is reachable from at all.
    """
    dockerfile = (routes.REPO_ROOT / "Dockerfile").read_text("utf-8")
    copied = [
        line.strip()
        for line in dockerfile.splitlines()
        if line.strip().startswith("COPY") and "scripts/" in line
    ]
    assert copied == [
        "COPY scripts/check_graphify_freshness.py scripts/check_graphify_freshness.py"
    ], copied
    assert "COPY scripts/db_recon.py" not in dockerfile
    assert "COPY scripts/ " not in dockerfile and "COPY scripts/\n" not in dockerfile


def test_the_response_is_deterministically_ordered(client, monkeypatch):
    configure_db(monkeypatch)
    install_connection(monkeypatch, FakeConnection(base_rows()))
    first = client.get(RECON_PATH).json()
    routes._db_recon_cached_payload = None
    routes._db_recon_cached_at = None
    install_connection(monkeypatch, FakeConnection(base_rows()))
    second = client.get(RECON_PATH).json()
    for body in (first, second):
        body.pop("generated_at")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_runtime_identity_is_reported(client, monkeypatch):
    configure_db(monkeypatch)
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "deadbeefcafe")
    ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    assert body["report_format_version"] == 1
    assert body["app_commit"] == "deadbeefcafe"
    assert body["schema_version"] == "1.05"
    assert len(body["schema_fingerprint"]) == 64
    assert body["generated_at"].endswith("Z")


def test_the_postgres_version_is_reported_never_gated(client, monkeypatch):
    configure_db(monkeypatch)
    rows = base_rows()
    rows[db_recon.Q_SERVER_VERSION] = [("16.4", "160004")]
    install_connection(monkeypatch, FakeConnection(rows))
    body = client.get(RECON_PATH).json()
    assert body["status"] == "ok", "a version mismatch must never refuse"
    assert body["database"]["server_version_major"] == 16
    assert body["database"]["expected_major_version"] == 18
    assert body["database"]["expected_major_version_match"] is False


def test_the_expected_version_matches_when_it_matches(client, monkeypatch):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    assert body["database"]["server_version"] == "18.0"
    assert body["database"]["server_version_major"] == 18
    assert body["database"]["expected_major_version_match"] is True


@pytest.mark.parametrize(
    "hostile",
    [
        "18.0 (SUPER-SECRET-VALUE) /etc/passwd",
        "18.0 " + "Z" * 100_000,
        "not a version at all",
        "18.0\npassword=hunter2",
    ],
    ids=["injected_secret", "unbounded", "free_text", "embedded_newline"],
)
def test_a_server_controlled_version_string_is_masked_not_projected(
    client, monkeypatch, hostile
):
    """I1: `server_version` is an UNVETTED VERBATIM server string.

    It was projected raw, so a 100,000-character value or
    `18.0 (SUPER-SECRET-VALUE) /etc/passwd` passed straight through — and the
    final leak scan cannot recognise arbitrary text, so it could not catch it.
    It now goes through `db_recon.safe_version_value`, the same dotted-numeric
    guard already applied to `isaac_record_version`.

    Nothing that matters is lost: `server_version_major` is an int, is derived
    from `server_version_num`, and still carries the useful signal.
    """
    configure_db(monkeypatch)
    rows = base_rows()
    rows[db_recon.Q_SERVER_VERSION] = [(hostile, "180000")]
    install_connection(monkeypatch, FakeConnection(rows))
    r = client.get(RECON_PATH)
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"]["server_version"] == db_recon.MASK_UNRECOGNISED
    for needle in ("SUPER-SECRET-VALUE", "/etc/passwd", "hunter2", "Z" * 40):
        assert needle not in r.text
    assert len(r.text) < 20_000, "an unbounded server string reached the wire"
    # The signal that actually matters survives the mask.
    assert body["database"]["server_version_major"] == 18
    assert body["database"]["expected_major_version_match"] is True


def test_the_leak_scan_replaces_the_report_when_it_trips(client, monkeypatch):
    """The last backstop: if a value ever did reach the projection, the response
    is replaced by a sanitized failure rather than sent."""
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    original = routes._db_recon_project

    def leaky(report, authority, statements):
        payload = original(report, authority, statements)
        payload["dataset"]["oops"] = FAKE_ULID_A
        return payload

    monkeypatch.setattr(routes, "_db_recon_project", leaky)
    r = client.get(RECON_PATH)
    body = r.json()
    assert body["status"] == "error"
    assert body["database"]["refusal_gate"] == "leak_scan"
    assert FAKE_ULID_A not in r.text
    assert body["dataset"] is None


def test_a_non_serializable_projection_is_sanitized_not_a_bare_500(
    client, monkeypatch
):
    """M3: the leak scan's `json.dumps` sat OUTSIDE the projection's guard.

    A value the projection produced but `json.dumps` cannot encode escaped the
    `try/except BaseException` two lines above it and surfaced as an unhandled
    500 — the one failure mode the sanitized envelope exists to prevent. The
    serialisation now lives inside the same guard.
    """
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    original = routes._db_recon_project

    class _Unserializable:
        def __repr__(self) -> str:  # pragma: no cover - must never be rendered
            return f"{FAKE_HOST}/{FAKE_PASSWORD}"

    def unserializable(report, authority, statements):
        payload = original(report, authority, statements)
        payload["dataset"]["oops"] = _Unserializable()
        return payload

    monkeypatch.setattr(routes, "_db_recon_project", unserializable)
    r = client.get(RECON_PATH)
    assert r.status_code == 200, "a bare 500 escaped the sanitized envelope"
    body = r.json()
    assert set(body) == EXPECTED_TOP_LEVEL_KEYS
    assert body["status"] == "error"
    assert body["database"]["refusal_gate"] == "projection"
    assert body["dataset"] is None
    for needle in SENSITIVE_STRINGS:
        assert needle not in r.text


@pytest.mark.parametrize("signal", [KeyboardInterrupt, SystemExit])
def test_process_signals_are_reraised_not_reported_as_a_scan_error(
    monkeypatch, signal
):
    """M9: `except BaseException` turned a Ctrl-C or a shutdown into a 200.

    `KeyboardInterrupt` and `SystemExit` are process-lifecycle signals, not
    scan outcomes. Swallowing them into `status: "error"` would keep the
    process alive through a shutdown request.
    """

    def _raise(env):
        raise signal()

    monkeypatch.setattr(db_recon, "connect_psycopg2", _raise)
    env = {
        "PGHOST": FAKE_HOST,
        "PGDATABASE": "metadata_assistant",
        "PGUSER": FAKE_USER,
        "PGPASSWORD": FAKE_PASSWORD,
    }
    with pytest.raises(signal):
        routes._db_recon_scan(env)


# =============================================================================
# 8. the validator authority is the FULL vendored schema
# =============================================================================


def test_validation_uses_the_full_official_schema(client, monkeypatch):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    authority = db_recon.schema_authority(routes.REPO_ROOT)
    assert authority["full_schema"] is True
    assert body["schema_fingerprint"] == authority["fingerprint"]
    assert body["integrity"]["full_schema_fingerprint_match"] is True
    assert body["integrity"]["partial_schema_validation_runs"] == 0
    assert body["integrity"]["schema_stable_across_run"] is True


def test_the_partial_validation_count_is_a_count_not_a_disguised_boolean(
    client, monkeypatch
):
    """M1: `partial_schema_validation_runs` was `0 if stable else 1`.

    That is a boolean wearing a count's name — it reported the before/after
    FINGERPRINT signal, not a number of validations. The spec requires the
    field name, so it stays, but it is now the literal count it claims to be:
    always 0, because a partial schema refuses at the `full_schema_authority`
    gate before a single record is validated. The fingerprint signal moved to
    its own boolean, `schema_stable_across_run`.

    Here the schema CHANGES under the scan mid-run. The old field would have
    flipped to 1, asserting that a validation ran against a partial schema —
    which never happened.
    """
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    real = db_recon.schema_authority
    calls: list[int] = []

    def drifting(root):
        result = dict(real(root))
        calls.append(1)
        if len(calls) > 1:  # the AFTER read sees a different authority
            result["fingerprint"] = "0" * 64
        return result

    monkeypatch.setattr(db_recon, "schema_authority", drifting)
    body = client.get(RECON_PATH).json()
    assert body["status"] == "ok"
    integrity = body["integrity"]
    assert integrity["schema_stable_across_run"] is False
    assert integrity["full_schema_fingerprint_match"] is False
    assert integrity["partial_schema_validation_runs"] == 0, (
        "no validation ran against a partial schema, so the count must stay 0"
    )


def test_rows_modified_is_zero_by_construction_and_says_so(client, monkeypatch):
    """M2: the field name is spec-required; the invariant is documented.

    `rows_modified` is any writer's net delta over the scan window, not ours,
    and is 0 by construction because an unequal count raises `MutationDetected`
    before a report is produced. The `limitations` list must say exactly that.
    """
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    body = client.get(RECON_PATH).json()
    assert body["integrity"]["rows_modified"] == 0
    text = " ".join(body["limitations"])
    assert "rows_modified is therefore any writer's net delta" in text
    assert "0 by construction" in text


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: {**s, "additionalProperties": True},
        lambda s: {**s, "properties": {"record_id": s["properties"]["record_id"]}},
        lambda s: {**s, "required": ["record_id"]},
        lambda s: {
            **s,
            "properties": {
                **s["properties"],
                "isaac_record_version": {"type": "string", "const": "0.99"},
            },
        },
    ],
    ids=["root_opened", "properties_trimmed", "required_trimmed", "version_moved"],
)
def test_a_trimmed_schema_is_rejected_as_validator_authority(
    client, monkeypatch, tmp_path, mutate
):
    """A subset schema would report a false 'everything passes' over real
    records, so it must be refused rather than used."""
    real = json.loads(
        (routes.REPO_ROOT / "schema" / "isaac_record_v1.json").read_text("utf-8")
    )
    fake_root = tmp_path / "fakeroot"
    (fake_root / "schema").mkdir(parents=True)
    (fake_root / "schema" / "isaac_record_v1.json").write_text(
        json.dumps(mutate(real)), encoding="utf-8"
    )
    assert db_recon.schema_authority(fake_root)["full_schema"] is False

    configure_db(monkeypatch)
    conn = FakeConnection(base_rows())
    install_connection(monkeypatch, conn)
    monkeypatch.setattr(routes, "REPO_ROOT", fake_root)
    body = client.get(RECON_PATH).json()
    assert body["status"] == "refused"
    assert body["database"]["refusal_gate"] == "full_schema_authority"
    assert conn.log == [], "nothing may be read against a partial schema"


def test_the_schema_resolves_under_the_container_layout(tmp_path):
    """In the image the layout is `/app/{schema,src,apps/api}`, so a
    `__file__.parent.parent` guess would resolve to `/app/apps`. The service
    reuses the repo-root finder the rest of the API uses, which walks up until
    the vendored schema is found — correct under both layouts."""
    from isaac_records.official import schema_path

    app_root = tmp_path / "app"
    (app_root / "schema").mkdir(parents=True)
    (app_root / "apps" / "api" / "isaac_api").mkdir(parents=True)
    (app_root / "src").mkdir()
    real = (routes.REPO_ROOT / "schema" / "isaac_record_v1.json").read_bytes()
    (app_root / "schema" / "isaac_record_v1.json").write_bytes(real)

    from isaac_api import workspace

    module_file = app_root / "apps" / "api" / "isaac_api" / "db_recon.py"
    module_file.write_text("", encoding="utf-8")
    here = module_file.resolve()
    found = None
    for candidate in (here, *here.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            found = candidate
            break
    assert found == app_root, "the repo-root walk must find /app, not /app/apps"
    assert schema_path(found).exists()
    # and the real module resolved a root whose schema exists
    assert schema_path(db_recon.REPO_ROOT).exists()
    assert db_recon.REPO_ROOT == workspace.REPO_ROOT


# =============================================================================
# 9. the endpoint takes nothing, mutates nothing, and seeds nothing
# =============================================================================


def test_the_operation_accepts_no_parameter_and_no_body(client, monkeypatch):
    schema = client.get("/api/openapi").json()
    op = schema["paths"][RECON_PATH]["get"]
    assert op.get("parameters", []) == []
    assert "requestBody" not in op


def test_the_operation_is_get_only(client, monkeypatch):
    configure_db(monkeypatch)
    monkeypatch.setattr(db_recon, "connect_psycopg2", lambda env: pytest.fail("no"))
    for method in (client.post, client.put, client.delete, client.patch):
        assert method(RECON_PATH).status_code == 405


def test_query_parameters_are_ignored_not_honoured(client, monkeypatch):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    body = client.get(
        RECON_PATH + "?record_id=" + FAKE_ULID_A + "&sql=SELECT+*&limit=1"
    ).json()
    assert body["status"] == "ok"
    assert FAKE_ULID_A not in json.dumps(body)


def test_the_scan_writes_nothing_to_the_workspace(client, monkeypatch, tmp_path):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    ws_dir = tmp_path / "ws"
    before = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    client.get(RECON_PATH)
    after = sorted(p.relative_to(ws_dir) for p in ws_dir.rglob("*")) if ws_dir.exists() else []
    assert after == before


def test_a_configured_database_does_not_seed_synthetic_records(client, monkeypatch):
    """The scan must read the database, not fabricate rows when it is present."""
    configure_db(monkeypatch)
    rows = base_rows(records=(FAKE_ULID_A,))
    install_connection(monkeypatch, FakeConnection(rows))
    body = client.get(RECON_PATH).json()
    assert body["dataset"]["total_records"] == 1
    assert body["dataset"]["records_scanned"] == 1
    # ...and the worked-example workspace is untouched by this operation. Re-pointed:
    # the five examples now live in a worked-example session, so the check opens one
    # and asserts the same five records are there afterwards, unchanged in count.
    scoped = client_ws(tutorial_client(client.app))
    assert len(scoped.list_experiments()) == 5
    body_again = client.get(RECON_PATH).json()
    assert body_again["dataset"]["records_scanned"] == 1
    assert len(scoped.list_experiments()) == 5


# =============================================================================
# 10. health: configuration only, zero I/O, never fails
# =============================================================================


def test_health_reports_no_database_when_unconfigured(client, monkeypatch):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] == {
        "configured": False,
        "classification": None,
        "contains_production_derived_records": None,
        "record_display": "closed",
        "last_recon": None,
    }


def test_health_reports_the_database_when_configured(client, monkeypatch):
    configure_db(monkeypatch)
    body = client.get("/api/health").json()
    assert body["database"]["configured"] is True
    assert body["database"]["classification"] == "isolated-app-postgres"
    assert body["database"]["contains_production_derived_records"] is True
    assert body["database"]["record_display"] == "closed"
    assert body["database"]["last_recon"] is None


def test_health_performs_no_io_and_opens_no_connection(client, monkeypatch):
    configure_db(monkeypatch)
    monkeypatch.setattr(
        db_recon, "connect_psycopg2", lambda env: pytest.fail("health must not connect")
    )
    monkeypatch.setattr(
        db_recon, "run_recon", lambda *a, **k: pytest.fail("health must not scan")
    )
    for _ in range(3):
        assert client.get("/api/health").status_code == 200


def test_health_never_blocks_on_an_in_progress_scan(client, monkeypatch):
    """The readiness probe must answer even mid-scan."""
    configure_db(monkeypatch)
    routes._DB_RECON_SCAN_LOCK.acquire()
    try:
        r = client.get("/api/health")
    finally:
        routes._DB_RECON_SCAN_LOCK.release()
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_status_is_unaffected_by_a_broken_database(client, monkeypatch):
    configure_db(monkeypatch)

    def _boom(env):
        raise RuntimeError(f"FATAL: {FAKE_HOST} unreachable")

    monkeypatch.setattr(db_recon, "connect_psycopg2", _boom)
    assert client.get(RECON_PATH).json()["status"] == "error"
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["mode"] == "synthetic-only"
    assert r.json()["database"]["last_recon"]["status"] == "error"
    assert FAKE_HOST not in r.text


def test_health_surfaces_the_last_successful_scan(client, monkeypatch):
    configure_db(monkeypatch)
    ok_scan(monkeypatch)
    client.get(RECON_PATH)
    last = client.get("/api/health").json()["database"]["last_recon"]
    assert last["status"] == "ok"
    assert last["at"].endswith("Z")


def test_health_keeps_its_original_keys_byte_identical(client, monkeypatch):
    configure_db(monkeypatch)
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "sha-for-health")
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["mode"] == "synthetic-only"
    assert body["core"] == "isaac_records"
    assert body["commit"] == "sha-for-health"
    assert body["version"]
    assert set(body) == {
        "status",
        "mode",
        "core",
        "version",
        "commit",
        "database",
        # ADDED, and this test's own name explains why it had to be added here
        # rather than tolerated by loosening the comparison: the point of the
        # assertion is that `database` did not disturb the keys that predate it, so
        # it has to be an exact set. `experiment_storage` is a SIBLING of
        # `database`, never a member of it — the two answer different questions
        # (the read-only diagnostic over the production-derived sample, versus
        # where THIS application stores its own experiments), and nesting one
        # inside the other would be the conflation this file exists to prevent.
        "experiment_storage",
    }


def test_health_carries_no_secret_or_connection_detail(client, monkeypatch):
    configure_db(monkeypatch)
    text = client.get("/api/health").text.lower()
    for needle in (FAKE_HOST, FAKE_PASSWORD, "pghost", "pgpassword", "postgres://"):
        assert needle.lower() not in text, needle


# --- the JSON-escaping blind spot -------------------------------------------
#
# `scan_for_leaks` was called ONLY with `json.dumps(payload, ensure_ascii=True)`.
# JSON escapes every non-ASCII character to `\uXXXX`, and always escapes `"`,
# `\`, newline and tab. The forbidden env value was compared as a raw Python
# string, so for any such value `value in text` was PERMANENTLY FALSE and the
# `env_value_present` check could not fire at all.
#
# The same defect class is documented in `verification._leak_scan` (with
# `verification._string_leaves` as its decoded-leaf walker), where it was fixed;
# it stayed live here. That module lands with feat/record-verification (PR #63)
# and is not on main yet. These tests are the negative controls
# that were missing: parametrised over exactly the characters JSON escapes, each
# one FAILS if the leaves argument stops being consulted.

_ESCAPING_PASSWORDS = (
    pytest.param("motdepassé-secret-value", id="non-ascii-latin"),
    pytest.param("σερνετ-value", id="non-ascii-greek"),
    pytest.param("secret→value", id="non-ascii-arrow"),
    pytest.param("secretÅngstrom-value", id="non-ascii-angstrom"),
    pytest.param('sec"ret-value', id="double-quote"),
    pytest.param("sec\\ret-value", id="backslash"),
    pytest.param("sec\nret-value", id="newline"),
    pytest.param("sec\tret-value", id="tab"),
)


@pytest.mark.parametrize("password", _ESCAPING_PASSWORDS)
def test_the_leak_scan_catches_an_env_value_that_json_escapes(password):
    """A leaked credential must be caught whatever characters it contains."""
    payload = {"some_field": password}
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)

    issues = db_recon.scan_for_leaks(
        serialized,
        env={"PGPASSWORD": password},
        allow_raw_ids=False,
        leaves=db_recon.string_leaves(payload),
    )
    assert "env_value_present:PGPASSWORD" in issues, (
        f"a leaked password containing {password!r} was NOT detected; "
        "the scan is blind to the representation JSON gave it"
    )


@pytest.mark.parametrize("password", _ESCAPING_PASSWORDS)
def test_the_serialized_text_ALONE_would_miss_it(password):
    """Fixture validity: every canary above really IS re-represented by JSON.

    This is what makes the parametrised cases valid negative controls. It does
    NOT protect the fix — removing the fix turns nine other tests red and leaves
    this one green, because it never calls `scan_for_leaks`. An earlier version
    of this docstring claimed it was the test holding the fix in place, which
    overstated its role.
    """
    payload = {"some_field": password}
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)

    assert password not in serialized, (
        f"{password!r} survives JSON encoding unchanged, so it is not a valid "
        "negative control for the escaping defect"
    )


def test_an_ascii_env_value_is_still_caught_guard_against_over_correction():
    """The control that proves the parametrised cases above are about ESCAPING."""
    password = "hunter2supersecretvalue"
    payload = {"some_field": password}
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    assert password in serialized

    issues = db_recon.scan_for_leaks(
        serialized,
        env={"PGPASSWORD": password},
        allow_raw_ids=False,
        leaves=db_recon.string_leaves(payload),
    )
    assert "env_value_present:PGPASSWORD" in issues


def test_a_leaked_value_arriving_as_a_mapping_KEY_is_caught():
    """Histogram cells are keyed by strings, so a key is a real leak surface."""
    password = "kéy-shaped-secret-value"
    payload = {"cells": {password: 3}}
    issues = db_recon.scan_for_leaks(
        json.dumps(payload, sort_keys=True, ensure_ascii=True),
        env={"PGPASSWORD": password},
        allow_raw_ids=False,
        leaves=db_recon.string_leaves(payload),
    )
    assert "env_value_present:PGPASSWORD" in issues


def test_a_secret_SHAPE_whose_separator_json_escapes_is_caught_only_via_leaves():
    """The fix widened `secret_shape` too, and nothing was holding that.

    An independent review measured this gap in the test suite rather than in the
    code: reinstating the defect (`haystacks = (text,)`) turned twelve tests red,
    and every one of them was an `env_value_present` or endpoint case. Not one
    `secret_shape` test moved — so a real improvement in detection was riding
    along uncovered, and a future edit that kept env values working could have
    dropped it in silence.

    `_SECRET_SHAPES` matches the bearer token across `\\s`. In the serialized
    text a newline is the TWO characters `\\` and `n`, which `\\s` does not
    match, so this token is invisible there and visible only in the decoded
    leaf. That makes it the exact canary for the widening.
    """
    token = "bearer\nabcdefgh12345678"
    payload = {"some_field": token}
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)

    # Fixture validity: text alone really is blind to this one.
    assert not [
        code
        for code in db_recon.scan_for_leaks(
            serialized, env={}, allow_raw_ids=False, leaves=()
        )
        if code.startswith("secret_shape:")
    ], "text alone already catches this token, so it is not a valid control"

    issues = db_recon.scan_for_leaks(
        serialized, env={}, allow_raw_ids=False, leaves=db_recon.string_leaves(payload)
    )
    assert "secret_shape:bearer_token" in issues, (
        "a bearer token separated by a JSON-escaped newline was NOT detected; "
        "the leaf scan is the only haystack that can see it"
    )


def test_a_leaf_walk_failure_is_sanitized_AND_named_as_its_own_gate(client, monkeypatch):
    """The leaf walk is inside the guard, and does not borrow projection's name.

    Two properties, and the second exists because the first was fixed carelessly.

    `string_leaves` is a Python-level recursive walk while `json.dumps` encodes in
    C, so it exhausts the stack at a shallower depth: measured, at depth 1200 the
    encoder succeeds and the walk raises. Computed as a bare argument to
    `scan_for_leaks` — outside the `try` that the surrounding comment says exists
    to stop exactly this — that band escaped as a 500 with a traceback. It is now
    inside the guard, so it collapses into the sanitized envelope.

    But the envelope's `refusal_gate` names the STAGE, and folding a third stage
    into a block labelled `projection` produces a safe response carrying a wrong
    label — and the label is what a later reader debugs against. `RecursionError`
    from this block can only be the walk: `json.dumps` raises `ValueError` on
    deep nesting, not `RecursionError`, and `_db_recon_project` is a flat
    allowlist projection. So the type is a sound discriminator, and narrowing by
    it beats splitting the `try` — splitting is what put the walk outside a guard
    to begin with.

    No traceback, no payload, no exception message: a gate name and a class name.

    THE FAKE RAISES ONCE, AND THAT IS THE REALISTIC SHAPE, not a convenience.
    An unconditional raiser also breaks the walk over the FAILURE envelope —
    `_db_recon_failure` runs `_db_recon_leak_guard` over its own small dict — and
    the response then comes back under `leak_scan` instead. That degradation is
    correct behaviour and worth knowing about (the envelope fails closed rather
    than escaping), but it is not what a stack overflow does in production: the
    overflow is a function of DEPTH, the deep object is the report, and the
    envelope is three levels deep. So the fake reproduces the real condition —
    the walk fails on the report and succeeds on the envelope — instead of a
    condition that cannot occur.
    """
    configure_db(monkeypatch)
    ok_scan(monkeypatch)

    real_string_leaves = db_recon.string_leaves
    calls = {"n": 0}

    def _blow_the_stack_on_the_report(node):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RecursionError("maximum recursion depth exceeded")
        return real_string_leaves(node)

    monkeypatch.setattr(db_recon, "string_leaves", _blow_the_stack_on_the_report)

    response = client.get(RECON_PATH)
    body = response.json()
    assert body["status"] == "error"
    assert body["database"]["refusal_gate"] == "leaf_walk", (
        "a leaf-walk failure must not be reported under the projection gate"
    )
    assert body["dataset"] is None
    # The envelope carries the class name and nothing else from the exception.
    assert "maximum recursion depth" not in response.text
    assert "Traceback" not in response.text


def test_leaves_is_required_so_a_caller_cannot_silently_restore_the_defect():
    """No default. A default of () would re-enable the bug by omission."""
    with pytest.raises(TypeError, match="leaves"):
        db_recon.scan_for_leaks(  # type: ignore[call-arg]
            "{}", env={}, allow_raw_ids=False
        )


def test_string_leaves_walks_keys_values_and_nesting():
    payload = {"a": "one", "b": {"nested-key": ["two", {"c": "three"}]}, "d": 4}
    assert set(db_recon.string_leaves(payload)) == {
        "a", "one", "b", "nested-key", "two", "c", "three", "d",
    }


# --- the ENDPOINT, not just the function ------------------------------------
#
# Everything above tests `scan_for_leaks` directly. That left the production
# wiring — the two `routes.py` call sites — covered by nothing behavioural: an
# independent review reinstated the defect verbatim by passing `leaves=()` at
# both sites and the entire suite stayed green apart from a content-hash drift
# test, which CLAUDE.md §17 instructs the author to regenerate. These two tests
# close that: they drive the real endpoint and assert the real refusal.

@pytest.mark.parametrize(
    "password",
    [
        pytest.param("leaked-pässword-value", id="non-ascii"),
        pytest.param('leaked"password-value', id="double-quote"),
        pytest.param("leaked\\password-value", id="backslash"),
    ],
)
def test_the_ENDPOINT_refuses_when_an_escaping_credential_reaches_the_payload(
    client, monkeypatch, password
):
    """A credential JSON would escape must still trip the endpoint's own gate."""
    configure_db(monkeypatch, PGPASSWORD=password)

    real_project = routes._db_recon_project

    def leaking_project(report, authority, statements):
        payload = real_project(report, authority, statements)
        # Simulate the failure this gate exists for: a projection that lets a
        # credential through. It must be REFUSED, not returned.
        payload["schema_fingerprint"] = password
        return payload

    monkeypatch.setattr(routes, "_db_recon_project", leaking_project)
    # `base_rows()` is the fixture that passes every EARLIER gate — an empty
    # FakeConnection refuses at `transaction_read_only` and never reaches the
    # projection, so the leak scan would not be exercised at all.
    install_connection(monkeypatch, FakeConnection(base_rows()))

    r = client.get(RECON_PATH)
    body = r.json()

    assert set(body) == EXPECTED_TOP_LEVEL_KEYS
    # `error`, with `refusal_gate: leak_scan`. Note the asymmetry: the LOG line
    # reads `outcome=refused gate=leak_scan` but the SERVED status is `error`
    # (routes.py `_db_recon_failure(status="error", gate="leak_scan")`). Do not
    # take the log wording as the contract — a first draft of this test asserted
    # `refused` and passed for the wrong reason, against a connection that was
    # actually being turned away at the `transaction_read_only` gate long before
    # the leak scan ran.
    assert body["status"] == "error", (
        f"the endpoint RETURNED a payload containing {password!r}; the leak scan "
        "did not fire, because the raw value and its JSON representation differ"
    )
    assert body["database"]["refusal_gate"] == "leak_scan"
    # And the credential itself is nowhere in what was actually served.
    assert password not in r.text
    assert password not in json.dumps(body, ensure_ascii=False)


def test_the_ENDPOINT_still_serves_a_clean_report_ascii_control(client, monkeypatch):
    """Guard against over-correction: an unleaked report is still returned."""
    configure_db(monkeypatch)
    install_connection(monkeypatch, FakeConnection(base_rows()))

    r = client.get(RECON_PATH)
    body = r.json()

    assert set(body) == EXPECTED_TOP_LEVEL_KEYS
    assert body["status"] == "ok"
    assert body["database"].get("refusal_gate") != "leak_scan"
