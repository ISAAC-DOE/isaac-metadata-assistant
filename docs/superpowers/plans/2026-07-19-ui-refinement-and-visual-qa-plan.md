# UI Refinement & Visual-QA Audit / Backlog Plan

Status: PROPOSED — awaiting approval. No implementation authorized.
Date: 2026-07-19  ·  Baseline commit: f534a4c  ·  Author: Claude (planning)
Related: 2026-07-16-phases-23-26-arc-decisions.md; P24 specs; this doc EXTENDS the approved arc (it is a cross-cutting quality pass, not a new product plane).
Approval decisions required:
1. Approve the audit rubric + breakpoint matrix + state matrix (Slice 0 gate) before any screenshot capture.
2. Confirm this is **audit-only first**: no CSS/source change until the consolidated CRITICAL/MEDIUM/OPTIONAL backlog is reviewed and you select items.
3. Confirm screenshots run against the **synthetic demo seed only** (no real/private SLAC data, no fabricated rows for polish).
4. Decide sequencing vs P25/P26: the Assistant-presentation and future-search-dialog audits partly depend on those phases landing. See §5, §24, §25.
5. All aesthetic/taste calls (density, accent restraint, dark-mode scope, type scale) are deferred to you at the consolidation gate — this plan sets up the review, it does not pre-decide look.

---

## 1. Purpose

Run a disciplined, screenshot-driven, page-by-page visual-QA audit of the **completed** ISAAC web product and produce a prioritized refinement backlog (CRITICAL / MEDIUM / OPTIONAL). The goal is to raise the UI to a premium scientific-workbench bar through **minimal, subtle** adjustments — spacing, hierarchy, density, contrast, state polish — **without** a broad redesign and **without** changing any functional semantics or test-enforced invariants.

This plan deliberately separates *seeing/judging* from *changing*. Audit slices produce evidence and candidates; they do not touch `apps/`, `src/`, or `schema/`. Any actual refinement is a later, separately approved, per-issue-cluster slice gated on your taste decisions.

## 2. User / scientist value

A scientist under time pressure reads the workbench faster: clearer typography hierarchy tells them "what needs me next," denser-but-legible tables reduce scrolling, honest degraded states never look broken, and advisory-vs-validation styling keeps them from mistaking an advisory note for a verdict. No behavior changes — only legibility and calm.

## 3. Mentor / demo value

The demo currently reads as an honest prototype; a subtle polish pass makes it read as a credible institutional tool during a live walkthrough. A categorized backlog also gives mentors a concrete, low-risk punch-list they can approve incrementally, and demonstrates QA rigor (screenshot evidence, accessibility contrast checks) rather than vibes.

## 4. Architectural value

Formalizes a repeatable visual-QA harness (breakpoint matrix, state matrix, contrast checks) and reinforces existing design-system-level guard tests (`no-vertical-rail.test.ts`, no-search, signals-distinctness) as the boundary refinements must not cross. Consolidates styling authority around the design tokens in `apps/web/src/styles/tokens.css` instead of scattered per-component drift.

## 5. Dependencies

- App must run locally: backend `uvicorn isaac_api.app:app` (see `RUN_COMMAND`, `apps/web/src/lib/api.ts:56-57`) + Vite dev server, seeded with the synthetic demo experiment (`POST /api/demo/run`).
- Screenshot tooling: `playwright-skill` or `claude-in-chrome` (both available). Deterministic viewport sizes required.
- **P25 (Grounded Assistant)** and **P26 (Real Search)** are NOT started (baseline §36–37). The Assistant audit (Slice H) evaluates today's static panel; the search-dialog audit (Slice L) is spec-forward only and **deferred** until P26 ships a real dialog — no UI exists to screenshot yet.
- No new npm dependencies. No data-fetching library added. Contrast checks can use a tokens-only computed check (no external service required for synthetic UI).

## 6. Scope

Audit surface = the full completed product:
- **9 screens**: ExperimentsHome, LoadMaterials, RecordWorkbench, GuidedCompletion, EvidenceExplorer, ExportReadiness, ProjectMemory, GovernancePage, SettingsPage.
- **Project Memory sub-surfaces**: Source Index + Concept Lookup + concept-detail card (`ProjectMemory.tsx`).
- **Global chrome**: AppShell, TopBar, LeftNav, WorkflowSpine, HelpPanel, StatusBar.
- **Assistant** presentation (`AssistantPanel.tsx`) — today's static panel only.
- **Future search dialog** — spec-forward checklist only, deferred to P26.

Audit dimensions applied per surface (the fixed rubric): spacing/rhythm, typography hierarchy, information density, Project Memory layout, Source Index readability, concept-detail presentation, assistant presentation, search-dialog presentation (deferred), responsive behavior, loading/empty/malformed/unavailable/backend-down states, hover/focus/pressed, keyboard-focus visibility, color contrast (WCAG AA), advisory-vs-validation styling separation, long-path handling, overflow/truncation, table/list readability, screen-to-screen consistency, demo readability (projector legibility).

Deliverable: one findings/backlog document (CRITICAL / MEDIUM / OPTIONAL) + screenshot evidence set. **No implementation in this plan.**

## 7. Non-goals

- No broad redesign, no new visual language, no re-layout of information architecture.
- No new features, routes, components, or slash commands.
- No change to functional semantics: verdict/coverage/advisory separation, the `hasVerdictLanguage` guard, no-search invariant, governance 403 wall, honest empty/degraded states, evidence coverage counts.
- No fake/decorative/placeholder data added for visual polish (violates baseline §54 and existing tests).
- No changes to `apps/`, `src/`, `schema/` during audit slices. (Refinement slices, if approved later, touch **only** `apps/web/src/**/*.css` and never truth-plane files.)
- No dark-mode implementation unless separately approved (tokens are light-only today; see §25).

## 8. Current baseline (cite files)

- Tokens / authority: `apps/web/src/styles/tokens.css` (spacing/color/type/radius/shadow vars; already carries a WCAG-AA history — `--advisory-text` / `--needsyou-text` darkened to `#8a6420` in P23C for AA on their backgrounds), `apps/web/src/styles/base.css`.
- Screen styling: `apps/web/src/screens/screens.css`; component styling split across `apps/web/src/components/{chrome,queue,runner,fields,workflow,evidence,signals,artifact,assistant,fetchstates,help}.css`.
- Screens: `apps/web/src/screens/{ExperimentsHome,LoadMaterials,RecordWorkbench,GuidedCompletion,EvidenceExplorer,ExportReadiness,ProjectMemory,GovernancePage,SettingsPage}.tsx`.
- Chrome/components: `apps/web/src/components/{AppShell,TopBar,LeftNav,WorkflowSpine,HelpPanel,StatusBar,StatusChip}.tsx`.
- Signals (advisory-vs-validation separation): `apps/web/src/components/{VerdictCard,CoverageBadge,AdvisoryChip,GraphStatusChip}.tsx` + `signals.css`.
- Dense read-only surfaces: `apps/web/src/components/{SourcePreview,EvidenceTrailPanel,EvidenceRow,FieldGroup,FieldRow,GuidedPrompt}.tsx`.
- Degraded states: `apps/web/src/components/FetchStates.tsx` (`LoadingPanel` `role=status`; `BackendDown` `role=alert`, 404 vs network) + `fetchstates.css`.
- Assistant: `apps/web/src/components/AssistantPanel.tsx` + `assistant.css` + `apps/web/src/lib/assistant.ts` (static samples, verdict guard).
- Guard tests that bound refinement: `apps/web/src/__tests__/{no-vertical-rail.test.ts, help-and-honesty.test.tsx, signals.test.tsx, memory-concepts.test.tsx, modal-a11y.test.tsx}` (frontend 137 tests / 17 files, all green at baseline).
- Detailed inventory: sibling `audit-frontend.md` (this scratchpad) is the read-only source-of-truth for what exists.

## 9. Files likely touched

**Audit slices (this plan):** only new/appended artifacts under `docs/superpowers/` (findings doc) and a screenshot evidence set written to the session scratchpad (NOT committed unless approved). No app source.

**Refinement slices (deferred, separately approved):** at most `apps/web/src/styles/tokens.css`, `apps/web/src/styles/base.css`, `apps/web/src/screens/screens.css`, and specific `apps/web/src/components/*.css` files named by the approved backlog item. Possibly minimal className/markup tweaks in the corresponding `.tsx` **only** where CSS cannot achieve the fix without structural change — and only if it does not alter DOM contracts asserted by tests.

## 10. Files that must NOT be touched

- Truth plane: everything under `src/isaac_records/`, `schema/isaac_record_v1.json`, `apps/api/**` (backend). No exceptions.
- Frontend logic/contracts: `apps/web/src/lib/*.ts` (api, useFetch, assistant, routes, labels), `apps/web/src/App.tsx`, any `.tsx` behavior/state/handlers.
- Test files during refinement must not be relaxed to hide a regression; guard tests (`no-vertical-rail`, no-search, signals-distinctness, verdict-guard, modal-a11y, memory honesty) must stay green unchanged.
- During **all audit slices**: nothing in `apps/`, `src/`, `schema/` at all.

## 11. Data flow

Audit only observes the existing flow (React typed fetch client → live backend endpoints → server-derived truth; `apps/web/src/lib/api.ts`). No data flow is introduced or altered. Screenshots are captured from the running app against the synthetic demo seed; each state (loading/empty/error/backend-down/unavailable) is induced by controlling the backend (stop server for backend-down; unseeded id for 404; memory-absent env for unavailable) — never by injecting fake client data.

## 12. API / contracts

None changed. No endpoints added, removed, or reshaped. The audit confirms the UI faithfully renders existing envelopes; if a malformed/partial-envelope rendering weakness is found, it is logged as a finding (its fix may be functional and would route to a separate backend/api review, NOT a CSS refinement).

## 13. UI behavior

No behavioral change in this plan. The audit records where current behavior is visually unclear (e.g., focus ring low-contrast, truncation without title tooltip, advisory chip too close in weight to verdict card). Approved refinements adjust presentation only; interaction semantics (click targets, keyboard activation via native buttons, focus trap/return, `aria-current`, `aria-disabled` on locked steps) are preserved exactly.

## 14. Security / governance constraints

- Synthetic-only screenshots; no real/private SLAC/SSRL artifacts, no `examples/` content captured or committed (baseline §Data Governance).
- The governance 403 upload wall and its verbatim reason copy must remain visually intact and unmistakable.
- No screenshot evidence containing anything from `examples/`, `drafts/`, `records/`, or `graphify-out/` is committed. Report `git status --short` + `git check-ignore` on any evidence path before staging.
- Contrast checks are advisory QA, not a validation authority — they never gate export or mutate records.

## 15. Risks

- **Scope creep into redesign** — mitigated: every refinement is a named backlog item, minimal-diff, CSS-first, separately approved.
- **Breaking a guard invariant** (verdict rail, no-search, signals distinctness) via a "harmless" CSS tweak — mitigated: guard tests run before/after every refinement slice; forbidden-file list enforced.
- **Contrast fix regressing another surface** — tokens are shared; mitigated by re-screenshotting all surfaces that consume a changed token.
- **Taste disagreement** — mitigated: no aesthetic decision is made unilaterally; consolidation gate hands all taste calls to the user.
- **Non-determinism in screenshots** (fonts, timestamps) — mitigated: fixed viewports, seeded demo, mask volatile regions (build commit, timestamps) in comparisons.
- **Malformed-state "fix" bleeding into functional/backend change** — mitigated: flagged as out-of-scope for CSS refinement, routed separately.

## 16. Tests

- Audit slices: no code, no new tests; verification is the screenshot set + findings doc.
- Refinement slices (deferred): the full existing frontend suite (`npx vitest run`, 137/17 baseline) must stay green. New tests are added **only** if a refinement changes structure that should be locked (prefer extending the existing "design-system guard" pattern, e.g. a token-contrast assertion or a "focus-visible present" check) — never to paper over a break. If a refinement touches a signal/rail/search-adjacent area, the relevant guard test is the acceptance gate.

## 17. Verification

- Audit: (a) every in-scope surface has screenshots at the defined breakpoints × states; (b) each surface has a completed rubric scorecard; (c) findings doc compiles CRITICAL/MEDIUM/OPTIONAL with a screenshot reference + cited CSS/component file per item.
- Refinement (deferred, per slice): `npx vitest run` green; before/after screenshots at all affected breakpoints; contrast recomputed for any changed color token; visual approval recorded. Report the exact command + result (no invented results; per project rule §6).

## 18. Deployment impact

Audit: none. Refinement (deferred): CSS-only changes deploy via the existing Vercel-on-push flow; no backend redeploy, no env change, no migration. Purely presentational; `/api/health` build-commit surface unaffected.

## 19. Documentation impact

- This plan + the findings/backlog doc live under `docs/superpowers/plans/`.
- If refinements land, note them in the relevant handoff docs (`docs/ui-handoff/*`) and the project-memory-map back-burner table (baseline §45) — reconcile, do not duplicate.
- No stale-doc fixes here (baseline §47–48 belong to the Documentation plan).

## 20. Bite-sized slices

Each slice is one subagent, independently reviewable/committable, with a visual-approval STOP gate. Audit slices touch **no app source**. Sizes are relative.

### Slice 0 — Audit harness & rubric (small)
- Objective: stand up the running app (backend + Vite + demo seed), define the **breakpoint matrix** (e.g. narrow / tablet / desktop / projector-wide — exact values proposed for approval), the **state matrix** (default / loading / empty / error-404 / backend-down / memory-unavailable / malformed-or-partial), and the **rubric scorecard** (the §6 dimensions as a checklist). Capture a first baseline screenshot per screen at desktop width to prove the harness works.
- Files touched: scratchpad only (capture protocol + screenshots); findings doc skeleton in `docs/superpowers/plans/`.
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Sonnet 5 (mechanical harness) with Opus review of the rubric.
- Acceptance: harness reproducible; matrices + rubric written; one clean baseline shot per screen.
- Tests: n/a (no code).
- Report: breakpoints, states, rubric, tool used, seed method, `git status --short`.
- Commit: findings skeleton only, if approved.
- **Stop point: user approves breakpoint matrix + state matrix + rubric before any full capture.**

### Slice A — Global chrome + design-token & contrast audit (medium)
- Objective: audit AppShell / TopBar / LeftNav / WorkflowSpine / HelpPanel / StatusBar and the shared token layer; compute WCAG AA contrast for every text/background token pair in `tokens.css`; check focus-ring visibility and keyboard focus order across the frame; screen-to-screen consistency of chrome.
- Files touched: findings doc (append) + screenshots. Cites `styles/tokens.css`, `styles/base.css`, `components/chrome.css`, `workflow.css`, `help.css`, and the chrome `.tsx`.
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Opus 4.8 (accessibility/contrast + design-system judgment).
- Acceptance: contrast table for all token pairs; chrome scorecard; focus-visibility findings.
- Tests: n/a.
- Report: contrast pass/fail table, chrome findings categorized.
- **Stop point: review chrome/token findings before proceeding.**

### Slice B — Entry surfaces: ExperimentsHome + LoadMaterials (medium)
- Objective: audit queue readability/density (`queue.css`, `ExperimentQueue/ExperimentRow`), "what needs me next" hierarchy, the demo on-ramp + honest "Safe · Fake" label, governance-403 banner (`runner.css`, `GovernanceBanner`), long-name/overflow handling in rows.
- Files touched: findings doc + screenshots (default + empty queue + backend-down).
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Opus 4.8.
- Acceptance: scorecard for both screens across states.
- Report: findings categorized.
- **Stop point.**

### Slice C — Authoring surfaces: RecordWorkbench + GuidedCompletion (medium)
- Objective: audit field-group density/hierarchy (`fields.css`, `FieldGroup/FieldRow`), guided-prompt confirm/leave-missing presentation (`GuidedPrompt`), long-path/long-value truncation, right-panel (Evidence-above-Assistant) balance, loading/empty ("never 0/0") states.
- Files touched: findings doc + screenshots.
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Opus 4.8.
- Acceptance: scorecard across states incl. zero-blockers empty state.
- **Stop point.**

### Slice D — Dense read-only: EvidenceExplorer + SourcePreview (medium)
- Objective: audit Evidence Trail list readability (`evidence.css`, `EvidenceTrailPanel/EvidenceRow`), 3-tab SourcePreview (source/record/sidecar), cited-line highlight legibility, never-truncated `HashField` sha256 + copy affordance, long-path handling, table/list density.
- Files touched: findings doc + screenshots.
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Opus 4.8.
- Acceptance: scorecard; overflow/truncation findings.
- **Stop point.**

### Slice E — ExportReadiness + signal separation (medium)
- Objective: audit the three signals for **visual and structural non-conflatability** (VerdictCard vs CoverageBadge vs AdvisoryChip, `signals.css`) — this is the advisory-vs-validation styling dimension and is guarded by `signals.test.tsx` + `no-vertical-rail.test.ts`; audit export button gate states, artifact cards (`artifact.css`), and the export modal a11y presentation.
- Files touched: findings doc + screenshots (pending>0 gated, ready, exported, 409 re-export).
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Opus 4.8.
- Acceptance: explicit confirmation that any proposed refinement preserves signal distinctness + no verdict rail.
- **Stop point.**

### Slice F — Project Memory: Source Index + Concept Lookup + concept-detail (medium)
- Objective: audit `ProjectMemory.tsx` layout, GraphStatusChip states, Source Index metadata/provenance readability, Concept Lookup keyboard model + concept-detail card presentation, and the honest **memory-unavailable** styling (advisory-degraded, deliberately NOT error-red) — guarded by `memory-*.test.tsx`.
- Files touched: findings doc + screenshots (available + unavailable + empty-leads).
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Opus 4.8.
- Acceptance: scorecard; confirmation that unavailable-state stays non-error styled.
- **Stop point.**

### Slice G — Minimal screens: GovernancePage + SettingsPage (small)
- Objective: audit the two intentionally-minimal screens for typography/spacing quality and consistency with the rest of the frame; confirm no dead controls introduced; keep their honest "minimal placeholder" self-description legible.
- Files touched: findings doc + screenshots.
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Sonnet 5 (light surfaces) with Opus spot-review.
- Acceptance: scorecard.
- **Stop point.**

### Slice H — Assistant presentation (small)
- Objective: audit `AssistantPanel.tsx` + `assistant.css` — guided-chip legibility, the permanently-disabled free-text box being *clearly* labeled not-wired (not just inert), `answered from:` source-label readability, subordinate-to-truth visual weight vs the Evidence panel above it.
- Files touched: findings doc + screenshots.
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Opus 4.8.
- Acceptance: scorecard; note any item that must be re-checked after P25 changes the panel.
- **Stop point.**

### Slice I — Cross-screen state sweep (medium)
- Objective: systematically capture loading / empty / error-404 / backend-down / memory-unavailable / malformed-or-partial across every live screen; verify FetchStates copy + run-command legibility; flag any surface that renders a broken or ambiguous state.
- Files touched: findings doc + screenshots.
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Opus 4.8.
- Acceptance: full state matrix filled; malformed-envelope findings routed correctly (CSS vs functional).
- **Stop point.**

### Slice J — Responsive sweep (medium)
- Objective: capture every screen at each approved breakpoint incl. projector-wide (demo readability); flag horizontal-scroll, overflow, cramped/loose density, and wrap failures on long paths/tables.
- Files touched: findings doc + screenshots.
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Opus 4.8.
- Acceptance: responsive findings per screen per breakpoint.
- **Stop point.**

### Slice K — Consolidation → CRITICAL / MEDIUM / OPTIONAL backlog (medium)
- Objective: merge all slice findings into one prioritized backlog; each item = title, surface, cited CSS/component file, screenshot ref, proposed minimal change *as a candidate (not a decision)*, risk to guard tests, and an explicit "**needs your taste call?**" flag. Surface all aesthetic/taste questions here.
- Files touched: findings/backlog doc.
- Files forbidden: `apps/`, `src/`, `schema/`.
- Model: Opus 4.8 (synthesis) + Fable review.
- Acceptance: complete categorized backlog; every taste-dependent item flagged.
- **Stop point: user reviews backlog, makes taste calls, and selects which items (if any) proceed to refinement. This is the primary approval gate of the whole plan.**

### Slice L — (Deferred) Future search-dialog presentation checklist
- Objective: spec-forward only — pre-register the visual/a11y bar a real P26 search dialog must meet (focus trap, `role`, keyboard, plane-labeling, honest provider-down state) so P26 ships to standard. **No UI exists to audit yet.**
- Status: DEFERRED until P26 lands a real dialog. Not executed in this phase.

### Refinement slices (deferred, one per approved backlog cluster)
- Objective (each): implement one approved cluster, CSS-first, minimal diff.
- Files touched: named `.css` (+ minimal className only if unavoidable).
- Files forbidden: truth plane, `lib/*.ts`, `App.tsx`, backend; guard tests unchanged.
- Model: Opus 4.8 for signal/contrast/a11y-sensitive clusters; Sonnet 5 for mechanical spacing/token clusters.
- Acceptance: `npx vitest run` green; before/after screenshots; contrast recomputed for changed tokens; semantics preserved.
- Commit: one commit per cluster.
- **Stop point after each: visual approval before the next cluster.**

## 21. Model / subagent assignment

Fable = orchestrator/planner/reviewer/verifier. Opus 4.8 = accessibility/contrast, signal-separation, dense-surface, and synthesis slices (A–F, H, I, J, K + sensitive refinements). Sonnet 5 = harness setup and light/minimal surfaces (Slice 0, G, mechanical refinement clusters). Every slice independently assignable/reviewable/verifiable/committable with an explicit stop gate (baseline §MODEL RULE).

## 22. Acceptance criteria

- Every in-scope surface (9 screens + Memory sub-surfaces + chrome + Assistant) has screenshots at all approved breakpoints × states and a completed rubric scorecard.
- Contrast table for all `tokens.css` text/background pairs, WCAG AA pass/fail marked.
- One consolidated backlog grouped CRITICAL / MEDIUM / OPTIONAL, each item citing a real component/CSS file + screenshot + guard-test risk + taste-call flag.
- No `apps/`/`src/`/`schema/` file changed during the audit; no fabricated data used; no guard invariant proposed for removal.
- All taste-dependent decisions surfaced to the user, not pre-decided.

## 23. Stop / approval gates

1. After Slice 0 — approve matrices + rubric.
2. After each audit slice (A–J) — review findings before next.
3. After Slice K — **primary gate**: user makes taste calls and selects refinement scope. No CSS changes before this.
4. After each refinement cluster — visual approval before the next.
No slice proceeds past its gate without explicit user approval (baseline §Phase Workflow; do not run ahead).

## 24. Deferred items

- Search-dialog visual audit (Slice L) — until P26 exists.
- Assistant re-audit — after P25 replaces the static panel; today's audit (Slice H) is a snapshot of the prototype panel.
- Dark-mode / theming — out of scope unless separately approved; tokens are light-only today.
- Any malformed/partial-envelope weakness whose fix is functional — routed to a separate backend/api review, not a CSS refinement.
- Motion/animation polish and micro-interactions beyond hover/focus/pressed — OPTIONAL bucket only, not committed.

## 25. Explicit questions for the user

Taste / aesthetic (these will not be decided without you):
1. **Breakpoints** — approve target widths, and is a "projector-wide" (demo) breakpoint in scope? What is the demo display resolution?
2. **Density preference** — do you want tighter/denser tables and field lists (more on screen) or more breathing room? This drives most spacing findings and is a pure taste call.
3. **Dark mode** — in or out of scope for this pass? Tokens are light-only today; adding dark mode is a larger effort and would need its own approval.
4. **Type scale / font** — keep the current type ramp and font stack, or is refining the typographic hierarchy (heading sizes, weights) on the table?
5. **Accent restraint** — how minimal? Any brand/institutional palette to align the accent and advisory/needs-you ambers toward, or hold the current tokens?

Process / scope:
6. Confirm **audit-only first** (no CSS change until the Slice K backlog is reviewed).
7. Sequencing: run this pass **before**, **after**, or **parallel to** P25/P26? (Affects whether Assistant/search audits are re-run.)
8. Should the screenshot evidence set be **committed** to the repo, or kept in the scratchpad and referenced only? (It is synthetic-only either way.)
9. Are there specific screens you already feel are weakest and want prioritized into CRITICAL regardless of the rubric?
