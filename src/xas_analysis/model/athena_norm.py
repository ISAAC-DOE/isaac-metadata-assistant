"""Athena-style edge-step normalization (Ravel & Newville 2005), for comparison and as an option.

pre(E)  = line (or quadratic) fitted on the pre-edge window
post(E) = polynomial (default quadratic) fitted on the post-edge window
step    = post(E0) - pre(E0)
norm    = (y - pre) / step;  flattened: above E0 subtract (post - pre - step) / step

No atomic cross-section: the post-edge curvature (instrument, self-absorption, cross-section
fall-off) is absorbed by the post polynomial. E0 defaults to the tabulated edge.
"""
from __future__ import annotations

import numpy as np

from ..physics.mcmaster import atomic_number
from .mback import MbackResult, _edge, fit_windows


def athena_norm(Z, energy_eV, raw, range_eV, core: str = "", E0_eV: float | None = None,
                pre_order: int = 1, post_order: int = 2, flatten: bool = True) -> MbackResult:
    E = np.asarray(energy_eV, float).ravel()
    y = np.asarray(raw, float).ravel()
    Zn = atomic_number(Z)
    E_edge, E_fluo = _edge(Zn, core, E / 1000.0)
    E0 = float(E0_eV if E0_eV is not None else 1000.0 * E_edge)
    i_pre, i_post = fit_windows(E, E_edge, range_eV)
    if i_pre.sum() < pre_order + 2 or i_post.sum() < post_order + 2:
        raise ValueError("athena_norm: too few pre-edge or post-edge points.")
    cp = np.polyfit(E[i_pre] - E0, y[i_pre], pre_order)
    cq = np.polyfit(E[i_post] - E0, y[i_post], post_order)
    pre = np.polyval(cp, E - E0)
    post = np.polyval(cq, E - E0)
    step = float(np.polyval(cq, 0.0) - np.polyval(cp, 0.0))
    if not step > 0:
        raise ValueError(f"athena_norm: edge step {step:.3g} <= 0.")
    norm = (y - pre) / step
    if flatten:
        norm = norm - np.where(E >= E0, (post - pre - step) / step, 0.0)
    info = {"A_edge": step, "bg": pre, "post_line": post, "E0_eV": E0, "pre_coef": cp, "post_coef": cq,
            "E_edge_keV": E_edge, "E_fluo_keV": E_fluo, "range": range_eV, "flatten": flatten,
            "model": f"athena pre{pre_order}/post{post_order}" + (" flattened" if flatten else "")}
    return MbackResult(E, norm, np.where(E >= E0, 1.0, 0.0), info)
