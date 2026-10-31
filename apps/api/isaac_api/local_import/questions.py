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
  stated in ``blocking_basis``), then conflicts that affect a record, then optional. Once record
  groups exist, "blocking" is what THE RECORD COMPOSER requires (``records.compose_group``, the list
  ``build-records`` and ``validate`` report) for a LIVE group the question reaches
  (:func:`_agree_with_composer`): a conditional field blocks only once the composer requires it, and a
  question about runs no live group holds blocks nothing. A conflict no record field holds is counted
  apart (``conflicts_without_a_record_field``), and a question whose every target was deferred carries
  ``deferred`` and is asked after the others.
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

An ANSWERED question keeps its id too: ``consolidate(include_answered=True)`` puts its answered targets back,
so ``decide --question`` re-answers it (a later decision replaces an earlier one) and ``bundle show question``
shows it with its current answers (:func:`answered_question`). Every kind that drops out of the open list once
answered (:data:`RESOLVABLE_WHEN_ANSWERED`): the value kinds, the absorber question (its answered groups back
in), the counter question (its answered positions back in, even after the regroup that applied them) and the
clock-zone question. A conflict none of whose readings its field
takes (zoneless ``#D`` times for a ``*_utc`` field, readings off a closed list) is answered with ``correct``,
and shows the UTC readings the bundle holds for that run (:func:`_conflict_answer`).
"""

from __future__ import annotations

import functools
import hashlib
import json
import operator
import re
from pathlib import Path
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
    # `defer` records "I don't know": the question stays, marked deferred; grouping is unchanged by it
    "naming_counter_positions": ("set_counter_positions", B.NOT_COUNTER_DECISION, "defer"),
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
#: The question kinds that ask for a record VALUE (the ones the record composer's missing list can concern).
VALUE_KINDS = ("missing_value", "optional_values", "confirm_value", "resolve_conflict")
#: The kinds an ANSWERED question of is still found under its id (``consolidate(include_answered=True)``):
#: ``decide --question`` re-answers it and ``bundle show question`` shows it with ``status`` and its answers.
RESOLVABLE_WHEN_ANSWERED = VALUE_KINDS + ("confirm_absorber", "naming_counter_positions", "clock_time_zone")
#: The grouping step's one counter question id (grouping.counter_question): the consolidated id derives from it.
_COUNTER_GQ_ID = "rgq-experiment-counter-positions"
#: ``records.compose_group``'s ``from`` for a required value only an answer supplies (the others come from an
#: approved processing result).
FROM_AN_ANSWER = "a scientist's answer"
#: When a CONDITIONALLY required field is required: the composer requires it only once the record carries this.
_REQUIRED_WHEN = {
    **{p: "a reaction (context.reaction.name) is in the record: confirmed or answered" for p in B.REACTION_REQUIRED_PATHS},
    "context.electrochemistry.potential_setpoint_V": "the record carries a confirmed potentiostatic control mode",
    "context.electrochemistry.current_setpoint_mA_cm2": "the record carries a confirmed galvanostatic control mode",
}
_OUTSIDE_LIVE_GROUPS = ("Not blocking: every target is in a run no live record group holds (its group was rejected, merged "
                        "or split, or it was never grouped), so no record is built from it.")


def compositions(bundle: Mapping, bundle_dir: Path | None = None, *,
                 decision_of: Mapping[tuple[str, str], Mapping] | None = None) -> dict[str, dict]:
    """``{group_id: composition report}`` for every LIVE record group, whatever its status: THE
    ``records.compose_group`` computation ``build-records`` and ``validate`` use, so "blocking" and the nearest
    group are judged by what the composer actually requires, never by a second reading of the schema.

    Without ``bundle_dir`` no processing file is read: the composer then sees no processing result, so its
    processing-derived entries (series, QC status, outputs) are not meaningful and callers use only the
    entries ``from`` :data:`FROM_AN_ANSWER`. ``decision_of``: :func:`bundle._decisions_by_target` of this bundle, when
    the caller already built it."""
    from . import records as R

    view = bundle if bundle_dir is not None else {**bundle, "processing_results": []}
    where = Path(bundle_dir) if bundle_dir is not None else Path(".")  # never read without a processing result
    # THE SAME INPUT, smaller: compose_group reads only its members' and the beamtime-wide (run_id null) candidates
    # and missing values — every other one it skips — so each group is composed from exactly those (in bundle
    # order), with everything else (decisions, conflicts, processing) whole. Per group that is linear in the
    # group, not in the whole import.
    run_key_to_id = {r["run_key"]: r["run_id"] for r in bundle["runs"]}
    by_run: dict[Any, dict[str, list]] = {}
    for kind in ("candidates", "missing_values"):
        for n, obj in enumerate(bundle[kind]):
            by_run.setdefault(obj.get("run_id"), {"candidates": [], "missing_values": []})[kind].append((n, obj))
    # THE WHOLE-BUNDLE READS (decision log, conflicts, processing) once for every group, never once per group
    index = R.composition_index(view, decision_of=decision_of)
    out = {}
    for g in live_groups(bundle):
        runs = [None] + [run_key_to_id[k] for k in g.get("member_run_keys") or () if k in run_key_to_id]
        part = {}
        for kind in ("candidates", "missing_values"):
            rows = [x for r in dict.fromkeys(runs) for x in (by_run.get(r) or {}).get(kind, ())]
            rows.sort(key=_first)  # bundle order: each run's rows already are, so this merges them
            part[kind] = [o for _, o in rows]
        out[g["group_id"]] = R.compose_group({**view, **part}, g, where, index)[1]
    return out


_first = operator.itemgetter(0)


def _answer_missing(report: Mapping) -> list[str]:
    return [m["path"] for m in report.get("missing_required") or () if m.get("from") == FROM_AN_ANSWER]


@functools.lru_cache(maxsize=4096)
def _composer_path(path: str) -> str:
    """The path the record composer writes an answer at ``path`` to (records.FIELD_REMAP, REQUIRED_AS_FIELD)."""
    from .records import FIELD_REMAP

    return REQUIRED_AS_FIELD.get(path, FIELD_REMAP.get(path, path))


def _fills(question_path: str | None, missing: str) -> bool:
    """Whether an answer at ``question_path`` fills the composer's missing ``missing`` path."""
    if not question_path:
        return False
    p = _composer_path(question_path)
    return p == missing or p.startswith(missing + ".")


def _required_when(path: str | None) -> str | None:
    """When a CONDITIONALLY required field is required (:data:`_REQUIRED_WHEN`, or a member an optional object
    requires once the record carries it: ``records.required_members_with``), or ``None``."""
    if not path:
        return None
    if path in _REQUIRED_WHEN:
        return _REQUIRED_WHEN[path]
    from .records import required_members_with

    leaf = path.rsplit(".", 1)[-1]
    for obj, members in required_members_with(path):
        if path == f"{obj}.{leaf}" and leaf in members and len(members) > 1:
            return (f"the record carries another member of {obj} (the schema requires {' and '.join(members)} "
                    "together)")
    return None


def scoped_answer_command(q: Mapping, field: str, group_id: str | None = None) -> str:
    """The ``decide --question`` command that answers ``field`` of question ``q`` — for ``group_id`` alone when the
    question reaches other groups too. A template: a placeholder for the value, never one read from the files."""
    pst = q.get("per_scope_targets") or {}
    only = f"group:{group_id}" if group_id and f"group:{group_id}" in pst and len(pst) > 1 else None
    if q["kind"] == "confirm_value" and "confirm" in (q.get("allowed_decisions") or ALLOWED_DECISIONS[q["kind"]]):
        decision = "--decision confirm"
    else:
        decision = ("--decision correct --value " + ("<one of its allowed values>" if _eligible_values(field) else "<value>")
                    + (" --json" if _is_numeric(B._schema_node(field)) else ""))
    return (f"isaac bundle decide <bundle_dir> --question {q['question_id']}"
            + (f" --field {field}" if q["kind"] == "optional_values" else "") + (f" --only {only}" if only else "")
            + f' {decision} --by "<your name>"')


def command_for_targets(payload: Mapping, target_ids: Sequence[str], path: str, group_id: str | None = None) -> str | None:
    """:func:`scoped_answer_command` for the open question that asks ``path`` of any of ``target_ids``, or ``None``."""
    wanted = set(target_ids)
    if not wanted:
        return None
    for q in payload["questions"]:
        if q["kind"] not in VALUE_KINDS or q.get("informational"):
            continue
        for field, ids in _value_paths(q):
            if field == path and wanted.intersection(ids):
                return scoped_answer_command(q, field, group_id)
    return None


def _value_paths(q: Mapping) -> list[tuple[str, list[str]]]:
    """``[(field path, target ids)]`` a value question asks about (an optional-values question: per field)."""
    if q["kind"] == "optional_values":
        return [(f, list(ids)) for f, ids in (q.get("fields") or {}).items()]
    return [(q["target_field_path"], [t["id"] for t in q["targets"]])] if q.get("target_field_path") else []


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


def consolidate(bundle: Mapping, *, compositions_out: dict | None = None, include_answered: bool = False) -> dict:
    """``questions.json`` v2 for ``bundle``. Pure: reads the bundle, writes nothing.

    ``compositions_out``, when given, receives the composer's report per live group that "blocking" was judged
    by (:func:`compositions`, no processing file read), for :func:`minimum_answers_for_one_group` to reuse on
    this same, unchanged bundle instead of composing every group again.

    ``include_answered`` puts the targets a scientist ANSWERED back into the questions that asked them (a value
    question the import asked: a missing value, a needs-review or blocking extracted candidate, a conflict), and
    keeps an answered absorber, counter or clock-zone question (:data:`RESOLVABLE_WHEN_ANSWERED`). The
    buckets, and so the ids, are the same ones (DEC-91: a question's scope and partition never depend on an
    answer), so an answered question is found under the id it was asked with: what ``decide --question`` resolves
    when the question is no longer open, and what ``bundle show question`` shows (:func:`answered_question`)."""
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
    # GROUPED: the record composer decides what blocks (a run no live group holds becomes no record)
    has_groups = bool(bundle.get("record_groups"))

    def outside(runs) -> int:
        return sum(1 for r in runs if r not in group_of) if has_groups else 0
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
            if again is None and not (include_answered and m.get("extracted_state", B.STATE_MISSING) in _UNANSWERED
                                      and ("missing_value", m["value_id"]) in decisions):
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
        state = c["value_state"]
        if state not in (B.STATE_NEEDS_REVIEW, B.STATE_CANDIDATE_EXTRACTED):
            again = not_eligible_answer(c, "candidate")
            if again is None:
                # ANSWERED (include_answered): asked as it was extracted, before the answer
                state = c.get("extracted_state")
                if not (include_answered and state in (B.STATE_NEEDS_REVIEW, B.STATE_CANDIDATE_EXTRACTED)
                        and B.candidate_decision(bundle, c, decisions) is not None):
                    continue
        if not zone_decided and B.is_local_clock_start(c):
            continue  # nothing to confirm until the clock's zone is stated: the zone question asks that
        blocking = required_for(path, c["run_id"])
        if again is None and state == B.STATE_CANDIDATE_EXTRACTED and not blocking:
            continue  # an extracted optional value is not asked about (one a scientist answered unfitly is)
        scope = scope_of_run(c["run_id"])
        add((scope, "confirm_value", path, None), kind="confirm_value", path=path, partition=None,
            target={"kind": "candidate", "id": c["candidate_id"]}, run_id=c["run_id"], scope=scope, blocking=blocking,
            again=again)

    conflicts_out = []
    for cf in bundle["conflicts"]:
        if (cf["value_state"] not in (B.STATE_CONFLICTING, B.STATE_NEEDS_REVIEW) and cf["conflict_id"] not in conflict_again
                and not (include_answered and ("conflict", cf["conflict_id"]) in decisions)):
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
                             + (_field_hints_text(fh) if (fh := _optional_field_hints(bundle, q["fields"], ai_hints)) else "")
                             + _asked_again_text(q["asked_again"], {f: _eligible_values(f) for f in q["fields"]})),
                    "asked_again": q["asked_again"],
                    "applies_to": {"groups": len({group_of[r] for r in q["runs"] if r in group_of}), "runs": len(q["runs"]), "targets": len(q["targets"]),
                                   "runs_outside_live_groups": outside(q["runs"])},
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
                if outside(q["runs"]):
                    text += (f" {outside(q['runs'])} of its {len(q['runs'])} run(s) are in no live record group (rejected, "
                             "merged or split, or never grouped): no record is built from them.")
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
            # AN AI READING IS NOT FILE EVIDENCE: no parser read this value, so it is never worded as one the files state
            text += (f" An AI reading of the files suggests {top['literal']!r}"
                     + (f", {top['read_for']}" if top.get("read_for") else "")
                     + " (not file evidence: it needs your "
                     f"confirmation), citing {cite}{' @ ' + str(top['locator']) if top.get('locator') else ''}"
                     + (f"; {len(ai) - 1} other AI suggestion(s) differ" if len(ai) > 1 else "") + ".")
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
            "applies_to": {"groups": n_groups, "runs": len(q["runs"]), "targets": len(q["targets"]),
                           "runs_outside_live_groups": outside(q["runs"])},
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
        # A DISAGREEMENT NO RECORD FIELD HOLDS (a comment line, a unit spelling, a file-name declaration) cannot
        # change a record, whichever reading is chosen: it is counted apart, never as affecting a record.
        no_field = (None if required else "something no record field holds (e.g. a comment line or a unit spelling)" if not path
                    else (f"{path}, which no record field takes an answer for ({lands})" if (lands := _never_lands(path, writable)) else None))
        reaches = bool(required) or (bool(affects) and no_field is None)
        qid = _qid(scope, "resolve_conflict", cf["conflict_id"])
        answer = _conflict_answer(qid, cf, path, enum, writable, related, source_path_of, _is_numeric(_node(schema, path)) if path else False)
        n_groups = len({group_of[r] for r in cf["run_ids"] if r in group_of})
        applies = {"groups": n_groups, "runs": len(cf["run_ids"]), "targets": 1}
        if not cf["run_ids"] and reaches and has_groups:
            # A BEAMTIME-WIDE disagreement (no run named) fills every record built: it reaches every live group, as
            # the composer counts it (blocks_groups), never "0 groups"
            applies = {"groups": len(groups), "runs": len(group_of), "targets": 1, "beamtime_wide": True}
        questions.append(
            {
                **({"asked_again": again, "reason": "answer_not_eligible_for_official_record"} if again else {}),
                "question_id": qid,
                "partition": None,
                "tier": TIER_BLOCKING if required else (TIER_CONFLICT if reaches else TIER_OPTIONAL),
                "blocking": bool(required),
                "affects_record": reaches,
                **({"no_record_field": no_field} if no_field else {}),
                "why": (f"The record cannot be exported until this is settled: the target schema requires {required}."
                        if required else
                        f"The sources disagree about {no_field}: settling it records which reading is right, as "
                        "evidence, and changes no record." if no_field else
                        "The sources disagree; a record built from these runs carries whichever reading you choose."
                        if affects else "The sources disagree about something outside any record group."),
                "kind": "resolve_conflict",
                "scope": scope,
                "target_field_path": path,
                "text": (f"The sources disagree ({cf['kind']}{', ' + str(cf['subject']) if cf['subject'] else ''}). "
                         + answer["text"] + _asked_again_text(again, {path: enum} if path else {})),
                "applies_to": applies,
                "targets": [{"kind": "conflict", "id": cf["conflict_id"]}],
                "per_scope_targets": {scope: [cf["conflict_id"]]},
                "hints": answer["hints"],
                "allowed_values": enum,
                **answer["fields"],
                "answer_command": answer["command"],
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
    counter_gqs = [gq for gq in bundle.get("grouping_questions") or ()
                   if isinstance(gq, Mapping) and gq.get("kind") == "naming_counter_positions"]
    if include_answered and not counter_gqs and (said_counter or said_not):
        # ANSWERED, AND APPLIED: the regroup that applied a counter answer no longer asks the question (no merge is
        # blocked by those positions now), but its id is the one it was asked with, so it is still found
        counter_gqs = [{"id": _COUNTER_GQ_ID, "kind": "naming_counter_positions",
                        "positions": sorted(p for p in said_counter | set(said_not) if p > 0),
                        "text": "Which filename token positions are run or acquisition counters? (Answered, and the "
                                "regroup applied it: the grouping step no longer asks it.)"}]
    for gq in counter_gqs:
        asked_positions = [int(p) for p in gq.get("positions") or () if isinstance(p, int)]
        open_positions = [p for p in asked_positions if p not in said_counter and p not in said_not]
        if asked_positions and not open_positions and not include_answered:
            continue  # every position it asks about is answered: it drops out of the open list
        qid = _qid("experiment", "naming_counter_positions", str(gq.get("id") or gq.get("text") or ""))
        text = str(gq.get("text") or "Which filename token positions are run or acquisition counters?")
        # REAL NAMES, NOT A PATTERN: the file names this bundle holds, the asked token marked
        examples = _counter_examples(bundle, open_positions or asked_positions)
        if examples and _COUNTER_PLACEHOLDER in text:
            text = text.replace(_COUNTER_PLACEHOLDER, "(e.g. " + "; ".join(
                f"the {_ordinal(p)} token: " + " vs ".join(ex["differ"])
                + (f", while it is not a number in {ex['elsewhere']}" if ex["elsewhere"] else "")
                for p, ex in examples.items()) + ")")
        example_names = {str(p): ex["differ"] + ([ex["elsewhere"]] if ex["elsewhere"] else []) for p, ex in examples.items()}
        if asked_positions and not open_positions:
            text += " Already answered: every position it asks about (" + ", ".join(map(str, asked_positions)) + ")."
        elif len(open_positions) < len(asked_positions):
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
                # answered (include_answered): the positions a no-counter answer names again, never one said to be a counter
                "positions": open_positions or [p for p in asked_positions if p not in said_counter] or asked_positions,
                **({"example_names": example_names} if example_names else {}),
                "applies_to": {"groups": len(groups), "runs": len(bundle["runs"]), "targets": 1},
                "targets": [{"kind": "experiment", "id": "experiment"}],
                "per_scope_targets": {"experiment": ["experiment"]},
                "hints": [{"kind": "grouping", "literal": ([n for names in example_names.values() for n in names] if example_names
                                                           else gq.get("examples") or gq.get("options")),
                           "locator": "file names in this bundle, the asked token in [brackets]" if example_names else "the grouping step"}],
                "allowed_values": None,
                "answered": answered_positions,
                **({"deferred": deferred} if (deferred := counter_deferral(bundle)) else {}),
                "answer_command": (
                    'isaac bundle decide <bundle_dir> --target experiment --decision set_counter_positions '
                    '--positions <n[,m] or last> --by "<your name>"  &&  isaac bundle group <bundle_dir> --regroup'
                    f'   # none is a counter: isaac bundle decide <bundle_dir> --question {qid} --decision {B.NOT_COUNTER_DECISION} --by "<your name>"'
                    f'   # not known: isaac bundle decide <bundle_dir> --question {qid} --decision defer --by "<your name>"'
                ),
            }
        )

    # THE INSTRUMENT CLOCK'S TIME ZONE (1.4.0): asked once for the beamtime while local-clock start
    # times wait on it. No value is suggested: no file states one (CLAUDE.md §5).
    zq = B.clock_zone_question(bundle)
    if zq is None and include_answered and B.clock_zone_decision(bundle) is not None:
        # ANSWERED: the question as it was asked, before any zone was stated (the same text, so the same id)
        zq = B.clock_zone_question({**bundle, "scientist_decisions": [
            d for d in bundle.get("scientist_decisions") or () if d.get("decision") != B.CLOCK_ZONE_DECISION]})
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

    questions += _absorber_questions(bundle, groups, include_answered=include_answered)

    def order(q):
        scope = q["scope"]
        if scope == "experiment":
            s = (0, 0)
        elif scope.startswith("group:"):
            s = (1, group_order.get(scope[6:], 10**9))
        else:
            s = (2, run_order.get(scope[4:], 10**9))
        # an informational question (nothing to answer) sorts after every question that has an answer; a
        # DEFERRED one ("I don't know") after every one not deferred in its tier, so it is not asked again first
        return (q["tier"], bool(q.get("informational")), bool(q.get("deferred")), s, q["target_field_path"] or "", q["question_id"])

    if has_groups:
        reports = compositions(bundle, decision_of=decisions)
        if compositions_out is not None:
            compositions_out.update(reports)
        basis = {**basis, "record_composer": _agree_with_composer(questions, bundle, group_of, cand_by_id, reports)}
    _note_shared_evidence(questions, cand_by_id, bundle)
    _mark_deferred(questions, decisions)
    _say_the_one_group(questions)
    questions.sort(key=order)
    for q in questions:
        q.setdefault("allowed_decisions", list(ALLOWED_DECISIONS.get(q["kind"], ())))
    return {
        "format": FORMAT_ID,
        "format_version": FORMAT_VERSION,
        "bundle_id": bundle.get("bundle_id"),
        "blocking_basis": basis,
        "counts": question_counts(questions, fine_grained_v1=len(bundle.get("questions") or ())),
        "questions": questions,
    }


def question_counts(questions: Sequence[Mapping], *, fine_grained_v1: int | None = None) -> dict:
    """The counts of a list of consolidated questions (the whole bundle's, or one scope's). The tier-3 ones are
    split so none is counted twice: informational > a conflict no record field holds > outside every live group
    > optional. ``deferred`` overlaps the others: a deferred question is still counted where it is."""
    rest = [q for q in questions if q["tier"] == TIER_OPTIONAL and not q.get("informational")]
    fieldless = [q for q in rest if q["kind"] == "resolve_conflict" and q.get("no_record_field")]
    outside = [q for q in rest if q.get("outside_live_groups") and not q.get("no_record_field")]
    out = {
        "total": len(questions),
        "blocking": sum(q["tier"] == TIER_BLOCKING for q in questions),
        "conflicts_affecting_a_record": sum(q["tier"] == TIER_CONFLICT for q in questions),
        "optional": len(rest) - len(fieldless) - len(outside),
        # questions kept under their ids that no answer can reach the record from (an array path,
        # or a path this build has no write route for): listed, never answerable
        "informational": sum(bool(q.get("informational")) for q in questions),
        # disagreements about something no record field holds: settling one changes no record
        "conflicts_without_a_record_field": len(fieldless),
        # every target is in a run no live record group holds: no record is built from it
        "outside_live_groups": len(outside),
        # every target's latest decision is `defer` ("I don't know"): still asked, and still counted above
        "deferred": sum(bool(q.get("deferred")) for q in questions),
        # targets a scientist answered with a value the record cannot take, asked again
        "asked_again": sum(len(q.get("asked_again") or ()) for q in questions),
    }
    if fine_grained_v1 is not None:
        out["fine_grained_v1"] = fine_grained_v1
    return out


def scope_counts(payload: Mapping, scope: str | None) -> dict:
    """:func:`question_counts` for the questions ``scope`` selects, where ``blocking`` means blocking THERE: in a
    group's scope, a question the composer says blocks only other groups counts as optional (exactly what
    ``filter_questions(..., blocking_only=True)`` leaves out)."""
    rows = filter_questions(payload, scope=scope)
    if scope and scope.startswith("group:"):
        gid = scope[len("group:"):]
        rows = [{**q, "blocking": False, "tier": TIER_OPTIONAL}
                if q["blocking"] and "blocks_group_ids" in q and gid not in q["blocks_group_ids"] else q for q in rows]
    return {**question_counts(rows), **({"scope": scope} if scope else {})}


def _agree_with_composer(questions: list[dict], bundle: Mapping, group_of: Mapping[str, str],
                         cand_by_id: Mapping[str, Mapping], reports: Mapping[str, Mapping]) -> dict:
    """BLOCKING IS WHAT THE RECORD COMPOSER REQUIRES (records.compose_group, the list ``build-records`` and
    ``validate`` report): a value question blocks exactly when, for at least one LIVE record group it reaches,
    the composer lists one of its fields as missing and only an answer can supply it. So a conditionally
    required field (a reaction's drive and catalysis, a control mode's set-point) blocks only once the composer
    requires it, and a question whose targets are all in runs no live group holds (rejected, merged, split, or
    never grouped) blocks nothing. Ids, scopes and targets are untouched (DEC-91): only ``blocking``, ``tier``
    and ``why`` change, and what was decided is stated in ``blocks_groups`` / ``required_fields``."""
    from .records import RUN_ONLY_PATHS

    missing = {gid: set(_answer_missing(rep)) for gid, rep in reports.items()}
    because_of = {gid: {m["path"]: m["required_because"] for m in rep.get("missing_required") or () if m.get("required_because")}
                  for gid, rep in reports.items()}
    filled = {gid: {f["path"] for f in rep.get("filled") or ()} for gid, rep in reports.items()}
    every = set(missing)
    order_of = {gid: i for i, gid in enumerate(missing)}
    run_of = {m["value_id"]: m["run_id"] for m in bundle["missing_values"]}
    conflict_runs = {cf["conflict_id"]: list(cf.get("run_ids") or ()) for cf in bundle["conflicts"]}

    def reached(kind: str, tid: str, path: str) -> set[str]:
        if kind == "conflict":
            rids = conflict_runs.get(tid) or []
            return every if not rids else {group_of[r] for r in rids if r in group_of}
        if kind == "candidate":
            rid = (cand_by_id.get(tid) or {}).get("run_id")
            if rid is None and path in RUN_ONLY_PATHS:
                return set()  # DEC-69: a beamtime fact never fills this run-level field
        elif kind == "missing_value":
            rid = run_of.get(tid)
        else:
            return set()
        if rid is None:
            return every
        return {group_of[rid]} if rid in group_of else set()

    needed_by: dict[str, set[str]] = {}

    def needs(path: str) -> set[str]:
        """The live groups the composer lists a field as missing for that an answer at ``path`` fills (once per path)."""
        if path not in needed_by:
            needed_by[path] = {g for g, ms in missing.items() if any(_fills(path, m) for m in ms)}
        return needed_by[path]

    changed = 0
    for q in questions:
        if q["kind"] not in VALUE_KINDS or q.get("informational") or q.get("no_record_field"):
            continue
        kinds = {t["id"]: t["kind"] for t in q["targets"]}
        groups_reached: set[str] = set()
        needing: set[str] = set()
        fields: set[str] = set()
        for path, ids in _value_paths(q):
            for tid in ids:
                gs = reached(kinds.get(tid, ""), tid, path)
                groups_reached |= gs
                hit = gs & needs(path)
                if hit:
                    needing |= hit
                    fields.add(path)
        if not groups_reached:
            q["outside_live_groups"] = True
        if needing:
            # which groups it blocks (`--scope group:<id> --blocking-only` lists it only for those)
            q["blocks_groups"], q["blocks_group_ids"] = len(needing), sorted(needing, key=lambda g: order_of.get(g, 0))
        if q["blocking"] and not needing:
            changed += 1
            q["blocking"] = False
            q["tier"] = TIER_CONFLICT if q["kind"] == "resolve_conflict" and groups_reached else TIER_OPTIONAL
            path = q["target_field_path"] or ""
            if not groups_reached:
                q["why"] = _OUTSIDE_LIVE_GROUPS
            elif (when := _required_when(path)):
                q["required_when"] = when
                q["why"] = (f"Not blocking now: a record requires {path} only once {when}, and no record "
                            "group this question reaches has that yet (what `build-records` and `validate` check). "
                            "Answer it if you know it; it blocks once that is so.")
            elif all(any(_fills(path, f) or _fills(f, _composer_path(path)) for f in filled[g]) for g in groups_reached):
                q["why"] = (f"Not blocking: every record group this question reaches already has {path} in the record "
                            "composed for it now (from another answer, e.g. a beamtime-wide one, or a source). Answer here "
                            "only with the same thing: two confirmed values that differ fill nothing.")
            else:
                q["why"] = (f"Not blocking: the record composer (what `build-records` and `validate` check) does not "
                            f"require {path} for any record group this question reaches.")
        elif not q["blocking"] and needing:
            changed += 1
            q["blocking"], q["tier"] = True, TIER_BLOCKING
            q["required_fields"] = sorted(fields)
            because = next((b for g in sorted(needing) for f in sorted(fields) if (b := because_of.get(g, {}).get(f))), None)
            q["why"] = (f"The record cannot be exported without it: the record composer (what `build-records` and "
                        f"`validate` check) lists {', '.join(sorted(fields))} as missing for {len(needing)} record "
                        "group(s) this question reaches, and only an answer supplies it"
                        + (f" ({because})" if because else "") + ".")
            if because:
                q["required_because"] = because
    return {"basis": "records.compose_group: the missing-required list build-records and validate report",
            "live_groups": len(every), "blocking_changed_to_agree": changed}


#: The experiment decisions that answer (or defer) the counter question, latest first wins.
COUNTER_QUESTION_DECISIONS = ("set_counter_positions", B.NOT_COUNTER_DECISION, "defer")
#: The pattern the grouping step's counter question shows (grouping.counter_question), replaced by real names.
_COUNTER_PLACEHOLDER = "(e.g. XX_02_… vs XX_03_…)"


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _marked_token(stem: str, position: int) -> str | None:
    """``stem`` with its ``position``-th token (1-based, split as grouping splits names: a sign on a number stays
    on it) in [brackets], every separator kept; ``None`` when the name has fewer tokens."""
    from .grouping import _SIGN

    marked = _SIGN.sub("\x00", str(stem))  # same length: the spans hold for the name itself
    spans = [m.span() for m in re.finditer(r"[^_\-\s.]+", marked)]
    if not 1 <= position <= len(spans):
        return None
    a, b = spans[position - 1]
    return f"{stem[:a]}[{stem[a:b]}]{stem[b:]}"


def _counter_examples(bundle: Mapping, positions: Sequence[int]) -> dict[int, dict]:
    """For each asked position: ``differ`` — the names (at most 2) of one merge candidate whose names differ there in
    a number (what the question is asked for), the token marked — and ``elsewhere``, one name of the bundle where
    that token is not a number (or ``None``). Real names of this bundle, never a pattern."""
    from .grouping import _stem_tokens

    runs_by_key = {r["run_key"]: r for r in bundle.get("runs") or ()}
    groups = {g["group_id"]: g for g in bundle.get("record_groups") or ()}
    out: dict[int, dict] = {}
    for mc in bundle.get("merge_candidates") or ():
        if not any(r.get("code") == "numeric_name_token_differs" for r in mc.get("reasons") or ()):
            continue
        stems = []
        for gid in mc.get("group_ids") or ():
            keys = (groups.get(gid) or {}).get("member_run_keys") or ()
            stem = (runs_by_key.get(keys[0]) or {}).get("stem") if keys else None
            if stem and stem not in stems:
                stems.append(stem)
        toks = [_stem_tokens(s) for s in stems]
        for p in positions:
            col = [t[p - 1] for t in toks if 1 <= p <= len(t)]
            if p not in out and len(stems) >= 2 and len(col) == len(toks) and len(set(col)) > 1 and all(c.isdigit() for c in col):
                out[p] = {"differ": [_marked_token(s, p) for s in stems[:2]], "elsewhere": None}
    for p, ex in out.items():
        other = next((r["stem"] for r in bundle.get("runs") or () if r.get("stem") and len(t := _stem_tokens(r["stem"])) >= p
                      and not t[p - 1].isdigit()), None)
        ex["elsewhere"] = _marked_token(other, p) if other else None
    return {p: out[p] for p in positions if p in out}


def counter_deferral(bundle: Mapping) -> dict | None:
    """``{by, decided_utc, decision_id}`` when the LATEST answer to the counter question is ``defer`` ("I don't
    know"), else ``None``. A later set_counter_positions / set_not_counter_positions answer supersedes it. A
    defer moves no position and no group (grouping reads only the two position decisions)."""
    last = None
    for d in bundle.get("scientist_decisions") or ():
        if (isinstance(d, Mapping) and d.get("target") == {"kind": "experiment", "id": "experiment"}
                and d.get("decision") in COUNTER_QUESTION_DECISIONS):
            last = d
    if last is None or last.get("decision") != "defer":
        return None
    return {"by": (last.get("decided_by") or {}).get("name"), "decided_utc": last.get("decided_utc"),
            "decision_id": last.get("decision_id")}


def _mark_deferred(questions: list[dict], decisions: Mapping[tuple[str, str], Mapping]) -> None:
    """"I DON'T KNOW" IS VISIBLE: a value question whose every target's latest decision is ``defer`` carries
    ``deferred`` (who, when) — still asked, still counted, sorted after the questions not deferred."""
    for q in questions:
        if q["kind"] not in VALUE_KINDS or not q["targets"]:
            continue
        ds = [decisions.get((t["kind"], t["id"])) for t in q["targets"]]
        if all(d is not None and d.get("decision") == "defer" for d in ds):
            last = max(ds, key=lambda d: (str(d.get("decided_utc") or ""), str(d.get("decision_id") or "")))
            q["deferred"] = {"by": (last.get("decided_by") or {}).get("name"), "decided_utc": last.get("decided_utc"),
                             "decision_id": last.get("decision_id"), "targets": len(ds)}


def _say_the_one_group(questions: list[dict]) -> None:
    """A question built at experiment scope whose every target is in ONE record group says that group.

    A sample field asked per sample reading (partition ``sample=<reading>``) is built at experiment scope, and
    when only one group holds that reading the question was labelled ``scope: experiment`` while applying to one
    group (BL6-2c: 69 ``sample.material.name`` and 69 ``sample.sample_form`` questions). The displayed ``scope``
    is now ``group:<id>``. THE ID IS UNCHANGED (DEC-91): ``_qid`` hashes the scope string the question was built
    at, which stays ``experiment`` and is kept as ``id_scope``; only the label moves."""
    for q in questions:
        pst = q.get("per_scope_targets") or {}
        if q["scope"] == "experiment" and len(pst) == 1:
            (only,) = pst
            if only.startswith("group:"):
                q["id_scope"] = q["scope"]
                q["scope"] = only


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


def _first_witness(reading: Mapping) -> Mapping:
    return (reading.get("witnesses") or [{}])[0] or {}


def _conflict_answer(qid: str, cf: Mapping, path: str | None, enum: list | None, writable: frozenset[str],
                     related: Mapping[str, Sequence[Mapping]], source_path_of: Mapping[str, Any], numeric: bool) -> dict:
    """What a conflict question asks, the hints it shows and the answer it offers: ``{"text", "hints", "fields",
    "command"}``.

    WHICH READINGS THE FIELD TAKES. ``decide`` refuses a reading its field refuses (``bundle.value_problem``: a
    ``*_utc`` field takes only a zoned instant, a closed field only its allowed values), so a conflict none of
    whose readings fits — ``#D`` local clock times with no zone, a macro name or a Python helper line read as a
    technique — cannot be answered with ``confirm --value <one reading>``. It says so, and offers ``correct``. For a
    ``*_utc`` field it shows the UTC instants the bundle ALREADY holds for the same run(s) (another statement in
    the files, e.g. a ``#E`` epoch line), each with its source: hints, never the answer — the command stays a
    template. A path this build does not write is not checked (``decide`` does not check it either). Neither the
    question's id nor its targets change (DEC-91)."""
    hints = []
    for r in cf["readings"][:_HINTS_PER_QUESTION]:
        w = _first_witness(r)
        hints.append({"kind": "reading", "literal": r["value"], "locator": w.get("locator"), "source_id": w.get("source_id"),
                      **({"relative_path": w["relative_path"]} if w.get("relative_path") else {})})
    default = {"text": "Which reading is right?", "hints": hints, "fields": {},
               "command": f'isaac bundle decide <bundle_dir> --question {qid} --decision confirm --value <one reading> --by "<your name>"'}
    if not path or path not in writable or not cf["readings"]:
        return default
    problems = [B.value_problem(path, r["value"]) for r in cf["readings"]]
    fit = sum(p is None for p in problems)
    for h, p in zip(hints, problems):
        h["fits_field"] = p is None
    fields: dict[str, Any] = {"readings_that_fit_the_field": fit}
    is_utc = path.endswith("_utc")
    utc: list[dict] = []
    if is_utc:
        runs = set(cf.get("run_ids") or ())
        for c in related.get(path, ()):
            if (c["candidate_id"] == cf.get("candidate_id") or c.get("value") is None
                    or (c.get("run_id") not in runs if runs else c.get("run_id") is not None)
                    or B.value_problem(path, c["value"]) is not None):
                continue
            ev = next((e for e in c.get("evidence") or () if e.get("method") != "ai_interpretation"), None) or {}
            rule = next((n.get("rule_id") for n in ev.get("normalization") or () if n.get("rule_id")), None)
            utc.append({"candidate_id": c["candidate_id"], "value": c["value"], "run_id": c.get("run_id"),
                        "observed_literal": (c.get("observed_literals") or [None])[0], "locator": ev.get("locator"),
                        "source_id": ev.get("source_id"),
                        "relative_path": ev.get("relative_path") or source_path_of.get(ev.get("source_id")),
                        "rule_id": rule, "value_state": c.get("value_state")})
        fields["utc_readings"] = utc
        hints += [{"kind": "utc_reading", "literal": u["value"], "candidate_id": u["candidate_id"], "locator": u["locator"],
                   "source_id": u["source_id"], "relative_path": u["relative_path"], "observed_literal": u["observed_literal"],
                   "note": ("A UTC instant this bundle already holds for the same run, from another statement in the files. "
                            "A hint: record it only once the scientist says it is the start.")} for u in utc]
    if fit == len(problems):
        return {**default, "hints": hints, "fields": fields}
    where = ", ".join(dict.fromkeys(str(_first_witness(r).get("locator")) for r in cf["readings"][:3]))
    if fit:
        bad = len(problems) - fit
        text = (f"{bad} of the {len(problems)} readings cannot be recorded as they stand ("
                + next(p for p in problems if p is not None).rstrip(".")
                + "): confirm only one that the field takes, or give the right value yourself (correct).")
        return {**default, "text": default["text"] + " " + text, "hints": hints, "fields": fields}
    if is_utc:
        text = (f"These readings are local clock times with no time zone (read at {where}), so they cannot be recorded: "
                f"{path} takes only a UTC instant, and `confirm --value <one reading>` is refused.")
        if utc:
            text += (f" The bundle already holds {len(utc)} UTC reading(s) for this run (utc_readings): "
                     + "; ".join(f"{u['value']} ({u['candidate_id']}, from {u['observed_literal']!r} at "
                                 f"{u['relative_path'] or u['source_id']} @ {u['locator']}"
                                 + (f", rule {u['rule_id']}" if u["rule_id"] else "") + ")" for u in utc[:3])
                     + ". If that is the start, answer with it (correct); otherwise give the UTC start yourself.")
        else:
            text += " No UTC reading of this start is held in the bundle: give the UTC start yourself (correct)."
        comment = ("   # the UTC reading(s) this bundle holds (utc_readings): "
                   + ", ".join(f"{u['value']} ({u['candidate_id']})" for u in utc[:3]) if utc else
                   "   # the local readings name no zone and are refused")
        placeholder = "<UTC instant, YYYY-MM-DDTHH:MM:SSZ>"
    elif enum:
        shown = ", ".join(map(str, enum[:8])) + (f", … ({len(enum)} in all)" if len(enum) > 8 else "")
        text = (f"None of these readings is a value {path} takes (allowed_values: {shown}), so none can be confirmed as "
                "it stands: answer with the allowed value that is right (correct), or reject or defer it.")
        comment = "   # one of allowed_values"
        placeholder = "<allowed value>"
    else:
        text = (f"None of these readings fits {path} (" + next(p for p in problems if p is not None).rstrip(".")
                + "): answer with the value that is right (correct), or reject or defer it.")
        comment = "   # a number: add --json" if numeric else ""
        placeholder = "<value>"
    return {"text": text, "hints": hints, "fields": fields,
            "command": (f"isaac bundle decide <bundle_dir> --question {qid} --decision correct --value {placeholder}"
                        + (" --json" if numeric and not is_utc else "") + f' --by "<your name>"{comment}')}


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
    run_of = {**{c["candidate_id"]: c.get("run_id") for c in bundle.get("candidates") or ()},
              **{m["value_id"]: m.get("run_id") for m in bundle.get("missing_values") or ()}}

    def hints(ids: Sequence[str]) -> list[dict]:
        wanted = set(ids)
        rows = sorted(n for tid in wanted for n in at.get(tid, ()))
        out = S.ai_hints({"ai_interpretations": [interps[n] for n in rows]}, wanted) if rows else []
        for h in out:
            # A READING OF FEWER RUNS THAN THE QUESTION ASKS ABOUT says so: "applies to 82 groups" beside an AI
            # suggestion read from one file must never read as a beamtime-wide reading
            covered = {(interps[n].get("target") or {}).get("id") for n in rows
                       if repr(interps[n].get("proposed_value")) == repr(h["literal"])}
            runs_all = {run_of.get(t) for t in wanted}
            if None not in runs_all and len({run_of.get(t) for t in covered}) < len(runs_all):
                h["read_for"] = f"read for {len({run_of.get(t) for t in covered})} of {len(runs_all)} runs"
            elif len(covered) < len(wanted):
                h["read_for"] = f"read for {len(covered)} of {len(wanted)} targets"
        return out

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


def _field_hints_text(field_hints: Mapping[str, Sequence[Mapping]]) -> str:
    """How many optional fields have an AI reading and how many a hint from the files — never one word for both:
    an AI reading is not file evidence."""
    ai = sum(1 for hs in field_hints.values() if any(h.get("kind") == "ai_suggestion" for h in hs))
    files = sum(1 for hs in field_hints.values() if any(h.get("kind") != "ai_suggestion" for h in hs))
    parts = ([f"{ai} an AI reading of the files (not file evidence)"] if ai else []) + ([f"{files} a hint from the files"] if files else [])
    return f" Of these, {' and '.join(parts)} (field_hints)."


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


def _absorber_questions(bundle: Mapping, groups: Sequence[Mapping], *, include_answered: bool = False) -> list[dict]:
    """The absorbing element and edge, asked ONCE per distinct suggestion over the groups
    the files agree on (or, where no file states it, the AI readings agree on), and per group
    where they disagree, are partial, or an AI reading differs from the files. Optional: the
    official schema has no absorber field (a confirmed one is carried in the evidence sidecar).

    A group a scientist answered (set_absorber) drops out; ``include_answered`` keeps it, in the SAME bucket:
    the buckets are read from the files' (and AI readings') suggestion only, never from an answer, so an answered
    question is found under the id it was asked with."""
    decided = S.absorber_decisions(bundle)
    by_pair: dict[tuple, list] = {}
    split: list[tuple[Mapping, dict]] = []
    for g in groups:
        if g["group_id"] in decided and not include_answered:
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


def filter_questions(payload: Mapping, *, scope: str | None = None, blocking_only: bool = False,
                     skip_deferred: bool = False) -> list[dict]:
    qs = list(payload["questions"])
    if blocking_only:
        qs = [q for q in qs if q["blocking"]]
        if scope and scope.startswith("group:"):
            # blocking FOR THIS GROUP: where the record composer said which groups a question blocks, only those
            qs = [q for q in qs if "blocks_group_ids" not in q or scope[len("group:"):] in q["blocks_group_ids"]]
    if skip_deferred:
        qs = [q for q in qs if not q.get("deferred")]
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


def answered_question(bundle: Mapping, question_id: str, payload: Mapping | None = None,
                      open_payload: Mapping | None = None) -> dict | None:
    """A value question with its ANSWERED targets back in (``consolidate(include_answered=True)``, the same id),
    and what each target carries now: ``current_answers`` (each distinct latest decision once, with how many
    targets hold it, who, when, and — for an optional-values question — the field), ``answered_targets`` and
    ``status`` (``answered`` when no target is still open, else ``open``). ``None`` when no value question has that
    id even then. ``payload``: that ``include_answered`` payload, and ``open_payload`` the plain one, when the
    caller built them.

    Every kind of :data:`RESOLVABLE_WHEN_ANSWERED`: an absorber question's answer is each group's latest
    set_absorber (or defer), the counter question's the latest answer to it, the clock-zone question's the latest
    zone stated; an answer carries its ``element``/``edge`` or ``positions`` when it has them. Such a question is
    ``open`` while the open list still asks it (a counter position, a group not yet answered)."""
    payload = payload or consolidate(bundle, include_answered=True)
    q = question(payload, question_id)
    if q is None or q["kind"] not in RESOLVABLE_WHEN_ANSWERED:
        return None
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    cand_by_id = {c["candidate_id"]: c for c in bundle["candidates"]}
    field_of = {i: f for f, ids in (q.get("fields") or {}).items() for i in ids}
    answers: dict[tuple, dict] = {}
    answered = 0
    for t in q["targets"]:
        if q["kind"] not in VALUE_KINDS:
            d = _latest_answer_to(bundle, q["kind"], t)
        elif t["kind"] == "candidate":
            c = cand_by_id.get(t["id"])
            d = B.candidate_decision(bundle, c, decisions) if c is not None else None
        else:
            d = decisions.get((t["kind"], t["id"]))
        if d is None or d.get("decision") == "defer":
            continue
        answered += 1
        stated = {k: d[k] for k in ("element", "edge") if d.get(k)}
        if d.get("positions") or d.get("not_counter_positions"):
            stated["positions"] = list(d.get("positions") or d.get("not_counter_positions"))
        key = (field_of.get(t["id"]), d.get("decision"), json.dumps(d.get("value"), sort_keys=True, default=str),
               json.dumps(stated, sort_keys=True))
        a = answers.setdefault(key, {**({"field": key[0]} if key[0] else {}), "decision": d.get("decision"),
                                     "value": d.get("value"), **stated, "targets": 0, "by": None, "decided_utc": None,
                                     "decision_id": None})
        a["targets"] += 1
        if str(d.get("decided_utc") or "") >= str(a["decided_utc"] or ""):
            a.update(by=(d.get("decided_by") or {}).get("name"), decided_utc=d.get("decided_utc"), decision_id=d.get("decision_id"))
    still_open = (question(open_payload or consolidate(bundle), question_id) is not None
                  if answered < len(q["targets"]) or q["kind"] not in VALUE_KINDS else False)
    return {**q, "status": "open" if still_open else "answered", "answered_targets": answered,
            "current_answers": sorted(answers.values(), key=lambda a: (str(a.get("field") or ""), -a["targets"])),
            "statement": ("A later `decide --question` on this id replaces these answers (the same checks apply); "
                          "repeating one records nothing new.")}


def _latest_answer_to(bundle: Mapping, kind: str, target: Mapping) -> Mapping | None:
    """The latest decision that answers a question of ``kind`` (not a value kind) for ``target``: on a record
    group, only a decision the absorber question takes (a group's confirm is not an absorber answer)."""
    if kind == "clock_time_zone":
        return B.clock_zone_decision(bundle)
    allowed = COUNTER_QUESTION_DECISIONS if kind == "naming_counter_positions" else ALLOWED_DECISIONS.get(kind, ())
    want = {"kind": target["kind"], "id": target["id"]}
    return next((d for d in reversed(bundle.get("scientist_decisions") or ())
                 if isinstance(d, Mapping) and d.get("target") == want and d.get("decision") in allowed), None)


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


def scanless_groups(bundle: Mapping, groups: Sequence[Mapping]) -> set[str]:
    """The ids of ``groups`` whose runs list no scan at all (every member's ``scan_count`` is 0): nothing to
    process, so no processing result can be made and the group can never export as it stands. The rule
    ``bundle list <dir> groups`` states as ``cannot_export_reason: no_scans``; ``isaac process`` records such a
    group as not applicable (``no_scans``)."""
    runs = {r["run_key"]: r for r in bundle.get("runs") or ()}
    out = set()
    for g in groups:
        members = [runs[k] for k in g.get("member_run_keys") or () if k in runs]
        if members and not any(int(r.get("scan_count") or 0) for r in members):
            out.add(g["group_id"])
    return out


def _curve(bundle: Mapping, gid: str) -> dict:
    """What approving this group's processing could give it: ``{"state": "approved" | "curve" | "no_curve" | "none",
    "verdict", "reasons"}``. ``no_curve``: every undecided result lists no normalised spectrum (e.g. QC
    ``too_few_common_points``), so an approval supplies no series and the record stays incomplete."""
    from .records import SPECTRUM_ROLES

    mine = [r for r in bundle.get("processing_results") or () if r.get("group_id") == gid and not B.processing_not_applicable(r)]
    if any(r.get("state") == B.STATE_SCIENTIST_CONFIRMED for r in mine):
        return {"state": "approved"}
    open_ = [r for r in mine if r.get("state") in B.PROCESSING_UNDECIDED_STATES]
    if not open_:
        return {"state": "none"}
    # THE LATEST undecided result is the one an approval would name. With NO output file `decide --decision approve`
    # refuses it outright; with files but no normalised spectrum an approval supplies no series. Either way: no curve.
    latest = open_[-1]
    files = (latest.get("outputs") or {}).get("files") or ()
    roles = ("athena_normalized",) + SPECTRUM_ROLES
    qc = latest.get("qc") or {}
    return {"state": "curve" if any(f.get("role") in roles for f in files) else "no_curve", "result_id": B.processing_id(latest),
            "no_output_file": not files, "verdict": qc.get("verdict"),
            "reasons": list(qc.get("reasons") or ()) or sorted({i.get("skip_reason") for i in latest.get("inputs") or () if i.get("skip_reason")})}


def _unasked(bundle: Mapping, group: Mapping, path: str, report: Mapping) -> dict:
    """A field the composer requires for ``group`` that no open question asks: why, and the command that settles it."""
    gid = group["group_id"]
    runs = [r for r in bundle["runs"] if r["run_key"] in set(group.get("member_run_keys") or ())]
    rids = {r["run_id"] for r in runs}
    held = [o.get("candidate_id") or o.get("value_id") for o in list(bundle["candidates"]) + list(bundle["missing_values"])
            if _fills(o.get("target_field_path"), path) and (o.get("run_id") in rids or o.get("run_id") is None)]
    reject = f'isaac bundle decide <bundle_dir> --target {gid} --decision reject --by "<your name>"'
    if held:
        why = ("the confirmed values for it differ inside this group, so the composer fills nothing"
               if any(d.get("path") == path for d in report.get("disagreements") or ()) else
               "every value the import holds for it is already answered (e.g. rejected), or its answer cannot go into the record")
        more = f"   # and the same for {', '.join(held[1:4])}{'…' if len(held) > 4 else ''}" if len(held) > 1 else ""
        return {"path": path, "answerable": True, "reason": why, "targets": len(held),
                "command": f'isaac bundle decide <bundle_dir> --target {held[0]} --decision correct --value <value> --by "<your name>"{more}'}
    if runs and not any(r.get("run_candidate") for r in runs):
        kinds = sorted({str(r.get("source_type")) for r in runs if r.get("source_type")})
        why = (f"every run of this group is marked not a measurement run (run_candidate false"
               + (f"; source type {', '.join(kinds)}" if kinds else "")
               + f": e.g. a reference standard, an alignment or a calibration scan), so the import asks nothing about "
               f"{path} for it and there is nothing an answer could be stored on")
    else:
        why = f"the import holds no value for {path} and asks no question about it here, so no answer can fill it"
    return {"path": path, "answerable": False, "reason": why,
            "command": reject + "   # if it should not become a record; this build cannot fill this field for it"}


def _recommended(report: Mapping, usable: Sequence[tuple], gid: str) -> list[dict]:
    """For each of the composer's stated-potential warnings for group ``gid`` (``records``: the file names state a
    potential the record will not carry), the open question to answer for it — RECOMMENDED, never blocking —
    with the warning, its command made the question's (:func:`scoped_answer_command`), as ``why``."""
    from .records import STATED_POTENTIAL_WARNING, potential_warning_text

    out = []
    for w in report.get("warnings") or ():
        if w.get("code") != STATED_POTENTIAL_WARNING:
            continue
        # BOTH STEPS when the warning names two (no set-point read and no scale): one recommendation each, the
        # warning's text (with both commands made the questions') as the why of each
        steps = [("needs", "targets", "command")] + ([("also_needs", "also_targets", "also_command")] if w.get("also_needs") else [])
        cmds, hits = {}, []
        for need, tkey, ckey in steps:
            wanted = set(w.get(tkey) or ())
            hit = next(((q, field) for _, q, field, _, _ in usable
                        if field == w[need] and wanted.intersection(dict(_value_paths(q)).get(field, ()))), None)
            hits.append((w[need], hit))
            if hit is not None:
                cmds[ckey] = scoped_answer_command(hit[0], hit[1], gid)
        why = potential_warning_text({**w, **cmds}) if cmds else w["text"]
        for need, hit in hits:
            if hit is None:
                out.append({"question_id": None, "fields": [need], "only": None, "blocking": False, "why": why})
                continue
            q, field = hit
            pst = q.get("per_scope_targets") or {}
            out.append({"question_id": q["question_id"], "fields": [field],
                        "only": f"group:{gid}" if f"group:{gid}" in pst and len(pst) > 1 else None, "blocking": False,
                        "why": why})
    return out


def minimum_answers_for_one_group(payload: Mapping, bundle: Mapping, scope: str | None = None,
                                  bundle_dir: Path | None = None, reports: Mapping[str, Mapping] | None = None) -> dict | None:
    """The fewest answers that stand between one record group and export, judged by THE RECORD COMPOSER
    (:func:`compositions`: the missing-required list ``build-records`` and ``validate`` report): for each field the
    composer lists as missing for the group that only an answer supplies, ONE open question that fills it
    (``questions``, each with the ``--only`` scope to answer it at), or — when no question asks it — an
    ``unasked_required`` item with why and the command that settles it; plus the decisions that group still needs:
    confirming it (unless a scientist already did) and approving its processing result (unless one is approved).
    A decision already made is never named again. So answering exactly ``questions`` (at their ``only`` scope) and
    ``plus_decisions`` leaves the group with nothing missing.

    A group with NOTHING left here (no field missing, confirmed, its processing approved) is not "the nearest": it
    is counted in ``groups_with_nothing_left`` and the nearest group that still needs something is named. When none
    does, ``group_id`` is ``None`` and the statement says so.

    ``scope`` ``group:<id>`` (``bundle questions --scope``) names THAT group, never another; any other
    scope (``experiment``, a run) is not one group and leaves the choice open.

    A group no answer or approval can complete — the processing protocol does not apply to it, its processing
    result has no curve (e.g. QC ``too_few_common_points``), none of its runs lists a scan (:func:`scanless_groups`,
    before ``isaac process`` has recorded it as ``no_scans``), or a required field nothing can be stored on (no
    measurement run) — is never offered as "the nearest" while another exists, and one whose curve FAILED QC only
    after every group without one. When only such groups are left, ``blocked`` says why, never "approve its
    processing result". ``bundle_dir`` lets the composer read the approved processing files (a changed file then
    shows as what is missing); without it only the answer-supplied fields are composed.

    ``reports``: the reports :func:`consolidate` composed for this same, unchanged bundle (its
    ``compositions_out``), reused instead of composing every live group again. They read no processing file, which
    changes nothing used here except for a group with an approved processing result (its curve, QC status and
    outputs): with ``bundle_dir`` such a group, and any group the reports lack, is composed again here."""
    blocked = processing_blocked_groups(bundle)
    wanted = scope[len("group:"):] if isinstance(scope, str) and scope.startswith("group:") else None
    live = [g for g in live_groups(bundle) if wanted is None or g["group_id"] == wanted]
    if not live:
        return None
    scanless = scanless_groups(bundle, live)
    if reports is None:
        reports = compositions({**bundle, "record_groups": live}, bundle_dir)
    else:
        again = [g for g in live if g["group_id"] not in reports
                 or (bundle_dir is not None and _curve(bundle, g["group_id"])["state"] == "approved")]
        reports = {**{g["group_id"]: reports[g["group_id"]] for g in live if g["group_id"] in reports},
                   **(compositions({**bundle, "record_groups": again}, bundle_dir) if again else {})}
    # INDEXED once: (composer path, the groups each (question, field) reaches, or every group via a beamtime target)
    asks: list[tuple[str, dict, str, set, bool]] = []
    for q in payload["questions"]:
        if q["kind"] not in VALUE_KINDS or q.get("informational"):
            continue
        pst = q.get("per_scope_targets") or {}
        for field, ids in _value_paths(q):
            mine = set(ids)
            groups = {sc[len("group:"):] for sc, tids in pst.items() if sc.startswith("group:") and mine.intersection(tids)}
            asks.append((_composer_path(field), q, field, groups, bool(mine.intersection(pst.get("experiment", ())))))
    # ...and which of them each group can use (in that order): every beamtime-wide one, plus its own
    everywhere: list[int] = []
    asks_of: dict[str, list[int]] = {}
    for i, (_, _, _, groups, anywhere) in enumerate(asks):
        if anywhere:
            everywhere.append(i)
        else:
            for owner in groups:
                asks_of.setdefault(owner, []).append(i)
    best = None
    done: list[str] = []
    warned_done: list[str] = []
    for n, g in enumerate(live):
        gid = g["group_id"]
        rep = reports[gid]
        chosen: dict[str, dict] = {}
        unasked: list[dict] = []
        usable = [asks[i] for i in sorted(everywhere + asks_of.get(gid, []))]
        because = {m["path"]: m["required_because"] for m in rep.get("missing_required") or () if m.get("required_because")}
        for path in _answer_missing(rep):
            options, seen = [], set()
            for cpath, q, field, _, _ in usable:
                if (cpath == path or cpath.startswith(path + ".")) and q["question_id"] not in seen:
                    seen.add(q["question_id"])
                    options.append((not q["blocking"], bool(q.get("deferred")), q["scope"] != "experiment", q, field))
            if not options:
                unasked.append(_unasked(bundle, g, path, rep))
                continue
            *_, q, field = min(options, key=lambda o: o[:3])
            pst = q.get("per_scope_targets") or {}
            entry = chosen.setdefault(q["question_id"], {
                "question_id": q["question_id"], "fields": [],
                # answer it for THIS group: an experiment-scope question's other groups need not be answered now
                "only": f"group:{gid}" if q["scope"] == "experiment" and f"group:{gid}" in pst and "experiment" not in pst else None,
                **({"deferred": True} if q.get("deferred") else {})})
            entry["fields"].append(field if q["kind"] == "optional_values" else path)
            if path in because:
                # a CONDITIONAL requirement (an object the record carries requires this member): why, said
                entry.setdefault("required_because", {})[path] = because[path]
        plus, hard, soft = [], [], None
        if g.get("status") != B.STATE_SCIENTIST_CONFIRMED:
            plus.append("confirm the group")
        curve = _curve(bundle, gid)
        if gid in blocked:
            hard.append(f"{B.NO_PROTOCOL_COVERS} ({blocked[gid]}); this group cannot become a complete record until one does")
        elif curve["state"] == "none" and gid in scanless:
            # never "approve its processing result": there is no scan to process, so no result can ever be made
            # (`isaac process` records it as not applicable, no_scans). The same rule as `bundle list groups`.
            hard.append("none of its runs lists a scan, so there is nothing to process and no processing result can be "
                        "made: it cannot become a complete record as it stands; reject the group if it is not a measurement "
                        f'(`isaac bundle decide <bundle_dir> --target {gid} --decision reject --by "<your name>"`)')
        elif curve["state"] == "no_curve":
            # never "approve its processing result": with no output file `decide` refuses that approval, and without a
            # normalised spectrum it would supply no series. The real steps are named instead.
            pid = curve["result_id"]
            hard.append(f"its processing result {pid} has no curve ("
                        + ("no output file" if curve["no_output_file"] else "no normalised spectrum")
                        + f"; QC {curve['verdict'] or 'not run'}{': ' + ', '.join(curve['reasons']) if curve['reasons'] else ''}), "
                        "so there is nothing to approve: reject the result or mark it needs_changes "
                        f'(`isaac bundle decide <bundle_dir> --target {pid} --decision reject|needs_changes --by "<your name>"`) '
                        "and re-run `isaac process`, or reject the group if it is not a measurement "
                        f'(`isaac bundle decide <bundle_dir> --target {gid} --decision reject --by "<your name>"`)')
        elif curve["state"] == "approved":
            struct = [m for m in rep.get("missing_required") or () if m.get("from") != FROM_AN_ANSWER]
            if bundle_dir is not None and struct:
                from .records import processing_remedy

                plus.append(f"processing: {processing_remedy(rep.get('processing') or {})}")
        elif gid not in scanless:
            plus.append("approve its processing result")
            if curve.get("verdict") == "fail":
                soft = f"its processing QC verdict is fail ({', '.join(curve['reasons']) or 'no reason given'})"
        cannot = [u for u in unasked if not u["answerable"]]
        if cannot:
            hard.append(f"{', '.join(u['path'] for u in cannot)}: {cannot[0]['reason']}")
        need = len(chosen) + sum(1 for u in unasked if u["answerable"])
        warned = _recommended(rep, usable, gid)
        if not need and not plus and not hard and wanted is None:
            done.append(gid)
            warned_done += [r["why"] for r in warned]
            continue
        rank = (bool(hard), soft is not None, need + len(plus), n)
        if best is None or rank < best["rank"]:
            best = {"rank": rank, "group_id": gid, "need": need, "plus": plus, "questions": list(chosen.values()),
                    "unasked": unasked, "hard": hard, "soft": soft, "missing": [m["path"] for m in rep.get("missing_required") or ()],
                    "recommended": warned}
    if best is None:
        if not done:
            return None
        return {"group_id": None, "blocking_questions": 0, "plus_decisions": [], "groups_with_nothing_left": len(done),
                "statement": (f"{len(done)} record group(s) have no blocking question and no decision left here (confirmed, "
                              "processing approved): run `isaac bundle build-records`, `validate` and `export`."),
                **({"warnings": warned_done[:_HINTS_PER_QUESTION], "warnings_total": len(warned_done)} if warned_done else {})}
    out = {"group_id": best["group_id"], "blocking_questions": best["need"], "plus_decisions": best["plus"],
           "questions": best["questions"], "unasked_required": best["unasked"],
           "missing_required_now": best["missing"],
           "basis": "records.compose_group: the missing-required list build-records and validate report"}
    if best["recommended"]:
        # NOT BLOCKING, NOT COUNTED in blocking_questions: the record exports without it, but without the condition
        # its file names state (records: the stated-potential warning)
        out["recommended"] = best["recommended"]
        out["warnings"] = [r["why"] for r in best["recommended"]]
    if best["hard"]:
        out["blocked"] = "; ".join(best["hard"])
    if best["soft"]:
        out["processing_qc"] = best["soft"]
    if blocked:
        out["groups_without_an_applicable_processing_protocol"] = len(blocked)
    if done:
        out["groups_with_nothing_left"] = len(done)
    if wanted is not None:
        out["scope"] = scope
    return out
