"""Hard-XAS component-fit background subtraction + normalization (port of mback_v4.m).

Model, fitted on the pre- and post-edge regions only (the XANES region is excluded):

    raw(E) = A_edge * mu_atomic(E)                  McMaster step, unit edge jump
           + A_erfc * erfc((E - E_fluo) / xi)       optional fluorescence envelope
           + poly_pre(E - E_edge)                        all E
           + poly_post(E - E_edge)  (no constant term)  for E >= E_edge

The background is continuous at E_edge (bg_continuity=True, default since 2026-11-09), so
the edge step can only be carried by A_edge * mu. With bg_continuity=False the post-edge
polynomial is independent and has its own constant, exactly as mback_v4.m:

           + poly_pre(E - E_edge)   for E <  E_edge
           + poly_post(E - E_edge)  for E >= E_edge

That form leaves A_edge unidentified (the post constant absorbs the step; Ti K BL4-3 gives
A ~ 1e3 at the exact minimum, chi2 flat over A = 0.5-100; docs/PORT_STATUS.md finding 0).
Keep it only for comparison with legacy MATLAB output.

Output: norm_xas = (raw - bg) / A_edge  (~0 below the edge, ~1 on the post-edge plateau).
Energies are handled in keV internally, as in MATLAB (polynomial coefficients are per keV).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.special import erfc

from ..physics.mcmaster import atomic_number, element, mcmaster


@dataclass
class MbackResult:
    energy_eV: np.ndarray
    norm_xas: np.ndarray
    mu: np.ndarray
    info: dict = field(default_factory=dict)


def _edge(Z: int, core: str, E_keV: np.ndarray) -> tuple[float, float]:
    el = element(Z)
    rows = [(el["K_edge"], el["K_alpha1"])]
    rows += [(L, el["L_alpha1"]) for L in el["L_edge"]]
    rows += [(el["M_edge"], 0.0)]
    names = {"K": 0, "L1": 1, "L2": 2, "L3": 3, "M1": 4}
    c = (core or "").upper()
    if c in names:
        return rows[names[c]]
    if c == "":
        for e, f in rows:  # first tabulated edge inside the data range, order K, L1-3, M
            if E_keV[0] < e < E_keV[-1]:
                return e, f
        raise ValueError("mback: no tabulated edge in data energy range.")
    raise ValueError(f"mback: {core} edge not supported.")


def fit_windows(E_eV, E_edge, range_eV):
    """Pre/post masks. range_eV: None (E_edge-20 / E_edge+80 eV), [pre_offset, post_offset]
    relative to the edge in eV, or [pre_lo, pre_hi, post_lo, post_hi] absolute in eV."""
    E = E_eV / 1000.0
    if range_eV is None or len(range_eV) == 0:
        return E <= E_edge - 0.020, E >= E_edge + 0.080
    if len(range_eV) == 4:
        r = range_eV
        return (E_eV >= r[0]) & (E_eV <= r[1]), (E_eV >= r[2]) & (E_eV <= r[3])
    if len(range_eV) == 2:
        return E <= E_edge - range_eV[0] / 1000, E >= E_edge + range_eV[1] / 1000
    raise ValueError("mback: range must be None, 2-element or 4-element.")


def atomic_step(Z, E_keV, E_edge) -> tuple[np.ndarray, float]:
    """McMaster step with unit jump: McMaster minus its quadratic pre-edge extrapolation,
    0 below E_edge, divided by its maximum (mback_v4.m). Returns (mu, raw jump)."""
    mu = mcmaster(Z, E_keV, "c")
    i_res = E_keV < E_edge
    mu = mu - np.polyval(np.polyfit(E_keV[i_res], mu[i_res], 2), E_keV)
    mu[i_res] = 0.0
    mu_jump = float(mu.max())
    if mu_jump > 0:
        mu = mu / mu_jump
    return mu, mu_jump


def _model(p, E, mu, E_edge, E_fluo, n_pre, n_post, erfc_on, continuity=False):
    A = p[0]
    if erfc_on:
        Ae, xi, base = p[1], p[2], 3
    else:
        Ae, xi, base = 0.0, 1.0, 1
    pre = p[base:base + n_pre + 1]
    post = p[base + n_pre + 1:]
    Es = E - E_edge
    m_pre = E < E_edge
    if continuity:  # post holds the coefficients of Es^n_post .. Es^1 (no constant)
        bg_poly = np.polyval(pre, Es) + np.where(m_pre, 0.0, np.polyval(np.r_[post, 0.0], Es))
    else:
        bg_poly = np.where(m_pre, np.polyval(pre, Es), np.polyval(post, Es))
    bg_erfc = Ae * erfc((E - E_fluo) / xi)
    bg = bg_poly + bg_erfc
    atomic = A * mu
    return bg + atomic, {"bg": bg, "atomic": atomic, "bg_poly": bg_poly, "bg_erfc": bg_erfc}


def mback(Z, energy_eV, raw, range_eV=None, Nth=(1, 1), core: str = "",
          weight_mode: str = "size_count", erfc_enabled: bool = False,
          bg_continuity: bool = True, max_func_evals: int = 4000) -> MbackResult:
    """Component-fit normalization of one spectrum (mback_v4.m lineage, fit_target='observed').

    bg_continuity: True (default) = background continuous at E_edge, A_edge identified
    (with Nth_post = 0 this is one polynomial across the edge, the original MBACK form);
    False = mback_v4.m model (independent post polynomial, A_edge unidentified).

    range_eV: None (E_edge-20 / E_edge+80 eV), [pre_offset, post_offset] relative to the
    edge in eV, or [pre_lo, pre_hi, post_lo, post_hi] absolute in eV.
    Nth: polynomial order(s), scalar or (pre, post).
    """
    Z = atomic_number(Z)
    E_eV = np.asarray(energy_eV, float).ravel()
    raw = np.asarray(raw, float).ravel()
    E = E_eV / 1000.0
    n_pre, n_post = (int(Nth), int(Nth)) if np.isscalar(Nth) else (int(Nth[0]), int(Nth[1]))
    E_edge, E_fluo = _edge(Z, core, E)

    i_pre, i_post = fit_windows(E_eV, E_edge, range_eV)
    i_fit = i_pre | i_post
    num_pre, num_post = int(i_pre.sum()), int(i_post.sum())
    if num_pre == 0:
        raise ValueError("mback: no pre-edge points selected.")
    if num_post == 0:
        raise ValueError("mback: no post-edge points selected.")
    warnings_ = []
    if num_pre < n_pre + 1:
        warnings_.append(f"pre-edge has {num_pre} pts; Nth_pre {n_pre} -> {num_pre - 1}")
        n_pre = max(0, num_pre - 1)
    if num_post < n_post + 1:
        warnings_.append(f"post-edge has {num_post} pts; Nth_post {n_post} -> {num_post - 1}")
        n_post = max(0, num_post - 1)
    size_pre = E[i_pre].max() - E[i_pre].min()
    size_post = E[i_post].max() - E[i_post].min()

    mu, mu_jump = atomic_step(Z, E, E_edge)

    if weight_mode == "size_count":
        w_pre, w_post = 1 / np.sqrt(size_pre * num_pre), 1 / np.sqrt(size_post * num_post)
    elif weight_mode == "count":
        w_pre, w_post = 1 / np.sqrt(num_pre), 1 / np.sqrt(num_post)
    elif weight_mode == "uniform":
        w_pre = w_post = 1.0
    else:
        raise ValueError(f"mback: bad weight_mode ({weight_mode}).")
    wfit = np.where(i_pre[i_fit], w_pre, w_post)

    mu_fit, E_fit, raw_fit = mu[i_fit], E[i_fit], raw[i_fit]
    A0 = (raw[i_post].mean() - raw[i_pre].mean()) / mu[i_post].max()
    if not np.isfinite(A0) or A0 <= 0:
        A0 = 1.0
    pre0 = np.polyfit(E[i_pre] - E_edge, raw[i_pre], n_pre)
    Ep = E[i_post] - E_edge
    if bg_continuity:  # post terms Es^n_post .. Es^1 on top of the pre polynomial
        rp = raw[i_post] - A0 * mu[i_post] - np.polyval(pre0, Ep)
        V = np.vander(Ep, n_post + 1)[:, :-1]   # Nth_post 0 -> no post terms: one polynomial
        post0 = np.linalg.lstsq(V, rp, rcond=None)[0] if n_post > 0 else np.zeros(0)
    else:
        post0 = np.polyfit(Ep, raw[i_post] - A0 * mu[i_post], n_post)
    if erfc_enabled:
        scale = raw[i_post].max() - raw[i_pre].min()
        p0 = np.r_[A0, -0.05 * scale, 0.05, pre0, post0]
        lb = np.r_[1e-9, -np.inf, 1e-4, np.full(pre0.size + post0.size, -np.inf)]
    else:
        p0 = np.r_[A0, pre0, post0]
        lb = np.r_[1e-9, np.full(pre0.size + post0.size, -np.inf)]
    ub = np.full(p0.size, np.inf)

    def resid(p):
        y, _ = _model(p, E_fit, mu_fit, E_edge, E_fluo, n_pre, n_post, erfc_enabled,
                      bg_continuity)
        return (y - raw_fit) * wfit

    # MATLAB uses lsqcurvefit/levenberg-marquardt; with erfc off the problem is linear,
    # so any converged solver reaches the same unique minimum.
    sol = least_squares(resid, p0, bounds=(lb, ub), method="trf", x_scale="jac",
                        ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=max_func_evals * 10)
    fits = sol.x
    model_full, comps = _model(fits, E, mu, E_edge, E_fluo, n_pre, n_post, erfc_enabled,
                               bg_continuity)
    A = fits[0]
    norm = (raw - comps["bg"]) / A
    info = {
        "A_edge": A, "params": fits, "resnorm": float(np.sum(sol.fun ** 2)), "status": sol.status,
        "bg": comps["bg"], "bg_poly": comps["bg_poly"], "bg_erfc": comps["bg_erfc"],
        "atomic_component": comps["atomic"], "total_model": model_full,
        "residual_fitregion": sol.fun / wfit, "E_edge_keV": E_edge, "E_fluo_keV": E_fluo,
        "range": range_eV, "Nth_pre": n_pre, "Nth_post": n_post, "erfc_enabled": erfc_enabled,
        "bg_continuity": bg_continuity, "i_fit": i_fit, "wfit": wfit,
        "num_pre": num_pre, "num_post": num_post, "weights": {"pre": w_pre, "post": w_post},
        "mu_jump_raw": mu_jump, "warnings": warnings_,
    }
    if erfc_enabled:
        info["A_erfc"], info["xi"] = fits[1], fits[2]
    return MbackResult(E_eV, norm, mu, info)


def mback_file(Z, fname, *args, save_nrm: bool = False, **kw) -> MbackResult:
    """mback on a two-column ASCII file [eV, raw] (extra columns ignored).

    save_nrm writes [E, norm, mu] next to the input as <name up to first '.'>.nrm_v4.
    """
    d = np.loadtxt(fname)
    res = mback(Z, d[:, 0], d[:, 1], *args, **kw)
    if save_nrm:
        p = Path(fname)
        out = p.with_name(p.name.split(".")[0] + ".nrm_v4")
        from ..matlab_compat import save_ascii
        save_ascii(out, np.c_[res.energy_eV, res.norm_xas, res.mu])
    return res
