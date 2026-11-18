"""Weighted average of aligned scans (port of average_scans.m)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class AlignedScan:
    num: int
    E: np.ndarray
    IF: np.ndarray
    I0: np.ndarray
    sec: np.ndarray | float
    anchor_eV: float = np.nan
    shift_eV: float = np.nan
    quality_ok: bool = True
    keep: bool = True
    # ISAAC (PROVENANCE.md M1): a sample may pool scans of several files (spots, repeats), whose scan numbers repeat;
    # `key` tells them apart (None: the scan number, as before)
    key: object = None

    @property
    def ident(self):
        return self.num if self.key is None else self.key


def _resolve_weights(weights, IF, I0, sec):
    nk = IF.shape[1]
    if not isinstance(weights, str):
        w = np.asarray(weights, float).ravel()
        if w.size != nk:
            raise ValueError(f"weights length {w.size} != kept scans {nk}")
        return w, "numeric (user-supplied)"
    m = weights.lower()
    if m == "uniform":
        w, scheme = np.ones(nk), "uniform"
    elif m == "i0":
        w, scheme = np.nanmean(I0, axis=0), "I0 mean per scan"
    elif m == "time":
        w, scheme = np.nanmean(sec, axis=0), "integration-time mean per scan"
    elif m == "sqrtn":
        w, scheme = np.sqrt(np.nanmean(IF, axis=0)), "sqrt(mean IF) per scan"
    else:
        raise ValueError(f"Unknown weights mode: {weights}")
    w = w * nk / w.sum() if w.sum() > 0 else np.ones(nk)
    return w, scheme


def average_scans(scans: list[AlignedScan], weights="uniform", min_scans: int = 1,
                  compute_norm: bool = True, empty_as_nan: bool = False) -> tuple[dict, dict]:
    """Weighted mean of IF/I0 over the kept scans, with the standard error of the mean.

    MATLAB quirk (default, empty_as_nan=False): at an energy where no scan is finite
    (e.g. grid ends after the alignment shift) IF_over_I0, err and sec_total are 0, so
    reduce_xas_v2 writes spurious zero rows into *_avg_raw. empty_as_nan=True makes
    those points NaN, and the save step drops them.
    """
    if not scans:
        raise ValueError("no scans to average")
    kept = [i for i, s in enumerate(scans) if s.keep]
    if len(kept) < min_scans:
        raise ValueError(f"only {len(kept)} scans kept (min {min_scans}).")
    E = np.asarray(scans[kept[0]].E, float).ravel()
    nE, nk = E.size, len(kept)
    IF = np.full((nE, nk), np.nan)
    I0 = np.full((nE, nk), np.nan)
    sec = np.full((nE, nk), np.nan)
    for j, i in enumerate(kept):
        s = scans[i]
        if np.asarray(s.E).size != nE:
            raise ValueError(f"scan {i} has {np.asarray(s.E).size} points; expected {nE}.")
        IF[:, j] = np.ravel(s.IF)
        I0[:, j] = np.ravel(s.I0)
        sec[:, j] = s.sec if np.isscalar(s.sec) else np.ravel(s.sec)
    with np.errstate(all="ignore"):
        w_scan, scheme = _resolve_weights(weights, IF, I0, sec)
        w = np.tile(w_scan, (nE, 1))
        w[~np.isfinite(IF) | ~np.isfinite(I0)] = 0.0
        w_row = w.sum(axis=1)
        w_row[w_row == 0] = np.nan
        w_norm = w / w_row[:, None]
        avg = {"E": E}
        if compute_norm:
            ratio = IF / I0
            mean = np.nansum(ratio * w_norm, axis=1)
            nfin = np.isfinite(ratio).sum(axis=1)
            var = np.nansum((ratio - mean[:, None]) ** 2 * w_norm, axis=1) / np.maximum(1, nfin - 1)
            avg["IF_over_I0"] = mean
            avg["err"] = np.sqrt(var)
        else:
            ifs = np.nansum(IF * w_norm, axis=1)
            i0s = np.nansum(I0 * w_norm, axis=1)
            avg["IF_over_I0"] = ifs / i0s
            avg["err"] = np.full(nE, np.nan)
        avg["sec_total"] = np.nansum(sec, axis=1)
        avg["n_kept"] = (np.isfinite(IF) & np.isfinite(I0)).sum(axis=1)
        avg["IF_sum"] = np.nansum(IF, axis=1)
        avg["I0_sum"] = np.nansum(I0, axis=1)
        if empty_as_nan:
            empty = avg["n_kept"] == 0
            for k in ("IF_over_I0", "err", "sec_total", "IF_sum", "I0_sum"):
                avg[k] = np.where(empty, np.nan, avg[k])
    info = {"weights_applied": w_scan, "kept_indices": kept, "scheme": scheme}
    return avg, info
