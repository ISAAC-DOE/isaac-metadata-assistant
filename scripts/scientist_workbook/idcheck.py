#!/usr/bin/env python3
"""Resolve every question-id row of a scientist question workbook against a folder of bundles.

Each tab is read by its header row (``isaac_api.local_import.workbook_answers.read_tabs``, the reader
``isaac bundle answers import`` uses). Every row whose ``ISAAC question ID`` is a ``Q-…`` id is looked up in
the bundle of its ``Folder``: ``<bundles_root>/<Folder>/bundle.json`` or ``<bundles_root>/<Folder>/bundle/bundle.json``.
A row resolves when the bundle's consolidated questions (answered ones included) still hold that id.

Writes one JSON row per id row (sheet, row, ref, folder, qid, resolves, in_list, open, blocking, tier), the shape
``idcompare.py`` compares, and prints the counts. Reads only; prints no value, no question text.

    python3 scripts/scientist_workbook/idcheck.py <workbook.xlsx> <bundles_root> --out ids.json [--code <checkout>]

``--code`` puts another checkout's ``src`` and ``apps/api`` first on the import path, to check the same rows on
another build.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import warnings
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("workbook")
    ap.add_argument("bundles_root", help="a folder holding one bundle per beamtime folder name")
    ap.add_argument("--out", required=True, help="the JSON file to write (one row per question-id row)")
    ap.add_argument("--code", help="a checkout whose src/ and apps/api/ to import ISAAC from")
    args = ap.parse_args(argv)
    if args.code:
        sys.path[:0] = [str(Path(args.code) / "src"), str(Path(args.code) / "apps" / "api")]
    import openpyxl
    from isaac_api.local_import import mutations as M
    from isaac_api.local_import import questions as Q
    from isaac_api.local_import import workbook_answers as W

    root = Path(args.bundles_root)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(args.workbook)
    rows = [(r["tab"], r["row"], r["ref"], r["folder"], r["id"]) for t in W.read_tabs(wb) for r in t["rows"]
            if (r.get("id") or "").startswith("Q-")]
    cache: dict[str, tuple] = {}

    def payloads(folder: str):
        if folder not in cache:
            d = root / folder
            if (d / "bundle").is_dir() and not (d / "bundle.json").exists():
                d = d / "bundle"
            b = M.load(d)
            every = Q.consolidate(b, include_answered=True)
            open_ = Q.consolidate(b)
            cache[folder] = (every, {q["question_id"] for q in every["questions"]},
                             {q["question_id"] for q in open_["questions"]})
        return cache[folder]

    out = []
    for sheet, n, ref, folder, qid in rows:
        if not folder:
            print(f"{sheet!r} row {n}: no Folder, skipped", file=sys.stderr)
            continue
        every, listed, open_ids = payloads(folder)
        q = Q.question(every, qid)
        out.append({"sheet": sheet, "row": n, "ref": ref, "folder": folder, "qid": qid, "resolves": q is not None,
                    "in_list": qid in listed, "open": qid in open_ids, "blocking": bool(q and q.get("blocking")),
                    "tier": q and q.get("tier")})
    Path(args.out).write_text(json.dumps(out), encoding="utf-8")
    bad = [r for r in out if not r["resolves"]]
    print(len(out), "rows with a Q- id;", len(bad), "do not resolve")
    print(dict(collections.Counter(r["sheet"] for r in bad)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
