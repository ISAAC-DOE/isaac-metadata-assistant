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
  groups, for an absorber finding). Each one cites its file, locator and quote, and on its own can lift a
  value to ``needs_review`` and never higher (``bundle.derive_value_state``); since 1.19.0 (DEC-97) a reading whose
  quote check is stored on it, strength ``stated``, and whose quote itself states the value can fill it under
  ``bundle.FILL_READING_STATED_RULE_ID``; an inferred reading never fills.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

from . import bundle as B
from . import scan_notes as SN

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


#: 1.16.0 (audit of 18 Nov 2026, rule 14): an SSRL XDC scan whose "Requested Energy" grid has a finest-step window
#: strictly inside its range (a pre-edge region before it and a post-edge region after it: the XANES region) names the
#: absorption edge that window brackets (``readers.xray_tables``, edges of 1 keV and up); where it brackets several, a
#: K or L3 edge (the edges one scans) is taken when exactly one is; otherwise nothing. A run's scans that name
#: different edges name none. A witness for the absorber SUGGESTION only (confirm_absorber), never a value.
SCANNED_EDGE_RULE_ID = "isaac.suggest.absorber_from_scanned_range.v1"
SCANNED_EDGE_MIN_EV = 1000.0
#: ``experiment.element_evidence[].role`` of a witness this rule gives (one per run, with its ``run_key``)
SCANNED_EDGE_ROLE = "scanned_range"


def scanned_edge(check: Mapping | None) -> dict | None:
    """``{element, edge, energy_eV, window_eV, range_eV, step_eV}`` the reader's energy check of ONE scan names
    (:data:`SCANNED_EDGE_RULE_ID`), or ``None``."""
    from .readers import xray_tables as X

    if not isinstance(check, Mapping) or not check.get("finest_window_eV") or not check.get("range_eV"):
        return None
    (lo, hi), (start, stop) = check["finest_window_eV"], check["range_eV"]
    if not (start < lo and hi < stop):
        return None  # a scan sampled uniformly (an alignment, a check): no XANES region, no edge named
    edges = [e for e in X.edges_between(lo, hi) if e["energy_eV"] >= SCANNED_EDGE_MIN_EV]
    if len(edges) > 1:
        edges = [e for e in edges if e["edge"] in ("K", "L3")]
    if len(edges) != 1:
        return None
    return {**edges[0], "window_eV": [lo, hi], "range_eV": [start, stop], "step_eV": check.get("finest_step_eV")}


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
            (group_specific if kind in ("processed_output_header", "scanned_range") else beamtime_wide)[0] += 1
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
        rule = links[0].get("rule_id") or "isaac.processed_output.link_by_run_stem.v0"
        extra = {"processed_output_id": po["processed_output_id"],
                 "link": (f"proposed by legacy number ({rule}), not confirmed" if rule.endswith("link_by_legacy_number.v0")
                          else f"proposed by name ({rule}), not confirmed")}
        # ONE processed output may hold several files (e.g. .nor and .xmu of one stem), each
        # with its own header: every statement is a witness, so two files that disagree show.
        for st in states.get("element_symbol") or ():
            note("processed_output_header", _element(st.get("literal")), None, st.get("source_id"), st.get("locator"), extra, st.get("literal"))
        for st in states.get("element_edge") or ():
            note("processed_output_header", None, _edge(st.get("literal")), st.get("source_id"), st.get("locator"), extra, st.get("literal"))
    for ev in (bundle.get("experiment") or {}).get("element_evidence") or ():
        if ev.get("role") == SCANNED_EDGE_ROLE:
            # 1.16.0: the edge a run's OWN scans bracket, a witness for that run's group only
            if ev.get("run_key") in keys:
                note("scanned_range", _element(ev.get("element")), _edge(ev.get("edge")), ev.get("source_id"),
                     ev.get("locator"), {"role": ev.get("role"), "rule_id": SCANNED_EDGE_RULE_ID},
                     ev.get("literal"))
            continue
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
    # r5d H2: the SPEC headers' own fingerprint (account and column names) first, beside the folder's name
    fp = system.get("fingerprint") or {}
    folder_disagrees = fp.get("disagrees_with_folder_name")
    runs, names = _acquisition_system_observed(bundle, system) if system.get("display_name") else (0, [])
    for m in fp.get("matches") or ():
        if runs and m.get("system_id") == system.get("system_id"):
            continue  # the acquisition-system hint below already names this system, from the same columns
        note = ("The SPEC account and column names these files' headers state, nothing more: they match data measured at "
                "this beamline, which is not proof of where these were taken. A HINT, never an answer.")
        if folder_disagrees:
            note += (f" The folder's name '{folder_disagrees['folder_name']}' names '{folder_disagrees['beamline']}': "
                     "the two hints disagree, so ask the scientist which beamline it was.")
        hints.append({
            "kind": "acquisition_fingerprint",
            "literal": f"{m['facility']} {m['beamline']}",
            "locator": B.fingerprint_said(m),
            "branch_stated": bool(m.get("branch_stated")),
            "note": note,
        })
    if runs:
        hints.append({
            "kind": "acquisition_system",
            "literal": system["display_name"],
            "locator": (f"{runs} run(s)' scan headers have columns named {', '.join(names)} "
                        f"(the column naming of: {system['display_name']})"),
            "note": ("Column names in the scan headers, nothing more: they match this acquisition system's naming, which is "
                     "not proof of the beamline. A HINT about where the data were taken, never an answer."),
        })
    folder_note = "A facility or beamline in a folder name is a HINT to ask about, never an answer."
    if folder_disagrees:
        folder_note += (" The SPEC headers' own fingerprint names another beamline: the two hints disagree, so ask the "
                        "scientist which beamline it was.")
    hints.append({
        "kind": "folder_name",
        "literal": bundle["source_root"]["label"],
        "locator": "the imported folder's name",
        "note": folder_note,
    })
    return hints


#: TECHNIQUE HINTS NEVER SHOW CODE (measured on two real BL15-2 beamtimes: the ``system.technique`` hints were
#: ``IrL3_xas`` and ``trigger`` from macro ``def`` lines, ``Pt_XAS.mac`` from a ``qdo`` include and
#: ``extract_voltage_and_save(target_directory,`` from a Python helper read as a macro). A technique hint is shown
#: unless it is code that names no technique (:func:`technique_hint_is_code`: a technique word is looked for FIRST).
#: The readings stay evidence on their candidates and conflicts; only the hints leave them out, and say so.
TECHNIQUE_HINT_RULE_ID = "isaac.suggest.technique_hint_not_code.v1"
TECHNIQUE_PATH = "system.technique"
#: the hint kinds that quote what a file holds (an AI reading is a reading, said as one, and is never filtered here)
LITERAL_HINT_KINDS = frozenset({"file_literal", "related_reading", "reading"})
#: a file that holds code: a SPEC macro, a script or a notebook
_CODE_FILE = re.compile(r"\.(?:mac|py|pyc|ipynb|m|pro|sh|bash|pl|bat|cmd|js|r)$", re.IGNORECASE)
#: a locator that is a macro statement (``line 2 `def```, ``line 1 `qdo` (before any newfile declaration)``)
_MACRO_LOCATOR = re.compile(r"`(?:def|qdo|rdef|cdef|macro)`", re.IGNORECASE)
#: an identifier with an underscore and no space (``syn_helper``, ``IrL3_xas``): a function or macro name
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]*$")
#: SPEC and beamline macro words that are never a technique
_MACRO_WORDS = frozenset({"trigger", "qdo", "def", "newfile", "ascan", "dscan", "gscan", "mono", "mv", "umv", "ct",
                          "setup", "init", "run", "scan", "loop", "wait", "sleep", "move"})
#: words that name a technique beside the schema's own values (matched as whole words, without case)
_TECHNIQUE_WORDS = frozenset({"xas", "xanes", "exafs", "xafs", "herfd", "xes", "rixs", "xrf", "xrd", "saxs", "waxs",
                              "xps", "absorption", "emission", "diffraction", "ptychography", "tomography",
                              "kbeta", "kalpha", "vtc"})


def _technique_values() -> frozenset[str]:
    return frozenset(str(v).casefold() for v in (B.allowed_values(TECHNIQUE_PATH) or ()))


#: what a technique hint is split on before its words are compared (``HERFD_XAS``, ``XANES,EXAFS``,
#: ``fluorescence XAS (Lytle)``, ``HERFD-XAS``, ``XAS/XES``)
_TECHNIQUE_SPLIT = re.compile(r"[_,()\-/\s]+")
#: a path: a folder separator, or a file name with an extension (``Pt_XAS.mac``, ``scans/run/plot.py``)
_PATH_LIKE = re.compile(r"/|\\|\.[A-Za-z0-9]{1,5}$")


def _words(text: Any) -> list[str]:
    return [w for w in _TECHNIQUE_SPLIT.split(str(text or "").casefold()) if w]


def names_a_technique(text: Any) -> bool:
    """Does ``text`` name a technique? Its words (split on ``_ , ( ) - /`` and spaces, without case) hold a technique
    word (:data:`_TECHNIQUE_WORDS`) or, word for word in order, one of ``system.technique``'s allowed values
    (``cyclic_voltammetry``, ``UV_Vis``, ``HERFD-XAS``)."""
    words = _words(text)
    if not words:
        return False
    if set(words) & _TECHNIQUE_WORDS:
        return True
    for value in _technique_values():
        v = _words(value)
        if v and any(words[i:i + len(v)] == v for i in range(len(words) - len(v) + 1)):
            return True
    return False


def looks_like_code(hint: Mapping) -> bool:
    """A call (``(``), a macro or function name (read at a macro ``def`` / ``qdo`` line, a macro word, an underscore
    identifier, a bare name read from a code file) or a path."""
    lit = str(hint.get("literal") or "").strip()
    if "(" in lit or _PATH_LIKE.search(lit) or _CODE_FILE.search(lit):
        return True
    if _MACRO_LOCATOR.search(str(hint.get("locator") or "")) or lit.casefold() in _MACRO_WORDS or _IDENTIFIER.match(lit):
        return True
    return bool(_CODE_FILE.search(str(hint.get("relative_path") or ""))) and " " not in lit


def technique_hint_is_code(hint: Mapping) -> bool:
    """:data:`TECHNIQUE_HINT_RULE_ID`: is this technique hint (``literal``, ``locator``, ``relative_path``) code to
    leave out? A hint that NAMES A TECHNIQUE is kept, whatever its spelling (checked first: ``HERFD_XAS``,
    ``IrL3_xas``, ``fluorescence XAS (Lytle)``); of the rest, only what looks like code (:func:`looks_like_code`) is
    left out, and an empty one."""
    lit = str(hint.get("literal") or "").strip()
    if not lit:
        return True
    if names_a_technique(lit):
        return False
    return looks_like_code(hint)


def technique_hints(path: str | None, hints: list[dict]) -> tuple[list[dict], int]:
    """``(hints kept, how many were left out)`` for a question at ``path``: at ``system.technique`` every literal
    hint that is code naming no technique is left out (:func:`technique_hint_is_code`); any other path, unchanged."""
    if path != TECHNIQUE_PATH:
        return hints, 0
    kept = [h for h in hints if h.get("kind") not in LITERAL_HINT_KINDS or not technique_hint_is_code(h)]
    return kept, len(hints) - len(kept)


def technique_hints_left_out_sentence(n: int) -> str:
    """The sentence a technique question adds when :func:`technique_hints` left ``n`` hints out."""
    return (f" {n} of the files' readings for it are macro or script names (a `def` or `qdo` line, a helper script) "
            "that name no technique, so they are not shown as hints: name the technique from allowed_values.")


def beamline_hints_sentence(bundle: Mapping) -> str:
    """r5d H2: one plain sentence for the beamline question when the SPEC headers' fingerprint disagrees with the
    folder's name, matches several beamlines, or is not the build's default system; ``""`` otherwise."""
    fp = ((bundle.get("experiment") or {}).get("acquisition_system") or {}).get("fingerprint") or {}
    matches = fp.get("matches") or ()
    if not matches:
        return ""
    said = "; ".join(B.fingerprint_said(m) for m in matches)
    ask = ": ask the scientist which beamline it was (system.facility.beamline)."
    folder = fp.get("disagrees_with_folder_name")
    if folder:
        return (f" The files' beamline hints disagree: the folder's name '{folder['folder_name']}' names "
                f"'{folder['beamline']}', while the SPEC headers state {said}. Neither is an answer" + ask)
    if len({m["beamline"] for m in matches}) > 1:
        return f" The SPEC headers match more than one beamline: {said}. Hints, never answers" + ask
    if fp.get("contradicts_build_default"):
        return (f" The SPEC headers state {said}; this build reads every import as BL15-2 data by default, "
                "which these headers do not match. A hint, never an answer" + ask)
    return ""


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


#: r6 I4: words a reading uses to say the files state NO value. Such a reading is no value: shown to the scientist it
#: would read "An AI reading suggests 'not stated'", and propose-terms would draft it as a vocabulary term.
NOTHING_STATED_READINGS = frozenset({
    "not stated", "none stated", "nothing stated", "not given", "not specified", "unspecified", "not mentioned",
    "not reported", "not recorded", "not found", "not available", "no value", "not in the files", "not in file",
    "unknown", "n/a",
})


def nothing_stated_reason(value: Any, path: str | None) -> str | None:
    """r6 I4: why an AI reading of ``value`` for ``path`` is not kept because it says the files state nothing, or
    ``None``. A word off a field's list is kept (``propose-terms`` drafts it as a vocabulary request); a value on the
    field's own list is kept, compared without case (r6 review L4: ``Unknown`` for a list holding ``unknown``)."""
    if not isinstance(value, str):
        return None
    said = re.sub(r"[\s.]+", " ", value.casefold()).strip(" .")
    if said not in NOTHING_STATED_READINGS:
        return None
    allowed = B.allowed_values(path) if path else None
    if allowed and value.strip().casefold() in {str(a).casefold() for a in allowed}:
        return None
    return (f"{value!r} says the files state no value, so it is not recorded as a reading: it would be shown to the "
            "scientist as an AI suggestion of a value. When the files state none, record nothing: the question stays "
            "asked, and the scientist answers it. Say in your report that you found no statement of it.")


def readings_to_interpretations(bundle: Mapping, findings: Mapping, *, model_id: str,
                                quote_results: Mapping[str, Mapping] | None = None) -> dict:
    """Plan the AI interpretations for one findings file. Pure: writes nothing.

    ``{"planned": [(target, entry_fields)], "scan_notes": [entry], "skipped": [{finding, reason}]}``.
    ``quote_results`` (:func:`reading_check.check_findings`, by finding id): a finding whose quote was NOT
    found is refused (``refused: quote_not_found``), never planned. A finding is also refused when a run
    reference names no run (``unknown_run``) or more than one (``ambiguous_run``), or when its value is not
    on its field's allowed list (``not_allowed_value``). A ``scan_note`` finding
    (:mod:`.scan_notes`) is planned as a scan note. A finding
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
    stale_lines = stale_comment_index(bundle)

    planned: list[tuple[dict, dict]] = []
    scan_notes: list[dict] = []
    skipped: list[dict] = []
    for i, f in enumerate(findings["findings"]):
        fid = f"finding-{i + 1:03d}"
        if not isinstance(f, Mapping):
            skipped.append({"finding": fid, "reason": "not an object"})
            continue
        checked = (quote_results or {}).get(fid)
        if checked is not None and checked.get("result") != "pass":
            # THE QUOTE CHECK (reading_check): a quote not found as cited is never loaded; the reader fixes the file
            skipped.append({"finding": fid, "field_path": f.get("field_path"), "kind": f.get("kind"), "refused": "quote_not_found",
                            "reason": f"its quote was not found as cited: {checked.get('reason')}"})
            continue
        if f.get("kind") not in (None, "field", SN.KIND):
            skipped.append({"finding": fid, "reason": f"unknown finding kind {str(f.get('kind'))[:40]!r}: a finding is a field reading or `{SN.KIND}`"})
            continue
        if f.get("kind") == SN.KIND:
            entry, skip = SN.plan_scan_note(bundle, f, fid=fid, runs_by_ref=runs_by_ref, model_id=model_id,
                                            canonical_path=(checked or {}).get("canonical_path"))
            if skip is not None:
                skipped.append(skip)
            else:
                scan_notes.append(entry)
            continue
        path = FIELD_ALIASES.get(str(f.get("field_path") or ""), str(f.get("field_path") or ""))
        source = f.get("source") if isinstance(f.get("source"), Mapping) else {}
        quote = f.get("quote")
        if not path or f.get("value") in (None, "") or not source.get("path") or not source.get("locator") or not quote:
            skipped.append({"finding": fid, "field_path": path, "reason": "a finding needs field_path, value, source.path, source.locator and quote"})
            continue
        if (nothing := nothing_stated_reason(f.get("value"), path)) is not None:
            # r6 review M3: as `annotate --target` refuses it (mutations.nothing_stated_refusal), never a suggestion
            skipped.append({"finding": fid, "field_path": path, "reason": nothing})
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
            off_list = [(m, allowed) for m in members if (allowed := B.allowed_values(m)) is not None and f["value"] not in allowed]
            if off_list:
                m, allowed = off_list[0]
                near = [a for a in allowed if str(a).casefold() == str(f["value"]).strip().casefold()]
                skipped.append({"finding": fid, "field_path": path, "refused": "not_allowed_value", "reason": (
                    f"{f['value']!r} is not one of the allowed values for {m}"
                    + (f" (did you mean {near[0]!r}? the value is compared exactly)" if near else
                       f": {', '.join(map(str, allowed[:12]))}{', ...' if len(allowed) > 12 else ''}")
                    + ". Write one allowed value, or no finding, and tell the scientist what the file says")})
                continue
        scope = (f.get("applies_to") or {}).get("scope") if isinstance(f.get("applies_to"), Mapping) else None
        sample_note = ""
        if scope == "samples":
            # 1.22.0 (fix round of DEC-100, the real-beamtime replay R3): a finding about named SAMPLES reaches EVERY run of
            # each (the bundle's sample groupings, by the sample's name as the files write it or its sample id); it is
            # kept as a reading of those runs (scope `runs`), so every rule that reads a runs-scoped reading reads it
            applies = f.get("applies_to") or {}
            names = applies.get("samples")
            if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
                skipped.append({"finding": fid, "field_path": path, "reason": (
                    "applies_to.samples must be a non-empty list of sample names, as the files write them (or sample "
                    "ids, as `bundle list <dir> samples` prints them)")})
                continue
            of_sample = runs_of_samples(bundle, names)
            unknown = [n for n in names if not of_sample.get(n)]
            if unknown:
                skipped.append({"finding": fid, "field_path": path, "refused": "unknown_sample", "reason": (
                    f"sample names not in this bundle: {unknown[:5]} (name a sample as its files write it, e.g. its "
                    "code in the file names, or by its sample id)")})
                continue
            named = {rid for n in names for rid in of_sample[n]}
            run_ids = sorted(named & live)
            named_keys = {key_of[rid] for rid in named}
            groups = [g for g in live_groups if named_keys & set(g.get("member_run_keys") or ())]
            if not (groups if absorber else run_ids):
                skipped.append({"finding": fid, "field_path": path, "reason": "the samples it names are in no live record group"})
                continue
            sample_note = f"About sample {', '.join(names)}: every one of its {len(named)} run(s). "
            scope = "runs"
        elif scope == "experiment":
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
                skipped.append({"finding": fid, "field_path": path, "refused": "unknown_run", "reason": (
                    f"run labels not in this bundle: {unknown[:5]} (name a run by its file stem or run id, as "
                    "`bundle list <dir> runs` prints them)")})
                continue
            ambiguous = {l: sorted(runs_by_ref[l]) for l in labels if len(runs_by_ref[l]) > 1}
            if ambiguous:
                said = "; ".join(f"{l!r} names {', '.join(ids[:5])}" for l, ids in list(ambiguous.items())[:3])
                skipped.append({"finding": fid, "field_path": path, "refused": "ambiguous_run", "reason": (
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
            skipped.append({"finding": fid, "field_path": path,
                            "reason": "applies_to.scope must be `experiment`, `runs` or `samples`"})
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
        # the path as the folder spells it (`./a.txt`, `A.TXT` on a case-insensitive disk): its source id is found by it
        rel = str((checked or {}).get("canonical_path") or source["path"])
        if not _cited_path_ok(rel):
            skipped.append({"finding": fid, "field_path": path,
                            "reason": "source.path must be relative to the imported folder (one leading ../ for a document beside it), never absolute"})
            continue
        source_id = src_by_path.get(rel)
        strength = f.get("strength") if f.get("strength") in ("stated", "inferred") else None
        # STALE_COMMENT_RULE_ID: a reading of the potential from a comment line flagged as possibly left over from an
        # earlier run is never loaded as "stated": it is an inference, and the suggestion says why
        cited = re.search(r"\d+", str(source["locator"]))
        stale = stale_lines.get((rel, int(cited.group(0)))) if path in STALE_FIELDS and cited else None
        if stale is not None:
            strength = "inferred"
            path_note = f"The line cited is possibly stale: {stale} Loaded as an inference, never as stated. " + path_note
        fields = {
            "proposed_value": f["value"],
            "rationale": (sample_note + path_note + str(f.get("reasoning") or ""))[:1000],
            "source_refs": [{"source_id": source_id, "locator": str(source["locator"])[:300]}],
            "excerpt_locator": str(source["locator"])[:300],
            "source_path": rel[:500],
            "quote": str(quote)[:300],
            "strength": strength,
            "finding_id": fid,
            # A group target does not say which field it reads; a value target does.
            "field_path": path if absorber else None,
            # 1.19.0: what the finding says it is about (`experiment`: the whole beamtime; `runs`: the runs it names).
            # A beamtime-scoped reading never fills a run-level field (DEC-69, bundle.reading_scope_problem)
            "scope": scope,
            # 1.19.0: the field the finding named, when it was offered unsplit on several fields (the electrolyte as a
            # whole on its name and its concentration): splitting it is the scientist's step, so it never fills
            "finding_field_path": path if (not absorber and path in FIELD_EXPANSIONS and members != [path]) else None,
            "model": {"model_id": model_id},
        }
        for t in targets:
            planned.append((t, {**fields, "run_ids": group_runs.get(t["id"]) if absorber else None}))
    return {"planned": planned, "scan_notes": scan_notes, "skipped": skipped}


def runs_of_samples(bundle: Mapping, names: Sequence[str]) -> dict[str, list[str]]:
    """1.22.0 (R3): ``{name: [run ids]}``: the runs of every sample of the bundle a name names, by its sample id or a
    sample-name reading its files give (compared without case or punctuation, ``reading_tie.label_key``); a bare
    number (a group token, an electrode number) names no sample. An unknown name maps to ``[]``."""
    from .reading_tie import label_key

    out: dict[str, list[str]] = {}
    for name in names:
        key = label_key(name)
        runs: set[str] = set()
        if key and not key.isdigit():
            for smp in bundle.get("samples") or ():
                if not isinstance(smp, Mapping):
                    continue
                keys = {label_key(smp.get("sample_id"))} | {label_key(x) for x in smp.get("sample_name_readings") or ()}
                if key in keys - {""}:
                    runs.update(str(r) for r in smp.get("run_ids") or ())
        out[name] = sorted(runs)
    return out


def ai_hints(bundle: Mapping, target_ids: Iterable[str], *, limit: int = 5) -> list[dict]:
    """One hint per distinct AI-proposed value over ``target_ids``, with how many targets
    it was read for and its first citation. For the consolidated questions."""
    wanted = set(target_ids)
    by_value: dict[str, dict] = {}
    # r4-b L7: a hint names the FILE it cites (the skill says no ids): an interpretation that kept only a source id
    path_of = {s["source_id"]: s.get("relative_path") for s in bundle.get("sources") or ()}
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
                "source_path": i.get("source_path") or path_of.get(ref.get("source_id")),
                "quote": i.get("quote"),
                "strength": i.get("strength"),
                "model_id": (i.get("model") or {}).get("model_id"),
                "targets": 0,
                "note": ("Suggested by an AI reading of the files. Not file evidence: no parser read this value, and the quote "
                         "is as the reader gave it. Confirm it, or correct it: it is asked because no registered reading "
                         "rule filled it (an inference, an unchecked quote, a quote that does not state the value, a "
                         "disagreement, or a run-level or sample field read for the whole beamtime)."),
            }
        h["targets"] += 1
    return sorted(by_value.values(), key=lambda h: -h["targets"])[:limit]


# --- suggestions the IMPORT reads from the files themselves (audit of 18 Nov 2026) ------------------------------------
#
# A value the files state is read; a value that needs one step of interpretation is a SUGGESTION: a candidate that
# NEEDS REVIEW, with the evidence it rests on and a reason that says what was read and why it is only a suggestion. A
# scientist confirms it (one decision) or corrects it; no record carries it before that. Each is built through the
# engine's own candidate type and ``bundle._candidate_record``, so its shape is every other candidate's and the
# existing questions ask it. Nothing here writes a value silently.


def suggested_candidate(*, engine_id: str, bundle_cid: str, run_id: str | None, key: str, path: str, value: Any,
                        rule_id: str, rule: str, reason: str, witnesses: Sequence[Mapping], writable) -> dict:
    """ONE candidate that needs review (``value`` may be ``None``: the reason then says what the files write and
    why no value is offered). ``witnesses``: ``{relative_path, source_id, locator, literal, supports, normalization}``
    in the order they are shown; the first ``supports`` one carries the value."""
    from .. import historical_import as hist

    evidence = []
    for w in list(witnesses)[:B.MAX_EVIDENCE_PER_CANDIDATE]:
        rel = w.get("relative_path")
        evidence.append({
            "evidence_id": f"{bundle_cid}.e{len(evidence) + 1:03d}",
            "source_id": w.get("source_id"),
            "relative_path": rel if w.get("source_id") else None,
            "locator_kind": "source_file" if w.get("source_id") else "described",
            "locator": str(w.get("locator") or ""),
            "statement_key": key,
            "literal_value": w.get("literal"),
            "method": "deterministic_parser",
            "method_id": rule_id,
            "relation": "supports" if value is not None and w.get("supports") else "context",
            "reading_index": None,
            "normalization": list(w.get("normalization") or ()),
        })
    sources = tuple(dict.fromkeys(str(w.get("relative_path")) for w in witnesses if w.get("relative_path")))
    engine = hist.SemanticCandidate(
        candidate_id=engine_id,
        kind=hist.CANDIDATE_KIND_FIELD,
        determinism=hist.DETERMINISM_DETERMINISTIC,
        rule=rule,
        supporting_source_ids=sources,
        target_field_path=path,
        proposed_value=value,
        not_proposable_reason=reason,
        supporting_statement_total=len(witnesses),
        distinct_sources=len(sources),
    )
    return B._candidate_record(engine, bundle_cid=bundle_cid, run_id=run_id, key=key, evidence=evidence,
                               total=len(witnesses), writable=writable)


CONFIRM_OR_CORRECT = "A scientist confirms it, or corrects it, before any record carries it."

# --- the technique, from the instrument configuration (rule 7) --------------------------------------------------------

TECHNIQUE_RULE_ID = "isaac.suggest.technique_from_configuration.v1"
TECHNIQUE_RULE = (
    f"{TECHNIQUE_RULE_ID}: the technique is suggested from what the INSTRUMENT recorded, never from a macro's, a "
    "script's or a function's name. (a) A SPEC acquisition whose emission motor (`emiss` / `emission` in #O / #P) is "
    "held, during an energy scan of the monochromator (gscan mono / energy), within the table's tolerance of an "
    "emission line of an element whose absorption edge that scan crosses is high-energy-resolution "
    "fluorescence-detected absorption: HERFD-XAS. (b) An SSRL XDC run whose own experiment file states EXPT_TYPE with "
    "a word that is one of the schema's techniques (XAS) is that technique. Line and edge energies: "
    "readers.xray_tables (a snapshot of xraydb). One suggestion for the beamtime, VALUED only when every run that "
    "records anything about the technique states the same one: a run whose emission motor is held off the line, or "
    "whose experiment file states another word, leaves no value and is named, and the runs' own technique readings "
    "then stay as they were. Runs that record nothing are counted apart and named. It needs review: a scientist "
    "confirms or corrects it."
)
TECHNIQUE_KEY = "technique_from_configuration"
HERFD = "HERFD-XAS"
#: the engine's macro reader: a technique candidate whose every witness it read carries a macro's or a script's NAME
MACRO_READER_ID = "bl15_macro_v1"
NOT_A_TECHNIQUE_REASON = (
    "A macro's, a script's or a function's name is not a statement of the technique, and the instrument "
    f"configuration of this beamtime states one for every run that records it (rule {TECHNIQUE_RULE_ID}: see the "
    "technique suggestion). The names "
    "are kept here as evidence of what was run; they no longer ask for the technique of each run."
)
_EMISSION_MOTORS = ("emiss", "emission")
_ENERGY_SCAN_MOTORS = ("mono", "energy")
_MAX_TECHNIQUE_WITNESS_RUNS = 6


def is_code_named_technique(candidate: Mapping) -> bool:
    """A technique candidate that rests ONLY on what the macro reader read (a ``qdo`` include, a ``def`` symbol, a
    helper script's function): a name, not a statement of the technique."""
    witnesses = [e for e in candidate.get("evidence") or () if e.get("method") != "ai_interpretation"]
    return (candidate.get("target_field_path") == TECHNIQUE_PATH and bool(witnesses)
            and all(e.get("method_id") == MACRO_READER_ID for e in witnesses))


def energy_scan_range(command: Any) -> tuple[float, float] | None:
    """``(low, high)`` eV of a SPEC ``gscan`` of the monochromator (``gscan mono|energy E0 E1 step E2 step ... time``):
    the start and every region end. ``None`` for any other scan (a stage or optics scan is no energy scan)."""
    tokens = str(command or "").split()
    if len(tokens) < 5 or tokens[0] != "gscan" or tokens[1] not in _ENERGY_SCAN_MOTORS:
        return None
    try:
        numbers = [float(t) for t in tokens[2:-1]]
    except ValueError:
        return None
    energies = [numbers[0], *numbers[1::2]]
    return (min(energies), max(energies)) if len(energies) >= 2 else None


def _herfd_reading(emission: Mapping | None, command: Mapping | None) -> dict | None:
    """What ONE SPEC run's header records about the technique, or ``None`` when it records nothing (no emission
    motor, or no energy scan of the monochromator). ``state`` ``states``: the emission motor is held on ONE emission
    line of an element whose absorption edge the scan crosses (HERFD-XAS). ``state`` ``blocks``: the motor is there
    during an energy scan but not so (off every such line, on several energies, on more than one line): the run
    states something else, so no technique is offered for the beamtime."""
    from .readers import xray_tables as X

    if emission is None or command is None:
        return None
    held = [e for e in emission.get("evidence") or ()
            if any(f"`{m}`" in str(e.get("locator") or "") for m in _EMISSION_MOTORS)]
    scans = [(e, r) for e in command.get("evidence") or () if (r := energy_scan_range(e.get("literal_value"))) is not None]
    if not held or not scans:
        return None
    # the HEADER's own positions only (every scan's, as far as the evidence window holds them): a macro call's
    # argument is what was asked for, not what the instrument recorded
    low, high = min(r[0] for _, r in scans), max(r[1] for _, r in scans)
    base = {"held": held[0], "scan": scans[0][0], "low": low, "high": high}
    try:
        energies = sorted({float(e.get("literal_value")) for e in held})
    except (TypeError, ValueError):
        return {**base, "state": "blocks", "energies": [], "why": "its emission motor position does not read as a number"}
    if len(energies) != 1:
        return {**base, "state": "blocks", "energies": energies, "why": "its emission motor is held at several energies"}
    energy = energies[0]
    hits = [h for h in X.lines_near(energy)
            if (edge := X.edge_energy(h["element"], h["edge"])) is not None and low <= edge <= high]
    if len(hits) != 1:
        return {**base, "state": "blocks", "energies": energies,
                "why": ("that is no emission line of an element whose absorption edge the scan crosses" if not hits
                        else "that is within reach of more than one emission line")}
    hit = hits[0]
    return {**base, "state": "states", "technique": HERFD, "energy": energy,
            "element": hit["element"], "line": hit["line"], "line_eV": hit["energy_eV"], "edge": hit["edge"],
            "edge_eV": X.edge_energy(hit["element"], hit["edge"])}


def technique_readings(runs: Sequence[Mapping], candidates: Sequence[Mapping], xdc_runs: Sequence[tuple]) -> dict[str, dict]:
    """``{run_id: reading}`` for every measurement run whose instrument files record something about the technique
    (``state`` ``states`` with a ``technique``, or ``blocks``): a SPEC run's emission motor (:func:`_herfd_reading`),
    an XDC run's ``EXPT_TYPE`` (``states`` when the word is on the schema's technique list, ``blocks`` when it is
    another word). A run with neither is not listed: it records nothing."""
    by_run: dict[str, dict[str, Mapping]] = {}
    for c in candidates:
        if c.get("run_id") and c.get("statement_key") in ("emission_energy", "scan_command"):
            by_run.setdefault(c["run_id"], {}).setdefault(c["statement_key"], c)
    allowed = set(B.allowed_values(TECHNIQUE_PATH) or ())
    stated = {run_id: st for run_id, g, _scans in xdc_runs for st in g.statements if st.get("key") == "exp_expt_type"}
    out: dict[str, dict] = {}
    for run in runs:
        if not run.get("run_candidate"):
            continue
        rid = run["run_id"]
        if run.get("source_type") == B.SPEC_ACQUISITION_SOURCE_TYPE:
            got = _herfd_reading(by_run.get(rid, {}).get("emission_energy"), by_run.get(rid, {}).get("scan_command"))
            if got is not None:
                out[rid] = got
        elif run.get("source_type") == B.XDC_RUN_SOURCE_TYPE and rid in stated:
            st = stated[rid]
            out[rid] = ({"state": "states", "technique": st["literal"], "expt": st} if st.get("literal") in allowed else
                        {"state": "blocks", "expt": st,
                         "why": f"its experiment file states EXPT_TYPE {st.get('literal')}, which is not one of the record's techniques"})
    return out


def _named(runs: Sequence[Mapping], limit: int = 5) -> str:
    names = [str(r.get("stem") or r.get("label")) for r in runs]
    return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")


def technique_candidate(runs: Sequence[Mapping], readings: Mapping[str, Mapping], sources: Mapping[str, str],
                        bundle_cid: str, writable) -> dict | None:
    """ONE beamtime-level candidate for ``system.technique`` from :func:`technique_readings`, or ``None`` when no run
    states one. VALUED only when every run that records anything about the technique states the same one: a run that
    states another, or records something else (``blocks``), leaves NO value, and it is named. Runs that record nothing
    (a processed or averaged file with no emission motor, a run with no experiment file) are counted apart and named:
    the suggestion does not rest on them."""
    from .readers import xray_tables as X

    measured = [r for r in runs if r.get("run_candidate")
                and r.get("source_type") in (B.SPEC_ACQUISITION_SOURCE_TYPE, B.XDC_RUN_SOURCE_TYPE)]
    stating = [r for r in measured if (readings.get(r["run_id"]) or {}).get("state") == "states"]
    blocking = [r for r in measured if (readings.get(r["run_id"]) or {}).get("state") == "blocks"]
    silent = [r for r in measured if r["run_id"] not in readings]
    if not stating:
        return None
    recording = len(stating) + len(blocking)
    by_technique: dict[str, list[Mapping]] = {}
    for r in stating:
        by_technique.setdefault(readings[r["run_id"]]["technique"], []).append(r)
    id_of = {p: s for s, p in sources.items()}
    witnesses: list[dict] = []
    said: list[str] = []
    value = next(iter(by_technique)) if len(by_technique) == 1 and not blocking else None

    def witness(got: Mapping, technique: str | None) -> list[dict]:
        if "held" in got:
            h, sc = got["held"], got["scan"]
            literal = str(h.get("literal_value"))
            derive = ([{"step": "derive", "rule_id": TECHNIQUE_RULE_ID, "from": literal, "to": technique, "unit": None}]
                      if technique else [])
            return [{"relative_path": h.get("relative_path"), "source_id": h.get("source_id"), "locator": h.get("locator"),
                     "literal": literal, "supports": bool(technique), "normalization": derive},
                    {"relative_path": sc.get("relative_path"), "source_id": sc.get("source_id"), "locator": sc.get("locator"),
                     "literal": sc.get("literal_value"), "supports": False, "normalization": []}]
        st = got["expt"]
        rel = st.get("source_relative_path")
        return [{"relative_path": rel, "source_id": id_of.get(rel), "locator": st.get("locator"), "literal": st["literal"],
                 "supports": bool(technique), "normalization": []}]

    for technique, members in by_technique.items():
        of = f"{len(members)} of the {recording} measurement runs that record it"
        first = readings[members[0]["run_id"]]
        if "held" in first:
            lines = sorted({(readings[r["run_id"]]["element"], readings[r["run_id"]]["line"]) for r in members})
            energies = sorted({readings[r["run_id"]]["energy"] for r in members})
            said.append(
                f"{technique}: the emission spectrometer is held at {', '.join(f'{e:g}' for e in energies[:4])} eV during "
                f"an energy scan from {first['low']:g} to {first['high']:g} eV in {of} (the emission motor's position in "
                f"the scan header, e.g. {first['held'].get('locator')} of {first['held'].get('relative_path')}). That is "
                f"the {' / '.join(f'{el} {line}' for el, line in lines)} emission line ({first['line_eV']:g} eV, within "
                f"{X.LINE_TOLERANCE_EV:g} eV), and the scan crosses the {first['element']} {first['edge']} absorption "
                f"edge ({first['edge_eV']:g} eV): an absorption scan recorded at one emission line with a crystal "
                f"analyser, HERFD-XAS. Energies: {X.source()}.")
        else:
            st = first["expt"]
            said.append(f"{technique}: the run's own experiment file states EXPT_TYPE {st['literal']} in {of} "
                        f"(e.g. {str(st.get('locator')).replace('line:', 'line ')} of {st.get('source_relative_path')}).")
        for r in members[:_MAX_TECHNIQUE_WITNESS_RUNS]:
            witnesses += witness(readings[r["run_id"]], technique if value is not None else None)
    for r in blocking[:_MAX_TECHNIQUE_WITNESS_RUNS]:
        witnesses += witness(readings[r["run_id"]], None)
    apart = ""
    if silent:
        apart = (f" {len(silent)} other measurement run{'s record' if len(silent) != 1 else ' records'} nothing about the "
                 f"technique (no emission motor in an energy scan, or no experiment file; a processed or averaged file is "
                 f"one such): {_named(silent)}. The suggestion does not rest on "
                 f"{'them' if len(silent) != 1 else 'it'}: confirm it for the beamtime only if it holds there too.")
    if value is not None:
        reason = (f"Suggested from the instrument configuration, never from a macro or script name. {said[0]}{apart} "
                  f"{CONFIRM_OR_CORRECT}")
    else:
        counts = "; ".join(f"{t} ({len(m)} run{'s' if len(m) != 1 else ''})" for t, m in by_technique.items())
        other = ""
        if blocking:
            whys: dict[str, list[Mapping]] = {}
            for r in blocking:
                got = readings[r["run_id"]]
                at = (f"its emission motor is held at {', '.join(f'{e:g}' for e in got['energies'][:4])} eV during an energy "
                      f"scan, and {got['why']}" if got.get("energies") and "several" not in got["why"] else got["why"])
                whys.setdefault(at, []).append(r)
            other = (" " + " ".join(f"{len(rs)} run{'s record' if len(rs) != 1 else ' records'} something else ({why}): "
                                    f"{_named(rs)}." for why, rs in whys.items()))
        reason = (f"No technique is offered for the beamtime: the instrument configurations of its runs do not all state "
                  f"one. Stated: {counts}. " + " ".join(said) + other + apart
                  + " Tell me the technique in answer to this question; where the record groups differ, answer this "
                  "question for each group in turn. Nothing was taken from a macro or script name, and the runs' own "
                  "technique readings are left as they were.")
    return suggested_candidate(
        engine_id=f"shared::{TECHNIQUE_RULE_ID}", bundle_cid=bundle_cid, run_id=None, key=TECHNIQUE_KEY, path=TECHNIQUE_PATH,
        value=value, rule_id=TECHNIQUE_RULE_ID, rule=TECHNIQUE_RULE, reason=reason, witnesses=witnesses, writable=writable)

# --- a field of one beamtime's standard is asked only where a source mentions it (audit item 9) -----------------------

#: Optional fields that describe ONE kind of sample (a diluted pellet standard): asked of a run only when a source of
#: that run mentions it: ``path -> the words that mention it`` (matched without case, anywhere in the run's name, its
#: scan-header comment lines and what its candidates read). Asking them of every sample of every beamtime put three
#: questions about a pellet on each electrode, film and foil.
MENTION_GATED_FIELDS: Mapping[str, re.Pattern] = {
    "sample.composition.CuO2_mass_fraction": re.compile(r"cuo2", re.IGNORECASE),
    "sample.composition.sucrose_mass_fraction": re.compile(r"sucrose|sugar", re.IGNORECASE),
    "sample.geometry.pellet_diameter_mm": re.compile(r"pellet", re.IGNORECASE),
}
#: the gate as shipped (a test turns :data:`MENTION_GATED_FIELDS` off to show every other value id is unchanged)
MENTION_GATED_FIELDS_DEFAULT = tuple(MENTION_GATED_FIELDS)
MENTION_GATE_RULE_ID = "isaac.import.optional_field_asked_where_mentioned.v1"


def run_source_texts(runs: Sequence[Mapping], candidates: Sequence[Mapping], statements: Sequence[Mapping]) -> dict[str, str]:
    """``{run_id: text}``: what each run's own sources say, for :func:`asks_field` — its name, every literal its
    candidates observed, and its scan-header comment lines (``statements``: the generic readers' kept statements)."""
    parts: dict[str, list[str]] = {r["run_id"]: [str(r.get("stem") or ""), str(r.get("label") or "")] for r in runs}
    for c in candidates:
        if c.get("run_id") in parts:
            parts[c["run_id"]] += [str(x) for x in c.get("observed_literals") or ()]
    for st in statements:
        if st.get("run_id") in parts and st.get("concept") == B.XDC_COMMENT_STATEMENT_KEY and isinstance(st.get("raw_literal"), str):
            parts[st["run_id"]].append(st["raw_literal"])
    return {rid: "\n".join(p) for rid, p in parts.items()}


def asks_field(path: str, text: str | None) -> bool:
    """Whether ``path`` is asked of a run whose sources say ``text``: always, except a :data:`MENTION_GATED_FIELDS`
    field, which is asked only where the text mentions it."""
    words = MENTION_GATED_FIELDS.get(path)
    return words is None or bool(words.search(text or ""))

# --- a comment line left over from an earlier run (rule 8, the safety half) -------------------------------------------

STALE_COMMENT_RULE_ID = "isaac.import.comment_possibly_stale.v1"
STALE_COMMENT_KIND = "comment_possibly_stale"
SETPOINT_PATH = "context.electrochemistry.potential_setpoint_V"
POTENTIAL_SCALE_PATH = "context.electrochemistry.potential_scale"
#: the fields a possibly stale comment line is not offered for: what it says about the POTENTIAL (the name's own
#: potential token is what changed); what the same header says about the electrolyte is read as before
STALE_FIELDS = frozenset({SETPOINT_PATH, POTENTIAL_SCALE_PATH})


# --- the potential a run's NAME states (rule 10) ----------------------------------------------------------------------

NAME_POTENTIAL_RULE_ID = "isaac.suggest.name_potential.v1"
NAME_POTENTIAL_RULE = (
    f"{NAME_POTENTIAL_RULE_ID}: the potential a run's own name writes is read by the file-name token rules "
    "(bl15.filenames: a leading m or - is a minus sign; millivolts as digits/1000) for a run the token reader does "
    "not read (an SSRL XDC scan set). When a name has several potential tokens the last is the condition. A name "
    "that marks two levels Pos / Neg writes a pulsed step: no set-point is read from it. Where a comment line of "
    "the same run writes the potential too, the two are compared: the same value confirms the reading, a different "
    "one is shown beside it and neither is offered. The value needs review: a name states a number, never the scale."
)
#: the engine's statement key for a potential read from a name: a grouping CONDITION key (``grouping.CONDITION_KEYS``)
NAME_POTENTIAL_KEY = "potential_magnitude"
OPEN_CIRCUIT_RULE_ID = "isaac.suggest.name_open_circuit.v1"
OPEN_CIRCUIT_RULE = (
    f"{OPEN_CIRCUIT_RULE_ID}: a run whose name carries an OCV or OCP token and no potential token after it was "
    "measured at open circuit: the control mode open_circuit is suggested and no set-point applies. A name is not "
    "the potentiostat's log, so the value needs review."
)
OPEN_CIRCUIT_KEY = "control_mode_statement"
CONTROL_MODE_VALUE = "open_circuit"
#: the largest size (volts) a name token with no scale is offered as a set-point at (``questions.HEADER_POTENTIAL_MAX_V``)
NAME_POTENTIAL_MAX_V = 3.0
#: the runs whose names are read here: an SSRL XDC scan set (no token reader reads its name) and a SPEC acquisition
#: (the engine's token reader gives its set-point; open circuit and a pulsed step are said here)
_NAMED_RUN_TYPES = frozenset({B.XDC_RUN_SOURCE_TYPE, B.SPEC_ACQUISITION_SOURCE_TYPE})


def xdc_comment_lines(g: Any, run_scans: Sequence[Mapping]) -> list[tuple]:
    """``(scan_index, relative_path, locator, literal)`` for every comment line (``bundle.XDC_COMMENT_LINES``) of ONE
    ``ssrl_xdc_v1`` run's scans: the lines rule ``bundle.XDC_COMMENT_RULE_ID`` reads."""
    scans = {sc.get("relative_path") for sc in run_scans}
    return [(st.get("scan_index"), st.get("source_relative_path"), str(st.get("locator") or ""), st["literal"])
            for st in g.statements
            if st.get("source_relative_path") in scans and isinstance(st.get("literal"), str)
            and B.is_xdc_comment_line(st.get("key"), st.get("locator"))]


def _name_potential_key(stem: str) -> tuple | None:
    """What a run's name says about the potential, to COMPARE two names: ``None`` when it says nothing."""
    from ..bl15 import filenames as fn

    reading = fn.name_potential(str(stem).split("_"))
    if reading.kind is None:
        return None
    said = reading.token if reading.kind != fn.NAME_PULSED else "_".join(lv.token for lv in reading.levels)
    value = (None if reading.volts is None else float(reading.volts) + 0.0,
             tuple(float(lv.volts) + 0.0 for lv in reading.levels))
    return (reading.kind, value, said)


def stale_comment_flags(xdc_runs: Sequence[tuple]) -> dict[str, list[dict]]:
    """``{run_id: [flag]}`` (rule :data:`STALE_COMMENT_RULE_ID`): a comment line that mentions a potential and is
    IDENTICAL to the line the run before it was acquired with (an unbroken chain back to the run the line first
    appeared on), while the potential the run's own name writes differs from that first run's. The comment lines of
    an SSRL XDC scan are typed once and stay until retyped, so such a line is possibly the earlier run's. Runs are
    taken in acquisition order (each run's earliest scan time, when every run states one; else as listed). A name
    that states no potential is compared with nothing; a name back at the first run's potential is not flagged."""
    from .questions import header_potential_mentions

    rows = []
    for position, (run_id, g, run_scans) in enumerate(xdc_runs):
        times = [sc.get("timestamp_naive") for sc in run_scans if sc.get("timestamp_naive")]
        lines: dict[str, tuple] = {}
        for index, rel, locator, literal in sorted(xdc_comment_lines(g, run_scans), key=lambda l: (l[0] is None, l[0] or 0, l[2])):
            if literal not in lines and header_potential_mentions(literal):
                lines[literal] = (index, rel, locator)
        rows.append({"run_id": run_id, "label": g.label, "start": min(times) if times else None, "position": position,
                     "lines": lines, "name": _name_potential_key(g.label)})
    if rows and all(r["start"] for r in rows):
        rows.sort(key=lambda r: (r["start"], r["position"]))
    out: dict[str, list[dict]] = {}
    origin: dict[str, dict] = {}  # line text -> the run it first appeared on, while every run since has carried it
    for row in rows:
        origin = {text: first for text, first in origin.items() if text in row["lines"]}
        for text, (index, rel, locator) in row["lines"].items():
            first = origin.setdefault(text, row)
            if first is row or row["name"] is None or first["name"] is None or row["name"][:2] == first["name"][:2]:
                continue
            out.setdefault(row["run_id"], []).append({
                "kind": STALE_COMMENT_KIND, "rule_id": STALE_COMMENT_RULE_ID, "locator": locator, "severity": "flag",
                "source_relative_path": rel, "scan_index": index, "line": text, "first_run": first["label"],
                "detail": (f"The comment line {text!r} is identical to the one run {first['label']} was acquired with, "
                           f"while the potential in the file name changed ({first['name'][2]} there, {row['name'][2]} "
                           "here): it is possibly left over from that run, not a statement about this one."),
            })
    return out


def stale_comment_reason(flags: Sequence[Mapping] | None, lines: Iterable[str]) -> str | None:
    """Why NO potential is offered from comment lines ``lines`` of a run flagged ``flags``: every one of them is a
    possibly stale line (``None`` when one is not, or the run has no flag)."""
    by_line = {f["line"]: f for f in flags or ()}
    lines = list(dict.fromkeys(lines))
    if not lines or not all(line in by_line for line in lines):
        return None
    return (f"{by_line[lines[0]]['detail']} The potential it states is not offered as this run's. The line and the "
            "file name's own token are both shown and neither is preferred: tell me the potential held during this scan.")


def stale_comment_index(bundle: Mapping) -> dict[tuple[str, int], str]:
    """``{(scan file, line number): detail}`` for every possibly stale comment line of the bundle's runs
    (their ``comment_possibly_stale`` anomalies), under each scan file of the run: an AI reading may cite any."""
    out: dict[tuple[str, int], str] = {}
    for run in bundle.get("runs") or ():
        for a in (run.get("other_relationships") or {}).get("anomalies") or ():
            if a.get("kind") != STALE_COMMENT_KIND:
                continue
            number = re.search(r"\d+", str(a.get("locator") or ""))
            for sc in run.get("scans") or ():
                if number and sc.get("relative_path"):
                    out[(sc["relative_path"], int(number.group(0)))] = str(a.get("detail") or "")
    return out


def _token_spans(stem: str) -> list[tuple[int, int]]:
    spans, at = [], 0
    for token in stem.split("_"):
        spans.append((at, at + len(token)))
        at += len(token) + 1
    return spans


def _token_locator(stem: str, index: int) -> str:
    start, end = _token_spans(stem)[index]
    return f"filename token {index} [chars {start}..{end}]"


def _volts(value: Any) -> float:
    return float(value) + 0.0


def _same_volts(a: float, b: float) -> bool:
    return abs(a - b) < 1e-9


def comment_potential_mentions(lines: Sequence[tuple]) -> list[dict]:
    """Every potential the comment lines of ONE run mention (``questions.header_potential_mentions``), one item per
    distinct (line text, mention), each with its first place. ``lines``: ``(scan_index, relative_path, locator,
    literal)``. Only to COMPARE with the name: never a value."""
    from .questions import header_potential_mentions

    out: dict[tuple[str, str], dict] = {}
    for _index, rel, locator, literal in sorted(lines, key=lambda l: (l[0] is None, l[0] or 0, str(l[2]))):
        for m in header_potential_mentions(literal):
            out.setdefault((literal, m["literal"]), {"line": literal, "relative_path": rel, "locator": locator,
                                                     "literal": m["literal"], "volts": m["volts"], "scale": m["scale"]})
    return list(out.values())


def name_potential_review(runs: Sequence[Mapping], comment_lines: Mapping[str, Sequence[tuple]]) -> dict[str, dict]:
    """``{run_id: review}`` for every measurement run whose name states a potential, open circuit or a pulsed step
    (``bl15.filenames.name_potential``). ``review``: ``reading`` (the name's), ``mentions`` (what the run's comment
    lines mention), ``relation`` (``agrees`` / ``differs`` / ``no_comment``; a set-point only), and ``sign_pairs``
    (shared by every review): the runs of this import whose name writes a minus as ``m`` or ``-`` and whose comment
    line writes the same negative potential, which is what confirms the convention here."""
    from ..bl15 import filenames as fn

    reviews: dict[str, dict] = {}
    pairs: list[dict] = []
    for run in runs:
        if not run.get("run_candidate") or run.get("source_type") not in _NAMED_RUN_TYPES:
            continue
        stem = str(run.get("stem") or "")
        reading = fn.name_potential(stem.split("_"))
        if reading.kind is None:
            continue
        mentions = comment_potential_mentions(comment_lines.get(run["run_id"]) or ())
        relation = None
        if reading.kind == fn.NAME_SETPOINT:
            volts = _volts(reading.volts)
            if not mentions:
                relation = "no_comment"
            elif all(_same_volts(m["volts"], volts) for m in mentions):
                relation = "agrees"
                if volts < 0 and reading.rule == fn.RULE_SIGNED_POTENTIAL:
                    pairs.append({"run_id": run["run_id"], "name": stem, "token": reading.token,
                                  "literal": mentions[0]["literal"], "relative_path": mentions[0]["relative_path"],
                                  "locator": mentions[0]["locator"]})
            else:
                relation = "differs"
        reviews[run["run_id"]] = {"reading": reading, "stem": stem, "mentions": mentions, "relation": relation,
                                  "sign_pairs": pairs, "source_type": run.get("source_type")}
    return reviews


def _where(m: Mapping) -> str:
    place = str(m.get("locator") or "").replace("line:", "line ")
    return f"{place} of {m['relative_path']}" if place and m.get("relative_path") else str(m.get("relative_path") or "")


def comment_differs_reason(review: Mapping) -> str | None:
    """Why NO potential is offered for a run whose name and comment line write different potentials (``None`` when
    they do not differ). The same sentence on the name's candidate and on the comment line's."""
    if review.get("relation") != "differs":
        return None
    reading = review["reading"]
    said = "; ".join(f"{m['literal']!r} ({_where(m)})" for m in review["mentions"][:3])
    return (f"The file name writes {reading.token} ({_volts(reading.volts):g} V) and a comment line of the same run "
            f"writes {said}. The two differ, and nothing in the files says which is right or that both are on one "
            "scale, so neither is offered: tell me the potential held during this scan.")


def name_setpoint_value(review: Mapping | None) -> float | None:
    """The set-point a run's NAME will be offered as (:func:`name_potential_candidates`), or ``None``: no review, not
    a set-point, a run the engine's token reader reads, a number too large, or a comment line that writes another."""
    from ..bl15 import filenames as fn

    if not review or review["reading"].kind != fn.NAME_SETPOINT or review.get("source_type") != B.XDC_RUN_SOURCE_TYPE:
        return None
    volts = _volts(review["reading"].volts)
    if abs(volts) > NAME_POTENTIAL_MAX_V or review.get("relation") == "differs":
        return None
    return volts


def name_potential_candidates(runs: Sequence[Mapping], candidates: Sequence[Mapping], reviews: Mapping[str, Mapping],
                              sources: Mapping[str, str], first_n: int, writable, *, room: int) -> list[dict]:
    """The candidates the names give (ids ``cand-<first_n>`` on, at most ``room`` of them), in run order:

    * a set-point (:data:`NAME_POTENTIAL_KEY`) for a run the engine's token reader does not read, valued unless the
      run's comment line writes another potential (:func:`comment_differs_reason`) or the number is too large to be
      an electrode potential;
    * a value-less set-point for a pulsed name, engine-read or not (it says the levels);
    * the control mode ``open_circuit`` (:data:`OPEN_CIRCUIT_KEY`) for an open-circuit name.

    ``sources``: ``{source_id: relative_path}``. A run that already has a candidate for the field gets none."""
    from ..bl15 import filenames as fn

    have = {(c.get("run_id"), c.get("target_field_path"), c.get("statement_key")) for c in candidates}
    out: list[dict] = []
    for run in runs:
        review = reviews.get(run["run_id"])
        if review is None or len(out) >= room:
            continue
        reading, stem, rid = review["reading"], review["stem"], run["run_id"]
        sid = run.get("acquisition_source_id")
        rel = sources.get(sid)
        cid = f"cand-{first_n + len(out):04d}"

        def token_witness(index: int, token: str, volts: Any, rule: str | None, supports: bool) -> dict:
            return {"relative_path": rel, "source_id": sid, "locator": _token_locator(stem, index), "literal": token,
                    "supports": supports,
                    "normalization": ([{"step": "normalize", "rule_id": B._rule_id(rule), "from": token,
                                        "to": None if volts is None else _volts(volts), "unit": "V"}] if rule else [])}

        def line_witnesses() -> list[dict]:
            return [{"relative_path": m["relative_path"], "source_id": next((s for s, p in sources.items() if p == m["relative_path"]), None),
                     "locator": m["locator"], "literal": m["line"], "supports": False, "normalization": []}
                    for m in review["mentions"]]

        if reading.kind == fn.NAME_OPEN_CIRCUIT:
            if (rid, B.CONTROL_MODE_PATH, OPEN_CIRCUIT_KEY) in have:
                continue
            reason = (f"Read from the file name's token {reading.token}: open circuit, so no potential was applied and "
                      f"no set-point applies. {CONFIRM_OR_CORRECT}")
            out.append(suggested_candidate(
                engine_id=f"{run['run_key']}::{OPEN_CIRCUIT_RULE_ID}", bundle_cid=cid, run_id=rid, key=OPEN_CIRCUIT_KEY,
                path=B.CONTROL_MODE_PATH, value=CONTROL_MODE_VALUE, rule_id=OPEN_CIRCUIT_RULE_ID, rule=OPEN_CIRCUIT_RULE,
                reason=reason, writable=writable,
                witnesses=[{**token_witness(reading.index, reading.token, None, None, True),
                            # a DERIVED value: the token is what the file writes, the control mode what it means
                            "normalization": [{"step": "derive", "rule_id": OPEN_CIRCUIT_RULE_ID, "from": reading.token,
                                               "to": CONTROL_MODE_VALUE, "unit": None}]}]))
            continue
        if any(k[0] == rid and k[1] == SETPOINT_PATH and k[2] == NAME_POTENTIAL_KEY for k in have):
            continue  # the engine's own reading of the name
        if reading.kind == fn.NAME_PULSED:
            levels = ", ".join(f"{lv.token} ({_volts(lv.volts):g} V)" for lv in reading.levels)
            reason = (f"The file name writes {len(reading.levels)} potential levels ({levels}), marked Pos / Neg: a pulsed "
                      "step between them, not one potential held during the scan. No set-point is offered: say the value "
                      "the record should carry, or leave the set-point out.")
            out.append(suggested_candidate(
                engine_id=f"{run['run_key']}::{NAME_POTENTIAL_RULE_ID}", bundle_cid=cid, run_id=rid, key=NAME_POTENTIAL_KEY,
                path=SETPOINT_PATH, value=None, rule_id=NAME_POTENTIAL_RULE_ID, rule=NAME_POTENTIAL_RULE, reason=reason,
                witnesses=[token_witness(lv.index, lv.token, lv.volts, fn.RULE_PULSED_LEVELS, False) for lv in reading.levels],
                writable=writable))
            continue
        if run.get("source_type") != B.XDC_RUN_SOURCE_TYPE:
            continue  # the engine reads this run's name; it gave no set-point (a refused or unread stem): nothing is added
        volts = _volts(reading.volts)
        value: float | None = volts
        signed = reading.rule == fn.RULE_SIGNED_POTENTIAL
        read = (f"Read from the file name's token {reading.token}"
                + (" (a leading m or - is a minus sign)" if signed else "") + f": {volts:g} V.")
        if abs(volts) > NAME_POTENTIAL_MAX_V:
            value = None
            reason = (f"The file name's token {reading.token} reads as {volts:g} V, larger than an electrode potential is "
                      "(it may be a detector or supply voltage), so it is not offered: tell me the potential held during "
                      "this scan, or say none applies.")
        elif review["relation"] == "differs":
            value, reason = None, comment_differs_reason(review)
        elif review["relation"] == "agrees":
            m = review["mentions"][0]
            reason = (f"{read} A comment line of the same run writes the same potential ({m['literal']!r}, {_where(m)}), "
                      f"which confirms the reading. {CONFIRM_OR_CORRECT}")
        else:
            pairs = [p for p in review["sign_pairs"] if p["run_id"] != rid]
            if signed and pairs:
                p = pairs[0]
                confirmed = (f" In this import {len(pairs)} run(s) write the same sign both ways (for example {p['token']} "
                             f"in the name of {p['name']} beside {p['literal']!r} in its comment line), which confirms "
                             "that the letter is a minus sign here.")
            elif signed:
                confirmed = (" No comment line in this import writes the same potential with a minus sign, so the sign "
                             "rests on the naming convention alone: check it.")
            else:
                confirmed = ""
            reason = f"{read}{confirmed} No comment line of this run states the potential. {CONFIRM_OR_CORRECT}"
        earlier = [token_witness(e.index, e.token, e.volts, fn.RULE_LAST_POTENTIAL_TOKEN, False) for e in reading.earlier]
        out.append(suggested_candidate(
            engine_id=f"{run['run_key']}::{NAME_POTENTIAL_RULE_ID}", bundle_cid=cid, run_id=rid, key=NAME_POTENTIAL_KEY,
            path=SETPOINT_PATH, value=value, rule_id=NAME_POTENTIAL_RULE_ID, rule=NAME_POTENTIAL_RULE, reason=reason,
            witnesses=[token_witness(reading.index, reading.token, reading.volts, reading.rule, True), *earlier,
                       *line_witnesses()],
            writable=writable))
    return out
