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
    if (metrics.get("i0_nonpositive_fraction") or 0) > float(q["fail_i0_nonpositive_fraction"]):
        fail.append("i0_nonpositive")
    if metrics.get("signal_all_zero_scans"):
        fail.append("signal_all_zero")
    if metrics.get("scans_used") is not None and metrics["scans_used"] < int(q["warn_min_scans"]):
        warn.append("single_scan")
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
