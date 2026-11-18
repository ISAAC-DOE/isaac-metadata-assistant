"""Hard-XAS normalization with the xrs-analysis low-q fit structure (2026-11-09).

One physical background across the whole range plus a locked atomic ansatz, fitted jointly:

    raw(E) = bg(E) + A * mu(E)
    bg(E)  = c0 + c3 * (E/E_edge)^-3 [+ c4 * (E/E_edge)^-4] [+ c1 * (E/E_edge - 1)]   Victoreen
    mu(E)  = McMaster step with unit jump, locked at the tabulated edge (same as mback)

Objective (xrs_analysis.model.lowq.Objective, on data scaled to a unit post-edge level):

    w_pre  * mean_pre  (y - bg)^2
  + w_post * mean_post (y - bg - A mu)^2
  + w_neg  * mean_{E >= E_edge} max(0, bg - y)^2            background stays below the data
  + w_area * ((int_post (y - bg) - A int_post mu) / width)^2   integrated post-edge weight

The XANES region is excluded from the LSQ terms (as in mback); it enters only through the
non-negativity term. Output: norm_xas = (raw - bg) / A.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from ..physics.mcmaster import atomic_number
from .mback import MbackResult, _edge, atomic_step, fit_windows

_trapz = getattr(np, "trapezoid", None) or np.trapz


@dataclass
class XrsWeights:
    pre: float = 10.0       # lowq.Weights defaults: preedge 10, postedge 3, nonneg 0.8
    post: float = 3.0
    nonneg: float = 0.8
    area: float = 1.0       # squared, on the mean level (lowq uses |.| * 0.02 on raw counts)


def victoreen_basis(E_keV, E_edge, e4=False, linear=False):
    x = E_keV / E_edge
    cols, names = [np.ones_like(x), x ** -3], ["c0", "c3"]
    if e4:
        cols.append(x ** -4)
        names.append("c4")
    if linear:
        cols.append(x - 1)
        names.append("c1")
    return np.column_stack(cols), names


def mback_xrs(Z, energy_eV, raw, range_eV=None, core: str = "", weights: XrsWeights | None = None,
              e4: bool = False, linear: bool = False, nonneg_from_eV: float | None = None,
              step_slope: bool | int = False, pre_tail: bool = False,
              bg_decreasing: bool | None = None, post_poly: int = 0,
              extra_edges: list | None = None, exclude_eV: list | None = None,
              step_factor_base: list | None = None, response_power: float | None = None) -> MbackResult:
    """Victoreen background + McMaster step, joint fit with the low-q XRS objective.

    Model:  y = bg(E) + A f(E) [mu(E) + sum_j r_j mu_j(E)] + P(E)
      bg   Victoreen c0 + c3 x^-3 (+ options), x = E / E_edge
      f    1 + k1 u + k2 u^2 ...  (u = x - 1; order = step_slope): multiplicative step factor
      mu_j unit McMaster steps of other edges in range (extra_edges), r_j >= 0, same f
      P    additive post-edge rise sum_i p_i u^i for E >= E_edge (order post_poly), 0 below
    norm = (y - bg - A f sum r_j mu_j - P) / (A f)

    range_eV: as mback (None, [pre_offset, post_offset] or [pre_lo, pre_hi, post_lo, post_hi]).
    nonneg_from_eV: start of the non-negativity window (default: the tabulated edge).
    step_slope: order of f (True = 1): smooth multiplicative instrument/sample factor on the
        step (I0 chamber efficiency at tender energies, thick-dilute fluorescence).
    pre_tail: add a decaying tail a * exp(-(E - E_pre_lo) / tau) to the background (a >= 0,
        tau 5-500 eV, fitted): scatter of the incident beam leaking into the fluorescence
        window, which shrinks as E moves away from it (tender fluorescence, e.g. S K at BL4-3).
    bg_decreasing: c0, c3 >= 0 (and no linear term): the background falls monotonically with E.
        DEFAULT since 2026-11-11 (None -> True, or False when `linear` is requested); False gives the
        free Victoreen of earlier versions. Free, c0 and c3 nearly cancel and act as a rising ramp
        under the post-edge (HERFD Ir/Pt: +11-14 % of the step, edge steps 5-13 % too small);
        constrained, HERFD backgrounds come out flat at the pre-edge level (c3 at 0).
       
        and stays >= 0, as a fluorescence pre-edge from matrix absorption and scatter does.
        Without it the fit may bend the background upward under the post-edge and take part
        of the step.
    post_poly: order of the additive post-edge rise P (continuous, 0 at the edge).
    extra_edges: other edges in the range, [(element, core), ...], e.g. [("Mo", "L3")]
        (an L3 step includes the L2 jump at the tabulated ratio).
    exclude_eV: [[lo, hi], ...] removed from the pre/post fit windows (white lines of
        extra edges, glitches).
    step_factor_base: fixed coefficients [b1, b2, ...] of an instrument response
        f0 = 1 + b1 u + b2 u^2 ... shared by a beamtime (e.g. fitted on diluted standards);
        the fitted factor multiplies it: f = f0 (1 + k1 u + ...).
    response_power: p of an I0 detection response F = (E/E_edge)^p that multiplies the WHOLE
        signal (background included): a thin gas I0 chamber counts ~ mu_gas(E) ~ E^-3, so
        IF/I0 rises as E^p, p ~ 3 (N2 3.0, He 3.1, more with windows/path). The data are
        divided by F before the fit; bg, total_model and the step are then in the
        I0-corrected frame, where the step follows mu x the sample's self-absorption factor
        (1 + k1 u). Splitting the rise between F and the step is NOT determined by the data
        (degenerate); p must come from physics.
    """
    wt = weights or XrsWeights()
    if bg_decreasing is None:
        bg_decreasing = not linear
    Z = atomic_number(Z)
    E_eV = np.asarray(energy_eV, float).ravel()
    y_raw = np.asarray(raw, float).ravel()
    E = E_eV / 1000.0
    E_edge, E_fluo = _edge(Z, core, E)
    F = (E / E_edge) ** float(response_power) if response_power else np.ones_like(E)
    y_raw = y_raw / F
    i_pre, i_post = fit_windows(E_eV, E_edge, range_eV)
    for lo, hi in (exclude_eV or []):
        keep = ~((E_eV >= lo) & (E_eV <= hi))
        i_pre, i_post = i_pre & keep, i_post & keep
    if i_pre.sum() < 3 or i_post.sum() < 3:
        raise ValueError("mback_xrs: need >= 3 pre-edge and post-edge points.")
    mu, mu_jump = atomic_step(Z, E, E_edge)
    mus, extra_names = [], []
    for el, c in (extra_edges or []):
        Zj = atomic_number(el)
        Ej, _ = _edge(Zj, c, E)
        mus.append(atomic_step(Zj, E, Ej)[0])
        extra_names.append(f"r_{el}{c}")
    i_neg = E_eV >= (nonneg_from_eV if nonneg_from_eV is not None else E_edge * 1000)

    scale = float(np.median(y_raw[i_post]) - np.median(y_raw[i_pre]))
    if not np.isfinite(scale) or scale <= 0:
        scale = float(np.max(np.abs(y_raw))) or 1.0
    y = y_raw / scale
    B, names = victoreen_basis(E, E_edge, e4, linear)
    Ep = E_eV[i_post]
    width = Ep.max() - Ep.min()
    s_pre, s_post = np.sqrt(wt.pre / i_pre.sum()), np.sqrt(wt.post / i_post.sum())
    s_neg = np.sqrt(wt.nonneg / max(1, i_neg.sum()))
    s_area = np.sqrt(wt.area)

    u = E / E_edge - 1.0
    above = (E >= E_edge).astype(float)
    nk = int(step_slope)                 # True -> 1
    nb, nx, npp = B.shape[1], len(mus), int(post_poly)
    E_lo = float(E_eV[i_pre].min())
    # parameter layout: [A, k1..k_nk, bg (nb), r_1..r_nx, p_1..p_npp, (tail amp, tau)]
    iA, ik, ib = 0, slice(1, 1 + nk), slice(1 + nk, 1 + nk + nb)
    ir = slice(ib.stop, ib.stop + nx)
    ip = slice(ir.stop, ir.stop + npp)
    U = np.column_stack([u ** n for n in range(1, nk + 1)]) if nk else np.zeros((E.size, 0))
    Pb = np.column_stack([above * u ** n for n in range(1, npp + 1)]) if npp else np.zeros((E.size, 0))
    MU = np.column_stack(mus) if nx else np.zeros((E.size, 0))

    f0 = 1.0 + sum((b * u ** (n + 1) for n, b in enumerate(step_factor_base or [])), np.zeros_like(u))

    def parts(p):
        f = f0 * (1.0 + U @ p[ik])
        bg = B @ p[ib]
        if pre_tail:
            bg = bg + p[-2] * np.exp(-(E_eV - E_lo) / p[-1])
        other = p[iA] * f * (MU @ p[ir]) + Pb @ p[ip]      # extra edges + additive post rise
        return p[iA] * f, bg, other

    def resid(p):
        g, bg, other = parts(p)
        d = y - bg - other
        am = g * mu
        return np.concatenate([
            s_pre * d[i_pre],
            s_post * (d[i_post] - am[i_post]),
            s_neg * np.maximum(0.0, -(y - bg)[i_neg]),
            [s_area * (_trapz(d[i_post], Ep) - _trapz(am[i_post], Ep)) / width],
        ])

    # seed: linear LSQ (products A k_i, A r_j are linear coefficients), no penalty
    w = i_pre | i_post
    post = lambda c: np.where(i_post[:, None], c, 0.0)
    M = np.column_stack([post((f0 * mu)[:, None]), post((f0 * mu)[:, None] * U), B, post(f0[:, None] * MU), Pb])[w]
    c = np.linalg.lstsq(M, y[w], rcond=None)[0]
    A0 = c[0] if c[0] > 0 else 1.0
    p0 = np.r_[A0, c[1:1 + nk] / A0, c[ib], np.maximum(c[ir] / A0, 0.0), c[ip]]
    lb = np.r_[0.0, np.full(nk + nb, -np.inf), np.zeros(nx), np.full(npp, -np.inf)]
    if bg_decreasing:
        if linear:
            raise ValueError("mback_xrs: bg_decreasing excludes the linear term.")
        for nm in ("c0", "c3") + (("c4",) if e4 else ()):
            lb[ib.start + names.index(nm)] = 0.0
    ub = np.full(lb.size, np.inf)
    if pre_tail:
        p0 = np.r_[p0, 0.05, 30.0]
        lb, ub = np.r_[lb, 0.0, 5.0], np.r_[ub, np.inf, 500.0]
    p0 = np.clip(p0, lb + 1e-9, ub - 1e-9)
    sol = least_squares(resid, p0, bounds=(lb, ub), method="trf", x_scale="jac",
                        ftol=1e-14, xtol=1e-14, gtol=1e-14, max_nfev=20000)
    px = sol.x
    g_s, bg_s, other_s = parts(px)
    A = float(px[iA] * scale)
    g = g_s * scale                      # A f(E): the step height at each energy
    bg = bg_s * scale
    other = other_s * scale
    norm = (y_raw - bg - other) / g
    r = sol.fun
    n1, n2, n3 = i_pre.sum(), i_post.sum(), i_neg.sum()
    terms = {"pre": float(np.sum(r[:n1] ** 2)), "post": float(np.sum(r[n1:n1 + n2] ** 2)),
             "nonneg": float(np.sum(r[n1 + n2:n1 + n2 + n3] ** 2)), "area": float(r[-1] ** 2)}
    model = bg + other + g * mu
    info = {"A_edge": A, "bg": bg, "other": other, "atomic_component": g * mu, "total_model": model,
            "step_factor": g / A if A else g, "response_F": F, "response_power": response_power,
            "frame": "I0-corrected (data / F)" if response_power else "raw", "step_slope_k": [float(v) for v in px[ik]] if nk else [],
            "extra_edges": dict(zip(extra_names, (float(v) for v in px[ir]))),
            "post_poly": [float(v * scale) for v in px[ip]],
            "pre_tail": {"amp": float(px[-2] * scale), "tau_eV": float(px[-1])} if pre_tail else None,
            "bg_params": dict(zip(names, (float(v * scale) for v in px[ib]))),
            "params": np.r_[A, px[ib] * scale], "param_names": ["A"] + names,
            "post_rms": float(np.sqrt(np.mean((y_raw - model)[i_post] ** 2)) / A) if A else np.nan,
            "pre_rms": float(np.sqrt(np.mean((y_raw - model)[i_pre] ** 2)) / A) if A else np.nan,
            "i_pre": i_pre, "i_post": i_post,
            "objective": float(np.sum(r ** 2)), "terms": terms, "status": sol.status,
            "E_edge_keV": E_edge, "E_fluo_keV": E_fluo, "range": range_eV, "mu_jump_raw": mu_jump,
            "num_pre": int(n1), "num_post": int(n2), "num_nonneg": int(n3), "scale": scale,
            "weights": wt.__dict__, "model": "victoreen+mcmaster (xrs objective)"}
    return MbackResult(E_eV, norm, mu, info)
