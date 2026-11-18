"""survey + recipe init on synthetic beamtime folders (glitch-only and in-scan foil)."""
import numpy as np
import yaml

from xas_analysis.pipeline import reduce
from xas_analysis.recipe_init import write_draft
from xas_analysis.survey import survey

E_EDGE = 11215.0
GLITCH = 11226.6


def _spec(path, nscan, offsets, foil=False, seed=0, hour0=10):
    rng = np.random.default_rng(seed)
    E = np.r_[np.arange(11165, 11205, 5.0), np.arange(11205, 11240, 0.25), np.arange(11240, 11500, 4.0)]
    lines = ["#F x", "#E 1", "#D Sat Apr 12 10:00:00 2025", ""]
    for n in range(1, nscan + 1):
        sh = offsets[n - 1]
        t = E + sh                                   # true energy of each point
        I0 = 1e5 * (1 - 0.0004 * (E - 11165)) * (1 - 0.06 * np.exp(-((t - GLITCH) / 0.22) ** 2))
        mu = 0.05 + 1.0 / (1 + np.exp(-(t - E_EDGE) / 1.2)) + 3 * np.exp(-((t - 11218) / 1.5) ** 2)
        IF = mu * I0 * 1e-3 * (1 + 2e-3 * rng.standard_normal(E.size))
        if foil:
            muf = 0.3 + 0.8 / (1 + np.exp(-(t - E_EDGE) / 0.9))
            I1 = 0.6 * I0
            I2 = I1 * np.exp(-muf)
        else:
            I1 = np.full(E.size, 3.0)
            I2 = np.full(E.size, 2.0)
        lines += [f"#S {n}  gscan energy 11165 11500 1", f"#D Sat Apr 12 {hour0 + n:02d}:00:00 2025",
                  "#L energy  absev  vortDT  I0  I1  I2  sec"]
        lines += [f"{e - 2.3:.3f} {e:.4f} {f:.5f} {i0:.3f} {i1:.4f} {i2:.4f} 1"
                  for e, f, i0, i1, i2 in zip(E, IF, I0, I1, I2)]
        lines.append("")
    path.write_text("\n".join(lines))


def test_survey_glitch_folder(tmp_path):
    d = tmp_path / "bt"
    d.mkdir()
    _spec(d / "01_IrO2_ref", 3, [0.0, 0.01, -0.01], seed=1, hour0=8)
    _spec(d / "02_sample_060mV", 4, [0.05, 0.06, 0.04, 0.05], seed=2, hour0=12)
    (d / "logbook.txt").write_text("notes")
    rep = survey(d)
    assert rep["edge"]["element"] == "Ir" and rep["edge"]["core"] == "L3"
    assert rep["fluorescence_channel"]["name"] == "vortDT"
    assert abs(rep["absev_minus_energy"]["median_eV"] - 2.3) < 0.01
    assert rep["docs"] == ["logbook.txt"]
    cal = rep["recommendation"]["calibration"]
    assert cal["mode"] == "glitch_I0" and cal["method"] in ("model", "shape")
    w = cal["shape_window_eV"]
    assert w[0] < GLITCH < w[1]
    # draft -> reduce: per-scan shifts recover the offsets relative to the reference file mean
    out = tmp_path / "r.yaml"
    write_draft(d, out, rep)
    r = yaml.safe_load(out.read_text())
    assert r["calibration"]["reference_sample"] == "earliest"
    r["outputs"]["output_dir"] = str(tmp_path / "out")
    r["quiet"] = True
    out.write_text(yaml.safe_dump(r))
    res = reduce(out)
    smp = next(s for s in res["samples"] if s["name"] == "02_sample_060mV")
    got = [a.shift_eV for a in smp["scans"]]
    assert np.allclose(got, [0.05, 0.06, 0.04, 0.05], atol=0.002)   # model fit: no grid-phase bias
    assert (tmp_path / "out" / "02_sample_060mV_avg_nrm").exists()


def test_survey_in_scan_foil(tmp_path):
    d = tmp_path / "bt"
    d.mkdir()
    _spec(d / "01_sample", 3, [0.0, 0.02, -0.03], foil=True, seed=3)
    _spec(d / "02_sample", 3, [0.1, 0.12, 0.08], foil=True, seed=4, hour0=14)
    rep = survey(d)
    cal = rep["recommendation"]["calibration"]
    assert cal["mode"] == "ref_foil"
    assert cal["ref_signal"] in ("ln(I1/I2)", "ln(I0/I2)")


def test_glitch_model_center_unbiased():
    """Gaussian-dip fit recovers a narrow glitch at any sub-grid phase (template match does not)."""
    from xas_analysis.calib import fit_glitch_center
    E = np.arange(11205, 11240, 0.25)
    for sh in np.arange(-0.12, 0.121, 0.03):
        y = np.log(1e5 * (1 - 0.0004 * (E - 11165)) * (1 - 0.06 * np.exp(-((E + sh - GLITCH) / 0.15) ** 2)))
        c, info = fit_glitch_center(E, y, [11223, 11230])
        assert info["ok"] and abs((GLITCH - sh) - c) < 0.002


def test_glitch_doublet_midpoint_stable():
    """Doublet glitch with varying relative depths: the one-dip centre jumps between the dips,
    the two-dip midpoint stays within a few meV (BL15-2 2019 Pt L3 case)."""
    from xas_analysis.calib import fit_glitch_center, fit_glitch_doublet
    E = np.r_[np.arange(11690, 11700, 5.0), np.arange(11700, 11706, 0.2), np.arange(11706, 11720, 5.0)]
    rng = np.random.default_rng(5)
    singles, mids = [], []
    for a1, a2 in ((0.015, 0.010), (0.010, 0.015), (0.013, 0.013), (0.016, 0.009)):
        g = 1 - a1 * np.exp(-0.5 * ((E - 11702.1) / 0.4) ** 2) - a2 * np.exp(-0.5 * ((E - 11703.55) / 0.4) ** 2)
        y = np.log(1e5 * (1 - 1e-4 * (E - 11690)) * g * (1 + 5e-4 * rng.standard_normal(E.size)))
        singles.append(fit_glitch_center(E, y, [11699.5, 11706])[0])
        c, info = fit_glitch_doublet(E, y, [11699.5, 11706])
        assert info["ok"] and abs(info["sep_eV"] - 1.45) < 0.1
        mids.append(c)
    assert np.ptp(singles) > 0.8                     # one-dip fit jumps between the dips
    assert np.ptp(mids) < 0.03 and abs(np.mean(mids) - 11702.825) < 0.02


def test_dark_chamber_not_a_foil():
    """A flat ion-chamber offset (BL6-2 2018 I1 ~ 987 counts) is dark; a lit chamber that follows
    I0 is not."""
    from xas_analysis.survey import _dark
    rng = np.random.default_rng(0)
    I0 = 23000 * (1 - 0.05 * np.linspace(0, 1, 225)) * (1 + 1e-3 * rng.standard_normal(225))
    dark = 987 + rng.normal(0, 1.0, 225)
    lit = 0.4 * I0 * np.exp(-0.2 * (np.arange(225) > 100))
    assert _dark(dark, I0) and not _dark(lit, I0)
