"""End to end: synthetic SPEC files with known per-scan mono drifts -> reduce()."""
import numpy as np
import yaml

from xas_analysis.pipeline import reduce

GLITCH = 11232.70          # true glitch energy in the reference frame


def _write_spec(path, shifts, seed, hour=None):
    """Each scan's mono axis is offset by `shift` (the glitch appears at GLITCH - shift)."""
    rng = np.random.default_rng(seed)
    lines = ["#F x", "#E 1", "#D today", ""]
    for n, sh in enumerate(shifts, 1):
        if hour is not None:
            lines.append(f"#D Sat Nov 13 {hour + n:02d}:00:00 2021")
        E = np.arange(11200.0, 11260.01, 0.25)
        true_E = E + sh
        mu = 1 + 0.5 * (1 + np.tanh((true_E - 11215) / 1.5))
        I0 = 1e5 * (1 - 0.05 * 0.5 * (1 + np.tanh((true_E - GLITCH) / 0.3)))
        IF = mu * I0 * 1e-3 * (1 + 1e-4 * rng.standard_normal(E.size))
        lines += [f"#S {n}  ascan  mono 11200 11260 240 1", "#L absev  vortDT  I0  sec"]
        lines += [f"{e:.4f} {f:.6f} {i:.4f} 1" for e, f, i in zip(E, IF, I0)]
        lines.append("")
    path.write_text("\n".join(lines))


def test_reduce_recovers_shifts_and_writes_matlab_files(tmp_path):
    ref_shifts = [0.0, 0.05, -0.04]
    smp_shifts = [0.12, 0.10, 0.15, 0.30]
    _write_spec(tmp_path / "ref.spec", ref_shifts, 1)
    _write_spec(tmp_path / "smp.spec", smp_shifts, 2)
    recipe = {
        "samples": [
            {"spec": "ref.spec", "name": "ref", "role": "reference"},
            {"spec": "smp.spec", "name": "smp", "outliers": [4]},
        ],
        "calibration": {"window_eV": [11231.0, 11234.5], "reference_sample": "ref", "reference_scan": 1},
        "outputs": {"output_dir": "out"},
        "quiet": True,
    }
    (tmp_path / "r.yaml").write_text(yaml.safe_dump(recipe))
    res = reduce(tmp_path / "r.yaml")

    got = {s["name"]: [a.shift_eV for a in s["scans"]] for s in res["samples"]}
    # the pipeline shift is (ref anchor - scan anchor) = true mono offset of the scan.
    # Tolerance: the 3-point-parabola anchor (MATLAB find_inflection_point) has a sub-grid
    # bias of up to +/-0.0085 eV per anchor for a 0.3 eV glitch on a 0.25 eV grid, so a
    # shift (difference of two anchors) is good to ~0.017 eV (see docs/PORT_STATUS.md).
    assert np.allclose(got["ref"], ref_shifts, atol=0.02)
    assert np.allclose(got["smp"], smp_shifts, atol=0.02)
    smp = res["samples"][1]
    assert smp["avg_info"]["kept_indices"] == [0, 1, 2]       # scan 4 = outlier
    out = tmp_path / "out"
    names = sorted(p.name for p in out.iterdir())
    assert "smp_avg_raw" in names and "smp_scans004_raw" in names and "reduce_diag.json" in names
    M = np.loadtxt(out / "smp_avg_raw")
    assert M.shape[1] == 4
    first = (out / "smp_avg_raw").read_text().splitlines()[0]
    assert len(first) == 64                                   # 4 x '%16.7e'
    # MATLAB quirk (default): sample scans all shifted by > +0.1 eV, so the first target
    # point lies outside every scan and the average file carries a zero row there
    assert M[0, 0] == 11200.0 and M[0, 1] == 0.0 and M[0, 3] == 0.0

    # with drop_empty_points the zero rows are gone and the edge sits at the same place
    # in every averaged spectrum
    recipe["averaging"] = {"drop_empty_points": True}
    recipe["outputs"] = {"output_dir": "out2"}
    (tmp_path / "r2.yaml").write_text(yaml.safe_dump(recipe))
    reduce(tmp_path / "r2.yaml")
    for nm in ("ref", "smp"):
        a = np.loadtxt(tmp_path / "out2" / f"{nm}_avg_raw")
        assert np.all(a[:, 1] > 0)
        i = np.argmax(np.gradient(a[:, 1], a[:, 0]))
        assert abs(a[i, 0] - 11215.0) < 0.3


def test_reference_earliest_mean(tmp_path):
    """reference_sample: earliest + reference_scan: mean -> shifts relative to the mean anchor
    of the earliest file's scans."""
    early, late = [0.02, -0.04, 0.05], [0.12, 0.10, 0.15]
    _write_spec(tmp_path / "late.spec", late, 3, hour=10)
    _write_spec(tmp_path / "early.spec", early, 4, hour=2)
    recipe = {
        "samples": [{"spec": "late.spec", "name": "late"}, {"spec": "early.spec", "name": "early"}],
        "calibration": {"window_eV": [11231.0, 11234.5], "reference_sample": "earliest",
                        "reference_scan": "mean"},
        "outputs": {"output_dir": "out", "save_per_scan": False},
        "quiet": True,
    }
    (tmp_path / "r.yaml").write_text(yaml.safe_dump(recipe))
    res = reduce(tmp_path / "r.yaml")
    assert res["reference"]["sample"] == "early"
    m = np.mean(early)
    got = {s["name"]: [a.shift_eV for a in s["scans"]] for s in res["samples"]}
    assert np.allclose(got["early"], np.array(early) - m, atol=0.02)
    assert np.allclose(got["late"], np.array(late) - m, atol=0.02)


def test_screening_drops_anchor_and_dead_channel_scans():
    from xas_analysis.average import AlignedScan
    from xas_analysis.pipeline import screen_scans
    E = np.arange(11200.0, 11260.01, 0.25)
    mu = 1 + 0.5 * (1 + np.tanh((E - 11215) / 1.5))
    rng = np.random.default_rng(3)
    out = [AlignedScan(n, E, mu * (1 + 1e-3 * rng.standard_normal(E.size)), np.ones_like(E), 1.0,
                       anchor_eV=11232.70 + 0.004 * rng.standard_normal()) for n in range(1, 8)]
    out[2].anchor_eV += 0.20                       # scan 3: mono jump
    out[4].IF = np.zeros_like(E)                   # scan 5: dead detector
    out[5].IF = (1 + 0.5 * (1 + np.tanh((E - 11225) / 1.5))) * 1.0   # scan 6: wrong shape
    got = dict(screen_scans(out, {"anchor_mad": 5, "shape_mad": 6, "window_eV": [11205, 11240]}))
    assert set(got) == {3, 5, 6}
    assert [a.num for a in out if a.keep] == [1, 2, 4, 7]


def test_normalize_stage_writes_nrm(tmp_path):
    from xas_analysis.pipeline import normalize_spectrum
    from xas_analysis.model.mback import atomic_step, _edge
    E = np.arange(11150.0, 11500.01, 1.0)
    Ek = E / 1000
    mu, _ = atomic_step(77, Ek, _edge(77, "L3", Ek)[0])
    raw = 0.02 + 0.01 * (Ek / 11.215) ** -3 + 0.37 * mu
    res = normalize_spectrum(E, raw, {"element": "Ir", "core": "L3", "range": [11160, 11206, 11275, 11490]})
    assert abs(res.info["A_edge"] / 0.37 - 1) < 1e-3
    for model in ("victoreen_linear", "poly"):
        assert normalize_spectrum(E, raw, {"element": "Ir", "core": "L3", "model": model,
                                           "range": [11160, 11206, 11275, 11490]}) is not None


def test_shape_shift_recovers_offset():
    from xas_analysis.pipeline import fit_shape_shift
    E = np.arange(8960.0, 9010.0, 0.15)
    foil = lambda e: np.arctan((e - 8979.0) / 0.8) + 0.3 * np.exp(-((e - 8982.0) / 1.5) ** 2)
    rng = np.random.default_rng(5)
    for d in (-0.237, 0.0, 0.081):
        y = 2.0 * foil(E + d) + 0.4 + 1e-3 * rng.standard_normal(E.size)
        got, _ = fit_shape_shift(E, y, E, foil(E), [8970, 9000])
        assert abs(got - d) < 0.003


def test_ref_foil_shape_pipeline(tmp_path):
    """Foil edge in ln(I0/I2) with known per-scan mono offsets -> recovered shifts."""
    rng = np.random.default_rng(7)
    shifts = [0.0, 0.06, -0.09, 0.12]
    lines = ["#F x", "#E 1", "#D today", ""]
    for n, sh in enumerate(shifts, 1):
        E = np.arange(8960.0, 9010.0, 0.15)
        t = E + sh
        mu_f = 1.0 + 0.8 * (0.5 + np.arctan((t - 8979.0) / 0.8) / np.pi)
        I0 = np.full(E.size, 1e5)
        I2 = I0 * np.exp(-mu_f)
        IF = (1 + 0.5 * (0.5 + np.arctan((t - 8981) / 1.2) / np.pi)) * 1e2 * (1 + 1e-3 * rng.standard_normal(E.size))
        lines += [f"#S {n}  ascan  energy 8960 9010 333 1", "#L absev  vortDT  I0  I2  sec"]
        lines += [f"{e:.4f} {f:.6f} {i:.4f} {j:.6f} 1" for e, f, i, j in zip(E, IF, I0, I2)]
        lines.append("")
    (tmp_path / "cu.spec").write_text("\n".join(lines))
    recipe = {"samples": [{"spec": "cu.spec", "name": "cu"}],
              "calibration": {"mode": "ref_foil", "ref_signal": "ln(I0/I2)", "method": "shape",
                              "window_eV": [8977, 8981], "shape_window_eV": [8970, 9000],
                              "reference_sample": "cu", "reference_scan": 1},
              "outputs": {"output_dir": "out", "save_per_scan": False}, "quiet": True}
    (tmp_path / "r.yaml").write_text(yaml.safe_dump(recipe))
    res = reduce(tmp_path / "r.yaml")
    got = [a.shift_eV for a in res["samples"][0]["scans"]]
    assert np.allclose(got, shifts, atol=0.004)


def test_normalize_keeps_zero_counts():
    """HERFD pre-edges read 0 counts: zero values are data, only uncovered points are dropped."""
    from xas_analysis.model.mback import _edge, atomic_step
    from xas_analysis.pipeline import normalize_spectrum
    E = np.arange(11150.0, 11500.01, 1.0)
    mu, _ = atomic_step(77, E / 1000, _edge(77, "L3", E / 1000)[0])
    raw = 0.37 * mu                     # zero background: the pre-edge is exactly 0
    n = np.full(E.size, 4)
    n[:3] = 0                           # grid start not covered after the shift
    raw[:3] = 0.0
    res = normalize_spectrum(E, raw, {"element": "Ir", "core": "L3", "range": [11160, 11206, 11275, 11490]}, n)
    assert res is not None and abs(res.info["A_edge"] / 0.37 - 1) < 2e-3
    assert res.energy_eV[0] == E[3]


def test_fluorescence_background_options():
    """Tender fluorescence: decaying scatter tail + rising instrument factor on the step.
    The plain Victoreen fit bends its background up (c3 < 0) and misses the pre-edge; the
    fluorescence options recover the step and a zero pre-edge."""
    from xas_analysis.model.mback import atomic_step
    from xas_analysis.model.mback_xrs import mback_xrs
    E = np.r_[np.arange(2390, 2465, 5.0), np.arange(2465, 2500, 0.2), np.arange(2500, 2810, 4.0)]
    mu, _ = atomic_step(16, E / 1000, 2.472)
    x = E / 2472.0 - 1
    true_A = 2.0
    bg = 0.02 + 0.06 * np.exp(-(E - 2390) / 40.0)
    y = bg + true_A * (1 + 5.0 * x) * mu
    R = [2391, 2448, 2532, 2805]
    r = mback_xrs("S", E, y, R, "K", bg_decreasing=True, pre_tail=True, step_slope=True)
    assert abs(r.info["A_edge"] / true_A - 1) < 0.02
    assert abs(r.info["step_slope_k"][0] - 5.0) < 0.3
    pre = (E > 2400) & (E < 2445)
    assert np.max(np.abs(r.norm_xas[pre])) < 0.01
    assert np.all(np.diff(r.info["bg"]) <= 1e-12) and r.info["bg"].min() >= -1e-12
    plain = mback_xrs("S", E, y, R, "K", bg_decreasing=False)
    assert np.max(np.abs(plain.norm_xas[pre])) > 3 * np.max(np.abs(r.norm_xas[pre]))


def test_athena_norm_flat():
    from xas_analysis.model.athena_norm import athena_norm
    E = np.arange(2390, 2810, 1.0)
    y = 0.1 - 1e-4 * (E - 2390) + np.where(E >= 2472, 1.5 + 1e-3 * (E - 2472) - 1e-6 * (E - 2472) ** 2, 0)
    r = athena_norm("S", E, y, [2391, 2448, 2532, 2805], "K")
    assert abs(r.info["A_edge"] - 1.5) < 1e-6
    assert np.allclose(r.norm_xas[E >= 2480], 1.0, atol=1e-6) and np.allclose(r.norm_xas[E < 2460], 0, atol=1e-6)


def test_extra_edge_and_quadratic_step_factor():
    """S K + Mo L3/L2 (MoS2-like): extra McMaster step recovers the S jump and the Mo ratio."""
    from xas_analysis.model.mback import atomic_step
    from xas_analysis.model.mback_xrs import mback_xrs
    E = np.r_[np.arange(2390, 2465, 5.0), np.arange(2465, 2500, 0.2), np.arange(2500, 2810, 2.0)]
    muS, _ = atomic_step(16, E / 1000, 2.472)
    muMo, _ = atomic_step(42, E / 1000, 2.520)
    u = E / 2472.0 - 1
    f = 1 + 3.0 * u + 15.0 * u ** 2
    y = 0.02 + 0.06 * np.exp(-(E - 2390) / 40.0) + 1.5 * f * (muS + 0.4 * muMo)
    r = mback_xrs("S", E, y, [2391, 2448, 2532, 2805], "K", bg_decreasing=True, pre_tail=True,
                  step_slope=2, extra_edges=[("Mo", "L3")])
    assert abs(r.info["A_edge"] / 1.5 - 1) < 0.02
    assert abs(r.info["extra_edges"]["r_MoL3"] - 0.4) < 0.03
    assert r.info["post_rms"] < 1e-3
    ok = (E > 2532) & (E < 2800)
    assert np.allclose(r.norm_xas[ok], muS[ok], atol=0.01)


def test_self_absorption_thick_roundtrip():
    """Forward thick-limit model on a known spectrum, then the correction recovers it; the
    feasibility check refuses contrast above 1 + alpha/D0."""
    import pytest
    from xas_analysis.model.mback import atomic_step
    from xas_analysis.model.self_absorption import (_k_shell_photo, mixture_mass_fractions,
                                                     sa_correct_thick)
    from xas_analysis.physics.mcmaster import mcmaster
    E = np.r_[np.arange(2400, 2465, 5.0), np.arange(2465, 2500, 0.2), np.arange(2500, 2810, 2.0)]
    mu, _ = atomic_step(16, E / 1000, 2.472)
    s_true = mu * (1 + 2.0 * np.exp(-((E - 2473) / 1.0) ** 2))
    comp = mixture_mass_fractions([{"formula": "Na2S2O3", "wt": 0.2}, {"formula": "C12H22O11", "wt": 0.8}])
    D0 = comp[16] * _k_shell_photo(16, np.array([2.4721]))[0]
    mt = sum(w * mcmaster(z, E / 1000) for z, w in comp.items())
    alpha = mt - comp[16] * _k_shell_photo(16, E / 1000) + sum(w * mcmaster(z, np.array([2.308]))[0] for z, w in comp.items())
    n = D0 * s_true / (D0 * s_true + alpha)
    n = n / np.median(n[(E > 2550) & (E < 2600)])
    post = (E > 2532) & (E < 2805)
    s, info = sa_correct_thick(E, n, "S", comp, mu, post, contrast=float(n.max()))
    assert np.allclose(s[E > 2465], s_true[E > 2465], atol=0.02 * s_true.max())
    assert abs(info["residual_step_slope_k"]) < 0.1
    with pytest.raises(ValueError):
        sa_correct_thick(E, n, "S", {16: 1.0}, mu, post, contrast=5.0)


def test_post_drift_screen():
    """A scan whose signal collapses late (post-edge falls) is dropped; normal scans are kept."""
    from xas_analysis.pipeline import AlignedScan, screen_scans
    E = np.arange(11540, 11806, 1.0)
    base = 0.01 + 0.1 / (1 + np.exp(-(E - 11564) / 1.0))
    rng = np.random.default_rng(1)
    out = []
    for n in range(1, 6):
        y = base * (1 + 2e-3 * rng.standard_normal(E.size))
        if n == 5:
            y = y * np.where(E > 11700, 1 - 0.8 * (E - 11700) / 106, 1.0)
        out.append(AlignedScan(n, E, y * 1e4, np.full(E.size, 1e4), np.ones(E.size), 0.0, 0.0, True, True))
    cfg = {"post_drift": {"windows": [[11625, 11660], [11760, 11800]], "pre_eV": [11541, 11553]}}
    dropped = screen_scans(out, cfg)
    assert [d[0] for d in dropped] == [5] and "post-edge drift" in dropped[0][1]


def test_ratio_shape_screen():
    """A scan whose intensity drifts across the post-edge (tilted ratio to the other scans) is
    dropped by screening.ratio_shape; flat scans are kept."""
    from xas_analysis.pipeline import AlignedScan, screen_scans
    E = np.arange(11540, 11806, 1.0)
    base = 0.01 + 0.1 / (1 + np.exp(-(E - 11564) / 1.0))
    rng = np.random.default_rng(2)
    out = []
    for n in range(1, 7):
        y = base * (1 + 3e-3 * rng.standard_normal(E.size)) * (1 + 0.02 * (n % 2))      # small level offsets: fine
        if n == 4:
            y = y * (1 + 0.15 * np.clip((E - 11570) / 230, 0, 1))                      # +15 % drift over the post-edge
        out.append(AlignedScan(n, E, y * 1e4, np.full(E.size, 1e4), np.ones(E.size), 0.0, 0.0, True, True))
    dropped = screen_scans(out, {"ratio_shape": {"window_eV": [11570, 11800], "min_frac": 0.05}})
    assert [d[0] for d in dropped] == [4] and "ratio-shape tilt" in dropped[0][1]
