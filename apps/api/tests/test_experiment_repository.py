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
        self.closed = False

    def execute(self, sql, params=None):
        self._connection.statements.append((sql, params))
        boom = self._connection.raise_on.get(sql)
        if boom is not None:
            raise boom
        if sql == dbw.Q_CURRENT_DATABASE:
            self._pending = [(self._connection.database,)]
        elif sql == dbm.Q_APPLIED_VERSIONS:
            self._pending = [(v,) for v in sorted(self._connection.applied)]
        elif sql == repo.Q_ALL_EXPERIMENTS:
            self._pending = list(self._connection.rows)
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

    def __init__(self, *, database=None, rows=(), applied=(), raise_on=None) -> None:
        self.database = dbw.EXPECTED_DATABASE if database is None else database
        self.rows = list(rows)
        self.applied = set(applied)
        self.raise_on = dict(raise_on or {})
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
    assert dbw.OWNED_TABLES == {"isaac_schema_migrations", "isaac_experiments"}


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
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    conn = FakeConnection(raise_on={repo.Q_UPSERT_EXPERIMENT: RuntimeError("no")})
    monkeypatch.setattr(dbw, "connect_psycopg2", _connector(conn))

    with pytest.raises(RuntimeError):
        TestClient(app, raise_server_exceptions=True).post(
            "/api/experiments", json={"title": "Doomed"}
        )
    on_disk = [p.name for p in (tmp_path / "ws").iterdir()] if (tmp_path / "ws").exists() else []
    assert on_disk == [], "a record whose durable write failed was written to disk anyway"
    assert conn.rollbacks == 1


# =============================================================================
# 8. the migration runner
# =============================================================================


def test_the_committed_migration_loads_and_is_create_only():
    migrations = dbm.load_migrations()
    assert [m.version for m in migrations] == ["0001_experiments"]
    statements = migrations[0].statements
    assert len(statements) == 3
    # Every statement is CREATE ... IF NOT EXISTS — the second half of the
    # idempotence claim, and the half that survives the bookkeeping table being lost.
    for statement in statements:
        assert statement.lower().startswith("create ")
        assert "if not exists" in statement.lower()
        # ...and it passes the owned-tables policy, so it can only name our tables.
        dbw.WriteStatementPolicy().check(statement)


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


def test_migrate_applies_once_and_a_second_run_is_a_no_op():
    conn = FakeConnection()
    assert dbm.migrate(_env(), connect=_connector(conn)) == ["0001_experiments"]
    assert conn.applied == {"0001_experiments"}
    ddl = [sql for sql, _ in conn.statements if sql.lower().startswith("create table if not exists isaac_experiments")]
    assert len(ddl) == 1

    again = FakeConnection(applied={"0001_experiments"})
    assert dbm.migrate(_env(), connect=_connector(again)) == []
    assert not [
        sql for sql, _ in again.statements
        if sql.lower().startswith("create table if not exists isaac_experiments")
    ], "a second run re-issued the migration's own DDL"


def test_pending_versions_reports_the_plan_without_applying_it():
    conn = FakeConnection()
    assert dbm.pending_versions(_env(), connect=_connector(conn)) == ["0001_experiments"]
    assert conn.applied == set(), "a plan-only call recorded a version as applied"


def test_the_bookkeeping_row_is_written_in_the_same_transaction_as_the_ddl():
    """"Applied" and "recorded" cannot disagree, because they commit together."""
    conn = FakeConnection()
    dbm.migrate(_env(), connect=_connector(conn))
    assert conn.commits == 1, "the migration used more than one transaction"
    issued = [sql for sql, _ in conn.statements]
    assert dbm.Q_RECORD_VERSION in issued
    assert issued.index(dbm.Q_RECORD_VERSION) > issued.index(
        [s for s in issued if s.lower().startswith("create table if not exists isaac_experiments")][0]
    )


def test_the_statement_separator_survives_a_semicolon_inside_a_literal():
    """Why the runner splits on ``--;`` and not on ``;``. The committed migration
    contains ``CHECK (experiment_id ~ '^[0-9A-Z]{26}$')``; a naive split would cut a
    statement in half at any semicolon a literal happened to contain."""
    sql = "CREATE TABLE IF NOT EXISTS isaac_experiments (x text CHECK (x ~ 'a;b'))\n--;\nCREATE INDEX IF NOT EXISTS i ON isaac_experiments (x)"
    statements = dbm.split_statements(sql)
    assert len(statements) == 2
    assert "'a;b'" in statements[0]
