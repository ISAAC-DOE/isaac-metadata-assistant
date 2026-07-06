---
name: isaac-export
description: Transform a validated ISAAC draft into an official record plus an evidence sidecar (schema-gated), with an optional best-effort graph refresh. Use when the user runs /isaac-export or asks to finalize/export.
---

# /isaac-export

Export transforms a draft into the **official ISAAC record shape** and writes two files:
`records/<ULID>.json` (validates against `schema/isaac_record_v1.json`) and
`records/<ULID>.evidence.json` (the evidence sidecar). It is gated twice — no-guessing checks
on the draft, then the official schema on the produced record. There is no override.

## Steps

1. Resolve the draft: argument, else newest in `drafts/`.
2. Run `.venv/bin/isaac export <draft>`.
   - **Blocked (exit 1):** show the report. Draft-level failures → `/isaac-complete`.
     Official-schema failures mean the mapping is wrong or a required block is absent — fix the
     draft's `fields` paths and re-run. Do not hand-edit the produced record, and do not
     weaken the checks (there is no flag to).
   - **Success (exit 0):** record + sidecar are written under `records/`, keyed by a generated
     ULID.
3. Explain the sidecar: the official record carries no per-field provenance (the schema forbids
   extra keys), so `records/<ULID>.evidence.json` maps each official JSON-path — and each
   asset, descriptor, and implicit inference — to its evidence. That file is where "no
   guessing" stays auditable after export. (It is not part of the ISAAC standard; flag for
   mentors if records leave this repo.)
4. Offer to commit: `git add records/ && git commit` naming the ULID. Git is the trust
   hierarchy — records enter history at export.
5. Best-effort graph refresh, **never blocking**: if `graphify-out/graph.json` exists, run
   `/graphify . --update`. If Graphify is absent or fails, note it and stop — the export
   already succeeded and must not be rolled back.
