"""THE STRUCTURED ISAAC EXTENDED CONTEXT COMPANION — `DEC-41` level 4, `CTX-002`.

WHAT THIS IS, IN ONE SENTENCE
============================

A **companion artifact** carrying the scientifically useful metadata the official ISAAC
v1.05 record has no field for, structured and provenance-backed, in the same
architectural class as the evidence sidecar (``CLAUDE.md`` §4) — *"which already carries
what the official record cannot"*.

WHAT IT IS NOT, AND WHY EACH DENIAL IS STRUCTURAL RATHER THAN PROMISED
======================================================================

* **It is not a record field, and it never enters the official record.** Nothing in this
  module produces an ISAAC record fragment, no entry carries a value at an official
  path, and :attr:`ContextEntry.official_path` is present only so a reader can see
  *where the schema's home for this concept is* — it is a pointer to the registry, not a
  destination for the literal beside it.
* **It never gates export.** Not "is not currently wired to gating": it is not
  reachable from the export path at all. :data:`STATE_KEY` sits BESIDE ``draft`` in the
  experiment state document, exactly where ``proposals.STATE_KEY`` sits and for the
  identical reason — *"the draft is what export reads"*, so choosing a location with no
  leak to disclose makes the inertness structural rather than asserted. A record is
  exportable or not on the official schema alone.
* **It is not an ISAAC standard.** ``CLAUDE.md`` §4's sentence about the evidence
  sidecar applies verbatim: it is an assistant audit artifact *"unless mentors approve
  it as an official ISAAC convention"*. This repository must not describe it as one.
* **It is not a prose dump.** `DEC-41`: every entry keeps its concept, its raw literal,
  its source and its locator. All four are **required at construction**, so an entry
  that cannot say where it came from cannot exist.

WHY A READER CANNOT MISTAKE IT FOR AN OFFICIAL FIELD VALUE
==========================================================

Three mechanisms, not one sentence of copy:

1. every entry serializes ``is_official_field_value: False``, and the flag is refused if
   a caller tries to set it — the same shape ``conflict_resolution`` already uses for a
   human decision that carries a value and is still not the field's value;
2. the document's own envelope carries :data:`NOT_OFFICIAL_CLAIM` and an
   ``artifact_kind`` of :data:`ARTIFACT_KIND`, which appears nowhere in the official
   schema;
3. the companion is written to its **own filename** —
   ``records/<ULID>.context.json``, beside ``<ULID>.json`` and
   ``<ULID>.evidence.json`` — so the two are not even in the same document.

`DEC-41`'s FIRST RULE IS ENFORCED HERE, BECAUSE HERE IS WHERE IT CAN BE BROKEN
=============================================================================

*"Never skip a level to reach 4 when a real field exists."* A registry row cannot
violate it (``bl15.mapping.ConceptMapping.placement_level`` is derived from the paths,
so no row states a level at all). A **companion entry** can: writing a concept in here
at level 4 when the schema has a field for it is how information silently stops being
offered at the field it belongs in. So every entry's level is checked against the
registry by :func:`bl15.mapping.check_placement`, and a mismatch **raises**.

Pure functions and frozen dataclasses only. No I/O, no clock, no id minting: the caller
supplies ``generated_utc`` and every ``entry_id``, exactly as ``notes.py``,
``proposals.py`` and ``conflict_resolution.py`` require, so this module is testable
without a workspace and cannot reach a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .bl15 import evidence as ev
from .bl15 import mapping as mp

__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_VERSION",
    "COMPANION_SUFFIX",
    "ContextEntry",
    "ExtendedContext",
    "NOT_OFFICIAL_CLAIM",
    "SCOPES",
    "SCOPE_EXPERIMENT",
    "SCOPE_RUN",
    "STATE_KEY",
    "UnsupportedContextEntry",
    "companion_filename",
    "entry_from_source_evidence",
    "hydrate",
    "state_payload",
]


#: The artifact's own name on the wire and on disk. Deliberately not a word the official
#: schema uses anywhere, so a reader who greps a payload for it finds only this.
ARTIFACT_KIND = "isaac_extended_context"

#: The COMPANION FORMAT's version, and it is not the record's ``schema_version``.
#:
#: Two versions travel with every entry and they answer different questions: this one
#: says *"what shape is this document"*, and ``profile_version`` says *"under which
#: reading of a filename convention was this literal produced"*. A profile whose alias
#: table changes meaning bumps the second and not the first — which is the whole reason
#: ``bl15.profiles`` versions itself, so that a record imported last month can be told
#: apart from the same file read under a revised convention.
#:
#: Bump this when the DOCUMENT shape changes in a way a reader of version N could
#: misread. Adding a key is not that; changing what a key means is.
ARTIFACT_VERSION = "1"

#: ``records/<ULID>.json`` -> ``records/<ULID>.context.json``. A SIBLING, chosen to read
#: the same way ``.evidence.json`` does, because the two artifacts are the same kind of
#: thing and a scientist should not have to learn two conventions.
COMPANION_SUFFIX = ".context.json"

NOT_OFFICIAL_CLAIM = (
    "This is an ISAAC Extended Context companion, not an official ISAAC record and not "
    "part of one. Nothing in it is a field value, nothing in it was validated against "
    "the official ISAAC schema, and nothing in it makes a record exportable or "
    "un-exportable: a record is exportable or not on the official schema alone. It "
    "exists because ISAAC v1.05 is the interoperable baseline rather than the ceiling, "
    "and discarding scientifically useful metadata for want of a core field would lose "
    "the science. Each entry records what a source said, verbatim, and where it said it."
)

#: Experiment-scoped: the statement is about the whole experiment. A beamtime-wide
#: reading lands here rather than being copied onto every Run — copying it would be a
#: lie about where it came from, which is the same reason ``bl15.reconstruct`` keeps
#: shared context shared.
SCOPE_EXPERIMENT = "experiment"
#: Run-scoped: the statement is about ONE acquisition, and :attr:`ContextEntry.run_id`
#: says which.
SCOPE_RUN = "run"

SCOPES: frozenset[str] = frozenset({SCOPE_EXPERIMENT, SCOPE_RUN})

#: The experiment state document's top-level key, BESIDE ``draft`` and never inside it.
#:
#: ``proposals.STATE_KEY``'s reasoning applies unchanged and is the reason this location
#: was chosen rather than the convenient one: the draft is what export reads, so an
#: extended-context key inside it would travel into ``export_draft`` and into the
#: submission content signature, and "level 4 never gates export" would become a
#: property of the export code rather than of the document. Out here it is structural.
#:
#: Three consequences, stated rather than left to be discovered: extended context is not
#: visible to ``export.transform``, is not in any run's ``resolved_run_draft``, and is
#: not in the submission content signature. And **no migration is required** —
#: ``Experiment.from_state`` reads every optional key with ``.get`` and a default, so a
#: document written before this existed hydrates to an empty companion.
#: ``db_write.OWNED_TABLES`` is UNCHANGED and no table is added.
STATE_KEY = "extended_context"


class UnsupportedContextEntry(ValueError):
    """A stored entry this build cannot read. Carried, never discarded.

    ``CLAUDE.md`` §11's rule, applied here: *a malformed value in a REQUEST can be
    refused, because the caller sent it; a malformed value already PERSISTED cannot be
    refused to the reader, who did nothing wrong and whose record would simply vanish.*
    So :func:`hydrate` returns the raw entry beside the ones it could read.
    """


@dataclass(frozen=True)
class ContextEntry:
    """ONE piece of extended context, with everything needed to audit it.

    The four `DEC-41` requires — :attr:`concept`, :attr:`raw_literal`, :attr:`source`,
    :attr:`locator` — are **required and non-empty**. That is the difference between a
    structured companion and a prose dump, and it is enforced rather than documented.
    """

    #: Stable within one import/companion build. Supplied by the caller, never minted
    #: here, so this module stays a pure function of its input.
    entry_id: str
    #: One of :data:`bl15.evidence.CONCEPTS`, or a concept the registry has not
    #: examined. An unexamined concept is permitted — and then level 4 is the only
    #: placement :func:`bl15.mapping.check_placement` will accept, because nobody has
    #: established a home for it.
    concept: str
    #: **VERBATIM, AND NEVER REPLACED.** ``ffilter35`` stays ``ffilter35``; the cleaner
    #: reading goes in :attr:`normalized_value` with :attr:`normalization_rule` beside
    #: it. Rewriting the source destroys the only thing that lets a scientist disagree.
    raw_literal: str
    #: WHERE FROM — the scientist's own handle on the source. An archive-relative path,
    #: a document name. Never an opaque id.
    source: str
    #: WHERE IN IT — a header key, a line number, a filename character span, a macro
    #: block. Scientist-readable, not a byte offset alone.
    locator: str
    #: `DEC-41`'s level, 1-4, checked against the registry at construction.
    placement_level: int
    scope: str = SCOPE_EXPERIMENT
    #: Required when :attr:`scope` is :data:`SCOPE_RUN`, refused otherwise.
    run_id: str | None = None
    #: What kind of source it is; one of :data:`bl15.evidence.SOURCE_TYPES` when it came
    #: from a BL15 reader. Recorded so a scientist can weigh it themselves, and
    #: deliberately not an authority ranking.
    source_type: str = ev.SOURCE_TYPE_UNKNOWN
    #: The cleaned reading, when a stored NAMED rule produced one.
    normalized_value: Any = None
    unit: str | None = None
    #: REQUIRED whenever :attr:`determinism` is not ``read`` — an unexplained
    #: normalisation is indistinguishable from a guess, which ``CLAUDE.md`` §5 forbids.
    normalization_rule: str | None = None
    determinism: str = ev.DETERMINISM_READ
    #: The naming profile in force and its version, when a profile was consulted.
    profile_id: str | None = None
    profile_version: str | None = None
    #: How widely the source's own statement applies; one of
    #: :data:`bl15.evidence.SCOPES`. NOT the same as :attr:`scope`: a beamtime-scope
    #: READING can be attached to one experiment, and conflating the two is how a
    #: shared README value comes to look like 94 manual entries.
    reading_scope: str | None = None
    parser_id: str | None = None
    #: An ISO-8601 UTC instant the SOURCE states, when it states one. Never a clock
    #: reading taken at build time.
    timestamp_utc: str | None = None
    #: Where the official schema's home for this CONCEPT is, per the registry — so a
    #: reader can see that a level-1 concept has a field and this entry is not it.
    #: **It is a pointer to the registry, never a destination for the literal.**
    official_path: str | None = None
    #: Why this is in the companion at all, in a sentence a scientist reads. The
    #: registry's own ``reason`` is the natural source.
    reason: str = ""
    #: Packet question ids still open for this concept, so a reader is not told to wait
    #: for an answer that has arrived. Derived from the registry when the entry is built
    #: by :func:`entry_from_source_evidence`.
    unresolved_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("entry_id", "concept", "raw_literal", "source", "locator"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"extended context entry needs a non-empty {name}: DEC-41 requires "
                    "concept, raw literal, source and locator on every entry"
                )
        if self.scope not in SCOPES:
            raise ValueError(f"unknown extended context scope: {self.scope!r}")
        if self.scope == SCOPE_RUN and not self.run_id:
            raise ValueError("a run-scoped entry must name its run_id")
        if self.scope == SCOPE_EXPERIMENT and self.run_id:
            raise ValueError(
                "an experiment-scoped entry must not name a run_id: a beamtime-wide "
                "statement attached to one run reads as though it had been entered there"
            )
        if self.determinism not in ev.DETERMINISM_KINDS:
            raise ValueError(f"unknown determinism: {self.determinism!r}")
        if self.determinism != ev.DETERMINISM_READ and not self.normalization_rule:
            raise ValueError(
                f"determinism {self.determinism!r} requires normalization_rule"
            )
        if self.reading_scope is not None and self.reading_scope not in ev.SCOPES:
            raise ValueError(f"unknown reading scope: {self.reading_scope!r}")
        if self.source_type not in ev.SOURCE_TYPES:
            raise ValueError(f"unknown source_type: {self.source_type!r}")
        # DEC-41's first rule. Raises PlacementSkipError, a ValueError subclass.
        mp.check_placement(self.concept, self.placement_level)

    @property
    def is_official_field_value(self) -> bool:
        """**Always ``False``, and derived so it cannot be persisted otherwise.**

        A stored boolean could be written ``True`` by a careless caller and would then
        travel on the wire saying the opposite of what this artifact is. Derived, with
        no field behind it, it is the same discipline ``ConceptMapping.proposable`` and
        ``conflict_resolution``'s ``is_field_value`` already use.
        """
        return False

    @property
    def placement_name(self) -> str:
        return mp.PLACEMENT_NAMES[self.placement_level]

    def to_state(self) -> dict:
        """The wire and on-disk shape. Every field, including the empty ones.

        Omitting ``None``s would make *"this reader looked and found no unit"*
        indistinguishable from *"this reader does not report units"*, and a review
        surface has to tell those apart — ``bl15.evidence.SourceEvidence.to_state``'s
        rule, for its reason.
        """
        return {
            "entry_id": self.entry_id,
            "concept": self.concept,
            "raw_literal": self.raw_literal,
            "source": self.source,
            "locator": self.locator,
            "placement_level": self.placement_level,
            "placement_name": self.placement_name,
            "scope": self.scope,
            "run_id": self.run_id,
            "source_type": self.source_type,
            "normalized_value": self.normalized_value,
            "unit": self.unit,
            "normalization_rule": self.normalization_rule,
            "determinism": self.determinism,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "reading_scope": self.reading_scope,
            "parser_id": self.parser_id,
            "timestamp_utc": self.timestamp_utc,
            "official_path": self.official_path,
            "reason": self.reason,
            "unresolved_questions": list(self.unresolved_questions),
            # Never a value at an official path. Derived; see the property.
            "is_official_field_value": self.is_official_field_value,
        }

    @classmethod
    def from_state(cls, raw: object) -> "ContextEntry":
        """Read one stored entry, or raise :class:`UnsupportedContextEntry`.

        Raises rather than coercing: a persisted entry this build cannot read is
        carried forward verbatim by :func:`hydrate`, which is the only honest thing to
        do with provenance nobody can interpret.
        """
        if not isinstance(raw, dict):
            raise UnsupportedContextEntry("an entry must be an object")
        known = {
            f
            for f in (
                "entry_id",
                "concept",
                "raw_literal",
                "source",
                "locator",
                "placement_level",
                "scope",
                "run_id",
                "source_type",
                "normalized_value",
                "unit",
                "normalization_rule",
                "determinism",
                "profile_id",
                "profile_version",
                "reading_scope",
                "parser_id",
                "timestamp_utc",
                "official_path",
                "reason",
            )
        }
        kwargs = {k: v for k, v in raw.items() if k in known}
        questions = raw.get("unresolved_questions")
        if isinstance(questions, (list, tuple)):
            kwargs["unresolved_questions"] = tuple(
                q for q in questions if isinstance(q, str)
            )
        try:
            return cls(**kwargs)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise UnsupportedContextEntry(str(exc)) from exc


def entry_from_source_evidence(
    item: ev.SourceEvidence,
    *,
    entry_id: str,
    scope: str = SCOPE_EXPERIMENT,
    run_id: str | None = None,
) -> ContextEntry:
    """Build one companion entry from ONE piece of read BL15 evidence.

    **This is the reuse `CTX-002` asks for and not a re-implementation.**
    ``bl15.evidence.SourceEvidence`` already records concept, raw literal, source and
    locator — the four `DEC-41` requires — plus the determinism, the named
    normalisation rule, the profile and its version. Every one of them is carried across
    unchanged; nothing is recomputed and no literal is rewritten.

    The placement level and the official path come from the registry, never from an
    argument, so a caller cannot choose a concept's level. That is what makes the
    level-4 skip unreachable through this constructor rather than merely checked in it.
    """
    entry = mp.mapping_for(item.concept)
    return ContextEntry(
        entry_id=entry_id,
        concept=item.concept,
        raw_literal=item.raw_literal,
        source=item.source_path,
        locator=item.locator,
        placement_level=(
            entry.placement_level if entry else mp.PLACEMENT_EXTENDED_CONTEXT
        ),
        scope=scope,
        run_id=run_id,
        source_type=item.source_type,
        normalized_value=item.normalized_value,
        unit=item.unit,
        normalization_rule=item.normalization_rule,
        determinism=item.determinism,
        profile_id=item.profile_id,
        profile_version=item.profile_version,
        reading_scope=item.scope,
        parser_id=item.parser_id,
        timestamp_utc=item.timestamp_utc,
        official_path=entry.official_path if entry else None,
        reason=entry.reason if entry else "",
        unresolved_questions=entry.unresolved_questions if entry else (),
    )


@dataclass(frozen=True)
class ExtendedContext:
    """One experiment's extended context: a queryable, versioned, scoped companion.

    Queryable means *by the three things a scientist asks about* — which run, which
    concept, which placement level — and each is a method rather than something a caller
    has to filter for itself, so every surface asks the same question the same way.
    """

    experiment_id: str
    entries: tuple[ContextEntry, ...] = ()
    #: ISO-8601 UTC, supplied by the caller. Empty is legal and means "not stamped":
    #: this module reads no clock.
    generated_utc: str = ""
    artifact_version: str = ARTIFACT_VERSION
    #: Stored entries this build could not read, carried verbatim. See
    #: :class:`UnsupportedContextEntry`.
    unreadable: tuple[dict, ...] = ()

    # --- queries ------------------------------------------------------------

    def for_run(self, run_id: str) -> tuple[ContextEntry, ...]:
        """Run-scoped entries for ONE run. Experiment-scoped entries are NOT included.

        Deliberate: a caller that wants "everything that applies to this run" wants
        :meth:`applying_to_run`, and the two are different claims. Merging them here
        would make a beamtime-wide reading indistinguishable from one taken on this run.
        """
        return tuple(
            e for e in self.entries if e.scope == SCOPE_RUN and e.run_id == run_id
        )

    def applying_to_run(self, run_id: str) -> tuple[ContextEntry, ...]:
        """Everything that applies to one run: its own entries plus the inherited ones.

        `DEC-40`'s posture, read-only: a run INHERITS what the experiment states and the
        inheritance is visible, because every entry still carries its own ``scope``.
        Nothing is copied and nothing is flattened.
        """
        return tuple(
            e
            for e in self.entries
            if e.scope == SCOPE_EXPERIMENT
            or (e.scope == SCOPE_RUN and e.run_id == run_id)
        )

    def experiment_scoped(self) -> tuple[ContextEntry, ...]:
        return tuple(e for e in self.entries if e.scope == SCOPE_EXPERIMENT)

    def for_concept(self, concept: str) -> tuple[ContextEntry, ...]:
        return tuple(e for e in self.entries if e.concept == concept)

    def at_level(self, level: int) -> tuple[ContextEntry, ...]:
        return tuple(e for e in self.entries if e.placement_level == level)

    def concepts(self) -> tuple[str, ...]:
        return tuple(sorted({e.concept for e in self.entries}))

    def run_ids(self) -> tuple[str, ...]:
        return tuple(sorted({e.run_id for e in self.entries if e.run_id}))

    def by_level(self) -> dict[str, int]:
        out = {str(level): 0 for level in mp.PLACEMENT_LEVELS}
        for e in self.entries:
            out[str(e.placement_level)] += 1
        return out

    def open_questions(self) -> tuple[str, ...]:
        """Packet question ids still open across these entries, sorted by number."""
        found = {q for e in self.entries for q in e.unresolved_questions}
        return tuple(sorted(found, key=lambda qid: int(qid[1:])))

    # --- serialization ------------------------------------------------------

    def to_state(self) -> dict:
        """The experiment state document's value for :data:`STATE_KEY`."""
        return {
            "artifact_kind": ARTIFACT_KIND,
            "artifact_version": self.artifact_version,
            "experiment_id": self.experiment_id,
            "generated_utc": self.generated_utc,
            "entries": [e.to_state() for e in self.entries],
            "unreadable": [dict(raw) for raw in self.unreadable],
        }

    def companion_document(self, record_id: str) -> dict:
        """The exported sibling artifact, for ``records/<ULID>.context.json``.

        It carries the RECORD id so it can be paired with the record, and
        :data:`NOT_OFFICIAL_CLAIM` so a reader who opens it alone cannot mistake it for
        one. It deliberately does **not** carry a ``schema_version``: the companion is
        not a schema-versioned ISAAC artifact and claiming a schema version would be the
        exact confusion this whole module exists to prevent.
        """
        return {
            "artifact_kind": ARTIFACT_KIND,
            "artifact_version": self.artifact_version,
            "record_id": record_id,
            "experiment_id": self.experiment_id,
            "generated_utc": self.generated_utc,
            "not_official": NOT_OFFICIAL_CLAIM,
            "placement_hierarchy": {
                str(level): mp.PLACEMENT_NAMES[level]
                for level in mp.PLACEMENT_LEVELS
            },
            "entry_count": len(self.entries),
            "entries_by_level": self.by_level(),
            "open_domain_questions": list(self.open_questions()),
            "entries": [e.to_state() for e in self.entries],
            "unreadable": [dict(raw) for raw in self.unreadable],
        }


def companion_filename(record_id: str) -> str:
    """``<ULID>`` -> ``<ULID>.context.json``. A sibling, never a field."""
    return f"{record_id}{COMPANION_SUFFIX}"


def hydrate(raw: object, *, experiment_id: str = "") -> ExtendedContext:
    """Read a stored companion. **Never raises, and never discards.**

    A malformed persisted document belongs to a reader who did nothing wrong
    (``CLAUDE.md`` §11), so anything unreadable is carried in
    :attr:`ExtendedContext.unreadable` rather than dropped or coerced. A value that is
    not a dict yields an empty companion — there is nothing to iterate — and a
    non-list ``entries`` yields no entries, for the same reason
    ``_hydrate_proposals`` gives.
    """
    if not isinstance(raw, dict):
        return ExtendedContext(experiment_id=experiment_id)
    entries: list[ContextEntry] = []
    unreadable: list[dict] = []
    stored = raw.get("entries")
    if isinstance(stored, list):
        for item in stored:
            try:
                entries.append(ContextEntry.from_state(item))
            except UnsupportedContextEntry:
                unreadable.append(
                    item if isinstance(item, dict) else {"unreadable_entry": item}
                )
    # THE `unreadable` KEY IS RE-READ, AND FORGETTING IT WAS A REAL DEFECT THIS
    # MODULE'S OWN TEST CAUGHT. The first version read only `entries`, so a companion
    # holding an uninterpretable entry lost it on the SECOND round trip: hydrate ->
    # to_state -> hydrate returned zero unreadable entries, and "never discards" was
    # false one save later rather than immediately, which is the version of that bug
    # nobody notices. Carried forward verbatim, exactly as it arrived.
    carried = raw.get("unreadable")
    if isinstance(carried, list):
        unreadable.extend(
            item if isinstance(item, dict) else {"unreadable_entry": item}
            for item in carried
        )
    version = raw.get("artifact_version")
    stored_id = raw.get("experiment_id")
    return ExtendedContext(
        experiment_id=(
            stored_id if isinstance(stored_id, str) and stored_id else experiment_id
        ),
        entries=tuple(entries),
        generated_utc=(
            raw.get("generated_utc")
            if isinstance(raw.get("generated_utc"), str)
            else ""
        ),
        artifact_version=version if isinstance(version, str) else ARTIFACT_VERSION,
        unreadable=tuple(unreadable),
    )


def state_payload(context: ExtendedContext | None) -> dict | None:
    """What to store at :data:`STATE_KEY`, or ``None`` when there is nothing to store.

    ``None`` rather than an empty document, so an experiment that has never had
    extended context stays byte-identical to one written before this module existed —
    which is what keeps "no migration is required" true rather than merely likely.
    """
    if context is None or (not context.entries and not context.unreadable):
        return None
    return context.to_state()


def build(
    *,
    experiment_id: str,
    entries: Iterable[ContextEntry],
    generated_utc: str = "",
) -> ExtendedContext:
    """Assemble a companion. Order is preserved; nothing is deduplicated.

    **Not deduplicated on purpose.** Sixteen scan files each recording one filter index
    is one fact with sixteen witnesses, and a companion that collapsed them would
    destroy fifteen locators — the opposite of what a provenance artifact is for.
    Grouping for display is a surface's job (``bl15.reconstruct`` groups candidates and
    keeps every statement, which is the same choice one layer up).
    """
    return ExtendedContext(
        experiment_id=experiment_id,
        entries=tuple(entries),
        generated_utc=generated_utc,
    )
