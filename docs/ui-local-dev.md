# Local UI prototype — developer guide

`apps/` is a **local-first, synthetic-only web UI prototype** over the existing
deterministic `isaac_records` core (built in Phase 19). **This is not a production
application.** It is a reviewable, runnable front end that makes the CLI's state
visible; the CLI and the deterministic core remain the source of truth for
validity, exportability, and completeness. If anything in this doc conflicts with
`docs/ui-handoff/` (the design source) or with the code under `apps/`, the code
wins.

For the design intent behind these screens, see `docs/ui-handoff/README.md` and
the rest of `docs/ui-handoff/`. This doc only covers running the prototype
locally and what it honestly does and does not do.

## What this is not

Read this before demoing it to anyone:

- **Not production.** No auth by default; binds `127.0.0.1` when run locally.
  A protection-gated synthetic demo deployment exists — see
  [`docs/deployment.md`](deployment.md). Local runs remain the primary flow.
- **Real or private data is not approved for this prototype.** The backend
  blocks every upload attempt with `403` (`POST /api/uploads`); only the two
  committed synthetic fixtures (`tests/fixtures/synthetic/mock_campaign.csv`,
  `tests/fixtures/synthetic/raw_scan_listing.txt`) are ever read or previewed.
- **Portal submission and portal-validator parity are not built.** The upstream
  `portal/validation.py` is not vendored. Zero advisory warnings in this UI is
  **not** the same as ISAAC portal acceptance — the export button writes local
  JSON artifacts only, under the workspace directory's per-experiment
  `records/` folder (`<record_id>.json` + `<record_id>.evidence.json` —
  never the repo's own `records/`), nothing is submitted anywhere.
- **Graphify is a memory/query layer, never a validator.** The UI's "Memory:
  Available / Unavailable" chip (`GraphStatusChip`) is status-only context about
  the optional project-memory graph. It never renders a verdict and never gates
  anything.
- **The assistant is advisory and subordinate.** It never renders `PASS`/`FAIL`
  or a validity claim; deterministic validation, evidence, and audit are the
  authority. In this prototype the assistant panel shows **static,
  source-labeled sample answers** (`apps/web/src/lib/assistant.ts`) — every
  reply and suggested-question answer names the deterministic source it is
  grounded in. **Freeform chat is not wired**; only the pre-written suggested
  questions are clickable.
- **Validation, evidence audit, and advisory warnings are three separate
  signals**, always rendered in three separate, labeled components — never
  merged into one badge:
  - **Validation** — the hard `PASS`/`FAIL` verdict against official ISAAC
    v1.05 (`isaac validate --official`).
  - **Evidence audit** — coverage (`N/N` resolved JSON-paths), informational,
    never a verdict (`isaac audit`).
  - **Advisory warnings** — non-gating soft notes (e.g. `[NO_LINKS]`) from a
    local heuristic seam; they never block export and are not upstream portal
    parity.
- **The evidence sidecar (`.evidence.json`) is an assistant convention, not an
  official ISAAC standard.** The official record stays schema-clean; the
  sidecar is where per-field provenance survives after export.
- **No telemetry.** Nothing phones home. Local and offline only.
- **Localhost only.** The backend binds `127.0.0.1:8000`; CORS allows only the
  Vite dev origins (`http://localhost:5173`, `http://127.0.0.1:5173`).
- **No license decided.** Same status as the rest of the repo — see the
  README's License & provenance section.
- **Existing CLI usage is unchanged.** `isaac validate | export | audit |
  new-id` behave exactly as before; the UI calls the same core functions
  in-process and gets byte-identical results.

## Navigation & chrome (Phase 22)

- **Brand mark is a real home link** — clicking it (`TopBar` → `Brand`) navigates back to
  **My Experiments**; it is not decorative.
- **Breadcrumbs are real links, not labels.** On record sub-surfaces (Complete, Evidence, Export)
  the record-title crumb links back to Review Record; on the record surface itself the current
  crumb is the non-link leaf. Reached workflow-spine steps (`WorkflowSpine`) link back to their
  surface — only locked (not-yet-reached) steps stay non-interactive.
- **Help is a real, static popover** (`HelpPanel`) — a small honest explainer of the five pipeline
  steps, opened from the Help button, closable via Escape or click-outside. It is not chat and not
  search.
- **The "Memory: Available / Unavailable" chip is live** — it reflects `GET /api/graph/status`, not
  a hardcoded placeholder; still status-only and never a verdict.
- **Search is a real ⌘K command palette; there is still no user/account chip.** An earlier iteration
  of the chrome had placeholder versions of both; they were removed (Phase 22D) because the prototype
  then had neither real search nor user accounts, and a fake affordance would misrepresent that.
  Phase 26 shipped a real, API-backed search (`SearchDialog`, opened with ⌘K); user accounts remain
  absent, so no account chip is shown.

## Prerequisites

- Python virtualenv already set up per the repo root `README.md` Quickstart
  (`.venv/`).
- Node.js (LTS) and `npm` for the frontend.

## Install

```bash
# Backend: adds FastAPI/uvicorn to the existing venv (extends the [dev] extra)
.venv/bin/pip install -e '.[dev,api]'

# Frontend
cd apps/web
npm install
```

## Run the backend

```bash
.venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

Smoke-test it:

```bash
curl -s http://127.0.0.1:8000/api/health
```

The backend persists UI state (experiments, exported records/sidecars) under a
workspace directory **outside the repo**: `ISAAC_UI_WORKSPACE` (default
`/tmp/isaac-ui-workspace`). It is a thin wrapper — 21 endpoints under
`/api/*` (17 experiment/pipeline endpoints plus 4 read-only `/api/memory/*`
project-memory endpoints) — that imports and calls the same `isaac_records` functions the CLI
uses (`draft_validator`, `official`, `export`, `audit`); it adds no validation
logic of its own. See `apps/api/README.md` for the full endpoint list and
governance notes.

## Run the frontend

In a second terminal:

```bash
cd apps/web
npm run dev
```

Open `http://localhost:5173`. The frontend makes direct cross-origin fetches
to the backend at `http://127.0.0.1:8000`, allowed by the backend's CORS
allowlist (`apps/web/vite.config.ts` has no `server.proxy`); if the backend is
not running, screens show an honest "backend not running" state rather than
silently failing.

## Browser demo walkthrough

This walks the same synthetic happy path as `scripts/run_synthetic_demo.py`
(fictional year-2099 CuO / Cu K-edge XANES session), driven entirely through
the browser and the live backend — every step below calls a real endpoint and
shows real results, nothing is staged client-side.

1. **My Experiments** (`/experiments`) — the home queue, grouped by status
   (Needs Attention / In Review / Ready to Export / Done). Empty on first run.
   Click **Run Synthetic Demo** or **New Record**.
2. **Load Materials** (`/load`) — click **Run Demo** under "Run the Synthetic
   Demo". This calls `POST /api/demo/run`, which assembles the evidenced draft
   from the two committed synthetic fixtures and returns the pipeline steps
   the CLI would produce. The other on-ramp, **Load Local Structured Files**,
   is present but always refused: it calls the governance seam, which returns
   `403` and the refusal is shown verbatim (`Blocked by governance.`) — nothing
   is read or uploaded. When the draft finishes, click **Open the Record**.
3. **Review Record** (`/record/:id`) — the core workbench. Grouped draft
   fields on the left/main, each selectable to load its evidence
   (`source_file`, `locator`, `quote`) in the right panel above the
   (visually subordinate) assistant panel. A banner lists the fields the
   system refuses to guess (hashes, spectrum pointer, a descriptor). The
   bottom status bar shows the three signals — Validation / Coverage /
   Advisory — each in its own segment, pre-export ones marked as a dry-run
   note rather than a verdict. Click **Review & Answer**.
4. **Complete Missing Fields** (`/record/:id/complete`) — one blocker at a
   time. Confirming an answer `POST`s it and the backend returns the shrunken
   pending list; **"I don't know — leave honestly missing"** sends nothing and
   the field stays honestly missing (export stays gated until every field is
   confirmed or explicitly left missing). Once all are resolved, click **Go to
   Ready to Export**.
5. **Evidence & File Preview** (`/record/:id/evidence`) — the evidence trail;
   selecting an entry highlights the exact cited line in the real synthetic
   source file (via `GET /api/experiments/{id}/source-preview` and
   `GET /api/experiments/{id}/artifacts`). The sidecar is labeled "assistant
   convention — not official" wherever it appears.
6. **Ready to Export** (`/record/:id/export`) — pre-export this is a
   readiness/gate view (dry-run only, never the reserved `PASS`/`FAIL` chip).
   Once every blocker is resolved and the dry-run would pass, click **Export
   Official Record + Sidecar**. This performs the real, gated export
   (`POST /api/experiments/{id}/export`) and writes the local record +
   evidence sidecar under the workspace. After export, the real verdict
   (`PASS`/`FAIL` against ISAAC v1.05), coverage badge, and advisory chip are
   shown, plus **View** / **Download** for both artifacts. Exported records are
   immutable — re-exporting the same id returns `409` and the UI shows an
   immutability message, never an overwrite.

Two additional nav destinations (**Governance & Safety**, **Settings**) are
intentionally minimal placeholders in this first build — not wired to live
data beyond static explanatory copy and the governance banner, and out of the
critical demo path above. **Project Memory** is a third nav destination and,
since Phase 24, is a real read-only surface — see the next section.

## Project Memory (Phase 24)

The **Project Memory** nav destination (`/memory`) is a real, read-only
browsing surface over the `/api/memory/*` endpoints and the additive
`GET /api/graph/status` fields — not a placeholder. It is a **memory plane**:
metadata/provenance only, never a validator, and it never authorizes export.

- **Status card** — live graph figures from `GET /api/graph/status` (node /
  edge / community / indexed-file / concept counts, built-at commit) plus three
  separately-honest freshness axes (P24.10): Snapshot Integrity
  (Verified/Malformed/Unsupported/Unknown), Memory Policy (Current/Out of
  date/Unknown), and Indexed Sources (Current/Out of date/Unknown, scoped to
  "proven in CI over only the files already in the snapshot"). Locally these
  come from a live `graphify-out/` graph; on the hosted demo they come from the
  committed sanitized snapshot (P24.9). Missing/unreadable artifacts render an
  honest unavailable panel — not a fabricated zero state — and none of these
  axes is ever a pass/fail token.
- **Source Index** — the served-file allowlist (`GET /api/memory/files` /
  `GET /api/memory/file`), grouped by kind (Code / Documents / Other), with
  per-file provenance (rationale, related leads). No file contents are
  served, and there is no inline search box on this screen itself — search
  is the global ⌘K palette, not per-screen.
- **Concept Lookup** — the curated concepts (`GET /api/memory/concepts` /
  `GET /api/memory/concepts/{id}`), browsable as an accordion showing anchor
  source, community, and related leads. Today all 19 curated concepts have
  zero recorded edges in the graph, so every concept detail honestly reads
  "no recorded leads for this concept in the current graph" rather than
  implying findings that don't exist.

Everything on this screen is a lead to verify, framed as memory/navigation —
never a validation result. See
[`docs/project-memory-map.md`](project-memory-map.md) for the full guardrails
(served allowlist, path-traversal guard, honest degraded states, and the
committed sanitized-snapshot delivery for the hosted demo).

## Tests and build

```bash
# Python (repo root) — deterministic core + API tests
.venv/bin/pytest -q

# Reproduce the synthetic demo used by the UI's "Run Synthetic Demo" on-ramp
.venv/bin/python scripts/run_synthetic_demo.py

# Frontend
cd apps/web
npm test        # vitest
npm run build   # tsc -b && vite build
```

## Related docs

- `docs/ui-handoff/README.md` — the design handoff package this build
  implements a first slice of.
- `apps/api/README.md` — backend endpoint summary and governance notes.
- `apps/web/README.md` — frontend commands.
- `docs/data-governance.md` — the repo-wide synthetic-vs-real data rules this
  prototype inherits unchanged.
- `docs/ui-handoff/validation-audit-warning-model.md` — why validation,
  coverage, and advisory never collapse into one signal.
