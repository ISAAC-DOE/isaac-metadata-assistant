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
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import secrets
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    """The workspace dir (env-overridable, resolved fresh so tests can monkeypatch)."""
    return Path(os.environ.get("ISAAC_UI_WORKSPACE", DEFAULT_WORKSPACE))


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


@contextlib.contextmanager
def record_lock(experiment_id: str):
    """Serialise the compare-and-swap critical section for one experiment id.

    A REENTRANT lock (``RLock``): across two threads it behaves exactly like a
    plain ``Lock`` (they still serialise on the same id), but the SAME thread may
    re-acquire it. That reentrancy is required because a mutation handler holds
    ``record_lock(id)`` and then calls ``load_experiment`` -> ``ensure_seeded``,
    which may itself take ``record_lock(id)`` for the same id to materialise a
    missing canonical — a plain ``Lock`` would self-deadlock there.
    """
    with _record_locks_guard:
        lock = _record_locks.setdefault(experiment_id, threading.RLock())
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


def _existing_generation(rid: str) -> str | None:
    """The persisted ``generation`` of an on-disk record, or ``None``.

    Reads ``workspace_root()/rid/experiment.json`` and returns its stored
    non-empty ``generation`` string if the file exists and parses; otherwise
    ``None`` (an ad-hoc new id has no prior file -> a fresh generation is minted).
    Preserving the on-disk generation for an explicit existing id keeps a no-op
    upsert (the idempotent demo) from churning the token.
    """
    state_path = workspace_root() / rid / "experiment.json"
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
        return workspace_root() / self.id

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
            sig = _authoritative_signature(Experiment.from_state(state))
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
    def from_state(cls, state: dict) -> "Experiment":
        return cls(
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
) -> Experiment:
    """Create (or upsert, given an explicit ``id``) and persist an experiment.

    ``id`` / ``created_utc`` default to a random ULID + wall-clock timestamp for
    ad hoc use; the canonical seed and the idempotent demo pass EXPLICIT fixed
    values so identities/order are stable across restarts and fresh workspaces.

    Generation minting: an ad-hoc new record (random id) has no prior on-disk file
    -> a FRESH generation is minted. An explicit existing id (the idempotent demo
    upsert) PRESERVES the on-disk generation so repeated no-op runs never churn the
    token.
    """
    rid = id or new_record_id()
    generation = _existing_generation(rid) or _new_generation()
    exp = Experiment(
        id=rid,
        title=title,
        created_utc=created_utc or _now_iso(),
        source=source,
        draft=draft,
        generation=generation,
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

_SEED_TITLE_BASE = "Synthetic XANES — CuO (Cu K-edge)"


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
        # The `Scenario N` prefix is retained deliberately: it is what makes "these
        # are five different scenarios, not five duplicates" legible at a glance,
        # and the demo script refers to the records by number. Everything after the
        # prefix names the MATERIALISATION, in the past tense.
        _SeedSpec(SEED_NEW_DRAFT_ID, "2026-07-12T00:00:01Z",
                  f"{_SEED_TITLE_BASE} · New Draft", _raw_draft, False,
                  "Scenario 1 · seeded: extraction only"),
        _SeedSpec(SEED_PARTIAL_ID, "2026-07-12T00:00:02Z",
                  f"{_SEED_TITLE_BASE} · Partially Completed", _partial_draft, False,
                  "Scenario 2 · seeded: partial answers applied"),
        _SeedSpec(SEED_READY_ID, "2026-07-12T00:00:03Z",
                  f"{_SEED_TITLE_BASE} · Ready to Export", _full_draft, False,
                  "Scenario 3 · seeded: all answers applied"),
        _SeedSpec(SEED_REVIEW_ID, "2026-07-12T00:00:04Z",
                  f"{_SEED_TITLE_BASE} · Export Review Required", _review_draft, False,
                  "Scenario 4 · seeded: descriptor uncertainty omitted"),
        _SeedSpec(SEED_DONE_ID, "2026-07-12T00:00:05Z",
                  f"{_SEED_TITLE_BASE} · Exported Record", _full_draft, True,
                  "Scenario 5 · seeded: export run at setup"),
    ]


#: (created_utc, title) for the canonical ids the idempotent demo overwrites in
#: place, so demo-run reuses the scenario's stable identity instead of appending.
SEED_META = {s.id: (s.created_utc, s.title) for s in _seed_specs()}

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


def _materialise_seed(spec: "_SeedSpec") -> Experiment:
    if not is_record_id(spec.id):  # guard: fixed ids must match RECORD_ID_RE
        raise ValueError(f"canonical seed id {spec.id!r} is not a valid record id")
    exp = Experiment(
        id=spec.id,
        title=spec.title,
        created_utc=spec.created_utc,
        source=_seed_source(),
        draft=spec.draft_fn(),
        generation=_new_generation(),
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


def _experiment_dirs() -> list[Path]:
    root = workspace_root()
    if not root.exists():
        return []
    return [p for p in sorted(root.iterdir()) if (p / "experiment.json").exists()]


def ensure_seeded() -> None:
    """Materialise the five canonical scenarios (by fixed id) when missing.

    Idempotent: only canonical ids not already present are (re)built, so repeated
    calls — and the idempotent demo pass — never grow the record count.

    Locking: ``ensure_seeded`` runs on EVERY read (``list_experiments`` /
    ``load_experiment``), so it can race a concurrent ``reset_to_canonical_seed``
    that is mid-way through ``_remove_experiment_dir`` + ``_materialise_seed`` for
    the same id — without coordination the reader could materialise into a dir the
    reset is ``rmtree``-ing, raising an uncaught ``OSError`` (ENOTEMPTY) -> HTTP 500.
    So the materialise of a MISSING id is done under ``record_lock(spec.id)``, the
    SAME lock reset holds around its remove+materialise, closing that window.

    Deadlock-free by construction: the common case (id present) takes NO lock; a
    lock is acquired for at most ONE id at a time and released before the next, so
    no thread ever holds two record locks — the classic lock-ordering cycle cannot
    form. The lock is a reentrant ``RLock``, so a mutation handler that already
    holds ``record_lock(id)`` and then calls ``load_experiment`` -> ``ensure_seeded``
    (which may re-acquire the same id's lock to materialise it) does not self-deadlock.
    """
    for spec in _seed_specs():
        # Cheap lock-free check first (common case: present -> no lock taken, so
        # the hot read path stays contention-free and cannot deadlock).
        if (workspace_root() / spec.id / "experiment.json").exists():
            continue
        with record_lock(spec.id):
            # Re-check under the lock: reset may have just (re)created it, or another
            # reader may have materialised it; only materialise if STILL missing.
            if not (workspace_root() / spec.id / "experiment.json").exists():
                _materialise_seed(spec)


def list_experiments() -> list[Experiment]:
    ensure_seeded()
    out: list[Experiment] = []
    for d in _experiment_dirs():
        try:
            state = json.loads((d / "experiment.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue  # dir removed by a concurrent reset between listing and read — benign
        out.append(Experiment.from_state(state))
    out.sort(key=lambda e: e.created_utc)
    return out


def load_experiment(experiment_id: str) -> Experiment | None:
    ensure_seeded()
    state_path = workspace_root() / experiment_id / "experiment.json"
    if not state_path.exists():
        return None
    return Experiment.from_state(json.loads(state_path.read_text(encoding="utf-8")))


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


def _load_all_experiments() -> list[Experiment]:
    """Load every persisted experiment WITHOUT reseeding (unlike list_experiments).

    The reset must classify the workspace exactly as it is, so this deliberately
    avoids ``ensure_seeded`` to keep classification honest about missing canonical.
    """
    out: list[Experiment] = []
    for d in _experiment_dirs():
        try:
            state = json.loads((d / "experiment.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue  # dir removed by a concurrent reset between listing and read — benign
        out.append(Experiment.from_state(state))
    return out


def _remove_experiment_dir(exp_dir: Path) -> None:
    """Delete a single experiment directory after proving it is safe.

    Path-safety guard: the target must resolve to a DIRECT child of
    ``workspace_root()`` (never the root itself, never a nested or ``..`` escape).
    Anything else raises rather than deleting.
    """
    root = workspace_root().resolve()
    target = exp_dir.resolve()
    if target == root or target.parent != root:
        raise ValueError(
            f"refusing to remove {target} — not a direct child of the workspace root"
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
    ``_remove_experiment_dir``, which enforces the direct-child path check.
    """
    if classify_experiment(exp) != MANAGED_LEGACY:
        raise ValueError(
            f"refusing to remove non-managed-legacy experiment {exp.id!r}"
        )
    _remove_experiment_dir(exp.dir)


def _canonical_state_counts() -> dict:
    """Workflow-state distribution over the currently-present canonical experiments.

    Reports the projected/actual post-reset distribution (canonical set only);
    legacy/ambiguous records are excluded on purpose.
    """
    counts = {key: 0 for key in _STATE_KEYS}
    for exp in _load_all_experiments():
        if exp.id in CANONICAL_IDS:
            counts[exp.status()] = counts.get(exp.status(), 0) + 1
    return counts


def reset_to_canonical_seed(*, dry_run: bool) -> dict:
    """Classify the workspace and (unless ``dry_run``) restore the canonical seed.

    Refuses (makes NO changes) if ANY ambiguous record exists. Otherwise, on
    execute, removes ONLY the managed_legacy directories via ``remove_experiment``
    (path-safe), then re-materialises EVERY canonical scenario to its deterministic
    seed baseline — a present-but-drifted canonical record (partial answers, stale
    evidence, a wrongly-exported artifact) is removed and rebuilt from the seed, not
    merely left in place. This restores CONTENT, not just the id set, and mints a
    fresh generation per id (invalidating every pre-reset ETag). Idempotent in
    content. Returns typed, path-free data (no filesystem paths).
    """
    experiments = _load_all_experiments()
    buckets: dict[str, list[Experiment]] = {
        CANONICAL: [],
        MANAGED_LEGACY: [],
        AMBIGUOUS: [],
    }
    for exp in experiments:
        buckets[classify_experiment(exp)].append(exp)

    previous_count = len(experiments)
    canonical = buckets[CANONICAL]
    legacy = buckets[MANAGED_LEGACY]
    ambiguous = buckets[AMBIGUOUS]
    refused = bool(ambiguous)

    removed = 0
    if not dry_run and not refused:
        for exp in legacy:
            remove_experiment(exp)
            removed += 1
        # Restore canonical CONTENT to the deterministic seed baseline (not just
        # fill missing). Each canonical id is removed and re-materialised, so
        # drifted content, partial answers, and wrongly-exported artifacts are
        # cleared, and a FRESH generation is minted (invalidating every pre-reset
        # ETag). Targeted to the fixed canonical id set — NOT a broad filesystem
        # wipe.
        for spec in _seed_specs():
            with record_lock(spec.id):
                target = workspace_root() / spec.id
                if target.exists():
                    _remove_experiment_dir(target)  # path-safe (direct-child guard)
                _materialise_seed(spec)  # baseline content + fresh generation + DONE artifact

    # final_count: nothing changes when refused; otherwise the reset guarantees
    # exactly the five canonical records (legacy removed, missing canonical rebuilt).
    final_count = previous_count if refused else len(CANONICAL_IDS)

    return {
        "refused": refused,
        "previous_count": previous_count,
        "canonical_count": len(canonical),
        "legacy_count": len(legacy),
        "ambiguous_count": len(ambiguous),
        "removed_count": removed,
        "final_count": final_count,
        "canonical_ids": sorted(CANONICAL_IDS),
        "removable": [{"id": e.id, "title": e.title} for e in legacy],
        "state_counts": _canonical_state_counts(),
    }
