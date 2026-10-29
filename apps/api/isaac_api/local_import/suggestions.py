"""Suggestions assembled from what an import already holds. Hints, never values.

Three things a scientist is shown so they can answer in one step instead of looking it up:

* :func:`absorber_for_group` - the absorbing element and edge of one record group, from the
  scientists' own processed outputs linked to its runs (``Element.symbol`` /
  ``Element.edge`` header lines) and the beamtime's element evidence (an acquisition macro's
  name, a shared readme). Proposed only when every witness agrees; a scientist confirms it
  with a ``set_absorber`` decision. The official schema has no field for it, so a confirmed
  absorber lives in the draft's ``implicit[]`` (sidecar only), like the hosted path's edge.
* :func:`facility_hints` - what the import knows about WHERE the data was taken: the
  acquisition-system signature the readers matched and the imported folder's name. Text
  hints on the facility questions, never a value: a file layout or a folder name is not a
  statement of a facility.
* :func:`readings_to_interpretations` - a Claude reading pass's findings file
  (``isaac.reading_findings``) turned into AI interpretations on the bundle's targets. Each
  one cites its file, locator and quote, and can lift a value to ``needs_review`` and never
  higher (``bundle.derive_value_state``).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable, Mapping

from . import bundle as B

ABSORBER_RULE_ID = "isaac.suggest.absorber.v0"
READINGS_FORMAT = "isaac.reading_findings"
_ELEMENT = re.compile(r"[A-Z][a-z]?")
_EDGE = re.compile(r"(?i)(K|L[1-3]|M[1-5])")
_MAX_WITNESSES = 8


def _edge(literal: Any) -> str | None:
    m = _EDGE.fullmatch(str(literal).strip()) if literal is not None else None
    return m.group(1).upper() if m else None


def _element(literal: Any) -> str | None:
    text = str(literal).strip() if literal is not None else ""
    return text if _ELEMENT.fullmatch(text) else None


def absorber_for_group(bundle: Mapping, group: Mapping) -> dict:
    """``{element, edge, status, readings, witnesses, rule_id}`` for ONE record group.

    ``status``: ``agrees`` (every witness that names an element names the same one, and the
    same for the edge, and both are named), ``partial`` (only one of the two is named),
    ``disagrees`` (two witnesses differ: nothing is proposed for that half), ``none``."""
    gid = group["group_id"]
    keys = set(group.get("member_run_keys") or ())
    elements: Counter = Counter()
    edges: Counter = Counter()
    witnesses: list[dict] = []
    sources = {s["source_id"]: s["relative_path"] for s in bundle.get("sources") or ()}

    group_specific, beamtime_wide = [0], [0]

    def note(kind: str, element: str | None, edge: str | None, source_id, locator, extra: dict, literal: str | None = None):
        if element or edge:
            (group_specific if kind == "processed_output_header" else beamtime_wide)[0] += 1
        if element:
            elements[element] += 1
        if edge:
            edges[edge] += 1
        if (element or edge) and len(witnesses) < _MAX_WITNESSES:
            witnesses.append({"kind": kind, "element": element, "edge": edge, "source_id": source_id,
                              "relative_path": sources.get(source_id), "locator": locator, "literal": literal, **extra})

    linked = 0
    for po in bundle.get("processed_outputs") or ():
        links = [l for l in po.get("proposed_links") or () if l.get("group_id") == gid or l.get("run_key") in keys]
        if not links:
            continue
        linked += 1
        states = po.get("states") or {}
        extra = {"processed_output_id": po["processed_output_id"],
                 "link": "proposed by name (isaac.processed_output.link_by_run_stem.v0), not confirmed"}
        # ONE processed output may hold several files (e.g. .nor and .xmu of one stem), each
        # with its own header: every statement is a witness, so two files that disagree show.
        for st in states.get("element_symbol") or ():
            note("processed_output_header", _element(st.get("literal")), None, st.get("source_id"), st.get("locator"), extra, st.get("literal"))
        for st in states.get("element_edge") or ():
            note("processed_output_header", None, _edge(st.get("literal")), st.get("source_id"), st.get("locator"), extra, st.get("literal"))
    for ev in (bundle.get("experiment") or {}).get("element_evidence") or ():
        note("beamtime_element_evidence", _element(ev.get("element")), _edge(ev.get("edge")),
             ev.get("source_id"), ev.get("locator"), {"role": ev.get("role")})

    def pick(c: Counter) -> tuple[str | None, bool]:
        return (next(iter(c)), False) if len(c) == 1 else (None, len(c) > 1)

    element, el_split = pick(elements)
    edge, ed_split = pick(edges)
    if el_split or ed_split:
        status = "disagrees"
    elif element and edge:
        status = "agrees"
    elif element or edge:
        status = "partial"
    else:
        status = "none"
    return {
        "element": element,
        "edge": edge,
        "status": status,
        "readings": {"element": dict(elements), "edge": dict(edges)},
        "linked_processed_outputs": linked,
        "group_specific_statements": group_specific[0],
        "beamtime_wide_statements": beamtime_wide[0],
        "witnesses": witnesses,
        "witness_total": sum(elements.values()) + sum(edges.values()),
        "rule_id": ABSORBER_RULE_ID,
        "statement": "A suggestion from the files, for a scientist to confirm (set_absorber). "
                     "The official schema has no absorber field: a confirmed one is carried in the evidence sidecar.",
    }


def absorber_decisions(bundle: Mapping) -> dict[str, Mapping]:
    """``{group_id: latest set_absorber decision}``."""
    out: dict[str, Mapping] = {}
    for d in bundle.get("scientist_decisions") or ():
        if (d.get("decision") == "set_absorber" and (d.get("target") or {}).get("kind") == "record_group"
                and d.get("element") and d.get("edge")):
            out[d["target"]["id"]] = d
    return out


def facility_hints(bundle: Mapping) -> list[dict]:
    """Text hints for the ``system.facility.*`` questions."""
    hints = []
    system = (bundle.get("experiment") or {}).get("acquisition_system") or {}
    if system.get("display_name"):
        hints.append({
            "kind": "acquisition_system",
            "literal": system["display_name"],
            "locator": f"the readers matched acquisition system `{system.get('system_id')}`",
            "note": "The files have this instrument's export layout. A HINT about where they were taken, never an answer.",
        })
    hints.append({
        "kind": "folder_name",
        "literal": bundle["source_root"]["label"],
        "locator": "the imported folder's name",
        "note": "A facility or beamline in a folder name is a HINT to ask about, never an answer.",
    })
    return hints


# --- a Claude reading pass's findings -> AI interpretations ------------------------------------

#: A finding's field may name a path the bundle spells differently. Only exact renames.
FIELD_ALIASES = {"context.reaction.name": "context.electrochemistry.reaction"}
#: A finding about a whole OBJECT the schema splits into members: the reading is offered on
#: each member, unsplit, with a note. Splitting "0.1 M KOH" into a name and a number is the
#: scientist's step, never this module's.
FIELD_EXPANSIONS = {
    "context.electrochemistry.electrolyte": ("context.electrochemistry.electrolyte.name",
                                             "context.electrochemistry.electrolyte.concentration_M"),
}


class ReadingsRefused(ValueError):
    pass


def _cited_path_ok(rel: str) -> bool:
    """Relative to the imported folder, or ONE leading ``../`` for a document beside it."""
    if not rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel) or "\x00" in rel:
        return False
    parts = rel.replace("\\", "/").split("/")
    rest = parts[1:] if parts[0] == ".." else parts
    return bool(rest) and ".." not in rest and all(p not in ("",) for p in rest)


def _live_run_ids(bundle: Mapping) -> set[str]:
    by_key = {r["run_key"]: r["run_id"] for r in bundle["runs"]}
    groups = bundle.get("record_groups") or ()
    if not groups:
        return {r["run_id"] for r in bundle["runs"]}
    return {by_key[k] for g in groups if g.get("status") in B.LIVE_GROUP_STATUSES
            for k in g.get("member_run_keys") or () if k in by_key}


def readings_to_interpretations(bundle: Mapping, findings: Mapping, *, model_id: str) -> dict:
    """Plan the AI interpretations for one findings file. Pure: writes nothing.

    ``{"planned": [(target, entry_fields)], "skipped": [{finding, reason}]}``. A finding
    targets every live run's missing value (or extracted candidate) of its field: all of
    them for ``scope: experiment``, the named runs for ``scope: runs``. A finding whose field
    has no target in this bundle is reported, never forced onto another field."""
    if not isinstance(findings, Mapping) or not isinstance(findings.get("findings"), list):
        raise ReadingsRefused("The findings file must be a JSON object with a `findings` list.")
    runs_by_label: dict[str, list[str]] = {}
    for r in bundle["runs"]:
        runs_by_label.setdefault(r["label"], []).append(r["run_id"])
    live = _live_run_ids(bundle)
    src_by_path = {s["relative_path"]: s["source_id"] for s in bundle["sources"]}
    missing: dict[tuple[str | None, str], list[str]] = {}
    for m in bundle["missing_values"]:
        missing.setdefault((m["run_id"], m["target_field_path"]), []).append(m["value_id"])
    cands: dict[tuple[str | None, str], list[str]] = {}
    for c in bundle["candidates"]:
        if c["target_field_path"]:
            cands.setdefault((c["run_id"], c["target_field_path"]), []).append(c["candidate_id"])
    paths = {p for (_, p) in missing} | {p for (_, p) in cands}

    planned: list[tuple[dict, dict]] = []
    skipped: list[dict] = []
    for i, f in enumerate(findings["findings"]):
        fid = f"finding-{i + 1:03d}"
        if not isinstance(f, Mapping):
            skipped.append({"finding": fid, "reason": "not an object"})
            continue
        path = FIELD_ALIASES.get(str(f.get("field_path") or ""), str(f.get("field_path") or ""))
        source = f.get("source") if isinstance(f.get("source"), Mapping) else {}
        quote = f.get("quote")
        if not path or f.get("value") in (None, "") or not source.get("path") or not source.get("locator") or not quote:
            skipped.append({"finding": fid, "field_path": path, "reason": "a finding needs field_path, value, source.path, source.locator and quote"})
            continue
        members = [p for p in FIELD_EXPANSIONS.get(path, (path,)) if p in paths]
        if path in FIELD_EXPANSIONS and members:
            path_note = f"The file states the {path.rsplit('.', 1)[-1]} as a whole; split it into {', '.join(m.rsplit('.', 1)[-1] for m in members)} when you confirm. "
        else:
            members, path_note = [path], ""
        if path not in paths and members == [path]:
            skipped.append({"finding": fid, "field_path": path,
                            "reason": "this bundle has no missing value or candidate for this field; kept in the findings file only"})
            continue
        scope = (f.get("applies_to") or {}).get("scope") if isinstance(f.get("applies_to"), Mapping) else None
        if scope == "experiment":
            run_ids = sorted(live) + [None]
        elif scope == "runs":
            labels = (f.get("applies_to") or {}).get("run_labels")
            if not isinstance(labels, list) or not labels or not all(isinstance(l, str) for l in labels):
                skipped.append({"finding": fid, "field_path": path, "reason": "applies_to.run_labels must be a non-empty list of run labels"})
                continue
            unknown = [l for l in labels if l not in runs_by_label]
            if unknown:
                skipped.append({"finding": fid, "field_path": path, "reason": f"run labels not in this bundle: {unknown[:5]}"})
                continue
            named = {rid for l in labels for rid in runs_by_label[l]}
            run_ids = sorted(named & live)
            if not run_ids:
                skipped.append({"finding": fid, "field_path": path, "reason": "the runs it names are in no live record group"})
                continue
        else:
            skipped.append({"finding": fid, "field_path": path, "reason": "applies_to.scope must be `experiment` or `runs`"})
            continue
        targets = []
        for rid in run_ids:
            for member in members:
                targets += [{"kind": "missing_value", "id": v} for v in missing.get((rid, member), ())]
                targets += [{"kind": "candidate", "id": c} for c in cands.get((rid, member), ())]
        if not targets:
            skipped.append({"finding": fid, "field_path": path, "reason": "no target for this field on the runs it names"})
            continue
        rel = str(source["path"])
        if not _cited_path_ok(rel):
            skipped.append({"finding": fid, "field_path": path,
                            "reason": "source.path must be relative to the imported folder (one leading ../ for a document beside it), never absolute"})
            continue
        source_id = src_by_path.get(rel)
        strength = f.get("strength") if f.get("strength") in ("stated", "inferred") else None
        fields = {
            "proposed_value": f["value"],
            "rationale": (path_note + str(f.get("reasoning") or ""))[:1000],
            "source_refs": [{"source_id": source_id, "locator": str(source["locator"])[:300]}],
            "excerpt_locator": str(source["locator"])[:300],
            "source_path": rel[:500],
            "quote": str(quote)[:300],
            "strength": strength,
            "finding_id": fid,
            "model": {"model_id": model_id},
        }
        for t in targets:
            planned.append((t, fields))
    return {"planned": planned, "skipped": skipped}


def ai_hints(bundle: Mapping, target_ids: Iterable[str], *, limit: int = 5) -> list[dict]:
    """One hint per distinct AI-proposed value over ``target_ids``, with how many targets
    it was read for and its first citation. For the consolidated questions."""
    wanted = set(target_ids)
    by_value: dict[str, dict] = {}
    for i in bundle.get("ai_interpretations") or ():
        if (i.get("target") or {}).get("id") not in wanted:
            continue
        key = repr(i.get("proposed_value"))
        h = by_value.get(key)
        if h is None:
            ref = (i.get("source_refs") or [{}])[0]
            h = by_value[key] = {
                "kind": "ai_suggestion",
                "literal": i.get("proposed_value"),
                "locator": ref.get("locator"),
                "source_id": ref.get("source_id"),
                "source_path": i.get("source_path"),
                "quote": i.get("quote"),
                "strength": i.get("strength"),
                "model_id": (i.get("model") or {}).get("model_id"),
                "targets": 0,
                "note": "Suggested by an AI reading of the files; the quote is as the reader gave it. Confirm it, or correct it; it is never used on its own.",
            }
        h["targets"] += 1
    return sorted(by_value.values(), key=lambda h: -h["targets"])[:limit]
