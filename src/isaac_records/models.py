"""Builders for the draft-authoring format.

A draft is NOT an ISAAC record. It is the pre-export working format where the
no-guessing policy is enforced: scalar fields carry a `{value, unit?, status,
evidence[]}` envelope so a value cannot be finalized without a source. Export
(`export.py`) transforms a draft into the native official record shape and drops
the envelope — evidence moves to a sidecar.

Draft shape:
    {
      "meta":    {record_type, record_domain, source_type},
      "fields":  {"<dotted.official.path>": <envelope>, ...},   # scalars only
      "series":  [...],                # official measurement.series shape (verbatim)
      "assets":  [{asset_id, content_role, uri, sha256, ..., "evidence":[...]}],
      "descriptors_outputs": [{label, generated_by, ...,
                               "descriptors":[{name, kind, source, value, ...,
                                               "evidence":[...]}]}],
      "links":   [...],
      "attribution": {...},
      "tags":    [...],
      "implicit":[{about, value, "evidence":[...]}]   # sidecar-only, never a record field
    }
"""

from __future__ import annotations

STATUSES = ("verified", "inferred", "needs_confirmation", "missing", "rejected")

SOURCE_TYPES = (
    "document",
    "spreadsheet",
    "screenshot",
    "web_form",
    "file_listing",
    "user_confirmation",
    "derivation",
)


def evidence(
    source_type: str,
    *,
    source_file: str | None = None,
    locator: str | None = None,
    quote: str | None = None,
    question: str | None = None,
    answer: str | None = None,
    rule: str | None = None,
    timestamp: str | None = None,
) -> dict:
    """One evidence entry. Keys with None values are dropped."""
    entry = {
        "source_type": source_type,
        "source_file": source_file,
        "locator": locator,
        "quote": quote,
        "question": question,
        "answer": answer,
        "rule": rule,
        "timestamp": timestamp,
    }
    return {k: v for k, v in entry.items() if v is not None}


def user_confirmation(question: str, answer: str, timestamp: str) -> dict:
    """The user's answer to a follow-up question, stored as evidence."""
    return evidence("user_confirmation", question=question, answer=answer, timestamp=timestamp)


def derivation(rule: str, quote: str | None = None) -> dict:
    """Evidence for an inferred value: the stated rule it was derived by."""
    return evidence("derivation", rule=rule, quote=quote)


def field_value(
    value=None,
    *,
    unit: str | None = None,
    status: str = "missing",
    evidence: tuple | list = (),
) -> dict:
    """A draft field envelope: {value, unit, status, evidence[]}."""
    env = {"value": value, "status": status, "evidence": list(evidence)}
    if unit is not None:
        env["unit"] = unit
    return env
