"""A structured answer checked against the OFFICIAL schema's own rule for its path.

THE DEFECT THIS CLOSES, measured by an independent QA audit in a real browser
(A-03, 2026-10-11). The series entry control told a scientist *"The shape is checked
here and again on the server"*, and the answer ``[{"series_id": "x"}]`` was ACCEPTED:
the question closed, the pending count fell, and the record became un-exportable for
a reason that surfaced only at export, as raw validator text. The server's check was
:func:`isaac_records.complete.is_series_shaped` — "a non-empty list of objects with a
hashable ``series_id``" — which is a STORABILITY rule, not the schema's rule. The
official schema declares three required keys on every series item, closes every
nested object with ``additionalProperties: false``, and constrains ``channels[].role``
to an enum. None of that was asked until export.

WHAT THIS DOES. It asks the vendored official schema (``schema/isaac_record_v1.json``,
through :func:`isaac_records.official.load_official_validator` — the same loader the
export gate uses, never a copy of the document) whether ONE answered value fits the
sub-schema the schema itself declares at the path that value is written to:

* ``series``     -> ``properties.measurement.properties.series``
* ``descriptor`` -> ``properties.descriptors.properties.outputs.items.properties
  .descriptors.items`` — ONE descriptor, because that is what the answer carries;
  ``complete.apply_answers`` builds the ``outputs[]`` wrapper (label, generated_utc,
  generated_by) around it, and those three are the application's, not the scientist's.

Every finding names the record path the failing part would occupy, in the same
dot-joined form :func:`isaac_records.official.validate_official` reports at export,
and the validator's message VERBATIM — the product decision that validation text is
shown as the validator wrote it (DEC-30/DEC-35) applies here exactly as it does there.

WHAT THIS IS NOT, stated because the difference is the honesty of the refusal.

* It is NOT whole-record validation and must never be reported as an official verdict.
  A value that fits its sub-schema can still leave the record un-exportable for a
  reason that lives elsewhere (the draft validator's evidence rules, the exactness
  gate, a conditional the schema states at the top level). It answers one narrower
  question: *does this value have the shape the official schema gives this field?*
* It does NOT touch the truth path. ``official.py`` is imported read-only and is not
  edited; ``complete.py`` still applies its own storability guard first, and this runs
  only on a value that guard admitted.
* It does NOT check ``format``. The official validator does not arm a format checker
  (``CLAUDE.md`` §15, Q20: format enforcement in the official validator is NOT
  authorized), so this, which reuses that validator's class, does not either.

The schema has no ``$ref`` (measured on v1.05: the document contains neither ``$ref``
nor ``$defs``), so a sub-schema validates on its own. If a schema refresh ever adds a
reference, :func:`_sub_validator` refuses to build a validator over a node carrying one
and every check fails CLOSED with a stated reason, rather than silently resolving a
reference against the wrong root.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from itertools import islice

from isaac_records.export import strip_evidence
from isaac_records.official import load_official_validator

from .workspace import REPO_ROOT

#: Where in the official schema each structured answer key's rule lives, and where in
#: an official RECORD the answered value lands. The second is the prefix every finding
#: path carries, so a reader of the refusal reads the same path the export gate would
#: have printed.
SHAPE_RULES: Mapping[str, tuple[tuple[str, ...], str]] = {
    "series": (
        ("properties", "measurement", "properties", "series"),
        "measurement.series",
    ),
    "descriptor": (
        (
            "properties",
            "descriptors",
            "properties",
            "outputs",
            "items",
            "properties",
            "descriptors",
            "items",
        ),
        "descriptors.outputs.0.descriptors.0",
    ),
}

#: The keys this module checks. ``qc`` is deliberately absent: its whole value space is
#: an enum plus a free-text note, and :func:`isaac_records.complete.is_qc_shaped`
#: already decides exactly what the schema would (an off-enum status, a non-string
#: note). Checking it twice would be two definitions of one rule.
CHECKED_KEYS: tuple[str, ...] = tuple(SHAPE_RULES)

#: The one sentence a finding carries when the schema itself could not be consulted.
#: It is NOT a schema message and says so; it exists so a broken vendored document
#: refuses every structured write with a reason instead of admitting every one.
SCHEMA_UNREADABLE_MESSAGE = (
    "The official ISAAC schema could not be read on this server, so this value could "
    "not be checked against it and was not written."
)


class _Unavailable(Exception):
    """The vendored schema, or the node a rule names, could not be used."""


def _sub_validator(key: str):
    """A validator over the schema's OWN node for ``key``. Fails closed."""
    try:
        validator = load_official_validator(REPO_ROOT)
    except (OSError, ValueError) as exc:  # missing / unparseable / invalid schema
        raise _Unavailable(str(type(exc).__name__)) from exc
    node: object = validator.schema
    for segment in SHAPE_RULES[key][0]:
        if not isinstance(node, Mapping) or segment not in node:
            raise _Unavailable(f"no schema node at {'/'.join(SHAPE_RULES[key][0])}")
        node = node[segment]
    if not isinstance(node, Mapping):
        raise _Unavailable("schema node is not an object")
    # A node that REFERENCES elsewhere cannot be validated on its own — the reference
    # would resolve against the sub-schema, not the document. Measured absent today.
    if "$ref" in json.dumps(node):
        raise _Unavailable("schema node carries a $ref")
    return validator.evolve(schema=dict(node))


def _carries_evidence_key(node: object) -> bool:
    """Whether any mapping anywhere in ``node`` has an ``evidence`` key. Iterative, so a
    deep value cannot exhaust the stack, and it allocates no copy of the value."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if "evidence" in current:
                return True
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return False


#: How many findings a check COLLECTS before it stops looking. One more than a refusal
#: reports, so "there are more" is an observation rather than a guess.
FINDINGS_LIMIT = 25


def shape_findings(key: str, value: object, *, limit: int = FINDINGS_LIMIT) -> tuple[list[dict], bool]:
    """``(findings, more)`` — the first ``limit`` ways ``value`` fails the official
    schema's rule for ``key``, and whether at least one more exists. ``([], False)`` fits.

    Each finding is ``{"key", "path", "message"}``: the answer key, the record path the
    failing part would occupy (dot-joined, exactly as the export gate prints it), and
    the validator's message verbatim. The findings returned are sorted by path, as
    ``validate_official`` sorts.

    **THE ERRORS ARE TAKEN LAZILY, AND THAT IS A RESOURCE BOUND, NOT A STYLE CHOICE.**
    The first version collected and sorted EVERY error and capped only the response. An
    independent review measured what that cost on ``POST /answers`` with ``series = [{}]
    * N``: 50,000 items took 2.4 s and 541 MB against 0.29 s / 109 MB before the check
    existed, and 300,000 items (1.2 MB of request) was still running after 45 s of CPU
    at over 1.37 GB — while the path's own size bound admits roughly 2 million such
    items. ``jsonschema``'s ``iter_errors`` is a generator that descends item by item,
    so ``islice`` stops the walk at the ``limit + 1``-th error: a refusal costs work
    proportional to where its first errors are, never to how many there are. What is
    given up is stated rather than hidden: the findings are the first the validator
    MET (then sorted), not the first in path order over the whole value, and no exact
    total is reported — only that there are more.

    **THE VALUE IS CHECKED THE WAY EXPORT WILL SEE IT** — with every ``evidence`` key
    removed by ``isaac_records.export.strip_evidence``, the exporter's own function,
    imported rather than restated. ``complete.apply_answers`` overwrites a descriptor's
    ``evidence`` and export strips evidence at every depth, so a value carrying one is
    exported cleanly; refusing it here would refuse what export accepts.

    A key this module does not check returns ``([], False)`` — it is not this module's
    to judge.
    """
    if key not in SHAPE_RULES:
        return [], False
    prefix = SHAPE_RULES[key][1]
    try:
        validator = _sub_validator(key)
    except _Unavailable:
        return [{"key": key, "path": prefix, "message": SCHEMA_UNREADABLE_MESSAGE}], False
    # Stripped only when there is something to strip: `strip_evidence` rebuilds the whole
    # value, and on a large spectrum with no evidence key that would be a second copy of
    # the request for nothing. The walk that decides it allocates nothing.
    checked = strip_evidence(value) if _carries_evidence_key(value) else value
    head = list(islice(validator.iter_errors(checked), limit + 1))
    more = len(head) > limit
    findings = []
    for err in sorted(head[:limit], key=lambda e: list(map(str, e.absolute_path))):
        tail = ".".join(str(p) for p in err.absolute_path)
        findings.append(
            {
                "key": key,
                "path": f"{prefix}.{tail}" if tail else prefix,
                "message": err.message,
            }
        )
    return findings, more


def findings_for_answers(
    answers: Mapping | None,
    keys: Sequence[str] = CHECKED_KEYS,
    *,
    limit: int = FINDINGS_LIMIT,
) -> tuple[list[dict], bool]:
    """:func:`shape_findings` over every checked key a request body carries, sharing ONE
    ``limit`` across keys. Returns ``(findings, more)``.

    A blank value (``None`` / ``""``) is skipped, because a blank answer is not an
    answer and every route already drops it.
    """
    out: list[dict] = []
    more = False
    for key in keys:
        value = (answers or {}).get(key)
        if value in (None, ""):
            continue
        room = limit - len(out)
        if room <= 0:
            # Something remains unchecked, and it is only "more" if it fails: ask for one.
            extra, _ = shape_findings(key, value, limit=1)
            more = more or bool(extra)
            continue
        found, key_more = shape_findings(key, value, limit=room)
        out.extend(found)
        more = more or key_more
    return out, more


def descriptor_enum(field: str) -> tuple | None:
    """The official schema's own closed value list for a descriptor's ``field`` (``kind``,
    ``source``), read from the vendored document — or ``None`` when it declares none or
    cannot be read. Used to decide whether the descriptor form's selects can show a stored
    value; never a second copy of the vocabulary."""
    try:
        validator = _sub_validator("descriptor")
    except _Unavailable:
        return None
    node = validator.schema.get("properties", {}).get(field, {})
    values = node.get("enum") if isinstance(node, Mapping) else None
    return tuple(values) if isinstance(values, list) else None
