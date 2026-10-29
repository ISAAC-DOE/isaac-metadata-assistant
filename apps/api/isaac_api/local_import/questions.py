"""Consolidated questions (``questions.json`` v2, LOCAL-4): ask each thing ONCE, at the
right scope, blocking first.

``bundle.questions[]`` (v1) stays the fine-grained list — one entry per missing value,
conflict and needs-review value — because decisions and references key on those targets.
This module CONSOLIDATES it for a person:

* **Scope hierarchy experiment > record group > run.** A missing value whose answer is
  plausibly shared (:data:`SHARED_PATHS`: facility, beamline, producer, technique,
  environment, reaction, cell type, electrolyte, ...) is asked ONCE at experiment scope —
  "applies to N groups — answer once, or per group" — and the answer becomes one decision
  per target (each listed). It is NOT consolidated when the bundle already records
  DIFFERENT values for that field (a differing recorded condition): then it is asked per
  group.
* **Run-level questions inside a record group collapse to the group** (a record is per group).
* **Identical questions are merged.** Order: export-blocking (required by the schema the
  local export targets — the pinned upstream schema when installed, else the vendored one,
  stated in ``blocking_basis``), then conflicts that affect a record, then optional.
* Each question carries plain text, why it blocks, hints (a literal and its locator — a
  hint, never an answer), allowed values where the target schema closes the field with an
  enum, and the exact ``isaac bundle decide --question`` command that answers it.

Question ids are content-derived (``Q-<sha1(scope|kind|subject)[:10]>``), so they are stable
across rebuilds; an answered target simply drops out.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from . import bundle as B

FORMAT_ID = "isaac.questions"
FORMAT_VERSION = "2.0.0"

#: Fields whose answer is plausibly the same for a whole beamtime. Prefix match.
SHARED_PATHS = (
    "system.facility.",
    "system.technique",
    "system.domain",
    "attribution.produced_by.",
    "context.environment",
    "context.reaction.",
    "context.electrochemistry.reaction",
    "context.electrochemistry.cell_type",
    "context.electrochemistry.electrolyte",
)
TIER_BLOCKING, TIER_CONFLICT, TIER_OPTIONAL = 1, 2, 3
#: A required schema OBJECT with no required members is asked for by its primary field.
REQUIRED_AS_FIELD = {"sample.material": "sample.material.name"}
_UNANSWERED = (B.STATE_MISSING,)
_HINTS_PER_QUESTION = 5


def _is_shared(path: str) -> bool:
    return any(path == p.rstrip(".") or path.startswith(p) for p in SHARED_PATHS)


def _vocabulary() -> dict[str, list]:
    """``dotted path -> allowed values`` from the PINNED upstream vocabulary
    (``data/vocabulary.json``), when the validator is installed. Empty otherwise."""
    from pathlib import Path

    from . import portal as P

    where = P.locate()
    if not where.get("available"):
        return {}
    try:
        vocab = json.loads((Path(where["dir"]) / "data" / "vocabulary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, list] = {}
    for section in vocab.values():
        if isinstance(section, Mapping):
            for key, entry in section.items():
                if isinstance(entry, Mapping) and isinstance(entry.get("values"), list):
                    out[key] = list(entry["values"])
    return out


def _target_schema() -> tuple[dict | None, dict]:
    """The schema blocking is judged against, and a statement of which one."""
    from . import portal as P

    where = P.locate()
    upstream = P.upstream_schema(where) if where.get("available") else None
    if upstream is not None:
        return upstream, {"schema": "local_export_target", "source": "pinned upstream clone", "commit": where.get("commit")}
    return B._vendored_schema(), {
        "schema": "vendored v1.05 (the pinned upstream validator is not installed)",
        "source": "schema/isaac_record_v1.json",
        "commit": None,
    }


def _node(schema: Mapping | None, path: str) -> Mapping | None:
    node: Any = schema
    for seg in path.split("."):
        if not isinstance(node, Mapping):
            return None
        node = (node.get("properties") or {}).get(seg.rstrip("[]"))
        if seg.endswith("[]") and isinstance(node, Mapping):
            node = node.get("items")
    return node if isinstance(node, Mapping) else None


def _label(path: str) -> str:
    return path.rsplit(".", 1)[-1].replace("_", " ")


def _qid(*parts: str) -> str:
    return "Q-" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]


def consolidate(bundle: Mapping) -> dict:
    """``questions.json`` v2 for ``bundle``. Pure: reads the bundle, writes nothing."""
    schema, basis = _target_schema()
    vocabulary = _vocabulary()
    required_base = list(B.required_record_paths(schema)) + list(B.PORTAL_REQUIRED_PATHS)
    if basis["schema"] == "local_export_target":
        # DEC-76: the pinned schema accepts an unknown temperature as null + not_reported,
        # which the composer writes; asking for it is optional there, never blocking.
        required_base = [p for p in required_base if p != "context.temperature_K"]
    groups = [g for g in bundle.get("record_groups") or () if g.get("status") not in ("rejected", "split", "merged")]
    run_by_key = {r["run_key"]: r["run_id"] for r in bundle["runs"]}
    group_of: dict[str, str] = {}
    for g in groups:
        for key in g.get("member_run_keys") or ():
            rid = run_by_key.get(key)
            if rid and rid not in group_of:
                group_of[rid] = g["group_id"]
    group_order = {g["group_id"]: i for i, g in enumerate(groups)}
    run_order = {r["run_id"]: i for i, r in enumerate(bundle["runs"])}
    reaction_runs = {c["run_id"] for c in bundle["candidates"] if c["target_field_path"] in ("context.electrochemistry.reaction", "context.reaction.name")}

    def required_for(path: str, run_id: str | None) -> str | None:
        req = [REQUIRED_AS_FIELD.get(r, r) for r in required_base]
        if run_id in reaction_runs:
            req += list(B.REACTION_REQUIRED_PATHS)
        return B._required_for(path, req)

    # A SAMPLE PARTITION: groups whose grouping basis records the SAME sample reading share
    # their sample questions (never across a differing reading; never for an empty basis).
    sample_key_of_group: dict[str, str] = {}
    for g in groups:
        sample = (g.get("basis") or {}).get("sample")
        if isinstance(sample, Mapping) and sample:
            canon = {k: (v.get("value") if isinstance(v, Mapping) else v) for k, v in sorted(sample.items())}
            sample_key_of_group[g["group_id"]] = json.dumps(canon, sort_keys=True)

    # what the bundle already RECORDS for each field (a differing recorded condition blocks
    # experiment-wide propagation)
    recorded: dict[str, set[str]] = {}
    for c in bundle["candidates"]:
        if c["target_field_path"] and c["value"] is not None:
            recorded.setdefault(c["target_field_path"], set()).add(json.dumps(c["value"], sort_keys=True))
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    for (kind, tid), d in decisions.items():
        if kind == "missing_value" and d.get("value") is not None:
            m = next((x for x in bundle["missing_values"] if x["value_id"] == tid), None)
            if m:
                recorded.setdefault(m["target_field_path"], set()).add(json.dumps(d["value"], sort_keys=True))

    def scope_of_run(run_id: str | None) -> str:
        if run_id is None:
            return "experiment"
        gid = group_of.get(run_id)
        return f"group:{gid}" if gid else f"run:{run_id}"

    related: dict[str, list[dict]] = {}
    for c in bundle["candidates"]:
        if c["target_field_path"]:
            related.setdefault(c["target_field_path"], []).append(c)

    buckets: dict[tuple, dict] = {}

    def add(key: tuple, *, kind: str, path: str | None, target: dict, run_id: str | None, scope: str,
            blocking: str | None, partition: str | None = None, field: str | None = None):
        q = buckets.get(key)
        if q is None:
            q = buckets[key] = {
                "kind": kind,
                "scope": scope,
                "partition": partition,
                "target_field_path": path,
                "required_by": blocking,
                "targets": [],
                "per_scope_targets": {},
                "fields": {},
                "runs": set(),
            }
        if field is not None:
            q["fields"].setdefault(field, []).append(target["id"])
        if target not in q["targets"]:
            q["targets"].append(target)
        q["per_scope_targets"].setdefault(scope_of_run(run_id), []).append(target["id"])
        if run_id:
            q["runs"].add(run_id)
        if blocking and not q["required_by"]:
            q["required_by"] = blocking

    for m in bundle["missing_values"]:
        if m["value_state"] not in _UNANSWERED:
            continue
        path, rid = m["target_field_path"], m["run_id"]
        if rid is not None and group_of and rid not in group_of:
            run = next((r for r in bundle["runs"] if r["run_id"] == rid), None)
            if run is not None and not run["run_candidate"]:
                continue
        blocking = required_for(path, rid)
        partition = None
        if _is_shared(path) and len(recorded.get(path, ())) <= 1:
            scope = "experiment"
        elif path.startswith("sample.") and sample_key_of_group.get(group_of.get(rid)):
            scope, partition = "experiment", f"sample={sample_key_of_group[group_of[rid]]}"
        elif path.startswith("sample.") and not recorded.get(path) and rid in group_of:
            # Nothing in the import records ANY reading for this field and the group has no
            # sample basis: asked once with the choice stated — never across a recorded,
            # differing reading.
            scope, partition = "experiment", "sample=unrecorded"
        else:
            scope = scope_of_run(rid)
        if blocking:
            add((scope, "missing_value", path, partition), kind="missing_value", path=path, partition=partition,
                target={"kind": "missing_value", "id": m["value_id"]}, run_id=rid, scope=scope, blocking=blocking)
        else:
            # OPTIONAL values are one question per scope, listing each field (answered per
            # field with --field), so they never outnumber the blocking ones.
            add((scope, "optional_values", None, partition), kind="optional_values", path=None, partition=partition,
                target={"kind": "missing_value", "id": m["value_id"]}, run_id=rid, scope=scope, blocking=None, field=path)

    for c in bundle["candidates"]:
        path = c["target_field_path"]
        if not path or c["value_state"] not in (B.STATE_NEEDS_REVIEW, B.STATE_CANDIDATE_EXTRACTED):
            continue
        blocking = required_for(path, c["run_id"])
        if c["value_state"] == B.STATE_CANDIDATE_EXTRACTED and not blocking:
            continue  # an extracted optional value is not asked about
        scope = scope_of_run(c["run_id"])
        add((scope, "confirm_value", path, None), kind="confirm_value", path=path, partition=None,
            target={"kind": "candidate", "id": c["candidate_id"]}, run_id=c["run_id"], scope=scope, blocking=blocking)

    cand_by_id = {c["candidate_id"]: c for c in bundle["candidates"]}
    conflicts_out = []
    for cf in bundle["conflicts"]:
        if cf["value_state"] not in (B.STATE_CONFLICTING, B.STATE_NEEDS_REVIEW):
            continue
        rids = cf["run_ids"]
        scope = scope_of_run(rids[0]) if rids else "experiment"
        cand = cand_by_id.get(cf.get("candidate_id") or "")
        path = cand["target_field_path"] if cand else None
        # D6: a disagreement about a field the record REQUIRES blocks the record exactly as
        # a missing value does (a beamtime-scope one blocks every record).
        required = required_for(path, rids[0] if rids else None) if path else None
        affects = any(r in group_of for r in rids) or (not group_of and bool(rids)) or (required and not rids)
        conflicts_out.append((scope, cf, affects, path, required))

    questions: list[dict] = []
    for (scope, kind, path, partition), q in buckets.items():
        if kind == "optional_values":
            qid = _qid(scope, kind, partition or "")
            questions.append(
                {
                    "question_id": qid,
                    "tier": TIER_OPTIONAL,
                    "blocking": False,
                    "why": "Optional: the record can be exported without these.",
                    "kind": kind,
                    "scope": scope,
                    "partition": partition,
                    "target_field_path": None,
                    "text": f"{len(q['fields'])} optional field(s) no source states: {', '.join(sorted(q['fields']))}. Answer any you know.",
                    "applies_to": {"groups": len({group_of[r] for r in q["runs"] if r in group_of}), "runs": len(q["runs"]), "targets": len(q["targets"])},
                    "targets": q["targets"],
                    "per_scope_targets": q["per_scope_targets"],
                    "fields": {f: ids for f, ids in sorted(q["fields"].items())},
                    "hints": [],
                    "allowed_values": None,
                    "answer_command": f'isaac bundle decide <bundle_dir> --question {qid} --field <field path> --decision correct --value <value> --by "<your name>"',
                }
            )
            continue
        node = _node(schema, path)
        enum = node.get("enum") if isinstance(node, Mapping) and isinstance(node.get("enum"), list) else None
        if enum is None and path in vocabulary:
            # D4: a vocabulary-controlled field (no schema enum, but the portal checks it).
            enum = vocabulary[path]
        numeric = isinstance(node, Mapping) and node.get("type") in ("number", "integer", ["number", "null"])
        n_groups = len({group_of[r] for r in q["runs"] if r in group_of})
        if kind == "missing_value":
            text = f"What is the {_label(path)} ({path})? No source in this import states it."
            if scope == "experiment" and len(q["per_scope_targets"]) > 1:
                text += (f" Applies to {n_groups} group(s)" if n_groups else f" Applies to {len(q['runs'])} run(s), not yet grouped")
                if partition == "sample=unrecorded":
                    text += (" that record no sample reading — answer once ONLY if they are all the same sample;"
                             " otherwise answer per group (--only group:<id>).")
                else:
                    text += (" with the same sample reading" if partition else "") + " — answer once, or per group."
            decision = "correct"
        else:
            text = f"Is the extracted {_label(path)} ({path}) right? Confirm it, or correct it."
            decision = "confirm"
        hints = []
        if path.startswith("attribution.produced_by."):
            hints.append({"kind": "folder_name", "literal": bundle["source_root"]["label"], "locator": "the imported folder's name",
                          "note": "A PI or group name in a folder name is a HINT to ask about, never an answer."})
        for c in related.get(path, [])[:_HINTS_PER_QUESTION]:
            if c["observed_literals"]:
                ev = next((e for e in c["evidence"] if e["method"] != "ai_interpretation"), None)
                hints.append({"kind": "related_reading", "candidate_id": c["candidate_id"], "literal": c["observed_literals"][0],
                              "locator": (ev or {}).get("locator"), "source_id": (ev or {}).get("source_id")})
        value_arg = "<value>" + (" --json" if numeric else "")
        qid = _qid(scope, kind, path, partition or "")
        questions.append(
            {
                "question_id": qid,
                "partition": partition,
                "tier": TIER_BLOCKING if q["required_by"] else TIER_OPTIONAL,
                "blocking": bool(q["required_by"]),
                "why": (f"The record cannot be exported without it: the target schema requires {q['required_by']}."
                        if q["required_by"] else "Optional: the record can be exported without it."),
                "kind": kind,
                "scope": scope,
                "target_field_path": path,
                "text": text,
                "applies_to": {"groups": n_groups, "runs": len(q["runs"]), "targets": len(q["targets"])},
                "targets": q["targets"],
                "per_scope_targets": q["per_scope_targets"],
                "hints": hints,
                "allowed_values": enum,
                "answer_command": (
                    f'isaac bundle decide <bundle_dir> --question {qid} --decision {decision}'
                    + (f" --value {value_arg}" if kind == "missing_value" else "")
                    + ' --by "<your name>"'
                    + ("   # per group: add --only group:<group_id>" if len(q["per_scope_targets"]) > 1 else "")
                ),
            }
        )
    for scope, cf, affects, path, required in conflicts_out:
        node = _node(schema, path) if path else None
        enum = node.get("enum") if isinstance(node, Mapping) and isinstance(node.get("enum"), list) else (vocabulary.get(path) if path else None)
        questions.append(
            {
                "question_id": _qid(scope, "resolve_conflict", cf["conflict_id"]),
                "partition": None,
                "tier": TIER_BLOCKING if required else (TIER_CONFLICT if affects else TIER_OPTIONAL),
                "blocking": bool(required),
                "why": (f"The record cannot be exported until this is settled: the target schema requires {required}."
                        if required else
                        "The sources disagree; a record built from these runs carries whichever reading you choose."
                        if affects else "The sources disagree about something outside any record group."),
                "kind": "resolve_conflict",
                "scope": scope,
                "target_field_path": path,
                "text": f"The sources disagree ({cf['kind']}{', ' + str(cf['subject']) if cf['subject'] else ''}). Which reading is right?",
                "applies_to": {"groups": len({group_of[r] for r in cf["run_ids"] if r in group_of}), "runs": len(cf["run_ids"]), "targets": 1},
                "targets": [{"kind": "conflict", "id": cf["conflict_id"]}],
                "per_scope_targets": {scope: [cf["conflict_id"]]},
                "hints": [
                    {"kind": "reading", "literal": r["value"], "locator": (r["witnesses"][0] if r["witnesses"] else {}).get("locator"),
                     "source_id": (r["witnesses"][0] if r["witnesses"] else {}).get("source_id")}
                    for r in cf["readings"][:_HINTS_PER_QUESTION]
                ],
                "allowed_values": enum,
                "answer_command": f'isaac bundle decide <bundle_dir> --question {_qid(scope, "resolve_conflict", cf["conflict_id"])} --decision confirm --value <one reading> --by "<your name>"',
            }
        )

    # THE GROUPING STEP'S OWN EXPERIMENT-SCOPE QUESTIONS (e.g. which filename positions are
    # run counters). Answered with a set_counter_positions decision, then a regroup.
    answered_positions = any(d.get("decision") == "set_counter_positions" for d in bundle.get("scientist_decisions") or ())
    for gq in bundle.get("grouping_questions") or ():
        if not isinstance(gq, Mapping) or gq.get("kind") != "naming_counter_positions":
            continue
        qid = _qid("experiment", "naming_counter_positions", str(gq.get("id") or gq.get("text") or ""))
        questions.append(
            {
                "question_id": qid,
                "partition": None,
                "tier": TIER_CONFLICT,
                "blocking": False,
                "why": "It decides which runs are repeats of one measurement, and so how many records there are.",
                "kind": "naming_counter_positions",
                "scope": "experiment",
                "target_field_path": None,
                "text": str(gq.get("text") or "Which filename token positions are run or acquisition counters?"),
                "applies_to": {"groups": len(groups), "runs": len(bundle["runs"]), "targets": 1},
                "targets": [{"kind": "experiment", "id": "experiment"}],
                "per_scope_targets": {"experiment": ["experiment"]},
                "hints": [{"kind": "grouping", "literal": gq.get("examples") or gq.get("options"), "locator": "the grouping step"}],
                "allowed_values": None,
                "answered": answered_positions,
                "answer_command": (
                    'isaac bundle decide <bundle_dir> --target experiment --decision set_counter_positions '
                    '--positions <n[,m]> --by "<your name>"  &&  isaac bundle group <bundle_dir> --regroup'
                ),
            }
        )

    def order(q):
        scope = q["scope"]
        if scope == "experiment":
            s = (0, 0)
        elif scope.startswith("group:"):
            s = (1, group_order.get(scope[6:], 10**9))
        else:
            s = (2, run_order.get(scope[4:], 10**9))
        return (q["tier"], s, q["target_field_path"] or "", q["question_id"])

    questions.sort(key=order)
    return {
        "format": FORMAT_ID,
        "format_version": FORMAT_VERSION,
        "bundle_id": bundle.get("bundle_id"),
        "blocking_basis": basis,
        "counts": {
            "total": len(questions),
            "blocking": sum(q["tier"] == TIER_BLOCKING for q in questions),
            "conflicts_affecting_a_record": sum(q["tier"] == TIER_CONFLICT for q in questions),
            "optional": sum(q["tier"] == TIER_OPTIONAL for q in questions),
            "fine_grained_v1": len(bundle.get("questions") or ()),
        },
        "questions": questions,
    }


def filter_questions(payload: Mapping, *, scope: str | None = None, blocking_only: bool = False) -> list[dict]:
    qs = list(payload["questions"])
    if blocking_only:
        qs = [q for q in qs if q["blocking"]]
    if scope:
        if scope.startswith("group:"):
            # D5: an experiment-scope question belongs to a group's list only when it
            # actually has a target for that group (or for the whole record).
            qs = [
                q for q in qs
                if q["scope"] == scope
                or (q["scope"] == "experiment" and (scope in q["per_scope_targets"] or "experiment" in q["per_scope_targets"]))
            ]
        elif scope.startswith("run:") or scope == "experiment":
            qs = [q for q in qs if q["scope"] == scope]
    return qs


def targets_for(payload: Mapping, question_id: str, only: str | None = None, field: str | None = None) -> list[str]:
    q = next((q for q in payload["questions"] if q["question_id"] == question_id), None)
    if q is None:
        return []
    ids = [t["id"] for t in q["targets"]]
    if q["kind"] == "optional_values":
        if not field:
            return []  # an optional-values question is answered one field at a time
        ids = list(q.get("fields", {}).get(field, []))
    if only:
        scoped = set(q["per_scope_targets"].get(only, []))
        ids = [i for i in ids if i in scoped]
    return ids


def processing_blocked_groups(bundle: Mapping) -> dict[str, str]:
    """``{group_id: reason_code}`` for groups whose latest processing result says the
    protocol does not apply (:func:`bundle.processing_blocked_groups`): there is no curve to
    approve, so none is asked about."""
    return {gid: r["applicability"]["reason_code"] for gid, r in B.processing_blocked_groups(bundle).items()}


def minimum_answers_for_one_group(payload: Mapping, bundle: Mapping) -> dict | None:
    """The fewest BLOCKING questions that stand between one record group and export —
    experiment-scope blocking questions plus that group's own — plus the two decisions
    every group needs (confirm the group, approve its processing).

    A group the processing protocol does not apply to is never offered as "the nearest"
    while another exists: no approval can make it complete. When only such groups are left,
    the decision named is the blocking reason, never "approve its processing result"."""
    blocked = processing_blocked_groups(bundle)
    best = None
    for g in bundle.get("record_groups") or ():
        key = f"group:{g['group_id']}"
        need = sum(
            1 for q in payload["questions"]
            if q["blocking"] and (q["scope"] == key or (q["scope"] == "experiment" and (key in q["per_scope_targets"] or "experiment" in q["per_scope_targets"])))
        )
        rank = (g["group_id"] in blocked, need)
        if best is None or rank < best[2]:
            best = (g["group_id"], need, rank)
    if best is None:
        return None
    out = {"group_id": best[0], "blocking_questions": best[1], "plus_decisions": ["confirm the group", "approve its processing result"]}
    if best[0] in blocked:
        out["plus_decisions"] = ["confirm the group"]
        out["blocked"] = f"{B.NO_PROTOCOL_COVERS} ({blocked[best[0]]}); this group cannot become a complete record until one does"
    if blocked:
        out["groups_without_an_applicable_processing_protocol"] = len(blocked)
    return out
