"""`DEC-43` — THE ONE VALUE IN THIS PROGRAMME SUPPLIED WITHOUT A SOURCE, AND ITS FENCE.

WHAT IT IS
==========

``context.temperature_K = 298``, for the **BL15-2 Angel-style historical profile only**,
recorded as a nominal room-temperature assumption.

**THE CORPUS STATES NO TEMPERATURE ANYWHERE** — not in the beamtime README, not in the
notes, not in any acquisition header. That measurement is unchanged and is the reason
``mapping.TEMPERATURE_ABSENT_REASON`` exists and stays exactly as it is. What `DEC-43`
changes is not the measurement but the AUTHORITY: **298 is supplied on the scientist's
authority, not on the parser's.** The project owner adopted it as domain guidance for
this one profile. No reader inferred it, nothing computed it, and no source is cited for
it, because there is none.

WHY THIS IS NOT A HOLE IN ``CLAUDE.md`` §5
==========================================

§5 forbids *inventing or guessing* a scientific value, and it is otherwise **untouched**.
`DEC-43` is a named, dated, profile-scoped exception whose four conditions are what keep
it from generalising, and all four are enforced here rather than described:

1. **The provenance says it is NOT MEASURED.** :attr:`NominalValue.measured` is a
   derived, always-``False`` property, and :meth:`NominalValue.to_state` cannot emit an
   entry without it. *A record that shows 298 K without that qualifier is a defect, not
   a rounding* — `DEC-43`'s own words.
2. **BL15-2 Angel profile only, structurally.** :func:`nominal_temperature_for` is a
   lookup in :data:`NOMINAL_DEFAULTS`, keyed by profile id. Any other profile gets
   ``None``: the field stays **absent** and the record stays blocked, which is the
   pre-`DEC-43` behaviour preserved for everybody else.
3. **It does not generalize to any other required-but-absent field.**
   :data:`NOMINAL_DEFAULTS` holds exactly ONE entry and
   ``test_bl15_nominal.py`` fails if a second appears. Adding one by analogy with this
   one is what `DEC-43` condition (iii) forbids; adding one needs its own decision, its
   own date and its own review, not a tuple append.
4. **The authority is named in the artifact.** :data:`SOURCE_CLASS` says
   *domain guidance / project-owner adopted*, so a reader is never left inferring that
   something in the archive said it.

NEVER DESCRIBE IT AS MEASURED
=============================

Not in code, not in copy, not in a serialization, not in a test name. The word this
module uses for it is **nominal**, and :data:`BASIS` is the sentence that travels with
the number wherever it goes.

IT IS NOT A CORPUS CONCEPT, AND THAT IS WHY IT IS NOT IN ``bl15.evidence``
=========================================================================

``SourceEvidence`` answers *"where did ISAAC get this?"* and requires a source path, a
locator and a concept from :data:`bl15.evidence.CONCEPTS`. **A nominal value has no
source and no locator**, so expressing it as read evidence would require inventing
both — the precise fabrication §5 exists to stop. So :class:`NominalValue` is its own
type with its own provenance vocabulary, no ``concept``, and no place in the 45-concept
count.

Pure data. No I/O, no clock, no environment read.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import profiles

__all__ = [
    "BASIS",
    "NOMINAL_DEFAULTS",
    "NOMINAL_TEMPERATURE_K",
    "NOMINAL_TEMPERATURE_PATH",
    "NominalValue",
    "SOURCE_CLASS",
    "nominal_temperature_for",
    "profiles_with_a_nominal_default",
]


#: The official path the value is for. Level 1 in `DEC-41`'s hierarchy: the schema has a
#: real field, so nothing about this goes near the extended-context companion.
NOMINAL_TEMPERATURE_PATH = "context.temperature_K"

#: 298 K. Room temperature, as a scientist would state it.
NOMINAL_TEMPERATURE_K = 298

#: `DEC-43`'s own words for what this is. Carried with the number, always.
BASIS = "nominal room temperature"

#: Where the authority comes from — and it is a person, not a file. Stated so no reader
#: can conclude that something in the archive said it.
SOURCE_CLASS = "domain guidance / project-owner adopted"

#: The decision that authorizes it, so an auditor has one thing to look up.
DECISION_REF = "DEC-43"

#: Said in full, once, so it can be rendered verbatim rather than paraphrased.
DISCLOSURE = (
    "298 K is a nominal room-temperature assumption adopted for the BL15-2 "
    "Angel-style historical profile. It was NOT measured and no source in the corpus "
    "states a temperature: the value is supplied on the scientist's authority as "
    "domain guidance (DEC-43), not derived, inferred or computed by this application. "
    "It applies to this profile only; any other profile leaves the field absent."
)


@dataclass(frozen=True)
class NominalValue:
    """A value supplied by domain guidance, with the provenance that says so.

    Every field exists to keep the number from ever travelling bare. There is
    deliberately **no** ``raw_literal``, ``source`` or ``locator``: inventing any of the
    three is what would turn this from an acknowledged assumption into a fabricated
    measurement.
    """

    official_path: str
    value: int | float
    unit: str
    basis: str
    source_class: str
    profile_id: str
    profile_version: str
    decision_ref: str
    disclosure: str

    def __post_init__(self) -> None:
        if not self.basis or not self.source_class:
            raise ValueError(
                "a nominal value must carry both a basis and a source class: DEC-43 "
                "condition (i) makes the qualifier mandatory, not optional"
            )
        if profiles.profile_for(self.profile_id) is None:
            raise ValueError(
                f"{self.profile_id!r} is not a registered naming profile, so a nominal "
                "default cannot be scoped to it"
            )

    @property
    def measured(self) -> bool:
        """**Always ``False``.** Derived so it cannot be persisted any other way.

        A stored boolean could be written ``True`` by a careless caller, and the number
        would then travel claiming to be a measurement — `DEC-43` condition (i)'s named
        defect. ``ConceptMapping.proposable`` and
        ``extended_context.ContextEntry.is_official_field_value`` use the same
        discipline for the same reason.
        """
        return False

    def to_state(self) -> dict:
        """The wire shape. ``measured`` and ``basis`` are **always** present.

        There is no code path that serializes the value without the qualifier, which is
        what condition (i) requires: *a record that shows 298 K without it is a defect*.
        """
        return {
            "official_path": self.official_path,
            "value": self.value,
            "unit": self.unit,
            "basis": self.basis,
            "source_class": self.source_class,
            "measured": self.measured,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "decision_ref": self.decision_ref,
            "disclosure": self.disclosure,
        }


#: **EXACTLY ONE ENTRY, AND THE COUNT IS THE FENCE.**
#:
#: `DEC-43` condition (iii): *"it does not generalize to any other required-but-absent
#: field … no second such default may be added by analogy with this one."* A tuple makes
#: that mechanically checkable — ``test_bl15_nominal.py`` asserts the length, the path
#: and the profile, so a second default cannot arrive as a quiet append. It can still
#: arrive; it just has to arrive through a failing test and a decision.
NOMINAL_DEFAULTS: tuple[NominalValue, ...] = (
    NominalValue(
        official_path=NOMINAL_TEMPERATURE_PATH,
        value=NOMINAL_TEMPERATURE_K,
        unit="K",
        basis=BASIS,
        source_class=SOURCE_CLASS,
        profile_id=profiles.SSRL_BL152_ANGEL_V1.profile_id,
        profile_version=profiles.SSRL_BL152_ANGEL_V1.profile_version,
        decision_ref=DECISION_REF,
        disclosure=DISCLOSURE,
    ),
)


def profiles_with_a_nominal_default() -> tuple[str, ...]:
    """Profile ids that have any nominal default at all, sorted. One today."""
    return tuple(sorted({d.profile_id for d in NOMINAL_DEFAULTS}))


def nominal_temperature_for(profile_id: str | None) -> NominalValue | None:
    """The nominal temperature for this profile, or ``None``.

    ``None`` is the answer for **every** profile except the BL15-2 Angel one, including
    ``None`` itself and an unregistered id — `DEC-43` condition (ii). A caller that gets
    ``None`` must leave ``context.temperature_K`` **absent** and let the record stay
    blocked, which is exactly what ``mapping.TEMPERATURE_ABSENT_REASON`` describes and
    what every other profile keeps doing.

    There is no ``default=`` parameter and there will not be one: a parameter that let a
    caller supply a fallback would move the decision from this module to the call site,
    and the whole point of `DEC-43` is that the decision is made once, dated, and
    scoped.
    """
    if not profile_id:
        return None
    for default in NOMINAL_DEFAULTS:
        if (
            default.profile_id == profile_id
            and default.official_path == NOMINAL_TEMPERATURE_PATH
        ):
            return default
    return None
