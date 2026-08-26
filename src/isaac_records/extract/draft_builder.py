"""Assemble a draft ENVELOPE deterministically from the Slice-3A parsers.

``build_draft(structured_path, listing_path)`` wires the two deterministic Phase-3
parsers (``structured`` + ``file_listing``) into the pre-export draft envelope the
no-guessing validator (:mod:`isaac_records.draft_validator`) accepts. It is PURE:
it only *reads* the two paths through the public parsers and returns a dict; it
writes nothing and touches no truth-path code.

The builder never guesses. Anything the deterministic pipeline knows is *required*
but cannot supply without more input is surfaced in a ``pending`` list (the exact
``/isaac-complete`` question set from ``docs/extraction.md`` §8), not fabricated:

  - every raw/reduced/notebook asset needs a ``sha256`` the listing does not carry,
    so ``assets`` stays EMPTY (a sha256-less asset would fail ``validate_draft``) and
    each candidate becomes a ``pending`` sha256 blocker instead;
  - ``measurement.series`` needs the reduced ``.xdi`` spectrum's actual data points,
    which the listing only *names* — a ``pending`` series blocker, never invented;
  - an evidence record requires at least one descriptor (schema ``allOf``), which no
    source supplies — a ``pending`` descriptor blocker.

Two implicit inferences are emitted deterministically: ``absorbing_element`` (the
sole non-oxygen element in the formula — a defensible derivation) and ``edge`` as a
NULL needs-confirmation candidate (inferring the absorption edge from an energy
window needs a physics table the deterministic builder must not fake).
"""

from __future__ import annotations

import re
from pathlib import Path

from .file_listing import parse_file_listing
from .structured import parse_contributors, parse_rows, parse_structured

# The single supported path: XANES / characterization at a facility.
_META = {
    "record_type": "evidence",
    "record_domain": "characterization",
    "source_type": "facility",
}

# Element symbols: an uppercase letter optionally followed by one lowercase.
_ELEMENT_RE = re.compile(r"[A-Z][a-z]?")


def non_oxygen_elements(formula) -> tuple[str, ...]:
    """The distinct non-oxygen element symbols in ``formula``, first-appearance order.

    The tokenizing half of the absorbing-element rule, exposed so a caller can tell
    the rule's three outcomes apart. ``_absorbing_element`` collapses "several
    candidates" and "no candidates" into the same ``None``, which is right for a
    builder that must not guess either way, but wrong for a caller that wants to say
    *ambiguous* in one case and *not inferable* in the other. Splitting it here keeps
    ONE tokenizer, so the two readings can never drift.
    """
    if not isinstance(formula, str) or not formula:
        return ()
    non_oxygen = [tok for tok in _ELEMENT_RE.findall(formula) if tok != "O"]
    return tuple(dict.fromkeys(non_oxygen))


#: The stated rule the ``system.domain`` derivation applies, verbatim, as it is
#: written into the derivation evidence entry. Named so the rule text has ONE
#: definition and cannot drift between the two callers of :func:`derive_system_domain`.
SYSTEM_DOMAIN_RULE = (
    "system.domain = experimental for a facility-source record "
    "(meta.source_type=facility ⇒ physical experiment, not computation)"
)


def derive_system_domain(meta) -> dict | None:
    """The ``system.domain`` envelope ``meta`` DETERMINES, or ``None``.

    A DERIVATION, NOT A GUESS, AND THE DISTINCTION IS ``CLAUDE.md`` §5's. That rule
    permits an inferred field "only by a documented/stored rule"; this is that rule,
    stored here, stated in :data:`SYSTEM_DOMAIN_RULE`, and carried into the field as a
    ``derivation`` evidence entry so the inference travels with its justification into
    the export sidecar. The official schema's ``system.domain`` is a CLOSED two-value
    enum (``experimental`` | ``computational``) and a physical facility is never a
    computation, so a ``facility``-source record has exactly one admissible value.

    ``None`` FOR EVERY OTHER ``source_type``, AND THAT IS THE NO-GUESSING HALF. The
    schema's ``source_type`` enum has six values, and only ``facility`` makes the
    domain deterministic: ``laboratory`` and ``industrial`` are physical but this rule
    does not speak for them, ``computation`` points the other way, and ``literature``
    and ``database`` describe a record ABOUT work rather than the work. Returning
    ``None`` leaves the field absent, which makes official validation report
    ``'domain' is a required property`` — an honest refusal a person can answer, and
    strictly better than a domain nothing supports.
    """
    if not isinstance(meta, dict) or meta.get("source_type") != "facility":
        return None
    return {
        "value": "experimental",
        "status": "inferred",
        "evidence": [{"source_type": "derivation", "rule": SYSTEM_DOMAIN_RULE}],
    }


def _absorbing_element(formula):
    """The sole non-oxygen element in ``formula`` (e.g. ``"CuO2" -> "Cu"``).

    Deterministic: tokenize element symbols and drop oxygen. Returns the element
    only when exactly one non-oxygen element remains; otherwise ``None`` (ambiguous
    or unparseable → no guess).
    """
    unique = non_oxygen_elements(formula)
    return unique[0] if len(unique) == 1 else None


def build_draft(structured_path, listing_path) -> dict:
    """Build a draft envelope from the campaign sheet + the raw file listing.

    Reads ``structured_path`` (``.csv``/``.xlsx``) via :func:`parse_structured` /
    :func:`parse_contributors` / :func:`parse_rows`, and ``listing_path`` via
    :func:`parse_file_listing`. Returns the draft dict; the caller validates it with
    ``draft_validator.validate_draft`` and later exports it.
    """
    structured_path = Path(structured_path)
    listing_path = Path(listing_path)

    # 1. Scalar fields — each ExtractedField already carries its evidence.
    fields: dict[str, dict] = {}
    formula = None
    for ef in parse_structured(structured_path):
        env: dict = {
            "value": ef.value,
            "status": ef.status,
            "evidence": list(ef.evidence),
        }
        if ef.unit is not None:
            env["unit"] = ef.unit
        fields[ef.path] = env
        if ef.path == "sample.material.formula":
            formula = ef.value

    # 1b. system.domain — a deterministic derivation, NOT a guess. The official
    #     schema requires system.domain whenever a system block exists, and one does
    #     here (technique + facility), so omitting it would make the draft
    #     un-exportable. A facility-source record is by definition an experiment: the
    #     enum is experimental|computational and a physical facility is never
    #     computational. Surface it as an inferred field (mirrors the golden draft's
    #     inferred domain) rather than fabricating it or letting export fail.
    #
    #     THE RULE ITSELF MOVED OUT to :func:`derive_system_domain` and is called
    #     here rather than restated. It has a second caller — the API's run-draft
    #     composition, which needs it for a record a scientist CREATED rather than
    #     extracted from a sheet, where the same required property was reachable by
    #     no write path at all. Two inline copies of one derivation is the drift this
    #     repository refuses; the output for this path is unchanged.
    derived_domain = derive_system_domain(_META)
    if derived_domain is not None:
        fields["system.domain"] = derived_domain

    # Block-level provenance the official record cannot carry per-field lands in
    #   ``block_evidence`` (assistant natural-key map), harvested into the export
    #   sidecar. Keys: ``attribution:<name>|<role>`` / ``qc:status`` / ``series:<id>``
    #   / ``links:<rel>|<target>|<basis>``.
    block_evidence: dict[str, list[dict]] = {}

    # 2. Attribution — contributors go in schema-clean (name + role only). Each
    #    contributor's spreadsheet provenance is preserved in block_evidence (under
    #    the attribution natural key), NOT dropped, keeping attribution record-shaped.
    contributors = []
    for c in parse_contributors(structured_path):
        contributors.append({"name": c["name"], "role": c["role"]})
        if c.get("evidence"):
            block_evidence[f"attribution:{c['name']}|{c['role']}"] = list(c["evidence"])

    # 3. Raw rows for the values the scalar map omits (qc_status, energy window).
    by_field = {r["field"]: r for r in parse_rows(structured_path)}

    # 4. qc — read the ACTUAL qc_status cell; never hardcode a status. The row's
    #    spreadsheet provenance is routed into block_evidence["qc:status"] (the
    #    official qc block has no per-field evidence slot for a native ``status``
    #    value). Sidecar keys must contain ':' so the audit treats them as namespaced,
    #    not dotted record paths; this one reads "provenance of measurement.qc.status".
    qc = None
    qc_row = by_field.get("qc_status")
    if qc_row is not None and qc_row.get("value") not in (None, ""):
        qc = {"status": qc_row["value"]}
        block_evidence["qc:status"] = [
            {
                "source_type": "spreadsheet",
                "source_file": qc_row["source_file"],
                "locator": qc_row["locator"],
                "quote": qc_row["value"],
            }
        ]

    # 5. Implicit inferences (deterministic derivations only).
    implicit: list[dict] = []
    absorber = _absorbing_element(formula)
    if absorber is not None:
        implicit.append(
            {
                "about": "absorbing_element",
                "value": absorber,
                "evidence": [
                    {
                        "source_type": "derivation",
                        "rule": (
                            "absorbing element = sole non-oxygen element in "
                            f"sample.material.formula ({formula} -> {absorber})"
                        ),
                    }
                ],
            }
        )
    # edge: do NOT assert a physics fact. Represent as a NULL needs-confirmation
    # candidate whose derivation note records the incident-energy window only.
    start = (by_field.get("incident_energy_start_eV") or {}).get("value")
    end = (by_field.get("incident_energy_end_eV") or {}).get("value")
    window = f"{start}–{end} eV" if start is not None and end is not None else "unrecorded"
    implicit.append(
        {
            "about": "edge",
            "value": None,
            "evidence": [
                {
                    "source_type": "derivation",
                    "rule": (
                        "edge requires scientific confirmation; incident-energy "
                        f"window {window} recorded from Configurations"
                    ),
                }
            ],
        }
    )

    # 6. Assets — ONLY assets with a real sha256 belong here. The synthetic listing
    #    carries none, so this stays empty; the candidates become pending blockers.
    assets: list[dict] = []

    # 7. Pending — the deterministic /isaac-complete question set, never guessed.
    pending: list[dict] = []
    reduced_evidence: list[dict] = []
    for cand in parse_file_listing(listing_path):
        cand_evidence = list(cand.evidence)
        pending.append(
            {
                "kind": "asset",
                "content_role": cand.content_role,
                "uri": cand.uri,
                "media_type": cand.media_type,
                "blocker": "sha256",
                "question": f"What is the sha256 of {cand.uri}?",
                "evidence": cand_evidence,
            }
        )
        if cand.content_role == "reduction_product":
            reduced_evidence = cand_evidence

    pending.append(
        {
            "kind": "series",
            "blocker": "reduced_spectrum",
            "question": (
                "Provide/point to the reduced spectrum (the .xdi reduction_product) "
                "so measurement.series can be built."
            ),
            "evidence": reduced_evidence,
        }
    )
    # qc verdict: if the sheet carried no qc_status cell we cannot source it, and a
    # measurement with series needs one — surface a pending blocker (never a default
    # 'valid'). Deterministic: fires only when qc could not be read above.
    if qc is None:
        pending.append(
            {
                "kind": "qc",
                "blocker": "qc_status",
                "question": (
                    "What is the QC verdict for this measurement "
                    "(valid/compromised/failed/pending) and how was it determined?"
                ),
            }
        )
    pending.append(
        {
            "kind": "descriptor",
            "blocker": "required_for_evidence_record",
            "question": (
                "Provide at least one descriptor (e.g. XANES inflection-point energy "
                "+ uncertainty) — an evidence record requires descriptors."
            ),
            "evidence": [
                {
                    "source_type": "derivation",
                    "rule": (
                        "evidence record requires descriptors.outputs[] "
                        "(official schema allOf: evidence => descriptors)"
                    ),
                }
            ],
        }
    )

    draft: dict = {
        "meta": dict(_META),
        "fields": fields,
        "attribution": {"contributors": contributors},
        "implicit": implicit,
        "assets": assets,
        "pending": pending,
    }
    if qc is not None:
        draft["qc"] = qc
    if block_evidence:
        draft["block_evidence"] = block_evidence
    return draft


__all__ = ["build_draft", "non_oxygen_elements"]
