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

# A well-formed sha256 answer: 64 lowercase hex chars — and EXACTLY 64, which the
# previous pattern did not enforce.
#
# It was `r"^[0-9a-f]{64}$"`, and in Python `$` also matches immediately BEFORE a
# trailing newline. So a 65-character string — `"9" * 64 + "\n"` — matched, and the
# consequence was measured end to end over the app's own HTTP surface (a local
# `TestClient` against the seeded worked-example corpus — NOT the deployed pod, which
# this environment cannot reach): `POST /edit` answered 200, `rev` advanced, the value
# was STORED as `'999…9\n'`, `POST /validate` then reported `ok: true`, and
# `POST /export` produced an official record whose `official_report.ok` was `true`. A
# sha256 that is not a sha256 reached an exported official ISAAC record. Nothing
# downstream could catch it: the official schema declares `sha256: {"type": "string"}`
# with NO `pattern`.
#
# `\A` / `\Z` rather than `^` / `$` because this module reaches the pattern through
# `.match()` in two places as well as through `is_sha256_shaped`; anchoring the PATTERN
# makes every one of them exact, instead of leaving the correctness of each call site to
# depend on which method it happens to use. (Python's `\Z` is the absolute end of the
# string — it is not Perl's `\Z`.)
#
# `draft_validator._SHA256_RE` still carries the `$` form. That file is a `CLAUDE.md` §13
# truth-path file and is deliberately NOT touched here; the quirk there is reported for
# its own reviewed slice.
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")

#: WHAT A DESCRIPTOR OUTPUT GROUP SAYS ABOUT ITS OWN ORIGIN, when a PERSON supplied it.
#:
#: These two constants used to read ``"completion_demo"`` and
#: ``{"agent": "isaac-complete-demo", "version": "0.1"}``, and they were written into
#: every record this application completed — including a record a scientist created and
#: filled in by hand. Measured on an ordinary record before this change::
#:
#:     "label": "completion_demo",
#:     "generated_by": {"agent": "isaac-complete-demo", "version": "0.1"}
#:
#: The schema says ``generated_by`` is *"Tool/pipeline/person that generated these
#: descriptors"*, so that record asserted a demo agent had generated the scientist's
#: descriptor. It is fabricated provenance in an exported official record, which is the
#: one place this project is least willing to have any.
#:
#: WHAT IS SAID INSTEAD, and why each part is true rather than merely nicer:
#:
#: * ``agent`` names THIS APPLICATION, which did assemble the output group. It does not
#:   claim to have computed anything — ``notes`` says who did.
#: * ``notes`` says a person supplied the value. That is checkable: this dict is only
#:   ever written on a path that requires ``confirmed_by_user`` and writes a
#:   ``user_confirmation`` evidence entry beside it.
#: * ``version`` is OMITTED. It is optional in the schema, and ``"0.1"`` was the demo's
#:   number; carrying a version this build cannot vouch for would be a smaller version
#:   of the same defect.
#: * ``author`` is OMITTED, and that is the honest gap rather than an oversight. It
#:   would name the person, and this application cannot name anybody until a trusted
#:   authentication boundary exists (E1) — see ``isaac_api.record_attribution``.
#:
#: ``label`` remains overridable by ``answers["descriptor_label"]``; only the DEFAULT
#: changed. A caller that knows the real provenance still supplies it.
DESCRIPTOR_OUTPUT_LABEL = "user_supplied"
DESCRIPTOR_GENERATED_BY: dict = {
    "agent": "isaac-metadata-assistant",
    "notes": (
        "Supplied and confirmed by a person through the assistant's completion flow. "
        "No tool computed this value."
    ),
}

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
            if not is_qc_shaped(qc_answer):
                # No answer, an off-enum verdict, or a note of the wrong type -> NOT
                # applied; stays pending. The system never invents a qc status (no
                # default 'valid'). `is_qc_shaped` rather than an inline enum test so
                # the route and this branch cannot disagree about what is storable, and
                # so an unhashable verdict raises nothing here.
                remaining_pending.append(entry)
                continue
            status = qc_answer["status"]
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
                    "label": answers.get("descriptor_label", DESCRIPTOR_OUTPUT_LABEL),
                    "generated_utc": timestamp,
                    "generated_by": dict(DESCRIPTOR_GENERATED_BY),
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

    ``fullmatch``, and the docstring above is the reason. The first version of this
    predicate used ``.match`` against a ``$``-anchored pattern and therefore accepted a
    **65-character** string, ``"9" * 64 + "\\n"``, while claiming "64 lowercase hex
    chars". The pattern is now anchored with ``\\A``/``\\Z`` as well, so both defences
    are in place and neither call site depends on the other being right. See the
    ``_SHA256_RE`` comment for the measured end-to-end consequence.
    """
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def is_qc_shaped(value) -> bool:
    """Can a QC answer be stored — a mapping naming a verdict from the official enum?

    EXPORTED FOR THE SAME REASON THE OTHER THREE ARE: ``routes.py`` needs to know
    whether a value the caller sent can actually be stored, and the rule for that must
    have ONE definition. Both writers here — :func:`apply_answers`'s ``qc`` branch and
    :func:`apply_corrections`' — already refuse a status outside :data:`_QC_STATUSES`;
    without this predicate the route would have to restate that set, and a fifth
    verdict added to the schema would then be accepted by the route and silently
    declined by the core, which is the exact **200-having-changed-nothing** shape
    :func:`is_sha256_shaped` was added to close.

    WHY THIS PREDICATE EXISTS AT ALL, stated because it is a scope change. Until now
    no route forwarded ``qc``, and this file's own docstring recorded that gap: *"no
    ``POST /answers`` or ``POST /edit`` request can reach the ``qc`` branch below …
    Adding it to the route would be a new accepted input on two mutation paths, with
    an evidence-trail write, and belongs to a slice that can review that on its own
    terms."* This is that slice. The consequence of the gap was not cosmetic — a
    record created through the application could answer every other blocking question
    and still never export, because a measurement carrying a series requires a QC
    verdict and nothing could supply one.

    ``evidence`` is NOT required here, and that is deliberate rather than lax. The
    draft validator is what decides whether a verdict needs provenance, and it says so
    in its own words ("qc verdict has no evidence; confirm or supply provenance"). A
    predicate that demanded evidence would be a second, quieter copy of that rule, and
    the two would be free to disagree. What this answers is only *"can this be
    stored"*; whether the stored thing is enough to export stays with the validator.

    An ``evidence`` of the wrong type IS refused, because the writers assign it
    straight onto ``measurement.qc.evidence``, which the schema declares a string. A
    dict there would be stored and then refused by official validation, one step too
    late to tell the caller anything useful.
    """
    if not isinstance(value, dict):
        return False
    status = value.get("status")
    # `isinstance` BEFORE the membership test, and not for tidiness: `[] in
    # _QC_STATUSES` raises `TypeError: unhashable type`, and a set-membership test on
    # attacker-shaped input is a 500 out of a predicate whose whole job is to answer
    # yes or no. Found by this slice's own parametrised negative control, which passed
    # a list and a dict as the verdict.
    if not isinstance(status, str) or status not in _QC_STATUSES:
        return False
    evidence_note = value.get("evidence")
    return evidence_note is None or isinstance(evidence_note, str)


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

    Accepts the SAME ``apply_answers`` input shape: ``asset_sha256`` (``{uri: sha}``),
    ``series``, ``descriptor`` / ``descriptor_label``, ``edge``, ``qc``.

    ~~ONE OF THOSE IS NOT REACHABLE OVER HTTP~~ — **NO LONGER TRUE, and the old text is
    struck rather than deleted because it recorded a real gap and named the slice that
    would close it.** It read: *"that function recognises only ``asset_sha256``,
    ``series``, ``descriptor``, ``descriptor_label`` and ``edge``. It has never forwarded
    ``qc``, so no ``POST /answers`` or ``POST /edit`` request can reach the ``qc`` branch
    below … Adding it to the route would be a new accepted input on two mutation paths,
    with an evidence-trail write, and belongs to a slice that can review that on its own
    terms."*

    **That slice has now run, and it closed a defect much larger than a missing key.**
    Measured before the fix, on a record created through the application's own Create
    Experiment path: every other blocking question could be answered over HTTP, and the
    record still could not export — ``draft_report`` refused with *"measurement has
    series but qc verdict has no evidence; confirm or supply provenance (no default
    'valid')"*, and **no route existed that could supply one**. So a scientist could
    create a record, complete it as far as the product allowed, and be permanently one
    field short of Submit. The five canonical seeds did not reveal this because their
    drafts are built by ``build_draft`` from a fixture sheet with ``qc`` already present,
    never through the API.

    ``qc`` is now forwarded by ``_answers_to_apply_shape`` on BOTH paths, guarded by
    :func:`is_qc_shaped` so a value the core would decline is refused at the route
    instead of absorbed into a 200 that changed nothing. Nothing in THIS file changed to
    make that work: both branches already validated the enum and already refused to
    invent a default. The gap was never in the truth core.
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
                    "label": answers.get("descriptor_label", DESCRIPTOR_OUTPUT_LABEL),
                    "generated_utc": timestamp,
                    "generated_by": dict(DESCRIPTOR_GENERATED_BY),
                    "descriptors": [desc],
                }
            ]

    # -- qc: overwrite the verdict AND the note it rests on, as one value --
    #
    # THE WHOLE PAIR, NOT THE STATUS ALONE. Two defects came from comparing and
    # applying only `status`, and an independent review measured both end to end:
    #
    #   C1  Flipping `compromised` -> `valid` with no new note KEPT the old one, so an
    #       exported official record read `{"status": "valid", "evidence": "Beam dropped
    #       during scan 3; spectrum unusable."}`. Official validation passed, the
    #       advisory tier was silent (`QC_NONVALID_WITHOUT_EVIDENCE` does not fire for
    #       `valid`), and `block_evidence` gained a confirmation naming "valid" — so the
    #       trail looked right while the record's own provenance contradicted its
    #       verdict. That is `CLAUDE.md` §5 inverted: evidence present, and false.
    #
    #   I3  Correcting ONLY the note was declined here and reported by the route as
    #       "the submitted value was identical; nothing was invalidated" — a claim about
    #       a value that had in fact changed. A scientist had no way to correct the
    #       reasoning behind a verdict, and was told they already had.
    #
    # So the comparison is over `{status, evidence}` and the write replaces both. An
    # absent note REMOVES a stale one rather than inheriting it: a note that justified a
    # different verdict is not provenance for this one, and dropping it correctly
    # re-arms `portal_warnings.QC_NONVALID_WITHOUT_EVIDENCE`.
    #
    # `is_qc_shaped` rather than an inline enum test, for the reason that predicate
    # exists: one definition of a storable verdict, shared with the route. It also makes
    # this total — `status in _QC_STATUSES` raises `TypeError: unhashable` for a list or
    # dict verdict, which a caller building the shape itself can still supply.
    qc_answer = answers.get("qc")
    if is_qc_shaped(qc_answer):
        status = qc_answer["status"]
        evidence_note = qc_answer.get("evidence") or None
        current = draft.get("qc") or {}
        if (status, evidence_note) != (current.get("status"), current.get("evidence") or None):
            qc = draft.setdefault("qc", {})
            qc["status"] = status
            if evidence_note:
                qc["evidence"] = evidence_note
            else:
                qc.pop("evidence", None)
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
