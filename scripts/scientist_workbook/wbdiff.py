#!/usr/bin/env python3
"""Diff two versions of a scientist question workbook, cell by cell.

For every sheet of the OLD workbook: every cell is compared by value with the same cell of the new one, and the
id-shaped cells are counted (question ids ``Q-…``, proposal ids, collapsed-row and row refs, record-group ids). New
sheets, removed sheets, whether the old sheets kept their order, and rows added to old sheets are listed. Exit 0 when
no old cell changed, 1 otherwise. Reads only.

    python3 scripts/scientist_workbook/wbdiff.py old.xlsx new.xlsx [--show 50]
"""

from __future__ import annotations

import argparse
import re
import warnings

#: the id shapes a question workbook carries (question, proposal, Athena merge, rule/new-question, rule proposal,
#: tab-row ref such as 2-0001 / 2b-0001, record group)
ID_RE = re.compile(r"^(Q-[0-9a-f]{10}|P-\d{4}|AM\d{2}|[NR]\d+|CR\d+|\d{1,2}b?-\d{4}|rg-[0-9a-f]{16})$")


def main(argv: list[str] | None = None) -> int:
    import openpyxl

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--show", type=int, default=50, help="print at most this many differing cells")
    args = ap.parse_args(argv)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a = openpyxl.load_workbook(args.old, read_only=True)
        b = openpyxl.load_workbook(args.new, read_only=True)
    added = [s for s in b.sheetnames if s not in a.sheetnames]
    removed = [s for s in a.sheetnames if s not in b.sheetnames]
    print("old sheets", len(a.sheetnames), "new sheets", len(b.sheetnames), "added", added, "removed", removed)
    print("order of old sheets kept:", [s for s in b.sheetnames if s in a.sheetnames] == [s for s in a.sheetnames if s in b.sheetnames])
    ncell = nid = 0
    diffs, rows_added = [], []
    for s in a.sheetnames:
        if s in removed:
            continue
        old_rows = list(a[s].iter_rows(values_only=True))
        new_rows = list(b[s].iter_rows(values_only=True))
        for i, ra in enumerate(old_rows):
            rb = new_rows[i] if i < len(new_rows) else ()
            for j, v in enumerate(ra):
                w = rb[j] if j < len(rb) else None
                ncell += 1
                if v is not None and ID_RE.match(str(v)):
                    nid += 1
                if v != w:
                    diffs.append((s, i + 1, j + 1, v, w))
        rows_added += [(s, i + 1, new_rows[i][0] if new_rows[i] else None) for i in range(len(old_rows), len(new_rows))]
    print("cells compared", ncell, "id cells compared", nid, "differences", len(diffs))
    for d in diffs[: args.show]:
        print("  DIFF", d[:3], repr(d[3])[:120], "->", repr(d[4])[:160])
    if len(diffs) > args.show:
        print(f"  … {len(diffs) - args.show} more")
    print("rows added to old sheets:", rows_added)
    return 0 if not diffs else 1


if __name__ == "__main__":
    raise SystemExit(main())
