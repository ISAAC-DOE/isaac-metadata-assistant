"""SPEC files -> aligned + averaged *_raw spectra (port of reduce_xas_v2.m).

Stages: 1 parse, 2 reference anchor (I0 glitch inflection), 3 per-scan shift + resample,
4 per-sample weighted average, 5 save.

The recipe is a dict (or a YAML file) with the same fields as the MATLAB recipe struct:

    samples:                      # list
      - spec: path/to/SPECfile    # relative paths resolve against the recipe file
        name: IrO2_ref
        output_name: IrO2_ref
        scans: [1, 2, 3, 4]       # empty/missing = all
        outliers: [3]             # dropped from the average
        role: reference | sample
    calibration: {mode: glitch_I0, window_eV: [11232.0, 11233.5],
                  reference_sample: IrO2_ref, reference_scan: 3}
        # mode: ref_foil -> anchor on a reference foil, ref_signal "ln(I0/I2)" (or "ln(I1/I2)",
        #   "-ln(I2/I0)"); method: inflection (max dmu/dE in window_eV, rising) | shape (shift
        #   of the whole foil spectrum vs the reference scan over shape_window_eV, free
        #   scale + offset; anchor = template inflection - shift). method: shape also works
        #   for glitch_I0 (fits ln I0): 3-8 meV per-scan scatter vs 10-30 (Ir) / ~80 (Cu foil)
        #   for the inflection; inflection stays the default for MATLAB parity.
        #   method: model (glitch_I0 only): Gaussian dip + linear fit of ln I0 in
        #   shape_window_eV, template-free (no grid-phase bias for narrow glitches)
        # reference_sample: earliest  -> file whose first scan has the earliest #D date
        # reference_scan: mean        -> mean anchor of that sample's good, non-outlier scans
        #                                (energy grid = its first good scan)
    energy_grid: reference        # or an explicit list of eV
    averaging: {weights: uniform, min_scans: 1, drop_empty_points: false}
    outputs: {output_dir: reduced_v2, save_per_scan: true, save_avg: true, save_diagnostic: true}
    column_map: {}                # e.g. {IF: vortDT2}
    data_root: <data root>/...    # optional base for relative spec paths
    screening: {anchor_mad: 5, shape_mad: 6, window_eV: [11205, 11260]}   # optional, off if absent
        # anchor_mad: drop scans whose anchor is > k robust sigmas (1.4826 MAD, floor
        #             anchor_floor_eV = 0.03) from the file median; shape_mad: same on the RMS
        #             deviation of IF/I0 (scaled to the file median) from the file median
        #             inside window_eV, and > shape_min_ratio (1.5) x the median RMS;
        #             any scan covering < min_coverage (0.9) of the grid is dropped (aborted)
    normalize: {element: Ir, core: L3, range: [11166, 11206, 11275, 11487]}   # optional
        # model: victoreen (default; mback_xrs) | victoreen_linear | poly (mback, nth [1, 1])
        # writes <output_name>_avg_nrm = [E, norm, mu_McMaster]; A_edge goes into the diagnostic
"""
from __future__ import annotations

import json
import re
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from .average import AlignedScan, average_scans
from .calib import align_and_resample, find_inflection_point, fit_glitch_center, fit_glitch_doublet
from .io.spec import read_xas_scans
from .matlab_compat import save_ascii


def _spec_time(d: str):
    try:
        return datetime.strptime(d.strip(), "%a %b %d %H:%M:%S %Y")
    except (ValueError, AttributeError):
        return None


def load_recipe(path) -> dict:
    path = Path(path)
    with open(path) as fh:
        r = yaml.safe_load(fh)
    base = path.parent
    if r.get("data_root"):  # spec paths resolve against data_root (~ expanded), else the recipe dir
        base_spec = (base / Path(r["data_root"]).expanduser()).resolve()
    else:
        base_spec = base
    for s in r.get("samples", []) + list((r.get("calibration") or {}).get("foils") or []):
        if "spec" in s and not Path(s["spec"]).is_absolute():
            s["spec"] = str((base_spec / s["spec"]).resolve())
    od = r.get("outputs", {}).get("output_dir")
    if od and not Path(od).is_absolute():
        r["outputs"]["output_dir"] = str((base / od).resolve())
    return r


def fill_recipe_defaults(recipe: dict) -> dict:
    r = dict(recipe)
    r.setdefault("quiet", False)
    r.setdefault("column_map", {})
    r.setdefault("energy_grid", "reference")
    av = dict(r.get("averaging") or {})
    av.setdefault("weights", "uniform")
    av.setdefault("min_scans", 1)
    # False = MATLAB behaviour (zero rows where no scan covers the point); True drops them
    av.setdefault("drop_empty_points", False)
    r["averaging"] = av
    out = dict(r.get("outputs") or {})
    out.setdefault("output_dir", "reduced_v2")
    out.setdefault("save_per_scan", True)
    out.setdefault("save_avg", True)
    out.setdefault("save_diagnostic", True)
    r["outputs"] = out
    samples = []
    for k, s in enumerate(r["samples"], 1):
        s = dict(s)
        s.setdefault("name", f"sample_{k}")
        s.setdefault("output_name", s["name"])
        s.setdefault("role", "sample")
        s["outliers"] = list(s.get("outliers") or [])
        s["scans"] = list(s.get("scans") or [])
        samples.append(s)
    r["samples"] = samples
    cal = dict(r.get("calibration") or {})
    if not cal:
        raise ValueError("recipe.calibration is required")
    cal.setdefault("mode", "glitch_I0")
    if "window_eV" not in cal and cal["mode"].lower() not in ("foil_timeline", "none"):
        raise ValueError("calibration.window_eV required")
    mode = cal["mode"].lower()
    if mode not in ("glitch_i0", "ref_foil", "foil_timeline", "none"):
        raise ValueError(f'calibration.mode must be glitch_I0, ref_foil, foil_timeline or none '
                         f'(got "{cal["mode"]}")')
    if mode in ("foil_timeline", "none"):
        cal.setdefault("reference_sample", r["samples"][0]["name"])
        cal.setdefault("reference_scan", "first")
        cal.setdefault("window_eV", [-np.inf, np.inf])
    if mode == "foil_timeline":
        if not cal.get("foils"):
            raise ValueError("foil_timeline needs calibration.foils: [{spec, ref_signal}, ...]")
        cal.setdefault("method", "shape")
    cal.setdefault("method", "inflection")
    if cal["method"] not in ("inflection", "shape", "model"):
        raise ValueError("calibration.method must be inflection, shape or model")
    if cal["method"] == "model" and mode != "glitch_i0":
        raise ValueError("calibration.method model is for glitch_I0 (Gaussian dip fit)")
    if mode == "ref_foil":
        cal.setdefault("ref_signal", "ln(I0/I2)")
        _ref_signal_terms(cal["ref_signal"])
    r["calibration"] = cal
    return r


def _read_scans(r, spec, scan_filter=None):
    reader = r.get("reader", "spec")
    if reader == "spec":
        return read_xas_scans(spec, column_map=r["column_map"], scan_filter=scan_filter, quiet=True)
    if reader == "ssrl_xdc":
        from .io.ssrl_xdc import read_xdc_scans
        return read_xdc_scans(spec, sca_channels=r.get("sca_channels"), scan_filter=scan_filter)
    raise ValueError(f"reader must be spec or ssrl_xdc (got {reader!r})")


def foil_timeline(r, cal):
    """Anchors of separate reference-foil scans (shape fit vs the first foil scan, or the
    rising inflection), with their times. Returns (times, anchors, rows)."""
    rows = []
    for f in cal["foils"]:
        fc = {"mode": "ref_foil", "ref_signal": f.get("ref_signal", "ln(I0/I1)"),
              "window_eV": f.get("window_eV", cal.get("foil_window_eV")), "method": "inflection"}
        for sc in _read_scans(r, f["spec"], f.get("scans")):
            rows.append((sc, fc))
    if not rows:
        raise ValueError("foil_timeline: no foil scans read")
    sc0, fc0 = rows[0]
    infl = make_anchor_fn(fc0)
    t_anchor, _ = infl(sc0)
    shape_cfg = dict(fc0, method="shape", shape_window_eV=cal.get("shape_window_eV", fc0["window_eV"]),
                     max_shift_eV=cal.get("max_shift_eV", 2.0))
    out = []
    for sc, fc in rows:
        if cal.get("method", "shape") == "shape":
            fn = make_anchor_fn(dict(shape_cfg, ref_signal=fc["ref_signal"]),
                                (sc0.Energy_eV, anchor_signal(sc0, fc0)), t_anchor)
        else:
            fn = make_anchor_fn(fc)
        a, ai = fn(sc)
        t = _spec_time(sc.date)
        out.append({"file": Path(str(sc.channel_map.get("file", ""))).name or sc.num, "num": sc.num,
                    "time": t.isoformat() if t else None, "anchor_eV": float(a), "ok": bool(ai.get("ok", False))})
    good = [(datetime.fromisoformat(o["time"]).timestamp(), o["anchor_eV"]) for o in out
            if o["ok"] and o["time"] and np.isfinite(o["anchor_eV"])]
    if not good:
        raise ValueError("foil_timeline: no foil scan gave a usable anchor")
    good.sort()
    return np.array([g[0] for g in good]), np.array([g[1] for g in good]), out


def _ref_signal_terms(expr: str) -> tuple[str, str]:
    m = re.fullmatch(r"\s*-?ln\(\s*(\w+)\s*/\s*(\w+)\s*\)\s*", expr)
    if not m:
        raise ValueError(f'calibration.ref_signal must look like "ln(I0/I2)" (got "{expr}")')
    num, den = m[1], m[2]
    return (den, num) if expr.strip().startswith("-") else (num, den)


def anchor_signal(sc, cal) -> np.ndarray:
    """The curve whose feature defines the energy anchor: I0 (glitch; ln I0 for the shape
    fit) or ln(a/b) (foil)."""
    if cal["mode"].lower() == "glitch_i0":
        if cal.get("method") == "shape":
            with np.errstate(all="ignore"):
                return np.log(sc.I0)
        return sc.I0
    num, den = _ref_signal_terms(cal["ref_signal"])
    a, b = getattr(sc, num), getattr(sc, den)
    if a is None or b is None:
        raise ValueError(f"scan {sc.num}: channel {num} or {den} missing for ref_signal")
    with np.errstate(all="ignore"):
        return np.log(a / b)


def fit_shape_shift(E, y, Et, yt, window, max_shift=2.0, step=0.002):
    """Shift d (eV) that best maps y(E + d) onto the template yt(Et) over window, with a
    free linear scale + offset; parabola-refined grid search. Returns (d, rms)."""
    m = (Et >= window[0]) & (Et <= window[1]) & np.isfinite(yt)
    o = np.argsort(E)
    E, y = E[o], y[o]
    ok = np.isfinite(y)
    E, y = E[ok], y[ok]
    ds = np.arange(-max_shift, max_shift + step / 2, step)
    r = np.empty(ds.size)
    for i, d in enumerate(ds):
        yi = np.interp(Et[m], E + d, y, left=np.nan, right=np.nan)
        g = np.isfinite(yi)
        if g.sum() < 5:
            r[i] = np.inf
            continue
        X = np.c_[yi[g], np.ones(g.sum())]
        c = np.linalg.lstsq(X, yt[m][g], rcond=None)[0]
        r[i] = np.mean((yt[m][g] - X @ c) ** 2)
    k = int(np.argmin(r))
    d = ds[k]
    if 0 < k < ds.size - 1 and np.all(np.isfinite(r[k - 1:k + 2])):
        den = r[k - 1] - 2 * r[k] + r[k + 1]
        if den > 0:
            d += 0.5 * step * (r[k - 1] - r[k + 1]) / den
    return float(d), float(np.sqrt(r[k]))


def make_anchor_fn(cal, template=None, template_anchor=None):
    """sc -> (anchor_eV, info). For ref_foil + shape: anchor = template anchor - fitted shift."""
    def fn(sc):
        if cal.get("method") == "model":
            win = cal.get("shape_window_eV", cal["window_eV"])
            with np.errstate(all="ignore"):
                if int(cal.get("glitch_dips", 1)) == 2:      # double glitch: midpoint of two dips
                    return fit_glitch_doublet(sc.Energy_eV, np.log(sc.I0), win,
                                              sep_eV=tuple(cal.get("doublet_sep_eV", (0.8, 2.2))))
                return fit_glitch_center(sc.Energy_eV, np.log(sc.I0), win)
        y = anchor_signal(sc, cal)
        if cal["method"] == "shape" and template is not None:
            win = cal.get("shape_window_eV", cal["window_eV"])
            ms = cal.get("max_shift_eV", 2.0)
            win = [max(win[0], np.nanmin(template[0]) + ms), min(win[1], np.nanmax(template[0]) - ms)]
            E = np.asarray(sc.Energy_eV, float)
            if not (np.nanmin(E) <= win[0] + ms and np.nanmax(E) >= win[1] - ms):
                # not an energy scan over the window (e.g. a motor alignment ascan)
                return np.nan, {"ok": False, "reason": "energy axis does not span shape_window_eV"}
            d, rms = fit_shape_shift(E, y, template[0], template[1], win, max_shift=ms)
            ok = bool(np.isfinite(d)) and abs(d) < 0.98 * ms
            return template_anchor - d, {"ok": ok, "shift_fit_rms": rms,
                                         "reason": "" if ok else "shift at the search limit"}
        if cal["mode"].lower() == "ref_foil":
            return find_inflection_point(sc.Energy_eV, y, cal["window_eV"], sign=1)
        return find_inflection_point(sc.Energy_eV, sc.I0, cal["window_eV"])
    return fn


def screen_scans(out, cfg) -> list[tuple[int, str]]:
    """Robust per-file screen; sets keep=False on flagged scans and returns (num, reason)."""
    return _apply([(a, f["reason"]) for a, f in _screen(out, cfg)])


def screen_report(out, cfg) -> list[dict]:
    """The same screen in REPORT-ONLY mode (ISAAC, PROVENANCE.md M1): nothing is set on the scans; every flag is
    returned with its evidence, so a caller's own documented rule decides what is dropped. Each flag:
    ``{"scan": num, "key": key, "test": coverage|dead_channel|anchor|shape|ratio_shape|post_drift, "reason": str,
    "value": float, "median": float, "threshold": float}`` (a scan may carry several)."""
    rows = []
    for a, f in _screen(out, cfg):
        rows.append({"scan": a.num, "key": a.key, **f})
    return rows


def _screen(out, cfg) -> list[tuple]:
    """(scan, flag) pairs; nothing is changed on the scans. Later tests see only scans no EARLIER test flagged, as
    screen_scans always did (an aborted scan is not also judged off-shape)."""
    flagged = []
    def flag(a, test, reason, value, median=None, threshold=None):
        flagged.append((a, {"test": test, "reason": reason, "value": _num(value), "median": _num(median),
                            "threshold": _num(threshold)}))
    # coverage: aborted scans (finite IF/I0 on < min_coverage of the grid) - any scan count
    cov_min = cfg.get("min_coverage", 0.9)
    for a in out:
        if a.keep and a.quality_ok:
            with np.errstate(all="ignore"):
                cov = np.mean(np.isfinite(a.IF / a.I0) & (a.I0 != 0))
            if cov < cov_min:
                flag(a, "coverage", f"covers {100 * cov:.0f}% of the grid (aborted?)", cov, None, cov_min)
    bad = {id(a) for a, _ in flagged}
    good = [a for a in out if a.keep and a.quality_ok and id(a) not in bad]
    if len(good) < 3:
        return flagged

    def robust(v, floor):
        med = np.median(v)
        return med, max(1.4826 * np.median(np.abs(v - med)), floor)

    # dead fluorescence channel: peak |IF| below 1 % of the file median peak
    pk = np.array([np.nanmax(np.abs(a.IF)) if np.isfinite(a.IF).any() else 0.0 for a in good])
    dead = pk < 0.01 * np.median(pk)
    for a, x in zip(good, pk):
        if x < 0.01 * np.median(pk):
            flag(a, "dead_channel", f"dead IF channel (peak {x:.3g} vs median {np.median(pk):.3g})", x,
                 np.median(pk), 0.01 * np.median(pk))
    good = [a for a, d in zip(good, dead) if not d]
    if len(good) < 3:
        return flagged
    k = cfg.get("anchor_mad")
    if k:
        v = np.array([a.anchor_eV for a in good])
        # floor 30 meV: alignment corrects real offsets; this only catches failed anchors
        med, sig = robust(v, cfg.get("anchor_floor_eV", 0.03))
        for a, x in zip(good, v):
            if abs(x - med) > k * sig:
                flag(a, "anchor", f"anchor {1000 * (x - med):+.0f} meV from file median", x - med, med, k * sig)
    k = cfg.get("shape_mad")
    if k:
        lo, hi = cfg.get("window_eV", [-np.inf, np.inf])
        E = good[0].E
        m = (E >= lo) & (E <= hi)
        with np.errstate(all="ignore"):
            Y = np.array([a.IF[m] / a.I0[m] for a in good])
        ref = np.nanmedian(Y, axis=0)
        sc = np.nanmedian(np.abs(ref)) or 1.0
        # scale each scan to the median first: shape, not overall level. ISAAC (PROVENANCE.md M7): with
        # ``shape_affine`` a free scale AND offset, so a constant background is not "shape" either
        affine = bool(cfg.get("shape_affine"))
        rms = []
        for y in Y:
            ok = np.isfinite(y) & np.isfinite(ref)
            if affine and ok.sum() > 2:
                A = np.c_[y[ok], np.ones(ok.sum())]
                (c, b), *_ = np.linalg.lstsq(A, ref[ok], rcond=None)
                rms.append(np.sqrt(np.mean((c * y[ok] + b - ref[ok]) ** 2)) / sc)
                continue
            c = np.dot(y[ok], ref[ok]) / np.dot(y[ok], y[ok]) if ok.any() else np.nan
            rms.append(np.sqrt(np.mean((c * y[ok] - ref[ok]) ** 2)) / sc if ok.any() else np.inf)
        rms = np.array(rms)
        med, sig = robust(rms[np.isfinite(rms)], 1e-4)
        for a, x in zip(good, rms):
            if not np.isfinite(x) or (x - med > k * sig and x > cfg.get("shape_min_ratio", 1.5) * med):
                flag(a, "shape", f"shape rms {x:.2e} vs median {med:.2e}", x, med,
                     max(med + k * sig, cfg.get("shape_min_ratio", 1.5) * med))
    rs = cfg.get("ratio_shape")
    if rs and len(good) >= 3:
        # intensity distortion inside a scan (drift, bubbles): ratio of each scan to the median of
        # the other scans over the post-edge, normalized to its own median. A healthy scan gives a
        # flat ratio (BL6-2 2018: ~1 %); a drifting one tilts (0 V scan 3: +4 % over 11570-11800 eV),
        # a bubble-hit one bends (-0.6 V scan 5: -15 % near 11580 eV). Flag by tilt or by bump.
        lo, hi = rs.get("window_eV", [-np.inf, np.inf])
        E = good[0].E
        m = (E >= lo) & (E <= hi)
        if rs.get("exclude_eV"):
            for a_, b_ in rs["exclude_eV"]:
                m &= ~((E >= a_) & (E <= b_))
        with np.errstate(all="ignore"):
            Y = np.array([a.IF[m] / a.I0[m] for a in good])
        x = (E[m] - E[m].mean()) / max(np.ptp(E[m]), 1e-9)
        n_s = int(rs.get("smooth_pts", 5))
        tilt, bump = [], []
        for i in range(len(good)):
            with np.errstate(all="ignore"):
                r = Y[i] / np.nanmedian(np.delete(Y, i, axis=0), axis=0)
            ok = np.isfinite(r)
            if ok.sum() < 5:
                tilt.append(np.nan); bump.append(np.nan); continue
            r = r / np.nanmedian(r[ok])
            tilt.append(float(np.polyfit(x[ok], r[ok], 1)[0]))          # change across the window
            rsm = np.convolve(r[ok], np.ones(n_s) / n_s, "same") if ok.sum() > n_s else r[ok]
            bump.append(float(np.nanmax(np.abs(rsm[n_s:-n_s] - 1.0))) if ok.sum() > 2 * n_s + 1 else np.nan)
        for name, v in (("tilt", np.array(tilt)), ("bump", np.array(bump))):
            fin = np.isfinite(v)
            if fin.sum() < 3:
                continue
            med, sig = robust(v[fin], 1e-3)
            for a, val in zip(good, v):
                if np.isfinite(val) and abs(val - med) > rs.get("mad", 5) * sig and abs(val - med) > rs.get("min_frac", 0.02):
                    flag(a, "ratio_shape", f"ratio-shape {name} {100 * (val - med):+.1f}% vs the other scans "
                         f"(window {lo:g}-{hi:g} eV)", val - med, med, max(rs.get("mad", 5) * sig, rs.get("min_frac", 0.02)))
    pd = cfg.get("post_drift")
    if pd:
        # signal collapse late in a scan (bubble, electrode, beam): the post-edge falls while the
        # XANES window looks normal (BL6-2 2018 PtNPs_08 scan 5: -76 % of the step; min_frac 0.15 keeps ~10 % noise). Per scan:
        # (level at the end of the post-edge - level at its start) / edge step, vs file median.
        (a1, b1), (a2, b2) = pd.get("windows", [[11625, 11660], [11760, 11800]])
        p1, p2 = pd.get("pre_eV", [-np.inf, -np.inf]), None
        E = good[0].E
        m1, m2 = (E >= a1) & (E <= b1), (E >= a2) & (E <= b2)
        mp = (E >= p1[0]) & (E <= p1[1]) if np.isfinite(p1[0]) else None
        v = []
        with np.errstate(all="ignore"):
            for a in good:
                y = a.IF / a.I0
                base = np.nanmedian(y[mp]) if mp is not None and mp.any() else 0.0
                lev1, lev2 = np.nanmedian(y[m1]), np.nanmedian(y[m2])
                v.append((lev2 - lev1) / (lev1 - base) if np.isfinite(lev1) and lev1 != base else np.nan)
        v = np.array(v)
        if np.isfinite(v).sum() >= 3:
            med, sig = robust(v[np.isfinite(v)], 1e-3)
            for a, x in zip(good, v):
                if np.isfinite(x) and abs(x - med) > pd.get("mad", 5) * sig and abs(x - med) > pd.get("min_frac", 0.15):
                    flag(a, "post_drift", f"post-edge drift {100 * x:+.0f}% of the step (file median {100 * med:+.0f}%)",
                         x, med, max(pd.get("mad", 5) * sig, pd.get("min_frac", 0.15)))
    return flagged


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _apply(flagged):
    # ISAAC M1: deduplicated by the scan's identity (a pooled sample repeats scan numbers across files), not its number
    seen, res = set(), []
    for a, why in flagged:
        a.keep = False
        if a.ident not in seen:
            seen.add(a.ident)
            res.append((a.num, why))
    return res


def normalize_spectrum(E, y, cfg, n_scans=None):
    """Normalize one averaged spectrum per the recipe's normalize block (None if it fails).

    n_scans: scans contributing at each point; points with 0 are not data (grid ends after the
    alignment shift, stored as 0 like MATLAB). Zero VALUES are kept: HERFD pre-edges are
    nearly background-free and read 0 counts legitimately (dropping them biases the pre-edge
    level up, and with heavy filters removes the whole pre-edge).
    """
    model = cfg.get("model", "victoreen")
    ok = np.isfinite(E) & np.isfinite(y)
    if n_scans is not None:
        ok &= np.asarray(n_scans) > 0
    try:
        if model in ("victoreen", "victoreen_linear"):
            from .model.mback_xrs import mback_xrs
            # fluorescence options (tender XAS): bg_decreasing, pre_tail, step_slope
            return mback_xrs(cfg["element"], E[ok], y[ok], cfg.get("range"), cfg.get("core", ""),
                             linear=model == "victoreen_linear",
                             bg_decreasing=cfg.get("bg_decreasing"),    # default: constrained
                             pre_tail=bool(cfg.get("pre_tail", False)),
                             step_slope=int(cfg.get("step_slope", 0)),
                             step_factor_base=cfg.get("step_factor_base"),
                             post_poly=int(cfg.get("post_poly", 0)),
                             extra_edges=[tuple(x) for x in cfg.get("extra_edges", [])] or None,
                             exclude_eV=cfg.get("exclude_eV"),
                             response_power=cfg.get("response_power"))
        if model == "athena":
            from .model.athena_norm import athena_norm
            return athena_norm(cfg["element"], E[ok], y[ok], cfg.get("range"), cfg.get("core", ""),
                               E0_eV=cfg.get("E0_eV"), pre_order=int(cfg.get("pre_order", 1)),
                               post_order=int(cfg.get("post_order", 2)), flatten=bool(cfg.get("flatten", True)))
        if model == "poly":
            from .model.mback import mback
            return mback(cfg["element"], E[ok], y[ok], cfg.get("range"), tuple(cfg.get("nth", (1, 1))),
                         cfg.get("core", ""))
        raise ValueError(f"normalize.model {model!r} unknown (victoreen | victoreen_linear | poly | athena)")
    except ValueError as e:
        warnings.warn(f"normalize: {e}")
        return None


def self_absorption_output(res, sa_cfg, ncfg):
    """Thick-limit self-absorption correction of one normalized result (None + warning if the
    thick limit is inconsistent with the data). Returns ([E, s, mu] array, info)."""
    from .model.self_absorption import mixture_mass_fractions, sa_correct_thick
    i = res.info
    E = res.energy_eV
    # background-subtracted, NOT divided by the step-slope factor (the correction replaces it)
    yc = res.norm_xas * i["step_factor"] if "step_factor" in i else res.norm_xas
    post = i.get("i_post")
    contrast = float(np.nanmax(res.norm_xas) / np.nanmedian(res.norm_xas[post] / np.where(res.mu[post] > 0, res.mu[post], np.nan)))
    try:
        s, info = sa_correct_thick(E, yc, ncfg["element"], mixture_mass_fractions(sa_cfg["composition"]),
                                   res.mu, post, phi_in_deg=float(sa_cfg.get("phi_in_deg", 45.0)),
                                   theta_out_deg=float(sa_cfg.get("theta_out_deg", 45.0)),
                                   E_fluo_keV=sa_cfg.get("E_fluo_keV"), contrast=contrast)
    except ValueError as e:
        warnings.warn(str(e))
        return None
    M = np.c_[E, s, res.mu]
    return M[~np.isnan(M).any(axis=1)], {k: v for k, v in info.items()}


def tabulated_edge_eV(element: str, core: str) -> float | None:
    """The McMaster table's edge energy in eV (K, L1-L3), or None."""
    from .physics.mcmaster import element as _el
    try:
        el = _el(element)
    except (ValueError, IndexError):
        return None
    core = (core or "").upper()
    if core == "K":
        return 1000.0 * el["K_edge"]
    if core in ("L1", "L2", "L3"):
        return 1000.0 * el["L_edge"][int(core[1]) - 1]
    return None


def sample_mode(sample: dict, scans, normalize: dict | None) -> dict | None:
    """measurement_mode (survey.py) of one recipe sample's scans at the normalize block's edge; None when the
    recipe names no edge or the sample states its mode (``mode: fluorescence`` keeps it)."""
    if sample.get("mode") == "fluorescence" or not normalize or not normalize.get("element"):
        return None
    E_edge = tabulated_edge_eV(normalize["element"], normalize.get("core") or "")
    if E_edge is None:
        return None
    from .survey import ScanInfo, measurement_mode
    infos = []
    for sc in scans:
        if sc.Energy_eV is None or sc.I0 is None:
            continue
        ch = {"I0": sc.I0, "I1": sc.I1, "I2": sc.I2}
        if sc.IF is not None:
            ch["IF"] = sc.IF
        infos.append(ScanInfo(str(sample.get("spec", "")), sc.num, None, np.asarray(sc.Energy_eV, float),
                              {k: np.asarray(v, float) for k, v in ch.items() if v is not None}))
    return measurement_mode(infos, E_edge, f"{sample.get('name', '')} {Path(str(sample.get('spec', ''))).name}")


def _log(r, msg):
    if not r["quiet"]:
        print(msg)


def _glitch_or_foil_reference(r, cal, parsed):
    """Reference anchor for glitch_I0 / ref_foil: (anchor_ref, grid scan, ref_anchors, info, anchor_of)."""
    if str(cal["reference_sample"]).lower() == "earliest":
        # SPEC file whose first scan has the earliest #D date (closest to the beamline mono
        # calibration); falls back to recipe order for undated scans
        def _t0(p):
            ts = [_spec_time(sc.date) for sc in p[1]]
            ts = [t for t in ts if t is not None]
            return min(ts) if ts else datetime.max
        cal["reference_sample"] = min(parsed, key=_t0)[0]["name"]
        _log(r, f"  earliest sample -> {cal['reference_sample']}")
    ref = [p for p in parsed if p[0]["name"] == cal["reference_sample"]]
    if not ref:
        raise ValueError(f'reference_sample "{cal["reference_sample"]}" not found among parsed samples.')
    # template (for ref_foil + shape): the reference scan, or the reference sample's first
    # non-outlier scan when reference_scan is 'mean'; its own anchor is its inflection
    anchor_of = make_anchor_fn(cal)
    if cal["method"] == "shape":
        cand = [sc for sc in ref[0][1] if (sc.num == cal["reference_scan"]) or
                (str(cal["reference_scan"]).lower() == "mean" and sc.num not in ref[0][0]["outliers"])]
        if not cand:
            raise ValueError("ref_foil/shape: no template scan in the reference sample")
        tsc = cand[0]
        t_anchor, _ = anchor_of(tsc)
        anchor_of = make_anchor_fn(cal, (tsc.Energy_eV, anchor_signal(tsc, cal)), t_anchor)
        _log(r, f"  shape template: {cal['reference_sample']} scan #{tsc.num}, inflection {t_anchor:.4f} eV")
    ref_anchors = []
    if str(cal["reference_scan"]).lower() == "mean":
        # mean anchor over the reference sample's good, non-outlier scans: averages out the
        # ~10-35 meV scan-to-scan anchor noise a single reference scan carries
        for sc in ref[0][1]:
            if sc.num in ref[0][0]["outliers"]:
                continue
            a, ai = anchor_of(sc)
            if np.isfinite(a) and ai["ok"]:
                ref_anchors.append((sc.num, a))
        if not ref_anchors:
            raise ValueError("reference_scan 'mean': no scan of the reference sample has a good anchor")
        rsc = [sc for sc in ref[0][1] if sc.num == ref_anchors[0][0]][0]   # grid source
        anchor_ref = float(np.mean([a for _, a in ref_anchors]))
        ainfo = {"mode": "mean", "scans": [n for n, _ in ref_anchors],
                 "anchors": [a for _, a in ref_anchors],
                 "std_eV": float(np.std([a for _, a in ref_anchors], ddof=1)) if len(ref_anchors) > 1 else 0.0}
    else:
        rsc = [sc for sc in ref[0][1] if sc.num == cal["reference_scan"]]
        if not rsc:
            raise ValueError(f'reference_scan {cal["reference_scan"]} not present in sample "{cal["reference_sample"]}".')
        rsc = rsc[0]
        anchor_ref, ainfo = anchor_of(rsc)
        if not np.isfinite(anchor_ref):
            raise ValueError(f"failed to locate anchor in reference scan: {ainfo['reason']}")
    return anchor_ref, rsc, ref_anchors, ainfo, anchor_of


def reduce(recipe: dict | str | Path) -> dict:
    """Run the full pipeline; returns a results dict and writes the output files."""
    if isinstance(recipe, (str, Path)):
        recipe = load_recipe(recipe)
    r = fill_recipe_defaults(recipe)

    _log(r, "\n=== 1. parse_all ===")
    parsed, skipped = [], []
    for s in r["samples"]:
        _log(r, f"  parsing [{s['name']}]: {s['spec']}")
        scans = _read_scans(r, s["spec"], s["scans"] or None)
        _log(r, f"    -> {len(scans)} scans kept")
        mode = sample_mode(s, scans, r.get("normalize"))
        if mode and mode["mode"] == "transmission":
            # ISAAC M3: scope.md says transmission-mode samples are NOT SUPPORTED (the pipeline reduces IF/I0);
            # such a sample is no longer reduced as if its IF column were the measurement. `mode: fluorescence`
            # on the sample keeps it.
            warnings.warn(f"sample [{s['name']}]: transmission-mode data ({mode['basis']}): not reduced "
                          "(not supported; set `mode: fluorescence` on the sample to reduce its IF/I0)")
            skipped.append({"name": s["name"], "reason": "transmission_mode", "evidence": mode})
            continue
        parsed.append((s, scans))
    if not parsed:
        raise ValueError("no sample left to reduce: " + "; ".join(f"{x['name']}: {x['reason']}" for x in skipped))

    _log(r, "\n=== 2. reference (locate energy anchor) ===")
    cal = r["calibration"]
    timeline = None
    if cal["mode"].lower() in ("foil_timeline", "none"):
        if cal["mode"].lower() == "foil_timeline":
            tt, aa, rows = foil_timeline(r, cal)
            for o in rows:
                _log(r, f"  foil {o['file']} #{o['num']} {o['time']}: anchor {o['anchor_eV']:.4f} eV"
                        + ("" if o["ok"] else "  (rejected)"))
            ref_i = cal.get("reference_foil", 0)
            anchor_ref = float(aa[ref_i])
            timeline = {"times": tt, "anchors": aa, "rows": rows}
        else:
            tt, aa, anchor_ref = None, None, 0.0

        def anchor_of(sc):
            if timeline is None:
                return 0.0, {"ok": True}
            t = _spec_time(sc.date)
            if t is None:
                return np.nan, {"ok": False, "reason": "scan has no date"}
            # linear in time between foil scans, constant beyond the first / last one
            return float(np.interp(t.timestamp(), tt, aa)), {"ok": True}
        ref = [p for p in parsed if p[0]["name"] == cal["reference_sample"]]
        if not ref:
            raise ValueError(f'reference_sample "{cal["reference_sample"]}" not found among parsed samples.')
        rsc = ref[0][1][0] if cal["reference_scan"] in ("first", "mean") else \
            [sc for sc in ref[0][1] if sc.num == cal["reference_scan"]][0]
        ref_anchors, ainfo = [], {"mode": cal["mode"], "timeline": timeline and timeline["rows"]}
        _log(r, f"  energy grid from {cal['reference_sample']} scan #{rsc.num}; reference anchor {anchor_ref:.4f} eV")
    else:
        anchor_ref, rsc, ref_anchors, ainfo, anchor_of = _glitch_or_foil_reference(r, cal, parsed)
    grid = r["energy_grid"]
    if isinstance(grid, str):
        if grid.lower() != "reference":
            raise ValueError("energy_grid must be 'reference' or a list of energies")
        target_E = np.asarray(rsc.Energy_eV, float).ravel()
    else:
        target_E = np.asarray(grid, float).ravel()
    if ref_anchors:
        _log(r, f"  reference anchor = mean of {len(ref_anchors)} scans (std {ainfo['std_eV'] * 1000:.1f} meV)")
    _log(r, f"  reference anchor: {cal['reference_sample']} scan #{cal['reference_scan']} -> "
            f"E_anchor = {anchor_ref:.4f} eV (window [{cal['window_eV'][0]:.3f}, {cal['window_eV'][1]:.3f}])")
    _log(r, f"  target energy axis: {target_E.size} points, [{target_E.min():.2f}, {target_E.max():.2f}] eV")

    _log(r, "\n=== 3. align (per-scan shift + resample) ===")
    aligned = []
    for s, scans in parsed:
        out = []
        for sc in scans:
            anc, ai = anchor_of(sc)
            if not np.isfinite(anc):
                nanv = np.full(target_E.size, np.nan)
                out.append(AlignedScan(sc.num, target_E, nanv, nanv.copy(), nanv.copy(),
                                       quality_ok=False, keep=False))
                continue
            sec = sc.sec if sc.sec is not None else np.full(sc.Energy_eV.size, np.nan)
            Y, ri = align_and_resample(sc.Energy_eV, np.c_[sc.IF, sc.I0, sec], anc, anchor_ref, target_E)
            out.append(AlignedScan(sc.num, target_E, Y[:, 0], Y[:, 1], Y[:, 2], anc,
                                   anchor_ref - anc, ai["ok"] and ri["ok"],
                                   sc.num not in s["outliers"]))
        aligned.append((s, out))
        sh = np.array([a.shift_eV for a in out], float)
        sh = sh[np.isfinite(sh)]
        kept = sum(a.keep and a.quality_ok for a in out)
        if sh.size:
            sd = sh.std(ddof=1) if sh.size > 1 else 0.0
            _log(r, f"  [{s['name']}]: {kept}/{len(out)} scans, anchor shift = {sh.mean():+.4f} +/- {sd:.4f} eV")

    if r.get("screening"):
        _log(r, "\n=== 3b. screening (anchor + shape) ===")
        for s, out in aligned:
            for num, why in screen_scans(out, r["screening"]):
                _log(r, f"  [{s['name']}]: scan {num} dropped ({why})")

    _log(r, "\n=== 4. average (per-sample weighted mean) ===")
    avgs = []
    for s, out in aligned:
        for a in out:
            a.keep = a.keep and a.quality_ok
        try:
            avg, info = average_scans(out, r["averaging"]["weights"], r["averaging"]["min_scans"], True,
                                      r["averaging"]["drop_empty_points"])
            _log(r, f"  [{s['name']}]: averaged {len(info['kept_indices'])} scans, scheme=\"{info['scheme']}\"")
        except ValueError as e:
            warnings.warn(f"sample [{s['name']}]: {e}")
            avg, info = None, {}
        avgs.append((avg, info))

    _log(r, "\n=== 5. save (per-scan + avg + diagnostic) ===")
    od = Path(r["outputs"]["output_dir"])
    od.mkdir(parents=True, exist_ok=True)
    files, samples_out = [], []
    for (s, out), (avg, info) in zip(aligned, avgs):
        mine = []
        if r["outputs"]["save_per_scan"]:
            for a in out:
                fn = od / f"{s['output_name']}_scans{a.num:03d}_raw"
                with np.errstate(all="ignore"):
                    M = np.c_[a.E, a.IF / a.I0, np.zeros(a.E.size), a.sec]
                # MATLAB quirk kept: rows with any NaN are dropped, so a file without a
                # 'sec' column gives empty per-scan files
                M = M[~np.isnan(M).any(axis=1)]
                save_ascii(fn, M)
                mine.append(str(fn))
        if r["outputs"]["save_avg"] and avg is not None:
            fn = od / f"{s['output_name']}_avg_raw"
            M = np.c_[avg["E"], avg["IF_over_I0"], avg["err"], avg["sec_total"]]
            M = M[~np.isnan(M).any(axis=1)]
            save_ascii(fn, M)
            mine.append(str(fn))
        files += mine
        samples_out.append({"name": s["name"], "output_name": s["output_name"], "role": s["role"],
                            "scans": out, "avg": avg, "avg_info": info, "files_written": mine})
    _log(r, f"  wrote {len(files)} files into {od}")

    if r.get("normalize"):
        _log(r, "\n=== 6. normalize (" + r["normalize"].get("model", "victoreen") + ") ===")
        per_sample = {s["name"]: s.get("normalize") or {} for s in r["samples"]}
        for so in samples_out:
            if so["avg"] is None:
                continue
            # sample-level normalize block overrides the global one (extra edges, windows)
            ncfg = {**r["normalize"], **per_sample.get(so["name"], {})}
            res = normalize_spectrum(so["avg"]["E"], so["avg"]["IF_over_I0"], ncfg,
                                     so["avg"].get("n_kept"))
            if res is None:
                continue
            so["A_edge"] = res.info["A_edge"]
            fn = od / f"{so['output_name']}_avg_nrm"
            M = np.c_[res.energy_eV, res.norm_xas, res.mu]
            save_ascii(fn, M[~np.isnan(M).any(axis=1)])
            so["files_written"].append(str(fn))
            files.append(str(fn))
            _log(r, f"  [{so['name']}]: A_edge = {res.info['A_edge']:.5g}")
            sa_cfg = next((s.get("self_absorption") for s in r["samples"] if s["name"] == so["name"]), None)
            if sa_cfg:
                sac = self_absorption_output(res, sa_cfg, ncfg)
                if sac is not None:
                    fn = od / f"{so['output_name']}_avg_sac"
                    save_ascii(fn, sac[0])
                    so["self_absorption"] = sac[1]
                    so["files_written"].append(str(fn))
                    files.append(str(fn))
                    _log(r, f"  [{so['name']}]: self-absorption corrected (max n/K {sac[1]['max_n_over_K']:.3f})")

    results = {"skipped_samples": skipped, "target_E": target_E,
               "reference": {"sample": cal["reference_sample"], "scan": cal["reference_scan"],
                             "anchor_eV": anchor_ref, "anchor_info": ainfo},
               "samples": samples_out, "files_written": files}
    if r["outputs"]["save_diagnostic"]:
        diag = {"skipped_samples": skipped, "reference": {**{k: v for k, v in results["reference"].items() if k != "anchor_info"},
                              **({"mean_of": ainfo} if ref_anchors else {})},
                "samples": [{"name": so["name"],
                             "scans": [{"num": a.num, "anchor_eV": a.anchor_eV, "shift_eV": a.shift_eV,
                                        "quality_ok": a.quality_ok, "kept": a.keep} for a in so["scans"]],
                             "A_edge": so.get("A_edge"),
                             **({"self_absorption": so["self_absorption"]} if so.get("self_absorption") else {}),
                             "files": so["files_written"]} for so in samples_out]}
        with open(od / "reduce_diag.json", "w") as fh:
            json.dump(diag, fh, indent=1, default=float)
    _log(r, "\nreduce done.")
    return results
