"""ONE HYDRATION PASS AT A TIME, PER PROCESS — and a burst shares it (2026-09-23).

THE SYMPTOM, observed read-only on the hosted deployment (``v0.0.261``, Postgres-backed
durable storage): ``/record/<an id that does not exist>`` rendered "ISAAC Returned an
Error — HTTP 503". The page's own network log showed the record screen's bundle firing
about eight concurrent per-record reads; every one answered ``404 experiment_not_found``
EXCEPT one ``GET /api/experiments/{id}/evidence``, which answered ``503``. The same GET
issued alone answered ``404``.

EVERY one of those reads missed its working copy and ran its OWN ordinary-scope
hydration pass — its own connection and its own ``SELECT`` of every stored experiment,
all at once. A pass that fails for any reason is a ``503`` by design (see
``workspace._hydrate_ordinary_scope_or_raise``; that reasoning is sound and is kept), so
eight uncoordinated passes gave the deployment eight chances to report an outage about a
question seven of them had answered correctly.

WHAT THESE TESTS PIN, and what they deliberately do not claim:

* A burst of reads runs AT MOST TWO passes (one already in flight when a request
  arrived, and one that started after it), and never two at once — so a record whose
  working copy is missing is restored EXACTLY ONCE, however many reads race for it.
* A request that arrives while a pass is running WAITS for it and, when a pass that
  STARTED after it arrived has finished, TAKES THAT PASS'S ANSWER rather than redoing
  the work. An answer from a pass that started BEFORE it arrived is never reused: that
  pass's ``SELECT`` may predate a row another replica committed a moment ago.
* A GENUINE outage is still a ``503`` for every request — it is shared, not retried
  serially behind the lock, which would stack connect timeouts and could exhaust the
  request threads. A healthy store never turns a miss into a ``503``.

THE CAUSE ON HOSTED IS NOT PROVEN BY THESE TESTS, and that is stated rather than implied.
Code reading found NO in-process race that fails a pass against a HEALTHY, UNCAPPED
store: the working-copy write is already atomic with a unique temp name, and two
concurrent restores of one record both succeed with identical bytes. Measured with the
fakes below on the pre-fix code: eight concurrent reads of a nonexistent id against a
healthy store answered eight ``404``s. What DOES reproduce the hosted shape is a server
that refuses connections past a cap (PostgreSQL's ``too_many_connections``, SQLSTATE
``53300``): eight simultaneous passes against a cap of two produced ``503``s beside
``404``s. That cap is a MODEL of one mechanism consistent with the symptom — the 503
body's message would say which (``STORAGE_READ_FAILED_MESSAGE`` for a failed read,
``STORAGE_RESTORE_FAILED_MESSAGE`` for a failed restore) — and the serialization closes
it either way, because a burst now opens at most one connection at a time.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
import isaac_api.workspace as ws
from test_experiment_repository import FakeConnection

RID = "01ABCDEFGHJKMNPQRSTVWXYZ00"
MISSING = "01ABCDEFGHJKMNPQRSTVWXYZ99"
BURST = 8
#: Long enough that every thread of a burst is in flight while the first pass holds
#: its ``SELECT``; the assertions below do not depend on the exact interleaving.
SELECT_DELAY_S = 0.3


def _stored_state(rid: str) -> dict:
    return {
        "id": rid,
        "title": "Restored",
        "created_utc": "2026-01-01T00:00:00Z",
        "source": {"description": "x", "files": []},
        "draft": {"fields": {}, "pending": []},
    }


class _TooManyClients(Exception):
    """What PostgreSQL raises past ``max_connections`` or a role's connection limit."""

    pgcode = "53300"


class _Server:
    """A fake SERVER: a fresh connection per connect, a connection cap, and a slow SELECT.

    ``FakeConnection`` models one connection; a real server hands every request its
    own, which is the property a concurrency test needs. It also counts what matters
    here — how many ``SELECT``s of every experiment were issued, how many connections
    were open at once, and how many were refused.
    """

    def __init__(self, rows, *, cap: int | None = None, refuse_all: bool = False) -> None:
        self.rows = list(rows)
        self.cap = cap
        self.refuse_all = refuse_all
        self._lock = threading.Lock()
        self.open = 0
        self.peak = 0
        self.connects = 0
        self.refused = 0
        self.selects = 0

    def connect(self, env):
        if self.refuse_all:
            # An unreachable server fails SLOWLY — a connect timeout, not an instant
            # refusal — and slow failures are the ones a lock could stack.
            time.sleep(SELECT_DELAY_S)
        with self._lock:
            self.connects += 1
            if self.refuse_all or (self.cap is not None and self.open >= self.cap):
                self.refused += 1
                raise _TooManyClients("sorry, too many clients already")
            self.open += 1
            self.peak = max(self.peak, self.open)
        return _TrackedConnection(self, rows=self.rows)


class _TrackedConnection(FakeConnection):
    def __init__(self, server: _Server, **kw) -> None:
        super().__init__(**kw)
        self._server = server

    def cursor(self):
        cur = super().cursor()
        server = self._server
        inner = cur.execute

        def execute(sql, params=None):
            if sql == repo.Q_ALL_EXPERIMENTS:
                with server._lock:
                    server.selects += 1
                time.sleep(SELECT_DELAY_S)
            return inner(sql, params)

        cur.execute = execute  # type: ignore[method-assign]
        return cur

    def close(self):
        super().close()
        with self._server._lock:
            self._server.open -= 1


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", dbw.EXPECTED_DATABASE)
    from isaac_api.app import create_app

    return create_app()


def _serve(monkeypatch, server: _Server) -> None:
    monkeypatch.setattr(dbw, "connect_psycopg2", server.connect)


def _burst(client: TestClient, paths: list[str]) -> list:
    """Issue every GET at once, from its own thread, and return the responses in order."""
    start = threading.Barrier(len(paths))
    out: list = [None] * len(paths)

    def run(i: int, path: str) -> None:
        start.wait(timeout=10)
        out[i] = client.get(path)

    threads = [threading.Thread(target=run, args=(i, p), name=f"read-{i}") for i, p in enumerate(paths)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive(), f"{t.name} did not finish — the hydration lock deadlocked"
    return out


def _bundle(rid: str) -> list[str]:
    """The record screen's per-record reads, as the hosted network log showed them."""
    base = f"/api/experiments/{rid}"
    return [base, f"{base}/evidence", f"{base}/runs", f"{base}/pending", base, f"{base}/evidence", base, base][:BURST]


def _count_restore_writes(monkeypatch, rid: str) -> list[str]:
    """Every working-copy write under ``rid``'s directory — the restore's only writer."""
    written: list[str] = []
    real = ws.atomic_write_text
    lock = threading.Lock()

    def spy(path, text):
        if f"/{rid}/" in str(path):
            with lock:
                written.append(str(path))
        return real(path, text)

    monkeypatch.setattr(ws, "atomic_write_text", spy)
    return written


def test_a_burst_restores_a_missing_record_exactly_once_and_every_read_succeeds(app, monkeypatch, tmp_path):
    """EIGHT READS OF A RECORD WHOSE WORKING COPY IS MISSING — the first load after a pod
    restart empties the ``emptyDir``. Every read must answer ``200``, and the record
    must be restored ONCE, not once per read.

    POLARITY, measured on the pre-fix code: 8 ``200``s, but EIGHT restore writes, eight
    ``SELECT``s and eight connections open at once — so ``writes == 1`` and
    ``selects <= 2`` both failed there.
    """
    server = _Server([(RID, json.dumps(_stored_state(RID)))])
    _serve(monkeypatch, server)
    writes = _count_restore_writes(monkeypatch, RID)
    client = TestClient(app, raise_server_exceptions=False)
    assert not (tmp_path / "ws" / RID / "experiment.json").exists(), "the premise: nothing on disk"

    responses = _burst(client, [f"/api/experiments/{RID}"] * BURST)

    assert [r.status_code for r in responses] == [200] * BURST, [r.text[:160] for r in responses]
    assert all(r.json()["id"] == RID for r in responses)
    assert len(writes) == 1, f"the record was restored {len(writes)} times: {writes}"
    assert server.selects <= 2, f"{server.selects} passes ran for one burst"
    assert server.peak == 1, f"{server.peak} connections were open at once"


def test_a_burst_for_a_nonexistent_id_is_404_every_time_even_past_a_connection_cap(app, monkeypatch):
    """THE HOSTED SHAPE: eight concurrent reads of an id that does not exist, against a
    healthy server that refuses connections past a cap of two.

    POLARITY, measured on the pre-fix code: eight simultaneous passes, six refused
    connections, and ``503``s beside ``404``s — the page's "HTTP 503". After the fix a
    burst opens one connection at a time, so nothing is refused and every read is the
    honest ``404``. See the module docstring for what this does and does not prove about
    the hosted cause.
    """
    server = _Server([(RID, json.dumps(_stored_state(RID)))], cap=2)
    _serve(monkeypatch, server)
    client = TestClient(app, raise_server_exceptions=False)

    responses = _burst(client, _bundle(MISSING))

    statuses = [r.status_code for r in responses]
    assert 503 not in statuses, f"a healthy store answered {statuses}: {[r.text[:120] for r in responses]}"
    assert statuses == [404] * BURST, statuses
    assert server.refused == 0 and server.peak == 1


def test_without_a_cap_a_burst_for_a_nonexistent_id_was_already_all_404(app, monkeypatch):
    """THE NEGATIVE RESULT, KEPT AS A TEST: against a healthy, uncapped fake the pre-fix
    code ALSO answered eight ``404``s. So no in-process race was found that fails a pass
    on its own; this pins that the serialization did not introduce one."""
    server = _Server([(RID, json.dumps(_stored_state(RID)))])
    _serve(monkeypatch, server)
    client = TestClient(app, raise_server_exceptions=False)

    responses = _burst(client, _bundle(MISSING))

    assert [r.status_code for r in responses] == [404] * BURST
    assert server.selects <= 2 and server.peak == 1


def test_a_genuine_outage_is_still_503_for_every_read_and_is_not_retried_serially(app, monkeypatch):
    """THE 503 SEMANTICS ARE KEPT. A store that refuses EVERY connection is an outage,
    and a miss during it must not become a ``404`` — the record may be in the database.

    And the lock must not turn an outage into a queue: a request that waited behind a
    failing pass takes that pass's answer instead of running its own, so a burst makes
    at most two connection attempts rather than eight in a row. (Each attempt here takes
    ``SELECT_DELAY_S`` to fail, as a connect timeout does; an INSTANT refusal finishes
    before the next request arrives, so there is nothing to queue behind and each request
    may try for itself.)

    POLARITY, measured on the pre-fix code: eight ``503``s (so the status half held
    there too) and EIGHT concurrent connection attempts.
    """
    server = _Server([], refuse_all=True)
    _serve(monkeypatch, server)
    client = TestClient(app, raise_server_exceptions=False)

    responses = _burst(client, _bundle(MISSING))

    assert [r.status_code for r in responses] == [503] * BURST
    assert all(r.json()["message"] == repo.STORAGE_READ_FAILED_MESSAGE for r in responses), responses[0].text
    assert server.connects <= 2, f"{server.connects} connection attempts for one burst"


def test_an_answer_from_a_pass_that_started_BEFORE_the_request_is_never_reused(app, monkeypatch, tmp_path):
    """A pass already running when a request arrives may have taken its ``SELECT`` before
    a row the request is asking about was committed (by another replica, say). Reusing
    it would answer a false ``404``. The request must wait and run a pass of its own.

    Pinned deterministically: the first pass's ``SELECT`` sees no row; the row is
    committed while that pass is still running and the second request is waiting; the
    second request must then find the record.

    POLARITY: this guards the NEW rule rather than reproducing the old defect. The
    pre-fix code has no reuse at all, so the second request always ran its own pass
    there. It FAILS under the mutation "reuse the last finished pass, whenever it
    started" (measured: only ONE pass ran, so the second request's answer was that of a
    pass whose ``SELECT`` predated the row).
    """
    rows: list = []
    in_select = threading.Event()
    release = threading.Event()

    class _Late(_Server):
        def connect(self, env):
            conn = super().connect(env)
            first = self.connects == 1
            inner_cursor = conn.cursor

            def cursor():
                cur = inner_cursor()
                inner = cur.execute

                def execute(sql, params=None):
                    if sql == repo.Q_ALL_EXPERIMENTS and first:
                        in_select.set()
                        release.wait(timeout=10)
                    return inner(sql, params)

                cur.execute = execute  # type: ignore[method-assign]
                return cur

            conn.cursor = cursor  # type: ignore[method-assign]
            return conn

    server = _Late(rows)
    _serve(monkeypatch, server)
    client = TestClient(app, raise_server_exceptions=False)

    first: dict = {}
    t = threading.Thread(target=lambda: first.setdefault("r", client.get(f"/api/experiments/{RID}")))
    t.start()
    assert in_select.wait(timeout=10), "the first pass never reached its SELECT"
    # The row is committed AFTER the first pass read the table.
    server.rows.append((RID, json.dumps(_stored_state(RID))))
    second: dict = {}
    t2 = threading.Thread(target=lambda: second.setdefault("r", client.get(f"/api/experiments/{RID}")))
    t2.start()
    time.sleep(0.2)  # let the second request queue behind the running pass
    release.set()
    t.join(timeout=30)
    t2.join(timeout=30)

    assert first["r"].status_code in (200, 404)  # depends on when its file re-check runs
    assert server.selects == 2, "the second request must have run a pass of its own"
    assert second["r"].status_code == 200, (
        "the second request reused a pass that started before it arrived: " + second["r"].text[:200]
    )


def test_a_restore_never_overwrites_a_working_copy_that_appeared_after_the_check(app, monkeypatch, tmp_path):
    """A RESTORE CREATES A WORKING COPY; IT NEVER REPLACES ONE. If a working copy appears
    between the pass's check and its write — a save of a just-created record is the
    realistic writer — the newer document must survive, and the pass must not count it as
    a restore of its own."""
    store = repo.PostgresOrdinaryStore(
        {"PGHOST": "db.invalid", "PGDATABASE": dbw.EXPECTED_DATABASE},
        connect=lambda env: FakeConnection(rows=[(RID, json.dumps(_stored_state(RID)))]),
    )
    target = tmp_path / "ws" / RID / "experiment.json"
    newer = dict(_stored_state(RID), title="Saved a moment later")
    real = ws.atomic_write_text

    def racing_write(path, text):
        # The concurrent writer lands its newer document just before the restore's own
        # bytes reach the directory.
        if f"/{RID}/" in str(path) and not target.exists():
            real(target, json.dumps(newer))
        return real(path, text)

    monkeypatch.setattr(ws, "atomic_write_text", racing_write)

    assert store.hydrate() == 0, "a working copy another writer produced is not this pass's restore"
    assert json.loads(target.read_text())["title"] == "Saved a moment later"
    # And no staging file is left behind in the record's directory.
    assert sorted(p.name for p in target.parent.iterdir()) == ["experiment.json"]


# --- the no-hard-link fallback (added 2026-09-23, from the independent review of #280) ---
#
# `restore_working_copy` hard-links a staged file into place so a restore can never REPLACE a
# working copy; on a filesystem without hard links it falls back to one more existence check
# and `os.replace`. That branch had no test. These pin its three promises with `os.link`
# forced to fail the way such a filesystem fails (EPERM): it still CREATES a missing file, it
# still REFUSES when a copy already exists, and it leaves no staging file behind either way.
# (The fallback keeps a small check-then-replace window; the function's docstring says so.)


def _no_hard_links(monkeypatch):
    import errno
    import os

    def refuse(*_args, **_kwargs):
        raise OSError(errno.EPERM, "hard links are not supported on this filesystem")

    monkeypatch.setattr(os, "link", refuse)


def _staging_files(directory):
    return [p.name for p in directory.iterdir() if ".restore-" in p.name]


def test_without_hard_links_a_restore_still_creates_a_missing_working_copy(monkeypatch, tmp_path):
    _no_hard_links(monkeypatch)
    target = tmp_path / "experiment.json"
    assert ws.restore_working_copy(target, '{"restored": true}') is True
    assert json.loads(target.read_text()) == {"restored": True}
    assert _staging_files(tmp_path) == []


def test_without_hard_links_a_restore_never_replaces_a_copy_that_appears_after_its_first_check(
    monkeypatch, tmp_path
):
    """The fallback's own existence check is what this pins. A file present BEFORE the call is
    refused by the function's first check and never reaches the fallback, so a test that only
    pre-creates the file passes even with the fallback's check deleted (measured — that was this
    test's first version). The window the fallback check guards is a working copy that appears
    AFTER the first check: here a concurrent writer creates it at the moment the hard link is
    refused, and the restore must leave that newer copy standing."""
    import errno
    import os

    target = tmp_path / "experiment.json"

    def concurrent_writer_then_refuse(*_args, **_kwargs):
        target.write_text('{"newer": true}')
        raise OSError(errno.EPERM, "hard links are not supported on this filesystem")

    monkeypatch.setattr(os, "link", concurrent_writer_then_refuse)
    assert ws.restore_working_copy(target, '{"older": true}') is False
    assert json.loads(target.read_text()) == {"newer": True}
    assert _staging_files(tmp_path) == []
