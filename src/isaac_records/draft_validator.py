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


# --- malformed top-level containers -------------------------------------------
#
# EVERY TOP-LEVEL CONTAINER THIS MODULE WALKS, AND THE JSON TYPE IT MUST BE.
#
# This table exists because `validate_draft` used to walk these containers without
# asking, so a stored draft whose `assets` was a string reached `asset.get("sha256")`
# and raised. Measured over HTTP on `721238a`, on a record with nothing pending (which
# is what lets `Experiment.export_ready` reach `draft_ok`): `GET
# /api/experiments/{id}` -> 500. The exception class depended only on whether the wrong
# type happened to be iterable (`TypeError`) or not (`AttributeError`); neither is an
# answer.
#
# NOT ALL TEN RAISED, AND THE DIFFERENCE MATTERS ENOUGH TO STATE IT HERE RATHER THAN
# LET A READER ASSUME OTHERWISE. An earlier revision of this comment, and of three
# sibling claims, said "all ten"; an independent review measured that false and it is
# corrected rather than deleted, because the false version concealed the one verdict
# this change moves. Measured on `721238a`, wrong-typed and truthy, one container at a
# time on an otherwise-minimal draft:
#
#   EIGHT raised unconditionally:  meta, fields, attribution, assets,
#                                  descriptors_outputs, implicit, series, links
#   `qc`  raised only when a series was present, because that is the only thing that
#         reads it — and the guard below is inside the SAME `if series:`, so `qc`
#         behaves identically before and after, in both branches.
#   `block_evidence` raised only when a series, a link, a contributor or the qc gate
#         looked it up. A draft with NONE of those never reached `.get` and so
#         VALIDATED CLEAN.
#
# So there is exactly one verdict flip: a draft storing a truthy non-object
# `block_evidence` and carrying no series, no links and no contributors went from
# PASS to FAIL, and `Experiment.draft_ok()` from True to False. It is a flip toward
# refusal, on a document that could never have exported anyway — `export.build_sidecar`
# does `(draft.get("block_evidence") or {}).items()`, so that draft raised
# `AttributeError` out of `export_draft`. The change converts that third crash into a
# clean refusal. Nothing that previously EXPORTED stops exporting; one thing that
# previously reported PASS while being unexportable now reports why.
#
# THE RULE: a container of the wrong type is a FINDING, not an exception. This module
# is asked "is this draft fit to become an official record, and if not, where is it
# wrong"; for a wrong-typed container the answer is *no, here*. Raising instead denies
# the reader the one answer their record's own validator exists to give — and unlike a
# malformed REQUEST, which the caller sent and can be told to fix, a malformed
# PERSISTED document is not the reader's fault and refusing it hides their record.
#
# The container is then treated as EMPTY for the rest of the pass. Not coerced, not
# guessed at, and NOT walked: `enumerate("abc")` would file three per-position claims
# invented out of a string's characters, which `serialize.py`'s per-item isolation note
# names as "a fabricated partial success, which is worse than the failure it replaced".
# Nothing here may assume what the container was meant to hold (CLAUDE.md §5).
#
# DELIBERATELY LIMITED TO THE TOP LEVEL. Nested payloads — a field envelope's
# `evidence`, `attribution.contributors` — still raise, and `routes._probe_override`
# depends on that: it catches `_PROBE_STRUCTURAL_ERRORS` to turn a malformed request
# into a typed 422. Widening this into them would make both `except` branches dead and
# would replace a refusal the caller can act on with a stored-then-refused override.
_TOP_LEVEL_CONTAINERS: dict[str, type] = {
    "meta": dict,
    "fields": dict,
    "block_evidence": dict,
    "qc": dict,
    "attribution": dict,
    "assets": list,
    "descriptors_outputs": list,
    "implicit": list,
    "series": list,
    "links": list,
}

#: Neutral English for a JSON type. The stored VALUE is never interpolated into a
#: message: the reader is told what SHAPE was found, not handed arbitrary content back
#: rendered as though it were the validator's own words. `serialize._JSON_KIND` took
#: the same decision for the same reason.
_JSON_KIND: dict[type, str] = {
    bool: "a boolean",
    int: "a number",
    float: "a number",
    str: "a string",
    dict: "an object",
    list: "a list",
    type(None): "null",
}

_CONTAINER_SHAPE: dict[type, str] = {dict: "an object", list: "a list"}


def _kind(value: object) -> str:
    # `bool` before `int`: `type(True) is bool`, so the dict lookup is already exact,
    # but a future `isinstance` rewrite here would get it wrong in the usual way.
    return _JSON_KIND.get(type(value), "a value of an unreadable type")


def _container(report: DraftReport, draft: dict, name: str):
    """The named top-level container, or an EMPTY one of the right type plus a finding.

    A FALSY wrong type keeps its long-standing normalisation: `draft.get("assets") or
    []` has always read `0`, `""` and `False` as "no assets", exactly as
    `workspace._hydrate_notes` reads a non-list `notes` as no notes. That tolerance is
    not obviously right, but it is not this guard's to change — altering it would move
    the verdict on drafts nobody reported a defect about. Only a TRUTHY wrong type,
    which is the shape that used to raise, is reported.
    """
    expected = _TOP_LEVEL_CONTAINERS[name]
    raw = draft.get(name)
    if not raw:
        return expected()
    if isinstance(raw, expected):
        return raw
    report.err(
        name,
        f"must be {_CONTAINER_SHAPE[expected]}; this draft stores {_kind(raw)}. "
        f"A container of another type is refused rather than walked — nothing here "
        f"can assume what it was meant to hold, and reading positions out of it "
        f"would invent claims the draft never made.",
    )
    return expected()


def validate_draft(draft: dict) -> DraftReport:
    report = DraftReport()

    meta = _container(report, draft, "meta")
    for key in ("record_type", "record_domain", "source_type"):
        if not meta.get(key):
            report.err(f"meta.{key}", "required to classify the record before export")

    fields = _container(report, draft, "fields")
    for path, env in fields.items():
        if not isinstance(env, dict):
            report.err(f"fields.{path}", "must be a field envelope")
            continue
        _check_envelope(report, f"fields.{path}", env)

    for i, asset in enumerate(_container(report, draft, "assets")):
        sha = asset.get("sha256")
        if not sha:
            report.err(f"assets[{i}]", "asset requires a sha256 (raw data is linked + hashed, not copied)")
        elif not _SHA256_RE.match(sha):
            report.err(f"assets[{i}]", f"sha256 {sha!r} is not a 64-char lowercase hex digest")
        _check_claim(report, f"assets[{i}] ({asset.get('asset_id', '?')})", asset.get("evidence"))

    for j, out in enumerate(_container(report, draft, "descriptors_outputs")):
        for k, d in enumerate(out.get("descriptors") or []):
            if d.get("value") is None:
                report.err(f"descriptors[{j}][{k}]", "descriptor value must not be null — it is a scientific claim")
            _check_claim(report, f"descriptor '{d.get('name', '?')}'", d.get("evidence"))

    for m, imp in enumerate(_container(report, draft, "implicit")):
        _check_claim(report, f"implicit '{imp.get('about', '?')}'", imp.get("evidence"))

    # Block-level provenance coverage. The official record cannot carry per-field
    # evidence for series/qc/links/attribution, so drafts cite it in a block_evidence
    # natural-key map. Each block below CONSTRUCTS its key from draft content and
    # requires a covered entry — a fabricated spectrum, an unevidenced qc verdict, or
    # an unsourced link/contributor is refused here, before export.
    block_evidence = _container(report, draft, "block_evidence")

    # Series: every spectrum must cite its reduction source or be user-confirmed.
    seen_series: set[str] = set()
    # BOUND ONCE, and read again by the qc gate below, so the finding about an
    # unreadable `series` is filed exactly once and both readers see the same value.
    series = _container(report, draft, "series")
    for i, s in enumerate(series):
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
    # `series`, NOT `draft.get("series")`. A truthy-but-unreadable value used to
    # satisfy this gate by truthiness alone, producing a second finding about the QC
    # verdict of a spectrum that could not be read — a claim this module is in no
    # position to make, derived from the very value it just refused.
    if series:
        qc = _container(report, draft, "qc")
        if not qc.get("status") or not _claim_covered(block_evidence.get("qc:status")):
            report.err("qc", "measurement has series but qc verdict has no evidence; confirm or supply provenance (no default 'valid')")

    # Links: each cross-record link must cite its basis; tuple keys must be unique.
    seen_links: set[str] = set()
    for i, link in enumerate(_container(report, draft, "links")):
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
    attribution = _container(report, draft, "attribution")

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
    for path in _paths_authoring_uploaded_by(fields):
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
