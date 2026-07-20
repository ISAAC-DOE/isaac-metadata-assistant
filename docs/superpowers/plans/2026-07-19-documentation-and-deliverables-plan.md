Status: PROPOSED — awaiting approval. No implementation authorized.
Date: 2026-07-19  ·  Baseline commit: f534a4c  ·  Author: Claude (planning)
Related: `2026-07-16-phases-23-26-arc-decisions.md` (approved arc, phases 23→24→25→26); `2026-07-16-phase-24-project-memory-design.md`, `2026-07-17-phase-24-9-hosted-project-memory-enablement.md`, `2026-07-19-phase-24-10-memory-freshness-semantics.md` (P24 specs). This doc **EXTENDS** the approved arc with a parallel documentation/deliverables track — it does not renumber or replace phases 25/26.
Approval decisions required: poster/slide/paper timing vs. Phase 25/26 completion (ties to open D7); paper/poster emphasis (D8, still open); standalone new docs vs. embedded sections for institutional-integration/limitations/security-governance/reproducibility content; figure source tooling (Mermaid+SVG vs. design tool); poster/slide production tool; single- vs. double-pass demo screenshots; explicit go-ahead on the mentor-decisions.md single-line fix. Full list in §25.

# Documentation, Handoff & Deliverables Plan

## 1. Purpose
Bring every reader-facing document to a state that honestly matches the shipped product (currently through P24.10, commit `f534a4c`), then produce the remaining paper/poster/slide/figure/table deliverables needed for mentor review and program hand-off — without touching product code, schema, or the deliverable content itself (this document is a plan only).

## 2. User/scientist value
A scientist or reviewer picking up any doc in `docs/` gets an accurate picture of what exists today (web app deployed, Project Memory built, 33/33 audit) instead of a picture that predates Phase 19. Figures and tables give a faster, correct mental model than reading source.

## 3. Mentor/demo value
`docs/mentor-brief.md` is the designated "start here" doc and is currently the single most misleading artifact in the repo (`docs/mentor-brief.md:102` says the web app is "not built" — false). Fixing it and producing the outstanding figures/tables/poster/slides directly serves the mentor-review and end-of-summer hand-off goals that `docs/mentor-decisions.md` D7/D8 exist to resolve.

## 4. Architectural value
None of this phase touches the truth or memory plane. Its only "architectural" output is *documentation of* the existing two-plane architecture (figures, an institutional-integration guide) — it must describe, never redesign, `src/isaac_records/` or `apps/api/isaac_api/memory.py`.

## 5. Dependencies
- Tier 0 (fix/verify/produce-now) depends only on the current baseline (`f534a4c`, clean, in sync with `origin/main` — confirmed via `git log --oneline -3` and `git status -sb` at planning time). No implementation dependency.
- Tier 1 depends on Phase 25 ("Grounded Assistant") shipping — not started per `audit-docs.md` §2.
- Tier 2 depends on Phase 26 ("Real Search") shipping — not started.
- Capstone tier depends on Tier 0–2 being complete **and** mentor decisions D7 (final deliverable scope) and D8 (paper/poster emphasis) being answered (`docs/mentor-decisions.md` §5, both open).

## 6. Scope
In scope: doc corrections, new figures (as diagrammed source + rendered image), new tables, a new institutional-integration guide, a new limitations/security-governance write-up, a reproducibility appendix, demo screenshots, a poster content package, a slide-deck content package, and an assembled final report draft.
Out of scope: any change to `apps/`, `src/`, `schema/`, CI workflow files, or actual production/deployment behavior; any new slash command; any CI doc-lint automation (deferred, §24); actually operating a design tool (Figma/Canva/PowerPoint) — this plan defines content and file packaging, not visual production itself.

### Deliverable definitions

**Tier 0 — do now, no P25/26 dependency**

| Deliverable | Source of truth | Required product state | Files likely created/updated | Evidence/data needed | Review gate | Completion criteria |
|---|---|---|---|---|---|---|
| Stale-doc fix cluster | `audit-docs.md` §1, §3, §7 | none (current baseline sufficient) | `docs/mentor-brief.md`, `docs/final-deliverable-outline.md`, `docs/paper-notes.md`, `docs/mentor-decisions.md` | current test/audit counts (461 backend / 137 frontend → verify against README post-commit; evidence 33/33) | Fable diff review (no narrative rewrite beyond the flagged lines) | `rg` for the 4 flagged strings (below) returns zero hits in the 4 files |
| Living-docs verification pass | `audit-docs.md` §1 rows marked CURRENT | none | none expected (verify-only) | re-read each doc against `f534a4c` | Fable spot-check | confirms README.md, architecture.md, deployment.md, ui-local-dev.md, operator-playbook.md, demo.md, demo-script.md still CURRENT; any drift found becomes its own micro-slice |
| Test + verification summary table | README.md test counts, CI run id, `isaac audit` output, `isaac validate --official` | none | `docs/tables/test-verification-summary.md` (new) | live `pytest --collect-only -q`, `isaac audit`, CI run URL | Fable factual check | numbers match a fresh run, cited with command used |
| Evaluation/results tables T1/T2(/T3) | `docs/final-deliverable-outline.md` §"figures/tables" spec | none | `docs/tables/t1-validation-stages.md`, `docs/tables/t2-results-summary.md`, optionally `docs/tables/t3-open-decisions.md` | validation stack (`CLAUDE.md` §3), `mentor-decisions.md` D1–D8 | Fable factual check; user for T3 framing | T1/T2 populated with real, cited numbers; T3 optional, flagged if skipped |
| Truth-plane vs. memory-plane figure | `PLANNING-BASELINE.md` §"Two-plane architecture", `src/isaac_records/`, `apps/api/isaac_api/memory.py` | none | `docs/figures/truth-vs-memory-plane.mmd` + rendered `.svg` | module list + isolation-test citations | **user visual-taste review** | every box/edge traceable to a cited file; user approves the rendering |
| End-to-end workflow figure | `docs/architecture.md` pipeline diagram, `cli.py`, `export.py` | none | `docs/figures/end-to-end-workflow.mmd` + `.svg` | draft→validate→complete→export→audit flow | **user visual-taste review** | matches `docs/architecture.md` prose 1:1 |
| Project Memory pipeline figure | `apps/api/isaac_api/memory.py` (`MemoryReader`, `LocalGraphArtifactSource`, `SanitizedSnapshotSource`, 4-step precedence) | none | `docs/figures/project-memory-pipeline.mmd` + `.svg` | precedence order, env var names | **user visual-taste review** | precedence order matches code exactly (no invented steps) |
| Final/polished architecture figure | `docs/architecture.md` ASCII diagram | none | `docs/figures/architecture-overview.mmd` + `.svg` | same as `architecture.md` | **user visual-taste review** | supplements (does not replace) the ASCII diagram in `docs/architecture.md`; paper/poster use the SVG |
| Security/governance write-up | `docs/data-governance.md`, `apps/api/isaac_api/auth.py`, baseline "biggest institutional gap" note | none | new content — **file location is an open question**, default `docs/security-governance-summary.md` | shared-secret auth model, ephemeral/shared state facts | Fable factual check; user tone/framing | accurately states single-shared-secret auth, no user/org/role concept, ephemeral filesystem persistence |
| Limitations write-up | `docs/mentor-decisions.md` D1–D8 (all open), arc back-burner list | none | new content — default `docs/limitations.md`, open question re: standalone vs. section | D1–D8 status, back-burner registry | Fable factual check; user tone | every listed limitation is cited to a real doc/line, no new limitations invented |
| Institutional migration guide | `memory.py` docstring (future DB/login-gated reader hook), baseline "GREENFIELD: identity+users/orgs/roles+durable persistence", `project-memory-map.md` back-burner | none | new `docs/institutional-integration.md` | `MemoryReader` Protocol extension point, auth middleware, workspace persistence model | **Opus** (architecture-sensitive) + Fable review | describes the extension seam accurately; does not promise unbuilt features as done |
| Reproducibility appendix | `docs/demo.md`, `docs/cli.md`, `docs/operator-playbook.md` | none | new `docs/reproducibility-appendix.md` | exact commands from the three source docs | Fable factual check | every command cross-referenced, none invented |

**Tier 1 — gated on Phase 25 ("Grounded Assistant") shipping**

| Deliverable | Source of truth | Required product state | Files likely created/updated | Evidence/data needed | Review gate | Completion criteria |
|---|---|---|---|---|---|---|
| Assistant-grounding figure | Phase 25 implementation + its design mini-spec | Phase 25 implemented and merged | `docs/figures/assistant-grounding.mmd` + `.svg` | shipped composer's grounding inputs (validate blockers, pending fields, audit coverage, evidence trail, memory availability — per baseline §"Assistant") | **user visual-taste review** | matches shipped P25 behavior, not the pre-P25 static-sample baseline |

**Tier 2 — gated on Phase 26 ("Real Search") shipping**

| Deliverable | Source of truth | Required product state | Files likely created/updated | Evidence/data needed | Review gate | Completion criteria |
|---|---|---|---|---|---|---|
| Search architecture figure | Phase 26 implementation + its design mini-spec | Phase 26 implemented and merged | `docs/figures/search-architecture.mmd` + `.svg` | shipped dual (workspace-truth + memory) search design per arc item 9 | **user visual-taste review** | matches shipped P26 behavior; explicitly shows plane-labeling/permission-awareness |
| Demo script + demo screenshots refresh | shipped P25 + P26 UI | both Phase 25 and Phase 26 implemented | `docs/demo-script.md` (update), new `docs/screenshots/*.png` | live or local deployment showing final UI, synthetic data only | Fable governance check (no secrets/real data in screenshots) + user narrative review | one screenshot per of the 9 screens + updated script beats for assistant/search; zero real data, zero visible `ISAAC_UI_API_KEY` value |

**Capstone tier — gated on Tier 0–2 complete AND D7/D8 answered**

| Deliverable | Source of truth | Required product state | Files likely created/updated | Evidence/data needed | Review gate | Completion criteria |
|---|---|---|---|---|---|---|
| Poster | `docs/final-deliverable-outline.md` (fixed), all figures/tables above | Tier 0–2 complete, D7/D8 answered | `docs/poster/isaac-poster-outline.md` (content) + exported artifact per chosen tool (open question) | final numbers, chosen figures, mentor emphasis (D8) | **heavy user content/taste review** | user signs off on content and layout before any print/export |
| Final slide deck | same | same | `docs/slides/isaac-slides-outline.md` (content) + exported artifact | same | **heavy user content/taste review** | same |
| Final report/paper | `docs/final-deliverable-outline.md` + `docs/paper-notes.md` (both fixed), all sections/figures/tables above | Tier 0–2 complete, D7/D8 answered | new `docs/final-report.md` (assembled draft; outline/notes remain source inputs, not replaced) | everything above | **heavy user content/taste review**, likely multiple passes | draft assembled, cites every figure/table by file path, zero unverified numeric claims |

## 7. Non-goals
- No product/behavior change of any kind.
- No new CI gate/workflow file (deferred, §24).
- No actual design-tool session (Canva/Figma/PowerPoint) run by an agent — this plan hands off content, not finished visual production, unless the user later chooses an HTML/artifact-rendered path.
- No rewriting of self-declared HISTORICAL docs (`docs/proposal-v2.md`, the entire `docs/ui-handoff/` package, `docs/extraction.md`, `docs/intake.md`) — per `audit-docs.md` §1 these are intentionally frozen snapshots and out of scope.
- No re-opening or attempting to close mentor decisions D1–D8 — this phase documents them, does not decide them.

## 8. Current baseline (cite files)

| Deliverable type | Current file(s) | State | Citation |
|---|---|---|---|
| Final report/paper | `docs/paper-notes.md` (prose notes), `docs/final-deliverable-outline.md` (skeleton) | STALE — no assembled paper draft exists at all | `audit-docs.md` §1, §4 |
| Poster | — | Does not exist anywhere in the repo | `audit-docs.md` §4 |
| Slide deck | — | Does not exist; `docs/demo-script.md` is a spoken/terminal script, not slides | `audit-docs.md` §4 |
| Mentor brief | `docs/mentor-brief.md` | STALE — line 102 "Web app / MCP server / portal integration — not built" (false for web-app half) | `audit-docs.md` §1, §7.1; confirmed via `grep -n` |
| Demo script | `docs/demo-script.md` | CURRENT — matches 33/33 audit pipeline | `audit-docs.md` §1 |
| README | `README.md` | CURRENT | `audit-docs.md` §1 |
| Architecture docs | `docs/architecture.md` | CURRENT but ASCII-only; no polished figure exists | `audit-docs.md` §1, §4 |
| Deployment guide | `docs/deployment.md` | CURRENT | `audit-docs.md` §1 |
| Local-development guide | `docs/ui-local-dev.md` | CURRENT | `audit-docs.md` §1 |
| Operator playbook | `docs/operator-playbook.md` | CURRENT | `audit-docs.md` §1 |
| Institutional integration guide | none dedicated — content scattered across `memory.py` docstring, `PLANNING-BASELINE.md` GREENFIELD note, `docs/project-memory-map.md` back-burner table | Does not exist as a standalone deliverable | `PLANNING-BASELINE.md` lines 7, 19; `audit-docs.md` §6 |
| Limitations/governance documentation | `docs/data-governance.md` (data rules only), `docs/mentor-decisions.md` (D1–D8 all open), arc back-burner list | No standalone limitations write-up for a paper/poster audience; content scattered across 3+ docs | `audit-docs.md` §5, §6 |
| Current figures | one ASCII diagram in `docs/architecture.md` | F1–F3 (per outline) all unproduced | `audit-docs.md` §4 |
| Current tables | none rendered | T1–T3 (per outline) all unproduced, spec-only | `audit-docs.md` §4 |

Exact stale citations to fix (verified this session via `grep -n`):
- `docs/mentor-brief.md:102` — "Web app / MCP server / portal integration — not built." (false)
- `docs/final-deliverable-outline.md:71` — "Delivery shape: local Python CLI + tooling (not a web app, not MCP)." (false)
- `docs/final-deliverable-outline.md:95` — "174 passing Python tests" (stale; current baseline 461 per `PLANNING-BASELINE.md`)
- `docs/paper-notes.md:109` — "174 passing Python tests" (same)
- `docs/mentor-decisions.md:52` — "clean audit (`evidence 26/26`)" (stale; current 33/33)

## 9. Files likely touched
`docs/mentor-brief.md`, `docs/final-deliverable-outline.md`, `docs/paper-notes.md`, `docs/mentor-decisions.md`, `docs/tables/*.md` (new), `docs/figures/*.mmd` + `*.svg` (new), `docs/security-governance-summary.md` or equivalent (new, path TBD), `docs/limitations.md` or equivalent (new, path TBD), `docs/institutional-integration.md` (new), `docs/reproducibility-appendix.md` (new), `docs/screenshots/*.png` (new, Tier 2), `docs/poster/*` (new, capstone), `docs/slides/*` (new, capstone), `docs/final-report.md` (new, capstone).

## 10. Files that must NOT be touched
`apps/`, `src/`, `schema/`, `.github/workflows/*`, `graphify-out/` (never committed), `examples/` (gitignored, potentially sensitive), any file under `docs/ui-handoff/`, `docs/proposal-v2.md`, `docs/extraction.md`, `docs/intake.md` (self-declared historical — leave alone per `audit-docs.md` §1 verdict), and every doc classified CURRENT in §8 unless a Tier-0 verification slice finds actual drift (in which case that becomes its own reviewed micro-slice, not a silent edit).

## 11. Data flow
Source docs/code (`architecture.md`, `memory.py`, `PLANNING-BASELINE.md`, test/audit output) → new figures/tables/sections (Tier 0) → capstone assembly (`docs/final-report.md`, poster, slides) draws only from already-committed Tier 0–2 artifacts, never re-derives numbers independently. No runtime data flow — this is a static-content phase.

## 12. API/contracts
N/A — no code, no endpoint, no contract changes in this phase.

## 13. UI behavior
N/A — no UI changes. Tier 2 screenshots capture existing UI as-is; they do not modify it.

## 14. Security/governance constraints
- Demo screenshots and any figure containing example data must show synthetic data only (per `CLAUDE.md` §6 / `docs/data-governance.md`); never capture `examples/` content.
- Screenshots must not expose `ISAAC_UI_API_KEY`, `ISAAC_MEMORY_SNAPSHOT` paths, or any other env value in visible UI chrome, browser devtools panes, or terminal panes.
- No content in this phase may claim a capability as shipped that is not (this is the exact failure mode being fixed in §8 — the plan must not reintroduce it).
- Graphify output, if consulted for any figure, is context only per `CLAUDE.md` §7 — every figure claim must be spot-checked against source files before commit.

## 15. Risks
- **Overclaim recurrence**: same failure mode as the docs being fixed — mitigate by requiring every new sentence with a number or capability claim to cite a file/line.
- **Scope creep into visual production tooling**: agents drafting "a poster" could balloon into operating external design tools — mitigate by treating poster/slide slices as *content packaging* only until the user picks a tool (open question §25).
- **Premature capstone**: assembling `docs/final-report.md` before D7/D8 are answered risks a wasted draft — mitigate with the explicit capstone gate.
- **Figure drift**: figures committed at Tier 0 could go stale if Phase 25/26 change the two-plane architecture — mitigate with the "v1 now + light touch-up after P25/26" default (flagged as open question, not assumed).
- **Screenshot secret leakage**: mitigate with an explicit pre-commit visual check (§16).

## 16. Tests
Docs-only phase; "tests" are verification checks, not pytest:
- `rg -n "174 passing|not a web app, not MCP|evidence 26/26|— not built\." docs/mentor-brief.md docs/final-deliverable-outline.md docs/paper-notes.md docs/mentor-decisions.md` → zero hits after slice 1.
- `git status --short` before every commit in this phase → only paths under `docs/` (never `apps/`, `src/`, `schema/`).
- For each figure: manual line-by-line cross-check against the cited source file before commit.
- For screenshots (Tier 2): visual scan for any secret/env value or non-synthetic data before commit.

## 17. Verification
Per slice: `git diff --stat` reviewed by Fable; `rg` regression check above; for figures/poster/slides, explicit user visual sign-off before commit (these cannot be verified by command alone). No build/deploy verification applies — `docs/` changes are not part of the Railway/Vercel deploy surface (§18).

## 18. Deployment impact
None. `docs/` is outside the deploy path for both the FastAPI backend and the Vite frontend; no rebuild, no redeploy triggered.

## 19. Documentation impact
This entire phase *is* documentation impact. Net effect: `docs/mentor-brief.md`, `docs/final-deliverable-outline.md`, `docs/paper-notes.md`, `docs/mentor-decisions.md` become accurate; `docs/` gains a `figures/`, `tables/`, `screenshots/`, `poster/`, `slides/` set plus 3–4 new standalone guides; `audit-docs.md`'s stale-claims list (in the planning scratchpad, not the repo) becomes fully resolved for Tier 0 items.

## 20. Bite-sized slices

**Slice 1 — Fix the 4 known stale claims**
Objective: correct exactly the 5 cited lines in §8, nothing else in those files.
Files touched: `docs/mentor-brief.md`, `docs/final-deliverable-outline.md`, `docs/paper-notes.md`, `docs/mentor-decisions.md`.
Files forbidden: everything else, including other prose in the same 4 files.
Model assignment: Sonnet 5 (mechanical).
Acceptance criteria: each fix states the current true fact (web app built/deployed; test count matches a fresh `pytest --collect-only -q`; audit ratio 33/33) with no other wording changes.
Tests: `rg` regression check (§16) clean; diff limited to the 5 lines (+minor adjacent wording only where the sentence requires it, e.g. "not a web app, not MCP" needs a full-sentence rewrite, not a token swap).
Report requirements: before/after text for each of the 5 lines.
Commit strategy: one commit, message referencing this plan.
Stop point: Fable review before commit.

**Slice 2 — Living-docs verification pass**
Objective: re-confirm README.md, architecture.md, deployment.md, ui-local-dev.md, operator-playbook.md, demo.md, demo-script.md are still accurate against `f534a4c`.
Files touched: none expected; any drift found is escalated as a new micro-slice, not fixed inline.
Model assignment: Sonnet 5.
Acceptance criteria: a short per-file confirmation note in the slice report; no silent edits.
Tests: n/a (read-only).
Report requirements: one line per file — confirmed current, or drift found + description.
Commit strategy: none unless drift found.
Stop point: report to Fable; only proceed to a fix-commit if drift is confirmed and approved.

**Slice 3 — Test + verification summary table**
Objective: produce `docs/tables/test-verification-summary.md` (backend/frontend test counts, CI run id, audit ratio, official-validate result).
Files touched: new file only.
Model assignment: Sonnet 5.
Acceptance criteria: every number sourced from a live command run in the report, not copied from a doc.
Tests: numbers cross-checked against `PLANNING-BASELINE.md` verification baseline.
Report requirements: commands run + outputs.
Commit strategy: one commit.
Stop point: Fable factual check.

**Slice 4 — Evaluation/results tables T1/T2(/T3)**
Objective: produce `docs/tables/t1-validation-stages.md`, `docs/tables/t2-results-summary.md`; T3 optional (open-decisions table) — draft only if user opts in (§25).
Files touched: new files only.
Model assignment: Sonnet 5 for T1/T2; user input required for T3 framing.
Acceptance criteria: T1 lists all 5 validation stages from `CLAUDE.md` §3 with authority/gating/implemented columns; T2 lists real field/blocker/audit/test numbers.
Tests: cross-check against `CLAUDE.md`, `docs/mentor-decisions.md`.
Report requirements: table content + citations.
Commit strategy: one commit (or two if T3 deferred).
Stop point: Fable review; user opt-in for T3.

**Slice 5 — Truth-plane vs. memory-plane figure**
Objective: `docs/figures/truth-vs-memory-plane.mmd` + rendered `.svg`.
Files touched: new files only.
Model assignment: Opus (architecture-sensitive).
Acceptance criteria: every box/edge cites a real file (`src/isaac_records/*`, `apps/api/isaac_api/memory.py`, the isolation tests).
Tests: manual cross-check line 16 §16.
Report requirements: element-to-citation map.
Commit strategy: one commit.
Stop point: **user visual sign-off required before commit.**

**Slice 6 — End-to-end workflow figure**
Objective: `docs/figures/end-to-end-workflow.mmd` + `.svg`.
Files touched: new files only. Model: Opus. Acceptance: matches `docs/architecture.md` pipeline description exactly. Tests/report/commit as Slice 5. Stop point: user visual sign-off.

**Slice 7 — Project Memory pipeline figure**
Objective: `docs/figures/project-memory-pipeline.mmd` + `.svg`, showing the exact 4-step precedence (`ISAAC_MEMORY_SNAPSHOT` → packaged snapshot → `ISAAC_MEMORY_DIR` → `graphify-out/`).
Files touched: new files only. Model: Opus. Acceptance: precedence order verified against `memory.py` `get_default_reader()`. Stop point: user visual sign-off.

**Slice 8 — Final/polished architecture figure**
Objective: `docs/figures/architecture-overview.mmd` + `.svg`, a paper/poster-grade companion to (not replacement of) the ASCII diagram in `docs/architecture.md`.
Files touched: new files only. Model: Opus. Acceptance: 1:1 with `docs/architecture.md` prose. Stop point: user visual sign-off. Note: revisit lightly after Phase 25/26 land (see open question §25.8) rather than redo from scratch.

**Slice 9 — Security/governance write-up**
Objective: draft content covering the single-shared-secret auth model, no user/org/role concept, ephemeral filesystem persistence, and the "biggest institutional gap = identity/users/orgs/roles" finding.
Files touched: new file, path per §25.3 decision (default `docs/security-governance-summary.md`).
Model assignment: Sonnet 5 draft, Fable factual review.
Acceptance criteria: every claim cites `apps/api/isaac_api/auth.py`, `workspace.py`, or `PLANNING-BASELINE.md`.
Stop point: user tone/framing review.

**Slice 10 — Limitations write-up**
Objective: draft content enumerating D1–D8 (all open) and the arc back-burner registry as user-facing limitations.
Files touched: new file, path per §25.3 (default `docs/limitations.md`).
Model assignment: Sonnet 5 draft, Fable factual review.
Acceptance criteria: no limitation listed that isn't already documented in `docs/mentor-decisions.md` or the arc back-burner list.
Stop point: user tone review.

**Slice 11 — Institutional migration guide**
Objective: new `docs/institutional-integration.md` describing the `MemoryReader` Protocol as the extension seam for a future DB/login-gated institutional reader, and naming identity/multi-user/durable-persistence as the greenfield gap.
Files touched: new file only.
Model assignment: **Opus** (architecture-sensitive per MODEL RULE).
Acceptance criteria: describes the seam accurately without promising unbuilt features as done; explicitly labels multi-user auth / real-data pilot as back-burner, not roadmap-committed.
Stop point: Fable review; optionally a second pass if mentor/IT stakeholder input becomes available.

**Slice 12 — Reproducibility appendix**
Objective: new `docs/reproducibility-appendix.md`, a compact command-reference appendix cross-referencing `docs/demo.md`, `docs/cli.md`, `docs/operator-playbook.md` rather than duplicating them.
Files touched: new file only. Model: Sonnet 5. Acceptance: every command tested to still run (`.venv/bin/isaac ...`, `pytest`) or explicitly marked "as documented in <doc>, not re-verified here." Stop point: Fable review.

**Slice 13 — Assistant-grounding figure** *(BLOCKED until Phase 25 ships)*
Objective: `docs/figures/assistant-grounding.mmd` + `.svg` showing the shipped grounded composer's inputs.
Precondition: Phase 25 implemented + merged.
Model: Opus. Stop point: cannot start before precondition; user visual sign-off after.

**Slice 14 — Search architecture figure** *(BLOCKED until Phase 26 ships)*
Objective: `docs/figures/search-architecture.mmd` + `.svg` showing the dual workspace/memory search design.
Precondition: Phase 26 implemented + merged.
Model: Opus. Stop point: cannot start before precondition; user visual sign-off after.

**Slice 15 — Demo script + demo screenshots refresh** *(BLOCKED until BOTH Phase 25 and 26 ship — see open question §25.6 on single- vs. double-pass)*
Objective: update `docs/demo-script.md` with assistant/search beats; capture one screenshot per of the 9 screens under `docs/screenshots/`.
Precondition: Phase 25 and Phase 26 both merged.
Model: Sonnet 5 for script text; screenshot capture needs a running local/deployed instance.
Acceptance criteria: zero real data, zero visible secrets (§14, §16); script beats match actual shipped behavior.
Stop point: Fable governance check + user narrative review.

**Slice 16 — Poster content package** *(capstone; blocked on Tier 0–2 + D7/D8)*
Objective: `docs/poster/isaac-poster-outline.md` — full content (title, sections, which figures/tables, callouts) ready to hand to a design tool.
Precondition: all Tier 0–2 slices committed; D7/D8 answered.
Model: Sonnet 5 drafts from approved content; **heavy user content/taste review** — this is not a mechanical slice despite the drafting model.
Stop point: user approves content before any visual layout work begins (visual layout is out of scope per §7 unless the user names a tool, §25.5).

**Slice 17 — Final slide deck content package** *(capstone; same gating as Slice 16)*
Objective: `docs/slides/isaac-slides-outline.md`.
Same preconditions, model assignment, and stop point as Slice 16.

**Slice 18 — Final report/paper assembly** *(capstone; blocked on everything above)*
Objective: `docs/final-report.md`, assembling the (already-fixed) outline and notes plus every figure/table/section produced in Tiers 0–2 into a single draft.
Precondition: Slices 1–15 complete; D7/D8 answered.
Model: Opus for assembly/consistency pass, Sonnet 5 for mechanical section insertion; Fable verifies every numeric claim traces to a cited source.
Acceptance criteria: zero unverified numeric claims; every figure/table referenced by file path, not re-drawn inline.
Stop point: **heavy, likely multi-pass user content/taste review** before this is treated as final.

## 21. Model/subagent assignment
Fable: orchestrator, planner, reviewer, verifier for the whole phase — no exceptions.
Sonnet 5: Slices 1, 2, 3, 4 (T1/T2), 9 (draft), 10 (draft), 12, 15 (script text), 16 (draft), 17 (draft), 18 (mechanical insertion).
Opus: Slices 5, 6, 7, 8, 11, 13, 14, 18 (assembly/consistency pass) — all architecture-sensitive figure/guide work, per the repo's MODEL RULE.
Visual production tooling (actual poster/slide layout): unassigned pending §25.5 — likely the user directly, or a design-tool integration named later.

## 22. Acceptance criteria
- Tier 0 complete: `rg` regression check (§16) clean repo-wide; 7 CURRENT docs re-verified; 4 new figures + 2–3 new tables + 4 new guide docs committed, every claim in them citable.
- Tier 1/2 complete: assistant-grounding + search-architecture figures committed; demo script/screenshots refreshed exactly once (not per-phase).
- Capstone complete: poster + slide deck content packages and `docs/final-report.md` committed and explicitly approved by the user.

## 23. Stop/approval gates
- **Gate A** (after Slice 1): user/Fable confirms the 5 stale-claim fixes before any Tier 0 figure/table work begins.
- **Gate B** (after Tier 0, before Tier 1/2 planning proceeds further): natural gate since Tier 1/2 are blocked on Phase 25/26 anyway.
- **Gate C** (before capstone tier): explicit user answer to D7 (final deliverable scope/timing) and D8 (paper/poster emphasis) required; no capstone slice starts without it.

## 24. Deferred items
- CI-level doc-staleness/link-check automation (would touch `.github/workflows/*`, out of scope for this phase, and not requested).
- Actual design-tool session (Figma/Canva/PowerPoint/LaTeX) to produce the physical poster/slide files — deferred until §25.5 is answered.
- Translating any deliverable into a second format (e.g., a video demo) — not requested, not planned.
- Closing mentor decisions D1–D8 — documented, not decided, in this phase.

## 25. Explicit questions for the user
1. **Timing (ties to D7)**: should the poster/slide deck/final paper wait until Phase 25 **and** 26 both ship, or is an interim version needed now for an earlier mentor checkpoint?
2. **Emphasis (D8, still open)**: what should the paper/poster foreground — no-guessing + evidence sidecar, the two-plane truth/memory architecture, Project Memory, or some combination?
3. **Doc placement**: institutional-integration, limitations, and security-governance content — standalone new files (as defaulted in §6) or sections folded directly into `docs/final-deliverable-outline.md`/`docs/paper-notes.md`?
4. **Figure tooling**: Mermaid source + exported SVG (text-diffable, repo-native, as defaulted in §6/§20) or a design tool for more polished conference-style figures?
5. **Poster/slide production tool**: HTML/Artifact render, PowerPoint/Keynote, LaTeX Beamer, or Canva/Figma export committed as PDF? This determines what Slices 16–17 hand off to.
6. **Demo screenshots**: one pass now against current P24.10 state (for interim review) plus a second pass after Phase 25/26, or a single pass deferred entirely until both ship (as currently planned in Slice 15)?
7. **`docs/mentor-decisions.md:52` fix**: confirm the single-line "26/26"→"33/33" correction is wanted, leaving the rest of that doc's self-declared "frozen since Phase 8" framing untouched (as scoped in Slice 1) — versus leaving the whole doc untouched as an intentionally historical snapshot.
8. **Final architecture figure revision policy**: produce v1 now and lightly touch it up after Phase 25/26 land (recommended, cheaper), or hold Slice 8 entirely until both phases ship to avoid a second pass?
