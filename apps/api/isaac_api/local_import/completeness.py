"""RECORD COMPLETENESS, a LOCAL gate (audit of 18 Nov 2026, finding 1). Stdlib only; reads the bundle.

WHY. Grouping keeps two runs of one sample apart because their files state different conditions (the potential,
the cycling history, the filter). Nothing required those conditions to reach the records: with every
schema-required question answered, a beamtime exported 89 valid records with 5 distinct metadata bodies. Each was
"valid for the portal's pinned schema" and nobody could tell 38 of them apart except by their curve.

WHAT THIS IS. A gate of this tool, beside official validation and never part of it:

* **A distinguishing condition** of a record group is a condition its grouping basis states and a
  ``conditions_differ`` split reason names against another live group of the same sample: exactly what kept the two
  records apart. So is the electrode or specimen number when another group reads the same material name with another
  one, and a condition the group's own files read two ways (:func:`distinguishing_conditions`). It must be IN THE
  RECORD (the composer filled the field that carries it) or DECLINED by the
  scientist (a ``reject`` on that value or label: "leave it out"), or the group is not :data:`READY`.
  A condition no record field can carry (the emission energy, a step number) is said and never holds a record.
* **Indistinguishable records**: two records that would be written with the same ``sample``, ``system`` and
  ``context`` are held, whatever the conditions above say (the catch-all for what no rule maps).

``validate`` reports it under its own name (:data:`GATE_ID`); ``export`` holds the records it names and says which
question answers each, unless :data:`ALLOW_FLAG` is given; ``bundle questions`` lists the questions that fill a
distinguishing condition as their own tier (:data:`TIER`), after the blocking ones and before the optional ones.

WHAT THIS IS NOT. It never changes a verdict of the official schema or the portal validator, never fills a value,
and never reads a condition into a record: every value is still a scientist's confirmation. ``verdict:
exportable`` keeps meaning "official validation passed".
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Sequence

from . import bundle as B

GATE_ID = "isaac.local.record_completeness.v1"
TIER = "distinguishing"
ALLOW_FLAG = "--allow-indistinguishable"
#: why a group is held
HELD_CONDITION = "distinguishing_condition_not_in_record"
HELD_IDENTICAL = "indistinguishable_from_another_record"
#: a condition's state for one group
IN_RECORD, DECLINED, OPEN, NO_RECORD_FIELD = "in_record", "declined", "open", "no_record_field"

SETPOINT_PATH = "context.electrochemistry.potential_setpoint_V"
SCALE_PATH = "context.electrochemistry.potential_scale"
#: A path that goes into the record only beside these (``records.SETPOINT_NEEDS_SCALE``): answering them is part of
#: putting the condition in the record, and declining one declines the condition.
COMPANIONS: Mapping[str, tuple[str, ...]] = {SETPOINT_PATH: (SCALE_PATH,)}
#: ``records.FIELD_REMAP``: the path a candidate names -> the path the composer fills.
REMAP = {"context.electrochemistry.reaction": "context.reaction.name"}
#: The record sections that say what was measured (``labels.record_warnings`` compares the same three).
BODY_SECTIONS = ("sample", "system", "context")
#: What each grouping condition is called when a person is told about it.
WORDS = {"potential_magnitude": "the potential", "scan_header_potential": "the potential",
         "cycling_state": "the cycling history", "before_after_state": "the cycling history", "filter": "the filter",
         "electrolyte_or_medium": "the electrolyte or medium", "ph": "the pH", "gas_condition": "the gas",
         "temperature_statement": "the temperature", "step_number": "the step number",
         "emission_energy": "the emission energy", "dry_state": "the dry state", "flow_rate": "the flow rate",
         "acquisition_method": "the technique", "loading_or_thickness": "the loading",
         "sample_or_electrode_number": "which electrode or specimen it is"}
NAMED = 5


def _label_paths() -> dict[str, str]:
    """grouping condition -> the condition label that carries it (``labels.py``)."""
    from . import labels as L

    return {"filter": L.FILTER_PATH, **{k: L.HISTORY_PATH for k in L.HISTORY_KEYS}}


def words(condition: str) -> str:
    return WORDS.get(condition, condition.replace("_", " "))


def _run_ids(bundle: Mapping, group: Mapping) -> list[str]:
    by_key = {r["run_key"]: r["run_id"] for r in bundle.get("runs") or ()}
    context = set(group.get("context_run_keys") or ())
    return [by_key[k] for k in group.get("member_run_keys") or () if k in by_key and k not in context]


def _basis_entries(group: Mapping, cats: Sequence[str] = ("conditions", "technique", "environment")) -> list[tuple[str, Mapping]]:
    """``[(condition, its basis entry)]`` of a group's conditions, technique and environment (``cats``); a basis part
    that is not a mapping (a hand-written or older group) holds none."""
    basis = group.get("basis") if isinstance(group.get("basis"), Mapping) else {}
    return [(k, v) for cat in cats if isinstance(basis.get(cat), Mapping)
            for k, v in basis[cat].items() if isinstance(v, Mapping)]


#: The sample readings that tell two specimens of ONE material apart (grouping never joins them, and compares
#: conditions only within one of them): the record says which through its sample id.
SAMPLE_INSTANCE_KEYS = ("sample_or_electrode_number", "loading_or_thickness")
_ALL = ("sample", "conditions", "technique", "environment")


def _sample_name(group: Mapping) -> Any:
    return next((v.get("value") for k, v in _basis_entries(group, ("sample",)) if k in ("sample_name", "sample_name_stem")
                 and v.get("value") is not None), None)


def distinguishing_conditions(group: Mapping, live_ids: Iterable[str],
                             peers: "Sequence[Mapping] | Materials" = ()) -> dict[str, dict]:
    """``{condition: {"condition", "value", "other_group_ids"}}``: what keeps THIS group's record apart from another
    live group's record of the same material.

    * each condition this group states that a ``conditions_differ`` split reason names against another LIVE group of
      its sample. A condition only the other group states (``this`` is None) is not one of this group's: there is
      nothing of it to put in this record;
    * with ``peers`` (the live groups): the electrode / specimen number or loading (:data:`SAMPLE_INSTANCE_KEYS`) when
      another group reads the same material name with another one: grouping keeps those apart as different samples
      and never compares their conditions, so only the sample id tells their records apart;
    * with ``peers``: a condition this group's own files read two ways (its care flag, ``conflicting_condition``)
      while another group reads the same material name: the record has to say which reading it is, or leave it out
      on purpose."""
    live = live_ids if isinstance(live_ids, (set, frozenset)) else set(live_ids)
    stated = dict(_basis_entries(group))
    out: dict[str, dict] = {}
    for sr in group.get("split_reasons") or ():
        if sr.get("code") != "conditions_differ" or sr.get("other_group_id") not in live:
            continue
        for d in sr.get("differences") or ():
            key = d.get("condition")
            if d.get("key_class") != "condition" or d.get("this") is None or key not in stated:
                continue
            row = out.setdefault(key, {"condition": key, "value": d.get("this"), "other_group_ids": []})
            if sr["other_group_id"] not in row["other_group_ids"]:
                row["other_group_ids"].append(sr["other_group_id"])
    materials = peers if isinstance(peers, Materials) else Materials(peers, live)
    name = _sample_name(group)
    same_material = materials.others(name, group.get("group_id"))
    if not same_material:
        return out
    mine = dict(_basis_entries(group, _ALL))
    for key in SAMPLE_INSTANCE_KEYS:
        value = (mine.get(key) or {}).get("value")
        others = materials.with_another(name, key, value) if value is not None else 0
        if others and key not in out:
            out[key] = {"condition": key, "value": value, "other_group_ids": [], "others": others}
    for sr in group.get("split_reasons") or ():
        key = sr.get("condition")
        if sr.get("code") == "conflicting_condition" and key in mine and key not in out:
            out[key] = {"condition": key, "value": {"its files read": list(sr.get("readings") or ())},
                        "other_group_ids": [], "others": same_material, "own_files_disagree": True}
    return out


class Materials:
    """The live groups by the material name they read, counted ONCE for a whole bundle (a beamtime can hold thousands
    of groups of one material): how many groups read each name, and how many read each specimen number under it."""

    def __init__(self, groups: Sequence[Mapping], live_ids: Iterable[str] | None = None):
        live = set(live_ids) if live_ids is not None else None
        self.count: dict[str, int] = {}
        self.values: dict[tuple[str, str], dict[str, int]] = {}
        self.member: dict[Any, str] = {}
        for g in groups:
            if live is not None and g.get("group_id") not in live:
                continue
            name = _sample_name(g)
            if name is None:
                continue
            name = _key(name)
            self.member[g.get("group_id")] = name
            self.count[name] = self.count.get(name, 0) + 1
            sample = dict(_basis_entries(g, ("sample",)))
            for key in SAMPLE_INSTANCE_KEYS:
                value = (sample.get(key) or {}).get("value")
                if value is not None:
                    seen = self.values.setdefault((name, key), {})
                    seen[_key(value)] = seen.get(_key(value), 0) + 1

    def others(self, name: Any, group_id: Any) -> int:
        """How many OTHER live groups read material ``name``."""
        if name is None:
            return 0
        n = self.count.get(_key(name), 0)
        return n - 1 if self.member.get(group_id) == _key(name) else n

    def with_another(self, name: Any, key: str, value: Any) -> int:
        """How many live groups of material ``name`` read ANOTHER value of ``key`` than ``value``."""
        seen = self.values.get((_key(name), key)) or {}
        return sum(n for v, n in seen.items() if v != _key(value))


def _key(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)


class _Index:
    """What the gate reads of the whole bundle, built once: each run's answerable targets per field path, and the
    latest decision on each."""

    def __init__(self, bundle: Mapping, decisions: Mapping | None = None):
        self.bundle = bundle
        self.decisions = decisions if decisions is not None else B._decisions_by_target(
            bundle.get("scientist_decisions") or ())
        self.cand = {c["candidate_id"]: c for c in bundle.get("candidates") or ()}
        self.targets: dict[tuple[Any, str], list[tuple[str, str]]] = {}
        for c in bundle.get("candidates") or ():
            if c.get("target_field_path"):
                self.targets.setdefault((c.get("run_id"), c["target_field_path"]), []).append(("candidate", c["candidate_id"]))
        for m in bundle.get("missing_values") or ():
            if m.get("target_field_path"):
                self.targets.setdefault((m.get("run_id"), m["target_field_path"]), []).append(("missing_value", m["value_id"]))
        self.label_paths = _label_paths()
        self.conflicts_of: dict[str, list[str]] = {}
        for cf in bundle.get("conflicts") or ():
            if isinstance(cf, Mapping) and cf.get("candidate_id") and cf.get("conflict_id"):
                self.conflicts_of.setdefault(cf["candidate_id"], []).append(cf["conflict_id"])

    def entry(self, group: Mapping, condition: str) -> Mapping:
        return next((v for k, v in _basis_entries(group, _ALL) if k == condition), None) or {}

    def conflicts(self, group: Mapping, condition: str) -> tuple[list[str], bool]:
        """``(open conflict ids, declined)`` of the disagreement on ``condition``'s reading for ``group`` (its basis
        candidates' conflicts): ``declined`` when the scientist's latest word on one is ``reject`` (neither reading:
        leave it out on purpose); open ones have no answer yet (or a ``defer``)."""
        # C6: a disagreement a standing rule settled (the filter the acquisition files recorded over a file name's) asks
        # nothing first: the group's condition is the reading the rule used, and its label question asks the rest
        ids = [c for i in self.entry(group, condition).get("candidate_ids") or ()
               if not ((self.cand.get(i) or {}).get("state_basis") or {}).get("resolved_by_rule")
               for c in self.conflicts_of.get(i, ())]
        said = {c: (self.decisions.get(("conflict", c)) or {}).get("decision") for c in ids}
        return [c for c, d in said.items() if d in (None, "defer")], any(d == "reject" for d in said.values())

    def paths(self, group: Mapping, condition: str) -> list[str]:
        """The record field(s) that carry ``condition`` for ``group``: what its basis candidates target, else the
        condition label ISAAC proposes for it. ``[]``: no record field carries it."""
        entry = self.entry(group, condition)
        found = [p for i in entry.get("candidate_ids") or () if (p := (self.cand.get(i) or {}).get("target_field_path"))]
        if not found and condition in self.label_paths:
            found = [self.label_paths[condition]]
        return list(dict.fromkeys(found))

    def declined(self, run_ids: Sequence[str], path: str) -> bool:
        """True when the scientist's latest word on ``path`` for these runs is ``reject`` ("leave it out") and no run
        of them holds a confirmed or corrected value for it."""
        latest = [self.decisions.get(t) for rid in run_ids for t in self.targets.get((rid, path), ())]
        said = [d.get("decision") for d in latest if d]
        return "reject" in said and not any(s in ("confirm", "correct", "provide_value", "choose_reading") for s in said)


def group_gate(index: _Index, group: Mapping, report: Mapping, live_ids: Iterable[str],
               peers: "Sequence[Mapping] | Materials" = ()) -> dict:
    """The gate for one group: ``{"gate", "ready", "conditions": [...], "held_by": [...], "needs": [paths]}``.
    ``report``: the composer's report for the group (``records.compose_group``): what it FILLED is what is in the
    record."""
    filled = {f["path"] for f in report.get("filled") or ()}
    run_ids = _run_ids(index.bundle, group)
    rows, needs = [], []
    for key, d in sorted(distinguishing_conditions(group, live_ids, peers).items()):
        paths = index.paths(group, key)
        carried = [REMAP.get(p, p) for p in paths]
        open_conflicts, conflict_declined = index.conflicts(group, key)
        if not paths:
            state = NO_RECORD_FIELD
        elif any(p in filled for p in carried):
            state = IN_RECORD
        elif conflict_declined or any(index.declined(run_ids, p) or any(index.declined(run_ids, c) for c in COMPANIONS.get(p, ()))
                                      for p in paths):
            state = DECLINED
        else:
            state = OPEN
            if open_conflicts:
                # review of PR 342, finding 3: the files read it two ways: the disagreement is answered first
                needs.append(conflict_field(key))
            for p in paths:
                for x in (p, *COMPANIONS.get(p, ())):
                    if x not in filled and x not in needs:
                        needs.append(x)
        rows.append({"condition": key, "words": words(key), "value": d["value"], "paths": paths, "state": state,
                     "keeps_apart_from": d.get("others", len(d["other_group_ids"])),
                     **({"conflict_ids": open_conflicts} if state == OPEN and open_conflicts else {})})
    open_rows = [r for r in rows if r["state"] == OPEN]
    return {"gate": GATE_ID, "group_id": group["group_id"], "ready": not open_rows, "conditions": rows,
            "held_by": [HELD_CONDITION] if open_rows else [], "needs": needs}


def conflict_field(condition: str) -> str:
    """The ``needs`` / ``fields`` key of the disagreement on a condition's reading (no record field: a conflict)."""
    return f"conflict:{condition}"


def live_record_group_ids(bundle: Mapping) -> list[str]:
    """The live groups that can become a record as they stand (``questions.cannot_export_reasons`` names the rest):
    a condition keeps a record apart only from another record."""
    from . import questions as Q

    never = Q.cannot_export_reasons(bundle)
    return [g["group_id"] for g in bundle.get("record_groups") or ()
            if g.get("status") in B.LIVE_GROUP_STATUSES and g["group_id"] not in never]


def gates(bundle: Mapping, reports: Mapping[str, Mapping], decisions: Mapping | None = None,
          live_ids: Sequence[str] | None = None) -> dict[str, dict]:
    """``{group_id: group_gate}`` for every group of ``reports`` (the composer's report per group) that is among
    ``live_ids`` (default :func:`live_record_group_ids`)."""
    live = list(live_ids) if live_ids is not None else live_record_group_ids(bundle)
    index = _Index(bundle, decisions)
    by_id = {g["group_id"]: g for g in bundle.get("record_groups") or ()}
    peers = Materials([by_id[g] for g in live if g in by_id])  # counted once, never once per group
    live_set = set(live)
    return {gid: group_gate(index, by_id[gid], reports[gid], live_set, peers) for gid in live if gid in reports and gid in by_id}


# --- the questions' tier --------------------------------------------------------------------------------------------


def mark_questions(questions: list[dict], bundle: Mapping, gate_of: Mapping[str, Mapping],
                   group_of: Mapping[str, str]) -> None:
    """Set ``completeness`` on every open question whose answer puts an OPEN distinguishing condition into a record:
    ``{"gate", "tier": "distinguishing", "groups", "conditions", "fields", "why"}``. No id, tier number, text or
    target of any question changes; the listing sorts these after the blocking questions and before the rest."""
    needed: dict[str, dict[str, list[str]]] = {}  # path -> {group id: [conditions]}
    for gid, gate in gate_of.items():
        for row in gate["conditions"]:
            if row["state"] != OPEN:
                continue
            for p in row["paths"]:
                for x in (p, *COMPANIONS.get(p, ())):
                    if x in gate["needs"]:
                        needed.setdefault(x, {}).setdefault(gid, []).append(row["condition"])
    # review of PR 342, finding 3: the disagreement a held group's condition waits on (a resolve_conflict question,
    # no record field of its own) is marked too, for exactly the groups whose condition it holds
    by_conflict: dict[str, list[tuple[str, str]]] = {}
    for gid, gate in gate_of.items():
        for row in gate["conditions"]:
            for cid in row.get("conflict_ids") or ():
                by_conflict.setdefault(cid, []).append((gid, row["condition"]))
    for q in questions:
        if q.get("kind") != "resolve_conflict" or q.get("informational") or not by_conflict:
            continue
        hit = [x for t in q.get("targets") or () if t.get("kind") == "conflict" for x in by_conflict.get(t.get("id"), ())]
        if not hit:
            continue
        gids = sorted({g for g, _ in hit})
        conds = sorted({c for _, c in hit})
        said = ", ".join(dict.fromkeys(words(c) for c in conds))
        q["completeness"] = {
            "gate": GATE_ID, "tier": TIER, "groups": len(gids), "group_ids": gids, "conditions": conds,
            "fields": [conflict_field(c) for c in conds],
            "why": (f"Needed before export: the files read {said} two ways, and it is what keeps {len(gids)} record(s) "
                    "apart from another record of the same material. Say which reading is right, or reject both to "
                    "leave it out on purpose."),
        }
    if not needed:
        return
    run_of: dict[str, Any] = {c["candidate_id"]: c.get("run_id") for c in bundle.get("candidates") or ()}
    run_of.update({m["value_id"]: m.get("run_id") for m in bundle.get("missing_values") or ()})
    found: list[tuple[dict, dict[str, tuple[set[str], set[str]]]]] = []  # (question, {path: (groups, target ids)})
    for q in questions:
        if (q.get("informational") or q.get("outside_live_groups") or not q.get("allowed_decisions", True)
                or q.get("completeness")):
            continue
        if q.get("kind") == "optional_values":
            asked = [(f, list(ids)) for f, ids in (q.get("fields") or {}).items()]
        elif q.get("target_field_path"):
            asked = [(q["target_field_path"], [t["id"] for t in q.get("targets") or ()])]
        else:
            continue
        per_path: dict[str, tuple[set[str], set[str]]] = {}
        for path, ids in asked:
            want = needed.get(path) or needed.get(REMAP.get(path, path))
            if not want:
                continue
            scoped = {s[len("group:"):] for s in (q.get("per_scope_targets") or {}) if s.startswith("group:")}
            reached = scoped | {group_of[r] for i in ids if (r := run_of.get(i)) in group_of}
            if any(i in run_of and run_of[i] is None for i in ids):
                reached |= set(want)  # a beamtime-level value reaches every group
            got = reached & set(want)
            if got:
                per_path[path] = (got, set(ids))
        if per_path:
            found.append((q, per_path))
    for q, per_path in found:
        # A WIDER QUESTION THAT ASKS THE SAME TARGETS is the one to answer (the beamtime-wide potential scale over
        # each group's own optional question): the narrower one is its `--only` route, not a second question
        mine = {path: (groups, ids) for path, (groups, ids) in per_path.items()
                if not any(o is not q and path in other and len(other[path][0]) > len(groups) and ids <= other[path][1]
                           for o, other in found)}
        if not mine:
            continue
        hit_groups: dict[str, set[str]] = {}
        for path, (groups, _ids) in mine.items():
            want = needed.get(path) or needed.get(REMAP.get(path, path)) or {}
            for gid in groups:
                hit_groups.setdefault(gid, set()).update(want.get(gid) or ())
        conds = sorted({c for cs in hit_groups.values() for c in cs})
        said = ", ".join(dict.fromkeys(words(c) for c in conds))
        q["completeness"] = {
            "gate": GATE_ID, "tier": TIER, "groups": len(hit_groups), "group_ids": sorted(hit_groups),
            "conditions": conds, "fields": list(mine),
            "why": (f"Needed before export: {said} is what keeps {len(hit_groups)} record(s) apart from another "
                    "record of the same sample, and it is not in the record yet. Confirm it, correct it, or decline "
                    "it (reject) to leave it out on purpose."),
        }


def answers_needed(questions: Sequence[Mapping]) -> dict:
    """How many questions carry the tier, and how many ANSWERS that is: questions that share one reading are answered
    together (``--same-reading``), so a batch counts once."""
    marked = [q for q in questions if q.get("completeness")]
    batches = {q.get("same_reading_group") or q["question_id"] for q in marked}
    return {"questions": len(marked), "answers": len(batches)}


def _by_words(counts: Mapping[str, int]) -> dict[str, int]:
    """``{what a person calls the condition: groups}``: two grouping keys with one name (the cycling state and the
    before/after state are both "the cycling history") are said once, with the larger count."""
    out: dict[str, int] = {}
    for key, n in counts.items():
        out[words(key)] = max(n, out.get(words(key), 0))
    return out


def summary(gate_of: Mapping[str, Mapping], group_ids: Iterable[str] | None = None) -> dict:
    """The gate over several groups, counted: ``{"gate", "groups", "ready", "held", "open_conditions": {condition:
    groups}, "statement"}``."""
    wanted = set(group_ids) if group_ids is not None else None
    rows = [g for gid, g in gate_of.items() if wanted is None or gid in wanted]
    held = [g for g in rows if not g["ready"]]
    open_by: dict[str, int] = {}
    for g in held:
        for r in g["conditions"]:
            if r["state"] == OPEN:
                open_by[r["condition"]] = open_by.get(r["condition"], 0) + 1
    unmapped = sorted({r["condition"] for g in rows for r in g["conditions"] if r["state"] == NO_RECORD_FIELD})
    out = {"gate": GATE_ID, "groups": len(rows), "ready": len(rows) - len(held), "held": len(held),
           "open_conditions": dict(sorted(open_by.items(), key=lambda kv: (-kv[1], kv[0])))}
    if held:
        out["statement"] = (
            f"{len(held)} of {len(rows)} record group(s) are not complete ({GATE_ID}, a local gate; official "
            "validation is not changed by it): " + "; ".join(f"{w} in {n}" for w, n in _by_words(out["open_conditions"]).items())
            + ". These are the conditions grouping used to keep records of one sample apart; each must be in the "
              "record or declined before export writes it. `isaac bundle questions <bundle_dir>` lists the questions "
              f"that fill them right after the blocking ones (`completeness`); `export {ALLOW_FLAG} --by \"<your name>\"` writes them anyway.")
    else:
        out["statement"] = (f"Every distinguishing condition of {len(rows)} record group(s) is in its record or "
                            f"declined ({GATE_ID}).")
    if unmapped:
        out["no_record_field"] = unmapped
        out["statement"] += (" No record field carries " + ", ".join(words(c) for c in unmapped)
                             + ": it never holds a record, and records that differ only there are caught as "
                               "indistinguishable at export.")
    return out


# --- indistinguishable records --------------------------------------------------------------------------------------


#: 1.15.0 (review of PR 342, finding 5): the scientist's "export it anyway", kept in the bundle as a decision
EXPORT_ANYWAY_DECISION = B.EXPORT_ANYWAY_DECISION


def body_digest(draft: Mapping) -> str:
    """The sha256 of what a record says was measured (:func:`metadata_key`): what an export-anyway decision binds to."""
    import hashlib

    return hashlib.sha256(metadata_key(draft).encode("utf-8")).hexdigest()


def export_anyway_of(bundle: Mapping) -> dict[str, Mapping]:
    """``{group id: the latest export_despite_completeness decision on it}``."""
    out: dict[str, Mapping] = {}
    for d in bundle.get("scientist_decisions") or ():
        t = d.get("target") or {} if isinstance(d, Mapping) else {}
        if isinstance(d, Mapping) and d.get("decision") == EXPORT_ANYWAY_DECISION and t.get("kind") == "record_group":
            out[t.get("id")] = d
    return out


def metadata_key(draft: Mapping) -> str:
    """What a record says was measured, as one comparable string: every ``sample``, ``system`` and ``context`` field
    of its draft. Never the curve, the ids, the files or the timestamps."""
    fields = draft.get("fields") or {}
    return json.dumps({p: (fields[p] or {}).get("value") for p in sorted(fields)
                       if p.split(".", 1)[0] in BODY_SECTIONS}, sort_keys=True, default=str)


def identical_sets(bundle: Mapping, drafts: Sequence[tuple[str, Mapping]],
                   gate_of: Mapping[str, Mapping] | None = None) -> list[list[str]]:
    """Group ids whose drafts say the same thing (:func:`metadata_key`), two or more per set, in the order given.
    Groups a scientist kept apart on purpose (``keep_apart`` on their merge candidate: declared repeats) are not a
    set.

    With ``gate_of`` (review of PR 342, finding 4): records that differ in a condition the scientist DECLINED, or that
    no record field carries, are told apart by that difference and are no set: each set is split by those conditions'
    readings (its members' basis values), and only members that agree on them too stay together."""
    by_key: dict[str, list[str]] = {}
    for gid, draft in drafts:
        by_key.setdefault(metadata_key(draft), []).append(gid)
    kept = [set(mc.get("group_ids") or ()) for mc in bundle.get("merge_candidates") or ()
            if (mc.get("merge_candidate_id") or mc.get("id")) in B.kept_apart(bundle)] if bundle.get("merge_candidates") else []
    groups = {g.get("group_id"): g for g in bundle.get("record_groups") or () if isinstance(g, Mapping)}
    out = []
    for gids in by_key.values():
        if len(gids) < 2 or any(set(gids) <= k for k in kept):
            continue
        if not gate_of:
            out.append(gids)
            continue
        left_out = sorted({r["condition"] for g in gids for r in (gate_of.get(g) or {}).get("conditions") or ()
                           if r.get("state") in (DECLINED, NO_RECORD_FIELD)})
        parts: dict[str, list[str]] = {}
        for g in gids:
            basis = dict(_basis_entries(groups.get(g) or {}, _ALL))
            parts.setdefault(json.dumps([(basis.get(k) or {}).get("value") for k in left_out], default=str), []).append(g)
        out += [p for p in parts.values() if len(p) > 1]
    return out


def questions_for(payload: Mapping) -> dict[str, dict[str, list[str]]]:
    """``{group id: {field path: [question id]}}`` of the open questions marked ``completeness`` in a consolidated
    payload: what answers each held group's open condition. A question that reaches the most groups first (the
    beamtime-wide one before a group's own)."""
    out: dict[str, dict[str, list[str]]] = {}
    marked = [q for q in payload.get("questions") or () if q.get("completeness")]
    for q in sorted(marked, key=lambda q: -int(q["completeness"].get("groups") or 0)):
        for gid in q["completeness"].get("group_ids") or ():
            for path in q["completeness"].get("fields") or ():
                # ONE question per group and field: the one that reaches the most groups (a group's own question
                # asking the same targets is the `--only` way to answer it, not a second thing to answer)
                out.setdefault(gid, {}).setdefault(path, [q["question_id"]])
    return out


def hold_text(gate: Mapping, questions_of: Mapping[str, Sequence[str]] | None = None) -> str:
    """Why one group is held for an open condition, and the route that frees it, naming only questions that reach this
    group (``questions_of``: :func:`questions_for`'s entry for it). A condition its files read two ways: first which
    reading is right (its disagreement question), then the label for this group (``--only group:<id>``); a condition
    no question reaches yet says so, never a question that would not reach it."""
    gid = gate.get("group_id")
    qof = questions_of or {}
    open_rows = [r for r in gate["conditions"] if r["state"] == OPEN]
    said = "; ".join(f"{r['words']} ({_shown(r['value'])}, which keeps it apart from {r['keeps_apart_from']} other "
                     f"record(s) of its material)" for r in open_rows)
    steps = []
    for r in open_rows:
        conflict = list(qof.get(conflict_field(r["condition"])) or ())
        fills = list(dict.fromkeys(q for p in r["paths"] for x in (p, *COMPANIONS.get(p, ())) for q in qof.get(x, ())))
        only = f" --only group:{gid}" if gid else ""
        if conflict:
            step = (f"for {r['words']}, say which reading is right (question {conflict[0]}; reject it to leave "
                    f"{r['words']} out on purpose)")
            step += (f", then confirm the label for this record: question {fills[0]}{only}" if fills else
                     ", then ISAAC proposes the label for this record from that answer (`isaac bundle questions` lists it)")
        elif fills:
            # a condition label is one beamtime question with a row per group: this record's row is `--only`
            label = any(p in set(_label_paths().values()) for p in r["paths"])
            step = (f"for {r['words']}, answer question {', '.join(fills[:3])}" + (only if label else "")
                    + (f" (and {len(fills) - 3} more)" if len(fills) > 3 else "")
                    + ", or decline it (reject) to leave it out on purpose")
        else:
            step = (f"for {r['words']}, no open question reaches this record yet: `isaac bundle show <bundle_dir> group "
                    f"{gid}` gives its readings")
        steps.append(step)
    return (f"Held ({GATE_ID}): the record would be written without {said}. To free it: " + "; ".join(steps)
            + f". Or export it anyway: `export {ALLOW_FLAG} --by \"<your name>\"`.")


def _shown(value: Any) -> str:
    return json.dumps(value, default=str) if not isinstance(value, str) else value
