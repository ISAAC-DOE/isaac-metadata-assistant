"""What a result's calibration step says about its energy reference, and what a named reference would do.
Stdlib only: read by processing (``run._calibration``), by ``bundle decide --decision approve_calibration``
(:mod:`..mutations`) and by ``bundle show processing-result``, from the stored step alone, so a result stored
before these sentences existed is read the same way.

Two rules (both in ``protocol.RULE_VERSIONS_SINCE_PROTOCOL_VERSION``, kept outside every hashed output file):

* :data:`IN_SCAN_MIN_RULE_ID` — an IN-SCAN reference channel is proposed only when its edge is usable (edge step /
  pre-edge noise at least ``calibration.reference_min_edge_snr``) in at least :data:`MIN_IN_SCAN_REFERENCE_SCANS`
  scans. One usable scan among many noisy ones is not a reference: its "edge" can be anywhere (measured on a real
  beamtime: 1 of 16 scans at signal-to-noise 10.5, the others 0.6-3.5, per-scan "edges" 4964.6-4985.5 eV).
* :data:`SHIFT_SIZE_RULE_ID` — an approved shift larger than ``qc.warn_energy_shift_eV`` is applied only when the
  scientist also confirmed its size (``--accept-shift``, matching the shift shown to 0.1 eV).
"""

from __future__ import annotations

import statistics
from typing import Any, Mapping

from .edges import edge_energy

MIN_IN_SCAN_REFERENCE_SCANS = 2
IN_SCAN_MIN_RULE_ID = "isaac.xas.in_scan_reference_min_scans.v0"
SHIFT_SIZE_RULE_ID = "isaac.xas.calibration_shift_size_confirmed.v0"
IN_SCAN = "in_scan_reference_channel"
TOO_FEW_FLAG = "reference_edge_in_too_few_scans"
SIZE_NOT_CONFIRMED_FLAG = "calibration_shift_size_not_confirmed"
#: the protocol's defaults, used only when a stored step does not carry its own value
DEFAULT_MIN_SNR = 10.0
DEFAULT_WARN_SHIFT_EV = 2.0
DEFAULT_MAX_SHIFT_EV = 25.0


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
    min_snr = float((step.get("params") or {}).get("reference_min_edge_snr") or DEFAULT_MIN_SNR)
    source = o.get("reference_source")
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


def shown(shift: float) -> str:
    """A shift as it is said and as ``--accept-shift`` takes it: signed, 0.1 eV (``-8.6``, ``+0.2``)."""
    v = round(float(shift), 1)
    return f"{'+' if v > 0 else ''}{v:.1f}" if v != 0 else "0.0"


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
    warn = float(DEFAULT_WARN_SHIFT_EV if warn_eV is None else warn_eV)
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
    said = (f"The reference edge sits {abs(gap):.1f} eV {side} {element} {edge}'s tabulated {tab:.1f} eV; "
            f"approving applies {shown(shift)} eV to this group's energy axis.")
    implausible = abs(shift) > max_eV
    big = abs(shift) > warn and not implausible
    if implausible:
        said += (f" That is more than the protocol's {max_eV:g} eV plausible limit, so it would not be applied: "
                 f"check the element and edge.")
    elif big:
        said += (f" That is more than the protocol's {warn:g} eV warning level and moves every energy of the record "
                 f"(E0 included) by that much: it is applied only when you also confirm its size "
                 f"(--accept-shift {shown(shift)}).")
    return {**out, "tabulated_edge_eV": tab, "tabulated_edge_source": src, "shift_eV": shift, "shown": shown(shift),
            "needs_size_confirmation": big, "implausible": implausible, "statement": said}
