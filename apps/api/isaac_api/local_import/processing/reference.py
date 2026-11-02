"""What a result's calibration step says about its energy reference, and what a named reference would do.
Stdlib only: read by processing (``run._calibration``), by ``bundle decide --decision approve_calibration``
(:mod:`..mutations`) and by ``bundle show processing-result``, from the stored step alone, so a result stored
before these sentences existed is read the same way.

Three rules (all in ``protocol.RULE_VERSIONS_SINCE_PROTOCOL_VERSION``, kept outside every hashed output file):

* :data:`IN_SCAN_MIN_RULE_ID` — an IN-SCAN reference channel is proposed only when its edge is usable (edge step /
  pre-edge noise at least ``calibration.reference_min_edge_snr``) in at least :data:`MIN_IN_SCAN_REFERENCE_SCANS`
  scans. One usable scan among many noisy ones is not a reference: its "edge" can be anywhere (measured on a real
  beamtime: 1 of 16 scans at signal-to-noise 10.5, the others 0.6-3.5, per-scan "edges" 4964.6-4985.5 eV).
* :data:`SHIFT_SIZE_RULE_ID` — an approved shift larger than ``qc.warn_energy_shift_eV`` is applied only when the
  scientist also confirmed its size (``--accept-shift``, matching the shift shown to 0.1 eV). A curve that already
  carries a shift these rules would not apply (approved under an older build) is said as carrying an UNCONFIRMED
  shift (:func:`carried_shift`), and its record is blocked until the scientist confirms or rejects it.
* :data:`STRICTER_ONLY_RULE_ID` — a params file may make the size confirmation (``qc.warn_energy_shift_eV``) and the
  in-scan reference's edge rule (``calibration.reference_min_edge_snr``) STRICTER, never looser: the protocol's value
  is a floor / ceiling (:func:`effective_warn_eV`, :func:`effective_min_snr`) and an override past it is ignored and
  said (:func:`ignored_overrides`).
* :data:`CALIBRANT_RULE_ID` — a calibration on a reference group's OWN edge (its own signal, not a separate foil
  channel) is applied only when the scientist confirms its size with ``--accept-shift``, WHATEVER its size and its
  names. A chemical standard is not an energy calibrant: its edge sits where its chemistry puts it. Measured on a real
  BL4-3 sulfur K-edge beamtime: CoSO4, MoS2 and Na2S2O3 standards were offered as their own calibration, and a truthful
  "S K" would have moved them by -9.6 and +1.2 eV onto elemental sulfur's tabulated edge, erasing the chemical shift
  each was measured to show. A name-based check could not be made safe (``Mo_S2``, ``S_cysteine``, ``Ti_anatase``,
  ``ref_B`` read as pure elements), so names are only a HINT in the sentence (:func:`calibrant_identity`, a closed
  list): ``calibration_proposed`` is true only for a group whose names clearly say one pure element, and even then
  approving needs ``--accept-shift``. An approval recorded without it (before this rule) is not applied to a result
  processed now (said so); a result already approved keeps the curve it has.
* :data:`DEGENERATE_RULE_ID` (r4-a) — a reference scan whose edge step is more than :data:`MAX_PLAUSIBLE_EDGE_SNR` times
  its pre-edge noise is not usable: that noise is about zero (a channel that is constant or not counting), not a
  measured edge. Measured on a real BL15-2 Ir L3 HERFD beamtime: in 7 groups the "usable" reference scans stood at
  1e13-1e14 times their noise, others at the threshold of 10, and their "edges" lay 11205-11233 eV apart.
* :data:`SPREAD_RULE_ID` (r4-a) — usable reference edges that spread over more than ``qc.warn_reference_e0_spread_eV``
  (never more than the protocol's :data:`DEFAULT_MAX_SPREAD_EV`: stricter only) are not PROPOSED (ISAAC does not offer
  them as the calibration, ``calibration_proposed`` false), and an explicit approval is applied only with its size
  confirmed (``--accept-shift``), whatever the size, as a group's own edge is: a real foil drifting between scans stays
  approvable, once the scientist says the reference is what they name. On the same beamtime "2 of 14 scans ... at
  11216.2 eV (spread 6.09 eV)" was proposed and approved, unconfirmed.
* :data:`NEAR_SAMPLE_RULE_ID` (r4-a) — an in-scan reference edge within :data:`NEAR_SAMPLE_EV` of the group's own
  (uncalibrated) sample E0 may be the sample seen through the reference channel: it is said, and an approval is
  applied only with its size confirmed (``--accept-shift``), whatever the size. Measured: a chemical standard's
  "reference edge" lay on its own E0 and -1.2 eV was applied to it with no warning.

The r4-a rules are read from the stored step too: the result's per-scan SNRs and edges, and the two values processing
now writes beside them outside the hashed files (``sample_e0_eV``, ``reference_max_spread_eV``).
"""

from __future__ import annotations

import math
import re
import statistics
from typing import Any, Mapping, Sequence

from .edges import edge_energy

MIN_IN_SCAN_REFERENCE_SCANS = 2
IN_SCAN_MIN_RULE_ID = "isaac.xas.in_scan_reference_min_scans.v0"
SHIFT_SIZE_RULE_ID = "isaac.xas.calibration_shift_size_confirmed.v0"
STRICTER_ONLY_RULE_ID = "isaac.xas.calibration_overrides_stricter_only.v0"
CALIBRANT_RULE_ID = "isaac.xas.own_signal_shift_confirmed.v0"
IN_SCAN = "in_scan_reference_channel"
OWN_SIGNAL = "reference_group_own_signal"
TOO_FEW_FLAG = "reference_edge_in_too_few_scans"
SIZE_NOT_CONFIRMED_FLAG = "calibration_shift_size_not_confirmed"
#: a reference group whose names do not clearly say one pure element: its own edge is not proposed as the calibration
NOT_NAMED_ELEMENT_FLAG = "own_signal_not_named_as_pure_element"
#: an approval of a group's own edge that the scientist did not also confirm with --accept-shift: not applied
CALIBRANT_NOT_CONFIRMED_FLAG = "calibration_own_signal_shift_not_confirmed"
#: r4-a: a reference scan's edge step above this many times its pre-edge noise is a channel with no noise, not an edge
DEGENERATE_RULE_ID = "isaac.xas.reference_noise_not_degenerate.v0"
MAX_PLAUSIBLE_EDGE_SNR = 1e6
DEGENERATE_FLAG = "reference_noise_degenerate"
#: r4-a: usable reference edges that spread over more than the protocol's reference-spread level are not proposed; an
#: approval of them is applied only with --accept-shift
SPREAD_RULE_ID = "isaac.xas.reference_edges_agree.v0"
DEFAULT_MAX_SPREAD_EV = 0.5
SPREAD_FLAG = "reference_edges_disagree"
#: an approval of such a reference that the scientist did not also confirm with --accept-shift: not applied
SPREAD_NOT_CONFIRMED_FLAG = "calibration_reference_spread_not_confirmed"
#: r4-a: an in-scan reference edge this close to the group's own sample E0 may be the sample seen through the channel
NEAR_SAMPLE_RULE_ID = "isaac.xas.reference_not_at_sample_e0.v0"
NEAR_SAMPLE_EV = 0.5
NEAR_SAMPLE_FLAG = "reference_edge_at_sample_e0"
#: an approval of such a reference that the scientist did not also confirm with --accept-shift: not applied
NEAR_SAMPLE_NOT_CONFIRMED_FLAG = "calibration_reference_at_sample_e0_not_confirmed"
CHEMICAL_STANDARD = "A chemical standard is not an energy calibrant: its edge sits where its chemistry puts it"
OWN_SIGNAL_RULE = ("This is the group's own edge, so it is applied as the energy calibration only with --accept-shift, "
                   "whatever its size")

ELEMENTS = frozenset(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr "
    "Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm "
    "Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu".split()
)
#: the protocol's defaults (``protocol.DEFAULT_PARAMS``): used when a stored step does not carry its own value, and the
#: floor of the in-scan SNR rule and the ceiling of the size-confirmation level (:data:`STRICTER_ONLY_RULE_ID`)
DEFAULT_MIN_SNR = 10.0
DEFAULT_WARN_SHIFT_EV = 2.0
DEFAULT_MAX_SHIFT_EV = 25.0
#: a shift within this of the warning level is said to 0.01 eV, so "+2.04" never reads as "+2.0" above 2 eV
NEAR_WARN_EV = 0.1


def _num(value: Any, default: float) -> float:
    try:
        return float(value) if value is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def effective_min_snr(configured: Any, source: str | None = IN_SCAN) -> float:
    """The edge SNR a reference scan needs: the configured value, but never below the protocol's for an IN-SCAN
    reference channel (an override may only make that rule stricter). A reference group's own signal takes the
    configured value as before."""
    v = _num(configured, DEFAULT_MIN_SNR)
    return max(DEFAULT_MIN_SNR, v) if source == IN_SCAN else v


def effective_warn_eV(configured: Any) -> float:
    """The shift above which an approval needs its size confirmed: the configured value, but never above the
    protocol's (an override may only make the confirmation stricter)."""
    return min(DEFAULT_WARN_SHIFT_EV, _num(configured, DEFAULT_WARN_SHIFT_EV))


def exceeds_warn(shift: float, warn_eV: Any = None) -> bool:
    """True when ``shift`` needs its size confirmed: |shift|, as said (0.01 eV), above :func:`effective_warn_eV`."""
    return round(abs(float(shift)), 2) > effective_warn_eV(warn_eV)


def effective_max_spread_eV(configured: Any) -> float:
    """r4-a (:data:`SPREAD_RULE_ID`): how far usable reference edges may spread and still be proposed (beyond it an
    approval needs ``--accept-shift``): the configured
    ``qc.warn_reference_e0_spread_eV``, but never above the protocol's (an override may only make it stricter)."""
    return min(DEFAULT_MAX_SPREAD_EV, _num(configured, DEFAULT_MAX_SPREAD_EV))


def ignored_overrides(params: Mapping) -> list[str]:
    """One sentence per params-file value :data:`STRICTER_ONLY_RULE_ID` ignored (``[]`` when none was)."""
    out = []
    spread = ((params.get("qc") or {}) if isinstance(params, Mapping) else {}).get("warn_reference_e0_spread_eV")
    if spread is not None and _num(spread, DEFAULT_MAX_SPREAD_EV) > DEFAULT_MAX_SPREAD_EV:
        out.append(f"The params file sets qc.warn_reference_e0_spread_eV to {_num(spread, 0):g}, above the protocol's "
                   f"{DEFAULT_MAX_SPREAD_EV:g} eV; it sets the drift warning, but a reference whose usable edges spread "
                   f"over more than {DEFAULT_MAX_SPREAD_EV:g} eV is still not proposed, and approving it still needs "
                   "--accept-shift (an override may only make that rule stricter).")
    snr = ((params.get("calibration") or {}) if isinstance(params, Mapping) else {}).get("reference_min_edge_snr")
    if snr is not None and _num(snr, DEFAULT_MIN_SNR) < DEFAULT_MIN_SNR:
        out.append(f"The params file sets calibration.reference_min_edge_snr to {_num(snr, 0):g}, below the protocol's "
                   f"{DEFAULT_MIN_SNR:g}; an override may only make the in-scan reference rule stricter, so "
                   f"{DEFAULT_MIN_SNR:g} was used for in-scan reference channels.")
    warn = ((params.get("qc") or {}) if isinstance(params, Mapping) else {}).get("warn_energy_shift_eV")
    if warn is not None and _num(warn, DEFAULT_WARN_SHIFT_EV) > DEFAULT_WARN_SHIFT_EV:
        out.append(f"The params file sets qc.warn_energy_shift_eV to {_num(warn, 0):g}, above the protocol's "
                   f"{DEFAULT_WARN_SHIFT_EV:g} eV; an override may only make the size confirmation stricter, so a "
                   f"calibration shift above {DEFAULT_WARN_SHIFT_EV:g} eV is still applied only with its size confirmed "
                   "(--accept-shift).")
    return out


def _ratio(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def degenerate_snr(snr: Any) -> bool:
    """r4-a (:data:`DEGENERATE_RULE_ID`): an edge SNR that says the pre-edge noise is about zero (not finite, or above
    :data:`MAX_PLAUSIBLE_EDGE_SNR`): a channel that is constant or not counting, never a measured edge."""
    v = _ratio(snr)
    return v is not None and (not math.isfinite(v) or v > MAX_PLAUSIBLE_EDGE_SNR)


def judge(e0s: Sequence[Any], snrs: Sequence[Any], min_snr: float, source: str | None,
          max_spread_eV: Any = None) -> dict:
    """Which reference scans are usable and whether their edges make a reference (the ONE judgement processing and
    every reader of a stored step share). ``passing``: the edges at least ``min_snr`` (the rule before r4-a, kept for
    what is hashed); ``usable``: those whose noise is not degenerate (:data:`DEGENERATE_RULE_ID`); ``degenerate``: how
    many were set aside for it; ``spread_eV`` over ``usable`` (null with fewer than two); ``disagree``: that spread is
    above :func:`effective_max_spread_eV` (:data:`SPREAD_RULE_ID`: not offered, approvable only with
    ``--accept-shift``); ``need``: the usable scans a reference needs; ``proposed``: a reference edge is read (enough
    usable scans), so an approval is possible."""
    passing, usable, degenerate = [], [], 0
    for e, s in zip(e0s or (), snrs or ()):
        v, ev = _ratio(s), _ratio(e)
        if ev is None or v is None:
            continue
        if degenerate_snr(v):
            degenerate += 1
            if not math.isnan(v) and v >= min_snr:
                passing.append(ev)
        elif v >= min_snr:
            passing.append(ev)
            usable.append(ev)
    need = MIN_IN_SCAN_REFERENCE_SCANS if source == IN_SCAN else 1
    spread = float(max(usable) - min(usable)) if len(usable) >= 2 else None
    limit = effective_max_spread_eV(max_spread_eV)
    # r4-a review: compared as qc_verdict compares reference_e0_drift (unrounded), so the two never disagree
    disagree = spread is not None and spread > limit
    return {"passing": passing, "usable": usable, "degenerate": degenerate, "need": need, "spread_eV": spread,
            "max_spread_eV": limit, "disagree": disagree,
            "proposed": source is not None and len(usable) >= need}


def near_sample(outcome: Mapping, measured: float | None) -> float | None:
    """r4-a (:data:`NEAR_SAMPLE_RULE_ID`): the group's own sample E0 when an IN-SCAN reference edge ``measured`` lies
    within :data:`NEAR_SAMPLE_EV` of it, else ``None`` (another source, or no sample E0 stored: a step stored before
    this rule)."""
    sample = _ratio(outcome.get("sample_e0_eV"))
    if outcome.get("reference_source") != IN_SCAN or measured is None or sample is None or not math.isfinite(sample):
        return None
    return sample if abs(float(measured) - sample) < NEAR_SAMPLE_EV else None


def _degenerate_sentence(k: int) -> str:
    return (f"{_n(k, 'scan')}' reference {'channel has' if k == 1 else 'channels have'} an edge step more than "
            f"{MAX_PLAUSIBLE_EDGE_SNR:,.0f} times {'its' if k == 1 else 'their'} pre-edge noise: that noise is about zero, "
            "a channel that is constant or not counting, not a measured edge, so "
            f"{'it is' if k == 1 else 'they are'} not counted as usable. ")


def _near_sample_sentence(measured: float, sample: float, rule: bool = True) -> str:
    return (f" The reference edge, {measured:.1f} eV, is within {NEAR_SAMPLE_EV:g} eV of this group's own sample E0 "
            f"({sample:.1f} eV, before any calibration): the reference channel may be seeing the sample, not a "
            "reference foil. Unless the foil is the sample's own chemical form, check the channel"
            + ("; an approval is applied only with its size confirmed (--accept-shift), whatever the size." if rule else "."))


def _n(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


# --- what a reference group's names say its sample is (CALIBRANT_RULE_ID: a hint, never what applies a shift) ------

_ID_TOKEN = re.compile(r"[_\-\s.,;/+]+")
#: English element names (both spellings where two are in use), for the hint only
ELEMENT_NAMES = {
    "hydrogen": "H", "helium": "He", "lithium": "Li", "beryllium": "Be", "boron": "B", "carbon": "C", "nitrogen": "N",
    "oxygen": "O", "fluorine": "F", "neon": "Ne", "sodium": "Na", "magnesium": "Mg", "aluminium": "Al",
    "aluminum": "Al", "silicon": "Si", "phosphorus": "P", "sulfur": "S", "sulphur": "S", "chlorine": "Cl",
    "argon": "Ar", "potassium": "K", "calcium": "Ca", "scandium": "Sc", "titanium": "Ti", "vanadium": "V",
    "chromium": "Cr", "manganese": "Mn", "iron": "Fe", "cobalt": "Co", "nickel": "Ni", "copper": "Cu", "zinc": "Zn",
    "gallium": "Ga", "germanium": "Ge", "arsenic": "As", "selenium": "Se", "bromine": "Br", "krypton": "Kr",
    "rubidium": "Rb", "strontium": "Sr", "yttrium": "Y", "zirconium": "Zr", "niobium": "Nb", "molybdenum": "Mo",
    "technetium": "Tc", "ruthenium": "Ru", "rhodium": "Rh", "palladium": "Pd", "silver": "Ag", "cadmium": "Cd",
    "indium": "In", "tin": "Sn", "antimony": "Sb", "tellurium": "Te", "iodine": "I", "xenon": "Xe", "caesium": "Cs",
    "cesium": "Cs", "barium": "Ba", "lanthanum": "La", "cerium": "Ce", "praseodymium": "Pr", "neodymium": "Nd",
    "promethium": "Pm", "samarium": "Sm", "europium": "Eu", "gadolinium": "Gd", "terbium": "Tb", "dysprosium": "Dy",
    "holmium": "Ho", "erbium": "Er", "thulium": "Tm", "ytterbium": "Yb", "lutetium": "Lu", "hafnium": "Hf",
    "tantalum": "Ta", "tungsten": "W", "rhenium": "Re", "osmium": "Os", "iridium": "Ir", "platinum": "Pt",
    "gold": "Au", "mercury": "Hg", "thallium": "Tl", "lead": "Pb", "bismuth": "Bi", "polonium": "Po",
    "astatine": "At", "radon": "Rn", "francium": "Fr", "radium": "Ra", "actinium": "Ac", "thorium": "Th",
    "protactinium": "Pa", "uranium": "U", "neptunium": "Np", "plutonium": "Pu",
}
#: an element's own molecule, named as such (elemental sulfur is S8)
_ALLOTROPES = {"s8": "S", "p4": "P"}
#: words that say nothing about the chemistry (a digit suffix allowed: ref1, scan2). r3-b M2: also what a run name says
#: about HOW it was measured — calibration (calib), a beam size (1x3mm, 0p5x1mm), a detector channel (I0-I3, trans,
#: transDet, fluo, fluor, PIPS, Lytle) and a run counter (run2). Measured on a real BL4-3 beamtime: foils named with such
#: words were read "ISAAC cannot tell from its names", while the same names proposed the foil's element. r3-d: a foil
#: thickness (7um, 7p5um, 0p1mm, 50nm) too, and the SYN / ZZ marker of an invented (synthetic) name.
_NEUTRAL = re.compile(r"^(ref|std|cal|calib|foil|metal|powder|elemental|pure|edge|scan|merged|run|trans|transdet|"
                      r"fluo|fluor|pips|lytle|syn|zz)\d*$|^i[0-3]$|^\d+(p\d+)?x\d+(p\d+)?(mm|um)?$"
                      r"|^\d+(p\d+)?(um|nm|mm)$", re.IGNORECASE)
#: r3-d L-3: the detector-channel words of :data:`_NEUTRAL`: beside them, without a foil or ref word, a lone ONE-letter
#: symbol is a label of how the run was measured (``B_trans``, ``S_fluo``, ``C_I1``), never read as that element
_CHANNEL = re.compile(r"^(trans|transdet|fluo|fluor|pips|lytle)\d*$|^i[0-3]$", re.IGNORECASE)
_REF_WORD = re.compile(r"^ref\d*$", re.IGNORECASE)
#: a word after which a lone symbol reads as a LABEL, not an element (ref_B, std_K: reference B, standard K)
_LABEL_AFTER = re.compile(r"^(ref|std|cal|calib|scan)\d*$", re.IGNORECASE)
#: an absorption edge named after a symbol: K, L1-L3, M1-M5 (Kedge, L3edge too)
_EDGE = re.compile(r"^(K|L[1-3]|M[1-5])(edge)?$", re.IGNORECASE)
_JOINED_FOIL = re.compile(r"^([a-z]+)foil\d*$", re.IGNORECASE)
_JOINED_REF = re.compile(r"^([A-Z][a-z]?)ref\d*$")
_IDENTITY_TEXTS_SAID = 4


def _texts(values: Any) -> list[str]:
    if isinstance(values, str):
        return [values]
    if isinstance(values, Mapping):
        return [t for v in values.values() for t in _texts(v)]
    if isinstance(values, (list, tuple)):
        return [t for v in values for t in _texts(v)]
    return []


def _symbol(word: str, any_case: bool) -> str | None:
    """The element ``word`` names as a symbol (``S``, ``Cu``; any case only beside ``foil``) or by its English name."""
    if word in ELEMENTS:
        return word
    if any_case and word.capitalize() in ELEMENTS:
        return word.capitalize()
    # r3-b M2: an English name only as a word (``tin``, ``Tin``), never a formula's capitals (``TiN`` is not tin)
    return ELEMENT_NAMES.get(word.casefold()) if (word.islower() or word.istitle()) else None


def _text_element(text: str) -> tuple[set, str | None] | None:
    """``(elements, edge)`` when EVERY word of ``text`` is on the closed list of a pure element's name (see
    :func:`calibrant_identity`), else ``None``."""
    tokens = [t for t in _ID_TOKEN.split(text) if t]
    foil = any("foil" in t.casefold() for t in tokens)
    # r3-d L-3: a lone one-letter symbol beside a channel word, with no foil or ref word, reads as unknown
    channel_label = not foil and not any(_REF_WORD.match(t) for t in tokens) and any(_CHANNEL.match(t) for t in tokens)
    elements, edges, prev = set(), set(), None
    for i, tok in enumerate(tokens):
        if tok.isdigit():
            pass
        elif tok in ("A", "a") and ((i == len(tokens) - 1 and prev is not None and prev.isdigit())
                                    or (i == len(tokens) - 2 and tokens[-1].isdigit())):
            pass  # r3-b M2: the XDAC counter at the end of a name: ``_016_A`` (a run), ``_A.001`` (its scan file)
        elif elements and (m := _EDGE.match(tok)):
            edges.add(m.group(1).upper())
        elif _NEUTRAL.match(tok):
            pass
        elif tok.casefold() in _ALLOTROPES:
            elements.add(_ALLOTROPES[tok.casefold()])
        elif (el := _symbol(tok, foil)) is not None:
            if prev is not None and _LABEL_AFTER.match(prev) and len(tok) <= 2:
                return None  # ref_B, std_K: a label, not an element
            if channel_label and len(tok) == 1:
                return None  # B_trans, S_fluo: a label of how it was measured, not a pure element
            elements.add(el)
        elif (m := _JOINED_FOIL.match(tok)) and _symbol(m.group(1), True) is not None:
            elements.add(_symbol(m.group(1), True))
        elif (m := _JOINED_REF.match(tok)) and m.group(1) in ELEMENTS:
            elements.add(m.group(1))
        else:
            return None
        prev = tok
    return (elements, next(iter(edges)) if len(edges) == 1 else None) if elements else None


def calibrant_identity(texts: Sequence[str]) -> dict:
    """What a reference group's names say its sample is: a HINT for the scientist, never what applies a calibration
    (:data:`CALIBRANT_RULE_ID`: a group's own edge is applied only with ``--accept-shift``, whatever its names say).
    ``kind`` is ``element`` only when EVERY name read (its sample identity readings and run names) is on a closed list
    naming one pure element: the symbol (any case only beside ``foil``) or English name (sulfur / sulphur), S8, P4,
    ``<El>foil``, ``<El>ref``, with only the words ref, std, cal, calib, foil, metal, powder, elemental, pure, edge,
    scan, merged, a beam size (``1x3mm``), a foil thickness (``7um``), a detector channel (I0-I3, trans, transDet, fluo,
    fluor, PIPS, Lytle; beside one, a one-letter symbol needs a foil or ref word), a run counter (``run2``, digits, a
    final XDAC ``_A``), the SYN / ZZ marker of an invented name, an edge label after the symbol (K, L1-L3, M1-M5) and
    digits beside it. Anything else (a compound, a mixture, a mineral, a label such as ``ref_B``, a name ISAAC does not know) is
    ``unknown``: ISAAC cannot tell. r3-b M2: this ONE reading also says which element a reference group's own edge is
    proposed as (``run.stated_reference``), so a proposal never contradicts it."""
    texts = [str(t) for t in texts if str(t or "").strip()]
    read = [_text_element(t) for t in texts]
    elements = set().union(*(r[0] for r in read if r is not None)) if read else set()
    edges = {r[1] for r in read if r is not None and r[1]}
    where = ", ".join(f"'{t}'" for t in texts[:_IDENTITY_TEXTS_SAID]) + (" …" if len(texts) > _IDENTITY_TEXTS_SAID else "")
    out = {"rule_id": CALIBRANT_RULE_ID, "kind": "unknown", "element": None, "edge": None,
           "read_from": texts[:_IDENTITY_TEXTS_SAID],
           "statement": f"ISAAC cannot tell from its names ({where or 'none was read'}) that this is a pure element."}
    if read and all(r is not None for r in read) and len(elements) == 1:
        element = next(iter(elements))
        out.update(kind="element", element=element, edge=next(iter(edges)) if len(edges) == 1 else None,
                   statement=f"Its names ({where}) say it is {element}.")
    return out


def own_signal(outcome: Mapping) -> dict | None:
    """What a calibration step on a reference group's OWN edge says its names are (its ``reference_calibrant``; ``{}``
    for a step stored before names were read), else ``None`` (another source)."""
    if not isinstance(outcome, Mapping) or outcome.get("reference_source") != OWN_SIGNAL:
        return None
    cal = outcome.get("reference_calibrant")
    return dict(cal) if isinstance(cal, Mapping) else {}


def named_element(cal: Mapping | None) -> str | None:
    """The pure element a group's names clearly say (:func:`calibrant_identity`), else ``None``."""
    return cal.get("element") if isinstance(cal, Mapping) and cal.get("kind") == "element" else None


#: r3-b M2: said in place of "approve with --accept-shift <shift>" when no shift is known yet (no edge named)
NO_SHIFT_YET = "naming its element and edge gives the shift, which is then confirmed with --accept-shift"


def own_signal_sentence(cal: Mapping | None, shift: str | None, element: str | None = None) -> str:
    """The plain sentence for a calibration on a group's own edge: always confirmed with ``--accept-shift`` (shown
    ``shift``); its names are only a hint. ``element``: the element an approval names (a mismatch is said). r3-b M2:
    ``shift`` ``None`` (no shift is known: no edge is named) drops the "approve with --accept-shift" clause, never a
    placeholder in its place."""
    said = OWN_SIGNAL_RULE
    el = named_element(cal)
    approve = f"approve with --accept-shift {shift}" if shift is not None else NO_SHIFT_YET
    if el is not None and element is not None and element != el:
        return (f"{said}: its names say it is {el}, not {element}; check the element. Only if it is pure {element}, "
                f"{approve}.")
    if el is not None:
        return f"{said}: its names say it is {el}; if so, {approve}."
    return (f"{said}. ISAAC cannot tell from its names that this is a pure element; "
            f"{CHEMICAL_STANDARD[0].lower() + CHEMICAL_STANDARD[1:]}. Only if it is a pure element, {approve}.")


def confirmed_sentence(shift: str, ref: Mapping | None = None) -> str:
    """r3-b L8: what a calibration on a group's own edge says once the scientist CONFIRMED it (``--accept-shift``
    matching the shift): no question is left, so the names' hint and "only if it is a pure element" are not said."""
    ref = ref or {}
    who = f" by {ref['decided_by']}" if ref.get("decided_by") else ""
    named = f" ({ref['element']} {ref['edge']})" if ref.get("element") and ref.get("edge") else ""
    return (f"The scientist confirmed this group's own edge as the energy calibration{named}{who}, with "
            f"--accept-shift {shift}, so it is applied.")


def _confirmed(outcome: Mapping) -> bool:
    """A scientist's approval whose size they confirmed (``--accept-shift``) was applied to this step's curve."""
    ref = outcome.get("reference") or {}
    return bool(outcome.get("applied") and ref.get("basis") == "scientist_decision"
                and outcome.get("accepted_shift_eV") is not None
                and shift_size_confirmed(outcome.get("accepted_shift_eV"), outcome.get("applied_shift_eV")))


def reading(step: Mapping) -> dict:
    """The reference a calibration step read: ``reference_source``, ``reference_scans_usable`` / ``_listed``,
    ``measured_reference_e0_eV`` (median of the usable scans), ``reference_e0_spread_eV`` (null with fewer than two
    usable scans: one scan has no spread), ``reference_proposed`` (a usable reference edge was read),
    ``calibration_proposed`` (ISAAC offers it as the energy calibration: a group's own edge only when its names clearly
    say one pure element, and even then it is applied only with ``--accept-shift``, :data:`CALIBRANT_RULE_ID`) and
    ``reference_statement`` (one plain sentence)."""
    o = step.get("outcome") or {}
    source = o.get("reference_source")
    calibrant = own_signal(o)
    min_snr = effective_min_snr((step.get("params") or {}).get("reference_min_edge_snr"), source)
    j = judge(o.get("reference_e0_per_scan_eV") or [], o.get("reference_snr_per_scan") or [], min_snr, source,
              o.get("reference_max_spread_eV"))
    usable = j["usable"]
    listed = len(o.get("reference_snr_per_scan") or [])
    need = j["need"]
    proposed = j["proposed"]
    measured = float(statistics.median(usable)) if usable else None
    spread = j["spread_eV"]
    of = f"{len(usable)} of {_n(listed, 'scan')}"
    snr = f"edge step / pre-edge noise at least {min_snr:g}"
    if j["degenerate"]:
        snr += f" and at most {MAX_PLAUSIBLE_EDGE_SNR:,.0f}"
    sample = near_sample(o, measured) if proposed else None
    if source is None:
        said = ("This group has no energy reference (no reference channel was read and it is not a reference group), "
                "so no calibration shift can be proposed or approved.")
    elif not usable:
        said = (f"No scan shows a usable reference edge (0 of {_n(listed, 'scan')} with {snr}), so no reference is "
                "proposed and no calibration shift can be approved.")
    elif not proposed:
        said = (f"Only {of} shows a usable reference edge ({snr}; at {measured:.1f} eV); an in-scan reference needs one "
                f"in at least {MIN_IN_SCAN_REFERENCE_SCANS} scans, so no reference is proposed and no calibration "
                "shift can be approved. The other scans' reference edges are noise, not a measurement.")
    else:
        where = "the reference channel" if source == IN_SCAN else "this reference group's own signal"
        said = (f"{of[0].upper() + of[1:]} show{'s' if len(usable) == 1 else ''} a usable reference edge in {where} "
                f"({snr}), at {measured:.1f} eV"
                + (f" (spread {spread:.2f} eV)." if spread is not None else "."))
        if calibrant is not None and _confirmed(o):
            # r3-b L8: the scientist confirmed it (--accept-shift): the question is answered, so it is not asked again
            said += " " + confirmed_sentence(shown(o["applied_shift_eV"]), o.get("reference"))
        elif calibrant is not None:
            # CALIBRANT_RULE_ID: the edge is read; applying it always needs --accept-shift, the names are a hint
            said += " " + own_signal_sentence(calibrant, _hinted_shift(o, calibrant, measured))
            if calibrant.get("read_from"):
                said += " Names read: " + ", ".join(f"'{t}'" for t in calibrant["read_from"]) + "."
        else:
            said += " Naming its element and edge gives the shift: the tabulated edge minus this energy."
        if sample is not None:
            said += _near_sample_sentence(measured, sample)
        if j["disagree"]:
            # r4-a (SPREAD_RULE_ID): not offered; approvable only with --accept-shift, whatever the size
            said = said.replace(f" (spread {spread:.2f} eV).", ".", 1) + " " + _spread_sentence(
                spread, j["max_spread_eV"], measured, len(usable), usable,
                shown(o["computed_shift_eV"]) if o.get("computed_shift_eV") is not None else None,
                confirmed=_size_confirmed_step(o))
    if j["degenerate"] and source is not None:
        said = _degenerate_sentence(j["degenerate"]) + said
    return {
        "reference_source": source,
        "reference_scans_usable": len(usable),
        "reference_scans_listed": listed,
        "reference_min_scans": need if source is not None else None,
        "measured_reference_e0_eV": measured,
        "reference_e0_spread_eV": spread,
        # a usable reference edge was read (approve_calibration is possible); calibration_proposed says whether ISAAC
        # offers it as the energy calibration (CALIBRANT_RULE_ID: a group's own edge only when its names clearly say a
        # pure element, never a compound, a mixture or an unknown; applying it needs --accept-shift either way)
        "reference_proposed": proposed,
        "calibration_proposed": (proposed and not j["disagree"]
                                 and (calibrant is None or named_element(calibrant) is not None)),
        "reference_statement": said,
        # r4-a: why fewer scans are usable than before, whether the edges disagree, and an edge at the sample's own E0
        # (each only when it applies, so an unaffected reading is unchanged)
        **({"reference_scans_degenerate": j["degenerate"]} if j["degenerate"] else {}),
        **({"reference_edges_disagree": True, "reference_max_spread_eV": j["max_spread_eV"]} if j["disagree"] else {}),
        **({"reference_at_sample_e0_eV": sample} if sample is not None else {}),
        **({"reference_calibrant": dict(o["reference_calibrant"])} if isinstance(o.get("reference_calibrant"), Mapping) else {}),
    }


def _size_confirmed_step(outcome: Mapping) -> bool:
    """A scientist's approval, with its size confirmed (``--accept-shift`` matching), was applied to this curve."""
    return bool(outcome.get("applied") and outcome.get("accepted_shift_eV") is not None
                and shift_size_confirmed(outcome.get("accepted_shift_eV"), outcome.get("applied_shift_eV")))


def _spread_sentence(spread: float, limit: float, measured: float, n: int, usable: Sequence[float],
                     shift: str | None, *, confirmed: bool = False, reply: bool = False) -> str:
    """r4-a (:data:`SPREAD_RULE_ID`): the sentence for usable reference edges that spread over more than ``limit``."""
    # r4-a review: just above the level, 0.001 eV, so "0.50 eV, more than 0.5 eV" is never said
    sp = f"{spread:.3f}" if round(spread, 2) <= limit else f"{spread:.2f}"
    said = (f"Its usable edges spread {sp} eV ({min(usable):.1f} to {max(usable):.1f} eV; median {measured:.1f} eV "
            f"of {_n(n, 'scan')}), more than the {limit:g} eV they may differ by (qc.warn_reference_e0_spread_eV), so "
            "ISAAC does not propose it as the reference: a missing foil, a channel that sees the sample, or the energy "
            "drifting between scans gives this.")
    if confirmed:
        return said + (" You confirmed the shift's size (--accept-shift), so processing applies it." if reply else
                       " The scientist confirmed the shift's size (--accept-shift), so it is applied.")
    approve = f"--accept-shift {shift}" if shift is not None else "--accept-shift <the shift approving shows>"
    return said + f" Approve only if the reference is what you name, with {approve}, whatever its size."


def _hinted_shift(outcome: Mapping, cal: Mapping, measured: float | None) -> str | None:
    """The shift ``--accept-shift`` would take for a group's own edge, as shown, when it is known: the step's computed
    shift (its proposed or approved element and edge), else the tabulated edge its names give minus ``measured``;
    ``None`` when neither is known (r3-b M2: never a placeholder said as if it were a shift)."""
    if outcome.get("computed_shift_eV") is not None:
        return shown(outcome["computed_shift_eV"])
    el, ed = named_element(cal), cal.get("edge")
    tab = edge_energy(el, ed)[0] if el and ed and measured is not None else None
    return shown(tab - measured) if tab is not None else None


def _digits(value: float, warn_eV: Any) -> int:
    return 2 if abs(abs(float(value)) - effective_warn_eV(warn_eV)) < NEAR_WARN_EV else 1


def shown(shift: float, warn_eV: Any = None) -> str:
    """A shift as it is said and as ``--accept-shift`` takes it: signed, 0.1 eV (``-8.6``, ``+0.2``); within
    :data:`NEAR_WARN_EV` of the warning level, 0.01 eV (``+2.04``: above 2 eV, so it needs its size confirmed)."""
    n = _digits(shift, warn_eV)
    v = round(float(shift), n)
    return f"{'+' if v > 0 else ''}{v:.{n}f}" if v != 0 else f"{0:.{n}f}"


def _ev(value: float, warn_eV: Any = None) -> str:
    """A magnitude in eV, to the precision :func:`shown` uses for it."""
    return f"{abs(float(value)):.{_digits(value, warn_eV)}f}"


def shift_size_confirmed(accepted: Any, shift: float) -> bool:
    """True when ``accepted`` is the shift shown (to 0.1 eV)."""
    try:
        return round(float(accepted), 1) == round(float(shift), 1)
    except (TypeError, ValueError):
        return False


def would_apply(step: Mapping, element: str, edge: str, *, warn_eV: float | None = None, accepted: Any = None) -> dict:
    """What approving ``element`` ``edge`` as this step's reference would do: ``shift_eV`` (tabulated - measured),
    ``shown``, ``needs_size_confirmation`` (|shift| above ``qc.warn_energy_shift_eV``), ``implausible`` (above
    ``calibration.max_plausible_shift_eV``: never applied), ``needs_calibrant_confirmation`` (a reference group's own
    edge, :data:`CALIBRANT_RULE_ID`: its size is confirmed whatever it is and whatever its names say, so
    ``needs_size_confirmation`` is true too), ``statement``. ``shift_eV`` is null when no reference is proposed or
    the edge energy is unknown (``statement`` says why). r3-b L8: ``accepted`` (the ``--accept-shift`` value): when it
    confirms the shift of a group's own edge, the statement says it is confirmed instead of asking again."""
    r = reading(step)
    warn = effective_warn_eV(warn_eV)
    max_eV = float((step.get("params") or {}).get("max_plausible_shift_eV") or DEFAULT_MAX_SHIFT_EV)
    out = {"element": element, "edge": edge, "tabulated_edge_eV": None, "tabulated_edge_source": None,
           "measured_reference_e0_eV": r["measured_reference_e0_eV"], "shift_eV": None, "shown": None,
           "warn_energy_shift_eV": warn, "needs_size_confirmation": False, "needs_calibrant_confirmation": False,
           "implausible": False}
    if not r["reference_proposed"]:
        return {**out, "statement": r["reference_statement"]}
    tab, src = edge_energy(element, edge)
    if tab is None:
        return {**out, "tabulated_edge_source": src,
                "statement": f"No tabulated energy is known for {element} {edge} ({src}), so no shift can be computed."}
    measured = r["measured_reference_e0_eV"]
    shift = tab - measured
    gap = measured - tab
    side = "above" if gap > 0 else "below"
    said = (f"The reference edge sits {_ev(gap, warn)} eV {side} {element} {edge}'s tabulated {tab:.1f} eV; "
            f"approving applies {shown(shift, warn)} eV to this group's energy axis.")
    # r4-a: what the reference edge is read from, so the approval's reply says it (the median, the scans, the spread)
    n_used = r["reference_scans_usable"]
    disagree = bool(r.get("reference_edges_disagree"))
    if not disagree:
        said += (f" That reference edge is the median of {_n(n_used, 'usable scan')} ({measured:.1f} eV"
                 + (f", spread {r['reference_e0_spread_eV']:.2f} eV" if r["reference_e0_spread_eV"] is not None else "")
                 + ").")
    sample = r.get("reference_at_sample_e0_eV")
    if sample is not None:
        said += _near_sample_sentence(measured, sample, rule=False)
    implausible = abs(shift) > max_eV
    if disagree and not implausible:
        # r4-a (SPREAD_RULE_ID): not offered; applied only with --accept-shift, whatever the size. Said BEFORE the size
        # sentence, so the reply that records a confirmed approval keeps it (and says the size was confirmed)
        o = step.get("outcome") or {}
        usable = judge(o.get("reference_e0_per_scan_eV") or [], o.get("reference_snr_per_scan") or [],
                       effective_min_snr((step.get("params") or {}).get("reference_min_edge_snr"), r["reference_source"]),
                       r["reference_source"], o.get("reference_max_spread_eV"))["usable"]
        said += " " + _spread_sentence(r["reference_e0_spread_eV"], r["reference_max_spread_eV"], measured, n_used, usable,
                                       shown(shift, warn),
                                       confirmed=accepted is not None and shift_size_confirmed(accepted, shift), reply=True)
    big = exceeds_warn(shift, warn) and not implausible
    calibrant = own_signal(step.get("outcome") or {}) if not implausible else None
    if calibrant is not None and accepted is not None and shift_size_confirmed(accepted, shift):
        # r3-b L8: the scientist confirmed this size: "ISAAC cannot tell ... only if it is a pure element" is not
        # said again in the reply that records it
        said += (f" This is the group's own edge: with its size confirmed (--accept-shift {shown(shift, warn)}), "
                 "processing applies it as the energy calibration.")
    elif calibrant is not None:
        # CALIBRANT_RULE_ID: said BEFORE the size sentence (a confirmed approval's reply keeps the text before it); the
        # names are a hint only, and an element they name that is not the approved one is said
        said += " " + own_signal_sentence(calibrant, shown(shift, warn), element)
    if implausible:
        said += (f" That is more than the protocol's {max_eV:g} eV plausible limit, so it would not be applied: "
                 f"check the element and edge.")
    elif big:
        said += (f" That is more than the protocol's {warn:g} eV warning level and moves every energy of the record "
                 f"(E0 included) by that much: it is applied only when you also confirm its size "
                 f"(--accept-shift {shown(shift, warn)}).")
    elif sample is not None and not (accepted is not None and shift_size_confirmed(accepted, shift)):
        # r4-a (NEAR_SAMPLE_RULE_ID): not said once the scientist confirmed the size (the reply that records it)
        said += (f" It is applied only when you also confirm its size (--accept-shift {shown(shift, warn)}), once the "
                 "scientist says the channel holds a reference foil.")
    return {**out, "tabulated_edge_eV": tab, "tabulated_edge_source": src, "shift_eV": shift, "shown": shown(shift, warn),
            # the size is confirmed (--accept-shift) for a shift above the warning level, for ANY shift of a group's
            # own edge (CALIBRANT_RULE_ID), whatever its names say, and (r4-a) for an in-scan reference edge at the
            # group's own sample E0 (NEAR_SAMPLE_RULE_ID)
            "needs_size_confirmation": (big or calibrant is not None
                                        or ((sample is not None or disagree) and not implausible)),
            "needs_calibrant_confirmation": calibrant is not None,
            "implausible": implausible, "statement": said}


def carried_shift(step: Mapping, approval: Mapping | None = None, *, warn_eV: Any = None,
                  group_id: str | None = None, result_id: str | None = None) -> dict | None:
    """The calibration shift a stored result's curve CARRIES (``outcome.applied``), and whether the current rules
    would apply it; ``None`` when the curve carries none. ``approval`` is the group's latest ``approve_calibration``
    (:func:`mutations.calibration_approvals`): its ``accepted_shift_eV`` confirms the carried size when it matches to
    0.1 eV, as the step's own ``accepted_shift_eV`` does. Returns ``applied_shift_eV``, ``shown``, ``confirmed``,
    ``reason`` (why it is unconfirmed, or ``None``) and ``statement``.

    Unconfirmed: a curve approved under an older build whose reference is no longer proposed (an in-scan reference
    usable in one scan only) or whose shift is above the warning level with no size confirmed. Such a result is kept
    on re-processing (it is decided), so its curve, E0 included, keeps the shift until the scientist confirms the size
    (``approve_calibration --accept-shift <shown>``) or rejects the result."""
    o = step.get("outcome") or {}
    try:
        applied = float(o.get("applied_shift_eV") or 0.0)
    except (TypeError, ValueError):
        return None
    if not o.get("applied") or applied == 0.0:
        return None
    warn = effective_warn_eV(warn_eV)
    said = shown(applied, warn)
    accepted = [a for a in ((approval or {}).get("accepted_shift_eV"), o.get("accepted_shift_eV")) if a is not None]
    size_confirmed = any(shift_size_confirmed(a, applied) for a in accepted)
    r = reading(step)
    reason = None
    # a step that lists no per-scan reference reading cannot be re-judged by the scan rule: only the size rule applies
    judged = "reference_snr_per_scan" in o
    if not size_confirmed and judged and r["reference_proposed"] and r.get("reference_edges_disagree"):
        # r4-a (SPREAD_RULE_ID)
        reason = (f"it was approved from reference edges that spread over {r['reference_e0_spread_eV']:.2f} eV, more "
                  f"than the {r['reference_max_spread_eV']:g} eV they may differ by, and its size was never confirmed "
                  "(such a reference is applied only with --accept-shift)")
    elif not size_confirmed and judged and not r["reference_proposed"]:
        degenerate = (f" ({_n(r['reference_scans_degenerate'], 'scan')} set aside for a pre-edge noise of about zero)"
                      if r.get("reference_scans_degenerate") else "")
        reason = (f"it was approved from a reference edge usable in {r['reference_scans_usable']} of "
                  f"{_n(r['reference_scans_listed'], 'scan')}{degenerate}, and an in-scan reference now needs one in at "
                  f"least {MIN_IN_SCAN_REFERENCE_SCANS} scans, so the current rules compute no shift")
    elif not size_confirmed and judged and r.get("reference_at_sample_e0_eV") is not None:
        # r4-a (NEAR_SAMPLE_RULE_ID)
        reason = (f"its reference edge lies within {NEAR_SAMPLE_EV:g} eV of this group's own sample E0, so the reference "
                  "channel may be seeing the sample, and its size was never confirmed")
    elif not size_confirmed and exceeds_warn(applied, warn):
        reason = (f"it is more than the protocol's {warn:g} eV warning level and its size was never confirmed "
                  "(an older build applied it without --accept-shift)")
    elif not size_confirmed and "reference_calibrant" in o and own_signal(o) is not None:
        # CALIBRANT_RULE_ID: a step that read the group's names was processed under this rule, so a shift it carries
        # without --accept-shift was never confirmed. A step stored before it (no names read) keeps its approved curve.
        reason = ("it calibrates on this group's own edge, which is applied only with --accept-shift, and its size was "
                  f"never confirmed ({CHEMICAL_STANDARD[0].lower() + CHEMICAL_STANDARD[1:]})")
    ref = o.get("reference") or {}
    el, ed = ref.get("element") or "<element>", ref.get("edge") or "<edge>"
    if reason is None:
        statement = f"This curve carries the approved calibration shift of {said} eV ({el} {ed})."
    else:
        gid = group_id or "<group id>"
        pid = result_id or "<result id>"
        statement = (f"This curve carries {said} eV that is now unconfirmed: {reason}. Every energy of the curve, E0 "
                     f"included, is moved by it. Re-approve with --accept-shift {said} if the scientist confirms that "
                     f"size (`isaac bundle decide <bundle_dir> --target {gid} --decision approve_calibration --element "
                     f"{el} --edge {ed} --accept-shift {said} --by \"<your name>\"`), or reject the result "
                     f"(`isaac bundle decide <bundle_dir> --target {pid} --decision reject --by \"<your name>\"`).")
    return {"applied_shift_eV": applied, "shown": said, "confirmed": reason is None, "reason": reason,
            "element": ref.get("element"), "edge": ref.get("edge"), "statement": statement}


def approval_not_applied(step: Mapping, warn_eV: Any = None) -> str | None:
    """The sentence for a result processed under a scientist's calibration approval that the current rules did not
    apply (flag :data:`TOO_FEW_FLAG`, :data:`SIZE_NOT_CONFIRMED_FLAG` or :data:`CALIBRANT_NOT_CONFIRMED_FLAG`), naming
    that approval; ``None`` otherwise."""
    o = step.get("outcome") or {}
    flags = set(step.get("flags") or ())
    ref = o.get("reference") or {}
    if ref.get("basis") != "scientist_decision" or not flags & {TOO_FEW_FLAG, SIZE_NOT_CONFIRMED_FLAG, CALIBRANT_NOT_CONFIRMED_FLAG,
                                                                DEGENERATE_FLAG, NEAR_SAMPLE_NOT_CONFIRMED_FLAG,
                                                                SPREAD_NOT_CONFIRMED_FLAG}:
        return None
    named = (f"The calibration approval {ref.get('decision_id') or ''} ({ref.get('element')} {ref.get('edge')}, "
             f"by {ref.get('decided_by')})").replace("approval  (", "approval (")
    r4 = reading(step)
    if not o.get("applied") and not r4["reference_proposed"] and DEGENERATE_FLAG in flags and TOO_FEW_FLAG not in flags:
        # r4-a: a reference the current rules do not read (its scans' pre-edge noise is about zero)
        return (f"{named} is not applied: {r4['reference_statement']} So no shift is computed for it and this curve "
                "carries no calibration shift. A result approved earlier keeps the curve it has (`bundle show "
                "processing-result` says whether a shift it carries is confirmed).")
    if not flags & {TOO_FEW_FLAG, SIZE_NOT_CONFIRMED_FLAG, CALIBRANT_NOT_CONFIRMED_FLAG, NEAR_SAMPLE_NOT_CONFIRMED_FLAG,
                    SPREAD_NOT_CONFIRMED_FLAG}:
        return None
    if SPREAD_NOT_CONFIRMED_FLAG in flags:
        shift = o.get("computed_shift_eV")
        said = shown(shift, warn_eV) if shift is not None else "?"
        return (f"{named} is not applied: its usable reference edges spread {r4['reference_e0_spread_eV']:.2f} eV "
                f"(median {r4['measured_reference_e0_eV']:.1f} eV of {_n(r4['reference_scans_usable'], 'scan')}), more "
                f"than the {r4['reference_max_spread_eV']:g} eV they may differ by, and the size of the shift it gives, "
                f"{said} eV, was not confirmed, so this curve carries no calibration shift. Approve again with "
                f"--accept-shift {said} only if the reference is what the scientist names.")
    if NEAR_SAMPLE_NOT_CONFIRMED_FLAG in flags:
        shift = o.get("computed_shift_eV")
        said = shown(shift, warn_eV) if shift is not None else "?"
        return (f"{named} is not applied: the reference edge lies within {NEAR_SAMPLE_EV:g} eV of this group's own sample "
                f"E0, so the reference channel may be seeing the sample, and the size of the shift it gives, {said} eV, "
                "was not confirmed, so this curve carries no calibration shift. Approve again with --accept-shift "
                f"{said} if the scientist says the channel holds a reference foil.")
    if TOO_FEW_FLAG in flags:
        r = reading(step)
        return (f"{named} is not applied: only {r['reference_scans_usable']} of "
                f"{_n(r['reference_scans_listed'], 'scan')} shows a usable reference edge and an in-scan reference needs "
                f"one in at least {MIN_IN_SCAN_REFERENCE_SCANS}, so no shift is computed and this curve carries no "
                "calibration shift. A result approved earlier keeps the curve it has (`bundle show processing-result` "
                "says whether a shift it carries is confirmed).")
    warn = effective_warn_eV(warn_eV)
    shift = o.get("computed_shift_eV")
    said = shown(shift, warn) if shift is not None else "?"
    accepted = o.get("accepted_shift_eV")
    why = (f"the size confirmed (--accept-shift {shown(accepted, warn)}) is not the shift it gives" if accepted is not None
           else "its size was not confirmed")
    if CALIBRANT_NOT_CONFIRMED_FLAG in flags:
        older = ("" if accepted is not None else
                 " That approval was recorded without --accept-shift, before ISAAC required it for a group's own edge: "
                 "the current rule applies to this result, processed now, so its curve carries no shift (a result "
                 "already approved keeps the curve it has).")
        return (f"{named} is not applied: the shift it gives, {said} eV, would move this group's own edge onto "
                f"{ref.get('element')} {ref.get('edge')}'s tabulated energy and {why}, so this curve carries no "
                f"calibration shift.{older} {own_signal_sentence(own_signal(o), said, ref.get('element'))}")
    return (f"{named} is not applied: the shift it gives, {said} eV, is more than the protocol's {warn:g} eV warning "
            f"level and {why}, so this curve carries no calibration shift. Approve again with --accept-shift {said} "
            "if the scientist confirms that size.")
