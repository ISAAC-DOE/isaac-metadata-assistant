"""Apply simulated human answers to a draft's ``pending[]`` blockers.

This is a NON-truth authoring module: it turns a draft with open ``pending``
blockers (from :func:`isaac_records.extract.draft_builder.build_draft`) into a
completed draft that the existing, unchanged export/validate machinery can carry
to an official record. It decides nothing about validity or exportability — that
stays with ``draft_validator`` / ``official`` / ``export`` (the truth plane).

Hard rule — NO GUESSING BY THE SYSTEM: :func:`apply_answers` may only apply values
that are literally present in the ``answers`` mapping (which represents simulated
human answers). It never invents a value, sha256, spectrum point, or descriptor on
its own. Every applied answer is recorded as ``user_confirmation`` evidence, added
alongside (never replacing) the deterministic evidence the draft already carries.
An unanswered blocker is left in ``pending`` and therefore keeps blocking export.

The module imports nothing but ``copy`` (stdlib): no graphify, no truth-plane code.
"""

from __future__ import annotations

import copy
import re

# A well-formed sha256 answer: 64 lowercase hex chars (mirrors draft_validator).
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# The official measurement.qc.status enum — a qc answer outside this set is rejected.
_QC_STATUSES = {"valid", "compromised", "failed", "pending"}

# A stable ``asset_id`` per ``content_role``. The ``pending`` asset blockers carry
# a ``content_role`` but no ``asset_id`` (build_draft drops the parser's implied id),
# so completion derives a deterministic, human-readable id from the role. Anything
# not in this map falls back to the role string itself (still deterministic).
_ASSET_ID_BY_ROLE = {
    "raw_data_pointer": "raw_scan_set",
    "reduction_product": "reduced_spectrum",
    "processing_script": "processing_notebook",
}


def _user_confirmation(question, answer, timestamp) -> dict:
    """One ``user_confirmation`` evidence entry recording a simulated human answer."""
    return {
        "source_type": "user_confirmation",
        "question": question,
        "answer": answer,
        "timestamp": timestamp,
    }


def apply_answers(draft: dict, answers: dict) -> dict:
    """Return a NEW completed draft with ``answers`` applied to ``draft['pending']``.

    Pure and non-mutating: deep-copies ``draft`` and only ever adds values that are
    present in ``answers``. Resolved ``pending`` entries are removed; unanswered ones
    are kept so export stays blocked. See the module docstring for the no-guessing
    contract.
    """
    draft = copy.deepcopy(draft)
    answers = answers or {}
    timestamp = answers.get("timestamp")
    asset_sha256 = answers.get("asset_sha256") or {}

    draft.setdefault("assets", [])
    remaining_pending: list[dict] = []

    for entry in draft.get("pending") or []:
        kind = entry.get("kind")

        if kind == "asset":
            uri = entry.get("uri")
            sha256 = asset_sha256.get(uri)
            if sha256 is None or not _SHA256_RE.match(str(sha256)):
                # No answer OR a malformed sha256 -> NOT applied. The blocker stays
                # pending (still blocks export) and the bad value is never written into
                # the draft. Same visible signal as an unanswered blocker, by design.
                remaining_pending.append(entry)
                continue
            content_role = entry.get("content_role")
            asset = {
                "asset_id": _ASSET_ID_BY_ROLE.get(content_role, content_role),
                "content_role": content_role,
                "uri": uri,
                "media_type": entry.get("media_type"),
                "sha256": sha256,
                # file_listing evidence (from the blocker) + the simulated answer.
                "evidence": list(entry.get("evidence") or [])
                + [_user_confirmation(entry.get("question"), sha256, timestamp)],
            }
            if asset["media_type"] is None:
                del asset["media_type"]  # never emit a null media_type
            draft["assets"].append(asset)
            # resolved -> not re-added to pending
            continue

        if kind == "series":
            series = answers.get("series")
            # TYPE-GUARDED, like `qc` below. Without the isinstance check a caller who
            # sends a STRING here reaches `s.get("series_id")` a few lines down, where
            # iterating the string yields characters and `.get` raises AttributeError —
            # surfacing as an HTTP 500 from POST /api/experiments/{id}/answers. A
            # wrong-typed answer must never crash the truth core; it follows the same
            # "not applied -> stays pending" rule an off-enum qc verdict already does,
            # so nothing is invented and nothing is silently written.
            if not is_series_shaped(series):
                remaining_pending.append(entry)
                continue
            draft["series"] = copy.deepcopy(series)
            # Record the human confirmation as block_evidence, keyed per series_id
            # (the official measurement.series has no per-series evidence slot).
            block_evidence = draft.setdefault("block_evidence", {})
            for s in draft["series"]:
                series_id = s.get("series_id")
                if series_id is None:
                    continue
                block_evidence[f"series:{series_id}"] = [
                    _user_confirmation(entry.get("question"), series_id, timestamp)
                ]
            # qc stays exactly as build_draft read it from the sheet.
            continue

        if kind == "qc":
            qc_answer = answers.get("qc")
            status = qc_answer.get("status") if isinstance(qc_answer, dict) else None
            if status not in _QC_STATUSES:
                # No answer OR an off-enum verdict -> NOT applied; stays pending. The
                # system never invents a qc status (no default 'valid').
                remaining_pending.append(entry)
                continue
            qc = draft.setdefault("qc", {})
            qc["status"] = status
            evidence_note = qc_answer.get("evidence")
            if evidence_note:
                # Native measurement.qc.evidence is a free-text string field.
                qc["evidence"] = evidence_note
            block_evidence = draft.setdefault("block_evidence", {})
            block_evidence.setdefault("qc:status", []).append(
                _user_confirmation(entry.get("question"), status, timestamp)
            )
            continue

        if kind == "descriptor":
            descriptor = answers.get("descriptor")
            # Same guard, same reason: `desc["evidence"] = [...]` two lines down raises
            # TypeError on a str ("does not support item assignment"), which also
            # surfaced as a 500. Only a mapping can carry a descriptor value.
            if not is_descriptor_shaped(descriptor):
                remaining_pending.append(entry)
                continue
            desc = copy.deepcopy(descriptor)
            desc["evidence"] = [
                _user_confirmation(
                    "Descriptor value + uncertainty?",
                    str(desc.get("value")),
                    timestamp,
                )
            ]
            draft["descriptors_outputs"] = [
                {
                    "label": answers.get("descriptor_label", "completion_demo"),
                    "generated_utc": timestamp,
                    "generated_by": {"agent": "isaac-complete-demo", "version": "0.1"},
                    "descriptors": [desc],
                }
            ]
            continue

        # Unknown blocker kind: leave it untouched (never silently dropped).
        remaining_pending.append(entry)

    draft["pending"] = remaining_pending

    # Optional edge confirmation. The edge lives in implicit[] as a null
    # needs-confirmation candidate (not a pending blocker); if the answer supplies
    # it, record the confirmed value and append user_confirmation evidence while
    # keeping the original derivation note.
    edge = answers.get("edge")
    if edge is not None:
        for imp in draft.get("implicit") or []:
            if imp.get("about") == "edge":
                imp["value"] = edge
                imp.setdefault("evidence", [])
                imp["evidence"].append(
                    _user_confirmation(
                        "What is the absorption edge (e.g. K, L3)?", edge, timestamp
                    )
                )

    return draft


#: A ``series_id`` must be one of these, or absent. It is used as a DICT KEY by
#: ``draft_validator`` (``if series_id in seen_series``), so an unhashable one raises
#: ``TypeError`` there — and by then the value has been written, which wedges the record:
#: every subsequent read 500s, so the caller cannot even obtain the ETag needed to correct
#: it. Measured on ``[{"series_id": {"a": 1}, "mu": 0.1}]``.
_HASHABLE_SERIES_ID = (str, int, float, bool)


def is_series_shaped(value) -> bool:
    """Can ``apply_corrections`` and ``apply_answers`` actually STORE this series?

    THE FIRST VERSION OF THIS ANSWERED A WEAKER QUESTION THAN ITS NAME, and a reviewer
    showed the gap was not academic. It tested "list of mappings" and nothing about what
    the mappings contain, so two shapes still got through:

    * ``[{"series_id": {"a": 1}, …}]`` — a list of dicts, so admitted, written, and then
      ``TypeError: unhashable type: 'dict'`` out of ``draft_validator``. The record is
      left permanently unreadable.
    * ``[]`` — ``all()`` over an empty list is vacuously true, so an empty correction was
      admitted. That DESTROYED an already-confirmed spectrum, ``validate`` then reported
      ``ok: true``, and an official record was EXPORTED with ``measurement.series: []``,
      which the schema permits because it declares no ``minItems``. That is the exact harm
      the previous commit called "worse than the crash" — refused for ``{}`` and admitted
      for ``[]``, one line of reasoning apart.

    So an empty series is refused here. Deleting a confirmed measurement is not a
    correction, and if it is ever wanted it should be an explicit act with its own name,
    not the by-product of sending an empty list to an overwrite route.

    EXPORTED, not private: the route imports this rather than restating it. The previous
    version had a copy in ``routes.py`` under a docstring that said it "mirrors the guards
    … rather than restating them loosely" — copying IS restating, and it created the
    second definition the comment warned about.
    """
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        series_id = item.get("series_id")
        if series_id is not None and not isinstance(series_id, _HASHABLE_SERIES_ID):
            return False
    return True


def is_sha256_shaped(value) -> bool:
    """Is this a sha256 the asset paths will actually STORE — 64 lowercase hex chars?

    EXPORTED FOR THE SAME REASON THE OTHER TWO ARE, and added because a reviewer found
    the gap they left. ``routes.py``'s ``/edit`` guard asked only ``isinstance(value,
    str)`` of an asset sha, so a malformed one — ``"Z" * 64``, ``"abc"``, 63 or 65 hex
    chars — passed the guard, was then declined by :func:`apply_corrections` for being
    malformed, and the route answered **200 having changed nothing**. Measured: 200,
    ``rev`` unmoved, nothing written.

    That is precisely the outcome the ``/edit`` route's own comment calls forbidden. It
    was closed for ``series`` and ``descriptor``, where malformation is a question of
    TYPE, and left open here, where it is a question of FORMAT.

    ``_SHA256_RE`` rather than a second pattern: the route imports this so there is one
    definition of "a storable hash", exactly as ``is_series_shaped`` exists so the route
    does not carry a copy of the series rule.

    Note what this deliberately does NOT do: re-sending the SAME valid hash still
    answers 200 with nothing changed, and that is correct — the value was usable, and
    the byte-stable no-op is documented behaviour. The defect was answering 200 about a
    value that could never be stored at all.
    """
    return isinstance(value, str) and bool(_SHA256_RE.match(value))


def is_descriptor_shaped(value) -> bool:
    """Can a descriptor correction be stored — a NON-EMPTY mapping?

    ``{}`` is refused for the same reason ``[]`` is. Measured: it destroyed a confirmed
    descriptor AND appended an evidence entry reading ``"answer": "None"`` — a recorded
    human confirmation of a value that does not exist, which is a `CLAUDE.md` §5
    violation in the evidence trail itself.
    """
    return isinstance(value, dict) and bool(value)


def apply_corrections(draft: dict, answers: dict) -> dict:
    """Return a NEW draft with ``answers`` OVERWRITING already-confirmed values.

    The edit / re-confirm counterpart to :func:`apply_answers`. Where
    ``apply_answers`` only FILLS open ``pending[]`` blockers, this overwrites the
    CURRENT value of a field that was already answered (even when ``pending`` is
    empty), recording a FRESH ``user_confirmation`` evidence entry for each
    corrected field. It NEVER touches ``pending`` (blocker resolution stays with
    ``apply_answers``) — it only mutates values that already exist / are supplied.

    Same NO-GUESSING contract as ``apply_answers``: it applies ONLY values that are
    literally present in ``answers``. A malformed sha256 or an off-enum qc verdict
    is rejected (the current value is left untouched — never overwritten with a bad
    value, never invented). An unrecognized key writes nothing. Pure and
    non-mutating (deep-copies ``draft``); imports nothing but stdlib.

    Accepts the SAME ``apply_answers`` input shape (produced by the route's
    ``_answers_to_apply_shape``): ``asset_sha256`` (``{uri: sha}``), ``series``,
    ``descriptor`` / ``descriptor_label``, ``edge``, ``qc``.
    """
    draft = copy.deepcopy(draft)
    answers = answers or {}
    timestamp = answers.get("timestamp")

    # Each branch guards on an EQUALITY check first: an identical re-confirm changes
    # NOTHING (no overwrite, no fresh evidence, no wrapper-timestamp churn), so the
    # authoritative draft signature stays byte-stable and save_versioned reports a
    # no-op. A correction is applied only when the submitted value actually differs.

    # -- asset sha256: overwrite the matching EXISTING asset's hash --
    asset_sha256 = answers.get("asset_sha256") or {}
    for asset in draft.get("assets") or []:
        uri = asset.get("uri")
        sha256 = asset_sha256.get(uri)
        if sha256 is None or not _SHA256_RE.match(str(sha256)):
            # No answer for this uri, or a malformed sha256 -> not applied; the
            # current value stays untouched (never overwritten with a bad value).
            continue
        if sha256 == asset.get("sha256"):
            continue  # identical -> byte-stable no-op
        asset["sha256"] = sha256
        asset.setdefault("evidence", [])
        asset["evidence"].append(
            _user_confirmation(f"Correct the sha256 of {uri}?", sha256, timestamp)
        )

    # -- series: overwrite the whole series block + refresh its block_evidence --
    series = answers.get("series")
    #
    # THE SAME TYPE GUARD `apply_answers` HAS AT :105, AND ITS ABSENCE HERE WAS TWO
    # DEFECTS RATHER THAN ONE. `apply_answers` was hardened when a wrong-typed answer
    # was found to crash the truth core; `apply_corrections` — the `POST /edit` path —
    # was not, and nothing tested it (`tests/test_answers_wrong_type.py` contains no
    # `/edit` reference). Measured on the un-guarded code:
    #
    #   series = 5 / "nope" / [1, 2] / a 1 MB string  ->  HTTP 500
    #       `AttributeError: 'str' object has no attribute 'get'` from the loop below,
    #       raised AFTER the assignment, so the write is attempted and the caller is
    #       told the request failed.
    #   series = {}                                   ->  HTTP 200, AND WORSE
    #       a dict passes `is not None`, the loop iterates its (zero) keys without
    #       raising, and `draft["series"]` is left as `{}` — a dict where the official
    #       schema requires a list, with a scientist's already-confirmed series
    #       DESTROYED and a 200 reported. Silent loss of a confirmed value is worse
    #       than the crash, because nothing anywhere says it happened.
    #
    # A malformed correction is therefore not applied at all. That matches
    # `apply_answers`' rule and `CLAUDE.md` §5: a value the core cannot shape is left
    # alone rather than guessed into place. The ROUTE turns this into a typed refusal so
    # the caller is not told 200 about a no-op — this function's job is only to refuse to
    # corrupt.
    if series is not None and not is_series_shaped(series):
        series = None
    if series is not None and series != draft.get("series"):
        draft["series"] = copy.deepcopy(series)
        block_evidence = draft.setdefault("block_evidence", {})
        for s in draft["series"]:
            series_id = s.get("series_id")
            if series_id is None:
                continue
            block_evidence[f"series:{series_id}"] = [
                _user_confirmation("Correct the reduced series?", series_id, timestamp)
            ]

    # -- descriptor: overwrite the descriptor output block --
    descriptor = answers.get("descriptor")
    # The mirror of the `series` guard above, and of `apply_answers` at :147: only a
    # mapping can carry a descriptor value, and a non-mapping raised a `TypeError` here
    # for the same reason it did there.
    if descriptor is not None and not is_descriptor_shaped(descriptor):
        descriptor = None
    if descriptor is not None:
        outputs = draft.get("descriptors_outputs") or []
        current_core = None
        if outputs and (outputs[0].get("descriptors") or []):
            current_core = {
                k: v for k, v in outputs[0]["descriptors"][0].items() if k != "evidence"
            }
        if descriptor != current_core:  # only rebuild on a real content change
            desc = copy.deepcopy(descriptor)
            desc["evidence"] = [
                _user_confirmation(
                    "Correct the descriptor value + uncertainty?",
                    str(desc.get("value")),
                    timestamp,
                )
            ]
            draft["descriptors_outputs"] = [
                {
                    "label": answers.get("descriptor_label", "completion_demo"),
                    "generated_utc": timestamp,
                    "generated_by": {"agent": "isaac-complete-demo", "version": "0.1"},
                    "descriptors": [desc],
                }
            ]

    # -- qc: overwrite the qc status (rejecting an off-enum verdict) --
    qc_answer = answers.get("qc")
    if isinstance(qc_answer, dict):
        status = qc_answer.get("status")
        if status in _QC_STATUSES and status != (draft.get("qc") or {}).get("status"):
            qc = draft.setdefault("qc", {})
            qc["status"] = status
            evidence_note = qc_answer.get("evidence")
            if evidence_note:
                qc["evidence"] = evidence_note
            block_evidence = draft.setdefault("block_evidence", {})
            block_evidence.setdefault("qc:status", []).append(
                _user_confirmation("Correct the QC status?", status, timestamp)
            )

    # -- edge: overwrite the implicit edge value + append confirmation --
    edge = answers.get("edge")
    if edge is not None:
        for imp in draft.get("implicit") or []:
            if imp.get("about") == "edge" and imp.get("value") != edge:
                imp["value"] = edge
                imp.setdefault("evidence", [])
                imp["evidence"].append(
                    _user_confirmation(
                        "Correct the absorption edge (e.g. K, L3)?", edge, timestamp
                    )
                )

    return draft


__all__ = ["apply_answers", "apply_corrections"]
