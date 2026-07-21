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

import copy
import json
import os
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

DEFAULT_WORKSPACE = "/tmp/isaac-ui-workspace"

# Derived status values (product vocabulary for the UI).
NEEDS_ATTENTION = "needs_attention"
IN_REVIEW = "in_review"
READY_TO_EXPORT = "ready_to_export"
DONE = "done"


def workspace_root() -> Path:
    """The workspace dir (env-overridable, resolved fresh so tests can monkeypatch)."""
    return Path(os.environ.get("ISAAC_UI_WORKSPACE", DEFAULT_WORKSPACE))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_demo_answers() -> dict:
    """The committed synthetic completion answers (SIMULATED human input)."""
    return json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))


# --- experiment record --------------------------------------------------------


@dataclass
class Experiment:
    id: str
    title: str
    created_utc: str
    source: dict
    draft: dict
    answer_log: list = field(default_factory=list)
    record_id: str | None = None

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
        }

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self.to_state(), indent=2) + "\n", encoding="utf-8"
        )

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
    """
    exp = Experiment(
        id=id or new_record_id(),
        title=title,
        created_utc=created_utc or _now_iso(),
        source=source,
        draft=draft,
    )
    exp.save()
    return exp


def _seed_source() -> dict:
    return {
        "description": "Synthetic XANES campaign (CuO, Cu K-edge) — committed demo fixtures",
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


def _seed_specs() -> list["_SeedSpec"]:
    return [
        _SeedSpec(SEED_NEW_DRAFT_ID, "2026-07-12T00:00:01Z",
                  f"{_SEED_TITLE_BASE} · New Draft", _raw_draft, False),
        _SeedSpec(SEED_PARTIAL_ID, "2026-07-12T00:00:02Z",
                  f"{_SEED_TITLE_BASE} · Partially Completed", _partial_draft, False),
        _SeedSpec(SEED_READY_ID, "2026-07-12T00:00:03Z",
                  f"{_SEED_TITLE_BASE} · Ready to Export", _full_draft, False),
        _SeedSpec(SEED_REVIEW_ID, "2026-07-12T00:00:04Z",
                  f"{_SEED_TITLE_BASE} · Export Review Required", _review_draft, False),
        _SeedSpec(SEED_DONE_ID, "2026-07-12T00:00:05Z",
                  f"{_SEED_TITLE_BASE} · Exported Record", _full_draft, True),
    ]


#: (created_utc, title) for the canonical ids the idempotent demo overwrites in
#: place, so demo-run reuses the scenario's stable identity instead of appending.
SEED_META = {s.id: (s.created_utc, s.title) for s in _seed_specs()}


def _write_seed_record(exp: Experiment, result) -> None:
    """Write the REAL export_draft output (record + sidecar) into the records dir.

    Mirrors ``routes._write_record``; never hand-writes schema content.
    """
    exp.records_dir.mkdir(parents=True, exist_ok=True)
    exp.record_id = result.record["record_id"]
    (exp.records_dir / f"{exp.record_id}.json").write_text(
        json.dumps(result.record, indent=2) + "\n", encoding="utf-8"
    )
    (exp.records_dir / f"{exp.record_id}.evidence.json").write_text(
        json.dumps(result.sidecar, indent=2) + "\n", encoding="utf-8"
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
    """
    existing = {p.name for p in _experiment_dirs()}
    for spec in _seed_specs():
        if spec.id not in existing:
            _materialise_seed(spec)


def list_experiments() -> list[Experiment]:
    ensure_seeded()
    out: list[Experiment] = []
    for d in _experiment_dirs():
        state = json.loads((d / "experiment.json").read_text(encoding="utf-8"))
        out.append(Experiment.from_state(state))
    out.sort(key=lambda e: e.created_utc)
    return out


def load_experiment(experiment_id: str) -> Experiment | None:
    ensure_seeded()
    state_path = workspace_root() / experiment_id / "experiment.json"
    if not state_path.exists():
        return None
    return Experiment.from_state(json.loads(state_path.read_text(encoding="utf-8")))
