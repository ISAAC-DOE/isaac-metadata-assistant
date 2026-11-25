#!/usr/bin/env python3
"""Measure how accurate automatic fills are, against a scientist's answers (read-only).

    PYTHONPATH=$PWD/src:$PWD/apps/api python scripts/replay_fill_accuracy.py \
        --answers <bundle dir holding the scientist's answers> --replay <bundle dir to measure> [--json]

ANSWER KEY: every value in --answers whose value_state is ``scientist_confirmed``, keyed by
(run name, target_field_path); the value is the effective one (a decision's corrected value wins).
Runs are matched across the two bundles by run NAME (the run's ``stem``, else its ``label``), never by id.
Experiment/beamtime-scope values are keyed by (None, path).

REPLAY: each key is looked up in --replay and classified:
  filled_correct  state ``filled`` and the same value
  filled_wrong    state ``filled`` and a different value
  confirmed       scientist_confirmed in the replay too
  still_asked     needs_review / candidate_extracted / conflicting / missing (would be asked)
  absent          no such target in the replay
Replay values in state ``filled`` with no answer-key counterpart are counted by path (filled_unchecked).

Nothing is ever written: bundle.json is only read (``load_bundle``), no save, no upgrade.
Exit 0, or 2 when an input is unreadable.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from isaac_api.local_import import bundle as B

CLASSES = ("filled_correct", "filled_wrong", "confirmed", "still_asked", "absent")
CONFIRMED = "scientist_confirmed"
FILLED = "filled"


def norm(value: Any) -> Any:
    """JSON-normalised value; strings compare case-insensitively after stripping."""
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, Mapping):
        return {str(k): norm(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [norm(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def same(a: Any, b: Any) -> bool:
    return json.dumps(norm(a), sort_keys=True, default=str) == json.dumps(norm(b), sort_keys=True, default=str)


def run_names(bundle: Mapping) -> dict:
    out = {}
    for r in bundle.get("runs") or ():
        out[r.get("run_id")] = r.get("stem") or r.get("label") or r.get("run_key") or r.get("run_id")
    return out


def entries(bundle: Mapping) -> list[dict]:
    """Every candidate / missing value / conflict with a target: run name, path, state, effective value."""
    names = run_names(bundle)
    decisions = B._decisions_by_target(bundle.get("scientist_decisions") or ())
    out = []
    for section, kind, idkey in (("candidates", "candidate", "candidate_id"),
                                 ("missing_values", "missing_value", "value_id"),
                                 ("conflicts", "conflict", "conflict_id")):
        for obj in bundle.get(section) or ():
            path = obj.get("target_field_path")
            if not path:
                continue
            if kind == "candidate":
                d = B.candidate_decision(bundle, obj, decisions)
            else:
                d = decisions.get((kind, obj.get(idkey)))
            value = B.final_value(obj.get("value"), d, obj.get("readings"))
            if obj.get("value_state") == FILLED and isinstance(obj.get("fill"), Mapping):
                # a filled value carries what its rule fills in `fill.value` (a missing value's `value` is always null)
                value = obj["fill"].get("value")
            rid = obj.get("run_id")
            out.append({"run": names.get(rid, rid) if rid else None, "path": path,
                        "state": obj.get("value_state"), "value": value})
    return out


def _by_key(items: list[dict]) -> dict:
    keyed = defaultdict(list)
    for e in items:
        keyed[(e["run"], e["path"])].append(e)
    return keyed


def classify(answers: Mapping, replay: Mapping) -> dict:
    key_rows = {}
    for k, es in _by_key(entries(answers)).items():
        conf = [e for e in es if e["state"] == CONFIRMED]
        if conf:
            key_rows[k] = conf[0]
    replay_by = _by_key(entries(replay))
    rows, wrong = [], []
    for (run, path), ans in sorted(key_rows.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        cands = replay_by.get((run, path), [])
        filled = [e for e in cands if e["state"] == FILLED]
        row = {"run": run, "path": path, "answer_value": ans["value"], "replay_value": None, "replay_state": None}
        if filled:
            pick = next((e for e in filled if same(e["value"], ans["value"])), filled[0])
            row.update(replay_value=pick["value"], replay_state=FILLED,
                       cls="filled_correct" if same(pick["value"], ans["value"]) else "filled_wrong")
        elif any(e["state"] == CONFIRMED for e in cands):
            pick = next(e for e in cands if e["state"] == CONFIRMED)
            row.update(replay_value=pick["value"], replay_state=CONFIRMED, cls="confirmed")
        elif cands:
            row.update(replay_value=cands[0]["value"], replay_state=cands[0]["state"], cls="still_asked")
        else:
            row["cls"] = "absent"
        rows.append(row)
        if row["cls"] == "filled_wrong":
            wrong.append({k: row[k] for k in ("run", "path", "replay_value", "answer_value")})
    overall = Counter(r["cls"] for r in rows)
    per_path: dict = defaultdict(Counter)
    for r in rows:
        per_path[r["path"]][r["cls"]] += 1
    unchecked: Counter = Counter()
    for (run, path), es in replay_by.items():
        if (run, path) not in key_rows:
            unchecked[path] += sum(1 for e in es if e["state"] == FILLED)
    unchecked = Counter({p: n for p, n in unchecked.items() if n})
    return {
        "answer_key_size": len(rows),
        "counts": {c: overall.get(c, 0) for c in CLASSES},
        "per_path": {p: {c: per_path[p].get(c, 0) for c in CLASSES} for p in sorted(per_path)},
        "filled_wrong": wrong,
        "filled_unchecked": {"total": sum(unchecked.values()), "per_path": dict(sorted(unchecked.items()))},
        "rows": rows,
    }


def render(result: Mapping) -> str:
    lines = [f"Answer key: {result['answer_key_size']} scientist-confirmed values", "", "Overall:"]
    lines += [f"  {c:15} {n}" for c, n in result["counts"].items()]
    lines += ["", "Per target_field_path:"]
    for p, cs in result["per_path"].items():
        lines.append(f"  {p}: " + ", ".join(f"{c}={n}" for c, n in cs.items() if n))
    lines += ["", f"filled_wrong ({len(result['filled_wrong'])}):"]
    for w in result["filled_wrong"]:
        lines.append(f"  run={w['run']!r} path={w['path']} replay={w['replay_value']!r} answer={w['answer_value']!r}")
    fu = result["filled_unchecked"]
    lines += ["", f"filled_unchecked (no answer-key counterpart): {fu['total']}"]
    lines += [f"  {p}: {n}" for p, n in fu["per_path"].items()]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--answers", required=True, type=Path)
    ap.add_argument("--replay", required=True, type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        answers = B.load_bundle(args.answers)
        replay = B.load_bundle(args.replay)
        result = classify(answers, replay)
    except (B.BundleInvalid, OSError, KeyError, TypeError) as exc:
        print(f"unreadable input: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, default=str) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
