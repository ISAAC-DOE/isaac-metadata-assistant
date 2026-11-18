"""Stage tests on synthetic inputs with known answers (no MATLAB needed)."""
import numpy as np
import pytest

from xas_analysis.average import AlignedScan, average_scans
from xas_analysis.calib import align_and_resample, find_inflection_point
from xas_analysis.io.spec import parse_spec, read_xas_scans
from xas_analysis.matlab_compat import gradient, mode_smallest, movmean, save_ascii


# ---------------- matlab_compat
def test_gradient_matches_matlab_formula_on_uneven_grid():
    x = np.array([0.0, 1.0, 3.0, 4.0])
    y = np.array([0.0, 1.0, 9.0, 16.0])
    # MATLAB: [1, (9-0)/3, (16-1)/3, 7]
    assert np.allclose(gradient(y, x), [1.0, 3.0, 5.0, 7.0])
    assert not np.allclose(gradient(y, x), np.gradient(y, x))  # numpy differs here


def test_movmean_shrink_and_mode_ties():
    assert np.allclose(movmean([1, 2, 3, 4, 5], 3), [1.5, 2, 3, 4, 4.5])
    assert np.allclose(movmean([1, 2, 3, 4], 2), [1, 1.5, 2.5, 3.5])
    assert mode_smallest([5, 7, 7, 5, 3]) == 5


def test_save_ascii_matlab_format(tmp_path):
    save_ascii(tmp_path / "m", np.array([[4835.996, -0.242816]]))
    assert (tmp_path / "m").read_text() == "   4.8359960e+03  -2.4281600e-01\n"


# ---------------- SPEC parsing
SPEC = """#F test.spec
#E 1700000000
#D Mon Nov  9 10:00:00 2026
#C user oscar
#O0 mono  Sz  Sx
#O1 Sy

#S 1  ascan  mono 11200 11260 4 1
#D Mon Nov  9 10:01:00 2026
#T 1  (Seconds)
#P0 11200 1.5 2.5
#P1 3.5
#N 4
#L absev  vortDT  I0  Seconds
11200 10 100 1
11201 11 101 1
11202 12 102 1
11203 13 103 1
11204 14 104 1
@A 1 2 3
11205 15 105
%S 2  ascan  mono 11200 11260 4 1
#L absev  VORTDT  I0
11200 20 200
11201 21 201
"""


def test_parse_spec(tmp_path):
    f = tmp_path / "s.spec"
    f.write_text(SPEC)
    with pytest.warns(UserWarning, match="ragged"):
        sp = parse_spec(f)
    assert sp.motor_names == ["mono", "Sz", "Sx", "Sy"]
    assert len(sp.scans) == 2
    s1 = sp.scans[0]
    assert s1.num == 1 and s1.macro[0] == "ascan" and s1.time_per_pt == 1
    assert s1.column_names == ["absev", "vortDT", "I0", "Seconds"]
    assert s1.data.shape == (5, 4)            # ragged 3-col row dropped, '@A' ignored
    assert np.allclose(s1.motor_pos, [11200, 1.5, 2.5, 3.5])
    assert sp.scans[1].num == 2               # '%S' accepted as '#S'


def test_read_xas_scans_channels(tmp_path):
    f = tmp_path / "s.spec"
    f.write_text(SPEC)
    with pytest.warns(UserWarning):
        sc = read_xas_scans(f, min_points=2)
    assert [s.num for s in sc] == [1, 2]
    assert np.allclose(sc[0].IF, [10, 11, 12, 13, 14])
    assert np.allclose(sc[1].IF, [20, 21])    # case-insensitive fallback VORTDT
    assert sc[0].sec is None                  # no 'sec' column ('Seconds' != 'sec')
    with pytest.warns(UserWarning):
        sc = read_xas_scans(f, min_points=5)  # scan 2 too short
    assert [s.num for s in sc] == [1]


# ---------------- calibration
def _glitch(E, E0, w=0.3):
    return 1e5 * (1 - 0.05 * 0.5 * (1 + np.tanh((E - E0) / w)))


def test_inflection_recovers_glitch_on_uneven_grid():
    rng = np.random.default_rng(0)
    E = np.sort(11220 + 30 * rng.random(400))
    E0 = 11232.71
    Ei, info = find_inflection_point(E, _glitch(E, E0), [11231.5, 11234.0])
    assert info["ok"]
    assert abs(Ei - E0) < 0.02


def test_inflection_reports_too_few_points():
    E = np.linspace(0, 10, 11)
    Ei, info = find_inflection_point(E, E ** 2, [3.1, 3.9])
    assert np.isnan(Ei) and "points" in info["reason"]


def test_align_and_resample_applies_shift():
    E = np.linspace(11200, 11260, 601)
    y = np.c_[np.sin(E / 3), E]
    tgt = np.linspace(11210, 11250, 200)
    out, info = align_and_resample(E, y, 11232.5, 11232.8, tgt)
    assert info["ok"] and np.isclose(info["shift_eV"], 0.3)
    assert np.allclose(out[:, 1], tgt - 0.3, atol=1e-9)   # y(E) seen at E+shift


# ---------------- averaging
def test_average_uniform_mean_and_sem():
    E = np.arange(5.0)
    r = np.array([[1, 2, 3, 4, 5], [3, 4, 5, 6, 7.0]])
    scans = [AlignedScan(i, E, r[i] * 10, np.full(5, 10.0), 1.0) for i in range(2)]
    avg, info = average_scans(scans)
    assert np.allclose(avg["IF_over_I0"], [2, 3, 4, 5, 6])
    assert np.allclose(avg["err"], 1.0)                    # SEM of two values 2 apart
    assert np.allclose(avg["sec_total"], 2.0)
    assert info["scheme"] == "uniform"


def test_average_nan_points_and_outliers():
    E = np.arange(3.0)
    a = AlignedScan(1, E, np.array([1, np.nan, 3.0]), np.ones(3), 1.0)
    b = AlignedScan(2, E, np.array([3, 4, 5.0]), np.ones(3), 1.0)
    c = AlignedScan(3, E, np.array([100, 100, 100.0]), np.ones(3), 1.0, keep=False)
    avg, _ = average_scans([a, b, c])
    assert np.allclose(avg["IF_over_I0"], [2, 4, 4])
    assert list(avg["n_kept"]) == [2, 1, 2]
