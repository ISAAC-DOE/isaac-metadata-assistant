"""McMaster (1969) cross-sections, port of McMaster.m (T.-C. Weng, Penner-Hahn group).

Tables come from element.mat, shipped as data/element.json. Energies in keV.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

import numpy as np

# rows copied from zymbol() in mback_v4.m
_PERIODIC = "".join([
    "H He",
    "LiBeB C N O F Ne",
    "NaMgAlSiP S ClAr",
    "K CaScTiV CrMnFeCoNiCuZnGaGeAsSeBrKr",
    "RbSrY ZrNbMoTcRuRhPdAgCdInSnSbTeI Xe",
    "CsBaLaCePrNdPmSmEuGdTbDyHoErTmYbLuHfTaW ReOsIrPtAuHgTlPbBiPoAtRn",
    "FrRaAcThPaU NpPuAmCmBkCfEsFmMdNoLrRfDbSgBhHsMt",
])
_MISSING = {84, 85, 87, 88, 89, 91, 93}  # Po, At, Fr, Ra, Ac, Pa, Np: not in McMaster


@lru_cache(maxsize=1)
def elements() -> list[dict]:
    with resources.files("xas_analysis.data").joinpath("element.json").open() as fh:
        return json.load(fh)["elements"]


def element(Z: int | str) -> dict:
    return elements()[atomic_number(Z) - 1]


def atomic_number(sym: int | str) -> int:
    """Symbol -> Z (zymbol in mback_v4.m). Integers pass through."""
    if isinstance(sym, (int, np.integer)):
        return int(sym)
    s = sym.strip()
    s = (s[0].upper() + s[1:].lower()).ljust(2)
    for i in range(0, len(_PERIODIC), 2):
        if _PERIODIC[i:i + 2] == s:
            return i // 2 + 1
    raise ValueError(f"unknown element symbol {sym!r}")


def _pv(coef4, lnE):
    c = np.asarray(coef4, float)
    return c[0] + c[1] * lnE + c[2] * lnE ** 2 + c[3] * lnE ** 3


def mcmaster(Z: int | str, E_keV, unit: str = "c") -> np.ndarray:
    """Total cross-section (photo + coherent + incoherent).

    unit 'c' (default): mass absorption coefficient [cm^2/g]; 'b': [barn/atom].
    Raises below the M edge (MATLAB fails there with a size mismatch).
    """
    Z = atomic_number(Z)
    if Z < 1 or Z > 94:
        raise ValueError("McMaster tables cover Z = 1..94")
    if Z in _MISSING:
        raise ValueError(f"McMaster did NOT have Z={Z}")
    el = element(Z)
    E = np.asarray(E_keV, float).ravel()
    if np.any(E < el["M_edge"]):
        raise ValueError(f"McMaster: energies below the M edge ({el['M_edge']} keV) are not tabulated")
    lnE = np.log(E)
    K, L1, L2, L3 = el["K_edge"], *el["L_edge"]
    with np.errstate(divide="ignore"):
        lj1, lj2 = np.log(el["L_jump"][0]), np.log(el["L_jump"][1])
    lnmu = np.empty_like(E)
    m = E >= K
    lnmu[m] = _pv(el["post_K"], lnE[m])
    m = (E < K) & (E >= L1)
    lnmu[m] = _pv(el["post_L"], lnE[m])
    m = (E < L1) & (E >= L2)
    lnmu[m] = _pv(el["post_L"], lnE[m]) - lj1
    m = (E < L2) & (E >= L3)
    lnmu[m] = _pv(el["post_L"], lnE[m]) - lj1 - lj2
    m = (E < L3) & (E >= el["M_edge"])
    lnmu[m] = _pv(el["post_M"], lnE[m])
    mu = np.exp(lnmu) + np.exp(_pv(el["xsec_coh"], lnE)) + np.exp(_pv(el["xsec_nch"], lnE))
    if unit in ("b", "B"):
        return mu
    return mu / el["m2a"]
