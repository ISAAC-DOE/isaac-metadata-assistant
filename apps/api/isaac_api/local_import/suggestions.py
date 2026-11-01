"""Suggestions assembled from what an import already holds. Hints, never values.

Three things a scientist is shown so they can answer in one step instead of looking it up:

* :func:`absorber_for_group` - the absorbing element and edge of one record group, from the
  scientists' own processed outputs linked to its runs (``Element.symbol`` /
  ``Element.edge`` header lines) and the beamtime's element evidence (an acquisition macro's
  name, a shared readme). Proposed only when every witness agrees; a scientist confirms it
  with a ``set_absorber`` decision. The official schema has no field for it, so a confirmed
  absorber lives in the draft's ``implicit[]`` (sidecar only), like the hosted path's edge.
  AI readings of the absorber are listed beside the file witnesses (``ai_readings``), never
  counted as one.
* :func:`facility_hints` - what the import knows about WHERE the data was taken: the
  imported folder's name and, only when the runs' scan headers have that system's detector
  column names, the acquisition system those names belong to (the bundle's
  ``acquisition_system`` is a build default, not a match). Text hints on the facility
  questions, never a value: a column name or a folder name is not a statement of a facility.
* :func:`readings_to_interpretations` - a Claude reading pass's findings file
  (``isaac.reading_findings``) turned into AI interpretations on the bundle's targets (record
  groups, for an absorber finding). Each one cites its file, locator and quote, and can lift a
  value to ``needs_review`` and never higher (``bundle.derive_value_state``).
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
    # AI READINGS ARE SHOWN BESIDE THE FILE EVIDENCE, NEVER COUNTED AS IT: ``status``,
    # ``element``, ``edge`` and ``readings`` above are the files' alone. A reading that differs
    # from the files is SAID (``ai_vs_files``), never resolved.
    ai = ai_absorber_readings(bundle, gid)
    files_name = {"element": set(elements), "edge": set(edges)}
    ai_vs_files = {}
    for half in ("element", "edge"):
        said = {r["value"] for r in ai if r["half"] == half}
        if not said:
            ai_vs_files[half] = "no_ai_reading"
        elif not files_name[half]:
            ai_vs_files[half] = "no_file_evidence"
        else:
            ai_vs_files[half] = "agrees" if said <= files_name[half] else "differs"
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
        "ai_readings": ai,
        "ai_vs_files": ai_vs_files,
        "ai_disagrees_with_files": "differs" in ai_vs_files.values(),
        "rule_id": ABSORBER_RULE_ID,
        "statement": "A suggestion from the files, for a scientist to confirm (set_absorber). "
                     "The official schema has no absorber field: a confirmed one is carried in the evidence sidecar. "
                     "AI readings (ai_readings) are suggestions beside the file evidence, never part of it.",
    }


def ai_absorber_readings(bundle: Mapping, group_id: str) -> list[dict]:
    """The distinct AI readings of a group's absorbing element / edge (``system.element`` /
    ``system.edge`` findings recorded on the group), each with its citation and the ids of
    the interpretations that carry it. Suggestions: they never set ``status`` or a value."""
    out: dict[tuple, dict] = {}
    for i in bundle.get("ai_interpretations") or ():
        if i.get("target") != {"kind": "record_group", "id": group_id} or i.get("field_path") not in ABSORBER_FIELDS:
            continue
        key = (i["field_path"], repr(i.get("proposed_value")), i.get("source_path"), i.get("excerpt_locator"))
        r = out.get(key)
        if r is None:
            ref = (i.get("source_refs") or [{}])[0]
            r = out[key] = {
                "field": i["field_path"],
                "half": ABSORBER_FIELDS[i["field_path"]],
                "value": i.get("proposed_value"),
                "source_path": i.get("source_path"),
                "source_id": ref.get("source_id"),
                "locator": i.get("excerpt_locator") or ref.get("locator"),
                "quote": i.get("quote"),
                "strength": i.get("strength"),
                "model_id": (i.get("model") or {}).get("model_id"),
                "finding_id": i.get("finding_id"),
                "interpretation_ids": [],
                # None: read for the whole group (experiment scope); else the named runs only
                "run_ids": None,
            }
        r["interpretation_ids"].append(i["interpretation_id"])
        r.setdefault("_named", []).append(i.get("run_ids"))
    if not out:
        return []
    group = next((g for g in [*(bundle.get("record_groups") or ()), *(bundle.get("superseded_record_groups") or ())]
                  if g["group_id"] == group_id), {})
    members = list(group.get("member_run_keys") or ())
    label_of = {r["run_id"]: r["label"] for r in bundle["runs"]}
    for r in out.values():
        named = r.pop("_named")
        r["run_ids"] = None if any(n is None for n in named) else sorted({x for n in named for x in n})
        # SAID when the reading names fewer than all of the group's runs: it is about those runs
        r["read_for"] = (None if r["run_ids"] is None or len(r["run_ids"]) >= len(members) else
                         f"read for {len(r['run_ids'])} of {len(members)} runs in this group: "
                         + ", ".join(f"{label_of.get(x, x)} ({x})" for x in r["run_ids"]))
    return list(out.values())


def absorber_decisions(bundle: Mapping) -> dict[str, Mapping]:
    """``{group_id: latest set_absorber decision}``."""
    out: dict[str, Mapping] = {}
    for d in bundle.get("scientist_decisions") or ():
        if (d.get("decision") == "set_absorber" and (d.get("target") or {}).get("kind") == "record_group"
                and d.get("element") and d.get("edge")):
            out[d["target"]["id"]] = d
    return out


#: Moved to :mod:`bundle` (2026-10-29), which also uses it to decide whether the bundle shows the
#: acquisition system's name at all; the hint and the bundle apply one test.
_acquisition_system_observed = B.acquisition_system_observed


def facility_hints(bundle: Mapping) -> list[dict]:
    """Text hints for the ``system.facility.*`` questions.

    ``experiment.acquisition_system`` is the engine's BUILD DEFAULT (set on every import,
    whatever the files are), so it is shown ONLY when the runs' scan headers have that system's
    detector column names, and the locator says literally what was seen."""
    hints = []
    system = (bundle.get("experiment") or {}).get("acquisition_system") or {}
    runs, names = _acquisition_system_observed(bundle, system) if system.get("display_name") else (0, [])
    if runs:
        hints.append({
            "kind": "acquisition_system",
            "literal": system["display_name"],
            "locator": (f"{runs} run(s)' scan headers have columns named {', '.join(names)} "
                        f"(the column naming of: {system['display_name']})"),
            "note": ("Column names in the scan headers, nothing more: they match this acquisition system's naming, which is "
                     "not proof of the beamline. A HINT about where the data were taken, never an answer."),
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
FIELD_ALIASES = {
    "context.reaction.name": "context.electrochemistry.reaction",
    "system.absorbing_element": "system.element",
    "system.absorption_edge": "system.edge",
}
#: Findings about the ABSORBER have no record field (the official schema has none): they are
#: recorded on record GROUPS, where the absorber question asks them, ``path -> half``.
ABSORBER_FIELDS = B.ABSORBER_READING_FIELDS
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


def run_paths(bundle: Mapping) -> dict[str, str | None]:
    """``{run_id: relative path of its acquisition file}`` (``None`` when the name is withheld)."""
    path_of = {s["source_id"]: s.get("relative_path") for s in bundle.get("sources") or ()}
    return {r["run_id"]: path_of.get(r.get("acquisition_source_id")) for r in bundle["runs"]}


def run_reference_index(bundle: Mapping) -> dict[str, set[str]]:
    """``{reference: {run_id, ...}}`` for every way a findings file may name a run: its run id, its file
    STEM (``bundle list <dir> runs`` prints it), its acquisition file's relative path, or its label. A
    label is a reordered token list and two runs can share one; a stem can be shared too (the same name in
    two folders): a reference naming more than one run is refused by the caller, never spread over both."""
    index: dict[str, set[str]] = {}
    paths = run_paths(bundle)
    for r in bundle["runs"]:
        for ref in (r["run_id"], r.get("stem"), paths.get(r["run_id"]), r.get("label")):
            if isinstance(ref, str) and ref:
                index.setdefault(ref, set()).add(r["run_id"])
    # a run id that is ALSO another run's stem, path or label (a file named ``run-002``) names two runs:
    # refused by the caller like any other ambiguous reference, never silently resolved to the id (review)
    return index


#: A finding whose field names one of these is about WHERE or BY WHOM the data was taken: its skip lists
#: every such path this bundle holds (``system.facility.*``, ``attribution.produced_by.*``).
_FACILITY_WORDS = ("facility", "beamline", "organization", "organisation", "instrument", "site", "endstation", "institution")
_FACILITY_PREFIXES = ("system.facility.", "attribution.produced_by.")


def nearest_field_paths(path: str, paths: Iterable[str], *, n: int = 3) -> list[str]:
    """The field paths of this bundle a finding's unknown ``path`` most likely meant: those it is the tail
    of (``facility.beamline`` -> ``system.facility.beamline``), else those with its last segment
    (``sample.form`` -> ``sample.sample_form``), else the closest spellings. A suggestion, never applied."""
    import difflib

    held = sorted({p for p in paths if p})
    tail = [p for p in held if p.endswith("." + path)]
    if tail:
        return tail[:n]
    last = path.rsplit(".", 1)[-1]
    same_last = [p for p in held if p.rsplit(".", 1)[-1] == last or p.rsplit(".", 1)[-1].endswith("_" + last)]
    if same_last:
        return same_last[:n]
    return difflib.get_close_matches(path, held, n=n, cutoff=0.75)


def unknown_field_reason(path: str, paths: Iterable[str], near: list[str]) -> str:
    """Why a finding on a field path this bundle has no target for is skipped, with the nearest real path(s)
    and, for a facility field, every facility path this bundle holds."""
    reason = f"this bundle has no missing value or candidate for {path}"
    if near:
        reason += f"; did you mean {' or '.join(near)}?"
    words = set(re.split(r"[._]", path.lower()))
    if words & set(_FACILITY_WORDS):
        facility = sorted(p for p in set(paths) if p and p.startswith(_FACILITY_PREFIXES))
        if facility:
            reason += f" The facility and producer fields here are: {', '.join(facility)}."
    return reason + " Kept in the findings file only: fix field_path and load the file again."


def readings_to_interpretations(bundle: Mapping, findings: Mapping, *, model_id: str) -> dict:
    """Plan the AI interpretations for one findings file. Pure: writes nothing.

    ``{"planned": [(target, entry_fields)], "skipped": [{finding, reason}]}``. A finding
    targets every live run's missing value (or extracted candidate) of its field: all of
    them for ``scope: experiment``, the named runs for ``scope: runs``. A finding about the
    absorber (:data:`ABSORBER_FIELDS`) targets record GROUPS instead: every live group for
    ``experiment``, every live group holding a named run for ``runs``. A finding whose field
    has no target in this bundle is reported, never forced onto another field."""
    if not isinstance(findings, Mapping) or not isinstance(findings.get("findings"), list):
        raise ReadingsRefused("The findings file must be a JSON object with a `findings` list.")
    runs_by_ref = run_reference_index(bundle)
    key_of = {r["run_id"]: r["run_key"] for r in bundle["runs"]}
    live = _live_run_ids(bundle)
    live_groups = [g for g in bundle.get("record_groups") or () if g.get("status") in B.LIVE_GROUP_STATUSES]
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
        absorber = path in ABSORBER_FIELDS
        path_note = ""
        if absorber:
            half = ABSORBER_FIELDS[path]
            ok = B.is_absorber_element if half == "element" else B.is_absorber_edge
            if not ok(f["value"]):
                skipped.append({"finding": fid, "field_path": path, "reason": (
                    f"{f['value']!r} is not an absorber {half} as set_absorber takes it "
                    + ("(an element symbol, e.g. Fe)" if half == "element" else "(exactly one of K, L1, L2, L3, M1-M5)")
                    + "; nothing is normalised")})
                continue
            if not live_groups:
                skipped.append({"finding": fid, "field_path": path,
                                "reason": "an absorber reading is recorded on record groups, and this bundle has no live record group yet (run `isaac bundle group`)"})
                continue
            members = [path]
        else:
            members = [p for p in FIELD_EXPANSIONS.get(path, (path,)) if p in paths]
            if path in FIELD_EXPANSIONS and members:
                path_note = f"The file states the {path.rsplit('.', 1)[-1]} as a whole; split it into {', '.join(m.rsplit('.', 1)[-1] for m in members)} when you confirm. "
            else:
                members = [path]
            if path not in paths and members == [path]:
                near = nearest_field_paths(path, paths)
                skipped.append({"finding": fid, "field_path": path, "did_you_mean": near,
                                "reason": unknown_field_reason(path, paths, near)})
                continue
        scope = (f.get("applies_to") or {}).get("scope") if isinstance(f.get("applies_to"), Mapping) else None
        if scope == "experiment":
            run_ids = sorted(live) + [None]
            groups = live_groups
        elif scope == "runs":
            # `runs` (1.9.x) or the older `run_labels`: each entry a run's file stem, run id, path or label
            applies = f.get("applies_to") or {}
            labels = applies.get("runs") if "runs" in applies else applies.get("run_labels")
            if not isinstance(labels, list) or not labels or not all(isinstance(l, str) for l in labels):
                skipped.append({"finding": fid, "field_path": path, "reason": (
                    "applies_to.runs (or run_labels) must be a non-empty list of run references: each run's file stem "
                    "as `bundle list <dir> runs` prints it, or its run id")})
                continue
            unknown = [l for l in labels if l not in runs_by_ref]
            if unknown:
                skipped.append({"finding": fid, "field_path": path, "reason": (
                    f"run labels not in this bundle: {unknown[:5]} (name a run by its file stem or run id, as "
                    "`bundle list <dir> runs` prints them)")})
                continue
            ambiguous = {l: sorted(runs_by_ref[l]) for l in labels if len(runs_by_ref[l]) > 1}
            if ambiguous:
                said = "; ".join(f"{l!r} names {', '.join(ids[:5])}" for l, ids in list(ambiguous.items())[:3])
                skipped.append({"finding": fid, "field_path": path, "reason": (
                    f"a run reference names more than one run ({said}): name each run by its run id (or its path "
                    "when two runs share a file stem); nothing was spread over both")})
                continue
            named = {rid for l in labels for rid in runs_by_ref[l]}
            run_ids = sorted(named & live)
            named_keys = {key_of[rid] for rid in named}
            groups = [g for g in live_groups if named_keys & set(g.get("member_run_keys") or ())]
            if not (groups if absorber else run_ids):
                skipped.append({"finding": fid, "field_path": path, "reason": "the runs it names are in no live record group"})
                continue
        else:
            skipped.append({"finding": fid, "field_path": path, "reason": "applies_to.scope must be `experiment` or `runs`"})
            continue
        targets = []
        group_runs: dict[str, list[str]] = {}
        if absorber:
            targets = [{"kind": "record_group", "id": g["group_id"]} for g in groups]
            if scope == "runs":
                # the reading is about the NAMED runs: record which of each group's runs those are
                id_of = {r["run_key"]: r["run_id"] for r in bundle["runs"]}
                for g in groups:
                    group_runs[g["group_id"]] = sorted(id_of[k] for k in g.get("member_run_keys") or () if k in named_keys and k in id_of)
        else:
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
            # A group target does not say which field it reads; a value target does.
            "field_path": path if absorber else None,
            "model": {"model_id": model_id},
        }
        for t in targets:
            planned.append((t, {**fields, "run_ids": group_runs.get(t["id"]) if absorber else None}))
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
                "note": ("Suggested by an AI reading of the files. Not file evidence: no parser read this value, and the quote "
                         "is as the reader gave it. Confirm it, or correct it; it is never used on its own."),
            }
        h["targets"] += 1
    return sorted(by_value.values(), key=lambda h: -h["targets"])[:limit]
