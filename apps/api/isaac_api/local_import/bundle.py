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
FORMAT_VERSION = "1.2.0"
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
    "record_group": frozenset({"confirm", "split", "merge", "reject", "defer", "approve_calibration"}),
    "processing_result": frozenset({"approve", "reject", "needs_changes", "defer"}),
    "experiment": frozenset({"set_counter_positions"}),
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


def apply_derivations(bundle: dict) -> dict:
    """Recompute every DERIVED state in place and return ``bundle``.

    The single derivation both the writers (``import``, ``decide``, ``annotate``) and
    the validator use: candidate and missing-value states and eligibility, conflict
    states, record-group status, processing-result state, readiness and counts.
    """
    decision_of = _decisions_by_target(bundle.get("scientist_decisions") or ())
    interpreted = _interpreted_targets(bundle.get("ai_interpretations") or ())
    writable = _writable_paths()
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


def _split_locator(locator: str, archive_paths: Sequence[str]):
    from ..bl15 import reconstruct as rc  # local: bl15 imports historical_import

    return rc.split_statement_locator(locator, archive_paths)


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
            # official field unless an explicit, tested rule says so, and there is none.
            for k, st in enumerate(run_statements[:MAX_GENERIC_STATEMENTS_PER_RUN]):
                generic_statements.append(_statement_entry(g, k, st, run_id=run_id, po_id=None))
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
        truncated = total > len(evidence)
        if truncated:
            evidence_windows_truncated += 1
        extracted = _extracted_state_of(c)
        state = derive_value_state(extracted, decision=None, interpreted=False)
        distinct: list = []
        for e in evidence:
            if e["literal_value"] not in distinct:
                distinct.append(e["literal_value"])
        literals = distinct[:MAX_OBSERVED_LITERALS]
        out_candidates.append(
            {
                "candidate_id": bundle_cid,
                "engine_candidate_id": c.candidate_id,
                "kind": c.kind,
                "run_id": run_id,
                "scope": "run" if run_id else "beamtime",
                "statement_key": key,
                "target_field_path": c.target_field_path,
                "target_write_scope": _target_scope(c.target_field_path) or UPSTREAM_TARGET_FIELDS.get(c.target_field_path),
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
                    "not_proposable_summary": _plain_reason(c),
                    "resolved_by_rule": c.resolved_by_rule,
                },
                "rule": c.rule,
                "evidence": evidence,
                "evidence_total": total,
                "evidence_truncated": truncated,
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
        scope = _target_scope(path) or UPSTREAM_TARGET_FIELDS.get(path)
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
    question is about a value, not about whether it has been answered."""
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
    for cand in bundle["candidates"]:
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
    for r in bundle.get("processing_results") or ():
        if r.get("group_id") not in held_ids:
            errors.append(f"reference: processing result {processing_id(r)} names group {r.get('group_id')}, in neither record_groups nor superseded_record_groups")
        for f in (r.get("outputs") or {}).get("files") or ():
            if _safe_relative(f.get("relative_path")) is None:
                errors.append(f"paths: processing result {processing_id(r)} names an output outside the bundle")
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
