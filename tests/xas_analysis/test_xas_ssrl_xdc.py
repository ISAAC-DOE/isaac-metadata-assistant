"""SSRL EXAFS Data Collector reader + foil_timeline calibration on synthetic files."""
import pytest

np = pytest.importorskip("numpy", reason="needs the optional `processing` extra")
pytest.importorskip("scipy", reason="needs the optional `processing` extra")
yaml = pytest.importorskip("yaml", reason="needs the optional `processing` extra")


from xas_analysis.io.ssrl_xdc import read_xdc_scans  # noqa: E402
from xas_analysis.pipeline import reduce  # noqa: E402

COLS = ["Real time clock", "Sum_RTC", "Requested Energy", "Achieved Energy", "I0", "I1", "I2",
        "Lytle", "SCA1_1", "SCA1_2", "ICR1_1", "ICR1_2"]


def _write(path, date, E_true_offset, foil=False, n=None):
    E = np.arange(4900.0, 5050.0, 0.5)[:n]
    t = E + E_true_offset
    I0 = np.full(E.size, 1e5)
    mu_f = 0.5 + 2.0 * (0.5 + np.arctan((t - 4966.0) / 0.7) / np.pi)
    I1 = I0 * np.exp(-mu_f) if foil else np.full(E.size, 3.0)
    f = (0.2 + 1.0 * (0.5 + np.arctan((t - 4980.0) / 2.0) / np.pi)) * 1e3
    rows = [[1, k + 1, e, e, i0, i1, 2.0, 0.0, fi / 2, fi / 2, 1e4, 1e4]
            for k, (e, i0, i1, fi) in enumerate(zip(E, I0, I1, f))]
    hdr = ["SSRL   EXAFS Data Collector 4.0", date, f"PTS: {E.size:10d} COLS: {len(COLS):10d}",
           "xsp7sca1.det", "TiK.rgn", "43 unfocused", "comment", "", "Weights: ",
           " ".join(["1.000"] * len(COLS)), "Offsets: ", " ".join(["0.000"] * len(COLS)), "Data: "]
    body = hdr + COLS + [""] + [" ".join(f"{v:.3f}" for v in r) for r in rows]
    path.write_text("\n".join(body) + "\n")


def test_reader_and_foil_timeline(tmp_path):
    _write(tmp_path / "foilA_A.001", "Sun Jul 27 10:00:00 2025", 0.0, foil=True)
    _write(tmp_path / "foilB_A.001", "Sun Jul 27 20:00:00 2025", -0.10, foil=True)   # mono drifted
    _write(tmp_path / "smp_A.001", "Sun Jul 27 12:30:00 2025", -0.025)                # 1/4 of the way
    _write(tmp_path / "smp_A.002", "Sun Jul 27 17:30:00 2025", -0.075)
    _write(tmp_path / "smp_A.003", "Sun Jul 27 18:00:00 2025", -0.08, n=60)           # aborted
    sc = read_xdc_scans(tmp_path / "smp")
    assert [s.num for s in sc] == [1, 2, 3]
    assert np.allclose(sc[0].IF, sc[0].data[:, 8] + sc[0].data[:, 9])
    recipe = {"reader": "ssrl_xdc",
              "samples": [{"spec": "smp", "name": "smp"}],
              "calibration": {"mode": "foil_timeline", "foil_window_eV": [4960, 4972],
                              "shape_window_eV": [4950, 4990],
                              "foils": [{"spec": "foilA", "ref_signal": "ln(I0/I1)"},
                                        {"spec": "foilB", "ref_signal": "ln(I0/I1)"}]},
              "screening": {"anchor_mad": 0, "shape_mad": 0},
              "outputs": {"output_dir": "out", "save_per_scan": False}, "quiet": True}
    (tmp_path / "r.yaml").write_text(yaml.safe_dump(recipe))
    res = reduce(tmp_path / "r.yaml")
    sh = {a.num: a.shift_eV for a in res["samples"][0]["scans"]}
    # mono reads E_true - offset: the foil anchor rises 4966.0 -> 4966.1 eV, so the shift
    # (ref anchor - anchor interpolated at the scan time) is the offset itself, -0.025 / -0.075
    assert abs(sh[1] + 0.025) < 0.004 and abs(sh[2] + 0.075) < 0.004
    assert [a.num for a in res["samples"][0]["scans"] if a.keep] == [1, 2]
