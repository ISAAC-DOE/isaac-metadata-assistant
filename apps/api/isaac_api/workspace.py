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

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from isaac_records.draft_validator import validate_draft
from isaac_records.export import export_draft
from isaac_records.extract.draft_builder import build_draft
from isaac_records.ids import new_record_id

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


def create_experiment(title: str, source: dict, draft: dict) -> Experiment:
    exp = Experiment(
        id=new_record_id(),
        title=title,
        created_utc=_now_iso(),
        source=source,
        draft=draft,
    )
    exp.save()
    return exp


def _seed_draft() -> dict:
    return build_draft(CSV_PATH, LISTING_PATH)


def _seed_source() -> dict:
    return {
        "description": "Synthetic XANES campaign (CuO, Cu K-edge) — committed demo fixtures",
        "files": list(SOURCE_FILES),
    }


def seed_experiment() -> Experiment:
    """Create the single seeded demo experiment (5 pending -> needs_attention)."""
    return create_experiment(
        title="Synthetic XANES — CuO (Cu K-edge) Demo",
        source=_seed_source(),
        draft=_seed_draft(),
    )


def _experiment_dirs() -> list[Path]:
    root = workspace_root()
    if not root.exists():
        return []
    return [p for p in sorted(root.iterdir()) if (p / "experiment.json").exists()]


def ensure_seeded() -> None:
    """Seed exactly ONE demo experiment on first access to an empty workspace."""
    if not _experiment_dirs():
        seed_experiment()


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
