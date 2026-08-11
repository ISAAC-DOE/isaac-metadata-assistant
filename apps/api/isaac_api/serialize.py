"""Read-only JSON serializers for core dataclasses and draft structures.

The core (``draft_validator``, ``official``, ``portal_warnings``, ``export``, ``audit``)
exposes ``.render()`` and typed fields but no ``.to_dict()`` — by design (see
docs/ui-handoff/technical-architecture.md §11). This module owns ALL serialization so
no method is added to a core dataclass. It never re-implements a verdict: it only reshapes
what the core returned.

Serialization rules honored here (technical-architecture.md §3 / §9):
  - ``DraftReport.errors`` is ``[(where, msg)]``  -> ``{where, message}``.
  - ``OfficialReport.errors`` is ``[OfficialError(path, message)]`` -> ``{path, message}``.
  - ``PortalWarningReport`` exposes only ``.warnings`` + ``.advisory`` — the warning payload
    carries ``advisory:true, gating:false`` and NO ok/valid/passed field.
"""

from __future__ import annotations

from isaac_records.draft_validator import OBSERVED_SOURCE_TYPES, DraftReport
from isaac_records.export import ExportResult, get_path
from isaac_records.official import OfficialReport
from isaac_records.portal_warnings import PortalWarningReport

from . import inferability

# --- report serializers -------------------------------------------------------


def draft_report_to_dict(report: DraftReport) -> dict:
    return {
        "ok": report.ok,
        "errors": [{"where": w, "message": m} for w, m in report.errors],
        "warnings": [{"where": w, "message": m} for w, m in report.warnings],
    }


def official_report_to_dict(report: OfficialReport) -> dict:
    return {
        "ok": report.ok,
        "errors": [{"path": e.path, "message": e.message} for e in report.errors],
    }


def warnings_to_dict(report: PortalWarningReport) -> dict:
    """Advisory, non-gating channel. Deliberately NO ok/valid/passed field."""
    return {
        "advisory": True,
        "gating": False,
        "warnings": [
            {"code": w.code, "where": w.where, "message": w.message}
            for w in report.warnings
        ],
    }


def export_result_to_dict(result: ExportResult) -> dict:
    """Serialize an ExportResult (reports always; record/sidecar when produced)."""
    out: dict = {
        "ok": result.ok,
        "draft_report": draft_report_to_dict(result.draft_report),
        "official_report": (
            official_report_to_dict(result.official_report)
            if result.official_report is not None
            else None
        ),
    }
    if result.record is not None:
        out["record"] = result.record
    if result.sidecar is not None:
        out["sidecar"] = result.sidecar
    return out


def audit_to_dict(results, text: str) -> dict:
    """``audit_records`` returns [(name, OfficialReport, (covered, expected, uncovered, dangling))].

    Coverage is completeness reporting, never a verdict: ``evidence_present`` /
    ``evidence_expected`` are the honest record-derived denominator, and the
    ``uncovered`` / ``dangling`` key lists are passed through faithfully.
    """
    records = []
    for name, report, (covered, expected, uncovered, dangling) in results:
        records.append(
            {
                "name": name,
                "ok": report.ok,
                "schema_errors": [
                    {"path": e.path, "message": e.message} for e in report.errors
                ],
                "evidence_present": covered,
                "evidence_expected": expected,
                "uncovered": list(uncovered),
                "dangling": list(dangling),
            }
        )
    return {"records": records, "text": text}


# --- draft field grouping -----------------------------------------------------

# Draft ``fields`` keys are official dotted JSON-paths (verified against
# docs/samples/…evidence.json). We group by the top-level path segment into stable,
# human-titled sections. Order is fixed; any unmapped prefix lands in "Other".
_GROUP_TITLES: dict[str, str] = {
    "system": "System & Instrument",
    "timestamps": "Timestamps",
    "sample": "Sample",
    "context": "Environment & Context",
    "measurement": "Measurement",
    "assets": "Assets & Files",
    "descriptors": "Descriptors",
    "attribution": "Attribution",
}
_GROUP_ORDER = list(_GROUP_TITLES.keys())
_OTHER = "Other"


def _label(path: str) -> str:
    """Humanize the last path segment (e.g. ``sample.material.formula`` -> ``Formula``)."""
    last = path.split(".")[-1]
    return last.replace("_", " ").strip().title()


def _source_types(evidence) -> list[str]:
    seen: list[str] = []
    for e in evidence or []:
        st = e.get("source_type") if isinstance(e, dict) else None
        if st and st not in seen:
            seen.append(st)
    return seen


def _draft_field(path: str, env: dict) -> dict:
    evidence = env.get("evidence") or []
    return {
        "path": path,
        "label": _label(path),
        "value": env.get("value"),
        "status": env.get("status"),
        "evidence_count": len(evidence),
        "source_types": _source_types(evidence),
    }


def draft_to_groups(draft: dict) -> dict:
    """Group draft scalar fields into stable UI sections for the Review Record screen."""
    fields = draft.get("fields") or {}
    buckets: dict[str, list[dict]] = {}
    for path, env in fields.items():
        if not isinstance(env, dict):
            continue
        top = path.split(".")[0]
        title = _GROUP_TITLES.get(top, _OTHER)
        buckets.setdefault(title, []).append(_draft_field(path, env))

    ordered_titles = [
        _GROUP_TITLES[k] for k in _GROUP_ORDER if _GROUP_TITLES[k] in buckets
    ]
    if _OTHER in buckets:
        ordered_titles.append(_OTHER)

    groups = [{"title": t, "fields": buckets[t]} for t in ordered_titles]
    return {"groups": groups}


# --- pending blockers ---------------------------------------------------------

_DEMO_LABEL = "Example answer"

#: Provenance carried BY the example answer itself, so a reader (and a test) can
#: check what it is without inferring it from a label. Every claim here is
#: machine-checkable and every one of them is a limitation.
EXAMPLE_ANSWER_PROVENANCE: dict = {
    "source": "tutorial_example_fixture",
    "is_evidence_for_this_record": False,
    "auto_applied": False,
    "requires_user_confirmation": True,
}


def _demo_answer_for(entry: dict, demo_answers: dict, *, example_scope: bool):
    """The labeled example answer for a blocker, or None. Never auto-applied.

    SCOPE IS ENFORCED HERE, and it did not used to be. The endpoint documentation
    has always promised this value "for the built-in examples only", but only the
    ``asset`` branch was incidentally scoped (it keys on the blocker's own URI
    against the fixture's URI map, so a foreign URI missed). The ``series`` and
    ``descriptor`` branches read the fixture unconditionally and returned it for
    ANY record — a fabricated 7-point spectrum and a fabricated descriptor value
    with an uncertainty, offered as the answer to a scientific question about a
    record they have nothing to do with. That is precisely what CLAUDE.md §5
    forbids ("Never invent or guess: scientific values, units, ... descriptor
    values, uncertainty values"), and the promise in the docstring made it worse
    by asserting a boundary the code did not have.

    ``example_scope`` is now required and defaults, at every caller, to False —
    fail-closed, so a caller that forgets it withholds the example rather than
    leaking it. The example content remains available on the five canonical
    walkthrough records, which is what it was authored for.
    """
    if not example_scope:
        return None
    kind = entry.get("kind")
    if kind == "asset":
        value = (demo_answers.get("asset_sha256") or {}).get(entry.get("uri"))
    elif kind == "series":
        value = demo_answers.get("series")
    elif kind == "descriptor":
        value = demo_answers.get("descriptor")
    else:
        value = None
    if value is None:
        return None
    return {"value": value, "label": _DEMO_LABEL, "provenance": dict(EXAMPLE_ANSWER_PROVENANCE)}


def blocker_id(entry: dict) -> str:
    """Stable id used as the answer key. Asset blockers key on their URI."""
    kind = entry.get("kind")
    if kind == "asset":
        return entry.get("uri") or "asset"
    return kind or "blocker"


def _blocker_about(entry: dict):
    return entry.get("uri") or entry.get("blocker")


def pending_to_list(draft: dict, demo_answers: dict, *, example_scope: bool = False) -> dict:
    """The open blocking questions, each with its explicit inferability decision.

    ``example_scope`` gates the walkthrough example answer (see
    :func:`_demo_answer_for`) and DEFAULTS TO FALSE so the leak-safe behaviour is
    the one you get by forgetting.

    Two channels, deliberately kept apart:

    * ``inferability`` — can ISAAC determine this value from the record's own
      evidence? For every blocker kind the honest answer is no, and the state says
      which flavour of no. It carries no value: ``Inferability.__post_init__``
      refuses one for any state but ``supported_suggestion``, and
      ``blocker_inferability`` cannot return that state at all.
    * ``demo_answer`` — is there illustrative walkthrough content the user may
      click? Example-scope only, provenance-carrying, never auto-applied.

    They cannot contradict each other because the second one's existence is fed
    INTO the first (``example_available``), so the refusal is written knowing the
    example is on screen and says so in the same sentence.

    NOT served here: the rule set's per-field decisions (``inferability.infer_all``).
    An earlier revision added them as an ``inferences`` block on this response, and
    they reached three endpoints with no consumer anywhere in the client — an
    unread payload that shipped concrete values and bypassed the client's own
    re-check, which only ever ran over ``item.inferability``. ``infer_all``
    remains available to a caller that has a use for it; serving it by default was
    speculative surface, so it is gone rather than guarded.
    """
    pending = []
    for entry in draft.get("pending") or []:
        demo = _demo_answer_for(entry, demo_answers, example_scope=example_scope)
        pending.append(
            {
                "id": blocker_id(entry),
                "kind": entry.get("kind"),
                "question": entry.get("question"),
                "about": _blocker_about(entry),
                "demo_answer": demo,
                "inferability": inferability.blocker_inferability(
                    entry, example_available=demo is not None
                ).to_dict(),
            }
        )
    return {"pending": pending}


# --- evidence trail -----------------------------------------------------------


def _status_from_evidence(evidence) -> str:
    """Derive a display status from evidence types (mirrors draft_validator semantics).

    An observed source (incl. user_confirmation) => verified; derivation-only => inferred.
    """
    types = {e.get("source_type") for e in (evidence or []) if isinstance(e, dict)}
    if types & set(OBSERVED_SOURCE_TYPES):
        return "verified"
    if "derivation" in types:
        return "inferred"
    return "verified"


# --- per-item isolation (one bad entry must not take the trail down) -----------
#
# MEASURED DEFECT this section exists to fix. Both builders below used to read
# each stored evidence payload with no shape check at all, so ONE malformed entry
# destroyed the WHOLE trail — and the trail is the whole Evidence screen:
#
#   * a payload that is not iterable (``{"system.facility.beamline": 7}`` in a
#     sidecar, or ``implicit: [7]`` in a draft) raised out of ``get_evidence``,
#     i.e. an unhandled 500 on a GET. Measured on `77820bf`: with 36 good sidecar
#     entries and one ``7``, ``GET /experiments/{id}/evidence`` raised
#     ``TypeError: 'int' object is not iterable`` and returned NOTHING. In the
#     browser that GET shares a ``Promise.all`` with four siblings, so the whole
#     bundle rejected and the screen rendered "Backend Not Running" — a false
#     statement about the server, caused by one field's stored evidence.
#   * a payload that is iterable but not a list of objects (a dict, a string, a
#     list containing a string) did NOT raise here; it was passed through
#     verbatim and crashed the CLIENT instead. Also measured: the Evidence view
#     rendered as an EMPTY DOM.
#   * a draft field envelope that is not a dict was silently ``continue``d — the
#     field vanished from the trail with no statement that anything was dropped,
#     which is the failure mode a scientist cannot even notice.
#
# The rule now: an entry whose stored evidence cannot be read is still SERVED,
# still carries its own identity (path/id/position) and whatever else about it
# IS readable, and says so explicitly via ``unavailable`` + ``unavailable_reason``.
# Nothing is invented for it — no value, no source, no citation, no status that
# implies support it does not have (CLAUDE.md §5).
#
# A BUNDLE-level failure is deliberately NOT absorbed here. If ``draft["fields"]``
# or ``sidecar["evidence"]`` is not a mapping at all, there is no per-item
# question to answer and these functions still raise, so the caller fails the
# whole read instead of reporting a misleading partial success. (The route's own
# artifact-pair tolerance — ``routes._read_artifact_json`` — is unchanged and
# still degrades an unreadable sidecar to the draft trail.)

#: ``status`` for an entry whose stored evidence yielded NO readable support.
#: A separate value rather than one of the draft's own statuses: the trail's
#: ``status`` is a statement about the support behind the entry, and no such
#: statement can be made about evidence that could not be read. "verified" — what
#: ``_status_from_evidence`` returns for an empty list — would have been a claim
#: this code is in no position to make. The field's own stored status is not lost:
#: ``/experiments/{id}/draft`` carries it independently.
UNAVAILABLE_STATUS = "unavailable"

#: Neutral English for a JSON type, for the reason string. The stored VALUE is
#: never interpolated — the reader is told what shape was found, not handed
#: arbitrary content to read as if it were a citation.
_JSON_KIND = {
    bool: "a boolean",
    int: "a number",
    float: "a number",
    str: "a string",
    dict: "an object",
    list: "a list",
    type(None): "null",
}


def _kind(value) -> str:
    return _JSON_KIND.get(type(value), "an unreadable value")


def _readable_evidence(payload) -> tuple[list[dict], str | None]:
    """Split a stored evidence payload into (readable entries, reason it is partial).

    ``None``/absent is NOT a failure — a field legitimately carries no citation,
    and reporting that as unavailable would cry wolf on every uncited entry.
    """
    if payload is None:
        return [], None
    if isinstance(payload, list):
        readable = [e for e in payload if isinstance(e, dict)]
        if len(readable) == len(payload):
            return readable, None
        unreadable = len(payload) - len(readable)
        return readable, (
            f"{unreadable} of {len(payload)} stored evidence entries cannot be "
            f"shown: not an evidence object"
        )
    return [], (
        f"the stored evidence for this entry is {_kind(payload)}, not a list of "
        f"evidence entries"
    )


def _trail_entry(path: str, value, status, payload) -> dict:
    """One trail entry, with its evidence read defensively.

    ``status`` is the caller's own answer for a well-formed entry; it is replaced
    by :data:`UNAVAILABLE_STATUS` only when the payload yielded no readable
    support at all. A PARTIALLY readable payload keeps the status its readable
    entries justify AND still discloses what could not be shown — the status then
    describes exactly what is on screen, and the reason names the rest.
    """
    readable, reason = _readable_evidence(payload)
    entry = {
        "path": path,
        "value": value,
        "status": UNAVAILABLE_STATUS if reason is not None and not readable else status,
        "evidence": readable,
    }
    if reason is not None:
        entry["unavailable"] = True
        entry["unavailable_reason"] = reason
    return entry


def _unreadable_entry(path: str, reason: str) -> dict:
    """An entry nothing could be read from except its position in the document.

    Kept in the trail on purpose. Dropping it would silently shorten a scientist's
    evidence trail; ``value``/``evidence`` stay empty because inventing either is
    exactly what CLAUDE.md §5 forbids.
    """
    return {
        "path": path,
        "value": None,
        "status": UNAVAILABLE_STATUS,
        "evidence": [],
        "unavailable": True,
        "unavailable_reason": reason,
    }


#: Shape errors a single malformed stored entry can raise. Narrow on purpose (the
#: reasoning is ``routes._read_artifact_json``'s): a ``MemoryError`` or a genuine
#: programming error must not be reported to a scientist as "this item's evidence
#: is malformed", because that would be a false statement about their record.
_ITEM_SHAPE_ERRORS = (AttributeError, TypeError, ValueError, KeyError, IndexError)


def evidence_trail_from_draft(draft: dict) -> list[dict]:
    """Evidence trail for a not-yet-exported experiment: read the draft envelopes.

    Every entry is read in isolation: one malformed envelope, implicit claim or
    asset becomes ONE entry marked unavailable, never a lost trail. See the
    section comment above for the measured defect.
    """
    entries: list[dict] = []
    for path, env in (draft.get("fields") or {}).items():
        if not isinstance(env, dict):
            # Was `continue` — a silent drop. The field is stated as unreadable
            # instead, so its absence from the record's evidence is visible.
            entries.append(
                _unreadable_entry(
                    str(path),
                    f"this field's stored draft envelope is {_kind(env)}, not an "
                    f"evidence envelope",
                )
            )
            continue
        try:
            entries.append(
                _trail_entry(path, env.get("value"), env.get("status"), env.get("evidence"))
            )
        except _ITEM_SHAPE_ERRORS as exc:
            entries.append(
                _unreadable_entry(
                    str(path), f"this field's stored evidence could not be read ({type(exc).__name__})"
                )
            )
    for index, imp in enumerate(draft.get("implicit") or []):
        if not isinstance(imp, dict):
            entries.append(
                _unreadable_entry(
                    f"implicit:#{index}",
                    f"the stored implicit claim at position {index} is {_kind(imp)}, "
                    f"not an implicit claim; it has no recorded subject to name",
                )
            )
            continue
        path = f"implicit:{imp.get('about', '?')}"
        try:
            payload = imp.get("evidence")
            entries.append(
                _trail_entry(path, imp.get("value"), _status_from_evidence(_readable_evidence(payload)[0]), payload)
            )
        except _ITEM_SHAPE_ERRORS as exc:
            entries.append(
                _unreadable_entry(
                    path, f"this implicit claim could not be read ({type(exc).__name__})"
                )
            )
    for index, asset in enumerate(draft.get("assets") or []):
        if not isinstance(asset, dict):
            entries.append(
                _unreadable_entry(
                    f"assets:#{index}",
                    f"the stored asset at position {index} is {_kind(asset)}, not an "
                    f"asset; it has no recorded id or URI to name",
                )
            )
            continue
        aid = asset.get("asset_id", asset.get("uri", "?"))
        try:
            payload = asset.get("evidence")
            entries.append(
                _trail_entry(
                    f"assets:{aid}",
                    asset.get("sha256"),
                    _status_from_evidence(_readable_evidence(payload)[0]),
                    payload,
                )
            )
        except _ITEM_SHAPE_ERRORS as exc:
            entries.append(
                _unreadable_entry(
                    f"assets:{aid}",
                    f"this asset's stored evidence could not be read ({type(exc).__name__})",
                )
            )
    return entries


def evidence_trail_from_sidecar(sidecar: dict, record: dict) -> list[dict]:
    """Evidence trail for an exported experiment: read the real sidecar faithfully.

    Sidecar keys are official dotted paths, or ``assets:``/``descriptors:``/``implicit:``
    namespaced keys. ``implicit:`` values are ``{value, evidence}``; the rest are evidence
    lists. Values are resolved from the record so sha256s are visible post-export.

    Read per key, in isolation: one malformed payload becomes ONE entry marked
    unavailable — keyed by the sidecar key it was stored under, so which entry
    failed and where it came from stay answerable. See the section comment above.
    """
    assets_by_id = {
        a.get("asset_id"): a for a in (record.get("assets") or []) if isinstance(a, dict)
    }
    entries: list[dict] = []
    for key, payload in (sidecar.get("evidence") or {}).items():
        try:
            if key.startswith("implicit:"):
                value = payload.get("value") if isinstance(payload, dict) else None
                evidence = payload.get("evidence") if isinstance(payload, dict) else payload
            else:
                evidence = payload
                if ":" in key:
                    namespace, _, name = key.partition(":")
                    if namespace == "assets":
                        value = (assets_by_id.get(name) or {}).get("sha256")
                    else:
                        value = None
                else:
                    value, _found = get_path(record, key)
            entries.append(
                _trail_entry(
                    key, value, _status_from_evidence(_readable_evidence(evidence)[0]), evidence
                )
            )
        except _ITEM_SHAPE_ERRORS as exc:
            entries.append(
                _unreadable_entry(
                    str(key),
                    f"this sidecar entry could not be read ({type(exc).__name__})",
                )
            )
    return entries
