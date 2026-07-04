---
name: isaac-export
description: Export a validated ISAAC draft into records/ (validation-gated, deterministic) with an optional best-effort knowledge-graph refresh. Use when the user runs /isaac-export or asks to finalize/export a record.
---

# /isaac-export

Export is gated by the deterministic validator. There is no override: if
validation fails, the export does not happen.

## Steps

1. Resolve the draft: the path given as an argument, else the newest file in `drafts/`.
2. Run: `.venv/bin/isaac export <draft>`
   - **Blocked (exit 1):** show the report verbatim and point to `/isaac-complete`
     for missing answers. Do not edit the draft yourself to force a pass, and do
     not retry with the checks weakened — there is no such flag by design.
   - **Success (exit 0):** the record now lives in `records/<record_id>.json`.
3. On success, offer to commit: `git add records/ && git commit` with a message
   naming the record_id. Records enter project history through git — that *is*
   the trust hierarchy.
4. Best-effort graph refresh — never blocking:
   - If `graphify-out/graph.json` exists, run the `/graphify . --update` flow.
   - If it fails or Graphify is not installed, report that as a note and move on.
     **The export already succeeded; a graph failure must never roll it back or
     be presented as an export failure.**
5. Confirm to the user: record path, PASS report summary, commit status, and
   graph-refresh outcome (done / skipped / failed-nonblocking).
