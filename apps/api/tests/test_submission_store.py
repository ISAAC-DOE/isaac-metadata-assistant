"""The submission write path, its statements, and the two migrations that back it.

WHAT THIS FILE PROVES AND WHAT IT CANNOT, stated first because the difference is
what an approval packet is judged on.

PROVEN HERE: that the committed migration text loads, is create-only, passes the
owned-tables statement policy, and declares the constraints the approval packets
claim; that the rollbacks are unreachable from the application and name only what
their own migration created; that **no statement this application declares ever
UPDATEs or DELETEs a history row** — which IS the append-only guarantee, because
the database cannot provide one; and that the write path's behaviour against a
connection double is what the route depends on.

NOT PROVEN HERE: that the SQL is valid PostgreSQL, that any CHECK rejects what it
claims to reject, that the foreign keys behave as described, or that ``jsonb``
round-trips the documents. No PostgreSQL is involved in this file — the machine
this was written on has none. That half is ``.github/workflows/ci.yml``'s
``postgres-migration`` job against a real ``postgres:18``, and where the two could
disagree, CI is the authority.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import isaac_api.db_migrate as dbm
import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
import isaac_api.submission_store as sstore
import isaac_api.submissions as submissions
import isaac_api.workspace as ws

from submission_fake import (
    FAKE_SUBMITTED_UTC,
    FakeSubmissionConnection,
    fake_env,
    fake_store,
)

BACKEND_SRC = Path(sstore.__file__).resolve().parent
MIGRATIONS = dbm.MIGRATIONS_DIR


# =============================================================================
# 1. the append-only guarantee — an INVENTORY, and it is the whole guarantee
# =============================================================================


def _module_statements() -> dict[str, str]:
    """Every module-level ``Q_*`` string constant in every backend module.

    Parsed from the AST rather than imported, so a constant assembled at run time —
    which is exactly how someone would sneak past a scan over module attributes —
    is not what is examined. It reads the SOURCE, and a statement built from parts
    would show up as a non-``Constant`` value and be reported by
    :func:`test_every_declared_statement_is_a_plain_string_literal`.
    """
    out: dict[str, str] = {}
    for path in sorted(BACKEND_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name) or not target.id.startswith("Q_"):
                    continue
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    out[f"{path.name}:{target.id}"] = value.value
                elif isinstance(value, (ast.JoinedStr, ast.BinOp)):
                    # An f-string or a concatenation. `getattr` the real object so the
                    # scan reasons about the statement that is actually issued.
                    module = __import__(f"isaac_api.{path.stem}", fromlist=["_"])
                    resolved = getattr(module, target.id, None)
                    if isinstance(resolved, str):
                        out[f"{path.name}:{target.id}"] = resolved
    return out


#: Every table whose rows must never be updated or deleted by this application.
_HISTORY_TABLES = (
    "isaac_experiment_revisions",
    "isaac_run_revisions",
    "isaac_revision_changes",
    "isaac_submissions",
    "isaac_submission_runs",
)


def test_no_submission_statement_updates_or_deletes_history():
    """THE APPEND-ONLY GUARANTEE. It is this test, and nothing else.

    The two mechanisms that would make it a DATABASE guarantee are both unavailable
    and both absences are deliberate rather than overlooked:

      * a ``BEFORE UPDATE OR DELETE`` trigger needs a function body, which needs
        dollar quoting, which ``db_migrate.split_statements`` refuses outright
        (proven by ``test_a_dollar_quoted_body_is_REFUSED_rather_than_silently_mangled``);
      * ``REVOKE UPDATE, DELETE`` is refused by ``db_write._FORBIDDEN_KEYWORDS``
        (proven by :func:`test_revoke_really_is_refused_so_the_stated_reason_is_true`).

    So the property is enforced by INVENTORY: every statement this application can
    issue is a module-level constant, and not one of them names a history table
    after ``UPDATE`` or ``DELETE``. That is a real guard over this application's own
    code and it is NOT a guarantee about a psql session, a superuser, or a future
    application. Nothing in this repository may describe these rows as immutable at
    the database level.
    """
    offenders: list[str] = []
    for where, sql in _module_statements().items():
        lowered = " ".join(sql.lower().split())
        for table in _HISTORY_TABLES:
            if table not in lowered:
                continue
            if re.search(rf"\bupdate\s+{table}\b", lowered) or re.search(
                rf"\bdelete\s+from\s+{table}\b", lowered
            ):
                offenders.append(f"{where} -> {sql[:80]}")
            # `INSERT ... ON CONFLICT DO UPDATE` is the same defect wearing the
            # upsert's clothes: it rewrites a row that is already there.
            if "on conflict" in lowered and "do update" in lowered:
                offenders.append(f"{where} (ON CONFLICT DO UPDATE) -> {sql[:80]}")
    assert offenders == [], (
        "a history row can be rewritten or removed by a statement this application "
        f"declares, which is the one thing the append-only claim forbids: {offenders}"
    )


def test_the_scan_above_is_not_vacuous():
    """Guards the guard: it must be LOOKING at the statements it claims to check."""
    statements = _module_statements()
    # It reaches the submission module...
    assert any(k.startswith("submission_store.py:") for k in statements), statements.keys()
    # ...and really sees the five tables in it.
    seen = {t for sql in statements.values() for t in _HISTORY_TABLES if t in sql}
    assert seen == set(_HISTORY_TABLES), sorted(seen)
    # ...and the regexes it applies really match the shapes it forbids.
    forbidden = "UPDATE isaac_submissions SET subject = %s"
    assert re.search(r"\bupdate\s+isaac_submissions\b", forbidden.lower())
    removal = "DELETE FROM isaac_experiment_revisions WHERE revision_id = %s"
    assert re.search(r"\bdelete\s+from\s+isaac_experiment_revisions\b", removal.lower())


def test_every_declared_statement_is_a_plain_string_literal():
    """No caller-supplied SQL, and none assembled from anything but literals.

    ``db_write``'s primary guarantee is that no caller-supplied SQL exists in the
    write path. The scan above reads source, so a statement built at run time from a
    variable would be invisible to it; this asserts none exists, which is what makes
    the scan's conclusion sound.
    """
    unresolved: list[str] = []
    for path in sorted(BACKEND_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name) or not target.id.startswith("Q_"):
                    continue
                module = __import__(f"isaac_api.{path.stem}", fromlist=["_"])
                if not isinstance(getattr(module, target.id, None), str):
                    unresolved.append(f"{path.name}:{target.id}")
    assert unresolved == [], unresolved


def test_revoke_really_is_refused_so_the_stated_reason_is_true():
    """The migration comments say ``REVOKE`` is unavailable. Asserted, not assumed."""
    for statement in (
        "REVOKE UPDATE, DELETE ON isaac_submissions FROM metadata_assistant",
        "GRANT SELECT ON isaac_submissions TO metadata_assistant",
    ):
        with pytest.raises(dbw.WriteRefused):
            dbw.WriteStatementPolicy().check(statement)


def test_every_submission_statement_passes_the_owned_tables_policy():
    """The other direction: an over-broad refusal filter would break the feature."""
    for name, sql in _module_statements().items():
        if not name.startswith("submission_store.py:"):
            continue
        assert dbw.WriteStatementPolicy().check(sql) == sql.strip(), name


# =============================================================================
# 2. the committed migrations
# =============================================================================


def _statements(version: str) -> list[str]:
    return next(m.statements for m in dbm.load_migrations() if m.version == version)


def test_the_two_new_migrations_are_create_only_and_pass_the_policy():
    for version, count in (("0003_revisions", 6), ("0004_submissions", 4)):
        statements = _statements(version)
        assert len(statements) == count, version
        for statement in statements:
            lowered = statement.lower()
            assert lowered.startswith("create "), version
            assert "if not exists" in lowered, version
            dbw.WriteStatementPolicy().check(statement)
            tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", lowered))
            assert tokens.isdisjoint({"alter", "drop", "truncate", "revoke", "grant"}), version


def test_the_new_tables_are_owned_before_their_own_create_can_run():
    """Listing the table and creating it must land in ONE change, and here is why.

    The statement policy is consulted BEFORE a connection is opened, so a
    ``CREATE TABLE`` naming a table outside ``OWNED_TABLES`` is refused by this
    application and the migration cannot run at all. Splitting the two across
    changes does not produce a half-working feature; it produces a migration that is
    dead on arrival. Asserted by removing the names and watching the CREATE refuse.
    """
    narrowed = dbw.WriteStatementPolicy(
        owned=frozenset({"isaac_schema_migrations", "isaac_experiments", "isaac_runs"})
    )
    for version in ("0003_revisions", "0004_submissions"):
        with pytest.raises(dbw.WriteRefused) as excinfo:
            for statement in _statements(version):
                narrowed.check(statement)
        assert "does not own" in str(excinfo.value), version


@pytest.mark.parametrize(
    "version,constraint",
    [
        # 0003 — the attribution CHECK, the revision-number uniqueness, and the
        # deliberate ABSENCE of a foreign key from a run revision to `isaac_runs`.
        ("0003_revisions", "isaac_experiment_revisions_attribution"),
        # M1 — `''` is not NULL, so without this the attribution pairing reads a row
        # naming nobody as ATTRIBUTED. Unreachable from this application (both actor
        # dataclasses reject an empty subject), declared anyway: `ALTER` is a
        # forbidden verb, so a CHECK omitted here needs a whole further migration.
        ("0003_revisions", "isaac_experiment_revisions_subject_non_empty"),
        ("0003_revisions", "isaac_experiment_revisions_no_unique"),
        ("0003_revisions", "isaac_experiment_revisions_signature_shape"),
        ("0003_revisions", "isaac_run_revisions_revision_run_unique"),
        ("0003_revisions", "isaac_run_revisions_document_identity"),
        ("0003_revisions", "isaac_revision_changes_unique"),
        ("0003_revisions", "isaac_revision_changes_kind_known"),
        # 0004 — the two uniqueness constraints idempotency rests on, the
        # one-run-one-record CHECK, and the same attribution pairing.
        ("0004_submissions", "isaac_submissions_signature_unique"),
        ("0004_submissions", "isaac_submissions_idempotency_unique"),
        ("0004_submissions", "isaac_submissions_revision_unique"),
        ("0004_submissions", "isaac_submissions_attribution"),
        ("0004_submissions", "isaac_submissions_subject_non_empty"),
        ("0004_submissions", "isaac_submission_runs_one_record_per_unit"),
        ("0004_submissions", "isaac_submission_runs_unit_unique"),
    ],
)
def test_the_approval_packets_named_constraints_are_in_the_committed_text(version, constraint):
    """Every constraint the packets claim is DECLARED. Whether it BEHAVES is CI's job."""
    assert constraint in "\n".join(_statements(version)), constraint


def test_a_run_revision_is_deliberately_not_a_foreign_key_to_isaac_runs():
    """History must survive the run it describes being removed.

    A run can be dropped from an experiment (``Q_DELETE_ABSENT_RUNS`` removes its
    row), and a foreign key would then either REFUSE that deletion — freezing the
    live table behind its own audit log — or, with CASCADE, DELETE THE HISTORY. The
    absence is a decision, so it is asserted positively rather than left to be
    noticed.
    """
    text = "\n".join(_statements("0003_revisions"))
    run_revisions = text[text.index("CREATE TABLE IF NOT EXISTS isaac_run_revisions") :]
    run_revisions = run_revisions.split("CREATE INDEX", 1)[0]
    assert "isaac_runs" not in run_revisions.replace("isaac_run_revisions", "")


def test_no_committed_migration_uses_on_delete_at_all():
    """No CASCADE anywhere, so no single statement can destroy a history tree.

    ``ON DELETE CASCADE`` is additionally UNWRITABLE under the statement policy —
    the tokenizer reads the ``delete`` after ``on`` as naming a table this
    application does not own. Both facts are true and the design argument stands on
    its own; this asserts the text, so the guarantee does not depend on a tokenizer
    quirk staying put.
    """
    for migration in dbm.load_migrations():
        for statement in migration.statements:
            assert "on delete" not in statement.lower(), migration.version


def test_the_change_kinds_in_python_and_in_sql_are_the_same_three():
    """One vocabulary, two languages. A drift here writes rows the CHECK refuses."""
    text = "\n".join(_statements("0003_revisions"))
    match = re.search(r"change_kind IN \(([^)]*)\)", text)
    assert match, text
    in_sql = {value.strip().strip("'") for value in match.group(1).split(",")}
    assert in_sql == set(submissions.CHANGE_KINDS)


def test_the_revision_reason_in_python_and_in_sql_are_the_same_one():
    text = "\n".join(_statements("0003_revisions"))
    match = re.search(r"reason IN \(([^)]*)\)", text)
    assert match, text
    assert {v.strip().strip("'") for v in match.group(1).split(",")} == {
        sstore.REASON_SUBMISSION
    }


def test_the_trust_bases_the_schema_admits_are_exactly_the_three_python_names():
    """The DB admits three; ``identity.RECOGNISED_TRUST_BASES`` holds only two.

    THE ASYMMETRY IS THE DECISION AND IS ASSERTED IN BOTH DIRECTIONS.
    ``unattributed`` must be admitted by the column (an unattributed row has to be
    writable) and must NOT be in ``RECOGNISED_TRUST_BASES`` (that set is what a
    ``HumanActor`` may CLAIM, and widening it would make
    ``HumanActor(subject="x", trust_basis="unattributed")`` constructible — a name
    nothing vouched for, which is the exact shape the identity seam exists to
    refuse).
    """
    from isaac_api import identity

    expected = set(identity.RECOGNISED_TRUST_BASES) | {submissions.TRUST_BASIS_UNATTRIBUTED}
    for version in ("0003_revisions", "0004_submissions"):
        text = "\n".join(_statements(version))
        match = re.search(r"trust_basis IN \(([^)]*)\)", text, re.S)
        assert match, version
        assert {v.strip().strip("'") for v in match.group(1).split(",")} == expected, version
    assert submissions.TRUST_BASIS_UNATTRIBUTED not in identity.RECOGNISED_TRUST_BASES
    with pytest.raises(ValueError):
        identity.HumanActor(
            subject="someone", trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED
        )


@pytest.mark.parametrize("version", ["0003_revisions", "0004_submissions"])
def test_the_rollback_is_committed_beside_it_and_is_unreachable_from_the_app(version):
    rollback = MIGRATIONS / f"{version}.rollback.sql"
    assert rollback.is_file()
    assert rollback.name not in {m.path.name for m in dbm.load_migrations()}
    body = rollback.read_text(encoding="utf-8")
    assert body.count("BEGIN;") == 1 and body.count("COMMIT;") == 1
    assert f"DELETE FROM isaac_schema_migrations WHERE version = '{version}';" in body
    # The whole file is refused by the write policy, because it contains a DROP.
    with pytest.raises(dbw.WriteRefused):
        for statement in dbm.split_statements(body):
            dbw.WriteStatementPolicy().check(statement)


def test_each_rollback_drops_exactly_what_its_own_migration_created_in_reverse_order():
    """Children before parents, and nothing belonging to another migration."""
    expected = {
        "0003_revisions": [
            "isaac_revision_changes",
            "isaac_run_revisions",
            "isaac_experiment_revisions",
        ],
        "0004_submissions": ["isaac_submission_runs", "isaac_submissions"],
    }
    for version, order in expected.items():
        body = (MIGRATIONS / f"{version}.rollback.sql").read_text(encoding="utf-8")
        dropped = re.findall(r"^DROP TABLE IF EXISTS (\w+);", body, re.M)
        assert dropped == order, version
        created = re.findall(
            r"CREATE TABLE IF NOT EXISTS (\w+)", "\n".join(_statements(version))
        )
        assert set(dropped) == set(created), version


def test_no_new_migration_or_rollback_names_the_production_table():
    """`records` holds the production-derived sample and must never be referenced."""
    for name in (
        "0003_revisions.sql",
        "0003_revisions.rollback.sql",
        "0004_submissions.sql",
        "0004_submissions.rollback.sql",
    ):
        body = (MIGRATIONS / name).read_text(encoding="utf-8")
        for statement in dbm.split_statements(body) if not name.endswith(
            ".rollback.sql"
        ) else [body]:
            # Comments are stripped from a migration's statements; a rollback is read
            # whole, so its own prose is scanned too — and it deliberately never
            # names the table, not even to explain that it does not.
            stripped = "\n".join(
                line for line in statement.splitlines() if not line.strip().startswith("--")
            )
            assert not re.search(r"\brecords\b", stripped), name


@pytest.mark.parametrize(
    "version,packet",
    [
        ("0003_revisions", "0003"),
        ("0004_submissions", "0004"),
        # `0005_run_projection` is not a submission migration, and this test lives in
        # the submission file. It is parametrised here rather than copied into
        # `test_experiment_repository.py` for one reason: THIS is the version of the
        # digest check that is driven by the version name rather than by a hardcoded
        # table, so adding a row costs one line and a copy would cost a second
        # implementation to keep correct. The alternative — a third near-identical
        # digest test — is how the 0002 packet's digest drifted for the whole life of
        # a branch while a test that looked like this one passed.
        ("0005_run_projection", "0005"),
    ],
)
def test_the_approval_packet_digests_match_the_committed_files(version, packet):
    """THE ONE CHECK THAT MAKES AN APPROVAL MEAN ANYTHING.

    A packet's digest table is the only evidence that the bytes an operator applies
    to the hosted database are the bytes the owner approved. `0002`'s packet records
    a period in which its own forward digest had gone stale and nothing noticed —
    which is exactly the failure this test exists to make impossible: editing a
    migration without re-issuing its packet now goes red here, before review rather
    than after application.
    """
    import hashlib

    doc = (
        Path(sstore.__file__).resolve().parents[3]
        / "docs"
        / f"migration-approval-packet-{packet}.md"
    ).read_text(encoding="utf-8")
    for suffix in (".sql", ".rollback.sql"):
        path = MIGRATIONS / f"{version}{suffix}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest in doc, (
            f"{path.name} has changed but "
            f"docs/migration-approval-packet-{packet}.md still quotes an older "
            f"SHA-256. Re-issue the packet; do not edit the digest by hand."
        )


def test_the_packets_do_not_claim_a_hosted_application(version="0003"):
    """A packet that read as applied would be a standing permission nobody granted.

    WHAT THIS PINS, AND WHAT IT DELIBERATELY NO LONGER PINS (changed 2026-08-17).

    It used to require two literals. The first — that the packet says it has not been
    applied to the hosted database — is the invariant, and is kept. The second was
    ``"No PostgreSQL has ever executed this file"``, and requiring it was a mistake
    of a specific and instructive kind: it pinned a sentence whose truth had an
    EXPIRY DATE BUILT INTO IT. The sentence itself named the event that would
    falsify it ("until the ``postgres-migration`` job runs on this branch"), that job
    then ran and passed on ``main``, and this assertion went on mechanically
    REQUIRING THE REPOSITORY TO KEEP ASSERTING A FALSE CLAIM ABOUT ITSELF — with the
    test reading as evidence of honesty while enforcing the opposite.

    So the rule this file now follows: **pin the invariant, never the transient.**
    "Nobody has applied this to the hosted database" is an invariant until an
    operator acts and amends the packet deliberately. "No PostgreSQL anywhere has
    ever run this SQL" was always going to stop being true the moment CI worked as
    designed, and a test cannot tell the difference between that and a regression.

    The owner's APPROVAL is likewise not pinned here, in either direction. An
    approval is a fact about a person's decision, recorded in the packet's STATUS
    block; asserting a literal about it would mean this test had to be edited to
    record a decision, which is backwards. What must never drift is the APPLICATION
    claim, because that is the one a reader could mistake for standing permission.
    """
    root = Path(sstore.__file__).resolve().parents[3]
    # `0005` IS COVERED HERE TOO, and its STATUS wording is deliberately different:
    # `0003`/`0004` are APPROVED-and-unapplied, while `0005` is NOT APPROVED. So the
    # exact literal cannot be shared, and each packet is checked against the phrasing
    # its own state requires. What is shared, and is the invariant, is that neither
    # reads as applied and neither reads as a delegation.
    for packet in ("0003", "0004", "0005"):
        doc = (root / "docs" / f"migration-approval-packet-{packet}.md").read_text(
            encoding="utf-8"
        )
        if packet == "0005":
            # WHITESPACE-NORMALISED, because a Markdown file wraps at 90 columns and
            # a phrase that happens to straddle a line break is not a different
            # phrase. The first version of this assertion failed for exactly that
            # reason, and reflowing the document to satisfy a test would have been
            # the tail wagging the dog.
            flat = " ".join(doc.split())
            assert "NOT APPLIED ANYWHERE" in flat, packet
            assert "NOT APPROVED" in flat, packet
            assert "no agent may do it" in flat, packet
        else:
            assert "NOT APPLIED TO THE HOSTED DATABASE, ANYWHERE." in doc, packet
            # The operator's act is outstanding, and the packet must say so in a form
            # a reader cannot mistake for a delegation.
            assert "no agent may run it" in doc, packet
        # And it must not have quietly acquired the opposite claim.
        for forbidden in (
            "APPLIED TO THE HOSTED DATABASE BY DEAN",
            "has been applied to the hosted database",
        ):
            assert forbidden not in doc, (packet, forbidden)


def test_the_0005_packet_does_not_read_as_proven_against_real_data():
    """`0005`'s OWN standing caveat, pinned separately because it is the load-bearing
    one and it is the sentence a re-issue would most naturally tidy away.

    CI proves the migration against an EMPTY `postgres:18` container with a two-row
    synthetic stand-in for `records`. That is not "behaves against the real data, the
    real roles and the real grants", and it is the entire reason the operator's step
    exists as a separate act rather than as a formality after a green build.

    Pinned as the invariant rather than the sentence: the packet must say the
    container is empty AND must not claim the hosted database has been contacted.
    """
    root = Path(sstore.__file__).resolve().parents[3]
    doc = (root / "docs" / "migration-approval-packet-0005.md").read_text(encoding="utf-8")
    flat = " ".join(doc.split())
    assert "the CI container is **empty**" in flat
    assert "no agent has connected to the hosted database" in flat.lower()
    for forbidden in (
        "proven against the hosted database",
        "verified against the real data",
    ):
        assert forbidden not in flat.lower(), forbidden


def test_the_packets_do_not_still_carry_the_expired_ci_claim():
    """The negative control for the change above: the stale sentence must be GONE.

    Dropping an assertion is how a guard silently becomes weaker, so the removal of
    the ``"No PostgreSQL has ever executed this file"`` requirement is paired with a
    positive assertion that the claim itself is no longer made anywhere in the
    packets except inside the quoted correction that explains why it was wrong.
    """
    root = Path(sstore.__file__).resolve().parents[3]
    for packet in ("0003", "0004"):
        doc = (root / "docs" / f"migration-approval-packet-{packet}.md").read_text(
            encoding="utf-8"
        )
        # The claim survives ONLY as a block-quoted historical citation, AND ONLY
        # INSIDE THE CORRECTION THAT EXPLAINS IT. An earlier version of this check
        # accepted any line beginning with ">", which an independent review defeated
        # in one line: the whole STATUS block is block-quoted, so a fresh assertion
        # planted there satisfied "is quoted" while asserting the false claim as
        # fact. The window is now anchored to the correction's own opening phrase.
        marker = "CORRECTED 2026-08-17"
        assert marker in doc, packet
        window_starts_at = doc.index(marker)
        for lineno, line in enumerate(doc.splitlines(), start=1):
            if "No PostgreSQL has ever executed this file" not in line:
                continue
            assert line.lstrip().startswith(">"), (
                f"packet {packet}:{lineno} asserts the expired CI claim as its own "
                f"statement rather than quoting it as corrected: {line!r}"
            )
            assert doc.index(line) > window_starts_at, (
                f"packet {packet}:{lineno} carries the expired claim OUTSIDE the "
                f"correction block that explains it — being inside a blockquote is "
                f"not the same as being a citation: {line!r}"
            )


def test_the_packets_do_not_overstate_CI_constraint_coverage():
    """The number in the packets must equal the number CI actually exercises.

    THIS TEST EXISTS BECAUSE THE PACKETS ONCE CLAIMED "every constraint". They did
    not; an independent review measured 27 of 46, and the overstatement sat in the
    evidence an owner approval is recorded as resting on. Correcting the sentence
    without a guard would leave the next slice free to re-inflate it, so the claim is
    now DERIVED here and compared against the committed text.

    `refuse()`'s third argument in CI is the object PostgreSQL must be shown to
    blame, so a constraint the workflow never NAMES was never exercised. That is the
    measurement: declared names minus names absent from the workflow file.

    The assertion is deliberately two-sided. Too high and the packets overstate the
    evidence, which is the original defect. Too low and someone has widened CI's
    coverage without crediting it, which quietly keeps a stale limitation in a
    document a reader trusts.
    """
    import re

    root = Path(sstore.__file__).resolve().parents[3]
    declared: set[str] = set()
    for version in ("0003_revisions", "0004_submissions"):
        text = (MIGRATIONS / f"{version}.sql").read_text(encoding="utf-8")
        code = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("--")
        )
        declared |= set(re.findall(r"CONSTRAINT\s+([a-z0-9_]+)", code))

    workflow_lines = (
        (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8").splitlines()
    )
    # BLAMED, NOT MERELY MENTIONED, and the difference is the whole measurement. A
    # `refuse()` call's third argument is the object PostgreSQL must be shown to
    # blame, and it sits on its own continuation line as a bare quoted name. Counting
    # names that merely APPEAR anywhere in the workflow gives 43 (re-measured
    # 2026-08-25; it was 29 when the strict rule gave 27, and the comment was not
    # updated when the strict rule moved to 41) and overstates the evidence by two:
    # `isaac_revision_changes_revision_fk` and `isaac_submissions_experiment_fk` are
    # referenced for other reasons without any refusal being blamed on them. The first
    # version of this guard made exactly that mistake, which is a small demonstration
    # of why the packets made the larger one.
    #
    # THE LOOSE RULE IS ALSO THE ONE COMMIT `5dc833a`'s MESSAGE PRINTS BESIDE THE
    # NUMBER, and it does not produce that number. That message states the recipe as
    # "blamed = that name appearing in `.github/workflows/ci.yml`" and then reports
    # 41 blamed / 5 unblamed. Applied literally, that recipe gives 43 blamed and 3
    # unblamed. The NUMBER is right and the RECIPE printed beside it is one this guard
    # rejects; a commit message cannot be edited, so the corrected wording lives in the
    # documents and here.
    blamed = {
        m.group(1)
        for m in (re.fullmatch(r'"([a-z0-9_]+)"', line.strip()) for line in workflow_lines)
        if m is not None and m.group(1) in declared
    }

    assert len(declared) == 46, (
        f"the two migrations now declare {len(declared)} constraints, not 46. "
        f"Re-measure and update both packets' §12A/§12B and CLAUDE.md."
    )
    # 27 -> 41. The seventeen constraints the packets listed as declared-and-never-
    # exercised are now exercised, fourteen of them individually. THREE ARE NOT, AND
    # CANNOT BE: `isaac_submission_runs` carries `record_id = unit_id` and
    # `run_id IS NULL OR run_id = unit_id`, so a row violating `unit_id_shape`,
    # `record_id_shape` or `run_id_shape` ALWAYS violates an equality CHECK at the same
    # time, and PostgreSQL reports only the first constraint it happens to check. There
    # is no assignment of those three columns that violates exactly one of them. That is
    # defence in depth rather than a defect — the equality CHECKs subsume the shape
    # CHECKs — and the workflow proves those rows are refused by a CHECK on that table
    # through a deliberately weaker helper (`refuse_by_the_table`) so nobody mistakes it
    # for the individual blame this counter measures.
    #
    # The other two are the pre-existing pair this guard's own comment names:
    # `isaac_revision_changes_revision_fk` and `isaac_submissions_experiment_fk` appear
    # in the workflow for other reasons with no refusal blamed on them.
    assert len(blamed) == 41, (
        f"CI's constraint step now blames {len(blamed)} of the {len(declared)} declared "
        f"constraints, not 41. Update both packets' §12A/§12B and CLAUDE.md to the "
        f"measured number — upward if coverage improved, and do not leave a stale "
        f"limitation sitting in a document a reader trusts."
    )

    for packet in ("0003", "0004"):
        doc = (root / "docs" / f"migration-approval-packet-{packet}.md").read_text(
            encoding="utf-8"
        )
        assert "41" in doc and "46" in doc, packet
        # And the packets must not have re-acquired the overstatement.
        assert "exercised every constraint these five tables declare" not in doc, packet


#: Sentences that must survive ONLY inside a strikethrough that corrects them — the
#: repository's established remedy, and the one
#: `test_the_packets_do_not_claim_a_hosted_application` already uses for an expired
#: claim about this same job.
#:
#: THERE ARE NOW TWO GENERATIONS OF RETIRED SENTENCE HERE, AND THEY WERE WRONG IN
#: OPPOSITE DIRECTIONS. The first group credited a real CI RUN with coverage only the
#: workflow FILE declared (41 when a run had produced 27). The second group is the
#: CORRECTION to the first, retired in turn on 2026-08-25 when `77de2db` merged to
#: `main` via `c153ec9` and run `32800763199` executed the 41. Keeping both means a
#: reader sees the sequence 41 (false) -> 27 (true) -> 41 (true, by a different run)
#: rather than only the latest number.
#:
#: Written WITHOUT markdown emphasis; the check strips `*` before searching, so a
#: re-bolded or un-bolded copy cannot slip past.

#: Generation 1 — credited run `32099627898` with the branch file's 41. STILL
#: FORBIDDEN as a live statement, and forbidden for a reason that did not expire: that
#: run blamed 27, and no later run changes what an earlier one did.
_RUN_CREDITED_WITH_FILE_COVERAGE: tuple[str, ...] = (
    # CLAUDE.md §15 — the one the review measured.
    "exercising 41 of the 46 declared constraints (27 when that sentence was written)",
    # CLAUDE.md §11.
    "41 of 46 declared (re-measured 2026-08-19, up from 27)",
    # CLAUDE.md §15, the readiness table row.
    "41 of the 46 declared constraints are exercised there",
    # docs/dean-handoff-consolidated-2026-08-18.md — the UNSENT EXTERNAL PACKAGE.
    "Constraint coverage moved 27 → 41 of 46, validated against a real",
    "CI's constraint step now blames 41 of them, up from 27",
    # the two approval packets.
    "coverage improved from 27 to 41 of 46",
    "IMPROVED on 2026-08-19 from 27 to 41 of 46",
)

#: Generation 2 — the 2026-08-24 correction, which was RIGHT and has been OVERTAKEN BY
#: EVENTS rather than refuted. Each of these lives in exactly one of the three
#: documents this repository owns outright (`CLAUDE.md` and the two packets), so the
#: per-claim control below can require each to be findable without coupling the suite
#: to the state of the external hand-off package.
_CORRECTION_RETIRED_BY_THE_C153EC9_RUN: tuple[str, ...] = (
    # CLAUDE.md §11.
    "Constraint coverage is 41 of 46 DECLARED IN THE WORKFLOW; 27 of 46 is what a "
    "real PostgreSQL has actually executed on `main`",
    # CLAUDE.md §15, the two-number table and the paragraph under it.
    "Declared in the workflow and NOT YET RUN on `main`",
    "The fourteen extra constraints arrived in `77de2db` (2026-08-19), which `git "
    "merge-base --is-ancestor 77de2db origin/main` reports is NOT in `main`",
    "`fe374c0` could only ever have exercised 27, and 41 is a property of the "
    "workflow file, not of any run this repository can point to",
    # CLAUDE.md §15, the readiness table row.
    "An operator weighing this evidence should read 27, not 41.",
    # docs/migration-approval-packet-0003.md — §12A and §12B.
    "YES, for the 27. The other 19 are declared and unexercised",
    "the WORKFLOW FILE now declares 41 of 46; a real PostgreSQL has run 27",
    "Run `32099627898`, at `fe374c0`, is the only execution against a real "
    "PostgreSQL this repository can point to",
    "An operator weighing this packet's evidence should read 27.",
    "27 — unchanged",
    # docs/migration-approval-packet-0004.md — §12A.
    "what a real PostgreSQL has EXECUTED is 27 of 46, unchanged",
    "An operator should weigh 27.",
    "Four of the unexercised belong to this migration's own tables "
    "(`isaac_submissions_id_shape`, `_conflict_summary_is_object`, "
    "`_trust_basis_known`, and every id-shape CHECK on `isaac_submission_runs`).",
)

RETIRED_COVERAGE_CLAIMS: tuple[str, ...] = (
    _RUN_CREDITED_WITH_FILE_COVERAGE + _CORRECTION_RETIRED_BY_THE_C153EC9_RUN
)

#: Every document that quotes either figure.
#:
#: EXTENDED 2026-08-25. `docs/dean-operator-addendum-2026-08-25.md` was added by the
#: same PR that introduced these guards, its §1 is ENTIRELY the 41-vs-27 correction,
#: and it was pinned by no test at all — so the one document most likely to restate
#: either figure was the one document nothing checked.
COVERAGE_DOCUMENTS: tuple[str, ...] = (
    "CLAUDE.md",
    "docs/dean-handoff-consolidated-2026-08-18.md",
    "docs/dean-operator-addendum-2026-08-25.md",
    "docs/migration-approval-packet-0003.md",
    "docs/migration-approval-packet-0004.md",
)

#: The three documents this repository owns outright — as opposed to the two UNSENT
#: EXTERNAL PACKAGES, which are maintained as prose for a reader outside the project.
OWNED_COVERAGE_DOCUMENTS: tuple[str, ...] = (
    "CLAUDE.md",
    "docs/migration-approval-packet-0003.md",
    "docs/migration-approval-packet-0004.md",
)

#: The two external packages. Both are Dean's to read, and BOTH are checked: the same
#: false sentence appended to either used to pass, including in the file this module's
#: own docstring calls the place the claim "mattered most".
EXTERNAL_COVERAGE_PACKAGES: tuple[str, ...] = (
    "docs/dean-handoff-consolidated-2026-08-18.md",
    "docs/dean-operator-addendum-2026-08-25.md",
)


def _flatten_markdown(raw: str) -> str:
    """Blockquote markers stripped, emphasis stripped, whitespace collapsed.

    So a line wrap, a bold marker, or a ``>`` continuation inside a sentence cannot
    hide it. The ``>`` rule was added after a corrected sentence in packet 0003
    wrapped mid-phrase and the search missed it.
    """
    import re

    return re.sub(
        r"\s+", " ", re.sub(r"(?m)^[ \t]*>[ \t]?", "", raw).replace("*", "")
    )


def _strike_spans(text: str) -> list[tuple[int, int]]:
    """Character spans covered by a ``~~ ... ~~`` strikethrough.

    Markers are paired in order, so a claim is "inside a strikethrough" no matter how
    far back the strike OPENED. The previous check looked only 12 characters behind the
    claim, which rejected a sentence genuinely inside a long strikethrough — loudly
    rather than silently, but it would still mislead a triager after an innocent
    reflow. Every document in :data:`COVERAGE_DOCUMENTS` was measured to hold an even
    number of markers, so pairing in order is well defined for them; an odd count would
    make the LAST marker unpaired and simply leave it out of every span, which fails
    towards demanding a strike rather than inventing one.
    """
    import re

    marks = [m.start() for m in re.finditer(r"~~", text)]
    return list(zip(marks[0::2], [m + 2 for m in marks[1::2]]))


def test_no_document_credits_a_real_RUN_with_the_branch_file_s_coverage():
    """EVERY NUMBER HERE BELONGS TO A NAMED RUN, AND THE SEQUENCE IS KEPT LEGIBLE.

    THE ORIGINAL DEFECT, measured by an independent review. `CLAUDE.md` said the
    `postgres-migration` job *"has since run and passed on `main` at `fe374c0` (Actions
    run `32099627898`) ... exercising 41 of the 46 declared constraints"*. It cannot
    have::

        git show fe374c0:.github/workflows/ci.yml   ->  27 declared names blamed

    The fourteen extra cases arrived in `77de2db` (2026-08-19), which was NOT in `main`
    at the time, and whose own commit message says *"CI is the first execution."*

    WHAT CHANGED ON 2026-08-25, AND WHY THIS GUARD GREW A SECOND GENERATION RATHER
    THAN LOSING ITS FIRST. `77de2db` merged to `main` via `c153ec9` (PR #171), and
    Actions run `32800763199` — job `97660962127`, step *"Prove every 0003 and 0004
    constraint rejects what it claims to reject"*, conclusion `success` — executed the
    41 against a real `postgres:18`. Confirmed twice over, from the workflow file and
    from the run's own output: the step prints one ``refused as designed by <object>``
    line per case, and intersecting the 58 distinct objects those 67 OUTPUT lines name
    with the 46 constraints declared in `0003`+`0004` gives exactly 41::

        git merge-base --is-ancestor 77de2db origin/main   ->  now exits 0
        git show fe374c0:.github/workflows/ci.yml          ->  27
        .github/workflows/ci.yml (== origin/main)          ->  41

    THE TWO SUPPORTING FIGURES IN THAT SENTENCE WERE RE-MEASURED 2026-08-25 AND BOTH
    WERE WRONG. It said "the 57 distinct objects those 70 lines name". 70 is every line
    containing the phrase, three of which are Actions echoing the ``run:`` block's own
    shell source (``echo "refused as designed by $3: $1"``), so the OUTPUT count is 67.
    And 57 reproduces under no counting at all: a truncating regex (``[A-Za-z0-9_.]*``)
    collapsed the three ``column "…"`` objects into one and captured the EMPTY STRING
    from each echoed line, so an empty string was counted as a blamed object
    (53 + 4 = 57). The figure is 58. `41` is untouched by either error — it is an
    intersection with the declared set — and 41 is the only one of the three this test
    asserts. `docs/dean-operator-addendum-2026-08-25.md` already carried 67 correctly,
    which is how the discrepancy surfaced.

    So the number went 41 (false) -> 27 (true) -> 41 (true, by a DIFFERENT run), and
    both corrections are pinned. `_RUN_CREDITED_WITH_FILE_COVERAGE` stays forbidden
    forever: crediting run `32099627898` with 41 is false no matter what a later run
    did, because a run's coverage is a property of the run.
    `_CORRECTION_RETIRED_BY_THE_C153EC9_RUN` is forbidden as a LIVE statement while
    remaining required as a visible correction — a figure overtaken by a later
    measurement is not a figure that was wrong, and a reader must be able to see that.

    IT MATTERED MOST WHERE IT WAS REPEATED. `docs/dean-handoff-consolidated-2026-08-18
    .md` is an UNSENT EXTERNAL PACKAGE and the operator's evidence basis for applying
    `0003`/`0004` to the hosted database. Mis-stating that evidence in either direction
    distorts the basis of a decision an agent may not make and cannot undo.

    THE RULE IS THE REPOSITORY'S OWN REMEDY RATHER THAN A PROSE JUDGEMENT: "does this
    paragraph imply a run" is not decidable mechanically, so each retired sentence is
    named and must survive only inside a strikethrough. A future slice that reverts a
    correction fails here; one that rewords a sentence entirely does not, which is
    correct — the pinned numbers are guarded by the test below.
    """
    # THE TUPLES ARE PINNED BY LENGTH FIRST, and this is not decoration. Emptying
    # either tuple to `()` used to leave every assertion in this file passing: the only
    # length reference compared a tuple against itself, so the counts were pinned
    # nowhere and a slice could delete the whole ban and stay green.
    assert len(_RUN_CREDITED_WITH_FILE_COVERAGE) == 7, (
        "the generation-1 ban has changed size. Those seven sentences credited run "
        "32099627898 with the workflow FILE's coverage and are forbidden PERMANENTLY; "
        "shrinking the tuple is how the ban gets removed without anyone deciding to "
        "remove it."
    )
    assert len(_CORRECTION_RETIRED_BY_THE_C153EC9_RUN) == 13, (
        "the generation-2 ban has changed size. Those thirteen sentences are the "
        "2026-08-24 correction, retired by the c153ec9 run and required to survive as "
        "visible strikethroughs."
    )
    # AND THE DOCUMENT SET IS PINNED THE SAME WAY. Both external packages must be in
    # scope: the ban used to cover three documents, and the same false line appended to
    # either package Dean actually reads would have passed.
    assert set(EXTERNAL_COVERAGE_PACKAGES) <= set(COVERAGE_DOCUMENTS), (
        "an external package has been dropped from the scanned set. Those two files are "
        "the ones sent OUT of the project; exempting them is exactly backwards."
    )
    assert set(OWNED_COVERAGE_DOCUMENTS) | set(EXTERNAL_COVERAGE_PACKAGES) == set(
        COVERAGE_DOCUMENTS
    ), "COVERAGE_DOCUMENTS no longer equals owned + external; one list has drifted."

    root = Path(sstore.__file__).resolve().parents[3]
    for relative in COVERAGE_DOCUMENTS:
        raw = (root / relative).read_text(encoding="utf-8")
        flat = _flatten_markdown(raw)
        spans = _strike_spans(flat)
        for claim in RETIRED_COVERAGE_CLAIMS:
            index = flat.find(claim)
            while index != -1:
                # INSIDE a strikethrough, however far back it opened. THE OLD TEST
                # WAS "a `~~` occurs within 12 characters before the claim", and it
                # was wrong in BOTH directions, which is why it is replaced rather
                # than widened. Too strict: a claim genuinely inside a long
                # strikethrough was rejected, loudly, after nothing worse than a
                # reflow. Too loose, and this one was live — in packet 0004 the
                # sentence reads `~~"…unchanged"~~ and ~~"An operator should weigh
                # 27."~~`, so DELETING the second pair still left the FIRST pair's
                # CLOSING marker inside the 12-character window and the un-struck
                # claim passed. Measured by mutation, not reasoned about. Span
                # membership has neither failure: it is exactly the question being
                # asked. Verified span-only over all five documents: 0 failures.
                struck = any(start <= index < end for start, end in spans)
                assert struck, (
                    f"{relative} asserts a retired coverage claim as its own statement "
                    f"rather than striking it: {claim!r}. Each number belongs to a "
                    "named run: run 32099627898 (at fe374c0) blamed 27, and run "
                    "32800763199 (at c153ec9) blamed 41. Neither figure may be "
                    "restated as a live claim about the other run, and neither "
                    "correction may be deleted."
                )
                index = flat.find(claim, index + 1)

    # AND THE ATTRIBUTION THAT CAN NEVER BECOME TRUE, CHECKED STRUCTURALLY RATHER THAN
    # BY SENTENCE. Run 32099627898 blamed 27. A later run blaming 41 does not
    # retroactively widen it.
    #
    # REBUILT 2026-08-25, because the first version was the repository's own recorded
    # `git grep -E '\b'` trap inverted: a plain substring test on a line. WHAT IT USED
    # TO DO WRONG, each measured rather than imagined:
    #
    #   * `"41" in line` matched `414`, `0.41`, `9b41ac2`, `ci.yml:41`, `2041` and
    #     `runs/32800763141` — so it would have refused legitimate future sentences.
    #   * `"~~" in line` accepted ANY strikethrough on the line, including one on an
    #     unrelated clause, so the escape hatch was wider than the ban.
    #
    # WHAT IT NOW DOES, and this list is also the list of what it CANNOT catch:
    #
    #   * the run id is matched as a whole token, in the raw line;
    #   * `41` is matched as a standalone number in the line's PROSE, with inline code
    #     spans and URLs blanked first — which is what removes `ci.yml:41`, `9b41ac2`
    #     and `runs/32800763141`, while leaving "41 of 46" fully visible;
    #   * the line passes only if a strikethrough SPAN actually covers the run id or
    #     one of the `41` occurrences (a correction quoting the old error), or if the
    #     line also names run `32800763199` — which is exactly the shape of a sentence
    #     that keeps the two runs apart, and is why the two live lines that pair them
    #     legitimately are allowed rather than special-cased.
    #
    # LIMITS, STATED RATHER THAN IMPLIED. This is LINE-SCOPED, so a claim split across
    # two lines is not caught here — `CLAUDE.md` wraps at ~100 columns and three live
    # cross-line pairings already exist. That is deliberate: proximity over the
    # flattened text was measured and produced false positives on seven correct
    # sentences, because a document that discusses both runs necessarily puts both
    # numbers near each other. The SENTENCE-LEVEL scan above is the real coverage for
    # wrapped prose — it flattens whitespace precisely so a line break cannot hide a
    # banned claim — and this check is the backstop for a NEW sentence nobody has
    # written yet. And a claim phrased with the number inside backticks
    # (`run 32099627898 blamed \`41\` of 46`) is invisible to it by construction.
    #
    # ALL FIVE DOCUMENTS, not three. The two external packages were previously exempt
    # "because they are maintained separately", which is exactly backwards: they are
    # the ones Dean reads.
    ban_run = re.compile(r"(?<![\w])32099627898(?![\w])")
    ok_run = re.compile(r"(?<![\w])32800763199(?![\w])")
    bare_41 = re.compile(r"(?<![\w.])41(?![\w.])")
    code_or_url = re.compile(r"`[^`]*`|https?://\S+")
    for relative in COVERAGE_DOCUMENTS:
        for lineno, line in enumerate(
            (root / relative).read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not ban_run.search(line):
                continue
            prose = code_or_url.sub(lambda m: " " * len(m.group(0)), line)
            positions = [m.start() for m in bare_41.finditer(prose)]
            if not positions:
                continue
            spans_here = _strike_spans(line)
            covered = any(
                start <= at < end
                for at in positions + [m.start() for m in ban_run.finditer(line)]
                for start, end in spans_here
            )
            if covered or ok_run.search(line):
                continue
            raise AssertionError(
                f"{relative}:{lineno} names run 32099627898 and the standalone number "
                f"41 in one line, with neither inside a strikethrough nor run "
                f"32800763199 named to keep them apart: {line.strip()[:160]!r}. That "
                "run blamed 27 of the 46 declared constraints; 41 belongs to run "
                "32800763199 at c153ec9."
            )


def test_the_retired_coverage_claims_are_actually_still_findable():
    """NEGATIVE CONTROL: the guard above passes trivially on a document that deleted
    the correction instead of keeping it.

    Deleting a struck sentence is how a corrected claim becomes indistinguishable from
    one that never existed — the failure mode CLAUDE.md's own convention exists to
    prevent. So at least one retired claim must still be PRESENT somewhere, struck.
    """
    root = Path(sstore.__file__).resolve().parents[3]
    found = 0
    for relative in COVERAGE_DOCUMENTS:
        flat = _flatten_markdown((root / relative).read_text(encoding="utf-8"))
        found += sum(1 for claim in RETIRED_COVERAGE_CLAIMS if claim in flat)
    assert found >= len(RETIRED_COVERAGE_CLAIMS), (
        f"only {found} of {len(RETIRED_COVERAGE_CLAIMS)} retired coverage claims are "
        "still visible as corrections. A struck sentence that is deleted leaves a "
        "reader unable to tell a corrected claim from one that never drifted."
    )

    # PER-CLAIM FOR GENERATION 1 TOO, ADDED 2026-08-25. The aggregate above tolerates
    # one claim appearing twice while another vanishes, and the per-claim control that
    # already existed covered only generation 2 — so the seven sentences that are
    # forbidden PERMANENTLY were the ones whose deletion nothing detected. Generation 1
    # is scanned across ALL FIVE documents, because its members are spread over the
    # owned files and both external packages.
    everywhere = "\n".join(
        _flatten_markdown((root / relative).read_text(encoding="utf-8"))
        for relative in COVERAGE_DOCUMENTS
    )
    gone = [c for c in _RUN_CREDITED_WITH_FILE_COVERAGE if c not in everywhere]
    assert not gone, (
        f"{len(gone)} of the {len(_RUN_CREDITED_WITH_FILE_COVERAGE)} permanently "
        "forbidden sentences have been deleted rather than kept struck, so the ban now "
        f"guards text no document contains: {gone!r}"
    )

    # PER-CLAIM, FOR THE 2026-08-25 GENERATION. The aggregate count above can be
    # satisfied by one claim appearing twice while another vanishes. Every sentence in
    # `_CORRECTION_RETIRED_BY_THE_C153EC9_RUN` was placed by this repository in one of
    # the three documents it owns outright, so each can be required individually
    # without coupling the suite to the state of the external hand-off package. This is
    # the control that makes the "41 (false) -> 27 (true) -> 41 (true)" sequence
    # something a reader can actually see rather than something a docstring asserts.
    blob = "\n".join(
        _flatten_markdown((root / relative).read_text(encoding="utf-8"))
        for relative in OWNED_COVERAGE_DOCUMENTS
    )
    missing = [c for c in _CORRECTION_RETIRED_BY_THE_C153EC9_RUN if c not in blob]
    assert not missing, (
        f"{len(missing)} of the {len(_CORRECTION_RETIRED_BY_THE_C153EC9_RUN)} sentences "
        "retired on 2026-08-25 have been deleted rather than struck in place, so the "
        f"correction history is no longer legible: {missing!r}"
    )


def test_the_two_constraint_numbers_are_each_still_the_measured_ones():
    """Both vantage points, re-derived, so neither can drift in prose alone.

    The sibling test above pins that the numbers are not CONFLATED. This one pins that
    they are the numbers, using the same "blamed" rule
    `test_the_packets_do_not_overstate_CI_constraint_coverage` applies: the third
    argument of a `refuse()` call, on its own continuation line as a bare quoted name.

    `fe374c0` is read out of git rather than out of the working tree, because the claim
    being guarded is about a commit that has already run.

    EXTENDED 2026-08-25, and the extension is the interesting part. Until `77de2db`
    reached `main`, 41 was a property of a BRANCH FILE and the documents had to say so.
    It is now a property of a run — `32800763199`, at `c153ec9` — and the three facts
    that make that sentence honest are each derivable OFFLINE from a FULL CLONE, which
    is why they are asserted here instead of being taken on trust from a CI URL — and
    each degrades to an explicit skip in a shallow one, which CI's is:

    * the fourteen extra cases are in `main` (`git merge-base --is-ancestor`);
    * the workflow this tree measures is byte-identical to `main`'s, so "41 on `main`"
      and "41 here" are the same claim rather than two hopeful ones;
    * `fe374c0` still measures 27, so the earlier correction reads as overtaken rather
      than as an error.

    What this test deliberately does NOT do is contact GitHub. The run id, job id and
    conclusion are recorded in the documents and were verified once, by hand, against
    the job's own ``refused as designed by <object>`` output; a test that needed the
    network to pass would be a test that fails for reasons unrelated to the claim.
    """
    import re
    import subprocess

    root = Path(sstore.__file__).resolve().parents[3]
    declared: set[str] = set()
    for version in ("0003_revisions", "0004_submissions"):
        text = (MIGRATIONS / f"{version}.sql").read_text(encoding="utf-8")
        code = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("--")
        )
        declared |= set(re.findall(r"CONSTRAINT\s+([a-z0-9_]+)", code))

    def blamed(lines: list[str]) -> set[str]:
        return {
            m.group(1)
            for m in (re.fullmatch(r'"([a-z0-9_]+)"', line.strip()) for line in lines)
            if m is not None and m.group(1) in declared
        }

    # THE ONE ASSERTION THAT RUNS EVERYWHERE COMES FIRST, AND THE ORDER IS THE FIX.
    # Every other assertion in this test needs git history, and CI has none (see the
    # note below). Because the `fe374c0` read used to come first, a shallow checkout
    # skipped the whole test — so in CI this test asserted NOTHING, and the 41 was
    # enforced only by its sibling
    # `test_the_packets_do_not_overstate_CI_constraint_coverage`. It is now enforced
    # here too, before anything can skip.
    current = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert len(blamed(current.splitlines())) == 41, (
        "the number of declared constraints the workflow blames today is no longer 41."
    )

    # WHAT FOLLOWS IS NOT ENFORCED IN CI, AND SAYING SO IS THE POINT. Every
    # `actions/checkout@v5` in `.github/workflows/ci.yml` runs at the default
    # `fetch-depth: 1` — the file sets `fetch-depth` nowhere — so the `fe374c0` blob,
    # the `77de2db` object and the `origin/main` remote-tracking ref do not exist in a
    # CI checkout and each assertion below degrades to a SKIP there. A skip is not a
    # pass, and `CLAUDE.md` no longer says these numbers are "guarded so neither can
    # move": 41 is enforced everywhere, 27 and the byte-identity are enforced in a full
    # clone (a developer machine, or any run of the full suite locally) and reported as
    # skipped in CI. Deepening the checkout would arm them, and is deliberately NOT
    # done in this change: `.github/workflows/ci.yml` is one of the 200 entries in the
    # committed served-content manifest, so editing it drifts
    # `apps/api/isaac_api/data/memory-snapshot.json`, and whether the deepened checkout
    # actually arms the assertion is only observable by running CI.
    _shallow = (
        "not enforced here: this needs git history that a `fetch-depth: 1` CI "
        "checkout does not have. Enforced in a full clone. Detail: "
    )
    try:
        historic = subprocess.run(
            ["git", "show", "fe374c0:.github/workflows/ci.yml"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.skip(f"{_shallow}fe374c0 is not readable from this checkout: {exc}")

    assert len(blamed(historic.splitlines())) == 27, (
        "the number of declared constraints CI blamed at `fe374c0` is no longer 27. "
        "That is the figure an operator acts on, and it is quoted in CLAUDE.md, the "
        "Dean handoff and both approval packets."
    )

    # 41 IS NOW A CLAIM ABOUT A RUN, NOT ABOUT A BRANCH FILE — and these are the two
    # offline facts that entitle the documents to say so.
    def _git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True
        )

    ancestry = _git("merge-base", "--is-ancestor", "77de2db", "origin/main")
    if ancestry.returncode not in (0, 1):
        pytest.skip(
            f"{_shallow}77de2db/origin/main not resolvable here: {ancestry.stderr!r}"
        )
    assert ancestry.returncode == 0, (
        "`git merge-base --is-ancestor 77de2db origin/main` no longer holds, so the "
        "fourteen widened constraint cases are not in `main` and every document "
        "claiming 41 has been EXECUTED there is overstating its evidence again. This "
        "is the exact defect the 2026-08-24 correction fixed; do not re-open it by "
        "rewriting history under this branch."
    )

    on_main = _git("show", "origin/main:.github/workflows/ci.yml")
    if on_main.returncode != 0:
        pytest.skip(
            f"{_shallow}origin/main workflow not readable here: {on_main.stderr!r}"
        )
    assert on_main.stdout == current, (
        "this tree's `.github/workflows/ci.yml` differs from `origin/main`'s, so 41 is "
        "once again a property of a branch file rather than of run 32800763199. Either "
        "re-measure and re-state the documents with their new vantage point, or do not "
        "claim the number has been executed on `main`."
    )


# =============================================================================
# 3. the write path against the connection double
# =============================================================================


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    return ws


def _exportable(store_ws, experiment_id: str = "01SUBMITSTOREFIXTURE000001"):
    exp = store_ws.create_experiment(
        "Store fixture", {"kind": "synthetic"}, store_ws._full_draft(), id=experiment_id
    )
    exp.save_versioned()
    return store_ws.load_experiment(experiment_id)


def _materialise(exp):
    """Give every unit a record id, the way the route does before it records."""
    for unit in exp.export_units():
        unit.mark_exported(unit.target_id)
    exp.save_versioned()


def test_a_recorded_submission_writes_one_row_in_each_table_it_should(workspace):
    exp = _exportable(workspace)
    _materialise(exp)
    units = exp.export_units()
    conn = FakeSubmissionConnection()
    recorded = fake_store(conn).record_submission(
        exp=exp,
        units=units,
        content_signature=submissions.content_signature(exp.id, units),
        conflict_summary=submissions.conflict_summary(units),
        subject="ada",
        trust_basis="test_fixture",
        idempotency_key=None,
    )
    assert conn.commits == 1 and conn.rollbacks == 0
    assert len(conn.revisions) == 1 and conn.revisions[0]["revision_no"] == 1
    assert len(conn.submissions) == 1
    assert len(conn.submission_runs) == len(units)
    # A zero-run experiment contributes NO run-revision rows, deliberately: its one
    # export unit IS the experiment, whose draft is already inside the snapshot.
    assert conn.run_revisions == []
    # The first revision has no predecessor, so no change rows — and the API says
    # so rather than letting `change_count: 0` read as "nothing changed".
    assert conn.changes == []
    assert recorded["change_count"] == 0
    assert recorded["changes_comparable"] is False
    # THE TIMESTAMP IS THE SERVER'S. The fake stamps a fixed value; if the
    # application substituted its own clock this would not match.
    assert recorded["submitted_utc"] == FAKE_SUBMITTED_UTC
    assert recorded["trust_basis"] == "test_fixture" and recorded["subject"] == "ada"
    assert recorded["replayed"] is False


def test_a_second_revision_records_the_addresses_that_changed(workspace):
    exp = _exportable(workspace)
    _materialise(exp)
    conn = FakeSubmissionConnection()
    store = fake_store(conn)
    units = exp.export_units()
    store.record_submission(
        exp=exp,
        units=units,
        content_signature=submissions.content_signature(exp.id, units),
        conflict_summary={},
        subject=None,
        trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
        idempotency_key=None,
    )
    # Change one field value and submit again.
    exp = workspace.load_experiment(exp.id)
    address = next(
        path
        for path, env in exp.draft["fields"].items()
        if isinstance(env, dict) and env.get("value") is not None
    )
    exp.draft["fields"][address]["value"] = "a different value entirely"
    exp.save_versioned()
    exp = workspace.load_experiment(exp.id)
    units = exp.export_units()
    recorded = store.record_submission(
        exp=exp,
        units=units,
        content_signature=submissions.content_signature(exp.id, units),
        conflict_summary={},
        subject=None,
        trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
        idempotency_key=None,
    )
    assert recorded["revision_no"] == 2
    assert recorded["changes_comparable"] is True
    assert [(c["unit_id"], c["address"], c["change_kind"]) for c in conn.changes] == [
        (exp.id, address, "modified")
    ]


def test_a_lost_race_on_the_revision_number_writes_absolutely_nothing(workspace):
    """The transaction rolls back, and the ROW SETS are what proves it.

    Asserting only that an exception was raised would pass against a write path that
    had already inserted three rows; the fake takes a before-image per cursor, so
    "nothing was written" is an outcome rather than a protocol shape.
    """
    exp = _exportable(workspace)
    _materialise(exp)
    units = exp.export_units()
    conn = FakeSubmissionConnection()
    conn.refuse_revision_insert = True
    with pytest.raises(sstore.SubmissionRaceLost):
        fake_store(conn).record_submission(
            exp=exp,
            units=units,
            content_signature=submissions.content_signature(exp.id, units),
            conflict_summary={},
            subject=None,
            trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
            idempotency_key=None,
        )
    assert conn.is_empty(), "a refused submission left rows behind"
    assert conn.rollbacks == 1 and conn.commits == 0


def test_a_lost_race_on_the_submission_row_also_rolls_the_revision_back(workspace):
    """The revision is inserted BEFORE the submission, so this is the real test.

    A writer that lost the submission insert has already written a revision row and
    N run revisions in the same transaction. If those were not rolled back, the
    database would accumulate orphan revisions that no submission points at — and
    the next writer's ``revision_no`` would skip.
    """
    exp = _exportable(workspace)
    _materialise(exp)
    units = exp.export_units()
    conn = FakeSubmissionConnection()
    conn.refuse_submission_insert = True
    with pytest.raises(sstore.SubmissionRaceLost):
        fake_store(conn).record_submission(
            exp=exp,
            units=units,
            content_signature=submissions.content_signature(exp.id, units),
            conflict_summary={},
            subject=None,
            trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
            idempotency_key=None,
        )
    assert conn.is_empty(), "the revision survived a refused submission"


def test_missing_tables_refuse_before_anything_is_written(workspace):
    exp = _exportable(workspace)
    _materialise(exp)
    units = exp.export_units()
    conn = FakeSubmissionConnection(tables=False)
    with pytest.raises(sstore.SubmissionTablesMissing):
        fake_store(conn).record_submission(
            exp=exp,
            units=units,
            content_signature=submissions.content_signature(exp.id, units),
            conflict_summary={},
            subject=None,
            trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
            idempotency_key=None,
        )
    assert conn.is_empty()
    # ...and NO statement named a submission table. The probe carries the name as a
    # parameter, which is what makes that assertion possible at all.
    for sql, _params in conn.statements:
        for table in sstore.REQUIRED_TABLES:
            assert table not in sql, sql


def test_an_unmaterialised_unit_is_refused_before_a_connection_is_opened(workspace):
    """A NOT NULL violation from the server would be reported as an outage.

    The route materialises every unit first. If that contract were broken, the last
    statement of an otherwise complete transaction would fail and the caller would
    be told "the database did not answer" about a database that answered correctly.
    """
    exp = _exportable(workspace)  # deliberately NOT materialised
    units = exp.export_units()
    conn = FakeSubmissionConnection()
    with pytest.raises(ValueError) as excinfo:
        fake_store(conn).record_submission(
            exp=exp,
            units=units,
            content_signature=submissions.content_signature(exp.id, units),
            conflict_summary={},
            subject=None,
            trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
            idempotency_key=None,
        )
    assert "materialised" in str(excinfo.value)
    assert conn.statements == [], "a connection was opened for a request that cannot succeed"


def test_a_worked_example_record_can_never_be_submitted_at_the_store_layer(tmp_path, monkeypatch):
    """The THIRD enforcement of the tutorial rule, below the route's own refusal.

    The route refuses a scoped request outright and ``stamp_actor`` names nobody in
    one. This is the layer that would still refuse if both were removed, and it is
    the same guard the ordinary experiment store already applies.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    session_id, _ids = ws.create_tutorial_session()
    exp = ws.load_experiment(ws.SEED_READY_ID, session_id=session_id)
    assert exp is not None
    conn = FakeSubmissionConnection()
    with pytest.raises(repo.NotPersistable):
        fake_store(conn).record_submission(
            exp=exp,
            units=exp.export_units(),
            content_signature="0" * 64,
            conflict_summary={},
            subject=None,
            trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
            idempotency_key=None,
        )
    assert conn.statements == []


def test_the_fake_returns_the_submission_columns_in_order():
    """Guards the double: a mis-ordered row would make every field wrong, silently."""
    columns = [
        part.strip()
        for part in sstore._SUBMISSION_COLUMNS.replace("\n", " ").split(",")
    ]
    assert columns == [
        "submission_id",
        "experiment_id",
        "revision_id",
        "content_signature",
        "idempotency_key",
        "unit_count",
        "conflict_summary",
        "subject",
        "trust_basis",
        "submitted_utc",
    ]
    row = FakeSubmissionConnection.submission_row(
        {name: name for name in columns}
    )
    assert list(row) == columns


def test_the_store_is_none_without_pghost_and_there_is_no_filesystem_fallback():
    """A submission is durable or it does not happen. No ephemeral second store.

    A copy in an ``emptyDir`` that disappears on the next pod restart is not a
    weaker version of a durable declaration, it is a false one. Asserted as an
    ABSENCE — the module exports exactly one store class and no filesystem sibling —
    because a future slice adding one would otherwise be a quiet change of meaning.
    """
    assert sstore.store({}) is None
    assert sstore.store({"PGHOST": ""}) is None
    assert isinstance(sstore.store(fake_env()), sstore.PostgresSubmissionStore)
    exported = set(sstore.__all__)
    assert not any(
        "filesystem" in name.lower() or "memory" in name.lower() for name in exported
    ), exported


def test_the_capability_block_opens_no_connection_and_never_claims_availability(monkeypatch):
    """``/api/health`` must not be able to hang, and must not overpromise."""

    def explode(env):  # pragma: no cover - must never be called
        raise AssertionError("capability() opened a connection")

    monkeypatch.setattr(dbw, "connect_psycopg2", explode)
    monkeypatch.setattr(sstore.repo, "connect_psycopg2", explode, raising=False)
    block = sstore.capability({})
    assert block["configuration_permits"] is False
    assert set(block["blockers"]) == {
        sstore.BLOCKER_NO_DURABLE_STORAGE,
        sstore.BLOCKER_NO_ATTRIBUTABLE_ACTOR,
    }
    assert block["basis"] == "configuration_only"
    # There is no `available` key anywhere in it: whether the write would land
    # cannot be known from configuration, and a key called `available` would be read
    # as saying it can.
    assert "available" not in block


def test_the_operator_handoff_quotes_digests_that_match_the_committed_files():
    """THE HANDOFF IS THE THING THAT ACTUALLY GETS SENT, so it gets the same guard.

    `docs/dean-handoff-consolidated-2026-08-18.md` is the package a human forwards
    to the database operator, and it carries the digest table the operator is told
    to recompute — *"That check is the only evidence that the bytes applied are the
    bytes approved."* Until now nothing checked the handoff's own copy of those
    values, only each packet's.

    That is exactly how the `0002` packet's forward digest went stale for the whole
    life of a branch: the migration was corrected in place, the prose was updated,
    and the digest was not. An operator following the packet's own instruction would
    have computed a mismatch against the very file they were about to apply and had
    to guess whether the document was stale or the file had been tampered with.

    Driven off the document's own table rows rather than a hardcoded list, so adding
    a migration to the handoff is covered without editing this test.
    """
    import hashlib
    import re

    root = Path(sstore.__file__).resolve().parents[3]
    doc = (root / "docs" / "dean-handoff-consolidated-2026-08-18.md").read_text(
        encoding="utf-8"
    )
    quoted = set(re.findall(r"`([0-9a-f]{64})`", doc))
    assert quoted, "the handoff quotes no digests at all — re-read this test"

    on_disk = {}
    for path in sorted((root / "apps/api/isaac_api/migrations").glob("*.sql")):
        on_disk[hashlib.sha256(path.read_bytes()).hexdigest()] = path.name

    unmatched = sorted(d for d in quoted if d not in on_disk)
    assert not unmatched, (
        "the handoff quotes SHA-256 values that no committed migration hashes to: "
        f"{unmatched}. Recompute the table in "
        "docs/dean-handoff-consolidated-2026-08-18.md in the SAME commit as the SQL "
        "— an operator is told that check is the only evidence the bytes applied are "
        "the bytes approved."
    )


def test_the_operator_handoff_does_not_read_as_if_0005_were_approved():
    """A NEW MIGRATION FILE MUST NOT ACQUIRE AN APPROVAL BY PROXIMITY.

    The handoff's §1 lists two migrations the owner HAS approved and that need an
    operator window. `0005_run_projection` is not one of them. The specific failure
    this guards is not a false sentence but a false IMPRESSION: a third migration
    appearing in a document whose subject is "migrations awaiting an operator" reads
    as a third thing waiting on the operator, and an operator who applied it would
    have skipped the owner's review entirely.

    So the document must say the word, in the section that names it, and must
    instruct against applying it.
    """
    root = Path(sstore.__file__).resolve().parents[3]
    doc = (root / "docs" / "dean-handoff-consolidated-2026-08-18.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(doc.split())
    assert "0005_run_projection" in flat
    assert "NOT approved" in flat or "NOT APPROVED" in flat
    assert "Do NOT apply `0005`" in flat
    # AND THE HEADING MUST NOT PROMISE TWO WHILE LISTING THREE. "Two migrations,
    # approved" was the original heading and became misleading the moment a third
    # appeared in the file.
    assert "## 1. Two migrations, approved and awaiting an operator" not in doc
