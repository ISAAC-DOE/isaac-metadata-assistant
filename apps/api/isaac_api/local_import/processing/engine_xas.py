"""Processing protocol ``isaac.xas.v1``: the vendored xas-analysis reduction engine (``src/xas_analysis``, Oscar's
validated package, PROVENANCE.md there) plus this ISAAC adapter.

WHAT RUNS HERE. Groups whose data the engine's own scope covers (``xas_analysis/skill/scope.md``): SSRL hard-XAS
fluorescence / HERFD read from SPEC files (BL15-2 and others) or SSRL EXAFS Data Collector files (BL4-3). Everything
else, transmission samples (mu = ln(I0/I1)), other formats, alignment groups, stays on ``isaac.xas.v0``, and that
result says why (:data:`ENGINE_KEY` ``{"protocol_id": "isaac.xas.v0", "reason": ...}``).

THE ORDER (the engine's own, ``xas_analysis/skill/SKILL.md`` "Order of operations"): per scan, anchor -> shift
(beamtime reference anchor - scan anchor) -> ONE interpolation onto the group's grid; then the scan decisions; then the
raw mu (IF/I0) of the KEPT scans is averaged; the average is normalised ONCE (Victoreen + McMaster, ``mback_xrs``,
constrained background). Normalised data are never merged (Angel and Krish, 17 Nov 2026).

ONCE PER BEAMTIME (:func:`prepare`): the engine's survey (``xas_analysis.survey.survey_files``) over every group's
scans picks the energy reference (an in-scan foil in transmission when the sample scans carry one, else the I0
glitch, else a foil timeline, else none), its anchor method and window, and reads the ``mono reset`` lines. The
reference is the engine's convention: the EARLIEST group (closest in time to the staff's foil calibration of the mono
at the start of the beamtime), the MEAN anchor of its scans. Every scan of every group is aligned to that ONE
reference, never to its own sample's edge.

THE SCAN DECISIONS (:data:`DECISION_RULE_ID`, :func:`decide_scans`): the skill DECIDES which scans are kept and which
dropped, by this documented rule, never as a proposal waiting on a person; every decision carries its reasons and
evidence, is shown, and a scientist can override it (``decide --decision set_scan_decision``). An intensity drop alone
never drops a scan.

The scientist still approves each processed curve before it goes into a record (the existing approval gate).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import statistics
import tempfile
import warnings
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .. import bundle as B
from . import core as C
from .channels import MODE_FLUORESCENCE

PROTOCOL_ID = "isaac.xas.v1"
PROTOCOL_VERSION = "1.0.0"
PROTOCOL_STATUS = "draft_unreviewed"
ENGINE_NAME = "xas-analysis"
ENGINE_SOURCE = "src/xas_analysis (vendored; PROVENANCE.md)"
ADAPTER_RULE_ID = "isaac.xas.engine_adapter.v1"
DECISION_RULE_ID = "isaac.xas.scan_decision.v1"
#: the record-group decision a scientist overrides one scan's keep / drop with
SCAN_DECISION = "set_scan_decision"
SCAN_DECISION_VALUES = ("keep", "drop")
#: result keys (a processing result allows extra properties)
ENGINE_KEY = "engine"
DECISIONS_KEY = "scan_decisions"
SHIFTS_KEY = "scan_shifts"
REFERENCE_KEY = "energy_reference"
NORMALIZATION_KEY = "normalization"
LOGBOOK_KEY = "logbook_notes"
#: the payload key of the beamtime pass (survey, reference, windows)
BEAMTIME_KEY = "engine_beamtime"
#: the formats the engine reads (``readers.py`` format ids) -> what they are
ENGINE_FORMATS = {"spec_columns": "SPEC", "ssrl_xdac": "SSRL EXAFS Data Collector"}
V0_FALLBACK = "isaac.xas.v0"

#: screening (the engine's ``screen_report``, report-only): its recipe defaults (recipe_init.draft_recipe)
SCREENING = {"anchor_mad": 5, "shape_mad": 6, "min_coverage": 0.9}
SCREEN_WINDOW_EV = (-10.0, 45.0)        # relative to the tabulated edge (recipe_init: E0-10 .. E0+45)
#: a shape flag whose rms is at most this many times the scan's OWN point-to-point noise is noise (fewer counts),
#: not a different shape: noise is an intensity effect, and an intensity drop alone never drops a scan (rule 3)
SHAPE_NOISE_FACTOR = 2.0
#: a dead-channel flag drops the scan only when the scan shows no edge at all (edge step under this many times its
#: own point noise): then there is no spectrum, which is not "less intensity"
DEAD_EDGE_SNR_MIN = 2.0
#: |shift| above this (eV) is a failed anchor, not a mono drift (the mono is foil-calibrated at the start; the
#: engine's max_shift_eV defaults: 1 eV for a glitch, 2 eV for a foil)
MAX_SHIFT_EV = {"glitch_I0": 1.0, "ref_foil": 2.0, "foil_timeline": 2.0, "none": 0.0}
#: normalisation window variants for the uncertainty note (normalization.md: "window choice: A spread 9-15 %")
WINDOW_VARIANTS = {"pre_hi": (-10.0, 0.0), "post_lo": (0.0, 15.0, 25.0), "post_hi": (-50.0, 0.0)}
WINDOW_SPREAD_WARN = 0.20
POST_LEVEL_RANGE = (0.0, 2.0)          # core.POST_EDGE_LEVEL_RANGE: norm / McMaster mu over the post-edge window
EDGE_MIN_NOISE_MULTIPLE = 5.0          # core.EDGE_MIN_NOISE_MULTIPLE
DROP_REASON = "dropped_by_scan_decision"

DECISION_RULE = {
    "rule_id": DECISION_RULE_ID,
    "statement": (
        "Every scan gets keep or drop, with its reasons and evidence. A scan is DROPPED when (a) a logbook scan note "
        "says so (exclude, start_from, keep_only; a note read from the logbook as 'inferred' applies too, marked "
        "so; a 'flag' note changes nothing and is shown); or (b) the stability analysis "
        "(isaac.xas.scan_selection_proposal.v0) puts it before the stable window (the sample was still changing); "
        "or (c) the engine's screening flags it: aborted or low coverage (under 90 % of the group's grid), a failed "
        "anchor (no fit, a shift beyond the limit, or more than 5 robust sigmas from the group's median, floor 30 "
        "meV), an off-shape scan (its IF/I0, scaled to the group's median, departs more than 6 robust sigmas and 1.5 "
        "times the median, and more than twice its own counting noise), or a dead channel that shows no edge at "
        "all. Otherwise it is KEPT. An intensity drop alone never drops a scan: a weaker or noisier scan is kept "
        "and said. A scientist's set_scan_decision on a scan overrides all of this, and is shown as theirs."),
    "sources": {"logbook": "a logbook scan note (bundle scan_notes)",
                "stability": "isaac.xas.scan_selection_proposal.v0 (before the stable window)",
                "screening": "xas-analysis screen_report (report-only) + this rule's intensity guard",
                "input": "the scan could not be read or formed (its skip reason)",
                "params_file": "the params file's exclude_scans",
                "scientist": "a set_scan_decision decision"},
}

_DATE = re.compile(r"([A-Z][a-z]{2} [A-Z][a-z]{2} +\d{1,2} \d\d:\d\d:\d\d \d{4})")


# --- small helpers ----------------------------------------------------------------------------------------------


def engine_version() -> str | None:
    try:
        import xas_analysis

        return getattr(xas_analysis, "__version__", None)
    except Exception:  # noqa: BLE001
        return None


def _f(x) -> float | None:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def _scan_time(header_lines: Sequence[str] | None) -> datetime | None:
    for line in header_lines or ():
        m = _DATE.search(str(line))
        if m:
            try:
                return datetime.strptime(re.sub(r" +", " ", m.group(1)), "%a %b %d %H:%M:%S %Y")
            except ValueError:
                continue
    return None


class _Sc:
    """The attributes the engine's anchor functions read (``pipeline.make_anchor_fn``), from one scan record."""

    def __init__(self, rec: Mapping):
        self.Energy_eV = rec["E"]
        self.IF, self.I0, self.I1, self.I2 = rec["IF"], rec["I0"], rec.get("I1"), rec.get("I2")
        self.num = rec["num"]
        self.date = rec["time"].strftime("%a %b %d %H:%M:%S %Y") if rec.get("time") else ""


def scan_notes_for(bundle: Mapping, run_id: str) -> tuple[list[dict] | None, str | None]:
    """``(notes, None)`` from the bundle's logbook scan notes (``isaac_api.local_import.scan_notes``), or ``(None,
    why)`` when this build has no such reader: then no note is applied, and the result says so."""
    try:
        from ..scan_notes import scan_notes_for_run  # type: ignore[import-not-found]
    except ImportError:
        return None, ("this build has no logbook scan-notes reader (isaac_api.local_import.scan_notes), so no logbook "
                      "note was applied")
    try:
        return list(scan_notes_for_run(bundle, run_id) or ()), None
    except Exception as exc:  # noqa: BLE001 - notes that cannot be read are said, never a failure
        return None, f"the logbook scan notes could not be read ({type(exc).__name__}: {exc})"[:300]


def scientist_scan_decisions(bundle: Mapping, group_id: str) -> dict[str, dict]:
    """``{scan id: the latest set_scan_decision naming it}`` for one group (later decisions win)."""
    out: dict[str, dict] = {}
    for d in bundle.get("scientist_decisions") or ():
        if d.get("decision") != SCAN_DECISION or (d.get("target") or {}).get("kind") != "record_group":
            continue
        if (d.get("target") or {}).get("id") != group_id:
            continue
        v = d.get("value") if isinstance(d.get("value"), Mapping) else {}
        if v.get("decision") not in SCAN_DECISION_VALUES:
            continue
        for sid in v.get("scans") or ():
            out[str(sid)] = {"decision": v["decision"], "decision_id": d.get("decision_id"),
                             "decided_by": (d.get("decided_by") or {}).get("name"), "note": d.get("note"),
                             "decided_utc": d.get("decided_utc")}
    return out


# --- reading a group --------------------------------------------------------------------------------------------


def read_group(g: Mapping, ctx) -> dict:
    """Every scan of one group, read with v0's own reader, channel choice and BL15-2 energy rule (hash-checked
    against the bundle), as the arrays the engine works on. ``scope`` says whether the engine covers it."""
    from . import run as R

    np, params = ctx.np, ctx.params
    out: dict = {"group_id": g["group_id"], "role": g.get("role", "sample"), "inputs": [], "recs": [],
                 "stems": [], "scope": None, "formats": []}
    scans, stems, sel = R.group_scans(g, ctx.runs_by_key)
    out["stems"] = stems
    if not scans or g.get("group_kind") in ("unread_acquisition", "generic_run"):
        out["scope"] = "no scans in a record group the engine reads"
        return out
    exclude = list((getattr(ctx, "exclusions", None) or {}).get(g["group_id"]) or ())
    shared: dict = {}
    for s in scans:
        shared[s.get("source_id")] = shared.get(s.get("source_id"), 0) + 1
    tables = []
    run_of = {s.get("source_id"): s.get("run_key") for s in scans}
    for s in scans:
        entry = {"source_id": s.get("source_id"), "scan": s.get("scan_index"), "relative_path": s.get("relative_path"),
                 "channel": None, "used": False, "run_key": s.get("run_key")}
        out["inputs"].append(entry)
        named = R._excluded_as(entry, exclude)
        if named is not None:
            entry.update(skip_reason=R.EXCLUDED_REASON, excluded_as=named)
            continue
        table, why = R._read_scan_table(s, ctx, shared)
        if table is None:
            entry["skip_reason"] = why
            continue
        entry["format"] = table.format_id
        if table.error:
            entry["skip_reason"] = f"unreadable:{table.error}"
            continue
        tables.append((entry, table))
    out["formats"] = sorted({str(e.get("format")) for e, _ in tables})
    if not tables:
        out["scope"] = "no readable scan"
        return out
    if out["role"] == "alignment":
        out["scope"] = "an alignment group (motor and foil scans): not a sample spectrum the engine reduces"
        return out
    if any(f not in ENGINE_FORMATS for f in out["formats"]):
        out["scope"] = (f"format {', '.join(f for f in out['formats'] if f not in ENGINE_FORMATS)} is not one the engine "
                        f"reads (it reads {', '.join(ENGINE_FORMATS.values())})")
        return out
    role = out["role"]
    choice = None
    for _e, t in tables:
        c = R.choose_channels(t, params=params, role=role, bl15_selection=sel, **R.bl15_2_kw(t, ctx))
        if R._formed(c):
            choice = c
            break
    if choice is None:
        out["scope"] = "no absorption channel could be formed (v0 says why)"
        return out
    choice = R._absev_first(choice, tables, params, role, sel, ctx)
    out["choice"] = choice
    if choice.mode != MODE_FLUORESCENCE:
        out["scope"] = (f"measured in {choice.mode} (mu = {choice.signal_name}): the engine reduces fluorescence / "
                        "HERFD (IF/I0) only; transmission-mode samples are NOT SUPPORTED in its scope")
        return out
    attempts = R._bl15_2_missing(R._scan_attempts(tables, choice, np), ctx, params)
    numbers, _basis = B.input_scan_numbers(out["inputs"], run_of)
    num_of = {id(e): n for e, n in zip(out["inputs"], numbers)}
    stem_of = {k: (ctx.runs_by_key.get(k) or {}).get("stem") for k in set(run_of.values())}
    for k, (entry, table, sa, code) in enumerate(attempts):
        code = code or C.unusable_reason(sa)
        if code:
            entry["skip_reason"] = code
            continue
        rec = _arrays(table, choice, np)
        if rec is None:
            entry["skip_reason"] = "too_few_points"
            continue
        n = num_of.get(id(entry))
        stem = stem_of.get(entry.get("run_key")) or PurePosixPath(str(entry.get("relative_path"))).stem
        rec.update(entry=entry, sa=sa, num=n if isinstance(n, int) else k + 1, stem=stem,
                   scan_id=f"{stem}#{n}" if isinstance(n, int) else f"{stem}#pos{k + 1}",
                   run_key=entry.get("run_key"), header=table.header_lines, time=_scan_time(table.header_lines),
                   template=R._scan_template(table.header_lines))
        if not R._is_energy_scan(rec["template"]):
            entry["skip_reason"] = "not_an_energy_scan"
            continue
        out["recs"].append(rec)
    if not out["recs"]:
        out["scope"] = "no usable energy scan (v0 says why)"
        return out
    return out


def _arrays(table, choice, np) -> dict | None:
    """Sorted, duplicate-averaged E, IF, I0, I1, I2, sec of one scan (finite E, I0 > 0, finite IF)."""
    cols = table.columns
    E = np.asarray(cols[choice.energy], float)
    IF = np.sum([np.asarray(cols[c], float) for c in choice.signal_columns], axis=0)
    I0 = np.asarray(cols[choice.i0], float)
    extra = {}
    for name, cands in (("I1", ("I1", "It", "IT")), ("I2", ("I2", "Iref", "IR")), ("sec", ("sec", "Seconds", "Real time clock"))):
        c = next((c for c in cands if table.has(c)), None)
        extra[name] = np.asarray(cols[c], float) if c else None
    ok = np.isfinite(E) & np.isfinite(IF) & np.isfinite(I0) & (I0 > 0)
    if ok.sum() < C.MIN_SCAN_POINTS:
        return None
    order = np.argsort(E[ok], kind="stable")
    E = E[ok][order]
    arr = {"IF": IF[ok][order], "I0": I0[ok][order]}
    for k, v in extra.items():
        arr[k] = v[ok][order] if v is not None else None
    key = np.round(E, 6)
    uniq, inverse, counts = np.unique(key, return_inverse=True, return_counts=True)
    if uniq.size != E.size:
        for k, v in arr.items():
            if v is not None:
                arr[k] = np.bincount(inverse, weights=np.nan_to_num(v)) / counts
        E = uniq
    return {"E": E, **arr}


def _transmission_check(gread: Mapping, E_edge: float | None) -> dict | None:
    """The engine's measurement_mode (PROVENANCE.md M3) on a group's scans; None without an edge."""
    if E_edge is None:
        return None
    from xas_analysis.survey import measurement_mode

    infos = [_scaninfo(r, gread) for r in gread["recs"][:6]]
    return measurement_mode(infos, E_edge, " ".join(gread["stems"]))


def _scaninfo(rec: Mapping, gread: Mapping):
    from xas_analysis.survey import ScanInfo

    name = (gread.get("choice").signal_name if gread.get("choice") is not None else None) or "IF"
    ch = {"I0": rec["I0"]}
    for k in ("I1", "I2"):
        if rec.get(k) is not None:
            ch[k] = rec[k]
    ch[re.sub(r"[()/]", "_", name)] = rec["IF"]
    return ScanInfo(gread["stems"][0] if gread["stems"] else gread["group_id"], int(rec["num"]), rec.get("time"),
                    rec["E"], ch)


# --- the beamtime pass ------------------------------------------------------------------------------------------


def fingerprint(groups: Sequence[Mapping], ctx) -> str:
    from . import run as R

    src = sorted((str(k), str((v or {}).get("content_sha256"))) for k, v in (ctx.sources or {}).items())
    grp = sorted((str(g.get("group_id")), sorted((str(s.get("source_id")), str(s.get("scan_index")))
                                               for s in R.group_scans(g, ctx.runs_by_key)[0])) for g in groups)
    basis = {"protocol": [PROTOCOL_ID, PROTOCOL_VERSION], "engine": engine_version(), "sources": src, "groups": grp,
             "channels": ctx.params.get("channels")}
    return hashlib.sha256(json.dumps(basis, sort_keys=True, default=str).encode()).hexdigest()


def _logs(gread: Mapping, ctx) -> list[dict]:
    """The engine's ``mono reset`` lines (survey._read_log) in the group's own SPEC files."""
    from xas_analysis.survey import _read_log

    from . import run as R

    out, seen = [], getattr(ctx, "_engine_log_seen", None)
    if seen is None:
        seen = ctx._engine_log_seen = set()
    paths = {e.get("relative_path") for e in gread["inputs"] if e.get("format") == "spec_columns"}
    for key in {e.get("run_key") for e in gread["inputs"]}:
        run = ctx.runs_by_key.get(key) or {}
        src = (ctx.sources.get(run.get("acquisition_source_id") or "") or {}).get("relative_path")
        if src:
            paths.add(src)
    for rel in sorted(p for p in paths if p):
        if rel in seen or ctx.root is None:
            continue
        seen.add(rel)
        path = R._resolve_source(ctx.root, rel)
        if path is None or not path.is_file() or path.stat().st_size > 50_000_000:
            continue
        try:
            for x in _read_log(path):
                out.append({**x, "file": rel})
        except OSError:
            continue
    return out


def prepare(groups: Sequence[Mapping], ctx, *, stored: Mapping | None = None, wanted: set | None = None) -> dict:
    """THE BEAMTIME PASS: read every group, run the engine's survey once, pick the reference (earliest group, mean
    anchor) and the normalisation windows, and anchor every scan. GUARDED: an exception is recorded (``error``) and
    every group then stays on v0 with that reason. ``stored`` (a ``--group`` run): the beamtime block of the last
    full run, used when its fingerprint is this run's (only the wanted groups are read then)."""
    try:
        return _prepare(groups, ctx, stored=stored, wanted=wanted)
    except Exception as exc:  # noqa: BLE001 - never a processing failure: the groups stay on v0, and say why
        return {"error": f"{type(exc).__name__}: {exc}"[:400], "reads": {}}


def _prepare(groups, ctx, *, stored, wanted) -> dict:
    import numpy as np  # noqa: F401 - the engine needs numpy; ctx.np is the same module

    fp = fingerprint(groups, ctx)
    reuse = (stored is not None and wanted is not None and stored.get("fingerprint") == fp and not stored.get("error")
             and stored.get("calibration") is not None)
    reads: dict[str, dict] = {}
    for g in groups:
        if reuse and g["group_id"] not in wanted:
            continue
        try:
            reads[g["group_id"]] = read_group(g, ctx)
        except Exception as exc:  # noqa: BLE001 - one group's read failure keeps it on v0
            reads[g["group_id"]] = {"group_id": g["group_id"], "scope": f"read failed: {type(exc).__name__}: {exc}"[:300],
                                    "recs": [], "inputs": [], "stems": []}
    if reuse:
        bt = {k: v for k, v in stored.items()}
        bt["reused"] = True
        bt["reads"] = reads
        _anchor_all(bt, reads, ctx)
        return bt
    bt = _survey(reads, groups, ctx)
    bt["fingerprint"] = fp
    bt["reused"] = False
    bt["reads"] = reads
    _reference(bt, reads, ctx)
    _anchor_all(bt, reads, ctx)
    _windows(bt, reads)
    return bt


def _survey(reads: Mapping, groups: Sequence[Mapping], ctx) -> dict:
    from xas_analysis.survey import FileInfo, _jsonable, identify_edge, survey_files

    from . import run as R

    files, logs = [], []
    by_id = {g["group_id"]: g for g in groups}
    for gid, gr in reads.items():
        role = gr.get("role")
        if gr.get("scope") is None:
            frole = "reference" if role == "reference" else "sample"
        elif role == "alignment" and gr.get("recs"):
            frole = "alignment"
        elif role == "reference" and R._names_a_foil(gr.get("stems") or ()) and gr.get("recs"):
            frole = "foil"
        else:
            frole = None
        logs += _logs(gr, ctx) if gr.get("inputs") else []
        if frole is None or not gr.get("recs"):
            continue
        fi = FileInfo(path=gid, name=(gr["stems"][0] if gr["stems"] else gid), fmt="spec", role=frole,
                      n_all=len(gr["inputs"]))
        fi.scans = [_scaninfo(r, gr) for r in gr["recs"]]
        fi._group_id = gid
        files.append(fi)
    files.sort(key=lambda f: min([s.time for s in f.scans if s.time] or [datetime.max]))
    if not any(f.role in ("sample", "reference") for f in files):
        return {"calibration": None, "statement": "no group in the engine's scope", "survey": {}, "logs": logs,
                "file_groups": {}}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rep = survey_files(files, [], "the bundle's record groups")
    rep["calibration_log"] = (rep.get("calibration_log") or []) + logs
    for x in logs:
        rep["findings"].append(f"{x['file']}: {x['axis']} reset {x['from']} -> {x['to']} ({x['time']})")
    edge = rep.get("edge") or identify_edge([s for f in files for s in f.scans[:2]])
    keep = ("findings", "warnings", "edge", "fluorescence_channel", "absev_minus_energy", "calibration_log",
            "glitch_candidates", "glitch", "glitch_method_scatter", "glitch_doublet_test", "window_sensitivity_meV",
            "foil_scans", "in_scan_foil_fraction", "first_sample_time", "recommendation")
    summary = _jsonable({k: rep.get(k) for k in keep if k in rep})
    summary["files"] = _jsonable([{k: f.get(k) for k in ("name", "role_guess", "n_xas", "first", "foil_edges")}
                                  for f in rep.get("files") or ()][:300])
    cal = dict((rep.get("recommendation") or {}).get("calibration") or {"mode": "none"})
    return {"calibration": _jsonable(cal), "survey": summary, "edge": _jsonable(edge), "logs": logs,
            "file_groups": {f.name: f._group_id for f in files}, "glitch": _jsonable(rep.get("glitch"))}


def _routes(bt: Mapping) -> list[dict]:
    """The anchor routes, best first: the survey's calibration, then (a foil route only) the I0 glitch, so a scan
    whose foil is not usable is still aligned on the glitch (rule 4: a foil when usable, otherwise the I0 glitch)."""
    cal = bt.get("calibration") or {"mode": "none"}
    routes = [dict(cal)]
    g = bt.get("glitch")
    if cal.get("mode") == "ref_foil" and g:
        from xas_analysis.survey import glitch_window

        w = glitch_window(g, ((bt.get("survey") or {}).get("glitch_candidates") or []))
        routes.append({"mode": "glitch_I0", "method": "model", "shape_window_eV": w, "window_eV": w,
                       "max_shift_eV": 1.0, "fallback": True})
    return routes


def _anchor_fns(route: Mapping, template_rec: Mapping | None):
    from xas_analysis.pipeline import anchor_signal, make_anchor_fn

    mode = route.get("mode")
    if mode in ("glitch_I0", "ref_foil") and route.get("method") == "shape" and template_rec is not None:
        t = _Sc(template_rec)
        base = make_anchor_fn({**route, "method": "inflection"})
        ta, _ = base(t)
        if ta is None or ta != ta:
            return None
        return make_anchor_fn(dict(route), (t.Energy_eV, anchor_signal(t, route)), ta)
    return make_anchor_fn(dict(route))


def _reference(bt: dict, reads: Mapping, ctx) -> None:
    """The beamtime reference (the engine's 'earliest file, mean anchor' convention), per route."""
    bt["routes"] = []
    cal = bt.get("calibration")
    if not cal:
        return
    inscope = [gr for gr in reads.values() if gr.get("scope") is None and gr.get("recs")]
    if not inscope:
        return
    def t0(gr):
        ts = [r["time"] for r in gr["recs"] if r.get("time")]
        return min(ts) if ts else datetime.max
    ref = min(inscope, key=t0)
    for route in _routes(bt):
        mode = route.get("mode")
        info = {"route": route, "reference_group_id": ref["group_id"], "reference_name": ref["stems"][0] if ref["stems"] else None}
        if mode == "none":
            info.update(anchor_eV=0.0, scans=[], anchors=[], std_eV=None, statement=(
                "No energy reference was found (no in-scan foil, no I0 glitch, no foil scans): energies are only as "
                "good as the beamline calibration, and no scan was shifted."))
            bt["routes"].append(info)
            continue
        if mode == "foil_timeline":
            info.update(_foil_timeline(route, bt, reads))
            bt["routes"].append(info)
            continue
        template = None
        if route.get("method") == "shape":
            template = next((r for r in ref["recs"]), None)
        try:
            fn = _anchor_fns(route, template)
        except Exception as exc:  # noqa: BLE001
            fn, info["error"] = None, f"{type(exc).__name__}: {exc}"[:200]
        if fn is None:
            info.update(anchor_eV=None, scans=[], anchors=[], statement="the reference anchor could not be made")
            bt["routes"].append(info)
            continue
        got = []
        for r in ref["recs"]:
            a, ok, _i = _anchor_one(fn, r, route)
            if ok:
                got.append((r["scan_id"], a))
        info["scans"] = [s for s, _ in got]
        info["anchors"] = [a for _, a in got]
        info["anchor_eV"] = float(statistics.fmean(info["anchors"])) if got else None
        info["std_eV"] = float(statistics.stdev(info["anchors"])) if len(got) > 1 else None
        info["template_scan"] = template["scan_id"] if template else None
        bt["routes"].append(info)
        bt.setdefault("_fns", {})[len(bt["routes"]) - 1] = fn


def _foil_timeline(route: Mapping, bt: Mapping, reads: Mapping) -> dict:
    """foil_timeline: the engine's foil anchors (inflection of the foil scans' transmission ratio) in time; a scan's
    anchor is linear in time between them (constant beyond the first and last)."""
    from xas_analysis.calib import find_inflection_point
    from xas_analysis.pipeline import _ref_signal_terms

    rows = []
    gid_of = bt.get("file_groups") or {}
    for f in route.get("foils") or ():
        gr = reads.get(gid_of.get(f.get("spec")))
        if not gr:
            continue
        num, den = _ref_signal_terms(f.get("ref_signal", "ln(I0/I1)"))
        import numpy as np

        for r in gr["recs"]:
            a_, b_ = r.get(num), r.get(den)
            if a_ is None or b_ is None or not r.get("time"):
                continue
            with np.errstate(all="ignore"):
                y = np.log(a_ / b_)
            a, i = find_inflection_point(r["E"], y, route.get("foil_window_eV") or [-np.inf, np.inf], sign=1)
            if i.get("ok") and a == a:
                rows.append((r["time"].timestamp(), float(a), r["scan_id"]))
    rows.sort()
    if not rows:
        return {"anchor_eV": None, "timeline": [], "statement": "no foil scan gave a usable anchor"}
    return {"anchor_eV": rows[min(int(route.get("reference_foil", 0)), len(rows) - 1)][1],
            "timeline": [{"time": datetime.fromtimestamp(t).isoformat(), "anchor_eV": a, "scan": s} for t, a, s in rows]}


def _anchor_one(fn, rec: Mapping, route: Mapping) -> tuple[float | None, bool, dict]:
    import numpy as np

    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        try:
            a, info = fn(_Sc(rec))
        except Exception as exc:  # noqa: BLE001 - a scan whose anchor cannot be found: a failed anchor
            return None, False, {"reason": f"{type(exc).__name__}: {exc}"[:200]}
    a = _f(a)
    info = {k: (_f(v) if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) else v)
            for k, v in (info or {}).items() if k in ("ok", "reason", "sigma_eV", "depth", "sep_eV", "shift_fit_rms")}
    return a, bool(a is not None and info.get("ok")), info


def _anchor_all(bt: dict, reads: Mapping, ctx) -> None:
    """Every in-scope scan's anchor and shift: the first route whose anchor is ok, within the shift limit."""
    routes = bt.get("routes") or []
    fns = bt.get("_fns") or {}
    if bt.get("reused"):
        # a reused beamtime block: the anchor functions are rebuilt from the stored routes
        fns = {}
        for k, info in enumerate(routes):
            route = info.get("route") or {}
            if route.get("mode") in ("glitch_I0", "ref_foil"):
                tmpl = None
                if route.get("method") == "shape":
                    tmpl = _stored_template(info, reads, ctx)
                    if tmpl is None:
                        continue
                fns[k] = _anchor_fns(route, tmpl)
        bt["_fns"] = fns
    for gr in reads.values():
        if gr.get("scope") is not None:
            continue
        for r in gr["recs"]:
            r["alignment"] = _align_rec(r, routes, fns)


def _stored_template(info: Mapping, reads: Mapping, ctx) -> dict | None:
    gid = info.get("reference_group_id")
    gr = reads.get(gid)
    if gr is None:
        g = next((x for x in getattr(ctx, "_engine_groups", ()) if x["group_id"] == gid), None)
        if g is None:
            return None
        gr = read_group(g, ctx)
    return next((r for r in gr.get("recs") or () if r["scan_id"] == info.get("template_scan")), None)


def _align_rec(r: Mapping, routes: Sequence[Mapping], fns: Mapping) -> dict:
    tried = []
    for k, info in enumerate(routes):
        route = info.get("route") or {}
        mode = route.get("mode")
        if mode == "none":
            return {"route": "none", "anchor_eV": None, "reference_anchor_eV": None, "shift_eV": 0.0, "ok": True,
                    "tried": tried}
        if mode == "foil_timeline":
            tl = info.get("timeline") or []
            if not tl or not r.get("time") or info.get("anchor_eV") is None:
                tried.append({"route": mode, "reason": "no foil timeline or no scan time"})
                continue
            import numpy as np

            ts = [datetime.fromisoformat(x["time"]).timestamp() for x in tl]
            a = float(np.interp(r["time"].timestamp(), ts, [x["anchor_eV"] for x in tl]))
            return {"route": mode, "anchor_eV": a, "reference_anchor_eV": info["anchor_eV"],
                    "shift_eV": info["anchor_eV"] - a, "ok": True, "tried": tried}
        fn = fns.get(k)
        if fn is None or info.get("anchor_eV") is None:
            tried.append({"route": mode, "reason": "no reference anchor for this route"})
            continue
        a, ok, detail = _anchor_one(fn, r, route)
        shift = (info["anchor_eV"] - a) if a is not None else None
        limit = float(route.get("max_shift_eV") or MAX_SHIFT_EV.get(mode, 1.0))
        if ok and shift is not None and abs(shift) > limit:
            ok, detail = False, {**detail, "reason": f"shift {shift:+.3f} eV beyond the {limit:g} eV limit"}
        if ok:
            return {"route": mode + ("_fallback" if route.get("fallback") else ""), "method": route.get("method"),
                    "anchor_eV": a, "reference_anchor_eV": info["anchor_eV"], "shift_eV": shift, "ok": True,
                    "fit": detail, "tried": tried}
        tried.append({"route": mode, "anchor_eV": a, "reason": detail.get("reason") or "fit not ok"})
    return {"route": None, "anchor_eV": None, "reference_anchor_eV": None, "shift_eV": None, "ok": False,
            "tried": tried}


def _windows(bt: dict, reads: Mapping) -> None:
    """The engine's default normalisation window (recipe_init.norm_range) on the beamtime's modal grid, one per
    edge: fixed for every compared series of that edge."""
    from collections import Counter

    from xas_analysis.recipe_init import norm_range

    edge = bt.get("edge") or {}
    if not edge.get("E_edge_eV"):
        bt["windows"] = {}
        return
    grids = Counter()
    for gr in reads.values():
        if gr.get("scope") is None:
            for r in gr["recs"]:
                grids[(round(float(r["E"][0])), round(float(r["E"][-1])))] += 1
    if not grids:
        bt["windows"] = {}
        return
    lo, hi = grids.most_common(1)[0][0]
    bt["windows"] = {f"{edge['element']} {edge['core']}": {"range": norm_range(float(edge["E_edge_eV"]), lo, hi),
                                                           "modal_grid_eV": [lo, hi],
                                                           "rule": "recipe_init.norm_range on the beamtime's modal grid"}}


def beamtime_payload(bt: Mapping) -> dict:
    """The beamtime block written into processing_results.json (no arrays, no functions)."""
    keep = ("fingerprint", "reused", "calibration", "survey", "edge", "routes", "windows", "glitch", "file_groups",
            "error", "statement")
    out = {k: bt.get(k) for k in keep if k in bt}
    out["protocol_id"], out["engine_version"] = PROTOCOL_ID, engine_version()
    out["in_scope_groups"] = sorted(k for k, v in (bt.get("reads") or {}).items() if v.get("scope") is None)
    out["out_of_scope_groups"] = {k: v.get("scope") for k, v in sorted((bt.get("reads") or {}).items())
                                  if v.get("scope") is not None}
    return json.loads(json.dumps(out, default=str))


# --- the group ---------------------------------------------------------------------------------------------------


def covers(group: Mapping, ctx) -> tuple[bool, str | None]:
    bt = getattr(ctx, "engine", None)
    if not bt:
        return False, "the engine is not available in this run"
    if bt.get("error"):
        return False, f"the engine's beamtime pass failed ({bt['error']})"
    gr = (bt.get("reads") or {}).get(group["group_id"])
    if gr is None:
        return False, "the group was not read by the engine"
    if gr.get("scope") is not None:
        return False, gr["scope"]
    if not bt.get("calibration"):
        return False, bt.get("statement") or "no beamtime calibration"
    absorber = absorber_of(group, ctx, bt)
    tr = _transmission_check(gr, absorber.get("E_edge_eV"))
    gr["mode_check"] = tr
    if tr and tr.get("mode") == "transmission":
        return False, (f"transmission-mode data ({tr['basis']}; ln(I0/I1) step {tr['transmission_step']:.3g}): "
                       "transmission samples are NOT SUPPORTED in the engine's scope")
    return True, None


def absorber_of(group: Mapping, ctx, bt: Mapping | None = None) -> dict:
    """The element and edge the normalisation uses: the scientist's set_absorber, else the files' agreeing absorber
    evidence (suggestions.absorber_for_group), else the edge the engine's survey identified from the scan range."""
    from xas_analysis.pipeline import tabulated_edge_eV

    from ..suggestions import absorber_decisions, absorber_for_group

    d = absorber_decisions(ctx.bundle).get(group["group_id"])
    if d is not None:
        el, ed, basis = d["element"], d["edge"], f"confirmed by a scientist (set_absorber, {d.get('decision_id')})"
    else:
        try:
            a = absorber_for_group(ctx.bundle, group)
        except Exception:  # noqa: BLE001
            a = {"status": "none"}
        if a.get("status") == "agrees":
            el, ed, basis = a["element"], a["edge"], "the files' absorber evidence (agrees; not yet confirmed)"
        else:
            e = (bt or getattr(ctx, "engine", {}) or {}).get("edge") or {}
            el, ed = e.get("element"), e.get("core")
            basis = ("identified by the engine's survey from the scan range (the tabulated edge inside it with the "
                     "largest fluorescence step); a suggestion, not confirmed: set_absorber confirms it")
    E = tabulated_edge_eV(el, ed) if el and ed else None
    return {"element": el, "edge": ed, "E_edge_eV": E, "basis": basis}


def process_group_v1(group: Mapping, ctx) -> list[dict]:
    from . import run as R

    np = ctx.np
    bt = ctx.engine
    gr = bt["reads"][group["group_id"]]
    absorber = absorber_of(group, ctx, bt)
    res = R._base(group, "isaac_protocol")
    res.update(protocol_id=PROTOCOL_ID, protocol_version=PROTOCOL_VERSION, protocol_status=PROTOCOL_STATUS)
    res.pop("rule_versions", None)
    res[ENGINE_KEY] = {"protocol_id": PROTOCOL_ID, "engine": ENGINE_NAME, "engine_version": engine_version(),
                       "engine_source": ENGINE_SOURCE, "adapter_rule_id": ADAPTER_RULE_ID,
                       "statement": (f"Processed by {PROTOCOL_ID}: the vendored {ENGINE_NAME} {engine_version()} "
                                     "reduction engine (Oscar's validated package) and the ISAAC adapter. A draft "
                                     "until the ISAAC processing reviewers (Oscar and Angel) review the adapter.")}
    res["review_flags"] = ["protocol_draft_unreviewed"]
    res["channel_choice"] = gr["choice"].to_state()
    inputs = gr["inputs"]
    res["inputs"] = inputs
    recs = gr["recs"]
    E_edge = absorber.get("E_edge_eV")
    # --- align: ONE shift and ONE interpolation per scan, onto the group's modal grid
    from collections import Counter

    from xas_analysis.average import AlignedScan, average_scans
    from xas_analysis.calib import align_and_resample
    from xas_analysis.pipeline import screen_report

    grid_of = Counter((round(float(r["E"][0]), 1), round(float(r["E"][-1]), 1), int(r["E"].size)) for r in recs)
    modal = grid_of.most_common(1)[0][0]
    grid_rec = next(r for r in recs if (round(float(r["E"][0]), 1), round(float(r["E"][-1]), 1), int(r["E"].size)) == modal)
    g_shift = grid_rec["alignment"]["shift_eV"] if grid_rec["alignment"]["ok"] else 0.0
    target = np.asarray(grid_rec["E"], float) + float(g_shift or 0.0)
    aligned = []
    for r in recs:
        al = r["alignment"]
        if not al["ok"]:
            r["aligned"] = None
            continue
        sec = r["sec"] if r.get("sec") is not None else np.full(r["E"].size, np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Y, _ri = align_and_resample(r["E"], np.c_[r["IF"], r["I0"], sec], 0.0, float(al["shift_eV"]), target)
        a = AlignedScan(r["num"], target, Y[:, 0], Y[:, 1], Y[:, 2], _f(al["anchor_eV"]) if al["anchor_eV"] is not None else 0.0,
                        float(al["shift_eV"]), True, True, key=r["scan_id"])
        r["aligned"] = a
        aligned.append(a)
    # --- screening (report-only: this rule decides)
    win = [E_edge + SCREEN_WINDOW_EV[0], E_edge + SCREEN_WINDOW_EV[1]] if E_edge else [-np.inf, np.inf]
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        flags = screen_report(aligned, {**SCREENING, "window_eV": win}) if aligned else []
    by_scan: dict[str, list[dict]] = {}
    for f in flags:
        by_scan.setdefault(f["key"], []).append(f)
    # --- stability (isaac.xas.scan_selection_proposal.v0 on the ALIGNED scans)
    stability = _stability(group, ctx, gr, recs, inputs)
    # --- logbook notes
    notes, notes_said = _logbook(ctx, gr, recs)
    # --- the rule
    table = decide_scans(recs, by_scan, stability, notes, scientist_scan_decisions(ctx.bundle, group["group_id"]),
                         inputs, target, win, np)
    kept = [r for r in recs if table["by_id"][r["scan_id"]]["decision"] == "keep" and r.get("aligned") is not None]
    for e in inputs:
        e["used"] = False
    for r in recs:
        row = table["by_id"][r["scan_id"]]
        e = r["entry"]
        e["scan_id"] = r["scan_id"]
        if row["decision"] == "keep" and r.get("aligned") is not None:
            e.update(used=True, channel=gr["choice"].signal_name)
            e.pop("skip_reason", None)
        else:
            e["skip_reason"] = DROP_REASON
    res[DECISIONS_KEY] = {k: v for k, v in table.items() if k != "by_id"}
    res[SHIFTS_KEY] = _shift_table(recs, bt)
    res[REFERENCE_KEY] = _reference_view(bt, recs)
    res[LOGBOOK_KEY] = notes_said
    cal_step = {"step": "calibration", "params": {"rule": "per-scan alignment to ONE beamtime reference (rule 4)",
                                                  "routes": [x.get("route") for x in bt.get("routes") or ()]},
                "outcome": {"kind": "per_scan_alignment", "applied": any(abs(r["alignment"]["shift_eV"] or 0) > 0
                                                                          for r in recs if r["alignment"]["ok"]),
                            "per_scan_alignment_shifts_eV": [r["alignment"]["shift_eV"] for r in kept],
                            "applied_shift_eV": 0.0, "reference_group_id": (bt.get("routes") or [{}])[0].get("reference_group_id")},
                "flags": []}
    res["steps"].append(cal_step)
    if not kept:
        out = R._fail(res, "no_scan_kept", f"all {len(recs)} usable scans were dropped by {DECISION_RULE_ID}")
        out["qc"]["statements"] = {"no_scan_kept": table["statement"]}
        _finish_ids(out, group)
        return [out]
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        avg, ainfo = average_scans([r["aligned"] for r in kept], "uniform", 1, True, True)
    ok = np.isfinite(avg["IF_over_I0"]) & (avg["n_kept"] > 0)
    E, y, err, n = target[ok], avg["IF_over_I0"][ok], avg["err"][ok], avg["n_kept"][ok]
    res["steps"].append({"step": "merge", "params": {"statistic": "uniform mean of raw IF/I0 over the kept scans "
                                                                  "(xas_analysis.average.average_scans; err = its standard "
                                                                  "error)", "grid": "the group's modal scan grid, shifted"},
                         "outcome": {"n_scans": len(kept), "points": int(E.size), "grid_from_scan": grid_rec["scan_id"]},
                         "flags": [] if len(kept) > 1 else ["single_scan_no_merge"]})
    nm = normalize_once(E, y, n, absorber, bt, np)
    res[NORMALIZATION_KEY] = {k: v for k, v in nm.items() if k not in ("norm", "mu", "bg")}
    if nm.get("error"):
        res["steps"].append({"step": "normalize", "params": nm.get("params") or {}, "outcome": {"error": nm["error"]},
                             "flags": ["normalization_failed"]})
        out = R._fail(res, "normalization_failed", nm["error"])
        _finish_ids(out, group)
        return [out]
    e0 = None
    try:
        e0 = _f(ctx.xafs.find_e0(E, y))
    except Exception:  # noqa: BLE001
        e0 = None
    res["steps"].append({"step": "normalize", "params": nm["params"],
                         "outcome": {"e0_eV": e0, "edge_step": nm["A_edge"], "model": nm["model"],
                                     "convention": nm["convention"]}, "flags": []})
    verdict, reasons, statements, metrics = _qc(res, recs, kept, table, nm, E, y, e0, absorber, bt, np)
    res["qc"] = {"metrics": metrics, "verdict": verdict, "reasons": reasons, **({"statements": statements} if statements else {})}
    res["steps"].append({"step": "qc", "params": {"rule": "isaac.xas.v1 qc (engine_xas._qc)"},
                         "outcome": {"verdict": verdict, "reasons": reasons}, "flags": []})
    # --- outputs (content-addressed, as v0)
    group_dir = ctx.out_dir / group["group_id"]
    group_dir.mkdir(parents=True, exist_ok=True)
    gdir = Path(tempfile.mkdtemp(prefix=".staging-", dir=group_dir))
    _csv(gdir / "merged.csv", ["energy_eV", "mu_mean", "mu_stderr", "n_scans"], [E, y, err, n.astype(float)], np)
    _csv(gdir / "normalized.csv", ["energy_eV", "norm", "mcmaster_mu", "background"], [E, nm["norm"], nm["mu"], nm["bg"]], np)
    R._write(gdir / "scan_decisions.json", R._json_bytes({"group_id": group["group_id"], "rule": DECISION_RULE,
                                                          "scan_decisions": res[DECISIONS_KEY]["rows"],
                                                          "scan_shifts": res[SHIFTS_KEY]}))
    R._write(gdir / "qc.json", R._json_bytes({"group_id": group["group_id"], **res["qc"], "protocol_status": PROTOCOL_STATUS}))
    R._write(gdir / "params.json", R._json_bytes({
        "protocol_id": PROTOCOL_ID, "protocol_version": PROTOCOL_VERSION, "protocol_status": PROTOCOL_STATUS,
        "engine": res[ENGINE_KEY], "screening": {**SCREENING, "window_eV": win},
        "decision_rule": DECISION_RULE, "channel_choice": res["channel_choice"], "absorber": absorber,
        "normalization": res[NORMALIZATION_KEY], "beamtime_fingerprint": bt.get("fingerprint"),
        "energy_reference": res[REFERENCE_KEY]}))
    plotted = False
    try:
        plotted = plot(gdir / "plot.png", group, recs, table, E, y, nm, e0, absorber, np)
    except Exception:  # noqa: BLE001 - a plot failure is a flag, never a processing failure
        plotted = False
    if not plotted:
        res["review_flags"].append("plot_unavailable")
    roles = [("merged", "merged.csv"), ("normalized", "normalized.csv"), ("scan_decisions", "scan_decisions.json"),
             ("qc", "qc.json"), ("params", "params.json")] + ([("plot", "plot.png")] if plotted else [])
    data_hashes = sorted((name, R.sha256_file(gdir / name)) for _r, name in roles if name != "plot.png")
    input_hashes = sorted((ctx.sources.get(r["entry"].get("source_id") or "") or {}).get("content_sha256")
                          or str(r["entry"].get("relative_path")) for r in kept)
    h = hashlib.sha256(json.dumps([PROTOCOL_ID, PROTOCOL_VERSION, group["group_id"], input_hashes,
                                   [list(x) for x in data_hashes]]).encode())
    run_id = "r-" + h.hexdigest()[:16]
    final = group_dir / run_id
    if final.exists():
        shutil.rmtree(gdir)
    else:
        gdir.rename(final)
    gdir = final
    res["run_id"] = run_id
    res["result_id"] = f"proc-{group['group_id']}-{run_id}-isaac"
    res["prior_run_ids"] = sorted(p.name for p in group_dir.iterdir() if p.is_dir() and R._RUN_DIR.match(p.name)
                                  and p.name != run_id)
    res["outputs"] = {"files": [{"role": role, "relative_path": PurePosixPath((gdir / name).relative_to(ctx.bundle_dir)).as_posix(),
                                 "sha256": R.sha256_file(gdir / name)} for role, name in roles if (gdir / name).is_file()],
                      "e0_eV": e0, "edge_step": nm["A_edge"], "points": int(E.size)}
    # the scientists' quick beamtime merges: a rough reference, as on v0 (outside every hashed file)
    try:
        quick = _quick_merges(group, ctx, recs, kept, E, y, nm, e0, absorber, np)
        if quick:
            from . import quick_merge as QM

            res[QM.RESULT_KEY] = quick
    except Exception:  # noqa: BLE001 - a rough reference that cannot be made is not a processing failure
        pass
    for e in inputs:
        e.pop("run_key", None)
    record = gdir / "result.json"
    if not record.exists():
        R._write(record, R._json_bytes({"results": [res]}))
    return [res]


def _finish_ids(res: dict, group: Mapping) -> None:
    """A failed v1 result: its id names the v1 protocol (R._fail hashes v0's id)."""
    h = hashlib.sha256(json.dumps([PROTOCOL_ID, PROTOCOL_VERSION, group["group_id"], res.get("failure"),
                                   (res.get(DECISIONS_KEY) or {}).get("rows")], default=str).encode())
    res["run_id"] = "r-" + h.hexdigest()[:16]
    res["result_id"] = f"proc-{group['group_id']}-{res['run_id']}-isaac"
    for e in res.get("inputs") or ():
        e.pop("run_key", None)


def _csv(path: Path, header: Sequence[str], cols: Sequence, np) -> None:
    from . import run as R

    lines = [f"# DRAFT protocol {PROTOCOL_ID} ({PROTOCOL_STATUS}) - review material, not an official value", ",".join(header)]
    for row in zip(*cols):
        lines.append(",".join("" if (v is None or not np.isfinite(v)) else (f"{v:.6f}" if i == 0 else f"{v:.8g}")
                              for i, v in enumerate(row)))
    R._write(path, ("\n".join(lines) + "\n").encode("utf-8"))


def _stability(group, ctx, gr, recs, inputs) -> dict:
    """v0's stability analysis on the ALIGNED scans: ``{scan id: per-scan row}`` plus the group block."""
    from . import run as R

    scans = [{"source_id": e.get("source_id"), "relative_path": e.get("relative_path"), "scan_index": e.get("scan"),
              "run_key": e.get("run_key")} for e in inputs]
    used, data, header_of = [], [], {}
    for r in recs:
        if r.get("aligned") is None:
            continue
        sa = dict(r["sa"])
        sa["energy"] = sa["energy"] + float(r["alignment"]["shift_eV"])
        r["entry"]["used"] = True
        used.append(r["entry"])
        data.append(sa)
        header_of[id(r["entry"])] = r["header"]
    if len(used) < 1:
        return {"status": "not_evaluated", "rows": {}}
    sel = R._propose_scan_selection(group, ctx, scans, used, data, header_of, inputs,
                                    {"outcome": {"applied_shift_eV": 0.0}}, mode=gr["choice"].mode)
    rows = {}
    if sel:
        for x in sel.get("scans") or ():
            e = next((e for e in inputs if e.get("source_id") == x.get("source_id") and e.get("scan") == x.get("scan")
                      and e.get("relative_path") == x.get("relative_path")), None)
            r = next((r for r in recs if r["entry"] is e), None)
            if r is not None:
                rows[r["scan_id"]] = x
    return {"status": (sel or {}).get("status", "not_evaluated"), "rows": rows,
            "stable_window": (sel or {}).get("stable_window"), "evolving_metrics": (sel or {}).get("evolving_metrics"),
            "group_observations": (sel or {}).get("group_observations"), "detail": (sel or {}).get("detail")}


def _logbook(ctx, gr, recs) -> tuple[dict, dict]:
    """``({scan id: [actions]}, the block said on the result)``: each run's logbook scan notes, applied by number."""
    by_scan: dict[str, list[dict]] = {}
    said: dict = {"available": True, "notes": [], "statement": None}
    why_none = None
    runs = []
    for key in dict.fromkeys(r["run_key"] for r in recs):
        run = ctx.runs_by_key.get(key) or {}
        runs.append(run)
    for run in runs:
        notes, why = scan_notes_for(ctx.bundle, run.get("run_id"))
        if notes is None:
            why_none = why
            continue
        mine = [r for r in recs if r["run_key"] == run.get("run_key")]
        nums = sorted(r["num"] for r in mine)
        for nt in notes:
            action = nt.get("action")
            scans = [int(s) for s in nt.get("scans") or () if isinstance(s, int) or str(s).isdigit()]
            if action == "exclude":
                hit = set(scans)
            elif action == "start_from" and scans:
                hit = {n for n in nums if n < min(scans)}
            elif action == "keep_only" and scans:
                hit = {n for n in nums if n not in set(scans)}
            else:
                hit = set()
            entry = {"run": run.get("stem"), "action": action, "scans": scans, "reason": nt.get("reason"),
                     "quote": nt.get("quote"), "source": nt.get("source"), "strength": nt.get("strength"),
                     "drops": sorted(hit), "applied": action in ("exclude", "start_from", "keep_only")}
            said["notes"].append(entry)
            for r in mine:
                if r["num"] in hit:
                    by_scan.setdefault(r["scan_id"], []).append(entry)
                elif action == "flag" and r["num"] in set(scans):
                    # a flag naming scans is shown on each; a flag naming none is said once (the logbook block)
                    by_scan.setdefault(r["scan_id"], []).append({**entry, "applied": False})
    if why_none is not None and not said["notes"]:
        said = {"available": False, "notes": [], "statement": f"No logbook scan notes: {why_none}."}
    elif not said["notes"]:
        said["statement"] = "No logbook scan note names these runs."
    else:
        said["statement"] = (f"{len(said['notes'])} logbook scan note(s) name these runs; exclude, start_from and keep_only "
                             "notes are applied (an 'inferred' one marked so); a flag changes nothing and is shown.")
    return by_scan, said


def decide_scans(recs, screen_flags, stability, notes, overrides, inputs, target, win, np) -> dict:
    """THE RULE (:data:`DECISION_RULE_ID`): keep or drop for every scan, with its reasons and evidence."""
    rows, by_id = [], {}
    stab_rows = (stability or {}).get("rows") or {}
    for r in recs:
        drop, noted = [], []
        sid = r["scan_id"]
        for nt in notes.get(sid) or ():
            item = {"source": "logbook", "code": f"logbook_{nt['action']}", "strength": nt.get("strength"),
                    "said": f"logbook ({nt.get('strength')}): {nt.get('reason')}", "quote": nt.get("quote"),
                    "where": nt.get("source")}
            (drop if nt.get("applied") else noted).append(item)
        st = stab_rows.get(sid)
        if st:
            reasons = list(st.get("reasons") or ())
            if "before_stable_window" in reasons:
                drop.append({"source": "stability", "code": "before_stable_window",
                             "said": "; ".join(st.get("said") or ()) or "the sample was still changing",
                             "evidence": {"stable_window": stability.get("stable_window"),
                                          "evolving_metrics": stability.get("evolving_metrics")}})
            other = [x for x in reasons if x != "before_stable_window"]
            if other and st.get("proposal") in ("needs_look", "exclude_proposed"):
                noted.append({"source": "stability", "code": ",".join(other), "said": "; ".join(st.get("said") or ()),
                              "decides": False})
        al = r.get("alignment") or {}
        if not al.get("ok"):
            drop.append({"source": "screening", "code": "anchor_failed",
                         "said": "no energy anchor: " + "; ".join(f"{t.get('route')}: {t.get('reason')}"
                                                                  for t in al.get("tried") or ()),
                         "evidence": {"tried": al.get("tried")}})
        for f in screen_flags.get(sid) or ():
            test = f["test"]
            item = {"source": "screening", "code": test, "said": f["reason"],
                    "evidence": {k: f.get(k) for k in ("value", "median", "threshold")}}
            if test == "shape":
                noise = _own_noise(r, win, np)
                item["evidence"]["own_noise"] = noise
                if noise is not None and f.get("value") is not None and f["value"] <= SHAPE_NOISE_FACTOR * noise:
                    noted.append({**item, "code": "noisier_not_off_shape", "decides": False,
                                  "said": f"{f['reason']}, but within {SHAPE_NOISE_FACTOR:g}x its own counting noise "
                                          f"({noise:.2e}): fewer counts, not another shape; kept (an intensity effect "
                                          "never drops a scan)"})
                    continue
            if test == "dead_channel":
                snr = _edge_snr(r, win, np)
                item["evidence"]["edge_snr"] = snr
                if snr is None or snr >= DEAD_EDGE_SNR_MIN:
                    noted.append({**item, "code": "weak_signal", "decides": False,
                                  "said": f"{f['reason']}; its edge is still visible (edge/noise {snr if snr is None else round(snr, 1)}): "
                                          "a weaker scan, kept (an intensity drop alone never drops a scan)"})
                    continue
                item["said"] = f"{f['reason']} and no edge at all (edge/noise {snr:.1f}): no spectrum"
            drop.append(item)
        decision = "drop" if drop else "keep"
        by = "rule"
        ov = overrides.get(sid) or overrides.get(PurePosixPath(str(r["entry"].get("relative_path"))).name) \
            or overrides.get(str(r["entry"].get("relative_path")))
        if ov:
            by = "scientist"
            decision = ov["decision"]
        row = {"scan_id": sid, "file": PurePosixPath(str(r["entry"].get("relative_path"))).name, "run": r["stem"],
               "scan": r["num"], "decision": decision, "decided_by": by,
               "rule_decision": "drop" if drop else "keep",
               "reasons": drop, "notes": noted,
               "shift_eV": al.get("shift_eV"), "anchor_route": al.get("route")}
        if ov:
            row["override"] = ov
        rows.append(row)
        by_id[sid] = row
    for e in inputs:
        if e.get("skip_reason") and e.get("skip_reason") != DROP_REASON and not any(r["entry"] is e for r in recs):
            sid = f"{PurePosixPath(str(e.get('relative_path'))).name}"
            rows.append({"scan_id": sid, "file": sid, "run": None, "scan": e.get("scan"), "decision": "drop",
                         "decided_by": "rule", "rule_decision": "drop",
                         "reasons": [{"source": "params_file" if e.get("excluded_as") else "input",
                                      "code": e["skip_reason"], "said": f"not usable: {e['skip_reason']}"}],
                         "notes": [], "shift_eV": None, "anchor_route": None})
    kept = [x for x in rows if x["decision"] == "keep"]
    dropped = [x for x in rows if x["decision"] == "drop"]
    overridden = [x for x in rows if x["decided_by"] == "scientist"]
    return {"rule_id": DECISION_RULE_ID, "rule": DECISION_RULE["statement"], "rows": rows, "by_id": by_id,
            "counts": {"scans": len(rows), "kept": len(kept), "dropped": len(dropped),
                       "overridden_by_scientist": len(overridden)},
            "statement": decisions_statement(rows),
            "override_command": ('isaac bundle decide <bundle_dir> --target <group id> --decision set_scan_decision '
                                 '--value keep|drop --scans "<scan id>[,<scan id>...]" --note "<why>" --by "<name>"')}


def decisions_statement(rows: Sequence[Mapping]) -> str:
    kept = [x for x in rows if x["decision"] == "keep"]
    dropped = [x for x in rows if x["decision"] == "drop"]
    def name(x):
        return f"{x['run']} scan {x['scan']}" if x.get("run") else str(x["file"])
    said = f"Scan decisions ({DECISION_RULE_ID}): {len(kept)} of {len(rows)} scans kept, {len(dropped)} dropped."
    if dropped:
        parts = []
        for x in dropped[:20]:
            why = "; ".join(r["said"] for r in x["reasons"]) if x["reasons"] else ""
            if x["decided_by"] == "scientist":
                why = f"the scientist's decision ({(x.get('override') or {}).get('decided_by')})" + (f"; the rule said: {why}" if why else "")
            parts.append(f"{name(x)} ({why})")
        said += " Dropped: " + "; ".join(parts) + (f"; and {len(dropped) - 20} more" if len(dropped) > 20 else "") + "."
    ov_keep = [x for x in kept if x["decided_by"] == "scientist" and x["rule_decision"] == "drop"]
    if ov_keep:
        said += " Kept on the scientist's word although the rule dropped them: " + ", ".join(name(x) for x in ov_keep) + "."
    noted = [x for x in kept if x["notes"]]
    if noted:
        said += " Kept, with a remark: " + "; ".join(f"{name(x)} ({'; '.join(n['said'] for n in x['notes'])})"
                                                     for x in noted[:10]) + "."
    return said


def _own_noise(r: Mapping, win, np) -> float | None:
    """The scan's own point-to-point noise of IF/I0 in the window, scaled as the engine's shape rms is (to the
    median level): std of second differences / sqrt(6)."""
    a = r.get("aligned")
    if a is None:
        return None
    m = (a.E >= win[0]) & (a.E <= win[1])
    with np.errstate(all="ignore"):
        y = a.IF[m] / a.I0[m]
    y = y[np.isfinite(y)]
    if y.size < 7:
        return None
    level = float(np.nanmedian(np.abs(y))) or 1.0
    return float(np.std(np.diff(y, 2)) / np.sqrt(6.0) / level)


def _edge_snr(r: Mapping, win, np) -> float | None:
    a = r.get("aligned")
    if a is None:
        return None
    with np.errstate(all="ignore"):
        y = a.IF / a.I0
    E = a.E
    pre = (E < win[0]) & np.isfinite(y)
    post = (E > win[0] + 30) & np.isfinite(y)
    if pre.sum() < 3 or post.sum() < 3:
        return None
    step = float(np.median(y[post]) - np.median(y[pre]))
    noise = float(np.std(np.diff(y[pre]))) / np.sqrt(2.0) if pre.sum() > 3 else 0.0
    return abs(step) / noise if noise > 0 else float("inf")


def normalize_once(E, y, n, absorber: Mapping, bt: Mapping, np) -> dict:
    """The kept scans' raw average, normalised ONCE: Victoreen + McMaster (``mback_xrs``, bg_decreasing default)."""
    from xas_analysis.model.mback_xrs import mback_xrs
    from xas_analysis.recipe_init import norm_range

    el, ed, E_edge = absorber.get("element"), absorber.get("edge"), absorber.get("E_edge_eV")
    out: dict = {"model": "victoreen", "engine_function": "xas_analysis.model.mback_xrs.mback_xrs",
                 "bg_decreasing": True, "element": el, "edge": ed, "E_edge_eV": E_edge,
                 "absorber_basis": absorber.get("basis"),
                 "convention": ("raw = background + A x McMaster unit step (Victoreen background c0 + c3 (E/E_edge)^-3, "
                                "c0, c3 >= 0, the step locked at the tabulated edge); norm = (raw - background) / A. "
                                "The post-edge follows the McMaster cross-section (it decays), it is NOT flattened to 1 "
                                "as Athena-style normalisation does; edge steps are therefore a few % larger than a "
                                "flattened post-edge gives.")}
    if not el or not ed or E_edge is None:
        out["error"] = "no element and edge for the absorber: nothing to normalise against"
        return out
    key = f"{el} {ed}"
    fixed = ((bt.get("windows") or {}).get(key) or {}).get("range")
    own = norm_range(float(E_edge), float(E[0]), float(E[-1]))
    rng, basis = own, "group"
    if fixed:
        # the beamtime's window; its OUTER ends clipped to this group's data when its scans start later or end
        # sooner (the pre-edge end and post-edge start, which set the step, stay the series' own)
        lo, hi = max(fixed[0], round(float(E[0]) + 1, 1)), min(fixed[3], round(float(E[-1]) - 1, 1))
        if lo <= fixed[1] - 10 and hi >= fixed[2] + 50:
            rng, basis = [lo, fixed[1], fixed[2], hi], ("beamtime" if [lo, hi] == [fixed[0], fixed[3]] else "beamtime_clipped")
    out["window_eV"] = rng
    out["window_basis"] = {
        "beamtime": "the beamtime's one window for this edge (recipe_init.norm_range on the modal grid): the same for "
                    "every compared series",
        "beamtime_clipped": "the beamtime's one window for this edge, its outer ends clipped to this group's data (the "
                            "pre-edge end and post-edge start are the series' own)",
        "group": "the group's own window (its scans do not cover the beamtime's): recipe_init.norm_range"}[basis]
    out["window_fixed_for_series"] = basis in ("beamtime", "beamtime_clipped")
    out["params"] = {"model": "victoreen", "element": el, "core": ed, "range": rng, "bg_decreasing": True}
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        try:
            r = mback_xrs(el, E, y, rng, ed)
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"{type(exc).__name__}: {exc}"[:300]
            return out
        A = _f(r.info["A_edge"])
        out.update(A_edge=A, norm=np.asarray(r.norm_xas, float), mu=np.asarray(r.mu, float),
                   bg=np.asarray(r.info["bg"], float), background=r.info.get("bg_params"),
                   pre_rms=_f(r.info.get("pre_rms")), post_rms=_f(r.info.get("post_rms")),
                   post_level=_post_level(r, np))
        spread = []
        for dp in WINDOW_VARIANTS["pre_hi"]:
            for dl in WINDOW_VARIANTS["post_lo"]:
                for dh in WINDOW_VARIANTS["post_hi"]:
                    w = [rng[0], rng[1] + dp, rng[2] + dl, rng[3] + dh]
                    if w[1] <= w[0] + 5 or w[3] <= w[2] + 30:
                        continue
                    try:
                        a = _f(mback_xrs(el, E, y, w, ed).info["A_edge"])
                    except Exception:  # noqa: BLE001
                        a = None
                    if a:
                        spread.append((w, a))
    if spread and A:
        vals = [a for _, a in spread]
        med = statistics.median(vals)
        out["uncertainty"] = {"window_spread_of_A": (max(vals) - min(vals)) / med if med else None,
                              "windows_tried": len(vals), "A_min": min(vals), "A_max": max(vals),
                              "statement": (f"The edge step A depends on the normalisation window: over {len(vals)} "
                                            f"windows around the one used, A spreads {100 * (max(vals) - min(vals)) / med:.1f} % "
                                            "(max - min over the median). The engine's own measurement (normalization.md): "
                                            "noise 1.7 % on A, window choice 9-15 % at normal loading and 16-20 % at about "
                                            "1 % Ir loading, the dominant systematic at low loading.")}
    return out


def _post_level(r, np) -> float | None:
    p = r.info.get("i_post")
    if p is None or not np.any(p):
        return None
    mu = np.asarray(r.mu, float)[p]
    nr = np.asarray(r.norm_xas, float)[p]
    ok = np.isfinite(mu) & np.isfinite(nr) & (mu > 0)
    return _f(np.median(nr[ok] / mu[ok])) if ok.any() else None


def _qc(res, recs, kept, table, nm, E, y, e0, absorber, bt, np):
    reasons_fail, reasons_warn, st = [], [], {}
    A = nm.get("A_edge")
    metrics = {"scans_listed": len(res["inputs"]), "scans_usable": len(recs), "scans_used": len(kept),
               "scans_dropped": table["counts"]["dropped"], "points": int(E.size), "e0_eV": e0, "edge_step": A,
               "pre_edge_rms_over_step": nm.get("pre_rms"), "post_edge_level": nm.get("post_level"),
               "window_spread_of_A": (nm.get("uncertainty") or {}).get("window_spread_of_A")}
    shifts = [r["alignment"]["shift_eV"] for r in kept if r["alignment"]["ok"]]
    if shifts:
        metrics["shift_mean_eV"] = float(statistics.fmean(shifts))
        metrics["shift_spread_eV"] = float(statistics.pstdev(shifts)) if len(shifts) > 1 else 0.0
    if not A or A <= 0:
        reasons_fail.append("no_edge")
        st["no_edge"] = "The fitted edge step is not positive: the normalisation found no edge."
    elif A > 2 * float(np.ptp(y)):
        reasons_fail.append("edge_step_implausible")
        st["edge_step_implausible"] = (f"The edge step {A:.4g} is more than twice the curve's whole range "
                                       f"({float(np.ptp(y)):.4g}): the fit did not describe the data.")
    elif nm.get("pre_rms") and 1.0 / nm["pre_rms"] < EDGE_MIN_NOISE_MULTIPLE:
        reasons_fail.append("no_edge")
        st["no_edge"] = (f"The edge step is only {1.0 / nm['pre_rms']:.1f} times the pre-edge scatter (under "
                         f"{EDGE_MIN_NOISE_MULTIPLE:g}): the edge is not distinguishable.")
    pl = nm.get("post_level")
    if pl is not None and not (POST_LEVEL_RANGE[0] < pl < POST_LEVEL_RANGE[1]):
        reasons_fail.append("post_edge_not_at_1")
        st["post_edge_not_at_1"] = f"The normalised post-edge sits at {pl:.2f} of the McMaster step, far from 1."
    sp = metrics["window_spread_of_A"]
    if sp is not None and sp > WINDOW_SPREAD_WARN:
        reasons_warn.append("normalization_window_sensitive")
        st["normalization_window_sensitive"] = (nm.get("uncertainty") or {}).get("statement")
    if len(kept) == 1:
        reasons_warn.append("single_scan")
    if any(r["alignment"].get("route", "") and str(r["alignment"]["route"]).endswith("_fallback") for r in kept):
        reasons_warn.append("anchor_fallback_route_used")
        st["anchor_fallback_route_used"] = ("Some scans had no usable foil edge and were aligned on the I0 glitch "
                                            "instead (both tied to the one beamtime reference).")
    route0 = ((bt.get("routes") or [{}])[0].get("route") or {}).get("mode")
    if route0 == "none":
        reasons_warn.append("no_energy_reference")
        st["no_energy_reference"] = (bt.get("routes") or [{}])[0].get("statement")
    if table["counts"]["dropped"] > table["counts"]["kept"]:
        reasons_warn.append("most_scans_dropped")
    if any(rr["source"] == "logbook" and rr.get("strength") == "inferred"
           for x in table["rows"] if x["decision"] == "drop" for rr in x["reasons"]):
        reasons_warn.append("logbook_inferred_note_applied")
    if not nm.get("window_fixed_for_series"):
        reasons_warn.append("normalization_window_group_own")
    if "not confirmed" in str(absorber.get("basis")) or "suggestion" in str(absorber.get("basis")):
        st["absorber_unconfirmed"] = (f"The normalisation used {absorber.get('element')} {absorber.get('edge')}: "
                                      f"{absorber.get('basis')}.")
    st[DECISIONS_KEY] = table["statement"]
    verdict = "fail" if reasons_fail else ("warn" if reasons_warn else "pass")
    return verdict, reasons_fail + reasons_warn, st, metrics


def _shift_table(recs, bt) -> dict:
    rows = []
    for r in recs:
        al = r.get("alignment") or {}
        rows.append({"scan_id": r["scan_id"], "file": PurePosixPath(str(r["entry"].get("relative_path"))).name,
                     "route": al.get("route"), "method": al.get("method"), "anchor_eV": al.get("anchor_eV"),
                     "shift_eV": al.get("shift_eV"), "ok": al.get("ok"),
                     **({"fit": al["fit"]} if al.get("fit") else {}), **({"tried": al["tried"]} if al.get("tried") else {})})
    ok = [x["shift_eV"] for x in rows if x["ok"] and x["shift_eV"] is not None]
    return {"rows": rows, "mean_eV": statistics.fmean(ok) if ok else None,
            "spread_eV": statistics.pstdev(ok) if len(ok) > 1 else None,
            "statement": (f"Every scan was shifted onto ONE beamtime reference (one shift and one interpolation per "
                          f"scan): {len(ok)} of {len(rows)} scans aligned"
                          + (f", shifts {1000 * min(ok):+.0f} to {1000 * max(ok):+.0f} meV" if ok else "") + ".")}


def _reference_view(bt, recs) -> dict:
    routes = []
    for info in bt.get("routes") or ():
        route = info.get("route") or {}
        routes.append({"mode": route.get("mode"), "method": route.get("method"),
                       "window_eV": route.get("shape_window_eV") or route.get("window_eV"),
                       "ref_signal": route.get("ref_signal"), "glitch_dips": route.get("glitch_dips"),
                       "fallback": bool(route.get("fallback")), "reference_group_id": info.get("reference_group_id"),
                       "reference_name": info.get("reference_name"), "reference_anchor_eV": info.get("anchor_eV"),
                       "reference_scans": len(info.get("scans") or ()), "reference_anchor_std_eV": info.get("std_eV")})
    sv = bt.get("survey") or {}
    why = list(((sv.get("recommendation") or {}).get("why")) or ())
    mode = routes[0]["mode"] if routes else None
    plain = {"ref_foil": "an in-scan reference foil in transmission", "glitch_I0": "the I0 glitch",
             "foil_timeline": "separate foil scans over time", "none": "no energy reference"}.get(mode, str(mode))
    first = routes[0] if routes else {}
    stmt = (f"Energy reference: {plain}"
            + (f" ({first.get('method')} fit, window {first.get('window_eV')})" if first.get("window_eV") else "")
            + (f", anchored on the earliest group {first.get('reference_name')} (mean of {first.get('reference_scans')} "
               f"scans, {first.get('reference_anchor_eV'):.4f} eV)" if first.get("reference_anchor_eV") else "")
            + ". The mono was foil-calibrated by the beamline staff at the start of the beamtime; every scan of every "
              "sample is aligned to this one reference, never to its own sample's edge.")
    if len(routes) > 1:
        stmt += " A scan whose foil edge is not usable is aligned on the I0 glitch instead."
    return {"routes": routes, "why": why, "mono_reset_lines": (sv.get("calibration_log") or [])[:20],
            "survey_warnings": list(sv.get("warnings") or ())[:10], "statement": stmt,
            "beamtime_fingerprint": bt.get("fingerprint")}


def _quick_merges(group, ctx, recs, kept, E, y, nm, e0, absorber, np) -> list[dict]:
    """The MERGE quick-merge comparison (quick_merge.py), with the quick merge normalised the way this result is."""
    from xas_analysis.model.mback_xrs import mback_xrs

    from . import quick_merge as QM

    rng = nm["window_eV"]
    e0v = e0 if e0 is not None else absorber.get("E_edge_eV")
    rp = {"pre1": rng[0] - e0v, "pre2": rng[1] - e0v, "norm1": rng[2] - e0v, "norm2": rng[3] - e0v, "nnorm": None}
    nmv = {"resolved_params": rp, "e0_eV": e0v, "edge_step": nm["A_edge"], "norm": nm["norm"]}
    M = np.array([np.interp(E, r["aligned"].E, r["aligned"].IF / r["aligned"].I0, left=np.nan, right=np.nan) for r in kept])

    def normalizer(e, yy):
        r = mback_xrs(absorber["element"], e, yy, rng, absorber["edge"])
        return np.asarray(r.norm_xas, float), float(r.info["A_edge"])

    return QM.compare_group(group, ctx, grid_ok=E, mean=y, nm=nmv, M=M, grid=E, used_entries=[r["entry"] for r in kept],
                            inputs=[r["entry"] for r in recs], normalizer=normalizer)


# --- the plot ----------------------------------------------------------------------------------------------------


def plot(path: Path, group, recs, table, E, y, nm, e0, absorber, np) -> bool:
    from ._deps import require

    mpl = require().get("matplotlib")
    if mpl is None:
        return False
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 8.4), sharex=False)
    lo, hi = (absorber["E_edge_eV"] - 20, absorber["E_edge_eV"] + 60) if absorber.get("E_edge_eV") else (E[0], E[-1])
    shown = 0
    for r in recs:
        a = r.get("aligned")
        row = table["by_id"][r["scan_id"]]
        if a is None:
            continue
        with np.errstate(all="ignore"):
            yy = a.IF / a.I0
        if row["decision"] == "keep":
            ax1.plot(a.E, yy, lw=0.8, alpha=0.75, label=f"{r['stem'][:18]} #{r['num']} kept ({1000 * (row['shift_eV'] or 0):+.0f} meV)"
                     if shown < 14 else None)
        else:
            why = ", ".join(sorted({x["code"] for x in row["reasons"]})) or "scientist"
            ax1.plot(a.E, yy, lw=0.9, ls="--", alpha=0.8, label=f"{r['stem'][:18]} #{r['num']} DROPPED: {why}"[:70]
                     if shown < 14 else None)
        shown += 1
    ax1.plot(E, y, color="k", lw=1.8, label=f"average of {table['counts']['kept']} kept (raw IF/I0)")
    unaligned = [f"#{r['num']}" for r in recs if r.get("aligned") is None]
    if unaligned:
        # a scan with no energy anchor cannot be drawn on the aligned axis: named, never hidden
        ax1.plot([], [], ls="--", color="0.5", label=f"not drawn (no energy anchor, dropped): {', '.join(unaligned)}"[:70])
    ax1.set_xlim(lo, hi)
    ax1.set_ylabel("raw IF/I0 (aligned)")
    ax1.legend(fontsize=6, loc="upper right", ncol=1)
    ax1.set_title(f"{group['group_id']} - aligned scans (kept solid, dropped dashed)", fontsize=9)
    ax2.plot(E, nm["norm"], color="k", lw=1.4, label="normalised average (Victoreen + McMaster)")
    ax2.plot(E, nm["mu"], color="tab:red", lw=0.9, ls=":", label=f"McMaster {absorber.get('element')} {absorber.get('edge')} unit step")
    w = nm.get("window_eV") or []
    for k, x in enumerate(w):
        ax2.axvline(x, color="0.7", lw=0.6, ls="--", label="normalisation windows" if k == 0 else None)
    if e0:
        ax2.axvline(e0, color="tab:blue", lw=0.6, label=f"E0 {e0:.2f} eV")
    ax2.set_xlabel("energy (eV)")
    ax2.set_ylabel("normalised")
    ax2.legend(fontsize=7, loc="lower right")
    fig.text(0.01, 0.005, f"DRAFT protocol {PROTOCOL_ID} ({ENGINE_NAME} {engine_version()} + ISAAC adapter) - not "
             "reviewed by a beamline scientist. Raw mu merged, normalised once.", fontsize=7)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, dpi=90)
    plt.close(fig)
    return True


# --- what `bundle show` / `bundle list` say ------------------------------------------------------------------------


def list_brief(r: Mapping) -> str | None:
    t = r.get(DECISIONS_KEY)
    if not isinstance(t, Mapping):
        return None
    c = t.get("counts") or {}
    s = f"{c.get('kept')} of {c.get('scans')} scans kept, {c.get('dropped')} dropped"
    if c.get("overridden_by_scientist"):
        s += f" ({c['overridden_by_scientist']} by the scientist)"
    return s + f" ({DECISION_RULE_ID})"


def show_blocks(r: Mapping, *, full: bool = False) -> dict:
    """``bundle show processing-result``'s v1 blocks, in plain words: the engine, the energy reference and its
    evidence, the shift table, the decision table and the normalisation convention."""
    out: dict = {}
    eng = r.get(ENGINE_KEY)
    if isinstance(eng, Mapping):
        out["engine"] = {k: eng.get(k) for k in ("protocol_id", "engine", "engine_version", "reason", "statement") if eng.get(k)}
    ref = r.get(REFERENCE_KEY)
    if isinstance(ref, Mapping):
        out["energy_reference"] = {"statement": ref.get("statement"), "routes": ref.get("routes"),
                                   "evidence": ref.get("why"), "mono_reset_lines": ref.get("mono_reset_lines"),
                                   **({"survey_warnings": ref["survey_warnings"]} if ref.get("survey_warnings") else {})}
    sh = r.get(SHIFTS_KEY)
    if isinstance(sh, Mapping):
        rows = sh.get("rows") or []
        out["scan_shifts"] = {"statement": sh.get("statement"),
                              "rows": [f"{x['file']}: {('%+.1f meV' % (1000 * x['shift_eV'])) if x.get('shift_eV') is not None else 'no shift'}"
                                       f" ({x.get('route') or 'no anchor'})" for x in (rows if full else rows[:30])],
                              **({"rows_not_shown": len(rows) - 30} if not full and len(rows) > 30 else {})}
    t = r.get(DECISIONS_KEY)
    if isinstance(t, Mapping):
        rows = t.get("rows") or []
        def line(x):
            why = "; ".join(y["said"] for y in x.get("reasons") or ()) or "no reason to drop it"
            s = f"{x.get('run') or x.get('file')} scan {x.get('scan')}: {x['decision'].upper()}"
            if x.get("decided_by") == "scientist":
                ov = x.get("override") or {}
                s += f" (the scientist's decision, {ov.get('decided_by')}, {ov.get('decision_id')}; the rule said {x['rule_decision']}: {why})"
            else:
                s += f" ({why})"
            if x.get("notes"):
                s += " - remark: " + "; ".join(n["said"] for n in x["notes"])
            return s
        shown = rows if full else rows[:30]
        out["scan_decisions"] = {"rule_id": t.get("rule_id"), "rule": t.get("rule"), "counts": t.get("counts"),
                                 "rows": [line(x) for x in shown],
                                 **({"rows_not_shown": len(rows) - len(shown)} if len(rows) > len(shown) else {}),
                                 "override": t.get("override_command")}
    lb = r.get(LOGBOOK_KEY)
    if isinstance(lb, Mapping):
        out["logbook_notes"] = {"statement": lb.get("statement"),
                                "notes": [f"{n.get('run')}: {n.get('action')} {n.get('scans') or ''} ({n.get('strength')}): "
                                          f"{n.get('reason')}" for n in lb.get("notes") or ()]}
    nm = r.get(NORMALIZATION_KEY)
    if isinstance(nm, Mapping):
        out["normalization"] = {"convention": nm.get("convention"),
                                "absorber": f"{nm.get('element')} {nm.get('edge')} ({nm.get('absorber_basis')})",
                                "window_eV": nm.get("window_eV"), "window_basis": nm.get("window_basis"),
                                "edge_step_A": nm.get("A_edge"),
                                "uncertainty": (nm.get("uncertainty") or {}).get("statement"),
                                **({"error": nm["error"]} if nm.get("error") else {})}
    return out
