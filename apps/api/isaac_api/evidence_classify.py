"""P28.4 — deterministic evidence-support classification (a display VIEW).

This is a THIRD axis — *evidence support* — that COMPOSES the two axes the truth
core already produces: draft **field-status** (verified / inferred /
needs_confirmation / missing / rejected) and evidence **source_type** (the
observed set / ``derivation`` / ``user_confirmation``). It reshapes what the core
already returned; it computes NO new verdict.

It is deliberately DISTINCT from — and must never be confused with — schema
validity, workflow completion, export readiness, or advisory warnings. A result
carries none of ``valid`` / ``ok`` / ``exportable`` / ``complete``. Classifying a
field ``supported`` here does not make a record exportable, and classifying it
``inferred_candidate`` does not block export; those decisions stay in the frozen
truth core (``official.py`` / ``export.py`` / ``audit.py``), unchanged.

Six classes, precedence highest-first:

  unreadable             the stored evidence for this entry could not be read at
                         all (``serialize`` marked it ``unavailable`` and salvaged
                         nothing), so its evidence support is UNKNOWN — a separate
                         class because "could not be read" and "has nothing" are
                         different facts and only one of them is a finding about
                         the science
  conflicting_evidence   >=2 evidence entries assert incompatible non-null values
  supported              value present AND (observed OR user_confirmation OR a
                         documented derivation rule) — all defensible, all export
                         today (this includes truth-core ``inferred``: rule-backed
                         with a present value)
  inferred_candidate     a derivation-rule PROPOSAL whose value is not confirmed
                         (value None, or status not final) — the implicit['edge']
                         pattern; never authoritative
  insufficient_evidence  needs_confirmation with >=1 evidence entry but the value
                         is not established
  unknown                needs_confirmation / missing / rejected with no defensible
                         evidence; plainly absent — a POSITIVE claim that nothing
                         defensible is recorded, which is why an unreadable entry
                         must never land here

Pure, non-mutating, deterministic, stdlib + existing project reads only
(Graphify-free). Read-only imports of ``draft_validator.OBSERVED_SOURCE_TYPES``
and ``serialize.evidence_trail_from_draft`` — the frozen truth path is untouched.
"""

from __future__ import annotations

import json

from isaac_records.draft_validator import OBSERVED_SOURCE_TYPES

from isaac_api.serialize import evidence_trail_from_draft

#: Observed source types (incl. ``user_confirmation``) as an O(1) set.
_OBSERVED = frozenset(OBSERVED_SOURCE_TYPES)

#: Statuses that mean the value is established/final (value entered as fact).
_FINAL_STATUSES = frozenset({"verified", "inferred"})

_EXPLANATIONS = {
    "unreadable": "This entry's stored evidence could not be read, so its evidence support cannot be classified.",
    "conflicting_evidence": "Evidence asserts incompatible values; needs human resolution.",
    "inferred_candidate": "Proposed by a derivation rule; unconfirmed — not entered as fact.",
    "insufficient_evidence": "Evidence present but the value is not established.",
    "unknown": "No defensible value.",
    # `supported` is tailored deterministically below by evidence kind.
}

#: Appended when SOME of an entry's stored evidence was readable and some was
#: not. The class then describes only the readable part, which is a true
#: statement about less than the whole entry — so the rest is said out loud
#: rather than left to read as completeness.
_PARTIAL_DISCLOSURE = (
    "Part of this entry's stored evidence could not be read; this describes only "
    "the part that could."
)


def _is_derivation_with_rule(evidence: list) -> bool:
    return any(
        isinstance(e, dict) and e.get("source_type") == "derivation" and e.get("rule")
        for e in evidence
    )


def _asserted_values(evidence: list) -> list[str]:
    """Distinct non-null asserted answers (e.g. ``user_confirmation.answer``).

    Values are normalized to a stable JSON key so ordering never affects the
    conflict decision; the return is sorted for determinism.
    """
    seen: set[str] = set()
    for e in evidence:
        if not isinstance(e, dict):
            continue
        answer = e.get("answer")
        if answer is None:
            continue
        seen.add(json.dumps(answer, sort_keys=True, default=str))
    return sorted(seen)


def _looks_unsafe(s: str) -> bool:
    """A locator we must not surface: absolute/private path or a token-like hex blob."""
    if s.startswith("/") or "/Users/" in s or "\\Users\\" in s:
        return True
    if len(s) >= 32 and all(c in "0123456789abcdefABCDEF" for c in s):
        return True
    return False


def _safe_locator(e: dict) -> str | None:
    """A safe, already-present reference for one evidence entry, or None.

    Prefers the curated ``locator`` string, else the ``source_file`` name. Never a
    secret/token, raw quote, or absolute private path; ``answer``/``quote`` are
    intentionally excluded.
    """
    for key in ("locator", "source_file"):
        v = e.get(key)
        if isinstance(v, str) and v and not _looks_unsafe(v):
            return v
    return None


def _sources(evidence: list) -> list[dict]:
    """Minimal, safe per-entry source refs: ``{source_type, locator?}``."""
    out: list[dict] = []
    for e in evidence:
        if not isinstance(e, dict):
            continue
        st = e.get("source_type")
        if not st:
            continue
        src: dict = {"source_type": st}
        loc = _safe_locator(e)
        if loc is not None:
            src["locator"] = loc
        out.append(src)
    return out


def _classify_entry(entry: dict) -> tuple[str, str]:
    """Compose (field-status + source_type) -> (classification, value_state).

    Precedence: unreadable > conflicting_evidence > supported > inferred_candidate
    > insufficient_evidence > unknown.
    """
    evidence = entry.get("evidence") or []
    value = entry.get("value")
    status = entry.get("status")

    # 0. unreadable — `serialize` could not read this entry's stored evidence and
    #    salvaged none of it, so there is no evidence to compose with. Every rule
    #    below would read the resulting empty list as an OBSERVATION about the
    #    record and fall through to `unknown` / "No defensible value." — a
    #    positive claim that nothing defensible is recorded, asserted about an
    #    entry whose evidence may well be there and merely unreadable. Measured on
    #    `ba8e38e`: both `{"a.b": 7}` and
    #    `{"c.d": {"value": "V", "status": "verified", "evidence": 7}}` classified
    #    `unknown` / "No defensible value.", and `{"value": "V"}` had a value
    #    right there. On base `77820bf` the first was silently absent and the
    #    second raised a 500, so BOTH a crash and an omission had become a
    #    confident false statement. CLAUDE.md §5: state what is true, or refuse.
    if entry.get("unavailable") and not evidence:
        return "unreadable", "unreadable"

    value_present = value is not None
    observed = any(
        isinstance(e, dict) and e.get("source_type") in _OBSERVED for e in evidence
    )
    derivation_with_rule = _is_derivation_with_rule(evidence)

    # 1. conflicting_evidence — two or more incompatible non-null assertions.
    if len(_asserted_values(evidence)) >= 2:
        return "conflicting_evidence", "candidate"

    # 2. supported — a present value with defensible backing. Includes truth-core
    #    `inferred` (rule-backed, value present): it exports today, so it is
    #    supported-by-rule, NOT a candidate.
    if value_present and (observed or derivation_with_rule):
        return "supported", "confirmed"

    # 3. inferred_candidate — a derivation-rule proposal whose value is not confirmed
    #    (reached only when not supported: value None, or status not final).
    if derivation_with_rule and (not value_present or status not in _FINAL_STATUSES):
        return "inferred_candidate", "candidate"

    # 4. insufficient_evidence — needs_confirmation with some evidence but no value.
    if status == "needs_confirmation" and len(evidence) >= 1:
        return "insufficient_evidence", ("candidate" if value_present else "none")

    # 5. unknown — nothing defensible; plainly absent.
    return "unknown", "none"


def _explanation(classification: str, evidence: list, entry: dict | None = None) -> str:
    """The deterministic sentence for a classification, given the entry it came from.

    ``entry`` is optional only so the older two-argument call shape keeps working;
    without it the unreadability disclosures cannot be composed, because the
    ``unavailable`` flag and its reason live on the trail entry rather than on the
    evidence list.
    """
    entry = entry or {}
    reason = entry.get("unavailable_reason")
    if classification == "unreadable":
        base = _EXPLANATIONS["unreadable"]
        # The reason names the SHAPE found, never the stored value — `serialize`
        # builds it from `_kind` alone. Passing it through keeps the row
        # actionable without quoting anything the reader could mistake for a
        # citation.
        return f"{base[:-1]}: {reason}." if isinstance(reason, str) and reason else base
    text = _explanation_for_readable(classification, evidence)
    if entry.get("unavailable"):
        # Reached only with SOME readable evidence (no readable evidence is
        # `unreadable` above), so the sentence is true of what was read and
        # silent about the rest until this is appended.
        return f"{text} {_PARTIAL_DISCLOSURE}"
    return text


def _explanation_for_readable(classification: str, evidence: list) -> str:
    if classification == "supported":
        observed_nonuc = any(
            isinstance(e, dict)
            and e.get("source_type") in _OBSERVED
            and e.get("source_type") != "user_confirmation"
            for e in evidence
        )
        if observed_nonuc:
            return "Backed by observed evidence."
        if any(
            isinstance(e, dict) and e.get("source_type") == "user_confirmation"
            for e in evidence
        ):
            return "Backed by user confirmation."
        return "Backed by a documented derivation rule with a present value."
    return _EXPLANATIONS[classification]


def classify_fields(draft: dict) -> list[dict]:
    """Classify every evidence-bearing entry of a draft by evidence support.

    Input surface is ``serialize.evidence_trail_from_draft`` — draft fields plus
    implicit claims plus assets — so all three are classified uniformly. Pure and
    non-mutating; deterministic in the draft's own field order.

    Returns a list of ``{field, classification, value_state, explanation, sources}``.
    """
    results: list[dict] = []
    for entry in evidence_trail_from_draft(draft):
        evidence = entry.get("evidence") or []
        classification, value_state = _classify_entry(entry)
        results.append(
            {
                "field": entry.get("path"),
                "classification": classification,
                "value_state": value_state,
                "explanation": _explanation(classification, evidence, entry),
                "sources": _sources(evidence),
            }
        )
    return results
