"""Profile-driven token reading: one filename in, one statement per token out.

**THE WHOLE DESIGN IN ONE SENTENCE.** Split the stem on ``_``, hand each token to
every recognizer the profile names until one claims it, and emit one
:class:`~isaac_api.bl15.evidence.SourceEvidence` per token — including for the
tokens nothing claimed.

**WHY NOT POSITIONAL.** The convention the project owner recorded reads like a
grammar and the corpus proves it is not one. Measured: a stem with no potential
and no filter (``71_07_IrTiO2_0p5nm_AsIs_NoElectrolyte``); a stem with a step
index the convention never mentions (``52_05_..._850mV_step05``); potential
before filter in one stem and after it in the next; one numeric token where the
convention implies two (``01_IrO2_oldPellet_f35``). A positional reader gets the
first of those four wrong in a way that is invisible: it reports a potential, at
a plausible-looking value, read out of a sample-state token.

**AN UNKNOWN TOKEN IS A RESULT, NOT A FAILURE.** A stem where six of eight tokens
are recognised produces six named statements and two ``unknown_token``
statements, and the two are as visible as the six. Dropping them would be
``HIST-004``'s banned *"Upload -> Spinner -> Mysterious JSON"* one layer down:
the scientist would have no way to see what was passed over, and no way to tell
"this profile does not know this word" from "this word was not there".

**WHAT THIS MODULE DELIBERATELY DOES NOT DO.**

* It never emits
  :data:`~isaac_api.bl15.evidence.CONCEPT_POTENTIAL_REFERENCE`. A filename states
  a MAGNITUDE (``850mV``) and says nothing whatever about what it is measured
  against; the beamtime notes say ``vs reference`` for the JK samples and
  ``RHE electrode`` for the later TiO2 one. A magnitude with an unknown basis is
  a different fact from a magnitude with a known one, and this reader has no
  access to the second. Enforced by test.
* It never expands ``acid`` to a named acid at a concentration, or ``base`` to a named
  alkali at a concentration. The
  notes say both, and contradict themselves about it (characterization §3.7).
* It never resolves whether the ``1500`` in ``after1500Cycling`` is millivolts or
  a cycle count. ``after1200mVCycling`` states millivolts explicitly and
  ``after1stCycling`` states an ordinal, in the same corpus, from the same
  scientist — so the bare form is genuinely ambiguous and is read as a
  case-folded literal with no magnitude and no unit.

**LOCATOR FORMAT**, fixed so a surface can rely on it::

    filename token 4 [chars 23..31]

The token index and the character span are both **0-based**, and the span is
half-open: ``stem[23:31]`` is exactly :attr:`SourceEvidence.raw_literal`. A test
asserts that identity for every token of every fixture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ._emit import EvidenceBuilder, refusal
from .evidence import (
    CONCEPT_ACQUISITION_METHOD,
    CONCEPT_BEFORE_AFTER_STATE,
    CONCEPT_CYCLING_STATE,
    CONCEPT_DRY_STATE,
    CONCEPT_ELECTROLYTE_OR_MEDIUM,
    CONCEPT_FILTER,
    CONCEPT_FLOW_RATE,
    CONCEPT_GAS_CONDITION,
    CONCEPT_LEGACY_NUMBER,
    CONCEPT_LOADING_OR_THICKNESS,
    CONCEPT_NEW_SPOT,
    CONCEPT_PH,
    CONCEPT_POTENTIAL_MAGNITUDE,
    CONCEPT_REPEAT_MARKER,
    CONCEPT_SAMPLE_NAME,
    CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER,
    CONCEPT_SAMPLE_PREPARATION,
    CONCEPT_STEP_NUMBER,
    CONCEPT_UNKNOWN_TOKEN,
    DETERMINISM_NORMALIZED,
    DETERMINISM_READ,
    SCOPE_MEASUREMENT,
    SOURCE_TYPE_UNKNOWN,
    ReaderResult,
)
from .inventory import SourceRecord
from .profiles import (
    DEFAULT_PROFILE_ID,
    RECOGNIZER_ACQUISITION_METHOD,
    RECOGNIZER_BARE_INTEGER,
    RECOGNIZER_CYCLING,
    RECOGNIZER_FILTER,
    RECOGNIZER_FLOW_RATE,
    RECOGNIZER_GAS,
    RECOGNIZER_LOADING,
    RECOGNIZER_MEDIUM,
    RECOGNIZER_PH,
    RECOGNIZER_POTENTIAL,
    RECOGNIZER_PREPARATION,
    RECOGNIZER_SAMPLE_NAME,
    RECOGNIZER_STATE,
    RECOGNIZER_STEP,
    NamingProfile,
    profile_for,
)

PARSER_ID = "bl15_filename_tokens_v1"

#: Longest stem this reader will split. A bound rather than a truncation: over
#: it the reader refuses whole. The measured corpus's longest stem is 54
#: characters; a thousand is four orders of magnitude of headroom and still
#: bounds a crafted name.
MAX_STEM_CHARS = 1_024
#: Most ``_``-separated tokens one stem may carry. Measured maximum is 8.
MAX_TOKENS = 128


# --- named normalisation rules ----------------------------------------------
#
# EVERY rule a reading can cite lives here, as a constant, because
# `SourceEvidence.__post_init__` refuses a normalisation with no named rule and
# a rule invented at the call site is indistinguishable from a guess. Each name
# carries its version so a changed rule is a changed name.

RULE_MILLIVOLT_TO_VOLT = (
    "bl15.filenames.millivolt_to_volt.v1: a token of the form <digits>mV states "
    "a potential magnitude in millivolts; the magnitude is reported in volts as "
    "digits/1000. The unit suffix is matched case-insensitively (the MERGE "
    "products write `1600mv`). NO reference basis is implied — a filename does "
    "not state one."
)
RULE_P_DECIMAL_VOLT = (
    "bl15.filenames.p_decimal_volt.v1: in this scientist's filenames `p` stands "
    "in for a decimal point where a `.` would break the name, so `1p2V` states "
    "1.2 V. Warranted by the corpus carrying `1p2V`/`1p5V`/`1p6V`/`1p8V` "
    "alongside `1200mV`/`1500mV`/`1600mV`/`1800mV` for the same measurements."
)
RULE_BARE_VOLT = (
    "bl15.filenames.bare_volt.v1: a token of the form <digits>V states a "
    "potential magnitude already in volts. UNEXERCISED by the measured corpus, "
    "which always writes either `<digits>mV` or the `p`-decimal form."
)
RULE_FILTER_COUNT = (
    "bl15.filenames.filter_count.v1: `filter<n>`, `f<n>` and `Filter<n>` all "
    "state the same filter number; the short `f<n>` form is what the MERGE "
    "products use for the same measurement the acquisition spells `filter<n>`. "
    "Matched case-insensitively."
)
RULE_FILTER_DOUBLED_PREFIX = (
    "bl15.filenames.filter_doubled_prefix.v1: `ffilter<n>` is read as filter "
    "<n>. The corpus contains exactly one instance "
    "(`46_04_JK2_base_after1500Cycling_ffilter35_newSpots_1600mV`) and the "
    "surrounding family writes `filter35`, so this is a PROBABLE DOUBLED-PREFIX "
    "TYPO. The literal is preserved verbatim and is never rewritten; a "
    "scientist who disagrees can see exactly what the file says."
)
RULE_LOADING_NM = (
    "bl15.filenames.loading_nanometres.v1: `<number>nm` states a nominal "
    "thickness in nanometres, with `p` read as a decimal point (`0p5nm` -> 0.5)."
)
RULE_LOADING_WEIGHT_PERCENT = (
    "bl15.filenames.loading_weight_percent.v1: `<number>wpc` and "
    "`<number>wtpc` both state a loading in weight percent, with `p` read as a "
    "decimal point. Warranted by the corpus writing `IrO2_0p2wpc_...` and "
    "`..._0p2wtpc` and `IrO2_5wpc_pellet_...` / `IrO2_5wtpc_pellet_...` for the "
    "same pellets."
)
RULE_STEP_INDEX = (
    "bl15.filenames.step_index.v1: `step<digits>` states a zero-padded "
    "electrochemical step index; the zero padding is dropped and the index "
    "reported as an integer. The convention the project owner supplied does not "
    "mention a step field at all — it is read because the corpus has it."
)
RULE_CYCLING_CASE_FOLD = (
    "bl15.filenames.cycling_state_case_fold.v1: a `before...Cycling` / "
    "`after...Cycling` / `after...CV` token is reported case-folded so "
    "`after1400Cycling` and `after1400cycling` read alike. THE EMBEDDED "
    "MAGNITUDE IS NOT INTERPRETED: `after1200mVCycling` states millivolts, "
    "`after1stCycling` states an ordinal, and the bare `after1500Cycling` could "
    "be either. Deciding between them is a domain question "
    "(`docs/bl15-2-domain-questions-2026-09-16.md`), not a normalisation."
)
RULE_BEFORE_AFTER = (
    "bl15.filenames.before_after_state.v1: the leading `before`/`after` of a "
    "cycling token states, on its own, which side of the treatment the "
    "measurement sits on. Reported as a SEPARATE statement from the cycling "
    "token because it is the half of the token a mapping can use without "
    "resolving the magnitude ambiguity above."
)
RULE_ALIAS_FOLD = (
    "bl15.filenames.case_insensitive_alias.v1: the token matched a profile alias "
    "only after folding case (the corpus writes `asIs` and `AsIs`, "
    "`noElectrolyte` and `NoElectrolyte`). Folding case is a normalisation and "
    "is recorded as one; the literal is preserved."
)
RULE_ALIAS_EXACT = (
    "bl15.filenames.profile_alias.v1: the token is a literal declared in this "
    "profile's alias table, read to the canonical form the table gives it. The "
    "table is measured from one archive and is versioned with the profile."
)
RULE_ELECTROLYTE_NEGATION = (
    "bl15.filenames.electrolyte_negation.v1: `NoElectrolyte` states the ABSENCE "
    "of an electrolyte and is read as `none`. This is a reading of a negation, "
    "not an inference about what the cell contained instead."
)
RULE_SAMPLE_CODE_SHAPE = (
    "bl15.filenames.sample_code_shape.v1: a token of uppercase letters followed "
    "by digits and an optional trailing letter is this scientist's sample code "
    "(`JK1`, `JK1C`). Read AS ITSELF — no expansion, no material identity, no "
    "link to any other sample. Checked against every token in the measured "
    "corpus: it matches those codes and nothing else."
)
RULE_BARE_INTEGER_ORDINAL = (
    "bl15.filenames.bare_integer_ordinal.v1: THE ONLY ORDERING RULE IN THIS "
    "READER. The convention states the run number leads and the "
    "sample/electrode number follows it, so the FIRST bare-integer token of a "
    "stem is the legacy run/file number and the SECOND is the "
    "sample/electrode number. This is an ordinal among the numeric tokens, not "
    "a token position: `01_IrO2_oldPellet_f35` has one and gets a legacy number "
    "only. A THIRD bare integer is NOT assigned a role — the MERGE product "
    "`43_44_04_JK2_...` carries three, and which of `43`/`44` is 'the' legacy "
    "number is a question about a processed artifact that only a scientist can "
    "answer — so the third and later are reported as unknown tokens. "
    "WHAT THE SECOND TOKEN MEANS IS NOT ESTABLISHED, AND READING IT IS NOT A "
    "CLAIM THAT IT IS. The grouping it implies is contiguous and "
    "non-overlapping over the measured archive and it agrees with the beamtime "
    "notes' own `Sample N` sections — but agreement is not confirmation: a "
    "token meaning something else could produce contiguous ranges just as "
    "easily. `bl15.mapping` marks `sample_or_electrode_number` "
    "`needs_domain_review` for exactly this reason, and it is the first "
    "question in the domain packet. This reader reports a recognised CONCEPT, "
    "never an established fact."
)
RULE_PH_VALUE = (
    "bl15.filenames.ph_value.v1: `pH<number>` states a pH, with `p` inside the "
    "number read as a decimal point. UNEXERCISED by the measured corpus's "
    "filenames — the convention names a pH field and the beamtime notes state "
    "`pH = 13` in prose, but no filename in this archive carries one."
)
RULE_FLOW_RATE_VALUE = (
    "bl15.filenames.flow_rate.v1: `<number>sccm` / `<number>mLmin` / "
    "`<number>uLmin` state a flow rate, with `p` read as a decimal point. "
    "UNEXERCISED by the measured corpus's filenames — the notes state "
    "`Flow cell = 10 ml/min` in prose, but no filename in this archive carries "
    "one."
)
#: An unrecognised token carries NO rule, on purpose: it is reported verbatim
#: with ``determinism=read`` and ``normalized_value=None``, because nothing was
#: normalised. A rule string there would assert a reading that did not happen.
#:
#: Every rule this module can cite. A test asserts every emitted
#: ``normalization_rule`` is one of these, so a rule cannot be invented inline.
NORMALIZATION_RULES: frozenset[str] = frozenset(
    {
        RULE_MILLIVOLT_TO_VOLT,
        RULE_P_DECIMAL_VOLT,
        RULE_BARE_VOLT,
        RULE_FILTER_COUNT,
        RULE_FILTER_DOUBLED_PREFIX,
        RULE_LOADING_NM,
        RULE_LOADING_WEIGHT_PERCENT,
        RULE_STEP_INDEX,
        RULE_CYCLING_CASE_FOLD,
        RULE_BEFORE_AFTER,
        RULE_ALIAS_FOLD,
        RULE_ALIAS_EXACT,
        RULE_ELECTROLYTE_NEGATION,
        RULE_SAMPLE_CODE_SHAPE,
        RULE_BARE_INTEGER_ORDINAL,
        RULE_PH_VALUE,
        RULE_FLOW_RATE_VALUE,
    }
)


# --- what one recognizer answers --------------------------------------------


@dataclass(frozen=True)
class TokenReading:
    """One recognizer's answer about one token.

    :attr:`companions` carries the statements a token supports BESIDES its
    primary one — ``beforeCycling`` states both a cycling state and, separately,
    that the measurement is on the "before" side. They are separate statements
    at the same locator because a mapping can use the second without resolving
    the first's ambiguity.
    """

    concept: str
    determinism: str = DETERMINISM_READ
    normalized_value: Any = None
    unit: str | None = None
    normalization_rule: str | None = None
    companions: tuple["TokenReading", ...] = ()


@dataclass
class _ScanState:
    """Carried across the tokens of ONE stem. Holds no cross-file state."""

    bare_integers_seen: int = 0


Recognizer = Callable[[str, NamingProfile, _ScanState], TokenReading | None]


# --- helpers ----------------------------------------------------------------

_P_DECIMAL = re.compile(r"^(\d+)p(\d+)$")


def _p_number(text: str) -> float | int | None:
    """``0p5`` -> 0.5, ``5`` -> 5. ``None`` when it is not a number at all."""
    match = _P_DECIMAL.match(text)
    if match:
        return float(f"{match.group(1)}.{match.group(2)}")
    if text.isdigit():
        return int(text)
    return None


def _alias_reading(
    profile: NamingProfile,
    table: str,
    token: str,
    concept: str,
    *,
    extra_rule: str | None = None,
) -> TokenReading | None:
    canonical = profile.alias(table, token)
    if canonical is None:
        return None
    exact = any(
        literal == token for literal in profile.alias_literals(table)
    )
    rule = RULE_ALIAS_EXACT if exact else RULE_ALIAS_FOLD
    if extra_rule:
        rule = f"{rule} | {extra_rule}"
    return TokenReading(
        concept=concept,
        determinism=DETERMINISM_NORMALIZED,
        normalized_value=canonical,
        normalization_rule=rule,
    )


# --- the recognizers --------------------------------------------------------
#
# Each takes a token, the profile and the per-stem state, and returns a reading
# or None. None means "not mine" — never "malformed": a token no recognizer
# claims becomes CONCEPT_UNKNOWN_TOKEN and survives.

#: Which concept a profile's ``state_aliases`` canonical reading belongs to.
#: The profile owns the LITERALS (one scientist's words); the reader owns the
#: CONCEPTS (this package's vocabulary), so a second profile can spell
#: "new spot" differently without redefining what a new spot is.
_STATE_CONCEPTS: dict[str, str] = {
    "new_spot": CONCEPT_NEW_SPOT,
    # `newGrid` is a fresh TEM grid rather than a fresh spot on one grid. Both
    # state "a fresh physical location was used", which is what `new_spot`
    # means here; the distinction between them survives in `normalized_value`
    # (`new_grid` vs `new_spot`) rather than being flattened away.
    "new_grid": CONCEPT_NEW_SPOT,
    "repeat": CONCEPT_REPEAT_MARKER,
    # `ave` marks a multi-scan average, which is a statement about repeats.
    "averaged": CONCEPT_REPEAT_MARKER,
    "dry": CONCEPT_DRY_STATE,
    # `asIs` states the sample was measured in its received condition. It is a
    # before/after statement and NOT read as "not cycled" — that equivalence is
    # a domain question.
    "as_is": CONCEPT_BEFORE_AFTER_STATE,
}


def _recognize_medium(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    canonical = profile.alias("medium", token)
    if canonical is None:
        return None
    extra = RULE_ELECTROLYTE_NEGATION if canonical == "none" else None
    return _alias_reading(
        profile, "medium", token, CONCEPT_ELECTROLYTE_OR_MEDIUM, extra_rule=extra
    )


def _recognize_state(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    canonical = profile.alias("state", token)
    if canonical is None:
        return None
    concept = _STATE_CONCEPTS.get(canonical)
    if concept is None:  # pragma: no cover - guarded by a profile parity test
        return None
    return _alias_reading(profile, "state", token, concept)


def _recognize_acquisition_method(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    if profile.alias("acquisition_method", token) is None:
        return None
    return _alias_reading(
        profile, "acquisition_method", token, CONCEPT_ACQUISITION_METHOD
    )


def _recognize_preparation(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    if profile.alias("preparation", token) is None:
        return None
    return _alias_reading(
        profile, "preparation", token, CONCEPT_SAMPLE_PREPARATION
    )


def _recognize_gas(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    if profile.alias("gas", token) is None:
        return None
    return _alias_reading(profile, "gas", token, CONCEPT_GAS_CONDITION)


_CYCLING = re.compile(r"^(before|after)(.*?)(cycling|cv)$", re.IGNORECASE)


def _recognize_cycling(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    match = _CYCLING.match(token)
    if not match:
        return None
    side = match.group(1).casefold()
    return TokenReading(
        concept=CONCEPT_CYCLING_STATE,
        determinism=DETERMINISM_NORMALIZED,
        normalized_value=token.casefold(),
        normalization_rule=RULE_CYCLING_CASE_FOLD,
        companions=(
            TokenReading(
                concept=CONCEPT_BEFORE_AFTER_STATE,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=side,
                normalization_rule=RULE_BEFORE_AFTER,
            ),
        ),
    )


_MILLIVOLT = re.compile(r"^(\d+)mv$", re.IGNORECASE)
_P_VOLT = re.compile(r"^(\d+)p(\d+)v$", re.IGNORECASE)
_BARE_VOLT = re.compile(r"^(\d+)v$", re.IGNORECASE)


def _recognize_potential(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    match = _MILLIVOLT.match(token)
    if match:
        return TokenReading(
            concept=CONCEPT_POTENTIAL_MAGNITUDE,
            determinism=DETERMINISM_NORMALIZED,
            normalized_value=int(match.group(1)) / 1000,
            unit="V",
            normalization_rule=RULE_MILLIVOLT_TO_VOLT,
        )
    match = _P_VOLT.match(token)
    if match:
        return TokenReading(
            concept=CONCEPT_POTENTIAL_MAGNITUDE,
            determinism=DETERMINISM_NORMALIZED,
            normalized_value=float(f"{match.group(1)}.{match.group(2)}"),
            unit="V",
            normalization_rule=RULE_P_DECIMAL_VOLT,
        )
    match = _BARE_VOLT.match(token)
    if match:
        return TokenReading(
            concept=CONCEPT_POTENTIAL_MAGNITUDE,
            determinism=DETERMINISM_NORMALIZED,
            normalized_value=int(match.group(1)),
            unit="V",
            normalization_rule=RULE_BARE_VOLT,
        )
    return None


_FILTER = re.compile(r"^(ffilter|filter|f)(\d+)$", re.IGNORECASE)


def _recognize_filter(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    match = _FILTER.match(token)
    if not match:
        return None
    doubled = match.group(1).casefold() == "ffilter"
    return TokenReading(
        concept=CONCEPT_FILTER,
        determinism=DETERMINISM_NORMALIZED,
        normalized_value=int(match.group(2)),
        normalization_rule=(
            RULE_FILTER_DOUBLED_PREFIX if doubled else RULE_FILTER_COUNT
        ),
    )


_LOADING = re.compile(r"^(\d+(?:p\d+)?)(nm|wtpc|wpc)$", re.IGNORECASE)


def _recognize_loading(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    match = _LOADING.match(token)
    if not match:
        return None
    value = _p_number(match.group(1))
    if value is None:  # pragma: no cover - the pattern guarantees a number
        return None
    suffix = match.group(2).casefold()
    if suffix == "nm":
        return TokenReading(
            concept=CONCEPT_LOADING_OR_THICKNESS,
            determinism=DETERMINISM_NORMALIZED,
            normalized_value=value,
            unit="nm",
            normalization_rule=RULE_LOADING_NM,
        )
    return TokenReading(
        concept=CONCEPT_LOADING_OR_THICKNESS,
        determinism=DETERMINISM_NORMALIZED,
        normalized_value=value,
        unit="wt%",
        normalization_rule=RULE_LOADING_WEIGHT_PERCENT,
    )


_STEP = re.compile(r"^step(\d+)$", re.IGNORECASE)


def _recognize_step(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    match = _STEP.match(token)
    if not match:
        return None
    return TokenReading(
        concept=CONCEPT_STEP_NUMBER,
        determinism=DETERMINISM_NORMALIZED,
        normalized_value=int(match.group(1)),
        normalization_rule=RULE_STEP_INDEX,
    )


_PH = re.compile(r"^ph(\d+(?:p\d+)?)$", re.IGNORECASE)


def _recognize_ph(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    match = _PH.match(token)
    if not match:
        return None
    value = _p_number(match.group(1))
    if value is None:  # pragma: no cover - the pattern guarantees a number
        return None
    return TokenReading(
        concept=CONCEPT_PH,
        determinism=DETERMINISM_NORMALIZED,
        normalized_value=value,
        normalization_rule=RULE_PH_VALUE,
    )


_FLOW = re.compile(
    r"^(\d+(?:p\d+)?)(sccm|mlmin|ulmin|mlpermin)$", re.IGNORECASE
)
#: What each flow suffix is reported in. `sccm` is already a unit; `mLmin` and
#: `uLmin` are the scientist's compressions of `mL/min` and `uL/min`.
_FLOW_UNITS = {
    "sccm": "sccm",
    "mlmin": "mL/min",
    "mlpermin": "mL/min",
    "ulmin": "uL/min",
}


def _recognize_flow_rate(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    match = _FLOW.match(token)
    if not match:
        return None
    value = _p_number(match.group(1))
    if value is None:  # pragma: no cover - the pattern guarantees a number
        return None
    return TokenReading(
        concept=CONCEPT_FLOW_RATE,
        determinism=DETERMINISM_NORMALIZED,
        normalized_value=value,
        unit=_FLOW_UNITS[match.group(2).casefold()],
        normalization_rule=RULE_FLOW_RATE_VALUE,
    )


def _recognize_sample_name(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    if profile.alias("sample_name", token) is not None:
        return _alias_reading(profile, "sample_name", token, CONCEPT_SAMPLE_NAME)
    if profile.sample_code_pattern and re.match(
        profile.sample_code_pattern, token
    ):
        return TokenReading(
            concept=CONCEPT_SAMPLE_NAME,
            determinism=DETERMINISM_NORMALIZED,
            normalized_value=token,
            normalization_rule=RULE_SAMPLE_CODE_SHAPE,
        )
    return None


def _recognize_bare_integer(
    token: str, profile: NamingProfile, state: _ScanState
) -> TokenReading | None:
    if not token.isdigit():
        return None
    state.bare_integers_seen += 1
    if state.bare_integers_seen == 1:
        concept = CONCEPT_LEGACY_NUMBER
    elif state.bare_integers_seen == 2:
        concept = CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER
    else:
        # A third bare integer gets no role. `43_44_04_JK2_...` in MERGE carries
        # three, and choosing between `43` and `44` is a scientific question
        # about a processed artifact.
        return TokenReading(
            concept=CONCEPT_UNKNOWN_TOKEN,
            determinism=DETERMINISM_NORMALIZED,
            normalized_value=None,
            normalization_rule=RULE_BARE_INTEGER_ORDINAL,
        )
    return TokenReading(
        concept=concept,
        determinism=DETERMINISM_NORMALIZED,
        normalized_value=int(token),
        normalization_rule=RULE_BARE_INTEGER_ORDINAL,
    )


_RECOGNIZERS: dict[str, Recognizer] = {
    RECOGNIZER_MEDIUM: _recognize_medium,
    RECOGNIZER_STATE: _recognize_state,
    RECOGNIZER_ACQUISITION_METHOD: _recognize_acquisition_method,
    RECOGNIZER_PREPARATION: _recognize_preparation,
    RECOGNIZER_GAS: _recognize_gas,
    RECOGNIZER_CYCLING: _recognize_cycling,
    RECOGNIZER_POTENTIAL: _recognize_potential,
    RECOGNIZER_FILTER: _recognize_filter,
    RECOGNIZER_LOADING: _recognize_loading,
    RECOGNIZER_STEP: _recognize_step,
    RECOGNIZER_PH: _recognize_ph,
    RECOGNIZER_FLOW_RATE: _recognize_flow_rate,
    RECOGNIZER_SAMPLE_NAME: _recognize_sample_name,
    RECOGNIZER_BARE_INTEGER: _recognize_bare_integer,
}


# --- the reader -------------------------------------------------------------


def stem_of(basename: str) -> str:
    """The measurement stem a basename names.

    Drops ONE trailing extension and, for a scan export, the ``_NNN`` scan
    index. Nothing else: the ``_dir`` suffix of a scan DIRECTORY is not a
    filename and is :mod:`bl15.relate`'s problem, and ``run29.mac.mac`` keeps
    one of its two ``.mac`` suffixes because dropping both would fuse it with
    ``run29.mac``, a DIFFERENT file with different content (measured: 4,013 and
    4,059 bytes).
    """
    stem = basename
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    return stem


def read_filename(
    record: SourceRecord,
    *,
    profile_id: str = DEFAULT_PROFILE_ID,
    source_type: str | None = None,
    stem: str | None = None,
    id_prefix: str = "",
) -> ReaderResult:
    """Read every token of one measurement stem. Never raises.

    ``stem`` overrides the stem derived from :attr:`SourceRecord.basename`, which
    is how the SPEC reader's internal ``#F`` declaration and a macro's
    ``newfile`` target get read by the same recognizers as an external filename
    — the conflict between them is only visible if both are read the same way.
    """
    resolved_type = source_type or SOURCE_TYPE_UNKNOWN
    profile = profile_for(profile_id)
    if profile is None:
        return refusal(
            source_path=record.archive_path,
            parser_id=PARSER_ID,
            reason=(
                f"unknown_naming_profile: {profile_id!r} is not a registered "
                f"profile, so no token could be read under a named convention"
            ),
        )

    text = stem if stem is not None else stem_of(record.basename)
    if len(text) > MAX_STEM_CHARS:
        # Its own wording rather than `_emit.oversize_reason`, which counts
        # BYTES. A stem ceiling is in CHARACTERS, and a refusal that reported
        # the wrong unit would be a small lie in the one sentence a scientist
        # reads about why nothing was read.
        return refusal(
            source_path=record.archive_path,
            parser_id=PARSER_ID,
            reason=(
                f"source_too_large: this stem is {len(text)} characters, above "
                f"the ceiling of {MAX_STEM_CHARS}; no token was read, so no "
                f"partial reading is reported as whole"
            ),
        )

    builder = EvidenceBuilder(
        source_path=record.archive_path,
        source_type=resolved_type,
        parser_id=PARSER_ID,
        id_prefix=id_prefix,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
    )

    if not text:
        builder.skip(
            reason="empty_stem",
            locator="filename",
            detail="the basename carries no stem to split",
        )
        return builder.result()

    recognizers = tuple(
        _RECOGNIZERS[name]
        for name in profile.token_recognizers
        if name in _RECOGNIZERS
    )
    state = _ScanState()

    cursor = 0
    tokens = text.split("_")
    for index, token in enumerate(tokens):
        start = cursor
        cursor += len(token) + 1  # the separator that followed it
        if index >= MAX_TOKENS:
            builder.skip(
                reason="too_many_tokens",
                locator=f"filename token {index}",
                detail=(
                    f"the stem splits into {len(tokens)} tokens, above the "
                    f"ceiling of {MAX_TOKENS}; tokens from index {MAX_TOKENS} "
                    f"were not read"
                ),
                token_count=len(tokens),
                ceiling=MAX_TOKENS,
            )
            break
        locator = f"filename token {index} [chars {start}..{start + len(token)}]"
        if token == "":
            # A doubled separator. Reported rather than dropped: it changes the
            # token indices a scientist would count by eye.
            builder.skip(
                reason="empty_token",
                locator=locator,
                detail="two consecutive `_` separators produced an empty token",
            )
            continue

        reading = None
        for recognize in recognizers:
            reading = recognize(token, profile, state)
            if reading is not None:
                break
        if reading is None:
            reading = TokenReading(
                concept=CONCEPT_UNKNOWN_TOKEN,
                determinism=DETERMINISM_READ,
                normalization_rule=None,
            )

        for item in (reading,) + reading.companions:
            builder.add(
                locator=locator,
                raw_literal=token,
                concept=item.concept,
                determinism=item.determinism,
                scope=SCOPE_MEASUREMENT,
                normalized_value=item.normalized_value,
                unit=item.unit,
                normalization_rule=item.normalization_rule,
                measurement_stem=text,
            )

    return builder.result()
