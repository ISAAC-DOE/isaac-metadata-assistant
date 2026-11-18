"""Processing protocol ``isaac.xas.v1``: the vendored xas-analysis engine + the ISAAC adapter (processing/engine_xas.py).

SYNTHETIC scans only: every spectrum is an invented logistic edge with a Gaussian white line at the tabulated Ir L3
energy, every name is SYN_*, every header says SYNTHETIC FIXTURE. Rules under test (Angel and Krish, 17 Nov 2026):
raw mu merged, normalised once; the skill DECIDES which scans are kept, by a documented rule, with reasons, shown and
overridable; an intensity drop alone never drops a scan; every scan aligned to ONE beamtime reference (a foil when
usable, else the I0 glitch); transmission samples stay on v0.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

np = pytest.importorskip("numpy", reason="XAS processing tests need the optional `processing` extra (numpy)")
pytest.importorskip("larch", reason="XAS processing tests need the optional `processing` extra (xraylarch)")
pytest.importorskip("scipy", reason="the xas-analysis engine needs scipy")
pytest.importorskip("yaml", reason="the xas-analysis engine needs pyyaml (the optional `processing` extra)")

from isaac_api.local_import.processing import engine_xas as EX  # noqa: E402

E_EDGE = 11215.0      # Ir L3, tabulated (McMaster); the synthetic edge sits there
GLITCH = 11226.6      # the synthetic I0 glitch (true energy)
GRID = np.r_[np.arange(11165, 11205, 5.0), np.arange(11205, 11240, 0.25), np.arange(11240, 11500, 4.0)]
BY = {"by": "SYN Scientist", "orcid": None}


@pytest.fixture(autouse=True)
def _engine_on(monkeypatch):
    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v1")


def scan_cols(seed, *, d=0.0, chem=0.0, scale=1.0, noise=2e-3, foil=False, glitch=True, fluo=True, trans_step=0.0,
              n_points=None, wl=3.0, bg=0.0, wl_shift=0.0):
    """One SYN scan. ``d``: the mono offset (the recorded absev reads ``d`` above the true energy, so every feature
    sits at its true energy + d); ``chem``: a true shift of the sample's own edge; ``scale``: the signal's intensity."""
    rng = np.random.default_rng(seed)
    E = GRID.copy() if n_points is None else GRID[:n_points].copy()
    t = E - d
    I0 = 1e5 * (1 - 0.0004 * (E - 11165))
    if glitch:
        I0 = I0 * (1 - 0.06 * np.exp(-((t - GLITCH) / 0.22) ** 2))
    mu = 0.05 + 1.0 / (1 + np.exp(-(t - E_EDGE - chem) / 1.2)) + wl * np.exp(-((t - 11218 - chem - wl_shift) / 1.5) ** 2)
    IF = (scale * mu + bg) * I0 * 1e-3 * (1 + noise * rng.standard_normal(E.size))
    if foil:
        muf = 0.3 + 0.8 / (1 + np.exp(-(t - E_EDGE) / 0.9))
        I1 = 0.6 * I0
        I2 = I1 * np.exp(-muf)
    else:
        I1 = I0 * np.exp(-(0.5 + trans_step / (1 + np.exp(-(t - E_EDGE) / 1.2)))) if trans_step else np.full(E.size, 3.0)
        I2 = np.full(E.size, 2.0)
    cols = {"energy": E - 2.3, "absev": E, "I0": I0, "I1": I1, "I2": I2, "sec": np.ones(E.size)}
    if fluo:
        cols["vortDT"] = IF
    return cols


SCAN_CMD = "gscan energy 11165 11205 5 11240 0.25 11500 4 0.5"
#: the #O motor names of a SPEC file whose per-scan split copies state their #P positions without names
O_LINE = "#O0   dummy0    emiss    filter        Sx        Sy        Sz        Sr"


def _spec(cols, n, hour, sz=3.0, *, command=SCAN_CMD, positional=False):
    names = list(cols)
    p0 = f"#P0 4 9175.4 10 1 2 {sz:g} 0" if positional else f"#P0 dummy0=4 emiss=9175.4 filter=10 Sx=1 Sy=2 Sz={sz:g} Sr=0"
    lines = ["#C SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value is invented.",
             f"#S {n}  {command}",
             f"#D Sat Apr 12 {hour:02d}:{n:02d}:00 2025", p0,
             "#L " + "  ".join(names)]
    for row in zip(*(cols[k] for k in names)):
        lines.append(" ".join(f"{v:.6f}" for v in row))
    return "\n".join(lines) + "\n"


def write_beamtime(root, runs, *, command=SCAN_CMD, positional=False, ext="dat"):
    """``runs``: [(stem, hour, [cols, ...]) or (stem, hour, [cols, ...], [Sz per scan])]: each run an acquisition file
    of #S blocks beside its per-scan files (a 4th item: each scan's stage Sz, its spot). ``positional``: the per-scan
    files state #P positions WITHOUT motor names, which only the acquisition file's #O line gives."""
    for stem, hour, scans, *spot in runs:
        d = root / f"{stem}_dir"
        d.mkdir(parents=True)
        blocks = []
        sz = spot[0] if spot else [3.0] * len(scans)
        for j, c in enumerate(scans, start=1):
            text = _spec(c, j, hour, sz[j - 1], command=command, positional=positional)
            (d / f"{stem}_{j:03d}.{ext}").write_text(text)
            blocks.append(text)
        head = f"#F {stem}\n#E 1\n" + (O_LINE + "\n" if positional else "") + "\n"
        (root / stem).write_text(head + "\n".join(blocks))


def imported(tmp_path, runs, *, process=True, **kw):
    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M

    root = tmp_path / "SYN_beamtime"
    write_beamtime(root, runs, **kw)
    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    M.group(out)
    if process:
        M.process(out, source=str(root))
    return out, root


def v1_results(bdir):
    from isaac_api.local_import import mutations as M

    return [r for r in M.load(bdir)["processing_results"] if r.get("protocol_id") == EX.PROTOCOL_ID]


def by_run(results, prefix):
    return next(r for r in results if any((x.get("run") or "").startswith(prefix) for x in r[EX.DECISIONS_KEY]["rows"]))


REF_D = [0.00, 0.03, -0.02, 0.01]
SMP_D = [0.12, 0.18, 0.05, -0.07, 0.21]


def _two_groups(foil=False, glitch=True):
    return [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k, d=d, foil=foil, glitch=glitch) for k, d in enumerate(REF_D)]),
            ("02_SYN_ZZ2_060mV", 11, [scan_cols(20 + k, d=d, foil=foil, glitch=glitch) for k, d in enumerate(SMP_D)])]


def _shift_errors(r, ds, ref_mean):
    rows = {x["scan_id"]: x for x in r[EX.SHIFTS_KEY]["rows"]}
    stem = next(iter(rows)).split("#")[0]
    return [1000 * (rows[f"{stem}#{k + 1}"]["shift_eV"] - (ref_mean - d)) for k, d in enumerate(ds)]


# --- the energy reference: injected shifts are recovered, on ONE beamtime reference ---------------------------------


def test_the_glitch_route_recovers_injected_per_scan_shifts(tmp_path):
    bdir, _ = imported(tmp_path, _two_groups())
    res = v1_results(bdir)
    assert len(res) == 2
    ref = by_run(res, "01_SYN_ZZ1")
    smp = by_run(res, "02_SYN_ZZ2")
    route = smp[EX.REFERENCE_KEY]["routes"][0]
    assert route["mode"] == "glitch_I0" and route["reference_name"] == "01_SYN_ZZ1_060mV"   # the earliest group
    ref_mean = float(np.mean(REF_D))
    for r, ds in ((ref, REF_D), (smp, SMP_D)):
        err = _shift_errors(r, ds, ref_mean)
        assert max(abs(e) for e in err) < 5.0, err                                  # within 5 meV
    assert "ONE beamtime reference" in smp[EX.SHIFTS_KEY]["statement"]
    cal = next(s for s in smp["steps"] if s["step"] == "calibration")
    assert cal["outcome"]["applied"] is True and cal["outcome"]["kind"] == "per_scan_alignment"


def test_the_foil_route_recovers_injected_per_scan_shifts(tmp_path):
    bdir, _ = imported(tmp_path, _two_groups(foil=True, glitch=False))
    res = v1_results(bdir)
    smp = by_run(res, "02_SYN_ZZ2")
    route = smp[EX.REFERENCE_KEY]["routes"][0]
    assert route["mode"] == "ref_foil" and route["method"] == "shape"
    ref_mean = float(np.mean(REF_D))
    for r, ds in ((by_run(res, "01_SYN_ZZ1"), REF_D), (smp, SMP_D)):
        err = _shift_errors(r, ds, ref_mean)
        assert max(abs(e) for e in err) < 5.0, err


def test_the_beamtime_pass_is_said_once_with_its_evidence(tmp_path):
    from isaac_api.local_import import mutations as M

    bdir, _ = imported(tmp_path, _two_groups())
    payload = json.loads((bdir / "processing" / "processing_results.json").read_text())
    bt = payload[EX.BEAMTIME_KEY]
    assert bt["calibration"]["mode"] == "glitch_I0" and bt["edge"]["element"] == "Ir"
    assert bt["windows"]["Ir L3"]["range"][1] < E_EDGE < bt["windows"]["Ir L3"]["range"][2]
    assert any("isaac.xas.v1" in line for line in payload["summary"]["lines"])
    assert M.load(bdir)["processing_results"]


# --- robust alignment: a minority of bad scans never degrades the others (review of 2ddb27e7, HIGH 1) ---------------


def _rows_by_scan_id(results):
    out = {}
    for r in results:
        for x in r[EX.DECISIONS_KEY]["rows"]:
            out[x["scan_id"]] = (r, x)
    return out


def _check_robust(bdir, ref_ds, smp_ds, bad):
    """Every good scan's shift within 5 meV of (median good reference anchor - its own offset); ONLY ``bad`` flagged,
    with a plain reason; the beamtime stays on the glitch route."""
    res = v1_results(bdir)
    assert len(res) == 2
    rows = _rows_by_scan_id(res)
    good_ref = [d for k, d in enumerate(ref_ds) if f"01_SYN_ZZ1_060mV#{k + 1}" not in bad]
    ref_anchor = float(np.median(good_ref))
    errs = {}
    for stem, ds in (("01_SYN_ZZ1_060mV", ref_ds), ("02_SYN_ZZ2_060mV", smp_ds)):
        for k, d in enumerate(ds):
            sid = f"{stem}#{k + 1}"
            r, row = rows[sid]
            shift = {x["scan_id"]: x for x in r[EX.SHIFTS_KEY]["rows"]}[sid]
            if sid in bad:
                assert row["decision"] == "drop", row
                codes = {y["code"] for y in row["reasons"]}
                assert codes & {"no_energy_reference", "reference_fit_failed"}, row["reasons"]
                said = " ".join(y["said"] for y in row["reasons"])
                assert "no energy reference found in this scan" in said or "reference feature fit failed" in said
                assert shift["shift_eV"] is None                                     # not aligned at all
            else:
                assert row["decision"] == "keep", (sid, row["reasons"])
                errs[sid] = 1000 * (shift["shift_eV"] - (ref_anchor - d))
    assert max(abs(e) for e in errs.values()) < 5.0, errs
    for r in res:
        assert r[EX.REFERENCE_KEY]["routes"][0]["mode"] == "glitch_I0"
    return res


@pytest.mark.parametrize("where", ["reference", "sample"])
def test_one_glitchless_scan_is_flagged_and_never_moves_the_glitch(tmp_path, where):
    ref_ds, smp_ds = REF_D, SMP_D + [0.09]
    ref = [scan_cols(10 + k, d=d) for k, d in enumerate(ref_ds)]
    smp = [scan_cols(20 + k, d=d) for k, d in enumerate(smp_ds)]
    if where == "reference":
        ref[0] = scan_cols(10, d=ref_ds[0], glitch=False)
        bad = {"01_SYN_ZZ1_060mV#1"}
    else:
        smp[0] = scan_cols(20, d=smp_ds[0], glitch=False)
        bad = {"02_SYN_ZZ2_060mV#1"}
    bdir, _ = imported(tmp_path, [("01_SYN_ZZ1_060mV", 9, ref), ("02_SYN_ZZ2_060mV", 11, smp)])
    _check_robust(bdir, ref_ds, smp_ds, bad)


def test_two_glitchless_scans_of_nine_never_flip_the_beamtime_to_no_reference(tmp_path):
    ref = [scan_cols(10 + k, d=d) for k, d in enumerate(REF_D)]
    smp = [scan_cols(20 + k, d=d) for k, d in enumerate(SMP_D)]
    ref[1] = scan_cols(11, d=REF_D[1], glitch=False)
    smp[0] = scan_cols(20, d=SMP_D[0], glitch=False)
    bdir, _ = imported(tmp_path, [("01_SYN_ZZ1_060mV", 9, ref), ("02_SYN_ZZ2_060mV", 11, smp)])
    _check_robust(bdir, REF_D, SMP_D, {"01_SYN_ZZ1_060mV#2", "02_SYN_ZZ2_060mV#1"})


@pytest.mark.parametrize("where", ["reference", "sample"])
def test_one_scan_shifted_far_is_flagged_and_the_others_keep_their_shifts(tmp_path, where):
    ref_ds, smp_ds = list(REF_D), list(SMP_D)
    if where == "reference":
        ref_ds[0], bad = 1.6, {"01_SYN_ZZ1_060mV#1"}
    else:
        smp_ds[2], bad = 1.6, {"02_SYN_ZZ2_060mV#3"}
    ref = [scan_cols(10 + k, d=d) for k, d in enumerate(ref_ds)]
    smp = [scan_cols(20 + k, d=d) for k, d in enumerate(smp_ds)]
    bdir, _ = imported(tmp_path, [("01_SYN_ZZ1_060mV", 9, ref), ("02_SYN_ZZ2_060mV", 11, smp)])
    _check_robust(bdir, ref_ds, smp_ds, bad)


# --- normalisation: once, Victoreen + McMaster -----------------------------------------------------------------------


def test_normalization_gives_the_step_of_a_synthetic_mcmaster_step():
    from xas_analysis.model.mback import atomic_step
    from xas_analysis.physics.mcmaster import element

    E = np.linspace(11160, 11500, 341)
    edge = element("Ir")["L_edge"][2]
    mu, _ = atomic_step(77, E / 1000, edge)
    raw = 0.02 + 0.05 * (E / 1000 / edge) ** -3 + 0.7 * mu
    nm = EX.normalize_once(E, raw, np.ones(E.size), {"element": "Ir", "edge": "L3", "E_edge_eV": 1000 * edge,
                                                     "basis": "SYN"}, {"windows": {}}, np)
    assert nm["A_edge"] == pytest.approx(0.7, rel=1e-6)
    assert np.allclose(nm["norm"], mu, atol=1e-6)
    assert nm["uncertainty"]["window_spread_of_A"] < 1e-6       # an exact model: no window dependence
    assert "NOT flattened" in nm["convention"] and nm["window_basis"].startswith("the group's own window")


def test_raw_mu_is_merged_and_the_average_is_normalised_once(tmp_path):
    bdir, _ = imported(tmp_path, _two_groups())
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    merge = next(s for s in r["steps"] if s["step"] == "merge")
    assert "raw IF/I0" in merge["params"]["statistic"] and merge["outcome"]["n_scans"] == 5
    nm = next(s for s in r["steps"] if s["step"] == "normalize")
    assert nm["outcome"]["model"] == "victoreen" and r[EX.NORMALIZATION_KEY]["bg_decreasing"] is True
    roles = {f["role"] for f in r["outputs"]["files"]}
    assert {"merged", "normalized", "scan_decisions", "qc", "params", "plot"} <= roles
    assert r["outputs"]["e0_eV"] == pytest.approx(E_EDGE, abs=2.0)


# --- the scan decisions ---------------------------------------------------------------------------------------------


def _rec(sid, num=1, *, ok=True, shift=0.0, scale=1.0, noise=2e-3, seed=0, edge=True):
    from xas_analysis.average import AlignedScan

    rng = np.random.default_rng(seed)
    E = GRID
    mu = (0.05 + 1.0 / (1 + np.exp(-(E - E_EDGE) / 1.2))) if edge else np.full(E.size, 0.5)
    IF = scale * mu * (1 + noise * rng.standard_normal(E.size))
    a = AlignedScan(num, E, IF, np.ones(E.size), 1.0, 0.0, shift, True, True, key=sid)
    return {"scan_id": sid, "num": num, "stem": sid.split("#")[0], "entry": {"relative_path": f"SYN/{sid}.dat"},
            "alignment": {"ok": ok, "shift_eV": shift if ok else None, "route": "glitch_I0" if ok else None,
                          "tried": [] if ok else [{"route": "glitch_I0", "reason": "fewer than 6 points"}]},
            "aligned": a}


def _decide(recs, flags=None, stability=None, notes=None, overrides=None):
    win = [E_EDGE - 10, E_EDGE + 45]
    return EX.decide_scans(recs, flags or {}, stability or {"rows": {}}, notes or {}, overrides or {}, [], GRID, win, np)


def test_each_input_of_the_rule_decides_with_its_reason():
    recs = [_rec(f"SYN_A#{k}", k, seed=k) for k in range(1, 9)]
    recs[6] = _rec("SYN_A#7", 7, ok=False)
    stab = {"rows": {"SYN_A#1": {"proposal": "exclude_proposed", "reasons": ["before_stable_window"],
                                 "said": ["before the stable window"]},
                     "SYN_A#2": {"proposal": "needs_look", "reasons": ["lowers_merge_snr"], "said": ["a weaker scan"]}},
            "stable_window": ["SYN_A_003.dat"], "evolving_metrics": ["wl_e_eV"]}
    notes = {"SYN_A#3": [{"action": "exclude", "applied": True, "strength": "stated", "reason": "beam lost",
                          "quote": "discard scan 3", "source": {"path": "SYN_log.txt"}}],
             "SYN_A#4": [{"action": "exclude", "applied": True, "strength": "inferred", "reason": "probably bad",
                          "quote": "maybe discard 4", "source": {"path": "SYN_log.txt"}}],
             "SYN_A#5": [{"action": "flag", "applied": False, "strength": "stated", "reason": "watch it",
                          "quote": "scan 5 noisy?", "source": {"path": "SYN_log.txt"}}]}
    flags = {"SYN_A#6": [{"test": "coverage", "reason": "covers 40% of the grid (aborted?)", "value": 0.4,
                          "median": None, "threshold": 0.9}],
             "SYN_A#8": [{"test": "anchor", "reason": "anchor +210 meV from file median", "value": 0.21,
                          "median": 0.0, "threshold": 0.15}]}
    t = _decide(recs, flags, stab, notes)
    row = t["by_id"]
    assert row["SYN_A#1"]["decision"] == "drop" and row["SYN_A#1"]["reasons"][0]["source"] == "stability"
    assert row["SYN_A#2"]["decision"] == "keep" and row["SYN_A#2"]["notes"]            # weaker: said, never dropped
    assert row["SYN_A#3"]["decision"] == "drop" and row["SYN_A#3"]["reasons"][0]["code"] == "logbook_exclude"
    assert row["SYN_A#4"]["decision"] == "drop" and row["SYN_A#4"]["reasons"][0]["strength"] == "inferred"
    assert row["SYN_A#5"]["decision"] == "keep" and row["SYN_A#5"]["notes"][0]["code"] == "logbook_flag"
    assert row["SYN_A#6"]["decision"] == "drop" and row["SYN_A#6"]["reasons"][0]["code"] == "coverage"
    assert row["SYN_A#7"]["decision"] == "drop" and row["SYN_A#7"]["reasons"][0]["code"] == "reference_fit_failed"
    assert row["SYN_A#7"]["reasons"][0]["said"].startswith("reference feature fit failed")
    assert row["SYN_A#8"]["decision"] == "drop" and row["SYN_A#8"]["reasons"][0]["code"] == "anchor"
    assert t["counts"] == {"scans": 8, "kept": 2, "dropped": 6, "overridden_by_scientist": 0, "merged": 2,
                           "kept_not_merged": 0}
    for x in t["rows"]:
        assert x["decided_by"] == "rule" and all(y["said"] for y in x["reasons"])
    assert "Dropped:" in t["statement"] and "set_scan_decision" in t["override_command"]


def test_an_intensity_drop_alone_never_drops_a_scan():
    """A dead-channel flag on a weak scan that still shows its edge, and an off-shape flag that is only the noise of
    fewer counts, both keep the scan (said); a channel with no edge at all, and a real shape change, drop."""
    weak = _rec("SYN_B#1", 1, scale=0.005, seed=1)
    noisy = _rec("SYN_B#2", 2, noise=0.05, seed=2)
    dead = _rec("SYN_B#3", 3, scale=0.005, seed=3, edge=False)
    shape = _rec("SYN_B#4", 4, seed=4)
    shape["aligned"].IF = (0.05 + 1.0 / (1 + np.exp(-(GRID - E_EDGE - 6) / 1.2)))
    flags = {"SYN_B#1": [{"test": "dead_channel", "reason": "dead IF channel", "value": 0.005, "median": 1.0,
                          "threshold": 0.01}],
             "SYN_B#2": [{"test": "shape", "reason": "shape rms 6e-02", "value": 0.06, "median": 0.002,
                          "threshold": 0.012}],
             "SYN_B#3": [{"test": "dead_channel", "reason": "dead IF channel", "value": 0.0025, "median": 1.0,
                          "threshold": 0.01}],
             "SYN_B#4": [{"test": "shape", "reason": "shape rms 2e-01", "value": 0.2, "median": 0.002,
                          "threshold": 0.012}]}
    row = _decide([weak, noisy, dead, shape], flags)["by_id"]
    assert row["SYN_B#1"]["decision"] == "keep" and row["SYN_B#1"]["notes"][0]["code"] == "weak_signal"
    assert row["SYN_B#2"]["decision"] == "keep" and row["SYN_B#2"]["notes"][0]["code"] == "noisier_not_off_shape"
    assert row["SYN_B#3"]["decision"] == "drop" and "no edge at all" in row["SYN_B#3"]["reasons"][0]["said"]
    assert row["SYN_B#4"]["decision"] == "drop" and row["SYN_B#4"]["reasons"][0]["code"] == "shape"


def test_end_to_end_a_weaker_and_a_noisier_scan_are_kept(tmp_path):
    scans = [scan_cols(30 + k) for k in range(5)]
    scans.append(scan_cols(39, scale=0.4))                 # 60 % intensity loss, same shape
    scans.append(scan_cols(40, noise=6e-3))                # three times the noise
    runs = [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k) for k in range(4)]), ("02_SYN_ZZ2_060mV", 11, scans)]
    bdir, _ = imported(tmp_path, runs)
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert rows[6]["decision"] == "keep" and rows[7]["decision"] == "keep", (rows[6], rows[7])
    assert r[EX.DECISIONS_KEY]["counts"]["dropped"] == 0


def test_a_sample_still_changing_is_dropped_before_its_stable_window(tmp_path):
    scans = [scan_cols(50 + k, chem=0.8 if k < 2 else 0.0) for k in range(9)]
    runs = [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k) for k in range(4)]), ("02_SYN_ZZ2_060mV", 11, scans)]
    bdir, _ = imported(tmp_path, runs)
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    for k in (1, 2):
        assert rows[k]["decision"] == "drop" and "before_stable_window" in {y["code"] for y in rows[k]["reasons"]}
    assert all(rows[k]["decision"] == "keep" for k in range(3, 10))


# --- the logbook notes (the bundle's scan_notes section; a parallel branch adds its reader) ---------------------------


def _notes_module(monkeypatch, by_stem):
    from isaac_api.local_import import mutations as M

    mod = types.ModuleType("isaac_api.local_import.scan_notes")

    def scan_notes_for_run(bundle, run_id):
        stem = next((r["stem"] for r in bundle["runs"] if r["run_id"] == run_id), None)
        return by_stem.get(stem, [])

    mod.scan_notes_for_run = scan_notes_for_run
    monkeypatch.setitem(sys.modules, "isaac_api.local_import.scan_notes", mod)
    return M


def test_logbook_notes_are_applied_by_scan_number(tmp_path, monkeypatch):
    runs = [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k) for k in range(4)]),
            ("02_SYN_ZZ2_060mV", 11, [scan_cols(60 + k) for k in range(8)])]
    bdir, root = imported(tmp_path, runs, process=False)
    note = {"source": {"path": "SYN_logbook.txt", "locator": "line 1"}, "quote": "SYN quote"}
    M = _notes_module(monkeypatch, {"02_SYN_ZZ2_060mV": [
        {**note, "action": "start_from", "scans": [3], "reason": "still evolving", "strength": "stated"},
        {**note, "action": "exclude", "scans": [8], "reason": "went to OCV", "strength": "inferred"},
        {**note, "action": "flag", "scans": [], "reason": "potentiostat noise", "strength": "stated"}]})
    M.process(bdir, source=str(root))
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert [k for k, x in sorted(rows.items()) if x["decision"] == "drop"] == [1, 2, 8]
    assert rows[1]["reasons"][0]["code"] == "logbook_start_from"
    assert rows[8]["reasons"][0]["strength"] == "inferred"
    assert "logbook_inferred_note_applied" in r["qc"]["reasons"]
    assert len(r[EX.LOGBOOK_KEY]["notes"]) == 3 and r[EX.LOGBOOK_KEY]["available"] is True


def test_without_a_scan_notes_reader_no_note_is_applied_and_that_is_said(tmp_path):
    bdir, _ = imported(tmp_path, _two_groups())
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    if "isaac_api.local_import.scan_notes" in sys.modules and not hasattr(sys.modules["isaac_api.local_import.scan_notes"], "__file__"):
        pytest.skip("a stub reader is installed")
    lb = r[EX.LOGBOOK_KEY]
    try:
        import isaac_api.local_import.scan_notes  # noqa: F401
    except ImportError:
        assert lb["available"] is False and "no logbook scan-notes reader" in lb["statement"]


# --- the scientist's override, through decide ----------------------------------------------------------------------


def test_the_override_round_trip(tmp_path):
    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M

    bdir, root = imported(tmp_path, _two_groups())
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    gid, old_id = r["group_id"], r["result_id"]
    sid = next(x["scan_id"] for x in r[EX.DECISIONS_KEY]["rows"] if x["scan"] == 2)
    with pytest.raises(M.MutationRefused, match="has no scan"):
        M.decide(bdir, target_ids=[gid], decision="set_scan_decision", value={"decision": "drop", "scans": ["SYN_nope#9"]}, **BY)
    with pytest.raises(M.MutationRefused, match="keep or --value drop"):
        M.decide(bdir, target_ids=[gid], decision="set_scan_decision", value={"decision": "maybe", "scans": [sid]}, **BY)
    assert cli.main(["bundle", "decide", str(bdir), "--target", gid, "--decision", "set_scan_decision", "--value", "drop",
                     "--scans", sid, "--note", "SYN: bubble on the cell", "--by", "SYN Scientist"]) == 0
    d = M.load(bdir)["scientist_decisions"][-1]
    assert d["decision"] == "set_scan_decision" and d["value"] == {"decision": "drop", "scans": [sid]}
    assert next(g for g in M.load(bdir)["record_groups"] if g["group_id"] == gid)["status"] == "proposed"  # no status move
    M.process(bdir, source=str(root), group_ids=[gid])
    new = [x for x in v1_results(bdir) if x["group_id"] == gid][-1]
    assert new["result_id"] != old_id                                       # a changed decision: a new result
    row = next(x for x in new[EX.DECISIONS_KEY]["rows"] if x["scan_id"] == sid)
    assert row["decision"] == "drop" and row["decided_by"] == "scientist" and row["rule_decision"] == "keep"
    assert row["override"]["decided_by"] == "SYN Scientist"
    assert new[EX.DECISIONS_KEY]["counts"]["overridden_by_scientist"] == 1
    assert next(s for s in new["steps"] if s["step"] == "merge")["outcome"]["n_scans"] == 4
    # and back: keep it again
    M.decide(bdir, target_ids=[gid], decision="set_scan_decision", value={"decision": "keep", "scans": [sid]}, **BY)
    M.process(bdir, source=str(root), group_ids=[gid])
    again = [x for x in v1_results(bdir) if x["group_id"] == gid][-1]
    assert next(s for s in again["steps"] if s["step"] == "merge")["outcome"]["n_scans"] == 5
    assert again["result_id"] != new["result_id"]


def test_the_cli_refuses_scans_without_the_decision(tmp_path, capsys):
    from isaac_api.local_import import cli

    bdir, _ = imported(tmp_path, _two_groups())
    gid = by_run(v1_results(bdir), "02_SYN_ZZ2")["group_id"]
    assert cli.main(["bundle", "decide", str(bdir), "--target", gid, "--decision", "confirm", "--scans", "x#1",
                     "--by", "SYN Scientist"]) != 0
    got = capsys.readouterr()
    assert "--scans goes with" in got.out + got.err


# --- several files in one group --------------------------------------------------------------------------------------


def test_a_group_pooling_two_runs_keeps_every_scan_apart(tmp_path):
    from isaac_api.local_import import mutations as M

    ds_a, ds_b = [0.10, 0.12, 0.08], [-0.05, -0.03, -0.06]
    runs = [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k, d=d) for k, d in enumerate(REF_D)]),
            ("02_SYN_ZZ2_850mV", 11, [scan_cols(70 + k, d=d) for k, d in enumerate(ds_a)]),
            ("03_SYN_ZZ2_850mV_again", 12, [scan_cols(80 + k, d=d) for k, d in enumerate(ds_b)])]
    bdir, root = imported(tmp_path, runs, process=False)
    # the scientist says the leading number is a run counter: the two runs (a repeat, `again`) are then ONE group
    M.decide(bdir, target_ids=["experiment"], decision="set_counter_positions", value=None, positions=[1], **BY)
    M.group(bdir, regroup=True)
    assert any(len(g["member_run_keys"]) == 2 for g in M.load(bdir)["record_groups"] if g["status"] == "proposed")
    M.process(bdir, source=str(root))
    r = next(x for x in v1_results(bdir) if len({y["run"] for y in x[EX.DECISIONS_KEY]["rows"]}) == 2)
    ids = [x["scan_id"] for x in r[EX.DECISIONS_KEY]["rows"]]
    assert len(ids) == len(set(ids)) == 6                                    # scan numbers repeat, ids do not
    assert {x["scan"] for x in r[EX.DECISIONS_KEY]["rows"]} == {1, 2, 3}
    ref_mean = float(np.mean(REF_D))
    rows = {x["scan_id"]: x for x in r[EX.SHIFTS_KEY]["rows"]}
    for stem, ds in (("02_SYN_ZZ2_850mV", ds_a), ("03_SYN_ZZ2_850mV_again", ds_b)):
        for k, d in enumerate(ds):
            assert abs(1000 * (rows[f"{stem}#{k + 1}"]["shift_eV"] - (ref_mean - d))) < 5.0
    assert next(s for s in r["steps"] if s["step"] == "merge")["outcome"]["n_scans"] == 6


# --- what the engine does not cover stays on v0 ----------------------------------------------------------------------


def test_a_transmission_sample_falls_back_to_v0(tmp_path):
    runs = _two_groups() + [
        ("03_SYN_ZZ3_pellet_transmission", 13, [scan_cols(90 + k, trans_step=0.07) for k in range(3)]),
        ("04_SYN_ZZ4_060mV", 14, [scan_cols(95 + k, fluo=False, trans_step=0.6) for k in range(3)])]
    bdir, _ = imported(tmp_path, runs)
    from isaac_api.local_import import mutations as M

    res = [r for r in M.load(bdir)["processing_results"] if r["source"] == "isaac_protocol"]
    by = {}
    for r in res:
        stem = (r.get("inputs") or [{}])[0].get("relative_path", "").split("/")[0]
        by[stem[:2]] = r
    assert by["01"]["protocol_id"] == by["02"]["protocol_id"] == "isaac.xas.v1"
    for k in ("03", "04"):
        assert by[k]["protocol_id"] == "isaac.xas.v0", k
        assert "transmission" in by[k][EX.ENGINE_KEY]["reason"] and "NOT SUPPORTED" in by[k][EX.ENGINE_KEY]["reason"]


def test_the_v0_pin_keeps_every_group_on_v0(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v0")
    bdir, _ = imported(tmp_path, _two_groups())
    from isaac_api.local_import import mutations as M

    res = [r for r in M.load(bdir)["processing_results"] if r["source"] == "isaac_protocol"]
    assert {r["protocol_id"] for r in res} == {"isaac.xas.v0"} and not any(EX.ENGINE_KEY in r for r in res)


# --- what the scientist is shown -------------------------------------------------------------------------------------


def test_show_and_list_say_the_reference_shifts_decisions_and_normalisation(tmp_path, capsys):
    from isaac_api.local_import import cli

    bdir, _ = imported(tmp_path, _two_groups())
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    capsys.readouterr()
    assert cli.main(["bundle", "show", str(bdir), "processing-result", r["result_id"]]) == 0
    view = json.loads(capsys.readouterr().out)
    for key in ("engine", "energy_reference", "scan_shifts", "scan_decisions", "normalization"):
        assert key in view, key
    assert "I0 glitch" in view["energy_reference"]["statement"]
    assert view["scan_decisions"]["counts"]["scans"] == 5
    assert all("KEEP" in x or "DROP" in x for x in view["scan_decisions"]["rows"])
    assert "McMaster" in view["normalization"]["convention"]
    assert cli.main(["bundle", "list", str(bdir), "processing-results", "--limit", "20"]) == 0
    rows = json.loads(capsys.readouterr().out)["items"]
    row = next(x for x in rows if x["result_id"] == r["result_id"])
    assert row["protocol"] == "isaac.xas.v1" and "scans kept" in row["scan_decisions"]


def test_an_approved_v1_result_composes_the_record_series(tmp_path):
    """The existing approval gate: once a scientist approves the curve, the record takes ITS normalised curve, its
    steps and an E0 attributed to isaac.xas.v1."""
    from isaac_api.local_import import mutations as M
    from isaac_api.local_import import records as R

    bdir, _ = imported(tmp_path, _two_groups())
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    M.decide(bdir, target_ids=[r["group_id"]], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=[r["result_id"]], decision="approve", value=None, qc_status="valid", **BY)
    R.build_records(bdir)
    comp = json.loads((bdir / "drafts" / f"{r['group_id']}.composition.json").read_text())["processing"]
    assert comp["result"] == r["result_id"] and comp["series"].endswith("normalized.csv")
    assert comp["processing_steps"] == ["calibration", "spectrum_merging", "normalization"]
    draft = json.loads((bdir / "drafts" / f"{r['group_id']}.draft.json").read_text())
    assert draft["descriptors_outputs"][0]["generated_by"]["agent"] == "isaac.xas.v1"
    assert len(draft["series"][0]["independent_variables"][0]["values"]) == r["outputs"]["points"]


# --- no reference at all: loud, and a bulk approval refuses it ------------------------------------------------------


def test_no_reference_at_all_is_loud_and_blocks_a_bulk_approval(tmp_path, capsys):
    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M

    bdir, _ = imported(tmp_path, _two_groups(glitch=False))
    res = v1_results(bdir)
    assert len(res) == 2
    for r in res:
        assert r[EX.REFERENCE_KEY]["routes"][0]["mode"] == "none"
        assert EX.NO_REFERENCE_FLAG in r["review_flags"] and EX.NO_REFERENCE_FLAG in r["qc"]["reasons"]
        assert r[EX.REFERENCE_KEY]["statement"].startswith("NO ENERGY REFERENCE")
        assert M.bulk_approve_problem(r) and "no energy reference" in M.bulk_approve_problem(r)
    for r in res:
        M.decide(bdir, target_ids=[r["group_id"]], decision="confirm", value=None, **BY)
    with pytest.raises(M.MutationRefused, match="no energy reference"):
        M.decide(bdir, target_ids=[r["result_id"] for r in res], decision="approve", value=None, qc_status="valid", **BY)
    capsys.readouterr()
    assert cli.main(["bundle", "show", str(bdir), "processing-result", res[0]["result_id"]]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["warning"].startswith("NO ENERGY REFERENCE")


# --- a keep override on a scan with no energy reference (review MEDIUM 3) -------------------------------------------


def test_a_keep_override_on_an_unaligned_scan_is_said_and_never_merged():
    recs = [_rec(f"SYN_C#{k}", k, seed=k) for k in range(1, 4)]
    recs[2] = _rec("SYN_C#3", 3, ok=False)
    recs[2]["alignment"].update(code=EX.NO_REFERENCE[0])
    ov = {"SYN_C#3": {"decision": "keep", "decision_id": "dec-SYN1", "decided_by": "SYN Scientist", "note": None,
                      "decided_utc": "2026-11-17T00:00:00Z"}}
    t = _decide(recs, overrides=ov)
    row = t["by_id"]["SYN_C#3"]
    assert row["decision"] == "keep" and row["decided_by"] == "scientist" and row["merged"] is False
    assert row["cannot_merge"] == "kept by the scientist but cannot be merged: no energy reference found in this scan"
    assert t["counts"]["kept"] == 3 and t["counts"]["merged"] == 2 and t["counts"]["kept_not_merged"] == 1
    assert "NOT in the merge" in t["statement"]
    view = EX.show_blocks({EX.DECISIONS_KEY: {k: v for k, v in t.items() if k != "by_id"}})
    assert any("cannot be merged" in line for line in view["scan_decisions"]["rows"])


def test_end_to_end_a_kept_glitchless_scan_stays_out_of_the_merge(tmp_path):
    from isaac_api.local_import import mutations as M

    smp = [scan_cols(20 + k, d=d) for k, d in enumerate(SMP_D)]
    smp[0] = scan_cols(20, d=SMP_D[0], glitch=False)
    runs = [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k, d=d) for k, d in enumerate(REF_D)]), ("02_SYN_ZZ2_060mV", 11, smp)]
    bdir, root = imported(tmp_path, runs)
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    sid = "02_SYN_ZZ2_060mV#1"
    M.decide(bdir, target_ids=[r["group_id"]], decision="set_scan_decision", value={"decision": "keep", "scans": [sid]}, **BY)
    M.process(bdir, source=str(root), group_ids=[r["group_id"]])
    new = [x for x in v1_results(bdir) if x["group_id"] == r["group_id"]][-1]
    row = next(x for x in new[EX.DECISIONS_KEY]["rows"] if x["scan_id"] == sid)
    assert row["decision"] == "keep" and row["merged"] is False and "cannot be merged" in row["cannot_merge"]
    assert next(s for s in new["steps"] if s["step"] == "merge")["outcome"]["n_scans"] == 4
    assert "kept_scan_not_merged" in new["qc"]["reasons"]
    assert new[EX.DECISIONS_KEY]["counts"]["kept_not_merged"] == 1
    shift = next(x for x in new[EX.SHIFTS_KEY]["rows"] if x["scan_id"] == sid)
    assert shift["shift_eV"] is None


# --- an override that names no current scan (review MEDIUM 4) --------------------------------------------------------


def test_a_stale_override_is_reported_in_the_result_and_in_show(tmp_path, capsys):
    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M

    bdir, root = imported(tmp_path, _two_groups())
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    sid = next(x["scan_id"] for x in r[EX.DECISIONS_KEY]["rows"] if x["scan"] == 2)
    M.decide(bdir, target_ids=[r["group_id"]], decision="set_scan_decision", value={"decision": "drop", "scans": [sid]}, **BY)
    # what a regroup or split leaves behind: the stored decision names a scan the group no longer has
    data = json.loads((bdir / "bundle.json").read_text())
    data["scientist_decisions"][-1]["value"]["scans"] = ["02_SYN_GONE_060mV#2"]
    (bdir / "bundle.json").write_text(json.dumps(data))
    M.process(bdir, source=str(root), group_ids=[r["group_id"]])
    new = [x for x in v1_results(bdir) if x["group_id"] == r["group_id"]][-1]
    [stale] = new[EX.DECISIONS_KEY]["overrides_not_applied"]
    assert stale["scan"] == "02_SYN_GONE_060mV#2" and stale["said"].startswith("override not applied: ")
    assert "override_not_applied" in new["qc"]["reasons"]
    assert new[EX.DECISIONS_KEY]["counts"]["overridden_by_scientist"] == 0
    capsys.readouterr()
    assert cli.main(["bundle", "show", str(bdir), "processing-result", new["result_id"]]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["scan_decisions"]["overrides_not_applied"][0].startswith("override not applied: ")


# --- the measurement-mode check is written (review MEDIUM 5) ---------------------------------------------------------


def test_the_measurement_mode_is_written_and_an_unknown_mode_is_said(tmp_path, monkeypatch):
    bdir, _ = imported(tmp_path / "a", _two_groups())
    fl = by_run(v1_results(bdir), "02_SYN_ZZ2")
    assert fl["measurement_mode"]["mode"] == "fluorescence" and fl["measurement_mode"]["fluorescence_contrast"] > 0.2
    assert fl["measurement_mode"]["statement"].startswith("Measured in fluorescence")
    assert "measurement_mode_unknown" not in fl["review_flags"]
    # a reading neither way (the check's own "unknown"): v1 runs anyway, and says so
    real = EX._transmission_check

    def unclear(gread, E_edge):
        got = real(gread, E_edge)
        return {**got, "mode": "unknown", "basis": "neither reading is clear", "fluorescence_contrast": 0.1}

    monkeypatch.setattr(EX, "_transmission_check", unclear)
    bdir, _ = imported(tmp_path / "b", _two_groups())
    unk = by_run(v1_results(bdir), "02_SYN_ZZ2")
    assert unk["protocol_id"] == EX.PROTOCOL_ID and unk["measurement_mode"]["mode"] == "unknown"
    assert "UNKNOWN" in unk["measurement_mode"]["statement"] and "anyway" in unk["measurement_mode"]["statement"]
    assert "measurement_mode_unknown" in unk["review_flags"] and "measurement_mode_unknown" in unk["qc"]["reasons"]
    assert EX.show_blocks(unk)["measurement_mode"] == unk["measurement_mode"]["statement"]


# --- the run id follows the override's content (review LOW 7) --------------------------------------------------------


def test_restating_the_same_override_keeps_the_run_id(tmp_path):
    from isaac_api.local_import import mutations as M

    bdir, root = imported(tmp_path, _two_groups())
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    gid = r["group_id"]
    sid = next(x["scan_id"] for x in r[EX.DECISIONS_KEY]["rows"] if x["scan"] == 2)
    M.decide(bdir, target_ids=[gid], decision="set_scan_decision", value={"decision": "drop", "scans": [sid]}, **BY)
    M.process(bdir, source=str(root), group_ids=[gid])
    first = [x for x in v1_results(bdir) if x["group_id"] == gid][-1]
    # the same override stated again (another decision id, another time, another note)
    data = json.loads((bdir / "bundle.json").read_text())
    d = dict(data["scientist_decisions"][-1])
    d.update(decision_id="d-09999", decided_utc="2026-11-18T09:00:00Z", note="SYN: said again")
    data["scientist_decisions"].append(d)
    (bdir / "bundle.json").write_text(json.dumps(data))
    M.process(bdir, source=str(root), group_ids=[gid])
    again = [x for x in v1_results(bdir) if x["group_id"] == gid][-1]
    ov1 = next(x for x in first[EX.DECISIONS_KEY]["rows"] if x["scan_id"] == sid)["override"]
    ov2 = next(x for x in again[EX.DECISIONS_KEY]["rows"] if x["scan_id"] == sid)["override"]
    assert ov1["decision_id"] != ov2["decision_id"]                      # a new decision...
    assert again["run_id"] == first["run_id"] and again["result_id"] == first["result_id"]   # ...the same content


# --- the default path keeps what the v0 suites protect (review MEDIUM 6) ---------------------------------------------


def test_v1_process_group_reuses_the_beamtime_and_leaves_other_groups_alone(tmp_path):
    from isaac_api.local_import import mutations as M

    bdir, root = imported(tmp_path, _two_groups())
    before = {r["group_id"]: r for r in v1_results(bdir)}
    smp = by_run(list(before.values()), "02_SYN_ZZ2")
    M.process(bdir, source=str(root), group_ids=[smp["group_id"]])
    payload = json.loads((bdir / "processing" / "processing_results.json").read_text())
    assert payload[EX.BEAMTIME_KEY]["reused"] is True
    after = {r["group_id"]: r for r in v1_results(bdir)}
    assert set(after) == set(before)
    assert after[smp["group_id"]]["run_id"] == smp["run_id"]           # the same inputs, the same reference: same run
    other = next(g for g in before if g != smp["group_id"])
    assert after[other]["result_id"] == before[other]["result_id"]
    old = {x["scan_id"]: x["shift_eV"] for x in smp[EX.SHIFTS_KEY]["rows"]}
    new = {x["scan_id"]: x["shift_eV"] for x in after[smp["group_id"]][EX.SHIFTS_KEY]["rows"]}
    assert new == pytest.approx(old, abs=1e-9)


def test_v1_compares_the_scientists_quick_merge(tmp_path):
    from isaac_api.local_import.processing import quick_merge as QM

    runs = _two_groups()
    root = tmp_path / "SYN_beamtime"
    write_beamtime(root, runs)
    cols = [scan_cols(20 + k, d=d) for k, d in enumerate(SMP_D)]
    E = cols[0]["absev"]
    quick = np.mean([c["vortDT"] / c["I0"] for c in cols], axis=0)
    (root / "MERGE").mkdir()
    (root / "MERGE" / "02_SYN_ZZ2.txt").write_text("".join(f"{e:.4f}  {v:.10e}\n" for e, v in zip(E, quick)))
    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M

    out = tmp_path / "out"
    assert cli.main(["import", str(root), "--out", str(out)]) == 0
    M.group(out)
    M.process(out, source=str(root))
    r = by_run(v1_results(out), "02_SYN_ZZ2")
    [c] = r[QM.RESULT_KEY]
    assert c["role"] == "rough_reference" and c["preferred_for_record"] is False
    assert c["verdict"] in ("agree", "differs") and c["metrics"]["rms_norm"] is not None
    raw = c.get("raw_comparison") or {}
    if raw:
        assert raw["median_ratio_to_isaac_merged_mu"] == pytest.approx(1.0, abs=0.05)


def test_a_failed_engine_pass_keeps_every_group_on_v0_and_says_why(tmp_path, monkeypatch, capsys):
    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M

    def boom(*a, **k):
        raise RuntimeError("SYN engine failure")

    monkeypatch.setattr(EX, "_prepare", boom)
    bdir, _ = imported(tmp_path, _two_groups())
    res = [r for r in M.load(bdir)["processing_results"] if r["source"] == "isaac_protocol"]
    assert res and {r["protocol_id"] for r in res} == {"isaac.xas.v0"}
    for r in res:
        assert "the engine's beamtime pass failed (RuntimeError: SYN engine failure)" in r[EX.ENGINE_KEY]["reason"]
    payload = json.loads((bdir / "processing" / "processing_results.json").read_text())
    assert payload[EX.BEAMTIME_KEY]["error"].startswith("RuntimeError")
    capsys.readouterr()
    assert cli.main(["bundle", "show", str(bdir), "processing-result", res[0]["result_id"]]) == 0
    assert "SYN engine failure" in json.loads(capsys.readouterr().out)["engine"]["reason"]


def test_without_the_processing_extra_the_default_path_says_unavailable(tmp_path, monkeypatch):
    from isaac_api.local_import.processing.run import STATUS_FILE, process_bundle

    monkeypatch.setitem(sys.modules, "larch", None)
    bundle = {"bundle_id": "syn", "source_root": {"label": "SYN"}, "runs": [], "candidates": [], "sources": [], "unread_files": []}
    out = process_bundle(tmp_path, bundle=bundle, created_utc="2026-11-17T00:00:00Z")
    assert out["status"] == "processing_unavailable" and out["processing_results"] == []
    assert json.loads((tmp_path / "processing" / STATUS_FILE).read_text())["status"] == "processing_unavailable"


# --- spots: a spot difference is not an evolution (isaac.xas.spot_decision.v1) ---------------------------------------


def _spot_run(spot_of_scan, cols):
    return [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k, d=d) for k, d in enumerate(REF_D)]),
            ("02_SYN_ZZ2_060mV", 11, cols, spot_of_scan)]


def test_three_spots_one_off_shape_the_odd_spot_is_dropped_with_a_spot_reason(tmp_path, capsys):
    from isaac_api.local_import import cli

    # the odd spot is the MIDDLE one in time: not the first scans, so a spot difference alone
    sz = [-7.45] * 3 + [-7.15] * 3 + [-6.0] * 3
    cols = [scan_cols(40 + k, wl=2.2 if 3 <= k < 6 else 3.0) for k in range(9)]
    bdir, _ = imported(tmp_path, _spot_run(sz, cols))
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    for k in (4, 5, 6):
        codes = [y["code"] for y in rows[k]["reasons"]]
        assert rows[k]["decision"] == "drop" and codes == ["spot_differs"], (k, rows[k]["reasons"])
        said = rows[k]["reasons"][0]["said"]
        assert said.startswith("spot Sz -7.15 (scans 4, 5, 6) differs from the other 2 spots (scans 1, 2, 3, 7, 8, 9)")
        assert "white-line height -2" in said and "normalised shape differs" in said and "still changing" not in said
    assert all(rows[k]["decision"] == "keep" for k in (1, 2, 3, 7, 8, 9))
    sp = r["spots"]
    assert sp["outcome"] == "differing_spot_dropped" and len(sp["spots"]) == 3
    assert EX.SPOTS_DISAGREE_FLAG not in r["review_flags"]
    capsys.readouterr()
    assert cli.main(["bundle", "show", str(bdir), "processing-result", r["result_id"]]) == 0
    view = json.loads(capsys.readouterr().out)
    assert len(view["spots"]["rows"]) == 3 and view["spots"]["rows"][1].startswith("spot Sz -7.15 (spot 2): 3 scans, 0 kept")


def test_the_first_scans_at_another_spot_say_both_causes(tmp_path):
    """Spot and time order confounded: the first scans of the run sit at another spot AND evolve."""
    sz = [-6.7, -6.7, -5.5, -5.5] + [-7.15] * 3 + [-7.45] * 3 + [-6.0] * 3
    cols = [scan_cols(60 + k, chem=0.8 if k < 4 else 0.0) for k in range(13)]
    bdir, _ = imported(tmp_path, _spot_run(sz, cols))
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    for k in (1, 2, 3, 4):
        assert rows[k]["decision"] == "drop" and [y["code"] for y in rows[k]["reasons"]] == ["early_and_spot_differs"], \
            (k, rows[k]["reasons"])
    said = rows[1]["reasons"][0]["said"]
    assert said.startswith("scans 1, 2, 3, 4 differ from the rest (scans 5, 6, 7, 8, 9, 10, 11, 12, 13) in shape "
                           "(edge position +0.")
    assert "they are the first scans" in said
    assert "AND at other spots (Sz -6.7, Sz -5.5)" in said and "either the sample was still changing or the spot differs" in said
    assert all(rows[k]["decision"] == "keep" for k in range(5, 14))
    assert r["spots"]["outcome"] == "early_and_spot_differs"


def test_two_spots_split_evenly_every_spot_is_kept_flagged_and_bulk_approval_refused(tmp_path):
    from isaac_api.local_import import mutations as M

    # an even split: no majority, so neither spot (nor the time order) decides; the note says both causes
    sz = [-7.15] * 3 + [-7.45] * 3
    cols = [scan_cols(40 + k, wl=2.2 if k < 3 else 3.0) for k in range(6)]
    bdir, _ = imported(tmp_path, _spot_run(sz, cols))
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert all(rows[k]["decision"] == "keep" for k in range(1, 7)), {k: x["reasons"] for k, x in rows.items()}
    note = next(n for n in rows[1]["notes"] if n["code"] == "spot_differs")
    assert "also the first scans of the run" in note["said"] and "no majority" in note["said"]
    assert r["spots"]["outcome"] == EX.SPOTS_DISAGREE_FLAG and r["spots"]["statement"].startswith("SPOTS DISAGREE")
    assert EX.SPOTS_DISAGREE_FLAG in r["review_flags"] and EX.SPOTS_DISAGREE_FLAG in r["qc"]["reasons"]
    assert "spots that disagree" in M.bulk_approve_problem(r)
    assert next(s for s in r["steps"] if s["step"] == "merge")["outcome"]["n_scans"] == 6


def test_a_trend_within_one_spot_is_still_changing(tmp_path):
    sz = [-7.15] * 5 + [-7.45] * 4
    cols = [scan_cols(50 + k, chem=0.8 if k < 2 else 0.0) for k in range(9)]
    bdir, _ = imported(tmp_path, _spot_run(sz, cols))
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    for k in (1, 2):
        assert rows[k]["decision"] == "drop" and "before_stable_window" in {y["code"] for y in rows[k]["reasons"]}
        assert "still changing" in rows[k]["reasons"][0]["said"]
    assert all(rows[k]["decision"] == "keep" for k in range(3, 10))
    assert r["spots"]["outcome"] == "evolution_within_a_spot"


# --- rule 3 at the spot level: a weaker spot with the same shape is KEPT (review of eec37461) -----------------------


@pytest.mark.parametrize("where", ["middle", "first"])
def test_a_weaker_spot_with_the_same_shape_is_kept_in_any_position(tmp_path, where):
    """The reviewer's probe: 9 scans on 3 spots, one spot's edge step 60 % lower, the SAME shape, a constant
    fluorescence background. Never dropped, whether it is the middle spot or holds the first scans."""
    weak = range(3, 6) if where == "middle" else range(0, 3)
    sz = ([-7.45] * 3 + [-7.15] * 3 if where == "middle" else [-7.15] * 3 + [-7.45] * 3) + [-6.0] * 3
    cols = [scan_cols(70 + k, scale=0.4 if k in weak else 1.0, bg=0.5) for k in range(9)]
    bdir, _ = imported(tmp_path, _spot_run(sz, cols))
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert all(x["decision"] == "keep" for x in rows.values()), {k: x["reasons"] for k, x in rows.items()}
    for k in weak:
        notes = [n for n in rows[k + 1]["notes"] if n.get("source") == "spots"]
        assert notes and notes[0]["said"].startswith("weaker signal at this spot (spot Sz -7.15: edge step -6"), notes
        assert notes[0]["said"].endswith("same shape: kept")
    assert r["spots"]["outcome"] in ("consistent", "intensity_only_kept")
    assert next(s for s in r["steps"] if s["step"] == "merge")["outcome"]["n_scans"] == 9


def test_a_nan_stage_position_is_spot_not_read_never_its_own_spot(tmp_path):
    from isaac_api.local_import.processing import run as R

    got = R._spot_labels([(["#P0 Sx=1 Sy=2 Sz=nan Sr=0"], ()), (["#P0 Sx=1 Sy=2 Sz=3 Sr=0"], ()),
                          (["#P0 Sx=1 Sy=2 Sz=abc Sr=0"], ())])
    assert got[0] == (None, "its #P lines give no usable stage position (Sz=nan)") and got[1][0]["label"] == "spot 1"
    assert got[2][0] is None and "Sz=abc" in got[2][1]
    sz = [-7.15] * 4 + [float("nan")] + [-7.45] * 4
    bdir, _ = imported(tmp_path, _spot_run(sz, [scan_cols(80 + k) for k in range(9)]))
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    assert [x["spot"] for x in r["spots"]["spots"]] == ["spot 1", "spot 2"]
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert "spot" not in rows[5] and rows[5]["decision"] == "keep"


@pytest.mark.parametrize("noisy", [False, True])
def test_a_white_line_energy_shift_in_the_first_scans_at_another_spot_is_dropped(tmp_path, noisy):
    """A 0.5 eV white-line ENERGY shift (same intensity) in the first scans, at another spot: a normalised-shape
    change, dropped and named, even for a noisier scan whose residual sits within twice its own noise."""
    sz = [-6.7] * 3 + [-7.15] * 3 + [-7.45] * 3 + [-6.0] * 3
    cols = [scan_cols(90 + k, wl_shift=0.5 if k < 3 else 0.0, noise=(6e-3 if noisy and k == 2 else 2e-3))
            for k in range(12)]
    bdir, _ = imported(tmp_path, _spot_run(sz, cols))
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    for k in (1, 2, 3):
        codes = {y["code"] for y in rows[k]["reasons"]}
        assert rows[k]["decision"] == "drop" and codes & {"early_and_spot_differs", "before_stable_window"}, \
            (k, rows[k]["reasons"], rows[k]["notes"])
        assert any("white-line energy +0." in y["said"] for y in rows[k]["reasons"]), rows[k]["reasons"]
    assert all(rows[k]["decision"] == "keep" for k in range(4, 13))


def test_the_noise_guard_never_keeps_a_scan_whose_white_line_moved():
    """decide_scans: an off-shape flag within twice the scan's noise is "noisier" ONLY when no normalised-shape
    metric moved; a white-line energy beyond the stability rule's threshold keeps the drop."""
    recs = [_rec(f"SYN_D#{k}", k, seed=k) for k in range(1, 7)]
    recs[5] = _rec("SYN_D#6", 6, noise=0.05, seed=6)
    metrics = {f"SYN_D#{k}": {"metrics": {"wl_e_eV": 11218.0 + 0.01 * k, "sd_wl_e_eV": 0.02, "wl_h": 2.0,
                                          "sd_wl_h": 0.01, "delta_eV": 0.0, "sd_delta_eV": 0.02}, "reasons": []}
               for k in range(1, 7)}
    metrics["SYN_D#6"]["metrics"]["wl_e_eV"] = 11218.5
    flags = {"SYN_D#6": [{"test": "shape", "reason": "shape rms 6e-02", "value": 0.06, "median": 0.002,
                          "threshold": 0.012}]}
    row = _decide(recs, flags, {"rows": metrics})["by_id"]["SYN_D#6"]
    assert row["decision"] == "drop" and row["reasons"][0]["code"] == "shape"
    assert "white-line energy +0.4" in row["reasons"][0]["said"]
    metrics["SYN_D#6"]["metrics"]["wl_e_eV"] = 11218.06           # within the threshold: noise, kept
    row = _decide(recs, flags, {"rows": metrics})["by_id"]["SYN_D#6"]
    assert row["decision"] == "keep" and row["notes"][0]["code"] == "noisier_not_off_shape"


# --- coverage of the end-to-end findings on real beamtimes (18 Nov 2026), each on SYN data ----------------------------


def _mono_only(cols):
    """A SYN scan as the older SPEC files write it (BL6-2c 2018, BL15-2 2019): the energy is the scanned ``mono`` motor,
    the time ``Seconds``; no ``energy`` or ``absev`` column, and no BL15-2 detector name."""
    return {"mono": cols["absev"], "I0": cols["I0"], "I1": cols["I1"], "FF1": cols["vortDT"], "Seconds": cols["sec"]}


def test_a_gscan_of_mono_or_of_the_chosen_energy_column_is_an_energy_scan():
    from isaac_api.local_import.processing import run as R

    assert R._is_energy_scan(("gscan", "mono")) and R._is_energy_scan(("gscan", "energy"))
    assert R._is_energy_scan(("ascan", "mono"), "mono")            # the motor IS the chosen energy column
    assert not R._is_energy_scan(("ascan", "mono"), "absev")       # a mono motor scan beside an absev axis
    assert not R._is_energy_scan(("ascan", "Sz"), "mono")


def test_a_gscan_mono_beamtime_runs_on_v1_and_is_aligned(tmp_path):
    runs = [("01_SYN_ZZ1_060mV", 9, [_mono_only(scan_cols(10 + k, d=d)) for k, d in enumerate(REF_D)]),
            ("02_SYN_ZZ2_060mV", 11, [_mono_only(scan_cols(20 + k, d=d)) for k, d in enumerate(SMP_D)])]
    bdir, _ = imported(tmp_path, runs, command="gscan mono 11165 11205 5 11240 0.25 11500 4 0.5")
    res = v1_results(bdir)
    assert len(res) == 2, "both groups run on isaac.xas.v1"
    smp = by_run(res, "02_SYN_ZZ2")
    assert smp[EX.REFERENCE_KEY]["routes"][0]["mode"] == "glitch_I0"
    assert not any("not_an_energy_scan" in str(i.get("skip_reason")) for i in smp["inputs"])
    ref_mean = float(np.mean(REF_D))
    for r, ds in ((by_run(res, "01_SYN_ZZ1"), REF_D), (smp, SMP_D)):
        assert max(abs(e) for e in _shift_errors(r, ds, ref_mean)) < 5.0


# --- the foil timeline: separate foil scans, one detector position, the foils before the calibration left out --------


def _foil_scan(seed, d, *, on_i2=False, n_points=None):
    """A SYN transmission foil scan (no fluorescence channel): the foil edge at the tabulated edge + ``d``; on I1
    (ln(I0/I1)), or ``on_i2`` in another detector position (ln(I1/I2), its edge distorted)."""
    c = scan_cols(seed, d=d, glitch=False, fluo=False, n_points=n_points)
    t = c["absev"] - d
    muf = 0.3 + 0.8 / (1 + np.exp(-(t - E_EDGE) / 0.9))
    if on_i2:
        c["I1"] = 0.6 * c["I0"]
        c["I2"] = c["I1"] * np.exp(-(0.3 + 0.8 / (1 + np.exp(-(t - E_EDGE - 1.4) / 2.5))))
    else:
        c["I1"] = c["I0"] * np.exp(-muf)
        c["I2"] = np.full(c["I0"].size, 2.0)                # a dark chamber beyond the foil
    return c


def _drift(hour):
    """The SYN mono drift: +0.30 eV over hours 9 -> 15."""
    return 0.05 * (hour - 9)


def _foil_beamtime():
    return [("00_SYN_Irfoil_calib_a", 7, [_foil_scan(1, -1.9)]),                    # before the mono calibration
            ("01_SYN_Irfoil_calib_b", 8, [_foil_scan(2, _drift(8))]),
            ("02_SYN_ZZ2_060mV", 9, [scan_cols(20 + k, glitch=False, d=_drift(9)) for k in range(3)]),
            ("03_SYN_ZZ3_060mV", 12, [scan_cols(30 + k, glitch=False, d=_drift(12)) for k in range(3)]),
            ("04_SYN_Irfoil_I2", 13, [_foil_scan(4, _drift(13), on_i2=True)]),     # another detector position
            ("05_SYN_ZZ5_060mV", 14, [scan_cols(50 + k, glitch=False, d=_drift(14)) for k in range(3)]),
            ("06_SYN_Irfoil_I1", 15, [_foil_scan(6, _drift(15))])]


def test_separate_foil_scans_give_a_foil_timeline_on_the_package_rules(tmp_path):
    bdir, _ = imported(tmp_path, _foil_beamtime())
    payload = json.loads((bdir / "processing" / "processing_results.json").read_text())
    bt = payload[EX.BEAMTIME_KEY]
    assert bt["calibration"]["mode"] == "foil_timeline", bt["calibration"]
    used = [f["spec"] for f in bt["calibration"]["foils"]]
    assert used == ["01_SYN_Irfoil_calib_b", "06_SYN_Irfoil_I1"], used    # one position; the last pre-sample foil
    route = bt["routes"][0]
    assert route["reference_name"] == "01_SYN_Irfoil_calib_b" and route["method"] == "shape"
    assert [x["foil"] for x in route["timeline"]] == used
    res = v1_results(bdir)
    assert len(res) == 3
    for stem, hour in (("02_SYN_ZZ2", 9), ("03_SYN_ZZ3", 12), ("05_SYN_ZZ5", 14)):
        rows = by_run(res, stem)[EX.SHIFTS_KEY]["rows"]
        want = _drift(8) - _drift(hour)                       # linear in time between the foils, on the reference foil
        for x in rows:
            assert x["route"] == "foil_timeline" and abs(1000 * (x["shift_eV"] - want)) < 12.0, (stem, x)


def _foil_reads(foils):
    """Minimal reads for :func:`engine_xas._foil_timeline`: ``foils`` = [(name, [(hour, d, grid step)])]."""
    from datetime import datetime as dt

    reads, groups = {}, {}
    for name, scans in foils:
        recs = []
        for j, (hour, d, step) in enumerate(scans, start=1):
            E = np.arange(11165.0, 11400.0, step)
            t = E - d
            I0 = np.full(E.size, 1e5)
            I1 = I0 * np.exp(-(0.3 + 0.8 / (1 + np.exp(-(t - E_EDGE) / 0.9))))
            recs.append({"E": E, "I0": I0, "I1": I1, "I2": I1 * 0.5, "IF": None, "num": j,
                         "scan_id": f"{name}#{j}", "time": dt(2025, 4, 12, hour, j)})
        reads[f"rg-{name}"] = {"recs": recs}
        groups[name] = f"rg-{name}"
    return reads, {"file_groups": groups}


def test_the_foil_timeline_anchors_by_shape_and_indexes_the_foil_list():
    # the reference foil (index 0) is scanned AFTER the other one; a coarse 1 eV grid on the edge, where the inflection
    # is quantised and the shape fit is not
    reads, bt = _foil_reads([("SYN_foilB", [(12, 0.20, 1.0), (12, 0.20, 1.0)]), ("SYN_foilA", [(9, 0.0, 0.25)])])
    route = {"mode": "foil_timeline", "method": "shape", "reference_foil": 0,
             "foils": [{"spec": "SYN_foilB", "ref_signal": "ln(I0/I1)"}, {"spec": "SYN_foilA", "ref_signal": "ln(I0/I1)"}],
             "foil_window_eV": [E_EDGE - 6, E_EDGE + 6], "shape_window_eV": [E_EDGE - 8, E_EDGE + 24], "max_shift_eV": 2.0}
    out = EX._foil_timeline(route, bt, reads)
    assert out["reference_name"] == "SYN_foilB" and out["scans"] == ["SYN_foilB#1", "SYN_foilB#2"]
    tl = {x["scan"]: x["anchor_eV"] for x in out["timeline"]}
    assert len(tl) == 3
    assert abs(1000 * ((tl["SYN_foilB#1"] - tl["SYN_foilA#1"]) - 0.20)) < 5.0      # the true 0.20 eV, by shape
    assert out["anchor_eV"] == pytest.approx(tl["SYN_foilB#1"], abs=1e-3)


# --- normalisation: tender fluorescence options, glitches kept out of the windows ------------------------------------


def _mcmaster(el, core, E):
    from xas_analysis.model.mback import atomic_step
    from xas_analysis.physics.mcmaster import element

    e = element(el)
    edge = e["K_edge"] if core == "K" else e["L_edge"][2]
    mu, _ = atomic_step(e["Z"], E / 1000, edge)
    return mu, 1000 * edge


def test_tender_fluorescence_uses_the_documented_options_and_says_so():
    E = np.arange(2390.0, 2816.0, 1.0)
    mu, e0 = _mcmaster("S", "K", E)
    u = E / e0 - 1
    F = (E / e0) ** 3.0                                     # the gas I0 response: IF/I0 rises with E
    raw = F * (0.05 + 0.4 * np.exp(-(E - 2391) / 40.0) + 2.5 * (1 + 1.2 * u) * mu)
    nm = EX.normalize_once(E, raw, np.ones(E.size), {"element": "S", "edge": "K", "E_edge_eV": e0, "basis": "SYN"},
                           {"windows": {}}, np)
    assert nm["tender"]["tender"] is True and nm["options"]["response_power"] == 3.0
    assert nm["options"]["step_slope"] == 1 and nm["options"]["pre_tail"] is True
    assert nm["window_eV"][1] == pytest.approx(e0 - 24.0, abs=0.1)
    assert nm["A_edge"] == pytest.approx(2.5, rel=0.02)
    assert "Tender-fluorescence normalisation" in nm["tender"]["statement"]
    hard = EX.tender_choice(E + 9000, raw / F, 11564.0, [11400, 11550, 11620, 11800], np)
    assert hard["tender"] is False


def test_the_glitch_window_is_kept_out_of_the_normalisation():
    E = np.arange(11540.0, 11806.0, 1.0)
    mu, e0 = _mcmaster("Pt", "L3", E)
    clean = 0.02 + 0.7 * mu
    dip = clean.copy()
    dip[(E >= 11701) & (E <= 11704)] += 0.6                # a glitch residue in IF/I0, in the post-edge window
    bt = {"windows": {}, "calibration": {"mode": "glitch_I0"},
          "consensus": {"found": True, "center_eV": 11702.5, "fwhm_eV": 1.0}}
    absorber = {"element": "Pt", "edge": "L3", "E_edge_eV": e0, "basis": "SYN"}
    nm = EX.normalize_once(E, dip, np.ones(E.size), absorber, bt, np)
    ref = EX.normalize_once(E, clean, np.ones(E.size), absorber, {"windows": {}}, np)
    assert nm["exclude_eV"] and nm["exclude_eV"][0][0] <= 11701 and nm["exclude_eV"][0][1] >= 11704
    assert nm["A_edge"] == pytest.approx(ref["A_edge"], rel=1e-3)
    assert "never removed" in nm["exclude_statement"]


# --- a standard v0 reduces as fluorescence (its transmission fails) is on v1 too -------------------------------------


def test_a_standard_whose_transmission_fails_is_reduced_as_fluorescence_on_v1(tmp_path):
    std = []
    for k in range(3):
        c = scan_cols(70 + k)
        c["I1"] = np.full(c["I0"].size, -5.0)               # I1 negative everywhere: transmission cannot be formed
        std.append(c)
    runs = _two_groups() + [("03_SYN_IrO2_std_005", 13, std)]
    bdir, _ = imported(tmp_path, runs)
    r = by_run(v1_results(bdir), "03_SYN_IrO2_std")
    assert r["protocol_id"] == "isaac.xas.v1"
    assert "channel_fallback_transmission_not_positive" in r["review_flags"]
    assert "channel_fallback_transmission_not_positive" in r["qc"]["reasons"]


# --- spots in SPEC split files; within-spot dose damage ---------------------------------------------------------------


def test_spots_of_split_files_take_the_motor_names_from_the_acquisition_file(tmp_path):
    sz = [-7.45] * 2 + [-7.15] * 2
    runs = [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k, d=d) for k, d in enumerate(REF_D)]),
            ("02_SYN_ZZ2_060mV", 11, [scan_cols(40 + k) for k in range(4)], sz)]
    bdir, _ = imported(tmp_path, runs, positional=True, ext="txt")
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert [rows[k].get("spot") for k in (1, 2, 3, 4)] == ["spot 1", "spot 1", "spot 2", "spot 2"]
    assert [x["name"] for x in r["spots"]["spots"]] == ["spot Sz -7.45", "spot Sz -7.15"]


def _dose_run(wl_of, scale_of=None, noise_of=None):
    """4 spots x 2 scans (A1 A2 B1 B2 ...); ``wl_of(k)``: the white-line height of scan k (0-based)."""
    sz = [-7.45, -7.45, -7.15, -7.15, -6.85, -6.85, -6.55, -6.55]
    cols = [scan_cols(110 + k, wl=wl_of(k), scale=(scale_of or (lambda k: 1.0))(k),
                      noise=(noise_of or (lambda k: 2e-3))(k)) for k in range(8)]
    return _spot_run(sz, cols)


def test_later_scans_at_each_spot_that_change_shape_are_beam_damage(tmp_path, capsys):
    from isaac_api.local_import import cli

    bdir, _ = imported(tmp_path, _dose_run(lambda k: 3.0 if k % 2 == 0 else 2.55))
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    for k in (1, 3, 5, 7):
        assert rows[k]["decision"] == "keep", (k, rows[k]["reasons"])
    for k in (2, 4, 6, 8):
        assert rows[k]["decision"] == "drop" and [y["code"] for y in rows[k]["reasons"]] == [EX.DOSE_CODE], \
            (k, rows[k]["reasons"])
        assert "beam damage at each spot: later scans at the same spot change shape" in rows[k]["reasons"][0]["said"]
    assert r["dose_damage"]["rule_id"] == EX.DOSE_RULE_ID and len(r["dose_damage"]["spots"]) >= 2
    assert "dose_damage" in r["qc"]["statements"]
    # overridable: a scientist keeps scan 2
    assert cli.main(["bundle", "decide", str(bdir), "--target", r["group_id"], "--decision", "set_scan_decision",
                     "--value", "keep", "--scans", "02_SYN_ZZ2_060mV#2", "--note", "SYN: keep it", "--by", "SYN"]) == 0
    from isaac_api.local_import import mutations as M

    M.process(bdir, source=str(tmp_path / "SYN_beamtime"))
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    row = next(x for x in r[EX.DECISIONS_KEY]["rows"] if x["scan"] == 2)
    assert row["decision"] == "keep" and row["decided_by"] == "scientist" and row["rule_decision"] == "drop"


@pytest.mark.parametrize("case", ["one_noisy_spot", "intensity_only", "still_changing"])
def test_dose_damage_never_fires_on_one_spot_on_intensity_or_on_an_evolution(tmp_path, case):
    if case == "one_noisy_spot":
        runs = _dose_run(lambda k: 2.55 if k == 7 else 3.0, noise_of=lambda k: 1.2e-2 if k == 7 else 2e-3)
    elif case == "intensity_only":
        runs = _dose_run(lambda k: 3.0, scale_of=lambda k: 1.0 if k % 2 == 0 else 0.6)
    else:                       # the white line falls scan after scan, across spots: the sample, not the dose
        runs = _dose_run(lambda k: 3.0 - 0.15 * k)
    bdir, _ = imported(tmp_path, runs)
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    assert "dose_damage" not in r
    said = json.dumps(r[EX.DECISIONS_KEY]["rows"])
    assert "beam damage" not in said
    if case == "still_changing":
        return
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert all(rows[k]["decision"] == "keep" for k in range(1, 7)), {k: x["reasons"] for k, x in rows.items()}
    if case == "intensity_only":
        assert all(x["decision"] == "keep" for x in rows.values())


# --- single-point I0 dropouts: the POINT is excluded, said, never interpolated; the scan is kept ----------------------


def test_a_single_point_i0_dropout_is_excluded_from_that_scans_contribution(tmp_path):
    scans = [scan_cols(120 + k) for k in range(5)]
    j = int(np.flatnonzero(GRID >= 11300.0)[0])
    scans[2]["I0"] = scans[2]["I0"].copy()
    scans[2]["I0"][j] = 1.0                                   # one count among ~1e5
    runs = [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k, d=d) for k, d in enumerate(REF_D)]),
            ("02_SYN_ZZ2_060mV", 11, scans)]
    bdir, _ = imported(tmp_path, runs)
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert rows[3]["decision"] == "keep"
    note = next(n for n in rows[3]["notes"] if n["code"] == EX.I0_DROPOUT_CODE)
    assert note["said"] == f"point excluded: I0 dropout (1 counts at {GRID[j]:.2f} eV)"
    assert r["point_exclusions"]["points"][0]["scan_id"] == "02_SYN_ZZ2_060mV#3"
    merged = next(f for f in r["outputs"]["files"] if f["role"] == "merged")["relative_path"]
    m = np.genfromtxt(bdir / merged, delimiter=",", names=True, skip_header=1)
    k = int(np.argmin(np.abs(m["energy_eV"] - GRID[j] - (rows[3]["shift_eV"] or 0))))
    assert m["n_scans"][k] == 4.0                             # the other scans cover that energy
    nb = np.median(m["mu_mean"][k - 3:k + 4])
    assert abs(m["mu_mean"][k] - nb) < 0.02 * nb              # no spike in the merge


# --- the ratio screens drop only a NORMALISED-shape distortion ---------------------------------------------------------


def test_a_within_scan_step_collapse_drops_and_a_uniformly_weaker_scan_does_not(tmp_path):
    scans = [scan_cols(130 + k) for k in range(6)]
    collapse = GRID > 11330.0
    scans[2]["vortDT"] = np.where(collapse, 0.55, 1.0) * scans[2]["vortDT"]    # the signal collapses mid-scan
    scans[4] = scan_cols(134, scale=0.5, bg=0.3)                                 # uniformly weaker, on a background
    runs = [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k, d=d) for k, d in enumerate(REF_D)]),
            ("02_SYN_ZZ2_060mV", 11, scans)]
    bdir, _ = imported(tmp_path, runs)
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    rows = {x["scan"]: x for x in r[EX.DECISIONS_KEY]["rows"]}
    assert rows[3]["decision"] == "drop", rows[3]
    codes = {y["code"] for y in rows[3]["reasons"]}
    assert codes & {"post_drift", "ratio_shape"}, rows[3]["reasons"]
    assert any("NORMALISED shape is distorted" in y["said"] for y in rows[3]["reasons"])
    assert rows[5]["decision"] == "keep", rows[5]
    assert all(rows[k]["decision"] == "keep" for k in (1, 2, 4, 5, 6))


# --- coverage is edge-relative; an aborted group says so ----------------------------------------------------------------


def test_a_shorter_scan_that_covers_the_windows_is_complete(tmp_path):
    n = int(np.flatnonzero(GRID >= 11400.0)[0])               # ends ~125 eV past the post-edge start: under 90 %
    scans = [scan_cols(140 + k) for k in range(4)] + [scan_cols(145, n_points=n)]
    runs = [("01_SYN_ZZ1_060mV", 9, [scan_cols(10 + k, d=d) for k, d in enumerate(REF_D)]),
            ("02_SYN_ZZ2_060mV", 11, scans)]
    bdir, _ = imported(tmp_path, runs)
    r = by_run(v1_results(bdir), "02_SYN_ZZ2")
    row = next(x for x in r[EX.DECISIONS_KEY]["rows"] if x["scan"] == 5)
    assert row["decision"] == "keep", row["reasons"]
    assert "shorter_but_complete" in {n["code"] for n in row["notes"]}, row["notes"]


@pytest.mark.parametrize("end, code, said", [
    (11232.0, "scan_range_incomplete", "not the pre-edge window through the post-edge window"),
    (11208.0, "scan_never_reaches_edge", "this scan never reaches the absorption edge")])
def test_a_one_scan_short_group_says_why_never_a_raw_error(tmp_path, end, code, said):
    n = int(np.flatnonzero(GRID >= end)[0]) + 1
    runs = _two_groups() + [("03_SYN_ZZ3_060mV", 13, [scan_cols(150, n_points=n)])]
    bdir, _ = imported(tmp_path, runs)
    r = next(x for x in v1_results(bdir) if x["inputs"][0]["relative_path"].startswith("03_SYN_ZZ3"))
    assert r["failure"]["code"] == code, r["failure"]
    assert said in r["failure"]["detail"] and "Error" not in r["failure"]["detail"]
    assert "measurement_mode_unknown" not in r["review_flags"]


# --- "still changing" needs a change beyond the noise ----------------------------------------------------------------


def test_before_the_stable_window_within_the_noise_is_kept():
    recs = [_rec(f"SYN_E#{k}", k, seed=k) for k in range(1, 7)]
    metrics = {f"SYN_E#{k}": {"metrics": {"wl_e_eV": 11218.0, "sd_wl_e_eV": 0.02, "wl_h": 2.0, "sd_wl_h": 0.01,
                                          "delta_eV": 0.0, "sd_delta_eV": 0.02},
                              "reasons": ["before_stable_window"] if k <= 2 else [],
                              "proposal": "exclude_proposed" if k <= 2 else "keep",
                              "said": ["the sample was still changing (wl_e_eV)"] if k <= 2 else []}
               for k in range(1, 7)}
    metrics["SYN_E#1"]["metrics"]["wl_e_eV"] = 11217.95          # 0.05 eV: within the noise
    metrics["SYN_E#2"]["metrics"]["wl_e_eV"] = 11217.40          # 0.6 eV: a real change
    stab = {"rows": metrics, "stable_window": ["SYN_E_003.dat"], "evolving_metrics": ["wl_e_eV"]}
    row = _decide(recs, stability=stab)["by_id"]
    assert row["SYN_E#1"]["decision"] == "keep" and row["SYN_E#1"]["notes"][0]["code"] == "change_within_noise"
    assert row["SYN_E#2"]["decision"] == "drop" and row["SYN_E#2"]["reasons"][0]["code"] == "before_stable_window"
