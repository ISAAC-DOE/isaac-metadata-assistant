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

from isaac_api.local_import.processing import engine_xas as EX  # noqa: E402

E_EDGE = 11215.0      # Ir L3, tabulated (McMaster); the synthetic edge sits there
GLITCH = 11226.6      # the synthetic I0 glitch (true energy)
GRID = np.r_[np.arange(11165, 11205, 5.0), np.arange(11205, 11240, 0.25), np.arange(11240, 11500, 4.0)]
BY = {"by": "SYN Scientist", "orcid": None}


@pytest.fixture(autouse=True)
def _engine_on(monkeypatch):
    monkeypatch.setenv("ISAAC_PROCESSING_ENGINE", "v1")


def scan_cols(seed, *, d=0.0, chem=0.0, scale=1.0, noise=2e-3, foil=False, glitch=True, fluo=True, trans_step=0.0,
              n_points=None):
    """One SYN scan. ``d``: the mono offset (the recorded absev reads ``d`` above the true energy, so every feature
    sits at its true energy + d); ``chem``: a true shift of the sample's own edge; ``scale``: the signal's intensity."""
    rng = np.random.default_rng(seed)
    E = GRID.copy() if n_points is None else GRID[:n_points].copy()
    t = E - d
    I0 = 1e5 * (1 - 0.0004 * (E - 11165))
    if glitch:
        I0 = I0 * (1 - 0.06 * np.exp(-((t - GLITCH) / 0.22) ** 2))
    mu = 0.05 + 1.0 / (1 + np.exp(-(t - E_EDGE - chem) / 1.2)) + 3 * np.exp(-((t - 11218 - chem) / 1.5) ** 2)
    IF = scale * mu * I0 * 1e-3 * (1 + noise * rng.standard_normal(E.size))
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


def _spec(cols, n, hour):
    names = list(cols)
    lines = ["#C SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value is invented.",
             f"#S {n}  gscan energy 11165 11205 5 11240 0.25 11500 4 0.5",
             f"#D Sat Apr 12 {hour:02d}:{n:02d}:00 2025", "#P0 dummy0=4 emiss=9175.4 filter=10 Sx=1 Sy=2 Sz=3 Sr=0",
             "#L " + "  ".join(names)]
    for row in zip(*(cols[k] for k in names)):
        lines.append(" ".join(f"{v:.6f}" for v in row))
    return "\n".join(lines) + "\n"


def write_beamtime(root, runs):
    """``runs``: [(stem, hour, [cols, ...])]: each run an acquisition file of #S blocks beside its per-scan files."""
    for stem, hour, scans in runs:
        d = root / f"{stem}_dir"
        d.mkdir(parents=True)
        blocks = []
        for j, c in enumerate(scans, start=1):
            text = _spec(c, j, hour)
            (d / f"{stem}_{j:03d}.dat").write_text(text)
            blocks.append(text)
        (root / stem).write_text(f"#F {stem}\n#E 1\n\n" + "\n".join(blocks))


def imported(tmp_path, runs, *, process=True):
    from isaac_api.local_import import cli
    from isaac_api.local_import import mutations as M

    root = tmp_path / "SYN_beamtime"
    write_beamtime(root, runs)
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
    assert row["SYN_A#7"]["decision"] == "drop" and row["SYN_A#7"]["reasons"][0]["code"] == "anchor_failed"
    assert row["SYN_A#8"]["decision"] == "drop" and row["SYN_A#8"]["reasons"][0]["code"] == "anchor"
    assert t["counts"] == {"scans": 8, "kept": 2, "dropped": 6, "overridden_by_scientist": 0}
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
