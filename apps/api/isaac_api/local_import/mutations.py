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
import math
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
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
#: The categories that count as HIGH-VALUE for the skill's "I independently read N of M high-value items":
#: the six named ones (``required_by_record``, ``run_association`` and ``herfd_signal_choice`` are listed too
#: but are not high-value). ``crosscheck-plan`` reports ``high_value_total`` over them.
HIGH_VALUE_CATEGORIES: tuple[str, ...] = tuple(name for name, _, _ in CROSSCHECK_CATEGORIES)
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


class OffListRefused(MutationRefused):
    """A ``confirm``/``correct`` refused ONLY because its value is not on the field's allowed list
    (:func:`bundle.off_list_only`): a word the vocabulary lacks. No decision and no value is recorded. Only with
    ``as_said`` (``decide --as-said``: the scientist says it is their own word) does the caller keep it as a
    vocabulary request (:func:`keep_vocabulary_request`) and say so; otherwise NOTHING is kept and the refusal says
    how to keep it (:data:`AS_SAID_HINT`). ``problem``: the refusal's own sentence, without what was or was not kept."""

    def __init__(self, message: str, *, field_path: str, term: str, code: int = 2, problem: str | None = None):
        super().__init__(message, code=code)
        self.field_path = field_path
        self.term = term
        self.problem = problem if problem is not None else message


#: c10-d H1: an off-list answer is kept as a vocabulary request ONLY when the scientist says it is their own word
#: (``--as-said``); a value Claude tries while working out a mapping is never attributed to the scientist.
AS_SAID_HINT = ("Nothing was kept (no vocabulary request): if this is the scientist's own word, repeat with --as-said "
                "(`isaac bundle decide ... --value \"<their exact word>\" --as-said`); never for a word they did not say.")
AS_SAID_NEEDS_VALUE = ("--as-said keeps the scientist's own word given with --value; give --value \"<their exact word>\". "
                       "Nothing was recorded.")
#: c10-r: --as-said says what a scientist's ANSWER to a value is; it goes with nothing else.
AS_SAID_ONLY_AN_ANSWER = ("--as-said goes only with --decision confirm or correct and --value \"<their exact word>\" (it keeps "
                          "the scientist's own word when the field's list lacks it). Nothing was recorded.")
#: c10-r: --as-said on a value the field's list holds keeps nothing: the value is recorded as the answer, as ever.
AS_SAID_ON_LIST = ("--as-said kept nothing: the field accepts this value (it is on the field's list, or the field has "
                   "none), so it is recorded as the answer and no vocabulary request is kept.")


def _as_said_refusal(as_said: bool, decision: str, value: Any) -> str | None:
    """Why ``--as-said`` cannot go with this answer (``None`` when it can, or is not given)."""
    if not as_said:
        return None
    if value is None:
        return AS_SAID_NEEDS_VALUE
    return None if decision in ("confirm", "correct") else AS_SAID_ONLY_AN_ANSWER


def _said_on_list(result: Mapping, as_said: bool) -> Mapping:
    """``result`` with :data:`AS_SAID_ON_LIST` said when ``--as-said`` was given and the value was recorded."""
    if not as_said:
        return result
    return {**result, "statement": " ".join(x for x in (result.get("statement"), AS_SAID_ON_LIST) if x)}


def _not_kept(exc: "OffListRefused") -> "OffListRefused":
    """The refusal of an off-list answer given WITHOUT ``--as-said``: nothing is kept, and it says how to keep it."""
    return OffListRefused(f"{exc.problem} {AS_SAID_HINT}", field_path=exc.field_path, term=exc.term, code=exc.code,
                          problem=exc.problem)


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
        bundle = B.load_bundle(path)
    except B.BundleInvalid as exc:
        raise MutationRefused(f"Unreadable bundle: {exc}", code=1) from exc
    # an older build's bundle holds a beamtime-wide notes statement as a run's extracted value: held for
    # review here, in memory, so every question and template reads it as the import now gives it (c6-a)
    B.hold_beamtime_wide_statements(bundle)
    return bundle


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
    drop_dead_slots(bundle)  # an answer slot no decision names is never left behind as an empty question
    B.refresh_local_write_summaries(bundle)
    B.hold_beamtime_wide_statements(bundle)  # what the import now gives (bundle.BEAMTIME_WIDE_REASON); no format change
    bundle["format_version"] = to_version
    for key in ("record_groups", "processing_results", "exposures"):
        bundle.setdefault(key, [])
    B.refresh_questions(bundle)
    B.apply_derivations(bundle)
    # A HOLD OF A VALUE THE STORED FILE GIVES AS EXTRACTED IS NEVER SILENT (M2, c6-r): each is logged in
    # `eligibility_rederived`, read from the bundle AS STORED (under the caller's lock), and one line goes to stderr
    # once the write succeeds. Read only when this bundle holds such a value (a fresh import's are held already:
    # the stored file then gives them held, and nothing is logged).
    held_now: list = []
    if any((c.get("state_basis") or {}).get("not_proposable_reason") == B.BEAMTIME_WIDE_REASON for c in bundle["candidates"]):
        stored_h = None
        if B.bundle_path(Path(bundle_dir)).is_file():
            try:
                stored_h = B.load_bundle(Path(bundle_dir))
            except B.BundleInvalid:
                stored_h = None
        held_now = B.log_beamtime_wide_holds(bundle, stored_h, to_version=to_version)
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
    if held_now:
        print(f"isaac: {B.held_statement(len(held_now))} (an older build stored them as extracted; logged in bundle.json "
              "eligibility_rederived)", file=sys.stderr)


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
        named = _target_source_ids(kind, obj)
        if source_id is not None and named and source_id not in named:
            raise MutationRefused(
                f"--source-id {source_id} is not a source of {target_id}; its locators name "
                f"{', '.join(sorted(named))}. Use one of those, the source `excerpt` printed."
            )
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
                    merge_with: Sequence[str] | None = None, split_into: Any = None) -> None:
    allowed = B.DECISIONS_BY_KIND.get(kind)
    if allowed is None:
        raise MutationRefused(f"A {kind} cannot be decided.")
    if decision not in allowed:
        raise MutationRefused(f"`{decision}` is not a decision for a {kind}; allowed: {', '.join(sorted(allowed))}.")
    if kind == "record_group" and decision == "merge":
        problem = merge_with_problem(bundle, obj["group_id"], merge_with)
        if problem is not None:
            raise MutationRefused(f"{problem} Nothing was recorded.")
    if kind == "record_group" and decision == "split":
        # c8-s: a split makes ONE group per list, so its lists name each of the group's runs exactly once
        problem = split_into_problem(bundle, obj, split_into)
        if problem is not None:
            raise MutationRefused(f"{problem} Nothing was recorded.")
    if kind == "record_group" and decision in ("split", "defer", "merge"):
        # c8-s / c8-r: a group whose runs another live group now holds (its parts, after an earlier split) is not
        # split, deferred (made a proposal again) or merged: each would put a run in two live groups
        mine = set(obj.get("member_run_keys") or ())
        holders = [g["group_id"] for g in bundle.get("record_groups") or ()
                   if g["group_id"] != obj["group_id"] and g.get("status") in B.LIVE_GROUP_STATUSES
                   and mine & set(g.get("member_run_keys") or ())]
        if holders:
            raise MutationRefused(
                f"The runs of {obj['group_id']} are now in {', '.join(holders[:5])}; {decision} (or decide) that group "
                "instead. Nothing was recorded.")
    if kind == "record_group" and decision == "split":
        # c8-r: A SPLIT INTO GROUPS THIS BUNDLE ALREADY HOLDS (the same lists as an earlier split of this group, whose
        # parts were then rejected): a part's id is derived from its runs and this group, so it would be made twice
        from .grouping import experiment_key_of

        exp_key = experiment_key_of(bundle)
        held = {g["group_id"]: g for g in bundle.get("record_groups") or ()}
        again = [held[pid] for pid in (split_part_id(exp_key, obj, part) for part in split_into) if pid in held]
        if again:
            said = ", ".join(f"{g['group_id']} ({g.get('status')})" for g in again[:5])
            rejected = [g["group_id"] for g in again if g.get("status") == B.STATE_REJECTED]
            remedy = (f"To make a rejected part a record again, confirm it (`isaac bundle decide <bundle_dir> --target "
                      f'{rejected[0]} --decision confirm --by "<your name>"`'
                      + (f", and the same for {', '.join(rejected[1:4])}" if len(rejected) > 1 else "") + ")"
                      if rejected else "Decide those groups instead")
            raise MutationRefused(
                f"This split of {obj['group_id']} would make {said}, which an earlier split of it with the same lists "
                f"already made: a part is the same group whenever it holds the same runs. {remedy}; or split "
                f"{obj['group_id']} into other lists. Nothing was recorded.")
    if kind == "processing_result" and B.processing_not_applicable(obj):
        app = obj.get("applicability") or {}
        raise MutationRefused(
            f"{B.processing_id(obj)} is not a curve: the processing protocol does not apply to this group "
            f"({app.get('reason_code')}: {B.NO_PROTOCOL_COVERS}). There is nothing to {decision}, and no QC verdict was given."
        )
    if kind == "processing_result" and decision == "approve" and not (obj.get("outputs") or {}).get("files"):
        raise MutationRefused(no_curve_refusal(obj))
    if kind == "processing_result" and decision == "approve" and unusable_curve_reasons(obj):
        # c8-a: a curve whose QC says it is NOT A USABLE SPECTRUM is never approved, whatever QC status is offered
        raise MutationRefused(unusable_curve_refusal(obj))
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
        listed_v = next(v for v in obj["athena_versions"] if v.get("version_id") == value)
        mine = B.athena_version_identity(listed_v)
        if not B._athena_same_version(listed_v, mine):
            # c10-r: a set listed before its identity named its members; selecting it would resolve to nothing
            raise MutationRefused(
                f"{value!r} is a set of per-scan Athena groups listed by an older ISAAC, whose identity does not name "
                "its members. Run `isaac process` again, then choose among the versions it lists. Nothing was recorded."
            )
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
        path, effective, _label = _decided_value_target(bundle, kind, obj, decision, value) or (None, None, None)
        if B.off_list_only(path, effective):
            raise OffListRefused(problem, field_path=path, term=effective)
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


#: The QC ``fail`` reasons (:func:`processing.core.qc_verdict`) that say the curve is NOT A USABLE SPECTRUM: the
#: edge step does not describe the data (``edge_step_implausible``), no edge stands above the pre-edge scatter
#: (``no_edge``), or the normalised level after the edge is far from 1 (``post_edge_not_at_1``). ``decide`` refuses
#: to approve a result failing for one of them and ``validate`` never offers that approval; any other ``fail``
#: (e.g. ``too_few_points``) stays the scientist's call, approved only with the QC status they state.
UNUSABLE_CURVE_REASONS = ("edge_step_implausible", "no_edge", "post_edge_not_at_1")


def unusable_curve_reasons(result: Mapping) -> list[str]:
    """The reasons of :data:`UNUSABLE_CURVE_REASONS` a result's QC ``fail`` names, in its order (``[]`` when its
    verdict is not ``fail`` or names none of them)."""
    qc = result.get("qc") or {}
    if qc.get("verdict") != "fail":
        return []
    return [r for r in qc.get("reasons") or () if r in UNUSABLE_CURVE_REASONS]


def unusable_curve_refusal(result: Mapping) -> str:
    """Why approving a result whose QC fails for a reason of :data:`UNUSABLE_CURVE_REASONS` is refused, in the
    result's own QC sentences, and the real options (the same three as :func:`no_curve_refusal`)."""
    pid, gid = B.processing_id(result), result.get("group_id")
    reasons = unusable_curve_reasons(result)
    statements = (result.get("qc") or {}).get("statements") or {}
    said = " ".join(str(statements[r]) for r in reasons if statements.get(r))
    return (
        f"{pid} cannot be approved: its QC fails {', '.join(reasons)}, so the curve is not a usable spectrum"
        + (f" ({said})" if said else "") + ". An approval would put a QC status into the record for a curve that "
        "does not describe the data, whatever status is given. Re-running `isaac process` with the same parameters "
        "gives the same result. The options: "
        f'reject it (`isaac bundle decide <bundle_dir> --target {pid} --decision reject --by "<your name>"`); '
        f"or mark it needs_changes (`--target {pid} --decision needs_changes`) and re-process the group with a "
        f"setting the scientist chooses ({reprocess_command(gid)}), which adds a new result to review; "
        "or leave the group out of the records "
        f'(`isaac bundle decide <bundle_dir> --target {gid} --decision reject --by "<your name>"`). Nothing was recorded.'
    )


#: The comparison flag an Athena curve carries when the scientist used fewer scans than ISAAC merged.
SCAN_SUBSET_FLAG = "scientist_selected_subset_of_scans"


def scan_subset_note(bundle: Mapping, result: Mapping) -> str | None:
    """One plain line when ``result`` is the scientist's Athena curve and it used only some of the group's
    scans (``scientist_selected_subset_of_scans``), else ``None``. The scan numbers come from the Athena label
    (``comparison.athena_scan_selection``); the total is what ISAAC's result of the same run merged.

    c11-r: in a one-run group the sentence is worked out from the scan numbers NOW, never from the stored flag alone
    (an older build stored it from scans counted by position): when every number is known and the label names
    exactly the scans ISAAC merged, there is nothing to say (``None``); when the numbers are not known, a neutral
    sentence that claims neither "only part of the merge" nor "a scan ISAAC did not merge"."""
    comparison = result.get("comparison") or {}
    if result.get("source") != "scientist_athena":
        return None
    flagged = SCAN_SUBSET_FLAG in (comparison.get("flags") or ())
    covers = comparison.get("athena_covers") or {}
    chosen = [str(n) for n in comparison.get("athena_scan_selection") or covers.get("scans") or ()]
    sibling = next((r for r in bundle.get("processing_results") or ()
                    if r.get("group_id") == result.get("group_id") and r.get("source") == "isaac_protocol"
                    and r.get("run_id") == result.get("run_id")), None)
    total = len([i for i in (sibling or {}).get("inputs") or () if not i.get("skip_reason")])
    gid = result.get("group_id")
    if covers.get("runs"):
        if not flagged:
            return None
        # c8-a: a MERGED group's scans are numbered per run, so the run is named, and how many of the merge they are
        runs = list(covers["runs"])
        total = total or int(covers.get("isaac_scans_merged") or 0)
        named = f"run{'s' if len(runs) > 1 else ''} {', '.join(runs)}"
        over = f" over runs {', '.join(covers.get('group_runs') or ())}" if covers.get("group_runs") else ""
        of = f" — {len(chosen)} of the {total} scan(s) ISAAC merged{over}" if chosen and total else (
            f" — of the {total} scan(s) ISAAC merged{over}" if total else "")
        which = f"scans {', '.join(chosen)} of {named}{of}" if chosen else f"the scans of {named}{of}"
        return (f"The scientist's Athena curve for group {gid} uses only {which} "
                f"({SCAN_SUBSET_FLAG}): its E0 and curve describe those scans, not the full merge.")
    inputs = list((sibling or {}).get("inputs") or ())
    if not inputs and not flagged:
        return None  # no ISAAC result of the same run to compare with, and nothing stored to say
    # c11-a/c11-r: a run kept as one file per scan states no scan index (its inputs hold `scan: None`): each scan's
    # number is read from its file name (bundle.input_scan_numbers), never counted by position. A scan is said merged,
    # not merged or absent ONLY when every number is known.
    run_of = {s.get("source_id"): r.get("run_key") for r in bundle.get("runs") or () for s in r.get("scans") or ()}
    numbers, basis = B.input_scan_numbers(inputs, run_of)
    known = B.all_scan_numbers_known(numbers)
    of = f" of the {total} scan(s) ISAAC merged" if total else ""
    if chosen and not known:
        # the numbers are not known, so neither "only part of the merge" nor "a scan ISAAC did not merge" is said
        return (f"The scientist's Athena curve for group {gid} uses scans {', '.join(chosen)}{of} "
                f"({SCAN_SUBSET_FLAG}): its E0 and curve describe those scans, which may not be ISAAC's merge.")
    if not chosen:
        return (f"The scientist's Athena curve for group {gid} uses only a subset of the scans{of} ({SCAN_SUBSET_FLAG}): "
                "its E0 and curve describe those scans, not the full merge.") if flagged else None
    merged = {n for n, i in zip(numbers, inputs) if not i.get("skip_reason")}
    how = ""
    if basis == B.SCAN_NUMBERS_FROM_FILE_NAME:
        several = len({run_of.get(i.get("source_id")) for i in inputs}) > 1
        how = (f" (the run{'s state' if several else ' states'} no scan index; each scan's number is read from its file "
               "name)")
    unlisted = [n for n in chosen if not (n.isdigit() and int(n) in set(numbers))]
    if unlisted:
        # a number the run does not have is not "a scan ISAAC did not merge": which scans it means is unknown
        return (f"The scientist's Athena curve for group {gid} names scan(s) {', '.join(unlisted)}, which the "
                f"run's {len(numbers)} listed scans do not include{how}, so which of the {total} scan(s) ISAAC "
                f"merged it used is not known ({SCAN_SUBSET_FLAG}): its E0 and curve describe its own scans, "
                "not necessarily ISAAC's merge.")
    extra = [n for n in chosen if int(n) not in merged]
    if extra:
        # c10-r: it includes a scan ISAAC did not merge: a DIFFERENT set of scans, never "only" part of the merge
        return (f"The scientist's Athena curve for group {gid} uses a different set of scans "
                f"({', '.join(chosen)}) from the {total} scan(s) ISAAC merged, including scan(s) {', '.join(extra)} "
                f"that ISAAC did not merge{how} ({SCAN_SUBSET_FLAG}): its E0 and curve describe its own scans, "
                "not ISAAC's merge.")
    if {int(n) for n in chosen} == merged:
        return None  # exactly the scans ISAAC merged: not a subset, whatever an older build stored
    return (f"The scientist's Athena curve for group {gid} uses only scans {', '.join(chosen)}{of}{how} "
            f"({SCAN_SUBSET_FLAG}): its E0 and curve describe those scans, not the full merge.")


def approval_files(result: Mapping) -> list[dict]:
    """The files an approval of ``result`` binds to (role, path and hash of each output file)."""
    return [{"role": f.get("role"), "relative_path": f.get("relative_path"), "sha256": f.get("sha256")}
            for f in (result.get("outputs") or {}).get("files") or ()]


def approval_is_stale(approval: Mapping | None, result: Mapping) -> bool:
    """``True`` when ``approval`` binds to other files than ``result`` now lists: the record composer
    uses nothing from it (records.py). An approval an older build recorded with no binding is not stale."""
    bound = (approval or {}).get("approved_files")
    return bound is not None and json.dumps(bound, sort_keys=True) != json.dumps(approval_files(result), sort_keys=True)


def approved_sibling_problem(bundle: Mapping, obj: Mapping, planned: Sequence[Mapping] = ()) -> str | None:
    """Why approving the processing result ``obj`` is refused because ANOTHER result of its group is already
    approved (or is approved in the same call, ``planned``), else ``None``.

    A record uses exactly one processing result. With two approved, the composer used neither, and the group
    read as having no processing result at all. The newer approval does NOT silently replace the older one: the
    older is a person's signed statement (with its QC status), so the scientist withdraws it themselves."""
    pid, gid = B.processing_id(obj), obj.get("group_id")
    same_call = [B.processing_id(r) for r in planned if r.get("group_id") == gid and B.processing_id(r) != pid]
    if same_call:
        return (f"{same_call[0]} and {pid} are both results of group {gid}, and a record uses exactly one processing "
                "result: approve one of them. Nothing was recorded.")
    # FROM THE DECISIONS, not the stored state: a caller deciding several times on one loaded bundle (the
    # template import) has not re-derived the states in between
    state_of = B.processing_state_decisions(bundle)
    others = [r for r in bundle.get("processing_results") or ()
              if r.get("group_id") == gid and B.processing_id(r) != pid and not B.processing_not_applicable(r)
              and (state_of.get(("processing_result", B.processing_id(r))) or {}).get("decision") == "approve"]
    if not others:
        return None
    old = B.processing_id(others[0])
    notes = " ".join(n for n in (scan_subset_note(bundle, r) for r in (others[0], obj)) if n)
    if approval_is_stale(state_of.get(("processing_result", old)), others[0]):
        # "keep it (nothing more to do)" would be false: the composer uses nothing from a stale approval
        keep = (f"{old}'s approval no longer matches its files (it names other files than {old} now lists), so "
                f"no record uses it. The options: keep {old} by approving it again after reviewing its current "
                f'files (`isaac bundle decide <bundle_dir> --target {old} --decision approve --qc-status <value> '
                f'--by "<your name>"`); or withdraw its approval first — ')
    else:
        keep = f"The options: keep {old} (nothing more to do); or withdraw its approval first — "
    return (
        f"{pid} cannot be approved: {old} is already approved for group {gid}, and a record uses exactly one "
        f"processing result. {keep}"
        f'reject it (`isaac bundle decide <bundle_dir> --target {old} --decision reject --by "<your name>"`) or '
        f'defer it (`isaac bundle decide <bundle_dir> --target {old} --decision defer --by "<your name>"`) — and '
        f"then approve {pid}." + (f" {notes}" if notes else "") + " Nothing was recorded."
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


def _decided_value_target(bundle: Mapping, kind: str, obj: Mapping, decision: str,
                          value: Any) -> tuple[str | None, Any, str] | None:
    """``(field path, the value a confirm/correct would leave, the target's id)``, or ``None`` when the decision
    states no value for a field (any other decision, any other kind)."""
    if decision not in ("confirm", "correct"):
        return None
    if kind == "candidate":
        effective = B.final_value(obj.get("value"), {"decision": decision, "value": value}, obj.get("readings"))
        return obj.get("target_field_path"), effective, obj["candidate_id"]
    if kind == "missing_value":
        return obj.get("target_field_path"), value, obj["value_id"]
    if kind == "conflict":
        cand = next((c for c in bundle.get("candidates") or () if c["candidate_id"] == obj.get("candidate_id")), None)
        return (cand or {}).get("target_field_path"), value, obj["conflict_id"]
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
    target = _decided_value_target(bundle, kind, obj, decision, value)
    if target is None:
        return None
    path, effective, label = target
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
    same_conditions: bool = False,
    as_said: bool = False,
    accept_shift: float | None = None,
) -> dict:
    """Record a scientist decision for each target (ALL-OR-NOTHING), idempotently.

    Replaying the same decision for a target whose latest decision is already identical
    records nothing new. Each target is its own entry even in a bulk call, sharing a
    ``batch_id``. ``expected_version``: see :func:`mutate` (the CLI passes none). ``as_said``
    (``--as-said``): a value refused only for being off its field's list is kept as a vocabulary
    request under ``by``; without it nothing is kept (:class:`OffListRefused`).
    """
    if (refusal := _as_said_refusal(as_said, decision, value)) is not None:
        raise MutationRefused(refusal)
    params = dict(
        target_ids=target_ids, decision=decision, value=value, by=by, orcid=orcid, note=note,
        split_into=split_into, merge_with=merge_with, qc_status=qc_status, qc_note=qc_note,
        element=element, edge=edge, positions=positions, same_conditions=same_conditions,
        **({"accept_shift": accept_shift} if accept_shift is not None else {}),
    )
    _decide_arguments(**params)  # refused before the lock is taken, as always
    with locked(Path(bundle_dir)):
        _require_version(Path(bundle_dir), expected_version)
        bundle = load(bundle_dir)
        try:
            result = record_decision(bundle, **params)
        except OffListRefused as exc:
            if not as_said:
                raise _not_kept(exc) from None
            raise _keep_refused_answer(bundle_dir, bundle, exc, target_ids=target_ids, by=by, orcid=orcid, note=note,
                                       source={"kind": "decide_answer", "command": "bundle decide", "decision": decision,
                                               "question_id": None, "as_said": True}) from None
        save_bundle(bundle_dir, bundle)
        return _said_on_list(result, as_said)


# --- vocabulary requests (1.10.0) ---------------------------------------------------------------


def _decider(by: str | None, orcid: str | None) -> dict | None:
    if not by or not str(by).strip():
        return None
    return {"name": str(by).strip(), "basis": "self_reported_local_user", "identity": "local_unverified",
            "orcid_claimed": {"value": orcid, "basis": "claimed_for_credit_not_authentication"} if orcid else None}


def keep_vocabulary_request(bundle: dict, *, field_path: str, term: str, by: str | None, orcid: str | None = None,
                            targets: Sequence[tuple[str, str]] = (), run_ids: Sequence[str] = (), scope: str = "run",
                            source: Mapping, note: str | None = None) -> tuple[dict, bool]:
    """Keep a scientist's answer that its field refused ONLY because it is not on the field's allowed list
    (:func:`bundle.off_list_only`) as a VOCABULARY REQUEST: who said it, when, the field, the targets and runs,
    and where it was said. Never a decision and never a value: no record, question or eligibility reads it;
    ``bundle propose-terms`` drafts its term. ``(request, new)``: the same answer by the same person from the
    same place (field, term, targets, runs, source) is kept once and records nothing the second time, except that
    the same ``--as-said`` answer given again stamps ``reaffirmed_utc`` on the kept request (the scientist said
    their word again: ``propose-terms`` reads an allowed value given before that time as not answering it)."""
    requests = bundle.setdefault("vocabulary_requests", [])
    entry = {
        "field_path": field_path,
        "term": term,
        "requested_by": _decider(by, orcid),
        "scope": scope if scope in ("run", "experiment") else "run",
        "targets": [{"kind": k, "id": i} for k, i in dict.fromkeys((k, i) for k, i in targets)],
        "run_ids": list(dict.fromkeys(r for r in run_ids if r)),
        "source": {"kind": source["kind"], "command": source["command"],
                   **{k: source.get(k) for k in ("decision", "question_id", "file") if k in source},
                   # c10-r: kept because the scientist said it is their own word (`decide --as-said`)
                   **({"as_said": True} if source.get("as_said") is True else {}),
                   **({"cells": list(dict.fromkeys(source["cells"]))} if source.get("cells") else {})},
        "note": note.strip() if isinstance(note, str) and note.strip() else None,
    }
    if entry["source"].get("file"):
        entry["source"]["file"] = Path(str(entry["source"]["file"])).name  # a file NAME, never its folders

    def same(r: Mapping) -> bool:
        return all(r.get(k) == entry[k] for k in ("field_path", "term", "scope", "targets", "run_ids", "source", "note")) and (
            (r.get("requested_by") or {}).get("name") == (entry["requested_by"] or {}).get("name"))

    for r in requests:
        if same(r):
            if entry["source"].get("as_said") is True:
                r["reaffirmed_utc"] = now_utc()
            return r, False
    if len(requests) >= B.MAX_VOCABULARY_REQUESTS:
        raise MutationRefused(f"This bundle already keeps {B.MAX_VOCABULARY_REQUESTS} vocabulary requests; nothing more can "
                              "be kept. Run `isaac bundle propose-terms` for the ones it holds.", code=5)
    numbers = [int(str(r.get("request_id", "vr-0")).split("-", 1)[1]) for r in requests
               if re.fullmatch(r"vr-\d+", str(r.get("request_id")))]
    request = {"request_id": f"vr-{max(numbers, default=0) + 1:05d}", **entry, "requested_utc": now_utc()}
    order = ("request_id", "field_path", "term", "requested_by", "requested_utc", "scope", "targets", "run_ids", "source", "note")
    # ``reaffirmed_utc`` (optional) is added only to a request kept earlier, when the same --as-said answer is given again
    request = {k: request[k] for k in order}
    requests.append(request)
    return request, True


def vocabulary_kept_sentence(request: Mapping, new: bool, reaffirmed: bool = False) -> str:
    """What a refusal says about the answer it kept (the same words for ``decide`` and the template). ``reaffirmed``:
    the same ``--as-said`` answer was given again, and the kept request's ``reaffirmed_utc`` now says so."""
    from . import propose_terms as P

    kept = "" if new else ", kept earlier and reaffirmed now" if reaffirmed else ", kept earlier"
    said = (f"{request['term']!r} is kept as a vocabulary request; `isaac bundle propose-terms` can draft it "
            f"({request['request_id']}{kept}: not a decision and not a value; the field keeps "
            "what it has, or stays missing, until the vocabulary has the term or you answer with an allowed value).")
    same = P.equivalent_term(request["field_path"], request["term"])
    if same is not None:
        said += f" It is the same as an existing term: use `{same}` (an existing term), e.g. `--value {same}`."
    return said


def _off_list_targets(bundle: Mapping, target_ids: Sequence[str], field_path: str, term: str,
                      skip: Iterable[str] = ()) -> tuple[list[tuple[str, str]], list[str], str]:
    """``(targets, run ids, scope)`` of the call's targets that the same off-list answer reaches."""
    skipped = set(skip)
    targets: list[tuple[str, str]] = []
    runs: list[str] = []
    beamtime = False
    for tid in target_ids:
        try:
            kind, obj = resolve_target(bundle, tid)
        except MutationRefused:
            continue
        if kind not in ("candidate", "missing_value", "conflict"):
            continue
        got = _decided_value_target(bundle, kind, obj, "correct", term)
        if got is None or got[0] != field_path:
            continue
        if tid not in skipped:
            targets.append((kind, tid))
        ids = list(obj.get("run_ids") or ()) if kind == "conflict" else [obj.get("run_id")]
        ids = [r for r in ids if r]
        if not ids:
            beamtime = True
        runs += ids
    return targets, runs, "experiment" if beamtime and not runs else "run"


def _keep_refused_answer(bundle_dir: Path, bundle: dict, exc: "OffListRefused", *, target_ids: Sequence[str], by: str,
                         orcid: str | None, note: str | None, source: Mapping, slots: Sequence[str] = (),
                         slot_runs: Sequence[str] = ()) -> MutationRefused:
    """Keep ``exc``'s answer as a vocabulary request on ``bundle`` (under the caller's lock), save it when it is new,
    and return the refusal to raise, saying so. ``slots``: per-run answer slots this call added in memory; they are
    dropped (never left as new questions) and their runs named instead."""
    if slots:
        drop_unrecorded_slots(bundle, slots)
    targets, runs, scope = _off_list_targets(bundle, target_ids, exc.field_path, exc.term, skip=slots)
    runs = [*runs, *slot_runs]
    request, new = keep_vocabulary_request(bundle, field_path=exc.field_path, term=exc.term, by=by, orcid=orcid,
                                           targets=targets, run_ids=runs, scope="run" if runs else scope,
                                           source=source, note=note)
    reaffirmed = not new and request["source"].get("as_said") is True  # keep_vocabulary_request stamped reaffirmed_utc
    if new or reaffirmed:
        save_bundle(bundle_dir, bundle)
    return OffListRefused(f"{exc} {vocabulary_kept_sentence(request, new, reaffirmed)}", field_path=exc.field_path, term=exc.term,
                          code=exc.code, problem=exc.problem)


#: c8-a: the ``value`` a ``defer`` on the experiment carries when it answers the CLOCK question ("I don't know the
#: instrument clock's time zone"). The counter question and the clock question share the experiment target, and a
#: ``defer`` with no value has always been the counter question's; the bundle format has no other field for it.
CLOCK_ZONE_DEFER_VALUE = "clock_time_zone"


#: c8-r: a ``defer`` on the experiment says "I don't know" to ONE question, chosen by the question, never by a
#: value the scientist types (``--value clock_time_zone`` recorded a clock deferral without the clock question).
EXPERIMENT_DEFER_VALUE_REFUSAL = (
    "`defer` on the experiment takes no --value: it is \"I don't know\" to one question, and the question says "
    "which. Answer the question itself: `isaac bundle decide <bundle_dir> --question <question id> --decision defer "
    '--by "<your name>"` (the counter question, or the instrument clock\'s time zone question; `isaac bundle '
    "questions <bundle_dir>` lists them). Nothing was recorded.")


def is_clock_zone_deferral(d: Mapping) -> bool:
    """``True`` for a ``defer`` that answers the clock question (:data:`CLOCK_ZONE_DEFER_VALUE`), never the counter's."""
    return (isinstance(d, Mapping) and d.get("decision") == "defer" and d.get("value") == CLOCK_ZONE_DEFER_VALUE
            and d.get("target") == {"kind": "experiment", "id": "experiment"})


def clock_zone_deferral(bundle: Mapping) -> dict | None:
    """``{by, decided_utc, decision_id}`` when the LATEST answer to the clock question is ``defer`` ("I don't
    know"), else ``None``. A later ``set_clock_time_zone`` supersedes it. A defer converts no start time."""
    last = None
    for d in bundle.get("scientist_decisions") or ():
        if isinstance(d, Mapping) and (d.get("decision") == B.CLOCK_ZONE_DECISION or is_clock_zone_deferral(d)):
            last = d
    if last is None or not is_clock_zone_deferral(last):
        return None
    return {"by": (last.get("decided_by") or {}).get("name"), "decided_utc": last.get("decided_utc"),
            "decision_id": last.get("decision_id")}


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


#: The reason a per-run answer slot says it exists (:func:`run_answer_targets`; :func:`bundle.is_answer_slot`).
ANSWER_SLOT_REASON = B.ANSWER_SLOT_REASON


def run_answer_targets(bundle: dict, path: str, run_ids: Sequence[str], *, question_id: str,
                       how: str) -> tuple[list[str], list[str]]:
    """``(target ids, slots added)`` for answering ``path`` for exactly ``run_ids``: each run's OWN targets for it
    (its candidates and missing values of that field), and, for a run that has none because the import asks the
    field once for the whole beamtime, a new missing value (``target_write_scope`` run) added to ``bundle`` in
    memory, citing ``question_id``. The caller records on the ids through :func:`record_decision` (every check of
    ``decide`` applies) and drops a slot whose decision was not recorded before any save
    (:func:`drop_unrecorded_slots`). The beamtime-wide target itself is never decided here."""
    wanted = list(dict.fromkeys(run_ids))
    own: dict[str, list[str]] = {}
    for c in bundle.get("candidates") or ():
        if c.get("target_field_path") == path and c.get("run_id") in wanted:
            own.setdefault(c["run_id"], []).append(c["candidate_id"])
    for m in bundle.get("missing_values") or ():
        if m.get("target_field_path") == path and m.get("run_id") in wanted:
            own.setdefault(m["run_id"], []).append(m["value_id"])
    beamtime = [c["candidate_id"] for c in bundle.get("candidates") or ()
                if c.get("run_id") is None and c.get("target_field_path") == path]
    numbers = [int(m["value_id"].split("-", 1)[1]) for m in bundle.get("missing_values") or ()
               if re.fullmatch(r"miss-\d+", str(m.get("value_id")))]
    n = max(numbers, default=0)
    writable = B._writable_paths()
    ids: list[str] = []
    added: list[str] = []
    for rid in wanted:
        if own.get(rid):
            ids += own[rid]
            continue
        slot = B._missing(n, rid, path, "run", ANSWER_SLOT_REASON.format(question=question_id, how=how),
                          {path: beamtime}, writable)
        n += 1
        bundle.setdefault("missing_values", []).append(slot)
        ids.append(slot["value_id"])
        added.append(slot["value_id"])
    return ids, added


def drop_unrecorded_slots(bundle: dict, added: Sequence[str]) -> list[str]:
    """Remove each slot of ``added`` that no decision targets, so a refused or skipped answer never leaves an
    empty slot (a new open question) behind. Returns the ids removed."""
    decided = {(d.get("target") or {}).get("id") for d in bundle.get("scientist_decisions") or ()
               if (d.get("target") or {}).get("kind") == "missing_value"}
    gone = [v for v in added if v not in decided]
    if gone:
        bundle["missing_values"] = [m for m in bundle["missing_values"] if m["value_id"] not in set(gone)]
    return gone


def drop_dead_slots(bundle: dict) -> list[str]:
    """c7-r LOW-8: remove every answer slot (:func:`bundle.is_answer_slot`) that nothing names — no decision, exposure,
    question or AI reading — on any save, as :func:`drop_unrecorded_slots` does for one call's own: a slot exists only
    to hold an answer. A slot any decision names (a deferred one too) is never dropped: the log refers to it."""
    named = {(e.get("target") or {}).get("id") for key in ("scientist_decisions", "exposures", "questions", "ai_interpretations")
             for e in bundle.get(key) or () if (e.get("target") or {}).get("kind") == "missing_value"}
    gone = [m["value_id"] for m in bundle.get("missing_values") or () if B.is_answer_slot(m) and m["value_id"] not in named]
    if gone:
        bundle["missing_values"] = [m for m in bundle["missing_values"] if m["value_id"] not in set(gone)]
    return gone


def _beamtime_level(bundle: Mapping, target_ids: Sequence[str]) -> list[str]:
    """The ids of ``target_ids`` that are about the WHOLE beamtime: a candidate or missing value with no run, a
    conflict that names no run."""
    out = []
    for tid in target_ids:
        try:
            kind, obj = resolve_target(bundle, tid)
        except MutationRefused:
            continue
        if (kind in ("candidate", "missing_value") and obj.get("run_id") is None) or (
                kind == "conflict" and not obj.get("run_ids")):
            out.append(tid)
    return out


def _live_reach(bundle: Mapping) -> tuple[int, int]:
    """``(groups, runs)``: the live record groups, and the runs they hold — what a beamtime-wide answer reaches."""
    from . import questions as Q

    groups = Q.live_groups(bundle)
    return len(groups), len({k for g in groups for k in g.get("member_run_keys") or ()})


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def group_answer_targets(bundle: dict, asked: Mapping, only: str, field: str | None,
                         decision: str) -> tuple[list[str], list[str], dict] | None:
    """``decide --question <Q> --only group:<id>`` for a question that asks its field ONCE for the whole beamtime
    (its targets are a beamtime-level candidate, conflict or missing value, so ``group:<id>`` is none of its
    scopes): the answer is recorded for exactly that group's runs (:func:`run_answer_targets`), never on the
    beamtime-wide target. ``(target ids, slots added, reach)``, or ``None`` when the question is not such a
    question (the caller then refuses as before)."""
    from . import questions as Q

    if not only.startswith("group:") or asked.get("kind") not in Q.VALUE_KINDS:
        return None
    pst = asked.get("per_scope_targets") or {}
    if only in pst or "experiment" not in pst:
        return None
    path = field if asked["kind"] == "optional_values" else asked.get("target_field_path")
    if not path or "[]" in path:
        return None
    asked_ids = set(pst["experiment"])
    if asked["kind"] == "optional_values":
        asked_ids &= set((asked.get("fields") or {}).get(path) or ())
    if not _beamtime_level(bundle, sorted(asked_ids)):
        return None
    if decision not in ("confirm", "correct"):
        raise MutationRefused(
            f"Question {asked['question_id']} asks {path} once for the whole beamtime. `--only {only}` records an answer "
            f"for that group's runs only (`--decision correct --value <v>`, or `confirm --value <v>`); to {decision} "
            "it, answer the question for the whole beamtime (without --only). Nothing was recorded.")
    gid = only.split(":", 1)[1]
    group = next((g for g in Q.live_groups(bundle) if g["group_id"] == gid), None)
    if group is None:
        raise MutationRefused(f"No live record group {gid!r} in this bundle; nothing was recorded.", code=6)
    run_of_key = {r["run_key"]: r["run_id"] for r in bundle["runs"]}
    runs = [run_of_key[k] for k in group.get("member_run_keys") or () if k in run_of_key]
    if not runs:
        raise MutationRefused(f"Record group {gid} holds no run; nothing was recorded.", code=6)
    ids, added = run_answer_targets(bundle, path, runs, question_id=asked["question_id"],
                                    how=f"decide --question {asked['question_id']} --only {only}")
    groups, _runs = _live_reach(bundle)
    return ids, added, {"question_id": asked["question_id"], "path": path, "scope": only, "runs": len(runs),
                        "slots_added": len(added), "other_groups": max(groups - 1, 0)}


def _options_for(bundle: Mapping, path: str, decisions: Mapping | None = None) -> list[tuple[str | None, str, Any, bool]]:
    """``[(run_id, target id, value, answered)]``: every value the record composer would take for ``path``
    (``records.compose_group``: an eligible candidate or missing value, under its decision), ``answered`` when a
    scientist's decision gives it."""
    from .records import FIELD_REMAP

    want = FIELD_REMAP.get(path, path)
    if decisions is None:  # ``decisions``: the caller's ``bundle._decisions_by_target`` of this bundle, when it has one
        decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    out = []
    for c in bundle.get("candidates") or ():
        if FIELD_REMAP.get(c.get("target_field_path"), c.get("target_field_path")) != want or not (
                c.get("eligibility_for_official_record") or {}).get("eligible"):
            continue
        d = B.candidate_decision(bundle, c, decisions)
        out.append((c.get("run_id"), c["candidate_id"], B.final_value(c["value"], d, c.get("readings")),
                    bool(d) and d.get("decision") in B.CONFIRMING_DECISIONS))
    for m in bundle.get("missing_values") or ():
        if FIELD_REMAP.get(m.get("target_field_path"), m.get("target_field_path")) != want or not (
                m.get("eligibility_for_official_record") or {}).get("eligible"):
            continue
        d = decisions.get(("missing_value", m["value_id"]))
        out.append((m.get("run_id"), m["value_id"], B.final_value(None, d), True))
    return out


def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def groups_keeping_their_own_answer(bundle: Mapping, path: str, value: Any, *, question_id: str | None = None,
                                    options: Sequence[tuple] | None = None) -> list[dict]:
    """The live record groups a beamtime-wide ``value`` for ``path`` does NOT fill (c7-r HIGH-1): a member run holds a
    value of its own for it (a scientist's run-scoped answer — its own target, or an answer slot from
    ``--only group:<id>`` — or an eligible value its files state) that differs, so the record composer meets two
    values and fills nothing for ``path`` until they agree. ``[{group_id, runs, own_answers, files_state,
    target_ids, command}]``; ``own_answers`` lists only what a SCIENTIST answered (a file's value is never
    printed here: it would be a parser value shown)."""
    from . import questions as Q

    differing: dict[str, list[tuple[str, Any, bool]]] = {}
    for rid, tid, v, answered in (options if options is not None else _options_for(bundle, path)):
        if rid is not None and not _same(v, value):
            differing.setdefault(rid, []).append((tid, v, answered))
    if not differing:
        return []
    run_of_key = {r["run_key"]: r["run_id"] for r in bundle["runs"]}
    out = []
    for g in Q.live_groups(bundle):
        members = [run_of_key[k] for k in g.get("member_run_keys") or () if k in run_of_key]
        mine = [x for r in members for x in differing.get(r, ())]
        if not mine:
            continue
        own, seen = [], set()
        for _tid, v, answered in mine:
            if answered and json.dumps(v, sort_keys=True) not in seen:
                seen.add(json.dumps(v, sort_keys=True))
                own.append(v)
        command = (f"isaac bundle decide <bundle_dir> --question {question_id} --only group:{g['group_id']} --decision "
                   'correct --value <value> --by "<your name>"' if question_id else None)
        out.append({"group_id": g["group_id"], "runs": len({r for r in members if r in differing}),
                    "own_answers": own, "files_state": any(not a for _t, _v, a in mine),
                    "target_ids": [t for t, _v, _a in mine], **({"command": command} if command else {})})
    return out


def not_reached_sentence(path: str, kept: Sequence[Mapping], *, lead: str = "NOT reached: ") -> str:
    """The plain sentence for :func:`groups_keeping_their_own_answer`: each group NOT reached, what it keeps, and
    how to change it."""
    label = path
    parts = []
    for k in kept[:5]:
        own = " / ".join(repr(v) for v in k["own_answers"])
        what = (f"keeps its own answer {own}" if own else "keeps the value its own files state")
        if own and k["files_state"]:
            what += " (and a value its own files state)"
        parts.append(f"group:{k['group_id']} {what}, so it fills nothing for {label} until the two agree"
                     + (f"; answer `--only group:{k['group_id']}` to change it (`{k['command']}`)" if k.get("command") else ""))
    more = f"; and {_count(len(kept) - 5, 'more group')}" if len(kept) > 5 else ""
    return lead + "; ".join(parts) + more + "."


def _beamtime_value(bundle: Mapping, path: str) -> tuple[bool, Any]:
    """``(found, value)``: the value the beamtime-wide target of ``path`` gives every record, when one is eligible."""
    found = [v for rid, _tid, v, _a in _options_for(bundle, path) if rid is None]
    return (bool(found), found[0] if found else None)


def _reach_statement(bundle: Mapping, recorded_ids: Sequence[str], override: Mapping | None,
                     question_id: str | None = None) -> tuple[str | None, dict]:
    """What a decide reply on a BEAMTIME-WIDE question adds to its plain sentence, and its ``reach``: how many groups
    and runs the answer reaches (``'HERFD-XAS' recorded for 1 conflict`` alone does not say it is every record of the
    beamtime) and, c7-r HIGH-1, each group it does NOT reach because a run of it keeps its own, differing answer; or,
    for ``--only group:<id>``, that it reaches that group only and what still asks the rest. ``bundle``: the bundle
    the decision was recorded on (a dry run's copy too)."""
    if override is not None:
        label = override["path"].rsplit(".", 1)[-1].replace("_", " ")
        found, beamtime = _beamtime_value(bundle, override["path"])
        mine = [v for rid, tid, v, _a in _options_for(bundle, override["path"])
                if tid in set(recorded_ids) and rid is not None]
        if found and mine and not _same(mine[0], beamtime):
            tail = (f"The beamtime-wide answer to question {override['question_id']} differs from this one, so this "
                    f"group's record has two values for {label} and fills nothing for it until the two agree.")
        elif found and mine:
            tail = f"It agrees with the beamtime-wide answer to question {override['question_id']}."
        else:
            tail = (f"if its answer differs from this one, this group's record gets two values for {label} and fills "
                    "nothing for it.")
        return (f"It reaches {override['scope']} only ({_count(override['runs'], 'run')}"
                + (f"; {_count(override['slots_added'], 'answer slot')} added for runs the files give no target of "
                   "their own" if override["slots_added"] else "")
                + f"). The beamtime-wide question {override['question_id']} covers the other "
                f"{_count(override['other_groups'], 'group')}"
                + (f". {tail}" if tail[0].isupper() else f"; {tail}")), dict(override)
    level = _beamtime_level(bundle, recorded_ids)
    if not level:
        return None, {}
    groups, runs = _live_reach(bundle)
    paths = []
    for tid in level:
        try:
            kind, obj = resolve_target(bundle, tid)
        except MutationRefused:
            continue
        if kind == "conflict":
            obj = next((c for c in bundle.get("candidates") or () if c.get("candidate_id") == obj.get("candidate_id")), {})
        if obj.get("target_field_path") and obj["target_field_path"] not in paths:
            paths.append(obj["target_field_path"])
    kept: list[dict] = []
    for path in paths:
        found, value = _beamtime_value(bundle, path)
        if found:
            kept += [{**k, "path": path} for k in groups_keeping_their_own_answer(bundle, path, value, question_id=question_id)]
    reach = {"beamtime_wide": True, "groups": groups, "runs": runs}
    if not kept:
        return f"It reaches every record group of the beamtime: {_count(groups, 'group')}, {_count(runs, 'run')}.", reach
    apart = {k["group_id"] for k in kept}
    run_of_key = {r["run_key"]: r["run_id"] for r in bundle["runs"]}
    from . import questions as Q

    runs_apart = {run_of_key[k] for g in Q.live_groups(bundle) if g["group_id"] in apart
                  for k in g.get("member_run_keys") or () if k in run_of_key}
    reached_groups = groups - len(apart)
    text = (f"It reaches {reached_groups} of the beamtime's {_count(groups, 'record group')} "
            f"({_count(runs - len(runs_apart), 'run')}). "
            + " ".join(not_reached_sentence(path, [k for k in kept if k["path"] == path]) for path in paths
                       if any(k["path"] == path for k in kept)))
    return text, {**reach, "groups_reached": reached_groups, "not_reached": kept}


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
    same_conditions: bool = False,
    as_said: bool = False,
) -> Any:
    """``isaac bundle decide --question`` — the CLI and the local questions screen both call this.

    ``as_said``: as for :func:`decide` (the local questions screen never passes it, so it never keeps a request).

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
    if (refusal := _as_said_refusal(as_said, decision, value)) is not None:
        raise MutationRefused(refusal)
    kept_overrides: list[dict] = []
    with locked(Path(bundle_dir)):
        _require_version(Path(bundle_dir), expected_version)
        version = bundle_version(bundle_dir)
        bundle = load(bundle_dir)
        resolve = dict(decision=decision, only=only, field=field, positions=positions, only_scopes=only_scopes)
        override = None
        slots_added: list[str] = []
        try:
            found, positions = question_targets(Q.consolidate(bundle), question_id, **resolve)
        except MutationRefused as exc:
            # AN ANSWERED QUESTION is resolved too, under the id it was asked with (its answered targets back in:
            # consolidate(include_answered=True)): a later decision replaces an earlier one, a repeat records
            # nothing, and every check below applies exactly as to an open question. Every kind that drops out once
            # answered (Q.RESOLVABLE_WHEN_ANSWERED): a value, the absorber, the counter positions, the clock zone.
            answered = Q.consolidate(bundle, include_answered=True, explain_counter=False) if exc.code == 6 else None
            asked = Q.question(answered, question_id) if answered is not None else None
            if asked is None or asked["kind"] not in Q.RESOLVABLE_WHEN_ANSWERED:
                raise
            try:
                found, positions = question_targets(answered, question_id, **resolve)
            except MutationRefused as again:
                # ONE GROUP OF A QUESTION ASKED ONCE FOR THE BEAMTIME (c7-s M1): `--only group:<id>` records the answer
                # for exactly that group's runs (their own targets, or a per-run slot), never on the beamtime target
                got = (group_answer_targets(bundle, asked, only, field, decision)
                       if again.code == 6 and only and not only_scopes else None)
                if got is None:
                    raise (exc if again.code == 6 else again) from None
                found, slots_added, override = got
            if asked["kind"] == "confirm_absorber" and decision == "set_absorber" and only is None:
                found, kept_overrides = _keep_absorber_overrides(bundle, found)
        clock_defer = False
        if decision == "defer" and (Q.question(Q.consolidate(bundle, include_answered=True, explain_counter=False),
                                               question_id) or {}).get("kind") == "clock_time_zone":
            # c8-a: the clock question's "I don't know", told apart from the counter question's on the same target
            zone_d = B.clock_zone_decision(bundle)
            if zone_d is not None:
                raise MutationRefused(
                    f"The instrument clock's time zone is already recorded ({zone_d.get('value')}, "
                    f"{zone_d.get('decision_id')}); a defer would not withdraw it, and the start times stay converted "
                    f"with it. To change it, state the zone again: {B.CLOCK_ZONE_COMMAND}. Nothing was recorded.")
            if value is not None:
                raise MutationRefused(EXPERIMENT_DEFER_VALUE_REFUSAL)
            value, clock_defer = CLOCK_ZONE_DEFER_VALUE, True
        params = dict(
            target_ids=list(extra_targets) + found, decision=decision, value=value, by=by, orcid=orcid, note=note,
            split_into=split_into, merge_with=merge_with, qc_status=qc_status, qc_note=qc_note,
            element=element, edge=edge, positions=positions, same_conditions=same_conditions,
            **({"clock_zone_defer": True} if clock_defer else {}),
        )
        def reached(on: dict, result: dict) -> dict:
            # read from the bundle the decision was recorded on (a dry run's copy too), its states derived as the
            # save will derive them: what each group's record now takes
            if override is None and not _beamtime_level(on, found):
                return result
            view = B.apply_derivations(copy.deepcopy(on))
            reach, detail = _reach_statement(view, found, override, question_id)
            if not reach:
                return result
            out = {"statement": " ".join(x for x in (result.get("statement"), reach) if x), "reach": detail}
            return {**out, **{k: v for k, v in result.items() if k != "statement"}}

        if dry_run:
            copied = copy.deepcopy(bundle)
            planned = reached(copied, record_decision(copied, **params))
            planned = {**planned, "statement": _would_say(planned.get("statement"))}
            return _with_kept(kept_overrides, {"dry_run": True, "bundle_version": version, "target_ids": params["target_ids"], **planned})
        try:
            recorded = record_decision(bundle, **params)
        except OffListRefused as exc:
            if not as_said:
                raise _not_kept(exc) from None
            slot_runs = [m.get("run_id") for m in bundle.get("missing_values") or () if m["value_id"] in set(slots_added)]
            raise _keep_refused_answer(bundle_dir, bundle, exc, target_ids=params["target_ids"], by=by, orcid=orcid,
                                       note=note, slots=slots_added, slot_runs=[r for r in slot_runs if r],
                                       source={"kind": "decide_answer", "command": "bundle decide", "decision": decision,
                                               "question_id": question_id, "as_said": True}) from None
        result = _said_on_list(_with_kept(kept_overrides, reached(bundle, recorded)), as_said)
        save_bundle(bundle_dir, bundle)
        return (result, bundle_version(bundle_dir)) if with_version else result


def _would_say(statement: str | None) -> str | None:
    """A decide statement said for a DRY RUN, which writes nothing: "Fe K recorded for 9 groups." becomes "Would
    record: Fe K recorded for 9 groups. Nothing was written."; "Nothing new recorded: …" becomes "Nothing would be
    recorded: …"."""
    if not statement:
        return statement
    if statement.startswith("Nothing new recorded"):
        return "Nothing would be recorded" + statement[len("Nothing new recorded"):] + " Nothing was written."
    return f"Would record: {statement} Nothing was written."


def _keep_absorber_overrides(bundle: Mapping, group_ids: Sequence[str]) -> tuple[list[str], list[dict]]:
    """Re-answering an ANSWERED absorber question for all its groups (no ``--only``) never undoes a per-group
    answer (review, cycle 5): a group whose current element/edge differs from the one most of the question's
    groups now hold keeps it, and is named; ``--only group:<id>`` changes one. Returns (groups to record, kept)."""
    from collections import Counter

    from . import suggestions as S

    current = S.absorber_decisions(bundle)
    pairs = {g: (current[g]["element"], current[g]["edge"]) for g in group_ids if g in current}
    if not pairs:
        return list(group_ids), []
    common, _ = Counter(pairs.values()).most_common(1)[0]
    kept = [{"group_id": g, "element": pairs[g][0], "edge": pairs[g][1]} for g in group_ids if g in pairs and pairs[g] != common]
    keep = {k["group_id"] for k in kept}
    return [g for g in group_ids if g not in keep], kept


def _with_kept(kept: Sequence[Mapping], result: dict) -> dict:
    """``result`` with the per-group absorber answers a whole-question re-answer left alone, said first."""
    if not kept:
        return result
    said = "; ".join(f"{k['group_id']} keeps {k['element']} {k['edge']}" for k in kept[:5]) + (
        f"; and {len(kept) - 5} more" if len(kept) > 5 else "")
    note = (f"{len(kept)} group(s) answered on their own were left as they are ({said}); change one with "
            "`--only group:<id>`.")
    return {"statement": " ".join(x for x in (result.get("statement"), note) if x), "kept_per_group_answers": list(kept),
            **{k: v for k, v in result.items() if k != "statement"}}


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
                      qc_note=None, same_conditions=False, split_into=None, clock_zone_defer=False, accept_shift=None,
                      **_rest):
    """The checks of :func:`decide` that need no bundle. Returns ``positions`` normalised."""
    problem = B.decider_name_problem(by)
    if problem:
        raise MutationRefused(f"--by is required: the name of the person deciding (this one {problem.replace('has ', 'has ', 1)}).")
    if orcid is not None and not ORCID_RE.fullmatch(orcid):
        raise MutationRefused("--orcid must look like 0000-0000-0000-0000 (last character may be X).")
    if not target_ids:
        raise MutationRefused("No target given.")
    if (decision == "defer" and value is not None and "experiment" in target_ids
            and not (clock_zone_defer and value == CLOCK_ZONE_DEFER_VALUE)):
        raise MutationRefused(EXPERIMENT_DEFER_VALUE_REFUSAL)
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
    if accept_shift is not None:
        if decision != "approve_calibration":
            raise MutationRefused("--accept-shift goes with --decision approve_calibration on a record group: the shift "
                                  "(in eV) the reply said approving applies. Nothing was recorded.")
        try:
            if not math.isfinite(float(accept_shift)):
                raise ValueError
        except (TypeError, ValueError):
            raise MutationRefused("--accept-shift must be a number in eV, e.g. -8.6. Nothing was recorded.") from None
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
    if split_into and decision != "split":
        raise MutationRefused("--split-into goes with --decision split on a record group: one list of run keys per "
                              "group to make.")
    if same_conditions and decision != "merge":
        raise MutationRefused("--same-conditions goes with --decision merge on a record group: it says the words the "
                              "groups' file names differ in are labels, not conditions.")
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


#: Record-group decisions that are not about the group's own state: each is compared with the latest of its own
#: kind when a repeat is judged (a set_absorber restated after the group was confirmed records nothing).
_GROUP_SIDE_DECISIONS = ("set_absorber", "approve_calibration")


def _shown_value(value: Any) -> str:
    text = repr(value) if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return text if len(text) <= 60 else text[:57] + "…"


def plain_statement(bundle: Mapping, planned: Sequence[tuple[str, Mapping]], target_ids: Sequence[str],
                    recorded: Sequence[str], *, decision: str, value: Any, element: str | None = None,
                    edge: str | None = None, positions: Sequence[int] | None = None, qc_status: str | None = None) -> str:
    """ONE plain sentence for a decide reply that says nothing else: what was recorded, for how many of what (groups,
    runs, the whole beamtime …) and which fields — e.g. "Pt L3 recorded for 194 groups.", "deferred for 140 runs:
    environment." The reply's id lists stay beside it; this sentence is for the person."""
    what = {
        "set_absorber": f"{element} {edge} recorded",
        "approve_calibration": f"calibration {element} {edge} approved",
        "confirm": "confirmed", "reject": "rejected", "defer": "deferred", "correct": f"{_shown_value(value)} recorded",
        "approve": "approved" + (f" (QC status {qc_status})" if qc_status else ""),
        "merge": "merge recorded", "split": "split recorded",
        "set_counter_positions": f"counter position(s) {', '.join(map(str, positions or ()))} recorded",
        B.CLOCK_ZONE_DECISION: f"instrument clock time zone {value} recorded",
    }.get(decision, f"{decision} recorded")
    cand_path = {c["candidate_id"]: c.get("target_field_path") for c in bundle.get("candidates") or ()}

    def count(n: int, noun: str) -> str:
        return f"{n} {noun}{'' if n == 1 else 's'}"

    def subject(ids: set[str]) -> tuple[str, str]:
        nouns = {"record_group": "group", "processing_result": "processing result", "merge_candidate": "merge candidate",
                 "conflict": "conflict", "source": "source", "run": "run"}
        by_kind: dict[str, list[Mapping]] = {}
        for tid, (kind, obj) in zip(target_ids, planned):
            if tid in ids:
                by_kind.setdefault(kind, []).append(obj)
        parts, fields = [], []
        for kind, objs in by_kind.items():
            if kind in ("candidate", "missing_value"):
                runs = {o.get("run_id") for o in objs}
                if runs - {None}:
                    parts.append(count(len(runs - {None}), "run"))
                if None in runs:
                    parts.append("the whole beamtime")
            elif kind == "experiment":
                parts.append("the beamtime")
            else:
                parts.append(count(len(objs), nouns.get(kind, kind.replace("_", " "))))
            for o in objs:
                path = o.get("target_field_path") if kind in ("candidate", "missing_value") else (
                    cand_path.get(o.get("candidate_id")) if kind == "conflict" else None)
                label = path.rsplit(".", 1)[-1].replace("_", " ") if path else None
                if label and label not in fields:
                    fields.append(label)
        named = ", ".join(fields[:3]) + ("…" if len(fields) > 3 else "")
        return " and ".join(parts), named

    done = set(recorded)
    rest = {t for t in target_ids if t not in done}
    if not done:
        who, fields = subject(rest)
        had = f"{element} {edge}" if decision == "set_absorber" else f"this answer ({what})"
        plural = not who.startswith(("1 ", "the "))
        return f"Nothing new recorded: {who} already {'have' if plural else 'has'} {had}" + (f": {fields}." if fields else ".")
    who, fields = subject(done)
    out = f"{what} for {who}" + (f": {fields}" if fields else "") + "."
    if rest:
        out += f" {subject(rest)[0]} already had it (nothing new recorded for them)."
    return out


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
    same_conditions: bool = False,
    clock_zone_defer: bool = False,
    accept_shift: float | None = None,
) -> dict:
    """:func:`decide` applied to an ALREADY-LOADED bundle, under the caller's lock. Saves
    nothing: the caller saves through :func:`save_bundle` (or :func:`mutate`). Every target
    is checked before any entry is appended, so a refusal leaves ``bundle`` unchanged.
    ``clock_zone_defer``: set ONLY by :func:`decide_question` for the clock question's ``defer``, whose value
    (:data:`CLOCK_ZONE_DEFER_VALUE`) it sets itself; a ``defer`` on the experiment otherwise takes no value."""
    positions = _decide_arguments(
        target_ids=target_ids, decision=decision, by=by, orcid=orcid, qc_status=qc_status,
        element=element, edge=edge, positions=positions, value=value, qc_note=qc_note, same_conditions=same_conditions,
        split_into=split_into, clock_zone_defer=clock_zone_defer, accept_shift=accept_shift,
    )
    bulk = len(target_ids) > 1
    # 0.01 eV: a shift near the warning level is shown to 0.01 eV (reference.shown); compared to 0.1 eV
    accepted = round(float(accept_shift), 2) if accept_shift is not None else None
    if decision == "approve_calibration":
        # c12-cal: what the approval would apply is said BEFORE anything is recorded (and refused when nothing can be)
        value = {"accepted_shift_eV": accepted} if accepted is not None else None

    def change(bundle):
        latest = B._decisions_by_target(bundle.get("scientist_decisions") or ())
        planned: list[tuple[str, dict]] = []
        acknowledged: dict[str, list[str]] = {}
        calibration_said: dict[str, str] = {}
        off_list: OffListRefused | None = None
        for tid in target_ids:
            kind, obj = resolve_target(bundle, tid)
            try:
                _check_decision(bundle, kind, obj, decision, value, bulk=bulk, merge_with=merge_with, split_into=split_into)
            except OffListRefused as exc:
                # EVERY TARGET IS CHECKED FIRST: an off-list refusal is raised (and kept as a vocabulary request) only
                # when no target is refused for any other reason, whatever order the targets came in
                off_list = off_list or exc
            if kind == "processing_result" and decision == "approve":
                problem = approved_sibling_problem(bundle, obj, [o for k, o in planned if k == "processing_result"])
                if problem is not None:
                    raise MutationRefused(problem)
            if same_conditions:
                acknowledged[tid] = _same_conditions_tokens(bundle, kind, obj, merge_with)
            if qc_status is not None and kind != "processing_result":
                raise MutationRefused("--qc-status applies to a processing result only.")
            if kind == "processing_result" and decision == "approve" and qc_status is None:
                # I4: the QC status is never guessed from the protocol's verdict.
                raise MutationRefused(
                    "Approving a processing result needs --qc-status (one of "
                    + ", ".join(qc_status_vocabulary()) + "): the QC status is a person's statement."
                )
            if kind == "record_group" and decision == "approve_calibration":
                calibration_said[tid] = calibration_shift_said(bundle, tid, element, edge, accepted)
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
        if off_list is not None:
            raise off_list
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
        split_made: list[tuple[dict, dict]] = []
        held_before = len(decisions)
        zone_d = B.clock_zone_decision(bundle)
        for tid, (kind, obj) in zip(target_ids, planned):
            prior = latest.get((kind, tid))
            if kind == "experiment":
                # several decision kinds share the one experiment target: replaying one is compared
                # with the latest of ITS kind (a zone restated after a counter answer is unchanged); a defer
                # is the counter question's "I don't know", compared with that question's latest answer
                # (c8-a: a defer of the CLOCK question, value CLOCK_ZONE_DEFER_VALUE, with that question's latest answer)
                clock = decision == "defer" and value == CLOCK_ZONE_DEFER_VALUE
                same = ((B.CLOCK_ZONE_DECISION, "defer") if clock else ("set_counter_positions", B.NOT_COUNTER_DECISION, "defer")
                        if decision == "defer" else (decision,))
                prior = next((d for d in reversed(bundle.get("scientist_decisions") or ())
                              if d.get("target") == {"kind": "experiment", "id": tid} and d.get("decision") in same
                              and (d.get("decision") != "defer" or is_clock_zone_deferral(d) == clock)), None)
            elif kind == "processing_result":
                # an Athena-version selection (1.6.0) and the state decisions share the target: each is
                # compared with the latest of its own class
                selecting = decision == B.ATHENA_SELECT_DECISION
                prior = next((d for d in reversed(bundle.get("scientist_decisions") or ())
                              if d.get("target") == {"kind": kind, "id": tid}
                              and (d.get("decision") == B.ATHENA_SELECT_DECISION) == selecting), None)
            elif kind == "record_group" and decision in _GROUP_SIDE_DECISIONS:
                # an absorber (or calibration) answer and the group's own state decisions share the target: a
                # repeated set_absorber after the group was confirmed is compared with the latest set_absorber
                prior = next((d for d in reversed(bundle.get("scientist_decisions") or ())
                              if d.get("target") == {"kind": kind, "id": tid} and d.get("decision") == decision), None)
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
                         json.dumps(positions or []), json.dumps(binding, sort_keys=True), json.dumps(identity, sort_keys=True),
                         json.dumps(acknowledged.get(tid)))
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
                json.dumps(prior.get("same_conditions_tokens")),
            ) == signature and not (kind == "processing_result" and decision == "approve" and approval_is_stale(prior, obj)):
                # an approval restated after its result's files changed binds it to them: a new statement
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
            if tid in acknowledged:
                # 1.9.0: the scientist's statement that these runs were measured under the SAME conditions,
                # bound to the file-name words it was made for (a merge naming other words needs it again)
                entry["same_conditions_tokens"] = acknowledged[tid]
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
                entry["approved_files"] = approval_files(obj)
            if qc_status is not None:
                # THE PERSON STATES THE QC STATUS; what they were shown is kept beside it.
                qc = obj.get("qc") or {}
                entry["qc_status"] = qc_status
                entry["qc_note"] = qc_note
                entry["qc_evidence"] = {"verdict": qc.get("verdict"), "metrics": qc.get("metrics") or {}}
            decisions.append(entry)
            recorded.append(tid)
            if kind == "record_group" and decision == "split":
                split_made.append((obj, entry))
        if len(decisions) > B.MAX_SCIENTIST_DECISIONS:
            added = len(decisions) - held_before
            del decisions[held_before:]  # the refusal leaves the bundle as it was
            raise MutationRefused(log_full_message("scientist_decisions", held_before, added, B.MAX_SCIENTIST_DECISIONS))
        result = {"recorded": recorded, "unchanged": unchanged, "batch_id": batch_id}
        if split_made:
            # A SPLIT MAKES EXACTLY THE GROUPS NAMED, now (c8-s; before, the lists were stored and nothing read them)
            made, said = [], []
            for obj, entry in split_made:
                parts = split_parts(bundle, obj, entry)
                bundle["record_groups"].extend(parts)
                made += [{"group_id": p["group_id"], "member_run_keys": p["member_run_keys"]} for p in parts]
                said.append(f"group {obj['group_id']} is now {len(parts)} proposed groups, one per list you named — "
                            + "; ".join(_part_said(bundle, p) for p in parts))
            result["split_into_groups"] = made
            result["statement"] = (
                "Split recorded: " + ". ".join(said) + ". Each is a proposal: confirm each "
                '(`isaac bundle decide <bundle_dir> --target <group id> --decision confirm --by "<your name>"`), or merge, '
                "reject or split it. A regroup keeps them as you named them; the split group is kept as the record of "
                "the split.")
        statement = CAPTURE_STATEMENTS.get(decision)
        if statement:
            result["statement"] = statement.format(value=value, positions=", ".join(map(str, positions or ())))
        if acknowledged:
            words = " / ".join(dict.fromkeys(t for ts in acknowledged.values() for t in ts))
            result["statement"] = (
                f"Recorded: the merge, with your statement that these runs measured the same sample under the same "
                f"conditions — their file names differ only in: {words}, which you said are labels, not conditions. "
                "Regroup (`isaac bundle group <bundle_dir> --regroup`) to apply it: the runs are combined only when the "
                "same sample is confirmed for every run and nothing else recorded tells them apart.")
        if decision == "defer" and recorded and value == CLOCK_ZONE_DEFER_VALUE and all(kind == "experiment" for kind, _ in planned):
            result["statement"] = (
                "Recorded: you do not know the time zone the instrument clock was set to (defer). No start time is "
                "converted: the runs' local clock times stay out of the records. The clock question stays open, marked "
                f"deferred; answer it later with set_clock_time_zone ({B.CLOCK_ZONE_COMMAND}).")
        elif decision == "defer" and recorded and all(kind == "experiment" for kind, _ in planned):
            result["statement"] = (
                "Recorded: you do not know which filename token positions are run/acquisition counters (defer). "
                "Grouping is unchanged: no position is recorded as a counter or as not one, and no group moved. The "
                "counter question stays open, marked deferred; answer it later with set_counter_positions or "
                "set_not_counter_positions.")
        if decision == "set_counter_positions" and recorded:
            # what this answer would do on the next regroup, said BEFORE it (the scientist is told what it joins)
            result["regroup_preview"] = counter_answer_preview(bundle)
        if decision == "approve" and recorded:
            # WHAT WAS APPROVED, said when it is not the full merge (the Athena curve's own scan subset)
            notes = [n for kind, obj in planned if kind == "processing_result" and B.processing_id(obj) in recorded
                     and (n := scan_subset_note(bundle, obj))]
            if notes:
                result["statement"] = "Recorded. " + " ".join(notes)
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
        # A PLAIN STATEMENT FIRST (the id lists stay, for --json consumers): what was recorded, for how many of what
        statement = result.pop("statement", None) or plain_statement(
            bundle, planned, target_ids, recorded, decision=decision, value=value, element=element, edge=edge,
            positions=positions, qc_status=qc_status)
        if calibration_said:
            said = list(dict.fromkeys(calibration_said.values()))
            statement = " ".join([statement, *said[:3]] + ([f"(and {len(said) - 3} more)"] if len(said) > 3 else []))
        return {"statement": statement, **result}

    return change(bundle)


# --- crosscheck plan / excerpt / reveal ---------------------------------------------------------


def _locators(candidate: Mapping) -> list[dict]:
    return [
        {"source_id": e["source_id"], "relative_path": e["relative_path"], "locator": e["locator"]}
        for e in candidate["evidence"]
        if e["method"] != "ai_interpretation"
    ][:B.MAX_EVIDENCE_PER_CANDIDATE]


def _target_source_ids(kind: str, obj: Mapping) -> set[str]:
    """The sources a target's own locators name (what ``excerpt`` reads); empty when it has none
    (a missing value, a record group, a processing result)."""
    if kind == "candidate":
        ids = [e["source_id"] for e in obj["evidence"] if e["method"] != "ai_interpretation"]
    elif kind == "source":
        ids = [obj["source_id"]]
    elif kind == "run":
        ids = [obj["acquisition_source_id"]] + [s["source_id"] for s in obj["scans"]] + [
            d["macro_source_id"] for d in obj["declared_by"]
        ]
    else:
        ids = []
    return {i for i in ids if i}


def _scan_locator(scan: Mapping, part: str | None = None) -> str:
    """Where one scan is: ``scan 3`` (``scan 3 channel columns``) in a file of numbered scans, or the scan
    file itself when it holds one scan and states no scan number (never "scan None")."""
    if scan.get("scan_index") is None:
        return ("the scan file's " + part if part else "the scan file") + " (one scan, no scan number)"
    return f"scan {scan['scan_index']}" + (f" {part}" if part else "")


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
        locs += [{"source_id": s["source_id"], "relative_path": s["relative_path"], "locator": _scan_locator(s)} for s in run["scans"]]
        locs += [{"source_id": d["macro_source_id"], "relative_path": d["macro_path"], "locator": f"newfile block {d['block_index']}"} for d in run["declared_by"]]
        add("run", run["run_id"], "run_association", run["run_id"], locs)
        if run["signal_selection"]:
            add("run", run["run_id"], "herfd_signal_choice", run["run_id"],
                [{"source_id": s["source_id"], "relative_path": s["relative_path"], "locator": _scan_locator(s, "channel columns")} for s in run["scans"]])
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
            if B.is_local_clock_start(c):
                # c8-b: no UTC value until the clock's zone is stated; `reveal` compares a reading with the header's
                # local clock time, so say what to read (no value)
                items[-1]["compared_as"] = LOCAL_CLOCK_COMPARED_AS
                items[-1]["read_note"] = LOCAL_CLOCK_READ_NOTE
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
    # THE DENOMINATOR for "I independently read N of M high-value items (K blind)": only the six named
    # high-value categories (the skill's list), and only items that can be read blind (excerptable)
    hv = [i for i in items if i["category"] in HIGH_VALUE_CATEGORIES and i["excerptable"]]
    hv_checked = sum(1 for i in hv if i["checked"])
    hv_blind = sum(1 for i in hv if i["blind_checks"])
    return {
        "total": total,
        "high_value_total": len(hv),
        "high_value_categories": list(HIGH_VALUE_CATEGORIES),
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
            "high_value_checked": hv_checked,
            "high_value_blind_checked": hv_blind,
            "high_value_statement": (
                f"High-value items (the {len(HIGH_VALUE_CATEGORIES)} categories in `high_value_categories`, only those that "
                f"can be excerpted): {len(hv)}. Say \"I independently read {hv_checked} of {len(hv)} high-value items "
                f"({hv_blind} blind)\"; targets outside those categories are not in either number."
            ),
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
        if (loc["locator"] or "").startswith(B._FILENAME_TOKEN_LOCATOR) or loc["locator"] == "filename":
            # The source text of a file-name reading IS the name: show it and which token, not the file's lines
            out.append({
                "source_id": src["source_id"],
                "relative_path": path,
                "locator": loc["locator"],
                "lines": None,
                "text": f"file name: {path}\n{loc['locator']}",
                "truncated": False,
            })
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


#: Why ``reveal`` gives no ``agrees_with_parser`` for a reading: there is no parser value to hold it against.
NO_PARSER_VALUE_NOTE = "the parser holds no value for this target, so there is nothing to compare"
#: ``compared_as`` for a reading of a scan start time held against the header's local clock time (c8-b).
LOCAL_CLOCK_COMPARED_AS = "local clock time"
#: What a ``crosscheck-plan`` item of a scan start time tells the reader to write down (c8-b).
LOCAL_CLOCK_READ_NOTE = ("a scan start time: read the EARLIEST scan's line-2 time and annotate it as the header writes it "
                         "or as YYYY-MM-DDTHH:MM:SS, with no zone (the header names none); `reveal` compares it with the "
                         "header's local clock time")
#: Date-time spellings a reading of a local clock time is read in (besides ISO 8601, with ``T`` or a space): the XDC
#: header's own (with or without its weekday) and month-name forms. A numeric day/month order is never guessed.
_LOCAL_CLOCK_FORMATS = ("%a %b %d %H:%M:%S %Y", "%b %d %H:%M:%S %Y", "%Y/%m/%d %H:%M:%S", "%d %b %Y %H:%M:%S",
                        "%b %d %Y %H:%M:%S", "%d %B %Y %H:%M:%S", "%B %d %Y %H:%M:%S", "%Y-%m-%d %H:%M")
_ZONE_SUFFIX = re.compile(r"(?:[zZ]|[+-]\d{2}:?\d{2}|\s+(?:UTC|GMT|[A-Z]{3,4}))$")


def read_local_clock_reading(value: Any) -> tuple[str | None, str | None]:
    """``(naive ISO to the second, problem)`` for an AI reading of a local clock time. ``problem`` says why it is not
    one: it names a zone or offset (then it is an instant, not a clock reading), or no known spelling reads it."""
    if not isinstance(value, str) or not value.strip():
        return None, "the reading is not a date and time written as text"
    text = " ".join(value.strip().replace(",", " ").split())
    if _ZONE_SUFFIX.search(text):
        return None, "the reading names a time zone or UTC offset, so it is an instant, not a local clock time"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
        for fmt in _LOCAL_CLOCK_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None, "the reading could not be read as a date and time (ISO 8601, or the header's own spelling)"
    if parsed.tzinfo is not None:
        return None, "the reading names a time zone or UTC offset, so it is an instant, not a local clock time"
    return parsed.replace(microsecond=0).isoformat(), None


def compare_local_clock(candidate: Mapping, proposed: Any) -> dict | None:
    """A blind reading of a scan start time (``bundle.is_local_clock_start``) held against the header's LOCAL CLOCK
    time, as the same clock time in any spelling (``compared_as: local clock time``): the earliest scan's, which the
    rule takes as the start. ``None`` when the reading names a zone and the candidate has a UTC value (compared as
    an instant, the ordinary way)."""
    start = B.local_clock_start(candidate, None)
    local, literal = start["local_time"], start["literal"]
    if local is None:
        return None
    iso, problem = read_local_clock_reading(proposed)
    if problem is not None:
        if candidate.get("value") is not None and "instant" in problem:
            return None
        return {"agrees_with_parser": None, "compared_as": LOCAL_CLOCK_COMPARED_AS,
                "comparison_note": (f"{problem}; the scan header writes the local clock time {literal!r} ({local}) and "
                                    "names no zone, so they cannot be compared as the same time")}
    note = (f"compared as the same local clock time: the reading {proposed!r} is {iso}, the scan header writes {literal!r} "
            f"({local}, no zone named), the earliest scan's time, which the rule takes as the start")
    if iso == local:
        return {"agrees_with_parser": True, "compared_as": LOCAL_CLOCK_COMPARED_AS, "comparison_note": note}
    later = next((e for e in candidate.get("evidence") or () if e.get("method") == "deterministic_parser"
                  and B.read_xdc_literal(e.get("literal_value")) == iso), None)
    if later is not None:
        note += (f"; the reading is the time another scan of the run writes ({later.get('relative_path')}, "
                 f"{later.get('literal_value')!r}), not the earliest")
    return {"agrees_with_parser": False, "compared_as": LOCAL_CLOCK_COMPARED_AS, "comparison_note": note}


def _zone_less_against_instant(path: str | None, proposed: Any, base: Any) -> dict | None:
    """c11-a: a reading of a ``*_utc`` field written as a date and time with NO zone (``2021-11-15T02:17:30``), held
    against the parser's zoned instant (a SPEC ``#E`` epoch: ``…T10:17:30+00:00``), is NOT COMPARABLE, never
    "contradicts": a local time with no zone is not an instant. ``None`` for anything else (compared as before)."""
    from .records import _instant

    if not (path and path.endswith("_utc") and isinstance(proposed, str) and isinstance(base, str)):
        return None
    held = _instant(base)
    if held is None or _instant(proposed) is not None:
        return None
    iso, problem = read_local_clock_reading(proposed)
    if iso is None:
        return None
    what = "UTC" if held.utcoffset().total_seconds() == 0 else f"the instant {base}"
    return {"agrees_with_parser": None, "compared_as": "instant",
            "comparison_note": (f"the reading names no time zone; the file's value is {what} ({base}), so the two cannot "
                                f"be compared as the same instant. Write the UTC instant (e.g. {iso}Z if that is UTC) or "
                                "the local time with its zone (+HH:MM).")}


def reveal(bundle_dir: Path, target_id: str) -> dict:
    """The parser value plus a comparison with every AI reading. RECORDS AN EXPOSURE."""
    with locked(Path(bundle_dir)):
        bundle = load(bundle_dir)
        kind, obj = resolve_target(bundle, target_id)
        record_exposure(bundle, kind, target_id, "bundle reveal")
        save_bundle(bundle_dir, bundle)
    readings = [i for i in bundle.get("ai_interpretations") or () if i["target"] == {"kind": kind, "id": target_id}]
    clock = kind == "candidate" and B.is_local_clock_start(obj)
    if kind == "candidate":
        parser = {"value": obj["value"], "observed_literals": obj["observed_literals"], "value_state": obj["value_state"]}
        base, path = obj["value"], obj["target_field_path"]
        if clock:
            # c8-b: a scan start time is a LOCAL CLOCK time until the clock's zone is stated (`value` is null until
            # then); the parser's local reading of it is shown, and a reading is compared with that
            parser["local_clock_start"] = B.local_clock_start(obj, None)["local_time"]
    elif kind == "run":
        parser = {"signal_selection": obj["signal_selection"], "label": obj["label"]}
        base, path = (obj["signal_selection"] or {}).get("primary_channel"), None
    else:
        parser = {"value": None, "note": f"a {kind} has no parser value"}
        base, path = None, None
    from .records import same_value  # numbers numerically, `*_utc` as instants, strings exactly

    node = B._schema_node(path) if path else None
    declared = (node or {}).get("type")
    numeric_field = bool({"number", "integer"} & set(declared if isinstance(declared, list) else [declared]))

    def compare(r) -> dict:
        proposed = r["proposed_value"]
        if clock:
            got = compare_local_clock(obj, proposed)
            if got is not None:
                return got
        if base is None:
            return {"agrees_with_parser": None, "comparison_note": NO_PARSER_VALUE_NOTE}
        zone_less = _zone_less_against_instant(path, proposed, base)
        if zone_less is not None:
            return zone_less
        # A NUMBER GIVEN AS TEXT (`annotate --value "0.4"` without --json) for a numeric field, against a numeric
        # parser value: compared as the number it parses as, and said so — never "contradicts" for 0.4 vs "0.4"
        if (numeric_field and isinstance(proposed, str) and isinstance(base, (int, float)) and not isinstance(base, bool)):
            try:
                number = float(proposed.strip())
            except ValueError:
                number = None
            if number is not None and math.isfinite(number):
                return {"agrees_with_parser": same_value(path, number, base), "compared_as": "number",
                        "comparison_note": (f"the AI reading {proposed!r} was recorded as text (annotate without --json); "
                                            f"{path} is a number, so it was compared as {number:g} with the parser's {base!r}")}
        return {"agrees_with_parser": same_value(path, proposed, base)}

    out = []
    for r in readings:
        got = compare(r)
        out.append({"interpretation_id": r["interpretation_id"], "proposed_value": r["proposed_value"],
                    "blind": r.get("blind", False), "agrees_with_parser": got["agrees_with_parser"],
                    "relation": {True: "supports", False: "contradicts", None: None}[got["agrees_with_parser"]],
                    **{k: v for k, v in got.items() if k != "agrees_with_parser"}})
    return {
        "target": {"kind": kind, "id": target_id},
        "parser": parser,
        "ai_readings": out,
        "exposure_recorded": True,
    }


# --- LOCAL-P wiring: grouping and processing, persisted through save_bundle ----------------------


def group(bundle_dir: Path, *, regroup: bool = False) -> dict:
    """Propose record groups (``local_import.grouping``, via LOCAL-P's entry point) and
    store them in ``record_groups[]``.

    ON ``--regroup`` (reviews B-1, B-2, R-1, R-2), by each existing group's STATUS, not by
    whether some decision names it:

    * BINDING (``scientist_confirmed``): kept, and its runs are never re-proposed;
    * HISTORY (``rejected``, ``split``): kept as the record of that decision; its runs are
      proposed afresh. A fresh proposal identical to a rejected or split group is not
      re-proposed (the scientist ruled on exactly that);
    * a group whose latest status decision is ``merge``: its merge is applied again (DEC-91,
      below). Applied — another live group now holds its runs — it is kept as history
      (``merged``); NOT applied, it is exactly what it was: the fresh proposal reproduces it
      under its own id, live, and the decision stays pending (polish c3: before, it was retired
      and its runs re-proposed under a new id, so ids changed although nothing merged);
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

    result = mutate(bundle_dir, lambda bundle: _regroup(bundle, regroup=regroup))
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


def _regroup(bundle: dict, *, regroup: bool = True) -> dict:
    """:func:`group` applied to an ALREADY-LOADED bundle (the caller's lock, or a copy: the counter answer's
    preview runs it on one). Saves nothing and writes no mirror."""
    try:
        from .processing import cli_entry
    except ImportError as exc:  # pragma: no cover - the package ships with the checkout
        raise MutationRefused(f"grouping is not installed: {exc}", code=2) from exc
    from . import grouping as G

    refusal = B.legacy_refusal(bundle)
    if refusal:
        raise MutationRefused(refusal, code=2)
    existing = list(bundle.get("record_groups") or ())
    if existing and not regroup:
        raise MutationRefused("This bundle already has record groups; pass --regroup to replace the undecided ones.")
    decisions = bundle.get("scientist_decisions") or ()
    # the merge decisions in force: a group's LATEST status decision is a merge (a later confirm,
    # reject, split or defer supersedes it), applied in the order the scientist made them
    latest_status = B._decisions_by_target([d for d in decisions if d.get("decision") in B.GROUP_STATUS_DECISIONS])
    merge_decision = {
        tid: d for (kind, tid), d in latest_status.items()
        if kind == "record_group" and d.get("decision") == "merge"
    }
    # c8-s: the split decisions in force (a later confirm, reject, merge or defer supersedes one)
    split_decision = {tid: d for (kind, tid), d in latest_status.items()
                      if kind == "record_group" and d.get("decision") == "split"}
    binding = [g for g in existing if g.get("status") in B.BINDING_GROUP_STATUSES]
    # a merge-decided group is not history until its merge is applied again below
    history = [g for g in existing if g.get("status") in B.HISTORY_GROUP_STATUSES and g["group_id"] not in merge_decision]
    replaced = [g for g in existing if g not in binding and g not in history]
    kept_by_id = {g["group_id"]: g for g in binding + history}
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
    # A SPLIT IS KEPT AS NAMED (c8-s), the way a confirmed group is: its parts are proposed again under their own
    # ids, and their runs are kept out of the fresh proposal, so no counter answer or rule joins them again (before,
    # the split group's runs were proposed afresh and skipped as identical to it: they were in no group at all)
    split_made, splits_applied, splits_not_applied, side_of = ([], [], [], {}) if not split_decision else _splits_in_force(
        bundle, split_decision, {g["group_id"]: g for g in [*(bundle.get("superseded_record_groups") or ()), *existing]},
        kept_by_id, excluded)
    split_runs = {k for p in split_made for k in p["member_run_keys"]}
    if excluded or split_runs:
        view = {**bundle, "runs": [r for r in bundle.get("runs") or () if r.get("run_key") not in excluded | split_runs]}
        payload = cli_entry.build_groups_payload(view, context=bundle)
    else:
        payload = full
    # a part a decision kept as history (rejected): a fresh proposal of exactly its runs is that ruling's group
    history_parts = {frozenset(g.get("member_run_keys") or ()) for g in history if g.get("split_by_decision")}
    fresh, renamed = [], {}
    for g0 in payload["record_groups"]:
        g = dict(g0)
        if g["group_id"] in kept_by_id or (history_parts and frozenset(g.get("member_run_keys") or ()) in history_parts):
            continue  # identical to a rejected/split group (or the bound group itself)
        g["status"] = "proposed"  # only a decision moves it
        g.setdefault("condition_violations", [])  # carried; a proposed group must have none
        fresh.append(g)
    fresh += split_made
    merge_payload = payload
    if split_runs:
        # the merge check reads each run's engine-reading issues; a part's runs are outside the fresh proposal
        issues = dict(payload.get("engine_reading_issues") or {})
        per_run = dict(issues.get("per_run") or {})
        for k, v in ((full.get("engine_reading_issues") or {}).get("per_run") or {}).items():
            if k in split_runs:
                per_run.setdefault(k, v)
        merge_payload = {**payload, "engine_reading_issues": {**issues, "per_run": per_run}}
    fresh_of = {k: g["group_id"] for g in fresh for k in g.get("member_run_keys") or ()}
    merge_candidates = [dict(mc) for mc in payload.get("merge_candidates") or ()]
    bound_candidates = G.binding_merge_candidates(
        full["record_groups"], fresh, bind_of, exports_of_binding, experiment_key=exp_key
    )
    if side_of:
        # never re-asked: runs a scientist split apart (a confirmed part and its sibling)
        runs_of = {g["group_id"]: g.get("member_run_keys") or () for g in [*binding, *fresh]}
        bound_candidates = [mc for mc in bound_candidates if mc.get("run_keys") or len(mc["group_ids"]) != 2
                            or not _split_apart(side_of, *(runs_of.get(x, ()) for x in mc["group_ids"]))]
    merge_candidates += bound_candidates
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
    made = {id(d): i for i, d in enumerate(decisions)}
    for gid, d in sorted(merge_decision.items(), key=lambda kv: made[id(kv[1])]):
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
            blockers = _merge_blocker_details(bundle, merge_payload, holders, combined, d)
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
                  "detail": f"a scientist decided to merge these runs' groups, but they were not combined: {why}. "
                            "The groups stay as they are and the merge decision stays pending (each regroup applies it "
                            "again). Confirm or reject each group, or record a new decision."}
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
    # A MERGE APPLIED (now, or by an earlier regroup whose combined group is confirmed or merged on) keeps
    # its group as history: another live group holds its runs, so it is `merged` (bundle.apply_derivations).
    # One NOT applied is in `fresh` under its own id, as it was; one whose runs the proposal now groups
    # otherwise is superseded below (the decision names it).
    fresh_ids = {g["group_id"] for g in fresh}
    live_runs = {k for g in [*binding, *fresh] for k in g.get("member_run_keys") or ()}
    applied = {g["group_id"] for g in replaced if g["group_id"] in merge_decision and g["group_id"] not in fresh_ids
               and live_runs & set(g.get("member_run_keys") or ())}
    for g in replaced:
        if g["group_id"] in applied:
            g["status"] = "merged"  # what bundle.apply_derivations gives it: another live group holds its runs
    was_history = {id(g) for g in history}
    history = [g for g in existing if id(g) in was_history or g["group_id"] in applied]
    replaced = [g for g in replaced if g["group_id"] not in applied]
    keep = binding + history
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
    if excluded or split_runs:
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
                    if excluded else "") + (
                    " Runs of a group a scientist split are not joined by the answer: the split stands." if split_runs else "")
    bundle["grouping_questions"] = questions
    out = {
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
    if split_decision:
        # each split in force: the groups it holds (kept as named), and, said plainly, one applied only now (an older
        # build recorded the split without making them) or one whose lists cannot make groups
        out["splits_applied"] = splits_applied
        out["split_decisions_not_applied"] = splits_not_applied
        out["statement"] = " ".join([out["statement"], *(a["statement"] for a in splits_applied if a["applied_now"]),
                                     *(n["reason"] for n in splits_not_applied)])
    return out


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
    return (why + "; it merged nothing, and the groups stay as they are (the merge decision is pending, not applied). "
            "Decide that group again (confirm, reject, or merge with --merge-with <group id>).")


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
#: One or two letters glued to a number (``T300``, ``E1``, ``P2``, ``s1``): a label beside its value — a
#: temperature, potential, pressure, electrode or sample number — so possibly a quantity too (review:
#: ``Cu_T300`` / ``Cu_T500`` were stated nothing). A longer word with a number (``spot2``) is not.
_GLUED_QUANTITY = re.compile(r"^[a-z]{1,2}[-+]?\d+(?:p\d+)?$", re.IGNORECASE)
#: ``Rep1`` / ``rep2`` glued: on the merge path a REPLICATE label (another sample), never a repeat marker
#: (review: ``Rep1_ZnO`` / ``Rep2_ZnO``). The default grouping still reads it as a marker (unchanged).
_REPLICATE_TOKEN = re.compile(r"^rep\d+$", re.IGNORECASE)
#: Any token mixing letters and digits (``T300K``, ``E0p4V``, ``Pt0p5wt``, ``cyc10``, ``t1h``, ``spot2``) may state
#: a quantity in a shape the patterns above do not know (verification review): FAIL CLOSED, so names that
#: differ in one are never combined. A bare number is left to the counter and unit-word rules.
_LETTERS_AND_DIGITS = re.compile(r"(?=.*\d)(?=.*[a-z])", re.IGNORECASE)
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


def _merge_blockers(bundle: Mapping, payload: Mapping, holders: Sequence[Mapping], combined: Mapping,
                    decision: Mapping | None = None) -> list[str]:
    """Why ``holders`` must NOT be combined for a merge decision (the reasons of :func:`_merge_blocker_details`)."""
    return [reason for reason, _ in _merge_blocker_details(bundle, payload, holders, combined, decision)]


def _merge_blocker_details(bundle: Mapping, payload: Mapping, holders: Sequence[Mapping], combined: Mapping,
                           decision: Mapping | None = None) -> list[tuple[str, list[str]]]:
    """``(reason, next commands)`` for each reason ``holders`` must NOT be combined for a merge decision —
    empty only when nothing the import read or a scientist confirmed tells them apart (FAIL CLOSED, DEC-91):

    * every basis reading agrees (value and kind; the name stem aside), and the independent condition
      check (:func:`grouping.condition_violations`) finds only the names — otherwise they were measured
      under different conditions and are NEVER combined;
    * the file names agree once the tokens a scientist declared run counters (``set_counter_positions``,
      ``last`` where it applies) and repeat markers (``again``, ``redo`` …, :func:`_merge_name_tokens`) are
      left out — or, where they still differ, no differing token states a quantity (:data:`_CONDITION_LIKE_TOKEN`,
      :data:`_GLUED_QUANTITY`), the scientist confirmed the same sample (:data:`MERGE_SAMPLE_PATH`) for every
      run AND said, on this merge decision, that the words the names differ in are labels, not conditions
      (``same_conditions_tokens``, ``decide --same-conditions``; it covers only the words it was given for).
      The same sample is not the same conditions (review: one material measured ``pristine`` and ``cycled``
      was combined on the sample alone). A token's SHAPE alone never makes it a counter (DEC-91, third
      review): decimals split on ".", unit words and unitless values all looked like counters;
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
    exempt = _last_exempt(bundle, declared)
    kept = [_merge_name_tokens(x, declared, exempt) for x in stems]
    sample, sample_conflict = _confirmed_sample(bundle, holders)
    names_reason = unknown_reason = None
    ordered = {tuple(t for _, t, _ in k) for k in kept}
    if len(ordered) > 1 and not _differing_tokens(kept):
        # the same words in another order or another number of times (``pristine_cycled`` / ``cycled_pristine``,
        # ``ox`` / ``ox_ox``): no word to acknowledge, and nothing recorded says which reading is right (review)
        never.append("their file names hold the same words in a different order or a different number of times, so "
                     "nothing recorded can say they are one measurement")
    elif len(ordered) > 1:
        stated = _stated_quantities(stems)
        said = {str(t).casefold() for t in (decision or {}).get("same_conditions_tokens") or ()}
        if stated:
            never.append(f"their file names state different conditions ({' / '.join(stated)})")
        elif sample is None or not {t.casefold() for t in _differing_tokens(kept)} <= said:
            names_reason = _names_differ(bundle, kept, stems, declared, holders, sample, sample_conflict, said, decision)
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
    (:data:`_CONDITION_LIKE_TOKEN`, a decimal kept whole), a short label glued to a number
    (:data:`_GLUED_QUANTITY`, ``T300``), or a whole number beside a unit or label word (:data:`_UNIT_WORDS`,
    :data:`_LABEL_WORDS`), shown with that word."""
    from . import grouping as G

    lists = [[t for t in G._stem_tokens(_DECIMAL_POINT.sub("p", x)) if not G._REPEAT_TOKEN.match(t) or _REPLICATE_TOKEN.match(t)]
             for x in stems]
    sets = [set(t) for t in lists]
    differ = set().union(*sets) - set.intersection(*sets)
    out = set()
    for toks in lists:
        for j, t in enumerate(toks):
            if t not in differ:
                continue
            if (_CONDITION_LIKE_TOKEN.match(t) or _GLUED_QUANTITY.match(t) or _LETTERS_AND_DIGITS.match(t)) \
                    and not _REPLICATE_TOKEN.match(t):
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


def _merge_name_tokens(stem: str, declared: Sequence[int], exempt: Any = ()) -> list[tuple[int, str, bool]]:
    """``(1-based position, token, is the last token)`` of each file-name token a merge compares: every
    token but a repeat marker (and the number right after one, ``again_2``) and a digit token at a
    position the scientist declared a run counter (``grouping.LAST_POSITION``: the last token, unless
    ``exempt`` names this name, :func:`grouping.last_counter_exempt`). A glued ``RepN`` is compared: a
    replicate label, another sample (:data:`_REPLICATE_TOKEN`)."""
    from . import grouping as G

    toks = G._stem_tokens(stem)
    positions = {int(x) for x in G.stem_counter_positions(stem, declared, exempt)}
    out = []
    for i, t in enumerate(toks):
        marker = bool(G._REPEAT_TOKEN.match(t)) and not _REPLICATE_TOKEN.match(t)
        if marker or (t.isdigit() and i > 0 and G._REPEAT_TOKEN.match(toks[i - 1]) and not _REPLICATE_TOKEN.match(toks[i - 1])):
            continue
        if t.isdigit() and ((i + 1) in positions or (G.LAST_POSITION in positions and i == len(toks) - 1)):
            continue
        out.append((i + 1, t, i == len(toks) - 1))
    return out


def _names_differ(bundle: Mapping, kept: Sequence[Sequence[tuple]], stems: Sequence[str], declared: Sequence[int],
                  holders: Sequence[Mapping], sample: Any, sample_conflict: bool, said: set[str],
                  decision: Mapping | None) -> tuple[str, list[str]]:
    """The reason file names keep a merge apart, and the commands that would let it through: the counter
    answer when the names differ only in whole numbers at one position (or always the last token) that
    no scientist said is NOT a counter; and — unless a different sample is confirmed already — the
    question "same sample AND same conditions?": the sample confirmed for each run AND the merge recorded
    again with ``--same-conditions`` naming the words the names differ in. Either path, followed whole,
    combines the runs on the next regroup."""
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
            if all(last for _, _, last in col) and not ({p for p, _, _ in col} & said_not) and G.LAST_POSITION not in declared:
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
    sample_steps = [] if sample_conflict or sample is not None else _sample_commands(bundle, holders)
    differ = _differing_tokens(kept)
    if not sample_conflict and (sample is not None or sample_steps):
        ack = [] if {t.casefold() for t in differ} <= said else [_same_conditions_command(holders, decision)]
        same = sample_steps + ack
        text += (("; or, " if steps else " — ") + f"same sample AND same conditions? the names differ in: {' / '.join(differ)}. "
                 "Only if these runs measured the same sample under the same conditions (those words are labels, not a "
                 "treatment, state, temperature or other condition): "
                 + ("confirm the sample for each run, with the same name each time" if sample_steps else "")
                 + (", and " if sample_steps and ack else "")
                 + ("record the merge again saying so (--same-conditions)" if ack else "") + ": " + _cmds(same))
        steps = steps + same
    return text, steps


def _differing_tokens(kept: Sequence[Sequence[tuple]]) -> list[str]:
    """The compared file-name tokens (:func:`_merge_name_tokens`) not in EVERY name, casefolded-unique, sorted."""
    sets = [{t.casefold() for _, t, _ in k} for k in kept]
    if not sets:
        return []
    differ = set().union(*sets) - set.intersection(*sets)
    shown: dict[str, str] = {}
    for k in kept:
        for _, t, _ in k:
            if t.casefold() in differ:
                shown.setdefault(t.casefold(), t)
    return [shown[c] for c in sorted(shown)]


def _same_conditions_command(holders: Sequence[Mapping], decision: Mapping | None) -> str:
    """The merge decision recorded again with ``--same-conditions``, on its own target (so it REPLACES the
    refused one) and the groups now holding its runs."""
    target = ((decision or {}).get("target") or {}).get("id") or holders[0]["group_id"]
    others = [h["group_id"] for h in holders if h["group_id"] != target]
    return (f"isaac bundle decide <bundle_dir> --target {target} --decision merge --merge-with {' '.join(others)} "
            '--same-conditions --by "<your name>"')


def _last_exempt(bundle: Mapping, declared: Sequence[int]) -> Any:
    """:func:`grouping.last_counter_exempt` over every run of the bundle, when ``last`` is declared."""
    from . import grouping as G

    if G.LAST_POSITION not in declared:
        return frozenset()
    return G.last_counter_exempt(r.get("stem") or "" for r in bundle.get("runs") or ())


def _same_conditions_tokens(bundle: Mapping, kind: str, obj: Mapping, merge_with: Sequence[str] | None) -> list[str]:
    """``decide --same-conditions``: the words the merged groups' file names differ in (what the statement
    is bound to). Refused when they differ in nothing to say it of, or in a quantity (never a label)."""
    if kind != "record_group":
        raise MutationRefused("--same-conditions goes with --decision merge on a record group.")
    groups = {g["group_id"]: g for g in [*(bundle.get("superseded_record_groups") or ()), *(bundle.get("record_groups") or ())]}
    named = [obj, *(groups[x] for x in dict.fromkeys(merge_with or ()) if x in groups)]
    stems = _merge_stems(bundle, named)
    declared = list(counter_positions(bundle) or ())
    exempt = _last_exempt(bundle, declared)
    differ = _differing_tokens([_merge_name_tokens(x, declared, exempt) for x in stems])
    stated = _stated_quantities(stems)
    if stated:
        raise MutationRefused(
            f"--same-conditions cannot be said here: the file names state different quantities ({' / '.join(stated)}), "
            "and runs whose files state different conditions are never combined. Nothing was recorded; keep them as "
            "separate records (confirm each group on its own).")
    if not differ:
        raise MutationRefused(
            "--same-conditions: these groups' file names do not differ once run counters and repeat markers are left out, "
            "so there is no word to say it of. Record the merge without it. Nothing was recorded.")
    return differ


def _merges_combined(bundle: Mapping) -> dict[str, dict]:
    """``{decision_id: combined_by_merge_decision entry}``: what a regroup of ``bundle`` now would combine,
    computed by THE regroup (:func:`_regroup`) on a copy. Nothing is changed; ``{}`` when it cannot run."""
    if not bundle.get("record_groups"):
        return {}
    try:
        out = _regroup(copy.deepcopy(dict(bundle)), regroup=True)
    except MutationRefused:
        return {}
    return {x["decision_id"]: x for x in out["combined_by_merge_decision"]}


def merge_decisions_unblocked(bundle: Mapping, answer: Mapping) -> list[dict]:
    """The pending merge decisions the next regroup would combine BECAUSE of ``answer`` (a decision in
    ``bundle``): combined with it, not without it. Each regroup is run on a copy; nothing is changed."""
    with_it = _merges_combined(bundle)
    if not with_it:
        return []
    without = _merges_combined({**bundle, "scientist_decisions": [d for d in bundle.get("scientist_decisions") or () if d is not answer]})
    return [{"decision_id": did, "group_ids": list(x["from_groups"]), "combined_group_id": x["group_id"]}
            for did, x in with_it.items() if did not in without]


def counter_answer_preview(bundle: Mapping) -> dict:
    """What the latest counter answer would do on the next regroup, said before it: how many of the
    current proposed groups the grouping step would join (and into how many), how many it would split,
    and which pending merge decisions it would let the regroup combine (``merge_decisions_unblocked``:
    polish c3 — a counter answer that joins no group by the naming rule can still let a merge through,
    and the preview said "would join none"). Computed as the regroup computes it (runs of confirmed
    groups are never re-proposed; the merges by the regroup itself, on a copy). Nothing is changed."""
    from . import grouping as G

    bound = {k for g in bundle.get("record_groups") or () if g.get("status") in B.BINDING_GROUP_STATUSES
             for k in g.get("member_run_keys") or ()}
    current = {k: g["group_id"] for g in bundle.get("record_groups") or ()
               if g.get("status") in B.LIVE_GROUP_STATUSES and g.get("status") not in B.BINDING_GROUP_STATUSES
               for k in g.get("member_run_keys") or ()}
    view = {**bundle, "runs": [r for r in bundle.get("runs") or () if r.get("run_key") not in bound]}
    fresh = G.propose(view, context=bundle)["record_groups"]
    joined: set[str] = set()
    into = 0
    lands: dict[str, set[int]] = {}
    for i, g in enumerate(fresh):
        cur = {current[k] for k in g.get("member_run_keys") or () if k in current}
        for c in cur:
            lands.setdefault(c, set()).add(i)
        if len(cur) > 1:
            joined |= cur
            into += 1
    split = sum(1 for v in lands.values() if len(v) > 1)
    answer = next((d for d in reversed(bundle.get("scientist_decisions") or ())
                   if d.get("target") == {"kind": "experiment", "id": "experiment"} and d.get("decision") == "set_counter_positions"), None)
    unblocked = merge_decisions_unblocked(bundle, answer) if answer is not None else []
    regroup = "`isaac bundle group <bundle_dir> --regroup`"
    said = (f"would join {len(joined)} of the current groups into {into}" if joined else "would join none of the current groups")
    said += f" and split {split}" if split else ""
    if unblocked:
        n = len(unblocked)
        shown = "; ".join(f"{u['decision_id']}: {' + '.join(u['group_ids'])}" for u in unblocked[:5]) + (" …" if n > 5 else "")
        merges = (f"would let {n} pending merge decision{'s' if n != 1 else ''} ({shown}) combine "
                  f"{'their' if n != 1 else 'its'} groups into one proposed group{' each' if n != 1 else ''}, for the scientist to confirm")
        said = f"{said}, and {merges}" if joined or split else f"{merges} (the naming rule itself joins no other group)"
    return {
        "groups_joined": len(joined),
        "into": into,
        "groups_split": split,
        "merge_decisions_unblocked": unblocked,
        "statement": f"On the next regroup ({regroup}) this answer {said}"
                     + ". Nothing is regrouped until then; tell the scientist before regrouping.",
    }


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
    combined, dropped = _combine_groups(holders, G.group_id_for(exp_key, members + [f"merged-by:{decision['decision_id']}"]),
                                        "merged_by_scientist_decision")
    combined["merged_by_decision"] = {
        "decision_id": decision["decision_id"],
        "merged_group_id": merged_group_id,
        "merge_with": list(decision.get("merge_with") or []),
        "decided_by": (decision.get("decided_by") or {}).get("name"),
        "from_groups": [h["group_id"] for h in holders],
        "basis_keys_dropped": dropped,
        "statement": "proposed as one group because a scientist decided to merge these runs' groups; "
                     "only a confirm decision makes it a record",
    }
    return combined


def _combine_groups(holders: Sequence[Mapping], group_id: str, flag: str) -> tuple[dict, list[str]]:
    """``(group, basis keys dropped)``: ONE proposed group ``group_id`` holding every run of ``holders``, in their
    order, flagged ``flag``. What the holders agree on is kept in its basis; a key they differ on is left out."""
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
        "group_id": group_id,
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
        + [flag],
        "status": "proposed",
        "condition_violations": [],
    })
    return combined, dropped


# --- a split decision makes exactly the groups the scientist named (polish c8-s) --------------------------------


#: The flag every group a split decision made carries (beside its ``split_by_decision``).
SPLIT_PART_FLAG = "split_by_scientist_decision"


def split_command(group_id: str) -> str:
    """The split of ``group_id``, as the scientist types it (run keys from ``bundle show <bundle_dir> group <id>``)."""
    return (f"isaac bundle decide <bundle_dir> --target {group_id} --decision split --split-into "
            "'[[\"<run key>\",\"<run key>\"],[\"<run key>\"]]' --by \"<your name>\"")


def split_into_problem(bundle: Mapping, group: Mapping, split_into: Any) -> str | None:
    """Why ``split_into`` does not name groups a split of ``group`` can make, or ``None``.

    A split makes ONE group per list, so the lists must name each of the group's runs exactly once: at least
    two lists, none empty, no run key the bundle does not hold or the group does not hold, none in two lists,
    none left out. Before c8-s the lists were stored and never read: nothing checked them, and nothing used them."""
    gid = group["group_id"]
    mine = list(group.get("member_run_keys") or ())
    show = f"`isaac bundle show <bundle_dir> group {gid}` lists its {len(mine)} run key(s)"
    if not split_into:
        return (f"A split of {gid} needs --split-into: one JSON list of run keys per group to make, together naming "
                f"each of its runs once ({show}): `{split_command(gid)}`.")
    if not isinstance(split_into, (list, tuple)) or any(
            not isinstance(part, (list, tuple)) or any(not isinstance(k, str) for k in part) for part in split_into):
        return f"--split-into must be a JSON list of lists of run keys, e.g. `{split_command(gid)}`."
    if len(split_into) < 2:
        return (f"--split-into names one group; a split makes at least two (to keep {gid}'s runs together, confirm "
                "it instead).")
    if any(not part for part in split_into):
        return "--split-into holds an empty list; every group a split makes holds at least one run."
    named = [k for part in split_into for k in part]
    known = {r.get("run_key") for r in bundle.get("runs") or ()}
    unknown = list(dict.fromkeys(k for k in named if k not in known))
    if unknown:
        return (f"--split-into names no run of this bundle: {', '.join(unknown[:5])}. A run key is an entry of the "
                f"group's member_run_keys, not a run_id or a stem ({show}).")
    foreign = list(dict.fromkeys(k for k in named if k not in set(mine)))
    if foreign:
        return f"--split-into names {', '.join(foreign[:5])}, which is not a run of group {gid} ({show})."
    twice = list(dict.fromkeys(k for k in named if named.count(k) > 1))
    if twice:
        return (f"--split-into names {', '.join(twice[:5])} in more than one list; each run goes into exactly one of "
                "the groups.")
    missing = [k for k in mine if k not in set(named)]
    if missing:
        return (f"--split-into would leave out {len(missing)} run(s) of {gid}: {', '.join(missing[:5])}. Every run of "
                f"the group goes into exactly one of the lists ({show}).")
    return None


def split_part_id(exp_key: str, parent: Mapping, named: Sequence[str]) -> str:
    """The id of the part a split of ``parent`` makes from the run keys ``named`` (:func:`split_parts`):
    :func:`grouping.group_id_for` over its runs, in the parent's order, and ``split-from:<parent id>``."""
    from . import grouping as G

    want = set(named)
    order = list(parent.get("member_run_keys") or ())
    members = [k for k in order if k in want] + [k for k in dict.fromkeys(named) if k not in set(order)]
    return G.group_id_for(exp_key, members + [f"split-from:{parent['group_id']}"])


def split_parts(bundle: Mapping, parent: Mapping, decision: Mapping) -> list[dict]:
    """The groups a split ``decision`` of ``parent`` makes: ONE proposed group per list of ``split_into``, in its
    order, each holding exactly the runs that list names.

    Each part is what the grouping rule proposes over its runs alone (its basis, flags, questions, issues), its id
    derived like every other group id — :func:`grouping.group_id_for` over its runs and ``split-from:<parent id>`` —
    so it is the same on every regroup and never mistaken for a group the rule proposed. A part whose runs the
    rule would keep apart (a split of a group a merge decision combined) is combined as a merge is, its basis what
    they agree on. Proposed only: a confirm decision makes a part a record."""
    from . import grouping as G

    exp_key = G.experiment_key_of(bundle)
    lists = [list(dict.fromkeys(part)) for part in decision.get("split_into") or ()]
    runs = list(bundle.get("runs") or ())
    run_id_of = {r.get("run_key"): r.get("run_id") for r in runs}
    order = list(parent.get("member_run_keys") or ())
    out = []
    for i, named in enumerate(lists, 1):
        want = set(named)
        members = [k for k in order if k in want] + [k for k in named if k not in set(order)]
        gid = split_part_id(exp_key, parent, named)
        view = {**bundle, "runs": [r for r in runs if r.get("run_key") in want]}
        holders = [g for g in G.propose(view, context=bundle)["record_groups"] if want & set(g.get("member_run_keys") or ())]
        if len(holders) == 1 and set(holders[0].get("member_run_keys") or ()) == want:
            part = {k: v for k, v in holders[0].items() if k != "reproposed_after_group_id"}
            # a reason naming another group names one of the rule's proposals over these runs alone: not a group here
            part["split_reasons"] = [r for r in part.get("split_reasons") or () if "other_group_id" not in r]
        else:
            part, _dropped = _combine_groups(holders, gid, SPLIT_PART_FLAG) if holders else ({}, [])
            part["member_run_keys"] = members
            part["member_run_ids"] = [run_id_of[k] for k in members]
            part["context_run_keys"] = [k for k in part.get("context_run_keys") or () if k not in want]
        part.update({
            "group_id": gid,
            "experiment_key": part.get("experiment_key") or exp_key,
            "basis": part.get("basis") or {},
            "split_reasons": part.get("split_reasons") or [],
            # c8-r: never "these runs look like repeats — merge them?": the scientist named this part's runs
            "questions": [q for q in part.get("questions") or () if q.get("code") != "confirm_repeats_merge"],
            "status": "proposed",
            "merge_candidate_ids": [],
            "flags": [f for f in part.get("flags") or () if f not in ("reproposed_after_merge_decision", SPLIT_PART_FLAG)]
            + [SPLIT_PART_FLAG],
            "condition_violations": [],
            "split_by_decision": {
                "decision_id": decision.get("decision_id"),
                "split_group_id": parent["group_id"],
                "part": i,
                "of": len(lists),
                "decided_by": (decision.get("decided_by") or {}).get("name"),
                "statement": (f"proposed as one group because a scientist split group {parent['group_id']} into these "
                              "runs; only a confirm decision makes it a record"),
            },
        })
        out.append(part)
    return out


def _part_said(bundle: Mapping, part: Mapping) -> str:
    """``rg-… (2 runs: stem, stem)`` — a part as the scientist named it."""
    stem_of = {r.get("run_key"): r.get("stem") for r in bundle.get("runs") or ()}
    keys = list(part.get("member_run_keys") or ())
    stems = [str(stem_of.get(k) or k) for k in keys[:3]] + (["…"] if len(keys) > 3 else [])
    return f"{part['group_id']} ({len(keys)} run{'' if len(keys) == 1 else 's'}: {', '.join(stems)})"


def _splits_in_force(bundle: Mapping, split_decision: Mapping, groups_by_id: Mapping, kept_by_id: Mapping,
                     claimed: set) -> tuple[list[dict], list[dict], list[dict], dict]:
    """A regroup's view of every split decision in force (a group's LATEST status decision is ``split``), in the order
    the scientist made them: ``(parts to propose, splits_applied, split_decisions_not_applied, side_of)``.

    A part a decision already decided (confirmed, rejected, split again) is kept as it is by the regroup, and so is
    not proposed here; one holding a run a confirmed group holds (``claimed``) is not proposed either (that run is
    bound). ``side_of``: run key -> {split decision id: the index of the list naming it}, for every split in force,
    so no merge candidate re-asks runs a scientist split apart."""
    made = {id(d): i for i, d in enumerate(bundle.get("scientist_decisions") or ())}
    existing_ids = {g["group_id"] for g in bundle.get("record_groups") or ()}
    proposed, applied, not_applied = [], [], []
    side_of: dict[str, dict[str, int]] = {}
    claimed = set(claimed)
    for gid, d in sorted(split_decision.items(), key=lambda kv: made.get(id(kv[1]), 0)):
        parent = groups_by_id.get(gid)
        problem = (split_into_problem(bundle, parent, d.get("split_into")) if parent is not None
                   else f"group {gid} is not a group of this bundle")
        if problem is not None:
            not_applied.append({
                "decision_id": d.get("decision_id"), "group_id": gid,
                "reason": (f"the split decision {d.get('decision_id')} of group {gid} made no group: {problem} Its runs "
                           "are proposed afresh, and a proposal identical to the split group is not proposed again. "
                           "Decide the split again, naming each of its runs once."),
                "next_commands": [split_command(gid)],
            })
            continue
        parts = split_parts(bundle, parent, d)
        for i, part in enumerate(parts):
            for k in part["member_run_keys"]:
                side_of.setdefault(k, {})[d["decision_id"]] = i
        now = not any(p["group_id"] in existing_ids for p in parts)
        listed = []
        for part in parts:
            kept = kept_by_id.get(part["group_id"])
            if kept is None and not claimed & set(part["member_run_keys"]):
                claimed |= set(part["member_run_keys"])
                proposed.append(part)
            listed.append({"group_id": part["group_id"], "member_run_keys": part["member_run_keys"],
                           "status": kept.get("status") if kept is not None else "proposed"})
        said = "; ".join(_part_said(bundle, p) for p in parts)
        applied.append({
            "decision_id": d.get("decision_id"), "group_id": gid, "applied_now": now, "groups": listed,
            "statement": (f"Split {d.get('decision_id')} of group {gid} applied now (an earlier build recorded it without "
                          f"making its groups): {len(parts)} proposed groups, one per list — {said}. Confirm each."
                          if now else f"Split {d.get('decision_id')} of group {gid} kept as named: {said}."),
        })
    return proposed, applied, not_applied, side_of


def _split_apart(side_of: Mapping, *run_sets: Iterable[str]) -> bool:
    """``True`` when the runs of two groups lie in different lists of one split in force."""
    sides = []
    for runs in run_sets:
        got: dict[str, set] = {}
        for k in runs:
            for did, i in (side_of.get(k) or {}).items():
                got.setdefault(did, set()).add(i)
        sides.append(got)
    a, b = sides
    return any(did in b and len(a[did] | b[did]) > 1 for did in a)


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
        superseded = {g["group_id"] for g in bundle.get("superseded_record_groups") or ()}
        # `--group` processes ONLY those groups: every other group's results (decided or not) are kept as they are
        untouched = set() if not group_ids else {g for g in {r.get("group_id") for r in bundle.get("processing_results") or ()}
                                                     if g not in set(group_ids)}
        # a group that is no longer live was not processed: its results stay exactly as they were
        untouched |= set(skip)
        # A fresh result of the same id holds the version with the provenance the latest selection recorded (project
        # file, Athena group, data hash; a set's names its members): it replaces the old one, the selection re-pointed.
        # c10-r: when it holds NO such version, the selection is never carried over to another curve and never left
        # silently on a stale result: the fresh result replaces the old one, says which choice no longer matches,
        # and the question is asked again. A result with nothing fresh to replace it is kept as it was.
        fresh_by_id = {B.processing_id(r): r for r in produced}
        not_carried: list[tuple[str, Mapping, Mapping]] = []
        for r in bundle.get("processing_results") or ():
            d = B.latest_athena_selection(bundle, r)
            pid = B.processing_id(r)
            if d is None or pid in decided or r.get("group_id") in superseded or r.get("group_id") in untouched:
                continue
            if pid not in fresh_by_id:
                decided.add(pid)
            elif B.athena_resolve(fresh_by_id[pid], d) is None:
                not_carried.append((pid, d, fresh_by_id[pid]))
        for pid, d, r in not_carried:
            _say_athena_choice_not_carried_over(r, d)
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
        if not_carried:
            line = _athena_choices_not_carried_over_line(not_carried)
            out["athena_selections_not_carried_over"] = {
                "results": [{"result_id": pid, "decision_id": d.get("decision_id"), "value": d.get("value")}
                            for pid, d, _ in not_carried],
                "statement": line}
            if isinstance(out.get("summary"), Mapping):
                out["summary"] = {**out["summary"], "lines": [*(out["summary"].get("lines") or ()), line]}
        new_curve = decided_results_with_a_new_all_zero_skip(bundle, keep, fresh)
        if new_curve:
            out["decided_results_with_a_scan_now_left_out"] = new_curve
            if isinstance(out.get("summary"), Mapping):
                out["summary"] = {**out["summary"],
                                  "lines": [*(out["summary"].get("lines") or ()), *(x["statement"] for x in new_curve)]}
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


def decided_results_with_a_new_all_zero_skip(bundle: Mapping, keep: Sequence[Mapping], fresh: Sequence[Mapping]) -> list[dict]:
    """c11-r: one line per DECIDED ISAAC result kept as it was whose group's fresh result (this build) now leaves out a
    scan the decided one merged, because its signal is zero at every point (``signal_all_zero``). The fresh curve has
    a new id; the decision still stands on the old id until the scientist changes it. ``[]`` when there is none."""
    decisions = B.processing_state_decisions(bundle)
    out = []
    for old in keep:
        if old.get("source") != "isaac_protocol":
            continue
        pid = B.processing_id(old)
        d = decisions.get(("processing_result", pid))
        if d is None:
            continue
        merged = {i.get("source_id") for i in old.get("inputs") or () if not i.get("skip_reason")}
        for new in fresh:
            if new.get("group_id") != old.get("group_id") or new.get("source") != "isaac_protocol":
                continue
            left = [i for i in new.get("inputs") or ()
                    if i.get("skip_reason") == C_SIGNAL_ALL_ZERO and i.get("source_id") in merged]
            if not left:
                continue
            nid = B.processing_id(new)
            names = ", ".join(PurePosixPath(str(i.get("relative_path") or i.get("source_id"))).name for i in left)
            what = d.get("decision")
            stands = "The old approval still stands" if what == "approve" else f"The earlier decision ({what}) still stands"
            said = (f"Group {old.get('group_id')}: {pid} ({what} by {(d.get('decided_by') or {}).get('name')}) merged "
                    f"{names}, whose signal is zero at every point; this build leaves {'it' if len(left) == 1 else 'them'} "
                    f"out, so the fresh curve is a new result, {nid}. The scientist can approve the new curve "
                    f'(`isaac bundle decide <bundle_dir> --target {nid} --decision approve --qc-status <value> --by '
                    f'"<your name>"`). {stands} on {pid} until they change it.')
            out.append({"group_id": old.get("group_id"), "decided_result_id": pid, "new_result_id": nid,
                        "left_out": [i.get("relative_path") or i.get("source_id") for i in left], "statement": said})
    return out


#: ``processing.core.SIGNAL_ALL_ZERO`` (not imported: processing is an optional extra).
C_SIGNAL_ALL_ZERO = "signal_all_zero"


def _say_athena_choice_not_carried_over(result: dict, decision: Mapping) -> None:
    """c10-r: on the fresh ``result``, which the scientist's latest ``select_athena_version`` no longer resolves on,
    record that it was not carried over (:data:`bundle.ATHENA_NOT_CARRIED_OVER`) and, when it lists versions, say so
    in its question, which is asked again (``athena_result_of_record`` stays ``None`` until they answer)."""
    who = (decision.get("decided_by") or {}).get("name")
    lists = bool(B.athena_version_ids(result))
    said = (f"The earlier choice {decision.get('value')} ({decision.get('decision_id')}, by {who}) is not one of the "
            "Athena versions ISAAC lists now, so it is not carried over to another curve"
            + (" and the question is asked again." if lists else "; this result lists no Athena versions to choose between now."))
    result[B.ATHENA_NOT_CARRIED_OVER] = {"decision_id": decision.get("decision_id"), "value": decision.get("value"),
                                         "decided_by": who, "statement": said}
    if lists and not any(isinstance(q, Mapping) and q.get("code") == B.ATHENA_QUESTION_CODE for q in result.get("questions") or ()):
        result["questions"] = [*(result.get("questions") or ()), B.athena_question(result)]
    for q in result.get("questions") or ():
        if isinstance(q, dict) and q.get("code") == B.ATHENA_QUESTION_CODE:
            q["text"] = f"{q.get('text', '')} {said}".strip()


def _athena_choices_not_carried_over_line(items: Sequence[tuple[str, Mapping, Mapping]]) -> str:
    """ONE plain line naming each earlier result-of-record choice that no longer matches a listed version."""
    parts = []
    for pid, d, r in items:
        who = (d.get("decided_by") or {}).get("name")
        part = f"{pid}: {d.get('value')} ({d.get('decision_id')}, by {who})"
        if not B.athena_version_ids(r):
            part += ", which now lists no Athena versions to choose between"
        parts.append(part)
    n = len(items)
    asked = any(B.athena_version_ids(r) for _, _, r in items)
    return (f"{n} earlier choice(s) of the Athena result of record no longer match a version ISAAC lists after this "
            f"re-processing ({'; '.join(parts)}): the project files, or how ISAAC reads them, changed. "
            f"{'It is' if n == 1 else 'They are'} not carried over to another curve: no version is selected for "
            f"{'that result' if n == 1 else 'those results'} now"
            + (", and the question \"Which one is the result of record?\" will be asked again." if asked else "."))


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
                # c12-cal: the shift size the scientist confirmed (--accept-shift), only when they did
                **({"accepted_shift_eV": d["value"]["accepted_shift_eV"]}
                   if isinstance(d.get("value"), Mapping) and d["value"].get("accepted_shift_eV") is not None else {}),
            }
    return out


def _latest_calibration_step(bundle: Mapping, group_id: str) -> tuple[Mapping | None, Mapping | None]:
    """(the calibration step, the qc step) of the group's latest ISAAC processing result that has one."""
    for r in reversed(bundle.get("processing_results") or ()):
        if r.get("group_id") == group_id and r.get("source") == "isaac_protocol":
            steps = {s.get("step"): s for s in r.get("steps") or () if isinstance(s, Mapping)}
            if "calibration" in steps:
                return steps["calibration"], steps.get("qc")
    return None, None


def _carried_shifts(bundle: Mapping, group_id: str, warn: float) -> list[tuple[str, dict]]:
    """``[(result id, reference.carried_shift)]`` for the group's DECIDED (approved) ISAAC results whose curve carries
    a calibration shift."""
    from .processing import reference as REF

    out = []
    for r in bundle.get("processing_results") or ():
        if r.get("group_id") != group_id or r.get("source") != "isaac_protocol" or r.get("state") != B.STATE_SCIENTIST_CONFIRMED:
            continue
        cal = next((s for s in r.get("steps") or () if isinstance(s, Mapping) and s.get("step") == "calibration"), None)
        c = REF.carried_shift(cal, warn_eV=warn) if cal else None
        if c is not None:
            out.append((B.processing_id(r), c))
    return out


def calibration_shift_said(bundle: Mapping, group_id: str, element: str, edge: str, accepted: float | None) -> str:
    """What approving ``element`` ``edge`` as group ``group_id``'s calibration reference would apply, in one or two
    sentences, from its latest ISAAC result; RAISES :class:`MutationRefused` (nothing recorded) when no reference is
    proposed, when the shift would never be applied (implausible), or when a shift above the protocol's warning
    level is not confirmed by ``accepted`` (``--accept-shift``) matching the shift said."""
    from .processing import protocol as PP
    from .processing import reference as REF

    warn = float(PP.DEFAULT_PARAMS["qc"]["warn_energy_shift_eV"])
    cal, qc = _latest_calibration_step(bundle, group_id)
    if cal is None:
        return (f"{group_id} has no processing result yet, so the shift is not known: the next `process --group "
                f"{group_id}` computes it ({element} {edge}'s tabulated edge minus the measured reference edge). A shift "
                f"above the protocol's {warn:g} eV warning level is not applied without its size confirmed: approve "
                "again then with --accept-shift <the shift shown>.")
    # c12-r (REF.STRICTER_ONLY_RULE_ID): never a params file's higher warning level
    warn = REF.effective_warn_eV(((qc or {}).get("params") or {}).get("warn_energy_shift_eV") or warn)
    w = REF.would_apply(cal, element, edge, warn_eV=warn)
    if not REF.reading(cal)["reference_proposed"]:
        # c12-r: a DECIDED result approved under an older build may carry a shift from this reference: confirming
        # its exact size (--accept-shift) is the scientist keeping that curve; nothing else can be approved
        carried = _carried_shifts(bundle, group_id, warn)
        mine = [(pid, c) for pid, c in carried if (c["element"], c["edge"]) == (element, edge)]
        if accepted is not None:
            match = next(((pid, c) for pid, c in mine if REF.shift_size_confirmed(accepted, c["applied_shift_eV"])), None)
            if match is not None:
                pid, c = match
                return (f"You confirmed the {c['shown']} eV that the approved result {pid} carries ({element} {edge}). "
                        f"{REF.reading(cal)['reference_statement']} So a re-processed result does not carry it: only "
                        f"{pid} does.")
        kept = "".join(f" The approved result {pid} carries {c['shown']} eV from an earlier approval: to keep it, "
                       f"approve again with --accept-shift {c['shown']} if the scientist confirms that size; or reject "
                       f"that result (`--target {pid} --decision reject`)." for pid, c in (mine or carried)[:2])
        raise MutationRefused(f"No calibration shift can be approved for {group_id}: {w['statement']}{kept} "
                              "Nothing was recorded.")
    if w["implausible"]:
        raise MutationRefused(f"{w['statement']} Nothing was recorded.")
    if w["shift_eV"] is None:
        return w["statement"]
    if accepted is not None and not REF.shift_size_confirmed(accepted, w["shift_eV"]):
        raise MutationRefused(f"--accept-shift {REF.shown(accepted)} is not the shift approving applies: {w['statement']} "
                              f"Pass --accept-shift {w['shown']} if that is the size you accept. Nothing was recorded.")
    if w["needs_size_confirmation"] and accepted is None:
        raise MutationRefused(f"{w['statement']} Say the size to the scientist; if they accept it, record it with "
                              f"--accept-shift {w['shown']}. Nothing was recorded.")
    return w["statement"].split(" That is more than")[0] + (" You confirmed that size." if accepted is not None else "")


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
