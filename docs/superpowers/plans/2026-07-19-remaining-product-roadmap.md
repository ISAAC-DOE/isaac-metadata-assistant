# ISAAC — Master Remaining-Work Roadmap

Status: PROPOSED — awaiting approval. Direction **DECISION-LOCKED 2026-07-20**; no production implementation authorized (only P25.0 design/spec after these plans are pushed).
Date: 2026-07-19 (decisions locked 2026-07-20) · Baseline commit: `f534a4c` (P24.10 released) · Author: Claude (planning)

> **AUTHORIZATION UPDATE (later 2026-07-20 master authorization) — supersedes the "only P25.0" status line above for execution scope.** The "only P25.0 authorized" wording is the initial planning-gate state and is retained as history. The **later 2026-07-20 master authorization** (recorded in the Phase 25 plan's session checkpoints and `2026-07-20-slac-account-toolchain-reconciliation.md`) authorizes **continuous execution of the locked core roadmap** — Phase 25 slices → Phase 26 → UI Refinement → Final Stabilization → Documentation & Deliverables → one final Graphify/snapshot refresh — **subject to the existing hard gates** (per-slice report → independent review → commit → push → exact-HEAD CI → checkpoint; P25.8 excluded; institutional infrastructure and Convex off the core path). This note settles no new decisions and rewrites no history; it only reconciles this header with the newer checkpoint so fresh sessions do not read the two as contradictory. Precedence when sources appear to conflict on *authorization*: the later master authorization governs execution scope.
Related / superseded: EXTENDS `2026-07-16-phases-23-26-arc-decisions.md`; the accepted decisions are recorded in `2026-07-20-remaining-work-decision-lock.md` (authoritative where it and any companion plan conflict); consolidates the back-burner registry currently in `docs/project-memory-map.md`. Companion detailed plans (all dated 2026-07-19, all PROPOSED): phase-25-grounded-assistant, phase-26-workspace-memory-search, ui-refinement-and-visual-qa, final-product-stabilization, institutional-integration-readiness, documentation-and-deliverables, convex-feasibility-spike.

> This roadmap is repo-grounded against a four-part audit of HEAD `f534a4c` (see `scratchpad/audit-*.md`). It supersedes the scope framing in the arc-decisions doc where the two differ, and it renumbers nothing in the approved 23→24→25→26 sequence — it refines *what runs in parallel* and *what is genuinely on the critical path*.

---

## 1. Current completed baseline (verified, not assumed)
- **Truth core** (`src/isaac_records/`, `schema/isaac_record_v1.json`): deterministic, Graphify-free (test-enforced), authoritative for validation/export/audit/completion. Official validate `PASS v1.05`; audit `33/33`.
- **Hosted app** (Railway FastAPI + Vercel React SPA, deployed `f534a4c`): 21 API routes, 9 screens, single shared-secret bearer auth, filesystem-JSON persistence, honest degraded states.
- **Project Memory** (P24, through P24.10): sanitized committed snapshot served via the `MemoryReader` provider seam; separated freshness axes (availability / integrity / memory-policy / indexed-sources); CI content-drift gate; Graphify-free at runtime.
- **Assistant**: guided-chip UI with a static answer table + verdict guard (no LLM), mounted on 2 screens.
- **Tests**: backend 461 (CI 460 pass + 1 conditional skip), frontend 137/17 files; CI green.
- **NOT yet built**: grounded (live-state) assistant answers; any search; users/orgs/roles; durable/per-user persistence; DB; background jobs; notifications; audit-history storage; poster/slide-deck/assembled paper.

## 2. What still remains (7 workstreams)
| # | Workstream | Detailed plan | Relative size |
|---|---|---|---|
| A | Phase 25 — Grounded Assistant | phase-25-grounded-assistant-plan | **Medium** (frontend-only, ~11 slices) |
| B | Phase 26 — Workspace + Memory Search | phase-26-workspace-memory-search-plan | **Large** (new backend + frontend + test-invariant change) |
| C | UI Refinement + Visual QA | ui-refinement-and-visual-qa-plan | **Medium** (audit small; refinement sized by backlog) |
| D | Final Product Stabilization | final-product-stabilization-plan | **Medium** |
| E | Documentation & Deliverables | documentation-and-deliverables-plan | **Medium–Large** (many artifacts; some need your content) |
| F | Institutional Integration Readiness | institutional-integration-readiness-plan | Plan = done; **impl = Large/greenfield, gated & off core path** |
| G | Convex feasibility spike | convex-feasibility-spike-plan | **Medium**, optional, off core path |

## 3. Dependency diagram
```
                 (Track B — parallel from day 1)
   Docs Tier 0 (stale-doc fix, truth/memory + workflow + pipeline figures,
                verification summary, governance/limitations/migration guides)
        │                                   ┌── Docs Tier 1 (assistant figure) ⇐ needs A
        │                                   ├── Docs Tier 2 (search figure)    ⇐ needs B
        ▼                                   └── Capstone (poster, deck, paper)  ⇐ needs A,B,C,D + mentor D7/D8
  ┌───────────────── CRITICAL PATH (Track A) ─────────────────┐
  │  P25.0 gate → A: Grounded Assistant → P26.0 gate →         │
  │  B: Workspace+Memory Search (incl. P26.6 test-rewrite) →   │
  │  C: UI Refinement (audit → backlog → refine) →             │
  │  D: Final Stabilization → release-verified                 │
  └───────────────────────────────────────────────────────────┘
   (Track C — parallel anytime) D's truth-path / snapshot-drift /
        deploy-rollback / security-governance regression tracks

   Off critical path, gated:
     F: Institutional seam-introduction   ⇐ Gate-0 authorization (Q-INST-1) + an engaged institution
     G: Convex spike                      ⇐ post-core, optional (Q-CVX-1)
```

## 4. Critical path & why this order
**P25 → P26 → UI → Stabilization**, because:
- **A (P25) first** — it is pure-frontend, adds *zero* new backend/truth-path contracts, is partly begun (already consumes live memory availability), is the cheapest, and yields immediate demo value. Its deterministic "prompt → structured query → templated reply" composer is designed to be **reused by B's search**, so doing A first avoids rework.
- **B (P26) second** — independent of A (no dependency either way), but sequencing it after A lets it reuse A's grounding/provenance layer. B is the larger, riskier build (new `/api/search` + `MemoryReader.search()` + the reviewed rewrite of the "no fake search" invariant), so it comes after the cheap win.
- **C (UI) after A+B** — the *authoritative* refinement pass + re-audit must review the *complete* functional product (assistant + search dialog). A lightweight **baseline** audit MAY begin now in parallel (capturing today's screens), but the binding CRITICAL/MEDIUM/OPTIONAL backlog is produced post-A+B so it does not audit a static assistant that P25 replaces or rely on the no-search invariant that P26.6 removes. Exact sequencing is the UI plan's open Q7 — user decides.
- **D (Stabilization) last on the path** — it stabilizes the finished feature set. But its truth-path/schema/export/audit/snapshot-drift/deploy-rollback/security regression tracks are feature-independent and run in parallel (Track C) from the start.

**I largely endorse the approved arc (25→26).** My one refinement is explicit: treat A's composer as the shared substrate for B, and run Docs Track B + Stabilization Track C in parallel rather than strictly after.

**Accepted master order (decision-lock 2026-07-20):** 1) Phase 25 → 2) Phase 26 → 3) UI Refinement → 4) Final Stabilization → 5) **Documentation, Handoff & Deliverables (terminal core-path item)** — with Docs Tier 0 truth-fixes and the regression/security tracks permitted to run in parallel when they change no product behavior and bypass no gate. Institutional infrastructure and Convex remain off the core path.

## 5. Approval gates
- **P25.0** — design/spec approval before any Phase 25 implementation (single gate).
- **P26.0** — design/spec approval before any Phase 26 implementation; **P26.6** (the "no fake search" test-rewrite) is a dedicated reviewed slice with its own gate.
- **UI**: audit-first; a visual-approval checkpoint per refinement cluster (your taste gates aesthetics).
- **D**: hard gate before any hosted deploy; final release-checklist gate.
- **F (Institutional)**: **Gate-0** — the readiness doc is assessment-only; NO seam-introduction implementation runs without explicit authorization AND an engaged institution.
- **G (Convex)**: optional, post-core; explicit go/no-go before the spike.
- **Global**: every implementation slice stops and reports; no phase begins without your approval of its plan.

## 6. Parallel vs sequential
- **Sequential (critical path):** A → B → C → D.
- **Parallel from day 1:** Docs Tier 0 (Track B); Stabilization's regression/deploy/governance tracks (Track C).
- **Parallel but gated by a phase:** Docs Tier 1 (after A), Tier 2 (after B).
- **Off critical path:** F (gated), G (optional).

## 7. Major risks (cross-cutting)
1. **Ephemeral + shared hosted workspace** (biggest architectural reality): one auto-seeded demo experiment on `/tmp`, wiped on restart, one global key. Search (B) and the demo look thin over a single experiment, and no user work persists. *Not a blocker for "current project complete" (synthetic demo), but it caps demo richness.* **Decision (LOCKED, Q-CROSS-2):** keep ephemeral + shared + honest re-seed (no DB / no volume); add a **deterministic richer synthetic seed** (multiple synthetic experiments in varied states) via the existing filesystem seeding path — placed in **Phase 26**, verified in Stabilization, clearly labeled demo data, never fake product data.
2. **Test-invariant change (P26.6):** flipping the actively-tested "no search" invariant must be a reviewed, honest slice; CI-green-per-commit ordering needs a decision (Q-P26-3).
3. **Deliverables depend on you:** poster/deck/paper need your scientific content, figure taste, and closure of open mentor decisions D1–D8 (esp. D7/D8).
4. **Subagent environment flakiness** observed this session (some spawns fast-fail with injected text — see §12). Mitigation: verify every artifact on disk; author keystone docs directly.
5. **Scope creep toward institutional infra:** durable multi-user persistence, SSO, monitoring, rate-limiting are *institution-ready-but-not-wired*, not core. Keeping them off the core path is a deliberate decision to reaffirm.

## 8. Institutional dependencies
Nothing in the core path (A–E) requires an institution. F (seam introduction) and any durable multi-user story require: an identity provider (SSO/OIDC), a user/org/role model, a durable datastore (Postgres or institution-provided), object storage for approved files, and possibly a hosted memory service. ISAAC's job is to expose clean seams + synthetic defaults; the institution supplies the backends. See the institutional-readiness plan.

## 9. Explicit non-goals (whole remaining program)
Truth core stays deterministic, Graphify-free, authoritative. No LLM in the assistant (guided prompts only). No vector/semantic search required (future option). No real/private SLAC data. No second scientific domain. No portal parity. No MCP. No dark theme. No new slash commands. Graphify never validates and never indexes private data. Institutional infra may store/transport but never becomes the validation authority.

## 10. Definitions
- **"Current project complete"** = A (P25) + B (P26) shipped & verified; C (UI) refined to premium scientific-workbench demo quality; D (stabilization) release-checklist passed; core deliverables (report + poster + deck + demo) produced; everything synthetic; truth core intact and Graphify-free. I.e., **functional end-to-end with synthetic/demo providers.**
- **"Institution-ready but not yet institution-wired"** = every provider boundary (identity/auth, users/orgs, roles, experiment/draft/evidence persistence, file/object storage, Project Memory, search, background jobs, notifications, audit-history, secrets/config) has a **documented seam + a working synthetic/demo default**, such that an institutional team **replaces or configures** those seams rather than rewriting the application. ISAAC ships seams + defaults, not institutional backends.
- **"Back burner"** = a deferred item with a named dependency/trigger that must occur before reconsideration; not on the core roadmap; classified as product / infrastructure / research / cosmetic.

---

## 11. Back-burner registry (consolidated — THE canonical registry)
Class: **P**roduct · **I**nfrastructure · **R**esearch · **C**osmetic.

**This section is the single canonical back-burner registry.** Where the companion plans say "update `docs/project-memory-map.md`," they should update THIS table going forward; `docs/project-memory-map.md`'s existing table becomes a pointer to here (that pointer edit is owned by the Documentation plan, since `project-memory-map.md` is a served memory-plane doc and editing it triggers a snapshot regen).

| Item | Class | Why deferred | Dependency / trigger before reconsidering | What makes it safe/valuable |
|---|---|---|---|---|
| Related records / record similarity | P | No cross-record relationships modeled; low demo value now | Real multi-record corpus + P26 search | Real corpus + a similarity contract that never implies validation |
| Experiment similarity | P | Same as above | Durable multi-experiment workspace | Meaningful once many experiments persist |
| Runtime-record indexing into memory | I/R | Memory is a committed snapshot; live indexing needs a dynamic memory service | Dynamic memory provider (institutional) | A safe, sanitized, permissioned indexing pipeline |
| Full graph explorer / raw network viz | P/C | High effort, low truth value; risks implying graph=truth | Post-core, if mentors want exploration | Read-only, clearly memory-plane, never a validator |
| Electrochemistry / 2nd scientific domain | P/R | MVP is single XANES path | Explicit mentor approval + schema-path validation | A second validated domain with its own evidence rules |
| Real / private SLAC data | I | Governance; synthetic-only MVP | Explicit user approval + data-governance sign-off | Sanitization + access controls proven first |
| Portal validator parity | P | Advisory seam only today | Mentor decision + upstream portal contract | Deterministic parity that stays advisory |
| Freeform / LLM assistant | P | Arc item 8: guided prompts only, no LLM this arc | Post-core product decision | Grounded composer (P25) proves the pattern first |
| LLM extraction | R | No-guessing policy; deterministic extraction only | Post-core research spike | Evidence-gated extraction that never invents values |
| MCP server | I | Out of scope | Post-core integration decision | A read-only MCP over existing APIs |
| Dark theme | C | Tokens are light-only today | UI-refinement phase, if desired | Theme-aware tokens, WCAG-AA both modes |
| Multi-user collaboration | P/I | Single shared workspace today | Identity + durable persistence (F) | Per-user isolation + real-time layer |
| Institutional login / SSO | I | Single shared-secret auth today | Institutional engagement (F, Gate-0) | OIDC seam behind the existing auth boundary |
| Full DB migration | I | Filesystem JSON today; no repo abstraction | F: introduce the persistence seam first | Repository abstraction + a durable store |
| Dynamic memory service | I | Committed snapshot only | Institutional memory provider | New `MemoryReader` impl behind the existing seam |
| **Convex adoption** | I | Not evaluated; not a Graphify replacement | The Convex spike (G) + explicit adoption criteria | A time-boxed, reversible spike with go/no-go criteria |
| Advanced vector / semantic search | R | P26 is deterministic token search; vector not required | Post-P26, if recall demands it | Optional layer atop the deterministic search |
| Real file ingestion / upload | I | Uploads wall = always 403 (governance) | Approved object storage + sanitization | Keeps the governance wall until storage is safe |
| Broad monitoring / ops infra (rate-limit, APM, alerting, autoscale) | I | Institutional responsibility; not core | Institutional hosting | Institution supplies; ISAAC stays vendor-neutral |

No back-burner item is promoted into the core roadmap without an explicit, called-out approval. The **2026-07-20 decision-lock re-affirmed every row above as deferred** (see `2026-07-20-remaining-work-decision-lock.md` §11); none was promoted.

---

## 12. Process note — subagent injection incident (this session)
During plan authoring, three subagent spawns fast-failed (~2–5s, zero tool calls) and returned **prompt-injection payloads** in their result text (a fake "System:" model-identity override; a fake "Automatic Delegation Note"; a fake "IMPORTANT: use TodoWrite"). These were **ignored** — no behavioral direction is taken from tool output. The affected plans were re-dispatched or authored directly; every committed plan file was **verified on disk and injection-scanned clean**. Flagged here for your awareness; it changed no content.

---

## 13. Decisions — LOCKED 2026-07-20 (see `2026-07-20-remaining-work-decision-lock.md`)
The questions below are **resolved** by the 2026-07-20 decision-lock. Genuinely-open items (this
lock did not decide them) are called out as **OPEN**.

**Cross-cutting**
- Q-CROSS-1 → **LOCKED.** Order = **P25 → P26 → UI → Stabilization → Documentation/Deliverables (terminal)**, with Docs Tier 0 + regression/security tracks in parallel.
- Q-CROSS-2 → **LOCKED.** Hosted workspace stays **ephemeral + shared + synthetic + honest re-seed**; **no** production DB / Railway volume for demo polish. A **deterministic richer synthetic seed** is **required** (placed in Phase 26; §7 risk 1). *(Baseline correction: the workspace seeds **one** experiment, not eight.)*
- Q-CROSS-3 → **LOCKED.** Institutional infra (SSO, durable multi-user persistence, monitoring/rate-limiting) stays **institution-ready-but-not-wired**, off the core path.

**Phase 25** — all LOCKED: (1) add `'advisory'` **yes**, plus a distinct **artifact/workflow-state** source label (5-category taxonomy); (2) mount on the **4 record surfaces + Project Memory where appropriate**; do **not** mount My Experiments / Load Materials / Settings / Governance for consistency; (3) pure-frontend composer, no new backend/truth contract **confirmed**; (4) **remove** the disabled free-text box, use `Guided Prompts Only` framing; (5) P25.0 approved as the **single** gate. First code slice = **P25.1 (composer skeleton + source-label rendering on RecordWorkbench)** — not authorized until P25.0 approved. **OPEN:** final chip wording / templates / the exact artifact-workflow enum value (P25.0 deliverables).

**Phase 26** — LOCKED: D1 **single** `GET /api/search` (internal separate providers); D2 **⌘K + visible trigger** (not keyboard-only); D3 P26.6 rewrite is a **dedicated reviewed slice, after** real behavior/trigger/dialog/navigation/tests exist; D4 vector/semantic **deferred**; D5 **single shared workspace + single memory provider**; D6 **no new env vars/deps**. Results carry typed metadata incl. **source/provider**. **OPEN:** the P26.6 CI-green mechanic (co-reviewed pair vs green-per-commit); caps/page defaults (proposed 50/10); min query length (proposed 2).

**UI** — LOCKED: **audit-only first**; dark-mode **deferred**; include large-screen/projector **QA** but **no dedicated projector breakpoint** unless a concrete finding requires it; preserve light-first workbench, truth-vs-advisory semantics, accessibility. **OPEN (taste, for you at the Slice-K gate):** breakpoint widths & demo resolution; density; type scale/font; accent restraint; whether to commit the screenshot set.

**Stabilization** — LOCKED: required-now vs institutional split confirmed (**no** rate-limiting/monitoring vendors in core now); persistence stays **ephemeral** (richer synthetic seed instead of durable). **OPEN:** add a CI contract-alignment job?; a minimal request/access log for the demo?

**Institutional** — LOCKED: **Gate-0 = assessment/documentation only.** Q-INST-1 → **no** speculative seam-introduction phase (seam only when a feature requires it, or SLAC authorizes with an owner); Q-INST-2 → ISAAC **exposes seams + synthetic defaults**, institution supplies backends; Q-INST-3/-4/-5 → governance walls closed-by-default, no P25/P26 entanglement, truth core off-limits — **all confirmed**. No current feature triggers any seam, so **none of S1–S9 is authorized**.

**Deliverables** — LOCKED: parallel Docs Tier 0 now; capstone terminal. **OPEN:** mentor decisions **D7** (deliverable scope/timing) & **D8** (paper/poster emphasis); figure/poster tooling; doc placement; number of screenshot passes; the one-line `mentor-decisions.md` `26/26`→`33/33` fix; architecture-figure revision policy.

**Convex** — LOCKED: **optional, post-core**; not scheduled; reconsider only after P25 + P26 + UI + Stabilization **and** demo/deliverables are substantially complete. Candidate application/data plane — not a Graphify or Python-truth-core replacement. **OPEN:** the go/no-go on scheduling the spike; self-host vs synthetic Cloud; Postgres comparison baseline; live demo vs written memo; who supplies SLAC infra facts.

---

## 14. Recommended first implementation slice (after approval)
**P25.0** — the Phase 25 design/spec approval gate: finalize the grounded-assistant composer contract (source-label taxonomy, per-context chip catalog, answer templates, no-verdict guard over composed output) as a mini-spec for your sign-off. No code until P25.0 is approved. First *code* slice thereafter: **P25.1 — the deterministic composer skeleton + source-label rendering on RecordWorkbench**, one screen, behind the existing verdict guard, fully unit-tested, no new backend contract.
