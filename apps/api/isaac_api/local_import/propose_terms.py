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

Four kinds of value are read, and each occurrence says which it is:

* ``scientist_confirmed`` — a candidate or missing value whose state is
  ``scientist_confirmed``, with its value as the governing decision leaves it;
* ``parser_reading`` — a candidate's value that no scientist has confirmed;
* ``ai_reading`` — an AI interpretation's ``proposed_value`` (``annotate`` / ``--from-readings``).
  A reading whose target a scientist has since confirmed or corrected with an ALLOWED value is
  not counted (the scientist answered it; ``skipped.ai_readings_already_answered`` counts them);
* ``scientist_request`` (bundle 1.10.0) — a VOCABULARY REQUEST: a scientist's answer that
  ``decide``, ``template import`` or ``template adopt`` refused only because it is not on the
  field's list (``bundle.off_list_only``), kept in ``vocabulary_requests``. Never a decision or a
  value; its person, time and own note are the term's ``scientist_notes``.

KNOWN EQUIVALENCES AND NEAR TERMS
=================================
:data:`EQUIVALENT_TERMS` is a small, explicit table of words that NAME an existing term (a
reference electrode written out: ``reversible_hydrogen_electrode`` is ``RHE``). Such a word is not
drafted: the report says "use `RHE` (an existing term)". An entry counts only while its term is
on the field's list. Matching ignores case and treats spaces and hyphens as underscores; nothing
else is ever matched, and the word itself is never rewritten.

:data:`NEAR_TERMS` (and an existing term that shares a whole run of words with the new one, e.g.
``three_electrode`` in ``three_electrode_static_cell``) are CLOSE but not the same (``XANES`` is a
region of an ``XAS`` scan): the term IS drafted, with ``check_existing`` listing them and a
sentence the scientist must answer in the description, why none of them fits. A genuinely new term
is never blocked by either table.

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

Citations are a file NAME (no folders), a locator and the run ids (``relative_path`` /
``locator`` of an evidence entry; ``source_path`` / ``excerpt_locator`` of an AI reading; the
sheet's cells or the ``decide`` answer of a vocabulary request). No quote is copied out. Each
term also carries ``runs`` / ``run_ids`` (the distinct runs its occurrences name) and
``scientist_notes`` (the scientist's own words from vocabulary requests, attributed), the keys
the website's drafts loader reads (``apps/web/src/lib/termDrafts.ts``).

A TERM THE WEBSITE WOULD REFUSE FOR ITS SHAPE (a space, a sentence) is not drafted, and its draft
says what to ASK for (``ask``: "one word, e.g. cathodic_corrosion"); ISAAC still never writes that
word as the term.

A SECOND RUN (``--merge``): :func:`merge_reports` updates an existing drafts file instead of
replacing it: new terms are added, counts, citations, runs and notes are this run's, a description
a person wrote into a draft's body is KEPT, and a term this run no longer finds is carried over
(``carried_over: true``) rather than dropped.

PRINTING A PARSER VALUE IS AN EXPOSURE (contract §11, §24): every candidate whose value this
command writes out is recorded as exposed to ``bundle propose-terms`` before anything is
printed or written, exactly as ``bundle list candidates`` does.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import PurePath
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
ORIGIN_REQUEST = "scientist_request"
ORIGINS = (ORIGIN_CONFIRMED, ORIGIN_PARSER, ORIGIN_AI, ORIGIN_REQUEST)

_REFERENCE_SCALES = {
    "reversible_hydrogen_electrode": "RHE",
    "standard_hydrogen_electrode": "SHE",
    "saturated_calomel_electrode": "SCE",
    "silver_chloride": "Ag/AgCl",
    "silver_silver_chloride": "Ag/AgCl",
}
#: Words that NAME an existing term of the field (``field path -> {word: existing term}``), matched by
#: :func:`_norm`. ONLY clear equivalences: a reference electrode written out in words is its
#: abbreviation on the portal's list. An entry counts only while its term is on the field's list.
EQUIVALENT_TERMS: Mapping[str, Mapping[str, str]] = {
    "context.electrochemistry.potential_scale": _REFERENCE_SCALES,
    "context.electrochemistry.reference_electrode.type": _REFERENCE_SCALES,
}
#: Words CLOSE to existing terms but not the same (``field path -> {word: existing terms}``): drafted,
#: with ``check_existing`` naming these. XANES and EXAFS are regions of an XAS scan; HERFD is a mode of it.
NEAR_TERMS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "system.technique": {
        "xanes": ("XAS", "HERFD-XAS"),
        "exafs": ("XAS",),
        "nexafs": ("XAS",),
        "xafs": ("XAS",),
        "herfd": ("HERFD-XAS", "XAS"),
        "herfd_xanes": ("HERFD-XAS", "XAS"),
    },
}
_SEPARATORS = re.compile(r"[\s\-]+")


def _norm(term: str) -> str:
    """Case folded, spaces and hyphens as underscores: how the two tables are matched (never a rewrite)."""
    return _SEPARATORS.sub("_", term.strip()).casefold()


def equivalent_term(path: str | None, term: Any, allowed: Sequence[str] | None = None) -> str | None:
    """The existing term ``term`` names (:data:`EQUIVALENT_TERMS`), while that term is on the field's list
    (``allowed``, else :func:`bundle.allowed_values`), else ``None``."""
    if not path or not isinstance(term, str):
        return None
    same = (EQUIVALENT_TERMS.get(_portal_key(path)) or {}).get(_norm(term))
    if same is None:
        return None
    listed = allowed if allowed is not None else (B.allowed_values(path) or ())
    return same if same in listed and same != term else None


def near_terms(path: str, term: str, allowed: Sequence[str]) -> list[str]:
    """Existing terms close to ``term`` (:data:`NEAR_TERMS`, then any existing term that shares a whole run of
    words with it, e.g. ``three_electrode`` in ``three_electrode_static_cell``), in the list's order."""
    near = set((NEAR_TERMS.get(_portal_key(path)) or {}).get(_norm(term), ()))
    words = [w for w in re.split(r"[_\s\-/]+", term.casefold()) if w]

    def runs_in(a: list[str], b: list[str]) -> bool:
        return 0 < len(a) <= len(b) and any(b[i:i + len(a)] == a for i in range(len(b) - len(a) + 1))

    for existing in allowed:
        if not isinstance(existing, str) or existing == term:
            continue
        theirs = [w for w in re.split(r"[_\s\-/]+", existing.casefold()) if w]
        if len(theirs) == 1 and len(theirs[0]) <= 2:
            continue  # a one- or two-letter term shares a word with too much to say anything
        if runs_in(theirs, words) or runs_in(words, theirs):
            near.add(existing)
    return [t for t in allowed if t in near]


def _file_name(path: Any) -> str | None:
    """A file's NAME, without its folders (a citation never carries a local path)."""
    if not isinstance(path, str) or not path:
        return None
    return PurePath(path.replace("\\", "/")).name or None

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


def _evidence_citations(evidence: Sequence[Mapping], run_ids: Sequence[str]) -> list[dict]:
    out = []
    for e in evidence or ():
        if e.get("method") in ("deterministic_parser", "stored_rule") and e.get("relation") != "contradicts":
            out.append({"file": _file_name(e.get("relative_path")), "locator": e.get("locator"), "run_ids": list(run_ids)})
    return out


def _request_citation(req: Mapping) -> dict:
    """Where a vocabulary request was said: the sheet and its cells, or the ``decide`` answer."""
    src = req.get("source") or {}
    cells = list(src.get("cells") or ())
    if cells:
        locator = ", ".join(cells[:5]) + (f" and {len(cells) - 5} more" if len(cells) > 5 else "")
    elif src.get("question_id"):
        locator = f"answer to question {src['question_id']} ({req.get('request_id')})"
    else:
        locator = f"`{src.get('command') or 'bundle decide'}` answer ({req.get('request_id')})"
    return {"file": _file_name(src.get("file")), "locator": locator, "run_ids": list(req.get("run_ids") or ())}


def _request_note(req: Mapping) -> dict:
    """The scientist's own words from one vocabulary request, attributed (the website reads ``text``)."""
    src = req.get("source") or {}
    by = (req.get("requested_by") or {}).get("name")
    day = str(req.get("requested_utc") or "")[:10]
    where = {"decide_answer": "an answer to `decide`", "template_cell": f"a cell of {_file_name(src.get('file'))}",
             "adopted_sheet_cell": f"their own sheet {_file_name(src.get('file'))}"}.get(src.get("kind"), "an answer")
    text = f'{by or "No name given"}, {day}, in {where}: "{req.get("term")}"'
    if req.get("note"):
        text += f" — {req['note']}"
    return {"text": text, "by": by, "said_utc": req.get("requested_utc"), "request_id": req.get("request_id")}


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

    def check(path: str | None, value: Any, origin: str, ref: dict, citations: list[dict],
              run_ids: Sequence[str] = (), note: dict | None = None) -> bool:
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
                    "run_ids": [r for r in run_ids if r],
                    **({"note": note} if note else {}),
                }
            )
        return hit

    for c in bundle.get("candidates") or ():
        decision = B.candidate_decision(bundle, c, decision_of)
        value = B.final_value(c.get("value"), decision, c.get("readings"))
        origin = ORIGIN_CONFIRMED if c.get("value_state") == B.STATE_SCIENTIST_CONFIRMED else ORIGIN_PARSER
        ref = {"kind": "candidate", "id": c["candidate_id"], "run_id": c.get("run_id"), "state": c.get("value_state")}
        runs = [c["run_id"]] if c.get("run_id") else []
        if check(c.get("target_field_path"), value, origin, ref, _evidence_citations(c.get("evidence") or (), runs), runs):
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
        runs = [m["run_id"]] if m.get("run_id") else []
        check(m.get("target_field_path"), value, origin, ref,
              [{"file": None, "locator": f"scientist decision {decision.get('decision_id')}", "run_ids": runs}], runs)

    index: dict = {}
    for c in bundle.get("candidates") or ():
        index[("candidate", c["candidate_id"])] = c
    for m in bundle.get("missing_values") or ():
        index[("missing_value", m["value_id"])] = m
    skipped_answered = 0
    for interp in bundle.get("ai_interpretations") or ():
        path = _interpretation_path(bundle, interp, index)
        target = interp.get("target") or {}
        obj = index.get((target.get("kind"), target.get("id")))
        if path and _answered_with_allowed_value(bundle, target, obj, path, decision_of):
            if any(t not in (cache.setdefault(path, lists_for(path))["schema"] or ())
                   and t not in (cache[path]["portal"] or ()) for t in _strings(interp.get("proposed_value"))):
                skipped_answered += 1
            continue  # the scientist answered this target with an allowed value: the reading is not a request
        runs = list(interp.get("run_ids") or ()) or ([obj["run_id"]] if isinstance(obj, Mapping) and obj.get("run_id") else [])
        ref = {
            "kind": "ai_interpretation",
            "id": interp.get("interpretation_id"),
            "target": {"kind": target.get("kind"), "id": target.get("id")},
            "state": interp.get("max_state"),
        }
        citations = [{"file": _file_name(interp.get("source_path")), "locator": interp.get("excerpt_locator"), "run_ids": runs}]
        if not citations[0]["file"] and not citations[0]["locator"]:
            citations = [
                {"file": None, "locator": r.get("locator"), "run_ids": runs}
                for r in interp.get("source_refs") or () if isinstance(r, Mapping)
            ]
        check(path, interp.get("proposed_value"), ORIGIN_AI, ref, citations, runs)

    for req in bundle.get("vocabulary_requests") or ():
        ref = {"kind": "vocabulary_request", "id": req.get("request_id"), "scope": req.get("scope")}
        check(req.get("field_path"), req.get("term"), ORIGIN_REQUEST, ref, [_request_citation(req)],
              list(req.get("run_ids") or ()), _request_note(req))

    return {"occurrences": occurrences, "exposed_candidates": sorted(set(exposed)), "lists": cache,
            "skipped": {"ai_readings_already_answered": skipped_answered}}


def _answered_with_allowed_value(bundle: Mapping, target: Mapping, obj: Any, path: str, decision_of: Mapping) -> bool:
    """``True`` when the target of an AI reading is governed by a scientist's ``confirm``/``correct`` whose value
    the field takes (:func:`bundle.value_problem` finds nothing): the scientist answered it."""
    if not isinstance(obj, Mapping):
        return False
    kind = target.get("kind")
    decision = decision_of.get((kind, target.get("id")))
    if kind == "candidate":
        decision = B.candidate_decision(bundle, obj, decision_of)
    if not isinstance(decision, Mapping) or decision.get("decision") not in ("confirm", "correct"):
        return False
    base = obj.get("value") if kind == "candidate" else None
    value = B.final_value(base, decision, obj.get("readings"))
    return value is not None and B.value_problem(path, value) is None


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
    same = equivalent_term(path, term, [*(lists["portal"] or ()), *(lists["schema"] or ())])
    if same is not None:
        message = (f"Use `{same}` (an existing term): {term!r} names the same thing as {same!r} on this list "
                   f"(propose_terms.EQUIVALENT_TERMS), so no proposal is drafted. Answer with `--value {same}`.")
        return {"drafted": False, "use_existing": same, "reason": message,
                "problems": [{"field": "term", "code": "equivalent_existing_term", "message": message}]}
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
        refused = {
            "drafted": False,
            "reason": "The ISAAC website would refuse this as a new term: "
            + " ".join(p["message"] for p in problems),
            "problems": problems,
        }
        if any(p["code"] == "invalid_term" for p in problems):
            # WHAT TO ASK, not a rewrite: the scientist names the one word; ISAAC never writes it as the term
            example = _SEPARATORS.sub("_", term.strip())
            shaped = bool(R._TERM_SHAPE.match(example)) and not R._PATH_LIKE.search(example) and example != term
            refused["ask"] = ("Ask the scientist for the term as one word (letters, digits and underscores, no spaces)"
                              + (f", e.g. {example}" if shaped else "")
                              + "; ISAAC does not rewrite it. Their answer, recorded again, is drafted.")
        return refused
    draft = {
        "drafted": True,
        "ready_to_send": False,
        "missing": ["description"],
        "problems": [],
        "portal_payload": payload,
    }
    near = near_terms(path, term, list(lists["portal"]))
    if near:
        question = (f"Existing terms close to it: {', '.join(near)}. In the description, say why none of these fits "
                    f"{term!r} (for example, what it names that they do not).")
        draft["check_existing"] = near
        draft["check_existing_question"] = question
        payload["notes"].append(question)
    return draft


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
            counts = {origin: 0 for origin in ORIGINS}
            for o in occs:
                counts[o["origin"]] += 1
            citations: list[dict] = []
            seen: set = set()
            total_citations = 0
            run_ids = sorted({r for o in occs for r in o.get("run_ids") or ()})
            notes = [o["note"] for o in occs if o.get("note")]
            for o in occs:
                for cit in o["citations"]:
                    key = (cit.get("file"), cit.get("locator"), tuple(cit.get("run_ids") or ()))
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
                    "runs": len(run_ids),
                    "run_ids": run_ids,
                    "scientist_notes": notes,
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
        "vocabulary_requests_read": len(bundle.get("vocabulary_requests") or ()),
        "fields": fields,
        "skipped": found["skipped"],
        "not_read": (
            "A reading pass's findings file is not part of a bundle and is not read: a term it lists "
            "under not_found, or mentions in its notes, is not counted here."
        ),
        "exposed_candidates": found["exposed_candidates"],
    }


# --- a second run: --merge ------------------------------------------------------------------------


class MergeRefused(ValueError):
    """An existing ``--out`` file that ``--merge`` cannot update; nothing was written."""


def _description(term_entry: Mapping) -> str:
    body = (((term_entry.get("draft") or {}).get("portal_payload") or {}).get("body") or {})
    text = body.get("description")
    return text.strip() if isinstance(text, str) else ""


def merge_reports(old: Any, new: Mapping, sources: Mapping) -> tuple[dict, dict]:
    """``(merged report, what changed)``: ``new`` (this run) laid over ``old`` (the file a first run wrote).

    Terms are this run's: counts, citations, runs and notes are re-read from the bundle, and a term new
    since the earlier file is added. A description a person wrote into an earlier draft's body is KEPT
    (and the draft re-checked with it by the website's own rules: ``ready_to_send`` only when they pass).
    A term the earlier file had and this run no longer finds is CARRIED OVER as it was, marked
    ``carried_over``, never dropped (it may carry a written description). Refuses a file that is not a
    drafts file, or one written for another bundle."""
    if not isinstance(old, Mapping) or old.get("format") != FORMAT_ID or not isinstance(old.get("fields"), list):
        raise MergeRefused(f"the existing file is not a drafts file ({FORMAT_ID}); --merge updates only one "
                           "`bundle propose-terms` wrote")
    if old.get("bundle_id") != new.get("bundle_id"):
        raise MergeRefused(f"the existing file was written for bundle {old.get('bundle_id')!r}, not this one "
                           f"({new.get('bundle_id')}); write this bundle's drafts to another file")
    before: dict[tuple[str, str], dict] = {}
    for f in old["fields"]:
        if isinstance(f, Mapping) and isinstance(f.get("terms"), list):
            for t in f["terms"]:
                if isinstance(t, Mapping) and isinstance(t.get("term"), str):
                    before[(str(f.get("field_path")), t["term"])] = dict(t)
    merged = {**new, "fields": [dict(f, terms=[dict(t) for t in f["terms"]]) for f in new["fields"]]}
    added: list[dict] = []
    kept_descriptions = updated = 0
    seen: set[tuple[str, str]] = set()
    for f in merged["fields"]:
        for t in f["terms"]:
            key = (f["field_path"], t["term"])
            seen.add(key)
            prior = before.get(key)
            if prior is None:
                added.append({"field_path": key[0], "term": key[1]})
                continue
            updated += 1
            notes = list(t.get("scientist_notes") or ())
            for n in prior.get("scientist_notes") or ():
                if n not in notes:
                    notes.append(n)
            t["scientist_notes"] = notes
            text = _description(prior)
            draft = t.get("draft") or {}
            if text and draft.get("drafted"):
                kept_descriptions += 1
                draft = {**draft, "portal_payload": {**draft["portal_payload"],
                                                     "body": {**draft["portal_payload"]["body"], "description": text}}}
                _, errors, _ = R._validate(dict(draft["portal_payload"]["body"]), sources)
                draft["missing"] = [] if not errors else ["description"]
                draft["ready_to_send"] = False if errors else True
                draft["description_kept_from_earlier_file"] = True
                if errors:
                    draft["problems"] = [{"field": e["field"], "code": e["code"], "message": e["message"]} for e in errors]
                t["draft"] = draft
    carried = 0
    by_path = {f["field_path"]: f for f in merged["fields"]}
    for (path, term), prior in before.items():
        if (path, term) in seen:
            continue
        carried += 1
        entry = {**prior, "carried_over": True,
                 "carried_over_note": ("This run of `bundle propose-terms` no longer finds this term in the bundle; it is "
                                       "kept from the earlier file, with its counts and description as they were.")}
        field = by_path.get(path)
        if field is None:
            old_field = next((f for f in old["fields"] if isinstance(f, Mapping) and f.get("field_path") == path), {})
            field = by_path[path] = {"field_path": path, "judged_by": old_field.get("judged_by"), "occurrences": 0, "terms": []}
            merged["fields"].append(field)
        field["terms"].append(entry)
    merged["fields"].sort(key=lambda f: f["field_path"])
    for f in merged["fields"]:
        f["terms"].sort(key=lambda t: t["term"])
        f["occurrences"] = sum(int(t.get("count") or 0) for t in f["terms"])
    merged["totals"] = {
        "fields": len(merged["fields"]),
        "terms": sum(len(f["terms"]) for f in merged["fields"]),
        "occurrences": sum(f["occurrences"] for f in merged["fields"]),
        "drafts": sum(1 for f in merged["fields"] for t in f["terms"] if (t.get("draft") or {}).get("drafted")),
    }
    change = {"merged_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "terms_before": len(before),
              "added": added, "updated": updated, "descriptions_kept": kept_descriptions, "carried_over": carried}
    merged["merges"] = [*(old.get("merges") or ()), change] if isinstance(old.get("merges"), list) else [change]
    return merged, change


# --- validate: values waiting on a proposal ------------------------------------------------------------

#: Groups ``pending_vocabulary`` names per term before it counts the rest.
PENDING_GROUPS_SHOWN = 10


def pending_vocabulary(bundle: Mapping, fresh: Sequence[tuple[str, Mapping, Mapping]]) -> list[dict]:
    """``[{field_path, term, groups, groups_total, request_ids}]``: each vocabulary request whose field is still
    missing from a confirmed group's draft that it concerns (a group holding one of its runs; every group for a
    request about the whole beamtime). ``validate`` says them, so a missing value waiting on a proposal is named."""
    out: dict[tuple[str, str], dict] = {}
    for req in bundle.get("vocabulary_requests") or ():
        path, term = req.get("field_path"), req.get("term")
        runs = set(req.get("run_ids") or ())
        for group_id, _draft, comp in fresh:
            members = set(comp.get("member_run_ids") or ())
            if runs and not runs & members:
                continue
            if any(f.get("path") == path for f in comp.get("filled") or ()):
                continue
            row = out.setdefault((path, term), {"field_path": path, "term": term, "groups": [], "request_ids": []})
            if group_id not in row["groups"]:
                row["groups"].append(group_id)
            if req.get("request_id") not in row["request_ids"]:
                row["request_ids"].append(req.get("request_id"))
    rows = []
    for row in out.values():
        same = equivalent_term(row["field_path"], row["term"])
        row["groups_total"] = len(row["groups"])
        row["groups"] = row["groups"][:PENDING_GROUPS_SHOWN]
        row["statement"] = (f"{row['field_path']} is missing for {row['groups_total']} group(s) whose answer "
                            f"{row['term']!r} is not on the list: "
                            + (f"use `{same}` (an existing term)." if same else
                               "it waits on a vocabulary proposal (`isaac bundle propose-terms`), or an allowed value."))
        rows.append(row)
    return sorted(rows, key=lambda r: (r["field_path"], r["term"]))
