"""The numeric steps of ``isaac.xas.v0``: per-scan mu, calibration E0, deglitch, merge,
normalise, QC. numpy + xraylarch, passed in (imported lazily by the caller).

Nothing here DROPS data unless ``deglitch.exclude_flagged`` is true; flagged points and
scans are reported as what WOULD be excluded.
"""

from __future__ import annotations

import math
import warnings
from typing import Any, Mapping, Sequence

from .channels import MODE_FLUORESCENCE, MODE_SIGNAL_ONLY, MODE_TRANSMISSION, ChannelChoice
from .readers import ScanTable


class StepError(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# --- per scan --------------------------------------------------------------------------------


def scan_arrays(table: ScanTable, choice: ChannelChoice, np) -> dict:
    """Energy-sorted, duplicate-merged, finite (energy, mu[, mu_ref]) for one scan + diagnostics.

    Also, for the scan-selection proposal only (:func:`scan_selection`; never written to a hashed file): ``counts``
    (the raw chosen signal), ``i0`` and ``ring`` (the ring current, :data:`RING_CURRENT_COLUMNS`, or ``None``), on the
    same points as ``energy``."""
    missing = [c for c in [choice.energy, *choice.signal_columns, choice.i0 if choice.mode != MODE_SIGNAL_ONLY else None, choice.transmission_after] if c and not table.has(c)]
    if missing:
        raise StepError("scan_lacks_chosen_columns", ",".join(missing))
    E = np.asarray(table.columns[choice.energy], dtype=float)
    diag: dict = {"points_read": int(E.size)}
    with np.errstate(divide="ignore", invalid="ignore"):
        i0 = np.asarray(table.columns[choice.i0], dtype=float) if choice.i0 else None
        if choice.mode == MODE_TRANSMISSION:
            it = np.asarray(table.columns[choice.transmission_after], dtype=float)
            raw_signal = it
            mu = np.where((i0 > 0) & (it > 0), np.log(i0 / it), np.nan)
        elif choice.mode in (MODE_FLUORESCENCE, MODE_SIGNAL_ONLY):
            raw_signal = np.sum([np.asarray(table.columns[c], dtype=float) for c in choice.signal_columns], axis=0)
            mu = raw_signal / i0 if (choice.mode == MODE_FLUORESCENCE and i0 is not None) else raw_signal.copy()
            if choice.mode == MODE_FLUORESCENCE:
                mu = np.where(i0 > 0, mu, np.nan)
        else:
            raise StepError("no_signal_channel")
        mu_ref = None
        if choice.reference_pair and all(table.has(c) for c in choice.reference_pair):
            a = np.asarray(table.columns[choice.reference_pair[0]], dtype=float)
            b = np.asarray(table.columns[choice.reference_pair[1]], dtype=float)
            mu_ref = np.where((a > 0) & (b > 0), np.log(a / b), np.nan)

    diag["i0_nonpositive"] = int(np.sum(i0 <= 0)) if i0 is not None else None
    # Saturation: the longest run of consecutive identical values AT the signal maximum.
    run = best = 0
    if raw_signal.size and np.isfinite(raw_signal).any():
        mx = np.nanmax(raw_signal)
        for v in raw_signal:
            run = run + 1 if (v == mx and mx > 0) else 0
            best = max(best, run)
    diag["signal_max_run"] = int(best)
    diag["signal_all_zero"] = bool(raw_signal.size and not np.any(raw_signal != 0))
    # c11-r: how many points of the chosen signal are EXACTLY zero (threshold-free; no point is changed or dropped
    # for it): a scan whose counts stop part-way (the beam lost) is merged as it is, and said (run.py)
    diag["signal_zero_points"] = int(np.sum(raw_signal == 0))

    ring_col = next((c for c in RING_CURRENT_COLUMNS if table.has(c)), None)
    ring = np.asarray(table.columns[ring_col], dtype=float) if ring_col else None
    steps = np.diff(E)
    diag["nonmonotonic_steps"] = int(np.sum(steps <= 0))
    order = np.argsort(E, kind="stable")
    E, mu = E[order], mu[order]
    raw_kept = raw_signal[order]
    i0_kept = i0[order] if i0 is not None else None
    ring_kept = ring[order] if ring is not None else None
    mu_ref = mu_ref[order] if mu_ref is not None else None
    finite = np.isfinite(E) & np.isfinite(mu)
    diag["nonfinite_dropped"] = int(np.sum(~finite))
    E, mu = E[finite], mu[finite]
    raw_kept = raw_kept[finite]
    i0_kept = i0_kept[finite] if i0_kept is not None else None
    ring_kept = ring_kept[finite] if ring_kept is not None else None
    mu_ref = mu_ref[finite] if mu_ref is not None else None
    key = np.round(E, 6)
    uniq, inverse, counts = np.unique(key, return_inverse=True, return_counts=True)
    diag["duplicate_energies_merged"] = int(np.sum(counts > 1))
    # per kept point: the signal is exactly zero there (a merged duplicate energy only when every reading is)
    signal_zero = raw_kept == 0
    sig_counts = raw_kept
    if uniq.size != E.size:
        signal_zero = np.bincount(inverse, weights=(raw_kept != 0).astype(float), minlength=uniq.size) == 0
        mu = np.bincount(inverse, weights=mu) / counts
        # summed over the readings of one energy (counts stay counts; I0 and the ring current likewise summed /
        # averaged), so counts / I0 is still the merged mu
        sig_counts = np.bincount(inverse, weights=np.nan_to_num(raw_kept))
        i0_kept = np.bincount(inverse, weights=np.nan_to_num(i0_kept)) if i0_kept is not None else None
        ring_kept = np.bincount(inverse, weights=np.nan_to_num(ring_kept)) / counts if ring_kept is not None else None
        if mu_ref is not None:
            ok = np.isfinite(mu_ref)
            num = np.bincount(inverse, weights=np.where(ok, mu_ref, 0.0))
            den = np.bincount(inverse, weights=ok.astype(float))
            mu_ref = np.where(den > 0, num / np.maximum(den, 1), np.nan)
        E = uniq
    diag["points_used"] = int(E.size)
    return {"energy": E, "mu": mu, "mu_ref": mu_ref, "signal_zero": signal_zero, "diagnostics": diag,
            "counts": sig_counts, "i0": i0_kept, "ring": ring_kept}


#: A scan with fewer usable points than this is skipped.
MIN_SCAN_POINTS = 5
SIGNAL_NOT_FINITE = "signal_not_finite"
#: A scan whose chosen signal is zero at every point (c11-a): skipped, counted and named, never merged.
SIGNAL_ALL_ZERO = "signal_all_zero"
#: The rule that skips such a scan (``protocol.RULE_VERSIONS_SINCE_PROTOCOL_VERSION`` names it).
SIGNAL_ALL_ZERO_RULE_ID = "isaac.xas.skip_signal_all_zero.v0"


def unusable_reason(sa: Mapping) -> str | None:
    """Why a scan's arrays (:func:`scan_arrays`) cannot be used, or ``None``.

    ``signal_not_finite`` when the scan HAS the points but its chosen signal is non-finite at
    too many of them (I0 or I1 not positive): measured on a real BL4-3 dilute standard, I1 is
    negative at all 303 points, so ln(I0/I1) dropped every one — that is not ``too_few_points``.

    ``signal_all_zero`` (c11-a) when the scan has the points but its chosen signal is zero at every one: measured
    on a real BL15-2 beamtime, the last of 8 scans recorded no counts, and merging it pulled the mean down to 0 at
    the end of the curve. Only a scan that would otherwise be used is given this reason (a scan already unusable
    keeps its reason, so no other result moves).
    """
    if sa["energy"].size >= MIN_SCAN_POINTS:
        return SIGNAL_ALL_ZERO if sa["diagnostics"].get("signal_all_zero") else None
    d = sa["diagnostics"]
    if d["nonfinite_dropped"] and d["points_read"] >= MIN_SCAN_POINTS:
        return SIGNAL_NOT_FINITE
    return "too_few_points"


# --- calibration ---------------------------------------------------------------------------


def edge_e0(energy, mu, np, larch_xafs) -> dict | None:
    """E0 (max of the first derivative, larch ``find_e0``) and an edge SNR, or None."""
    ok = np.isfinite(mu)
    if np.sum(ok) < 10:
        return None
    e, m = energy[ok], mu[ok]
    try:
        from larch import Group

        g = Group()
        larch_xafs.pre_edge(e, m, group=g)
        e0 = _f(larch_xafs.find_e0(e, m))
        step = _f(g.edge_step)
        lo, hi = g.e0 + g.pre_edge_details.pre1, g.e0 + g.pre_edge_details.pre2
        sel = (e >= lo) & (e <= hi)
        noise = float(np.std((m - g.pre_edge)[sel])) if np.sum(sel) >= 3 else None
    except Exception:  # noqa: BLE001 - a channel with no edge is "no reference", not an error
        return None
    snr = (abs(step) / noise) if (step is not None and noise) else None
    return {"e0_eV": e0, "edge_step": step, "snr": _f(snr)}


# --- grid, deglitch, merge --------------------------------------------------------------------


def common_grid(scans: Sequence[Mapping], np, *, truncated_fraction: float = 0.9):
    """The merge grid: the energy points of the scan spanning the widest range (first such).

    Every scan contributes only inside its OWN range (no extrapolation): a truncated or
    aborted scan is kept where it has data and counted per point (``n`` in merged.csv),
    instead of shrinking the whole group's grid to its range. Measured on a real BL15-2
    beamtime: one scan ending at the edge had cut a group's grid to below E0.
    """
    spans = [float(s["energy"][-1] - s["energy"][0]) for s in scans]
    base_pos = int(max(range(len(scans)), key=lambda i: (spans[i], -i)))
    grid = scans[base_pos]["energy"]
    if grid.size < 2:
        raise StepError("no_common_energy_overlap", "grid has fewer than 2 points")
    full = float(grid[-1] - grid[0]) or 1.0
    truncated = [i for i, sp in enumerate(spans) if sp < truncated_fraction * full]
    lo = max(float(s["energy"][0]) for s in scans)
    hi = min(float(s["energy"][-1]) for s in scans)
    return grid, {
        "grid_from_scan_position": base_pos,
        "grid_eV": [float(grid[0]), float(grid[-1])],
        "all_scans_overlap_eV": [lo, hi] if hi > lo else None,
        "truncated_scan_positions": truncated,
        "truncated_fraction": truncated_fraction,
    }


def interpolate(scans: Sequence[Mapping], grid, np, key: str = "mu"):
    """Linear interpolation of each scan onto ``grid``; NaN outside the scan's own range."""
    rows = []
    for s in scans:
        y = np.interp(grid, s["energy"], s[key])
        y[(grid < s["energy"][0]) | (grid > s["energy"][-1])] = np.nan
        rows.append(y)
    return np.vstack(rows)


def _mad_scale(r, np, floor: float) -> float:
    r = r[np.isfinite(r)]
    if r.size == 0:
        return max(floor, 1e-300)
    med = np.median(r)
    s = 1.4826 * float(np.median(np.abs(r - med)))
    return max(s, floor, 1e-300)


def deglitch(M, grid, params: Mapping, np) -> dict:
    """Flag glitch points and outlier scans. Returns masks; never modifies ``M``.

    * >= ``min_scans_for_cross_scan`` scans: each scan is fitted to the per-point median
      spectrum as ``a + b*median`` (absorbs I0/gain scaling); a point is flagged when its
      residual exceeds ``k`` robust scales, the scale being the LARGER of (i) the scan's
      residual MAD over energy and (ii) the across-scan MAD at that energy — so points where
      every scan legitimately differs (the steep edge under sub-eV energy jitter) are not
      flagged, and a spike in one scan is.
    * fewer scans: leave-one-out against the straight line through the two neighbours,
      scaled by the scan's residual MAD.
    """
    p = params["deglitch"]
    k = float(p["point_z_threshold"])
    n, npts = M.shape
    point_flags = np.zeros_like(M, dtype=bool)
    zmax = np.zeros(n)
    scan_rms: list = [None] * n
    finite = np.isfinite(M)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        if n >= int(p["min_scans_for_cross_scan"]):
            method = "cross_scan_median"
            med = np.nanmedian(M, axis=0)
            R = np.full_like(M, np.nan)
            for s in range(n):
                ok = finite[s] & np.isfinite(med)
                if ok.sum() < 3:
                    continue
                A = np.vstack([np.ones(int(ok.sum())), med[ok]]).T
                coef, *_ = np.linalg.lstsq(A, M[s][ok], rcond=None)
                R[s, ok] = M[s][ok] - A @ coef
            across = 1.4826 * np.nanmedian(np.abs(R - np.nanmedian(R, axis=0)), axis=0)
            span = float(np.nanmax(med) - np.nanmin(med)) or 1.0
            for s in range(n):
                r = R[s]
                if not np.isfinite(r).any():
                    continue
                own = _mad_scale(r, np, 1e-4 * span)
                scale = np.maximum(np.nan_to_num(across, nan=0.0), own)
                z = (r - np.nanmedian(r)) / scale
                point_flags[s] = np.nan_to_num(np.abs(z), nan=0.0) > k
                zmax[s] = float(np.nanmax(np.abs(z)))
                scan_rms[s] = float(np.sqrt(np.nanmean(r**2)) / span)
            vals = [x for x in scan_rms if x is not None]
            med_rms = float(np.median(vals)) if vals else 0.0
            scan_flags = [
                bool(x is not None and x > float(p["scan_rms_ratio_threshold"]) * med_rms and x > float(p["scan_rms_floor"]))
                for x in scan_rms
            ]
        else:
            method = "local_neighbour_interpolation"
            for s in range(n):
                ok = finite[s]
                idx = np.nonzero(ok)[0]
                if idx.size < 5:
                    continue
                e, m = grid[idx], M[s][idx]
                pred = m[:-2] + (m[2:] - m[:-2]) * (e[1:-1] - e[:-2]) / (e[2:] - e[:-2])
                r = m[1:-1] - pred
                span = float(np.ptp(m)) or 1.0
                z = (r - np.median(r)) / _mad_scale(r, np, 1e-4 * span)
                point_flags[s, idx[1:-1]] = np.abs(z) > k
                zmax[s] = float(np.max(np.abs(z)))
            scan_flags = [False] * n
    listed = []
    for s, i in zip(*np.nonzero(point_flags)):
        if len(listed) >= int(p["max_listed_points"]):
            break
        listed.append({"scan_position": int(s), "energy_eV": float(grid[i])})
    return {
        "method": method,
        "point_flags": point_flags,
        "scan_flags": scan_flags,
        "scan_rms": scan_rms,
        "max_abs_z": [float(x) for x in zmax],
        "flagged_points_total": int(point_flags.sum()),
        "flagged_points_listed": listed,
    }


#: r2-a: a flagged point within this many eV of E0, or where the merged curve is steep, is on the edge: the glitch
#: check cannot tell a glitch from the edge there (a sub-eV energy jitter between scans moves the steepest points by
#: many robust scales). Measured on a real Pt L3 HERFD beamtime: with 4-5 scans the flagged points sat at E0 and on
#: the white line, and 27 groups carried ``glitches_flagged``. NOT a protocol parameter: params.json is hashed into
#: every result id, so the rule lives here and is said beside the count (the stored count and verdict are unchanged).
#: r4-a: v1 — a flagged point from ONE scan far beyond the others at its energy is never on the edge
#: (:func:`glitch_points_from_one_scan`)
GLITCH_EDGE_RULE_ID = "isaac.xas.glitch_points_on_edge.v1"
GLITCH_EDGE_WINDOW_EV = 5.0
#: ...or where the merged curve's slope is at least this fraction of its steepest slope
GLITCH_EDGE_STEEP_FRACTION = 0.25
#: the slope at a point is taken between the points this many places either side, never through the point itself,
#: so a one-point spike does not make its own slope steep
GLITCH_EDGE_SLOPE_HALF_WIDTH = 2


#: r4-a: a flagged point is from ONE scan alone when, with each scan put on the median spectrum's scale first
#: (``a + b*median`` fitted to its unflagged points, as :func:`deglitch` does, so a gain step is not a departure), its
#: residual is more than this many times every other scan's residual there...
GLITCH_ONE_SCAN_FACTOR = 10.0
#: ...and more than this fraction of the median curve's whole range (an energy jitter on the steep edge moves a point
#: by a fraction of the edge's height; a spike that becomes the white line moves it by many times the height)...
GLITCH_ONE_SCAN_SPAN_FRACTION = 0.5
#: ...and, on the median's scale, it lies outside the median curve's own range (above its maximum or below its
#: minimum) by more than this many times that range: a white line that grows in situ, or is damped by
#: self-absorption, stays inside it (a white line 2.5 times as tall reaches about 1 range above), a spike does not.
#: Measured on a real BL15-2 Ir L3 HERFD beamtime: one scan of five read about 28 where the others read about 0.01;
#: 15 of its 22 flagged points lay on the edge and were "unjudged", and the merge's white line and E0 came from it.
GLITCH_ONE_SCAN_ENVELOPE_SPANS = 2.0
#: a median curve, or the other scans' mean, "has an edge" when its range, with a straight line taken out, is at least
#: this many times its point-to-point noise (dead, dark or out-of-beam scans have none)
HAS_EDGE_MIN_NOISE_MULTIPLE = 10.0


def has_edge(y, grid, np) -> bool:
    """r4-a: ``y`` (on ``grid``) rises or falls by at least :data:`HAS_EDGE_MIN_NOISE_MULTIPLE` times its own
    point-to-point noise once a straight line is taken out: a spectrum, not dark counts, scatter or a dead channel."""
    ok = np.isfinite(y) & np.isfinite(grid)
    if int(ok.sum()) < 5:
        return False
    e, v = grid[ok], y[ok]
    resid = v - np.polyval(np.polyfit(e, v, 1), e)
    d = np.diff(v)
    noise = 1.4826 * float(np.median(np.abs(d - np.median(d))))
    if noise <= 0:
        noise = float(np.std(d))
    noise /= math.sqrt(2.0)
    span = float(np.ptp(resid))
    return span > 0 and (noise <= 0 or span >= HAS_EDGE_MIN_NOISE_MULTIPLE * noise)


def glitch_points_from_one_scan(point_flags, grid, M, np) -> set[tuple[int, float]]:
    """r4-a: the flagged points (``(scan_position, energy_eV)``) that are ONE scan's glitch, never the edge: on the
    median spectrum's scale (each scan's ``a + b*median`` fitted to its unflagged points), the scan's residual there is
    far beyond every other scan's (:data:`GLITCH_ONE_SCAN_FACTOR`), more than :data:`GLITCH_ONE_SCAN_SPAN_FRACTION` of
    the median curve's range, and outside that curve's own range by more than :data:`GLITCH_ONE_SCAN_ENVELOPE_SPANS`
    ranges. Needs at least three scans (with two, the median is their mean) and a median curve with an edge
    (:func:`has_edge`: against dead or dark scans nothing can be judged)."""
    n = M.shape[0]
    out: set[tuple[int, float]] = set()
    if n < 3 or not np.any(point_flags):
        return out
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(M, axis=0)
    fin = np.isfinite(med)
    if int(fin.sum()) < 5 or not has_edge(med, grid, np):
        return out
    lo, hi = float(np.nanmin(med)), float(np.nanmax(med))
    span = hi - lo
    R = np.full_like(M, np.nan, dtype=float)
    V = np.full_like(M, np.nan, dtype=float)  # each scan on the median's scale: (M - a) / b
    for s in range(n):
        ok = np.isfinite(M[s]) & fin & ~point_flags[s]
        if int(ok.sum()) < 3:
            continue
        A = np.vstack([np.ones(int(ok.sum())), med[ok]]).T
        (a, b), *_ = np.linalg.lstsq(A, M[s][ok], rcond=None)
        if not b > 0.1:
            continue  # not the median's shape on any sensible scale: nothing to judge it by
        R[s] = M[s] - (a + b * med)
        V[s] = (M[s] - a) / b
    dev = np.abs(R)
    for s, i in zip(*np.nonzero(point_flags)):
        d = float(dev[s, i])
        others = [float(dev[j, i]) for j in range(n) if j != s and np.isfinite(dev[j, i])]
        if not math.isfinite(d) or not others:
            continue
        v = float(V[s, i])
        outside = v > hi + GLITCH_ONE_SCAN_ENVELOPE_SPANS * span or v < lo - GLITCH_ONE_SCAN_ENVELOPE_SPANS * span
        if d > GLITCH_ONE_SCAN_FACTOR * max(others) and d > GLITCH_ONE_SCAN_SPAN_FRACTION * span and outside:
            out.add((int(s), float(grid[i])))
    return out


def glitch_points_on_edge(point_flags, grid, energy, curve, e0, np, *, M=None) -> list[tuple[int, float, bool]]:
    """Each flagged point (``deglitch``'s ``point_flags`` on ``grid``) as ``(scan_position, energy_eV, on_edge)``.
    ``energy``/``curve`` are the merged curve WITH THE FLAGGED POINTS LEFT OUT (a glitch must not make its own
    neighbourhood look steep) and ``e0`` its E0. A point is on the edge when it lies within
    :data:`GLITCH_EDGE_WINDOW_EV` of ``e0``, or inside the one stretch of steep slope (at least
    :data:`GLITCH_EDGE_STEEP_FRACTION` of the steepest) that holds the edge: a steep patch elsewhere never counts
    (:data:`GLITCH_EDGE_RULE_ID`). r4-a: given the scans ``M``, a point from one scan alone far beyond the others
    (:func:`glitch_points_from_one_scan`) is never on the edge: it is a glitch."""
    k = GLITCH_EDGE_SLOPE_HALF_WIDTH
    slope = np.full(energy.size, np.nan)
    if energy.size > 2 * k:
        with np.errstate(invalid="ignore", divide="ignore"):
            slope[k:-k] = np.abs((curve[2 * k:] - curve[:-2 * k]) / (energy[2 * k:] - energy[:-2 * k]))
    finite = np.isfinite(slope)
    steepest = float(np.nanmax(slope)) if finite.any() else 0.0
    lo = hi = None
    if steepest > 0:
        steep = finite & (np.nan_to_num(slope, nan=0.0) >= GLITCH_EDGE_STEEP_FRACTION * steepest)
        # the stretch that holds the edge: around E0 when it is steep there, else around the steepest point
        at = int(np.argmin(np.abs(energy - float(e0)))) if e0 is not None else int(np.nanargmax(slope))
        if not steep[at]:
            at = int(np.nanargmax(slope))
        lo = hi = at
        while lo > 0 and steep[lo - 1]:
            lo -= 1
        while hi < energy.size - 1 and steep[hi + 1]:
            hi += 1
    one = glitch_points_from_one_scan(point_flags, grid, M, np) if M is not None else set()
    out = []
    for s, i in zip(*np.nonzero(point_flags)):
        e = float(grid[i])
        near = e0 is not None and abs(e - float(e0)) <= GLITCH_EDGE_WINDOW_EV
        in_edge = lo is not None and float(energy[lo]) <= e <= float(energy[hi])
        out.append((int(s), e, bool(near or in_edge) and (int(s), e) not in one))
    return out


#: THE MERGED CURVE FROM ONE SCAN (``isaac.xas.edge_not_from_single_scan.v0``, r4-a). A merge describes its scans
#: only when no single scan sets it: the curve FAILS ``edge_from_single_scan`` when, with one scan left out, the
#: merged curve's range (max - min) shrinks by more than :data:`SINGLE_SCAN_SPAN_FACTOR` times, the OTHER scans have an
#: edge of their own (:func:`has_edge`), AND that scan's shape departs from theirs by more than the same factor, each
#: curve measured in units of its OWN edge step (its post-edge minus its pre-edge level, medians of the first and last
#: :data:`SINGLE_SCAN_LEVEL_FRACTION` of the points, so a tall white line is not a spike). A scan that is only larger
#: everywhere (a gain step) has the others' shape. When the others have no edge (dead, out of the beam, dark counts),
#: the scan is the group's only scan with an edge: that is said (``only_scan_with_edge``), never failed. Measured on a
#: real BL15-2 Ir L3 HERFD beamtime: one scan of five read about 28 where the others read about 0.01, the merge's
#: normalised white line was 2586 (the median curve's near 5) and its E0 2.7-3 eV from the neighbouring groups'; the
#: verdict was ``warn``. Not a protocol parameter (params.json is hashed into every id): a sanity bound.
SINGLE_SCAN_RULE_ID = "isaac.xas.edge_not_from_single_scan.v0"
SINGLE_SCAN_SPAN_FACTOR = 5.0
SINGLE_SCAN_LEVEL_FRACTION = 0.15
#: a departure within this window around the others' steepest point (eV below, eV above) is said as on the edge
SINGLE_SCAN_EDGE_WINDOW_EV = (10.0, 20.0)


def _in_step_units(y, np):
    """``y`` with its pre-edge level at 0 and its post-edge level at 1 (medians of its first and last
    :data:`SINGLE_SCAN_LEVEL_FRACTION` of points), or ``None`` (no positive step)."""
    k = max(2, int(round(SINGLE_SCAN_LEVEL_FRACTION * y.size)))
    pre, post = float(np.median(y[:k])), float(np.median(y[-k:]))
    step = post - pre
    return (y - pre) / step if step > 0 else None


def _region(lo: float, hi: float, edge: float | None) -> str:
    if edge is None:
        return "edge"
    below, above = SINGLE_SCAN_EDGE_WINDOW_EV
    if lo > edge + above:
        return "above_edge"
    if hi < edge - below:
        return "below_edge"
    return "edge"


def single_scan_dominance(M, grid, np, *, exclude_points=None, exclude_scans=None) -> dict | None:
    """``None`` when no single scan sets the merged curve (above); else the scan's position, ``kind``
    (``one_scan_sets_merge``: QC fails; ``only_scan_with_edge``: the other scans have no edge, said only), the ratio of
    the merged curve's range to its range without that scan, both ranges, the energies where the scan departs and
    their ``region`` (``edge``, ``above_edge`` or ``below_edge`` of the others' steepest point). ``M`` is scans x
    ``grid``; the exclusions are the merge's own (``deglitch.exclude_flagged``)."""
    n = M.shape[0]
    if n < 2:
        return None
    X = M.astype(float).copy()
    if exclude_points is not None:
        X[exclude_points] = np.nan
    if exclude_scans is not None:
        for s, bad in enumerate(exclude_scans):
            if bad:
                X[s] = np.nan
    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(X, axis=0)
        for s in range(n):
            if not np.isfinite(X[s]).any():
                continue
            rest = np.nanmean(np.delete(X, s, axis=0), axis=0)
            both = np.isfinite(rest) & np.isfinite(mean) & np.isfinite(X[s])
            if int(both.sum()) < 5:
                continue
            span_rest = float(np.ptp(rest[both]))
            span_all = float(np.ptp(mean[both]))
            if span_rest <= 0 or span_all < SINGLE_SCAN_SPAN_FACTOR * span_rest:
                continue
            e = grid[both]
            ratio = span_all / span_rest
            base = {"rule_id": SINGLE_SCAN_RULE_ID, "scan_position": int(s), "ratio": ratio, "span_merged": span_all,
                    "span_without_scan": span_rest, "factor": SINGLE_SCAN_SPAN_FACTOR, "points": int(both.sum())}
            if not has_edge(rest[both], e, np):
                # the others are dead, dark or out of the beam: this is the group's only scan with an edge, not a spike
                if has_edge(X[s][both], e, np) and (best is None or best["kind"] != "one_scan_sets_merge"):
                    best = {**base, "kind": "only_scan_with_edge", "departs_eV": [float(e[0]), float(e[-1])],
                            "departs_points": int(both.sum()), "region": "edge"}
                continue
            mine, theirs = _in_step_units(X[s][both], np), _in_step_units(rest[both], np)
            if mine is None or theirs is None:
                continue
            away = np.abs(mine - theirs)
            if float(away.max()) < SINGLE_SCAN_SPAN_FACTOR:
                continue  # the others' shape on a larger (or smaller) scale: a gain step
            far = away > 0.5 * float(away.max())
            if best is None or best["kind"] != "one_scan_sets_merge" or ratio > best["ratio"]:
                where = e[far]
                slope = np.abs(np.gradient(rest[both], e))
                edge = float(e[int(np.nanargmax(slope))]) if np.isfinite(slope).any() else None
                best = {**base, "kind": "one_scan_sets_merge", "departs_eV": [float(where.min()), float(where.max())],
                        "departs_points": int(far.sum()), "edge_eV": edge,
                        "region": _region(float(where.min()), float(where.max()), edge)}
    return best


def merge(M, exclude_points=None, exclude_scans: Sequence[bool] | None = None, np=None) -> dict:
    X = M.astype(float).copy()
    if exclude_points is not None:
        X[exclude_points] = np.nan
    if exclude_scans is not None:
        for s, bad in enumerate(exclude_scans):
            if bad:
                X[s] = np.nan
    n = np.sum(np.isfinite(X), axis=0)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN columns -> NaN, counted in n
        mean = np.nanmean(X, axis=0)
        std = np.nanstd(X, axis=0, ddof=1)
    std = np.where(n > 1, std, np.nan)
    stderr = np.where(n > 1, std / np.sqrt(np.maximum(n, 1)), np.nan)
    return {"mean": mean, "std": std, "stderr": stderr, "n": n}


# --- normalise --------------------------------------------------------------------------------


def normalize(energy, mu, params: Mapping, np, larch_xafs, *, e0: float | None = None) -> dict:
    from larch import Group

    p = params["normalize"]
    kwargs = {k: p[k] for k in ("pre1", "pre2", "norm1", "norm2", "nnorm") if p.get(k) is not None}
    use_e0 = p.get("e0") if p.get("e0") is not None else e0
    norm1_rule = None
    if p.get("norm1") is None and p.get("norm1_rule_cap_eV") is not None:
        try:
            e0_for_rule = use_e0 if use_e0 is not None else float(larch_xafs.find_e0(energy, mu))
        except Exception as exc:  # noqa: BLE001
            raise StepError("normalization_failed", f"find_e0: {type(exc).__name__}: {exc}") from exc
        span = float(energy[-1]) - e0_for_rule
        if span > 0:
            kwargs["norm1"] = min(float(p["norm1_rule_cap_eV"]), float(p["norm1_rule_fraction"]) * span)
            norm1_rule = {"cap_eV": p["norm1_rule_cap_eV"], "fraction": p["norm1_rule_fraction"], "post_e0_span_eV": span}
        if p.get("nnorm") is not None and span < 100 and kwargs.get("nnorm", 0) > 1:
            kwargs["nnorm"] = 1  # a quadratic over < 100 eV is not constrained (only when a scientist set >1); recorded below
    if p.get("nnorm") is None and p.get("nnorm_rule_quadratic_from_eV") is not None:
        # isaac.xas.post_edge_order_is_larch_degree.v0: a line under the threshold window, a quadratic from it on
        try:
            e0_w = use_e0 if use_e0 is not None else float(larch_xafs.find_e0(energy, mu))
        except Exception as exc:  # noqa: BLE001
            raise StepError("normalization_failed", f"find_e0: {type(exc).__name__}: {exc}") from exc
        n1 = kwargs.get("norm1")
        n2 = kwargs.get("norm2") if kwargs.get("norm2") is not None else float(energy[-1]) - e0_w
        if n1 is not None:
            kwargs["nnorm"] = 2 if (n2 - n1) >= float(p["nnorm_rule_quadratic_from_eV"]) else 1
    g = Group()
    try:
        larch_xafs.pre_edge(energy, mu, group=g, e0=use_e0, make_flat=bool(p.get("make_flat", True)), **kwargs)
    except Exception as exc:  # noqa: BLE001
        raise StepError("normalization_failed", f"{type(exc).__name__}: {exc}") from exc
    if len(g.norm) != len(energy):
        raise StepError("normalization_length_mismatch", f"{len(g.norm)} != {len(energy)}")
    d = g.pre_edge_details
    resolved = {k: _f(getattr(d, k, None)) for k in ("pre1", "pre2", "norm1", "norm2", "nnorm")}
    lo, hi = g.e0 + (resolved["pre1"] or 0), g.e0 + (resolved["pre2"] or 0)
    sel = (energy >= lo) & (energy <= hi)
    step = _f(g.edge_step)
    noise = None
    if np.sum(sel) >= 3 and step:
        noise = _f(np.std((mu - g.pre_edge)[sel]) / abs(step))
    return {
        "e0_eV": _f(g.e0),
        "edge_step": step,
        "norm": np.asarray(g.norm, dtype=float),
        "flat": np.asarray(getattr(g, "flat", g.norm), dtype=float),
        "pre_edge_curve": np.asarray(g.pre_edge, dtype=float),
        "post_edge_curve": np.asarray(g.post_edge, dtype=float),
        "resolved_params": {**resolved, "norm1_rule": norm1_rule, "e0": _f(g.e0), "e0_source": "param" if p.get("e0") is not None else ("calibrated_reference" if e0 is not None else "larch_find_e0"), "make_flat": bool(p.get("make_flat", True))},
        "pre_edge_noise": noise,
        "pre_edge_points": int(np.sum(sel)),
    }


# --- QC ---------------------------------------------------------------------------------------

#: THE EDGE-STEP SANITY BOUND (``isaac.xas.edge_step_plausible.v0``). An edge step is the jump of the
#: spectrum at E0, so it cannot be much larger than the spectrum's whole range (max - min of the signal
#: that was normalised). One larger than this many times that range means the post-edge fit did not
#: describe the data. Measured on a real BL6-2c beamtime: Athena projects stating a post-edge range of
#: zero width (``nor1 == nor2``), which larch widens to 2 eV and fits with a cubic, gave edge steps of
#: 4683 to 190115 for spectra spanning 2.5, and their QC said ``pass``. Not a protocol parameter: it
#: is a sanity bound, and adding it changed no result that it does not flag.
EDGE_STEP_MAX_RANGE_RATIO = 2.0
EDGE_STEP_RULE_ID = "isaac.xas.edge_step_plausible.v0"


def edge_step_implausible(step, signal, np, *, post_edge: str | None = None) -> dict | None:
    """``None`` when ``step`` is plausible for ``signal`` (or there is no positive step to judge: that
    fails on its own as ``edge_step_not_positive``); else what was found, with a plain sentence.
    ``post_edge`` names the post-edge range that was fitted, for the sentence."""
    step = _f(step)
    if step is None or step <= 0:
        return None
    y = np.asarray(signal, dtype=float)
    y = y[np.isfinite(y)]
    if y.size < 2:
        return None
    span = float(y.max() - y.min())
    ratio = (step / span) if span > 0 else None
    if ratio is not None and ratio <= EDGE_STEP_MAX_RANGE_RATIO:
        return None
    where = f" (post-edge range {post_edge})" if post_edge else ""
    return {
        "rule_id": EDGE_STEP_RULE_ID,
        "edge_step": step,
        "signal_range": span,
        "ratio": ratio,
        "max_ratio": EDGE_STEP_MAX_RANGE_RATIO,
        "statement": (
            f"The edge step {step:.6g} is {ratio:.4g} times the spectrum's whole range ({span:.6g}, max - min)"
            if ratio is not None else f"The edge step {step:.6g} is not zero but the spectrum is flat"
        ) + (
            f"; an edge step is at most about that range, so the post-edge fit{where} did not describe the "
            "data and the normalised curve made with it is not usable. A person checks the post-edge range."
        ),
    }


#: A curve Athena marks already normalised (``is_nor``) is used as stored; it is believed only when it looks
#: normalised: its pre-edge mean near 0 and its post-edge mean near 1 (review: the flag alone was trusted).
NORMALIZED_CHECK_RULE_ID = "isaac.xas.stored_normalized_plausible.v0"
NORMALIZED_CHECK_TOLERANCE = 0.25
NORMALIZED_CHECK_PRE_EDGE_EV = -20.0
NORMALIZED_CHECK_POST_EDGE_EV = 50.0


def stored_normalized_implausible(energy, curve, e0, np) -> dict | None:
    """``None`` when a curve stored as already normalised looks normalised (or there is too little on
    either side of ``e0`` to judge); else what was found, with a plain sentence. Same shape as
    :func:`edge_step_implausible`, so the curve is handled the same way: not compared, not preferred."""
    e0 = _f(e0)
    if e0 is None:
        return None
    e, y = np.asarray(energy, dtype=float), np.asarray(curve, dtype=float)
    ok = np.isfinite(e) & np.isfinite(y)
    pre = y[ok & (e < e0 + NORMALIZED_CHECK_PRE_EDGE_EV)]
    post = y[ok & (e > e0 + NORMALIZED_CHECK_POST_EDGE_EV)]
    if pre.size < 3 or post.size < 3:
        return None
    pre_mean, post_mean = float(pre.mean()), float(post.mean())
    if abs(pre_mean) <= NORMALIZED_CHECK_TOLERANCE and abs(post_mean - 1.0) <= NORMALIZED_CHECK_TOLERANCE:
        return None
    return {
        "rule_id": NORMALIZED_CHECK_RULE_ID,
        "pre_edge_mean": pre_mean,
        "post_edge_mean": post_mean,
        "tolerance": NORMALIZED_CHECK_TOLERANCE,
        "statement": (
            f"Athena marks this curve already normalised, but its pre-edge mean is {pre_mean:.3g} and its "
            f"post-edge mean is {post_mean:.3g} (a normalised curve is near 0 and 1, within "
            f"{NORMALIZED_CHECK_TOLERANCE}); it is not used as the scientist's normalised result. A person checks it."
        ),
    }


#: THE POST-EDGE LEVEL (``isaac.xas.post_edge_level.v1``). Over the post-edge window (norm1 to norm2 above
#: E0) a normalised spectrum sits about ONE edge step above the pre-edge line. The level is measured TWO
#: ways, and the curve fails only when BOTH are outside :data:`POST_EDGE_LEVEL_RANGE` (the edge step then
#: does not describe the spectrum's jump, so the normalised curve is not usable):
#:
#: * from the pre-edge line AT EACH post-edge energy, ``mean(mu - pre_edge_line) / edge_step`` over the
#:   window (the mean of larch's ``norm``): right for a transmission spectrum, whose absorption background
#:   falls (or whose pre-edge line has a real slope) across the 50-600 eV window by as much as the edge step;
#: * from the pre-edge line held at its E0 value, ``(mean(mu) - pre_edge_line(E0)) / edge_step`` (v0's only
#:   measure): right when the line's slope, fitted over a short pre-edge window, is extrapolated far.
#:
#: Why both (review, cycle 3): v0 failed clean synthetic Co K-edges in transmission on a background of 2.5
#: (levels -0.44 to -0.09) and any spectrum whose pre-edge slope is +-0.01 step/eV (4.0, -2.0); the mean of
#: ``norm`` alone, measured on four real SSRL beamtimes, put sound dilute Ir HERFD scans (3 pre-edge points
#: over 15 eV, extrapolated 280 eV) at -0.73 and 2.2 to 2.8.
#:
#: Measured with v1 on every curve of those four beamtimes (BL15-2, BL6-2c, two BL4-3) with a post-edge
#: window and a scan reaching 50 eV above E0 (212 pass/warn): from the line at each energy -0.73 to 2.77
#: (5th-95th percentile 0.80 to 1.49), from the line at E0 0.34 to 1.89 (0.82 to 1.27); the level nearer 1
#: lies at 0.50 to 1.89. Outside (0, 2) one way only were 7 sound fluorescence/HERFD curves (the line way),
#: none in transmission (IrO2 in transmission: 1.39 from the line, 0.35 at E0). Failed both ways: a TiO2
#: anatase scan ending 122 eV above E0 (2.49 / 2.45: a quadratic post-edge over 49-120 eV of EXAFS put the
#: step at 0.58 for a jump of 1.4), a noisy dilute Ir HERFD scan (2.11 / 2.11: step half its post-edge
#: level), a Ti foil whose ln(I0/I1) falls at the edge (-0.88 / -1.82; larch's edge step is |jump|, so the
#: step alone is positive) and an all-zero signal (3.84). The bounds stay 0 and 2: the measurements do not
#: move them (sound 0.50 to 1.89, junk at 2.11 and above, or below 0). The two Ti foil calibration scans
#: ending 19 eV above E0 are not judged (:data:`POST_EDGE_MIN_SPAN_EV`). Verdicts on the four beamtimes are
#: unchanged from v0; the synthetic transmission spectra above now pass.
#: Not a protocol parameter: a sanity bound, like :data:`EDGE_STEP_MAX_RANGE_RATIO`.
POST_EDGE_LEVEL_RULE_ID = "isaac.xas.post_edge_level.v1"
POST_EDGE_LEVEL_RANGE = (0.0, 2.0)
POST_EDGE_LEVEL_MIN_POINTS = 3
#: A scan ending less than this far above E0 has no real post-edge window: the level is NOT judged and QC
#: warns ``post_edge_window_too_short`` instead (as ``no_edge`` is not judged with < 3 pre-edge points).
#: Measured on the four beamtimes' pass/warn curves: scans end 0.9 to 27 eV above E0 (calibration foils,
#: short XANES scans) or at least 64 eV; the two Ti calibration scans (19 eV) have a sound E0 but a
#: "post-edge" window inside the edge.
POST_EDGE_MIN_SPAN_EV = 50.0


def post_edge_window_too_short(energy, e0, np) -> dict | None:
    """``None`` when the scan reaches at least :data:`POST_EDGE_MIN_SPAN_EV` above ``e0`` (or there is no E0);
    else the span, with a plain sentence. The post-edge level is then not judged."""
    e0 = _f(e0)
    e = np.asarray(energy, dtype=float)
    e = e[np.isfinite(e)]
    if e0 is None or e.size == 0:
        return None
    span = float(e.max()) - e0
    if span >= POST_EDGE_MIN_SPAN_EV:
        return None
    return {
        "rule_id": POST_EDGE_LEVEL_RULE_ID,
        "post_e0_span_eV": span,
        "min_span_eV": POST_EDGE_MIN_SPAN_EV,
        "statement": (
            f"The scan ends {span:.3g} eV above E0 {e0:g} eV (under {POST_EDGE_MIN_SPAN_EV:g} eV), so there is no real "
            "post-edge window and the normalised level cannot be checked; its edge position is still usable."
        ),
    }


def post_edge_level_implausible(energy, mu, pre_edge_curve, e0, step, np, *, norm1, norm2) -> dict | None:
    """``None`` when either post-edge level (above) is inside :data:`POST_EDGE_LEVEL_RANGE`, or when it cannot
    be judged (no positive step, no E0, a scan ending too soon above E0, fewer than
    :data:`POST_EDGE_LEVEL_MIN_POINTS` points in the window); else what was found, with a plain sentence.
    ``level`` is the level from the pre-edge line at each energy; ``level_from_line_at_e0`` the other."""
    step, e0, norm1, norm2 = _f(step), _f(e0), _f(norm1), _f(norm2)
    if step is None or step <= 0 or e0 is None or norm1 is None or norm2 is None:
        return None
    if post_edge_window_too_short(energy, e0, np):
        return None  # not judged: QC warns post_edge_window_too_short instead
    e, y, pre = (np.asarray(a, dtype=float) for a in (energy, mu, pre_edge_curve))
    ok = np.isfinite(pre)
    if not ok.any():
        return None
    sel = np.isfinite(e) & np.isfinite(y) & ok & (e >= e0 + norm1) & (e <= e0 + norm2)
    n = int(np.sum(sel))
    if n < POST_EDGE_LEVEL_MIN_POINTS:
        return None
    pre_e0 = float(np.interp(e0, e[ok], pre[ok]))
    level = _f(float(np.mean(y[sel] - pre[sel])) / step)
    at_e0 = _f((float(np.mean(y[sel])) - pre_e0) / step)
    lo, hi = POST_EDGE_LEVEL_RANGE
    if level is None or at_e0 is None or lo < level < hi or lo < at_e0 < hi:
        return None
    where = f"over the post-edge window ({norm1:g} to {norm2:g} eV above E0 {e0:g} eV, {n} points)"
    both = (f"{level:.3g} edge steps from the pre-edge line at each energy and {at_e0:.3g} from the line held at "
            "its E0 value")
    if level <= lo and at_e0 <= lo:
        said = (f"The spectrum sits below the pre-edge line {where}: its post-edge level is {both}, so it falls at "
                "the edge instead of rising (the edge step is the size of the jump, not its sign). ")
    elif level >= hi and at_e0 >= hi:
        said = (f"The spectrum sits {level:.3g} edge steps above the pre-edge line {where} ({both}), where a "
                f"normalised spectrum sits about 1: the edge step {step:.6g} does not describe its jump. ")
    else:
        said = (f"The post-edge level {where} is {both}: neither is near 1, so the edge step {step:.6g} and the "
                "pre-edge line do not describe the spectrum. ")
    return {
        "rule_id": POST_EDGE_LEVEL_RULE_ID,
        "level": level,
        "level_from_line_at_e0": at_e0,
        "range": list(POST_EDGE_LEVEL_RANGE),
        "edge_step": step,
        "window_eV": [e0 + norm1, e0 + norm2],
        "points": n,
        "statement": said + (f"Outside {lo:g} to {hi:g} both ways, the normalised curve is not usable. A person "
                             "checks the channel, E0 and the pre- and post-edge ranges."),
    }


#: THE EDGE ABOVE THE NOISE (``isaac.xas.edge_above_noise.v0``). The edge step must be at least this many
#: times the pre-edge scatter (the standard deviation of mu about the pre-edge line, ``pre_edge_noise`` =
#: scatter / step). Measured on every pass/warn curve of four real SSRL beamtimes with >= 3 pre-edge points
#: (150): the step was 16.5 to 5600 times the scatter, except a Ti foil read through a dead I1 (2.4 times: a
#: falling noisy trace with no edge). Curves with fewer than 3 pre-edge points have no ``pre_edge_noise`` and
#: are not judged by this check. Not a protocol parameter: a sanity bound.
EDGE_NOISE_RULE_ID = "isaac.xas.edge_above_noise.v0"
EDGE_MIN_NOISE_MULTIPLE = 5.0


def no_edge(step, pre_edge_noise) -> dict | None:
    """``None`` when the edge stands at least :data:`EDGE_MIN_NOISE_MULTIPLE` times above the pre-edge scatter
    (or there is no scatter to judge by, or no positive step: that fails on its own); else what was found."""
    step, noise = _f(step), _f(pre_edge_noise)
    if step is None or step <= 0 or noise is None or noise <= 0:
        return None
    multiple = 1.0 / noise
    if multiple >= EDGE_MIN_NOISE_MULTIPLE:
        return None
    return {
        "rule_id": EDGE_NOISE_RULE_ID,
        "edge_to_noise": multiple,
        "min_multiple": EDGE_MIN_NOISE_MULTIPLE,
        "statement": (
            f"No edge stands above the noise: the edge step {step:.6g} is only {multiple:.3g} times the pre-edge scatter "
            f"(the standard deviation of mu about the pre-edge line); a measured edge is at least "
            f"{EDGE_MIN_NOISE_MULTIPLE:g} times it. This is not a usable spectrum. A person checks the channel."
        ),
    }


def edge_checks(energy, mu, nm: Mapping, np) -> dict[str, dict]:
    """The two checks above on a normalisation (:func:`normalize`'s output): ``{qc reason: finding}`` for each
    that FAILS (empty when both pass or cannot be judged)."""
    out = {}
    rp = nm.get("resolved_params") or {}
    lvl = post_edge_level_implausible(energy, mu, nm["pre_edge_curve"], nm.get("e0_eV"), nm.get("edge_step"), np,
                                      norm1=rp.get("norm1"), norm2=rp.get("norm2"))
    if lvl:
        out["post_edge_not_at_1"] = lvl
    ne = no_edge(nm.get("edge_step"), nm.get("pre_edge_noise"))
    if ne:
        out["no_edge"] = ne
    return out



def qc_verdict(metrics: Mapping, params: Mapping) -> tuple[str, list[str]]:
    """pass | warn | fail with the reasons, from DATA-QUALITY metrics only.

    Provenance flags (channel or calibration unconfirmed) are review flags on the result,
    not quality: they do not move the verdict.
    """
    q = params["qc"]
    fail, warn = [], []
    if metrics.get("scans_used") == 0:
        fail.append("no_usable_scan")
    if (metrics.get("points") or 0) < int(q["fail_min_points"]):
        fail.append("too_few_points")
    step = metrics.get("edge_step")
    if step is None or not (step > 0):
        fail.append("edge_step_not_positive")
    if "edge_step_implausible" in metrics:
        # present only when the step failed the sanity bound (edge_step_implausible; its value, the
        # step / range ratio, is null for a flat spectrum): never a pass
        fail.append("edge_step_implausible")
    # each present only when its check failed (post_edge_level_implausible, no_edge): never a pass
    if "post_edge_level" in metrics:
        fail.append("post_edge_not_at_1")
    if "edge_to_pre_edge_noise" in metrics:
        fail.append("no_edge")
    if "single_scan_span_ratio" in metrics:
        # r4-a (SINGLE_SCAN_RULE_ID): present only when one scan sets the merged curve's range: never a pass
        fail.append("edge_from_single_scan")
    if (metrics.get("i0_nonpositive_fraction") or 0) > float(q["fail_i0_nonpositive_fraction"]):
        fail.append("i0_nonpositive")
    if metrics.get("signal_all_zero_scans"):
        fail.append("signal_all_zero")
    if metrics.get("scans_used") is not None and metrics["scans_used"] < int(q["warn_min_scans"]):
        warn.append("single_scan")
    if metrics.get("scans_skipped_signal_all_zero"):
        # c11-a: a scan whose signal is zero at every point was left out of the merge: a person checks why it
        # recorded nothing (the plain sentence is in qc.statements)
        warn.append("scans_skipped_signal_all_zero")
    if metrics.get("scans_skipped_aborted_fragment"):
        # r5 A5: a scan that stopped early was left out of the merge (run.FRAGMENT_RULE_ID): a person checks it
        warn.append("scans_skipped_aborted_fragment")
    if metrics.get("scans_skipped_lacking_chosen_columns"):
        # readable scans of the group that lack the chosen columns were left out: a person
        # confirms they belong elsewhere (e.g. motor/alignment scans), so never a pass
        warn.append("scans_skipped_lacking_chosen_columns")
    if "post_edge_span_eV" in metrics:
        # present only when the scan ends too soon above E0 for the post-edge level to be judged
        warn.append("post_edge_window_too_short")
    if metrics.get("truncated_scans"):
        # a scan that ends early is kept where it has data, so part of the merged curve averages fewer
        # scans than are listed as used: a person checks it (the plain sentence is in qc.statements)
        warn.append("scans_truncated")
    if metrics.get("channel_fallback"):
        # the role's first channel was abandoned (``channel_fallback_<why>``): a person confirms
        # the channel that was used, so never a pass
        warn.append(f"channel_fallback_{metrics['channel_fallback']}")
    if (metrics.get("pre_edge_noise") or 0) > float(q["warn_pre_edge_noise"]):
        warn.append("pre_edge_noise")
    if (metrics.get("scan_spread") or 0) > float(q["warn_scan_spread"]):
        warn.append("scan_to_scan_spread")
    if metrics.get("glitch_points"):
        warn.append("glitches_flagged")
    if metrics.get("outlier_scans"):
        warn.append("outlier_scans_flagged")
    shift = metrics.get("energy_shift_eV")
    if shift is not None and abs(shift) > float(q["warn_energy_shift_eV"]):
        warn.append("large_energy_shift")
    spread = metrics.get("reference_e0_spread_eV")
    if spread is not None and spread > float(q["warn_reference_e0_spread_eV"]):
        warn.append("reference_e0_drift")
    if (metrics.get("signal_max_run") or 0) >= int(q["saturation_run_points"]):
        warn.append("saturation_suspected")
    if metrics.get("nonmonotonic_steps"):
        warn.append("energy_not_monotonic")
    if metrics.get("nonfinite_dropped"):
        warn.append("nonfinite_points_dropped")
    if metrics.get("i0_nonpositive_fraction"):
        warn.append("some_i0_nonpositive")
    if fail:
        return "fail", fail + warn
    return ("warn", warn) if warn else ("pass", [])


# --- scan selection: a PROPOSAL per scan, never a drop ---------------------------------------------------------------
#
# ``isaac.xas.scan_selection_proposal.v0``. Rules from the beamline scientist (Angel, 9 Nov 2026):
#
# * normalised data are NEVER merged. Each scan is normalised ALONE, with ONE parameter set for the whole series (the
#   series E0, the pre-edge ending at E0-30, a linear post-edge from E0+100 to the end), ONLY to judge it: trends,
#   glitches, beam drops, diffraction peaks, errors. The merge stays RAW mu (:func:`merge` is unchanged);
# * an intensity drop alone never excludes a scan: an edge-step change is a group OBSERVATION ("possible dissolution
#   or detachment"), never a reason;
# * every exclusion is a PROPOSAL the scientist confirms (``exclude_scans`` in a params file, then re-process).
#
# The thresholds are module constants, NOT protocol parameters: params.json is hashed into every result id, so they
# live here and the rule id is listed in ``protocol.RULE_VERSIONS_SINCE_PROTOCOL_VERSION`` (rolling this out moves no
# result id: merged.csv and run_id are unchanged).

SCAN_SELECTION_RULE_ID = "isaac.xas.scan_selection_proposal.v0"
#: proposals, in increasing strength
PROPOSAL_INCLUDE = "include"
PROPOSAL_LOOK = "needs_look"
PROPOSAL_EXCLUDE = "exclude_proposed"
#: a scan the rule cannot judge (no scan of its group reaches the series window): never a proposal
PROPOSAL_NOT_EVALUATED = "not_evaluated"
_PROPOSAL_ORDER = {PROPOSAL_INCLUDE: 0, PROPOSAL_LOOK: 1, PROPOSAL_EXCLUDE: 2}

SEL_PRE2_REL_EV = -30.0          # the series pre-edge fit ends at E0-30 (protocol pre2)
SEL_NORM1_REL_EV = 100.0         # the series post-edge fit starts at E0+100, linear, to the end of the scan
SEL_XANES_WINDOW_EV = (-20.0, 80.0)  # shape comparison and artifact relevance, relative to the series E0
SEL_MIN_POST_EDGE_EV = 50.0      # a scan reaches E0 + 100 + this (E0+150) to be normalised alone ("complete")
SEL_COVERAGE_MIN = 0.95          # ...and covers this fraction of the group's widest scan
SEL_EVAL_SNR_MIN = 2.0           # edge step / per-point post-edge noise under this: the scan alone cannot be judged
SEL_BEAM_DROP_LOOK = 0.50        # I0 under half its usual level: a beam drop a person looks at
SEL_BEAM_DROP_FRAC = 0.90        # I0 under 90% of its usual level (ring current divided out): a beam drop
SEL_MANY_ARTIFACTS = 3           # this many merge-visible artifacts in one scan: propose leaving it out
SEL_EXCESS_NOISE_LOOK = 2.0      # measured noise / counting-statistics noise
SEL_ARTIFACT_Z = 6.0             # the deglitch point threshold
SEL_ARTIFACT_MAX_WIDTH = 6       # points; a wider departure is shape, not an artifact
SEL_VISIBLE_R = 1.0              # the bias a scan puts on the raw merge / that merge's own noise
SEL_ALPHA = 0.01 / 3             # trend slope significance, Bonferroni over the 3 shape metrics
SEL_FIRST_LAST_Z = 3.0           # first-vs-last difference in noise units
#: the smallest change that matters (eV, eV, normalised height)
SEL_FLOOR = {"delta_eV": 0.15, "wl_e_eV": 0.15, "wl_h": 0.03}
SEL_SHAPE_METRICS = ("delta_eV", "wl_e_eV", "wl_h")
SEL_CHI2_P = 1e-3                # a shape outlier's chi2/nu is above this p...
SEL_CHI2_MEDIAN_FACTOR = 1.5     # ...and this many times the group median
SEL_SHIFT_MIN_EV = 0.2           # energy_shifted: more than this...
SEL_SHIFT_SPREAD_FACTOR = 4.0    # ...and this many robust spreads of the other scans' shifts
SEL_SNR_LOWERED = 0.98           # merged edge SNR with the scan under this fraction of it without: lowers_merge_snr
SEL_EDGE_STEP_OBSERVED = 0.05    # an edge-step change of at least this fraction is said (an observation only)
SEL_BOOTSTRAP = 40               # noise-injection replicas per scan (seeded by the scan's own content)
#: header keys (``#P`` lines, ``key=value``) that must agree across a group's scans, with their tolerance
SEL_SETUP_KEYS = (("emiss", 0.1), ("filter", 0.0))
#: ring-current columns, first present wins: I0 is judged against it so a ring-current change is not a beam drop
RING_CURRENT_COLUMNS = ("spear", "SPEAR", "ring_current", "RingCurrent", "Ring Current", "ring")

SCAN_SELECTION_CONSTANTS = {
    "pre2_rel_eV": SEL_PRE2_REL_EV, "norm1_rel_eV": SEL_NORM1_REL_EV, "nnorm": 1,
    "xanes_window_eV": list(SEL_XANES_WINDOW_EV), "complete_min_post_e0_eV": SEL_NORM1_REL_EV + SEL_MIN_POST_EDGE_EV,
    "coverage_min": SEL_COVERAGE_MIN, "eval_snr_min": SEL_EVAL_SNR_MIN, "excess_noise_look": SEL_EXCESS_NOISE_LOOK,
    "artifact_z": SEL_ARTIFACT_Z, "artifact_max_width_points": SEL_ARTIFACT_MAX_WIDTH,
    "beam_drop_fraction": SEL_BEAM_DROP_FRAC, "beam_drop_look_fraction": SEL_BEAM_DROP_LOOK,
    "many_artifacts": SEL_MANY_ARTIFACTS, "visible_R": SEL_VISIBLE_R, "trend_alpha": SEL_ALPHA,
    "first_last_z": SEL_FIRST_LAST_Z, "floors": dict(SEL_FLOOR), "chi2_p": SEL_CHI2_P,
    "chi2_median_factor": SEL_CHI2_MEDIAN_FACTOR, "energy_shift_min_eV": SEL_SHIFT_MIN_EV,
    "energy_shift_spread_factor": SEL_SHIFT_SPREAD_FACTOR, "merge_snr_lowered_fraction": SEL_SNR_LOWERED,
    "edge_step_observed_fraction": SEL_EDGE_STEP_OBSERVED, "bootstrap": SEL_BOOTSTRAP,
}


def _stats():
    from scipy import stats  # a dependency of xraylarch

    return stats


def counting_noise(counts, i0, np):
    """Counting-statistics noise of mu = N/I0 for INTEGER counts N: sqrt(N+1)/I0, else ``None`` (the signal is not
    counts: a current, a dead-time-corrected float, a log ratio)."""
    if counts is None or i0 is None:
        return None
    c, d = np.asarray(counts, dtype=float), np.asarray(i0, dtype=float)
    ok = np.isfinite(c) & np.isfinite(d)
    if not ok.any() or np.any(c[ok] < 0) or np.any(np.abs(c[ok] - np.round(c[ok])) > 1e-6) or np.any(d[ok] <= 0):
        return None
    return np.sqrt(np.maximum(c, 0) + 1.0) / d


def neighbour_z(E, y, s, np):
    """Each inner point's residual against the line through its two neighbours, in units of its expected sigma."""
    wa = (E[2:] - E[1:-1]) / (E[2:] - E[:-2])
    wb = 1 - wa
    r = y[1:-1] - (wa * y[:-2] + wb * y[2:])
    v = s[1:-1] ** 2 + (wa * s[:-2]) ** 2 + (wb * s[2:]) ** 2
    return E[1:-1], r / np.sqrt(v)


def robust_sigma(z, np) -> float | None:
    z = z[np.isfinite(z)]
    return float(1.4826 * np.median(np.abs(z - np.median(z)))) if z.size >= 5 else None


def normalize_fixed(E, mu, e0s: float, np) -> dict | None:
    """ONE fixed parameter set (evaluation only): a line through the pre-edge (second point to E0-30), a line through
    the post-edge (E0+100 to the end), the step at E0. ``None`` without a positive step."""
    pre = (E >= E[1] if E.size > 1 else E >= E[0]) & (E <= e0s + SEL_PRE2_REL_EV)
    post = E >= e0s + SEL_NORM1_REL_EV
    if pre.sum() >= 3:
        pc = np.polyfit(E[pre], mu[pre], 1)
    else:
        pc = np.array([0.0, float(np.mean(mu[pre])) if pre.any() else float(mu[0])])
    if post.sum() < 3:
        return None
    qc = np.polyfit(E[post], mu[post], 1)
    step = float(np.polyval(qc, e0s) - np.polyval(pc, e0s))
    if not step > 0:
        return None
    return {"norm": (mu - np.polyval(pc, E)) / step, "step": step}


def white_line(E, n, e0s: float, np) -> dict | None:
    """White-line energy and height (vertex of a quadratic through the top), and the energy at half step (the first
    rising crossing of 0.5 below the white line)."""
    sel = (E >= e0s - 2) & (E <= e0s + 15)
    if sel.sum() < 5:
        return None
    e, y = E[sel], n[sel]
    ys = np.convolve(y, np.ones(3) / 3, mode="same")
    i = int(np.argmax(ys[1:-1])) + 1
    near = np.abs(e - e[i]) <= 1.2
    wl_e, wl_h = e[i], float(ys[i])
    if near.sum() >= 4:
        c = np.polyfit(e[near] - e[i], y[near], 2)
        if c[0] < 0:
            x0 = -c[1] / (2 * c[0])
            if abs(x0) <= 1.2:
                wl_e, wl_h = e[i] + x0, float(np.polyval(c, x0))
    sel2 = (E >= e0s - 15) & (E <= wl_e)
    e2, y2 = E[sel2], n[sel2]
    half = None
    for j in range(1, e2.size):
        if y2[j - 1] < 0.5 <= y2[j]:
            half = float(e2[j - 1] + (0.5 - y2[j - 1]) * (e2[j] - e2[j - 1]) / (y2[j] - y2[j - 1]))
            break
    return {"wl_e_eV": float(wl_e), "wl_h": wl_h, "e_half_eV": half}


def _scan_metrics(sc: dict, e0s: float, span_ref: float, np) -> dict:
    """One scan alone: completeness, noise (counting and excess), I0 health, its own normalisation with the series
    parameters, edge SNR, white line, and their spreads by noise injection. Adds the working arrays to ``sc``."""
    E, mu = sc["energy"], sc["mu"]
    m = {"points": int(E.size), "E_first_eV": float(E[0]), "E_last_eV": float(E[-1]),
         "coverage": float((E[-1] - E[0]) / span_ref) if span_ref else None,
         **{k: (sc.get("setup") or {}).get(k) for k, _ in SEL_SETUP_KEYS}}
    m["complete"] = bool(E[-1] >= e0s + SEL_NORM1_REL_EV + SEL_MIN_POST_EDGE_EV and (m["coverage"] or 0) >= SEL_COVERAGE_MIN)
    sigP = counting_noise(sc.get("counts"), sc.get("i0"), np)
    if sigP is not None and E.size >= 7:
        m["noise_model"] = "counting_statistics"
        ez, z = neighbour_z(E, mu, sigP, np)
        m["F_pre"] = robust_sigma(z[ez < e0s - 10], np)
        m["F_post"] = robust_sigma(z[ez > e0s + 40], np)
        sig = max(m["F_post"] or 1.0, 1.0) * sigP  # never claim less than counting noise
    else:
        # not integer counts: the noise is the scatter about the neighbour line itself (no excess-noise factor)
        m["noise_model"] = "measured_scatter"
        m["F_pre"] = m["F_post"] = None
        ones = np.ones(E.size)
        if E.size >= 7:
            ez, z = neighbour_z(E, mu, ones, np)
        else:
            ez, z = E, np.full(E.size, np.nan)
        s_post = robust_sigma(z[ez > e0s + 40], np) or robust_sigma(z, np) or 0.0
        sig = ones * (s_post if s_post > 0 else max(float(np.std(mu)) * 1e-3, 1e-300))
    sc["sig"] = sig
    ring = sc.get("ring")
    i0 = sc.get("i0")
    if i0 is not None:
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = i0 / np.where(np.isfinite(ring) & (ring > 0), ring, 1.0) if ring is not None else i0.copy()
        med = float(np.median(i0)) if i0.size else 0.0
        m["i0_min_over_median"] = float(np.min(i0) / med) if med > 0 else None
    else:
        ratio = None
        m["i0_min_over_median"] = None
    sc["i0_ratio"] = ratio
    m["i0_nonpositive"] = int(sc.get("i0_nonpositive") or 0)
    if not m["complete"]:
        return m
    nm = normalize_fixed(E, mu, e0s, np)
    if nm is None:
        m["complete"] = False
        m["normalization_failed"] = True
        return m
    sc["norm"], sc["step"] = nm["norm"], nm["step"]
    sc["sig_norm"] = sig / nm["step"]
    m["edge_step"] = nm["step"]
    post = E >= e0s + SEL_NORM1_REL_EV
    m["noise_post_mu"] = float(np.median(sig[post]))
    m["edge_snr"] = float(nm["step"] / m["noise_post_mu"]) if m["noise_post_mu"] > 0 else None
    m.update(white_line(E, nm["norm"], e0s, np) or {})
    rng = np.random.default_rng(int(sc.get("seed") or 0))
    reps: dict[str, list] = {k: [] for k in ("edge_step", "e_half_eV", "wl_e_eV", "wl_h")}
    for _ in range(SEL_BOOTSTRAP):
        nb = normalize_fixed(E, mu + rng.normal(0, sig), e0s, np)
        if nb is None:
            continue
        reps["edge_step"].append(nb["step"])
        f = white_line(E, nb["norm"], e0s, np) or {}
        for k in ("e_half_eV", "wl_e_eV", "wl_h"):
            if f.get(k) is not None:
                reps[k].append(f[k])
    for k, v in reps.items():
        m[f"sd_{k}"] = float(np.std(v, ddof=1)) if len(v) > 5 else None
    return m


def _on_grid(sc: Mapping, grid, key: str, np):
    y = np.interp(grid, sc["energy"], sc[key])
    y[(grid < sc["energy"][0]) | (grid > sc["energy"][-1])] = np.nan
    return y


def _shift_fit(sc, grid, c, c_var, win, np):
    """The shift delta minimising chi2 of the scan at E+delta against the consensus on ``win``; sigma from the chi2
    curvature (scaled by chi2/nu when above 1).

    KNOWN BIAS, kept as the validated design has it (for the scientist's review): the noise at E+delta is the noise
    INTERPOLATED, not propagated, while a value interpolated between two points scatters less than either; so a
    fractional shift fits slightly better than none, and identical scans come out about +-0.4 of the point spacing
    apart (measured: +-0.06 eV on a real HERFD beamtime, +-0.1 eV on synthetic scans with a 0.25 eV step at the edge).
    Propagating it ((1-f)^2 s_j^2 + f^2 s_j+1^2) removes that, but moved 26 of 666 proposals on the real beamtime the
    design was validated on, including its step-at-start case, so it is not changed here."""
    ds = np.arange(-2.0, 2.0001, 0.02)
    chi = []
    with np.errstate(invalid="ignore", divide="ignore"):
        for d in ds:
            y = np.interp(grid[win] + d, sc["energy"], sc["norm"])
            s = np.interp(grid[win] + d, sc["energy"], sc["sig_norm"])
            chi.append(np.nansum((y - c[win]) ** 2 / (s ** 2 + c_var[win])))
    chi = np.array(chi)
    i = int(np.argmin(chi))
    lo, hi = max(i - 15, 0), min(i + 16, ds.size)  # +-0.3 eV: wider than the interpolation kinks
    a = np.polyfit(ds[lo:hi], chi[lo:hi], 2)[0] if hi - lo >= 3 else 0
    nu = max(int(win.sum()) - 1, 1)
    chi_nu = float(chi[i] / nu)
    sd = (1 / math.sqrt(a)) * math.sqrt(max(chi_nu, 1)) if a > 0 else None
    return float(ds[i]), sd, chi_nu, nu


def _consensus(members, grid, np):
    """Each point's mean of the members' normalised curves, weighted as a RAW-mu merge weighs them (by edge step)."""
    N = np.vstack([_on_grid(s, grid, "norm", np) for s in members])
    S = np.vstack([_on_grid(s, grid, "sig_norm", np) for s in members])
    with np.errstate(invalid="ignore", divide="ignore"):
        w = np.array([s["step"] for s in members])[:, None] * np.isfinite(N)
        c = np.nansum(np.nan_to_num(N) * w, axis=0) / np.sum(w, axis=0)
        var = np.nansum((np.nan_to_num(S) * w) ** 2, axis=0) / np.sum(w, axis=0) ** 2
    return c, var


def _artifacts(sc, grid, c, c_var, delta, e0s, i0_profile, np) -> list[dict]:
    """Clusters of points departing from the consensus by more than :data:`SEL_ARTIFACT_Z`, at most
    :data:`SEL_ARTIFACT_MAX_WIDTH` points wide, quiet either side: a spike (one point), a diffraction peak (a positive
    bump), a dip, or a beam drop (I0 under :data:`SEL_BEAM_DROP_FRAC` of its usual level there). A beam drop mu = If/I0
    divides out is listed too (``beam_drop_divided_out``)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        y = np.interp(grid + delta, sc["energy"], sc["norm"])
        s = np.interp(grid + delta, sc["energy"], sc["sig_norm"])
        inside = (grid + delta >= sc["energy"][0]) & (grid + delta <= sc["energy"][-1])
        z = np.where(inside, (y - c) / np.sqrt(s ** 2 + c_var), 0.0)
        z = np.nan_to_num(z, nan=0.0)
        i0r = (np.interp(grid, sc["energy"], sc["i0_ratio"]) / i0_profile
               if (i0_profile is not None and sc.get("i0_ratio") is not None) else None)
    flag = np.abs(z) > SEL_ARTIFACT_Z
    out, j = [], 0
    while j < grid.size:
        if not flag[j]:
            j += 1
            continue
        k = j
        while k + 1 < grid.size and flag[k + 1]:
            k += 1
        width = k - j + 1
        quiet = np.abs(z[max(j - 3, 0):j]).max(initial=0) < 3 and np.abs(z[k + 1:k + 4]).max(initial=0) < 3
        if width <= SEL_ARTIFACT_MAX_WIDTH and quiet:
            seg = slice(j, k + 1)
            amp = float(np.max(np.abs(y[seg] - c[seg])) * np.sign(np.sum(y[seg] - c[seg])))
            drop = bool(i0r is not None and np.nanmin(i0r[max(j - 1, 0):k + 2]) < SEL_BEAM_DROP_FRAC)
            kind = "beam_drop" if drop else ("spike" if width == 1 else ("diffraction_peak" if amp > 0 else "dip"))
            out.append({"kind": kind, "E_eV": [float(grid[j]), float(grid[k])], "points": width,
                        "amplitude_norm": amp, "max_abs_z": float(np.max(np.abs(z[seg]))),
                        "in_xanes": bool(e0s + SEL_XANES_WINDOW_EV[0] <= grid[j] <= e0s + SEL_XANES_WINDOW_EV[1])})
        j = k + 1
    if i0r is not None:
        low = np.flatnonzero(np.isfinite(i0r) & (i0r < SEL_BEAM_DROP_FRAC))
        said = {e for a in out for e in range(grid.size) if a["E_eV"][0] <= grid[e] <= a["E_eV"][1]}
        free = [int(i) for i in low if int(i) not in said]
        if free:
            out.append({"kind": "beam_drop_divided_out", "E_eV": [float(grid[free[0]]), float(grid[free[-1]])],
                        "points": len(free), "min_i0_fraction": float(np.nanmin(i0r[free]))})
    return out


def trend_test(t, m, sd, np) -> dict | None:
    """A weighted slope (inflated by excess scatter, Birge), its t-test, and the first-vs-last difference in units of
    the random scatter. ``None`` under 4 values."""
    stats = _stats()
    t, m = np.asarray(t, float), np.asarray(m, float)
    sd = np.asarray([x if (x and x > 0) else np.nan for x in sd], float)
    ok = np.isfinite(t) & np.isfinite(m) & np.isfinite(sd)
    t, m, sd = t[ok], m[ok], sd[ok]
    n = t.size
    if n < 4:
        return None
    w = 1 / sd ** 2
    tb = np.sum(w * t) / np.sum(w)
    Sxx = np.sum(w * (t - tb) ** 2)
    if not Sxx > 0:
        return None
    b = np.sum(w * (t - tb) * (m - np.sum(w * m) / np.sum(w))) / Sxx
    a = np.sum(w * m) / np.sum(w) - b * tb
    chi_nu = float(np.sum(w * (m - a - b * t) ** 2) / (n - 2))
    sb = math.sqrt(1 / Sxx) * math.sqrt(max(chi_nu, 1.0))
    tstat = b / sb
    p = float(2 * stats.t.sf(abs(tstat), n - 2))
    d2 = float(np.mean(np.diff(m) ** 2) / 2)  # von Neumann successive-difference variance
    s_rand = math.sqrt(max(float(np.mean(sd ** 2)), d2))
    k = 2 if n >= 6 else 1
    dfl = float(np.mean(m[-k:]) - np.mean(m[:k]))
    z_fl = dfl / (s_rand * math.sqrt(2 / k)) if s_rand > 0 else 0.0
    vn = float(np.sum(np.diff(m) ** 2) / np.sum((m - m.mean()) ** 2)) if np.ptp(m) > 0 else None
    return {"n": int(n), "slope_per_scan": float(b), "t": float(tstat), "p": p, "birge": math.sqrt(max(chi_nu, 0)),
            "drift": float(b * (t[-1] - t[0])), "first_last": dfl, "z_first_last": float(z_fl), "von_neumann": vn}


def _evolving(tr, metric: str) -> bool:
    """A SLOPE: significant, confirmed by first-vs-last, and larger than the physical floor."""
    return bool(tr and tr["p"] < SEL_ALPHA and abs(tr["z_first_last"]) >= SEL_FIRST_LAST_Z
                and abs(tr["drift"]) >= SEL_FLOOR[metric] and abs(tr["first_last"]) >= SEL_FLOOR[metric])


def _sd_key(k: str) -> str:
    return "sd_delta_eV" if k == "delta_eV" else f"sd_{k}"


def change_point(m, sd, metric: str, np):
    """A STEP at the start: the leading block (1..n-3 scans) against the rest, in pooled within-block scatter units,
    Bonferroni over the splits and the shape metrics. ``(split, z, diff, p)`` or ``None``."""
    stats = _stats()
    m = np.asarray(m, float)
    sd = np.asarray([x if (x and x > 0) else np.nan for x in sd], float)
    n = m.size
    if n < 4 or not np.isfinite(m).all() or not np.isfinite(sd).all():
        return None
    best = None
    for s in range(1, n - 2):
        a, b = m[:s], m[s:]
        within = np.concatenate([a - a.mean(), b - b.mean()])
        s_r = math.sqrt(max(float(np.sum(within ** 2) / max(n - 2, 1)), float(np.mean(sd ** 2))))
        z = (a.mean() - b.mean()) / (s_r * math.sqrt(1 / s + 1 / (n - s)))
        p = float(2 * stats.t.sf(abs(z), n - 2)) * (n - 3) * len(SEL_SHAPE_METRICS)
        if p < 0.01 and abs(a.mean() - b.mean()) >= SEL_FLOOR[metric] and (best is None or abs(z) > abs(best[1])):
            best = (s, float(z), float(a.mean() - b.mean()), p)
    return best


def _unstable(sub, np) -> list[str]:
    """The shape metrics in which a run of scans still changes: a slope, or a first-vs-last difference beyond noise
    and the floor."""
    bad = []
    for k in SEL_SHAPE_METRICS:
        v = [s["m"].get(k) for s in sub]
        sd = [s["m"].get(_sd_key(k)) for s in sub]
        if any(x is None for x in v) or any(not x for x in sd):
            continue
        v, sd = np.array(v, float), np.array(sd, float)
        if len(sub) >= 4:
            tr = trend_test(list(range(len(sub))), v, sd, np)
            if tr and tr["p"] < SEL_ALPHA and abs(tr["drift"]) >= SEL_FLOOR[k]:
                bad.append(k)
                continue
        kk = 2 if len(sub) >= 6 else 1
        d = float(v[-kk:].mean() - v[:kk].mean())
        s_r = math.sqrt(max(float(np.mean(sd ** 2)), float(np.mean(np.diff(v) ** 2) / 2)))
        if abs(d) >= SEL_FLOOR[k] and s_r > 0 and abs(d) / (s_r * math.sqrt(2 / kk)) >= SEL_FIRST_LAST_Z:
            bad.append(k)
    return bad


def detect_evolution(shape_ok, np, tr=None):
    """``(evolving metrics, change points, start of the stable window or None)``: a slope OR a step at the start.
    ``shape_ok`` is the scans in time order (each with its metrics ``m``)."""
    if tr is None:
        t = list(range(len(shape_ok)))
        tr = {k: trend_test(t, [s["m"].get(k) for s in shape_ok], [s["m"].get(_sd_key(k)) for s in shape_ok], np)
              for k in SEL_SHAPE_METRICS}
    evo = [k for k in SEL_SHAPE_METRICS if _evolving(tr.get(k), k)]
    cps = {}
    for k in SEL_SHAPE_METRICS:
        cp = change_point([s["m"].get(k) for s in shape_ok], [s["m"].get(_sd_key(k)) for s in shape_ok], k, np)
        if cp and not _unstable(shape_ok[cp[0]:], np):
            cps[k] = {"leading_scans": cp[0], "z": cp[1], "diff": cp[2], "p_bonferroni": cp[3]}
    evo = sorted(set(evo) | set(cps))
    if not evo:
        return evo, cps, None
    # the window starts after the LATEST change point (every metric settled), else the first stable suffix
    start = max((c["leading_scans"] for c in cps.values()), default=None)
    if start is None or _unstable(shape_ok[start:], np):
        start = next((s0 for s0 in range(1, len(shape_ok) - 2) if not _unstable(shape_ok[s0:], np)), None)
    return evo, cps, start


def _finite(obj):
    """A JSON-safe copy: non-finite floats become ``None``, numpy scalars plain numbers."""
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    if obj is None or isinstance(obj, (bool, str, int)):
        return obj
    kind = getattr(getattr(obj, "dtype", None), "kind", "")
    if kind == "b":
        return bool(obj)
    if kind in ("i", "u"):
        return int(obj)
    try:
        v = float(obj)
    except (TypeError, ValueError):
        return obj
    return v if math.isfinite(v) else None


def scan_selection(scans: Sequence[Mapping], e0s: float, np) -> dict:
    """THE PROPOSAL for one group's merge (:data:`SCAN_SELECTION_RULE_ID`). ``scans``: the group's energy scans in
    time order, each ``{"key", "number", "energy", "mu", "counts", "i0", "ring", "i0_nonpositive", "setup", "seed"}``
    (``number`` orders them in time; ``key`` is the caller's handle, returned as it came). ``e0s``: the SERIES E0 (one
    parameter set for every scan of the series). Nothing is dropped and nothing is merged here: every scan gets
    ``include`` | ``needs_look`` | ``exclude_proposed``, its reason codes, a sentence for each, and its metrics."""
    stats = _stats()
    work = []
    for s in scans:
        E = np.asarray(s["energy"], dtype=float)
        if E.size < 7:
            continue
        sc = {**s, "energy": E, "mu": np.asarray(s["mu"], dtype=float)}
        for k in ("counts", "i0", "ring"):
            sc[k] = np.asarray(s[k], dtype=float) if s.get(k) is not None else None
        work.append(sc)
    out: dict = {"rule_id": SCAN_SELECTION_RULE_ID, "e0_series_eV": float(e0s), "scans_evaluated": len(work),
                 "complete_scans": 0, "scans": [], "trend": {}, "change_point": {}, "evolving_metrics": [],
                 "stable_window": None, "edge_step_change": None, "group_observations": [], "merge_snr": None}
    if not work:
        return _finite(out)
    span = max(float(s["energy"][-1] - s["energy"][0]) for s in work)
    for sc in work:
        sc["m"] = _scan_metrics(sc, e0s, span, np)
    full = [s for s in work if s["m"]["complete"]]
    out["complete_scans"] = len(full)
    dec = {id(s): {"proposal": PROPOSAL_INCLUDE, "reasons": [], "said": []} for s in work}
    out["status"] = "evaluated"
    if not full:
        # NO scan reaches the series window (a XANES-only or calibration scan design): none can be judged with the
        # series parameters, so none is proposed (proposing every scan of the group for leaving out says nothing)
        out["status"] = "not_evaluated"
        out["detail"] = (f"no scan of the group reaches {e0s + SEL_NORM1_REL_EV + SEL_MIN_POST_EDGE_EV:.1f} eV "
                         f"(E0+{SEL_NORM1_REL_EV + SEL_MIN_POST_EDGE_EV:g}) with {SEL_COVERAGE_MIN:.0%} of the widest "
                         "scan's range, so none can be normalised with the series parameters; nothing is proposed")
        for s in work:
            dec[id(s)] = {"proposal": PROPOSAL_NOT_EVALUATED, "reasons": ["series_window_not_reached"],
                          "said": [out["detail"]]}

    def say(s, prop, code, text):
        d = dec[id(s)]
        if _PROPOSAL_ORDER[prop] > _PROPOSAL_ORDER[d["proposal"]]:
            d["proposal"] = prop
        if code not in d["reasons"]:
            d["reasons"].append(code)
            d["said"].append(text)

    for s in work if full else ():
        m = s["m"]
        if m.get("normalization_failed"):
            say(s, PROPOSAL_LOOK, "normalization_failed",
                "the series parameters give no positive edge step for this scan")
        elif not m["complete"]:
            say(s, PROPOSAL_EXCLUDE, "incomplete_scan",
                f"stops at {m['E_last_eV']:.1f} eV after {m['points']} points (it must reach "
                f"{e0s + SEL_NORM1_REL_EV + SEL_MIN_POST_EDGE_EV:.1f} eV and cover {SEL_COVERAGE_MIN:.0%} of the "
                "group's widest scan); it cannot be normalised alone")

    def result():
        for s in work:
            out["scans"].append({"key": s.get("key"), "number": s.get("number"), **dec[id(s)], "metrics": s["m"]})
        inc = [s for s in full if dec[id(s)]["proposal"] == PROPOSAL_INCLUDE]
        msnr: dict = {"proposed_scans": [s.get("number") for s in inc]}
        if inc:
            st = np.array([s["m"]["edge_step"] for s in inc])
            sp = np.array([s["m"]["noise_post_mu"] for s in inc])
            msnr["proposed"] = float(st.sum() / math.sqrt(np.sum(sp ** 2)))
        if full:
            st = np.array([s["m"]["edge_step"] for s in full])
            sp = np.array([s["m"]["noise_post_mu"] for s in full])
            msnr["all_complete"] = float(st.sum() / math.sqrt(np.sum(sp ** 2)))
        out["merge_snr"] = msnr
        return _finite(out)

    if not full:
        return result()
    # setup consistency (emission energy, filter...)
    for key, tol in SEL_SETUP_KEYS:
        vals = [s["m"].get(key) for s in full if s["m"].get(key) is not None]
        if vals:
            mode = max(sorted(set(vals)), key=vals.count)
            for s in full:
                v = s["m"].get(key)
                if v is not None and abs(v - mode) > tol:
                    say(s, PROPOSAL_LOOK, f"setup_differs_{key}", f"{key} {v:g} where the group's other scans have {mode:g}")
    for s in full:
        if s["m"]["edge_snr"] is None or s["m"]["edge_snr"] < SEL_EVAL_SNR_MIN:
            say(s, PROPOSAL_LOOK, "too_noisy_to_evaluate",
                f"edge step only {s['m']['edge_snr'] or 0:.1f} x its per-point noise: alone it cannot be judged")
        F = s["m"].get("F_post")
        if F and F > SEL_EXCESS_NOISE_LOOK:
            say(s, PROPOSAL_LOOK, "excess_noise",
                f"noise {F:.1f} x what counting statistics give (bubbles, vibration or a detector problem?)")
        if s["m"]["i0_nonpositive"]:
            say(s, PROPOSAL_LOOK, "i0_nonpositive", f"{s['m']['i0_nonpositive']} points with I0 <= 0")
    good = [s for s in full if dec[id(s)]["proposal"] != PROPOSAL_EXCLUDE]
    grid = (good or full)[0]["energy"]
    win = (grid >= e0s + SEL_XANES_WINDOW_EV[0]) & (grid <= e0s + SEL_XANES_WINDOW_EV[1])
    i0_prof = None
    if len(full) >= 2 and all(s.get("i0_ratio") is not None for s in full):
        with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
            warnings.simplefilter("ignore", RuntimeWarning)
            for s in full:
                med = float(np.median(s["i0_ratio"]))
                s["i0_ratio"] = s["i0_ratio"] / med if med > 0 else s["i0_ratio"] * np.nan
            R = np.vstack([_on_grid({"energy": s["energy"], "r": s["i0_ratio"]}, grid, "r", np) for s in full])
            i0_prof = np.nanmedian(R, axis=0)

    def sig_merge(members):
        return np.sqrt(np.nansum(np.vstack([_on_grid(o, grid, "sig", np) for o in members]) ** 2, axis=0))

    def consistency(members_for_consensus, targets):
        res = {}
        for s in targets:
            others = [o for o in members_for_consensus if o is not s]
            if not others:
                continue
            c, c_var = _consensus(others, grid, np)
            d, sd_d, chi_nu, nu = _shift_fit(s, grid, c, c_var, win & np.isfinite(c), np)
            # the bias this scan puts on a RAW-mu merge, against that merge's own noise (unshifted: the merge does
            # not align)
            members = others + [s]
            steps = np.array([o["step"] for o in members])
            with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                dif = (_on_grid(s, grid, "norm", np) - c)[win]
                sm = sig_merge(members)[win]
                bias = s["step"] * dif / len(members)
                R = float(np.sqrt(np.nanmean((bias / (sm / len(members))) ** 2)))
            sig_post = np.array([o["m"]["noise_post_mu"] for o in members])
            snr_with = steps.sum() / math.sqrt(np.sum(sig_post ** 2))
            snr_without = steps[:-1].sum() / math.sqrt(np.sum(sig_post[:-1] ** 2))
            res[id(s)] = {"delta_eV": d, "sd_delta_eV": sd_d, "chi2_nu_shifted": chi_nu, "nu": nu,
                          "visible_bias_R": R, "merge_snr_with": float(snr_with),
                          "merge_snr_without": float(snr_without),
                          "artifacts": _artifacts(s, grid, c, c_var, d, e0s, i0_prof, np)}
        return res

    cons = consistency(good, good) if len(good) >= 2 else {}
    for s in good:
        if id(s) in cons:
            s["m"].update({k: v for k, v in cons[id(s)].items() if k != "artifacts"})
    # ---- trend and change point ----
    shape_ok = [s for s in good if "delta_eV" in s["m"]]
    good_w = shape_ok
    if len(shape_ok) >= 4:
        t = [s.get("number") for s in shape_ok]
        tr = {k: trend_test(t, [s["m"].get(k) for s in shape_ok], [s["m"].get(_sd_key(k)) for s in shape_ok], np)
              for k in ("delta_eV", "wl_e_eV", "wl_h", "e_half_eV", "edge_step")}
        out["trend"] = tr
        evo, cps, start = detect_evolution(shape_ok, np, tr)
        out["change_point"] = cps
        out["evolving_metrics"] = evo
        if evo:
            if start is not None:
                win_scans = shape_ok[start:]
                out["stable_window"] = [s.get("number") for s in win_scans]
                for s in shape_ok[:start]:
                    parts = [f"{k} {s['m'][k] - np.mean([w['m'][k] for w in win_scans]):+.3g} from the stable scans"
                             for k in evo]
                    say(s, PROPOSAL_EXCLUDE, "before_stable_window",
                        "the sample was still changing (" + ", ".join(parts) + ")")
                good_w = win_scans
            else:
                for s in shape_ok:
                    say(s, PROPOSAL_LOOK, "still_evolving_no_stable_window",
                        "the sample is still changing at the end of the series: " + ", ".join(evo))
    # ---- shape outliers and artifacts, against the (stable) consensus ----
    if len(good_w) >= 2:
        cons2 = consistency(good_w, shape_ok)
        chis = [cons2[id(s)]["chi2_nu_shifted"] for s in good_w if id(s) in cons2]
        med = float(np.median(chis)) if chis else 1.0
        out["chi2_nu_median"] = med
        ds_w = np.array([cons2[id(w)]["delta_eV"] for w in good_w if id(w) in cons2])
        spread = 1.4826 * float(np.median(np.abs(ds_w - np.median(ds_w)))) if ds_w.size >= 4 else 0.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            noise_w = sig_merge(good_w)
        for s in shape_ok:
            r = cons2.get(id(s))
            if not r:
                continue
            s["m"]["vs_stable"] = {k: v for k, v in r.items() if k != "artifacts"}
            s["m"]["artifacts"] = r["artifacts"]
            nu = r["nu"]
            crit = max(float(stats.chi2.isf(SEL_CHI2_P, nu)) / nu, SEL_CHI2_MEDIAN_FACTOR * med)
            if len(good_w) >= 4 and r["chi2_nu_shifted"] > crit:
                if r["visible_bias_R"] >= SEL_VISIBLE_R:
                    say(s, PROPOSAL_EXCLUDE, "shape_out_of_trend",
                        f"shape differs (chi2/nu {r['chi2_nu_shifted']:.2f} vs group median {med:.2f}) and would move "
                        f"the merge {r['visible_bias_R']:.1f} x its noise")
                else:
                    say(s, PROPOSAL_INCLUDE, "differs_below_merge_noise",
                        f"shape differs (chi2/nu {r['chi2_nu_shifted']:.2f}) but would move the merge only "
                        f"{r['visible_bias_R']:.2f} x its noise")
            visible = 0
            for a in r["artifacts"]:
                if a["kind"] == "beam_drop_divided_out":
                    txt = (f"I0 fell to {a['min_i0_fraction']:.0%} of its usual level at {a['E_eV'][0]:.1f}-"
                           f"{a['E_eV'][1]:.1f} eV (ring current divided out); mu = If/I0 shows no departure there")
                    if a["min_i0_fraction"] < SEL_BEAM_DROP_LOOK:
                        say(s, PROPOSAL_LOOK, "beam_drop", txt)
                    else:
                        say(s, PROPOSAL_INCLUDE, "beam_dip_divided_out", txt)
                    continue
                at = float(np.interp(a["E_eV"][0], grid, np.nan_to_num(noise_w, nan=0.0)))
                vis = (abs(a["amplitude_norm"]) * s["step"] / len(good_w) / (at / len(good_w))) if at > 0 else math.inf
                a["visible_in_merge"] = float(vis) if math.isfinite(vis) else None
                txt = (f"{a['kind']} at {a['E_eV'][0]:.1f}-{a['E_eV'][1]:.1f} eV ({a['points']} pt, "
                       f"{a['amplitude_norm']:+.3f} of the edge step, z {a['max_abs_z']:.0f}); "
                       f"{vis:.1f} x the merge's noise there")
                if vis >= SEL_VISIBLE_R:
                    visible += 1
                    say(s, PROPOSAL_LOOK, f"artifact_{a['kind']}",
                        txt + ("" if a["in_xanes"] else " (outside the XANES window)") + "; remove these points, or the scan")
                else:
                    say(s, PROPOSAL_INCLUDE, f"artifact_{a['kind']}_below_merge_noise", txt)
            if visible >= SEL_MANY_ARTIFACTS:
                say(s, PROPOSAL_EXCLUDE, "many_artifacts", f"{visible} artifacts each visible in the merge")
            if r["merge_snr_with"] < r["merge_snr_without"] * SEL_SNR_LOWERED:
                say(s, PROPOSAL_EXCLUDE, "lowers_merge_snr",
                    f"merged edge SNR {r['merge_snr_without']:.0f} without it, {r['merge_snr_with']:.0f} with it")
            off = r["delta_eV"] - (float(np.median(ds_w)) if ds_w.size else 0.0)
            lim = max(SEL_SHIFT_MIN_EV, 3 * (r["sd_delta_eV"] or 0), SEL_SHIFT_SPREAD_FACTOR * spread)
            if len(good_w) >= 4 and abs(off) > lim and "before_stable_window" not in dec[id(s)]["reasons"]:
                say(s, PROPOSAL_LOOK, "energy_shifted",
                    f"{off:+.2f} eV from the other scans (their robust spread {spread:.2f} eV)")
    # ---- two and three scans: pairwise only, honest about what cannot be told ----
    if len(shape_ok) in (2, 3):
        pair = []
        for i, a in enumerate(shape_ok):
            for b in shape_ok[i + 1:]:
                zs = []
                for k in ("e_half_eV", "wl_e_eV", "wl_h"):
                    va, vb = a["m"].get(k), b["m"].get(k)
                    sa, sb = a["m"].get(f"sd_{k}"), b["m"].get(f"sd_{k}")
                    fl = SEL_FLOOR.get(k, SEL_FLOOR["wl_e_eV"])
                    if None not in (va, vb, sa, sb) and sa > 0 and sb > 0:
                        z = (vb - va) / math.hypot(sa, sb)
                        if abs(z) >= SEL_FIRST_LAST_Z and abs(vb - va) >= fl:
                            zs.append(f"{k} {vb - va:+.3g} ({z:+.1f} sigma)")
                pair.append((a, b, zs))
        bad = [p for p in pair if p[2]]
        if len(shape_ok) == 2 and bad:
            for s in shape_ok:
                say(s, PROPOSAL_LOOK, "two_scans_disagree",
                    "the two scans differ: " + "; ".join(bad[0][2]) + "; two scans cannot say which, or whether the "
                    "sample changed")
        if len(shape_ok) == 3 and bad:
            odd = [s for s in shape_ok if all(s is p[0] or s is p[1] for p in bad)]
            if len(bad) == 2 and len(odd) == 1:
                say(odd[0], PROPOSAL_LOOK, "odd_one_of_three", "differs from the other two, which agree")
            else:
                for s in shape_ok:
                    say(s, PROPOSAL_LOOK, "three_scans_change",
                        "the three scans differ beyond noise; three scans cannot tell a trend from one bad scan")
    # ---- intensity: an observation, never a reason ----
    steps = [(s.get("number"), s["m"]["edge_step"]) for s in shape_ok]
    if len(steps) >= 2:
        first, last = steps[0][1], steps[-1][1]
        ch = last / first - 1
        tr_s = (out["trend"] or {}).get("edge_step")
        out["edge_step_change"] = {"first": first, "last": last, "relative": ch,
                                   "max_over_min": max(v for _, v in steps) / min(v for _, v in steps),
                                   "trend_p": tr_s["p"] if tr_s else None}
        if abs(ch) >= SEL_EDGE_STEP_OBSERVED:
            out["group_observations"].append(
                f"edge step {'fell' if ch < 0 else 'grew'} {abs(ch):.0%} from scan {steps[0][0]} to scan {steps[-1][0]} "
                f"({first:.4g} -> {last:.4g})"
                + (" - possible dissolution or detachment of the sample; a scientist judges" if ch < 0 else "")
                + ". Not a reason to leave a scan out: the merge is raw mu.")
    return result()
