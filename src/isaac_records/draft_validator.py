"""No-guessing enforcement on drafts (authoring time).

This is where the project's core promise is enforced BEFORE anything becomes an
official record: a finalized scalar needs evidence, a missing field must be null,
an inferred field needs a stated derivation rule, and every asset and descriptor
(both scientific/provenance claims) must cite a source.

It deliberately does NOT check vocabulary or units — those are the official
schema's job, applied to the transformed record by `official.validate_official`.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

FINAL_STATUSES = ("verified", "inferred")
OBSERVED_SOURCE_TYPES = (
    "document",
    "spreadsheet",
    "screenshot",
    "web_form",
    "file_listing",
    "user_confirmation",
)


@dataclass
class DraftReport:
    errors: list[tuple[str, str]] = dc_field(default_factory=list)
    warnings: list[tuple[str, str]] = dc_field(default_factory=list)

    def err(self, where: str, msg: str) -> None:
        self.errors.append((where, msg))

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append((where, msg))

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = [f"✗ error   {w} — {m}" for w, m in self.errors]
        lines += [f"⚠ warning {w} — {m}" for w, m in self.warnings]
        lines.append(
            f"{'PASS' if self.ok else 'FAIL'} "
            f"({len(self.errors)} errors, {len(self.warnings)} warnings)"
        )
        return "\n".join(lines)


def _has_observed(entries: list[dict]) -> bool:
    return any(e.get("source_type") in OBSERVED_SOURCE_TYPES for e in entries)


def _has_derivation(entries: list[dict]) -> bool:
    return any(e.get("source_type") == "derivation" and e.get("rule") for e in entries)


def _check_envelope(report: DraftReport, where: str, env: dict) -> None:
    status = env.get("status")
    value = env.get("value")
    entries = [e for e in (env.get("evidence") or []) if isinstance(e, dict)]

    if status not in ("verified", "inferred", "needs_confirmation", "missing", "rejected"):
        report.err(where, f"invalid status {status!r}")
        return
    if status == "missing" and value is not None:
        report.err(where, "status 'missing' but a value is present")
    if status in FINAL_STATUSES and value is None:
        report.err(where, f"status '{status}' but value is null")
    if status == "verified" and value is not None and not _has_observed(entries):
        report.err(where, "verified field has no observed evidence or user confirmation")
    if status == "inferred" and value is not None:
        if not _has_derivation(entries):
            report.err(where, "inferred field has no derivation evidence with a stated rule")
        elif not _has_observed(entries):
            report.warn(where, "inferred field cites a rule but no observed supporting evidence")


def _check_claim(report: DraftReport, where: str, entries) -> None:
    """A claim (asset, descriptor, implicit) must cite at least one source."""
    entries = [e for e in (entries or []) if isinstance(e, dict)]
    if not entries:
        report.err(where, "no evidence — every asset/descriptor/inference must cite a source")


def validate_draft(draft: dict) -> DraftReport:
    report = DraftReport()

    meta = draft.get("meta") or {}
    for key in ("record_type", "record_domain", "source_type"):
        if not meta.get(key):
            report.err(f"meta.{key}", "required to classify the record before export")

    for path, env in (draft.get("fields") or {}).items():
        if not isinstance(env, dict):
            report.err(f"fields.{path}", "must be a field envelope")
            continue
        _check_envelope(report, f"fields.{path}", env)

    for i, asset in enumerate(draft.get("assets") or []):
        if not asset.get("sha256"):
            report.err(f"assets[{i}]", "asset requires a sha256 (raw data is linked + hashed, not copied)")
        _check_claim(report, f"assets[{i}] ({asset.get('asset_id', '?')})", asset.get("evidence"))

    for j, out in enumerate(draft.get("descriptors_outputs") or []):
        for k, d in enumerate(out.get("descriptors") or []):
            if d.get("value") is None:
                report.err(f"descriptors[{j}][{k}]", "descriptor value must not be null — it is a scientific claim")
            _check_claim(report, f"descriptor '{d.get('name', '?')}'", d.get("evidence"))

    for m, imp in enumerate(draft.get("implicit") or []):
        _check_claim(report, f"implicit '{imp.get('about', '?')}'", imp.get("evidence"))

    return report
