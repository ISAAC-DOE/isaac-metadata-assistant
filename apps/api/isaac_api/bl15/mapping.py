"""Corpus concept -> official ISAAC v1.05 path. A REGISTRY, not a converter.

**This module maps and refuses to map. It never decides a scientific question**, and
five of its outcomes are ways of saying "not here" — which is the point. A registry
that only recorded successes would tell a scientist nothing about the part of a
historical corpus the schema has no home for, and this corpus has a lot of it.

The analysis behind every entry, with each path and enum walked out of
``schema/isaac_record_v1.json`` rather than recalled, is
``docs/bl15-2-schema-mapping-analysis-2026-09-16.md``. Read it before changing a row.

**THE SCHEMA IS THE AUTHORITY** (``CLAUDE.md`` §1). Nothing here validates, accepts, or
refuses a value on the schema's behalf: :func:`mapping_for` answers *"is there a path for
this concept, and what is the warrant"*, and the official validator answers whether a
value at that path is any good. Two different questions, kept apart on purpose.

**The most important thing in this file is §3 of that analysis, so it is restated here:
the schema already carries vocabulary for saying a value is NOT KNOWN, and this corpus's
central gap is exactly that.** A filename says ``850mV`` and says nothing about what it is
measured against. ``context.electrochemistry.potential_scale``'s six members are each a
specific claim with no "unknown" member — so the honest act is to leave that field
**absent**, not to pick one. Meanwhile
``context.electrochemistry.potential_vs_RHE.rhe_basis`` offers ``not_reported`` and
``not_convertible_no_reference_offset`` verbatim, with ``value_V`` nullable. So *"no RHE
value, and here is why"* is a complete, valid statement, and §5's no-guessing rule is
satisfiable without leaving the record silent about why.

**A magnitude with no scale is therefore the CORRECT mapping of this corpus, not an
incomplete one**, and :data:`MAPPINGS` says so with two separate entries rather than one
entry with a hole in it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import evidence as ev

# --- mapping status ----------------------------------------------------------
#
# All five are FIRST-CLASS OUTCOMES. None of them is a failure, and a consumer that
# treated the last three as "not done yet" would be wrong about all three.

#: A source states it and one official path takes it as-is.
STATUS_DETERMINISTIC = "deterministic"
#: A source states it and a NAMED rule carries it across (``mV`` -> V, ``p`` -> decimal
#: point, a doubled-prefix typo). The rule travels with the value; the literal survives.
STATUS_NORMALIZED = "normalized"
#: The schema has a path and choosing among its options is a scientific judgement this
#: repository may not make. **Not a gap to be closed by a later slice** — it is closed by
#: a domain owner answering, and `docs/bl15-2-domain-questions-2026-09-16.md` is the ask.
STATUS_NEEDS_DOMAIN_REVIEW = "needs_domain_review"
#: The official schema has no field for this concept at all. Preserved as source evidence.
#: **Inventing a path is forbidden** (``CLAUDE.md`` §5); requesting one is upstream's
#: decision (§1).
STATUS_NOT_EXPRESSIBLE = "not_expressible"
#: The schema HAS a path and THIS BUILD cannot reach it. Distinct from
#: :data:`STATUS_NOT_EXPRESSIBLE` because the remedy is different: an application change,
#: not a schema request. Today this is ``assets[]`` and nothing else — see
#: :data:`ASSETS_BLOCKED_REASON`.
STATUS_BLOCKED_BY_BUILD = "blocked_by_build"

MAPPING_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_DETERMINISTIC,
        STATUS_NORMALIZED,
        STATUS_NEEDS_DOMAIN_REVIEW,
        STATUS_NOT_EXPRESSIBLE,
        STATUS_BLOCKED_BY_BUILD,
    }
)

#: Statuses that may carry a value toward a candidate. The other three carry a REASON.
PROPOSABLE_STATUSES: frozenset[str] = frozenset(
    {STATUS_DETERMINISTIC, STATUS_NORMALIZED}
)


# --- DEC-41: the four-level placement hierarchy ------------------------------
#
# A STATUS says whether a value can travel. A PLACEMENT says WHERE the information
# lands. They are different questions and the registry answered only the first until
# `CTX-001`: 40 of 45 concepts carried a refusal reason and no home at all, which is
# exactly the "shrug" `DEC-41` exists to replace.
#
# `ISAAC_PRODUCT_DECISIONS.md` §B4 `DEC-41`, verbatim in order: (1) a native official
# ISAAC field where one genuinely fits; (2) a schema-approved configuration/extension
# point; (3) Run / series conditions where the value is genuinely per-acquisition;
# (4) a structured ISAAC Extended Context companion.
#
# **THE LEVEL IS DERIVED, NOT TRANSCRIBED**, for the reason `CONCEPT_POINT_COUNT`'s own
# entry gives about the scan-point count: a stored level beside the paths that decide it
# would be a second place for one fact to be wrong. :attr:`ConceptMapping.placement_level`
# reads the paths this registry already declares — every one of which
# :func:`registry_paths_exist` checks against the vendored schema at runtime — so a
# schema refresh moves the levels and cannot leave a stale one behind.
#
# **AND THAT IS WHAT MAKES `DEC-41`'s FIRST RULE STRUCTURAL.** "Never skip a level to
# reach 4 when a real field exists" cannot be violated by a registry row, because no row
# states a level. It CAN be violated by a consumer that writes an entry into the
# companion claiming level 4 for a concept the schema has a field for, which is the
# defect the rule names — so the enforcement lives at that boundary
# (:func:`check_placement`, called by :mod:`isaac_api.extended_context`).

#: A native official ISAAC v1.05 field the schema declares for this concept.
PLACEMENT_OFFICIAL_FIELD = 1
#: The schema's own designated open extension namespace. Not a fallback: the schema
#: describes it as the home for configuration that does not generalize across
#: facilities, which is what a filter index and a spectrometer crystal are.
PLACEMENT_SCHEMA_EXTENSION_POINT = 2
#: A genuinely per-acquisition operating condition, at a schema-legal series home.
PLACEMENT_RUN_SERIES_CONDITION = 3
#: The structured ISAAC Extended Context companion — the same architectural class as
#: the evidence sidecar (``CLAUDE.md`` §4), and **never** a record field.
PLACEMENT_EXTENDED_CONTEXT = 4

PLACEMENT_LEVELS: tuple[int, ...] = (
    PLACEMENT_OFFICIAL_FIELD,
    PLACEMENT_SCHEMA_EXTENSION_POINT,
    PLACEMENT_RUN_SERIES_CONDITION,
    PLACEMENT_EXTENDED_CONTEXT,
)

#: **NOT A PLACEMENT, AND THAT IS `DEC-41`'s OWN WORDING.** It is what an OPEN domain
#: question renders as: unresolved evidence, waiting on a person.
#:
#: Read the distinction precisely, because collapsing it is the easy mistake here. Every
#: EXAMINED CONCEPT has a placement level 1-4 — `DEC-41` settles placement for all of
#: them, which is the half of the domain packet it closed. What is still unresolved is a
#: set of **questions**, eight of them, and a question is not a concept: a concept can
#: sit at level 1 with a real native field and still have its enum member blocked on
#: Angel (``potential_reference_basis`` is exactly that). So a consumer shows *"level 1,
#: and the member is blocked on Q9"* rather than ``"-"``, because that is the true state
#: and the two facts move independently.
PLACEMENT_UNRESOLVED = "-"

PLACEMENT_NAMES: dict[int, str] = {
    PLACEMENT_OFFICIAL_FIELD: "native official ISAAC v1.05 field",
    PLACEMENT_SCHEMA_EXTENSION_POINT: "schema-approved extension point",
    PLACEMENT_RUN_SERIES_CONDITION: "Run / series condition",
    PLACEMENT_EXTENDED_CONTEXT: "structured ISAAC Extended Context companion",
}

#: The schema's designated open extension namespace, read as a PREFIX so
#: ``system.configuration.slit_width`` places at level 2 as well as the bare object.
EXTENSION_NAMESPACE = "system.configuration"
#: The schema-legal per-acquisition condition home level 3 is about.
SERIES_CONDITIONS_HOME = "measurement.series[].conditions"


ASSETS_BLOCKED_REASON = (
    "The official schema requires both assets[].uri and assets[].sha256. This build "
    "does not publish either for a historical source: a manifest digest is only ever "
    "what the scientist stated, never one this application computed, and the location "
    "of a file inside an archive is not a URI anything outside this working area could "
    "resolve. So a historical file cannot become an official asset entry without this "
    "application asserting two things it has no standing to assert. The asset "
    "content_role vocabulary otherwise fits this corpus exactly (raw_data_pointer, "
    "reduction_product, calibration_reference), which is why this is named as a "
    "boundary rather than left to surface as a failing export."
)

#: ~~"this build computes no digest for any historical source — not even for a file it
#: reads"~~ — **THAT WAS THE REASON ABOVE UNTIL 2026-09-16, AND IT WENT FALSE ON THIS
#: BRANCH.** Found by independent review, which measured 14 member digests computed
#: while this sentence was being served to a scientist on the same payload.
#:
#: The archive walk computes a SHA-256 per member, and it must: content hashing is the
#: only thing that stops the corpus doubling (94 measurements became 181 without it) and
#: the only correct way to recognise the 96 duplicate groups. So the digest now EXISTS,
#: and the blocker is no longer its absence.
#:
#: **The conclusion did not change and the reason had to.** What blocks an asset entry is
#: a POLICY about publishing, not an arithmetic gap: a manifest ``sha256`` is "what the
#: scientist said", and a computed one published in the same field would put two meanings
#: behind one name — which is the argument ``historical_import`` has made since
#: ``HIST-001``. The ``uri`` half is new here and is the firmer of the two: an archive
#: member's path resolves nowhere outside this working area.
#:
#: This is the sibling of the claim the wiring slice corrected one module away, and it is
#: another instance of §15's incomplete-correction-sweep pattern — made worse by
#: ``test_bl15_mapping.py``'s pinning this constant to ONE home, which guaranteed the
#: false text was byte-identical in both places it was served.
#:
#: **Consequence worth naming rather than leaving implied:** a future slice COULD reach
#: ``assets[]`` for an archive member, by deciding that a computed digest may be published
#: in a field distinguishable from a stated one, and by giving the member a resolvable
#: URI. Both are decisions; neither is blocked by a missing number.
_ASSETS_BLOCKED_REASON_CORRECTION = "2026-09-16"

#: **NARROWED 2026-09-17 BY `DEC-43`, AND THE OLD SENTENCE IS KEPT INSIDE THE NEW ONE
#: RATHER THAN DELETED.** This text is SERVED TO SCIENTISTS (``historical_import``'s
#: ``_mapping_block`` renders it on the corpus-review screen), and until `CTX-003` it
#: said flatly that *"298 must not be defaulted into context.temperature_K"* — which is
#: still exactly right about the PARSER and became wrong as a blanket statement the day
#: the project owner adopted 298 as domain guidance for one profile. A screen that kept
#: saying the unqualified version would be telling a scientist the opposite of the
#: standing decision.
#:
#: The measurement behind it has not moved an inch and is restated first: **the corpus
#: states no temperature anywhere.** What moved is the AUTHORITY — see
#: :mod:`bl15.nominal`, where the value, its nominal basis and its
#: profile scope live, and where ``measured`` is a derived, always-``False`` property.
#:
#: ***SUPERSEDED 2026-09-22, AND THE 2026-09-17 SENTENCE IS KEPT BELOW, STRUCK, RATHER
#: THAN DELETED.*** The domain owner (Angel), relayed by the project owner, reconsidered
#: the 298 K exception: missing data stays missing, 293 K may be the commoner "room
#: temperature", and published work / NIST should be checked. The check found both 293.15
#: and 298.15 K are real conventions answering different questions
#: (``docs/evidence/temperature-convention-research-2026-09-22.md``). The retired text
#: read, in full: ~~"... ONE NARROW EXCEPTION, ADDED 2026-09-17: for the BL15-2
#: Angel-style historical profile, and for no other profile, the project owner has
#: adopted 298 K as a nominal room-temperature assumption (DEC-43). It is recorded as
#: nominal, domain-supplied and NOT measured, on the scientist's authority rather than
#: the parser's; under any other profile the field stays absent and the record stays
#: blocked, exactly as described above."~~
#:
#: ***CORRECTED 2026-09-22 — TRUE FOR EVERY ARCHIVE, NOT ONLY THE SUPPLIED ONE.*** The
#: sentence used to open "this corpus states no temperature anywhere — not in the
#: beamtime README, not in the notes, not in any acquisition header". That was measured
#: of the supplied archive and it is still true of it, but this constant is served for
#: EVERY archive (as ``mapping.temperature_absent_reason`` and as the first of
#: ``corpus_digest.cannot_be_export_ready``), including one whose notes say "held at
#: room temperature throughout" — for which it denied the very statement shown beside
#: it. The export BLOCKING is unchanged and is what the sentence now states: whatever a
#: source says about temperature, in words or on a labelled line, is kept verbatim and
#: never converted, so nothing here supplies ``context.temperature_K``.
#:
#: ***CORRECTED AGAIN 2026-09-23, after an independent review.*** The 2026-09-22 wording
#: said "No source here supplies that number: a corpus either states no temperature at
#: all, or states one only as words" — a universal claim, false for a labelled number
#: (``notes._TEMPERATURE_LABEL`` matches ``Temperature: 298 K``). The true statement is
#: about THIS BUILD, not the sources: it converts none of them.
TEMPERATURE_ABSENT_REASON = (
    "context.temperature_K is required by the official schema whenever a context block "
    "is present, and it takes a number in kelvin. This build converts no source "
    "statement into context.temperature_K: whatever a source says about temperature — "
    "'room temperature', 'RT', or a labelled Temperature: line, including a labelled "
    "number — is kept verbatim in the extended context and never converted. The field "
    "is therefore left MISSING "
    "and shown as Not recorded, or as the source's own words where it has some: this "
    "application inserts no value and offers no value automatically, because a "
    "plausible number in a required field is a fabricated measurement that nothing "
    "downstream can tell from a measured one, and 298 must not be defaulted into "
    "context.temperature_K by this application. A nominal number may be OFFERED only "
    "by a reviewed convention rule that names its convention (NTP-style 293.15 K or "
    "SATP-style 298.15 K), labels it nominal and inferred, and waits for a scientist to "
    "confirm it; no such rule is enabled. The 2026-09-17 exception that supplied 298 K "
    "for one profile (DEC-43) was withdrawn on 2026-09-22 by the domain owner's answer."
)

CYCLING_STATE_NO_FIELD_REASON = (
    "The official schema has no field for electrochemical cycling history "
    "(beforeCycling / after1500Cycling / after1stCycling). It is the single most "
    "important experimental variable in this corpus, which makes it the strongest "
    "schema-request case the corpus produced — and a schema request is upstream's "
    "decision, not this repository's. measurement.series[].conditions is a schema-legal "
    "candidate home for it as a per-series condition; nothing here places it there."
)

SYSTEM_CONFIGURATION_CAUTION = (
    "The schema describes system.configuration as 'THE designated open extension "
    "namespace' for instrument- and station-specific configuration that does not "
    "generalize across facilities — naming slits, pass energies and logbook fields, "
    "which is what a filter index and a spectrometer crystal are. So a natural home "
    "exists. BUT the six system.configuration.* fields are recorded as unclassified "
    "with the domain owner's classification outstanding, and no write route in this "
    "build accepts them. Candidate home; NOT a settled mapping and not writable today."
)


# --- the domain packet, reconciled ------------------------------------------
#
# `docs/bl15-2-domain-questions-2026-09-16.md` asks twenty numbered questions. On
# 2026-09-17 **twelve closed and eight did not**, and the registry has to be able to say
# which is which — because a row that keeps presenting a CLOSED question as blocked is
# telling a scientist to wait for an answer that has arrived.
#
# **The evidentiary classes are different and are recorded separately on purpose**, in
# the same spirit as `CLAUDE.md` §15's treatment of Dean's answers: a question closed by
# a domain owner, by reading a document, and by a product decision are three different
# kinds of closed, and a reader weighing one is owed which it is.
#
# **What this does NOT do: it moves no status.** A question closing does not make a value
# proposable — the packet's own §1 says an answer moves one row "from
# `needs_domain_review` to `deterministic` or `normalized`", and that move requires the
# ANSWER'S CONTENT, which for the document-closed questions is scientific text this
# repository may not commit (the characterization document's §0 boundary). So the twelve
# are recorded as closed and every status is exactly as it was.

QUESTION_CLOSED_BY_DOMAIN_OWNER = "closed_by_domain_owner"
QUESTION_CLOSED_BY_DOCUMENT = "closed_by_beamtime_document"
QUESTION_CLOSED_BY_PRODUCT_DECISION = "closed_by_product_decision"
QUESTION_CLOSED_BY_EXISTING_RULE = "closed_by_existing_rule"
QUESTION_OPEN_NEEDS_DOMAIN_OWNER = "open_needs_domain_owner"

# --- added 2026-09-22, for Angel's reply to Q9/Q11/Q14/Q15/Q16 -------------------
#
# FIVE NEW WAYS TO BE CLOSED, because "closed_by_domain_owner" would have flattened five
# genuinely different answers into one word. A reader weighing a closed question is owed
# WHICH kind of closed it is: an answer that settles a mapping, an answer that settles a
# mapping only per Run and only when evidence supports it, an answer that says "leave it
# missing", a policy with an advisory layer, and "I do not know". Each is a real answer
# and none of them makes a value proposable.

#: The domain owner answered with a RULE whose outcome depends on each Run's evidence —
#: Q11: the HERFD primary signal is selected per Run by :mod:`bl15.signals`, which
#: suggests a channel only when the evidence supports one and otherwise leaves it
#: unresolved for review.
QUESTION_CONDITIONALLY_RESOLVED = "conditionally_resolved"
#: The domain owner's answer is that, when a source does not state it, the field stays
#: MISSING and the user updates it later — never guessed (Q9 when no basis is stated;
#: Q14's QC verdict, whose free-text remarks are kept as Data Quality Notes instead).
QUESTION_INTENTIONALLY_LEFT_MISSING = "intentionally_left_missing"
#: A POLICY was adopted in place of a precedence rule: preserve every source, show the
#: disagreement, choose nothing — plus a clearly labelled non-authoritative
#: recommendation when independent evidence supports one (Q15, :mod:`bl15.resolution`).
QUESTION_POLICY_ADOPTED = "policy_adopted_with_non_authoritative_recommendation"
#: The domain owner does not know. The conflict is PERMANENTLY PRESERVED and nothing is
#: ever chosen (Q16 — the two legacy-32 acquisitions).
QUESTION_DOMAIN_OWNER_DOES_NOT_KNOW = "domain_owner_does_not_know_conflict_preserved"

QUESTION_DISPOSITIONS: frozenset[str] = frozenset(
    {
        QUESTION_CLOSED_BY_DOMAIN_OWNER,
        QUESTION_CLOSED_BY_DOCUMENT,
        QUESTION_CLOSED_BY_PRODUCT_DECISION,
        QUESTION_CLOSED_BY_EXISTING_RULE,
        QUESTION_OPEN_NEEDS_DOMAIN_OWNER,
        QUESTION_CONDITIONALLY_RESOLVED,
        QUESTION_INTENTIONALLY_LEFT_MISSING,
        QUESTION_POLICY_ADOPTED,
        QUESTION_DOMAIN_OWNER_DOES_NOT_KNOW,
    }
)

#: Where the 2026-09-22 answers came from, attached to every question they moved.
#: An owner relay of a domain owner's words — the evidentiary class `DEC-47` records.
ANGEL_2026_09_22 = (
    "Angel (domain owner), relayed by the project owner on 2026-09-22. No transcript is "
    "committed; only Krish can confirm the relay and only Angel the content."
)

#: The scientist-facing name for what the corpus calls quality remarks.
DATA_QUALITY_NOTES_LABEL = "Data Quality Notes"


@dataclass(frozen=True)
class DomainQuestion:
    """One numbered question from the domain packet, and what became of it."""

    question_id: str
    #: The subject in a few words, matching the packet's own table so the two can be
    #: read side by side.
    subject: str
    disposition: str
    #: What closed it, or what is still being asked. One sentence, no scientific value:
    #: the packet is the place that argues it, this is the place that records it.
    note: str
    #: WHO answered it and how that reached this repository, when a person did. ``None``
    #: for a question closed by a document, a product decision or an existing rule.
    attribution: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in QUESTION_DISPOSITIONS:
            raise ValueError(
                f"{self.question_id}: unknown disposition {self.disposition!r}"
            )

    @property
    def is_open(self) -> bool:
        return self.disposition == QUESTION_OPEN_NEEDS_DOMAIN_OWNER

    @property
    def placement(self) -> int | str:
        """``"-"`` while open. **A question is never given a level 1-4** — see
        :data:`PLACEMENT_UNRESOLVED`, and note this property exists so a surface can
        render the packet's own row without inventing a fifth level for a concept."""
        return PLACEMENT_UNRESOLVED if self.is_open else PLACEMENT_LEVELS[-1]

    def to_state(self) -> dict:
        return {
            "question_id": self.question_id,
            "subject": self.subject,
            "disposition": self.disposition,
            "note": self.note,
            "is_open": self.is_open,
            "attribution": self.attribution,
        }


_QUESTIONS: tuple[DomainQuestion, ...] = (
    DomainQuestion(
        "Q1",
        "second filename token = sample/electrode instance",
        QUESTION_CLOSED_BY_DOMAIN_OWNER,
        "Angel confirmed the convention explicitly (DEC-47). The token is a "
        "sample/electrode instance number. Stop asking.",
    ),
    DomainQuestion(
        "Q2",
        "Experiment-level vs Run-level concepts",
        QUESTION_CLOSED_BY_PRODUCT_DECISION,
        "DEC-40: inheritance with EXPLICIT Run overrides, never duplication, and "
        "never a silent override.",
    ),
    DomainQuestion(
        "Q3",
        "sample.material.name per stem",
        QUESTION_CLOSED_BY_DOCUMENT,
        "Every sample section of the beamtime document names its electrode label "
        "and medium, and the material is stated in the opening scope.",
    ),
    DomainQuestion(
        "Q4",
        "sample.material.provenance",
        QUESTION_CLOSED_BY_DOCUMENT,
        "The document names a preparer for one sample family and gives a full "
        "deposition recipe for another.",
    ),
    DomainQuestion(
        "Q5",
        "acid/base -> electrolyte name and concentration",
        QUESTION_CLOSED_BY_DOCUMENT,
        "Each sample section names its own electrolyte, and DEC-42 rules on the "
        "document's disagreement with itself: sample-specific evidence wins and the "
        "broad claim is PRESERVED as superseded, not deleted.",
    ),
    DomainQuestion(
        "Q6",
        "context.environment member",
        QUESTION_OPEN_NEEDS_DOMAIN_OWNER,
        "Partial. The dry / as-received acquisitions are stated as such. The member "
        "for the electrochemical acquisitions is one word only Angel can say. NOT "
        "addressed by his 2026-09-22 reply, so still open — and per that reply's "
        "general rule the field stays missing until he or a scientist supplies it.",
    ),
    DomainQuestion(
        "Q7",
        "context.electrochemistry.reaction member",
        QUESTION_OPEN_NEEDS_DOMAIN_OWNER,
        "Narrowed. The document names the reaction in prose and three enum members "
        "remain compatible; choosing between them is a scientific call. NOT addressed "
        "by the 2026-09-22 reply; still open, and the field stays missing meanwhile.",
    ),
    DomainQuestion(
        "Q8",
        "cell_type per sample group",
        QUESTION_OPEN_NEEDS_DOMAIN_OWNER,
        "Partial. One sample family is explicitly a flow cell; the other family's "
        "enum member is still Angel's. NOT addressed by the 2026-09-22 reply; still "
        "open, and the field stays missing meanwhile.",
    ),
    DomainQuestion(
        "Q9",
        "reference basis / rhe_basis",
        QUESTION_INTENTIONALLY_LEFT_MISSING,
        "~~Partial, and the one the corpus most clearly cannot settle~~ — answered "
        "2026-09-22 by the general rule: when a source does not state the basis (the "
        "JK groups name only 'a reference electrode'), the basis is LEFT MISSING for "
        "the user to update later and is never guessed. Where the notes name RHE "
        "explicitly, that statement is preserved verbatim as evidence; no rhe_basis "
        "member is written or proposed automatically for any group.",
        attribution=ANGEL_2026_09_22,
    ),
    DomainQuestion(
        "Q10",
        "where the E-chem Procedure rows go",
        QUESTION_CLOSED_BY_PRODUCT_DECISION,
        "DEC-41's hierarchy places them. Whether the Notes column may drive a QC "
        "state is Q14 and stays separate.",
    ),
    DomainQuestion(
        "Q11",
        "primary_signal channel",
        QUESTION_CONDITIONALLY_RESOLVED,
        "Answered as a RULE, not a column (2026-09-22): vortDT is generally the HERFD "
        "Vortex channel; in dual-element measurements vortDT and vortDT2 may belong to "
        "different elements and one can be empty. So the primary signal is selected "
        "PER RUN from evidence (bl15.signals): suggested, non-authoritatively, only "
        "when exactly one channel carries live signal and one element is established; "
        "otherwise left unresolved for review. The liveness thresholds are measured "
        "from the archive and recorded with their basis.",
        attribution=ANGEL_2026_09_22,
    ),
    DomainQuestion(
        "Q12",
        "expand the scan-grid literal into values?",
        QUESTION_CLOSED_BY_EXISTING_RULE,
        "Expanding a segmented grid into a value series is this repository computing "
        "a scientific quantity, which CLAUDE.md §5 forbids. The literal is preserved "
        "as extended context. No longer a domain question at all.",
    ),
    DomainQuestion(
        "Q13",
        "element and absorption edge",
        QUESTION_CLOSED_BY_PRODUCT_DECISION,
        "'Is the schema really silent' was answered by measurement — the walk covers "
        "every declared path and there is no native field. DEC-41 now gives both a "
        "structured home, so the question is closed rather than merely unanswerable.",
    ),
    DomainQuestion(
        "Q14",
        "is measurement.qc.status derivable from the notes?",
        QUESTION_INTENTIONALLY_LEFT_MISSING,
        "Answered 2026-09-22: the domain owner does not know what 'QC' would mean "
        "here, so qc.status is NEVER written from the notes. Every free-text Notes "
        "cell — a remark that a scan failed, that its counts were low, or which "
        "scans to keep — is preserved verbatim as a Data Quality Note, bound to its "
        "file number; the schema field is untouched.",
        attribution=ANGEL_2026_09_22,
    ),
    DomainQuestion(
        "Q15",
        "source precedence when three sources disagree",
        QUESTION_POLICY_ADOPTED,
        "Angel asked ISAAC to brainstorm it (2026-09-22). Policy adopted, with no "
        "universal source hierarchy: a macro is planned intent, a header is what the "
        "acquisition system recorded, a filename is a human label, the final notes "
        "are retrospective interpretation. Every source is preserved, the "
        "disagreement is shown and nothing is chosen; ISAAC may add a clearly "
        "labelled NON-AUTHORITATIVE recommendation when independent evidence supports "
        "one; only a scientist-confirmed resolution is authoritative, and for a "
        "record field it still goes forward as a proposal. DEC-42 (a document "
        "disagreeing with itself) is unchanged and separate.",
        attribution=ANGEL_2026_09_22,
    ),
    DomainQuestion(
        "Q16",
        "legacy number 32 carried by two acquisitions",
        QUESTION_DOMAIN_OWNER_DOES_NOT_KNOW,
        "Angel does not recall whether the two are two conditions or a typo "
        "(2026-09-22). So the conflict is PERMANENTLY PRESERVED: both acquisitions "
        "are kept with distinct durable identities (source path plus content digest, "
        "never the legacy number alone), neither overwrites the other, and neither is "
        "preferred or recommended. The final notes' support for one reading is shown "
        "as evidence, not truth (DEC-46).",
        attribution=ANGEL_2026_09_22,
    ),
    DomainQuestion(
        "Q17",
        "standards / alignment -> Runs?",
        QUESTION_CLOSED_BY_PRODUCT_DECISION,
        "The build already treats them as units that are not run candidates, which "
        "is the behaviour the question was asking about.",
    ),
    DomainQuestion(
        "Q18",
        "loading vs thickness",
        QUESTION_CLOSED_BY_DOCUMENT,
        "They are TWO concepts: one sample family states a deposition time and a "
        "thickness, the other a weight loading. Placement is DEC-41's.",
    ),
    DomainQuestion(
        "Q19",
        "system.configuration vs series[].conditions",
        QUESTION_CLOSED_BY_PRODUCT_DECISION,
        "DEC-41's hierarchy orders the two: the extension namespace is level 2 and a "
        "per-acquisition condition is level 3, so a concept with both homes places "
        "at the first one the hierarchy reaches.",
    ),
    DomainQuestion(
        "Q20",
        "which fields are intentionally custom Run conditions",
        QUESTION_CLOSED_BY_PRODUCT_DECISION,
        "DEC-41. A custom Run condition is a placement, and placement is decided.",
    ),
)

DOMAIN_QUESTIONS: dict[str, DomainQuestion] = {
    q.question_id: q for q in _QUESTIONS
}


def open_domain_questions() -> tuple[str, ...]:
    """The question ids still waiting on a domain owner, sorted by number.

    ~~Eight as of 2026-09-17.~~ **Three as of 2026-09-22** — Q6, Q7 and Q8, which the
    domain owner's reply that day did not address. The other five of the eight closed in
    five different ways (see the dispositions added that day). Exposed as a function
    rather than a constant so a disposition change moves it, and pinned by test so a
    change has to be deliberate.
    """
    return tuple(
        sorted(
            (qid for qid, q in DOMAIN_QUESTIONS.items() if q.is_open),
            key=lambda qid: int(qid[1:]),
        )
    )


@dataclass(frozen=True)
class ConceptMapping:
    """What the official schema can and cannot do with ONE corpus concept.

    :attr:`official_path` is ``None`` for every status outside
    :data:`PROPOSABLE_STATUSES` **except** :data:`STATUS_NEEDS_DOMAIN_REVIEW` and
    :data:`STATUS_BLOCKED_BY_BUILD`, where a path exists and the obstacle is elsewhere.
    Naming the path in those two cases is deliberate: a scientist asked to decide between
    ``operando`` and ``in_situ`` is owed the field the decision lands in.
    """

    concept: str
    status: str
    #: Dotted official path, ``[]`` marking an array. ``None`` when none exists.
    official_path: str | None
    #: WHY this status — in a sentence a scientist reads, not a code.
    reason: str
    #: The named rule, required when :attr:`status` is :data:`STATUS_NORMALIZED`.
    rule: str | None = None
    #: Sibling paths the schema REQUIRES alongside this one, so a consumer can see that
    #: satisfying this mapping is not sufficient on its own. ``electrolyte`` is the case
    #: that makes this field necessary: the schema requires BOTH ``name`` and
    #: ``concentration_M``, and ``acid``/``base`` supplies neither.
    requires_siblings: tuple[str, ...] = ()
    #: Enum members the schema allows here, when it constrains the value. Quoted so a
    #: domain question can be asked as "which of these" rather than open-ended.
    allowed_values: tuple[str, ...] = ()
    #: Candidate homes for a concept with no field of its own. Named, never applied.
    candidate_homes: tuple[str, ...] = ()
    #: Which numbered questions from the domain packet this concept's remaining
    #: judgement belongs to, if any. Ids only: :data:`DOMAIN_QUESTIONS` holds the
    #: dispositions, so a question closing does not need 45 rows edited.
    #:
    #: **An empty tuple is a real state and is not the same as "nothing outstanding".**
    #: Four rows carry :data:`STATUS_NEEDS_DOMAIN_REVIEW` and no question id, because
    #: the packet's twenty questions and the registry's rows are different sets — the
    #: packet says so itself. :func:`needs_review_without_a_question` names them rather
    #: than leaving a reader to subtract.
    domain_questions: tuple[str, ...] = ()
    #: The name a SCIENTIST sees for this concept, when the registry's own name is a
    #: code. ``None`` means the concept name reads well enough on its own. Added
    #: 2026-09-22 for "Data Quality Notes" — the domain owner's words for what the
    #: corpus calls quality remarks.
    scientist_label: str | None = None

    def __post_init__(self) -> None:
        if self.status not in MAPPING_STATUSES:
            raise ValueError(f"unknown mapping status: {self.status!r}")
        if self.concept not in ev.CONCEPTS:
            raise ValueError(f"unknown concept: {self.concept!r}")
        for question_id in self.domain_questions:
            if question_id not in DOMAIN_QUESTIONS:
                raise ValueError(
                    f"{self.concept}: unknown domain question {question_id!r}"
                )
        if self.status == STATUS_NORMALIZED and not self.rule:
            raise ValueError(f"{self.concept}: normalized mapping needs a rule")
        if self.status in PROPOSABLE_STATUSES and not self.official_path:
            raise ValueError(f"{self.concept}: {self.status} needs an official_path")
        if self.status == STATUS_NOT_EXPRESSIBLE and self.official_path:
            raise ValueError(
                f"{self.concept}: not_expressible must name no official_path"
            )

    @property
    def proposable(self) -> bool:
        """Whether a value at this concept may travel toward a candidate at all.

        Derived, with no field behind it, so it cannot be persisted out of step with
        the status that decides it — the same discipline
        ``historical_import.SemanticCandidate.proposable`` already uses.
        """
        return self.status in PROPOSABLE_STATUSES

    # --- DEC-41 placement, derived ------------------------------------------

    @property
    def declared_homes(self) -> tuple[str, ...]:
        """Every schema path this row names — the primary one and the candidates.

        All of them are checked against the vendored schema by
        :func:`registry_paths_exist`, which is what makes a derived level trustworthy:
        the level can only ever be as wrong as the paths, and the paths are verified.
        """
        primary = (self.official_path,) if self.official_path else ()
        return primary + self.candidate_homes

    @property
    def placement_level(self) -> int:
        """Where this concept's information lands, per :data:`PLACEMENT_LEVELS`.

        **The FIRST level of `DEC-41`'s hierarchy at which this concept has a home**,
        which is `DEC-41`'s ordering read literally rather than restated. Level 4 is
        therefore reached only when 1, 2 and 3 are all genuinely unavailable — so
        *"never skip a level to reach 4 when a real field exists"* is not a rule this
        property obeys, it is the definition it is built from.

        Note ``blocked_by_build`` still places at **1**: ``assets[].uri`` genuinely
        fits, and the obstacle is an application decision (``ASSETS_BLOCKED_REASON``),
        not the absence of a field. Placing it at 4 would record a build boundary as a
        schema fact.

        **LEVEL 1 IS DECIDED BY ``official_path`` ALONE AND DELIBERATELY NOT BY A
        CANDIDATE HOME**, and the first draft of this property got that wrong — it read
        any non-extension candidate home as a native field and returned level 1 for
        ``beamtime_purpose``, ``beamtime_dates`` and ``loading_or_thickness``. All three
        are wrong, and the registry's own rows say so: ``tags`` *"would reduce a
        paragraph to keywords, which loses the statement rather than recording it"*, and
        the loading/thickness row reads *"a composition object and a geometry object and
        a natural home for neither"*. `DEC-41`'s level 1 is *"a native official ISAAC
        field **where one genuinely fits**"*; a ``candidate_homes`` entry is by this
        registry's own definition *"named, never applied"*, and several are argued
        AGAINST in the very reason beside them. So a candidate home is consulted only
        for levels **2** and **3**, where the home in question is the hierarchy's own
        (the schema's designated extension namespace, and the schema-legal per-series
        condition) rather than a near-miss somebody named.
        """
        homes = self.declared_homes
        if self.official_path and not self.official_path.startswith(
            EXTENSION_NAMESPACE
        ):
            return PLACEMENT_OFFICIAL_FIELD
        if any(p.startswith(EXTENSION_NAMESPACE) for p in homes):
            return PLACEMENT_SCHEMA_EXTENSION_POINT
        if SERIES_CONDITIONS_HOME in homes:
            return PLACEMENT_RUN_SERIES_CONDITION
        return PLACEMENT_EXTENDED_CONTEXT

    @property
    def placement_name(self) -> str:
        return PLACEMENT_NAMES[self.placement_level]

    @property
    def unresolved_questions(self) -> tuple[str, ...]:
        """This concept's domain questions that are STILL OPEN. Empty is the common case.

        Separate from :attr:`domain_questions` because twelve of the twenty closed on
        2026-09-17: a surface that read the full list would keep telling a scientist to
        wait for an answer that has arrived, which is the defect ``CTX-001`` names.
        """
        return tuple(
            q for q in self.domain_questions if DOMAIN_QUESTIONS[q].is_open
        )

    def to_state(self) -> dict:
        return {
            "concept": self.concept,
            "status": self.status,
            "official_path": self.official_path,
            "reason": self.reason,
            "rule": self.rule,
            "requires_siblings": list(self.requires_siblings),
            "allowed_values": list(self.allowed_values),
            "candidate_homes": list(self.candidate_homes),
            "proposable": self.proposable,
            # DEC-41. Both the number and its words: a bare integer on a screen is a
            # rank a reader has to look up, and the level is the more useful half.
            "placement_level": self.placement_level,
            "placement_name": self.placement_name,
            "domain_questions": list(self.domain_questions),
            "unresolved_questions": list(self.unresolved_questions),
            "scientist_label": self.scientist_label,
            # 2026-09-22 — how many values the concept is expected to have, so a
            # surface can say "varies by scan" from the registry rather than guess it.
            "cardinality": cardinality_for(self.concept),
        }


# --- the registry ------------------------------------------------------------

_MAPPINGS: tuple[ConceptMapping, ...] = (
    # ---- deterministic ------------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_ACQUISITION_TIMESTAMP,
        status=STATUS_DETERMINISTIC,
        official_path="timestamps.acquired_start_utc",
        reason=(
            "Each acquisition file states its own start time in its SPEC header. The "
            "epoch line and the date line are two separate statements and are NOT "
            "reconciled here: if they disagree, both are read and the disagreement is "
            "a conflict for a scientist, not an arithmetic problem."
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ACQUISITION_EPOCH,
        status=STATUS_NORMALIZED,
        official_path="timestamps.acquired_start_utc",
        reason=(
            "The SPEC header states the acquisition instant twice — once as Unix "
            "seconds and once as a formatted local date — and the epoch line is the "
            "one that converts without assuming a timezone, which is why the rule "
            "hangs off it. THE TWO ARE NOT RECONCILED HERE: they are two statements "
            "the file makes, and if they disagree both are read and the disagreement "
            "belongs to a scientist. Choosing the epoch as the mappable one is a "
            "statement about which is convertible, not about which is right."
        ),
        rule="unix_epoch_seconds_to_iso8601_utc",
    ),
    # ---- normalized ---------------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_POTENTIAL_MAGNITUDE,
        status=STATUS_NORMALIZED,
        official_path="context.electrochemistry.potential_setpoint_V",
        reason=(
            "Filenames state a potential magnitude in two unit conventions. The "
            "schema's field is in volts. THE MAGNITUDE IS ALL THAT IS MAPPED HERE — "
            "the electrochemical reference it is measured against is a separate "
            "concept with a separate and usually absent mapping, and collapsing the "
            "two would assert a basis no source states."
        ),
        rule="millivolts_to_volts_and_p_as_decimal_point",
        requires_siblings=("context.electrochemistry.control_mode",),
            domain_questions=("Q2", "Q20"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_PH,
        status=STATUS_NORMALIZED,
        official_path="context.electrochemistry.pH",
        reason=(
            "The beamtime notes state a pH for the later oxide samples. The schema "
            "pairs it with pH_basis, whose members are 'measured', 'nominal' and "
            "'buffered_assumed'; a figure quoted beside a hydroxide concentration is "
            "evidenced as nominal, and no source states a basis for any other sample."
        ),
        rule="ph_figure_read_verbatim_basis_nominal_only_where_quoted_with_a_concentration",
        requires_siblings=("context.electrochemistry.pH_basis",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_FLOW_RATE,
        status=STATUS_NORMALIZED,
        official_path="context.transport.feed.flow_rate",
        reason=(
            "The notes state a flow rate for the flow-cell samples. The schema keeps "
            "the unit in a sibling field rather than in the number, so both are "
            "carried; the feed object additionally REQUIRES phase and composition, "
            "which a flow rate alone does not supply."
        ),
        rule="flow_rate_value_and_unit_carried_separately_never_converted",
        requires_siblings=(
            "context.transport.feed.flow_rate_unit",
            "context.transport.feed.phase",
            "context.transport.feed.composition",
        ),
    ),
    # ---- needs domain review ------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_POTENTIAL_REFERENCE,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="context.electrochemistry.potential_vs_RHE.rhe_basis",
        reason=(
            "THIS IS THE COROLLARY OF THE POTENTIAL MAGNITUDE MAPPING AND THE MOST "
            "CONSEQUENTIAL ENTRY IN THIS REGISTRY. A filename states a magnitude and "
            "says nothing about the basis. potential_scale's six members are each a "
            "specific claim with no 'unknown' member, so that field is left ABSENT "
            "rather than guessed. rhe_basis, by contrast, has vocabulary FOR the "
            "absence: 'not_reported' where no source names a basis, and "
            "'not_convertible_no_reference_offset' where a reference is mentioned but "
            "its offset is not. value_V is nullable, so 'no RHE value, and here is "
            "why' is a complete and valid statement. Which member applies to which "
            "sample group is a domain judgement, because only a scientist can say "
            "whether a note naming RHE for one group covers its neighbours. SINCE "
            "2026-09-22 the domain owner's answer governs the unstated case: when no "
            "source states the basis it stays MISSING for the user to update, and no "
            "member is chosen for them — not even not_reported."
        ),
        allowed_values=(
            "measured_direct",
            "derived_calibrated",
            "reported_as_RHE",
            "derived_nominal",
            "in_silico_setpoint",
            "not_convertible_no_pH",
            "not_convertible_no_reference_offset",
            "not_reported",
            "not_applicable",
        ),
        candidate_homes=("context.electrochemistry.potential_scale",),
            domain_questions=("Q9",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ELECTROLYTE_OR_MEDIUM,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="context.electrochemistry.electrolyte.name",
        reason=(
            "Filenames say only 'acid' or 'base', which is a medium class and not an "
            "electrolyte name, and the schema REQUIRES both a name and a molar "
            "concentration in the same object. The notes name a specific acid for one "
            "sample; the one sentence that would supply a concentration for the rest "
            "is the corpus's own contradicted broad claim — it asserts a single "
            "hydroxide for ALL experiments while sitting above a sample section "
            "labelled acid, in a document whose preparation steps specify the acid. "
            "So this concept cannot be mapped from a filename at all, and the note "
            "that would complete it is in conflict with the same document."
        ),
        requires_siblings=("context.electrochemistry.electrolyte.concentration_M",),
            domain_questions=("Q2", "Q5"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_GAS_CONDITION,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="context.transport.feed.composition",
        reason=(
            "The notes describe purging an inert gas and saturating the later samples "
            "with it. Whether that is the cell's FEED in the schema's sense — the "
            "transport block is written for flowing reactant feeds — or an atmosphere "
            "belonging in context.thermodynamics.atmosphere, is a judgement about the "
            "experiment rather than about the text."
        ),
        requires_siblings=("context.transport.feed.phase",),
        candidate_homes=("context.thermodynamics.atmosphere",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SAMPLE_NAME,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="sample.material.name",
        reason=(
            "A filename's sample token is the scientist's own shorthand — an electrode "
            "label for some samples and a material description for others. Which of "
            "those two it is decides whether it belongs at sample.material.name or "
            "sample.sample_id, and only the scientist who wrote it can say. The schema "
            "also requires a sample_form alongside, which no filename states."
        ),
        requires_siblings=("sample.sample_form",),
        candidate_homes=("sample.sample_id", "sample.electrode_type"),
            domain_questions=("Q2", "Q3"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="sample.sample_id",
        reason=(
            "The second numeric filename token IS a sample/electrode instance "
            "number — confirmed by the domain owner on 2026-09-17 (DEC-47), so the "
            "question this row used to ask is closed. What still needs a domain owner "
            "is narrower and is about the schema rather than the corpus: an instance "
            "number could land at sample.sample_id or at sample.library.sample_no, and "
            "the schema requires a sample_form alongside whichever is chosen, which no "
            "filename states."
        ),
        candidate_homes=("sample.library.sample_no",),
            domain_questions=("Q1",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_LOADING_OR_THICKNESS,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path=None,
        reason=(
            "One filename slot carries two physically different quantities in this "
            "corpus — an overlayer thickness in nanometres for the oxide samples and a "
            "weight loading in percent for the pellets. The schema has a composition "
            "object and a geometry object and a natural home for neither, so this is "
            "both a mapping question and a question about what the token means."
        ),
        candidate_homes=("sample.composition", "sample.geometry"),
            domain_questions=("Q18",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ELEMENT,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path=None,
        reason=(
            "The beamtime README names the absorbing element in one line, for the whole "
            "beamtime. The official schema has no absorber-element field; the absorbing "
            "element and edge are recorded as implicit/sidecar-only for the XANES path "
            "and must not be forced into the official record where the schema provides "
            "no valid path."
        ) + " " + SYSTEM_CONFIGURATION_CAUTION,
        candidate_homes=("system.configuration",),
            domain_questions=("Q13", "Q19"),
    ),
    # ---- not expressible ----------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_CYCLING_STATE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=CYCLING_STATE_NO_FIELD_REASON,
        candidate_homes=("measurement.series[].conditions",),
            domain_questions=("Q20",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_BEFORE_AFTER_STATE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The before/after qualifier is one half of the cycling-state concept and "
            "has no field for the same reason."
        ),
        candidate_homes=("measurement.series[].conditions",),
            domain_questions=("Q20",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_FILTER,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "An attenuator index is beamline-specific instrument state. The official "
            "schema has no field for it. " + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=(
            "measurement.series[].conditions",
            "system.configuration",
        ),
            domain_questions=("Q19", "Q20"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_EMISSION_ENERGY,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The emission energy the spectrometer is parked at is stated by the "
            "acquisition headers and by the macro call, and the official schema has no "
            "field for it. " + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=(
            "measurement.series[].conditions",
            "system.configuration",
        ),
            domain_questions=("Q19",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_LEGACY_NUMBER,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The leading filename number is the CORPUS'S identifier, not ISAAC's. It "
            "must not be forced into record_id, which the server mints, nor into "
            "sample.sample_id, which identifies a sample rather than a measurement. It "
            "is preserved as source evidence and is the right label to show a "
            "scientist, because it is the handle they already use."
        ),
            domain_questions=("Q16",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_NEW_SPOT,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "Moving to an unexposed spot on the same electrode is a real experimental "
            "act with no schema field. It is not a replicate — the sample is the same "
            "one — so links[].rel = replica_of would be wrong about it."
        ),
        candidate_homes=("measurement.series[].conditions",),
            domain_questions=("Q20",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_MONOCHROMATOR_CALIBRATION,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The README states which foil the monochromator was calibrated against. "
            "There is no calibration field; links[].rel = calibration_of with basis "
            "same_absorber_edge can express the RELATIONSHIP once a calibration record "
            "exists to point at, which this corpus does not contain. "
            + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=("system.configuration", "links[]"),
            domain_questions=("Q19",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SPECTROMETER_CONFIG,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "Slit width, analyser crystal and emission line are exactly the "
            "facility-specific configuration the schema declines to generalize. "
            + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=("system.configuration",),
            domain_questions=("Q19",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_BEAMSIZE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "Beam dimensions at a stated energy are station configuration. "
            + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=("system.configuration",),
            domain_questions=("Q19",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_UNKNOWN_TOKEN,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "A token no profile recognised has no concept, so it can have no mapping. "
            "IT IS STILL CARRIED: an unrecognised token is preserved as source "
            "evidence and shown to the scientist, because the alternative is dropping "
            "part of a filename silently."
        ),
    ),
    # ---- blocked by build ---------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_SCAN_COMMAND,
        status=STATUS_BLOCKED_BY_BUILD,
        official_path="assets[].uri",
        reason=ASSETS_BLOCKED_REASON,
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ENERGY_GRID,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="measurement.series[].independent_variables[].values",
        reason=(
            "The scan grid is stated literally by the acquisition command and by the "
            "method macro, so the VALUES are evidenced. What the schema needs "
            "alongside them is a channel set with a role for each, and which detector "
            "column carries the primary signal among the many a scan export records is "
            "a domain fact this repository must not choose."
        ),
        requires_siblings=(
            "measurement.series[].series_id",
            "measurement.series[].independent_variables[].name",
            "measurement.series[].independent_variables[].unit",
            "measurement.series[].channels[]",
        ),
            domain_questions=("Q11", "Q12"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_DETECTOR_COLUMN,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="measurement.series[].channels[].name",
        reason=(
            "A scan export names its columns, so the names are evidenced. The schema "
            "requires a role for each from a closed set, and assigning those roles is "
            "a scientific reading of the detector set, not a transcription. FOR THE "
            "HERFD PRIMARY SIGNAL SPECIFICALLY, the domain owner answered on 2026-09-22 "
            "with a per-Run rule, so a selector SUGGESTS a channel when a Run's own "
            "evidence supports exactly one — non-authoritatively, and writing no field, "
            "because the series block this path belongs to needs values this build "
            "does not carry."
        ),
        requires_siblings=(
            "measurement.series[].channels[].unit",
            "measurement.series[].channels[].role",
        ),
        allowed_values=(
            "primary_signal",
            "measured_response",
            "simulated_observable",
            "derived_signal",
            "auxiliary_signal",
            "control_readback",
            "quality_monitor",
        ),
            domain_questions=("Q11",),
    ),
    # ---- the acquisition and instrument vocabulary --------------------------
    #
    # Examined together because they share one answer: an acquisition header states a
    # great deal about the INSTRUMENT, and the official schema is deliberately not an
    # instrument log. Each entry below says so in its own terms rather than deferring to
    # a shared note, because a scientist reading one of them should not have to find
    # another to learn why.
    ConceptMapping(
        concept=ev.CONCEPT_ACQUISITION_METHOD,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="system.technique",
        reason=(
            "~~The acquisition-method macro defines a named high-energy-resolution "
            "fluorescence-detected absorption scan … so this is a transcription rather "
            "than a judgement.~~ CORRECTED 2026-09-16, the same day, by the slice that "
            "wired this registry to a route and MEASURED what the concept actually "
            "carries. The reasoning was about what a human reading the corpus knows; "
            "the mapping is about what the readers emit, and those are different. "
            "Measured: from a macro this concept carries THE MACRO'S OWN NAME — the "
            "file a `qdo` includes, or the symbol a `def` block defines — and from a "
            "filename it carries the profile's alias reading, whose normalised values "
            "are lowercase shorthands. NOT ONE OF THOSE IS A MEMBER OF THE SCHEMA'S "
            "TECHNIQUE ENUM, so the old status proposed an off-enum value from every "
            "source, and a proposal at this path is then work a scientist is offered "
            "and cannot complete. Two further reasons it is a judgement and not a "
            "transcription: one alias normalises to a DETECTION MODE, which the enum "
            "has no member for at all and which is not a technique; and the strongest "
            "evidence for the real technique is a word in the beamtime document's "
            "TITLE, which no reader in this build reads as a technique statement. So "
            "the enum member is a scientist's to choose, and the options are named "
            "below so that choice is one word."
        ),
        allowed_values=("XAS", "HERFD-XAS", "XES", "RIXS"),
        requires_siblings=("system.domain",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_REPEAT_MARKER,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="links[].rel",
        reason=(
            "A repeat qualifier on an otherwise identical filename is the corpus "
            "saying 'this is the same measurement again', and the schema has exactly "
            "that relationship — replica_of, with basis replicate_preparation. But a "
            "link needs a TARGET RECORD, and whether the earlier acquisition is a "
            "replicate or a failed first attempt that should not be linked at all is a "
            "scientific reading. Note the contrast with a new-spot qualifier, which "
            "looks similar and is NOT a replicate: the sample is the same one."
        ),
        requires_siblings=("links[].target", "links[].basis"),
        allowed_values=("replica_of", "follows", "same_sample_as"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_QUALITY_NOTE,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="measurement.qc.notes",
        reason=(
            "The beamtime notes carry the scientist's own remarks about which "
            "acquisitions were poor, which sample misbehaved, and which were repeated. "
            "They are preserved VERBATIM as Data Quality Notes, each bound to its file "
            "number. THE VERDICT DOES NOT FOLLOW FROM THEM, and since 2026-09-22 that "
            "is the domain owner's answer rather than only this repository's caution: "
            "he does not know what 'QC' would mean for these remarks, so qc.status is "
            "never written from them — not as a value, not as a suggestion. qc.status "
            "is a closed set of four, and a record already carries the stronger "
            "constraint that a status must have evidence behind it."
        ),
        requires_siblings=("measurement.qc.status",),
        allowed_values=("valid", "compromised", "failed", "pending"),
            domain_questions=("Q10", "Q14"),
        scientist_label=DATA_QUALITY_NOTES_LABEL,
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SAMPLE_PREPARATION,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="sample.material.provenance",
        reason=(
            "The notes describe ink preparation, dropcasting and electrode assembly at "
            "length. The schema has a provenance string and a notes string on the "
            "material, so there is a home — but the preparation described is "
            "beamtime-wide prose covering several samples, and deciding how much of it "
            "is provenance OF ONE SAMPLE is a scoping judgement, not an extraction."
        ),
        candidate_homes=("sample.material.notes",),
            domain_questions=("Q4",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ECHEM_PROCEDURE,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="context.electrochemistry.notes",
        reason=(
            "The notes tabulate the electrochemical program step by step, including an "
            "impedance-compensation step whose parameters the schema models properly in "
            "its ir_compensation object rather than as prose. So part of this concept "
            "has a STRUCTURED home and part has only a notes field, and which rows are "
            "which is a reading of the protocol."
        ),
        candidate_homes=(
            "context.electrochemistry.ir_compensation.method",
            "context.electrochemistry.control_mode",
        ),
            domain_questions=("Q8", "Q10"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_BEAMTIME_DATES,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path=None,
        reason=(
            "The notes state the beamtime window. The schema's timestamps are per "
            "record — an acquisition's own start and end — and a campaign window is "
            "neither. Writing it into a record's acquired_start_utc would claim a "
            "measurement began when the beamtime did."
        ),
        candidate_homes=("timestamps.revision_note",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_BEAMTIME_PURPOSE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The scientific aim of the campaign is stated in the notes' own words. "
            "There is no purpose or abstract field; tags is a free array and would "
            "reduce a paragraph to keywords, which loses the statement rather than "
            "recording it. Preserved as source evidence."
        ),
        candidate_homes=("tags",),
            domain_questions=("Q7",),
    ),
    # ---- instrument state: real, stated, and not the schema's business ------
    ConceptMapping(
        concept=ev.CONCEPT_MOTOR_POSITION,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "An acquisition header records roughly a hundred and eighty motor "
            "positions. They are genuine instrument state and the schema has no field "
            "for any of them. " + SYSTEM_CONFIGURATION_CAUTION
        ),
        candidate_homes=("system.configuration",),
            domain_questions=("Q19",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SAMPLE_POSITION,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "Stage coordinates are how the corpus distinguishes one spot on an "
            "electrode from another, which makes them scientifically load-bearing here "
            "and still gives them no schema field. The library block holds plate "
            "coordinates for combinatorial samples, which is a different thing from a "
            "stage position and must not be reused for it."
        ) + " " + SYSTEM_CONFIGURATION_CAUTION,
        candidate_homes=("system.configuration",),
            domain_questions=("Q19",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_COUNTING_TIME,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "Dwell time per point is stated by the acquisition header and by the macro "
            "call. It is an acquisition parameter with no schema field; as a per-series "
            "operating condition it has a schema-legal candidate home."
        ),
        candidate_homes=("measurement.series[].conditions",),
            domain_questions=("Q20",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SCAN_COUNT,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "How many scans a macro asked for is intent; how many scan files exist is "
            "fact, and in this corpus THEY DISAGREE. Neither has a schema field, and "
            "mapping either one would quietly pick a side of a real conflict."
        ),
        candidate_homes=("measurement.series[].conditions",),
            domain_questions=("Q20",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_POINT_COUNT,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The number of points in a scan is a property OF the series values, not a "
            "separate field. If the values are ever carried, the count is implied by "
            "them; recording it alongside would create a second place for one fact to "
            "be wrong."
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_EDGE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The absorbing element and its edge are implicit/sidecar-only for this "
            "technique path and must not be forced into the official record while the "
            "schema provides no valid field. That is a standing project rule, not a "
            "judgement made here."
        ) + " " + SYSTEM_CONFIGURATION_CAUTION,
        candidate_homes=("system.configuration",),
            domain_questions=("Q13", "Q19"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_DRY_STATE,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "A dry or as-received measurement is a condition with no schema field. It "
            "interacts with the environment enum — an ex-situ reading is plausible for "
            "these — but the enum describes the MEASUREMENT context and this token "
            "describes the sample's state, and conflating them would assert something "
            "no source states."
        ),
        candidate_homes=("measurement.series[].conditions",),
            domain_questions=("Q6", "Q20"),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_STEP_NUMBER,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "A step index refers to a position in the electrochemical program, which "
            "the notes tabulate and the schema does not model. It is the join key "
            "between a filename and a human note row, which makes it valuable as "
            "evidence and still not a record field."
        ),
            domain_questions=("Q10",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_TRIGGER,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "A trigger command in a macro is the handshake between the acquisition and "
            "the potentiostat. It explains how the two instruments were synchronised "
            "and asserts nothing about the sample, so there is nothing for it to map "
            "to. It matters for relationship reconstruction, where it marks where one "
            "measurement ends and the next begins."
        ),
    ),
    # ---- added 2026-09-22 -----------------------------------------------------
    ConceptMapping(
        concept=ev.CONCEPT_TEMPERATURE_STATEMENT,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path=None,
        reason=(
            "What a source SAYS about temperature, in its own words — 'room "
            "temperature', 'RT', a labelled Temperature line. The words have no home "
            "in context.temperature_K, which holds a NUMBER, and turning them into one "
            "is choosing a convention (NTP-style 293.15 K or SATP-style 298.15 K), "
            "which the domain owner declined to have done automatically on "
            "2026-09-22. So the statement is kept verbatim in the extended context and "
            "the field stays missing; a nominal number may be OFFERED only by a "
            "reviewed convention rule that names its convention and waits for a "
            "scientist's confirmation, and none is enabled. The supplied archive "
            "states no temperature anywhere, so no real file produces this concept."
        ),
        candidate_homes=("context.temperature_K",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_CONTRIBUTOR_STATEMENT,
        status=STATUS_NEEDS_DOMAIN_REVIEW,
        official_path="attribution.contributors",
        reason=(
            "A person a source NAMES as having run, measured or prepared something. It "
            "is PROVENANCE, recorded beside the readings it concerns and never used to "
            "select how a file is read. The schema's contributors list takes a name "
            "and a role, and whether a name typed in a historical note is the right "
            "person for a record — and in which role — is a judgement about identity "
            "this build cannot make: no trusted boundary exists, and uploaded_by is "
            "server-stamped for exactly that reason. Kept as evidence; never proposed "
            "automatically. The supplied archive carries no such labelled line."
        ),
        requires_siblings=(),
        allowed_values=(
            "data_owner",
            "performed_measurement",
            "performed_analysis",
            "curated_record",
        ),
    ),
    # ---- structural and provenance-only: examined and deliberately refused --
    ConceptMapping(
        concept=ev.CONCEPT_SPEC_USER_STRING,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "REFUSED ON PURPOSE, AND THIS IS THE ONE ENTRY THAT WOULD BE ACTIVELY "
            "HARMFUL TO 'FIX'. An acquisition header carries the account string the "
            "beamline software was running under. The schema does have an uploader "
            "field — and it is SERVER-STAMPED, requires a verified trust basis that no "
            "verifier in this build mints, and is therefore absent from every record "
            "this deployment produces. Copying a beamline account string into it would "
            "manufacture exactly the attribution the trust boundary exists to withhold. "
            "It stays raw source evidence, and it is never an ISAAC identity or actor."
        ),
        candidate_homes=(),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_SPEC_FILE_DECLARATION,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The name an acquisition file declares for ITSELF, internally. It is not a "
            "value to map — it is the ANCHOR for conflict detection, because in this "
            "corpus an internal declaration and the external filename disagree about "
            "the experimental state of the sample. Mapping it anywhere would settle "
            "that disagreement by accident."
        ),
            domain_questions=("Q15",),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_ACQUISITION_TARGET,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "The measurement name a macro DECLARES it is about to write. It is intent, "
            "and in this corpus nine declared targets were never acquired while nine "
            "acquisitions were never declared. It is a relationship key, not a field."
        ),
    ),
    ConceptMapping(
        concept=ev.CONCEPT_NOTE_FILE_NUMBER_ROW,
        status=STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason=(
            "A row from the human file-number table is the scientist's own independent "
            "mapping from a file number to a condition. Its VALUE is as corroboration "
            "and as a cross-check against the filesystem — which is a relationship "
            "question — and the individual concepts inside such a row have their own "
            "entries in this registry."
        ),
    ),
)

MAPPINGS: dict[str, ConceptMapping] = {m.concept: m for m in _MAPPINGS}

# --- cardinality: how many values a concept is EXPECTED to have -----------------
#
# ADDED 2026-09-22, AFTER A MEASUREMENT: on the synthetic multi-operator corpus, 36 of
# the 43 "field disagreements" the reconstruction reported were not disagreements. Each
# scan export names its own scan index, a `#L` line lists several detector columns, a
# `#P` line gives several motors' positions, and each scan file's name carries its own
# index token — so comparing every reading of those concepts against every other
# reported "the sources disagree" about scans that were simply different. The rule
# below is stated PER CONCEPT and never inferred from the data: a concept this table
# does not name is one value per measurement, which is the conservative default because
# comparing everything is the one choice that can never hide a disagreement.

#: One value per measurement: every reading is compared with every other. The default.
CARDINALITY_PER_MEASUREMENT = "per_measurement"
#: One value per SCAN: a reading is compared only with readings about the same scan.
CARDINALITY_PER_SCAN = "per_scan"
#: Several values per scan, one per ITEM (a detector column, a motor): a reading is
#: compared only with readings about the same item of the same scan.
CARDINALITY_PER_SCAN_ITEM = "per_scan_item"
#: Values per FILE, one per item of it (a name's token position): a reading is compared
#: only with readings about the same item of the same file.
CARDINALITY_PER_SOURCE = "per_source"
CARDINALITIES: frozenset[str] = frozenset(
    {
        CARDINALITY_PER_MEASUREMENT,
        CARDINALITY_PER_SCAN,
        CARDINALITY_PER_SCAN_ITEM,
        CARDINALITY_PER_SOURCE,
    }
)

RULE_CARDINALITY = (
    "bl15.mapping.cardinality.v2: a concept's readings are compared at the level its "
    "cardinality names. Two readings about DIFFERENT scans may differ only when each "
    "source itself states which scan it is about — the SPEC scan number on its own #S "
    "line; a scan export's file index is never taken as one. A per-scan-item concept is "
    "compared within the same column or motor of the same scan, a per-source concept "
    "within the same token of the same file. Every statement about the whole "
    "measurement, or whose scan is not established, is compared with every reading of "
    "the same item, so a plan that disagrees with a recording is a conflict. Values that "
    "differ across two or more established scans are kept as one reading per scan; any "
    "other difference is a conflict. Nothing is chosen and nothing is dropped."
)

#: THE DECLARED CARDINALITIES, each with the reason it is not the default.
#:
#: * ``acquisition_target`` — a scan export's basename names ITS OWN scan index, so it
#:   differs by construction; a macro's declared target is compared with every scan's
#:   on the measurement stem alone.
#: * ``detector_column`` — a `#L` line lists SEVERAL columns; each column position is
#:   its own item.
#: * ``motor_position`` — a `#P` line gives SEVERAL motors; each motor is its own item.
#: * ``unknown_token`` — an unrecognised piece of ONE file's own name, at one token
#:   position; two files' pieces, or two positions of one name, are different facts,
#:   not two accounts of one.
#:
#: REVERTED TO PER-MEASUREMENT IN v2 (2026-09-23): ``counting_time``,
#: ``scan_command``, ``energy_grid`` and ``emission_energy``. v1 declared them per scan,
#: and an independent review measured the cost: a macro's planned counting time or
#: emission energy and the header's recorded value for the SAME, only scan read as
#: variation. The domain answers so far treat counting time and emission energy as read
#: "for a measurement", so they are compared as one value until the domain owner says
#: which acquisition quantities are expected to vary per scan — asked as Q21 in
#: ``docs/bl15-2-domain-questions-2026-09-16.md``.
#:
#: DELIBERATELY NOT HERE, though some of their readings are stated per scan:
#: ``filter`` (a condition of the measurement — a scan header's filter motor disagreeing
#: with the filename's filter index is a real question for a scientist) and
#: ``acquisition_timestamp`` (it feeds ``timestamps.acquired_start_utc``, one value per
#: run, and choosing between scans' dates is a decision, not a reading).
CONCEPT_CARDINALITY: dict[str, str] = {
    ev.CONCEPT_ACQUISITION_TARGET: CARDINALITY_PER_SCAN,
    ev.CONCEPT_DETECTOR_COLUMN: CARDINALITY_PER_SCAN_ITEM,
    ev.CONCEPT_MOTOR_POSITION: CARDINALITY_PER_SCAN_ITEM,
    ev.CONCEPT_UNKNOWN_TOKEN: CARDINALITY_PER_SOURCE,
}


def cardinality_for(concept: str) -> str:
    """How many values ``concept`` is expected to have — see :data:`RULE_CARDINALITY`."""
    return CONCEPT_CARDINALITY.get(concept, CARDINALITY_PER_MEASUREMENT)



def mapping_for(concept: str) -> ConceptMapping | None:
    """The registry entry for one concept, or ``None`` if the registry is silent.

    **``None`` is not the same as :data:`STATUS_NOT_EXPRESSIBLE`.** An explicit
    ``not_expressible`` entry is a measured finding — somebody read the schema and
    established there is no field. ``None`` means nobody has looked yet. A consumer that
    treated them alike would report unexamined concepts as settled, so
    :func:`unmapped_concepts` exists to keep the difference visible.
    """
    return MAPPINGS.get(concept)


def unmapped_concepts() -> tuple[str, ...]:
    """Concepts this registry has NOT examined, sorted.

    Deliberately exposed rather than left implicit: it is the honest measure of how
    much of a corpus's vocabulary the registry has actually been reasoned about, and it
    should be quoted alongside any claim about mapping coverage.
    """
    return tuple(sorted(ev.CONCEPTS - set(MAPPINGS)))


def needs_review_without_a_question() -> tuple[str, ...]:
    """``needs_domain_review`` rows that no numbered packet question covers, sorted.

    **Non-empty, and that is a measured finding rather than a gap in this function.**
    The packet's own reconciliation records it: *"20 questions, 15 registry rows, and
    they are different sets."* Exposed because the alternative is a reader subtracting
    two numbers and guessing which four rows are missing — and because a row whose
    remaining judgement belongs to nobody in particular is exactly the row that gets
    "fixed" by pointing it at a nearby field.
    """
    return tuple(
        sorted(
            concept
            for concept, m in MAPPINGS.items()
            if m.status == STATUS_NEEDS_DOMAIN_REVIEW and not m.domain_questions
        )
    )


class PlacementSkipError(ValueError):
    """`DEC-41`'s first rule, refused at the boundary where it can be broken.

    Raised when a consumer records a concept at a placement level other than the one
    the registry derives for it — above all at level 4 when the official schema has a
    field. That is the *"skip a level to reach 4"* the decision forbids, and it is the
    shape a careless companion entry takes: the information looks preserved, and a
    native field silently stopped being offered.
    """


def check_placement(concept: str, level: int) -> None:
    """Refuse a placement that disagrees with the registry. Returns ``None`` or raises.

    **Equality, not "level >= expected"**, and the direction matters in both
    directions: claiming level 4 for a concept with a native field hides the field, and
    claiming level 1 for a concept the schema has nowhere for asserts a home that does
    not exist. Neither is a placement a companion may record.

    A concept with **no registry entry** may only be recorded at level 4 — nobody has
    established a home for it, and level 4 is the level that claims none.
    """
    if level not in PLACEMENT_LEVELS:
        raise PlacementSkipError(
            f"{concept}: {level!r} is not one of the four DEC-41 placement levels "
            f"{PLACEMENT_LEVELS}"
        )
    entry = MAPPINGS.get(concept)
    expected = entry.placement_level if entry else PLACEMENT_EXTENDED_CONTEXT
    if level == expected:
        return
    if level == PLACEMENT_EXTENDED_CONTEXT:
        raise PlacementSkipError(
            f"{concept}: DEC-41 forbids skipping to level 4 (extended context) when a "
            f"home exists at level {expected} ({PLACEMENT_NAMES[expected]}"
            + (f", {entry.official_path}" if entry and entry.official_path else "")
            + ")"
        )
    raise PlacementSkipError(
        f"{concept}: placement level {level} ({PLACEMENT_NAMES[level]}) disagrees with "
        f"the registry, which places it at {expected} "
        f"({PLACEMENT_NAMES[expected]})"
    )


def placement_violations() -> tuple[str, ...]:
    """Registry rows whose derived placement contradicts `DEC-41`. Empty is correct.

    The level is derived, so most ways of getting it wrong are unreachable — but two
    are not, and both are edits a future slice could plausibly make:

    * a row at level 4 that nonetheless names an ``official_path`` (the rule `DEC-41`
      states in words);
    * a row at level 1 with no ``official_path`` at all.
    """
    bad: list[str] = []
    for concept, m in sorted(MAPPINGS.items()):
        level = m.placement_level
        if level == PLACEMENT_EXTENDED_CONTEXT and m.official_path:
            bad.append(
                f"{concept}: level 4 while naming {m.official_path}"
            )
        if level == PLACEMENT_OFFICIAL_FIELD and not m.official_path:
            bad.append(f"{concept}: level 1 with no official_path")
    return tuple(bad)


def placement_coverage() -> dict[str, int]:
    """``level -> count``, plus the open-question count. For reports, not for gating.

    Keys are the levels as strings so the block survives a JSON round trip unchanged;
    ``open_domain_questions`` is beside them because a reader comparing *"40 concepts
    now have a home"* against *"8 questions are still open"* needs both numbers at
    once, and they are not the same measurement.
    """
    out = {str(level): 0 for level in PLACEMENT_LEVELS}
    for m in MAPPINGS.values():
        out[str(m.placement_level)] += 1
    out["open_domain_questions"] = len(open_domain_questions())
    out["concepts_with_an_open_question"] = sum(
        1 for m in MAPPINGS.values() if m.unresolved_questions
    )
    return out


def coverage() -> dict[str, int]:
    """Counts per status, plus the unexamined remainder. For reports, not for gating."""
    out = {status: 0 for status in sorted(MAPPING_STATUSES)}
    for m in MAPPINGS.values():
        out[m.status] += 1
    out["examined"] = len(MAPPINGS)
    out["not_examined"] = len(unmapped_concepts())
    out["concepts_total"] = len(ev.CONCEPTS)
    return out


# --- the schema, read rather than recalled -----------------------------------


@lru_cache(maxsize=1)
def _schema() -> dict:
    root = Path(__file__).resolve().parents[4]
    return json.loads(
        (root / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def official_paths() -> frozenset[str]:
    """Every dotted path the vendored official schema declares, ``[]`` marking an array.

    Walked out of the schema file at runtime. **Nothing in this module transcribes a
    path list**, so a schema refresh moves this set and :func:`registry_paths_exist`
    fails rather than the registry quietly pointing at a field that no longer exists.
    """
    out: set[str] = set()

    def walk(node: object, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        props = node.get("properties")
        if isinstance(props, dict):
            for key, child in props.items():
                path = f"{prefix}.{key}" if prefix else key
                out.add(path)
                walk(child, path)
                if isinstance(child, dict) and isinstance(child.get("items"), dict):
                    out.add(f"{path}[]")
                    walk(child["items"], f"{path}[]")

    walk(_schema(), "")
    return frozenset(out)


def registry_paths_exist() -> tuple[str, ...]:
    """Registry paths the official schema does NOT declare, sorted. Empty is correct.

    The guard that makes this registry checkable rather than merely asserted. It covers
    ``official_path`` AND ``requires_siblings`` AND ``candidate_homes`` — a sibling or a
    candidate home naming a field that does not exist would be exactly as misleading as
    a bad primary path, and a scientist sent to decide between two paths deserves both
    to be real.
    """
    declared = official_paths()
    missing: set[str] = set()
    for m in MAPPINGS.values():
        for path in (
            (m.official_path,) + m.requires_siblings + m.candidate_homes
        ):
            if path and path not in declared:
                missing.add(path)
    return tuple(sorted(missing))
