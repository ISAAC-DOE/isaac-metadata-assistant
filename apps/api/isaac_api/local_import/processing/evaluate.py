"""Evaluation harness: how ISAAC's draft protocol agrees with what scientists did in Athena.

Reads every ``processing/processing_results.json`` under a folder (one per bundle) and
reports, per bundle and overall: groups, QC verdicts, failures by cause, how many groups
matched an Athena group, the agree/differs/not_comparable counts, and the distributions
of |E0 delta|, normalised-mu RMS and edge-step ratio. Stdlib only.

    python -m isaac_api.local_import.processing.evaluate <folder> [--json]

Counts and summary statistics only: no sample names or spectra are printed.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Iterable, Mapping, Sequence

RESULTS_GLOB = "processing/processing_results.json"
_BINS = {
    "abs_e0_delta_eV": [0.25, 0.5, 1.0, 2.0, 5.0],
    "rms_norm": [0.01, 0.02, 0.05, 0.1, 0.2],
    "edge_step_ratio": [0.5, 0.8, 1.25, 2.0],
    "rms_norm_with_athena_params": [0.01, 0.02, 0.05, 0.1, 0.2],
}


def _hist(values: Sequence[float], edges: Sequence[float]) -> dict:
    out: dict[str, int] = {}
    lo = None
    for e in edges:
        label = f"<={e}" if lo is None else f"({lo},{e}]"
        out[label] = sum(1 for v in values if (lo is None or v > lo) and v <= e)
        lo = e
    out[f">{edges[-1]}"] = sum(1 for v in values if v > edges[-1])
    return out


def _dist(values: Sequence[float], edges: Sequence[float]) -> dict:
    if not values:
        return {"n": 0}
    qs = statistics.quantiles(values, n=4) if len(values) >= 2 else [values[0]] * 3
    return {"n": len(values), "min": min(values), "q1": qs[0], "median": statistics.median(values), "q3": qs[2], "max": max(values), "histogram": _hist(values, edges)}


def evaluate_results(payloads: Iterable[Mapping]) -> dict:
    rows = []
    for p in payloads:
        for key in ("processing_results", "unread_acquisition_results"):
            for r in p.get(key) or ():
                if r.get("source") != "isaac_protocol":
                    continue
                c = r.get("comparison") or {}
                m = c.get("metrics") or {}
                rows.append(
                    {
                        "bundle": p.get("source_root_label") or p.get("experiment_key"),
                        "group_id": r["group_id"],
                        "group_kind": r.get("group_kind"),
                        "qc_verdict": (r.get("qc") or {}).get("verdict"),
                        "failure": (r.get("failure") or {}).get("code"),
                        "matched": bool(c),
                        "comparison_verdict": c.get("verdict"),
                        "comparison_flags": c.get("flags") or [],
                        "e0_delta_eV": m.get("e0_delta_eV"),
                        "rms_norm": m.get("rms_norm"),
                        "edge_step_ratio": m.get("edge_step_ratio"),
                        "rms_norm_with_athena_params": m.get("rms_norm_with_athena_params"),
                        "athena_versions": len(r.get("athena_versions") or ()),
                    }
                )
    return {"rows": rows, "overall": _summary(rows), "by_bundle": {b: _summary([r for r in rows if r["bundle"] == b]) for b in sorted({r["bundle"] or "?" for r in rows})}}


def _count(rows: Sequence[Mapping], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        v = r.get(key)
        if v is not None:
            out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items()))


def _summary(rows: Sequence[Mapping]) -> dict:
    matched = [r for r in rows if r["matched"]]
    comparable = [r for r in matched if r["comparison_verdict"] in ("agree", "differs")]
    flags: dict[str, int] = {}
    for r in matched:
        for f in r["comparison_flags"]:
            flags[f] = flags.get(f, 0) + 1
    return {
        "groups": len(rows),
        "qc_verdicts": _count(rows, "qc_verdict"),
        "failures_by_cause": _count(rows, "failure"),
        "athena_matched": len(matched),
        "athena_versions_unselected": sum(1 for r in rows if r.get("athena_versions")),
        "comparison_verdicts": _count(matched, "comparison_verdict"),
        "comparison_flags": dict(sorted(flags.items())),
        "abs_e0_delta_eV": _dist([abs(r["e0_delta_eV"]) for r in comparable if r["e0_delta_eV"] is not None], _BINS["abs_e0_delta_eV"]),
        "rms_norm": _dist([r["rms_norm"] for r in comparable if r["rms_norm"] is not None], _BINS["rms_norm"]),
        "edge_step_ratio": _dist([r["edge_step_ratio"] for r in comparable if r["edge_step_ratio"] is not None], _BINS["edge_step_ratio"]),
        # Diagnostic: ISAAC's merged data normalised with the SCIENTIST's parameters. Small
        # values mean the data/channel/merge agree and the difference is parameter choice.
        "rms_norm_with_athena_params": _dist(
            [r["rms_norm_with_athena_params"] for r in comparable if r.get("rms_norm_with_athena_params") is not None],
            _BINS["rms_norm_with_athena_params"],
        ),
    }


def evaluate_folder(folder: Path | str) -> dict:
    folder = Path(folder)
    files = sorted(folder.rglob(RESULTS_GLOB)) if folder.is_dir() else []
    if (folder / RESULTS_GLOB).is_file() and (folder / RESULTS_GLOB) not in files:
        files.insert(0, folder / RESULTS_GLOB)
    payloads = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    out = evaluate_results(payloads)
    out["files"] = len(files)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="isaac-evaluate-processing", description=__doc__.split("\n\n")[0])
    ap.add_argument("folder")
    ap.add_argument("--json", action="store_true", help="print the full report (incl. per-group rows) as JSON")
    a = ap.parse_args(argv)
    rep = evaluate_folder(a.folder)
    if a.json:
        print(json.dumps(rep, indent=2))
        return 0
    print(f"{rep['files']} results file(s)")
    for name, s in [("OVERALL", rep["overall"]), *rep["by_bundle"].items()]:
        print(f"\n== {name}: {s['groups']} groups; QC {s['qc_verdicts']}; failures {s['failures_by_cause']}")
        print(f"   Athena matched {s['athena_matched']}: {s['comparison_verdicts']}  flags {s['comparison_flags']}  unselected-version groups {s['athena_versions_unselected']}")
        for k in ("abs_e0_delta_eV", "rms_norm", "edge_step_ratio", "rms_norm_with_athena_params"):
            d = s[k]
            if d.get("n"):
                print(f"   {k}: n={d['n']} median={d['median']:.4g} q1={d['q1']:.4g} q3={d['q3']:.4g} hist={d['histogram']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
