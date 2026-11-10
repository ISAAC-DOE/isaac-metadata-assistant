"""The scientists' QUICK MERGES (bundle 1.11.0) compared with ISAAC's own merge — a ROUGH REFERENCE, never truth.

WHAT IS COMPARED (``isaac.processed_output.quick_merge_compare.v0``, :data:`RULE_ID`). A processed output kept by the
engine's own classification (``bundle.ENGINE_ORIGIN_RULE_ID``: a headerless file whose every line is two numbers) with
a proposed link (``bundle.LEGACY_LINK_RULE_ID``) to a run of a record group. The match is THAT stored link, never a
name match here. Measured on a real BL15-2 beamtime: 32 such files in a ``MERGE/`` folder; the scientist said these
beamline merges "could be not robust or rigorous enough", so the comparison is labelled a rough reference: it is never
``preferred_for_record``, never the result of record, and moves no verdict, flag or id of ISAAC's own result (it is
written on the ISAAC result under :data:`RESULT_KEY`, outside every hashed output file).

THE COLUMNS. The file names none. Column 1 is read as energy in eV ONLY when it is strictly monotonic and lies inside
the group's energy range (ISAAC's grid, :data:`ENERGY_RANGE_TOLERANCE_EV` either side); column 2 as the signal. Both
are recorded as assumptions. Otherwise nothing is compared (``not_comparable``, with the reason).

ALREADY NORMALISED (pre-edge mean ~0 and post-edge mean ~1, within :data:`NORMALIZED_TOLERANCE`, over ISAAC's own
pre- and post-edge windows): compared AS STORED, edge step 1, never re-fitted.

NOT NORMALISED: (1) the raw signal against ISAAC's merged mu (median ratio and the relative residual after that
ratio); (2) the scientist's curve normalised with ISAAC's OWN parameters (E0, pre1/pre2, norm1/norm2, nnorm), said
so, and compared with ISAAC's normalised curve; (3) when the group has at most :data:`MAX_SUBSET_SCANS` scans and
EXACTLY ONE subset of them rebuilds the raw curve (relative residual at most :data:`REBUILD_RELATIVE_RMS` after a
scale), that subset is named as a HINT: an ``exclude_scans`` params-file snippet, never applied.
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .. import bundle as B
from . import core as C

RULE_ID = "isaac.processed_output.quick_merge_compare.v0"
#: the key on ISAAC's own processing result (``processing_result`` allows extra properties)
RESULT_KEY = "scientist_quick_merges"
ROLE = "rough_reference"
ENERGY_RANGE_TOLERANCE_EV = 1.0
NORMALIZED_TOLERANCE = 0.1
MIN_WINDOW_POINTS = 3
MAX_SUBSET_SCANS = 10
#: a subset "rebuilds" the curve when, after one scale, the residual is at most this fraction of the curve's range.
#: Measured on a real BL15-2 beamtime: the mean of the very scans a beamline merge holds, interpolated as ISAAC
#: interpolates them, differs from that merge by 2e-4 to 6e-4 of its range; another subset's mean differs by scan
#: noise, well above it. A subset is named only when it is the ONLY one under this bound.
REBUILD_RELATIVE_RMS = 1e-3
_LABEL = ("A rough reference: the scientists' quick merge at the beamline, which they say could be not robust or "
          "rigorous enough. Never preferred for the record and never treated as truth.")


def linked_quick_merges(bundle: Mapping, group: Mapping) -> list[tuple[Mapping, Mapping]]:
    """``[(processed output, its link)]`` of the engine-classified outputs whose STORED link names a run of ``group``."""
    keys = set(group.get("member_run_keys") or ()) - set(group.get("context_run_keys") or ())
    out = []
    for po in bundle.get("processed_outputs") or ():
        if not B.is_engine_classified(po):
            continue
        for link in po.get("proposed_links") or ():
            if link.get("rule_id") == B.LEGACY_LINK_RULE_ID and link.get("run_key") in keys:
                out.append((po, link))
    return out


def _read(root: Path | None, f: Mapping, np) -> tuple[Any, Any, str | None]:
    """``(column 1, column 2, None)`` of one file, or ``(None, None, why)``."""
    from ..readers import two_column
    from .run import _resolve_source, sha256_file

    rel = str(f.get("relative_path") or "")
    path = _resolve_source(root, rel) if root else None
    if path is None or not path.is_file():
        return None, None, "the file was not found under the source folder given to `isaac process`"
    if f.get("sha256") and sha256_file(path) != f["sha256"]:
        return None, None, "the file's bytes are not the ones imported (sha256 differs)"
    try:
        rows = two_column.read(path).rows
    except (ValueError, OSError) as exc:
        return None, None, f"it could not be read as two numeric columns ({type(exc).__name__})"
    pairs = [(r[0], r[1]) for r in rows if len(r) >= 2 and r[0] is not None and r[1] is not None
             and math.isfinite(r[0]) and math.isfinite(r[1])]
    if len(pairs) < 2:
        return None, None, "it holds fewer than two rows of two finite numbers"
    return np.array([p[0] for p in pairs], dtype=float), np.array([p[1] for p in pairs], dtype=float), None


def _window(e, y, lo, hi, np):
    sel = (e >= lo) & (e <= hi)
    return (float(np.mean(y[sel])), int(np.sum(sel))) if int(np.sum(sel)) >= MIN_WINDOW_POINTS else (None, int(np.sum(sel)))


def _rms(d, np) -> float | None:
    v = float(np.sqrt(np.mean(d ** 2))) if d.size else float("nan")
    return v if math.isfinite(v) else None


def _scaled_residual(y, ref, np) -> tuple[float | None, float | None]:
    """``(median ratio y/ref, rms(y - ratio*ref) / range(y))`` over the points where ``ref`` is finite and non-zero."""
    ok = np.isfinite(ref) & (ref != 0)
    if int(np.sum(ok)) < 2:
        return None, None
    ratio = float(np.median(y[ok] / ref[ok]))
    span = float(np.max(y[ok]) - np.min(y[ok]))
    if not math.isfinite(ratio) or span <= 0:
        return (ratio if math.isfinite(ratio) else None), None
    rms = _rms(y[ok] - ratio * ref[ok], np)
    return ratio, (rms / span if rms is not None else None)


def _subset_hint(e, y, M, grid, used_entries: Sequence[Mapping], inputs: Sequence[Mapping], group_id: str, np) -> dict | None:
    from .run import exclude_hint, exclusion_name

    n = int(M.shape[0])
    if n < 1 or n > MAX_SUBSET_SCANS:
        return {"tried": False, "reason": f"the group has {n} scans; subsets are tried only for 1 to {MAX_SUBSET_SCANS}"}
    fits = []
    with np.errstate(all="ignore"):
        for k in range(1, n + 1):
            for sub in itertools.combinations(range(n), k):
                mean = np.nanmean(M[list(sub)], axis=0)
                ok = np.isfinite(mean)
                if int(np.sum(ok)) < 2:
                    continue
                ref = np.interp(e, grid[ok], mean[ok], left=np.nan, right=np.nan)
                _, resid = _scaled_residual(y, ref, np)
                if resid is not None and resid <= REBUILD_RELATIVE_RMS:
                    fits.append((sub, resid))
    names = [exclusion_name(u, inputs) for u in used_entries]
    out: dict = {"tried": True, "subsets_tried": 2 ** n - 1, "subsets_that_rebuild": len(fits),
                 "tolerance_relative_rms": REBUILD_RELATIVE_RMS, "applied": False}
    if len(fits) != 1:
        out["statement"] = ("No single subset of the group's scans rebuilds this curve, so no scan is named."
                            if not fits else f"{len(fits)} subsets of the group's scans rebuild this curve, so none is named.")
        return out
    sub, resid = fits[0]
    used = [names[i] for i in sub]
    left_out = [names[i] for i in range(n) if i not in sub]
    out.update(scans_that_rebuild=used, scans_not_in_it=left_out, relative_rms=resid)
    if not left_out:
        out["statement"] = f"Exactly one subset rebuilds this curve: all {n} scans ISAAC merged."
    else:
        out["exclude_scans_snippet"] = exclude_hint(group_id, left_out)
        out["statement"] = (f"HINT ONLY, never applied: exactly one subset of the group's {n} scans rebuilds this curve "
                            f"({', '.join(used)}); it leaves out {', '.join(left_out)}. "
                            + out["exclude_scans_snippet"])
    return out


def compare_one(po: Mapping, link: Mapping, *, group: Mapping, root: Path | None, grid_ok, mean, nm: Mapping, M, grid,
                used_entries: Sequence[Mapping], inputs: Sequence[Mapping], params: Mapping, np, xafs) -> dict:
    f = (po.get("files") or [{}])[0]
    out: dict = {
        "rule_id": RULE_ID,
        "processed_output_id": po.get("processed_output_id"),
        "relative_path": f.get("relative_path"),
        "source_id": f.get("source_id"),
        "matched_by": {"rule_id": link.get("rule_id"), "run_id": link.get("run_id"), "run_key": link.get("run_key"),
                       "status": link.get("status")},
        "role": ROLE,
        "preferred_for_record": False,
        "treated_as_truth": False,
        "assumptions": [],
        "verdict": "not_comparable",
        "metrics": {},
        "statement": _LABEL,
    }
    e, y, why = _read(root, f, np)
    if why:
        out["reason"] = f"Not compared: {why}."
        return out
    d = np.diff(e)
    if np.all(d < 0):
        e, y = e[::-1], y[::-1]
    elif not np.all(d > 0):
        out["reason"] = "Not compared: column 1 is not strictly monotonic, so it is not read as an energy."
        return out
    lo, hi = float(grid_ok[0]), float(grid_ok[-1])
    if e[0] < lo - ENERGY_RANGE_TOLERANCE_EV or e[-1] > hi + ENERGY_RANGE_TOLERANCE_EV:
        out["reason"] = (f"Not compared: column 1 spans {e[0]:g} to {e[-1]:g}, outside the group's energy range "
                         f"{lo:g} to {hi:g} eV (±{ENERGY_RANGE_TOLERANCE_EV:g}), so it is not read as an energy.")
        return out
    out["assumptions"] = [
        f"column 1 is read as energy in eV: it is strictly monotonic and lies inside the group's energy range "
        f"({lo:g} to {hi:g} eV, ±{ENERGY_RANGE_TOLERANCE_EV:g})",
        "column 2 is read as the merged signal (mu); the file names neither column",
    ]
    tol = params["athena"]
    rp = nm["resolved_params"]
    e0 = float(nm["e0_eV"])
    pre_lo = e0 + (rp.get("pre1") if rp.get("pre1") is not None else -math.inf)
    pre_hi = e0 + (rp.get("pre2") if rp.get("pre2") is not None else 0.0)
    post_lo = e0 + (rp.get("norm1") if rp.get("norm1") is not None else 0.0)
    post_hi = e0 + (rp.get("norm2") if rp.get("norm2") is not None else math.inf)
    pre_mean, pre_n = _window(e, y, pre_lo, pre_hi, np)
    post_mean, post_n = _window(e, y, post_lo, post_hi, np)
    normalized = (pre_mean is not None and post_mean is not None and abs(pre_mean) <= NORMALIZED_TOLERANCE
                  and abs(post_mean - 1.0) <= NORMALIZED_TOLERANCE)
    m = out["metrics"]
    m.update(points=int(e.size), energy_eV=[float(e[0]), float(e[-1])], pre_edge_mean=pre_mean, pre_edge_points=pre_n,
             post_edge_mean=post_mean, post_edge_points=post_n, e0_isaac_eV=e0, edge_step_isaac=nm.get("edge_step"))
    try:
        found = float(xafs.find_e0(e, y))
        m["e0_found_in_it_eV"] = found if math.isfinite(found) else None
    except Exception:  # noqa: BLE001 - an E0 that cannot be found is said as null
        m["e0_found_in_it_eV"] = None
    sel = (grid_ok >= e[0]) & (grid_ok <= e[-1])
    npts = int(np.sum(sel))
    m["overlap_points"] = npts
    if npts < int(tol["min_overlap_points"]) or (min(hi, e[-1]) - max(lo, e[0])) < float(tol["min_overlap_eV"]):
        out["reason"] = "Not compared: the overlap with ISAAC's merged curve is too small."
        return out
    if normalized:
        out["normalization"] = "already_normalized"
        out["assumptions"].append(
            f"already normalised (pre-edge mean {pre_mean:.3g}, post-edge mean {post_mean:.3g} over ISAAC's own windows): "
            "compared as stored, edge step 1, never re-fitted")
        sci_norm = y
        m["edge_step_scientist"] = 1.0
    else:
        out["normalization"] = "normalized_with_isaac_parameters"
        ratio, resid = _scaled_residual(y, np.interp(e, grid_ok, mean, left=np.nan, right=np.nan), np)
        out["raw_comparison"] = {"median_ratio_to_isaac_merged_mu": ratio, "relative_rms_residual": resid,
                                 "statement": "Its raw signal against ISAAC's merged mu, after one median scale."}
        p = {**params, "normalize": {**params["normalize"], "e0": e0, "pre1": rp.get("pre1"), "pre2": rp.get("pre2"),
                                     "norm1": rp.get("norm1"), "norm2": rp.get("norm2"), "nnorm": rp.get("nnorm")}}
        try:
            snm = C.normalize(e, y, p, np, xafs)
        except C.StepError as exc:
            out["reason"] = f"Not compared: normalising it with ISAAC's own parameters failed ({exc.code})."
            return out
        out["assumptions"].append(
            "not normalised: normalised here with ISAAC's OWN parameters (E0 "
            f"{e0:g} eV, pre1 {rp.get('pre1')}, pre2 {rp.get('pre2')}, norm1 {rp.get('norm1')}, norm2 {rp.get('norm2')}, "
            f"nnorm {rp.get('nnorm')}), not the scientist's")
        sci_norm = snm["norm"]
        m["edge_step_scientist"] = snm["edge_step"]
        out["scan_subset_hint"] = _subset_hint(e, y, M, grid, used_entries, inputs, group["group_id"], np)
    isaac_norm = np.interp(e, grid_ok, nm["norm"], left=np.nan, right=np.nan)
    ok = np.isfinite(isaac_norm)
    rms = _rms(sci_norm[ok] - isaac_norm[ok], np)
    m["compared_quantity"] = "norm"
    m["rms_norm"] = rms
    if rms is None:
        out["reason"] = "Not compared: the difference is not finite."
        return out
    e0_delta = (e0 - m["e0_found_in_it_eV"]) if m.get("e0_found_in_it_eV") is not None else None
    m["e0_delta_eV"] = e0_delta
    agree = rms <= float(tol["agree_rms_norm"]) and (e0_delta is None or abs(e0_delta) <= float(tol["agree_e0_delta_eV"]))
    out["verdict"] = "agree" if agree else "differs"
    out["tolerances"] = {k: tol[k] for k in ("agree_rms_norm", "agree_e0_delta_eV", "min_overlap_points", "min_overlap_eV")}
    return out


def compare_group(group: Mapping, ctx: Any, *, grid_ok, mean, nm: Mapping, M, grid, used_entries: Sequence[Mapping],
                  inputs: Sequence[Mapping]) -> list[dict]:
    """Every linked quick merge of ``group`` compared with ISAAC's result (empty when none is linked)."""
    out = []
    for po, link in linked_quick_merges(ctx.bundle or {}, group):
        try:
            out.append(compare_one(po, link, group=group, root=ctx.root, grid_ok=grid_ok, mean=mean, nm=nm, M=M, grid=grid,
                                   used_entries=used_entries, inputs=inputs, params=ctx.params, np=ctx.np, xafs=ctx.xafs))
        except Exception as exc:  # noqa: BLE001 - a reference that cannot be compared never fails ISAAC's result
            out.append({"rule_id": RULE_ID, "processed_output_id": po.get("processed_output_id"), "role": ROLE,
                        "preferred_for_record": False, "treated_as_truth": False, "verdict": "not_comparable",
                        "reason": f"Not compared: {type(exc).__name__}.", "statement": _LABEL})
    return out
