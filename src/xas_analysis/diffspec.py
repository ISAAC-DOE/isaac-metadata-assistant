"""Difference spectra and their decomposition (scale, onset shift, broadening, remaining shape).

Lessons from the BL6-2 2018 Pt L3 / Nature Mater. 2025 Fig. 2b comparison:
- the depth of a difference-spectrum minimum mixes a normalization (edge-step) factor with real
  changes; the onset shift is robust to the reduction method;
- a model-free relative normalization (raw IF/I0 minus the pre-edge level, each spectrum scaled to
  the reference over a common post-edge window) is a check for any edge-step model.

Model fitted to a difference spectrum d(E) = S(E) - R(E) on a common grid:

    d(E) = a R(E) + dE (-dR/dE) + w d2R/dE2 + remainder(E)

a: relative scale (normalization-sensitive), dE: onset shift in eV (positive = S at higher
energy), w: broadening in eV^2 (Gaussian broadening by sigma adds w = sigma^2 / 2), remainder:
shape change not explained by the three. Derivatives are taken on R smoothed by a Gaussian of
`sigma_eV` (piecewise-linear interpolation makes raw second derivatives spiky).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def boxcar(y, n: int = 5):
    """Athena-style boxcar smoothing (edge values repeated)."""
    y = np.asarray(y, float)
    if n <= 1:
        return y
    yp = np.r_[np.repeat(y[0], n // 2), y, np.repeat(y[-1], n // 2)]
    return np.convolve(yp, np.ones(n) / n, "valid")


def difference(E, y, E_ref, y_ref, grid, smooth: int = 0):
    """S - R on `grid` (both optionally boxcar-smoothed on their own points first)."""
    return np.interp(grid, E, boxcar(y, smooth)) - np.interp(grid, E_ref, boxcar(y_ref, smooth))


def _post_mask(E, post, exclude):
    m = (E >= post[0]) & (E <= post[1])
    for lo, hi in exclude or []:
        m &= ~((E >= lo) & (E <= hi))
    return m


def model_free_difference(E, y_raw, E_ref, y_ref_raw, grid, pre, post, exclude=None, smooth: int = 0):
    """Normalization-model-free difference spectrum.

    Each raw IF/I0 minus its median over `pre`; the sample is scaled to the reference over `post`
    (least squares, `exclude` windows removed, e.g. a glitch); the result is in units of the
    reference's mean post-edge level. Assumes a flat background between pre and post (HERFD) and
    the same post-edge shape over `post` for both spectra. Returns (difference, scale)."""
    E, y, E_ref, yr = map(lambda a: np.asarray(a, float), (E, y_raw, E_ref, y_ref_raw))
    y = y - np.median(y[(E >= pre[0]) & (E <= pre[1])])
    yr = yr - np.median(yr[(E_ref >= pre[0]) & (E_ref <= pre[1])])
    mr = _post_mask(E_ref, post, exclude)
    level = float(np.mean(yr[mr]))
    m = _post_mask(E, post, exclude)
    r_on_s = np.interp(E[m], E_ref, yr)
    s = float(np.dot(y[m], r_on_s) / np.dot(y[m], y[m]))
    d = (np.interp(grid, E, boxcar(s * y, smooth)) - np.interp(grid, E_ref, boxcar(yr, smooth))) / level
    return d, s


@dataclass
class Decomposition:
    scale: float
    shift_eV: float
    broadening_eV2: float
    explained: float                      # fraction of the variance of d explained by the 3 terms
    stderr: dict = field(default_factory=dict)
    grid: np.ndarray | None = None
    data: np.ndarray | None = None
    components: dict = field(default_factory=dict)   # scale / shift / broadening / remainder arrays

    def summary(self) -> str:
        e = self.stderr
        return (f"scale {100 * self.scale:+.2f}% (±{100 * e.get('scale', np.nan):.2f}), "
                f"shift {1000 * self.shift_eV:+.0f} meV (±{1000 * e.get('shift_eV', np.nan):.0f} stat), "
                f"broadening {1000 * self.broadening_eV2:+.1f}e-3 eV², explained {100 * self.explained:.0f}%")


def decompose(grid, d, E_ref, y_ref, sigma_eV: float = 0.1, smooth: int = 0, window=None) -> Decomposition:
    """Fit d = a R + dE (-dR/dE) + w d2R/dE2 on `grid` (optionally restricted to `window`).

    R is y_ref (boxcar `smooth` if given, as used for d) on the grid; its derivatives use an extra
    Gaussian of sigma_eV. stderr: least-squares standard errors from the residual (statistical
    only; add the energy-alignment uncertainty of both spectra to shift_eV separately)."""
    g = np.asarray(grid, float)
    d = np.asarray(d, float)
    R = np.interp(g, E_ref, boxcar(y_ref, smooth))
    step = float(np.median(np.diff(g)))
    half = max(1, int(round(4 * sigma_eV / step)))
    k = np.exp(-0.5 * (np.arange(-half, half + 1) * step / sigma_eV) ** 2)
    k /= k.sum()
    Rs = np.convolve(np.r_[np.repeat(R[0], half), R, np.repeat(R[-1], half)], k, "valid")
    dR = np.gradient(Rs, g)
    d2R = np.gradient(dR, g)
    B = np.column_stack([R, -dR, d2R])
    m = np.isfinite(d) if window is None else np.isfinite(d) & (g >= window[0]) & (g <= window[1])
    c, *_ = np.linalg.lstsq(B[m], d[m], rcond=None)
    fit = B @ c
    res = d - fit
    dof = max(1, int(m.sum()) - 3)
    s2 = float(np.sum(res[m] ** 2) / dof)
    try:
        cov = s2 * np.linalg.inv(B[m].T @ B[m])
        se = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        se = np.full(3, np.nan)
    explained = 1 - float(np.sum(res[m] ** 2) / np.sum(d[m] ** 2)) if np.any(d[m]) else np.nan
    return Decomposition(float(c[0]), float(c[1]), float(c[2]), explained,
                         {"scale": float(se[0]), "shift_eV": float(se[1]), "broadening_eV2": float(se[2])},
                         g, d, {"scale": B[:, 0] * c[0], "shift": B[:, 1] * c[1], "broadening": B[:, 2] * c[2],
                                "remainder": res})
