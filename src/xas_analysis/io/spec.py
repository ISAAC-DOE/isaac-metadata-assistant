"""SPEC file parsing (port of parse_spec.m) and XAS channel resolution (read_xas_scans.m).

Faithful to the MATLAB behaviour, including its quirks (noted inline), so outputs can be
compared stage by stage.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field

import numpy as np

from ..matlab_compat import mode_smallest

DEFAULT_COLUMN_MAP = {
    "Energy_eV": "absev",
    "IF": "vortDT",
    "I0": "I0",
    "I1": "I1",
    "I2": "I2",
    "sec": "sec",
}


@dataclass
class SpecScan:
    num: float = np.nan
    macro: list[str] = field(default_factory=list)
    macro_str: str = ""
    date: str = ""
    time_per_pt: float = np.nan
    motor_pos: np.ndarray = field(default_factory=lambda: np.empty(0))
    column_names: list[str] = field(default_factory=list)
    n_cols: float = np.nan
    data: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))


@dataclass
class SpecFile:
    filename: str = ""
    epoch: float = np.nan
    date: str = ""
    user: str = ""
    motor_names: list[str] = field(default_factory=list)
    scans: list[SpecScan] = field(default_factory=list)


def _scan_floats(s: str) -> list[float]:
    """MATLAB sscanf(s, '%f'): read numbers until the first token that is not one."""
    out = []
    for tok in s.split():
        try:
            out.append(float(tok))
        except ValueError:
            break
    return out


def _finalize(sc: SpecScan, pos_rows: list[str], data_rows: list[list[float]]) -> SpecScan:
    pos: list[float] = []
    for r in pos_rows:
        pos.extend(_scan_floats(r))
    sc.motor_pos = np.asarray(pos, float)
    if data_rows:
        widths = [len(r) for r in data_rows]
        target = mode_smallest(widths)
        keep = [w == target for w in widths]
        if not all(keep):
            warnings.warn(
                f"parse_spec: scan #{sc.num:g} has {keep.count(False)}/{len(data_rows)} rows "
                f"with non-standard width ({target} expected); dropping ragged rows.")
            data_rows = [r for r, k in zip(data_rows, keep) if k]
        sc.data = np.asarray(data_rows, float)
    else:
        sc.data = np.empty((0, 0))
    return sc


def parse_spec(path) -> SpecFile:
    """Parse a SPEC data file. '%' is accepted as a comment marker like '#'."""
    spec = SpecFile()
    motor_lines: list[str] = []
    in_scan = False
    sc = SpecScan()
    pos_rows: list[str] = []
    data_rows: list[list[float]] = []

    with open(path, "r", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line[0] == "%":
                line = "#" + line[1:]
            if line[0] == "#":
                tag = line.split(None, 1)[0]
                if tag == "#F":
                    spec.filename = line[2:].strip()
                elif tag == "#E":
                    v = _scan_floats(line[2:])
                    spec.epoch = v[0] if v else np.nan
                elif tag == "#D":
                    # quirk (as MATLAB): a #D after a scan, e.g. a second file header in a
                    # concatenated file, overwrites the previous scan's date
                    if in_scan:
                        sc.date = line[2:].strip()
                    else:
                        spec.date = line[2:].strip()
                elif tag == "#C":
                    spec.user = line[2:].strip()
                elif tag == "#S":
                    if in_scan:
                        spec.scans.append(_finalize(sc, pos_rows, data_rows))
                    sc, pos_rows, data_rows, in_scan = SpecScan(), [], [], True
                    body = line[2:].strip()
                    toks = body.split()
                    try:
                        sc.num = int(toks[0])
                    except (IndexError, ValueError):
                        sc.num = np.nan
                    if len(toks) >= 2:
                        sc.macro = toks[1:]
                        sc.macro_str = body[len(toks[0]):].strip()
                elif tag == "#T":
                    v = _scan_floats(line[2:])
                    sc.time_per_pt = v[0] if v else np.nan
                elif tag.startswith("#O") and not in_scan:
                    motor_lines.append(line[len(tag):].strip())
                elif tag.startswith("#P") and in_scan:
                    pos_rows.append(line[len(tag):].strip())
                elif tag == "#L" and in_scan:
                    # SPEC separates column names by two or more spaces
                    sc.column_names = [n for n in re.split(r"\s{2,}", line[2:].strip()) if n]
                elif tag == "#N" and in_scan:
                    v = _scan_floats(line[2:])
                    sc.n_cols = v[0] if v else np.nan
            elif in_scan:
                row = _scan_floats(line)
                if row:
                    data_rows.append(row)

    if in_scan:
        spec.scans.append(_finalize(sc, pos_rows, data_rows))

    for ml in motor_lines:
        spec.motor_names.extend(ml.split())
    nm = len(spec.motor_names)
    for s in spec.scans:
        if s.motor_pos.size and s.motor_pos.size >= nm:
            s.motor_pos = s.motor_pos[:nm]
    return spec


@dataclass
class XasScan:
    """One scan with its XAS channels resolved by column name (read_xas_scans.m)."""
    num: int
    macro: list[str]
    macro_str: str
    npts: int
    ncols: int
    date: str
    time_per_pt: float
    column_names: list[str]
    data: np.ndarray
    channels: dict[str, np.ndarray | None]
    channel_map: dict[str, float]

    def __getattr__(self, name):  # sc.Energy_eV, sc.IF, sc.I0, ...
        ch = self.__dict__.get("channels", {})
        if name in ch:
            return ch[name]
        raise AttributeError(name)


def _find_first_column(names: list[str], target: str) -> float:
    if not names or not target:
        return np.nan
    for i, n in enumerate(names):
        if n == target:
            return i
    t = target.lower()
    for i, n in enumerate(names):
        if n.lower() == t:
            return i
    return np.nan


def read_xas_scans(path, column_map: dict | None = None, scan_filter=None,
                   macro_filter=None, min_points: int = 5, quiet: bool = True) -> list[XasScan]:
    """Parse a SPEC file and return the XAS scans with named channels.

    column_map overrides DEFAULT_COLUMN_MAP entries (logical name -> SPEC column name).
    A channel whose column is absent is None (MATLAB: []).
    """
    cmap = dict(DEFAULT_COLUMN_MAP)
    for k, v in (column_map or {}).items():
        if k not in DEFAULT_COLUMN_MAP:
            warnings.warn(f'read_xas_scans: column_map field "{k}" is not a recognized XAS channel; ignoring.')
            continue
        if v:
            cmap[k] = v

    spec = parse_spec(path)
    if not spec.scans:
        raise ValueError(f"No scans found in {path}")

    out: list[XasScan] = []
    for s in spec.scans:
        if scan_filter is not None and len(scan_filter) and s.num not in list(scan_filter):
            continue
        if macro_filter:
            if not s.macro or s.macro[0] not in macro_filter:
                continue
        if s.data.size == 0 or s.data.shape[0] < min_points:
            continue
        chans, cm = {}, {}
        for logical, colname in cmap.items():
            idx = _find_first_column(s.column_names, colname)
            if np.isnan(idx) or idx >= s.data.shape[1]:
                chans[logical] = None
            else:
                chans[logical] = s.data[:, int(idx)].copy()
            cm[logical] = idx
        rec = XasScan(num=int(s.num), macro=s.macro, macro_str=s.macro_str,
                      npts=s.data.shape[0], ncols=s.data.shape[1], date=s.date,
                      time_per_pt=s.time_per_pt, column_names=s.column_names, data=s.data,
                      channels=chans, channel_map=cm)
        out.append(rec)
        if not quiet:
            f = lambda i: "--" if np.isnan(i) else f"{int(i) + 1:2d}"
            print(f"  scan #{rec.num:<4d}  {rec.npts:5d} pts x {rec.ncols:2d} cols   "
                  f"E:{f(cm['Energy_eV'])}  IF:{f(cm['IF'])}  I0:{f(cm['I0'])}   "
                  + " ".join(rec.macro[:3]))
    if not out:
        raise ValueError(f"All scans were filtered out ({len(spec.scans)} in file; "
                         "scan_filter / macro_filter / min_points too strict?)")
    return out
