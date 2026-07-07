"""Advisory portal-style soft-warning seam (LOCAL — NOT official portal parity).

The official ISAAC portal ships a *soft-warning* tier in `portal/validation.py`
(NO_LINKS, MISSING_PH, GALVANOSTATIC_NO_POTENTIAL, FE_SUM_EXCEEDS_UNITY, ...) layered
on top of the hard, schema-enforced (HTTP-400) rules. That upstream validator is **not
vendored** in this repo (see docs/portal-warnings.md), so this module deliberately does
**not** reproduce it. It is a small, clearly-labelled *local* advisory seam: it emits
structured soft-warnings derived only from the record's own content and the vendored
schema's documented soft conventions.

Where it sits in the validation stack (see docs/architecture.md, docs/proposal-v2.md):

    1. Draft no-guessing validation       (draft_validator.py)     — gates authoring
    2. Official ISAAC schema validation    (official.py)            — gates export  ← HARD GATE
    3. Portal-style advisory warnings      (this module)            — ADVISORY ONLY, non-gating
    4. AI scientific consistency review    (review.py)              — advisory placeholder
    5. Human review of anything flagged                            — the decider

Hard guarantees (mirroring review.py):
  - **advisory only** — it never marks a record officially valid or invalid; the report
    deliberately exposes no ``.ok`` / ``.valid`` / ``.passed`` / ``.errors``;
  - **never mutates** the record;
  - **never blocks export** — nothing in the export/validation/audit path imports this
    module (enforced by a test), so it cannot change whether a record is produced;
  - **never uses Graphify.**

True portal parity requires vendoring + reviewing the upstream `portal/validation.py`
(with provenance), then reconciling its exact codes/semantics. Until then the codes below
are *local heuristics* — the documented upstream names are reused where they map cleanly
(``NO_LINKS``), and clearly-scoped local names are used otherwise
(``QC_NONVALID_WITHOUT_EVIDENCE``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class PortalWarning:
    """One advisory soft-warning. Never a pass/fail verdict."""

    code: str  # documented upstream name (NO_LINKS) or a local name (QC_NONVALID_WITHOUT_EVIDENCE)
    where: str  # official JSON-path the warning concerns
    message: str

    def render(self) -> str:
        return f"⚠ [{self.code}] {self.where} — {self.message}"


@dataclass(frozen=True)
class PortalWarningReport:
    """Advisory result. Deliberately has NO ``.ok`` / ``.valid`` / ``.passed`` / ``.errors``
    — this layer does not decide official validity and does not gate export. ``advisory`` is
    always True and is a self-check."""

    warnings: tuple[PortalWarning, ...] = ()
    advisory: bool = True

    def render(self) -> str:
        if not self.warnings:
            return (
                "Advisory portal warnings: none. "
                "(Advisory only — does not affect official validity or export.)"
            )
        lines = [
            "Advisory portal warnings (LOCAL seam — do NOT affect official validity or export):"
        ]
        lines.extend(f"  {w.render()}" for w in self.warnings)
        lines.append(f"({len(self.warnings)} advisory warning(s) — non-gating)")
        return "\n".join(lines)


def _no_links(record: dict) -> PortalWarning | None:
    """Optional ``links`` block absent — the record declares no relationship to any other
    record. Mirrors the upstream ``NO_LINKS`` soft-warning; the schema makes ``links``
    optional, so this is advisory, never a hard error."""
    if not record.get("links"):
        return PortalWarning(
            code="NO_LINKS",
            where="links",
            message=(
                "record declares no relationships to other records "
                "(optional `links` block absent)."
            ),
        )
    return None


def _qc_nonvalid_without_evidence(record: dict) -> PortalWarning | None:
    """``measurement.qc.status`` is not ``valid`` but ``qc.evidence`` is missing. The schema
    describes ``qc.evidence`` as "REQUIRED in practice when status != valid" yet does not hard-
    enforce it — exactly the kind of gap a soft-warning tier catches."""
    qc = (record.get("measurement") or {}).get("qc") or {}
    status = qc.get("status")
    if status and status != "valid" and not qc.get("evidence"):
        return PortalWarning(
            code="QC_NONVALID_WITHOUT_EVIDENCE",
            where="measurement.qc.evidence",
            message=(
                f"qc.status is '{status}' but qc.evidence is missing; the schema notes "
                "evidence is expected in practice when status is not 'valid'."
            ),
        )
    return None


# Registry of advisory checks. Each takes a record and returns a PortalWarning or None.
# Intentionally small and generic — no domain-specific scientific judgment, no guessing.
_CHECKS: tuple[Callable[[dict], PortalWarning | None], ...] = (
    _no_links,
    _qc_nonvalid_without_evidence,
)


def portal_warnings(record: dict) -> PortalWarningReport:
    """Run the local advisory soft-warning checks over ``record``.

    Read-only: the record is never mutated. The result is advisory and non-gating — it does
    not decide official validity and callers must not use it to block export.
    """
    found = tuple(w for check in _CHECKS if (w := check(record)) is not None)
    return PortalWarningReport(warnings=found)
