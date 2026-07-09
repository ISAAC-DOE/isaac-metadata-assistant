# UI handoff — user workflows

> Design handoff, **not** an implementation spec. The UI is not being built yet. These flows
> describe what a future ISAAC Metadata Assistant UI would let an operator do, mapped step by step
> to the real CLI commands, Claude skills, and Python functions that already exist. A UI is a
> **front end over the deterministic core** — it must never become a second source of truth.

Read alongside [`screens.md`](screens.md), [`design-system.md`](design-system.md), and
[`ai-assistant-and-graphify.md`](ai-assistant-and-graphify.md). Ground truth for behavior:
[`../operator-playbook.md`](../operator-playbook.md), [`../cli.md`](../cli.md),
[`../architecture.md`](../architecture.md).

## Product truths every workflow must respect

- The deterministic CLI (`isaac validate | export | audit | new-id`) is the **only** truth
  authority. The UI wraps it; it never re-decides validity.
- Export is **doubly gated**: no-guessing draft checks, then official ISAAC v1.05 schema on the
  produced record. If either fails, **nothing is written**. There is no override flag; the UI must
  not invent one.
- Missing scientific values are **never** invented. A blocker is the product working as intended —
  present it as such, not as an error.
- Every finalized field carries **evidence or an explicit user confirmation**. The UI must be able
  to show that trail for any value it displays.
- Audit reports **evidence coverage**, not a re-vote on validity. Warnings are **advisory and
  non-gating**. Graphify and the assistant **explain and navigate** — they never validate.
- Real / private data is **not supported** and upload is not production-ready. Only the synthetic
  demo and structured local files are safe today.

---

## Workflow A — Synthetic demo (the safe, complete happy path)

This is the flow to build first. Every step maps to something that exists and passes today. The
canonical run is `.venv/bin/python scripts/run_synthetic_demo.py`; see [`../demo.md`](../demo.md)
and [`../demo-script.md`](../demo-script.md).

1. **Choose / load the synthetic XANES demo.**
   - User sees: a clearly-labeled **synthetic, safe, fake** demo card on the dashboard.
   - System does: loads the committed synthetic inputs (structured `mock_campaign.csv`, archive
     `raw_scan_listing.txt`) — no real data touched. Wraps `scripts/run_synthetic_demo.py` /
     `extract/structured.py` + `extract/file_listing.py`.
   - Branch: nothing to fail here; the inputs are committed and byte-stable.

2. **Build the draft.**
   - User sees: extraction runs; a draft appears with fields, statuses, and per-field evidence.
   - System does: `build_draft` (`extract/draft_builder.py`) assembles the evidence envelope
     (`{value, status, evidence[]}`), `implicit[]` inferences, and `pending[]` blockers. Mirrors
     the `/isaac-draft` skill.
   - Branch: if inputs were empty, stop and prompt for files — never draft from nothing.

3. **Review extracted metadata + per-field evidence.**
   - User sees: 26 evidenced fields, each with a status chip (verified / inferred /
     needs_confirmation / missing) and a citation (e.g. `mock_campaign.csv`, `Sheet 'Sample',
     field=formula`, quote `CuO2`).
   - System does: renders the draft envelope read-only. No value is shown without its evidence.
   - Branch: a `needs_confirmation` or `missing` field routes forward to completion (step 5).

4. **See the missing-field blockers (the 5).**
   - User sees: a prominent but calm **blockers** panel — the record cannot export until these are
     resolved. The five, verbatim from `draft["pending"]`:
     1. sha256 of `…/xanes_reduction_v2.ipynb`
     2. sha256 of `…/CuO2_merged.xdi`
     3. sha256 of `…/raw/`
     4. point to the reduced spectrum (`.xdi`) so `measurement.series` can be built
     5. give at least one descriptor (e.g. XANES inflection-point energy + uncertainty)
   - System does: surfaces exactly `draft["pending"]` — nothing optional, nothing from memory.
   - Branch: this panel is the honest "not done yet" state, not a failure. Style accordingly.

5. **Apply completion answers.**
   - User sees: one question per blocker, batched. Enum fields (technique, environment, edge, …)
     show allowed values straight from the schema. "I don't know" is a first-class answer.
   - System does: `apply_answers` (`complete.py`) stores each reply as `user_confirmation`
     evidence **next to** the deterministic evidence, and removes the blocker from `pending`.
     Mirrors `/isaac-complete`. Never fabricates a sha256, URI, number, or descriptor.
   - Branch: "I don't know" leaves the field honestly missing; if the schema requires it, the
     record simply cannot finalize yet. Unanswered blocker → stays blocking.

6. **Export the official record.**
   - User sees: a single Export action; on success, two artifact cards (record + sidecar) and a
     green **PASS** verdict against v1.05.
   - System does: `isaac export <draft>` → `export_draft` (`export.py`), doubly gated. Writes
     `records/<ULID>.json` and `records/<ULID>.evidence.json`. Records are immutable via the CLI.
   - Branch (blocked, exit 1): draft-level failure → route back to completion (step 5);
     schema-mapping failure → the draft's field paths are wrong. Show the report; **do not** offer
     a hand-edit of the produced record and **do not** offer to weaken checks.

7. **View the evidence sidecar.**
   - User sees: each official JSON-path mapped to its source evidence; namespaced `assets:` /
     `descriptors:` / `implicit:` entries shown distinctly.
   - System does: renders `records/<ULID>.evidence.json`. The record stays schema-clean; the
     sidecar preserves provenance. Label it an **assistant convention, not an official ISAAC
     standard**.

8. **Validate.**
   - User sees: **PASS — valid against official ISAAC schema v1.05** as the hard verdict.
   - System does: `isaac validate <record> --official` → `official.py` (jsonschema).
   - Branch (FAIL): list the exact schema errors; the verdict is authoritative and not softenable.

9. **Audit.**
   - User sees: `evidence 26/26`, `0 schema errors` — the evidence trail is intact.
   - System does: `isaac audit --records-dir …` → `audit.py` (re-validate + sidecar coverage).
   - Branch: any dangling sidecar path → coverage < N/N; surface which path failed to resolve.

10. **View advisory warnings.**
    - User sees: exactly one advisory chip — `[NO_LINKS]` (no optional `links` block), clearly
      marked **advisory / non-gating**. Verdict stays PASS.
    - System does: `isaac validate <record> --official --warnings` → `portal_warnings.py` (local
      heuristic seam). Not upstream portal parity.
    - Branch: warnings never change the verdict or block export.

11. **Ask the assistant / project memory.**
    - User sees: an assistant panel to ask "where did the beamline come from?", "which files
      implement export?", "what does NO_LINKS mean?" — each answer cites its source.
    - System does: routes per [`../query-cookbook.md`](../query-cookbook.md) — schema / audit /
      git / Graphify / files. Graphify only navigates; truth questions go to the CLI.
    - Branch: stale / missing graph → answer from files, disclose it (see Workflow D).

---

## Workflow B — Upload intake (FUTURE, gated, local-only first)

> **FUTURE / not implemented.** Only **structured** parsing exists today (`.csv` / `.xlsx` via
> `extract/structured.py`, archive listings via `extract/file_listing.py`). Extraction of
> unstructured artifacts is **designed, not built**. Real / private data is **not supported** and
> needs explicit written approval — see [`../operator-playbook.md`](../operator-playbook.md) §10.
> The UI must gate this whole flow behind a governance screen and a synthetic-only default.

1. **Upload / select metadata files.**
   - User sees: an intake panel that accepts only synthetic / local structured files; a persistent
     banner that real experiment data is not permitted here.
   - System does (today): structured extraction only. Anything unstructured is out of scope.
   - Branch: a file that looks real / private → **governance intercept** (Workflow D5), not a draft.

2. **Extract / build draft.** Same as A2, but on user files. `needs_confirmation` will be common.

3. **Review field evidence.** Same as A3 — every value shows its locator + quote.

4. **Complete missing values.** Same as A5 — `apply_answers`, evidence-stored confirmations.

5. **Validate / audit / export.** Same as A6–A10 — the identical deterministic gate. The UI must
   not relax any check because the input was user-supplied.

---

## Workflow C — Claude-assisted (assistant explains, human decides)

The assistant is an **optional helper layered over** the same deterministic core. See
[`../claude-workflow.md`](../claude-workflow.md) and
[`ai-assistant-and-graphify.md`](ai-assistant-and-graphify.md).

1. **Assistant explains what happened.** After any step, the user can ask "what did that do?" The
   assistant narrates the draft, the blockers, the verdict — always pointing back to the artifact
   or CLI output, never asserting a new verdict.
2. **User stays responsible for scientific confirmation.** The assistant may **propose** a value
   *with cited evidence*, but the user must **explicitly confirm**; the confirmation is stored as
   `user_confirmation` evidence. The assistant cannot invent scientific values.
3. **AI / Graphify navigate docs + evidence.** "Where is the sidecar explained?", "which files
   implement audit?" — routed to docs/code/graph, each answer labeled with its source.
4. **Deterministic CLI/backend stays truth.** The assistant never marks a record valid/invalid,
   never mutates a record, never overrides validation, audit, or the export gate. If the assistant
   and the CLI disagree, the CLI wins and the UI says so.

---

## Workflow D — Errors, fallbacks, and governance intercepts

Each of these is a legitimate, expected state. Design them as honest, calm, protective — not as
crashes. Details: [`../query-safety-checklist.md`](../query-safety-checklist.md),
[`../graphify-workflow.md`](../graphify-workflow.md), [`../portal-warnings.md`](../portal-warnings.md).

1. **Validation failure (FAIL).** Export blocked, nothing written. Show the exact schema errors and
   route: draft-level → completion; mapping-level → fix draft field paths. Never soften the verdict.
2. **Missing evidence (audit).** Coverage < N/N or a dangling sidecar path. Name the unresolved
   path; the record is schema-valid but its evidence trail is incomplete — distinct from a FAIL.
3. **Warnings present.** One or more `⚠ [CODE]` chips (e.g. `[NO_LINKS]`,
   `[QC_NONVALID_WITHOUT_EVIDENCE]`). Advisory, non-gating; verdict unchanged. Absence of warnings
   is **not** upstream portal sign-off.
4. **Graphify stale / missing.** Freshness helper prints `fresh` / `stale` / `missing`
   (exit `0` / `1` / `2`). Stale or missing → show the freshness indicator, answer from files, and
   disclose the memory layer was unavailable. **Never fabricate graph output.**
5. **Unsupported real-data upload (governance intercept).** If a user tries to load real / private
   / sensitive data, block the intake, explain that real data needs explicit written approval, and
   route to data governance. Nothing is extracted, indexed, or sent to any model.
