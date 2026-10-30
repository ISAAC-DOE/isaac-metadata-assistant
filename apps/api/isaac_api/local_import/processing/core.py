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
    """Energy-sorted, duplicate-merged, finite (energy, mu[, mu_ref]) for one scan + diagnostics."""
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

    steps = np.diff(E)
    diag["nonmonotonic_steps"] = int(np.sum(steps <= 0))
    order = np.argsort(E, kind="stable")
    E, mu = E[order], mu[order]
    mu_ref = mu_ref[order] if mu_ref is not None else None
    finite = np.isfinite(E) & np.isfinite(mu)
    diag["nonfinite_dropped"] = int(np.sum(~finite))
    E, mu = E[finite], mu[finite]
    mu_ref = mu_ref[finite] if mu_ref is not None else None
    key = np.round(E, 6)
    uniq, inverse, counts = np.unique(key, return_inverse=True, return_counts=True)
    diag["duplicate_energies_merged"] = int(np.sum(counts > 1))
    if uniq.size != E.size:
        mu = np.bincount(inverse, weights=mu) / counts
        if mu_ref is not None:
            ok = np.isfinite(mu_ref)
            num = np.bincount(inverse, weights=np.where(ok, mu_ref, 0.0))
            den = np.bincount(inverse, weights=ok.astype(float))
            mu_ref = np.where(den > 0, num / np.maximum(den, 1), np.nan)
        E = uniq
    diag["points_used"] = int(E.size)
    return {"energy": E, "mu": mu, "mu_ref": mu_ref, "diagnostics": diag}


#: A scan with fewer usable points than this is skipped.
MIN_SCAN_POINTS = 5
SIGNAL_NOT_FINITE = "signal_not_finite"


def unusable_reason(sa: Mapping) -> str | None:
    """Why a scan's arrays (:func:`scan_arrays`) cannot be used, or ``None``.

    ``signal_not_finite`` when the scan HAS the points but its chosen signal is non-finite at
    too many of them (I0 or I1 not positive): measured on a real BL4-3 dilute standard, I1 is
    negative at all 303 points, so ln(I0/I1) dropped every one — that is not ``too_few_points``.
    """
    if sa["energy"].size >= MIN_SCAN_POINTS:
        return None
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
            kwargs["nnorm"] = 1  # a quadratic over < 100 eV is not constrained; recorded below
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
    if (metrics.get("i0_nonpositive_fraction") or 0) > float(q["fail_i0_nonpositive_fraction"]):
        fail.append("i0_nonpositive")
    if metrics.get("signal_all_zero_scans"):
        fail.append("signal_all_zero")
    if metrics.get("scans_used") is not None and metrics["scans_used"] < int(q["warn_min_scans"]):
        warn.append("single_scan")
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
