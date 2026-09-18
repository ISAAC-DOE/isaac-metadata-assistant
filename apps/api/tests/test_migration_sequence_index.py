"""THE CANONICAL OPERATOR SEQUENCE EXISTS IN TWO PLACES, AND THIS IS WHY THAT IS SAFE.

``docs/migration-approval-packet-0005.md`` §12A is the AUTHORITATIVE ordered
sequence. ``docs/production-migration-execution-sequence.md`` §1 is the single
operator entry point, added because the sequence's steps live in three different
approval packets and an operator should not have to assemble the order from three
documents.

WHY IT IS NOT A BYTE-FOR-BYTE TRANSCLUSION
==========================================
§12A is written to be read *inside* the ``0005`` packet, so two of its eleven lines
say *"this packet's §5 prechecks"* and *"this packet's §7 postchecks"*. Copied
verbatim into a different file those phrases point at the NEW file, which has no §5
and no §7 — **a false reference introduced by the act of consolidating.** So the
index resolves them to named documents, and this test pins everything else.

WHAT THIS PINS, AND WHY EACH PART
=================================
This repository's measured history is that a claim duplicated across two files
drifts, and that the drift is invisible until somebody acts on the stale copy —
``CLAUDE.md`` §11 records a workflow vocabulary that stranded three of four copies,
five artifacts carrying one false ``never_projected: 0`` claim, and an enumeration
written *while correcting an enumeration error* that was itself short. So:

* **the STEP COUNT** — adding a step to one document and not the other fails here,
  rather than being discovered by an operator mid-migration;
* **every step's NUMBER and ACTION PHRASE** — the part that is not a cross-reference
  must be identical, so "verify the ledger" cannot become "verify the ledger and the
  grants" in one place only;
* **the two bounded commands, byte for byte** — these are the two lines an operator
  TYPES AT A PRODUCTION DATABASE. A drifted ``--through`` bound is the single most
  consequential divergence this pair could develop, because an unbounded ``--apply``
  would now land THREE approved migrations in one unverifiable step;
* **the absence of an unbounded ``--apply``** in the index — a positive assertion,
  because the dangerous form is a SUBSTRING of the safe one and so cannot be caught
  by looking for the safe one.

It deliberately does NOT pin the prose of either document. Pinning prose is how a
guard ends up mechanically requiring a repository to keep asserting something that
has expired — the failure recorded at
``test_submission_store.py::test_the_packets_do_not_claim_a_hosted_application``.
Pin the invariant, never the transient.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[3] / "docs"
PACKET = DOCS / "migration-approval-packet-0005.md"
INDEX = DOCS / "production-migration-execution-sequence.md"

#: The two commands an operator types at a production database. Held here as
#: literals as well as compared between the documents, so a change that edited BOTH
#: files consistently — and wrongly — still fails.
BOUNDED_COMMANDS = (
    "python scripts/db_migrate.py --apply --through 0004_submissions",
    "python scripts/db_migrate.py --apply --through 0005_run_projection",
)


def _sequence_block(text: str, heading: str) -> list[str]:
    """The ``text`` fence that follows ``heading``, as non-blank lines.

    Anchored on the heading rather than on "the first fence in the file", because a
    document gains sections and a positional read would silently start describing a
    different block.
    """
    start = text.index(heading)
    fence = re.search(r"```text\n(.*?)```", text[start:], re.S)
    assert fence is not None, f"no ```text block follows {heading!r}"
    return [line for line in fence.group(1).splitlines() if line.strip()]


def _steps(lines: list[str]) -> list[tuple[str, str, str]]:
    """``(number, action, reference)`` per line.

    The columns are separated by runs of two or more spaces, which is how both
    documents already lay the block out. The reference column is the ONLY part
    allowed to differ between them.
    """
    out: list[tuple[str, str, str]] = []
    for line in lines:
        fields = re.split(r"\s{2,}", line.strip())
        number = fields[0]
        action = fields[1] if len(fields) > 1 else ""
        reference = fields[2] if len(fields) > 2 else ""
        out.append((number, action, reference))
    return out


@pytest.fixture(scope="module")
def packet_steps() -> list[tuple[str, str, str]]:
    return _steps(_sequence_block(PACKET.read_text(encoding="utf-8"), "## 12A."))


@pytest.fixture(scope="module")
def index_steps() -> list[tuple[str, str, str]]:
    return _steps(
        _sequence_block(
            INDEX.read_text(encoding="utf-8"),
            "## 1. The sequence",
        )
    )


def test_the_operator_entry_point_exists() -> None:
    """A sequence assembled from three packets by each reader is a sequence that
    gets assembled differently by some reader."""
    assert INDEX.is_file(), (
        "docs/production-migration-execution-sequence.md is the single operator "
        "entry point for the migration programme. Do not delete it without moving "
        "the sequence somewhere and repointing this test."
    )


def test_both_documents_carry_the_same_number_of_steps(packet_steps, index_steps) -> None:
    assert len(packet_steps) == 11, (
        f"the 0005 packet's §12A sequence has {len(packet_steps)} steps, not 11. If a "
        "step was genuinely added, update the index in the same change and update "
        "this number — but read §12A's own note first: the ORDER is the safety "
        "property, so a new step needs an argument about where it goes."
    )
    assert len(index_steps) == len(packet_steps), (
        f"§12A has {len(packet_steps)} steps and the index has {len(index_steps)}. "
        "One document gained or lost a step without the other. The index is a "
        "consolidation of §12A, not an independent sequence."
    )


def test_every_step_number_and_action_is_identical(packet_steps, index_steps) -> None:
    """The reference column may differ; nothing else may.

    This is the assertion that makes the resolved cross-references safe. Without it,
    "resolve the references" is indistinguishable from "rewrite the sequence".
    """
    for position, (packet, index) in enumerate(zip(packet_steps, index_steps), start=1):
        assert packet[0] == index[0], (
            f"step {position} is numbered {packet[0]!r} in §12A and {index[0]!r} in "
            "the index"
        )
        assert packet[1] == index[1], (
            f"step {position}'s action reads {packet[1]!r} in §12A and {index[1]!r} "
            "in the index. Only the CROSS-REFERENCE column may differ between the "
            "two documents — the action a person performs may not."
        )


def test_the_two_bounded_commands_are_byte_identical_in_both(packet_steps, index_steps) -> None:
    """The two lines an operator types at a production database.

    A drifted ``--through`` bound is the most consequential divergence this pair
    could develop: with three approved-and-unapplied migrations on disk, a bound
    that moved would land a migration the operator did not intend to land, in a
    step that reads as verified.
    """
    for source, steps in (("§12A", packet_steps), ("the index", index_steps)):
        commands = [
            reference
            for _, _, reference in steps
            if reference.startswith("python scripts/db_migrate.py")
        ]
        assert commands == list(BOUNDED_COMMANDS), (
            f"{source} carries migration commands {commands!r}, expected "
            f"{list(BOUNDED_COMMANDS)!r}. Both the bound and its order are load-bearing: "
            "0003 and 0004 are ONE decision and must be applied together, and 0005 "
            "must be applied separately so its postchecks can attribute a failure."
        )


def test_the_index_never_shows_an_unbounded_apply() -> None:
    """The dangerous form is a SUBSTRING of the safe one.

    ``--apply`` once globbed every migration on disk, which made the documented
    operator ask mechanically impossible to satisfy. Today it would land three
    approved migrations in one unverifiable step. So the index must never show
    ``db_migrate.py --apply`` without a ``--through`` bound on the same line — and
    this is asserted positively, because searching for the safe string would match
    inside the dangerous one and pass.
    """
    offenders = [
        line.strip()
        for line in INDEX.read_text(encoding="utf-8").splitlines()
        if "db_migrate.py --apply" in line and "--through" not in line
    ]
    assert offenders == [], (
        "the operator entry point shows an UNBOUNDED --apply: "
        f"{offenders!r}. Every documented invocation must carry --through."
    )


def test_the_index_does_not_read_as_an_authorization_or_as_applied() -> None:
    """Two invariants, not two literals.

    The index must not read as though the migrations have been applied, and must not
    read as though publishing the sequence authorizes running it. Owner approval of
    bytes is a PRECONDITION for the operator's act, never a substitute — and this
    document is the one an operator opens first, so it is the worst place for either
    misreading.
    """
    text = INDEX.read_text(encoding="utf-8")
    assert "NOTHING HAS BEEN APPLIED ANYWHERE" in text, (
        "the operator entry point must state plainly that nothing is applied. A "
        "sequence document that omits its own status reads as a record of work done."
    )
    assert "No agent may" in text, (
        "CLAUDE.md §15's hard stop must be restated here. This is the document an "
        "operator — or an agent — opens first."
    )


def test_the_index_cites_a_guard_THAT_EXISTS() -> None:
    """A document pointing at a test that does not exist is a dead reference.

    THIS TEST EXISTS BECAUSE THE INDEX SHIPPED WITH EXACTLY THAT DEFECT. Its first
    draft named
    ``test_experiment_repository.py::test_the_canonical_migration_sequence_matches_the_0005_packet``
    — a file that is real and a test inside it that never existed, because the guard
    had been moved into its own module and the prose was not updated with it. A
    reader following that citation to check whether the sequence is pinned would
    have found nothing and reasonably concluded it was not.

    That is the same class of defect as a stale count, and cheaper to prevent: the
    citation is a PATH, so it can be resolved.
    """
    text = INDEX.read_text(encoding="utf-8")
    cited = re.findall(r"`(apps/api/tests/[A-Za-z0-9_./]+\.py)[^`]*`", text)
    assert cited, (
        "the index no longer cites the guard that pins it against §12A. A reader "
        "cannot verify the two documents are kept in step without being told where "
        "that is asserted."
    )
    repo = Path(__file__).resolve().parents[3]
    for path in cited:
        assert (repo / path).is_file(), (
            f"the index cites {path!r}, which does not exist. Repoint the prose; do "
            "not delete the citation."
        )
