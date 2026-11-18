"""Survey a beamtime folder before writing a recipe: what is there, and how to calibrate it.

The checks are the ones that decided the calibration of every dataset reduced so far
(docs/PORT_STATUS.md, skill/references/calibration.md):

  files      format (SPEC / SSRL EXAFS Data Collector), XAS scans, times, energy grids
  edge       element and edge from the scan range (McMaster table) and the fluorescence step
  channels   which column carries the fluorescence (largest edge contrast), I1/I2 dark or not
  axes       SPEC 'energy' vs 'absev' offset (2025 BL15-2: 2.3 eV; absev is the encoder)
  foil       edge in ln(I0/I1), ln(I1/I2), ln(I0/I2) at the sample's edge -> in-scan reference
  glitch     sharp dips in ln I0 common to the scans (not at grid-step boundaries); whether the
             max-|dI0/dE| anchor is bimodal (sharp symmetric dips: use the shape fit)
  log        'mono reset' lines and energy scans with an edge in alignment-type files
  foil files separate foil scans (name or transmission-only) -> foil timeline candidates
  docs       logbooks / readmes to read for curation

recommend() turns the findings into a calibration block: ref_foil if the sample scans carry a
foil edge, else glitch_I0 if a consistent glitch exists, else foil_timeline if foil files
exist, else none. Every choice comes with the evidence; nothing here edits data.
"""
from __future__ import annotations

import glob
import json
import os
import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import savgol_filter

from .calib import find_inflection_point
from .physics.mcmaster import elements

DOC_EXT = (".txt", ".docx", ".pdf", ".md", ".doc", ".xlsx")
SKIP_EXT = (".mac", ".png", ".jpg", ".fig", ".m", ".sh", ".py", ".zip", ".prj", ".nor", ".xmu")
NON_SIGNAL = {"energy", "absev", "epoch", "sec", "i0", "i1", "i2", "i3", "spear", "gap", "gapct",
              "eth", "emission", "bgi0", "bgi1", "bgi2", "i0gain", "i0offs", "i2gain", "i2offs",
              "real time clock", "sum_rtc", "requested energy", "achieved energy", "lytle", "spare",
              "mono", "tc", "dummy0", "modsum", "c5", "c6", "c7"}
REF_NAMES = re.compile(r"(IrO2|Oxide|oxide|pellet|_ref|_std|standard|anatase|ANATASE|Ti2O3|"
                       r"H2IrCl6|Chloride|Nanoparticles|metal|_foil)", re.I)
FOIL_NAMES = re.compile(r"foil", re.I)


@dataclass
class ScanInfo:
    file: str
    num: int
    time: datetime | None
    E: np.ndarray
    ch: dict
    energy_motor: np.ndarray | None = None
    energy_column: str = "absev"


@dataclass
class FileInfo:
    path: str
    name: str
    fmt: str
    scans: list = field(default_factory=list)
    n_all: int = 0
    log: list = field(default_factory=list)
    # ISAAC (PROVENANCE.md M2): a caller that already knows what this "file" is (a record group pooling several
    # files: "sample", "reference", "alignment", "foil") says so; None = guess from the name as before
    role: str | None = None


def _time(s):
    for fmt in ("%a %b %d %H:%M:%S %Y",):
        try:
            return datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            pass
    return None


def _is_xdc(path):
    try:
        with open(path, errors="replace") as fh:
            return "EXAFS Data Collector" in fh.readline()
    except OSError:
        return False


def _is_spec(path):
    try:
        with open(path, errors="replace") as fh:
            head = fh.read(4000)
    except OSError:
        return False
    return "\n#S " in head or head.startswith("#F") or "\n#L " in head


def collect(folder) -> tuple[list[FileInfo], list[str]]:
    """Read every data file in folder (non-recursive; *_dir sub-folders are SPEC split copies)."""
    from .io.spec import parse_spec
    from .io.ssrl_xdc import parse_xdc
    folder = Path(folder).expanduser()
    files, docs, xdc_groups = [], [], {}
    for p in sorted(folder.iterdir()):
        if p.is_dir() or p.name.startswith("."):
            continue
        if p.suffix.lower() in DOC_EXT or p.name.lower().startswith("readme"):
            docs.append(p.name)
            continue
        if p.suffix.lower() in SKIP_EXT:
            continue
        if re.search(r"_A\.\d+$", p.name) and _is_xdc(p):
            xdc_groups.setdefault(re.sub(r"_A\.\d+$", "", p.name), []).append(p)
        elif _is_spec(p):
            fi = FileInfo(str(p), p.name, "spec")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    sf = parse_spec(p)
                except Exception:          # noqa: BLE001 - unreadable file: report, skip
                    continue
            fi.n_all = len(sf.scans)
            for s in sf.scans:
                if s.data.size == 0 or s.data.shape[0] < 40:
                    continue
                c = dict(zip(s.column_names, s.data.T))
                E = c.get("absev", c.get(s.column_names[0]))
                tok = s.macro_str.split()
                energy_scan = bool(tok) and (tok[0] in ("gscan", "escan") or tok[1:2] == ["energy"])
                if E is None or not energy_scan or np.ptp(E) < 25:
                    continue
                fi.scans.append(ScanInfo(p.name, int(s.num), _time(s.date), np.asarray(E, float), c,
                                         np.asarray(c["energy"], float) if "energy" in c else None,
                                         "absev" if "absev" in c else s.column_names[0]))
            fi.log = _read_log(p)
            files.append(fi)
    for stem, ps in xdc_groups.items():
        fi = FileInfo(str(folder / stem), stem, "ssrl_xdc")
        for p in sorted(ps):
            d = parse_xdc(p)
            if d["data"].shape[0] < 40:
                continue
            c = {n: d["data"][:, k] for k, n in enumerate(d["column_names"])}
            Eax = c.get("Achieved Energy")
            if Eax is None or np.ptp(Eax) < 25 or np.nanmedian(Eax) < 1000:
                continue                                    # motor alignment scan
            sca = [n for n in d["column_names"] if n.startswith("SCA")]
            if sca:
                c["SCA_sum"] = np.sum([c[n] for n in sca], axis=0)
            fi.scans.append(ScanInfo(p.name, int(p.name.rsplit(".", 1)[1]), _time(d["date"]),
                                     np.asarray(c["Achieved Energy"], float), c))
        fi.n_all = len(ps)
        if fi.scans or not re.search(r"align", stem, re.I):
            files.append(fi)
    files.sort(key=lambda f: min([s.time for s in f.scans if s.time] or [datetime.max]))
    return files, docs


def _read_log(path):
    out = []
    with open(path, errors="replace") as fh:
        for ln in fh:
            m = re.match(r"#C (.*?)\.\s+(mono|energy|absev) reset from (\d+(?:\.\d+)?) to (\d+(?:\.\d+)?)", ln)
            if m:
                out.append({"time": m[1], "axis": m[2], "from": float(m[3]), "to": float(m[4])})
    return out


def identify_edge(scans) -> dict | None:
    """Tabulated edge inside the scan range with the largest fluorescence step."""
    E = np.concatenate([s.E for s in scans])
    lo, hi = np.nanpercentile(E, 2), np.nanpercentile(E, 98)
    cands = []
    for el in elements():
        for core, e in [("K", el["K_edge"])] + list(zip(("L1", "L2", "L3"), el["L_edge"])):
            if e and lo + 5 < 1000 * e < hi - 20:          # table in keV, scans in eV
                cands.append((el["symbol"], core, 1000 * e))
    if not cands:
        return None
    best, score = None, -np.inf
    for sym, core, e in cands:
        sc = -np.inf
        for s in scans:
            sig = _best_fluo(s)[1]
            if sig is not None:
                with np.errstate(all="ignore"):
                    y = sig / s.ch["I0"]
            elif s.ch.get("I0") is not None and s.ch.get("I1") is not None:
                with np.errstate(all="ignore"):
                    y = np.log(s.ch["I0"] / s.ch["I1"])          # foil scans: transmission
            else:
                continue
            g = np.abs(np.gradient(y, s.E))
            m = (s.E > e - 8) & (s.E < e + 8)
            if m.any():
                sc = max(sc, np.nanmax(g[m]) / (np.nanmedian(g) + 1e-30))
        if sc > score:
            best, score = (sym, core, e), sc
    if best is None:
        return None
    return {"element": best[0], "core": best[1], "E_edge_eV": round(best[2], 1),
            "candidates": [f"{a} {b} {c:.1f}" for a, b, c in cands]}


def _best_fluo(s, E_edge=None):
    """(name, signal) of the fluorescence channel with the largest edge contrast."""
    best, bsig, bc = None, None, 0.0
    I0 = s.ch.get("I0")
    if I0 is None:
        return None, None
    E = s.E
    e0 = E_edge if E_edge else np.nanmedian(E)
    pre, post = E < e0 - 10, E > e0 + 30
    if pre.sum() < 2 or post.sum() < 2:
        pre, post = E < np.nanpercentile(E, 15), E > np.nanpercentile(E, 85)
    for k, v in s.ch.items():
        if k.lower() in NON_SIGNAL or k.startswith(("SCA1_", "ICR")) or np.nanmax(np.abs(v)) == 0:
            continue
        with np.errstate(all="ignore"):
            y = v / I0
        a, b = np.nanmedian(y[pre]), np.nanmedian(y[post])
        c = (b - a) / (abs(b) + abs(a) + 1e-30)
        if np.isfinite(c) and c > bc:
            best, bsig, bc = k, v, c
    return best, bsig


def fluo_channel(files, E_edge):
    votes = {}
    for f in files:
        for s in f.scans[:3]:
            k, _ = _best_fluo(s, E_edge)
            if k:
                votes[k] = votes.get(k, 0) + 1
    return max(votes, key=votes.get) if votes else None, votes


def axes_offset(files):
    off = [np.median(s.E - s.energy_motor) for f in files for s in f.scans if s.energy_motor is not None]
    if not off:
        return None
    off = np.array(off)
    return {"median_eV": float(np.median(off)), "p5_eV": float(np.percentile(off, 5)),
            "p95_eV": float(np.percentile(off, 95)), "n": int(off.size)}


RATIOS = (("I0", "I1"), ("I1", "I2"), ("I0", "I2"))


def _dark(B, I0):
    """A dark ion chamber reads a constant offset + noise (BL6-2 2018: I1 ~ 987 counts, flat):
    < 0.5 % relative spread and < 0.3 x the relative spread of I0."""
    B = np.asarray(B, float)
    if np.nanmedian(B) < 50:
        return True
    rel = np.nanstd(B) / max(np.nanmedian(B), 1e-12)
    if I0 is None or rel >= 0.005:
        return False
    I0 = np.asarray(I0, float)
    rel0 = np.nanstd(I0) / max(np.nanmedian(I0), 1e-12)
    # a lit chamber varies (relatively) about as much as I0 does; an offset varies far less
    return rel < 0.3 * rel0


def foil_edges(s, E_edge):
    """Step and inflection of each transmission ratio at E_edge (dark channels skipped)."""
    out = {}
    I0 = s.ch.get("I0")
    for a, b in RATIOS:
        A, B = s.ch.get(a), s.ch.get(b)
        if A is None or B is None or np.nanmedian(A) < 50 or _dark(B, I0):
            continue
        with np.errstate(all="ignore"):
            y = np.log(A / B)
        pre, post = (s.E < E_edge - 10), (s.E > E_edge + 25)
        if pre.sum() < 2:                  # short calibration scans start close to the edge
            pre = s.E < E_edge - 3
        if post.sum() < 2:
            post = s.E > E_edge + 10
        if pre.sum() < 2 or post.sum() < 2:
            continue
        step = float(np.nanmedian(y[post]) - np.nanmedian(y[pre]))
        infl, info = find_inflection_point(s.E, y, [E_edge - 6, E_edge + 6], sign=1 if step > 0 else -1)
        out[f"ln({a}/{b})"] = {"step": step, "inflection_eV": float(infl)}
    return out


def glitch_candidates(files, max_scans=40):
    """Sharp dips in ln I0 common to the scans, on the first scan's grid."""
    scans = [s for f in files for s in f.scans[:3]][:max_scans]
    if len(scans) < 2:
        return []
    Eg = scans[0].E
    R = []
    for s in scans:
        I0 = s.ch.get("I0")
        if I0 is None or np.any(I0 <= 0) or s.E.size < 25:
            continue
        o = np.argsort(s.E)
        E, y = s.E[o], np.log(I0[o])
        w = min(21, (len(y) // 2) * 2 - 1)
        r = y - savgol_filter(y, w, 2)
        R.append(np.interp(Eg, E, r))
    if len(R) < 2:
        return []
    R = np.array(R)
    med = np.median(R, axis=0)
    noise = 1.4826 * np.median(np.abs(med - np.median(med)))
    dE = np.gradient(Eg)
    step_change = np.r_[False, np.abs(np.diff(dE)) > 0.3 * np.minimum(dE[1:], dE[:-1])]
    out = []
    for k in range(2, len(Eg) - 2):
        if not (med[k] < med[k - 1] and med[k] <= med[k + 1]):
            continue
        depth = -med[k]
        if depth < max(0.003, 6 * noise) or dE[k] > 1.0:
            continue
        if step_change[max(0, k - 2):k + 3].any() and depth < 0.01:
            continue                     # shallow dip at a region boundary: trend-filter artefact
        half = med[k] / 2
        j1 = k
        while j1 > 0 and med[j1] < half:
            j1 -= 1
        j2 = k
        while j2 < len(med) - 1 and med[j2] < half:
            j2 += 1
        frac = float(np.mean(R[:, k] < -0.5 * depth))
        out.append({"E_eV": float(Eg[k]), "depth": float(depth), "fwhm_eV": float(Eg[j2] - Eg[j1]),
                    "points": int(j2 - j1), "in_scans_frac": frac})
    out.sort(key=lambda d: -d["depth"])
    return out[:5]


def glitch_consistency(files, E_g, half_window=1.5):
    """Inflection anchors around a glitch: spread per file and bimodality."""
    per_file, allv = {}, []
    for f in files:
        v = []
        for s in f.scans:
            I0 = s.ch.get("I0")
            if I0 is None:
                continue
            a, _ = find_inflection_point(s.E, I0, [E_g - half_window, E_g + half_window])
            if np.isfinite(a):
                v.append(a)
        if v:
            per_file[f.name] = (float(np.mean(v)), float(np.std(v)), len(v))
            allv += v
    allv = np.array(allv)
    bimodal = False
    if allv.size > 6:
        c = allv - np.median(allv)
        lo, hi = c[c < -0.1], c[c > 0.1]
        bimodal = (lo.size > 0.15 * c.size and hi.size > 0.15 * c.size) or allv.std() > 0.08
    return per_file, {"n": int(allv.size), "std_eV": float(allv.std()) if allv.size else np.nan,
                      "bimodal": bool(bimodal)}


def survey(folder) -> dict:
    files, docs = collect(folder)
    return survey_files(files, docs, str(Path(folder).expanduser()))


def survey_files(files: list[FileInfo], docs: list[str] = (), folder: str = "") -> dict:
    """The survey of already-read files (ISAAC, PROVENANCE.md M2): one FileInfo per sample, which may pool the scans
    of several SPEC files (spots, repeats). ``survey(folder)`` is ``collect`` + this."""
    data = [f for f in files if f.scans]
    findings, warns = [], []
    rep = {"folder": folder, "docs": list(docs), "files": [], "findings": findings,
           "warnings": warns}
    if not data:
        warns.append("no XAS scans found")
        return rep
    fmt = sorted({f.fmt for f in data})
    rep["reader"] = fmt[0] if len(fmt) == 1 else fmt
    tcols = sorted({("sec" if "sec" in sc.ch else next((k for k in sc.ch if k.lower() in ("seconds", "time")), None))
                    for f in data if f.fmt == "spec" for sc in f.scans} - {None})
    if tcols:
        rep["time_column"] = tcols[0] if len(tcols) == 1 else tcols
    ecols = sorted({sc.energy_column for f in data if f.fmt == "spec" for sc in f.scans})
    if ecols:
        rep["energy_column"] = ecols[0] if len(ecols) == 1 else ecols
        if ecols != ["absev"]:
            findings.append(f"energy column: {', '.join(ecols)} (no 'absev' encoder column)")
    align = [f for f in data if f.role == "alignment" or (f.role is None and (
        re.search(r"align", f.name, re.I) or (f.n_all > 3 * max(1, len(f.scans)) and f.n_all > 30)))]
    samples = [f for f in data if f not in align]
    edge = identify_edge([s for f in samples[:12] for s in f.scans[:2]])
    rep["edge"] = edge
    if not edge:
        warns.append("no tabulated edge inside the scan range")
        return rep
    E0 = edge["E_edge_eV"]
    findings.append(f"edge: {edge['element']} {edge['core']} at {E0:.1f} eV (tabulated)")
    ch, votes = fluo_channel(samples, E0)
    rep["fluorescence_channel"] = {"name": ch, "votes": votes}
    findings.append(f"fluorescence channel: {ch} (largest edge contrast; votes {votes})")
    ax = axes_offset(samples)
    rep["absev_minus_energy"] = ax
    if ax and max(abs(ax["p5_eV"]), abs(ax["p95_eV"])) > 0.1:
        warns.append(f"SPEC 'energy' and 'absev' differ by {ax['median_eV']:+.2f} eV (5-95 %: "
                     f"{ax['p5_eV']:+.2f} .. {ax['p95_eV']:+.2f}); absev (encoder) is used. Check the "
                     "glitch / foil stays fixed on absev over the beamtime.")
    # per-file table + foil edges
    foil_hits = {}
    for f in data:
        t = [s.time for s in f.scans if s.time]
        Es = sorted({(round(float(s.E.min())), round(float(s.E.max())), s.E.size) for s in f.scans})
        fe = foil_edges(f.scans[len(f.scans) // 2], E0) if f.scans else {}
        strong = {k: v for k, v in fe.items() if abs(v["step"]) > 0.05 and np.isfinite(v["inflection_eV"])}
        foil_hits[f.name] = strong
        fluo_k, sig = _best_fluo(f.scans[0], E0)
        guess = "alignment" if f in align else (
            "foil" if FOIL_NAMES.search(f.name) or (strong and sig is None) else (
                "reference" if REF_NAMES.search(f.name) else "sample"))
        if f.role in ("sample", "reference", "foil"):
            guess = f.role                 # ISAAC M2: the caller's role wins over the name guess
        rep["files"].append({"name": f.name, "format": f.fmt, "n_xas": len(f.scans), "n_all": f.n_all,
                             "first": min(t).isoformat() if t else None, "grids": Es[:3],
                             "role_guess": guess, "foil_edges": strong})
    roles = {r["name"]: r["role_guess"] for r in rep["files"]}
    smp = [f for f in samples if roles[f.name] in ("sample", "reference")]
    foils = [f for f in samples if roles[f.name] == "foil"]
    in_scan = [f.name for f in smp if foil_hits.get(f.name)]
    rep["in_scan_foil_fraction"] = len(in_scan) / max(1, len(smp))
    # alignment log
    logs = [dict(l, file=f.name) for f in data for l in f.log]
    rep["calibration_log"] = logs
    for l in logs:
        findings.append(f"{l['file']}: {l['axis']} reset {l['from']} -> {l['to']} ({l['time']})")
    for f in align:
        for s in f.scans:
            fe = {k: v for k, v in foil_edges_any(s).items()}
            if fe:
                # ISAAC M5: an undated scan no longer crashes the survey (`None:%m-%d` raised TypeError)
                when = f"{s.time:%m-%d %H:%M}" if s.time else "undated"
                findings.append(f"{f.name} #{s.num} ({when}): edge scan, " +
                                ", ".join(f"{k} step {v['step']:+.2f} infl {v['inflection_eV']:.2f}"
                                          for k, v in fe.items()))
    # glitches (sample files only)
    gl = glitch_candidates(smp)
    rep["glitch_candidates"] = gl
    best_g = None
    for g in gl:
        if g["in_scans_frac"] > 0.8 and abs(g["E_eV"] - E0) > 3:
            best_g = g
            break
    if best_g:
        per_file, cons = glitch_consistency(smp, best_g["E_eV"])
        rep["glitch"] = {**best_g, **cons}
        means = np.array([v[0] for v in per_file.values()])
        rep["glitch"]["file_mean_range_eV"] = [float(means.min()), float(means.max())] if means.size else None
        findings.append(f"I0 glitch at {best_g['E_eV']:.2f} eV: depth {100 * best_g['depth']:.1f} %, "
                        f"FWHM {best_g['fwhm_eV']:.2f} eV, in {100 * best_g['in_scans_frac']:.0f} % of scans; "
                        f"inflection anchors std {1000 * cons['std_eV']:.0f} meV"
                        + (" - UNRELIABLE inflection (edge flipping / noise): use method shape" if cons["bimodal"] else ""))
    # foil files
    ftl = []
    for f in foils:
        for s in f.scans:
            fe = foil_edges(s, E0)
            for k, v in fe.items():
                if abs(v["step"]) > 0.3:
                    ftl.append({"file": f.name, "num": s.num, "time": s.time.isoformat() if s.time else None,
                                "ratio": k, "step": v["step"], "inflection_eV": v["inflection_eV"]})
    rep["foil_scans"] = ftl
    ts = [s.time for f in smp for s in f.scans if s.time]
    rep["first_sample_time"] = min(ts).isoformat() if ts else None
    rep["recommendation"] = recommend(rep, smp, foils, E0)
    cal = rep["recommendation"]["calibration"]
    if cal["mode"] == "glitch_I0":
        cmp = glitch_method_comparison(smp, cal)
        rep["glitch_method_scatter"] = cmp
        if cmp and cmp["model_meV"] is not None:
            use_model = cmp["shape_meV"] is None or cmp["model_meV"] <= 1.3 * cmp["shape_meV"]
            if use_model:
                cal["method"] = "model"
            rep["recommendation"]["why"].append(
                f"per-file anchor scatter: Gaussian-dip model {cmp['model_meV']:.1f} meV, shape fit "
                f"{cmp['shape_meV']:.1f} meV ({cmp['files']} files) -> method {cal['method']} (the model "
                "is template-free: no grid-phase bias for narrow glitches)")
    if cal["mode"] == "glitch_I0" and cal.get("method") == "model":
        dt = doublet_test(smp, rep["glitch"]["E_eV"])
        rep["glitch_doublet_test"] = dt
        if dt and dt["is_doublet"]:
            hw = round(dt["sep_eV"] / 2 + 2.5, 2)
            mid = dt["midpoint_eV"]
            cal["glitch_dips"] = 2
            cal["shape_window_eV"] = [round(mid - hw, 2), round(mid + hw, 2)]
            cal["window_eV"] = list(cal["shape_window_eV"])
            rep["recommendation"]["why"].append(
                f"the glitch is a DOUBLET (two dips {dt['sep_eV']:.2f} eV apart, fit ok on "
                f"{100 * dt['ok_frac']:.0f} % of scans): per-file scatter one-dip {dt['single_meV']:.0f} meV vs "
                f"two-dip midpoint {dt['doublet_meV']:.0f} meV -> glitch_dips: 2, window {cal['shape_window_eV']}")
    if cal.get("method") == "model" and int(cal.get("glitch_dips", 1)) == 2:
        scans_ws = [s for f in smp for s in f.scans[1:3]]
        ws = model_window_sensitivity(scans_ws, cal)
        rep["window_sensitivity_meV"] = ws
        if ws is not None:
            msg = f"window check (doublet): per-scan shifts change by {ws:.0f} meV (95th pct, common offset removed) when the window is widened/narrowed 25 %"
            (warns if ws > 20 else findings).append(msg + (" - choose the window by hand" if ws > 20 else ""))
    elif cal.get("method") == "model":
        # choose the half-width from the data: the widest window (<= the rule's) whose centres
        # stay within 20 meV when it is widened / narrowed 25 % (an absorber in the I0 path
        # gives a dip on an edge step, which the dip model only follows close to the peak)
        scans_ws = [s for f in smp for s in f.scans[1:3]]
        g0, w0 = rep["glitch"]["E_eV"], cal["shape_window_eV"]
        hw0 = (w0[1] - w0[0]) / 2
        best = None
        for hw in sorted({round(h, 2) for h in (hw0, 5, 4, 3, 2.5, 2.0, 1.5) if h <= hw0 + 1e-9}, reverse=True):
            trial = dict(cal, shape_window_eV=[round(g0 - hw, 2), round(g0 + hw, 2)])
            ws_ = model_window_sensitivity(scans_ws, trial)
            if ws_ is not None and (best is None or ws_ < best[1]):
                best = (trial["shape_window_eV"], ws_)
            if ws_ is not None and ws_ < 20:
                break
        if best and best[0] != w0:
            cal["shape_window_eV"] = best[0]
            rep["recommendation"]["why"].append(
                f"glitch window narrowed to {best[0]} (the {w0} window moved centres by more than 20 meV)")
        ws = best[1] if best else None
        rep["window_sensitivity_meV"] = ws
        if ws is not None:
            msg = f"window check: per-scan shifts change by {ws:.0f} meV (95th pct, common offset removed) when the window is widened/narrowed 25 %"
            (warns if ws > 20 else findings).append(msg + (" - choose the window by hand" if ws > 20 else ""))
    elif cal.get("method") == "shape" and cal["mode"] in ("glitch_I0", "ref_foil"):
        scans = [s for f in smp for s in f.scans[1:3]]
        ws = window_sensitivity(scans, cal)
        rep["window_sensitivity_meV"] = ws
        if ws is not None:
            msg = f"shape-window check: per-scan shifts change by {ws:.0f} meV (95th pct, common offset removed) when the window is widened/narrowed 25 %"
            (warns if ws > 20 else findings).append(msg + (" - choose the window by hand" if ws > 20 else ""))
    return rep


TRANSMISSION_NAME = re.compile(r"(?:^|[_\-\s.])trans(?:mission)?(?:$|[_\-\s.])", re.I)
#: measurement_mode thresholds (ISAAC, PROVENANCE.md M3)
MODE_FLUO_CONTRAST_MIN = 0.2      # (post - pre) / (|post| + |pre|) of IF/I0 across the edge: a fluorescence edge
MODE_TRANS_STEP_MIN = 0.02        # ln(I0/I1) step across the edge with the name saying transmission
MODE_TRANS_STEP_ALONE = 0.05      # ...and with no fluorescence edge at all (the name says nothing)


def measurement_mode(scans, E_edge: float, name: str = "") -> dict:
    """Is this sample measured in TRANSMISSION (mu = ln(I0/I1)) rather than fluorescence / HERFD (IF/I0)? The
    pipeline reduces IF/I0 only, and scope.md lists transmission-mode samples as NOT SUPPORTED, yet reduce() used
    to read a transmission file's IF column as if it were the measurement (ISAAC, PROVENANCE.md M3: a reference
    pellet named ``..._transmission`` in a real BL15-2 beamtime was reduced as HERFD).

    Evidence per scan (median over the scans): the fluorescence edge contrast of the best channel (``_best_fluo``)
    and the transmission step of ln(I0/I1) (I1 lit, not a dark chamber). ``transmission`` when the name says so
    and ln(I0/I1) has a step of at least MODE_TRANS_STEP_MIN, or when no channel shows a fluorescence edge
    (contrast < MODE_FLUO_CONTRAST_MIN) while ln(I0/I1) steps by MODE_TRANS_STEP_ALONE; ``fluorescence`` when a
    fluorescence edge is there and the name does not say transmission; else ``unknown``. Returns the mode and the
    numbers it was decided on."""
    fc, ts = [], []
    for sc in scans:
        E = np.asarray(sc.E, float)
        pre, post = E < E_edge - 10, E > E_edge + 30
        if pre.sum() < 2 or post.sum() < 2:
            continue
        k, sig = _best_fluo(sc, E_edge)
        I0 = sc.ch.get("I0")
        if sig is not None and I0 is not None:
            with np.errstate(all="ignore"):
                y = sig / I0
            a, b = np.nanmedian(y[pre]), np.nanmedian(y[post])
            c = (b - a) / (abs(b) + abs(a) + 1e-30)
            if np.isfinite(c):
                fc.append(float(c))
        I1 = sc.ch.get("I1")
        if I0 is not None and I1 is not None and np.nanmedian(I0) >= 50 and not _dark(I1, I0):
            with np.errstate(all="ignore"):
                t = np.log(np.asarray(I0, float) / np.asarray(I1, float))
            step = float(np.nanmedian(t[post]) - np.nanmedian(t[pre]))
            if np.isfinite(step):
                ts.append(step)
    contrast = float(np.median(fc)) if fc else None
    step = float(np.median(ts)) if ts else None
    says = bool(TRANSMISSION_NAME.search(name or ""))
    if says and step is not None and step >= MODE_TRANS_STEP_MIN:
        mode, basis = "transmission", "the name says transmission and ln(I0/I1) steps across the edge"
    elif (contrast is None or contrast < MODE_FLUO_CONTRAST_MIN) and step is not None and step >= MODE_TRANS_STEP_ALONE:
        mode, basis = "transmission", "no fluorescence edge, and ln(I0/I1) steps across the edge"
    elif contrast is not None and contrast >= MODE_FLUO_CONTRAST_MIN and not says:
        mode, basis = "fluorescence", "a fluorescence (IF/I0) edge, and the name does not say transmission"
    else:
        mode, basis = "unknown", "neither reading is clear"
    return {"mode": mode, "basis": basis, "fluorescence_contrast": contrast, "transmission_step": step,
            "name_says_transmission": says, "scans": len(fc) or len(ts),
            "thresholds": {"fluorescence_contrast_min": MODE_FLUO_CONTRAST_MIN,
                           "transmission_step_min": MODE_TRANS_STEP_MIN,
                           "transmission_step_alone": MODE_TRANS_STEP_ALONE}}


def foil_edges_any(s):
    """Transmission edges of any element inside an (alignment) energy scan."""
    out = {}
    for a, b in RATIOS:
        A, B = s.ch.get(a), s.ch.get(b)
        if A is None or B is None or np.nanmedian(A) < 50 or _dark(B, s.ch.get("I0")):
            continue
        with np.errstate(all="ignore"):
            y = np.log(A / B)
        n = max(2, len(y) // 8)
        step = float(np.nanmedian(y[-n:]) - np.nanmedian(y[:n]))
        if abs(step) < 0.05:
            continue
        infl, _ = find_inflection_point(s.E, y, [s.E.min() + 1, s.E.max() - 1], sign=1 if step > 0 else -1)
        out[f"ln({a}/{b})"] = {"step": step, "inflection_eV": float(infl)}
    return out


def glitch_window(g, cands):
    """Shape window around the glitch, clear of the other glitch candidates: half-width
    min(6 eV, 0.6 x distance to the nearest other dip), at least 2 FWHM."""
    others = [abs(c["E_eV"] - g["E_eV"]) for c in cands if abs(c["E_eV"] - g["E_eV"]) > 1.0]
    # wide enough for the dip (3 FWHM), never beyond 6 eV or into the next dip: a broad absorber
    # dip (S K: 1.8 eV FWHM) in a +-6 eV window drifts with the window (1.6 eV, BL4-3 2025-11)
    hw = min([6.0, max(3 * g.get("fwhm_eV", 0.5), 2.5)] + [0.6 * d for d in others])
    return [round(g["E_eV"] - hw, 2), round(g["E_eV"] + hw, 2)]


def window_sensitivity(scans, cal, n=30):
    """Per-scan shape shifts with the recommended window vs the window widened / narrowed by
    25 %: max change in meV (a robust window moves anchors by a few meV)."""
    from .pipeline import anchor_signal, fit_shape_shift
    w = cal["shape_window_eV"]
    c, h = (w[0] + w[1]) / 2, (w[1] - w[0]) / 2
    sc = [s for s in scans if s.ch.get("I0") is not None][:n]
    if len(sc) < 3:
        return None
    class _S:                                   # minimal adapter for anchor_signal
        def __init__(self, s):
            self.I0, self.Energy_eV = s.ch["I0"], s.E
            for k in ("I1", "I2"):
                setattr(self, k, s.ch.get(k))
    t = _S(sc[0])
    yt = anchor_signal(t, cal)
    out = []
    for f in (0.75, 1.25):
        ww = [c - f * h, c + f * h]
        d = []
        for s in sc[1:]:
            a = _S(s)
            y = anchor_signal(a, cal)
            d0, _ = fit_shape_shift(a.Energy_eV, y, t.Energy_eV, yt, w, max_shift=cal.get("max_shift_eV", 1.0))
            d1, _ = fit_shape_shift(a.Energy_eV, y, t.Energy_eV, yt, ww, max_shift=cal.get("max_shift_eV", 1.0))
            d.append(d1 - d0)
        d = np.array(d)
        out.append(float(np.percentile(np.abs(d - np.median(d)), 95)))
    return 1000 * max(out)


def glitch_method_comparison(files, cal, nfiles=12):
    """Median per-file scatter of the glitch anchor: Gaussian-dip model vs shape fit."""
    from .calib import fit_glitch_center
    from .pipeline import fit_shape_shift
    w = cal["shape_window_eV"]
    fl = [f for f in files if len(f.scans) >= 2][:nfiles]
    if not fl:
        return None
    t = fl[0].scans[0]
    yt = np.log(t.ch["I0"])
    sd_m, sd_s = [], []
    for f in fl:
        with np.errstate(all="ignore"):
            m = [fit_glitch_center(s.E, np.log(s.ch["I0"]), w)[0] for s in f.scans]
            sh = [fit_shape_shift(s.E, np.log(s.ch["I0"]), t.E, yt, w, max_shift=1.0)[0] for s in f.scans]
        m, sh = np.array(m, float), np.array(sh, float)
        if np.isfinite(m).sum() > 1:
            sd_m.append(np.nanstd(m))
        if np.isfinite(sh).sum() > 1:
            sd_s.append(np.nanstd(sh))
    return {"model_meV": 1000 * float(np.median(sd_m)) if sd_m else None,
            "shape_meV": 1000 * float(np.median(sd_s)) if sd_s else None, "files": len(fl)}


def _glitch_fit(cal):
    from .calib import fit_glitch_center, fit_glitch_doublet
    return fit_glitch_doublet if int(cal.get("glitch_dips", 1)) == 2 else fit_glitch_center


def doublet_test(files, g0, nfiles=12, hw=3.3):
    """Is the I0 glitch a doublet? Fit one- and two-dip models on up to nfiles files around g0.
    Doublet if the two-dip fit succeeds on >= 70 % of scans with a stable separation (std < 0.1 eV)."""
    from .calib import fit_glitch_center, fit_glitch_doublet
    w = [g0 - hw, g0 + hw]
    fl = [f for f in files if len(f.scans) >= 2][:nfiles]
    ok, sep, sd1, sd2, mids = 0, [], [], [], []
    n = 0
    for f in fl:
        c1, c2 = [], []
        for s in f.scans:
            I0 = s.ch.get("I0")
            if I0 is None or np.any(I0 <= 0):
                continue
            n += 1
            with np.errstate(all="ignore"):
                a, ia = fit_glitch_center(s.E, np.log(I0), w)
                b, ib = fit_glitch_doublet(s.E, np.log(I0), w)
            if np.isfinite(a):
                c1.append(a)
            if ib["ok"]:
                ok += 1
                c2.append(b)
                sep.append(ib["sep_eV"])
                mids.append(b)
        if len(c1) > 1:
            sd1.append(np.std(c1))
        if len(c2) > 1:
            sd2.append(np.std(c2))
    if n < 4 or not sep:
        return None
    res = {"ok_frac": ok / n, "sep_eV": float(np.median(sep)), "sep_std_eV": float(np.std(sep)),
           "single_meV": 1000 * float(np.median(sd1)) if sd1 else None,
           "doublet_meV": 1000 * float(np.median(sd2)) if sd2 else None,
           "midpoint_eV": float(np.median(mids))}
    # A stable separation is the evidence: on a single dip the two-dip fit loses a dip or runs
    # to a bound. Do not require a lower per-file scatter: a one-dip fit can latch onto the same
    # dip within most files and jump only in a few (BL6-2 2018: 10 meV per file, but six files
    # 250-390 meV off because it took the other dip).
    res["is_doublet"] = bool(res["ok_frac"] >= 0.7 and res["sep_std_eV"] < 0.1)
    return res


def model_window_sensitivity(scans, cal, n=30):
    fit_glitch_center = _glitch_fit(cal)
    w = cal["shape_window_eV"]
    c, h = (w[0] + w[1]) / 2, (w[1] - w[0]) / 2
    worst = []
    for f in (0.75, 1.25):
        d = []
        for s in [s for s in scans if s.ch.get("I0") is not None][:n]:
            with np.errstate(all="ignore"):
                a, ia = fit_glitch_center(s.E, np.log(s.ch["I0"]), w)
                b, ib = fit_glitch_center(s.E, np.log(s.ch["I0"]), [c - f * h, c + f * h])
            if ia["ok"] and ib["ok"] and np.isfinite(a) and np.isfinite(b):   # failed trial: no info
                d.append(b - a)
        if len(d) > 2:
            d = np.array(d)
            # a common change of all centres cancels in the shifts (ref - scan): use the spread
            worst.append(np.percentile(np.abs(d - np.median(d)), 95))
    return 1000 * float(max(worst)) if worst else None


def recommend(rep, smp, foils, E0) -> dict:
    why = []
    if rep["in_scan_foil_fraction"] >= 0.8:
        cnt = {}
        for f in rep["files"]:
            for k, v in f["foil_edges"].items():
                cnt.setdefault(k, []).append(abs(v["step"]))
        ratio = max(cnt, key=lambda k: (len(cnt[k]), np.median(cnt[k])))
        why.append(f"{100 * rep['in_scan_foil_fraction']:.0f} % of sample files carry a foil edge at the "
                   f"sample edge; {ratio} has it most often")
        cal = {"mode": "ref_foil", "ref_signal": ratio, "method": "shape",
               "window_eV": [round(E0 - 2, 1), round(E0 + 1.5, 1)],
               "shape_window_eV": [round(E0 - 9, 1), round(E0 + 21, 1)]}
    elif rep.get("glitch"):
        g = rep["glitch"]
        why.append(f"no in-scan foil; I0 glitch at {g['E_eV']:.2f} eV in {100 * g['in_scans_frac']:.0f} % of scans")
        if g.get("bimodal"):
            why.append(f"inflection anchors scatter {1000 * g['std_eV']:.0f} meV (edge flipping on a sharp "
                       "dip): the shape fit is required")
        cal = {"mode": "glitch_I0", "method": "shape",
               "window_eV": [round(g["E_eV"] - 1.2, 2), round(g["E_eV"] + 1.4, 2)],
               "shape_window_eV": glitch_window(g, rep.get("glitch_candidates", [])), "max_shift_eV": 1.0}
    elif rep["foil_scans"]:
        why.append("no in-scan reference (no foil edge, no glitch); separate foil scans exist: "
                   "foil timeline, linear in time")
        fs_all = sorted(rep["foil_scans"], key=lambda x: x["time"] or "")
        # one detector position: the ratio most foil files share (others: different geometry)
        by_ratio = {}
        for x in fs_all:
            by_ratio.setdefault(x["ratio"], set()).add(x["file"])
        ratio = max(by_ratio, key=lambda k: len(by_ratio[k]))
        use = [x for x in fs_all if x["ratio"] == ratio]
        for k, fl_ in by_ratio.items():
            for f_ in sorted(fl_ - by_ratio[ratio]):
                why.append(f"excluded {f_}: foil in another position ({k}); its edge need not match")
        # foils before the first sample scan: keep the last one (earlier ones may precede the
        # beamline's mono calibration)
        t0 = rep.get("first_sample_time")
        pre = [x for x in use if t0 and x["time"] and x["time"] < t0]
        if len(pre) > 1:
            keep_pre = pre[-1]["file"]
            for x in pre[:-1]:
                if x["file"] != keep_pre:
                    why.append(f"excluded {x['file']} ({x['inflection_eV']:.2f} eV): earlier than the last "
                               f"foil before the first sample ({keep_pre}, {pre[-1]['inflection_eV']:.2f} eV)")
            use = [x for x in use if x not in pre or x["file"] == keep_pre]
        fl = []
        for x in use:
            if not any(y["spec"] == x["file"] for y in fl):
                fl.append({"spec": x["file"], "ref_signal": ratio})
        cal = {"mode": "foil_timeline", "method": "shape", "foils": fl,
               "foil_window_eV": [round(E0 - 6, 1), round(E0 + 6, 1)],
               "shape_window_eV": [round(E0 - 8, 1), round(E0 + 24, 1)], "max_shift_eV": 2.0}
        an = [x["inflection_eV"] for x in use]
        if len(an) > 1:
            why.append(f"kept foil anchors span {np.ptp(an):.2f} eV over the beamtime (= drift + inflection noise)")
    else:
        why.append("NO energy reference found: energies are only as good as the beamline calibration")
        cal = {"mode": "none"}
    cal.setdefault("reference_sample", "earliest")
    cal.setdefault("reference_scan", "mean")
    return {"calibration": cal, "why": why}


def print_report(rep):
    print(f"survey of {rep['folder']}")
    if rep.get("docs"):
        print(f"  documents to read for curation: {', '.join(rep['docs'])}")
    print(f"  reader: {rep.get('reader')}")
    for f in rep["findings"]:
        print(f"  - {f}")
    if rep.get("files"):
        print("  files (first scan time, XAS scans / all, role guess, in-scan foil edges):")
        for f in rep["files"]:
            fe = "; ".join(f"{k} {v['step']:+.2f}" for k, v in f["foil_edges"].items())
            print(f"    {(f['first'] or '')[:16]:16s} {f['name'][:52]:52s} {f['n_xas']:3d}/{f['n_all']:<3d} "
                  f"{f['role_guess']:9s} {fe}")
    if rep.get("foil_scans"):
        print("  foil scans:")
        for fs in rep["foil_scans"]:
            print(f"    {(fs['time'] or '')[:16]:16s} {fs['file'][:40]:40s} #{fs['num']} {fs['ratio']} "
                  f"step {fs['step']:+.2f} inflection {fs['inflection_eV']:.2f} eV")
    if rep.get("recommendation"):
        r = rep["recommendation"]
        print("  RECOMMENDED calibration:")
        for k, v in r["calibration"].items():
            print(f"    {k}: {v}")
        for w in r["why"]:
            print(f"    because: {w}")
    for w in rep["warnings"]:
        print(f"  WARNING: {w}")


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def write_survey(rep, path):
    with open(path, "w") as fh:
        json.dump(_jsonable(rep), fh, indent=1, default=str)
