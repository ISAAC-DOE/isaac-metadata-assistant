"""NOMINAL VALUES — offered ONLY by a reviewed convention rule, and NONE is enabled.

WHAT CHANGED ON 2026-09-22, AND WHY THIS MODULE WAS NOT DELETED
===============================================================

This module used to supply ``context.temperature_K = 298`` for the BL15-2 "Angel-style"
profile, under ``DEC-43`` (2026-09-17). **``DEC-43`` IS SUPERSEDED.** On 2026-09-22 the
domain owner (Angel), relayed by the project owner, reconsidered it: leaving missing
data empty may be safest, 293 K may be the more common reading of "room temperature",
and published work / NIST should be checked. The check was made
(``docs/evidence/temperature-convention-research-2026-09-22.md``) and found that **both
293.15 K and 298.15 K are real conventions answering different questions** — neither is
evidence of what an unrecorded experiment's temperature was.

~~298 K is supplied on the scientist's authority for the BL15-2 Angel profile.~~ —
**withdrawn**, and struck rather than deleted because "this profile supplies 298" is
exactly the claim a future session would otherwise rebuild. The binding rule now is:

1. **The corpus states no temperature -> ``context.temperature_K`` stays MISSING.** A
   surface shows *Temperature — Not recorded*. There is no automatic insert and **no
   automatic proposal**. Measured default: ``nominal_offers`` is ``[]`` for every
   profile this build registers.
2. **A source that literally says "room temperature" / "RT" is preserved VERBATIM** —
   as a ``temperature_statement`` in the Extended Context companion — and is never
   converted to a number.
3. **A numeric nominal value may be OFFERED only by a :class:`NominalRule`** that (i) a
   reviewer attached to one convention profile at one version, (ii) names WHICH
   convention it adopts (:data:`CONVENTION_NTP_STYLE` or :data:`CONVENTION_SATP_STYLE`,
   each cited), (iii) is labelled nominal / inferred on the wire, (iv) reaches a record
   only as a PROPOSAL a scientist confirms, and (v) is never labelled measured.
4. **No such rule is enabled by default.** :data:`REVIEWED_NOMINAL_RULES` is EMPTY, and
   ``test_bl15_nominal.py`` fails if a production rule appears without that test being
   changed deliberately. The only way to enable one in this repository today is the
   test-only seam :func:`reviewed_rule_registered_for_tests`.

WHY THIS IS NOT A HOLE IN ``CLAUDE.md`` §5
==========================================

§5 forbids inventing a scientific value. A rule here cannot put a value anywhere: it can
only OFFER one, as an open proposal whose ``rule`` is the rule's own disclosure, and a
person accepting that proposal is the act that supplies it — recorded with the
``user_confirmation`` evidence that is this build's only human-act evidence type, behind
the ``409 human_actor_required`` gate every acceptance has. The number never travels
without its convention, its citation and ``measured: false``.

Pure data. No I/O, no clock, no environment read.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from . import profiles

__all__ = [
    "BASIS",
    "CONVENTIONS",
    "CONVENTION_NTP_STYLE",
    "CONVENTION_SATP_STYLE",
    "DETERMINISM",
    "NOMINAL_TEMPERATURE_PATH",
    "NominalConvention",
    "NominalRule",
    "NominalValue",
    "REVIEWED_NOMINAL_RULES",
    "SOURCE_CLASS",
    "SUPERSEDED_DECISION",
    "nominal_temperature_for",
    "profiles_with_a_nominal_default",
    "reviewed_rule_registered_for_tests",
]

#: The official path a nominal temperature would be offered for. Level 1 in `DEC-41`'s
#: hierarchy: the schema has a real numeric field.
NOMINAL_TEMPERATURE_PATH = "context.temperature_K"

#: What a nominal value IS, carried with every number.
BASIS = "nominal — inferred by a reviewed convention rule, NOT measured"
#: How it was arrived at, in the determinism vocabulary the review surface already uses.
DETERMINISM = "inferred"
#: Where the authority comes from: a reviewed rule, and a person's confirmation.
SOURCE_CLASS = "reviewed convention rule; applied only on a scientist's confirmation"

#: The decision this module used to implement, recorded so an auditor can find it.
SUPERSEDED_DECISION = (
    "DEC-43 (2026-09-17: 298 K as a nominal room temperature for the BL15-2 "
    "Angel-style profile) — SUPERSEDED 2026-09-22 by the domain owner's answer, "
    "relayed by the project owner: missing temperature stays missing; no automatic "
    "insert and no automatic proposal."
)

_RESEARCH_NOTE = "docs/evidence/temperature-convention-research-2026-09-22.md"


@dataclass(frozen=True)
class NominalConvention:
    """A named room-temperature convention, with the authority behind the number.

    **A convention is not a measurement and not a default.** It is the answer to "IF a
    scientist wants a nominal number here, which convention does it follow?" — and the
    two below answer different questions, which is exactly why a rule must name one.
    """

    convention_id: str
    label: str
    value: float
    unit: str
    authority: str
    retrieval_note: str

    def to_state(self) -> dict:
        return {
            "convention_id": self.convention_id,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "authority": self.authority,
            "retrieval_note": self.retrieval_note,
            "research_note": _RESEARCH_NOTE,
        }


CONVENTION_NTP_STYLE = NominalConvention(
    convention_id="ntp_style_293_15_K",
    label="NTP-style normal temperature (20 °C)",
    value=293.15,
    unit="K",
    authority=(
        "NIST usage of normal temperature and pressure (20 °C, 101.325 kPa); ISO 1's "
        "20 °C reference temperature for dimensional metrology."
    ),
    retrieval_note=(
        "Secondary sources only in the 2026-09-22 check; no NIST primary page was "
        "retrieved. See the research note."
    ),
)

CONVENTION_SATP_STYLE = NominalConvention(
    convention_id="satp_style_298_15_K",
    label="SATP-style standard ambient temperature (25 °C)",
    value=298.15,
    unit="K",
    authority=(
        "IUPAC standard ambient temperature and pressure (25 °C, 100 kPa) — a "
        "thermodynamic REFERENCE STATE for tabulating data, not a statement about any "
        "laboratory's temperature."
    ),
    retrieval_note=(
        "Secondary sources only in the 2026-09-22 check. See the research note."
    ),
)

CONVENTIONS: dict[str, NominalConvention] = {
    c.convention_id: c for c in (CONVENTION_NTP_STYLE, CONVENTION_SATP_STYLE)
}


@dataclass(frozen=True)
class NominalRule:
    """A REVIEWED rule permitting a nominal value to be OFFERED under one convention.

    Scoped to ONE convention profile at ONE version, like every convention rule; a rule
    reviewed against version 1 of a profile is not a rule about version 2.
    """

    rule_id: str
    rule_version: str
    profile_id: str
    profile_version: str
    official_path: str
    convention: NominalConvention
    #: Who reviewed it and on what basis — a sentence, because this build has no
    #: trusted identity to put here and must not pretend otherwise.
    reviewed_basis: str

    def __post_init__(self) -> None:
        if self.official_path != NOMINAL_TEMPERATURE_PATH:
            raise ValueError(
                "a nominal rule may only be written for context.temperature_K; a second "
                "path needs its own decision, not a rule entry"
            )
        profile = profiles.profile_for(self.profile_id)
        if profile is None:
            raise ValueError(f"{self.profile_id!r} is not a registered convention profile")
        if not self.reviewed_basis.strip():
            raise ValueError("a nominal rule must say who reviewed it and why")
        if self.convention.convention_id not in CONVENTIONS:
            raise ValueError("a nominal rule must adopt one of the named conventions")

    @property
    def disclosure(self) -> str:
        """The sentence that travels with the number, verbatim, wherever it goes."""
        c = self.convention
        return (
            f"{c.value:g} {c.unit} is a NOMINAL value under the {c.label} convention, "
            f"offered by reviewed rule {self.rule_id} (v{self.rule_version}) for "
            f"convention profile {self.profile_id} v{self.profile_version}. It was NOT "
            "measured and no source in the corpus states it; it becomes the record's "
            "value only if a scientist confirms it. Convention authority: "
            f"{c.authority}"
        )

    def to_state(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "official_path": self.official_path,
            "convention": self.convention.to_state(),
            "reviewed_basis": self.reviewed_basis,
        }


@dataclass(frozen=True)
class NominalValue:
    """A value a reviewed rule OFFERS, with the provenance that says so.

    There is deliberately **no** ``raw_literal``, ``source`` or ``locator``: inventing
    any of the three would turn an acknowledged convention into a fabricated
    measurement.
    """

    official_path: str
    value: float
    unit: str
    rule: NominalRule

    @property
    def measured(self) -> bool:
        """**Always ``False``.** Derived, so it cannot be persisted any other way."""
        return False

    @property
    def requires_confirmation(self) -> bool:
        """**Always ``True``.** It is offered as a proposal and nothing else."""
        return True

    @property
    def disclosure(self) -> str:
        return self.rule.disclosure

    @property
    def profile_id(self) -> str:
        return self.rule.profile_id

    @property
    def decision_ref(self) -> str:
        return self.rule.rule_id

    def to_state(self) -> dict:
        """The wire shape. ``measured``, ``basis`` and the convention are ALWAYS present."""
        return {
            "official_path": self.official_path,
            "value": self.value,
            "unit": self.unit,
            "basis": BASIS,
            "determinism": DETERMINISM,
            "source_class": SOURCE_CLASS,
            "measured": self.measured,
            "requires_confirmation": self.requires_confirmation,
            "convention": self.rule.convention.to_state(),
            "rule": self.rule.to_state(),
            "profile_id": self.rule.profile_id,
            "profile_version": self.rule.profile_version,
            "decision_ref": self.rule.rule_id,
            "disclosure": self.disclosure,
            "superseded_decision": SUPERSEDED_DECISION,
        }


#: **EMPTY, AND THE EMPTINESS IS THE POLICY.** No reviewed nominal rule is enabled in
#: this build. A production rule arrives here only through a failing test and a
#: recorded decision; tests use :func:`reviewed_rule_registered_for_tests`.
REVIEWED_NOMINAL_RULES: tuple[NominalRule, ...] = ()

#: The live registry: :data:`REVIEWED_NOMINAL_RULES` plus anything a test registered.
_ACTIVE: list[NominalRule] = list(REVIEWED_NOMINAL_RULES)


@contextmanager
def reviewed_rule_registered_for_tests(rule: NominalRule) -> Iterator[NominalRule]:
    """TEST-ONLY SEAM: enable one reviewed rule for the duration of a block.

    No production module calls this, and ``test_bl15_nominal.py`` greps the application
    package to keep it that way. It exists so the reviewed-rule PATH — offer, label,
    confirmation — is exercised end to end without a production rule existing.
    """
    _ACTIVE.append(rule)
    try:
        yield rule
    finally:
        _ACTIVE.remove(rule)


def profiles_with_a_nominal_default() -> tuple[str, ...]:
    """Profile ids that have ANY enabled nominal rule, sorted. ``()`` by default."""
    return tuple(sorted({r.profile_id for r in _ACTIVE}))


def nominal_temperature_for(profile_id: str | None) -> NominalValue | None:
    """The nominal temperature a reviewed rule offers for this profile, or ``None``.

    ``None`` for EVERY profile in this build unless a test enabled a rule — including
    the BL15-2 convention that ``DEC-43`` used to cover, ``None`` itself and an
    unregistered id. A caller that gets ``None`` leaves ``context.temperature_K`` absent,
    offers nothing, and lets the record stay blocked.

    Alias-aware: the historical id ``ssrl_bl152_angel`` resolves to the convention it
    now names, so a session persisted before the rename asks the same question.
    """
    if not profile_id:
        return None
    canonical = profiles.canonical_profile_id(profile_id)
    profile = profiles.profile_for(canonical)
    if profile is None:
        return None
    for rule in _ACTIVE:
        if (
            profiles.canonical_profile_id(rule.profile_id) == canonical
            and rule.profile_version == profile.profile_version
            and rule.official_path == NOMINAL_TEMPERATURE_PATH
        ):
            return NominalValue(
                official_path=rule.official_path,
                value=rule.convention.value,
                unit=rule.convention.unit,
                rule=rule,
            )
    return None
