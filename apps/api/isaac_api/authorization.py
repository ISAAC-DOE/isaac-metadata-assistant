"""Machine-readable record of what the record-verification programme may do.

WHY A MODULE AND NOT A PARAGRAPH
================================
Until 2026-08-05 the answer to "may the verification engine read the
application's own datastore?" lived in prose — ``docs/dean-authorization-packet.md``
said Q19 was NOT SENT, ``verification.py``'s docstring repeated it, and
``test_verification.py`` asserted a one-member mode tuple with a comment
pointing at a line number in a Markdown file. Three copies of one fact, none of
them derived from the others.

That is exactly the shape that drifts. This module is the single machine-readable
source: ``verification.VERIFICATION_MODES`` is *computed* from
:func:`verification_modes`, so a mode cannot exist unless the flag that permits
it is set here, and ``test_authorization_state.py`` fails if the two ever
disagree.

WHAT WAS APPROVED, AND HOW IT REACHED THIS FILE
===============================================
:data:`APPROVAL_DATE` and :data:`APPROVAL_SOURCE` are the whole provenance, and
the source string is deliberately blunt: the approval was **relayed by the
project owner**. No agent spoke to the database owner, no transcript exists in
this repository, and none is quoted here. A future session must read
:data:`APPROVAL_SOURCE` as testimony, not as a captured artifact — the same
distinction ``CLAUDE.md`` §15 draws about the one observed reconnaissance scan
and about the Authentik header probe.

WHAT IS *NOT* APPROVED IS AS LOAD-BEARING AS WHAT IS
====================================================
:data:`NOT_AUTHORIZED` is not decoration. An approval to compute aggregates over
a corpus is routinely misread as an approval to *show* the corpus, and this
project has already shipped that mistake once (the five aggregates withdrawn in
``v0.0.32``; ``CLAUDE.md`` §15, gate G3). Per-record display remains closed by
default, and nothing here reopens it.

Q20 — arming JSON Schema ``format`` enforcement in the official validator — is
**separately unanswered**. The two questions were deliberately not bundled
(``docs/dean-authorization-packet.md:6``), so an answer to one is not an answer
to the other. :data:`Q20_FORMAT_ENFORCEMENT_APPROVED` is ``False`` and the format
shadow stays advisory; ``tests/test_truthpath_characterization.py`` is the
mechanical proof and is not modified by the slice that added this file.

NO DATABASE HERE
================
This module holds constants. It opens no connection, imports no driver, reads no
environment variable and knows no hostname. Scoped to THIS MODULE, per
``CLAUDE.md`` §15: the honest form is "no connection is opened here", never "the
database has never been contacted".
"""

from __future__ import annotations

__all__ = [
    "APPROVAL_DATE",
    "APPROVAL_SOURCE",
    "AUTHORIZED_PRIVATE_SAMPLE_MODE",
    "DATASTORE_CONSTRAINTS",
    "NOT_AUTHORIZED",
    "PUBLIC_REFERENCE_MODE",
    "Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED",
    "Q20_FORMAT_ENFORCEMENT_APPROVED",
    "authorization_record",
    "verification_modes",
]

# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

#: The date the approval was recorded in this repository. It is the date of the
#: RELAY, which is the only event this repository can witness.
APPROVAL_DATE = "2026-08-05"

#: How the approval reached this file. Verbatim, and deliberately unflattering:
#: it names the gap rather than papering over it.
APPROVAL_SOURCE = (
    "relayed by the project owner; no direct agent-to-owner communication occurred"
)

#: The committed question this approval answers. The packet is the wording that
#: was approved; it is not restated here, so there is one copy of it.
APPROVAL_QUESTION_REFERENCE = "docs/dean-authorization-packet.md (Q19)"

#: Where the approval is recorded in prose, for a human reader.
APPROVAL_EVIDENCE_DOCUMENT = "docs/evidence/2026-08-05-q19-q20-authorization.md"


# --------------------------------------------------------------------------
# The flags. One boolean per independently-decided capability.
# --------------------------------------------------------------------------

#: Q19: may the verification engine draw its records from the application's own
#: datastore, read-only, emitting aggregates only? APPROVED.
#:
#: **LOAD-BEARING.** :func:`verification_modes` reads it, and
#: ``db_provider.DatastoreRecordProvider.records`` re-checks it before opening
#: anything. Setting it ``False`` removes the mode from the engine and refuses
#: the provider. It is not documentation.
Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED = True

#: Q20: may JSON Schema ``format`` enforcement be armed in the official
#: validator? NO ANSWER WAS RELAYED. The two questions were explicitly not
#: bundled, so Q19's approval says nothing about this one.
#:
#: **DESCRIPTIVE, NOT LOAD-BEARING — and the asymmetry with Q19 above is the
#: whole reason this note exists.** Nothing reads this flag except
#: :func:`authorization_record`. Setting it ``True`` changes no behaviour: it
#: would NOT arm ``format`` enforcement, because arming it requires two
#: independent code changes elsewhere — a ``format_checker=`` on the validator
#: in ``src/isaac_records/official.py`` AND the ``jsonschema[format]`` extra in
#: ``pyproject.toml``, neither of which this module can reach, and fixing either
#: alone changes nothing (``docs/dean-authorization-packet.md`` Q20).
#:
#: It sits here so the two decisions are recorded in one place. Do not read the
#: symmetry of the two names as a symmetry of effect, and do not "enable Q20" by
#: flipping this — that would produce a record claiming an approval was acted on
#: while the validator stayed format-blind.
Q20_FORMAT_ENFORCEMENT_APPROVED = False


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------

#: The corpus that needs no authorization at all: the public upstream ISAAC
#: example records vendored under ``tests/fixtures/official/`` and already
#: published on GitHub (``schema/PROVENANCE.md``).
PUBLIC_REFERENCE_MODE = "public_reference"

#: The corpus Q19 authorizes: records drawn from the application's own datastore,
#: read-only, one at a time, aggregated, and discarded. The name says
#: "authorized" because the mode may not exist unless the flag above is set, and
#: it says "sample" because it is a bounded page of that datastore, never the
#: claim of a census.
AUTHORIZED_PRIVATE_SAMPLE_MODE = "authorized_private_sample"


def verification_modes() -> tuple[str, ...]:
    """The verification modes this build is permitted to offer.

    ``verification.VERIFICATION_MODES`` is assigned from this call. The
    consequence is the point: flipping
    :data:`Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED` to ``False`` removes
    the datastore mode from the engine, from the served contract, and from the
    mode a caller may ask for — it does not merely disable it.

    The authorization audit is explicit that "a disabled runner is a runner
    someone enables"
    (``docs/superpowers/plans/2026-08-02-corpus-validation-authorization.md:221-223``),
    so the withdrawal path is absence, not a switch.
    """
    modes = [PUBLIC_REFERENCE_MODE]
    if Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED:
        modes.append(AUTHORIZED_PRIVATE_SAMPLE_MODE)
    return tuple(modes)


# --------------------------------------------------------------------------
# The constraints the owner imposed, transcribed as data
# --------------------------------------------------------------------------

#: Every constraint attached to the Q19 approval, in the owner's terms. These
#: are implemented literally in ``db_provider.py``; the module docstring there
#: names which function discharges which line. They live here as data so a
#: reviewer can diff intent against implementation instead of reading both and
#: hoping.
DATASTORE_CONSTRAINTS: tuple[str, ...] = (
    "One short-lived connection per aggregate run. The deployment's connection "
    "limit is 5, so the run must never approach it. 'Short-lived' is measured "
    "against the FETCH, not the sweep: the rows are drained and the connection "
    "closed before any record is validated or mutated, so a multi-minute sweep "
    "never holds an open transaction.",
    "An explicit transaction. Read-only is declared twice — through the driver "
    "(set_session(readonly=True)) and through SET TRANSACTION READ ONLY.",
    "Read-only is VERIFIED server-side: the session reads back "
    "SHOW transaction_read_only and refuses to proceed unless it is 'on'.",
    "Conservative statement_timeout and lock_timeout, set with SET LOCAL so they "
    "expire with the transaction.",
    "Deterministic rollback and close in a finally block. There is no autocommit "
    "path.",
    "Every statement is a module-level frozen constant. Every value is "
    "parameterized; no value is ever interpolated into SQL.",
    "A query-policy guard rejects INSERT, UPDATE, DELETE, MERGE, CREATE, ALTER, "
    "DROP, TRUNCATE, COPY and CALL, temporary tables, sequence functions, "
    "';'-chaining, and any statement not in the frozen set.",
    "A caller can never supply SQL, an identifier, a pointer, a path, a mode, or "
    "a schema location.",
    "The identifier column is CHAR(26) and blank-padded. Strip the padding, then "
    "drop the identifier before yielding, so no caller ever receives it.",
    "Exactly one parsed record is yielded at a time. The whole parsed corpus is "
    "never retained, and neither is any structure derived from it: the consumer "
    "aggregates each record's result and discards it.",
    "Cross-references pointing outside the sample are EXPECTED. Tolerate a "
    "missing referenced row; never repair it, never follow it, never report it.",
    "The driver is imported lazily, so the module imports cleanly when the driver "
    "is absent and the run then reports a safe 'unavailable' state.",
)

#: What the Q19 approval does NOT extend to. Read this before adding anything.
NOT_AUTHORIZED: tuple[str, ...] = (
    "Per-record display of datastore content — record ids, titles, field values, "
    "evidence entries, exports or any per-record outcome. Closed by default "
    "pending an explicit visibility decision (docs/postgres-test-db-guide.md).",
    "Any write of any kind: INSERT, UPDATE, DELETE, DDL, temporary tables, or a "
    "durable record repository.",
    "Any connection originating from a laptop or from CI, and any local "
    "kubeconfig, port-forward or Secret retrieval. That prohibition is a project "
    "rule and does not depend on the datastore being unreachable "
    "(docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52).",
    "Restoring the five aggregates withdrawn in v0.0.32 — by_instance_path, "
    "distinct_structural_signatures, total_link_count, dangling_link_count and "
    "vocabulary_term_count. Gate G3 is still open.",
    "Caller-parameterized aggregation, cross-tabulation, or any histogram cell "
    "below the disclosure floor (baseline matrix §4.3).",
    "Arming JSON Schema 'format' enforcement in the official validator. That is "
    "Q20, it was not bundled with Q19, and no answer has been relayed.",
    "Phase 37 as a feature phase: portal integration, persistence, API keys, "
    "identity/role enforcement, or an external model provider.",
)


def authorization_record() -> dict:
    """The whole authorization state as one plain, serializable mapping.

    Nothing here is derived from a record, an environment variable, or a
    connection — it is a projection of this module's own constants, so it is
    safe to log, serve, or embed in a report. It is deliberately NOT wired into
    the verification envelope: that envelope's key set is frozen, and widening it
    is a contract change, not a convenience.
    """
    return {
        "approval_date": APPROVAL_DATE,
        "approval_source": APPROVAL_SOURCE,
        "approval_question_reference": APPROVAL_QUESTION_REFERENCE,
        "approval_evidence_document": APPROVAL_EVIDENCE_DOCUMENT,
        "aggregate_datastore_verification_approved": bool(
            Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED
        ),
        "format_enforcement_approved": bool(Q20_FORMAT_ENFORCEMENT_APPROVED),
        "verification_modes": list(verification_modes()),
        "datastore_constraints": list(DATASTORE_CONSTRAINTS),
        "not_authorized": list(NOT_AUTHORIZED),
    }
