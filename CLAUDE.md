# ISAAC Metadata Assistant — Project Instructions

This repository contains the ISAAC Metadata Assistant prototype.

Project goal: turn experiment metadata into validated, evidence-grounded official ISAAC records using the official ISAAC v1.05 schema. The assistant helps draft, complete, validate, export, query, and review records while preserving a strict no-guessing policy.

Read this file before working in the repository. Also read `AGENTS.md` for agent workflow and phase execution rules.

---

## 1. Source of Truth

The official ISAAC schema is the authority on record structure, required fields, and vocabulary.

Authoritative schema:

```text
schema/isaac_record_v1.json
```

Schema provenance:

```text
schema/PROVENANCE.md
```

Upstream source:

```text
https://github.com/ISAAC-DOE/isaac-ai-ready-record
```

The official schema is vendored for offline, deterministic validation. It is not ours to casually edit. If it needs to be refreshed, do so from the upstream ISAAC repository and update `schema/PROVENANCE.md`.

Exported records must validate against the official schema.

Use:

```bash
.venv/bin/isaac validate <record> --official
```

Do not invent an alternative official record format.

---

## 2. Two Planes: Truth vs. Memory

The project has two separate planes.

### Truth Plane

The truth plane decides validity, exportability, and official record shape.

It includes:

- `schema/isaac_record_v1.json`
- `src/isaac_records/official.py`
- `src/isaac_records/draft_validator.py`
- `src/isaac_records/export.py`
- `src/isaac_records/audit.py`
- `src/isaac_records/cli.py`
- tests that enforce schema validation, export gating, sidecar path resolution, and no Graphify imports

The truth plane must be deterministic and Graphify-free.

If a graph answer, LLM answer, note, or memory conflicts with the schema, validator, export behavior, audit result, or tests, the deterministic source wins.

### Memory / Query Plane

The memory/query plane helps with context, relationships, and project navigation.

It includes:

- Graphify
- docs
- query routing
- project memory
- similar-record lookup
- documentation search
- prior experiment/document queries
- contextual drafting help

Graphify is central for memory and query, but never central for truth.

Graphify can suggest context. It cannot authorize export.

---

## 3. Validation Stack

Validation and review happen in this order:

1. Draft no-guessing validation using `draft_validator.py`
2. Official ISAAC schema validation using `official.py`
3. Official `portal/validation.py` soft-warning tier, when integrated
4. AI scientific consistency review using `review.py`, advisory only
5. Human review for ambiguous science or policy decisions

Stage 4 is advisory only. It must never:

- mark records officially valid or invalid
- mutate records silently
- override official schema validation
- override portal validation
- block export unless an explicit user-approved policy later wires it in

The official schema and deterministic validators remain authoritative.

---

## 4. Drafts vs. Official Records

Drafts and official records are different.

### Drafts

Drafts are assistant authoring artifacts. They may use an evidence envelope format such as:

```json
{
  "value": "...",
  "status": "verified",
  "evidence": []
}
```

Drafts may contain:

- missing values
- `needs_confirmation`
- user-confirmation requests
- evidence entries
- implicit values
- extraction notes

Drafts are not official ISAAC records.

Drafts may live in:

```text
drafts/
tests/fixtures/
```

### Official Records

Official records are schema-clean ISAAC records.

They must:

- validate against `schema/isaac_record_v1.json`
- use official ISAAC field structure
- avoid custom evidence envelopes
- avoid arbitrary assistant-only fields
- be generated through `isaac export`

Official generated records live in:

```text
records/
```

Never hand-edit official records in `records/` unless explicitly instructed. The normal path is draft → export.

### Evidence Sidecars

The official schema does not support arbitrary per-field evidence wrappers. This assistant preserves field-level evidence in sidecar files:

```text
records/<ULID>.json
records/<ULID>.evidence.json
```

The sidecar maps official JSON paths to evidence entries.

The sidecar is an assistant audit artifact unless mentors approve it as an official ISAAC convention.

---

## 5. No-Guessing Rules

Never invent or guess:

- scientific values
- units
- sha256 hashes
- URIs
- file paths
- raw-data pointers
- descriptor values
- uncertainty values
- QC status
- links
- timestamps from nowhere
- scientific interpretations

If a value is not supported by evidence:

- leave it missing
- mark it `needs_confirmation`
- ask a targeted question
- or keep it out of the exported official record

Every non-null finalized draft field must have evidence or user confirmation.

A field may be inferred only by a documented/stored rule. Scientific judgment is not an inference unless supported by evidence or user confirmation.

Absorbing element and edge for the XANES path are currently treated as implicit/sidecar-only unless the official schema provides a native field. Do not force them into the official record if the schema has no valid path.

---

## 6. Data Governance

Treat `examples/` as potentially sensitive. It is gitignored for a reason.

Rules:

- Never commit real SLAC/SSRL/private artifacts.
- Never commit private Excel files, screenshots, PDFs, raw data, raw file listings, or private notes.
- Never send real experiment data to external services unless the user explicitly confirms that it is allowed.
- Synthetic fixtures must be unmistakably fake.
- Public official ISAAC schema/examples may be committed if provenance is documented.
- If unsure whether a file is safe, stop and ask.

For any phase touching input artifacts, report:

- what files were read
- whether they were synthetic or real
- whether any model/LLM saw the content
- whether anything under `examples/` was staged
- `git status --short`
- `git check-ignore` results for generated examples files when relevant

---

## 7. Graphify Memory Plane

This repository may have a local Graphify graph at:

```text
graphify-out/
```

Graphify is the memory/query/context plane.

Use Graphify for:

- project memory
- relationship search
- similar-record lookup
- prior experiment/document queries
- contextual drafting help
- documentation search
- “what changed?” history
- “how is this connected?” questions
- architecture navigation before editing unfamiliar code

Do not use Graphify for:

- official schema validation
- export decisions
- required-field enforcement
- vocabulary authority
- audit truth
- data-governance decisions

If `graphify-out/graph.json` exists, use Graphify before answering architecture/codebase questions.

Recommended commands:

```bash
graphify query "<question>"
graphify explain "<concept>"
graphify path "<A>" "<B>"
```

Use `graphify-out/wiki/index.md` if present for broad navigation.

Use `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/explain/path are insufficient.

Known caveat: Graphify may contain dangling/collapsed semantic edges from AST/semantic ID mismatch. Treat Graphify as helpful context, not guaranteed truth. Spot-check important graph claims against source files, schema, and tests.

Never commit `graphify-out/`.

After large uncommitted architectural/code changes, run `graphify update .` if safe and useful. If a git hook already updates the graph after commit, manual update is only needed for large uncommitted changes.

---

## 8. Slash Skills

Available project-local skills:

- `/isaac-draft`
- `/isaac-complete`
- `/isaac-validate`
- `/isaac-query`
- `/isaac-export`
- `/isaac-checkpoint`
- `/isaac-resume`

Do not add new slash commands unless explicitly approved.

`/checkpoint`, `/resume`, `/phase`, and `/verify-ui` were previously prose workflow names in these
instructions, **not installed ISAAC commands** — do not assume they are invocable. The checkpoint and
resume discipline is now provided as repo-local skills `/isaac-checkpoint` and `/isaac-resume`; `/phase` and `/verify-ui` remain prose +
plan-doc conventions with a manual procedure documented in the toolchain reconnection runbook.

Current command boundaries:

- `/isaac-draft`: extract into draft format with evidence
- `/isaac-complete`: ask only validator/export-blocking questions
- `/isaac-validate`: explain draft/official validation results
- `/isaac-query`: route query to schema/docs/audit/git/Graphify depending on question type
- `/isaac-export`: deterministic export to official ISAAC record + evidence sidecar
- `/isaac-checkpoint`: report verified session/repo state (branch, tree, changed-file classes, verification), run the snapshot preflight when served files changed, and commit/push only explicitly-safe scoped docs; refuses destructive git and deployment
- `/isaac-resume`: reconstruct verified repo + remote state, read the decision-lock/roadmap/active phase plan/checkpoint, and state the next authorized action; implements nothing

---

## 9. Query Routing

Use the correct source for the question.

| Question type | Source |
|---|---|
| Is this official record valid? | `isaac validate` / official schema |
| What fields are required? | official schema |
| What vocabulary values are allowed? | official schema / official docs |
| Which records are incomplete? | deterministic audit |
| What changed recently? | git log / docs / Graphify for memory |
| What is related to this sample/record/topic? | Graphify |
| What prior docs mention this concept? | Graphify / docs |
| Is this scientifically suspicious? | advisory review / human review, not official validation |

Graphify can suggest context; it cannot authorize export.

---

## 10. Phase Workflow

Work phase-by-phase. Do not run ahead.

Each phase should follow this loop:

1. Plan the slice.
2. Dispatch the appropriate subagent for focused implementation.
3. Review the diff against project invariants.
4. Run verification.
5. Fix/iterate if checks fail.
6. Commit/push only when the phase instructions allow it.
7. Stop at the approval gate before the next phase.

For this project, the risk-tiered orchestration policy is:

- **Orchestrator** (orchestrator-only — plans, decomposes, inspects, reviews, verifies, judges
  integration/release, and controls commits, branch pushes, and PR creation; does **not** write
  production code): Fable 5 when it is actually available in the current account; otherwise Opus 4.8
  (ratified standing fallback) under the same orchestrator-only restriction.
- **Ordinary implementation:** Sonnet 5 by default.
- **High-risk implementation** (instruction-architecture, security-sensitive, truth/validation/export
  core, data-model, deployment-critical, or design-critical work): Opus 4.8.
- **Independent review:** a separate Opus 4.8 reviewer that implemented none of the work under review.
- **Concurrency:** one fresh, focused implementation subagent per task by default, run sequentially; no
  fixed maximum agent count, but no large uncontrolled parallel swarm.
- **Implementation subagents edit files only**; they do NOT commit, push, merge, deploy, tag, change
  remotes, switch accounts, rebase, reset, alter infrastructure, or change credentials/billing/ownership.
  Every state-changing task receives a separate Opus review before the orchestrator commits.
- Keep slices small, reviewable, testable, and committable.
- Do not begin the next phase without explicit user approval.
- Do not broaden scope during a phase.

---

## 11. Current Phase Context

Current state:

- The deterministic truth/export/validation/audit core and the synthetic XANES draft→export→sidecar→audit flow are in place and passing.
- **Phase 34 (free-form deterministic Assistant Q&A) is COMPLETE**, shipped at code HEAD `d69d0ed`
  (see `docs/superpowers/plans/2026-07-21-post-phase-26-master-execution-ledger.md` §Phase 34 and
  `docs/superpowers/plans/2026-07-23-phase-34-assistant-freeform-closure.md`). "Free-form" means
  flexible natural-language phrasing over a bounded, deterministic intent catalog — **no LLM was
  added**; unsupported/ambiguous/open-world questions are refused honestly, never guessed; Q&A is
  read-only. A real LLM provider (Tier 2) remains an unapproved, deferred decision. The Phase 33/34
  human visual sign-off gate (narrow-viewport + 200% zoom) is still OPEN — Krish's to give.
- **Phase 35 (org-repo convergence + S3DF deployment) is COMPLETE** — org canonical HEAD `8a10ed5`
  (two-parent merge #1, both histories preserved), deployed image `v0.0.3`, hosted `/krish` running
  commit verified `8a10ed5`, `mode: synthetic-only` (see
  `docs/superpowers/plans/2026-07-24-phase-35-org-convergence-closure.md`). The canonical repo is now
  `ISAAC-DOE/isaac-metadata-assistant` (local remote `origin`); the personal repo is remote `personal`
  (preserved historical mirror). The integration did NOT change the truth path. **Personal-deploy
  retirement (Vercel `isaac-demo-web` + Railway service) is pending Krish's dashboard disable-not-delete
  action**; the human responsive / 200%-zoom visual sign-off gate remains OPEN.
- **Phase 36 (repository-local native enhancements) — COMPLETE incl. workflow-progression closure
  slice** at org HEAD `5bb25a8` (image `v0.0.11`); synthetic-only, deterministic, no LLM/portal/real-data,
  truth core untouched (see `docs/superpowers/plans/2026-07-24-phase-36-native-enhancements-plan.md` and
  the closure `docs/superpowers/plans/2026-07-24-phase-36-closure.md`). Feature slices: **P36.1**
  Assistant empty-state cleanup (`v0.0.5`), **P36.2** Project Memory Graph tab (`v0.0.6`), **P36.3**
  Standalone Validator (`v0.0.7`), **P36.4** API Docs + Help/About (`v0.0.8`), **P36.6** Schema &
  Vocabulary browser (`v0.0.9`). Closure slice **P36.8** (`v0.0.11`, merge `5bb25a8`, PR #9): a
  state-driven **workflow progression banner** on the four record screens surfacing the single next
  action — export-readiness confirmed **fully derived** (`workflow.py::derive_workflow`; no human review
  step, no state-transition bug), so the banner is frontend-only, truthful to the derivation (never claims
  "ready" when the official dry-run is failing), never mutates or bypasses a gate; **plus** a
  synthetic-demo idempotence **regression guard** (audit found repeated Run-Synthetic-Demo already
  idempotent by fixed `CANONICAL_IDS` upsert — no fix needed, test-strengthening only). Each slice: Sonnet
  implement → independent Opus review → full suites + `tsc -b` + snapshot regen + gate → PR → merge-commit
  → GHCR + Flux. **P36.5** (New Record audit) and **P36.7** (Workspace Overview) were **skipped with
  documented rationale**. Hardening: **H3** `ApiKeyAuthMiddleware` → retain + defer (decided); **H1**
  `:latest` removal + **H2** Action-SHA pinning → specified, staged as Dean-in-the-loop PRs (both edit
  `build-push.yaml`, not PR-CI-verified; H1 unprovable without `isaac-k8`). **Hosted QA of every image is
  Krish-gated** (Authentik edge, not self-verifiable here — hosted `/krish/api/health` `commit` should
  read `5bb25a8` once Flux rolls `v0.0.11`); responsive/200%-zoom sign-off + personal-deploy retirement
  remain OPEN. **Phase 37 (portal / Postgres / real data / API keys / roles / external LLM) remains NOT
  authorized** — readiness plan only: `docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md`.
- **Phase 36R (interaction, information architecture & graph exploration refinement) — COMPLETE**
  at org HEAD `5b08ce5` (image `v0.0.19`); synthetic-only, deterministic, **no LLM added, no new npm
  dependency, no backend route added or changed**, truth core untouched. Plan:
  `docs/superpowers/plans/2026-07-25-phase-36r-interaction-ia-graph-refinement.md`; closure:
  `docs/superpowers/plans/2026-07-26-phase-36r-closure.md`. Seven merge-commit PRs (#11–#17) →
  images `v0.0.13`…`v0.0.19`. Frontend tests **751 → 1120** (62 → 69 files); backend **1029**
  unchanged. Shipped: a shared `readable`/`wide`/`full` content-width system (the old
  `.placeholder { max-width: 640px }` had squeezed Project Memory, Governance and Settings);
  an Assistant conversation redesign across all five mounts (the log had been clipped to 340px of
  761px content); a **native** Graph Explore/Browse over the committed 220-node/508-edge projection
  with a deterministic seeded layout — the Graphify HTML was rejected because `graphify-out/` is
  gitignored and excluded from the Docker COPY allowlist, it loads vis-network from a CDN, and its
  `graph.json` carries paths the served-content manifest withholds (**R1**); a bounded deterministic
  graph command bar and Assistant graph intents sharing ONE typed `GraphAction` model (**R6**);
  Concepts and Schema Reference master-detail redesigns; and a Settings IA with an OpenAPI browser.
  Every slice: Opus implement → **independent Opus review** → all Critical/Important fixed → green CI.
  The reviews' most consequential catches were honesty defects that every test passed through —
  including an Assistant stating a node count the applied action did not produce, and a Settings
  claim that real artifacts are "refused before anything is read or extracted" when **no
  real-vs-synthetic detection exists anywhere in the codebase** (the app enforces synthetic *mode*,
  not synthetic *data*). **R9 records that the authorizing prompt's own prescribed copy was false**
  and was corrected. **HOSTED QA of every image `v0.0.13`–`v0.0.19` is PENDING (Krish)** — `/krish`
  is behind an Authentik edge this environment cannot authenticate to; no rollout is claimed as
  verified. Responsive / 200%-zoom human sign-off and personal-deploy retirement remain OPEN.
- **Product-hardening phase (2026-08-03) — SIX PRs merged**, `#47` `3263e1e`, `#48` `0c13629`,
  `#49` `a3c0fb3`, `#52` `74299b3`, `#50` `91dc09c`, `#51` (see git log). Closure record:
  `docs/superpowers/plans/2026-08-03-product-hardening-closure.md`. What a future session must not
  re-derive or silently reverse:
  - **Reset is now precondition-gated.** `preview` returns an opaque `plan_digest`; `execute`
    REQUIRES it (**428** absent, **412** stale), and the match is verified *inside the same critical
    section as the mutation*. Managed-legacy removal now holds `record_lock` like canonical
    re-materialisation always did, and `final_count` is **measured**, not asserted. **Two different
    phrases, and this line used to conflate them.** The phrase the operator TYPES is `RESET`
    (`TYPED_GATE`, `apps/web/src/components/ResetDemoDialog.tsx:61`; `armed = confirmText ===
    TYPED_GATE`, `:269`; the field's own label reads "Type RESET to confirm this destructive
    reset", `:442`/`:451`). `RESET EXAMPLE WORKSPACE` is the BACKEND's phrase
    (`RESET_CONFIRMATION`, `apps/web/src/lib/api.ts:106-118`), sent verbatim on execute and
    deliberately never surfaced or auto-filled. Do not describe it as the displayed phrase: a
    tester who types it leaves the confirm button disabled.
  - **Three claims that were FALSE and are now scoped, not deleted.** Governance & Safety and Load
    Materials asserted *"no file is read, parsed, or inspected"* while `RecordValidator` (one tab
    away) and `CsvReconcilePanel` read and POST a chosen file. The refusal claim is true of
    `POST /api/uploads` only. `__tests__/upload-claim-parity.test.tsx` pins all three sites — and
    pins **polarity**, because its first version passed an inverted disclosure.
  - **`VerdictCard` no longer renders `isaac validate --official · exit N`.** No CLI is ever
    invoked; `exitCode` was a client-side literal. Do not reintroduce a command transcript.
  - **`export.transform` guards `series` with `is not None`, not truthiness.** The old falsy guard
    deleted an evidenced `qc` verdict for `series: []` AND suppressed the advisory that would have
    caught it. `portal_warnings.NO_MEASUREMENT_SERIES` now discloses an empty series; it is
    **advisory and non-gating** and deliberately does not classify the science.
  - **`POST /api/validate/record` runs the advisory tier.** `ok` stays computed from schema
    validation ALONE — a warning must never turn a PASS into a FAIL.
  - **`complete.py` type-guards `series` and `descriptor`** (matching what `qc` already did). A
    wrong-typed structured answer used to return **HTTP 500** from the truth core. A typed 422 is a
    deliberate follow-up, not an oversight.
  - **A second Playwright suite exists**: `playwright.mutation.config.ts`, own backend, own
    workspace, own dev server, `workers: 1`, `retries: 0`. Do NOT fold it into the read-only suite —
    that one asserts canonical seed CONTENT across five parallel projects and would break.
  - **Guided tutorial** with browser-local versioned completion; replay never calls
    `POST /api/demo/reset`. The mode chip reads **"Example workspace"** and its *accessible name*
    carries the three claims the word "Synthetic" used to carry. `/api/health`'s
    `mode: synthetic-only` is UNCHANGED — presentation moved, contract did not.
  - **STILL OPEN**: backend-sourced jargon on product screens (`MANAGED_SOURCE_DESCRIPTION` feeds
    `classify_experiment`, so it is a behaviour change to the destructive path); axe scans at
    390/320 px; evidence/confirmation/validation mutation specs; tutorial browser specs; the
    screenshot sweep; `.section-tab` contrast (pre-existing, now documented in the a11y baseline).
  - **HOSTED QA PENDING (Krish)** for every image from this phase. `/krish` returns `302` here.
    Manual sequence: `docs/krish-manual-verification-checklist.md`.
- Current repository status is summarized in README.md and docs/mentor-brief.md; see git history for the exact commit state.
- Start any further phase (beyond the completed Phase 36 / Phase 36R slices) only after explicit user approval.

Do not treat this note as a work authorization — confirm the actual head, branch, and status with the commands below before continuing.

Before continuing, verify repo state with:

```bash
git status -sb
git diff --stat
git log --oneline -5
.venv/bin/pytest
```

---

## 12. Reporting Cadence

After every implementation slice and every phase, provide a report. Do not wait until the end of a large phase.

Each report must include:

- files changed
- what was implemented
- what was intentionally not changed
- verification commands/results
- test results
- safety/data-governance checks
- whether truth/export/validation paths were touched
- whether Graphify was used or updated
- commit hash if committed
- push status
- blockers or deferred items
- recommendation for the next slice/phase

For each Phase 36 (and later) deployed slice, the report must additionally include:

- implementer model and reviewer model
- accessibility checks (result)
- PR URL and CI result
- merge commit SHA and image version / semver tag
- hosted health commit and hosted QA result — or `HOSTED QA PENDING (Krish)` with an exact checklist
  when the hosted app is not self-verifiable from this environment (Authentik edge). Never claim an
  unobserved rollout as verified.

This applies to all future phases.

### Durable per-slice report contract (added 2026-07-31, baseline restoration)

Every implementation slice — not only deployed ones, and not only at phase end — reports **all** of:

slice name · starting SHA · ending SHA · files changed · what was implemented · **what was
deliberately not implemented** · verification commands and their results · frontend test count ·
backend test count · browser test result · accessibility test result · security and governance checks ·
reviewer findings · fixes made · commit hash · PR · merge commit · image version · push status ·
hosted rollout status · blockers · deferred items · recommendation for the next slice.

Two rules that exist because they were violated before:

- **Never report a count you did not just measure.** Quote the command.
- **Never report an unobserved hosted rollout as verified.** `/krish` sits behind an Authentik edge
  that this environment cannot authenticate to, and an agent must not enter credentials. The honest
  status is `HOSTED QA PENDING (Krish)` plus an exact checklist.

**Extended 2026-08-02 (corpus-validation phase).** Two fields are added to the list above, because a
slice that touches production-derived content cannot be judged from test counts alone:

- **Authorization basis** — the specific committed sentence, with `file:line`, that permits what the
  slice did. "It seemed covered" is not an authorization basis. If the basis is a Dean answer that has
  not arrived, the slice does not run against real data; it runs against synthetic fixtures and says so.
- **Data boundary** — what production-derived content the slice touched, where it lived, how long it
  lived, and what left the process. For a slice that touches none, the honest entry is "none", which is
  a stronger claim than silence and should be stated explicitly.

---

## 13. Truth Path Protection

The truth/export/validation path consists of:

- `schema/isaac_record_v1.json`
- `src/isaac_records/official.py`
- `src/isaac_records/draft_validator.py`
- `src/isaac_records/export.py`
- `src/isaac_records/audit.py`
- `src/isaac_records/cli.py`
- tests that enforce official validation, export gating, sidecar resolution, and no Graphify import

Do not modify the truth path during extraction/query/review work unless explicitly required.

If the truth path is touched, the report must say:

- why it was touched
- what changed
- what tests cover it
- whether exported record behavior changed
- whether official schema compliance changed

The deterministic core must remain Graphify-free.

---

## 14. Development Commands

Use the project virtual environment.

Common commands:

```bash
.venv/bin/pytest
.venv/bin/isaac validate <path> --official
.venv/bin/isaac validate <path> --draft
.venv/bin/isaac export <draft>
.venv/bin/isaac audit
git status -sb
git diff --stat
git log --oneline -5
git check-ignore <path>
```

Keep output concise:

- report command and result
- do not paste huge passing logs
- on failures, show the failing test/file and first useful error lines

This is a Python package/prototype, not a Next.js app. Do not run unrelated build/deploy commands.

---

## 15. Scope Discipline

Current MVP scope:

- single XANES / characterization path
- synthetic data first
- real/sanitized data later only with explicit approval
- official ISAAC schema validation
- evidence sidecar
- optional Graphify memory/query
- free-form deterministic Assistant Q&A shipped (Phase 34, `d69d0ed`): bounded intent catalog only,
  no LLM; Tier-2 LLM/generative Q&A remains out of scope unless explicitly approved
- org-canonical single-image `/krish` deployment on SLAC S3DF Kubernetes (Phase 35, `8a10ed5`):
  synthetic-only, ephemeral (`emptyDir`), Authentik-edge-authenticated; deploy via push to org `main`
  → GHCR image + Flux
- Phase 36 repository-local native enhancements (authorized 2026-07-24) — built only on our own
  schema/contracts, synthetic-only, deterministic, no LLM, no portal dependency, no real data:
  Assistant empty-state cleanup, Project Memory Graph (read-only view of the committed snapshot),
  standalone Validator, API-docs + Help/About, New-Record coverage improvements, schema/vocabulary
  browser

Out of scope unless explicitly approved:

- performance/electrochemistry domain support
- simulation/theory/derived domain support
- portal validator integration beyond evaluation
- real SLAC/SSRL data processing
- new slash commands
- Graphify as truth layer
- advisory AI review implementation beyond isolated placeholder
- Phase 37 and its dependencies (NOT authorized): portal module integration, **durable persistence /
  a PostgreSQL-backed record repository / any database write**, portal or personal API keys, external
  model provider / LLM, identity/role enforcement, retiring the blue portal, deleting/archiving the
  personal repo or the Vercel/Railway projects, and any `isaac-k8` change.
  *Narrowed 2026-07-31:* deployment-mediated **read-only** in-cluster Postgres access that returns
  sanitized **aggregate** output is authorized (Slice 2A, see the readiness table below). Reads from a
  laptop or from CI, writes of any kind, and per-record hosted display remain out of scope.

**Pre-Phase-37 readiness sequence (authorized 2026-07-30; Slice 2A authorized 2026-07-31).** An
explicitly authorized, sequential readiness sequence runs *before* — and does not start — Phase 37.
Phase 37 as a broad feature phase remains **unstarted and unauthorized**.

**The access model changed on 2026-07-30.** Dean updated `docs/postgres-test-db-guide.md` (commit
`b746b1a`) to document that the **supported** development path is *deployment-mediated*: push → GitHub
Actions image build → GHCR → Flux → pod, where the standard libpq environment variables are already
set. Write against the environment contract and verify in the deployed app.

**Corrected 2026-08-01 — this paragraph previously misstated Dean's guide, and the misstatement is
recorded rather than silently replaced.** It said the database is *"not reachable from the laptop or
from CI at all"* and that local execution is *"architecturally impossible … the DB is unreachable from
outside the cluster."* **The guide does not say that.** It says (`docs/postgres-test-db-guide.md:8-13`)
*"**You do not need Kubernetes access, a kubeconfig, or credentials to write code against it**"* and
that *"the port-forward section near the end is an optional convenience for whoever already holds a
SLAC cluster context"* — and it then documents that convenience as working
(`:83-96`): `kubectl port-forward -n isaac-psql svc/isaac-psql-rw 5432:5432`, plus the five `PG*`
variables pointing at `localhost`, with the password from the `metadata-assistant-db-app` Secret. So
"you do not need cluster access" was read as "cluster access does not exist". Not needed ≠ impossible.

**The real constraint is unchanged, and is a project rule binding the agent — not a fact about the
network.** `docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52` blocks *"any connection
originating from a laptop or from CI; local kubeconfig, port-forward, or Secret retrieval"*. Do not
request a kubeconfig, a port-forward, or a Secret; do not run recon locally. That prohibition stands on
its own authority and does not need the false impossibility claim to prop it up.

Two further precisions. The port-forward is **authorized for someone who already holds a SLAC cluster
context** — it is not universally available, and **this repository contains no evidence that Krish
holds such a context** (`docs/where-the-30-records-are.md` §"Proven vs. inferred" lists it as
inferred/unknown). And the §2 hard gate in the readiness plan is **narrowed, not lifted** — read the
amended §2 for exactly what is and is not permitted.

| Slice | Status |
|---|---|
| **1** — deterministic schema-truth-core diagnostics (`src/isaac_records/diagnostics.py`) | **authorized and done.** Contains **no database access** of any kind. |
| **2 (design artifact)** — a safe, **unexecuted** read-only reconnaissance script (`scripts/db_recon.py`) | **authorized and done.** Satisfied §3's "read-only Postgres reconnaissance design" prerequisite. Superseded in place by Slice 2A: the logic moved into the app and this file is now a thin, still-unexecuted CLI wrapper that is deliberately **absent from the container image**. |
| **2 (local execution)** — running that script from a laptop against the SLAC database | **NOT authorized.** Do not request a kubeconfig, port-forward, or Secret; do not run recon locally. The prohibition is the project rule at `2026-07-24-phase-37-readiness-plan.md:48-52`. ~~"and architecturally impossible … the DB is unreachable from outside the cluster"~~ — **corrected 2026-08-01**: Dean's guide says the opposite, documenting `kubectl port-forward -n isaac-psql svc/isaac-psql-rw 5432:5432` as a working optional convenience for anyone who already holds a SLAC cluster context (`:8-13`, `:83-96`). The rule binds regardless; it never depended on impossibility. |
| **2A (deployed execution)** — the deployed pod performs read-only reconnaissance and returns a **sanitized aggregate** report via `GET /api/runtime/database/recon` | **authorized 2026-07-31.** Read-only, one short-lived connection, fail-closed gates, aggregate output only. No record ids, titles, scientific values, evidence, or JSON leave the pod. No writes. **Caveat below:** five shipped aggregates went beyond Dean's enumerated list and have since been withheld from the response — see the G3 note after this table. |
| **3+** — PostgreSQL record repository, record loading, upload writes | **NOT authorized.** Later sequential slices, each independently reviewed. Gated on the Slice 2A hosted report. |
| **Hosted real-record display** | **closed by default**, pending Dean's explicit visibility decision. Dean's guide §"Displaying record content" requires the boundary to be built into the read path from the start, not bolted on later. |

Two separate **questions**, which Dean's guide is explicit about not conflating: **writing** to this
database is unrestricted (the app owns it), while **displaying** its rows is closed by default,
because the seeded rows are real production-derived records. Aggregate output is authorized now;
per-record fields are not. (Not to be confused with §17's "two counts", which is the unrelated
201-served-paths vs 200-manifest-entries distinction.)

**But "aggregate output is authorized" is not the whole truth, and this file must not imply it is.**
Dean's authorization names a specific list — record counts, counts by type and domain, validation
totals, schema version, reachability. **Slice 2A shipped FIVE aggregates beyond that list** — not
three, as an earlier revision of this note said: `by_instance_path`,
`distinct_structural_signatures`, the `total_link_count` / `dangling_link_count` pair, and
`vocabulary_term_count`. They are record-*derived* structural facts. None emitted a scientific value,
title, id, or record text — the masking in `apps/api/isaac_api/db_recon.py` (`safe_key_segment`)
holds under static review; note this is code review, **not** a runtime observation. ~~and **the scan
has still never run**~~ — **corrected 2026-08-01:** the scan **has** run, once, against image
`v0.0.38` (`ceea656`), observed by Krish in an authenticated session and reported as no leaks, four
matching allowlists, zero schema drift, 30/30. That is **operator testimony, not a captured artifact**
(the endpoint keeps its result in process memory only, by design), so the masking claim above is still
backed by code review rather than by an inspected response body — the caveat stands, its reason
changes. See `docs/superpowers/plans/2026-07-31-baseline-completion-matrix.md` §0, Entry 2. **Never
write "the deployed database has never been contacted"**; the accurate form is "no database connection
was opened during this session".

**They are no longer served.** The baseline-closure slice withheld all five from the HTTP response
and names them in `dataset.withheld_pending_visibility_decision`; `vocabulary_term_count` is replaced
by the boolean `vocabulary_cache_present`, which is reachability and *is* enumerated. The root cause
is worth remembering: only the **top-level** response keys were frozen, so all five could ship inside
`dataset` in `v0.0.32` without tripping a single contract test — four of them record-*derived*, the
fifth (`vocabulary_term_count`) a production-table cardinality. The
`dataset`, `integrity` **and `database`** blocks — all three nested blocks, so the gap is closed
rather than relocated — are now built from frozen allowlists (`_DB_RECON_DATASET_KEYS`,
`_DB_RECON_INTEGRITY_KEYS`, `_DB_RECON_DATABASE_KEYS`, `_DB_RECON_GATE_KEYS`). Every block is
*projected* onto its allowlist, so an unlisted key can never be served; on the success path an
unlisted key additionally **raises**, failing closed into a sanitized `projection` envelope. That
raise is deliberately NOT armed on the failure envelopes: they are what a raise degrades *into*, so
if they raised too, a broken allowlist would escape as an unhandled 500 with a traceback instead of
the sanitized envelope — fail-closed has to include the closing. What remains is either explicitly enumerated by Dean, or a schema-side breakdown of
"validation totals" (`by_rule_family`, `by_schema_path`) that obeys *the schema may describe the
data; the data may not describe itself*. The wider report is still computed by `run_recon` for
`scripts/db_recon.py`, which the Dockerfile COPY allowlist keeps out of the image — verified by test,
so no application route reaches it.

**G3 remains OPEN**, narrowed from a live exposure to a question: all five *were* served in
`v0.0.32`, and only Dean can say whether they were within his intent. Do not restore any of them
without his answer, and do not repeat "aggregate output is authorized" without this qualification.

**The Authentik header contract has been OBSERVED, and the probe that observed it is GONE
(2026-08-02).** A temporary endpoint `POST {base}/api/runtime/identity/probe` shipped in `v0.0.42`
(`d521dd7`), ran once in an authenticated session — **operator testimony, not a captured artifact; see
§6A** — and was removed in a reviewed cleanup PR: the route now returns 404 and a test pins that. **Do not re-add it**; the observation is recorded and re-running
it would re-open an ingress-configuration oracle for no new information.

**The durable record is [`docs/identity-trust-contract.md`](docs/identity-trust-contract.md) §6A.** In
brief, and none of it is a value: all seven candidate headers arrived; **ISAAC consumes none of them**;
for `username`, `uid`, `email`, `name` and `groups` the edge **supplied the value and did not append**
the client's planted canary — no second header line, no coalescing on `,` or `|`. **It does NOT follow
that the client's copy was removed**; §6A.1 names two scenarios producing the same signature, one of
which means the client *did* influence the header. And for **`X-authentik-entitlements` and
`X-Isaac-Edge` the client's own value arrived untouched**, so the edge was not observed to supply them
at all.

*(That "does not follow" sentence is load-bearing. An earlier revision of this summary said the edge
"replaced" the client's copy and called it "the safest of the possible outcomes" — stating the
conclusion more firmly than §6A supports, in the file that is read at the start of every session while
§6A is opened rarely. That inversion is the exact failure §6A's testimony block exists to prevent.)*

**Two rules that follow, and that a future slice must not quietly drop:**

- **`X-authentik-entitlements` and `X-Isaac-Edge` are permanently disqualified** from authentication,
  authorization, role assignment, proof that Authentik was traversed, and proof that the caller is an
  institutional user — unless infrastructure changes and is independently re-verified. `X-Isaac-Edge`
  cannot witness edge traversal, which is the one job its name implies.
- **Q1–Q3 are answered for the tested path only.** Q4 (can an in-cluster caller reach the Service
  bypassing Authentik?) is untouched by this and remains Dean's. Nothing observed proves the caller was
  authenticated.

**`X-authentik-uid` is present**, so it is now a live candidate for ISAAC's canonical internal key
alongside the username, which remains the required compatibility key for upstream ownership/ACL rows.
**Neither is confirmed** — UID permanence is **Q17**, username non-reassignability is **Q5**, and both
are institutional lifecycle facts no observation can settle.

**Baseline restoration (started 2026-07-31).** The authoritative definition of "baseline" — which
capabilities are required, which are deliberately deferred, and who owns each external gate — is
[`docs/superpowers/plans/2026-07-31-baseline-completion-matrix.md`](docs/superpowers/plans/2026-07-31-baseline-completion-matrix.md).
Update it in the same PR as any slice that changes a row. Two determinations from it that a future
session must not silently reverse:

- **Real-record display is NOT authorized.** Dean's guide (`docs/postgres-test-db-guide.md:149-162`)
  states hosted per-record display is "**closed by default** pending an explicit visibility decision".
  A real-record adapter, list, detail, evidence view, or export is therefore out of scope — not
  deferred by preference but withheld by the database owner. Database *reachability* is not display
  authorization, and the guide says so directly. The exact question Dean must answer is gate **G2**
  in the matrix.
- **Schema drift is already classified, and the rule for anything further is narrow.** Slice 2A
  ships the taxonomy — `by_rule_family` and `by_schema_path` are served; `by_instance_path` is still
  computed by `run_recon` but is **no longer projected** into the HTTP response. Do not rebuild it.
  Do **not** quote a family count: the deployed pod prefers the diagnostics engine, whose labels are
  raw jsonschema keywords (an open set), not the 12 normalized patterns in `_FAMILY_PATTERNS`. The
  label set is unobserved until the scan runs — matrix §4.1 explains why. For anything *new*, the rule is: *the schema may describe the data; the data may not
  describe itself* — if an output string can only be produced by reading a record's value, it is
  per-record content and is closed. That rule alone is not sufficient, because per-record facts can
  be reconstructed by arithmetic; matrix §4.3 adds a minimum cell size, a cross-tabulation limit, and
  an absolute prohibition on caller-parameterized aggregation. `by_instance_path` was the boundary
  case that proved the rule: over a 30-row seed an `error_count` of 1 at a path *is* a single-record
  fact, which is why it is now withheld rather than merely flagged (see the G3 note above).

Graph freshness and the measured performance baseline are settled in
[`docs/superpowers/plans/2026-07-31-graph-and-performance-baseline.md`](docs/superpowers/plans/2026-07-31-graph-and-performance-baseline.md):
the graph stays **point-in-time, disclosed, and non-blocking**. Regeneration requires the user-local
`graphify` binary, which CI cannot obtain — that, not the model, is the blocker. Note precisely, so
this does not appear to contradict §7's "run `graphify update .`": `graphify update` is manifest-based
and needs **no** model, and remains the correct routine step for a human to run. Only a *full
clustering* run invokes an external model to name communities, and `graphify-out/cost.json` records
that happening exactly once (2026-07-06), with labels cached since.
Personal-deploy retirement facts and the approval-gated order live in
[`docs/personal-deployment-retirement.md`](docs/personal-deployment-retirement.md); both personal
deployments are still live, public, unauthenticated, and Railway is 98 commits stale (re-measured 2026-08-01 at `d7010f9`) with a
**persistent volume** (so deleting destroys data that pausing preserves).

Note also that the app's `mode: synthetic-only` describes the **workspace** — uploads refused, seeding
from committed fixtures only. It has never meant "no real data exists anywhere in the process", and
since Slice 2A production-derived records transit pod memory during a scan. `runtime_mode.py` is
unchanged and still refuses to boot in `real` mode; the honest DB status lives in the `database` block
of `/api/health`, deliberately adjacent to `mode`.

---

## 16. Resume Protocol

After interruption or context reset:

1. Read `CLAUDE.md`.
2. Read `AGENTS.md`.
3. Check latest roadmap/plan docs if present.
4. Run `git status -sb`.
5. Run `git log --oneline -5`.
6. Reconcile claimed progress with actual repo state.
7. Announce the verified state.
8. Continue only from verified facts.

Never guess what was completed.

## 17. Account, Continuity & Snapshot Preflight

### Default-account policy

Preserve the currently connected, developer-owned service identities for ISAAC (GitHub, Railway, Vercel)
unless the user explicitly authorizes a different account. Claude Code runs under the SLAC organization
account; **that does not migrate the other services.** Do not log out a working account, switch identity,
link/relink a project, create duplicate cloud projects, change teams/orgs, alter billing, rotate
credentials, or change git remotes without explicit per-action approval. Treat current infrastructure as
**temporary developer-owned infrastructure pending an explicit SLAC ownership and handoff decision.** The
specific service identities, the account-switch/reconnection/recovery procedure, and the ownership-handoff
gate live in `docs/toolchain-reconnection-runbook.md` — link, do not duplicate.

### Orchestrator selection

See §10 for the full risk-tiered orchestration policy (orchestrator-only Fable 5 when available, else
orchestrator-only Opus 4.8 fallback; Sonnet 5 default implementation; Opus 4.8 for high-risk
implementation and all independent review).

### Snapshot preflight (before any push that touches served files)

The committed snapshot `apps/api/isaac_api/data/memory-snapshot.json` embeds a served-content manifest
re-checked in CI by `apps/api/tests/test_committed_snapshot.py`.

**Two counts, deliberately different by one — do not conflate them:**

| Number | What it is | Where |
|---|---|---|
| **201** | the served **path set** — every repo-relative path the memory plane may describe | `snapshot["served"]`; also `memory-graph-detail.json`'s `served_file_count`, which the API labels `served_file_count_scope: "served_path_set"` |
| **200** | the served **content manifest** — path + raw-bytes sha256, the drift-detection basis | `snapshot["memory_inputs"]["served_content_manifest"]` / `...["served_file_count"]` |

The one path that is served but **not** content-hashed is
`tests/fixtures/memory_snapshot/memory-snapshot.json`: the manifest builder self-excludes any
`*memory-snapshot.json` it would otherwise hash (embedding a snapshot digest inside a snapshot is
circular). So "201 served files" and "200 manifest entries" are both correct statements about
different sets.

The manifest **is far broader than documentation** — measured composition: **64 `apps/web/src/**` files**
(the largest single bucket, including component, lib and `__tests__` files), 37 under `docs/` (35 `.md`
plus two sample JSON artifacts), 36 `tests/**`, 15 `apps/api/**`,
15 `src/**` (the truth core), 7 `docs/superpowers/**`, 5 `.claude/skills/*/SKILL.md`, plus root files
(`CLAUDE.md`, `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `pyproject.toml`, …).

**Practical consequence:** an ordinary frontend component edit, or even a test-file edit, causes snapshot
drift. Do not assume a slice is "frontend only, so the snapshot is not my problem" — three P36V slices hit
this independently after reading an earlier version of this section that listed only docs and skills.
Editing any manifest-listed file is predictable drift — regenerate in the same commit; do not wait for CI.
When two slices touch manifest-listed files in one working tree, regenerate **once** after both settle,
or each will capture the other's in-flight hashes. Pre-push
sequence: implementation → focused tests → full relevant tests → typecheck / Vite build → snapshot drift
check → deterministic regeneration if required → path/secret/leak checks → independent review → commit →
push → exact-HEAD CI → deployment/browser QA. Commands:

**Two committed artifacts, one command.** Since P36V.1 the generator also produces the deep
(symbol-level) graph artifact `apps/api/isaac_api/data/memory-graph-detail.json`. `--detail-out` is
opt-in, so a command **without** it neither regenerates nor checks that artifact — `--check` will
print "ok: no drift" while a stale deep artifact sits on disk, and a regeneration will rewrite the
snapshot and leave the deep artifact stale. The script now says so on stderr, but **always pass
`--detail-out`**:

```bash
# drift check for BOTH committed artifacts (exit 0 = no drift; 6 = drift, and both are reported)
.venv/bin/python scripts/build_memory_snapshot.py --graph-dir graphify-out \
  --out apps/api/isaac_api/data/memory-snapshot.json \
  --detail-out apps/api/isaac_api/data/memory-graph-detail.json --check
# deterministic regeneration of BOTH (drop --check), then re-run the check + the gate tests
.venv/bin/python scripts/build_memory_snapshot.py --graph-dir graphify-out \
  --out apps/api/isaac_api/data/memory-snapshot.json \
  --detail-out apps/api/isaac_api/data/memory-graph-detail.json
.venv/bin/pytest apps/api/tests/test_committed_snapshot.py \
  apps/api/tests/test_memory_graph_detail.py -q
```

### Shared Repository Synchronization Contract

Both Claude toolsets (`claude-personal` on `~/.claude`, `claude-slac` on `~/.claude-slac`) share
the **one** repository `~/Documents/ISAAC` — one working tree, `.git`, `origin`, `main`, history,
tracked plans/specs, repo-local skills, and one each GitHub/Railway/Vercel project — while their
Claude **config roots stay intentionally different** and are **never** copied between (no
credentials, OAuth/Keychain, plugins, hooks, MCP, caches, context-mode state). Only **one**
session edits the repo at a time. A **stable checkpoint** requires clean local/Git sync (branch
`main`, 0 ahead / 0 behind, HEAD == `origin/main`); active and interrupted work may exist only
locally and must never be lost. The **only** automatic reconciliation is `git pull --ff-only`
from a **clean** tree that is strictly behind and not diverged; dirty, ahead, diverged, and
remote-advanced states stop for human decision — no automatic merge/rebase/reset/stash/force.
Git, CI, Vercel, and Railway are **four separate synchronization axes**; never report global
"synchronized" when only Git is. Service identities stay the existing Krish-owned accounts. The
authoritative rules, the four-state model, and the decision table live in
`docs/toolchain-reconnection-runbook.md` → "Shared Repository Synchronization Contract" — link,
do not duplicate.