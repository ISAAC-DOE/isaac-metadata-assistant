"""Draft recipe from a survey (xas-analysis recipe init).

The draft is a starting point to review, never a finished recipe: roles are guessed from file
names, no scan is excluded, and the curation the logbook asks for (dropped scans, spots, flags)
is left to the user. The header lists the survey findings and the documents to read.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

from .survey import survey


def norm_range(E0, Emin, Emax):
    """Pre-edge up to E0 - (5..10) eV, post-edge from E0 + 60 eV to 10 eV before the end."""
    gap = max(5.0, min(10.0, 0.25 * (E0 - Emin)))
    return [round(Emin + 1, 1), round(E0 - gap, 1), round(E0 + 60, 1), round(Emax - 10, 1)]


def draft_recipe(folder, rep=None, output_dir="reduced"):
    rep = rep or survey(folder)
    if not rep.get("recommendation"):
        raise ValueError("survey found nothing to reduce: " + "; ".join(rep["warnings"]))
    files = [f for f in rep["files"] if f["role_guess"] in ("sample", "reference")]
    grids = Counter(tuple(f["grids"][-1]) for f in files if f["grids"])
    modal = grids.most_common(1)[0][0] if grids else None
    cal = dict(rep["recommendation"]["calibration"])
    notes = []
    if cal.get("reference_sample") == "earliest" and modal:
        # the reference file also supplies the energy grid: keep the earliest file (closest to
        # the beamline calibration) unless its grid fails to cover the common range
        first = min(files, key=lambda f: f["first"] or "9")
        g = first["grids"][-1]
        if g[0] > modal[0] + 5 or g[1] < modal[1] - 5:
            ok = [f for f in files if f["grids"] and f["grids"][-1][0] <= modal[0] + 5
                  and f["grids"][-1][1] >= modal[1] - 5]
            alt = min(ok, key=lambda f: f["first"] or "9")
            cal["reference_sample"] = alt["name"]
            notes.append(f"reference_sample {alt['name']}: the earliest file ({first['name']}, grid "
                         f"{g[0]}-{g[1]} eV) does not cover the common range {modal[0]}-{modal[1]} eV")
    E0 = rep["edge"]["E_edge_eV"]
    Emin, Emax = (modal[0], modal[1]) if modal else (E0 - 50, E0 + 300)
    rng = norm_range(E0, Emin, Emax)
    if rng[3] - rng[2] < 50:
        notes.append(f"post-edge window only {rng[3] - rng[2]:.0f} eV: edge jumps are window-sensitive")
    r = {"data_root": rep["folder"]}
    if rep.get("reader") == "ssrl_xdc":
        r["reader"] = "ssrl_xdc"
    r["samples"] = [{"spec": f["name"], "name": f["name"], "output_name": f["name"], "scans": [],
                     "outliers": [], "role": f["role_guess"]} for f in files]
    r["calibration"] = cal
    r["energy_grid"] = "reference"
    r["averaging"] = {"weights": "uniform", "min_scans": 1}
    r["screening"] = {"anchor_mad": 5, "shape_mad": 6,
                      "window_eV": [round(E0 - 10, 1), round(E0 + 45, 1)]}
    r["normalize"] = {"element": rep["edge"]["element"], "core": rep["edge"]["core"], "range": rng,
                      "model": "victoreen"}
    r["outputs"] = {"output_dir": output_dir, "save_per_scan": False, "save_avg": True,
                    "save_diagnostic": True}
    ch = (rep.get("fluorescence_channel") or {}).get("name")
    r["column_map"] = {"IF": ch} if ch and rep.get("reader") == "spec" and ch != "vortDT" else {}
    ec = rep.get("energy_column")
    if rep.get("reader") == "spec" and isinstance(ec, str) and ec != "absev":
        r["column_map"]["Energy_eV"] = ec       # e.g. BL6-2 2018/2019: 'mono' (no absev column)
    tc = rep.get("time_column")
    if rep.get("reader") == "spec" and isinstance(tc, str) and tc != "sec":
        r["column_map"]["sec"] = tc             # e.g. 'Seconds' 
    lines = [f"DRAFT recipe from `xas-analysis survey` ({datetime.now():%Y-%m-%d %H:%M}). REVIEW BEFORE USE:",
             "roles are guessed from file names; no scan is excluded; curate from the logbook.",
             f"folder: {rep['folder']}"]
    if rep.get("docs"):
        lines.append("read for curation: " + ", ".join(rep["docs"]))
    lines += [f"survey: {x}" for x in rep["findings"]]
    lines += [f"calibration because: {x}" for x in rep["recommendation"]["why"]]
    lines += [f"WARNING: {x}" for x in rep["warnings"]] + [f"NOTE: {x}" for x in notes]
    hdr = "".join(f"# {ln}\n" for ln in lines)
    return r, hdr


def write_draft(folder, out, rep=None):
    r, hdr = draft_recipe(folder, rep)
    Path(out).write_text(hdr + yaml.safe_dump(r, sort_keys=False, width=200))
    return r
