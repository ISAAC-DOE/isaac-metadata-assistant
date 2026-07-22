# Technical architecture proposal — future ISAAC web UI

**Status: DRAFT PROPOSAL. Nothing in this document is implemented.** No application code, config,
dependency, or scaffolding exists or is added by this document. Every stack choice, endpoint, and
data object below is a *paper design* for a future web UI that would wrap the existing deterministic
core **without changing its behavior**. Anything here is pending mentor approval before any code is
written.

Verified against the package at commit `af89217` (105 tests passing). All function and module names
cited below were read from the source; where a capability the UI would need does **not** yet exist in
the core, this document says so explicitly (see §11, Open technical questions) rather than inventing a
seam.

---

## 1. Goals and non-goals

**Goals**

- Give a future operator a browser UI for the same draft → validate → complete → export → audit flow
  that `.venv/bin/isaac` and the Claude skills drive today.
- Keep the deterministic core (`isaac_records`) the **only** authority on validity, export shape, and
  audit truth. The UI is a presentation and orchestration layer, nothing more.
- Local-first and synthetic-first: runs on a lab/dev machine, against synthetic fixtures, with no
  cloud dependency and no external network calls in v1.
- Reuse the existing library functions in-process wherever possible instead of shelling out, so the
  UI inherits the exact same verdicts the CLI produces.

**Non-goals**

- This document does **not** implement anything. No dependency is added to `pyproject.toml` now; the
  current runtime deps stay exactly `jsonschema>=4.21`, `python-ulid>=2.0`, `openpyxl>=3.1` (dev:
  `pytest>=8`). Future deps in §2 are listed as *future*, not added.
- No change to the schema, validators, export transform, audit, or CLI surface.
- Not in scope: MCP server, official portal parity, real/sanitized-data ingestion, electrochemistry
  or simulation domains, multi-user auth, cloud hosting. Those remain mentor-gated (see CLAUDE.md §15).

---

## 2. Recommended stack (proposal, pending approval)

**Frontend: React + Vite, with a high-quality component system.**

- Vite for a fast local dev server and a static build that a lab machine can serve offline.
- A mature component/design system (e.g. shadcn/ui + Tailwind, or Radix primitives) so evidence
  tables, validation reports, and blocker prompts get accessible, product-grade UI without bespoke
  CSS. Exact library is a later decision; the point is "use a real system, not ad-hoc styles."
- The UI is a thin client: it renders core outputs and posts user confirmations. It holds no
  validation logic of its own.

**Backend: FastAPI wrapping `isaac_records` as an imported library.**

Justification, briefly:

- The core already exposes clean, pure, in-process functions returning dataclasses/dicts
  (`validate_official`, `validate_draft`, `export_draft`, `audit_records`, `apply_answers`,
  `portal_warnings`, `build_draft`). A Python backend can `import isaac_records` and call these
  directly, so the UI gets **byte-identical** verdicts to the CLI — no reimplementation, no drift.
- FastAPI gives typed request/response models and auto-generated OpenAPI docs, which suits a
  small, well-defined endpoint set.
- It binds to localhost by default (see §8), matching the local-first goal.

This is a recommendation, not a decision. A mentor could equally choose to have the backend shell out
to `.venv/bin/isaac` for maximum "same path as the operator" fidelity; §3 notes where shelling out is
actually preferable (Graphify).

---

## 3. How the backend calls the existing core

The backend reuses the **same library functions the CLI calls internally** (see `cli.py` imports),
not a parallel implementation. Real, verified entry points:

| Concern | Core function (module.function) | Signature (real) |
|---|---|---|
| Draft no-guessing check | `draft_validator.validate_draft` | `(draft: dict) -> DraftReport` |
| Official schema check | `official.validate_official` | `(record: dict, root: Path) -> OfficialReport` |
| Export (schema-gated) | `export.export_draft` | `(draft, root, *, record_id=None, now=None) -> ExportResult` |
| Audit a records dir | `audit.audit_records` | `(records_dir: Path, root: Path) -> list[tuple[str, OfficialReport, tuple]]` |
| Render audit text | `audit.render_audit` | `(results) -> str` |
| Advisory warnings | `portal_warnings.portal_warnings` | `(record: dict) -> PortalWarningReport` |
| Apply blocker answers | `complete.apply_answers` | `(draft: dict, answers: dict) -> dict` |
| Build draft from files | `extract.draft_builder.build_draft` | `(structured_path, listing_path) -> dict` |
| Mint a record id | `ids.new_record_id` | `() -> str` |

Notes on wiring:

- `export_draft` already returns an `ExportResult(ok, record, sidecar, draft_report, official_report)`
  **without writing to disk** — the CLI's `cmd_export` is what writes files and enforces "records are
  immutable" (`if record_path.exists(): block`). A FastAPI export endpoint would call `export_draft`
  in-process, then apply the same write-and-immutability logic against a UI-managed workspace dir
  (§6). The immutability guard currently lives in `cli.cmd_export`, not in `export.py` — see §11.
- Validation endpoints read the dataclasses directly: `DraftReport.errors` is a list of
  `(where, msg)` tuples with `.ok`; `OfficialReport.errors` is a list of `OfficialError(path, message)`
  with `.ok`. The backend serializes these to JSON itself (there is no `.to_dict()` today — §11).
- `portal_warnings` returns a `PortalWarningReport` that deliberately exposes **no** `.ok`/`.valid`/
  `.errors` — only `.warnings` (tuples of `PortalWarning(code, where, message)`) and `.advisory=True`.
  The API must preserve this: warnings are a separate, non-gating channel (§9).
- **Demo runner endpoint** wraps `scripts/run_synthetic_demo.py` (`main()`, `--out` default
  `/tmp/isaac-demo`). It regenerates the committed sample record
  `01JQZ0SYNTHXANESDEMO000000.json` + `.evidence.json` via `build_draft → apply_answers →
  export_draft`. The backend can call the script's `main()`/inner functions or subprocess it into a
  workspace dir; output must stay byte-identical to `docs/samples/`.
- **Graph freshness endpoint** wraps `scripts/check_graphify_freshness.py` (`check(root) -> "fresh" |
  "stale" | "missing"`, exit `0 | 1 | 2`). Pure stdlib, mtime-only, no Graphify required — safe to
  call in-process or subprocess.
- **Graphify queries shell out** to the external `graphify` CLI (`graphify query`, `graphify explain`,
  `graphify path`) as a clearly-degradable optional service. There is **no** Python Graphify API in
  this repo; the backend must treat Graphify as absent-by-default and degrade gracefully when the CLI
  or `graphify-out/graph.json` is missing (memory plane only — never a verdict; see §9).

---

## 4. Proposed API surface (future)

All paths are `/api/...`, JSON in/out. "v1" = first local UI; "future" = mentor-gated. This is a
proposal; nothing is built.

| # | Method | Path | Wraps (core) | Request → Response summary | Tier |
|---|---|---|---|---|---|
| 1 | POST | `/api/validate/draft` | `validate_draft` | draft JSON → `{ok, errors[], warnings[]}` | v1 |
| 2 | POST | `/api/validate/official` | `validate_official` | record JSON → `{ok, errors[{path,message}]}` | v1 |
| 3 | POST | `/api/warnings` | `portal_warnings` | record JSON → `{advisory:true, warnings[{code,where,message}]}` | v1 |
| 4 | POST | `/api/export` | `export_draft` + workspace write | draft JSON `?record_id` → `{ok, record, sidecar, reports}` | v1 |
| 5 | POST | `/api/complete/apply` | `apply_answers` | `{draft, answers}` → completed draft (`pending[]` shrinks) | v1 |
| 6 | GET | `/api/audit` | `audit_records`+`render_audit` | `?records_dir` → `{records[{name,ok,errors,evidence}], text}` | v1 |
| 7 | POST | `/api/new-id` | `ids.new_record_id` | (none) → `{record_id}` | v1 |
| 8 | POST | `/api/demo/run` | `run_synthetic_demo.main` | `{out_dir?}` → `{record, sidecar, steps[]}` | v1 |
| 9 | GET | `/api/graph/freshness` | `check_graphify_freshness.check` | (none) → `{status:"fresh\|stale\|missing"}` | v1 |
| 10 | GET | `/api/workspace/records` | filesystem (workspace) | list drafts/records in the UI workspace | v1 |
| 11 | GET | `/api/records/{id}` | filesystem read | fetch one record + its `.evidence.json` sidecar | v1 |
| 12 | GET | `/api/schema` | `official.schema_path` read | vendored v1.05 schema for form hints/vocab | v1 |
| 13 | POST | `/api/graph/query` | `graphify` CLI (subprocess) | `{question}` → `{leads[], sources[], disclaimer, freshness}` | future |
| 14 | POST | `/api/extract` | **new seam** (see §11) | uploaded artifacts → draft | future |
| 15 | POST | `/api/draft/build` | `build_draft` | `{structured_path, listing_path}` (synthetic fixtures) → draft | future |

Endpoints 13–15 are explicitly future-gated. `/api/extract` (unstructured upload → draft) has **no
backing function today** and is the largest missing seam (§11). `/api/draft/build` exists as a
function but only over structured CSV + listing files, so it stays behind the synthetic-only gate.

---

## 5. Data objects (grounded in the real artifacts)

Shapes below are taken from the real code and `docs/samples/`. They become the API's JSON contracts.

**Draft envelope** (authoring artifact; produced by `build_draft`, consumed by `validate_draft`,
`apply_answers`, `export_draft`):

```json
{
  "fields": { "<official.dotted.path>": {
      "value": "...", "unit": "eV|null",
      "status": "verified|inferred|needs_confirmation|missing|rejected",
      "evidence": [ { "source_type": "spreadsheet", "source_file": "...", "locator": "...", "quote": "..." } ] } },
  "implicit": [ "absorbing_element", "edge" ],
  "assets": [ { "asset_id": "...", "content_role": "...", "uri": "...", "sha256": "..." } ],
  "pending": [ { "kind": "sha256|series|descriptor", "question": "...", "content_role": "..." } ]
}
```

`pending[]` entries are the **export blockers** the UI surfaces as questions. `status` values and the
observed `source_type` set (`document`, `spreadsheet`, `screenshot`, `web_form`, `file_listing`,
`user_confirmation`, plus `derivation`) come straight from `draft_validator.py`.

**Completion answer** (posted to `/api/complete/apply`, applied by `apply_answers`): a map keyed by
blocker (e.g. `sha256`, `series`, descriptor), each answer stored as a `user_confirmation` evidence
entry `{source_type, question, answer, timestamp}`. Unanswered blockers stay in `pending[]`, so export
stays blocked (no invention).

**Official record** (output of `export.transform`, validated by `validate_official`; real top-level
structure from `docs/samples/01JQZ0SYNTHXANESDEMO000000.json`):

```json
{
  "isaac_record_version": "1.05", "record_id": "<ULID>", "record_type": "evidence",
  "record_domain": "characterization", "source_type": "facility",
  "system": { "facility": {...}, "technique": "HERFD-XAS", "configuration": {...}, "domain": "experimental" },
  "timestamps": {...}, "sample": {...}, "context": {...}, "measurement": {...},
  "assets": [...], "descriptors": { "outputs": [...] }, "attribution": {...}
}
```

Top-level keys (verified): `isaac_record_version, record_id, record_type, record_domain, source_type,
system, timestamps, sample, context, measurement, assets, descriptors, attribution`. No evidence
envelope — the record is schema-clean; evidence lives only in the sidecar.

**Evidence sidecar** (output of `export.build_sidecar`; real shape from
`...evidence.json`): maps official JSON paths → evidence entry lists.

```json
{
  "record_id": "01JQZ0SYNTHXANESDEMO000000", "schema_version": "...", "generated_utc": "<iso8601>",
  "evidence": {
    "system.facility.facility_name": [
      { "source_type": "spreadsheet", "source_file": "mock_campaign.csv",
        "locator": "Sheet 'Campaign Info', field=facility_name", "quote": "SSRL" } ]
  }
}
```

**Validation result** (from `DraftReport` / `OfficialReport`): `{ok: bool, errors: [...], warnings:
[...]}`. Draft errors are `(where, msg)` pairs; official errors are `{path, message}`. `ok` is a hard
PASS/FAIL and drives export gating.

**Audit result** (from `audit_records` + `render_audit`): per record `{name, ok, errors[{path,
message}], evidence: "resolved/total", dangling[]}` plus the rendered text block and a
`{audited, failing}` summary. Evidence coverage is the sidecar `resolved/total` count from
`_sidecar_coverage`.

**Warning result** (from `PortalWarningReport`): `{advisory: true, warnings: [{code, where,
message}]}`. Deliberately has **no** `ok`/`valid`/`passed` field — advisory, non-gating.

**Graph / query result** (future; from the `graphify` CLI): `{leads: [...], sources: [...],
freshness: "fresh|stale|missing", disclaimer: "memory plane — not a validity verdict"}`.

---

## 6. Artifact storage for the local demo

- The UI operates on a **UI-managed workspace directory** — its own equivalent of the CLI's
  `--records-dir` / demo `--out`. Default candidate: a per-session dir under the user's data path or a
  configurable `ISAAC_UI_WORKSPACE`. This mirrors how `cmd_export` and `run_synthetic_demo.py` accept
  an explicit output dir.
- **Ephemeral**: drafts in progress, completion answers, demo output (`/tmp/isaac-demo`-style),
  validation/audit responses. These can be regenerated deterministically and need not persist.
  > **Deployment note (2026-07-21, P27.0):** on the hosted Railway service the workspace is **not**
  > ephemeral — `ISAAC_UI_WORKSPACE` points at a persistent Railway volume mounted at
  > `/data/isaac-workspace`, so experiment state survives restarts/redeploys. This bullet describes the
  > design-era regeneration property, not hosted persistence. See `docs/deployment.md`.
- **Persisted (only on explicit user action)**: an exported record + sidecar the user chooses to keep,
  written into the workspace dir. Exported filenames follow the core convention `<ULID>.json` +
  `<ULID>.evidence.json`.
- **Never** write into the repo `records/` directory except by explicit, confirmed user action, and
  never overwrite an existing record (honor the CLI's immutability rule: refuse if the target file
  exists).
- **Never** write to or mutate `docs/samples/` — those are committed golden artifacts the demo is
  checked against.

---

## 7. What NOT to persist

- No real or private experimental data (synthetic-only by default — see `docs/data-governance.md`).
- No secrets, API keys, or credentials on the server or in the workspace.
- No telemetry / analytics by default. No usage beacons.
- No cloud storage in v1. Everything stays on the local disk under the workspace dir.
- No LLM/model API keys held server-side without explicit mentor approval. The deterministic core
  needs no keys; extraction/review that would need a model is future-gated.

---

## 8. How to avoid real-data risk (backend-level governance)

- **Local-only binding by default**: bind the API to `127.0.0.1`; do not expose on `0.0.0.0` without
  explicit opt-in. Local-first means no remote listener in v1.
- **No external calls in v1**: the deterministic core makes none; the backend adds none. Graphify is
  the only optional subprocess and is local.
- **Upload disabled or synthetic-marked in v1**: `/api/extract` (unstructured upload) is future-gated.
  Any file intake in v1 is limited to synthetic fixtures and clearly labelled as such.
- **Graphify indexing excluded for user uploads by default**: the freshness helper already excludes
  `examples/`, `graphify-out/`, `.venv/`, `.git/`, caches (`IGNORED_DIRS`); a UI workspace holding
  user files must likewise be excluded from any graph indexing unless the user explicitly opts in.
- Governance echoes CLAUDE.md §6: treat anything the user drops in as potentially sensitive; never ship
  it to an external service.

---

## 9. Safety constraints mapping (product truth → architectural enforcement)

| Product truth | Architectural enforcement |
|---|---|
| Warnings are advisory, non-gating | `/api/warnings` is a **separate** endpoint; its response has no `ok`/verdict field and never feeds export/validation gating. Mirrors `PortalWarningReport` having no `.ok`. |
| Graphify never validates | Graph endpoints (13) return `leads`/`sources` + a `disclaimer` field and a `freshness` flag — **never** a validity verdict. Graphify is import-free in the truth path and stays that way. |
| No invention / no guessing | Completion (5) only applies answers explicitly present in the user payload; unanswered `pending[]` blockers remain and keep export blocked. The core's `validate_draft` still gates. |
| Export is schema-gated | `/api/export` returns `ok:false` with the failing `draft_report`/`official_report` unless **both** no-guessing and official schema pass — exactly `export_draft`'s behavior. |
| Official schema is the only authority | `/api/validate/official` and export both call `validate_official` against the vendored `schema/isaac_record_v1.json` (v1.05); the UI adds no rules. |
| Records are immutable | Export refuses to overwrite an existing `<ULID>.json` (CLI's `record_path.exists()` guard, re-applied at the workspace write step). |
| Deterministic core untouched | Backend imports and calls the core; it does not fork, patch, or wrap validation logic. Same functions the CLI uses. |

---

## 10. Future deployment considerations

- **Local / lab-machine first**, always. The default deployment is "run the FastAPI backend + a static
  Vite build on the operator's own machine."
- Anything beyond local — a shared server, multi-user hosting, cloud storage, remote Graphify — is
  **mentor-gated** and out of scope for this proposal.
- If a shared deployment is ever approved, data governance (§7–8) and an auth story (§11) must be
  designed first; they are not assumed here.

---

## 11. Open technical questions

Honest list of things that would need a decision or a **new seam** in the core. Where a function does
not exist today, it is named as a gap, not pretended into existence.

1. **Unstructured-upload extraction seam is missing.** `build_draft(structured_path, listing_path)`
   ingests only a structured CSV + a file listing. There is **no** core function that turns an
   arbitrary uploaded artifact (PDF/image/xlsx/notes) into draft fields with evidence. `/api/extract`
   would require a new, reviewed extraction seam (likely LLM-assisted) — a significant future design,
   not a wrapper over existing code.
2. **Structured serialization of reports.** `DraftReport`, `OfficialReport`, and `PortalWarningReport`
   expose `.render()` (human text) and their fields, but no `.to_dict()`/JSON serializer. A small,
   read-only serialization layer in the backend (not a core change) is needed — or a mentor-approved
   `to_dict()` added to the core. Decide which.
3. **Where the immutability + workspace-write guard lives.** The "don't overwrite an existing record"
   rule currently sits in `cli.cmd_export`, not in `export.py`. The backend must either duplicate it
   or a shared helper is lifted into the core. Duplicating is safe short-term; lifting is cleaner but
   touches the truth path and needs approval.
4. **Process model for the demo / long-running work.** Should `/api/demo/run` and future extraction be
   synchronous request/response or a background job queue? v1 demo is fast and deterministic, so sync
   is likely fine; extraction later probably needs jobs. Decide before adding extraction.
5. **How the Claude skills map to a backend.** Today `/isaac-draft`, `/isaac-complete`, `/isaac-query`,
   etc. are Claude skills, not CLI subcommands. A UI "assistant" panel would need a defined bridge to
   those skills (or a subset reimplemented as endpoints). Scope and ownership of that bridge is open.
6. **Auth story if ever multi-user.** v1 is single-user localhost with no auth. Any shared deployment
   needs an auth design (§10) — currently undefined and mentor-gated.
7. **Sidecar convention pending mentor decision (D1).** The evidence sidecar is an assistant audit
   artifact, not (yet) an official ISAAC convention. If mentors ratify or change it, the sidecar data
   object (§5) and the `/api/records/{id}` response shape change accordingly.
8. **Graphify availability.** Graph endpoints must degrade gracefully when the `graphify` CLI or
   `graphify-out/graph.json` is absent. The freshness helper handles "missing" already; the query
   endpoint needs an explicit "unavailable" response contract.

---

*End of proposal. Reminder: nothing above is implemented; no dependency is added; the deterministic
core and its 105 passing tests are unchanged. Implementation, if any, starts only after explicit
approval.*
