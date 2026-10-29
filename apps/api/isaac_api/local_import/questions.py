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
across rebuilds; an answered target simply drops out. **That holds across answers too
(DEC-91):** a question's scope and partition are read only from what the import recorded and
from the record groups, never from answers, so answering one question (or some of its
targets) leaves every other open question's id unchanged. What an answer can still do is ADD a
question that was withheld until it existed — the documented unlocks: a stated clock zone
unlocks the start-time confirmations it gives; a stated control mode makes its set-point
required (that missing value moves from the optional question to a blocking one); a later zone
change re-asks the confirmations it undid. None of these renames an existing question.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from . import bundle as B
from . import suggestions as S

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
#: A missing value an AI reading lifted to needs_review is still unanswered: it is asked,
#: with the reading as a hint. Only a scientist decision takes it out of the list.
_UNANSWERED = (B.STATE_MISSING, B.STATE_NEEDS_REVIEW)
_HINTS_PER_QUESTION = 5
#: The decisions that answer each kind of question. ``decide --question`` refuses any other,
#: so answering e.g. an absorber question with ``confirm`` can never bulk-confirm the record
#: GROUPS it targets (the absorber question's targets are groups).
ALLOWED_DECISIONS: Mapping[str, tuple[str, ...]] = {
    "missing_value": ("confirm", "correct", "reject", "defer"),
    "optional_values": ("confirm", "correct", "reject", "defer"),
    "confirm_value": ("confirm", "correct", "reject", "defer"),
    "resolve_conflict": ("confirm", "correct", "reject", "defer"),
    "naming_counter_positions": ("set_counter_positions", B.NOT_COUNTER_DECISION),
    "clock_time_zone": (B.CLOCK_ZONE_DECISION,),
    "confirm_absorber": ("set_absorber", "defer"),
}


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


def _eligible_values(path: str) -> list | None:
    """The vendored schema's ``enum`` at ``path`` — exactly what ``bundle.value_problem`` refuses
    outside of — or ``None`` when that schema does not close the field."""
    node = B._schema_node(path)
    enum = node.get("enum") if isinstance(node, Mapping) else None
    return list(enum) if isinstance(enum, list) else None


def _is_numeric(node: Mapping | None) -> bool:
    return isinstance(node, Mapping) and node.get("type") in ("number", "integer", ["number", "null"])


def _label(path: str) -> str:
    return path.rsplit(".", 1)[-1].replace("_", " ")


def _qid(*parts: str) -> str:
    return "Q-" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]


def consolidate(bundle: Mapping) -> dict:
    """``questions.json`` v2 for ``bundle``. Pure: reads the bundle, writes nothing."""
    schema, basis = _target_schema()
    vocabulary = _vocabulary()
    # THE SET-POINT A CONTROL MODE NEEDS (1.5.0): the target schema's conditional rules make the
    # set-point required for some modes, so a run whose mode a file states or a scientist confirmed
    # (bundle.control_mode_by_run) has its set-point asked as BLOCKING. A run with no mode adds
    # nothing, and no mode is ever derived from a set-point (or the reverse).
    control_mode = B.control_mode_by_run(bundle)
    required_by_mode: dict[str | None, list[str]] = {}

    def required_base(mode: str | None) -> list[str]:
        if mode not in required_by_mode:
            base = list(B.required_record_paths(schema, control_mode=mode)) + list(B.PORTAL_REQUIRED_PATHS)
            if basis["schema"] == "local_export_target":
                # DEC-76: the pinned schema accepts an unknown temperature as null + not_reported,
                # which the composer writes; asking for it is optional there, never blocking.
                base = [p for p in base if p != "context.temperature_K"]
            required_by_mode[mode] = base
        return required_by_mode[mode]
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
        req = [REQUIRED_AS_FIELD.get(r, r) for r in required_base(control_mode.get(run_id))]
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

    # what the FILES record for each field (a differing recorded condition blocks experiment-wide
    # propagation). ID STABILITY (DEC-91): the scope and partition of a question — and so its id —
    # are read ONLY from what the import recorded, never from the answers given since. An answer
    # given for some targets therefore takes exactly those targets out and leaves the question for
    # the rest under the SAME id; answers that already differ are stated in its text instead.
    recorded: dict[str, set[str]] = {}
    for c in bundle["candidates"]:
        if c["target_field_path"] and c["value"] is not None:
            recorded.setdefault(c["target_field_path"], set()).add(json.dumps(c["value"], sort_keys=True))
    answered: dict[str, set[str]] = {}
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    path_of_value = {m["value_id"]: m["target_field_path"] for m in bundle["missing_values"]}
    for (kind, tid), d in decisions.items():
        if kind == "missing_value" and d.get("value") is not None and tid in path_of_value:
            answered.setdefault(path_of_value[tid], set()).add(json.dumps(d["value"], sort_keys=True))

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

    zone_decided = B.clock_zone_decision(bundle) is not None
    for c in bundle["candidates"]:
        path = c["target_field_path"]
        if not path or c["value_state"] not in (B.STATE_NEEDS_REVIEW, B.STATE_CANDIDATE_EXTRACTED):
            continue
        if not zone_decided and B.is_local_clock_start(c):
            continue  # nothing to confirm until the clock's zone is stated: the zone question asks that
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
            # A number given without --json is stored as text, which the schema's type check
            # then keeps out of the record (bundle.value_problem): say which fields need it.
            numeric_fields = sorted(f for f in q["fields"] if _is_numeric(_node(schema, f)))
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
                    "text": (f"{len(q['fields'])} optional field(s) no parser read a value for: {', '.join(sorted(q['fields']))}. Answer any you know."
                             + (f" {len(fh)} of them have a suggestion or hint (field_hints)." if (fh := _optional_field_hints(bundle, q["fields"])) else "")),
                    "applies_to": {"groups": len({group_of[r] for r in q["runs"] if r in group_of}), "runs": len(q["runs"]), "targets": len(q["targets"])},
                    "targets": q["targets"],
                    "per_scope_targets": q["per_scope_targets"],
                    "fields": {f: ids for f, ids in sorted(q["fields"].items())},
                    # the values the VENDORED schema's enum allows — the one source eligibility checks
                    # (bundle.value_problem) — so an answer outside a list given here is stored but never
                    # eligible. A field closed only by the export-target schema or the pinned vocabulary is
                    # not listed: eligibility does not refuse an answer outside those lists.
                    "field_allowed_values": {f: a for f in sorted(q["fields"]) if (a := _eligible_values(f))},
                    "hints": [],
                    "field_hints": _optional_field_hints(bundle, q["fields"]),
                    "allowed_values": None,
                    "answer_command": (f'isaac bundle decide <bundle_dir> --question {qid} --field <field path> --decision correct --value <value> --by "<your name>"'
                                       + (f"   # a number ({', '.join(numeric_fields)}): add --json, e.g. --value -0.8 --json" if numeric_fields else "")),
                }
            )
            continue
        node = _node(schema, path)
        enum = node.get("enum") if isinstance(node, Mapping) and isinstance(node.get("enum"), list) else None
        if enum is None and path in vocabulary:
            # D4: a vocabulary-controlled field (no schema enum, but the portal checks it).
            enum = vocabulary[path]
        numeric = _is_numeric(node)
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
            given = answered.get(path) or set()
            answers_differ = bool(given) and len(given | recorded.get(path, set())) > 1
            if answers_differ:
                # the question keeps its id (DEC-91); what the answers so far say is stated instead
                text += (f" Answers already given for this field elsewhere differ ({len(given)} distinct value(s) answered"
                         + (", besides what the files record" if recorded.get(path) else "")
                         + "): answer per group (--only group:<id>) unless they truly are all the same.")
            decision = "correct"
        else:
            text = f"Is the extracted {_label(path)} ({path}) right? Confirm it, or correct it."
            decision = "confirm"
            answers_differ = False
        hints = []
        if path.startswith("attribution.produced_by."):
            hints.append({"kind": "folder_name", "literal": bundle["source_root"]["label"], "locator": "the imported folder's name",
                          "note": "A PI or group name in a folder name is a HINT to ask about, never an answer."})
        if path.startswith("system.facility."):
            hints += S.facility_hints(bundle)
        ai = S.ai_hints(bundle, [t["id"] for t in q["targets"]])
        hints = ai + hints
        if ai:
            top = ai[0]
            cite = top.get("source_path") or top.get("source_id") or "a file"
            text += (f" Suggested from the files (needs your confirmation): {top['literal']!r}, from {cite}"
                     f"{' @ ' + str(top['locator']) if top.get('locator') else ''}"
                     + (f"; {len(ai) - 1} other suggestion(s) differ" if len(ai) > 1 else "") + ".")
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
                # L2: the answers already given for this field differ — an agent following
                # answer_command should answer per group (--only), not once for all
                "answers_differ": answers_differ,
                "answer_command": (
                    f'isaac bundle decide <bundle_dir> --question {qid} --decision {decision}'
                    + (f" --value {value_arg}" if kind == "missing_value" else "")
                    + ' --by "<your name>"'
                    + ("   # answers given so far DIFFER: answer per group with --only group:<group_id>" if answers_differ
                       else "   # per group: add --only group:<group_id>" if len(q["per_scope_targets"]) > 1 else "")
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
    # DEC-91: a position is ANSWERED once a scientist stated it is a counter (the latest
    # set_counter_positions) or is not one (set_not_counter_positions); the question asks only about
    # the positions still open and drops out when none is — under the SAME id throughout.
    from .mutations import counter_positions

    answered_positions = any(d.get("decision") in ("set_counter_positions", B.NOT_COUNTER_DECISION)
                             for d in bundle.get("scientist_decisions") or ())
    said_counter = set(counter_positions(bundle) or ())
    said_not = B.not_counter_positions(bundle)
    for gq in bundle.get("grouping_questions") or ():
        if not isinstance(gq, Mapping) or gq.get("kind") != "naming_counter_positions":
            continue
        asked_positions = [int(p) for p in gq.get("positions") or () if isinstance(p, int)]
        open_positions = [p for p in asked_positions if p not in said_counter and p not in said_not]
        if asked_positions and not open_positions:
            continue  # every position it asks about is answered: it drops out
        qid = _qid("experiment", "naming_counter_positions", str(gq.get("id") or gq.get("text") or ""))
        text = str(gq.get("text") or "Which filename token positions are run or acquisition counters?")
        if len(open_positions) < len(asked_positions):
            text += (" Already answered: position(s) " + ", ".join(str(p) for p in asked_positions if p not in open_positions)
                     + f"; still open: {', '.join(map(str, open_positions))}.")
        text += (" If none of the open positions is a counter (the numbers name distinct samples, electrodes or "
                 "conditions, or are a plain sequence that does not mark repeats), say so with "
                 f"{B.NOT_COUNTER_DECISION}: grouping is unchanged by that answer and each merge candidate stays open.")
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
                "text": text,
                "positions": open_positions,
                "applies_to": {"groups": len(groups), "runs": len(bundle["runs"]), "targets": 1},
                "targets": [{"kind": "experiment", "id": "experiment"}],
                "per_scope_targets": {"experiment": ["experiment"]},
                "hints": [{"kind": "grouping", "literal": gq.get("examples") or gq.get("options"), "locator": "the grouping step"}],
                "allowed_values": None,
                "answered": answered_positions,
                "answer_command": (
                    'isaac bundle decide <bundle_dir> --target experiment --decision set_counter_positions '
                    '--positions <n[,m]> --by "<your name>"  &&  isaac bundle group <bundle_dir> --regroup'
                    f'   # none is a counter: isaac bundle decide <bundle_dir> --question {qid} --decision {B.NOT_COUNTER_DECISION} --by "<your name>"'
                ),
            }
        )

    # THE INSTRUMENT CLOCK'S TIME ZONE (1.4.0): asked once for the beamtime while local-clock start
    # times wait on it. No value is suggested: no file states one (CLAUDE.md §5).
    zq = B.clock_zone_question(bundle)
    if zq is not None:
        qid = _qid("experiment", "clock_time_zone", "instrument_clock")
        questions.append(
            {
                "question_id": qid,
                "partition": None,
                "tier": TIER_OPTIONAL,
                "blocking": False,
                "why": ("Optional: the record can be exported without a start time, but these runs' start times "
                        "stay out of it until the clock's time zone is stated."),
                "kind": "clock_time_zone",
                "scope": "experiment",
                "target_field_path": B.XDC_START_PATH,
                "text": zq["text"],
                "applies_to": {"groups": len({group_of[r] for r in zq["run_ids"] if r in group_of}), "runs": len(zq["run_ids"]),
                               "targets": 1},
                "targets": [{"kind": "experiment", "id": "experiment"}],
                "per_scope_targets": {"experiment": ["experiment"]},
                "hints": [{"kind": "local_clock_literal", **zq["example"],
                           "note": "The header's own words: a local clock time with no zone. A hint about WHAT is asked, never an answer."}],
                "allowed_values": None,
                "suggested_value": None,
                "answer_command": (f'isaac bundle decide <bundle_dir> --question {qid} --decision {B.CLOCK_ZONE_DECISION} '
                                   '--value <IANA time-zone name> --by "<your name>"'),
            }
        )

    # A START TIME CONFIRMED UNDER ANOTHER CLOCK ZONE is asked again: its confirmation no longer
    # counts (bundle.local_clock_binding_problem), and it must not vanish from the list.
    again: dict[str, list[dict]] = {}
    for x in B.local_clock_reconfirm(bundle):
        again.setdefault(scope_of_run(x["run_id"]), []).append(x)
    value_of = {c["candidate_id"]: c["value"] for c in bundle["candidates"]}
    for scope, every in again.items():
        # where the zone now gives NO single instant (ambiguous / nonexistent) there is nothing to
        # confirm: each such start is asked on its own, answered with `correct --value`
        for x in [x for x in every if value_of.get(x["candidate_id"]) is None]:
            cid = x["candidate_id"]
            qid = _qid(scope, "confirm_value", B.XDC_START_PATH, "clock_zone_changed_no_instant", cid)
            questions.append(
                {
                    "question_id": qid,
                    "partition": None,
                    "tier": TIER_OPTIONAL,
                    "blocking": False,
                    "why": "Optional, but a confirmed start time no longer counts: the instrument clock's time zone changed after it was confirmed.",
                    "kind": "confirm_value",
                    "reason": "clock_zone_changed_after_confirmation",
                    "scope": scope,
                    "target_field_path": B.XDC_START_PATH,
                    "text": (f"The instrument clock's time zone changed after start time {cid} was confirmed, so that "
                             "confirmation no longer counts, and under the zone now recorded its local time is not a single "
                             "instant (ambiguous or nonexistent): there is nothing to confirm. Correct it with the UTC start."),
                    "applies_to": {"groups": 1 if x["run_id"] in group_of else 0, "runs": 1, "targets": 1},
                    "targets": [{"kind": "candidate", "id": cid}],
                    "per_scope_targets": {scope: [cid]},
                    "hints": [{"kind": "why_asked_again", "literal": x["reason"], "candidate_id": cid}],
                    "allowed_values": None,
                    "allowed_decisions_note": "correct (with a UTC value), reject or defer; confirm is refused: there is no value to confirm",
                    "answer_command": (f'isaac bundle decide <bundle_dir> --question {qid} --decision correct '
                                       '--value YYYY-MM-DDTHH:MM:SSZ --by "<your name>"'),
                }
            )
        items = [x for x in every if value_of.get(x["candidate_id"]) is not None]
        if not items:
            continue
        qid = _qid(scope, "confirm_value", B.XDC_START_PATH, "clock_zone_changed")
        values = {x["candidate_id"]: value_of[x["candidate_id"]] for x in items}
        questions.append(
            {
                "question_id": qid,
                "partition": None,
                "tier": TIER_OPTIONAL,
                "blocking": False,
                "why": "Optional, but a confirmed start time no longer counts: the instrument clock's time zone changed after it was confirmed.",
                "kind": "confirm_value",
                "reason": "clock_zone_changed_after_confirmation",
                "scope": scope,
                "target_field_path": B.XDC_START_PATH,
                "text": (f"The instrument clock's time zone changed after {len(items)} start time(s) here were confirmed, so "
                         "those confirmations no longer count. Under the zone now recorded the start is "
                         + ", ".join(f"{v} ({cid})" for cid, v in values.items())
                         + ". Confirm it again, or correct it."),
                "applies_to": {"groups": len({group_of[x["run_id"]] for x in items if x["run_id"] in group_of}),
                               "runs": len({x["run_id"] for x in items}), "targets": len(items)},
                "targets": [{"kind": "candidate", "id": x["candidate_id"]} for x in items],
                "per_scope_targets": {scope: [x["candidate_id"] for x in items]},
                "hints": [{"kind": "why_asked_again", "literal": x["reason"], "candidate_id": x["candidate_id"]} for x in items[:_HINTS_PER_QUESTION]],
                "allowed_values": None,
                "answer_command": f'isaac bundle decide <bundle_dir> --question {qid} --decision confirm --by "<your name>"',
            }
        )

    questions += _absorber_questions(bundle, groups)

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
    for q in questions:
        q["allowed_decisions"] = list(ALLOWED_DECISIONS.get(q["kind"], ()))
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


def _optional_field_hints(bundle: Mapping, fields: Mapping[str, Sequence[str]]) -> dict[str, list[dict]]:
    """Per optional field: the AI readings of its targets, and the facility hints."""
    out: dict[str, list[dict]] = {}
    for path, ids in sorted(fields.items()):
        hints = S.ai_hints(bundle, ids)
        if path.startswith("system.facility."):
            hints += S.facility_hints(bundle)
        if hints:
            out[path] = hints
    return out


def _absorber_hints(items: Sequence[tuple[Mapping, dict]]) -> list[dict]:
    """FILE EVIDENCE FIRST — a processed-output summary, then each distinct beamtime-wide
    statement — then each distinct AI reading, labelled as an AI suggestion with its citation.
    Each list is capped on its own, so file evidence never crowds out an AI reading's
    disclosure (or the reverse)."""
    hints: list[dict] = []
    po = [w for _, s in items for w in s["witnesses"] if w["kind"] == "processed_output_header"]
    if po:
        n = len({w.get("processed_output_id") for w in po})
        el = next((w["element"] for w in po if w.get("element")), None)
        ed = next((w["edge"] for w in po if w.get("edge")), None)
        hints.append({"kind": "processed_output_header", "literal": f"{el or '?'} {ed or '?'}",
                      "locator": po[0].get("locator"), "relative_path": po[0].get("relative_path"), "source_id": po[0].get("source_id"),
                      "note": f"from {n} linked processed output(s) (e.g. this one; an output can be linked to runs of several groups); links are proposed by name, not confirmed"})
    seen = set()
    for _, s in items:
        for w in s["witnesses"]:
            key = (w.get("source_id"), w.get("locator"))
            if w["kind"] == "beamtime_element_evidence" and key not in seen:
                seen.add(key)
                hints.append({"kind": w["kind"], "literal": f"{w.get('element') or '?'} {w.get('edge') or '?'}", "locator": w.get("locator"),
                              "source_id": w.get("source_id"), "relative_path": w.get("relative_path"), "note": "stated for the whole beamtime"})
    ai: dict[tuple, dict] = {}
    for g, s in items:
        for r in s.get("ai_readings") or ():
            key = (r["field"], repr(r["value"]), r.get("source_path"), r.get("locator"))
            h = ai.get(key)
            if h is None:
                h = ai[key] = {
                    "kind": "ai_suggestion",
                    "field": r["field"],
                    "literal": r["value"],
                    "locator": r.get("locator"),
                    "source_id": r.get("source_id"),
                    "source_path": r.get("source_path"),
                    "quote": r.get("quote"),
                    "strength": r.get("strength"),
                    "model_id": r.get("model_id"),
                    "groups": 0,
                    "differs_from_files": False,
                    "note": (f"The {r['half']}, suggested by an AI reading of the files; the quote is as the reader gave it. "
                             "Not file evidence: confirm it with set_absorber, or answer otherwise; it is never used on its own."),
                }
            h["groups"] += 1
            if r.get("read_for"):
                h.setdefault("read_for", []).append({"group_id": g["group_id"], "run_ids": r["run_ids"], "text": r["read_for"]})
            if s.get("ai_vs_files", {}).get(r["half"]) == "differs" and r["value"] not in s["readings"][r["half"]]:
                h["differs_from_files"] = True
    for h in ai.values():
        if h["differs_from_files"]:
            h["note"] += " It DIFFERS from what the files state; nothing has chosen between them."
        for part in h.get("read_for") or ():
            h["note"] += f" Group {part['group_id']}: {part['text']}."
    return hints[:_HINTS_PER_QUESTION] + list(ai.values())[:_HINTS_PER_QUESTION]


def _ai_pair(sug: Mapping) -> tuple[str, str] | None:
    """The one element and one edge the AI readings of a group name, or ``None``."""
    els = {r["value"] for r in sug.get("ai_readings") or () if r["half"] == "element"}
    eds = {r["value"] for r in sug.get("ai_readings") or () if r["half"] == "edge"}
    return (next(iter(els)), next(iter(eds))) if len(els) == 1 and len(eds) == 1 else None


def _absorber_questions(bundle: Mapping, groups: Sequence[Mapping]) -> list[dict]:
    """The absorbing element and edge, asked ONCE per distinct suggestion over the groups
    the files agree on (or, where no file states it, the AI readings agree on), and per group
    where they disagree, are partial, or an AI reading differs from the files. Optional: the
    official schema has no absorber field (a confirmed one is carried in the evidence sidecar)."""
    decided = S.absorber_decisions(bundle)
    by_pair: dict[tuple, list] = {}
    split: list[tuple[Mapping, dict]] = []
    for g in groups:
        if g["group_id"] in decided:
            continue
        sug = S.absorber_for_group(bundle, g)
        if sug["status"] == "agrees" and not sug["ai_disagrees_with_files"]:
            by_pair.setdefault((sug["element"], sug["edge"]), []).append((g, sug))
        elif sug["status"] == "none" and sug["ai_readings"] and _ai_pair(sug):
            by_pair.setdefault(_ai_pair(sug), []).append((g, sug))
        elif sug["status"] in ("disagrees", "partial", "agrees") or sug["ai_readings"]:
            split.append((g, sug))
    out = []
    for (element, edge), items in sorted(by_pair.items()):
        qid = _qid("experiment", "confirm_absorber", f"{element}|{edge}")
        from_files = [(g, s) for g, s in items if s["status"] == "agrees"]
        ai_only = len(items) - len(from_files)
        if not ai_only:
            text = (f"The files state element {element}, edge {edge} for {len(items)} group(s), and no file disagrees: "
                    f"{sum(1 for _, s in items if s['group_specific_statements'])} of them from processed outputs linked to their runs, "
                    f"the rest only from beamtime-wide statements ({items[0][1]['beamtime_wide_statements']}, e.g. an acquisition macro's name). "
                    "Is that the absorber? Answer once, or per group (a reference foil or blank cell may differ).")
            element_arg, edge_arg = element, edge
        else:
            partial = sum(1 for _, s in items for r in s["ai_readings"] if r.get("read_for"))
            text = (f"Element {element}, edge {edge} is suggested for {len(items)} group(s): "
                    + (f"the files state it for {len(from_files)}; " if from_files else "")
                    + f"for {ai_only}, no file the import parsed states the absorber and only an AI reading of the files suggests it "
                      "(needs your confirmation: an AI reading is not file evidence). "
                      "Is that the absorber? Answer once, or per group (a reference foil or blank cell may differ)."
                    + (f" {partial} AI reading(s) name only some of a group's runs (see the hints)." if partial else ""))
            element_arg, edge_arg = "<El>", "<K|L1-L3|M1-M5>"
        out.append({
            "question_id": qid,
            "partition": None,
            "tier": TIER_OPTIONAL,
            "blocking": False,
            "why": "Optional: the official schema has no absorber field. A confirmed absorber is kept in the evidence sidecar.",
            "kind": "confirm_absorber",
            "scope": "experiment",
            "target_field_path": None,
            "text": text,
            "applies_to": {"groups": len(items), "runs": sum(len(g.get("member_run_keys") or ()) for g, _ in items), "targets": len(items)},
            "targets": [{"kind": "record_group", "id": g["group_id"]} for g, _ in items],
            "per_scope_targets": {f"group:{g['group_id']}": [g["group_id"]] for g, _ in items},
            "hints": _absorber_hints(items),
            "allowed_values": None,
            "answer_command": (f'isaac bundle decide <bundle_dir> --question {qid} --decision set_absorber '
                               f'--element {element_arg} --edge {edge_arg} --by "<your name>"   # per group: add --only group:<group_id>'),
        })
    for g, sug in split:
        qid = _qid(f"group:{g['group_id']}", "confirm_absorber", "")
        if sug["status"] == "none":
            said = ", ".join(f"{r['half']} {r['value']}" for r in sug["ai_readings"])
            text = ("No file the import parsed states this group's absorber, and the AI readings of the files disagree "
                    f"or name only one half (AI readings: {said}). Nothing has chosen between them. Which is it?")
        elif sug["status"] == "agrees":
            text = (f"The files state element {sug['element']}, edge {sug['edge']} for this group, but an AI reading of the files "
                    f"differs ({', '.join(h for h, v in sug['ai_vs_files'].items() if v == 'differs')}). Nothing has chosen between them. Which is it?")
        else:
            text = (f"The files {'disagree about' if sug['status'] == 'disagrees' else 'only partly state'} this group's absorber "
                    f"(element readings {sug['readings']['element']}, edge readings {sug['readings']['edge']}). Which is it?")
            if sug["ai_disagrees_with_files"]:
                text += " An AI reading of the files also differs from them."
        for r in sug["ai_readings"]:
            if r.get("read_for"):
                text += f" The AI reading {r['half']} {r['value']} was {r['read_for']}."
        out.append({
            "question_id": qid,
            "partition": None,
            "tier": TIER_OPTIONAL,
            "blocking": False,
            "why": "Optional: the official schema has no absorber field. A confirmed absorber is kept in the evidence sidecar.",
            "kind": "confirm_absorber",
            "scope": f"group:{g['group_id']}",
            "target_field_path": None,
            "text": text,
            "applies_to": {"groups": 1, "runs": len(g.get("member_run_keys") or ()), "targets": 1},
            "targets": [{"kind": "record_group", "id": g["group_id"]}],
            "per_scope_targets": {f"group:{g['group_id']}": [g["group_id"]]},
            "hints": _absorber_hints([(g, sug)]),
            "allowed_values": None,
            "answer_command": f'isaac bundle decide <bundle_dir> --question {qid} --decision set_absorber --element <El> --edge <K|L1-L3|M1-M5> --by "<your name>"',
        })
    return out


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


def question(payload: Mapping, question_id: str) -> Mapping | None:
    return next((q for q in payload["questions"] if q["question_id"] == question_id), None)


def targets_for(payload: Mapping, question_id: str, only: str | None = None, field: str | None = None) -> list[str]:
    q = question(payload, question_id)
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
