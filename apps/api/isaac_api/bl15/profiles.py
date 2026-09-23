"""Versioned naming CONVENTIONS — **a registry, not one hard-coded convention, and not a person.**

**A CONVENTION IS NOT A SCIENTIST (corrected 2026-09-22).** The first profile here was
registered as ``ssrl_bl152_angel`` — "Angel-style" — and applied to a whole archive,
which quietly made "Angel-style" an architectural synonym for "every file Angel
touched". The project owner named why that is wrong: one beamtime's Runs 1-5 may be one
scientist's, 6-10 another's and 11-15 a third's; they may share a convention, use
different ones, switch mid-way, or collaborate on one Run. So:

* the profile is now named for the CONVENTION it encodes and the archive it was measured
  on (:data:`SSRL_BL152_HERFD_ECHEM_V1`, id ``ssrl_bl152_herfd_echem_naming``);
* the old id stays RESOLVABLE as a historical alias (:data:`PROFILE_ALIASES`), so every
  session, evidence item and companion entry stamped ``ssrl_bl152_angel`` before the
  rename still hydrates and still answers the same questions;
* WHICH convention applies to WHICH sources is decided by
  :mod:`bl15.applicability` — bindings at facility, beamline, acquisition-system,
  experiment, Run-subset, source-family or single-source scope — and **never by who ran
  a measurement**, which is provenance recorded beside the reading.

The rest of this docstring predates the correction and is kept because every word of it
about the convention's SHAPE is still true; read "one scientist's" as "one beamtime's".

**WHY A REGISTRY.** The only naming convention this repository has measured
evidence for belongs to ONE scientist's April-2025 beamtime
(``docs/evidence/bl15-2-corpus-characterization-2026-09-16.md``). A second
scientist, a second beamtime or a second beamline will name files differently,
and the thing that must not happen then is a rewrite of
:mod:`bl15.filenames`. Adding a second convention here means **adding a profile,
its alias tables and its fixtures** — the recognizers are shared, named, and
selected per profile.

**A PROFILE IS NOT A VALIDATOR.** Nothing here accepts or refuses a value; the
official schema is the only authority on validity (``CLAUDE.md`` §1). A profile's
job is to make the same filename read the same way twice, and to make the
convention it encodes *visible and versioned* rather than buried in a regex.

**THE ONE ORDERING FACT, NAMED SO IT IS NOT MISTAKEN FOR A GRAMMAR.** Recognition
is by SHAPE and by ALIAS. The single exception is that a bare integer's ROLE
depends on whether it is the first or a later bare integer in the stem
(:data:`RECOGNIZER_BARE_INTEGER`), because the convention says the run number
leads and the sample/electrode number follows it. That is an ordinal among the
numeric tokens, not a token position, and it is the only place any ordering is
consulted.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

# --- recognizer names --------------------------------------------------------
#
# A profile names the recognizers it uses, in order; :mod:`bl15.filenames` owns
# the implementations and looks them up by these names. The indirection is what
# lets a second profile reuse, reorder or drop a recognizer without touching the
# reader — and it is why these constants live here and not there.

RECOGNIZER_MEDIUM = "medium_alias"
RECOGNIZER_STATE = "state_alias"
RECOGNIZER_ACQUISITION_METHOD = "acquisition_method_alias"
RECOGNIZER_PREPARATION = "preparation_alias"
RECOGNIZER_CYCLING = "cycling_state"
RECOGNIZER_POTENTIAL = "potential_magnitude"
RECOGNIZER_FILTER = "filter"
RECOGNIZER_LOADING = "loading_or_thickness"
RECOGNIZER_STEP = "step_number"
RECOGNIZER_GAS = "gas_condition"
RECOGNIZER_PH = "ph"
RECOGNIZER_FLOW_RATE = "flow_rate"
RECOGNIZER_SAMPLE_NAME = "sample_name"
RECOGNIZER_BARE_INTEGER = "bare_integer_ordinal"

RECOGNIZER_NAMES: frozenset[str] = frozenset(
    {
        RECOGNIZER_MEDIUM,
        RECOGNIZER_STATE,
        RECOGNIZER_ACQUISITION_METHOD,
        RECOGNIZER_PREPARATION,
        RECOGNIZER_CYCLING,
        RECOGNIZER_POTENTIAL,
        RECOGNIZER_FILTER,
        RECOGNIZER_LOADING,
        RECOGNIZER_STEP,
        RECOGNIZER_GAS,
        RECOGNIZER_PH,
        RECOGNIZER_FLOW_RATE,
        RECOGNIZER_SAMPLE_NAME,
        RECOGNIZER_BARE_INTEGER,
    }
)


@dataclass(frozen=True)
class NamingProfile:
    """One filename CONVENTION, versioned. ~~One scientist's filename convention~~ —
    corrected 2026-09-22: a convention may be shared by several scientists and one
    scientist may use several; see the module docstring.

    Alias tables are ``((source literal, canonical reading), ...)`` tuples rather
    than dicts so the profile stays frozen and hashable, and they are matched
    **case-insensitively** — the corpus writes ``asIs`` and ``AsIs``,
    ``noElectrolyte`` and ``NoElectrolyte``, ``filter35`` and ``Filter35``,
    ``after1400Cycling`` and ``after1400cycling``, ``1600mV`` and ``1600mv``.
    Folding case is itself a normalisation and every reading that needed it says
    so through its ``normalization_rule`` (see :mod:`bl15.filenames`).

    :attr:`profile_version` is part of the identity of every piece of evidence a
    reader stamps. If an alias table changes meaning, the version changes — so a
    record imported last month can be told apart from the same file read under a
    revised convention.
    """

    profile_id: str
    profile_version: str
    display_name: str
    description: str
    #: Ordered recognizer names, each one of :data:`RECOGNIZER_NAMES`. Order is
    #: consulted so an explicit ALIAS always beats a SHAPE guess.
    token_recognizers: tuple[str, ...]
    #: ``acid``/``base``/``NoElectrolyte`` -> a canonical reading.
    medium_aliases: tuple[tuple[str, str], ...] = ()
    #: ``newSpots``/``again``/``dry``/``asIs``/``newGrid``/``ave``.
    state_aliases: tuple[tuple[str, str], ...] = ()
    #: ``HERFD``/``TRANSMISSION``.
    acquisition_method_aliases: tuple[tuple[str, str], ...] = ()
    #: ``pellet``/``oldPellet``.
    preparation_aliases: tuple[tuple[str, str], ...] = ()
    #: Gas atmospheres. Corpus-attested in the beamtime NOTES, not in any
    #: filename of this archive — see :data:`_UNEXERCISED_IN_FILENAMES`.
    gas_aliases: tuple[tuple[str, str], ...] = ()
    #: Sample names that no shape rule can reach, e.g. a chemical formula.
    sample_name_aliases: tuple[tuple[str, str], ...] = ()
    #: Shape of a sample CODE (uppercase letters then digits, optional trailing
    #: letter). Empty string disables the shape rule for a profile that wants
    #: alias-only sample naming.
    sample_code_pattern: str = ""
    #: Historical ids that resolve to this convention. A stamped id is never rewritten;
    #: it is resolved, so old evidence keeps saying what it said.
    aliases: tuple[str, ...] = ()
    #: What the convention was MEASURED ON — the archive and beamtime — so a reader can
    #: tell a convention observed once from a beamline standard. Descriptive only.
    measured_on: str = ""
    #: Built in ``__post_init__`` from the alias tuples; ``compare=False`` keeps
    #: the dataclass hashable. Populated in place rather than rebound, which a
    #: frozen dataclass permits.
    _folded: dict = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        for name in self.token_recognizers:
            if name not in RECOGNIZER_NAMES:
                raise ValueError(f"unknown recognizer: {name!r}")
        for key, pairs in (
            ("medium", self.medium_aliases),
            ("state", self.state_aliases),
            ("acquisition_method", self.acquisition_method_aliases),
            ("preparation", self.preparation_aliases),
            ("gas", self.gas_aliases),
            ("sample_name", self.sample_name_aliases),
        ):
            self._folded[key] = {
                literal.casefold(): canonical for literal, canonical in pairs
            }

    def alias(self, table: str, token: str) -> str | None:
        """The canonical reading of ``token`` in ``table``, or ``None``.

        Case-insensitive on purpose, and the CALLER is responsible for recording
        that fact: a reading reached by folding case is a normalisation, and
        :class:`~isaac_api.bl15.evidence.SourceEvidence` refuses one without a
        named rule.
        """
        return self._folded.get(table, {}).get(token.casefold())

    def alias_literals(self, table: str) -> tuple[str, ...]:
        """Every literal declared in one alias table, for tests and surfaces."""
        mapping = {
            "medium": self.medium_aliases,
            "state": self.state_aliases,
            "acquisition_method": self.acquisition_method_aliases,
            "preparation": self.preparation_aliases,
            "gas": self.gas_aliases,
            "sample_name": self.sample_name_aliases,
        }
        return tuple(literal for literal, _ in mapping.get(table, ()))

    def to_state(self) -> dict:
        """What a surface lists about a convention. No alias TABLE is served — the
        tables are this build's reading aid, and the review surface already shows every
        reading with the rule that produced it."""
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "measured_on": self.measured_on,
            "is_default": self.profile_id == DEFAULT_PROFILE_ID,
            "unexercised_recognizers": sorted(
                name for name in self.token_recognizers if name in UNEXERCISED_RECOGNIZERS
            ),
        }


#: Recognizers this profile carries for which **no instance occurs anywhere in
#: the measured filenames of the supplied archive.** The convention the project
#: owner recorded names gas condition, pH and flow rate, and the beamtime notes
#: state all three in prose for Sample 7 (``NaOH at a stated concentration, with a pH`` / ``Ar sat`` /
#: ``Flow cell = 10 ml/min``) — so the CONCEPTS are corpus-attested, but their
#: **filename spellings are not**. These three recognizers are therefore
#: convention-derived rather than corpus-measured, are exercised only by
#: synthetic fixtures, and are the first thing to re-measure when a second
#: archive arrives. Named here rather than left implicit, because "this
#: recognizer has never seen a real example" is exactly the sort of thing that
#: silently becomes a wrong alias table.
_UNEXERCISED_IN_FILENAMES: frozenset[str] = frozenset(
    {RECOGNIZER_GAS, RECOGNIZER_PH, RECOGNIZER_FLOW_RATE}
)

UNEXERCISED_RECOGNIZERS: frozenset[str] = _UNEXERCISED_IN_FILENAMES


#: The id this convention was registered under until 2026-09-22. RESOLVABLE, never
#: reused: see :data:`PROFILE_ALIASES`.
HISTORICAL_ANGEL_PROFILE_ID = "ssrl_bl152_angel"

SSRL_BL152_HERFD_ECHEM_V1 = NamingProfile(
    profile_id="ssrl_bl152_herfd_echem_naming",
    profile_version="1",
    display_name=(
        "SSRL BL15-2 HERFD electrochemistry filename convention v1 — measured on "
        "the April 2025 IrOx beamtime archive"
    ),
    aliases=(HISTORICAL_ANGEL_PROFILE_ID,),
    measured_on=(
        "One archive: a single April-2025 SSRL BL15-2 HERFD electrochemistry "
        "beamtime (the IrOx archive the project owner supplied on 2026-09-16). "
        "Registered until 2026-09-22 as `ssrl_bl152_angel`."
    ),
    description=(
        "A FILENAME CONVENTION, NOT A PERSON. ~~one scientist's habits~~ — "
        "corrected 2026-09-22: the convention is what the FILES of one beamtime "
        "show, and whoever ran a given measurement is provenance recorded beside "
        "the reading, never the reason a file is read this way.\n"
        "\n"
        "THE FIRST PROFILE IN THIS REPOSITORY, AND EXPLICITLY NOT A BEAMLINE "
        "STANDARD. It is built from ONE measured archive: a single April-2025 "
        "SSRL BL15-2 beamtime, one element. Nothing in "
        "it is authority for how any other BL15-2 user names a file, and "
        "nothing in it is an ISAAC field mapping.\n"
        "\n"
        "THE CONVENTION THE PROJECT OWNER SUPPLIED, VERBATIM:\n"
        "\n"
        "    runNo_sample/electrodeNo_sampleName_loading_electrolyte_gas_"
        "condition_pH_flowRate_filter_Potential\n"
        "\n"
        "THAT IS A VOCABULARY AND NOT A POSITIONAL GRAMMAR, and the measured "
        "corpus is what settles it:\n"
        "  * `71_07_IrTiO2_0p5nm_AsIs_NoElectrolyte` carries NO potential and "
        "NO filter, so a positional reader would read the potential out of a "
        "sample-state token.\n"
        "  * `52_05_JK1_base_after1stCycling_filter20_850mV_step05` carries a "
        "step index the convention does not mention at all.\n"
        "  * `03_01_JK3_acid_beforeCycling_060mV_filter10` puts the potential "
        "BEFORE the filter; `06_01_JK3_acid_after1200mVCycling_filter10_060mV` "
        "puts it after. Same scientist, same sample, same week.\n"
        "  * `46_04_JK2_base_after1500Cycling_ffilter35_newSpots_1600mV` "
        "misspells the filter prefix.\n"
        "  * `01_IrO2_oldPellet_f35` has ONE numeric token where the convention "
        "implies two.\n"
        "Every token is therefore recognised independently, by shape and by "
        "alias; an unrecognised token survives as `unknown_token` rather than "
        "shifting every other token's meaning."
    ),
    token_recognizers=(
        # Alias tables first, so an explicit literal always beats a shape rule.
        RECOGNIZER_MEDIUM,
        RECOGNIZER_STATE,
        RECOGNIZER_ACQUISITION_METHOD,
        RECOGNIZER_PREPARATION,
        RECOGNIZER_GAS,
        # Shape rules, ordered most specific first.
        RECOGNIZER_CYCLING,
        RECOGNIZER_POTENTIAL,
        RECOGNIZER_FILTER,
        RECOGNIZER_LOADING,
        RECOGNIZER_STEP,
        RECOGNIZER_PH,
        RECOGNIZER_FLOW_RATE,
        RECOGNIZER_SAMPLE_NAME,
        RECOGNIZER_BARE_INTEGER,
    ),
    medium_aliases=(
        # `acid` and `base` are read AS THEMSELVES and never expanded. The
        # beamtime notes name an acid and an alkali, each with a concentration, and binding either
        # to a filename token would be this package answering a question with a
        # domain owner (`docs/bl15-2-domain-questions-2026-09-16.md`) — and the
        # notes contradict themselves about it (characterization §3.7).
        ("acid", "acid"),
        ("base", "base"),
        ("NoElectrolyte", "none"),
        ("noElectrolyte", "none"),
    ),
    state_aliases=(
        ("newSpots", "new_spot"),
        ("newSpot", "new_spot"),
        ("newGrid", "new_grid"),
        ("again", "repeat"),
        ("ave", "averaged"),
        ("dry", "dry"),
        ("asIs", "as_is"),
    ),
    acquisition_method_aliases=(
        ("HERFD", "herfd"),
        ("TRANSMISSION", "transmission"),
    ),
    preparation_aliases=(
        ("pellet", "pellet"),
        ("oldPellet", "old_pellet"),
    ),
    gas_aliases=(
        # Convention-derived, not corpus-measured in a filename; see
        # _UNEXERCISED_IN_FILENAMES.
        ("Ar", "ar"),
        ("ArSat", "ar_saturated"),
        ("N2", "n2"),
        ("N2Sat", "n2_saturated"),
        ("O2", "o2"),
        ("O2Sat", "o2_saturated"),
        ("air", "air"),
    ),
    sample_name_aliases=(
        # Formula-style names no uppercase-code shape can reach. Both literals
        # appear in filenames the characterization document already quotes
        # (`71_07_IrTiO2_...`, `IrO2_5wpc_pellet_transmission`), which is the
        # boundary `CLAUDE.md` §6 draws for what may be committed.
        ("IrO2", "IrO2"),
        ("IrTiO2", "IrTiO2"),
    ),
    #: `JK1`, `JK2`, `JK3`, `JK1C` — uppercase code, digits, optional trailing
    #: letter. Checked against every token in the measured corpus: it matches
    #: those four and nothing else, so it introduces no false sample name.
    sample_code_pattern=r"^[A-Z]{2,}[0-9]+[A-Z]?$",
)


#: ~~SSRL_BL152_ANGEL_V1~~ — the OLD NAME, kept as an alias of the same object so a
#: caller written before the rename keeps working. New code names the convention.
SSRL_BL152_ANGEL_V1 = SSRL_BL152_HERFD_ECHEM_V1

PROFILES: dict[str, NamingProfile] = {
    SSRL_BL152_HERFD_ECHEM_V1.profile_id: SSRL_BL152_HERFD_ECHEM_V1,
}

#: ``historical id -> current id``. Derived from each profile's own ``aliases`` so the
#: two cannot disagree; a stamped id is RESOLVED through this, never rewritten.
PROFILE_ALIASES: dict[str, str] = {
    alias: profile.profile_id
    for profile in PROFILES.values()
    for alias in profile.aliases
}

#: What a caller with no profile preference gets: the build's default BINDING
#: (:func:`bl15.applicability.default_binding`), stated as a default wherever it is
#: applied. A second convention must be CHOSEN — by a binding — never defaulted into.
DEFAULT_PROFILE_ID = SSRL_BL152_HERFD_ECHEM_V1.profile_id


def canonical_profile_id(profile_id: str | None) -> str | None:
    """The current id for ``profile_id`` — itself, or what its historical alias names."""
    if not profile_id:
        return profile_id
    return PROFILE_ALIASES.get(profile_id, profile_id)


def profile_for(profile_id: str) -> NamingProfile | None:
    """The profile with this id — or with this HISTORICAL id — or ``None``.

    Returns ``None`` rather than raising: a reader handed an unknown profile id
    must REFUSE with a reason a scientist can read, not crash the import.
    Alias-aware since 2026-09-22, so ``ssrl_bl152_angel`` still resolves.
    """
    return PROFILES.get(canonical_profile_id(profile_id) or "")


def registered_profiles() -> list[dict]:
    """Every registered convention, for a surface to list. Sorted by id."""
    return [PROFILES[pid].to_state() for pid in sorted(PROFILES)]


@contextmanager
def registered_for_tests(profile: NamingProfile) -> Iterator[NamingProfile]:
    """TEST-ONLY SEAM: register one additional convention for the duration of a block.

    The second convention a multi-convention test needs must not look like a real
    beamline standard, so it is never registered in production — no application module
    calls this, and ``test_historical_semantics.py`` greps the package to keep it so.
    """
    if profile.profile_id in PROFILES:
        raise ValueError(f"{profile.profile_id!r} is already registered")
    PROFILES[profile.profile_id] = profile
    added = [alias for alias in profile.aliases if alias not in PROFILE_ALIASES]
    for alias in added:
        PROFILE_ALIASES[alias] = profile.profile_id
    try:
        yield profile
    finally:
        del PROFILES[profile.profile_id]
        for alias in added:
            PROFILE_ALIASES.pop(alias, None)
