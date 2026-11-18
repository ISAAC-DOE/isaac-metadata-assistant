"""Difference-spectrum decomposition and model-free relative normalization (synthetic)."""
import numpy as np

from xas_analysis.diffspec import decompose, difference, model_free_difference


def _spec(E, shift=0.0, sigma=0.0, scale=1.0):
    x = E - shift
    step = 1 / (1 + np.exp(-(x - 11564) / 0.8))
    wl = 1.4 * np.exp(-0.5 * ((x - 11565.5) / np.hypot(1.0, sigma)) ** 2) / (np.hypot(1.0, sigma) / 1.0)
    return scale * (step + wl)


def test_decompose_recovers_scale_shift_broadening():
    E = np.arange(11540, 11640, 0.1)
    g = np.arange(11556, 11600, 0.02)
    R = _spec(E)
    S = _spec(E, shift=0.060, sigma=0.20, scale=1.015)
    d = difference(E, S, E, R, g)
    r = decompose(g, d, E, R, sigma_eV=0.05)
    assert abs(r.shift_eV - 0.060) < 0.006
    assert abs(r.scale - 0.015) < 0.004
    assert r.broadening_eV2 > 0.01                       # sigma^2/2 = 0.02 (first-order)
    assert r.explained > 0.97


def test_model_free_difference_removes_edge_step_errors():
    E = np.arange(11540, 11800, 0.2)
    g = np.arange(11556, 11600, 0.05)
    R = 0.003 + 0.8 * _spec(E)
    S = 0.003 + 0.5 * _spec(E, shift=0.04)               # different loading (edge step), same pre level
    d, s = model_free_difference(E, S, E, R, g, pre=(11541, 11553), post=(11620, 11790))
    assert abs(s - 0.8 / 0.5) < 0.01                     # scaled to the reference
    r = decompose(g, d, E, _spec(E), sigma_eV=0.05)
    assert abs(r.shift_eV - 0.04) < 0.006 and abs(r.scale) < 0.005
