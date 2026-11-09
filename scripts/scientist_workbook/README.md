# Scientist question workbook checks

Read-only checks for the question workbook a scientist is sent and fills in (the tabs with a
`YOUR ANSWER` column). `isaac bundle answers import` reads the answers back into a bundle; these
scripts check the ids and the workbook itself. Every path is an argument; nothing is hard-coded, and
nothing they read or write belongs in the repository (real workbooks and bundles stay outside it).

| Script | What it does |
|---|---|
| `idcheck.py <workbook.xlsx> <bundles_root> --out ids.json [--code <checkout>]` | Every `Q-…` row, looked up in its `Folder`'s bundle (`<bundles_root>/<Folder>/bundle.json` or `.../bundle/bundle.json`): resolves, listed, open, blocking, tier. Prints how many do not resolve, by tab. `--code` imports ISAAC from another checkout, to check the same rows on another build. |
| `idcompare.py before.json after.json` | Two `idcheck.py` outputs, row by row: the same rows, and which changed status. Exit 1 on any change. |
| `wbdiff.py old.xlsx new.xlsx [--show N]` | Two versions of the workbook: every cell of every old sheet by value, id cells counted, sheets added or removed, rows added. Exit 1 when an old cell changed. |

Run them with the repository's environment (`PYTHONPATH=src:apps/api`), e.g.

    python scripts/scientist_workbook/idcheck.py filled.xlsx bundles/ --out /tmp/ids.json

Not ported: the scripts that built the 8 Nov 2026 workbook, its dashboard and its numbers. They named
real beamtime folders and expected counts, so they are not general tools.
