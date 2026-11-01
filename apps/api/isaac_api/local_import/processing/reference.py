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
"""

from __future__ import annotations

import statistics
from typing import Any, Mapping

from .edges import edge_energy

MIN_IN_SCAN_REFERENCE_SCANS = 2
IN_SCAN_MIN_RULE_ID = "isaac.xas.in_scan_reference_min_scans.v0"
SHIFT_SIZE_RULE_ID = "isaac.xas.calibration_shift_size_confirmed.v0"
STRICTER_ONLY_RULE_ID = "isaac.xas.calibration_overrides_stricter_only.v0"
IN_SCAN = "in_scan_reference_channel"
TOO_FEW_FLAG = "reference_edge_in_too_few_scans"
SIZE_NOT_CONFIRMED_FLAG = "calibration_shift_size_not_confirmed"
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


def reading(step: Mapping) -> dict:
    """The reference a calibration step read: ``reference_source``, ``reference_scans_usable`` / ``_listed``,
    ``measured_reference_e0_eV`` (median of the usable scans), ``reference_e0_spread_eV`` (null with fewer than two
    usable scans: one scan has no spread), ``reference_proposed`` and ``reference_statement`` (one plain sentence)."""
    o = step.get("outcome") or {}
    source = o.get("reference_source")
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
                + (f" (spread {spread:.2f} eV)." if spread is not None else ".")
                + " Naming its element and edge gives the shift: the tabulated edge minus this energy.")
    return {
        "reference_source": source,
        "reference_scans_usable": len(usable),
        "reference_scans_listed": listed,
        "reference_min_scans": need if source is not None else None,
        "measured_reference_e0_eV": measured,
        "reference_e0_spread_eV": spread,
        "reference_proposed": proposed,
        "reference_statement": said,
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
    ``calibration.max_plausible_shift_eV``: never applied), ``statement``. ``shift_eV`` is null when no reference is
    proposed or the edge energy is unknown (``statement`` says why)."""
    r = reading(step)
    warn = effective_warn_eV(warn_eV)
    max_eV = float((step.get("params") or {}).get("max_plausible_shift_eV") or DEFAULT_MAX_SHIFT_EV)
    out = {"element": element, "edge": edge, "tabulated_edge_eV": None, "tabulated_edge_source": None,
           "measured_reference_e0_eV": r["measured_reference_e0_eV"], "shift_eV": None, "shown": None,
           "warn_energy_shift_eV": warn, "needs_size_confirmation": False, "implausible": False}
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
    if implausible:
        said += (f" That is more than the protocol's {max_eV:g} eV plausible limit, so it would not be applied: "
                 f"check the element and edge.")
    elif big:
        said += (f" That is more than the protocol's {warn:g} eV warning level and moves every energy of the record "
                 f"(E0 included) by that much: it is applied only when you also confirm its size "
                 f"(--accept-shift {shown(shift, warn)}).")
    return {**out, "tabulated_edge_eV": tab, "tabulated_edge_source": src, "shift_eV": shift, "shown": shown(shift, warn),
            "needs_size_confirmation": big, "implausible": implausible, "statement": said}


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
    if ref.get("basis") != "scientist_decision" or not flags & {TOO_FEW_FLAG, SIZE_NOT_CONFIRMED_FLAG}:
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
    return (f"{named} is not applied: the shift it gives, {said} eV, is more than the protocol's {warn:g} eV warning "
            f"level and {why}, so this curve carries no calibration shift. Approve again with --accept-shift {said} "
            "if the scientist confirms that size.")
