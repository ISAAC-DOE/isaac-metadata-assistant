"""Self-absorption (over-absorption) correction of fluorescence XANES, thick-sample limit.

Explicit model (Troger et al. 1992 / Haskel FLUO / Booth & Bridges 2005 in the thick limit):

    IF(E) / I0  ~  mu_a(E) / [ mu_a(E) + alpha(E) ]                         (thick, flat sample)
    alpha(E)  =  mu_rest(E) + g * mu_tot(E_f),    g = sin(phi_in) / sin(theta_out)

    mu_a(E)    absorber K-shell photoabsorption (only it produces the K fluorescence line),
               = D0 s(E), D0 = w_a [mu_K-branch - mu_L-branch extrapolated] just above the
               edge (McMaster); s(E) carries all the energy dependence (atomic step x fine
               structure), so the target scale is the McMaster unit step mu_unit(E).
    mu_rest(E) everything else at E: matrix + absorber shells other than K (McMaster, cm^2/g)
    mu_tot(E_f) total absorption of the sample at the fluorescence energy (below the edge)
    s(E)       the quantity wanted: true normalized absorption (fine structure x atomic step)

Measured, after background removal: n(E) = (IF/I0 / F - bg) / A = K mu_a / (mu_a + alpha),
with K unknown. Solving for the true absorption:

    s(E) = alpha(E) n(E) / ( D0 [K - n(E)] )

K is fixed by requiring s(E) = mu_unit(E) (the McMaster unit step, the same convention as
the uncorrected _avg_nrm) on the post-edge window, in least squares; the output is s on that
scale. Inputs that must be stated: composition (mass fractions), the fluorescence energy,
the two angles. Assumptions: sample infinitely thick (thickness >> 1/mu_tot: a sugar pellet
at 2.5 keV has an attenuation length ~ 30 um), homogeneous, flat, single absorbing element
contributing to the detected line. Not valid for thin films (use the uncorrected spectrum;
a thickness-dependent correction needs the thickness). The correction is ill-conditioned
where n approaches K (concentrated absorbers at the white line): reported as max n/K.

Feasibility check (done before correcting): for a thick sample the measured normalized
spectrum cannot exceed  n_max / n_post = 1 + alpha/D0  (s -> infinity). If the measured
contrast (max of the uncorrected normalized spectrum over its post-edge level) exceeds it,
the sample is NOT in the thick limit for the stated composition (powder finer than the
absorption length, thin film, or diluted): ValueError, no correction.
"""
from __future__ import annotations

import re

import numpy as np

from ..physics.mcmaster import _pv, atomic_number, element, mcmaster

_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*\.?\d*)")


def formula_mass_fractions(formula: str) -> dict[int, float]:
    """'Na2S2O3' -> {Z: mass fraction}. No parentheses."""
    n: dict[int, float] = {}
    for sym, cnt in _TOKEN.findall(formula.replace(" ", "")):
        z = atomic_number(sym)
        n[z] = n.get(z, 0.0) + (float(cnt) if cnt else 1.0)
    m = {z: c * element(z)["weight"] for z, c in n.items()}
    tot = sum(m.values())
    return {z: v / tot for z, v in m.items()}


def mixture_mass_fractions(components: list[dict]) -> dict[int, float]:
    """[{formula: Na2S2O3, wt: 0.05}, {formula: C12H22O11, wt: 0.95}] -> {Z: mass fraction}."""
    tot_w = sum(float(c["wt"]) for c in components)
    out: dict[int, float] = {}
    for c in components:
        for z, f in formula_mass_fractions(c["formula"]).items():
            out[z] = out.get(z, 0.0) + f * float(c["wt"]) / tot_w
    return out


def _k_shell_photo(Z, E_keV):
    """Absorber K-shell photoabsorption [cm^2/g] (0 below the K edge)."""
    el = element(Z)
    lnE = np.log(E_keV)
    d = np.exp(_pv(el["post_K"], lnE)) - np.exp(_pv(el["post_L"], lnE))
    return np.where(E_keV >= el["K_edge"], d, 0.0) / el["m2a"]


def sa_correct_thick(E_eV, n, absorber, composition: dict[int, float], mu_unit, post_mask,
                     phi_in_deg: float = 45.0, theta_out_deg: float = 45.0,
                     E_fluo_keV: float | None = None, contrast: float | None = None):
    """Thick-limit self-absorption correction of a background-subtracted fluorescence spectrum.

    n: (IF/I0 / F - bg) / A, NOT divided by any step-slope factor. mu_unit: McMaster unit step
    on the same grid (the target scale). post_mask: post-edge window for fixing K.
    Returns (s, info).
    """
    Za = atomic_number(absorber)
    E = np.asarray(E_eV, float) / 1000.0
    n = np.asarray(n, float)
    Ef = float(E_fluo_keV if E_fluo_keV is not None else element(Za)["K_alpha1"])
    wa = composition.get(Za, 0.0)
    if wa <= 0:
        raise ValueError("self-absorption: absorber not in the composition")
    D = wa * _k_shell_photo(Za, E)                                     # absorber K photo, cm^2/g
    mu_tot = sum(w * mcmaster(z, E, "c") for z, w in composition.items())
    mu_rest = mu_tot - D                                               # all but absorber K
    mu_f = sum(w * mcmaster(z, np.array([Ef]), "c")[0] for z, w in composition.items())
    g = np.sin(np.radians(phi_in_deg)) / np.sin(np.radians(theta_out_deg))
    alpha = mu_rest + g * mu_f
    above = E >= element(Za)["K_edge"]
    D0 = float(wa * _k_shell_photo(Za, np.array([element(Za)["K_edge"] + 1e-4]))[0])

    a0 = float(alpha[above][0] / D0)
    if contrast is not None and contrast > 0.95 * (1.0 + a0):
        raise ValueError(f"self-absorption: measured contrast {contrast:.2f} exceeds the thick-limit "
                         f"maximum 1 + alpha/D0 = {1 + a0:.2f} for this composition: not a thick "
                         "sample (fine powder, thin film or diluted); no correction applied")

    def s_of(K):
        with np.errstate(divide="ignore", invalid="ignore"):
            s = alpha * n / (D0 * (K - n))      # valid at all E (D0 constant); below the
                                                # tabulated edge n ~ 0 and s ~ alpha n / (D0 K)
        return s

    # K: least squares of s against mu_unit on the post window (1-D, bracketed search)
    nmax = float(np.nanmax(n[above]))
    Ks = nmax * np.geomspace(1.0005, 1e4, 4000)
    cost = [np.nanmean((s_of(K)[post_mask] - mu_unit[post_mask]) ** 2) for K in Ks]
    j = int(np.nanargmin(cost))
    lo, hi = Ks[max(j - 1, 0)], Ks[min(j + 1, len(Ks) - 1)]
    for _ in range(60):
        a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        ca = np.nanmean((s_of(a)[post_mask] - mu_unit[post_mask]) ** 2)
        cb = np.nanmean((s_of(b)[post_mask] - mu_unit[post_mask]) ** 2)
        lo, hi = (lo, b) if ca < cb else (a, hi)
    K = 0.5 * (lo + hi)
    s = s_of(K)
    # consistency: residual step slope after correction (0 if the thick model explains the rise)
    u = E / element(Za)["K_edge"] - 1.0
    pm = post_mask & np.isfinite(s) & (mu_unit > 0)
    k_res = float(np.polyfit(u[pm], s[pm] / mu_unit[pm], 1)[0] / np.polyval(np.polyfit(u[pm], s[pm] / mu_unit[pm], 1), 0.0))
    i_edge = np.argmin(np.abs(E - element(Za)["K_edge"] - 0.002))
    info = {"method": "thick-limit (Troger/Haskel FLUO)", "K": K, "max_n_over_K": nmax / K,
            "alpha_over_D_at_edge": float(alpha[i_edge] / D0),
            "thick_limit_max_contrast": 1.0 + a0, "measured_contrast": contrast, "g": float(g), "phi_in_deg": phi_in_deg, "theta_out_deg": theta_out_deg,
            "E_fluo_keV": Ef, "w_absorber": wa,
            "composition": {element(z)["symbol"]: round(w, 6) for z, w in composition.items()},
            "residual_step_slope_k": k_res, "post_rms_vs_mcmaster": float(np.sqrt(np.nanmean((s - mu_unit)[post_mask] ** 2)))}
    return s, info
