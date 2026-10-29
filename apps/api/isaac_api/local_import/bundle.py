"""ISAAC Local Import Bundle v1 — builder, loader, validator, value states.

The contract is ``bundle-v1.schema.json`` (beside this file) plus the checks here
that JSON Schema cannot express: total size, per-string length, referential
integrity, and — the one that matters most — that every value's state is the one
:func:`derive_value_state` computes from parser output plus recorded decisions.
Human-readable contract: ``docs/local-import-bundle-contract.md``.

FOUR AUTHORITIES, KEPT APART (see :data:`AUTHORITIES`): what a source says; what
extraction or interpretation made of it; what a scientist confirmed; and what the
deterministic schema validators decide. A bundle carries the first three and is
judged by none of the official validators — it is not a record.

THE STATE RULE, IN ONE SENTENCE: parser output can produce only
:data:`PARSER_STATES`; an AI interpretation can lift a value to ``needs_review`` and
never higher; only a ``scientist_decisions`` entry produces ``scientist_confirmed``
or ``rejected``. The validator recomputes this for every value and refuses a bundle
whose stored state disagrees, so a hand-edited ``"value_state":
"scientist_confirmed"`` is a schema-valid but contract-INVALID bundle.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

FORMAT_ID = "isaac.local-import-bundle"
#: 1.2.0 (additive): ``processed_outputs[]`` — the scientists' own Athena/Demeter outputs,
#: kept OUT of ``runs[]`` (see :func:`_processing_origin`).
#: 1.3.0 (additive): ``ai_interpretation.field_path`` / ``.run_ids`` (absorber readings on
#: record groups), the ``eligibility_rederived`` log, and a larger writable set
#: (:data:`WRITABLE_ADDED_IN`), so eligibility stored by an older build can be STALE.
#: 1.4.0 (additive): the ``set_clock_time_zone`` experiment decision (a 1.3.0 validator would
#: refuse a bundle that uses it), the ``confirm_clock_time_zone`` question kind, the optional
#: ``candidates[].local_clock`` block and ``scientist_decisions[].clock_zone_binding``, and the
#: import rule :data:`XDC_START_RULE_ID`. Nothing becomes newly writable
#: (``timestamps.acquired_start_utc`` already was), so :data:`WRITABLE_ADDED_IN` is unchanged.
FORMAT_VERSION = "1.4.0"
#: Paths this build can write that the build of an older format version could not. A value at
#: one of them whose stored eligibility differs from this build's is STALE, not tampered.
WRITABLE_ADDED_IN: Mapping[str, frozenset] = {
    "1.3.0": frozenset({"context.electrochemistry.potential_setpoint_V"}),
}
#: Import-time rules a format version added: ``version -> ((run source_type, rule id), ...)``. A
#: bundle an older build imported has none of that rule's candidates on such runs, and nothing but
#: a re-import adds them; the first save by this build says so in its ``format_upgrades`` entry.
IMPORT_RULES_ADDED_IN: Mapping[str, tuple] = {
    "1.4.0": (("generic:ssrl_xdc_v1", "ssrl_xdc_scan_start_v1"),),
}
_VERSION_ORDER = ("1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0")
#: A field composed into a draft only beside another of the SAME run (interim decision for the
#: set-point, pending domain-owner review; ``records.compose_group`` applies it).
COMPOSES_ONLY_WITH: Mapping[str, str] = {
    "context.electrochemistry.potential_setpoint_V": "context.electrochemistry.potential_scale",
}
SCHEMA_FILE = Path(__file__).with_name("bundle-v1.schema.json")
BUNDLE_FILE = "bundle.json"

OFFICIAL_RECORD_NOTICE = (
    "This is an ISAAC Local Import Bundle, NOT an official ISAAC record and not a "
    "validated one. It holds what the deterministic readers extracted from your files "
    "and the evidence for each value. Nothing in it has been confirmed by a scientist "
    "unless a scientist_decisions entry says so, and nothing in it has been checked "
    "against the official ISAAC schema. An official record is produced only by "
    "`isaac export` from a reviewed draft."
)

# --- bounds ------------------------------------------------------------------
#
# Generous but finite. Each is tied to a ceiling the engine already enforces, so a
# bundle built from any reading the engine accepts fits, and a bundle that does not
# fit was produced (or edited) by something else.

#: One run per acquisition at most, and the walk inventories at most
#: ``ArchiveLimits.max_entries`` (5,000) entries — 4x the measured 1,192-file corpus.
MAX_RUNS = 5_000
#: The engine's own ``historical_import.MAX_CANDIDATES_PER_SESSION`` (4,000); the
#: measured real corpus produces ~1,000. A truncated engine reading says so in
#: ``bounds.candidates_truncated_by_engine``.
MAX_CANDIDATES = 4_000
#: Witnesses kept per value. The engine keeps a window of 5 supporting statements
#: (``MAX_STATEMENTS_PER_CANDIDATE``) plus every disagreement reading; 256 clears the
#: largest disagreement measured on the fixtures by two orders of magnitude, and a
#: window past it sets ``evidence_truncated`` with ``evidence_total`` — never silent.
MAX_EVIDENCE_PER_CANDIDATE = 256
#: Longest string kept verbatim. The engine's longest stored prose is the readings
#: note (``READINGS_NOTE_MAX_CHARS`` = 12,000); a longer string (a pathological
#: one-line note) is clamped with a visible marker and counted in
#: ``bounds.strings_truncated``.
MAX_STRING_CHARS = 20_000
#: bundle.json ceiling. The 9-run fixture is ~1 MB; the real 1,192-file corpus is
#: estimated at well under 16 MB. 64 MiB is a laptop-safe JSON load.
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
#: Distinct literal values listed on a candidate; past it ``observed_literals_truncated``.
MAX_OBSERVED_LITERALS = 8
#: Generic-reader statements kept per run (as source-recorded extended context); the
#: rest are counted in ``runs[].reader.statements_total``, never dropped silently.
MAX_GENERIC_STATEMENTS_PER_RUN = 200

_TRUNCATION_MARKER = " …[truncated by bundle bounds: {n} characters in the original]"

# --- processed outputs (1.2.0) ---------------------------------------------------
#
# A PROCESSED OUTPUT IS A REFERENCE RESULT, NEVER AN ACQUISITION. The XDI reader reads the
# scientists' own Athena/Demeter outputs (``.nor``, ``.xmu``, ``.peak`` ...). Each one is
# the scientist's processing of scans that are already in the bundle as runs, so making it
# a run as well made the grouping step propose record groups (future ISAAC records) out of
# processed files, double-counting measurements. They are kept in ``processed_outputs[]``
# instead: evidence, and the thing ISAAC's own processing is checked against.
#
# THE RULE (``isaac.processed_output.origin.v0``, :func:`classify_processing_origin`) is the
# file's OWN statement, not its extension and not the format. Line 1 decides: an exact
# application token in :data:`PROCESSING_APPLICATIONS` makes it a processed output; only
# OTHER applications named keeps it a run whatever its fields say (a disagreement is
# recorded); no application named falls back to a non-empty ``Demeter.output_filetype`` or
# ``Athena.*`` fields. XDI is also a raw-data format at some beamlines.

PROCESSED_OUTPUT_KIND = "processed_output_of_the_scientist"
PROCESSED_ORIGIN_RULE_ID = "isaac.processed_output.origin.v0"
#: Casefolded application names, as written on an XDI file's first line. Measured on the
#: real corpus (28 Oct 2026): every XDI file names one of these two.
PROCESSING_APPLICATIONS = frozenset({"athena", "demeter"})
#: Header statements of a processed output recorded as what the file states about itself.
_PROCESSED_STATED_KEYS = {
    "Element.symbol": "element_symbol",
    "Element.edge": "element_edge",
    "Demeter.output_filetype": "demeter_output_filetype",
}

# THE LINK RULE (``isaac.processed_output.link_by_run_stem.v0``, :func:`propose_processed_links`)
# — PROPOSES, never merges. A processed output's name stem (its file name minus the processed
# extension, as the reader groups it) against run ``stem``s, case-sensitively, nothing else
# normalised:
#   1. ``exact``                 — a run has exactly this name (ANY such run, even zero-scan,
#      also blocks rule 2); only a run candidate with at least one scan is linked;
#   2. ``scan_selection_suffix`` — stem == run stem + "_" + N or N-M, and every number is a
#      scan the run HAS (its stated scan indices, else 1..scan_count). Another number may be
#      another sample or condition, so it links nothing.
# Exactly ONE fitting run -> one proposed link (its record group derived from live
# ``record_groups[]`` membership). Several -> no link, noted as ambiguous. None -> unlinked,
# the honest outcome when the scientist renamed the file. The validator re-runs it.
LINK_RULE_ID = "isaac.processed_output.link_by_run_stem.v0"
_SCAN_SELECTION_SUFFIX = re.compile(r"^(?P<base>.+)_(?P<sel>\d+(?:-\d+)?)$")

# --- value states --------------------------------------------------------------

STATE_SOURCE_RECORDED = "source_recorded"
STATE_CANDIDATE_EXTRACTED = "candidate_extracted"
STATE_NEEDS_REVIEW = "needs_review"
STATE_CONFLICTING = "conflicting"
STATE_SCIENTIST_CONFIRMED = "scientist_confirmed"
STATE_REJECTED = "rejected"
STATE_UNMAPPED = "unmapped"
STATE_MISSING = "missing"

VALUE_STATES = frozenset(
    {
        STATE_SOURCE_RECORDED,
        STATE_CANDIDATE_EXTRACTED,
        STATE_NEEDS_REVIEW,
        STATE_CONFLICTING,
        STATE_SCIENTIST_CONFIRMED,
        STATE_REJECTED,
        STATE_UNMAPPED,
        STATE_MISSING,
    }
)
#: What parser output ALONE can yield for a value. ``scientist_confirmed`` and
#: ``rejected`` are absent by construction.
PARSER_STATES = frozenset(
    {
        STATE_CANDIDATE_EXTRACTED,
        STATE_NEEDS_REVIEW,
        STATE_CONFLICTING,
        STATE_UNMAPPED,
        STATE_MISSING,
    }
)
#: The states an AI interpretation may lift to ``needs_review``. A conflict is NOT
#: in it: an interpretation cannot settle a disagreement between sources, so it stays
#: ``conflicting`` until a scientist chooses.
_AI_LIFTABLE = frozenset({STATE_MISSING, STATE_UNMAPPED, STATE_CANDIDATE_EXTRACTED})

#: ``SemanticCandidate.review_status`` -> the bundle's extracted state. THE ONE
#: MAPPING from the existing contract; see the contract doc's table.
REVIEW_STATUS_TO_STATE: Mapping[str, str] = {
    "sources_conflict": STATE_CONFLICTING,
    "unmapped": STATE_UNMAPPED,
    "ready": STATE_CANDIDATE_EXTRACTED,
    "needs_review": STATE_NEEDS_REVIEW,
    # A disagreement a STORED rule resolved is not a scientist's confirmation in this
    # bundle: it is shown as extracted (when it carries a sendable value) or held for
    # review. See `_extracted_state_of`.
    "resolved": STATE_NEEDS_REVIEW,
}

AUTHORITIES: Mapping[str, str] = {
    "source_evidence": (
        "What a file literally says, at a locator: sources[], every evidence[] entry's "
        "literal_value, extended_context[], data_quality_notes[], contributors[]. "
        "Never rewritten; normalisation is recorded beside the literal, not over it."
    ),
    "extraction_interpretation": (
        "What the deterministic readers, stored rules and (later) AI interpretations "
        "made of the evidence: candidates[] values, conflicts[] recommendations, "
        "ai_interpretations[]. Suggestions only; an AI interpretation can raise a value "
        "to needs_review and never higher."
    ),
    "scientist_confirmation": (
        "scientist_decisions[] only. The sole source of scientist_confirmed and "
        "rejected. Recorded by the local user; this build cannot verify identity, and "
        "decided_by.basis says so."
    ),
    "deterministic_schema_validation": (
        "The official ISAAC schema and validators (`isaac validate --official`, "
        "`isaac export`). They judge official RECORDS, not this bundle; "
        "validation.official_record_validation is therefore not_applicable here. This "
        "bundle is checked only against its own bundle-v1 contract."
    ),
}


# --- small helpers ---------------------------------------------------------------


@lru_cache(maxsize=1)
def bundle_schema() -> dict:
    """The bundle-v1 JSON Schema, parsed."""
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def _safe_relative(path: object) -> str | None:
    """``path`` if it is a relative path with no ``..`` segment, else ``None``."""
    if not isinstance(path, str) or not path:
        return None
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path):
        return None
    if ".." in PurePosixPath(path.replace("\\", "/")).parts:
        return None
    return path


def _rule_id(rule_text: object) -> str | None:
    """``bl15.spec.epoch_to_utc_iso.v1`` out of ``"bl15.spec.epoch_to_utc_iso.v1: ..."``."""
    if not isinstance(rule_text, str) or not rule_text.strip():
        return None
    head = rule_text.split(":", 1)[0].strip()
    return head if re.fullmatch(r"[A-Za-z0-9_.\-]+", head) else None


def _reader_version(reader_id: str) -> str | None:
    match = re.search(r"_v(\d+)$", reader_id)
    return match.group(1) if match else None


_XDI_LINE1 = re.compile(r"^#[ \t]+XDI/\d+\.\d+(?:[ \t]+(?P<apps>\S.*?))?[ \t]*$")


def xdi_line1_applications(literal: object) -> list[tuple[str, str | None]]:
    """``[(name, version)]`` for each whitespace-separated ``Name/version`` token an XDI
    first line lists after ``XDI/x.y`` (XDI lets several applications sign a file)."""
    m = _XDI_LINE1.match(literal.strip()) if isinstance(literal, str) else None
    if not m or not m.group("apps"):
        return []
    out = []
    for tok in m.group("apps").split():
        name, _, version = tok.partition("/")
        if name:
            out.append((name, version or None))
    return out


def classify_processing_origin(
    applications: Sequence[tuple[str, str | None]], *, demeter_output_filetype: object, has_athena_fields: bool
) -> tuple[dict | None, dict | None]:
    """``(origin, disagreement)`` by ``isaac.processed_output.origin.v0`` — the ONE rule, used
    for a fresh import and for recognising a pre-1.2.0 bundle that still holds them as runs.

    * line 1 names, as an exact token (case ignored), an application in
      :data:`PROCESSING_APPLICATIONS` -> processed output (basis ``line_1``);
    * line 1 names only OTHER applications -> NOT a processed output, whatever the fields
      say; if ``Demeter.output_filetype`` / ``Athena.*`` fields are present the file
      disagrees with itself, and the disagreement is returned to be recorded, not resolved;
    * line 1 names nothing -> processed output only when it carries a non-empty
      ``Demeter.output_filetype`` or ``Athena.*`` fields (basis ``fields``).
    """
    filetype = demeter_output_filetype.strip() if isinstance(demeter_output_filetype, str) else ""
    named = [(n, v) for n, v in applications if n.casefold() in PROCESSING_APPLICATIONS]
    foreign = [n for n, _ in applications if n.casefold() not in PROCESSING_APPLICATIONS]
    if named:
        basis = "line_1"
    elif foreign:
        if filetype or has_athena_fields:
            return None, {
                "kind": "processing_statement_disagrees",
                "locator": "line:1",
                "detail": (
                    f"line 1 names {', '.join(foreign)}, not Athena or Demeter, but the header also "
                    "carries " + " and ".join(x for x, on in (("Demeter.output_filetype", bool(filetype)), ("Athena.* fields", has_athena_fields)) if on)
                    + "; kept as an acquisition, nothing decided"
                ),
                "severity": "note",
            }
        return None, None
    elif filetype or has_athena_fields:
        basis = "fields"
    else:
        return None, None
    return {
        "rule_id": PROCESSED_ORIGIN_RULE_ID,
        "basis": basis,
        "processed_by": named[0][0] if named else None,
        "application_version": named[0][1] if named else None,
        "line_1_applications": [f"{n}/{v}" if v else n for n, v in applications][:10],
        "names_a_processing_application": bool(named),
        "has_demeter_output_filetype": bool(filetype),
        "has_athena_fields": bool(has_athena_fields),
    }, None


def _processing_origin(scan: Mapping, line1: object) -> tuple[dict | None, dict | None]:
    """:func:`classify_processing_origin` for one file the XDI reader read (``line1`` is its
    literal first line)."""
    hints = scan.get("role_hints") if isinstance(scan.get("role_hints"), Mapping) else {}
    return classify_processing_origin(
        xdi_line1_applications(line1),
        demeter_output_filetype=hints.get("demeter_output_filetype"),
        has_athena_fields=bool(hints.get("has_athena_fields")),
    )


def legacy_processed_runs(bundle: Mapping) -> list[str]:
    """Run ids of a PRE-1.2.0 bundle (no ``processed_outputs`` section) that are XDI files
    whose own header, by :func:`classify_processing_origin`, makes them the scientists'
    processed outputs — read back from the run's recorded statements. Empty for 1.2.0+."""
    if "processed_outputs" in bundle:
        return []
    xdi_runs = {r["run_id"] for r in bundle.get("runs") or () if r.get("source_type") == "generic:xdi_v1"}
    if not xdi_runs:
        return []
    per_file: dict[tuple[str, Any], dict] = {}
    for e in bundle.get("extended_context") or ():
        if e.get("run_id") not in xdi_runs:
            continue
        f = per_file.setdefault((e["run_id"], e.get("relative_path")), {"line1": None, "filetype": None, "athena": False})
        concept = str(e.get("concept") or "")
        if concept == "xdi_version":
            f["line1"] = e.get("raw_literal")
        elif concept == "Demeter.output_filetype":
            f["filetype"] = e.get("raw_literal")
        elif concept.startswith("Athena."):
            f["athena"] = True
    hits = []
    for (run_id, _), f in per_file.items():
        origin, _ = classify_processing_origin(
            xdi_line1_applications(f["line1"]), demeter_output_filetype=f["filetype"], has_athena_fields=f["athena"]
        )
        if origin and run_id not in hits:
            hits.append(run_id)
    return hits


def legacy_refusal(bundle: Mapping) -> str | None:
    """Why grouping or composing records must refuse this bundle, or ``None``."""
    hits = legacy_processed_runs(bundle)
    if not hits:
        return None
    return (
        f"This bundle (format {bundle.get('format_version')}) holds {len(hits)} of the scientists' own "
        "processed outputs (Athena/Demeter XDI) as runs, so grouping would make record groups of "
        "processed files. Re-import the folder with this build (`isaac import <folder> --out <new dir>`) "
        "to separate the scientists' processed outputs; nothing was written."
    )


def _scan_numbers(run: Mapping) -> tuple[set[int], str]:
    """The scan numbers a run HAS: its scans' own ``scan_index`` values when any is stated,
    else ``1..scan_count`` (basis named, so a reader sees which)."""
    stated = {s["scan_index"] for s in run.get("scans") or () if isinstance(s.get("scan_index"), int) and not isinstance(s.get("scan_index"), bool)}
    if stated:
        return stated, "scan_indices"
    return set(range(1, int(run.get("scan_count") or 0) + 1)), "scan_count"


def _selection_numbers(sel: str) -> set[int] | None:
    """``"7"`` -> {7}; ``"1-5"`` -> {1..5}; a reversed or oversized range -> ``None``."""
    a, _, b = sel.partition("-")
    lo, hi = int(a), int(b) if b else int(a)
    if hi < lo or hi - lo > 10_000:
        return None
    return set(range(lo, hi + 1))


def propose_processed_links(processed_outputs: Sequence[dict], runs: Sequence[Mapping]) -> None:
    """Fill each processed output's ``proposed_links`` / ``link_note`` in place by
    :data:`LINK_RULE_ID`. Deterministic; proposes only; never touches a run or a group.
    The validator re-runs this over the stored runs and refuses a bundle that disagrees."""
    named: dict[str, list[Mapping]] = {}
    for r in runs:
        if isinstance(r.get("stem"), str):
            named.setdefault(r["stem"], []).append(r)

    def with_scans(rs):
        return [r for r in rs if r.get("run_candidate") and int(r.get("scan_count") or 0) > 0]

    for po in processed_outputs:
        stem = po["label"]
        po["proposed_links"] = []
        po["link_note"] = None
        match, suffix, basis, hits = None, None, None, []
        if stem in named:
            # ANY run carrying this exact name (zero-scan included) blocks the suffix rule
            match, hits = "exact", with_scans(named[stem])
            if not hits:
                po["link_note"] = {
                    "code": "exact_name_run_has_no_scans",
                    "match": "exact",
                    "run_keys": sorted(r["run_key"] for r in named[stem])[:20],
                    "detail": "A run has exactly this name but no scan, so nothing is linked.",
                }
                continue
        else:
            m = _SCAN_SELECTION_SUFFIX.match(stem)
            base_runs = with_scans(named.get(m.group("base"), [])) if m else []
            wanted = _selection_numbers(m.group("sel")) if m else None
            if base_runs and wanted:
                fitting = []
                for r in base_runs:
                    have, why = _scan_numbers(r)
                    if wanted <= have:
                        fitting.append((r, why))
                if fitting:
                    match, suffix, hits = "scan_selection_suffix", m.group("sel"), [r for r, _ in fitting]
                    basis = fitting[0][1] if len(fitting) == 1 else None
        if len(hits) == 1:
            run = hits[0]
            po["proposed_links"].append(
                {
                    "rule_id": LINK_RULE_ID,
                    "status": "proposed",
                    "match": match,
                    "scan_selection_literal": suffix,
                    "scan_selection_basis": basis,
                    # stated, never hidden: a run that states no scan index is taken to
                    # number its scans 1..scan_count
                    "assumption": (
                        f"the run states no scan index; its {int(run.get('scan_count') or 0)} scans are taken to be numbered 1..{int(run.get('scan_count') or 0)}"
                        if basis == "scan_count" else None
                    ),
                    "run_id": run["run_id"],
                    "run_key": run["run_key"],
                    "run_stem": run["stem"],
                    "group_id": None,  # derived from record_groups[] by apply_derivations
                }
            )
        elif len(hits) > 1:
            po["link_note"] = {
                "code": "ambiguous",
                "match": match,
                "run_keys": sorted(r["run_key"] for r in hits)[:20],
                "detail": f"{len(hits)} runs fit the name this output points to; none is chosen.",
            }
        else:
            po["link_note"] = {
                "code": "no_run_named_like_it",
                "match": None,
                "run_keys": [],
                "detail": (
                    "No run's name equals this output's name, or equals it minus a trailing "
                    "scan selection whose every number is a scan that run has; it stays unlinked."
                ),
            }


def processed_output_counts(processed_outputs: Sequence[Mapping]) -> dict[str, int]:
    """The ``counts`` keys for ``processed_outputs[]`` (present only when the section is)."""
    return {
        "processed_outputs": len(processed_outputs),
        "processed_output_files": sum(len(p.get("files") or ()) for p in processed_outputs),
        "processed_outputs_linked": sum(1 for p in processed_outputs if p.get("proposed_links")),
        "processed_outputs_unlinked": sum(1 for p in processed_outputs if not p.get("proposed_links")),
    }


#: Record-group statuses that hold their runs: a run belongs to at most ONE such group.
#: ``merged`` is NOT one (review R-1): nothing applies a decision's ``merge_with`` and only a
#: confirmed group becomes a record, so a merged group is history, like rejected and split.
LIVE_GROUP_STATUSES = frozenset({"proposed", "scientist_confirmed"})
#: Statuses that BIND a scientist's choice: their runs are never re-proposed.
BINDING_GROUP_STATUSES = frozenset({"scientist_confirmed"})
#: Decided statuses kept as the record of that decision; they do not hold their runs.
HISTORY_GROUP_STATUSES = frozenset({"rejected", "split", "merged"})


def _derive_processed_links(bundle: Mapping) -> None:
    """A proposed link's ``group_id`` is DERIVED: the live record group (status in
    :data:`LIVE_GROUP_STATUSES`) whose ``member_run_keys`` holds the linked run, else
    ``None``. A rejected or split group is history and is never named."""
    pos = bundle.get("processed_outputs")
    if not pos:
        return
    group_of: dict[str, str] = {}
    for g in bundle.get("record_groups") or ():
        if g.get("status") in LIVE_GROUP_STATUSES:
            for key in g.get("member_run_keys") or ():
                group_of.setdefault(key, g["group_id"])
    for po in pos:
        for link in po.get("proposed_links") or ():
            link["group_id"] = group_of.get(link["run_key"])


def _derive_merge_candidate_ids(bundle: Mapping) -> None:
    """A record group's ``merge_candidate_ids`` is a DERIVED pointer (review N-1): the stored
    merge candidates naming that group, in their order. Not part of any decision."""
    if not bundle.get("record_groups"):
        return
    of: dict[str, list[str]] = {}
    for mc in bundle.get("merge_candidates") or ():
        for gid in mc.get("group_ids") or ():
            of.setdefault(gid, []).append(mc.get("merge_candidate_id"))
    for g in bundle["record_groups"]:
        if "merge_candidate_ids" in g or g["group_id"] in of:
            g["merge_candidate_ids"] = of.get(g["group_id"], [])


def _clamp_strings(obj: Any, counter: list[int]) -> Any:
    """Every string longer than :data:`MAX_STRING_CHARS`, clamped VISIBLY and counted."""
    if isinstance(obj, str):
        if len(obj) <= MAX_STRING_CHARS:
            return obj
        counter[0] += 1
        marker = _TRUNCATION_MARKER.format(n=len(obj))
        return obj[: MAX_STRING_CHARS - len(marker)] + marker
    if isinstance(obj, list):
        return [_clamp_strings(v, counter) for v in obj]
    if isinstance(obj, dict):
        return {k: _clamp_strings(v, counter) for k, v in obj.items()}
    return obj


def _iter_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_strings(v)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_strings(v)


def encode(bundle: Mapping) -> bytes:
    """The exact bytes ``bundle.json`` holds."""
    return (json.dumps(bundle, indent=1, ensure_ascii=False, sort_keys=False) + "\n").encode(
        "utf-8"
    )


# --- the state machine -----------------------------------------------------------


#: Decisions that CONFIRM a value (value targets: candidate, missing value, conflict).
CONFIRMING_DECISIONS = frozenset({"confirm", "correct", "choose_reading", "provide_value", "approve"})
#: Decisions that settle nothing: the target keeps the state its evidence supports.
NEUTRAL_DECISIONS = frozenset({"defer"})
#: Which decisions each target kind accepts. ``isaac bundle decide`` refuses the rest.
DECISIONS_BY_KIND: Mapping[str, frozenset[str]] = {
    "candidate": frozenset({"confirm", "correct", "reject", "defer"}),
    "missing_value": frozenset({"confirm", "correct", "reject", "defer"}),
    "conflict": frozenset({"confirm", "correct", "reject", "defer"}),
    "record_group": frozenset({"confirm", "split", "merge", "reject", "defer", "approve_calibration", "set_absorber"}),
    "processing_result": frozenset({"approve", "reject", "needs_changes", "defer"}),
    "experiment": frozenset({"set_counter_positions", "set_clock_time_zone"}),
}
#: Record-group status from its decision (``None`` = no decision, or ``defer``).
GROUP_STATUS_BY_DECISION: Mapping[str | None, str] = {
    None: "proposed",
    "confirm": "scientist_confirmed",
    "split": "split",
    "merge": "merged",
    "reject": "rejected",
}
#: The record-group decisions that set its status.
GROUP_STATUS_DECISIONS = frozenset({"confirm", "split", "merge", "reject", "defer"})
#: What a processing result may say about itself without a scientist's decision.
PROCESSING_UNDECIDED_STATES = frozenset({STATE_CANDIDATE_EXTRACTED, STATE_NEEDS_REVIEW})
#: ``processing_result.applicability.status``: the protocol could not be applied to the group.
#: Such a result is an explicit outcome, NOT a curve: it carries no QC verdict and no output
#: file, and no decision (approve, reject, needs_changes, defer) is accepted on it.
NOT_APPLICABLE = "not_applicable"
#: The group lists no scan: nothing to process.
NA_NO_SCANS = "no_scans"
#: No energy axis or no absorption signal could be formed from the scan's columns.
NA_NO_XAS_CHANNEL = "no_xas_channel"
#: Why a group without an approvable processing result cannot become a record.
NO_PROTOCOL_COVERS = "no ISAAC processing protocol covers this data yet"


def processing_not_applicable(result: Mapping) -> bool:
    """True when the processing protocol could not be applied (``applicability.status``)."""
    return isinstance(result, Mapping) and (result.get("applicability") or {}).get("status") == NOT_APPLICABLE


def processing_blocked_groups(bundle: Mapping) -> dict[str, Mapping]:
    """``{group_id: latest result}`` for groups whose LATEST ``isaac_protocol`` result says
    the protocol does not apply. Latest = last in ``processing_results`` (``isaac process``
    stores the kept, decided results first and the fresh run after them). Older results
    (e.g. a rejected ``fail`` from before this rule) are kept and never deleted, but they do
    not make the group approvable. A group with an APPROVED (non-not-applicable) result is
    never blocked: the record composer uses that approved curve."""
    latest: dict[str, Mapping] = {}
    approved: set = set()
    for r in bundle.get("processing_results") or ():
        if r.get("source") == "isaac_protocol":
            latest[r.get("group_id")] = r
        if r.get("state") == STATE_SCIENTIST_CONFIRMED and not processing_not_applicable(r):
            approved.add(r.get("group_id"))  # an approved curve exists: the record uses it
    return {gid: r for gid, r in latest.items() if processing_not_applicable(r) and gid not in approved}


def processing_id(result: Mapping) -> str:
    """The id a decision names a processing result by: ``result_id`` if LOCAL-P set
    one, else ``<group_id>:<protocol_id>@<protocol_version>``."""
    rid = result.get("result_id")
    if isinstance(rid, str) and rid:
        return rid
    return f"{result.get('group_id')}:{result.get('protocol_id')}@{result.get('protocol_version')}"


def _decisions_by_target(decisions: Sequence[Mapping]) -> dict[tuple[str, str], Mapping]:
    """The LAST decision per target — a later answer supersedes an earlier one. A
    ``defer`` is a decision too: it withdraws an earlier confirmation."""
    out: dict[tuple[str, str], Mapping] = {}
    for d in decisions:
        target = d.get("target") if isinstance(d, Mapping) else None
        if isinstance(target, Mapping):
            out[(str(target.get("kind")), str(target.get("id")))] = d
    return out


def _interpreted_targets(interpretations: Sequence[Mapping]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for i in interpretations:
        target = i.get("target") if isinstance(i, Mapping) else None
        if isinstance(target, Mapping):
            out.add((str(target.get("kind")), str(target.get("id"))))
    return out


def derive_value_state(
    extracted_state: str,
    *,
    decision: Mapping | None,
    interpreted: bool,
) -> str:
    """The state a value is in, from what the parser found plus what was recorded.

    * a scientist decision decides: ``reject`` -> ``rejected``; ``confirm``,
      ``correct``, ``choose_reading``, ``provide_value`` or ``approve`` ->
      ``scientist_confirmed``; ``needs_changes`` -> ``needs_review``; ``defer``
      decides nothing;
    * otherwise an AI interpretation lifts ``missing``/``unmapped``/
      ``candidate_extracted`` to ``needs_review`` — never higher, and never a conflict;
    * otherwise the parser's own state stands.

    ``extracted_state`` outside :data:`PARSER_STATES` is refused: that is how a
    parser-produced ``scientist_confirmed`` is made impossible rather than unlikely.
    """
    if extracted_state not in PARSER_STATES:
        raise ValueError(f"{extracted_state!r} is not a state parser output can produce")
    kind = decision.get("decision") if decision is not None else None
    if kind is not None and kind not in NEUTRAL_DECISIONS:
        if kind == "reject":
            return STATE_REJECTED
        if kind == "needs_changes":
            return STATE_NEEDS_REVIEW
        if kind in CONFIRMING_DECISIONS:
            return STATE_SCIENTIST_CONFIRMED
    if interpreted and extracted_state in _AI_LIFTABLE:
        return STATE_NEEDS_REVIEW
    return extracted_state


def eligibility_for_official_record(
    value_state: str,
    *,
    target_field_path: str | None,
    value: Any,
    writable_paths: frozenset[str],
) -> dict:
    """``{eligible, reason}`` — CONSERVATIVE BY DESIGN.

    Eligible ONLY when a scientist confirmed the value, there is a value, and this
    build has a write route for its target path. Nothing a parser or an AI produced is
    ever eligible on its own: even a ``candidate_extracted`` value the server would let
    a person PROPOSE still needs a person to accept it there (the accept route's
    trusted-actor gate). "Eligible" means "may be carried into a draft for review and
    ``isaac export``" — never "is official".
    """
    if value_state != STATE_SCIENTIST_CONFIRMED:
        return {
            "eligible": False,
            "reason": (
                f"Not confirmed by a scientist (state: {value_state}). Only a "
                "scientist-confirmed value can go toward an official record."
            ),
        }
    if value is None:
        return {"eligible": False, "reason": "Confirmed, but there is no value to carry."}
    if not target_field_path or target_field_path not in writable_paths:
        return {
            "eligible": False,
            "reason": (
                "Confirmed, but this build has no write path for its official field, so "
                "it stays evidence."
            ),
        }
    problem = value_problem(target_field_path, value)
    if problem is not None:
        return {"eligible": False, "reason": f"Confirmed, but the value does not fit the official field: {problem}"}
    return {
        "eligible": True,
        "reason": (
            "Confirmed by a scientist and this build can write its official field. It "
            "still becomes official only through a reviewed draft and `isaac export`."
        ),
    }


@lru_cache(maxsize=1)
def _vendored_schema() -> dict | None:
    from ..schema_locator import resolve_schema_path

    try:
        return json.loads(resolve_schema_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _schema_node(path: str) -> Mapping | None:
    node: Any = _vendored_schema()
    for segment in path.split("."):
        if not isinstance(node, Mapping):
            return None
        if segment.endswith("[]"):
            segment = segment[:-2]
            node = (node.get("properties") or {}).get(segment)
            node = node.get("items") if isinstance(node, Mapping) else None
        else:
            node = (node.get("properties") or {}).get(segment)
    return node if isinstance(node, Mapping) else None


_JSON_TYPES = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
    "null": lambda v: v is None,
}


def value_problem(path: str, value: Any) -> str | None:
    """Why ``value`` cannot stand at ``path`` (review L3), or ``None``.

    The ``*_utc`` rule (a zoned ISO instant — a local time with no zone is refused,
    the engine's own ``is_zoned_utc_value``), then the vendored schema's own ``enum``
    and ``type`` at that path, read at runtime. An open namespace the schema does not
    declare gets no check, and none is invented.
    """
    from .. import historical_import as hist

    if not hist.is_zoned_utc_value(path, value):
        return f"{path} needs a UTC instant with a zone; {value!r} is not one"
    node = _schema_node(path)
    if node is None:
        return None
    enum = node.get("enum")
    if isinstance(enum, list) and value not in enum:
        return f"{value!r} is not one of the schema's allowed values for {path}"
    declared = node.get("type")
    types = declared if isinstance(declared, list) else [declared] if isinstance(declared, str) else []
    if types and not any(_JSON_TYPES.get(t, lambda v: True)(value) for t in types):
        return f"{path} must be {' or '.join(types)}; got {type(value).__name__}"
    return None


def final_value(base_value: Any, decision: Mapping | None, readings: Sequence | None = None) -> Any:
    """The value a target carries once its decision is applied."""
    if decision is None or decision.get("decision") in NEUTRAL_DECISIONS:
        return base_value
    kind = decision.get("decision")
    if kind == "reject":
        return None
    if kind in ("provide_value", "correct"):
        return decision.get("value")
    if kind == "choose_reading":
        idx = decision.get("chosen_reading_index")
        if isinstance(idx, int) and readings and 0 <= idx < len(readings):
            return readings[idx]
        return decision.get("value")
    return decision.get("value") if decision.get("value") is not None else base_value


_final_value = final_value  # LOCAL-1 name, kept


def candidate_decision(bundle: Mapping, candidate: Mapping, decision_of=None) -> Mapping | None:
    """The decision that governs a candidate: the LATER of one naming the candidate and
    one naming its conflict (a person resolving a conflict decides its value)."""
    decisions = list(bundle.get("scientist_decisions") or ())
    if decision_of is None:
        decision_of = _decisions_by_target(decisions)
    own = decision_of.get(("candidate", candidate["candidate_id"]))
    conflict_ids = [c["conflict_id"] for c in bundle["conflicts"] if c.get("candidate_id") == candidate["candidate_id"]]
    via = [decision_of.get(("conflict", cid)) for cid in conflict_ids]
    options = [d for d in [own, *via] if d is not None]
    if not options:
        return None
    return max(options, key=lambda d: decisions.index(d) if d in decisions else -1)


# --- the SSRL XDC scan start time, and the instrument clock's time zone (1.4.0) ---------------
#
# THE RULE (``ssrl_xdc_scan_start_v1``, applied at import by :func:`_xdc_start_candidate`): one
# ``timestamps.acquired_start_utc`` candidate per run the ``ssrl_xdc_v1`` reader found. Each scan's
# line 2 is a LOCAL clock time ("Tue Jul 14 10:23:45 2099") and names no zone; there is no epoch
# line. The run's start is the EARLIEST parsed scan time. A scan whose time did not parse, or whose
# weekday does not fall on its date, is not used (the reader already flagged it).
#
# THE ZONE is a scientist's statement: ``set_clock_time_zone`` on the experiment, the IANA name of
# the time zone the INSTRUMENT CLOCK that wrote the headers was set to. No file states it, and
# nothing here assumes it from where the facility is. Until it is stated the candidate carries no
# value. Once stated, :func:`apply_derivations` converts the local time on every save
# (``local_clock_to_utc_via_confirmed_zone_v1``, zoneinfo, DST-aware); a time the zone makes
# ambiguous (the fall-back hour) or nonexistent (the spring-forward gap) gets NO value.
#
# THE BINDING: ``confirm`` without ``--value`` stores no value, and the composed value is the
# candidate's LIVE value — which a later zone decision changes. So a confirmation records the zone
# and the converted value it was made under (``clock_zone_binding``), and a candidate whose current
# zone or value differs from its binding is NOT eligible until it is confirmed again.

XDC_PROFILE_ID = "ssrl_xdc_v1"
XDC_RUN_SOURCE_TYPE = f"generic:{XDC_PROFILE_ID}"
XDC_START_RULE_ID = "ssrl_xdc_scan_start_v1"
XDC_START_RULE = (
    f"{XDC_START_RULE_ID}: the run's acquisition start is the EARLIEST timestamp written on line 2 of "
    "its SSRL EXAFS Data Collector 4.0 scan files, read as the instrument clock's local time. A scan "
    "whose line-2 time does not parse, or names a weekday its date does not fall on, is not used. The "
    "header names no time zone and states no epoch, so the time becomes a UTC value only under a "
    "time zone a scientist confirms for that clock."
)
XDC_START_STATEMENT_KEY = "acquisition_timestamp"
XDC_START_PATH = "timestamps.acquired_start_utc"
CLOCK_ZONE_DECISION = "set_clock_time_zone"
CLOCK_ZONE_RULE_ID = "local_clock_to_utc_via_confirmed_zone_v1"
#: Normalisation steps on the supporting witness: the literal read as a naive local time, then
#: (with a zone) that local time converted to UTC.
LOCAL_CLOCK_READ_STEP = "read_local_clock"
LOCAL_CLOCK_CONVERT_STEP = "local_clock_to_utc"
CLOCK_ZONE_COMMAND = (
    'isaac bundle decide <bundle_dir> --target experiment --decision set_clock_time_zone '
    '--value <IANA time-zone name> --by "<your name>"'
)
CLOCK_ZONE_QUESTION = "What time zone was the instrument clock that wrote these scan headers set to?"
_XDC_TIME_FORMAT = "%a %b %d %H:%M:%S %Y"
_XDC_UNUSABLE_TIME = {"timestamp_unparsed": "its line-2 time does not parse",
                      "timestamp_weekday_mismatch": "the weekday it names does not fall on its date"}
LOCAL_CLOCK_AWAITING = "awaiting_clock_time_zone"
LOCAL_CLOCK_CONVERTED = "converted"
LOCAL_CLOCK_AMBIGUOUS = "ambiguous_in_zone"
LOCAL_CLOCK_NONEXISTENT = "nonexistent_in_zone"


def _awaiting_zone_reason() -> str:
    return (
        "The scan header writes a local clock time, names no time zone and states no epoch, so it is "
        "not a UTC value and no zone is assumed. It becomes a UTC value only after a scientist "
        "confirms the time zone the instrument clock that wrote these headers was set to: "
        f"{CLOCK_ZONE_COMMAND}"
    )


_OFFSET_SHAPE = re.compile(r"[+-]\s*\d|^\d|^(?:UTC|GMT|UT)\s*[+-]", re.IGNORECASE)


def clock_zone_problem(value: Any) -> str | None:
    """Why ``value`` cannot be the instrument clock's time zone, or ``None``. THE ONE RULE both
    ``decide`` and the validator apply. ACCEPTED: ``UTC``, and any Area/Location name ``zoneinfo``
    knows — canonical names and the IANA links that keep that form (``US/Pacific``,
    ``Asia/Calcutta``) alike. REFUSED, never mapped: a non-string or empty value; a fixed offset
    (``-08:00``, ``UTC-8``, ``Etc/GMT+8``: it cannot say whether daylight saving applied on a scan's
    date); a name with no Area/Location form (an abbreviation such as ``PST`` or ``EST``, or a
    one-word name such as ``Japan``); another fixed ``Etc/`` zone; and a name ``zoneinfo`` does not know."""
    from zoneinfo import available_timezones

    if not isinstance(value, str) or not value.strip():
        return "set_clock_time_zone needs --value: the IANA time-zone name the instrument clock was set to, as text"
    if value == "UTC":
        return None
    if _OFFSET_SHAPE.search(value):
        return (f"{value!r} is a fixed UTC offset, not a time zone: an offset cannot say whether daylight "
                "saving time applied on each scan's date. Give the IANA name (Area/Location) of the zone "
                "the instrument clock was set to")
    if "/" not in value:
        return (f"{value!r} has no Area/Location form: an abbreviation (PST, EST, ...) or a one-word name is "
                "refused, because it does not reliably say which region's daylight-saving rules applied. Give the "
                "Area/Location name the instrument clock was set to (an IANA link such as US/Pacific is accepted), "
                "or UTC")
    if value.startswith("Etc/"):
        return f"{value!r} is a fixed zone under Etc/; give UTC or the Area/Location name the instrument clock was set to"
    if value not in available_timezones():
        return f"{value!r} is not a time-zone name this build's time-zone database (zoneinfo) knows"
    return None


def clock_zone_decision(bundle: Mapping) -> Mapping | None:
    """The LATEST ``set_clock_time_zone`` decision (earlier ones are kept and superseded), or ``None``."""
    found = None
    for d in bundle.get("scientist_decisions") or ():
        if isinstance(d, Mapping) and d.get("decision") == CLOCK_ZONE_DECISION:
            found = d
    return found


def is_local_clock_start(candidate: Mapping) -> bool:
    """A start-time candidate of :data:`XDC_START_RULE_ID` (its value waits on the clock's zone)."""
    return _rule_id(candidate.get("rule")) == XDC_START_RULE_ID and candidate.get("target_field_path") == XDC_START_PATH


def local_clock_to_utc(local_iso: str, zone: str) -> tuple[str, str | None]:
    """``(status, utc)`` for a naive local time in ``zone`` (rule :data:`CLOCK_ZONE_RULE_ID`).
    ``status`` is :data:`LOCAL_CLOCK_CONVERTED` with ``YYYY-MM-DDTHH:MM:SSZ``, or
    :data:`LOCAL_CLOCK_AMBIGUOUS` (both offsets valid: the fall-back fold) /
    :data:`LOCAL_CLOCK_NONEXISTENT` (the spring-forward gap) with ``None``. Never fold=0 silently."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(zone)
    naive = datetime.fromisoformat(local_iso)
    first, second = naive.replace(tzinfo=tz, fold=0), naive.replace(tzinfo=tz, fold=1)
    if first.utcoffset() != second.utcoffset():
        back = first.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
        return (LOCAL_CLOCK_AMBIGUOUS if back == naive else LOCAL_CLOCK_NONEXISTENT), None
    return LOCAL_CLOCK_CONVERTED, first.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_clock_witness(candidate: Mapping) -> Mapping | None:
    return next((e for e in candidate.get("evidence") or () if e.get("relation") == "supports"
                 and e.get("method") == "deterministic_parser"), None)


def read_xdc_literal(literal: Any) -> str | None:
    """The naive local time an XDC line-2 literal states, as ISO, by the READER'S OWN rule (format
    ``Www Mmm dd hh:mm:ss yyyy`` and the weekday must fall on the date), or ``None``."""
    from datetime import datetime

    if not isinstance(literal, str):
        return None
    try:
        parsed = datetime.strptime(literal, _XDC_TIME_FORMAT)
    except ValueError:
        return None
    return parsed.isoformat() if parsed.strftime("%a") == literal[:3] else None


def local_clock_witness_problems(candidate: Mapping) -> list[str]:
    """What is wrong with a start-time candidate's witnesses, re-read from their LITERALS (never
    from a stored local time): each parser witness's literal must read under the reader's rule and
    its ``read_local_clock`` step must say exactly that; exactly one witness ``supports``, and it is
    the EARLIEST (ties: the lower scan index, i.e. the earlier witness — they are in scan order)."""
    cid = candidate.get("candidate_id")
    problems: list[str] = []
    parsed: list[tuple[str, int, Mapping]] = []
    witnesses = [e for e in candidate.get("evidence") or () if e.get("method") == "deterministic_parser"]
    for i, e in enumerate(witnesses):
        iso = read_xdc_literal(e.get("literal_value"))
        read = [n for n in e.get("normalization") or () if n.get("step") == LOCAL_CLOCK_READ_STEP]
        if iso is None:
            problems.append(f"{cid} witness {e.get('evidence_id')} literal {e.get('literal_value')!r} is not a usable line-2 time")
            continue
        if len(read) != 1 or read[0].get("from") != e.get("literal_value") or read[0].get("to") != iso or read[0].get("rule_id") != XDC_START_RULE_ID:
            problems.append(f"{cid} witness {e.get('evidence_id')} {LOCAL_CLOCK_READ_STEP} step does not say what its literal reads ({iso})")
        if e.get("relation") not in ("supports", "context"):
            problems.append(f"{cid} witness {e.get('evidence_id')} relation {e.get('relation')!r} is neither supports nor context")
        parsed.append((iso, i, e))
    supports = [e for e in witnesses if e.get("relation") == "supports"]
    if len(supports) != 1:
        problems.append(f"{cid} has {len(supports)} supporting witnesses; exactly one (the earliest scan) supports the start")
    elif parsed and min(parsed, key=lambda t: (t[0], t[1]))[2] is not supports[0]:
        problems.append(f"{cid} supporting witness {supports[0].get('evidence_id')} is not the earliest scan time")
    return problems


#: Why a start-time candidate is not proposable to the WEBSITE once converted: true of every status.
NOT_PROPOSABLE_TO_WEBSITE = (
    "Not proposable to the website: its UTC value rests on a scientist's statement of the instrument "
    "clock's time zone (set_clock_time_zone), and the website's proposal route has no clock-zone "
    "decision to carry, so the value would travel without the evidence it rests on. It is decided "
    "in this local import instead."
)


def local_clock_start(candidate: Mapping, zone_decision: Mapping | None) -> dict:
    """What a start-time candidate derives to under ``zone_decision``: ``status``, ``value``, the
    zone and its decision id, the witness's literal and local time (RE-READ from the literal, never
    taken from a stored step), why it is not proposable (``reason`` / ``summary``) and what the
    conversion did (``explanation``). Pure: reads the candidate's own witness, writes nothing."""
    witness = _local_clock_witness(candidate)
    literal = (witness or {}).get("literal_value")
    local_iso = read_xdc_literal(literal)
    zone = zone_decision.get("value") if zone_decision is not None else None
    out = {"status": LOCAL_CLOCK_AWAITING, "value": None, "zone": None, "zone_decision_id": None,
           "literal": literal, "local_time": local_iso,
           "reason": _awaiting_zone_reason(),
           "summary": ("This time names no time zone, so it is not a UTC value. It becomes one only after "
                       "you confirm the instrument clock's time zone (set_clock_time_zone)."),
           "explanation": ("Waiting on the instrument clock's time zone: no file states it, and none is "
                           "assumed.")}
    if zone_decision is None or local_iso is None or clock_zone_problem(zone) is not None:
        return out
    out["zone"], out["zone_decision_id"] = zone, zone_decision.get("decision_id")
    status, utc = local_clock_to_utc(local_iso, zone)
    out["status"], out["value"] = status, utc
    who = f"{zone} ({zone_decision.get('decision_id')})"
    if status == LOCAL_CLOCK_CONVERTED:
        out["reason"] = NOT_PROPOSABLE_TO_WEBSITE
        out["summary"] = ("Not sent to the website: this UTC value rests on the clock time zone a scientist "
                          "stated here, which the website cannot carry.")
        out["explanation"] = (f"The scan header writes the local clock time {literal!r} and names no zone. It was "
                              f"converted to {utc} under the instrument clock's time zone a scientist confirmed, "
                              f"{who}, by rule {CLOCK_ZONE_RULE_ID}. Confirm it, or correct it.")
    elif status == LOCAL_CLOCK_AMBIGUOUS:
        out["reason"] = (f"AMBIGUOUS: the scan header's local clock time {literal!r} happens twice in {who} "
                         "(the daylight-saving fall-back hour), so it is two different UTC instants and none "
                         "is chosen; there is no value to propose. Give the UTC start with correct --value "
                         "YYYY-MM-DDTHH:MM:SSZ.")
        out["summary"] = ("This local time happens twice in the confirmed zone (the fall-back hour); no UTC "
                          "value is chosen. Give it with correct.")
        out["explanation"] = out["reason"]
    else:
        out["reason"] = (f"NONEXISTENT: the scan header's local clock time {literal!r} does not exist in {who} "
                         "(it falls in the daylight-saving spring-forward gap), so no UTC value is given and "
                         "there is none to propose. Check the zone, or give the UTC start with correct --value "
                         "YYYY-MM-DDTHH:MM:SSZ.")
        out["summary"] = ("This local time does not exist in the confirmed zone (the spring-forward gap); no "
                          "UTC value is given. Check the zone, or give it with correct.")
        out["explanation"] = out["reason"]
    return out


def _derive_local_clock_starts(bundle: dict) -> None:
    """Re-derive every start-time candidate's value, conversion step, reasons and ``local_clock``
    block from its witness and the LATEST zone decision. Idempotent; part of :func:`apply_derivations`."""
    zone_d = clock_zone_decision(bundle)
    for c in bundle.get("candidates") or ():
        if not is_local_clock_start(c):
            continue
        got = local_clock_start(c, zone_d)
        c["value"] = got["value"]
        witness = _local_clock_witness(c)
        if witness is not None:
            steps = [n for n in witness["normalization"] if n.get("step") != LOCAL_CLOCK_CONVERT_STEP]
            if got["status"] == LOCAL_CLOCK_CONVERTED:
                steps.append({"step": LOCAL_CLOCK_CONVERT_STEP, "rule_id": CLOCK_ZONE_RULE_ID, "from": got["local_time"],
                              "to": got["value"], "unit": None, "zone": got["zone"],
                              "zone_decision_id": got["zone_decision_id"]})
            witness["normalization"] = steps
        sb = c["state_basis"]
        sb["not_proposable_reason"], sb["not_proposable_summary"] = got["reason"], got["summary"]
        block = dict(c.get("local_clock") or {})
        block.update({"status": got["status"], "zone": got["zone"], "zone_decision_id": got["zone_decision_id"],
                      "local_time": got["local_time"], "literal": got["literal"], "explanation": got["explanation"]})
        c["local_clock"] = block


def local_clock_binding_problem(candidate: Mapping, decision: Mapping | None, zone_decision: Mapping | None) -> str | None:
    """Why a CONFIRMED start-time candidate may not carry its value, or ``None``. A ``correct``
    states its own UTC value and needs no binding; a ``confirm`` carries the candidate's live value,
    so it must have been made under the zone and the converted value that hold now."""
    if decision is None or decision.get("decision") != "confirm":
        return None
    binding = decision.get("clock_zone_binding")
    cid = candidate.get("candidate_id")
    again = f'isaac bundle decide <bundle_dir> --target {cid} --decision confirm --by "<your name>"'
    if not isinstance(binding, Mapping):
        return ("Confirmed, but not under a confirmed instrument-clock time zone, so the confirmation is not "
                f"bound to a converted value. Confirm it again once the zone is set: {again}")
    if decision.get("value") is not None and decision.get("value") != binding.get("value"):
        return ("Confirmed with a value of its own, which is not the value the instrument clock's time zone gives; "
                "a value a scientist supplies is a correction: isaac bundle decide <bundle_dir> --target "
                f"{cid} --decision correct --value YYYY-MM-DDTHH:MM:SSZ --by \"<your name>\"")
    zone_now = zone_decision.get("value") if zone_decision is not None else None
    if binding.get("zone") != zone_now or binding.get("value") != candidate.get("value"):
        return (f"Confirmed under the instrument clock's time zone {binding.get('zone')} "
                f"({binding.get('zone_decision_id')}) as {binding.get('value')}, but the clock time zone changed "
                f"after it was confirmed: it is now {zone_now} ({(zone_decision or {}).get('decision_id')}), "
                + (f"giving {candidate.get('value')}. Confirm it again: {again}" if candidate.get("value") is not None else
                   "under which its local time is not a single instant (ambiguous or nonexistent), so there is nothing "
                   "to confirm. Correct it with the UTC start: isaac bundle decide <bundle_dir> --target "
                   f"{cid} --decision correct --value YYYY-MM-DDTHH:MM:SSZ --by \"<your name>\""))
    return None


def clock_zone_question(bundle: Mapping) -> dict | None:
    """THE ONE beamtime-scope question about the instrument clock's zone, or ``None`` when no
    start-time candidate waits on it or a ``set_clock_time_zone`` decision exists. It states how
    many runs the answer unblocks, ONE example literal with its file, that no file states a zone,
    and the exact command. It suggests NO zone: guessing one from where the facility is would be
    exactly the guess CLAUDE.md §5 forbids."""
    if clock_zone_decision(bundle) is not None:
        return None
    waiting = [c for c in bundle.get("candidates") or () if is_local_clock_start(c)]
    if not waiting:
        return None
    runs = sorted({c["run_id"] for c in waiting if c.get("run_id")})
    example = _local_clock_witness(waiting[0]) or {}
    where = example.get("relative_path") or "(unlocated)"
    text = (
        f"{len(runs)} run(s) state their start only in the instrument clock's local time, e.g. "
        f"{example.get('literal_value')!r} in {where} ({example.get('locator')}). No file in this import "
        "states the clock's time zone, and none is assumed, so these start times stay out of the record. "
        f"{CLOCK_ZONE_QUESTION} Give its IANA name (Area/Location, or UTC; not an offset or an "
        "abbreviation). Answering converts these start times to UTC (where the zone gives exactly one instant) "
        f"for you to confirm: "
        f"{CLOCK_ZONE_COMMAND}"
    )
    return {"text": text, "run_ids": runs, "candidate_ids": [c["candidate_id"] for c in waiting],
            "example": {"literal": example.get("literal_value"), "relative_path": example.get("relative_path"),
                        "source_id": example.get("source_id"), "locator": example.get("locator")}}


def local_clock_reconfirm(bundle: Mapping) -> list[dict]:
    """Start-time candidates a scientist CONFIRMED whose confirmation no longer counts (the binding
    check of :func:`local_clock_binding_problem`, e.g. the clock zone changed after it was given):
    ``[{candidate_id, run_id, reason}]``. Read from ``bundle`` as derived; writes nothing."""
    zone_d = clock_zone_decision(bundle)
    decision_of = _decisions_by_target(bundle.get("scientist_decisions") or ())
    out = []
    for c in bundle.get("candidates") or ():
        if not is_local_clock_start(c) or c.get("value_state") != STATE_SCIENTIST_CONFIRMED:
            continue
        problem = local_clock_binding_problem(c, candidate_decision(bundle, c, decision_of), zone_d)
        if problem is not None:
            out.append({"candidate_id": c["candidate_id"], "run_id": c.get("run_id"), "reason": problem})
    return out


def clock_zone_status(bundle: Mapping) -> dict | None:
    """The recorded instrument-clock zone and what hangs on it, for ``summary.md`` and ``decide``:
    ``None`` when the bundle has no start-time candidate and no zone decision."""
    zone_d = clock_zone_decision(bundle)
    starts = [c for c in bundle.get("candidates") or () if is_local_clock_start(c)]
    if zone_d is None and not starts:
        return None
    stale = local_clock_reconfirm(bundle)
    return {
        "zone": zone_d.get("value") if zone_d else None,
        "zone_decision_id": zone_d.get("decision_id") if zone_d else None,
        "start_time_candidates": len(starts),
        "confirmations_no_longer_counting": len(stale),
        "candidate_ids_to_confirm_again": [x["candidate_id"] for x in stale],
    }


def local_clock_binding(candidate: Mapping, zone_decision: Mapping) -> dict:
    """The ``clock_zone_binding`` a confirmation of a start-time candidate records."""
    got = local_clock_start(candidate, zone_decision)
    return {"zone": got["zone"], "zone_decision_id": got["zone_decision_id"], "value": got["value"],
            "rule_id": CLOCK_ZONE_RULE_ID}


def _xdc_start_candidate(g, run_scans: Sequence[Mapping], run_id: str, bundle_cid: str, sid_of: Mapping, writable) -> tuple[dict, dict | None] | None:
    """``(candidate, order_anomaly or None)`` for ONE ``ssrl_xdc_v1`` run, or ``None`` when no scan
    has a usable line-2 time. Built through the engine's own candidate type and
    :func:`_candidate_record`, so its shape is every other candidate's."""
    from .. import historical_import as hist

    unusable: dict[str, str] = {}
    for a in g.anomalies:
        if a.get("kind") in _XDC_UNUSABLE_TIME and a.get("locator") == "line:2":
            unusable.setdefault(a.get("source_relative_path"), _XDC_UNUSABLE_TIME[a["kind"]])
    used, excluded = [], []
    for sc in run_scans:
        rel = sc.get("relative_path")
        literal, naive = sc.get("timestamp_literal"), sc.get("timestamp_naive")
        reason = unusable.get(rel) or (None if naive else "it has no line-2 time")
        if reason is None and read_xdc_literal(literal) != naive:
            # the reader's own parse, re-checked: a stored naive time is never trusted blind
            reason = "its line-2 literal does not read as the stored local time (format or weekday)"
        if reason is not None:
            excluded.append({"relative_path": rel, "source_id": sid_of.get(rel), "scan_index": sc.get("scan_index"),
                             "literal": literal, "reason": f"not used: {reason}"})
            continue
        used.append((sc.get("scan_index"), rel, literal, naive))
    if not used:
        return None
    earliest = min(used, key=lambda u: (u[3], u[0] if u[0] is not None else -1))
    index_order = [u[1] for u in sorted(used, key=lambda u: (u[0] is None, u[0] or 0))]
    time_order = [u[1] for u in sorted(used, key=lambda u: (u[3], u[0] if u[0] is not None else -1))]
    order_note = None
    anomaly = None
    if index_order != time_order:
        order_note = ("The scans' line-2 times are not in scan-index order. Every scan is kept as evidence in "
                      "scan-index order; nothing was reordered. The start is the earliest time, from "
                      f"{earliest[1]} (scan {earliest[0]}).")
        anomaly = {"kind": "scan_time_order_differs_from_index_order", "locator": "run", "detail": order_note,
                   "severity": "note", "source_relative_path": None, "scan_index": None}
    # THE WINDOW (bundle bound MAX_EVIDENCE_PER_CANDIDATE): scan-index order, and the earliest
    # scan's witness is ALWAYS in it (it is the start); what is left out is counted, never silent.
    in_order = sorted(used, key=lambda u: (u[0] is None, u[0] or 0))
    window = in_order[:MAX_EVIDENCE_PER_CANDIDATE]
    if earliest not in window:
        window = [u for u in in_order if u in window[: MAX_EVIDENCE_PER_CANDIDATE - 1] or u is earliest]
    evidence = []
    for index, rel, literal, naive in window:
        evidence.append({
            "evidence_id": f"{bundle_cid}.e{len(evidence) + 1:03d}",
            "source_id": sid_of.get(rel),
            "relative_path": _safe_relative(rel) if rel in sid_of else None,
            "locator_kind": "source_file" if rel in sid_of else "described",
            "locator": "line:2",
            "statement_key": XDC_START_STATEMENT_KEY,
            "literal_value": literal,
            "method": "deterministic_parser",
            "method_id": XDC_START_RULE_ID,
            # the earliest scan's time IS the start; the others are context for it, never contradictions
            "relation": "supports" if rel == earliest[1] else "context",
            "reading_index": None,
            "normalization": [{"step": LOCAL_CLOCK_READ_STEP, "rule_id": XDC_START_RULE_ID, "from": literal, "to": naive, "unit": None}],
        })
    rows = tuple({"scan": index, "item": None, "source": rel, "value": naive, "source_ids": [sid_of.get(rel)], "locators": ["line:2"]}
                 for index, rel, _, naive in window) if len(used) > 1 else ()
    engine = hist.SemanticCandidate(
        candidate_id=f"{g.run_key}::{XDC_START_RULE_ID}",
        kind=hist.CANDIDATE_KIND_FIELD,
        determinism=hist.DETERMINISM_DETERMINISTIC,
        rule=XDC_START_RULE,
        supporting_source_ids=tuple(rel for _, rel, _, _ in used),
        target_field_path=XDC_START_PATH,
        proposed_value=None,
        not_proposable_reason=_awaiting_zone_reason(),
        supporting_statement_total=len(used),
        distinct_sources=len({rel for _, rel, _, _ in used}),
        variation=rows,
        variation_basis="per_scan" if rows else None,
        variation_total=len(used) if rows else None,
        variation_scans=len(used) if rows else None,
    )
    cand = _candidate_record(engine, bundle_cid=bundle_cid, run_id=run_id, key=XDC_START_STATEMENT_KEY,
                             evidence=evidence, total=len(used), writable=writable)
    cand["local_clock"] = {
        "rule_id": XDC_START_RULE_ID,
        "conversion_rule_id": CLOCK_ZONE_RULE_ID,
        "timezone_stated": "not_stated",
        "start_rule": "earliest",
        "start_source_id": sid_of.get(earliest[1]),
        "start_relative_path": _safe_relative(earliest[1]),
        "scans_used": len(used),
        "excluded_scans": excluded[:MAX_EVIDENCE_PER_CANDIDATE],
        "excluded_scans_total": len(excluded),
        "order_note": order_note,
    }
    return cand, anomaly


def apply_derivations(bundle: dict) -> dict:
    """Recompute every DERIVED state in place and return ``bundle``.

    The single derivation both the writers (``import``, ``decide``, ``annotate``) and
    the validator use: candidate and missing-value states and eligibility, conflict
    states, record-group status, processing-result state, readiness and counts.
    """
    decision_of = _decisions_by_target(bundle.get("scientist_decisions") or ())
    interpreted = _interpreted_targets(bundle.get("ai_interpretations") or ())
    writable = _writable_paths()
    # the start-time candidates' values follow the clock's zone decision (latest wins), every save
    _derive_local_clock_starts(bundle)
    zone_d = clock_zone_decision(bundle)
    eligible = 0
    for c in bundle["candidates"]:
        key = ("candidate", c["candidate_id"])
        d = candidate_decision(bundle, c, decision_of)
        state = derive_value_state(c["extracted_state"], decision=d, interpreted=key in interpreted)
        c["value_state"] = state
        c["eligibility_for_official_record"] = eligibility_for_official_record(
            state,
            target_field_path=c["target_field_path"],
            value=final_value(c["value"], d, c.get("readings")),
            writable_paths=writable,
        )
        if state == STATE_SCIENTIST_CONFIRMED and is_local_clock_start(c):
            # THE BINDING: a confirmation made under one zone never carries a value converted under another
            problem = local_clock_binding_problem(c, d, zone_d)
            if problem is not None:
                c["eligibility_for_official_record"] = {"eligible": False, "reason": problem}
        eligible += c["eligibility_for_official_record"]["eligible"]
    for m in bundle["missing_values"]:
        key = ("missing_value", m["value_id"])
        d = decision_of.get(key)
        state = derive_value_state(STATE_MISSING, decision=d, interpreted=key in interpreted)
        m["value_state"] = state
        m["eligibility_for_official_record"] = eligibility_for_official_record(
            state,
            target_field_path=m["target_field_path"],
            value=final_value(None, d),
            writable_paths=writable,
        )
        eligible += m["eligibility_for_official_record"]["eligible"]
    for conflict in bundle["conflicts"]:
        d = decision_of.get(("conflict", conflict["conflict_id"]))
        base = STATE_NEEDS_REVIEW if conflict.get("resolution") else STATE_CONFLICTING
        conflict["value_state"] = derive_value_state(base, decision=d, interpreted=False)
    status_of = _decisions_by_target(
        [d for d in bundle.get("scientist_decisions") or () if d.get("decision") in GROUP_STATUS_DECISIONS]
    )
    for g in bundle.get("record_groups") or ():
        # only a STATUS decision moves a group's status (a calibration approval does not)
        d = status_of.get(("record_group", g["group_id"]))
        kind = d.get("decision") if d is not None else None
        g["status"] = GROUP_STATUS_BY_DECISION.get(None if kind == "defer" else kind, "proposed")
    for r in bundle.get("processing_results") or ():
        d = decision_of.get(("processing_result", processing_id(r)))
        kind = d.get("decision") if d is not None else None
        if kind is None or kind in NEUTRAL_DECISIONS:
            if r.get("state") not in PROCESSING_UNDECIDED_STATES:
                r["state"] = STATE_NEEDS_REVIEW  # nothing but a decision confirms it
        elif kind == "approve":
            r["state"] = STATE_SCIENTIST_CONFIRMED
        elif kind == "reject":
            r["state"] = STATE_REJECTED
        else:
            r["state"] = STATE_NEEDS_REVIEW
    _derive_processed_links(bundle)
    _derive_merge_candidate_ids(bundle)
    bundle["readiness"]["eligible_value_count"] = eligible
    states = [c["value_state"] for c in bundle["candidates"]]
    counts = bundle.get("counts") or {}
    counts.update(
        {
            "sources": len(bundle["sources"]),
            "unread_files": len(bundle["unread_files"]),
            "runs": len(bundle["runs"]),
            "run_candidates": sum(1 for r in bundle["runs"] if r["run_candidate"]),
            "runs_sharing_a_legacy_number": sum(1 for r in bundle["runs"] if r["legacy_number_shared"]),
            "samples": len(bundle["samples"]),
            "contributors": len(bundle["contributors"]),
            "candidates": len(bundle["candidates"]),
            "conflicts": len(bundle["conflicts"]),
            "missing_values": len(bundle["missing_values"]),
            "extended_context": len(bundle["extended_context"]),
            "data_quality_notes": len(bundle["data_quality_notes"]),
            "questions": len(bundle["questions"]),
            "candidate_extracted": states.count(STATE_CANDIDATE_EXTRACTED),
            "needs_review": states.count(STATE_NEEDS_REVIEW),
            "conflicting_candidates": states.count(STATE_CONFLICTING),
            "unmapped": states.count(STATE_UNMAPPED),
            "scientist_confirmed": states.count(STATE_SCIENTIST_CONFIRMED),
            "rejected": states.count(STATE_REJECTED),
        }
    )
    if "processed_outputs" in bundle:  # absent in a 1.0/1.1 bundle: no counts are expected
        counts.update(processed_output_counts(bundle["processed_outputs"]))
    bundle["counts"] = counts
    bundle["readiness"]["blocking"] = {
        "conflicts": sum(1 for c in bundle["conflicts"] if c["value_state"] in (STATE_CONFLICTING, STATE_NEEDS_REVIEW)),
        "needs_review": counts["needs_review"],
        "missing": sum(1 for m in bundle["missing_values"] if m["value_state"] == STATE_MISSING),
        "unread_files": len(bundle["unread_files"]),
    }
    if bundle["readiness"]["stage"] != "unreadable":
        bundle["readiness"]["stage"] = "in_review" if bundle.get("scientist_decisions") else "extracted"
    return bundle


# --- what the official record REQUIRES (for missing-value questions) -------------------

#: Paths `isaac export` or the composer sets itself, never asked of a scientist.
COMPOSER_SET_PATHS = frozenset(
    {"isaac_record_version", "record_id", "record_type", "record_domain", "source_type", "timestamps.created_utc"}
)
#: The sections a composed XAS characterization record carries. The vendored schema
#: requires none of them at its root; once present, each one's own ``required`` applies.
RECORD_SECTIONS = ("sample", "system", "context", "measurement")


def required_record_paths(schema: Mapping | None = None, *, record_type: str = "evidence",
                          control_mode: str | None = None) -> tuple[str, ...]:
    """Dotted paths an official record of this shape MUST carry, read from the schema.

    The root's ``required``, the ``required`` of every section in
    :data:`RECORD_SECTIONS`, recursed through required object children, plus the
    schema's own conditional rules that apply: ``record_type == evidence`` requires
    ``descriptors``; ``control_mode`` potentiostatic / galvanostatic requires the
    matching set-point. Nothing is transcribed except which sections a record carries.
    """
    if schema is None:
        from ..schema_locator import resolve_schema_path

        schema = json.loads(resolve_schema_path().read_text(encoding="utf-8"))
    out: list[str] = []

    def walk(node: Mapping, prefix: str, keys: Iterable[str]) -> None:
        props = node.get("properties") if isinstance(node, Mapping) else None
        for key in keys:
            child = props.get(key) if isinstance(props, Mapping) else None
            path = f"{prefix}.{key}" if prefix else key
            child_required = child.get("required") if isinstance(child, Mapping) else None
            if isinstance(child, Mapping) and child.get("type") == "object" and child_required:
                walk(child, path, child_required)
            elif path not in out:
                out.append(path)

    walk(schema, "", [k for k in schema.get("required") or () if k not in RECORD_SECTIONS])
    walk(schema, "", RECORD_SECTIONS)
    for rule in schema.get("allOf") or ():
        cond = json.dumps(rule.get("if") or {}, sort_keys=True)
        then = rule.get("then") or {}
        if '"record_type": {"const": "evidence"}' in cond and record_type == "evidence":
            for key in then.get("required") or ():
                walk(schema, "", [key])
        for mode in ("potentiostatic", "galvanostatic"):
            if f'"const": "{mode}"' in cond and control_mode == mode:
                ec = then["properties"]["context"]["properties"]["electrochemistry"]
                for key in ec.get("required") or ():
                    path = f"context.electrochemistry.{key}"
                    if path not in out:
                        out.append(path)
    return tuple(p for p in out if p not in COMPOSER_SET_PATHS)


def _writable_paths() -> frozenset[str]:
    """Paths this build has a write route for: the proposal targets PLUS the record's
    schema-closed required enums (``system.domain``, ``system.technique``), which the
    record answers route writes (``field_paths._record_enum_fields``). Without the second
    half ``system.domain`` — required by every record — could never be answered."""
    from .. import field_paths  # local: keep this module import-light

    return (
        frozenset(field_paths.PROPOSAL_TARGET_PATHS)
        | frozenset(field_paths._record_enum_fields())
        | frozenset(UPSTREAM_TARGET_FIELDS)
        | frozenset(LOCAL_ANSWER_FIELDS)
    )


#: DEC-76: the local export targets the schema the PORTAL enforces (upstream, pinned), so
#: the fields that schema adds and a scientist must supply are answerable here too. These
#: are NOT website write paths; the website's vendored v1.05 schema does not declare them.
#: ``path -> scope``.
UPSTREAM_TARGET_FIELDS: Mapping[str, str] = {
    "attribution.produced_by.group": "record",
    "attribution.produced_by.organization": "record",
    "context.reaction.drive": "run",
    "context.reaction.catalysis": "run",
}
#: Fields BOTH schemas declare (vendored v1.05 and the pinned portal schema) that the website
#: has no write route for, and that a beamtime's documents often state: answerable locally so
#: a scientist's answer (or a cited AI reading of their notes) has a target. ``path -> scope``.
#: ``electrolyte`` is an object requiring ``name`` AND ``concentration_M``: a record with one
#: and not the other fails the schema at export, which is the gate working.
LOCAL_ANSWER_FIELDS: Mapping[str, str] = {
    "context.electrochemistry.electrolyte.name": "run",
    "context.electrochemistry.electrolyte.concentration_M": "run",
    "context.electrochemistry.pH": "run",
    "context.electrochemistry.potential_scale": "run",
    # The as-commanded potential (``number``, volts, on ``potential_scale``). Parsers already
    # propose it from file names (e.g. ``100mV``); a run whose files state none had no
    # missing value, so a cited reading of the scientist's notes had nowhere to land.
    "context.electrochemistry.potential_setpoint_V": "run",
}
#: THE ONE SHAPE CHECK for an absorber (``set_absorber`` / ``approve_calibration`` decisions,
#: and a reading pass's ``system.element`` / ``system.edge`` findings): an element SYMBOL's
#: shape (one capital, optional lower-case letter; not a periodic-table lookup) and an edge
#: from K, L1-L3, M1-M5, exactly as written.
ABSORBER_ELEMENT_PATTERN = re.compile(r"[A-Z][a-z]?")
ABSORBER_EDGE_PATTERN = re.compile(r"K|L[1-3]|M[1-5]")


def is_absorber_element(value: Any) -> bool:
    return isinstance(value, str) and ABSORBER_ELEMENT_PATTERN.fullmatch(value) is not None


def is_absorber_edge(value: Any) -> bool:
    return isinstance(value, str) and ABSORBER_EDGE_PATTERN.fullmatch(value) is not None


#: A reading pass's absorber findings (no record field: recorded on record GROUPS), path -> half.
ABSORBER_READING_FIELDS: Mapping[str, str] = {"system.element": "element", "system.edge": "edge"}


#: The portal requires a producer (``PRODUCED_BY_MISSING``); asked as a required value.
PORTAL_REQUIRED_PATHS = ("attribution.produced_by.group", "attribution.produced_by.organization")
#: When a run states a reaction, the upstream ``context.reaction`` object requires these.
REACTION_REQUIRED_PATHS = ("context.reaction.drive", "context.reaction.catalysis")


def _target_scope(path: str | None) -> str | None:
    from .. import historical_import as hist  # local: keep this module import-light

    return hist._target_scope(path)


def _extracted_state_of(candidate) -> str:
    """Map ONE engine candidate onto the bundle's parser states (the doc's table)."""
    status = candidate.review_status
    if status == "resolved":
        # A STORED rule (a confirmed convention rule or the domain owner's standing
        # resolution) chose the value. Shown as extracted when it carries a sendable
        # value; otherwise held for review. Never scientist_confirmed in THIS bundle:
        # that confirmation was not made here, about these files.
        return STATE_CANDIDATE_EXTRACTED if candidate.proposable else STATE_NEEDS_REVIEW
    return REVIEW_STATUS_TO_STATE.get(status, STATE_NEEDS_REVIEW)


# --- the builder -----------------------------------------------------------------


class BundleBoundsExceeded(ValueError):
    """The reading cannot be expressed inside the bundle's bounds. Nothing is written."""


#: The classifier id stamped on a source the analysis-file readers recognised (``.larix``,
#: ``.pxp``): decided by the file's own extension AND whether its structure could be read.
ANALYSIS_CLASSIFIER_ID = "local_import_analysis_file_classifier_v1"
#: ``scope`` of an ``extended_context`` entry read from an analysis file. Such an entry has no
#: ``run_id`` and no ``processed_output_id``: an analysis file is never a run, never a record
#: group and never a processed output.
ANALYSIS_SCOPE = "analysis_file"


def _staging_failure_rows(generic: Any, unread: list[dict]) -> None:
    """A nested ZIP member the generic readers were never given (it could not be staged, or its
    staged bytes did not match the walk's digest) stays in ``unread_files`` with that reason
    rather than the generic "no reader for this type"."""
    by_path = {u["relative_path"]: u for u in unread}
    for failure in getattr(generic, "staging_failures", None) or ():
        row = by_path.get(failure.get("relative_path"))
        if row is not None:
            row["reason_code"] = "member_not_staged"
            row["reason"] = str(failure.get("reason") or "the member was not offered to the readers")


def _analysis_file_context(
    generic: Any,
    sources: list[dict],
    unread: list[dict],
    readers_seen: set[str],
    classifiers_seen: set[str],
) -> list[dict]:
    """Record what the analysis-file readers (Larch session, Igor experiment) found.

    Mutates ``sources`` (each file's classification and reader block) and ``unread`` (a file the
    reader could not open stays listed, now with ``reader_refused`` and the reader's own
    reason), and returns the ``extended_context`` entries. EVIDENCE ONLY: every entry is
    ``source_recorded`` with a verbatim literal and a locator, none maps to an official field,
    and none carries a run or a processed output.
    """
    by_path = {s["relative_path"]: s for s in sources}
    unread_by_path = {u["relative_path"]: u for u in unread}
    entries: list[dict] = []
    for af in getattr(generic, "analysis_files", None) or ():
        src = by_path.get(af.relative_path)
        if src is None:
            continue
        sid = src["source_id"]
        classifiers_seen.add(ANALYSIS_CLASSIFIER_ID)
        src["classification"] = {
            "source_type": f"analysis_file:{af.kind}",
            "reason": (
                "a scientist's analysis file, by its extension. It is evidence about their "
                "processing, never a run, a record group or a processed output."
            ),
            "confidence": "content" if af.refused_reason is None else "path",
            "overridable": True,
            "classifier_id": ANALYSIS_CLASSIFIER_ID,
        }
        if af.refused_reason is not None:
            src["reader"] = {
                "reader_id": af.reader_id,
                "content_read": False,
                "statements_read": 0,
                "statements_suppressed": 0,
                "partial": False,
                "skipped_total": 0,
                "refused_reason": af.refused_reason,
            }
            row = unread_by_path.get(af.relative_path)
            if row is not None:
                row["source_type"] = src["classification"]["source_type"]
                row["reason_code"] = "reader_refused"
                row["reason"] = af.refused_reason
            continue
        readers_seen.add(af.reader_id)
        src["reader"] = {
            "reader_id": af.reader_id,
            "content_read": True,
            "statements_read": len(af.entries),
            "statements_suppressed": af.suppressed_total,
            "partial": af.partial,
            "skipped_total": af.skipped_total,
            "refused_reason": None,
        }
        for n, e in enumerate(af.entries, 1):
            entries.append(
                {
                    "entry_id": f"{af.reader_id}:{sid}#{n}",
                    "concept": str(e["concept"]),
                    "raw_literal": e["literal"],
                    "source_id": sid,
                    "relative_path": _safe_relative(af.relative_path),
                    "locator": e["locator"],
                    "normalized_value": None,
                    "unit": None,
                    "normalization_rule_id": None,
                    "parser_id": af.reader_id,
                    "scope": ANALYSIS_SCOPE,
                    "official_path": None,
                    "value_state": STATE_SOURCE_RECORDED,
                    "is_official_field_value": False,
                    "run_id": None,
                }
            )
    return entries


def _split_locator(locator: str, archive_paths: Sequence[str]):
    from ..bl15 import reconstruct as rc  # local: bl15 imports historical_import

    return rc.split_statement_locator(locator, archive_paths)


def _candidate_record(c, *, bundle_cid: str, run_id: str | None, key: str, evidence: list[dict], total: int, writable) -> dict:
    """ONE bundle candidate from ONE engine :class:`SemanticCandidate` and its evidence window —
    the single shape every candidate has, whichever rule produced it."""
    extracted = _extracted_state_of(c)
    state = derive_value_state(extracted, decision=None, interpreted=False)
    distinct: list = []
    for e in evidence:
        if e["literal_value"] not in distinct:
            distinct.append(e["literal_value"])
    literals = distinct[:MAX_OBSERVED_LITERALS]
    return {
        "candidate_id": bundle_cid,
        "engine_candidate_id": c.candidate_id,
        "kind": c.kind,
        "run_id": run_id,
        "scope": "run" if run_id else "beamtime",
        "statement_key": key,
        "target_field_path": c.target_field_path,
        "target_write_scope": _target_scope(c.target_field_path) or UPSTREAM_TARGET_FIELDS.get(c.target_field_path) or LOCAL_ANSWER_FIELDS.get(c.target_field_path),
        "value": c.proposed_value,
        "observed_literals": literals,
        # THE CAP IS STATED, never silent (review L3).
        "observed_literals_total": len(distinct),
        "observed_literals_truncated": len(distinct) > len(literals),
        # THE ONE INDEX SPACE for choosing a reading: the engine's RAW
        # disagreement readings, in order, duplicates kept (review L3).
        "readings": [r.get("value") for r in c.disagreement],
        "standing_resolution": dict(c.standing_resolution) if c.standing_resolution else None,
        "extracted_state": extracted,
        "value_state": state,
        "state_basis": {
            "review_status": c.review_status,
            "agreement": c.agreement,
            "determinism": c.determinism,
            "proposable": c.proposable,
            "unresolved_reason": c.unresolved_reason,
            "not_proposable_reason": c.not_proposable_reason,
            "not_proposable_summary": _local_plain_reason(c),
            "resolved_by_rule": c.resolved_by_rule,
        },
        "rule": c.rule,
        "evidence": evidence,
        "evidence_total": total,
        "evidence_truncated": total > len(evidence),
        "distinct_sources": c.distinct_sources,
        "variation": (
            {
                "basis": c.variation_basis,
                "rows_total": c.variation_total if c.variation_total is not None else len(c.variation),
                "scans": c.variation_scans,
                "rows": [dict(v) for v in c.variation],
            }
            if c.variation
            else None
        ),
        "eligibility_for_official_record": eligibility_for_official_record(
            state,
            target_field_path=c.target_field_path,
            value=c.proposed_value,
            writable_paths=writable,
        ),
    }


def build_bundle(
    reading,
    candidates: Sequence,
    *,
    evidence_by_source: Mapping[str, Sequence],
    source_kind: str,
    created_utc: str,
    bundle_id: str | None = None,
    local_root_hint: str | None = None,
    profile_request: str = "auto",
    isaac_commit: str | None = None,
    tool_version: str = "0.1.0",
    generic: Any = None,
) -> dict:
    """Build a v1 bundle from ONE :func:`historical_import.read_local_archive` result.

    Deterministic given its inputs (``bundle_id`` and ``created_utc`` aside). Raises
    :class:`BundleBoundsExceeded` rather than silently dropping runs or candidates.
    """
    from isaac_records.ids import new_record_id

    if len(reading.units) > MAX_RUNS:
        raise BundleBoundsExceeded(f"{len(reading.units)} runs exceeds the bound of {MAX_RUNS}.")
    if len(candidates) > MAX_CANDIDATES:
        raise BundleBoundsExceeded(
            f"{len(candidates)} candidates exceeds the bound of {MAX_CANDIDATES}."
        )

    writable = _writable_paths()
    manifest = list(reading.manifest)
    archive_paths = [row["archive_path"] for row in manifest]
    sid_of = {path: f"src-{i:04d}" for i, path in enumerate(archive_paths, 1)}
    reading_rows = {row["archive_path"]: row for row in reading.reading}
    default_assignment = {
        "profile_ids": [reading.profile_id],
        "profile_versions": [reading.profile_version],
        "binding_ids": ["build-default"],
        "ambiguous": False,
    }

    # -- evidence index: (concept, full locator) -> SourceEvidence ------------------
    from ..bl15 import reconstruct as rc

    ev_index: dict[tuple[str, str], Any] = {}
    for items in evidence_by_source.values():
        for item in items:
            ev_index.setdefault((item.concept, rc.statement_locator(item)), item)

    # -- sources + unread ------------------------------------------------------------
    sources: list[dict] = []
    unread: list[dict] = []
    readers_seen: set[str] = set()
    classifiers_seen: set[str] = set()
    for row in manifest:
        path = row["archive_path"]
        rr = reading_rows.get(path, {})
        parser_id = rr.get("parser_id")
        if parser_id:
            readers_seen.add(parser_id)
        if row.get("classifier_id"):
            classifiers_seen.add(row["classifier_id"])
        convention = row.get("convention")
        assignment = (
            {
                "profile_ids": list(convention.get("profile_ids") or []),
                "profile_versions": [_profile_version(pid) for pid in convention.get("profile_ids") or []],
                "binding_ids": list(convention.get("binding_ids") or []),
                "ambiguous": bool(convention.get("ambiguous")),
            }
            if isinstance(convention, Mapping)
            else dict(default_assignment)
        )
        content_read = bool(parser_id) and rr.get("refused_reason") is None
        sources.append(
            {
                "source_id": sid_of[path],
                "relative_path": path,
                "basename": row.get("basename") or "",
                "extension": row.get("extension") or "",
                "parent_dir": row.get("parent_dir") or "",
                "depth": int(row.get("depth") or 0),
                "size_bytes": row.get("size_bytes"),
                "content_sha256": row.get("content_sha256"),
                "sha256_basis": "computed_by_the_walk_over_the_bytes_read_on_this_machine",
                "local_only": True,
                "classification": {
                    "source_type": row.get("source_type") or "unknown",
                    "reason": row.get("reason"),
                    "confidence": row.get("confidence"),
                    "overridable": row.get("overridable"),
                    "classifier_id": row.get("classifier_id"),
                },
                "reader": {
                    "reader_id": parser_id,
                    "content_read": content_read,
                    "statements_read": int(rr.get("statements_read") or 0),
                    "statements_suppressed": int(rr.get("statements_suppressed") or 0),
                    "partial": bool(rr.get("partial")),
                    "skipped_total": int(rr.get("skipped_total") or 0),
                    "refused_reason": rr.get("refused_reason"),
                },
                "naming_profile": assignment,
            }
        )
        if not content_read:
            if not parser_id and (rr.get("refused_reason") or "").startswith("This build has no reader"):
                code = "no_reader_for_source_type"
            elif not parser_id:
                code = "content_unavailable"
            else:
                code = "reader_refused"
            unread.append(
                {
                    "relative_path": path,
                    "source_id": sid_of[path],
                    "source_type": row.get("source_type"),
                    "reason_code": code,
                    "reason": rr.get("refused_reason")
                    or "No reader produced statements from this file's contents.",
                    "local_only": True,
                }
            )
    for refusal in reading.inventory.get("refused") or ():
        clean = sanitized_refusal(refusal)
        unread.append(
            {
                "relative_path": clean["archive_path"],
                "source_id": None,
                "source_type": None,
                "reason_code": clean["reason"],
                "reason": clean["detail"],
                "local_only": True,
            }
        )

    # -- runs -----------------------------------------------------------------------------
    rel_state = dict(reading.relationships or {})
    # KEYED BY POSITION AND BY RELATIVE PATH, NEVER BY STEM (real-data finding R1): two
    # acquisitions with the same file name in different folders are two engine units
    # with the SAME stem and the SAME engine candidate ids. The stem stays a label.
    rel_list = [u for u in rel_state.get("units") or () if isinstance(u, Mapping)]
    rel_by_path = {u.get("acquisition_path"): u for u in rel_list if u.get("acquisition_path")}
    run_ids = [f"run-{i:03d}" for i in range(1, len(reading.units) + 1)]
    run_of_acquisition = {u.acquisition_path: run_ids[i] for i, u in enumerate(reading.units) if u.acquisition_path}
    runs_of_stem: dict[str, list[str]] = {}
    for i, u in enumerate(reading.units):
        runs_of_stem.setdefault(u.stem, []).append(run_ids[i])
    run_of_stem = {stem: rids[0] for stem, rids in runs_of_stem.items() if len(rids) == 1}
    by_legacy: dict[int, list[str]] = {}
    for i, u in enumerate(reading.units):
        if u.legacy_number is not None:
            by_legacy.setdefault(u.legacy_number, []).append(run_ids[i])

    # candidates, in engine order: each unit's are consecutive (read_archive_at extends
    # them unit by unit), so they are assigned by POSITION, not by their engine id.
    cand_bundle_ids = [f"cand-{i:04d}" for i in range(1, len(candidates) + 1)]
    run_of_index: dict[int, str] = {}
    unit_cand_ids: list[list[str]] = []
    used: set[int] = set()
    cursor = 0
    for ui, u in enumerate(reading.units):
        mine: list[str] = []
        for cid in u.candidate_ids:
            idx = next(
                (j for j in range(cursor, len(candidates)) if j not in used and candidates[j].candidate_id == cid),
                None,
            )
            if idx is None:
                continue
            used.add(idx)
            cursor = idx + 1
            run_of_index[idx] = run_ids[ui]
            mine.append(cand_bundle_ids[idx])
        unit_cand_ids.append(mine)
    shared_ids_set = set(reading.shared_candidate_ids)
    shared_bundle_ids = [cand_bundle_ids[j] for j, c in enumerate(candidates) if j not in used and c.candidate_id in shared_ids_set]

    # samples, from the relationship groups
    samples: list[dict] = []
    sample_of_stem: dict[str, str] = {}
    for i, group in enumerate(rel_state.get("groups") or (), 1):
        if not isinstance(group, Mapping):
            continue
        sample_id = f"sample-{i:02d}"
        stems = [s for s in group.get("stems") or () if s in runs_of_stem]
        for s in stems:
            sample_of_stem[s] = sample_id
        samples.append(
            {
                "sample_id": sample_id,
                "group_token": group.get("group_token"),
                "run_ids": [rid for s in stems for rid in runs_of_stem[s]],
                "legacy_low": group.get("legacy_low"),
                "legacy_high": group.get("legacy_high"),
                "contiguous": group.get("contiguous"),
                "sample_name_readings": [],
                "basis": (
                    "Grouped by the filename's group token under the naming profile. A "
                    "grouping of runs, not a confirmed sample identity."
                ),
            }
        )

    # contributors (EVIDENCE about people; never the naming profile, never an actor)
    contributors: dict[str, dict] = {}

    def _add_contributor(row: Mapping, run_id: str | None) -> str | None:
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        entry = contributors.get(name)
        if entry is None:
            entry = contributors[name] = {
                "contributor_id": f"person-{len(contributors) + 1:03d}",
                "name": name,
                "labels": [],
                "scope": "run" if run_id else "beamtime",
                "run_ids": [],
                "evidence": [],
                "role": "provenance",
                "is_actor": False,
                "is_naming_profile": False,
                "value_state": STATE_SOURCE_RECORDED,
            }
        label = row.get("label")
        if isinstance(label, str) and label not in entry["labels"]:
            entry["labels"].append(label)
        if run_id and run_id not in entry["run_ids"]:
            entry["run_ids"].append(run_id)
        if run_id is None:
            entry["scope"] = "beamtime"
        witness = {
            "source_id": sid_of.get(row.get("source_path")),
            "locator": row.get("locator"),
            "section": row.get("section"),
            "basis": row.get("basis"),
        }
        if witness not in entry["evidence"]:
            entry["evidence"].append(witness)
        return entry["contributor_id"]

    # data-quality notes, deduplicated by (source, locator) across runs
    dq_notes: dict[tuple, dict] = {}

    def _add_note(row: Mapping, run_id: str | None) -> str:
        key = (row.get("source_path"), row.get("locator"), row.get("text"))
        note = dq_notes.get(key)
        if note is None:
            note = dq_notes[key] = {
                "note_id": f"dq-{len(dq_notes) + 1:03d}",
                "text": str(row.get("text") or ""),
                "run_ids": [],
                "source_id": sid_of.get(row.get("source_path")),
                "locator": row.get("locator"),
                "label": row.get("label"),
                "writes_qc_status": False,
                "legacy_number_shared": bool(row.get("legacy_number_shared")),
                "value_state": STATE_SOURCE_RECORDED,
            }
        if run_id and run_id not in note["run_ids"]:
            note["run_ids"].append(run_id)
        return note["note_id"]

    runs: list[dict] = []
    conflicts_of_run: dict[str, list] = {}
    for ui, u in enumerate(reading.units):
        run_id = run_ids[ui]
        rel = rel_by_path.get(u.acquisition_path) or (rel_list[ui] if ui < len(rel_list) else {})
        conflicts_of_run[run_id] = list(rel.get("conflicts") or ())
        shares = [r for r in by_legacy.get(u.legacy_number, []) if r != run_id] if u.legacy_number is not None else []
        contributor_ids = []
        beamtime_rows = [dict(c) for c in reading.beamtime_contributors if isinstance(c, Mapping)]
        for person in u.contributors:
            if dict(person) in beamtime_rows:
                continue  # the engine appends the beamtime's own people to every unit; listed once below
            cid = _add_contributor(person, run_id)
            if cid and cid not in contributor_ids:
                contributor_ids.append(cid)
        note_ids = [_add_note(n, run_id) for n in u.data_quality_notes]
        other = {
            key: rel.get(key)
            for key in ("duplicate_copies", "suppressed_duplicate_acquisitions", "processed_products", "internal_declaration")
            if rel.get(key)
        }
        runs.append(
            {
                "run_id": run_id,
                # THE STABLE KEY: the acquisition file's own name and its bytes, never
                # the legacy number (two acquisitions may share one).
                "run_key": u.acquisition_identity or f"{u.stem}@{u.acquisition_path}",
                "label": u.label,
                "stem": u.stem,
                "source_type": u.source_type,
                "run_candidate": u.run_candidate,
                "legacy_number": u.legacy_number,
                "legacy_number_shared": u.legacy_number_shared,
                "shares_legacy_number_with": shares,
                "group_token": u.group_token,
                "sample_id": sample_of_stem.get(u.stem),
                "acquisition_source_id": sid_of.get(u.acquisition_path),
                "scans": [
                    {
                        "source_id": sid_of.get(s.get("path")),
                        "relative_path": s.get("path"),
                        "scan_index": s.get("scan_index"),
                    }
                    for s in rel.get("scans") or ()
                    if isinstance(s, Mapping) and _safe_relative(s.get("path"))
                ],
                "scan_count": u.scan_count,
                "declared_by": [
                    {
                        "macro_source_id": sid_of.get(d.get("macro_path")),
                        "macro_path": d.get("macro_path"),
                        "block_index": d.get("block_index"),
                        "declared_target": d.get("declared_target"),
                        "acquired": d.get("acquired"),
                    }
                    for d in rel.get("declared_by") or ()
                    if isinstance(d, Mapping) and _safe_relative(d.get("macro_path"))
                ],
                "note_rows": [
                    {
                        "source_id": sid_of.get(n.get("source_path")),
                        "locator": str(n.get("locator") or ""),
                        "value": n.get("value"),
                    }
                    for n in rel.get("note_rows") or ()
                    if isinstance(n, Mapping)
                ],
                "other_relationships": other,
                "candidate_ids": unit_cand_ids[ui],
                "shares_file_name_with": [r for r in runs_of_stem[u.stem] if r != run_id],
                "conflict_ids": [],  # filled below
                "contributor_ids": contributor_ids,
                "data_quality_note_ids": note_ids,
                "naming_profile": dict(u.applicability),
                "signal_selection": dict(u.signal_selection) if u.signal_selection else None,
            }
        )
    for person in reading.beamtime_contributors:
        _add_contributor(person, None)
    for note in reading.unbound_data_quality_notes:
        _add_note(note, None)
    # -- runs the GENERIC readers found (LOCAL-3), in files the engine did not read ------
    generic_statements: list[dict] = []
    generic_claimed: set[str] = set()
    processed_outputs: list[dict] = []
    xdc_runs: list[tuple] = []  # (run_id, generic run, its scans): ssrl_xdc_scan_start_v1 applies

    def _statement_entry(g, k: int, st: Mapping, *, run_id: str | None, po_id: str | None) -> dict:
        path = st.get("source_relative_path")
        entry = {
            # "#p" for a processed output's statements: a stem group split file by file
            # (one stated, one unstated XDI file) must not mint one entry id twice.
            "entry_id": f"{g.run_key}#{'p' if po_id else 's'}{k}",
            "concept": str(st.get("key") or ""),
            "raw_literal": st.get("literal") if isinstance(st.get("literal"), str) else json.dumps(st.get("literal")),
            "source_id": sid_of.get(path),
            "relative_path": _safe_relative(path) if path in sid_of else None,
            "locator": st.get("locator"),
            "normalized_value": None,
            "unit": None,
            "normalization_rule_id": None,
            "parser_id": g.reader_id or g.profile,
            "scope": "processed_output" if po_id else "run",
            "official_path": None,
            "value_state": STATE_SOURCE_RECORDED,
            "is_official_field_value": False,
            "run_id": run_id,
        }
        if po_id:
            entry["processed_output_id"] = po_id
        return entry

    def _reader_block(g, n_statements: int) -> dict:
        return {
            "reader_id": g.reader_id or g.profile,
            "profile": g.profile,
            "profile_version": _reader_version(g.profile) or _reader_version(g.reader_id or ""),
            "statements_total": n_statements,
            "statements_kept": min(n_statements, MAX_GENERIC_STATEMENTS_PER_RUN),
        }

    if generic is not None:
        for claim in getattr(generic, "claims", None) or ():
            generic_claimed.add(claim["relative_path"])
        for g in getattr(generic, "runs", None) or ():
            all_scans = [sc for sc in g.scans if _safe_relative(sc.get("relative_path"))]
            line1 = {st.get("source_relative_path"): st.get("literal") for st in g.statements if st.get("key") == "xdi_version"}
            judged = {
                sc["relative_path"]: _processing_origin(sc, line1.get(sc["relative_path"]))
                for sc in all_scans
                if (g.role_hints or {}).get("kind") == PROCESSED_OUTPUT_KIND
            }
            origin = {p: o for p, (o, _) in judged.items()}
            # a file whose line 1 names another application but whose fields mention
            # Athena/Demeter stays an acquisition; the disagreement is recorded on it
            disagreements = [
                {**d, "source_relative_path": p, "scan_index": None} for p, (o, d) in judged.items() if d is not None
            ]
            processed_paths = {p for p, o in origin.items() if o is not None}
            # -- the scientist's processed output: evidence and a reference result ---------
            if processed_paths:
                po_id = "po-" + hashlib.sha256(f"processed:{g.run_key}".encode("utf-8")).hexdigest()[:16]
                po_statements = [st for st in g.statements if st.get("source_relative_path") in processed_paths]
                kept = po_statements[:MAX_GENERIC_STATEMENTS_PER_RUN]
                stated: dict[str, list[dict]] = {name: [] for name in ("processed_by", *_PROCESSED_STATED_KEYS.values())}
                for st in kept:
                    name = _PROCESSED_STATED_KEYS.get(str(st.get("key") or ""))
                    if name:
                        stated[name].append(
                            {
                                "literal": st.get("literal"),
                                "source_id": sid_of.get(st.get("source_relative_path")),
                                "locator": st.get("locator"),
                            }
                        )
                files = []
                for sc in all_scans:
                    rel = sc["relative_path"]
                    if rel not in processed_paths:
                        continue
                    o = origin[rel]
                    if o["processed_by"]:
                        stated["processed_by"].append(
                            {
                                "literal": o["processed_by"] + (f"/{o['application_version']}" if o["application_version"] else ""),
                                "source_id": sid_of.get(rel),
                                "locator": "line:1",
                            }
                        )
                    files.append(
                        {
                            "source_id": sid_of.get(rel),
                            "relative_path": rel,
                            "sha256": sc.get("sha256"),
                            "size_bytes": sc.get("size_bytes"),
                            "extension": sc.get("extension"),
                            "columns": list(sc.get("columns") or [])[:50],
                            "points": sc.get("points"),
                            "processing_origin": o,
                        }
                    )
                entries = [_statement_entry(g, k, st, run_id=None, po_id=po_id) for k, st in enumerate(kept)]
                generic_statements.extend(entries)
                processed_outputs.append(
                    {
                        "processed_output_id": po_id,
                        "output_key": g.run_key,
                        "label": g.label,
                        "directory": g.directory,
                        "role": "reference_result",
                        "is_acquisition": False,
                        "becomes_a_record": False,
                        "statement": (
                            "The scientists' own processed output, as its header states. A "
                            "reference result and evidence: never a run, never a record group."
                        ),
                        "reader": _reader_block(g, len(po_statements)),
                        "files": files,
                        "states": stated,
                        "anomalies": [a for a in g.anomalies if a.get("source_relative_path") in processed_paths][:50],
                        "extended_context_entry_ids": [e["entry_id"] for e in entries],
                        "proposed_links": [],
                        "link_note": None,
                        "value_state": STATE_SOURCE_RECORDED,
                    }
                )
            # -- an acquisition (everything else the generic readers found) -----------------
            run_scans = [sc for sc in all_scans if sc["relative_path"] not in processed_paths]
            if processed_paths and not run_scans:
                continue
            run_statements = [st for st in g.statements if st.get("source_relative_path") not in processed_paths]
            run_id = f"run-{len(runs) + 1:03d}"
            scans = [
                {
                    "source_id": sid_of.get(sc.get("relative_path")),
                    "relative_path": sc.get("relative_path"),
                    "scan_index": sc.get("scan_index"),
                }
                for sc in run_scans
            ]
            first = scans[0]["source_id"] if scans else None
            runs.append(
                {
                    "run_id": run_id,
                    "run_key": g.run_key,
                    "label": g.label,
                    "stem": g.label,
                    "source_type": f"generic:{g.profile}",
                    "run_candidate": bool(scans),
                    "legacy_number": None,
                    "legacy_number_shared": False,
                    "shares_legacy_number_with": [],
                    "shares_file_name_with": [],
                    "group_token": None,
                    "sample_id": None,
                    "acquisition_source_id": first,
                    "scans": scans,
                    "scan_count": len(scans),
                    "declared_by": [],
                    "note_rows": [],
                    "other_relationships": {
                        "companions": [c.get("relative_path") for c in g.companions if _safe_relative(c.get("relative_path"))],
                        "anomalies": (disagreements + [a for a in g.anomalies if a.get("source_relative_path") not in processed_paths])[:50],
                        "header_differences": list(g.header_differences)[:50],
                    },
                    "candidate_ids": [],
                    "conflict_ids": [],
                    "contributor_ids": [],
                    "data_quality_note_ids": [],
                    "naming_profile": {},
                    "signal_selection": None,
                    "reader": _reader_block(g, len(run_statements)),
                }
            )
            # STATEMENTS ARE SOURCE EVIDENCE, NEVER FIELD VALUES: no statement maps to an
            # official field unless an explicit, tested rule says so. There is exactly ONE such
            # rule, ssrl_xdc_scan_start_v1 (an ssrl_xdc_v1 run's line-2 scan times ->
            # timestamps.acquired_start_utc, valueless until the clock's zone is confirmed; built
            # below as a candidate). The statements themselves stay extended context either way.
            for k, st in enumerate(run_statements[:MAX_GENERIC_STATEMENTS_PER_RUN]):
                generic_statements.append(_statement_entry(g, k, st, run_id=run_id, po_id=None))
            if g.profile == XDC_PROFILE_ID and run_scans:
                xdc_runs.append((run_id, g, run_scans))
        # ANALYSIS FILES (.larix, .pxp): evidence in extended_context, never a run.
        generic_statements.extend(
            _analysis_file_context(generic, sources, unread, readers_seen, classifiers_seen)
        )
        _staging_failure_rows(generic, unread)
        if generic_claimed:
            unread = [u for u in unread if u["relative_path"] not in generic_claimed]
    propose_processed_links(processed_outputs, runs)
    runs_by_id = {r["run_id"]: r for r in runs}

    # -- candidates -------------------------------------------------------------------
    decisions: list = []  # a freshly built bundle has none
    out_candidates: list[dict] = []
    evidence_windows_truncated = 0
    conflicts: list[dict] = []
    for ci, c in enumerate(candidates):
        bundle_cid = cand_bundle_ids[ci]
        run_id = run_of_index.get(ci)
        statements = list(c.supporting_statements)
        key = (
            statements[0].get("key")
            if statements and isinstance(statements[0].get("key"), str)
            else c.candidate_id.split("::", 1)[-1]
        )
        evidence, total = _evidence_for(
            c, bundle_cid, key, archive_paths, sid_of, ev_index
        )
        if total > len(evidence):
            evidence_windows_truncated += 1
        extracted = _extracted_state_of(c)
        out_candidates.append(
            _candidate_record(c, bundle_cid=bundle_cid, run_id=run_id, key=key, evidence=evidence, total=total, writable=writable)
        )
        if c.disagreement and (extracted == STATE_CONFLICTING or c.resolved_by_rule):
            # A disagreement a STORED rule resolved is still a conflict entry (review
            # L4): every reading is kept, and the rule that chose is carried beside it.
            engine_conflict = None
            if "::conflict::" in c.candidate_id and run_id:
                try:
                    idx = int(c.candidate_id.rsplit("::", 1)[-1])
                    engine_conflict = conflicts_of_run.get(run_id, [])[idx]
                except (ValueError, IndexError):
                    engine_conflict = None
            conflicts.append(
                _conflict_from_candidate(
                    f"conf-{len(conflicts) + 1:03d}", c, bundle_cid, run_id, engine_conflict,
                    archive_paths, sid_of,
                )
            )

    # ssrl_xdc_scan_start_v1: one start-time candidate per XDC run, continuing the cand sequence
    for run_id, g, run_scans in xdc_runs:
        built = _xdc_start_candidate(g, run_scans, run_id, f"cand-{len(out_candidates) + 1:04d}", sid_of, writable)
        if built is None:
            continue  # no scan states a usable time: the run's start stays a missing value
        cand, order_anomaly = built
        out_candidates.append(cand)
        runs_by_id[run_id]["candidate_ids"].append(cand["candidate_id"])
        if order_anomaly is not None:
            runs_by_id[run_id]["other_relationships"]["anomalies"].append(order_anomaly)
    if len(out_candidates) > MAX_CANDIDATES:
        raise BundleBoundsExceeded(f"{len(out_candidates)} candidates exceeds the bound of {MAX_CANDIDATES}.")

    # corpus-level conflicts (no candidate carries them)
    for cc in rel_state.get("corpus_conflicts") or ():
        if not isinstance(cc, Mapping):
            continue
        readings = []
        involved: list[str] = []
        for i, r in enumerate(cc.get("readings") or ()):
            path = r.get("source_path")
            stem_run = (run_of_acquisition.get(path) or run_of_stem.get(path)) if isinstance(path, str) else None
            if stem_run and stem_run not in involved:
                involved.append(stem_run)
            readings.append(
                {
                    "reading_index": i,
                    "value": r.get("value"),
                    "witnesses": [
                        {
                            "source_id": sid_of.get(path),
                            "relative_path": _safe_relative(path),
                            "locator": str(r.get("locator") or ""),
                            "source_role": r.get("source_role"),
                        }
                    ],
                }
            )
        if len(readings) < 2:
            # A one-sided "conflict" (a macro target that was never acquired) is a
            # relationship fact, recorded as such on the bundle rather than dropped.
            readings.append(
                {
                    "reading_index": len(readings),
                    "value": None,
                    "witnesses": [
                        {
                            "source_id": None,
                            "relative_path": None,
                            "locator": "absent: no source in this archive states the counterpart",
                            "source_role": None,
                        }
                    ],
                }
            )
        conflicts.append(
            {
                "conflict_id": f"conf-{len(conflicts) + 1:03d}",
                "engine_conflict_id": cc.get("conflict_id"),
                "kind": str(cc.get("kind") or "corpus_conflict"),
                "subject": cc.get("subject"),
                "candidate_id": None,
                "run_ids": involved,
                "readings": readings,
                "explanation": cc.get("explanation"),
                "recommendation": cc.get("recommendation"),
                "value_state": STATE_CONFLICTING,
            }
        )
    # SAME FILE NAME, DIFFERENT FOLDERS (R1): both runs are kept; the pair is a review
    # item, because it may be one acquisition copied twice or two that were named alike.
    for stem, rids in runs_of_stem.items():
        if len(rids) < 2:
            continue
        readings = []
        for i, rid in enumerate(rids):
            run = runs_by_id[rid]
            readings.append(
                {
                    "reading_index": i,
                    "value": next((s["relative_path"] for s in sources if s["source_id"] == run["acquisition_source_id"]), None),
                    "witnesses": [
                        {
                            "source_id": run["acquisition_source_id"],
                            "relative_path": next((s["relative_path"] for s in sources if s["source_id"] == run["acquisition_source_id"]), None),
                            "locator": "the acquisition file",
                            "source_role": None,
                        }
                    ],
                }
            )
        conflicts.append(
            {
                "conflict_id": f"conf-{len(conflicts) + 1:03d}",
                "engine_conflict_id": None,
                "kind": "same_file_name_different_folders",
                "subject": stem,
                "candidate_id": None,
                "run_ids": list(rids),
                "readings": readings,
                "explanation": (
                    f"{len(rids)} acquisition files share the name {stem!r} in different folders. "
                    "Each is kept as its own run. They may be one measurement copied twice "
                    "(possible duplicate data) or different measurements named alike; nothing "
                    "here decides which."
                ),
                "recommendation": None,
                "resolution": None,
                "value_state": STATE_CONFLICTING,
            }
        )
    for conflict in conflicts:
        for rid in conflict["run_ids"]:
            if rid in runs_by_id:
                runs_by_id[rid]["conflict_ids"].append(conflict["conflict_id"])

    # sample-name readings
    for sample in samples:
        rids = set(sample["run_ids"])
        names: list[str] = []
        for cand in out_candidates:
            if cand["run_id"] in rids and cand["statement_key"] == "sample_name":
                for v in [cand["value"], *cand["observed_literals"]]:
                    if isinstance(v, str) and v not in names:
                        names.append(v)
        sample["sample_name_readings"] = names

    # -- missing values: a writable target no source states. Nothing is defaulted. -----
    missing: list[dict] = []
    targets_by_run: dict[str | None, set[str]] = {}
    beamtime_targets: dict[str, list[str]] = {}
    for cand in out_candidates:
        if cand["target_field_path"]:
            targets_by_run.setdefault(cand["run_id"], set()).add(cand["target_field_path"])
            if cand["run_id"] is None:
                beamtime_targets.setdefault(cand["target_field_path"], []).append(cand["candidate_id"])
    any_target = set().union(*targets_by_run.values()) if targets_by_run else set()
    reason = (
        "No source in this archive states a value for this field. It stays missing: "
        "nothing is defaulted, and a beamtime-level statement is never copied onto a "
        "run (DEC-69)."
    )
    for path in sorted(writable):
        scope = _target_scope(path) or UPSTREAM_TARGET_FIELDS.get(path) or LOCAL_ANSWER_FIELDS.get(path)
        if scope == "record":
            # ONE record-scope question, asked whenever ANY run that becomes a record lacks
            # a reading for it (real-data finding D3): "some run states it" used to suppress
            # the question, leaving the other runs' records with no way to be answered.
            lacking = [r for r in runs if r["run_candidate"] and path not in targets_by_run.get(r["run_id"], set())]
            if lacking and (path not in any_target or targets_by_run.get(None, set()).isdisjoint({path})):
                missing.append(_missing(len(missing), None, path, "record", reason, beamtime_targets, writable))
            continue
        for run in runs:
            if not run["run_candidate"]:
                continue
            if path not in targets_by_run.get(run["run_id"], set()):
                missing.append(_missing(len(missing), run["run_id"], path, "run", reason, beamtime_targets, writable))

    unmapped = [
        {
            "candidate_id": cand["candidate_id"],
            "run_id": cand["run_id"],
            "statement_key": cand["statement_key"],
            "reason": cand["state_basis"]["not_proposable_summary"]
            or cand["state_basis"]["not_proposable_reason"],
        }
        for cand in out_candidates
        if cand["value_state"] == STATE_UNMAPPED
    ]

    extended = []
    for entry in reading.extended_context_entries:
        src = entry.get("source")
        extended.append(
            {
                "entry_id": str(entry.get("entry_id") or ""),
                "concept": str(entry.get("concept") or ""),
                "raw_literal": entry.get("raw_literal"),
                "source_id": sid_of.get(src),
                "relative_path": _safe_relative(src),
                "locator": entry.get("locator"),
                "normalized_value": entry.get("normalized_value"),
                "unit": entry.get("unit"),
                "normalization_rule_id": _rule_id(entry.get("normalization_rule")),
                "parser_id": entry.get("parser_id"),
                "scope": entry.get("scope"),
                "official_path": entry.get("official_path"),
                "value_state": STATE_SOURCE_RECORDED,
                "is_official_field_value": False,
            }
        )

    questions: list[dict] = []  # built by refresh_questions() once the bundle exists

    # -- naming profiles ---------------------------------------------------------------
    naming = [
        {
            "binding_id": str(b.get("binding_id") or ""),
            "profile_id": str(b.get("profile_id") or ""),
            "profile_version": b.get("profile_version"),
            "display_name": b.get("profile_display_name"),
            "scope": b.get("scope"),
            "basis": b.get("basis"),
            "selector_description": (b.get("selector") or {}).get("description")
            if isinstance(b.get("selector"), Mapping)
            else None,
            "source_count": int(reading.convention_counts.get(b.get("profile_id"), 0)),
        }
        for b in reading.bindings
        if isinstance(b, Mapping)
    ]

    # -- counts / readiness ---------------------------------------------------------------
    states = [c["value_state"] for c in out_candidates]
    counts = {
        "sources": len(sources),
        "unread_files": len(unread),
        "runs": len(runs),
        "run_candidates": sum(1 for r in runs if r["run_candidate"]),
        "runs_sharing_a_legacy_number": sum(1 for r in runs if r["legacy_number_shared"]),
        "samples": len(samples),
        "contributors": len(contributors),
        "candidates": len(out_candidates),
        "candidate_extracted": states.count(STATE_CANDIDATE_EXTRACTED),
        "needs_review": states.count(STATE_NEEDS_REVIEW),
        "conflicting_candidates": states.count(STATE_CONFLICTING),
        "unmapped": states.count(STATE_UNMAPPED),
        "conflicts": len(conflicts),
        "missing_values": len(missing),
        "extended_context": len(extended),
        "data_quality_notes": len(dq_notes),
        "questions": len(questions),
        **processed_output_counts(processed_outputs),
    }
    eligible = sum(1 for c in out_candidates if c["eligibility_for_official_record"]["eligible"])
    readiness = {
        "stage": "extracted" if sources else "unreadable",
        "is_official_record": False,
        "official_record_ready": False,
        "eligible_value_count": eligible,
        "blocking": {
            "conflicts": len(conflicts),
            "needs_review": counts["needs_review"],
            "missing": len(missing),
            "unread_files": len(unread),
        },
        "next_step": (
            "Review the conflicts and the values that need review with the scientist who "
            "ran the beamtime, and look at the unread files. No value here is confirmed, "
            "and none is eligible for an official record until a scientist confirms it."
        ),
    }

    inv = dict(reading.inventory or {})
    source_root = {
        "label": reading.root_label,
        "kind": source_kind,
        "local_only": True,
        "entry_count": int(inv.get("entry_count") or 0),
        "total_bytes": int(inv.get("total_bytes") or 0),
        "refused_count": len(inv.get("refused") or ()),
        "truncated_reason": inv.get("truncated_reason"),
        "duplicate_group_count": int(inv.get("duplicate_group_count") or 0),
    }
    if local_root_hint:
        source_root["local_root_hint"] = local_root_hint

    profiles_used = sorted(
        {(b["profile_id"], b["profile_version"]) for b in naming}, key=lambda t: (t[0], str(t[1]))
    )
    bundle = {
        "format": FORMAT_ID,
        "format_version": FORMAT_VERSION,
        "is_official_record": False,
        "official_record_notice": OFFICIAL_RECORD_NOTICE,
        "bundle_id": bundle_id or new_record_id(),
        "created_utc": created_utc,
        "generator": {
            "tool": "isaac import",
            "tool_version": tool_version,
            "engine": "isaac_api.historical_import.read_archive_at",
            "isaac_commit": isaac_commit,
            "walker_id": reading.walker_id,
            "classifier_ids": sorted(classifiers_seen),
            "readers": [
                {"reader_id": r, "version": _reader_version(r)} for r in sorted(readers_seen)
            ],
            "naming_profiles": [
                {"profile_id": p, "profile_version": v} for p, v in profiles_used
            ],
            "profile_request": profile_request,
        },
        "source_root": source_root,
        "sources": sources,
        "unread_files": unread,
        "experiment": {
            "label": reading.root_label,
            "context_candidate_ids": shared_bundle_ids,
            "element_evidence": [
                {**dict(e), "source_id": sid_of.get(e.get("source_path"))}
                for e in reading.element_evidence
            ],
            "temperature_statements": [
                {**dict(t), "source_id": sid_of.get(t.get("source_path"))}
                for t in reading.temperature_statements
            ],
            "acquisition_system": {
                k: v
                for k, v in dict(reading.acquisition_system).items()
                if k in {"system_id", "display_name", "candidate_channels"}
            },
            "beamtime_contributor_ids": [
                p["contributor_id"] for p in contributors.values() if p["scope"] == "beamtime"
            ],
            "statement": (
                "Experiment-level context the sources state for the whole beamtime. "
                "Context, not run values: nothing here is copied onto a run."
            ),
        },
        "samples": samples,
        "runs": runs,
        "contributors": list(contributors.values()),
        "naming_profiles": naming,
        "candidates": out_candidates,
        "conflicts": conflicts,
        "missing_values": missing,
        "unmapped_statements": unmapped,
        "extended_context": extended + generic_statements,
        "data_quality_notes": list(dq_notes.values()),
        "questions": questions,
        "ai_interpretations": [],
        "scientist_decisions": decisions,
        # Filled by later steps: LOCAL-P (grouping, processing) and the mutation commands.
        "record_groups": [],
        "processing_results": [],
        "exposures": [],
        # 1.2.0: the scientists' own processed outputs — reference results, never runs.
        "processed_outputs": processed_outputs,
        "validation": {
            "bundle_schema": {
                "status": "valid",
                "schema_id": bundle_schema()["$id"],
                "checked_utc": created_utc,
            },
            "official_record_validation": {
                "status": "not_applicable",
                "reason": (
                    "A bundle is not an official record. Official validation runs on an "
                    "exported record (`isaac validate <record> --official`)."
                ),
            },
            "statement": (
                "Checked against bundle-v1 (schema plus bounds, state and reference "
                "consistency) when written. `isaac bundle check <dir>` re-checks it."
            ),
        },
        "readiness": readiness,
        "counts": counts,
        "bounds": {
            "max_runs": MAX_RUNS,
            "max_candidates": MAX_CANDIDATES,
            "max_evidence_per_candidate": MAX_EVIDENCE_PER_CANDIDATE,
            "max_string_chars": MAX_STRING_CHARS,
            "max_bundle_bytes": MAX_BUNDLE_BYTES,
            "strings_truncated": 0,
            "evidence_windows_truncated": evidence_windows_truncated,
            "candidates_truncated_by_engine": bool(reading.candidates_truncated),
            "engine_candidate_total": int(reading.candidate_total),
        },
        "authorities": dict(AUTHORITIES),
    }
    refresh_questions(bundle)
    apply_derivations(bundle)
    counter = [0]
    bundle = _clamp_strings(bundle, counter)
    bundle["bounds"]["strings_truncated"] = counter[0]
    if len(encode(bundle)) > MAX_BUNDLE_BYTES:
        raise BundleBoundsExceeded(
            f"The bundle would exceed {MAX_BUNDLE_BYTES} bytes; nothing was written."
        )
    return bundle


def _run_order(bundle: Mapping) -> dict[str | None, tuple]:
    """Sort key per run id: by record group (when LOCAL-P has grouped), then run order.
    Record-scope (``None``) sorts first."""
    by_key = {r["run_key"]: r["run_id"] for r in bundle["runs"]}
    order: dict[str | None, tuple] = {None: (-1, -1)}
    for gi, g in enumerate(bundle.get("record_groups") or ()):
        for key in g.get("member_run_keys") or ():
            rid = by_key.get(key)
            if rid is not None and rid not in order:
                order[rid] = (gi, len(order))
    base = len(bundle.get("record_groups") or ())
    for i, r in enumerate(bundle["runs"]):
        order.setdefault(r["run_id"], (base, i))
    return order


def _required_for(path: str, required: Sequence[str]) -> str | None:
    for req in required:
        if path == req or path.startswith(req + "."):
            return req
    return None


def refresh_questions(bundle: dict) -> dict:
    """(Re)build ``questions[]``: conflicts, needs-review values with a field, and —
    since 1.1.0 — ``missing_value`` questions ONLY for values the official record
    REQUIRES (:func:`required_record_paths`), ordered by record (record groups when
    present, else runs), record-scope first. Answered targets keep their question; a
    question is about a value, not about whether it has been answered. The ONE exception is the
    beamtime-scope ``confirm_clock_time_zone`` question (1.4.0), which is about a fact no file
    states and is asked only while no ``set_clock_time_zone`` decision exists."""
    _derive_local_clock_starts(bundle)  # so a prompt below quotes what the zone decision gives now
    questions: list[dict] = []
    for conflict in bundle["conflicts"]:
        questions.append(
            {
                "question_id": "",
                "kind": "resolve_conflict",
                "target": {"kind": "conflict", "id": conflict["conflict_id"]},
                "run_id": conflict["run_ids"][0] if conflict["run_ids"] else None,
                "prompt": (
                    f"The sources disagree ({conflict['kind']}"
                    + (f", {conflict['subject']}" if conflict["subject"] else "")
                    + "). Which reading is right? Nothing has been chosen for you."
                ),
                "options": [r["value"] for r in conflict["readings"]],
            }
        )
    reconfirm = {x["candidate_id"]: x["reason"] for x in local_clock_reconfirm(bundle)}
    for cand in bundle["candidates"]:
        if cand["extracted_state"] == STATE_NEEDS_REVIEW and cand["target_field_path"] and is_local_clock_start(cand):
            # A LOCAL clock literal is never offered as an answer for a *_utc field: before a zone the
            # question has no option and says it waits on the zone; after, its one option is the UTC value.
            clock = cand.get("local_clock") or {}
            if cand["candidate_id"] in reconfirm:
                prompt = f"{cand['target_field_path']}: {reconfirm[cand['candidate_id']]}"
            elif clock.get("status") == LOCAL_CLOCK_AWAITING:
                prompt = (f"{cand['target_field_path']}: waits on the instrument clock's time zone (no file states it); "
                          "nothing can be confirmed until it is stated (see the confirm_clock_time_zone question).")
            else:
                prompt = f"{cand['target_field_path']}: {clock.get('explanation') or cand['state_basis']['not_proposable_summary']}"
            questions.append(
                {
                    "question_id": "",
                    "kind": "confirm_value",
                    "target": {"kind": "candidate", "id": cand["candidate_id"]},
                    "run_id": cand["run_id"],
                    "prompt": prompt,
                    "options": [cand["value"]] if cand["value"] is not None else [],
                }
            )
            continue
        if cand["extracted_state"] == STATE_NEEDS_REVIEW and cand["target_field_path"]:
            questions.append(
                {
                    "question_id": "",
                    "kind": "confirm_value",
                    "target": {"kind": "candidate", "id": cand["candidate_id"]},
                    "run_id": cand["run_id"],
                    "prompt": (
                        f"{cand['target_field_path']}: "
                        + (cand["state_basis"]["not_proposable_summary"] or "needs your review.")
                    ),
                    "options": list(cand["observed_literals"]),
                }
            )
    zone_question = clock_zone_question(bundle)
    if zone_question is not None:
        questions.append(
            {
                "question_id": "",
                "kind": "confirm_clock_time_zone",
                "target": {"kind": "experiment", "id": "experiment"},
                "run_id": None,
                "prompt": zone_question["text"],
                "options": [],  # NO suggested value: no file states the zone
            }
        )
    control_mode: dict[str | None, str] = {}
    for cand in bundle["candidates"]:
        if cand["target_field_path"] == "context.electrochemistry.control_mode" and isinstance(cand["value"], str):
            control_mode[cand["run_id"]] = cand["value"]
    reaction_runs = {
        cand["run_id"] for cand in bundle["candidates"]
        if cand["target_field_path"] in ("context.electrochemistry.reaction", "context.reaction.name")
    }
    order = _run_order(bundle)
    missing_qs = []
    for m in bundle["missing_values"]:
        required = required_record_paths(control_mode=control_mode.get(m["run_id"])) + PORTAL_REQUIRED_PATHS
        if m["run_id"] in reaction_runs:
            required = required + REACTION_REQUIRED_PATHS
        req = _required_for(m["target_field_path"], required)
        if req is None:
            continue
        missing_qs.append(
            (
                order.get(m["run_id"], (10**9, 10**9)),
                m["value_id"],
                {
                    "question_id": "",
                    "kind": "missing_value",
                    "target": {"kind": "missing_value", "id": m["value_id"]},
                    "run_id": m["run_id"],
                    "prompt": (
                        f"{m['target_field_path']} is required by the official record "
                        f"({req}) and no source states it. What is it? Leave it missing if "
                        "nobody knows; nothing is defaulted."
                    ),
                    "options": [],
                    "required_by": req,
                },
            )
        )
    questions.extend(q for _, _, q in sorted(missing_qs, key=lambda t: (t[0], t[1])))
    for i, q in enumerate(questions, 1):
        q["question_id"] = f"q-{i:04d}"
    bundle["questions"] = questions
    bundle.setdefault("counts", {})["questions"] = len(questions)
    return bundle


def _profile_version(profile_id: str) -> str | None:
    from ..bl15 import profiles as prof

    registered = prof.profile_for(profile_id)
    return registered.profile_version if registered is not None else None


def sanitized_refusal(refusal: Mapping) -> dict:
    """ONE walk refusal with an absolute or escaping member name WITHHELD — the name and
    the walker's detail (which quotes it) both. Used for bundle.json AND
    reading.full.json, so neither file carries what the other withholds (review L1)."""
    raw_path = refusal.get("archive_path")
    safe = _safe_relative(raw_path)
    detail = str(refusal.get("detail") or refusal.get("reason") or "refused by the walk")
    if raw_path and safe is None:
        detail = (
            f"Refused by the walk ({refusal.get('reason')}): the member's name is "
            "absolute or escapes the archive root, so it is withheld. Nothing was read "
            "from it and nothing was extracted."
        )
    return {"archive_path": safe, "reason": str(refusal.get("reason") or "refused"), "detail": detail}


def full_reading(reading, candidates) -> dict:
    """``reading.full.json``: the raw engine state, under the SAME minimisation and bounds
    as the bundle — refusals sanitised, strings clamped visibly, total size capped."""
    state = reading.to_state()
    inv = dict(state.get("inventory") or {})
    inv["refused"] = [sanitized_refusal(r) for r in inv.get("refused") or ()]
    state["inventory"] = inv
    full = {
        "note": (
            "Raw engine state (ArchiveReading.to_state() and every candidate's to_state()), "
            "kept for lookup. NOT the bundle contract; bundle.json is. It holds parser "
            "values: reading it directly is an exposure the CLI cannot record."
        ),
        "reading": state,
        "candidates": [c.to_state() for c in candidates],
    }
    counter = [0]
    full = _clamp_strings(full, counter)
    full["strings_truncated"] = counter[0]
    if len(encode(full)) > MAX_BUNDLE_BYTES:
        raise BundleBoundsExceeded(f"reading.full.json would exceed {MAX_BUNDLE_BYTES} bytes; nothing was written.")
    return full


def _plain_reason(candidate) -> str | None:
    from .. import historical_import as hist

    return hist.plain_reason_of(candidate)


#: The engine's "this build cannot write it" is about the WEBSITE's write routes. For a field
#: only the local path answers (UPSTREAM_TARGET_FIELDS, LOCAL_ANSWER_FIELDS) it is not true here.
LOCAL_WRITE_PATH_REASON = (
    "The website cannot write this field yet, but this local import can: confirm or correct it, "
    "and a confirmed value goes toward the record."
)


def _local_plain_reason(candidate) -> str | None:
    from .. import historical_import as hist

    reason = _plain_reason(candidate)
    if reason == hist.PLAIN_REASON_NO_WRITE_PATH and (
        candidate.target_field_path in UPSTREAM_TARGET_FIELDS or candidate.target_field_path in LOCAL_ANSWER_FIELDS
    ):
        return LOCAL_WRITE_PATH_REASON
    return reason


def _missing(n, run_id, path, scope, reason, beamtime_targets, writable) -> dict:
    return {
        "value_id": f"miss-{n + 1:04d}",
        "run_id": run_id,
        "target_field_path": path,
        "target_write_scope": scope,
        "value": None,
        "extracted_state": STATE_MISSING,
        "value_state": STATE_MISSING,
        "reason": reason,
        "beamtime_context_candidate_ids": list(beamtime_targets.get(path, [])),
        "eligibility_for_official_record": eligibility_for_official_record(
            STATE_MISSING, target_field_path=path, value=None, writable_paths=writable
        ),
    }


def _normalization_of(item) -> list[dict]:
    if item is None or not getattr(item, "normalization_rule", None):
        return []
    normalized = item.normalized_value
    if normalized is None or normalized == item.raw_literal:
        return []
    rule_id = _rule_id(item.normalization_rule) or "unnamed_stored_rule"
    return [
        {
            "step": "normalize",
            "rule_id": rule_id,
            "from": item.raw_literal,
            "to": normalized,
            "unit": getattr(item, "unit", None),
        }
    ]


def _witness_pairs(reading: Mapping, archive_paths: Sequence[str]) -> list[tuple[str | None, str, str]]:
    """``[(archive_path or None, locator-within, full locator)]`` for ONE disagreement reading."""
    locators = [loc for loc in reading.get("locators") or () if isinstance(loc, str)]
    source_ids = [s for s in reading.get("source_ids") or () if isinstance(s, str)]
    out = []
    for i, loc in enumerate(locators):
        split = _split_locator(loc, archive_paths)
        if split is not None:
            out.append((split[0], split[1], loc))
            continue
        if len(source_ids) == 1:
            path = source_ids[0]
        elif len(source_ids) == len(locators):
            path = source_ids[i]
        else:
            path = None
        full = f"{path} · {loc}" if path else loc
        out.append((path, loc, full))
    if not out:
        for path in source_ids:
            out.append((path, "", path))
    return out


def _evidence_for(c, bundle_cid, key, archive_paths, sid_of, ev_index) -> tuple[list[dict], int]:
    """EVERY witness the engine kept for a candidate — never flattened to one origin."""
    full: list[dict] = []
    derived_by_rule = bool(c.resolved_by_rule) and c.unresolved_reason is None and c.proposed_value is not None

    def entry(path, within, full_loc, literal, relation, reading_index):
        item = ev_index.get((key, full_loc))
        method = "stored_rule" if derived_by_rule else "deterministic_parser"
        method_id = c.resolved_by_rule if derived_by_rule else (item.parser_id if item is not None else None)
        # A "path" that is not a manifest file (e.g. "(the macros in this import)", or a
        # measurement stem) is a DESCRIPTION, typed as such, never a relative_path.
        is_file = bool(path) and path in sid_of
        return {
            "evidence_id": f"{bundle_cid}.e{len(full) + 1:03d}",
            "source_id": sid_of.get(path) if is_file else None,
            "relative_path": _safe_relative(path) if is_file else None,
            "locator_kind": "source_file" if is_file else ("described" if path else "unlocated"),
            "locator": (within or full_loc) if is_file else (full_loc or within),
            "statement_key": key,
            "literal_value": literal,
            "method": method,
            "method_id": method_id,
            "relation": relation,
            "reading_index": reading_index,
            "normalization": _normalization_of(item),
        }

    if c.disagreement:
        for ri, reading in enumerate(c.disagreement):
            value = reading.get("value")
            used = {
                row.get("value")
                for row in (c.standing_resolution or {}).get("reading_used") or ()
                if isinstance(row, Mapping)
            }
            relation = (
                "supports"
                if (c.proposed_value is not None and value == c.proposed_value) or value in used
                else "contradicts"
            )
            for path, within, full_loc in _witness_pairs(reading, archive_paths):
                full.append(entry(path, within, full_loc, value, relation, ri))
        total = len(full)
    else:
        for st in c.supporting_statements:
            loc = str(st.get("locator") or "")
            split = _split_locator(loc, archive_paths)
            path, within = (split if split is not None else (None, loc))
            full.append(entry(path, within, loc, st.get("value"), "supports", None))
        total = max(len(full), c.supporting_statement_total or 0)
    # THE ENGINE'S OWN DERIVATION, RECORDED (real-data finding): a value a NAMED engine rule
    # produced from the statements (a lexicon member picked out of a structured reading, a
    # stored rule such as dry sample -> ex_situ) is not a literal and not the reader's
    # normalisation. It is recorded as a `derive` step naming that rule, so the validator
    # can VERIFY it (rule id == the candidate's rule; `from` == a witnessed reading) instead
    # of accepting an unexplained value. A value with no named rule gets no step, and the
    # validator still refuses it.
    if c.proposed_value is not None and not derived_by_rule:
        probe = {"rule": c.rule, "evidence": full}
        key_value = json.dumps(c.proposed_value, sort_keys=True)
        rid = _rule_id(c.rule)
        if key_value not in witnessed_values(probe) and rid:
            for e in full:
                if e["relation"] != "supports":
                    continue
                source = e["normalization"][-1]["to"] if e["normalization"] else e["literal_value"]
                e["normalization"].append({"step": "derive", "rule_id": rid, "from": source, "to": c.proposed_value, "unit": None})
    window = full[:MAX_EVIDENCE_PER_CANDIDATE]
    return window, max(total, len(full))


def witnessed_values(candidate: Mapping) -> set[str]:
    """Every value a candidate's evidence VOUCHES for (JSON-canonical): each witness's
    literal, each recorded reader normalisation's output, and each ``derive`` step's output
    — but a ``derive`` step only when it names the candidate's OWN rule and starts from a
    reading a witness actually states (so a hand-added step cannot launder a value)."""
    base: set[str] = set()
    for e in candidate["evidence"]:
        if e["method"] == "ai_interpretation":
            continue
        base.add(json.dumps(e["literal_value"], sort_keys=True))
        for n in e["normalization"]:
            if n.get("step") != "derive":
                base.add(json.dumps(n["to"], sort_keys=True))
    out = set(base)
    own = _rule_id(candidate.get("rule"))
    for e in candidate["evidence"]:
        for n in e["normalization"]:
            if n.get("step") == "derive" and own and n.get("rule_id") == own and json.dumps(n["from"], sort_keys=True) in base:
                out.add(json.dumps(n["to"], sort_keys=True))
    return out


def _conflict_from_candidate(conflict_id, c, bundle_cid, run_id, engine_conflict, archive_paths, sid_of) -> dict:
    roles: dict[tuple[str, str], str] = {}
    if isinstance(engine_conflict, Mapping):
        for r in engine_conflict.get("readings") or ():
            roles[(str(r.get("source_path")), str(r.get("locator")))] = r.get("source_role")
    readings = []
    for ri, reading in enumerate(c.disagreement):
        witnesses = []
        for path, within, _full in _witness_pairs(reading, archive_paths):
            witnesses.append(
                {
                    "source_id": sid_of.get(path) if path else None,
                    "relative_path": _safe_relative(path),
                    "locator": within or _full,
                    "source_role": roles.get((str(path), str(within))),
                }
            )
        if not witnesses:
            witnesses.append(
                {"source_id": None, "relative_path": None, "locator": "unlocated", "source_role": None}
            )
        readings.append({"reading_index": ri, "value": reading.get("value"), "witnesses": witnesses})
    return {
        "conflict_id": conflict_id,
        "engine_conflict_id": engine_conflict.get("conflict_id")
        if isinstance(engine_conflict, Mapping)
        else c.candidate_id,
        "kind": str(engine_conflict.get("kind"))
        if isinstance(engine_conflict, Mapping)
        else "field_disagreement",
        "subject": engine_conflict.get("subject")
        if isinstance(engine_conflict, Mapping)
        else c.target_field_path or c.candidate_id.split("::", 1)[-1],
        "candidate_id": bundle_cid,
        "run_ids": [run_id] if run_id else [],
        "readings": readings,
        "explanation": engine_conflict.get("explanation")
        if isinstance(engine_conflict, Mapping)
        else c.rule,
        "recommendation": engine_conflict.get("recommendation")
        if isinstance(engine_conflict, Mapping)
        else None,
        "resolution": (
            {
                "resolved_by_rule": c.resolved_by_rule,
                "standing_resolution": dict(c.standing_resolution) if c.standing_resolution else None,
                "authority": "stored_rule_not_a_scientist_decision_about_these_files",
            }
            if c.resolved_by_rule
            else None
        ),
        "value_state": STATE_NEEDS_REVIEW if c.resolved_by_rule else STATE_CONFLICTING,
    }


# --- loader + validator ---------------------------------------------------------------


class BundleInvalid(ValueError):
    """A bundle file that cannot be read or does not meet the v1 contract."""

    def __init__(self, errors: Sequence[str]):
        super().__init__("; ".join(errors[:5]))
        self.errors = list(errors)


def bundle_path(location: Path) -> Path:
    location = Path(location)
    return location / BUNDLE_FILE if location.is_dir() else location


def load_bundle(location: Path) -> dict:
    """Read ``bundle.json`` (or the dir holding it). Refuses oversize BEFORE parsing."""
    path = bundle_path(location)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise BundleInvalid([f"cannot read {path.name}: {type(exc).__name__}"]) from exc
    if size > MAX_BUNDLE_BYTES:
        raise BundleInvalid([f"{path.name} is {size} bytes, over the bound of {MAX_BUNDLE_BYTES}"])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BundleInvalid([f"{path.name} is not readable JSON: {exc}"]) from exc
    if not isinstance(data, dict):
        raise BundleInvalid([f"{path.name} does not hold a JSON object"])
    return data


def _added_since(version: str | None) -> frozenset:
    """Writable paths added after ``version`` (all of them for an unknown version)."""
    at = _VERSION_ORDER.index(version) if version in _VERSION_ORDER else -1
    out: set = set()
    for v, paths in WRITABLE_ADDED_IN.items():
        if _VERSION_ORDER.index(v) > at:
            out |= paths
    return frozenset(out)


def stale_eligibility(bundle: Mapping) -> list[dict]:
    """Values whose STORED eligibility differs from this build's derivation ONLY because this
    build can write a field the storing build could not (:data:`WRITABLE_ADDED_IN`). Each with
    its id, path, state, before/now and why. Empty for a bundle of this format version."""
    added = _added_since(bundle.get("format_version"))
    if not added:
        return []
    expected = apply_derivations(json.loads(json.dumps(bundle)))
    decision_of = _decisions_by_target(bundle.get("scientist_decisions") or ())
    out = []
    for kind, section, key in (("candidate", "candidates", "candidate_id"), ("missing_value", "missing_values", "value_id")):
        for obj, e in zip(bundle[section], expected[section]):
            path = obj.get("target_field_path")
            before = bool((obj.get("eligibility_for_official_record") or {}).get("eligible"))
            now = bool(e["eligibility_for_official_record"]["eligible"])
            if path in added and before != now:
                d = candidate_decision(bundle, obj, decision_of) if kind == "candidate" else decision_of.get((kind, obj[key]))
                reason = f"this build can now write {path}"
                if e["value_state"] == STATE_SCIENTIST_CONFIRMED:
                    reason += ("; a scientist confirmed it while the storing build could not write the field: "
                               + ("eligible now" if now else "not eligible now"))
                    if now and path in COMPOSES_ONLY_WITH:
                        reason += f"; composes only beside a confirmed {COMPOSES_ONLY_WITH[path].rsplit('.', 1)[-1]}"
                out.append({"kind": kind, "id": obj[key], "target_field_path": path, "run_id": obj.get("run_id"),
                            "value_state": e["value_state"], "eligible_before": before, "eligible_now": now,
                            "decision_id": (d or {}).get("decision_id"), "reason": reason[:600]})
    return out


def import_rules_missing(bundle: Mapping) -> list[tuple[str, str]]:
    """``[(run source_type, rule id)]`` for import rules a LATER format added
    (:data:`IMPORT_RULES_ADDED_IN`) that this bundle has runs for and no candidate of: an older
    build imported it, and only a re-import applies the rule. Empty for a bundle of this version."""
    version = bundle.get("format_version")
    at = _VERSION_ORDER.index(version) if version in _VERSION_ORDER else -1
    have = {_rule_id(c.get("rule")) for c in bundle.get("candidates") or ()}
    kinds = {r.get("source_type") for r in bundle.get("runs") or ()}
    out = []
    for v, rules in IMPORT_RULES_ADDED_IN.items():
        if _VERSION_ORDER.index(v) > at:
            out += [(st, rid) for st, rid in rules if st in kinds and rid not in have]
    return out


def upgrade_statement(from_version: str | None, newly_writable: Iterable[str],
                      rules_missing: Iterable[tuple[str, str]] = ()) -> str:
    """THE ONE SENTENCE every surface prints about an upgrade of an older bundle."""
    if list(newly_writable):
        text = (f"upgraded from {from_version}; fields this build can newly write have no answer slots on runs that "
                "lacked a parsed value — re-import to get them")
    else:
        text = f"upgraded from {from_version}"
    for source_type, rule_id in rules_missing:
        text += (f"; its {source_type.split(':', 1)[-1]} runs were imported before rule {rule_id} existed and carry "
                 "none of its candidates — re-import to get them")
    return text


def record_format_upgrade(bundle: dict, *, from_version: str | None, to_version: str, decisions_before: int) -> dict:
    """Append ONE ``format_upgrades`` entry: an older bundle first written (re-derived) by this
    build. ``decisions_before`` is how many scientist decisions it held then, so a composition can
    tell an answer given under the old build's wording from one given after."""
    from datetime import datetime, timezone

    newly = sorted(_added_since(from_version))
    entry = {
        "from_format_version": str(from_version),
        "to_format_version": to_version,
        "derived_by_format_version": FORMAT_VERSION,
        "upgraded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decisions_before": int(decisions_before),
        "newly_writable_paths": newly,
        "statement": upgrade_statement(from_version, newly, import_rules_missing(bundle)),
    }
    bundle.setdefault("format_upgrades", []).append(entry)
    return entry


def needs_format_upgrade(bundle: Mapping) -> bool:
    """True when this build has not yet re-derived an older bundle (and logged it)."""
    if not _added_since(bundle.get("format_version")) and not import_rules_missing(bundle):
        return False
    return not any(u.get("derived_by_format_version") == FORMAT_VERSION for u in bundle.get("format_upgrades") or ())


def refresh_local_write_summaries(bundle: dict) -> int:
    """A candidate whose short reason is the engine's "this build cannot write it yet" while this
    local build DOES write its path gets :data:`LOCAL_WRITE_PATH_REASON` (the engine's full text
    stays in ``not_proposable_reason``). The import does this; an older bundle gets it on save."""
    from .. import historical_import as hist

    local = set(UPSTREAM_TARGET_FIELDS) | set(LOCAL_ANSWER_FIELDS)
    n = 0
    for c in bundle.get("candidates") or ():
        sb = c.get("state_basis") or {}
        if c.get("target_field_path") in local and sb.get("not_proposable_summary") == hist.PLAIN_REASON_NO_WRITE_PATH:
            sb["not_proposable_summary"] = LOCAL_WRITE_PATH_REASON
            n += 1
    return n


def upgraded_before(bundle: Mapping, path: str | None, decision: Mapping | None) -> Mapping | None:
    """The ``format_upgrades`` entry under which ``decision`` (governing a value at ``path``) was
    made BEFORE this build re-derived the bundle, when ``path`` is one the old build could not
    write; else ``None``. Decision ids are sequential (``d-<n>``)."""
    if not path or not decision:
        return None
    try:
        n = int(str(decision.get("decision_id")).rsplit("-", 1)[-1])
    except ValueError:
        return None
    for u in bundle.get("format_upgrades") or ():
        if path in (u.get("newly_writable_paths") or ()) and n <= int(u.get("decisions_before") or 0):
            return u
    return None


def validate_allowing_stale(bundle: Any, *, max_errors: int = 50) -> tuple[list[str], list[dict]]:
    """``(errors, stale)``: :func:`validate_bundle` with every STALE eligibility (and the count
    it moves) taken as this build re-derives it. ``errors`` empty and ``stale`` non-empty means
    the bundle is valid except that an older build stored it: any mutation re-derives it."""
    errors = validate_bundle(bundle, max_errors=max_errors)
    if not errors or not isinstance(bundle, dict):
        return errors, []
    try:
        stale = stale_eligibility(bundle)
    except (KeyError, TypeError, ValueError):
        return errors, []
    if not stale:
        return errors, []
    fixed = json.loads(json.dumps(bundle))
    expected = apply_derivations(json.loads(json.dumps(bundle)))
    ids = {(s["kind"], s["id"]) for s in stale}
    for kind, section, key in (("candidate", "candidates", "candidate_id"), ("missing_value", "missing_values", "value_id")):
        for obj, e in zip(fixed[section], expected[section]):
            if (kind, obj[key]) in ids:
                obj["eligibility_for_official_record"] = e["eligibility_for_official_record"]
    fixed["readiness"]["eligible_value_count"] = expected["readiness"]["eligible_value_count"]
    return validate_bundle(fixed, max_errors=max_errors), stale


def record_rederivation(bundle: dict, stale: Sequence[Mapping], *, to_version: str) -> None:
    """Append ``stale`` to ``bundle['eligibility_rederived']`` (the log a composition reads)."""
    if not stale:
        return
    from datetime import datetime, timezone

    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log = bundle.setdefault("eligibility_rederived", [])
    for s in stale:
        log.append({"kind": s["kind"], "id": s["id"], "target_field_path": s["target_field_path"],
                    "from_format_version": str(bundle.get("format_version")), "to_format_version": to_version,
                    "rederived_utc": at, "value_state": s["value_state"], "eligible_before": s["eligible_before"],
                    "eligible_now": s["eligible_now"], "decision_id": s.get("decision_id"), "reason": s["reason"]})


def validate_bundle(bundle: Any, *, max_errors: int = 50) -> list[str]:
    """Every way ``bundle`` breaks the v1 contract. Empty means valid."""
    from jsonschema import Draft202012Validator

    errors: list[str] = []
    validator = Draft202012Validator(bundle_schema())
    for err in sorted(validator.iter_errors(bundle), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"schema: {where}: {err.message[:300]}")
        if len(errors) >= max_errors:
            return errors
    if not isinstance(bundle, dict) or errors:
        return errors

    size = len(encode(bundle))
    if size > MAX_BUNDLE_BYTES:
        errors.append(f"bounds: bundle is {size} bytes, over {MAX_BUNDLE_BYTES}")
    for s in _iter_strings(bundle):
        if len(s) > MAX_STRING_CHARS:
            errors.append(f"bounds: a string of {len(s)} characters exceeds {MAX_STRING_CHARS}")
            break
    for c in bundle["candidates"]:
        if len(c["evidence"]) > MAX_EVIDENCE_PER_CANDIDATE:
            errors.append(f"bounds: {c['candidate_id']} carries more than {MAX_EVIDENCE_PER_CANDIDATE} evidence entries")
        if c["evidence_total"] < len(c["evidence"]):
            errors.append(f"bounds: {c['candidate_id']} evidence_total is below the evidence it carries")
        if c["evidence_truncated"] != (c["evidence_total"] > len(c["evidence"])):
            errors.append(f"bounds: {c['candidate_id']} evidence_truncated disagrees with evidence_total")

    # identifiers + references
    def _unique(rows, key, label):
        seen = set()
        for row in rows:
            if row[key] in seen:
                errors.append(f"reference: duplicate {label} {row[key]}")
            seen.add(row[key])
        return seen

    source_ids = _unique(bundle["sources"], "source_id", "source_id")
    run_ids = _unique(bundle["runs"], "run_id", "run_id")
    cand_ids = _unique(bundle["candidates"], "candidate_id", "candidate_id")
    conflict_ids = _unique(bundle["conflicts"], "conflict_id", "conflict_id")
    missing_ids = _unique(bundle["missing_values"], "value_id", "value_id")
    _unique(bundle["questions"], "question_id", "question_id")
    for s in bundle["sources"]:
        if _safe_relative(s["relative_path"]) is None:
            errors.append(f"paths: {s['source_id']} relative_path is absolute or escapes the root")
    for u in bundle["unread_files"]:
        if u["relative_path"] is not None and _safe_relative(u["relative_path"]) is None:
            errors.append("paths: an unread_files entry has an absolute or escaping path")
    held_ids = {g.get("group_id") for g in bundle.get("record_groups") or ()} | {
        g.get("group_id") for g in bundle.get("superseded_record_groups") or ()
    }
    not_applicable_ids = set()
    for r in bundle.get("processing_results") or ():
        if r.get("group_id") not in held_ids:
            errors.append(f"reference: processing result {processing_id(r)} names group {r.get('group_id')}, in neither record_groups nor superseded_record_groups")
        if processing_not_applicable(r):
            # RECOMPUTED, not trusted: a not-applicable result is no curve and carries no verdict
            pid = processing_id(r)
            not_applicable_ids.add(pid)
            if (r.get("qc") or {}).get("verdict") is not None:
                errors.append(f"consistency: processing result {pid} is not_applicable but carries a QC verdict")
            if (r.get("outputs") or {}).get("files"):
                errors.append(f"consistency: processing result {pid} is not_applicable but lists output files")
            if r.get("preferred_for_record"):
                errors.append(f"consistency: processing result {pid} is not_applicable but is preferred_for_record")
            code = r["applicability"].get("reason_code")
            if (code == NA_NO_SCANS) != (not r.get("inputs")):
                errors.append(f"consistency: processing result {pid} reason {code} disagrees with its {len(r.get('inputs') or ())} listed inputs")
            if code == NA_NO_XAS_CHANNEL:
                # the result's OWN record must show no channel formed from a scan that was read
                cc = r.get("channel_choice")
                read = [i for i in r.get("inputs") or () if not i.get("skip_reason")]
                if not isinstance(cc, Mapping) or (cc.get("energy") is not None and cc.get("mode") is not None):
                    errors.append(f"consistency: processing result {pid} says no_xas_channel but its channel_choice formed one (or is absent)")
                if not read:
                    errors.append(f"consistency: processing result {pid} says no_xas_channel but no scan was read")
                if any(i.get("used") for i in r.get("inputs") or ()):
                    errors.append(f"consistency: processing result {pid} says no_xas_channel but marks a scan used")
        for f in (r.get("outputs") or {}).get("files") or ():
            if _safe_relative(f.get("relative_path")) is None:
                errors.append(f"paths: processing result {processing_id(r)} names an output outside the bundle")
    for d in bundle["scientist_decisions"]:
        if d["target"]["kind"] == "processing_result" and d["target"]["id"] in not_applicable_ids:
            errors.append(
                f"decision: {d['decision_id']} decides processing result {d['target']['id']}, which is not_applicable "
                f"({NO_PROTOCOL_COVERS}); there is nothing to {d.get('decision')}"
            )
    for c in bundle["candidates"]:
        if c["run_id"] is not None and c["run_id"] not in run_ids:
            errors.append(f"reference: {c['candidate_id']} names unknown run {c['run_id']}")
        for e in c["evidence"]:
            if e["source_id"] is not None and e["source_id"] not in source_ids:
                errors.append(f"reference: {e['evidence_id']} names unknown source {e['source_id']}")
            if e["relative_path"] is not None and _safe_relative(e["relative_path"]) is None:
                errors.append(f"paths: {e['evidence_id']} path is absolute or escapes the root")
    for r in bundle["runs"]:
        for cid in r["candidate_ids"]:
            if cid not in cand_ids:
                errors.append(f"reference: {r['run_id']} names unknown candidate {cid}")
        for rid in r["shares_legacy_number_with"]:
            if rid not in run_ids:
                errors.append(f"reference: {r['run_id']} shares a legacy number with unknown {rid}")
        if bool(r["shares_legacy_number_with"]) != r["legacy_number_shared"]:
            errors.append(f"consistency: {r['run_id']} legacy_number_shared disagrees with shares_legacy_number_with")
    for d in bundle["scientist_decisions"]:
        problem = decider_name_problem((d.get("decided_by") or {}).get("name"))
        if problem:
            errors.append(f"decision: {d['decision_id']} {problem}")
        if d.get("decision") in ("approve_calibration", "set_absorber") and not (
            is_absorber_element(d.get("element")) and is_absorber_edge(d.get("edge"))
        ):
            errors.append(f"decision: {d['decision_id']} {d['decision']} needs an element and an edge (K, L1-L3, M1-M5)")
        if d.get("decision") == CLOCK_ZONE_DECISION:
            problem = clock_zone_problem(d.get("value"))
            if problem is not None:
                errors.append(f"decision: {d['decision_id']} {problem}")
    for c in bundle["candidates"]:
        if is_local_clock_start(c):
            # THE WITNESSES ARE RE-READ FROM THEIR LITERALS (ssrl_xdc_scan_start_v1), never trusted
            errors.extend(f"provenance: {p}" for p in local_clock_witness_problems(c))
    for i in bundle["ai_interpretations"]:
        half = ABSORBER_READING_FIELDS.get(i.get("field_path"))
        if half is None:
            continue
        if i["target"]["kind"] != "record_group":
            errors.append(f"interpretation: {i['interpretation_id']} reads {i['field_path']} but targets a {i['target']['kind']}, not a record group")
        if not (is_absorber_element if half == "element" else is_absorber_edge)(i.get("proposed_value")):
            errors.append(f"interpretation: {i['interpretation_id']} {i['field_path']} {i.get('proposed_value')!r} is not an absorber {half}")
    groups_by_id = {g["group_id"]: g for g in [*(bundle.get("record_groups") or ()), *(bundle.get("superseded_record_groups") or ())]}
    key_of_run = {r["run_id"]: r["run_key"] for r in bundle["runs"]}
    for i in bundle["ai_interpretations"]:
        if i.get("run_ids") is None:
            continue
        if i["target"]["kind"] != "record_group" or i.get("field_path") not in ABSORBER_READING_FIELDS:
            errors.append(f"interpretation: {i['interpretation_id']} names run_ids, which only a record-group absorber reading carries")
            continue
        members = set((groups_by_id.get(i["target"]["id"]) or {}).get("member_run_keys") or ())
        outside = [x for x in i["run_ids"] if key_of_run.get(x) not in members]
        if outside:
            errors.append(f"interpretation: {i['interpretation_id']} names run(s) {outside[:3]} that are not in group {i['target']['id']}")
    ids_of = {"candidate": {c["candidate_id"] for c in bundle["candidates"]},
              "missing_value": {m["value_id"] for m in bundle["missing_values"]}}
    decision_ids = {d["decision_id"] for d in bundle["scientist_decisions"]}
    for r in bundle.get("eligibility_rederived") or ():
        if r["id"] not in ids_of[r["kind"]]:
            errors.append(f"reference: eligibility_rederived names unknown {r['kind']} {r['id']}")
        if r.get("decision_id") is not None and r["decision_id"] not in decision_ids:
            errors.append(f"reference: eligibility_rederived names unknown decision {r['decision_id']}")
    for u in bundle.get("format_upgrades") or ():
        if u["decisions_before"] > len(bundle["scientist_decisions"]):
            errors.append("consistency: a format_upgrades entry counts more decisions than the bundle holds")
    for g in bundle.get("record_groups") or ():
        if g.get("status") == "proposed" and g.get("condition_violations"):
            errors.append(f"consistency: proposed record group {g['group_id']} carries condition violations")
    run_keys = {r["run_key"] for r in bundle["runs"]}
    group_ids = _unique(bundle.get("record_groups") or [], "group_id", "group_id")
    targets = {
        "candidate": cand_ids,
        "conflict": conflict_ids,
        "missing_value": missing_ids,
        "source": source_ids,
        "run": run_ids,
        "record_group": group_ids | {g["group_id"] for g in bundle.get("superseded_record_groups") or ()},
        "processing_result": {processing_id(r) for r in bundle.get("processing_results") or ()},
        "experiment": {"experiment"},
    }
    for entry in [
        *bundle["scientist_decisions"],
        *bundle["ai_interpretations"],
        *bundle["questions"],
        *(bundle.get("exposures") or ()),
    ]:
        t = entry["target"]
        if t["id"] not in targets.get(t["kind"], set()):
            errors.append(f"reference: a {t['kind']} target {t['id']} does not exist")

    # PROCESSED OUTPUTS (1.2.0): references, and the one invariant that matters — a file
    # that is a processed output is never also a run's scan (so never a record group's).
    po_ids = _unique(bundle.get("processed_outputs") or [], "processed_output_id", "processed_output_id")
    run_scan_paths = {s.get("relative_path") for r in bundle["runs"] for s in r.get("scans") or ()}
    runs_by_id_v = {r["run_id"]: r for r in bundle["runs"]}
    for po in bundle.get("processed_outputs") or ():
        pid = po["processed_output_id"]
        for f in po["files"]:
            if f["source_id"] is not None and f["source_id"] not in source_ids:
                errors.append(f"reference: processed output {pid} names unknown source {f['source_id']}")
            if _safe_relative(f["relative_path"]) is None:
                errors.append(f"paths: processed output {pid} has an absolute or escaping path")
            if f["relative_path"] in run_scan_paths:
                errors.append(f"consistency: processed output {pid} file {f['relative_path']} is also a run's scan")
        for link in po["proposed_links"]:
            if link["run_id"] not in run_ids or link["run_key"] not in run_keys:
                errors.append(f"reference: processed output {pid} links to unknown run {link['run_id']}")
        if len(po["proposed_links"]) > 1:
            errors.append(f"consistency: processed output {pid} proposes more than one link")
        for link in po["proposed_links"]:
            run = runs_by_id_v.get(link["run_id"])
            if run is not None and (run["run_key"] != link["run_key"] or run.get("stem") != link["run_stem"]):
                errors.append(f"consistency: processed output {pid} link names run {link['run_id']} by another run's key or stem")
    # THE LINK RULE IS RE-RUN, NEVER TRUSTED: a stored link (or its absence) must be exactly
    # what `propose_processed_links` gives over the stored runs (the derived group_id aside).
    if bundle.get("processed_outputs"):
        again = json.loads(json.dumps(bundle["processed_outputs"]))
        propose_processed_links(again, bundle["runs"])

        def _bare(links):
            return [{k: v for k, v in link.items() if k != "group_id"} for link in links]

        for po, e in zip(bundle["processed_outputs"], again):
            if _bare(po["proposed_links"]) != _bare(e["proposed_links"]) or po["link_note"] != e["link_note"]:
                errors.append(f"consistency: processed output {po['processed_output_id']} link is not what {LINK_RULE_ID} gives over the stored runs")
    # A RUN IS IN AT MOST ONE LIVE GROUP (proposed / confirmed / merged); rejected and split
    # groups are history and do not hold their runs.
    live_of: dict[str, list[str]] = {}
    for g in bundle.get("record_groups") or ():
        if g.get("status") in LIVE_GROUP_STATUSES:
            for key in g["member_run_keys"]:
                live_of.setdefault(key, []).append(g["group_id"])
    for key, gids in live_of.items():
        if len(gids) > 1:
            errors.append(f"consistency: run {key} is in more than one live record group ({', '.join(gids[:5])})")
    for e in bundle["extended_context"]:
        if e.get("processed_output_id") is not None:
            if e["processed_output_id"] not in po_ids:
                errors.append(f"reference: extended_context {e['entry_id']} names unknown processed output {e['processed_output_id']}")
            if e.get("run_id") is not None:
                errors.append(f"consistency: extended_context {e['entry_id']} is attributed to a processed output AND a run")

    # THE STATE RULE — recomputed, never trusted. ONE derivation (`apply_derivations`)
    # is used both to write a bundle and to check one.
    for c in bundle["candidates"]:
        if c["extracted_state"] not in PARSER_STATES:
            errors.append(f"state: {c['candidate_id']} extracted_state {c['extracted_state']} is not a parser state")
    for m in bundle["missing_values"]:
        if m["value"] is not None:
            errors.append(f"state: {m['value_id']} carries a value; a missing value's value is always null")
    errors.extend(_provenance_errors(bundle))
    if errors:
        return errors[:max_errors]
    for g in bundle.get("record_groups") or ():
        for key in g["member_run_keys"]:
            if key not in run_keys:
                errors.append(f"reference: record group {g['group_id']} names unknown run_key {key}")
    # MERGE CANDIDATES (review N-2): name stored groups and runs; groups point only at them
    mc_ids = [mc.get("merge_candidate_id") for mc in bundle.get("merge_candidates") or ()]
    for mc in bundle.get("merge_candidates") or ():
        if not set(mc.get("group_ids") or ()) <= group_ids:
            errors.append(f"reference: merge candidate {mc.get('merge_candidate_id')} names a group not in record_groups")
        if not set(mc.get("run_keys") or ()) <= run_keys:
            errors.append(f"reference: merge candidate {mc.get('merge_candidate_id')} names a run not in runs")
    for g in bundle.get("record_groups") or ():
        stale = [x for x in g.get("merge_candidate_ids") or () if x not in mc_ids]
        if stale:
            errors.append(f"reference: record group {g['group_id']} lists merge candidate(s) {', '.join(stale[:3])} that do not exist")
    expected = apply_derivations(json.loads(json.dumps(bundle)))
    for c, e in zip(bundle["candidates"], expected["candidates"]):
        if c["value_state"] != e["value_state"]:
            errors.append(
                f"state: {c['candidate_id']} is {c['value_state']} but its evidence and "
                f"decisions support only {e['value_state']}"
            )
        if c["eligibility_for_official_record"]["eligible"] != e["eligibility_for_official_record"]["eligible"]:
            errors.append(f"eligibility: {c['candidate_id']} eligibility disagrees with its state")
        if is_local_clock_start(c):
            # THE CONVERSION IS RE-RUN, NEVER TRUSTED: value, steps, reasons and block are what the
            # witness and the latest zone decision give.
            for part in ("value", "evidence", "state_basis", "local_clock"):
                if json.dumps(c.get(part), sort_keys=True) != json.dumps(e.get(part), sort_keys=True):
                    errors.append(f"consistency: {c['candidate_id']} {part} is not what {XDC_START_RULE_ID} and the clock's zone decision give")
    for m, e in zip(bundle["missing_values"], expected["missing_values"]):
        if m["value_state"] != e["value_state"]:
            errors.append(f"state: {m['value_id']} is {m['value_state']} but only {e['value_state']} is supported")
        if m["eligibility_for_official_record"]["eligible"] != e["eligibility_for_official_record"]["eligible"]:
            errors.append(f"eligibility: {m['value_id']} eligibility disagrees with its state")
    for c, e in zip(bundle["conflicts"], expected["conflicts"]):
        if c["value_state"] != e["value_state"]:
            errors.append(f"state: {c['conflict_id']} is {c['value_state']} but only {e['value_state']} is supported")
    for g, e in zip(bundle.get("record_groups") or (), expected.get("record_groups") or ()):
        if g["status"] != e["status"]:
            errors.append(f"state: record group {g['group_id']} is {g['status']} but only {e['status']} is supported")
    for po, e in zip(bundle.get("processed_outputs") or (), expected.get("processed_outputs") or ()):
        if [l["group_id"] for l in po["proposed_links"]] != [l["group_id"] for l in e["proposed_links"]]:
            errors.append(f"consistency: processed output {po['processed_output_id']} link group disagrees with record_groups")
    for r, e in zip(bundle.get("processing_results") or (), expected.get("processing_results") or ()):
        if r["state"] != e["state"]:
            errors.append(f"state: processing result for {r['group_id']} is {r['state']} but only {e['state']} is supported")
    if bundle["readiness"]["eligible_value_count"] != expected["readiness"]["eligible_value_count"]:
        errors.append("consistency: readiness.eligible_value_count disagrees with the candidates")
    for key, want in expected["counts"].items():
        if bundle["counts"].get(key) != want:
            errors.append(f"consistency: counts.{key} is {bundle['counts'].get(key)} but the bundle holds {want}")
    if bundle["readiness"]["blocking"] != expected["readiness"]["blocking"]:
        errors.append("consistency: readiness.blocking disagrees with the bundle's own sections")
    return errors[:max_errors]


MAX_DECIDER_NAME_CHARS = 200


def decider_name_problem(name: object) -> str | None:
    """Why ``name`` cannot stand as the person who decided, or ``None``. The ONE rule both
    ``decide --by`` and the validator apply: a non-empty string after strip, at most
    :data:`MAX_DECIDER_NAME_CHARS`, with no control characters."""
    if not isinstance(name, str) or not name.strip():
        return "has no decider name (decided_by.name is empty)"
    if len(name.strip()) > MAX_DECIDER_NAME_CHARS:
        return f"has a decider name longer than {MAX_DECIDER_NAME_CHARS} characters"
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        return "has a control character in its decider name"
    return None


def review_status_from_basis(candidate: Mapping) -> tuple[str, bool]:
    """``(review_status, proposable)`` re-derived from a candidate's OWN facts, exactly as
    ``SemanticCandidate`` derives them — so a tampered ``extracted_state`` (or
    ``review_status``) cannot stand on its own word (review L2)."""
    sb = candidate["state_basis"]
    proposable = (
        candidate["kind"] == "field"
        and sb["unresolved_reason"] is None
        and sb["not_proposable_reason"] is None
        and candidate["target_field_path"] is not None
    )
    if sb["resolved_by_rule"] is not None:
        return "resolved", proposable
    if sb["unresolved_reason"] is not None:
        return "sources_conflict", proposable
    if proposable:
        return "ready", proposable
    if candidate["kind"] == "field" and candidate["target_field_path"] is None:
        return "unmapped", proposable
    return "needs_review", proposable


def _extracted_from_status(status: str, proposable: bool) -> str:
    if status == "resolved":
        return STATE_CANDIDATE_EXTRACTED if proposable else STATE_NEEDS_REVIEW
    return REVIEW_STATUS_TO_STATE.get(status, STATE_NEEDS_REVIEW)


def _provenance_errors(bundle: Mapping) -> list[str]:
    """What a hand edit could otherwise get past the state rule (review L2)."""
    errors: list[str] = []
    writable = _writable_paths()
    decision_of = _decisions_by_target(bundle.get("scientist_decisions") or ())
    conflict_for: dict[str, list[str]] = {}
    for conflict in bundle["conflicts"]:
        if conflict.get("candidate_id"):
            conflict_for.setdefault(conflict["candidate_id"], []).append(conflict["conflict_id"])
    by_id = {c["candidate_id"]: c for c in bundle["candidates"]}
    for cid in conflict_for:
        c = by_id.get(cid)
        if c is None:
            errors.append(f"reference: a conflict names unknown candidate {cid}")
        elif c["state_basis"]["unresolved_reason"] is None and c["state_basis"]["resolved_by_rule"] is None:
            errors.append(f"consistency: {cid} has a conflict entry but records no disagreement")
    for c in bundle["candidates"]:
        cid = c["candidate_id"]
        status, proposable = review_status_from_basis(c)
        sb = c["state_basis"]
        if sb["review_status"] != status or sb["proposable"] != proposable:
            errors.append(f"state: {cid} state_basis says {sb['review_status']}/{sb['proposable']} but its own facts give {status}/{proposable}")
        if c["extracted_state"] != _extracted_from_status(status, proposable):
            errors.append(f"state: {cid} extracted_state {c['extracted_state']} is not what its state_basis supports")
        if proposable and c["target_field_path"] not in writable:
            errors.append(f"state: {cid} is proposable at a path this build cannot write")
        disagreeing = any(e["reading_index"] is not None or e["relation"] == "contradicts" for e in c["evidence"]) or bool(c.get("readings"))
        if disagreeing and sb["unresolved_reason"] is None and sb["resolved_by_rule"] is None:
            errors.append(f"state: {cid} carries disagreeing witnesses but records no disagreement")
        if sb["unresolved_reason"] is not None and c["value"] is not None:
            errors.append(f"state: {cid} records a disagreement yet carries a chosen value")
        if (sb["unresolved_reason"] is not None or (sb["resolved_by_rule"] and c.get("readings"))) and cid not in conflict_for:
            errors.append(f"consistency: {cid} is a disagreement with no conflicts[] entry")
        decided = candidate_decision(bundle, c, decision_of)
        if c["value"] is not None and (decided is None or decided.get("decision") in NEUTRAL_DECISIONS):
            if json.dumps(c["value"], sort_keys=True) not in witnessed_values(c):
                errors.append(f"provenance: {cid} carries a value no witness states and no recorded normalisation produced")
    return errors


def check_bundle(location: Path) -> list[str]:
    """Load and validate. Errors as strings; empty means the bundle meets v1."""
    try:
        bundle = load_bundle(location)
    except BundleInvalid as exc:
        return exc.errors
    return validate_bundle(bundle)
