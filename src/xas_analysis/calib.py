"""Energy calibration: anchor location (find_inflection_point.m) and shift + resample
(align_and_resample.m)."""
from __future__ import annotations

import warnings

import numpy as np

from .matlab_compat import gradient, interp1_linear, movmean


def find_inflection_point(E, y, window_eV, smooth_pts: int = 1, sign: int = 0,
                          min_points: int = 5) -> tuple[float, dict]:
    """Energy of max |dy/dE| inside window_eV, refined by a 3-point parabola.

    sign: +1 rising only, -1 falling only, 0 either. Returns (E_inflect, info);
    E_inflect is NaN on failure (info['reason'] says why).
    """
    info = {"E_inflect_raw": np.nan, "dydE_max": np.nan, "idx_window": np.empty(0, int),
            "ok": False, "reason": ""}
    E = np.asarray(E, float).ravel()
    y = np.asarray(y, float).ravel()
    if E.size != y.size:
        info["reason"] = "E and y length mismatch"
        return np.nan, info
    if len(window_eV) != 2:
        info["reason"] = "window_eV must be [E_lo, E_hi]"
        return np.nan, info
    lo, hi = min(window_eV), max(window_eV)
    if E[-1] < E[0]:
        E, y = E[::-1], y[::-1]
    in_win = (E >= lo) & (E <= hi)
    info["idx_window"] = np.flatnonzero(in_win)
    if in_win.sum() < min_points:
        info["reason"] = f"only {in_win.sum()} points in [{lo:.3f}, {hi:.3f}] eV (need {min_points})"
        return np.nan, info
    Ew, yw = E[in_win], y[in_win]
    if smooth_pts > 1:
        yw = movmean(yw, smooth_pts)
    dy = gradient(yw, Ew)
    signal = dy if np.sign(sign) > 0 else (-dy if np.sign(sign) < 0 else np.abs(dy))
    k = int(np.argmax(signal))  # first max, as MATLAB max
    info["dydE_max"] = float(signal[k])
    info["E_inflect_raw"] = float(Ew[k])
    if 0 < k < Ew.size - 1:
        x3, s3 = Ew[k - 1:k + 2], signal[k - 1:k + 2]
        # centred abscissae: MATLAB fits raw eV (~1e4) and loses ~1e-6 eV to conditioning;
        # centring gives the exact vertex of the 3-point parabola
        p = np.polyfit(x3 - Ew[k], s3, 2)
        if p[0] != 0:
            xp = Ew[k] - p[1] / (2 * p[0])
            if x3[0] <= xp <= x3[2]:
                info["ok"] = True
                return float(xp), info
    info["reason"] = "parabolic refinement skipped (edge of window or degenerate fit)"
    return info["E_inflect_raw"], info


def align_and_resample(E_src, y_src, anchor_src_eV: float, anchor_target_eV: float,
                       E_target, require_overlap_frac: float = 0.5) -> tuple[np.ndarray, dict]:
    """Shift E_src by (anchor_target - anchor_src) and linearly resample y onto E_target.

    One interpolation (the legacy energy_calibration_xas_glitch.m did two that cancelled).
    Outside the source range the result is NaN.
    """
    E_src = np.asarray(E_src, float).ravel()
    E_target = np.asarray(E_target, float).ravel()
    Y = np.asarray(y_src, float)
    if Y.ndim == 2 and Y.shape[0] != E_src.size and Y.shape[1] == E_src.size:
        Y = Y.T
    if Y.shape[0] != E_src.size:
        raise ValueError("y_src first dimension must match E_src length")
    shift = anchor_target_eV - anchor_src_eV
    Es = E_src + shift
    info = {"shift_eV": shift, "src_range_eV": (float(Es.min()), float(Es.max())),
            "target_inside_frac": 0.0, "ok": False}
    inside = (E_target >= Es.min()) & (E_target <= Es.max())
    info["target_inside_frac"] = inside.sum() / E_target.size
    if info["target_inside_frac"] < require_overlap_frac:
        warnings.warn(f"align_and_resample: only {100 * info['target_inside_frac']:.0f}% of target "
                      f"grid covered after shift {shift:.3f} eV")
    if np.any(np.diff(Es) <= 0):
        srt = np.argsort(Es, kind="stable")
        Es, Y = Es[srt], Y[srt]
        keep = np.concatenate([[True], np.diff(Es) > 0])
        Es, Y = Es[keep], Y[keep]
    out = interp1_linear(Es, Y, E_target)
    sel = out[inside] if out.ndim == 1 else out[inside, :]
    if sel.ndim == 2:   # ignore input columns that are entirely missing (e.g. no 'sec' column)
        present = np.any(np.isfinite(Y), axis=0)
        sel = sel[:, present]
    info["ok"] = bool(np.all(np.isfinite(sel)))
    return out, info


def fit_glitch_center(E, lnI0, window_eV, max_sigma_eV: float = 2.0) -> tuple[float, dict]:
    """Centre of an I0 glitch: Gaussian dip + linear trend fitted to ln I0 inside window_eV.

    Template-free, so it does not inherit any scan's sampling: a narrow glitch sampled at
    ~2 points per FWHM biases a template match by 10-40 meV with the grid phase (BL15-2
    2025), the model fit by < 1 meV (synthetic). Returns (centre_eV, info)."""
    from scipy.optimize import least_squares
    E = np.asarray(E, float).ravel()
    y = np.asarray(lnI0, float).ravel()
    lo, hi = min(window_eV), max(window_eV)
    m = (E >= lo) & (E <= hi) & np.isfinite(y)
    info = {"ok": False, "reason": "", "sigma_eV": np.nan, "depth": np.nan}
    if m.sum() < 6:
        info["reason"] = "fewer than 6 points in the glitch window"
        return np.nan, info
    x, z = E[m], y[m]
    c0 = 0.5 * (lo + hi)

    def res(p):
        return p[0] + p[1] * (x - c0) - p[2] * np.exp(-0.5 * ((x - p[3]) / p[4]) ** 2) - z
    k = int(np.argmin(z))
    p0 = [np.median(z), 0.0, max(1e-5, np.median(z) - z[k]), x[k], 0.25]
    sol = least_squares(res, p0, bounds=([-np.inf, -np.inf, 0.0, lo, 0.03],
                                         [np.inf, np.inf, np.inf, hi, max_sigma_eV]))
    c, s, d = sol.x[3], sol.x[4], sol.x[2]
    edge = min(c - lo, hi - c) < 0.5 * s
    info.update(ok=bool(sol.success and d > 0 and not edge), sigma_eV=float(s), depth=float(d),
                reason="" if not edge else "centre at the window edge")
    return float(c), info


def fit_glitch_doublet(E, lnI0, window_eV, sep_eV=(0.8, 2.2), max_sigma_eV: float = 0.8,
                       min_depth: float = 0.003) -> tuple[float, dict]:
    """Centre (midpoint) of a DOUBLE I0 glitch: two Gaussian dips with a shared width and free
    separation + linear trend, fitted to ln I0 inside window_eV.

    A single-dip fit on a doublet jumps between the two dips from scan to scan (BL15-2 2019 Pt
    L3: dips at ~11702.1 / 11703.5 eV, anchors bimodal by 1.4 eV); the midpoint of a doublet fit
    does not, whatever the relative depths. ok is False when a dip vanishes (< min_depth) or the
    separation hits its bounds. Returns (midpoint_eV, info)."""
    from scipy.optimize import least_squares
    E = np.asarray(E, float).ravel()
    y = np.asarray(lnI0, float).ravel()
    lo, hi = min(window_eV), max(window_eV)
    m = (E >= lo) & (E <= hi) & np.isfinite(y)
    info = {"ok": False, "reason": "", "sigma_eV": np.nan, "sep_eV": np.nan, "depths": (np.nan, np.nan)}
    if m.sum() < 10:
        info["reason"] = "fewer than 10 points in the glitch window"
        return np.nan, info
    x, z = E[m], y[m]
    c0 = 0.5 * (lo + hi)
    s_lo, s_hi = sep_eV

    def res(p):
        c, d, s, a1, a2, b0, b1 = p
        return (b0 + b1 * (x - c0) - a1 * np.exp(-0.5 * ((x - (c - d / 2)) / s) ** 2)
                - a2 * np.exp(-0.5 * ((x - (c + d / 2)) / s) ** 2) - z)
    p0 = [c0, 0.5 * (s_lo + s_hi), 0.3, 0.01, 0.01, np.median(z), 0.0]
    lb = [lo + s_lo / 2, s_lo, 0.05, 0.0, 0.0, -np.inf, -np.inf]
    ub = [hi - s_lo / 2, s_hi, max_sigma_eV, np.inf, np.inf, np.inf, np.inf]
    sol = least_squares(res, np.clip(p0, np.array(lb) + 1e-9, np.array(ub) - 1e-9), bounds=(lb, ub))
    c, d, s, a1, a2 = sol.x[:5]
    at_bound = d < s_lo + 0.02 or d > s_hi - 0.02
    weak = min(a1, a2) < min_depth
    info.update(ok=bool(sol.success and not at_bound and not weak), sigma_eV=float(s), sep_eV=float(d),
                depths=(float(a1), float(a2)),
                reason="separation at its bound" if at_bound else ("one dip vanished" if weak else ""))
    return float(c), info
