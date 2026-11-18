"""Reader for the SSRL "EXAFS Data Collector" ASCII format (BL4-3, BL7-3, BL9-3, ...).

One scan per file (<stem>_A.001, _A.002, ...). Layout:

    SSRL   EXAFS Data Collector 4.0
    <date>
    PTS:  N COLS:  M
    <detector file> / <region file> / <beamline line> / ... / free comment lines
    Weights: / <M values>
    Offsets: / <M values>        dark offsets; the recorded columns are already corrected
                                 (I1/I2 read ~0 without beam through them, Lytle goes
                                 slightly negative), so they are reported, not re-applied
    Data:
    <M column names, one per line>
    <blank>
    <N rows x M values>

Channels: Energy_eV = "Achieved Energy", I0/I1/I2, IF = sum of the SCA windows of the
fluorescence detector (SCA1_1..SCA1_7 by default; `sca_channels` selects a subset), sec =
"Real time clock" (count time per point). No deadtime correction: the files carry the
input count rate (ICR1_*) but no output count rate.
"""
from __future__ import annotations

import glob
import re
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np

from .spec import XasScan


def parse_xdc(path) -> dict:
    lines = Path(path).read_text(errors="replace").splitlines()
    if not lines or "EXAFS Data Collector" not in lines[0]:
        raise ValueError(f"{path}: not an SSRL EXAFS Data Collector file")
    m = re.search(r"PTS:\s*(\d+)\s+COLS:\s*(\d+)", lines[2])
    if not m:
        raise ValueError(f"{path}: no PTS/COLS line")
    npts, ncols = int(m[1]), int(m[2])
    i = 3
    header = []
    while i < len(lines) and not lines[i].startswith("Weights:"):
        header.append(lines[i].rstrip())
        i += 1
    weights = np.array(lines[i + 1].split(), float)
    if not lines[i + 2].startswith("Offsets:"):
        raise ValueError(f"{path}: Offsets block not found")
    offsets = np.array(lines[i + 3].split(), float)
    i += 4
    while i < len(lines) and not lines[i].startswith("Data:"):
        i += 1
    names = [lines[i + 1 + k].strip() for k in range(ncols)]
    rows = []
    for ln in lines[i + 1 + ncols:]:
        v = ln.split()
        if len(v) == ncols:
            try:
                rows.append([float(x) for x in v])
            except ValueError:
                continue
    data = np.array(rows, float).reshape(-1, ncols)
    if data.shape[0] != npts:
        warnings.warn(f"{Path(path).name}: {data.shape[0]} rows, header says {npts} (aborted scan?)")
    date = lines[1].strip()
    return {"date": date, "header": header, "weights": weights, "offsets": offsets,
            "column_names": names, "data": data, "npts_header": npts,
            "detector": header[0].strip() if header else "", "region": header[1].strip() if len(header) > 1 else "",
            "comments": [h.strip() for h in header[2:] if h.strip()]}


def _xdc_time(date: str):
    try:
        return datetime.strptime(date.strip(), "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None


def read_xdc_scans(pattern, sca_channels=None, scan_filter=None, min_points: int = 5) -> list[XasScan]:
    """All files matching `pattern` (a glob, or a stem: '<stem>_A.*' is appended), one scan
    each; scan number = the numeric extension."""
    p = str(pattern)
    files = sorted(glob.glob(p)) if any(c in p for c in "*?[") else sorted(glob.glob(p + "_A.[0-9]*"))
    if not files:
        raise ValueError(f"read_xdc_scans: no files match {p}")
    out = []
    for f in files:
        num = int(re.search(r"\.(\d+)$", f)[1]) if re.search(r"\.(\d+)$", f) else len(out) + 1
        if scan_filter and num not in list(scan_filter):
            continue
        d = parse_xdc(f)
        if d["data"].shape[0] < min_points:
            continue
        col = {n: d["data"][:, k] for k, n in enumerate(d["column_names"])}
        sca = [n for n in d["column_names"] if n.startswith("SCA")]
        if sca_channels:
            sca = [n for n in sca if n in sca_channels or n.split("_")[-1] in map(str, sca_channels)]
        IF = np.sum([col[n] for n in sca], axis=0) if sca else None
        chans = {"Energy_eV": col.get("Achieved Energy", col.get("Requested Energy")),
                 "I0": col.get("I0"), "I1": col.get("I1"), "I2": col.get("I2"), "IF": IF,
                 "sec": col.get("Real time clock"), "Lytle": col.get("Lytle")}
        out.append(XasScan(num=num, macro=["xdc", d["region"]], macro_str=f"xdc {d['region']}",
                           npts=d["data"].shape[0], ncols=d["data"].shape[1], date=d["date"],
                           time_per_pt=float(np.nanmedian(col["Real time clock"])) if "Real time clock" in col else np.nan,
                           column_names=d["column_names"], data=d["data"], channels=chans,
                           channel_map={"IF": "+".join(sca), "file": f, "comments": d["comments"]}))
    if not out:
        raise ValueError(f"read_xdc_scans: all scans of {p} filtered out")
    return out
