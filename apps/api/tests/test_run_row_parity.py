"""THE STAGE-1 PARITY ORACLE for the ``isaac_runs`` SHADOW WRITE.

WHAT THIS FILE IS
=================
One property, asserted over and over against a REAL PostgreSQL engine:

    after any save, the rows of ``isaac_runs`` for an experiment are exactly
    ``exp.sorted_runs()`` — id, ordinal, document, rev and generation.

``isaac_runs`` is a SHADOW. ``CLAUDE.md`` §15 is explicit that the experiment
document remains authoritative, that ``state["runs"]`` stays where it is, and that
making ``isaac_runs`` a READ source is a separate, unauthorized decision. **Nothing
in this file reads a run row on behalf of the application.** Every read here is a
TEST reading the table to check the shadow against the document. That is the whole
point of a shadow: a row nobody reads is only worth having if it is right, and the
only way to know it is right is to look at it from outside the application.

WHY IT MUST RUN AGAINST A REAL ENGINE, AND WHY IT SKIPS EVERYWHERE ELSE
======================================================================
``test_experiment_repository.py`` already exercises the run write path against an
IN-PROCESS FAKE DRIVER, and that file's own docstring says what that proves: the
SHAPE — one transaction, the statement policy, the accepted gate, deterministic
rollback. It does not prove the SQL is valid PostgreSQL, it enforces none of
``0002_runs``' seven constraints, and — the one that matters most here — the fake
hands back exactly the document it was given, so a text-vs-document comparison
defect in the diff would PASS there and rewrite every row on every save here.

So this suite is the real-engine half. There is no PostgreSQL on a developer
machine in this project, and by project rule (``CLAUDE.md`` §15, and
``docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52``) no agent
may reach for a kubeconfig, a port-forward or a Secret to obtain one. The engine
this suite is written for is CI's ``postgres:18`` SERVICE CONTAINER, in
``.github/workflows/ci.yml``'s ``postgres-migration`` job. Locally every test here
SKIPS, and a skip is reported as a skip — never as a pass.

**A SKIP IS ONLY HONEST IF SOMETHING SOMEWHERE REFUSES TO ACCEPT IT.** A suite that
silently skips in the one environment that can run it is worse than no suite,
because the green tick means "not run" while reading as "verified". So
:data:`REQUIRE_ENV` exists: CI sets ``ISAAC_REQUIRE_REAL_ENGINE_PARITY=1``, and
:func:`test_the_real_engine_is_present_when_the_environment_demands_it` then FAILS
instead of skipping if the engine is not reachable.

AND THE ORACLE ITSELF IS CONTROLLED
===================================
:func:`test_the_parity_oracle_FAILS_when_a_row_is_mutated_out_of_band` and its
sibling mutate a row behind the application's back and assert the oracle goes RED.
A control suite that can only produce green is not evidence; it is a gap wearing
the costume of one.

NO HOSTED DATABASE IS CONTACTED BY ANYTHING IN THIS FILE. The connection is
whatever the standard libpq environment variables point at, which in CI is a
throwaway container created and destroyed by the job, and which on a developer
machine is nothing at all.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from typing import Any

import pytest

import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
import isaac_api.workspace as ws

# =============================================================================
# 0. is there an engine, and is one REQUIRED?
# =============================================================================

#: Set by CI's ``postgres-migration`` job. When it is set, an unreachable engine is
#: a FAILURE rather than a skip — see the module docstring.
REQUIRE_ENV = "ISAAC_REQUIRE_REAL_ENGINE_PARITY"


def _probe_engine() -> tuple[bool, str]:
    """``(available, reason)``: can this process reach a migrated app database?

    Deliberately probes for the WHOLE precondition rather than just ``PGHOST``:
    the driver must be importable, the ``PGDATABASE`` gate must pass, the server
    must answer, and ``isaac_runs`` must exist. Anything less and the suite would
    fail for a reason that has nothing to do with parity.

    It opens ONE short-lived transaction through the application's own write path,
    so it inherits the timeouts, the database gate and the statement policy. It
    writes nothing.
    """
    if not dbw.database_configured(os.environ):
        return False, "no PGHOST: this suite needs a real PostgreSQL (CI's postgres:18)"
    try:
        dbw.pgdatabase_gate(os.environ)
    except dbw.WriteRefused as exc:
        return False, f"the PGDATABASE gate refused this environment: {exc}"
    try:
        with dbw.write_transaction(os.environ) as (cursor, policy):
            cursor.execute(policy.check(repo.Q_RUN_TABLE_PRESENT), (repo.RUN_TABLE,))
            row = cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - a probe reports, it does not raise
        return False, f"could not reach the database ({type(exc).__name__})"
    if not row or row[0] is None:
        return False, "isaac_runs does not exist: migration 0002_runs is not applied"
    return True, "a real engine with 0002_runs applied is reachable"


_AVAILABLE, _REASON = _probe_engine()

#: Applied to every parity test individually rather than as a module-level
#: ``pytestmark``, because ONE test in this file must stay collected and runnable
#: when the engine is absent: the one that turns an unexpected absence into a
#: failure.
real_engine = pytest.mark.skipif(not _AVAILABLE, reason=_REASON)


def test_the_real_engine_is_present_when_the_environment_demands_it():
    """THE ANTI-SILENT-SKIP GUARD. Not itself a parity assertion.

    Locally this skips, and says why. In CI, where ``ISAAC_REQUIRE_REAL_ENGINE_PARITY``
    is set, it FAILS if the engine is not reachable — so the whole suite quietly
    skipping in the only place it can run is a red build, not a green one.
    """
    if os.environ.get(REQUIRE_ENV) != "1":
        pytest.skip(
            f"{REQUIRE_ENV} is not set, so a real engine is optional here. "
            f"Probe result: {_REASON}"
        )
    assert _AVAILABLE, (
        f"{REQUIRE_ENV}=1 demands a real engine and this one is unusable: {_REASON}"
    )


# =============================================================================
# 1. reading the table — the TEST's own statements, never the application's
# =============================================================================
#
# These are TEST statements. They are defined here rather than in the application
# for a reason that is a rule and not a preference: `db_write`'s primary guarantee
# is that every statement the WRITE PATH issues is a module-level constant in the
# application, and adding a test-only read to `experiment_repository` would put a
# statement in the application that the application never issues — and would make
# the "no read path names isaac_runs" enumeration in
# `test_0002_is_now_written_by_the_write_path_and_by_nothing_else` false. They
# still go through `policy.check(...)`, so they are bound by the same owned-table
# and forbidden-verb rules as everything else.

#: Every column of every run row in the database, including the two SERVER-SIDE row
#: stamps the application never reads. ``updated_utc`` is how a real engine answers
#: "did this save TOUCH this row", which no in-process fake can answer at all.
Q_TEST_ALL_RUN_ROWS = (
    "SELECT run_id, experiment_id, ordinal, state, rev, generation,"
    " created_utc, updated_utc FROM isaac_runs"
)

#: The same, narrowed to one experiment.
Q_TEST_RUN_ROWS_FOR = Q_TEST_ALL_RUN_ROWS + " WHERE experiment_id = %s"

#: THE OUT-OF-BAND MUTATION the oracle's own control test uses. It is a legal,
#: policy-passing statement against an owned table, issued by the TEST — which is
#: precisely the situation a shadow row can find itself in and the application
#: cannot notice, because nothing in the application ever reads the row back.
Q_TEST_SHIFT_ORDINALS = (
    "UPDATE isaac_runs SET ordinal = ordinal + 1 WHERE experiment_id = %s"
)

#: The second control: a row that has simply gone.
Q_TEST_DELETE_RUNS_OF = "DELETE FROM isaac_runs WHERE experiment_id = %s"

#: DRIFT IN THE DOCUMENT ONLY, with every promoted column left exactly as it was.
#: This is the shape that tells apart a diff comparing ``state`` from one comparing
#: only ``(ordinal, rev, generation)`` — see
#: :func:`test_the_diff_compares_the_DOCUMENT_and_repairs_a_tampered_row`.
Q_TEST_TAMPER_WITH_A_RUN_LABEL = (
    "UPDATE isaac_runs SET state = jsonb_set(state, '{label}',"
    " '\"TAMPERED-OUT-OF-BAND\"') WHERE run_id = %s"
)


def _as_document(value: Any) -> Any:
    """A ``jsonb`` column as a PARSED DOCUMENT, whatever the driver handed back.

    psycopg2 registers a jsonb loader and returns a ``dict``; a build without it
    returns text. Comparing as TEXT would be wrong in the direction that matters:
    ``jsonb`` normalises key order and whitespace on the way in, so a text
    comparison reports a difference on every single save and would make a broken
    diff look like a working one. The application's own ``_stored_run_rows``
    applies the same tolerance for the same reason.
    """
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    return value


def _query(sql: str, params: tuple | None = None) -> list[tuple]:
    """Run one read against the real engine through the application's write path."""
    with dbw.write_transaction(os.environ) as (cursor, policy):
        cursor.execute(policy.check(sql), params)
        return list(cursor.fetchall() or [])


def _execute(sql: str, params: tuple | None = None) -> int:
    """Run one out-of-band statement. Used ONLY by the oracle's control tests."""
    with dbw.write_transaction(os.environ) as (cursor, policy):
        cursor.execute(policy.check(sql), params)
        return cursor.rowcount


def _full_rows(experiment_id: str | None = None) -> dict[str, tuple]:
    """``run_id -> every column``, with ``state`` parsed. The whole table, or one
    experiment's slice of it.

    Includes ``created_utc``/``updated_utc``, so "these rows did not move" is a
    claim about the SERVER's own stamps and not about what the test re-derived.
    """
    if experiment_id is None:
        rows = _query(Q_TEST_ALL_RUN_ROWS)
    else:
        rows = _query(Q_TEST_RUN_ROWS_FOR, (experiment_id,))
    return {
        row[0]: (row[1], row[2], _as_document(row[3]), row[4], row[5], row[6], row[7])
        for row in rows
    }


# =============================================================================
# 2. THE ORACLE
# =============================================================================


def _observed(experiment_id: str) -> list[tuple]:
    """``(run_id, ordinal, state, rev, generation)`` for every row of one experiment."""
    rows = _query(
        "SELECT run_id, ordinal, state, rev, generation FROM isaac_runs"
        " WHERE experiment_id = %s",
        (experiment_id,),
    )
    return sorted(
        ((row[0], row[1], _as_document(row[2]), row[3], row[4]) for row in rows),
        key=lambda row: row[0],
    )


def _expected(exp: "ws.Experiment") -> list[tuple]:
    """The same tuple, projected from the AUTHORITATIVE document."""
    return sorted(
        (
            (run.id, run.ordinal, run.to_state(), run.rev, run.generation)
            for run in exp.sorted_runs()
        ),
        key=lambda row: row[0],
    )


def assert_parity(exp: "ws.Experiment") -> None:
    """THE ORACLE. The rows for ``exp`` ARE ``exp.sorted_runs()``, column by column.

    ``sorted(...)`` is keyed on the run id EXPLICITLY. The natural
    ``sorted(list_of_tuples)`` would compare the tuples element by element and, on
    an ordinal tie, would reach the ``state`` DICT — which is unorderable and would
    raise ``TypeError`` instead of failing the assertion. Run ids are unique (the
    primary key on one side, ``_hydrate_runs`` dropping duplicates on the other),
    so keying on the id is a total order that never has to look further.

    ``state`` is compared as a PARSED DOCUMENT, never as text: the column is
    ``jsonb`` and normalises key order and whitespace on the way in.

    The ``experiment_id`` COLUMN is deliberately not part of the tuple — the
    ``WHERE`` already pinned it, so every row returned carries it by construction.
    The document's own ``experiment_id`` IS compared, inside ``state``, which is
    what the legacy-empty-string case turns on.
    """
    observed = _observed(exp.id)
    expected = _expected(exp)
    assert observed == expected, (
        "isaac_runs disagrees with the experiment document.\n"
        f"  rows:     {observed}\n"
        f"  document: {expected}"
    )


# =============================================================================
# 3. fixtures and helpers
# =============================================================================


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A private ordinary-scope workspace, with the REAL database left configured.

    ``PGHOST`` and friends are deliberately NOT cleared — this suite exists to talk
    to the engine. Only the workspace directory is redirected, so each test gets
    its own working copy and cannot see another's files.
    """
    root = tmp_path / "ws"
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(root))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    return root


def _new_experiment(title: str) -> "ws.Experiment":
    """Create an ordinary experiment through the real repository seam.

    Asserts the DURABLE backend was selected. Without that, a misconfigured
    environment would silently exercise the filesystem repository and every parity
    assertion below would be reading an empty table and comparing it against an
    experiment with no runs — green, and meaningless.
    """
    repository = repo.repository()
    assert repository.backend == repo.BACKEND_POSTGRES, repository.backend
    return repository.create(title=title, description=None)


def _with_runs(title: str, count: int) -> "ws.Experiment":
    """An experiment carrying ``count`` runs, persisted in ONE versioned save."""
    exp = _new_experiment(title)
    for index in range(count):
        exp.add_run(label=f"run {index}")
    if count:
        assert exp.save_versioned() is True
    return exp


def _envelope(value: str) -> dict:
    """A draft field envelope. Synthetic, and unmistakably so.

    ``status``/``evidence`` are present because the draft shape carries them, not
    because anything here is asserting a scientific claim: the value is a fixture
    string, and no test in this file reads it as science.
    """
    return {
        "value": value,
        "status": "verified",
        "evidence": [{"source_type": "user_confirmation", "detail": "synthetic fixture"}],
    }


# =============================================================================
# 4. the scenarios
# =============================================================================


@real_engine
def test_parity_an_experiment_with_no_runs_leaves_isaac_runs_holding_no_row_for_it(
    workspace,
):
    """ZERO IS A ROW COUNT, NOT AN ABSENCE OF EVIDENCE — and the neighbours matter.

    The interesting half is the second assertion. ``Q_DELETE_ABSENT_RUNS`` deletes
    "every row of this experiment the document no longer names", and a predicate
    that lost its ``experiment_id`` clause would still leave THIS experiment with
    no rows while quietly emptying every other experiment's. So a run-less save is
    checked against a SNAPSHOT OF THE WHOLE TABLE, stamps included.
    """
    neighbour = _with_runs("parity: the neighbour that must not move", 2)
    assert_parity(neighbour)
    before = _full_rows()
    assert len(before) >= 2

    empty = _new_experiment("parity: no runs at all")
    assert empty.runs == []
    assert _observed(empty.id) == []
    assert_parity(empty)

    # A second save, this time versioned, so the run-less path is exercised on both
    # of the application's persistence primitives.
    empty.title = "parity: still no runs"
    assert empty.save_versioned() is True
    assert _observed(empty.id) == []

    assert _full_rows() == before, "a run-less save disturbed another experiment's rows"


@real_engine
def test_parity_one_run_produces_exactly_one_row_equal_to_its_to_state(workspace):
    """The base case, stated in full rather than by the oracle alone.

    The oracle compares tuples; this also asserts the DOCUMENT is ``to_state()``
    verbatim — every key, including the ``experiment_id`` duplication and the empty
    ``overrides`` map that ``to_state`` always emits. Nothing is dropped, cleaned or
    reordered on the way into ``jsonb``.
    """
    exp = _with_runs("parity: exactly one", 1)
    (run,) = exp.runs

    rows = _full_rows(exp.id)
    assert list(rows) == [run.id]
    experiment_id, ordinal, state, rev, generation, _created, _updated = rows[run.id]
    assert experiment_id == exp.id
    assert ordinal == run.ordinal
    assert rev == run.rev
    assert generation == run.generation
    assert state == run.to_state()
    # The document really does carry every key, so "verbatim" is a measured claim.
    assert set(state) == {
        "id",
        "experiment_id",
        "label",
        "ordinal",
        "created_utc",
        "draft",
        "record_id",
        "overrides",
        "rev",
        "updated_utc",
        "generation",
    }
    assert_parity(exp)


@real_engine
@pytest.mark.parametrize("n", [0, 1, 2, 50, 200])
def test_parity_holds_at_every_run_count_from_zero_to_two_hundred(workspace, n):
    """THE COUNT IS NOT A DETAIL. Three distinct things break at different sizes.

    ``0`` is the empty-array case ``Q_DELETE_ABSENT_RUNS``' ``%s::text[]`` cast
    exists for — an empty array literal carries no element type for the server to
    infer, so this is the one save where the cast is load-bearing. ``1`` and ``2``
    are the ordinary shapes. ``50`` and ``200`` are where a diff that silently
    degraded into a blanket rewrite would still be CORRECT and would be issuing
    N+1 statements under a 15-second per-statement timeout.

    A row-count equality is asserted BESIDE the oracle deliberately: the oracle
    compares two sorted lists, and two lists can only be equal if they are the same
    length — but stating the count separately is what makes a failure legible as
    "the table has the wrong number of rows" rather than as a wall of tuples.
    """
    exp = _with_runs(f"parity: {n} runs", n)
    assert len(exp.runs) == n
    assert len(_observed(exp.id)) == n
    assert_parity(exp)

    # And the set really is a function of the document, not of insertion history:
    # drop every run and the table follows.
    if n:
        exp.runs = []
        assert exp.save_versioned() is True
        assert _observed(exp.id) == []
        assert_parity(exp)


@real_engine
def test_parity_an_inherited_address_is_absent_from_the_run_row_because_absence_is_the_inheritance(
    workspace,
):
    """CONTRACT §2 D2, VISIBLE IN THE TABLE: a run stores only the ABSENCE.

    ``workspace.py``'s ``Run.overrides`` says it directly — "THE ABSENCE OF A KEY IS
    THE INHERITANCE. Nothing is copied down from the experiment." This asserts the
    shadow row honours that. If a future writer ever "helpfully" materialised the
    resolved view into the row, every experiment-level edit would silently stop
    flowing through to its runs, and the table would be the place that lied.

    Both halves are asserted, because only the pair means anything: the inherited
    content is ABSENT from the row, and ``resolve_inherited`` nonetheless reports it
    for that run. Absence without live resolution would just be data loss.
    """
    exp = _new_experiment("parity: inheritance is an absence")
    exp.draft = {
        "fields": {"sample.material.name": _envelope("SYNTHETIC-FIXTURE-MATERIAL")},
        "attribution": {"contributors": [{"name": "Synthetic Fixture"}]},
        "tags": ["synthetic-campaign"],
    }
    run = exp.add_run(label="inherits everything")
    assert exp.save_versioned() is True

    rows = _full_rows(exp.id)
    state = rows[run.id][2]

    # The run's own draft is empty and its override map is empty...
    assert state["draft"] == {}
    assert state["overrides"] == {}
    # ...and no trace of the experiment-level content reached the row, in any key.
    blob = json.dumps(state, sort_keys=True)
    assert "SYNTHETIC-FIXTURE-MATERIAL" not in blob
    assert "synthetic-campaign" not in blob
    assert "Synthetic Fixture" not in blob

    # THE OTHER HALF: the run really does inherit, computed on read.
    resolved = exp.resolve_run(run)
    inherited = resolved[ws.field_address("sample.material.name")]
    assert inherited.provenance == ws.PROVENANCE_INHERITED
    assert inherited.value == "SYNTHETIC-FIXTURE-MATERIAL"
    assert resolved[ws.block_address("tags")].payload == ["synthetic-campaign"]

    assert_parity(exp)


@real_engine
def test_parity_an_override_and_its_displaced_payload_round_trip_verbatim(workspace):
    """AN OVERRIDE IS AUDITED STATE, so the row must carry ALL THREE of its parts.

    ``payload`` (what this run says), ``recorded_utc`` (when the displacement was
    recorded) and ``displaced`` (what the experiment said AT THAT MOMENT). The third
    is the one a projection is tempted to drop, and it is the one contract §2 D2
    requires: an override records what it displaced. It is also a HISTORICAL fact —
    so the test edits the experiment afterwards and asserts ``displaced`` did NOT
    follow, which is the difference between a captured record and a live alias.
    """
    exp = _new_experiment("parity: an override survives verbatim")
    address = ws.field_address("sample.material.name")
    exp.draft = {"fields": {"sample.material.name": _envelope("EXPERIMENT-LEVEL-VALUE")}}
    run = exp.add_run(label="overrides one address")
    override = exp.set_run_override(run, address, _envelope("RUN-LEVEL-VALUE"))
    assert exp.save_versioned() is True

    state = _full_rows(exp.id)[run.id][2]
    assert set(state["overrides"]) == {address}
    stored = state["overrides"][address]
    assert stored == override.to_state()
    assert stored["payload"]["value"] == "RUN-LEVEL-VALUE"
    assert stored["recorded_utc"] == override.recorded_utc
    assert stored["displaced"]["value"] == "EXPERIMENT-LEVEL-VALUE"
    assert_parity(exp)

    # HISTORY IS NOT REFRESHED. Editing the experiment moves what is INHERITED and
    # leaves what was DISPLACED exactly where it was.
    exp.draft["fields"]["sample.material.name"] = _envelope("EDITED-AFTERWARDS")
    assert exp.save_versioned() is True
    after = _full_rows(exp.id)[run.id][2]
    assert after["overrides"][address]["displaced"]["value"] == "EXPERIMENT-LEVEL-VALUE"
    assert_parity(exp)


@real_engine
def test_parity_clearing_an_override_removes_the_address_from_the_row(workspace):
    """THE SIBLING OF THE TEST ABOVE, and the direction a projection gets wrong.

    Adding a key to a document is easy to project. REMOVING one is where a writer
    that merges instead of replacing leaves the old key behind — and since nothing
    reads this table, a stale override would sit there indefinitely, invisible.
    """
    exp = _new_experiment("parity: clearing an override")
    address = ws.field_address("sample.material.name")
    exp.draft = {"fields": {"sample.material.name": _envelope("EXPERIMENT-LEVEL-VALUE")}}
    run = exp.add_run(label="overrides then inherits")
    exp.set_run_override(run, address, _envelope("RUN-LEVEL-VALUE"))
    assert exp.save_versioned() is True
    assert set(_full_rows(exp.id)[run.id][2]["overrides"]) == {address}

    assert exp.clear_run_override(run, address) is True
    assert exp.save_versioned() is True

    state = _full_rows(exp.id)[run.id][2]
    assert state["overrides"] == {}, "a cleared override survived in the shadow row"
    blob = json.dumps(state, sort_keys=True)
    assert "RUN-LEVEL-VALUE" not in blob
    assert_parity(exp)


@real_engine
def test_parity_a_versioned_save_moves_only_the_changed_runs_rev_and_the_row_agrees(
    workspace,
):
    """THE DIFF, PROVEN BY THE SERVER'S OWN STAMPS.

    ``_write_run_rows`` skips a run whose stored columns already equal the desired
    ones. Only a real engine can check that, and it checks it through
    ``updated_utc``, which ``Q_UPSERT_RUN`` stamps ``now()`` on every ACCEPTED
    update. If the stored ``jsonb`` document ever compared unequal to
    ``Run.to_state()`` — the text-vs-document defect the in-process fake cannot
    catch — all three stamps would move here and this test would go red.
    """
    exp = _with_runs("parity: only the changed run moves", 3)
    before = {run_id: row[6] for run_id, row in _full_rows(exp.id).items()}
    assert len(before) == 3
    revs_before = {run.id: run.rev for run in exp.runs}

    edited = exp.sorted_runs()[1]
    edited.draft = {"fields": {"context.temperature_K": _envelope("77")}}
    assert exp.save_versioned() is True

    # THE DOCUMENT: exactly one rev moved.
    moved = [run.id for run in exp.runs if run.rev != revs_before[run.id]]
    assert moved == [edited.id], moved
    assert edited.rev == revs_before[edited.id] + 1

    # THE ROWS AGREE — and the two untouched rows were not even rewritten.
    after = {run_id: row[6] for run_id, row in _full_rows(exp.id).items()}
    assert after[edited.id] != before[edited.id], "the changed run's row was not written"
    for run in exp.sorted_runs():
        if run.id != edited.id:
            assert after[run.id] == before[run.id], (
                f"an unchanged run row was rewritten: {run.id}"
            )
    assert_parity(exp)


@real_engine
def test_parity_reordering_rewrites_only_the_ordinals_that_moved(workspace):
    """A REORDER IS A CONTENT CHANGE FOR THE RUNS THAT MOVED AND FOR NO OTHERS.

    ``ordinal`` is inside ``_run_signature_payload``, so swapping two ordinals
    genuinely changes those two runs and genuinely leaves the third alone. The row
    set must follow exactly that, in both directions: the two that moved are
    rewritten, the one that did not is untouched.
    """
    exp = _with_runs("parity: a reorder", 3)
    ordered = exp.sorted_runs()
    first, second, third = ordered
    before = {run_id: row[6] for run_id, row in _full_rows(exp.id).items()}

    first.ordinal, second.ordinal = second.ordinal, first.ordinal
    assert exp.save_versioned() is True

    # The canonical order really did change.
    assert [run.id for run in exp.sorted_runs()] == [second.id, first.id, third.id]

    after = _full_rows(exp.id)
    assert after[first.id][6] != before[first.id]
    assert after[second.id][6] != before[second.id]
    assert after[third.id][6] == before[third.id], "an unmoved run's row was rewritten"
    # The promoted ordinal column follows the document, not the insertion order.
    assert after[first.id][1] == first.ordinal
    assert after[second.id][1] == second.ordinal
    assert_parity(exp)


@real_engine
def test_parity_a_run_added_later_appears_without_rewriting_its_siblings(workspace):
    """GROWTH IS INCREMENTAL. Adding the Nth run must cost one row write, not N.

    This is the property that makes the diff worth its extra ``SELECT``: an
    experiment that accumulates runs over a session must not rewrite its whole row
    set on every addition. The siblings' server-side ``updated_utc`` is the
    measurement.
    """
    exp = _with_runs("parity: a later arrival", 3)
    before = {run_id: row[6] for run_id, row in _full_rows(exp.id).items()}

    added = exp.add_run(label="the fourth")
    assert exp.save_versioned() is True

    after = _full_rows(exp.id)
    assert set(after) == set(before) | {added.id}
    for run_id, stamp in before.items():
        assert after[run_id][6] == stamp, f"adding a run rewrote sibling {run_id}"
    assert after[added.id][1] == added.ordinal == 4
    assert_parity(exp)


@real_engine
def test_parity_survives_a_pod_restart_and_hydration_leaves_the_rows_untouched(
    workspace,
):
    """A POD RESTART, AND THE PROPERTY IS "UNCHANGED", NOT "REBUILT".

    ``PostgresOrdinaryStore.hydrate`` reads ``isaac_experiments`` and writes FILES.
    It does not read ``isaac_runs`` and it does not write it — nothing in this
    application reads that table at all. So the honest property after a restart is
    that the rows are exactly as the last save left them, byte for byte including
    the server-side stamps, and that the restored working copy still agrees with
    them.

    Asserting "the rows were rebuilt" would be asserting a behaviour that does not
    exist and should not; asserting "unchanged" is what actually protects the
    shadow, because a hydration that DID touch the rows would be a second, unowned
    write path.
    """
    exp = _with_runs("parity: a pod restart", 3)
    rid = exp.id
    before_all = _full_rows()
    before_mine = _full_rows(rid)
    assert len(before_mine) == 3

    # The pod restarts: the emptyDir workspace is gone.
    shutil.rmtree(ws.workspace_root())
    # THE PROBE IS THE FILESYSTEM, NOT ``load_experiment`` — measured, after this
    # test asserted the wrong thing. ``ws.load_experiment`` HYDRATES ON A MISS by
    # design (``experiment_repository``'s module docstring: "a miss on an
    # ordinary-scope load" consults the store, because on an ``emptyDir`` pod "no
    # directory" no longer implies "no record"), so it returns the record rather
    # than ``None`` and would have made this step assert the opposite of the
    # product's actual, correct behaviour.
    assert not (ws.workspace_root() / rid / "experiment.json").exists()

    restored = repo.repository().hydrate()
    assert restored >= 1, restored

    # NOT ONE ROW MOVED — not this experiment's, and not anybody else's.
    assert _full_rows(rid) == before_mine
    assert _full_rows() == before_all

    reloaded = ws.load_experiment(rid)
    assert reloaded is not None
    assert len(reloaded.runs) == 3
    assert_parity(reloaded)

    # And a save AFTER the restart still agrees, so the restored working copy is a
    # usable basis for the diff rather than merely a readable one.
    reloaded.sorted_runs()[0].label = "renamed after the restart"
    assert reloaded.save_versioned() is True
    assert_parity(reloaded)


class _RecordingCursor:
    """A real cursor that also writes down the SQL it is asked to execute.

    Everything except ``execute`` falls through to the real driver object, so
    ``rowcount``, ``fetchone`` and ``fetchall`` are the engine's answers and not a
    fake's. It observes; it changes nothing.
    """

    def __init__(self, inner, log: list[tuple]) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_log", log)

    def execute(self, sql, params=None):
        self._log.append((sql, params))
        return self._inner.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)


class _RecordingConnection:
    """The same, one level up. ``autocommit`` is a SET, so ``__setattr__`` forwards.

    Without the ``__setattr__`` forward, ``write_transaction``'s
    ``conn.autocommit = False`` would land on the proxy and the REAL connection
    would stay on autocommit — a wrapper that silently disabled the transaction it
    was meant to watch.
    """

    def __init__(self, inner, log: list[tuple]) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_log", log)

    def cursor(self):
        return _RecordingCursor(self._inner.cursor(), self._log)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)


def _recording_store() -> tuple[repo.PostgresOrdinaryStore, list[tuple]]:
    """A REAL durable store whose statements are recorded.

    ``PostgresOrdinaryStore`` forwards ``**connect_kwargs`` to
    ``write_transaction``, whose ``connect`` seam exists precisely so the shape can
    be observed. Here it wraps the genuine ``connect_psycopg2`` rather than
    replacing it, so this is a real connection to the real engine with a notebook
    attached.
    """
    log: list[tuple] = []

    def connect(env):
        return _RecordingConnection(dbw.connect_psycopg2(env), log)

    return repo.PostgresOrdinaryStore(os.environ, connect=connect), log


@real_engine
def test_parity_a_lost_compare_and_swap_leaves_the_winners_rows_untouched(workspace):
    """THE MOST DANGEROUS LINE IN THE SHADOW WRITE, CHECKED AGAINST A REAL ENGINE.

    ``persist`` writes run rows strictly inside ``if accepted:``. A writer that lost
    the experiment-level compare-and-swap and stamped its runs anyway would overwrite
    the WINNER's rows while correctly reporting ``412`` to its own client — the
    last-writer-wins defect ``Q_UPSERT_EXPERIMENT``'s predicate exists to close,
    reintroduced one level down and INVISIBLE, because the loser is told it lost and
    nothing ever reads the rows.

    TWO REAL CONNECTIONS, AND THEY ARE SEQUENTIAL, NOT CONCURRENT — stated plainly
    rather than implied. The predicate is decided from the ROW's state, not from wall
    clock overlap, so the wedge is built the way the deployment actually builds it:
    a winner moves the row forward (a second replica, or a fault between ``save()``'s
    two writes) while this process's workspace file stays behind. The loser then
    offers a rev the row has already passed and is refused by the server.

    THREE THINGS ARE ASSERTED, and the third is the one this test exists for:
      1. the loser really was refused (``DurableWriteConflict``, not a success);
      2. its transaction issued NO statement naming ``isaac_runs`` — and did not
         even reach the ``to_regclass`` probe, which lives inside the same branch;
      3. the winner's rows are byte-identical afterwards, stamps included.
    """
    exp = _with_runs("parity: a lost compare-and-swap", 2)
    rid = exp.id
    winner_rows = _full_rows(rid)
    assert len(winner_rows) == 2

    # THE WINNER moves the row forward without touching the workspace file or the
    # run rows — exactly what a second replica's save looks like from here.
    wedged = dict(exp.to_state(), rev=exp.rev + 7, title="a replica won")
    with dbw.write_transaction(os.environ) as (cursor, policy):
        cursor.execute(
            policy.check(repo.Q_UPSERT_EXPERIMENT),
            (rid, json.dumps(wedged, sort_keys=True)),
        )
        assert cursor.rowcount == 1, "the winner's own write was refused"

    # THE LOSER: this process's copy, still at the old rev, with a genuine change.
    loser = ws.load_experiment(rid)
    assert loser is not None and loser.rev == exp.rev
    loser.sorted_runs()[0].label = "the loser's rename"
    loser.runs[0].rev += 1  # what _bump_changed_runs would have done

    store, log = _recording_store()
    with pytest.raises(repo.DurableWriteConflict) as refusal:
        store.persist(loser)
    assert refusal.value.experiment_id == rid
    assert refusal.value.stored_state["rev"] == exp.rev + 7

    issued = [sql for sql, _ in log]
    assert not [sql for sql in issued if "isaac_runs" in sql.lower()], issued
    assert repo.Q_RUN_TABLE_PRESENT not in issued, (
        "the loser reached the run-table probe, which lives inside the accepted branch"
    )
    assert repo.Q_UPSERT_EXPERIMENT in issued and repo.Q_ONE_EXPERIMENT in issued

    assert _full_rows(rid) == winner_rows, "a losing writer rewrote the winner's rows"


@real_engine
def test_parity_holds_for_a_legacy_run_document_carrying_an_empty_experiment_id(
    workspace,
):
    """THE SHAPE ``isaac_runs_document_identity``'S ``coalesce(nullif(...))`` EXISTS FOR.

    ``Run.to_state()`` emits ``experiment_id`` unconditionally and ``Run.from_state``
    reads it through ``_as_str``, which returns ``''`` for an absent key — so a
    legacy run document carries ``"experiment_id": ""``, not a missing key.
    ``_hydrate_runs`` deliberately does NOT repair it from the owning experiment,
    because repairing it on READ would change the run's authoritative signature and
    bump every record's ``rev`` on a mere listing. The value is therefore PERMANENT,
    and the row must be writable with it.

    The CHECK's original form compared ``'' = experiment_id``, which is FALSE (not
    NULL) and REFUSED this row; the fixture that "proved" it worked inserted a bare
    ``'{}'``. So this test builds the document the way the APPLICATION builds it —
    through ``Run.from_state`` — rather than by hand, which is the whole reason the
    earlier check passed while the constraint was wrong.

    A row rejected here would abort the transaction and take the EXPERIMENT upsert
    down with it, so this is not a cosmetic case: it is whether an experiment holding
    a legacy run can be saved at all.
    """
    exp = _new_experiment("parity: a legacy run document")
    legacy = ws.Run.from_state(
        {
            "id": ws.new_record_id(),
            # every string key absent -> `_as_str` yields "" for each
            "created_utc": "2026-01-01T00:00:00Z",
        }
    )
    assert legacy.experiment_id == "", "the premise of this test moved"
    exp.runs.append(legacy)
    assert exp.save_versioned() is True

    rows = _full_rows(exp.id)
    assert list(rows) == [legacy.id]
    experiment_id_column, _ordinal, state, _rev, _generation, _c, _u = rows[legacy.id]
    # THE COLUMN names the owning experiment; the DOCUMENT keeps what it always said.
    assert experiment_id_column == exp.id
    assert state["experiment_id"] == ""
    assert state["id"] == legacy.id
    assert_parity(exp)

    # It stays writable: a second save of the same legacy run is not a one-off.
    legacy.label = "renamed legacy run"
    assert exp.save_versioned() is True
    assert _full_rows(exp.id)[legacy.id][2]["experiment_id"] == ""
    assert_parity(exp)


@real_engine
def test_parity_an_UNVERSIONED_save_of_a_CHANGED_document_is_refused_and_leaves_no_stale_row(
    workspace,
):
    """WRITTEN TO PROVE ONE THING, AND IT MEASURED ANOTHER. Both are recorded.

    THE PREMISE THIS TEST WAS COMMISSIONED WITH: ``Experiment.save()`` is the
    UNVERSIONED persistence primitive, ``_bump_changed_runs`` is the only writer of
    ``Run.rev`` and runs only on the write branch of ``save_versioned`` — so a
    caller that mutates a run and calls ``save()`` changes the run's document while
    ``rev``, ``ordinal`` and ``generation`` all stay put, and a diff comparing only
    the promoted columns would leave the row STALE.

    WHAT A REAL ENGINE ACTUALLY DOES, measured here: that write never lands at all.
    ``Q_UPSERT_EXPERIMENT``'s predicate admits a differing generation, a strictly
    greater rev, or a byte-identical document — and an unversioned save of a CHANGED
    document is none of the three. The server refuses it and ``persist`` raises
    ``DurableWriteConflict``. So on a durable deployment the run rows CANNOT go stale
    by this route, because the experiment write they ride inside is rejected first.

    THAT IS A FINDING ABOUT THE PRODUCT, NOT A BUG THIS SLICE FIXES, and it is
    reported rather than patched. Two consequences worth writing down where they
    will be found:

    * ``Experiment.save()`` can persist to Postgres ONLY when the document is
      byte-identical (clause 3) or the rev has already moved. Its filesystem
      behaviour — write whatever you are holding — is not its durable behaviour.
    * ``_bump_changed_runs``' documented case "a run first persisted by a plain
      ``save()`` sits at rev 0" is therefore a FILESYSTEM-ONLY reality. Against a
      database that same sequence is refused, because adding a run changes the
      document without moving the experiment's rev.

    WHAT IS ASSERTED, then, is the property that is true and that still matters: the
    refusal is CLEAN. No run row is half-written, none is left stale, and the rows
    still agree with the document the database actually holds. The load-bearing case
    for ``state`` being inside the diff is proven separately and reachably, by
    :func:`test_the_diff_compares_the_DOCUMENT_and_repairs_a_tampered_row`.
    """
    exp = _with_runs("parity: an unversioned save of a changed document", 2)
    target = exp.sorted_runs()[0]
    before = _full_rows(exp.id)
    rev_before = target.rev

    target.label = "renamed without a version bump"
    target.draft = {"fields": {"context.environment": _envelope("SYNTHETIC-ENV")}}

    with pytest.raises(repo.DurableWriteConflict):
        exp.save()  # the UNVERSIONED primitive, against a document that changed

    assert target.rev == rev_before, "the premise moved: save() bumped a run's rev"
    # NOTHING WAS WRITTEN. Not the changed run, not its sibling, not a stamp.
    assert _full_rows(exp.id) == before

    # And the rows still describe the document the DATABASE holds.
    stored = ws.load_experiment(exp.id)
    assert stored is not None
    assert_parity(stored)
    assert stored.get_run(target.id).label != "renamed without a version bump"


@real_engine
def test_the_diff_compares_the_DOCUMENT_and_repairs_a_tampered_row(workspace):
    """WHY ``Q_EXPERIMENT_RUN_ROWS`` SELECTS ``state``, PROVEN AT A REACHABLE INPUT.

    Selecting the whole document on every save is not free, and its stated
    justification — an unversioned save changing a run without moving its ``rev`` —
    turns out to be unreachable against a real engine (see the test above: the
    compare-and-swap refuses that write). This is the reachable case, and it is the
    one a shadow table actually has to survive: a row whose DOCUMENT has drifted
    while every promoted column still matches.

    A diff comparing only ``(ordinal, rev, generation)`` would see nothing to do and
    the drift would persist forever, invisibly, because no read path in this
    application consults the table. The repair rides in on a BYTE-IDENTICAL re-save,
    which is admitted by clause 3 and needs no new SQL.

    The tampering is done by a TEST statement, out of band, which is exactly the
    provenance such drift would have: a migration, an operator, or a future second
    writer — never this application, whose only write is the one under test.
    """
    exp = _with_runs("parity: a tampered document", 2)
    target = exp.sorted_runs()[0]
    before = _full_rows(exp.id)

    tampered = _execute(Q_TEST_TAMPER_WITH_A_RUN_LABEL, (target.id,))
    assert tampered == 1
    drifted = _full_rows(exp.id)
    assert drifted[target.id][2]["label"] == "TAMPERED-OUT-OF-BAND"
    # The promoted columns are untouched, which is the whole point of the case.
    assert drifted[target.id][1:2] == before[target.id][1:2]
    assert drifted[target.id][3:6] == before[target.id][3:6]
    with pytest.raises(AssertionError):
        assert_parity(exp)

    exp.save()  # byte-identical: admitted by clause 3, and the diff repairs the row

    repaired = _full_rows(exp.id)
    assert repaired[target.id][2] == target.to_state()
    assert repaired[target.id][6] != drifted[target.id][6], "the drifted row was skipped"
    # The sibling, whose document did NOT drift, was not rewritten.
    sibling = exp.sorted_runs()[1]
    assert repaired[sibling.id] == before[sibling.id]
    assert_parity(exp)


# =============================================================================
# 5. THE CONTROLS — without these the whole stage is worthless
# =============================================================================


@real_engine
def test_the_parity_oracle_FAILS_when_a_row_is_mutated_out_of_band(workspace):
    """THE NEGATIVE CONTROL. A suite that can only go green proves nothing.

    Every assertion above is worth exactly as much as this one: the oracle must be
    able to FAIL. One statement moves every ordinal by one behind the application's
    back — a change the application can never notice, because no read path in this
    codebase consults ``isaac_runs`` — and the oracle must go red on the next call.

    It then repairs the damage through the ordinary write path and confirms the
    oracle goes green again, so a later test in the same database is not left
    reading a table this one broke.
    """
    exp = _with_runs("parity: the negative control", 3)
    assert_parity(exp)

    changed = _execute(Q_TEST_SHIFT_ORDINALS, (exp.id,))
    assert changed == 3, changed

    with pytest.raises(AssertionError) as failure:
        assert_parity(exp)
    assert "isaac_runs disagrees with the experiment document" in str(failure.value)

    # REPAIR, through the application rather than by hand: an unversioned re-save
    # rewrites the rows the diff now sees as different.
    exp.save()
    assert_parity(exp)


@real_engine
def test_the_parity_oracle_FAILS_when_a_row_is_deleted_out_of_band(workspace):
    """THE SECOND CONTROL, for the other direction.

    The ordinal control proves the oracle notices a row that is WRONG. This proves
    it notices a row that is GONE — a different failure, and the one a projection
    that only ever upserts would produce.
    """
    exp = _with_runs("parity: the deletion control", 2)
    assert_parity(exp)

    removed = _execute(Q_TEST_DELETE_RUNS_OF, (exp.id,))
    assert removed == 2, removed
    assert _observed(exp.id) == []

    with pytest.raises(AssertionError):
        assert_parity(exp)

    exp.save()
    assert_parity(exp)


# =============================================================================
# 6. the byte-identical re-save: is it the backfill primitive it looks like?
# =============================================================================


@real_engine
def test_a_byte_identical_re_save_is_accepted_and_rewrites_the_run_rows(workspace):
    """THE CLAIM UNDER TEST, read from statement text and never executed until now.

    ``Q_UPSERT_EXPERIMENT``'s third clause — ``isaac_experiments.state =
    EXCLUDED.state`` — admits a re-offer of a BYTE-IDENTICAL document at an equal
    rev. If that is true against a real engine, then ``persist`` reaches
    ``if accepted:`` and runs ``_write_run_rows``, which means an unchanged re-save
    is an IN-PATH REPAIR for the run rows: it needs no new SQL, no new route and no
    new statement, and it can rebuild a row set that has gone missing.

    THE PROOF IS CONSTRUCTED SO IT CANNOT PASS VACUOUSLY. The rows are DELETED out
    of band first, so "the rows are correct afterwards" can only be true if the
    re-save actually wrote them — a run of this test against a build where clause 3
    refused would leave an empty table and fail.

    Three layers, deliberately, because they can fail independently:
      1. the SQL clause itself: the same document offered twice, ``rowcount == 1``;
      2. the STORE: ``persist`` of an unchanged experiment issues ``Q_UPSERT_RUN``
         per run and restores the row set;
      3. the IN-PATH primitive: a plain ``exp.save()`` — what an application caller
         actually has — does the same thing.
    """
    exp = _with_runs("parity: the byte-identical re-save", 3)
    expected_rows = _expected(exp)
    payload = json.dumps(exp.to_state(), sort_keys=True)

    # ── 1. THE CLAUSE. The same bytes, at the same rev, offered again. ──────────
    with dbw.write_transaction(os.environ) as (cursor, policy):
        cursor.execute(policy.check(repo.Q_UPSERT_EXPERIMENT), (exp.id, payload))
        assert cursor.rowcount == 1, (
            "a byte-identical re-offer was REFUSED: clause 3 of Q_UPSERT_EXPERIMENT "
            "does not behave as its comment claims, and the run-row backfill "
            "primitive this test documents does not exist"
        )

    # ── 2. THE STORE. Rows deleted behind its back; an unchanged persist repairs. ─
    assert _execute(Q_TEST_DELETE_RUNS_OF, (exp.id,)) == 3
    assert _observed(exp.id) == []

    store, log = _recording_store()
    store.persist(exp)  # no DurableWriteConflict: the document is unchanged

    issued = [sql for sql, _ in log]
    assert issued.count(repo.Q_UPSERT_RUN) == 3, issued
    assert repo.Q_EXPERIMENT_RUN_ROWS in issued
    assert _observed(exp.id) == expected_rows
    assert_parity(exp)

    # ── 3. THE IN-PATH PRIMITIVE. What a caller actually has. ───────────────────
    assert _execute(Q_TEST_DELETE_RUNS_OF, (exp.id,)) == 3
    assert _observed(exp.id) == []
    reloaded = ws.load_experiment(exp.id)
    assert reloaded is not None
    before_rev = reloaded.rev
    reloaded.save()
    assert reloaded.rev == before_rev, "a plain save() moved the experiment rev"
    assert_parity(reloaded)
    assert _observed(exp.id) == expected_rows

    # AND IT IS A REPAIR, NOT A REWRITE OF HISTORY: the document is untouched.
    with dbw.write_transaction(os.environ) as (cursor, policy):
        cursor.execute(policy.check(repo.Q_ONE_EXPERIMENT), (exp.id,))
        stored = _as_document(cursor.fetchone()[0])
    assert stored == json.loads(payload)


@real_engine
def test_a_byte_identical_re_save_of_a_run_less_experiment_still_holds(workspace):
    """The same clause, at the boundary the ``%s::text[]`` cast exists for.

    A re-save of an experiment with NO runs reaches ``_write_run_rows`` with an
    empty desired set. Nothing should be written and nothing should be deleted —
    but the SELECT still runs, and this is the case where a mistake would produce a
    type error rather than a wrong answer.
    """
    exp = _new_experiment("parity: a run-less byte-identical re-save")
    store, log = _recording_store()
    store.persist(exp)
    issued = [sql for sql, _ in log]
    assert repo.Q_EXPERIMENT_RUN_ROWS in issued
    assert repo.Q_UPSERT_RUN not in issued
    assert repo.Q_DELETE_ABSENT_RUNS not in issued
    assert _observed(exp.id) == []


@real_engine
def test_the_delete_of_the_last_run_binds_the_empty_text_array(workspace):
    """``Q_DELETE_ABSENT_RUNS``' ``%s::text[]`` CAST, at the one input that needs it.

    Deleting the LAST run passes an EMPTY id list. An empty array literal carries no
    element type for the server to infer, whichever of psycopg2's renderings it
    produces, so without the explicit cast this is a type error on the one save that
    matters most. The machine the cast was written on had no PostgreSQL and no
    psycopg2; this is where the precaution stops being unmeasured.
    """
    exp = _with_runs("parity: the empty array", 1)
    assert len(_observed(exp.id)) == 1

    exp.runs = []
    # THE REV IS BUMPED BY HAND, and that is not a shortcut around anything. The
    # recording store is needed to observe the PARAMETER, so this cannot go through
    # ``save_versioned`` (which builds its own store) — and a bare ``persist`` of a
    # changed document at an unchanged rev is REFUSED by the compare-and-swap, as
    # the unversioned-save test above measures. ``max(rev, disk_rev) + 1`` is
    # exactly what ``save_versioned`` would have offered.
    exp.rev += 1
    store, log = _recording_store()
    store.persist(exp)

    issued = [sql for sql, params in log]
    assert repo.Q_DELETE_ABSENT_RUNS in issued
    empty_binding = [
        params for sql, params in log if sql == repo.Q_DELETE_ABSENT_RUNS
    ]
    assert empty_binding == [(exp.id, [])], empty_binding
    assert _observed(exp.id) == []
    assert_parity(exp)


# =============================================================================
# 7. what the ORACLE itself is, asserted where a reader will find it
# =============================================================================


def test_this_suite_reads_isaac_runs_only_as_a_test_and_never_on_the_apps_behalf():
    """A SCOPE ASSERTION, and it runs even with no engine — it opens nothing.

    ``CLAUDE.md`` §15: the run write is a SHADOW, the document is authoritative, and
    making ``isaac_runs`` a READ SOURCE is a separate, unauthorized decision. This
    file reads the table constantly, and that could be mistaken for exactly the
    change that is not authorized. It is not: every statement here is defined in
    THIS MODULE, none of them is reachable from ``isaac_api``, and the application's
    own enumeration of which statements name the table
    (``test_0002_is_now_written_by_the_write_path_and_by_nothing_else``) is
    unaffected because none of these is a module-level constant of an application
    module.

    Asserted rather than only written down, so a future slice that moves one of
    these statements into the application trips here.
    """
    application_statements = set()
    for module in (dbw, repo):
        for name in dir(module):
            if name.startswith("Q_"):
                application_statements.add(getattr(module, name))
    for sql in (
        Q_TEST_ALL_RUN_ROWS,
        Q_TEST_RUN_ROWS_FOR,
        Q_TEST_SHIFT_ORDINALS,
        Q_TEST_DELETE_RUNS_OF,
        Q_TEST_TAMPER_WITH_A_RUN_LABEL,
    ):
        assert sql not in application_statements, sql
        # ...and each is still bound by the same policy every application
        # statement is: owned tables only, no forbidden verb.
        assert dbw.WriteStatementPolicy().check(sql) == sql

    # The application's read of the table remains the ONE inside the write path.
    assert repo.Q_EXPERIMENT_RUN_ROWS in application_statements


def test_the_oracle_projects_the_same_tuple_the_application_writes():
    """A PURE, ENGINE-FREE CHECK THAT THE ORACLE IS COMPARING THE RIGHT THING.

    ``_expected`` is hand-written here, so it could drift from
    ``experiment_repository._run_row_params`` — the one place a ``Run`` becomes a
    row — and an oracle comparing the wrong projection would agree with the table
    for the wrong reason. This pins the two together WITHOUT a database:
    ``_run_row_params`` is pure and deliberately callable without one.

    ``state`` is compared after a ``json.loads`` because ``_run_row_params``
    serialises with ``sort_keys=True`` for determinism, while the oracle compares
    documents.
    """
    exp = ws.Experiment(
        id="01ABCDEFGHJKMNPQRSTVWXYZ00",
        title="oracle projection",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
    )
    run = ws.Run(
        id="01AAAAAAAAAAAAAAAAAAAAAAAA",
        experiment_id=exp.id,
        label="a run",
        ordinal=3,
        created_utc="2026-01-01T00:00:00Z",
        draft={"fields": {}},
        rev=7,
        generation="gen-fixture",
    )
    exp.runs.append(run)

    run_id, experiment_id, ordinal, state_json, rev, generation = repo._run_row_params(
        exp.id, run
    )
    assert experiment_id == exp.id
    assert _expected(exp) == [
        (run_id, ordinal, json.loads(state_json), rev, generation)
    ]
    # Guard against the oracle silently comparing an aliased document.
    assert json.loads(state_json) == run.to_state()
    assert json.loads(state_json) is not run.to_state()
    assert copy.deepcopy(run.to_state()) == run.to_state()


# =============================================================================
# 8. THE FAKE-DRIVER HALF — only the shapes the existing fake suite does NOT cover
# =============================================================================
#
# `test_experiment_repository.py` §7b already proves, against the in-process fake:
# the row set at four widths, the legacy empty `experiment_id`, the deduped row
# set, the null `record_id`, add/rename/override/remove each writing only what
# moved, the empty `::text[]` parameter, the no-op second save, a drifted promoted
# column being repaired, and — the important one — that a REFUSED upsert issues no
# run statement at all. NONE of that is repeated here. Duplicating it would create
# a second place for the same property to be maintained and a second place for it
# to drift.
#
# TWO SHAPES ARE GENUINELY UNCOVERED THERE and are cheap to cover here. Both are
# FAKE-DRIVER tests: they prove the STATEMENTS and the projected row set under a
# faithful-but-simplified store, and they prove nothing about PostgreSQL. The
# real-engine counterparts above are the authority.
#
# The fake is IMPORTED rather than re-implemented. A second copy of a 190-line
# connection double is exactly how two suites end up disagreeing about what the
# driver does.

from test_experiment_repository import FakeConnection, _connector, _env  # noqa: E402


def _fake_persist(exp, conn=None):
    conn = FakeConnection() if conn is None else conn
    repo.PostgresOrdinaryStore(_env(), connect=_connector(conn)).persist(exp)
    return conn


def _bare_experiment(rid: str = "01ABCDEFGHJKMNPQRSTVWXYZ00") -> "ws.Experiment":
    return ws.Experiment(
        id=rid,
        title="fake-driver fixture",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
    )


def test_FAKE_an_inherited_address_never_reaches_the_projected_run_row():
    """FAKE-DRIVER. The projection half of the inheritance property, with no engine.

    The real-engine test of the same name asserts this against the stored ``jsonb``.
    This one asserts it one layer earlier, in the PARAMETERS the write path sends —
    so a projection that started copying resolved experiment content down into the
    row would fail here even on a machine with no database, which is every
    developer machine in this project.
    """
    exp = _bare_experiment()
    exp.draft = {
        "fields": {"sample.material.name": _envelope("SYNTHETIC-FIXTURE-MATERIAL")},
        "tags": ["synthetic-campaign"],
    }
    run = exp.add_run(label="inherits everything")

    conn = _fake_persist(exp)
    _experiment_id, _ordinal, state, _rev, _generation = conn.runs[run.id]
    assert state["draft"] == {} and state["overrides"] == {}
    blob = json.dumps(state, sort_keys=True)
    assert "SYNTHETIC-FIXTURE-MATERIAL" not in blob
    assert "synthetic-campaign" not in blob
    # ...while the run genuinely inherits, computed on read.
    assert exp.resolve_run(run)[ws.field_address("sample.material.name")].value == (
        "SYNTHETIC-FIXTURE-MATERIAL"
    )


def test_FAKE_hydration_issues_no_statement_naming_isaac_runs(workspace):
    """FAKE-DRIVER. The read half of the pod-restart property, stated as a shape.

    ``hydrate`` reads ``isaac_experiments`` and writes FILES. The real-engine test
    asserts the OUTCOME — not one run row moved. This asserts the MECHANISM: the
    hydration transaction issues exactly one application statement and it is
    ``Q_ALL_EXPERIMENTS``. A future hydration that started "helpfully" rebuilding
    run rows would be a second, unowned write path into the shadow table, and it
    would fail here.
    """
    exp = _bare_experiment()
    exp.add_run(label="a run the row set already holds")
    state = exp.to_state()

    conn = FakeConnection(rows=[(exp.id, json.dumps(state))])
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))
    before = dict(conn.runs)
    store.hydrate()

    assert [sql for sql, _ in conn.statements if "isaac_runs" in sql.lower()] == []
    assert repo.Q_RUN_TABLE_PRESENT not in [sql for sql, _ in conn.statements]
    assert conn.runs == before, "hydration wrote to the shadow table"
