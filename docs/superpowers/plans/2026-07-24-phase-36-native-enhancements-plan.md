# Phase 36 — Repository-Local Native Enhancements · Plan + Capability Matrix

**Status:** OPEN 2026-07-24 (authorized under the 2026-07-24 execution authorization). Base: org
canonical `main` @ `8a10ed5`.
**Owner:** orchestrator (Opus 4.8, ratified fallback for Fable 5).
**Scope guardrails:** repository-local only; **synthetic-only, deterministic, no LLM, no portal
dependency, no real data, no Postgres, no new secret, no `isaac-k8` change.** Preserve the truth core,
no-guessing, official-schema authority, evidence audit, export behavior, and the read-only/advisory
Assistant contract. Preserve the current **flat light-design IA**; **no sidebar item appears until its
destination is functional**; no duplicated record editor / validator authority / Assistant.

**Deploy model per slice:** fresh branch from org `main` → focused implementer → focused + full
relevant tests, tsc, Vite build, Docker PR smoke → independent Opus review (fix all Critical +
Important) → PR into `main` via **Create a merge commit** → GHCR image + Flux → verify image/tag →
**hosted QA is Krish-gated** (Authentik edge; not self-verifiable from this environment) → checkpoint +
slice report. Never squash/rebase/force; never push `main` directly; never manual `v*` tag.

---

## 1. Capability matrix (Phase 36.0)

Derived from the 2026-07-24 read-only app inventory (`path:line` evidence recorded in that audit).
Current app = React/Vite SPA (`apps/web`) with a **flat 4-item LeftNav** (My Experiments, Project
Memory, Governance & Safety, Settings) + nested record sub-routes; FastAPI (`apps/api/isaac_api`, one
`/api` router, base-path via `include_router(prefix=base)`); no frontend graph/viz dependency.

| Capability | Class | Evidence / destination |
|---|---|---|
| Deterministic truth core, official validation, evidence audit, export, CSV reconciliation | **Already exists (authoritative — do not duplicate)** | `src/isaac_records/*`, `schema/`; validate/audit/export in `ExportReadiness.tsx` |
| Read-only advisory Assistant (bounded, no-LLM) across 5 surfaces | **Already exists** | `AssistantPanel.tsx`; do not fork/duplicate |
| Project Memory (Overview / Sources / Concepts tabs) | **Already exists** | `ProjectMemory.tsx:46-56`; read-only memory plane |
| Assistant redundant resting placeholder card | **Immediate user-requested improvement → P36.1** | remove placeholder text + empty card chrome; keep live region |
| Project Memory **Graph** tab (served-file reference graph) | **Immediate user-requested improvement → P36.2** | new local tab in `ProjectMemory.tsx`; data from committed snapshot |
| Standalone **Validator** (upload JSON → official schema/vocab) | **Safe native enhancement → P36.3** | build into **Governance & Safety** (currently a stub — makes it functional); reuse authoritative validators |
| **API Documentation** (from real OpenAPI, base-path-correct) | **Safe native enhancement → P36.4** | FastAPI `/docs` exists but is unprefixed/root-only + unlinked; needs base-path-correct surface |
| **Help / About** (build commit, app + schema version, mode) | **Safe native enhancement → P36.4** | today split/partial (`HelpPanel` has no version; `LABELS.version` hardcoded); use `GET /api/graph/status` `deployed_app_commit` (rendered nowhere today) |
| **New Record** coverage audit + targeted gaps | **Safe native enhancement → P36.5** | `LoadMaterials.tsx` + record flow; **extend the one flow only where a schema-coverage gap is proven**; no 2nd form |
| **Schema & Vocabulary browser** (read-only) | **Safe native enhancement → P36.6** | absent today; source = official schema + canonical vocab files |
| **Workspace/System Overview** | **Optional → P36.7 (evaluate; likely defer/skip)** | absent; only build if the audit proves non-redundant value; local synthetic only, no identity/IP/fake analytics |
| Second record editor / second validator authority / second Assistant | **Duplicate to avoid** | forbidden by scope |
| Discovery, Ontology Editor, System Overview (real analytics), API Keys, roles, record consolidation | **Portal-dependent — NOT authorized** | require portal access + per-module audit (Phase 37) |
| Real SLAC data, durable persistence, Postgres, external LLM/assist-layer | **Real-data / infra-dependent — NOT authorized** | Phase 37 staged, credential-governed |

**Hardening items (H1–H3, §4):** remove `:latest` publication; pin GitHub Actions to SHAs;
`ApiKeyAuthMiddleware` retain/remove/defer decision.

---

## 2. IA & design constraints (binding for every slice)

- Keep the **flat LeftNav**; do not introduce portal-style sections (Research/Trust/Developer/Personal)
  — the app has never had them.
- **Functional-first:** a nav item or tab ships only when its destination works. P36.3 makes the
  Governance & Safety stub functional (Validator); P36.4 makes the Settings stub functional
  (Help/About + API-docs link); P36.2 adds a *tab* (not a nav item) inside Project Memory.
- Reuse the light design system (`tokens.css`, existing card/tab/badge patterns); no dark portal shell,
  no dense portal forms, no raw error dumps, no color-only meaning.
- Every new surface: keyboard-reachable, visible focus, accessible names, 200%-zoom usable,
  narrow-screen functional, reduced-motion respected.
- Every new backend endpoint: **GET-only, read-only, deterministic, same-origin, base-path-correct,
  bounded, no raw absolute paths, no secrets, no real/private data, tests included, honest on
  missing/stale input.** No general file-read endpoint.

---

## 3. Slice sequence

### P36.1 — Assistant empty-state cleanup (implementer: Sonnet 5; reviewer: Opus 4.8)
Remove the redundant resting placeholder `ASSISTANT_EMPTY_STATE` ('Ask a question or choose a suggested
prompt.', `lib/assistant.ts:72`) rendered at `AssistantPanel.tsx:879-888`. **Critical a11y constraint:**
that `<p class="assistant-reply" aria-live="polite">` is the single live region that *also* renders live
answers (`liveText`, `AssistantPanel.tsx:682-688`). Do **not** delete the live region — in the resting
state render it empty and suppress the empty card chrome (`assistant.css:215-224`) so no bordered empty
box / fixed-height gap remains; keep it mounted so answers still announce. Preserve composer, Suggested
Questions, Agent Actions, conversation log, provenance/staleness/Ask-Again, refusal/unavailable/degraded
states, the bottom advisory disclaimer, and all accessible names. Applies to all 5 mounting surfaces
(shared component). **No replacement empty-state card.**
- Acceptance: placeholder text + empty card chrome gone in resting state on all 5 surfaces; live-answer
  announcement, focus order, keyboard handling, conversation state unchanged; no awkward gap; tests
  updated to assert the card's **absence** (`assistant.test.tsx`, `assistant-a11y.test.tsx`,
  `assistant-freeform.test.tsx`, `memory-status.test.tsx`).
- Verify: focused frontend tests → full frontend suite → tsc → Vite build → responsive/a11y checks →
  Opus review.

### P36.2 — Project Memory **Graph** tab (architecture: Opus 4.8; implementer: Sonnet 5; reviewer: Opus 4.8)
Highest-priority new capability. Add a `graph` tab to `ProjectMemory.tsx` (`MEMORY_TABS`, `:46-56`).
See §5 for the **truthful data model** (served-file reference graph — NOT an ontology). Opus does the
architecture pass first (endpoint shape + bounded-SVG component + a11y plan + performance controls),
then Sonnet implements.
- Backend: add one **GET** projection endpoint (`/api/memory/graph`) that reads the committed snapshot
  via the existing `memory.py` reader and returns bounded `{nodes, edges, communities, meta}`
  (deterministic, base-path-correct, no absolute paths/secrets, honest on missing/stale). Auto-updates
  when the snapshot is regenerated. No general file-read.
- Frontend: bounded **SVG** (no new dependency) + search-first + node-type/community filter + fit/pan/
  zoom + selectable node → readable detail panel (title, type, community, deterministic metadata,
  **textual connected-node list**, optional collapsed raw-JSON of that node) + source navigation to the
  existing memory file/concept views + node/edge counts + restrained legend + snapshot version/
  fingerprint. Clear empty/unavailable/invalid/loading states.
- A11y/perf: keyboard-navigable controls + non-pointer node selection/navigation; meaning not by color
  alone; reduced-motion; 200% zoom; narrow-screen fallback = the textual list even if the canvas
  simplifies. Bounded initial neighborhood / depth / node-type filter so nothing unbounded renders.
- Verify: focused backend + frontend tests (parsing, projection, invalid/missing snapshot, node/edge
  determinism, search, filters, selection, source-nav, keyboard, narrow-screen, base-path, **no
  mutation / no external network / no Graphify runtime / no record-truth authority**, snapshot-drift) →
  full backend + full frontend → tsc → Vite build → Docker PR smoke → snapshot `--check` +
  committed-snapshot gate → security/path scans → a11y checks → Opus review.

### P36.3 — Standalone Validator (implementer: Sonnet 5; reviewer: Opus 4.8)
Functional destination under **Governance & Safety** (`GovernancePage.tsx`, currently a stub). Upload/
paste JSON → official schema + canonical vocabulary validation, structured errors, **verdict parity with
CLI**. Reuse authoritative validators (`src/isaac_records` via a thin read-only backend route); bounded
upload size; **no record mutation, no raw-file persistence, no secret/private-content logging**; honest
synthetic/local scope; no second validation implementation.

### P36.4 — API Documentation + Help/About (implementer: Sonnet 5; reviewer: Opus 4.8)
- **Help/About** under **Settings** (`SettingsPage.tsx`, currently a stub): build commit, app version,
  schema version (v1.05), deployment mode (`synthetic-only`), ephemeral status, provenance/authority
  boundaries, doc links — from live backend (`GET /api/graph/status` `deployed_app_commit` + a small
  read-only about projection), not hardcoded strings. No sensitive infra details.
- **API Documentation** from the real OpenAPI contract, **base-path-correct under `/krish`** (today
  FastAPI `/docs` is root-mounted and unreachable behind the base path). Searchable/readable; do not
  expose privileged/mutating endpoints beyond what an authenticated user may safely inspect; no
  hand-maintained duplicate API truth. Final placement (Settings sub-view vs. a single new flat item)
  decided at the slice under the functional-first rule.

### P36.5 — New Record coverage audit + targeted gaps (audit: Opus 4.8; implementer: Sonnet 5; reviewer: Opus 4.8)
Audit the **one** existing flow (`LoadMaterials.tsx` → `/record/:id` → draft/complete/evidence/export)
against the canonical schema (required/optional/enums/nested/validation/save/export/import). Implement
**only proven gaps** that materially improve the single flow. **No second record form.** Avoid dense
portal-style forms.

### P36.6 — Schema & Vocabulary browser (implementer: Sonnet 5; reviewer: Opus 4.8)
Read-only browser sourced from the canonical schema + vocabulary files: search; field/term detail;
type; required/optional; allowed values; description; relationships **actually present in the schema**;
source/version. **No** proposal/approval/ontology-editing/role/persistence features; not "the portal
Ontology system." Destination decided at the slice (likely a Governance & Safety or Settings sub-view)
under functional-first.

### P36.7 — Optional Workspace Overview (evaluate first)
Implement only if a focused audit proves non-redundant value (candidate read-only sources:
`GET /runtime/records`, `GET /graph/status` counts). If built: local synthetic only; no raw identity/
IPs/fake analytics; not the home; no production-operational implication. **If redundant, skip and
document the decision.**

---

## 4. Hardening items

- **H1 — remove mutable `:latest`.** `.github/workflows/build-push.yaml` (owned in this repo, Dean-
  authored) publishes `:latest` alongside immutable semver. Remove `:latest` publication only; preserve
  immutable semver image + auto tag-create + Flux compatibility; add workflow static assertions/tests
  where practical; prove no deployment component depends on `:latest` (Dean's guide: Flux pins semver);
  deployment-sensitive Opus review. **Do not modify `isaac-k8`.** Residual to flag: cannot prove no
  out-of-repo consumer pulls `:latest`.
- **H2 — pin GitHub Actions to commit SHAs** (first- and third-party) with a comment showing the
  semantic version; no secret/permissions expansion; no behavior change; PR Docker smoke stays
  non-publishing; CI green; independent supply-chain review.
- **H3 — `ApiKeyAuthMiddleware` decision.** Focused architecture review (Authentik is the sole prod
  access model). Choose: remove (edge-only) / retain for local-dev with a loud asymmetric-config
  startup warning / defer with reason. **No personal or SPA key in production.** Any change → tests +
  independent security review.

Handle H1–H3 as small reviewed PRs (dedicated or folded into an appropriate slice).

---

## 5. Project Memory Graph — truthful data model (binding for P36.2)

The committed snapshot (`apps/api/isaac_api/data/memory-snapshot.json`) is a **curated projection**, not
the full source graph. It embeds **no edge list**. Therefore the Graph tab presents only what is
materialized, honestly labeled **"Graph" / "Memory Graph"** (never "ontology" or "knowledge graph"):

- **Nodes:** 201 served **files** (`files[]`: `path, file_type, community_id, community_name, node_count,
  on_disk`) + 19 **concepts** (`concepts[]`: `id, label, community_id, community_name, on_disk,
  source_file`). Two truthful node types.
- **Edges:** directed **file→file `"references"`** from `file_detail[path].related.files[]` (each
  `{path, file_type, relation}`; 149/201 files have ≥1). **Concept relations are empty** (0/19) — do not
  invent concept edges. **Community membership** (`community_id`, 257 communities) is grouping/clustering
  metadata, **not** pairwise edges — present it as grouping/legend, not fabricated links.
- **Honest meta:** show the materialized counts (201 files, 19 concepts, ~149 with references, 257
  communities) AND disclose that the underlying source graph (`overview.node_count=2988`,
  `edge_count=4465`) is **not embedded** — this view is the served-content reference projection. Include
  `built_at_commit` / `source_graph_sha256` / `snapshot_schema_version` for provenance.
- **No writes, no scientific-authority claims, no record truth.** The graph is a navigation/provenance
  aid over project documentation, exactly like the existing memory plane.

---

## 6. Phase 37 boundary (NOT started in Phase 36)

At Phase 36 close, update the Phase 37 readiness plan (doc only): `/portal` stays production, `/krish`
stays preview; existing portal stays live until verified replacements exist; in-cluster Postgres is the
preferred future record-data path; portal API exists but is not the preferred integration path;
`isaac-k8` belongs to Dean; Authentik forwarded headers available; production secrets are Dean's in
Kubernetes; any external model-provider dependency needs separate billing/ownership/retention/security
decisions. Identify required access, module inventory, API/DB contracts, role mapping, read-only
Postgres reconnaissance design, security approvals, migration gates, and legacy keep/merge/retire
decisions. **Connect to none of them.**
