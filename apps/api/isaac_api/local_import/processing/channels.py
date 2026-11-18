"""Choose the energy, signal and I0 columns of a group's scans. Stdlib only.

The choice is always RECORDED with its basis and the alternatives, and always needs
review. For BL15-2 HERFD the bundle carries ``bl15/signals.py``'s own proposal
(``run.signal_selection``); when it proposes a channel that the scan has, it is used.
Otherwise common channel names are matched in the protocol's priority order, preferring
transmission for reference/alignment groups and fluorescence for samples. When transmission is
not positive in every scan of a group, :mod:`.run` takes the next alternative
(``exclude_modes``), flagged ``channel_fallback_transmission_not_positive``.
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


#: Whole-token words that name TIME. A column so named is never taken as the energy axis by
#: value shape: measured on a real BL15-2 motor (alignment) scan, ``Epoch`` is monotonic and
#: lies inside the energy value range, so the shape rule alone would have called it energy.
TIME_WORDS = frozenset({"epoch", "time", "sec", "secs", "second", "seconds", "timestamp", "clock"})
_LABEL_TOKEN = re.compile(r"[^0-9a-z]+")


def names_time(label: str) -> bool:
    """True when a whole token of ``label`` (case-insensitive) is a time word."""
    return any(t in TIME_WORDS for t in _LABEL_TOKEN.split(label.casefold()) if t)


def _energy_by_shape(table: ScanTable, lo: float, hi: float) -> str | None:
    for name in table.labels:
        if names_time(name):
            continue
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


def dead_candidates(table: ScanTable, *, params: Mapping) -> list[str]:
    """Signal-side candidate columns (I0, transmission, fluorescence names and ``sum:``
    family members) that the scan HAS but that are not live — present and rejected. When no
    channel forms, these make it a data-quality failure, not "the protocol does not apply"."""
    cp = params["channels"]
    names: list[str] = []
    for cand in [*cp["i0_candidates"], *cp["transmission_after_sample"], *cp["fluorescence_candidates"]]:
        names.extend(_family(table, cand[4:]) if cand.startswith("sum:") else [cand])
    seen: list[str] = []
    for c in names:
        if table.has(c) and not _live(table.columns[c]) and c not in seen:
            seen.append(c)
    return seen


def choose_channels(
    table: ScanTable,
    *,
    params: Mapping,
    role: str = "sample",
    bl15_selection: Mapping | None = None,
    exclude_modes: Sequence[str] = (),
    bl15_2: str | None = None,
    bl15_2_hint: str | None = None,
) -> ChannelChoice:
    """``exclude_modes``: modes NOT taken (still listed as alternatives) — the fallback when a
    group's transmission channel is not positive in any scan (:mod:`.run`).

    :data:`BL15_2_ENERGY_RULE_ID` (pq-001): a scan with ``channels.bl15_2_energy_column`` (``absev``) is ALWAYS read
    on it, whatever the beamline. ``bl15_2``: why this scan is KNOWN to be a BL15-2 scan (a scientist's beamline
    answer, or an unambiguous fingerprint; ``None`` when it is not known): a scan without ``absev`` then has no
    energy column (flag :data:`BL15_2_ENERGY_MISSING_FLAG`), never another one. ``bl15_2_hint``: why this scan MAY be
    a BL15-2 scan when that is not known (a fingerprint shared with another beamline, a folder name naming another
    one): a scan without ``absev`` is read on the usual energy column and flagged
    :data:`BL15_2_BEAMLINE_UNCONFIRMED_FLAG` for the scientist to confirm the beamline."""
    cp = params["channels"]
    flags: list[str] = []
    present = [c for c in cp["energy_candidates"] if table.has(c)]
    energy = present[0] if present else None
    if len(present) > 1:
        flags.append("energy_column_alternatives")
    bl15_col = cp.get("bl15_2_energy_column")
    bl15_missing = bl15_unconfirmed = bl15_moved = False
    if bl15_col and table.has(bl15_col):
        # absev, when a scan has it, is always the right axis (pq-001)
        bl15_moved = energy != bl15_col
        energy = bl15_col
        present = [bl15_col] + [c for c in present if c != bl15_col]
    elif bl15_col and bl15_2:
        energy, bl15_missing = None, True
        flags.append(BL15_2_ENERGY_MISSING_FLAG)
    elif bl15_col and bl15_2_hint:
        bl15_unconfirmed = True
        flags.append(BL15_2_BEAMLINE_UNCONFIRMED_FLAG)
    if energy is None and not bl15_missing:
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
        for mode in (m for m in order if m not in exclude_modes):
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
    if bl15_col and (bl15_2 or bl15_unconfirmed or bl15_moved):
        # set after the signal choice, which may replace the basis (the BL15-2 selector's proposal). Absent for a scan
        # read on absev as it always was, with no beamline hint (no result id moves)
        choice.basis["energy_rule"] = {
            "rule_id": BL15_2_ENERGY_RULE_ID, "column": bl15_col,
            **({"bl15_2_basis": bl15_2} if bl15_2 else {}),
            **({"missing": True, "statement": bl15_2_missing_statement(bl15_col, bl15_2)} if bl15_missing else {}),
            **({"beamline_unconfirmed": bl15_2_hint, "used": energy} if bl15_unconfirmed else {})}
    if len(alternatives) > 1:
        flags.append("multiple_signal_alternatives")
    if choice.mode is None:
        flags.append("no_signal_channel_found")
    if energy is None:
        flags.append("no_energy_column_found")
    choice.flags = flags
    return choice


#: pq-001 (beamline scientist answers relayed by Krish, 17 Nov 2026): a BL15-2 scan's energy axis is always ``absev``
BL15_2_ENERGY_RULE_ID = "isaac.xas.bl15_2_energy_is_absev.v0"
BL15_2_ENERGY_MISSING_FLAG = "bl15_2_energy_column_missing"
#: a scan with no absev whose beamline MAY be BL15-2 but is not known: read on its usual energy column, flagged
BL15_2_BEAMLINE_UNCONFIRMED_FLAG = "absev_missing_beamline_unconfirmed"


def bl15_2_missing_statement(column: str, basis: str) -> str:
    return (f"This is a BL15-2 scan ({basis}), whose energy axis is always the '{column}' column (beamline scientist "
            f"answers relayed by Krish, 17 Nov 2026), and it has no '{column}' column. It is not read on another energy "
            "column; a person checks the file.")


def bl15_2_unconfirmed_statement(column: str, files: Sequence[str], used: str | None, hint: str) -> str:
    """The plain sentence for flag :data:`BL15_2_BEAMLINE_UNCONFIRMED_FLAG`: which scans have no absev, what they were
    read on, and that the beamline needs confirming."""
    names = ", ".join(files[:10]) + (f" and {len(files) - 10} more" if len(files) > 10 else "")
    one = len(files) == 1
    return (f"{'This scan has' if one else f'{len(files)} scans have'} no '{column}' column ({names}); if this is "
            f"BL15-2 data, '{column}' is required (beamline scientist answers relayed by Krish, 17 Nov 2026) — confirm "
            f"the beamline. The beamline is not known: {hint}. {'It was' if one else 'They were'} read on "
            f"'{used or 'no energy column'}', so the curve needs review before it is approved.")


def needs_review_statement(choice: ChannelChoice) -> str:
    """r4-a L6: the plain sentence for flag ``channel_choice_needs_review``: the channel was chosen by the protocol's
    column-name priority (``channels.*_candidates``), not by the BL15-2 selector's proposal, so nothing in the data
    confirms it is the channel the scientist used. Names the channel, the rule, why the selector was not used and the
    other channels the scan has."""
    basis = choice.basis or {}
    if basis.get("rule"):
        how = f"the rule '{basis['rule']}'"
    elif basis.get("candidate"):
        how = f"the first fluorescence name present, '{basis['candidate']}'"
    else:
        how = "the protocol's order of column names"
    said = (f"ISAAC chose the {choice.mode or 'signal'} channel {choice.signal_name or '(none)'} by column name ({how}), "
            "not from a reading of the data")
    if basis.get("bl15_signal_selection_not_used"):
        said += f"; the BL15-2 signal selector did not propose one it could use ({basis['bl15_signal_selection_not_used']})"
    others = [a for a in choice.alternatives
              if not (a.get("mode") == choice.mode and list(a.get("columns") or ()) == list(choice.signal_columns))
              and not (a.get("mode") == MODE_TRANSMISSION and choice.mode == MODE_TRANSMISSION)]
    if others:
        listed = ", ".join(f"{a.get('mode')} {'+'.join(a.get('columns') or ())}" for a in others[:5])
        said += f". The scan also has: {listed}{' and more' if len(others) > 5 else ''}"
    return (said + ". A person confirms this is the channel the measurement used; another is chosen only on the "
            "scientist's word, with a params file (channels.fluorescence_candidates or channels.transmission_after_sample).")

