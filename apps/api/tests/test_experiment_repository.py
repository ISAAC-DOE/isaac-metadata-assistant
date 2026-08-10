"""Create Experiment: the route, the seam, the write path, and the migration.

WHAT IS PROVEN AGAINST A REAL ENGINE, AND WHAT IS NOT — read this before trusting
anything below, because the distinction is the whole reason this docstring exists.

* The FILESYSTEM repository is exercised end to end, through the real route,
  against a real workspace directory. Nothing about it is faked.
* The POSTGRES repository, the write path and the migration runner are exercised
  here against an IN-PROCESS FAKE DRIVER (:class:`FakeConnection`, in the style of
  ``test_db_provider.py``). That proves the SHAPE — one transaction, deterministic
  rollback and close, the statement policy, the isolation refusals, parameterized
  values, idempotence of the runner's bookkeeping. **It does not prove the SQL is
  valid PostgreSQL**, because no PostgreSQL is involved.
* That gap is closed in CI, not here: ``.github/workflows/ci.yml`` runs a
  ``postgres:`` service container, applies the migration twice, diffs
  ``information_schema.tables`` before and after, and proves a stand-in ``records``
  table is untouched. This machine has no PostgreSQL and no Docker, so it cannot.

Everything here is synthetic. No database connection is opened by any test in this
file — the fake driver is a Python object, and ``PGHOST`` is set to a value that is
never dialled.
"""

from __future__ import annotations

import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

import isaac_api.db_migrate as dbm
import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
import isaac_api.workspace as ws
from isaac_api.routes import TUTORIAL_SESSION_HEADER

from conftest import tutorial_client


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def plain(app) -> TestClient:
    return TestClient(app)


def _create(client, **body):
    return client.post("/api/experiments", json=body)


# =============================================================================
# 1. the route: what it accepts, what it refuses, what it creates
# =============================================================================


def test_create_returns_the_new_experiments_detail_bundle(plain):
    r = _create(plain, title="Cu K-edge, run 3")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Cu K-edge, run 3"
    assert ws.is_record_id(body["id"])
    assert body["exported"] is False and body["record_id"] is None
    # The SAME bundle GET returns, so a client can route straight into the record
    # without a second read to discover its shape.
    assert plain.get(f"/api/experiments/{body['id']}").json()["id"] == body["id"]
    assert r.headers["ETag"] == f'"{body["version"]}"'


def test_a_created_experiment_appears_in_the_ordinary_list(plain):
    assert plain.get("/api/experiments").json()["experiments"] == []
    created = _create(plain, title="First").json()
    rows = plain.get("/api/experiments").json()["experiments"]
    assert [row["id"] for row in rows] == [created["id"]]
    # It is not mistaken for a built-in example: `scenario` is derived from the id
    # and a minted ULID is never canonical.
    assert rows[0]["scenario"] is None


def test_the_description_is_optional_and_lands_on_the_source_block(plain):
    plain_created = _create(plain, title="No note").json()
    exp = ws.load_experiment(plain_created["id"])
    assert exp is not None
    assert exp.source["description"] == repo.NEW_EXPERIMENT_SOURCE_DESCRIPTION

    noted = _create(plain, title="Noted", description="  Beamline 4-1, Tuesday  ").json()
    exp = ws.load_experiment(noted["id"])
    assert exp is not None
    # Trimmed, and it replaces the default rather than being appended to it.
    assert exp.source["description"] == "Beamline 4-1, Tuesday"
    assert exp.source["files"] == []


@pytest.mark.parametrize("body", [{}, {"title": ""}, {"title": "   "}, {"title": "\t\n"}])
def test_a_missing_or_blank_title_is_refused_and_creates_nothing(plain, body):
    r = plain.post("/api/experiments", json=body)
    assert r.status_code == 422, r.text
    assert plain.get("/api/experiments").json()["experiments"] == []


def test_a_client_supplied_id_is_REJECTED_not_ignored(plain):
    """The defect the guard docstring warns about, asserted at the contract.

    ``extra="forbid"`` means a caller that names an id gets a 422. Silently
    ignoring it would be almost as bad: the client would believe it had chosen the
    id and would then address the record by the wrong name.
    """
    for extra in ({"id": ws.SEED_READY_ID}, {"record_id": "x"}, {"session_id": "a" * 22}):
        r = plain.post("/api/experiments", json={"title": "t", **extra})
        assert r.status_code == 422, (extra, r.text)
    assert plain.get("/api/experiments").json()["experiments"] == []


def test_a_minted_id_is_never_a_canonical_example_id(plain):
    """Belt and braces over 40 creates: the ULID space and the five fixed ids are
    disjoint by construction, and this says so by measurement rather than by
    argument."""
    minted = {_create(plain, title=f"r{n}").json()["id"] for n in range(40)}
    assert len(minted) == 40, "two creates produced the same id"
    assert minted.isdisjoint(ws.CANONICAL_IDS)


# =============================================================================
# 2. tutorial isolation — the invariant that matters most
# =============================================================================


def test_create_refuses_inside_a_worked_example_session_and_writes_nothing(app, tmp_path):
    session = tutorial_client(app)
    before = sorted(p.name for p in (tmp_path / "ws").rglob("*"))

    r = session.post("/api/experiments", json={"title": "Mine"})
    assert r.status_code == 409, r.text
    payload = r.json()
    assert payload["error"] == "ordinary_scope_required"
    assert payload["header"] == TUTORIAL_SESSION_HEADER

    assert sorted(p.name for p in (tmp_path / "ws").rglob("*")) == before
    # Neither scope gained anything: not the session, not the ordinary workspace.
    assert {e["id"] for e in session.get("/api/experiments").json()["experiments"]} == set(
        ws.CANONICAL_IDS
    )
    assert TestClient(app).get("/api/experiments").json()["experiments"] == []


def test_a_created_experiment_is_invisible_from_a_session_and_the_examples_from_it(app):
    plain = TestClient(app)
    created = _create(plain, title="Ordinary").json()["id"]
    session = tutorial_client(app)

    session_ids = {e["id"] for e in session.get("/api/experiments").json()["experiments"]}
    assert session_ids == set(ws.CANONICAL_IDS)
    assert created not in session_ids
    assert session.get(f"/api/experiments/{created}").status_code == 404

    # ...and the five examples did not appear in the ordinary scope alongside it.
    ordinary_ids = {e["id"] for e in plain.get("/api/experiments").json()["experiments"]}
    assert ordinary_ids == {created}
    assert ordinary_ids.isdisjoint(ws.CANONICAL_IDS)


def test_a_malformed_or_unknown_session_header_is_refused_before_anything_is_created(app):
    """FAIL-CLOSED, and the ORDER is the assertion: scope resolution runs first, so a
    header naming no session can never be silently treated as "no header" and
    create in the ordinary workspace."""
    malformed = TestClient(app, headers={TUTORIAL_SESSION_HEADER: ".."})
    assert malformed.post("/api/experiments", json={"title": "t"}).status_code == 422
    unknown = TestClient(app, headers={TUTORIAL_SESSION_HEADER: "Zz" + "0" * 20})
    assert unknown.post("/api/experiments", json={"title": "t"}).status_code == 404
    assert TestClient(app).get("/api/experiments").json()["experiments"] == []


# =============================================================================
# 3. no scientific guessing
# =============================================================================


def test_the_created_record_invents_no_scientific_value(plain):
    """THE NO-GUESSING ASSERTION, field by field.

    A create form supplies a name. It supplies no evidence, so it may produce no
    evidenced value — not a descriptor, not a series, not a QC verdict, and not a
    single populated draft field.
    """
    created = _create(plain, title="Blank", description="a note").json()
    exp = ws.load_experiment(created["id"])
    assert exp is not None
    draft = exp.draft

    assert draft["fields"] == {}, "a create form supplied a field value"
    assert draft["assets"] == []
    assert draft["implicit"] == []
    assert draft["attribution"] == {"contributors": []}
    # The three blocks that carry scientific VALUES are absent entirely rather than
    # present-and-empty: an empty `qc` block would still be a claim that a QC
    # judgement was made.
    for key in ("qc", "measurement", "descriptors", "block_evidence"):
        assert key not in draft, f"the create path fabricated a {key} block"
    assert created["evidenced_field_count"] == 0

    # The whole serialized record mentions no scientific value the form never saw.
    blob = json.dumps(exp.to_state())
    for needle in ("valid", "compromised", "eV", "Cu", "8979", "XANES", "sha256"):
        # `sha256` and `XANES` appear in the deterministic QUESTION text, which is a
        # question rather than a value — so the check is that no ANSWER carries them.
        assert needle not in json.dumps(draft["fields"]), needle


def test_the_new_draft_is_blocked_and_flows_into_guided_completion(plain):
    created = _create(plain, title="Blank").json()
    assert created["pending_count"] == 3
    assert created["status"] == ws.NEEDS_ATTENTION
    # `draft_ok` IS TRUE, AND THAT IS THE POINT RATHER THAN A SURPRISE — it was
    # asserted False here first, on the assumption that "empty" implies "invalid".
    #
    # `draft_ok` is `validate_draft(draft).ok`, the NO-GUESSING check: it asks
    # whether every non-null value carries evidence, not whether the record is
    # finished. A record with no values guesses nothing, so it passes — and that is
    # exactly the property this feature has to have. What stops it from being
    # exported is `pending_count`, asserted above, and the export gate.
    #
    # Both are asserted together on purpose: "nothing was invented" and "it is not
    # exportable yet" are different claims, and a create path has to satisfy both.
    assert created["draft_ok"] is True
    assert created["exported"] is False

    pending = plain.get(f"/api/experiments/{created['id']}/pending").json()
    assert pending, "the guided completion surface has nothing to ask"
    # Every blocker is a QUESTION, never a pre-filled answer.
    for entry in ws.load_experiment(created["id"]).pending():
        assert entry["question"]
        assert "value" not in entry


def test_the_blank_drafts_meta_is_the_builders_own_stored_rule():
    """``meta`` is an inference by a documented rule, and there is ONE definition of
    that rule. Pinned by identity rather than by a copied literal, so the two can
    never drift into disagreeing about what this build supports."""
    from isaac_records.extract.draft_builder import _META

    assert repo.blank_draft()["meta"] == _META
    # And the rule is what it claims to be: the single supported path.
    assert _META["record_type"] == "evidence"
    assert _META["source_type"] == "facility"


def test_the_blank_drafts_questions_are_worded_exactly_as_the_extractor_words_them():
    """A second wording of the same question is a second product voice, and the one
    that drifts is always the copy nobody re-reads. The two blockers the extractor
    also emits from a real input are compared byte for byte against it."""
    from isaac_records.extract.draft_builder import build_draft

    extracted = build_draft(ws.CSV_PATH, ws.LISTING_PATH)
    by_kind = {p["kind"]: p for p in extracted["pending"]}
    blank = {p["kind"]: p for p in repo.blank_draft()["pending"]}

    assert blank["series"]["question"] == by_kind["series"]["question"]
    assert blank["descriptor"]["question"] == by_kind["descriptor"]["question"]
    assert blank["descriptor"]["evidence"] == by_kind["descriptor"]["evidence"]
    # The series blocker's evidence points at a reduced file. A blank record names
    # no files, so it carries none — an absence with a reason.
    assert blank["series"]["evidence"] == []
    # There are no asset blockers, for the same reason.
    assert "asset" not in blank
    # `qc` is NOT compared: the committed sheet carries a qc_status cell, so the
    # extractor's qc branch is unreachable from this input and there is nothing to
    # compare against. Its wording is asserted directly instead.
    assert blank["qc"]["blocker"] == "qc_status"
    assert blank["qc"]["question"].startswith("What is the QC verdict")


# =============================================================================
# 4. repository selection — environment-driven, and degrading is not silent
# =============================================================================


def _env(**over) -> dict:
    base = {"PGHOST": "db.invalid", "PGDATABASE": dbw.EXPECTED_DATABASE}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def test_no_pghost_selects_the_filesystem_repository():
    env: dict = {}
    assert repo.ordinary_store(env) is None
    assert isinstance(repo.repository(env), repo.FilesystemExperimentRepository)
    assert repo.storage_status(env) == {
        "configured": False,
        "backend": "filesystem",
        "durable": False,
        "state": repo.STORAGE_STATE_EPHEMERAL,
    }


def test_pghost_with_the_expected_database_selects_postgres():
    env = _env()
    assert isinstance(repo.ordinary_store(env), repo.PostgresOrdinaryStore)
    active = repo.repository(env)
    assert isinstance(active, repo.PostgresExperimentRepository)
    assert active.durable is True and active.backend == "postgres"
    assert repo.storage_status(env) == {
        "configured": True,
        "backend": "postgres",
        "durable": True,
        "state": repo.STORAGE_STATE_DURABLE,
    }


def test_a_wrong_pgdatabase_degrades_to_the_filesystem_AND_SAYS_SO():
    """The two booleans exist so this state is DISTINGUISHABLE.

    A database is wired up but its name is not the one the write path requires, so
    the app must not create its tables there. It degrades — and reports
    ``configured: true, durable: false``, which is what lets the UI tell the reader
    their work is not durable instead of promising that it is. Collapsing the two
    into one boolean would hide a misconfiguration behind a false promise.
    """
    env = _env(PGDATABASE="somewhere_else")
    assert repo.ordinary_store(env) is None
    assert isinstance(repo.repository(env), repo.FilesystemExperimentRepository)
    assert repo.storage_status(env) == {
        "configured": True,
        "backend": "filesystem",
        "durable": False,
        # A database is configured and experiments are not going into it. That is
        # the same THING to a reader as a database that stopped answering, even
        # though it is a different CAUSE to an operator, so it carries the same
        # state word — and `backend: "filesystem"` is what distinguishes it, because
        # here the app really has fallen back rather than kept trying.
        "state": repo.STORAGE_STATE_UNAVAILABLE,
    }


def test_health_reports_the_storage_block_without_opening_a_connection(app, monkeypatch):
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)

    def explode(*_a, **_k):  # pragma: no cover - must never be reached
        raise AssertionError("/api/health opened a database connection")

    monkeypatch.setattr(dbw, "connect_psycopg2", explode)
    body = TestClient(app).get("/api/health").json()
    assert body["experiment_storage"] == {
        "configured": True,
        "backend": "postgres",
        "durable": True,
        "state": repo.STORAGE_STATE_DURABLE,
    }
    assert body["status"] == "ok"


# =============================================================================
# 5. the durable store's refusals — impossible, not merely unused
# =============================================================================


def test_a_tutorial_session_record_is_never_persistable():
    """THE SINGLE MOST IMPORTANT INVARIANT IN THIS CHANGE.

    Asserted at the store rather than only at the caller, because "nothing calls it
    with a session" is a fact about today's code and "it refuses a session" is a
    fact about the code. A future caller that wires it wrongly is refused.
    """
    scoped = ws.Experiment(
        id="01ABCDEFGHJKMNPQRSTVWXYZ00",
        title="t",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
        session_id="a" * 22,
    )
    store = repo.PostgresOrdinaryStore(_env())
    with pytest.raises(repo.NotPersistable):
        store.refuse_if_not_persistable(scoped)
    with pytest.raises(repo.NotPersistable):
        store.persist(scoped)


def test_a_canonical_example_id_is_never_persistable():
    """The other half, and it is what keeps the three product strings true: a
    built-in example cannot be made durable even from the ordinary scope, where a
    workspace left by an older build can already be holding one."""
    store = repo.PostgresOrdinaryStore(_env())
    for canonical_id in sorted(ws.CANONICAL_IDS):
        exp = ws.Experiment(
            id=canonical_id,
            title="t",
            created_utc="2026-01-01T00:00:00Z",
            source={},
            draft={},
        )
        with pytest.raises(repo.NotPersistable):
            store.persist(exp)


def test_the_save_hook_is_skipped_for_every_worked_example_session(app, monkeypatch):
    """The FIRST of the three guards, checked where it lives.

    ``_ordinary_store`` returns ``None`` for a session before it consults the
    environment at all, so a session's save can never reach the store even on a
    deployment that has one.
    """
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    assert ws._ordinary_store("a" * 22) is None
    assert isinstance(ws._ordinary_store(None), repo.PostgresOrdinaryStore)


def test_creating_a_session_touches_no_database_even_when_one_is_configured(
    app, monkeypatch
):
    """BEHAVIOURAL, over the real seeding path: materialising the five examples with
    a database configured must open no connection at all."""
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)

    def explode(*_a, **_k):  # pragma: no cover - must never be reached
        raise AssertionError("seeding a worked-example session contacted the database")

    monkeypatch.setattr(dbw, "connect_psycopg2", explode)
    session = tutorial_client(app)
    assert set(session.tutorial_record_ids) == set(ws.CANONICAL_IDS)


# =============================================================================
# 6. the write path — one transaction, deterministic rollback and close
# =============================================================================


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self._connection = connection
        self._pending: list = []
        #: DB-API's "unknown". Set per statement below; only the upsert's value is
        #: ever read by the application.
        self.rowcount = -1
        self.closed = False

    def execute(self, sql, params=None):
        self._connection.statements.append((sql, params))
        boom = self._connection.raise_on.get(sql)
        if boom is not None:
            raise boom
        self.rowcount = -1
        if sql == dbw.Q_CURRENT_DATABASE:
            self._pending = [(self._connection.database,)]
        elif sql == dbm.Q_APPLIED_VERSIONS:
            self._pending = [(v,) for v in sorted(self._connection.applied)]
        elif sql == repo.Q_ALL_EXPERIMENTS:
            self._pending = list(self._connection.rows)
        elif sql == repo.Q_UPSERT_EXPERIMENT:
            # THE FAKE DOES NOT EVALUATE THE PREDICATE, AND MUST NOT PRETEND TO.
            # It reports the server's DECISION — one row returned, or none — so the
            # application's handling of a refusal is exercised. Whether the SQL
            # predicate itself decides correctly is a question about PostgreSQL, and
            # it is answered in `.github/workflows/ci.yml`'s `postgres-migration`
            # job against a real engine, never here. See this file's own docstring.
            self._pending = []
            refused = bool(params) and params[0] in self._connection.refuse_upsert
            self.rowcount = 0 if refused else 1
        elif sql == repo.Q_ONE_EXPERIMENT:
            state = self._connection.stored.get(params[0]) if params else None
            self._pending = [] if state is None else [(json.dumps(state),)]
            self.rowcount = len(self._pending)
        else:
            self._pending = []
            if sql == dbm.Q_RECORD_VERSION and params:
                self._connection.applied.add(params[0])

    def fetchone(self):
        return self._pending.pop(0) if self._pending else None

    def fetchall(self):
        out, self._pending = self._pending, []
        return out

    def close(self):
        self.closed = True


class FakeConnection:
    """A connection double that records everything the write path does to it."""

    def __init__(
        self,
        *,
        database=None,
        rows=(),
        applied=(),
        raise_on=None,
        refuse_upsert=(),
        stored=None,
    ) -> None:
        self.database = dbw.EXPECTED_DATABASE if database is None else database
        self.rows = list(rows)
        self.applied = set(applied)
        self.raise_on = dict(raise_on or {})
        #: Experiment ids whose upsert the server DECIDES to refuse (the
        #: compare-and-swap predicate did not match). Mutable, so one test can let a
        #: create through and then have a later write lose the race.
        self.refuse_upsert = set(refuse_upsert)
        #: ``experiment_id -> state document`` the winner's row holds, read back by
        #: ``Q_ONE_EXPERIMENT`` when an upsert is refused.
        self.stored: dict = dict(stored or {})
        self.autocommit = True  # the write path must set this False itself
        self.statements: list = []
        self.cursors: list[FakeCursor] = []
        self.commits = 0
        self.rollbacks = 0
        self.close_calls = 0

    def cursor(self):
        cur = FakeCursor(self)
        self.cursors.append(cur)
        return cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.close_calls += 1


def _connector(conn: FakeConnection):
    return lambda env: conn


def test_the_transaction_is_explicit_bounded_committed_and_closed():
    conn = FakeConnection()
    with dbw.write_transaction(_env(), connect=_connector(conn)) as (cursor, policy):
        cursor.execute(policy.check("SELECT 1 FROM isaac_experiments"))
    issued = [sql for sql, _ in conn.statements]
    assert conn.autocommit is False, "the write path left the connection on autocommit"
    assert issued[:3] == [
        dbw.Q_SET_STATEMENT_TIMEOUT,
        dbw.Q_SET_LOCK_TIMEOUT,
        dbw.Q_CURRENT_DATABASE,
    ]
    assert conn.commits == 1 and conn.rollbacks == 0
    assert conn.close_calls == 1 and conn.cursors[0].closed


def test_any_exception_rolls_back_and_still_closes():
    conn = FakeConnection()
    with pytest.raises(RuntimeError):
        with dbw.write_transaction(_env(), connect=_connector(conn)):
            raise RuntimeError("boom")
    assert conn.rollbacks == 1 and conn.commits == 0
    assert conn.close_calls == 1 and conn.cursors[0].closed


def test_a_redirected_connection_is_refused_by_the_server_side_check():
    """Gate 2. ``PGDATABASE`` said the right thing and the server said another — the
    transaction is refused and rolled back rather than writing somewhere unexpected."""
    conn = FakeConnection(database="not_the_app_database")
    with pytest.raises(dbw.WriteRefused):
        with dbw.write_transaction(_env(), connect=_connector(conn)):
            pass  # pragma: no cover - the refusal happens before the body
    assert conn.rollbacks == 1 and conn.commits == 0 and conn.close_calls == 1


def test_the_gate_refuses_before_a_connection_is_even_attempted():
    def never(_env):  # pragma: no cover - must never be reached
        raise AssertionError("connected despite a failing PGDATABASE gate")

    with pytest.raises(dbw.WriteRefused):
        with dbw.write_transaction(_env(PGDATABASE="elsewhere"), connect=never):
            pass  # pragma: no cover


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT record_id, data FROM records ORDER BY record_id LIMIT 30",
        "INSERT INTO records (record_id) VALUES (%s)",
        "UPDATE records SET data = %s",
        "DELETE FROM records",
        "SELECT * FROM pg_shadow",
        # ── THE ONE THAT ACTUALLY GOT THROUGH ──────────────────────────────────
        # HOW IT WAS FOUND, stated accurately because the first version of this
        # comment got it wrong and the wrong version is the more alarming one. It
        # was NOT discovered sitting in the committed migration file. It was a
        # deliberate, temporary mutation — negative control (f) of the review of
        # this feature: append a statement touching a table the migration does not
        # own, run the tests, see what fails, revert. The migration file has never
        # contained it and does not now.
        #
        # WHAT THE CONTROL REVEALED. The policy ACCEPTED it. `on` was not an
        # introducer — it had been deliberately left out so `INSERT ... ON CONFLICT`
        # would not be read as naming a table called `conflict` — so every statement
        # that attaches an object to a table named that table after `ON` and was
        # never checked. `CREATE INDEX ... ON records` and `CREATE TRIGGER ... ON
        # records` both passed. Neither reads or writes a row, which is why they
        # look harmless; both take a lock on the production-derived sample and
        # change its schema permanently.
        #
        # The only thing that failed the control was
        # `test_the_committed_migration_loads_and_is_create_only`, and it failed on
        # its `len(statements) == 3` count rather than on the policy — a coincidence
        # that would not have fired had the statement replaced an existing one.
        #
        # Two independent fixes now stop it — `on` is an introducer with `conflict`
        # excepted, and `records` is on an absolute denylist — and this row is why
        # neither may be removed.
        "CREATE INDEX IF NOT EXISTS isaac_probe_idx ON records (record_id)",
        # The same shape, in the other directions it could be written.
        "CREATE INDEX isaac_probe_idx ON public.records (record_id)",
        "ANALYZE records",
        "SELECT count(*) FROM records",
        "CREATE TABLE IF NOT EXISTS isaac_experiments (x text REFERENCES records (record_id))",
        "DROP TABLE isaac_experiments",
        "TRUNCATE isaac_experiments",
        "ALTER TABLE isaac_experiments ADD COLUMN x text",
        "GRANT ALL ON isaac_experiments TO PUBLIC",
        "COPY isaac_experiments FROM '/etc/passwd'",
        "",
    ],
)
def test_the_statement_policy_refuses_anything_outside_this_applications_tables(sql):
    """``records`` holds the production-derived sample. It is not in
    :data:`OWNED_TABLES` and never will be, so the write path cannot name it — not to
    read it, and certainly not to change it."""
    policy = dbw.WriteStatementPolicy()
    with pytest.raises(dbw.WriteRefused):
        policy.check(sql)
    assert policy.seen == [], "a refused statement was recorded as having passed"


@pytest.mark.parametrize(
    "sql",
    [
        dbw.Q_SET_STATEMENT_TIMEOUT,
        dbw.Q_SET_LOCK_TIMEOUT,
        dbw.Q_CURRENT_DATABASE,
        dbm.Q_ENSURE_BOOKKEEPING,
        dbm.Q_APPLIED_VERSIONS,
        dbm.Q_RECORD_VERSION,
        repo.Q_UPSERT_EXPERIMENT,
        repo.Q_ONE_EXPERIMENT,
        repo.Q_ALL_EXPERIMENTS,
    ],
)
def test_every_statement_this_application_actually_issues_passes_the_policy(sql):
    """The other direction, and it is not a formality: an over-broad refusal filter
    that rejected the app's own upsert would be caught here rather than in
    production. ``ON CONFLICT ... DO UPDATE SET`` is the shape that most nearly
    tripped it."""
    assert dbw.WriteStatementPolicy().check(sql) == sql.strip()


def test_records_is_not_and_never_becomes_an_owned_table():
    assert "records" not in dbw.OWNED_TABLES
    # THE MEMBERSHIP IS PINNED EXACTLY, so adding a table is a visible, reviewed
    # edit rather than a side effect. `isaac_runs` was added for migration
    # `0002_runs`; nothing writes it yet (see the inertness test below).
    assert dbw.OWNED_TABLES == {
        "isaac_schema_migrations",
        "isaac_experiments",
        "isaac_runs",
    }
    # ...and it is additionally on the absolute denylist, which does not reason
    # about SQL grammar at all. Both guards are asserted, because the grammar one
    # is the one that was already wrong once.
    assert "records" in dbw._FORBIDDEN_TABLES


def test_no_committed_migration_may_reference_the_production_table():
    """A FILE-LEVEL guard, independent of the statement policy.

    The policy only sees a statement when something executes it. This reads every
    committed migration and rollback off disk, so a statement appended to a file
    fails here even if it is never run — which is how the one that got through was
    actually shaped: it sat in the committed file, and only the runner would have
    tripped over it.
    """
    files = sorted(dbm.MIGRATIONS_DIR.glob("*.sql"))
    assert files, "the migration directory is empty — this guard would pass vacuously"
    for path in files:
        for statement in dbm.split_statements(path.read_text(encoding="utf-8")):
            tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", statement.lower()))
            assert "records" not in tokens, (
                f"{path.name} contains a statement naming the production-derived "
                f"`records` table: {statement[:120]!r}"
            )


# =============================================================================
# 7. persistence and hydration
# =============================================================================


def test_persist_sends_the_state_as_a_parameter_never_as_interpolated_sql():
    conn = FakeConnection()
    exp = ws.Experiment(
        id="01ABCDEFGHJKMNPQRSTVWXYZ00",
        title="Robert'); DROP TABLE records;--",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
    )
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))
    store.persist(exp)

    upserts = [(sql, params) for sql, params in conn.statements if sql == repo.Q_UPSERT_EXPERIMENT]
    assert len(upserts) == 1
    sql, params = upserts[0]
    assert params[0] == exp.id
    assert json.loads(params[1])["title"] == exp.title
    # The value never touches the statement text: the hostile title is in the
    # parameters and only in the parameters.
    assert "DROP TABLE" not in sql
    assert conn.commits == 1


def test_hydrate_restores_a_missing_directory_into_the_ordinary_root_only(app, tmp_path):
    rid = "01ABCDEFGHJKMNPQRSTVWXYZ00"
    state = {
        "id": rid,
        "title": "Restored",
        "created_utc": "2026-01-01T00:00:00Z",
        "source": {"description": "x", "files": []},
        "draft": {"fields": {}, "pending": []},
    }
    conn = FakeConnection(rows=[(rid, json.dumps(state))])
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))

    assert store.hydrate() == 1
    written = tmp_path / "ws" / rid / "experiment.json"
    assert written.is_file()
    assert json.loads(written.read_text())["title"] == "Restored"
    # It wrote into the ordinary root and nowhere near the session namespace.
    assert not (tmp_path / "ws" / ws.TUTORIAL_NAMESPACE).exists()
    # Idempotent: a second call restores nothing, because nothing is missing.
    assert store.hydrate() == 0


@pytest.mark.parametrize(
    "rid,state_id",
    [
        (ws.SEED_READY_ID, ws.SEED_READY_ID),  # a canonical example id
        ("_tutorial", "_tutorial"),  # the session namespace name
        ("../escape", "../escape"),  # a traversal attempt
        ("01ABCDEFGHJKMNPQRSTVWXYZ00", "01ZZZZZZZZZZZZZZZZZZZZZZZZ"),  # id/body mismatch
    ],
)
def test_hydrate_refuses_a_row_it_should_never_have_stored(app, tmp_path, rid, state_id):
    """FAIL-CLOSED on read. Nothing can put these rows there — ``persist`` refuses a
    canonical id, and a non-record id violates the table's own CHECK — so a row of
    this shape means something is wrong. It is skipped rather than written, which is
    the same reading the rest of the workspace layer applies to anything it did not
    create itself."""
    state = {
        "id": state_id,
        "title": "t",
        "created_utc": "2026-01-01T00:00:00Z",
        "source": {},
        "draft": {},
    }
    conn = FakeConnection(rows=[(rid, json.dumps(state))])
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))
    assert store.hydrate() == 0
    root = tmp_path / "ws"
    assert (sorted(p.name for p in root.iterdir()) if root.exists() else []) == []


def test_a_durable_create_writes_to_the_database_before_the_filesystem(
    app, tmp_path, monkeypatch
):
    """The whole path, end to end, with the durable store active.

    The ORDER is asserted because it is the property that makes a failed durable
    write safe: the workspace file is written only after the database accepted it,
    so a reader is never shown a change that did not stick.
    """
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    conn = FakeConnection()
    monkeypatch.setattr(dbw, "connect_psycopg2", _connector(conn))

    created = TestClient(app).post("/api/experiments", json={"title": "Durable"}).json()
    upserts = [p for sql, p in conn.statements if sql == repo.Q_UPSERT_EXPERIMENT]
    assert [p[0] for p in upserts] == [created["id"]]
    assert (tmp_path / "ws" / created["id"] / "experiment.json").is_file()


def test_a_failed_durable_write_does_not_leave_a_file_behind(app, tmp_path, monkeypatch):
    """The write is NOT degraded to the filesystem, and the failure is typed.

    It used to be an unhandled exception, which the route surfaced as a 500. The
    property this test was written for — nothing on disk — is unchanged and still
    asserted; what is added is that the caller now gets a 503 with a typed body
    instead of a stack trace, and that the body names no host, path or credential.
    """
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    conn = FakeConnection(raise_on={repo.Q_UPSERT_EXPERIMENT: RuntimeError("no")})
    monkeypatch.setattr(dbw, "connect_psycopg2", _connector(conn))

    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/experiments", json={"title": "Doomed"}
    )
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "experiment_storage_unavailable"
    assert "db.invalid" not in response.text and "PGHOST" not in response.text

    on_disk = [p.name for p in (tmp_path / "ws").iterdir()] if (tmp_path / "ws").exists() else []
    assert on_disk == [], "a record whose durable write failed was written to disk anyway"
    assert conn.rollbacks == 1
    # ...and the outage is now ON RECORD, which is what `/api/health` reads.
    assert repo.storage_failure() == "RuntimeError"
    assert repo.storage_status(_env())["state"] == repo.STORAGE_STATE_UNAVAILABLE


# =============================================================================
# 8. the migration runner
# =============================================================================


def test_the_committed_migrations_load_and_are_create_only():
    """EVERY committed migration, not just the first.

    The version list is asserted in ORDER, because `load_migrations` sorts by
    filename and the runner applies in that order — `0002_runs` declares a foreign
    key into `isaac_experiments`, so applying it before `0001_experiments` is not a
    stylistic preference, it is a failure.
    """
    migrations = dbm.load_migrations()
    assert [m.version for m in migrations] == ["0001_experiments", "0002_runs"]
    assert [len(m.statements) for m in migrations] == [3, 2]
    # Every statement is CREATE ... IF NOT EXISTS — the second half of the
    # idempotence claim, and the half that survives the bookkeeping table being lost.
    for migration in migrations:
        for statement in migration.statements:
            assert statement.lower().startswith("create "), migration.version
            assert "if not exists" in statement.lower(), migration.version
            # ...and it passes the owned-tables policy, so it can only name our
            # tables.
            dbw.WriteStatementPolicy().check(statement)
            # ADDITIVE MEANS ADDITIVE: no statement may alter, drop or truncate
            # anything — including `isaac_experiments`, which 0002 references but
            # must not modify. The policy above would refuse each of these too;
            # this is asserted separately because a policy is a property of today's
            # keyword list and this is a property of the file.
            tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", statement.lower()))
            assert tokens.isdisjoint({"alter", "drop", "truncate"}), migration.version


def test_the_rollback_file_is_committed_beside_it_and_is_never_loaded():
    """It exists for the operator and for CI to run with psql. The application
    cannot run it: it is excluded from `load_migrations`, and every statement in it
    is a DROP, which the write path's policy refuses outright."""
    rollback = dbm.MIGRATIONS_DIR / "0001_experiments.rollback.sql"
    assert rollback.is_file()
    assert rollback.name not in {m.path.name for m in dbm.load_migrations()}
    body = rollback.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS isaac_experiments;" in body
    assert "DROP TABLE IF EXISTS isaac_schema_migrations;" in body
    # It names only tables 0001 created. `records` must never appear in it.
    # Only the STATEMENTS are checked for it, not the commentary: the file's own
    # header explains at length that `records` is deliberately not named here, and a
    # scan over the prose would flag the explanation as the offence.
    for statement in dbm.split_statements(body):
        assert "records" not in statement.replace("isaac_experiments", "")
    for statement in dbm.split_statements(body):
        with pytest.raises(dbw.WriteRefused):
            dbw.WriteStatementPolicy().check(statement)


def _ddl_for(conn, table: str) -> list[str]:
    prefix = f"create table if not exists {table}"
    return [sql for sql, _ in conn.statements if sql.lower().startswith(prefix)]


def test_migrate_applies_once_and_a_second_run_is_a_no_op():
    conn = FakeConnection()
    assert dbm.migrate(_env(), connect=_connector(conn)) == [
        "0001_experiments",
        "0002_runs",
    ]
    assert conn.applied == {"0001_experiments", "0002_runs"}
    assert len(_ddl_for(conn, "isaac_experiments")) == 1
    assert len(_ddl_for(conn, "isaac_runs")) == 1

    again = FakeConnection(applied={"0001_experiments", "0002_runs"})
    assert dbm.migrate(_env(), connect=_connector(again)) == []
    assert not _ddl_for(again, "isaac_experiments"), "a second run re-issued 0001's DDL"
    assert not _ddl_for(again, "isaac_runs"), "a second run re-issued 0002's DDL"


def test_a_partially_applied_database_applies_only_what_is_missing():
    """THE STATE THE HOSTED DATABASE IS ACTUALLY IN as of 2026-08-09: `0001` applied
    by the operator, `0002` not.

    The bookkeeping check is per-migration rather than "have we ever migrated", so
    the pending one applies and the applied one is not re-issued. Asserted because
    this is the exact transition the `0002` approval packet asks for.
    """
    conn = FakeConnection(applied={"0001_experiments"})
    assert dbm.migrate(_env(), connect=_connector(conn)) == ["0002_runs"]
    assert not _ddl_for(conn, "isaac_experiments"), "an applied migration was re-issued"
    assert len(_ddl_for(conn, "isaac_runs")) == 1


def test_pending_versions_reports_the_plan_without_applying_it():
    conn = FakeConnection()
    assert dbm.pending_versions(_env(), connect=_connector(conn)) == [
        "0001_experiments",
        "0002_runs",
    ]
    assert conn.applied == set(), "a plan-only call recorded a version as applied"


def test_the_bookkeeping_row_is_written_in_the_same_transaction_as_the_ddl():
    """"Applied" and "recorded" cannot disagree, because they commit together.

    ONE TRANSACTION PER MIGRATION, so two committed migrations commit twice — not
    once. That is the contract `db_migrate` states, and asserting the count rather
    than `>= 1` is what would catch a future runner that batched them: a batched
    apply would leave a half-migrated database recorded as fully migrated if the
    second statement failed.
    """
    conn = FakeConnection()
    dbm.migrate(_env(), connect=_connector(conn))
    assert conn.commits == 2, "one transaction per migration was not honoured"
    issued = [sql for sql, _ in conn.statements]
    assert dbm.Q_RECORD_VERSION in issued
    for table in ("isaac_experiments", "isaac_runs"):
        ddl_index = issued.index(_ddl_for(conn, table)[0])
        # The bookkeeping row for this migration is written AFTER its DDL, in the
        # same transaction.
        assert any(
            index > ddl_index
            for index, sql in enumerate(issued)
            if sql == dbm.Q_RECORD_VERSION
        ), table


def test_the_statement_separator_survives_a_semicolon_inside_a_literal():
    """Why the runner splits on ``--;`` and not on ``;``. The committed migration
    contains ``CHECK (experiment_id ~ '^[0-9A-Z]{26}$')``; a naive split would cut a
    statement in half at any semicolon a literal happened to contain."""
    sql = "CREATE TABLE IF NOT EXISTS isaac_experiments (x text CHECK (x ~ 'a;b'))\n--;\nCREATE INDEX IF NOT EXISTS i ON isaac_experiments (x)"
    statements = dbm.split_statements(sql)
    assert len(statements) == 2
    assert "'a;b'" in statements[0]


def test_a_dollar_quoted_body_is_REFUSED_rather_than_silently_mangled():
    """The other half of "why ``--;``": a shape the splitter must not guess at.

    ``split_statements`` drops every line beginning ``--`` and cuts on a line that
    is exactly ``--;``. Inside a ``$$ … $$`` body both rules are wrong — such a
    line is body text, not syntax — so the block would be cut in two, yielding two
    fragments that are each invalid SQL and neither of which is what was written.
    Silently. No committed migration uses one, so the file is refused at load time
    rather than parsed by a splitter that cannot read it.
    """
    body = (
        "DO $$\n"
        "BEGIN\n"
        "  -- a comment inside the body\n"
        "  --;\n"
        "  RAISE NOTICE 'hello';\n"
        "END $$"
    )
    with pytest.raises(dbw.WriteRefused) as excinfo:
        dbm.split_statements(body)
    assert "dollar-quoted" in str(excinfo.value)
    # A tagged dollar quote is the same construct and is refused identically.
    with pytest.raises(dbw.WriteRefused):
        dbm.split_statements("DO $tag$ SELECT 1 $tag$")


def test_the_committed_migrations_regex_literal_is_not_read_as_a_dollar_quote():
    """The guard above must not refuse the migration this repository actually ships.

    ``CHECK (experiment_id ~ '^[0-9A-Z]{26}$')`` contains a ``$``. A guard matching
    a single ``$`` would refuse the one migration in the repository — an
    over-broad refusal that would have been discovered at deploy time rather than
    here. Dollar QUOTING needs a pair.
    """
    migrations = dbm.load_migrations()
    assert [m.version for m in migrations] == ["0001_experiments", "0002_runs"]
    assert [len(m.statements) for m in migrations] == [3, 2]
    # 0002 carries the same `$` inside `CHECK (run_id ~ '^[0-9A-Z]{26}$')`, so the
    # guard has to stay narrow for it too.
    assert "$" in "\n".join(migrations[1].statements)


# =============================================================================
# 8A. migration 0002_runs — the run table, its constraints, and its rollback
# =============================================================================
#
# WHAT THESE PROVE AND WHAT THEY CANNOT. Everything here is a property of the
# committed TEXT and of the runner's behaviour against the in-process fake: the
# statements load, they are create-only, they pass the write policy, the version
# ordering is right, and the rollback is unreachable from the application. NONE OF
# IT PROVES THE SQL IS VALID POSTGRESQL, that the CHECK constraints reject what
# they are meant to reject, or that the foreign key behaves as described — no
# PostgreSQL is involved in this file. That half is `.github/workflows/ci.yml`'s
# `postgres-migration` job, against a real `postgres:18` engine. See this file's
# own module docstring, and §"What remains unproven" in
# `docs/migration-approval-packet-0002.md`.


def _runs_migration() -> dbm.Migration:
    (migration,) = [m for m in dbm.load_migrations() if m.version == "0002_runs"]
    return migration


def _runs_table_statement() -> str:
    return " ".join(_runs_migration().statements[0].split()).lower()


def test_0002_creates_only_the_run_table_and_its_one_index():
    """SCOPE, pinned. Contract §8 D7 names six candidate tables
    (`isaac_runs`, `isaac_experiment_revisions`, `isaac_run_revisions`,
    `isaac_assets`, `isaac_run_assets`, `isaac_submissions`). This migration
    creates exactly ONE of them, deliberately: the other five belong to the slices
    that need them, and an over-stuffed migration is harder to approve and harder
    to roll back.
    """
    statements = _runs_migration().statements
    assert len(statements) == 2
    assert statements[0].lower().startswith("create table if not exists isaac_runs ")
    assert statements[1].lower().startswith(
        "create index if not exists isaac_runs_experiment_order_idx"
    )
    created = set(
        re.findall(r"create table if not exists ([a-z_]+)", "\n".join(statements).lower())
    )
    assert created == {"isaac_runs"}
    for deferred in (
        "isaac_experiment_revisions",
        "isaac_run_revisions",
        "isaac_assets",
        "isaac_run_assets",
        "isaac_submissions",
    ):
        assert deferred not in "\n".join(statements), deferred


def test_0002_declares_the_primary_key_foreign_key_and_named_constraints():
    """Each structural claim the approval packet makes, asserted against the text.

    A text assertion is the right instrument here for the same reason it is at
    `test_the_upsert_predicate_is_a_compare_and_swap_and_not_a_blind_overwrite`:
    the property being protected is "this clause exists at all", and the failure
    being guarded against is a future edit that quietly removes one.
    """
    sql = _runs_table_statement()
    assert "run_id text primary key" in sql
    assert "constraint isaac_runs_id_shape check (run_id ~ '^[0-9a-z]{26}$')" in sql
    assert (
        "constraint isaac_runs_experiment_fk references isaac_experiments (experiment_id)"
        in sql
    )
    assert "experiment_id text not null" in sql
    assert "state jsonb not null" in sql
    assert "generation text not null," in sql
    for column in ("created_utc", "updated_utc"):
        assert f"{column} timestamptz not null default now()" in sql
    for named in (
        "isaac_runs_ordinal_non_negative",
        "isaac_runs_rev_non_negative",
        "isaac_runs_state_is_object",
        "isaac_runs_document_identity",
    ):
        assert f"constraint {named}" in sql, named
    # The two identity keys are tied to the document they project, so a row cannot
    # claim to be a run the document does not describe.
    assert (
        "check (state ->> 'id' = run_id and state ->> 'experiment_id' = experiment_id)"
        in sql
    )


def test_0002_declares_no_on_delete_action_so_the_default_RESTRICT_applies():
    """THE FOREIGN KEY REFUSES A PARENT DELETE, and that is a decision.

    No `ON DELETE` clause means NO ACTION, which for a non-deferrable constraint is
    RESTRICT: deleting an `isaac_experiments` row that still has runs errors rather
    than silently destroying them. `DELETE FROM isaac_experiments` already passes
    the write policy, so `ON DELETE CASCADE` would have put an unbounded
    multi-row destruction one statement away.

    IT IS ALSO UNWRITABLE UNDER THE CURRENT POLICY, and that is asserted here
    rather than left as a claim in a comment: the tokenizer reads the `delete`
    after `on` as naming a table it does not own. So the design argument and the
    mechanical constraint agree — and a future author who reaches for CASCADE will
    fail this test and read why.
    """
    sql = _runs_table_statement()
    assert "on delete" not in sql
    assert "cascade" not in sql
    with pytest.raises(dbw.WriteRefused):
        dbw.WriteStatementPolicy().check(
            "CREATE TABLE IF NOT EXISTS isaac_runs (experiment_id text REFERENCES "
            "isaac_experiments (experiment_id) ON DELETE CASCADE)"
        )


def test_0002_declares_no_uniqueness_on_experiment_and_ordinal():
    """A UNIQUE (experiment_id, ordinal) would refuse data this application already
    produces: every run in a pre-`ordinal` persisted document hydrates with
    `ordinal = 0` (`Run.ordinal` defaults to 0 and `_as_int` returns 0 for a
    missing key), so a single experiment can legitimately hold several runs at
    ordinal 0. `sorted_runs` tie-breaks instead of forbidding, and the schema
    matches it."""
    assert "unique" not in _runs_table_statement()
    exp = ws.Experiment(
        id="01ABCDEFGHJKMNPQRSTVWXYZ00",
        title="t",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
    )
    legacy = [
        ws.Run.from_state({"id": "01AAAAAAAAAAAAAAAAAAAAAAAA", "experiment_id": exp.id}),
        ws.Run.from_state({"id": "01BBBBBBBBBBBBBBBBBBBBBBBB", "experiment_id": exp.id}),
    ]
    assert [r.ordinal for r in legacy] == [0, 0], "the premise of this test moved"


def test_0002_is_inert_for_this_build_no_statement_names_isaac_runs():
    """LEGACY COMPATIBILITY, HALF ONE: the application runs unchanged whether 0002
    is applied or not, because nothing it issues names the table.

    Measured over the complete set of statements this application can issue — the
    module-level constants in the three modules that hold them — rather than
    asserted. `isaac_runs` being in `OWNED_TABLES` grants a capability; it does not
    exercise one.
    """
    issued = [
        dbw.Q_SET_STATEMENT_TIMEOUT,
        dbw.Q_SET_LOCK_TIMEOUT,
        dbw.Q_CURRENT_DATABASE,
        dbm.Q_ENSURE_BOOKKEEPING,
        dbm.Q_APPLIED_VERSIONS,
        dbm.Q_RECORD_VERSION,
        repo.Q_UPSERT_EXPERIMENT,
        repo.Q_ONE_EXPERIMENT,
        repo.Q_ALL_EXPERIMENTS,
    ]
    # The list above must BE the module-level statement set, not a stale copy of it.
    for module in (dbw, dbm, repo):
        for name in dir(module):
            if name.startswith("Q_"):
                assert getattr(module, name) in issued, f"{module.__name__}.{name}"
    for sql in issued:
        assert "isaac_runs" not in sql.lower(), sql


def test_the_app_serves_reads_and_writes_identically_with_0002_pending(app, monkeypatch):
    """LEGACY COMPATIBILITY, HALF TWO, behaviourally: a deployment whose database is
    migrated to 0001 ONLY — which is the hosted deployment as of 2026-08-09 — is
    unaffected by this migration being committed.

    The fake connection answers every statement; what makes this meaningful is the
    assertion that no statement naming `isaac_runs` was ever issued, so the create
    and the read cannot have depended on the new table existing.
    """
    conn = FakeConnection(applied={"0001_experiments"})
    client = _durable_client(app, monkeypatch, conn)
    created = client.post("/api/experiments", json={"title": "0002 pending"})
    assert created.status_code == 201, created.text
    listed = client.get("/api/experiments")
    assert [row["id"] for row in listed.json()["experiments"]] == [created.json()["id"]]
    assert not [sql for sql, _ in conn.statements if "isaac_runs" in sql.lower()]


def test_the_0002_rollback_is_committed_beside_it_and_is_never_loaded():
    """The rollback exists for the operator and for CI, and the application cannot
    reach it: `load_migrations` excludes it by suffix and the write policy refuses
    what it contains.

    ONE DISCLOSURE IS ASSERTED RATHER THAN ONLY WRITTEN DOWN, because the file's
    own header makes the claim and a claim in a comment is what drifts. Unlike
    0001's rollback — every statement of which is a DROP and is therefore
    independently refused — this file also contains a `DELETE` against the
    bookkeeping table, and that statement WOULD pass the policy on its own. The
    file as a whole is still refused, and the loader still never reads it.
    """
    rollback = dbm.MIGRATIONS_DIR / "0002_runs.rollback.sql"
    assert rollback.is_file()
    assert rollback.name not in {m.path.name for m in dbm.load_migrations()}
    body = rollback.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS isaac_runs;" in body
    # It removes its own bookkeeping row, or a re-apply would print "nothing to
    # apply" over a table that no longer exists.
    assert "DELETE FROM isaac_schema_migrations WHERE version = '0002_runs';" in body
    # Both statements are in ONE transaction, so "dropped" and "unrecorded" cannot
    # disagree.
    assert body.count("BEGIN;") == 1 and body.count("COMMIT;") == 1
    # It names ONLY what 0002 created: not `isaac_experiments` (0001's), and never
    # the production-derived table.
    for statement in dbm.split_statements(body):
        tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", statement.lower()))
        assert "records" not in tokens
        assert "isaac_experiments" not in tokens
        with pytest.raises(dbw.WriteRefused):
            dbw.WriteStatementPolicy().check(statement)

    # THE DISCLOSURE, measured: the DELETE line alone is accepted by the policy.
    # This is NOT a property being sought — it is the one recorded in the file's
    # header, pinned so the header cannot quietly become false.
    assert dbw.WriteStatementPolicy().check(
        "DELETE FROM isaac_schema_migrations WHERE version = '0002_runs'"
    )


def test_the_0001_rollback_was_not_edited_by_this_migration():
    """0001 IS APPLIED TO THE HOSTED DATABASE and its rollback was reviewed as it
    stands. 0002 does not touch it — which is precisely why rolling both back has
    an ORDER: `DROP TABLE IF EXISTS isaac_experiments` has no `CASCADE`, so it
    fails while `isaac_runs` still references it. That ordering is documented in
    0002's rollback header and proven against a real engine in CI; here we only
    assert the file was left alone.
    """
    body = (dbm.MIGRATIONS_DIR / "0001_experiments.rollback.sql").read_text(
        encoding="utf-8"
    )
    assert "isaac_runs" not in body
    assert "CASCADE" not in body.upper()


# =============================================================================
# 9. privilege and identity statements — refused, and the docstring says so
# =============================================================================
#
# THIS SECTION EXISTS BECAUSE THE DOCSTRING WAS WRONG. `db_write`'s module
# docstring claimed `CREATE ROLE` / `USER` / `DATABASE` / `EXTENSION` were refused
# "anywhere at all"; measured against the policy, all four were ACCEPTED, as was
# `SET ROLE postgres`. In a module whose entire job is refusing statements, a
# docstring is read as a specification. These pin the specification, so the two
# cannot come apart again silently.


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE ROLE evil LOGIN SUPERUSER",
        "CREATE USER evil PASSWORD 'x'",
        "CREATE DATABASE elsewhere",
        "CREATE EXTENSION dblink",
        "CREATE EXTENSION IF NOT EXISTS postgres_fdw",
        # SET ROLE is included deliberately: it changes the identity subsequent
        # statements execute as, which is the one move that could make every other
        # guard in this module irrelevant.
        "SET ROLE postgres",
        "RESET ROLE",
        "SET SESSION AUTHORIZATION postgres",
        "ALTER ROLE metadata_assistant SUPERUSER",
        "DROP OWNED BY someone",
    ],
)
def test_privilege_and_identity_statements_are_refused_anywhere_at_all(sql):
    policy = dbw.WriteStatementPolicy()
    with pytest.raises(dbw.WriteRefused):
        policy.check(sql)
    assert policy.seen == [], "a refused statement was recorded as having passed"


def test_the_new_privilege_verbs_are_actually_on_the_list():
    """Pinned by name, so a future edit cannot drop one and leave the tests green.

    The parametrized cases above could each still fail for a different reason (an
    unowned table name, say), which would let a removed keyword pass unnoticed.
    """
    for verb in ("role", "user", "database", "extension", "authorization"):
        assert verb in dbw._FORBIDDEN_KEYWORDS, verb


def test_the_near_misses_that_make_this_a_token_match_and_not_a_substring_one():
    """`current_database` and `isaac_schema_migrations` must still pass.

    A substring check for "database" would refuse the write path's own
    `SELECT current_database()` — the server-side gate that catches a redirected
    connection. The refusal filter matches identifier TOKENS, and each of these is
    one token.
    """
    assert dbw.WriteStatementPolicy().check(dbw.Q_CURRENT_DATABASE)
    assert dbw.WriteStatementPolicy().check(dbm.Q_ENSURE_BOOKKEEPING)


def test_the_obfuscated_do_block_residual_is_documented_where_it_lives():
    """A KNOWN, ACCEPTED LIMIT, asserted so it stays documented rather than lurking.

    The policy is a tokenizer, not a SQL parser, so a forbidden verb assembled at
    run time inside a `DO $$ … $$` body is not seen. It is not reachable in this
    application — the only SQL reaching the policy is a module-level constant or a
    committed migration file, both human-reviewed, and `split_statements` refuses
    a dollar-quoted migration outright. This test asserts the limit is WRITTEN
    DOWN, because an undocumented limit is what a later reader mistakes for a
    guarantee. It deliberately does NOT assert the statement is refused: that
    would be asserting behaviour the module does not have.
    """
    doc = dbw.__doc__ or ""
    assert "KNOWN, ACCEPTED LIMITS" in doc
    assert "TOKENIZER, not a SQL parser" in doc
    assert "DO $$" in doc


# =============================================================================
# 10. THE DEPLOYED-POD FAILURE MODE: configured, and the table is not there
# =============================================================================
#
# This is the state the hosted pod is in on the next image roll. `PGHOST` and
# `PGDATABASE` are already set there (`docs/postgres-test-db-guide.md`), so the
# durable backend selects itself, and the migration is deliberately not applied at
# boot — so `isaac_experiments` does not exist and every statement against it
# raises.
#
# Before this was handled, that made THREE previously database-free operations
# return 500: the list (My Experiments rendered "Backend Not Running"), a detail
# read (a clean 404 became a 500), and the create. The same 500s would have
# returned on any transient outage.


class UndefinedTable(Exception):
    """Stands in for ``psycopg2.errors.UndefinedTable``.

    A real driver class is not used, and not because psycopg2 is awkward to import:
    the fix must catch ANY failure from the driver or the server, not a curated
    list of exception types. Using an exception class the application has never
    heard of is what proves that.
    """


def _table_missing_connection():
    """A ``FakeConnection`` on which every statement naming the app's own table raises."""
    return FakeConnection(
        raise_on={
            repo.Q_ALL_EXPERIMENTS: UndefinedTable("relation does not exist"),
            repo.Q_UPSERT_EXPERIMENT: UndefinedTable("relation does not exist"),
        }
    )


@pytest.fixture()
def pod_without_migration(app, monkeypatch):
    """The deployed pod's environment, with the migration not yet applied."""
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    conn = _table_missing_connection()
    monkeypatch.setattr(dbw, "connect_psycopg2", _connector(conn))
    return TestClient(app, raise_server_exceptions=False), conn


def test_the_list_degrades_to_the_filesystem_view_instead_of_500ing(
    pod_without_migration, tmp_path, monkeypatch
):
    """`GET /api/experiments` must stay 200. It is a READ, and it had no database
    dependency at all before durable storage existed."""
    client, _conn = pod_without_migration
    # A record already on disk, written by an earlier pod that had no database.
    monkeypatch.delenv("PGHOST")
    existing = ws.create_experiment(
        title="Written before the roll", source=repo.new_experiment_source(), draft={}
    )
    monkeypatch.setenv("PGHOST", "db.invalid")

    response = client.get("/api/experiments")
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["experiments"]] == [existing.id]


def test_an_unknown_id_is_still_a_404_and_not_a_500(pod_without_migration):
    """A miss stays a miss. "We could not check" and "it is not here" look the same
    to a client holding a stale link, and only one of them is a server error."""
    client, _conn = pod_without_migration
    response = client.get("/api/experiments/01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"


def test_a_known_id_still_loads_from_the_filesystem(pod_without_migration, monkeypatch):
    client, _conn = pod_without_migration
    monkeypatch.delenv("PGHOST")
    existing = ws.create_experiment(
        title="Still readable", source=repo.new_experiment_source(), draft={}
    )
    monkeypatch.setenv("PGHOST", "db.invalid")
    assert client.get(f"/api/experiments/{existing.id}").status_code == 200


def test_create_fails_with_a_typed_503_and_writes_nothing(pod_without_migration, tmp_path):
    """The WRITE does not degrade, and that asymmetry is the design.

    A read that shows less than everything is a degraded read. A write that
    quietly lands somewhere temporary is a broken promise — the reader was told on
    the screen they created this from that their work is kept.
    """
    client, _conn = pod_without_migration
    response = client.post("/api/experiments", json={"title": "Doomed"})
    assert response.status_code == 503, response.text
    assert response.json()["error"] == "experiment_storage_unavailable"
    workspace = tmp_path / "ws"
    on_disk = [p.name for p in workspace.iterdir()] if workspace.exists() else []
    assert on_disk == [], "a create that failed durably still wrote a directory"


def test_health_stops_claiming_durability_once_a_read_has_failed(pod_without_migration):
    """THE DISCLOSURE, and the ordering is asserted because it is the honest limit.

    The FIRST health read says `durable: true`: nothing has been attempted, and
    `/api/health` is the readiness probe so it may not open a connection to find
    out. Once a real read has failed, every subsequent health read reports
    `unavailable` — which is what stops the UI promising durability.
    """
    client, _conn = pod_without_migration
    before = client.get("/api/health").json()["experiment_storage"]
    assert before["durable"] is True and before["state"] == repo.STORAGE_STATE_DURABLE

    assert client.get("/api/experiments").status_code == 200

    after = client.get("/api/health").json()["experiment_storage"]
    assert after["durable"] is False
    assert after["state"] == repo.STORAGE_STATE_UNAVAILABLE
    # The backend is still `postgres`: the app has NOT fallen back, it keeps
    # trying, which is what lets it recover. `durable`/`state` carry "is it
    # working"; `backend` carries "what is selected".
    assert after["backend"] == "postgres"
    assert after["configured"] is True


def test_a_transient_outage_heals_instead_of_marking_the_pod_broken_forever(
    app, tmp_path, monkeypatch
):
    """Clearing the observation matters as much as setting it.

    Without it, one blip would make `/api/health` report `unavailable` for the life
    of the process — a false claim in the other direction, and one nothing would
    ever correct.
    """
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    broken = _table_missing_connection()
    monkeypatch.setattr(dbw, "connect_psycopg2", _connector(broken))
    client = TestClient(app, raise_server_exceptions=False)

    assert client.get("/api/experiments").status_code == 200
    assert client.get("/api/health").json()["experiment_storage"]["durable"] is False

    healthy = FakeConnection()
    monkeypatch.setattr(dbw, "connect_psycopg2", _connector(healthy))
    assert client.post("/api/experiments", json={"title": "After recovery"}).status_code == 201
    storage = client.get("/api/health").json()["experiment_storage"]
    assert storage["durable"] is True
    assert storage["state"] == repo.STORAGE_STATE_DURABLE


def test_a_refusal_is_never_recorded_as_an_outage():
    """`NotPersistable` is a permanent property of the RECORD, not of the deployment.

    Recording it as a storage failure would make `/api/health` report the database
    as unavailable because a tutorial record was correctly refused — sending an
    operator to look at a database that is working perfectly.
    """
    session_record = ws.Experiment(
        id="01SYNTHTESTEXP000000000000",
        title="t",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
        generation="g",
        session_id="a" * 22,
    )
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(FakeConnection()))
    with pytest.raises(repo.NotPersistable):
        store.persist(session_record)
    assert repo.storage_failure() is None
    assert repo.storage_status(_env())["state"] == repo.STORAGE_STATE_DURABLE


def test_the_storage_error_body_names_no_host_path_user_or_driver_message(
    pod_without_migration,
):
    client, _conn = pod_without_migration
    text = client.post("/api/experiments", json={"title": "Doomed"}).text
    for leak in ("db.invalid", "PGHOST", "PGUSER", "PGPASSWORD", "relation does not exist"):
        assert leak not in text, leak


# =============================================================================
# 11. THE DURABLE COMPARE-AND-SWAP (defect C1)
# =============================================================================
#
# WHAT WAS WRONG. The upsert was `ON CONFLICT ... DO UPDATE SET state =
# EXCLUDED.state` with no predicate — last writer wins, unconditionally. The API's
# `If-Match`/`ETag` contract promises a stale write is REFUSED, and that promise
# was kept only by an in-process `threading.Lock` around the read-modify-write. A
# lock in one process says nothing about a second replica, so two writers could
# each pass their own local precondition and the second would silently overwrite
# the first — with both told they had succeeded.
#
# WHAT IS PROVEN HERE, AND WHAT IS NOT. Everything below proves how the
# APPLICATION behaves when the database accepts or refuses: the statement it
# issues, that a refusal is detected rather than mistaken for success, that it is
# raised as its own type, that it is not recorded as an outage, and that it reaches
# the client as the 412 the contract already promises. It does NOT prove that the
# SQL predicate decides correctly — no PostgreSQL is involved in this file, and a
# fake that evaluated the predicate would be testing the fake. That half is the
# `postgres-migration` job's, against a real engine.


def test_the_upsert_predicate_is_a_compare_and_swap_and_not_a_blind_overwrite():
    """The three accept clauses, pinned in the statement text.

    A text assertion is a weak instrument and it is the right one HERE: the
    property is "the predicate exists at all", and the defect being closed is
    precisely a predicate that was missing. A future edit that reverts to a bare
    `DO UPDATE SET` fails this, wherever else it might still pass.
    """
    sql = repo.Q_UPSERT_EXPERIMENT
    normalized = " ".join(sql.split()).lower()
    assert "on conflict (experiment_id) do update" in normalized
    # 1. a fresh generation is a new object, not a stale write
    assert (
        "coalesce(isaac_experiments.state ->> 'generation', '') "
        "<> coalesce(excluded.state ->> 'generation', '')" in normalized
    )
    # 2. otherwise the incoming rev must be STRICTLY ahead
    assert (
        "coalesce((isaac_experiments.state ->> 'rev')::bigint, 0) "
        "< coalesce((excluded.state ->> 'rev')::bigint, 0)" in normalized
    )
    # 3. ...or the document is identical, which is a no-op in every field
    assert "isaac_experiments.state = excluded.state" in normalized
    # and the refusal must be DETECTABLE: a conflict action whose WHERE is false
    # updates nothing and raises nothing.
    assert normalized.endswith("returning experiment_id")


def test_the_compare_and_swap_statement_passes_the_write_policy():
    """Acceptance criterion 6, asserted by calling the policy rather than reading it.

    The predicate had to be written AROUND the policy, and the constraint is not
    obvious: `IS DISTINCT FROM` would read better than the `COALESCE(...) <>
    COALESCE(...)` that is there, and it is refused, because `from` is a table
    introducer and the tokenizer reads the following `COALESCE` as a table this
    application does not own. Both halves are asserted so a future "tidy-up" that
    reintroduces it fails here rather than in the deployed pod.
    """
    policy = dbw.WriteStatementPolicy()
    assert policy.check(repo.Q_UPSERT_EXPERIMENT) == repo.Q_UPSERT_EXPERIMENT
    assert policy.seen == [repo.Q_UPSERT_EXPERIMENT]
    # It names only this application's own table, and no forbidden verb.
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", repo.Q_UPSERT_EXPERIMENT.lower()))
    assert "isaac_experiments" in tokens
    assert "records" not in tokens
    assert tokens.isdisjoint(set(dbw._FORBIDDEN_KEYWORDS))
    # The read-back of the winner's row is subject to the same policy.
    assert dbw.WriteStatementPolicy().check(repo.Q_ONE_EXPERIMENT)
    # ...and the shape that would have read better is genuinely refused.
    with pytest.raises(dbw.WriteRefused):
        dbw.WriteStatementPolicy().check(
            "INSERT INTO isaac_experiments (experiment_id) VALUES (%s) ON CONFLICT "
            "(experiment_id) DO UPDATE SET state = EXCLUDED.state WHERE "
            "isaac_experiments.state IS DISTINCT FROM EXCLUDED.state"
        )


def _ordinary(rid="01ABCDEFGHJKMNPQRSTVWXYZ00", rev=3, generation="g0"):
    return ws.Experiment(
        id=rid,
        title="Racing",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
        rev=rev,
        generation=generation,
    )


def test_a_refused_write_raises_a_conflict_rather_than_reporting_success():
    """THE DEFECT, AT THE SEAM. A refused upsert used to be indistinguishable from
    an applied one — `execute` returned, nothing raised, and `persist` reported
    success. It now raises its own type."""
    exp = _ordinary()
    conn = FakeConnection(refuse_upsert={exp.id})
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))
    with pytest.raises(repo.DurableWriteConflict):
        store.persist(exp)
    # The statement really was issued — the refusal is the SERVER's answer, not an
    # early return that never asked.
    assert [sql for sql, _ in conn.statements].count(repo.Q_UPSERT_EXPERIMENT) == 1


def test_a_conflict_is_neither_an_outage_nor_a_permanent_refusal():
    """Three failure types, three meanings, and this is the one the CLIENT resolves.

    Reusing `StorageUnavailable` would send an operator to look at a database that
    is behaving perfectly and would tell the client to wait rather than to refresh;
    reusing `NotPersistable` would say the record may never be stored at all.
    """
    repo.forget_storage_failure()
    exp = _ordinary()
    conn = FakeConnection(refuse_upsert={exp.id})
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))
    with pytest.raises(repo.DurableWriteConflict) as excinfo:
        store.persist(exp)
    assert not isinstance(excinfo.value, repo.StorageUnavailable)
    assert not isinstance(excinfo.value, repo.NotPersistable)
    # The round trip WORKED. `/api/health` must not start reporting an outage
    # because two writers raced.
    assert repo.storage_failure() is None
    assert repo.storage_status(_env())["state"] == repo.STORAGE_STATE_DURABLE
    # The message names no host, path, credential or driver text.
    for leak in ("db.invalid", "PGHOST", "PGUSER", "PGPASSWORD"):
        assert leak not in str(excinfo.value)


def test_a_conflict_reads_the_winners_document_back_in_the_same_transaction():
    """So the 412 can echo a version that actually exists, rather than the losing
    write's own."""
    exp = _ordinary(rev=3)
    winner = dict(exp.to_state(), rev=9, title="Theirs")
    conn = FakeConnection(refuse_upsert={exp.id}, stored={exp.id: winner})
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))
    with pytest.raises(repo.DurableWriteConflict) as excinfo:
        store.persist(exp)
    current = excinfo.value.current_experiment(exp)
    assert current.rev == 9 and current.title == "Theirs"
    assert current.version_token() == f"{exp.generation}.9"
    # It was read inside the SAME transaction that refused the write — one
    # connection, one commit, no second round trip.
    issued = [sql for sql, _ in conn.statements]
    assert issued.index(repo.Q_ONE_EXPERIMENT) == issued.index(repo.Q_UPSERT_EXPERIMENT) + 1
    assert conn.commits == 1 and conn.rollbacks == 0


@pytest.mark.parametrize(
    "stored",
    [
        None,  # the row could not be read back
        {"id": "01ZZZZZZZZZZZZZZZZZZZZZZZZ", "title": "t", "created_utc": "x"},  # wrong id
    ],
)
def test_an_unreadable_winner_falls_back_instead_of_turning_412_into_500(stored):
    """`current_experiment` is only ever called while rendering an error. A row it
    cannot parse — or one filed under a different id, which describes a different
    record — must not escalate a clean refusal into a server error."""
    exp = _ordinary()
    conflict = repo.DurableWriteConflict(stored)
    assert conflict.current_experiment(exp) is exp


def _durable_client(app, monkeypatch, conn):
    """A client on a deployment whose durable store is ``conn``. No socket is opened."""
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    monkeypatch.setattr(dbw, "connect_psycopg2", _connector(conn))
    return TestClient(app)


def _upsert_count(conn) -> int:
    return [sql for sql, _ in conn.statements].count(repo.Q_UPSERT_EXPERIMENT)


def test_a_byte_stable_no_op_never_reaches_the_database_at_all(app, monkeypatch):
    """ACCEPTANCE CRITERION 4, at its source, and it is why an equal-rev write is
    not simply refused by the predicate.

    `save_versioned` returns False for an identical authoritative state BEFORE it
    bumps `rev` and BEFORE it calls `save()`, so the non-bumping path issues no
    statement at all. A naive `stored.rev < new.rev` predicate would have been
    correct for every write that DOES reach the database — the question was only
    ever what happens to the writes that do not, and the answer is that there are
    none. (The predicate still admits an identical document at an equal rev, for
    the retry-after-a-partial-failure case; that is clause 3, and it is a no-op in
    every field by construction.)

    Asserted against a store that refuses EVERYTHING from that point on: if a
    byte-stable no-op reached the database, this would raise.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Stable"}).json()["id"]
    exp = ws.load_experiment(rid)
    assert exp is not None
    before = (exp.rev, exp.updated_utc)
    upserts_before = _upsert_count(conn)

    conn.refuse_upsert.add(rid)
    assert exp.save_versioned() is False, "an identical re-entry was written"
    assert (exp.rev, exp.updated_utc) == before, "a no-op bumped the version"
    assert _upsert_count(conn) == upserts_before, "the byte-stable no-op issued a statement"


def test_an_identical_re_entry_through_the_api_still_succeeds(app, monkeypatch):
    """ACCEPTANCE CRITERION 7(b), at the contract rather than at the seam.

    A client that re-submits the same answers gets 200, not 412 — the legitimate
    non-bumping save is unaffected by the compare-and-swap. The store is set to
    refuse before the second call, so a 200 here can only mean the write never
    reached it.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Twice"}).json()["id"]

    first = client.post(
        f"/api/experiments/{rid}/answers",
        json=_answers_payload(),
        headers={"If-Match": client.get(f"/api/experiments/{rid}").headers["ETag"]},
    )
    assert first.status_code == 200, first.text
    token = first.json()["version"]

    conn.refuse_upsert.add(rid)
    upserts_before = _upsert_count(conn)
    second = client.post(
        f"/api/experiments/{rid}/answers",
        json=_answers_payload(),
        headers={"If-Match": f'"{token}"'},
    )
    assert second.status_code == 200, second.text
    assert second.json()["version"] == token, "an identical re-entry churned the token"
    assert _upsert_count(conn) == upserts_before


def test_a_refused_write_rolls_the_in_memory_version_bump_back(app, monkeypatch):
    """The instance must not go on claiming a revision that was never stored.

    Without this, the 412 built from it would echo a version no client could ever
    match — and the fallback path in `current_experiment` would report the LOSING
    write's rev as though it were current.
    """
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    conn = FakeConnection()
    monkeypatch.setattr(dbw, "connect_psycopg2", _connector(conn))

    created = TestClient(app).post("/api/experiments", json={"title": "Racing"}).json()
    exp = ws.load_experiment(created["id"])
    assert exp is not None
    before = (exp.rev, exp.updated_utc)

    conn.refuse_upsert.add(exp.id)
    exp.title = "Changed"
    with pytest.raises(repo.DurableWriteConflict):
        exp.save_versioned()
    assert (exp.rev, exp.updated_utc) == before
    # ...and the workspace file was not rewritten either: the durable write goes
    # first, so a refusal means the reader is never shown a change that did not stick.
    assert json.loads(exp.state_path.read_text())["title"] == "Racing"


# --- the contract the client actually sees ------------------------------------


def _answers_payload():
    answers = ws.load_demo_answers()
    return {
        "confirmed_by_user": True,
        "answers": {"series": answers.get("series"), "descriptor": answers.get("descriptor")},
    }


def test_a_lost_race_surfaces_as_the_412_stale_write_the_contract_already_promises(
    app, tmp_path, monkeypatch
):
    """ACCEPTANCE CRITERION 3, end to end through HTTP.

    NO NEW STATUS CODE AND NO NEW BODY. `_check_if_match` and the durable
    compare-and-swap are the same contract enforced at two distances — "does your
    version match the copy this process read" and "…is that copy still current for
    every process". The client's remedy is identical (re-read, re-apply, retry), so
    a second name for it would only be a second name.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    created = client.post("/api/experiments", json={"title": "Racing"}).json()
    rid = created["id"]
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]

    # Another replica got there first: it holds rev 9, and our write is refused.
    winner = dict(ws.load_experiment(rid).to_state(), rev=9)
    conn.refuse_upsert.add(rid)
    conn.stored[rid] = winner

    r = client.post(
        f"/api/experiments/{rid}/answers", json=_answers_payload(), headers={"If-Match": etag}
    )
    assert r.status_code == 412, r.text
    body = r.json()
    assert body["error"] == "stale_write"
    assert body["experiment_id"] == rid
    # The SAME body shape the header-level 412 produces — the fields are asserted
    # by name so a divergence between the two paths is visible.
    assert set(body) == {
        "error",
        "experiment_id",
        "expected_rev",
        "current_rev",
        "expected_version",
        "current_version",
    }
    # It reports the WINNER's version, not the losing write's, and echoes it as the
    # ETag so the client can refresh in one hop.
    assert body["current_rev"] == 9
    assert body["current_version"] == f"{winner['generation']}.9"
    assert r.headers["ETag"] == f'"{winner["generation"]}.9"'
    # `expected_version` echoes the client's own token UNQUOTED, exactly as the
    # header-level 412 does — this path reuses `_stale_write` rather than
    # reimplementing it, and `expected_rev` parses only in that form.
    assert body["expected_version"] == etag.strip('"')
    assert body["expected_rev"] == 0
    # THE CLIENT'S CHANGE WAS NOT APPLIED — the durable write goes before the file
    # write, so nothing of theirs reached either copy. The workspace file IS
    # rewritten, with the WINNER's document: this used to assert `rev == 0`, back
    # when the refusal left the local copy stale and the retry therefore offered the
    # same already-taken rev forever. See the wedge-recovery test below.
    on_disk = json.loads((tmp_path / "ws" / rid / "experiment.json").read_text())
    assert on_disk["rev"] == 9, "the refusal did not adopt the winner locally"
    assert on_disk["draft"] == winner["draft"], "the losing write's draft was applied"


def test_a_lost_race_is_not_a_503_and_does_not_mark_the_deployment_unhealthy(
    app, monkeypatch
):
    """The distinction the whole exception hierarchy exists for, at the HTTP edge.

    503 tells an operator the database is sick and tells the client to wait. Both
    would be false: the database answered, correctly, in the time it took to ask.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Racing"}).json()["id"]
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]
    conn.refuse_upsert.add(rid)
    conn.stored[rid] = dict(ws.load_experiment(rid).to_state(), rev=9)

    r = client.post(
        f"/api/experiments/{rid}/answers", json=_answers_payload(), headers={"If-Match": etag}
    )
    assert r.status_code == 412
    assert r.json()["error"] != "experiment_storage_unavailable"
    storage = client.get("/api/health").json()["experiment_storage"]
    assert storage["durable"] is True and storage["state"] == repo.STORAGE_STATE_DURABLE


# =============================================================================
# 12. THE WEDGE THE COMPARE-AND-SWAP WOULD OTHERWISE CREATE (defect C1, review)
# =============================================================================
#
# WHAT THE INDEPENDENT REVIEW FOUND. A strict compare-and-swap over storage that
# can drift AHEAD of the local workspace file does not merely refuse one write —
# it refuses every write after it, forever, while reads keep serving the stale
# local copy. `save_versioned` offers `max(self.rev, disk_rev) + 1`; once the row
# holds that rev, clause 1 is false (same generation), clause 2 is false (not
# strictly ahead) and clause 3 is false (`updated_utc` differs). The previous
# behaviour — last writer wins — converged, wrongly. This one stops, permanently.
# The trade was silent data loss for a hard stop, and two comments asserted the
# opposite ("the remedy is identical", "a permanent wedge is the worse failure").
#
# TWO ORDINARY WAYS THE ROW GETS AHEAD OF THE FILE, NEITHER NEEDING A SECOND
# REPLICA to be interesting:
#   A. a fault between `save()`'s two writes — the durable write lands, the file
#      write does not;
#   B. a replica that hydrated the record before it moved on — `hydrate` skips any
#      record whose `experiment.json` already exists, so it never refreshes one.
#
# WHAT CLOSES IT. `Experiment._adopt_winner_locally`: the refusal copies the
# winner's document (read back inside the refusing transaction) into the workspace
# file on the way out. The client re-reads, gets the winner, and its next write is
# strictly ahead. Convergence is restored WITHOUT weakening the predicate.
#
# WHAT IS PROVEN HERE, AND WHAT IS NOT — the same split as section 11. The fake
# reports the server's DECISION and does not evaluate the predicate, so these
# tests prove the application recovers: the local copy is refreshed, and the retry
# OFFERS a rev strictly ahead of the winner's. Whether PostgreSQL then admits that
# offer is a question about PostgreSQL, and it is answered end to end in
# `.github/workflows/ci.yml`'s `postgres-migration` job, case 7.


def _offered_revs(conn) -> list[int]:
    """Every `rev` this application OFFERED to the upsert, in order.

    Reads the parameter the statement was executed with, so it measures what was
    sent rather than what the fake decided — the one half of convergence a fake
    cannot fake.
    """
    return [
        json.loads(params[1])["rev"]
        for sql, params in conn.statements
        if sql == repo.Q_UPSERT_EXPERIMENT and params
    ]


def test_a_wedged_record_recovers_instead_of_412ing_forever(app, monkeypatch):
    """THE REVIEW'S CRITICAL FINDING, end to end through HTTP.

    The row is ahead of the file — scenario A above, and indistinguishable from
    scenario B from the application's side. Before the local adoption every retry
    re-offered the rev the row already held and every one was refused.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Wedged"}).json()["id"]
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]

    # The row has moved on to rev 9; the workspace file is still at rev 0.
    winner = dict(ws.load_experiment(rid).to_state(), rev=9, title="The winner")
    conn.refuse_upsert.add(rid)
    conn.stored[rid] = winner
    assert ws.load_experiment(rid).rev == 0, "the file moved; there is no wedge to test"

    first = client.post(
        f"/api/experiments/{rid}/answers", json=_answers_payload(), headers={"If-Match": etag}
    )
    assert first.status_code == 412, first.text

    # THE RECOVERY, HALF ONE: a re-read returns the WINNER, not the same stale copy
    # the retry would otherwise be built from.
    refreshed = client.get(f"/api/experiments/{rid}")
    assert refreshed.json()["rev"] == 9, refreshed.text
    assert refreshed.json()["title"] == "The winner"
    assert refreshed.headers["ETag"] == f'"{winner["generation"]}.9"'

    # THE RECOVERY, HALF TWO: the retry OFFERS a rev strictly ahead of the winner's.
    # Asserted on the statement parameters, so it is a property of what this
    # application SENT and not of what the fake chose to answer.
    conn.refuse_upsert.discard(rid)
    retried = client.post(
        f"/api/experiments/{rid}/answers",
        json=_answers_payload(),
        headers={"If-Match": refreshed.headers["ETag"]},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["rev"] == 10
    assert _offered_revs(conn)[-1] == 10 > winner["rev"], _offered_revs(conn)


def test_without_the_adoption_the_retry_would_re_offer_the_taken_rev(app, monkeypatch):
    """The wedge itself, pinned — so a future edit that drops the adoption fails
    HERE, naming the mechanism, rather than only in the real-engine job.

    With the adoption removed, the second attempt offers the SAME rev as the first,
    which is the rev the row already holds. That is the permanent 412.
    """
    monkeypatch.setattr(ws.Experiment, "_adopt_winner_locally", lambda self, conflict: None)
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Wedged"}).json()["id"]
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]
    conn.refuse_upsert.add(rid)
    conn.stored[rid] = dict(ws.load_experiment(rid).to_state(), rev=9)

    for _ in range(2):
        r = client.post(
            f"/api/experiments/{rid}/answers",
            json=_answers_payload(),
            headers={"If-Match": etag},
        )
        assert r.status_code == 412, r.text
    offered = _offered_revs(conn)[-2:]
    assert offered[0] == offered[1] == 1, offered
    assert ws.load_experiment(rid).rev == 0, "the local copy was refreshed after all"


def test_the_adoption_writes_the_local_file_only_and_does_not_bump_rev(app, monkeypatch):
    """It copies the winner verbatim: no merge, no bump, no second database call.

    The database already holds this document — writing it back would be at best a
    round trip for nothing and at worst a new race.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Adopting"}).json()["id"]
    winner = dict(ws.load_experiment(rid).to_state(), rev=9, title="The winner")
    conn.refuse_upsert.add(rid)
    conn.stored[rid] = winner
    upserts_before = _upsert_count(conn)

    exp = ws.load_experiment(rid)
    exp.title = "Mine"
    with pytest.raises(repo.DurableWriteConflict):
        exp.save_versioned()

    # ONE upsert — the refused one. The adoption issued no statement of its own.
    assert _upsert_count(conn) == upserts_before + 1
    # The file holds the winner byte-for-byte, and `rev` is the winner's, unbumped.
    assert json.loads(exp.state_path.read_text()) == winner
    # ...and the losing in-memory instance was rolled back, not left claiming rev 1.
    assert exp.rev == 0


@pytest.mark.parametrize(
    "make_stored",
    [
        pytest.param(lambda rid: None, id="unreadable"),
        pytest.param(lambda rid: {"id": "01ZZZZZZZZZZZZZZZZZZZZZZZZ", "rev": 9}, id="other-id"),
        # Right id, but not loadable as an Experiment (no `title`, no `created_utc`).
        pytest.param(lambda rid: {"id": rid, "rev": 9}, id="unparseable"),
    ],
)
def test_an_unusable_winner_leaves_the_local_file_alone_and_still_412s(
    app, monkeypatch, make_stored
):
    """A row this application cannot use must not be written into the workspace.

    The record stays wedged in that case — which is the honest outcome, and is why
    `Q_ONE_EXPERIMENT` runs inside the refusing transaction rather than being
    treated as optional. What must NOT happen is a 412 escalating into a 500, a
    directory named one record holding another, or a state file that the next read
    cannot parse — this is the only writer that puts a database row into the
    workspace on an ERROR path.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Unusable"}).json()["id"]
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]
    before = json.loads(ws.load_experiment(rid).state_path.read_text())
    conn.refuse_upsert.add(rid)
    stored = make_stored(rid)
    if stored is not None:
        conn.stored[rid] = stored

    r = client.post(
        f"/api/experiments/{rid}/answers", json=_answers_payload(), headers={"If-Match": etag}
    )
    assert r.status_code == 412, r.text
    assert json.loads(ws.load_experiment(rid).state_path.read_text()) == before


def test_a_failing_adoption_degrades_and_never_turns_the_412_into_a_500(
    app, monkeypatch, caplog
):
    """The adoption is a convenience on an error path; it may not own the outcome —
    AND IT MAY NOT BE SILENT ABOUT FAILING.

    A read-only filesystem, a full disk, a permission change: none of them make a
    concurrency refusal into a server error, and all of them make this record
    behave EXACTLY like the permanent wedge the adoption exists to remove. This
    test used to assert only the 412, so a deployment in which the adoption always
    failed would have looked identical to one in which it always worked — no log
    record, and correctly no `storage_failure` bit, because a refusal is not an
    outage. "Degrading is not silent" is this codebase's own rule, stated at
    `workspace._hydrate_ordinary_scope` and again in `experiment_repository`.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Degrading"}).json()["id"]
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]
    conn.refuse_upsert.add(rid)
    conn.stored[rid] = dict(ws.load_experiment(rid).to_state(), rev=9)

    def _boom(self, conflict):
        raise OSError("read-only file system: /srv/isaac/workspace/experiment.json")

    monkeypatch.setattr(ws.Experiment, "_adopt_winner_locally", _boom)
    with caplog.at_level(logging.WARNING, logger="isaac_api.workspace"):
        r = client.post(
            f"/api/experiments/{rid}/answers",
            json=_answers_payload(),
            headers={"If-Match": etag},
        )
    assert r.status_code == 412, r.text
    assert r.json()["error"] == "stale_write"

    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert len(warnings) == 1, [rec.getMessage() for rec in caplog.records]
    message = warnings[0].getMessage()
    # It NAMES THE RECORD and the failure CLASS, so an operator can tell this
    # record apart from a healthy refusal...
    assert rid in message
    assert "OSError" in message
    # ...and it carries NO PATH. `OSError`'s own message would have leaked the
    # absolute workspace path into the log, which is an exfiltration surface like
    # any other (P30.6); only `type(exc).__name__` is interpolated.
    assert "/srv/isaac" not in message
    assert "read-only file system" not in message
    # A refusal is still not an outage: health must not start reporting one.
    assert client.get("/api/health").json()["experiment_storage"]["durable"] is True


def test_the_adoption_never_moves_the_local_copy_BACKWARDS(app, monkeypatch):
    """REVIEW M-1. The one condition that makes this write safe was the one
    condition not checked.

    A refusal implies `Q_UPSERT_EXPERIMENT`'s clause 2 was false, so the stored rev
    is at least the offered rev and therefore already past the local one — but that
    is an invariant in ANOTHER MODULE, and `_adopt_winner_locally` neither stated
    nor checked it while carefully guarding three lesser conditions. Probed
    directly, a winner at rev 1 really was written over a local file at rev 5.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Ahead"}).json()["id"]

    # Move the LOCAL copy to rev 5 the ordinary way, through the store.
    exp = ws.load_experiment(rid)
    exp.rev = 4
    exp.draft = ws._full_draft()
    assert exp.save_versioned() is True and exp.rev == 5
    local_before = json.loads(exp.state_path.read_text())

    # A stale winner: same record, same generation, an OLDER revision.
    behind = dict(local_before, rev=1, title="an older document")
    exp._adopt_winner_locally(repo.DurableWriteConflict(behind, experiment_id=rid))
    assert json.loads(exp.state_path.read_text()) == local_before, "the copy went backwards"

    # A winner at an EQUAL rev is still adopted — that is the identical-document /
    # same-second case the predicate's clause 3 admits, and it is not a regression.
    equal = dict(local_before, title="an equal-rev document")
    exp._adopt_winner_locally(repo.DurableWriteConflict(equal, experiment_id=rid))
    assert json.loads(exp.state_path.read_text())["title"] == "an equal-rev document"


def test_the_adoption_refuses_a_winner_from_a_different_generation(app, monkeypatch):
    """Two generations cannot be ORDERED — the nonce is random — so "newer" is not
    defined across them, and a refusal implies clause 1 was false, i.e. that they
    matched. A differing generation here means an assumption has already broken;
    the local copy is left alone rather than written on top of.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Reborn"}).json()["id"]
    exp = ws.load_experiment(rid)
    local_before = json.loads(exp.state_path.read_text())

    reborn = dict(local_before, rev=99, generation="ffffffffffffffff", title="recreated")
    exp._adopt_winner_locally(repo.DurableWriteConflict(reborn, experiment_id=rid))
    assert json.loads(exp.state_path.read_text()) == local_before


def test_a_worked_example_record_can_never_be_healed_from_a_row():
    """TUTORIAL ISOLATION, asserted at the one method that writes files from a row.

    A session record cannot reach this method — `_ordinary_store` returns `None`
    for any non-`None` `session_id`, so `persist` is never called and no conflict
    can be raised — but this method WRITES, and "cannot happen" is exactly the
    claim that stops being true when a seam moves. It refuses rather than writing
    into a session directory, and writes nothing on the way to refusing.
    """
    exp = _ordinary()
    exp.session_id = "01SESSION0000000000000000"
    conflict = repo.DurableWriteConflict(dict(exp.to_state(), rev=9))
    with pytest.raises(AssertionError):
        exp._adopt_winner_locally(conflict)
    assert not exp.state_path.exists()


# --- the other two mutation routes, and the create path (review I-5, M-4) -----


def _durable_ordinary(client, conn, title="Racing"):
    """A created, durably-stored ordinary experiment: ``(id, its state document)``."""
    rid = client.post("/api/experiments", json={"title": title}).json()["id"]
    return rid, ws.load_experiment(rid).to_state()


def test_a_lost_race_on_edit_is_the_same_412(app, monkeypatch):
    """`post_edit` shares `_save_versioned` with `post_answers`; sharing a helper is
    not the same as being covered by its test, and this route had no conflict test
    at all."""
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid, _ = _durable_ordinary(client, conn, title="Editing")
    # A completed draft, so there is a real evidenced field to correct.
    exp = ws.load_experiment(rid)
    exp.draft = ws._full_draft()
    assert exp.save_versioned() is True
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]

    winner = dict(ws.load_experiment(rid).to_state(), rev=42)
    conn.refuse_upsert.add(rid)
    conn.stored[rid] = winner

    edited = client.post(
        f"/api/experiments/{rid}/edit",
        # The raw-scan-set asset in the committed synthetic full draft, corrected to
        # a new well-formed sha256 — the same edit `test_edit_field.py` makes.
        json={
            "confirmed_by_user": True,
            "answers": {"ssrl-archive://BL15-2/2099_run_000/raw/": "f" * 64},
        },
        headers={"If-Match": etag},
    )
    assert edited.status_code == 412, edited.text
    assert edited.json()["error"] == "stale_write"
    assert edited.json()["current_rev"] == 42
    assert edited.headers["ETag"] == f'"{winner["generation"]}.42"'
    # ...and the local copy adopted the winner, so the client's retry converges.
    assert ws.load_experiment(rid).rev == 42


def test_a_lost_race_on_export_keeps_the_artifact_pair_and_still_recovers(app, monkeypatch):
    """THE ONE PATH THAT RETURNS 412 AFTER A FILESYSTEM SIDE EFFECT, and it had no
    conflict test at all.

    `post_export` writes the official record and its evidence sidecar BEFORE it
    saves the state, so a refusal here leaves an orphan artifact pair on disk. That
    is the shape the handler's own reconciliation branch already repairs, which is
    why the refusal degrades into a state the app handles rather than a new one —
    and it is why `_save_versioned`'s docstring no longer says "NOTHING WAS
    WRITTEN" unconditionally.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid, _ = _durable_ordinary(client, conn, title="Exporting")

    # Make it genuinely export-ready with the committed synthetic full draft.
    exp = ws.load_experiment(rid)
    exp.draft = ws._full_draft()
    assert exp.save_versioned() is True
    assert client.get(f"/api/experiments/{rid}").json()["status"] == "ready_to_export"
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]

    winner = dict(ws.load_experiment(rid).to_state(), rev=42)
    conn.refuse_upsert.add(rid)
    conn.stored[rid] = winner

    refused = client.post(f"/api/experiments/{rid}/export", headers={"If-Match": etag})
    assert refused.status_code == 412, refused.text
    assert refused.json()["error"] == "stale_write"
    assert refused.json()["current_rev"] == 42

    # THE SIDE EFFECT STANDS: the artifact pair is on disk while the state says the
    # record was never exported. Asserted rather than assumed, because the docstring
    # now claims it.
    reloaded = ws.load_experiment(rid)
    assert reloaded.record_id is None, "the state claims an export that was refused"
    written = sorted(p.name for p in (reloaded.dir / "records").glob("*.json"))
    assert len(written) == 2, written
    assert any(n.endswith(".evidence.json") for n in written), written

    # ...and the retry, from the adopted local copy, completes the export.
    conn.refuse_upsert.discard(rid)
    retried = client.post(
        f"/api/experiments/{rid}/export",
        headers={"If-Match": client.get(f"/api/experiments/{rid}").headers["ETag"]},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["record_id"], retried.text


def test_a_conflict_on_create_is_a_412_and_not_an_unhandled_500(app, monkeypatch):
    """REVIEW M-4. `POST /api/experiments` is the one `persist` call site that does
    not go through `_save_versioned`, and the app registered a handler for
    `StorageUnavailable` only — so a `DurableWriteConflict` escaping there was an
    unhandled 500 for a condition that is not a server error.

    Reaching it needs an id collision with a row carrying the same generation,
    which this application cannot produce; the defect is the unguarded call site,
    not the likelihood.

    THE INJECTED CONFLICT MATCHES THE GENERATION, and that is the point of this
    revision. The fixture used to raise with `generation: "gwin"` against a record
    whose generation was freshly minted — describing a refusal the predicate cannot
    produce, because a differing generation is ADMITTED by clause 1. A test fixture
    that models an impossible server answer proves the handler works on input the
    server never sends.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    captured: dict = {}

    # The fake refuses by id, and a created id is minted INSIDE the request, so it
    # cannot be named in advance. Refused at the seam instead — the store's own
    # method — which is exactly the shape a real collision presents to the route.
    # The winner is built FROM the record being written, so it shares its id and
    # its generation and differs only in `rev`: the one shape a real refusal has.
    def _always_conflict(self, exp):
        captured["winner"] = dict(exp.to_state(), rev=4, title="the row's own record")
        raise repo.DurableWriteConflict(captured["winner"], experiment_id=exp.id)

    monkeypatch.setattr(repo.PostgresOrdinaryStore, "persist", _always_conflict)
    created = client.post("/api/experiments", json={"title": "Colliding"})
    assert created.status_code == 412, created.text
    body = created.json()
    assert body["error"] == "stale_write"
    assert set(body) == {
        "error",
        "experiment_id",
        "expected_rev",
        "current_rev",
        "expected_version",
        "current_version",
    }
    generation = captured["winner"]["generation"]
    # `experiment_id` is a STRING, as it is on every other `stale_write` body. It
    # comes from the exception, which knows it at every raise site, and not from
    # the read-back, which can return nothing.
    assert body["experiment_id"] == captured["winner"]["id"]
    assert isinstance(body["experiment_id"], str)
    assert body["current_rev"] == 4
    assert body["current_version"] == f"{generation}.4"
    # No client validator exists on a create, so the echoed expectation is null
    # rather than invented.
    assert body["expected_rev"] is None and body["expected_version"] is None
    assert created.headers["ETag"] == f'"{generation}.4"'
    # Nothing of the CLIENT's was created: the durable write goes first, so the new
    # record's own state never reached disk. What the directory holds is the
    # WINNER's document — which is correct, and is exactly what `hydrate` would
    # have materialised from the same row on the next read.
    on_disk = ws.workspace_root() / body["experiment_id"] / "experiment.json"
    assert json.loads(on_disk.read_text()) == captured["winner"]


def test_a_refused_write_rolls_back_run_versions_too(app, monkeypatch):
    """A refused durable write must not leave a RUN claiming a rev that is nowhere.

    THE MERGE DEFECT THIS PINS, and it is a merge defect specifically. Two branches
    changed `save_versioned` without being able to see each other: the durable
    compare-and-swap added a rollback of the experiment's `rev`/`updated_utc` on a
    failed save, and the run work added `_bump_changed_runs()` just above it, noting
    that it left bumped run revs ahead of disk "because the durable write path is
    being changed concurrently on another branch". Git merges the two cleanly. The
    RESULT is wrong: the experiment heals and every run stays advanced, which is the
    same defect the rollback was written to close, one level down.

    It is not cosmetic. `_bump_changed_runs` is documented as the ONLY writer of
    `Run.rev`, and that is what makes excluding `rev` from the run signature sound.
    A phantom bump breaks it — the next successful save computes
    `max(run.rev, disk_rev) + 1` from a value that was never persisted, so a single
    refused write permanently offsets that run's version series from disk.
    """
    conn = FakeConnection()
    client = _durable_client(app, monkeypatch, conn)
    rid = client.post("/api/experiments", json={"title": "Runs"}).json()["id"]

    exp = ws.load_experiment(rid)
    run = exp.add_run(label="Cold")
    exp.save_versioned()
    persisted = ws.load_experiment(rid).runs[0]
    persisted_run_rev, persisted_run_stamp = persisted.rev, persisted.updated_utc

    # Refuse the next write, with a winner the loser must not overwrite.
    exp = ws.load_experiment(rid)
    exp.runs[0].label = "Warm"
    conn.refuse_upsert.add(rid)
    conn.stored[rid] = dict(ws.load_experiment(rid).to_state(), rev=9, title="The winner")

    with pytest.raises(repo.DurableWriteConflict):
        exp.save_versioned()

    assert exp.runs[0].rev == persisted_run_rev, (
        "the refused write left a run claiming a rev that was never persisted"
    )
    assert exp.runs[0].updated_utc == persisted_run_stamp
    assert exp.runs[0].id == run.id
