"""r2 review: a glitch away from the edge is never read as "on the edge" because it makes its own neighbourhood steep,
and points on the edge are said as unjudged, not cleared."""

import pytest

from isaac_api.local_import.processing import core as C, protocol as P, run as RUN

np = pytest.importorskip("numpy")
xafs = pytest.importorskip("larch.xafs")
E0 = 11564.0
NAMES = [f"SYN_ZZ1_{s:03d}.dat" for s in range(5)]


def _herfd(e, wl=1.0):
    return 0.05 + (0.5 + np.arctan((e - E0) / 0.7) / np.pi) + wl * 1.8 * np.exp(-0.5 * ((e - E0 - 1.6) / 1.1) ** 2)


def _scans(e):
    return np.vstack([_herfd(e, wl=1 + 0.02 * (s - 2)) + np.random.default_rng(s).normal(0, 0.003, e.size)
                      for s in range(5)])


def _points(M, e):
    params = P.resolve_params()
    dg = C.deglitch(M, e, params, np)
    clean = C.merge(M, dg["point_flags"], None, np)["mean"]
    nm = C.normalize(e, C.merge(M, None, None, np)["mean"], params, np, xafs)
    ok = np.isfinite(clean)
    return C.glitch_points_on_edge(dg["point_flags"], e, e[ok], clean[ok], nm["e0_eV"], np), nm["e0_eV"]


def test_a_derivative_shaped_glitch_20_ev_above_the_edge_stays_off_the_edge():
    e = np.arange(11500.0, 11700.0, 0.25)
    M = _scans(e)
    i = int(np.searchsorted(e, E0 + 20))
    M[3, i - 1] -= 2.0
    M[3, i + 1] += 2.0
    pts, _ = _points(M, e)
    assert pts and not any(on for _, en, on in pts if abs(en - (E0 + 20)) < 2)


def test_a_flag_at_e0_is_said_as_unjudged_not_cleared():
    e = np.arange(11500.0, 11700.0, 0.25)
    M = _scans(e)
    M[3, int(np.searchsorted(e, E0 + 0.5))] += 1.0
    pts, e0 = _points(M, e)
    said = RUN._glitch_points_on_edge(pts, e0, NAMES)
    if said:  # the spike is on the edge: it must not be called evidence of no glitch
        assert "cannot judge" in said["statement"]
        assert "nothing here is evidence of a glitch" not in said["statement"]
        assert "neither counted as glitches nor cleared" in said["statement"]
