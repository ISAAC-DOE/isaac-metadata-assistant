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

### Measured routing rule (2026-08-07) — replaces "use Graphify first"

**This section previously said: "If `graphify-out/graph.json` exists, use Graphify before answering
architecture/codebase questions." That instruction is WITHDRAWN — it presumed a benefit that a
controlled benchmark did not find.** Evidence:
[`docs/evidence/graphify-benchmark-results.md`](docs/evidence/graphify-benchmark-results.md)
(methodology and decision rules:
[`graphify-benchmark-methodology.md`](docs/evidence/graphify-benchmark-methodology.md)).

**Read the pre-registration claim precisely.** The methodology was **written** before any arm ran —
that ordering is **asserted by the author, not witnessed by git**: all four artifacts first appear
in one commit, `35c4cbb`, so no commit has ever held the methodology without the results. Do not
repeat the stronger phrasing "written *and committed* before any arm ran"; it was in an earlier
revision and is withdrawn. What a reader *can* check mechanically, and what does hold: **no decision
rule or category label changed after results existed** — §5.1 and §5.3–§5.4 are byte-identical
between `35c4cbb` and HEAD. Note also that the results document now records **five tasks where the
§5.3 rules were not applied purely mechanically** (T8, T5, T4, T2, T7), with the direction each cuts;
no label was changed.

32 runs, 8 frozen tasks, two arms, fresh index built at the exact commit under test. Median tool
calls +5.7% and total tokens +4.2% **against** Graphify; correctness tied in 7 of 8 categories.
Across 16 Graphify-arm runs the agents' own `graphify_helped` rating was **never "yes"** (13
"partly", 3 "no"), and every answer they found was found with `rg`.

*Wall-clock also ran against Graphify (median 154.9 s → 218.4 s) but is **deliberately excluded
from every verdict**, and from the figures above, because run 1 launched 16 agents concurrently
and the measurements are contaminated by CPU contention — one agent detected the contention
itself. The quoted figures are the ones contention cannot move. Omitting the larger unfavourable
number is not a kindness to the tool; it is the methodology applied consistently.*

| Route | Rule |
|---|---|
| **First choice** | *(none)* — no category showed a gain distinguishable from run-to-run variance. **No confidence interval or significance test was computed anywhere**; at 2 runs per arm per task none would be meaningful, and none is claimed. Do not write "survives its own error bars" — there were no error bars. |
| **Optional** | Orienting in unfamiliar **documentation**; frontend/TypeScript neighbourhood discovery. Treat output as a pointer to a *document*, then verify in source. |
| **Do NOT use** | Exhaustive/exact-string inventories (**measured HARMFUL**: +26% effort, +19% tokens, no accuracy gain — use `rg`); locating **backend Python**; import/dependency questions; runtime or truth-path verification; disambiguating similarly-named concepts. |

Two reproducible failure modes, both measured across independent runs:

1. **Flat label space.** BFS start-node matching resolves short generic tokens to whatever node
   carries the label — `"preview"` → `ResetDemoDialog.tsx`, `"version"` and `"private"` →
   `apps/web/package.json`, `"If-Match"` → the tutorial-session cluster.
2. **Backend Python is systematically under-surfaced.** `export.py`, `official.py`, `serialize.py`,
   `verification.py`, `disclosure.py`, `csv_ingest.py`, `routes.py`, `auth.py` were all missed by
   the graph *even when they were the answer*.

Commands, if used:

```bash
graphify query "<question>"
graphify explain "<concept>"
graphify path "<A>" "<B>"
```

`graphify-out/GRAPH_REPORT.md` for broad architecture review only. **`graphify-out/graph.html` no
longer generates** at this repo's size (10,618 nodes exceeds the tool's own 5,000-node viz limit).

**Refresh before relying on it.** `graphify update .` costs ~10 s and no model call, but nothing in
CI can run it: the binary is user-local. The index was found **420 commits / 529 files stale** when
the benchmark began. A stale graph is worse than no graph, because its answers look authoritative.

Known caveat, stated precisely: `CLAUDE.md` has long asserted "dangling/collapsed semantic edges
from AST/semantic ID mismatch". **No measured instance of that specific defect exists in this
repository** — the sources for the claim are mutually-citing prose. A *different*, real staleness
defect was measured (a renamed symbol persisting in the deep graph artifact). Do not conflate them.
Treat Graphify as leads, never truth; spot-check every graph claim against source, schema, tests.

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
  - **`POST /api/validate/record` runs the advisory tier.** ~~`ok` stays computed from schema
    validation ALONE~~ — **corrected 2026-08-11, and the old wording is kept struck through
    because it read as a standing guarantee.** The half that still holds, and is the reason the
    sentence existed: **a warning must never turn a PASS into a FAIL.** That is unchanged.
    What changed is the other half — `ok` is now `schema_ok AND exactness_ok`. The route also
    applies the anchored-pattern **exactness gate** (`src/isaac_records/exactness.py`), which
    refuses a value satisfying one of the vendored schema's five `^...$` patterns only because
    Python's `$` also matches before a trailing newline. Three things about it that a future
    session must not collapse back together: the schema's own verdict is preserved beside `ok`
    as **`schema_ok`**, the findings are a **separate `exactness_errors` list** never merged
    into `errors`, and the gate is **ISAAC's, not upstream's** — §1 makes the schema not ours to
    speak for, so no surface may report an exactness refusal as an official-schema error. The
    Validator screen did exactly that for one commit (`FAIL — Invalid against official ISAAC
    schema v1.05 — 0 errors` above `schema_ok: true` and an empty error list); it now branches
    on `schema_ok` and renders the findings under their own heading, pinned by
    `apps/web/src/__tests__/validator-exactness.test.tsx`. The exactness gate is a **hard** gate
    and is the ONE non-schema input to `ok`; `portal_warnings` remains advisory and still cannot
    move it. **Known divergence, deliberate and unfixed:** the per-experiment validate route's
    already-exported branch reports the schema verdict alone, so a record with such a value reads
    `ok: false` here and `ok: true` there.
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
  - **STILL OPEN — RE-MEASURED 2026-08-26, and FOUR OF THE SIX WERE ALREADY CLOSED.** The list is
    corrected in place rather than replaced, because a stale "still open" list is worse than no
    list: it sends a future session to build what exists, and it makes the two real items look
    like five. Measured at `1ad1f8f`:
    - ~~axe scans at 390/320 px~~ — **DONE.** `apps/web/e2e/specs/a11y-narrow.spec.ts` exists;
      `NARROW_WIDTHS = [390, 320]` (`e2e/a11y-baseline.ts:133`); **54** `width-390` and **67**
      `width-320` baseline references, several carrying `{darwin, linux}` splits transcribed from
      Linux CI — a split no local run could have invented.
    - ~~evidence/confirmation/validation mutation specs~~ — **DONE.** `e2e/mutation/evidence.spec.ts`,
      `validation.spec.ts`, `answers.spec.ts`.
    - ~~tutorial browser specs~~ — **DONE.** `e2e/specs/tutorial.spec.ts` +
      `e2e/mutation/tutorial-lifecycle.spec.ts`.
    - ~~the screenshot sweep~~ — **DONE.** `e2e/specs/visual-sweep.spec.ts`.
    - ~~**`.section-tab` contrast — STILL OPEN**, and now quantified: `screens.css` uses
      `--text-tertiary #78838f` at 12.5px/500 for **3.86:1**. The narrow fix has in-repo precedent
      (`--text-muted #5b6570`, 5.93:1). It needs a Linux-CI round-trip to re-transcribe ~35 cells,
      which is why it is not a one-line change.~~ — **DONE, corrected 2026-08-27, and the whole
      item is struck rather than edited because "STILL OPEN" is a claim a future session acts
      on.** Verified at HEAD `7668bf8`, not quoted: `apps/web/src/screens/screens.css:337-346`
      now reads `color: var(--text-muted)`, and `styles/tokens.css:29` gives `--text-muted`
      `#5b6570` — recomputed here as **5.93:1** on `#ffffff` against the discarded
      `--text-tertiary #78838f`'s **3.86:1**, so both figures above were right and it is the
      STATUS that was stale. It landed in `d0c1096` ("FINDING A16 fix"), merged as PR #186 /
      `1dd28ad`; `git merge-base --is-ancestor d0c1096 1dd28ad` exits 0. **The Linux-CI
      round-trip the item said was needed has also happened**, which is why the fix could
      merge: `e2e/a11y-baseline.ts` records it under "`.section-tab` TRANSCRIPTION,
      2026-08-27", linux 2802 → 2431, **119 cells** transcribed from CI run 33025558592 at head
      `2da0c71` — not the "~35" the estimate above guessed. Two things it did NOT close, kept
      separate so nobody reads this as more than it is: **A3**, the app-wide 1,610-node
      `--text-tertiary` contrast debt, is untouched and is a palette decision; and the darwin
      half of those 119 cells was **reasoned rather than measured** until a local macOS run on
      2026-08-27 confirmed all 119 and corrected 19 other cells.
    - **backend-sourced jargon on product screens — UNCERTAIN, and the named exemplar is wrong.**
      `MANAGED_SOURCE_DESCRIPTION` reaches **no** frontend file: `rg "Synthetic XANES campaign"
      apps/web/` returns **0** hits. So the example this item rested on no longer supports it.
      Whether other backend jargon reaches a screen is UNMEASURED. Do not treat the item as
      closed, and do not treat the old example as evidence.
  - **HOSTED QA PENDING (Krish)** for every image from this phase. `/krish` returns `302` here.
    Manual sequence: `docs/krish-manual-verification-checklist.md`.
- **Session of 2026-08-18 — an honesty-defect sweep, conflict resolution, and two external packages.**
  Nothing about the hosted deployment, the truth path, or any external authorization changed. What a
  future session must not re-derive:
  - **The owner's approval of `0003_revisions` and `0004_submissions` is RECORDED** (§15 and each
    packet's STATUS block). **Hosted application remains NOT DONE and is not an agent's act.** A test
    that had been *requiring* the false literal *"No PostgreSQL has ever executed this file"* was
    corrected to pin the invariant instead — CI has executed both migrations against `postgres:18`.
    **Constraint coverage is 41 of 46 declared, and a real PostgreSQL has now EXECUTED all 41 on
    `main`** — Actions run
    [`32800763199`](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/32800763199),
    head `c153ec9` (the PR #171 merge), job `97660962127` *"migration and durable repository against a
    real PostgreSQL"*, step *"Prove every 0003 and 0004 constraint rejects what it claims to reject"*,
    conclusion `success`. **THIS ONE NUMBER HAS BEEN WRONG TWICE, IN OPPOSITE DIRECTIONS, AND BOTH
    CORRECTIONS ARE KEPT SO A READER SEES THE SEQUENCE RATHER THAN ONLY THE LATEST NUMBER: 41 (false)
    → 27 (true) → 41 (true, by a different run).** (i) ~~"41 of 46 declared (re-measured 2026-08-19,
    up from 27)"~~ read as though a run had produced 41, when the fourteen extra cases sat in
    `77de2db`, which was not in `main` and whose own message says *"CI is the first execution"*.
    (ii) ~~"Constraint coverage is 41 of 46 DECLARED IN THE WORKFLOW; 27 of 46 is what a real
    PostgreSQL has actually executed on `main`"~~ was the RIGHT correction on 2026-08-24 and has since
    been **overtaken, not refuted**: `77de2db` merged to `main` on 2026-08-25 via `c153ec9`, and the 41
    then ran. **27 remains exactly right for run `32099627898` at `fe374c0`** and must never be
    re-described as an error. Re-derive rather than quoting: `git merge-base --is-ancestor 77de2db
    origin/main` (now exits 0), and the blamed-name count over `git show
    fe374c0:.github/workflows/ci.yml` (**27**) versus the working tree (**41**, byte-identical to
    `origin/main` — `git diff origin/main -- .github/workflows/ci.yml` is empty). ~~"Both numbers are
    guarded by a test so neither can move without the workflow moving."~~ **CORRECTED 2026-08-25 —
    only ONE of them is guarded in CI, and the other read as a guarantee while being green-by-skip.**
    `41` is enforced everywhere, by `test_the_packets_do_not_overstate_CI_constraint_coverage` and
    (since 2026-08-25) as the first assertion of
    `test_the_two_constraint_numbers_are_each_still_the_measured_ones`, both of which read only the
    working tree. `27` and the `origin/main` byte-identity reach their evidence through
    `git show fe374c0:…`, `git show origin/main:…` and `git merge-base --is-ancestor 77de2db
    origin/main` — and **every `actions/checkout@v5` in `.github/workflows/ci.yml` runs at the default
    `fetch-depth: 1`** (the file sets `fetch-depth` nowhere, at any of its four checkout sites), so in
    CI none of those objects exists and each assertion degrades to a `pytest.skip`. **They are
    enforced in a full clone and reported as skipped in CI.** The skip messages now say so rather than
    reading as a pass. The **5** still unblamed are
    unchanged, and three of them are STRUCTURALLY unprovable in isolation — `isaac_submission_runs`'
    equality CHECKs subsume its shape CHECKs, so no row violates exactly one of them; they are proved
    refused with the blame ambiguous by design. See §15 for the full split.
  - **Explicit conflict resolution exists** (`apps/api/isaac_api/conflict_resolution.py` + two
    operations). It closes a real defect this file had only described in prose: a scientist who fixed a
    typo owned a permanent conflict no surface could clear. Decisions **supersede without deleting**
    evidence, staleness is detected by `competing_digest`, nothing auto-picks a winner, and the chosen
    value deliberately does **not** become the field's value — that is a separate decision.
  - **Four classes of honesty defect were fixed, each mutation-tested**: a failed pipeline step wore
    the success check mark; Record Verification painted three green cards for a corpus it never
    examined; three banners promised "your input is kept" beside a Refresh that destroyed it; and an
    assistant message containing a digest or path lost its whole text and rendered blank. Several
    *existing tests pinned the defect* and were **inverted rather than deleted** — that is now the
    established remedy here.
  - **Repository hygiene:** local branches 141 → 8, with three superseded ones renamed `preserve/*`
    rather than deleted; seven merged worktrees removed. All deletions were preceded by a mechanical
    `git rev-list --count origin/main..<branch>` = 0 proof.
  - ~~**Two external packages are ready and UNSENT:** `docs/dean-handoff-consolidated-2026-08-18.md`
    (migrations, external configuration, open gates) and the re-measured
    `docs/run-scope-decision-packet.md`.~~ **BOTH HALVES ARE NOW FALSE, corrected 2026-08-26 and kept
    struck because "unsent" is the kind of claim a future session acts on.** The 2026-08-18 package
    **HAS been sent** — its own pointer block says the successor "carries only what is new or
    corrected since this one **was sent**", and
    `docs/dean-operator-addendum-2026-08-25.md` addresses Dean about what "the sent package" told him.
    And `docs/run-scope-decision-packet.md` is **SUPERSEDED AS THE DOCUMENT TO SEND** (its own §1,
    2026-08-25) by `docs/angel-scope-questions-2026-08-25.md`; it is not withdrawn — it keeps the
    engineering detail the successor omits — but it is not the thing to forward. **STILL UNSENT, as
    far as this repository can witness:** the 2026-08-25 addendum and the Angel question list. Whether
    either has been forwarded is **only Krish's to say**; an agent cannot observe it, and the honest
    entry is that the repository records preparation, not delivery. The six `system.configuration.*` fields remain
    **`unclassified`, verified** — and nothing in the programme is blocked on Angel's answer.
  - **Not done, and named rather than implied:** `isaac_runs` Stage 2 — ~~"its blocker is measured —
    no completeness marker and no backfill"~~ **corrected 2026-08-26, and the correction matters
    because §15 of this same file has contradicted this sentence since 2026-08-19.** BOTH exist:
    `isaac_run_projection` (`0005_run_projection`) IS the completeness marker, and
    `scripts/db_backfill_runs.py` IS the backfill. The reason a read cutover still cannot distinguish
    "zero runs" from "never projected" is unchanged and is the reason both were built — but the
    blocker is now an EXECUTION, not an absence: the backfill **has never been run anywhere**, `0005`
    is **not owner-approved**, and Stage 2b additionally needs the operator's two completeness queries
    (`docs/migration-approval-packet-0005.md` §8A) both returning 0. Kept struck rather than edited so
    a future session sees that §11 was the stale half of the contradiction, not §15; actor stamping (authorized by Dean, blocked in practice — no trusted boundary
    exists, and the seam stays unset); ~~the native assistant, MCP and voice product surfaces beyond
    their existing seams~~ — **narrowed 2026-08-24: true of the ASSISTANT only.** `TranscriptCapturePanel`
    had already shipped in `72e2206` (2026-08-17) and so was a product surface on the day this was
    written, and `Settings → Connect Your Agent` is MCP's; the accurate claim is that no product
    screen advertises the assistant seam. Left struck rather than edited because the three were never
    in the same state and pairing them is the error worth remembering; and ~~the scale/concurrency
    benchmarks~~ — **struck 2026-08-26: they exist at HEAD.** `docs/run-scale-measurements.md`,
    `docs/evidence/scale-envelope-2026-08-25.md`, `apps/api/tests/test_lifecycle_concurrency.py`,
    `test_concurrent_write_pairs_lose_no_update.py` and `test_handler_concurrency.py` are all
    committed. What is NOT measured is a HOSTED figure of any kind, which is a different claim and is
    the one to make going forward.
- **Session of 2026-08-19 — the product could not capture a record, and now can.** PR #171
  (`819568e`, `42dee80`, `bed331b`, `bb2095c`). Read this before planning any further feature
  work, because it changes what "substantially implemented" means for everything downstream.

  **THE FINDING.** A record created through `POST /api/experiments` — the product's own Create
  Experiment path — **could not be completed or exported, by any route.** Measured on `main` at
  `b118ed6`, over HTTP:

  | step | result |
  |---|---|
  | create, then answer every question the API accepts | `200`, `pending: ['qc']`, `status: needs_attention` |
  | `POST /export` | `200 {"ok": false}` — *"measurement has series but qc verdict has no evidence"* |

  Three independent causes, each fixed here:

  1. **`qc` was not forwarded** by `_answers_to_apply_shape`. `complete.py` had always handled it
     and had always validated the enum; only the route mapper omitted it, and `complete.py`'s own
     docstring had recorded the gap and named the slice that would close it.
  2. **`series` and `descriptor` were answerable only by CONFIRMING a worked example**, which a
     created record does not have. The screen said "No example value is available for this field"
     and rendered no control. `apps/web/src/components/StructuredValueEntry.tsx` is the fix.
  3. **Adding a Run destroyed the answers.** Those four blocks are RUN-level, `new_run` defaulted a
     run's draft to `{}`, so a completed record went to `pending 0 · complete_metadata: completed ·
     review_evidence: completed` **and an export that refused**. The first run now adopts the
     record's run-level content; a later run does not, because copying one run's spectrum onto
     another asserts they measured the same thing.

  **WHY 4,714 BACKEND AND 4,113 FRONTEND TESTS DID NOT CATCH ANY OF IT.** All five canonical
  scenarios are built by `build_draft` from a fixture sheet **that already carries all three
  values**, so every completion and export test in the suite began past the part that did not work.
  `apps/api/tests/test_scientist_can_finish_a_record.py` exists to close that blind spot: it walks
  create → answer → export with values written out rather than harvested, and a negative control
  parses the file to prove it still borrows nothing. **Do not "simplify" it by reaching for a seed.**

  **Two false claims in exported records, both fixed.** `descriptors.outputs[].generated_by` read
  `{"agent": "isaac-complete-demo", "version": "0.1"}` with `label: "completion_demo"` — a demo
  agent claiming authorship of a scientist's descriptor, in a document the schema says names the
  "Tool/pipeline/person that generated these descriptors". And `apply_corrections` compared only
  `qc.status`, so flipping `compromised → valid` kept the old note: a record asserting **valid**
  with provenance saying the spectrum was **unusable**, which official validation and the advisory
  tier both passed. Found by independent review, not by CI.

  **`attribution.uploaded_by` is now server-stamped — and still absent everywhere.** The stamp is
  applied at the ingestion boundary (`apps/api/isaac_api/record_attribution.py`), never in the truth
  core, which is what `export._enforce_server_owned_invariant` anticipates. It requires
  `trust_basis == verified_edge_assertion`, and **no verifier in this build mints that**, so no
  shipped deployment stamps anything. The fixture verifier deliberately still attributes a
  submission ROW (which carries `trust_basis` and so says what it is worth) and deliberately cannot
  reach a RECORD (which has no field to qualify it). Do not collapse those two.

  **Still not done, and named rather than implied:** the campaign-sheet fields (technique, facility,
  sample, contributors) ~~have no capture surface~~ — **CORRECTED 2026-08-30 and the file
  contradicted itself here: §11 already measured "5 writable via `PATCH .../runs/{id}`, 13 via
  `/overrides`, 7 refused by all five". Probed over HTTP: `field:system.facility.site`,
  `field:sample.material.name`, `field:system.technique` and `block:attribution` all return
  **200**. The TRUE residue is the 7 paths no route accepts — the six `system.configuration.*`
  and `timestamps.created_utc` — and, until 2026-08-30, the absence of a RECORD-level surface
  reaching any of them**, so a record could be finished but not richly
  described; `POST /ingestion/csv/preview` has no route that APPLIES a preview; ~~the native
  assistant and voice remain provider seams with no route invoking them~~ — **CORRECTED 2026-08-24,
  and this clause was FALSE WHEN IT WAS COMMITTED, which is why it is struck rather than edited.**
  Both seams have a reachable route. `POST /api/assistant/ask` shipped in `51435e7`, whose own
  subject line reads *"the assistant seam becomes reachable"*, and `git merge-base --is-ancestor
  51435e7 32fe7a3` confirms that commit was already in history when this paragraph was written.
  `POST /api/transcription` shipped earlier still, in `72e2206` (2026-08-17). Both answer **`501`
  `no_provider_configured`** in every deployment, `POST /api/experiments/{id}/transcript` answers
  **`200`** with no provider involved at all, and `/api/assistant/ask` is one of the ~~69~~ **71** operations (re-measured 2026-08-30; the test's
  own comments record 68→69 assistant/ask, 69→70 rename, 70→71 discard)
  `test_about_and_openapi.py` pins. So the sentence was not describing a gap; it was describing
  absent *routes* that existed. **The true residue, which is what the clause was reaching for and
  what still holds: no product screen advertises the assistant seam** — deliberately, per
  `docs/ai-integration-decision-packet.md` §9. **Added 2026-08-25, so the next reader does not
  re-derive it:** §3's stated mitigation for surfacing no seam status — that the Assistant panel
  already says there is no language model — **was absent on the panel when §3 relied on it** (the
  user-facing claim lived in Settings → AI & Automation, behind a tab), and now exists as
  `ASSISTANT_NO_MODEL_CLAIM` rendered in the panel's dock on all five mounts, pinned together with
  the §3 decision by `apps/web/src/__tests__/assistant-model-claim-parity.test.tsx`. It names no
  seam, no provider and no decision, which is precisely why it closes §3's premise without
  weakening the sentence above. Voice is the opposite case and must not be folded back
  in with it: `TranscriptCapturePanel` is a **shipped** voice surface, mounted ungated at
  `apps/web/src/screens/RecordWorkbench.tsx:687`, so any future sentence pairing "assistant and
  voice" as equally unsurfaced is wrong about the second half. See also the D6 supersession, which is
  the decision record this contradicted; `isaac_runs` Stage 2, the Evidence
  Graph / Compare Runs cross-feature work, the scale and concurrency benchmarks, and every hosted
  QA are unchanged by this session.
- **Session of 2026-08-25/26 — seven PRs (#171–#177), and the recurring finding was that a
  surface returned 200 or a green check for work it had not done.** Org `main` at `1ad1f8f`,
  image `v0.0.167`, every CI check green on the exact head SHA of each merge. Backend tests
  **4,714 → 5,368**; frontend **4,113 → 4,390**. Nothing about the hosted deployment, the
  external authorizations, gates **G2**/**G3**, or Dean's **D1–D9** deferral changed, and no
  agent touched a database. What a future session must not re-derive or silently reverse:

  **THE WRITE PATH RETURNED THE WHOLE RECORD ON EVERY ANSWER, and the fix needed a server-side
  decision first.** `POST .../answers` echoed every open blocking question back — measured
  1,772,692 B over 3,000 entries at 1,000 runs, twice per accepted answer. Bounding it was
  blocked by a real coupling, not by caution: the frontend's `confirmProposal` decided
  `submitAnswer` vs `editField` from MEMBERSHIP in that list, so a question outside a window
  read as "already answered" and took the edit route — **`422 unrecognized_field` on a
  legitimate first answer.** The route now tells the client which operation to use
  (`answer_at`), which is what made the bound safe rather than merely cheap. Per accepted
  answer at 1,000 runs: **3,545,986 B → 61,558 B (98.3%)**. `PENDING_WINDOW = 50`, and the
  window is ANCHORED — head plus every still-open question of the unit just written — so the
  answer you just gave is never withheld from you. `api.getPending` (unbounded, no parameters)
  **still exists and is still correct twice**, for Review Record and Export Readiness, which
  would UNDERSTATE outstanding work from a page. Do not "fix" those two.

  **THE DETAIL ROUTE COMPOSED EVERY RUN FIVE TIMES, AND DRY-RAN EVERY UNIT TWICE.** Threading
  one `export_units()` list through the response (`routes._shared_units`) took
  `resolved_run_draft` from 5× to 1× the run count; it left `export_draft` at **2×**, which an
  independent review measured as roughly HALF the request against ~3% for the composition. That
  is why the fully-answered gain was ~1.28× and not the 2.4× headline. `Experiment.dry_run_verdict`
  closes it (`routes._shared_dry_run`), and **the gate is the design**: it answers `None` while
  `pending_count() > 0`, which is exactly the union of `status()`'s and `export_ready()`'s
  short-circuits, because on a record that still owes questions the dry run is entered ZERO
  times and a naive "compute it once up front" would have turned 0 into N — making the common
  case slower to speed up the rare one. Both seams are **threaded, not memoised**: this module
  mutates an `Experiment` and re-reads its derived state in the same request, so nothing may be
  stored on the instance. Responses byte-identical across all 21 shapes;
  `test_detail_route_composes_each_run_once.py::_disable_threading` reverts all three seams and
  **silently failed to revert each new one until extended** — twice.

  **FOUR SURFACES CLAIMED SOMETHING THEY HAD NOT DONE, and CI passed all four.** An answer the
  record could not store returned **200** and reported the value "identical"; a conflict decision
  could never be recorded, so a scientist who fixed a typo owned a permanent conflict no surface
  could clear; the Assistant panel said nothing about whether a model was involved, in a build
  where every provider answers `501`; and the memory graph kept showing a deleted run. Each was
  found by independent review, not by a test.

  **`0003`+`0004` COULD NOT BE APPLIED WITHOUT `0005`, WHICH NOBODY HAD APPROVED.** `--apply`
  globbed every migration on disk, so the operator ask that `docs/dean-handoff-consolidated-2026-08-18.md`
  makes was **mechanically impossible** to satisfy. `scripts/db_migrate.py --through VERSION`
  fixes it, proven against a real `postgres:18` in CI. **This changes nothing about the hard
  stop:** applying any migration to the hosted environment is the operator's act, and no agent
  may do it.

  **TWO READ-PATH 500s, AND THE SECOND ONE TOOK DOWN THE WHOLE LIST SCREEN.** A persisted
  non-iterable `draft["pending"]` (e.g. `7`) made BOTH `GET /api/experiments/{id}` and
  `GET /api/experiments` return **500** — one malformed run draft took My Experiments down for
  every record. A wrong-typed top-level draft container (`assets: "not a list"`) did the same
  through `validate_draft`. Both are now **read, not refused**, and the distinction is the whole
  design: *a malformed value in a REQUEST can be refused, because the caller sent it and a typed
  422 names what to fix; a malformed value already PERSISTED cannot be refused to the reader, who
  did nothing wrong and whose record would simply vanish.* So the §11 "typed 422" precedent for
  the ANSWER path deliberately does **not** transfer to the READ path. `pending: 7` becomes one
  unreadable entry and the record stays blocked — truthful, because a document whose blocker list
  cannot be read must not be certified exportable. Nothing is coerced, parsed, or walked:
  `enumerate("abc")` would invent three per-position claims the draft never made.

  **AND THE §13 DISCLOSURE FOR THAT CHANGE WAS ITSELF FALSE FOR ONE COMMIT.** It said all ten
  top-level containers raised. **Eight** did; **`qc`** raised only when a series was present (and
  the guard is inside that same `if series:`, so `qc` is unchanged); **`block_evidence`** raised
  only when a series, link, contributor or the qc gate looked it up — so a draft with none of
  those **validated clean**, and that is the ONE verdict this change moves (PASS → FAIL). The
  false enumeration is what concealed it. It is a flip toward refusal on a document that could
  never have exported anyway (`export.build_sidecar` does
  `(draft.get("block_evidence") or {}).items()`), so **nothing that previously exported stops
  exporting** — and that third crash is now a clean refusal too. Four claim sites corrected in
  place, marked as corrections. **The pattern to remember: a table-driven test whose fixture makes
  every row reachable cannot see which rows were reachable before**, and it reads as an eleventh
  confirmation rather than as a missing case.

  **`attribution.uploaded_by` is server-stamped and still absent everywhere** — unchanged from
  2026-08-19, and re-verified: the stamp requires `trust_basis == verified_edge_assertion`, and
  **no verifier in this build mints that**, because no trusted authentication boundary exists
  (Dean reconfirmed the ClusterIP bypass, 2026-08-12). The seam stays unset.

  **Named rather than implied, and still not done:** `isaac_runs` Stage 2b (gated on the
  operator's two completeness queries, `docs/migration-approval-packet-0005.md` §8A); the
  campaign-sheet capture fields (technique, facility, sample, contributors — a record can be
  finished but not richly described); an apply route for `POST /ingestion/csv/preview`; the
  Evidence Graph / Compare Runs cross-feature work; ~~the `.section-tab` contrast item (3.86:1 at
  12.5px/500, and the narrow fix has in-repo precedent)~~ — **DONE, corrected 2026-08-27; see the
  struck item earlier in §11 for the evidence**; the human responsive / 200%-zoom
  visual sign-off; personal-deploy retirement; and **every hosted QA of every image from this
  session** — `/krish` sits behind an Authentik edge this environment cannot authenticate to, so
  the honest status is `HOSTED QA PENDING (Krish)`. `docs/dean-operator-addendum-2026-08-25.md`
  and `docs/angel-scope-questions-2026-08-25.md` are **prepared and UNSENT**; nothing in the
  programme is blocked on Angel's answer.

  **Two flaky frontend tests were found by CI and fixed, and both had the same shape as the
  honesty defects above: a test asserting more than it had established.** One sampled a counter
  of two independent effects after awaiting only one (`expected 1 to be 2` in Actions, green
  locally — reproduced on demand with a 120 ms probe, then fixed with `waitFor`). The other had
  raised testing-library's `asyncUtilTimeout` to 5,000 ms while vitest's own per-test deadline
  was **also** 5,000 ms, so the raised budget was unreachable and the failure read `Test timed
  out in 5000ms`, naming neither the query nor the DOM.

- **Session of 2026-08-26/27 — six PRs (#179, #182–#185, #187), and the recurring finding moved
  from "a surface claimed what it had not done" to "a claim was published without being
  measured."** Org `main` at `da889cb`. Backend tests **5,368 → 5,437**; frontend **4,390 →
  ~4,410**. Nothing about the hosted deployment, the external authorizations, gates **G2**/**G3**,
  or Dean's **D1–D9** deferral changed, and no agent touched a database. What a future session
  must not re-derive:

  **A `.venv` SYMLINK WAS COMMITTED TO `main` AND DESTROYED THE READER'S VIRTUALENV.** An agent
  working in a git worktree created it so its tests could find an interpreter; `git add -A` swept
  it in; it merged. `.gitignore` carried **`.venv/`** — with a trailing slash, which matches a
  **directory and not a symlink of the same name** — so it was never ignored and the mistake was
  invisible at every stage. `git checkout main` then replaced the real virtualenv **directory**
  with a symlink pointing at **itself**, and every `.venv/bin/python` failed with *"too many
  levels of symbolic links"* until the environment was rebuilt. **This broke tooling mid-session,
  twice** — the second time when `git stash` restored the tracked symlink over the freshly rebuilt
  venv. Rebuilding on the wrong Python (3.14 rather than the **3.12** this tree expects) then
  produced a `UnicodeEncodeError` at collection, which is a separate trap worth remembering. Fixed
  in #187: untracked, the **bare `.venv`** added to `.gitignore` beside `.venv/`, and a guard
  asserting **no tracked entry has git mode `120000`** — stated over the recorded mode, not over a
  filename, because the next one will not be called `.venv`.

  **AND THAT GUARD'S SECOND ASSERTION WAS WRITTEN, MEASURED, AND WITHDRAWN.** It forbade any
  tracked text file from embedding an absolute path under a home directory. Run, it flagged
  **twelve files, every one legitimate** — synthetic fixture paths (`/Users/someone/`,
  `/Users/me/`, `/Users/fake/`) and documentation examples — including
  `test_memory_graph_detail.py`'s `("home_absolute", "/Users/krishverma/secret.py")`, which is a
  **negative control proving redaction works**. Keeping it meant twelve exemptions on day one,
  the cries-wolf-then-gets-suppressed outcome its own comment predicted. **The withdrawal is
  recorded in the file** so nobody re-derives it and reaches the same twelve.

  **THE RESET DESTROYED RECORDS, REFUSED FOREVER, AND TOLD THE OPERATOR TO RETRY.** #183 made the
  list read tolerant while `_current_plan_row` stayed strict, so a malformed document entered the
  plan and the execute aborted **partway through the mutation loop**: preview said `refused:
  false, final_count: 5`, execute returned `412 plan_digest_stale` with `removed_count: 1` — the
  managed-legacy record destroyed, the malformed canonical not restored — and every retry with a
  fresh digest refused identically. `plan_digest_stale`'s documented meaning is *"recoverable in
  one further request"*. **And the reviewer's suggested predicate covered only 4 of 7 cases**:
  `draft`, `source` and `answer_log` set to a wrong-typed truthy value hydrate **strictly without
  error** and still diverge, so a raise-based test looks complete because the four loudest cases
  pass. **The predicate is reader disagreement.** The fix is a preflight inside `_reset_lock`
  before the mutation loop, answering **409 `malformed_records_present`** and naming ids only.
  **Both rows are built from ONE read** — reading twice would let a concurrent write masquerade as
  "malformed", a permanent-sounding reason for a transient condition.

  **AND #183'S OWN CLAIM WAS WITHDRAWN, NOT REWORDED.** It said the change was *"fail-closed, and
  strictly better than the preview 500 it replaces."* Fail-closed is true; **strictly better is
  false — the branch was strictly worse.** `main` returned 500 and destroyed nothing. The branch
  asserted success, destroyed, failed to restore, and misdirected. **The lesson generalises:
  fail-closed describes the DECISION, not its TIMING, and on a destructive path the timing is the
  whole thing.**

  **THE WIRE COULD NOT SAY WHETHER THE OFFICIAL VALIDATOR HAD RUN** (#185), which is why the same
  conflation recurred four times. `official_validator_ran` is now published, derived at the route
  from `official_report is not None`. Two payloads that differ only in that field were shown to be
  **identical on every other key**, asserted as a property. **The sixth consumer was invisible to
  every prior sweep**: ~~`lib/experimentGraph.ts` contains **2 NUL bytes**, so `rg`/`grep` dropped it
  and exited 0.~~ — **FALSE AT THIS HEAD, measured twice independently on 2026-08-30: 369 files
  under `apps/web/src`, ZERO containing a NUL byte; that file's NUL count is 0; `rg -l` and
  `rg -al` return the identical 63 files.** The file was rewritten since. The finding was real
  when written and the `-a` habit costs nothing — but **a future session must not skip an `rg`
  sweep of `apps/web/src` on the strength of this**, and must not cite it as a live trap.

  ***THE TRAP IS LIVE AGAIN, IN A DIFFERENT FILE, AND THE "DO NOT CITE IT AS LIVE" SENTENCE
  ABOVE IS THEREFORE WITHDRAWN AS A GENERAL CLAIM — measured 2026-08-31.*** Both halves of the
  2026-08-30 correction were true **of `experimentGraph.ts`**, and are kept for that reason. What
  was wrong was generalising a fact about ONE file into a fact about the tree. Re-measured at
  `bebf4e2` and again at `ddec2b5`: **379 files under `apps/web/src`, and exactly ONE holds a NUL
  byte — `components/RecordDescriptionPanel.tsx`, 2 of them**, a `rows.join('\0')` separator typed
  as a raw byte instead of an escape.

  **IT COST EXACTLY THE CONFUSION THIS ENTRY PREDICTED, AND IT COST IT TO THE RECORD-CAPTURE
  SURFACE.** `RecordDescriptionPanel.tsx` is the file implementing record-level field capture, so
  a `grep`/`rg` sweep for those inputs returned **nothing** and exited **0** — which is how three
  separate sessions came to believe the twelve free-text record paths *had no website input*. They
  had one, shipped in `7822b13`. The measurement that says so:

  ```bash
  grep -rl  RecordDescriptionPanel apps/web/src   # 2 files  <- the panel itself is MISSING
  grep -ral RecordDescriptionPanel apps/web/src   # 3 files  <- -a finds it
  ```

  **The durable rule, stated so it does not need re-deriving a third time: a `grep`/`rg` sweep of
  this tree is only evidence of absence when run with `-a`, and a zero-hit result without it is
  not a measurement at all — it is indistinguishable from a skipped file.** A mechanical guard now
  exists (`apps/web/src/__tests__/source-is-greppable.test.ts`) asserting no file under
  `apps/web/src` holds a NUL, so the next occurrence fails a test instead of costing a session.

  **AND THE SWEEP ABOVE WAS ITSELF SCOPED TOO NARROWLY — widened 2026-08-31.** "Exactly one
  file" is true of `apps/web/src`. Over **all tracked files** there are **three**, and the
  second one is the joke this entry deserves: **`docs/superpowers/plans/2026-07-27-phase-36v1-hosted-qa-fix-forward.md`
  held a literal NUL inside the sentence `raw NUL/SOH replaced with ...`** — a document
  *describing* this defect, made invisible by it, in the directory §16's resume protocol
  sends every new session to read. `grep -l "Phase 36V" <that file>` exited **1**; `grep -al`
  exited **0**. The byte is now the printable escape the sentence says it is, and the file is
  greppable. The third is `qa/validator-upload-package/isaac-validator-qa-files.zip`, a
  genuine binary and the **only** legitimate exemption — so widening the guard to tracked
  files costs **one** exemption, not the "binary fixtures and generated artifacts" (plural)
  that the narrow scope was justified by.

  ***A THIRD OPERATIONAL TRAP, MEASURED 2026-08-31 AND RECORDED BESIDE THE `.venv` SYMLINK
  AND THE SNAPSHOT CONFLICT, BECAUSE IT ALREADY PRODUCED ONE FALSE "SKIP REGRESSION" REPORT
  IN THE SESSION THAT FOUND IT:*** **any backend skip count measured in a git WORKTREE is
  `+2` against the same commit measured in the MAIN CHECKOUT.** `graphify-out/graph.json` is
  **gitignored and untracked** (2,609,140 bytes, dated 2026-08-07), so it exists in the main
  checkout and in **no worktree and no clone**. Exactly two tests gate on its presence —
  `apps/api/tests/test_memory.py:856` and `apps/api/tests/test_memory_graph_detail.py:1568`
  — and each names an unconditional sibling covering the same property, so they are genuine
  environment gates and **not** untested paths wearing one: run in the main checkout, those
  two files give **248 passed, 0 skipped**.

  **The consequence is a comparison error, not a defect.** A slice measuring `42 skipped` in
  its worktree, against a `40` quoted from a main-checkout run, has measured **no change at
  all**. Both numbers are correct; they answer different questions. Re-derive rather than
  trusting either:

  ```bash
  git check-ignore graphify-out/graph.json && echo "gitignored -> absent from every worktree"
  ```

  **Quote the environment with any skip count**, exactly as §15 now quotes a vantage point
  with every constraint-coverage figure. A skip total without its checkout is not a
  measurement.

  **And a seventh no payload-shaped sweep could find** — `VerdictCard`, reached
  through an adapter that returns a *different type*, was rendering **"FAIL — Invalid against
  official ISAAC schema v1.05"** about a record `validate_official` never opened.

  **A MEASUREMENT THAT CONTRADICTS THE OBVIOUS ORDERING RULE, worth carrying forward:** an
  unanswered freshly-created record reports `official_validator_ran: **true**` with `'descriptors'
  is a required property`, and its `draft.ok` is **true**. Anyone hand-writing the rule would have
  guessed the opposite on the most common failing payload in the product.

  **`ok and official_validator_ran` IS AN EQUIVALENT MUTANT** — it moves no verdict anywhere,
  because a pass is unreachable without the validator having run. That *is* §12's
  warning-cannot-turn-PASS-into-FAIL invariant demonstrated, and it is why that mutation had to be
  split into an inert one and a real one.

  **A PANEL TOLD THE SCIENTIST TO ENTER A VALUE ON 25 FIELDS, AND 7 ACCEPT NONE** (#182). Measured
  over all 25 paths × 5 write routes: **5** writable via `PATCH .../runs/{id}`, **13** via
  `/overrides`, **7** refused by all five — and ~~**on a record with no runs, none of the 25 is
  writable**, because both accepting routes are a run's~~ — **CORRECTED 2026-08-27: exactly one of
  the 25, `system.technique`, is now writable on a record with no runs**, through the record-level
  answers/edit operations added in the same session (see the correction two paragraphs below). The
  other 24 are unchanged and the "7 refused by all five" figure was re-derived and still holds. The copy is now per path. `block:attribution`
  accepted a contributor that **could never export**; the write now records the
  `user_confirmation` evidence it had already earned, reusing `complete.py`'s exact four-key shape,
  and stays fail-closed on contributor shapes the route does not check.

  ~~**`system.domain` HAS NO WRITE PATH ANYWHERE**, which is why setting `technique` or a facility
  field makes a record un-exportable-until-cleared. Declined deliberately: the correct fix is the
  stored derivation applied in `Experiment.resolved_run_draft`, and **the repository holds TWO
  stored expressions of that one rule with opposite confirmation postures** (`draft_builder`
  stores it directly; `inferability.system_domain` requires user confirmation and has no
  production caller). Deriving `domain` from `technique` would mean authoring a **37-entry**
  scientific classification that exists nowhere here — §5 forbids it.~~

  **REVERSED 2026-08-27, AND THE DECLINE IS KEPT STRUCK RATHER THAN DELETED, because a recorded
  deliberate decline is exactly the kind of claim a future session acts on.** Both
  `system.domain` AND `system.technique` now have a record-level write path
  (`POST /api/experiments/{id}/answers` to answer, `.../edit` to correct). **The decline was not
  wrong — it was answering a different question.** It declined *deriving* `domain` from
  `technique`, and that remains declined for exactly the reason given: the 37-entry classification
  does not exist here and §5 forbids authoring one. Re-measured 2026-08-27: `system.technique`'s
  enum has **37** values, so the figure was right.

  **What made it buildable was noticing the derivation was never required.** Both fields are
  **closed enums declared by the official schema itself** (`system.domain` → `["experimental",
  "computational"]`; `system.technique` → 37 values). A scientist **choosing** from the schema's
  own enum is a user confirmation over a bounded set, not a guess and not an inference — squarely
  inside §5. The writable set is **derived from the vendored schema at runtime** by three gates
  (declares an `enum` ∧ its parent declares it `required` ∧ `workspace.field_level` is
  experiment-level), which yields exactly those two paths and was re-derived independently by
  review over all 29 enum leaves. Nothing is transcribed, so it follows a schema refresh; an
  unreadable schema fails closed to refusing every such write.
  **Neither field is ever derived from the other, defaulted, or inferred** — a record given only
  one keeps the other missing, and stays blocked. The two stored expressions of the derivation
  rule (`draft_builder` vs `inferability.system_domain`) are **untouched**, and choosing between
  their opposite confirmation postures remains an open decision this did not need to take.

  **Measured before:** all five write routes refused both fields (`422 unrecognized_field`;
  `not_overridable` for `system.domain` at `/overrides`). **One cell of that table was wrong and
  is corrected here:** `field:system.technique` IS in `EXPERIMENT_OVERRIDABLE_ADDRESSES` and its
  run override returns **200 — accepting off-enum values**. That is **pre-existing**, not caused
  by this change, and is deliberately left alone: closing it breaks `test_run_api.py:2157` and
  needs its own argument.

  **A SCIENTIST CAN NOW RENAME A RECORD** (#184, `PATCH /api/experiments/{id}`, operations 69 →
  70). ~~**Discard was NOT built, and the reason is the finding:** §15 enumerates, per table, only
  `INSERT`s and `UPSERT`s — **no committed sentence permits a `DELETE`** — while
  `db_write.WriteStatementPolicy` **does not refuse one** (measured: `DELETE` against all eight
  app-owned tables is accepted; only `records` is refused). **Mechanical permission is not
  authorization.** A hard delete would also need **eight statements in dependency order across
  seven referencing tables, six of them append-only history**, none carrying `ON DELETE`.~~

  ***EVERY SENTENCE OF THAT PARAGRAPH IS NOW FALSE, AND ONE OF THEM WAS FALSE WHEN IT WAS
  WRITTEN. It is struck rather than deleted because "discard was not built" is exactly the kind
  of claim a future session acts on — by building it a second time.*** Re-measured 2026-08-30:

  - **Discard EXISTS.** `POST /api/experiments/{experiment_id}/discard` is registered at
    `routes.py:3179`, shipped in `d93b896` and merged in `6d5bda6` — **an ancestor of the very
    commit that wrote "was NOT built"**. So this was false on the day it was committed, not
    merely overtaken.
  - **The policy DOES refuse a `DELETE`, on five of nine tables**, and there are **nine** owned
    tables, not eight. Measured by importing `WriteStatementPolicy` and checking each:
    `isaac_experiments`, `isaac_runs`, `isaac_run_projection` and `isaac_schema_migrations`
    **accept**; the five append-only history tables are **refused** by a `_APPEND_ONLY_TABLES`
    guard that did not exist when the paragraph was written; `records` is refused as a table this
    application does not own.
  - **Four `DELETE` statements now execute** (`experiment_repository.py:1059`, `:1659`, `:1670`,
    `:1677`), not the "eight in dependency order" the paragraph forecast — because the five
    history tables are never reached.

  ***AND THE HALF THAT SURVIVES IS THE HALF THAT MATTERS: "MECHANICAL PERMISSION IS NOT
  AUTHORIZATION" IS STILL TRUE, AND THIS IS A FIFTH INSTANCE OF THE PATTERN §15 DOCUMENTS FOUR
  TIMES.*** No sentence in §15 permits a `DELETE` against any table. The four that execute rest
  on an authorization `experiment_repository.py:1606` itself calls *"the project owner's narrow
  one"* — i.e. conversational, exactly as `isaac_runs`, the five submission-lifecycle tables and
  `isaac_run_projection` each were before being named. **§15 is corrected below to name it**, so
  the basis is committed rather than conversational. The durable lesson is unchanged and is now
  five-for-five: a slice that cannot cite a committed sentence permitting what it does has not
  established its authorization basis, and saying so is part of the slice.

  **Named rather than implied, and still not done:** ~~the `.section-tab` contrast fix is written
  but its **~40 Linux baseline cells need a CI round-trip** to transcribe (PR #186)~~ —
  **DONE, corrected 2026-08-27.** PR #186 merged as `1dd28ad`, and the round-trip happened:
  **119** cells, not ~40, transcribed from CI run 33025558592 at head `2da0c71`
  (`e2e/a11y-baseline.ts`, "`.section-tab` TRANSCRIPTION, 2026-08-27", linux 2802 → 2431).
  This is the THIRD site in §11 asserting the same stale item; all three are corrected in
  the same change, because "the item is closed" is itself a checkable claim and a
  partially-swept correction is what this file has been caught publishing before.
  **A NEW residue this closure created and then closed:** the darwin half of those 119 cells
  was REASONED, and no CI job can ever judge it (`grep -rn 'macos\|darwin' .github/workflows/`
  returns nothing). A local macOS run on 2026-08-27 at `7668bf8` measured it — 149 of 168
  cells confirmed, **19 corrected**, `A11Y_BASELINE_TOTAL_NODES.darwin` 2161 → **2435** — and
  found that **15 of the 20 recorded "platform splits" were not platform differences at all
  but a stale darwin column** — all 15 collapsed back to scalars. Two of the remaining five
  (`memory-graph@zoom-200`, `validator@zoom-200`) reproduced exactly and are now confirmed
  rather than assumed; the other three had a darwin half that was wrong while the difference
  was real, and one scalar became a genuine split. `DARWIN_CARRIED_FORWARD` now makes a
  carried-forward darwin half distinguishable from a measured one; `isaac_runs`
  Stage 2b; an apply route for `POST /ingestion/csv/preview` — **which is NOT residual work but a
  committed human decision** (*"Option 1 — reconciliation-only … a deliberate authority boundary,
  NOT a defect"*); ~~the Evidence Graph / Compare Runs cross-feature work~~ — **DONE, corrected
  2026-08-30: `apps/web/src/components/RunCompare.tsx` and `run-compare.css` exist, and
  `7a66127 feat(evidence graph)` and `5b99807 feat(compare runs)` are both ancestors of HEAD**;
  the human responsive /
  200%-zoom sign-off, which **no CDP method, flag or API can drive** and is therefore not
  automatable at all; personal-deploy retirement; and **every hosted QA** — `/krish` sits behind an
  Authentik edge this environment cannot authenticate to.

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
  no LLM; a **production** Tier-2 LLM/generative provider remains out of scope unless explicitly
  approved — see the narrowing immediately below
- **AI / MCP / voice IMPLEMENTATION against deterministic fake providers — authorized by the project
  owner 2026-08-12.** MCP, Connect Your Agent, the native LLM assistant, transcription/voice and the
  provider architecture may be **built**: code, APIs, UI, auth abstraction, provider abstraction,
  tests, error handling, security boundaries. **Dean DEFERRED D1–D9 on the same day** — *"leave AI
  integration as future work rather than increasing scope at this point"* — so **no production
  endpoint, credential, network path, billing arrangement or provider approval exists or is
  authorized**, and none may be created. *Implementation complete* and *production provider
  configured* are different milestones; the absence of the second is not a reason to skip the first,
  and reaching the first is not permission to claim the second. `ai-integration-decision-packet.md`
  §6 binds in full — above all **no fake `Connected` state** and **no model output in the truth
  path** — as does §9's *"build nothing that implies any of it exists"*
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
  laptop or from CI, ~~writes of any kind~~, and per-record hosted display remain out of scope.

  *Narrowed again 2026-08-12, for AI only:* "external model provider / LLM" above continues to mean a
  **production** provider — an endpoint, a credential, an outbound call, a charge — and that stays out
  of scope, reinforced rather than relaxed by Dean's deferral of D1–D9. **Building the capability
  against a deterministic fake provider is separately authorized by the project owner**; see the
  in-scope entry above. **Identity/role enforcement is likewise still out of scope**, and Dean's
  2026-08-12 authorization of username stamping does not change that: it is conditional on a trusted
  authentication boundary ISAAC has not built, and Q4's answer is that the Service can be reached
  in-cluster without traversing Authentik at all.

  ***Narrowed again 2026-08-07 — "any database write" is NO LONGER a blanket prohibition.*** The
  project owner lifted it **narrowly**, for one bounded feature: **durable Create Experiment
  persistence in the existing app-owned PostgreSQL database**, plus the minimum supporting persistence
  architecture that feature requires. The strikethrough above is deliberate — the old wording is kept
  visible so a future session can see that this is a recorded change of scope and not a drift.

  **What the lift covers:** app-owned tables for experiments and their normal application state
  (`isaac_experiments`, `isaac_schema_migrations`, — **added 2026-08-12** — `isaac_runs`, and —
  **added 2026-08-16** — the five submission-lifecycle tables `isaac_experiment_revisions`,
  `isaac_run_revisions`, `isaac_revision_changes`, `isaac_submissions` and `isaac_submission_runs`,
  and — **added 2026-08-19** — `isaac_run_projection`);
  a swappable repository seam
  (`apps/api/isaac_api/experiment_repository.py`) with a filesystem fallback whenever `PGHOST` is
  unset; a separate write path (`db_write.py`) with parameterized SQL, explicit transactions and
  deterministic rollback; and forward-only, idempotent migrations
  (`apps/api/isaac_api/migrations/`, runner `db_migrate.py`, operator CLI `scripts/db_migrate.py`).

  ***`isaac_runs` was written to before this sentence named it, and that is recorded rather than
  quietly corrected.*** The 2026-08-07 lift enumerated two tables. `0002_runs` was reviewed,
  approved and applied on the strength of its own packet, and the shadow-write slice then wrote the
  table — but **no committed sentence in this file named `isaac_runs` as in-scope for writes**, so
  that slice's authorization basis was the owner's instruction plus the approval packet, and not
  this list. The implementing agent found the gap itself and reported it rather than proceeding
  quietly; the list is corrected here so the basis is committed rather than conversational. The
  general rule stands: **a slice that cannot cite a committed sentence permitting what it does has
  not established its authorization basis, and saying so is part of the slice.**

  ***`isaac_run_projection` IS NAMED HERE — ONE COMMIT AFTER THE TABLE SHIPPED, and that is the whole
  point of the two corrections below.*** Twice now a slice has added a table to
  `db_write.OWNED_TABLES` that no committed sentence in this file named — `isaac_runs`, found and
  reported by the implementing slice, and the five submission-lifecycle tables, found only by an
  independent review. **The third time it is a SMALLER correction and still a correction — and the
  slice published a claim that it was not.** `db_write.py`, the Stage-2 contract and the `0005`
  packet all said "named in the same change that creates it"; an independent review measured that
  false by one commit (the table shipped in `6dce6fd`, §15 was updated in `8f7c650`).
  **`isaac_run_projection`
  (`0005_run_projection`)** is the per-experiment completeness claim for `isaac_runs`: one row per
  experiment recording the `(rev, generation)` its run rows were projected from, how many were
  written, and which projector wrote it.

  ***AND THAT CORRECTION WAS ITSELF INCOMPLETE — THE FOURTH INSTANCE OF THIS PATTERN, AND THE FIRST
  IN WHICH THE FIX RATHER THAN THE CLAIM WAS THE DEFECT.*** ~~"and all four artifacts now carry the
  correction in place"~~ — **struck 2026-08-24, because a SECOND independent review measured it
  false.** Three carried it: `db_write.py:176-186`, `docs/isaac-runs-stage-2-contract.md` §5, and
  `apps/api/tests/test_experiment_repository.py:839`. **The `0005` operator packet did not** — its
  §10 still read *"added in the same change that creates the table"* and *"This is the first time the
  sentence exists before the table is written"*. So for one commit this file asserted the completeness
  of a correction whose most consequential copy was missing, in the one artifact an operator actually
  reads before acting. Packet §10 now carries it, and this sentence records that the completeness was
  published before it was true. **The durable lesson is not "enumerate the table earlier" — that has
  been learned three times. It is that a correction sweep needs the same enumeration-and-measurement
  discipline as the claim it corrects: "all N artifacts are fixed" is itself a checkable claim, and
  this one was published unchecked.** The same sweep also miscounted a second enumeration — the
  `never_projected: 0` claim sat in FIVE committed artifacts, not four, the uncounted ones being
  `0005_run_projection.sql`'s own header and the `0005` packet's §11; both are corrected in place.

  **Why it has to exist at all, measured rather than argued:** `SELECT ... FROM isaac_runs WHERE
  experiment_id = %s` returning zero rows means EITHER "this experiment has no runs" OR "its runs
  were never projected", and both are reachable — the second is the normal state of every experiment
  persisted before the shadow write shipped, and of every save in the window between a merge and the
  operator applying the migration. A read cutover that treated zero rows as "no runs" would silently
  delete every run of every pre-existing record and report success. The contract is
  [`docs/isaac-runs-stage-2-contract.md`](docs/isaac-runs-stage-2-contract.md); the operator packet
  is [`docs/migration-approval-packet-0005.md`](docs/migration-approval-packet-0005.md).

  **What listing it covers, precisely:** creating it by an owner-applied migration, and writing it
  through the ONE statement `experiment_repository.Q_UPSERT_RUN_PROJECTION`, inside the same
  transaction and the same accepted branch as the run rows it describes. ~~It covers **no read** —
  exactly one statement in the application names the table and nothing reads it, pinned by test~~
  — **FALSE NOW, re-measured 2026-08-30: THREE statements name it** — the write path's stamp, the
  Stage-2b reader (`FROM isaac_run_projection WHERE experiment_id = ANY(...)`), and the discard's
  delete. Stage 2b IS this build, and `/api/health` says so on the wire
  (`run_projection.authoritative: true`). The two halves of the old gating claim that DO survive:
  `0005` is still **not owner-approved**, and the backfill has still **never been run anywhere** —
  and **no** hosted application of `0005`. **Making `isaac_runs` a read source (Stage 2b) is still a
  separate decision and is gated on the backfill having RUN with every one of its
  `UNREADABLE`/`refused`/`failed` counts at 0, AND on the operator's two completeness
  queries (`docs/migration-approval-packet-0005.md` §8A) both returning 0. ~~"the backfill
  having RUN and reported `never_projected: 0`"~~ — **corrected 2026-08-20: no script prints
  that word and none can, because the backfill deliberately never reads
  `isaac_run_projection`.** The gate is a query an operator runs, not a number a script
  prints, and the strikethrough is kept so this reads as a corrected claim rather than a
  drifting one;
  removing `runs` from the experiment document is a third decision and is justified by no
  measurement in this repository.**

  ***The five submission-lifecycle tables were added to `db_write.OWNED_TABLES` before this list
  named them — the same failure as `isaac_runs`, a second time, and recorded rather than quietly
  corrected.*** The submit slice (`0003_revisions`, `0004_submissions`) added
  `isaac_experiment_revisions`, `isaac_run_revisions`, `isaac_revision_changes`, `isaac_submissions`
  and `isaac_submission_runs` to `OWNED_TABLES` — which it had to, because the statement policy
  refuses a `CREATE TABLE` naming an unlisted table, so the migration could not run at all otherwise.
  **No committed sentence in this file named those five**, so that slice's authorization basis was
  the project owner's instruction plus this lift's *"minimum supporting persistence architecture that
  feature requires"* clause, and **not** the enumeration above. Unlike the `isaac_runs` slice, the
  implementing slice did **not** find and report the gap; an independent review did. The list is
  corrected here so the basis is committed rather than conversational, and both approval packets now
  carry an explicit **"Authorization basis"** section saying the same thing. **This is a recorded
  scope extension, not a pre-existing permission written down late.**

  **What listing those five covers, precisely:** creating them, by an owner-applied migration, and
  writing them through `submission_store.py`'s append-only `INSERT`s. It covers **no** read surface
  over the history, **no** change to `records`, and — per the hard stop below — **no hosted
  application of `0003` or `0004`**.

  ***APPROVAL STATUS CHANGED 2026-08-17, and only one of the two halves moved.*** The sentence above
  used to end *"both of which remain NOT APPROVED and NOT APPLIED anywhere"*, and it is corrected
  rather than deleted because the two halves are different people's acts and the old wording bundled
  them. **The project owner (Krish) has now APPROVED the exact bytes** of `0003_revisions` and
  `0004_submissions`, conditional on five mechanical checks that were performed and recorded — digests
  match the packets, the SQL has had exactly one version ever (commit `0896b07`, never since touched),
  prior review findings remain resolved, and a structural safety scan found no new defect. See
  [`docs/migration-approval-packet-0003.md`](docs/migration-approval-packet-0003.md) §12D and
  [`-0004.md`](docs/migration-approval-packet-0004.md) §12D. **HOSTED APPLICATION REMAINS NOT DONE AND
  IS NOT THE AGENT'S ACT** — owner approval is a precondition for the operator's step, never a
  substitute for it, and the hard stop below is unchanged in every respect.

  **A second, separate correction made in the same change, because a test was enforcing a false
  claim.** Both packets' §12B asserted *"No PostgreSQL has ever executed this file"*, and
  `test_the_packets_do_not_claim_a_hosted_application` **required that literal to be present**. The
  sentence named its own expiry condition (*"until the `postgres-migration` job runs"*); that job has
  since run and passed on `main` **twice over**, applying `0001`–`0004` forward against a `postgres:18`
  container against input each should reject, and proving the rollback order: at `fe374c0` (Actions run
  [`32099627898`](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/32099627898)), and
  again at `c153ec9` (Actions run
  [`32800763199`](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/32800763199), job
  `97660962127`, conclusion `success`) — which is the run that matters for the numbers below.

  **THE CONSTRAINT NUMBER IS TWO NUMBERS, AND THIS BULLET CONFLATED THEM.**
  ~~"exercising **41 of the 46 declared constraints** (27 when that sentence was written)"~~ — struck
  in place, because that attributes to run `32099627898` a coverage it could not have produced, in the
  paragraph an operator reads before applying a migration. Adopt the split
  [`docs/migration-approval-packet-0003.md`](docs/migration-approval-packet-0003.md) §12B already uses:

  The table below had TWO rows on 2026-08-24 and has THREE now — the third supersedes the second
  without deleting it, because the second was a correct reading of the evidence that then existed:

  | | Number | Re-derived by (2026-08-24, third row 2026-08-25) |
  |---|---:|---|
  | **What a real PostgreSQL HAS executed**, at `fe374c0` on `main` | **27 of 46** | `git show fe374c0:.github/workflows/ci.yml`, counting the distinct declared names a `refuse()` call blames |
  | ~~"**Declared in the workflow and NOT YET RUN on `main`**, at this branch's HEAD"~~ — **RETIRED 2026-08-25, see the row below** | ~~41 of 46~~ | the same measurement over the working tree / `git show HEAD:.github/workflows/ci.yml` |
  | **What a real PostgreSQL HAS executed**, at `c153ec9` on `main` — the row that supersedes the one above | **41 of 46** | the same measurement over the working tree, which `git diff origin/main -- .github/workflows/ci.yml` shows is byte-identical to `main` |

  ~~"The fourteen extra constraints arrived in **`77de2db`** (2026-08-19), which **`git merge-base
  --is-ancestor 77de2db origin/main` reports is NOT in `main`**"~~ — **the commit is now IN `main`**
  (that same command exits 0), having merged on 2026-08-25 via `c153ec9`, so the fourteen have run. The
  `refuse`/`refuse_by_the_table` mention count moved 53 → 86 over the same span (`git show
  fe374c0:.github/workflows/ci.yml` vs. the working tree). So ~~"`fe374c0` could only ever have
  exercised 27, and **41 is a property of the workflow file, not of any run this repository can point
  to**"~~ — the first half is permanently true and is why 27 must keep its vantage point; the second
  half **expired the moment `c153ec9` merged**, and the run this repository can now point to is
  `32800763199`. **Confirmed from that run's own output, not merely from the file**: its step prints one
  `refused as designed by <object>` line per case, and intersecting the **58** distinct objects those
  **67** OUTPUT lines name with the 46 declared in `0003`+`0004` gives exactly **41**, and exactly the
  same five absent names. ~~"the 57 distinct objects those 70 lines name"~~ — **RE-MEASURED 2026-08-25
  and both figures were wrong**, in a sentence whose whole point was that the number came from the run
  rather than the file. **70** is every line containing the phrase; **3 of those are Actions echoing
  the `run:` block's own shell source** (`echo "refused as designed by $3: $1"`), so the OUTPUT count
  is **67**. And **57** reproduces under no counting at all: it came from a truncating regex
  (`[A-Za-z0-9_.]*`) that collapsed the three `column "…"` objects and captured the **empty string**
  for the three echoed lines, so an empty string was counted as an object (53 + 4 = 57). The correct
  figure is **58**. Re-derive rather than quoting:

  ```bash
  gh api repos/ISAAC-DOE/isaac-metadata-assistant/actions/jobs/97660962127/logs > /tmp/job.log
  # then split on the FIRST ": " after the phrase, and drop lines carrying the unexpanded `$3`
  ```

  **41 is unchanged and is the figure that matters** — it is an intersection with the declared set,
  and neither miscount touched it.

  ~~"17 declared constraint names appear nowhere in the workflow"~~ — also stale, and the same edit
  left it standing beside a "41 of 46" that implies **5**. Both figures are now stated with their
  vantage point: at `fe374c0`, **17** declared names appeared nowhere in the workflow and **19** were
  unblamed; at `c153ec9` on `main` (and at this branch's HEAD, which carries the identical workflow),
  **3** appear nowhere (`isaac_submission_runs`' `unit_id_shape`, `record_id_shape`
  and `run_id_shape`, proved refused through the deliberately weaker `refuse_by_the_table` because the
  table's equality CHECKs subsume them) and **5** are unblamed (those three plus
  `isaac_revision_changes_revision_fk` and `isaac_submissions_experiment_fk`, which are named for other
  reasons with no refusal driven off them). The packets' §12B lists them. Nothing suggests any of them
  is wrong; the packets may simply not be cited as evidence that they behave. So the repository was mechanically requiring itself to keep
  asserting something untrue, with the test reading as evidence of honesty. The guard now pins the
  **invariant** — that the packets do not read as hosted-applied — and a paired negative control
  asserts the expired sentence survives only as a quoted correction. **What CI still does not prove is
  unchanged and is the whole reason the operator's act is separate:** the container is empty, with a
  two-row synthetic stand-in for `records`, so *"behaves against the real data, roles and grants"*
  remains unproven.

  **What writing `isaac_runs` covers, precisely:** a SHADOW write only. Rows are maintained as a
  pure function of the experiment document inside the one existing durable write, and **nothing
  reads them**. The document remains authoritative, `state` keeps its `runs` key, and no read path,
  route or scientist-visible behaviour changes. Making `isaac_runs` a read source, and removing
  `runs` from the document, are separate decisions that are **NOT** covered here — the second is
  not justified by any measurement in this repository, and the brief that motivates it ("contract
  §8 D7") is cited by several files and committed to none of them.

  ***DELETE IS NAMED HERE, 2026-08-30 — THE FIFTH TIME A STATEMENT CLASS REACHED THE WRITE PATH
  BEFORE ANY COMMITTED SENTENCE NAMED IT, AND THE FIRST TIME IT IS A STATEMENT CLASS RATHER THAN A
  TABLE.*** `isaac_runs`, the five submission-lifecycle tables, `isaac_run_projection`, and the
  incomplete correction sweep that followed are the first four; this is the fifth, found by an
  independent truthfulness sweep rather than by the implementing slice. **What is covered:** the
  four `DELETE` statements the discard path executes — `Q_DELETE_EXPERIMENT`,
  `Q_DELETE_RUNS_FOR_EXPERIMENT`, the run-pruning delete at `experiment_repository.py:1059`, and
  `Q_DELETE_RUN_PROJECTION_FOR_EXPERIMENT` — against `isaac_experiments`, `isaac_runs` and
  `isaac_run_projection` only, inside the discard transaction. **What is NOT covered, and is
  refused mechanically as well as textually:** any `DELETE` against the five append-only history
  tables (`db_write._APPEND_ONLY_TABLES` raises), any `DELETE` against `records`, and any
  `TRUNCATE` or `DROP` of anything. The mechanical guard and this sentence must agree; if a future
  slice widens one, it widens both in the same change.

  **What it does NOT cover, and each of these is still out of scope:** modifying the
  production-derived 30-record `records` table (the write path's statement policy refuses any
  statement naming it); the verification truth plane; official validator/export behaviour;
  Dean-owned infrastructure; destructive migrations, `DROP`/`TRUNCATE`/`ALTER` of anything, or broad
  schema cleanup; per-record hosted display (still **closed by default**, gate **G2**); and any
  weakening of the read-only guarantees on `db_provider`/`db_recon`, which are unchanged.

  **The hard stop:** implementation and local/CI testing are authorized; **applying any migration to
  the hosted environment is NOT.** The owner reviews the migration text before it is applied. Do not
  request a kubeconfig, a port-forward, or a Secret, and do not connect to the SLAC database — the
  rule at `2026-07-24-phase-37-readiness-plan.md:48-52` is untouched by this lift. **This hard stop is
  UNCHANGED by the fact that both `0001` and `0002` are now applied to the hosted database
  (2026-08-09 and 2026-08-12, both by Dean).** Two migrations having been applied *by the
  infrastructure owner* is not a precedent, a delegation, or a standing permission; `0003` and later
  each need their own packet, their own owner approval, and their own operator action. CI proves the
  migration against a `postgres:18` service container (`.github/workflows/ci.yml` →
  `postgres-migration`), which is **not** the same as proving it against the hosted database with its
  real data; see `docs/create-experiment-persistence.md`.

  **Tutorial isolation is unchanged and is the invariant this feature must not break:** a
  worked-example session is temporary and synthetic and is NEVER persisted as a normal experiment.
  Enforced three times — the save hook skips any non-`None` `session_id`,
  `PostgresOrdinaryStore.refuse_if_not_persistable` raises on one, and it raises on a canonical
  example id in any scope.

***APPLICATION-SIDE SCOPE EXTENSION — PROJECT OWNER, 2026-08-29.*** **This is a NEW authorization
granted on that date. Nothing below was authorized before it, and no earlier slice may cite it.**
`docs/ingestion-proposal-contract.md` §8.1 said *"No committed sentence authorizes building it. A
slice that implements it must establish and cite its own authorization basis."* **That sentence was
TRUE when it was written and is SUPERSEDED as of 2026-08-29 — not retroactively false.** It is
struck in place in that document rather than deleted, for the reason this section has struck rather
than deleted four previous scope corrections: a reader must be able to see a recorded change of
scope and not mistake it for a drift.

  **What is authorized, APPLICATION-SIDE ONLY:** persistent ingestion proposals and the durable
  contract they need; the scientist-facing Experiment Data Workspace, and website proposal review,
  edit, acceptance, rejection, deferral and conflict handling; complete campaign-sheet write
  coverage within the limits below; the remote MCP and bounded change-feed application architecture;
  the disabled-by-default OAuth resource-server implementation; the verified-principal and
  server-stamped attribution work buildable inside ISAAC; the least-disruptive accessible
  palette/token decision needed to close **A11Y-01**, plus **A11Y-06**, **LAYOUT-01** and
  **LAYOUT-02**; and the associated tests, documentation, migration artifacts, PRs and safe
  integration.


  ***PROVENANCE OF THIS GRANT, STATED BECAUSE A REPOSITORY CANNOT WITNESS A
  CONVERSATION.*** This authorization reaches the repository as an **owner instruction
  relayed in-session** — the same evidentiary class as the Dean answers this section
  records as *"OPERATOR TESTIMONY ABOUT INFRASTRUCTURE CONFIGURATION … not an
  observation by this repository and no artifact backing it is committed here."* **No
  evidence file, packet or transcript backs it, and authorship witnesses nothing**:
  every commit in this repository is authored by the project owner with Claude
  co-authored, so a commit author cannot distinguish a granted scope from an assumed
  one. An independent audit of the implementing branch raised exactly this and was
  **right to**: a branch's own prose is not proof of its own authorization, and the
  sentence being cited was written one commit earlier by the same work that cites it.
  What a reader CAN check mechanically is the BOUNDARY — this entry is dated, names
  what is and is not covered, forbids any earlier slice from citing it, and adds no
  table. What a reader CANNOT check from inside the repository is that the instruction
  was given. **Only Krish can confirm that.** The honest entry is that the repository
  records the DECISION, not its DELIVERY — and no slice may cite this entry as though
  the repository had verified it.

  **What is NOT authorized, restated here so the boundary is committed rather than conversational:**
  applying any hosted migration; modifying `isaac-k8` or any SLAC infrastructure; bypassing
  Authentik; hunting for or repurposing secrets; creating provider accounts, enabling billing, or
  incurring any charge; sending real scientific data, transcripts or audio to an unapproved
  provider; exposing production-derived records or the five withheld aggregates (**G3**); deploying
  a replacement personal Vercel/Railway environment; acting as Krish, Dean, Angel or a database
  operator; making Angel's scientific classification decisions; claiming the human 200%-zoom gate
  was automated; mass-deleting remote branches; or adding an apply route for
  `POST /ingestion/csv/preview` — whose reconciliation-only authority boundary remains a **committed
  human decision, not residual work**. Dean's **D1–D9** deferral is UNCHANGED by this: implementation
  against deterministic fakes is authorized, a production provider is not.

  ***NO NEW TABLE IS ADDED, AND THAT IS A DELIBERATE CONSEQUENCE OF THIS ENTRY, NOT AN OVERSIGHT.***
  Proposals are stored at `state["proposals"]`, beside `state["notes"]`, inside the experiment state
  document. **`db_write.OWNED_TABLES` is UNCHANGED.** This is the **first** scope extension in this
  section that adds no table, and it is deliberate: this section records **four** separate occasions
  on which a table reached `OWNED_TABLES` before any committed sentence named it — `isaac_runs`, the
  five submission-lifecycle tables, `isaac_run_projection`, and the incomplete correction sweep that
  followed — and a fifth is avoidable by not needing one. Two consequences, stated rather than left
  to be discovered: a proposal is durable **exactly where the experiment document is durable and no
  more**, and a feature that needed `0006` would be a feature that does not work until an operator
  acts, which is a hard stop this authorization does not lift. **The persistence LOCATION was already
  covered** by the 2026-08-07 lift's *"app-owned tables for experiments and their normal application
  state"*; it is the FEATURE that needed authorizing, and a slice should cite that sentence for the
  location rather than re-argue it.

  **One consequence a future session must not read as a defect:** the acceptance route answers
  **`409 human_actor_required`** in every default-configured deployment, because no trusted
  authentication boundary exists in this build (Dean reconfirmed the ClusterIP bypass, 2026-08-12).
  That is a CONFIGURATION fact, not a build defect, and no application change can close it. It is
  exercised in CI through the deterministic fixture verifier.

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
| **3+** — PostgreSQL record repository, record loading, upload writes | **NOT authorized.** Later sequential slices, each independently reviewed. Gated on the Slice 2A hosted report. **Do not read this row as covering the 2026-08-07 lift**: that authorizes storing experiments THIS APPLICATION CREATES in its own new tables. It authorizes no repository over `records`, no record loading, and no upload write. |
| **Create Experiment durable persistence** (`isaac_experiments`) | **authorized 2026-08-07**, narrowly — see the scope note above. Implementation and local/CI testing only; **applying the migration to the hosted database is the owner's act, not the agent's.** Dean applied `0001_experiments` to the hosted database on **2026-08-09** ([evidence](docs/evidence/hosted-0001-verification-2026-08-09.md)) — which changes nothing about gate **G2**, gate **G3**, or the prohibition on an agent connecting to that database. ~~which changes nothing about `0002` (still unapplied and unauthorized for hosted application)~~ — **superseded 2026-08-12, see the next row.** |
| **`0002_runs`** (the `isaac_runs` table) | **APPLIED TO THE HOSTED DATABASE BY DEAN, 2026-08-12 00:30 UTC** ([evidence](docs/evidence/hosted-0002-verification-2026-08-12.md); packet [`docs/migration-approval-packet-0002.md`](docs/migration-approval-packet-0002.md), STATUS + §12C). Both SHA-256 digests Dean reported were **recomputed here and MATCH** the committed files, so the bytes applied are the bytes Krish approved on 2026-08-11. Verified from the hosted server: table, PK, FK, five CHECKs, the index, no `ON DELETE`/`CASCADE`, row count **0**, idempotent re-run, app health OK / `postgres` / `durable`. **Operator testimony, not a captured artifact** — no agent connected to that database. **NOT reported, and named as gaps:** the `records` and `isaac_experiments` before/after counts (packet postchecks 1 and 2) and the hosted engine build string. **The table existing is NOT permission to write it** — the run write path is a later, separately-reviewed slice, and `db_write.OWNED_TABLES` listing `isaac_runs` "grants nothing on its own". |
| **`0003_revisions` + `0004_submissions`** (the five submission-lifecycle tables) | **APPROVED BY THE PROJECT OWNER 2026-08-17; NOT APPLIED TO THE HOSTED DATABASE, ANYWHERE.** Two different people's acts — see the paragraph above and each packet's STATUS block. They are ONE decision (`0004` declares a foreign key into a table `0003` creates) and must be applied together or not at all. Proven forward, rollback and wrong-order-refusal against a `postgres:18` container in CI; **a real PostgreSQL has now executed cases blaming 41 of the 46 declared constraints on `main`** — run `32800763199`, job `97660962127`, at `c153ec9`, step *"Prove every 0003 and 0004 constraint rejects what it claims to reject"*. **THREE LAYERS OF CORRECTION SIT ON THIS ONE FIGURE AND ALL THREE ARE KEPT, because the sequence is the point: 41 (false) → 27 (true) → 41 (true, by a different run).** (i) ~~"**41 of the 46 declared constraints** are exercised there (27 until 2026-08-19)"~~ credited a run with a file's coverage. (ii) The 2026-08-24 correction — the workflow DECLARES 41, of which **27** had been executed on `main` (`fe374c0`, run `32099627898`), the other fourteen sitting in `77de2db` which was not in `main` — was right, and its instruction ~~"**An operator weighing this evidence should read 27, not 41.**"~~ is **RETIRED 2026-08-25**: `77de2db` merged to `main` via `c153ec9` (`git merge-base --is-ancestor 77de2db origin/main` now exits 0) and run `32800763199` executed the 41. **An operator should now read 41, and 27 remains the correct figure for run `32099627898` at `fe374c0` — that correction was overtaken, not wrong.** Three of the five still-unblamed cannot be blamed individually because the table's equality CHECKs subsume its shape CHECKs. Applying them is the operator's act, and no agent may do it. |
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

**The authorized private verification mode HAS RUN (2026-08-08), verdict
`PRIVATE_30_VERIFICATION_PASS`.** Terminology first, because it has been got wrong: this is the
**authorized private verification mode** — a bounded diagnostic/verification path over the
authorized 30-record production-derived corpus that returns only sanitized aggregate results. It
is not a "privacy mode" and not a user-facing toggle. It was unreachable until `e710f4a` gave the
verification route a `?mode=` parameter; it then executed **twice** on the deployed application.
Reported: 30 records read, official validation **30 passing / 0 failing**, **0** unexpected
mutation outcomes over 9,136 applicable trials, **0** oracle failures, `dml_statements: 0` and
`ddl_statements: 0`. **The limits are as load-bearing as the verdict and must travel with it:**
the figures are **operator-relayed testimony, not a captured artifact** (no response body exists
in this repository, by design); only *some* of the safety conditions were measured per-run, and
that condition list is a **reconstruction written ~7 hours after the run**, not pre-registered
criteria; **no database row was re-read and compared** after the sweep (the connection closes
first); and the corpus leak scan **did not run** in this mode — a corpus-free structural audit
stood in, and that skip is a *design decision* (the corpus is not retained past the sweep), not
an impossibility. **No image build or rollout was observed from this environment**, so nothing
about which image `/krish` serves is verified here. Evidence, with every qualification attached:
[`docs/evidence/private-30-verification-2026-08-08.md`](docs/evidence/private-30-verification-2026-08-08.md).

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

~~**`X-authentik-uid` is present**, so it is now a live candidate for ISAAC's canonical internal key
alongside the username, which remains the required compatibility key for upstream ownership/ACL rows.
**Neither is confirmed** — UID permanence is **Q17**, username non-reassignability is **Q5**, and both
are institutional lifecycle facts no observation can settle.~~ **Superseded 2026-08-12 — see the next
block.**

### DEAN ANSWERED THE IDENTITY QUESTIONS, 2026-08-12 — and the trust boundary went the UNSAFE way

**Everything in this block is OPERATOR TESTIMONY ABOUT INFRASTRUCTURE CONFIGURATION**, relayed by the
project owner. It is **not** an observation by this repository and no artifact backing it is committed
here. Durable record, with every qualification:
[`docs/identity-trust-contract.md`](docs/identity-trust-contract.md) §2, §6A.1, §7, §10.1.

**Read the bad news first, because everything else is conditional on it.** Dean **reconfirmed the
bypass**: the Service is a **plain ClusterIP with no NetworkPolicy**, so any in-cluster pod can reach
the app directly and **can forge forwarded identity headers**.

> **THE PRESENCE OF `X-authentik-username` ALONE DOES NOT PROVE AUTHENTICATED EDGE TRAVERSAL.**

That is **Q4, answered against us.** The resolution pattern Dean named is the existing portal
precedent — **trusted-edge mechanism for browser/UI traffic, independent Bearer validation for
API/service traffic** — and **ISAAC has neither today.** Do not write or imply anywhere that edge
headers are sufficient proof of authentication.

The rest, each also testimony:

- **The edge injects/overwrites exactly five headers** — `X-authentik-username`, `X-authentik-groups`,
  `X-authentik-email`, `X-authentik-name`, `X-authentik-uid`; **only those are overwritten.** This
  **resolves** the "does not follow that the client's copy was removed" ambiguity above **for the edge
  path only** — the paragraph is kept struck-through-in-place rather than deleted because it was right
  about what the *probe* could prove, and remains right about a direct in-cluster caller, who never
  meets the edge at all. **`X-authentik-entitlements` and `X-Isaac-Edge` remain UNTRUSTED** (Q18
  answered; ISAAC's existing permanent disqualification is confirmed as also Dean's intent).
- **Actor stamping is AUTHORIZED, and blocked in practice.** Server-stamp the canonical Authentik
  **username** for `attribution.uploaded_by`, **Run overrides, submissions and revision-history rows**
  — **provided the request's identity was established through the trusted authentication boundary.**
  **Client-supplied username is never authoritative.** Q10 and Q25 both close on that one answer. Since
  no such boundary exists in ISAAC, **nothing may be stamped yet**; the actor seam stays unset/unknown
  exactly as built.
- **Usernames are not reassigned; the username is canonical** (**Q5** answered). **Q17 — UID
  permanence — should NOT be reopened absent contradictory evidence, and NO UID↔username
  infrastructure should be introduced.** So the "probable design keeps both keys" line above is
  withdrawn: **one key, the username.** UID lifecycle is still an unestablished fact; it has simply
  stopped being a question ISAAC needs answered.
- **Groups: `admin` and `researcher`** are the relevant ISAAC groups at the authenticated edge
  (**Q7**). **`bl152-users` and `bl152-staff` are NOT ISAAC roles.** `X-authentik-groups` is
  authoritative **ONLY for a request known to have traversed the authenticated edge** (**Q6**) — a
  condition ISAAC cannot currently establish for any request.
- **Session expiry (Q8):** an expired/unauthenticated `/krish/*` request gets a **302 to Authentik**; a
  browser `fetch` **follows it** and lands on an **HTML login response**. `FetchStates.tsx` already
  handles exactly that.
- **Logout (Q9): `/outpost.goauthentik.io/sign_out`** is a valid logout path. Whether ISAAC should
  surface it is a product decision Dean was not asked and did not make — **still open, and Krish's**.
- **Q20 (`format` enforcement) is ANSWERED and is a SEPARATE question from all of the above** —
  see the next block.

**NOT addressed by this response, and therefore exactly as open as before:** **Q11**, **Q13**,
**Q14/G6**, **Q16**, gate **G2** (per-record display — still closed by default) and gate **G3** (the
five withdrawn aggregates). Silence is not assent.

### Q20 — ANSWERED 2026-08-12. Two halves; never quote one without the other.

- **ALLOWED:** JSON Schema `format` enforcement **in shadow mode** — read-only, **aggregates only**,
  **non-gating**, **outside the truth plane**. Those four are **conditions**, not description.
- **NOT AUTHORIZED:** **arming `format` enforcement in the official validator.**

`authorization.Q20_FORMAT_ENFORCEMENT_APPROVED` stays `False` and is now **confirmed correct** rather
than pending. The shipped behaviour already matched the ruling in both directions, so **no code
changed**. Q20(f) (does the portal enforce `format`?) was not addressed; Q20(e) is answered only by
implication. See [`docs/dean-authorization-packet.md`](docs/dean-authorization-packet.md) and
[`docs/evidence/2026-08-05-q19-q20-authorization.md`](docs/evidence/2026-08-05-q19-q20-authorization.md).

### AI / MCP / voice — DEAN DEFERRED; THE OWNER ELECTED TO CONTINUE. Both facts, kept separate.

**1. Dean's recommendation, unsoftened.** He **deferred D1–D9** — MCP reachability and auth, model
provider, credential, billing, egress, retention, data policy, transcription provider. His words:
***"leave AI integration as future work rather than increasing scope at this point."*** He is away for
roughly a week. **He approved none of it. Do not record any D-row as approved, narrowed, or closed.**

**2. The project owner's decision, attributed to Krish.** Krish has **explicitly elected to CONTINUE
implementing the original scope** — MCP, Connect Your Agent, the native LLM assistant,
transcription/voice, and the provider architecture. **The roadmap is NOT cancelled and must not be
recorded as cancelled.**

Both are true, because they are about different things:

| | Covers | Status |
|---|---|---|
| **Implementation complete** | code, APIs, UI, auth abstraction, provider abstraction, tests, **deterministic fake providers**, error handling, security boundaries | **owner-authorized; PROCEEDING** |
| **Production provider configured** | institutional endpoint, credential, network path, billing, provider approval | **genuinely external; DEFERRED by Dean** |

> **The absence of the second is not a reason to skip the first.**

**What still binds the continued work:** `ai-integration-decision-packet.md` §6 in full — **no fake
`Connected` state**, external agents cannot submit, **no model output may enter the truth path**, and
the no-guessing rule applies to the assistant's own answers — plus §9's ***"build nothing that implies
any of it exists."*** Building a capability and advertising it are different acts; the first is
authorized, the second is not. **No real endpoint, credential, outbound model call, or charge is
authorized by this**, and the out-of-scope entry for an external model provider below stands.

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

**[`docs/session-handoff-2026-08-26.md`](docs/session-handoff-2026-08-26.md) IS CLOSED OUT.** It
was written when a session stopped on a usage limit with one unreviewed PR and four unverified
`wip/*` branches; **all of that resolved on 2026-08-27** — every PR merged with an independent
review and green CI, and each `wip/` slice was re-run from its brief and re-measured rather than
merged. Its box at the top carries the current state; the body is kept for its evidence and
reasoning, not as a description of where things stand. **Read it for the still-open list**
(~~`system.domain` has no write path~~ — **CLOSED 2026-08-27, see the reversal in §11**; discard
needs the owner; A11Y-06's residue; the reasoned darwin a11y column) **and for three operational traps that cost real time** — a `.venv` symlink that
reached `main`, the snapshot conflicting every open PR on each merge, and OpenAPI aggregates that
must be re-measured rather than added. It is a description, not an authorization; verify every fact
with the commands in its §1.

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

The manifest **is far broader than documentation.** Composition **re-measured 2026-08-17** over
`snapshot["memory_inputs"]["served_content_manifest"]`, and it sums to all 200 entries — the previous
version of this paragraph said *"measured composition"* while listing buckets that summed to **187**,
so it implied completeness it did not have, and the buckets it omitted are exactly the ones that catch
a slice by surprise:

| Count | Bucket |
|---:|---|
| 64 | `apps/web/src/**` — the largest single bucket, including component, `lib` and `__tests__` files |
| 37 | `docs/**` (excluding `docs/superpowers/`) — `.md` plus two sample JSON artifacts |
| 35 | `tests/**` |
| 15 | `apps/api/**` |
| 15 | `src/**` — the truth core |
| 7 | `docs/superpowers/**` |
| 7 | `apps/web/*` — `package.json`, `index.html`, `vite.config.ts`, the three `tsconfig*.json`, `README.md` |
| 6 | root files — `CLAUDE.md`, `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `pyproject.toml` |
| 5 | `.claude/skills/*/SKILL.md` |
| 4 | `scripts/**` |
| 3 | `schema/**` |
| 1 | `vocabulary/descriptor_class.json` |
| 1 | **`.github/workflows/ci.yml`** |
| **200** | **total** |

**Two entries in that table were previously wrong or missing, and both were found the hard way.**
`tests/**` was listed as 36 and measures **35**. And **`.github/workflows/ci.yml` was not listed at
all** — discovered when a one-line `expected_scenarios` bump in the CI workflow drifted the snapshot,
which is precisely the surprise the next paragraph warns about, arriving through a bucket this list had
omitted. Re-measure rather than trusting this table:

```bash
.venv/bin/python -c "import json,collections; d=json.load(open('apps/api/isaac_api/data/memory-snapshot.json')); m=d['memory_inputs']['served_content_manifest']; print(len(m))"
```

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