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
  hint, never an answer), allowed values where a fixed list closes the field
  (``bundle.allowed_values``: exactly what ``decide`` accepts and the export validates against), and the exact ``isaac bundle decide --question`` command that answers it — always a
  TEMPLATE with placeholders, never a value read from the files or an AI.
* A ``confirm_value`` question whose candidates carry no value asks "What is X?", cites the
  text the files hold, and does not offer ``confirm``. One about a path no answer can reach the
  record from (an array path; a path with no write route) is ``informational``: listed under its
  id, answerable by nothing. A scientist's answer the record cannot take
  (``eligibility_for_official_record``) is ASKED AGAIN under the question's own id, with why.

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
#: How many other questions ``same_statement_as`` / ``same_reading_as`` name (the count is in the text).
_CROSS_REFERENCES = 10
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
#: A ``confirm_value`` question whose targets carry NO value (the files hold text, no value this
#: build derives from it): there is nothing to confirm, so ``confirm`` is not offered. The kind —
#: and so the question id — is unchanged; only the decisions, text and command differ.
VALUELESS_DECISIONS: tuple[str, ...] = ("correct", "reject", "defer")
#: A question about a field the record builder never fills from an answer (an array path, or a
#: path this build has no write route for): kept under its id, answered by nothing.
INFORMATIONAL_DECISIONS: tuple[str, ...] = ()
#: Why the record builder can never fill a path from a scientist's answer, or ``None``.
_ARRAY_PATH_REASON = ("an array path: the record builder composes it only from structured blocks (an approved "
                      "processing result, the evidence sidecar), never from a confirmed value")
_NO_WRITE_PATH_REASON = "this build has no write path for this official field, so a confirmed value stays evidence"


def _never_lands(path: str | None, writable: frozenset[str]) -> str | None:
    """Why no answer at ``path`` can reach a record (``records.compose_group`` skips every ``[]``
    path; ``bundle.eligibility_for_official_record`` refuses a path outside the write routes)."""
    if not path:
        return None
    if "[]" in path:
        return _ARRAY_PATH_REASON
    if path not in writable:
        return _NO_WRITE_PATH_REASON
    return None


def _is_shared(path: str) -> bool:
    return any(path == p.rstrip(".") or path.startswith(p) for p in SHARED_PATHS)


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
    """:func:`bundle.allowed_values` — THE list a field takes, the one ``bundle.value_problem`` (so
    ``decide`` and eligibility) refuses outside of and the export validates against — or ``None``
    when no fixed list closes the field. Every list a question offers is this one."""
    return B.allowed_values(path)


def _extracted_value_problem(candidate: Mapping | None, writable: frozenset[str]) -> str | None:
    """Why ``decide`` would refuse to CONFIRM a candidate's extracted value (its field refuses it:
    ``bundle.value_problem``), or ``None``. A path this build does not write is not checked (``decide``
    does not check it either); a value-less candidate is the caller's other case."""
    if not candidate or candidate.get("value") is None or B.is_local_clock_start(candidate):
        return None  # a local clock time is confirmed as the UTC value its stated zone gives it, not as stored
    path = candidate.get("target_field_path")
    if not path or path not in writable:
        return None
    return B.value_problem(path, candidate["value"])


def _is_numeric(node: Mapping | None) -> bool:
    return isinstance(node, Mapping) and node.get("type") in ("number", "integer", ["number", "null"])


def _label(path: str) -> str:
    return path.rsplit(".", 1)[-1].replace("_", " ")


def _qid(*parts: str) -> str:
    return "Q-" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]


def consolidate(bundle: Mapping) -> dict:
    """``questions.json`` v2 for ``bundle``. Pure: reads the bundle, writes nothing."""
    schema, basis = _target_schema()
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
    groups = live_groups(bundle)
    run_by_key = {r["run_key"]: r["run_id"] for r in bundle["runs"]}
    run_by_id = {r["run_id"]: r for r in bundle["runs"]}
    cand_by_id = {c["candidate_id"]: c for c in bundle["candidates"]}
    writable = B._writable_paths()
    source_path_of = {x["source_id"]: x.get("relative_path") for x in bundle.get("sources") or ()}
    ai_hints = _ai_hint_index(bundle)
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
    # ASKED AGAIN: a scientist's answer the record cannot take (bundle.eligibility_for_official_record,
    # e.g. "ex situ" where the schema allows ex_situ) leaves its target unanswered for the record, so
    # it is asked again — in the SAME bucket, so under the SAME id — with the reason stated. A
    # start time whose clock zone changed is asked again by its own question below; a path no answer
    # can ever reach (an array path, no write route) is never asked again (nothing would land).
    reconfirm_ids = {x["candidate_id"] for x in B.local_clock_reconfirm(bundle)}
    conflict_again: dict[str, dict] = {}

    def not_eligible_answer(obj: Mapping, kind: str) -> dict | None:
        # the ONE definition of "answered, but the record cannot take it" (bundle.unusable_answer_reason)
        if B.unusable_answer_reason(obj, writable) is None:
            return None
        fit = obj.get("eligibility_for_official_record") or {}
        if kind == "candidate":
            if obj["candidate_id"] in reconfirm_ids:
                return None
            d = B.candidate_decision(bundle, obj, decisions)
            value, tid = B.final_value(obj["value"], d, obj.get("readings")), obj["candidate_id"]
            via = (d or {}).get("target") or {}
            if via.get("kind") == "conflict":
                # answered by settling a conflict: THAT question (its id) is asked again
                conflict_again[via.get("id")] = {"target": {"kind": "conflict", "id": via.get("id")}, "answered": value,
                                                 "decision_id": (d or {}).get("decision_id"), "reason": fit.get("reason"),
                                                 "candidate_id": tid}
                return None
        else:
            d = decisions.get(("missing_value", obj["value_id"]))
            value, tid = B.final_value(None, d), obj["value_id"]
        return {"target": {"kind": kind, "id": tid}, "answered": value, "decision_id": (d or {}).get("decision_id"),
                "reason": fit.get("reason")}

    path_of_value = {m["value_id"]: m["target_field_path"] for m in bundle["missing_values"]}
    unfit_values = {m["value_id"] for m in bundle["missing_values"] if not_eligible_answer(m, "missing_value")}
    for (kind, tid), d in decisions.items():
        if kind == "missing_value" and d.get("value") is not None and tid in path_of_value and tid not in unfit_values:
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
            blocking: str | None, partition: str | None = None, field: str | None = None, again: dict | None = None):
        q = buckets.get(key)
        if q is None:
            q = buckets[key] = {
                "kind": kind,
                "scope": scope,
                "partition": partition,
                "target_field_path": path,
                "required_by": blocking,
                "targets": [],
                # LINEAR, not quadratic: membership is checked against this set (order is the list's)
                "target_keys": set(),
                "per_scope_targets": {},
                "fields": {},
                "runs": set(),
                "asked_again": [],
            }
        if field is not None:
            q["fields"].setdefault(field, []).append(target["id"])
        tkey = (target["kind"], target["id"])
        if tkey not in q["target_keys"]:
            q["target_keys"].add(tkey)
            q["targets"].append(target)
            if again is not None:
                q["asked_again"].append({**again, **({"field": field} if field is not None else {})})
        q["per_scope_targets"].setdefault(scope_of_run(run_id), []).append(target["id"])
        if run_id:
            q["runs"].add(run_id)
        if blocking and not q["required_by"]:
            q["required_by"] = blocking

    for m in bundle["missing_values"]:
        again = None
        if m["value_state"] not in _UNANSWERED:
            again = not_eligible_answer(m, "missing_value")
            if again is None:
                continue
        path, rid = m["target_field_path"], m["run_id"]
        if rid is not None and group_of and rid not in group_of:
            run = run_by_id.get(rid)
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
                target={"kind": "missing_value", "id": m["value_id"]}, run_id=rid, scope=scope, blocking=blocking, again=again)
        else:
            # OPTIONAL values are one question per scope, listing each field (answered per
            # field with --field), so they never outnumber the blocking ones.
            add((scope, "optional_values", None, partition), kind="optional_values", path=None, partition=partition,
                target={"kind": "missing_value", "id": m["value_id"]}, run_id=rid, scope=scope, blocking=None, field=path,
                again=again)

    zone_decided = B.clock_zone_decision(bundle) is not None
    for c in bundle["candidates"]:
        path = c["target_field_path"]
        if not path:
            continue
        again = None
        if c["value_state"] not in (B.STATE_NEEDS_REVIEW, B.STATE_CANDIDATE_EXTRACTED):
            again = not_eligible_answer(c, "candidate")
            if again is None:
                continue
        if not zone_decided and B.is_local_clock_start(c):
            continue  # nothing to confirm until the clock's zone is stated: the zone question asks that
        blocking = required_for(path, c["run_id"])
        if again is None and c["value_state"] == B.STATE_CANDIDATE_EXTRACTED and not blocking:
            continue  # an extracted optional value is not asked about (one a scientist answered unfitly is)
        scope = scope_of_run(c["run_id"])
        add((scope, "confirm_value", path, None), kind="confirm_value", path=path, partition=None,
            target={"kind": "candidate", "id": c["candidate_id"]}, run_id=c["run_id"], scope=scope, blocking=blocking,
            again=again)

    conflicts_out = []
    for cf in bundle["conflicts"]:
        if cf["value_state"] not in (B.STATE_CONFLICTING, B.STATE_NEEDS_REVIEW) and cf["conflict_id"] not in conflict_again:
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
                             + (f" {len(fh)} of them have a suggestion or hint (field_hints)." if (fh := _optional_field_hints(bundle, q["fields"], ai_hints)) else "")
                             + _asked_again_text(q["asked_again"], {f: _eligible_values(f) for f in q["fields"]})),
                    "asked_again": q["asked_again"],
                    "applies_to": {"groups": len({group_of[r] for r in q["runs"] if r in group_of}), "runs": len(q["runs"]), "targets": len(q["targets"])},
                    "targets": q["targets"],
                    "per_scope_targets": q["per_scope_targets"],
                    "fields": {f: ids for f, ids in sorted(q["fields"].items())},
                    # bundle.allowed_values — the one list `decide` and eligibility (bundle.value_problem)
                    # refuse outside of and the export validates against — for each field it closes
                    "field_allowed_values": {f: a for f in sorted(q["fields"]) if (a := _eligible_values(f))},
                    "hints": [],
                    "field_hints": fh,
                    "allowed_values": None,
                    "answer_command": (f'isaac bundle decide <bundle_dir> --question {qid} --field <field path> --decision correct --value <value> --by "<your name>"'
                                       + (f"   # a number ({', '.join(numeric_fields)}): add --json, e.g. --value -0.8 --json" if numeric_fields else "")),
                }
            )
            continue
        node = _node(schema, path)
        # THE ONE LIST (H1): what is offered is exactly what `decide` accepts and the export validates
        # against (bundle.allowed_values) — a vocabulary-controlled field included (D4).
        enum = _eligible_values(path)
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
            decision = "confirm"
            answers_differ = False
        # WHAT A confirm_value QUESTION CAN BE ANSWERED WITH. A target whose candidate carries NO value
        # (the files hold text this build derives no value from) has nothing to confirm — `decide`
        # refuses `confirm` on it — so the question asks for the value instead, cites the text the
        # files hold, and never offers `confirm`. A path no answer can reach is informational.
        valueless = [t["id"] for t in q["targets"] if t["kind"] == "candidate" and (cand_by_id.get(t["id"]) or {}).get("value") is None]
        never = _never_lands(path, writable) if kind == "confirm_value" else None
        # A target whose EXTRACTED value its field refuses (bundle.value_problem — e.g. an older build
        # stored a confirm of it, now asked again) cannot be confirmed either: `decide` refuses that
        # confirm, so it is offered only `correct` (or reject / defer), exactly like a value-less one.
        unfit = ({t["id"]: why for t in q["targets"] if t["kind"] == "candidate" and t["id"] not in valueless
                  and (why := _extracted_value_problem(cand_by_id.get(t["id"]), writable)) is not None}
                 if kind == "confirm_value" and not never else {})
        unconfirmable = set(valueless) | set(unfit)
        decisions_offered = None
        own_literals: list[dict] = []
        if kind == "confirm_value":
            own_literals = _own_literal_hints(source_path_of, [cand_by_id[i] for i in (t["id"] for t in q["targets"]) if i in cand_by_id])
            summary = next((s for t in q["targets"] if (s := ((cand_by_id.get(t["id"]) or {}).get("state_basis") or {}).get("not_proposable_summary"))), None)
            if never:
                text = (f"For information only: the files hold a reading for the {_label(path)} ({path}), and no answer here can "
                        f"reach the record ({never}). The reading stays evidence; nothing is asked.")
                decisions_offered = list(INFORMATIONAL_DECISIONS)
            elif len(valueless) == len(q["targets"]):
                text = (f"What is the {_label(path)} ({path})? The files hold text for it (see the hints) but no value this "
                        "build can carry" + (f": {summary.rstrip('.')}" if summary else "")
                        + ". There is nothing to confirm: give the value yourself (correct), or reject or defer it.")
                decision = "correct"
                decisions_offered = list(VALUELESS_DECISIONS)
            elif len(unconfirmable) == len(q["targets"]):
                text = (f"What is the {_label(path)} ({path})? The value extracted from the files does not fit the field ("
                        + next(iter(unfit.values())).rstrip(".")
                        + "), so there is nothing to confirm: give the value yourself (correct), or reject or defer it.")
                decision = "correct"
                decisions_offered = list(VALUELESS_DECISIONS)
            else:
                text = f"Is the extracted {_label(path)} ({path}) right? Confirm it, or correct it."
                if valueless:
                    text += (f" {len(valueless)} of its {len(q['targets'])} target(s) carry no value ({', '.join(valueless[:5])}"
                             f"{'…' if len(valueless) > 5 else ''}): confirm refuses them; answer those with correct --value, "
                             "per group (--only group:<group_id>).")
                if unfit:
                    names = sorted(unfit)
                    text += (f" {len(unfit)} of its {len(q['targets'])} target(s) carry an extracted value the field refuses "
                             f"({', '.join(names[:5])}{'…' if len(names) > 5 else ''}): confirm refuses them too; answer those "
                             "with correct --value, per group (--only group:<group_id>).")
        hints = []
        if path.startswith("attribution.produced_by."):
            hints.append({"kind": "folder_name", "literal": bundle["source_root"]["label"], "locator": "the imported folder's name",
                          "note": "A PI or group name in a folder name is a HINT to ask about, never an answer."})
        if path.startswith("system.facility."):
            hints += S.facility_hints(bundle)
        ai = ai_hints([t["id"] for t in q["targets"]])
        # the text THIS question's own targets hold comes first (a value-less question is answered from it)
        hints = own_literals + ai + hints
        if ai and not never:
            top = ai[0]
            cite = top.get("source_path") or top.get("source_id") or "a file"
            text += (f" Suggested from the files (needs your confirmation): {top['literal']!r}, from {cite}"
                     f"{' @ ' + str(top['locator']) if top.get('locator') else ''}"
                     + (f"; {len(ai) - 1} other suggestion(s) differ" if len(ai) > 1 else "") + ".")
        mine = {t["id"] for t in q["targets"]}
        shown_own = {h.get("candidate_id") for h in own_literals}
        for c in related.get(path, [])[:_HINTS_PER_QUESTION]:
            if c["observed_literals"] and c["candidate_id"] not in shown_own:
                ev = next((e for e in c["evidence"] if e["method"] != "ai_interpretation"), None)
                hints.append({"kind": "related_reading", "candidate_id": c["candidate_id"], "literal": c["observed_literals"][0],
                              "locator": (ev or {}).get("locator"), "source_id": (ev or {}).get("source_id"),
                              # a reading of the same field ELSEWHERE in the import (another run or group) is
                              # context, not this question's own evidence
                              "of_this_question": c["candidate_id"] in mine})
        text += _asked_again_text(q["asked_again"], {path: enum})
        value_arg = "<value>" + (" --json" if numeric else "")
        qid = _qid(scope, kind, path, partition or "")
        blocking_here = bool(q["required_by"]) and not never
        per_group_note = ("   # answers given so far DIFFER: answer per group with --only group:<group_id>" if answers_differ
                          else "   # per group: add --only group:<group_id>" if len(q["per_scope_targets"]) > 1 else "")
        # the scopes a `confirm` is accepted for: every target there carries a value its field takes
        confirmable_scopes = sorted(sc for sc, ids in q["per_scope_targets"].items() if not unconfirmable.intersection(ids))
        if never:
            command = f"# nothing to answer: no answer to {qid} can reach the record ({never})"
        elif decision == "confirm" and unconfirmable:
            # A MIXED question: `decide` checks every target and refuses the whole answer when one cannot be
            # confirmed, so a confirm is offered only per scope where every target can be (confirmable_scopes)
            command = (f'isaac bundle decide <bundle_dir> --question {qid} --decision confirm --only <scope> --by "<your name>"'
                       + "   # confirm only a scope in confirmable_scopes"
                       + (f" ({', '.join(confirmable_scopes[:3])}{'…' if len(confirmable_scopes) > 3 else ''})" if confirmable_scopes else
                          " (none: answer every scope with --decision correct --value <value>)")
                       + "; answer the others with --decision correct --value <value>")
        else:
            command = (f'isaac bundle decide <bundle_dir> --question {qid} --decision {decision}'
                       + (f" --value {value_arg}" if decision == "correct" else "")
                       + ' --by "<your name>"' + per_group_note)
        entry = {
            "question_id": qid,
            "partition": partition,
            "tier": TIER_BLOCKING if blocking_here else TIER_OPTIONAL,
            "blocking": blocking_here,
            "why": (f"The record cannot be exported without it: the target schema requires {q['required_by']}."
                    if blocking_here else
                    f"Informational: {never}." if never else "Optional: the record can be exported without it."),
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
            "answer_command": command,
        }
        if kind == "confirm_value":
            entry["targets_without_a_value"] = len(valueless)
            entry["targets_with_an_unfit_value"] = len(unfit)
            entry["confirmable_scopes"] = confirmable_scopes if "confirm" in (decisions_offered if decisions_offered is not None
                                                                              else ALLOWED_DECISIONS[kind]) else []
            entry["lands_in_record"] = not never
            if never:
                entry["informational"] = True
        if q["asked_again"]:
            entry["asked_again"] = q["asked_again"]
            entry["reason"] = "answer_not_eligible_for_official_record"
        if decisions_offered is not None:
            entry["allowed_decisions"] = decisions_offered
        questions.append(entry)
    for scope, cf, affects, path, required in conflicts_out:
        enum = _eligible_values(path) if path else None
        again = [conflict_again[cf["conflict_id"]]] if cf["conflict_id"] in conflict_again else []
        questions.append(
            {
                **({"asked_again": again, "reason": "answer_not_eligible_for_official_record"} if again else {}),
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
                "text": (f"The sources disagree ({cf['kind']}{', ' + str(cf['subject']) if cf['subject'] else ''}). Which reading is right?"
                         + _asked_again_text(again, {path: enum} if path else {})),
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
        # an informational question (nothing to answer) sorts after every question that has an answer
        return (q["tier"], bool(q.get("informational")), s, q["target_field_path"] or "", q["question_id"])

    _note_shared_evidence(questions, cand_by_id, bundle)
    questions.sort(key=order)
    for q in questions:
        q.setdefault("allowed_decisions", list(ALLOWED_DECISIONS.get(q["kind"], ())))
    return {
        "format": FORMAT_ID,
        "format_version": FORMAT_VERSION,
        "bundle_id": bundle.get("bundle_id"),
        "blocking_basis": basis,
        "counts": {
            "total": len(questions),
            "blocking": sum(q["tier"] == TIER_BLOCKING for q in questions),
            "conflicts_affecting_a_record": sum(q["tier"] == TIER_CONFLICT for q in questions),
            "optional": sum(q["tier"] == TIER_OPTIONAL and not q.get("informational") for q in questions),
            # questions kept under their ids that no answer can reach the record from (an array path,
            # or a path this build has no write route for): listed, never answerable
            "informational": sum(bool(q.get("informational")) for q in questions),
            # targets a scientist answered with a value the record cannot take, asked again
            "asked_again": sum(len(q.get("asked_again") or ()) for q in questions),
            "fine_grained_v1": len(bundle.get("questions") or ()),
        },
        "questions": questions,
    }


def live_groups(bundle: Mapping) -> list[Mapping]:
    """The record groups that can still become records: not rejected, and not replaced by a split
    or a merge. Questions, and the nearest group to export, are only ever about these."""
    return [g for g in bundle.get("record_groups") or () if g.get("status") not in ("rejected", "split", "merged")]


def _own_literal_hints(path_of: Mapping[str, str | None], cands: Sequence[Mapping]) -> list[dict]:
    """The literal text each of a question's OWN candidates holds, with the file and locator it was
    read at (deduplicated by statement). What the files say — a hint, never an answer.
    ``path_of``: ``source_id -> relative_path``."""
    out: list[dict] = []
    seen: set = set()
    for c in cands:
        if not c.get("observed_literals"):
            continue
        ev = next((e for e in c.get("evidence") or () if e.get("method") != "ai_interpretation"), None) or {}
        key = (c["observed_literals"][0], ev.get("source_id"), ev.get("locator"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": "file_literal", "candidate_id": c["candidate_id"], "literal": c["observed_literals"][0],
                    "locator": ev.get("locator"), "source_id": ev.get("source_id"),
                    "relative_path": ev.get("relative_path") or path_of.get(ev.get("source_id")),
                    "carries_value": c.get("value") is not None,
                    "note": "The text the file holds for this field, as written. A hint about what to answer, never the answer."})
        if len(out) >= _HINTS_PER_QUESTION:
            break
    return out


def _asked_again_text(again: Sequence[Mapping], allowed_by_path: Mapping[str, list | None]) -> str:
    """The sentence that says why answered targets are asked again, or ``""``: each distinct answer
    once, with how many targets hold it and the reason it cannot go into the record."""
    if not again:
        return ""
    by_answer: dict[tuple, list[Mapping]] = {}
    for a in again:
        by_answer.setdefault((json.dumps(a["answered"], sort_keys=True, default=str), a.get("field"), a.get("reason")), []).append(a)
    parts = []
    for (_, field, reason), items in list(by_answer.items())[:3]:
        parts.append(f"{items[0]['answered']!r}" + (f" for {field}" if field else "")
                     + f" ({len(items)} target(s): {', '.join(a['target']['id'] for a in items[:3])}{'…' if len(items) > 3 else ''})"
                     + f": {reason or 'not eligible for the record'}")
    fields = {a.get("field") for a in again}
    allowed = [f"{p}: {', '.join(map(str, v))}" for p, v in allowed_by_path.items()
               if v and (len(allowed_by_path) == 1 or p in fields)]
    return (f" ASKED AGAIN: {len(again)} answer(s) already given here cannot go into the record — "
            + "; ".join(parts) + (f"; and {len(by_answer) - 3} other answer(s)" if len(by_answer) > 3 else "")
            + (f". Allowed values ({'; '.join(allowed)})" if allowed else "")
            + ". Answer again with a value the record can take.")


def _note_shared_evidence(questions: list[dict], cand_by_id: Mapping[str, Mapping], bundle: Mapping) -> None:
    """Per-group ``confirm_value`` questions about one field that rest on the SAME file statement (or the
    same literal reading) name each other (``same_statement_as`` / ``same_reading_as``), so one file line
    asked per group is visibly one statement. And where a BEAMTIME value for that field is open or already
    answered (it fills every record but DEC-69's run-only fields, records.compose_group), the per-group
    question does not block: answering the experiment-wide one fills this group's record too. Ids, scopes
    and targets are untouched (DEC-91): only text, ``blocking`` and ``tier`` change."""
    from .records import RUN_ONLY_PATHS

    def statement(q):
        out = set()
        for t in q["targets"]:
            c = cand_by_id.get(t["id"])
            if c is None or not c.get("observed_literals"):
                return None
            ev = next((e for e in c.get("evidence") or () if e.get("method") != "ai_interpretation"), None) or {}
            out.add((c["observed_literals"][0], ev.get("source_id"), ev.get("locator")))
        return frozenset(out) or None

    per_group = [q for q in questions if q["kind"] == "confirm_value" and q["scope"].startswith("group:")
                 and not q.get("informational") and q["targets"] and all(t["kind"] == "candidate" for t in q["targets"])]
    path_of_source = {x["source_id"]: x.get("relative_path") for x in bundle.get("sources") or ()}
    by_statement: dict[tuple, list[dict]] = {}
    by_reading: dict[tuple, list[dict]] = {}
    for q in per_group:
        st = statement(q)
        if st is None:
            continue
        by_statement.setdefault((q["target_field_path"], st), []).append(q)
        by_reading.setdefault((q["target_field_path"], frozenset(lit for lit, _, _ in st)), []).append(q)
    for (path, st), qs in by_statement.items():
        if len(qs) < 2:
            continue
        lit, src, loc = sorted(st, key=repr)[0]
        where = path_of_source.get(src) or src
        ids = [o["question_id"] for o in qs]
        for q in qs:
            # bounded (never one list of every other group per question: that grows as groups squared)
            q["same_statement_as"] = [i for i in ids[:_CROSS_REFERENCES + 1] if i != q["question_id"]][:_CROSS_REFERENCES]
            q["text"] += (f" The same file statement ({where} @ {loc}: {lit!r}) is behind {len(qs) - 1} other group "
                          f"question(s) for this field (same_statement_as names up to {_CROSS_REFERENCES}): it is one statement in the files, asked per "
                          "group because each record carries its own answer.")
    for (path, lits), qs in by_reading.items():
        rest = [q for q in qs if "same_statement_as" not in q]
        if len(qs) < 2 or not rest:
            continue
        ids = [o["question_id"] for o in qs]
        for q in rest:
            q["same_reading_as"] = [i for i in ids[:_CROSS_REFERENCES + 1] if i != q["question_id"]][:_CROSS_REFERENCES]
            q["text"] += (f" {len(qs) - 1} other group(s) hold the same reading ({', '.join(sorted(map(repr, lits)))}) for this "
                          f"field in their own files (same_reading_as names up to {_CROSS_REFERENCES}): if they are the same thing, give each the same answer.")
    # a beamtime value for the field: open at experiment scope, or answered and eligible
    run_of = {m["value_id"]: m["run_id"] for m in bundle["missing_values"]}
    run_of.update({cid: c["run_id"] for cid, c in cand_by_id.items()})
    experiment_q = {q["target_field_path"]: q["question_id"] for q in questions
                    if q["scope"] == "experiment" and q["kind"] in ("confirm_value", "missing_value") and not q.get("informational")
                    and any(t["id"] in run_of and run_of[t["id"]] is None for t in q["targets"])}
    answered_beamtime = {c["target_field_path"] for c in bundle["candidates"]
                         if c["run_id"] is None and (c.get("eligibility_for_official_record") or {}).get("eligible")}
    answered_beamtime |= {m["target_field_path"] for m in bundle["missing_values"]
                          if m["run_id"] is None and (m.get("eligibility_for_official_record") or {}).get("eligible")}
    for q in per_group:
        path = q["target_field_path"]
        if not q["blocking"] or path in RUN_ONLY_PATHS or not (path in experiment_q or path in answered_beamtime):
            continue
        q["blocking"], q["tier"] = False, TIER_OPTIONAL
        q["covered_by"] = experiment_q.get(path) or "an answered beamtime value"
        q["why"] = (f"Not blocking: {path} is required, and a beamtime-wide value fills it for every record, this group's "
                    + (f"included — answer the experiment-wide question {experiment_q[path]}." if path in experiment_q
                       else "included, and one is already answered.")
                    + " Answer here only with the same thing: if this group's answer differs from the beamtime one, the "
                    "record builder fills nothing for this field (two confirmed values that differ fill nothing).")


def _ai_hint_index(bundle: Mapping):
    """``ids -> suggestions.ai_hints(bundle, ids)``, with the AI interpretations indexed by target once:
    each call reads only the interpretations of ``ids`` (in their bundle order, so the output is
    identical), never the whole list again — per question that was quadratic in a large import."""
    interps = list(bundle.get("ai_interpretations") or ())
    at: dict[Any, list[int]] = {}
    for n, i in enumerate(interps):
        at.setdefault((i.get("target") or {}).get("id"), []).append(n)

    def hints(ids: Sequence[str]) -> list[dict]:
        wanted = set(ids)
        rows = sorted(n for tid in wanted for n in at.get(tid, ()))
        return S.ai_hints({"ai_interpretations": [interps[n] for n in rows]}, wanted) if rows else []

    return hints


def _optional_field_hints(bundle: Mapping, fields: Mapping[str, Sequence[str]], ai_hints=None) -> dict[str, list[dict]]:
    """Per optional field: the AI readings of its targets, and the facility hints."""
    ai_hints = ai_hints or _ai_hint_index(bundle)
    out: dict[str, list[dict]] = {}
    for path, ids in sorted(fields.items()):
        hints = ai_hints(ids)
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
        else:
            partial = sum(1 for _, s in items for r in s["ai_readings"] if r.get("read_for"))
            text = (f"Element {element}, edge {edge} is suggested for {len(items)} group(s): "
                    + (f"the files state it for {len(from_files)}; " if from_files else "")
                    + f"for {ai_only}, no file the import parsed states the absorber and only an AI reading of the files suggests it "
                      "(needs your confirmation: an AI reading is not file evidence). "
                      "Is that the absorber? Answer once, or per group (a reference foil or blank cell may differ)."
                    + (f" {partial} AI reading(s) name only some of a group's runs (see the hints)." if partial else ""))
        # NEVER A READY-TO-RUN ANSWER: the command is a template whatever the files state, so an agent
        # cannot record the files' (or an AI's) suggestion on a vague "yes". The suggestion is a hint.
        suggested = {"kind": "suggested_absorber", "literal": f"{element} {edge}", "element": element, "edge": edge,
                     "basis": "stated in the files" if not ai_only else ("stated in the files for some groups, an AI reading for the rest"
                                                                         if from_files else "an AI reading of the files"),
                     "note": ("What this question suggests, never the answer: type it into --element/--edge only once the "
                              "scientist has said it is the absorber.")}
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
            # the file (or AI) evidence first, then the pair it adds up to — both hints, neither an answer
            "hints": _absorber_hints(items) + [suggested],
            "allowed_values": None,
            "answer_command": (f'isaac bundle decide <bundle_dir> --question {qid} --decision set_absorber '
                               '--element <El> --edge <K|L1-L3|M1-M5> --by "<your name>"   # per group: add --only group:<group_id>'),
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
    approve, so none is asked about. Only LIVE groups (:func:`live_groups`): a rejected, split or
    merged group will never be a record, so it blocks nothing."""
    live = {g["group_id"] for g in live_groups(bundle)}
    return {gid: r["applicability"]["reason_code"] for gid, r in B.processing_blocked_groups(bundle).items() if gid in live}


def minimum_answers_for_one_group(payload: Mapping, bundle: Mapping, scope: str | None = None) -> dict | None:
    """The fewest BLOCKING questions that stand between one record group and export —
    experiment-scope blocking questions plus that group's own — plus the decisions that group
    still needs: confirming it (unless a scientist already did) and approving its processing result
    (unless one is approved). A decision already made is never named again.

    A group with NOTHING left here (no blocking question, confirmed, its processing approved) is not
    "the nearest": it is counted in ``groups_with_nothing_left`` and the nearest group that still needs
    something is named. When none does, ``group_id`` is ``None`` and the statement says so.

    ``scope`` ``group:<id>`` (``bundle questions --scope``) names THAT group, never another; any other
    scope (``experiment``, a run) is not one group and leaves the choice open.

    A group the processing protocol does not apply to is never offered as "the nearest"
    while another exists: no approval can make it complete. When only such groups are left,
    the decision named is the blocking reason, never "approve its processing result"."""
    blocked = processing_blocked_groups(bundle)
    approved = {r["group_id"] for r in bundle.get("processing_results") or ()
                if r.get("state") == B.STATE_SCIENTIST_CONFIRMED and not B.processing_not_applicable(r)}
    wanted = scope[len("group:"):] if isinstance(scope, str) and scope.startswith("group:") else None
    best = None
    done: list[str] = []
    # only a LIVE group can become a record: a rejected, split or merged one is never "the nearest"
    for g in live_groups(bundle):
        if wanted is not None and g["group_id"] != wanted:
            continue
        key = f"group:{g['group_id']}"
        need = sum(
            1 for q in payload["questions"]
            if q["blocking"] and (q["scope"] == key or (q["scope"] == "experiment" and (key in q["per_scope_targets"] or "experiment" in q["per_scope_targets"])))
        )
        plus = []
        if g.get("status") != B.STATE_SCIENTIST_CONFIRMED:
            plus.append("confirm the group")
        if g["group_id"] not in blocked and g["group_id"] not in approved:
            plus.append("approve its processing result")
        if not need and not plus and g["group_id"] not in blocked and wanted is None:
            done.append(g["group_id"])
            continue
        rank = (g["group_id"] in blocked, need + len(plus))
        if best is None or rank < best[3]:
            best = (g["group_id"], need, plus, rank)
    if best is None:
        if wanted is not None:
            return None  # the named group is not a live record group
        if not done:
            return None
        return {"group_id": None, "blocking_questions": 0, "plus_decisions": [], "groups_with_nothing_left": len(done),
                "statement": (f"{len(done)} record group(s) have no blocking question and no decision left here (confirmed, "
                              "processing approved): run `isaac bundle build-records`, `validate` and `export`.")}
    out = {"group_id": best[0], "blocking_questions": best[1], "plus_decisions": best[2]}
    if best[0] in blocked:
        out["blocked"] = f"{B.NO_PROTOCOL_COVERS} ({blocked[best[0]]}); this group cannot become a complete record until one does"
    if blocked:
        out["groups_without_an_applicable_processing_protocol"] = len(blocked)
    if done:
        out["groups_with_nothing_left"] = len(done)
    if wanted is not None:
        out["scope"] = scope
    return out
