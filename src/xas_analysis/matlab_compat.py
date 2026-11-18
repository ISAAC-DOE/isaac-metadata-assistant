"""MATLAB built-ins whose numpy namesakes behave differently.

Only functions whose semantics differ are here; np.polyfit/np.polyval match MATLAB's
polyfit/polyval (descending coefficients, least squares).
"""
from __future__ import annotations

import numpy as np


def gradient(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """MATLAB ``gradient(y, x)`` for a vector with a coordinate vector.

    MATLAB uses (y[i+1] - y[i-1]) / (x[i+1] - x[i-1]) at interior points and one-sided
    first differences at the ends. ``numpy.gradient(y, x)`` uses a second-order
    non-uniform formula instead, which differs on uneven grids.
    """
    y = np.asarray(y, float)
    x = np.asarray(x, float)
    n = y.size
    g = np.empty(n)
    if n == 1:
        g[0] = 0.0
        return g
    g[0] = (y[1] - y[0]) / (x[1] - x[0])
    g[-1] = (y[-1] - y[-2]) / (x[-1] - x[-2])
    if n > 2:
        g[1:-1] = (y[2:] - y[:-2]) / (x[2:] - x[:-2])
    return g


def movmean(y: np.ndarray, k: int) -> np.ndarray:
    """MATLAB ``movmean(y, k)`` with the default 'shrink' endpoints.

    Odd k: window [i-(k-1)/2, i+(k-1)/2]. Even k: [i-k/2, i+k/2-1].
    """
    y = np.asarray(y, float)
    n = y.size
    if k <= 1:
        return y.copy()
    if k % 2:
        lo, hi = (k - 1) // 2, (k - 1) // 2
    else:
        lo, hi = k // 2, k // 2 - 1
    out = np.empty(n)
    for i in range(n):
        a, b = max(0, i - lo), min(n, i + hi + 1)
        out[i] = y[a:b].mean()
    return out


def mode_smallest(values) -> int:
    """MATLAB ``mode``: most frequent value, ties resolved to the smallest."""
    vals, counts = np.unique(np.asarray(values), return_counts=True)
    return int(vals[counts == counts.max()].min())


def interp1_linear(x: np.ndarray, y: np.ndarray, xq: np.ndarray) -> np.ndarray:
    """MATLAB ``interp1(x, Y, xq, 'linear', NaN)``; Y may be a vector or N x K matrix."""
    x = np.asarray(x, float)
    xq = np.asarray(xq, float)
    y = np.asarray(y, float)
    one_d = y.ndim == 1
    Y = y[:, None] if one_d else y
    out = np.empty((xq.size, Y.shape[1]))
    for j in range(Y.shape[1]):
        out[:, j] = np.interp(xq, x, Y[:, j], left=np.nan, right=np.nan)
    return out[:, 0] if one_d else out


def save_ascii(path, M: np.ndarray) -> None:
    """MATLAB ``save(path, 'M', '-ascii')``: 8 significant digits, '%16.7e' per value."""
    M = np.atleast_2d(np.asarray(M, float))
    with open(path, "w") as fh:
        for row in M:
            fh.write("".join(f"{v:16.7e}" for v in row) + "\n")
