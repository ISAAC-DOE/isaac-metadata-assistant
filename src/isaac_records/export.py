"""Transform a draft into an official ISAAC record + an evidence sidecar.

The record conforms to the official schema (no envelope, no evidence keys — the
schema is `additionalProperties: false`). The sidecar preserves the auditability
the record cannot carry: it maps official JSON-paths (and asset/descriptor/implicit
keys) to the evidence collected during drafting.

Export is validation-gated: it refuses unless the draft passes no-guessing checks
AND the produced record passes the official schema.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .draft_validator import UPLOADED_BY_PATH, DraftReport, validate_draft
from .exactness import check_exactness, describe_characters
from .ids import is_record_id, new_record_id
from .official import OfficialReport, validate_official

ISAAC_VERSION = "1.05"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_path(obj: dict, dotted: str, value) -> None:
    """Set a nested object path (dotted, no array indices), creating dicts."""
    parts = dotted.split(".")
    node = obj
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def get_path(obj, dotted: str):
    node = obj
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


def strip_evidence(node):
    """Deep-copy a structured block with every 'evidence' key removed, so it
    conforms to the official schema (which forbids unknown keys)."""
    if isinstance(node, dict):
        return {k: strip_evidence(v) for k, v in node.items() if k != "evidence"}
    if isinstance(node, list):
        return [strip_evidence(v) for v in node]
    return node


def _enforce_server_owned_invariant(record: dict) -> None:
    """FINAL INVARIANT — the assembled record carries no `attribution.uploaded_by`.

    The schema declares this field SERVER-STAMPED from the authenticated identity, with
    any client value overwritten (tamper-proof attribution, D. Sokaras 2026-06-15). ISAAC
    authenticates nobody, so it has nothing true to stamp, and copying a draft's string
    would launder client input into a field readers are told the server owns. The
    USER-VISIBLE refusal is `draft_validator`'s, and `export_draft` gates on it; this is
    the structural backstop for callers that invoke `transform` directly — which
    `apps/api/isaac_api/dependencies.py:68` does for exported-artifact drift detection, so
    it is live in production, not test-only.

    WHY IT LIVES HERE, AFTER EVERY WRITER, AND NOT INSIDE ONE OF THEM. The first attempt
    at this fix popped the key inside the `attribution` block writer. An independent
    adversarial review (finding C1) proved that non-composing: `transform` writes into
    `record["attribution"]` from TWO independent places, and the other one — the `fields`
    loop's `set_path`, which is the draft format's NATIVE mechanism for scalar official
    JSON-paths — was unguarded. Measured at that commit: `validate_draft` ok with zero
    errors, `isaac export` printing "PASS — valid against official ISAAC schema v1.05",
    and `{"uploaded_by": "attacker@example.invalid"}` on disk. A third mechanism
    (`fields["attribution"]` carrying the whole block as one object value) leaked the same
    way. Guarding write mechanisms one by one loses to whichever one you did not think of;
    guarding the OUTPUT does not. Keep this call last, and add to it rather than
    scattering equivalents back into the writers.

    It also fixes review finding I2. The per-writer version had made one shape WORSE than
    the pre-fix parent: an attribution block stripping to `{}` no longer overwrote what
    the `fields` loop had already written there, so a leak that the parent's unconditional
    assignment had accidentally clobbered became visible. Running after both writers means
    there is no ordering in which a leak survives.

    Do NOT turn this into a server-stamp. A future stamped value (Q10,
    docs/identity-trust-contract.md §7) must be injected on the trusted server side at
    ingestion — never read from draft content, and never plumbed through this function as
    a caller-supplied argument, which would only move the same untrusted input one frame
    up.
    """
    block_key, leaf_key = UPLOADED_BY_PATH.split(".")
    attribution = record.get(block_key)
    # A non-dict `attribution` — a draft can produce one via `fields["attribution"]` with a
    # list or scalar value — is left alone: there is no key to remove. Be precise about what
    # stops it, because the "single chokepoint" framing does not by itself: a LIST value
    # like `[{"uploaded_by": ...}]` slips BOTH halves of this fix (the validator's
    # spelling-(3) walk breaks on the first non-dict, and this skips it), and only OFFICIAL
    # VALIDATION refuses it, as a type error. So the honest claim is that no *exported*
    # record can carry the field — `transform` output alone is not the guarantee, which
    # matters for `dependencies.py:68`, the one caller that consumes `transform` without
    # validating. Review #2, finding M-2.
    if isinstance(attribution, dict):
        if leaf_key in attribution:
            # Rebuild rather than `pop`. The `fields` loop writes by reference via
            # `set_path`, so for the whole-block spelling `record["attribution"]` IS the
            # draft's own nested dict — an in-place `pop` deleted the key from the CALLER'S
            # draft (review #2, finding I-2). `transform` must stay total and side-effect
            # free: `apps/api/isaac_api/dependencies.py:68` passes the LIVE `exp.draft` for
            # read-only drift detection and `:69` documents transform as "read-only + total".
            # Mutating there would silently strip a stored draft and make the check
            # non-idempotent.
            attribution = {k: v for k, v in attribution.items() if k != leaf_key}
            record[block_key] = attribution
        # An attribution block left empty is omitted rather than written as `{}`. `{}` IS
        # schema-valid here (`additionalProperties: false`, no required keys — pinned by
        # tests/test_truthpath_characterization.py's "attribution = {}" case), but it
        # asserts nothing, so writing it records an empty claim. This applies both to a
        # block emptied BY the refusal and to one that arrives empty because it held only
        # `evidence` keys, which `strip_evidence` removes (review finding I4: a real,
        # deliberate second behaviour change, disclosed rather than reverted).
        if not attribution:
            del record[block_key]


def transform(draft: dict, *, record_id: str | None = None, now: str | None = None) -> dict:
    """Build the official-shape record from a draft (no validation here)."""
    now = now or _now_iso()
    meta = draft.get("meta") or {}
    record: dict = {
        "isaac_record_version": ISAAC_VERSION,
        "record_id": record_id or new_record_id(),
    }
    for key in ("record_type", "record_domain", "source_type"):
        if meta.get(key) is not None:
            record[key] = meta[key]

    # Scalar fields: drop the envelope, keep the value. Skip honestly-missing fields.
    for path, env in (draft.get("fields") or {}).items():
        if not isinstance(env, dict):
            continue
        if env.get("status") == "missing" or env.get("value") is None:
            continue
        set_path(record, path, env["value"])

    # Timestamps: created_utc is required by the schema — default to now.
    record.setdefault("timestamps", {})
    record["timestamps"].setdefault("created_utc", now)

    # Structured blocks copied verbatim, evidence keys stripped.
    # R2 — `is not None`, NOT truthiness. The guard used to read `if draft.get("series"):`,
    # so a draft with `series: []` fell through the whole block and the exported record
    # carried NO `measurement` at all. That silently DELETED an evidenced qc verdict:
    # measured on a draft holding `series: []` plus
    # `qc: {status: "nonvalid", evidence: "Beam damage observed in scans 4-6."}`, the
    # transform produced a record with `"measurement" in record` False, and official
    # validation PASSED — an operator's recorded judgment that the data was bad, dropped,
    # with a clean bill of health on the way out.
    #
    # It compounded: with the qc block gone, `_qc_nonvalid_without_evidence` had nothing
    # to inspect, so the deletion also suppressed the one advisory warning that would
    # have flagged it. The falsy guard laundered its own evidence.
    #
    # `series: []` is schema-valid (no `minItems` — verified against the vendored schema,
    # 0 errors), so emitting it is legal, and PRESERVING the operator's verdict is
    # strictly more honest than discarding it. An empty series is now disclosed instead,
    # by `portal_warnings.NO_MEASUREMENT_SERIES`.
    #
    # An ABSENT `series` (None) still skips the block, unchanged: there is no measurement
    # to describe and nothing to preserve. Only the empty-list case changes.
    if draft.get("series") is not None:
        record.setdefault("measurement", {})["series"] = strip_evidence(draft["series"])
        if draft.get("qc"):
            # qc goes through verbatim (a shallow copy of its entries), NOT
            # strip_evidence: the schema defines measurement.qc.evidence as a native
            # string field, so blanket-stripping "evidence" would delete it.
            record["measurement"]["qc"] = dict(draft["qc"])
        # No qc fallback: a verdict is never invented. A series-present/qc-absent draft
        # is refused upstream by validate_draft (and would fail official validation,
        # which requires measurement.qc); export_draft gates on both.
    if draft.get("assets"):
        record["assets"] = [strip_evidence(a) for a in draft["assets"]]
    if draft.get("descriptors_outputs"):
        record["descriptors"] = {"outputs": strip_evidence(draft["descriptors_outputs"])}
    if draft.get("links") is not None:
        record["links"] = strip_evidence(draft["links"])
    if draft.get("attribution"):
        record["attribution"] = strip_evidence(draft["attribution"])
    if draft.get("tags"):
        record["tags"] = list(draft["tags"])

    _enforce_server_owned_invariant(record)
    return record


def build_sidecar(draft: dict, record: dict) -> dict:
    """Evidence map keyed by official JSON-path / asset / descriptor / implicit."""
    ev: dict = {}
    for path, env in (draft.get("fields") or {}).items():
        if isinstance(env, dict) and env.get("evidence") and env.get("value") is not None:
            ev[path] = env["evidence"]
    for asset in draft.get("assets") or []:
        if asset.get("evidence"):
            ev[f"assets:{asset.get('asset_id', asset.get('uri', '?'))}"] = asset["evidence"]
    for out in draft.get("descriptors_outputs") or []:
        for d in out.get("descriptors") or []:
            if d.get("evidence"):
                ev[f"descriptors:{d.get('name', '?')}"] = d["evidence"]
    for imp in draft.get("implicit") or []:
        ev[f"implicit:{imp.get('about', '?')}"] = {
            "value": imp.get("value"),
            "evidence": imp.get("evidence", []),
        }
    # Block-level provenance (series/qc/links/attribution natural keys) passes through
    # verbatim: its namespaces cannot collide with dotted paths or assets:/descriptors:/
    # implicit: keys.
    for key, entries in (draft.get("block_evidence") or {}).items():
        ev[key] = entries
    # THE SIDECAR IS DELIBERATELY NOT FILTERED FOR THE REFUSED FIELD, and that is a
    # reversal — two earlier attempts in this branch filtered it. Both were wrong, and the
    # reason is worth keeping so a fourth attempt is not made.
    #
    # An exact-match filter missed `implicit`; a normalising filter missed
    # `implicit:implicit:...`, an unlisted `meta:` prefix, and zero-width characters
    # (`'\u200b'.isspace()` is False). Each round was a denylist over caller-chosen free
    # text, and a denylist over free text cannot be closed by adding cases.
    #
    # More importantly it was never a boundary. This map legitimately carries arbitrary
    # caller text — contributor names, document quotes, user-confirmation answers — so an
    # author who wants a person's name in a sidecar can simply write
    # `about: "who_uploaded_this"` and no filter would or should object. Filtering keys that
    # merely LOOK like the refused path prevented nothing while causing real harm: the
    # normalising version silently deleted a legitimately-exported descriptor's evidence,
    # and silent deletion of authored content is its own honesty defect.
    #
    # The invariant that matters is on the OFFICIAL RECORD, which is schema-validated and
    # is what asserts a server-stamped identity: see `_enforce_server_owned_invariant`.
    #
    # BE EXACT ABOUT WHAT IS THEREFORE POSSIBLE, because a draft of this very note said the
    # sidecar could only name the field via a draft that never exports, and that was FALSE —
    # `validate_draft` refuses the RECORD-bound spellings (the `attribution` block and the
    # `fields` map), not `implicit[].about`. So an exporting draft CAN produce a sidecar
    # entry naming `attribution.uploaded_by`, carrying a value. That is accepted, not
    # overlooked: the sidecar makes no authentication claim, and the same author can write
    # the same name under any key they like. `tests/test_attribution_uploaded_by.py` pins
    # this as a deliberate non-guarantee so it cannot be mistaken later for an oversight.
    return {
        "record_id": record["record_id"],
        "schema_version": ISAAC_VERSION,
        "generated_utc": _now_iso(),
        "evidence": ev,
    }


@dataclass
class ExportResult:
    ok: bool
    record: dict | None
    sidecar: dict | None
    draft_report: DraftReport
    official_report: OfficialReport | None


def export_draft(
    draft: dict,
    root: Path,
    *,
    record_id: str | None = None,
    now: str | None = None,
) -> ExportResult:
    draft_report = validate_draft(draft)
    if record_id is not None and not is_record_id(record_id):
        # The message must NOT quote `^[0-9A-Z]{26}$` as the rule it applied. That was
        # the old text, and it was false in the one case that matters most: for
        # `"A"*26 + "\n"` the quoted pattern MATCHES in Python (`$` also matches before a
        # trailing newline), so the operator was handed a refusal justified by a rule
        # that, checked as written, accepts their value. On a defect whose whole subject
        # is "`$` is not what you think", an error message asserting the wrong rule is
        # the same defect in prose.
        #
        # `is_record_id` is the authority for what was actually applied; the message now
        # describes the requirement in words instead of quoting a regex whose flavour is
        # the thing in question. `describe_characters` names any control character rather
        # than echoing it — `repr()` alone would render a raw newline into the terminal.
        detail = ""
        if isinstance(record_id, str):
            lead = record_id[: len(record_id) - len(record_id.lstrip())]
            trail = record_id[len(record_id.rstrip()):]
            if lead or trail:
                detail = (
                    " It carries surrounding whitespace or control characters: "
                    f"{describe_characters(lead + trail)}."
                )
        draft_report.err(
            "record_id",
            f"{record_id!r} is not a valid ULID: exactly 26 characters, each of them "
            f"an uppercase letter A-Z or a digit 0-9, and nothing before or after "
            f"them.{detail}",
        )
    if not draft_report.ok:
        return ExportResult(False, None, None, draft_report, None)

    record = transform(draft, record_id=record_id, now=now)

    # EXACTNESS, on the ASSEMBLED RECORD, before official validation.
    #
    # The five anchored `pattern` gates in the vendored schema accept one value each
    # that they visibly intend to refuse, because Python's `$` also matches before a
    # trailing newline (see `exactness.py` for the measured table and the cause, which
    # is NOT the search-vs-match difference people usually reach for). `tags` is the
    # clearest: `transform` above copies it verbatim — `list(draft["tags"])`, no
    # normalisation anywhere in this module or in `draft_validator` — so `"campaign\n"`
    # went in at the draft and came out in an official record that then validated PASS.
    #
    # CHECKED ON THE OUTPUT, NOT ON THE DRAFT, for the reason
    # `_enforce_server_owned_invariant` records at length: `transform` writes strings
    # into the record from several independent places (the `fields` loop's `set_path` to
    # an arbitrary dotted path, the verbatim `tags` copy, `strip_evidence` over `links`,
    # `attribution` and `descriptors_outputs`), and guarding writers one at a time loses
    # to whichever one you did not think of. Guarding the output does not.
    #
    # BEFORE `validate_official`, so the refusal names the real problem. Run after, a
    # newline-bearing record would validate clean and the operator would be told PASS by
    # one gate and refused by another in the same breath.
    #
    # REFUSED, NEVER STRIPPED — `CLAUDE.md` §5. Trimming the value would hand back a
    # record the author did not write, and a silent repair of scientific metadata is the
    # exact failure the no-guessing policy exists to prevent.
    #
    # Reported through `draft_report` rather than through a new `ExportResult` field:
    # the offending value ORIGINATES in the draft, every existing caller already renders
    # `draft_report` on failure (`cli.py`'s "Draft validation failed — nothing exported",
    # the API's export route), and adding a field would leave those callers silently
    # dropping the only explanation of the refusal.
    exactness_report = check_exactness(record, root)
    if not exactness_report.ok:
        for err in exactness_report.errors:
            draft_report.err(err.path, err.message)
        return ExportResult(False, record, None, draft_report, None)

    official_report = validate_official(record, root)
    if not official_report.ok:
        return ExportResult(False, record, None, draft_report, official_report)

    sidecar = build_sidecar(draft, record)
    return ExportResult(True, record, sidecar, draft_report, official_report)
