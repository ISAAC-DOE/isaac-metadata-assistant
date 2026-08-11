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
#
# ``\A``/``\Z``, not ``^``/``$``: Python's ``$`` also matches immediately BEFORE a
# trailing newline, so ``^[0-9a-f]{64}$`` accepted the 65-character string
# ``"a"*64 + "\n"`` — measured — and nothing downstream caught it. The official
# schema declares ``assets.items.properties.sha256`` as bare ``{"type": "string"}``
# (no pattern, no length bound), so the malformed digest exported into an official
# record and passed ``validate_official`` clean. A hash that is not a hash is
# exactly the guessed/unverifiable value this module exists to refuse.
#
# The exactness lives in the PATTERN rather than in a ``fullmatch`` call site so
# that every present and future consumer of this constant is exact by construction;
# a new ``.match()`` caller cannot reintroduce the hole. ``format_shadow``'s
# ``_RFC3339_SHAPE`` took the same decision for the same reason.
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")

FINAL_STATUSES = ("verified", "inferred")

# The one official field a draft may never author, as a dotted official JSON-path.
#
# It is LOAD-BEARING, not decorative, and that distinction was earned: an earlier revision
# of this comment claimed the constant coupled three sites so that renaming it would move
# them all, while the block refusal below and `export`'s invariant both hardcoded the leaf
# string. Review #4 renamed the constant and measured the result — the validator stopped
# refusing and the invariant stopped stripping, i.e. the single edit the comment promised was
# safe silently DISARMED the guard. Both sites now split this constant instead, so the claim
# is true. Do not reintroduce a literal "uploaded_by" in either place.
UPLOADED_BY_PATH = "attribution.uploaded_by"

# ONE message for every mechanism. It used to be typed out at the single site that
# existed; an independent review then found a second, unguarded mechanism, and a
# hand-copied second message would have been free to drift from the first.
UPLOADED_BY_REFUSAL = (
    "a draft may not author this field — the official schema declares it "
    "server-stamped from the authenticated identity at ingestion, with any "
    "client value overwritten. ISAAC has no trusted authenticated identity to "
    "stamp it with, and no evidence can make a client-supplied value true "
    "(evidence can show a document names someone, not that the server "
    "authenticated them). Remove it; record people via "
    "attribution.contributors[], which is evidence-gated. A future "
    "server-stamped value must be injected server-side at ingestion, never "
    "carried in draft content."
)

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


def _paths_authoring_uploaded_by(fields) -> list[str]:
    """Every `draft["fields"]` key that would land a value on `attribution.uploaded_by`.

    `fields` + `export.set_path` is the draft format's NATIVE mechanism for scalar
    official JSON-paths, and `attribution.uploaded_by` IS a scalar official string —
    so this is not an exotic bypass, it is the ordinary way to write the field. Three
    spellings reach it, and all three are refused:

      1. the exact path, `fields["attribution.uploaded_by"]`;
      2. a DEEPER path, `fields["attribution.uploaded_by.x"]`, which `set_path` creates
         the refused key as a dict in order to reach;
      3. a SHORTER path whose envelope VALUE supplies the remaining segments, e.g.
         `fields["attribution"] = {"value": {"uploaded_by": ...}, ...}`.

    (3) is measured, not hypothetical: at the first-attempt commit it produced a record
    carrying `{"uploaded_by": "attacker@example.invalid"}` exactly as (1) did.

    On spellings that do NOT reach it: `set_path` performs no normalisation whatsoever —
    it splits on "." and uses the segments as dict keys verbatim. So `" attribution.
    uploaded_by"` writes a top-level `" attribution"` key and `"attribution.uploaded_by "`
    writes `"uploaded_by "` inside the block; `"attribution..uploaded_by"` nests under an
    empty-string key. None is the real field, and each is rejected outright by the
    official schema, which sets `additionalProperties: false` on both the record root and
    the attribution block. Whitespace variants are therefore deliberately NOT normalised
    here: silently treating `" attribution"` as `attribution` would invent an intent the
    draft did not express, and the schema already refuses it loudly.

    Refusal is on KEY PRESENCE, consistent with the `attribution` block check: a null or
    empty-string value still asserts authorship of a server-owned field. (Note the
    exporter would SKIP such an envelope, so this check is strictly stricter than what
    can leak — that is the intended direction.)
    """
    target = UPLOADED_BY_PATH.split(".")
    offenders: list[str] = []
    for path, env in (fields or {}).items():
        if not isinstance(path, str):
            continue
        parts = path.split(".")
        if parts[: len(target)] == target:
            offenders.append(path)  # spellings (1) and (2)
            continue
        if target[: len(parts)] == parts:
            # spelling (3): walk the envelope's value for the missing segments.
            node = env.get("value") if isinstance(env, dict) else None
            for segment in target[len(parts) :]:
                if not isinstance(node, dict) or segment not in node:
                    break
                node = node[segment]
            else:
                offenders.append(path)
    return sorted(offenders)


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

    # Attribution: `uploaded_by` is refused outright, and each contributor must cite
    # its source; name|role keys must be unique.
    attribution = draft.get("attribution") or {}

    # `attribution.uploaded_by` is not a field a draft may author. The official schema
    # declares it SERVER-STAMPED from the authenticated identity at ingestion, with any
    # client value overwritten ("tamper-proof attribution", D. Sokaras 2026-06-15) — and
    # ISAAC has no trusted identity to stamp it with (nothing in the app reads an
    # authenticated principal; see docs/identity-trust-contract.md §6A). So there is no
    # evidence that could make a draft-supplied value true: evidence can show that a
    # document NAMES someone, never that the server AUTHENTICATED them. Letting it pass
    # would launder a client string into a field readers are told is tamper-proof, and
    # it can name a real person. Refuse, fail closed. This is key-presence, not
    # truthiness: a null, an empty string and an envelope are all refused, because each
    # asserts authorship of a server-owned field.
    #
    # TWO refusals, because there are two ways a draft can express the field, and the
    # first attempt at this fix guarded only the block. `where` names the mechanism so a
    # user can tell which one they used; the message is one shared constant.
    if isinstance(attribution, dict) and UPLOADED_BY_PATH.split(".")[1] in attribution:
        report.err(UPLOADED_BY_PATH, UPLOADED_BY_REFUSAL)
    for path in _paths_authoring_uploaded_by(draft.get("fields")):
        report.err(f"fields[{path!r}]", UPLOADED_BY_REFUSAL)
    # THE SIDECAR-ONLY MECHANISMS (`implicit[].about`, `block_evidence` keys) ARE
    # DELIBERATELY NOT REFUSED. An earlier revision of this branch refused them, to keep
    # every spelling loud rather than silently filtered. That was withdrawn together with
    # the sidecar filter it paired with — see the long note in `export.build_sidecar`. In
    # short: the sidecar is unvalidated free text that legitimately carries names and
    # quotes, so matching keys that merely LOOK like this field guarded nothing, and the
    # refusal's normalising comparison over-matched (it would have rejected a
    # `block_evidence` key a user wrote as `implicit:...`). The official record is where a
    # server-stamped identity is asserted, and that is guarded above and in `export`.
    seen_contrib: set[str] = set()
    for i, c in enumerate(attribution.get("contributors") or []):
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
