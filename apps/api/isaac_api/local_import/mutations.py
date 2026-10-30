"""Mutations of an ISAAC Local Import Bundle (slice LOCAL-2). No hand-edited JSON.

Every write here goes through :func:`save_bundle`, which (1) re-derives every state
with :func:`bundle.apply_derivations` and rebuilds ``questions[]``, (2) re-validates
the whole bundle against v1 and REFUSES to write an invalid one, (3) holds an
exclusive lock on the bundle directory, and (4) replaces ``bundle.json`` atomically
(temp file + ``os.replace``), then regenerates the derived section files.

THE BLIND PROTOCOL. ``exposures[]`` records every time a CLI command PRINTED a
target's parser value (``bundle show``, ``bundle list candidates``, ``bundle reveal``).
``annotate --blind`` is honoured only when no exposure exists for that target;
otherwise the interpretation is stored with ``blind: false`` and the reason. The CLI
cannot see a person or an agent reading ``bundle.json`` or ``reading.full.json``
directly — a blind claim is only as good as that discipline, and the contract says so.

IDENTITY. ``decided_by.identity`` is always ``local_unverified``: this build
authenticates nobody. An ORCID iD is stored as ``orcid_claimed`` — a credit value the
local user typed — and is never used to decide anything.
"""

from __future__ import annotations

import copy
import errno
import fcntl
import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import bundle as B

#: The most file-name positions one counter answer names (the schema's ``positions`` maxItems).
MAX_COUNTER_POSITIONS = 8
ORCID_RE = re.compile(r"\A[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]\Z")
MAX_EXCERPT_CHARS = 4_000
MAX_EXCERPTS = 5
EXCERPT_CONTEXT_LINES = 3

#: Crosscheck categories -> how a candidate is recognised (target path prefix or key).
CROSSCHECK_CATEGORIES: Sequence[tuple[str, tuple[str, ...], tuple[str, ...]]] = (
    ("sample_identity", ("sample.material.name", "sample.sample_id"), ("sample_name",)),
    ("potential_or_reference_basis", ("context.electrochemistry.potential", "context.electrochemistry.reference"), ("potential_magnitude", "potential_scale")),
    ("reaction", ("context.electrochemistry.reaction",), ()),
    ("environment", ("context.environment",), ()),
    ("cell_type", ("context.electrochemistry.cell_type",), ()),
    ("acquisition_time", ("timestamps.acquired_start_utc",), ()),
)
#: The order ``crosscheck-plan`` lists its items in: the high-value categories first, then values the
#: record requires, then the run-level checks. Within the order every item that can be EXCERPTED comes
#: before every one that cannot (a missing value has no source text to read).
CROSSCHECK_ORDER: Sequence[str] = (
    *(name for name, _, _ in CROSSCHECK_CATEGORIES), "required_by_record", "run_association", "herfd_signal_choice",
)
#: Locators ``crosscheck-plan`` prints per item (``locators_total`` says how many there are); ``excerpt``
#: reads at most :data:`MAX_EXCERPTS` of them anyway. Measured: a BL15-2 run lists one per scan, and
#: ``--limit 30`` printed 115 KB.
MAX_PLAN_LOCATORS = 5
NOT_EXCERPTABLE_MISSING = ("nothing in the source states it (a missing value): there is no source text to excerpt or "
                           "cross-check; the scientist answers it (`isaac bundle questions`)")


class MutationRefused(ValueError):
    """A mutation that was refused; nothing was written. ``code`` is the exit code."""

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- load / lock / save -------------------------------------------------------------------


@contextmanager
def locked(bundle_dir: Path):
    """An exclusive advisory lock on ``<dir>/.bundle.lock`` for one read-modify-write.

    The lock file is opened WITHOUT following a symbolic link (``O_NOFOLLOW``), owner-only when it is
    created, and not inherited by a child process (``O_CLOEXEC``): a ``.bundle.lock`` planted as a link
    can never make this create or truncate a file elsewhere. A lock file that cannot be opened safely
    (a link, no permission, a read-only folder) is refused, exit 1, naming no path."""
    bundle_dir = Path(bundle_dir)
    lock = bundle_dir / ".bundle.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(lock, flags, 0o600)
    except OSError as exc:
        why = {errno.ELOOP: "it is a symbolic link", errno.EACCES: "permission is denied",
               errno.EPERM: "permission is denied", errno.EROFS: "the folder is read-only"}.get(
                   exc.errno, errno.errorcode.get(exc.errno or 0, type(exc).__name__))
        raise MutationRefused(
            f"The bundle's lock file (.bundle.lock) cannot be opened safely: {why}. Nothing was read or written.",
            code=1) from None
    with os.fdopen(fd, "r+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load(bundle_dir: Path) -> dict:
    path = B.bundle_path(Path(bundle_dir))
    if not path.is_file():
        # the folder's NAME only: an absolute local path is never put in a message (data minimisation)
        raise MutationRefused(f"No bundle.json in {Path(bundle_dir).name!r}.", code=6)
    try:
        return B.load_bundle(path)
    except B.BundleInvalid as exc:
        raise MutationRefused(f"Unreadable bundle: {exc}", code=1) from exc


def save_bundle(bundle_dir: Path, bundle: dict) -> None:
    """Re-derive, re-validate, then atomically replace. Refuses an invalid result."""
    from . import cli

    # AN OLDER BUNDLE IS UPGRADED ONCE, AND NEVER SILENTLY. The first save by this build of a
    # bundle an older build stored (a smaller writable set, bundle.WRITABLE_ADDED_IN):
    #   * logs ONE `format_upgrades` entry (from/to version, time, how many decisions it held),
    #     printed once to stderr and shown by `check` and summary.md;
    #   * appends each value whose eligibility moves only for that reason to
    #     `eligibility_rederived`, read from the bundle AS STORED (on disk, under the caller's
    #     lock), so a change made now is not mistaken for one an older build made.
    # Every save also corrects the engine's "this build cannot write it yet" summary on paths this
    # local build writes (bundle.refresh_local_write_summaries); the engine's own text is kept.
    stored_version = bundle.get("format_version")
    # THE STORED VERSION IS NOT RELABELLED past what it holds: only a bundle that HAS
    # processed_outputs (an import by a 1.2.0+ build) is raised to this build's version (1.4.0:
    # its eligibility is re-derived below under this build's writable set, and it may now hold a
    # set_clock_time_zone decision, which a 1.3.0 validator refuses). An older bundle is raised to
    # at most 1.1.0, the version whose sections this writer adds below; calling it 1.2.0+ would
    # claim that its processed outputs had been separated from its runs, which only a re-import
    # does. 1.4.0 adds no section an import must have filled, and nothing newly writable; the one
    # import rule it adds (ssrl_xdc_scan_start_v1) is NOT applied by a save, so a 1.3.0 bundle with
    # ssrl_xdc_v1 runs is raised to 1.4.0 WITH a format_upgrades entry saying those runs have none
    # of its candidates until re-imported (bundle.import_rules_missing) — never silently.
    # 1.5.0 makes context.electrochemistry.control_mode writable (bundle.WRITABLE_ADDED_IN), as 1.3.0
    # did the set-point: a 1.4.0 bundle is raised to 1.5.0 with a format_upgrades entry naming it
    # newly writable, and any stored control-mode eligibility that moves is logged as re-derived. A
    # save adds no missing value: a 1.4.0 import has no control-mode answer slots until re-imported.
    # 1.7.0 (DEC-92) does the same for context.electrochemistry.current_setpoint_mA_cm2: a 1.4.0-1.6.0
    # bundle is raised with a format_upgrades entry naming it, and gets no current set-point slots
    # until re-imported. 1.8.0 raises the bounds of the append-only logs (bundle.CHANGES_ADDED_IN): a
    # 1.7.0-or-older bundle is raised with a format_upgrades entry saying so; no eligibility moves.
    to_version = (B.FORMAT_VERSION if "processed_outputs" in bundle
                  else "1.1.0" if stored_version in ("1.0.0", "1.1.0") else stored_version)
    upgrading = B.needs_format_upgrade(bundle)
    if not upgrading and B.allowed_list_rederivations(bundle):
        # A FIELD'S ALLOWED VALUES ARE NOW THE EXPORT TARGET'S LIST (bundle.allowed_values): a value an
        # older build judged against the vendored enum alone is re-derived by this save — and logged in
        # `eligibility_rederived`, read from the bundle AS STORED (the cheap check above runs on the
        # in-memory copy, which may already hold this change's own decision), never silently.
        stored_l = None
        if B.bundle_path(Path(bundle_dir)).is_file():
            try:
                stored_l = B.load_bundle(Path(bundle_dir))
            except B.BundleInvalid:
                stored_l = None
        if stored_l is not None:
            live = {("candidate", c["candidate_id"]) for c in bundle.get("candidates") or ()} | {
                ("missing_value", m["value_id"]) for m in bundle.get("missing_values") or ()}
            B.record_rederivation(bundle, [x for x in B.allowed_list_rederivations(stored_l) if (x["kind"], x["id"]) in live],
                                  to_version=to_version)
    if upgrading:
        stored = None
        if B.bundle_path(Path(bundle_dir)).is_file():
            try:
                stored = B.load_bundle(Path(bundle_dir))
            except B.BundleInvalid:
                stored = None
        stale: list = []
        if stored is not None:
            try:
                stale = B.stale_eligibility(stored)
            except (KeyError, TypeError, ValueError):
                stale = []
        live_ids = {("candidate", c["candidate_id"]) for c in bundle.get("candidates") or ()} | {
            ("missing_value", m["value_id"]) for m in bundle.get("missing_values") or ()}
        B.record_rederivation(bundle, [x for x in stale if (x["kind"], x["id"]) in live_ids], to_version=to_version)
        entry = B.record_format_upgrade(
            bundle, from_version=stored_version, to_version=to_version,
            decisions_before=len((stored if stored is not None else bundle).get("scientist_decisions") or ()))
        print(f"isaac: {entry['statement']} (bundle format {stored_version} -> {to_version}; "
              "logged in bundle.json format_upgrades)", file=sys.stderr)
    B.refresh_local_write_summaries(bundle)
    bundle["format_version"] = to_version
    for key in ("record_groups", "processing_results", "exposures"):
        bundle.setdefault(key, [])
    B.refresh_questions(bundle)
    B.apply_derivations(bundle)
    # NO WRITE ADDS A NON-FINITE NUMBER (NaN / Infinity: not standard JSON). One the STORED file already
    # holds — an answer an older build accepted, kept by the append-only log — never blocks a write
    # (a correction must be possible); `bundle check` names it and it is never eligible.
    if next(iter(B.non_finite_numbers(bundle)), None) is not None:
        stored_nf = None
        if B.bundle_path(Path(bundle_dir)).is_file():
            try:
                stored_nf = B.load_bundle(Path(bundle_dir))
            except B.BundleInvalid:
                stored_nf = None
        added = B.new_non_finite_paths(bundle, stored_nf)
        if added:
            raise MutationRefused(
                "The change would add a non-finite number (NaN or infinity), which is not standard JSON and no field "
                f"takes, so nothing was written: {', '.join(added[:10])}", code=5)
    errors = B.validate_bundle(bundle)
    if errors:
        raise MutationRefused(
            "The change would leave the bundle invalid, so nothing was written:\n  - "
            + "\n  - ".join(errors[:20]),
            code=5,
        )
    bundle_dir = Path(bundle_dir)
    cli._atomic_write(bundle_dir / B.BUNDLE_FILE, B.encode(bundle))
    for name, data in cli.section_payloads(bundle).items():
        cli._atomic_write(bundle_dir / name, data)


class StaleBundleVersion(MutationRefused):
    """The caller read the bundle at one version and it is now another (a CLI command, or
    another window, wrote it since). Nothing was written; ``current_version`` says what is
    there now, so the caller can re-read before answering again."""

    def __init__(self, expected: str, current: str | None):
        super().__init__(
            f"The bundle changed since it was read (read at {expected}, now {current}); nothing was written. "
            "Re-read the questions and answer again.",
            code=2,
        )
        self.expected = expected
        self.current = current


def bundle_version(bundle_dir: Path) -> str | None:
    """The version of ``bundle.json`` as stored: the sha256 of its bytes, or ``None`` when there is
    no file. Every save rewrites the file, so ANY write (this process's or a CLI command's) moves it.
    Read it under :func:`locked` when it must agree with what a following write sees."""
    path = B.bundle_path(Path(bundle_dir))
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require_version(bundle_dir: Path, expected_version: str | None) -> None:
    """Under the caller's lock: refuse when ``expected_version`` is given and is not what is stored."""
    if expected_version is None:
        return
    current = bundle_version(bundle_dir)
    if current != expected_version:
        raise StaleBundleVersion(expected_version, current)


def mutate(bundle_dir: Path, change, *, expected_version: str | None = None, with_version: bool = False) -> Any:
    """Lock, load, apply ``change(bundle)``, save. Returns what ``change`` returned.

    ``expected_version`` (a :func:`bundle_version`) is checked UNDER THE LOCK, before the load: a
    caller that showed a person the bundle at one version cannot write over a change made since
    (the CLI passes none, as it always has). ``with_version`` returns ``(result, version)``, the
    version read under the same lock right after the save."""
    with locked(Path(bundle_dir)):
        _require_version(Path(bundle_dir), expected_version)
        bundle = load(bundle_dir)
        result = change(bundle)
        save_bundle(bundle_dir, bundle)
        return (result, bundle_version(bundle_dir)) if with_version else result


# --- target lookup ---------------------------------------------------------------------------


def resolve_target(bundle: Mapping, target_id: str) -> tuple[str, dict]:
    """``(kind, object)`` for an id, by the bundle's own id spaces. ``experiment`` names
    the whole beamtime (e.g. for ``set_counter_positions``)."""
    if target_id == "experiment":
        return "experiment", {"id": "experiment"}
    sections = (
        ("candidate", "candidates", "candidate_id"),
        ("missing_value", "missing_values", "value_id"),
        ("conflict", "conflicts", "conflict_id"),
        ("source", "sources", "source_id"),
        ("run", "runs", "run_id"),
        ("record_group", "record_groups", "group_id"),
    )
    for kind, section, key in sections:
        for obj in bundle.get(section) or ():
            if obj.get(key) == target_id:
                return kind, obj
    for result in bundle.get("processing_results") or ():
        if B.processing_id(result) == target_id:
            return "processing_result", result
    for mc in bundle.get("merge_candidates") or ():
        if mc.get("merge_candidate_id") == target_id:
            return "merge_candidate", mc
    raise MutationRefused(f"No target with id {target_id!r} in this bundle.", code=6)


def _candidate_of_conflict(bundle: Mapping, conflict: Mapping) -> str | None:
    return conflict.get("candidate_id")


def record_exposure(bundle: dict, kind: str, target_id: str, command: str) -> None:
    """Record that ``command`` printed this target's parser value. First one per
    (target, command) is kept — the question a blind check asks is WHETHER and WHEN."""
    exposures = bundle.setdefault("exposures", [])
    for e in exposures:
        if e["target"] == {"kind": kind, "id": target_id} and e["command"] == command:
            return
    exposures.append(
        {
            "exposure_id": f"x-{len(exposures) + 1:06d}",
            "target": {"kind": kind, "id": target_id},
            "command": command,
            "at_utc": now_utc(),
        }
    )


def exposures_for(bundle: Mapping, kind: str, target_id: str) -> list[dict]:
    return [e for e in bundle.get("exposures") or () if e["target"] == {"kind": kind, "id": target_id}]


def expose_and_load(bundle_dir: Path, targets: Iterable[tuple[str, str]], command: str) -> dict:
    """Record exposures FIRST (durably), then hand back the bundle for printing. If the
    exposure cannot be written, nothing is printed — the caller gets the refusal."""
    targets = list(targets)

    def change(bundle):
        for kind, tid in targets:
            record_exposure(bundle, kind, tid, command)
            if kind == "conflict":
                _, conflict = resolve_target(bundle, tid)
                cid = conflict.get("candidate_id")
                if cid:
                    record_exposure(bundle, "candidate", cid, command)
        return bundle

    return mutate(bundle_dir, change)


# --- annotate (AI interpretation) -----------------------------------------------------------


def parse_value(raw: str | None, as_json: bool) -> Any:
    if raw is None:
        return None
    if not as_json:
        return raw
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise MutationRefused(f"--value is not valid JSON: {exc}") from exc
    # Python's json accepts NaN / Infinity / -Infinity (and reads 1e999 as Infinity); storing one would
    # make bundle.json non-standard JSON. Refused here, before anything is recorded.
    if (problem := B.non_finite_problem(value)) is not None:
        raise MutationRefused(f"--value {raw}: {problem}; nothing was recorded")
    return value


def _add_interpretation(bundle: dict, kind: str, obj: Mapping, target_id: str, *, value: Any, rationale: str,
                        source_refs: list, excerpt_locator: str | None, model_id: str, is_blind: bool, basis: str,
                        extra: Mapping | None = None) -> dict:
    """Append ONE AI interpretation (and, on a candidate, its context witness)."""
    interps = bundle.setdefault("ai_interpretations", [])
    if len(interps) >= B.MAX_AI_INTERPRETATIONS:
        raise MutationRefused(log_full_message("ai_interpretations", len(interps), 1, B.MAX_AI_INTERPRETATIONS))
    entry = {
        "interpretation_id": f"ai-{len(interps) + 1:04d}",
        "target": {"kind": kind, "id": target_id},
        "proposed_value": value,
        "rationale": rationale or "",
        "source_refs": source_refs,
        "method": "ai_interpretation",
        "model": {"model_id": model_id},
        "created_utc": now_utc(),
        "max_state": "needs_review",
        "blind": is_blind,
        "blind_basis": basis,
        "excerpt_locator": excerpt_locator,
    }
    for k, v in (extra or {}).items():
        if v is not None:
            entry[k] = v
    interps.append(entry)
    if kind == "candidate":
        source_id = (source_refs[0] if source_refs else {}).get("source_id")
        if len(obj["evidence"]) >= B.MAX_EVIDENCE_PER_CANDIDATE:
            obj["evidence_truncated"] = True
        else:
            path = None
            if source_id:
                path = next(s["relative_path"] for s in bundle["sources"] if s["source_id"] == source_id)
            obj["evidence"].append(
                {
                    "evidence_id": f"{obj['candidate_id']}.ai{len(interps):04d}",
                    "source_id": source_id,
                    "relative_path": path,
                    "locator": excerpt_locator or "(no locator given)",
                    "statement_key": obj["statement_key"],
                    "literal_value": value,
                    "method": "ai_interpretation",
                    "method_id": model_id,
                    "relation": "context",
                    "reading_index": None,
                    "normalization": [],
                }
            )
        obj["evidence_total"] = max(obj["evidence_total"] + 1, len(obj["evidence"]))
        obj["evidence_truncated"] = obj["evidence_total"] > len(obj["evidence"])
    return entry


def log_full_message(section: str, held: int, adding: int, bound: int) -> str:
    """The sentence for a write refused because an append-only log is at its bound (contract §7)."""
    what = "scientist decisions" if section == "scientist_decisions" else "AI interpretations"
    return (f"This bundle already holds {held:,} {what}; recording {adding:,} more would pass the bound of {bound:,} "
            f"({section}, contract §7), so nothing was written. The log is append-only and nothing in it is dropped: "
            "start a new import of the remaining files, or split this beamtime's files into smaller imports.")


_INTERPRETABLE = ("candidate", "missing_value", "record_group", "source", "run", "processing_result")


def annotate(
    bundle_dir: Path,
    *,
    target_id: str,
    value: Any,
    excerpt_locator: str | None,
    source_id: str | None,
    model_id: str,
    blind: bool,
    rationale: str,
) -> dict:
    """Store ONE AI interpretation. It can lift a value to ``needs_review`` and never
    higher (``bundle.derive_value_state``); it never settles a conflict."""

    def change(bundle):
        kind, obj = resolve_target(bundle, target_id)
        if kind not in _INTERPRETABLE:
            raise MutationRefused(f"An AI interpretation cannot target a {kind}.")
        if source_id is not None and source_id not in {s["source_id"] for s in bundle["sources"]}:
            raise MutationRefused(f"Unknown source {source_id!r}.", code=6)
        prior = exposures_for(bundle, kind, target_id)
        if blind and not prior:
            is_blind, basis = True, "No CLI command had printed this target's parser value before this reading."
        elif blind:
            first = prior[0]
            is_blind, basis = False, (
                f"--blind was requested, but `{first['command']}` printed this target's parser "
                f"value at {first['at_utc']}, so the reading is not blind."
            )
        else:
            is_blind, basis = False, "Not requested as blind."
        return _add_interpretation(
            bundle, kind, obj, target_id, value=value, rationale=rationale,
            source_refs=[{"source_id": source_id, "locator": excerpt_locator}] if (source_id or excerpt_locator) else [],
            excerpt_locator=excerpt_locator, model_id=model_id, is_blind=is_blind, basis=basis,
        )

    return mutate(bundle_dir, change)


def annotate_from_readings(bundle_dir: Path, findings: Mapping, *, model_id: str, apply: bool) -> dict:
    """A Claude reading pass's findings file (``isaac.reading_findings``) as AI
    interpretations, one per target, in ONE write. Without ``apply`` nothing is written.
    Re-applying the same findings adds nothing (an identical reading of a target is kept once)."""
    from . import suggestions as S

    def plan(bundle):
        try:
            out = S.readings_to_interpretations(bundle, findings, model_id=model_id)
        except S.ReadingsRefused as exc:
            raise MutationRefused(str(exc)) from exc
        # ``field_path`` is part of the identity: one group can be read as element ``K``
        # (potassium) and edge ``K`` from one line, and those are two readings.
        seen = {
            (i["target"]["kind"], i["target"]["id"], json.dumps(i.get("proposed_value"), sort_keys=True),
             i.get("source_path"), i.get("excerpt_locator"), i.get("field_path"), json.dumps(i.get("run_ids")))
            for i in bundle.get("ai_interpretations") or ()
        }
        fresh, repeated = [], 0
        for t, f in out["planned"]:
            key = (t["kind"], t["id"], json.dumps(f["proposed_value"], sort_keys=True), f["source_path"], f["excerpt_locator"],
                   f["field_path"], json.dumps(f["run_ids"]))
            if key in seen:
                repeated += 1
                continue
            seen.add(key)
            fresh.append((t, f))
        return out, fresh, repeated

    def summary(out, fresh, repeated, recorded):
        by_field: dict = {}
        for t, f in fresh:
            by_field.setdefault(f["finding_id"], 0)
            by_field[f["finding_id"]] += 1
        return {"applied": recorded, "interpretations": len(fresh), "already_recorded": repeated,
                "targets_per_finding": by_field, "skipped": out["skipped"]}

    if not apply:
        with locked(Path(bundle_dir)):
            bundle = load(bundle_dir)
        out, fresh, repeated = plan(bundle)
        return summary(out, fresh, repeated, False)

    def change(bundle):
        out, fresh, repeated = plan(bundle)
        for t, f in fresh:
            kind, obj = resolve_target(bundle, t["id"])
            if kind not in _INTERPRETABLE:
                raise MutationRefused(f"An AI interpretation cannot target a {kind}.")
            _add_interpretation(
                bundle, kind, obj, t["id"], value=f["proposed_value"], rationale=f["rationale"],
                source_refs=f["source_refs"], excerpt_locator=f["excerpt_locator"], model_id=model_id,
                is_blind=False, basis="A reading pass over the files; not requested as blind.",
                extra={k: f[k] for k in ("source_path", "quote", "strength", "finding_id", "field_path", "run_ids")},
            )
        return summary(out, fresh, repeated, True)

    return mutate(bundle_dir, change)


# --- decide (scientist decision) ------------------------------------------------------------


def _has_source_evidence(candidate: Mapping) -> bool:
    return any(e["method"] in ("deterministic_parser", "stored_rule") for e in candidate["evidence"])


def _check_decision(bundle: Mapping, kind: str, obj: Mapping, decision: str, value: Any, *, bulk: bool,
                    merge_with: Sequence[str] | None = None) -> None:
    allowed = B.DECISIONS_BY_KIND.get(kind)
    if allowed is None:
        raise MutationRefused(f"A {kind} cannot be decided.")
    if decision not in allowed:
        raise MutationRefused(f"`{decision}` is not a decision for a {kind}; allowed: {', '.join(sorted(allowed))}.")
    if kind == "record_group" and decision == "merge":
        problem = merge_with_problem(bundle, obj["group_id"], merge_with)
        if problem is not None:
            raise MutationRefused(f"{problem} Nothing was recorded.")
    if kind == "processing_result" and B.processing_not_applicable(obj):
        app = obj.get("applicability") or {}
        raise MutationRefused(
            f"{B.processing_id(obj)} is not a curve: the processing protocol does not apply to this group "
            f"({app.get('reason_code')}: {B.NO_PROTOCOL_COVERS}). There is nothing to {decision}, and no QC verdict was given."
        )
    if kind == "processing_result" and decision == "approve" and not (obj.get("outputs") or {}).get("files"):
        raise MutationRefused(no_curve_refusal(obj))
    if decision == "correct" and value is None:
        raise MutationRefused("`correct` needs --value.")
    if decision == B.ATHENA_SELECT_DECISION:
        listed = B.athena_version_ids(obj)
        if not listed:
            raise MutationRefused(f"{B.processing_id(obj)} lists no Athena versions; there is no result of record to select.")
        if value not in listed:
            raise MutationRefused(
                f"{value!r} is not one of the Athena versions {B.processing_id(obj)} lists ({', '.join(listed)}). "
                "Name one of them with --value; nothing was recorded."
            )
        ident = [B.athena_version_identity(v) for v in obj.get("athena_versions") or ()]
        mine = B.athena_version_identity(next(v for v in obj["athena_versions"] if v.get("version_id") == value))
        if ident.count(mine) != 1 or not any(mine.values()):
            raise MutationRefused(
                f"{value!r} cannot be told apart from another listed version by its own provenance (project file, "
                "Athena group, data hash), so a later re-processing could not keep this selection on it. Nothing was recorded."
            )
    if kind == "candidate" and decision == "confirm" and B.is_local_clock_start(obj):
        # a local clock time is confirmed only as the UTC value a CONFIRMED zone gives it; a value
        # the scientist supplies is a correction, and is never credited to the zone rule
        if value is not None:
            raise MutationRefused(
                f"{obj['candidate_id']} is a local clock time: `confirm` accepts only the UTC value the instrument "
                "clock's confirmed time zone gives it, so it takes no --value. To give the UTC start yourself, use "
                f"`isaac bundle decide <bundle_dir> --target {obj['candidate_id']} --decision correct --value "
                'YYYY-MM-DDTHH:MM:SSZ --by "<your name>"`.'
            )
        zone_d = B.clock_zone_decision(bundle)
        if zone_d is None:
            raise MutationRefused(
                f"{obj['candidate_id']} is a local clock time with no time zone; there is no UTC value to confirm "
                "until a scientist states the time zone the instrument clock was set to: "
                f"{B.CLOCK_ZONE_COMMAND}  (or give the UTC start yourself with `correct --value YYYY-MM-DDTHH:MM:SSZ`)."
            )
        got = B.local_clock_start(obj, zone_d)
        if got["value"] is None:
            raise MutationRefused(f"{obj['candidate_id']} carries no value to confirm: {got['reason']}")
    if kind == "candidate" and decision == "confirm":
        if value is None and obj["value"] is None:
            raise MutationRefused(
                f"{obj['candidate_id']} carries no value to confirm. Use `correct --value ...` "
                "to give one."
            )
        if bulk and not _has_source_evidence(obj):
            raise MutationRefused(f"{obj['candidate_id']} has no source evidence; a bulk confirmation needs it.")
    if kind in ("missing_value", "conflict") and decision in ("confirm", "correct") and value is None:
        raise MutationRefused(f"Deciding a {kind} needs --value: there is no single extracted value to confirm.")
    problem = _decided_value_problem(bundle, kind, obj, decision, value)
    if problem is not None:
        raise MutationRefused(problem)


def no_curve_cause(result: Mapping) -> str:
    """``code: detail`` of why a processing result made no curve (its ``failure``), plainly."""
    failure = result.get("failure") or {}
    code = failure.get("code") or ", ".join((result.get("qc") or {}).get("reasons") or ()) or "no output file"
    detail = failure.get("detail")
    return f"{code}: {detail}" if detail else str(code)


def reprocess_command(group_id: str) -> str:
    """Re-processing ONE group with other parameters: the only way to a different result."""
    return (f"`isaac process <bundle_dir> --source <the beamtime folder you imported> --group {group_id} "
            "--params-file <params.json>`")


def no_curve_refusal(result: Mapping) -> str:
    """Why approving a processing result that has NO CURVE (no output file) is refused, and the
    real options. An approval would put a QC status into the record with no spectrum beside it."""
    pid, gid = B.processing_id(result), result.get("group_id")
    verdict = (result.get("qc") or {}).get("verdict")
    return (
        f"{pid} has no curve to approve: the protocol made no output file (QC verdict {verdict!r}, "
        f"{no_curve_cause(result)}), so an approval would state a QC status for a spectrum that does not exist. "
        "Re-running `isaac process` with the same parameters gives the same result. The options: "
        f'reject it (`isaac bundle decide <bundle_dir> --target {pid} --decision reject --by "<your name>"`); '
        f"or mark it needs_changes (`--target {pid} --decision needs_changes`) and re-process the group with "
        f"other parameters ({reprocess_command(gid)}), which adds a new result to review; "
        "or leave the group out of the records "
        f'(`isaac bundle decide <bundle_dir> --target {gid} --decision reject --by "<your name>"`). Nothing was recorded.'
    )


def merge_with_problem(bundle: Mapping, group_id: str, merge_with: Sequence[str] | None) -> str | None:
    """Why a ``merge`` of ``group_id`` with ``merge_with`` names nothing to merge, or ``None``.

    A merge needs at least one OTHER group this bundle holds, each LIVE (proposed or confirmed). A
    merge with no ``merge_with``, an unknown id, the group itself, or a rejected / merged / split
    group combined nothing: it only moved the group to ``merged`` — a silent reject."""
    named = list(dict.fromkeys(merge_with or ()))
    how = ("isaac bundle decide <bundle_dir> --target " + group_id
           + " --decision merge --merge-with <other group id> --by \"<your name>\"")
    if not named:
        return f"A merge of {group_id} needs --merge-with naming the group(s) to merge it with: `{how}`."
    if group_id in named:
        return f"--merge-with names {group_id} itself; a group is merged with ANOTHER group: `{how}`."
    groups = {g["group_id"]: g for g in bundle.get("record_groups") or ()}
    unknown = [x for x in named if x not in groups]
    if unknown:
        superseded = {g["group_id"] for g in bundle.get("superseded_record_groups") or ()}
        said = ", ".join(x + (" (superseded by a regroup; not a record group now)" if x in superseded else "") for x in unknown)
        return f"--merge-with names no record group of this bundle: {said}. `isaac bundle list <bundle_dir> groups` lists them."
    dead = [f"{x} ({groups[x].get('status')})" for x in named if groups[x].get("status") not in B.LIVE_GROUP_STATUSES]
    if dead:
        return (f"--merge-with names a group that is no longer live: {', '.join(dead)}. Only a proposed or confirmed group "
                "can be merged with; its runs are now in another proposal (`isaac bundle list <bundle_dir> groups`).")
    return None


def _decided_value_problem(bundle: Mapping, kind: str, obj: Mapping, decision: str, value: Any) -> str | None:
    """Why a ``confirm``/``correct`` would store a value its official field refuses, or ``None``.

    The SAME check eligibility makes (:func:`bundle.eligibility_for_official_record`: a path this
    build writes, then :func:`bundle.value_problem` — the ``*_utc`` rule, the field's
    :func:`bundle.allowed_values` (the list every question offers, which the export validates against)
    and the vendored schema's ``type``), made BEFORE anything is recorded. Without it an off-list answer was
    stored as ``scientist_confirmed`` but never eligible, and its question closed: the record stayed
    blocked with nothing left to ask. A value on a path this build does not write stays evidence and
    is not checked (eligibility does not check it either); when the vendored schema cannot be read,
    nothing is refused here — eligibility still fails closed."""
    if decision not in ("confirm", "correct"):
        return None
    if kind == "candidate":
        path = obj.get("target_field_path")
        effective = B.final_value(obj.get("value"), {"decision": decision, "value": value}, obj.get("readings"))
        label = obj["candidate_id"]
    elif kind == "missing_value":
        path, effective, label = obj.get("target_field_path"), value, obj["value_id"]
    elif kind == "conflict":
        cand = next((c for c in bundle.get("candidates") or () if c["candidate_id"] == obj.get("candidate_id")), None)
        path, effective, label = (cand or {}).get("target_field_path"), value, obj["conflict_id"]
    else:
        return None
    if not path or effective is None or path not in B._writable_paths():
        return None
    if not isinstance(B._vendored_schema(), Mapping):
        return None
    problem = B.value_problem(path, effective)
    if problem is None:
        return None
    node = B._schema_node(path) or {}
    allowed = B.allowed_values(path)  # the same list every question offers (bundle.allowed_values)
    hint = ""
    if allowed:
        hint = f" Allowed values for {path}: {', '.join(json.dumps(a) if not isinstance(a, str) else a for a in allowed)}."
    elif isinstance(effective, str) and {"number", "integer"} & set(
            node.get("type") if isinstance(node.get("type"), list) else [node.get("type")]):
        hint = " Give the number itself with --json (e.g. --value 0.5 --json)."
    return (f"{label}: {problem}, so it could never go into the record.{hint} Nothing was recorded "
            f"(`{decision}` refused).")


def decide(
    bundle_dir: Path,
    *,
    target_ids: Sequence[str],
    decision: str,
    value: Any,
    by: str,
    orcid: str | None,
    note: str | None = None,
    split_into: Sequence[Sequence[str]] | None = None,
    merge_with: Sequence[str] | None = None,
    qc_status: str | None = None,
    qc_note: str | None = None,
    element: str | None = None,
    edge: str | None = None,
    positions: Sequence[int] | None = None,
    expected_version: str | None = None,
) -> dict:
    """Record a scientist decision for each target (ALL-OR-NOTHING), idempotently.

    Replaying the same decision for a target whose latest decision is already identical
    records nothing new. Each target is its own entry even in a bulk call, sharing a
    ``batch_id``. ``expected_version``: see :func:`mutate` (the CLI passes none).
    """
    params = dict(
        target_ids=target_ids, decision=decision, value=value, by=by, orcid=orcid, note=note,
        split_into=split_into, merge_with=merge_with, qc_status=qc_status, qc_note=qc_note,
        element=element, edge=edge, positions=positions,
    )
    _decide_arguments(**params)  # refused before the lock is taken, as always
    return mutate(bundle_dir, lambda bundle: record_decision(bundle, **params), expected_version=expected_version)


def question_targets(payload: Mapping, question_id: str, *, decision: str, only: str | None, field: str | None,
                     positions: Sequence[int] | None,
                     only_scopes: Sequence[str] | None = None) -> tuple[list[str], list[int] | None]:
    """``decide --question``: the targets a consolidated question's answer is recorded on, and the
    positions it names. ONE implementation for the CLI and the local questions screen.

    Refuses a decision that does not answer the question (so e.g. an absorber question can never
    bulk-confirm the record GROUPS it targets), and a question with no open target in that scope
    (``--only``) or field (``--field``). The counter question answered with
    ``set_not_counter_positions`` and no positions names the positions it asks about now."""
    from . import questions as Q

    asked = Q.question(payload, question_id)
    if asked is not None and decision not in asked.get("allowed_decisions", ()):
        raise MutationRefused(
            f"`{decision}` does not answer question {question_id} ({asked['kind']}); "
            f"use one of: {', '.join(asked.get('allowed_decisions') or ()) or '(none)'}."
        )
    if only_scopes:
        # SEVERAL SCOPES (the local screen's "accept for the groups whose files suggest it"): exactly their
        # targets, and refused whole when any named scope has no open target — never a partial answer
        if only:
            raise MutationRefused("Name one scope (--only) or several, not both.")
        found = []
        for sc in dict.fromkeys(only_scopes):
            got = Q.targets_for(payload, question_id, sc, field)
            if not got:
                raise MutationRefused(f"No open question {question_id!r} for {sc}; nothing was recorded.", code=6)
            found += [t for t in got if t not in found]
    else:
        found = Q.targets_for(payload, question_id, only, field)
    if not found:
        raise MutationRefused(f"No open question {question_id!r}" + (f" for {only}" if only else "") + ".", code=6)
    if asked is not None and asked["kind"] == "naming_counter_positions" and decision == B.NOT_COUNTER_DECISION and positions is None:
        positions = list(asked.get("positions") or [])  # the positions the question asks about now
    return list(found), (list(positions) if positions is not None else None)


def decide_question(
    bundle_dir: Path,
    *,
    question_id: str,
    only: str | None = None,
    only_scopes: Sequence[str] | None = None,
    field: str | None = None,
    extra_targets: Sequence[str] = (),
    decision: str,
    value: Any,
    by: str,
    orcid: str | None,
    note: str | None = None,
    split_into: Sequence[Sequence[str]] | None = None,
    merge_with: Sequence[str] | None = None,
    qc_status: str | None = None,
    qc_note: str | None = None,
    element: str | None = None,
    edge: str | None = None,
    positions: Sequence[int] | None = None,
    expected_version: str | None = None,
    dry_run: bool = False,
    with_version: bool = False,
) -> Any:
    """``isaac bundle decide --question`` — the CLI and the local questions screen both call this.

    The question is resolved to its targets UNDER THE SAME LOCK as the write, from the bundle that
    write changes, so an answer can never land on targets another command changed in between. With
    ``expected_version`` the stored version is checked first, under that lock. ``dry_run`` resolves
    and checks exactly as a write would (every target, every refusal) on a copy and writes nothing:
    it returns the targets a write would record and the version it was read at. ``with_version``
    returns ``(result, version)`` for a write, the version read under the lock right after the save."""
    from . import questions as Q

    # as the CLI always answered: a folder with no bundle.json is exit 6, and nothing (not even the
    # lock file) is created in it
    if not B.bundle_path(Path(bundle_dir)).is_file():
        raise MutationRefused(f"No bundle.json in {Path(bundle_dir).name!r}.", code=6)
    with locked(Path(bundle_dir)):
        _require_version(Path(bundle_dir), expected_version)
        version = bundle_version(bundle_dir)
        bundle = load(bundle_dir)
        found, positions = question_targets(Q.consolidate(bundle), question_id, decision=decision, only=only,
                                            field=field, positions=positions, only_scopes=only_scopes)
        params = dict(
            target_ids=list(extra_targets) + found, decision=decision, value=value, by=by, orcid=orcid, note=note,
            split_into=split_into, merge_with=merge_with, qc_status=qc_status, qc_note=qc_note,
            element=element, edge=edge, positions=positions,
        )
        if dry_run:
            planned = record_decision(copy.deepcopy(bundle), **params)
            return {"dry_run": True, "bundle_version": version, "target_ids": params["target_ids"], **planned}
        result = record_decision(bundle, **params)
        save_bundle(bundle_dir, bundle)
        return (result, bundle_version(bundle_dir)) if with_version else result


#: QC statuses that say something is WRONG with the measurement: approving with one needs ``--qc-note``
#: saying what and why (the historical-import skill asks for it; a bare "compromised" tells a reader nothing).
QC_STATUSES_NEEDING_A_NOTE = ("compromised", "failed")


def qc_note_problem(qc_status: str | None, qc_note: str | None) -> str | None:
    """Why a QC status cannot be recorded without a note, or ``None`` (one rule for the CLI and the local screen)."""
    if qc_status in QC_STATUSES_NEEDING_A_NOTE and not (qc_note or "").strip():
        return (f"--qc-status {qc_status} says something is wrong with the measurement, so it needs --qc-note "
                f"\"<what is {qc_status} and why>\" — the scientist's own words. Nothing was recorded.")
    return None


def _decide_arguments(*, target_ids, decision, by, orcid, qc_status, element, edge, positions, value=None,
                      qc_note=None, **_rest):
    """The checks of :func:`decide` that need no bundle. Returns ``positions`` normalised."""
    problem = B.decider_name_problem(by)
    if problem:
        raise MutationRefused(f"--by is required: the name of the person deciding (this one {problem.replace('has ', 'has ', 1)}).")
    if orcid is not None and not ORCID_RE.fullmatch(orcid):
        raise MutationRefused("--orcid must look like 0000-0000-0000-0000 (last character may be X).")
    if not target_ids:
        raise MutationRefused("No target given.")
    if qc_status is not None:
        allowed = qc_status_vocabulary()
        if qc_status not in allowed:
            raise MutationRefused(f"--qc-status must be one of {', '.join(allowed)} (measurement.qc.status).")
        if decision != "approve":
            raise MutationRefused("--qc-status goes with --decision approve on a processing result.")
        problem = qc_note_problem(qc_status, qc_note)
        if problem:
            raise MutationRefused(problem)
    if decision in ("approve_calibration", "set_absorber"):
        if not B.is_absorber_element(element) or not B.is_absorber_edge(edge):
            raise MutationRefused(f"{decision} needs --element (e.g. Ir) and --edge (K, L1-L3, M1-M5).")
    elif element or edge:
        raise MutationRefused("--element/--edge go with --decision approve_calibration or set_absorber on a record group.")
    if decision in ("set_counter_positions", B.NOT_COUNTER_DECISION):
        from .grouping import LAST_POSITION

        if (
            not positions
            or len(positions) > MAX_COUNTER_POSITIONS
            or any(not isinstance(n, int) or isinstance(n, bool) or (n < 1 and n != LAST_POSITION) for n in positions)
        ):
            raise MutationRefused(
                f"--positions must be 1 to {MAX_COUNTER_POSITIONS} positions: positive whole numbers, or `last` for the last "
                "token whatever the name's length, e.g. --positions 2, --positions 2,3 or --positions last"
                + (" (answering the counter question with --question names its open positions for you)."
                   if decision == B.NOT_COUNTER_DECISION else ".")
            )
        if decision == B.NOT_COUNTER_DECISION and LAST_POSITION in positions:
            raise MutationRefused("`last` goes with set_counter_positions (the last token IS a counter); "
                                  "set_not_counter_positions names whole-number positions only.")
        positions = sorted(set(positions)) if decision == B.NOT_COUNTER_DECISION else list(positions)
    elif positions:
        raise MutationRefused("--positions goes with --target experiment --decision set_counter_positions or set_not_counter_positions.")
    if decision == B.ATHENA_SELECT_DECISION and (value is None or not isinstance(value, str)):
        raise MutationRefused("select_athena_version needs --value <version id>, one of the processing result's athena_versions.")
    if decision == B.CLOCK_ZONE_DECISION:
        problem = B.clock_zone_problem(value)
        if problem is not None:
            raise MutationRefused(f"{problem}. Nothing was recorded.")
    return positions


#: What a 1.6.0 capture decision records — and what it does NOT do (DEC-91). Returned by ``decide``.
CAPTURE_STATEMENTS: Mapping[str, str] = {
    B.KEEP_APART_DECISION: (
        "Recorded: the groups this merge candidate names are distinct and stay apart. The candidate is no "
        "longer an open merge question (status kept_apart). No group was changed, confirmed or rejected: "
        "confirm (or otherwise decide) each group on its own."
    ),
    B.ATHENA_SELECT_DECISION: (
        "Recorded: {value} is the scientist's result of record among this result's Athena versions "
        "(athena_result_of_record). The processing result's state, QC status and processed values are unchanged."
    ),
    B.NOT_COUNTER_DECISION: (
        "Recorded: filename token position(s) {positions} are NOT run/acquisition counters. Grouping is unchanged "
        "by this answer: runs whose names differ there were proposed as separate groups and stay so, and each merge "
        "candidate between them stays open (merge it, or keep it apart). The counter question no longer asks about "
        "these positions."
    ),
}


def record_decision(
    bundle: dict,
    *,
    target_ids: Sequence[str],
    decision: str,
    value: Any,
    by: str,
    orcid: str | None,
    note: str | None = None,
    split_into: Sequence[Sequence[str]] | None = None,
    merge_with: Sequence[str] | None = None,
    qc_status: str | None = None,
    qc_note: str | None = None,
    element: str | None = None,
    edge: str | None = None,
    positions: Sequence[int] | None = None,
) -> dict:
    """:func:`decide` applied to an ALREADY-LOADED bundle, under the caller's lock. Saves
    nothing: the caller saves through :func:`save_bundle` (or :func:`mutate`). Every target
    is checked before any entry is appended, so a refusal leaves ``bundle`` unchanged."""
    positions = _decide_arguments(
        target_ids=target_ids, decision=decision, by=by, orcid=orcid, qc_status=qc_status,
        element=element, edge=edge, positions=positions, value=value, qc_note=qc_note,
    )
    bulk = len(target_ids) > 1

    def change(bundle):
        latest = B._decisions_by_target(bundle.get("scientist_decisions") or ())
        planned: list[tuple[str, dict]] = []
        for tid in target_ids:
            kind, obj = resolve_target(bundle, tid)
            _check_decision(bundle, kind, obj, decision, value, bulk=bulk, merge_with=merge_with)
            if qc_status is not None and kind != "processing_result":
                raise MutationRefused("--qc-status applies to a processing result only.")
            if kind == "processing_result" and decision == "approve" and qc_status is None:
                # I4: the QC status is never guessed from the protocol's verdict.
                raise MutationRefused(
                    "Approving a processing result needs --qc-status (one of "
                    + ", ".join(qc_status_vocabulary()) + "): the QC status is a person's statement."
                )
            if kind == "record_group" and decision == "confirm":
                # R-4: a group whose runs now sit in ANOTHER live group cannot be confirmed
                # (e.g. a rejected group after a regroup re-proposed its runs)
                mine = set(obj.get("member_run_keys") or ())
                for other in bundle.get("record_groups") or ():
                    if other["group_id"] != tid and other.get("status") in B.LIVE_GROUP_STATUSES and mine & set(other.get("member_run_keys") or ()):
                        raise MutationRefused(
                            f"This group's run is now in proposal {other['group_id']}; confirm or reject that proposal instead."
                        )
            if decision == B.NOT_COUNTER_DECISION:
                counters = set(counter_positions(bundle) or ())
                clash = sorted(set(positions or ()) & counters)
                if clash:
                    raise MutationRefused(
                        f"Position(s) {', '.join(map(str, clash))} are recorded as run counters by the latest "
                        "set_counter_positions answer. To say otherwise, record set_counter_positions without them; "
                        "nothing was recorded."
                    )
            planned.append((kind, obj))
        decided_by = {
            "name": by.strip(),
            "basis": "self_reported_local_user",
            "identity": "local_unverified",
            "orcid_claimed": (
                {"value": orcid, "basis": "claimed_for_credit_not_authentication"} if orcid else None
            ),
        }
        decisions = bundle.setdefault("scientist_decisions", [])
        batch_id = f"batch-{len(decisions) + 1:04d}" if bulk else None
        if decision == B.CLOCK_ZONE_DECISION:
            # what the zone answer is about to undo is SAID, never left for a later check to find
            counting_before = {x["candidate_id"] for x in B.local_clock_reconfirm(B.apply_derivations(json.loads(json.dumps(bundle))))}
        recorded, unchanged = [], []
        held_before = len(decisions)
        zone_d = B.clock_zone_decision(bundle)
        for tid, (kind, obj) in zip(target_ids, planned):
            prior = latest.get((kind, tid))
            if kind == "experiment":
                # several decision kinds share the one experiment target: replaying one is compared
                # with the latest of ITS kind (a zone restated after a counter answer is unchanged)
                prior = next((d for d in reversed(bundle.get("scientist_decisions") or ())
                              if d.get("target") == {"kind": "experiment", "id": tid} and d.get("decision") == decision), None)
            elif kind == "processing_result":
                # an Athena-version selection (1.6.0) and the state decisions share the target: each is
                # compared with the latest of its own class
                selecting = decision == B.ATHENA_SELECT_DECISION
                prior = next((d for d in reversed(bundle.get("scientist_decisions") or ())
                              if d.get("target") == {"kind": kind, "id": tid}
                              and (d.get("decision") == B.ATHENA_SELECT_DECISION) == selecting), None)
            elif kind in ("candidate", "conflict") and prior is not None:
                # A CANDIDATE'S VALUE IS GOVERNED BY THE LATER of its own decision and its conflict's
                # (bundle.candidate_decision). A replay is "unchanged" only when this target's latest
                # decision is the one that governs NOW: after `correct` cand -> A, `confirm` conflict -> B,
                # a second `correct` cand -> A changes the composed value back to A and is recorded.
                cand = obj if kind == "candidate" else next(
                    (c for c in bundle.get("candidates") or () if c["candidate_id"] == obj.get("candidate_id")), None)
                if cand is not None and B.candidate_decision(bundle, cand, latest) is not prior:
                    prior = None
            # THE BINDING (1.4.0): a confirmation of a local-clock start time records the zone and the
            # converted value it was made under; a later zone decision cannot reuse it silently.
            binding = (B.local_clock_binding(obj, zone_d)
                       if kind == "candidate" and decision == "confirm" and B.is_local_clock_start(obj) and zone_d is not None
                       else None)
            # an Athena selection is compared on the version's IDENTITY, not its positional id: after a
            # renumbering, `g1-v01` may now be another curve, and re-selecting it is a new statement
            identity = (B.athena_version_identity(next(v for v in obj.get("athena_versions") or () if v.get("version_id") == value))
                        if decision == B.ATHENA_SELECT_DECISION else None)
            signature = (decision, json.dumps(value, sort_keys=True), decided_by["name"], orcid,
                         json.dumps(split_into or []), json.dumps(merge_with or []), qc_status, qc_note, element, edge,
                         json.dumps(positions or []), json.dumps(binding, sort_keys=True), json.dumps(identity, sort_keys=True))
            if prior is not None and (
                prior.get("decision"),
                json.dumps(prior.get("value"), sort_keys=True),
                (prior.get("decided_by") or {}).get("name"),
                ((prior.get("decided_by") or {}).get("orcid_claimed") or {}).get("value"),
                json.dumps(prior.get("split_into") or []),
                json.dumps(prior.get("merge_with") or []),
                prior.get("qc_status"),
                prior.get("qc_note"),
                prior.get("element"),
                prior.get("edge"),
                json.dumps(prior.get("positions") or prior.get("not_counter_positions") or []),
                json.dumps(prior.get("clock_zone_binding"), sort_keys=True),
                json.dumps(prior.get("athena_version_provenance"), sort_keys=True),
            ) == signature:
                unchanged.append(tid)
                continue
            entry = {
                "decision_id": f"d-{len(decisions) + 1:05d}",
                "target": {"kind": kind, "id": tid},
                "decision": decision,
                "value": value,
                "chosen_reading_index": None,
                "decided_by": decided_by,
                "decided_utc": now_utc(),
                "method": "scientist_answer",
                "note": note,
                "batch_id": batch_id,
            }
            if split_into:
                entry["split_into"] = [list(g) for g in split_into]
            if merge_with:
                entry["merge_with"] = list(merge_with)
            if decision in ("approve_calibration", "set_absorber"):
                entry["element"], entry["edge"] = element, edge
            if decision == "set_counter_positions":
                entry["positions"] = positions
            if decision == B.NOT_COUNTER_DECISION:
                entry["not_counter_positions"] = positions
            if decision == B.ATHENA_SELECT_DECISION:
                # the version's own identity, so a re-processing that renumbers the versions cannot make
                # this selection point at another curve (B.athena_resolve)
                entry["athena_version_provenance"] = identity
            if binding is not None:
                entry["clock_zone_binding"] = binding
            if kind == "processing_result" and decision == "approve":
                # AN APPROVAL BINDS TO EXACTLY THIS RESULT'S FILES (and their hashes).
                entry["approved_files"] = [
                    {"role": f.get("role"), "relative_path": f.get("relative_path"), "sha256": f.get("sha256")}
                    for f in (obj.get("outputs") or {}).get("files") or ()
                ]
            if qc_status is not None:
                # THE PERSON STATES THE QC STATUS; what they were shown is kept beside it.
                qc = obj.get("qc") or {}
                entry["qc_status"] = qc_status
                entry["qc_note"] = qc_note
                entry["qc_evidence"] = {"verdict": qc.get("verdict"), "metrics": qc.get("metrics") or {}}
            decisions.append(entry)
            recorded.append(tid)
        if len(decisions) > B.MAX_SCIENTIST_DECISIONS:
            added = len(decisions) - held_before
            del decisions[held_before:]  # the refusal leaves the bundle as it was
            raise MutationRefused(log_full_message("scientist_decisions", held_before, added, B.MAX_SCIENTIST_DECISIONS))
        result = {"recorded": recorded, "unchanged": unchanged, "batch_id": batch_id}
        statement = CAPTURE_STATEMENTS.get(decision)
        if statement:
            result["statement"] = statement.format(value=value, positions=", ".join(map(str, positions or ())))
        if decision == "needs_changes":
            # WHAT needs_changes DOES, said: it moves nothing but the result's review, and it freezes the
            # result against a plain re-run (bundle.apply_derivations, process: a state decision keeps it)
            gids = sorted({obj.get("group_id") for _, obj in planned if obj.get("group_id")})
            result["statement"] = (
                f"Recorded: {', '.join(target_ids)} needs changes. Its state stays needs_review: not approved and not "
                "rejected, so its group still has no approved curve and cannot become a complete record. A plain "
                "`isaac process` re-run keeps it as it is (a decided result is never replaced). A changed result comes "
                "only from re-processing with other parameters: "
                + "; ".join(reprocess_command(g) for g in gids[:3]) + (" …" if len(gids) > 3 else "")
                + ", which adds a new result beside this one to review and approve."
            )
        if decision == B.CLOCK_ZONE_DECISION:
            after = B.apply_derivations(json.loads(json.dumps(bundle)))
            stale = B.local_clock_reconfirm(after)
            # ONLY what THIS decision undid: a confirmation already stale before it is not counted again
            newly = [x for x in stale if x["candidate_id"] not in counting_before]
            value_of = {c["candidate_id"]: c["value"] for c in after["candidates"]}
            to_confirm = [x["candidate_id"] for x in newly if value_of.get(x["candidate_id"]) is not None]
            to_correct = [x["candidate_id"] for x in newly if value_of.get(x["candidate_id"]) is None]

            def _ids(ids):
                return ", ".join(ids[:20]) + ("…" if len(ids) > 20 else "")

            parts = []
            if to_confirm:
                parts.append(f"{len(to_confirm)} to confirm again (this zone gives a UTC value): {_ids(to_confirm)}")
            if to_correct:
                parts.append(f"{len(to_correct)} to correct with a UTC value (in this zone the local time is ambiguous or "
                             f"does not exist, so there is nothing to confirm): {_ids(to_correct)}")
            result["clock_zone"] = {
                **B.clock_zone_status(after),
                "confirmations_invalidated_now": len(newly),
                "to_confirm_again": to_confirm,
                "to_correct": to_correct,
                "statement": (
                    f"The instrument clock's time zone is now {value}. "
                    + (f"{len(newly)} start-time confirmation(s) made under another zone no longer count: the clock "
                       "time zone changed after they were confirmed, so the UTC value they confirmed is not the one "
                       "this zone gives (isaac bundle questions lists them). " + "; ".join(parts) + "."
                       if newly else "No start-time confirmation was undone by it.")
                ),
            }
            if newly:
                print(f"isaac: {result['clock_zone']['statement']}", file=sys.stderr)
        return result

    return change(bundle)


# --- crosscheck plan / excerpt / reveal ---------------------------------------------------------


def _locators(candidate: Mapping) -> list[dict]:
    return [
        {"source_id": e["source_id"], "relative_path": e["relative_path"], "locator": e["locator"]}
        for e in candidate["evidence"]
        if e["method"] != "ai_interpretation"
    ][:B.MAX_EVIDENCE_PER_CANDIDATE]


def crosscheck_plan(bundle: Mapping) -> dict:
    """High-value targets to cross-check, with ids and source locators — NO values.
    Also the coverage so far: checked (has an AI reading), blind-checked, unchecked."""
    required = B.required_record_paths()
    interps = bundle.get("ai_interpretations") or ()
    checked: dict[tuple[str, str], list[dict]] = {}
    for i in interps:
        checked.setdefault((i["target"]["kind"], i["target"]["id"]), []).append(i)
    items: list[dict] = []

    def add(kind, tid, category, run_id, locators, field_path=None, not_excerptable=None):
        key = (kind, tid)
        readings = checked.get(key, [])
        excerptable = not_excerptable is None and bool(locators)
        item = {
            "target": {"kind": kind, "id": tid},
            "category": category,
            "run_id": run_id,
            "field_path": field_path,
            "excerptable": excerptable,
            "locators": locators[:MAX_PLAN_LOCATORS],
            "locators_total": len(locators),
            "checked": bool(readings),
            "blind_checks": sum(1 for r in readings if r.get("blind")),
            "parser_value_exposed": bool(exposures_for(bundle, kind, tid)),
        }
        if not excerptable:
            item["not_excerptable_because"] = not_excerptable or "no source locator was recorded for it"
        items.append(item)

    sources = {s["source_id"]: s for s in bundle["sources"]}
    for run in bundle["runs"]:
        locs = [{"source_id": run["acquisition_source_id"], "relative_path": sources.get(run["acquisition_source_id"], {}).get("relative_path"), "locator": "the acquisition file"}]
        locs += [{"source_id": s["source_id"], "relative_path": s["relative_path"], "locator": f"scan {s['scan_index']}"} for s in run["scans"]]
        locs += [{"source_id": d["macro_source_id"], "relative_path": d["macro_path"], "locator": f"newfile block {d['block_index']}"} for d in run["declared_by"]]
        add("run", run["run_id"], "run_association", run["run_id"], locs)
        if run["signal_selection"]:
            add("run", run["run_id"], "herfd_signal_choice", run["run_id"],
                [{"source_id": s["source_id"], "relative_path": s["relative_path"], "locator": f"scan {s['scan_index']} channel columns"} for s in run["scans"]])
    for c in bundle["candidates"]:
        path = c["target_field_path"] or ""
        category = None
        for name, prefixes, keys in CROSSCHECK_CATEGORIES:
            if any(path == p or path.startswith(p) for p in prefixes) or c["statement_key"] in keys:
                category = name
                break
        if category is None and path and B._required_for(path, required):
            category = "required_by_record"
        if category:
            add("candidate", c["candidate_id"], category, c["run_id"], _locators(c), field_path=c["target_field_path"])
    for m in bundle["missing_values"]:
        if B._required_for(m["target_field_path"], required):
            add("missing_value", m["value_id"], "required_by_record", m["run_id"], [],
                field_path=m["target_field_path"], not_excerptable=NOT_EXCERPTABLE_MISSING)
    # HIGH-VALUE FIRST, and every item that can be excerpted before every one that cannot (stable)
    rank = {name: n for n, name in enumerate(CROSSCHECK_ORDER)}
    items.sort(key=lambda i: (not i["excerptable"], rank.get(i["category"], len(rank))))
    total = len(items)
    excerptable_n = sum(1 for i in items if i["excerptable"])
    by_category: dict[str, int] = {}
    for i in items:
        by_category[i["category"]] = by_category.get(i["category"], 0) + 1
    checked_n = sum(1 for i in items if i["checked"])
    blind_n = sum(1 for i in items if i["blind_checks"])
    return {
        "total": total,
        "excerptable": excerptable_n,
        "not_excerptable": total - excerptable_n,
        "by_category": {name: by_category[name] for name in CROSSCHECK_ORDER if name in by_category},
        "statement_excerptable": (
            f"{excerptable_n} of {total} item(s) can be cross-checked against the source (`excerpt` reads their "
            f"locators; each item lists at most {MAX_PLAN_LOCATORS}, `locators_total` says how many it has). The "
            f"other {total - excerptable_n} (excerptable: false) have no source text — a missing value is answered "
            "by the scientist, never cross-checked. High-value categories come first."
        ),
        "coverage": {
            "checked": checked_n,
            "blind_checked": blind_n,
            "unchecked": total - checked_n,
            "statement": (
                "Spot checks only. A checked target has at least one AI reading recorded; "
                "nothing here claims the bundle is verified, and unchecked targets were not "
                "examined at all."
            ),
        },
        "items": items,
    }


def _source_root(bundle: Mapping, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    hint = bundle["source_root"].get("local_root_hint")
    if hint:
        return Path(hint)
    raise MutationRefused(
        "This bundle does not record where its source is (that is the default). Pass "
        "--source <the folder or ZIP you imported>."
    )


_LINE_RE = re.compile(r"\bline (\d+)\b")


def excerpt(bundle: Mapping, target_id: str, *, source: str | None) -> dict:
    """Raw source text at a target's locators — never a parser value. Bounded. The file
    is re-read through the same guarded walk, and refused if its bytes changed."""
    from .. import historical_import as hist
    from ..bl15 import archive

    kind, obj = resolve_target(bundle, target_id)
    if kind == "candidate":
        locs = _locators(obj)
    elif kind == "source":
        locs = [{"source_id": obj["source_id"], "relative_path": obj["relative_path"], "locator": "line 1"}]
    elif kind == "run":
        locs = [{"source_id": obj["acquisition_source_id"], "relative_path": None, "locator": "line 1"}]
    elif kind == "missing_value":
        raise MutationRefused(f"{target_id} is not excerptable: {NOT_EXCERPTABLE_MISSING}. `crosscheck-plan` marks "
                              "such items excerptable: false.")
    else:
        raise MutationRefused(f"A {kind} has no source locators to excerpt.")
    root = _source_root(bundle, source)
    inventory = hist._inventory_of(root, root_label=root.name)
    current = {e.archive_path: e for e in inventory.entries}
    sources = {s["source_id"]: s for s in bundle["sources"]}
    out = []
    for loc in locs[:MAX_EXCERPTS]:
        src = sources.get(loc["source_id"]) if loc["source_id"] else None
        if src is None:
            continue
        path = src["relative_path"]
        if ".zip!/" in path.lower():
            out.append({"source_id": src["source_id"], "relative_path": path,
                        "refused": "a member of a ZIP inside the folder: excerpt does not open nested archive members yet; read it with the Read tool after unzipping"})
            continue
        entry = current.get(path)
        if entry is None:
            out.append({"source_id": src["source_id"], "relative_path": path, "refused": "the file is no longer in the source"})
            continue
        if src["content_sha256"] and entry.content_sha256 != src["content_sha256"]:
            out.append({"source_id": src["source_id"], "relative_path": path, "refused": "the file's bytes changed since the import"})
            continue
        text, refusal = archive.read_source_text(inventory, path, source_root=root)
        if text is None:
            out.append({"source_id": src["source_id"], "relative_path": path, "refused": str(refusal)})
            continue
        lines = text.splitlines()
        match = _LINE_RE.search(loc["locator"] or "")
        if match:
            n = int(match.group(1))
            lo, hi = max(1, n - EXCERPT_CONTEXT_LINES), min(len(lines), n + EXCERPT_CONTEXT_LINES)
        else:
            lo, hi = 1, min(len(lines), 2 * EXCERPT_CONTEXT_LINES + 1)
        body = "\n".join(f"{i:>5}: {lines[i - 1]}" for i in range(lo, hi + 1))
        truncated = len(body) > MAX_EXCERPT_CHARS
        out.append(
            {
                "source_id": src["source_id"],
                "relative_path": path,
                "locator": loc["locator"],
                "lines": [lo, hi],
                "text": body[:MAX_EXCERPT_CHARS],
                "truncated": truncated,
            }
        )
    return {
        "target": {"kind": kind, "id": target_id},
        "excerpts": out,
        "omitted": max(0, len(locs) - MAX_EXCERPTS),
        "statement": "Raw source text only; no parser value is shown. Reading this does not record an exposure.",
    }


def _same(a: Any, b: Any) -> bool:
    def norm(v):
        return v.strip().casefold() if isinstance(v, str) else v
    return norm(a) == norm(b)


def reveal(bundle_dir: Path, target_id: str) -> dict:
    """The parser value plus a comparison with every AI reading. RECORDS AN EXPOSURE."""
    with locked(Path(bundle_dir)):
        bundle = load(bundle_dir)
        kind, obj = resolve_target(bundle, target_id)
        record_exposure(bundle, kind, target_id, "bundle reveal")
        save_bundle(bundle_dir, bundle)
    readings = [i for i in bundle.get("ai_interpretations") or () if i["target"] == {"kind": kind, "id": target_id}]
    if kind == "candidate":
        parser = {"value": obj["value"], "observed_literals": obj["observed_literals"], "value_state": obj["value_state"]}
        base = obj["value"]
    elif kind == "run":
        parser = {"signal_selection": obj["signal_selection"], "label": obj["label"]}
        base = (obj["signal_selection"] or {}).get("primary_channel")
    else:
        parser = {"value": None, "note": f"a {kind} has no parser value"}
        base = None
    return {
        "target": {"kind": kind, "id": target_id},
        "parser": parser,
        "ai_readings": [
            {
                "interpretation_id": r["interpretation_id"],
                "proposed_value": r["proposed_value"],
                "blind": r.get("blind", False),
                "agrees_with_parser": (_same(r["proposed_value"], base) if base is not None else None),
            }
            for r in readings
        ],
        "exposure_recorded": True,
    }


# --- LOCAL-P wiring: grouping and processing, persisted through save_bundle ----------------------


def group(bundle_dir: Path, *, regroup: bool = False) -> dict:
    """Propose record groups (``local_import.grouping``, via LOCAL-P's entry point) and
    store them in ``record_groups[]``.

    ON ``--regroup`` (reviews B-1, B-2, R-1, R-2), by each existing group's STATUS, not by
    whether some decision names it:

    * BINDING (``scientist_confirmed``): kept, and its runs are never re-proposed;
    * HISTORY (``rejected``, ``split``, ``merged``): kept as the record of that decision; its
      runs are proposed afresh. A fresh proposal identical to a rejected or split group is
      not re-proposed (the scientist ruled on exactly that); one identical to a MERGED group
      is re-proposed under a distinct id with a merge candidate carrying the merge decision
      (nothing applies ``merge_with``; the scientist confirms the merge);
    * ``proposed`` (undecided, deferred, calibration-only): replaced. If a decision or a
      processing result still names it and the fresh proposal does not reproduce it, it moves
      to ``superseded_record_groups[]`` so they keep their target.

    STRUCTURAL: the fresh proposal is computed over the runs that are NOT bound and are not a
    zero-scan export of a bound run, so every group, flag, issue and question is computed
    from its real members; the sample-number check, the counter question and the
    ``matches_binding_group`` merge candidates come from the proposal over the FULL bundle.
    Refused on a pre-1.2.0 bundle that still holds the scientists' processed outputs as runs."""
    try:
        from .processing import cli_entry
    except ImportError as exc:  # pragma: no cover - the package ships with the checkout
        raise MutationRefused(f"grouping is not installed: {exc}", code=2) from exc
    from . import grouping as G

    def change(bundle):
        refusal = B.legacy_refusal(bundle)
        if refusal:
            raise MutationRefused(refusal, code=2)
        existing = list(bundle.get("record_groups") or ())
        if existing and not regroup:
            raise MutationRefused("This bundle already has record groups; pass --regroup to replace the undecided ones.")
        binding = [g for g in existing if g.get("status") in B.BINDING_GROUP_STATUSES]
        history = [g for g in existing if g.get("status") in B.HISTORY_GROUP_STATUSES]
        replaced = [g for g in existing if g not in binding and g not in history]
        keep = binding + history
        kept_by_id = {g["group_id"]: g for g in keep}
        exp_key = G.experiment_key_of(bundle)
        full = cli_entry.build_groups_payload(bundle)  # over the FULL bundle
        bind_of = {rk: g["group_id"] for g in binding for rk in g.get("member_run_keys") or ()}
        exports_of_binding = {
            rk: bind_of[i["related_run_key"]]
            for rk, issues in (full.get("engine_reading_issues") or {}).get("per_run", {}).items()
            for i in issues
            if rk not in bind_of and i.get("code") == "exported_file_read_as_acquisition" and i.get("related_run_key") in bind_of
        }
        excluded = set(bind_of) | set(exports_of_binding)
        if excluded:
            view = {**bundle, "runs": [r for r in bundle.get("runs") or () if r.get("run_key") not in excluded]}
            payload = cli_entry.build_groups_payload(view, context=bundle)
        else:
            payload = full
        decisions = bundle.get("scientist_decisions") or ()
        merge_decision = {
            d["target"]["id"]: d for d in decisions
            if d["target"]["kind"] == "record_group" and d.get("decision") == "merge"
        }
        fresh, renamed = [], {}
        for g0 in payload["record_groups"]:
            g = dict(g0)
            hist = kept_by_id.get(g["group_id"])
            if hist is not None:
                if hist.get("status") != "merged":
                    continue  # identical to a rejected/split group (or the bound group itself)
                old = g["group_id"]
                g["group_id"] = G.group_id_for(exp_key, list(g["member_run_keys"]) + [f"reproposed-after:{old}"])
                g["reproposed_after_group_id"] = old
                g["flags"] = list(g.get("flags") or []) + ["reproposed_after_merge_decision"]
                renamed[old] = g["group_id"]
            g["status"] = "proposed"  # only a decision moves it
            g.setdefault("condition_violations", [])  # carried; a proposed group must have none
            fresh.append(g)
        fresh_of = {k: g["group_id"] for g in fresh for k in g.get("member_run_keys") or ()}
        merge_candidates = [
            {**mc, "group_ids": [renamed.get(x, x) for x in mc.get("group_ids") or ()]}
            for mc in payload.get("merge_candidates") or ()
        ]
        merge_candidates += G.binding_merge_candidates(
            full["record_groups"], fresh, bind_of, exports_of_binding, experiment_key=exp_key
        )
        # A MERGE DECISION IS APPLIED (DEC-91; before 1.6.0 it was only carried as a candidate, which no
        # decision could turn into one group — a dead end). The runs of the merged group and of every
        # group it names in merge_with are proposed as ONE combined group, for the scientist to confirm,
        # only when nothing the import or a scientist recorded tells them apart (FAIL CLOSED,
        # :func:`_merge_blocker_details`): none is in a confirmed group, they share a role, every basis
        # reading agrees, the independent condition check finds nothing but the names, the file names
        # agree but for declared counters and repeat markers (or the scientist confirmed one sample for
        # every run), and no confirmed run-level answer differs. Anything else keeps the candidate below,
        # naming why and the commands that move it on (1.9.0: before, a counter answer was the only
        # advice, and it changed nothing for runs that state no sample — a dead end measured on real data).
        by_id_all = {g["group_id"]: g for g in [*(bundle.get("superseded_record_groups") or ()), *existing]}
        # the combined group a previous regroup made for a decision still holds the runs of its
        # merge_with groups after those were replaced, so a later regroup reproduces it
        combined_runs_of: dict[str, list[str]] = {}
        for g in existing:
            mbd = g.get("merged_by_decision")
            if isinstance(mbd, Mapping) and mbd.get("decision_id"):
                combined_runs_of.setdefault(mbd["decision_id"], []).extend(g.get("member_run_keys") or ())
        combined_by: list[dict] = []
        not_combined: list[dict] = []
        runs_by_key = {r["run_key"]: r for r in bundle.get("runs") or ()}
        for gid, d in sorted(merge_decision.items()):
            if (by_id_all.get(gid) or {}).get("status") != "merged":
                continue  # a later status decision superseded the merge
            runs_named = [k for x in [gid, *(d.get("merge_with") or [])] for k in (by_id_all.get(x) or {}).get("member_run_keys") or ()]
            runs_named += [k for k in combined_runs_of.get(d["decision_id"], ()) if k not in runs_named]
            gids = sorted({fresh_of[k] if k in fresh_of else bind_of[k] for k in runs_named if k in fresh_of or k in bind_of})
            if len(gids) < 2:
                if d["decision_id"] not in combined_runs_of:
                    # NEVER SILENT: a merge decision that names nothing to merge (no merge_with, an unknown
                    # id, the group itself, a group that is no longer live — `decide` refuses these now, but
                    # an older bundle may hold one), or whose runs are all in one group already, combined
                    # nothing. (One a previous regroup DID combine, now confirmed or re-proposed whole, is
                    # not listed: it was applied.)
                    not_combined.append({"decision_id": d["decision_id"],
                                         "reason": _merge_not_applicable(d, gid, by_id_all, gids)})
                continue
            why, steps = None, []
            holders = [g for g in fresh if g["group_id"] in gids]
            if any(k in bind_of for k in runs_named):
                why = "a run of it is in a confirmed group, whose runs are never re-proposed"
            elif len(holders) != len(gids) or len({h.get("role") for h in holders}) != 1:
                why = "the groups holding its runs do not share one role"
            if why is None:
                order = {g["group_id"]: i for i, g in enumerate(fresh)}
                holders.sort(key=lambda h: order[h["group_id"]])
                combined = _combine_for_merge(holders, d, gid, exp_key)
                prior = kept_by_id.get(combined["group_id"])
                if prior is not None:
                    # H1: the combined group was itself decided (rejected, split or merged): that is the
                    # scientist's ruling on exactly this group, so it is not proposed again — and no
                    # candidate re-asks it
                    not_combined.append({"decision_id": d["decision_id"],
                                         "reason": f"the combined group {combined['group_id']} was already decided ({prior.get('status')})"})
                    continue
                blockers = _merge_blocker_details(bundle, payload, holders, combined)
                if blockers:
                    why = "; ".join(r for r, _ in blockers)
                    steps = list(dict.fromkeys(c for _, cs in blockers for c in cs))
                else:
                    first = order[holders[0]["group_id"]]
                    fresh = [g for g in fresh if g["group_id"] not in gids]
                    fresh.insert(min(first, len(fresh)), combined)
                    for h in holders:
                        renamed[h["group_id"]] = combined["group_id"]
                        for k in h.get("member_run_keys") or ():
                            fresh_of[k] = combined["group_id"]
                    combined_by.append({"decision_id": d["decision_id"], "group_id": combined["group_id"], "from_groups": gids})
                    continue
            not_combined.append({"decision_id": d["decision_id"], "reason": why, "next_commands": steps})
            reason = {"code": "scientist_decided_merge", "decision_id": d["decision_id"], "group_id": gid,
                      "detail": f"a scientist decided to merge these runs' former groups, but they were not combined: {why}. "
                                "Confirm or reject each group, or record a new decision."}
            same = next((mc for mc in merge_candidates if sorted(mc.get("group_ids") or ()) == gids and not mc.get("run_keys")), None)
            if same is not None:
                # ONE candidate per set of groups: the rule's candidate for exactly these groups keeps its id
                # (a scientist's answers key on it) and leads with the decision (before 1.9.0 the pair was
                # listed twice, under two ids)
                merge_candidates[merge_candidates.index(same)] = {
                    **same, "reasons": [reason, *(same.get("reasons") or ())], "reason_code": "scientist_decided_merge",
                    "reason_codes": sorted({"scientist_decided_merge", *(same.get("reason_codes") or ())})}
                continue
            mcid = "mc-" + hashlib.sha256((exp_key + "\n" + "\n".join(gids)).encode()).hexdigest()[:16]
            merge_candidates.append({
                "merge_candidate_id": mcid, "experiment_key": exp_key, "group_ids": gids, "run_keys": [],
                "status": "proposed", "rule_id": G.BINDING_RULE_ID, "reasons": [reason],
                "reason_code": "scientist_decided_merge", "reason_codes": ["scientist_decided_merge"],
                "caution": G.merge_candidate_caution({h["group_id"]: h for h in holders}, runs_by_key, gids),
            })
        if combined_by:
            # a candidate that named a group now combined names the combined group instead; one left
            # naming a single group (and no run) has nothing left to merge
            remapped, seen_mc = [], set()
            for mc in merge_candidates:
                gids2 = sorted({renamed.get(x, x) for x in mc.get("group_ids") or ()})
                if gids2 != sorted(mc.get("group_ids") or ()):
                    if len(gids2) < 2 and not mc.get("run_keys"):
                        continue
                    mc = {**mc, "group_ids": gids2,
                          "merge_candidate_id": "mc-" + hashlib.sha256((exp_key + "\n" + "\n".join(gids2 + list(mc.get("run_keys") or []))).encode()).hexdigest()[:16]}
                if mc["merge_candidate_id"] in seen_mc:
                    continue
                seen_mc.add(mc["merge_candidate_id"])
                remapped.append(mc)
            merge_candidates = remapped
        bundle["record_groups"] = keep + fresh
        ids = {g["group_id"] for g in bundle["record_groups"]}
        before_mc = list(bundle.get("merge_candidates") or ())
        bundle["merge_candidates"] = [dict(mc) for mc in merge_candidates if mc.get("group_ids") and set(mc["group_ids"]) <= ids]
        # 1.6.0: a merge candidate a decision names (keep_apart) that this regroup no longer proposes is
        # kept in superseded_merge_candidates, so the decision keeps its target; one proposed again
        # leaves it (its decision applies to it again by id)
        mc_now = {mc["merge_candidate_id"] for mc in bundle["merge_candidates"]}
        mc_named = {d["target"]["id"] for d in decisions if d["target"]["kind"] == "merge_candidate"}
        sup_mc = [x for x in bundle.get("superseded_merge_candidates") or () if x["merge_candidate_id"] not in mc_now]
        known_mc = {x["merge_candidate_id"] for x in sup_mc}
        for mc in before_mc:
            mcid = mc.get("merge_candidate_id")
            if mcid in mc_named and mcid not in mc_now and mcid not in known_mc:
                sup_mc.append({"merge_candidate_id": mcid, "group_ids": list(mc.get("group_ids") or []),
                               "run_keys": list(mc.get("run_keys") or []), "superseded_utc": now_utc(),
                               "reason": "no longer proposed by `isaac bundle group --regroup`; a decision names it, so it "
                                         "is kept here as that decision's target. It is not an open question."})
        if sup_mc or "superseded_merge_candidates" in bundle:
            bundle["superseded_merge_candidates"] = sup_mc
        mc_ids_of: dict[str, list[str]] = {}
        for mc in bundle["merge_candidates"]:
            for x in mc["group_ids"]:
                mc_ids_of.setdefault(x, []).append(mc["merge_candidate_id"])
        for g in fresh:
            g["merge_candidate_ids"] = mc_ids_of.get(g["group_id"], [])
        # A replaced group that a decision, a processing result OR an AI reading (an absorber
        # finding is recorded on a group) names is kept as superseded, so every reference stays
        # resolvable. Its readings stay on it; they do not move to the new groups (apply the
        # findings file again for those).
        named = {d["target"]["id"] for d in decisions if d["target"]["kind"] == "record_group"}
        named |= {i["target"]["id"] for i in bundle.get("ai_interpretations") or () if i["target"]["kind"] == "record_group"}
        results_of: dict[str, list[str]] = {}
        for r in bundle.get("processing_results") or ():
            results_of.setdefault(r.get("group_id"), []).append(B.processing_id(r))
        superseded = [s for s in bundle.get("superseded_record_groups") or () if s["group_id"] not in ids]
        known = {s["group_id"] for s in superseded}
        for g in replaced:
            gid = g["group_id"]
            if gid in ids or gid in known or (gid not in named and gid not in results_of):
                continue
            superseded.append(
                {
                    "group_id": gid,
                    "member_run_keys": list(g.get("member_run_keys") or []),
                    "status": "proposed",
                    "superseded_utc": now_utc(),
                    "reason": (
                        "replaced by `isaac bundle group --regroup`; a decision, processing result or AI reading names it, "
                        "so it is kept here as their target. It is not a record."
                    ),
                    "processing_result_ids": results_of.get(gid, []),
                }
            )
        if superseded or "superseded_record_groups" in bundle:
            bundle["superseded_record_groups"] = superseded
        questions = [
            dict(q) for q in (full.get("experiment_questions") or full.get("questions") or ())
            if isinstance(q, Mapping)
        ]
        if excluded:
            # N-3: the counter question is the beamtime's (full bundle), but an answer cannot
            # merge a CONFIRMED group's runs; say so where that changes what it resolves.
            view_q = next((q for q in payload.get("experiment_questions") or () if q.get("kind") == "naming_counter_positions"), None)
            for q in questions:
                if q.get("kind") != "naming_counter_positions":
                    continue
                left = dict((view_q or {}).get("candidates_resolved_by_position") or {})
                if left != dict(q.get("candidates_resolved_by_position") or {}):
                    q["candidates_resolved_by_position_excluding_confirmed"] = left
                    q["text"] = str(q.get("text") or "") + (
                        " Runs of a confirmed group are not merged by the answer; they are offered as a merge candidate instead."
                    )
        bundle["grouping_questions"] = questions
        return {
            "record_groups": len(bundle["record_groups"]),
            # the groups that are (or may become) records; the rest is decision history (merged, rejected, split)
            "live_record_groups": sum(1 for g in bundle["record_groups"] if g.get("status") in B.LIVE_GROUP_STATUSES),
            "kept_decided": len(keep),
            "kept_binding": len(binding),
            "kept_history": len(history),
            "superseded": len(superseded),
            "proposed": len(fresh),
            "merge_candidates": len(bundle["merge_candidates"]),
            "combined_by_merge_decision": combined_by,
            "merge_decisions_not_combined": not_combined,
            "rule_id": payload.get("rule_id"),
            "statement": "Proposed groups only. A scientist confirms, splits, merges or rejects each one.",
            "read_them_with": [
                "isaac bundle list <bundle_dir> groups",
                "isaac bundle show <bundle_dir> group <group_id>",
                "isaac bundle list <bundle_dir> merge-candidates",
            ],
        }

    result = mutate(bundle_dir, change)
    # record_groups.json is kept as a MIRROR of bundle.json's record_groups (so LOCAL-P's
    # processing reads exactly the persisted groups and never re-proposes its own).
    from .cli import _atomic_write, _json_bytes

    saved = load(bundle_dir)
    _atomic_write(
        Path(bundle_dir) / cli_entry.GROUPS_FILE,
        _json_bytes({
            "format": cli_entry.GROUPS_FORMAT,
            "format_version": cli_entry.GROUPS_FORMAT_VERSION,
            "notice": "A mirror of bundle.json's record_groups, rewritten by every `isaac bundle group`. bundle.json is the authority.",
            "bundle_id": saved.get("bundle_id"),
            "record_groups": saved.get("record_groups") or [],
            "merge_candidates": saved.get("merge_candidates") or [],
        }),
    )
    return result


def _merge_not_applicable(d: Mapping, gid: str, by_id_all: Mapping, gids: Sequence[str]) -> str:
    """The reason a stored merge decision combined nothing (``merge_decisions_not_combined``)."""
    named = [x for x in d.get("merge_with") or () if x != gid]
    unknown = [x for x in named if x not in by_id_all]
    if not d.get("merge_with"):
        why = "the merge decision names no group to merge with (no merge_with)"
    elif not named:
        why = "the merge decision names only the group itself in merge_with"
    elif unknown and len(unknown) == len(named):
        why = f"merge_with names no group this bundle holds ({', '.join(unknown)})"
    elif gids:
        why = f"its runs are all in one group now ({gids[0]}), so there is nothing to combine"
    else:
        why = "none of the runs it names is in a live group now"
    return (why + "; it merged nothing, and its group stays `merged` (not a record). Decide that group again "
            "(confirm, reject, or merge with --merge-with <group id>).")


def _reading_core(v: Any) -> str:
    """A basis reading compared on what it SAYS (value, kind ...), never on the per-run evidence ids."""
    if isinstance(v, Mapping):
        v = {k: x for k, x in v.items() if k != "candidate_ids"}
    return json.dumps(v, sort_keys=True)


#: The one basis key a merge decision may override: the name stem standing in for an unstated
#: sample (``grouping.CONDITION_KEYS['sample_name_stem']``) — it is the file name, which is what the
#: scientist's merge rules on. Every other differing basis reading blocks the combination.
_MERGE_NAME_ONLY_BASIS = frozenset({("sample", "sample_name_stem")})
_MERGE_NAME_ONLY_VIOLATIONS = frozenset({"name_non_counter_tokens", "sample_name_stem"})


#: The field a scientist states a run's sample in; the same confirmed value for every run lets a merge
#: decision combine runs whose file names differ (the scientist has said what the names could not).
MERGE_SAMPLE_PATH = "sample.material.name"
#: A file-name token stating a quantity with its unit (``400mV``, ``0p5wt``, ``25C``), a decimal (``7p02``,
#: written ``7.02``) or a pH (``pH7``): possibly a condition this build does not classify. Names that
#: differ in one are never combined, whatever else was confirmed.
_CONDITION_LIKE_TOKEN = re.compile(r"^[-+]?\d+(?:p\d+)?[a-z%]+$|^[-+]?\d+p\d+$|^ph\d", re.IGNORECASE)
_DECIMAL_POINT = re.compile(r"(?<=\d)\.(?=\d)")
#: A whole number written beside its unit or label as a separate token (``05_mM``, ``25_C``, ``E_1``,
#: ``pH_7``) states a quantity too. These lists only ever BLOCK a combination (fail closed): a word
#: missing from them leaves such a pair to the scientist's sample confirmation, never to a token shape.
_UNIT_WORDS = frozenset({"v", "mv", "k", "c", "f", "h", "hr", "hrs", "min", "mins", "s", "sec", "m", "mm", "um", "nm", "mg",
                         "ug", "g", "wt", "rpm", "cycle", "cycles", "ma", "ua", "bar", "mbar", "torr", "ev", "kev", "ph"})
_LABEL_WORDS = frozenset({"ph", "e", "t", "temp", "v", "i", "u"})
_NEVER_COMBINED = (": runs whose files state different samples or conditions are never combined into one record (it would "
                   "be wrong). Keep them as separate records — confirm each group on its own: ")


def _cmds(commands: Sequence[str]) -> str:
    return "; ".join(f"`{c}`" for c in commands)


def _merge_blockers(bundle: Mapping, payload: Mapping, holders: Sequence[Mapping], combined: Mapping) -> list[str]:
    """Why ``holders`` must NOT be combined for a merge decision (the reasons of :func:`_merge_blocker_details`)."""
    return [reason for reason, _ in _merge_blocker_details(bundle, payload, holders, combined)]


def _merge_blocker_details(bundle: Mapping, payload: Mapping, holders: Sequence[Mapping], combined: Mapping) -> list[tuple[str, list[str]]]:
    """``(reason, next commands)`` for each reason ``holders`` must NOT be combined for a merge decision —
    empty only when nothing the import read or a scientist confirmed tells them apart (FAIL CLOSED, DEC-91):

    * every basis reading agrees (value and kind; the name stem aside), and the independent condition
      check (:func:`grouping.condition_violations`) finds only the names — otherwise they were measured
      under different conditions and are NEVER combined;
    * the file names agree once the tokens a scientist declared run counters (``set_counter_positions``,
      ``last`` included) and repeat markers (``again``, ``rep2`` …, :func:`_merge_name_tokens`) are left
      out — or, where they still differ, the scientist confirmed the same sample (:data:`MERGE_SAMPLE_PATH`)
      for every run and no differing token states a quantity (:data:`_CONDITION_LIKE_TOKEN`). A token's
      SHAPE alone never makes it a counter (DEC-91, third review): decimals split on ".", unit words and
      unitless values all looked like counters;
    * no confirmed, eligible run-level answer differs.

    Every reason names the commands that move the merge on, and each one, followed, does (tested): a
    counter answer or the sample confirmation where those apply, else keeping the groups apart."""
    from . import grouping as G

    keep_apart = [f'isaac bundle decide <bundle_dir> --target {h["group_id"]} --decision confirm --by "<your name>"' for h in holders]
    never: list[str] = []
    differing, unknown = [], []
    for part in sorted({p for h in holders for p in (h.get("basis") or {})}):
        vals = [(h.get("basis") or {}).get(part) for h in holders]
        if not all(isinstance(v, Mapping) or v is None for v in vals):
            if len({_reading_core(v) for v in vals}) > 1:
                differing.append(part)
            continue
        for key in sorted({k for v in vals for k in (v or {})}):
            if (part, key) in _MERGE_NAME_ONLY_BASIS:
                continue
            if len({_reading_core((v or {}).get(key)) for v in vals}) > 1:
                # a key this build does not classify is no condition it read: it is what a merge decides
                (unknown if part == "unclassified" else differing).append((part, key))
    differing = [f"{part}.{key}" for part, key in differing]
    if differing:
        never.append(f"the files state different {', '.join(differing)} for them")
    viol = G.condition_violations(bundle, {**payload, "record_groups": [combined]})
    other = sorted({v["key"] for v in viol if v["key"] not in _MERGE_NAME_ONLY_VIOLATIONS})
    if other:
        never.append(f"they were measured under different conditions ({', '.join(other)})")
    stems = _merge_stems(bundle, holders)
    declared = list(counter_positions(bundle) or ())
    kept = [_merge_name_tokens(x, declared) for x in stems]
    sample, sample_conflict = _confirmed_sample(bundle, holders)
    names_reason = unknown_reason = None
    if len({tuple(t for _, t, _ in k) for k in kept}) > 1:
        stated = _stated_quantities(stems)
        if stated:
            never.append(f"their file names state different conditions ({' / '.join(stated)})")
        elif sample is None:
            names_reason = _names_differ(bundle, kept, stems, declared, holders, sample_conflict)
    # An unclassified reading read off the file names (``unknown_token``, ``new_spot`` …) is the names'
    # business, settled above; one from elsewhere is settled only by the same confirmed sample.
    in_names = {t.casefold() for x in stems for t in G._stem_tokens(x)}
    off_names = [f"{part}.{key}" for part, key in unknown
                 if not all(_name_literals(((h.get("basis") or {}).get(part) or {}).get(key), in_names) for h in holders)]
    if off_names and sample is None:
        steps = [] if sample_conflict else _sample_commands(bundle, holders)
        unknown_reason = (f"the files state different {', '.join(off_names)} for them, which this build does not classify"
                          + (" — if these runs measured the same sample, confirm it for each run, with the same name each time: "
                             + _cmds(steps) if steps else ""), steps)
    out: list[tuple[str, list[str]]] = [(r + _NEVER_COMBINED + _cmds(keep_apart), keep_apart) for r in never]
    for text, steps in [x for x in (names_reason, unknown_reason) if x is not None]:
        if never:  # a counter or sample answer cannot combine runs whose conditions differ: none is offered
            out.append((text.split(" — ")[0], []))
            continue
        if steps:
            out.append((text + "; then regroup (`isaac bundle group <bundle_dir> --regroup`), which applies the merge", steps))
        else:
            out.append((text + _NEVER_NAMES + _cmds(keep_apart), keep_apart))
    answers = _confirmed_run_answers(bundle, {r for h in holders for r in h.get("member_run_ids") or ()})
    diff_answers = sorted(path for path, vals in answers.items() if len(vals) > 1)
    if diff_answers:
        out.append((f"confirmed answers for their runs differ ({', '.join(diff_answers)}); if one is wrong, correct it, else keep "
                    "them as separate records — confirm each group on its own: " + _cmds(keep_apart), keep_apart))
    return out


_NEVER_NAMES = ("; nothing recorded can say they are one measurement, so keep them as separate records — confirm each group "
                "on its own: ")


def _stated_quantities(stems: Sequence[str]) -> list[str]:
    """The file-name tokens that differ between ``stems`` AND state a quantity: a number with its unit
    (:data:`_CONDITION_LIKE_TOKEN`, a decimal kept whole), or a whole number beside a unit or label word
    (:data:`_UNIT_WORDS`, :data:`_LABEL_WORDS`), shown with that word."""
    from . import grouping as G

    lists = [[t for t in G._stem_tokens(_DECIMAL_POINT.sub("p", x)) if not G._REPEAT_TOKEN.match(t)] for x in stems]
    sets = [set(t) for t in lists]
    differ = set().union(*sets) - set.intersection(*sets)
    out = set()
    for toks in lists:
        for j, t in enumerate(toks):
            if t not in differ:
                continue
            if _CONDITION_LIKE_TOKEN.match(t):
                out.add(t)
            elif t.isdigit():
                nxt = toks[j + 1] if j + 1 < len(toks) else ""
                prev = toks[j - 1] if j else ""
                if nxt.casefold() in _UNIT_WORDS:
                    out.add(f"{t} {nxt}")
                elif prev.casefold() in _LABEL_WORDS:
                    out.add(f"{prev} {t}")
    return sorted(out)


def _name_literals(entry: Any, tokens: set[str]) -> bool:
    """Is this basis reading's value nothing but file-name tokens (``tokens``, casefolded)? Absent counts."""
    if entry is None:
        return True
    v = entry.get("value") if isinstance(entry, Mapping) else None
    vals = v if isinstance(v, list) else [v]
    return all(isinstance(x, str) and all(t.casefold() in tokens for t in x.replace("_", " ").split()) for x in vals)


def _merge_name_tokens(stem: str, declared: Sequence[int]) -> list[tuple[int, str, bool]]:
    """``(1-based position, token, is the last token)`` of each file-name token a merge compares: every
    token but a repeat marker (and the number right after one, ``again_2``) and a digit token at a
    position the scientist declared a run counter (``grouping.LAST_POSITION``: the last token)."""
    from . import grouping as G

    toks = G._stem_tokens(stem)
    positions = {int(x) for x in declared}
    out = []
    for i, t in enumerate(toks):
        if G._REPEAT_TOKEN.match(t) or (t.isdigit() and i > 0 and G._REPEAT_TOKEN.match(toks[i - 1])):
            continue
        if t.isdigit() and ((i + 1) in positions or (G.LAST_POSITION in positions and i == len(toks) - 1)):
            continue
        out.append((i + 1, t, i == len(toks) - 1))
    return out


def _names_differ(bundle: Mapping, kept: Sequence[Sequence[tuple]], stems: Sequence[str], declared: Sequence[int],
                  holders: Sequence[Mapping], sample_conflict: bool) -> tuple[str, list[str]]:
    """The reason file names keep a merge apart, and the commands that would let it through: the counter
    answer when the names differ only in whole numbers at one position (or always the last token) that
    no scientist said is NOT a counter, and the sample confirmation unless a different sample is
    confirmed already. Either one, followed, combines the runs on the next regroup."""
    from . import grouping as G

    steps: list[str] = []
    if len({len(k) for k in kept}) > 1:
        text = "their file names have different tokens (" + " / ".join(sorted(set(stems))) + ")"
    else:
        cols = [i for i in range(len(kept[0])) if len({k[i][1] for k in kept}) > 1]
        text = "their file names differ " + ", ".join(
            f"at token {kept[0][i][0]} ({' / '.join(sorted({k[i][1] for k in kept}))})" for i in cols)
        new: set[int] = set()
        said_not = set(B.not_counter_positions(bundle))
        for i in cols:
            col = [k[i] for k in kept]
            if not all(t.isdigit() for _, t, _ in col):
                new = set()
                break
            if all(last for _, _, last in col) and not ({p for p, _, _ in col} & said_not):
                new.add(G.LAST_POSITION)
            elif len({p for p, _, _ in col}) == 1 and col[0][0] not in said_not:
                new.add(col[0][0])
            else:
                new = set()
                break
        positions = sorted(set(declared) | new, key=lambda p: (p == G.LAST_POSITION, p))
        if new and len(positions) <= MAX_COUNTER_POSITIONS:
            shown = ",".join("last" if p == G.LAST_POSITION else str(p) for p in positions)
            steps.append(f'isaac bundle decide <bundle_dir> --target experiment --decision set_counter_positions --positions {shown} --by "<your name>"')
            text += (" — if that number counts runs or acquisitions in EVERY file name of this beamtime, say so (it applies to "
                     "the whole beamtime): " + _cmds(steps))
    sample_steps = [] if sample_conflict else _sample_commands(bundle, holders)
    if sample_steps:
        text += (("; or, " if steps else " — ") + "if these runs measured the same sample, confirm it for each run, "
                 "with the same name each time: " + _cmds(sample_steps))
    return text, steps + sample_steps


def _confirmed_sample(bundle: Mapping, holders: Sequence[Mapping]) -> tuple[Any, bool]:
    """``(value, conflict)``: the ONE sample (:data:`MERGE_SAMPLE_PATH`) a scientist confirmed for every
    measurement run of ``holders`` (else ``None``), and whether different ones are confirmed."""
    run_id_of = {r["run_key"]: r.get("run_id") for r in bundle.get("runs") or ()}
    seen: set[str] = set()
    every = True
    for h in holders:
        context = set(h.get("context_run_keys") or ())
        for k in h.get("member_run_keys") or ():
            if k in context:
                continue
            vals = _confirmed_run_answers(bundle, {run_id_of.get(k)}).get(MERGE_SAMPLE_PATH) or set()
            every = every and bool(vals)
            seen |= vals
    return (json.loads(next(iter(seen))) if every and len(seen) == 1 else None), len(seen) > 1


def _sample_commands(bundle: Mapping, holders: Sequence[Mapping]) -> list[str]:
    """One ``decide`` per measurement run of ``holders`` with no confirmed sample yet, on its sample value
    (a reading, else the missing value); none when some run has neither (no command could state it)."""
    run_id_of = {r["run_key"]: r.get("run_id") for r in bundle.get("runs") or ()}
    out = []
    for h in holders:
        context = set(h.get("context_run_keys") or ())
        for k in h.get("member_run_keys") or ():
            rid = run_id_of.get(k)
            if k in context or _confirmed_run_answers(bundle, {rid}).get(MERGE_SAMPLE_PATH):
                continue
            target = next((c["candidate_id"] for c in bundle.get("candidates") or ()
                           if c.get("run_id") == rid and c.get("target_field_path") == MERGE_SAMPLE_PATH), None)
            target = target or next((m["value_id"] for m in bundle.get("missing_values") or ()
                                     if m.get("run_id") == rid and m.get("target_field_path") == MERGE_SAMPLE_PATH), None)
            if target is None:
                return []
            out.append(f'isaac bundle decide <bundle_dir> --target {target} --decision correct --value "<the sample>" --by "<your name>"')
    return out


def _merge_stems(bundle: Mapping, groups: Sequence[Mapping]) -> list[str]:
    runs = {r["run_key"]: r for r in bundle.get("runs") or ()}
    context = {k for g in groups for k in g.get("context_run_keys") or ()}
    return [runs[k].get("stem") or "" for g in groups for k in g.get("member_run_keys") or () if k in runs and k not in context]


def _confirmed_run_answers(bundle: Mapping, run_ids: set) -> dict[str, set[str]]:
    """``path -> distinct values`` of every scientist-confirmed, ELIGIBLE run-level value of these runs
    (an answer to a missing value, or a confirmed or corrected reading)."""
    decision_of = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    out: dict[str, set[str]] = {}
    for m in bundle.get("missing_values") or ():
        if m.get("run_id") in run_ids and m.get("value_state") == B.STATE_SCIENTIST_CONFIRMED \
                and (m.get("eligibility_for_official_record") or {}).get("eligible"):
            v = B.final_value(None, decision_of.get(("missing_value", m["value_id"])))
            out.setdefault(m["target_field_path"], set()).add(json.dumps(v, sort_keys=True))
    for c in bundle.get("candidates") or ():
        if c.get("run_id") in run_ids and c.get("target_field_path") and c.get("value_state") == B.STATE_SCIENTIST_CONFIRMED \
                and (c.get("eligibility_for_official_record") or {}).get("eligible"):
            v = B.final_value(c.get("value"), B.candidate_decision(bundle, c, decision_of), c.get("readings"))
            out.setdefault(c["target_field_path"], set()).add(json.dumps(v, sort_keys=True))
    return out


def _combine_for_merge(holders: Sequence[Mapping], decision: Mapping, merged_group_id: str, exp_key: str) -> dict:
    """ONE proposed group holding every run of ``holders`` (the fresh groups now holding a merge
    decision's runs), in their order. Its id is new (the runs plus the decision id), so it is never
    mistaken for a group the rule proposed. What the holders agree on is kept in its basis; a key they
    differ on is left out of it and named in ``merged_by_decision.basis_keys_dropped``."""
    from . import grouping as G

    members = [k for h in holders for k in h.get("member_run_keys") or ()]
    combined = {k: v for k, v in holders[0].items() if k not in ("reproposed_after_group_id",)}
    basis: dict = {}
    dropped: list[str] = []
    for part, first in (holders[0].get("basis") or {}).items():
        if not isinstance(first, Mapping):
            same = all((h.get("basis") or {}).get(part) == first for h in holders)
            basis[part] = first if same else None
            if not same:
                dropped.append(part)
            continue
        if not all(isinstance((h.get("basis") or {}).get(part), Mapping) for h in holders):
            basis[part] = first if all(_reading_core((h.get("basis") or {}).get(part)) == _reading_core(first) for h in holders) else {}
            if basis[part] != first:
                dropped.append(part)
            continue
        keys = set().union(*[set(((h.get("basis") or {}).get(part) or {})) for h in holders])
        basis[part] = {}
        for k in sorted(keys):
            vals = [((h.get("basis") or {}).get(part) or {}).get(k) for h in holders]
            # M2: compared on what the reading SAYS; the evidence ids (per run) are united, never compared
            if all(_reading_core(v) == _reading_core(vals[0]) for v in vals):
                kept = copy.deepcopy(vals[0])
                if isinstance(kept, dict) and any(isinstance(v, Mapping) and "candidate_ids" in v for v in vals):
                    kept["candidate_ids"] = list(dict.fromkeys(c for v in vals for c in (v or {}).get("candidate_ids") or ()))
                basis[part][k] = kept
            else:
                dropped.append(f"{part}.{k}")
    combined.update({
        "group_id": G.group_id_for(exp_key, members + [f"merged-by:{decision['decision_id']}"]),
        "member_run_keys": members,
        "member_run_ids": [r for h in holders for r in h.get("member_run_ids") or ()],
        "context_run_keys": [r for h in holders for r in h.get("context_run_keys") or ()],
        "engine_reading_issues": [i for h in holders for i in h.get("engine_reading_issues") or ()],
        "merged_despite_engine_reading": [i for h in holders for i in h.get("merged_despite_engine_reading") or ()],
        "basis": basis,
        "split_reasons": [],
        "questions": [],
        "merge_candidate_ids": [],
        "flags": sorted({f for h in holders for f in h.get("flags") or () if f != "reproposed_after_merge_decision"})
        + ["merged_by_scientist_decision"],
        "status": "proposed",
        "condition_violations": [],
        "merged_by_decision": {
            "decision_id": decision["decision_id"],
            "merged_group_id": merged_group_id,
            "merge_with": list(decision.get("merge_with") or []),
            "decided_by": (decision.get("decided_by") or {}).get("name"),
            "from_groups": [h["group_id"] for h in holders],
            "basis_keys_dropped": dropped,
            "statement": "proposed as one group because a scientist decided to merge these runs' groups; "
                         "only a confirm decision makes it a record",
        },
    })
    return combined


def process(
    bundle_dir: Path,
    *,
    source: str | None = None,
    group_ids: Sequence[str] | None = None,
    athena: bool = True,
    params_file: str | None = None,
) -> dict:
    """Run the processing protocol (LOCAL-P's ``processing.cli_entry.run_process``) and
    store its ``processing_results[]``. A result a scientist already decided is KEPT;
    nothing here approves anything — every new result is undecided.

    ONLY LIVE GROUPS (proposed or confirmed) are processed unless ``group_ids`` names others: a
    rejected, merged or split group cannot become a record, so processing it only added results
    and QC verdicts nobody can use (a real BL4-3 bundle: 26 rejected alignment groups among 62
    results). Their earlier results, and every decision on them, are kept as they were, and the
    reply counts them apart (``not_live_groups``)."""
    try:
        from .processing import cli_entry
    except ImportError as exc:
        raise MutationRefused(f"processing not installed: {exc}", code=2) from exc
    bundle_dir = Path(bundle_dir)
    current = load(bundle_dir)
    refusal = B.legacy_refusal(current)
    if refusal:  # R-6: never process groups that may hold the scientists' processed outputs
        raise MutationRefused(refusal, code=2)
    if not current.get("record_groups"):
        raise MutationRefused("No record groups yet: run `isaac bundle group` first.", code=2)
    not_live = [] if group_ids else [g for g in current["record_groups"] if g.get("status") not in B.LIVE_GROUP_STATUSES]
    if not_live and len(not_live) == len(current["record_groups"]):
        raise MutationRefused(
            f"No live record group to process: all {len(not_live)} groups are rejected, merged or split, so none can "
            "become a record. Nothing was processed. Name one with `--group <id>` to process it anyway, or regroup "
            "(`isaac bundle group <bundle_dir> --regroup`).", code=2)
    skip = [g["group_id"] for g in not_live]
    payload = cli_entry.run_process(
        bundle_dir,
        source_root=source,
        group_ids=group_ids,
        athena=athena,
        params_file=params_file,
        bundle=current,
        calibration_approvals=calibration_approvals(current),
        skip_group_ids=skip,
    )
    if payload.get("status") == "processing_unavailable":
        missing = ", ".join(payload.get("missing") or []) or "its dependencies"
        raise MutationRefused(f"processing not installed (processing_unavailable): missing {missing}. Nothing was "
                              "processed. Install it with `scripts/setup_isaac_local.sh --with-processing` (from the "
                              "ISAAC folder), then run `isaac process` again.", code=2)
    produced = [dict(r) for r in payload.get("processing_results") or ()]

    def change(bundle):
        known = {g["group_id"] for g in bundle.get("record_groups") or ()}
        # only a decision that sets a result's STATE freezes it against re-processing (L3): a
        # select_athena_version answer keys on the result id and its listed version ids, so it applies
        # to the fresh result of the same id as it did to the old one
        decided = {d["target"]["id"] for d in bundle.get("scientist_decisions") or ()
                   if d["target"]["kind"] == "processing_result" and d.get("decision") in B.PROCESSING_STATE_DECISIONS}
        # ... unless the fresh result (same id) holds no version with the provenance the latest selection
        # recorded (project file, Athena group, data hash): then the old result is kept, so the selection
        # never points at nothing — or, after a renumbering, at a different curve
        fresh_by_id = {B.processing_id(r): r for r in produced}
        for r in bundle.get("processing_results") or ():
            d = B.latest_athena_selection(bundle, r)
            pid = B.processing_id(r)
            if d is not None and (pid not in fresh_by_id or B.athena_resolve(fresh_by_id[pid], d) is None):
                decided.add(pid)
        superseded = {g["group_id"] for g in bundle.get("superseded_record_groups") or ()}
        # `--group` processes ONLY those groups: every other group's results (decided or not) are kept as they are
        untouched = set() if not group_ids else {g for g in {r.get("group_id") for r in bundle.get("processing_results") or ()}
                                                     if g not in set(group_ids)}
        # a group that is no longer live was not processed: its results stay exactly as they were
        untouched |= set(skip)
        # decided results are kept, and so is every result of a SUPERSEDED group (never deleted)
        keep = [r for r in bundle.get("processing_results") or ()
                if B.processing_id(r) in decided or r.get("group_id") in superseded or r.get("group_id") in untouched]
        kept = {B.processing_id(r) for r in keep}
        fresh = []
        for r in produced:
            if r.get("group_id") not in known or B.processing_id(r) in kept:
                continue
            if r.get("state") not in B.PROCESSING_UNDECIDED_STATES:
                r["state"] = B.STATE_NEEDS_REVIEW
            fresh.append(r)
        bundle["processing_results"] = keep + fresh
        kept_decided = sum(B.processing_id(r) in decided or r.get("group_id") in superseded for r in keep)
        out = {
            "processing_results": len(bundle["processing_results"]),
            "kept_decided": kept_decided,
            "new": len(fresh),
            "summary": payload.get("summary"),
            "statement": "Draft, unreviewed processing. Nothing goes into a record until a scientist approves it.",
        }
        if group_ids:
            # the groups NOT named keep their results as stored (`new` counts only the named groups')
            out["kept_other_groups"] = len(keep) - kept_decided
        if not_live:
            by_status: dict[str, int] = {}
            for g in not_live:
                by_status[g.get("status")] = by_status.get(g.get("status"), 0) + 1
            held = sum(1 for r in keep if r.get("group_id") in set(skip))
            said = ", ".join(f"{n} {k}" for k, n in sorted(by_status.items()))
            line = (f"{len(not_live)} record group(s) not processed because they are no longer live ({said}): their "
                    f"{held} earlier result(s) and any decision on them are kept as they were. `--group <id>` processes one anyway.")
            out["not_live_groups"] = {"groups": len(not_live), "by_status": dict(sorted(by_status.items())),
                                      "results_kept": held, "statement": line}
            if isinstance(out.get("summary"), Mapping):
                out["summary"] = {**out["summary"], "lines": [*(out["summary"].get("lines") or ()), line]}
        return out

    return mutate(bundle_dir, change)


def qc_status_vocabulary() -> list[str]:
    """``measurement.qc.status`` values from the PINNED upstream vocabulary when the
    validator is installed, else from the vendored schema's enum."""
    from . import portal as P

    where = P.locate()
    if where.get("available"):
        try:
            vocab = json.loads((Path(where["dir"]) / "data" / "vocabulary.json").read_text(encoding="utf-8"))
            values = vocab["Measurement"]["measurement.qc.status"]["values"]
            if isinstance(values, list) and values:
                return [str(v) for v in values]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    node = B._schema_node("measurement.qc.status") or {}
    return [str(v) for v in node.get("enum") or ()]


def calibration_approvals(bundle: Mapping) -> dict:
    """``{group_id: {element, edge, decided_by, decision_id}}`` from the LATEST
    ``approve_calibration`` decision per group — the only thing that lets processing apply
    a calibration shift. A decision always has a named decider (``--by`` is required)."""
    out: dict = {}
    for d in bundle.get("scientist_decisions") or ():
        if d.get("decision") == "approve_calibration" and d["target"]["kind"] == "record_group":
            out[d["target"]["id"]] = {
                "element": d["element"],
                "edge": d["edge"],
                "decided_by": (d.get("decided_by") or {}).get("name"),
                "decision_id": d["decision_id"],
            }
    return out


def counter_positions(bundle: Mapping) -> list[int] | None:
    """The scientist's LATEST ``set_counter_positions`` answer (every earlier one is kept in
    ``scientist_decisions``; the last supersedes), or ``None``. For the grouping step."""
    latest = None
    for d in bundle.get("scientist_decisions") or ():
        if (
            d.get("decision") == "set_counter_positions"
            and d["target"] == {"kind": "experiment", "id": "experiment"}
            and B.decider_name_problem((d.get("decided_by") or {}).get("name")) is None
        ):
            latest = list(d.get("positions") or [])
    return latest
