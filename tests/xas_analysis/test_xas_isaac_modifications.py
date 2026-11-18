"""ISAAC's local modifications of the vendored xas-analysis engine (src/xas_analysis/PROVENANCE.md M1-M5).

Synthetic spectra only (unmistakably fake: SYN_ names, a smooth logistic edge at the tabulated Ir L3 energy)."""
import warnings
from datetime import datetime

import pytest

np = pytest.importorskip("numpy", reason="needs the optional `processing` extra")
pytest.importorskip("scipy", reason="needs the optional `processing` extra")
yaml = pytest.importorskip("yaml", reason="needs the optional `processing` extra")


from xas_analysis.average import AlignedScan  # noqa: E402
from xas_analysis.pipeline import reduce, screen_report, screen_scans  # noqa: E402
from xas_analysis.survey import FileInfo, ScanInfo, measurement_mode, survey_files  # noqa: E402

E_EDGE = 11215.0
GLITCH = 11226.6


def _aligned(n=7, seed=3, key_prefix=None):
    E = np.arange(11200.0, 11260.01, 0.25)
    mu = 1 + 0.5 * (1 + np.tanh((E - 11215) / 1.5))
    rng = np.random.default_rng(seed)
    return E, [AlignedScan(k, E, mu * (1 + 1e-3 * rng.standard_normal(E.size)), np.ones_like(E), 1.0,
                           anchor_eV=11232.70 + 0.004 * rng.standard_normal(),
                           key=None if key_prefix is None else f"{key_prefix}#{k}") for k in range(1, n + 1)]


def test_screen_report_is_report_only():
    E, out = _aligned()
    out[2].anchor_eV += 0.20
    out[4].IF = np.zeros_like(E)
    out[5].IF = (1 + 0.5 * (1 + np.tanh((E - 11225) / 1.5))) * 1.0
    cfg = {"anchor_mad": 5, "shape_mad": 6, "window_eV": [11205, 11240]}
    rows = screen_report(out, cfg)
    assert all(a.keep for a in out)                       # nothing changed on the scans
    assert {(r["scan"], r["test"]) for r in rows} == {(3, "anchor"), (5, "dead_channel"), (6, "shape")}
    for r in rows:
        assert r["reason"] and r["value"] is not None and r["threshold"] is not None
    # screen_scans gives exactly what it gave before (report + apply)
    assert dict(screen_scans(out, cfg)).keys() == {3, 5, 6}
    assert [a.num for a in out if a.keep] == [1, 2, 4, 7]


def test_pooled_scans_keep_their_identity():
    """Two files pooled into one sample: scan numbers repeat; each scan is reported by its own key."""
    E, a = _aligned(4, seed=1, key_prefix="SYN_A")
    _, b = _aligned(4, seed=2, key_prefix="SYN_B")
    a[0].anchor_eV += 0.3                                 # SYN_A scan 1 and SYN_B scan 1 both off
    b[0].anchor_eV += 0.3
    rows = screen_report(a + b, {"anchor_mad": 5})
    assert sorted(r["key"] for r in rows) == ["SYN_A#1", "SYN_B#1"]
    got = screen_scans(a + b, {"anchor_mad": 5})
    assert len(got) == 2                                  # before M1: scan 1 of SYN_B was swallowed (same number)
    assert not a[0].keep and not b[0].keep


def _scaninfo(file, n, shift, t, rng, foil=False, trans=False):
    E = np.r_[np.arange(11165, 11205, 5.0), np.arange(11205, 11240, 0.25), np.arange(11240, 11500, 4.0)]
    tt = E + shift
    I0 = 1e5 * (1 - 0.0004 * (E - 11165)) * (1 - 0.06 * np.exp(-((tt - GLITCH) / 0.22) ** 2))
    mu = 0.05 + 1.0 / (1 + np.exp(-(tt - E_EDGE) / 1.2)) + 3 * np.exp(-((tt - 11218) / 1.5) ** 2)
    if trans:
        IF = np.full(E.size, 5.0) * (1 + 1e-3 * rng.standard_normal(E.size))     # no fluorescence edge
        I1 = I0 * np.exp(-(0.4 + 0.6 / (1 + np.exp(-(tt - E_EDGE) / 1.2))))
    else:
        IF = mu * I0 * 1e-3 * (1 + 2e-3 * rng.standard_normal(E.size))
        I1 = np.full(E.size, 3.0)
    I2 = I1 * 0.5
    return ScanInfo(file, n, t, E, {"I0": I0, "I1": I1, "I2": I2, "vortDT": IF})


def test_survey_files_on_pooled_groups():
    """One FileInfo per record group, pooling scans of several files; the caller's role wins over the name."""
    rng = np.random.default_rng(0)
    files = []
    for k, name in enumerate(["SYN_ref_pellet", "SYN_sample_a", "SYN_sample_b"]):
        fi = FileInfo(path=name, name=name, fmt="spec", role="reference" if k == 0 else "sample")
        fi.scans = [_scaninfo(f"{name}_{f}", n, 0.01 * n, datetime(2025, 4, 12, 10 + k, n), rng)
                    for f in ("spot1", "spot2") for n in (1, 2)]
        files.append(fi)
    al = FileInfo(path="SYN_alignx", name="SYN_alignx", fmt="spec", role="sample")   # named align*, role sample
    al.scans = [_scaninfo("SYN_alignx", 1, 0.0, datetime(2025, 4, 12, 14, 0), rng)]
    files.append(al)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rep = survey_files(files, [], "synthetic")
    assert rep["edge"]["element"] == "Ir" and rep["edge"]["core"] == "L3"
    assert rep["recommendation"]["calibration"]["mode"] == "glitch_I0"
    roles = {f["name"]: f["role_guess"] for f in rep["files"]}
    assert roles == {"SYN_ref_pellet": "reference", "SYN_sample_a": "sample", "SYN_sample_b": "sample",
                     "SYN_alignx": "sample"}


def test_survey_undated_alignment_scan():
    rng = np.random.default_rng(1)
    smp = FileInfo(path="s", name="SYN_sample", fmt="spec", role="sample")
    smp.scans = [_scaninfo("SYN_sample", n, 0.0, datetime(2025, 4, 12, 10, n), rng) for n in (1, 2, 3)]
    al = FileInfo(path="a", name="SYN_alignment", fmt="spec", role="alignment")
    s = _scaninfo("SYN_alignment", 7, 0.0, None, rng, trans=True)   # an edge scan in transmission, no date
    al.scans = [s]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rep = survey_files([smp, al], [], "synthetic")                # raised TypeError before M5
    assert any("undated" in f for f in rep["findings"])


def test_measurement_mode_detects_transmission():
    rng = np.random.default_rng(2)
    fluo = [_scaninfo("SYN_f", n, 0.0, None, rng) for n in (1, 2)]
    trans = [_scaninfo("SYN_t", n, 0.0, None, rng, trans=True) for n in (1, 2)]
    assert measurement_mode(fluo, E_EDGE, "SYN_sample")["mode"] == "fluorescence"
    m = measurement_mode(trans, E_EDGE, "SYN_pellet")
    assert m["mode"] == "transmission" and m["transmission_step"] > 0.5
    # a HERFD edge AND a name saying transmission, with ln(I0/I1) stepping: transmission (the transmission-named pellet case)
    both = [_scaninfo("SYN_b", n, 0.0, None, rng) for n in (1, 2)]
    for s in both:
        s.ch["I1"] = s.ch["I0"] * np.exp(-(0.5 + 0.07 / (1 + np.exp(-(s.E - E_EDGE) / 1.2))))
    assert measurement_mode(both, E_EDGE, "SYN_IrO2_pellet_transmission")["mode"] == "transmission"
    assert measurement_mode(both, E_EDGE, "SYN_IrO2_pellet")["mode"] == "fluorescence"


def _spec_file(path, trans=False, seed=0):
    rng = np.random.default_rng(seed)
    lines = ["#F x", "#E 1", "#D Sat Apr 12 10:00:00 2025", ""]
    for n in (1, 2, 3):
        s = _scaninfo(path.name, n, 0.0, None, rng, trans=trans)
        lines += [f"#S {n}  gscan energy 11165 11500 1", f"#D Sat Apr 12 1{n}:00:00 2025",
                  "#L energy  absev  vortDT  I0  I1  I2  sec"]
        lines += [f"{e - 2.3:.3f} {e:.4f} {f:.5f} {i0:.3f} {i1:.4f} {i2:.4f} 1"
                  for e, f, i0, i1, i2 in zip(s.E, s.ch["vortDT"], s.ch["I0"], s.ch["I1"], s.ch["I2"])]
        lines.append("")
    path.write_text("\n".join(lines))


def test_reduce_skips_a_transmission_sample(tmp_path):
    _spec_file(tmp_path / "SYN_sample", seed=1)
    _spec_file(tmp_path / "SYN_pellet_transmission", trans=True, seed=2)
    recipe = {"samples": [{"spec": "SYN_sample", "name": "SYN_sample"},
                          {"spec": "SYN_pellet_transmission", "name": "SYN_pellet_transmission"}],
              "calibration": {"mode": "glitch_I0", "method": "model", "window_eV": [11224, 11229],
                              "shape_window_eV": [11224.4, 11229.2], "reference_sample": "SYN_sample",
                              "reference_scan": "mean"},
              "normalize": {"element": "Ir", "core": "L3", "range": [11166, 11206, 11275, 11487]},
              "outputs": {"output_dir": "out", "save_per_scan": False}, "quiet": True}
    (tmp_path / "r.yaml").write_text(yaml.safe_dump(recipe))
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        res = reduce(tmp_path / "r.yaml")
    assert [s["name"] for s in res["samples"]] == ["SYN_sample"]
    assert res["skipped_samples"][0]["name"] == "SYN_pellet_transmission"
    assert res["skipped_samples"][0]["evidence"]["mode"] == "transmission"
    assert any("transmission-mode" in str(x.message) for x in w)
    # the recipe can keep it: mode fluorescence
    recipe["samples"][1]["mode"] = "fluorescence"
    (tmp_path / "r2.yaml").write_text(yaml.safe_dump(recipe))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res2 = reduce(tmp_path / "r2.yaml")
    assert len(res2["samples"]) == 2 and not res2["skipped_samples"]
