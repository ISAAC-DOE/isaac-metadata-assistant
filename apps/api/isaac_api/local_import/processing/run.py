"""Run protocol ``isaac.xas.v0`` over a bundle's record groups and write the results.

Outputs, all under ``<bundle_dir>/processing/`` (paths in results are relative to
``<bundle_dir>``; every file carries its sha256):

* ``processing_results.json`` — ``processing_results[]`` (record groups; one
  ``isaac_protocol`` entry per group, plus a ``scientist_athena`` entry when an Athena group
  matches) and ``unread_acquisition_results[]`` for acquisitions the import could not read;
* ``<group_id>/merged.csv``, ``normalized.csv``, ``qc.json``, ``params.json``, ``plot.png``
  and, when matched, ``athena_normalized.csv``;
* ``status.json`` — ``processing_unavailable`` when numpy/xraylarch are missing (no
  results are fabricated).

A group the protocol CANNOT APPLY to gets no QC verdict: its result carries
``applicability = {status: "not_applicable", reason_code, ...}`` instead
(:func:`_not_applicable`). The boundary is what the code detects, never a reader name:
``no_scans`` when the group lists no scan at all (nothing to process), ``no_xas_channel``
when :func:`channels.choose_channels` forms no channel (energy axis + signal) in ANY of the
group's readable scans and no scan with an energy axis has a signal-side candidate column
that is present but dead (that is ``fail signal_channel_dead``). When only some scans form a
channel, the first that does supplies the choice, the others are skipped and counted, and
QC warns ``scans_skipped_lacking_chosen_columns``. When the chosen channel is transmission and
it is not positive in every scan, the next alternative (fluorescence) is used, never silently
(:func:`_fallback_from_transmission`). What the data states about itself (run source type, the reader
and profile that claimed it, that reader's stated LAYOUT, the scan format and column labels)
is reported as literals beside it; no technique is inferred.

Raw data is READ from the source folder (``source_root``, else the bundle's
``local_root_hint``); each scan's bytes are checked against the bundle's
``content_sha256`` before use. Nothing is copied out of the source folder.
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import math
import re
import shutil
import tempfile
import warnings
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .. import bundle as B
from .. import grouping as G
from . import _deps
from . import athena as A
from . import core as C
from . import protocol as P
from .channels import MODE_TRANSMISSION, ChannelChoice, choose_channels, dead_candidates
from . import reference as REF
from .edges import edge_energy
from .readers import read_scan_file

PROCESSING_DIR = "processing"
RESULTS_FILE = "processing_results.json"
STATUS_FILE = "status.json"
RESULTS_FORMAT = "isaac.processing-results"
#: 0.2.0 (additive): ``applicability`` on a not-applicable result; ``summary.not_applicable``.
RESULTS_FORMAT_VERSION = "0.2.0"

ELEMENTS = frozenset(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr "
    "Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm "
    "Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu".split()
)
#: The region/method-file shape ``<Element><Edge>_...`` — the same shape
#: ``bl15.signals.RULE_METHOD_SYMBOL_ELEMENT_EDGE`` reads from a BL15-2 method macro.
_REGION_SYMBOL = re.compile(r"^([A-Z][a-z]?)(K|L[1-3]|M[1-5])_")
_TOKEN = re.compile(r"[_\-\s.]+")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=False, ensure_ascii=False, default=_jsonable) + "\n").encode("utf-8")


def _jsonable(o: Any):
    try:
        import numpy as np

        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:  # noqa: BLE001
        pass
    return str(o)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _resolve_source(root: Path, rel: str) -> Path | None:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts:
        return None
    full = root.joinpath(*p.parts)
    try:
        if full.is_symlink() or not full.resolve().is_relative_to(root.resolve()):
            return None
    except OSError:
        return None
    return full


def stated_reference(name: str, bundle: Mapping, header_lines: Sequence[str]) -> tuple[dict | None, str]:
    """A reference foil's element + edge, ONLY when evidence states both. (reference, reason).

    Element: the name has a ``foil`` token and exactly one token that is an element symbol
    (case-sensitive). Edge: the bundle's ``experiment.element_evidence`` for that element,
    and/or a header line shaped ``<El><Edge>_`` (an XDAC region file, e.g. ``ZzK_SYNTHETIC.rgn``);
    every stated edge must agree.
    """
    toks = [t for t in _TOKEN.split(name) if t]
    if not any(t.casefold().startswith("foil") for t in toks):
        return None, "name_has_no_foil_token"
    els = sorted({t for t in toks if t in ELEMENTS})
    if len(els) != 1:
        return None, f"foil_element_not_unique:{els}"
    el = els[0]
    basis = [{"kind": "name_token", "name": name, "element": el}]
    edges = set()
    for ev in (bundle.get("experiment") or {}).get("element_evidence") or ():
        if ev.get("element") == el and ev.get("edge"):
            edges.add(ev["edge"])
            basis.append({"kind": "bundle_element_evidence", "source_id": ev.get("source_id"), "locator": ev.get("locator"), "edge": ev["edge"]})
    for i, line in enumerate(header_lines):
        m = _REGION_SYMBOL.match(line.strip())
        if m and m.group(1) == el:
            edges.add(m.group(2))
            basis.append({"kind": "scan_header_region_symbol", "header_line_index": i, "literal": line.strip()[:80], "edge": m.group(2)})
    if len(edges) != 1:
        return None, f"edge_not_stated_uniquely:{sorted(edges)}"
    return {"element": el, "edge": next(iter(edges)), "basis": "stated_by_evidence", "evidence": basis}, "stated_by_evidence"


# --- per group ------------------------------------------------------------------------------


class _Ctx:
    def __init__(self, *, bundle, bundle_dir, root, params, np, xafs, out_dir, sources, runs_by_key):
        self.bundle = bundle
        self.bundle_dir = bundle_dir
        self.root = root
        self.params = params
        self.np = np
        self.xafs = xafs
        self.out_dir = out_dir
        self.sources = sources
        self.runs_by_key = runs_by_key


def group_scans(group: Mapping, runs_by_key: Mapping[str, Mapping]) -> tuple[list[dict], list[str], dict | None]:
    if group.get("group_kind") in ("unread_acquisition", "generic_run"):
        return [dict(s) for s in group.get("member_scans") or ()], list(group.get("stems") or [group.get("stem") or ""]), None
    scans, stems, sel = [], [], None
    context = set(group.get("context_run_keys") or ())
    for key in group.get("member_run_keys") or ():
        run = runs_by_key.get(key)
        if run is None or key in context:  # an exported file kept as context: no scans, no stem
            continue
        stems.append(run.get("stem") or "")
        sel = sel or run.get("signal_selection")
        for s in run.get("scans") or ():
            scans.append({"source_id": s.get("source_id"), "relative_path": s.get("relative_path"), "scan_index": s.get("scan_index"), "run_key": key})
    return scans, stems, sel


def _formed(choice) -> bool:
    return choice.energy is not None and choice.mode is not None


def _base(group: Mapping, source: str) -> dict:
    return {
        "result_id": f"proc-{group['group_id']}-{'isaac' if source == 'isaac_protocol' else 'athena'}",
        "group_id": group["group_id"],
        "group_kind": group.get("group_kind", "record_group"),
        "protocol_id": P.PROTOCOL_ID,
        "protocol_version": P.PROTOCOL_VERSION,
        "protocol_status": P.PROTOCOL_STATUS,
        "source": source,
        "inputs": [],
        "steps": [],
        "outputs": {"files": [], "e0_eV": None, "edge_step": None, "points": None},
        "qc": {"metrics": {}, "verdict": "fail", "reasons": []},
        "comparison": None,
        "state": "needs_review",
        "review_flags": ["protocol_draft_unreviewed"],
        "preferred_for_record": False,
        "failure": None,
        # outside every hashed output file, so it moves no id (protocol.RULE_VERSIONS_SINCE_PROTOCOL_VERSION)
        **({"rule_versions": copy.deepcopy(P.RULE_VERSIONS_SINCE_PROTOCOL_VERSION)} if source == "isaac_protocol" else {}),
    }


_RUN_DIR = re.compile(r"^r-[0-9a-f]{16}$")


def run_id_for(group_id: str, input_hashes: Sequence[str], data_hashes: Sequence[tuple[str, str]]) -> str:
    h = hashlib.sha256(json.dumps([P.PROTOCOL_ID, P.PROTOCOL_VERSION, group_id, list(input_hashes), [list(x) for x in data_hashes]]).encode())
    return "r-" + h.hexdigest()[:16]


def _fail(res: dict, code: str, detail: str = "") -> dict:
    res["failure"] = {"code": code, "detail": detail}
    rid = run_id_for(res["group_id"], [], [("failure", hashlib.sha256(f"{code}:{detail}".encode()).hexdigest())])
    res["run_id"] = rid
    res["result_id"] = f"proc-{res['group_id']}-{rid}-isaac"
    res["qc"] = {"metrics": res["qc"].get("metrics") or {}, "verdict": "fail", "reasons": [code]}
    return res


#: What each generic reader states about a file's LAYOUT — its own docstring's "layout from
#: the real files", literal structure only. Never a technique: ``xes_tab_v1`` itself "does
#: not say ... what technique produced the file", and neither does this table.
READER_LAYOUT = {
    "xes_tab_v1": "tab-separated columns whose header names are xes<N>",
    "mca_v1": "one MCA array of counts (#@MCA header, @A array)",
    "two_column_v1": "two numbers per line, no header",
    "ssrl_xdc_v1": "SSRL EXAFS Data Collector 4.0 text scan",
    "xdi_v1": "XDI text file",
}
NA_STATEMENTS = {
    B.NA_NO_SCANS: (
        "Nothing to process: this group lists no scan. This says nothing about data quality, "
        "so no QC verdict is given."
    ),
    B.NA_NO_XAS_CHANNEL: (
        f"No ISAAC processing protocol covers this data yet: {P.PROTOCOL_ID} could not form an "
        "absorption spectrum (an energy axis and an absorption signal) from these columns. This "
        "says nothing about data quality, so no QC verdict is given."
    ),
}
_MAX_LABELS_STATED = 16


def data_states(group: Mapping, runs_by_key: Mapping[str, Mapping], entries: Sequence[Mapping] = (), table: Any = None) -> dict:
    """What the group's data states about itself — literals only, no inferred technique."""
    readers, seen = [], set()
    for key in group.get("member_run_keys") or ():
        run = runs_by_key.get(key)
        if not run:
            continue
        rd = run.get("reader") or {}
        item = {"source_type": run.get("source_type"), "reader_id": rd.get("reader_id"), "profile": rd.get("profile")}
        k = tuple(item.values())
        if k not in seen:
            seen.add(k)
            readers.append(item)
    labels = list(table.labels) if table is not None else []
    return {
        "basis": "the runs' recorded source type and reader, that reader's stated file layout, and the scan's own column labels; no technique is inferred",
        "readers": readers,
        "reader_layout": sorted({READER_LAYOUT[r["profile"]] for r in readers if r.get("profile") in READER_LAYOUT}),
        "scan_formats": sorted({str(e["format"]) for e in entries if e.get("format")}),
        "column_labels": labels[:_MAX_LABELS_STATED],
        "column_labels_total": len(labels),
    }


def reader_label(result: Mapping) -> str:
    """The reader a not-applicable result's data came through: profile, else source type."""
    rs = ((result.get("applicability") or {}).get("what_the_data_states") or {}).get("readers") or []
    names = sorted({str(r.get("profile") or r.get("source_type") or "unknown") for r in rs})
    return "+".join(names) or "unknown"


def _not_applicable(res: dict, code: str, detail: str, states: Mapping) -> dict:
    """The protocol does not apply: an explicit outcome, never a QC verdict."""
    res["applicability"] = {
        "status": B.NOT_APPLICABLE,
        "reason_code": code,
        "detail": detail,
        "statement": NA_STATEMENTS[code],
        "what_the_data_states": dict(states),
    }
    rid = run_id_for(res["group_id"], [], [("not_applicable", hashlib.sha256(f"{code}:{detail}".encode()).hexdigest())])
    res["run_id"] = rid
    res["result_id"] = f"proc-{res['group_id']}-{rid}-isaac"
    res["qc"] = {"metrics": {}, "reasons": []}  # NO verdict: there is no curve to judge
    res["failure"] = None
    res["review_flags"] = ["no_isaac_protocol_applies"]
    return res


def _calibration(group: Mapping, stems: Sequence[str], scans_data: list[dict], headers: Sequence[str], ctx: _Ctx) -> dict:
    np, cp = ctx.np, ctx.params["calibration"]
    role = group.get("role", "sample")
    flags: list[str] = []
    # AUTHORITY: a params-file value or file-name evidence may only PROPOSE the reference
    # element/edge. The shift is APPLIED only under a scientist's processing-approval decision
    # (``calibration_approvals[group_id]``, recorded with a named decider).
    proposed = None
    param_ref = cp.get("proposed_reference")
    if param_ref:
        proposed = {"element": param_ref.get("element"), "edge": param_ref.get("edge"), "basis": "params_file_value"}
    approval = (ctx.calibration_approvals or {}).get(group["group_id"])
    approved = None
    if approval and str(approval.get("decided_by") or "").strip() and approval.get("element") and approval.get("edge"):
        approved = {
            "element": approval["element"],
            "edge": approval["edge"],
            "basis": "scientist_decision",
            "decided_by": approval["decided_by"],
            "decision_id": approval.get("decision_id"),
        }
    elif approval:
        flags.append("calibration_approval_incomplete_ignored")
    per_scan: list[dict | None] = []
    ref_source = None
    unconfirmed_reason = None
    if role == "reference":
        ref_source = "reference_group_own_signal"
        per_scan = [C.edge_e0(sa["energy"], sa["mu"], np, ctx.xafs) for sa in scans_data]
        if not proposed:
            stated, unconfirmed_reason = stated_reference(stems[0] if stems else "", ctx.bundle, headers)
            if stated:
                proposed = stated
    elif cp.get("use_in_scan_reference_channel") and any(sa.get("mu_ref") is not None for sa in scans_data):
        ref_source = "in_scan_reference_channel"
        per_scan = [C.edge_e0(sa["energy"], sa["mu_ref"], np, ctx.xafs) if sa.get("mu_ref") is not None else None for sa in scans_data]
        unconfirmed_reason = "in_scan_reference_element_not_confirmed"
    else:
        flags.append("no_reference_available")
        unconfirmed_reason = "no_reference"
    min_snr = float(cp["reference_min_edge_snr"])
    usable = [r for r in per_scan if r and r.get("e0_eV") is not None and (r.get("snr") or 0) >= min_snr]
    if per_scan and not usable:
        flags.append("reference_edge_not_found")
    # c12-cal (REF.IN_SCAN_MIN_RULE_ID): an in-scan reference whose edge is usable in fewer than
    # MIN_IN_SCAN_REFERENCE_SCANS scans is no reference: no shift is computed or applied, even under an approval
    too_few = ref_source == REF.IN_SCAN and 0 < len(usable) < REF.MIN_IN_SCAN_REFERENCE_SCANS
    if too_few:
        flags.append(REF.TOO_FEW_FLAG)
    measured = spread = None
    if usable:
        e0s = [r["e0_eV"] for r in usable]
        measured = float(np.median(e0s))
        spread = float(max(e0s) - min(e0s))
    ref = approved or proposed
    tab = tab_src = shift = None
    applied = 0.0
    if not approved:
        flags.append("calibration_reference_unconfirmed")
    accepted = approval.get("accepted_shift_eV") if approved and approval else None
    if ref and measured is not None and not too_few:
        tab, tab_src = edge_energy(ref["element"], ref["edge"])
        if tab is None:
            flags.append("edge_energy_unknown")
        else:
            shift = tab - measured
            if abs(shift) > float(cp["max_plausible_shift_eV"]):
                flags.append("shift_implausible_not_applied")
            elif not approved:
                flags.append("calibration_shift_awaiting_approval")
            elif abs(shift) > float(ctx.params["qc"]["warn_energy_shift_eV"]) and not REF.shift_size_confirmed(accepted, shift):
                # c12-cal (REF.SHIFT_SIZE_RULE_ID): a shift above the warning level moves every energy of the record by
                # that much; it is applied only when the scientist also confirmed its size (--accept-shift)
                flags.append(REF.SIZE_NOT_CONFIRMED_FLAG)
            elif cp.get("apply_shift_when_confirmed"):
                applied = shift
    if approved:
        unconfirmed_reason = None
    elif proposed:
        unconfirmed_reason = "proposed_not_approved"
    confirmed = approved
    basis = approved or proposed
    per_scan_shifts = None
    if cp.get("align_scans_by_reference") and usable and len(usable) == len(scans_data):
        per_scan_shifts = [measured - r["e0_eV"] for r in per_scan]  # type: ignore[index]
    return {
        "step": "calibration",
        "params": {
            k: cp[k] for k in ("use_in_scan_reference_channel", "reference_min_edge_snr", "apply_shift_when_confirmed", "max_plausible_shift_eV", "align_scans_by_reference", "proposed_reference")
        },
        "outcome": {
            "reference_source": ref_source,
            "reference_e0_per_scan_eV": [r.get("e0_eV") if r else None for r in per_scan],
            "reference_snr_per_scan": [r.get("snr") if r else None for r in per_scan],
            "measured_reference_e0_eV": measured,
            "reference_e0_spread_eV": spread,
            "reference": basis,
            "reference_approved": bool(confirmed),
            "unconfirmed_reason": unconfirmed_reason,
            "tabulated_edge_eV": tab,
            "tabulated_edge_source": tab_src,
            "computed_shift_eV": shift,
            "applied_shift_eV": applied,
            "applied": bool(applied),
            "per_scan_alignment_shifts_eV": per_scan_shifts,
            "method": "larch find_e0 (maximum of the first derivative)",
            # only when the scientist confirmed a shift's size (absent otherwise, so an unaffected result is unchanged)
            **({"accepted_shift_eV": float(accepted)} if accepted is not None else {}),
        },
        "flags": flags,
    }


def _said_reference(cal: dict) -> dict:
    """``cal`` with what its reference reading says (:func:`reference.reading`: the usable / listed scan counts,
    whether a reference is proposed, a plain sentence, and a spread that is null with fewer than two usable scans)
    added to its outcome. Returns the outcome AS IT IS HASHED (params.json, qc.json): exactly the keys and values
    the step had before these sentences existed, so a group whose curve does not change keeps its result id."""
    hashed = copy.deepcopy(cal["outcome"])
    said = REF.reading(cal)
    cal["outcome"].update({k: said[k] for k in ("reference_scans_usable", "reference_scans_listed", "reference_min_scans",
                                                "reference_proposed", "reference_statement")})
    if said["reference_e0_spread_eV"] is None:
        cal["outcome"]["reference_e0_spread_eV"] = None
    return hashed


def _few_scan_glitch_statement(n_scans: int, flagged: int, params: Mapping) -> str | None:
    """The sentence for a result whose glitch points were judged against their neighbours (fewer than
    ``deglitch.min_scans_for_cross_scan`` scans), or ``None`` (nothing flagged, or enough scans for the cross-scan
    check). Measured on a real beamtime: a clean Ti foil (one scan) had 21 points flagged at z up to 37.7, all on the
    white line and the oscillations; 30 of 34 results carried ``glitches_flagged``."""
    if not flagged or n_scans >= int(params["deglitch"]["min_scans_for_cross_scan"]):
        return None
    return (f"With {n_scans} scan{'' if n_scans == 1 else 's'}, the glitch check compares neighbouring points and also "
            "flags real features such as the white line and oscillations; these "
            f"{flagged} flag{'' if flagged == 1 else 's'} are not by themselves evidence of glitches.")


def _csv(path: Path, header: Sequence[str], cols: Sequence, np) -> None:
    lines = ["# DRAFT protocol isaac.xas.v0 (draft_unreviewed) - review material, not an official value", ",".join(header)]
    for row in zip(*cols):
        lines.append(",".join("" if (v is None or not np.isfinite(v)) else (f"{v:.6f}" if i == 0 else f"{v:.8g}") for i, v in enumerate(row)))
    _write(path, ("\n".join(lines) + "\n").encode("utf-8"))


def _scan_attempts(tables, choice, np) -> list[tuple]:
    """``(entry, table, arrays | None, skip code | None)`` per readable scan under ``choice``."""
    out = []
    for entry, table in tables:
        try:
            out.append((entry, table, C.scan_arrays(table, choice, np), None))
        except C.StepError as exc:
            out.append((entry, table, None, exc.code))
    return out


FALLBACK_FLAG = "channel_fallback_transmission_not_positive"


def _fallback_from_transmission(attempts, choice, tables, role: str, sel, params: Mapping):
    """The next alternative channel when TRANSMISSION fails the whole group, else ``None``.

    Only when transmission was chosen and, in EVERY scan that has its columns, fewer than
    ``merge.min_points`` of its points are finite because some are not (I0 or I1 not positive).
    Measured on a real BL4-3 beamtime: dilute standards in sucrose pellets are named as
    standards (role ``reference``, so transmission first) but were measured in fluorescence;
    I1 is negative at every point. Transmission that works in any scan is kept. Like the
    channel choice itself, the first readable scan that forms the alternative supplies it.
    The fallback is never silent: flag :data:`FALLBACK_FLAG`, ``basis.fallback_from`` with a
    plain statement of what was tried and why it was abandoned, and QC at least ``warn``.
    """
    if choice.mode != MODE_TRANSMISSION:
        return None
    min_points = int(params["merge"]["min_points"])
    tried = [(entry, sa["diagnostics"]) for entry, _, sa, _ in attempts if sa is not None]
    if not tried or any(d["points_read"] - d["nonfinite_dropped"] >= min_points or not d["nonfinite_dropped"] for _, d in tried):
        return None
    found = None
    for k, (_, table) in enumerate(tables):
        alt = choose_channels(table, params=params, role=role, bl15_selection=sel, exclude_modes=(MODE_TRANSMISSION,))
        if _formed(alt):
            found = (k, alt)
            break
    if found is None:
        return None
    k, alt = found
    if k:
        alt.basis["chosen_from_scan_position"] = k
        alt.flags.append("channel_from_a_later_scan")
    read = sum(d["points_read"] for _, d in tried)
    dropped = sum(d["nonfinite_dropped"] for _, d in tried)
    alt.basis["fallback_from"] = {
        "mode": MODE_TRANSMISSION,
        "signal_name": choice.signal_name,
        "rule": choice.basis.get("rule"),
        "reason_code": "transmission_not_positive",
        "min_points": min_points,
        "scans": [{"source_id": e.get("source_id"), "points_read": d["points_read"], "nonfinite_dropped": d["nonfinite_dropped"]} for e, d in tried],
        "statement": (
            f"Transmission {choice.signal_name} was tried first (a {role} group takes transmission first) and abandoned: "
            f"I0 or I1 is not positive, so {dropped} of its {read} points were not finite and every one of the "
            f"{len(tried)} scans kept fewer than {min_points}. Fluorescence {alt.signal_name} was used instead; "
            "a person confirms this channel."
        ),
    }
    alt.flags.append(FALLBACK_FLAG)
    return alt


REFERENCE_FALLBACK_FLAG = "channel_fallback_reference_channel"
#: v1 (review, cycle 3): reached only by a run NAMED a foil or calibration (:func:`_names_a_foil`) or an
#: alignment group; v0 was reached by every ``reference`` group, which a ``std``/``standard``/``ref`` token
#: makes a compound standard too (``05_SYN_CoO_std_005`` with a dead I1 was switched to ln(I0/I2)).
REFERENCE_CHANNEL_RULE_ID = "isaac.xas.reference_channel_fallback.v1"
#: Flag on a choice whose reference channel was tried and was not usable either (the choice is unchanged).
REFERENCE_TRIED_FLAG = "reference_channel_tried_not_usable"


def _positive(table, col: str | None) -> bool:
    """True when ``col`` is a column of ``table`` and every one of its values is a positive number."""
    if not col or not table.has(col):
        return False
    vals = table.columns[col]
    return bool(vals) and all(v == v and v > 0 for v in vals)


def _screen(attempts, params: Mapping, np, xafs) -> dict | None:
    """:func:`core.edge_checks` on a quick merge of the usable scans of ``attempts`` (mean on the widest scan's
    grid, as the merge does; no calibration shift: the checks do not depend on it). ``None`` when no curve can
    be normalised; else ``{"failed": {reason: finding}, "e0_eV", "edge_step"}``."""
    scans = [sa for _, _, sa, code in attempts if sa is not None and code is None and C.unusable_reason(sa) is None]
    if not scans:
        return None
    try:
        grid, _ = C.common_grid(scans, np)
    except C.StepError:
        return None
    M = C.interpolate(scans, grid, np)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(M, axis=0)
    ok = np.isfinite(mean)
    if int(ok.sum()) < int(params["merge"]["min_points"]):
        return None
    try:
        nm = C.normalize(grid[ok], mean[ok], params, np, xafs)
    except C.StepError:
        return None
    return {"failed": C.edge_checks(grid[ok], mean[ok], nm, np), "e0_eV": nm["e0_eV"], "edge_step": nm["edge_step"]}


def _foil_token(tok: str) -> bool:
    """A token that names a foil or a calibration: starting ``foil``/``calib`` (as grouping's role rule) or
    ending ``foil`` (``Tifoil``, ``Cufoil``). Case-folded."""
    return tok.startswith(("foil", "calib")) or tok.endswith("foil")


def _names_a_foil(stems: Sequence[str]) -> bool:
    """True when a run name has a foil or calibration token (:func:`_foil_token`)."""
    return any(_foil_token(t.casefold()) for stem in stems for t in _TOKEN.split(str(stem)) if t)


def _names_foil_on(stems: Sequence[str], column: str) -> bool:
    """True when a run name has a ``foil`` token and a token that IS ``column`` (``..._foil_I2_120``)."""
    for stem in stems:
        toks = [t.casefold() for t in _TOKEN.split(str(stem)) if t]
        if any(_foil_token(t) for t in toks) and column.casefold() in toks:
            return True
    return False


def _reference_channel_fallback(attempts, choice, tables, role: str, stems: Sequence[str], ctx: _Ctx):
    """The reference channel when TRANSMISSION ln(I0/I1) fails the edge checks for a foil measured on I2;
    else ``None``. Never silent; never for a sample.

    Measured on a real BL4-3 beamtime: a Ti foil run said to be on I2 (a Ti foil said to be on I2) had I1 at -3.6 to
    26 counts, so ln(I0/I1) was a falling noisy trace with no edge (step 2.4 times the pre-edge scatter) that
    QC only warned about. There ln(I1/I2) is not tried (I1 is not a positive intensity) and ln(I0/I2) is
    REFUSED by the checks: that I2 rises about 270 times across the edge, as a fluorescence or yield signal
    does, so ln(I0/I2) falls (post-edge level -0.68 from the pre-edge line, -1.02 at E0); the group keeps
    ln(I0/I1) and fails, with what was tried recorded. Which signal that I2 is, is the scientist's question.
    Only when ALL hold (:data:`REFERENCE_CHANNEL_RULE_ID`): the group is an alignment group, or a reference
    group a run name says is a foil or calibration (:func:`_names_a_foil`: a compound standard is a reference
    by its ``std`` token, and its I2 is not a reference foil's); ln(I0/I1) was chosen; a
    reference-after column (``channels.reference_after_reference``, I2) is a positive intensity in every
    scan; and EITHER a run name says the foil is on it (a ``foil`` token and an ``I2`` token) OR I1 is not a
    positive intensity in some scan. Candidates, in order: ln(I1/I2) (the protocol's reference pair), only
    when I1 is a positive intensity in every scan; else ln(I0/I2) (I1 cannot be read, so the beam is read
    after it on I2). The first that passes the checks is used, flagged :data:`REFERENCE_FALLBACK_FLAG`, with
    ``basis.fallback_from`` naming what failed and every candidate tried, and QC at least ``warn``. When none
    passes, the choice is unchanged (it fails on its own) and the candidates tried are recorded on it.
    """
    if choice.mode != MODE_TRANSMISSION or not (role == "alignment" or (role == "reference" and _names_a_foil(stems))):
        return None
    np, params = ctx.np, ctx.params
    readable = [t for _, t in tables if t.has(choice.i0) and t.has(choice.transmission_after)]
    ref = next((c for c in params["channels"]["reference_after_reference"]
                if readable and all(_positive(t, c) for t in readable)), None)
    if ref is None:
        return None
    i1_positive = all(_positive(t, choice.transmission_after) for t in readable)
    if not (_names_foil_on(stems, ref) or not i1_positive):
        return None
    first = _screen(attempts, params, np, ctx.xafs)
    if first is None or not first["failed"]:
        return None
    tried, found = [], None
    for num in (choice.transmission_after, choice.i0):
        alt = ChannelChoice(energy=choice.energy, mode=MODE_TRANSMISSION, i0=num, transmission_after=ref,
                            reference_pair=choice.reference_pair, basis=dict(choice.basis), alternatives=list(choice.alternatives),
                            flags=list(choice.flags))
        row = {"signal_name": alt.signal_name}
        if num == choice.transmission_after and not i1_positive:
            row.update(outcome="not_tried", reason=f"{num} is not a positive intensity in every scan")
        elif num == choice.i0 and i1_positive:
            row.update(outcome="not_tried", reason=f"{choice.transmission_after} can be read, so the reference pair is ln({choice.transmission_after}/{ref})")
        elif found is not None:
            row.update(outcome="not_tried", reason=f"{found.signal_name} passed first")
        else:
            got = _screen(_scan_attempts(tables, alt, np), params, np, ctx.xafs)
            if got is None:
                row.update(outcome="failed", reason="no curve could be normalised")
            elif got["failed"]:
                row.update(outcome="failed", failed_checks=sorted(got["failed"]),
                           reason=" ".join(f["statement"] for f in got["failed"].values()))
            else:
                row.update(outcome="used", e0_eV=got["e0_eV"], edge_step=got["edge_step"])
                found = alt
        tried.append(row)
    failed = sorted(first["failed"])
    said_failed = "; ".join(first["failed"][k]["statement"] for k in failed)
    if found is None:
        choice.basis["reference_channel_tried"] = {"fallback_rule": REFERENCE_CHANNEL_RULE_ID, "failed_checks": failed, "tried": tried, "statement": (
            f"Transmission {choice.signal_name} failed the edge checks ({', '.join(failed)}), and the reference channel "
            f"was tried and was not usable either: {'; '.join(t['signal_name'] + ' ' + t['outcome'] + ' (' + t['reason'] + ')' for t in tried)}.")}
        choice.flags.append(REFERENCE_TRIED_FLAG)
        return None
    found.basis["fallback_from"] = {
        "mode": MODE_TRANSMISSION,
        "signal_name": choice.signal_name,
        "rule": choice.basis.get("rule"),
        "reason_code": "transmission_failed_edge_checks",
        "fallback_rule": REFERENCE_CHANNEL_RULE_ID,
        "failed_checks": failed,
        "tried": tried,
        "statement": (
            f"Transmission {choice.signal_name} was tried first and failed the edge checks ({', '.join(failed)}): {said_failed} "
            f"This {role} group's reference channel {found.signal_name} has an edge "
            f"({ref} is a positive intensity in every scan"
            + (f"; {choice.transmission_after} is not" if not i1_positive else "")
            + (f"; the name says the foil is on {ref}" if _names_foil_on(stems, ref) else "")
            + f"), so {found.signal_name} was used instead; a person confirms this channel."
        ),
    }
    found.flags.append(REFERENCE_FALLBACK_FLAG)
    return found


#: Review flag (and the merge step's flag): a scan used in the merge ends early.
TRUNCATED_FLAG = "scan_range_truncated"


def _truncation_statement(ginfo: Mapping, scans_data: Sequence[Mapping], pos_sid: Sequence[str]) -> str | None:
    """One plain sentence when the merge kept a scan that spans less than ``truncated_fraction`` of the
    grid (``None`` otherwise). Measured on a real BL6-2c beamtime: the last scan of a run, aborted after
    98 of 225 points, was merged with the other 11 and QC said nothing (``scans_used`` 12 of 12)."""
    pos = list(ginfo.get("truncated_scan_positions") or ())
    if not pos:
        return None
    g0, g1 = ginfo["grid_eV"]
    each = ", ".join(
        f"{pos_sid[i]} covers {float(scans_data[i]['energy'][0]):.3f}-{float(scans_data[i]['energy'][-1]):.3f} eV" for i in pos[:10]
    ) + (f" and {len(pos) - 10} more" if len(pos) > 10 else "")
    overlap = ginfo.get("all_scans_overlap_eV")
    common = f"all {len(scans_data)} overlap only {overlap[0]:.3f}-{overlap[1]:.3f} eV" if overlap else "no energy is covered by every scan"
    n, k = len(scans_data), len(pos)
    return (
        f"{k} of {n} scans used {'ends' if k == 1 else 'end'} early (under {ginfo['truncated_fraction']:.0%} of the merge grid "
        f"{g0:.3f}-{g1:.3f} eV): {each}. Each scan is merged only where it has data, so outside its range the merged "
        f"curve averages fewer than {n} scans ({common}). A person checks whether {'it belongs' if k == 1 else 'they belong'} in the merge."
    )


def _file_name(entry: Mapping) -> str:
    """A used scan as a person knows it: its file name (the source id when no path is recorded)."""
    return PurePosixPath(str(entry.get("relative_path") or entry.get("source_id"))).name


def _scan_name(entry: Mapping) -> str:
    return f"{entry.get('source_id')} (scan {entry['scan']})" if entry.get("scan") is not None else str(entry.get("source_id"))


def _scans_phrase(scans: Sequence[int]) -> str:
    """[1, 3, 4, 5, 8] -> "1, 3-5, 8"."""
    nums = sorted({int(n) for n in scans})
    out: list[str] = []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ", ".join(out)


def _no_usable_scan_statement(inputs: Sequence[Mapping], too_few: Sequence[int], *, signal: str | None = None) -> str | None:
    """c10-m: one plain sentence when NO scan could be used because scans have too few points (``None`` when none
    did): "The only scan has 2 usable points; at least 5 are needed". Scans skipped for other reasons are counted.
    c11-a: when no scan has too few points but every one's signal is zero at every point, that is said instead."""
    if not too_few:
        zero = sum(1 for i in inputs if i.get("skip_reason") == C.SIGNAL_ALL_ZERO)
        if not zero or zero != len(inputs):
            return None
        named = f"signal ({signal})" if signal else "signal"
        if zero == 1:
            return f"The only scan's {named} is zero at every point, so there is no curve to process."
        every = "both scans" if zero == 2 else f"all {zero} scans"
        return f"No scan could be used: the {named} is zero at every point in {every}, so there is no curve to process."
    need = f"at least {C.MIN_SCAN_POINTS} are needed, so there is no curve to process."
    if len(inputs) == 1:
        return f"The only scan has {too_few[0]} usable point{'' if too_few[0] == 1 else 's'}; {need}"
    k = len(too_few)
    other = len(inputs) - k
    return (f"No scan could be used: {k} {'has' if k == 1 else 'have'} too few usable points ({', '.join(map(str, too_few))}); "
            + (f"{other} {'was' if other == 1 else 'were'} skipped for other reasons (see inputs); " if other else "")
            + need)


def _raw_signal(choice) -> str | None:
    """The column(s) whose values ``signal_all_zero`` tests (core.scan_arrays' raw signal), as a reader names them."""
    if choice.mode == MODE_TRANSMISSION:
        return choice.transmission_after
    return "+".join(choice.signal_columns) or None


def _all_zero_statement(inputs: Sequence[Mapping], signal: str | None, used: int) -> str | None:
    """c11-a: one plain sentence when scans were left out because their signal is zero at every point (``None``
    otherwise): how many of the listed scans were used, which were not (by file name), and that the curve merges the
    others. In ``qc.statements``, so in ``qc.json``: only a result with such a scan has a new id."""
    zero = [i for i in inputs if i.get("skip_reason") == C.SIGNAL_ALL_ZERO]
    if not zero:
        return None
    k = len(zero)
    names = ", ".join(PurePosixPath(str(i.get("relative_path") or i.get("source_id"))).name for i in zero[:10])
    names += f" and {k - 10} more" if k > 10 else ""
    named = f"signal ({signal})" if signal else "signal"
    return (f"{used} of {len(inputs)} listed scans were used. {k} {'was' if k == 1 else 'were'} left out because "
            f"{'its' if k == 1 else 'their'} {named} is zero at every point: {names}; the curve merges the other "
            f"{used}. A person checks why {'that scan' if k == 1 else 'those scans'} recorded no signal.")


#: c11-r: the review flag of a result that merged a scan whose signal is exactly zero at points where another merged
#: scan's is not (the beam lost part-way, or a detector that stopped counting): it is merged unchanged and said.
ZERO_SIGNAL_POINTS_FLAG = "merged_scan_has_zero_signal_points"


def _zero_signal_points_statement(used_entries: Sequence[Mapping], scans_data: Sequence[Mapping], signal: str | None,
                                  np) -> str | None:
    """c11-r: one plain statement naming each MERGED scan whose counts STOP: its signal is exactly zero from some point
    to the scan's last point (a run of at least two points, :func:`_zero_runs`), where another merged scan's signal is
    not zero (at the other scan's nearest point within its energy range); ``None`` otherwise. c12-cal: zeros that do
    not reach the end (the counts come back) are counted apart (:func:`_isolated_zero_points_statement`), never said
    as a lost beam. Threshold-free and descriptive only: nothing is skipped or changed for it (whether such a scan
    belongs in the merge is the scientist's call, docs/xas-processing-protocol-v0.md). Said in the result, NOT in
    qc.json (hashed into the run id), so no result id moves."""
    parts = []
    for entry, sa, z in _zero_scans(used_entries, scans_data, np):
        trail, others = z["trailing"], z["n"] - z["trailing"]
        if trail < 2:
            continue
        d = sa["diagnostics"]
        name = PurePosixPath(str(entry.get("relative_path") or entry.get("source_id"))).name
        named = f"signal ({signal})" if signal else "signal"
        extra = f", and at {others} other point{'' if others == 1 else 's'}" if others else ""
        parts.append(f"{name}'s {named} is zero at {d.get('signal_zero_points', z['n'])} of "
                     f"{d.get('points_read', z['size'])} points (from {z['trailing_from_eV']:.1f} eV on{extra}); it is "
                     "merged unchanged.")
    if not parts:
        return None
    more = f" {len(parts) - 10} more merged scan(s) are the same." if len(parts) > 10 else ""
    return " ".join(parts[:10]) + more + " A person checks whether the beam was lost."


def _zero_scans(used_entries: Sequence[Mapping], scans_data: Sequence[Mapping], np) -> list[tuple[Mapping, Mapping, dict]]:
    """Each merged scan whose signal is exactly zero at points where another merged scan's is not: ``(entry, scan,
    {n, size, trailing, trailing_from_eV, longest})`` — ``trailing`` is the length of the run of zeros that ends at
    the scan's last point (0 when the last point is not zero), ``longest`` its longest run of consecutive zeros."""
    out = []
    for k, (entry, sa) in enumerate(zip(used_entries, scans_data)):
        zero = sa.get("signal_zero")
        if zero is None or not zero.any():
            continue
        at = sa["energy"][zero]
        elsewhere = False
        for j, other in enumerate(scans_data):
            e_o, z_o = other["energy"], other.get("signal_zero")
            if j == k or not e_o.size or z_o is None:
                continue
            inside = at[(at >= e_o[0]) & (at <= e_o[-1])]
            if not inside.size:
                continue
            right = np.clip(np.searchsorted(e_o, inside), 0, e_o.size - 1)
            left = np.clip(right - 1, 0, e_o.size - 1)
            nearest = np.where(np.abs(e_o[left] - inside) <= np.abs(e_o[right] - inside), left, right)
            if (~z_o[nearest]).any():
                elsewhere = True
                break
        if not elsewhere:
            continue
        where = np.flatnonzero(zero)
        runs = np.split(where, np.flatnonzero(np.diff(where) != 1) + 1)
        last = runs[-1]
        trailing = int(last.size) if last[-1] == zero.size - 1 else 0
        out.append((entry, sa, {"n": int(where.size), "size": int(zero.size), "trailing": trailing,
                                "trailing_from_eV": float(sa["energy"][last[0]]) if trailing else None,
                                "longest": int(max(r.size for r in runs))}))
    return out


def _isolated_zero_points_statement(used_entries: Sequence[Mapping], scans_data: Sequence[Mapping], signal: str | None,
                                    np) -> str | None:
    """c12-cal: ONE count line for the merged scans whose signal is exactly zero at points where another's is not but
    whose counts come back (the zeros do not run to the scan's end): single-point dropouts, said like glitches, with
    no beam-loss wording and no review flag. Measured on a real BL15-2 beamtime: 441 merged scans of 70 groups had such
    points, 414 at only 1-5 points, I0 positive at all of them; the one scan whose counts stopped (zero at 204 of 226
    points to its end) was buried among them. ``None`` when there is none. Said after the run id (no id moves)."""
    rows = [(z["n"] - (z["trailing"] if z["trailing"] >= 2 else 0), z["longest"] if z["trailing"] < 2 else None)
            for _, _, z in _zero_scans(used_entries, scans_data, np)]
    rows = [(n, lng) for n, lng in rows if n]
    if not rows:
        return None
    named = f"signal ({signal})" if signal else "signal"
    k, total = len(rows), sum(n for n, _ in rows)
    longest = max((lng for _, lng in rows if lng is not None), default=None)
    return (f"{k} merged scan{'' if k == 1 else 's'} {'has' if k == 1 else 'have'} isolated points where the {named} "
            f"is exactly zero while another scan's is not ({total} point{'' if total == 1 else 's'} in all"
            + (f", at most {longest} in a row" if longest else "")
            + "); the counts come back after each, so they read as detector dropouts, like glitches. They are merged "
            "unchanged.")


def _one_scan_ends_statement(grid, n_per_point, used_entries: Sequence[Mapping], M, n_scans: int, np) -> str | None:
    """c12-cal: one plain sentence when the merged curve's first or last points come from ONE scan alone, whose
    signal is zero there, although the group merges several (``None`` otherwise): which scan and which energies. Measured on a real BL15-2 beamtime: a 7-scan group's last point (11497.1 eV) came only from the scan whose
    counts had stopped, so the merged value there was 0 and the normalised curve dropped. The grid is unchanged
    (trimming it would change every such curve and its id); said after the run id. ``grid``, ``n_per_point`` and
    ``M`` (scans x grid) are the merged curve's own points."""
    if n_scans < 2 or not n_per_point.size:
        return None
    parts = []
    size = int(n_per_point.size)
    for side, order in (("first", range(size)), ("last", range(size - 1, -1, -1))):
        alone = []
        for i in order:
            if int(n_per_point[i]) != 1:
                break
            alone.append(i)
        if not alone or len(alone) == size:
            continue
        who = {int(np.flatnonzero(np.isfinite(M[:, i]))[0]) for i in alone}
        if len(who) != 1:
            continue
        p = who.pop()
        name = PurePosixPath(str(used_entries[p].get("relative_path") or used_entries[p].get("source_id"))).name
        lo, hi = float(grid[min(alone)]), float(grid[max(alone)])
        n = len(alone)
        what = f"{side} point ({lo:.1f} eV) comes" if n == 1 else f"{side} {n} points ({lo:.1f}-{hi:.1f} eV) come"
        if not bool(np.all(M[p, alone] == 0)):
            # measured: on 52 of 78 groups the widest scan reaches a fraction of an eV past the others; one real scan
            # alone at one end changes nothing a person can see, so only a lone ZERO there is said
            continue
        parts.append(f"The merged curve's {what} from {name} alone, whose signal is zero there, so the merged value is 0.")
    if not parts:
        return None
    return " ".join(parts) + " Everywhere else at least 2 scans are averaged; read the curve's ends with that in mind."


def _skipped_scans_statement(inputs: Sequence[Mapping], choice, used: int) -> str | None:
    """One plain sentence when readable scans of the group were left out because they lack the chosen
    columns (``None`` otherwise): how many of the listed scans were used, which were not, and why. Added to
    ``qc.statements`` AFTER the run id is fixed (``qc.json`` is hashed into it), so no result id moves."""
    lacking = [i for i in inputs if i.get("skip_reason") == "scan_lacks_chosen_columns"]
    if not lacking:
        return None
    k = len(lacking)
    names = ", ".join(_scan_name(i) for i in lacking[:10]) + (f" and {k - 10} more" if k > 10 else "")
    other = len(inputs) - used - k
    return (
        f"{used} of {len(inputs)} listed scans were used. {k} {'was' if k == 1 else 'were'} left out because "
        f"{'it lacks' if k == 1 else 'they lack'} the columns chosen for this group (energy {choice.energy}, signal "
        f"{choice.signal_name}): {names}. {'It may be a motor or alignment scan' if k == 1 else 'They may be motor or alignment scans'} or another "
        f"kind of measurement; a person confirms {'it does' if k == 1 else 'they do'} not belong in this record."
        + (f" {other} more {'scan was' if other == 1 else 'scans were'} skipped for other reasons (see inputs)." if other > 0 else "")
    )


def _athena_coverage(entry: Mapping, stems: Sequence[str], used_entries: Sequence[Mapping],
                     stem_of: Mapping[str, str]) -> dict | None:
    """Which of a MERGED group's runs the scientist's Athena curve covers (c8-a), ``None`` for a one-run group.

    A run's scans are numbered from 1 in each run (``<stem>_A.001``), so in a group of several runs "scans 1-2" says
    nothing without the run. The runs are the group's stems its name names (``athena._match_kind``; for a set of
    per-scan groups, each member's label). ``partial``: it covers fewer runs than the group holds. ``scans``: the
    covered runs' scan numbers the project states (``None`` when it states none)."""
    group_runs = list(dict.fromkeys(s for s in stems if s))
    if len(group_runs) < 2:
        return None
    members = entry.get("per_scan_set") if entry.get("_match_kind") == "per_scan_set" else None
    names = [A.normalise_name(n) for n in members.get("labels") or ()] if members else list(entry.get("names") or ())
    runs = [s for s in group_runs if any(A._match_kind([n], A.normalise_name(s)) for n in names)]
    if not runs:
        return None
    sel = [int(n) for n in members["scans"]] if members and members.get("scans") else A.scan_selection(str(entry.get("label") or ""), runs)
    return {"runs": runs, "group_runs": group_runs, "scans": list(sel) if sel else None,
            "isaac_scans_merged": len(used_entries),
            "isaac_scans_of_these_runs": sum(1 for e in used_entries if stem_of.get(e.get("source_id")) in runs),
            "partial": len(runs) < len(group_runs)}


def _set_scans(entry: Mapping) -> list[int] | None:
    """The scan numbers a set of per-scan Athena groups names (one each), else ``None``."""
    members = entry.get("per_scan_set") if entry.get("_match_kind") == "per_scan_set" else None
    return [int(n) for n in members["scans"]] if members and members.get("scans") else None


def _athena_scans_used(entry: Mapping, stems: Sequence[str], isaac_counts: tuple[int, int] | None,
                       coverage: Mapping | None = None, isaac_scans: Sequence[int] | None = None, *,
                       listed_scans: Sequence[int] | None = None, numbered_from_file_names: bool = False) -> dict:
    """Which scans the scientist's Athena curve used, as far as the project says: ``basis`` is ``per_scan_set``
    (the member groups name one scan each), ``label`` (the Athena group's label names a selection) or
    ``not_stated`` (an Athena project does not list the scan files it merged). In a group of several runs
    (``coverage``, :func:`_athena_coverage`) the statement names the run(s) the curve covers, and says so plainly
    when that is only some of the group's runs."""
    members = entry.get("per_scan_set") if entry.get("_match_kind") == "per_scan_set" else None
    label = str(entry.get("label") or "")
    ours = f" ISAAC's own curve for this group merges {isaac_counts[0]} of {isaac_counts[1]} listed scans." if isaac_counts else ""
    of_run = f" of run{'s' if coverage and len(coverage['runs']) > 1 else ''} {', '.join(coverage['runs'])}" if coverage else ""
    part = ""
    if coverage and coverage["partial"]:
        k = len(coverage["scans"]) if coverage["scans"] else None
        n_runs = len(coverage["runs"])
        part = (f" It covers only run{'s' if n_runs > 1 else ''} {', '.join(coverage['runs'])} of the "
                f"{len(coverage['group_runs'])} runs merged in this group ({', '.join(coverage['group_runs'])})"
                + (f": {k} of the {coverage['isaac_scans_merged']} scans ISAAC merged" if k else
                   f": at most {coverage['isaac_scans_of_these_runs']} of the {coverage['isaac_scans_merged']} scans ISAAC merged")
                + ", so it is not preferred for the record (ISAAC's curve merges every run of the group); the scientist "
                "can still approve it, knowing it describes only those scans.")

    def subset(scans: Sequence[int]) -> str:
        # c10-m: in a ONE-run group, a curve of only some of the scans ISAAC merged says so (a merged group's says
        # which runs it covers, above)
        if coverage is not None:
            return ""
        if not isaac_scans:
            # c11-r: some scan's number is not known (it states none, or the file names do not say; process_group then
            # passes none): which scans of ISAAC's merge these are is not said either way
            return (" The run's scans do not all state a scan number, so whether these are the scans ISAAC merged is "
                    "not known.") if isaac_counts else ""
        if set(scans) == set(isaac_scans):
            return ""
        how = (" (the run states no scan index: each scan's number is read from its file name)"
               if numbered_from_file_names else "")
        unlisted = sorted(set(scans) - set(listed_scans)) if listed_scans else []
        if unlisted:
            # c11-a: a number the run does not have is not "a scan ISAAC did not merge": which scans it means is unknown
            return (f" It names scan{'s' if len(unlisted) > 1 else ''} {_scans_phrase(unlisted)}, which the run's "
                    f"{len(listed_scans)} listed scans do not include{how}, so which of the scans ISAAC merged it used is "
                    "not known: its E0 and curve describe its own scans, not necessarily ISAAC's merge.")
        extra = sorted(set(scans) - set(isaac_scans))
        if extra:
            # c10-r: a scan ISAAC did not merge (it skipped it) makes it ANOTHER set, never "only" part of the merge
            left = sorted(set(isaac_scans) - set(scans))
            return (f" It is a different set of scans from the {len(isaac_scans)} ISAAC merged: it includes "
                    f"scan{'s' if len(extra) > 1 else ''} {_scans_phrase(extra)}, which ISAAC did not merge"
                    + (f", and leaves out scan{'s' if len(left) > 1 else ''} {_scans_phrase(left)}" if left else "")
                    + f"{how}: its E0 and curve describe its own scans, not ISAAC's merge.")
        return (f" It covers only scan{'s' if len(scans) > 1 else ''} {_scans_phrase(scans)} of the {len(isaac_scans)} "
                f"scans ISAAC merged{how}: its E0 and curve describe those scans, not the full merge.")

    if members and members.get("scans"):
        scans = [int(n) for n in members["scans"]]
        said = (f"The scientist's curve is ISAAC's mean of {len(scans)} per-scan Athena groups, one each for scans "
                f"{_scans_phrase(scans)}{of_run} (read from their labels).{ours}{part}{subset(scans)}")
        return {"basis": "per_scan_set", "scans": scans, "statement": said}
    sel = A.scan_selection(label, stems)
    if sel:
        said = (f"The scientist's Athena group '{label}' names scans {_scans_phrase(sel)}{of_run} in its label. An Athena "
                f"project does not list the scan files it merged, so this is read from the label, not confirmed.{ours}{part}"
                f"{subset(sel)}")
        return {"basis": "label", "scans": list(sel), "statement": said}
    made_from = PurePosixPath(str(entry.get("filename") or "").replace("\\", "/")).name
    # c12-cal: Athena writes its own null marker when a group names no source file: said in words, never printed
    unnamed = not made_from or made_from == A.ATHENA_NULL_MARKER
    said = (f"The project does not say which scans the scientist's curve used: its Athena label '{label}' names no scan"
            + (", though Athena marks the group as a merge" if entry.get("is_merge") else "")
            + (", and the project does not name its source file" if unnamed else
               f", and it records the group as made from the file '{made_from}'" if made_from.casefold() != label.casefold() else "")
            + (f"; its name names run{'s' if len(coverage['runs']) > 1 else ''} {', '.join(coverage['runs'])}" if coverage else "")
            + f".{ours}{part} Ask the scientist which scans went into it.")
    return {"basis": "not_stated", "scans": None, "statement": said}


def _versions_question_text(versions: Sequence[Mapping]) -> str:
    """The which-version question, in words. c12-cal: versions that are the SAME raw data (one curve copied into
    several projects) normalised differently are said as such, naming the projects and the parameters that differ
    (measured on a real BL15-2 beamtime: one scan file in three projects read as "3 different Athena versions").
    Byte-identical curves with the same parameters are already one version (athena.match_with_versions)."""
    n = len(versions)
    ask = " Which one is the result of record? None is selected until you choose."
    hashes = {str(v.get("data_hash") or "") for v in versions}
    sets = any(v.get("_match_kind") == "per_scan_set" or v.get("per_scan_set") for v in versions)
    if sets or len(hashes) != 1 or "" in hashes:  # a set of per-scan groups is named by its members, not one curve
        return f"{n} different Athena versions of this measurement exist." + ask
    projects = sorted({PurePosixPath(str(v.get("prj_relative_path") or "")).name for v in versions})
    params = [v.get("params") or {} for v in versions]
    differ = sorted(k for k in set().union(*params) if len({json.dumps(p.get(k), default=str) for p in params}) > 1)
    where = (f"in {len(projects)} Athena projects ({', '.join(projects[:5])}{', …' if len(projects) > 5 else ''})"
             if len(projects) > 1 else f"{n} times in {projects[0]}")
    return (f"The same data (one curve, byte for byte) is kept {where}, normalised {n} different ways"
            + (f" (the parameters that differ: {', '.join(differ[:8])})" if differ else "") + "." + ask)


def _post_edge_range(resolved: Mapping) -> str | None:
    lo, hi = resolved.get("norm1"), resolved.get("norm2")
    return f"norm1 {lo:g} to norm2 {hi:g} eV above E0" if lo is not None and hi is not None else None


def process_group(group: Mapping, ctx: _Ctx, athena_entry: Mapping | None = None, athena_versions: Sequence[Mapping] | None = None) -> list[dict]:
    np, params = ctx.np, ctx.params
    res = _base(group, "isaac_protocol")
    scans, stems, sel = group_scans(group, ctx.runs_by_key)
    if not scans:
        return [_not_applicable(res, B.NA_NO_SCANS, "the group lists no scan", data_states(group, ctx.runs_by_key))]
    tables = []
    for s in scans:
        entry = {"source_id": s.get("source_id"), "scan": s.get("scan_index"), "relative_path": s.get("relative_path"), "channel": None, "used": False}
        res["inputs"].append(entry)
        path = _resolve_source(ctx.root, s.get("relative_path") or "") if ctx.root else None
        if path is None or not path.is_file():
            entry["skip_reason"] = "source_file_not_found"
            continue
        expected = (ctx.sources.get(s.get("source_id") or "") or {}).get("content_sha256")
        if expected and sha256_file(path) != expected:
            entry["skip_reason"] = "source_hash_mismatch"
            continue
        table = ctx.scan_reader(path)
        entry["format"] = table.format_id
        entry["reader_notes"] = table.notes
        if table.error:
            entry["skip_reason"] = f"unreadable:{table.error}"
            continue
        tables.append((entry, table))
    if not tables:
        causes = sorted({e.get("skip_reason") or "?" for e in res["inputs"]})
        return [_fail(res, "no_readable_scan", ";".join(causes))]

    role = group.get("role", "sample")
    choice = choose_channels(tables[0][1], params=params, role=role, bl15_selection=sel)
    if not _formed(choice):
        # THE FIRST SCAN DOES NOT DECIDE ALONE. Every readable scan is asked; the first one
        # that forms a channel supplies the group's choice (scans without those columns are
        # then skipped, each with its reason, by the merge below). Only when NO scan forms one:
        # a scan whose signal-side candidate columns are PRESENT but not live is a real QC
        # failure (``signal_channel_dead``); otherwise the protocol does not apply.
        first = choice
        choices = [first] + [choose_channels(t, params=params, role=role, bl15_selection=sel) for _, t in tables[1:]]
        found = next(((k, c) for k, c in enumerate(choices) if _formed(c)), None)
        if found is None:
            res["channel_choice"] = first.to_state()
            dead = {}
            for (entry, table), c in zip(tables, choices):
                cols = dead_candidates(table, params=params) if c.energy is not None else []
                if cols:
                    dead[entry.get("relative_path")] = cols
            if dead:
                res["review_flags"] += first.flags
                cols = sorted({c for d in dead.values() for c in d})
                return [_fail(res, "signal_channel_dead", f"{len(dead)} of {len(tables)} readable scans have candidate columns that are present but not live: {','.join(cols)}")]
            return [_not_applicable(res, B.NA_NO_XAS_CHANNEL, ",".join(first.flags), data_states(group, ctx.runs_by_key, res["inputs"], tables[0][1]))]
        k, choice = found
        choice.basis["chosen_from_scan_position"] = k
        choice.flags.append("channel_from_a_later_scan")
    attempts = _scan_attempts(tables, choice, np)
    fallback = _fallback_from_transmission(attempts, choice, tables, role, sel, params)
    fallback_flag = FALLBACK_FLAG
    if fallback is None:
        fallback = _reference_channel_fallback(attempts, choice, tables, role, stems, ctx)
        fallback_flag = REFERENCE_FALLBACK_FLAG
    if fallback is not None:
        choice = fallback
        attempts = _scan_attempts(tables, choice, np)
    res["channel_choice"] = choice.to_state()
    res["review_flags"] += choice.flags
    scans_data, used_entries, headers = [], [], []
    too_few: list[int] = []  # the usable points of each scan skipped as too_few_points (said if no scan is left)
    for entry, table, sa, code in attempts:
        code = code or C.unusable_reason(sa)
        if code:
            entry["skip_reason"] = code
            if code == "too_few_points" and sa is not None:
                too_few.append(int(sa["energy"].size))
            if code in (C.SIGNAL_NOT_FINITE, C.SIGNAL_ALL_ZERO):
                entry["diagnostics"] = sa["diagnostics"]  # points_read, nonfinite_dropped / signal_all_zero: why
            continue
        entry.update(used=True, channel=choice.signal_name, diagnostics=sa["diagnostics"])
        scans_data.append(sa)
        used_entries.append(entry)
        headers.extend(table.header_lines)
    if not scans_data:
        causes = sorted({e.get("skip_reason") or "?" for e in res["inputs"]})
        nonfinite = [e["diagnostics"] for e in res["inputs"] if e.get("skip_reason") == C.SIGNAL_NOT_FINITE]
        if nonfinite:
            res["qc"]["metrics"] = {k: sum(d[k] for d in nonfinite) for k in ("points_read", "nonfinite_dropped")}
        out = _fail(res, "no_usable_scan", ";".join(causes))
        # c10-m: said in the result and the lists, outside the failure's hash (its id does not move): how many scans
        # were listed and used, and, when scans were too short, how short
        out["qc"]["metrics"].update(scans_listed=len(res["inputs"]), scans_used=0)
        said = _no_usable_scan_statement(res["inputs"], too_few, signal=_raw_signal(choice))
        if said:
            out["qc"]["statements"] = {"no_usable_scan": said}
        return [out]

    cal = _calibration(group, stems, scans_data, headers, ctx)
    hashed_cal = _said_reference(cal)  # c12-cal: said in the result, not in the hashed files (no id moves)
    res["steps"].append(cal)
    res["review_flags"] += cal["flags"]
    shifts = cal["outcome"]["per_scan_alignment_shifts_eV"] or [0.0] * len(scans_data)
    for sa, d in zip(scans_data, shifts):
        sa["energy"] = sa["energy"] + cal["outcome"]["applied_shift_eV"] + d

    try:
        grid, ginfo = C.common_grid(scans_data, np)
    except C.StepError as exc:
        return [_fail(res, exc.code, exc.detail)]
    if grid.size < int(params["merge"]["min_points"]):
        return [_fail(res, "too_few_common_points", str(grid.size))]
    M = C.interpolate(scans_data, grid, np)
    dg = C.deglitch(M, grid, params, np)
    excl = bool(params["deglitch"]["exclude_flagged"])
    pos_sid = [e["source_id"] for e in used_entries]
    res["steps"].append(
        {
            "step": "deglitch",
            "params": {k: params["deglitch"][k] for k in ("point_z_threshold", "robust_scale", "min_scans_for_cross_scan", "scan_rms_ratio_threshold", "scan_rms_floor", "exclude_flagged")},
            "outcome": {
                "method": dg["method"],
                "flagged_points_total": dg["flagged_points_total"],
                "flagged_points_listed": [{"source_id": pos_sid[p["scan_position"]], "energy_eV": p["energy_eV"]} for p in dg["flagged_points_listed"]],
                "flagged_points_listed_truncated": dg["flagged_points_total"] > len(dg["flagged_points_listed"]),
                "scan_rms": dg["scan_rms"],
                "max_abs_z": dg["max_abs_z"],
                "outlier_scans": [pos_sid[i] for i, f in enumerate(dg["scan_flags"]) if f],
                "would_exclude": {"points": dg["flagged_points_total"], "scans": int(sum(dg["scan_flags"]))},
                "excluded": excl,
            },
            "flags": (["glitch_points_flagged"] if dg["flagged_points_total"] else []) + (["outlier_scans_flagged"] if any(dg["scan_flags"]) else []),
        }
    )
    mg = C.merge(M, dg["point_flags"] if excl else None, dg["scan_flags"] if excl else None, np)
    ok = np.isfinite(mg["mean"])
    g2, mean = grid[ok], mg["mean"][ok]
    if g2.size < int(params["merge"]["min_points"]):
        return [_fail(res, "too_few_common_points", str(g2.size))]
    res["steps"].append(
        {
            "step": "merge",
            "params": {k: params["merge"][k] for k in ("grid", "interpolation", "min_points")} | {"statistic": "mean, std (ddof=1), stderr = std/sqrt(N)"},
            "outcome": {
                "n_scans": len(scans_data),
                **{k: ginfo[k] for k in ("grid_eV", "all_scans_overlap_eV", "truncated_fraction")},
                "grid_from_source_id": pos_sid[ginfo["grid_from_scan_position"]],
                "truncated_scans": [pos_sid[i] for i in ginfo["truncated_scan_positions"]],
                "points": int(g2.size),
                "n_min": int(mg["n"][ok].min()) if ok.any() else 0,
                "n_max": int(mg["n"][ok].max()) if ok.any() else 0,
            },
            "flags": ([] if len(scans_data) > 1 else ["single_scan_no_merge"]) + (["scan_range_truncated"] if ginfo["truncated_scan_positions"] else []),
        }
    )
    try:
        nm = C.normalize(g2, mean, params, np, ctx.xafs)
    except C.StepError as exc:
        res["steps"].append({"step": "normalize", "params": dict(params["normalize"]), "outcome": {"error": exc.code, "detail": exc.detail}, "flags": ["normalization_failed"]})
        return [_fail(res, exc.code, exc.detail)]
    res["steps"].append(
        {"step": "normalize", "params": nm["resolved_params"], "outcome": {"e0_eV": nm["e0_eV"], "edge_step": nm["edge_step"], "pre_edge_noise": nm["pre_edge_noise"]}, "flags": []}
    )

    implausible = C.edge_step_implausible(nm["edge_step"], mean, np, post_edge=_post_edge_range(nm["resolved_params"]))
    checks = C.edge_checks(g2, mean, nm, np)
    short = C.post_edge_window_too_short(g2, nm["e0_eV"], np)
    truncated = _truncation_statement(ginfo, scans_data, pos_sid)
    diags = [sa["diagnostics"] for sa in scans_data]
    read_pts = sum(d["points_read"] for d in diags) or 1
    i0np = [d["i0_nonpositive"] for d in diags if d["i0_nonpositive"] is not None]
    step = nm["edge_step"]
    se = mg["stderr"][ok]
    lacking = sum(1 for e, _ in tables if e.get("skip_reason") == "scan_lacks_chosen_columns")
    zero_skipped = sum(1 for e in res["inputs"] if e.get("skip_reason") == C.SIGNAL_ALL_ZERO)
    metrics = {
        "scans_listed": len(scans),
        "scans_used": len(scans_data),
        # only when scans WERE skipped (absent otherwise, so an unaffected result is unchanged)
        **({"scans_readable": len(tables), "scans_skipped_lacking_chosen_columns": lacking} if lacking else {}),
        # only when the role's first channel was abandoned (absent otherwise, as above)
        **({"channel_fallback": choice.basis["fallback_from"]["reason_code"]} if fallback is not None else {}),
        "points": int(g2.size),
        "e0_eV": nm["e0_eV"],
        "edge_step": step,
        # only when the step failed the sanity bound (absent otherwise, so an unaffected result is unchanged)
        **({"edge_step_implausible": implausible["ratio"]} if implausible else {}),
        # only when the check failed (core.edge_checks; absent otherwise, as above)
        **({"post_edge_level": checks["post_edge_not_at_1"]["level"]} if "post_edge_not_at_1" in checks else {}),
        **({"edge_to_pre_edge_noise": checks["no_edge"]["edge_to_noise"]} if "no_edge" in checks else {}),
        **({"post_edge_span_eV": short["post_e0_span_eV"]} if short else {}),
        "pre_edge_noise": nm["pre_edge_noise"],
        "scan_spread": float(np.nanmedian(se) / abs(step)) if (len(scans_data) > 1 and step and np.isfinite(se).any()) else None,
        "glitch_points": dg["flagged_points_total"],
        "outlier_scans": int(sum(dg["scan_flags"])),
        "truncated_scans": len(ginfo["truncated_scan_positions"]),
        "energy_shift_eV": cal["outcome"]["computed_shift_eV"],
        "reference_e0_spread_eV": cal["outcome"]["reference_e0_spread_eV"],
        "signal_max_run": max(d["signal_max_run"] for d in diags),
        "nonmonotonic_steps": sum(d["nonmonotonic_steps"] for d in diags),
        "nonfinite_dropped": sum(d["nonfinite_dropped"] for d in diags),
        "duplicate_energies_merged": sum(d["duplicate_energies_merged"] for d in diags),
        "i0_nonpositive_fraction": (sum(i0np) / read_pts) if i0np else None,
        "signal_all_zero_scans": sum(1 for d in diags if d["signal_all_zero"]),
        # c11-a: only when a scan was skipped for a signal of zero at every point (absent otherwise, as above)
        **({"scans_skipped_signal_all_zero": zero_skipped} if zero_skipped else {}),
    }
    verdict, reasons = C.qc_verdict(metrics, params)
    res["qc"] = {"metrics": metrics, "verdict": verdict, "reasons": reasons}
    statements = {}
    if fallback is not None:
        statements[fallback_flag] = choice.basis["fallback_from"]["statement"]
    if truncated:
        statements["scans_truncated"] = truncated
        res["review_flags"].append(TRUNCATED_FLAG)
    if implausible:
        statements["edge_step_implausible"] = implausible["statement"]
        res["review_flags"].append("edge_step_implausible")
    for reason, finding in checks.items():
        statements[reason] = finding["statement"]
    if short:
        statements["post_edge_window_too_short"] = short["statement"]
    zero_said = _all_zero_statement(res["inputs"], _raw_signal(choice), len(scans_data))
    if zero_said:
        statements["scans_skipped_signal_all_zero"] = zero_said
    if statements:  # absent when there is nothing to say, so an unaffected result is unchanged
        res["qc"]["statements"] = statements
    res["steps"].append({"step": "qc", "params": dict(params["qc"]), "outcome": {"verdict": verdict, "reasons": reasons}, "flags": []})

    # outputs
    group_dir = ctx.out_dir / group["group_id"]
    group_dir.mkdir(parents=True, exist_ok=True)
    gdir = Path(tempfile.mkdtemp(prefix=".staging-", dir=group_dir))
    _csv(gdir / "merged.csv", ["energy_eV", "mu_mean", "mu_std", "mu_stderr", "n_scans"], [g2, mean, mg["std"][ok], se, mg["n"][ok].astype(float)], np)
    _csv(gdir / "normalized.csv", ["energy_eV", "norm", "flat"], [g2, nm["norm"], nm["flat"]], np)
    comparison = None
    athena_res = None
    # the run each used scan belongs to: in a group of several runs, scan numbers repeat across runs (c8-a)
    stem_of = {s.get("source_id"): (ctx.runs_by_key.get(s.get("run_key")) or {}).get("stem") for s in scans if s.get("run_key")}
    # c11-a/c11-r: each listed scan's number: its stated index or, when the run states none (one file per scan), the
    # number its file name states — never its place in the list. Used only to compare with the scientist's Athena
    # selection; the inputs keep what the bundle states. Said merged / not merged only when EVERY number is known.
    numbers, numbering = B.input_scan_numbers(res["inputs"], {s.get("source_id"): s.get("run_key") for s in scans})
    number_of = {id(e): n for e, n in zip(res["inputs"], numbers)}
    listed_scans = numbers if B.all_scan_numbers_known(numbers) else None
    coverage = None
    if athena_entry is not None:
        comparison = A.compare({"grid": g2, "norm": nm["norm"], "flat": nm["flat"], "e0_eV": nm["e0_eV"], "edge_step": step}, athena_entry, params, np)
        coverage = _diagnose(comparison, athena_entry, stems, used_entries, grid, M, ctx, stem_of=stem_of, number_of=number_of)
        res["comparison"] = comparison
        if comparison["verdict"] == "differs":
            res["review_flags"].append("athena_disagrees")
        if A.frame_known(athena_entry):
            _csv(gdir / "athena_normalized.csv", ["energy_eV", "norm", "flat"], [athena_entry["energy"], athena_entry["norm"], athena_entry["flat"]], np)
        elif A.ENERGY_FRAME_UNKNOWN_FLAG not in res["review_flags"]:
            res["review_flags"].append(A.ENERGY_FRAME_UNKNOWN_FLAG)
    version_files = []
    if athena_versions:
        # Several distinct Athena versions for this group (e.g. re-normalised, glitch-removed,
        # smoothed). NONE is selected: each is listed with what its own files state, compared,
        # and the scientist is asked which one is the result of record.
        res["athena_versions"] = []
        for n, v in enumerate(athena_versions, start=1):
            cmp_ = A.compare({"grid": g2, "norm": nm["norm"], "flat": nm["flat"], "e0_eV": nm["e0_eV"], "edge_step": step}, v, params, np)
            _diagnose(cmp_, v, stems, used_entries, grid, M, ctx, stem_of=stem_of, number_of=number_of)
            listed = {"version_id": f"{group['group_id']}-v{n:02d}", "provenance": A.version_provenance(v, stems), "comparison": cmp_}
            if not A.plausible(v):
                listed["flags"] = [A.EDGE_STEP_IMPLAUSIBLE_FLAG]
            if A.frame_known(v):
                name = f"athena_version_{n:02d}.csv"
                _csv(gdir / name, ["energy_eV", "norm", "flat"], [v["energy"], v["norm"], v["flat"]], np)
                version_files.append((f"athena_version_{n:02d}", name))
            else:
                # LISTED, so the question stays the scientist's; no curve file in an unknown energy frame
                listed["flags"] = [A.ENERGY_FRAME_UNKNOWN_FLAG]
                listed["non_finite_values"] = list(v.get("non_finite_values") or ())
                if A.ENERGY_FRAME_UNKNOWN_FLAG not in res["review_flags"]:
                    res["review_flags"].append(A.ENERGY_FRAME_UNKNOWN_FLAG)
            res["athena_versions"].append(listed)
        res["athena_result_of_record"] = None
        res["review_flags"].append("athena_result_of_record_not_selected")
        res["questions"] = [
            {
                "code": "which_athena_version_is_result_of_record",
                "text": _versions_question_text(athena_versions),
                "version_ids": [v["version_id"] for v in res["athena_versions"]],
            }
        ]
    plotted = False
    try:
        from .plot import review_plot

        plotted = review_plot(
            gdir / "plot.png",
            title=f"{group['group_id']} ({group.get('role')}) {', '.join(stems)[:90]}",
            grid=grid,
            M=M,
            merged=mg["mean"],
            point_flags=dg["point_flags"],
            scan_flags=dg["scan_flags"],
            norm=nm["norm"],
            flat=nm["flat"],
            e0=nm["e0_eV"],
            # never overlay a curve in an unknown energy frame, or one whose normalisation is implausible
            athena=athena_entry if athena_entry is not None and A.frame_known(athena_entry) and A.plausible(athena_entry) else None,
            np=np,
        )
    except Exception:  # noqa: BLE001 - a plot failure is a flag, never a processing failure
        plotted = False
    if not plotted:
        res["review_flags"].append("plot_unavailable")
    # qc.json is hashed: it keeps the reference spread as first written (0.0 for one usable scan), so no id moves; the
    # result's metrics say null (one scan has no spread)
    hashed_qc = {**res["qc"], "metrics": {**res["qc"]["metrics"], "reference_e0_spread_eV": hashed_cal["reference_e0_spread_eV"]}}
    _write(gdir / "qc.json", _json_bytes({"group_id": group["group_id"], **hashed_qc, "thresholds": params["qc"], "protocol_status": P.PROTOCOL_STATUS}))
    _write(
        gdir / "params.json",
        _json_bytes(
            {
                "protocol_id": P.PROTOCOL_ID,
                "protocol_version": P.PROTOCOL_VERSION,
                "protocol_status": P.PROTOCOL_STATUS,
                "notice": P.PROTOCOL_NOTICE,
                "params": params,
                "changed_from_default": P.changed_from_default(params),
                "needs_scientist_approval": P.needs_approval(),
                "protocol_questions": P.PROTOCOL_QUESTIONS,
                "channel_choice": res["channel_choice"],
                "calibration": hashed_cal,
                "normalize_resolved": nm["resolved_params"],
            }
        ),
    )
    roles = [("merged", "merged.csv"), ("normalized", "normalized.csv"), ("qc", "qc.json"), ("params", "params.json")]
    if plotted:
        roles.append(("plot", "plot.png"))
    if athena_entry is not None and A.frame_known(athena_entry):  # no curve file in an unknown energy frame
        roles.append(("athena_normalized", "athena_normalized.csv"))
    roles.extend(version_files)
    # CONTENT-ADDRESSED RUN DIRECTORY. A decided (approved) result's outputs are never
    # overwritten: each run lives in processing/<group>/<run_id>/, run_id = sha256 over the
    # protocol version, the group, the used inputs and every data output (the plot is
    # excluded: PNG bytes are not guaranteed reproducible). Changing any parameter makes a
    # NEW run_id and so NEW, undecided result ids; prior runs are kept untouched.
    data_hashes = sorted((name, sha256_file(gdir / name)) for role, name in roles if name != "plot.png")
    input_hashes = sorted((ctx.sources.get(e.get("source_id") or "") or {}).get("content_sha256") or str(e.get("relative_path")) for e in used_entries)
    run_id = run_id_for(group["group_id"], input_hashes, data_hashes)
    final = group_dir / run_id
    if final.exists():
        shutil.rmtree(gdir)  # identical content already on disk: keep it, never rewrite it
    else:
        gdir.rename(final)
    gdir = final
    res["run_id"] = run_id
    res["result_id"] = f"proc-{group['group_id']}-{run_id}-isaac"
    res["prior_run_ids"] = sorted(p.name for p in group_dir.iterdir() if p.is_dir() and _RUN_DIR.match(p.name) and p.name != run_id)
    # said in the result and the lists, NOT in qc.json: qc.json is hashed into run_id, so a sentence written there
    # would give every group with skipped scans a new result id (and orphan a decision made on the old one)
    skipped_said = _skipped_scans_statement(res["inputs"], choice, len(scans_data))
    if skipped_said:
        res["qc"].setdefault("statements", {})["scans_skipped_lacking_chosen_columns"] = skipped_said
    # c11-r: a merged scan whose signal is exactly zero where another's is not: merged unchanged, said and flagged
    # (after run_id: qc.json is hashed, so no result id moves)
    # c12-cal: with fewer scans than the cross-scan check needs, the glitch check compares each point with its
    # neighbours and flags real features too (white line, oscillations): said beside the count (after run_id: no id
    # moves; the count, the flag and the verdict are unchanged)
    few_said = _few_scan_glitch_statement(len(scans_data), dg["flagged_points_total"], params)
    if few_said:
        res["qc"].setdefault("statements", {})["glitch_check_few_scans"] = few_said
    zero_points_said = _zero_signal_points_statement(used_entries, scans_data, _raw_signal(choice), np)
    if zero_points_said:
        res["qc"].setdefault("statements", {})["merged_scan_zero_signal_points"] = zero_points_said
        res["review_flags"].append(ZERO_SIGNAL_POINTS_FLAG)
    # c12-cal: zeros whose counts come back are counted in one line (no flag), never said as a lost beam
    isolated_said = _isolated_zero_points_statement(used_entries, scans_data, _raw_signal(choice), np)
    if isolated_said:
        res["qc"].setdefault("statements", {})["merged_scan_isolated_zero_points"] = isolated_said
    # c12-cal: the merged curve's ends from one scan alone (the grid is the widest scan's; nothing is trimmed)
    ends_said = _one_scan_ends_statement(g2, mg["n"][ok], used_entries, M[:, ok], len(scans_data), np)
    if ends_said:
        res["qc"].setdefault("statements", {})["merged_curve_end_from_one_scan"] = ends_said
    if truncated:
        # c12-cal: the result names each short scan by its FILE; qc.json (hashed) keeps the sentence it was written with
        res["qc"]["statements"]["scans_truncated"] = _truncation_statement(ginfo, scans_data, [_file_name(e) for e in used_entries])
    files = []
    for role, name in roles:
        p = gdir / name
        if p.is_file():
            files.append({"role": role, "relative_path": PurePosixPath(p.relative_to(ctx.bundle_dir)).as_posix(), "sha256": sha256_file(p)})
    res["outputs"] = {"files": files, "e0_eV": nm["e0_eV"], "edge_step": step, "points": int(g2.size)}

    out = [res]
    if athena_entry is not None:
        athena_res = _athena_result(group, athena_entry, files, params, np, ctx, stems=stems, isaac_counts=(len(scans_data), len(scans)),
                                    coverage=coverage,
                                    isaac_scans=[number_of[id(e)] for e in used_entries] if listed_scans else None,
                                    listed_scans=listed_scans,
                                    numbered_from_file_names=numbering == B.SCAN_NUMBERS_FROM_FILE_NAME)
        athena_res["comparison"] = comparison
        # a curve whose energy frame is unknown (non-finite bkg_eshift) is never preferred by default;
        # its result carries athena_energy_frame_unknown, and a scientist can still approve it
        # nor is a curve whose edge step failed the sanity bound (its QC fails edge_step_implausible), nor (c8-a) a
        # curve of only some of a merged group's runs: it does not describe the group (its statement says so)
        athena_res["preferred_for_record"] = (A.frame_known(athena_entry) and A.plausible(athena_entry)
                                              and not (coverage or {}).get("partial"))
        athena_res["run_id"] = run_id
        athena_res["result_id"] = f"proc-{group['group_id']}-{run_id}-athena"
        out.append(athena_res)
    # result.json is a SNAPSHOT, written once with the run folder: a re-run into an existing folder leaves it as it is
    # (the folder is content-addressed and never rewritten), so a sentence added to the result later (the non-hashed
    # `qc.statements`) is in bundle.json and the list/show output, not necessarily in an older result.json
    record = gdir / "result.json"
    if not record.exists():
        _write(record, _json_bytes({"results": out}))
    return out


def _diagnose(comparison: dict, entry: Mapping, stems: Sequence[str], used_entries: Sequence[Mapping], grid, M, ctx: _Ctx,
              *, stem_of: Mapping[str, str] | None = None, number_of: Mapping[int, int | None] | None = None) -> dict | None:
    """Separate WHY ISAAC and Athena differ (diagnostics only; the verdict is unchanged):

    * ``rms_norm_with_athena_params`` — ISAAC's merge of ALL its scans, normalised with the
      scientist's e0/pre/post parameters: what remains is data (scans, channel, energy).
    * ``rms_norm_same_scans_same_params`` — only the scans the Athena label selects
      (``_5-6``), same parameters: what remains is channel / energy axis / processing.
    """
    np = ctx.np
    sel = A.scan_selection(entry["label"], stems)
    # c8-a: in a group of several runs, the scans compared are those of the run(s) the Athena curve names (scan
    # numbers restart in each run), and a curve of only some of the runs is a subset of what ISAAC merged
    coverage = _athena_coverage(entry, stems, used_entries, stem_of or {})
    # c10-m: in a ONE-run group a set of per-scan groups selects the scans its members name, exactly as a label does
    # (its own label is its first member's); in a group of several runs that is athena_covers.scans, per run
    chosen = sel or (_set_scans(entry) if coverage is None else None)
    comparison["athena_scan_selection"] = chosen
    mine = [e for e in used_entries if coverage is None or (stem_of or {}).get(e.get("source_id")) in coverage["runs"]]
    # c11-a/c11-r: a scan's number is its stated index or, in a run that states none, the number its file name states
    def number(e: Mapping):
        return (number_of or {}).get(id(e), e.get("scan"))

    idx = [number(e) for e in mine]
    # c11-r: with some number unknown, a selection is never said to be the full merge (the note says it neutrally)
    if (chosen and (None in idx or set(chosen) != set(idx))) or (coverage or {}).get("partial"):
        comparison["flags"].append("scientist_selected_subset_of_scans")
    if coverage is not None:
        comparison["athena_covers"] = {k: coverage[k] for k in ("runs", "group_runs", "scans", "isaac_scans_merged")}
    p = entry["params"]
    if not A.frame_known(entry) or any(p.get(k) is None for k in ("e0", "pre1", "pre2", "nor1", "nor2", "nnorm")):
        return coverage
    if A.already_normalized(entry) or not A.plausible(entry):
        # the project's parameters were not what made this curve (already normalised), or what they make
        # is not a usable curve (implausible edge step): re-running them on ISAAC's merge says nothing
        return coverage
    quantity = comparison["metrics"].get("compared_quantity", "flat")
    eshift = float(p.get("eshift") or 0.0)

    def _rms(rows) -> float | None:
        if not rows:
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mean = np.nanmean(M[rows], axis=0)
        ok = np.isfinite(mean)
        if ok.sum() < 10:
            return None
        from larch import Group

        g = Group()
        try:
            ctx.xafs.pre_edge(grid[ok], mean[ok], group=g, e0=float(p["e0"]) + eshift, pre1=float(p["pre1"]), pre2=float(p["pre2"]),
                              norm1=float(p["nor1"]), norm2=float(p["nor2"]), nnorm=int(float(p["nnorm"])))
        except Exception:  # noqa: BLE001 - a diagnostic that cannot be computed is omitted
            return None
        y = np.asarray(getattr(g, quantity, g.norm), dtype=float)
        e = grid[ok]
        ae = entry["energy"]
        inside = (e >= ae[0]) & (e <= ae[-1])
        if inside.sum() < 10:
            return None
        return C._f(np.sqrt(np.mean((y[inside] - np.interp(e[inside], ae, entry[quantity])) ** 2)))

    comparison["metrics"]["rms_norm_with_athena_params"] = _rms(list(range(M.shape[0])))
    if sel:
        keep = {id(e) for e in mine}
        rows = [i for i, e in enumerate(used_entries) if id(e) in keep and number(e) in set(sel)]
        if rows and len(rows) == len(sel):
            comparison["metrics"]["rms_norm_same_scans_same_params"] = _rms(rows)
    return coverage


def _athena_result(group: Mapping, entry: Mapping, files: Sequence[Mapping], params: Mapping, np, ctx: _Ctx, *,
                   stems: Sequence[str] = (), isaac_counts: tuple[int, int] | None = None,
                   coverage: Mapping | None = None, isaac_scans: Sequence[int] | None = None,
                   listed_scans: Sequence[int] | None = None, numbered_from_file_names: bool = False) -> dict:
    res = _base(group, "scientist_athena")
    members = entry.get("per_scan_set") if entry.get("_match_kind") == "per_scan_set" else None
    # A SET of the scientist's per-scan groups is ISAAC's mean of them (athena._per_scan_set), not values
    # ISAAC left unchanged: the flag and the input say so, and name every member group
    res["review_flags"] = ["scientist_processed_data",
                           "isaac_computed_mean_of_scientist_per_scan_curves" if members else "isaac_did_not_change_scientist_values"]
    scans_used = _athena_scans_used(entry, stems, isaac_counts, coverage, isaac_scans, listed_scans=listed_scans,
                                    numbered_from_file_names=numbered_from_file_names)
    res["inputs"] = [
        {
            "source_id": entry["prj_source_id"],
            "scan": entry["label"],
            "channel": entry["channel_expression"],
            "relative_path": entry["prj_relative_path"],
            "athena_group": entry["group_name"],
            "match_kind": entry.get("_match_kind"),
            # the Athena group IS the input and it is what was used; which SCANS went into it is scans_basis/scans
            "used": True,
            "scans_basis": scans_used["basis"],
            "scans": scans_used["scans"],
            **({"per_scan_set": A._set_named(entry, members)} if members else {}),
        }
    ]
    e = entry["energy"]
    # A value the project stated as a non-finite number is None on the entry (athena.load_project);
    # it is NAMED here, so the result never hides it.
    non_finite = list(entry.get("non_finite_values") or ())
    noise = None
    if entry["e0_eV"] is not None:
        sel = (e >= entry["e0_eV"] + (entry["params"].get("pre1") or -1e9)) & (e <= entry["e0_eV"] + (entry["params"].get("pre2") or -1e9))
        if np.sum(sel) >= 3 and entry["edge_step"]:
            # pre-edge residual of the scientist's own normalised curve (norm ~ 0 before the edge)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                noise = C._f(np.std(entry["norm"][sel]))
            if noise is None:
                non_finite.append("qc.metrics.pre_edge_noise")
    if not A.frame_known(entry):
        res["review_flags"].append(A.ENERGY_FRAME_UNKNOWN_FLAG)
    if non_finite:
        res["review_flags"].append("athena_value_not_finite")
        res["non_finite_values"] = {
            "paths": non_finite,
            "reason": ("the scientist's Athena project gives these as non-finite numbers (NaN or infinity), which "
                       "are not JSON numbers; each is recorded as null, never as a number ISAAC made up"),
        }
    if A.already_normalized(entry):
        reproduced = (f"none: the group is already normalised (Athena is_nor), so its stored spectrum is used as stored, "
                      f"edge step 1 by definition ({A.ALREADY_NORMALIZED_RULE_ID})")
    else:
        reproduced = "larch AthenaProject.read(do_preedge=True)"
    res["steps"] = [
        {
            "step": "normalize",
            "params": {**entry["params"], "reproduced_with": reproduced, "energy_frame": "stored energy + bkg_eshift"},
            "outcome": {"e0_eV": entry["e0_eV"], "edge_step": entry["edge_step"]},
            "flags": ["scientist_params_recorded"] + (["athena_already_normalized"] if A.already_normalized(entry) else []),
        }
    ]
    steps_ok = np.all(np.diff(e) > 0)
    metrics = {
        "scans_used": None,
        "points": int(e.size),
        "e0_eV": entry["e0_eV"],
        "edge_step": entry["edge_step"],
        "pre_edge_noise": noise,
        "nonmonotonic_steps": 0 if steps_ok else int(np.sum(np.diff(e) <= 0)),
    }
    bad = entry.get("edge_step_implausible")
    if bad:
        metrics["edge_step_implausible"] = bad["ratio"] if "ratio" in bad else bad.get("post_edge_mean")
    verdict, reasons = C.qc_verdict(metrics, params)
    res["qc"] = {"metrics": metrics, "verdict": verdict, "reasons": reasons}
    res["qc"]["statements"] = {"scans_used": scans_used["statement"]}
    if bad:
        res["qc"]["statements"]["edge_step_implausible"] = bad["statement"]
        res["review_flags"].append("edge_step_implausible")
    res["steps"].append({"step": "qc", "params": dict(params["qc"]), "outcome": {"verdict": verdict, "reasons": reasons}, "flags": []})
    ath = [f for f in files if f["role"] in ("athena_normalized", "plot")]
    res["outputs"] = {"files": ath, "e0_eV": entry["e0_eV"], "edge_step": entry["edge_step"], "points": int(e.size)}
    return res


# --- whole bundle ---------------------------------------------------------------------------


def _groups_for(bundle: Mapping, bundle_dir: Path) -> tuple[list[dict], list[dict], str]:
    if bundle.get("record_groups"):
        rec, origin = list(bundle["record_groups"]), "bundle.json"
    else:
        f = bundle_dir / "record_groups.json"
        if f.is_file():
            data = json.loads(f.read_text(encoding="utf-8"))
            return list(data.get("record_groups") or ()), list(data.get("unread_acquisition_groups") or ()), "record_groups.json"
        rec, origin = G.propose_record_groups(bundle), "proposed_now"
    return rec, G.propose_unread_acquisition_groups(bundle), origin


def process_bundle(
    bundle_dir: Path,
    *,
    source_root: Path | None = None,
    params: Mapping | None = None,
    group_ids: Sequence[str] | None = None,
    include_unread: bool = True,
    athena: bool = True,
    bundle: Mapping | None = None,
    created_utc: str | None = None,
    generic_runs: Sequence[Any] | None = None,
    scan_reader: Any = None,
    calibration_approvals: Mapping[str, Mapping] | None = None,
    skip_group_ids: Sequence[str] = (),
) -> dict:
    """Process every (or the selected) record group of the bundle in ``bundle_dir``.

    ``skip_group_ids``: record groups NOT processed (``isaac process`` passes the groups that are no
    longer live: rejected, merged, split). They still take part in the Athena name match, exactly as
    before, so no live group's match — and so no live group's result id — moves because of them.

    ``generic_runs``: runs from a non-engine reader (duck-typed, see
    :func:`grouping.groups_from_generic_runs`); when given they REPLACE the unread-file
    fallback groups. ``scan_reader``: ``callable(path) -> readers.ScanTable`` used instead
    of the built-in content-sniffing reader (adapt a reader's output with
    :func:`readers.table_from_columns`). ``calibration_approvals``: ``{group_id: {element,
    edge, decided_by, decision_id}}`` from the scientist's processing-approval decisions —
    the ONLY thing that applies a calibration shift.
    """
    from ..bundle import load_bundle

    bundle_dir = Path(bundle_dir)
    bundle = bundle if bundle is not None else load_bundle(bundle_dir)
    out_dir = bundle_dir / PROCESSING_DIR
    resolved = P.resolve_params(params)
    header = {
        "format": RESULTS_FORMAT,
        "format_version": RESULTS_FORMAT_VERSION,
        "protocol": {"id": P.PROTOCOL_ID, "version": P.PROTOCOL_VERSION, "status": P.PROTOCOL_STATUS, "notice": P.PROTOCOL_NOTICE, "protocol_questions": P.PROTOCOL_QUESTIONS},
        "bundle_id": bundle.get("bundle_id"),
        "experiment_key": G.experiment_key_of(bundle),
        "created_utc": created_utc or _now(),
    }
    try:
        mods = _deps.require()
    except _deps.ProcessingUnavailable as exc:
        status = {**header, "status": "processing_unavailable", "missing": exc.missing, "detail": exc.detail, "processing_results": []}
        _write(out_dir / STATUS_FILE, _json_bytes(status))
        return status
    np = mods["numpy"]
    import larch.xafs as xafs

    root = Path(source_root) if source_root else None
    if root is None and (bundle.get("source_root") or {}).get("local_root_hint"):
        root = Path(bundle["source_root"]["local_root_hint"])
    rec, unread, origin = _groups_for(bundle, bundle_dir)
    if generic_runs is not None:
        by_path = {s.get("relative_path"): s.get("source_id") for s in bundle.get("sources") or ()}
        unread = G.groups_from_generic_runs(generic_runs, experiment_key=G.experiment_key_of(bundle), sources_by_path=by_path)
    if not include_unread:
        unread = []
    if group_ids:
        wanted = set(group_ids)
        rec = [g for g in rec if g["group_id"] in wanted]
        unread = [g for g in unread if g["group_id"] in wanted]
    runs_by_key = {r["run_key"]: r for r in bundle.get("runs") or ()}
    sources = {s["source_id"]: s for s in bundle.get("sources") or () if s.get("source_id")}
    ctx = _Ctx(bundle=bundle, bundle_dir=bundle_dir, root=root, params=resolved, np=np, xafs=xafs, out_dir=out_dir, sources=sources, runs_by_key=runs_by_key)
    ctx.scan_reader = scan_reader or read_scan_file
    ctx.calibration_approvals = dict(calibration_approvals or {})

    # Athena-first: read every project once, match by name.
    entries, a_notes, projects = [], [], A.find_projects(bundle)
    read_ok = 0
    if athena and resolved["athena"]["enabled"] and root is not None:
        for rel, sid in projects:
            path = _resolve_source(root, rel)
            if path is None or not path.is_file():
                a_notes.append({"code": "athena_project_not_found", "prj_relative_path": rel})
                continue
            got, notes = A.load_project(path, rel, sid, np)
            read_ok += 1 if got or not notes else 0
            entries.extend(got)
            a_notes.extend({"code": n.split(":", 1)[0], "detail": n} for n in notes if not n.startswith("athena_group_not_xmu"))
    all_groups = [dict(g) for g in rec] + [dict(g) for g in unread]
    for g in all_groups:
        scans_, stems_, _ = group_scans(g, runs_by_key)
        g["_stems"], g["_has_scans"] = stems_, bool(scans_)
    matched, m_notes, versions = A.match_with_versions(all_groups, entries, np)

    results, unread_results = [], []
    skipped = set(skip_group_ids or ())
    for g in all_groups:
        if g["group_id"] in skipped and g.get("group_kind") not in ("unread_acquisition", "generic_run"):
            continue
        try:
            out = process_group(g, ctx, matched.get(g["group_id"]), athena_versions=versions.get(g["group_id"]))
        except Exception as exc:  # noqa: BLE001 - one group's crash is that group's failure, never a pass
            out = [_fail(_base(g, "isaac_protocol"), "processing_error", f"{type(exc).__name__}: {exc}"[:500])]
        for r in out:
            _null_non_finite(r)
        (unread_results if g.get("group_kind") in ("unread_acquisition", "generic_run") else results).extend(out)

    payload = {
        **header,
        "status": "processed",
        "groups_origin": origin,
        "source_root_label": (bundle.get("source_root") or {}).get("label"),
        "source_root_available": root is not None,
        "software": _deps.versions(),
        "athena": {
            "projects_found": len(projects),
            "projects_read": read_ok,
            "groups_read": len(entries),
            "record_groups_matched": len(matched),
            "record_groups_with_unselected_versions": len(versions),
            "notes": (a_notes + m_notes)[:500],
            "match_rule": A.MATCH_RULE_ID,
            "statement": athena_match_statement(all_groups, entries, matched=matched, notes=m_notes),
        },
        "processing_results": results,
        "unread_acquisition_results": unread_results,
        "summary": summarize(results + unread_results),
    }
    if payload["athena"]["statement"]:
        payload["summary"]["lines"].append(payload["athena"]["statement"])
    _write(out_dir / RESULTS_FILE, _json_bytes(payload))
    return payload


_STATED_SUFFIXES = 3


def athena_match_statement(groups: Sequence[Mapping], entries: Sequence[Mapping], *, matched: Mapping, notes: Sequence[Mapping]) -> str | None:
    """ONE LINE saying why the Athena groups that were read matched NO record group, or ``None`` when
    there were none to match or some matched. Names how many Athena names BEGIN with a group's scan
    name but end in a suffix the match rule does not accept (measured on a real BL4-3 beamtime: 161
    Athena groups named ``<scan>_a_001``, none matched under v0; v1 accepts that XDC scan-file suffix),
    and how many matched several groups. A name the rule accepts is never counted as a near miss."""
    if not entries or matched:
        return None
    stems = {A.normalise_name(s) for g in groups if g.get("_has_scans", True) for s in g.get("_stems") or ()}
    stems.discard("")
    near, suffixes = 0, []
    for e in entries:
        tails = [n[len(st):] for n in e.get("names") or () for st in stems
                 if n and n.startswith(st + "_") and not A.accepted_suffix(n[len(st) + 1:])]
        if tails:
            near += 1
            tail = min(tails, key=len)
            if tail not in suffixes:
                suffixes.append(tail)
    ambiguous = sum(1 for n in notes if n.get("code") == "athena_group_matches_several_record_groups")
    line = (f"Athena: {len(entries)} Athena group(s) were read and matched no record group under rule {A.MATCH_RULE_ID} "
            "(an Athena name equal to a group's scan name, or that name plus a scan or merge suffix such as _001 or _merged, "
            "or plus an XDC scan-file suffix such as _A.001)")
    if near:
        shown = ", ".join(f"'{t}'" for t in suffixes[:_STATED_SUFFIXES]) + (" …" if len(suffixes) > _STATED_SUFFIXES else "")
        line += f"; {near} of them begin with a group's scan name but end in a suffix the rule does not accept ({shown})"
    if ambiguous:
        line += f"; {ambiguous} matched several record groups, so none was used"
    if not near and not ambiguous:
        line += "; their names are not the scan names"
    return line + ". No ISAAC result was compared with the scientist's Athena processing."


def _null_non_finite(result: dict) -> None:
    """LAST GUARD: a NaN or infinity anywhere in a result (not a JSON number; a bundle holding one is
    refused) becomes null, and every path it was at is NAMED on the result
    (``non_finite_values.paths``, review flag ``value_not_finite``) — never silent, never a number."""

    def walk(obj, where):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, float) and not math.isfinite(v):
                    obj[k] = None
                    found.append(f"{where}{k}")
                else:
                    walk(v, f"{where}{k}.")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, float) and not math.isfinite(v):
                    obj[i] = None
                    found.append(f"{where}{i}")
                else:
                    walk(v, f"{where}{i}.")

    found: list[str] = []
    walk(result, "")
    if found:
        block = result.setdefault("non_finite_values", {"paths": [], "reason": (
            "these were computed or read as non-finite numbers (NaN or infinity), which are not JSON "
            "numbers; each is recorded as null, never as a number ISAAC made up")})
        block["paths"] = list(block["paths"]) + [p for p in found if p not in block["paths"]]
        flags = result.setdefault("review_flags", [])
        if "value_not_finite" not in flags:
            flags.append("value_not_finite")


def summarize(results: Sequence[Mapping]) -> dict:
    """Counts. A not-applicable group is counted APART from the QC verdicts, never as a fail."""
    isaac = [r for r in results if r.get("source") == "isaac_protocol"]
    na = [r for r in isaac if B.processing_not_applicable(r)]
    applied = [r for r in isaac if not B.processing_not_applicable(r)]
    verdicts: dict[str, int] = {}
    failures: dict[str, int] = {}
    comp: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    by_reader: dict[str, int] = {}
    for r in na:
        code = r["applicability"]["reason_code"]
        by_reason[code] = by_reason.get(code, 0) + 1
        if code == B.NA_NO_XAS_CHANNEL:
            name = reader_label(r)
            by_reader[name] = by_reader.get(name, 0) + 1
    for r in applied:
        verdicts[r["qc"]["verdict"]] = verdicts.get(r["qc"]["verdict"], 0) + 1
        if r.get("failure"):
            code = r["failure"]["code"]
            failures[code] = failures.get(code, 0) + 1
        if r.get("comparison"):
            v = r["comparison"]["verdict"]
            comp[v] = comp.get(v, 0) + 1
    return {
        "groups": len(isaac),
        "groups_processed": len(applied),
        "qc_verdicts": dict(sorted(verdicts.items())),
        "failures_by_cause": dict(sorted(failures.items())),
        "not_applicable": {
            "groups": len(na),
            "by_reason": dict(sorted(by_reason.items())),
            "no_xas_channel_by_reader": dict(sorted(by_reader.items())),
        },
        "athena_matched": sum(comp.values()),
        "athena_comparison": dict(sorted(comp.items())),
        "lines": summary_lines(len(applied), verdicts, by_reason, by_reader),
    }


def summary_lines(processed: int, verdicts: Mapping[str, int], by_reason: Mapping[str, int], by_reader: Mapping[str, int]) -> list[str]:
    """The plain sentences ``isaac process`` and ``summary.md`` print."""
    qc = ", ".join(f"{k} {verdicts[k]}" for k in ("pass", "warn", "fail") if verdicts.get(k)) or "none"
    lines = [f"{processed} groups processed by draft protocol {P.PROTOCOL_ID}: QC {qc} (a person states the QC status)."]
    n = by_reason.get(B.NA_NO_XAS_CHANNEL, 0)
    if n:
        readers = ", ".join(f"{k} {v}" for k, v in sorted(by_reader.items()))
        lines.append(f"{n} groups: no ISAAC processing protocol applies (no absorption channel could be formed; by reader: {readers}). No QC verdict.")
    m = by_reason.get(B.NA_NO_SCANS, 0)
    if m:
        lines.append(f"{m} groups: no scans, nothing to process. No QC verdict.")
    return lines
