"""``isaac bundle propose-terms`` — values in a bundle that are outside the vocabulary, as
draft proposals in the website's own portal format. Local; nothing is sent.

WHAT COUNTS AS "OUTSIDE THE VOCABULARY"
=======================================
A string value at a field path whose allowed values are a FIXED LIST, and which is not on
that list. Two lists can judge a path, and both are read, never transcribed:

* ``schema`` — the vendored official schema's ``enum`` at the path (the WEBSITE's list; since audit
  round 2 :func:`bundle.value_problem` refuses outside :func:`bundle.allowed_values`, the export
  target's list, so a value on the portal's list but not this one is eligible and is reported as a
  schema that lags the portal, never drafted);
* ``portal`` — the portal vocabulary snapshot's term list for the path
  (``schema_proposal_rules.PORTAL_SNAPSHOT_FILE``), the list the portal checks an upload and a
  proposed term against. Some paths have only this list.

Three kinds of value are read, and each occurrence says which it is:

* ``scientist_confirmed`` — a candidate or missing value whose state is
  ``scientist_confirmed``, with its value as the governing decision leaves it;
* ``parser_reading`` — a candidate's value that no scientist has confirmed;
* ``ai_reading`` — an AI interpretation's ``proposed_value`` (``annotate`` / ``--from-readings``).

MEASURED, 2026-10-29, on copies of the six real beamtime bundles (counts only): 618
occurrences of 16 distinct off-list values in 4 fields, ALL of them AI readings (no parser
value and no confirmed value was off a list). 2 drafts result, one term in two beamtimes
(131 readings of a potential scale that neither list has); the other 14 values are phrases
or sentences the website would refuse as a term, so they are listed and not drafted. The
reaction and cell-type terms the coverage note calls "outside the vocabulary" are NOT among
them: the reading pass kept them out of the bundles itself, listing them in its findings
file under ``not_found`` with free-text notes, and that file is not part of a bundle. This
command reads the bundle only; it never reads a findings file or turns a note into a term.

WHAT A DRAFT IS
===============
For an off-list value at a path the PORTAL has a term list for, one draft per distinct term,
in exactly the shape ``GET /api/schema-proposals/{id}/portal-payload`` hands out
(``schema_proposal_rules.portal_payload``: ``portal``, ``body``, ``sent_by_isaac``,
``notes``). Its ``description`` is EMPTY: what a term means is the proposer's statement, not
something a count of occurrences can supply, and the portal refuses a description under 20
characters. So every draft is ``ready_to_send: false`` until a person writes one. The
website's own check (``schema_proposal_rules._validate`` and its duplicate-term check) is run
on each term with the description set aside; a term it would refuse for any OTHER reason (a
space, a sentence, a near-duplicate of an allowed term) is NOT drafted, and the report gives
the website's own sentence why.

Nothing is transformed: ``cathodic corrosion`` is never rewritten to ``cathodic_corrosion``;
the draft keeps what the bundle holds and says why the portal would refuse it.

Citations are a file and a locator only (``relative_path`` / ``locator`` of an evidence
entry; ``source_path`` / ``excerpt_locator`` of an AI reading). No quote is copied out.

PRINTING A PARSER VALUE IS AN EXPOSURE (contract §11, §24): every candidate whose value this
command writes out is recorded as exposed to ``bundle propose-terms`` before anything is
printed or written, exactly as ``bundle list candidates`` does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .. import schema_proposal_rules as R
from . import bundle as B

FORMAT_ID = "isaac.term-proposal-drafts"
FORMAT_VERSION = "1"
COMMAND = "bundle propose-terms"

#: Citations kept per term. The total is always reported beside them.
MAX_CITATIONS_PER_TERM = 20

ORIGIN_CONFIRMED = "scientist_confirmed"
ORIGIN_PARSER = "parser_reading"
ORIGIN_AI = "ai_reading"

NOTICE = (
    "Draft proposals, written on this machine and sent nowhere. Each needs a description in "
    "the proposer's own words (at least 20 characters) before it can go to the ISAAC portal; "
    "the standard's owners decide there. These are not official records. Showing a parser value "
    "is recorded as an exposure in the bundle; that save is an ordinary bundle save, so a bundle "
    "written by an older build is also raised to this build's format, with the upgrade and any "
    "re-derived eligibility logged in format_upgrades and eligibility_rederived."
)


def _schema_list(path: str) -> list[str] | None:
    """The vendored schema's enum at ``path`` (an array is looked through to its items)."""
    node = B._schema_node(path)
    if not isinstance(node, Mapping):
        return None
    enum = node.get("enum")
    if not isinstance(enum, list) and isinstance(node.get("items"), Mapping):
        enum = node["items"].get("enum")
    return [v for v in enum if isinstance(v, str)] if isinstance(enum, list) else None


def _portal_key(path: str) -> str:
    return path.replace("[]", "")


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _evidence_citations(evidence: Sequence[Mapping]) -> list[dict]:
    out = []
    for e in evidence or ():
        if e.get("method") in ("deterministic_parser", "stored_rule") and e.get("relation") != "contradicts":
            out.append({"file": e.get("relative_path"), "locator": e.get("locator")})
    return out


def _interpretation_path(bundle: Mapping, interp: Mapping, index: Mapping) -> str | None:
    if isinstance(interp.get("field_path"), str):
        return interp["field_path"]
    target = interp.get("target") or {}
    obj = index.get((target.get("kind"), target.get("id")))
    return obj.get("target_field_path") if isinstance(obj, Mapping) else None


def collect(bundle: Mapping, sources: Mapping) -> dict:
    """Every off-list occurrence, grouped by field and term, and the candidates shown.

    Pure: reads ``bundle`` and the two vocabulary ``sources``; writes nothing."""
    decision_of = B._decisions_by_target(list(bundle.get("scientist_decisions") or ()))
    occurrences: list[dict] = []
    exposed: list[str] = []

    def lists_for(path: str) -> dict:
        key = _portal_key(path)
        section = R.section_of_term_list(sources, key)
        portal = R._portal_term_list(sources, section, key) if section else None
        return {
            "schema": _schema_list(path),
            "portal": list(portal["terms"]) if portal else None,
            "portal_section": section,
        }

    cache: dict[str, dict] = {}

    def check(path: str | None, value: Any, origin: str, ref: dict, citations: list[dict]) -> bool:
        if not path:
            return False
        lists = cache.setdefault(path, lists_for(path))
        if lists["schema"] is None and lists["portal"] is None:
            return False
        hit = False
        for term in _strings(value):
            missing_from = [
                name for name in ("schema", "portal") if lists[name] is not None and term not in lists[name]
            ]
            if not missing_from:
                continue
            hit = True
            occurrences.append(
                {
                    "field_path": path,
                    "term": term,
                    "origin": origin,
                    "missing_from": missing_from,
                    "ref": ref,
                    "citations": citations,
                }
            )
        return hit

    for c in bundle.get("candidates") or ():
        decision = B.candidate_decision(bundle, c, decision_of)
        value = B.final_value(c.get("value"), decision, c.get("readings"))
        origin = ORIGIN_CONFIRMED if c.get("value_state") == B.STATE_SCIENTIST_CONFIRMED else ORIGIN_PARSER
        ref = {"kind": "candidate", "id": c["candidate_id"], "run_id": c.get("run_id"), "state": c.get("value_state")}
        if check(c.get("target_field_path"), value, origin, ref, _evidence_citations(c.get("evidence") or ())):
            exposed.append(c["candidate_id"])

    for m in bundle.get("missing_values") or ():
        decision = decision_of.get(("missing_value", m["value_id"]))
        if decision is None:
            continue
        value = B.final_value(None, decision)
        origin = ORIGIN_CONFIRMED if m.get("value_state") == B.STATE_SCIENTIST_CONFIRMED else ORIGIN_PARSER
        if origin != ORIGIN_CONFIRMED:
            continue  # a decision that left it unconfirmed (defer, reject) states no value
        ref = {"kind": "missing_value", "id": m["value_id"], "run_id": m.get("run_id"), "state": m.get("value_state")}
        check(m.get("target_field_path"), value, origin, ref, [{"file": None, "locator": f"scientist decision {decision.get('decision_id')}"}])

    index: dict = {}
    for c in bundle.get("candidates") or ():
        index[("candidate", c["candidate_id"])] = c
    for m in bundle.get("missing_values") or ():
        index[("missing_value", m["value_id"])] = m
    for interp in bundle.get("ai_interpretations") or ():
        path = _interpretation_path(bundle, interp, index)
        target = interp.get("target") or {}
        ref = {
            "kind": "ai_interpretation",
            "id": interp.get("interpretation_id"),
            "target": {"kind": target.get("kind"), "id": target.get("id")},
            "state": interp.get("max_state"),
        }
        citations = [{"file": interp.get("source_path"), "locator": interp.get("excerpt_locator")}]
        if not citations[0]["file"] and not citations[0]["locator"]:
            citations = [
                {"file": None, "locator": r.get("locator")} for r in interp.get("source_refs") or () if isinstance(r, Mapping)
            ]
        check(path, interp.get("proposed_value"), ORIGIN_AI, ref, citations)

    return {"occurrences": occurrences, "exposed_candidates": sorted(set(exposed)), "lists": cache}


def _draft(sources: Mapping, path: str, term: str, lists: Mapping) -> dict:
    """One draft in the website's portal-payload format, checked by the website's own rules."""
    section = lists["portal_section"]
    if lists["portal"] is None or section is None:
        return {
            "drafted": False,
            "reason": (
                "The portal vocabulary snapshot has no list for this field, so the portal would refuse a new "
                "term for it and there is no portal payload. It is a fixed list in the ISAAC schema only: raise "
                "it with the standard's owners as a schema change."
            ),
        }
    if term in lists["portal"]:
        return {
            "drafted": False,
            "reason": (
                "The portal's list already has this term; only the vendored ISAAC schema lacks it. That is a "
                "schema that lags the portal, not a missing term, so no proposal is drafted."
            ),
        }
    body = {"proposal_type": R.ADD_TERM, "section": section, "category": _portal_key(path), "term": term}
    _, errors, _ = R._validate({**body, "description": "x" * R.LIMITS["description_min"]}, sources)
    conflict = R._term_conflict(sources, body)
    doc = {**body, "description": ""}
    payload = R.portal_payload(doc)
    payload["notes"] = [
        *payload["notes"],
        "Write the description before sending: what the term means and where it is used. ISAAC did not write one.",
    ]
    problems = [{"field": e["field"], "code": e["code"], "message": e["message"]} for e in errors]
    if conflict is not None:
        problems.append(
            {
                "field": "term",
                "code": "term_already_exists",
                "message": f"'{conflict['existing_term']}' is already an allowed term in this category; use it instead.",
            }
        )
    if problems:
        # The website would refuse it, so it is not drafted: the term is kept as the bundle
        # holds it and never rewritten into one that would pass (no guessing).
        return {
            "drafted": False,
            "reason": "The ISAAC website would refuse this as a new term: "
            + " ".join(p["message"] for p in problems),
            "problems": problems,
        }
    return {
        "drafted": True,
        "ready_to_send": False,
        "missing": ["description"],
        "problems": [],
        "portal_payload": payload,
    }


def propose_terms(bundle: Mapping, sources: Mapping) -> dict:
    """The full report: fields, terms, counts, citations and drafts. Pure."""
    found = collect(bundle, sources)
    by_field: dict[str, dict[str, list[dict]]] = {}
    for occ in found["occurrences"]:
        by_field.setdefault(occ["field_path"], {}).setdefault(occ["term"], []).append(occ)

    fields = []
    drafts = 0
    for path in sorted(by_field):
        lists = found["lists"][path]
        terms = []
        for term in sorted(by_field[path]):
            occs = by_field[path][term]
            counts = {ORIGIN_CONFIRMED: 0, ORIGIN_PARSER: 0, ORIGIN_AI: 0}
            for o in occs:
                counts[o["origin"]] += 1
            citations: list[dict] = []
            seen: set = set()
            total_citations = 0
            for o in occs:
                for cit in o["citations"]:
                    key = (cit.get("file"), cit.get("locator"))
                    if key in seen:
                        continue
                    seen.add(key)
                    total_citations += 1
                    if len(citations) < MAX_CITATIONS_PER_TERM:
                        citations.append({**cit, "origin": o["origin"], "ref": o["ref"]})
            draft = _draft(sources, path, term, lists)
            drafts += 1 if draft["drafted"] else 0
            terms.append(
                {
                    "term": term,
                    "count": len(occs),
                    "by_origin": counts,
                    "missing_from": sorted({m for o in occs for m in o["missing_from"]}),
                    "citations": citations,
                    "citations_total": total_citations,
                    "citations_truncated": total_citations > len(citations),
                    "draft": draft,
                }
            )
        fields.append(
            {
                "field_path": path,
                "judged_by": {
                    "schema_enum": lists["schema"] is not None,
                    "portal_list": lists["portal"] is not None,
                    "portal_section": lists["portal_section"],
                },
                "occurrences": sum(t["count"] for t in terms),
                "terms": terms,
            }
        )
    return {
        "format": FORMAT_ID,
        "format_version": FORMAT_VERSION,
        "notice": NOTICE,
        "sent_by_isaac": False,
        "bundle_id": bundle.get("bundle_id"),
        "vocabularies": {
            "schema": {"label": "Schema enums (vendored)", "sha256": sources["schema"].get("schema_sha256")},
            "portal": {"label": R.PORTAL_SNAPSHOT_LABEL, "sha256": sources["portal"].get("portal_sha256")},
        },
        "totals": {
            "fields": len(fields),
            "terms": sum(len(f["terms"]) for f in fields),
            "occurrences": sum(f["occurrences"] for f in fields),
            "drafts": drafts,
        },
        "fields": fields,
        "not_read": (
            "A reading pass's findings file is not part of a bundle and is not read: a term it lists "
            "under not_found, or mentions in its notes, is not counted here."
        ),
        "exposed_candidates": found["exposed_candidates"],
    }
