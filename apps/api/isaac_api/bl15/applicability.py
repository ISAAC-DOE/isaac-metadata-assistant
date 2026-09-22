"""WHICH naming convention applies to WHICH sources — and why. Never "whose files these are".

THE CORRECTION THIS MODULE EXISTS TO MAKE
=========================================

Until 2026-09-22 the build had one profile, ``ssrl_bl152_angel`` ("Angel-style"),
applied to a whole archive. That conflated two things that are different in the real
world, and the project owner named the difference: one beamtime's Runs 1-5 may be
measured by one scientist, 6-10 by another and 11-15 by a third; they may share a
convention, use different ones, switch mid-way, or collaborate on one Run. **A parsing
convention and the person who ran a measurement are separate concepts, and parsing is
never keyed on the person.**

So a profile is selected by a :class:`ProfileBinding` — a convention bound to a SCOPE
by a stated BASIS (the build's default, a choice made in this import, or a
scientist-confirmed rule). The hierarchy has seven levels — facility, beamline,
acquisition system, experiment, a family of sources, a subset of Runs, one source — and
**IN THIS BUILD FIVE OF THEM ARE REACHABLE** (:data:`REACHABLE_SCOPES`, corrected
2026-09-22 after an independent review found the seven claimed as available): the
build's default binding sits at ``acquisition_system``, and a recorded rule's selector
places it at ``experiment`` (no selector), ``source_family`` (source types),
``run_subset`` (legacy range, group tokens or stem prefixes) or ``source`` (named
files). No selector can express a facility or a beamline, because every source this
build reads is from one; those two levels are kept as ordering constants so a binding
from a future multi-facility reader slots in without renumbering, and nothing produces
one today. The operator is recorded as PROVENANCE beside
the reading (:mod:`bl15.notes` reads an explicit labelled contributor line; the
historical-import layer carries it per measurement) and is consulted by nothing in this
module. There is deliberately no ``operator`` field on a binding or a selector.

THE HIERARCHY, IN ORDER
=======================

Source -> source-format parser -> facility / beamline / acquisition-system knowledge ->
Experiment/beamtime context -> applicable naming convention -> Run/source-specific
overrides -> operator/contributor provenance -> normalised ISAAC concepts.

In this module that is one rule: **the most specific matching binding wins**, by
:data:`SCOPE_SPECIFICITY`. That is an ordering of APPLICABILITY — which convention is in
force for a file — and it is not, and must not become, an ordering of SOURCES for
resolving a disagreement between them. There is no source hierarchy anywhere in this
package; see :mod:`bl15.resolution`.

A TIE IS AN AMBIGUITY, NEVER A GUESS
====================================

Two bindings at the same specificity naming DIFFERENT conventions for one source is not
resolved by picking one. The source is read under EACH (every statement stamped with its
own ``profile_id``), so any token the two conventions read differently becomes a visible
disagreement in the candidate stream — the existing "no value when sources disagree"
invariant does the rest — and the tie itself is reported here as :attr:`Applicability.ambiguity`.

Pure data, pure functions. No I/O.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from . import profiles as prof

__all__ = [
    "Applicability",
    "BASIS_BUILD_DEFAULT",
    "BASIS_CONFIRMED_RULE",
    "BASIS_IMPORT_CHOICE",
    "BINDING_BASES",
    "ProfileBinding",
    "REACHABLE_SCOPES",
    "SCOPES",
    "SCOPE_SPECIFICITY",
    "Selector",
    "default_binding",
    "resolve",
]

SCOPE_FACILITY = "facility"
SCOPE_BEAMLINE = "beamline"
SCOPE_ACQUISITION_SYSTEM = "acquisition_system"
SCOPE_EXPERIMENT = "experiment"
SCOPE_SOURCE_FAMILY = "source_family"
SCOPE_RUN_SUBSET = "run_subset"
SCOPE_SOURCE = "source"

#: Broader first. A binding at a higher number is more specific and wins over one at a
#: lower number for a source both match.
SCOPE_SPECIFICITY: Mapping[str, int] = {
    SCOPE_FACILITY: 0,
    SCOPE_BEAMLINE: 1,
    SCOPE_ACQUISITION_SYSTEM: 2,
    SCOPE_EXPERIMENT: 3,
    SCOPE_SOURCE_FAMILY: 4,
    SCOPE_RUN_SUBSET: 5,
    SCOPE_SOURCE: 6,
}
SCOPES: frozenset[str] = frozenset(SCOPE_SPECIFICITY)
#: The levels a binding can actually reach in THIS build: the default binding's level
#: plus the four a recorded rule's selector can express. See the module docstring.
REACHABLE_SCOPES: frozenset[str] = frozenset(
    {SCOPE_ACQUISITION_SYSTEM, SCOPE_EXPERIMENT, SCOPE_SOURCE_FAMILY, SCOPE_RUN_SUBSET, SCOPE_SOURCE}
)

#: The build's own default: the only registered convention for this kind of archive,
#: applied because nothing more specific matched. A LEAD, stated as one.
BASIS_BUILD_DEFAULT = "build_default"
#: Chosen for this import only ("apply only here"). Non-durable, like the session.
BASIS_IMPORT_CHOICE = "import_session_choice"
#: A scientist-confirmed rule recorded on an experiment. Durable where the experiment is.
BASIS_CONFIRMED_RULE = "confirmed_rule"

BINDING_BASES: frozenset[str] = frozenset(
    {BASIS_BUILD_DEFAULT, BASIS_IMPORT_CHOICE, BASIS_CONFIRMED_RULE}
)

_LEGACY = re.compile(r"^(\d+)_")
#: Bounds, so a crafted selector cannot grow a session document without limit.
MAX_SELECTOR_ITEMS = 64
MAX_SELECTOR_TEXT = 256


def legacy_number_of(stem: str) -> int | None:
    """The leading legacy number of a measurement stem, or ``None``. Same rule as relate."""
    match = _LEGACY.match(stem or "")
    return int(match.group(1)) if match else None


def group_token_of(stem: str) -> str | None:
    """The second numeric token, when the first is numeric. Same rule as relate."""
    parts = (stem or "").split("_")
    if len(parts) > 1 and parts[0].isdigit() and parts[1].isdigit():
        return parts[1]
    return None


def _clean_texts(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"selector `{label}` must be a list of strings")
    if len(value) > MAX_SELECTOR_ITEMS:
        raise ValueError(
            f"selector `{label}` holds more than {MAX_SELECTOR_ITEMS} entries"
        )
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"selector `{label}` entries must be non-blank strings")
        if len(item) > MAX_SELECTOR_TEXT:
            raise ValueError(f"a selector `{label}` entry is too long")
        out.append(item.strip())
    return tuple(sorted(set(out)))


@dataclass(frozen=True)
class Selector:
    """WHICH sources a binding or a rule applies to. Every field narrows; empty = all.

    Deliberately limited to things a source's own NAME and CLASSIFICATION state — a
    legacy-number range, sample-group tokens, stem prefixes, source types, exact archive
    paths. **There is no operator field, and there must not be one:** selecting a
    convention by who ran a measurement is exactly the conflation this module removes.
    """

    legacy_range: tuple[int, int] | None = None
    group_tokens: tuple[str, ...] = ()
    stem_prefixes: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.legacy_range is not None:
            low, high = self.legacy_range
            if (
                isinstance(low, bool)
                or isinstance(high, bool)
                or not isinstance(low, int)
                or not isinstance(high, int)
                or low < 0
                or high < low
            ):
                raise ValueError("legacy_range must be two non-negative integers, low <= high")

    @property
    def is_everything(self) -> bool:
        return not (
            self.legacy_range
            or self.group_tokens
            or self.stem_prefixes
            or self.source_types
            or self.source_paths
        )

    def matches(self, *, archive_path: str, stem: str, source_type: str | None) -> bool:
        if self.source_paths and archive_path not in self.source_paths:
            return False
        if self.source_types and (source_type or "") not in self.source_types:
            return False
        if self.stem_prefixes and not any(stem.startswith(p) for p in self.stem_prefixes):
            return False
        if self.group_tokens and group_token_of(stem) not in self.group_tokens:
            return False
        if self.legacy_range is not None:
            legacy = legacy_number_of(stem)
            if legacy is None or not (self.legacy_range[0] <= legacy <= self.legacy_range[1]):
                return False
        return True

    def describe(self) -> str:
        """A sentence a scientist reads to know which files this applies to."""
        if self.is_everything:
            return "every source"
        parts: list[str] = []
        if self.legacy_range is not None:
            low, high = self.legacy_range
            parts.append(
                f"legacy number {low}" if low == high else f"legacy numbers {low}-{high}"
            )
        if self.group_tokens:
            parts.append("sample group " + ", ".join(self.group_tokens))
        if self.stem_prefixes:
            parts.append("names starting " + ", ".join(self.stem_prefixes))
        if self.source_types:
            parts.append("source type " + ", ".join(self.source_types))
        if self.source_paths:
            parts.append(f"{len(self.source_paths)} named file(s)")
        return "; ".join(parts)

    def to_state(self) -> dict:
        return {
            "legacy_range": list(self.legacy_range) if self.legacy_range else None,
            "group_tokens": list(self.group_tokens),
            "stem_prefixes": list(self.stem_prefixes),
            "source_types": list(self.source_types),
            "source_paths": list(self.source_paths),
            "description": self.describe(),
        }

    @classmethod
    def from_state(cls, state: object) -> "Selector":
        """Parse a selector a CLIENT sent or a document stored. Raises ``ValueError``."""
        if state is None:
            return cls()
        if not isinstance(state, Mapping):
            raise ValueError("a selector must be an object")
        unknown = set(state) - {
            "legacy_range",
            "group_tokens",
            "stem_prefixes",
            "source_types",
            "source_paths",
            "description",
        }
        if unknown:
            raise ValueError(f"unknown selector key(s): {sorted(unknown)}")
        raw_range = state.get("legacy_range")
        legacy_range = None
        if raw_range is not None:
            if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
                raise ValueError("legacy_range must be [low, high]")
            legacy_range = (raw_range[0], raw_range[1])
        return cls(
            legacy_range=legacy_range,
            group_tokens=_clean_texts(state.get("group_tokens"), "group_tokens"),
            stem_prefixes=_clean_texts(state.get("stem_prefixes"), "stem_prefixes"),
            source_types=_clean_texts(state.get("source_types"), "source_types"),
            source_paths=_clean_texts(state.get("source_paths"), "source_paths"),
        )


@dataclass(frozen=True)
class ProfileBinding:
    """A convention bound to a scope, with the basis that put it there."""

    binding_id: str
    profile_id: str
    profile_version: str
    scope: str
    selector: Selector = field(default_factory=Selector)
    basis: str = BASIS_BUILD_DEFAULT
    #: The rule id when :attr:`basis` is a rule, so a reader can find who confirmed it.
    rule_ref: str | None = None

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise ValueError(f"unknown binding scope {self.scope!r}")
        if self.basis not in BINDING_BASES:
            raise ValueError(f"unknown binding basis {self.basis!r}")

    @property
    def specificity(self) -> int:
        return SCOPE_SPECIFICITY[self.scope]

    def to_state(self) -> dict:
        profile = prof.profile_for(self.profile_id)
        return {
            "binding_id": self.binding_id,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_display_name": profile.display_name if profile else None,
            "scope": self.scope,
            "selector": self.selector.to_state(),
            "basis": self.basis,
            "rule_ref": self.rule_ref,
        }


def default_binding() -> ProfileBinding:
    """The build default: the registered BL15-2 convention, at acquisition-system scope.

    ACQUISITION-SYSTEM SCOPE and not beamline or facility, because what the convention
    was measured on is the file NAMES a SPEC session at BL15-2 wrote during one
    beamtime — a statement about that system's output, not about every BL15-2 user.
    Its basis says it is a default, so no surface can present it as a confirmed fact
    about a particular archive.
    """
    profile = prof.PROFILES[prof.DEFAULT_PROFILE_ID]
    return ProfileBinding(
        binding_id="build-default",
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        scope=SCOPE_ACQUISITION_SYSTEM,
        basis=BASIS_BUILD_DEFAULT,
    )


@dataclass(frozen=True)
class Applicability:
    """Which convention(s) one source was read under, and why."""

    profile_ids: tuple[str, ...]
    profile_versions: tuple[str, ...]
    scope: str
    basis: str
    binding_ids: tuple[str, ...]
    selector_description: str
    rule_refs: tuple[str, ...] = ()
    #: Set when two bindings of equal specificity named different conventions. The
    #: source was then read under each; nothing was chosen.
    ambiguity: str | None = None
    #: Bindings that matched this source and were NOT applied because the convention
    #: they name is registered at a different version today. Reported, never silently
    #: upgraded: a rule confirmed against v1 is not a rule about v2.
    stale_bindings: tuple[str, ...] = ()

    @property
    def ambiguous(self) -> bool:
        return self.ambiguity is not None

    def to_state(self) -> dict:
        return {
            "profile_ids": list(self.profile_ids),
            "profile_versions": list(self.profile_versions),
            "scope": self.scope,
            "basis": self.basis,
            "binding_ids": list(self.binding_ids),
            "rule_refs": list(self.rule_refs),
            "selector_description": self.selector_description,
            "ambiguous": self.ambiguous,
            "ambiguity": self.ambiguity,
            "stale_bindings": list(self.stale_bindings),
        }


def resolve(
    bindings: Sequence[ProfileBinding],
    *,
    archive_path: str,
    stem: str,
    source_type: str | None,
) -> Applicability:
    """The applicable convention(s) for ONE source. Deterministic; never raises.

    The build default is always a candidate, so every source is read under SOMETHING —
    and a source no binding matched says so in its basis rather than looking chosen.
    """
    candidates = [default_binding(), *bindings]
    matching: list[ProfileBinding] = []
    stale: list[str] = []
    for binding in candidates:
        if not binding.selector.matches(
            archive_path=archive_path, stem=stem, source_type=source_type
        ):
            continue
        profile = prof.profile_for(binding.profile_id)
        if profile is None or profile.profile_version != binding.profile_version:
            stale.append(binding.binding_id)
            continue
        matching.append(binding)
    top = max(b.specificity for b in matching)
    winners = sorted(
        (b for b in matching if b.specificity == top),
        key=lambda b: (b.profile_id, b.binding_id),
    )
    profile_ids = tuple(sorted({prof.canonical_profile_id(b.profile_id) for b in winners}))
    ambiguity = None
    if len(profile_ids) > 1:
        ambiguity = (
            f"{len(winners)} bindings at {winners[0].scope} scope name different "
            f"conventions ({', '.join(profile_ids)}) for this source. It was read under "
            "each; nothing was chosen, and any token they read differently is shown as "
            "a disagreement."
        )
    versions = tuple(
        prof.PROFILES[pid].profile_version for pid in profile_ids if pid in prof.PROFILES
    )
    return Applicability(
        profile_ids=profile_ids,
        profile_versions=versions,
        scope=winners[0].scope,
        basis=winners[0].basis if len({b.basis for b in winners}) == 1 else "mixed",
        binding_ids=tuple(b.binding_id for b in winners),
        rule_refs=tuple(b.rule_ref for b in winners if b.rule_ref),
        selector_description=winners[0].selector.describe(),
        ambiguity=ambiguity,
        stale_bindings=tuple(sorted(stale)),
    )
