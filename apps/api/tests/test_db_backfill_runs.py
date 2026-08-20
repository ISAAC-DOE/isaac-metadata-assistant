"""``scripts/db_backfill_runs.py`` — the operator backfill, driven in process.

WHY THIS FILE EXISTS. The script shipped with ZERO tests, and an independent review
measured four separate defects in it by running it: the documented invocation
(`--dry-run`) errored with exit 2; the "table not present" warning named the wrong
migration and fired on an empty database where nothing had been probed; two of its
printed counts claimed something about the DATABASE that they did not measure; and its
docstring described a Stage-2b gate figure it does not print and cannot compute.

Every one of those is a REPORT defect rather than a data-loss defect, which is exactly
why no test caught them and exactly why they matter: the whole point of this script is
that an operator reads its output and decides whether a gate has been met.

WHAT THESE TESTS ARE AND ARE NOT. They drive `main()` against the same in-process
`FakeConnection` the repository tests use, so they establish which statements are
issued, what is printed, and what the exit code says. They do NOT establish that the
script works against PostgreSQL — nothing here opens a connection, no migration is
applied anywhere, and the script has still never been executed against any real
database.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
import isaac_api.workspace as ws
from test_experiment_repository import FakeConnection, _connector, _env, _exp_with_runs

_SCRIPT = Path(repo.__file__).resolve().parents[3] / "scripts" / "db_backfill_runs.py"


@pytest.fixture()
def backfill():
    """The script, imported by path — `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("db_backfill_runs", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    repo.forget_run_table_presence()
    repo.forget_storage_failure()


def _state(rid: str, *labels: str) -> dict:
    exp = _exp_with_runs(*labels) if labels else _exp_with_runs()
    state = exp.to_state()
    state["id"] = rid
    for run in state.get("runs") or []:
        run["experiment_id"] = rid
    return state


def _install(monkeypatch, conn) -> None:
    store = repo.PostgresOrdinaryStore(_env(), connect=_connector(conn))
    monkeypatch.setattr(repo, "ordinary_store", lambda *a, **k: store)


def _rows(*states) -> FakeConnection:
    return FakeConnection(rows=[(s.get("id"), json.dumps(s)) for s in states])


# ---------------------------------------------------------------------------
# the documented invocation
# ---------------------------------------------------------------------------

def test_the_documented_dry_run_flag_is_accepted(backfill, monkeypatch, capsys):
    """`--dry-run` errored with exit 2 and four committed documents told an operator
    to type it. It is accepted and is a no-op, because a flag meaning "do the
    default" cannot be dangerous and an operator reaching for the safe invocation
    should not be punished for naming it."""
    _install(monkeypatch, _rows(_state("01AAAAAAAAAAAAAAAAAAAAAAAA", "R1")))
    assert backfill.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry run: nothing was written" in out


def test_the_two_flags_contradict_each_other_rather_than_one_winning(backfill):
    """A precedence rule would be a coin flip on whether a write happens."""
    with pytest.raises(SystemExit) as exc:
        backfill.main(["--dry-run", "--apply"])
    assert exc.value.code == 2


def test_no_flag_at_all_is_the_dry_run_and_writes_nothing(backfill, monkeypatch, capsys):
    conn = _rows(_state("01BBBBBBBBBBBBBBBBBBBBBBBB", "R1"))
    _install(monkeypatch, conn)
    assert backfill.main([]) == 0
    assert conn.runs == {}
    assert [sql for sql, _ in conn.statements].count(repo.Q_UPSERT_EXPERIMENT) == 0
    assert "dry run" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# what the report claims
# ---------------------------------------------------------------------------

def test_the_apply_report_counts_persist_calls_and_says_so(backfill, monkeypatch, capsys):
    """THE COUNTS ARE NAMED FOR WHAT THEY ARE.

    They were printed as `projected:` and `runs written:`, both of which claim
    something about the DATABASE. They count `persist` calls that returned without
    raising, and the runs those documents held — which on a deployment missing
    `isaac_runs` is not the same thing at all (see the next test).
    """
    conn = _rows(
        _state("01CCCCCCCCCCCCCCCCCCCCCCCC", "R1", "R2"),
        _state("01DDDDDDDDDDDDDDDDDDDDDDDD"),
    )
    _install(monkeypatch, conn)
    assert backfill.main(["--apply"]) == 0
    out = capsys.readouterr().out
    assert "experiments persisted without error: 2" in out
    assert "runs held by those documents: 2" in out
    assert "refused (a newer writer won): 0" in out
    assert "failed (storage error): 0" in out
    # NEITHER OLD LABEL SURVIVES. They are the exact strings an operator would read
    # as a database claim.
    assert "projected:" not in out
    assert "runs written:" not in out


def test_an_ABSENT_isaac_runs_names_0002_and_not_0005(backfill, monkeypatch, capsys):
    """THE WARNING NAMED THE WRONG MIGRATION, and the mechanism is worth stating.

    `isaac_run_projection` is probed only INSIDE the branch where `isaac_runs` is
    present, so an absent `isaac_runs` leaves the projection unprobed — and the old
    code read only `projection_table_seen()` and told the operator to apply `0005`.
    An operator would have applied the wrong migration and re-run to the same output.
    """
    conn = _rows(_state("01EEEEEEEEEEEEEEEEEEEEEEEE", "R1", "R2"))
    conn.run_table = False
    _install(monkeypatch, conn)
    assert backfill.main(["--apply"]) == 3
    captured = capsys.readouterr()
    assert "isaac_runs was NOT present" in captured.err
    assert "Apply 0002_runs first" in captured.err
    assert "0005" not in captured.err
    # AND NO RUN ROW WAS WRITTEN, which is what makes the old "runs written: 2"
    # a false report rather than a mislabelled one.
    assert conn.runs == {}


def test_an_ABSENT_projection_table_names_0005_and_says_the_rows_ARE_maintained(
    backfill, monkeypatch, capsys
):
    conn = _rows(_state("01FFFFFFFFFFFFFFFFFFFFFFFF", "R1"))
    conn.projection_table = False
    _install(monkeypatch, conn)
    assert backfill.main(["--apply"]) == 3
    captured = capsys.readouterr()
    assert "isaac_run_projection was NOT present" in captured.err
    assert "Apply 0005_run_projection first" in captured.err
    # The distinction that makes the message useful: the rows ARE there.
    assert "rows were maintained" in captured.err
    assert conn.runs


def test_an_EMPTY_database_warns_about_nothing_and_exits_zero(backfill, monkeypatch, capsys):
    """THE FALSE POSITIVE. With `0005` applied and no experiments, the old code
    printed "isaac_run_projection was not present … Apply 0005 first" and exited 3 —
    because nothing had been PROBED, which is a different fact from nothing being
    present. An operator would have applied an already-applied migration."""
    conn = _rows()
    _install(monkeypatch, conn)
    assert backfill.main(["--apply"]) == 0
    captured = capsys.readouterr()
    assert "experiments readable: 0" in captured.out
    assert "nothing was probed and nothing was written" in captured.err
    assert "Apply 0005" not in captured.err
    assert "Apply 0002" not in captured.err


def test_an_UNREADABLE_row_is_reported_and_changes_the_exit_code(
    backfill, monkeypatch, capsys
):
    """A pass that could not read part of the table must not look complete — and this
    count is what decides whether the operator's gate query is being asked about a
    complete pass or an incomplete one."""
    conn = _rows({"id": "01GGGGGGGGGGGGGGGGGGGGGGGG"}, _state("01HHHHHHHHHHHHHHHHHHHHHHHH", "R1"))
    _install(monkeypatch, conn)
    assert backfill.main(["--apply"]) == 4
    out = capsys.readouterr().out
    assert "experiments UNREADABLE (skipped, not projected): 1" in out
    assert "experiments persisted without error: 1" in out


def test_a_LOST_compare_and_swap_is_counted_and_does_not_end_the_pass(
    backfill, monkeypatch, capsys
):
    """Another writer holding a newer document is not this pass's failure — its own
    save projected its own rows. But it IS a non-zero count, so the gate query is not
    yet being asked about a complete pass."""
    first, second = _state("01JJJJJJJJJJJJJJJJJJJJJJJJ", "R1"), _state("01KKKKKKKKKKKKKKKKKKKKKKKK", "R1")
    conn = _rows(first, second)
    conn.refuse_upsert = {"01JJJJJJJJJJJJJJJJJJJJJJJJ"}
    conn.stored = {"01JJJJJJJJJJJJJJJJJJJJJJJJ": first}
    _install(monkeypatch, conn)
    assert backfill.main(["--apply"]) == 0
    out = capsys.readouterr().out
    assert "refused (a newer writer won): 1" in out
    # THE SECOND EXPERIMENT WAS STILL PROJECTED, which is the "does not end the pass"
    # half and the reason the loop catches rather than propagates.
    assert "experiments persisted without error: 1" in out


# ---------------------------------------------------------------------------
# what it must never do
# ---------------------------------------------------------------------------

def test_it_reads_no_projection_table_and_prints_no_gate_figure(backfill, monkeypatch, capsys):
    """INVARIANT 5 OF THE CONTRACT, held from the script's side.

    Adding a read here would make this file `isaac_run_projection`'s FIRST reader —
    which is the Stage-2b decision this script is a precondition for rather than a
    part of. So the gate is a query the operator runs, and this asserts the script
    neither reads the table nor prints the words four documents once said it did.
    """
    conn = _rows(_state("01LLLLLLLLLLLLLLLLLLLLLLLL", "R1"))
    _install(monkeypatch, conn)
    backfill.main(["--apply"])
    captured = capsys.readouterr()
    for sql, _ in conn.statements:
        if "isaac_run_projection" in sql.lower():
            assert sql.lower().startswith("insert into"), sql
    for banned in ("never_projected", "stale:"):
        assert banned not in captured.out and banned not in captured.err


def test_it_prints_no_id_no_title_and_no_document(backfill, monkeypatch, capsys):
    """Counts only. This may be run by an operator against a database seeded with
    production-derived records, so the same rule `db_recon.py` follows applies."""
    rid = "01MMMMMMMMMMMMMMMMMMMMMMMM"
    state = _state(rid, "R1")
    state["title"] = "a title that must not be printed"
    conn = _rows(state)
    _install(monkeypatch, conn)
    backfill.main(["--apply"])
    captured = capsys.readouterr()
    whole = captured.out + captured.err
    assert rid not in whole
    assert "a title that must not be printed" not in whole
    for run in state.get("runs") or []:
        assert run["id"] not in whole


def test_the_filesystem_fallback_is_refused_rather_than_silently_doing_nothing(
    backfill, monkeypatch, capsys
):
    monkeypatch.setattr(repo, "ordinary_store", lambda *a, **k: None)
    assert backfill.main(["--apply"]) == 2
    assert "no durable store" in capsys.readouterr().err


def test_it_names_records_in_no_statement_it_causes(backfill, monkeypatch):
    """`records` holds the production-derived sample. The write path's policy refuses
    any statement naming it, and this asserts the backfill causes none."""
    conn = _rows(_state("01NNNNNNNNNNNNNNNNNNNNNNNN", "R1"))
    _install(monkeypatch, conn)
    backfill.main(["--apply"])
    for sql, _ in conn.statements:
        assert "records" not in sql.lower().split(), sql
    assert "records" not in dbw.OWNED_TABLES
