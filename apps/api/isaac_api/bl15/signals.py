"""The per-Run HERFD primary-signal selector — evidence-based, deterministic, reviewable.

WHY THIS EXISTS
===============

Domain question ``Q11`` asked which ``.dat`` column is the HERFD signal. On
**2026-09-22 the domain owner (Angel) answered it, relayed by the project owner**, and
the answer is not one column name — it is a rule that depends on the Run:

* ``vortDT`` is GENERALLY the Vortex channel used for HERFD;
* in dual-element measurements ``vortDT`` and ``vortDT2`` may correspond to DIFFERENT
  elements;
* one can be empty while the other carries live signal;
* which one is the primary signal depends on which element/edge the Run measures.

So this module does not pick a column. It reads what each candidate channel actually
carries in each Run, states which elements the Run's sources establish, and applies a
fixed decision table. **It suggests; it never writes.** A suggestion is labelled
non-authoritative on the wire, and nothing here reaches a record field — the official
``measurement.series[].channels[]`` block needs values this build does not carry (``Q12``
forbids expanding the scan grid), so the selection is shown for review and, when a
scientist confirms it, becomes a *convention rule* (:mod:`isaac_api.convention_rules`)
rather than a value.

"GENERALLY ``vortDT``" IS RECORDED AND IS NOT A TIE-BREAKER
===========================================================

It would be easy to turn Angel's first clause into a default — "when unsure, pick
``vortDT``". That would be a hard-coded source hierarchy of exactly the kind his
2026-09-22 answer on conflicts rejects, and it would be wrong precisely in the
dual-element case he named. So the sentence is carried in
:attr:`AcquisitionSystemKnowledge.domain_note` for a reviewer to read, and the decision
table never consults it.

THE LIVENESS THRESHOLDS ARE MEASURED, NOT PICKED
================================================

Measured 2026-09-22 over the real BL15-2 archive, locally, by reading every ``.dat``'s
data rows (904 scans with data, 92 measurement units with scans). Aggregates only — no
count value, energy or note prose is reproduced here or anywhere in the repository:

* ``vortDT3``, ``vortDT4``, ``vort`` and ``vort2`` are **all-zero in all 837 scans**
  that carry them.
* Per unit, ``vortDT2``'s share of the Vortex counts is **at most 0.0397** (every one of
  92 units), and ``vortDT``'s is **at least 0.9603**. Nothing falls in between.
* A Poisson edge-step significance (last-decile mean against first-decile mean, in
  standard deviations) of **>= 5** appears in at least half of the scans of **every
  sample-measurement unit's** ``vortDT`` (the only unit below one half is ``alignment``,
  at 0.200), and in **no scan at all** of any sample unit's ``vortDT2``. The one unit
  whose ``vortDT2`` shows an edge in more than zero scans is a TRANSMISSION reference
  pellet, where the channel carries 0.03% of the counts.

The three defaults below sit in those measured gaps, each with its basis stated in
:data:`THRESHOLD_BASIS`, and :class:`SelectorThresholds` makes them a reviewable,
replaceable input rather than constants buried in the table.

WHAT IS DELIBERATELY NOT USED
=============================

**The energy window.** Checking that a scan's energy range brackets the established
edge would need an edge-energy reference, which this build does not carry, and the
alternative — comparing against the method macro's grid literal — is interpreting that
literal, which ``Q12`` forbids. So the selector abstains from it and says so in every
result (:data:`EVIDENCE_NOT_USED`), rather than using a number it has no warrant for.

Pure data and pure functions. No I/O, no clock, no environment read. A scan's TEXT is
handed in by :mod:`isaac_api.historical_import`, which already holds it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .evidence import MAX_DATA_ROWS

__all__ = [
    "AcquisitionSystemKnowledge",
    "BL152_VORTEX",
    "ChannelAssignment",
    "ChannelSummary",
    "DEFAULT_THRESHOLDS",
    "ElementEvidence",
    "EVIDENCE_NOT_USED",
    "SELECTOR_ID",
    "ScanChannelStats",
    "SelectorThresholds",
    "SignalSelection",
    "THRESHOLD_BASIS",
    "element_evidence_from_method_symbol",
    "scan_channel_stats",
    "select_primary_signal",
    "summarize_channels",
]

#: Versioned. A change to the decision table or to what a threshold means is a new id,
#: so a selection recorded last month can be told apart from one made under a revised
#: rule.
SELECTOR_ID = "bl15.signals.herfd_primary_signal_selector.v1"

# --- status vocabulary -------------------------------------------------------

#: Exactly one channel carries live signal, every other candidate is empty, and the
#: Run's sources establish exactly one element. A SUGGESTION — non-authoritative.
STATUS_PROPOSED = "proposed"
#: The evidence does not support a single answer. The reason code says why.
STATUS_UNRESOLVED = "unresolved"
#: A scientist-confirmed signal-assignment rule applies to this Run and the channels
#: it names carry signal here. Authoritative FOR THIS IMPORT'S SEMANTICS ONLY — it
#: writes no record field.
STATUS_CONFIRMED = "confirmed"
#: A confirmed rule applies but this Run's own channel contents contradict it (the
#: assigned channel is empty here). Shown for review; the rule is not applied silently.
STATUS_NEEDS_REVIEW = "needs_review"

SELECTION_STATUSES: frozenset[str] = frozenset(
    {STATUS_PROPOSED, STATUS_UNRESOLVED, STATUS_CONFIRMED, STATUS_NEEDS_REVIEW}
)

AUTHORITY_NON_AUTHORITATIVE = "non_authoritative_suggestion"
AUTHORITY_CONFIRMED = "scientist_confirmed"

REASON_SINGLE_LIVE_CHANNEL = "single_live_channel_and_established_element"
REASON_NO_CANDIDATE_CHANNEL = "no_candidate_channel"
REASON_NO_LIVE_CHANNEL = "no_live_channel"
REASON_MULTIPLE_LIVE_CHANNELS = "multiple_live_channels"
REASON_AMBIGUOUS_LIVENESS = "channel_liveness_ambiguous"
REASON_ELEMENT_NOT_ESTABLISHED = "target_element_not_established"
REASON_CONFLICTING_ELEMENTS = "conflicting_element_evidence"
REASON_CONFIRMED_RULE = "confirmed_signal_assignment_rule"
REASON_RULE_CONTRADICTED = "confirmed_rule_contradicted_by_channel_contents"

#: Channel classifications.
LIVENESS_LIVE = "live"
LIVENESS_EMPTY = "empty"
LIVENESS_AMBIGUOUS = "ambiguous"
LIVENESS_ABSENT = "absent"

#: What the selector deliberately does not consult, stated in every result.
EVIDENCE_NOT_USED: tuple[str, ...] = (
    "energy_window: checking a scan's energy range against the established edge "
    "would need an edge-energy reference this build does not carry, and reading the "
    "method macro's grid literal for it would interpret that literal, which Q12 "
    "forbids. Not used.",
    "the domain owner's 'vortDT is generally the HERFD channel': recorded for the "
    "reviewer and never used as a tie-breaker, because a default channel is a "
    "hard-coded hierarchy and is wrong in exactly the dual-element case.",
)


# --- acquisition-system knowledge -------------------------------------------


@dataclass(frozen=True)
class AcquisitionSystemKnowledge:
    """What this build knows about ONE acquisition system's detector channels.

    **FACILITY/INSTRUMENT KNOWLEDGE, NOT A SCIENTIST'S HABIT AND NOT A FILENAME
    CONVENTION.** It sits at the ``acquisition_system`` level of the applicability
    hierarchy (:mod:`bl15.applicability`), beside — never inside — a naming profile: a
    filename convention says what a token MEANS, and this says which columns of a scan
    export are candidates for the fluorescence signal. A person who ran a Run is
    provenance and appears in neither.
    """

    system_id: str
    display_name: str
    #: The columns that may carry the HERFD signal, in the order a surface lists them.
    #: Order is PRESENTATIONAL ONLY — see this module's docstring.
    candidate_channels: tuple[str, ...]
    basis: str
    #: The domain owner's words, paraphrased and attributed. Read by a reviewer, never
    #: by the decision table.
    domain_note: str

    def to_state(self) -> dict:
        return {
            "system_id": self.system_id,
            "display_name": self.display_name,
            "candidate_channels": list(self.candidate_channels),
            "basis": self.basis,
            "domain_note": self.domain_note,
        }


BL152_VORTEX = AcquisitionSystemKnowledge(
    system_id="ssrl_bl152_spec_vortex_channels",
    display_name="SSRL BL15-2 SPEC scan exports — Vortex fluorescence channels",
    candidate_channels=("vortDT", "vortDT2", "vortDT3", "vortDT4"),
    basis=(
        "The four dead-time-corrected Vortex columns named in the `#L` header of every "
        "measured BL15-2 scan export that carries them. Measured 2026-09-22 over the "
        "real archive: vortDT3 and vortDT4 are all-zero in all 837 scans that carry "
        "them, and they are kept as candidates because the domain owner states that "
        "different Vortex channels may correspond to different elements — a channel "
        "that is empty in this archive is not thereby never the signal."
    ),
    domain_note=(
        "Angel (domain owner), relayed by the project owner 2026-09-22: vortDT is "
        "generally the Vortex channel used for HERFD; in dual-element measurements "
        "vortDT and vortDT2 may correspond to different elements; one can be empty "
        "while the other carries live signal; the choice depends on which element/edge "
        "the Run measures."
    ),
)


# --- thresholds ---------------------------------------------------------------


#: The basis for each default, in the words a reviewer checks it against.
THRESHOLD_BASIS: Mapping[str, str] = {
    "edge_z_min": (
        "A scan counts as showing an absorption edge in a channel when the channel's "
        "last-decile mean exceeds its first-decile mean by at least this many Poisson "
        "standard deviations. At 5, every sample-measurement unit's vortDT shows an "
        "edge in at least half its scans and no sample unit's vortDT2 shows one in any "
        "scan (measured 2026-09-22, 92 units). At 3 a few vortDT2 scans cross; at 10 a "
        "second vortDT unit drops below one half — 5 is the value at which only the "
        "alignment scan and a transmission reference fall outside."
    ),
    "live_edge_fraction_min": (
        "A channel is LIVE only if it shows an edge in at least this fraction of the "
        "Run's scans. Measured: every sample-measurement unit's vortDT is at or above "
        "one half; the only unit below is the alignment scan (0.200)."
    ),
    "empty_share_max": (
        "A channel is EMPTY only if it carries at most this share of the Run's "
        "candidate-channel counts. Measured: vortDT2's per-unit share never exceeds "
        "0.0397 and vortDT's is never below 0.9603, so the smallest round value above "
        "the measured empty maximum sits in a gap no unit falls in."
    ),
}


@dataclass(frozen=True)
class SelectorThresholds:
    """The three liveness thresholds. REVIEWABLE AND REPLACEABLE, never buried.

    A caller may pass different values — for a different beamline, or after a second
    archive shows the gap is narrower — and every result records the thresholds it was
    computed under, so two selections under different thresholds cannot be confused.
    """

    edge_z_min: float = 5.0
    live_edge_fraction_min: float = 0.5
    empty_share_max: float = 0.05
    basis: Mapping[str, str] = field(default_factory=lambda: dict(THRESHOLD_BASIS))

    def __post_init__(self) -> None:
        if not (self.edge_z_min > 0):
            raise ValueError("edge_z_min must be positive")
        if not (0 < self.live_edge_fraction_min <= 1):
            raise ValueError("live_edge_fraction_min must be in (0, 1]")
        if not (0 <= self.empty_share_max < 1):
            raise ValueError("empty_share_max must be in [0, 1)")

    def to_state(self) -> dict:
        return {
            "edge_z_min": self.edge_z_min,
            "live_edge_fraction_min": self.live_edge_fraction_min,
            "empty_share_max": self.empty_share_max,
            "basis": dict(self.basis),
        }


DEFAULT_THRESHOLDS = SelectorThresholds()


# --- per-scan statistics ------------------------------------------------------


@dataclass(frozen=True)
class ChannelScan:
    """One channel in one scan: how much it counted and whether it shows an edge."""

    total: float
    nonzero: int
    edge_z: float


@dataclass(frozen=True)
class ScanChannelStats:
    """What ONE scan export's data rows say about the candidate channels.

    AGGREGATES ONLY. No row value is retained: a total, a count of non-zero rows and an
    edge-step significance per channel are enough to decide liveness, and keeping the
    rows would put a spectrum in a session document.
    """

    scan_path: str
    rows: int
    #: False when the row walk stopped at :data:`~bl15.evidence.MAX_DATA_ROWS`, in which
    #: case every figure is over the rows read and the scan is flagged.
    complete: bool
    channels: Mapping[str, ChannelScan]
    #: Rows that did not parse as numbers and were skipped, so a malformed file cannot
    #: silently shrink a channel's total.
    unparsed_rows: int = 0


_L_LINE = re.compile(r"^#L[ \t]+(.*)$")


def _edge_z(values: Sequence[float]) -> float:
    """Poisson significance of last-decile over first-decile mean. 0.0 when undecidable.

    Undecidable means fewer than six rows (two windows of three) or no counts at all —
    both answer 0.0, which no threshold treats as an edge. A NEGATIVE value (the channel
    falls across the scan) is kept as it is: it is not an edge, and flooring it would
    hide that the channel did something.
    """
    n = len(values)
    k = max(3, n // 10)
    if n < 2 * k:
        return 0.0
    pre = sum(values[:k]) / k
    post = sum(values[-k:]) / k
    variance = (pre + post) / k
    if variance <= 0:
        return 0.0
    return (post - pre) / math.sqrt(variance)


def scan_channel_stats(
    text: str,
    *,
    scan_path: str,
    channels: Sequence[str],
    max_rows: int = MAX_DATA_ROWS,
) -> ScanChannelStats:
    """Per-channel aggregates for one ``.dat``. **Never raises.**

    The column set is read from the LAST ``#L`` line before the data — a ``.dat``
    carries one scan block, measured 908 of 908 — and a candidate channel absent from it
    is simply absent from the result, which the summary reports as ``absent`` rather
    than as ``empty``: "this scan has no such column" and "this column counted nothing"
    are different facts.
    """
    columns: list[str] | None = None
    wanted = tuple(channels)
    series: dict[str, list[float]] = {}
    index: dict[str, int] = {}
    rows = 0
    unparsed = 0
    complete = True
    try:
        lines = text.splitlines()
    except Exception:  # pragma: no cover - str.splitlines does not raise
        lines = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            match = _L_LINE.match(line)
            if match:
                columns = match.group(1).split()
                index = {c: i for i, c in enumerate(columns) if c in wanted}
                series = {c: [] for c in index}
            continue
        if columns is None:
            continue
        if rows >= max_rows:
            complete = False
            continue
        parts = line.split()
        try:
            values = [float(p) for p in parts]
        except ValueError:
            unparsed += 1
            continue
        rows += 1
        for name, position in index.items():
            if position < len(values) and math.isfinite(values[position]):
                series[name].append(values[position])
    out = {
        name: ChannelScan(
            total=float(sum(vals)),
            nonzero=sum(1 for v in vals if v != 0),
            edge_z=_edge_z(vals),
        )
        for name, vals in series.items()
    }
    return ScanChannelStats(
        scan_path=scan_path,
        rows=rows,
        complete=complete,
        channels=out,
        unparsed_rows=unparsed,
    )


# --- per-Run summary -----------------------------------------------------------


@dataclass(frozen=True)
class ChannelSummary:
    """One candidate channel over one Run's scans, with its classification and why."""

    channel: str
    scans_present: int
    scans_with_edge: int
    #: This channel's share of the Run's candidate-channel counts; ``None`` when the
    #: Run's candidate channels counted nothing at all.
    share: float | None
    edge_fraction: float | None
    liveness: str
    reason: str

    def to_state(self) -> dict:
        return {
            "channel": self.channel,
            "scans_present": self.scans_present,
            "scans_with_edge": self.scans_with_edge,
            "share": None if self.share is None else round(self.share, 6),
            "edge_fraction": (
                None if self.edge_fraction is None else round(self.edge_fraction, 6)
            ),
            "liveness": self.liveness,
            "reason": self.reason,
        }


def summarize_channels(
    scans: Sequence[ScanChannelStats],
    *,
    system: AcquisitionSystemKnowledge = BL152_VORTEX,
    thresholds: SelectorThresholds = DEFAULT_THRESHOLDS,
) -> tuple[ChannelSummary, ...]:
    """Classify every candidate channel over a Run's scans. Deterministic.

    ``live`` needs BOTH halves — an edge in enough scans AND more than the empty share —
    and ``empty`` needs BOTH of its halves. Anything else is ``ambiguous``, and that is
    the point: a channel carrying a tiny share and still showing edges (the transmission
    reference in the measured archive) is neither, and a table that forced it into one
    would be deciding what the thresholds were never measured to decide.
    """
    totals = {c: 0.0 for c in system.candidate_channels}
    present = {c: 0 for c in system.candidate_channels}
    edges = {c: 0 for c in system.candidate_channels}
    for scan in scans:
        for channel in system.candidate_channels:
            stats = scan.channels.get(channel)
            if stats is None:
                continue
            present[channel] += 1
            totals[channel] += max(0.0, stats.total)
            if stats.edge_z >= thresholds.edge_z_min:
                edges[channel] += 1
    grand = sum(totals.values())
    out: list[ChannelSummary] = []
    for channel in system.candidate_channels:
        if present[channel] == 0:
            out.append(
                ChannelSummary(
                    channel=channel,
                    scans_present=0,
                    scans_with_edge=0,
                    share=None,
                    edge_fraction=None,
                    liveness=LIVENESS_ABSENT,
                    reason="no scan of this Run carries this column",
                )
            )
            continue
        share = totals[channel] / grand if grand > 0 else None
        fraction = edges[channel] / present[channel]
        live_by_edge = fraction >= thresholds.live_edge_fraction_min
        small = share is None or share <= thresholds.empty_share_max
        if live_by_edge and not small:
            liveness, reason = (
                LIVENESS_LIVE,
                f"shows an edge in {edges[channel]} of {present[channel]} scan(s) and "
                "carries more than the empty share of the Vortex counts",
            )
        elif small and not live_by_edge:
            liveness, reason = (
                LIVENESS_EMPTY,
                f"carries at most the empty share of the Vortex counts and shows an edge "
                f"in only {edges[channel]} of {present[channel]} scan(s)",
            )
        else:
            liveness, reason = (
                LIVENESS_AMBIGUOUS,
                "the channel's share and its edge evidence point different ways "
                f"(edge in {edges[channel]} of {present[channel]} scan(s)), so it is "
                "neither live nor empty under these thresholds",
            )
        out.append(
            ChannelSummary(
                channel=channel,
                scans_present=present[channel],
                scans_with_edge=edges[channel],
                share=share,
                edge_fraction=fraction,
                liveness=liveness,
                reason=reason,
            )
        )
    return tuple(out)


# --- element evidence ----------------------------------------------------------

#: Where an element statement came from. A surface shows the role, and the conflict
#: check below treats every role equally — no role outranks another.
ELEMENT_ROLE_SHARED_README = "shared_readme"
ELEMENT_ROLE_METHOD_MACRO = "method_macro_symbol"
ELEMENT_ROLE_FILENAME = "filename"
ELEMENT_ROLE_BEAMTIME_NOTES = "beamtime_notes"
ELEMENT_ROLE_CONFIRMED_RULE = "confirmed_rule"


@dataclass(frozen=True)
class ElementEvidence:
    """One source's statement of which element (and possibly which edge) a Run measures."""

    element: str
    source_path: str
    locator: str
    role: str
    rule: str
    edge: str | None = None

    def to_state(self) -> dict:
        return {
            "element": self.element,
            "edge": self.edge,
            "source_path": self.source_path,
            "locator": self.locator,
            "role": self.role,
            "rule": self.rule,
        }


#: A method macro named ``<Element><Edge>_<anything>`` — measured: ``def IrL3_xas`` is
#: the archive's only acquisition-method definition. The edge vocabulary is the
#: standard X-ray level notation (K; L1-L3; M1-M5), not an energy table.
_METHOD_SYMBOL = re.compile(r"^([A-Z][a-z]?)(K|L[1-3]|M[1-5])_[A-Za-z0-9_]+$")

RULE_METHOD_SYMBOL_ELEMENT_EDGE = (
    "bl15.signals.method_symbol_names_element_and_edge.v1: at SSRL BL15-2 an "
    "acquisition-method macro is named `<Element><Edge>_<suffix>` (measured: `def "
    "IrL3_xas`, the archive's only method definition), so the symbol is read as naming "
    "the element and the absorption edge. Only the element symbol shape and the "
    "standard level notation are recognised; no energy is looked up and a symbol of any "
    "other shape states nothing."
)
RULE_README_ELEMENT = (
    "bl15.signals.readme_element.v1: the element line the shared readme states for the "
    "whole beamtime, taken as stated."
)


def element_evidence_from_method_symbol(
    symbol: str, *, source_path: str, locator: str
) -> ElementEvidence | None:
    """An element/edge statement from a method macro's ``def`` symbol, or ``None``."""
    match = _METHOD_SYMBOL.match(symbol or "")
    if not match:
        return None
    return ElementEvidence(
        element=match.group(1),
        edge=match.group(2),
        source_path=source_path,
        locator=locator,
        role=ELEMENT_ROLE_METHOD_MACRO,
        rule=RULE_METHOD_SYMBOL_ELEMENT_EDGE,
    )


# --- the selection -------------------------------------------------------------


@dataclass(frozen=True)
class ChannelAssignment:
    """``channel -> element/edge``. Several may coexist in one Run (dual-element)."""

    channel: str
    element: str | None
    edge: str | None
    basis: str

    def to_state(self) -> dict:
        return {
            "channel": self.channel,
            "element": self.element,
            "edge": self.edge,
            "basis": self.basis,
        }


@dataclass(frozen=True)
class SignalSelection:
    """The selector's answer for ONE Run, with everything that decided it."""

    status: str
    reason_code: str
    reason: str
    primary_channel: str | None
    assignments: tuple[ChannelAssignment, ...]
    channels: tuple[ChannelSummary, ...]
    elements: tuple[ElementEvidence, ...]
    thresholds: SelectorThresholds
    authority: str
    rule_ref: str | None = None
    system_id: str = BL152_VORTEX.system_id

    def __post_init__(self) -> None:
        if self.status not in SELECTION_STATUSES:
            raise ValueError(f"unknown selection status {self.status!r}")
        if self.status in {STATUS_UNRESOLVED, STATUS_NEEDS_REVIEW} and self.primary_channel:
            # An unresolved selection carrying a chosen channel would be the selector
            # deciding while saying it had not — the invariant SemanticCandidate keeps
            # for proposed_value and unresolved_reason, kept here for the same reason.
            raise ValueError("an unresolved selection cannot name a primary channel")

    def to_state(self) -> dict:
        return {
            "selector_id": SELECTOR_ID,
            "system_id": self.system_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "primary_channel": self.primary_channel,
            "assignments": [a.to_state() for a in self.assignments],
            "channels": [c.to_state() for c in self.channels],
            "elements": [e.to_state() for e in self.elements],
            "thresholds": self.thresholds.to_state(),
            "authority": self.authority,
            "rule_ref": self.rule_ref,
            "evidence_not_used": list(EVIDENCE_NOT_USED),
            # SAID ON THE WIRE, for the reason every other companion says it: this is
            # the one claim a surface must not get wrong about a selection.
            "writes_a_record_field": False,
        }


def _distinct_elements(elements: Sequence[ElementEvidence]) -> list[str]:
    return sorted({e.element for e in elements})


def _edge_for(element: str, elements: Sequence[ElementEvidence]) -> str | None:
    edges = sorted({e.edge for e in elements if e.element == element and e.edge})
    # ONE edge stated, or none claimed. Two different edges for one element is a
    # disagreement this module reports by claiming neither.
    return edges[0] if len(edges) == 1 else None


def select_primary_signal(
    channels: Sequence[ChannelSummary],
    elements: Sequence[ElementEvidence],
    *,
    confirmed_assignments: Sequence[ChannelAssignment] = (),
    rule_ref: str | None = None,
    thresholds: SelectorThresholds = DEFAULT_THRESHOLDS,
    system: AcquisitionSystemKnowledge = BL152_VORTEX,
) -> SignalSelection:
    """THE DECISION TABLE. Deterministic, and every row names its reason.

    1. A confirmed assignment rule applies -> ``confirmed``, unless a channel it names is
       EMPTY or ABSENT in this Run, in which case ``needs_review`` (the rule is not
       applied over contrary evidence).
    2. No candidate channel present -> unresolved.
    3. Any channel ambiguous -> unresolved.
    4. No live channel -> unresolved.
    5. Two or more live channels -> unresolved (possibly dual-element; needs an explicit
       channel -> element assignment, which only a scientist can confirm).
    6. Exactly one live channel:
       * no element established -> unresolved;
       * two or more distinct elements stated by the Run's sources — including a
         filename naming a different element than the readme -> unresolved;
       * exactly one element -> ``proposed``, NON-AUTHORITATIVE.
    """
    channels = tuple(channels)
    elements = tuple(elements)
    by_name = {c.channel: c for c in channels}

    def result(status, code, sentence, primary=None, assignments=(), authority=AUTHORITY_NON_AUTHORITATIVE, ref=None):
        return SignalSelection(
            status=status,
            reason_code=code,
            reason=sentence,
            primary_channel=primary,
            assignments=tuple(assignments),
            channels=channels,
            elements=elements,
            thresholds=thresholds,
            authority=authority,
            rule_ref=ref,
            system_id=system.system_id,
        )

    if confirmed_assignments:
        contradicted = [
            a.channel
            for a in confirmed_assignments
            if by_name.get(a.channel) is None
            or by_name[a.channel].liveness in {LIVENESS_EMPTY, LIVENESS_ABSENT}
        ]
        if contradicted:
            return result(
                STATUS_NEEDS_REVIEW,
                REASON_RULE_CONTRADICTED,
                "A confirmed signal-assignment rule applies to this Run, and the "
                f"channel(s) it names ({', '.join(sorted(contradicted))}) carry no signal "
                "here. The rule is NOT applied over this Run's own evidence; review it.",
                ref=rule_ref,
            )
        primary = confirmed_assignments[0].channel if len(confirmed_assignments) == 1 else None
        return result(
            STATUS_CONFIRMED,
            REASON_CONFIRMED_RULE,
            "A scientist-confirmed signal-assignment rule applies to this Run within its "
            "recorded scope, and the channel(s) it names carry signal here.",
            primary=primary,
            assignments=confirmed_assignments,
            authority=AUTHORITY_CONFIRMED,
            ref=rule_ref,
        )

    present = [c for c in channels if c.liveness != LIVENESS_ABSENT]
    if not present:
        return result(
            STATUS_UNRESOLVED,
            REASON_NO_CANDIDATE_CHANNEL,
            "No scan of this Run carries any of the candidate HERFD channels "
            f"({', '.join(system.candidate_channels)}), so there is nothing to select from.",
        )
    ambiguous = [c.channel for c in present if c.liveness == LIVENESS_AMBIGUOUS]
    if ambiguous:
        return result(
            STATUS_UNRESOLVED,
            REASON_AMBIGUOUS_LIVENESS,
            f"Channel(s) {', '.join(ambiguous)} are neither clearly live nor clearly "
            "empty under the recorded thresholds, so no channel is suggested.",
        )
    live = [c.channel for c in present if c.liveness == LIVENESS_LIVE]
    if not live:
        return result(
            STATUS_UNRESOLVED,
            REASON_NO_LIVE_CHANNEL,
            "No candidate channel carries live signal in this Run.",
        )
    if len(live) > 1:
        return result(
            STATUS_UNRESOLVED,
            REASON_MULTIPLE_LIVE_CHANNELS,
            f"{len(live)} channels carry live signal ({', '.join(live)}). This may be a "
            "dual-element measurement in which each channel belongs to a different "
            "element; which is which is not established by the sources, so nothing is "
            "suggested. A scientist can confirm an explicit channel-to-element "
            "assignment.",
        )
    distinct = _distinct_elements(elements)
    if not distinct:
        return result(
            STATUS_UNRESOLVED,
            REASON_ELEMENT_NOT_ESTABLISHED,
            f"Exactly one channel ({live[0]}) carries live signal, and no source "
            "establishes which element this Run measures, so the channel is not "
            "assigned to anything.",
        )
    if len(distinct) > 1:
        return result(
            STATUS_UNRESOLVED,
            REASON_CONFLICTING_ELEMENTS,
            f"The sources name more than one element ({', '.join(distinct)}) for this "
            "Run. No source outranks another, so nothing is suggested.",
        )
    element = distinct[0]
    edge = _edge_for(element, elements)
    return result(
        STATUS_PROPOSED,
        REASON_SINGLE_LIVE_CHANNEL,
        f"Exactly one candidate channel ({live[0]}) carries live signal, every other "
        f"candidate is empty or absent, and the Run's sources establish one element "
        f"({element}). SUGGESTED, not decided: a scientist confirms it.",
        primary=live[0],
        assignments=(
            ChannelAssignment(
                channel=live[0],
                element=element,
                edge=edge,
                basis=(
                    "single live channel + single established element "
                    f"({len(elements)} element statement(s))"
                ),
            ),
        ),
    )
