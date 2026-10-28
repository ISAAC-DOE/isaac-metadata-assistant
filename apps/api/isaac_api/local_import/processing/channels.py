"""Choose the energy, signal and I0 columns of a group's scans. Stdlib only.

The choice is always RECORDED with its basis and the alternatives, and always needs
review. For BL15-2 HERFD the bundle carries ``bl15/signals.py``'s own proposal
(``run.signal_selection``); when it proposes a channel that the scan has, it is used.
Otherwise common channel names are matched in the protocol's priority order, preferring
transmission for reference/alignment groups and fluorescence for samples.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence

from .readers import ScanTable

MODE_FLUORESCENCE = "fluorescence"  # mu = signal / I0
MODE_TRANSMISSION = "transmission"  # mu = ln(I0 / I1)
MODE_SIGNAL_ONLY = "signal_only"  # mu = signal (no I0 found)


@dataclass
class ChannelChoice:
    energy: str | None
    mode: str | None
    signal_columns: list[str] = field(default_factory=list)
    i0: str | None = None
    transmission_after: str | None = None
    reference_pair: list[str] | None = None
    basis: dict = field(default_factory=dict)
    alternatives: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def signal_name(self) -> str | None:
        if self.mode == MODE_TRANSMISSION:
            return f"ln({self.i0}/{self.transmission_after})"
        if not self.signal_columns:
            return None
        sig = "+".join(self.signal_columns)
        return f"({sig})/{self.i0}" if self.mode == MODE_FLUORESCENCE else sig

    def to_state(self) -> dict:
        d = asdict(self)
        d["signal_name"] = self.signal_name
        return d


def _live(values: Sequence[float]) -> bool:
    nonzero = sum(1 for v in values if v == v and v != 0)
    return bool(values) and nonzero >= max(1, len(values) // 2)


def _total(values: Sequence[float]) -> float:
    return float(sum(abs(v) for v in values if v == v))


def _family(table: ScanTable, prefix: str) -> list[str]:
    pat = re.compile(r"^" + re.escape(prefix) + r"\d+$")
    return [c for c in table.labels if pat.match(c)]


def _energy_by_shape(table: ScanTable, lo: float, hi: float) -> str | None:
    for name in table.labels:
        vals = table.columns[name]
        if len(vals) < 5:
            continue
        if all(lo <= v <= hi for v in vals) and sum(1 for a, b in zip(vals, vals[1:]) if b > a) >= 0.9 * (len(vals) - 1):
            return name
    return None


def _fluorescence_options(table: ScanTable, candidates: Sequence[str]) -> list[dict]:
    out = []
    for cand in candidates:
        if cand.startswith("sum:"):
            fam = _family(table, cand[4:])
            live = [c for c in fam if _live(table.columns[c])]
            if live:
                out.append(
                    {
                        "candidate": cand,
                        "columns": live,
                        "dead_columns": [c for c in fam if c not in live],
                        "total": sum(_total(table.columns[c]) for c in live),
                    }
                )
        elif table.has(cand) and _live(table.columns[cand]):
            out.append({"candidate": cand, "columns": [cand], "dead_columns": [], "total": _total(table.columns[cand])})
    return out


def choose_channels(
    table: ScanTable,
    *,
    params: Mapping,
    role: str = "sample",
    bl15_selection: Mapping | None = None,
) -> ChannelChoice:
    cp = params["channels"]
    flags: list[str] = []
    present = [c for c in cp["energy_candidates"] if table.has(c)]
    energy = present[0] if present else None
    if len(present) > 1:
        flags.append("energy_column_alternatives")
    if energy is None:
        lo, hi = cp["energy_value_range_eV"]
        energy = _energy_by_shape(table, lo, hi)
        if energy is not None:
            flags.append("energy_column_by_value_shape")
    i0 = next((c for c in cp["i0_candidates"] if table.has(c) and _live(table.columns[c])), None)
    if i0 is None:
        flags.append("i0_missing")
    after = next((c for c in cp["transmission_after_sample"] if table.has(c) and _live(table.columns[c])), None)
    ref_after = next((c for c in cp["reference_after_reference"] if table.has(c) and _live(table.columns[c])), None)
    reference_pair = [after, ref_after] if after and ref_after else None

    fluor = _fluorescence_options(table, cp["fluorescence_candidates"])
    alternatives = [
        {"mode": MODE_FLUORESCENCE, "columns": f["columns"], "candidate": f["candidate"], "total": f["total"]} for f in fluor
    ]
    if i0 and after:
        alternatives.append({"mode": MODE_TRANSMISSION, "columns": [i0, after], "candidate": "transmission"})

    choice = ChannelChoice(energy=energy, mode=None, i0=i0, reference_pair=reference_pair, alternatives=alternatives)
    choice.basis["energy_alternatives"] = present[1:]

    sel = bl15_selection or {}
    primary = sel.get("primary_channel")
    if cp.get("use_bl15_signal_selection") and sel.get("status") == "proposed" and primary and table.has(primary):
        choice.mode = MODE_FLUORESCENCE if i0 else MODE_SIGNAL_ONLY
        choice.signal_columns = [primary]
        choice.basis = {
            "basis": "bl15_signal_selection",
            "selector_id": sel.get("selector_id"),
            "reason_code": sel.get("reason_code"),
            "status": sel.get("status"),
        }
        flags.append("channel_from_bl15_selector_suggestion")
    else:
        if sel.get("selector_id"):
            choice.basis["bl15_signal_selection_not_used"] = sel.get("reason_code") or sel.get("status")
        order = [MODE_TRANSMISSION, MODE_FLUORESCENCE] if role in ("reference", "alignment") else [MODE_FLUORESCENCE, MODE_TRANSMISSION]
        for mode in order:
            if mode == MODE_TRANSMISSION and i0 and after:
                choice.mode = MODE_TRANSMISSION
                choice.transmission_after = after
                choice.basis.update({"basis": "channel_name_priority", "rule": f"{role}: transmission first" if order[0] == mode else "fallback"})
                break
            if mode == MODE_FLUORESCENCE and fluor:
                f = fluor[0]
                choice.mode = MODE_FLUORESCENCE if i0 else MODE_SIGNAL_ONLY
                choice.signal_columns = list(f["columns"])
                choice.basis.update({"basis": "channel_name_priority", "candidate": f["candidate"], "dead_columns_excluded": f["dead_columns"]})
                if f["dead_columns"]:
                    flags.append("dead_detector_elements_excluded")
                break
        flags.append("channel_choice_needs_review")
    dt = cp.get("dead_time_rate_prefix")
    if dt and choice.mode == MODE_FLUORESCENCE and _family(table, dt):
        # Input-count-rate columns exist (XDAC ICR1_n): a dead-time correction is possible
        # but no rule for it is approved, so none is applied — flagged for the scientist.
        flags.append("dead_time_correction_not_applied")
        choice.basis["dead_time_rate_columns"] = _family(table, dt)
    if len(alternatives) > 1:
        flags.append("multiple_signal_alternatives")
    if choice.mode is None:
        flags.append("no_signal_channel_found")
    if energy is None:
        flags.append("no_energy_column_found")
    choice.flags = flags
    return choice
