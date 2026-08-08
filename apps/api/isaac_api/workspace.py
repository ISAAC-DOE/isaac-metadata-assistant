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
because ``isaac_records.ids.RECORD_ID_RE`` (``^[0-9A-Z]{26}$``) can never match a
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
#: with) a record id: ``RECORD_ID_RE`` is ``^[0-9A-Z]{26}$``.
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
#: Matching is done with ``re.fullmatch`` (which anchors both ends itself, and so
#: cannot be defeated by ``$``'s trailing-newline tolerance).
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")


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
    (``^[0-9A-Z]{26}$``) can contain ``/``, so the two halves cannot be confused.
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


def _authoritative_signature(exp: "Experiment") -> str:
    """Deterministic hash of the AUTHORITATIVE scientific state of an experiment.

    Covers exactly ``{title, source, draft, record_id}`` — the fields that define
    the record's scientific content. It EXCLUDES ``answer_log`` (an audit trail,
    not scientific state), ``generation``/``rev``/``updated_utc`` (version metadata,
    not scientific content — excluding ``generation`` keeps a byte-stable no-op from
    churning the token), and ``created_utc`` (immutable identity). Two experiments
    with an identical scientific state therefore hash identically, so a no-op
    re-entry is detectable and never bumps ``rev``.
    """
    payload = {
        "title": exp.title,
        "source": exp.source,
        "draft": exp.draft,
        "record_id": exp.record_id,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


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
        }

    def save(self) -> None:
        """Persist this experiment's state, durably when the deployment has a database.

        THE DURABLE WRITE GOES FIRST, and the order is load-bearing rather than
        arbitrary. If the database write fails, this raises and the workspace file
        is NOT rewritten, so the reader is told their change did not stick instead
        of seeing it applied locally and losing it at the next pod restart. If the
        database write succeeds and the file write then fails, the durable copy is
        ahead of the working copy — which the next ordinary-scope read repairs by
        itself, because hydration writes back any stored record whose directory is
        missing. Only one of the two orderings is self-healing.

        SCOPE IS THE GATE. ``_ordinary_store`` returns ``None`` for any record that
        belongs to a worked-example session, so a session's records never reach the
        database. This is the first of the three guards described in
        ``experiment_repository``; the store itself raises on the same condition,
        so the guard does not depend on this one line being right.
        """
        store = _ordinary_store(self.session_id)
        if store is not None:
            store.persist(self)
        atomic_write_text(self.state_path, json.dumps(self.to_state(), indent=2) + "\n")

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
        """
        old_sig, disk_rev = self._persisted_sig_and_rev()
        new_sig = _authoritative_signature(self)
        if old_sig is not None and old_sig == new_sig:
            return False
        self.rev = max(self.rev, disk_rev) + 1
        self.updated_utc = _now_iso()
        self.save()
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
        )

    # -- derived views --

    def pending(self) -> list[dict]:
        return list(self.draft.get("pending") or [])

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
        return validate_draft(self.draft).ok

    def status(self) -> str:
        """Derive status deterministically; never stored, always recomputed.

        pending > 0            -> needs_attention
        pending == 0, exported -> done
        pending == 0, dry-run export passes -> ready_to_export
        pending == 0, dry-run export fails  -> in_review
        """
        if self.exported():
            return DONE
        if self.pending_count() > 0:
            return NEEDS_ATTENTION
        # Dry-run only: export_draft returns an ExportResult and writes nothing.
        try:
            result = export_draft(self.draft, REPO_ROOT)
        except Exception:  # pragma: no cover - defensive, keeps status non-throwing
            return IN_REVIEW
        return READY_TO_EXPORT if result.ok else IN_REVIEW

    def export_ready(self) -> bool:
        """True iff a dry-run export of the CURRENT draft passes (pending==0 AND
        the export gate succeeds), independent of whether it was already exported.

        Unlike ``status()`` (which short-circuits to DONE for any exported
        record), this reflects the CURRENT draft's export-readiness — so an
        exported record edited back to pending>0 is correctly NOT export-ready.
        Read-only dry-run, exactly as ``status()`` uses ``export_draft``.
        """
        if self.pending_count() > 0:
            return False
        try:
            return export_draft(self.draft, REPO_ROOT).ok
        except Exception:  # pragma: no cover - defensive, keeps the check non-throwing
            return False


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
    ``RECORD_ID_RE`` (``^[0-9A-Z]{26}$``) can never match a ``_``-prefixed name, so
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


def _hydrate_ordinary_scope() -> int:
    """Restore any durably-stored ordinary record whose directory is missing.

    Returns the number of directories written (0 when there is no database).

    WHY ON EVERY ORDINARY READ rather than once at boot. A pod restart is not the
    only way the workspace and the database diverge — an ``emptyDir`` is per-pod,
    so a second replica starts empty while the first is serving, and a boot-time
    hydration would leave that replica permanently blind to everything created
    before it started. Hydrating on read is one bounded ``SELECT`` on a table this
    application owns, and it writes only what is genuinely absent.

    A FAILED HYDRATION DEGRADES TO THE FILESYSTEM VIEW AND RETURNS 0. It does not
    raise, and this is the single most consequential line in the durable-storage
    work. ``PGHOST`` and ``PGDATABASE`` are already set in the deployed pod and the
    migration is deliberately not applied at boot, so on the next image roll this
    ``SELECT`` hits a table that does not exist. With the exception propagating,
    ``GET /api/experiments`` returned 500 and My Experiments — the product's
    primary screen — rendered "Backend Not Running"; ``GET /api/experiments/<id>``
    turned a clean 404 into a 500. Both are READS that had no database dependency
    at all before this feature, and an optimisation must not be able to take a read
    path down.

    Degrading is not silent. ``PostgresOrdinaryStore.hydrate`` records the failure
    before raising, so ``/api/health`` reports ``experiment_storage.state:
    "unavailable"`` and the UI stops claiming durability. WRITES still fail loudly
    (``Experiment.save`` re-raises ``StorageUnavailable``, rendered as a typed
    503) — a read that shows less than everything is a degraded read, while a write
    that quietly lands somewhere temporary is a broken promise.

    ``Exception`` and not ``BaseException``: a cancellation or a ``KeyboardInterrupt``
    is not a storage outage and must not be swallowed as one.
    """
    store = _ordinary_store(None)
    if store is None:
        return 0
    try:
        return store.hydrate()
    except Exception:  # noqa: BLE001 - see the docstring; reads must never 500 on this
        return 0


def list_experiments(session_id: str | None = None) -> list[Experiment]:
    """Every experiment in one scope, ordered by ``created_utc``.

    NEVER seeds — and hydration is not seeding. On a fresh normal scope with no
    database this returns ``[]``, and it stays empty however many times it is read.
    With a database configured it first restores records THIS APPLICATION ALREADY
    CREATED whose directory a pod restart threw away; it never materialises a
    built-in example, which the store refuses outright.
    """
    if session_id is None:
        _hydrate_ordinary_scope()
    out: list[Experiment] = []
    for d in _experiment_dirs(scope_root(session_id)):
        try:
            state = json.loads((d / "experiment.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue  # dir removed by a concurrent reset between listing and read — benign
        out.append(Experiment.from_state(state, session_id=session_id))
    out.sort(key=lambda e: e.created_utc)
    return out


def load_experiment(experiment_id: str, session_id: str | None = None) -> Experiment | None:
    """One experiment from one scope, or ``None`` when that scope has no such id.

    NEVER seeds. A canonical worked-example id therefore resolves to ``None`` in the
    normal scope, which is what makes a normal-scope request for one a 404 rather
    than a silent cross-scope read.
    """
    state_path = scope_root(session_id) / experiment_id / "experiment.json"
    if not state_path.exists():
        # A MISS IN THE ORDINARY SCOPE IS RETRIED ONCE AFTER HYDRATION, and only
        # then. A record created before a pod restart has a durable row and no
        # directory, so a deep link to it would otherwise 404 until something else
        # happened to list. Hydration cannot invent a record: it writes back only
        # rows this application stored, and never a canonical example id.
        #
        # AND A MISS STAYS A 404 WHEN THE DATABASE IS DOWN. `_hydrate_ordinary_scope`
        # returns 0 rather than raising on a failed read, so this returns `None` and
        # the route answers "not found" — which is what it answered before durable
        # storage existed. It must not become a 500: "we could not check" and "it is
        # not here" look identical to a client holding a stale link, and only one of
        # them is a server error.
        if session_id is not None or _hydrate_ordinary_scope() == 0:
            return None
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
    """
    return [
        exp.id,
        bucket,
        exp.version_token(),
        len(exp.answer_log or []),
        _authoritative_signature(exp),
    ]


def _current_plan_row(experiment_id: str, session_id: str | None) -> list | None:
    """Re-read ONE record from disk NOW and rebuild its plan row (``None`` if absent).

    Deliberately reads and rehydrates by exactly the same two steps
    ``_load_all_experiments`` uses (``read_text`` -> ``Experiment.from_state``), so a
    record nobody touched produces a row byte-identical to the one classified
    earlier and the comparison can never refuse spuriously. Absence is a real answer,
    not an error: a record removed in the window has no row, which differs from the
    row it had when it was classified — which is the point.

    Callers hold that id's ``record_lock``; the ``FileNotFoundError`` guard mirrors
    ``_load_all_experiments``'s and exists for the same benign reason.
    """
    state_path = scope_root(session_id) / experiment_id / "experiment.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    exp = Experiment.from_state(state, session_id=session_id)
    return _plan_digest_row(exp, classify_experiment(exp))


def _plan_digest(buckets: dict[str, list["Experiment"]]) -> str:
    """A deterministic, opaque digest of the CLASSIFIED workspace.

    One row per record present: its id, the bucket it classified into, its public
    version token (``<generation>.<rev>``), how many entries its answer log holds,
    and its authoritative signature. Any edit, answer, confirmation, export,
    creation or removal anywhere in the workspace changes at least one row, so it
    changes the digest:

    * an answer / edit / export bumps ``rev`` -> the version token changes;
    * a creation adds a row; a removal drops one;
    * a delete-then-recreate of the same id mints a fresh ``generation``, so the
      digest differs even though ``rev`` returned to 0 (the ABA the generation nonce
      exists to defeat);
    * a record whose provenance marker changed moves bucket.

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
        plan_digest = _plan_digest(buckets)
        at_risk = _at_risk_summary(canonical, legacy)

        # The digest above is one number over the WHOLE classification; these are the
        # individual rows it was reduced from, kept so each id can be re-checked
        # against its own row inside its own lock (C2 — see ``_reset_lock``). An id
        # that was ABSENT here simply has no entry, and ``.get`` returning ``None``
        # is the correct comparison value: "absent then" must match "absent now".
        planned_rows: dict[str, list] = {
            exp.id: _plan_digest_row(exp, bucket)
            for bucket, exps in buckets.items()
            for exp in exps
        }

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
                        break
                    target = scope_root(session_id) / spec.id
                    if target.exists():
                        # path-safe (direct-child-of-THIS-scope guard)
                        _remove_experiment_dir(target, session_id=session_id)
                    # baseline content + fresh generation + DONE artifact
                    _materialise_seed(spec, session_id=session_id)
                    mutated = True

        # ``final_count`` — three cases, and the difference between them is the point
        # of D3. Keep them distinct; collapsing any two makes the number dishonest.
        #
        #  * REFUSED WITHOUT MUTATING: nothing changed, so the classification snapshot
        #    IS the truth. Every pre-C2 refusal was decided before the mutation block,
        #    so this stayed exactly the case it always was.
        #  * REFUSED AFTER MUTATING (C2, a per-record abort part-way through): the
        #    snapshot is NOT the truth any more — ids before the aborted one were
        #    already removed / re-materialised. It falls through to the MEASURED arm
        #    below, so a partial abort reports what it actually left behind. It still
        #    reports ``refused``, so it can never read as success.
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
        if refused and not mutated:
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
