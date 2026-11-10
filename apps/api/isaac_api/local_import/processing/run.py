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
import statistics
import tempfile
import warnings
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .. import bundle as B
from .. import grouping as G
from . import _deps
from . import athena as A
from . import core as C
from . import protocol as P
from .channels import MODE_TRANSMISSION, ChannelChoice, choose_channels, dead_candidates, needs_review_statement
from . import reference as REF
from .edges import edge_energy
from .readers import read_scan_file

PROCESSING_DIR = "processing"
RESULTS_FILE = "processing_results.json"
STATUS_FILE = "status.json"
RESULTS_FORMAT = "isaac.processing-results"
#: 0.2.0 (additive): ``applicability`` on a not-applicable result; ``summary.not_applicable``.
#: 0.3.0 (additive): ``scan_selection`` on an ISAAC result (:data:`SCAN_SELECTION_KEY`), the review flag
#: :data:`SCAN_SELECTION_FLAG` and ``qc.statements.scan_selection``; ``scan_selection_series`` on the payload.
RESULTS_FORMAT_VERSION = "0.3.0"

ELEMENTS = REF.ELEMENTS
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


def _stated_edges(el: str, bundle: Mapping, header_lines: Sequence[str]) -> tuple[set, list[dict]]:
    """The edges the evidence states for element ``el`` (bundle element evidence, XDAC region-file header lines)."""
    edges: set = set()
    basis: list[dict] = []
    for ev in (bundle.get("experiment") or {}).get("element_evidence") or ():
        if ev.get("element") == el and ev.get("edge"):
            edges.add(ev["edge"])
            basis.append({"kind": "bundle_element_evidence", "source_id": ev.get("source_id"), "locator": ev.get("locator"), "edge": ev["edge"]})
    for i, line in enumerate(header_lines):
        m = _REGION_SYMBOL.match(line.strip())
        if m and m.group(1) == el:
            edges.add(m.group(2))
            basis.append({"kind": "scan_header_region_symbol", "header_line_index": i, "literal": line.strip()[:80], "edge": m.group(2)})
    return edges, basis


def stated_reference(name: str, bundle: Mapping, header_lines: Sequence[str],
                     calibrant: Mapping | None = None) -> tuple[dict | None, str]:
    """A reference foil's element + edge, ONLY when evidence states both. (reference, reason).

    Element: r3-b M2: the ONE name reading that also says whether the group is named as a pure element
    (:func:`reference.calibrant_identity` — ``calibrant``, the group's reading, else ``name``'s alone): its element when
    it says one pure element (a foil named with words of how it was measured, ``SYN_Ti_foil_I1``, ``SYN_Tifoil_calib_
    1x3mm``). Before, only a ``foil`` token and one case-sensitive symbol were read, and ``Tifoil`` proposed nothing.
    Edge: the bundle's ``experiment.element_evidence`` for that element, and/or a header line shaped ``<El><Edge>_`` (an
    XDAC region file, e.g. ``ZzK_SYNTHETIC.rgn``); every stated edge must agree.

    THE HASHED OUTCOME DOES NOT MOVE where the proposal did not: the reference and its evidence keep the shape they
    had (``name_token``), and when nothing is proposed the reason is the one the earlier rule gave (``name_has_no_foil_
    token``, ``foil_element_not_unique:[...]``, ``edge_not_stated_uniquely:[...]``). r3-d: where the earlier rule (a
    ``foil`` token and one symbol, an edge stated) found a reference and the reading says "ISAAC cannot tell" (a word
    not on its list beside them), that reference is returned too: it stays in the hashed outcome with its computed
    shift, which the scientist needs for ``--accept-shift``, and the result id does not move. It is still NOT proposed
    (``calibration_proposed`` follows the reading, :func:`reference.reading`; nothing awaits an approval). So only a
    group the reading newly names (``Tifoil``) gets a new result id. The statement (not hashed) says what the reading
    says.
    """
    toks = [t for t in _TOKEN.split(name) if t]
    foil = any(t.casefold().startswith("foil") for t in toks)
    els = sorted({t for t in toks if t in ELEMENTS})
    legacy = "name_has_no_foil_token" if not foil else (f"foil_element_not_unique:{els}" if len(els) != 1 else None)
    if legacy is None:
        edges, _ = _stated_edges(els[0], bundle, header_lines)
        legacy = None if len(edges) == 1 else f"edge_not_stated_uniquely:{sorted(edges)}"
    cal = calibrant if calibrant is not None else REF.calibrant_identity([name])
    el = REF.named_element(cal)
    if el is None and legacy is None:
        el = els[0]  # r3-d: the earlier rule's reference stays hashed (with its shift); the reading keeps it unproposed
    if el is None:
        return None, legacy
    edges, stated = _stated_edges(el, bundle, header_lines)
    if len(edges) != 1:
        return None, legacy or f"edge_not_stated_uniquely:{sorted(edges)}"
    basis = [{"kind": "name_token", "name": name, "element": el}, *stated]
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
        self.athena_ties: dict[str, list[dict]] = {}  # r6 G1: {group id: the ties the scientist named for it}
        self.scan_series: dict | None = None  # scan selection: the series pass (:func:`scan_selection_series`)


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
    "ssrl_xdc_v1": "SSRL EXAFS Data Collector 2.0 or 4.0 text scan",
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


def identity_texts(group: Mapping, stems: Sequence[str]) -> list[str]:
    """The names a group's sample is known by: its sample identity readings (``basis.sample``) and its run names."""
    sample = (group.get("basis") or {}).get("sample")
    said = [t for entry in (sample.values() if isinstance(sample, Mapping) else ())
            for t in REF._texts((entry or {}).get("value") if isinstance(entry, Mapping) else entry)]
    return list(dict.fromkeys([*said, *(str(s) for s in stems if s)]))


def _calibration(group: Mapping, stems: Sequence[str], scans_data: list[dict], headers: Sequence[str], ctx: _Ctx,
                 calibrant: Mapping | None = None) -> dict:
    """``calibrant``: :func:`reference.calibrant_identity` of a REFERENCE group (``None`` otherwise): a hint only. An
    approval of a reference group's own edge is applied only with its size confirmed (``--accept-shift``), whatever
    the size and whatever its names say (:data:`reference.CALIBRANT_RULE_ID`)."""
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
    own = role == "reference"
    # CALIBRANT_RULE_ID: names that do not clearly say one pure element: the group's own edge is not proposed
    not_named = own and REF.named_element(calibrant) is None
    if not_named:
        flags.append(REF.NOT_NAMED_ELEMENT_FLAG)
    if role == "reference":
        ref_source = "reference_group_own_signal"
        per_scan = [C.edge_e0(sa["energy"], sa["mu"], np, ctx.xafs) for sa in scans_data]
        if not proposed:
            stated, unconfirmed_reason = stated_reference(stems[0] if stems else "", ctx.bundle, headers, calibrant)
            if stated:
                proposed = stated
    elif cp.get("use_in_scan_reference_channel") and any(sa.get("mu_ref") is not None for sa in scans_data):
        ref_source = "in_scan_reference_channel"
        per_scan = [C.edge_e0(sa["energy"], sa["mu_ref"], np, ctx.xafs) if sa.get("mu_ref") is not None else None for sa in scans_data]
        unconfirmed_reason = "in_scan_reference_element_not_confirmed"
    else:
        flags.append("no_reference_available")
        unconfirmed_reason = "no_reference"
    # c12-r (REF.STRICTER_ONLY_RULE_ID): a params file may raise the in-scan SNR rule, never lower it
    min_snr = REF.effective_min_snr(cp["reference_min_edge_snr"], ref_source)
    usable = [r for r in per_scan if r and r.get("e0_eV") is not None and (r.get("snr") or 0) >= min_snr]
    if per_scan and not usable:
        flags.append("reference_edge_not_found")
    # c12-cal (REF.IN_SCAN_MIN_RULE_ID): an in-scan reference whose edge is usable in fewer than
    # MIN_IN_SCAN_REFERENCE_SCANS scans is no reference: no shift is computed or applied, even under an approval
    too_few = ref_source == REF.IN_SCAN and 0 < len(usable) < REF.MIN_IN_SCAN_REFERENCE_SCANS
    if too_few:
        flags.append(REF.TOO_FEW_FLAG)
    # r4-a: the reading every reader of the stored step makes (REF.judge): a scan whose pre-edge noise is about zero is
    # not usable (DEGENERATE_RULE_ID): too few usable scans BLOCK a shift, none is applied even under an approval; usable
    # edges that spread over more than the reference-spread level are not proposed and an approval of them is applied
    # only with its size confirmed (SPREAD_RULE_ID, as a group's own edge). What is hashed
    # (measured edge, spread, computed shift) keeps the earlier rule's values, so a group whose curve does not change
    # keeps its id; only a group with a NAMED reference (approved, or a params file's) and a degenerate scan reads its
    # edge from the usable scans alone (its shift would otherwise come from a channel that is not counting).
    j = REF.judge([r.get("e0_eV") if r else None for r in per_scan], [r.get("snr") if r else None for r in per_scan],
                  min_snr, ref_source, ctx.params["qc"].get("warn_reference_e0_spread_eV"))
    blocked = ref_source is not None and not j["proposed"]
    if j["degenerate"]:
        flags.append(REF.DEGENERATE_FLAG)
    if j["disagree"]:
        flags.append(REF.SPREAD_FLAG)
    if ref_source == REF.IN_SCAN and 0 < len(j["usable"]) < j["need"] and not too_few:
        flags.append(REF.TOO_FEW_FLAG)
    if usable and not j["usable"]:
        flags.append("reference_edge_not_found")
    measured = spread = None
    if usable:
        e0s = [r["e0_eV"] for r in usable]
        measured = float(np.median(e0s))
        spread = float(max(e0s) - min(e0s))
    ref = approved or proposed
    if ref and j["degenerate"]:
        measured = float(np.median(j["usable"])) if j["usable"] else None
        spread = float(max(j["usable"]) - min(j["usable"])) if j["usable"] else None
    # r4-a (NEAR_SAMPLE_RULE_ID): an in-scan reference edge at the group's own (uncalibrated) sample E0
    said: dict = {}
    near = None
    if ref_source == REF.IN_SCAN and j["proposed"]:
        own_e0 = [x["e0_eV"] for x in (C.edge_e0(sa["energy"], sa["mu"], np, ctx.xafs) for sa in scans_data)
                  if x and x.get("e0_eV") is not None]
        if own_e0:
            said["sample_e0_eV"] = float(np.median(own_e0))
            near = REF.near_sample({"reference_source": ref_source, **said}, float(np.median(j["usable"])))
            if near is not None:
                flags.append(REF.NEAR_SAMPLE_FLAG)
    if j["max_spread_eV"] != REF.DEFAULT_MAX_SPREAD_EV:
        said["reference_max_spread_eV"] = j["max_spread_eV"]
    tab = tab_src = shift = None
    applied = 0.0
    if not approved and ref_source is not None:
        # r2-a L5: with no reference at all, no_reference_available says it; "unconfirmed" would suggest one to confirm
        # (every result of a beamtime without one carried both). Flags are not hashed: no result id moves.
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
                if not not_named and not blocked and not j["disagree"]:  # nothing awaits an approval ISAAC does not
                    # propose (flags are not hashed)
                    flags.append("calibration_shift_awaiting_approval")
            elif blocked:
                pass  # r4-a: no reference is read (its flags say why); approval_not_applied names the approval
            elif own and not REF.shift_size_confirmed(accepted, shift):
                # CALIBRANT_RULE_ID: a group's own edge is a calibration only if its sample is a pure element, which
                # names cannot settle (a chemical standard's edge sits where its chemistry puts it, and moving it onto
                # a tabulated edge erases that chemical shift): applied only with --accept-shift, whatever the size
                flags.append(REF.CALIBRANT_NOT_CONFIRMED_FLAG)
            elif j["disagree"] and not REF.shift_size_confirmed(accepted, shift):
                # r4-a (SPREAD_RULE_ID): a reference whose usable edges disagree, applied only with --accept-shift
                flags.append(REF.SPREAD_NOT_CONFIRMED_FLAG)
            elif near is not None and not REF.shift_size_confirmed(accepted, shift):
                # r4-a (NEAR_SAMPLE_RULE_ID): the reference channel may be seeing the sample: applied only with its size
                # confirmed (--accept-shift), whatever the size
                flags.append(REF.NEAR_SAMPLE_NOT_CONFIRMED_FLAG)
            elif REF.exceeds_warn(shift, ctx.params["qc"]["warn_energy_shift_eV"]) and not REF.shift_size_confirmed(accepted, shift):
                # c12-cal (REF.SHIFT_SIZE_RULE_ID): a shift above the warning level moves every energy of the record by
                # that much; it is applied only when the scientist also confirmed its size (--accept-shift). c12-r: the
                # warning level is the protocol's or lower (REF.effective_warn_eV), never a params file's higher value
                flags.append(REF.SIZE_NOT_CONFIRMED_FLAG)
            elif cp.get("apply_shift_when_confirmed"):
                applied = shift
    if not_named and applied and REF.shift_size_confirmed(accepted, shift):
        # r3-b M2: the scientist confirmed this group's own edge (--accept-shift) and it is applied: its names no longer
        # stand in the way of anything (step flags are not hashed: no id moves)
        flags.remove(REF.NOT_NAMED_ELEMENT_FLAG)
    if approved:
        unconfirmed_reason = None
    elif proposed:
        unconfirmed_reason = "proposed_not_approved"
    confirmed = approved
    basis = approved or proposed
    per_scan_shifts = None
    # r4-a review: aligned only by usable edges (REF.judge: never a scan whose pre-edge noise is about zero)
    if cp.get("align_scans_by_reference") and j["usable"] and len(j["usable"]) == len(scans_data):
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
        # r4-a: written into the outcome by _said_reference, after the hashed copy (no id moves)
        "said": said,
    }


def _said_reference(cal: dict, calibrant: Mapping | None = None) -> dict:
    """``cal`` with what its reference reading says (:func:`reference.reading`: the usable / listed scan counts,
    whether a reference is proposed, a plain sentence, and a spread that is null with fewer than two usable scans)
    added to its outcome. Returns the outcome AS IT IS HASHED (params.json, qc.json): exactly the keys and values
    the step had before these sentences existed, so a group whose curve does not change keeps its result id.
    ``calibrant`` (a reference group's :func:`reference.calibrant_identity`) is said here too, never hashed."""
    hashed = copy.deepcopy(cal["outcome"])
    cal["outcome"].update(cal.pop("said", None) or {})  # r4-a: the sample E0 and spread level the reading uses
    if calibrant is not None and cal["outcome"].get("reference_source") == REF.OWN_SIGNAL:
        cal["outcome"]["reference_calibrant"] = dict(calibrant)
    said = REF.reading(cal)
    cal["outcome"].update({k: said[k] for k in ("reference_scans_usable", "reference_scans_listed", "reference_min_scans",
                                                "reference_proposed", "calibration_proposed", "reference_statement")})
    cal["outcome"].update({k: said[k] for k in ("reference_scans_degenerate", "reference_edges_disagree",
                                                "reference_at_sample_e0_eV") if k in said})
    o = cal["outcome"]
    passing = REF.judge(o.get("reference_e0_per_scan_eV") or [], o.get("reference_snr_per_scan") or [],
                        REF.effective_min_snr((cal.get("params") or {}).get("reference_min_edge_snr"), o.get("reference_source")),
                        o.get("reference_source"))["passing"]
    if said["reference_e0_spread_eV"] is None and len(passing) < 2:
        # one usable scan has no spread (c12-cal). r4-a: never nulled for scans the degenerate-noise rule set aside:
        # the QC verdict reads this value, and qc.json keeps the earlier rule's (an unchanged curve keeps its id)
        o["reference_e0_spread_eV"] = None
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


def _glitch_points_on_edge(points: Sequence[tuple[int, float, bool]], e0, names: Sequence[str], *,
                           one_scan: int = 0, few_scans: bool = False) -> dict | None:
    """r2-a: the flagged points on the edge (:func:`core.glitch_points_on_edge`), listed apart and said, or ``None``
    when no flagged point is on the edge (an unaffected result is unchanged). ``names`` are the used scans' file
    names by scan position. The stored count, flag and verdict are not changed (qc.json is hashed). r4-a:
    ``one_scan`` of the points given as off the edge lie on it but are one scan's glitches
    (:func:`core.glitch_points_from_one_scan`): said as counted glitches, never as off the edge.

    r5 A6: with ``few_scans`` (fewer than ``deglitch.min_scans_for_cross_scan`` scans: the check compares neighbouring
    points, ``glitch_check_few_scans``) NO flagged point is counted as a glitch, off the edge either: the sentence says
    every flag is unjudged, ``off_edge`` is ``None`` and ``unjudged`` counts them all. Measured on a real BL6-2c
    beamtime: the few-scan sentence said the flags were no evidence of glitches while this one counted the points off
    the edge as glitches, and ``glitch_points_off_edge`` gave that count."""
    edge = [(s, e) for s, e, on in points if on]
    if not edge:
        return None
    off = len(points) - len(edge) - one_scan
    shown = ", ".join(f"{e:.3f} eV ({names[s]})" for s, e in edge[:10]) + (f" and {len(edge) - 10} more" if len(edge) > 10 else "")
    e0_said = f" {float(e0):.3f} eV" if e0 is not None else ""
    off_said = (f"The other {off} flagged point{'' if off == 1 else 's'} {'is' if off == 1 else 'are'} off the edge and "
                "counted as glitches." if off else "No point off the edge is flagged.")
    if one_scan:
        off_said += (f" {one_scan} more on the edge {'is' if one_scan == 1 else 'are'} from one scan alone, far beyond "
                     "the other scans there, and counted as glitches (glitch_points_from_one_scan).")
    if few_scans:
        off_said = ((f"The other {off} flagged point{'' if off == 1 else 's'} {'is' if off == 1 else 'are'} off the "
                     "edge, but with this few scans the check cannot judge those either (glitch_check_few_scans): none "
                     f"of the {len(points)} flagged points is counted as a glitch.") if off else
                    "No point off the edge is flagged.")
    return {
        "on_edge": len(edge), "off_edge": None if few_scans else off,
        **({"unjudged": len(points)} if few_scans else {}),
        "listed": [{"scan_position": s, "energy_eV": e} for s, e in edge[:200]],
        "statement": (f"{len(edge)} of the {len(points)} flagged point{'' if len(points) == 1 else 's'} "
                      f"{'lies' if len(edge) == 1 else 'lie'} on the edge "
                      f"(within {C.GLITCH_EDGE_WINDOW_EV:g} eV of E0{e0_said}, or in the steep stretch of the edge): "
                      f"the check cannot judge {'it' if len(edge) == 1 else 'them'}, since it cannot tell a glitch from "
                      f"the steep edge there: {shown}. They are neither counted as glitches nor cleared. {off_said} "
                      "The stored verdict keeps glitches_flagged as it was first written; look at the plot near E0."),
    }


def _one_scan_glitch_statement(points: Sequence[tuple[int, float]], names: Sequence[str], e0) -> str:
    """r4-a: the flagged points on the edge that are one scan's glitches, not the edge
    (:func:`core.glitch_points_from_one_scan`), by file, said apart from the points the check cannot judge."""
    by_scan: dict[int, list[float]] = {}
    for s, e in points:
        by_scan.setdefault(s, []).append(e)
    parts = [f"{names[s]} ({_n_points(len(es))}, {min(es):.1f} to {max(es):.1f} eV)" for s, es in sorted(by_scan.items())]
    e0_said = f" {float(e0):.3f} eV" if e0 is not None else ""
    n = len(points)
    return (f"{n} flagged point{'' if n == 1 else 's'} on the edge (near E0{e0_said} or in its steep stretch) "
            f"{'comes' if n == 1 else 'come'} from one scan alone: {'; '.join(parts[:10])}. There that scan departs from "
            f"the median of the scans more than {C.GLITCH_ONE_SCAN_FACTOR:g} times as far as any other scan does, and by "
            f"more than {C.GLITCH_ONE_SCAN_SPAN_FRACTION:.0%} of the median curve's whole range: a glitch in that scan, not "
            "the edge, so these points are counted as glitches. Look at that scan in the plot and ask the scientist "
            "whether it belongs in the merge.")


def _n_points(n: int) -> str:
    return f"{n} point{'' if n == 1 else 's'}"


#: r4-a: the review flag (and the QC fail reason) of a merged curve one scan's stretch sets (core.SINGLE_SCAN_RULE_ID)
SINGLE_SCAN_FLAG = "edge_from_single_scan"


def _single_scan_statement(dominant: Mapping, names: Sequence[str], group_id: str, excluded_as: str) -> str:
    """r4-a: the plain sentence for a merged curve whose range one scan's stretch sets (:func:`core.single_scan_dominance`),
    naming the scan by its file and saying how to leave it out (:func:`exclude_hint`)."""
    name = names[dominant["scan_position"]]
    lo, hi = dominant["departs_eV"]
    where = f"from {lo:.1f} to {hi:.1f} eV" if hi > lo else f"at {lo:.1f} eV"
    # r4-a review: said by WHERE the scan departs (the others' steepest point is the edge)
    what = {"edge": "the merged white line, edge step and E0 come from that scan's stretch",
            "above_edge": ("that stretch lies above the edge, so the merged post-edge, and with it the edge step and the "
                           "normalised curve, come from that scan there"),
            "below_edge": ("that stretch lies below the edge, so the merged pre-edge, and with it the edge step and the "
                           "normalised curve, come from that scan there")}[dominant.get("region") or "edge"]
    return (f"One scan sets this merged curve: with {name} left out, the merged curve's range (max - min) is "
            f"{dominant['span_without_scan']:.4g}; with it, {dominant['span_merged']:.4g}, "
            f"{dominant['ratio']:.3g} times as large (more than {dominant['factor']:g} times is one scan, not a merge). "
            f"{name} departs from the other scans only {where} "
            f"({_n_points(dominant['departs_points'])} of {dominant['points']}), measured in each curve's own edge "
            f"steps; {what}, not from the measurement: this curve is not usable as it is. Ask the "
            "scientist whether that scan belongs in the merge. " + exclude_hint(group_id, [excluded_as]))


#: r4-a review: the statement (and review flag) of a group whose other scans have no edge (core.single_scan_dominance)
ONLY_EDGE_FLAG = "only_scan_with_edge"


def _only_edge_statement(dominant: Mapping, names: Sequence[str]) -> str:
    """r4-a review: one scan has an edge and the others none: said, never failed, and never "leave it out"."""
    name = names[dominant["scan_position"]]
    others = len(names) - 1
    return (f"{name} is the group's only scan with an edge: the other {_n(others, 'scan')} show no edge (dead, out of "
            f"the beam or dark counts), so the merged curve is {name}'s, averaged with {'that scan' if others == 1 else 'them'} "
            f"(its range is {dominant['ratio']:.3g} times theirs). The sentences on zero or missing signal "
            "(merged_scan_zero_signal_points, outlier_scans) say which scans recorded nothing; ask the scientist "
            f"whether {'that scan belongs' if others == 1 else 'those scans belong'} in the merge.")


def _n(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


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


#: r4-a M6: the skip reason (and review flag, and statement key) of a scan a params file leaves out of the merge
EXCLUDED_REASON = "scans_excluded_by_params_file"


def _excluded_as(entry: Mapping, names: Sequence[str]) -> str | None:
    """The ``exclude_scans`` name (:data:`protocol.EXCLUDE_SCANS_SECTION`) that names this input, else ``None``: its
    source id, relative path or file name, optionally with ``#<scan number>`` for one scan of a multi-scan file."""
    if not names:
        return None
    rel = str(entry.get("relative_path") or "")
    own = {str(entry.get("source_id") or ""), rel, PurePosixPath(rel).name} - {""}

    def _clean(x: str) -> str:
        x = x.strip()
        return x[2:] if x.startswith("./") else x

    for name in names:
        # r4-a review: the whole name first (a file name may hold a '#'), then <name>#<scan> (spaces allowed)
        if _clean(name) in own:
            return name
        if "#" in name:
            base, _, scan = name.rpartition("#")
            if (_clean(base) in own and scan.strip() and entry.get("scan") is not None
                    and scan.strip().lstrip("0") == str(entry["scan"]).lstrip("0")):
                return name
    return None


def exclusion_name(entry: Mapping, inputs: Sequence[Mapping]) -> str:
    """How ``exclude_scans`` names one input so that it names that input alone: its file name; its relative path when
    another input of the group has the same file name in another folder (``day1/x.dat``, ``day2/x.dat``); and
    ``#<scan>`` when another input shares the file."""
    name = _file_name(entry)
    rel = str(entry.get("relative_path") or "")
    if any(_file_name(i) == name and str(i.get("relative_path") or "") != rel for i in inputs):
        name = rel or name
    shared = sum(1 for i in inputs if str(i.get("relative_path") or "") == rel) > 1
    return f"{name}#{entry['scan']}" if shared and entry.get("scan") is not None else name


def exclude_hint(group_id: str, names: Sequence[str]) -> str:
    """r4-a M6: how to leave named scans out of a group's merge: the params file's exact shape and the command."""
    one = len(names) == 1
    listed = ", ".join(json.dumps(n) for n in names)
    return (f"If the scientist says {'it does' if one else 'they do'} not belong in the merge, re-process the group with a "
            f"params file {{\"{P.EXCLUDE_SCANS_SECTION}\": {{\"{group_id}\": [{listed}]}}}}: `isaac process "
            f"<bundle_dir> --source <the beamtime folder you imported> --group {group_id} --params-file <that file>`. "
            f"That gives a new result without {'it' if one else 'them'} to review; this one stays as it is.")


def _exclusion_statement(excluded: Sequence[Mapping], names: Sequence[str], listed: int, used: int) -> str | None:
    """r4-a M6: which scans the params file left out of this group's merge, and any name that matched none of its
    scans (``None`` when the params file names none for this group)."""
    if not names:
        return None
    found = {x["named_as"] for x in excluded}
    missing = [n for n in names if n not in found]
    said = ""
    if excluded:
        k = len(excluded)
        base = [PurePosixPath(str(x["relative_path"] or x["source_id"])).name for x in excluded]
        # r4-a review: by relative path when file names repeat across folders
        shown = [str(x["relative_path"] or x["source_id"]) if base.count(b) > 1 else b for x, b in zip(excluded, base)]
        files = ", ".join(n + (f" (scan {x['scan']})" if x.get("scan") is not None else "")
                          for n, x in zip(shown[:10], excluded[:10]))
        files += f" and {k - 10} more" if k > 10 else ""
        said = (f"{k} of {listed} listed scans {'was' if k == 1 else 'were'} left out of the merge by the params file "
                f"({P.EXCLUDE_SCANS_SECTION}): {files}. "
                + (f"The curve merges {used} scan{'' if used == 1 else 's'}" if used else
                   "No scan is left, so there is no curve")
                + "; the group's earlier result, with every scan, stays as it was.")
    if missing:
        said += (" " if said else "") + (
            f"The params file's {P.EXCLUDE_SCANS_SECTION} names {', '.join(repr(n) for n in missing)} for this group, "
            "which matches none of its scans (a file name, relative path or source id, optionally #<scan>): nothing "
            "was left out for it. Check the name.")
    many = {n: [x for x in excluded if x["named_as"] == n] for n in found}
    for n, xs in many.items():
        if len(xs) > 1:
            # r4-a review: one name that left out more than one scan (a file name repeated across folders, or a
            # multi-scan file named without #<scan>) is said, so it is never more than the scientist meant
            said += (f" The name {n!r} matched {len(xs)} scans ("
                     + ", ".join(str(x["relative_path"] or x["source_id"]) + (f" scan {x['scan']}" if x.get("scan") is not None else "")
                                 for x in xs[:5])
                     + "); if only one was meant, name it by its relative path, or with #<scan>.")
    return said


#: r3-b M4: a merged scan's point departs from the other scans' median by more than this fraction of that median's span
OUTLIER_DEPARTS_FRACTION = 0.1


def _outlier_scans_statement(scan_flags: Sequence[bool], used_entries: Sequence[Mapping], grid, M, merged,
                             excluded: bool, np, *, group_id: str | None = None,
                             inputs: Sequence[Mapping] = ()) -> str | None:
    """r3-b M4: one plain statement naming each scan the deglitch step flagged as an OUTLIER (its deviation from the
    group's median spectrum is far above the others'), by its FILE, with the energy range where it departs from the
    other scans' median (by more than :data:`OUTLIER_DEPARTS_FRACTION` of that median's span), its signal there as a
    share of theirs, and what merging it did to the merged curve there; it asks whether the scan belongs in the merge.
    ``None`` when no scan is flagged. Measured on a real BL4-3 Ti beamtime: one scan's signal fell to about 0.05 after
    4985 eV and the merge was about 30% low there, said only as a count (``outlier_scans_flagged``). Descriptive only:
    nothing is skipped or changed for it. Said after the run id (qc.json is hashed), so no result id moves. r4-a M6:
    with ``group_id``, how to leave the scans out (:func:`exclude_hint`)."""
    flagged = [k for k, f in enumerate(scan_flags) if f]
    if not flagged:
        return None
    n = M.shape[0]
    parts = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for k in flagged:
            others = [j for j in range(n) if j != k and not scan_flags[j]] or [j for j in range(n) if j != k]
            if not others:
                continue
            ref = np.nanmedian(M[others], axis=0)
            mine = np.isfinite(M[k])
            ok = mine & np.isfinite(ref)
            name = _file_name(used_entries[k])
            if not ok.any():
                continue
            span = float(np.nanmax(ref[ok]) - np.nanmin(ref[ok])) or 1.0
            away = ok & (np.abs(M[k] - ref) > OUTLIER_DEPARTS_FRACTION * span)
            if not away.any():
                lo, hi = float(grid[mine][0]), float(grid[mine][-1])
                parts.append(f"{name} ({lo:.1f}-{hi:.1f} eV) differs from the other scans more than they differ from "
                             "each other, though nowhere by more than a tenth of the edge's height.")
                continue
            idx = np.flatnonzero(away)
            lo, hi = float(grid[idx[0]]), float(grid[idx[-1]])
            nonzero = away & (np.abs(ref) > 0)
            share = float(np.median(M[k][nonzero] / ref[nonzero])) if nonzero.any() else None
            said = (f"{name} departs from the other scans' median from {lo:.1f} to {hi:.1f} eV ({int(away.sum())} of its "
                    f"{int(mine.sum())} points)" + (f": its signal there is about {share * 100:.0f}% of theirs" if share is not None else ""))
            fin = nonzero & np.isfinite(merged)
            if excluded:
                said += "; it is left out of the merge (deglitch.exclude_flagged)."
            elif fin.any():
                effect = float(np.median(merged[fin] / ref[fin]) - 1.0)
                said += (f"; it is merged unchanged, so the merged curve there is about {abs(effect) * 100:.0f}% "
                         f"{'lower' if effect < 0 else 'higher'} than the other scans' median.")
            else:
                said += "; it is merged unchanged."
            parts.append(said)
    if not parts:
        return None
    more = f" {len(parts) - 10} more flagged scan(s) are said in the deglitch step." if len(parts) > 10 else ""
    one = len(flagged) == 1
    hint = (" " + exclude_hint(group_id, [exclusion_name(used_entries[k], inputs or used_entries) for k in flagged])
            if group_id and not excluded else "")
    return (" ".join(parts[:10]) + more + f" Ask the scientist whether {'this scan belongs' if one else 'these scans belong'} "
            "in the merge (a beam loss, a sample that moved or a detector that stopped counting would not)." + hint)


def _scan_name(entry: Mapping) -> str:
    return f"{entry.get('source_id')} (scan {entry['scan']})" if entry.get("scan") is not None else str(entry.get("source_id"))


def _scan_file(entry: Mapping) -> str:
    """r5f L2: a scan as a person knows it: the file's path in the beamtime folder (the source id only when no path is
    recorded), with ``(scan N)`` when the file holds more than one."""
    name = str(entry.get("relative_path") or entry.get("source_id"))
    return f"{name} (scan {entry['scan']})" if entry.get("scan") is not None else name


def _more_points_elsewhere(res: Mapping, points: int) -> int:
    """How many scans left OUT of the merge have more than ``points`` points (read): processing again might use them."""
    return sum(1 for i in res.get("inputs") or () if not i.get("used")
               and int((i.get("diagnostics") or {}).get("points_read") or 0) > points)


def _too_few_common_statement(res: Mapping, scans_used: int, points: int, minimum: int) -> str:
    """r5f L1: one plain sentence for a group whose scans share too few points to merge: how many scans it lists and
    used, how many points they have, and (only when it is true) that processing again cannot add points. It is true
    when one scan is used, or when no scan left out has more points than these; else the scans left out are named."""
    listed = len(res.get("inputs") or ())
    lead = f"{scans_used} of {listed} listed scan{'' if listed == 1 else 's'} {'was' if scans_used == 1 else 'were'} used"
    have = (f"it has {points} usable point{'' if points == 1 else 's'}" if scans_used == 1
            else f"they share {points} point{'' if points == 1 else 's'} on a common energy grid")
    more = _more_points_elsewhere(res, points)
    tail = ("Processing the group again with other parameters cannot add points the scans do not have."
            if scans_used == 1 or not more else
            f"{more} scan{' left' if more == 1 else 's left'} out of the merge ha{'s' if more == 1 else 've'} more points (see "
            "inputs): processing again with other parameters might use them.")
    return (f"{lead}, and {have}; the merge needs at least {minimum}. No merged curve was made, so there is nothing "
            f"to approve. {tail}")


def _fail_too_few_common(res: dict, scans_used: int, points: int, minimum: int) -> dict:
    """:func:`_fail` ``too_few_common_points`` plus its statement and scan counts (said after the id is fixed: the id
    of a failure comes from its code and detail only, so none moves). ``reprocess_cannot_help`` (a metric) is what the
    remedies read: they offer re-processing unless it is true."""
    out = _fail(res, "too_few_common_points", str(points))
    out["qc"]["metrics"] = {**out["qc"].get("metrics", {}), "scans_listed": len(res.get("inputs") or ()),
                            "scans_used": scans_used, "common_points": points,
                            "reprocess_cannot_help": scans_used == 1 or not _more_points_elsewhere(res, points)}
    out["qc"]["statements"] = {"too_few_common_points": _too_few_common_statement(res, scans_used, points, minimum)}
    return out


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


def _no_usable_scan_statement(inputs: Sequence[Mapping], too_few: Sequence[int], *, signal: str | None = None,
                              transmission: bool = False) -> str | None:
    """c10-m: one plain sentence when NO scan could be used because scans have too few points (``None`` when none
    did): "The only scan has 2 usable points; at least 5 are needed". Scans skipped for other reasons are counted.
    c11-a: when no scan has too few points but every one's signal is zero at every point, that is said instead.
    r3-b L4: when no scan has too few points and scans were skipped ``signal_not_finite`` (the beam off, I0 negative),
    that is said: how many points are not finite and at how many I0 is zero or negative."""
    nonfinite = [i for i in inputs if i.get("skip_reason") == C.SIGNAL_NOT_FINITE]
    if not too_few and nonfinite:
        diags = [i.get("diagnostics") or {} for i in nonfinite]
        dropped = sum(int(d.get("nonfinite_dropped") or 0) for d in diags)
        read = sum(int(d.get("points_read") or 0) for d in diags)
        i0 = [int(d["i0_nonpositive"]) for d in diags if d.get("i0_nonpositive") is not None]
        k, n = len(nonfinite), len(inputs)
        named = f"signal ({signal})" if signal else "signal"
        who = ("The only scan's" if n == 1 else
               f"In {'both scans' if k == n == 2 else f'all {k} scans' if k == n else f'{k} of the {n} scans'}, the")
        needs = f"I0 and {signal}" if transmission and signal else "I0"
        said = (f"{who} {named} is not a finite number at {dropped} of {read} points"
                + (f"; I0 is zero or negative at {sum(i0)} of them" if i0 and sum(i0) else "")
                + f" (the absorption is computed only where {needs} {'are' if ' and ' in needs else 'is'} above zero), so "
                "there is no curve to process. A beam that was off or a detector that was not counting gives this; a "
                "person checks the scan" + ("s" if k > 1 else ""))
        other = n - k
        return said + (f". {other} more {'scan was' if other == 1 else 'scans were'} skipped for other reasons (see "
                       "inputs)." if other else ".")
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
#: c12-r: a run of zeros whose counts come back is said as a possible lost beam (with the flag) when it is at least
#: this fraction of the scan's points and at least BEAM_LOSS_MIN_POINTS long; runs of 1-2 points are isolated
#: dropouts; anything between is counted without a claim. Measured on the real BL15-2 beamtimes (docs/xas-processing-
#: protocol-v0.md section 5): recovering runs in 2021-11 were at most 11 points of 226 (4.9 %); in 2025-04 runs of
#: 25 of 46 and 30 of 74 points recovered.
ZERO_RUNS_RULE_ID = "isaac.xas.zero_signal_runs.v0"
BEAM_LOSS_MIN_FRACTION = 0.05
BEAM_LOSS_MIN_POINTS = 3
ISOLATED_MAX_POINTS = 2


def _long_runs(z: Mapping) -> list[tuple[int, int]]:
    """The ``(start, length)`` runs of zeros of one scan (:func:`_zero_scans`) that do NOT reach its end and are long
    enough to be said as a possible lost beam (:data:`BEAM_LOSS_MIN_FRACTION`, :data:`BEAM_LOSS_MIN_POINTS`)."""
    size = z["size"]
    return [(st, n) for st, n in z["runs"] if st + n < size and n >= BEAM_LOSS_MIN_POINTS and n >= BEAM_LOSS_MIN_FRACTION * size]


def _zero_signal_points_statement(used_entries: Sequence[Mapping], scans_data: Sequence[Mapping], signal: str | None,
                                  np, *, group_id: str | None = None, inputs: Sequence[Mapping] = ()) -> str | None:
    """c11-r: one plain statement naming each MERGED scan whose counts STOP (its signal is exactly zero from some point
    to the scan's last point, a run of at least two points) or, c12-r, DROP OUT FOR A WHILE (a run of zeros at least
    :data:`BEAM_LOSS_MIN_FRACTION` of the scan and :data:`BEAM_LOSS_MIN_POINTS` long, whose counts come back), where
    another merged scan's signal is not zero (at the other scan's nearest point within its energy range); ``None``
    otherwise. Shorter runs whose counts come back are counted apart (:func:`_isolated_zero_points_statement`,
    :func:`_short_zero_runs_statement`), never said as a lost beam. Descriptive only: nothing is skipped or changed
    for it (whether such a scan belongs in the merge is the scientist's call, docs/xas-processing-protocol-v0.md).
    Said in the result, NOT in qc.json (hashed into the run id), so no result id moves. r4-a M6: with ``group_id``, how
    to leave those scans out (:func:`exclude_hint`)."""
    parts, said_entries = [], []
    for entry, sa, z in _zero_scans(used_entries, scans_data, np):
        trail = z["trailing"] if z["trailing"] >= 2 else 0
        long_runs = _long_runs(z)
        if not trail and not long_runs:
            continue
        d = sa["diagnostics"]
        name = PurePosixPath(str(entry.get("relative_path") or entry.get("source_id"))).name
        named = f"signal ({signal})" if signal else "signal"
        e = sa["energy"]
        where = [f"from {z['trailing_from_eV']:.1f} eV on"] if trail else []
        where += [f"{n} in a row from {e[st]:.1f} to {e[st + n - 1]:.1f} eV, after which the counts come back"
                  for st, n in long_runs[:3]]
        if len(long_runs) > 3:
            where.append(f"{len(long_runs) - 3} more such run{'' if len(long_runs) == 4 else 's'}")
        others = z["n"] - trail - sum(n for _, n in long_runs)
        extra = f", and at {others} other point{'' if others == 1 else 's'}" if others else ""
        parts.append(f"{name}'s {named} is zero at {d.get('signal_zero_points', z['n'])} of "
                     f"{d.get('points_read', z['size'])} points ({'; '.join(where)}{extra}); it is merged unchanged.")
        said_entries.append(entry)
    if not parts:
        return None
    more = f" {len(parts) - 10} more merged scan(s) are the same." if len(parts) > 10 else ""
    hint = (" " + exclude_hint(group_id, [exclusion_name(e, inputs or used_entries) for e in said_entries])
            if group_id else "")
    return " ".join(parts[:10]) + more + " A person checks whether the beam was lost." + hint


def _zero_scans(used_entries: Sequence[Mapping], scans_data: Sequence[Mapping], np) -> list[tuple[Mapping, Mapping, dict]]:
    """Each merged scan whose signal is exactly zero at points where another merged scan's is not: ``(entry, scan,
    {n, size, trailing, trailing_from_eV, longest, runs})`` — ``trailing`` is the length of the run of zeros that ends
    at the scan's last point (0 when the last point is not zero), ``longest`` its longest run of consecutive zeros,
    ``runs`` every run as ``(start index, length)``."""
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
                                "longest": int(max(r.size for r in runs)),
                                "runs": [(int(r[0]), int(r.size)) for r in runs]}))
    return out


def _recovering_runs(z: Mapping) -> list[int]:
    """The lengths of one scan's zero runs that are said in neither lost-beam form (the counts come back and the run is
    shorter than :func:`_long_runs`; a single zero at the very last point counts here too)."""
    size, long_ = z["size"], set(_long_runs(z))
    trail_said = z["trailing"] >= 2
    return [n for st, n in z["runs"] if (st, n) not in long_ and not (trail_said and st + n == size)]


def _isolated_zero_points_statement(used_entries: Sequence[Mapping], scans_data: Sequence[Mapping], signal: str | None,
                                    np) -> str | None:
    """c12-cal: ONE count line for the merged scans whose signal is exactly zero at ISOLATED points (runs of 1 or 2,
    :data:`ISOLATED_MAX_POINTS`) where another's is not and whose counts come back: dropouts, said like glitches, with
    no beam-loss wording and no review flag. Measured on a real BL15-2 beamtime: 441 merged scans of 70 groups had such
    points, 414 at only 1-5 points, I0 positive at all of them; the one scan whose counts stopped (zero at 204 of 226
    points to its end) was buried among them. c12-r: longer runs are never in this line (they are counted by
    :func:`_short_zero_runs_statement` or said by :func:`_zero_signal_points_statement`). ``None`` when there is none.
    Said after the run id (no id moves)."""
    rows = []
    for _, _, z in _zero_scans(used_entries, scans_data, np):
        runs = [n for n in _recovering_runs(z) if n <= ISOLATED_MAX_POINTS]
        if runs:
            rows.append((sum(runs), max(runs)))
    if not rows:
        return None
    named = f"signal ({signal})" if signal else "signal"
    k, total = len(rows), sum(n for n, _ in rows)
    longest = max(lng for _, lng in rows)
    return (f"{k} merged scan{'' if k == 1 else 's'} {'has' if k == 1 else 'have'} isolated points where the {named} "
            f"is exactly zero while another scan's is not ({total} point{'' if total == 1 else 's'} in all, at most "
            f"{longest} in a row); the counts come back after each, so they read as detector dropouts, like glitches. "
            "They are merged unchanged.")


def _short_zero_runs_statement(used_entries: Sequence[Mapping], scans_data: Sequence[Mapping], signal: str | None,
                               np) -> str | None:
    """c12-r: ONE count line for the runs of zeros longer than isolated points but shorter than a possible lost beam
    (3 points or more, under :data:`BEAM_LOSS_MIN_FRACTION` of the scan) whose counts come back: counted with no claim
    of what they are (a dropout or a brief loss of beam cannot be told from the data) and no flag. ``None`` when there
    is none. Said after the run id (no id moves)."""
    rows = []
    for _, _, z in _zero_scans(used_entries, scans_data, np):
        runs = [n for n in _recovering_runs(z) if n > ISOLATED_MAX_POINTS]
        if runs:
            rows.append(runs)
    if not rows:
        return None
    named = f"signal ({signal})" if signal else "signal"
    k, n_runs = len(rows), sum(len(r) for r in rows)
    total, longest = sum(sum(r) for r in rows), max(max(r) for r in rows)
    return (f"{k} merged scan{'' if k == 1 else 's'} {'has' if k == 1 else 'have'} {n_runs} short run"
            f"{'' if n_runs == 1 else 's'} of points where the {named} is exactly zero while another scan's is not "
            f"({total} points in all, {ISOLATED_MAX_POINTS + 1} or more and at most {longest} in a row, each run "
            f"under {BEAM_LOSS_MIN_FRACTION:.0%} of its scan); the counts come back after each. They are merged unchanged.")


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


#: r5 A5: THE ABORTED FRAGMENT (``isaac.xas.skip_aborted_scan_fragment.v0``). A usable scan with fewer points than
#: ``merge.min_points``, in a group where another usable scan has at least that many, is a scan that stopped early: it
#: is left out of the merge (skip reason :data:`FRAGMENT_REASON`), counted (metric and warn
#: ``scans_skipped_aborted_fragment``) and named. Measured on a real BL15-2 beamtime: a 6-point scan beside two of 222
#: was merged into the curve (one of eight such scans of 6 to 18 points in 610). When no scan has enough points nothing
#: is left out (the merge then fails as before).
FRAGMENT_RULE_ID = "isaac.xas.skip_aborted_scan_fragment.v0"
FRAGMENT_REASON = "aborted_scan_fragment"


def _aborted_fragments(arrays: Sequence[Mapping], min_points: int) -> set[int]:
    """The positions (in ``arrays``, the usable scans) of the aborted fragments (:data:`FRAGMENT_RULE_ID`)."""
    sizes = [int(sa["energy"].size) for sa in arrays]
    if not sizes or max(sizes) < min_points:
        return set()
    return {k for k, n in enumerate(sizes) if n < min_points}


def _fragments_statement(inputs: Sequence[Mapping], used: int, min_points: int) -> str | None:
    """r5 A5: the sentence for the scans left out as aborted fragments (``None`` when there is none)."""
    frags = [i for i in inputs if i.get("skip_reason") == FRAGMENT_REASON]
    if not frags:
        return None
    sizes = [int((i.get("diagnostics") or {}).get("points_used") or 0) for i in frags]
    full = [int((i.get("diagnostics") or {}).get("points_used") or 0) for i in inputs if i.get("used")]
    k = len(frags)
    named = ", ".join(f"{_file_name(i)} ({_n_points(n)})" for i, n in list(zip(frags, sizes))[:10])
    named += f" and {k - 10} more" if k > 10 else ""
    others = (f"{min(full)}" if min(full) == max(full) else f"{min(full)} to {max(full)}") if full else "more"
    return (f"{used} of {len(inputs)} listed scans were merged. {k} {'scan' if k == 1 else 'scans'} stopped early and "
            f"{'was' if k == 1 else 'were'} left out of the merge as {'an aborted fragment' if k == 1 else 'aborted fragments'}: "
            f"{named}. A merge needs at least {min_points} points, and the merged scans have {others}. A person checks "
            f"that {'the scan was' if k == 1 else 'these scans were'} stopped, not a short scan meant to be kept.")


#: r5 A5: the points a scan skipped as ``too_few_points`` read and kept (on its input entry)
TOO_FEW_POINTS_KEY = "too_few_points"

#: r5 A5: how a SPEC file's scan line names its scan (``#S 3  ascan  Sz -23.7 -19.7  30 0.3`` -> ``ascan Sz``).
_SPEC_SCAN_LINE = re.compile(r"^#S\s+\d+\s+(\w+)\s+([^\s]+)")


def _scan_command(header_lines: Sequence[str]) -> str | None:
    """The scan command and its first argument a SPEC ``#S`` line states (``ascan Sz``), or ``None``."""
    for line in header_lines or ():
        m = _SPEC_SCAN_LINE.match(str(line).strip())
        if m:
            return f"{m.group(1)} {m.group(2)}"
    return None


def _too_few_points_statement(inputs: Sequence[Mapping], used: int, energy: str | None,
                              header_of: Mapping[int, Sequence[str]]) -> str | None:
    """r5 A5: one plain sentence on the scans skipped as ``too_few_points`` (``None`` when none was): which are NOT
    ENERGY SCANS (at least :data:`core.MIN_SCAN_POINTS` points read, but the energy column holds fewer distinct values:
    something else was scanned, e.g. a motor or the emission energy; the SPEC scan line is quoted when there is one) and
    which stopped after too few points. Said after the run id (no id moves). Measured on a real BL15-2 beamtime: 30
    scans, most of them sample-motor and emission ``ascan``s whose energy column held one value, were skipped with no
    word on what they were."""
    few = [i for i in inputs if i.get("skip_reason") == "too_few_points"]
    if not few:
        return None
    flat, short = [], []
    for i in few:
        d = i.get(TOO_FEW_POINTS_KEY) or {}
        read, kept = int(d.get("points_read") or 0), int(d.get("points_used") or 0)
        (flat if read >= C.MIN_SCAN_POINTS and kept < C.MIN_SCAN_POINTS else short).append((i, read, kept))
    parts = []
    col = f"the energy column ({energy})" if energy else "the energy column"
    if flat:
        k = len(flat)
        kept = sorted({x[2] for x in flat})
        read = sorted({x[1] for x in flat})
        cmds = sorted({c for c in (_scan_command(header_of.get(id(x[0])) or ()) for x in flat) if c})
        values = f"{kept[0]}" if len(kept) == 1 else f"{kept[0]} to {kept[-1]}"
        points = f"{read[0]}" if len(read) == 1 else f"{read[0]} to {read[-1]}"
        names = ", ".join(_file_name(x[0]) for x in flat[:10]) + (f" and {k - 10} more" if k > 10 else "")
        parts.append(f"{k} {'is not an energy scan' if k == 1 else 'are not energy scans'}: {col} holds only {values} "
                     f"distinct value{'' if values == '1' else 's'} over {points} points, so something else was scanned"
                     + (f" (the file{'' if k == 1 else 's'} say{'s' if k == 1 else ''}: {', '.join(cmds[:6])})" if cmds else "")
                     + f": {names}")
    if short:
        k = len(short)
        names = ", ".join(f"{_file_name(x[0])} ({_n_points(x[2])})" for x in short[:10]) + (f" and {k - 10} more" if k > 10 else "")
        parts.append(f"{k} stopped after fewer than {C.MIN_SCAN_POINTS} usable points "
                     f"({'an aborted scan' if k == 1 else 'aborted scans'}): {names}")
    k = len(few)
    lead = (f"{used} of {len(inputs)} listed scans were used; {k} {'was' if k == 1 else 'were'} left out because "
            f"{'it has' if k == 1 else 'they have'} too few points.")
    return (f"{lead} " + "; ".join(parts) + f". A person confirms {'it does' if k == 1 else 'they do'} not belong in "
            "this record.")


def _skipped_scans_statement(inputs: Sequence[Mapping], choice, used: int) -> str | None:
    """One plain sentence when readable scans of the group were left out because they lack the chosen
    columns (``None`` otherwise): how many of the listed scans were used, which were not, and why. Added to
    ``qc.statements`` AFTER the run id is fixed (``qc.json`` is hashed into it), so no result id moves."""
    lacking = [i for i in inputs if i.get("skip_reason") == "scan_lacks_chosen_columns"]
    if not lacking:
        return None
    k = len(lacking)
    # r5f L2: the file, as the other statements name it (never the source id): its path in the beamtime folder
    names = ", ".join(_scan_file(i) for i in lacking[:10]) + (f" and {k - 10} more" if k > 10 else "")
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
    if entry.get("_match_kind") in ("scientist_merge", A.TIED_KIND):
        # r3-b H3: the scientist's merge named after one run, or after the group's base name (every run); r6 G1: a
        # group the scientist named for this group (params athena_match) covers every run of it
        runs = [s for s in group_runs if A.normalise_name(s) in set(entry.get("_merge_of") or ())]
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
        if members.get("runs"):
            # r3-b H3: members of several runs (scan numbers restart in each run): each run's scans named apart
            by_run: dict[str, list[int]] = {}
            for run_, n in zip(members["runs"], scans):
                by_run.setdefault(run_, []).append(n)
            each = " and ".join(f"scan{'s' if len(v) > 1 else ''} {_scans_phrase(v)} of run {k}" for k, v in by_run.items())
            said = (f"The scientist's curve is ISAAC's mean of {len(scans)} per-scan Athena groups, one each for {each} "
                    f"(read from their labels).{ours}{part}")
        else:
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
    merge_of = ([x for x in stems if A.normalise_name(x) in set(entry.get("_merge_of") or ())]
                if entry.get("_match_kind") == "scientist_merge" else None)
    tied = entry.get("_match_kind") == A.TIED_KIND
    said = (f"The project does not say which scans the scientist's curve used: its Athena label '{label}' names no scan"
            + (", though Athena marks the group as a merge" if entry.get("is_merge") else "")
            # r3-b H3: a merge named before the run or base name (athena.SCIENTIST_MERGE_RULE_ID) is the scientist's merge
            + (f"; its label names it the scientist's merge of {'run' if len(merge_of) == 1 else 'runs'} "
               f"{', '.join(merge_of)} ({A.SCIENTIST_MERGE_RULE_ID})" if merge_of and not coverage else "")
            # r6 G1: matched because the scientist named it for this group, never by a near name
            + ("; the scientist named it as this group's in the params file's athena_match (its name is not this "
               "group's scan name)" if tied else "")
            + (", and the project does not name its source file" if unnamed else
               f", and it records the group as made from the file '{made_from}'" if made_from.casefold() != label.casefold() else "")
            + (f"; {'it is named for' if tied else 'its name names'} run{'s' if len(coverage['runs']) > 1 else ''} "
               f"{', '.join(coverage['runs'])}" if coverage else "")
            + f".{ours}{part} Ask the scientist which scans went into it.")
    return {"basis": "not_stated", "scans": None, "statement": said}


#: r3-d: the statement (``qc.statements``) of an Athena result whose per-scan groups beside its merge were set aside
SET_ASIDE_STATEMENT = "athena_per_scan_set_set_aside"
#: r3-d: the scientist's merge differs from the mean of a per-scan set beside it that covers every scan of the group
MERGE_DIFFERS_FROM_SET_FLAG = "athena_merge_differs_from_per_scan_set"
MERGE_OR_SET_QUESTION = "athena_merge_or_per_scan_set"


def _sets_aside(entry: Mapping, stems: Sequence[str], inputs: Sequence[Mapping], numbers: Sequence[int | None],
                stem_of: Mapping[str, str], params: Mapping, np) -> dict | None:
    """r3-d: what the per-scan sets set aside beside the scientist's merge (``athena.match_with_versions``,
    ``_sets_aside``) are: each listed with its provenance (:func:`athena.version_provenance`), whether it covers every
    scan of the group (each listed scan's run and number among its members'; never when a number is unknown) and, when
    it does, the merge compared with its mean (:func:`athena.merge_versus_set`). ``differs``: such a comparison differs
    beyond the comparison's tolerances. ``None`` when nothing was set aside."""
    sets = list(entry.get("_sets_aside") or ())
    if not sets:
        return None
    one = A.normalise_name(stems[0]) if len({A.normalise_name(x) for x in stems if x}) == 1 else None
    known = B.all_scan_numbers_known(numbers)
    group = ({(A.normalise_name(stem_of.get(i.get("source_id")) or "") or one, n) for i, n in zip(inputs, numbers)}
             if known else set())
    label, listed, said, differs = entry["label"], [], [], False
    for v in sets:
        members = v["per_scan_set"]
        have = set()
        for lab in members["labels"]:
            got = A._selection_of_run(lab, stems)
            if got is not None:
                have.add((A.normalise_name(stems[got[0]]), got[1][0]))
        covers = bool(group) and None not in {g[0] for g in group} and group <= have
        n = len(members["labels"])
        prj = PurePosixPath(str(v["prj_relative_path"])).name
        item = {"provenance": A.version_provenance(v, stems), "per_scan_groups": n, "covers_every_scan_of_group": covers}
        head = (f"The {n} per-scan Athena groups beside it in {prj} ('{members['labels'][0]}' …) were set aside: the "
                "scientist's merge is preferred, so ISAAC does not average them")
        if not covers:
            said.append(head + ("; they do not cover every scan of this group" if known else
                                "; whether they cover every scan of this group is not known (a scan states no number)")
                        + ", so the merge was not compared with their mean.")
        else:
            cmp_ = A.merge_versus_set(entry, v, params, np)
            item["comparison"] = cmp_
            m = cmp_["metrics"]
            how = (f"E0 {m['e0_delta_eV']:+.2f} eV, rms {m['rms_norm']:.3f} of the normalised curves"
                   if m.get("e0_delta_eV") is not None and m.get("rms_norm") is not None else "")
            if cmp_["verdict"] == "differs":
                differs = True
                said.append(f"The scientist's merge '{label}' differs from the mean of the {n} per-scan groups beside it "
                            f"({prj}, covering every scan of this group; {how}), so it is not preferred for the record; "
                            "ask which is the result of record.")
            elif cmp_["verdict"] == "agree":
                said.append(head + f"; their mean covers every scan of this group and agrees with the merge ({how}).")
            else:
                said.append(head + "; their mean covers every scan of this group, but the merge could not be compared "
                            f"with it ({', '.join(cmp_['flags']) or 'not comparable'}).")
        listed.append(item)
    question = (f"The scientist's merge '{label}' differs from the mean of the per-scan Athena groups beside it, which "
                "cover every scan of this group. Which is the result of record: the merge, or the per-scan groups? Approving "
                "this result puts the merge's E0 and curve in the record.") if differs else None
    return {"sets": listed, "statement": " ".join(said), "differs": differs, "question": question}


def _versions_question_text(versions: Sequence[Mapping]) -> str:
    """The which-version question, in words. c12-cal: versions that are the SAME raw data (one curve copied into
    several projects) normalised differently are said as such, naming the projects and the parameters that differ
    (measured on a real BL15-2 beamtime: one scan file in three projects read as "3 different Athena versions").
    Byte-identical curves with the same parameters are already one version (athena.match_with_versions)."""
    n = len(versions)
    ask = (" Which one is the result of record? None is selected until you choose. Once one is chosen, processing this "
           "group again gives that version its own Athena result to approve; the record carries the E0 and curve of the "
           "result that is approved.")
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


#: SCAN SELECTION (C.SCAN_SELECTION_RULE_ID): a proposal per scan of a merge, attached to an ISAAC result after its run
#: id, so it moves no result id. ``False`` turns the whole pass off (the series pass too); merged.csv and run_id are
#: byte-identical either way.
SCAN_SELECTION_ENABLED = True
#: the result key, the statement key and the review flag (a bulk approval refuses it: mutations.BULK_APPROVE_REVIEW)
SCAN_SELECTION_KEY = "scan_selection"
SCAN_SELECTION_FLAG = "scan_selection_proposed"
#: the payload key listing every series (scan template) and its E0
SCAN_SERIES_KEY = "scan_selection_series"
#: proposals for an input the merge does not take (a skip reason) or for a scan that is not an energy scan
LEFT_OUT = "left_out"
NOT_EVALUATED = "not_evaluated"
_SPEC_S_FULL = re.compile(r"^#S\s+\d+\s+(\w+)\s+([^\s]+)")
_HEADER_KEY_VALUE = re.compile(r"(?<![\w.])([A-Za-z_][\w.]*)=(-?[0-9.]+(?:[eE][-+]?\d+)?)")


def _scan_template(header_lines: Sequence[str] | None) -> tuple[str, str] | None:
    """``(command, scanned motor)`` a SPEC ``#S`` line states (``("gscan", "energy")``), or ``None``."""
    for line in header_lines or ():
        m = _SPEC_S_FULL.match(str(line).strip())
        if m:
            return m.group(1), m.group(2)
    return None


def _is_energy_scan(template: tuple[str, str] | None) -> bool:
    """A scan whose ``#S`` line scans ``energy`` (``gscan energy``, ``ascan energy``); a motor scan (``ascan Sz``,
    ``a2scan``, ``loopscan``) is ``not_an_energy_scan``. A scan with no ``#S`` line is taken as the energy scan the
    channel choice already found."""
    return template is None or template[1] == "energy"


def _header_setup(header_lines: Sequence[str] | None) -> dict:
    """The setup values (:data:`core.SEL_SETUP_KEYS`) a SPEC ``#P`` line states as ``key=value``."""
    want = {k for k, _ in C.SEL_SETUP_KEYS}
    out: dict = {}
    for line in header_lines or ():
        text = str(line).strip()
        if not text.startswith("#P"):
            continue
        for k, v in _HEADER_KEY_VALUE.findall(text):
            if k in want and k not in out:
                try:
                    out[k] = float(v)
                except ValueError:
                    pass
    return out


def _scan_seed(entry: Mapping, ctx: _Ctx) -> int:
    """The noise-injection seed of one scan: from its own bytes' hash (and its scan number), so a re-run repeats."""
    sha = (ctx.sources.get(entry.get("source_id") or "") or {}).get("content_sha256") or str(entry.get("relative_path"))
    return int(hashlib.sha256(f"{sha}#{entry.get('scan')}".encode()).hexdigest()[:15], 16)


def _find_e0(energy, mu, xafs) -> float | None:
    try:
        return C._f(xafs.find_e0(energy, mu))
    except Exception:  # noqa: BLE001 - no E0 for this scan: it takes no part in the median
        return None


def scan_selection_series(groups: Sequence[Mapping], ctx: _Ctx) -> dict:
    """THE SERIES PASS: every energy scan of the bundle (every group's, once each), by SPEC template (``#S`` command
    and scanned motor) and overlapping energy range, and the series E0 = the median per-scan E0 (larch ``find_e0``) of
    the series' scans that cover at least :data:`core.SEL_COVERAGE_MIN` of its median scan's span (a stopped scan
    takes no part; a few longer scans do not leave the usual ones out). ``{"series": {id: ...},
    "of": {(source_id, scan_index): id}}``. Scans with no ``#S`` line belong to no series (their group's own scans
    give its E0)."""
    np = ctx.np
    seen: set = set()
    rows: list[dict] = []
    for g in groups:
        scans, _stems, sel = group_scans(g, ctx.runs_by_key)
        if not scans:
            continue
        shared: dict = {}
        for s in scans:
            shared[s.get("source_id")] = shared.get(s.get("source_id"), 0) + 1
        choice = None
        for s in scans:
            key = (s.get("source_id"), s.get("scan_index"))
            if key in seen:
                continue
            seen.add(key)
            try:
                table, _why = _read_scan_table(s, ctx, shared)
            except Exception:  # noqa: BLE001 - an unreadable scan takes no part in a series
                continue
            if table is None or table.error:
                continue
            tpl = _scan_template(table.header_lines)
            if tpl is None or not _is_energy_scan(tpl):
                continue
            if choice is None:
                c = choose_channels(table, params=ctx.params, role=g.get("role", "sample"), bl15_selection=sel)
                if not _formed(c):
                    continue
                choice = c
            try:
                sa = C.scan_arrays(table, choice, np)
            except C.StepError:
                continue
            if C.unusable_reason(sa) or sa["energy"].size < int(ctx.params["merge"]["min_points"]):
                continue
            rows.append({"key": key, "template": tpl, "energy": sa["energy"], "mu": sa["mu"],
                         "lo": float(sa["energy"][0]), "hi": float(sa["energy"][-1])})
    series: dict = {}
    of: dict = {}
    by_tpl: dict = {}
    for r in rows:
        by_tpl.setdefault(r["template"], []).append(r)
    for tpl in sorted(by_tpl):
        members = sorted(by_tpl[tpl], key=lambda r: (r["lo"], r["hi"]))
        clusters: list[list[dict]] = []
        for r in members:  # overlapping energy ranges: one series (one edge)
            if clusters and r["lo"] <= max(x["hi"] for x in clusters[-1]):
                clusters[-1].append(r)
            else:
                clusters.append([r])
        for cl in clusters:
            lo, hi = min(x["lo"] for x in cl), max(x["hi"] for x in cl)
            sid = f"{tpl[0]} {tpl[1]} {lo:.6g}-{hi:.6g} eV"
            # the series' usual span (its median scan's): a few longer scans must not leave the usual ones out
            usual = statistics.median([x["hi"] - x["lo"] for x in cl])
            e0s = [v for v in (_find_e0(x["energy"], x["mu"], ctx.xafs) for x in cl
                               if (x["hi"] - x["lo"]) >= C.SEL_COVERAGE_MIN * usual) if v is not None]
            series[sid] = {"series_id": sid, "command": f"{tpl[0]} {tpl[1]}", "range_eV": [lo, hi], "scans": len(cl),
                           "scans_for_e0": len(e0s), "e0_eV": float(statistics.median(e0s)) if e0s else None,
                           "e0_rule": "median of larch find_e0 over the series' scans covering "
                                      f"{C.SEL_COVERAGE_MIN:.0%} of its median scan's span"}
            for x in cl:
                of[x["key"]] = sid
    return {"series": series, "of": of}


def _propose_scan_selection(group: Mapping, ctx: _Ctx, scans: Sequence[Mapping], used_entries: Sequence[dict],
                            scans_data: Sequence[Mapping], header_of: Mapping[int, Sequence[str]],
                            inputs: Sequence[dict], cal: Mapping) -> dict | None:
    """The group's scan-selection proposal (:func:`core.scan_selection`), shaped for the result: every listed input
    with its proposal, reasons and sentences, named by file; the group's trend, change point, stable window, edge-step
    observation and merged edge SNR. ``None`` only when it cannot be evaluated at all (it is then not said)."""
    np = ctx.np
    try:
        run_of = {s.get("source_id"): s.get("run_key") for s in scans}
        numbers, _ = B.input_scan_numbers(inputs, run_of)
        num_of = {id(e): n for e, n in zip(inputs, numbers)}
        used_nums = [num_of.get(id(e)) for e in used_entries]
        by_number = (all(isinstance(n, int) for n in used_nums)
                     and all(a < b for a, b in zip(used_nums, used_nums[1:])))
        pos_of = {id(e): k + 1 for k, e in enumerate(inputs)}
        evaluated, not_energy = [], {}
        for e, sa in zip(used_entries, scans_data):
            tpl = _scan_template(header_of.get(id(e)))
            if not _is_energy_scan(tpl):
                not_energy[id(e)] = tpl
                continue
            evaluated.append({"key": id(e), "number": num_of[id(e)] if by_number else pos_of[id(e)],
                              "energy": sa["energy"], "mu": sa["mu"], "counts": sa.get("counts"), "i0": sa.get("i0"),
                              "ring": sa.get("ring"), "i0_nonpositive": sa["diagnostics"].get("i0_nonpositive"),
                              "setup": _header_setup(header_of.get(id(e))), "seed": _scan_seed(e, ctx)})
        by_key = {id(e): e for e in used_entries}
        ser = getattr(ctx, "scan_series", None) or {}
        keys = [ser.get("of", {}).get((by_key[x["key"]].get("source_id"), by_key[x["key"]].get("scan")))
                for x in evaluated]
        tally: dict = {}
        for k in keys:
            if k:
                tally[k] = tally.get(k, 0) + 1
        series, e0s, basis = None, None, None
        if tally:
            sid = max(sorted(tally), key=tally.get)
            series = ser["series"].get(sid)
            if series and series.get("e0_eV") is not None:
                e0s, basis = float(series["e0_eV"]) + float(cal["outcome"].get("applied_shift_eV") or 0.0), "series"
        if e0s is None:
            # no SPEC template (another reader): the group's own scans are its series
            vals = [v for v in (_find_e0(x["energy"], x["mu"], ctx.xafs) for x in evaluated) if v is not None]
            if vals:
                e0s, basis = float(statistics.median(vals)), "group"
        if e0s is None:
            return None
        core = C.scan_selection(evaluated, e0s, np)
    except Exception as exc:  # noqa: BLE001 - a proposal that cannot be made is said, never a processing failure
        return {"rule_id": C.SCAN_SELECTION_RULE_ID, "status": "not_evaluated",
                "detail": f"{type(exc).__name__}: {exc}"[:300], "open": False, "scans": []}
    got = {x["key"]: x for x in core.pop("scans")}
    file_of_number = {}
    per_scan = []
    for e in inputs:
        base = {"file": _file_name(e), "relative_path": e.get("relative_path"), "source_id": e.get("source_id"),
                "scan": e.get("scan"), "exclude_as": exclusion_name(e, inputs)}
        if id(e) in got:
            x = got[id(e)]
            file_of_number[x["number"]] = base["file"]
            per_scan.append({**base, "time_order": x["number"], "proposal": x["proposal"], "reasons": x["reasons"],
                             "said": x["said"], "metrics": x["metrics"]})
        elif id(e) in not_energy:
            tpl = not_energy[id(e)]
            per_scan.append({**base, "proposal": NOT_EVALUATED, "reasons": ["not_an_energy_scan"],
                             "said": [f"its #S line is `{tpl[0]} {tpl[1]}`, not an energy scan: it is never proposed"],
                             "metrics": {}})
        elif e.get("used"):
            per_scan.append({**base, "proposal": NOT_EVALUATED, "reasons": ["too_few_points_to_evaluate"],
                             "said": ["too few points to judge alone"], "metrics": {}})
        else:
            per_scan.append({**base, "proposal": LEFT_OUT, "reasons": [e.get("skip_reason") or "not_used"],
                             "said": ["not in this merge"], "metrics": {}})
    exclude = [x["exclude_as"] for x in per_scan if x["proposal"] == C.PROPOSAL_EXCLUDE]
    look = [x["exclude_as"] for x in per_scan if x["proposal"] == C.PROPOSAL_LOOK]
    window = core.get("stable_window")
    return {
        "rule_id": C.SCAN_SELECTION_RULE_ID,
        # "not_evaluated" when no scan reaches the series window (nothing is proposed; ``detail`` says why)
        "status": core.get("status") or "evaluated",
        **({"detail": core["detail"]} if core.get("detail") else {}),
        "constants": C.SCAN_SELECTION_CONSTANTS,
        "e0_series_eV": core["e0_series_eV"],
        "e0_basis": basis,
        "series_id": series.get("series_id") if (series and basis == "series") else None,
        "time_order": "scan_numbers" if by_number else "input_order",
        "scans": per_scan,
        "trend": core.get("trend") or {},
        "change_point": core.get("change_point") or {},
        "evolving_metrics": core.get("evolving_metrics") or [],
        "stable_window": [file_of_number.get(n, n) for n in window] if window else None,
        "edge_step_change": core.get("edge_step_change"),
        "group_observations": core.get("group_observations") or [],
        "merge_snr": core.get("merge_snr"),
        "chi2_nu_median": core.get("chi2_nu_median"),
        "exclude_proposed": exclude,
        "needs_look": look,
        "open": bool(exclude or look),
        # the params-file names already left out of this merge: an exclude_scans list must keep naming them
        "already_excluded": [e["excluded_as"] for e in inputs if e.get("excluded_as")],
    }


def _scan_selection_statement(sel: Mapping, group_id: str) -> str | None:
    """The one sentence a person reads: what is proposed, for which scan and why, what to look at, the group's
    observations, and the exact ``exclude_scans`` snippet for the scans proposed for leaving out (``None`` when there
    is nothing to say)."""
    rows = sel.get("scans") or ()
    exc = [x for x in rows if x["proposal"] == C.PROPOSAL_EXCLUDE]
    look = [x for x in rows if x["proposal"] == C.PROPOSAL_LOOK]
    obs = list(sel.get("group_observations") or ())
    if not (exc or look or obs):
        return None
    merged = sum(1 for x in rows if x["proposal"] in (C.PROPOSAL_INCLUDE, C.PROPOSAL_LOOK, C.PROPOSAL_EXCLUDE))

    def each(xs, shown=12):
        out = "; ".join(f"{x['file']} ({', '.join(x['reasons'])}: {'; '.join(x['said'])})" for x in xs[:shown])
        return out + (f"; and {len(xs) - shown} more" if len(xs) > shown else "")

    said = (f"Scan selection ({C.SCAN_SELECTION_RULE_ID}; a PROPOSAL, nothing was left out of this merge): each of the "
            f"{merged} merged scans was normalised alone with the series' one parameter set (E0 "
            f"{sel['e0_series_eV']:.2f} eV) only to judge it; the merge stays raw mu.")
    if sel.get("stable_window"):
        said += (f" The sample was still changing at first ({', '.join(sel.get('evolving_metrics') or ())}); the stable "
                 f"scans are {', '.join(str(f) for f in sel['stable_window'])}.")
    if exc:
        said += f" Proposed for leaving out ({len(exc)}): {each(exc)}."
    if look:
        said += f" A person looks at ({len(look)}): {each(look)}."
    if obs:
        said += " Observed: " + " ".join(obs)
    if exc:
        said += (" The scientist confirms each proposal: " +
                 exclude_hint(group_id, list(sel.get("already_excluded") or ()) + [x["exclude_as"] for x in exc]))
    if exc or look:
        said += (" While a proposal is open this result is approved only on its own (never in a bulk approval), and "
                 "the approval's note records what was still open.")
    return said


def _attach_scan_selection(res: dict, sel: Mapping, group_id: str) -> None:
    """After the run id: the proposal on the result (:data:`SCAN_SELECTION_KEY`), its sentence, and the review flag
    when any proposal is open."""
    res[SCAN_SELECTION_KEY] = sel
    said = _scan_selection_statement(sel, group_id) if sel.get("status") == "evaluated" else None
    if said:
        res["qc"].setdefault("statements", {})[SCAN_SELECTION_KEY] = said
    if sel.get("open") and SCAN_SELECTION_FLAG not in res["review_flags"]:
        res["review_flags"].append(SCAN_SELECTION_FLAG)


def _read_scan_table(s: Mapping, ctx: _Ctx, shared_sids: Mapping[Any, int]):
    """``(table, None)`` for one listed scan, or ``(None, skip reason)`` when its file is missing or its bytes are not
    the bundle's (``content_sha256``)."""
    path = _resolve_source(ctx.root, s.get("relative_path") or "") if ctx.root else None
    if path is None or not path.is_file():
        return None, "source_file_not_found"
    expected = (ctx.sources.get(s.get("source_id") or "") or {}).get("content_sha256")
    if expected and sha256_file(path) != expected:
        return None, "source_hash_mismatch"
    # r5d H1: one scan of a file of several `#S` blocks (several of the group's scans in one file, or the
    # run's own SPEC acquisition file) is read at its own block; every other scan file is read as before
    in_file = s.get("source_id") is not None and (
        shared_sids.get(s.get("source_id"), 0) > 1
        or s.get("source_id") == (ctx.runs_by_key.get(s.get("run_key")) or {}).get("acquisition_source_id"))
    table = (read_scan_file(path, scan=s["scan_index"]) if ctx.scan_reader is read_scan_file and in_file
             and isinstance(s.get("scan_index"), int) and not isinstance(s.get("scan_index"), bool)
             else ctx.scan_reader(path))
    return table, None


def process_group(group: Mapping, ctx: _Ctx, athena_entry: Mapping | None = None, athena_versions: Sequence[Mapping] | None = None) -> list[dict]:
    np, params = ctx.np, ctx.params
    res = _base(group, "isaac_protocol")
    scans, stems, sel = group_scans(group, ctx.runs_by_key)
    if not scans:
        return [_not_applicable(res, B.NA_NO_SCANS, "the group lists no scan", data_states(group, ctx.runs_by_key))]
    tables = []
    exclude = list((getattr(ctx, "exclusions", None) or {}).get(group["group_id"]) or ())
    excluded: list[dict] = []
    shared_sids: dict[str, int] = {}
    for s in scans:
        shared_sids[s.get("source_id")] = shared_sids.get(s.get("source_id"), 0) + 1
    for s in scans:
        entry = {"source_id": s.get("source_id"), "scan": s.get("scan_index"), "relative_path": s.get("relative_path"), "channel": None, "used": False}
        res["inputs"].append(entry)
        named = _excluded_as(entry, exclude)
        if named is not None:
            # r4-a M6: left out by the params file's exclude_scans, never read (recorded in params.json and said)
            entry.update(skip_reason=EXCLUDED_REASON, excluded_as=named)
            excluded.append({"source_id": entry["source_id"], "relative_path": entry["relative_path"],
                             "scan": entry["scan"], "named_as": named})
            continue
        table, why = _read_scan_table(s, ctx, shared_sids)
        if table is None:
            entry["skip_reason"] = why
            continue
        entry["format"] = table.format_id
        entry["reader_notes"] = table.notes
        if table.error:
            entry["skip_reason"] = f"unreadable:{table.error}"
            continue
        tables.append((entry, table))
    if not tables:
        causes = sorted({e.get("skip_reason") or "?" for e in res["inputs"]})
        out = _fail(res, "no_readable_scan", ";".join(causes))
        said = _exclusion_statement(excluded, exclude, len(res["inputs"]), 0)
        if said:
            # r4-a review: every scan left out by the params file: said and flagged here too (outside the failure's hash)
            out["qc"]["statements"] = {EXCLUDED_REASON: said}
            out["review_flags"].append(EXCLUDED_REASON)
        return [out]

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
    usable: list[tuple] = []
    header_of: dict[int, Sequence[str]] = {id(entry): table.header_lines for entry, table, _, _ in attempts}
    for entry, table, sa, code in attempts:
        code = code or C.unusable_reason(sa)
        if code:
            entry["skip_reason"] = code
            if code == "too_few_points" and sa is not None:
                too_few.append(int(sa["energy"].size))
                # r5 A5: points read and kept, so the sentence can say what the scan is (not an energy scan / stopped);
                # its own key: ``diagnostics`` on a skipped scan means signal_not_finite / signal_all_zero
                entry[TOO_FEW_POINTS_KEY] = {k: sa["diagnostics"][k] for k in ("points_read", "points_used")}
            if code in (C.SIGNAL_NOT_FINITE, C.SIGNAL_ALL_ZERO):
                entry["diagnostics"] = sa["diagnostics"]  # points_read, nonfinite_dropped / signal_all_zero: why
            continue
        usable.append((entry, table, sa))
    # r5 A5 (FRAGMENT_RULE_ID): a scan with fewer points than a merge needs, beside a scan with enough, is a stopped
    # (aborted) fragment: left out of the merge, counted and said
    fragments = _aborted_fragments([sa for _, _, sa in usable], int(params["merge"]["min_points"]))
    for k, (entry, table, sa) in enumerate(usable):
        if k in fragments:
            entry.update(skip_reason=FRAGMENT_REASON, diagnostics=sa["diagnostics"])
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
        said = _no_usable_scan_statement(res["inputs"], too_few, signal=_raw_signal(choice),
                                         transmission=choice.mode == MODE_TRANSMISSION)
        if said:
            out["qc"]["statements"] = {"no_usable_scan": said}
        few_said = _too_few_points_statement(res["inputs"], 0, choice.energy, header_of)
        if few_said:
            out["qc"].setdefault("statements", {})["scans_skipped_too_few_points"] = few_said
        return [out]

    calibrant = REF.calibrant_identity(identity_texts(group, stems)) if role == "reference" else None
    cal = _calibration(group, stems, scans_data, headers, ctx, calibrant=calibrant)
    hashed_cal = _said_reference(cal, calibrant)  # c12-cal: said in the result, not in the hashed files (no id moves)
    res["steps"].append(cal)
    res["review_flags"] += cal["flags"]
    shifts = cal["outcome"]["per_scan_alignment_shifts_eV"] or [0.0] * len(scans_data)
    for sa, d in zip(scans_data, shifts):
        sa["energy"] = sa["energy"] + cal["outcome"]["applied_shift_eV"] + d
    # THE SCAN-SELECTION PROPOSAL (C.SCAN_SELECTION_RULE_ID), before the merge grid: each scan normalised alone with the
    # series' one parameter set, only to judge it. It changes nothing that is merged or hashed (merged.csv, run_id);
    # it is attached to the result after the run id (:func:`_attach_scan_selection`)
    selection = (_propose_scan_selection(group, ctx, scans, used_entries, scans_data, header_of, res["inputs"], cal)
                 if SCAN_SELECTION_ENABLED else None)

    try:
        grid, ginfo = C.common_grid(scans_data, np)
    except C.StepError as exc:
        return [_fail(res, exc.code, exc.detail)]
    if grid.size < int(params["merge"]["min_points"]):
        return [_fail_too_few_common(res, len(scans_data), int(grid.size), int(params["merge"]["min_points"]))]
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
    # r4-a (C.SINGLE_SCAN_RULE_ID): one scan's stretch that sets the merged curve's range fails the curve; a group whose
    # other scans have no edge is said, never failed (only_scan_with_edge)
    found = C.single_scan_dominance(M, grid, np, exclude_points=dg["point_flags"] if excl else None,
                                    exclude_scans=dg["scan_flags"] if excl else None)
    dominant = found if found and found["kind"] == "one_scan_sets_merge" else None
    only_edge = found if found and found["kind"] == "only_scan_with_edge" else None
    ok = np.isfinite(mg["mean"])
    g2, mean = grid[ok], mg["mean"][ok]
    if g2.size < int(params["merge"]["min_points"]):
        return [_fail_too_few_common(res, len(scans_data), int(g2.size), int(params["merge"]["min_points"]))]
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
        # r4-a: only when one scan sets the merged curve (absent otherwise, as above): the curve fails
        **({"single_scan_span_ratio": dominant["ratio"]} if dominant else {}),
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
        # r4-a M6: only when the params file left scans out (absent otherwise, as above)
        **({"scans_excluded_by_params_file": len(excluded)} if excluded else {}),
        # r5 A5: only when aborted fragments were left out of the merge (absent otherwise, as above)
        **({"scans_skipped_aborted_fragment": len(fragments)} if fragments else {}),
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
    version_coverage: list[dict | None] = []
    if athena_versions:
        # Several distinct Athena versions for this group (e.g. re-normalised, glitch-removed,
        # smoothed). NONE is selected: each is listed with what its own files state, compared,
        # and the scientist is asked which one is the result of record.
        res["athena_versions"] = []
        for n, v in enumerate(athena_versions, start=1):
            cmp_ = A.compare({"grid": g2, "norm": nm["norm"], "flat": nm["flat"], "e0_eV": nm["e0_eV"], "edge_step": step}, v, params, np)
            version_coverage.append(_diagnose(cmp_, v, stems, used_entries, grid, M, ctx, stem_of=stem_of, number_of=number_of))
            listed = {"version_id": f"{group['group_id']}-v{n:02d}", "provenance": A.version_provenance(v, stems), "comparison": cmp_}
            if not A.plausible(v):
                listed["flags"] = [A.EDGE_STEP_IMPLAUSIBLE_FLAG]
            elif athena_post_edge_level(v, np):
                # r5 A1: the version's post-edge level fails: flagged where the scientist chooses (its own QC, once
                # chosen, fails post_edge_not_at_1)
                listed["flags"] = [ATHENA_POST_EDGE_FLAG]
            if v.get(A.RENORMALISED_KEY):
                # r5 H1: the version's curve is made as Athena makes it, not as larch reads it. r6 G4: recorded on the
                # version, said once for the bundle (renormalisation_line), never flagged on each
                listed[A.RENORMALISED_KEY] = {k: x for k, x in v[A.RENORMALISED_KEY].items() if k != "statement"}
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
                # r4-a M6: only for a group the params file leaves scans out of (absent otherwise: no other id moves)
                **({"excluded_scans": excluded} if excluded else {}),
                # r6 G1: only for a group the scientist named an Athena group for (absent otherwise: no other id moves)
                **({P.ATHENA_MATCH_SECTION: ctx.athena_ties[group["group_id"]]}
                   if ctx.athena_ties.get(group["group_id"]) else {}),
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
    # r5 A5: scans left out for too few points (not energy scans, or stopped) and aborted fragments are said
    few_points_said = _too_few_points_statement(res["inputs"], len(scans_data), choice.energy, header_of)
    if few_points_said:
        res["qc"].setdefault("statements", {})["scans_skipped_too_few_points"] = few_points_said
    fragments_said = _fragments_statement(res["inputs"], len(scans_data), int(params["merge"]["min_points"]))
    if fragments_said:
        res["qc"].setdefault("statements", {})[FRAGMENT_REASON] = fragments_said
        res["review_flags"].append(FRAGMENT_REASON)
    # c11-r: a merged scan whose signal is exactly zero where another's is not: merged unchanged, said and flagged
    # (after run_id: qc.json is hashed, so no result id moves)
    # c12-cal: with fewer scans than the cross-scan check needs, the glitch check compares each point with its
    # neighbours and flags real features too (white line, oscillations): said beside the count (after run_id: no id
    # moves; the count, the flag and the verdict are unchanged)
    # c12-r: an approval the current rules did not apply is named (the flag alone said nothing of the approval), and a
    # params-file value the stricter-only rule ignored is said (after run_id: no id moves)
    cal_step = next((s_ for s_ in res["steps"] if s_.get("step") == "calibration"), None)
    not_applied = REF.approval_not_applied(cal_step, params["qc"]["warn_energy_shift_eV"]) if cal_step else None
    if not_applied:
        res["qc"].setdefault("statements", {})["calibration_approval_not_applied"] = not_applied
    ignored = REF.ignored_overrides(params)
    if ignored:
        res["qc"].setdefault("statements", {})["params_override_ignored"] = " ".join(ignored)
    few_said = _few_scan_glitch_statement(len(scans_data), dg["flagged_points_total"], params)
    if few_said:
        res["qc"].setdefault("statements", {})["glitch_check_few_scans"] = few_said
        # r5 A6/L3: with fewer than 3 scans every flagged point is unjudged, on the edge or not (after the run id)
        res["qc"]["metrics"]["glitch_points_unjudged"] = int(dg["flagged_points_total"])
    # r4-a L6: a channel chosen by column-name priority (no selection ISAAC can check) is said, not only flagged
    if "channel_choice_needs_review" in choice.flags:
        res["qc"].setdefault("statements", {})["channel_choice_needs_review"] = needs_review_statement(choice)
    # r2-a: flagged points at E0 or where the merged curve is steep are on the edge, not glitches: listed apart,
    # counted and said (after run_id: qc.json is hashed, so no id moves; the stored count, flag and verdict stay)
    clean = C.merge(M, dg["point_flags"], None, np)["mean"]  # review: steepness read without the flagged points
    okc = np.isfinite(clean)
    names = [_file_name(e) for e in used_entries]
    where = C.glitch_points_on_edge(dg["point_flags"], grid, grid[okc], clean[okc], nm["e0_eV"], np)
    # r4-a (GLITCH_EDGE_RULE_ID v1): a point from one scan alone, far beyond the other scans there, is a glitch even on
    # the edge: never shielded as "unjudged" (said apart; the stored count, flag and verdict are unchanged)
    one = C.glitch_points_from_one_scan(dg["point_flags"], grid, M, np)
    one_on_edge = [(sp, en) for sp, en, at in where if at and (sp, en) in one]
    on_edge = _glitch_points_on_edge([(sp, en, at and (sp, en) not in one) for sp, en, at in where], nm["e0_eV"], names,
                                     one_scan=len(one_on_edge), few_scans=few_said is not None)
    if one_on_edge:
        res["qc"]["metrics"]["glitch_points_from_one_scan_on_edge"] = len(one_on_edge)
        res["qc"].setdefault("statements", {})["glitch_points_from_one_scan"] = _one_scan_glitch_statement(
            one_on_edge, names, nm["e0_eV"])
        dg_step = next(s_ for s_ in res["steps"] if s_.get("step") == "deglitch")
        dg_step["outcome"]["flagged_points_from_one_scan_on_edge"] = [{"source_id": pos_sid[sp], "energy_eV": en}
                                                                      for sp, en in one_on_edge[:200]]
        dg_step["outcome"]["glitch_edge_rule_id"] = C.GLITCH_EDGE_RULE_ID
    if dominant:
        res["review_flags"].append(SINGLE_SCAN_FLAG)
        res["qc"].setdefault("statements", {})[SINGLE_SCAN_FLAG] = _single_scan_statement(
            dominant, names, group["group_id"], exclusion_name(used_entries[dominant["scan_position"]], res["inputs"]))
    if only_edge:
        res["review_flags"].append(ONLY_EDGE_FLAG)
        res["qc"].setdefault("statements", {})[ONLY_EDGE_FLAG] = _only_edge_statement(only_edge, names)
    if on_edge:
        if on_edge["off_edge"] is None:
            # r5 A6: with fewer than 3 scans no flag is counted as a glitch (glitch_points_unjudged, set above)
            res["qc"]["metrics"].update(glitch_points_on_edge=on_edge["on_edge"])
        else:
            res["qc"]["metrics"].update(glitch_points_on_edge=on_edge["on_edge"], glitch_points_off_edge=on_edge["off_edge"])
        res["qc"].setdefault("statements", {})["glitch_points_on_edge"] = on_edge["statement"]
        dg_step = next(s_ for s_ in res["steps"] if s_.get("step") == "deglitch")
        dg_step["outcome"]["flagged_points_on_edge"] = [{"source_id": pos_sid[p["scan_position"]], "energy_eV": p["energy_eV"]}
                                                        for p in on_edge["listed"]]
        dg_step["outcome"]["glitch_edge_rule_id"] = C.GLITCH_EDGE_RULE_ID
    exclusion_said = _exclusion_statement(excluded, exclude, len(res["inputs"]), len(scans_data))
    if exclusion_said:
        res["qc"].setdefault("statements", {})[EXCLUDED_REASON] = exclusion_said
        res["review_flags"].append(EXCLUDED_REASON)
    zero_points_said = _zero_signal_points_statement(used_entries, scans_data, _raw_signal(choice), np,
                                                     group_id=group["group_id"], inputs=res["inputs"])
    if zero_points_said:
        res["qc"].setdefault("statements", {})["merged_scan_zero_signal_points"] = zero_points_said
        res["review_flags"].append(ZERO_SIGNAL_POINTS_FLAG)
    # r3-b M4: an outlier scan is named, with where it departs and what merging it did (the count alone said nothing)
    outlier_said = _outlier_scans_statement(dg["scan_flags"], used_entries, grid, M, mg["mean"], excl, np,
                                            group_id=group["group_id"], inputs=res["inputs"])
    if outlier_said:
        res["qc"].setdefault("statements", {})["outlier_scans"] = outlier_said
    # c12-cal: zeros whose counts come back are counted in one line (no flag), never said as a lost beam
    isolated_said = _isolated_zero_points_statement(used_entries, scans_data, _raw_signal(choice), np)
    if isolated_said:
        res["qc"].setdefault("statements", {})["merged_scan_isolated_zero_points"] = isolated_said
    # c12-r: runs of 3+ zeros under 5 % of the scan whose counts come back: counted, with no claim of what they are
    short_said = _short_zero_runs_statement(used_entries, scans_data, _raw_signal(choice), np)
    if short_said:
        res["qc"].setdefault("statements", {})["merged_scan_short_zero_runs"] = short_said
    # c12-cal: the merged curve's ends from one scan alone (the grid is the widest scan's; nothing is trimmed)
    ends_said = _one_scan_ends_statement(g2, mg["n"][ok], used_entries, M[:, ok], len(scans_data), np)
    if ends_said:
        res["qc"].setdefault("statements", {})["merged_curve_end_from_one_scan"] = ends_said
    if truncated:
        # c12-cal: the result names each short scan by its FILE; qc.json (hashed) keeps the sentence it was written with
        res["qc"]["statements"]["scans_truncated"] = _truncation_statement(ginfo, scans_data, [_file_name(e) for e in used_entries])
    if selection is not None:
        # after run_id: never in a hashed file (no id moves)
        _attach_scan_selection(res, selection, group["group_id"])
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
                                              and not (coverage or {}).get("partial")
                                              # r5 A1: nor a curve whose post-edge level fails (its QC fails too)
                                              and ATHENA_POST_EDGE_FLAG not in athena_res["review_flags"])
        athena_res["run_id"] = run_id
        athena_res["result_id"] = f"proc-{group['group_id']}-{run_id}-athena"
        _say_tie(athena_res, athena_entry, files)
        # r3-d: the per-scan sets set aside beside the scientist's merge are listed and said, and a merge that differs
        # from the mean of a set covering every scan of the group is not preferred (after run_id: no id moves)
        aside = _sets_aside(athena_entry, stems, res["inputs"], numbers, stem_of, params, np)
        if aside is not None:
            athena_res["athena_per_scan_sets_set_aside"] = aside["sets"]
            athena_res["qc"]["statements"][SET_ASIDE_STATEMENT] = aside["statement"]
            if aside["differs"]:
                athena_res["review_flags"].append(MERGE_DIFFERS_FROM_SET_FLAG)
                athena_res["preferred_for_record"] = False
                athena_res["questions"] = [*(athena_res.get("questions") or ()),
                                           {"code": MERGE_OR_SET_QUESTION, "text": aside["question"]}]
        out.append(athena_res)
    picked = None
    chosen = _group_selection(group["group_id"], res, ctx.bundle)
    if chosen is not None:
        decision, vid = chosen
        ids = B.athena_version_ids(res)
        if vid in ids:
            picked = (ids.index(vid) + 1, decision)
        elif (decision.get("target") or {}).get("id") != res["result_id"]:
            # r1-a M2: chosen on ANOTHER result of this group (ISAAC's own result id moved: a params file, a
            # calibration) and it names no version listed now: never carried over to another curve, and said. A choice
            # on this very result id is said by `isaac process` (mutations) as before.
            _say_selection_not_carried_over(res, decision)
    if picked is not None:
        # r1-a M4: the version the scientist chose as the result of record gets its own Athena result, built as
        # every Athena result is; approving it (never the choice alone) makes the record carry its E0 and curve
        n, decision = picked
        v, listed = athena_versions[n - 1], res["athena_versions"][n - 1]
        vfiles = [{**f, "role": "athena_normalized"} for f in files if f["role"] == f"athena_version_{n:02d}"]
        # r7 K4: the chosen version's own plot, with its curve overlaid (the run's plot.png has no Athena curve: it was
        # drawn before any version was chosen). PNGs are never hashed, so no id moves; one already there is kept.
        vplot = _version_plot(gdir, n, v, group, stems, grid, M, mg, dg, nm, np, ctx.bundle_dir)
        vfiles += [vplot] if vplot else [f for f in files if f["role"] == "plot"]
        vres = _athena_result(group, v, vfiles, params, np, ctx, stems=stems, isaac_counts=(len(scans_data), len(scans)),
                              coverage=version_coverage[n - 1],
                              isaac_scans=[number_of[id(e)] for e in used_entries] if listed_scans else None,
                              listed_scans=listed_scans,
                              numbered_from_file_names=numbering == B.SCAN_NUMBERS_FROM_FILE_NAME)
        vres["comparison"] = listed["comparison"]
        vres["preferred_for_record"] = (A.frame_known(v) and A.plausible(v)
                                        and not (version_coverage[n - 1] or {}).get("partial")
                                        and ATHENA_POST_EDGE_FLAG not in vres["review_flags"])
        vres["run_id"] = run_id
        vres["result_id"] = f"proc-{group['group_id']}-{run_id}-athena-v{n:02d}"
        _say_tie(vres, v, files)
        said = _version_chosen_statement(listed, decision, vres, res)
        made_on = (decision.get("target") or {}).get("id")
        if made_on != res["result_id"]:
            # r1-a M2: the choice was made on an earlier ISAAC result of this group and is carried over by the version's
            # own provenance (project file, Athena group, data hash), never by its position
            carried = (f" The choice was made on an earlier ISAAC result of this group, {made_on}; the same version "
                       "(same project file, Athena group and data hash) is listed here, so it is carried over. This "
                       "result's own question stays open until a choice is recorded on it; approving "
                       f"{vres['result_id']} is what puts that version's E0 and curve in the record.")
            said = {"athena": said["athena"] + carried, "isaac": said["isaac"] + carried}
        replaced = _approved_other_versions(group["group_id"], decision, vres["result_id"], ctx.bundle)
        if replaced:
            # r1-a M3: an approved result of a version the scientist chose EARLIER, while the latest choice is another: a
            # record uses one approved result (decide refuses a second), so the order is said
            vres["athena_version_replaces_approved"] = replaced
            both = " ".join(x["statement"] for x in replaced)
            said = {"athena": f"{said['athena']} {both}", "isaac": f"{said['isaac']} {both}"}
        vres["athena_version_id"] = listed["version_id"]
        vres["athena_version_selected"] = {"decision_id": decision.get("decision_id"),
                                           "decided_by": (decision.get("decided_by") or {}).get("name"),
                                           "isaac_result_id": res["result_id"], "statement": said["athena"]}
        vres["qc"]["statements"]["athena_version_selected"] = said["athena"]
        # after run_id: said in the result and the lists, never in the hashed files (no id moves)
        res["qc"].setdefault("statements", {})["athena_version_selected"] = said["isaac"]
        out.append(vres)
    # result.json is a SNAPSHOT, written once with the run folder: a re-run into an existing folder leaves it as it is
    # (the folder is content-addressed and never rewritten), so a sentence added to the result later (the non-hashed
    # `qc.statements`) is in bundle.json and the list/show output, not necessarily in an older result.json
    record = gdir / "result.json"
    if not record.exists():
        _write(record, _json_bytes({"results": out}))
    return out


VERSION_PLOT_KEY = "athena_version_plot"


def version_plot_notes(results: Sequence[dict], *, stored: Sequence[Mapping] = ()) -> list[dict]:
    """r7 K4: on each result of a chosen Athena version, the path of its own plot (``plot_athena_v<n>.png``, its curve
    overlaid) as a field and a sentence; and a kept note for a STORED result of that id that does not name it yet (a
    version result decided before this build, kept as it was, its outputs unchanged). Outside the hashed files: no id
    moves."""
    named = {B.processing_id(r): r.get(VERSION_PLOT_KEY) for r in stored or () if isinstance(r, Mapping)}
    notes = []
    for r in results:
        if not r.get("athena_version_id"):
            continue
        path = next((f["relative_path"] for f in (r.get("outputs") or {}).get("files") or ()
                     if f.get("role") == "plot" and PurePosixPath(str(f.get("relative_path"))).name.startswith("plot_athena_v")), None)
        if not path:
            continue
        said = (f"The plot of this version, with its Athena curve over ISAAC's: {path}. The run's plot.png shows ISAAC's "
                "curve alone (it was drawn before a version was chosen).")
        r[VERSION_PLOT_KEY] = path
        r.setdefault("qc", {}).setdefault("statements", {})[VERSION_PLOT_KEY] = said
        if r["result_id"] in named and named[r["result_id"]] != path:
            notes.append({"result_id": r["result_id"], "fields": {VERSION_PLOT_KEY: path},
                          "statements": {VERSION_PLOT_KEY: said}})
    return notes


def _version_plot(gdir: Path, n: int, v: Mapping, group: Mapping, stems, grid, M, mg, dg, nm, np, bundle_dir: Path) -> dict | None:
    """r7 K4: ``plot_athena_v<n>.png`` in the run folder: the run's review plot with the chosen Athena version's curve
    overlaid (never one in an unknown energy frame or with an implausible step). Written once: a run folder is never
    rewritten. The file entry (role ``plot``), or ``None`` when no plot can be drawn."""
    if not (A.frame_known(v) and A.plausible(v)):
        return None
    path = gdir / f"plot_athena_v{n:02d}.png"
    if not path.is_file():
        try:
            from .plot import review_plot

            if not review_plot(path, title=f"{group['group_id']} ({group.get('role')}) {', '.join(stems)[:50]} + Athena v{n:02d}",
                               grid=grid, M=M, merged=mg["mean"], point_flags=dg["point_flags"],
                               scan_flags=dg["scan_flags"], norm=nm["norm"], flat=nm["flat"], e0=nm["e0_eV"],
                               athena=v, np=np):
                return None
        except Exception:  # noqa: BLE001 - a plot failure is never a processing failure
            return None
    return {"role": "plot", "relative_path": PurePosixPath(path.relative_to(bundle_dir)).as_posix(), "sha256": sha256_file(path)}


#: review M1: an Athena result whose curve the SCIENTIST tied to its group (params athena_match): the review flag, the
#: statement key and the field that names the tie. A bulk approval refuses it (mutations.BULK_APPROVE_REVIEW), and its
#: approval records the tie in its note (mutations.decide). Not in a hashed file.
TIED_FLAG = "athena_named_by_scientist"
TIE_KEY = "athena_match_tie"


def _say_tie(res: dict, entry: Mapping, files: Sequence[Mapping]) -> None:
    """Review M1: on an Athena result of a TIED curve (match kind ``named_by_scientist``), the tie (project, Athena
    group, the run's params.json that records it), the flag :data:`TIED_FLAG` and one sentence."""
    if entry.get("_match_kind") != A.TIED_KIND:
        return
    params_file = next((f["relative_path"] for f in files if f.get("role") == "params"), None)
    tie = {"project": entry["prj_relative_path"], "athena_group": entry["group_name"], "athena_label": entry["label"],
           "by": f"the scientist's params file ({P.ATHENA_MATCH_SECTION})", "params_file": params_file}
    res[TIE_KEY] = tie
    if TIED_FLAG not in res["review_flags"]:
        res["review_flags"].append(TIED_FLAG)
    res["qc"].setdefault("statements", {})[TIED_FLAG] = (
        f"This curve is the scientist's Athena group '{entry['label']}' in {entry['prj_relative_path']}, tied to this "
        f"group by the scientist's params file ({P.ATHENA_MATCH_SECTION}), not by its name"
        + (f" (recorded in {params_file})" if params_file else "") + ". Approve it on its own, after the scientist "
        "confirms the tie; the approval records it.")


#: r1-a M3: an approved Athena-version result that is no longer the scientist's latest choice (on that stored result)
VERSION_NOT_CHOSEN_FLAG = "athena_version_no_longer_chosen"
_ISAAC_RESULT_ID = re.compile(r"^proc-(?P<group>.+)-r-[0-9a-f]{16}-isaac$")


def _group_selection(group_id: str, res: Mapping, bundle: Mapping | None) -> tuple[Mapping, str | None] | None:
    """``(decision, version id or None)``: the scientist's LATEST ``select_athena_version`` on ANY ISAAC result of this
    group (r1-a M2: a new params file or a calibration gives ISAAC's own result a new id; the choice must not be lost),
    resolved among the versions ``res`` lists now. A choice made on another result is resolved ONLY by the provenance
    it recorded (:func:`bundle.athena_resolve`: project file, Athena group, data hash), never by a position, so it is
    never carried over to another curve. ``None`` when the group has no choice."""
    bundle = bundle or {}
    mine = {B.processing_id(r) for r in bundle.get("processing_results") or ()
            if r.get("group_id") == group_id and r.get("source") == "isaac_protocol"} | {res.get("result_id")}
    latest = None
    for d in bundle.get("scientist_decisions") or ():
        t = d.get("target") if isinstance(d, Mapping) else None
        if d.get("decision") != B.ATHENA_SELECT_DECISION or not isinstance(t, Mapping) or t.get("kind") != "processing_result":
            continue
        m = _ISAAC_RESULT_ID.match(str(t.get("id")))
        if t.get("id") in mine or (m is not None and m.group("group") == group_id):
            latest = d
    if latest is None:
        return None
    elsewhere = (latest.get("target") or {}).get("id") != res.get("result_id")
    if elsewhere and not isinstance(latest.get("athena_version_provenance"), Mapping):
        return latest, None
    return latest, (B.athena_resolve(res, latest) if B.athena_version_ids(res) else None)


def _say_selection_not_carried_over(res: dict, decision: Mapping) -> None:
    """r1-a M2: on ``res``, say that the group's latest choice, made on another result, names no version listed now."""
    who = (decision.get("decided_by") or {}).get("name")
    lists = bool(B.athena_version_ids(res))
    said = (f"The scientist's latest choice of this group's Athena result of record, {decision.get('value')} "
            f"({decision.get('decision_id')}, by {who}, made on the earlier result "
            f"{(decision.get('target') or {}).get('id')}), is not one of the Athena versions this result lists now "
            "(matched by project file, Athena group and data hash), so it is not carried over to another curve"
            + (" and the question is asked again." if lists else "; this result lists no Athena versions to choose between now."))
    res[B.ATHENA_NOT_CARRIED_OVER] = {"decision_id": decision.get("decision_id"), "value": decision.get("value"),
                                      "decided_by": who, "statement": said}
    res["qc"].setdefault("statements", {})[B.ATHENA_NOT_CARRIED_OVER] = said
    for q in res.get("questions") or ():
        if isinstance(q, dict) and q.get("code") == B.ATHENA_QUESTION_CODE:
            q["text"] = f"{q.get('text', '')} {said}".strip()


def _choice_identity(decision: Mapping | None) -> str | None:
    if not isinstance(decision, Mapping):
        return None
    prov = decision.get("athena_version_provenance")
    if isinstance(prov, Mapping):
        return json.dumps({k: prov.get(k) for k in B.ATHENA_IDENTITY_KEYS}, sort_keys=True)
    return json.dumps({"decision_id": decision.get("decision_id")})


def _approved_other_versions(group_id: str, latest: Mapping, new_id: str, bundle: Mapping | None) -> list[dict]:
    """r1-a M3: the group's APPROVED Athena-version results (stored) whose version is not the one the scientist's
    ``latest`` choice names: ``[{result_id, version_id, chosen_in, statement}]``, the statement saying the order
    (reject the old result first, then approve ``new_id``)."""
    bundle = bundle or {}
    by_id = {d.get("decision_id"): d for d in bundle.get("scientist_decisions") or () if isinstance(d, Mapping)}
    want = _choice_identity(latest)
    out = []
    for r in bundle.get("processing_results") or ():
        if (r.get("group_id") != group_id or r.get("source") != "scientist_athena" or not r.get("athena_version_id")
                or r.get("state") != B.STATE_SCIENTIST_CONFIRMED or B.processing_id(r) == new_id):
            continue
        made = (r.get("athena_version_selected") or {}).get("decision_id")
        if made is not None and _choice_identity(by_id.get(made)) == want:
            continue  # the same version the latest choice names
        old = B.processing_id(r)
        out.append({"result_id": old, "version_id": r.get("athena_version_id"), "chosen_in": made,
                    "latest_decision_id": latest.get("decision_id"), "latest_value": latest.get("value"),
                    "new_result_id": new_id,
                    "statement": (f"{old} (version {r.get('athena_version_id')}, chosen earlier in {made}) is approved, "
                                  f"but the scientist's latest choice is {latest.get('value')} "
                                  f"({latest.get('decision_id')}). A record uses exactly one approved result: reject "
                                  f"{old} first, then approve {new_id}.")})
    return out


def _version_chosen_statement(listed: Mapping, decision: Mapping, vres: Mapping, res: Mapping) -> dict:
    """What choosing an Athena version did, in words, for the version's own result and for ISAAC's."""
    prov = listed.get("provenance") or {}
    who = (decision.get("decided_by") or {}).get("name")
    named = ", ".join(x for x in (prov.get("prj_file_name"), f"Athena group {prov['athena_group']}" if prov.get("athena_group") else None) if x)
    e0 = (vres.get("outputs") or {}).get("e0_eV")
    own = (res.get("outputs") or {}).get("e0_eV")
    e0_said = f"{e0:.3f} eV" if isinstance(e0, (int, float)) else "not stated"
    own_said = f"{own:.3f} eV" if isinstance(own, (int, float)) else "not stated"
    chose = f"The scientist chose {listed['version_id']} ({named}) as the result of record ({decision.get('decision_id')}, by {who})."
    return {
        "athena": (f"{chose} This result is that version: approving it makes the record carry its E0 ({e0_said}) and "
                   f"curve. ISAAC's own result for this group ({res['result_id']}) has E0 {own_said}."),
        "isaac": (f"{chose} Its own Athena result is {vres['result_id']} (E0 {e0_said}); this ISAAC result's E0 is "
                  f"{own_said}. The record carries the E0 and curve of whichever result is approved: approve "
                  f"{vres['result_id']} for the chosen version's."),
    }


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


#: r5 A1: the review flag of a scientist's Athena curve whose post-edge level fails (:func:`athena_post_edge_level`)
ATHENA_POST_EDGE_FLAG = "athena_post_edge_not_at_1"


def athena_post_edge_level(entry: Mapping, np) -> dict | None:
    """r5 A1: :func:`core.post_edge_level_implausible` on the scientist's Athena curve, over the project's own post-edge
    window (``nor1`` to ``nor2`` above its E0), in its frame (stored energy + ``bkg_eshift``). ``None`` when the level
    is plausible or cannot be judged (no E0 or window, too few points, a scan ending under 50 eV above E0), for a curve
    in an unknown energy frame, and for an already-normalised curve (it has its own check,
    ``core.stored_normalized_implausible``). Larch's ``norm`` is ``(mu - pre-edge line) / edge step``, so the line is
    ``mu - norm * step``: the rule is the one ISAAC's own curve is judged by. A SET of per-scan groups is a mean of
    the scientist's normalised curves: it is judged on that mean (line 0, step 1). Measured on a real BL4-3 beamtime:
    two Athena curves whose normalised spectrum reached 116 (post-edge level near 94) passed QC and were exported."""
    if not A.frame_known(entry) or A.already_normalized(entry):
        return None
    p = entry.get("params") or {}
    e, norm = np.asarray(entry["energy"], dtype=float), np.asarray(entry["norm"], dtype=float)
    if entry.get("_match_kind") == "per_scan_set" or e.size != np.asarray(entry["mu"]).size:
        mu, line, step = norm, np.zeros_like(norm), 1.0
    else:
        step = C._f(entry.get("edge_step"))
        if step is None or step <= 0:
            return None
        mu = np.asarray(entry["mu"], dtype=float)
        line = mu - norm * step
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        found = C.post_edge_level_implausible(e, mu, line, entry.get("e0_eV"), step, np, norm1=p.get("nor1"),
                                              norm2=p.get("nor2"))
    if not found:
        return None
    return {**found, "statement": ("This is the scientist's Athena curve, judged over the project's own post-edge range "
                                   "(nor1 to nor2). " + found["statement"])}


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
    renorm = entry.get(A.RENORMALISED_KEY)
    if A.already_normalized(entry):
        reproduced = (f"none: the group is already normalised (Athena is_nor), so its stored spectrum is used as stored, "
                      f"edge step 1 by definition ({A.ALREADY_NORMALIZED_RULE_ID})")
    elif entry.get(A.BASIS_KEY):
        # r5 H1 / review LOW 6: which way the curve was made, as Athena makes it (A.ATHENA_RENORM_RULE_ID)
        made = {A.BASIS_STORED: "the project's stored normalisation (its stored pre-edge line, post-edge curve and "
                                "edge step, which still fit the data)",
                A.BASIS_REFIT: "Athena's re-fit of the project's ranges (larch pre_edge with nnorm = bkg_nnorm - 1, "
                               "the stored step only when bkg_fixstep), the stored values no longer fitting the data"}
        counts = entry.get(A.BASIS_COUNTS_KEY) if members else None
        if isinstance(counts, Mapping) and counts:
            # r6 G3: a set names how many of its per-scan groups were made each way
            n_all = len(members.get("scans") or ()) or sum(counts.values())
            reproduced = "; ".join(f"for {n} of the {n_all} per-scan groups, {made.get(b, b)}"
                                   for b, n in sorted(counts.items())) + f" ({A.ATHENA_RENORM_RULE_ID})"
        else:
            reproduced = " and ".join(made.get(b, b) for b in str(entry[A.BASIS_KEY]).split("+")) + (
                f" ({A.ATHENA_RENORM_RULE_ID})")
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
    if members:
        # r3-b H3: ISAAC AVERAGED the scientist's per-scan curves: a merge step, so a record lists spectrum_merging (the
        # Athena result's steps are not in a hashed file: no id moves)
        res["steps"].append({"step": "merge",
                             "params": {"made_by": "ISAAC", "statistic": "mean of the scientist's per-scan Athena "
                                        "normalisations (norm, flat) and E0s, on the first group's energy points"},
                             "outcome": {"n_scans": len(members.get("scans") or ()),
                                         "athena_groups": list(members.get("athena_groups") or ())},
                             "flags": ["isaac_computed_mean_of_scientist_per_scan_curves"]})
    elif A.is_scientist_merge(entry):
        # the scientist merged in Athena (flagged is_merge, or a merge word in its name); how many scans is not stated
        res["steps"].append({"step": "merge",
                             "params": {"made_by": "the scientist, in Athena", "statistic": "not stated by the project"},
                             "outcome": {"n_scans": None, "basis": "athena_is_merge" if entry.get("is_merge") else
                                         "merge_word_in_athena_name"},
                             "flags": ["scientist_merge"]})
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
    level = None if bad else athena_post_edge_level(entry, np)
    if level:
        # r5 A1: only when the check fails (absent otherwise, as for ISAAC's own curve): the QC fails post_edge_not_at_1
        metrics["post_edge_level"] = level["level"]
    verdict, reasons = C.qc_verdict(metrics, params)
    res["qc"] = {"metrics": metrics, "verdict": verdict, "reasons": reasons}
    res["qc"]["statements"] = {"scans_used": scans_used["statement"]}
    if bad:
        res["qc"]["statements"]["edge_step_implausible"] = bad["statement"]
        res["review_flags"].append("edge_step_implausible")
    if level:
        res["qc"]["statements"]["post_edge_not_at_1"] = level["statement"]
        res["review_flags"].append(ATHENA_POST_EDGE_FLAG)
    if renorm:
        # r5 H1: ISAAC made the curve as Athena makes it, never a fault of the scientist's. r6 G4: recorded on the
        # result (with the post-edge difference and whether it is material, athena.ATHENA_RENORM_MATERIAL) and said
        # ONCE for the bundle (renormalisation_line), never flagged on each result. Measured on a real BL4-3 beamtime:
        # the flag was on 16 of 16 Athena results, and 16 of 18 now differ by more than 2 % of the step at the
        # post-edge (larch's step is a few percent off on nearly every group), so a threshold would not thin it out.
        res[A.RENORMALISED_KEY] = {k: v for k, v in renorm.items() if k != "statement"}
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
    longer live: rejected, merged, split). A rejected one still takes part in the Athena name match; a group
    merged away (``merged``/``split``) does not (r5 A2, :func:`athena.takes_part`): its runs are a live group's,
    and its stems made that live group's Athena groups ambiguous.

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
    # r3-b M5: ``group_ids`` selects what is PROCESSED; every group still takes part in the Athena name match (as
    # ``skip_group_ids`` always did), so a named group's match is the one a full run makes and the Athena statement
    # can count the whole project
    wanted = set(group_ids) if group_ids else None
    runs_by_key = {r["run_key"]: r for r in bundle.get("runs") or ()}
    sources = {s["source_id"]: s for s in bundle.get("sources") or () if s.get("source_id")}
    ctx = _Ctx(bundle=bundle, bundle_dir=bundle_dir, root=root, params=resolved, np=np, xafs=xafs, out_dir=out_dir, sources=sources, runs_by_key=runs_by_key)
    ctx.scan_reader = scan_reader or read_scan_file
    ctx.calibration_approvals = dict(calibration_approvals or {})
    ctx.exclusions = P.scan_exclusions(params)  # r4-a M6: scans a params file leaves out of a named group's merge

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
    # r6 G1: the Athena groups the SCIENTIST named for a group (params athena_match); never a near name
    # (with no Athena group read, each named tie is said as naming nothing)
    ties, tie_rows = A.resolve_ties(P.athena_match_ties(params), entries, all_groups)
    # review LOW 4: the scientist's "no" (params athena_match_not): that merge is no longer hinted for that group
    nots, not_rows = A.resolve_ties(P.athena_match_ties(params, P.ATHENA_MATCH_NOT_SECTION), entries, all_groups,
                                    not_this=True)
    for row in tie_rows:
        if row["status"] == "tied":
            ctx.athena_ties.setdefault(row["group_id"], []).append(
                {"project": entries[row["entry_index"]]["prj_relative_path"],
                 "athena_group": entries[row["entry_index"]]["group_name"]})
    matched, m_notes, versions = A.match_with_versions(all_groups, entries, np, ties=ties)
    # r7 K5: the scientist's merges set aside as no group's (params athena_ignore): no longer listed
    ignored, ignore_rows = A.resolve_ignores(P.athena_ignores(params), entries, all_groups, tied=ties)
    unmatched = A.unmatched_merges(all_groups, entries, tied=ties, not_this=nots, ignored=ignored)
    # r7 K1: each names the live groups whose Athena groups are in the same project (where the merge was made)
    project_groups(unmatched, all_groups, entries, ties=ties)
    # r7 K3: reference channels ("  Ref <name>") are no sample merges: counted, never listed or hinted
    ref_channels = A.unmatched_reference_channels(all_groups, entries, tied=ties)

    # THE SERIES PASS (scan selection): every group's energy scans, so a group's series E0 is the same whichever
    # groups this call processes
    if SCAN_SELECTION_ENABLED:
        ctx.scan_series = scan_selection_series(all_groups, ctx)
    results, unread_results = [], []
    skipped = set(skip_group_ids or ())
    for g in all_groups:
        if g["group_id"] in skipped and g.get("group_kind") not in ("unread_acquisition", "generic_run"):
            continue
        if wanted is not None and g["group_id"] not in wanted:
            continue
        try:
            out = process_group(g, ctx, matched.get(g["group_id"]), athena_versions=versions.get(g["group_id"]))
        except Exception as exc:  # noqa: BLE001 - one group's crash is that group's failure, never a pass
            out = [_fail(_base(g, "isaac_protocol"), "processing_error", f"{type(exc).__name__}: {exc}"[:500])]
        for r in out:
            _null_non_finite(r)
        (unread_results if g.get("group_kind") in ("unread_acquisition", "generic_run") else results).extend(out)

    unknown_excl = sorted(set(ctx.exclusions) - {g["group_id"] for g in all_groups})
    fixed_said = possibly_fixed_athena_e0(results, bundle, all_groups, entries)
    processed = {r.get("group_id") for r in results + unread_results}

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
            # the groups processed in this call (all of them without --group)
            "record_groups_matched": len([g for g in matched if g in processed]),
            "record_groups_with_unselected_versions": len([g for g in versions if g in processed]),
            "notes": (a_notes + m_notes)[:500],
            "match_rule": A.MATCH_RULE_ID,
            "statement": athena_match_statement(all_groups, entries, matched={**versions, **matched}, notes=m_notes,
                                                processed=processed, stored=bundle.get("processing_results") or (),
                                                ties=ties),
            # r6 G1: the scientist's merges that match no group by name, with near-name hints (never matched)
            **({"unmatched_merges": unmatched[:UNMATCHED_STORED], "unmatched_merges_total": len(unmatched)}
               if unmatched else {}),
            **({"athena_match": [{k: v for k, v in r.items() if k != "entry_index"} for r in tie_rows]} if tie_rows else {}),
            **({"athena_match_not": [{k: v for k, v in r.items() if k != "entry_index"} for r in not_rows]}
               if not_rows else {}),
            **({"athena_ignore": ignore_rows} if ignore_rows else {}),
            **({"unmatched_reference_channels": {"count": len(ref_channels), "rule": A.REFERENCE_CHANNEL_RULE_ID,
                                                 "labels": [i["athena_label"] for i in ref_channels[:50]]}}
               if ref_channels else {}),
        },
        **({SCAN_SERIES_KEY: {"rule_id": C.SCAN_SELECTION_RULE_ID,
                              "series": list((ctx.scan_series or {}).get("series", {}).values())}}
           if ctx.scan_series is not None else {}),
        "processing_results": results,
        "unread_acquisition_results": unread_results,
        "summary": summarize(results + unread_results),
    }
    if payload["athena"]["statement"]:
        payload["summary"]["lines"].append(payload["athena"]["statement"])
    kept_notes: list[dict] = []
    payload["summary"]["lines"].extend(r["statement"] for r in tie_rows + not_rows
                                       if r["status"] not in ("tied", "not_this_group") or r.get("also_matches_by_name"))
    # review M1: a group whose merge is tied now, or was tied in its decided result, is not asked again
    decided = _decided_ids(bundle)
    settled = set(ctx.athena_ties) | {
        r.get("group_id") for r in bundle.get("processing_results") or ()
        if r.get("source") == "scientist_athena" and B.processing_id(r) in decided
        and ((r.get("inputs") or [{}])[0] or {}).get("match_kind") == A.TIED_KIND}
    several_line = several_groups_line(m_notes, all_groups, bundle)
    if several_line:
        payload["summary"]["lines"].append(several_line)
    if unmatched or ref_channels:
        line = unmatched_merges_line(unmatched, reference_channels=len(ref_channels))
        payload["athena"]["unmatched_merges_statement"] = line
        payload["summary"]["lines"].append(line)
    ignore_line = athena_ignore_line(ignore_rows)
    if ignore_line:
        payload["summary"]["lines"].append(ignore_line)
    kept_notes += say_unmatched_merges(results, unmatched, settled=settled, stored=bundle.get("processing_results") or ())
    kept_notes += version_plot_notes(results, stored=bundle.get("processing_results") or ())
    renorm_line = renormalisation_line(results)
    if renorm_line:
        payload["summary"]["lines"].append(renorm_line)
    if fixed_said:
        kept_notes += fixed_said.pop("kept_result_notes")
        payload["athena"]["e0_possibly_fixed"] = fixed_said
        if fixed_said["statement"]:
            payload["summary"]["lines"].append(fixed_said["statement"])
        # r1-a M5: a stored result that stays as it was (decided, or not processed now) is said apart, by its own id
        payload["summary"]["lines"].extend(kept_fixed_e0_lines(fixed_said["kept_results"], wanted))
    stored_by_id = {B.processing_id(r): r for r in bundle.get("processing_results") or ()}
    for r in results:
        for x in r.get("athena_version_replaces_approved") or ():
            # r1-a M3: the approved result of an earlier choice no longer says it is the scientist's choice
            payload["summary"]["lines"].append(f"Athena: {x['statement']}")
            said = (f"This result is version {x['version_id']}, which the scientist chose earlier ({x['chosen_in']}) "
                    f"and approved. It is no longer the scientist's choice: the latest is {x['latest_value']} "
                    f"({x['latest_decision_id']}). A record uses exactly one approved result: reject {x['result_id']} "
                    f"first, then approve {x['new_result_id']}.")
            sel = dict((stored_by_id.get(x["result_id"]) or {}).get("athena_version_selected") or {})
            kept_notes.append({"result_id": x["result_id"], "add_review_flags": [VERSION_NOT_CHOSEN_FLAG],
                               "statements": {"athena_version_selected": said},
                               "fields": {"athena_version_selected": {**sel, "statement": said,
                                                                      "superseded_by_decision_id": x["latest_decision_id"],
                                                                      "superseded_by_result_id": x["new_result_id"]}}})
    for r in results:
        if r.get("source") == "scientist_athena" and ATHENA_POST_EDGE_FLAG in (r.get("review_flags") or ()):
            # r5 M1: a result of this id decided before the check is KEPT as it was (mutations.process): it carries
            # the flag and the sentence (outside the hashed files; its stored verdict is not rewritten)
            said = ((r.get("qc") or {}).get("statements") or {}).get("post_edge_not_at_1") or ""
            kept_notes.append({"result_id": r["result_id"], "add_review_flags": [ATHENA_POST_EDGE_FLAG],
                               "statements": {"post_edge_not_at_1": (
                                   f"{said} This result was decided before this check, so its stored QC verdict stays "
                                   "as it was recorded; the curve fails it now. A person reviews the decision: reject "
                                   "it, or mark it needs_changes.").strip()}})
    not_carried = [r for r in results if isinstance(r.get(B.ATHENA_NOT_CARRIED_OVER), Mapping)]
    if not_carried:
        # r1-a M2: a choice made on another ISAAC result of the group that names no version listed now
        line = (f"Athena: {len(not_carried)} earlier choice(s) of the Athena result of record, made on an earlier ISAAC "
                "result of the group, no longer match a version ISAAC lists ("
                + "; ".join(f"{r['result_id']}: {r[B.ATHENA_NOT_CARRIED_OVER]['value']} "
                            f"({r[B.ATHENA_NOT_CARRIED_OVER]['decision_id']})" for r in not_carried)
                + "): not carried over to another curve; where versions are listed, the question is asked again.")
        payload["athena_selections_not_carried_over"] = {
            "results": [{"result_id": r["result_id"], "decision_id": r[B.ATHENA_NOT_CARRIED_OVER]["decision_id"],
                         "value": r[B.ATHENA_NOT_CARRIED_OVER]["value"]} for r in not_carried],
            "statement": line}
        payload["summary"]["lines"].append(line)
    if kept_notes:
        # for the STORED results `isaac process` keeps as they were: apply_kept_result_notes (outside the hashed files)
        payload["kept_result_notes"] = kept_notes
    payload["summary"]["lines"].extend(REF.ignored_overrides(resolved))  # c12-r: an ignored override is said once
    if unknown_excl:
        # r4-a review: an exclude_scans group id that is no group of this bundle left nothing out
        payload["summary"]["lines"].append(
            f"The params file's {P.EXCLUDE_SCANS_SECTION} names {', '.join(repr(g) for g in unknown_excl)}, which "
            f"{'is' if len(unknown_excl) == 1 else 'are'} no record group of this bundle: nothing was left out for "
            f"{'it' if len(unknown_excl) == 1 else 'them'}. Check the group id (`isaac bundle list <bundle_dir> groups`).")
    _write(out_dir / RESULTS_FILE, _json_bytes(payload))
    return payload


_STATED_SUFFIXES = 3

#: r1-a M5: an Athena E0 IDENTICAL (to :data:`FIXED_E0_DECIMALS`) in DIFFERENT Athena curves of one beamtime, while
#: ISAAC's own E0s for those groups (each with a QC verdict of pass or warn) differ by at least
#: :data:`FIXED_E0_MIN_ISAAC_SPREAD_EV`, is likely a FIXED normalisation setting (an E0 typed or carried over in Athena),
#: not a measured edge position. Measured on a real BL4-3 sulfur beamtime: an elemental standard and two samples carried
#: one Athena E0 while ISAAC measured the last about 1 eV away, and it was exported as the edge position. Names are
#: never read for that comparison (r1-a review: one sample named two ways was flagged as different chemistry).
#:
#: r3-b M3: the E0s of EVERY Athena group of the result's own project count too, matched to a group or not (measured on
#: a real BL4-3 beamtime: one project gave one E0 to four samples' groups; three of those groups were rejected before
#: processing, so no other Athena RESULT carried it and the flag never fired). Such a group counts only
#: when it is ANOTHER SAMPLE (:func:`_sample_key`: names equal apart from counters, scan-file and merge words are one
#: sample's repeats, never other samples) and the E0 is not where its own edge is: ISAAC's own E0 for its record group,
#: where one exists and this group has one too, differs from this group's by at least the same 0.5 eV, or else its own
#: stored data's edge (larch find_e0 near the E0, ``athena.load_project``) is 0.5 eV or more from that E0. And never
#: when THIS curve's own data puts its edge within 0.5 eV of it (r3-d L-2: in the Athena E0's own frame; ISAAC's E0
#: only when the project gives none): there the E0 is where this group's edge is (two samples' E0s on one grid point
#: are no setting).
FIXED_E0_RULE_ID = "isaac.athena.e0_possibly_fixed.v0"
FIXED_E0_FLAG = "athena_e0_possibly_fixed"
FIXED_E0_QUESTION = "athena_e0_measured_or_set"
FIXED_E0_DECIMALS = 3
#: more than one curve's E0 moves by landing on a grid point or by noise
FIXED_E0_MIN_ISAAC_SPREAD_EV = 0.5
_FIXED_E0_GROUPS_SAID = 5
_QC_SAID = "(each with a QC verdict of pass or warn)"
_SAMPLE_NOISE = re.compile(r"^(" + A._MERGE_WORD + r")\d*$")


def _sample_key(label: str) -> str:
    """r3-b M3: what an Athena label says its SAMPLE is, for telling repeats of one sample from different samples: the
    normalised name without its XDC scan-file suffix (``_a_001``), whole-number tokens (counters), a trailing XDAC
    letter and merge words. ``""`` when nothing is left (such a name is never counted as another sample)."""
    n = re.sub(r"_a_\d+$", "", A.normalise_name(str(label or "")))
    toks = [t for t in n.split("_") if t and not t.isdigit() and not _SAMPLE_NOISE.match(t)]
    if toks and toks[-1] == "a":
        toks = toks[:-1]
    return "_".join(toks)


def _decided_ids(bundle: Mapping) -> set[str]:
    """The processing results a scientist decided (approve / reject / needs_changes / defer): ``isaac process`` keeps
    each as stored, and a fresh result of the same id is not stored."""
    return {str((d.get("target") or {}).get("id")) for d in bundle.get("scientist_decisions") or ()
            if isinstance(d, Mapping) and (d.get("target") or {}).get("kind") == "processing_result"
            and d.get("decision") in B.PROCESSING_STATE_DECISIONS}


def _athena_curve(r: Mapping) -> str:
    """The curve an Athena result is (its project file, Athena group, a set's members): one curve matched to two
    groups is ONE curve, never an E0 shared across curves."""
    i = (r.get("inputs") or [{}])[0] or {}
    return json.dumps([i.get("relative_path"), i.get("athena_group"), i.get("per_scan_set")], sort_keys=True, default=str)


def possibly_fixed_athena_e0(results: list[dict], bundle: Mapping, groups: Sequence[Mapping],
                             entries: Sequence[Mapping] = ()) -> dict | None:
    """Flag (:data:`FIXED_E0_FLAG`) each Athena result whose E0 equals, to :data:`FIXED_E0_DECIMALS`, the Athena E0 of
    a DIFFERENT Athena curve of another group of the beamtime while ISAAC's own E0s for those groups (QC pass or warn)
    differ by at least :data:`FIXED_E0_MIN_ISAAC_SPREAD_EV`, or (r3-b M3) the E0 of other Athena groups of its own
    project (``entries``: every group read, matched or not) as set out at :data:`FIXED_E0_RULE_ID`. Compared: this
    run's Athena results and the stored ones that stay stored (a decided result, or a group not processed now), never a
    rejected result nor one of a superseded or non-live group. A flagged result of this run is not preferred for the
    record, says why (``qc.statements``, ``athena_e0_possibly_fixed``) and asks whether the E0 was measured or set
    (``questions``). A STORED result that would be flagged is said apart (``kept_results``) and its flag and sentence
    are returned as ``kept_result_notes`` (:func:`apply_kept_result_notes`), since ``isaac process`` keeps it as
    stored. Nothing hashed changes. Returns a summary (or ``None``)."""
    bundle = bundle or {}
    stored = list(bundle.get("processing_results") or ())
    decided = _decided_ids(bundle)
    superseded = {g.get("group_id") for g in bundle.get("superseded_record_groups") or ()}
    status = {g.get("group_id"): g.get("status") for g in [*(bundle.get("record_groups") or ()), *groups]}

    def live(gid):
        return gid not in superseded and gid in status and (status[gid] or "proposed") in B.LIVE_GROUP_STATUSES

    pool = [*results, *stored]

    def _measured(sib) -> float | None:
        if sib is None or (sib.get("qc") or {}).get("verdict") not in ("pass", "warn"):
            return None  # only an ISAAC E0 whose QC did not fail (pass or warn) is a measurement to compare
        v = (sib.get("outputs") or {}).get("e0_eV")
        return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None

    def own_e0(r):
        return _measured(next((x for x in pool if x.get("source") == "isaac_protocol" and x.get("group_id") == r.get("group_id")
                               and x.get("run_id") == r.get("run_id")), None))

    def group_e0(gid):
        # r3-b M3: an Athena group's record group (matched or not processed now): its ISAAC E0, this run's first
        return _measured(next((x for x in pool if x.get("source") == "isaac_protocol" and x.get("group_id") == gid), None))

    def athena_e0(r):
        v = (r.get("outputs") or {}).get("e0_eV")
        return round(float(v), FIXED_E0_DECIMALS) if isinstance(v, (int, float)) and math.isfinite(v) else None

    now = {r.get("group_id") for r in results}
    stored_ids = {B.processing_id(r) for r in stored}
    rows = [(r, False) for r in results if r.get("source") == "scientist_athena"
            and not (B.processing_id(r) in decided and B.processing_id(r) in stored_ids)]  # else the stored one stays
    rows += [(r, True) for r in stored if r.get("source") == "scientist_athena" and r.get("state") != B.STATE_REJECTED
             and live(r.get("group_id")) and (r.get("group_id") not in now or B.processing_id(r) in decided)]
    by_group = {g.get("group_id"): g for g in groups}

    def name(gid):
        g = by_group.get(gid) or {}
        return next((str(s) for s in g.get("_stems") or () if s), None) or str(gid)

    # r3-b M3: every Athena group read, by (project, E0), and the record group each matches (if exactly one)
    egroup = A.entry_groups(groups, entries) if entries else {}
    in_project: dict[tuple, list[int]] = {}
    for i, e in enumerate(entries):
        v = e.get("e0_eV")
        if isinstance(v, (int, float)) and math.isfinite(v):
            in_project.setdefault((e.get("prj_relative_path"), round(float(v), FIXED_E0_DECIMALS)), []).append(i)

    def project_partners(r, value) -> list[dict]:
        """Other samples' Athena groups of r's own project that carry its E0 and count (:data:`FIXED_E0_RULE_ID`)."""
        inp = (r.get("inputs") or [{}])[0] or {}
        members = inp.get("per_scan_set") if isinstance(inp.get("per_scan_set"), Mapping) else {}
        mine_groups = set(members.get("athena_groups") or ()) | {inp.get("athena_group")}
        keys = {_sample_key(x) for x in (members.get("labels") or [inp.get("scan")])} - {""}
        gid, mine = r.get("group_id"), own_e0(r)
        # r3-d L-2: where this curve's OWN data puts its edge, in the scientist's frame (the Athena E0's frame, with
        # bkg_eshift); ISAAC's E0 (its own, uncalibrated frame) only when the project gives no such edge for this curve
        here = [float(e["data_e0_eV"]) for e in entries if e.get("prj_relative_path") == inp.get("relative_path")
                and e.get("group_name") in mine_groups and isinstance(e.get("data_e0_eV"), (int, float))
                and math.isfinite(e["data_e0_eV"])]
        at = float(statistics.median(here)) if here else mine
        if at is not None and abs(at - value) < FIXED_E0_MIN_ISAAC_SPREAD_EV:
            return []  # this group's edge is there: the E0 is where its edge is
        found: list[dict] = []
        for i in in_project.get((inp.get("relative_path"), value), ()):
            e = entries[i]
            key = _sample_key(e.get("label"))
            if e.get("group_name") in mine_groups or egroup.get(i) == gid or not key or key in keys:
                continue  # this curve, this group, or a repeat of this sample: never another sample's E0
            theirs = group_e0(egroup[i]) if i in egroup else None
            edge = e.get("data_e0_eV")
            by_isaac = theirs is not None and mine is not None
            if by_isaac:
                if abs(mine - theirs) < FIXED_E0_MIN_ISAAC_SPREAD_EV:
                    continue  # an ISAAC E0 that exists must differ, as for the results above
            elif edge is None or abs(edge - value) < FIXED_E0_MIN_ISAAC_SPREAD_EV:
                # no two ISAAC E0s to compare (r3-d L-2: also when this group's own ISAAC QC failed, never a skip): its
                # own data must put its edge elsewhere
                continue
            found.append({"athena_label": e.get("label"), "athena_group": e.get("group_name"), "sample_key": key,
                          "group_id": egroup.get(i), "isaac_e0_eV": theirs,
                          "basis": "isaac_e0" if by_isaac else "own_data_edge",
                          "own_data_e0_eV": round(float(edge), FIXED_E0_DECIMALS) if edge is not None else None})
        return found

    flagged, kept, notes = [], [], []
    by_value: dict[float, list] = {}
    for r, is_kept in rows:
        if athena_e0(r) is not None:
            by_value.setdefault(athena_e0(r), []).append((r, is_kept))
    for value in sorted(by_value):
        same = by_value[value]
        own = {}
        for r, _ in same:
            if own.get(r.get("group_id")) is None:
                own[r.get("group_id")] = own_e0(r)
        curves: dict[str, set] = {}
        for r, _ in same:
            curves.setdefault(_athena_curve(r), set()).add(r.get("group_id"))

        def partners(curve):
            # other curves holding a group whose ISAAC E0 differs from one of this curve's groups by the minimum
            mine = [own[g] for g in curves[curve] if own.get(g) is not None]
            return [c for c, gids in curves.items() if c != curve and any(
                abs(a - own[g]) >= FIXED_E0_MIN_ISAAC_SPREAD_EV for g in gids - curves[curve] if own.get(g) is not None
                for a in mine)]

        for r, is_kept in same:
            gid, curve = r.get("group_id"), _athena_curve(r)
            others_c = partners(curve)
            mine = own.get(gid)
            if others_c:
                others = sorted({g for c in others_c for g in curves[c]} - {gid})
                known = [own[g] for g in [gid, *others] if own.get(g) is not None]
                spread = max(known) - min(known)
                listed = ", ".join(f"{name(g)} (ISAAC {own[g]:.3f} eV)" if own.get(g) is not None else name(g)
                                   for g in others[:_FIXED_E0_GROUPS_SAID])
                listed += f" and {len(others) - _FIXED_E0_GROUPS_SAID} more" if len(others) > _FIXED_E0_GROUPS_SAID else ""
                said = (f"The scientist's Athena E0 here, {value:.{FIXED_E0_DECIMALS}f} eV, is exactly the Athena E0 of "
                        f"{len(others)} other group{'' if len(others) == 1 else 's'} of this beamtime ({listed}), in a "
                        f"different Athena curve, while ISAAC's own E0s for these groups {_QC_SAID} span "
                        f"{spread:.2f} eV" + (f" (ISAAC measures {mine:.3f} eV here)" if mine is not None else "")
                        + ". An E0 identical across different curves is likely a fixed normalisation setting (typed or "
                        "carried over in Athena), not a measured edge position")
                info = {"rule_id": FIXED_E0_RULE_ID, "athena_e0_eV": value, "decimals": FIXED_E0_DECIMALS,
                        "groups": [{"group_id": g, "athena_e0_eV": value, "isaac_e0_eV": own.get(g)} for g in [gid, *others]],
                        "isaac_e0_spread_eV": spread, "min_isaac_spread_eV": FIXED_E0_MIN_ISAAC_SPREAD_EV}
                why = (f"the same in {len(others)} other group(s) whose ISAAC E0s span {spread:.2f} eV")
                asked = (f"The same Athena E0 is in {len(others)} other group{'' if len(others) == 1 else 's'}' Athena "
                         f"curve{'' if len(others) == 1 else 's'}, while ISAAC's own E0s for these groups (QC pass or "
                         f"warn) span {spread:.2f} eV.")
            else:
                found = project_partners(r, value)
                if not found:
                    continue
                prj = PurePosixPath(str(((r.get("inputs") or [{}])[0] or {}).get("relative_path") or "")).name
                n = len(found)
                listed = ", ".join(f"'{f['athena_label']}'" + (f" (ISAAC {f['isaac_e0_eV']:.3f} eV)" if f["basis"] == "isaac_e0"
                                                             else f" (its own edge at {f['own_data_e0_eV']:.3f} eV)")
                                   for f in found[:_FIXED_E0_GROUPS_SAID])
                listed += f" and {n - _FIXED_E0_GROUPS_SAID} more" if n > _FIXED_E0_GROUPS_SAID else ""
                said = (f"The scientist's Athena E0 here, {value:.{FIXED_E0_DECIMALS}f} eV, is exactly the Athena E0 of "
                        f"{n} other Athena group{'' if n == 1 else 's'} of other samples in the same project ({prj}: "
                        f"{listed}), matched to a record group or not, whose own edges are not there (ISAAC's E0 for "
                        f"its record group {_QC_SAID}, else the edge of its own stored data, {FIXED_E0_MIN_ISAAC_SPREAD_EV:g} "
                        "eV or more away)"
                        + (f"; ISAAC measures {mine:.3f} eV here" if mine is not None else "")
                        + ". An E0 identical across different samples' curves is likely a fixed normalisation setting "
                        "(typed or carried over in Athena), not a measured edge position")
                info = {"rule_id": FIXED_E0_RULE_ID, "athena_e0_eV": value, "decimals": FIXED_E0_DECIMALS,
                        "groups": [{"group_id": gid, "athena_e0_eV": value, "isaac_e0_eV": mine}],
                        "same_project": {"prj_relative_path": ((r.get("inputs") or [{}])[0] or {}).get("relative_path"),
                                         "athena_groups": found},
                        "min_isaac_spread_eV": FIXED_E0_MIN_ISAAC_SPREAD_EV}
                why = f"the same in {n} other sample(s)' Athena group(s) of {prj}"
                asked = (f"The same Athena E0 is in {n} other Athena group{'' if n == 1 else 's'} of other samples in "
                         f"{prj}.")
            pid = B.processing_id(r)
            if is_kept:
                state = r.get("state")
                what = "approved result" if state == B.STATE_SCIENTIST_CONFIRMED else f"stored result ({state})"
                line = (f"Athena: {what} {pid} carries a possibly fixed Athena E0 ({value:.{FIXED_E0_DECIMALS}f} eV, "
                        f"{why}); ask the scientist whether it was measured.")
                kept.append({"result_id": pid, "group_id": gid, "state": state, "statement": line})
                notes.append({"result_id": pid, "rule_id": FIXED_E0_RULE_ID, "add_review_flags": [FIXED_E0_FLAG],
                              "statements": {FIXED_E0_FLAG: (f"{said}. This result was kept as it was decided "
                                                             f"({state}): ask the scientist whether this E0 was measured "
                                                             "or set; if it was set, it is not this group's edge position.")},
                              "fields": {"athena_e0_possibly_fixed": {**info, "statement": line}}})
                continue
            said += (", so this result is not preferred for the record. Before approving it, ask the scientist whether "
                     "this E0 was measured or set; if it was set, it is not this group's edge position.")
            r.setdefault("review_flags", []).append(FIXED_E0_FLAG)
            r["preferred_for_record"] = False
            r.setdefault("qc", {}).setdefault("statements", {})[FIXED_E0_FLAG] = said
            r["athena_e0_possibly_fixed"] = {**info, "statement": said}
            r["questions"] = [*(r.get("questions") or ()), {
                "code": FIXED_E0_QUESTION,
                "text": (f"Was the Athena E0 of {value:.{FIXED_E0_DECIMALS}f} eV measured from this group's own edge, or "
                         f"set (typed, or carried over from another group) in Athena? {asked}")}]
            flagged.append(pid)
    if not flagged and not kept:
        return None
    line = None
    if flagged:
        line = (f"Athena: {len(flagged)} of the scientist's Athena result(s) carry an E0 identical to other curves' "
                f"(of groups whose ISAAC E0s differ by {FIXED_E0_MIN_ISAAC_SPREAD_EV:g} eV or more, or of other samples "
                f"in the same Athena project): likely a fixed normalisation setting, not a measured edge position (flag "
                f"{FIXED_E0_FLAG}); ask the scientist before approving them.")
    return {"rule_id": FIXED_E0_RULE_ID, "results": flagged, "kept_results": kept, "kept_result_notes": notes,
            "statement": line}


def kept_fixed_e0_lines(kept: Sequence[Mapping], wanted: set | None) -> list[str]:
    """The summary lines for STORED results flagged by :func:`possibly_fixed_athena_e0` (``kept_results``): each by
    its own id; r4-a L1: with ``--group`` (``wanted``), only the named groups' by id and the other groups' in one count
    line (a real beamtime printed 67 such lines, about other groups, for one named group)."""
    if wanted is None:
        return [k["statement"] for k in kept]
    rest = [k for k in kept if k.get("group_id") not in wanted]
    lines = [k["statement"] for k in kept if k.get("group_id") in wanted]
    if rest:
        groups = len({k.get("group_id") for k in rest})
        lines.append(f"Athena: {len(rest)} more stored result{'' if len(rest) == 1 else 's'} of {groups} "
                     f"group{'' if groups == 1 else 's'} not processed now carr{'ies' if len(rest) == 1 else 'y'} a "
                     f"possibly fixed Athena E0 (flag {FIXED_E0_FLAG}); `isaac bundle list <bundle_dir> processing-results` "
                     "lists them. Ask the scientist whether each E0 was measured before approving one.")
    return lines


def apply_kept_result_notes(results: Sequence[dict], notes: Sequence[Mapping]) -> int:
    """Apply ``kept_result_notes`` (from :func:`process_bundle`) to the STORED results ``isaac process`` keeps as they
    were (a decided result, a group not processed now): each note's ``add_review_flags`` (no duplicates),
    ``statements`` (into ``qc.statements``) and ``fields`` (set on the result). All outside the hashed files, so no id
    moves and no decision changes. Review LOW 3: ``remove_review_flags`` and ``remove_statements`` take off a flag and
    a sentence that no longer hold. Returns how many results were changed. Stdlib only (``mutations.process`` calls
    it on the results it keeps)."""
    by_id: dict[str, list[Mapping]] = {}
    for n in notes or ():
        if isinstance(n, Mapping) and n.get("result_id"):
            by_id.setdefault(str(n["result_id"]), []).append(n)
    changed = 0
    for r in results:
        mine = by_id.get(B.processing_id(r))
        if not mine:
            continue
        for n in mine:
            flags = r.setdefault("review_flags", [])
            flags.extend(f for f in n.get("add_review_flags") or () if f not in flags)
            # review LOW 3: a sentence and flag that no longer hold are taken off (outside the hashed files too)
            gone = set(n.get("remove_review_flags") or ())
            if gone:
                r["review_flags"] = [f for f in flags if f not in gone]
            said = r.setdefault("qc", {}).setdefault("statements", {})
            for k in n.get("remove_statements") or ():
                said.pop(k, None)
            said.update(dict(n.get("statements") or {}))
            r.update(copy.deepcopy(dict(n.get("fields") or {})))
        changed += 1
    return changed


def _stored_athena_matches(stored: Sequence[Mapping]) -> set[tuple]:
    """r3-b M5: ``(project path, Athena group)`` of every Athena group a STORED result was matched to: an Athena result's
    input (and a set's members) and the versions an ISAAC result lists."""
    out: set[tuple] = set()

    def add(path, group, members):
        if path and group:
            out.add((str(path), str(group)))
        for m in (members or {}).get("athena_groups") or () if isinstance(members, Mapping) else ():
            out.add((str(path), str(m)))

    for r in stored or ():
        if not isinstance(r, Mapping):
            continue
        if r.get("source") == "scientist_athena":
            for i in r.get("inputs") or ():
                if isinstance(i, Mapping):
                    add(i.get("relative_path"), i.get("athena_group"), i.get("per_scan_set"))
        for v in r.get("athena_versions") or ():
            prov = (v or {}).get("provenance") or {} if isinstance(v, Mapping) else {}
            add(prov.get("prj_relative_path"), prov.get("athena_group"), prov.get("per_scan_set"))
    return out


def athena_match_statement(groups: Sequence[Mapping], entries: Sequence[Mapping], *, matched: Mapping, notes: Sequence[Mapping],
                           processed: Sequence[str] | set | None = None, stored: Sequence[Mapping] = (),
                           ties: Mapping[int, Sequence[str]] | None = None) -> str | None:
    """ONE LINE saying why the Athena groups that were read matched NO group processed now, or ``None`` when there
    were none to match or a group processed now matched. Names how many Athena names BEGIN with a group's scan
    name but end in a suffix the match rule does not accept (measured on a real BL4-3 beamtime: 161
    Athena groups named ``<scan>_a_001``, none matched under v0; v1 accepts that XDC scan-file suffix),
    and how many matched several groups. A name the rule accepts is never counted as a near miss.

    r3-b M5: scoped to the groups processed NOW (``processed``; every group when ``None``). An Athena group counts as
    matched when it matches a record group of the bundle (this run's match over every group) or a STORED result was
    matched to it (``stored``). When any is, the line says how many of the project's Athena groups match and that
    none of the groups processed now does; it never says "matched no record group" (measured: after ``process
    --group A --group B`` it did, while 6 groups held matched Athena results)."""
    if not entries:
        return None
    processed = set(processed) if processed is not None else {g.get("group_id") for g in groups}
    if any(g in processed for g in matched):
        return None
    of_group = A.entry_groups(groups, entries, ties=ties)
    held = _stored_athena_matches(stored)
    hit = {i for i, gid in of_group.items() if gid in matched} | {
        i for i, e in enumerate(entries) if (str(e.get("prj_relative_path")), str(e.get("group_name"))) in held}
    unmatched = [e for i, e in enumerate(entries) if i not in hit]
    stems = {A.normalise_name(s) for g in groups if g.get("_has_scans", True) for s in g.get("_stems") or ()}
    stems.discard("")
    near, suffixes = 0, []
    for e in unmatched:
        tails = [n[len(st):] for n in e.get("names") or () for st in stems
                 if n and n.startswith(st + "_") and not A.accepted_suffix(n[len(st) + 1:])]
        if tails:
            near += 1
            tail = min(tails, key=len)
            if tail not in suffixes:
                suffixes.append(tail)
    ambiguous = sum(1 for n in notes if n.get("code") == "athena_group_matches_several_record_groups")
    rule = ("(an Athena name equal to a group's scan name, or that name plus a scan or merge suffix such as _001 or "
            "_merged, or plus an XDC scan-file suffix such as _A.001)")
    if hit:
        n_now = len(processed)
        line = (f"Athena: none of the {n_now} group(s) processed now has an Athena match under rule {A.MATCH_RULE_ID} "
                f"{rule}; of the {len(entries)} Athena group(s) read, {len(hit)} match a record group (this run's match "
                f"over every group of the bundle, and the Athena results stored for groups not processed now) and "
                f"{len(unmatched)} match none")
    else:
        line = (f"Athena: {len(entries)} Athena group(s) were read and matched no record group under rule {A.MATCH_RULE_ID} "
                f"{rule}")
    if near:
        shown = ", ".join(f"'{t}'" for t in suffixes[:_STATED_SUFFIXES]) + (" …" if len(suffixes) > _STATED_SUFFIXES else "")
        line += f"; {near} of {'those' if hit else 'them'} begin with a group's scan name but end in a suffix the rule does not accept ({shown})"
    if ambiguous:
        line += f"; {ambiguous} matched several record groups, so none was used"
    if not near and not ambiguous and unmatched:
        line += f"; {'the other' if hit else 'their'} names are not the scan names"
    if hit:
        return line + ". No ISAAC result processed now was compared with the scientist's Athena processing."
    return line + ". No ISAAC result was compared with the scientist's Athena processing."


#: r6 G1: the statement key, review flag and question code of a group whose name is near a scientist's merge that
#: matched no group (athena.unmatched_merges). Said after the run id (never in a hashed file): no id moves.
UNMATCHED_MERGE_KEY = "athena_merge_not_matched"
UNMATCHED_MERGE_QUESTION = "athena_unmatched_merge_for_group"
_UNMATCHED_SAID = 8


def _merge_where(item: Mapping) -> str:
    names = list(dict.fromkeys(PurePosixPath(str(i["prj_relative_path"])).name for i in item["in"]))
    return ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")


def _tie_snippet(group_id: str, item: Mapping) -> str:
    first = item["in"][0]
    return json.dumps({P.ATHENA_MATCH_SECTION: {group_id: [{"project": first["prj_relative_path"],
                                                           "athena_group": first["athena_group"]}]}})


def _why_near(c: Mapping) -> str:
    why = []
    if c.get("shares_run_number"):
        why.append(f"it names this group's run number {c['group_name'].split('_', 1)[0]}")
    if c.get("shared_tokens"):
        why.append("it shares the words " + ", ".join(c["shared_tokens"][:6]))
    if not c.get("shares_run_number"):
        why.append(f"the names are {round(100 * float(c.get('similarity') or 0))} % alike")
    diff = c.get("differs_in") or {}
    if diff.get("merge") or diff.get("group"):
        # review M2: the difference is named plainly, so a likeness is never read as more than it is
        why.append("they differ in " + (", ".join(diff.get("merge") or ()) or "nothing") + " (the merge) against "
                   + (", ".join(diff.get("group") or ()) or "nothing") + " (the group)")
    return "; ".join(why)


#: how many unmatched merges processing_results.json keeps (review L5: the true count is stored beside it)
UNMATCHED_STORED = 500
#: r7 K1: how many live groups an unmatched merge names as sharing its project (``groups_in_project``)
_PROJECT_GROUPS_SAID = 10


def project_groups(items: Sequence[dict], groups: Sequence[Mapping], entries: Sequence[Mapping], *,
                   ties: Mapping[int, Sequence[str]] | None = None) -> None:
    """r7 K1: on each unmatched merge, ``groups_in_project``: the live record groups whose Athena groups (matched by
    name, or tied) are in a project the merge is in. Where the scientist made the merge; a hint of where to look, never
    a match."""
    of_group = A.entry_groups(groups, entries, ties=ties)
    live = {g["group_id"] for g in groups if A.hint_eligible(g)}
    by_prj: dict[str, set] = {}
    for i, gid in of_group.items():
        if gid in live:
            by_prj.setdefault(str(entries[i]["prj_relative_path"]), set()).add(gid)
    for item in items:
        got = sorted({g for x in item["in"] for g in by_prj.get(str(x["prj_relative_path"]), ())})
        item["groups_in_project"] = got[:_PROJECT_GROUPS_SAID]
        if len(got) > _PROJECT_GROUPS_SAID:
            item["groups_in_project_more"] = len(got) - _PROJECT_GROUPS_SAID


def _beside(item: Mapping) -> str:
    gids = list(item.get("groups_in_project") or ())
    if not gids:
        return "no group's Athena groups are in that project"
    more = int(item.get("groups_in_project_more") or 0) + max(0, len(gids) - 3)
    return "beside the Athena groups of " + ", ".join(gids[:3]) + (f" and {more} more" if more else "")


#: r7 K1: the command that pages every unmatched merge (the reply and the line show a few)
ATHENA_MERGES_COMMAND = "`isaac bundle list <bundle_dir> athena-merges`"


def unmatched_merges_line(items: Sequence[Mapping], *, reference_channels: int = 0) -> str:
    """r6 G1: ONE summary line for the scientist's merges that match no record group by name (athena.unmatched_merges):
    how many, the near-name hints (never matched), and how the scientist ties one. r7 K1: the merges with no near name
    are named too (label, project, the groups beside it), and the line says which command lists them all. r7 K3: the
    reference channels (``reference_channels``) are counted, never listed."""
    groups_read = sum(len(i["in"]) for i in items)
    hinted = [i for i in items if i.get("candidates")]
    refs = (f" {reference_channels}{' more' if items else ''} Athena group(s) that match no group are reference "
            "channels (Athena's \"Ref <name>\": the reference read beside a sample), not sample merges, so they are "
            "not listed or hinted." if reference_channels else "")
    if not items:
        return "Athena:" + refs
    line = (f"Athena: {len(items)} of the scientist's merges ({groups_read} Athena groups) match no record group by "
            "name, so ISAAC did not use them. A merge exists but was not matched.")
    if hinted:
        shown = "; ".join(
            f"'{i['athena_label']}' ({_merge_where(i)}) is near "
            + " or ".join(f"{c['group_id']} ({c['group_name']})" for c in i["candidates"])
            for i in hinted[:_UNMATCHED_SAID])
        line += (f" {len(hinted)} have a near name, a hint only, never matched: {shown}"
                 + (" …" if len(hinted) > _UNMATCHED_SAID else "") + ".")
    bare = [i for i in items if not i.get("candidates")]
    if bare:
        shown = "; ".join(f"'{i['athena_label']}' ({_merge_where(i)}, {_beside(i)})" for i in bare[:_UNMATCHED_SAID])
        line += (f" {len(bare)} have no near name: {shown}" + (" …" if len(bare) > _UNMATCHED_SAID else "") + ".")
    return (line + refs + f" Ask the scientist which group each is for, if any. To use one, name it in a params "
            f"file's {P.ATHENA_MATCH_SECTION} ({{\"<group id>\": [{{\"project\": \"<project file>\", \"athena_group\": "
            "\"<Athena label>\"}]}) and run `isaac process --params-file <file>`. If it is no group's, name it in "
            f"{P.ATHENA_IGNORE_SECTION} ([{{\"project\": …, \"athena_group\": …}}]) and it is no longer listed. "
            f"{ATHENA_MERGES_COMMAND} lists every one.")


def athena_ignore_line(rows: Sequence[Mapping]) -> str | None:
    """r7 K5: ONE line for the params file's ``athena_ignore``: the merges set aside (no longer listed), and each item
    that set nothing aside, in its own words. ``None`` when the params file has none."""
    if not rows:
        return None
    done = [r for r in rows if r.get("status") == "ignored"]
    parts = []
    if done:
        named = ", ".join(f"'{r['label']}' ({PurePosixPath(str(r['prj_relative_path'])).name})" for r in done[:_UNMATCHED_SAID])
        parts.append(f"Athena: {len(done)} merge(s) the scientist set aside as no group's (params "
                     f"{P.ATHENA_IGNORE_SECTION}) are no longer listed: {named}" + (" …" if len(done) > _UNMATCHED_SAID else "")
                     + ". Nothing was matched and no result changed. Pass the same params file to keep them set aside.")
    parts += [r["statement"] for r in rows if r.get("status") != "ignored"]
    return " ".join(parts)


def several_groups_line(notes: Sequence[Mapping], groups: Sequence[Mapping], bundle: Mapping | None = None) -> str | None:
    """r7 K6: ONE line for the scientist's Athena groups whose name matches SEVERAL record groups
    (``athena_group_matches_several_record_groups``), so ISAAC used none: each label (its projects) and the groups. When
    the groups are live, it is a hint that they may be one sample in several runs: the scientist decides; ISAAC never
    merges them. The proposed merge candidate between them is named when there is one. ``None`` when none."""
    status = {g["group_id"]: g.get("status") for g in groups}
    by_label: dict[tuple, dict] = {}
    for n in notes:
        if n.get("code") != "athena_group_matches_several_record_groups":
            continue
        gids = tuple(sorted(n.get("group_ids") or ()))
        item = by_label.setdefault((str(n.get("athena_label")), gids), {"projects": []})
        name = PurePosixPath(str(n.get("prj_relative_path"))).name
        if name not in item["projects"]:
            item["projects"].append(name)
    if not by_label:
        return None
    mcs = [m for m in (bundle or {}).get("merge_candidates") or () if isinstance(m, Mapping) and m.get("status") == "proposed"]
    shown = []
    for (label, gids), item in list(by_label.items())[:_UNMATCHED_SAID]:
        live = [g for g in gids if status.get(g) in B.LIVE_GROUP_STATUSES]
        said = f"'{label}' ({', '.join(item['projects'][:3])}) matches {', '.join(gids)}"
        if len(live) > 1:
            mc = next((m.get("merge_candidate_id") for m in mcs if set(live) <= set(m.get("group_ids") or ())), None)
            said += (f": they may be one sample in several runs (a hint only; ISAAC never merges groups"
                     + (f"; merge candidate {mc} proposes it" if mc else "") + ")")
        shown.append(said)
    return (f"Athena: {len(by_label)} of the scientist's Athena group(s) match several record groups by name, so ISAAC "
            "used none of them: " + "; ".join(shown) + (" …" if len(by_label) > _UNMATCHED_SAID else "")
            + ". Ask the scientist whether the groups are one sample. Only on their yes, merge them (`isaac bundle "
            "decide <bundle_dir> --target <group id> --decision merge --merge-with <other group id> --by \"<your "
            f"name>\"`); if not, tie the Athena group to its group in a params file's {P.ATHENA_MATCH_SECTION}.")


def say_unmatched_merges(results: Sequence[dict], items: Sequence[Mapping], *, settled: Iterable[str] = (),
                         stored: Sequence[Mapping] = ()) -> list[dict]:
    """r6 G1: on each result of a group a merge's near-name hint names (athena.unmatched_merges), the sentence "a merge
    exists but was not matched" with the hint and the tie snippet, the review flag :data:`UNMATCHED_MERGE_KEY` and, on
    ISAAC's own result, a question (:data:`UNMATCHED_MERGE_QUESTION`). Nothing is matched. Returns the notes for the
    STORED results ``isaac process`` keeps (apply_kept_result_notes): after the run id, so no id moves.

    Review M1: a group in ``settled`` (its merge is tied now, or was tied in its decided result) is not hinted or asked
    again. Review LOW 3: a ``stored`` result that carries the sentence while its group is no longer hinted (its merge
    tied, or the scientist said no) gets a note taking the flag and the sentence off."""
    settled = set(settled)
    by_group: dict[str, list[tuple[Mapping, Mapping]]] = {}
    for item in items:
        for c in item.get("candidates") or ():
            if c["group_id"] not in settled:
                by_group.setdefault(c["group_id"], []).append((item, c))
    notes: list[dict] = [{"result_id": B.processing_id(r), "remove_review_flags": [UNMATCHED_MERGE_KEY],
                          "remove_statements": [UNMATCHED_MERGE_KEY]}
                         for r in stored or () if isinstance(r, Mapping) and r.get("group_id") not in by_group
                         and UNMATCHED_MERGE_KEY in (r.get("review_flags") or ())]
    for r in results:
        hints = by_group.get(r.get("group_id"))
        if not hints:
            continue
        parts = []
        for item, c in hints:
            parts.append(f"A merge exists but was not matched: the scientist's Athena merge '{item['athena_label']}' "
                         f"({_merge_where(item)}) matches no group by name. Its name is near this group's ({_why_near(c)}), "
                         "a hint only. ISAAC did not use it. If it is this group's merge, name it in a params file "
                         f"and process again: {_tie_snippet(r['group_id'], item)}.")
        said = " ".join(parts)
        r.setdefault("qc", {}).setdefault("statements", {})[UNMATCHED_MERGE_KEY] = said
        if UNMATCHED_MERGE_KEY not in (r.get("review_flags") or ()):
            r.setdefault("review_flags", []).append(UNMATCHED_MERGE_KEY)
        if r.get("source") == "isaac_protocol":
            labels = ", ".join(f"'{item['athena_label']}'" for item, _ in hints)
            r["questions"] = [*(r.get("questions") or ()), {
                "code": UNMATCHED_MERGE_QUESTION,
                "text": (f"Is the scientist's Athena merge {labels} this group's merge? Its name matches no group, so "
                         "ISAAC did not use it. If yes, name it in a params file's athena_match and process again; it "
                         "is then compared and listed for approval. If no, nothing changes."),
                "athena_merges": [{"athena_label": item["athena_label"], "in": list(item["in"])} for item, _ in hints]}]
        notes.append({"result_id": r["result_id"], "add_review_flags": [UNMATCHED_MERGE_KEY],
                      "statements": {UNMATCHED_MERGE_KEY: said}})
    return notes


_RENORM_IDS_SAID = 20


def renormalisation_line(results: Sequence[Mapping]) -> str | None:
    """r6 G4: ONE summary line for every Athena result whose curve differs from larch's reading of its project
    (``renormalised_from_project``): how many, and which are material (more than :data:`athena.ATHENA_RENORM_MATERIAL`
    of the step at the post-edge; named by result id, a few at most). Nothing is flagged on the results. ``None``
    when none."""
    rows = [r for r in results if r.get("source") == "scientist_athena" and r.get(A.RENORMALISED_KEY)]
    if not rows:
        return None
    big = [B.processing_id(r) for r in rows if A.renorm_material(r[A.RENORMALISED_KEY])]
    material = len(big)
    named = (": " + ", ".join(big[:_RENORM_IDS_SAID]) + (f" and {len(big) - _RENORM_IDS_SAID} more" if len(big) > _RENORM_IDS_SAID else "")
             if big else "")
    n = len([r for r in results if r.get("source") == "scientist_athena"])
    return (f"Athena: for {len(rows)} of the {n} Athena results, larch's own reading of the project gives another "
            "curve than Athena shows. ISAAC used the curve Athena shows (the project's stored values where they still "
            "fit the data, else Athena's own re-fit), so each is the scientist's curve. That is larch's reproduction, "
            f"not the scientist's processing. {material} of them differ by more than {A.ATHENA_RENORM_MATERIAL:g} of the "
            f"edge step over the post-edge range{named}. Each result records it ({A.RENORMALISED_KEY}); it is said here once, "
            "not flagged on each result.")


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
