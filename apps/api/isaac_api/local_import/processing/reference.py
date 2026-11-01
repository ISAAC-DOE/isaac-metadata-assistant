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
* :data:`CALIBRANT_RULE_ID` — a reference group's OWN edge is proposed as the energy calibration only when the group's
  sample is named as a pure element (a foil, elemental sulfur; :func:`calibrant_identity`). A chemical standard is not
  an energy calibrant: its edge sits where its chemistry puts it. Measured on a real BL4-3 sulfur K-edge beamtime:
  CoSO4, MoS2 and Na2S2O3 standards (5 and 0.5 wt% in sucrose) were offered as their own calibration, and a truthful
  "S K" would have moved them by -9.6 and +1.2 eV onto elemental sulfur's tabulated edge, erasing the chemical shift
  each was measured to show. A compound, a mixture or a sample whose identity is not stated is not proposed
  (``calibration_proposed: false``, said why); approving its own edge anyway needs ``--accept-shift`` with the shift
  shown, WHATEVER its size. A stored step without ``reference_calibrant`` (made before this rule) is read as before.
"""

from __future__ import annotations

import re
import statistics
from typing import Any, Mapping, Sequence

from .edges import edge_energy

MIN_IN_SCAN_REFERENCE_SCANS = 2
IN_SCAN_MIN_RULE_ID = "isaac.xas.in_scan_reference_min_scans.v0"
SHIFT_SIZE_RULE_ID = "isaac.xas.calibration_shift_size_confirmed.v0"
STRICTER_ONLY_RULE_ID = "isaac.xas.calibration_overrides_stricter_only.v0"
CALIBRANT_RULE_ID = "isaac.xas.own_signal_calibrant_pure_element.v0"
IN_SCAN = "in_scan_reference_channel"
OWN_SIGNAL = "reference_group_own_signal"
TOO_FEW_FLAG = "reference_edge_in_too_few_scans"
SIZE_NOT_CONFIRMED_FLAG = "calibration_shift_size_not_confirmed"
#: a reference group whose own edge is not proposed as the calibration (its sample is not named as a pure element)
NOT_A_CALIBRANT_FLAG = "own_signal_not_an_energy_calibrant"
#: an approval of such a group's own edge that the scientist did not also confirm with --accept-shift: not applied
CALIBRANT_NOT_CONFIRMED_FLAG = "calibration_own_signal_shift_not_confirmed"
CHEMICAL_STANDARD = "A chemical standard is not an energy calibrant: its edge sits where its chemistry puts it"

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


def ignored_overrides(params: Mapping) -> list[str]:
    """One sentence per params-file value :data:`STRICTER_ONLY_RULE_ID` ignored (``[]`` when none was)."""
    out = []
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


def _usable(outcome: Mapping, min_snr: float) -> list[float]:
    e0s = outcome.get("reference_e0_per_scan_eV") or []
    snrs = outcome.get("reference_snr_per_scan") or []
    return [float(e) for e, s in zip(e0s, snrs) if e is not None and s is not None and float(s) >= min_snr]


def _n(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


# --- what a reference group's sample is (CALIBRANT_RULE_ID) --------------------------------------------------------

_ID_TOKEN = re.compile(r"[_\-\s.,;/+]+")
_FORMULA = re.compile(r"^(?:[A-Z][a-z]?\d*)+$")
_FORMULA_PART = re.compile(r"([A-Z][a-z]?)\d*")
_FOIL_OF = re.compile(r"^([A-Z][a-z]?)foil$")
#: ion-chamber and detector names (I0, I1, I2, IF): never iodine
_DETECTOR = re.compile(r"^I[0-9F]$")
#: an element's own molecule, named as such (elemental sulfur is S8)
_ALLOTROPES = {"S8": "S", "P4": "P"}
#: a dilution or a matrix: 5wt, 0p5wt, wt%, sucrose, BN ...
_DILUTION = re.compile(r"^(\d+(p\d+)?)?(wt|wtpct|pct|percent|ppm)%?$")
_MIXTURE_WORDS = frozenset({"sucrose", "cellulose", "bn", "mix", "mixed", "mixture", "dilute", "diluted", "dilution",
                            "blend", "composite", "alloy", "matrix"})
_COMPOUND_WORDS = frozenset({"mof", "complex", "salt", "polymer", "compound", "mineral"})
_COMPOUND_ENDINGS = ("ide", "ate", "ite")
_IDENTITY_TEXTS_SAID = 4


def _texts(values: Any) -> list[str]:
    if isinstance(values, str):
        return [values]
    if isinstance(values, Mapping):
        return [t for v in values.values() for t in _texts(v)]
    if isinstance(values, (list, tuple)):
        return [t for v in values for t in _texts(v)]
    return []


def calibrant_identity(texts: Sequence[str]) -> dict:
    """What a reference group's sample is named as, read ONLY from the names it has (its sample identity and run
    names): ``kind`` is ``element`` (exactly one element, named alone: ``S``, ``Ti``, ``Tifoil``, ``S8``), ``compound``
    (a formula of two or more elements, ``CoSO4``, ``MoS2``, or a word such as oxide or MOF), ``mixture`` (a dilution or
    matrix: ``5wt``, ``sucrose``) or ``unknown`` (no chemistry named, or several elements). Only ``element`` lets the
    group's own edge be proposed as the energy calibration (:data:`CALIBRANT_RULE_ID`). Case-sensitive: an all-capital
    word with no digit (``SYN``, ``STD``) is never read as a formula."""
    texts = [str(t) for t in texts if str(t or "").strip()]
    elements, compounds, mixtures = set(), [], []
    for text in texts:
        for tok in (t for t in _ID_TOKEN.split(text) if t):
            bare = re.sub(r"[()\[\]]", "", tok)
            low = bare.casefold()
            if _DILUTION.match(low) or low in _MIXTURE_WORDS:
                mixtures.append(tok)
            elif low in _COMPOUND_WORDS or (len(low) >= 5 and low.isalpha() and low.endswith(_COMPOUND_ENDINGS)):
                compounds.append(tok)
            elif bare in ELEMENTS and not _DETECTOR.match(bare):
                elements.add(bare)
            elif bare in _ALLOTROPES:
                elements.add(_ALLOTROPES[bare])
            elif (m := _FOIL_OF.match(bare)) and m.group(1) in ELEMENTS:
                elements.add(m.group(1))
            elif (_FORMULA.match(bare) and not _DETECTOR.match(bare) and (bare != bare.upper() or any(c.isdigit() for c in bare))):
                parts = {p for p in _FORMULA_PART.findall(bare)}
                if parts <= ELEMENTS and len(parts) >= 2:
                    compounds.append(tok)
    named = sorted(set(compounds)) + sorted(set(mixtures)) + sorted(elements)
    where = ", ".join(f"'{t}'" for t in texts[:_IDENTITY_TEXTS_SAID]) + (" …" if len(texts) > _IDENTITY_TEXTS_SAID else "")
    if compounds:
        kind, element = "compound", None
        said = f"This group's sample is named as a compound ({', '.join(sorted(set(compounds)))}, read from {where})."
    elif mixtures:
        kind, element = "mixture", None
        said = f"This group's sample is named as a mixture or dilution ({', '.join(sorted(set(mixtures)))}, read from {where})."
    elif len(elements) == 1:
        kind, element = "element", next(iter(elements))
        said = f"This group's sample is named as the pure element {element} (read from {where})."
    else:
        kind, element = "unknown", None
        said = ("This group's names do not state that its sample is a pure element ("
                + (f"they name several elements: {', '.join(sorted(elements))}; " if elements else "")
                + (f"read from {where})." if texts else "no name was read)."))
    return {"rule_id": CALIBRANT_RULE_ID, "kind": kind, "element": element, "named": named,
            "read_from": texts[:_IDENTITY_TEXTS_SAID], "statement": said}


def not_a_calibrant(outcome: Mapping) -> dict | None:
    """The ``reference_calibrant`` of an own-signal step whose sample is NOT named as a pure element, else ``None``
    (another source, a pure element, or a step stored before :data:`CALIBRANT_RULE_ID`, which is read as before)."""
    cal = outcome.get("reference_calibrant") if isinstance(outcome, Mapping) else None
    if outcome.get("reference_source") != OWN_SIGNAL or not isinstance(cal, Mapping) or cal.get("kind") == "element":
        return None
    return cal


def not_proposed_sentence(cal: Mapping) -> str:
    """Why a reference group's own edge is not proposed as the calibration, in plain words."""
    return (f"{cal.get('statement') or ''} {CHEMICAL_STANDARD}, so this group's own edge is not proposed as the energy "
            "calibration; only a pure element (a foil, elemental sulfur) is.").strip()


def reading(step: Mapping) -> dict:
    """The reference a calibration step read: ``reference_source``, ``reference_scans_usable`` / ``_listed``,
    ``measured_reference_e0_eV`` (median of the usable scans), ``reference_e0_spread_eV`` (null with fewer than two
    usable scans: one scan has no spread), ``reference_proposed`` (a usable reference edge was read),
    ``calibration_proposed`` (ISAAC offers it as the energy calibration: not for a reference group whose sample is not
    named as a pure element, :data:`CALIBRANT_RULE_ID`) and ``reference_statement`` (one plain sentence)."""
    o = step.get("outcome") or {}
    source = o.get("reference_source")
    calibrant = not_a_calibrant(o)
    min_snr = effective_min_snr((step.get("params") or {}).get("reference_min_edge_snr"), source)
    usable = _usable(o, min_snr)
    listed = len(o.get("reference_snr_per_scan") or [])
    need = MIN_IN_SCAN_REFERENCE_SCANS if source == IN_SCAN else 1
    proposed = source is not None and len(usable) >= need
    measured = float(statistics.median(usable)) if usable else None
    spread = float(max(usable) - min(usable)) if len(usable) >= 2 else None
    of = f"{len(usable)} of {_n(listed, 'scan')}"
    snr = f"edge step / pre-edge noise at least {min_snr:g}"
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
        if calibrant is not None:
            # CALIBRANT_RULE_ID: the edge is read, but it is not offered as the calibration
            said += (f" {not_proposed_sentence(calibrant)} Only if the scientist asks for it: approving it needs "
                     "--accept-shift with the shift it gives, whatever its size.")
        else:
            said += " Naming its element and edge gives the shift: the tabulated edge minus this energy."
    return {
        "reference_source": source,
        "reference_scans_usable": len(usable),
        "reference_scans_listed": listed,
        "reference_min_scans": need if source is not None else None,
        "measured_reference_e0_eV": measured,
        "reference_e0_spread_eV": spread,
        # a usable reference edge was read (approve_calibration is possible); calibration_proposed says whether ISAAC
        # offers it as the energy calibration (CALIBRANT_RULE_ID: never a compound standard's own edge)
        "reference_proposed": proposed,
        "calibration_proposed": proposed and calibrant is None,
        "reference_statement": said,
        **({"reference_calibrant": dict(o["reference_calibrant"])} if isinstance(o.get("reference_calibrant"), Mapping) else {}),
    }


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


def would_apply(step: Mapping, element: str, edge: str, *, warn_eV: float | None = None) -> dict:
    """What approving ``element`` ``edge`` as this step's reference would do: ``shift_eV`` (tabulated - measured),
    ``shown``, ``needs_size_confirmation`` (|shift| above ``qc.warn_energy_shift_eV``), ``implausible`` (above
    ``calibration.max_plausible_shift_eV``: never applied), ``needs_calibrant_confirmation`` (a reference group's own
    edge whose sample is not named as a pure element, :data:`CALIBRANT_RULE_ID`: its size is confirmed whatever it is,
    so ``needs_size_confirmation`` is true too), ``statement``. ``shift_eV`` is null when no reference is proposed or
    the edge energy is unknown (``statement`` says why)."""
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
    implausible = abs(shift) > max_eV
    big = exceeds_warn(shift, warn) and not implausible
    calibrant = not_a_calibrant(step.get("outcome") or {}) if not implausible else None
    if calibrant is not None:
        # CALIBRANT_RULE_ID: said BEFORE the size sentence (a confirmed approval's reply keeps the text before it)
        said += (f" {not_proposed_sentence(calibrant)} Approving it moves this group's edge onto {element} {edge}'s "
                 "tabulated energy and erases the chemical shift it was measured to show: it is applied only when the "
                 f"scientist asks for it and also confirms its size (--accept-shift {shown(shift, warn)}), whatever "
                 "the size.")
    if implausible:
        said += (f" That is more than the protocol's {max_eV:g} eV plausible limit, so it would not be applied: "
                 f"check the element and edge.")
    elif big:
        said += (f" That is more than the protocol's {warn:g} eV warning level and moves every energy of the record "
                 f"(E0 included) by that much: it is applied only when you also confirm its size "
                 f"(--accept-shift {shown(shift, warn)}).")
    return {**out, "tabulated_edge_eV": tab, "tabulated_edge_source": src, "shift_eV": shift, "shown": shown(shift, warn),
            # the size is confirmed (--accept-shift) for a shift above the warning level, and for ANY shift of an
            # own edge that is not an energy calibrant
            "needs_size_confirmation": big or calibrant is not None, "needs_calibrant_confirmation": calibrant is not None,
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
    if not size_confirmed and judged and not r["reference_proposed"]:
        reason = (f"it was approved from a reference edge usable in {r['reference_scans_usable']} of "
                  f"{_n(r['reference_scans_listed'], 'scan')}, and an in-scan reference now needs one in at least "
                  f"{MIN_IN_SCAN_REFERENCE_SCANS} scans, so the current rules compute no shift")
    elif not size_confirmed and exceeds_warn(applied, warn):
        reason = (f"it is more than the protocol's {warn:g} eV warning level and its size was never confirmed "
                  "(an older build applied it without --accept-shift)")
    elif not size_confirmed and not_a_calibrant(o) is not None:
        reason = ("it calibrates on this group's own edge, whose sample is not named as a pure element, and its size "
                  f"was never confirmed ({CHEMICAL_STANDARD[0].lower() + CHEMICAL_STANDARD[1:]})")
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
    apply (flag :data:`TOO_FEW_FLAG` or :data:`SIZE_NOT_CONFIRMED_FLAG`), naming that approval; ``None`` otherwise."""
    o = step.get("outcome") or {}
    flags = set(step.get("flags") or ())
    ref = o.get("reference") or {}
    if ref.get("basis") != "scientist_decision" or not flags & {TOO_FEW_FLAG, SIZE_NOT_CONFIRMED_FLAG, CALIBRANT_NOT_CONFIRMED_FLAG}:
        return None
    named = (f"The calibration approval {ref.get('decision_id') or ''} ({ref.get('element')} {ref.get('edge')}, "
             f"by {ref.get('decided_by')})").replace("approval  (", "approval (")
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
        cal = not_a_calibrant(o) or {}
        return (f"{named} is not applied: it calibrates on this group's own edge, and {not_proposed_sentence(cal)} "
                f"The shift it gives, {said} eV, would move this group's edge onto "
                f"{ref.get('element')} {ref.get('edge')}'s tabulated energy and {why}, so this curve carries no "
                f"calibration shift. Approve again with --accept-shift {said} only if the scientist asks for that shift.")
    return (f"{named} is not applied: the shift it gives, {said} eV, is more than the protocol's {warn:g} eV warning "
            f"level and {why}, so this curve carries no calibration shift. Approve again with --accept-shift {said} "
            "if the scientist confirms that size.")
