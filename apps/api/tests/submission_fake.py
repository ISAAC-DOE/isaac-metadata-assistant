"""An in-process double for the five submission-lifecycle tables.

WHAT IT IS FOR, AND WHAT IT CANNOT DO — read this before trusting anything it
proves. It is a CONNECTION double in the shape
``test_experiment_repository.FakeConnection`` already established, so the write
path's real transaction machinery (``db_write.write_transaction``: explicit
transaction, statement policy, ``PGDATABASE`` gate, deterministic rollback and
close) is exercised for real and only the SERVER is fake.

IT MODELS FIVE THINGS THE SERVER DOES, and each is here because a defect in the
application would otherwise pass:

  * ``to_regclass`` ANSWERING (never raising) for an absent relation — the whole
    reason a pre-check is possible at all;
  * the two UNIQUE constraints ``ON CONFLICT DO NOTHING`` depends on, so a lost race
    is reachable in a unit test rather than only under real concurrency;
  * the attribution CHECK ``(trust_basis = 'unattributed') = (subject IS NULL)``;
  * the one-run-one-record CHECK ``record_id = unit_id``;
  * rollback restoring the pre-transaction row sets, so "everything or nothing" is
    an OUTCOME this suite can assert rather than a protocol shape.

IT ALSO MODELS THE READ PATH (``isaac_api.revision_history``), against the SAME
rows the write path put in it. A reader with a store of its own could not catch a
listing that disagrees with what a submission actually wrote, which is the main
thing a history read surface can get wrong. Ordering is modelled rather than left
to insertion order, because ``ORDER BY revision_no DESC`` is what puts the newest
revision first and a fake that ignored it would let an oldest-first surface pass.

IT PROVES NOTHING ABOUT POSTGRESQL. Whether the committed SQL is valid, whether the
other CHECK constraints reject what they claim to, whether the foreign keys behave
as described, and whether ``jsonb`` round-trips the documents — none of that is
answerable here, and all of it is answered by ``.github/workflows/ci.yml``'s
``postgres-migration`` job against a real ``postgres:18``. Anywhere the two could
disagree, CI is the authority.
"""

from __future__ import annotations

import json

import isaac_api.db_write as dbw
import isaac_api.revision_history as rhist
import isaac_api.submission_store as sstore

#: What the fake stamps as the server-assigned submission time. A FIXED string
#: rather than a clock: the property under test is that the API reports what the
#: DATABASE stamped, and a moving value would let a test pass while the application
#: substituted its own timestamp.
FAKE_SUBMITTED_UTC = "2026-01-01T00:00:00+00:00"

#: The same device for the ``created_utc DEFAULT now()`` the history tables carry.
#: The application never sends one — the column is absent from every INSERT — so a
#: fake that did not stamp one would let a read surface report ``None`` for a time
#: the server always assigns, and a test asserting on it would be asserting the
#: wrong thing.
FAKE_CREATED_UTC = "2026-01-01T00:00:00+00:00"


class FakeSubmissionCursor:
    def __init__(self, connection: "FakeSubmissionConnection") -> None:
        self._connection = connection
        self._pending: list = []
        self.rowcount = -1
        self.closed = False

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _check_attribution(subject, trust_basis, where: str) -> None:
        """The CHECK both attributed tables carry, enforced here too.

        Modelled rather than left to CI because it guards the one failure this whole
        seam exists to prevent — a durable row carrying a name nothing vouched for —
        and a unit suite that could not catch it would be testing everything except
        the point.
        """
        unattributed = trust_basis == sstore.submissions.TRUST_BASIS_UNATTRIBUTED
        if unattributed != (subject is None):
            raise AssertionError(
                f"{where} violates the attribution CHECK: "
                f"trust_basis={trust_basis!r} subject={subject!r}"
            )

    def execute(self, sql, params=None):
        conn = self._connection
        conn.statements.append((sql, params))
        self.rowcount = -1
        self._pending = []

        if sql == dbw.Q_CURRENT_DATABASE:
            self._pending = [(conn.database,)]
            return
        if sql in (dbw.Q_SET_STATEMENT_TIMEOUT, dbw.Q_SET_LOCK_TIMEOUT):
            return

        # A statement naming a relation this fake does not have must FAIL the way the
        # server fails, or the pre-check that exists to avoid that failure would be
        # untestable. `Q_TABLE_PRESENT` is deliberately exempt: it carries the name as
        # a PARAMETER, and asking whether a relation exists is the one thing that must
        # work when it does not.
        if sql != sstore.Q_TABLE_PRESENT:
            for table in sstore.REQUIRED_TABLES:
                if table in sql and table not in conn.tables:
                    raise UndefinedRelation(f'relation "{table}" does not exist')

        if sql == sstore.Q_TABLE_PRESENT:
            name = params[0]
            self._pending = [(name if name in conn.tables else None,)]
            self.rowcount = 1
            return

        if sql == sstore.Q_LATEST_REVISION:
            rows = [r for r in conn.revisions if r["experiment_id"] == params[0]]
            rows.sort(key=lambda r: r["revision_no"], reverse=True)
            if rows:
                top = rows[0]
                self._pending = [
                    (
                        top["revision_id"],
                        top["revision_no"],
                        top["content_signature"],
                        # psycopg2 returns `jsonb` as a dict; the application accepts
                        # either, and returning the dict is the shape a real driver
                        # produces.
                        json.loads(top["state"]),
                    )
                ]
            self.rowcount = len(self._pending)
            return

        if sql == sstore.Q_SUBMISSION_BY_SIGNATURE:
            self._pending = [
                conn.submission_row(r)
                for r in conn.submissions
                if r["experiment_id"] == params[0] and r["content_signature"] == params[1]
            ]
            self.rowcount = len(self._pending)
            return

        if sql == sstore.Q_SUBMISSION_BY_KEY:
            self._pending = [
                conn.submission_row(r)
                for r in conn.submissions
                if r["experiment_id"] == params[0] and r["idempotency_key"] == params[1]
            ]
            self.rowcount = len(self._pending)
            return

        if sql == sstore.Q_INSERT_REVISION:
            (
                revision_id,
                experiment_id,
                revision_no,
                experiment_rev,
                generation,
                state,
                content_signature,
                reason,
                subject,
                trust_basis,
            ) = params
            self._check_attribution(subject, trust_basis, "isaac_experiment_revisions")
            clash = conn.refuse_revision_insert or any(
                r["revision_id"] == revision_id
                or (r["experiment_id"] == experiment_id and r["revision_no"] == revision_no)
                for r in conn.revisions
            )
            if clash:
                self.rowcount = 0
                return
            conn.revisions.append(
                {
                    "revision_id": revision_id,
                    "experiment_id": experiment_id,
                    "revision_no": revision_no,
                    "experiment_rev": experiment_rev,
                    "generation": generation,
                    "state": state,
                    "content_signature": content_signature,
                    "reason": reason,
                    "subject": subject,
                    "trust_basis": trust_basis,
                    # The column's `DEFAULT now()`, modelled — see FAKE_CREATED_UTC.
                    "created_utc": FAKE_CREATED_UTC,
                }
            )
            self._pending = [(revision_id,)]
            self.rowcount = 1
            return

        if sql == sstore.Q_INSERT_RUN_REVISION:
            keys = ("run_revision_id", "revision_id", "run_id", "ordinal", "state", "rev", "generation")
            row = dict(zip(keys, params))
            row["created_utc"] = FAKE_CREATED_UTC
            conn.run_revisions.append(row)
            self.rowcount = 1
            return

        if sql == sstore.Q_INSERT_REVISION_CHANGE:
            keys = ("change_id", "revision_id", "unit_id", "address", "change_kind")
            row = dict(zip(keys, params))
            row["created_utc"] = FAKE_CREATED_UTC
            conn.changes.append(row)
            self.rowcount = 1
            return

        if sql == sstore.Q_INSERT_SUBMISSION:
            # THE ONE-SHOT RACE HOOK. Fired here — after `record_submission` has
            # re-read the signature and the key inside its own transaction, and
            # before the insert is evaluated — because that is the ONLY window in
            # which a concurrent writer produces `SubmissionRaceLost` rather than
            # `SubmissionAlreadyExists`. See `commit_from_another_writer`.
            if conn.before_submission_insert is not None:
                hook, conn.before_submission_insert = conn.before_submission_insert, None
                hook(conn)
            (
                submission_id,
                experiment_id,
                revision_id,
                content_signature,
                idempotency_key,
                unit_count,
                conflict_summary,
                subject,
                trust_basis,
            ) = params
            self._check_attribution(subject, trust_basis, "isaac_submissions")
            clash = conn.refuse_submission_insert or any(
                r["experiment_id"] == experiment_id
                and (
                    r["content_signature"] == content_signature
                    or (idempotency_key is not None and r["idempotency_key"] == idempotency_key)
                    or r["revision_id"] == revision_id
                )
                for r in conn.submissions
            )
            if clash:
                self.rowcount = 0
                return
            conn.submissions.append(
                {
                    "submission_id": submission_id,
                    "experiment_id": experiment_id,
                    "revision_id": revision_id,
                    "content_signature": content_signature,
                    "idempotency_key": idempotency_key,
                    "unit_count": unit_count,
                    "conflict_summary": conflict_summary,
                    "subject": subject,
                    "trust_basis": trust_basis,
                    "submitted_utc": FAKE_SUBMITTED_UTC,
                }
            )
            self._pending = [(submission_id, FAKE_SUBMITTED_UTC)]
            self.rowcount = 1
            return

        if sql == sstore.Q_INSERT_SUBMISSION_RUN:
            keys = ("submission_run_id", "submission_id", "unit_id", "run_id", "record_id")
            row = dict(zip(keys, params))
            if row["record_id"] != row["unit_id"]:
                raise AssertionError(
                    "isaac_submission_runs violates isaac_submission_runs_one_record_per_unit: "
                    f"record_id={row['record_id']!r} unit_id={row['unit_id']!r}"
                )
            if row["run_id"] is not None and row["run_id"] != row["unit_id"]:
                raise AssertionError(
                    "isaac_submission_runs violates isaac_submission_runs_run_matches_unit"
                )
            conn.submission_runs.append(row)
            self.rowcount = 1
            return

        # --- the READ path (`isaac_api.revision_history`) ---------------------
        #
        # Modelled here rather than in a second double, because the read surface and
        # the write surface have to agree about ONE set of rows: a reader with its
        # own store could never catch a listing that disagrees with what the submit
        # path actually wrote, which is the main thing there is to get wrong.
        #
        # ORDERING IS MODELLED, not left to insertion order. `ORDER BY revision_no
        # DESC` is what makes the newest revision first, and a fake that returned
        # insertion order would let a surface that renders oldest-first pass.

        if sql == rhist.Q_REVISIONS_FOR_EXPERIMENT:
            experiment_id, limit = params
            rows = sorted(
                (r for r in conn.revisions if r["experiment_id"] == experiment_id),
                key=lambda r: r["revision_no"],
                reverse=True,
            )[: int(limit)]
            self._pending = [
                (
                    r["revision_id"],
                    r["revision_no"],
                    r["experiment_rev"],
                    r["generation"],
                    r["content_signature"],
                    r["reason"],
                    r["subject"],
                    r["trust_basis"],
                    r.get("created_utc"),
                )
                for r in rows
            ]
            self.rowcount = len(self._pending)
            return

        if sql == rhist.Q_REVISION_COUNT:
            total = sum(1 for r in conn.revisions if r["experiment_id"] == params[0])
            self._pending = [(total,)]
            self.rowcount = 1
            return

        if sql == rhist.Q_SUBMISSION_COUNT_FOR_EXPERIMENT:
            total = sum(1 for r in conn.submissions if r["experiment_id"] == params[0])
            self._pending = [(total,)]
            self.rowcount = 1
            return

        if sql == rhist.Q_REVISION_BY_NO:
            experiment_id, revision_no = params
            match = [
                r
                for r in conn.revisions
                if r["experiment_id"] == experiment_id
                and int(r["revision_no"]) == int(revision_no)
            ]
            self._pending = [
                (
                    r["revision_id"],
                    r["revision_no"],
                    r["experiment_rev"],
                    r["generation"],
                    r["content_signature"],
                    r["reason"],
                    r["subject"],
                    r["trust_basis"],
                    r.get("created_utc"),
                    # psycopg2 returns `jsonb` as a dict; the write path stores the
                    # serialised text it sent, so the decode happens here — the same
                    # shape a real driver produces.
                    json.loads(r["state"]),
                )
                for r in match
            ]
            self.rowcount = len(self._pending)
            return

        if sql == rhist.Q_SUBMISSION_BY_REVISION:
            self._pending = [
                conn.submission_row(r)
                for r in conn.submissions
                if r["revision_id"] == params[0]
            ]
            self.rowcount = len(self._pending)
            return

        if sql == rhist.Q_CHANGE_COUNTS_FOR_REVISION:
            counts: dict[str, int] = {}
            for r in conn.changes:
                if r["revision_id"] != params[0]:
                    continue
                counts[r["change_kind"]] = counts.get(r["change_kind"], 0) + 1
            self._pending = sorted(counts.items())
            self.rowcount = len(self._pending)
            return

        if sql == rhist.Q_CHANGES_FOR_REVISION:
            rows = sorted(
                (r for r in conn.changes if r["revision_id"] == params[0]),
                key=lambda r: (r["unit_id"], r["address"]),
            )
            self._pending = [
                (r["unit_id"], r["address"], r["change_kind"]) for r in rows
            ]
            self.rowcount = len(self._pending)
            return

        if sql == rhist.Q_RUN_REVISIONS_FOR_REVISION:
            rows = sorted(
                (r for r in conn.run_revisions if r["revision_id"] == params[0]),
                key=lambda r: (int(r["ordinal"]), r["run_id"]),
            )
            self._pending = [
                (
                    r["run_revision_id"],
                    r["run_id"],
                    r["ordinal"],
                    r["rev"],
                    r["generation"],
                    r.get("created_utc"),
                    # `state ->> 'label'` — the SERVER extracts one string, so the
                    # fake does too. A fake that returned the whole document here
                    # would let a route that ships the snapshot to a client pass.
                    json.loads(r["state"]).get("label"),
                )
                for r in rows
            ]
            self.rowcount = len(self._pending)
            return

        if sql == rhist.Q_SUBMISSION_RUNS_FOR_SUBMISSION:
            rows = sorted(
                (r for r in conn.submission_runs if r["submission_id"] == params[0]),
                key=lambda r: r["unit_id"],
            )
            self._pending = [
                (r["unit_id"], r["run_id"], r["record_id"]) for r in rows
            ]
            self.rowcount = len(self._pending)
            return

        raise AssertionError(f"the fake was handed an unmodelled statement: {sql!r}")

    def fetchone(self):
        return self._pending.pop(0) if self._pending else None

    def fetchall(self):
        out, self._pending = self._pending, []
        return out

    def close(self):
        self.closed = True


class UndefinedRelation(Exception):
    """What the fake raises for a statement naming a table it does not have."""


class FakeSubmissionConnection:
    """A connection double holding the five tables as lists of dicts."""

    _TABLES = ("revisions", "run_revisions", "changes", "submissions", "submission_runs")

    def __init__(self, *, tables: bool = True, database: str | None = None) -> None:
        self.tables = set(sstore.REQUIRED_TABLES) if tables else set()
        self.database = dbw.EXPECTED_DATABASE if database is None else database
        self.revisions: list[dict] = []
        self.run_revisions: list[dict] = []
        self.changes: list[dict] = []
        self.submissions: list[dict] = []
        self.submission_runs: list[dict] = []
        #: Force the corresponding insert to report "no row" — what the server does
        #: when a concurrent writer already took the natural key.
        self.refuse_revision_insert = False
        self.refuse_submission_insert = False
        #: A ONE-SHOT callable invoked immediately before the `isaac_submissions`
        #: INSERT is evaluated, so a test can model a concurrent writer committing in
        #: the one window that produces `SubmissionRaceLost` — after this transaction
        #: re-read the signature and the key, and before its own insert lands.
        #: Without it that branch is reachable only through
        #: `refuse_submission_insert`, which always resolves to the GENERIC conflict
        #: and leaves the route's two more interesting post-race outcomes — a replay,
        #: and an `already_submitted` echoing the winner — untested (review item I5).
        self.before_submission_insert = None
        self.statements: list = []
        self.autocommit = True
        self.commits = 0
        self.rollbacks = 0
        self.close_calls = 0
        self._snapshot: dict | None = None

    @staticmethod
    def submission_row(row: dict) -> tuple:
        """One row in ``_SUBMISSION_COLUMNS`` order.

        The order is duplicated from the statement DELIBERATELY and is asserted
        against it by ``test_the_fake_returns_the_submission_columns_in_order``: a
        fake that returned them in a different order would make every field of the
        API's submission object wrong while every test still passed.
        """
        return (
            row["submission_id"],
            row["experiment_id"],
            row["revision_id"],
            row["content_signature"],
            row["idempotency_key"],
            row["unit_count"],
            row["conflict_summary"],
            row["subject"],
            row["trust_basis"],
            row["submitted_utc"],
        )

    def cursor(self):
        # ONE CURSOR PER TRANSACTION, so this is where the before-image is taken —
        # the same device `test_experiment_repository.FakeConnection` uses, and what
        # lets a test assert that a refused submission left NOTHING behind rather
        # than merely that an exception was raised.
        self._snapshot = {name: list(getattr(self, name)) for name in self._TABLES}
        return FakeSubmissionCursor(self)

    def commit(self):
        self.commits += 1
        self._snapshot = None

    def rollback(self):
        self.rollbacks += 1
        if self._snapshot is not None:
            for name, rows in self._snapshot.items():
                setattr(self, name, rows)
            self._snapshot = None

    def close(self):
        self.close_calls += 1

    # -- convenience -----------------------------------------------------------

    def is_empty(self) -> bool:
        return not any(getattr(self, name) for name in self._TABLES)

    def commit_from_another_writer(self, row: dict) -> None:
        """Add a submission row AS IF a different transaction had committed it.

        It is appended to the live list **and to the in-flight before-image**, which
        is the whole point: `rollback` restores the before-image, so a row written
        only to the live list would VANISH when the losing transaction rolls back —
        and the route's post-race handling exists precisely to read a row that
        SURVIVES that rollback, in a fresh transaction of its own.
        """
        self.submissions.append(row)
        if self._snapshot is not None:
            self._snapshot["submissions"].append(dict(row))

    def winner_row(
        self,
        *,
        experiment_id: str,
        content_signature: str,
        submission_id: str = "01WINNERSUBMISSION00000001",
        idempotency_key: str | None = None,
        subject: str = "other.scientist",
        trust_basis: str = "test_fixture",
    ) -> dict:
        """A plausible committed submission row for the concurrent-writer tests."""
        return {
            "submission_id": submission_id,
            "experiment_id": experiment_id,
            "revision_id": "01WINNERREVISION0000000001",
            "content_signature": content_signature,
            "idempotency_key": idempotency_key,
            "unit_count": 1,
            "conflict_summary": "{}",
            "subject": subject,
            "trust_basis": trust_basis,
            "submitted_utc": FAKE_SUBMITTED_UTC,
        }


def fake_env(**overrides) -> dict:
    """The libpq environment the write path gates on. No host is ever contacted."""
    env = {
        "PGHOST": "db.invalid",
        "PGUSER": "metadata_assistant",
        "PGPASSWORD": "not-a-real-password",
        "PGDATABASE": dbw.EXPECTED_DATABASE,
    }
    env.update(overrides)
    return env


def fake_store(conn: FakeSubmissionConnection) -> sstore.PostgresSubmissionStore:
    return sstore.PostgresSubmissionStore(fake_env(), connect=lambda env: conn)


def fake_reader(conn: FakeSubmissionConnection) -> rhist.PostgresRevisionReader:
    """The READ path bound to the same connection double the writes went through.

    Deliberately the SAME ``conn``: a reader over its own store could not catch a
    listing that disagrees with what the submit path wrote, which is the main thing
    a history read surface can get wrong.
    """
    return rhist.PostgresRevisionReader(fake_env(), connect=lambda env: conn)
