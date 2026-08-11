"""Experiment store for the local UI prototype.

An *experiment* is the UI's unit of work: a synthetic draft plus whatever the
operator has confirmed and exported. Everything lives under a workspace directory
OUTSIDE the repo (``ISAAC_UI_WORKSPACE`` env, default ``/tmp/isaac-ui-workspace``),
mirroring how ``cli.cmd_export`` / ``run_synthetic_demo.py`` take an explicit output
dir. The store is deterministic and Graphify-free; it only reads the two committed
synthetic fixtures and calls the unchanged core functions.

Layout::

    <workspace>/<experiment_id>/experiment.json      # persisted state
    <workspace>/<experiment_id>/records/             # exported <record_id>.json + .evidence.json

Status is DERIVED on read (never stored stale) from the current draft via an
in-memory dry-run of ``export_draft`` — nothing is written to derive status.

Runs
----

An experiment carries zero or more :class:`Run` objects — one measurement
*condition* each. One Run exports to exactly one ISAAC record; an ``Experiment``
is an application-level grouping with no schema counterpart. That mapping is
decided by the official schema rather than by preference and is settled in
``docs/superpowers/specs/2026-08-08-scientist-capture-data-contract.md`` §1.
Experiment-level fields are inherited BY REFERENCE and never copied down (§2 D2);
see :func:`resolve_inherited`. Runs currently live inside the experiment's
own state document; §8 D7 moves them to relational rows in a later migration.

Scopes
------

A *scope* is a DIRECTORY NAMESPACE, not a filter. There are exactly two kinds:

* the NORMAL scope, rooted at ``workspace_root()``. It is where a real record
  would live. It is **never auto-seeded**: on a fresh deployment it is empty and
  it stays empty until something explicitly creates a record in it.
* a TUTORIAL scope, rooted at ``workspace_root()/_tutorial/<session_id>``. The
  five canonical worked-example records live ONLY here, one independent copy per
  session.

Exclusion of the worked examples from a normal read is therefore STRUCTURAL —
they are not in the directory being enumerated — rather than a predicate some
future caller could forget to apply. ``_tutorial`` is a safe namespace name
because ``isaac_records.ids.RECORD_ID_RE`` (``\\A[0-9A-Z]{26}\\Z``) can never match a
``_``-prefixed name, so no record id can ever collide with it; ``_experiment_dirs``
additionally skips ``_``-prefixed entries as a stated rule rather than relying on
that.

The FILESYSTEM is the session registry: a tutorial session exists iff its
directory exists. There is deliberately no in-memory registry — one would be lost
on a pod restart (stranding every session's files with nothing to attribute them
to) and would make cleanup non-idempotent.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from isaac_records.complete import apply_answers
from isaac_records.draft_validator import validate_draft
from isaac_records.export import export_draft
from isaac_records.extract.draft_builder import build_draft
from isaac_records.ids import is_record_id, new_record_id
from isaac_records.models import derivation

#: PATH-FREE BY RULE, like every other log line this application emits: a record
#: id and an exception CLASS NAME, never a message, a filesystem path, a host or a
#: credential. A log line is an exfiltration surface too (P30.6), and an ``OSError``
#: message in particular carries the filename it failed on.
_log = logging.getLogger("isaac_api.workspace")

# --- repo + fixture locations -------------------------------------------------


def _find_repo_root() -> Path:
    """Walk up from this file until the vendored official schema is found."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            return candidate
    # Fallback: apps/api/isaac_api/workspace.py -> repo root is parents[3].
    return here.parents[3]


REPO_ROOT = _find_repo_root()
SYN_DIR = REPO_ROOT / "tests" / "fixtures" / "synthetic"
CSV_PATH = SYN_DIR / "mock_campaign.csv"
LISTING_PATH = SYN_DIR / "raw_scan_listing.txt"
ANSWERS_PATH = SYN_DIR / "xanes_completion_answers.json"

# Source files an experiment is built from (also the source-preview allowlist).
SOURCE_FILES = (CSV_PATH.name, LISTING_PATH.name)

# The committed synthetic-demo provenance marker. A non-canonical experiment is
# recognised as belonging to the managed synthetic-demo dataset when its
# ``source.description`` equals this string and/or its ``source.files`` is a
# non-empty subset of SOURCE_FILES. See ``classify_experiment``.
MANAGED_SOURCE_DESCRIPTION = (
    "Synthetic XANES campaign (CuO, Cu K-edge) — committed demo fixtures"
)

DEFAULT_WORKSPACE = "/tmp/isaac-ui-workspace"

# Derived status values (product vocabulary for the UI).
NEEDS_ATTENTION = "needs_attention"
IN_REVIEW = "in_review"
READY_TO_EXPORT = "ready_to_export"
DONE = "done"


def workspace_root() -> Path:
    """The NORMAL scope's root (env-overridable, resolved fresh so tests can monkeypatch).

    This is the root of the normal scope only. It is never auto-seeded. Use
    :func:`scope_root` when a caller may be operating inside a tutorial session.
    """
    return Path(os.environ.get("ISAAC_UI_WORKSPACE", DEFAULT_WORKSPACE))


# --- scopes: the normal workspace vs. an isolated tutorial session -------------

#: The single directory under ``workspace_root()`` that holds every tutorial
#: session. Chosen ``_``-prefixed so it can never be mistaken for (or collide
#: with) a record id: ``RECORD_ID_RE`` is ``\A[0-9A-Z]{26}\Z``.
TUTORIAL_NAMESPACE = "_tutorial"

#: The per-session marker file. It sits at the session ROOT, never inside an
#: experiment directory, and it is not named ``experiment.json`` — so
#: ``_experiment_dirs`` (which enumerates directories containing an
#: ``experiment.json``) can never mistake it for a record.
TUTORIAL_MARKER = "session.json"

#: How long an untouched tutorial session survives before the sweep removes it.
TUTORIAL_TTL_HOURS = 24

#: A session id is SERVER-GENERATED by ``secrets.token_urlsafe(16)``, whose
#: alphabet is exactly ``[A-Za-z0-9_-]`` (22 characters for 16 bytes). This
#: pattern is the path-traversal boundary for the whole tutorial namespace, so it
#: is an ALLOWLIST rather than a denylist of bad shapes: no ``.``, no ``/``, no
#: ``\``, no NUL, no empty string, nothing shorter than 16 or longer than 64.
#:
#: ANCHORED IN THE PATTERN, with ``\A``/``\Z``. It was previously written bare —
#: ``[A-Za-z0-9_-]{16,64}`` — with a comment justifying the omission by arguing
#: that ``re.fullmatch`` "cannot be defeated by ``$``'s trailing-newline
#: tolerance". That rationale defended an anchor the pattern did not contain:
#: there was no ``$`` here to be tolerant, and the reasoning quietly assumed the
#: single ``fullmatch`` call site would stay a ``fullmatch`` forever.
#:
#: It would not survive that assumption breaking. Measured: change the call in
#: ``is_tutorial_session_id`` from ``fullmatch`` to ``match`` and the bare pattern
#: accepts ``"abcdefghijklmnop" + "\n" + "../../etc/passwd"`` — arbitrary-suffix
#: path injection, at a boundary whose polarity is ALLOW at every consumer and one
#: of whose consumers is DESTRUCTIVE (``dispose_tutorial_session`` below, called on
#: a name read off the filesystem).
#:
#: ``\A``/``\Z`` and not ``^``/``$``: Python's ``$`` also matches before a trailing
#: newline, so ``^...$`` with ``.match()`` would admit exactly the injection above
#: with the traversal on its own line. ``\Z`` is end-of-string, full stop. With
#: ``fullmatch`` the anchors are redundant, which is the point — the exactness now
#: lives in the pattern, so no future caller can reopen the hole by reaching for a
#: different ``re`` method. ``tests/test_tutorial_session_id.py`` pins both the
#: behaviour and the redundancy.
_SESSION_ID_RE = re.compile(r"\A[A-Za-z0-9_-]{16,64}\Z")


class InvalidTutorialSession(ValueError):
    """A tutorial session id that is not of the server-minted shape.

    Deliberately carries a FIXED, path-free message. The rejected id is not echoed
    and no filesystem path is interpolated: this exception is raised on the request
    path from caller-supplied input, and an error string that quoted either would
    turn a traversal attempt into a filesystem oracle.
    """

    def __init__(self) -> None:
        super().__init__("invalid tutorial session id")


def is_tutorial_session_id(session_id: object) -> bool:
    """Whether ``session_id`` has the server-minted shape. Never raises."""
    return isinstance(session_id, str) and _SESSION_ID_RE.fullmatch(session_id) is not None


def validate_tutorial_session_id(session_id: str) -> str:
    """Return ``session_id`` if it is well-formed, else raise :class:`InvalidTutorialSession`."""
    if not is_tutorial_session_id(session_id):
        raise InvalidTutorialSession()
    return session_id


def tutorial_namespace_root() -> Path:
    """The directory holding every tutorial session (``<workspace>/_tutorial``)."""
    return workspace_root() / TUTORIAL_NAMESPACE


def scope_root(session_id: str | None = None) -> Path:
    """The root directory of a scope.

    ``None`` -> the normal scope (``workspace_root()``). Otherwise the tutorial
    session's own root, after validating the id — so every path built from a
    caller-supplied session id passes through the traversal boundary exactly once,
    here.
    """
    if session_id is None:
        return workspace_root()
    return tutorial_namespace_root() / validate_tutorial_session_id(session_id)


def tutorial_session_exists(session_id: str) -> bool:
    """Whether this tutorial session exists. Raises on a malformed id.

    The filesystem IS the registry: the session exists iff its directory exists.
    A directory with a missing or unparseable marker still EXISTS (so a request
    against it is answered rather than mis-reported as unknown); the stale sweep is
    what removes it, treating an unmarked session as expired.
    """
    return scope_root(session_id).is_dir()


def is_synthetic_only() -> bool:
    """Whether this deployment is the synthetic-only demo.

    Delegates to the single authoritative runtime-mode source
    (``isaac_api.runtime_mode``) which both this guard and the ``/health`` mode
    banner read from, so they can never drift apart. The function is kept defined
    here because existing callers (and the reset test's monkeypatch) reference
    ``ws.is_synthetic_only``; it now reflects the fail-closed
    ``ISAAC_RUNTIME_MODE`` resolution instead of a literal.

    The guarded reset gates on this function; its deeper defence-in-depth remains
    provenance classification (a non-managed / real record lacks
    ``MANAGED_SOURCE_DESCRIPTION`` -> classifies AMBIGUOUS -> the reset refuses
    with zero mutation).
    """
    from . import runtime_mode

    return runtime_mode.is_synthetic_only()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically and durably (crash-safe).

    A partially-written file must NEVER be observable by a reader: the bytes are
    written to a uniquely-named temp file in the SAME directory (so the final
    ``os.replace`` is an atomic same-filesystem rename), flushed + ``os.fsync``-ed,
    then renamed over the target. ``os.replace`` swaps atomically, so a concurrent
    reader always sees the complete OLD or complete NEW file — never a truncated
    one. On any failure the temp file is removed and the exception re-raised,
    leaving the previous target (if any) untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        tmp = Path(tmp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # atomic swap; no partial-target window
        tmp = None  # ownership transferred to the target
    finally:
        # If we failed before/at the swap, drop the orphaned temp file so no
        # ``.experiment.json.*.tmp`` litter survives a crashed write.
        if tmp is not None:
            try:
                tmp.unlink()
            except FileNotFoundError:  # pragma: no cover - already gone
                pass


def load_demo_answers() -> dict:
    """The committed synthetic completion answers (SIMULATED human input)."""
    return json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))


# --- per-record mutation lock -------------------------------------------------
#
# The deployed server is single-process uvicorn (no ``--workers``); sync route
# handlers run in Starlette's threadpool, so concurrent writers are threads in ONE
# process. This in-process per-record lock serialises the load->compare->mutate->
# save compare-and-swap critical section so two writers holding the same token can
# never both succeed — exactly one wins and the loser observes a stale token.

_record_locks: dict[str, threading.RLock] = {}
_record_locks_guard = threading.Lock()


def _lock_key(experiment_id: str, session_id: str | None) -> str:
    """The scope-qualified lock key.

    The SCOPE IS PART OF THE KEY. Two tutorial sessions legitimately hold records
    with the SAME canonical id, and those are different files; if they shared a
    lock, a mutation in one session would serialise against — and could be delayed
    indefinitely by — an unrelated mutation in another. Injective by construction:
    neither a session id (``[A-Za-z0-9_-]{16,64}``) nor a record id
    (``\\A[0-9A-Z]{26}\\Z``) can contain ``/``, so the two halves cannot be confused.
    """
    return f"{session_id or ''}/{experiment_id}"


@contextlib.contextmanager
def record_lock(experiment_id: str, *, session_id: str | None = None):
    """Serialise the compare-and-swap critical section for one experiment id in one scope.

    A REENTRANT lock (``RLock``): across two threads it behaves exactly like a
    plain ``Lock`` (they still serialise on the same scope+id), but the SAME thread
    may re-acquire it.

    Reentrancy is retained deliberately, with an honest note about WHY. It was
    originally required because every read (``list_experiments`` /
    ``load_experiment``) called ``ensure_seeded``, so a mutation handler holding
    ``record_lock(id)`` would re-enter the same lock through its own reload. Reads
    no longer seed — seeding is now an explicit tutorial-session-creation step — so
    that particular self-deadlock path no longer exists. ``RLock`` is kept because
    it is strictly weaker than nothing and stronger than a plain ``Lock`` for a
    future re-entrant caller; downgrading it would be a silent trap.
    """
    key = _lock_key(experiment_id, session_id)
    with _record_locks_guard:
        lock = _record_locks.setdefault(key, threading.RLock())
    with lock:
        yield


# --- experiment record --------------------------------------------------------


def _legacy_generation(rid: str) -> str:
    """Deterministic generation fallback for a legacy / bare record.

    A pre-P27.3 state file (or a bare construction) carries no ``generation``; this
    derives a stable, non-empty nonce from the record id so such a record has a
    consistent generation across every load (hence a stable ETag). Legacy records
    are never recreated, so a deterministic value is safe for them.
    """
    return hashlib.sha256(("gen:" + rid).encode("utf-8")).hexdigest()[:16]


def _new_generation() -> str:
    """A fresh opaque generation nonce (16 lowercase hex chars).

    Random with no secret meaning and no path/content — safe to expose in a token.
    Minted at genuine (re)creation to defeat a rev-0 -> rev-0 ABA.
    """
    return secrets.token_hex(8)


def _existing_generation(rid: str, *, session_id: str | None = None) -> str | None:
    """The persisted ``generation`` of an on-disk record, or ``None``.

    Reads ``scope_root(session_id)/rid/experiment.json`` and returns its stored
    non-empty ``generation`` string if the file exists and parses; otherwise
    ``None`` (an ad-hoc new id has no prior file -> a fresh generation is minted).
    Preserving the on-disk generation for an explicit existing id keeps a no-op
    upsert from churning the token. NOTE (W1, 2026-08-01): `POST /api/demo/run` no
    longer performs this upsert at all — it writes nothing on a pristine target and
    refuses on a drifted one — so the demo is no longer a live caller of this path.
    The behaviour is retained because `create_experiment` still exposes it.
    """
    state_path = scope_root(session_id) / rid / "experiment.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        gen = state["generation"]
        return gen if isinstance(gen, str) and gen else None
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


# --- the Run: one condition, one record ---------------------------------------
#
# WHY A RUN EXISTS AT ALL, decided by the official schema and not by preference.
# The reasoning is settled in
# ``docs/superpowers/specs/2026-08-08-scientist-capture-data-contract.md`` §1 and
# must not be re-derived here: ``context.required = ["environment",
# "temperature_K"]`` and ``temperature_K`` is a SCALAR, so one ISAAC record cannot
# express two temperatures. ``timestamps.split_operation`` exists precisely to note
# a multi-condition split, ``tags`` is the schema's designated campaign grouping,
# and ``links[]`` (``replica_of`` / ``replicate_preparation``) is how sibling runs
# are re-associated.
#
# DECISION D1 (contract §1): **one Run produces exactly one ISAAC record.** An
# ``Experiment`` is an application-level grouping with NO schema counterpart; it
# exports to N records, one per Run.
#
# WHAT THIS MODULE DOES NOT DO, deliberately. Export still mints exactly one
# record per draft (``src/isaac_records/export.py``). Export fan-out is a LATER
# slice. This slice makes the Run exist, persist and round-trip; it changes no
# export behaviour, no route, no migration and nothing under
# ``src/isaac_records/`` or ``schema/``.
#
# WHAT THE FAN-OUT SLICE MUST CHANGE. This list named only ``record_id`` and was
# incomplete; the derivations are the larger half of the work:
#
# * ``Experiment.record_id`` — the singular field the current 1:1 path writes. Per
#   contract §1 D1 the record identity is per-Run (``Run.record_id``).
# * ``Experiment.status`` / ``pending`` / ``export_ready`` — ALL THREE ARE
#   RUN-BLIND. They derive from ``self.draft`` and ``self.exported()`` alone and
#   never consult ``self.runs``, so an experiment whose OWN draft is clean reports
#   ``ready_to_export`` (or ``done``) no matter what its runs contain: a run with
#   unanswered pending blockers, or one that would fail the export gate, is not
#   counted anywhere. This is UNREACHABLE TODAY — no route touches runs and nothing
#   creates one in production — which is why it is recorded here rather than fixed
#   in this slice. It stops being latent the moment a route can add a run, and
#   fixing it is part of fan-out, not a follow-up to it: once one Experiment exports
#   to N records, "is this ready?" is a question about N drafts and has no
#   single-draft answer. Whether the aggregate is "all runs ready" or "any run
#   ready", and how a zero-run experiment answers, is a product decision that slice
#   must make explicitly rather than inherit from the 1:1 shape.

# A DRAFT IS NOT SHAPED LIKE A RECORD, AND THE CONTRACT'S §2 LISTS WERE WRITTEN AS
# IF IT WERE. This is a correction, recorded rather than quietly applied.
#
# Contract §2 enumerates the experiment/run split in OFFICIAL SCHEMA-PATH space —
# it cites ``schema/isaac_record_v1.json`` line numbers for every entry. The first
# implementation of this module applied those lists directly to DRAFT FIELD KEYS,
# on the stated assumption that "a draft field key is a dotted schema path, so
# membership is a prefix test". That assumption is false for 7 of the 14 entries,
# and independent review measured which ones. A draft (``schema/isaac_draft.schema.json``)
# has TWO namespaces, not one:
#
# 1. ``draft["fields"]`` — a map of dotted official path -> evidence envelope,
#    SCALARS ONLY. ``sample.material.name``, ``context.temperature_K``,
#    ``system.facility.beamline``, ``timestamps.acquired_start_utc`` live here.
# 2. TOP-LEVEL DRAFT BLOCKS, siblings of ``fields``, which are arrays/objects and
#    are NOT dotted paths at all: ``series``, ``qc``, ``assets``,
#    ``descriptors_outputs``, ``attribution``, ``tags``, ``links``, ``implicit``.
#
# So the schema-space entry ``measurement.series[]`` is the draft block ``series``;
# ``measurement.qc`` is ``qc``; ``descriptors.outputs[]`` is ``descriptors_outputs``;
# ``attribution.contributors`` is inside the ``attribution`` block
# (``extract/draft_builder.py:269``); and ``tags`` is a block, not a field key.
# Applied to field keys, those prefixes match NOTHING — ``field_level("qc")`` and
# ``field_level("series")`` returned ``unclassified``, and the experiment-level
# ``attribution``/``tags`` inherited nothing at all.
#
# The lists below are therefore split by NAMESPACE. The contract itself is
# corrected in the same commit (§2, "Correction 2026-08-08").

#: Draft FIELD-MAP path prefixes (keys of ``draft["fields"]``) that are entered once
#: on the experiment and inherited by every Run. Segment-aware prefixes.
#:
#: ``system.instrument`` is a real official schema path (``system.properties`` =
#: ``{configuration, domain, facility, instrument, technique}``) that the current
#: deterministic extractor never emits — ``extract/structured.FIELD_MAP`` has no
#: entry for it. It is retained because it is correct for the namespace and costs
#: nothing; it is simply unexercised today, which is a different thing from wrong.
EXPERIMENT_LEVEL_FIELD_PATHS: tuple[str, ...] = (
    "sample",
    "system.domain",
    "system.technique",
    "system.facility",
    "system.instrument",
)

#: Draft FIELD-MAP path prefixes that are per-Run. ``context.*`` is the one that
#: forces the record split (``context.temperature_K`` is a required scalar).
RUN_LEVEL_FIELD_PATHS: tuple[str, ...] = (
    "context",
    "timestamps.acquired_start_utc",
    "timestamps.acquired_end_utc",
)

#: TOP-LEVEL DRAFT BLOCK keys that are experiment-level. ``attribution`` holds
#: ``contributors`` (contract §2's ``attribution.contributors``); ``tags`` is the
#: schema's campaign grouping. Neither is a ``fields`` key.
EXPERIMENT_LEVEL_BLOCKS: tuple[str, ...] = ("attribution", "tags")

#: TOP-LEVEL DRAFT BLOCK keys that are per-Run — the draft-space names for contract
#: §2's ``measurement.series[]``, ``measurement.qc``, ``assets[]`` and
#: ``descriptors.outputs[]``.
RUN_LEVEL_BLOCKS: tuple[str, ...] = ("series", "qc", "assets", "descriptors_outputs")

#: The three values a level classification can take.
LEVEL_EXPERIMENT = "experiment"
LEVEL_RUN = "run"
LEVEL_UNCLASSIFIED = "unclassified"

#: The two values a resolution's ``provenance`` can take.
PROVENANCE_INHERITED = "inherited"
PROVENANCE_OVERRIDDEN = "overridden"

#: The two namespaces an :func:`address` can point into.
ADDRESS_FIELD = "field"
ADDRESS_BLOCK = "block"

_ADDRESS_SEP = ":"


def field_address(path: str) -> str:
    """The address of one key inside ``draft["fields"]`` (e.g. ``field:sample.sample_form``)."""
    return f"{ADDRESS_FIELD}{_ADDRESS_SEP}{path}"


def block_address(key: str) -> str:
    """The address of one top-level draft block (e.g. ``block:tags``)."""
    return f"{ADDRESS_BLOCK}{_ADDRESS_SEP}{key}"


def parse_address(address: str) -> tuple[str, str]:
    """``"field:sample.sample_form"`` -> ``("field", "sample.sample_form")``.

    Addresses are EXPLICITLY NAMESPACED rather than bare names, because the two
    namespaces are not disjoint in principle: ``tags`` is both a top-level draft
    block and a legal official schema path, so a bare ``"tags"`` would be ambiguous
    the moment anything put ``tags`` in the field map. The prefix also makes a
    persisted override document self-describing, which matters when runs move to
    their own table.

    Raises :class:`ValueError` on anything that is not a well-formed address.
    """
    kind, sep, name = address.partition(_ADDRESS_SEP)
    if not sep or kind not in (ADDRESS_FIELD, ADDRESS_BLOCK) or not name:
        raise ValueError(f"malformed draft address: {address!r}")
    return kind, name


def _path_matches(path: str, prefix: str) -> bool:
    """Whether a dotted draft-field path falls under ``prefix``.

    Segment-aware on purpose: ``sample`` matches ``sample.material.name`` but
    ``system.domain`` must NOT match a hypothetical ``system.domain_notes``. A bare
    ``str.startswith`` would match both.
    """
    return path == prefix or path.startswith(prefix + ".")


def field_level(path: str) -> str:
    """Classify one key of ``draft["fields"]``. FIELD-MAP SPACE ONLY.

    This function does NOT classify a top-level draft block — see :func:`block_level`
    — and calling it with one returns ``LEVEL_UNCLASSIFIED``, which is the honest
    answer for a field-map key that does not exist rather than a judgement about the
    block of that name. Use :func:`address_level` when the caller may hold either.

    ``LEVEL_UNCLASSIFIED`` IS A REAL ANSWER AND IS NOT AN OVERSIGHT. Two families of
    field-map key are in neither list, for two different reasons:

    * ``system.configuration.*`` — SIX fields, not the five this list used to name:
      ``detector_model``, ``monochromator_crystal``, ``spectrometer_geometry``,
      ``n_scans``, ``proposal_id``, ``session_id``. The behaviour was always correct
      (the prefix test covers the whole namespace); only this prose undercounted, and
      it was found by enumerating ``extract/structured.FIELD_MAP`` rather than reading
      it. They are emitted by the real extractor and the contract assigns them to
      neither level. Guessing would be the unevidenced inference ``CLAUDE.md`` §5
      forbids: whether two runs of one experiment may legitimately differ in detector
      model is a scientific question this repository has no answer to. The question is
      written out per field, with what each answer would unlock, in
      ``docs/run-scope-decision-packet.md``.
    * ``timestamps.created_utc`` is also unclassified, and it is the one member of this
      list that does NOT need a scientific answer — stated here because grouping it
      with the six made it look as though it did. The official schema REQUIRES it and
      gives it no description, ``export.py`` already defaults it to the export time via
      ``setdefault``, and an unclassified field is not inherited — so it is a
      record-creation stamp, not an inherited scientific value. The consequence, logged
      rather than fixed here: a creation time recorded in a source sheet is dropped on
      the fan-out path and replaced by the export time.
    * anything else a future extractor emits, which defaults to unclassified rather
      than to a level — fail-closed, so a new field is inherited by nobody until
      somebody decides.
    """
    for prefix in EXPERIMENT_LEVEL_FIELD_PATHS:
        if _path_matches(path, prefix):
            return LEVEL_EXPERIMENT
    for prefix in RUN_LEVEL_FIELD_PATHS:
        if _path_matches(path, prefix):
            return LEVEL_RUN
    return LEVEL_UNCLASSIFIED


def block_level(key: str) -> str:
    """Classify one TOP-LEVEL draft block key. BLOCK SPACE ONLY.

    Exact match, not a prefix test: block keys are single tokens, not paths.
    ``meta``, ``pending``, ``implicit``, ``links`` and ``block_evidence`` are
    deliberately unclassified — ``pending``/``implicit``/``block_evidence`` are
    draft-only bookkeeping that never becomes a record field, ``meta`` is the
    record-type stamp that is the same for every run by construction, and ``links``
    is how sibling runs are re-associated at export (contract §1), which is the
    fan-out slice's business and not an inherited value.

    UNCLASSIFIED HERE MEANS "NOT SUBJECT TO THE OVERRIDE MACHINERY", AND THAT IS A
    NARROWER STATEMENT THAN "NO RUN EVER SEES IT". The distinction was easy to miss
    and is spelled out because the fan-out slice had to decide it: an override is an
    audited displacement of an *inherited scientific value*, and none of these five
    is one. What each of them does at EXPORT is a separate question, answered by
    :meth:`Experiment.resolved_run_draft` and pinned by its own tests:

    * ``meta`` — CARRIED onto every run's export draft (the run's own wins if it has
      one). Not because it is inherited, but because the official schema *requires*
      ``record_type``/``record_domain``/``source_type`` and this docstring already
      states the stamp cannot legitimately vary between runs of one experiment.
    * ``block_evidence`` — MERGED, experiment entries first, run entries winning on a
      key collision. Its keys are namespaced per block (``attribution:…``,
      ``series:…``, ``qc:status``, ``links:…``), so a merge cannot conflate two
      blocks' provenance, and withholding it would strand the inherited
      ``attribution`` block with no evidence — which ``validate_draft`` refuses, so
      *every* fan-out export would fail. It is a requirement, not a preference.
    * ``implicit`` — MERGED by ``about``, run entries winning. Sidecar-only
      provenance that carries its own evidence; dropping it would silently discard
      recorded evidence, which is a different failure from refusing to invent one.
    * ``pending`` — NOT merged into the export draft (``validate_draft`` never reads
      it). It is aggregated separately by :meth:`Experiment.pending`, which is where
      a run's blockers have to be counted.
    * ``links`` — NOT inherited and NOT copied. The only links a run's export draft
      gains are the sibling relations derived in :func:`_apply_sibling_grouping`.
    """
    if key in EXPERIMENT_LEVEL_BLOCKS:
        return LEVEL_EXPERIMENT
    if key in RUN_LEVEL_BLOCKS:
        return LEVEL_RUN
    return LEVEL_UNCLASSIFIED


def address_level(address: str) -> str:
    """Classify a namespaced draft address. Raises ``ValueError`` on a malformed one."""
    kind, name = parse_address(address)
    return field_level(name) if kind == ADDRESS_FIELD else block_level(name)


class NotOverridable(ValueError):
    """An override was attempted at an address that is not experiment-level.

    Only an experiment-level address can be *overridden*, because only an
    experiment-level address is *inherited* in the first place. A run-level field or
    block is simply the run's own draft content — writing one is an ordinary edit,
    not an override, and routing it through the override map would create a second
    place the same value could live.
    """


@dataclass(frozen=True)
class Override:
    """One run's explicit override of one inherited experiment-level address.

    ``payload`` is whatever that address holds. For a ``field:`` address it is a
    draft field envelope (``{"value": ..., "status": ..., "evidence": [...]}``) —
    the same shape ``blank_draft()`` and the deterministic extractor produce, so an
    override carries its own evidence and is subject to the same no-guessing rules
    as any other field. For a ``block:`` address it is the block itself (a list for
    ``tags``, an object for ``attribution``).

    ``displaced`` is the experiment's payload AT THE MOMENT THE OVERRIDE WAS
    RECORDED, or ``None`` when the experiment carried nothing there. Contract §2 D2
    requires an override to record what it displaced; this is that record. It is a
    HISTORICAL fact and is never refreshed — it is a DEEP COPY taken at capture, so
    a later in-place edit of the experiment's own draft cannot rewrite history
    through a shared reference. Do not read it as "what the experiment says now":
    that is ``Resolution.inherited_payload``, and the two legitimately differ once
    the experiment value is edited afterwards. Making that difference visible is the
    point of inheritance by reference.
    """

    payload: object
    recorded_utc: str
    displaced: object | None = None

    def to_state(self) -> dict:
        state: dict = {"payload": self.payload, "recorded_utc": self.recorded_utc}
        # ABSENCE IS THE ENCODING: the key is omitted when there is nothing to record.
        #
        # THE COMMENT HERE USED TO CLAIM MORE THAN THE CODE DOES, and the claim was
        # false. It said this keeps "displaced no inherited value" and "displaced an
        # inherited null" DISTINGUISHABLE on disk. It does not, and cannot: the
        # condition is `is not None`, so an explicit displaced `None` omits the key
        # exactly as nothing-displaced does, and `from_state` reads `None` back for both.
        # MEASURED — with the record carrying `draft["tags"] = None`, an accepted
        # `block:tags` override serialises to `{'payload': [...], 'recorded_utc': ...}`
        # with `'displaced' in state` FALSE, byte-identical to the nothing-displaced
        # case. This encoding cannot represent an explicit displaced null.
        #
        # THE BEHAVIOUR IS DELIBERATELY LEFT ALONE. It is not reachable over HTTP today
        # (no operation can set a record-level value to `null`), the two cases mean the
        # same thing to every current reader — "there was nothing here to bring back" —
        # and changing an on-disk encoding is its own slice with its own compatibility
        # question for overrides already stored. What is fixed is the comment, so a
        # future slice does not build on a guarantee that was never here.
        if self.displaced is not None:
            state["displaced"] = self.displaced
        return state

    @classmethod
    def from_state(cls, state: dict) -> "Override":
        return cls(
            payload=state.get("payload"),
            recorded_utc=state.get("recorded_utc") or "",
            displaced=state.get("displaced"),
        )


@dataclass(frozen=True)
class Resolution:
    """The resolved view of ONE inherited experiment-level address for ONE run.

    Computed on read, never stored. ``payload`` is what this run actually has at the
    address; ``inherited_payload`` is what the experiment carried WHEN THIS WAS
    RESOLVED; ``displaced_payload`` is what the override displaced when it was
    recorded.

    EVERY PAYLOAD IS A DEEP COPY, so this is a snapshot and not a window. Mutating
    one cannot reach the experiment's draft or a stored :class:`Override` — it used
    to, and ``frozen=True`` did not prevent it, because freezing the dataclass only
    stops the ATTRIBUTES being rebound and says nothing about the mutable objects
    they point at. To see a later experiment-level edit, resolve again; that is the
    inheritance-by-reference of contract §2 D2 working, not a staleness bug.
    """

    address: str
    kind: str
    name: str
    provenance: str
    payload: object | None
    inherited_payload: object | None
    displaced_payload: object | None = None

    @property
    def value(self):
        """The resolved scientific value.

        A ``field:`` address unwraps the envelope's ``value``; a ``block:`` address
        IS its own value and is returned whole. ``None`` is genuinely ambiguous
        between "absent" and "an explicit null", so callers that care about the
        difference should test ``payload is None``.
        """
        if self.payload is None:
            return None
        if self.kind == ADDRESS_FIELD:
            return self.payload.get("value") if isinstance(self.payload, dict) else None
        return self.payload


def _experiment_payload_at(draft: dict | None, kind: str, name: str):
    """What the experiment's draft carries at one address, or ``None``."""
    draft = draft or {}
    if kind == ADDRESS_FIELD:
        return (draft.get("fields") or {}).get(name)
    return draft.get(name)


def resolve_inherited(experiment_draft: dict | None, run: "Run") -> dict[str, Resolution]:
    """Resolve every inherited experiment-level address for one run.

    PURE, AND ITS OUTPUT CANNOT MUTATE ANYTHING EITHER. The docstring used to say
    only "Pure; stores nothing", which was true of the FUNCTION and false of what it
    HANDED BACK: every payload was a live reference into ``experiment_draft`` (or
    into a stored :class:`Override`), so ``res.payload["value"] = ...`` rewrote the
    experiment's draft — measured — through a call that reads. :class:`Resolution`
    being a frozen dataclass made that worse rather than better: freezing the record
    while its payload stays a live mutable alias reads as a guarantee and is not one.
    Every payload is therefore DEEP-COPIED on the way out.

    That does not weaken contract §2 D2, and the distinction is worth stating exactly
    because it looks like a contradiction. D2 governs STORAGE: a run stores only the
    ABSENCE of an override, and nothing copies an experiment value down into a run.
    A Resolution is not storage — it is a read handout, computed and discarded — so
    it is a SNAPSHOT taken at call time. Editing an experiment-level field still
    flows through to every non-overriding run on the next resolve, with no fan-out
    write, no reconciliation pass and no window of disagreement. What the copy
    removes is only the ability to write through a read.

    THIS IS THE READ HALF OF CONTRACT §2 DECISION D2 — inheritance is BY REFERENCE,
    NEVER BY COPY. A run stores only the ABSENCE of an override; nothing here writes
    an experiment value into a run, and nothing anywhere else does either. The
    consequence that makes the decision worth its cost: editing an experiment-level
    field flows through to every non-overriding run immediately, with no fan-out
    write, no reconciliation pass, and no window in which some runs hold the old
    value.

    Takes the WHOLE experiment draft, not just ``draft["fields"]``, because
    experiment-level content lives in both namespaces — ``attribution`` and ``tags``
    are top-level blocks, and an earlier version of this function took only the field
    map and therefore inherited neither.

    The key set is the union of (a) every address in the experiment's own draft that
    classifies as experiment-level and (b) every address this run overrides — so an
    override of an address the experiment does not (yet) carry is still reported,
    with ``inherited_payload=None``.

    A STORED OVERRIDE IS REPORTED EVEN IF ITS ADDRESS NO LONGER CLASSIFIES AS
    EXPERIMENT-LEVEL, and that is deliberate. ``set_run_override`` refuses a
    non-experiment-level address at write time, so this can only arise if the lists
    above change under data that already exists. Silently dropping it would hide
    user-entered content with evidence attached; reporting it keeps it visible and
    deletable. A malformed address is skipped, because it cannot be classified at
    all.
    """
    draft = experiment_draft or {}
    addresses: set[str] = set()
    for path in (draft.get("fields") or {}):
        if field_level(path) == LEVEL_EXPERIMENT:
            addresses.add(field_address(path))
    for key in draft:
        if key != "fields" and block_level(key) == LEVEL_EXPERIMENT:
            addresses.add(block_address(key))
    addresses |= set(run.overrides)

    out: dict[str, Resolution] = {}
    for address in sorted(addresses):
        try:
            kind, name = parse_address(address)
        except ValueError:
            continue  # unclassifiable garbage in a persisted document
        inherited = copy.deepcopy(_experiment_payload_at(draft, kind, name))
        override = run.overrides.get(address)
        if override is None:
            # ``payload`` and ``inherited_payload`` are separate copies rather than
            # the same object twice: a caller mutating one must not appear to move
            # the other, which is the very confusion this copy exists to remove.
            out[address] = Resolution(
                address=address,
                kind=kind,
                name=name,
                provenance=PROVENANCE_INHERITED,
                payload=copy.deepcopy(inherited),
                inherited_payload=inherited,
            )
        else:
            out[address] = Resolution(
                address=address,
                kind=kind,
                name=name,
                provenance=PROVENANCE_OVERRIDDEN,
                payload=copy.deepcopy(override.payload),
                inherited_payload=inherited,
                displaced_payload=copy.deepcopy(override.displaced),
            )
    return out


def _as_int(raw: object) -> int:
    """``int(raw)`` or ``0``. Never raises — a persisted document is untrusted input.

    ``int(state.get("rev") or 0)`` still raises on ``"seven"`` or ``[]``, which on
    the read path is the same HTTP 500 the hard subscripts were.
    """
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _as_str(raw: object) -> str:
    """The value if it IS a string, else ``""``. Never raises, and never coerces.

    The companion to :func:`_as_int` for the string-typed keys, and the asymmetry
    between the two is deliberate rather than an oversight. ``_as_int`` coerces
    (``int("7") == 7``) because ``int()`` can fail and therefore only accepts what
    is genuinely integral. ``str()`` CANNOT fail — it is total — so a coercing
    ``_as_str`` would silently manufacture a value out of anything: ``5`` would
    become the run id ``"5"``, ``{"a": 1}`` would become the timestamp
    ``"{'a': 1}"``. That is guessing, and a wrong-typed key on disk is not evidence
    for any particular string. Falling back to ``""`` instead puts the entry in
    exactly the bucket a MISSING key was already in, where the existing policy
    applies unchanged — :func:`_hydrate_runs` drops an id-less run, and an empty
    ``created_utc``/``label`` is the same legacy default a pre-runs document gets.

    ``or ""`` is what this replaces, and it was not a type guard: it catches
    ``None`` but every wrong type here is TRUTHY. A ``{"id": 5}`` entry therefore
    survived hydration and raised ``TypeError`` in ``Run.__post_init__`` ->
    ``_legacy_generation`` (``"gen:" + rid``) — a measured HTTP 500 on BOTH
    ``GET /api/experiments/<id>`` and the whole-workspace ``GET /api/experiments``.

    ``isinstance(raw, str)`` is the right test and a truthiness or numeric one is
    not: ``True`` is an ``int`` in Python and would pass a numeric guard.
    """
    return raw if isinstance(raw, str) else ""


def _as_record_id(raw: object) -> str | None:
    """A persisted ``record_id`` if it really is one, else ``None`` (= not exported).

    The third guard in the :func:`_as_int` / :func:`_as_str` family, and the one that
    cannot use either of them: ``None`` here is a MEANING (this run has not been
    exported), so ``""`` is not an acceptable fallback and ``str()`` coercion would
    manufacture an id out of an integer. ``is_record_id`` is the same predicate
    ``export_draft`` applies before it will mint a record, so a value this rejects
    could not have produced an artifact in the first place.
    """
    return raw if isinstance(raw, str) and is_record_id(raw) else None


@dataclass
class Run:
    """One measurement condition of an experiment. Exports to exactly ONE record.

    A Run is a first-class domain object with its own draft, its own evidence and
    its own version — but it is NOT its own storage unit in this slice: runs are
    carried inside the experiment's state document (``Experiment.to_state``). That
    is a deliberate, temporary shape. Contract §8 DECISION D7 makes runs relational
    rows (``isaac_runs``) precisely because one jsonb document rewritten on every
    autosave keystroke, containing N runs, is the "single enormous object" the brief
    forbids. That change needs migration ``0002``, an approval packet and an
    explicit approval, none of which this slice has — so the model exists here
    first, and the storage moves later.

    No ``session_id``. The scope (normal vs. a worked-example session) is a property
    of WHERE the owning experiment's files live, and ``Experiment`` already carries
    it. A run of a worked-example session is unpersistable for exactly the reason
    its experiment is: ``PostgresOrdinaryStore.refuse_if_not_persistable`` refuses
    the experiment, and the experiment is what carries the runs.
    """

    id: str
    experiment_id: str
    label: str
    #: THE ORDER KEY, and it is explicit for a reason: the label must never
    #: determine order. ``"Run 10"`` sorts before ``"Run 2"`` lexically, and a
    #: scientist may rename a run to anything at all. ``ordinal`` is what
    #: :meth:`Experiment.sorted_runs` sorts on.
    ordinal: int
    created_utc: str
    #: The run's OWN draft, in the same shape ``blank_draft()`` produces. It carries
    #: the run-level content in BOTH draft namespaces: the run-level ``fields`` keys
    #: (``context.*``, ``timestamps.acquired_*``) and the run-level top-level blocks
    #: (``series``, ``qc``, ``assets``, ``descriptors_outputs``).
    draft: dict = field(default_factory=dict)
    #: Set when THIS RUN is exported. Per contract §1 D1 the record identity is
    #: per-Run, not per-Experiment. ``Experiment.record_id`` remains the field the
    #: current 1:1 export path writes and is untouched by this slice.
    record_id: str | None = None
    #: namespaced draft address (``field:sample.sample_form``, ``block:tags``) ->
    #: :class:`Override`. THE ABSENCE OF A KEY IS THE INHERITANCE. Nothing is copied
    #: down from the experiment; see :func:`resolve_inherited`.
    overrides: dict[str, Override] = field(default_factory=dict)
    #: Monotonic per-run version, bumped only by
    #: ``Experiment._bump_changed_runs`` when this run's authoritative signature
    #: actually changes. Never derived — it is stored.
    rev: int = 0
    updated_utc: str = ""
    #: Per-run opaque nonce, minted at genuine creation and preserved across saves,
    #: so a delete->recreate of the same run id is distinguishable even at rev 0.
    generation: str = ""

    def __post_init__(self) -> None:
        if not self.updated_utc:
            self.updated_utc = self.created_utc
        if not self.generation:
            self.generation = _legacy_generation(self.id)

    def version_token(self) -> str:
        """The run's opaque concurrency token: ``<generation>.<rev>``.

        Same shape as ``Experiment.version_token``. No route consumes it yet; it
        exists so a later per-run ``If-Match`` reuses the machinery in
        ``version_contract`` unchanged rather than inventing a second scheme.
        """
        return f"{self.generation}.{self.rev}"

    def to_state(self) -> dict:
        return {
            "id": self.id,
            "experiment_id": self.experiment_id,
            "label": self.label,
            "ordinal": self.ordinal,
            "created_utc": self.created_utc,
            "draft": self.draft,
            "record_id": self.record_id,
            "overrides": {p: o.to_state() for p, o in sorted(self.overrides.items())},
            "rev": self.rev,
            "updated_utc": self.updated_utc,
            "generation": self.generation,
        }

    @classmethod
    def from_state(cls, state: dict) -> "Run":
        """Rehydrate one run. NEVER RAISES on a malformed document.

        EVERY key is read with ``.get`` and a default, ``id`` and ``experiment_id``
        included. They used to be hard subscripts, and the asymmetry was a measured
        HTTP 500: ``Experiment.from_state`` hydrates runs in an unguarded
        comprehension and ``list_experiments`` catches only ``FileNotFoundError``, so
        ONE run entry missing ``id`` took out ``GET /api/experiments/<id>`` *and*
        ``GET /api/experiments`` for the entire workspace. Worse, this module's own
        fail-open handlers (``_persisted_sig_and_rev``, ``_persisted_run_state``)
        both catch ``KeyError`` — a tolerance that could never fire, because the read
        path raised first.

        Producing a run rather than raising is only half the fix; a run with no id is
        unaddressable and is dropped by :func:`_hydrate_runs`, which owns that policy
        so it lives in one place.

        EVERY KEY IS ALSO TYPE-GUARDED, and ``.get`` with a default was NOT enough —
        that is the second half of the same defect, measured after the first. ``or
        ""`` catches ``None`` and nothing else, and every wrong type is truthy, so a
        persisted ``{"id": 5}`` survived hydration and then raised ``TypeError`` in
        ``__post_init__`` -> ``_legacy_generation`` (``"gen:" + rid``): the SAME 500
        on the single record and the whole-workspace list that the hard subscripts
        caused, reached by a different route. ``{"created_utc": 5}`` was worse,
        because it did not fail on read at all — it returned 200 and then wedged the
        WRITE path, since ``sorted_runs`` orders on ``(ordinal, created_utc, id)``
        and is used by both ``to_state`` and ``_authoritative_signature``. Once two
        runs' ordinals tie (which every pre-``ordinal`` document does, all defaulting
        to ``0``) the mixed types are compared and every subsequent save raises,
        leaving the experiment permanently unsavable with no in-product repair path.

        So the string keys go through :func:`_as_str` exactly as the integer keys go
        through :func:`_as_int`. ``ordinal``/``rev`` were guarded from the start and
        their string-typed neighbours were not; that asymmetry is what this closes,
        rather than closing only the two keys that were observed to break.

        ``draft`` and ``overrides`` keep their own guards (``or {}`` / ``isinstance``).

        ``record_id`` USED TO BE PASSED THROUGH UNGUARDED, declared as a known gap
        owed to "the export fan-out slice that starts writing it". This is that
        slice, so the debt is paid here. ``_as_str`` was the wrong instrument and
        still is — ``None`` is a MEANINGFUL value (not-yet-exported), not a fallback,
        and coercing garbage to ``""`` would erase the distinction. The guard is
        :func:`isaac_records.ids.is_record_id` instead: anything that is not a valid
        record id becomes ``None``, i.e. NOT EXPORTED, which is both fail-closed and
        true — a malformed id names no artifact this application ever wrote. The
        reason it now matters is concrete: :func:`_run_artifact_presence` and the
        export route build ``<records_dir>/<record_id>.json`` from this value, so an
        unguarded ``"../../etc/x"`` would be a path built from a persisted document.

        ONE CONSEQUENCE, DISCLOSED RATHER THAN HIDDEN. Coercing a garbage
        ``record_id`` to ``None`` changes that run's authoritative signature on read,
        so the next save of an experiment holding such a document bumps its ``rev``.
        That can only happen to a document that was already malformed, and the
        alternative — keeping the garbage so the signature is stable — keeps a path
        component this module refuses to trust.
        """
        raw_overrides = state.get("overrides")
        # ``or {}`` is not a type guard: a persisted ``"overrides": "nope"`` is
        # truthy and reached ``.items()``. Found by this module's own
        # never-raises-on-garbage test, which is the same defect class as the hard
        # subscripts above.
        overrides = raw_overrides if isinstance(raw_overrides, dict) else {}
        return cls(
            id=_as_str(state.get("id")),
            experiment_id=_as_str(state.get("experiment_id")),
            label=_as_str(state.get("label")),
            ordinal=_as_int(state.get("ordinal")),
            created_utc=_as_str(state.get("created_utc")),
            draft=state.get("draft") or {},
            record_id=_as_record_id(state.get("record_id")),
            overrides={
                addr: Override.from_state(o)
                for addr, o in overrides.items()
                if isinstance(addr, str) and isinstance(o, dict)
            },
            rev=_as_int(state.get("rev")),
            updated_utc=_as_str(state.get("updated_utc")),
            generation=_as_str(state.get("generation")),
        )


def _hydrate_runs(raw: object) -> list[Run]:
    """Hydrate a persisted ``runs`` array, skipping what cannot be a run. Never raises.

    THE ONE PLACE THAT DECIDES WHAT A MALFORMED RUN ENTRY IS, so hydration and
    ``_persisted_run_state`` cannot disagree about which runs a document contains.
    Two things are skipped, both fail-closed-on-read-garbage in the same style as
    ``_experiment_dirs`` and ``_persisted_sig_and_rev``:

    * an entry that is not an object, or that carries no ``id``. A run with no id is
      unaddressable — nothing can render, version, override or export it — so there
      is no meaningful way to keep it. Dropping one entry is a real loss and is the
      lesser of two: the alternative, measured, was a 500 on ``GET /api/experiments``
      that hid EVERY experiment in the workspace behind one bad entry.
    * a DUPLICATE id, first occurrence wins. Duplicate ids would break the total
      order :meth:`Experiment.sorted_runs` promises and would let
      ``_persisted_run_state`` silently lose one run's on-disk ``rev``.

    ``experiment_id`` is deliberately NOT repaired from the owning experiment even
    though it could be. Backfilling it would change the run's authoritative
    signature on read, so merely LISTING a workspace would mark records as changed
    and bump their ``rev`` at the next save.
    """
    if not isinstance(raw, list):
        return []
    out: list[Run] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        run = Run.from_state(entry)
        if not run.id or run.id in seen:
            continue
        seen.add(run.id)
        out.append(run)
    return out


def _run_signature_payload(run: Run) -> dict:
    """A run's AUTHORITATIVE content, for hashing. Version metadata is excluded.

    Covers ``{id, experiment_id, label, ordinal, draft, record_id, overrides}``.
    EXCLUDES ``rev`` / ``updated_utc`` / ``generation`` (version metadata, exactly as
    ``Experiment`` excludes its own) and ``created_utc`` (immutable identity).

    Excluding ``rev`` is only safe because of an invariant that must not be broken:
    ``Experiment._bump_changed_runs`` is the ONLY thing that moves a run's ``rev``,
    it runs solely on the write path, and it moves ``rev`` only when THIS payload
    changed. So a run's ``rev`` can never move without the experiment's signature
    moving too, and therefore can never be silently dropped by the byte-stable
    no-op in ``save_versioned``. If a second writer of ``run.rev`` is ever added,
    this exclusion becomes unsound.

    ``overrides`` is included WHOLE, ``recorded_utc`` and ``displaced`` included:
    recording an override is an audited act and its record is authoritative state.
    That is safe from churn because :meth:`Experiment.set_run_override` is
    idempotent — re-applying an equal envelope does not restamp ``recorded_utc``.
    """
    return {
        "id": run.id,
        "experiment_id": run.experiment_id,
        "label": run.label,
        "ordinal": run.ordinal,
        "draft": run.draft,
        "record_id": run.record_id,
        "overrides": {p: o.to_state() for p, o in sorted(run.overrides.items())},
    }


def _run_signature(run: Run) -> str:
    blob = json.dumps(_run_signature_payload(run), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def new_run(
    experiment_id: str,
    *,
    ordinal: int,
    label: str | None = None,
    draft: dict | None = None,
    created_utc: str | None = None,
    id: str | None = None,
) -> Run:
    """Mint a Run. The id is a fresh ULID, minted by the same function record ids use.

    Same alphabet and shape as a record id — but a RUN ID IS NOT A RECORD ID. The
    record identity lives in ``Run.record_id`` and is set only when this run is
    exported. Reusing ``new_record_id()`` avoids a second id scheme; it asserts
    nothing about the run having been exported.

    ``draft`` defaults to an empty dict rather than to ``blank_draft()``: that
    builder lives in ``experiment_repository`` (which imports this module), and the
    caller that creates a run is the one that knows whether the blank-draft pending
    blockers apply. Nothing scientific is invented here.

    ``draft`` IS DEEP-COPIED, so the run owns its draft outright. The previous
    ``draft if draft is not None else {}`` stored the caller's dict itself, which
    made ``run.draft is exp.draft`` true when a run was seeded from its experiment
    and ``a.draft is b.draft`` true for two runs seeded from one template — a run
    silently tracking another object is the same defect as an override doing it
    (:meth:`Experiment.set_run_override`), and it contradicts the whole reason a Run
    has its OWN draft: contract §1 D1 makes each run a separate ISAAC record.

    It is deliberately fixed NOW even though NO caller passes ``draft`` today. That
    is what makes it worth doing rather than what makes it safe to defer: the next
    slice is the one that seeds runs from a template or from the experiment, and the
    sharing would not announce itself when it arrived. ``_run_signature`` covers
    ``draft``, so two aliased runs move their ``rev`` in lockstep — the versioning
    machinery would report the shared state as though both runs had genuinely been
    edited, MASKING the aliasing instead of exposing it.

    A shallow ``dict(draft)`` would not be enough: a draft's ``fields`` is a map of
    envelope dicts, so the envelopes — the things carrying evidence — would stay
    shared one level down.
    """
    return Run(
        id=id or new_record_id(),
        experiment_id=experiment_id,
        label=label if label is not None else f"Run {ordinal}",
        ordinal=ordinal,
        created_utc=created_utc or _now_iso(),
        draft=copy.deepcopy(draft) if draft is not None else {},
        generation=_new_generation(),
    )


def _authoritative_signature(exp: "Experiment") -> str:
    """Deterministic hash of the AUTHORITATIVE scientific state of an experiment.

    Covers exactly ``{title, source, draft, record_id, runs}`` — the fields that
    define the record's scientific content. It EXCLUDES ``answer_log`` (an audit
    trail, not scientific state), ``generation``/``rev``/``updated_utc`` (version
    metadata, not scientific content — excluding ``generation`` keeps a byte-stable
    no-op from churning the token), and ``created_utc`` (immutable identity). Two
    experiments with an identical scientific state therefore hash identically, so a
    no-op re-entry is detectable and never bumps ``rev``.

    ``runs`` WAS ADDED, and the decision is argued rather than assumed. Runs are
    authoritative scientific state: per contract §1 D1 each one exports to its own
    ISAAC record, so a run edit changes what this experiment will produce. Leaving
    runs out would mean adding, editing or deleting a run left ``version_token()``
    unmoved — and the whole ``If-Match`` contract (428/412 at ``routes.py:507-539``)
    is built on that token. A second client holding the pre-edit ETag would pass its
    precondition and silently overwrite the run edit, which is the exact class of
    loss the precondition exists to prevent. So a run edit DOES bump the
    experiment's ``rev``.

    Byte-stable no-op still holds, in both directions:

    * runs are hashed through :func:`_run_signature_payload`, which excludes each
      run's ``rev``/``updated_utc``/``generation``/``created_utc`` — so the version
      metadata this save is about to write cannot feed back into the signature that
      decides whether to write;
    * the list is taken in :meth:`Experiment.sorted_runs` order, so a re-ordering of
      the in-memory list that does not change any ``ordinal`` is correctly not an
      authoritative change;
    * ``answer_log``-style non-authoritative data stays out — a run has no
      ``answer_log``, and if one is added later it belongs outside this payload for
      the same reason the experiment's is.

    An experiment written before runs existed hashes with ``"runs": []``, and so
    does the same experiment re-read from disk (``from_state`` yields zero runs), so
    the added key does NOT cause a spurious rev bump on legacy state. That is pinned
    by ``test_run_domain_model.py``.
    """
    payload = {
        "title": exp.title,
        "source": exp.source,
        "draft": exp.draft,
        "record_id": exp.record_id,
        "runs": [_run_signature_payload(r) for r in exp.sorted_runs()],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --- export fan-out (contract §1 DECISION D1) ---------------------------------
#
# ONE RUN PRODUCES EXACTLY ONE ISAAC RECORD. An ``Experiment`` with runs exports to
# N records; an ``Experiment`` with NO runs exports exactly as it always did — one
# record, ``record_id == exp.id``, byte-identical draft, same artifacts. That is not
# a transitional courtesy: it is the shape of every experiment this application has
# ever stored, so the zero-run path is the common case and is preserved by
# CONSTRUCTION rather than by a compatibility branch bolted on afterwards — the
# zero-run unit is handed ``self.draft`` ITSELF, not a composed copy, so there is no
# composition rule that can drift away from today's behaviour.
#
# NOTHING IN ``src/isaac_records/`` OR ``schema/`` CHANGES. ``export_draft``,
# ``transform`` and ``build_sidecar`` are already per-record — one draft in, one
# record out — which is the correct granularity for ONE run. The 1:1 assumption
# lived entirely in the caller, and it is the caller that is fixed.
#
# --- A KNOWN COST, RECORDED RATHER THAN FIXED (review item C9) ----------------
#
# The run-blind derivations were fixed by making ``status``/``draft_ok``/
# ``export_ready`` aggregate over ``export_units()``, and each of those composes N
# drafts and dry-runs ``export_draft`` over them. Nothing gates on the cost, and no
# route can create a Run yet, so this is deliberately NOT optimised in this slice —
# but it is measured, so the Run-workspace slice inherits a number rather than a
# suspicion. MEASURED on this commit by counting calls through
# ``isaac_api.workspace.export_draft`` and ``dependencies.transform`` over the real
# HTTP surface, on one 5-run experiment alongside the five canonical zero-run seeds:
#
#                                     export_draft   transform
#     GET /api/experiments/<id>   before export   10           0
#                                 fully exported   5           5
#     GET /api/experiments        before export    7           0
#                                 fully exported   2           0
#
# The 10 is two dry runs per run: ``status()`` and ``export_ready()`` each call
# ``_all_units_pass_dry_run`` independently. It falls to 5 once every unit is
# exported, because ``status()`` short-circuits to DONE — so the cost is highest on
# exactly the experiments a user is still working on. The 5 transforms are
# ``artifact_state`` comparing each written record with what exporting it now would
# produce. The 7 on the listing is 5 (this experiment) + 2 (the seeds that reach
# their dry-run branch).
#
# Two amplifiers a future slice should address together rather than separately:
# ``status()`` and ``export_ready()`` each dry-run every unit independently, and
# ``export_units()`` itself now reads one JSON file per MATERIALISED unit (the C1
# sibling-link fix). A per-request memoisation of ``export_units()`` would remove
# most of both; it is not added here because it introduces a cache into a module
# whose correctness argument is "recomputed on every read, never stored".
#
# --- WHAT EVERY OTHER SURFACE DOES FOR A FAN-OUT ------------------------------
#
# HOW THIS LIST WAS BUILT, because that is the part that keeps failing. Two earlier
# revisions of this block were wrong in the same way, and neither was wrong about a
# fact — both were wrong about a COUNT. The first said the remaining read-only routes
# "surface no artifacts", which was too kind: some of them ASSERTED, and falsely. The
# second corrected that, enumerated FOUR routes, and claimed *"each is now either
# fixed or stated"* — a completeness claim over an enumeration that was missing six
# surfaces, including two that were still asserting falsehoods. A disclosure that
# claims completeness it does not have is worse than one that says "at least these",
# because it stops the next reader looking.
#
# So the enumeration below is established BY SEARCH over the API package —
# every function that calls ``exported()``, ``record_path()``, ``sidecar_path()``,
# ``all_units_exported()`` or ``any_unit_exported()`` on anything that is not a
# PROVABLE ``ExportUnit`` (which is fan-out-native by construction), plus every
# ``derive_workflow`` call site — and the search is RE-RUN AT TEST TIME by
# ``test_export_fan_out.test_the_fan_out_disclosure_names_every_surface_that_reads_the_singular_pair``,
# which fails until any new such caller is named here.
#
# THAT SENTENCE WAS FALSE WHEN IT WAS FIRST WRITTEN, AND THE CORRECTION IS THE
# THIRD TIME THIS BLOCK HAS BEEN WRONG ABOUT ITS OWN COVERAGE — the first two were
# wrong about a COUNT, this one was wrong about a MECHANISM, which is worse: it
# named the property a reader could rely on and enforced something much narrower.
# Four separate one-line additions each left the whole suite GREEN. A caller whose
# parameter was named ``experiment`` rather than ``exp`` (and ``experiment`` is
# already the parameter name at ``_apply_sibling_grouping`` and
# ``_run_artifact_presence``, both in this file); a chained receiver
# (``ws.load_experiment(id).exported()``); the same body placed in
# ``assistant_query.py``, outside a hard-coded four-module allowlist; and a new
# ``derive_workflow`` call site, which the searched attribute set did not contain at
# all — while this very sentence promised *"plus every ``derive_workflow`` call
# site"*. The search now globs every module in the package, proves ``ExportUnit``
# receivers from annotations and bindings instead of from two literal variable
# names, resolves chained receivers by callee name, and includes
# ``derive_workflow``. Its REACH is measured, not described:
# ``test_a_new_caller_cannot_slip_past_the_disclosure_guard`` re-runs all four
# bypasses against it, plus the positive control and four ``ExportUnit`` shapes that
# must still be excluded.
#
# AND IT WAS WRONG A FOURTH TIME, in the two ways a name-based test is always wrong.
# Both were measured on ``0337d19``:
#
#   * B1 — the verdict keyed on the FUNCTION NAME, not on ``module::name``. The
#     module appeared only in the failure message. This package has 19 duplicated
#     function names across modules; ``def _summary(exp): return exp.exported()``
#     added to ``assistant_query.py`` left the suite GREEN, because ``routes._summary``
#     is already disclosed. That is this branch's own defect class, not a
#     hypothetical: ``_assistant_validate_dryrun`` was a sibling copy of
#     ``post_validate``, in another module, asserting a falsehood. Worse still,
#     ``status`` is BOTH a disclosed caller here (``Experiment.status``) and an
#     existing function in ``memory.py``.
#   * B2 — membership was ``name not in block``: a substring test against this
#     English. A new caller named ``state``, ``status``, ``reason``, ``audit`` or
#     ``_detail`` was authorised by a SENTENCE. All five measured GREEN.
#
# Both are closed by the enumeration below, which is a parsed list of qualified
# ``module.py::function`` tokens. Prose can no longer authorise a function, and a
# sibling copy in another module is a different token. The test also fails on a
# STALE entry — a name the list authorises that no function answers to — because a
# pre-authorised name is the one way a structured list can re-open the hole.
#
# THE ENUMERATION. Every line below is machine-read by the guard test; the
# discussion that follows is for humans and authorises nothing.
#
#   [caller] corpus_mutation.py::_workflow_consistent
#   [caller] dependencies.py::_post_workflow
#   [caller] dependencies.py::artifact_state
#   [caller] routes.py::_assistant_validate_dryrun
#   [caller] routes.py::_detail
#   [caller] routes.py::_summary
#   [caller] routes.py::_warnings_payload
#   [caller] routes.py::_workflow_for
#   [caller] routes.py::get_artifacts
#   [caller] routes.py::get_evidence
#   [caller] routes.py::post_audit
#   [caller] routes.py::post_export
#   [caller] routes.py::post_validate
#   [caller] runtime_records.py::_project_one
#   [caller] workspace.py::_plan_digest_row
#   [caller] workspace.py::status
#
# WHAT REMAINS OUTSIDE THE GUARD — AT LEAST THESE. The qualifier is deliberate and
# is the correction this paragraph most needed: this is the FOURTH consecutive
# revision of this block whose self-description outran its reach, and each of the
# first three read as exhaustive. It is not claimed to be exhaustive. It is claimed
# to name every limit known on 2026-08-09, and each of the eight below was
# demonstrated, not imagined.
#
#   1. ``self`` inside ``ExportUnit`` is excluded — it IS a unit. Deliberate.
#   2. An unannotated parameter that really does hold a unit is REPORTED, and must
#      be annotated or named. Deliberate: an unproved receiver costs a sentence,
#      the opposite default costs a silent hole.
#   3. NO frontend consumer is scanned at all. The guard cannot cross the language
#      boundary, and the ``exported: true`` / ``record_id: null`` pair reached two
#      React screens that rendered the literal string ``null``, and two more that
#      called an exported record a Draft, before anyone looked.
#   4. B3 — ``package.glob("*.py")`` is NOT recursive. A caller in a subpackage is
#      invisible. Latent today: the only subdirectories are ``data/`` and
#      ``migrations/``, and ``migrations/`` holds ``.sql`` files only.
#   5. B4 — only calls lexically inside a ``def`` are considered. A call at module
#      level, or in a class body, is not walked.
#   6. B5 — ``getattr(exp, "exported")()`` is a string, not an ``ast.Attribute``,
#      and is not matched. Nor is any other dynamic dispatch.
#   7. B6/B7 — the ``ExportUnit`` proof is SYNTACTIC. A parameter falsely annotated
#      ``: ws.ExportUnit``, or a decoy class named ``ExportUnit`` in any module,
#      excludes a receiver that is not a unit. The guard trusts the annotation.
#   8. B8 — the key is ``module.py::function``, so two functions of the same name in
#      ONE module collapse to a single entry: a method ``Foo.status`` and a
#      module-level ``status`` in the same file are one token. Qualifying by class
#      as well would close it; it is not closed today.
#
# B3–B8 are RECORDED AND NOT FIXED, by decision. None is reachable by code in this
# package today, and each would widen the guard's own surface — which is itself a
# thing that can be wrong.
#
# There are FOUR ``derive_workflow`` CALL SITES, plus the definition — not "five
# call sites", which is what this block said after correcting the C5 fix's "three",
# and which counted the definition as a call. The four are
# ``routes._workflow_for``, ``dependencies._post_workflow``,
# ``runtime_records._project_one`` and ``corpus_mutation._workflow_consistent``
# (which takes no experiment at all — it calls the pure function with literal
# arguments as a regression check, and is correct as written). The count is
# established by the guard, not by this sentence.
#
# FIXED — these asserted something false about a fan-out and no longer do:
#
#   * ``routes.post_validate`` returned ``{"ok": false, "errors": [{"path": "$",
#     "message": "'descriptors' is a required property"}], "dry_run": true}`` about a
#     fan-out whose N records had all just passed official validation, because
#     ``exp.exported()`` is False for a fan-out and it therefore validated
#     ``exp.draft`` — the experiment-level half, which is never exported and is not a
#     record. FIXED (C6): checked per run, ``runs[]`` carries each verdict.
#   * ``routes._assistant_validate_dryrun`` — the Assistant Q&A route's validation
#     thunk — was a SECOND COPY of that same defect and the C6 fix did not touch it.
#     Measured on ``c467dc7`` in one process: the endpoint answered ``ok: true`` while
#     the thunk answered ``ok: false`` with the identical ``'descriptors' is a
#     required property``. FIXED (F1), and fixed ONCE: both now call
#     ``routes._fan_out_official_verdict``.
#   * ``routes._summary`` (``exported``) and ``routes._detail`` reported ``exported:
#     false`` and ``workflow.export: 'current'`` for a fully-exported fan-out,
#     disagreeing with the export response's own ``completed`` — and any later
#     mutation then reported ``reopened_steps: ['export']``. FIXED (C5).
#   * ``routes._workflow_for`` and ``dependencies._post_workflow`` are the other two
#     halves of that same disagreement. FIXED (C5).
#   * ``runtime_records._project_one`` — served by ``GET /api/runtime/records`` — was
#     the FIFTH site the C5 fix's "all three" did not count. Measured on ``c467dc7``:
#     ``_project_one(exp)["exported"] -> False`` beside ``GET /api/experiments/{id}
#     ["exported"] -> True``, same experiment, same process. FIXED (F2).
#   * ``dependencies.artifact_state`` reported ``none`` — "nothing was exported" — for
#     an experiment whose N records were all on disk and current. FIXED (C5), and
#     corrected again in ``_fan_out_artifact_state`` (F4), which used to report a
#     PERMANENT ``stale`` that nothing could repair: it compared each materialised
#     record against a draft carrying the reverse sibling link that record will
#     deliberately never gain.
#   * ``routes.post_audit`` answered ``{"records": [], "text": "No records found.",
#     "message": "Nothing exported yet — export this experiment before auditing."}``
#     about a fully-exported fan-out. The audit itself was never fan-out-blind —
#     ``audit_records`` globs this experiment's own records dir — only the
#     ``exported()`` gate in front of it was. FIXED (F5), gated on
#     ``any_unit_exported()`` so a PARTIAL fan-out is audited too.
#   * ``routes._warnings_payload`` (both the GET and the POST warnings operations)
#     dry-ran ``exp.draft`` and advised ``NO_LINKS`` / ``NO_MEASUREMENT_SERIES`` about
#     a fan-out whose every record on disk carries a ``measurement`` block. FIXED
#     (F5): per run, with ``runs[]`` and a deduplicated union at the top level.
#   * ``routes.post_export`` itself: the 409 named one arbitrary run's record as
#     though it were THE record (FIXED, C10), the prune could delete a record a
#     surviving run or a surviving link still named (FIXED, C3/C4/C7), and it could
#     rewrite a record in a way that falsified a surviving sibling's link (FIXED, F7 —
#     the export is refused with ``sibling_link_conflict``).
#   * ``workspace._plan_digest_row`` stats the SINGULAR pair, which is permanently
#     absent for a fan-out, so an acknowledged run export could be destroyed by a
#     reset in silence. FIXED by the per-run ``[run_id, record_present,
#     sidecar_present]`` element; the singular stats are retained for the legacy pair.
#
# STATED, NOT FIXED — these do not assert anything false, and each is incomplete for
# a reason that is a product decision rather than a bug:
#
#   * ``routes.get_artifacts`` serves the experiment's OWN pair, so a fan-out gets
#     four nulls — beside an ``artifact.state`` that can now read ``current``, which
#     together said "current, but there is nothing". The nulls are correct; what was
#     missing was the reason, and it is now served (``FAN_OUT_ARTIFACT_REASON``).
#     LISTING the per-run pairs is left to the Run-workspace slice, which is the slice
#     with a UI for them.
#   * ``routes.get_evidence`` reads the experiment's own sidecar+record pair, which a
#     fan-out does not have, so it degrades to the EXPERIMENT-LEVEL draft trail. That
#     trail is this record's own evidence and nothing is fabricated, but it omits
#     every run-level field.
#
#     THE REASON THIS BLOCK USED TO GIVE WAS BORROWED, AND IT DID NOT FIT. It said
#     merging N sidecars "would have to answer 'whose evidence is this' for a field N
#     runs each resolve, and that is the same product question
#     ``evidenced_field_count`` raises below." It is NOT the same question, and this
#     slice had already answered the version that applies here — twice.
#     ``_validate_unit`` and ``_unit_warnings_entry`` both key per-unit output by
#     ``run_id``/``run_label``/``record_id`` in a ``runs[]`` array, which is exactly
#     "whose is this", and neither had to merge anything to do it. An evidence
#     response could carry the same shape. What ``evidenced_field_count`` and
#     ``get_evidence_classification`` raise is a DENOMINATOR question — one number,
#     or one histogram, over N records, where any aggregate is a choice — and that
#     genuinely has no default. ``get_evidence`` mostly does not have it.
#
#     So the honest status is: DEFERRED FOR COST, not blocked on a product question.
#     It needs a ``runs[]`` array, N sidecar reads, and a frontend that can display
#     more than one trail — ``api.ts::getEvidence`` discards every key except
#     ``evidence`` today — and that frontend is the Run-workspace slice. It is listed
#     here rather than fixed because widening the wire shape with no consumer would
#     be shipping a contract nobody reads; it is not listed because we do not know
#     what it should say.
#   * ``routes.get_evidence_classification`` classifies ``exp.draft`` alone, so its
#     five-class histogram counts the experiment-level fields only. Same question,
#     same answer: it is a display axis, not a verdict, and nothing gates on it.
#   * ``evidenced_field_count`` is 14 for a fan-out where the byte-equivalent zero-run
#     experiment reports 26, because it reads ``exp.draft`` alone. See the comment at
#     its call site in ``routes._summary`` for why the honest options are "disclose"
#     or "redefine", and why redefining is a product decision rather than a bug fix.
#
# CORRECT AS WRITTEN — reached by the same search, named here because the search
# names it and an unexplained entry is how a reader learns to skim this list:
#
#   * ``Experiment.status`` calls ``self.all_units_exported()``, the fan-out-aware
#     aggregate, and its own docstring argues why the aggregate is ALL rather than
#     ANY. It is in this enumeration because it reads the exported state at all, not
#     because it reads it wrongly.

#: The ONE ``rel``/``basis`` pair this module will assert between sibling run
#: records, and the field whose equality justifies it.
#:
#: The schema's own words are the justification, not a scientific judgement of ours
#: (``schema/isaac_record_v1.json``, ``sample.sample_id``): *"Two records share a
#: sample_id if and only if they measured the same physical object — this is the
#: basis that gives same_sample_as links their meaning."* So when two runs resolve
#: to the SAME ``sample.sample_id``, ``same_sample_as`` / ``same_sample_id`` is a
#: restatement of stored equality under a definition the schema supplies. No other
#: relation is emitted, and the omissions are deliberate — see
#: :func:`_apply_sibling_grouping`.
SIBLING_REL = "same_sample_as"
SIBLING_BASIS = "same_sample_id"
SAMPLE_ID_PATH = "sample.sample_id"

#: Prefix of the grouping tag every fan-out record carries. ``tags`` is the schema's
#: designated grouping mechanism — *"how a user groups an arbitrary SET of records
#: at any granularity (campaign, material system, study)"* — and a tag is a label,
#: not a scientific claim, so emitting one asserts nothing about the science. Its
#: value encodes a stored identifier and nothing else.
GROUP_TAG_PREFIX = "experiment:"


def _group_tag(experiment_id: str) -> str | None:
    """The grouping tag for one experiment, or ``None`` if it would be invalid.

    Fail-closed against the schema's own constraints on a tag (``minLength: 1``,
    ``maxLength: 64``, ``pattern: ^\\S(.*\\S)?$``) rather than trusting that an
    experiment id is always a 26-character ULID — ``create_experiment`` accepts an
    explicit id and the fixtures use readable ones. A tag that could not validate is
    not emitted at all, because an export that fails schema validation on a label we
    added would be this slice breaking records it was asked to relate.

    The whitespace test is deliberately stricter than the pattern (which permits
    interior spaces): any whitespace at all disqualifies, which is a superset of what
    the pattern refuses and needs no reasoning about which regex dialect is in play.
    """
    tag = f"{GROUP_TAG_PREFIX}{experiment_id}"
    if not 1 <= len(tag) <= 64:
        return None
    if any(ch.isspace() for ch in tag):
        return None
    return tag


def _exported_field_value(draft: dict, path: str):
    """The value a draft field will actually carry INTO the record, or ``None``.

    Deliberately the same rule ``export.transform`` applies (skip ``status ==
    "missing"``, skip a null value) rather than a second reading of the envelope. It
    has to be: a sibling link is only honest if the two records really do carry the
    same ``sample_id``, and "the draft holds one" and "the record will hold one" are
    different statements whenever the envelope is a missing/null placeholder.
    """
    env = (draft.get("fields") or {}).get(path)
    if not isinstance(env, dict):
        return None
    if env.get("status") == "missing" or env.get("value") is None:
        return None
    return env.get("value")


def _merge_implicit(
    experiment_draft: dict, run_draft: dict, *, inherit: bool = True
) -> list | None:
    """The run's ``implicit`` entries, plus the experiment's ONLY when ``inherit``.

    ``implicit`` never becomes a record field — it is sidecar-only provenance — but
    each entry is a DERIVATION, and a derivation is only true relative to the values
    it was derived from. That distinction is the whole of this function.

    **``inherit=True`` — a run that holds the experiment's values.** It genuinely
    holds them at every experiment-level address, so the experiment's derivations are
    true of it, and withholding them would silently delete recorded evidence from the
    exported sidecar. Carrying them is correct.

    **THAT TEST IS ABOUT THE ENVELOPE, NOT ABOUT WHETHER AN OVERRIDE WAS RECORDED
    (review item F8, headline corrected by F-D).** The caller used to pass
    ``inherit=not run.overrides``, so an override that re-recorded the experiment's
    own envelope — a no-op — stripped every inherited entry. Measured. That was
    consistent with the rule as it was written down and inconsistent with the argument
    written immediately below it, which reasons entirely from DIVERGENCE (*"That
    argument was wrong the moment a run diverged"*). A no-op override has not
    diverged; the run holds what the experiment holds, which is the very premise the
    paragraph above rests on, so dropping the entries deleted real evidence for no
    reason.

    **THE HEADLINE USED TO SAY "ABOUT VALUES", AND THE CODE HAS NEVER COMPARED
    VALUES.** :func:`_diverges_from_experiment` compares ``Resolution.payload``
    against ``Resolution.inherited_payload`` — the whole ENVELOPE, evidence, status
    and confirmation included. :attr:`Resolution.value` exists for exactly the
    comparison the old headline described and this does not call it. The F8 test
    could not tell the two apart, because it re-records a byte-identical envelope.
    Measured where they differ: a run that records the SAME value with a re-stamped
    ``user_confirmation`` is treated as divergent and loses every inherited
    ``implicit`` entry.

    That is kept, and it is the fail-closed side rather than an accident of
    implementation. An ``implicit`` entry is a derivation over the experiment's
    recorded state, and the envelope IS that state: a run that re-records the value
    under its own confirmation is asserting it on its own authority, and the
    experiment's derivations were not evidenced against that. Widening to
    value-equality would carry the experiment's provenance onto a value the run has
    re-sourced, which is the direction ``CLAIMS`` discipline does not allow us to
    guess in. An override at an address the experiment does not carry counts as
    divergence for the same reason — there is nothing to agree with.

    What this costs is real and is stated rather than implied: a run whose only change
    is metadata loses inherited provenance it would have been entitled to under a
    value comparison. Changing that is a product decision about what an override
    MEANS, not a bug fix, and it would need its own test for every ``implicit`` entry
    it starts preserving.

    **``inherit=False`` — a run that diverges at ANY address.** An earlier revision
    carried the entries unconditionally, arguing that "merging asserts nothing that
    was not already asserted and evidenced on the experiment". That argument was
    wrong the moment a run diverged, and the review measured it: a run overriding
    ``sample.material.formula`` to ``FeO2`` exported a record whose sidecar carried
    ``implicit:absorbing_element = "Cu"`` with the rule *"absorbing element = sole
    non-oxygen element in sample.material.formula (CuO2 -> Cu)"*. Applying that rule
    to this record's own value yields ``Fe``. The entry was evidenced RELATIVE TO THE
    EXPERIMENT'S value; against the run's it is false.

    **Why ALL the experiment's entries are dropped when it does, and not just the
    dependent ones.**
    An ``implicit`` entry carries no machine-readable link to the field it derives
    from — only prose in ``rule``. Keeping the entries that "obviously" do not depend
    on an overridden field would mean parsing that prose, or hard-coding a dependency
    table that nothing in the model asserts. That is inventing a dependency we cannot
    derive, which ``CLAUDE.md`` §5 forbids; dropping is the honest side of the
    trade — the sidecar loses provenance it can no longer vouch for, rather than
    keeping provenance that may be false. A run that wants a derivation to survive an
    override can carry its own entry, which always wins.

    ``None`` rather than ``[]`` when there is nothing, so a draft that had no
    ``implicit`` key does not acquire an empty one.
    """
    exp_items = (
        [e for e in (experiment_draft.get("implicit") or []) if isinstance(e, dict)]
        if inherit
        else []
    )
    run_items = list(run_draft.get("implicit") or [])
    run_abouts = {e.get("about") for e in run_items if isinstance(e, dict)}
    merged = [copy.deepcopy(e) for e in exp_items if e.get("about") not in run_abouts]
    merged.extend(copy.deepcopy(run_items))
    return merged or None


def _diverges_from_experiment(resolutions: dict[str, "Resolution"]) -> bool:
    """Whether this run holds a DIFFERENT ENVELOPE from the experiment anywhere.

    ENVELOPE, not value, and the distinction is deliberate — see the F-D paragraph in
    :func:`_merge_implicit`, whose headline used to say "values" while this compared
    ``payload``. :attr:`Resolution.value` would give the narrower comparison and is
    deliberately not used: an override that re-records the experiment's value under
    its own ``user_confirmation`` has re-sourced it, and the experiment's derivations
    were evidenced against the experiment's envelope, not against that one.

    The ``inherit`` input to :func:`_merge_implicit`, inverted. It reads only what
    :func:`resolve_inherited` already computed, so it adds no traversal and no second
    definition of what a run holds at an address.

    A resolution is divergent when it came from an override AND its payload differs
    from the experiment's CURRENT payload at the same address. ``inherited_payload``
    is ``None`` for an override at an address the experiment does not carry, and that
    counts as divergence: there is nothing for the run to agree with, so the
    experiment's derivations cannot be shown to be true of it.

    ``displaced_payload`` is deliberately NOT consulted. It records what an override
    displaced WHEN IT WAS RECORDED, and the question here is about now — an
    experiment-level edit that moved the experiment onto the override's own value
    should stop the entries being withheld, and an edit that moved it away should
    start withholding them.
    """
    return any(
        resolution.provenance == PROVENANCE_OVERRIDDEN
        and resolution.payload != resolution.inherited_payload
        for resolution in resolutions.values()
    )


def _merge_block_evidence(experiment_draft: dict, run_draft: dict) -> dict | None:
    """Experiment ``block_evidence`` overlaid by the run's. Run wins per key.

    THIS MERGE IS A REQUIREMENT, NOT A CONVENIENCE. ``attribution`` is
    experiment-level and inherited, and ``validate_draft`` demands a covered
    ``attribution:<name>|<role>`` entry for every contributor. Inherit the block
    without its evidence and EVERY fan-out export fails the no-guessing gate.

    It is safe because the keys are namespaced per block by construction
    (``attribution:``, ``series:``, ``qc:status``, ``links:``), so an experiment-level
    key and a run-level key cannot collide unless they describe the same block — in
    which case the run's is the more specific and correctly wins.
    """
    merged: dict = {}
    for src in (experiment_draft.get("block_evidence"), run_draft.get("block_evidence")):
        if isinstance(src, dict):
            merged.update(copy.deepcopy(src))
    return merged or None


@dataclass
class ExportUnit:
    """ONE thing that becomes ONE official ISAAC record.

    Either a :class:`Run` (``run`` set, ``target_id == run.id``, contract §1 D1) or
    the experiment itself when it has no runs (``run is None``,
    ``target_id == experiment.id``) — the shape every stored experiment has today.

    ``draft`` is the FULLY RESOLVED draft for this unit. For the zero-run unit it is
    ``experiment.draft`` ITSELF, not a copy, so that path is provably identical to
    the pre-fan-out call. For a run it is a fresh composed dict; mutating it cannot
    reach the run's or the experiment's stored draft, which is what keeps
    inheritance BY REFERENCE (contract §2 D2) rather than by copy: the composition
    is recomputed on every read and nothing is ever written back down into a run.
    """

    experiment: "Experiment"
    run: "Run | None"
    target_id: str
    draft: dict

    @property
    def run_id(self) -> str | None:
        return self.run.id if self.run is not None else None

    @property
    def run_label(self) -> str | None:
        return self.run.label if self.run is not None else None

    def current_record_id(self) -> str | None:
        """The record id this unit already holds, or ``None`` if never exported."""
        return self.run.record_id if self.run is not None else self.experiment.record_id

    def mark_exported(self, record_id: str) -> None:
        """Record that this unit's artifact pair was written, under ONE id.

        **The equality is enforced, not assumed (review item C7).** This module named
        the same concept two ways: ``unit.target_id`` (what the export prune's
        keep-set is built from) and ``Run.record_id`` (what the artifact file is
        actually named by). They coincide today because ``routes._write_record``
        passes ``result.record["record_id"]``, minted by
        ``export_draft(..., record_id=unit.target_id)`` — so a mismatch is
        unreachable, which is exactly why it should be stated here, where a future
        edit would have to break it deliberately rather than silently.

        ``ValueError`` and not ``assert``: an assertion disappears under ``python
        -O``, and this guards a filesystem-naming invariant that a destructive
        operation relies on.
        """
        if record_id != self.target_id:
            raise ValueError(
                "export unit record id does not match its target id "
                f"({record_id!r} != {self.target_id!r}); the artifact would be "
                "named by one and tracked by the other"
            )
        if self.run is not None:
            self.run.record_id = record_id
        else:
            self.experiment.record_id = record_id

    def record_path(self) -> Path | None:
        """``<records_dir>/<target_id>.json``, or ``None`` if the id is not a record id.

        ``None`` rather than a path built from an untrusted string: ``Run.id`` comes
        out of a persisted document through :func:`_as_str`, so it can be anything at
        all. A unit whose id is not a record id can never be exported anyway —
        ``export_draft`` refuses it with a typed draft error — so refusing to name a
        file for it costs nothing and removes the only place this slice could have
        turned document content into a filesystem path.
        """
        if not is_record_id(self.target_id):
            return None
        return self.experiment.records_dir / f"{self.target_id}.json"

    def sidecar_path(self) -> Path | None:
        if not is_record_id(self.target_id):
            return None
        return self.experiment.records_dir / f"{self.target_id}.evidence.json"

    def materialised(self) -> bool:
        """State says exported AND both halves of the artifact pair are on disk.

        The same three-part test the export route's immutability guard has always
        applied to the single-record case (``exported() and record.exists() and
        sidecar.exists()``), just addressed per unit. Anything less than all three is
        a half-written state the export path reconciles rather than refuses.
        """
        record_path = self.record_path()
        sidecar_path = self.sidecar_path()
        return (
            self.current_record_id() is not None
            and record_path is not None
            and record_path.exists()
            and sidecar_path is not None
            and sidecar_path.exists()
        )


def _add_sibling_link(draft: dict, target_id: str, sample_id: str) -> None:
    """Add one ``same_sample_as`` link plus the evidence entry it is required to cite.

    ``validate_draft`` refuses a link with no ``block_evidence`` under
    ``links:<rel>|<target>|<basis>``, so emitting the link without the evidence would
    make every fan-out export fail. The evidence is a ``derivation`` with a stated
    rule — the one form of evidence that does not claim an observation — and the rule
    quotes the schema clause that licenses the relation. That is the *documented rule*
    ``CLAUDE.md`` §5 permits an inference to rest on, not a scientific judgement.

    Idempotent on the (rel, target, basis) tuple, because ``validate_draft`` refuses
    a duplicate link tuple as an unkeyable evidence collision.
    """
    links = draft.get("links")
    if not isinstance(links, list):
        links = []
    tuple_key = (SIBLING_REL, target_id, SIBLING_BASIS)
    if not any(
        isinstance(link, dict)
        and (link.get("rel"), link.get("target"), link.get("basis")) == tuple_key
        for link in links
    ):
        links = [*links, {"rel": SIBLING_REL, "target": target_id, "basis": SIBLING_BASIS}]
    draft["links"] = links

    block_evidence = draft.get("block_evidence")
    if not isinstance(block_evidence, dict):
        block_evidence = {}
    key = f"links:{SIBLING_REL}|{target_id}|{SIBLING_BASIS}"
    block_evidence.setdefault(
        key,
        [
            derivation(
                rule=(
                    "Both records carry sample.sample_id "
                    f"{sample_id!r}. For a record this export writes, that is the "
                    "value being written; for a record already on disk, it was read "
                    "back from that record. The official ISAAC schema states that "
                    "two records share a sample_id if and only if they measured the "
                    "same physical object, and names that equality as the basis "
                    "that gives same_sample_as links their meaning. Derived from "
                    "record content at export; no scientific judgement was applied."
                )
            )
        ],
    )
    draft["block_evidence"] = block_evidence


def _linkable(unit: ExportUnit) -> tuple[str, str] | None:
    """``(link target record id, sample_id)`` that is TRUE OF A RECORD, or ``None``.

    THIS FUNCTION IS THE C1 FIX, and the defect it closes was a fabricated scientific
    relationship in an official ISAAC record. Grouping used to read the CURRENTLY
    COMPOSED ``sample.sample_id`` for every unit, including units whose record was
    written long ago. A written record is frozen; the composed draft is not. Change
    the experiment-level ``sample.sample_id``, add a run, export, and the measured
    result was::

        OLD record ...817C sample_id: SYN-ORIGINAL
        NEW record ...JYM5 sample_id: SYN-DIFFERENT
        NEW record links: [{'rel': 'same_sample_as', 'target': '...817C', ...}]

    plus a sidecar derivation asserting that BOTH records carry ``SYN-DIFFERENT``.
    The link was disprovable from the two records alone.

    So the value depends on which document will speak for this unit:

    * **materialised** (state exported AND both halves on disk) — its record will not
      be rewritten by this export, so the only honest source is the record itself.
    * **not materialised** — this export writes it from ``unit.draft``, so the draft
      is what the record will carry.

    **An unreadable materialised record yields ``None``, and does NOT fall back to
    the draft.** A fallback would restore exactly the defect for the one case where
    we have the least evidence. A unit with no linkable id is simply not grouped:
    no link is a legitimate outcome (``CLAUDE.md`` §5), a false one is not.

    **THE TARGET IS ``unit.target_id``, NOT THE RECORD'S OWN ``record_id`` (review
    item F6).** The first revision of this function returned ``record["record_id"]``
    and justified it as *"the id of the file that exists"*. That was wrong by one
    level of indirection: the FILE is named by ``unit.target_id``
    (:meth:`ExportUnit.record_path`), and the ``record_id`` string INSIDE it is
    separate content that a document written outside this module can set to anything.
    With the divergence section 10's own C7 test plants, the measured result was a
    link whose target matched no stem in the directory::

        targets = ['01JQZ0ADVPHANTOMTARGET0001']
        stems   = ['01KZMKT511J6RCMDGHJ1AVH618', '01KZMKT51KCWDN6C17WRYKQZF7']

    — the application manufacturing exactly the ``dangling_link_count`` that
    :func:`routes._link_targets_of_surviving_records` exists to prevent.

    A record whose own ``record_id`` DISAGREES with the file carrying it yields no
    link at all, rather than a link under the filename. The disagreement means the
    record cannot vouch for its own identity, and a record we cannot trust to name
    itself is not evidence for a relation between records. Refusing is the same
    fail-closed side as the unreadable case above.

    ``is_record_id`` on the target as well, because the schema constrains
    ``links[].target`` to ``^[0-9A-Z]{26}$``.
    """
    if not unit.materialised():
        sample_id = _exported_field_value(unit.draft, SAMPLE_ID_PATH)
        if isinstance(sample_id, str) and sample_id.strip() and is_record_id(unit.target_id):
            return unit.target_id, sample_id
        return None

    record_path = unit.record_path()
    if record_path is None:
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # never guess what a record we could not read says
    if not isinstance(record, dict):
        return None
    if record.get("record_id") != unit.target_id:
        return None  # the record does not name the file it is stored in
    sample = record.get("sample")
    sample_id = sample.get("sample_id") if isinstance(sample, dict) else None
    if not isinstance(sample_id, str) or not sample_id.strip():
        return None
    if not is_record_id(unit.target_id):
        return None
    return unit.target_id, sample_id


def _apply_sibling_grouping(experiment: "Experiment", units: list[ExportUnit]) -> None:
    """Relate the sibling records of ONE fan-out, using schema-native means only.

    Two things happen, and the second is much narrower than it could have been.

    **The grouping tag** goes on every unit. It is a label, it encodes a stored
    identifier, and ``tags`` is the schema's own answer to "how do I group a SET of
    records". Nothing scientific is claimed by it.

    **The links.** Exactly ONE relation is emitted: ``same_sample_as`` with basis
    ``same_sample_id``, between units whose RECORDS carry the same non-empty
    ``sample.sample_id`` — read from the written record for a unit this export will
    not rewrite, and from the composed draft for a unit it will (:func:`_linkable`,
    which exists because the earlier "currently composed value" rule emitted links
    that the two records disproved). Every other member of the vocabulary the fan-out could have
    reached is DELIBERATELY NOT EMITTED, and each omission has a reason:

    * ``replica_of`` / ``replicate_preparation`` — asserts that two runs are
      replicates of one another. Nothing in the stored state says so. Two runs of one
      experiment may just as well be a deliberate temperature series, which is the
      opposite claim. Guessing it would be exactly the scientific judgement
      ``CLAUDE.md`` §5 forbids.
    * ``follows`` — a procedural/temporal claim. ``Run.ordinal`` is documented in this
      module as an ORDER KEY for display, explicitly not a label and explicitly
      renameable/reorderable, so it is not evidence that one measurement followed
      another. ``timestamps.acquired_start_utc`` would be closer, but "B started after
      A" is still not "B follows A" in the schema's sense, and no stored field asserts
      the procedural relation.
    * ``derived_from`` — nothing in the model records that one run was derived from
      another.
    * ``matched_operating_conditions`` — computable (compare the resolved
      ``context.*``), but it is a BASIS, not a relation, and every ``rel`` it could
      justify is one of the three refused above. Emitting a basis with a guessed
      ``rel`` would launder the guess through a legal-looking enum value.
    * ``shared_material_batch`` — no batch is stored anywhere in the model.

    So on an experiment whose runs carry no ``sample.sample_id``, or different ones,
    the honest output is the shared tag and NO links at all. That is a legitimate
    outcome, not a gap to be filled later with something plausible.

    **One asymmetry, disclosed.** A run exported LATER links to its already-exported
    siblings, but those siblings' records were written before it existed and are
    immutable, so they do not gain the reverse link. Rewriting them to add it would
    break record immutability, which is a stronger guarantee than link symmetry.

    **A cost, stated rather than hidden.** Grouping now READS each materialised
    unit's record from disk, once per :meth:`Experiment.export_units` call — and that
    method is called by ``draft_ok``/``status``/``export_ready``, so a read-only
    detail GET pays it. It is bounded by the number of runs and by this experiment's
    own records dir, and it is the price of the link being checkable. See the
    performance note in this module's fan-out section header.
    """
    tag = _group_tag(experiment.id)
    if tag is not None:
        for unit in units:
            tags = unit.draft.get("tags")
            if not isinstance(tags, list):
                tags = []
            if tag not in tags:
                tags = [*tags, tag]
            unit.draft["tags"] = tags

    # `_linkable` decides what each unit's RECORD will say, which is not the same
    # question as what its draft says — see that function for the measured defect.
    by_sample: dict[str, list[tuple[ExportUnit, str]]] = {}
    for unit in units:
        linkable = _linkable(unit)
        if linkable is not None:
            target_id, sample_id = linkable
            by_sample.setdefault(sample_id, []).append((unit, target_id))

    for sample_id, group in by_sample.items():
        if len(group) < 2:
            continue  # nothing to relate; emit no link rather than a self-link
        for unit, _ in group:
            for other, other_target in group:
                if other is not unit:
                    _add_sibling_link(unit.draft, other_target, sample_id)


def without_sibling_links(record: dict) -> dict:
    """``record`` with every link this module's grouping emits removed.

    PUBLIC, and used by exactly one caller: ``dependencies._fan_out_artifact_state``
    (review item F4). It lives here because the ``(rel, basis)`` pair it filters on is
    defined here, and a second copy of that pair in the freshness module would be free
    to drift away from what the export actually writes.

    WHY A FRESHNESS COMPARISON MUST IGNORE THESE. ``artifact_state`` asks "is the
    written record still a faithful projection of the current draft", and the draft it
    compares against comes from :meth:`Experiment.export_units`, which applies
    :func:`_apply_sibling_grouping` to EVERY unit including materialised ones. So
    exporting a second run adds the REVERSE link into the first run's composed draft —
    a link that function's own docstring says the first record will deliberately never
    gain, because records are immutable. Measured before this fix: export run 1 alone,
    add run 2, export, and run 1's artifact reported::

        {"state": "stale", "reason": "The record changed after export; … regenerate
         the record (or reset the workspace) to refresh it."}

    Nothing had changed, re-export answered 409, and the only remedy the reason
    offered was a destructive whole-workspace reset. A permanent unrepairable
    ``stale`` is worse than no signal, because it trains a reader to ignore the one
    that is real.

    THE NARROWNESS IS THE POINT, and it is stated because it is a real loss. Only
    links matching BOTH :data:`SIBLING_REL` and :data:`SIBLING_BASIS` are dropped, and
    they are dropped from BOTH sides of the comparison, so a link a run carries for
    any other reason still stales its record when it changes.

    THE FILTER IS ON ``(rel, basis)``, NOT ON PROVENANCE, AND THE OLD WORDING HID
    THAT (review item F-E). It said what this cannot detect is "a change to a
    ``same_sample_as`` link on a materialised record — which is exactly the change
    that record can never receive", which reads as though the blind spot were exactly
    co-extensive with the links this module emits. It is not. Nothing here asks WHO
    wrote the link. A ``same_sample_as``/``same_sample_id`` pair authored by any other
    means — added to a draft by hand, or by some future route — is dropped by this
    filter too, and so a record that gains or loses one after export does NOT report
    ``stale``. Measured, alongside the control: the same edit to a ``derived_from``
    link stales the record correctly.

    Why it is nonetheless kept as written: no route in this API authors a ``links``
    block today, so the reachable set is exactly the links this module emits, and for
    those the blind spot is a difference the record can never receive. If a link-
    authoring path is ever added, this filter becomes wrong before that path ships
    — it will need the provenance test the ``(rel, basis)`` pair is standing in for.

    ``links`` is DROPPED rather than left empty when nothing survives, because
    ``export.transform`` omits the key entirely for a draft with no links, and an
    empty list beside an absent key would compare unequal for no reason. Never
    mutates its argument.
    """
    links = record.get("links")
    if not isinstance(links, list):
        return record
    kept = [
        link
        for link in links
        if not (
            isinstance(link, dict)
            and link.get("rel") == SIBLING_REL
            and link.get("basis") == SIBLING_BASIS
        )
    ]
    if kept == links:
        return record
    trimmed = dict(record)
    if kept:
        trimmed["links"] = kept
    else:
        trimmed.pop("links", None)
    return trimmed


def sibling_link_conflicts(units: list[ExportUnit]) -> list[dict]:
    """Rewrites this export would perform that a SURVIVING record already disproves.

    REVIEW ITEM F7, and it is the converse of the question :func:`_linkable` asks.
    ``_linkable`` closed EMIT-TIME falsity — "will the record I am about to write
    assert something its target disproves?". Nothing asked the other direction: *does
    rewriting this record falsify a link a surviving sibling already carries?*

    Measured before this fix. Two runs share ``SYN-A``, are exported, and are mutually
    linked. Delete run 1's artifact pair, change the experiment's
    ``sample.sample_id``, and export along the blessed self-heal path::

        01…63G  sample_id SYN-CHANGED  links []
        01…63H  sample_id SYN-A        links ['01…63G']   <- asserts a shared id

    Disprovable from the two records alone — the same class of defect as C1, one
    direction over — and this time the falsified record is the SURVIVING one, which is
    immutable and cannot be corrected afterwards.

    **SO THE EXPORT IS REFUSED, and refusal is the answer rather than a placeholder
    for a better one.** Within record immutability there is no write that leaves both
    records true: rewriting the sibling to drop its link is the immutability breach
    this module refuses everywhere else, and writing the unit anyway leaves a false
    claim in an official ISAAC record (``CLAUDE.md`` §5). Declining to write, and
    saying which pair disagrees, is the only remaining honest act. The operator can
    restore the value, or delete the run.

    Only MATERIALISED units are consulted as accusers, because only a written record
    can already carry the link, and only NOT-materialised units are candidates,
    because a materialised unit is skipped by the export entirely and its record is
    not rewritten. An unreadable sibling accuses nobody: it is fail-open here on
    purpose, and that asymmetry with the prune is deliberate — the prune's fail-closed
    protects against DELETING a file, while blocking every export in the workspace on
    one corrupt record would turn a repairable artifact into a wedge.

    Returns one entry per conflicting ``(unit, sibling)`` pair, in unit order.
    """
    conflicts: list[dict] = []
    pending = [unit for unit in units if not unit.materialised()]
    if not pending:
        return conflicts
    survivors: list[tuple[str, dict]] = []
    for unit in units:
        if not unit.materialised():
            continue
        record_path = unit.record_path()
        if record_path is None:
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict):
            survivors.append((unit.target_id, record))

    for unit in pending:
        candidate = _exported_field_value(unit.draft, SAMPLE_ID_PATH)
        for sibling_id, record in survivors:
            asserted = any(
                isinstance(link, dict)
                and link.get("rel") == SIBLING_REL
                and link.get("basis") == SIBLING_BASIS
                and link.get("target") == unit.target_id
                for link in record.get("links") or []
            )
            if not asserted:
                continue
            sample = record.get("sample")
            sibling_value = sample.get("sample_id") if isinstance(sample, dict) else None
            if candidate == sibling_value:
                continue
            conflicts.append(
                {
                    "run_id": unit.run_id,
                    "run_label": unit.run_label,
                    "record_id": unit.target_id,
                    "sibling_record_id": sibling_id,
                    "basis": SIBLING_BASIS,
                }
            )
    return conflicts


def _run_artifact_presence(experiment: "Experiment", run: "Run") -> list:
    """``[run_id, record_present, sidecar_present]`` for one run's artifact pair.

    The per-run half of :func:`_plan_digest_row`. ``record_id`` is guarded by
    :func:`_as_record_id` at hydration, so the path built here can only come from a
    value that passed ``is_record_id``; the belt-and-braces check costs nothing and
    keeps this function safe if it is ever called on an instance built by hand.
    """
    record_id = run.record_id
    if not isinstance(record_id, str) or not is_record_id(record_id):
        return [run.id, False, False]
    records_dir = experiment.records_dir
    return [
        run.id,
        (records_dir / f"{record_id}.json").exists(),
        (records_dir / f"{record_id}.evidence.json").exists(),
    ]


@dataclass
class Experiment:
    id: str
    title: str
    created_utc: str
    source: dict
    draft: dict
    answer_log: list = field(default_factory=list)
    record_id: str | None = None
    #: Monotonic per-record version. Starts at 0 on create and on the canonical
    #: seed; bumped ONLY by ``save_versioned`` when the authoritative scientific
    #: state actually changes. Never derived — it is stored.
    rev: int = 0
    #: Wall-clock UTC of the last authoritative change. Defaults to
    #: ``created_utc`` (see ``__post_init__``) so a freshly-created or legacy
    #: record has a meaningful, non-empty timestamp.
    updated_utc: str = ""
    #: A per-instantiation opaque nonce, minted fresh at genuine (re)creation and
    #: PRESERVED across saves / loads / no-op re-entries. It makes the public token
    #: differ across a delete->recreate even when ``rev`` returns to 0 (ABA-safe).
    generation: str = ""
    #: Which SCOPE this instance's files live in: ``None`` = the normal scope,
    #: otherwise the tutorial session id. Deliberately NOT persisted (absent from
    #: ``to_state``) and deliberately NOT part of ``_authoritative_signature``: the
    #: scope is a property of WHERE the record is stored, not of the scientific
    #: state, so the same content in two sessions hashes identically and a state
    #: file carries nothing that would go stale if the directory moved.
    session_id: str | None = None
    #: The experiment's runs — one measurement condition each, one exported ISAAC
    #: record each (contract §1 D1). Ordered by :meth:`sorted_runs`, NOT by list
    #: position and NOT by label.
    #:
    #: NO MAXIMUM IS IMPOSED, and none is imposed anywhere else either. The brief's
    #: §5 forbids a product-level cap, and no defensive cap is added because there
    #: is no number this repository can justify: a defensive bound is only honest
    #: when it is derived from a measured resource limit, and nothing here has been
    #: measured. The real resource pressure is named and located rather than papered
    #: over with an arbitrary constant — runs currently live inside ONE state
    #: document that is rewritten whole on every save, which is exactly why contract
    #: §8 D7 moves them to relational rows in migration ``0002``. That is the fix;
    #: a magic number would only hide the need for it.
    runs: list["Run"] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Legacy-safe default: a pre-P27.2 state file (or a bare construction)
        # carries no ``updated_utc``; anchor it to ``created_utc`` in memory. This
        # never writes — only a real mutation rewrites the file.
        if not self.updated_utc:
            self.updated_utc = self.created_utc
        # A legacy / bare record carries no ``generation``; anchor it to a
        # deterministic id-derived fallback (stable across loads -> stable ETag).
        if not self.generation:
            self.generation = _legacy_generation(self.id)

    # -- filesystem --

    @property
    def dir(self) -> Path:
        return scope_root(self.session_id) / self.id

    @property
    def records_dir(self) -> Path:
        return self.dir / "records"

    @property
    def state_path(self) -> Path:
        return self.dir / "experiment.json"

    def version_token(self) -> str:
        """The public opaque concurrency token: ``<generation>.<rev>``."""
        return f"{self.generation}.{self.rev}"

    def etag(self) -> str:
        """The HTTP ETag: the version token as a strong quoted validator."""
        return f'"{self.version_token()}"'

    def record_path(self) -> Path | None:
        return self.records_dir / f"{self.record_id}.json" if self.record_id else None

    def sidecar_path(self) -> Path | None:
        rid = self.record_id
        return self.records_dir / f"{rid}.evidence.json" if rid else None

    # -- persistence --

    def to_state(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_utc": self.created_utc,
            "source": self.source,
            "draft": self.draft,
            "answer_log": self.answer_log,
            "record_id": self.record_id,
            "rev": self.rev,
            "updated_utc": self.updated_utc,
            "generation": self.generation,
            "runs": [r.to_state() for r in self.sorted_runs()],
        }

    def save(self) -> None:
        """Persist this experiment's state, durably when the deployment has a database.

        THE DURABLE WRITE GOES FIRST, and the order is load-bearing rather than
        arbitrary. If the database is UNAVAILABLE, this raises and the workspace
        file is NOT rewritten, so the reader is told their change did not stick
        instead of seeing it applied locally and losing it at the next pod restart.
        If the database write succeeds and the file write then fails, the durable
        copy is ahead of the working copy — recoverable, where the other ordering
        loses the write outright.

        THAT PARAGRAPH IS TRUE OF AN OUTAGE AND FALSE OF A REFUSAL, and it used to
        be written as though it covered both. On a :class:`DurableWriteConflict`
        this experiment's OWN state is still never written anywhere — but the
        workspace file IS rewritten, with the WINNER's document. "Nothing is
        written" and "this client's change is not written" are different claims,
        and only the second one holds for all three failure types.

        BUT "HYDRATION REPAIRS IT" IS TOO STRONG, and this line used to say it.
        ``PostgresOrdinaryStore.hydrate`` writes back only a record whose
        ``experiment.json`` is ABSENT; a present-but-stale one is skipped and never
        refreshed. So a row that is ahead of an existing file stays ahead until a
        write refuses — which is why the refusal below adopts the winner rather
        than leaving the skew for a reader that will not fix it.

        SCOPE IS THE GATE. ``_ordinary_store`` returns ``None`` for any record that
        belongs to a worked-example session, so a session's records never reach the
        database. This is the first of the three guards described in
        ``experiment_repository``; the store itself raises on the same condition,
        so the guard does not depend on this one line being right.

        A REFUSED DURABLE WRITE ADOPTS THE WINNER'S DOCUMENT LOCALLY BEFORE IT
        RE-RAISES, and that is not a nicety — without it the compare-and-swap
        introduces a wedge it can never leave. Both orderings above can leave the
        row AHEAD of the file: a fault between the two writes does it in one
        process, and a second replica that hydrated earlier does it without any
        fault at all (``PostgresOrdinaryStore.hydrate`` skips a record whose
        ``experiment.json`` is already present, so it never refreshes one). From
        there every mutation computes ``max(self.rev, disk_rev) + 1``, which is the rev
        the row ALREADY holds — the predicate refuses it, and refuses the next one,
        and the next: a permanent ``412`` over reads that keep serving the stale
        local file. Copying the winner's state into the file makes the advertised
        remedy true — the client re-reads, gets the winner, and its next write is
        strictly ahead. It is the LOCAL file only: the database already holds this
        document, and ``rev`` is deliberately not bumped, because nothing new
        happened.

        THIS IS THE ONLY CALL TO ``PostgresOrdinaryStore.persist`` IN THE
        CODEBASE, which is why the adoption lives here and not in the route helper
        that renders the 412. Not "it covers four call sites instead of three" —
        it covers every caller by construction, and a caller added later inherits
        it without knowing it exists.
        """
        store = _ordinary_store(self.session_id)
        if store is not None:
            from .experiment_repository import DurableWriteConflict  # noqa: PLC0415 - cycle

            try:
                store.persist(self)
            except DurableWriteConflict as conflict:
                # A FAILURE TO HEAL MUST NOT ESCALATE A CLEAN 412 INTO A 500. The
                # refusal is already the correct answer; adopting the winner only
                # shortens how long the client stays behind. So every failure of the
                # adoption is caught, including the scope assertion inside it.
                #
                # BUT DEGRADING IS NOT SILENT — this module says so itself, at
                # `_hydrate_ordinary_scope`, and `experiment_repository` says it
                # again. An earlier revision of this block swallowed the failure
                # with `contextlib.suppress` and emitted NOTHING: no log record, and
                # correctly no `storage_failure` bit, because a refusal is not an
                # outage. The consequence was that a deployment where the adoption
                # ALWAYS fails — read-only filesystem, permission change, full disk
                # — presents as EXACTLY the permanent wedge this whole change exists
                # to remove, with no signal anywhere. The catch stays this broad;
                # only the silence was the defect.
                #
                # `_log.warning`, not `.error`: the request is answered correctly
                # and the client's remedy is unchanged. What an operator needs to
                # know is that the remedy will not converge until the workspace is
                # writable again.
                try:
                    self._adopt_winner_locally(conflict)
                except Exception as heal_failure:  # noqa: BLE001 - see above
                    _log.warning(
                        "durable conflict: could not adopt the stored document for "
                        "record %s (%s). The local copy is still behind the row, so "
                        "writes to this record will keep being refused until it can "
                        "be refreshed.",
                        self.id,
                        type(heal_failure).__name__,
                    )
                raise
        atomic_write_text(self.state_path, json.dumps(self.to_state(), indent=2) + "\n")

    def _adopt_winner_locally(self, conflict) -> None:
        """Write the WINNER's stored document into this scope's workspace file.

        Called only from :meth:`save` after the database refused a write, with the
        document the refusing transaction read back. It writes the winner's state
        verbatim — it does not merge, does not bump ``rev``, and does not touch the
        in-memory instance, which ``save_versioned`` is about to roll back anyway.

        SCOPE IS ASSERTED, NOT ASSUMED. A worked-example record can never reach
        this method — ``_ordinary_store`` returns ``None`` for any non-``None``
        ``session_id``, so ``persist`` is never called and no conflict can be
        raised — but "cannot happen" is exactly the kind of claim that stops being
        true when the seam moves, and this method writes files. It raises rather
        than writing into a session directory. ``save`` catches that raise, so the
        failure mode is "no heal", never "a session record written from a row".

        FOUR CONDITIONS ARE CHECKED, AND THE FOURTH IS THE ONE THAT MAKES THE
        WRITE SAFE. A stored document that is missing, filed under a different id,
        not loadable as an ``Experiment``, or NOT AHEAD OF THE LOCAL COPY is
        SKIPPED, and the record stays wedged — which is the honest outcome.

        The first two are the reason :meth:`PostgresOrdinaryStore.hydrate` skips
        them: a row naming another record describes another record. The third is
        this method's own — it is the only writer that puts a database row into
        the workspace on an ERROR path, and a state file no later read can parse
        is worse than a stale one.

        The FOURTH was missing, and it was the one holding the other three up.
        Nothing here stopped an OLDER document being written over a newer local
        copy; a winner at ``rev 1`` really was written over a local file at
        ``rev 5`` when probed directly. That is safe today ONLY by a cross-module
        invariant this method neither stated nor checked — a refusal means
        ``Q_UPSERT_EXPERIMENT``'s clause 2 was false, so the stored rev is at
        least the offered rev, which is already past the local one. Leaving the
        single safety property implicit while carefully guarding three lesser ones
        is the shape of defect this method's own docstring warns about. It is
        checked now, against the file that would be overwritten:

        * a DIFFERING ``generation`` -> skip. Two generations cannot be ordered
          (the nonce is random), so "newer" is not defined across them, and a
          refusal implies clause 1 was false, i.e. they matched. A differing one
          here means an assumption has already broken; do not write on top of it.
        * a LOWER ``rev`` -> skip. Never move the local copy backwards.

        An absent or unreadable local file has no claim, so the winner is written.
        That is the ordinary create-time shape, and it is what ``hydrate`` would
        do with the same row.
        """
        if self.session_id is not None:
            raise AssertionError(
                "a worked-example record has no durable row and must never be "
                "healed from one"
            )
        state = conflict.stored_state
        if not isinstance(state, dict) or state.get("id") != self.id:
            return
        try:
            winner = Experiment.from_state(state, session_id=None)
        except (KeyError, TypeError, ValueError):
            return
        local = self._local_state_or_none()
        if local is not None and (
            local.generation != winner.generation or winner.rev < local.rev
        ):
            return
        atomic_write_text(self.state_path, json.dumps(state, indent=2) + "\n")

    def _local_state_or_none(self) -> "Experiment | None":
        """This record as the workspace file currently holds it, or ``None``.

        ``None`` for absent, unreadable, or unparseable — the same tolerance
        :meth:`_persisted_sig_and_rev` applies, and for the same reason: a missing
        or corrupt local file is "no prior state", not an error.
        """
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            return Experiment.from_state(state, session_id=self.session_id)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def _persisted_sig_and_rev(self) -> tuple[str | None, int]:
        """``(authoritative signature, rev)`` of the CURRENTLY on-disk state, or
        ``(None, 0)`` if the file is absent or unreadable (missing/corrupt). Read
        once so ``save_versioned`` can both detect a no-op AND keep the on-disk
        ``rev`` monotonic even when this in-memory instance is stale."""
        if not self.state_path.exists():
            return None, 0
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            sig = _authoritative_signature(
                Experiment.from_state(state, session_id=self.session_id)
            )
            return sig, int(state.get("rev") or 0)
        except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Defensive: a missing/corrupt state file is treated as "no prior
            # state" so a real save still proceeds rather than crashing.
            return None, 0

    # -- runs ------------------------------------------------------------------

    def sorted_runs(self) -> list["Run"]:
        """This experiment's runs in their canonical order.

        Sorted on ``(ordinal, created_utc, id)``. THE LABEL IS NOT IN THE KEY, by
        requirement: ``"Run 10"`` sorts before ``"Run 2"`` lexically, and a run may
        be renamed to anything.

        THE ORDER IS TOTAL BECAUSE RUN IDS ARE UNIQUE, and that uniqueness is
        enforced rather than assumed — :meth:`add_run` refuses a duplicate id and
        :func:`_hydrate_runs` drops one. An earlier version of this docstring claimed
        the two tie-breakers alone made the order total "for any input rather than
        only for well-formed input", which was FALSE and was measured false: two runs
        sharing ``(ordinal, created_utc, id)`` produce an identical key, ``sorted`` is
        merely stable, and reversing the list flipped the result — which would have
        made ``_authoritative_signature`` order-dependent. Uniqueness of the third
        key component is what closes it, so the claim now rests on the invariant that
        is actually enforced.
        """
        return sorted(self.runs, key=lambda r: (r.ordinal, r.created_utc, r.id))

    def next_ordinal(self) -> int:
        """The ordinal a newly-added run should take: one past the current maximum.

        Deliberately max+1 rather than ``len(runs)+1`` — after a run is deleted,
        ``len``-based numbering would re-issue an ordinal that an existing run's
        earlier sibling once had, silently reordering history.
        """
        return max((r.ordinal for r in self.runs), default=0) + 1

    def get_run(self, run_id: str) -> "Run | None":
        for r in self.runs:
            if r.id == run_id:
                return r
        return None

    def add_run(
        self,
        *,
        label: str | None = None,
        draft: dict | None = None,
        created_utc: str | None = None,
        id: str | None = None,
    ) -> "Run":
        """Append a run to this experiment IN MEMORY. Does not save.

        Saving is the caller's, so a route can add a run and persist once inside the
        same ``record_lock`` critical section every other mutation already uses.
        """
        run = new_run(
            self.id,
            ordinal=self.next_ordinal(),
            label=label,
            draft=draft,
            created_utc=created_utc,
            id=id,
        )
        if self.get_run(run.id) is not None:  # pragma: no cover - ULID collision
            raise ValueError(f"run id {run.id!r} already exists on this experiment")
        self.runs.append(run)
        return run

    def resolve_run(self, run: "Run") -> dict[str, "Resolution"]:
        """Every inherited experiment-level address, resolved for ``run``. Read-only.

        Thin wrapper over :func:`resolve_inherited`. Passes the WHOLE draft, because
        experiment-level content lives in both draft namespaces — the ``fields`` map
        AND the top-level ``attribution`` / ``tags`` blocks.
        """
        return resolve_inherited(self.draft, run)

    def set_run_override(self, run: "Run", address: str, payload: object) -> "Override":
        """Record an explicit run-level override at one inherited address. Does not save.

        ``address`` is namespaced — build it with :func:`field_address` or
        :func:`block_address`. Refuses any address that is not experiment-level
        (:class:`NotOverridable`): only an inherited address can be overridden, and
        run-level content is just an ordinary edit to the run's own draft. A
        malformed address raises ``ValueError`` from :func:`parse_address`.

        IDEMPOTENT. Re-applying an equal payload returns the existing override
        unchanged and does NOT restamp ``recorded_utc`` — which is what lets
        ``_run_signature_payload`` include the whole override record without a no-op
        save churning the version.

        BOTH PAYLOADS ARE DEEP-COPIED AT CAPTURE. Storing a live reference was safe
        only by accident: both current write paths replace ``exp.draft`` wholesale,
        so nothing mutated the captured object in place — but the docstring on
        :class:`Override` promises history that "is never refreshed", and one
        ``exp.draft["fields"][path]["value"] = ...`` would have rewritten it through
        the shared reference. The copy makes the promise true by construction instead
        of by the coincidence of how callers happen to write.

        That argument was originally applied to ``displaced`` ONLY, and it is
        STRONGER for ``payload``. An override that silently tracks the object it was
        built from is the exact INVERSE of contract §2 D2: inheritance is by
        reference *on purpose*, and an override is the captured, audited displacement
        of it. A caller overriding "with what the experiment says now, then edited"
        naturally passes the live envelope — measured, ``override.payload`` WAS
        ``exp.draft["fields"][path]``, so a later in-place edit moved the override
        too and ``value`` could never diverge from ``inherited_payload``, which is
        the entire observable point of recording one. It also silently rewrites
        content that carries its own evidence, which the no-guessing rules do not
        allow to change without an act.
        """
        if address_level(address) != LEVEL_EXPERIMENT:
            raise NotOverridable(
                f"{address!r} is not an experiment-level address, so it cannot be overridden"
            )
        existing = run.overrides.get(address)
        if existing is not None and existing.payload == payload:
            return existing
        kind, name = parse_address(address)
        override = Override(
            payload=copy.deepcopy(payload),
            recorded_utc=_now_iso(),
            displaced=copy.deepcopy(_experiment_payload_at(self.draft, kind, name)),
        )
        run.overrides[address] = override
        return override

    def resolved_run_draft(self, run: "Run") -> dict:
        """The complete draft ONE run exports — computed on read, never stored.

        Four layers, in this order, and the order is the rule:

        1. the run's OWN draft, deep-copied (its ``context.*`` fields, its ``series``,
           ``qc``, ``assets``, ``descriptors_outputs``);
        2. every experiment-level address, through :func:`resolve_inherited` — so an
           overridden address contributes the override and an un-overridden one
           contributes the experiment's current value. This is the whole of contract
           §2 D2's read half and it is reused, not re-implemented;
        3. ``meta``, if the run does not carry its own;
        4. the two evidence maps, merged — see :func:`block_level` for why each of the
           five unclassified blocks is treated the way it is. ``implicit`` is the
           exception, and :func:`_merge_implicit` explains it: the experiment's
           entries are carried onto a run that holds the experiment's VALUES and
           withheld from a run that diverges from any of them, because they are
           derivations and a derivation can outlive the value it was derived from.

        Layer 2 is applied ON TOP of layer 1, so if a run's own draft somehow carries
        an experiment-level field directly, the resolution wins. That is not data
        loss by preference: :meth:`set_run_override` refuses to write an
        experiment-level address anywhere but the override map, so such a field could
        only arrive by a document written outside this module, and the resolution is
        the definition of what the run holds there.

        INHERITANCE STAYS BY REFERENCE. Nothing here writes into ``run.draft`` or
        ``self.draft``; the composed dict is built fresh and discarded. Edit an
        experiment-level field and the next call to this method already reflects it,
        with no fan-out write and no run document having copied anything.
        """
        source = run.draft if isinstance(run.draft, dict) else {}
        draft = copy.deepcopy(source)

        fields = draft.get("fields")
        if not isinstance(fields, dict):
            fields = {}
            draft["fields"] = fields

        resolutions = self.resolve_run(run)
        for resolution in resolutions.values():
            if resolution.payload is None:
                continue
            if resolution.kind == ADDRESS_FIELD:
                fields[resolution.name] = resolution.payload
            else:
                draft[resolution.name] = resolution.payload

        experiment_draft = self.draft if isinstance(self.draft, dict) else {}
        if draft.get("meta") is None and experiment_draft.get("meta") is not None:
            draft["meta"] = copy.deepcopy(experiment_draft["meta"])

        # `inherit` is false for a run that DIVERGES IN VALUE at any experiment-level
        # address — see `_merge_implicit` for why the test is "any divergence" rather
        # than "a divergence at the field this entry derives from" (there is no stored
        # link between the two), and for why review item F8 moved it off
        # `not run.overrides`: a NO-OP override stripped every inherited entry while
        # the run held exactly the experiment's values.
        implicit = _merge_implicit(
            experiment_draft, draft, inherit=not _diverges_from_experiment(resolutions)
        )
        if implicit is not None:
            draft["implicit"] = implicit
        block_evidence = _merge_block_evidence(experiment_draft, draft)
        if block_evidence is not None:
            draft["block_evidence"] = block_evidence

        return draft

    def export_units(self) -> list[ExportUnit]:
        """Everything this experiment exports: N records for N runs, else exactly one.

        THE ZERO-RUN UNIT CARRIES ``self.draft`` ITSELF. Not a copy, not a composed
        equivalent — the same object the pre-fan-out route passed to ``export_draft``.
        Backward compatibility is therefore not an assertion this slice makes about
        its own composition rules; it is a property of the code path.

        Sibling grouping runs over ALL units, including ones already exported, so a
        run added later can link to an existing sibling record. It is applied here
        rather than inside :meth:`resolved_run_draft` because a relation is a fact
        about the SET, and a function that composes one run's draft cannot see the set.
        """
        if not self.runs:
            return [ExportUnit(experiment=self, run=None, target_id=self.id, draft=self.draft)]
        units = [
            ExportUnit(
                experiment=self,
                run=run,
                target_id=run.id,
                draft=self.resolved_run_draft(run),
            )
            for run in self.sorted_runs()
        ]
        _apply_sibling_grouping(self, units)
        return units

    def all_units_exported(self) -> bool:
        """Whether EVERY unit this experiment exports already holds a record id.

        Identical to :meth:`exported` when there are no runs — which is why
        :meth:`exported` is left alone rather than redefined. ``exported()`` answers
        a question about ``Experiment.record_id`` specifically, and roughly fifteen
        call sites pair it with :meth:`record_path` to READ the experiment's own
        single artifact. Broadening it would have made those sites claim an artifact
        that, for a fan-out experiment, is not there. Status derivation asks a
        different question, so it gets a different method.

        Deliberately reads ``run.record_id`` directly instead of building units: it
        is called from :meth:`status` on every experiment in a listing, and composing
        N drafts to answer a question about N booleans would be wasteful.
        """
        if not self.runs:
            return self.record_id is not None
        return all(run.record_id is not None for run in self.runs)

    def any_unit_exported(self) -> bool:
        """Whether ANY unit this experiment exports already holds a record id.

        The third member of the family, and it exists because two read-only routes
        were asking the wrong one of the other two (review item F5). ``/audit`` and
        ``/warnings`` describe WHAT IS ON DISK, so their gate is "is there anything to
        describe" — not :meth:`exported` (permanently False for a fan-out, so both
        routes reported a fully-exported experiment as having exported nothing) and
        not :meth:`all_units_exported` (which would have replaced one false answer
        with a narrower one: a PARTIAL fan-out has records on disk and they are worth
        auditing).

        Identical to :meth:`exported` when there are no runs — ``all()`` and ``any()``
        agree on a one-element set — so the common case has exactly one behaviour, as
        it does for :meth:`all_units_exported`.

        Reads ``run.record_id`` directly for the same reason its sibling does: this is
        a question about N booleans, not a reason to compose N drafts.
        """
        if not self.runs:
            return self.record_id is not None
        return any(run.record_id is not None for run in self.runs)

    def clear_run_override(self, run: "Run", address: str) -> bool:
        """Drop an override so the run inherits again. Returns whether one was removed.

        Removal restores inheritance BY REFERENCE — the run goes back to carrying no
        value at that address at all, rather than to carrying a copy of whatever the
        experiment currently says.

        MIRRORS :meth:`set_run_override`'S REFUSALS, and it did not used to. The body
        was ``run.overrides.pop(address, None) is not None`` and nothing else, so it
        would accept ``"garbage"``, ``"field:context.temperature_K"`` or ``"block:qc"``
        without complaint — reporting ``False`` for each, which reads as "there was no
        override there" when the honest answer is "that address could never hold one".
        That was tolerable while the only callers were this module's own tests; it is
        not tolerable now that a route drives it with client input, because a client
        that misspells an address would be told its clear succeeded in the sense that
        nothing was refused. So a non-experiment-level address raises
        :class:`NotOverridable` and a malformed one raises ``ValueError`` from
        :func:`parse_address`, exactly as setting one does.

        THE ``bool`` RETURN AND ITS IDEMPOTENCE ARE DELIBERATELY UNCHANGED. Clearing a
        VALID address that holds no override is ``False``, not an error — that is what
        lets the HTTP operation be repeatable: a client that clears twice, or that
        retries after a dropped response, gets a successful no-op rather than a refusal
        it would have to interpret. Only "you named something that cannot be an
        override" is an error.

        A STORED KEY IS REMOVABLE WHATEVER IT SAYS, and the check order is what makes
        that true. A guard on a REMOVAL must not be able to make stored state
        unremovable, so a key this run actually holds is popped before the address is
        classified at all. :meth:`set_run_override` cannot create such a key, so the
        only ways one exists are a document written outside this module and a future
        reclassification that moves an address off ``EXPERIMENT_LEVEL_FIELD_PATHS``
        while runs still carry overrides at it. Both are real, and in both cases this
        method is the repair path; refusing would leave an override visible in every
        run view with nothing able to delete it. It leaks nothing a reader does not
        already have — the run view publishes every override address it holds — and it
        cannot be used to write, only to remove what is already there.
        """
        if address in run.overrides:
            del run.overrides[address]
            return True
        if address_level(address) != LEVEL_EXPERIMENT:
            raise NotOverridable(
                f"{address!r} is not an experiment-level address, so it cannot hold "
                "an override to clear"
            )
        return False

    def _persisted_run_state(self) -> dict[str, tuple[str, int]]:
        """``{run_id: (authoritative signature, rev)}`` of the CURRENTLY on-disk runs.

        ``{}`` when the state file is absent or unreadable — the same fail-open
        reading ``_persisted_sig_and_rev`` applies, so a corrupt file makes a real
        save proceed rather than crash.

        Hydrates through :func:`_hydrate_runs` rather than looping over the raw
        array, so this and ``Experiment.from_state`` cannot disagree about which
        entries are runs. Building the map by hand skipped a different set and
        collapsed duplicate ids onto one key, which would have silently discarded a
        run's on-disk ``rev`` and let a stale in-memory copy regress it.
        """
        if not self.state_path.exists():
            return {}
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            return {
                run.id: (_run_signature(run), run.rev)
                for run in _hydrate_runs(state.get("runs"))
            }
        except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return {}

    def _bump_changed_runs(self) -> list[str]:
        """Bump ``rev``/``updated_utc`` on each run whose authoritative state changed.

        Returns the ids bumped (a MEASURED list, not an assertion). Called only from
        the write branch of :meth:`save_versioned`, and it is the ONLY writer of
        ``Run.rev`` — which is the invariant that makes excluding ``rev`` from
        :func:`_run_signature_payload` sound. A run whose signature matches disk is
        untouched, so an experiment-only edit (a title change, say) never disturbs a
        run's version.

        A RUN NOT FOUND ON DISK BUMPS TO 1 — and the earlier phrasing of that,
        "a run absent from disk is NEW and bumps to 1", was wrong in a way worth
        recording rather than quietly deleting. It equated "absent from disk" with
        "new", and those differ: ``save()`` is the UNVERSIONED persistence primitive
        and writes runs without bumping anything, so a run first persisted that way
        is already on disk with a matching signature. The next ``save_versioned()``
        therefore skips it — correctly — and it sits at rev 0 rather than at 1.
        Measured; pinned by ``test_a_run_first_persisted_by_a_plain_save_stays_at_rev_0``.

        THAT BEHAVIOUR IS ACCEPTABLE AND IS NOT TO BE "REPAIRED" INTO MATCHING THE
        OLD SENTENCE, for three reasons:

        * it is exactly what the experiment itself does. A plain ``save()`` leaves
          ``Experiment.rev`` at 0 too. Runs are not anomalous; the unversioned
          primitive is simply unversioned, for runs and their experiment alike.
        * rev 0 is a designed, safe value, not a broken one. ``version_token()``
          returns ``"<generation>.0"``, which is unique and non-empty, and it is
          ``generation`` — minted at genuine creation — that defeats a
          delete->recreate ABA at rev 0. Nothing depends on rev being >= 1.
        * the only available repair is worse than the defect. Reaching rev 1 here
          would mean bumping a run whose on-disk signature MATCHES, which breaks the
          byte-stable no-op guarantee and directly contradicts the promise two
          sentences above that an experiment-only edit never disturbs a run's
          version. Trading a real invariant for a cosmetic one is not a fix.

        Monotonicity is untouched either way: a run that is genuinely edited versions
        normally from wherever it sits.

        ``max(run.rev, disk_rev) + 1`` mirrors ``save_versioned``: a stale in-memory
        run can never regress the persisted rev.
        """
        on_disk = self._persisted_run_state()
        bumped: list[str] = []
        for run in self.runs:
            prior = on_disk.get(run.id)
            if prior is not None and prior[0] == _run_signature(run):
                continue
            run.rev = max(run.rev, prior[1] if prior is not None else 0) + 1
            run.updated_utc = _now_iso()
            bumped.append(run.id)
        return bumped

    def save_versioned(self) -> bool:
        """Persist atomically ONLY if the authoritative scientific state changed.

        Compares this record's authoritative signature (title/source/draft/
        record_id — ``answer_log``/``rev``/``updated_utc``/``created_utc`` are
        deliberately EXCLUDED) against the last-persisted signature. If it changed
        (or there is no prior file), bump ``rev``, stamp ``updated_utc``, persist,
        and return ``True``. If it is byte-for-byte the same authoritative state,
        do NOT bump and do NOT rewrite the file (byte-stable no-op) — return
        ``False``. This guarantees an identical scientific re-entry never bumps
        ``rev``.

        The bump is taken from ``max(self.rev, on-disk rev) + 1`` so a stale
        in-memory instance can never *regress* the persisted ``rev`` (defence in
        depth; the API rejects stale writes via ``If-Match`` in P27.3).

        A BYTE-STABLE NO-OP NEVER REACHES ``save()`` AT ALL — it returns above,
        before the bump. That matters to the durable compare-and-swap
        (``experiment_repository.Q_UPSERT_EXPERIMENT``): the only writes that reach
        the database from here carry a rev strictly ahead of the one this process
        read, so the predicate refuses exactly the writes that lost a race and
        nothing else.

        RUNS. The no-op decision is made BEFORE any run version is touched, and
        that ordering is load-bearing: ``_bump_changed_runs`` mutates
        ``Run.rev``/``Run.updated_utc`` in memory, and doing it first would leave a
        rejected no-op having silently advanced a run's version that was never
        written. So the signature is compared, and only on the write branch are the
        changed runs bumped. Run version metadata is excluded from the signature
        (see ``_run_signature_payload``), so the bump cannot feed back into the
        decision that authorised it.

        IF THE SAVE FAILS, THE VERSION METADATA IS ROLLED BACK — THE EXPERIMENT'S
        AND EVERY RUN'S. Without this, an instance whose write was refused (or
        whose database was unreachable) would go on reporting a ``rev`` and an
        ``updated_utc`` that exist nowhere — and the 412 built from it would echo a
        version no client could ever match.

        THE RUN HALF OF THAT ROLLBACK EXISTS ONLY BECAUSE OF THIS MERGE, and it is
        worth saying why, because nothing on either side was wrong. The run work
        bumped run revs and stated plainly that leaving them ahead of disk on a
        failed write was "the pre-existing behaviour of this method, deliberately
        not altered here, because the durable write path is being changed
        concurrently on another branch". That other branch was adding exactly the
        rollback this defers to. Both halves were correct in isolation; taken
        together WITHOUT this loop they reintroduce, at run granularity, the very
        defect the rollback was written to close — and no test on either branch
        could have failed, because neither branch could see the other's half.

        Restoring ``self.rev`` while leaving ``Run.rev`` advanced would also break
        the invariant that ``_bump_changed_runs`` is the ONLY writer of ``Run.rev``,
        which is what makes excluding ``rev`` from the run signature sound: the next
        successful save would compute ``max(run.rev, disk_rev) + 1`` from a value
        that was never persisted, permanently offsetting that run's version series
        from disk. ``test_a_refused_write_rolls_back_run_versions_too`` pins it, and
        goes RED if the loop is removed.
        """
        old_sig, disk_rev = self._persisted_sig_and_rev()
        new_sig = _authoritative_signature(self)
        if old_sig is not None and old_sig == new_sig:
            return False
        previous = (self.rev, self.updated_utc)
        previous_runs = {run.id: (run.rev, run.updated_utc) for run in self.runs}
        self._bump_changed_runs()
        self.rev = max(self.rev, disk_rev) + 1
        self.updated_utc = _now_iso()
        try:
            self.save()
        except BaseException:
            self.rev, self.updated_utc = previous
            for run in self.runs:
                prior = previous_runs.get(run.id)
                if prior is not None:
                    run.rev, run.updated_utc = prior
            raise
        return True

    @classmethod
    def from_state(cls, state: dict, *, session_id: str | None = None) -> "Experiment":
        """Rehydrate from a persisted state dict, bound to ``session_id``'s scope.

        ``session_id`` is supplied by the caller that knew which directory the state
        was read from — it is never read out of ``state``, which deliberately does
        not carry it.
        """
        return cls(
            session_id=session_id,
            id=state["id"],
            title=state["title"],
            created_utc=state["created_utc"],
            source=state.get("source") or {},
            draft=state.get("draft") or {},
            answer_log=state.get("answer_log") or [],
            record_id=state.get("record_id"),
            rev=int(state.get("rev") or 0),  # missing/legacy -> 0
            updated_utc=state.get("updated_utc") or "",  # __post_init__ -> created_utc
            generation=state.get("generation") or "",  # missing/legacy -> deterministic fallback
            # NO MIGRATION IS REQUIRED FOR RUNS, and this line is why. ``from_state``
            # is legacy-tolerant by construction — every optional key is read with
            # ``.get`` and a default — so a state document written before runs
            # existed hydrates to an experiment with ZERO runs rather than raising.
            # That property was verified before this change (a row lacking ``rev``,
            # ``updated_utc`` and ``generation`` hydrates to rev 0 and a
            # deterministic fallback generation) and is preserved here; it is pinned
            # against a hand-written legacy dict by ``test_run_domain_model.py``.
            #
            # ``_hydrate_runs`` also makes this call TOTAL: it never raises, so one
            # malformed run entry can no longer take down the read of the whole
            # workspace.
            runs=_hydrate_runs(state.get("runs")),
        )

    # -- derived views --

    def pending(self) -> list[dict]:
        """Every unanswered blocker on this experiment — ITS OWN AND ITS RUNS'.

        THIS USED TO BE RUN-BLIND, AND THAT WAS A MEASURED DEFECT, not a latent one
        once runs can be exported. It read ``self.draft["pending"]`` alone, so an
        experiment whose single Run held three unanswered blockers reported
        ``pending: 0``, ``status: in_review``. My Experiments groups on ``status()``,
        so a blocked experiment would have been filed as needing nothing. Measured on
        ``201cab0`` before this change:

            experiment with NO runs   -> status: needs_attention | pending: 3
            run carries three blockers-> status: in_review       | pending: 0

        The aggregate is ALL UNITS' BLOCKERS, not "the experiment's own", because
        contract §1 D1 makes each run a record of its own and a record that cannot be
        completed is the experiment's problem regardless of which run holds it.

        Run-sourced entries are TAGGED with ``run_id``/``run_label`` so a caller can
        address a blocker to the run that owns it; experiment-level entries are
        passed through untouched, so a zero-run experiment's list is byte-identical
        to what it always was. A non-dict entry (a malformed persisted document) is
        passed through as-is rather than wrapped — this is a derived view, not a
        place to start repairing documents.
        """
        own = list(self.draft.get("pending") or [])
        if not self.runs:
            return own
        out = list(own)
        for run in self.sorted_runs():
            run_draft = run.draft if isinstance(run.draft, dict) else {}
            for item in run_draft.get("pending") or []:
                if isinstance(item, dict):
                    out.append({**item, "run_id": run.id, "run_label": run.label})
                else:
                    out.append(item)
        return out

    def pending_count(self) -> int:
        return len(self.pending())

    def evidenced_field_count(self) -> int:
        """Draft fields that carry a non-null value AND at least one evidence entry."""
        fields = self.draft.get("fields") or {}
        return sum(
            1
            for env in fields.values()
            if isinstance(env, dict)
            and env.get("value") is not None
            and env.get("evidence")
        )

    def exported(self) -> bool:
        return self.record_id is not None

    def draft_ok(self) -> bool:
        """Whether EVERY unit's draft passes the no-guessing checks.

        Run-aware for the same reason :meth:`pending` is. With runs, ``self.draft``
        alone is not a thing that gets exported — it holds only the experiment-level
        half — so validating it in isolation would answer a question nobody asked
        and would usually answer it ``False`` (no ``series``, no ``qc``).
        """
        if not self.runs:
            return validate_draft(self.draft).ok
        return all(validate_draft(unit.draft).ok for unit in self.export_units())

    def _all_units_pass_dry_run(self) -> bool:
        """Dry-run the export gate over every unit. Writes nothing, never raises.

        ``export_draft`` is called WITHOUT ``record_id``, exactly as the pre-fan-out
        code did. That is deliberate: this is a question about DRAFT validity, and
        passing an id would additionally fail any experiment or run whose id is not a
        ULID — a real possibility for hand-built fixtures, and a change in behaviour
        for the zero-run path this slice promised not to touch.
        """
        try:
            return all(export_draft(unit.draft, REPO_ROOT).ok for unit in self.export_units())
        except Exception:  # pragma: no cover - defensive, keeps the check non-throwing
            return False

    def status(self) -> str:
        """Derive status deterministically; never stored, always recomputed.

        pending > 0                 -> needs_attention
        pending == 0, all exported  -> done
        pending == 0, every unit's dry-run export passes -> ready_to_export
        pending == 0, any unit fails                     -> in_review

        THE AGGREGATE IS "ALL UNITS", AND IT IS CHOSEN RATHER THAN INHERITED. The
        run-domain slice left this open, noting that once one experiment exports to N
        records "is this ready?" has no single-draft answer and that whether the
        aggregate is "all runs ready" or "any run ready" is a product decision. It is
        ALL: a fan-out export is refused unless every eligible run validates
        (contract §3 D4 — a required validation failure on any run blocks the whole
        submission, and there is no ``Submit Anyway``), so any weaker aggregate would
        report a readiness the export path will not honour.

        A zero-run experiment answers exactly as it always did, because its single
        unit IS its own draft.
        """
        if self.all_units_exported():
            return DONE
        if self.pending_count() > 0:
            return NEEDS_ATTENTION
        # Dry-run only: export_draft returns an ExportResult and writes nothing.
        return READY_TO_EXPORT if self._all_units_pass_dry_run() else IN_REVIEW

    def export_ready(self) -> bool:
        """True iff a dry-run export of EVERY unit passes (pending==0 AND the export
        gate succeeds for each), independent of whether anything was already exported.

        Unlike ``status()`` (which short-circuits to DONE once every unit is
        exported), this reflects the CURRENT drafts' export-readiness — so an
        exported record edited back to pending>0 is correctly NOT export-ready.
        Read-only dry-run, exactly as ``status()`` uses ``export_draft``.
        """
        if self.pending_count() > 0:
            return False
        return self._all_units_pass_dry_run()


# --- store operations ---------------------------------------------------------


def create_experiment(
    title: str,
    source: dict,
    draft: dict,
    *,
    id: str | None = None,
    created_utc: str | None = None,
    session_id: str | None = None,
) -> Experiment:
    """Create (or upsert, given an explicit ``id``) and persist an experiment.

    ``id`` / ``created_utc`` default to a random ULID + wall-clock timestamp for
    ad hoc use; the canonical seed passes EXPLICIT fixed
    values so identities/order are stable across restarts and fresh workspaces.

    Generation minting: an ad-hoc new record (random id) has no prior on-disk file
    -> a FRESH generation is minted. An explicit existing id PRESERVES the on-disk
    generation so repeated no-op runs never churn the
    token.
    """
    rid = id or new_record_id()
    generation = _existing_generation(rid, session_id=session_id) or _new_generation()
    exp = Experiment(
        id=rid,
        title=title,
        created_utc=created_utc or _now_iso(),
        source=source,
        draft=draft,
        generation=generation,
        session_id=session_id,
    )
    exp.save()
    return exp


def _seed_source() -> dict:
    return {
        "description": MANAGED_SOURCE_DESCRIPTION,
        "files": list(SOURCE_FILES),
    }


# --- canonical deterministic seed (P26.0a) ------------------------------------
#
# Exactly FIVE canonical synthetic scenarios spanning all four derived workflow
# states. FIXED ids + FIXED created_utc keep ids and list order stable across
# restarts and across fresh workspaces WITHOUT touching src/isaac_records/*. Each
# draft is derived ONLY from the two committed synthetic fixtures + the committed
# demo answers, through the unchanged truth core — no invented values.

_SEED_ID_PREFIX = "01SYNTHXANESSEED000000000"  # + n (1..5) => 26-char id matching RECORD_ID_RE
SEED_NEW_DRAFT_ID = _SEED_ID_PREFIX + "1"
SEED_PARTIAL_ID = _SEED_ID_PREFIX + "2"
SEED_READY_ID = _SEED_ID_PREFIX + "3"
SEED_REVIEW_ID = _SEED_ID_PREFIX + "4"
SEED_DONE_ID = _SEED_ID_PREFIX + "5"

#: The five fixed canonical seed ids. An experiment whose id is in this set is
#: canonical and is NEVER a *managed_legacy* removal candidate (``remove_experiment``
#: refuses it). Reset itself DOES remove + re-materialise each canonical id by
#: design, to restore its content to the deterministic seed baseline.
CANONICAL_IDS = frozenset(
    {SEED_NEW_DRAFT_ID, SEED_PARTIAL_ID, SEED_READY_ID, SEED_REVIEW_ID, SEED_DONE_ID}
)

#: The shared scientific title every canonical seed carries (the lifecycle suffix
#: below distinguishes the five).
#:
#: RENAMING THIS IS A BEHAVIOUR CHANGE, not a copy change, and P1 renamed it.
#: ``title`` is one of the four fields inside :func:`_authoritative_signature`
#: (``{title, source, draft, record_id}``), and :func:`ensure_tutorial_seeded` heals
#: by ID only — it never reconciles the CONTENT of a canonical id that already exists
#: on disk. So in any SESSION that survives the deploy, the five records keep their
#: pre-rename titles while ``routes._demo_baseline`` builds post-rename ones, the
#: two signatures differ, and ``POST /api/demo/run`` answers 409 with a refusal
#: that says the user's record has been edited — when nothing of theirs changed;
#: the baseline's definition did. Auto-healing titles by content is deliberately
#: NOT done (it would let a deploy silently overwrite a record's authoritative
#: state); the remedy is the **Reset Worked Example** control, which removes and
#: re-materialises each canonical id from the current specs. Named correctly here
#: because it was named wrongly: there is no "Reset Workspace" control, and this one
#: is NOT on My Experiments — it lives in the worked-example bar
#: (``apps/web/src/components/TutorialSessionBar.tsx``), which renders only while a
#: session is open, because ``POST /api/demo/reset`` refuses without a session header.
#: So the remedy is reachable only from inside the stranded session itself.
#:
#: WHICH DEPLOYMENTS ARE AFFECTED. There are TWO cases. An earlier version of this note
#: described only the first and asserted it was the only one — "Only a SESSION can be
#: stranded ... for at most ``TUTORIAL_TTL_HOURS``" — which independent review falsified.
#:
#: 1. A STRANDED SESSION — time-bounded and repairable. A session is created on demand and
#:    swept after ``TUTORIAL_TTL_HOURS``, so a rename can strand one for at most that
#:    long, and the **Reset Worked Example** control in the session's own bar fixes it at
#:    once. The S3DF pod mounts ``ISAAC_UI_WORKSPACE`` on an ``emptyDir``
#:    (docs/deployment.md:29), so it loses every session on a pod restart anyway.
#:
#: 2. FIVE CANONICAL RECORDS SITTING IN THE ORDINARY SCOPE, left by a build that predates
#:    scope isolation — NOT time-bounded, and NOT repairable through the UI at all. The
#:    retired ``ensure_seeded()`` materialised them into ``workspace_root()`` itself.
#:    Nothing in this build creates that state, and nothing migrates it away either:
#:    ``list_experiments(None)`` enumerates them (measured — all five, each classifying
#:    ``canonical``), ``sweep_stale_tutorial_sessions`` only ever looks inside
#:    ``_tutorial/``, ``remove_experiment`` REFUSES a canonical id, and
#:    ``POST /api/demo/reset`` refuses without a session header. So no in-app control can
#:    remove or re-materialise them and they keep their pre-rename titles indefinitely;
#:    the remedy is operational — clear the workspace directory. Reachable wherever the
#:    workspace is durable: a developer's default ``/tmp/isaac-ui-workspace`` that has not
#:    been cleared, and the Railway deployment's persistent volume at
#:    ``/data/isaac-workspace`` (docs/personal-deployment-retirement.md:44).
#:
#: The title reaches NO exported artifact — ``src/isaac_records/export.py`` contains
#: no reference to it — so official schema compliance and exported record content
#: are unaffected by any rename here.
_SEED_TITLE_BASE = "XANES Example — CuO (Cu K-edge)"


def _raw_draft() -> dict:
    """Scenario 1 — raw extraction (5 pending -> needs_attention)."""
    return build_draft(CSV_PATH, LISTING_PATH)


def _partial_draft() -> dict:
    """Scenario 2 — only the sha256 answers applied (2 pending -> needs_attention)."""
    answers = load_demo_answers()
    partial = {k: v for k, v in answers.items() if k not in ("series", "descriptor")}
    return apply_answers(build_draft(CSV_PATH, LISTING_PATH), partial)


def _full_draft() -> dict:
    """Scenarios 3 & 5 — all committed answers applied (0 pending)."""
    return apply_answers(build_draft(CSV_PATH, LISTING_PATH), copy.deepcopy(load_demo_answers()))


def _review_draft() -> dict:
    """Scenario 4 — full answers EXCEPT the descriptor's uncertainty sub-key.

    A human supplied a descriptor value but no uncertainty; the official schema
    legitimately blocks export ('uncertainty' is a required property), so the
    REAL export_draft dry-run fails and status derives to in_review. Truthful,
    never faked.
    """
    answers = copy.deepcopy(load_demo_answers())
    answers["descriptor"].pop("uncertainty", None)
    return apply_answers(build_draft(CSV_PATH, LISTING_PATH), answers)


@dataclass(frozen=True)
class _SeedSpec:
    id: str
    created_utc: str
    title: str
    draft_fn: "callable"
    exported: bool
    #: Human-readable name of the SEEDED FIXTURE IDENTITY — HOW this canonical
    #: scenario was MATERIALISED at setup time by ``draft_fn`` (and, for seed 5,
    #: by the export run in ``_materialise_seed``).
    #:
    #: The label is a statement about materialisation, in the PAST TENSE, and it is
    #: deliberately NEVER refreshed afterwards. That combination is what keeps it
    #: honest: the value being invariant is NOT by itself non-contradiction — an
    #: invariant *present-tense state description* over a mutating record is
    #: guaranteed to go false (an earlier wording, "Scenario 2 · Partially
    #: Confirmed", survived unchanged while the record was fully confirmed,
    #: exported and done). What cannot be falsified by any later user action is how
    #: the fixture was built, so that — and only that — is what the wording says.
    #:
    #: Presentation only, and DERIVED — see ``scenario_label``: it is never
    #: persisted in ``Experiment.to_state`` and never reaches a draft, an official
    #: record, an evidence sidecar, or an export.
    scenario: str


def _seed_specs() -> list["_SeedSpec"]:
    return [
        # The `Example N` prefix is retained deliberately (it replaces `Scenario N`,
        # which was development jargon): the NUMBERING is what makes "these are five
        # different examples, not five duplicates" legible at a glance, and the walk-
        # through refers to the records by number. Everything after the prefix names
        # the MATERIALISATION, and `at setup:` is the anchor that keeps it in the past
        # tense — see the load-bearing docstring on ``_SeedSpec.scenario`` above.
        # Without that anchor, "extraction only" / "some answers confirmed" /
        # "descriptor uncertainty omitted" read as descriptions of the record's
        # CURRENT state and go false the moment a user confirms an answer, which is
        # exactly the defect that comment records. Do not drop it.
        _SeedSpec(SEED_NEW_DRAFT_ID, "2026-07-12T00:00:01Z",
                  f"{_SEED_TITLE_BASE} · New Draft", _raw_draft, False,
                  "Example 1 · at setup: extraction only"),
        _SeedSpec(SEED_PARTIAL_ID, "2026-07-12T00:00:02Z",
                  f"{_SEED_TITLE_BASE} · Partially Completed", _partial_draft, False,
                  "Example 2 · at setup: some answers confirmed"),
        _SeedSpec(SEED_READY_ID, "2026-07-12T00:00:03Z",
                  f"{_SEED_TITLE_BASE} · Ready to Export", _full_draft, False,
                  "Example 3 · at setup: all answers confirmed"),
        _SeedSpec(SEED_REVIEW_ID, "2026-07-12T00:00:04Z",
                  f"{_SEED_TITLE_BASE} · Export Review Required", _review_draft, False,
                  "Example 4 · at setup: descriptor uncertainty omitted"),
        _SeedSpec(SEED_DONE_ID, "2026-07-12T00:00:05Z",
                  f"{_SEED_TITLE_BASE} · Exported Record", _full_draft, True,
                  "Example 5 · at setup: export run"),
    ]


#: id -> scenario label for the five canonical seeds, derived from the SAME
#: ``_SeedSpec`` rows that build the titles (one source of truth; the label is
#: never recovered by parsing a title, and the title is never rewritten).
SEED_SCENARIOS: dict[str, str] = {s.id: s.scenario for s in _seed_specs()}


def scenario_label(experiment_id: str) -> str | None:
    """The derived scenario label for a canonical synthetic seed, else ``None``.

    Purely derived at read/serialization time from the record id — nothing is
    stored on disk (``Experiment`` has no ``scenario`` field and ``to_state``
    writes none), so a saved + reloaded record carries no new key. A
    user-created / non-canonical id has NO scenario and yields ``None``, which
    the UI renders as nothing at all.
    """
    return SEED_SCENARIOS.get(experiment_id)


def _write_seed_record(exp: Experiment, result) -> None:
    """Write the REAL export_draft output (record + sidecar) into the records dir.

    Mirrors ``routes._write_record``; never hand-writes schema content.
    """
    exp.records_dir.mkdir(parents=True, exist_ok=True)
    exp.record_id = result.record["record_id"]
    atomic_write_text(
        exp.records_dir / f"{exp.record_id}.json",
        json.dumps(result.record, indent=2) + "\n",
    )
    atomic_write_text(
        exp.records_dir / f"{exp.record_id}.evidence.json",
        json.dumps(result.sidecar, indent=2) + "\n",
    )


def _materialise_seed(spec: "_SeedSpec", *, session_id: str) -> Experiment:
    """Materialise one canonical seed INTO A TUTORIAL SESSION.

    ``session_id`` is REQUIRED and has no default, AND ``None`` is REFUSED at
    runtime. Together those are the enforcement of the product rule "the five worked
    examples exist only inside a tutorial scope".

    THE MISSING DEFAULT ALONE WAS NOT ENOUGH, and it was relied on as though it were.
    ``scope_root(None)`` returns ``workspace_root()`` without raising, so
    ``_materialise_seed(spec, session_id=None)`` — an explicit argument, not a
    forgotten one — used to write ``workspace_root()/<canonical id>/``; independent
    review measured it doing exactly that, and nothing in CI type-checks this package,
    so the annotation caught nothing. The refusal below is what makes the rule
    behavioural: ``validate_tutorial_session_id`` rejects ``None`` (it is not a
    ``str``) with the same path-free :class:`InvalidTutorialSession` a malformed id
    gets, so neither a missing scope nor a malformed one can produce a path.
    """
    validate_tutorial_session_id(session_id)  # refuses None; refuses a malformed id
    if not is_record_id(spec.id):  # guard: fixed ids must match RECORD_ID_RE
        raise ValueError(f"canonical seed id {spec.id!r} is not a valid record id")
    exp = Experiment(
        id=spec.id,
        title=spec.title,
        created_utc=spec.created_utc,
        source=_seed_source(),
        draft=spec.draft_fn(),
        generation=_new_generation(),
        session_id=session_id,
    )
    if spec.exported:
        # Reuse the REAL export output; let the truth core produce the record.
        result = export_draft(exp.draft, REPO_ROOT, record_id=spec.id)
        if not result.ok:  # pragma: no cover - would signal a truth-path regression
            raise RuntimeError(
                "canonical 'done' seed failed real export; refusing to fake a record"
            )
        _write_seed_record(exp, result)
    exp.save()
    return exp


def _experiment_dirs(root: Path) -> list[Path]:
    """Every experiment directory directly under ``root``, in name order.

    Takes the SCOPE ROOT explicitly rather than reaching for ``workspace_root()``,
    so an enumeration can never silently be of the wrong scope.

    A ``_``-prefixed entry is skipped EXPLICITLY. For the normal root that is what
    keeps ``_tutorial/`` out of the record listing, and it is stated as a rule
    rather than left to the ``experiment.json`` existence check below: today
    ``_tutorial/`` holds no ``experiment.json`` of its own, so that check would
    already exclude it, but that is an accident of layout and not a guarantee.
    ``RECORD_ID_RE`` (``\\A[0-9A-Z]{26}\\Z``) can never match a ``_``-prefixed name, so
    no ``_``-prefixed directory can ever legitimately be a record in ANY scope, and
    the skip is therefore unconditional.
    """
    if not root.exists():
        return []
    return [
        p
        for p in sorted(root.iterdir())
        if not p.name.startswith("_") and (p / "experiment.json").exists()
    ]


def ensure_tutorial_seeded(session_id: str) -> None:
    """Materialise the five canonical scenarios (by fixed id) into ONE tutorial session.

    Idempotent: only canonical ids not already present IN THAT SESSION are (re)built,
    so repeated calls — and the idempotent demo pass — never grow the session's
    record count. Nothing here can write outside the session's own directory:
    ``_materialise_seed`` requires a session id and REFUSES ``None``, and this
    function refuses ``None`` too rather than leaning on that — ``scope_root(None)``
    returns ``workspace_root()`` silently, so without the refusal below an unscoped
    call would have enumerated the ordinary workspace looking for canonical ids to
    fill, and only the write itself would have stopped it.

    This replaces the former ``ensure_seeded()``, which ran on EVERY normal read.
    Normal scope is never auto-seeded now; there is no code path that materialises a
    canonical seed into it.

    Locking: this can still race a concurrent ``reset_to_canonical_seed`` for the
    SAME session that is mid-way through ``_remove_experiment_dir`` +
    ``_materialise_seed`` for the same id — without coordination the seeder could
    materialise into a dir the reset is ``rmtree``-ing, raising an uncaught
    ``OSError`` (ENOTEMPTY) -> HTTP 500. So the materialise of a MISSING id is done
    under ``record_lock(spec.id, session_id=session_id)``, the SAME lock reset holds
    around its remove+materialise, closing that window. The lock key includes the
    scope, and so does the reset's, so the two agree; a DIFFERENT session's reset
    holds a different key and correctly does not block this one, because it is
    operating on different files.

    Deadlock-free by construction, and the argument survives scope-aware keys
    unchanged because it never depended on WHICH keys exist, only on how many are
    held at once: the common case (id present) takes NO lock; a lock is acquired for
    at most ONE key at a time and released before the next, so no thread ever holds
    two record locks — the classic lock-ordering cycle cannot form.
    """
    root = scope_root(validate_tutorial_session_id(session_id))  # refuses None + malformed
    for spec in _seed_specs():
        # Cheap lock-free check first (common case: present -> no lock taken, so
        # repeat calls stay contention-free and cannot deadlock).
        if (root / spec.id / "experiment.json").exists():
            continue
        with record_lock(spec.id, session_id=session_id):
            # Re-check under the lock: reset may have just (re)created it, or another
            # seeder may have materialised it; only materialise if STILL missing.
            if not (root / spec.id / "experiment.json").exists():
                _materialise_seed(spec, session_id=session_id)


# --- the durable-store seam ---------------------------------------------------
#
# ``experiment_repository`` imports THIS module (it builds ``Experiment`` objects),
# so the import below is deliberately lazy and inside the function: a module-level
# import would be a cycle. It is also re-resolved on every call rather than cached,
# which is what makes the environment the single source of truth for which backend
# is active — including in a test that monkeypatches ``PGHOST`` per case.


def _ordinary_store(session_id: str | None):
    """The durable store for this scope, or ``None``.

    ``None`` for EVERY worked-example session, unconditionally and before anything
    else is consulted — a session is temporary and synthetic and must never be
    persisted. ``None`` also whenever the deployment has no database configured,
    which is every developer machine and every CI job except the dedicated
    Postgres one.
    """
    if session_id is not None:
        return None
    from .experiment_repository import ordinary_store  # noqa: PLC0415 - cycle

    return ordinary_store()


#: WHY AN ORDINARY-SCOPE HYDRATION PASS DID NOT FINISH. Two labels, because there
#: are two failures and they are NOT the same fact about the deployment — a caller
#: that collapsed them would describe a healthy database as a broken one.
#:
#: ``store_unavailable`` — the ``SELECT`` itself failed. The database is not
#: answering, which ``/api/health`` ALSO reports (``experiment_storage.state:
#: "unavailable"``), because :meth:`PostgresOrdinaryStore.hydrate` records the
#: failure before raising.
#:
#: ``restore_failed`` — the ``SELECT`` SUCCEEDED and the restore did not finish.
#: Writing a working copy is a filesystem write and can fail on its own (a full
#: ``emptyDir`` is the realistic trigger; so is a row this build cannot parse),
#: and the loop then stops with every later row unrestored. THE DATABASE IS
#: HEALTHY IN THIS STATE, so ``/api/health`` correctly goes on reporting
#: ``durable`` — which is exactly why this label has to exist. It was the mode
#: nothing disclosed: a short list, a health block saying everything is fine, and
#: a by-id read answering ``404`` for a record the database is holding.
HYDRATION_STORE_UNAVAILABLE = "store_unavailable"
HYDRATION_RESTORE_FAILED = "restore_failed"

#: The one sentence each label puts in front of a reader. FIXED LITERALS, for the
#: reason ``experiment_repository``'s two storage messages are: they reach a
#: response body, so they must never acquire a host, a path, a user or a driver
#: message. Neither of them states a NUMBER — how many rows are missing is exactly
#: what an aborted pass does not know, and inventing one would be the guess
#: ``CLAUDE.md`` §5 forbids.
HYDRATION_DISCLOSURE_MESSAGES = {
    HYDRATION_STORE_UNAVAILABLE: (
        "This deployment stores experiments in its own database, and that database "
        "could not be read just now, so this list shows only the working copies "
        "this server already had. Experiments stored durably may be missing from "
        "it. Nothing has been deleted, and this is usually temporary — try again."
    ),
    HYDRATION_RESTORE_FAILED: (
        "This deployment stores experiments in its own database. The database "
        "answered, but this server could not finish restoring its own working "
        "copies, so this list may be missing experiments that are stored durably. "
        "Nothing has been deleted, and this is usually temporary — try again."
    ),
}

#: The sentence for a label this build does not recognise. It exists so that
#: rendering a disclosure can never be the thing that fails: the list path must
#: not raise, and a direct dictionary index on a future label would make it.
HYDRATION_DISCLOSURE_FALLBACK = (
    "This list may be missing experiments: restoring this server's working copies "
    "from the database did not finish. Nothing has been deleted, and this is "
    "usually temporary — try again."
)


@dataclass(frozen=True)
class HydrationOutcome:
    """What one ordinary-scope hydration pass did, and WHETHER IT FINISHED.

    THE SECOND FIELD IS THE POINT. Hydration used to report one number, and a
    ``0`` meant three different things — "there was nothing to restore", "the
    database did not answer", and "the restore stopped part-way". A list built on
    top of that could not tell a complete list from a short one, so it said
    nothing, and a short list is indistinguishable from an empty workspace to the
    person reading it.

    IT IS NOT AN ERROR TYPE AND IT IS NOT RAISED. The list must go on being a
    list (see :func:`_hydrate_ordinary_scope`), so the incompleteness travels as
    a VALUE that the caller decides what to do with: the list discloses it, and a
    single-record read raises on it.
    """

    #: How many directories this call wrote. MEANINGFUL ONLY WHEN ``complete``.
    #: An incomplete pass carries ``0``, which there means "not known to have
    #: written any" rather than "wrote none" — a pass that aborted mid-loop
    #: genuinely does not know its own count, so nothing publishes this field on
    #: that path, and :func:`_hydrate_ordinary_scope_or_raise` raises before it
    #: could be read.
    restored: int = 0

    #: ``None`` when the pass finished; otherwise one of the two labels above.
    reason: str | None = None

    #: The failure that stopped the pass, kept for chaining only. It is NEVER
    #: rendered: a driver exception's message carries the host, the user and the
    #: connection string.
    error: BaseException | None = None

    @property
    def complete(self) -> bool:
        """Did this pass finish? ``True`` also when there was nothing to do."""
        return self.reason is None

    def message(self) -> str:
        """The fixed sentence for this outcome's reason. Never raises."""
        return HYDRATION_DISCLOSURE_MESSAGES.get(
            self.reason or "", HYDRATION_DISCLOSURE_FALLBACK
        )


def _hydrate_ordinary_scope() -> HydrationOutcome:
    """Restore any durably-stored ordinary record whose directory is missing.

    Returns a :class:`HydrationOutcome`: how many directories were written, and
    whether the pass finished. It NEVER RAISES.

    WHY ON EVERY ORDINARY READ rather than once at boot. A pod restart is not the
    only way the workspace and the database diverge — an ``emptyDir`` is per-pod,
    so a second replica starts empty while the first is serving, and a boot-time
    hydration would leave that replica permanently blind to everything created
    before it started. Hydrating on read is one bounded ``SELECT`` on a table this
    application owns, and it writes only what is genuinely absent.

    A FAILED HYDRATION DEGRADES TO THE FILESYSTEM VIEW. It does not raise, and
    this is the single most consequential line in the durable-storage work.
    ``PGHOST`` and ``PGDATABASE`` are already set in the deployed pod and the
    migration is deliberately not applied at boot, so on the next image roll this
    ``SELECT`` hits a table that does not exist. With the exception propagating,
    ``GET /api/experiments`` returned 500 and My Experiments — the product's
    primary screen — rendered "Backend Not Running"; ``GET /api/experiments/<id>``
    turned a clean 404 into a 500. Both are READS that had no database dependency
    at all before this feature, and an optimisation must not be able to take a read
    path down. NARROWING THIS CATCH IS NOT THE FIX and must not be attempted: a
    list that 500s trades a quiet lie for a loud outage, and a scientist with three
    readable records should still see three. The fix is DISCLOSURE, which is what
    the returned ``reason`` is for.

    ``Exception`` and not ``BaseException``: a cancellation or a ``KeyboardInterrupt``
    is not a storage outage and must not be swallowed as one.

    THE FOUR OUTCOMES, AND NONE OF THE CLAUSES IS REDUNDANT.

    * NO DATABASE — every developer machine and every CI job but one. Complete;
      the filesystem is the whole truth.
    * ``StorageNotProvisioned`` — COMPLETE, AND THAT IS THE WHOLE POINT OF THERE
      BEING TWO STORAGE ERRORS. It is not an outage: the relation does not exist,
      so the store holds nothing, so ``0 restored`` is the COMPLETE truth rather
      than the ambiguous "0 or unknown" the rest of this design is written
      against. A caller may then read an absent file as an absent record and
      answer the ``404`` it answered before durable storage existed — which is
      what ``.github/workflows/ci.yml``'s first ``postgres-migration`` step,
      running against a real PostgreSQL with the migration deliberately
      unapplied, requires. It is deliberately NOT a subclass of
      ``StorageUnavailable`` (see its docstring), so the clause order below is not
      what makes it work — it is written most-specific-first anyway, so that a
      later reader who makes it a subclass "for tidiness" does not silently flip
      a 404 into a 503.
    * ``StorageUnavailable`` — INCOMPLETE, ``store_unavailable``. The database did
      not answer; rows may exist that this pass never saw.
    * ANYTHING ELSE — INCOMPLETE, ``restore_failed``. THIS ARM USED TO RETURN A
      BARE 0 AND CALL IT "not an outage", on the reasoning that a row this build
      cannot parse, or a workspace write that failed for SOME OTHER record, says
      nothing about the record a caller is asking about. The premise is true and
      the conclusion was wrong: whatever it says about one record, it says the
      LOOP STOPPED, so every row after the failing one was never restored. The
      old docstring named that "a real remaining hole"; an independent reviewer
      then measured it — a succeeding ``SELECT`` plus one failing working-copy
      write produced an empty list, ``/api/health`` reporting ``durable``, and a
      ``404`` for an untouched durable record. It is a hole no longer: the pass
      says it did not finish, and both callers act on that.
    """
    store = _ordinary_store(None)
    if store is None:
        return HydrationOutcome()
    from .experiment_repository import (  # noqa: PLC0415 - cycle
        StorageNotProvisioned,
        StorageUnavailable,
    )

    try:
        return HydrationOutcome(restored=store.hydrate())
    except StorageNotProvisioned:
        return HydrationOutcome()  # nothing to restore, and that is KNOWN.
    except StorageUnavailable as exc:
        return HydrationOutcome(reason=HYDRATION_STORE_UNAVAILABLE, error=exc)
    except Exception as exc:  # noqa: BLE001 - see the docstring; the LIST must never 500
        return HydrationOutcome(reason=HYDRATION_RESTORE_FAILED, error=exc)


def _hydrate_ordinary_scope_or_raise() -> int:
    """:func:`_hydrate_ordinary_scope`, except that AN INCOMPLETE PASS PROPAGATES.

    Same work, same count; the difference is the one caller that must be able to
    tell "there is no such record" apart from "I could not look".

    RAISES :class:`~isaac_api.experiment_repository.StorageUnavailable` on EITHER
    incomplete outcome, and the two are raised differently on purpose.

    ``store_unavailable`` re-raises the store's OWN exception, so the ``503`` body
    keeps ``STORAGE_READ_FAILED_MESSAGE`` — "that database could not be read".

    ``restore_failed`` raises a NEW ``StorageUnavailable`` carrying
    ``STORAGE_RESTORE_FAILED_MESSAGE``, chained from the original. It must not
    reuse the read message, because in this mode the database WAS read
    successfully and telling an operator otherwise sends them to look at a healthy
    database. This is the same lesson ``experiment_repository`` records for having
    once had a single message for a read and a write: a body that reaches a person
    has to describe what actually happened. AND IT IS NOT RECORDED AS A STORAGE
    FAILURE (:func:`~isaac_api.experiment_repository.storage_failure` is untouched
    on this path), so ``/api/health`` goes on reporting ``durable`` — which is
    true, because the database is fine and a write against it would still succeed.

    WHY ``restore_failed`` IS A ``503`` AND NOT THE ``404`` IT USED TO BE. The
    caller's question is "does this record exist", and after an aborted restore the
    honest answer is that this server does not know: the row may be sitting in a
    database it read but did not finish copying out of. ``404`` asserts it is gone,
    which is the exact false claim about a scientist's work that the single-record
    read path was corrected for once already. The cost of the other direction is a
    retry; the cost of this direction was a person believing their record had been
    destroyed. It does mean a genuinely mistyped id also answers ``503`` while
    hydration is failing — accepted knowingly, and only in a state that is already
    a deployment fault.
    """
    outcome = _hydrate_ordinary_scope()
    if outcome.reason == HYDRATION_STORE_UNAVAILABLE and outcome.error is not None:
        raise outcome.error
    if outcome.reason is not None:
        from .experiment_repository import (  # noqa: PLC0415 - cycle
            STORAGE_RESTORE_FAILED_MESSAGE,
            StorageUnavailable,
        )

        raise StorageUnavailable(STORAGE_RESTORE_FAILED_MESSAGE) from outcome.error
    return outcome.restored


def list_experiments_with_hydration(
    session_id: str | None = None,
) -> tuple[list[Experiment], HydrationOutcome]:
    """:func:`list_experiments`, and WHETHER THE LIST CAN BE TRUSTED TO BE WHOLE.

    The rows are exactly what :func:`list_experiments` returns. The second value is
    the hydration pass that ran before them, which is the only thing that knows
    whether a row could be missing — the directory scan itself cannot tell an empty
    workspace from a workspace whose restore stopped half way.

    A TUTORIAL SCOPE NEVER HYDRATES, so its outcome is always complete. That is
    not a special case for callers: a session's records are materialised into its
    own directory and never touch the database, so there is nothing that could be
    missing from a session's list.
    """
    hydration = _hydrate_ordinary_scope() if session_id is None else HydrationOutcome()
    out: list[Experiment] = []
    for d in _experiment_dirs(scope_root(session_id)):
        try:
            state = json.loads((d / "experiment.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue  # dir removed by a concurrent reset between listing and read — benign
        out.append(Experiment.from_state(state, session_id=session_id))
    out.sort(key=lambda e: e.created_utc)
    return out, hydration


def list_experiments(session_id: str | None = None) -> list[Experiment]:
    """Every experiment in one scope THIS READ COULD ENUMERATE, ordered by ``created_utc``.

    NEVER seeds — and hydration is not seeding. On a fresh normal scope with no
    database this returns ``[]``, and it stays empty however many times it is read.
    With a database configured it first restores records THIS APPLICATION ALREADY
    CREATED whose directory a pod restart threw away; it never materialises a
    built-in example, which the store refuses outright.

    IT DISCARDS THE COMPLETENESS ANSWER, and every caller of it therefore MUST NOT
    present its result as an inventory. A caller that shows these rows to a person
    should use :func:`list_experiments_with_hydration` and disclose what it gets —
    ``GET /api/experiments`` does. This signature is kept for the derived read
    models (search, statistics, the record projection), which is a real remaining
    gap rather than a decision that they are exempt.
    """
    return list_experiments_with_hydration(session_id)[0]


def load_experiment(experiment_id: str, session_id: str | None = None) -> Experiment | None:
    """One experiment from one scope, or ``None`` when that scope has no such id.

    NEVER seeds. A canonical worked-example id therefore resolves to ``None`` in the
    normal scope, which is what makes a normal-scope request for one a 404 rather
    than a silent cross-scope read.

    ``None`` MEANS "THIS SCOPE HAS NO SUCH RECORD" AND NOTHING ELSE. It is never
    the answer to "the store did not respond": in that case this raises
    :class:`~isaac_api.experiment_repository.StorageUnavailable`, which every route
    already renders as a typed ``503``. Twenty-eight call sites turn ``None`` into
    ``404``, so a ``None`` that meant "I could not check" was twenty-eight false
    claims of non-existence; the narrowing is what makes those call sites correct
    without any of them changing. See the comment inside for what was measured.

    "THE STORE DID NOT RESPOND" IS NOT THE SAME AS "THE STORE DOES NOT EXIST YET".
    On a deployment whose migration has not been applied there is no relation and
    therefore no durable row, so ``None`` is TRUE and this returns it — the
    filesystem is the whole truth there, as it was before durable storage. Only
    the case where rows may exist and could not be read raises. See
    :class:`~isaac_api.experiment_repository.StorageNotProvisioned`.

    AND "COULD NOT BE READ" NOW INCLUDES "WAS READ AND COULD NOT BE RESTORED",
    which is a second mode that used to reach this function as a false ``404``.
    A ``SELECT`` that succeeds while one working-copy WRITE fails leaves the loop
    stopped and every later row unrestored, with the database perfectly healthy.
    The rule is unchanged — ``503`` ONLY WHEN THE STORE MIGHT BE HOLDING THE
    RECORD AND WE COULD NOT FIND OUT — and that mode has always satisfied it; what
    changed is that hydration now says so instead of returning a bare 0. See
    :func:`_hydrate_ordinary_scope_or_raise`.
    """
    state_path = scope_root(session_id) / experiment_id / "experiment.json"
    if not state_path.exists():
        # A MISS IN THE ORDINARY SCOPE IS RETRIED ONCE AFTER HYDRATION, and only
        # then. A record created before a pod restart has a durable row and no
        # directory, so a deep link to it would otherwise 404 until something else
        # happened to list. Hydration cannot invent a record: it writes back only
        # rows this application stored, and never a canonical example id.
        #
        # THE ANSWER IS THE FILE, NEVER THE COUNT, and that distinction is the whole
        # of this branch. `_hydrate_ordinary_scope` returns how many directories THIS
        # CALL wrote across the WHOLE SCOPE — it says nothing about the record being
        # asked for. This used to short-circuit on `... == 0`, so a zero count
        # returned `None` without ever re-checking the file, and the record screen's
        # SEVEN concurrent per-record reads made that routine on the first burst after
        # a pod roll: whichever read hydrated first wrote every missing directory, and
        # each sibling that reached its own hydrate afterwards restored nothing,
        # counted 0, and answered 404 for a record whose `experiment.json` was on disk
        # at that instant. Measured at 6 of 7. The count is also wrong in the other
        # direction — a sibling that restored a DIFFERENT record returns non-zero and
        # says nothing about this one — so it is not consulted at all.
        #
        # A MISS NO LONGER STAYS A 404 WHEN THE DATABASE IS DOWN — DOWN, AND NOT
        # MERELY UNMIGRATED; the difference is drawn a paragraph below and it is
        # the difference CI caught this branch getting wrong. That paragraph
        # used to stand here and said so approvingly: a failed hydrate returned 0,
        # wrote nothing, the re-check failed, and the route answered "not found" —
        # "which is what it answered before durable storage existed". THE SECOND
        # HALF OF THAT SENTENCE IS TRUE AND THE CONCLUSION IS WRONG, and it was
        # measured wrong on the deployed application: moments after a rollout to
        # `v0.0.103`, `/record/01KZNWCXS0WYAGHRQJ37KZFCFD` rendered the definitive
        # panel "This experiment id is not in the workspace — it may not have been
        # created yet" about a record that answered 200 to a direct read seconds
        # later and rendered completely on reload.
        #
        # BEFORE DURABLE STORAGE THAT 404 WAS TRUE. The workspace directory was
        # everything there was, so "no directory" and "no record" were the same
        # fact, and answering from the filesystem alone lost nothing. Durable
        # storage moved the authoritative copy into the database and left the
        # directory as a CACHE of it (`experiment_repository`'s module docstring),
        # and from that moment "no directory" stopped implying "no record" — a pod
        # roll empties an `emptyDir` workspace while every row is still there. So
        # the unchanged answer is not continuity; it is the same code saying
        # something that used to be true and no longer is.
        #
        # THE HONEST ANSWER WHEN THE STORE CANNOT BE READ IS 503, NOT 404. "We
        # could not check" and "it is not here" do NOT look the same to a client —
        # that is the argument this branch used to make, and it is an argument
        # about the SERVER's convenience. To the reader they are opposite claims:
        # one says come back, the other says your work is gone. 503 is also the
        # true one, and the deployment already renders it as a typed, path-free
        # `experiment_storage_unavailable` (`routes.storage_unavailable_handler`)
        # that says try again — which is correct, because the next read opens a
        # fresh connection and recovers by itself, exactly as the reload did.
        #
        # A GENUINE MISS IS STILL A 404, and nothing below softens it: the raise
        # happens only when the store was asked and did not answer. With no
        # database configured — every developer machine, every CI job but one —
        # `_hydrate_ordinary_scope_or_raise` returns 0 without raising and this is
        # the code it always was. A healthy database that simply has no such row
        # likewise returns normally, and the absent file is the answer.
        #
        # AND "DID NOT ANSWER" IS NARROWER THAN "FAILED", WHICH IS THE CORRECTION
        # CI FORCED. An earlier version of this branch raised on ANY hydration
        # failure, including the one where the relation does not exist because the
        # migration has not been applied. That case is not an unknown: no durable
        # row CAN exist, the workspace filesystem is the whole truth exactly as it
        # was before durable storage, and the miss is TRUE. `.github/workflows/
        # ci.yml`'s first `postgres-migration` step proves that state against a
        # real PostgreSQL: assertion 1 is that the list still degrades to the
        # filesystem VIEW, assertion 2 that a miss is a clean 404, assertion 3
        # that a known id still loads from disk. This branch broke assertion 2, by
        # treating "there is no table" as "I could not look" — and assertions 1
        # and 3 kept passing, which is what made it a design flaw rather than a
        # crash. `experiment_repository` now tells them
        # apart at the driver error (SQLSTATE 42P01) and `StorageNotProvisioned`
        # arrives here as a plain "restored 0". The rule is not "any storage
        # failure is a 503"; it is 503 ONLY WHEN THE STORE MIGHT BE HOLDING THE
        # RECORD AND WE COULD NOT FIND OUT.
        #
        # THE FILE IS STILL CHECKED BEFORE THE OUTAGE IS REPORTED, and that is the
        # same lesson as the paragraph above rather than a new one: the answer is
        # the FILE, never the count — and never the exception either. A sibling
        # read hydrating on its own connection can restore this record while ours
        # fails, and answering 503 with the record on disk would be its own false
        # claim.
        if session_id is not None:
            return None
        #
        # `Exception` AND NOT THE ONE CLASS: today only `StorageUnavailable`
        # escapes `_hydrate_ordinary_scope_or_raise`, so naming it would read
        # better and behave identically. `Exception` is used because nothing is
        # swallowed here — every arm either re-raises or falls through to a file
        # that exists — so the broad catch cannot hide anything, while the narrow
        # one would let a future exception escaping hydration go back to producing
        # a false 404, which is the defect this branch exists to stop.
        try:
            _hydrate_ordinary_scope_or_raise()
        except Exception:
            if not state_path.exists():
                raise
            # A sibling restored it while ours failed. Fall through and read it.
        else:
            # Hydration COMPLETED. An absent file now means an absent record, and
            # that is the honest 404 this branch must go on producing.
            if not state_path.exists():
                return None
    return Experiment.from_state(
        json.loads(state_path.read_text(encoding="utf-8")), session_id=session_id
    )


# --- tutorial session lifecycle ------------------------------------------------
#
# The filesystem is the registry. Three operations, all idempotent:
# create (mint + seed), dispose (remove), sweep (remove what has expired).


#: Serialises the APPEARANCE of a session directory against the sweep that judges
#: it. Without it there is a real race, not a theoretical one: ``create`` makes the
#: directory and then writes the marker, and a sweep landing between those two steps
#: sees an unmarked directory, correctly applies its fail-closed rule, and deletes a
#: session that is being created — mid-seed. Since the sweep runs at create time,
#: two concurrent creates hit this window routinely.
#:
#: Held only around the two steps that make a session OBSERVABLE (mkdir + marker),
#: never around seeding, which is the slow part; and held for the whole of a sweep
#: pass. Deadlock-free with ``record_lock`` and ``_reset_lock``: it is released
#: before any of them is taken, so it is never held at the same time as another.
#:
#: In-process only, which matches the deployment (single-process uvicorn, no
#: ``--workers``) and matches every other lock in this module. It is NOT a registry:
#: the filesystem is still the registry, so nothing is lost on a restart.
_tutorial_registry_lock = threading.Lock()


def _session_marker_path(session_id: str) -> Path:
    return scope_root(session_id) / TUTORIAL_MARKER


def _parse_marker_utc(raw: object) -> datetime | None:
    """Parse a marker timestamp into an aware UTC datetime, or ``None``.

    Tolerant of the trailing ``Z`` that :func:`_now_iso` writes and of an explicit
    offset; anything else (missing, wrong type, unparseable, naive) is ``None``,
    which the sweep treats as STALE. Fail-closed: an unreadable age is not "young".
    """
    if not isinstance(raw, str) or not raw:
        return None
    text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _session_created_utc(session_dir: Path) -> datetime | None:
    """When this session was created, per its own marker, or ``None`` if unknowable."""
    try:
        marker = json.loads((session_dir / TUTORIAL_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # absent, unreadable, or not JSON
        return None
    if not isinstance(marker, dict):
        return None
    return _parse_marker_utc(marker.get("created_utc"))


def create_tutorial_session() -> tuple[str, list[str]]:
    """Mint an isolated tutorial session and materialise the five worked examples.

    Returns ``(session_id, record_ids)``. ``record_ids`` is MEASURED by listing the
    session afterwards, not asserted from ``CANONICAL_IDS`` — the caller is told what
    is actually there.

    The id comes from ``secrets.token_urlsafe(16)``: server-generated, unguessable,
    and by construction of the shape ``_SESSION_ID_RE`` accepts. It is not a
    credential — it scopes a directory of committed synthetic examples and confers no
    authority — and the deployment's own authentication is unaffected by it.
    """
    session_id = secrets.token_urlsafe(16)
    root = scope_root(session_id)
    # The directory and its marker appear together as far as any sweep can tell (see
    # ``_tutorial_registry_lock``). The marker is written BEFORE the seeds: if the
    # process dies mid-seed, the session has an age and the sweep retires it on
    # schedule, whereas a seed-first order would leave an unmarked — hence
    # immediately stale — session holding records.
    with _tutorial_registry_lock:
        root.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            _session_marker_path(session_id),
            json.dumps(
                {"created_utc": _now_iso(), "ttl_hours": TUTORIAL_TTL_HOURS}, indent=2
            )
            + "\n",
        )
    ensure_tutorial_seeded(session_id)
    return session_id, [exp.id for exp in list_experiments(session_id)]


def _remove_tutorial_session_dir(session_id: str) -> None:
    """Delete one tutorial session tree after proving the target is safe.

    Path-safety guard, mirroring ``_remove_experiment_dir``: the target must resolve
    to a DIRECT child of ``tutorial_namespace_root()`` — never the namespace root
    itself, never the workspace root, never a nested or ``..`` escape. The session id
    was already validated by ``scope_root``; this is the second, independent check
    that the RESOLVED path is where it should be.
    """
    root = scope_root(session_id)  # validates
    if not root.exists():
        return  # already gone: idempotent by contract
    namespace = tutorial_namespace_root().resolve()
    target = root.resolve()
    if target == namespace or target.parent != namespace:
        raise ValueError(
            "refusing to remove a tutorial session that is not a direct child of "
            "the tutorial namespace"
        )
    # Retryable by construction: rmtree removes what it can and raises on what it
    # cannot, so a partial failure leaves the session DIRECTORY present and this
    # function callable again. If the marker was among what it removed, the session
    # is now unmarked, which the sweep reads as stale — the failure mode degrades
    # towards removal, never towards a session that can never be cleared.
    try:
        shutil.rmtree(target)
    except FileNotFoundError:  # lost the race to a concurrent dispose — benign
        pass


def dispose_tutorial_session(session_id: str) -> None:
    """Remove one tutorial session and everything in it.

    IDEMPOTENT: disposing a session that does not exist is a success, because the
    postcondition ("this session does not exist") already holds. Raises
    :class:`InvalidTutorialSession` for a malformed id — that is not an absent
    session, it is a request that never named one.
    """
    _remove_tutorial_session_dir(session_id)


def sweep_stale_tutorial_sessions(ttl_hours: float = TUTORIAL_TTL_HOURS) -> int:
    """Remove expired tutorial sessions; return HOW MANY were removed (measured).

    A session is stale when its marker says it was created more than ``ttl_hours``
    ago, OR when its age cannot be established at all (marker missing, unreadable,
    not JSON, or carrying an unparseable timestamp). The second arm is FAIL-CLOSED
    on purpose: an unmarked session directory is treated as expired rather than kept
    forever on the strength of a fact nobody can read.

    Bounded: one non-recursive pass over the children of ``_tutorial``, no retries,
    no unbounded work per child. Idempotent: a second call removes nothing further.

    It CANNOT touch the normal scope. It only ever iterates
    ``tutorial_namespace_root()``, and it only removes a child whose name is a
    well-formed session id — a directory this application did not create is left
    alone rather than deleted on a guess. A removal that fails is skipped (and stays
    a candidate for the next sweep) rather than aborting the pass.
    """
    namespace = tutorial_namespace_root()
    if not namespace.is_dir():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    removed = 0
    # Held for the WHOLE pass, so a session being created cannot be observed
    # half-made (directory present, marker not yet written) and deleted for it.
    with _tutorial_registry_lock:
        try:
            children = sorted(namespace.iterdir())
        except OSError:  # pragma: no cover - namespace vanished mid-sweep; benign
            return 0
        for child in children:
            if not child.is_dir() or not is_tutorial_session_id(child.name):
                continue
            created = _session_created_utc(child)
            if created is not None and created > cutoff:
                continue  # demonstrably fresh -> keep
            try:
                dispose_tutorial_session(child.name)
            except (OSError, ValueError):  # pragma: no cover - the next sweep retries
                continue
            removed += 1
    return removed


# --- guarded synthetic-demo reset (P26.0b) ------------------------------------
#
# Restores the workspace to EXACTLY the five canonical P26.0a scenarios. It never
# accepts caller ids/paths, removes ONLY records proven to belong to the managed
# synthetic-demo dataset, refuses on ANY ambiguous record, and reuses the existing
# deterministic seed (never fabricates a record). The truth core is never bypassed.

CANONICAL = "canonical"
MANAGED_LEGACY = "managed_legacy"
AMBIGUOUS = "ambiguous"

#: Ordered workflow-state keys reported in the reset result's ``state_counts``.
_STATE_KEYS = (NEEDS_ATTENTION, READY_TO_EXPORT, IN_REVIEW, DONE)


def classify_experiment(exp: Experiment) -> str:
    """Classify an experiment for the guarded reset.

    * ``canonical``      — id is one of the five fixed seed ids.
    * ``managed_legacy`` — NOT canonical, but carries the committed synthetic-demo
      provenance marker: ``source.description == MANAGED_SOURCE_DESCRIPTION``
      (the exact string stamped by both the canonical seed and the demo-run path).
    * ``ambiguous``      — NOT canonical and no managed-demo marker; never removed.

    Provenance is proven ONLY by the exact description marker. Matching filenames
    in ``source.files`` are deliberately NOT sufficient: an unrelated record that
    merely references the two fixture names must classify ``ambiguous`` (and thus
    force a refusal) rather than be auto-deleted. Do not weaken this to a filename
    heuristic — filename overlap is not proof of managed-demo ownership.
    """
    if exp.id in CANONICAL_IDS:
        return CANONICAL
    source = exp.source or {}
    has_marker = source.get("description") == MANAGED_SOURCE_DESCRIPTION
    return MANAGED_LEGACY if has_marker else AMBIGUOUS


def _load_all_experiments(session_id: str | None = None) -> list[Experiment]:
    """Load every persisted experiment in one scope, in listing order.

    Kept distinct from ``list_experiments`` (which sorts by ``created_utc``) so the
    reset classifies the scope exactly as the filesystem presents it. Neither one
    seeds any more, so this no longer differs from ``list_experiments`` in that
    respect — it did when reads auto-seeded, and the distinction mattered then for
    keeping classification honest about a MISSING canonical record. Retained because
    the reset's ordering contract is its own.
    """
    out: list[Experiment] = []
    for d in _experiment_dirs(scope_root(session_id)):
        try:
            state = json.loads((d / "experiment.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue  # dir removed by a concurrent reset between listing and read — benign
        out.append(Experiment.from_state(state, session_id=session_id))
    return out


def _remove_experiment_dir(exp_dir: Path, *, session_id: str | None = None) -> None:
    """Delete a single experiment directory after proving it is safe.

    Path-safety guard: the target must resolve to a DIRECT child of that SCOPE's
    root — ``scope_root(session_id)``, never the root itself, never a nested or
    ``..`` escape, and never a directory belonging to a different scope. Anything
    else raises rather than deleting.
    """
    root = scope_root(session_id).resolve()
    target = exp_dir.resolve()
    if target == root or target.parent != root:
        raise ValueError(
            f"refusing to remove {target} — not a direct child of the scope root"
        )
    # Tolerate an already-removed dir: two concurrent resets (e.g. two browser
    # tabs) can each snapshot the same managed-legacy dir, and losing the race to
    # delete it is benign — the dir being gone IS the desired end state. Only this
    # specific benign case is swallowed; the path-safety guard above still runs
    # first, and any other error still propagates.
    try:
        shutil.rmtree(target)
    except FileNotFoundError:
        pass


def remove_experiment(exp: Experiment) -> None:
    """Remove ONE experiment — only if it classifies as managed_legacy.

    Double guard: it refuses to delete anything that is not managed_legacy
    (canonical/ambiguous raise) and defers the filesystem delete to
    ``_remove_experiment_dir``, which enforces the direct-child path check — against
    the record's OWN scope root, taken from the record itself, so a record can only
    ever be deleted from the scope it was loaded out of.
    """
    if classify_experiment(exp) != MANAGED_LEGACY:
        raise ValueError(
            f"refusing to remove non-managed-legacy experiment {exp.id!r}"
        )
    _remove_experiment_dir(exp.dir, session_id=exp.session_id)


def _canonical_state_counts(session_id: str | None = None) -> dict:
    """Workflow-state distribution over the canonical experiments present IN ONE SCOPE.

    Reports the projected/actual post-reset distribution (canonical set only);
    legacy/ambiguous records are excluded on purpose.
    """
    counts = {key: 0 for key in _STATE_KEYS}
    for exp in _load_all_experiments(session_id):
        if exp.id in CANONICAL_IDS:
            counts[exp.status()] = counts.get(exp.status(), 0) + 1
    return counts


# --- R1: the reset plan digest -------------------------------------------------
#
# The reset used to accept ``{mode, confirmation}`` and nothing else. A client that
# previewed, showed the operator a dialog, and executed thirty seconds later
# destroyed anything committed in between — the operator had approved a
# CLASSIFICATION that no longer held, and the response then stated an outcome
# derived from that stale classification. ``plan_digest`` closes that: ``preview``
# returns an opaque digest of the classified workspace, and ``execute`` must present
# it back. A missing digest and a stale digest are refused SEPARATELY (the route maps
# them to 428 / 412, mirroring the ``If-Match`` convention).
#
# THIS PARAGRAPH USED TO END "and neither mutates". C2 made that false for one case
# and the sentence is corrected rather than deleted: a MISSING digest still mutates
# nothing, and so does a stale digest caught by the workspace-wide check below. But
# the digest is ALSO re-checked per record inside that record's own lock, and an abort
# there refuses after restoring the records the loop had already reached. See
# ``_reset_lock`` for why that trade is the right one.

#: Serialises the whole classify -> verify-digest -> mutate -> measure sequence, so
#: two concurrent resets cannot interleave and a digest verified here cannot be
#: invalidated by ANOTHER reset before the mutation runs.
#:
#: Deadlock-free with ``record_lock``: this lock is only ever acquired FIRST and the
#: reset then takes at most ONE ``record_lock`` at a time (see the loops below).
#: Nothing else in the codebase acquires this lock, and no ``record_lock`` holder
#: ever waits for it, so the classic two-lock cycle cannot form.
#:
#: WHAT IT DOES NOT COVER, stated plainly: a per-record writer (``/answers``,
#: ``/edit``, ``/export``) does NOT take this lock. It deliberately never will —
#: putting a workspace-wide lock on the hot mutation path would invert the ordering
#: documented above (a ``record_lock`` holder would then wait for this lock, which is
#: exactly the two-lock cycle the paragraph above rules out).
#:
#: So a write CAN still land in the window between the workspace-wide digest check
#: and the per-id mutation. That window used to be an unguarded hole: the write
#: returned 200 and was then destroyed, and the response's ``at_risk`` summary —
#: computed from the pre-write snapshot — under-reported by exactly what it had
#: destroyed. **C2 closes it by making the precondition PER-RECORD as well**: inside
#: each id's own ``record_lock``, and before that id is touched, the reset re-reads
#: that one record and rebuilds its digest row (:func:`_plan_digest_row`). A row that
#: no longer matches the one classified at the top of this function means a write
#: landed in the window, so the reset ABORTS that id unmutated and refuses with the
#: existing ``plan_digest_stale`` reason. The write therefore either SURVIVES or the
#: reset REFUSES — never neither. ``record_lock`` still keeps the filesystem
#: consistent; the row re-check is what keeps the outcome honest.
#:
#: **WHAT COUNTS AS "A WRITE" HERE, stated because the first version got it wrong.**
#: The row was built entirely from ``experiment.json``, so it covered every write
#: that changes a record's STATE and nothing else. That is not the same set: the
#: export self-heal (``routes._write_record`` on an already-exported record whose
#: artifact file is missing) durably republishes the record and its sidecar and then
#: ``save_versioned()`` returns False, because ``record_id`` did not move. A 200 that
#: repaired the filesystem moved no row component at all and was destroyed in
#: silence. The row now also carries whether each half of the artifact pair is on
#: disk (:func:`_plan_digest_row`), which closes it: ``_write_record`` is the only
#: filesystem write in ``routes.py`` outside ``Experiment.save``, and every reachable
#: path through it either flips a presence flag or bumps the state. Keep that
#: property in mind before adding another filesystem write to a record's directory —
#: a write the row cannot see is a write this paragraph's promise does not cover.
#:
#: **THE FAN-OUT SLICE ADDED TWO MORE WRITES AND KEPT THE PROPERTY, deliberately.**
#: (1) ``_write_record`` now writes ONE UNIT's pair, and a fan-out experiment has N
#: of them named by ``Run.record_id`` — covered by the per-run presence flags in
#: :func:`_plan_digest_row`. (2) ``routes._prune_orphan_artifacts`` DELETES artifact
#: pairs left behind when the run set changes. A prune of a CURRENT unit's pair is
#: impossible by construction (the keep-set is exactly the current targets), and a
#: prune of anything else is invisible to the row — but it can only run on the
#: success path of an export that also moved at least one ``Run.record_id``, because
#: an export with nothing to write returns 409 before reaching it. So the row still
#: moves whenever the filesystem does.
_reset_lock = threading.Lock()


def _seed_baseline(spec: "_SeedSpec") -> "Experiment":
    """The canonical seed baseline for one spec, built IN MEMORY only — never saved.

    Used to answer "has this example been worked on?" by comparing authoritative
    signatures. ``record_id`` matters and is easy to get wrong: an ``exported`` spec
    is materialised through a real export keyed to its own id, so disk carries
    ``record_id == spec.id`` while a freshly-constructed ``Experiment`` carries
    ``None`` — and ``record_id`` is inside ``_authoritative_signature``.

    NOTE (duplication, deliberate and NOT fixed in this slice): ``routes._demo_baseline``
    builds the same object for the demo-run drift check. Converging them means editing
    a part of ``routes.py`` this slice does not own, so the two are kept identical by
    hand for now — both derive from ``_seed_specs`` / ``_seed_source``, which remain the
    single definition of the seed's CONTENT, so a drift between them could only be in
    this wrapper. Fold them together in a later slice.
    """
    return Experiment(
        id=spec.id,
        title=spec.title,
        created_utc=spec.created_utc,
        source=_seed_source(),
        draft=spec.draft_fn(),
        record_id=spec.id if spec.exported else None,
    )


def _classify_workspace(experiments: list["Experiment"]) -> dict[str, list["Experiment"]]:
    """Split the workspace into the three reset buckets, in listing order."""
    buckets: dict[str, list[Experiment]] = {
        CANONICAL: [],
        MANAGED_LEGACY: [],
        AMBIGUOUS: [],
    }
    for exp in experiments:
        buckets[classify_experiment(exp)].append(exp)
    return buckets


def _plan_digest_row(exp: "Experiment", bucket: str) -> list:
    """ONE record's row in the reset plan — the unit :func:`_plan_digest` hashes.

    Extracted so the per-record precondition in :func:`reset_to_canonical_seed` can
    re-derive exactly the same row for one id, rather than re-implementing the rule
    beside it and drifting from it. Anything that would change this row changes the
    digest, and vice versa, BY CONSTRUCTION — there is only one definition.

    See :func:`_plan_digest` for what each element is and why it is included.

    **The last two elements are not derived from ``experiment.json``**, and that is
    deliberate. Every other element is, and while that was the whole row an
    acknowledged write could move nothing in it: ``routes._write_record`` on the
    export SELF-HEAL path (state says exported, an artifact file is missing) durably
    rewrites the record and its sidecar and then ``save_versioned()`` returns False,
    because ``record_id`` never changed. A 200 that repaired the filesystem was
    therefore invisible here, and the reset destroyed it. Two ``exists()`` calls make
    the row cover what any reader would call this record's state.

    PRESENCE, not content, and that is sufficient rather than lazy: every reachable
    path through ``_write_record`` either flips one of these flags or moves the state.
    With BOTH files present and the state exported, the immutability guard answers 409
    and never reaches the write; with both present and the state NOT exported, the
    reconciliation republishes and ``save_versioned`` bumps ``rev``. Hashing the file
    contents would cost a full read of every artifact on every preview to detect
    nothing that presence does not already detect.

    **THE LAST ELEMENT EXISTS BECAUSE FAN-OUT REOPENED THE HOLE THE TWO ABOVE CLOSED,
    ONE GRANULARITY DOWN, and the gap was real rather than theoretical.** The two
    ``exists()`` calls above stat ``exp.record_path()`` / ``exp.sidecar_path()`` —
    SINGULAR, the experiment's OWN pair, derived from ``Experiment.record_id``. Under
    contract §1 D1 an experiment with runs has N pairs, named by ``Run.record_id``,
    and ``Experiment.record_id`` is ``None`` for such an experiment, so BOTH flags
    above are permanently ``False`` and describe nothing.

    Trace the destructive path exactly, because it is the same one the export
    self-heal took: a run is exported (``run.record_id`` moves ``None`` -> an id,
    which IS inside ``_run_signature_payload`` and therefore inside the authoritative
    signature, so a FRESH fan-out export is already covered). Later that run's record
    file goes missing and a re-export republishes it. ``run.record_id`` is ALREADY
    set, so the signature does not move, ``save_versioned`` returns ``False``, the
    version token does not move, and — before this element — no row component moved
    at all. A 200 that durably repaired an acknowledged run export was invisible to
    the digest, and a reset would have destroyed it in silence: precisely the defect
    the two ``exists()`` calls were added to close, reintroduced by a slice that could
    not see them.

    So the row also carries ``[run_id, record_present, sidecar_present]`` for every
    run, in :meth:`sorted_runs` order. For a zero-run experiment this is ``[]`` and
    the row is the old row plus an empty list — the digest value changes (it is
    opaque and lives only between one preview and its execute), the meaning does not.

    Keep the property that made this fixable: this is the ONE definition, shared by
    :func:`_plan_digest` and by the per-record re-check in
    :func:`reset_to_canonical_seed`. Do not re-derive a row beside either of them.
    """
    record_path = exp.record_path()
    sidecar_path = exp.sidecar_path()
    return [
        exp.id,
        bucket,
        exp.version_token(),
        len(exp.answer_log or []),
        _authoritative_signature(exp),
        record_path is not None and record_path.exists(),
        sidecar_path is not None and sidecar_path.exists(),
        [_run_artifact_presence(exp, run) for run in exp.sorted_runs()],
    ]


#: The row for a record whose state file is PRESENT but cannot be turned into one.
#:
#: A distinct third answer, and it has to be distinct from BOTH of the other two.
#: ``None`` is already taken and means ABSENT — and absent-then / absent-now compares
#: EQUAL, which is what lets the reset heal a canonical gap
#: (see ``_current_plan_row``). Answering ``None`` for an unreadable record would
#: therefore silently re-create it from the seed instead of refusing. A real row
#: always starts with an experiment id, so this sentinel can never collide with one.
_UNREADABLE_ROW: list = ["\x00unreadable"]


def _current_plan_row(experiment_id: str, session_id: str | None) -> list | None:
    """Re-read ONE record from disk NOW and rebuild its plan row (``None`` if absent).

    Deliberately reads and rehydrates by exactly the same two steps
    ``_load_all_experiments`` uses (``read_text`` -> ``Experiment.from_state``) and
    then hands the result to the one shared :func:`_plan_digest_row`, so a record
    nobody touched produces a row byte-identical to the one classified earlier and
    the comparison can never refuse spuriously. That the row also stats the artifact
    pair is therefore automatic here, and is the point: this is the single definition
    of what "unchanged" means. Absence is a real answer,
    not an error: a record removed in the window has no row, which differs from the
    row it had when it was classified — which is the point.

    Callers hold that id's ``record_lock``; the ``FileNotFoundError`` guard mirrors
    ``_load_all_experiments``'s and exists for the same benign reason.

    **It must not RAISE, and that is a safety property rather than tidiness.** This
    runs inside the mutation loop with ``_reset_lock`` and a ``record_lock`` held. The
    locks are context managers, so an exception here deadlocks nothing — but it leaves
    the reset PART-APPLIED and answers the caller with a 500 carrying no refusal
    reason and none of the measured counts a partial abort is supposed to disclose.
    The question this function is asked is "can I prove this record is unchanged?",
    and a read that cannot be parsed is a no. So anything that is present-but-unusable
    — a torn write, a bad encoding, a state dict this build cannot rehydrate —
    answers ``_UNREADABLE_ROW``, which compares unequal to every real row and the
    reset refuses. Fail-closed: it can cost a spurious refusal (recoverable in one
    further request), never a destroyed write.
    """
    state_path = scope_root(session_id) / experiment_id / "experiment.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        # ValueError covers JSONDecodeError and UnicodeDecodeError; OSError covers a
        # read that failed for any other reason (FileNotFoundError, an OSError
        # subclass, is caught above and keeps its own meaning).
        return _UNREADABLE_ROW
    try:
        exp = Experiment.from_state(state, session_id=session_id)
        return _plan_digest_row(exp, classify_experiment(exp))
    except (KeyError, TypeError, ValueError, AttributeError):
        # Rehydration failures for a state file this build cannot read. Deliberately
        # an explicit tuple rather than a bare ``except``: a fault of some OTHER kind
        # is a defect in this module and should still be loud, not swallowed into a
        # refusal that looks like an ordinary concurrent write.
        return _UNREADABLE_ROW


def _plan_digest(buckets: dict[str, list["Experiment"]]) -> str:
    """A deterministic, opaque digest of the CLASSIFIED workspace.

    One row per record present: its id, the bucket it classified into, its public
    version token (``<generation>.<rev>``), how many entries its answer log holds,
    its authoritative signature, and whether each half of its exported artifact pair
    is on disk. Any edit, answer, confirmation, export, creation, removal or artifact
    repair anywhere in the workspace changes at least one row, so it changes the
    digest:

    * an answer / edit / export bumps ``rev`` -> the version token changes;
    * a creation adds a row; a removal drops one;
    * a delete-then-recreate of the same id mints a fresh ``generation``, so the
      digest differs even though ``rev`` returned to 0 (the ABA the generation nonce
      exists to defeat);
    * a record whose provenance marker changed moves bucket;
    * an export self-heal republishes a missing artifact WITHOUT touching the state
      (``save_versioned`` returns False when ``record_id`` is unchanged), so a
      presence flag is the only thing that moves — and it does move. That holds for
      the experiment's own pair AND, since the fan-out slice, for each RUN's pair:
      see the last element of :func:`_plan_digest_row`, which exists because the
      first two flags describe only ``Experiment.record_id``, and a fan-out
      experiment does not have one.

    The signature and the answer-log length are included because the preview reports
    numbers DERIVED from them (``at_risk``), and a digest that did not cover them
    could stay valid while the disclosed numbers went stale. In normal operation they
    are redundant with ``rev`` — a content change always bumps it — but a state file
    written outside ``save_versioned`` would not, and the digest must still notice.

    Path-free and content-free by construction: ids and buckets are opaque
    identifiers, and everything else is a hash or a count. The whole row set is
    reduced to one sha256, so nothing is recoverable from the digest itself.
    """
    rows = sorted(
        _plan_digest_row(exp, bucket)
        for bucket, exps in buckets.items()
        for exp in exps
    )
    blob = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return "rp1." + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _at_risk_summary(
    canonical: list["Experiment"], legacy: list["Experiment"]
) -> dict[str, int]:
    """What confirmed work this reset would actually discard — DERIVED, never guessed.

    Three counts, each from real persisted state, over exactly the records the reset
    touches (canonical is re-materialised, managed-legacy is removed; an ambiguous
    record is never touched and so is never counted):

    * ``confirmed_answers`` — total entries in ``answer_log``. One entry is appended
      per submission that actually changed the authoritative draft; a no-op
      re-entry is popped again (``routes.submit_answers``), so this counts real
      confirmations, not clicks.
    * ``examples_with_progress`` — built-in examples whose authoritative signature
      (``{title, source, draft, record_id}``) differs from the in-memory seed
      baseline. That is the SAME comparison ``POST /api/demo/run`` uses to refuse
      over a changed record, so the two surfaces cannot disagree about what "worked
      on" means.
    * ``exported_artifacts`` — exports that are NOT part of the baseline. The
      built-in exported example is excluded by construction: its spec carries
      ``exported=True``, so its ``record_id`` is baseline state rather than operator
      progress. Counting it would tell the operator they are about to lose an export
      they never made.
    """
    specs = {s.id: s for s in _seed_specs()}
    confirmed_answers = 0
    examples_with_progress = 0
    exported_artifacts = 0

    for exp in canonical:
        confirmed_answers += len(exp.answer_log or [])
        spec = specs.get(exp.id)
        if spec is None:  # pragma: no cover - CANONICAL_IDS is derived from _seed_specs
            continue
        if _authoritative_signature(exp) != _authoritative_signature(_seed_baseline(spec)):
            examples_with_progress += 1
        if exp.record_id is not None and not spec.exported:
            exported_artifacts += 1

    for exp in legacy:
        confirmed_answers += len(exp.answer_log or [])
        if exp.record_id is not None:
            exported_artifacts += 1

    return {
        "confirmed_answers": confirmed_answers,
        "examples_with_progress": examples_with_progress,
        "exported_artifacts": exported_artifacts,
    }


def reset_to_canonical_seed(
    *, dry_run: bool, expected_plan_digest: str | None = None, session_id: str
) -> dict:
    """Classify ONE TUTORIAL SESSION and (unless ``dry_run``) restore the canonical seed.

    Refuses, MAKING NO CHANGES, if ANY ambiguous record exists, and — when
    ``expected_plan_digest`` is supplied — if it does not match the digest of the
    session as classified here.

    It ALSO refuses, and this one is the exception to "no changes", if any single
    record changes between that classification and the moment this reset is about to
    touch it: the ids already reached are already reset. That is the per-record
    precondition described below; it is the only refusal that mutates anything, and
    the counts it reports are measured rather than assumed.

    Otherwise, on execute, removes ONLY the
    managed_legacy directories via ``remove_experiment`` (path-safe, each under that
    record's own ``record_lock``), then re-materialises EVERY canonical scenario to
    its deterministic seed baseline — a present-but-drifted canonical record (partial
    answers, stale evidence, a wrongly-exported artifact) is removed and rebuilt from
    the seed, not merely left in place. This restores CONTENT, not just the id set,
    and mints a fresh generation per id (invalidating every pre-reset ETag).
    Idempotent in content. Returns typed, path-free data (no filesystem paths).

    ``session_id`` is REQUIRED and has no default, and ``None`` is REFUSED at runtime,
    for the same reason ``_materialise_seed``'s is: this operation re-materialises the
    canonical seed, and a normal-scope form of it would be a normal-scope auto-seed by
    another name. The refusal is not decoration — before it, an explicit
    ``reset_to_canonical_seed(dry_run=False, session_id=None)`` was measured
    materialising all five canonical records into ``workspace_root()`` and reporting
    ``final_count: 5``. Requiring the id also means preview and execute cannot disagree
    about which scope they describe — the projection below depends on that.

    ``expected_plan_digest`` defaults to ``None`` = no precondition, which is what the
    direct in-process callers (tests, the concurrency suites) use. The HTTP route
    ALWAYS supplies it for an execute: the precondition is part of the API contract,
    not of this function's contract.

    **The precondition is checked TWICE, and the second check is the point (C2).**
    Once here, over the whole classification; and then again PER RECORD, inside each
    id's own ``record_lock`` and before that id is touched, by rebuilding that one
    record's row (:func:`_current_plan_row`) and comparing it to the row classified
    above. Without the second check the span from the snapshot to the per-id mutation
    was open to a writer — ``/answers``, ``/edit`` and ``/export`` take ``record_lock``
    but not ``_reset_lock`` — so a write could return 200 and then be destroyed by a
    reset reporting success. It now cannot: the write either lands before that id's
    check (and the reset aborts) or it cannot land at all (the lock is held).

    That holds for a write to the record's STATE and for one that only repairs its
    exported ARTIFACT PAIR, which are not the same set and were not both covered at
    first — see ``_reset_lock`` and :func:`_plan_digest_row`.

    **So a refusal is NOT always "made no changes".** A workspace-wide refusal, and
    every refusal that existed before C2, still mutates nothing. A per-record abort
    part-way through leaves the ids BEFORE the aborted one already reset — which is
    why ``final_count``/``plan_digest``/``at_risk`` are measured from disk in that case
    rather than echoed from the snapshot, and why it still reports ``refused``. A
    partial reset is the honest price of never destroying an acknowledged write; the
    alternative (holding every record's lock at once) would break the one-lock-at-a-time
    rule that makes this deadlock-free.

    ``final_count`` is MEASURED after the mutation, never asserted from
    ``len(CANONICAL_IDS)``. A record created between the classification and the
    mutation is not classified, so it is not removed — it survives, and the reported
    count says so.
    """
    validate_tutorial_session_id(session_id)  # refuses None; refuses a malformed id
    with _reset_lock:
        experiments = _load_all_experiments(session_id)
        buckets = _classify_workspace(experiments)

        previous_count = len(experiments)
        canonical = buckets[CANONICAL]
        legacy = buckets[MANAGED_LEGACY]
        ambiguous = buckets[AMBIGUOUS]
        # The per-id rows the digest below is reduced from, kept so each id can be
        # re-checked against its own row inside its own lock (C2 — see
        # ``_reset_lock``). An id that was ABSENT here simply has no entry, and
        # ``.get`` returning ``None`` is the correct comparison value: "absent then"
        # must match "absent now".
        #
        # THE ORDER OF THESE TWO STATEMENTS IS LOAD-BEARING, and it was the other way
        # round until the row learned to stat the artifact pair. A row is no longer a
        # pure function of the in-memory ``Experiment``: two of its elements are read
        # from the filesystem AT THE MOMENT THE ROW IS BUILT. So the digest and the
        # rows are two separate observations, and whichever is taken SECOND sees a
        # write that landed between them. Built second, ``planned_rows`` picked up the
        # very repair the per-record check exists to notice, matched it, and waved the
        # reset through — which is exactly how the fix for that defect failed its own
        # test. Built FIRST, the residual is fail-closed instead: a write landing
        # between the two makes the DIGEST differ from the token the caller presented,
        # so the workspace-wide precondition refuses before anything is touched.
        planned_rows: dict[str, list] = {
            exp.id: _plan_digest_row(exp, bucket)
            for bucket, exps in buckets.items()
            for exp in exps
        }
        plan_digest = _plan_digest(buckets)
        at_risk = _at_risk_summary(canonical, legacy)

        # Precondition BEFORE the ambiguity verdict: a client holding a stale plan
        # must be told to look again, not handed a classification verdict about a
        # workspace it has never seen.
        refusal: str | None = None
        if expected_plan_digest is not None and expected_plan_digest != plan_digest:
            refusal = "plan_digest_stale"
        elif ambiguous:
            refusal = "ambiguous_records_present"
        refused = refusal is not None

        removed = 0
        #: Has ANY id been removed or re-materialised yet? Only consulted when the
        #: reset aborts part-way (C2): a refusal that already mutated must MEASURE
        #: what it left behind rather than report the pre-reset snapshot.
        mutated = False
        #: Did the refusal come from the PER-RECORD row check (C2) rather than from
        #: the workspace-wide precondition? Tracked separately from ``mutated``
        #: because WHERE the refusal came from — not whether it managed to mutate
        #: anything first — is what decides whether the snapshot may still be
        #: reported. A per-record abort is reached only when a write has ALREADY
        #: landed in the window, so its snapshot is stale BY CONSTRUCTION, even when
        #: it aborted on the very first id and removed nothing.
        row_abort = False
        if not dry_run and not refused:
            # C2 — the PER-RECORD precondition. Armed only when the caller supplied a
            # precondition at all: ``expected_plan_digest is None`` means "no
            # precondition" (the documented contract for the direct in-process
            # callers), and refusing such a call with ``plan_digest_stale`` would
            # invent a precondition it never presented. The HTTP route ALWAYS supplies
            # one for an execute, so the production path is always guarded.
            check_rows = expected_plan_digest is not None

            def _row_changed(experiment_id: str) -> bool:
                """Did this ONE record change since it was classified above?

                Called inside that id's ``record_lock``, so between this answer and
                the mutation that follows it no writer can intervene — which is what
                makes the check a precondition rather than a guess.
                """
                return _current_plan_row(experiment_id, session_id) != planned_rows.get(
                    experiment_id
                )

            # Symmetric locking: BOTH the managed-legacy removal and the canonical
            # re-materialisation hold that record's own ``record_lock``, so a
            # concurrent writer can never race an unlocked directory removal. Taken
            # one at a time and released before the next (never two at once), which
            # is what keeps this deadlock-free — and the row re-check adds no lock, so
            # that argument is unchanged. Every lock key is scope-qualified with
            # this session, so a reset in one session never blocks — and is never
            # blocked by — a mutation in another.
            for exp in legacy:
                with record_lock(exp.id, session_id=session_id):
                    if check_rows and _row_changed(exp.id):
                        refusal = "plan_digest_stale"
                        refused = True
                        row_abort = True
                        break
                    remove_experiment(exp)
                removed += 1
                mutated = True
            # Restore canonical CONTENT to the deterministic seed baseline (not just
            # fill missing). Each canonical id is removed and re-materialised, so
            # drifted content, partial answers, and wrongly-exported artifacts are
            # cleared, and a FRESH generation is minted (invalidating every pre-reset
            # ETag). Targeted to the fixed canonical id set — NOT a broad filesystem
            # wipe.
            for spec in _seed_specs():
                if refused:
                    break
                with record_lock(spec.id, session_id=session_id):
                    if check_rows and _row_changed(spec.id):
                        refusal = "plan_digest_stale"
                        refused = True
                        row_abort = True
                        break
                    target = scope_root(session_id) / spec.id
                    if target.exists():
                        # path-safe (direct-child-of-THIS-scope guard)
                        _remove_experiment_dir(target, session_id=session_id)
                    # baseline content + fresh generation + DONE artifact
                    _materialise_seed(spec, session_id=session_id)
                    mutated = True

        # ``final_count`` — four cases, and the difference between them is the point
        # of D3. Keep them distinct; collapsing any two makes the number dishonest.
        #
        #  * REFUSED WITHOUT MUTATING, by the WORKSPACE-WIDE check (or the ambiguity
        #    verdict): nothing changed, so the classification snapshot IS the truth.
        #    Every pre-C2 refusal was decided before the mutation block, so this
        #    stayed exactly the case it always was.
        #  * REFUSED AFTER MUTATING (C2, a per-record abort part-way through): the
        #    snapshot is NOT the truth any more — ids before the aborted one were
        #    already removed / re-materialised. It falls through to the MEASURED arm
        #    below, so a partial abort reports what it actually left behind. It still
        #    reports ``refused``, so it can never read as success.
        #  * REFUSED WITHOUT MUTATING, by the PER-RECORD check (C2 — an abort on the
        #    very first id the reset would have touched): ``mutated`` is False, and
        #    that is exactly why this case needs naming rather than folding into the
        #    first. A per-record abort is REACHABLE ONLY when a write has already
        #    landed in the window, so the snapshot is known-stale BY CONSTRUCTION —
        #    its count, its digest and its ``at_risk`` all predate that write. Echoing
        #    it here was measured returning the digest the client had just presented
        #    (so the documented "recoverable in one further request" was false, the
        #    retry 412'd again), an ``at_risk`` of zeroes over work that existed, and
        #    a count of 4 with 5 records on disk. ``row_abort`` is therefore what this
        #    branch tests, not ``mutated``: WHERE the refusal came from, not whether
        #    it got as far as changing something.
        #  * PREVIEW that would proceed: nothing has happened yet, so this is
        #    necessarily a PROJECTION — and the projection is exactly the canonical
        #    five, because a non-refused reset removes the legacy set and rebuilds the
        #    canonical set. Since R1 that projection is also GUARANTEED rather than
        #    hoped for: the ``plan_digest`` precondition means the execute cannot run
        #    against a scope that gained a record after this preview.
        #
        #    The projection is scope-correct only because ``session_id`` is REQUIRED.
        #    An unscoped form of this function would project five records into a
        #    normal scope that this operation can no longer seed and that would in
        #    fact end up holding zero — the preview would state a number the execute
        #    could not produce. Preview and execute describe the same scope by
        #    construction, not by convention.
        #  * EXECUTE that proceeded: MEASURED by re-reading the scope. Never
        #    ``len(CANONICAL_IDS)``, which was the D3 defect — a record created between
        #    the classification and the mutation is not classified, so it is not
        #    removed, so it survives, and the response must say so.
        if refused and not mutated and not row_abort:
            final_count = previous_count
            final_digest = plan_digest
            final_at_risk = at_risk
        elif dry_run:
            final_count = len(CANONICAL_IDS)
            final_digest = plan_digest
            final_at_risk = at_risk
        else:
            post = _load_all_experiments(session_id)
            post_buckets = _classify_workspace(post)
            final_count = len(post)
            final_digest = _plan_digest(post_buckets)
            final_at_risk = _at_risk_summary(
                post_buckets[CANONICAL], post_buckets[MANAGED_LEGACY]
            )

        return {
            "refused": refused,
            "refusal": refusal,
            "previous_count": previous_count,
            "canonical_count": len(canonical),
            "legacy_count": len(legacy),
            "ambiguous_count": len(ambiguous),
            "removed_count": removed,
            "final_count": final_count,
            # The canonical ids THIS SCOPE will hold once the reset has run — which is
            # the whole fixed set, because a non-refused reset re-materialises every
            # one of them into this session. It is a statement about this tutorial
            # session, not about the workspace at large: the normal scope holds none of
            # these ids and this operation cannot put them there.
            "canonical_ids": sorted(CANONICAL_IDS),
            "removable": [{"id": e.id, "title": e.title} for e in legacy],
            "state_counts": _canonical_state_counts(session_id),
            "plan_digest": final_digest,
            "at_risk": final_at_risk,
        }
