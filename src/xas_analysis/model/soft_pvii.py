"""Soft-XAS background subtraction: Pearson-VII valence background + FEFF mu0 atomic term.

Port of sxas_bl82_proto/sxas_core.py (2026-08, BL8-2 C K, Dennis biochar). The defaults of
SoftPviiConfig are that ADOPTED recipe; reference/sxas_core_2026-08.py is the original.

    y = sc / i0**i0_exp
    fit:  pre   : w_pre * (y - PVII)
          post  :       (y - (PVII + coeff1 * mu0))
          pen   : sqrt(lam) * max(0, PVII - y)          (background must stay below data)
    PVII(E) = a1 * (c1^2 (E - b1)^2 + 1)^(-d1), with b1 below the edge, b1 and d1 free,
    multi-start over b1 seeds; lowest cost kept.

Outputs: red = y - PVII; unit = red / coeff1 (unit edge jump, mu0 normalised to 1 on
norm_window); area-normalised red / A(area_window).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources

import numpy as np
from scipy.optimize import least_squares


@dataclass
class SoftPviiConfig:
    trim_eV: float = 340.0
    area_window: tuple[float, float] = (280.0, 310.0)
    area_window_dennis: tuple[float, float] = (283.0, 313.0)
    norm_window: tuple[float, float] = (320.0, 340.0)     # mu0 normalised to mean 1 here
    pre_windows: list[tuple[float, float]] = field(default_factory=lambda: [(278.0, 283.8)])
    post_window: tuple[float, float] = (302.0, 338.0)
    penalty_window: tuple[float, float] = (283.0, 340.0)
    lam: float = 3.5
    w_pre: float = 6.0                                     # squared weight; residual x sqrt(w_pre)
    b1_seeds: tuple[float, ...] = (240.0, 180.0, 300.0)
    c1_max: float = 0.5
    b1_bounds: tuple[float, float] = (100.0, 340.0)
    d1_bounds: tuple[float, float] = (0.02, 12.0)
    eshift_eV: float = 7.0                                 # FEFF mu0 energy shift
    i0_exp: float = 1.0
    slope_check_lo_eV: float = 303.0                       # positivity check range start
    s0_file: str | None = None                             # None = packaged graphite q=0.10 a.u.


def load_s0(cfg: SoftPviiConfig) -> tuple[np.ndarray, np.ndarray]:
    if cfg.s0_file is None:
        with resources.files("xas_analysis.data").joinpath("S0_graphite_q0.10.dat").open() as fh:
            s0 = np.loadtxt(fh, comments="#")
    else:
        s0 = np.loadtxt(cfg.s0_file, comments="#")
    return s0[:, 0], s0[:, 1]


def mu0(E, cfg: SoftPviiConfig, s0=None) -> np.ndarray:
    w0, v0 = s0 if s0 is not None else load_s0(cfg)
    w = w0 + cfg.eshift_eV
    v = np.interp(E, w, v0, left=0.0, right=v0[-1])
    v = np.where(E < w[0], 0.0, v)
    ref = np.interp(np.linspace(*cfg.norm_window, 101), w, v0).mean()
    return v / ref


def pvii(E, a, b, c, d):
    return a * (c ** 2 * (E - b) ** 2 + 1.0) ** (-d)


def read_bl82_export(path) -> dict[str, np.ndarray]:
    """BL8-2 spec_export .dat: '#mono tey aey ...' header line, whitespace columns."""
    hdr, rows = None, []
    with open(path) as fh:
        for ln in fh:
            s = ln.strip()
            if not s:
                continue
            if s.startswith("#"):
                hdr = s.lstrip("#").split()
                continue
            rows.append([float(x) for x in s.split()])
    a = np.array(rows)
    return {n: a[:, i] for i, n in enumerate(hdr)}


def load_xy(path, cfg: SoftPviiConfig) -> tuple[np.ndarray, np.ndarray]:
    c = read_bl82_export(path)
    keep = c["mono"] <= cfg.trim_eV
    return c["mono"][keep], (c["sc"] / c["i0"] ** cfg.i0_exp)[keep]


def reduce_pvii(E, y, cfg: SoftPviiConfig | None = None, s0=None) -> dict:
    cfg = cfg or SoftPviiConfig()
    E = np.asarray(E, float)
    y = np.asarray(y, float)
    pre = np.zeros_like(E, bool)
    for lo, hi in cfg.pre_windows:
        pre |= (E >= lo) & (E <= hi)
    post = (E >= cfg.post_window[0]) & (E <= cfg.post_window[1])
    pen = (E >= cfg.penalty_window[0]) & (E <= cfg.penalty_window[1])
    at0 = mu0(E, cfg, s0)
    S = float(np.median(np.abs(y[pre])))
    if not np.isfinite(S) or S <= 0:
        S = float(np.median(np.abs(y))) or 1.0
    ys = y / S
    yl, yh = np.median(ys[pre]), np.median(ys[post])
    lb = [0.0, 1e-5, 0.0, cfg.b1_bounds[0], cfg.d1_bounds[0]]
    ub = [50.0, cfg.c1_max, 10.0, cfg.b1_bounds[1], cfg.d1_bounds[1]]
    wpre, sl = np.sqrt(cfg.w_pre), np.sqrt(cfg.lam)

    def resid(p):
        a1, c1, cf, b1, d1 = p
        bg = pvii(E, a1, b1, c1, d1)
        return np.concatenate([wpre * (ys[pre] - bg[pre]),
                               ys[post] - (bg[post] + cf * at0[post]),
                               sl * np.maximum(0, bg[pen] - ys[pen])])

    best = None
    for b1s in cfg.b1_seeds:
        p0 = [min(max(v, l), u) for v, l, u in
              zip([yl, 0.03, max(yh - yl, 1e-3), b1s, 1.0], lb, ub)]
        sol = least_squares(resid, p0, bounds=(lb, ub), max_nfev=80000,
                            ftol=1e-13, xtol=1e-13, gtol=1e-13)
        if best is None or sol.cost < best.cost:
            best = sol
    sol = best
    a1, c1, cf, b1, d1 = sol.x
    a1, cf = a1 * S, cf * S
    bg = pvii(E, a1, b1, c1, d1)
    red = y - bg
    m = (E >= cfg.area_window[0]) & (E <= cfg.area_window[1])
    A = np.trapezoid(red[m], E[m])
    unit = red / cf if cf > 0 else red * np.nan
    md = (E >= cfg.area_window_dennis[0]) & (E <= cfg.area_window_dennis[1])
    Ad = np.trapezoid(unit[md], E[md])
    resid_post = red[post] - cf * at0[post]
    sd = np.polyfit(E[post], red[post], 1)[0]
    sr = np.polyfit(E[post], resid_post, 1)[0]
    unmod = abs(sr / sd) * 100 if sd else np.nan
    pmin = float(np.min(red[(E >= cfg.slope_check_lo_eV) & (E <= cfg.trim_eV)] / A))
    rail = [nm for nm, v, l, u in zip(("a1", "c1", "coeff1", "b1", "d1"), sol.x, lb, ub)
            if abs(v - l) < 1e-5 * max(1, abs(l)) or abs(v - u) < 1e-5 * max(1, abs(u))]
    return dict(E=E, red=red / A, unit=unit, bg=bg, y=y, at=cf * at0,
                a1=a1, b1=b1, c1=c1, d1=d1, cf=cf, area=A, areaD=Ad,
                unmod=unmod, pmin=pmin, rail=rail, cost=sol.cost,
                rms=float(np.sqrt(np.mean(resid_post ** 2)) / cf) if cf > 0 else np.nan)


def reduce_file(path, cfg: SoftPviiConfig | None = None) -> dict:
    cfg = cfg or SoftPviiConfig()
    return reduce_pvii(*load_xy(path, cfg), cfg)
