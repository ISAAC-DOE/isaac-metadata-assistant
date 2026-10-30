"""Athena-first: read the scientist's Athena projects, match their groups to record groups,
and compare the scientist's normalisation with the ISAAC protocol's.

The scientist's Athena output is PREFERRED for the record; a disagreement is a review
item, never an override in either direction.

MATCHING RULE (``isaac.athena.match_by_name.v0``)
===============================================

A name is normalised: casefold; one trailing ``.txt``/``.dat``/``.xmu``/``.nor``/``.csv``
removed; runs of whitespace, ``-`` and ``.`` become ``_``. An Athena group's names are its
``label`` and its file name's basename. A record group's names are its members' run stems
(for an unread acquisition, its stem). An Athena group MATCHES a record group when one of
its names EQUALS a stem (exact), or is the stem followed by ``_`` and a scan-selection
suffix — digits and digit ranges (``5_6``, ``001``), or ``merge``/``mrg``/``avg``/
``average``/``mean``/``sum`` (+ anything) — (suffix match).

* an Athena group matching several record groups: an exact match wins over suffix matches;
  still several -> ambiguous, matched to none, and noted;
* several Athena groups for one record group: identical data (same energy+mu bytes) count
  once; otherwise a single merged one (Athena ``is_merge`` or a merge-word suffix) wins;
  otherwise ambiguous -> no match, and the candidates are noted.

The Athena normalisation is reproduced the way larch's own ``read_athena(do_preedge=True)``
does: ``pre_edge`` on the stored energy with the project's ``e0``, ``pre1``, ``pre2``,
``nor1``, ``nor2``, ``nnorm`` and ``flatten``. Comparisons are made in the scientist's
energy frame: stored energy + ``bkg_eshift``, E0 + ``bkg_eshift``.

TODO (bundle 1.2.0 ``processed_outputs[]``, NOT BUILT): the bundle now also carries the
scientists' exported Athena/Demeter XDI files (``.nor``, ``.xmu`` ...) as reference results,
each with at most one PROPOSED link to a run (``bundle.LINK_RULE_ID``) and, through it, a
record group. They are not fed into this comparison. Doing so honestly needs more than a
name match: (1) only a scientist-CONFIRMED link should count (a decision kind for
processed-output links does not exist yet; a proposed link is a suggestion); (2) an XDI
export carries the processed spectrum, not the project's ``pre1``/``nor1``/``nnorm``
parameters (those are present only when the file states ``Athena.*`` fields), so
:func:`compare` cannot re-run the scientist's normalisation from it; and (3) which column is
the normalised spectrum must come from the file's own ``Column.N``/column-header statement,
never from its extension. Until then the ``.prj`` path below is the only Athena comparison.
"""

from __future__ import annotations

import contextlib
import hashlib
import math
import os
import re
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

MATCH_RULE_ID = "isaac.athena.match_by_name.v0"
COMPARE_RULE_ID = "isaac.athena.compare.v0"

_EXT = re.compile(r"\.(txt|dat|xmu|nor|csv)$", re.IGNORECASE)
_SEP = re.compile(r"[\s\-.]+")
_MERGE_WORD = r"(merge|merged|mrg|avg|average|mean|sum)"
_SCAN_SUFFIX = re.compile(r"^(\d+(_\d+)*|" + _MERGE_WORD + r"\w*|scans?_?\d+(_\d+)*|\d+_?to_?\d+)$")
_HAS_MERGE_WORD = re.compile(r"(^|_)" + _MERGE_WORD + r"(_|$|\d)")


def normalise_name(name: str) -> str:
    base = PurePosixPath(str(name).replace("\\", "/")).name
    base = _EXT.sub("", base.strip())
    return _SEP.sub("_", base.casefold()).strip("_")


def _match_kind(names: Iterable[str], stem: str) -> str | None:
    best = None
    for n in names:
        if not n or not stem:
            continue
        if n == stem:
            return "exact"
        if n.startswith(stem + "_") and _SCAN_SUFFIX.match(n[len(stem) + 1 :]):
            best = "suffix"
    return best


# --- reading projects -------------------------------------------------------------------------


def load_project(path: Path, rel_path: str, source_id: str | None, np) -> tuple[list[dict], list[str]]:
    """The xmu groups of one Athena project, with the scientist's parameters. (entries, notes)."""
    from larch.io import AthenaProject

    notes: list[str] = []
    prj = AthenaProject()
    try:
        # larch prints notes ("nans seen") and needs a real file descriptor: devnull, not StringIO
        # (StringIO.fileno() raises io.UnsupportedOperation, an OSError, inside larch).
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            prj.read(str(path), do_preedge=True, do_bkg=False, do_fft=False)
    except Exception as exc:  # noqa: BLE001 - an unreadable project is a note, not a crash
        return [], [f"athena_unreadable:{rel_path}:{type(exc).__name__}"]
    out = []
    for gname, g in sorted(prj.groups.items()):
        energy = getattr(g, "energy", None)
        mu = getattr(g, "mu", None)
        if energy is None or mu is None or not hasattr(g, "norm"):
            notes.append(f"athena_group_not_xmu:{gname}")
            continue
        ap = getattr(g, "athena_params", None)
        bkg = getattr(ap, "bkg", None)
        # NEVER A NON-FINITE NUMBER: a project can carry "nan" text (larch reads it as a NaN float),
        # which is not a JSON number. Each such value becomes None and is NAMED in
        # ``non_finite_values`` (and on the result, run._athena_result) — never dropped silently.
        non_finite: list[str] = []

        def _p(obj, name):
            v = getattr(obj, name, None) if obj is not None else None
            try:
                f = float(v)
            except (TypeError, ValueError):
                return v
            if not math.isfinite(f):
                non_finite.append(f"params.{name}")
                return None
            return f

        params = {
            k: _p(bkg, k) for k in ("e0", "pre1", "pre2", "nor1", "nor2", "nnorm", "eshift", "flatten", "step", "fixstep", "z")
        }
        # A NON-FINITE bkg_eshift: the stored energies' frame is unknown. The group is KEPT (it is one of
        # the scientist's versions: dropping it would silently make the result-of-record choice), with
        # its identity intact, but nothing of it is placed on an energy axis (``energy_frame_known``):
        # no e0, no comparison, no curve file, no plot. Its result says so (ENERGY_FRAME_UNKNOWN_FLAG).
        frame_known = "params.eshift" not in non_finite
        if not frame_known:
            notes.append(f"athena_group_eshift_not_finite:{rel_path}:{gname}")
        eshift = (params["eshift"] or 0.0) if frame_known else 0.0
        channel_expr = {k: getattr(ap, k, None) for k in ("numerator", "denominator", "ln", "energy_string", "i0_string", "signal_string")} if ap is not None else {}
        e = np.asarray(energy, dtype=float)
        m = np.asarray(mu, dtype=float)
        e0_raw, step_raw = _finite(getattr(g, "e0", None)), _finite(getattr(g, "edge_step", None))
        if e0_raw is None:
            non_finite.append("e0_eV")
        if step_raw is None:
            non_finite.append("edge_step")
        is_merge = False
        try:
            is_merge = bool(int(getattr(ap, "is_merge", 0) or 0))
        except (TypeError, ValueError):
            pass
        out.append(
            {
                "prj_relative_path": rel_path,
                "prj_source_id": source_id,
                "group_name": gname,
                "label": str(getattr(g, "label", gname)),
                "filename": str(getattr(ap, "file", "") or getattr(g, "filename", "") or ""),
                "names": sorted({normalise_name(str(getattr(g, "label", gname))), normalise_name(str(getattr(ap, "file", "") or ""))} - {""}),
                "is_merge": is_merge,
                "energy": e + float(eshift),
                "mu": m,
                "norm": np.asarray(g.norm, dtype=float),
                "flat": np.asarray(getattr(g, "flat", g.norm), dtype=float),
                "energy_frame_known": frame_known,
                "e0_eV": (e0_raw + float(eshift)) if (e0_raw is not None and frame_known) else None,
                "edge_step": step_raw,
                "params": params,
                "non_finite_values": non_finite,
                "channel_expression": {k: (str(v) if v is not None else None) for k, v in channel_expr.items()},
                "data_hash": hashlib.sha256(e.tobytes() + m.tobytes()).hexdigest(),
            }
        )
    return out, notes


#: A version whose ``bkg_eshift`` is not a finite number: listed, never placed on an energy axis.
ENERGY_FRAME_UNKNOWN_FLAG = "athena_energy_frame_unknown"


def frame_known(entry: Mapping) -> bool:
    return entry.get("energy_frame_known", True) is not False


def _finite(x) -> float | None:
    """``float(x)`` when it is a finite number, else ``None`` (the caller names what was not)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _mean_or_none(values, np) -> float | None:
    """The mean, or ``None`` when any value is unknown (never a mean over what is left)."""
    return None if any(v is None for v in values) else _finite(np.mean(values))


def find_projects(bundle: Mapping) -> list[tuple[str, str | None]]:
    """(relative_path, source_id) of every ``.prj`` the bundle inventoried, sorted."""
    seen: dict[str, str | None] = {}
    for item in list(bundle.get("sources") or ()) + list(bundle.get("unread_files") or ()):
        rel = item.get("relative_path")
        if rel and str(rel).lower().endswith(".prj"):
            seen.setdefault(str(rel), item.get("source_id"))
    return sorted(seen.items())


# --- matching ---------------------------------------------------------------------------------


def _per_scan_set(pool: Sequence[Mapping], stems: Sequence[str], np) -> dict | None:
    """When the scientist kept ONE Athena group per scan file (no merge) — every candidate
    selects exactly one, distinct, scan of this record group, all in one project — the
    scientist's result is that SET. It is compared as the mean of the scientist's own
    per-scan normalised spectra (on the first group's grid), labelled as derived."""
    if np is None or len(pool) < 2 or len({c["prj_relative_path"] for c in pool}) != 1:
        return None
    if not all(frame_known(c) for c in pool):
        return None  # a curve in an unknown energy frame is never averaged: the versions stay listed
    sels = [scan_selection(c["label"], stems) for c in pool]
    if any(s is None or len(s) != 1 for s in sels) or len({s[0] for s in sels}) != len(sels):
        return None
    order = sorted(range(len(pool)), key=lambda i: sels[i][0])
    base = pool[order[0]]
    e = base["energy"]

    def _mean(key):
        rows = []
        for i in order:
            c = pool[i]
            y = np.interp(e, c["energy"], c[key])
            y[(e < c["energy"][0]) | (e > c["energy"][-1])] = np.nan
            rows.append(y)
        return np.nanmean(np.vstack(rows), axis=0)

    out = dict(base)
    out.update(
        {
            "label": f"{base['label']} [+{len(pool) - 1} per-scan groups]",
            "group_name": base["group_name"],
            "norm": _mean("norm"),
            "flat": _mean("flat"),
            "e0_eV": _mean_or_none([pool[i]["e0_eV"] for i in order], np),
            "edge_step": _mean_or_none([pool[i]["edge_step"] for i in order], np),
            "non_finite_values": sorted({v for i in order for v in pool[i].get("non_finite_values") or ()}),
            "per_scan_set": {
                "scans": [sels[i][0] for i in order],
                "labels": [pool[i]["label"] for i in order],
                "e0_eV": [pool[i]["e0_eV"] for i in order],
                "edge_step": [pool[i]["edge_step"] for i in order],
                "params": [pool[i]["params"] for i in order],
                "derived": "mean of the scientist's per-scan Athena normalisations (ISAAC-computed summary, not a scientist merge)",
            },
        }
    )
    return out


MAX_VERSIONS = 20
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def version_provenance(entry: Mapping, stems: Sequence[str]) -> dict:
    """What the scientist's own files STATE about one Athena version — file name, the years
    the project's path names, the group label, merge flag, scan selection and parameters.
    Nothing is ranked; no version is selected."""
    path = entry["prj_relative_path"]
    return {
        "prj_relative_path": path,
        "prj_file_name": PurePosixPath(path).name,
        "years_stated_in_path": sorted(set(_YEAR.findall(path))),
        "athena_label": entry["label"],
        "athena_group": entry["group_name"],
        "is_merge": entry.get("is_merge"),
        "scan_selection": scan_selection(entry["label"], stems),
        "params": entry.get("params"),
        "data_sha256_prefix": str(entry.get("data_hash") or "")[:16],
    }


def match(groups: Sequence[Mapping], entries: Sequence[Mapping], np=None) -> tuple[dict[str, dict], list[dict]]:
    return match_with_versions(groups, entries, np)[:2]


def match_with_versions(groups: Sequence[Mapping], entries: Sequence[Mapping], np=None) -> tuple[dict[str, dict], list[dict], dict[str, list[dict]]]:
    """group_id -> athena entry (unambiguous matches only), and notes on every ambiguity.

    Record groups with no scans take no part (measured: a scientist's exported ``x.dat``
    became a zero-scan run named like the real run, which made every match ambiguous).
    """
    stems = {g["group_id"]: [normalise_name(s) for s in g.get("_stems") or ()] for g in groups if g.get("_has_scans", True)}
    raw_stems = {g["group_id"]: list(g.get("_stems") or ()) for g in groups}
    notes: list[dict] = []
    by_group: dict[str, list[dict]] = {}
    for idx, entry in enumerate(entries):
        hits = []
        for gid, gstems in stems.items():
            kinds = [k for k in (_match_kind(entry["names"], s) for s in gstems) if k]
            if kinds:
                hits.append((gid, "exact" if "exact" in kinds else "suffix"))
        if not hits:
            continue
        exact = [h for h in hits if h[1] == "exact"]
        chosen = exact if exact else hits
        if len(chosen) > 1:
            notes.append(
                {
                    "code": "athena_group_matches_several_record_groups",
                    "athena_label": entry["label"],
                    "prj_relative_path": entry["prj_relative_path"],
                    "group_ids": sorted(h[0] for h in chosen),
                }
            )
            continue
        by_group.setdefault(chosen[0][0], []).append({**entry, "_match_kind": chosen[0][1], "_index": idx})
    matched: dict[str, dict] = {}
    versions: dict[str, list[dict]] = {}
    for gid, cands in by_group.items():
        uniq: dict[str, dict] = {}
        for c in cands:
            uniq.setdefault(c["data_hash"], c)
        pool = list(uniq.values())
        if len(pool) > 1:
            merged = [c for c in pool if c["is_merge"] or any(_HAS_MERGE_WORD.search(n) for n in c["names"])]
            if len(merged) == 1:
                pool = merged
        if len(pool) > 1:
            combined = _per_scan_set(pool, raw_stems.get(gid) or (), np)
            if combined is not None:
                pool = [{**combined, "_match_kind": "per_scan_set"}]
        if len(pool) == 1:
            matched[gid] = {**pool[0], "_candidates": len(cands), "_distinct": len(uniq)}
        else:
            notes.append(
                {
                    "code": "several_athena_groups_for_record_group",
                    "group_id": gid,
                    "candidates": [{"label": c["label"], "prj_relative_path": c["prj_relative_path"]} for c in pool][:20],
                }
            )
            versions[gid] = [{**c, "_match_kind": c.get("_match_kind")} for c in sorted(pool, key=lambda c: (c["prj_relative_path"], c["group_name"]))][:MAX_VERSIONS]
    return matched, notes, versions


_RANGE = re.compile(r"^(\d+)\s*-\s*(\d+)$")


def scan_selection(label: str, stems: Sequence[str]) -> list[int] | None:
    """Scan numbers a scientist's Athena label selects after the run stem (``..._5-6`` ->
    [5, 6]; ``..._1-3_7`` -> [1, 2, 3, 7]; XDAC ``...A.003`` -> [3]); None when the label
    states no selection."""
    raw = PurePosixPath(str(label)).name
    raw = _EXT.sub("", raw)
    low = raw.casefold()
    for stem in stems:
        st = str(stem).casefold()
        if not st or not low.startswith(st) or len(low) == len(st) or low[len(st)] not in "_-. ":
            continue
        rest = raw[len(st) + 1 :]
        out: list[int] = []
        for tok in re.split(r"[_,\s.]+", rest):
            if not tok:
                continue
            m = _RANGE.match(tok)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if b < a or b - a > 500:
                    return None
                out.extend(range(a, b + 1))
            elif tok.isdigit():
                out.append(int(tok))
            else:
                return None
        return sorted(set(out)) or None
    return None


# --- comparing --------------------------------------------------------------------------------


def compare(isaac: Mapping, entry: Mapping, params: Mapping, np) -> dict:
    """ISAAC protocol vs the scientist's Athena normalisation."""
    tol = params["athena"]
    flatten = entry["params"].get("flatten")
    quantity = "flat" if (flatten is None or float(flatten or 0) >= 0.5) else "norm"
    ref = {
        "prj_relative_path": entry["prj_relative_path"],
        "prj_source_id": entry["prj_source_id"],
        "athena_group": entry["group_name"],
        "athena_label": entry["label"],
        "match_rule": MATCH_RULE_ID,
        "match_kind": entry.get("_match_kind"),
    }
    out = {"athena_ref": ref, "rule_id": COMPARE_RULE_ID, "metrics": {}, "verdict": "not_comparable", "flags": [], "tolerances": dict(tol)}
    if not frame_known(entry):
        out["flags"].append(ENERGY_FRAME_UNKNOWN_FLAG)
        out["non_finite_values"] = list(entry.get("non_finite_values") or ())
        return out
    grid = isaac.get("grid")
    y = isaac.get(quantity)
    if grid is None or y is None:
        out["flags"].append("isaac_normalization_unavailable")
        return out
    ae, ay = entry["energy"], entry[quantity]
    lo, hi = max(float(grid[0]), float(ae[0])), min(float(grid[-1]), float(ae[-1]))
    sel = (grid >= lo) & (grid <= hi)
    npts = int(np.sum(sel))
    m = out["metrics"]
    m.update(
        {
            "compared_quantity": quantity,
            "overlap_points": npts,
            "overlap_eV": [lo, hi] if hi > lo else None,
            "e0_isaac_eV": isaac.get("e0_eV"),
            "e0_athena_eV": entry["e0_eV"],
            "e0_delta_eV": (isaac["e0_eV"] - entry["e0_eV"]) if isaac.get("e0_eV") is not None and entry["e0_eV"] is not None else None,
            "edge_step_isaac": isaac.get("edge_step"),
            "edge_step_athena": entry["edge_step"],
            "edge_step_ratio": (isaac["edge_step"] / entry["edge_step"]) if isaac.get("edge_step") and entry["edge_step"] else None,
        }
    )
    if npts < int(tol["min_overlap_points"]) or (hi - lo) < float(tol["min_overlap_eV"]):
        out["flags"].append("overlap_too_small")
        return out
    diff = y[sel] - np.interp(grid[sel], ae, ay)
    rms = float(np.sqrt(np.mean(diff**2)))
    m["rms_norm"] = rms if math.isfinite(rms) else None
    if m["rms_norm"] is None or m["e0_delta_eV"] is None:
        out["flags"].append("metric_not_finite")
        return out
    lo_r, hi_r = tol["edge_step_ratio_range"]
    if m["edge_step_ratio"] is None or not (lo_r <= m["edge_step_ratio"] <= hi_r):
        out["flags"].append("edge_step_scale_differs")
    agree = abs(m["e0_delta_eV"]) <= float(tol["agree_e0_delta_eV"]) and rms <= float(tol["agree_rms_norm"])
    out["verdict"] = "agree" if agree else "differs"
    if abs(m["e0_delta_eV"]) > float(tol["agree_e0_delta_eV"]):
        out["flags"].append("e0_differs")
    if rms > float(tol["agree_rms_norm"]):
        out["flags"].append("normalized_shape_differs")
    return out
