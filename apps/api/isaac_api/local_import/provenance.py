"""How an approved ``isaac.xas.v1`` curve was made, said in the record and in full in its evidence sidecar.

An end-to-end test on real data (17 Nov 2026) found the record kept only the normalised curve and E0, its
``generated_by`` named only the protocol version, and the energy reference, the per-scan shifts and the keep / drop
decisions with their reasons lived only in uncited files (params.json, scan_decisions.json, merged.csv). This module
says them, using ONLY fields the official schema has:

* :func:`generated_by` -- ``descriptors.outputs[].generated_by``: agent ``isaac.xas.v1``, a version naming the
  protocol, the adapter and the vendored engine, and :func:`summary` as its ``notes`` (plain English);
* :func:`merged_series` -- the merged RAW average (``merged.csv``) as a second ``measurement.series`` beside the
  normalised one (channel roles ``derived_signal`` / ``quality_monitor``, units ``arb`` / ``count``: both in the
  schema's enum and the portal's unit vocabulary);
* :func:`sidecar_block` -- the evidence sidecar's ``processing`` block: the result id, protocol, versions, energy
  reference evidence, the per-scan shift table, the decision table, the normalisation parameters, the excluded points
  and every output file with its sha256 (paths relative to the bundle).

Nothing here is computed anew: every number is read from the approved result as the engine stored it. The edge step
is said in the notes, not as a descriptor: the descriptor vocabulary (``descriptors.spectroscopy`` @ the pinned portal
commit) has no edge-step name, and a name outside it would be invented.

A result of any other protocol (``isaac.xas.v0``, an Athena reading) is composed exactly as before.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

V1_PROTOCOL_ID = "isaac.xas.v1"
#: the sidecar block's own format (bumped when its keys change)
SIDECAR_FORMAT = "isaac.processing_provenance.v1"
#: the vendored engine's provenance file, named in the record's version string
ENGINE_PROVENANCE_FILE = "src/xas_analysis/PROVENANCE.md"
#: merged.csv's columns (engine_xas.process_group_v1)
MERGED_COLUMNS = ("energy_eV", "mu_mean", "mu_stderr", "n_scans")
#: the merged series' channel notes
STDERR_NOTE = "Standard error of the mean at each energy where two or more scans contribute."
SCANS_AVERAGED_NOTE = ("How many scans contribute at each energy: fewer at the ends of the grid, where a scan's shift "
                       "onto the energy reference leaves it short of the grid, and where an I0 dropout point was left "
                       "out.")
#: why the edge step is not a descriptor
EDGE_STEP_NOT_A_DESCRIPTOR = ("the edge step is stated here, not as a descriptor: the ISAAC descriptor vocabulary has "
                              "no edge-step name")
#: the output files the sidecar lists, in this order (the rest after them)
ARTIFACT_ORDER = ("params", "scan_decisions", "merged", "normalized", "plot", "qc")

#: a drop reason code -> a few plain words (the reason's own sentence is in the sidecar)
_REASON_WORDS = {
    "before_stable_window": "the sample was still changing",
    "spot_differs": "a differing spot",
    "early_and_spot_differs": "early scans at another spot, differing in shape",
    "beam_damage_at_spot": "beam damage at the spot",
    "first_scan_settling": "a first scan still settling",
    "no_energy_reference": "no energy reference in the scan",
    "reference_fit_failed": "the reference fit failed",
    "coverage": "aborted (too short)",
    "anchor": "a failed anchor",
    "shape": "an off-shape scan",
    "ratio_shape": "a distorted normalised shape",
    "post_drift": "a distorted normalised shape",
    "dead_channel": "no edge at all",
}


def is_v1(result: Mapping) -> bool:
    return (result.get("protocol_id") == V1_PROTOCOL_ID and result.get("source") == "isaac_protocol"
            and isinstance(result.get("engine"), Mapping))


def version_text(result: Mapping) -> str:
    """``protocol 1.0.0; adapter isaac.xas.engine_adapter.v1; xas-analysis 0.1.0.dev0 (vendored, see ...)``."""
    eng = result.get("engine") or {}
    engine = f"{eng.get('engine') or 'xas-analysis'} {eng.get('engine_version') or '(version not recorded)'}"
    return (f"protocol {result.get('protocol_version')}; adapter {eng.get('adapter_rule_id') or '(not recorded)'}; "
            f"{engine} (vendored, see {ENGINE_PROVENANCE_FILE})")


def _num(v: Any, fmt: str) -> str | None:
    return format(v, fmt) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _span(w: Any) -> str | None:
    if isinstance(w, (list, tuple)) and len(w) == 2 and all(isinstance(x, (int, float)) for x in w):
        return f"{w[0]:g}-{w[1]:g} eV"
    return None


def _scan_names(rows: Sequence[Mapping]) -> str:
    """``run A scans 1, 3, 4; run B scan 2`` (a file name for a row with no run), the first few of each run."""
    by_run: dict[str, list[str]] = {}
    loose = []
    for x in rows:
        if x.get("run"):
            by_run.setdefault(str(x["run"]), []).append(str(x.get("scan")))
        else:
            loose.append(str(x.get("file") or x.get("scan_id")))
    parts = []
    for run, nums in by_run.items():
        shown = ", ".join(nums[:8]) + (f" and {len(nums) - 8} more" if len(nums) > 8 else "")
        parts.append(f"{run} scan{'s' if len(nums) > 1 else ''} {shown}")
    if loose:
        parts.append(", ".join(loose[:4]) + (f" and {len(loose) - 4} more" if len(loose) > 4 else ""))
    return "; ".join(parts)


def _reason_words(row: Mapping) -> str:
    if row.get("decided_by") == "scientist":
        return "the scientist's decision"
    reasons = row.get("reasons") or ()
    if not reasons:
        return "no reason recorded"
    code = str(reasons[0].get("code") or "")
    if code.startswith("logbook_"):
        return "a logbook note"
    return _REASON_WORDS.get(code, code.replace("_", " ") or "no reason recorded")


def _decisions_sentence(table: Mapping) -> str:
    rows = list(table.get("rows") or ())
    kept = [x for x in rows if x.get("decision") == "keep"]
    merged = [x for x in rows if x.get("merged")]
    dropped = [x for x in rows if x.get("decision") == "drop"]
    said = f"Scans: {len(kept)} of {len(rows)} kept ({len(merged)} merged), {len(dropped)} dropped"
    if dropped:
        by: dict[str, list[Mapping]] = {}
        for x in dropped:
            by.setdefault(_reason_words(x), []).append(x)
        parts = [f"{words}: {_scan_names(xs)}" for words, xs in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
        said += " (" + "; ".join(parts) + ")"
    said += f", by rule {table.get('rule_id')}."
    ov_keep = [x for x in kept if x.get("decided_by") == "scientist" and x.get("rule_decision") == "drop"]
    if ov_keep:
        said += f" {len(ov_keep)} kept on the scientist's word although the rule dropped them."
    unmerged = [x for x in kept if not x.get("merged")]
    if unmerged:
        said += f" {len(unmerged)} kept but not merged (no energy anchor)."
    return said


def _steps(result: Mapping) -> dict[str, Mapping]:
    return {s.get("step"): s for s in result.get("steps") or () if isinstance(s, Mapping)}


def summary(result: Mapping, *, merged_series_id: str | None = None, merged_stderr: str | None = None) -> str:
    """The compact plain-English story of the curve, for ``generated_by.notes``."""
    from .processing import engine_xas as EX

    story = EX.energy_story(result)
    nm = result.get("normalization") or {}
    merge = (_steps(result).get("merge") or {}).get("outcome") or {}
    out = result.get("outputs") or {}
    parts = [f"Processed from the raw scans by {V1_PROTOCOL_ID} (ISAAC processing result {result.get('result_id')}; "
             f"protocol status {result.get('protocol_status')}), approved by a scientist."]
    cal = story["absolute_calibration"]["statement"]
    parts.append("Energy: " + cal[:1].lower() + cal[1:] + " " + story["alignment"]["statement"])
    parts.append(_decisions_sentence(result.get("scan_decisions") or {}))
    grid = f" on the energy grid of kept scan {merge['grid_from_scan']}" if merge.get("grid_from_scan") else ""
    parts.append(f"Merge: uniform mean of the raw IF/I0 of the {merge.get('n_scans', '?')} merged scans{grid}"
                 + (f" (series {merged_series_id}" + {"all": ", with its standard error",
                                                       "partial": ", with its standard error where two or more scans "
                                                                  "contribute"}.get(merged_stderr, "") + ")"
                    if merged_series_id else "")
                 + "; normalised once afterwards (normalised curves are never merged).")
    w = nm.get("window_eV")
    windows = (f"pre-edge {w[0]:g}-{w[1]:g} eV, post-edge {w[2]:g}-{w[3]:g} eV"
               if isinstance(w, (list, tuple)) and len(w) == 4 else "windows not recorded")
    step = _num(out.get("edge_step"), ".4g")
    spread = _num(((nm.get("uncertainty") or {}).get("window_spread_of_A")), ".1%")
    tender = (nm.get("tender") or {}).get("tender")
    excl = ", ".join(_span(x) or str(x) for x in nm.get("exclude_eV") or ())
    parts.append(
        f"Normalisation: {str(nm.get('model') or '?').capitalize()} background + McMaster step "
        f"({nm.get('engine_function') or 'engine'}), "
        f"{nm.get('element') or '?'} {nm.get('edge') or '?'}"
        + (f" (tabulated edge {nm['E_edge_eV']:g} eV)" if isinstance(nm.get("E_edge_eV"), (int, float)) else "")
        + f", {windows}" + (", tender-fluorescence options" if tender else "")
        + (f", glitch windows kept out of the fit ({excl})" if excl else "")
        + "; the post-edge follows the McMaster cross-section (not flattened to 1)"
        + (f"; edge step {step} in raw IF/I0 units" + (f", spread {spread} over nearby windows" if spread else "")
           + f" ({EDGE_STEP_NOT_A_DESCRIPTOR})" if step else "") + ".")
    pts = ((result.get("point_exclusions") or {}).get("points")) or []
    if pts:
        scans = sorted({str(p.get("scan_id")) for p in pts})
        parts.append(f"Points excluded: {len(pts)} I0 dropout(s) in {len(scans)} scan(s) ({', '.join(scans[:4])}"
                     + (f" and {len(scans) - 4} more" if len(scans) > 4 else "")
                     + "), left out of that scan's contribution, never interpolated; the scans are kept.")
    else:
        parts.append("Points excluded: none (no I0 dropout in the merged scans).")
    parts.append("The full shift table, decision table, parameters and files (sha256) are in the record's evidence "
                 "file, under processing.")
    return " ".join(parts)


def generated_by(result: Mapping, *, merged_series_id: str | None = None, merged_stderr: str | None = None) -> dict:
    return {"agent": V1_PROTOCOL_ID, "version": version_text(result),
            "notes": summary(result, merged_series_id=merged_series_id, merged_stderr=merged_stderr)}


def bundle_relative(raw: Any) -> str | None:
    """``raw`` when it is a bundle-relative POSIX path (not empty, not absolute, no ``..``, no backslash, no drive
    letter), else ``None``: a path written into the sidecar or an export row never points outside the bundle."""
    from . import bundle as B

    safe = B._safe_relative(raw) if isinstance(raw, str) and raw.strip() else None
    if safe is None or safe in (".", "") or ":" in safe.split("/")[0]:
        return None
    return safe


UNSAFE_PATH_NOTE = "its relative_path is left out: not a bundle-relative path (absolute, '..', or a drive)"


def _read_columns(path: Path, names: Sequence[str]) -> dict[str, list[float | None]] | str:
    """The named columns of a processing CSV (``#`` banner lines skipped, header row naming them), a blank cell read
    as ``None``; or the REASON it was refused. Nothing is interpolated or guessed."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return f"the file could not be read ({type(exc).__name__})"
    rows = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if len(rows) < 2:
        return "the file holds no data rows"
    header = [c.strip() for c in rows[0].split(",")]
    if any(n not in header for n in names):
        return f"the header {header!r} does not name {list(names)!r}"
    idx = [header.index(n) for n in names]
    cols: dict[str, list[float | None]] = {n: [] for n in names}
    for k, row in enumerate(rows[1:], 1):
        cells = [c.strip() for c in row.split(",")]
        for n, i in zip(names, idx):
            if i >= len(cells):
                return f"data row {k} is short"
            try:
                cols[n].append(float(cells[i]) if cells[i] else None)
            except ValueError:
                return f"data row {k} has no number in the {n} column"
    return cols


def merged_series(group_id: str, path: Path) -> tuple[list[dict] | None, str, str | None]:
    """``(series, what was used, stderr)`` for the merged RAW average, or ``(None, why not, None)``.

    ``stderr``: ``"all"`` (the standard error is a channel of the merged series), ``"partial"`` (only some points
    have one: it is its own series, ``<group>_merged_stderr``, on those energies) or ``None`` (no point has one).
    A point where fewer than 2 scans contribute has NO standard error: the engine writes 0 there
    (``xas_analysis.average``: var / max(1, n - 1)), which is not a measured spread, so it is never written as one.
    """
    cols = _read_columns(path, MERGED_COLUMNS)
    if isinstance(cols, str):
        return None, f"not used: {cols}", None
    E, mu, err, n = (cols[c] for c in MERGED_COLUMNS)
    if any(v is None for v in E) or any(v is None for v in mu) or any(v is None for v in n):
        return None, "not used: a blank energy, mean or scan count", None
    defined = [i for i in range(len(E)) if n[i] >= 2 and err[i] is not None]
    stderr = "all" if len(defined) == len(E) else ("partial" if defined else None)
    channels = [{"name": "absorption", "unit": "arb", "role": "derived_signal", "values": mu,
                 "notes": "Raw fluorescence IF/I0, the uniform mean over the merged scans; not normalised."}]
    if stderr == "all":
        channels.append({"name": "absorption_stderr", "unit": "arb", "role": "quality_monitor", "values": err,
                         "notes": STDERR_NOTE})
    channels.append({"name": "scans_averaged", "unit": "count", "role": "quality_monitor", "values": n,
                     "notes": SCANS_AVERAGED_NOTE})
    out = [{
        "series_id": f"{group_id}_merged",
        "independent_variables": [{"name": "incident_energy", "unit": "eV", "values": E}],
        "channels": channels,
        "notes": ("The merged raw average this record's normalised curve was made from: each kept scan shifted onto "
                  "one beamtime energy reference and interpolated once onto one grid, then averaged (raw IF/I0). "
                  "It is normalised once, into the normalised series."
                  + {"all": "", "partial": f" Its standard error is series {group_id}_merged_stderr (only the "
                                           "energies where two or more scans contribute).",
                     None: " No standard error is given: one scan contributes at every energy."}[stderr]),
    }]
    if stderr == "partial":
        out.append({
            "series_id": f"{group_id}_merged_stderr",
            "independent_variables": [{"name": "incident_energy", "unit": "eV", "values": [E[i] for i in defined]}],
            "channels": [{"name": "absorption_stderr", "unit": "arb", "role": "quality_monitor",
                          "values": [err[i] for i in defined], "notes": STDERR_NOTE}],
            "notes": (f"The standard error of series {group_id}_merged, at the {len(defined)} of its {len(E)} energies "
                      "where two or more scans contribute. Where fewer than 2 scans contribute there is no standard "
                      "error, so those energies are left out (never written as 0)."),
        })
    said = {"all": "with its standard error and scan count",
            "partial": (f"with its scan count, and its standard error at the {len(defined)} of {len(E)} points where "
                        "two or more scans contribute"),
            None: "with its scan count; the standard error is not given (one scan contributes at every point)"}[stderr]
    return out, f"{len(E)} points, {said}", stderr


def normalized_series_note(result: Mapping, merged_series_id: str | None) -> str:
    nm = result.get("normalization") or {}
    return ("Normalised absorption: (raw - background) / edge step, from "
            + (f"the merged raw average (series {merged_series_id})" if merged_series_id else "the merged raw average")
            + f", normalised once by {V1_PROTOCOL_ID} ({nm.get('model') or '?'} background + McMaster step; the "
              "post-edge follows the McMaster cross-section, not flattened to 1).")


def _sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _decision_row(x: Mapping) -> dict:
    return {k: v for k, v in {
        "scan_id": x.get("scan_id"), "file": x.get("file"), "run": x.get("run"), "scan": x.get("scan"),
        "decision": x.get("decision"), "decided_by": x.get("decided_by"), "rule_decision": x.get("rule_decision"),
        "merged": bool(x.get("merged")), "reason_codes": [str(y.get("code")) for y in x.get("reasons") or ()],
        "reasons": [{k: y.get(k) for k in ("source", "code", "rule", "said", "evidence", "quote", "where") if k in y}
                    for y in x.get("reasons") or ()],
        "remarks": [{k: y.get(k) for k in ("source", "code", "said", "evidence") if k in y} for y in x.get("notes") or ()],
        "shift_eV": x.get("shift_eV"), "anchor_route": x.get("anchor_route"), "spot": x.get("spot"),
        "override": ({k: x["override"].get(k) for k in ("decision", "decision_id", "decided_by", "decided_utc", "note")
                      if k in x["override"]} if isinstance(x.get("override"), Mapping) else None),
        "cannot_merge": x.get("cannot_merge"),
    }.items() if v is not None}


def sidecar_block(result: Mapping, bundle_dir: Path, *, group_id: str, generated: Mapping | None,
                  merged_series_id: str | None = None, merged_stderr: str | None = None) -> dict:
    """The evidence sidecar's ``processing`` block for an approved v1 result (read from the result as stored)."""
    from .processing import engine_xas as EX
    from .records import contained_file

    eng = result.get("engine") or {}
    steps = _steps(result)
    table = result.get("scan_decisions") or {}
    shifts = result.get("scan_shifts") or {}
    ref = result.get("energy_reference") or {}
    files = list((result.get("outputs") or {}).get("files") or ())
    order = {r: i for i, r in enumerate(ARTIFACT_ORDER)}
    files.sort(key=lambda f: (order.get(f.get("role"), len(order)), str(f.get("relative_path"))))
    artifacts = []
    for f in files:
        rel = bundle_relative(f.get("relative_path"))
        src = contained_file(Path(bundle_dir), rel) if rel else None
        actual = _sha256_of(src) if src is not None else None
        artifacts.append({"role": f.get("role"), **({"relative_path": rel} if rel else {"note": UNSAFE_PATH_NOTE}),
                          "sha256": f.get("sha256"), "matches_file": actual is not None and actual == f.get("sha256")})
    story = EX.energy_story(result)
    return {
        "format": SIDECAR_FORMAT,
        "result_id": result.get("result_id"),
        "group_id": group_id,
        "run_id": result.get("run_id"),
        "protocol": {"id": result.get("protocol_id"), "version": result.get("protocol_version"),
                     "status": result.get("protocol_status")},
        "versions": {"protocol": result.get("protocol_version"), "adapter_rule_id": eng.get("adapter_rule_id"),
                     "engine": eng.get("engine"), "engine_version": eng.get("engine_version"),
                     "engine_source": eng.get("engine_source"), "engine_provenance": ENGINE_PROVENANCE_FILE,
                     "decision_rule_id": table.get("rule_id")},
        # exactly the record's generated_by: none when the record has no descriptors output (no numeric E0)
        **({"generated_by": dict(generated)} if generated else
           {"generated_by_note": ("the record has no descriptors output (no numeric E0), so no generated_by; the "
                                  "processing summary is below")}),
        "summary": summary(result, merged_series_id=merged_series_id, merged_stderr=merged_stderr),
        "energy": {
            "absolute_calibration": story["absolute_calibration"],
            "alignment": story["alignment"],
            "reference": {k: ref.get(k) for k in ("routes", "why", "statement", "mono_reset_lines", "survey_warnings",
                                                  "beamtime_fingerprint") if k in ref},
        },
        "scan_shifts": {"rows": [{k: x.get(k) for k in ("scan_id", "file", "route", "method", "anchor_eV", "shift_eV",
                                                        "ok", "fit") if k in x} for x in shifts.get("rows") or ()],
                        "mean_eV": shifts.get("mean_eV"), "spread_eV": shifts.get("spread_eV"),
                        "statement": shifts.get("statement")},
        "scan_decisions": {"rule_id": table.get("rule_id"), "counts": table.get("counts"),
                           "rows": [_decision_row(x) for x in table.get("rows") or ()],
                           "overrides_not_applied": list(table.get("overrides_not_applied") or ()),
                           "statement": table.get("statement")},
        **({"spots": result["spots"]} if result.get("spots") else {}),
        **({"dose_damage": result["dose_damage"]} if result.get("dose_damage") else {}),
        "merge": {k: (steps.get("merge") or {}).get(k) for k in ("params", "outcome", "flags")},
        "normalization": {k: v for k, v in (result.get("normalization") or {}).items()},
        "excluded_points": (dict(result["point_exclusions"]) if result.get("point_exclusions")
                            else {"points": [], "statement": "No point was excluded (no I0 dropout in the merged scans)."}),
        "outputs": {"e0_eV": (result.get("outputs") or {}).get("e0_eV"),
                    "edge_step": (result.get("outputs") or {}).get("edge_step"),
                    "edge_step_note": EDGE_STEP_NOT_A_DESCRIPTOR,
                    "points": (result.get("outputs") or {}).get("points")},
        "qc": {k: (result.get("qc") or {}).get(k) for k in ("verdict", "reasons", "metrics")},
        "measurement_mode": (result.get("measurement_mode") or {}).get("mode"),
        "channel": {k: (result.get("channel_choice") or {}).get(k) for k in ("energy", "mode", "signal_name", "i0")},
        "artifacts": artifacts,
        "artifacts_relative_to": ("the bundle directory; export copies each file beside the record, under "
                                  "<record id>.artifacts/<relative_path>"),
    }
