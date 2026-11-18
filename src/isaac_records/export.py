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

#: Field-envelope statuses whose value never enters the record or the sidecar, whatever it
#: carries: ``missing`` (nothing is known) and ``rejected`` (a person turned the value down).
#: ``needs_confirmation`` is not here: it is an open question, and ``export_draft`` refuses it.
DROPPED_STATUSES = ("missing", "rejected")


def rejected_paths(draft: dict) -> list[str]:
    """Every `fields` path whose envelope is ``rejected``, with or without a value, in draft order."""
    fields = draft.get("fields")
    if not isinstance(fields, dict):
        return []
    return [p for p, env in fields.items() if isinstance(env, dict) and env.get("status") == "rejected"]


def _within(path: str, roots) -> str | None:
    """The rejected root that `path` is, or lies under (dotted), if any."""
    for root in roots:
        if path == root or path.startswith(root + "."):
            return root
    return None


def _remove_rejected_paths(record: dict, rejected: list[str]) -> list[str]:
    """Remove every rejected path from the composed record; return the paths actually removed.

    A REJECT IS ON THE PATH, NOT ON ONE WRITER (review of the reject fix, MEDIUM). Skipping the
    rejected envelope in the `fields` loop was not enough: a non-rejected PARENT envelope
    (`fields["system.facility"]` holding the whole object) or a structured block writes the same
    path a second way, and the turned-down value went out while the export warned it had been
    left out. So, as `_enforce_server_owned_invariant` does for its field, the rule is applied
    to the OUTPUT, after every writer: nothing is exported at or under a rejected path. This
    covers the reverse overlap too: a verified child under a rejected parent goes with it (and
    `export_draft` says so). If the removal leaves the record schema-invalid, official
    validation refuses it, honestly, for the missing property.

    Copy-on-write along the path, never an in-place delete: `set_path` writes by reference, so a
    nested dict here may BE the caller's draft (see `_enforce_server_owned_invariant`)."""
    removed: list[str] = []
    for path in rejected:
        if not get_path(record, path)[1]:
            continue
        parts = path.split(".")
        node = record
        for part in parts[:-1]:
            node[part] = dict(node[part])
            node = node[part]
        del node[parts[-1]]
        removed.append(path)
    return removed


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


def _write_not_reported_temperature(record: dict, draft: dict) -> None:
    """Write ``context.temperature_K: null`` when, and only when, the record states
    ``context.temperature_basis: "not_reported"`` and carries no ``temperature_K`` at all.

    The schema vendored on 2026-11-16 REQUIRES ``context.temperature_K`` and makes it
    ``number | null``, with a ``context.allOf`` rule tying the two together: null only with
    basis ``not_reported``, and basis ``not_reported`` only with null. The ``fields`` loop
    skips a null or ``status: missing`` envelope, so without this a draft whose evidenced
    answer is "the source does not state the temperature" exported a record with NO
    ``temperature_K`` and was refused for a missing required property — reporting the
    stated absence as an unanswered question.

    This is the schema's own rule, not a guess: null asserts no value, and it is written only
    for the one basis that means "not stated". Nothing is defaulted. A draft that holds a
    number AND ``not_reported`` keeps its number, and official validation refuses the
    contradiction; a null temperature WITHOUT that basis is never written here, so the
    schema still refuses it (or reports the missing property) exactly as before.

    AN OPEN QUESTION STAYS OPEN (review of #323, LOW 1). The null is written only when the
    draft's own ``context.temperature_K`` envelope is absent or ``status: missing``. A
    ``needs_confirmation`` (or any other) envelope is a question nobody has answered, and an
    evidenced basis elsewhere must not close it: the record then has no ``temperature_K`` and
    the schema refuses the export for the missing required property."""
    context = record.get("context")
    if not isinstance(context, dict):
        return
    env = (draft.get("fields") or {}).get("context.temperature_K")
    if env is not None and not (isinstance(env, dict) and env.get("status") == "missing"):
        return
    if context.get("temperature_basis") == "not_reported" and "temperature_K" not in context:
        # A copy, not an in-place write: under the whole-block spelling
        # (`fields["context"] = {"value": {...}}`) `record["context"]` IS the draft's own dict,
        # and `transform` must stay side-effect free (see `_enforce_server_owned_invariant`).
        record["context"] = {**context, "temperature_K": None}


def transform(draft: dict, *, record_id: str | None = None, now: str | None = None) -> dict:
    """Build the official-shape record from a draft (no validation here)."""
    return _compose(draft, record_id=record_id, now=now)[0]


def _compose(draft: dict, *, record_id: str | None, now: str | None) -> tuple[dict, list[str]]:
    """`transform`, plus the rejected paths it removed from the record (for `export_draft`'s
    warnings, which must describe what actually happened)."""
    now = now or _now_iso()
    meta = draft.get("meta") or {}
    record: dict = {
        "isaac_record_version": ISAAC_VERSION,
        "record_id": record_id or new_record_id(),
    }
    for key in ("record_type", "record_domain", "source_type"):
        if meta.get(key) is not None:
            record[key] = meta[key]

    # Scalar fields: drop the envelope, keep the value. Skip honestly-missing fields, and
    # REJECTED ones: a reject says "nothing goes in this field", so a value it still carries
    # (the one a person turned down, kept as the draft's history) is never written. The field
    # is then absent, exactly as a `missing` one is, so a field the schema requires refuses
    # the export for the missing property: a reject never satisfies a required field.
    for path, env in (draft.get("fields") or {}).items():
        if not isinstance(env, dict):
            continue
        if env.get("status") in DROPPED_STATUSES or env.get("value") is None:
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
        block = strip_evidence(draft["attribution"])
        existing = record.get("attribution")
        # MERGE, NOT REPLACE, since the 2026-11-16 schema declares `attribution.produced_by`:
        # the `fields` loop above writes `attribution.produced_by.*` envelopes into
        # `record["attribution"]`, and assigning the block over it silently DROPPED them from
        # any draft that also carried contributors. Block keys win on a collision, which is
        # the previous behaviour for every key the block holds. (`validate_draft` refuses
        # `produced_by` inside the block, so the two spellings do not meet there.)
        if isinstance(existing, dict) and isinstance(block, dict):
            record["attribution"] = {**existing, **block}
        else:
            record["attribution"] = block
    _write_not_reported_temperature(record, draft)
    if draft.get("tags"):
        record["tags"] = list(draft["tags"])

    removed = _remove_rejected_paths(record, rejected_paths(draft))
    _enforce_server_owned_invariant(record)
    return record, removed


def build_sidecar(draft: dict, record: dict) -> dict:
    """Evidence map keyed by official JSON-path / asset / descriptor / implicit."""
    ev: dict = {}
    for path, env in (draft.get("fields") or {}).items():
        # Exactly the envelopes `transform` writes: a rejected value is not in the record, so
        # its evidence is not cited for that path.
        if (isinstance(env, dict) and env.get("evidence") and env.get("value") is not None
                and env.get("status") not in DROPPED_STATUSES):
            ev[path] = env["evidence"]
    for asset in draft.get("assets") or []:
        if asset.get("evidence"):
            ev[f"assets:{asset.get('asset_id', asset.get('uri', '?'))}"] = asset["evidence"]
    for out in draft.get("descriptors_outputs") or []:
        for d in out.get("descriptors") or []:
            if d.get("evidence"):
                ev[f"descriptors:{d.get('name', '?')}"] = d["evidence"]
    rejected = rejected_paths(draft)
    for imp in draft.get("implicit") or []:
        entry = {"value": imp.get("value"), "evidence": imp.get("evidence", [])}
        # AN IMPLICIT ENTRY ABOUT A REJECTED PATH IS KEPT, MARKED (review of the reject fix,
        # LOW). `implicit` is sidecar-only by design: it never claims to be a record value,
        # sits in its own `implicit:` namespace, and the audit treats it as informational.
        # Dropping it would silently delete authored content (the defect the note below
        # records), and matching `about` text is no boundary anyway. What it must not do is
        # read as an unqualified claim beside a decision that turned the value down, so it
        # says the path was rejected and the value is not in the record.
        root = _within(str(imp.get("about")), rejected)
        if root is not None:
            entry["status"] = "rejected"
            entry["note"] = f"fields.{root} is rejected: this value is not in the record"
        ev[f"implicit:{imp.get('about', '?')}"] = entry
    # Block-level provenance (series/qc/links/attribution natural keys) passes through
    # verbatim.
    for key, entries in (draft.get("block_evidence") or {}).items():
        ev[key] = entries
    # A BARE DOTTED KEY AT OR UNDER A REJECTED PATH IS NOT CITED, whichever map filed it (review
    # of the reject fix, LOW). Unlike `implicit:`, a key without a namespace IS the record-path
    # namespace: the sidecar's convention, the audit and the evidence trail all read it as
    # "evidence for the record's value at this path", resolving that value from the record. A
    # `block_evidence` key spelled as the rejected path therefore re-cited the very evidence the
    # `fields` loop above declines to cite, for a value the record does not hold; and a verified
    # child under a rejected parent is no longer in the record either. This is exact matching on
    # the sidecar's own keys against the draft's own rejected paths, not the free-text denylist
    # the note below warns against, and `export_draft` warns for each key left out.
    for key in [k for k in ev if ":" not in k and _within(k, rejected) is not None]:
        del ev[key]
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


def _report_rejected(draft: dict, record: dict, removed: list[str], report: DraftReport) -> None:
    """Say what each reject did to THIS record, checked against the record itself.

    Not an error: a reject is a decision, and `_compose` honours it by leaving the path out.
    Said, so the omission (and any missing-required refusal it causes) is never silent. Each
    "left out" is stated only after `get_path` confirms the path is absent from the composed
    record; a rejected path still present would be a defect in `_remove_rejected_paths`, and it
    refuses the export rather than being reported as left out."""
    rejected = rejected_paths(draft)
    if not rejected:
        return
    fields = draft["fields"]
    for path in rejected:
        if get_path(record, path)[1]:
            report.err(f"fields.{path}", "status 'rejected', but a value is still in the composed record")
        elif path in removed:
            report.warn(f"fields.{path}", "status 'rejected': left out of the exported record, including "
                        "the value an enclosing field or block placed at this path")
        elif fields[path].get("value") is not None:
            report.warn(f"fields.{path}", "status 'rejected': its value is left out of the exported record")
    for path, env in fields.items():
        root = _within(path, rejected)
        if (root is None or root == path or not isinstance(env, dict)
                or env.get("status") in DROPPED_STATUSES or env.get("value") is None):
            continue
        if not get_path(record, path)[1]:
            report.warn(f"fields.{path}", f"left out of the exported record: it lies inside "
                        f"'{root}', which is rejected")
    for imp in draft.get("implicit") or []:
        root = _within(str(imp.get("about")), rejected) if isinstance(imp, dict) else None
        if root is not None:
            report.warn("implicit", f"the entry about '{imp.get('about')}' names rejected field "
                        f"'{root}': kept in the evidence sidecar marked rejected, never in the record")
    for key in draft.get("block_evidence") or {}:
        root = _within(key, rejected) if ":" not in key else None
        if root is not None:
            report.warn(f"block_evidence.{key}", f"names rejected field '{root}': not cited in the "
                        "evidence sidecar")


def export_draft(
    draft: dict,
    root: Path,
    *,
    record_id: str | None = None,
    now: str | None = None,
) -> ExportResult:
    draft_report = validate_draft(draft)
    # AN OPEN QUESTION IS NEVER EXPORTED (CLAUDE.md §5). `validate_draft` accepts a
    # `needs_confirmation` envelope (it is a legitimate DRAFT state), and `transform` writes
    # every non-null value regardless of status, so an unconfirmed, unevidenced value went
    # into an official record. Refused here, at export only, so drafts in progress are
    # reported exactly as before. Predates the 2026-11-16 schema re-vendoring.
    for path, env in (draft.get("fields") or {}).items() if isinstance(draft.get("fields"), dict) else ():
        if isinstance(env, dict) and env.get("status") == "needs_confirmation":
            draft_report.err(
                f"fields.{path}",
                "status 'needs_confirmation' is an open question: confirm the value with its "
                "evidence, or mark it missing, before export",
            )
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

    record, removed = _compose(draft, record_id=record_id, now=now)
    _report_rejected(draft, record, removed, draft_report)
    if not draft_report.ok:
        return ExportResult(False, record, None, draft_report, None)

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
