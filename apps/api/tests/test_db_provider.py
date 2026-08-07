"""The read-only record source, driven entirely by in-process fake doubles.

NOTHING HERE OPENS A CONNECTION. Every test supplies its own ``connect``
callable returning a :class:`FakeConnection`, so no socket, no driver and no
credential is involved. The one test that touches the real connector asserts it
REFUSES when the driver is absent, which is the only thing it can do here.

The suite is organised around ``authorization.DATASTORE_CONSTRAINTS``: each
constraint the owner imposed has at least one test that would fail if the
implementation quietly stopped honouring it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api import db_provider
from isaac_api.db_provider import (
    FROZEN_STATEMENTS,
    DatastoreRecordProvider,
    PolicyViolation,
    StatementPolicy,
    classify_statement,
    normalize_identifier,
    parse_row,
)

ROOT = Path(__file__).resolve().parents[3]

#: The environment the deployed pod is documented to have. `check_env_gates`
#: pins `PGDATABASE`; the rest are only read by the real connector, which these
#: tests replace.
ENV = {
    "PGDATABASE": "metadata_assistant",
    "PGHOST": "example.invalid",
    "PGUSER": "metadata_assistant",
    "PGPASSWORD": "not-a-real-password",
}


class QueryCanceledError(Exception):
    """Named to match psycopg2's timeout exception, which is what the provider
    classifies on -- the driver is imported lazily and may be absent, so the
    class object cannot be referenced."""


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self._connection = connection
        self._pending: list = []
        self.closed = False

    def execute(self, sql, params=None):
        self._connection.statements.append((sql, params))
        boom = self._connection.raise_on.get(sql)
        if boom is not None:
            raise boom
        if sql == db_provider.Q_SHOW_TRANSACTION_READ_ONLY:
            self._pending = [(self._connection.read_only_setting,)]
        elif sql == db_provider.Q_RECORD_PAGE:
            limit = int(params[0])
            self._pending = list(self._connection.rows[:limit])
        else:
            self._pending = []

    def fetchone(self):
        self._connection.fetch_calls += 1
        if (
            self._connection.fetch_raises_after is not None
            and self._connection.fetch_calls > self._connection.fetch_raises_after
        ):
            raise QueryCanceledError("canceling statement due to statement timeout")
        if not self._pending:
            return None
        return self._pending.pop(0)

    def close(self):
        self.closed = True


class FakeConnection:
    """A connection double that records everything the provider does to it."""

    def __init__(
        self,
        rows=(),
        *,
        read_only_setting="on",
        autocommit=False,
        has_set_session=True,
        set_session_raises=False,
        raise_on=None,
        fetch_raises_after=None,
    ) -> None:
        self.rows = list(rows)
        self.read_only_setting = read_only_setting
        self.autocommit = autocommit
        self.raise_on = dict(raise_on or {})
        self.fetch_raises_after = fetch_raises_after
        self._set_session_raises = set_session_raises

        self.statements: list = []
        self.set_session_calls: list = []
        self.cursors: list[FakeCursor] = []
        self.rolled_back = 0
        self.close_calls = 0
        self.fetch_calls = 0

        if not has_set_session:
            # Instance attribute shadows the method, and `callable(None)` is
            # False, so the provider takes its "driver cannot do this" branch.
            self.set_session = None

    def cursor(self):
        cursor = FakeCursor(self)
        self.cursors.append(cursor)
        return cursor

    def set_session(self, readonly=None, **kwargs):
        self.set_session_calls.append({"readonly": readonly, **kwargs})
        if self._set_session_raises:
            raise RuntimeError("driver refused set_session")

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.close_calls += 1

    # -- helpers for assertions -------------------------------------------

    @property
    def executed(self) -> list:
        return [sql for sql, _ in self.statements]


def make_provider(connection, **kwargs):
    return DatastoreRecordProvider(ENV, connect=lambda env: connection, **kwargs)


@pytest.fixture(scope="module")
def sample_records() -> list[dict]:
    """Two real, valid official records used as row payloads.

    Drawn from the vendored PUBLIC upstream examples, so the fixture itself
    discloses nothing -- but they exercise the same parse and validate path a
    datastore row would.
    """
    from isaac_api.verification import load_public_corpus

    return [json.loads(json.dumps(r)) for r in load_public_corpus(ROOT)[:2]]


def rows_for(records, *, pad=True):
    """``(record_id, data)`` rows. CHAR(26) is blank-padded by Postgres."""
    return [
        (f"01FAKEROWID{index:015d}" + ("    " if pad else ""), json.dumps(record))
        for index, record in enumerate(records)
    ]


# ---------------------------------------------------------------------------
# The frozen statement set and the query policy
# ---------------------------------------------------------------------------


def test_the_frozen_set_is_exactly_five_literal_statements():
    """Enumerated here so widening it is a visible diff in a test, not only in
    the module that widened it."""
    assert FROZEN_STATEMENTS == (
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = '15000ms'",
        "SET LOCAL lock_timeout = '3000ms'",
        "SHOW transaction_read_only",
        "SELECT record_id, data FROM records ORDER BY record_id LIMIT %s",
    )


def test_only_the_limit_ever_varies_and_it_is_a_bound_parameter():
    """No template, no format, no f-string. The one variable is `%s`."""
    source = Path(db_provider.__file__).read_text(encoding="utf-8")
    for statement in FROZEN_STATEMENTS:
        assert "{" not in statement
    assert db_provider.Q_RECORD_PAGE.count("%s") == 1
    # `.format(` on a SQL string is how `db_recon` interpolates a catalog column
    # name; this module discovers nothing, so it must not need it.
    assert ".format(" not in source


@pytest.mark.parametrize(
    "sql, kind",
    [
        ("DELETE FROM records", "dml"),
        ("delete   from records", "dml"),
        ("INSERT INTO records VALUES (1)", "dml"),
        ("UPDATE records SET data = '{}'", "dml"),
        ("MERGE INTO records USING x ON true", "dml"),
        ("TRUNCATE records", "dml"),
        ("COPY records TO STDOUT", "dml"),
        ("CREATE TEMP TABLE t AS SELECT 1", "ddl"),
        ("ALTER TABLE records ADD COLUMN x int", "ddl"),
        ("DROP TABLE records", "ddl"),
        ("GRANT ALL ON records TO PUBLIC", "ddl"),
        ("CALL some_procedure()", "other"),
        ("SELECT nextval('records_seq')", "read"),
    ],
)
def test_a_forbidden_statement_is_counted_and_then_refused(sql, kind):
    """Counted FIRST, refused second.

    A policy that only counted what it allowed would report zero writes in
    exactly the scenario where the number matters, so `dml_statements` is
    incremented before the refusal and stays incremented after it.
    """
    policy = StatementPolicy()
    assert classify_statement(sql) == kind
    with pytest.raises(PolicyViolation):
        policy.check(sql)
    assert policy.counts[kind] == 1
    assert policy.refusals == 1
    assert policy.executed == 0
    assert policy.parameterized_only is False


def test_statement_chaining_is_refused():
    policy = StatementPolicy()
    with pytest.raises(PolicyViolation) as caught:
        policy.check("SHOW transaction_read_only; DROP TABLE records")
    assert "chaining" in str(caught.value)


def test_a_read_that_is_simply_not_in_the_frozen_set_is_refused():
    """The catch-all. A perfectly harmless SELECT is still refused, because the
    policy is an allowlist and not a threat model."""
    policy = StatementPolicy()
    with pytest.raises(PolicyViolation) as caught:
        policy.check("SELECT 1")
    assert "frozen statement set" in str(caught.value)
    assert policy.counts["read"] == 1


def test_parameters_must_be_a_bound_sequence():
    policy = StatementPolicy()
    with pytest.raises(PolicyViolation):
        policy.check(db_provider.Q_RECORD_PAGE, "30")


def test_an_empty_or_non_string_statement_is_refused():
    policy = StatementPolicy()
    for bad in ("", "   ", None, 42):
        with pytest.raises(PolicyViolation):
            policy.check(bad)


def test_the_provider_exposes_no_way_for_a_caller_to_supply_sql():
    """The constraint "callers can never supply SQL, identifiers, pointers,
    paths, modes or schema locations", asserted on the signature itself."""
    import inspect

    params = inspect.signature(DatastoreRecordProvider.__init__).parameters
    assert set(params) == {"self", "env", "connect", "max_records"}
    assert list(inspect.signature(DatastoreRecordProvider.records).parameters) == ["self"]


# ---------------------------------------------------------------------------
# Row handling: padding, and dropping the identifier
# ---------------------------------------------------------------------------


def test_char26_blank_padding_is_stripped():
    assert normalize_identifier("01ABCDEFGHJKMNPQRSTVWXYZ01    ") == (
        "01ABCDEFGHJKMNPQRSTVWXYZ01"
    )
    assert normalize_identifier(None) == ""
    assert normalize_identifier(b"") == ""


def test_parse_row_drops_the_identifier_entirely():
    """The caller must never receive it -- not as a key, not as a value, not
    alongside the body."""
    body = {"isaac_record_version": "1.05", "record_id": "SOMETHING"}
    parsed = parse_row(("01FAKEIDENTIFIER0000000000  ", json.dumps(body)))
    assert parsed == body
    assert "01FAKEIDENTIFIER0000000000" not in json.dumps(parsed)


def test_parse_row_accepts_a_dict_a_string_and_bytes():
    body = {"a": 1}
    assert parse_row(("x", body)) == body
    assert parse_row(("x", json.dumps(body))) == body
    assert parse_row(("x", json.dumps(body).encode("utf-8"))) == body


def test_an_unparseable_row_degrades_the_sample_rather_than_the_report():
    assert parse_row(("x", "not json")) is None
    assert parse_row(("x", None)) is None
    assert parse_row(("x", [1, 2])) is None
    assert parse_row(("x",)) is None
    assert parse_row(None) is None


def test_an_unreadable_row_is_skipped_and_counted(sample_records):
    rows = rows_for(sample_records) + [("01BADROW00000000000000000 ", "{not json")]
    connection = FakeConnection(rows)
    provider = make_provider(connection)
    yielded = list(provider.records())
    assert len(yielded) == 2
    assert provider.rows_unreadable == 1
    assert provider.state == db_provider.STATE_OK


# ---------------------------------------------------------------------------
# Session discipline
# ---------------------------------------------------------------------------


def test_the_session_is_declared_read_only_twice_and_then_verified(sample_records):
    connection = FakeConnection(rows_for(sample_records))
    provider = make_provider(connection)
    list(provider.records())

    assert connection.set_session_calls == [{"readonly": True}]
    assert connection.executed[:4] == [
        db_provider.Q_SET_TRANSACTION_READ_ONLY,
        db_provider.Q_SET_STATEMENT_TIMEOUT,
        db_provider.Q_SET_LOCK_TIMEOUT,
        db_provider.Q_SHOW_TRANSACTION_READ_ONLY,
    ]
    assert provider.read_only_verified is True
    assert provider.state == db_provider.STATE_OK


def test_the_timeouts_are_set_local_so_they_die_with_the_transaction():
    assert db_provider.Q_SET_STATEMENT_TIMEOUT.startswith("SET LOCAL ")
    assert db_provider.Q_SET_LOCK_TIMEOUT.startswith("SET LOCAL ")


@pytest.mark.parametrize("reported", ["off", "", "yes", "1", None])
def test_the_run_refuses_unless_the_SERVER_says_read_only(reported, sample_records):
    """The whole point of the read-back.

    `set_session` can be absent, silently ignored by a proxy, or overridden by a
    pooler. The server's own answer is the only evidence that survives all
    three, so anything other than exactly `on` -- including an answer this code
    does not understand -- refuses BEFORE the record query runs.
    """
    connection = FakeConnection(
        rows_for(sample_records), read_only_setting=reported
    )
    provider = make_provider(connection)
    assert list(provider.records()) == []
    assert provider.state == db_provider.STATE_REFUSED
    assert provider.refusal_gate == "transaction_read_only"
    assert provider.read_only_verified is False
    assert db_provider.Q_RECORD_PAGE not in connection.executed


def test_the_read_back_is_normalized_but_not_guessed(sample_records):
    """Case and surrounding whitespace are NORMALIZED -- that is reading the
    answer, not guessing it. Anything that is not `on` after normalization
    refuses; see the parametrized test above."""
    connection = FakeConnection(rows_for(sample_records), read_only_setting=" ON ")
    provider = make_provider(connection)
    assert len(list(provider.records())) == 2
    assert provider.read_only_verified is True


def test_a_missing_read_only_row_refuses_rather_than_assuming(sample_records):
    connection = FakeConnection(rows_for(sample_records))
    connection.read_only_setting = "on"
    provider = make_provider(connection)
    # Force the read-back to return no row at all.
    original = FakeCursor.fetchone

    def empty_first(self):
        FakeCursor.fetchone = original
        self._connection.fetch_calls += 1
        return None

    FakeCursor.fetchone = empty_first
    try:
        assert list(provider.records()) == []
    finally:
        FakeCursor.fetchone = original
    assert provider.state == db_provider.STATE_REFUSED


def test_an_autocommit_connection_is_refused(sample_records):
    """`SET LOCAL` under autocommit expires immediately and the rollback rolls
    back nothing -- the guarantee would become decorative, which is worse than
    absent."""
    connection = FakeConnection(rows_for(sample_records), autocommit=True)
    provider = make_provider(connection)
    assert list(provider.records()) == []
    assert provider.state == db_provider.STATE_REFUSED
    assert provider.refusal_gate == "autocommit"
    assert connection.close_calls == 1


def test_a_driver_without_set_session_still_verifies_server_side(sample_records):
    connection = FakeConnection(rows_for(sample_records), has_set_session=False)
    provider = make_provider(connection)
    assert len(list(provider.records())) == 2
    assert provider.read_only_verified is True


def test_a_set_session_that_raises_is_survivable(sample_records):
    """Defence in depth #1 failing is not fatal: #2 and #3 still run, and #3 is
    the one that decides."""
    connection = FakeConnection(rows_for(sample_records), set_session_raises=True)
    provider = make_provider(connection)
    assert len(list(provider.records())) == 2
    assert provider.read_only_verified is True


def test_the_environment_gate_refuses_a_database_that_is_not_ours():
    provider = DatastoreRecordProvider(
        {**ENV, "PGDATABASE": "postgres"},
        connect=lambda env: pytest.fail("connected despite a failed env gate"),
    )
    assert list(provider.records()) == []
    assert provider.state == db_provider.STATE_REFUSED
    assert provider.refusal_gate == "pgdatabase_env"
    assert provider.connections_opened == 0


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------


def test_exactly_one_connection_per_run_and_it_is_rolled_back_and_closed(
    sample_records,
):
    """The owner's connection limit is 5. One run must cost one."""
    connection = FakeConnection(rows_for(sample_records))
    provider = make_provider(connection)
    list(provider.records())
    assert provider.connections_opened == 1
    assert connection.rolled_back == 1
    assert connection.close_calls == 1
    assert all(cursor.closed for cursor in connection.cursors)
    assert len(connection.cursors) == 1


def test_the_connection_is_closed_even_when_the_consumer_abandons_the_stream(
    sample_records,
):
    """Now trivially true -- the connection is closed before the first yield --
    but asserted anyway, because it must stay true if draining is ever revisited.
    The undelivered rows are dropped too, rather than living as long as the
    abandoned generator object."""
    connection = FakeConnection(rows_for(sample_records))
    provider = make_provider(connection)
    stream = provider.records()
    next(stream)
    stream.close()
    assert connection.rolled_back == 1
    assert connection.close_calls == 1
    assert provider.rows_remaining == 0
    # An abandoned sweep is NOT `ok`: it did not finish.
    assert provider.state == db_provider.STATE_ERROR
    assert provider.refusal_gate == "abandoned"


def test_an_empty_read_back_row_names_its_gate_instead_of_erroring(sample_records):
    """A `SHOW` returning `()` used to raise `IndexError` into the generic
    handler and be reported as an anonymous `unexpected` error, losing the one
    thing worth knowing: which gate was not satisfied."""
    connection = FakeConnection(rows_for(sample_records))
    original = FakeCursor.fetchone

    def empty_row_first(self):
        FakeCursor.fetchone = original
        self._connection.fetch_calls += 1
        return ()

    provider = make_provider(connection)
    FakeCursor.fetchone = empty_row_first
    try:
        assert list(provider.records()) == []
    finally:
        FakeCursor.fetchone = original

    assert provider.state == db_provider.STATE_REFUSED
    assert provider.refusal_gate == "transaction_read_only"
    assert provider.read_only_verified is False
    assert db_provider.Q_RECORD_PAGE not in connection.executed


def test_a_rollback_that_raises_does_not_prevent_the_close(sample_records):
    connection = FakeConnection(rows_for(sample_records))

    def angry_rollback():
        raise RuntimeError("rollback failed")

    connection.rollback = angry_rollback
    provider = make_provider(connection)
    list(provider.records())
    assert connection.close_calls == 1


def test_a_second_run_resets_the_counters(sample_records):
    """Otherwise `dml_statements` would stop being a measurement of THIS run."""
    connection = FakeConnection(rows_for(sample_records))
    provider = make_provider(connection)
    list(provider.records())
    first = provider.policy.executed
    list(provider.records())
    assert provider.policy.executed == first
    assert provider.records_yielded == 2


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def test_records_arrive_one_at_a_time_and_the_set_is_never_materialized(
    sample_records,
):
    """The claim, at its true strength: this module holds ONE parsed record.

    Measured by `rows_remaining`: the drained page shrinks by exactly one per
    consumed record, so the parsed corpus is never assembled. (It is NOT a claim
    about the raw rows or the driver's client-side buffer; see the module
    docstring, which now says so plainly.)

    The generator is lazy, so NOTHING has run before the first `next()`: no
    connection, no session statement, no read-back. That is itself part of the
    contract -- constructing a provider must not touch the datastore.
    """
    connection = FakeConnection(rows_for(sample_records))
    provider = make_provider(connection)
    stream = provider.records()

    assert connection.statements == []
    assert provider.connections_opened == 0

    next(stream)
    assert provider.records_yielded == 1
    assert provider.rows_remaining == 1
    next(stream)
    assert provider.records_yielded == 2
    assert provider.rows_remaining == 0
    stream.close()
    assert provider.rows_remaining == 0


def test_the_connection_is_closed_before_the_first_record_is_yielded(sample_records):
    """THE fix for the long-transaction defect, asserted where it is visible.

    The consumer runs a full validate + shadow + 755-operator harness between
    records, measured at ~2.56 s each. Yielding from inside the open transaction
    made "one short-lived connection" mean a ~21 minute idle-in-transaction
    session at the row ceiling, against a database whose connection limit is 5 --
    pinning a snapshot and blocking VACUUM throughout.

    Nothing was lost by draining: psycopg2's client-side cursor had already
    buffered every row before the first `fetchone` returned, so holding the
    transaction bought no memory property at all.
    """
    connection = FakeConnection(rows_for(sample_records))
    provider = make_provider(connection)
    stream = provider.records()

    first = next(stream)
    assert first  # a record really was delivered
    assert connection.rolled_back == 1
    assert connection.close_calls == 1
    assert all(cursor.closed for cursor in connection.cursors)
    # ...and every statement, including the whole fetch, is already behind us.
    assert connection.fetch_calls == 1 + len(sample_records) + 1  # read-back, rows, None
    assert set(connection.executed) == set(FROZEN_STATEMENTS)

    # The rest of the sweep proceeds with no connection whatsoever.
    rest = list(stream)
    assert len(rest) == len(sample_records) - 1
    assert connection.close_calls == 1
    assert provider.state == db_provider.STATE_OK


def test_the_drain_is_bounded_even_if_the_server_ignores_the_limit(sample_records):
    """A server returning more rows than `LIMIT` asked for must not be able to
    grow pod memory without bound -- which is the one thing a fetch cap is for."""
    many = [json.loads(json.dumps(sample_records[0])) for _ in range(20)]
    connection = FakeConnection(rows_for(many))
    provider = make_provider(connection, max_records=5)
    # The fake honours LIMIT, so widen its page deliberately to simulate a server
    # that does not.
    connection.rows = rows_for(many)

    class LyingCursor(FakeCursor):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            if sql == db_provider.Q_RECORD_PAGE:
                self._pending = list(self._connection.rows)  # ignores the LIMIT

    connection.cursor = lambda: connection.cursors.append(
        LyingCursor(connection)
    ) or connection.cursors[-1]

    yielded = list(provider.records())
    assert len(yielded) == 5


def test_the_row_cap_is_a_bound_parameter_and_is_clamped(sample_records):
    connection = FakeConnection(rows_for(sample_records))
    provider = make_provider(connection, max_records=10_000_000)
    list(provider.records())
    page = [
        params for sql, params in connection.statements if sql == db_provider.Q_RECORD_PAGE
    ]
    assert page == [(db_provider.MAX_RECORDS_CEILING,)]

    connection = FakeConnection(rows_for(sample_records))
    provider = make_provider(connection, max_records=0)
    list(provider.records())
    page = [
        params for sql, params in connection.statements if sql == db_provider.Q_RECORD_PAGE
    ]
    assert page == [(1,)]


def test_a_dangling_cross_reference_is_neither_followed_nor_reported(sample_records):
    """Records reference rows that may not be in the sample. That is EXPECTED.

    Tolerance is implemented as absence: nothing here reads `links`, so no second
    query is issued and no dangling count exists to leak. The statement count is
    the assertion -- five statements, exactly the frozen set, regardless of what
    the records point at.
    """
    record = json.loads(json.dumps(sample_records[0]))
    record["links"] = [
        {"relation": "derived_from", "target_record_id": "01NOSUCHRECORD000000000000"}
    ]
    connection = FakeConnection(rows_for([record]))
    provider = make_provider(connection)
    yielded = list(provider.records())

    assert len(yielded) == 1
    assert yielded[0]["links"] == record["links"]  # passed through untouched
    assert len(connection.statements) == 5
    assert set(connection.executed) == set(FROZEN_STATEMENTS)
    assert provider.state == db_provider.STATE_OK


# ---------------------------------------------------------------------------
# Failure states
# ---------------------------------------------------------------------------


def test_a_statement_timeout_is_classified_as_a_timeout(sample_records):
    connection = FakeConnection(rows_for(sample_records), fetch_raises_after=1)
    provider = make_provider(connection)
    list(provider.records())
    assert provider.state == db_provider.STATE_TIMEOUT
    assert provider.refusal_gate == "timeout"
    assert connection.rolled_back == 1
    assert connection.close_calls == 1


def test_a_connection_failure_is_unavailable_and_carries_no_driver_text():
    def refuse(env):
        raise RuntimeError("FATAL: password authentication failed for user 'x' at host y")

    provider = DatastoreRecordProvider(ENV, connect=refuse)
    assert list(provider.records()) == []
    assert provider.state == db_provider.STATE_UNAVAILABLE
    assert provider.refusal_gate == "connect"


def test_an_unexpected_error_never_captures_its_message(sample_records):
    connection = FakeConnection(
        rows_for(sample_records),
        raise_on={db_provider.Q_SET_TRANSACTION_READ_ONLY: RuntimeError("secret-value")},
    )
    provider = make_provider(connection)
    assert list(provider.records()) == []
    assert provider.state == db_provider.STATE_ERROR
    assert provider.refusal_gate == "unexpected"
    assert "secret-value" not in json.dumps(
        {"state": provider.state, "gate": provider.refusal_gate}
    )


def test_the_module_imports_cleanly_without_the_driver_and_reports_unavailable():
    """psycopg2 is not installed in this interpreter, which is the point.

    The import is lazy, so this module and its whole test suite load anyway, and
    the real connector reports a safe `unavailable` instead of an ImportError at
    module scope.
    """
    pytest.importorskip  # noqa: B018 - referenced so the intent is explicit
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        pass
    else:  # pragma: no cover - depends on the environment
        pytest.skip("psycopg2 is installed here; the absent-driver path is untestable")

    with pytest.raises(db_provider.ProviderUnavailable) as caught:
        db_provider.connect_psycopg2(ENV)
    assert caught.value.gate == "driver"

    provider = DatastoreRecordProvider(ENV)
    assert list(provider.records()) == []
    assert provider.state == db_provider.STATE_UNAVAILABLE


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


def test_the_statement_counts_are_observations_of_a_real_run(sample_records):
    connection = FakeConnection(rows_for(sample_records))
    provider = make_provider(connection)
    list(provider.records())
    assert provider.dml_statements == 0
    assert provider.ddl_statements == 0
    assert provider.parameterized_only is True
    assert provider.policy.executed == 5
    assert provider.policy.parameterized_executions == 1


def test_parameterized_only_is_false_before_anything_ran():
    """A run that issued no statement has demonstrated nothing. Reporting it as
    "parameterized queries only: verified" would be a claim about an event that
    never happened."""
    assert StatementPolicy().parameterized_only is False
    provider = DatastoreRecordProvider(ENV, connect=lambda env: FakeConnection())
    assert provider.parameterized_only is False


def test_no_identifier_is_retained_anywhere_on_the_provider(sample_records):
    connection = FakeConnection(rows_for(sample_records))
    provider = make_provider(connection)
    list(provider.records())
    state = {
        key: value
        for key, value in vars(provider).items()
        if isinstance(value, (str, int, float, bool, type(None)))
    }
    assert "01FAKEROWID" not in json.dumps(state)
