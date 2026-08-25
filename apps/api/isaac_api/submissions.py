"""The SUBMISSION domain: pure functions over export units. No I/O, no database.

WHAT LIVES HERE AND WHAT DOES NOT
=================================
This module answers four questions about a set of :class:`~isaac_api.workspace.
ExportUnit` objects, and nothing else:

  * :func:`content_signature` — what is the stable identity of this content?
  * :func:`conflict_summary` — which fields carry conflicting evidence?
  * :func:`field_values` / :func:`address_changes` — what changed since last time?
  * :func:`blocker_report` — why is this not submittable?

Every one of them is a pure function of its arguments. Nothing here opens a
connection, reads the filesystem, reads the environment, mints an id, or reads a
clock — the write path (:mod:`isaac_api.submission_store`) does all of that, and
keeping the split sharp is what makes these four testable without a database and
without a fixture workspace.

**It computes no verdict the truth core does not already produce.**
:func:`blocker_report` calls ``exp.pending_count()`` and
``isaac_records.export.export_draft`` — the same two checks the export route
already gates on — and reshapes their answers. It adds no rule of its own, and it
must never grow one: a submission is refused for exactly the reasons an export is
refused, and inventing a fifth reason here would create a state a scientist could
not resolve through any surface this application offers.

THE ONE DECISION IN THIS MODULE THAT IS NOT MECHANICAL
======================================================
``conflicting_evidence`` is **recorded and disclosed, never gated on**, and the
reason is measured rather than stylistic. ``evidence_classify._classify_entry``
rule 1 flags a field the moment two distinct non-null answers are recorded for it.
``routes._apply_run_field`` **appends** a ``user_confirmation`` entry every time and
never replaces one, and no route in this application removes an evidence entry. So
a scientist who answers a question, notices a typo, and answers it again has
manufactured a conflict **they cannot clear through any surface this build offers**.
Gating submission on it would be a permanent block produced by correcting a
mistake. :func:`conflict_summary` therefore reports it, the submission row stores
it, and the response discloses it — and none of that stops the submission.

**THE "CANNOT CLEAR IT" HALF IS NO LONGER TRUE, AND THE PARAGRAPH IS KEPT RATHER
THAN REWRITTEN, because the argument it makes is still the one that decides the
gating.** :mod:`isaac_api.conflict_resolution` gives a person an explicit way to
record which competing answer is right, so the defect above is addressable; the two
facts that made gating wrong are untouched. First, **nothing removes the competing
evidence**, so the classification stays ``conflicting_evidence`` forever and gating on
it would still be a permanent block. Second, **a resolution is not required**: a
scientist may legitimately submit with a conflict undecided, and ``deferred`` is a
recorded outcome precisely because declining to decide is allowed. So ``gating``
stays ``disclosed_not_gated`` — no committed sentence in this repository authorises a
gate — and what :func:`conflict_summary` gained is the ability to say *which* of the
conflicts somebody has already decided.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from isaac_records.export import export_draft

from . import evidence_classify
from . import serialize
from .workspace import REPO_ROOT

__all__ = [
    "CHANGE_ADDED",
    "CHANGE_KINDS",
    "CHANGE_MODIFIED",
    "CHANGE_REMOVED",
    "CONFLICT_SCOPE",
    "SIGNATURE_SCOPE",
    "TRUST_BASIS_UNATTRIBUTED",
    "UnitBlocker",
    "address_changes",
    "address_value_changes",
    "blocker_report",
    "canonical_json",
    "conflict_decisions",
    "conflict_summary",
    "content_signature",
    "field_values",
    "present_field_values",
    "unit_membership_changes",
    "unit_payloads",
    "units_by_id",
]


#: The trust basis recorded when NOBODY was established for a write.
#:
#: **Deliberately defined here and NOT added to
#: :data:`isaac_api.identity.RECOGNISED_TRUST_BASES`.** That set is the set of bases
#: a :class:`~isaac_api.identity.HumanActor` may CLAIM, and "nobody" is not a
#: person: widening it would make ``HumanActor(subject="x",
#: trust_basis="unattributed")`` constructible, which is precisely the shape —
#: a name nothing vouched for — that the whole identity seam exists to refuse.
#:
#: The database CHECK admits three values (this one plus the two recognised bases)
#: and pairs it with ``(trust_basis = 'unattributed') = (subject IS NULL)``, so an
#: unattributed row can never carry a name and a named row can never claim this
#: basis.
TRUST_BASIS_UNATTRIBUTED = "unattributed"

#: What :func:`content_signature` covers, echoed into the API response so a reader
#: never has to infer the scope of a digest from its name.
#:
#: **IT USED TO READ ``export_unit_ids_and_drafts``, AND THE VALUE MOVED BECAUSE THE
#: COVERAGE DID.** The digest now also covers the record's stored conflict decisions
#: — see :func:`content_signature` for the measured defect that forced it. The string
#: is served, so leaving it unchanged would have made the response describe a scope
#: one term narrower than the digest it labels.
SIGNATURE_SCOPE = "export_unit_ids_drafts_and_conflict_decisions"

#: What :func:`conflict_summary` looked at. Same reason.
CONFLICT_SCOPE = "draft_field_evidence"

CHANGE_ADDED = "added"
CHANGE_REMOVED = "removed"
CHANGE_MODIFIED = "modified"

#: Exactly the three values ``isaac_revision_changes.change_kind`` admits. Named
#: here so the Python and the SQL cannot drift; a test asserts the migration's CHECK
#: lists these three and no others.
CHANGE_KINDS: tuple[str, ...] = (CHANGE_ADDED, CHANGE_REMOVED, CHANGE_MODIFIED)


def canonical_json(value: Any) -> str:
    """One deterministic text form for any JSON value.

    ``sort_keys`` so key order cannot change a digest, ``separators`` with no
    whitespace so indentation cannot either, and ``ensure_ascii=False`` so a
    non-ASCII character has ONE encoding rather than two that hash differently
    depending on which writer produced the document.

    NO ``default=`` HANDLER, DELIBERATELY. Every draft in this application has
    round-tripped through JSON on the way out of the workspace file or the database,
    so a non-serialisable value is unreachable; adding a stringifying fallback would
    make two genuinely different objects hash identically in exchange for tolerating
    a state that cannot occur. If one ever does occur, a ``TypeError`` naming it is
    a better outcome than a signature that quietly means less than it says.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def unit_payloads(units: Sequence[Any]) -> list[dict]:
    """The signature-relevant projection of each export unit, ordered by unit id.

    ``unit_id`` is ``ExportUnit.target_id`` — a run's id for an experiment with
    runs, the experiment's own id for one without — and ``draft`` is the FULLY
    RESOLVED draft that unit would export, inheritance and overrides already
    applied. Those two are the whole of what becomes an official ISAAC record.

    THEY ARE NO LONGER THE WHOLE OF WHAT THE SIGNATURE COVERS, and this sentence used
    to say they were. :func:`content_signature` adds the record's conflict decisions
    as a component of its own; that component publishes no byte, and it is there
    because a submission row discloses THAT a conflict was decided. It is covered
    **verbatim**, which is broader than that disclosure — see that function, whose
    rule paragraph states the coverage and argues why the broader side is the safe
    one.

    Sorted by ``unit_id`` rather than left in ``sorted_runs()`` order on purpose:
    ``sorted_runs`` orders on ``(ordinal, created_utc, id)``, so REORDERING two runs
    changes that sequence without changing a single record. A signature that moved
    on a reorder would refuse a re-submission of content that is byte-identical
    record for record.
    """
    return sorted(
        (
            {
                "unit_id": unit.target_id,
                "run_id": unit.run_id,
                "draft": unit.draft,
            }
            for unit in units
        ),
        key=lambda payload: payload["unit_id"],
    )


def conflict_decisions(units: Sequence[Any]) -> Any:
    """The record's stored conflict decisions, VERBATIM, or ``None`` if it has none.

    READ OFF THE UNITS' EXPERIMENT RATHER THAN TAKEN AS A PARAMETER, and that is the
    one decision in this function. :func:`conflict_summary` takes its resolutions as
    an argument and says why; this one must not, because the digest it feeds decides
    whether a second submission may exist AT ALL. Three call sites in ``routes``
    compute the signature (submit, the history listing, the revision diff) and they
    have to agree: a parameter with a default of ``()`` would let one of them omit
    the decisions and report a digest the write path would never produce. Every unit
    of one record shares one :class:`~isaac_api.workspace.Experiment`, so the first
    unit answers for all of them.

    VERBATIM — the raw stored list, readable and unreadable entries alike, in stored
    order. Not the parsed :class:`~isaac_api.conflict_resolution.ConflictResolution`
    objects, for two reasons. An entry this build cannot read is still a recorded
    human decision, and a digest that skipped it would call two different documents
    the same content. And stored order is stable by construction:
    ``conflict_resolution.write_resolution`` upserts IN PLACE and preserves the
    position of every row, readable or not, precisely so that a byte-identical
    re-decision does not rewrite the document.

    AN EMPTY LIST AND AN ABSENT KEY ARE TREATED IDENTICALLY — both give ``None`` — and
    that conflation is deliberate rather than sloppy. Both mean the same thing about
    the science: this record carries no decision. Distinguishing them would make the
    digest of a record that has never had a decision depend on whether some earlier
    write happened to leave an empty list behind, which is a difference no reader of a
    submission could act on.
    """
    from . import conflict_resolution as cr  # noqa: PLC0415 - cycle; see conflict_summary

    if not units:
        return None
    draft = getattr(getattr(units[0], "experiment", None), "draft", None)
    if not isinstance(draft, dict):
        return None
    stored = draft.get(cr.DRAFT_KEY)
    return stored if stored else None


def content_signature(experiment_id: str, units: Sequence[Any]) -> str:
    """The stable sha256 identity of what a submission would publish and declare.

    WHAT IT COVERS: the experiment id, each export unit's id and fully resolved
    draft, and the record's stored conflict decisions. Nothing else.

    THE LAST OF THOSE THREE WAS ADDED TO CLOSE A MEASURED DEFECT, AND THE DEFECT IS
    WORTH STATING BECAUSE IT DECIDES WHAT THIS DIGEST IS FOR. One act — ``POST
    .../conflicts/resolve``, ``200`` — used to be recordable or unrecordable
    depending only on whether the record had runs:

      * a ZERO-RUN record's one unit draft IS ``exp.draft``, which is where
        ``conflict_resolution.write_resolution`` stores decisions, so a decision moved
        the digest and the resubmission that discloses it was accepted;
      * a record WITH RUNS composes its units from run drafts, and
        ``workspace.resolved_run_draft`` deliberately does not copy the record-level
        decisions key into one, so the digest did not move, the resubmission was
        refused ``already_submitted``, and ``isaac_submissions.conflict_summary`` —
        the ONE place a submission discloses that a person settled a conflicting
        field — could never be written again for that record. A record with runs is
        the shape this product normally produces.

    So the coverage was shape-dependent by accident, and the shape a scientist most
    often has was the one that lost the decision.

    IS A RESUBMISSION AFTER A DECISION A NEW SUBMISSION OR A DUPLICATE? A NEW ONE,
    and the reason is the row rather than the artifacts. A decision changes no
    exported byte — ``ConflictResolution.is_field_value`` is permanently ``False``,
    and no route republishes an immutable record — so if a submission were only its
    published records, this would be a duplicate. It is not: a submission row also
    carries ``conflict_summary``, and two rows that disagree about whether a human
    settled a conflicting field are not two copies of one declaration.

    ~~**The rule this digest now follows is: it covers what a submission DISCLOSES
    about itself — the records it publishes and the conflict state it reports — and
    nothing else.**~~ **THAT SENTENCE WAS NARROWER THAN THIS FUNCTION, and it is
    struck rather than deleted because the reasoning either side of it is still the
    reasoning that decides identity.** :func:`conflict_decisions` returns the stored
    decisions **VERBATIM** — ``rationale``, ``recorded_utc`` and the whole ``history``
    tuple included — and :func:`conflict_summary` reports none of those three: it
    discloses addresses, counts, and four fixed state words, and says in its own
    docstring that it carries "no value, no rationale text, no subject". So the digest
    is strictly BROADER than what a submission discloses, and describing it as the
    disclosure was a claim about a projection this function does not perform.

    **THE TRUE RULE: the digest covers what a submission PUBLISHES — each unit's id
    and fully resolved draft — plus the record's stored conflict decisions AS STORED,
    not a summary of them, and nothing else.** Over-inclusion is the safe direction
    here, and the two consequences it has are CHOSEN rather than incidental. Both were
    measured over HTTP and both are pinned by
    ``apps/api/tests/test_the_signature_covers_a_decision_verbatim.py``:

    * A **RATIONALE-ONLY** revision moves the digest. ``submit#3`` is accepted
      ``200``, revisions read ``[1, 2, 3]``, and submission 2's and submission 3's
      ``conflict_summary`` are byte-identical — the digest moved on something no
      disclosure column mentions.
    * **REVISE-THEN-REVERT** does not restore the earlier digest; it produces a THIRD
      distinct value, and revisions read ``[1, 2, 3, 4]``. The mechanism is
      ``conflict_resolution.revise_resolution``: it compares ``rationale`` when
      deciding whether an act changed anything, and any act that did APPENDS an
      ``ACTION_REVISE`` transition — so ``ConflictResolution.to_state()`` can never
      re-enter a value it has already had. A monotonically growing audit trail cannot
      be un-grown.

    WHY NARROWING THE DIGEST TO THE DISCLOSED SUMMARY WOULD BE WORSE, which is the
    argument for leaving it broad rather than an apology for it. Both consequences
    above fail **OPEN**: one extra submission row, no exported byte rewritten, nothing
    lost, and the row's own claims are all true. A digest over only
    ``conflict_summary``'s projection would fail **CLOSED**. A scientist who corrected
    the reason they had given, or who changed their mind and then changed it back,
    would get ``409 already_submitted`` — a refusal asserting the record is unchanged
    while the persisted document has moved, which is the exact defect the widening was
    made to fix, reintroduced one layer further in. Worse, a submission is the only
    durable declaration this application writes: the reconsideration would live in the
    decision's ``history`` and **no submission on file would ever attest that it
    happened**. Losing the record of a change of mind is the direction that hurts;
    writing an extra row that is true is not.

    That is also what keeps the exclusions below from looking arbitrary, on the
    corrected rule rather than the struck one: they are excluded because they are
    neither the published content nor a recorded decision — not because some
    disclosure column happens not to mention them.

    THE ONE THING THAT RULE MUST NOT BE READ AS SAYING, because a revision row does
    hold more than its disclosure columns: ``isaac_experiment_revisions.state``
    archives the WHOLE experiment document, notes and title included, so a second
    submission's snapshot would differ from the first's whenever anything at all had
    moved. That is deliberately not treated as new content. If it were, every note,
    every rename and every keystroke that touches the document would license another
    submission, and the digest would stop being an idempotency key. The archive
    records what the document held; the disclosure is what the submission CLAIMS, and
    only the second decides identity.

    WHAT IT DELIBERATELY EXCLUDES, AND WHY EACH EXCLUSION IS LOAD-BEARING:

    * ``notes``, the captured transcript, and everything else that lives in the
      experiment's STATE rather than in a unit draft or the decisions list. Measured,
      not assumed: capture a note after a submission and the digest does not move, so
      the resubmission is refused — correctly, because no column of the submission
      says anything about notes, and the second row would differ from the first in no
      claim a reader could act on.
    * ``rev``, ``updated_utc``, ``generation`` — they move on every save, including
      saves that change no record. A signature carrying them would differ between
      two submissions of identical science.
    * ``record_id`` — it is ``None`` before materialisation and set after it, on the
      very same content. Including it would mean the signature computed BEFORE the
      artifacts are written differs from the one computed AFTER, so a retry after a
      partial failure would look like new content and would write a second
      submission for one act. **Stability across materialisation is the property
      this exclusion exists to provide**, and it is what makes the signature usable
      as the natural idempotency key.

      *M4 — ONE DEGRADED CASE IN WHICH IT CAN STILL MOVE, AND IT IS NOT EXCLUDABLE
      HERE.* A unit's composed draft carries sibling ``links``, and
      ``workspace._linkable`` deliberately returns ``None`` for a MATERIALISED record
      that cannot be read or whose own ``record_id`` disagrees with the file carrying
      it — rather than falling back to the draft, which would restore a fabricated
      link. Such a unit drops out of its sibling group, the links composed into its
      siblings' drafts change, and the signature moves with them. So the claim holds
      **whenever every materialised record is readable and self-consistent**, which
      is every non-degraded case; against a corrupted or hand-edited artifact a retry
      can legitimately compute a different signature and record a second submission.
    * ``title`` — a record's title is workspace metadata and reaches no official
      record. Renaming a record and re-submitting therefore does NOT produce a new
      submission, and that is the honest answer: the content that was published is
      unchanged. Stated here because it is the one exclusion a reader might expect
      to go the other way.

    The digest is over :func:`canonical_json`, so it is stable across Python
    versions, dict insertion order, and whitespace.

    ONE REDUNDANCY, STATED RATHER THAN ENGINEERED AWAY. A zero-run unit's draft IS
    ``exp.draft``, so for that shape the decisions are inside ``units`` as well as in
    ``conflict_decisions`` — counted twice, which changes no outcome, because the
    question the digest answers is only ever "did this move". The alternative was to
    strip the key out of a copy of every unit draft, which buys tidiness in exchange
    for a per-unit deep copy and a second place where the digest's coverage is
    decided. Uniformity is what the fix needed, and the extra component provides it
    for BOTH shapes; counting the zero-run case once instead of twice would not make
    any record behave differently.

    NEITHER THE OLD NOR THE NEW DIGEST IS PERSISTED ANYWHERE TODAY, so widening the
    coverage — and moving :data:`SIGNATURE_SCOPE`, which is itself in the payload and
    therefore changes every digest value — invalidates no stored row.
    ``submission_store.store()`` has no filesystem fallback and returns ``None``
    without a database, and ``0003_revisions``/``0004_submissions`` are applied in no
    deployment, so no ``isaac_submissions`` row exists to compare against.
    """
    payload = {
        "experiment_id": experiment_id,
        "scope": SIGNATURE_SCOPE,
        "units": unit_payloads(units),
        "conflict_decisions": conflict_decisions(units),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def field_values(draft: Mapping[str, Any] | None) -> dict[str, str]:
    """``address -> canonical JSON of that field's value``, for present values only.

    A field is PRESENT when its envelope carries a non-``None`` ``value``. An
    envelope with ``value: null`` — the shape a ``needs_confirmation`` blocker has —
    is absent here rather than present-and-null, so answering a blocker reads as
    ``added`` and clearing an answer reads as ``removed``, which is what a reader
    means by both words.

    THE SCOPE IS NARROW AND IS THE SAME ONE ``0003_revisions.sql`` WRITES DOWN. Only
    ``draft["fields"]`` is examined. Evidence entries, run overrides, answer logs,
    assets and implicit claims are NOT compared, and neither is anything nested
    inside a value beyond that value's canonical form. So an empty change set means
    "no field value differed", never "nothing changed".
    """
    fields = (draft or {}).get("fields")
    if not isinstance(fields, dict):
        return {}
    out: dict[str, str] = {}
    for address, envelope in fields.items():
        if not isinstance(address, str) or not address:
            continue
        if not isinstance(envelope, dict):
            continue
        value = envelope.get("value")
        if value is None:
            continue
        out[address] = canonical_json(value)
    return out


def address_changes(
    previous: Mapping[str, Mapping[str, Any] | None] | None,
    current: Mapping[str, Mapping[str, Any] | None],
) -> list[tuple[str, str, str]]:
    """``(unit_id, address, change_kind)`` triples, sorted, for two unit->draft maps.

    ``previous`` of ``None`` means there is no comparable predecessor — the first
    revision of an experiment, or one whose stored predecessor could not be read.
    **It yields an EMPTY list, not "everything was added"**, and the difference
    matters: an initial submission did not ADD three hundred fields to anything, and
    a caller must be able to tell "nothing differed" from "there was nothing to
    differ from". The route discloses which of the two happened; this function
    simply does not invent a baseline it was not given.

    A unit present in one map and absent from the other contributes one row per
    field value it holds, so adding a run reads as that run's fields being added.
    """
    if previous is None:
        return []
    out: list[tuple[str, str, str]] = []
    for unit_id in sorted(set(previous) | set(current)):
        was = field_values(previous.get(unit_id))
        now = field_values(current.get(unit_id))
        for address in sorted(set(was) | set(now)):
            if address not in was:
                out.append((unit_id, address, CHANGE_ADDED))
            elif address not in now:
                out.append((unit_id, address, CHANGE_REMOVED))
            elif was[address] != now[address]:
                out.append((unit_id, address, CHANGE_MODIFIED))
    return out


def present_field_values(draft: Mapping[str, Any] | None) -> dict[str, Any]:
    """The SAME addresses :func:`field_values` reports, carrying the RAW values.

    :func:`field_values` returns each value's canonical JSON *text*, which is what a
    change comparison needs and is deliberately all it needs. A surface that shows a
    scientist what a field used to hold needs the value itself, so that it can be
    rendered by the same rules every other value on that surface is rendered by
    (one line for a scalar; "cannot be shown in one line" for an object).

    **IT IS NOT A SECOND DEFINITION OF "PRESENT".** The presence rule is
    :func:`field_values`' rule, restated in one place and pinned in another:
    ``test_revision_history`` asserts, over a matrix of drafts, that
    ``{k: canonical_json(v) for k, v in present_field_values(d).items()}`` equals
    ``field_values(d)`` exactly. If the two ever diverge, that test fails rather
    than a diff quietly disagreeing with the change log stored beside it.
    """
    fields = (draft or {}).get("fields")
    if not isinstance(fields, dict):
        return {}
    out: dict[str, Any] = {}
    for address, envelope in fields.items():
        if not isinstance(address, str) or not address:
            continue
        if not isinstance(envelope, dict):
            continue
        value = envelope.get("value")
        if value is None:
            continue
        out[address] = value
    return out


def address_value_changes(
    previous: Mapping[str, Mapping[str, Any] | None] | None,
    current: Mapping[str, Mapping[str, Any] | None],
) -> list[dict]:
    """:func:`address_changes`, plus the two values — for a surface, not for a row.

    Returns dicts of ``{unit_id, address, change_kind, previous_value,
    current_value}``, in the SAME order and with the SAME membership as
    :func:`address_changes`. That equality is not asserted by construction — the two
    functions are written out separately — it is asserted by test, over a matrix of
    inputs, because a diff shown to a scientist that disagreed with the change rows
    stored in ``isaac_revision_changes`` would be the worse kind of wrong: both
    plausible, and only one of them written down.

    WHY NOT SIMPLY EXTEND :func:`address_changes`. That function is on the
    SUBMISSION WRITE PATH — its output becomes ``isaac_revision_changes`` rows inside
    the one durable transaction — and this slice adds a read surface. Changing the
    shape a write path emits in order to serve a screen is how a read requirement
    ends up embedded in a durable record. So the write path is left exactly as it
    was, and the drift risk that creates is paid for with a test rather than with a
    refactor.

    ``previous`` of ``None`` yields an empty list for the reason
    :func:`address_changes` yields one: **there was nothing to compare against**, and
    that is not the same statement as "nothing changed". Every caller must disclose
    which of the two it is reporting.

    THE VALUES ARE THE DRAFT'S OWN, UNTRANSFORMED. Nothing here rounds, formats,
    truncates, units-converts or summarises a scientific value; a value too large or
    too structured to render is a rendering decision made where the rendering happens.
    """
    if previous is None:
        return []
    out: list[dict] = []
    for unit_id in sorted(set(previous) | set(current)):
        was_text = field_values(previous.get(unit_id))
        now_text = field_values(current.get(unit_id))
        was_raw = present_field_values(previous.get(unit_id))
        now_raw = present_field_values(current.get(unit_id))
        for address in sorted(set(was_text) | set(now_text)):
            if address not in was_text:
                kind = CHANGE_ADDED
            elif address not in now_text:
                kind = CHANGE_REMOVED
            elif was_text[address] != now_text[address]:
                kind = CHANGE_MODIFIED
            else:
                continue
            out.append(
                {
                    "unit_id": unit_id,
                    "address": address,
                    "change_kind": kind,
                    # `None` HERE MEANS "NOT RECORDED AT THAT POINT", and it can only
                    # occur on the side the change kind already says is absent —
                    # `field_values` excludes an envelope whose `value` is null, so a
                    # present value is never `None`. The two facts therefore agree
                    # rather than needing a reader to reconcile them.
                    "previous_value": was_raw.get(address),
                    "current_value": now_raw.get(address),
                }
            )
    return out


def unit_membership_changes(
    previous: Mapping[str, Any] | None, current: Mapping[str, Any]
) -> dict:
    """Which export units this record gained and lost since a stored revision.

    An export unit is a RUN for a record that has them, and the record itself for one
    that does not (``workspace.ExportUnit``), so for the fan-out case this is exactly
    "which runs were added and which were removed".

    IT IS REPORTED SEPARATELY FROM THE FIELD CHANGES RATHER THAN FOLDED INTO THEM.
    :func:`address_changes` already contributes one ``added``/``removed`` row per
    field value a unit holds, so a removed run appears there as forty removed fields
    — which is true, and is not the sentence a reader wants first. "One run was
    removed" and "forty values are no longer recorded" are the same event described
    at two altitudes, and a surface that only had the second would make the reader
    reconstruct the first.

    ``previous`` of ``None`` yields empty lists and ``comparable: false``, for the
    reason :func:`address_changes` yields an empty list: there was no baseline.
    """
    if previous is None:
        return {"comparable": False, "added": [], "removed": [], "unchanged": []}
    was = set(previous)
    now = set(current)
    return {
        "comparable": True,
        "added": sorted(now - was),
        "removed": sorted(was - now),
        "unchanged": sorted(now & was),
    }


def conflict_summary(units: Sequence[Any], resolutions: Sequence[Any] = ()) -> dict:
    """Which fields carry conflicting evidence, per unit, and which were DECIDED.

    RECORDED, NEVER GATING — see the module docstring, whose argument survives the
    arrival of conflict resolution intact.

    Reuses :func:`isaac_api.evidence_classify.classify_fields`, which is the one
    definition of ``conflicting_evidence`` in this application — recomputing the
    rule here would create a second definition that could disagree with the one the
    Evidence screen shows. Resolution state is delegated the same way, to
    ``conflict_resolution.state_of``.

    THE OUTPUT CARRIES ADDRESSES AND COUNTS, NEVER VALUES, AND THAT IS UNCHANGED.
    The conflicting values are in the revision snapshot beside this row, and the
    ``GET .../conflicts`` resolution surface serves them because a scientist cannot
    choose between answers they are not shown. Copying them into a disclosure column
    would put scientific content into a field whose job is navigation, and would give
    the same value two places to live. ``resolution_states`` is a map of address to a
    ``conflict_resolution.RESOLUTION_STATES`` member — four fixed words, no value, no
    rationale text, no subject.

    ``resolutions`` IS PASSED IN RATHER THAN READ OFF THE UNIT, and the asymmetry is
    the reason. A resolution lives at the RECORD level (one list, run-scoped rows
    distinguished by ``run_id``), and ``workspace.resolved_run_draft`` does not copy
    that key into a run's composed draft — so for a fan-out experiment ``unit.draft``
    carries no resolutions at all, while for a zero-run experiment ``unit.draft`` IS
    ``exp.draft`` and carries them. Reading from the unit would therefore have
    reported resolutions for one record shape and silently none for the other. The
    default of ``()`` keeps this function callable without them, and a caller that
    omits them gets ``absent`` for every address — honest, and visibly so, because
    ``resolutions_supplied`` says which happened.

    A resolution matches a unit when its ``run_id`` is the unit's OR is ``None``: an
    inherited experiment-level address is decided once, at the record, and the run
    that inherits it inherits the decision with the value. That is the same
    inheritance ``resolve_inherited`` already implements for the value itself.

    ``gating`` is stated IN THE DATA rather than left to documentation, because this
    object is stored and is read back by surfaces that were not written today. A
    reader who finds a non-zero count must be able to see, from the object itself,
    that it did not block anything.
    """
    from . import conflict_resolution as cr  # noqa: PLC0415 - see below
    from . import serialize as _serialize  # noqa: PLC0415

    # LAZY IMPORTS, because `conflict_resolution` imports this module (for
    # `canonical_json` and `TRUST_BASIS_UNATTRIBUTED`) and a module-level import here
    # would close the cycle. The direction is deliberate: the digest and the
    # unattributed basis are this module's, and a domain module reading them is
    # better than a second copy of either.
    supplied = list(resolutions)
    affected: list[dict] = []
    total = 0
    tally = {state: 0 for state in cr.RESOLUTION_STATES}
    for unit in units:
        classified = {
            entry["field"]: entry
            for entry in evidence_classify.classify_fields(unit.draft)
            if isinstance(entry.get("field"), str)
        }
        addresses = sorted(
            field
            for field, entry in classified.items()
            if entry.get("classification") == "conflicting_evidence"
        )
        if not addresses:
            continue
        total += len(addresses)
        evidence_by_address = {
            str(item.get("path")): item.get("evidence") or []
            for item in _serialize.evidence_trail_from_draft(unit.draft)
        }
        scoped = [
            resolution
            for resolution in supplied
            if resolution.run_id in (unit.run_id, None)
        ]
        states = {}
        for address in addresses:
            state = cr.state_of(
                cr.find(scoped, address, unit.run_id)
                or cr.find(scoped, address, None),
                cr.competing_from_evidence(evidence_by_address.get(address)),
            )
            states[address] = state
            tally[state] += 1
        affected.append(
            {
                "unit_id": unit.target_id,
                "run_id": unit.run_id,
                "addresses": addresses,
                "resolution_states": states,
            }
        )
    return {
        "scope": CONFLICT_SCOPE,
        "gating": "disclosed_not_gated",
        "conflicting_field_count": total,
        # WHETHER THE CALLER SUPPLIED ANY DECISIONS AT ALL. Without it, "nothing was
        # resolved" and "nobody asked about resolutions" are the same bytes, and only
        # the first is a statement about the record.
        "resolutions_supplied": bool(supplied),
        "resolved_field_count": tally[cr.RESOLUTION_CURRENT],
        "deferred_field_count": tally[cr.RESOLUTION_DEFERRED],
        "stale_resolution_count": tally[cr.RESOLUTION_STALE],
        # `stale` counts as unresolved, deliberately and in one place: a decision made
        # over a different competing set does not cover the conflict a reader sees.
        "unresolved_field_count": total - tally[cr.RESOLUTION_CURRENT],
        "affected_units": affected,
    }


class UnitBlocker(dict):
    """One unit's reason for not being submittable. A plain ``dict`` subclass.

    A ``dict`` rather than a dataclass because it goes straight into a JSON response
    body and a dataclass would need a second serialiser; a NAMED type rather than a
    bare dict so the shape has somewhere to be documented.
    """


def blocker_report(exp: Any, units: Sequence[Any]) -> dict:
    """Why this experiment cannot be submitted, per unit. Writes nothing.

    THE GATE IS EXACTLY EXPORT-READINESS AND NOTHING MORE:

      1. ``exp.pending_count() == 0`` over ALL units — every unanswered blocker, the
         experiment's own and its runs'.
      2. Every unit's ``export_draft`` DRY RUN passes.

    Those are the same two conditions ``Experiment.export_ready()`` composes into a
    boolean; this returns the same answer with the per-unit detail a refusal needs,
    so a scientist is told WHICH run refused rather than only THAT one did.

    **M5 — THE HEADING USED TO READ "EXACTLY THE EXISTING EXPORT GATE", AND THAT
    OVERSTATED IT BY ONE CONDITION.** It is exactly ``Experiment.export_ready()``,
    which is not the same as what ``POST /api/experiments/{id}/export`` enforces:
    that route has no ``pending_count()`` check anywhere and will publish a record
    with unanswered questions. So submission adds no rule beyond export-readiness,
    but it is stricter than the export ROUTE by condition 1. The wording is corrected
    rather than deleted because the claim it makes — "no fifth reason, no Submit
    Anyway" — is the one that matters and is still true.

    ``export_draft`` is called WITHOUT ``record_id``, matching
    ``Experiment._all_units_pass_dry_run`` exactly. Passing the id would
    additionally fail any unit whose id is not a ULID, which would make this
    stricter than the readiness the rest of the application reports — a gate that
    refuses what ``status()`` calls ``ready_to_export`` is a gate nobody can satisfy.

    THERE IS NO OVERRIDE, NO FORCE PARAMETER AND NO "SUBMIT ANYWAY", by contract §3
    D4: a required validation failure on any run blocks the whole submission. This
    function has no argument by which one could be requested.

    NEVER RAISES. ``export_draft`` is a pure transform plus two validations, but a
    malformed persisted draft is a reachable input, and a submission refusal that
    500s tells the reader nothing. A unit whose dry run raises is reported as
    blocked, naming the exception CLASS only — never its message, which can carry a
    filesystem path.
    """
    pending = list(exp.pending())
    unit_blockers: list[UnitBlocker] = []
    for unit in units:
        try:
            result = export_draft(unit.draft, REPO_ROOT)
            ok = bool(result.ok)
            errors = _dry_run_errors(result)
        except Exception as exc:  # noqa: BLE001 - see the docstring
            ok = False
            errors = [f"the export gate could not be evaluated ({type(exc).__name__})"]
        if ok:
            continue
        unit_blockers.append(
            UnitBlocker(
                {
                    "unit_id": unit.target_id,
                    "run_id": unit.run_id,
                    "run_label": unit.run_label,
                    "errors": errors,
                }
            )
        )
    return {
        "pending_count": len(pending),
        "pending": pending,
        "failing_units": unit_blockers,
        "blocked": bool(pending) or bool(unit_blockers),
    }


def _dry_run_errors(result: Any) -> list:
    """The flat error list for one dry run, official errors first. JSON-READY.

    Mirrors ``routes._flat_export_errors``' precedence — official errors when the
    record was built and refused, otherwise the draft errors that stopped it being
    built at all — rather than importing it, because importing from ``routes`` into
    a domain module would make the domain depend on the HTTP layer.

    IT READS THE SERIALISED REPORT, NOT THE RAW ONE, AND THAT IS NOT A DETAIL.
    ``ExportResult.official_report.errors`` holds ``OfficialError`` DATACLASSES, and
    the first version of this function returned them straight into a response body.
    ``json.dumps`` raised ``TypeError: Object of type OfficialError is not JSON
    serializable`` inside Starlette's renderer, so the refusal that exists to
    explain WHY a submission was blocked arrived as a bare HTTP 500 — measured, not
    theorised. ``serialize.export_result_to_dict`` is the one place this project
    turns those reports into JSON, and going through it is what makes the two
    branches of the refusal produce the same shape.
    """
    payload = serialize.export_result_to_dict(result)
    official = payload.get("official_report")
    if official and official.get("errors"):
        return list(official["errors"])
    draft_report = payload.get("draft_report")
    if draft_report is not None and not getattr(result.draft_report, "ok", True):
        return list(draft_report.get("errors") or [])
    return []


def units_by_id(units: Iterable[Any]) -> dict[str, dict]:
    """``unit_id -> resolved draft``, the shape :func:`address_changes` compares."""
    return {unit.target_id: unit.draft for unit in units}
