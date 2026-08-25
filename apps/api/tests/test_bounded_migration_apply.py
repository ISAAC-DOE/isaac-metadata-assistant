"""``--through`` — applying migrations UP TO AND INCLUDING a named version.

WHY THIS FILE EXISTS, MEASURED RATHER THAN ARGUED
=================================================
The external operator ask was: apply ``0003_revisions`` and ``0004_submissions``
to the hosted database, and do **not** apply ``0005_run_projection``, which the
project owner has not approved. With the shipped tooling those two instructions
were **not jointly satisfiable** — ``scripts/db_migrate.py`` exposed ``--plan``
and ``--apply`` and nothing else, ``db_migrate.load_migrations`` globbed every
``*.sql`` in the migrations directory, and ``0005_run_projection.sql`` is
committed — so ``--apply`` landed three migrations or none, and the addendum
recorded the operator's DO row as **BLOCKED** rather than pending.

``--through`` is what unblocks it. These tests exist because it is operator
tooling pointed at a database holding 30 production-derived records, so the
interesting failures are not "it crashed" but "it quietly applied one more than
the operator was approved to apply", and "the document the operator diffs
against no longer matches what the tool prints".

WHAT THESE TESTS ARE, AND WHAT THEY ARE NOT
===========================================
They drive ``scripts/db_migrate.py::main`` and the runner's selector in process,
against the same ``FakeConnection`` the repository tests use. They establish
which versions are selected, which statements are issued, what is printed to the
byte, and what the exit code says.

They do **not** establish that any of it works against PostgreSQL. Nothing here
opens a connection and no migration is applied anywhere. The real-engine half is
``.github/workflows/ci.yml``'s ``postgres-migration`` job, which applies
``0001``–``0004`` through the bound against a ``postgres:18`` service container
and asserts ``isaac_run_projection`` does not exist afterwards — which is
precisely the operator's situation.

THE DRIFT GUARD IS THE POINT OF THE LAST SECTION
================================================
``docs/migration-approval-packet-0003.md`` §9 quotes the command's output as the
thing an operator diffs against. A test that merely asserted the tool's output
against a literal in this file would let the packet and the tool drift apart
silently, which is the failure that produced the correction the packet now
carries. So the last section reads the committed documents and requires the
strings to appear in them verbatim.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import isaac_api.db_migrate as dbm
import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
from test_experiment_repository import FakeConnection, _connector, _env

_SCRIPT = Path(repo.__file__).resolve().parents[3] / "scripts" / "db_migrate.py"
_REPO_ROOT = Path(repo.__file__).resolve().parents[3]

#: Every committed forward version, in the order the runner applies them. Read
#: from disk rather than hard-coded: a sixth migration must not make this file
#: silently assert something about a five-migration world.
ALL_VERSIONS = [m.version for m in dbm.load_migrations()]

#: The boundary the operator ask needs. Named once so the intent is legible.
BOUNDARY = "0004_submissions"

#: What that boundary withholds. Derived, for ALL_VERSIONS' reason.
WITHHELD = ALL_VERSIONS[ALL_VERSIONS.index(BOUNDARY) + 1 :]


@pytest.fixture()
def cli():
    """The operator script, imported by path — ``scripts/`` is not a package."""
    spec = importlib.util.spec_from_file_location("db_migrate_cli", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def pg_env(monkeypatch):
    """A configured-looking environment. No connection is made from it."""
    for key, value in _env().items():
        monkeypatch.setenv(key, value)


def _install(monkeypatch, conn: FakeConnection) -> None:
    """Route the write path at an in-process double.

    ``db_write.connect_psycopg2`` is monkeypatched rather than passed as
    ``connect=``: the CLI does not thread a connector through, which is exactly
    why ``write_transaction`` resolves the default at call time.
    """
    monkeypatch.setattr(dbw, "connect_psycopg2", _connector(conn))


def _refuse_to_connect(monkeypatch) -> None:
    def never(_env):  # pragma: no cover - reaching this IS the failure
        raise AssertionError("a connection was opened despite a bad --through")

    monkeypatch.setattr(dbw, "connect_psycopg2", never)


def _lines(capsys) -> list[str]:
    captured = capsys.readouterr()
    return [line for line in (captured.out + captured.err).splitlines() if line]


# =============================================================================
# 1. the selector — a prefix, exactly, or a refusal
# =============================================================================


@pytest.mark.parametrize("index", range(len(ALL_VERSIONS)))
def test_through_selects_the_prefix_ending_at_the_named_version(index):
    boundary = ALL_VERSIONS[index]
    selected, withheld = dbm.select_through(dbm.load_migrations(), boundary)
    assert [m.version for m in selected] == ALL_VERSIONS[: index + 1]
    assert withheld == ALL_VERSIONS[index + 1 :]


def test_through_none_is_the_unbounded_set_and_withholds_nothing():
    """The behaviour the runner has always had, unchanged by the new parameter."""
    selected, withheld = dbm.select_through(dbm.load_migrations(), None)
    assert [m.version for m in selected] == ALL_VERSIONS
    assert withheld == []


def test_the_selection_is_ALWAYS_a_contiguous_prefix_whatever_the_boundary():
    """The property that makes out-of-order and skip-one unexpressible.

    Not a restatement of the parametrized case above: this asserts that across
    EVERY accepted boundary the result is ``ALL_VERSIONS[:n]`` for some ``n``,
    so there is no argument to this function that yields a gap, a reordering, or
    a single-version pick. That matters because every migration here declares a
    foreign key into a table an earlier one creates, and because the presence
    checks inside ``0005`` are sound only if everything before it ran.
    """
    prefixes = {
        tuple(m.version for m in dbm.select_through(dbm.load_migrations(), v)[0])
        for v in ALL_VERSIONS
    }
    assert prefixes == {tuple(ALL_VERSIONS[: n + 1]) for n in range(len(ALL_VERSIONS))}


def test_an_unknown_version_is_refused_and_the_refusal_names_what_it_knows():
    with pytest.raises(dbw.WriteRefused) as exc:
        dbm.select_through(dbm.load_migrations(), "0009_does_not_exist")
    message = str(exc.value)
    assert "0009_does_not_exist" in message
    for version in ALL_VERSIONS:
        assert version in message, f"the refusal did not name {version}"
    assert "Nothing was applied" in message


@pytest.mark.parametrize(
    "typo",
    [
        "0004",  # a prefix of the real stem
        "submissions",  # a substring
        "0004_submissions ",  # a trailing space
        " 0004_submissions",
        "0004_SUBMISSIONS",  # wrong case
        "0004_submissions.sql",  # the filename rather than the stem
        "0004_*",  # a glob
        "",  # empty
    ],
)
def test_a_near_miss_is_REFUSED_rather_than_guessed(typo):
    """A typo must never quietly apply everything, and never quietly apply nothing.

    Both silent outcomes are worse than a refusal here: one applies an
    unapproved migration to a database holding production-derived records, and
    the other reports success over a database nothing happened to.
    """
    with pytest.raises(dbw.WriteRefused):
        dbm.select_through(dbm.load_migrations(), typo)


@pytest.mark.parametrize(
    "stem", sorted(p.name[: -len(".sql")] for p in dbm.MIGRATIONS_DIR.glob("*.rollback.sql"))
)
def test_a_rollback_FILE_can_never_be_a_BOUNDARY(stem):
    """``--through`` is forward-only and cannot be pointed at a rollback.

    ``load_migrations`` excludes ``*.rollback.sql`` by suffix, so a rollback
    stem is not in the set the selector matches against and naming one refuses.
    This is asserted for every committed rollback file rather than for one,
    because the guarantee is about the suffix rule and not about a filename.
    """
    assert stem.endswith(".rollback")
    with pytest.raises(dbw.WriteRefused):
        dbm.select_through(dbm.load_migrations(), stem)


def test_load_migrations_never_returns_a_rollback_file_bounded_or_not():
    for boundary in [None, *ALL_VERSIONS]:
        for migration in dbm.load_migrations(through=boundary):
            assert not migration.version.endswith(".rollback")
            assert not migration.path.name.endswith(".rollback.sql")


def test_a_BOUND_DOES_NOT_HIDE_A_BROKEN_LATER_MIGRATION(tmp_path):
    """Every file is still read and parsed; the bound only selects.

    A bound applied at load time would let a syntactically unreadable migration
    sit behind the boundary undetected until the day someone widened the bound.
    """
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "0001_ok.sql").write_text(
        "CREATE TABLE IF NOT EXISTS isaac_experiments (a text)", encoding="utf-8"
    )
    # A dollar-quoted body, which `split_statements` refuses outright.
    (directory / "0002_broken.sql").write_text(
        "DO $$ BEGIN END $$", encoding="utf-8"
    )
    with pytest.raises(dbw.WriteRefused) as exc:
        dbm.load_migrations(directory, through="0001_ok")
    assert "dollar-quoted" in str(exc.value)


def test_a_boundary_naming_nothing_in_an_EMPTY_directory_refuses(tmp_path):
    """Not "nothing to do" — there is no such version, and that is the answer."""
    empty = tmp_path / "none"
    empty.mkdir()
    assert dbm.load_migrations(empty) == []
    with pytest.raises(dbw.WriteRefused):
        dbm.load_migrations(empty, through=BOUNDARY)


# =============================================================================
# 2. a bounded PLAN — the thing the operator checks against the packet
# =============================================================================


def test_a_bounded_plan_prints_the_prefix_and_NAMES_WHAT_IT_WITHHOLDS(
    cli, pg_env, monkeypatch, capsys
):
    conn = FakeConnection(applied=("0001_experiments", "0002_runs"))
    _install(monkeypatch, conn)

    assert cli.main(["--plan", "--through", BOUNDARY]) == 0

    assert _lines(capsys) == [
        "pending through 0004_submissions: 0003_revisions, 0004_submissions",
        "withheld by --through 0004_submissions: 0005_run_projection",
    ]
    # A PLAN APPLIES NOTHING. The bookkeeping table may be created to be read;
    # no migration statement may be issued.
    issued = [sql for sql, _ in conn.statements]
    assert dbm.Q_RECORD_VERSION not in issued
    assert not any("CREATE TABLE" in sql and "isaac_schema_migrations" not in sql for sql in issued)


def test_the_bounded_plan_and_the_bounded_apply_NAME_THE_SAME_VERSIONS(
    cli, pg_env, monkeypatch, capsys
):
    """The plan an operator reads must be the apply they get.

    Asserted as an equality between the two outputs rather than as two separate
    literals, because two literals can be edited apart.
    """
    conn = FakeConnection(applied=("0001_experiments", "0002_runs"))
    _install(monkeypatch, conn)
    cli.main(["--plan", "--through", BOUNDARY])
    planned = _lines(capsys)

    conn = FakeConnection(applied=("0001_experiments", "0002_runs"))
    _install(monkeypatch, conn)
    cli.main(["--apply", "--through", BOUNDARY])
    applied = _lines(capsys)

    assert planned[0].replace("pending through", "applied through") == applied[0]
    assert planned[1] == applied[1]


def test_an_empty_bounded_plan_still_says_what_it_withheld(
    cli, pg_env, monkeypatch, capsys
):
    """`(none)` is not the whole answer — the withheld line is the other half."""
    conn = FakeConnection(applied=tuple(ALL_VERSIONS[: ALL_VERSIONS.index(BOUNDARY) + 1]))
    _install(monkeypatch, conn)
    assert cli.main(["--plan", "--through", BOUNDARY]) == 0
    assert _lines(capsys) == [
        "pending through 0004_submissions: (none)",
        "withheld by --through 0004_submissions: 0005_run_projection",
    ]


# =============================================================================
# 3. a bounded APPLY — the boundary lands, the next one does not
# =============================================================================


def test_a_bounded_apply_applies_the_prefix_and_NOTHING_AFTER_IT(
    cli, pg_env, monkeypatch, capsys
):
    conn = FakeConnection(applied=("0001_experiments", "0002_runs"))
    _install(monkeypatch, conn)

    assert cli.main(["--apply", "--through", BOUNDARY]) == 0

    assert _lines(capsys) == [
        "applied through 0004_submissions: 0003_revisions, 0004_submissions",
        "withheld by --through 0004_submissions: 0005_run_projection",
    ]
    # THE BOOKKEEPING, WHICH IS THE PART A LATER RUN DEPENDS ON.
    assert conn.applied == {
        "0001_experiments",
        "0002_runs",
        "0003_revisions",
        "0004_submissions",
    }
    for version in WITHHELD:
        assert version not in conn.applied


def test_the_BOUNDARY_VERSIONS_TABLES_ARE_CREATED_AND_THE_NEXT_ONES_ARE_NOT(
    cli, pg_env, monkeypatch
):
    """Read off the statements, not off the printed summary.

    A tool that printed the right thing and issued the wrong statements would
    pass the output assertions above. ``isaac_submission_runs`` is ``0004``'s
    table and must appear; ``isaac_run_projection`` is ``0005``'s and must not
    appear in a single statement.
    """
    conn = FakeConnection(applied=("0001_experiments", "0002_runs"))
    _install(monkeypatch, conn)
    cli.main(["--apply", "--through", BOUNDARY])

    issued = " ".join(sql for sql, _ in conn.statements)
    assert "isaac_experiment_revisions" in issued  # 0003
    assert "isaac_submission_runs" in issued  # 0004, the boundary
    assert "isaac_run_projection" not in issued, "0005's table was touched"


def test_a_bounded_apply_run_TWICE_is_a_no_op_and_still_withholds(
    cli, pg_env, monkeypatch, capsys
):
    conn = FakeConnection(applied=("0001_experiments", "0002_runs"))
    _install(monkeypatch, conn)

    assert cli.main(["--apply", "--through", BOUNDARY]) == 0
    capsys.readouterr()
    before = set(conn.applied)

    assert cli.main(["--apply", "--through", BOUNDARY]) == 0
    assert _lines(capsys) == [
        "nothing to apply through 0004_submissions "
        "(every migration up to it is already recorded)",
        "withheld by --through 0004_submissions: 0005_run_projection",
    ]
    assert conn.applied == before, "the second bounded apply changed the bookkeeping"


def test_a_boundary_that_is_ALREADY_APPLIED_is_a_no_op(
    cli, pg_env, monkeypatch, capsys
):
    """Distinct from the twice case: here nothing in the prefix is pending at all."""
    conn = FakeConnection(applied=tuple(ALL_VERSIONS))
    _install(monkeypatch, conn)
    assert cli.main(["--apply", "--through", BOUNDARY]) == 0
    assert _lines(capsys)[0] == (
        "nothing to apply through 0004_submissions "
        "(every migration up to it is already recorded)"
    )
    assert conn.applied == set(ALL_VERSIONS)


def test_a_bounded_apply_THEN_AN_UNBOUNDED_ONE_applies_exactly_what_was_withheld(
    cli, pg_env, monkeypatch, capsys
):
    """The bookkeeping claim, stated as the sequence an operator actually runs.

    The bound is an argument to one invocation and is never persisted, so a
    later unbounded run must pick up precisely what the bound left alone — no
    more (it must not re-apply the prefix) and no less (it must not have lost
    track of the remainder).
    """
    conn = FakeConnection(applied=("0001_experiments", "0002_runs"))
    _install(monkeypatch, conn)

    cli.main(["--apply", "--through", BOUNDARY])
    capsys.readouterr()

    assert cli.main(["--apply"]) == 0
    assert _lines(capsys) == ["applied: 0005_run_projection"]
    assert conn.applied == set(ALL_VERSIONS)


def test_a_bounded_apply_does_NOT_bypass_the_write_statement_policy(
    cli, pg_env, monkeypatch, tmp_path, capsys
):
    """The reason "just use psql" was rejected must not be reintroduced here.

    ``through`` narrows which files are considered and changes nothing about how
    their statements are checked, so a forbidden statement inside the selected
    prefix still refuses. Exercised over a staged directory rather than the
    committed files, because no committed migration contains a ``DROP`` and
    adding one to prove this would be the defect.
    """
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "0001_fine.sql").write_text(
        "CREATE TABLE IF NOT EXISTS isaac_experiments (a text)", encoding="utf-8"
    )
    (directory / "0002_forbidden.sql").write_text(
        "DROP TABLE isaac_experiments", encoding="utf-8"
    )
    conn = FakeConnection()
    _install(monkeypatch, conn)

    with pytest.raises(dbw.WriteRefused):
        dbm.migrate(_env(), directory=directory, through="0002_forbidden")
    assert "0002_forbidden" not in conn.applied

    # And the same statement is equally refused when it is the whole selection.
    with pytest.raises(dbw.WriteRefused):
        dbm.migrate(_env(), directory=directory)


# =============================================================================
# 4. refusals from the console — loud, and before anything is opened
# =============================================================================


def test_an_unknown_version_refuses_WITHOUT_OPENING_A_CONNECTION(
    cli, pg_env, monkeypatch, capsys
):
    _refuse_to_connect(monkeypatch)
    assert cli.main(["--apply", "--through", "0004_submision"]) == 3
    out = capsys.readouterr()
    assert out.out == "", "a refusal printed something on stdout"
    assert out.err.startswith("refused: no migration is named '0004_submision'")


def test_a_typo_refuses_EVEN_WITH_NO_DATABASE_CONFIGURED(cli, monkeypatch, capsys):
    """Exit 3, not 2 — the bound is validated before the environment gate.

    So an operator can check the spelling of a boundary on a laptop, and a typo
    can never reach the point where the only thing standing between it and the
    hosted database is ``PGHOST`` being set.
    """
    for key in ("PGHOST", "PGDATABASE"):
        monkeypatch.delenv(key, raising=False)
    _refuse_to_connect(monkeypatch)
    assert cli.main(["--apply", "--through", "nonsense"]) == 3
    assert "refused:" in capsys.readouterr().err


def test_a_ROLLBACK_STEM_from_the_console_is_a_refusal_not_a_rollback(
    cli, pg_env, monkeypatch, capsys
):
    _refuse_to_connect(monkeypatch)
    assert cli.main(["--apply", "--through", "0003_revisions.rollback"]) == 3
    assert "no migration is named '0003_revisions.rollback'" in capsys.readouterr().err


def test_there_is_still_no_way_to_ROLL_BACK_from_this_command(cli):
    """The flag that must not exist, pinned so it cannot arrive by accident."""
    for forbidden in ("--rollback", "--down", "--downgrade", "--undo", "--only"):
        with pytest.raises(SystemExit) as exc:
            cli.main([forbidden])
        assert exc.value.code == 2, f"{forbidden} was accepted"


# =============================================================================
# 5. the interaction with the documented rollback order
# =============================================================================


def test_a_bounded_apply_leaves_NO_BOOKKEEPING_ROW_FOR_A_WITHHELD_VERSION(
    cli, pg_env, monkeypatch
):
    """Why this is the rollback-order question, stated precisely.

    Each rollback file deletes its OWN ``isaac_schema_migrations`` row, and the
    documented order is children before parents across files. After a bounded
    apply the withheld versions have no row and no table, so their rollback
    files are irrelevant rather than half-needed — and the wrong-order refusal
    that protects the applied ones is unchanged, because it comes from real
    foreign keys between tables that exist.

    The refusal itself is an engine property and is proved in CI against
    ``postgres:18``; what is provable here is the bookkeeping state it acts on.
    """
    conn = FakeConnection(applied=("0001_experiments", "0002_runs"))
    _install(monkeypatch, conn)
    cli.main(["--apply", "--through", BOUNDARY])

    for version in WITHHELD:
        assert version not in conn.applied
        # And its rollback file still exists, unread by the runner.
        assert (dbm.MIGRATIONS_DIR / f"{version}.rollback.sql").is_file()


def test_every_forward_migration_still_has_a_committed_rollback_beside_it():
    """A bound must not create a version that can be applied and not undone."""
    for version in ALL_VERSIONS:
        assert (
            dbm.MIGRATIONS_DIR / f"{version}.rollback.sql"
        ).is_file(), f"{version} has no rollback file"


# =============================================================================
# 6. UNBOUNDED output is byte-identical, and the PACKET quotes what the tool prints
# =============================================================================


def test_unbounded_output_is_UNCHANGED_to_the_byte(cli, pg_env, monkeypatch, capsys):
    """Every packet and CI step quotes these three strings. Adding a bound must
    not have reworded the unbounded case even slightly."""
    conn = FakeConnection()
    _install(monkeypatch, conn)
    assert cli.main(["--plan"]) == 0
    assert _lines(capsys) == ["pending: " + ", ".join(ALL_VERSIONS)]

    assert cli.main(["--apply"]) == 0
    assert _lines(capsys) == ["applied: " + ", ".join(ALL_VERSIONS)]

    assert cli.main(["--apply"]) == 0
    assert _lines(capsys) == ["nothing to apply (every migration is already recorded)"]


#: The four lines ``docs/migration-approval-packet-0003.md`` §9 tells the operator
#: to expect, and the command that produces them. Held here as data so the
#: assertion below can be an equality against BOTH the tool and the document.
PACKET_COMMAND = "python scripts/db_migrate.py --apply --through 0004_submissions"
PACKET_PLAN_COMMAND = "python scripts/db_migrate.py --plan --through 0004_submissions"
PACKET_PLAN_OUTPUT = [
    "pending through 0004_submissions: 0003_revisions, 0004_submissions",
    "withheld by --through 0004_submissions: 0005_run_projection",
]
PACKET_APPLY_OUTPUT = [
    "applied through 0004_submissions: 0003_revisions, 0004_submissions",
    "withheld by --through 0004_submissions: 0005_run_projection",
]

_OPERATOR_DOCS = (
    "docs/migration-approval-packet-0003.md",
    "docs/dean-operator-addendum-2026-08-25.md",
)


def test_the_tool_prints_EXACTLY_what_the_packet_tells_the_operator_to_expect(
    cli, pg_env, monkeypatch, capsys
):
    conn = FakeConnection(applied=("0001_experiments", "0002_runs"))
    _install(monkeypatch, conn)
    cli.main(["--plan", "--through", BOUNDARY])
    assert _lines(capsys) == PACKET_PLAN_OUTPUT

    conn = FakeConnection(applied=("0001_experiments", "0002_runs"))
    _install(monkeypatch, conn)
    cli.main(["--apply", "--through", BOUNDARY])
    assert _lines(capsys) == PACKET_APPLY_OUTPUT


@pytest.mark.parametrize("relative", _OPERATOR_DOCS)
def test_the_operator_documents_QUOTE_those_exact_lines(relative):
    """The half that stops the packet and the tool drifting apart.

    The test above pins the tool to a literal in this file; on its own that
    would let the document say something else. This one requires the same
    literal to appear verbatim in the documents an operator actually reads, so
    changing the output without changing the instruction fails here.
    """
    text = (_REPO_ROOT / relative).read_text(encoding="utf-8")
    for line in [PACKET_COMMAND, *PACKET_PLAN_OUTPUT, *PACKET_APPLY_OUTPUT]:
        assert line in text, f"{relative} does not quote: {line}"


def test_the_packet_no_longer_tells_the_operator_to_run_the_UNBOUNDED_apply():
    """The correction, pinned in the direction it actually failed.

    §9's instruction used to be a bare ``--apply``, which — once ``0005`` was
    committed — would have applied an unapproved migration to a database holding
    30 production-derived records. The fix is only real if the bounded command is
    the one in the instruction, so the bare form must not reappear as an
    instruction. It may still appear inside a quoted correction or a postcheck,
    which is why this looks for the instruction shape rather than the substring.
    """
    text = (_REPO_ROOT / "docs/migration-approval-packet-0003.md").read_text(
        encoding="utf-8"
    )
    fenced = [
        block
        for block in text.split("```")[1::2]
        if block.lstrip().startswith("bash")
    ]
    apply_lines = [
        line.strip()
        for block in fenced
        for line in block.splitlines()
        if line.strip().startswith("python scripts/db_migrate.py --apply")
    ]
    assert apply_lines, "the packet no longer shows an apply command at all"
    for line in apply_lines:
        assert "--through 0004_submissions" in line, (
            "the packet still instructs a bare unbounded --apply: " + line
        )


#: The sequence ``.github/workflows/ci.yml``'s bounded-apply step walks against a
#: real ``postgres:18``, as ``(argv, ...)`` — reconstructing the hosted database's
#: state with one bound, then running the operator's two commands at another, then
#: the no-op, then the unbounded handoff.
CI_SEQUENCE = [
    ["--plan", "--through", "0002_runs"],
    ["--apply", "--through", "0002_runs"],
    ["--plan", "--through", BOUNDARY],
    ["--apply", "--through", BOUNDARY],
    ["--apply", "--through", BOUNDARY],
    ["--plan"],
    ["--apply"],
]


def test_the_CI_STEPS_LITERALS_are_what_the_tool_ACTUALLY_PRINTS(
    cli, pg_env, monkeypatch, capsys
):
    """The third leg of the drift guard, and the one with no other cover.

    The CI step asserts its output against hard-coded literals inside a shell
    ``[ ... ]`` test. If the tool's wording moved, that step would fail — but
    only on a runner, only in a job that needs a service container, and with a
    shell-quoting error and a real regression looking identical. So the sequence
    is walked here against one stateful double and every line it produces is
    required to appear verbatim in the workflow file.

    This does NOT prove the step passes against PostgreSQL; nothing here opens a
    connection. It proves the step is asserting the strings this tool emits.
    """
    conn = FakeConnection()
    _install(monkeypatch, conn)
    produced: list[str] = []
    for argv in CI_SEQUENCE:
        assert cli.main(argv) == 0, argv
        produced.extend(_lines(capsys))

    # The sequence really did end fully migrated by way of the bound.
    assert conn.applied == set(ALL_VERSIONS)

    workflow = (_REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for line in produced:
        assert line in workflow, f"the workflow does not assert this output: {line}"

    # And the two lines that matter most in that list are present by construction
    # rather than by accident, so a future edit cannot thin the sequence down to
    # the easy cases and still pass.
    assert PACKET_APPLY_OUTPUT[0] in produced
    assert "applied: 0005_run_projection" in produced


def test_the_CI_step_asserts_that_0005s_TABLE_IS_ABSENT(cli):
    """The one assertion the whole feature exists for, pinned in the workflow.

    A future edit could keep every output assertion and quietly drop the check
    that ``isaac_run_projection`` does not exist — which is the only thing that
    distinguishes "the tool printed the right words" from "the unapproved
    migration was not applied".
    """
    workflow = (_REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "THE BOUND LEAKED: isaac_run_projection exists after --through 0004_submissions" in (
        workflow
    ), "the workflow no longer proves 0005's table is absent after a bounded apply"


def test_the_addendum_no_longer_reports_the_DO_row_as_BLOCKED():
    """It was accurately BLOCKED when written; this change is what unblocks it.

    Pinned because the addendum's own discipline is corrections in place, so the
    word ``BLOCKED`` survives in the struck-through record of what was true. The
    assertion is therefore about the DO row, not about the word's absence.
    """
    text = (_REPO_ROOT / "docs/dean-operator-addendum-2026-08-25.md").read_text(
        encoding="utf-8"
    )
    assert "--through" in text, "the addendum does not mention the bounded command"
    assert "UNBLOCKED" in text, "the addendum does not record the DO row as unblocked"
    assert (
        "no invocation of the shipped command that applies `0003` and `0004` while leaving"
        in text
    ), "the addendum no longer records WHY it was blocked"
