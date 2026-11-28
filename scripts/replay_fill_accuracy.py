#!/usr/bin/env python3
"""Measure how accurate automatic fills are, against a scientist's answers (read-only).

    PYTHONPATH=$PWD/src:$PWD/apps/api python scripts/replay_fill_accuracy.py \
        --answers <bundle dir holding the scientist's answers> --replay <bundle dir to measure> [--rederive] [--json]

ANSWER KEY: every value in --answers whose value_state is ``scientist_confirmed``, keyed by
(run name, target_field_path); the value is the effective one (a decision's corrected value wins).
Runs are matched across the two bundles by run NAME (the run's ``stem``, else its ``label``), never by id.
Experiment/beamtime-scope values are keyed by (None, path).

REPLAY: each key is looked up in --replay and classified:
  filled_correct  state ``filled`` and the same value (a green fill, or a yellow deduction: see the colour)
  filled_wrong    state ``filled`` and a different value
  guessed_correct state ``guessed`` (1.22.0, DEC-100: an inferred reading, yellow) and the same value
  guessed_wrong   state ``guessed`` and a different value
  confirmed       scientist_confirmed in the replay too
  still_asked     needs_review / candidate_extracted / conflicting / missing (would be asked)
  absent          no such target in the replay
Replay values in state ``filled`` with no answer-key counterpart are counted by path (filled_unchecked), and ``guessed``
ones likewise (guessed_unchecked). Each wrong row says its colour (green / yellow, ``bundle.value_colour``): the design's
target is green-wrong 0, yellow-wrong reported and kept low.

``--rederive`` derives the replay bundle's states under THIS build in memory first (``bundle.apply_derivations`` on a
copy), so a bundle an older build stored is measured with this build's rules (guesses included). Nothing is ever
written: bundle.json is only read (``load_bundle``), no save, no upgrade.
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

CLASSES = ("filled_correct", "filled_wrong", "guessed_correct", "guessed_wrong", "confirmed", "still_asked", "absent")
CONFIRMED = "scientist_confirmed"
FILLED = "filled"
GUESSED = "guessed"
#: the states a rule supplies a value in (each classified apart)
RULE_STATES = (FILLED, GUESSED)


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
            if obj.get("value_state") in RULE_STATES and isinstance(obj.get("fill"), Mapping):
                # a filled value carries what its rule fills in `fill.value` (a missing value's `value` is always null)
                value = obj["fill"].get("value")
            rid = obj.get("run_id")
            rule = (obj.get("fill") or {}).get("rule_id") if isinstance(obj.get("fill"), Mapping) else None
            out.append({"run": names.get(rid, rid) if rid else None, "path": path,
                        "state": obj.get("value_state"), "value": value, "rule": rule,
                        "colour": B.value_colour(obj.get("value_state"), rule, needed=False)})
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
    rows, wrong, guessed_wrong = [], [], []
    for (run, path), ans in sorted(key_rows.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        cands = replay_by.get((run, path), [])
        filled = [e for e in cands if e["state"] == FILLED]
        guessed = [e for e in cands if e["state"] == GUESSED]
        row = {"run": run, "path": path, "answer_value": ans["value"], "replay_value": None, "replay_state": None}
        if filled or guessed:
            state = FILLED if filled else GUESSED
            pool = filled or guessed
            pick = next((e for e in pool if same(e["value"], ans["value"])), pool[0])
            row.update(replay_value=pick["value"], replay_state=state, rule=pick.get("rule"), colour=pick.get("colour"),
                       cls=f"{state}_correct" if same(pick["value"], ans["value"]) else f"{state}_wrong")
        elif any(e["state"] == CONFIRMED for e in cands):
            pick = next(e for e in cands if e["state"] == CONFIRMED)
            row.update(replay_value=pick["value"], replay_state=CONFIRMED, cls="confirmed")
        elif cands:
            row.update(replay_value=cands[0]["value"], replay_state=cands[0]["state"], cls="still_asked")
        else:
            row["cls"] = "absent"
        rows.append(row)
        if row["cls"] in ("filled_wrong", "guessed_wrong"):
            (wrong if row["cls"] == "filled_wrong" else guessed_wrong).append(
                {k: row.get(k) for k in ("run", "path", "replay_value", "answer_value", "rule", "colour")})
    overall = Counter(r["cls"] for r in rows)
    per_path: dict = defaultdict(Counter)
    for r in rows:
        per_path[r["path"]][r["cls"]] += 1
    unchecked: Counter = Counter()
    guessed_unchecked: Counter = Counter()
    for (run, path), es in replay_by.items():
        if (run, path) not in key_rows:
            unchecked[path] += sum(1 for e in es if e["state"] == FILLED)
            guessed_unchecked[path] += sum(1 for e in es if e["state"] == GUESSED)
    unchecked = Counter({p: n for p, n in unchecked.items() if n})
    guessed_unchecked = Counter({p: n for p, n in guessed_unchecked.items() if n})
    return {
        "answer_key_size": len(rows),
        "counts": {c: overall.get(c, 0) for c in CLASSES},
        "per_path": {p: {c: per_path[p].get(c, 0) for c in CLASSES} for p in sorted(per_path)},
        "filled_wrong": wrong,
        "guessed_wrong": guessed_wrong,
        # the design's measure: a wrong GREEN value must stay 0; a wrong yellow one is reported
        "wrong_by_colour": dict(Counter(w.get("colour") or "?" for w in wrong + guessed_wrong)),
        "filled_unchecked": {"total": sum(unchecked.values()), "per_path": dict(sorted(unchecked.items()))},
        "guessed_unchecked": {"total": sum(guessed_unchecked.values()),
                              "per_path": dict(sorted(guessed_unchecked.items()))},
        "rows": rows,
    }


def render(result: Mapping) -> str:
    lines = [f"Answer key: {result['answer_key_size']} scientist-confirmed values", "", "Overall:"]
    lines += [f"  {c:15} {n}" for c, n in result["counts"].items()]
    lines += ["", "Per target_field_path:"]
    for p, cs in result["per_path"].items():
        lines.append(f"  {p}: " + ", ".join(f"{c}={n}" for c, n in cs.items() if n))
    for key in ("filled_wrong", "guessed_wrong"):
        lines += ["", f"{key} ({len(result[key])}):"]
        for w in result[key]:
            lines.append(f"  run={w['run']!r} path={w['path']} replay={w['replay_value']!r} answer={w['answer_value']!r}"
                         + (f" colour={w['colour']}" if w.get("colour") else ""))
    lines += ["", "wrong by colour: " + (", ".join(f"{c}={n}" for c, n in sorted(result["wrong_by_colour"].items()))
                                          or "none")]
    for key in ("filled_unchecked", "guessed_unchecked"):
        fu = result[key]
        lines += ["", f"{key} (no answer-key counterpart): {fu['total']}"]
        lines += [f"  {p}: {n}" for p, n in fu["per_path"].items()]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--answers", required=True, type=Path)
    ap.add_argument("--replay", required=True, type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--rederive", action="store_true",
                    help="derive the replay bundle's states under this build in memory first (nothing is written)")
    args = ap.parse_args(argv)
    try:
        answers = B.load_bundle(args.answers)
        replay = B.load_bundle(args.replay)
        if args.rederive:
            replay = B.apply_derivations(json.loads(json.dumps(replay)))
        result = classify(answers, replay)
    except (B.BundleInvalid, OSError, KeyError, TypeError) as exc:
        print(f"unreadable input: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, default=str) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
