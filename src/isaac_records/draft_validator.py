"""No-guessing enforcement on drafts (authoring time).

This is where the project's core promise is enforced BEFORE anything becomes an
official record: a finalized scalar needs evidence, a missing field must be null,
an inferred field needs a stated derivation rule, and every asset and descriptor
(both scientific/provenance claims) must cite a source.

It deliberately does NOT check vocabulary or units — those are the official
schema's job, applied to the transformed record by `official.validate_official`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

# A sha256 digest: exactly 64 lowercase hex chars (strict — no uppercase).
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

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


def _claim_covered(entries) -> bool:
    """A claim is covered iff it cites at least one source (a dict evidence entry)."""
    return any(isinstance(e, dict) for e in (entries or []))


def _check_claim(report: DraftReport, where: str, entries) -> None:
    """A claim (asset, descriptor, implicit) must cite at least one source."""
    if not _claim_covered(entries):
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
        sha = asset.get("sha256")
        if not sha:
            report.err(f"assets[{i}]", "asset requires a sha256 (raw data is linked + hashed, not copied)")
        elif not _SHA256_RE.match(sha):
            report.err(f"assets[{i}]", f"sha256 {sha!r} is not a 64-char lowercase hex digest")
        _check_claim(report, f"assets[{i}] ({asset.get('asset_id', '?')})", asset.get("evidence"))

    for j, out in enumerate(draft.get("descriptors_outputs") or []):
        for k, d in enumerate(out.get("descriptors") or []):
            if d.get("value") is None:
                report.err(f"descriptors[{j}][{k}]", "descriptor value must not be null — it is a scientific claim")
            _check_claim(report, f"descriptor '{d.get('name', '?')}'", d.get("evidence"))

    for m, imp in enumerate(draft.get("implicit") or []):
        _check_claim(report, f"implicit '{imp.get('about', '?')}'", imp.get("evidence"))

    # Block-level provenance coverage. The official record cannot carry per-field
    # evidence for series/qc/links/attribution, so drafts cite it in a block_evidence
    # natural-key map. Each block below CONSTRUCTS its key from draft content and
    # requires a covered entry — a fabricated spectrum, an unevidenced qc verdict, or
    # an unsourced link/contributor is refused here, before export.
    block_evidence = draft.get("block_evidence") or {}

    # Series: every spectrum must cite its reduction source or be user-confirmed.
    seen_series: set[str] = set()
    for i, s in enumerate(draft.get("series") or []):
        series_id = s.get("series_id")
        where = f"series[{i}] ({series_id or '?'})"
        if not series_id:
            report.err(where, "series has no series_id — cannot key its evidence")
            continue
        if series_id in seen_series:
            report.err(f"series[{i}]", f"duplicate series_id '{series_id}' — evidence key not unique")
            continue
        seen_series.add(series_id)
        if not _claim_covered(block_evidence.get(f"series:{series_id}")):
            report.err(where, "series has no evidence; a spectrum must cite its reduction source or be user-confirmed")

    # QC: a measurement with series must carry an evidenced qc verdict (no default 'valid').
    if draft.get("series"):
        qc = draft.get("qc") or {}
        if not qc.get("status") or not _claim_covered(block_evidence.get("qc:status")):
            report.err("qc", "measurement has series but qc verdict has no evidence; confirm or supply provenance (no default 'valid')")

    # Links: each cross-record link must cite its basis; tuple keys must be unique.
    seen_links: set[str] = set()
    for i, link in enumerate(draft.get("links") or []):
        where = f"links[{i}]"
        rel, target, basis = link.get("rel"), link.get("target"), link.get("basis")
        if not (rel and target and basis):
            report.err(where, "link missing required rel/target/basis — cannot key its evidence")
            continue
        key = f"links:{rel}|{target}|{basis}"
        if key in seen_links:
            report.err(where, f"duplicate link {rel}|{target}|{basis} — evidence key not unique")
            continue
        seen_links.add(key)
        if not _claim_covered(block_evidence.get(key)):
            report.err(where, "link has no evidence; a cross-record link must cite its basis or be user-confirmed")

    # Attribution: each contributor must cite its source; name|role keys must be unique.
    seen_contrib: set[str] = set()
    for i, c in enumerate((draft.get("attribution") or {}).get("contributors") or []):
        where = f"attribution.contributors[{i}]"
        name, role = c.get("name"), c.get("role")
        if not (name and role):
            report.err(where, "contributor missing name/role — cannot key its evidence")
            continue
        key = f"attribution:{name}|{role}"
        if key in seen_contrib:
            report.err(where, f"duplicate contributor {name}|{role} — evidence key not unique")
            continue
        seen_contrib.add(key)
        if not _claim_covered(block_evidence.get(key)):
            report.err(where, "contributor has no evidence; attribution must cite its source or be user-confirmed")

    # Tags are user-authored grouping labels — authorship IS the confirmation, so they
    # are deliberately exempt from evidence coverage (no check here, by design).

    # Unsupported scientific blocks: refuse (do not silently drop) any block the XANES
    # MVP exporter has no path for — dropping scientific values violates no-guessing.
    for name in ("processing", "computation"):
        if name in draft:
            report.err(name, f"unsupported scientific block '{name}' — out of XANES MVP scope; the exporter has no path for it")
    measurement = draft.get("measurement")
    if isinstance(measurement, dict) and "processing" in measurement:
        report.err("measurement.processing", "unsupported scientific block 'measurement.processing' — out of XANES MVP scope; the exporter has no path for it")

    return report
