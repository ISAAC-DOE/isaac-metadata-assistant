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
glitch, else a foil timeline, else none), its anchor method and window, and reads the ``mono reset`` lines. The I0
glitch is then located by a ROBUST CONSENSUS of every scan's own dips (:data:`CONSENSUS`): a minority of scans without
it, or far shifted, never moves it, never makes the beamtime "no reference" and never degrades the other scans (the
survey runs again without them). The reference is the EARLIEST group (closest in time to the staff's foil calibration
of the mono at the start of the beamtime) with good anchors, the robust MEDIAN anchor of its validated scans. Every
scan's anchor is validated against the consensus (:func:`_judge`); a scan that fails is not aligned, says why in plain
words, and is not merged. Every other scan of every group is aligned to that ONE reference, never to its own
sample's edge. No reference at all is a loud state (:data:`NO_REFERENCE_FLAG`) that a bulk approval refuses.

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
from .channels import MODE_FLUORESCENCE, MODE_TRANSMISSION

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
SCREENING = {"anchor_mad": 5, "shape_mad": 6, "min_coverage": 0.9,
             # off-shape = the residual after a free scale AND offset (PROVENANCE.md M7): an edge-step change or a
             # constant fluorescence background is intensity, never shape (rule 3)
             "shape_affine": True}
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
#: THE WHITE-LINE SPREAD OVER WINDOW CHOICES (processing-science audit of 18 Nov 2026, findings 4 and 8): the 12
#: variants above (the edge step's spread, which the QC warning reads, unchanged) understate how much the window
#: choice moves the white line, the quantity people reuse. The white-line height (the normalised maximum within
#: ``WL_RANGE_EV`` of the tabulated edge) is reported over a wider set: the pre-edge end -10..0 eV, the post-edge
#: start 0..+50 eV and its end -100..0 eV from the window used (36 fits, the 12 above among them).
WL_VARIANTS = {"pre_hi": (-10.0, -5.0, 0.0), "post_lo": (0.0, 15.0, 25.0, 50.0), "post_hi": (-100.0, -50.0, 0.0)}
WL_RANGE_EV = (-5.0, 20.0)
#: TENDER FLUORESCENCE (the engine's normalization.md, "Tender fluorescence (S K, BL4-3): background options"): below
#: about 3-4 keV a gas I0 counts ~ E^-3, so IF/I0 rises as (E/E_edge)^p over the WHOLE signal, the pre-edge carries a
#: falling scatter tail and a resonant-Raman foot about 25 eV before the edge. The documented options are used, with
#: the documented window (the pre-edge window ends before the foot). They apply to a fluorescence edge under
#: ``max_edge_eV`` only. Above it, a post-edge IF/I0 that RISES with E (a linear fit over the post-edge window climbs
#: by at least ``rise_min`` of the edge step) changes no option: a disclosed note recommends review (a dilute sample
#: on a large background reads +36 %; distorted spectra do too).
TENDER = {"max_edge_eV": 4000.0, "rise_min": 0.20, "pre_hi_below_edge_eV": 24.0,
          "options": {"response_power": 3.0, "step_slope": 1, "pre_tail": True}}
TENDER_RULE_ID = "isaac.xas.tender_fluorescence.v1"
#: the glitch windows kept out of the normalisation windows: the beamtime's I0 glitch (and every other dip most scans
#: share), +- max(this many FWHM, ``min_half_eV``) around its centre
GLITCH_EXCLUDE = {"fwhm": 1.5, "min_half_eV": 1.0}
POST_LEVEL_RANGE = (0.0, 2.0)          # core.POST_EDGE_LEVEL_RANGE: norm / McMaster mu over the post-edge window
EDGE_MIN_NOISE_MULTIPLE = 5.0          # core.EDGE_MIN_NOISE_MULTIPLE
DROP_REASON = "dropped_by_scan_decision"
#: THE GLITCH CONSENSUS (review of 2ddb27e7, HIGH 1): the I0 glitch is located by a robust consensus of per-scan
#: dips, never by a few sampled scans, so a minority of bad scans (no glitch, a far shift) cannot move it, flip the
#: beamtime to "no reference" or degrade the other scans. A dip is a local minimum of ln I0 minus its quadratic
#: Savitzky-Golay trend (the survey's own glitch_candidates residual), on a step of at most ``max_step_eV``, clear of
#: the tabulated edge by ``edge_clear_eV``; FOUND at ``min_depth`` and ``noise_mult`` robust sigmas of the scan's own
#: residual; CONFIRMED in a scan (the validation) at a quarter of the consensus depth and ``confirm_noise_mult``
#: sigmas. The consensus is the position most scans share (within ``cluster_eV``), then the median of each scan's
#: nearest dip; it holds when more than ``majority`` of the scans carry it. A per-scan anchor is accepted when its
#: fit is ok, inside the fit window, and its offset from its own dip agrees with the beamtime's median offset within
#: max(``fit_tol_eV``, ``fit_tol_steps`` grid steps).
CONSENSUS = {"min_depth": 0.003, "noise_mult": 6.0, "confirm_noise_mult": 3.0, "confirm_depth_frac": 0.25,
             "edge_clear_eV": 3.0, "max_step_eV": 1.0, "cluster_eV": 1.0, "majority": 0.5, "recenter_eV": 0.5,
             "fit_tol_eV": 0.25, "fit_tol_steps": 1.5}
CONSENSUS_RULE_ID = "isaac.xas.glitch_consensus.v1"
#: the plain reasons a scan is not aligned (decide_scans codes)
NO_REFERENCE = ("no_energy_reference", "no energy reference found in this scan")
FIT_FAILED = ("reference_fit_failed", "reference feature fit failed")
#: the beamtime has no energy reference at all: a loud state, a review flag that blocks a bulk approval
NO_REFERENCE_FLAG = "no_energy_reference"
#: How a REMARK (a note that decides nothing) ends: it says the finding is not a reason to drop the scan, never "kept",
#: because the scan may still be dropped for another reason (a dose or spot rule after it, or the scientist), and a
#: remark must never contradict the decision (end-to-end test on real data, 17 Nov 2026: a DROP row said "kept").
NOT_A_DROP_REASON = "not a reason to drop"

DECISION_RULE = {
    "rule_id": DECISION_RULE_ID,
    "statement": (
        "Every scan gets keep or drop, with its reasons and evidence. A scan is DROPPED when (a) a logbook scan note "
        "says so (exclude, start_from, keep_only; a note read from the logbook as 'inferred' applies too, marked "
        "so; a 'flag' note changes nothing and is shown); or (b) the stability analysis "
        "(isaac.xas.scan_selection_proposal.v0) puts it before the stable window (the sample was still changing) "
        "beyond the noise (an offset of the evolving normalised-shape metric within the stability rule's floor and 3 "
        "x the scans' own sd is kept and said); or (c) the engine's screening flags it: aborted (under 90 % of the "
        "group's grid AND not covering the pre-edge window through the post-edge window: a shorter scan that covers "
        "them is complete), a failed anchor (no fit, a shift beyond the limit, or more than 5 robust sigmas from the "
        "group's median, floor 30 meV), an off-shape scan (its IF/I0, scaled to the group's median, departs more than "
        "6 robust sigmas and 1.5 times the median, and more than twice its own counting noise), a ratio-shape or "
        "post-edge-drift flag whose NORMALISED shape is distorted (after a free scale and offset it still departs 5 % "
        "of the edge step; a within-scan step collapse is shape, a uniformly weaker scan is not), or a dead channel "
        "that shows no edge at all; or (d) a within-spot change at two or more spots (isaac.xas.dose_damage.v3; "
        "each scan normalised on its own, never fitted onto another; under 150 post-edge counts per point at most "
        "spots the rule says it cannot judge and decides nothing): beam damage when it GROWS with dose (scan 3 further from scan 1 than scan 2), the way the edge expects (the white "
        "line falls at Ir and Pt L3) and a fresh spot recovers: the later scans are dropped, the first kept; a first "
        "scan still settling when the later scans agree with each other: the first is dropped; otherwise (two scans per "
        "spot, mixed patterns, a logbook note on CV or equilibration) a question to the scientist, nothing decided "
        "(set_dose_reading decides; a logbook exclude / start_from note always wins). Otherwise it is KEPT. An intensity drop alone never drops a scan: a weaker or noisier "
        "scan is kept and said. An I0 dropout or beam loss (a point or a run under 1 % of the scan's own level that comes "
        "back) excludes those POINTS from the scan's contribution, said, never interpolated, never the scan. "
        "Scans that differ are judged by SPOT first (isaac.xas.spot_decision.v1): when they all sit at spots no kept "
        "scan shares, the spot is what differs, not the sample's evolution; the majority of consistent spots is kept, a "
        "differing spot whose shape differs is dropped with a spot reason, and an even split keeps every spot and flags "
        "'spots disagree'. A scientist's set_scan_decision on a scan overrides all of this, and is shown as theirs."),
    "sources": {"logbook": "a logbook scan note (bundle scan_notes)",
                "stability": "isaac.xas.scan_selection_proposal.v0 (before the stable window)",
                "screening": "xas-analysis screen_report (report-only) + this rule's intensity guard",
                "input": "the scan could not be read or formed (its skip reason)",
                "params_file": "the params file's exclude_scans",
                "dose": "isaac.xas.dose_damage.v3 (beam damage, or a first scan still settling, at each spot)",
                "merge": "a point excluded from the scan's contribution (an I0 dropout), said, never a drop",
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
        self.IF, self.I0, self.I1, self.I2 = rec.get("IF"), rec["I0"], rec.get("I1"), rec.get("I2")
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
    numbers, _basis = B.input_scan_numbers(out["inputs"], run_of)
    num_of = {id(e): n for e, n in zip(out["inputs"], numbers)}
    stem_of = {k: (ctx.runs_by_key.get(k) or {}).get("stem") for k in set(run_of.values())}
    if out["role"] == "alignment":
        out["scope"] = "an alignment group (motor and foil scans): not a sample spectrum the engine reduces"
        # the survey still sees its energy scans (edge scans, foils): never a record, but evidence for the reference
        out["recs"] = _survey_recs(tables, out["role"], sel, ctx, num_of, stem_of)
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
    attempts = R._bl15_2_missing(R._scan_attempts(tables, choice, np), ctx, params)
    # v0's own fallback (run._fallback_from_transmission): a standard taken in transmission first whose I1 is not
    # positive in any scan was measured in fluorescence; v0 reduces it as SCA / I0 fluorescence, and so does v1
    fallback = R._fallback_from_transmission(attempts, choice, tables, role, sel, params)
    if fallback is not None:
        choice = fallback
        attempts = R._bl15_2_missing(R._scan_attempts(tables, choice, np), ctx, params)
    out["choice"] = choice
    standard_in_transmission = False
    if choice.mode != MODE_FLUORESCENCE:
        out["scope"] = (f"measured in {choice.mode} (mu = {choice.signal_name}): the engine reduces fluorescence / "
                        "HERFD (IF/I0) only; transmission-mode samples are NOT SUPPORTED in its scope")
        # a transmission group is never part of the beamtime survey as a sample, but the survey sees its scans (the
        # foil timeline); a STANDARD in transmission is still reduced on v1 (TRANSMISSION_STANDARD), its own recs apart
        out["recs"] = _survey_recs(tables, role, sel, ctx, num_of, stem_of, choice=choice)
        if role != "reference" or choice.mode != MODE_TRANSMISSION:
            return out
        if R._reference_channel_fallback(attempts, choice, tables, role, stems, ctx) is not None:
            return out                     # a foil on I2 read on v0's reference channel: stays on v0, said there
        standard_in_transmission = True
        out["scope"] = (f"a standard measured in transmission (mu = {choice.signal_name}): not part of the beamtime "
                        f"reference survey as a sample; reduced on v1 ({TRANSMISSION_RULE_ID})")
    v1_recs: list[dict] = []
    for k, (entry, table, sa, code) in enumerate(attempts):
        code = code or C.unusable_reason(sa)
        if code:
            entry["skip_reason"] = code
            continue
        rec = _arrays(table, choice, np, transmission=standard_in_transmission)
        if rec is None:
            entry["skip_reason"] = "too_few_points"
            continue
        n = num_of.get(id(entry))
        stem = stem_of.get(entry.get("run_key")) or PurePosixPath(str(entry.get("relative_path"))).stem
        rec.update(entry=entry, sa=sa, num=n if isinstance(n, int) else k + 1, stem=stem,
                   scan_id=f"{stem}#{n}" if isinstance(n, int) else f"{stem}#pos{k + 1}",
                   run_key=entry.get("run_key"), header=table.header_lines, time=_scan_time(table.header_lines),
                   motor_lines=tuple(getattr(table, "motor_lines", ()) or ()),
                   template=R._scan_template(table.header_lines))
        if not R._is_energy_scan(rec["template"], choice.energy) or R.not_an_energy_axis(rec["E"], params):
            entry["skip_reason"] = "not_an_energy_scan"
            continue
        v1_recs.append(rec)
    if standard_in_transmission:
        if v1_recs:
            out["transmission_v1"] = True
            out["v1_recs"] = v1_recs
            out["transmission_offset"] = _transmission_offset(v1_recs, np)
        return out
    out["recs"] = v1_recs
    if not out["recs"]:
        out["scope"] = "no usable energy scan (v0 says why)"
        return out
    return out


def _survey_recs(tables, role: str, sel, ctx, num_of: Mapping, stem_of: Mapping, *, choice=None) -> list[dict]:
    """The energy scans of a group that is never a v1 record (an alignment group, a foil or other transmission
    group), as the survey reads them: E, I0, I1, I2 and the scan time (no fluorescence signal: ``IF`` is None). The
    survey's foil timeline and its edge-scan findings need them (calibration.md: separate foil scans in the folder ->
    ``foil_timeline``). Motor scans are left out (:func:`run._is_energy_scan`)."""
    from . import run as R

    np, params = ctx.np, ctx.params
    out = []
    for k, (entry, table) in enumerate(tables):
        if table.format_id not in ENGINE_FORMATS:
            continue
        c = choice
        if c is None or not (table.has(c.energy) and table.has(c.i0 or "")):
            c = None
            for rl in dict.fromkeys((role, "reference", "sample")):
                cc = R.choose_channels(table, params=params, role=rl, bl15_selection=sel, **R.bl15_2_kw(table, ctx))
                if cc.energy is not None and cc.i0 and table.has(cc.i0):
                    c = cc
                    break
        if c is None:
            continue
        template = R._scan_template(table.header_lines)
        if not R._is_energy_scan(template, c.energy):
            continue
        rec = _arrays(table, c, np, signal=False)
        if rec is None:
            continue
        n = num_of.get(id(entry))
        stem = stem_of.get(entry.get("run_key")) or PurePosixPath(str(entry.get("relative_path"))).stem
        rec.update(entry=entry, num=n if isinstance(n, int) else k + 1, stem=stem,
                   scan_id=f"{stem}#{n}" if isinstance(n, int) else f"{stem}#pos{k + 1}", run_key=entry.get("run_key"),
                   header=table.header_lines, time=_scan_time(table.header_lines), template=template,
                   motor_lines=tuple(getattr(table, "motor_lines", ()) or ()), survey_only=True)
        out.append(rec)
    return out


def _arrays(table, choice, np, *, signal: bool = True, transmission: bool = False) -> dict | None:
    """Sorted, duplicate-averaged E, IF, I0, I1, I2, sec of one scan (finite E, I0 > 0, finite IF). ``signal=False``
    (a foil or alignment scan the survey reads): no fluorescence signal, ``IF`` is None. ``transmission``: ``IF`` is
    ln(I0/I1) x I0, so IF/I0 is the transmission mu (:data:`TRANSMISSION_RULE_ID`; the group's constant offset is
    added by :func:`_transmission_offset`)."""
    cols = table.columns
    E = np.asarray(cols[choice.energy], float)
    if transmission:
        with np.errstate(all="ignore"):
            I0_, I1_ = np.asarray(cols[choice.i0], float), np.asarray(cols[choice.transmission_after], float)
            IF = np.where((I0_ > 0) & (I1_ > 0), np.log(I0_ / I1_), np.nan) * I0_
    elif signal:
        IF = np.sum([np.asarray(cols[c], float) for c in choice.signal_columns], axis=0)
    else:
        IF = np.zeros(E.size)
    I0 = np.asarray(cols[choice.i0], float)
    extra = {}
    for name, cands in (("I1", ("I1", "It", "IT")), ("I2", ("I2", "Iref", "IR")), ("sec", ("sec", "Seconds", "Real time clock"))):
        c = next((c for c in cands if table.has(c)), None)
        extra[name] = np.asarray(cols[c], float) if c else None
    fin = np.isfinite(E) & np.isfinite(IF) & np.isfinite(I0)
    drop = i0_dropouts(E, I0, fin, np)
    ok = fin & (I0 > 0) & ~drop
    if ok.sum() < C.MIN_SCAN_POINTS:
        return None
    # contiguous runs in energy order among the finite points
    fin_idx = np.flatnonzero(fin)
    rank = np.empty(E.size, int)
    rank[fin_idx[np.argsort(E[fin_idx], kind="stable")]] = np.arange(fin_idx.size)
    dropouts: list[dict] = []
    if drop.any():
        prev = None
        for k in sorted(np.flatnonzero(drop), key=lambda i: rank[i]):
            if dropouts and prev is not None and rank[k] == rank[prev] + 1:
                dropouts[-1].update(E_end_eV=float(E[k]), points=dropouts[-1]["points"] + 1,
                                    I0=min(dropouts[-1]["I0"], float(I0[k])))
            else:
                dropouts.append({"E_eV": float(E[k]), "E_end_eV": float(E[k]), "points": 1, "I0": float(I0[k])})
            prev = k
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
    if not signal:
        arr["IF"] = None
    return {"E": E, **arr, "i0_dropouts": dropouts}


#: A STANDARD MEASURED IN TRANSMISSION ON v1 (processing-science audit of 18 Nov 2026, finding 7; the scientists' rule:
#: every scan of all samples is aligned on its in-scan reference). v0 reduced transmission standards without per-scan
#: alignment and with another normalisation (larch pre_edge, flattened) than the samples'. On v1 a standard (role
#: reference) whose channel choice is transmission is read as mu = ln(I0/I1), aligned per scan to the SAME beamtime
#: reference as the samples (the foil on I1/I2, else the I0 glitch), merged and normalised exactly as they are
#: (Victoreen + McMaster). It is never part of the beamtime survey as a sample (the reference group stays a sample's).
#: ln(I0/I1) carries the ion chambers' gain ratio as a constant and may be negative; one constant per group
#: (``offset``: the curve's span minus its minimum, so it starts at its own span above zero) is added while it is
#: processed, because the Victoreen background is non-negative, and subtracted again in merged.csv and the
#: background column; the normalised curve does not depend on a constant. The dose rule is not applied (IF is not a
#: count). No thickness, pinhole or harmonic correction. Transmission SAMPLES stay on v0 (not in the engine's scope), and
#: so does a foil on I2 that v0 reads on its reference channel (run._reference_channel_fallback).
TRANSMISSION_RULE_ID = "isaac.xas.transmission_standard_on_v1.v1"
TRANSMISSION_SAID = ("Measured in transmission: mu = ln(I0/I1), aligned per scan to the beamtime reference and "
                     "normalised as the samples are ({rule}); a constant {offset:.4g} is added while it is "
                     "normalised (the Victoreen background is non-negative) and subtracted in merged.csv; no "
                     "thickness, pinhole or harmonic correction; the beam-damage rule is not applied (the signal is "
                     "not a count).")


def _transmission_offset(recs: Sequence[dict], np) -> float:
    """Add the group's one constant to every transmission rec's IF/I0 (:data:`TRANSMISSION_RULE_ID`); returns it."""
    with np.errstate(all="ignore"):
        mus = np.concatenate([r["IF"] / r["I0"] for r in recs])
    mus = mus[np.isfinite(mus)]
    if not mus.size:
        return 0.0
    lo, hi = float(np.min(mus)), float(np.max(mus))
    offset = (hi - lo) - lo
    for r in recs:
        r["IF"] = r["IF"] + offset * r["I0"]
    return offset


#: I0 DROPOUTS AND BEAM LOSSES: a point, or a contiguous run of points, whose I0 falls under ``frac`` of the scan's own
#: level just before it (the median of the ``half`` good points before) and comes BACK (the median of the ``half``
#: points after it is at least ``return_frac`` of that level) is non-physical (I0 = 1 count among ~34 000; a beam loss
#: of 11-20 points). Those POINTS are excluded from the scan's contribution to the average (the other scans cover
#: them), disclosed per run, never interpolated, and never drop the scan. A filter change (x10, x100) is a step that
#: does not come back, so it is never masked; a run longer than ``max_run`` points is not a dropout either.
I0_DROPOUT = {"frac": 0.01, "half": 5, "return_frac": 0.2, "max_run": 100}
I0_DROPOUT_CODE = "i0_dropout_point_excluded"


def i0_dropouts(E, I0, fin, np):
    """Boolean mask of the :data:`I0_DROPOUT` points of one scan (``fin``: the finite points, in file order)."""
    mask = np.zeros(E.size, bool)
    idx = np.flatnonzero(fin)
    h = I0_DROPOUT["half"]
    if idx.size < 2 * h + 1:
        return mask
    order = idx[np.argsort(E[idx], kind="stable")]
    v = I0[order].astype(float)
    hit = np.zeros(v.size, bool)
    n = v.size
    j = 1
    while j < n:
        before = v[max(0, j - h):j][~hit[max(0, j - h):j]]
        before = before[before > 0]
        if before.size < 3:
            j += 1
            continue
        ref = float(np.median(before))
        if not v[j] < I0_DROPOUT["frac"] * ref:
            j += 1
            continue
        k = j
        while k < n and v[k] < I0_DROPOUT["frac"] * ref:
            k += 1
        after = v[k:k + h]
        after = after[after > 0]
        if (k < n and after.size >= 3 and float(np.median(after)) >= I0_DROPOUT["return_frac"] * ref
                and k - j <= I0_DROPOUT["max_run"]):
            hit[j:k] = True
        j = k
    mask[order[hit]] = True
    return mask


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
    if rec.get("IF") is not None:            # a foil / alignment scan the survey reads has no fluorescence signal
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
    if bt.get("calibration"):
        cons, without = _glitch_consensus(reads, (bt.get("edge") or {}).get("E_edge_eV"), ctx.np)
        _apply_consensus(bt, cons, without, reads, groups, ctx)
    _reference(bt, reads, ctx)
    _anchor_all(bt, reads, ctx)
    _windows(bt, reads)
    return bt


def _survey(reads: Mapping, groups: Sequence[Mapping], ctx, *, exclude: frozenset = frozenset()) -> dict:
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
        elif R._names_a_foil(gr.get("stems") or ()) and gr.get("recs"):
            frole = "foil"                   # a separate foil scan: a foil-timeline candidate (calibration.md)
        else:
            frole = None
        logs += _logs(gr, ctx) if gr.get("inputs") else []
        if frole is None or not gr.get("recs"):
            continue
        fi = FileInfo(path=gid, name=(gr["stems"][0] if gr["stems"] else gid), fmt="spec", role=frole,
                      n_all=len(gr["inputs"]))
        fi.scans = [_scaninfo(r, gr) for r in gr["recs"] if r["scan_id"] not in exclude]
        if not fi.scans:
            continue
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
    # the foil / alignment scans the survey read carry their I0-dropout masking too: said, never silent
    masked = [{"scan_id": r["scan_id"], "said": dropout_said(d)} for gr in reads.values() if gr.get("scope") is not None
              for r in gr.get("recs") or () for d in r.get("i0_dropouts") or ()]
    if masked:
        summary["point_exclusions"] = masked[:100]
    cal = dict((rep.get("recommendation") or {}).get("calibration") or {"mode": "none"})
    return {"calibration": _jsonable(cal), "survey": summary, "edge": _jsonable(edge), "logs": logs,
            "file_groups": {f.name: f._group_id for f in files}, "glitch": _jsonable(rep.get("glitch"))}


# --- the glitch consensus (review of 2ddb27e7, HIGH 1) --------------------------------------------------------------


def _scan_dips(E, I0, E0, np, *, min_depth: float | None = None, mult: float | None = None,
               near: float | None = None, within: float | None = None) -> list[dict]:
    """The sharp dips of one scan's ln I0 (minus its quadratic Savitzky-Golay trend, as the survey's
    ``glitch_candidates`` does on the median of the scans), deepest first: the 3 deepest, or with ``near`` every dip
    within ``within`` eV of it. Each dip: its position (a parabola through its 3 points), depth, FWHM, the grid step
    there and the scan's residual noise. See :data:`CONSENSUS`."""
    from scipy.signal import savgol_filter

    E = np.asarray(E, float)
    I0 = np.asarray(I0, float)
    if E.size < 25 or not np.all(np.isfinite(I0)) or np.any(I0 <= 0):
        return []
    with np.errstate(all="ignore"):
        y = np.log(I0)
    w = min(21, (len(y) // 2) * 2 - 1)
    # a ROBUST trend: the points of a dip are bridged (interpolated) and the trend fitted again, so the dip does not
    # pull its own trend down (a plain trend leaves side-lobe "dips" about 1.6 eV either side of a deep glitch)
    yt = y
    for _ in range(3):
        r = y - savgol_filter(yt, w, 2)
        noise = 1.4826 * float(np.median(np.abs(r - np.median(r))))
        m = r < -max(0.5 * CONSENSUS["min_depth"], 3 * noise)
        if not m.any() or m.all():
            break
        m = m | np.r_[m[1:], False] | np.r_[False, m[:-1]]
        yt = y.copy()
        yt[m] = np.interp(E[m], E[~m], y[~m])
    r = y - savgol_filter(yt, w, 2)
    noise = 1.4826 * float(np.median(np.abs(r - np.median(r))))
    dE = np.gradient(E)
    step_change = np.r_[False, np.abs(np.diff(dE)) > 0.3 * np.minimum(dE[1:], dE[:-1])]
    thr = max(CONSENSUS["min_depth"] if min_depth is None else min_depth,
              (CONSENSUS["noise_mult"] if mult is None else mult) * noise)
    out = []
    for k in range(2, E.size - 2):
        if not (r[k] < r[k - 1] and r[k] <= r[k + 1]):
            continue
        depth = -float(r[k])
        if depth < thr or dE[k] > CONSENSUS["max_step_eV"]:
            continue
        if E0 is not None and abs(E[k] - E0) <= CONSENSUS["edge_clear_eV"]:
            continue
        if near is not None and abs(E[k] - near) > within:
            continue
        if step_change[max(0, k - 2):k + 3].any() and depth < 0.01:
            continue                     # a shallow dip at a grid-region boundary: a trend-filter artefact
        c2, c1, _c0 = np.polyfit(E[k - 1:k + 2] - E[k], r[k - 1:k + 2], 2)
        pos = float(E[k] - c1 / (2 * c2)) if c2 > 0 else float(E[k])
        if not (E[k - 1] <= pos <= E[k + 1]):
            pos = float(E[k])
        half = r[k] / 2
        j1 = k
        while j1 > 0 and r[j1] < half:
            j1 -= 1
        j2 = k
        while j2 < E.size - 1 and r[j2] < half:
            j2 += 1
        out.append({"E_eV": pos, "depth": depth, "fwhm_eV": float(E[j2] - E[j1]), "step_eV": float(dE[k]),
                    "noise": noise})
    out.sort(key=lambda d: -d["depth"])
    return out if near is not None else out[:3]


def _glitch_consensus(reads: Mapping, E0: float | None, np) -> tuple[dict, frozenset]:
    """Where the I0 glitch is, by a robust consensus of every in-scope scan's own dips (:data:`CONSENSUS`): the
    position most scans share, then the median of each scan's nearest dip (and its robust spread). Scans with no dip
    there are counted and named; they never move it."""
    per: dict[str, list[dict]] = {}
    for gr in reads.values():
        if gr.get("scope") is not None:
            continue
        for r in gr["recs"]:
            per[r["scan_id"]] = _scan_dips(r["E"], r["I0"], E0, np)
    n = len(per)
    out: dict = {"rule_id": CONSENSUS_RULE_ID, "scans": n, "found": False, "with_dip": 0}
    idx = np.array([i for i, ds in enumerate(per.values()) for _ in ds], int)
    pos = np.array([d["E_eV"] for ds in per.values() for d in ds], float)
    if not n or not pos.size:
        out["statement"] = f"No scan of the {n} in scope shows a sharp I0 dip: there is no I0 glitch to align on."
        return out, frozenset()
    cl = CONSENSUS["cluster_eV"]

    def support(p):
        return int(np.unique(idx[np.abs(pos - p) <= cl]).size)

    deepest = [ds[0]["E_eV"] for ds in per.values() if ds]
    best = max(deepest, key=lambda p: (support(p), float(sum(d["depth"] for ds in per.values() for d in ds
                                                               if abs(d["E_eV"] - p) <= cl))))
    c = best
    hits: list[dict] = []
    for _ in range(2):                   # the median of each scan's nearest dip, then once more around it
        hits = [min((d for d in ds if abs(d["E_eV"] - c) <= cl), key=lambda d: abs(d["E_eV"] - c))
                for ds in per.values() if any(abs(d["E_eV"] - c) <= cl for d in ds)]
        c = float(np.median([d["E_eV"] for d in hits]))
    hp = np.array([d["E_eV"] for d in hits])
    # other dips most scans share (a second glitch): the fit window stays clear of them
    others = []
    for p in sorted(deepest, key=lambda p: -support(p)):
        if support(p) > CONSENSUS["majority"] * n and abs(p - c) > cl and all(abs(p - q) > cl for q in others):
            others.append(float(p))
    without = sorted(sid for sid, ds in per.items() if not any(abs(d["E_eV"] - c) <= cl for d in ds))
    found = len(hits) >= 2 and len(hits) > CONSENSUS["majority"] * n
    out.update(found=found, E_eV=c, mad_eV=1.4826 * float(np.median(np.abs(hp - c))),
               depth=float(np.median([d["depth"] for d in hits])), fwhm_eV=float(np.median([d["fwhm_eV"] for d in hits])),
               with_dip=len(hits), without_dip=len(without), scans_without_dip=without[:50], other_dips_eV=others)
    out["statement"] = (f"I0 glitch consensus ({CONSENSUS_RULE_ID}): {len(hits)} of {n} scans carry a sharp I0 dip at "
                        f"{c:.2f} eV (robust spread {1000 * out['mad_eV']:.0f} meV, depth {100 * out['depth']:.1f} %)"
                        + (f"; {len(without)} scan(s) show no dip there and are not aligned on it" if without else "")
                        + ("." if found else ": not a majority, so it is not used on its own."))
    return out, frozenset(without)


def _apply_consensus(bt: dict, cons: Mapping, without: frozenset, reads: Mapping, groups: Sequence[Mapping], ctx) -> None:
    """Put the glitch where the per-scan consensus says it is. When some scans lack the glitch there (none, or far
    shifted), the engine's survey (which samples a few scans per file and the median of them) is RUN AGAIN without
    those scans, so its own method choice and window rules see only scans that carry the glitch; a minority of bad
    scans then never moves the glitch, changes the method, or makes the beamtime "no reference"."""
    from xas_analysis.survey import glitch_window

    bt["consensus"] = dict(cons)
    cal = bt.get("calibration")
    if not cal:
        return
    said = bt.setdefault("consensus_said", [])
    if not cons.get("found"):
        g = bt.get("glitch") or {}
        if cal.get("mode") == "glitch_I0" and g.get("E_eV") is not None:
            bt["consensus"]["center_eV"] = float(g["E_eV"])
            bt["consensus"]["center_basis"] = "the survey's glitch (no per-scan majority)"
        return
    c = float(cons["E_eV"])
    if cal.get("mode") in ("none", "glitch_I0") and without:
        again = _survey(reads, groups, ctx, exclude=without)
        cal2 = again.get("calibration") or {}
        if cal2.get("mode") == "glitch_I0" and again.get("glitch"):
            said.append(f"The survey was run again without the {len(without)} scan(s) that show no I0 glitch at "
                        f"{c:.2f} eV (first pass: {cal.get('mode')}"
                        + (f", glitch at {float(bt['glitch']['E_eV']):.2f} eV" if (bt.get("glitch") or {}).get("E_eV") else "")
                        + f", method {cal.get('method')}, window {cal.get('shape_window_eV')}): "
                          f"{cal2.get('method')} fit, window {cal2.get('shape_window_eV')}.")
            bt["calibration"], bt["glitch"] = cal2, again["glitch"]
            bt["survey"]["recommendation_first_pass"] = (bt["survey"] or {}).get("recommendation")
            bt["survey"]["recommendation"] = (again.get("survey") or {}).get("recommendation")
            cal = cal2
    g = dict(bt.get("glitch") or {})
    mode = cal.get("mode")
    # the window keeps clear of the other dips MOST SCANS share
    cands = [{"E_eV": p} for p in cons.get("other_dips_eV") or ()]
    newg = {**g, "E_eV": c, "fwhm_eV": float(g.get("fwhm_eV") or cons.get("fwhm_eV") or 0.5),
            "consensus": CONSENSUS_RULE_ID}
    bt["consensus"]["center_eV"] = c
    bt["consensus"]["center_basis"] = "the per-scan consensus"
    if mode == "none":
        w = glitch_window(newg, cands)
        bt["calibration"] = {"mode": "glitch_I0", "method": "model", "window_eV": [round(c - 1.2, 2), round(c + 1.4, 2)],
                             "shape_window_eV": w, "max_shift_eV": 1.0, "reference_sample": "earliest",
                             "reference_scan": "median", "basis": CONSENSUS_RULE_ID}
        bt["glitch"] = newg
        said.append(f"The survey gave no energy reference, but {cons['with_dip']} of {cons['scans']} scans carry the "
                    f"I0 glitch at {c:.2f} eV: aligned on it (Gaussian-dip model, window {w}).")
    elif mode == "glitch_I0":
        old = g.get("E_eV")
        w = list(cal.get("shape_window_eV") or cal.get("window_eV") or [c - 2.5, c + 2.5])
        if int(cal.get("glitch_dips", 1)) == 2:
            if not (w[0] < c < w[1]) and old is not None:
                d = c - float(old)
                cal["shape_window_eV"] = [round(w[0] + d, 2), round(w[1] + d, 2)]
                cal["window_eV"] = list(cal["shape_window_eV"])
                bt["glitch"] = newg
                said.append(f"The survey placed the glitch doublet at {float(old):.2f} eV; the per-scan consensus "
                            f"puts a dip at {c:.2f} eV: the window moved by {d:+.2f} eV.")
        elif old is None or abs(float(old) - c) > CONSENSUS["recenter_eV"]:
            cal["shape_window_eV"] = glitch_window(newg, cands)
            cal["window_eV"] = [round(c - 1.2, 2), round(c + 1.4, 2)]
            bt["glitch"] = newg
            said.append(f"The survey placed the I0 glitch at {old if old is None else round(float(old), 2)} eV (window "
                        f"{w}); {cons['with_dip']} of {cons['scans']} scans put it at {c:.2f} eV: the fit window is "
                        f"{cal['shape_window_eV']}.")
    elif mode == "ref_foil" and (g.get("E_eV") is None or abs(float(g["E_eV"]) - c) > CONSENSUS["recenter_eV"]):
        bt["glitch"] = newg               # the fallback route's window


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


def _is_glitch(route: Mapping) -> bool:
    return route.get("mode") == "glitch_I0"


def _own_dip(r: Mapping, info: Mapping, route: Mapping, np) -> dict | None:
    """The scan's own I0 dip near the consensus glitch (the deepest within the shift limit), or None."""
    c = info.get("consensus_eV")
    if c is None:
        return None
    ms = float(route.get("max_shift_eV") or MAX_SHIFT_EV["glitch_I0"])
    depth = info.get("consensus_depth")
    dips = _scan_dips(r["E"], r["I0"], info.get("edge_eV"), np,
                      min_depth=CONSENSUS["confirm_depth_frac"] * depth if depth else None,
                      mult=CONSENSUS["confirm_noise_mult"], near=float(c), within=ms)
    return dips[0] if dips else None


def _judge(r: Mapping, fit: tuple, info: Mapping, route: Mapping, np) -> tuple[bool, tuple | None, str | None, dict]:
    """Is this scan's anchor good? ``(ok, (code, plain reason) or None, detail, evidence)``. A glitch anchor must
    have the scan's own dip near the consensus, an ok fit, lie inside the fit window, and sit at the beamtime's usual
    offset from that dip (:data:`CONSENSUS`); a foil anchor needs an ok fit."""
    a, ok, detail = fit
    ev: dict = {}
    if _is_glitch(route) and info.get("consensus_eV") is not None:
        dip = _own_dip(r, info, route, np)
        ms = float(route.get("max_shift_eV") or MAX_SHIFT_EV["glitch_I0"])
        if dip is None:
            c = float(info["consensus_eV"])
            E = r["E"]
            if float(E[-1]) < c + 0.5 * ms or float(E[0]) > c - 0.5 * ms or not np.any(np.abs(E - c) <= 0.5 * ms):
                return False, NO_REFERENCE, (f"the scan does not reach the beamtime's glitch at {c:.2f} eV (it covers "
                                             f"{float(E[0]):.1f}-{float(E[-1]):.1f} eV: aborted, or another grid)"), ev
            return False, NO_REFERENCE, f"no I0 dip within {ms:g} eV of the beamtime's glitch at {c:.2f} eV", ev
        ev = {"own_dip_eV": dip["E_eV"], "own_dip_depth": dip["depth"]}
        if not ok or a is None:
            return False, FIT_FAILED, detail.get("reason") or "the fit did not converge", ev
        w = route.get("shape_window_eV") or route.get("window_eV")
        if route.get("method") == "model" and w and not (w[0] < a < w[1]):
            return False, FIT_FAILED, f"the fitted centre {a:.2f} eV is outside the fit window {w}", ev
        off, med = a - dip["E_eV"], info.get("fit_offset_eV")
        ev["offset_from_own_dip_eV"] = off
        tol = max(CONSENSUS["fit_tol_eV"], CONSENSUS["fit_tol_steps"] * dip["step_eV"])
        if med is not None and abs(off - med) > tol:
            return False, FIT_FAILED, (f"the fitted anchor is {off - med:+.2f} eV away from where this scan's own dip "
                                       f"puts it (tolerance {tol:.2f} eV): the fit took another feature"), ev
        return True, None, None, ev
    if not ok or a is None:
        return False, FIT_FAILED, detail.get("reason") or "fit not ok", ev
    return True, None, None, ev


def _reference(bt: dict, reads: Mapping, ctx) -> None:
    """The beamtime reference, per route: the EARLIEST group with good anchors, the ROBUST MEDIAN of its validated
    scans' anchors (a scan with no glitch, or a fit that took another feature, never enters it)."""
    np = ctx.np
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

    ordered = sorted(inscope, key=t0)
    cons = bt.get("consensus") or {}
    edge = (bt.get("edge") or {}).get("E_edge_eV")
    for route in _routes(bt):
        mode = route.get("mode")
        ref = ordered[0]
        info = {"route": route, "reference_group_id": ref["group_id"],
                "reference_name": ref["stems"][0] if ref["stems"] else None}
        if mode == "none":
            info.update(anchor_eV=0.0, scans=[], anchors=[], std_eV=None, statement=(
                "NO ENERGY REFERENCE: no in-scan foil, no I0 glitch in most scans, no foil scans. No scan was aligned "
                "(every shift is 0): energies are only as good as the beamline calibration. Each result must be "
                "looked at and approved on its own."))
            bt["routes"].append(info)
            continue
        if mode == "foil_timeline":
            info.update(_foil_timeline(route, bt, reads))
            bt["routes"].append(info)
            continue
        if _is_glitch(route) and cons.get("center_eV") is not None:
            info.update(consensus_eV=float(cons["center_eV"]), consensus_depth=cons.get("depth"), edge_eV=edge)
        template = None
        if route.get("method") == "shape":
            template = _pick_template(ordered, info, route, np)
        try:
            fn = _anchor_fns(route, template)
        except Exception as exc:  # noqa: BLE001
            fn, info["error"] = None, f"{type(exc).__name__}: {exc}"[:200]
        if fn is None:
            info.update(anchor_eV=None, scans=[], anchors=[], statement="the reference anchor could not be made")
            bt["routes"].append(info)
            continue
        fits = {r["scan_id"]: _anchor_one(fn, r, route) for gr in inscope for r in gr["recs"]}
        if _is_glitch(route) and info.get("consensus_eV") is not None:
            offs = []
            for gr in inscope:
                for r in gr["recs"]:
                    a, ok, _d = fits[r["scan_id"]]
                    dip = _own_dip(r, info, route, np) if ok and a is not None else None
                    if dip is not None:
                        offs.append(a - dip["E_eV"])
            info["fit_offset_eV"] = float(np.median(offs)) if offs else None
        judged = {r["scan_id"]: _judge(r, fits[r["scan_id"]], info, route, np) for gr in inscope for r in gr["recs"]}
        got = []
        for gr in ordered:
            got = [(r["scan_id"], fits[r["scan_id"]][0]) for r in gr["recs"] if judged[r["scan_id"]][0]]
            if got:
                ref = gr
                break
        info.update(reference_group_id=ref["group_id"], reference_name=ref["stems"][0] if ref["stems"] else None)
        if ref is not ordered[0]:
            info["reference_moved"] = (f"the earliest group {ordered[0]['group_id']} has no scan with a good anchor on "
                                       f"this route; the reference is the next earliest, {ref['group_id']}")
        info["scans"] = [s for s, _ in got]
        info["anchors"] = [a for _, a in got]
        info["statistic"] = "median"
        info["anchor_eV"] = float(np.median(info["anchors"])) if got else None
        info["std_eV"] = float(statistics.stdev(info["anchors"])) if len(got) > 1 else None
        info["mad_eV"] = (1.4826 * float(np.median(np.abs(np.array(info["anchors"]) - info["anchor_eV"])))
                          if got else None)
        info["template_scan"] = template["scan_id"] if template else None
        info["template_group_id"] = next((gr["group_id"] for gr in ordered if any(r is template for r in gr["recs"])),
                                         None) if template else None
        bt["routes"].append(info)
        k = len(bt["routes"]) - 1
        bt.setdefault("_fns", {})[k] = fn
        bt.setdefault("_fits", {})[k] = fits


def _pick_template(ordered: Sequence[Mapping], info: Mapping, route: Mapping, np) -> dict | None:
    """The shape-fit template: on the glitch, the scan of the earliest group that has its own dip closest to that
    group's median dip (never a scan without the glitch); on a foil, the earliest group's first scan."""
    if not (_is_glitch(route) and info.get("consensus_eV") is not None):
        return next((r for r in ordered[0]["recs"]), None)
    for gr in ordered:
        dips = [(r, _own_dip(r, info, route, np)) for r in gr["recs"]]
        dips = [(r, d) for r, d in dips if d is not None]
        if dips:
            med = float(np.median([d["E_eV"] for _r, d in dips]))
            return min(dips, key=lambda x: abs(x[1]["E_eV"] - med))[0]
    return None


def _foil_timeline(route: Mapping, bt: Mapping, reads: Mapping) -> dict:
    """foil_timeline, as the engine's own ``pipeline.foil_timeline`` does it: every scan of every foil the survey kept
    (one detector position, the foils before the mono calibration left out; ``survey.recommend``) is anchored by the
    route's method, ``shape`` (the whole foil edge shifted onto the first foil scan, free scale and offset, over
    ``shape_window_eV``; anchor = that template's inflection - the shift) or ``inflection``; a scan's anchor is then
    linear in time between the foil anchors (constant before the first and after the last). The reference anchor is
    the median anchor of the foil ``reference_foil`` names (an index into the foil LIST, default the first)."""
    import numpy as np
    from xas_analysis.pipeline import _ref_signal_terms, anchor_signal, make_anchor_fn

    gid_of = bt.get("file_groups") or {}
    foils = list(route.get("foils") or ())
    fw = route.get("foil_window_eV") or [-np.inf, np.inf]
    method = route.get("method", "shape")
    per: list[tuple[dict, list[dict]]] = []
    for f in foils:
        gr = reads.get(gid_of.get(f.get("spec"))) or {}
        num, den = _ref_signal_terms(f.get("ref_signal", "ln(I0/I1)"))
        recs = [r for r in gr.get("recs") or () if r.get(num) is not None and r.get(den) is not None]
        per.append((f, recs))
    first = next(((f, rs[0]) for f, rs in per if rs), None)
    if first is None:
        return {"anchor_eV": None, "timeline": [], "scans": [], "statement": "no foil scan could be read"}
    f0, t0 = first
    fc0 = {"mode": "ref_foil", "ref_signal": f0.get("ref_signal", "ln(I0/I1)"), "window_eV": f0.get("window_eV", fw),
           "method": "inflection"}
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        t_anchor, _ti = make_anchor_fn(fc0)(_Sc(t0))
        template = (np.asarray(t0["E"], float), anchor_signal(_Sc(t0), fc0))
        rows, rejected = [], []
        for k, (f, recs) in enumerate(per):
            fc = {**fc0, "ref_signal": f.get("ref_signal", fc0["ref_signal"]), "window_eV": f.get("window_eV", fw)}
            if method == "shape" and t_anchor == t_anchor:
                fn = make_anchor_fn({**fc, "method": "shape", "shape_window_eV": route.get("shape_window_eV") or fw,
                                     "max_shift_eV": float(route.get("max_shift_eV") or 2.0)}, template, t_anchor)
            else:
                fn = make_anchor_fn(fc)
            for r in recs:
                try:
                    a, info = fn(_Sc(r))
                except Exception as exc:  # noqa: BLE001 - a foil scan whose anchor cannot be found is said
                    a, info = None, {"ok": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}
                a = _f(a)
                if a is None or not info.get("ok") or not r.get("time"):
                    rejected.append({"scan": r["scan_id"], "foil": f.get("spec"),
                                     "reason": "no scan time" if a is not None and info.get("ok") else
                                     (info.get("reason") or "the anchor fit was not ok")})
                    continue
                rows.append({"t": r["time"].timestamp(), "anchor_eV": a, "scan": r["scan_id"], "foil": f.get("spec"),
                             "foil_index": k, **({"point_exclusions": [dropout_said(d) for d in r["i0_dropouts"]]}
                                                 if r.get("i0_dropouts") else {})})
    rows.sort(key=lambda x: x["t"])
    if not rows:
        return {"anchor_eV": None, "timeline": [], "scans": [], "rejected": rejected,
                "statement": "no foil scan gave a usable anchor"}
    want = int(route.get("reference_foil", 0) or 0)
    ref_rows = [x for x in rows if x["foil_index"] == want]
    moved = None
    if not ref_rows:
        k = min(x["foil_index"] for x in rows)
        ref_rows = [x for x in rows if x["foil_index"] == k]
        moved = (f"the reference foil {foils[want].get('spec') if want < len(foils) else want} gave no usable anchor; "
                 f"the reference is the next foil, {foils[k].get('spec')}")
    ref_foil = foils[ref_rows[0]["foil_index"]].get("spec")
    anchor = float(np.median([x["anchor_eV"] for x in ref_rows]))
    tl = [{"time": datetime.fromtimestamp(x["t"]).isoformat(), "anchor_eV": x["anchor_eV"], "scan": x["scan"],
           "foil": x["foil"], **({"point_exclusions": x["point_exclusions"]} if x.get("point_exclusions") else {})}
          for x in rows]
    span = max(x["anchor_eV"] for x in rows) - min(x["anchor_eV"] for x in rows)
    out = {"anchor_eV": anchor, "timeline": tl, "scans": [x["scan"] for x in ref_rows],
           "anchors": [x["anchor_eV"] for x in ref_rows], "statistic": "median",
           "reference_name": ref_foil, "reference_group_id": gid_of.get(ref_foil),
           "template_scan": t0["scan_id"], "template_anchor_eV": _f(t_anchor), "method": method,
           "rejected": rejected,
           "statement": (f"Foil timeline: {len(rows)} foil scans of {len({x['foil'] for x in rows})} foils "
                         f"({', '.join(dict.fromkeys(x['foil'] for x in rows))}), anchored by the {method} fit"
                         + (f" onto {t0['scan_id']}" if method == "shape" else "")
                         + f"; the anchors span {1000 * span:.0f} meV over the beamtime; each scan's anchor is linear "
                         f"in time between them. Reference: {ref_foil} ({anchor:.4f} eV)."
                         + (f" {len(rejected)} foil scan(s) gave no usable anchor." if rejected else ""))}
    if moved:
        out["reference_moved"] = moved
    return out


OUTSIDE_TIMELINE_FLAG = "outside_foil_timeline"
OUTSIDE_TIMELINE_SAID = "outside the foil timeline: nearest foil used; drift beyond it unknown"


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
    """Every in-scope scan's anchor and shift: the first route whose anchor is GOOD (:func:`_judge`), within the
    shift limit. A scan no route anchors is not aligned, and says why; it never changes another scan's shift."""
    routes = bt.get("routes") or []
    fns = bt.get("_fns") or {}
    if bt.get("reused"):
        # a reused beamtime block: the anchor functions are rebuilt from the stored routes (their consensus and fit
        # offset are stored with them, so a --group run judges a scan exactly as the full run did)
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
        bt["_fits"] = {}
    fits = bt.get("_fits") or {}
    for gr in reads.values():
        recs = gr.get("v1_recs") if gr.get("transmission_v1") else (gr["recs"] if gr.get("scope") is None else ())
        for r in recs or ():
            r["alignment"] = _align_rec(r, routes, fns, fits, ctx.np)


def _stored_template(info: Mapping, reads: Mapping, ctx) -> dict | None:
    gid = info.get("template_group_id") or info.get("reference_group_id")
    gr = reads.get(gid)
    if gr is None:
        g = next((x for x in getattr(ctx, "_engine_groups", ()) if x["group_id"] == gid), None)
        if g is None:
            return None
        gr = read_group(g, ctx)
    return next((r for r in gr.get("recs") or () if r["scan_id"] == info.get("template_scan")), None)


def _align_rec(r: Mapping, routes: Sequence[Mapping], fns: Mapping, fits: Mapping, np) -> dict:
    tried = []
    for k, info in enumerate(routes):
        route = info.get("route") or {}
        mode = route.get("mode")
        if mode == "none":
            return {"route": "none", "anchor_eV": None, "reference_anchor_eV": None, "shift_eV": 0.0, "ok": True,
                    "tried": tried, "unreferenced": True}
        if mode == "foil_timeline":
            tl = info.get("timeline") or []
            if not tl or not r.get("time") or info.get("anchor_eV") is None:
                tried.append({"route": mode, "code": NO_REFERENCE[0], "reason": "no foil timeline or no scan time"})
                continue
            ts = [datetime.fromisoformat(x["time"]).timestamp() for x in tl]
            t = r["time"].timestamp()
            a = float(np.interp(t, ts, [x["anchor_eV"] for x in tl]))
            out = {"route": mode, "anchor_eV": a, "reference_anchor_eV": info["anchor_eV"],
                   "shift_eV": info["anchor_eV"] - a, "ok": True, "tried": tried}
            if t < min(ts) or t > max(ts):
                out["outside_foil_timeline"] = (f"{OUTSIDE_TIMELINE_SAID} (the scan is "
                                                f"{'before the first' if t < min(ts) else 'after the last'} foil scan)")
            return out
        fn = fns.get(k)
        if fn is None or info.get("anchor_eV") is None:
            tried.append({"route": mode, "code": FIT_FAILED[0], "reason": "no reference anchor for this route"})
            continue
        fit = (fits.get(k) or {}).get(r["scan_id"]) or _anchor_one(fn, r, route)
        good, why, detail, ev = _judge(r, fit, info, route, np)
        a, _ok, fdetail = fit
        shift = (info["anchor_eV"] - a) if a is not None else None
        limit = float(route.get("max_shift_eV") or MAX_SHIFT_EV.get(mode, 1.0))
        if good and shift is not None and abs(shift) > limit:
            good, why, detail = False, FIT_FAILED, f"shift {shift:+.3f} eV beyond the {limit:g} eV limit"
        if good:
            return {"route": mode + ("_fallback" if route.get("fallback") else ""), "method": route.get("method"),
                    "anchor_eV": a, "reference_anchor_eV": info["anchor_eV"], "shift_eV": shift, "ok": True,
                    "fit": {**fdetail, **ev}, "tried": tried}
        tried.append({"route": mode, "anchor_eV": a, "code": why[0], "reason": f"{why[1]}: {detail}", **ev})
    codes = {t.get("code") for t in tried}
    code = NO_REFERENCE if codes == {NO_REFERENCE[0]} else FIT_FAILED
    return {"route": None, "anchor_eV": None, "reference_anchor_eV": None, "shift_eV": None, "ok": False,
            "code": code[0], "said": "; ".join(t["reason"] for t in tried) or code[1], "tried": tried}


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
            "error", "statement", "consensus", "consensus_said")
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
    transmission = bool(gr.get("transmission_v1") and gr.get("v1_recs"))
    if gr.get("scope") is not None and not transmission:
        return False, gr["scope"]
    if not bt.get("calibration"):
        return False, bt.get("statement") or "no beamtime calibration"
    absorber = absorber_of(group, ctx, bt)
    if transmission:
        gr["recs"] = gr["v1_recs"]          # its own v1 recs (the survey's recs carry no signal)
        gr["mode_check"] = {"mode": "transmission", "basis": "the channel choice: a standard in transmission",
                            "offset": gr.get("transmission_offset")}
        return True, None
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
    E_edge0 = absorber.get("E_edge_eV")
    below = E_edge0 is not None and gr["recs"] and all(float(r["E"][-1]) < float(E_edge0) for r in gr["recs"])
    res["measurement_mode"] = measurement_mode_block(gr.get("mode_check"), below_edge=(
        (max(float(r["E"][-1]) for r in gr["recs"]), float(E_edge0), absorber, len(gr["recs"])) if below else None))
    if res["measurement_mode"]["mode"] == BELOW_EDGE:
        res["review_flags"].append(BELOW_EDGE_FLAG)
    elif res["measurement_mode"]["mode"] not in ("fluorescence", "transmission"):
        res["review_flags"].append("measurement_mode_unknown")
    if R.FALLBACK_FLAG in (gr["choice"].flags or ()):
        res["review_flags"].append(R.FALLBACK_FLAG)        # v0's own fallback, never silent
    if below:
        res["channel_choice"] = gr["choice"].to_state()
        res["inputs"] = gr["inputs"]
        said = _below_edge_said(max(float(r["E"][-1]) for r in gr["recs"]), float(E_edge0), absorber, len(gr["recs"]))
        out = R._fail(res, BELOW_EDGE_FLAG, said)
        out["qc"]["statements"] = {BELOW_EDGE_FLAG: said}
        _finish_ids(out, group)
        return [out]
    if ((bt.get("routes") or [{}])[0].get("route") or {}).get("mode") == "none":
        res["review_flags"].append(NO_REFERENCE_FLAG)        # loud, and a bulk approval is refused for it
    res["channel_choice"] = gr["choice"].to_state()
    inputs = gr["inputs"]
    res["inputs"] = inputs
    recs = gr["recs"]
    E_edge = absorber.get("E_edge_eV")
    # --- align: ONE shift and ONE interpolation per scan, onto the group's modal grid
    from xas_analysis.average import AlignedScan, average_scans
    from xas_analysis.calib import align_and_resample
    from xas_analysis.pipeline import screen_report

    grid_rec = modal_grid_scan(recs)
    target = grid_target(grid_rec, np)

    def align_onto(rs, grid):
        out = []
        for r in rs:
            al = r["alignment"]
            if not al["ok"]:
                r["aligned"] = None
                continue
            sec = r["sec"] if r.get("sec") is not None else np.full(r["E"].size, np.nan)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                Y, _ri = align_and_resample(r["E"], np.c_[r["IF"], r["I0"], sec], 0.0, float(al["shift_eV"]), grid)
            _exclude_dropout_points(Y, r, float(al["shift_eV"]), grid, np)
            a = AlignedScan(r["num"], grid, Y[:, 0], Y[:, 1], Y[:, 2],
                            _f(al["anchor_eV"]) if al["anchor_eV"] is not None else 0.0,
                            float(al["shift_eV"]), True, True, key=r["scan_id"])
            r["aligned"] = a
            out.append(a)
        return out

    aligned = align_onto(recs, target)
    # --- screening (report-only: this rule decides)
    win = [E_edge + SCREEN_WINDOW_EV[0], E_edge + SCREEN_WINDOW_EV[1]] if E_edge else [-np.inf, np.inf]
    screen_cfg = {**SCREENING, "window_eV": win, **ratio_screens(E_edge, target, bt)}
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        flags = screen_report(aligned, screen_cfg) if aligned else []
    by_scan: dict[str, list[dict]] = {}
    for f in flags:
        by_scan.setdefault(f["key"], []).append(f)
    # --- stability (isaac.xas.scan_selection_proposal.v0 on the ALIGNED scans)
    stability = _stability(group, ctx, gr, recs, inputs)
    # --- logbook notes
    notes, notes_said = _logbook(ctx, gr, recs)
    # --- the rule
    complete = complete_window(absorber, bt, float(target[0]), float(target[-1]))
    rs = screen_cfg.get("ratio_shape") or {}
    table = decide_scans(recs, by_scan, stability, notes, scientist_scan_decisions(ctx.bundle, group["group_id"]),
                         inputs, target, win, np, complete_eV=complete, E_edge=E_edge,
                         ratio_win=rs.get("window_eV"), ratio_exclude=rs.get("exclude_eV") or ())
    transmission = res["measurement_mode"]["mode"] == "transmission"
    dose = None if transmission else apply_dose_damage(table, recs, stability, np, E_edge, absorber=absorber,
                                                       notes_said=notes_said,
                                                       reading=dose_reading_of(ctx.bundle, group["group_id"]))
    if dose:
        res["dose_damage"] = dose
        if dose.get("outcome") == "question":
            res["review_flags"].append(DOSE_QUESTION_FLAG)       # the scientist decides: a bulk approval refuses it
    spots = apply_spots(table, recs, stability, np)
    if spots:
        res["spots"] = spots
        if spots["outcome"] == SPOTS_DISAGREE_FLAG:
            res["review_flags"].append(SPOTS_DISAGREE_FLAG)      # the scientist looks: a bulk approval refuses it
    kept = [r for r in recs if table["by_id"][r["scan_id"]]["decision"] == "keep" and r.get("aligned") is not None]
    grid_said = None
    if kept and not any(r is grid_rec for r in kept):
        # THE MERGE GRID COMES FROM A KEPT SCAN (end-to-end test on real data, 17 Nov 2026: the grid was named after a
        # dropped scan). The screening above ran on the first modal grid; the kept scans are interpolated again, once
        # each, onto the modal grid of the KEPT scans, so the average's energies are those of a scan that is in it.
        dropped_grid = grid_rec["scan_id"]
        grid_rec = modal_grid_scan(kept)
        target = grid_target(grid_rec, np)
        align_onto(kept, target)
        complete = complete_window(absorber, bt, float(target[0]), float(target[-1]))
        grid_said = (f"the modal grid of the kept scans, from {grid_rec['scan_id']} (the screening grid came from "
                     f"{dropped_grid}, which was dropped)")
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
    # calibration (absolute, none) and alignment (per scan, to the one reference) said apart, in one place (energy_story)
    cal_step["outcome"].update(energy_story(res))
    res["steps"].append(cal_step)
    if not kept:
        out = R._fail(res, "no_scan_kept", f"all {len(recs)} usable scans were dropped by {DECISION_RULE_ID}")
        out["qc"]["statements"] = {"no_scan_kept": table["statement"]}
        _finish_ids(out, group)
        return [out]
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        avg, ainfo = average_scans([r["aligned"] for r in kept], "uniform", 1, True, True)
        matched = coverage_matched_mean([r["aligned"] for r in kept], avg, np)
    ok = np.isfinite(avg["IF_over_I0"]) & (avg["n_kept"] > 0)
    E, y, err, n = target[ok], avg["IF_over_I0"][ok], avg["err"][ok], avg["n_kept"][ok]
    res["steps"].append({"step": "merge", "params": {"statistic": "uniform mean of raw IF/I0 over the kept scans "
                                                                  "(xas_analysis.average.average_scans; err = its standard "
                                                                  "error)" + (", scale-matched where coverage differs "
                                                                              f"({COVERAGE_RULE_ID})" if matched else ""),
                                                     "grid": grid_said or "the group's modal scan grid (a kept scan's), shifted"},
                         "outcome": {"n_scans": len(kept), "points": int(E.size), "grid_from_scan": grid_rec["scan_id"],
                                     **({"coverage_matched": matched} if matched else {})},
                         "flags": [] if len(kept) > 1 else ["single_scan_no_merge"]})
    short = _incomplete(E, complete, E_edge, absorber, len(kept))
    if short is not None:
        # the range is the reason (no edge step to measure a mode on either): not "mode unknown"
        res["review_flags"] = [f for f in res["review_flags"] if f != "measurement_mode_unknown"]
        out = R._fail(res, short[0], short[1])
        out["qc"]["statements"] = {short[0]: short[1], DECISIONS_KEY: table["statement"]}
        _finish_ids(out, group)
        return [out]
    excluded_points = [{"scan_id": r["scan_id"], **d, "said": dropout_said(d)} for r in kept for d in r.get("i0_dropouts") or ()]
    if excluded_points:
        res["point_exclusions"] = {"rule": I0_DROPOUT, "points": excluded_points,
                                   "statement": "; ".join(f"{x['scan_id']}: {x['said']}" for x in excluded_points[:20])
                                   + (f"; and {len(excluded_points) - 20} more" if len(excluded_points) > 20 else "")
                                   + ". Each such point is left out of its scan's contribution to the average (the "
                                     "other scans cover that energy); it is never interpolated, and the scan is kept."}
    res["acquisition"] = acquisition_block(kept, E_edge, transmission, np)
    nm = normalize_once(E, y, n, absorber, bt, np, transmission=transmission)
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
    if e0 is not None:
        res["e0"] = e0_block(E, e0, absorber, np, transmission=transmission)
        e0 = res["e0"]["e0_eV"]
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
    off = float(res["measurement_mode"].get("offset") or 0.0) if transmission else 0.0   # TRANSMISSION_RULE_ID
    _csv(gdir / "merged.csv", ["energy_eV", "mu_mean", "mu_stderr", "n_scans"], [E, y - off, err, n.astype(float)], np)
    _csv(gdir / "normalized.csv", ["energy_eV", "norm", "mcmaster_mu", "background"],
         [E, nm["norm"], nm["mu"], nm["bg"] - off], np)
    R._write(gdir / "scan_decisions.json", R._json_bytes({"group_id": group["group_id"], "rule": DECISION_RULE,
                                                          "scan_decisions": res[DECISIONS_KEY]["rows"],
                                                          "scan_shifts": res[SHIFTS_KEY]}))
    R._write(gdir / "qc.json", R._json_bytes({"group_id": group["group_id"], **res["qc"], "protocol_status": PROTOCOL_STATUS}))
    R._write(gdir / "params.json", R._json_bytes({
        "protocol_id": PROTOCOL_ID, "protocol_version": PROTOCOL_VERSION, "protocol_status": PROTOCOL_STATUS,
        "engine": res[ENGINE_KEY], "screening": screen_cfg,
        "decision_rule": DECISION_RULE, "channel_choice": res["channel_choice"], "absorber": absorber,
        "normalization": res[NORMALIZATION_KEY], "beamtime_fingerprint": bt.get("fingerprint"),
        "energy_reference": res[REFERENCE_KEY]}))
    plotted = False
    try:
        plotted = plot(gdir / "plot.png", group, recs, table, E, y, nm, e0, absorber, np, offset=off,
                       signal="ln(I0/I1)" if transmission else "IF/I0")
    except Exception:  # noqa: BLE001 - a plot failure is a flag, never a processing failure
        plotted = False
    if not plotted:
        res["review_flags"].append("plot_unavailable")
    roles = [("merged", "merged.csv"), ("normalized", "normalized.csv"), ("scan_decisions", "scan_decisions.json"),
             ("qc", "qc.json"), ("params", "params.json")] + ([("plot", "plot.png")] if plotted else [])
    # the decision table enters by its CONTENT (decision_content), never by its file: the file carries the
    # override's decision id and time, which a restated override changes
    data_hashes = sorted((name, R.sha256_file(gdir / name)) for _r, name in roles
                         if name not in ("plot.png", "scan_decisions.json", "qc.json"))
    data_hashes.append(("scan_decisions", hashlib.sha256(json.dumps(decision_content(res[DECISIONS_KEY]["rows"]),
                                                                    default=str).encode()).hexdigest()))
    data_hashes.append(("qc", hashlib.sha256(json.dumps([res["qc"]["verdict"], res["qc"]["reasons"],
                                                         res["qc"]["metrics"]], default=str).encode()).hexdigest()))
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
        quick = _quick_merges(group, ctx, recs, kept, E, y, nm, e0, absorber, np, offset=off)
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


def _grid_key(r: Mapping) -> tuple:
    return (round(float(r["E"][0]), 1), round(float(r["E"][-1]), 1), int(r["E"].size))


def modal_grid_scan(recs: Sequence[Mapping]) -> Mapping:
    """The first scan (in order) on the most common grid of ``recs``: the merge grid is taken from it."""
    from collections import Counter

    modal = Counter(_grid_key(r) for r in recs).most_common(1)[0][0]
    return next(r for r in recs if _grid_key(r) == modal)


def grid_target(grid_rec: Mapping, np):
    """The merge grid: ``grid_rec``'s energies, shifted by its own alignment shift (0 when it is not aligned)."""
    g_shift = grid_rec["alignment"]["shift_eV"] if grid_rec["alignment"]["ok"] else 0.0
    return np.asarray(grid_rec["E"], float) + float(g_shift or 0.0)


def dropout_said(d: Mapping) -> str:
    if int(d.get("points") or 1) > 1:
        return f"points excluded: I0 dropout from {d['E_eV']:.2f} to {d['E_end_eV']:.2f} eV ({d['points']} points)"
    return f"point excluded: I0 dropout ({d['I0']:.0f} counts at {d['E_eV']:.2f} eV)"


def _exclude_dropout_points(Y, r: Mapping, shift: float, target, np) -> None:
    """:data:`I0_DROPOUT`: the grid points that the excluded raw point would have fed (between its kept neighbours)
    are NaN in this scan's contribution, so the average there comes from the other scans: never interpolated across."""
    Es = np.asarray(r["E"], float) + shift
    for d in r.get("i0_dropouts") or ():
        e = float(d["E_eV"]) + shift
        e2 = float(d.get("E_end_eV", d["E_eV"])) + shift
        below, above = Es[Es < e], Es[Es > e2]
        lo = float(below.max()) if below.size else e - 1e-9
        hi = float(above.min()) if above.size else e2 + 1e-9
        m = (target > lo) & (target < hi)
        Y[m, :] = np.nan
        d["grid_points_excluded"] = int(m.sum())


#: a group whose scans all END below the absorption edge: no edge to measure a mode on (never "mode unknown")
BELOW_EDGE = "below_edge"
BELOW_EDGE_FLAG = "scan_never_reaches_edge"
#: a group whose merged scans do not cover the pre-edge window through the post-edge window: nothing to normalise
INCOMPLETE_CODE = "scan_range_incomplete"


def _below_edge_said(end: float, E_edge: float, absorber: Mapping, n: int) -> str:
    return (f"{'this scan never reaches' if n == 1 else 'these scans never reach'} the absorption edge "
            f"({'it ends' if n == 1 else 'they end'} at {end:.1f} eV; the {absorber.get('element')} "
            f"{absorber.get('edge')} edge is at {E_edge:.1f} eV): there is no edge to normalise")


def _incomplete(E, complete, E_edge, absorber: Mapping, n_kept: int) -> tuple[str, str] | None:
    """``(code, plain reason)`` when the merged scans cannot be normalised for their range (an aborted one-scan
    group, a short check scan, a scan that ends below the edge), never a raw fitting error; else None."""
    if not E.size or complete is None:
        return None
    lo, hi = float(E[0]), float(E[-1])
    if E_edge is not None and hi < float(E_edge):
        return BELOW_EDGE_FLAG, _below_edge_said(hi, float(E_edge), absorber, n_kept)
    if lo > complete[0] or hi < complete[1]:
        who = "the only scan" if n_kept == 1 else f"the {n_kept} merged scans"
        return INCOMPLETE_CODE, (f"{who} cover{'s' if n_kept == 1 else ''} {lo:.1f}-{hi:.1f} eV, not the pre-edge "
                                 f"window through the post-edge window ({complete[0]:.1f}-{complete[1]:.1f} eV): an "
                                 "aborted scan or a short check scan, with no edge step to normalise")
    return None


def measurement_mode_block(mc: Mapping | None, below_edge: tuple | None = None) -> dict:
    """What the engine's measurement-mode check said, in plain words (review of 2ddb27e7, MEDIUM 5): v1 runs on a
    fluorescence reading and on an UNKNOWN one (then flagged: v1 reduced it as fluorescence / HERFD anyway). Scans
    that end below the edge (``below_edge``: (end, E_edge, absorber)) say so, never "unknown"."""
    if below_edge is not None:
        said = _below_edge_said(*below_edge)
        return {"mode": BELOW_EDGE, "statement": said[:1].upper() + said[1:] + "."}
    if not mc:
        return {"mode": None, "statement": ("The measurement mode was not checked (no tabulated edge for the check): v1 "
                                            "reduced it as fluorescence / HERFD (IF/I0) anyway; check the mode.")}
    out = {k: mc.get(k) for k in ("mode", "basis", "fluorescence_contrast", "transmission_step",
                                  "name_says_transmission", "scans", "thresholds")}
    if mc.get("mode") == "fluorescence":
        out["statement"] = f"Measured in fluorescence / HERFD: {mc.get('basis')}."
    elif mc.get("mode") == "transmission" and mc.get("offset") is not None:
        out.update(rule_id=TRANSMISSION_RULE_ID, offset=mc["offset"])
        out["statement"] = TRANSMISSION_SAID.format(rule=TRANSMISSION_RULE_ID, offset=float(mc["offset"]))
    else:
        out["statement"] = (f"The measurement mode is UNKNOWN ({mc.get('basis')}; fluorescence contrast "
                            f"{mc.get('fluorescence_contrast')}, ln(I0/I1) step {mc.get('transmission_step')}): v1 "
                            "reduced it as fluorescence / HERFD (IF/I0) anyway; check the mode.")
    return out


def decision_content(rows: Sequence[Mapping] | None) -> list:
    """What a run id depends on from the decision table: each scan's keep / drop and who decided it, never an
    override's decision id, time or note (restating the same override keeps the run id; review LOW 7)."""
    return [[x.get("scan_id"), x.get("decision"), x.get("decided_by"), x.get("rule_decision"), bool(x.get("merged")),
             sorted(str(y.get("code")) for y in x.get("reasons") or ())] for x in rows or ()]


def _finish_ids(res: dict, group: Mapping) -> None:
    """A failed v1 result: its id names the v1 protocol (R._fail hashes v0's id)."""
    h = hashlib.sha256(json.dumps([PROTOCOL_ID, PROTOCOL_VERSION, group["group_id"], res.get("failure"),
                                   decision_content((res.get(DECISIONS_KEY) or {}).get("rows"))], default=str).encode())
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
                                    {"outcome": {"applied_shift_eV": 0.0}}, mode=gr["choice"].mode,
                                    energy_column=gr["choice"].energy)
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


def decide_scans(recs, screen_flags, stability, notes, overrides, inputs, target, win, np, *,
                 complete_eV: Sequence[float] | None = None, E_edge: float | None = None,
                 ratio_win: Sequence[float] | None = None, ratio_exclude: Sequence = ()) -> dict:
    """THE RULE (:data:`DECISION_RULE_ID`): keep or drop for every scan, with its reasons and evidence.
    ``complete_eV``: the edge-relative span a complete scan covers (:func:`complete_window`); ``E_edge``,
    ``ratio_win`` and ``ratio_exclude``: what the normalised-shape guard of the ratio screens measures over."""
    rows, by_id = [], {}
    stab_rows = (stability or {}).get("rows") or {}
    matched: set[str] = set()
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
                item = {"source": "stability", "code": "before_stable_window",
                        "said": "; ".join(st.get("said") or ()) or "the sample was still changing",
                        "evidence": {"stable_window": stability.get("stable_window"),
                                     "evolving_metrics": stability.get("evolving_metrics")}}
                # the SAME noise-based threshold as the shape guard (metric_shifts): an offset of the evolving
                # normalised-shape metric within the noise is not a change (a 0.05 eV white-line offset, no trend)
                evaluated, moved = beyond_noise(sid, stability, np)
                if evaluated and not moved:
                    noted.append({**item, "code": "change_within_noise", "decides": False,
                                  "said": f"{item['said']}; but within the noise (the shape guard's threshold: "
                                          "the stability rule's floor and 3 x the scans' own sd): " + NOT_A_DROP_REASON})
                else:
                    if moved:
                        item["evidence"]["normalised_shape"] = moved
                    drop.append(item)
            other = [x for x in reasons if x != "before_stable_window"]
            if other and st.get("proposal") in ("needs_look", "exclude_proposed"):
                noted.append({"source": "stability", "code": ",".join(other), "said": "; ".join(st.get("said") or ()),
                              "decides": False})
        for d in r.get("i0_dropouts") or ():
            noted.append({"source": "merge", "code": I0_DROPOUT_CODE, "decides": False, "said": dropout_said(d),
                          "evidence": {"E_eV": d["E_eV"], "I0": d["I0"], "rule": I0_DROPOUT}})
        al = r.get("alignment") or {}
        if al.get("outside_foil_timeline"):
            noted.append({"source": "alignment", "code": OUTSIDE_TIMELINE_FLAG, "decides": False,
                          "said": al["outside_foil_timeline"]})
        if not al.get("ok"):
            code = al.get("code") or FIT_FAILED[0]
            plain = NO_REFERENCE[1] if code == NO_REFERENCE[0] else FIT_FAILED[1]
            detail = "; ".join(f"{t.get('route')}: {t.get('reason')}" for t in al.get("tried") or ())
            drop.append({"source": "alignment", "code": code,
                         "said": f"{plain}; not aligned, so not merged" + (f" ({detail})" if detail else ""),
                         "evidence": {"tried": al.get("tried")}})
        for f in screen_flags.get(sid) or ():
            test = f["test"]
            item = {"source": "screening", "code": test, "said": f["reason"],
                    "evidence": {k: f.get(k) for k in ("value", "median", "threshold")}}
            if test == "shape":
                noise = _own_noise(r, win, np)
                item["evidence"]["own_noise"] = noise
                # a NORMALISED-shape metric that moved (white-line energy, edge position, white-line height against
                # the stable scans, beyond the stability rule's floor and 3 x the scans' own sd) is a shape change,
                # however small the residual looks next to the scan's noise (a 0.5 eV white-line shift on a sharp
                # HERFD line): never "noisier"
                moved = metric_shifts(sid, stability, np)
                if moved:
                    item["evidence"]["normalised_shape"] = moved
                    item["said"] = f"{f['reason']}; its normalised shape moved: " + ", ".join(m["said"] for m in moved)
                    drop.append(item)
                    continue
                if noise is not None and f.get("value") is not None and f["value"] <= SHAPE_NOISE_FACTOR * noise:
                    noted.append({**item, "code": "noisier_not_off_shape", "decides": False,
                                  "said": f"{f['reason']}, but within {SHAPE_NOISE_FACTOR:g}x its own counting noise "
                                          f"({noise:.2e}): fewer counts, not another shape; {NOT_A_DROP_REASON} (an "
                                          "intensity effect never drops a scan)"})
                    continue
            if test == "coverage" and complete_eV is not None:
                span = _finite_span(r, np)
                item["evidence"]["covers_eV"] = span
                item["evidence"]["complete_eV"] = list(complete_eV)
                if span and span[0] <= complete_eV[0] and span[1] >= complete_eV[1]:
                    noted.append({**item, "code": "shorter_but_complete", "decides": False,
                                  "said": f"{f['reason']}, but it covers {span[0]:.0f}-{span[1]:.0f} eV, the pre-edge "
                                          f"window through the post-edge window ({complete_eV[0]:.0f}-"
                                          f"{complete_eV[1]:.0f} eV): a shorter, complete scan, {NOT_A_DROP_REASON}"})
                    continue
            if test in ("ratio_shape", "post_drift"):
                dist = shape_distortion(r, recs, ratio_win or win, E_edge, np, exclude=ratio_exclude)
                item["evidence"]["normalised_distortion"] = dist
                if dist is None or not dist["distorted"]:
                    noted.append({**item, "code": "intensity_not_shape", "decides": False,
                                  "said": f"{f['reason']}; after a free scale and offset its normalised shape is the "
                                          "others' (" + (f"residual {100 * dist['max_residual']:.1f} % of the edge step, "
                                                         f"threshold {100 * dist['threshold']:.1f} %" if dist else
                                                         "not measurable") + f"): an intensity effect, {NOT_A_DROP_REASON}"})
                    continue
                item["said"] = (f"{f['reason']}; its NORMALISED shape is distorted (after a free scale and offset it "
                                f"departs {100 * dist['max_residual']:.1f} % of the edge step from the other scans, "
                                f"threshold {100 * dist['threshold']:.1f} %)")
            if test == "dead_channel":
                snr = _edge_snr(r, win, np)
                item["evidence"]["edge_snr"] = snr
                if snr is None or snr >= DEAD_EDGE_SNR_MIN:
                    noted.append({**item, "code": "weak_signal", "decides": False,
                                  "said": f"{f['reason']}; its edge is still visible (edge/noise {snr if snr is None else round(snr, 1)}): "
                                          f"a weaker scan, {NOT_A_DROP_REASON} (an intensity drop alone never drops a scan)"})
                    continue
                item["said"] = f"{f['reason']} and no edge at all (edge/noise {snr:.1f}): no spectrum"
            drop.append(item)
        decision = "drop" if drop else "keep"
        by = "rule"
        keys = [k for k in (sid, PurePosixPath(str(r["entry"].get("relative_path"))).name,
                            str(r["entry"].get("relative_path"))) if k in overrides]
        matched.update(keys)
        ov = overrides[keys[0]] if keys else None
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
        # a scan is merged only when it is kept AND aligned: a scientist's keep on a scan with no energy anchor is
        # shown as such and never merged with a wrong (or no) shift
        row["merged"] = decision == "keep" and bool(al.get("ok"))
        if decision == "keep" and not al.get("ok"):
            plain = NO_REFERENCE[1] if al.get("code") == NO_REFERENCE[0] else FIT_FAILED[1]
            row["cannot_merge"] = f"kept by the scientist but cannot be merged: {plain}"
        rows.append(row)
        by_id[sid] = row
    for e in inputs:
        if e.get("skip_reason") and e.get("skip_reason") != DROP_REASON and not any(r["entry"] is e for r in recs):
            sid = f"{PurePosixPath(str(e.get('relative_path'))).name}"
            rows.append({"scan_id": sid, "file": sid, "run": None, "scan": e.get("scan"), "decision": "drop",
                         "decided_by": "rule", "rule_decision": "drop",
                         "reasons": [{"source": "params_file" if e.get("excluded_as") else "input",
                                      "code": e["skip_reason"], "said": f"not usable: {e['skip_reason']}"}],
                         "notes": [], "shift_eV": None, "anchor_route": None, "merged": False})
    # an override naming no scan of the group as it is now (after a regroup or a split): said, never silently lost
    stale = []
    for key, ov in overrides.items():
        if key in matched:
            continue
        unusable = next((x for x in rows if x["run"] is None and x["scan_id"] == key), None)
        why = (f"{key} is in this group but not usable ({unusable['reasons'][0]['code']})" if unusable else
               f"{key} is not a scan of this group now (regrouped or split?)")
        stale.append({"scan": key, "decision": ov.get("decision"), "decision_id": ov.get("decision_id"),
                      "decided_by": ov.get("decided_by"),
                      "said": f"override not applied: {why}; the scientist's {ov.get('decision')} "
                              f"({ov.get('decision_id')}) stays in the bundle"})
    kept = [x for x in rows if x["decision"] == "keep"]
    dropped = [x for x in rows if x["decision"] == "drop"]
    overridden = [x for x in rows if x["decided_by"] == "scientist"]
    merged = [x for x in rows if x.get("merged")]
    return {"rule_id": DECISION_RULE_ID, "rule": DECISION_RULE["statement"], "rows": rows, "by_id": by_id,
            "counts": {"scans": len(rows), "kept": len(kept), "dropped": len(dropped),
                       "overridden_by_scientist": len(overridden), "merged": len(merged),
                       "kept_not_merged": len(kept) - len(merged)},
            "overrides_not_applied": stale,
            "statement": decisions_statement(rows, stale),
            "override_command": ('isaac bundle decide <bundle_dir> --target <group id> --decision set_scan_decision '
                                 '--value keep|drop --scans "<scan id>[,<scan id>...]" --note "<why>" --by "<name>"')}


# --- spots (review of group 02: a spot difference is not an evolution) ---------------------------------------------

#: the reasons that say a scan DIFFERS from the others (the stability analysis, the engine's shape screen)
DIFFERS_CODES = ("before_stable_window", "shape")
#: stability metrics that are shape (normalised), not intensity (core.SEL_SHAPE_METRICS)
SHAPE_METRICS = ("delta_eV", "wl_e_eV", "wl_h")
SPOT_RULE_ID = "isaac.xas.spot_decision.v1"
#: a spot whose edge step differs from the other spots' by at least this fraction, with the same shape, is said
WEAK_SPOT_FRACTION = 0.25
SPOTS_DISAGREE_FLAG = "spots_disagree"
SPOT_RULE = (
    "Scans are grouped by spot (the stage motors Sx Sy Sz Sr their headers state). When the scans the rule finds "
    "DIFFERENT (before the stable window, or off-shape) all sit at spots where no kept scan sits, the difference is the "
    "SPOT's, not an evolution: the majority of consistent spots is kept and each differing spot is dropped with a spot "
    "reason, when its shape differs (a difference in intensity alone drops nothing). When the spots split evenly (no "
    "majority), every spot is kept, the group is flagged 'spots disagree' and a bulk approval refuses it, so the "
    "scientist looks. When the differing scans are ALSO the first scans of their run (and the other spots are the "
    "majority), spot and time order are confounded: the reason says both (early_and_spot_differs) and they are "
    "dropped. 'Still changing' alone stays only "
    "for a trend across scans at the SAME spot.")


def _spots_of(recs: Sequence[Mapping]) -> dict[str, dict | None]:
    """``{scan id: spot}`` (``{"label": "spot 1", "Sz": -7.15, ...}``) from each scan's SPEC header (v0's reader)."""
    from . import run as R

    labels = R._spot_labels([(r.get("header"), r.get("motor_lines") or ()) for r in recs])
    return {r["scan_id"]: sp for r, (sp, _why) in zip(recs, labels)}


def _spot_name(sp: Mapping, varying: Sequence[str]) -> str:
    pos = " ".join(f"{m} {sp[m]:g}" for m in varying if m in sp)
    return f"spot {pos}" if pos else str(sp.get("label"))


def _scan_list(rows: Sequence[Mapping]) -> str:
    runs = {x.get("run") for x in rows}
    nums = [str(x["scan"]) if len(runs) == 1 else x["scan_id"] for x in rows]
    return ("scan " if len(nums) == 1 else "scans ") + ", ".join(nums)


def _pct(v, ref) -> str | None:
    if v is None or ref in (None, 0):
        return None
    return f"{100 * (v - ref) / abs(ref):+.0f} %"


def apply_spots(table: dict, recs: Sequence[Mapping], stability: Mapping, np) -> dict | None:
    """:data:`SPOT_RULE` on the decision table (changed in place); returns the per-spot block (None: one spot or none
    stated)."""
    spot = _spots_of(recs)
    rows = table["by_id"]
    for sid, row in rows.items():
        sp = spot.get(sid)
        if sp:
            row["spot"] = sp["label"]
    labels = sorted({sp["label"] for sp in spot.values() if sp}, key=lambda s: int(s.split()[-1]))
    if len(labels) < 2:
        return None
    first = {}
    for sp in spot.values():
        if sp:
            first.setdefault(sp["label"], sp)
    motors = sorted({m for sp in first.values() for m in sp if m != "label"})
    varying = [m for m in motors if len({round(sp.get(m, float("nan")), 4) for sp in first.values()}) > 1]
    names = {lab: _spot_name(first[lab], varying) for lab in labels}
    stab = (stability or {}).get("rows") or {}

    def metric(sid, k):
        v = ((stab.get(sid) or {}).get("metrics") or {}).get(k)
        return float(v) if isinstance(v, (int, float)) and v == v else None

    flagged = [sid for sid, row in rows.items() if sid in spot and any(y["code"] in DIFFERS_CODES for y in row["reasons"])]
    kept = [sid for sid, row in rows.items() if sid in spot and row["rule_decision"] == "keep"]
    sp_f = {spot[s]["label"] for s in flagged if spot.get(s)}
    sp_k = {spot[s]["label"] for s in kept if spot.get(s)}
    by_spot = {lab: [rows[s] for s in rows if spot.get(s) and spot[s]["label"] == lab] for lab in labels}

    def med(lab, k, only=None):
        vs = [metric(x["scan_id"], k) for x in by_spot[lab] if only is None or x["scan_id"] in only]
        vs = [v for v in vs if v is not None]
        return float(np.median(vs)) if vs else None

    ref_ids = set(kept)
    evo = set((stability or {}).get("evolving_metrics") or ())

    def shape_evidence(ids) -> tuple[list[str], bool]:
        """What of the NORMALISED shape differs between ``ids`` and the kept scans, beyond the noise (white-line
        height, white-line energy, edge position: the stability metrics; their floors and 3 x their per-scan sd),
        and whether there is a real shape difference at all (those, an affine off-shape flag, or the stability
        analysis' evolution in a shape metric). An edge step or a background is intensity, never shape."""
        ids = list(ids)
        said = []
        for k in SHAPE_METRICS:
            f = [v for v in (metric(x, k) for x in ids) if v is not None]
            r = [v for v in (metric(x, k) for x in ref_ids) if v is not None]
            if not f or not r:
                continue
            d = float(np.median(f)) - float(np.median(r))
            sds = [v for v in (metric(x, C._sd_key(k)) for x in list(ids) + list(ref_ids)) if v is not None]
            noise = max(float(C.SEL_FLOOR.get(k, 0.0)), 3 * float(np.median(sds)) if sds else 0.0)
            if abs(d) > noise:
                said.append(f"white-line height {_pct(float(np.median(f)), float(np.median(r)))}" if k == "wl_h" else
                            f"white-line energy {d:+.2f} eV" if k == "wl_e_eV" else f"edge position {d:+.2f} eV")
        flag = any(y["code"] == "shape" for x in ids for y in rows[x]["reasons"] + rows[x]["notes"]
                   if y.get("source") == "screening")
        trend = bool(evo & set(SHAPE_METRICS)) and any(y["code"] == "before_stable_window" for x in ids
                                                         for y in rows[x]["reasons"])
        return said, bool(said) or flag or trend

    ref_wl = [metric(s, "wl_h") for s in ref_ids]
    ref_wl = float(np.median([v for v in ref_wl if v is not None])) if any(v is not None for v in ref_wl) else None
    ref_st = [metric(s, "edge_step") for s in ref_ids]
    ref_st = float(np.median([v for v in ref_st if v is not None])) if any(v is not None for v in ref_st) else None
    outcome, statement = "consistent", None
    confined = bool(flagged) and all(spot.get(s) for s in flagged) and not (sp_f & sp_k)
    if flagged and not confined:
        outcome = "evolution_within_a_spot" if sp_f & sp_k else "spot_not_read"
    elif confined and _earliest(flagged, recs, rows) and len(sp_k) > len(sp_f) and shape_evidence(flagged)[1]:
        # spot and time order are CONFOUNDED: the differing scans are the first of their run AND at other spots;
        # neither label alone is honest, and both point to leaving them out
        mine = [rows[s] for s in sorted(flagged, key=lambda s: [r["scan_id"] for r in recs].index(s))]
        sps = sorted({spot[s]["label"] for s in flagged}, key=lambda x: int(x.split()[-1]))
        pos = ", ".join(names[lab].removeprefix("spot ") for lab in sps)
        other_rows = [x for o in sorted(sp_k, key=lambda x: int(x.split()[-1])) for x in by_spot[o] if x["scan_id"] in ref_ids]
        how = shape_evidence(flagged)[0]
        what = (f"{_scan_list(mine)} differ{'s' if len(mine) == 1 else ''} from the rest ({_scan_list(other_rows)})"
                + (f" in shape ({', '.join(how)})" if how else " in shape") + ": "
                f"{'it is the first scan' if len(mine) == 1 else 'they are the first scans'} of the run (after the "
                f"condition was set) AND at {'another spot' if len(sps) == 1 else 'other spots'} ({pos}), so either "
                "the sample was still changing or the spot differs; both point to leaving "
                f"{'it' if len(mine) == 1 else 'them'} out")
        for x in mine:
            old = [y for y in x["reasons"] if y["code"] in DIFFERS_CODES]
            x["reasons"] = [y for y in x["reasons"] if y["code"] not in DIFFERS_CODES] + [
                {"source": "spots", "code": "early_and_spot_differs", "rule": SPOT_RULE_ID, "said": what,
                 "evidence": {"spot": spot[x["scan_id"]], "replaces": [y["code"] for y in old],
                              "was_said": "; ".join(y["said"] for y in old)}}]
            x["rule_decision"] = "drop"
            if x["decided_by"] == "rule":
                x["decision"], x["merged"] = "drop", False
        outcome, statement = "early_and_spot_differs", what
    elif confined:
        others = sorted(sp_k, key=lambda s: int(s.split()[-1]))
        majority = len(sp_k) > len(sp_f)
        early = _earliest(flagged, recs, rows)
        said_spots: list[str] = []
        outcomes: list[str] = []
        for lab in sorted(sp_f, key=lambda s: int(s.split()[-1])):
            mine = [x for x in by_spot[lab] if x["scan_id"] in flagged]
            how, shape = shape_evidence([x["scan_id"] for x in mine])
            st = med(lab, "edge_step", {x["scan_id"] for x in mine})
            parts = list(how)
            if _pct(st, ref_st):
                parts.append(f"edge step {_pct(st, ref_st)}")
            other_rows = [x for o in others for x in by_spot[o] if x["scan_id"] in ref_ids]
            what = (f"{names[lab]} ({_scan_list(mine)}) differs from the other "
                    f"{'spot' if len(others) == 1 else f'{len(others)} spots'} ({_scan_list(other_rows)})"
                    + (": " + ", ".join(parts) if parts else "")
                    + ("; its normalised shape differs" if shape else
                       "; weaker signal at this spot, same shape" if st is not None and ref_st and st < ref_st else
                       "; only its intensity differs, same shape")
                    + ("; these are also the first scans of the run, so the sample may still have been changing"
                       if early else "")
                    + "; possibly an uneven or thinner area of the sample")
            for x in mine:
                old = [y for y in x["reasons"] if y["code"] in DIFFERS_CODES]
                rest = [y for y in x["reasons"] if y["code"] not in DIFFERS_CODES]
                said_before = "; ".join(y["said"] for y in old)
                if majority and shape:
                    x["reasons"] = rest + [{"source": "spots", "code": "spot_differs", "rule": SPOT_RULE_ID,
                                            "said": what + " (the majority of consistent spots is kept)",
                                            "evidence": {"spot": spot[x["scan_id"]], "replaces": [y["code"] for y in old],
                                                         "was_said": said_before}}]
                else:
                    x["reasons"] = rest
                    x["notes"] = list(x["notes"]) + [{"source": "spots", "code": "spot_differs", "decides": False,
                                                      "said": what + (f"; {NOT_A_DROP_REASON}: the spots split evenly, no "
                                                                      "majority, the scientist decides" if shape else
                                                                      f": {NOT_A_DROP_REASON} (an intensity "
                                                                      "difference alone never drops a scan)"),
                                                      "was_said": said_before}]
                x["rule_decision"] = "drop" if x["reasons"] else "keep"
                if x["decided_by"] == "rule":
                    x["decision"] = x["rule_decision"]
                    x["merged"] = x["decision"] == "keep" and x.get("shift_eV") is not None
            said_spots.append(what)
            outcomes.append("differing_spot_dropped" if majority and shape else
                            ("spots_disagree" if shape else "intensity_only_kept"))
        statement = "; ".join(said_spots)
        outcome = next((o for o in ("spots_disagree", "differing_spot_dropped") if o in outcomes), "intensity_only_kept")
    # a spot whose signal is much weaker (or stronger) with the SAME normalised shape: kept, and said so
    for lab in labels:
        xs = [x for x in by_spot[lab] if x["decision"] == "keep" and not any(n.get("source") == "spots" for n in x["notes"])]
        others_k = {x for o in labels if o != lab for x in (y["scan_id"] for y in by_spot[o]) if x in ref_ids}
        st = med(lab, "edge_step", {x["scan_id"] for x in xs})
        ro = [v for v in (metric(x, "edge_step") for x in others_k) if v is not None]
        ref_o = float(np.median(ro)) if ro else None
        if not xs or st is None or not ref_o or abs(st - ref_o) / abs(ref_o) < WEAK_SPOT_FRACTION:
            continue
        how = shape_evidence([x["scan_id"] for x in xs])[0]
        if how:
            continue
        word = "weaker" if st < ref_o else "stronger"
        note = {"source": "spots", "code": f"{word}_spot_same_shape", "decides": False,
                "said": f"{word} signal at this spot ({names[lab]}: edge step {_pct(st, ref_o)}), same shape: "
                        f"{NOT_A_DROP_REASON}"}
        for x in xs:
            x["notes"] = list(x["notes"]) + [note]
    summary = []
    for lab in labels:
        xs = by_spot[lab]
        summary.append({"spot": lab, "name": names[lab], "position": {m: first[lab].get(m) for m in motors},
                        "scans": [x["scan_id"] for x in xs], "kept": [x["scan_id"] for x in xs if x["decision"] == "keep"],
                        "white_line_height": med(lab, "wl_h"), "edge_step": med(lab, "edge_step")})
    block = {"rule_id": SPOT_RULE_ID, "rule": SPOT_RULE, "outcome": outcome, "spots": summary,
             "statement": statement or (f"{len(labels)} spots; the rule found no spot that differs from the others."
                                        if outcome == "consistent" else
                                        "The scans that differ share a spot with kept scans: a change within a spot "
                                        "(the stability analysis), not a spot difference."
                                        if outcome == "evolution_within_a_spot" else
                                        "Some differing scans have no stated spot: the spot rule was not applied.")}
    if outcome == SPOTS_DISAGREE_FLAG:
        block["statement"] = ("SPOTS DISAGREE: " + statement + ". The spots split evenly (no majority): every spot is "
                              "kept; look at the spots and decide (set_scan_decision); a bulk approval refuses this "
                              "result.")
    _recount(table)
    return block


#: WITHIN-SPOT CHANGE: BEAM DAMAGE, OR A FIRST SCAN STILL SETTLING (isaac.xas.dose_damage.v3; v2 reviewed 271efe4a;
#: v3 after the processing-science audit of 18 Nov 2026, finding 1).
#: The measure: EACH scan is normalised ON ITS OWN with the same fixed windows (its mean IF/I0 below E_edge +
#: ``pre_eV`` set to 0, its mean above E_edge + ``post_eV`` set to 1: an intensity change or a constant background is
#: never shape), and the later scan minus the earlier one is averaged over the white-line window (the group's
#: white-line energy +- ``wl_half_eV``), in edge-step units. v2 instead fitted one scan onto the other by least squares
#: (yf ~ c*ys + k): the regressor is itself a noisy scan, so c is attenuated (regression dilution) and the later scan's
#: white line reads LOWER from counting noise alone, the more so the fewer the counts (on the real 2025 data, two
#: simulated scans of one unchanged curve gave almost the same "damage" as measured). Normalising each scan alone has
#: no regressor: noise enters only through the two window means, the same way for both scans, so pure noise gives no
#: trend (a residual bias is second order in the window means' relative error, about 1e-4 of the step for a 1 % error,
#: and cancels between scans of equal counts). Fitting both scans onto the group's merge was the other option; it
#: still regresses on a noisy curve (the merge contains the two scans) and its bias depends on how many scans merge. The noise of the difference: the point-to-point scatter of the difference over the window, / sqrt(n),
#: combined with each scan's edge-step error (its window means' scatter / sqrt(n), times the window's mean level);
#: "beyond the noise" is max(``floor``, ``noise_mult`` x that noise). COUNTS FLOOR: a spot whose scans have under
#: ``min_counts`` counts per point in the post-edge (the median IF above E_edge + ``post_eV``, the lower of the scans
#: compared, IF read as the counts the beamline wrote) is NOT JUDGED; when at least half of the spots measured more
#: than once are under it, the rule says it cannot judge dose at this count level and decides nothing (no drop, no
#: question). Per spot with three or more scans (in time):
#:   GROWS (beam damage): scan 3 differs from scan 1 more than scan 2 does, the same way, and scan 3 differs from
#:     scan 2 beyond the noise: the change grows with dose;
#:   PLATEAU (a first scan still settling): scans 2 and 3 both differ from scan 1 the same way and agree with each
#:     other: the first scan is the outlier (an equilibration transient).
#: The group: BEAM DAMAGE (the first scan per spot kept, the later ones dropped) only when most spots measured three
#: or more times grow (at least two), the same way at every changed spot, the way the edge's physics expects (the
#: white line FALLS, a reduction, at Ir and Pt L3; elsewhere the one direction every spot shares, said), and a fresh
#: spot recovers (the move from a spot's last scan to the next spot's first undoes at least half of the damage, at most
#: moves). FIRST SCAN SETTLING (the first scan per spot dropped) when most such spots plateau (at least two), the same
#: way. A change that carries on across spots (no recovery, most moves continue it) is the sample's evolution, not
#: this rule's. Otherwise a consistent within-spot change at two or more spots is a QUESTION to the scientist, with
#: both readings, nothing decided and a bulk approval refused: only two scans per spot (growth cannot be told from a
#: settling first scan), mixed patterns, a damage-like pattern the wrong way for the edge, or a logbook note speaking
#: of CV, equilibration or discarding the first scans. A logbook exclude / start_from / keep_only note on the group
#: always wins (this rule then decides nothing); an existing shape-screen drop is never cleared; a scientist's
#: set_dose_reading (the group's, else the beamtime's) decides the reading; set_scan_decision still wins per scan.
DOSE = {"wl_half_eV": 4.0, "floor": 0.01, "noise_mult": 3.0, "pre_eV": -10.0, "post_eV": 30.0, "recovery_frac": 0.5,
        "min_counts": 150.0}
DOSE_RULE_ID = "isaac.xas.dose_damage.v3"
DOSE_LOW_COUNTS = "cannot_judge_low_counts"
DOSE_NO_CHANGE = "no_change_at_judged_spots"
DOSE_CODE = "beam_damage_at_spot"
SETTLING_CODE = "first_scan_settling"
DOSE_SAID = "beam damage at each spot: later scans at the same spot change shape"
SETTLING_SAID = "first scan at each spot still settling: the later scans there agree with each other, the first does not"
DOSE_QUESTION_FLAG = "dose_reading_question"
DOSE_READING = "set_dose_reading"
#: the edges whose beam damage is a REDUCTION (the white line falls): Ir and Pt L3 under the beam
REDUCING_EDGES = {("Ir", "L3"): -1, ("Pt", "L3"): -1}
_DOSE_NOTE = re.compile(r"\bCVs?\b|cyclic voltam|equilibrat|discard(ing)?\s+(the\s+)?first|first\s+\d*\s*scans?",
                        re.I)


def dose_reading_of(bundle: Mapping, group_id: str) -> dict | None:
    """The scientist's set_dose_reading for this group (latest), else for the beamtime (``experiment``), or None."""
    group = beamtime = None
    for d in bundle.get("scientist_decisions") or ():
        if d.get("decision") != DOSE_READING:
            continue
        t = d.get("target") or {}
        x = {"reading": d.get("value"), "decision_id": d.get("decision_id"),
             "decided_by": (d.get("decided_by") or {}).get("name"), "note": d.get("note")}
        if t.get("kind") == "record_group" and t.get("id") == group_id:
            group = {**x, "scope": "group"}
        elif t.get("kind") == "experiment":
            beamtime = {**x, "scope": "beamtime"}
    return group or beamtime


def _norm_difference(f: Mapping, s: Mapping, E_edge: float, win: Sequence[float], np) -> tuple[float, float] | None:
    """``(mean difference, its noise)`` of scan ``s`` minus scan ``f``, each normalised ON ITS OWN with the same fixed
    pre- and post-edge windows, over ``win`` in edge-step units (:data:`DOSE`; no regression of one noisy scan on the
    other, which biases the later scan's white line low)."""
    a, b = f.get("aligned"), s.get("aligned")
    if a is None or b is None:
        return None
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yf, ys, E = a.IF / a.I0, b.IF / b.I0, a.E
        ok = np.isfinite(yf) & np.isfinite(ys)
        pre, post = ok & (E < E_edge + DOSE["pre_eV"]), ok & (E > E_edge + DOSE["post_eV"])
        w = ok & (E >= win[0]) & (E <= win[1])
        if pre.sum() < 2 or post.sum() < 3 or w.sum() < 5:
            return None
        normed, step_var = [], 0.0
        for y in (yf, ys):
            lo, hi = float(np.mean(y[pre])), float(np.mean(y[post]))
            step = hi - lo
            if not step > 0:
                return None
            nrm = (y - lo) / step
            normed.append(nrm)
            # the edge-step error: each window mean's point-to-point scatter / sqrt(n), carried to the window's level
            e_lo, e_hi = (float(np.std(np.diff(y[m])) / np.sqrt(2.0) / np.sqrt(m.sum())) for m in (pre, post))
            step_var += (float(np.mean(nrm[w])) * np.hypot(e_lo, e_hi) / step) ** 2
        d = normed[1][w] - normed[0][w]
        noise = np.hypot(float(np.std(np.diff(d)) / np.sqrt(2.0) / np.sqrt(w.sum())), np.sqrt(step_var))
        return float(np.mean(d)), float(noise)


def _post_counts(r: Mapping, E_edge: float, np) -> float | None:
    """The scan's counts per point in the post-edge (median IF above E_edge + ``post_eV``, as written), or None."""
    a = r.get("aligned")
    if a is None:
        return None
    with np.errstate(all="ignore"):
        m = np.isfinite(a.IF) & (a.E > E_edge + DOSE["post_eV"])
        return float(np.median(a.IF[m])) if m.sum() >= 3 else None


def apply_dose_damage(table: dict, recs: Sequence[Mapping], stability: Mapping, np, E_edge: float | None = None, *,
                      absorber: Mapping | None = None, notes_said: Mapping | None = None,
                      reading: Mapping | None = None) -> dict | None:
    """:data:`DOSE_RULE_ID` on the decision table (changed in place); the block said on the result, or None. Spots
    under the counts floor are left out and said (review of PR 345, I1)."""
    info: dict = {}
    block = _dose_core(table, recs, stability, np, E_edge, absorber=absorber, notes_said=notes_said, reading=reading,
                       info=info)
    low = info.get("left_out") or ()
    if not low:
        return block
    said = (f"{len(low)} of {info['repeat']} spots measured more than once were left out of this judgement (under "
            f"{DOSE['min_counts']:.0f} post-edge counts per point: {', '.join(sorted(low))}); {info['judged']} were "
            "judged.")
    if block is None:
        return {"rule_id": DOSE_RULE_ID, "rule": DOSE, "outcome": DOSE_NO_CHANGE, "spots_under_floor_not_judged":
                sorted(low), "post_edge_counts_per_point": info.get("counts"),
                "statement": f"No consistent within-spot change at the {info['judged']} spots judged. {said}"}
    block["statement"] = block["statement"].rstrip() + " " + said
    return block


def _dose_core(table: dict, recs: Sequence[Mapping], stability: Mapping, np, E_edge: float | None = None, *,
               absorber: Mapping | None = None, notes_said: Mapping | None = None, reading: Mapping | None = None,
               info: dict) -> dict | None:
    if E_edge is None:
        return None
    spot = _spots_of(recs)
    rows = table["by_id"]
    stab = (stability or {}).get("rows") or {}
    judged = [r for r in recs if spot.get(r["scan_id"]) and r.get("aligned") is not None
              and not any(y["code"] not in DIFFERS_CODES for y in rows[r["scan_id"]]["reasons"])]
    judged.sort(key=lambda r: (r.get("time") or datetime.max, r["num"]))
    by_spot: dict[str, list] = {}
    for r in judged:
        by_spot.setdefault(spot[r["scan_id"]]["label"], []).append(r)
    repeat = {lab: rs for lab, rs in by_spot.items() if len(rs) >= 2}
    if len(repeat) < 2:
        return None
    # the COUNTS FLOOR (v3): a spot under min_counts post-edge counts per point is not judged
    counts = {}
    for lab, rs in repeat.items():
        c = [v for r in rs if (v := _post_counts(r, float(E_edge), np)) is not None]
        counts[lab] = min(c) if c else None
    low = {lab for lab, c in counts.items() if c is not None and c < DOSE["min_counts"]}
    reading_of = (reading or {}).get("reading")
    forced = False
    if len(repeat) - len(low) < 2:
        known = [c for c in counts.values() if c is not None]
        block = {"rule_id": DOSE_RULE_ID, "rule": DOSE, "outcome": DOSE_LOW_COUNTS, "spots_measured_more_than_once":
                 len(repeat), "spots_under_floor": len(low), "post_edge_counts_per_point": counts,
                 "statement": (f"Beam damage is not judged at this count level: {len(low)} of {len(repeat)} spots "
                               f"measured more than once have under {DOSE['min_counts']:.0f} counts per point in the "
                               f"post-edge (median {statistics.median(known):.0f}), so fewer than two can be judged. "
                               "At these counts a within-spot change of a few % of the white line cannot be told "
                               "from counting noise, and its absence cannot be confirmed either; only a much larger "
                               "change would stand out. Nothing is decided by this rule; every scan is judged by the "
                               "other rules.")}
        # a scientist's set_dose_reading is checked BEFORE the floor (review of PR 345, I2): applied, or said as not
        # applied (override_not_applied), never ignored
        if reading_of == "not_beam_damage":
            block.update(outcome="not_beam_damage", reading=reading, statement=(
                f"The scientist's reading ({reading.get('decided_by')}, {reading.get('scope')}): not beam damage. "
                + block["statement"]))
            return block
        if reading_of in ("beam_damage", "first_scan_settling") and reading.get("scope") == "group":
            forced = True                  # the scientist's reading for THIS group decides it at every repeated spot
        else:
            if reading_of:
                table.setdefault("overrides_not_applied", []).append({
                    "scan": None, "decision": f"{DOSE_READING} {reading_of}", "decision_id": reading.get("decision_id"),
                    "decided_by": reading.get("decided_by"),
                    "said": (f"override not applied: the scientist's beamtime-wide {DOSE_READING} {reading_of} "
                             f"({reading.get('decision_id')}) has nothing to act on in this group, because no spot's "
                             "change can be measured at this count level; it stays in the bundle (a "
                             f"{DOSE_READING} on this group, or set_scan_decision, decides it here)")})
                _recount(table)
                block.update(reading=reading, reading_applied=False)
            return block
    elif low:
        info.update(left_out=sorted(low), repeat=len(repeat), judged=len(repeat) - len(low), counts=counts)
        repeat = {lab: rs for lab, rs in repeat.items() if lab not in low}
    wle = [((stab.get(r["scan_id"]) or {}).get("metrics") or {}).get("wl_e_eV") for r in judged]
    wle = [float(v) for v in wle if isinstance(v, (int, float)) and v == v]
    centre = float(np.median(wle)) if wle else float(E_edge) + 3.0
    win = [centre - DOSE["wl_half_eV"], centre + DOSE["wl_half_eV"]]

    def raw(f, s_):
        return _norm_difference(f, s_, float(E_edge), win, np)

    # 2026-11-18: a GLOBAL trend in time order is taken out first: a change it explains is the sample's (the stability
    # rule's "still changing"), never settling or damage; only a within-spot change beyond it (and the noise) is judged.
    # It is a trend only when the fresh spots' first scans (across spots) and the scans within each spot change at the
    # same rate (within 2x, the same way); a spot-to-spot offset, damage or a settling first scan is not one
    pos = {r["scan_id"]: i for i, r in enumerate(judged)}
    firsts = [rs[0] for rs in by_spot.values()]
    pts = [(pos[r["scan_id"]], 0.0 if r is firsts[0] else (raw(firsts[0], r) or (None,))[0]) for r in firsts]
    pts = [p for p in pts if p[1] is not None]
    across = float(np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)[0]) if len(pts) >= 2 else 0.0
    inner = [(pos[r["scan_id"]] - pos[rs[0]["scan_id"]], x[0]) for rs in repeat.values() for r in rs[1:]
             if (x := raw(rs[0], r)) is not None]
    within = sum(n * v for n, v in inner) / sum(n * n for n, _ in inner) if inner else 0.0
    slope = across if across * within > 0 and 0.5 <= across / within <= 2.0 else 0.0

    def diff(f, s_):
        x = raw(f, s_)
        return x and (x[0] - slope * (pos[s_["scan_id"]] - pos[f["scan_id"]]), x[1])

    def beyond(x):
        return x is not None and abs(x[0]) > max(DOSE["floor"], DOSE["noise_mult"] * x[1])

    def sgn(x):
        return int(np.sign(x[0])) if beyond(x) else 0

    per: dict[str, dict] = {}
    for lab, rs in repeat.items():
        d12 = diff(rs[0], rs[1])
        x = {"scans": [r["scan_id"] for r in rs], "d12": d12 and d12[0], "noise12": d12 and d12[1]}
        if len(rs) == 2:
            x.update(kind="two_scans" if beyond(d12) else "none", direction=sgn(d12))
        else:
            d13, d23 = diff(rs[0], rs[2]), diff(rs[1], rs[2])
            x.update(d13=d13 and d13[0], d23=d23 and d23[0])
            s12, s13, s23 = sgn(d12), sgn(d13), sgn(d23)
            if s13 and s23 == s13 and s12 in (0, s13) and abs(d13[0]) > abs(d12[0]):
                x.update(kind="grows", direction=s13)
            elif s12 and s13 == s12 and not s23:
                x.update(kind="plateau", direction=s12)
            elif not s12 and not s13:
                x.update(kind="none", direction=0)
            else:
                x.update(kind="mixed", direction=s13 or s12)
        per[lab] = x
    changed = dict(per) if forced else {lab: x for lab, x in per.items() if x["kind"] != "none"}
    block: dict = {"rule_id": DOSE_RULE_ID, "rule": DOSE, "window_eV": win, "per_spot": per,
                   "spots_measured_more_than_once": len(repeat), "post_edge_counts_per_point": counts,
                   **({"spots_under_floor_not_judged": sorted(low)} if low else {})}
    # a logbook exclude / start_from / keep_only note on the group ALWAYS wins
    applied = [n for n in (notes_said or {}).get("notes") or () if n.get("applied") and n.get("drops")]
    if applied:
        if len(changed) >= 2:
            block.update(outcome="logbook_decides", statement=(
                "A within-spot change was seen, but a logbook note on this run decides which scans are left out ("
                + "; ".join(f"{n.get('action')} {n.get('scans')}: {n.get('reason')}" for n in applied[:3])
                + "); the beam-damage rule decides nothing here."))
            return block
        return None
    if not forced and (len(changed) < 2 or 2 * len(changed) <= len(repeat)):
        return None
    three = {lab: x for lab, x in changed.items() if len(x["scans"]) >= 3}
    directions = {x["direction"] for x in changed.values() if x["direction"]}
    el, ed = (absorber or {}).get("element"), (absorber or {}).get("edge")
    expected = REDUCING_EDGES.get((el, ed))
    grows = [lab for lab, x in three.items() if x["kind"] == "grows"]
    plateau = [lab for lab, x in three.items() if x["kind"] == "plateau"]
    n3 = sum(1 for x in per.values() if len(x["scans"]) >= 3)
    note_text = " ".join(str(n.get("reason") or "") + " " + str(n.get("quote") or "")
                         for n in (notes_said or {}).get("notes") or ())
    order = list(dict.fromkeys(spot[r["scan_id"]]["label"] for r in judged))

    def moves(sign):
        out = []
        for la, lb in zip(order, order[1:]):
            if la not in repeat:
                continue
            x = diff(by_spot[la][-1], by_spot[lb][0])
            if x is None:
                continue
            dmg = diff(by_spot[la][0], by_spot[la][-1])
            out.append({"from": by_spot[la][-1]["scan_id"], "to": by_spot[lb][0]["scan_id"], "difference": x[0],
                        "noise": x[1], "continues": beyond(x) and int(np.sign(x[0])) == sign,
                        "recovers": (dmg is not None and int(np.sign(x[0])) == -sign
                                     and abs(x[0]) >= DOSE["recovery_frac"] * abs(dmg[0]))})
        return out

    outcome, why = None, None
    if reading_of == "not_beam_damage":
        block.update(outcome="not_beam_damage", reading=reading, statement=(
            f"The scientist's reading ({reading.get('decided_by')}, {reading.get('scope')}): not beam damage. Every scan "
            "is judged by the other rules."))
        return block
    if reading_of in ("beam_damage", "first_scan_settling"):
        outcome = reading_of
    elif len(directions) > 1:
        why = "the spots change in opposite directions"
    elif grows and len(grows) >= 2 and 2 * len(grows) > n3:
        sign = directions.pop()
        mv = moves(sign)
        block["moves_between_spots"] = mv
        if mv and 2 * sum(m["continues"] for m in mv) > len(mv) and not any(m["recovers"] for m in mv):
            return None                    # the change carries on across spots: the sample's evolution, not dose
        if expected is not None and sign != expected:
            why = (f"the white line {'rises' if sign > 0 else 'falls'} with dose at {len(grows)} spots, the opposite of "
                   f"the reduction expected at {el} {ed}")
        elif not mv or 2 * sum(m["recovers"] for m in mv) <= len(mv):
            why = "a fresh spot does not recover to the first-scan level"
        elif _DOSE_NOTE.search(note_text):
            why = "a logbook note speaks of CV time, equilibration or discarding the first scans"
        else:
            outcome = "beam_damage"
    elif plateau and len(plateau) >= 2 and 2 * len(plateau) > n3:
        outcome = "first_scan_settling"
    elif not three:
        why = "only two scans per spot: a change that grows with dose cannot be told from a first scan still settling"
    else:
        why = "the spots measured three or more times show mixed patterns (" + ", ".join(
            f"{lab}: {x['kind']}" for lab, x in sorted(three.items(), key=lambda kv: int(kv[0].split()[-1]))) + ")"
    sign = next(iter({x["direction"] for x in changed.values() if x["direction"]}), -1)
    word = "falls" if sign < 0 else "rises"
    spots_said = "; ".join(f"{lab} ({x['kind']}: scan 2 {100 * (x['d12'] or 0):+.1f} %"
                           + (f", scan 3 {100 * (x.get('d13') or 0):+.1f} %" if x.get("d13") is not None else "") + ")"
                           for lab, x in sorted(changed.items(), key=lambda kv: int(kv[0].split()[-1])))
    if outcome is None:
        what = (f"QUESTION: at {len(changed)} of {len(repeat)} spots measured more than once the white line {word} "
                f"after the first scan ({spots_said}, normalised shape, edge-step units, window {win[0]:.1f}-"
                f"{win[1]:.1f} eV), and the rule cannot tell why: {why}. Either it is beam damage (keep the first scan "
                "per spot) or the first scan is still settling (drop the first scan per spot). Nothing is decided: "
                f"`isaac bundle decide <bundle_dir> --target <group id> --decision {DOSE_READING} --value "
                "beam_damage|first_scan_settling|not_beam_damage --by \"<name>\"` (or --target experiment for the "
                "whole beamtime); a bulk approval refuses this result.")
        for lab in changed:
            for r in repeat[lab]:
                x = rows[r["scan_id"]]
                x["notes"] = list(x["notes"]) + [{"source": "dose", "code": DOSE_QUESTION_FLAG, "decides": False,
                                                  "said": "open question: beam damage or a first scan still settling"}]
        block.update(outcome="question", why=why, statement=what)
        return block
    by = f"the scientist's reading ({reading.get('decided_by')}, {reading.get('scope')})" if reading_of else "the rule"
    dropped = []
    if outcome == "beam_damage":
        what = (f"{DOSE_SAID} (the white line {word} with dose at {len(changed)} of {len(repeat)} spots measured more "
                f"than once and recovers at a fresh spot: {spots_said}; normalised shape, edge-step units, window "
                f"{win[0]:.1f}-{win[1]:.1f} eV"
                + ("" if expected is not None or reading_of else f"; at {el} {ed} the direction the spots share, "
                                                                   f"the white line {word}, is taken as the damage")
                + f"; decided by {by}); the first scan per spot is kept")
        if forced:
            what = (f"{DOSE_SAID}: decided by {by} for this group, at every one of the {len(repeat)} spots measured "
                    "more than once; no change could be measured at this count level (" + spots_said
                    + "); the first scan per spot is kept")
        for lab in changed:
            for r in repeat[lab][1:]:
                x = rows[r["scan_id"]]
                old = [y for y in x["reasons"] if y["code"] in DIFFERS_CODES]
                x["reasons"] = [y for y in x["reasons"] if y["code"] not in DIFFERS_CODES] + [
                    {"source": "dose", "code": DOSE_CODE, "rule": DOSE_RULE_ID, "said": what,
                     "evidence": {"spot": spot[r["scan_id"]], "first_scan_at_spot": repeat[lab][0]["scan_id"],
                                  "window_eV": win, "replaces": [y["code"] for y in old]}}]
                dropped.append(x["scan_id"])
    else:
        what = (f"{SETTLING_SAID} ({spots_said}; normalised shape, edge-step units, window {win[0]:.1f}-{win[1]:.1f} "
                f"eV; decided by {by}); the first scan per spot is dropped")
        if forced:
            what = (f"{SETTLING_SAID}: decided by {by} for this group, at every one of the {len(repeat)} spots "
                    "measured more than once; no change could be measured at this count level (" + spots_said
                    + "); the first scan per spot is dropped")
        for lab in changed:
            r = repeat[lab][0]
            x = rows[r["scan_id"]]
            x["reasons"] = list(x["reasons"]) + [
                {"source": "dose", "code": SETTLING_CODE, "rule": DOSE_RULE_ID, "said": what,
                 "evidence": {"spot": spot[r["scan_id"]], "later_scans_at_spot": [y["scan_id"] for y in repeat[lab][1:]],
                              "window_eV": win}}]
            dropped.append(x["scan_id"])
    for sid in dropped:
        x = rows[sid]
        x["rule_decision"] = "drop"
        if x["decided_by"] == "rule":
            x["decision"], x["merged"] = "drop", False
    _recount(table)
    block.update(outcome=outcome, dropped=dropped, spots=sorted(changed, key=lambda v: int(v.split()[-1])),
                 statement=what[:1].upper() + what[1:] + ".", **({"reading": reading} if reading_of else {}))
    return block


#: WHERE COVERAGE DIFFERS, A SCALE-MATCHED MEAN (processing-science audit of 18 Nov 2026, finding 6). The kept scans'
#: raw IF/I0 differ in level (spot, loading, filter); where only some of them contribute (an I0-dropout point left
#: out, a scan that ends early) the plain mean steps by the missing scans' level. Each scan's level relative to the
#: merge, r_j = sum(y_j m) / sum(m^2) over the points ALL kept scans cover (m: the plain mean there; the r_j average
#: exactly 1), then at every point the mean is sum(y_j) / sum(r_j) over the scans that contribute there: the plain mean
#: where all contribute (uniform weights, unchanged), free of the step where some do not. Nothing is interpolated.
COVERAGE_RULE_ID = "isaac.xas.coverage_matched_mean.v1"
COVERAGE_MIN_COMMON = 20


def coverage_matched_mean(aligned: Sequence, avg: dict, np) -> dict | None:
    """Rewrite ``avg["IF_over_I0"]`` in place at the points where only some kept scans contribute
    (:data:`COVERAGE_RULE_ID`); the disclosure block, or None when every point has every scan (or too few in common)."""
    if len(aligned) < 2:
        return None
    Y = np.array([np.ravel(a.IF) / np.ravel(a.I0) for a in aligned]).T
    fin = np.isfinite(Y)
    nfin = fin.sum(axis=1)
    partial = (nfin > 0) & (nfin < len(aligned))
    if not partial.any():
        return None
    full = nfin == len(aligned)
    if full.sum() < COVERAGE_MIN_COMMON:
        return {"rule_id": COVERAGE_RULE_ID, "applied": False, "partial_points": int(partial.sum()),
                "statement": (f"At {int(partial.sum())} points only some of the kept scans contribute, and the scans "
                              f"share under {COVERAGE_MIN_COMMON} points to match their levels on: the plain mean is "
                              "kept there and may step where coverage changes.")}
    m = Y[full].mean(axis=1)
    r = (Y[full] * m[:, None]).sum(axis=0) / float((m * m).sum())
    if not np.all(np.isfinite(r) & (r > 0)):
        return None
    num = np.where(fin, Y, 0.0).sum(axis=1)
    den = np.where(fin, r[None, :], 0.0).sum(axis=1)
    avg["IF_over_I0"] = np.where(partial, num / np.where(den > 0, den, np.nan), avg["IF_over_I0"])
    keys = [getattr(a, "ident", getattr(a, "num", None)) for a in aligned]
    return {"rule_id": COVERAGE_RULE_ID, "applied": True, "partial_points": int(partial.sum()),
            "common_points": int(full.sum()), "scan_levels": {str(k): round(float(v), 4) for k, v in zip(keys, r)},
            "statement": (f"Scale-matched where coverage differs: at {int(partial.sum())} points only some of the "
                          f"{len(aligned)} kept scans contribute (a point left out, a scan that ends early); there "
                          "the mean is the sum of the contributing scans over the sum of their levels relative to the "
                          f"merge (levels {min(r):.3f}-{max(r):.3f}, fitted over the {int(full.sum())} points all "
                          "scans cover), so a missing scan's level leaves no step. Where all scans contribute it is "
                          "the plain mean. Nothing is interpolated.")}


def _earliest(flagged: Sequence[str], recs: Sequence[Mapping], rows: Mapping) -> bool:
    """Are the differing scans the FIRST scans of their run (a contiguous run from the start, in time order by #D,
    then scan number)? Scans dropped for another reason only (aborted, no energy reference, a logbook note) are
    skipped in that order: they are judged by nothing here."""
    fl = set(flagged)
    by_run: dict = {}
    for r in recs:
        by_run.setdefault(r.get("run_key"), []).append(r)
    for rs in by_run.values():
        mine = [r for r in rs if r["scan_id"] in fl]
        if not mine:
            continue
        judged = [r for r in rs if r["scan_id"] in fl or not rows[r["scan_id"]]["reasons"]]
        judged.sort(key=lambda r: (r.get("time") or datetime.max, r["num"]))
        if {r["scan_id"] for r in judged[:len(mine)]} != {r["scan_id"] for r in mine}:
            return False
    return True


def _recount(table: dict) -> None:
    rows = table["rows"]
    kept = [x for x in rows if x["decision"] == "keep"]
    merged = [x for x in rows if x.get("merged")]
    table["counts"] = {"scans": len(rows), "kept": len(kept), "dropped": len(rows) - len(kept),
                       "overridden_by_scientist": len([x for x in rows if x["decided_by"] == "scientist"]),
                       "merged": len(merged), "kept_not_merged": len(kept) - len(merged)}
    table["statement"] = decisions_statement(rows, table.get("overrides_not_applied") or ())


def metric_shifts(sid: str, stability: Mapping | None, np) -> list[dict]:
    """How one scan's NORMALISED-shape metrics (the stability analysis' ``delta_eV``, ``wl_e_eV``, ``wl_h``) differ
    from the stable scans' (the stable window, else every other scan), counted only beyond the stability rule's own
    floor (``core.SEL_FLOOR``) and 3 x the difference's sd (this scan's and the stable scans'). Empty: no shape metric moved, or none was measured."""
    rows = (stability or {}).get("rows") or {}
    me = (rows.get(sid) or {}).get("metrics") or {}
    if not me:
        return []
    ref = [x for k, x in rows.items() if k != sid and "before_stable_window" not in (x.get("reasons") or ())]

    def val(m, k):
        v = m.get(k)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else None

    out = []
    for k in SHAPE_METRICS:
        v = val(me, k)
        r = [x for x in (val(y.get("metrics") or {}, k) for y in ref) if x is not None]
        if v is None or len(r) < 2:
            continue
        d = v - float(np.median(r))
        # the uncertainty of the DIFFERENCE: this scan's own sd (a noisier scan's metric is less certain) with the
        # stable scans' typical sd
        mine = val(me, C._sd_key(k)) or 0.0
        sds = [x for x in (val(y.get("metrics") or {}, C._sd_key(k)) for y in ref) if x is not None]
        thr = max(float(C.SEL_FLOOR.get(k, 0.0)), 3 * float(np.hypot(mine, float(np.median(sds)) if sds else 0.0)))
        if abs(d) > thr:
            said = (f"white-line energy {d:+.2f} eV" if k == "wl_e_eV" else f"edge position {d:+.2f} eV"
                    if k == "delta_eV" else f"white-line height {d:+.3g}")
            out.append({"metric": k, "difference": d, "threshold": thr, "said": said + f" (threshold {thr:.2g})"})
    return out


def beyond_noise(sid: str, stability: Mapping | None, np) -> tuple[bool, list[dict]]:
    """``(evaluated, moved)`` for a scan the stability analysis puts before the stable window: its evolving
    normalised-shape metrics (else every shape metric) against the stable scans', by :func:`metric_shifts`' threshold
    (the stability rule's floor and 3 x the difference's sd). Not evaluated (no metrics): the stability rule stands."""
    rows = (stability or {}).get("rows") or {}
    if not ((rows.get(sid) or {}).get("metrics")):
        return False, []
    moved = metric_shifts(sid, stability, np)
    evo = set((stability or {}).get("evolving_metrics") or ())
    if evo & set(SHAPE_METRICS):
        moved = [m for m in moved if m["metric"] in evo]
    elif evo:
        return False, []                     # evolving in a metric the guard does not measure: the rule stands
    return True, moved


#: the normalised-shape guard of the ratio screens: a ratio_shape / post_drift flag drops a scan only when, after a
#: free scale AND offset onto the other scans' median (an intensity change and a background are not shape), the
#: smoothed residual still departs more than ``min_frac`` of the edge step and ``noise_mult`` times its own noise (the
#: largest of many smoothed points of pure noise reaches about 3 x: 5 x, as the package's own mad 5)
DISTORTION = {"min_frac": 0.05, "noise_mult": 5.0, "smooth_pts": 5}


def shape_distortion(r: Mapping, recs: Sequence[Mapping], win, E_edge, np, *, exclude: Sequence = ()) -> dict | None:
    a = r.get("aligned")
    others = [x["aligned"] for x in recs if x is not r and x.get("aligned") is not None]
    if a is None or len(others) < 2:
        return None
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        y = a.IF / a.I0
        ref = np.nanmedian(np.array([o.IF / o.I0 for o in others]), axis=0)
        E = a.E
        e0 = float(E_edge) if E_edge else float(np.nanmedian(E))
        pre, post = (E < e0 - 10) & np.isfinite(ref), (E > e0 + 30) & np.isfinite(ref)
        if pre.sum() < 2 or post.sum() < 3:
            return None
        step = float(np.median(ref[post]) - np.median(ref[pre]))
        ok = np.isfinite(y) & np.isfinite(ref)
        for lo, hi in exclude or ():
            ok &= ~((E >= lo) & (E <= hi))
        # the scale is set by the edge step (pre-edge AND post-edge in the fit: over a flat post-edge alone an offset
        # would absorb a collapse), the distortion is measured over the post-edge part of the ratio window (the edge
        # region is the shape screen's)
        m = ok & (E > e0 + 30) & (E >= win[0]) & (E <= win[1])
        fit = m | (ok & pre)
        n = DISTORTION["smooth_pts"]
        if not step > 0 or m.sum() < 2 * n + 3 or (fit & pre).sum() < 2:
            return None
        A = np.c_[y[fit], np.ones(fit.sum())]
        (c, b), *_ = np.linalg.lstsq(A, ref[fit], rcond=None)
        res = (c * y[m] + b - ref[m]) / step
        sm = np.convolve(res, np.ones(n) / n, "valid")
        noise = float(np.std(np.diff(res, 2)) / np.sqrt(6.0) / np.sqrt(n))
    worst = float(np.max(np.abs(sm)))
    thr = max(DISTORTION["min_frac"], DISTORTION["noise_mult"] * noise)
    return {"max_residual": worst, "threshold": thr, "distorted": worst > thr, "scale": float(c), "offset": float(b),
            "window_eV": [float(win[0]), float(win[1])], "rule": DISTORTION}


def _finite_span(r: Mapping, np) -> list[float] | None:
    a = r.get("aligned")
    if a is None:
        return None
    with np.errstate(all="ignore"):
        ok = np.isfinite(a.IF / a.I0)
    return [float(a.E[ok].min()), float(a.E[ok].max())] if ok.any() else None


def complete_window(absorber: Mapping, bt: Mapping, E_lo: float, E_hi: float) -> list[float] | None:
    """What a COMPLETE scan covers, edge-relative: from 10 eV before the end of the pre-edge window to 50 eV into the
    post-edge window (the span normalize_once needs to keep the beamtime's window): a shorter scan that covers it is
    complete, whatever the group's longest grid."""
    from xas_analysis.recipe_init import norm_range

    el, ed, E_edge = absorber.get("element"), absorber.get("edge"), absorber.get("E_edge_eV")
    if E_edge is None:
        return None
    rng = ((bt.get("windows") or {}).get(f"{el} {ed}") or {}).get("range") or norm_range(float(E_edge), E_lo, E_hi)
    return [float(rng[1]) - 10.0, float(rng[2]) + 50.0]


def decisions_statement(rows: Sequence[Mapping], stale: Sequence[Mapping] = ()) -> str:
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
    unmerged = [x for x in kept if x.get("cannot_merge")]
    if unmerged:
        said += (f" {len(unmerged)} kept scan(s) are NOT in the merge: " + "; ".join(f"{name(x)} ({x['cannot_merge']})"
                                                                               for x in unmerged[:20]) + ".")
    noted = [x for x in kept if x["notes"]]
    if noted:
        said += " Kept, with a remark: " + "; ".join(f"{name(x)} ({'; '.join(n['said'] for n in x['notes'])})"
                                                     for x in noted[:10]) + "."
    if stale:
        said += " " + " ".join(x["said"][:1].upper() + x["said"][1:] + "." for x in stale[:20])
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


def glitch_exclusions(bt: Mapping, extra: Sequence[Sequence[float]] = ()) -> list[list[float]]:
    """``[[lo, hi], ...]`` kept out of the normalisation (and ratio-screen) windows: the beamtime's I0 glitch (the
    consensus centre, or the survey's), every other dip most scans share (``other_dips_eV``), both +- max(1.5 FWHM,
    1 eV), and ``extra`` (glitches flagged in the merge). A glitch is FLAGGED and kept out of the fits, never removed
    from the data."""
    out = []
    cons = (bt or {}).get("consensus") or {}
    g = (bt or {}).get("glitch") or {}
    fwhm = float(cons.get("fwhm_eV") or g.get("fwhm_eV") or 0.5)
    half = max(GLITCH_EXCLUDE["fwhm"] * fwhm, GLITCH_EXCLUDE["min_half_eV"])
    cal = (bt or {}).get("calibration") or {}
    centres = []
    c = cons.get("center_eV") if cons.get("center_eV") is not None else g.get("E_eV")
    if c is not None and (cal.get("mode") == "glitch_I0" or cons.get("found")):
        centres.append(float(c))
        if int(cal.get("glitch_dips", 1)) == 2 and cal.get("shape_window_eV"):
            w = cal["shape_window_eV"]                # a doublet: its whole fit window (both dips)
            out.append([round(float(w[0]) + 1.5, 2), round(float(w[1]) - 1.5, 2)])
    centres += [float(x) for x in cons.get("other_dips_eV") or ()]
    out += [[round(x - half, 2), round(x + half, 2)] for x in centres]
    out += [[float(a), float(b)] for a, b in extra]
    merged: list[list[float]] = []
    for lo, hi in sorted(out):                 # overlapping windows are one window
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return merged


def tender_choice(E, y, E_edge: float | None, rng: Sequence[float], np) -> dict:
    """:data:`TENDER`: does this fluorescence curve need the tender options, and why (``{"tender": bool, "why": ...,
    "post_rise": ...}``)."""
    out: dict = {"rule_id": TENDER_RULE_ID, "tender": False, "post_rise": None}
    if E_edge is None:
        out["why"] = "no tabulated edge"
        return out
    E, y = np.asarray(E, float), np.asarray(y, float)
    post = (E >= rng[2]) & (E <= rng[3]) & np.isfinite(y)
    pre = (E >= rng[0]) & (E <= rng[1]) & np.isfinite(y)
    if post.sum() >= 5 and pre.sum() >= 3:
        step = float(np.median(y[post]) - np.median(y[pre]))
        slope = float(np.polyfit(E[post], y[post], 1)[0])
        if step > 0:
            out["post_rise"] = slope * float(rng[3] - rng[2]) / step
    if E_edge < TENDER["max_edge_eV"]:
        out.update(tender=True, why=(f"fluorescence at a tender edge ({E_edge:.0f} eV, under about "
                                     f"{TENDER['max_edge_eV'] / 1000:g} keV)"))
    elif out["post_rise"] is not None and out["post_rise"] >= TENDER["rise_min"]:
        # above 4 keV a rising post-edge is NOT taken as the gas-I0 response: no option changes, a note for review
        out["why"] = f"a hard-X-ray edge ({E_edge:.0f} eV): the tender options apply only under 4 keV"
        out["review_note"] = (f"The post-edge IF/I0 rises with E (+{100 * out['post_rise']:.0f} % of the edge step over "
                              f"the post-edge window) at a hard-X-ray edge ({E_edge:.0f} eV): normalised with the "
                              "standard options (the tender ones apply only under 4 keV); a large background, a "
                              "dilute sample or a distorted scan can do this; review the normalisation.")
    else:
        out["why"] = (f"a hard-X-ray edge ({E_edge:.0f} eV) whose post-edge does not rise"
                      + (f" ({100 * out['post_rise']:+.0f} % of the step)" if out["post_rise"] is not None else ""))
    return out


def tender_window(rng: Sequence[float], E_edge: float) -> list[float]:
    """The tender window rule (normalization.md): the pre-edge window ends before the resonant-Raman foot."""
    return [rng[0], round(min(float(rng[1]), E_edge - TENDER["pre_hi_below_edge_eV"]), 1), rng[2], rng[3]]


def normalize_once(E, y, n, absorber: Mapping, bt: Mapping, np, *, exclude_extra: Sequence = (),
                   transmission: bool = False) -> dict:
    """The kept scans' raw average, normalised ONCE: Victoreen + McMaster (``mback_xrs``, bg_decreasing default),
    with the tender-fluorescence options when :func:`tender_choice` says so, and the glitch windows kept out of the
    fit windows (:func:`glitch_exclusions`)."""
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
    tender = tender_choice(E, y, float(E_edge), rng, np)
    if transmission:                       # the tender options model a fluorescence detector's response, not ln(I0/I1)
        tender = {**tender, "tender": False, "why": "transmission: the tender-fluorescence options do not apply"}
    opts: dict = {}
    if tender["tender"]:
        opts = dict(TENDER["options"])
        rng = tender_window(rng, float(E_edge))
        tender["options"] = opts
        tender["window_eV"] = rng
        tender["statement"] = (f"Tender-fluorescence normalisation ({TENDER_RULE_ID}): {tender['why']}, so the engine's "
                               "documented options are used (normalization.md, 'Tender fluorescence'): the I0 response "
                               f"(E/E_edge)^{opts['response_power']:g} divides the whole signal, a falling pre-edge "
                               "tail and a linear step factor (step_slope 1) are fitted, and the pre-edge window ends "
                               f"{TENDER['pre_hi_below_edge_eV']:g} eV below the edge (before the resonant-Raman foot): "
                               f"window {rng}.")
    else:
        tender["statement"] = f"Standard normalisation (no tender options): {tender['why']}."
    excl = [w for w in glitch_exclusions(bt, exclude_extra)
            if w[1] >= rng[0] and w[0] <= rng[3] and not (w[0] > rng[1] and w[1] < rng[2])]
    if excl:
        opts["exclude_eV"] = excl
    out["tender"] = tender
    out["exclude_eV"] = excl
    if excl:
        out["exclude_statement"] = (f"Kept out of the normalisation windows (glitches, flagged, never removed from the "
                                    f"data): {', '.join(f'{a:g}-{b:g} eV' for a, b in excl)}.")
    out["options"] = opts
    out["window_eV"] = rng
    out["window_basis"] = {
        "beamtime": "the beamtime's one window for this edge (recipe_init.norm_range on the modal grid): the same for "
                    "every compared series",
        "beamtime_clipped": "the beamtime's one window for this edge, its outer ends clipped to this group's data (the "
                            "pre-edge end and post-edge start are the series' own)",
        "group": "the group's own window (its scans do not cover the beamtime's): recipe_init.norm_range"}[basis]
    out["window_fixed_for_series"] = basis in ("beamtime", "beamtime_clipped")
    out["params"] = {"model": "victoreen", "element": el, "core": ed, "range": rng, "bg_decreasing": True, **opts}
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        try:
            r = mback_xrs(el, E, y, rng, ed, **opts)
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"{type(exc).__name__}: {exc}"[:300]
            return out
        A = _f(r.info["A_edge"])
        out.update(A_edge=A, norm=np.asarray(r.norm_xas, float), mu=np.asarray(r.mu, float),
                   bg=np.asarray(r.info["bg"], float), background=r.info.get("bg_params"),
                   pre_rms=_f(r.info.get("pre_rms")), post_rms=_f(r.info.get("post_rms")),
                   post_level=_post_level(r, np))
        spread, wl = [], []
        Ev = np.asarray(E, float)
        in_wl = (Ev >= float(E_edge) + WL_RANGE_EV[0]) & (Ev <= float(E_edge) + WL_RANGE_EV[1])
        for dp in WL_VARIANTS["pre_hi"]:
            for dl in WL_VARIANTS["post_lo"]:
                for dh in WL_VARIANTS["post_hi"]:
                    w = [rng[0], rng[1] + dp, rng[2] + dl, rng[3] + dh]
                    if w[1] <= w[0] + 5 or w[3] <= w[2] + 30:
                        continue
                    try:
                        rv = mback_xrs(el, E, y, w, ed, **opts)
                        a = _f(rv.info["A_edge"])
                    except Exception:  # noqa: BLE001
                        a = rv = None
                    if not a:
                        continue
                    if dp in WINDOW_VARIANTS["pre_hi"] and dl in WINDOW_VARIANTS["post_lo"] and dh in WINDOW_VARIANTS["post_hi"]:
                        spread.append((w, a))
                    if in_wl.any():
                        h = _f(np.nanmax(np.asarray(rv.norm_xas, float)[in_wl]))
                        if h is not None:
                            wl.append(h)
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
        h0 = _f(np.nanmax(out["norm"][in_wl])) if in_wl.any() else None
        if h0 is not None and len(wl) >= 3:
            out["uncertainty"].update(
                white_line_height=round(h0, 4), white_line_min=round(min(wl), 4), white_line_max=round(max(wl), 4),
                white_line_windows_tried=len(wl), white_line_spread=round((max(wl) - min(wl)) / h0, 4),
                white_line_statement=(
                    f"The white-line height (the normalised maximum {WL_RANGE_EV[0]:+g} to {WL_RANGE_EV[1]:+g} eV from "
                    f"the tabulated edge) is {h0:.3f}; over {len(wl)} window choices (pre-edge end -10..0 eV, post-edge "
                    f"start 0..+50 eV, post-edge end -100..0 eV from the window used) it ranges {min(wl):.3f}-"
                    f"{max(wl):.3f} ({100 * (max(wl) - min(wl)) / h0:.1f} % of it). That is the normalisation-window "
                    "uncertainty only; another convention (a flattened post-edge, area normalisation) moves it more, "
                    "and no self-absorption correction is applied."))
    return out


#: WHAT THE FILES STATE ABOUT THE COUNTS (processing-science audit of 18 Nov 2026, finding 8): the attenuator setting
#: (the ``filter`` a SPEC #P line states as key=value) of each kept scan, and the counts per point in the post-edge
#: (the median IF above E_edge + DOSE["post_eV"], as written), with what is NOT corrected.
NOT_CORRECTED_SAID = ("No dead-time correction beyond the detector column as the beamline wrote it, and no self-"
                      "absorption (over-absorption) correction is applied.")


def acquisition_block(kept: Sequence[Mapping], E_edge: float | None, transmission: bool, np) -> dict:
    from . import run as R

    filt = [R._header_setup(r.get("header")).get("filter") for r in kept]
    stated = sorted({v for v in filt if v is not None})
    counts = [] if transmission or E_edge is None else [
        float(np.median(r["IF"][m])) for r in kept if (m := np.isfinite(r["IF"]) & (r["E"] > E_edge + DOSE["post_eV"])).sum() >= 3]
    out: dict = {"attenuator_filter": stated or None,
                 "attenuator_stated_in": f"{sum(v is not None for v in filt)} of {len(kept)} kept scans",
                 "post_edge_counts_per_point": ({"median": round(float(np.median(counts)), 1),
                                                 "min": round(min(counts), 1), "max": round(max(counts), 1),
                                                 "scans": len(counts)} if counts else None)}
    parts = [("Attenuator (filter, as the #P line states it): " + ", ".join(f"{v:g}" for v in stated)
              + f" ({out['attenuator_stated_in']})") if stated else "No attenuator (filter) setting was read from the files' #P key=value lines"]
    if counts:
        parts.append(f"counts per point in the post-edge (median IF above E_edge + {DOSE['post_eV']:g} eV, as written): "
                     f"median {np.median(counts):.0f}, {min(counts):.0f}-{max(counts):.0f} over {len(counts)} kept scans")
    elif transmission:
        parts.append("counts per point are not given for transmission (ln(I0/I1) is not a count)")
    out["statement"] = "; ".join(parts) + ". " + NOT_CORRECTED_SAID
    return out


#: E0 AS REPORTED (processing-science audit of 18 Nov 2026, finding 5): larch find_e0 returns a GRID POINT (the
#: maximum of the first derivative, no sub-grid interpolation), so it is reported to 0.01 eV with the grid step there
#: as its resolution, and said apart from the tabulated edge the normalisation locks its step to.
E0_DEFINITION = ("larch find_e0 on the merged raw {signal}: the grid point of the maximum first derivative (no sub-grid "
                 "interpolation; on a rising white line competing maxima can move it by about a grid step or more)")


def e0_block(E, e0: float, absorber: Mapping, np, *, transmission: bool = False) -> dict:
    E = np.asarray(E, float)
    k = int(np.argmin(np.abs(E - e0)))
    steps = np.diff(E[max(0, k - 2):k + 3])
    step = float(np.median(steps)) if steps.size else None
    tab = absorber.get("E_edge_eV")
    definition = E0_DEFINITION.format(signal="ln(I0/I1)" if transmission else "IF/I0")
    out = {"e0_eV": round(float(e0), 2), "definition": definition, "grid_step_eV": round(step, 3) if step else None,
           "tabulated_edge_eV": tab}
    out["statement"] = (f"E0 {out['e0_eV']:.2f} eV: {definition}; the grid step there is "
                        + (f"{step:.2f} eV, its resolution" if step else "unknown")
                        + (f". The normalisation locks its step at the tabulated {absorber.get('element')} "
                           f"{absorber.get('edge')} edge, {tab:g} eV, a different definition"
                           if isinstance(tab, (int, float)) else "") + ".")
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
        reasons_warn.append(NO_REFERENCE_FLAG)
        st[NO_REFERENCE_FLAG] = (bt.get("routes") or [{}])[0].get("statement")
    if table["counts"]["dropped"] > table["counts"]["kept"]:
        reasons_warn.append("most_scans_dropped")
    if table["counts"].get("kept_not_merged"):
        reasons_warn.append("kept_scan_not_merged")
        st["kept_scan_not_merged"] = "; ".join(f"{x['scan_id']}: {x['cannot_merge']}" for x in table["rows"]
                                               if x.get("cannot_merge"))
    if (res.get("spots") or {}).get("outcome") == SPOTS_DISAGREE_FLAG:
        reasons_warn.append(SPOTS_DISAGREE_FLAG)
        st[SPOTS_DISAGREE_FLAG] = res["spots"]["statement"]
    if table.get("overrides_not_applied"):
        reasons_warn.append("override_not_applied")
        st["override_not_applied"] = "; ".join(x["said"] for x in table["overrides_not_applied"])
    if res.get("point_exclusions"):
        st["point_exclusions"] = res["point_exclusions"]["statement"]
    outside = [r["scan_id"] for r in kept if (r.get("alignment") or {}).get("outside_foil_timeline")]
    if outside:
        reasons_warn.append(OUTSIDE_TIMELINE_FLAG)
        st[OUTSIDE_TIMELINE_FLAG] = (f"{len(outside)} merged scan(s) {OUTSIDE_TIMELINE_SAID}: "
                                     + ", ".join(outside[:10]) + (" ..." if len(outside) > 10 else ""))
    if (nm.get("tender") or {}).get("review_note"):
        reasons_warn.append("post_edge_rises")
        st["post_edge_rises"] = nm["tender"]["review_note"]
    if res.get("dose_damage"):
        st["dose_damage"] = res["dose_damage"]["statement"]
        if res["dose_damage"].get("outcome") == "question":
            reasons_warn.append(DOSE_QUESTION_FLAG)
            st[DOSE_QUESTION_FLAG] = res["dose_damage"]["statement"]
    if (nm.get("tender") or {}).get("statement"):
        st["normalization_options"] = nm["tender"]["statement"]
    if nm.get("exclude_statement"):
        st["normalization_excluded"] = nm["exclude_statement"]
    if R_FALLBACK in (res.get("review_flags") or ()):
        reasons_warn.append(R_FALLBACK)
        st[R_FALLBACK] = ((res.get("channel_choice") or {}).get("basis") or {}).get("fallback_from", {}).get("statement")
    mc = res.get("measurement_mode") or {}
    if mc.get("mode") in ("unknown", None):
        reasons_warn.append("measurement_mode_unknown")
        st["measurement_mode_unknown"] = mc.get("statement")
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


R_FALLBACK = "channel_fallback_transmission_not_positive"     # run.FALLBACK_FLAG


def ratio_screens(E_edge: float | None, target, bt: Mapping) -> dict:
    """The engine's ratio_shape and post_drift screens (pipeline._screen), edge-relative (the package author's
    BL6-2c recipe, Pt L3: ratio window E_edge + 6 eV to the grid end, 5 %; post-edge levels E_edge + 60..95 eV vs the
    last 40 eV, 15 % of the step), the glitch windows kept out. Report-only, as every screen: a flag drops a scan only
    when its NORMALISED shape is distorted (:data:`DISTORTION`)."""
    if E_edge is None or target is None or len(target) < 10:
        return {}
    lo, hi = float(target[0]), float(target[-1])
    out: dict = {}
    if hi - 5 > E_edge + 6 + 30:
        out["ratio_shape"] = {"window_eV": [round(E_edge + 6, 1), round(hi - 5, 1)],
                              "exclude_eV": glitch_exclusions(bt), "mad": 5, "min_frac": 0.05, "smooth_pts": 5}
    a1, b1, a2, b2 = E_edge + 60, E_edge + 95, hi - 45, hi - 5
    if a2 > b1 + 20 and lo < E_edge - 15:
        out["post_drift"] = {"windows": [[round(a1, 1), round(b1, 1)], [round(a2, 1), round(b2, 1)]],
                             "pre_eV": [round(lo + 1, 1), round(E_edge - 10, 1)], "mad": 5, "min_frac": 0.15}
    return out


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
                       "reference_scans": len(info.get("scans") or ()), "reference_anchor_std_eV": info.get("std_eV"),
                       "reference_statistic": info.get("statistic", "median"),
                       **({"consensus_eV": info["consensus_eV"], "fit_offset_eV": info.get("fit_offset_eV")}
                          if info.get("consensus_eV") is not None else {}),
                       **({"reference_moved": info["reference_moved"]} if info.get("reference_moved") else {})})
    sv = bt.get("survey") or {}
    why = list(((sv.get("recommendation") or {}).get("why")) or ())
    cons = bt.get("consensus") or {}
    if cons.get("statement"):
        why.append(cons["statement"])
    why += list(bt.get("consensus_said") or ())
    mode = routes[0]["mode"] if routes else None
    plain = {"ref_foil": "an in-scan reference foil in transmission", "glitch_I0": "the I0 glitch",
             "foil_timeline": "separate foil scans over time", "none": "no energy reference"}.get(mode, str(mode))
    first = routes[0] if routes else {}
    stmt = (f"Energy reference: {plain}"
            + (f" ({first.get('method')} fit, window {first.get('window_eV')})" if first.get("window_eV") else "")
            + (f", anchored on the earliest group {first.get('reference_name')} (median of {first.get('reference_scans')} "
               f"scans with a good anchor, {first.get('reference_anchor_eV'):.4f} eV)" if first.get("reference_anchor_eV") else "")
            + ". " + ({0: "The files hold no mono reset line (no calibration record). ",
                      1: "The mono was foil-calibrated by the beamline staff at the start of the beamtime (one mono "
                         "reset line). "}.get(len(sv.get("calibration_log") or ()),
                                             f"The files state {len(sv.get('calibration_log') or ())} mono resets. "))
            + "Every scan of every sample is aligned to this one reference, never to its own sample's edge.")
    if len(routes) > 1:
        stmt += " A scan whose foil edge is not usable is aligned on the I0 glitch instead."
    if mode == "none":
        stmt = ("NO ENERGY REFERENCE: no in-scan foil, no I0 glitch in most scans, no foil scans. No scan was aligned "
                "(every shift is 0); energies are only as good as the beamline calibration. Look at each result and "
                "approve it on its own (a bulk approval refuses it).")
    bad = [r["scan_id"] for r in recs if not (r.get("alignment") or {}).get("ok")]
    if bad:
        stmt += (f" {len(bad)} scan(s) of this group are not aligned (no energy reference found in the scan, or the "
                 f"reference feature fit failed) and are not merged: {', '.join(bad[:10])}"
                 + (f" and {len(bad) - 10} more" if len(bad) > 10 else "") + ".")
    return {"routes": routes, "why": why, "mono_reset_lines": (sv.get("calibration_log") or [])[:20],
            "survey_warnings": list(sv.get("warnings") or ())[:10], "statement": stmt,
            "beamtime_fingerprint": bt.get("fingerprint")}


#: what ``applied_shift_eV`` 0.0 on a v1 result means: no ABSOLUTE calibration was applied. The absolute scale is the
#: staff's foil calibration of the mono, not traced to a tabulated energy nor across beamtimes (processing-science
#: audit of 18 Nov 2026, finding 2: v1 said none "is needed", which overclaims).
ABSOLUTE_CALIBRATION_SAID = ("No absolute energy calibration was applied (shift 0 eV).{alignment}{scale} It is not "
                             "traced to a tabulated energy, and not across beamtimes: energies from two beamtimes may "
                             "differ by a constant offset.")
SET_POINT_NONE = ("The files hold no calibration record (no mono reset line): the absolute scale is the monochromator's "
                  "as the beamline set it, undocumented here.")


def calibration_set_points(ref: Mapping) -> list[dict]:
    """The ``mono reset from A to B`` lines of the beamtime's files (energy_reference.mono_reset_lines), as read."""
    return [x for x in (ref or {}).get("mono_reset_lines") or ()
            if isinstance(x, Mapping) and isinstance(x.get("to"), (int, float))]


def _set_points_said(pts: Sequence[Mapping]) -> str:
    said = "; ".join(f"`{x.get('axis') or 'mono'} reset from {x['from']:g} to {x['to']:g}`"
                     + (f" at {x['time']}" if x.get("time") else "") for x in pts[:3])
    return said + (f"; and {len(pts) - 3} more" if len(pts) > 3 else "")


def absolute_calibration_said(ref: Mapping, mode: str | None = None) -> str:
    """Review of PR 345, I3: the alignment clause follows the route; no reset line is no calibration record; "at the
    start of the beamtime" only when the files state one reset."""
    pts = calibration_set_points(ref)
    alignment = (" No scan is aligned: the beamtime has no energy reference." if mode in ("none", None) else
                 " The scans are aligned to one beamtime reference (the alignment says how many).")
    if not pts:
        scale = " " + SET_POINT_NONE
    elif len(pts) == 1:
        scale = (" The absolute scale rests on the beamline staff's foil calibration of the monochromator at the start "
                 f"of the beamtime, as the files state it: {_set_points_said(pts)}.")
    else:
        scale = (" The absolute scale rests on the beamline staff's foil calibration of the monochromator; the files "
                 f"state {len(pts)} mono resets: {_set_points_said(pts)}.")
    return ABSOLUTE_CALIBRATION_SAID.format(alignment=alignment, scale=scale)


_ROUTE_SAID = {"ref_foil": "an in-scan reference foil in transmission", "glitch_I0": "the I0 glitch",
               "foil_timeline": "separate foil scans over time", "none": "no energy reference"}


def energy_story(res: Mapping) -> dict:
    """``{"absolute_calibration": ..., "alignment": ...}`` of a v1 result, from its ``energy_reference``,
    ``scan_shifts`` and ``scan_decisions`` (so a result stored before this was written is said the same way).

    The two words mean two things (end-to-end test on real data, 17 Nov 2026: the calibration block said "no energy
    reference" while the energy reference showed an I0-glitch alignment of +67 to +72 meV). CALIBRATION is absolute
    (onto tabulated energies): none applied; the scale is the staff's foil calibration of the mono (its set-point said
    when the files state it), not traced across beamtimes. ALIGNMENT is per scan: every scan shifted onto
    the ONE beamtime reference."""
    ref = res.get(REFERENCE_KEY) or {}
    route = (ref.get("routes") or [{}])[0] or {}
    mode = route.get("mode")
    rows = (res.get(SHIFTS_KEY) or {}).get("rows") or []
    merged = {x.get("scan_id") for x in (res.get(DECISIONS_KEY) or {}).get("rows") or () if x.get("merged")}
    aligned = [x for x in rows if x.get("ok") and isinstance(x.get("shift_eV"), (int, float))]
    in_merge = [x["shift_eV"] for x in aligned if x.get("scan_id") in merged] or [x["shift_eV"] for x in aligned]
    shown = (lambda v: f"{1000 * v:+.0f} meV")
    alignment: dict[str, Any] = {
        "kind": "per_scan_alignment", "route": mode, "method": route.get("method"),
        "window_eV": route.get("window_eV"), "reference_group_id": route.get("reference_group_id"),
        "reference_name": route.get("reference_name"), "reference_anchor_eV": route.get("reference_anchor_eV"),
        "reference_scans": route.get("reference_scans"), "scans_aligned": len(aligned), "scans_listed": len(rows),
        "shift_range_eV": [min(in_merge), max(in_merge)] if in_merge else None,
        "shift_range_of": "the merged scans" if merged and any(x.get("scan_id") in merged for x in aligned) else "the aligned scans",
    }
    if mode == "none" or not route:
        alignment["statement"] = ("No per-scan alignment: the beamtime has no energy reference (no in-scan foil, no I0 "
                                  "glitch in most scans, no foil scans), so every shift is 0.")
    else:
        anchor = route.get("reference_anchor_eV")
        alignment["statement"] = (
            f"Each scan was aligned to one beamtime energy reference, {_ROUTE_SAID.get(mode, str(mode))}"
            + (f" ({route.get('method')} fit, window {route['window_eV'][0]:g}-{route['window_eV'][1]:g} eV)"
               if isinstance(route.get("window_eV"), (list, tuple)) and len(route["window_eV"]) == 2 else "")
            + (f", anchored on the earliest group {route.get('reference_name')} at {anchor:.4f} eV (median of "
               f"{route.get('reference_scans')} scans)" if isinstance(anchor, (int, float)) else "")
            + f": {len(aligned)} of {len(rows)} scans aligned"
            + (f", shifts {shown(min(in_merge))} to {shown(max(in_merge))} ({alignment['shift_range_of']})"
               if in_merge else "") + ".")
    return {"absolute_calibration": {"applied": False, "applied_shift_eV": 0.0, "traced_across_beamtimes": False,
                                     "basis": "staff_foil_calibrated_mono",
                                     "set_points": [{k: x.get(k) for k in ("time", "axis", "from", "to")}
                                                    for x in calibration_set_points(ref)],
                                     "statement": absolute_calibration_said(ref, mode if route else None)},
            "alignment": alignment}


def _quick_merges(group, ctx, recs, kept, E, y, nm, e0, absorber, np, *, offset: float = 0.0) -> list[dict]:
    """The MERGE quick-merge comparison (quick_merge.py), with the quick merge normalised the way this result is.
    ``offset``: a transmission standard's constant (TRANSMISSION_RULE_ID), taken out of the curves compared (review of
    PR 345, M2); the quick merge's own ln(I0/I1) gets it back only while it is normalised."""
    from xas_analysis.model.mback_xrs import mback_xrs

    from . import quick_merge as QM

    rng = nm["window_eV"]
    e0v = e0 if e0 is not None else absorber.get("E_edge_eV")
    rp = {"pre1": rng[0] - e0v, "pre2": rng[1] - e0v, "norm1": rng[2] - e0v, "norm2": rng[3] - e0v, "nnorm": None}
    nmv = {"resolved_params": rp, "e0_eV": e0v, "edge_step": nm["A_edge"], "norm": nm["norm"]}
    M = np.array([np.interp(E, r["aligned"].E, r["aligned"].IF / r["aligned"].I0, left=np.nan, right=np.nan) for r in kept])
    M, y = M - offset, y - offset

    opts = nm.get("options") or {}

    def normalizer(e, yy):
        r = mback_xrs(absorber["element"], e, np.asarray(yy, float) + offset, rng, absorber["edge"], **opts)
        return np.asarray(r.norm_xas, float), float(r.info["A_edge"])

    return QM.compare_group(group, ctx, grid_ok=E, mean=y, nm=nmv, M=M, grid=E, used_entries=[r["entry"] for r in kept],
                            inputs=[r["entry"] for r in recs], normalizer=normalizer)


# --- the plot ----------------------------------------------------------------------------------------------------


def plot(path: Path, group, recs, table, E, y, nm, e0, absorber, np, *, offset: float = 0.0, signal: str = "IF/I0"
         ) -> bool:
    """``offset``: a transmission standard's constant, taken out of the raw panel (review of PR 345, M1)."""
    from ._deps import require

    mpl = require().get("matplotlib")
    if mpl is None:
        return False
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 8.4), sharex=False)
    lo, hi = (absorber["E_edge_eV"] - 20, absorber["E_edge_eV"] + 60) if absorber.get("E_edge_eV") else (E[0], E[-1])
    shown = 0
    palette = ["tab:blue", "tab:orange", "tab:green", "tab:purple", "tab:brown", "tab:pink", "tab:olive", "tab:cyan"]
    labs = sorted({row["spot"] for row in table["by_id"].values() if row.get("spot")}, key=lambda x: int(x.split()[-1]))
    spot_colors = {lab: palette[k % len(palette)] for k, lab in enumerate(labs)}
    for r in recs:
        a = r.get("aligned")
        row = table["by_id"][r["scan_id"]]
        if a is None:
            continue
        with np.errstate(all="ignore"):
            yy = a.IF / a.I0 - offset
        # scans coloured by spot (the spot named in the legend) when the group has several
        sp = row.get("spot")
        color = spot_colors.get(sp) if sp else None
        tag = f" [{sp}]" if sp and len(spot_colors) > 1 else ""
        if row["decision"] == "keep":
            ax1.plot(a.E, yy, lw=0.8, alpha=0.75, color=color,
                     label=f"{r['stem'][:18]} #{r['num']}{tag} kept ({1000 * (row['shift_eV'] or 0):+.0f} meV)"
                     if shown < 14 else None)
        else:
            why = ", ".join(sorted({x["code"] for x in row["reasons"]})) or "scientist"
            ax1.plot(a.E, yy, lw=0.9, ls="--", alpha=0.8, color=color,
                     label=f"{r['stem'][:18]} #{r['num']}{tag} DROPPED: {why}"[:80] if shown < 14 else None)
        shown += 1
    ax1.plot(E, y - offset, color="k", lw=1.8, label=f"average of {table['counts']['kept']} kept (raw {signal})")
    unaligned = [f"#{r['num']}" for r in recs if r.get("aligned") is None]
    if unaligned:
        # a scan with no energy anchor cannot be drawn on the aligned axis: named, never hidden
        ax1.plot([], [], ls="--", color="0.5", label=f"not drawn (no energy anchor, dropped): {', '.join(unaligned)}"[:70])
    ax1.set_xlim(lo, hi)
    ax1.set_ylabel(f"raw {signal} (aligned)")
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
    if c.get("kept_not_merged"):
        s += f", {c['kept_not_merged']} kept but not merged (no energy reference)"
    if t.get("overrides_not_applied"):
        s += f", {len(t['overrides_not_applied'])} override(s) not applied"
    return s + f" ({DECISION_RULE_ID})"


def show_blocks(r: Mapping, *, full: bool = False) -> dict:
    """``bundle show processing-result``'s v1 blocks, in plain words: the engine, the energy reference and its
    evidence, the shift table, the decision table and the normalisation convention."""
    out: dict = {}
    if SPOTS_DISAGREE_FLAG in (r.get("review_flags") or ()):
        out["spots_warning"] = (r.get("spots") or {}).get("statement")
    if NO_REFERENCE_FLAG in (r.get("review_flags") or ()):
        out["warning"] = ("NO ENERGY REFERENCE for this beamtime: no scan was aligned (every shift is 0). Look at this "
                          "result and approve it on its own; a bulk approval refuses it.")
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
            if x.get("cannot_merge"):
                s += f" - {x['cannot_merge'].upper()[:1]}{x['cannot_merge'][1:]}"
            if x.get("notes"):
                s += " - remark: " + "; ".join(n["said"] for n in x["notes"])
            return s
        shown = rows if full else rows[:30]
        out["scan_decisions"] = {"rule_id": t.get("rule_id"), "rule": t.get("rule"), "counts": t.get("counts"),
                                 "rows": [line(x) for x in shown],
                                 **({"rows_not_shown": len(rows) - len(shown)} if len(rows) > len(shown) else {}),
                                 **({"overrides_not_applied": [x["said"] for x in t["overrides_not_applied"]]}
                                    if t.get("overrides_not_applied") else {}),
                                 "override": t.get("override_command")}
    sp = r.get("spots")
    if isinstance(sp, Mapping):
        def fmt(v):
            return "n/a" if v is None else f"{v:.3g}"
        out["spots"] = {"statement": sp.get("statement"), "outcome": sp.get("outcome"),
                        "rows": [f"{x['name']} ({x['spot']}): {len(x['scans'])} scans, {len(x['kept'])} kept; white-line "
                                 f"height {fmt(x.get('white_line_height'))}, edge step {fmt(x.get('edge_step'))}"
                                 for x in sp.get("spots") or ()]}
    mm = r.get("measurement_mode")
    if isinstance(mm, Mapping):
        out["measurement_mode"] = mm.get("statement")
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
                                "tender": (nm.get("tender") or {}).get("statement"),
                                **({"excluded": nm["exclude_statement"]} if nm.get("exclude_statement") else {}),
                                "uncertainty": (nm.get("uncertainty") or {}).get("statement"),
                                **({"error": nm["error"]} if nm.get("error") else {})}
    return out
