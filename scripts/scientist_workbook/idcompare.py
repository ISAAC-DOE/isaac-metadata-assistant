#!/usr/bin/env python3
"""Compare two ``idcheck.py`` outputs: the same rows, and whether each row's status changed.

A row is (sheet, row, ref, folder, question id); its status is resolves / in_list / open / blocking / tier. Prints
whether both runs hold the same rows, how many rows changed status (by sheet and field), and the first examples.
Exit 0 when nothing differs, 1 otherwise.

    python3 scripts/scientist_workbook/idcompare.py before.json after.json
"""

from __future__ import annotations

import argparse
import collections
import json

FIELDS = ("resolves", "in_list", "open", "blocking", "tier")


def _key(r: dict) -> tuple:
    return (r["sheet"], r["row"], r["ref"], r["folder"], r["qid"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--examples", type=int, default=15)
    args = ap.parse_args(argv)
    a = {_key(r): r for r in json.load(open(args.before, encoding="utf-8"))}
    b = {_key(r): r for r in json.load(open(args.after, encoding="utf-8"))}
    same_rows = set(a) == set(b)
    print("rows", len(a), len(b), "same row keys:", same_rows)
    if not same_rows:
        print("  only before:", len(set(a) - set(b)), " only after:", len(set(b) - set(a)))
    diff: collections.Counter = collections.Counter()
    examples, changed = [], set()
    for k in sorted(set(a) & set(b), key=str):
        for f in FIELDS:
            if a[k][f] != b[k][f]:
                changed.add(k)
                diff[(k[0], f, a[k][f], b[k][f])] += 1
                if len(examples) < args.examples:
                    examples.append((k, f, a[k][f], b[k][f]))
    print("rows whose status differs:", len(changed))
    for k, v in sorted(diff.items(), key=lambda kv: -kv[1]):
        print(" ", v, k)
    for e in examples:
        print("   ", e)
    return 0 if same_rows and not changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
