# Convex Feasibility Spike — OPTIONAL, Post-Core, Off-Roadmap

Status: PROPOSED — awaiting approval. No implementation authorized.
Date: 2026-07-19  ·  Baseline commit: f534a4c  ·  Author: Claude (planning)
Related: 2026-07-16-phases-23-26-arc-decisions.md; P24 specs. This doc does NOT extend or reorder the approved 23→26 arc — it is a **standalone, optional, reversible spike** to be considered only AFTER the core arc lands, and only if the institutional-multi-user question is actually pursued.
Approval decisions required:
1. Approve running an isolated, synthetic-only Convex feasibility spike at all (yes/no). This plan is PROPOSED; nothing here authorizes installing Convex, adopting it, or touching production code.
2. Approve the quarantine location (a sandbox OUTSIDE the ISAAC repo working tree) and the rule that only the findings markdown returns to the repo.
3. Approve the adoption/rejection rubric in §22 BEFORE any Convex install (rubric-first gate).
4. Confirm the spike is scored against the current FastAPI/local architecture, a conventional PostgreSQL architecture, AND institution-provided infrastructure — not evaluated in a vacuum.
5. Confirm the non-negotiable: the Python truth core stays authoritative; Convex may STORE and TRANSPORT verdicts and data, never PRODUCE a validity verdict.

---

> **Framing (read first).** This is a **feasibility spike**, not an adoption. Its only output is a written recommendation grounded in a working synthetic prototype. It is **time-boxed, isolated, and reversible**. It must not touch `apps/`, `src/`, `schema/`, the truth core, the memory plane, or the CI/deploy path. It must not become a Graphify replacement — Graphify remains a possible memory-construction/indexing tool, and the deterministic Python core remains the sole validation authority. If the spike is rejected, deleting the sandbox directory returns the world to exactly its prior state; the repo never depended on Convex.

---

## 1. Purpose

Determine, with a **working synthetic prototype**, whether [Convex](https://convex.dev) is a credible future **application/data plane** for ISAAC's currently-greenfield institutional needs — identity, durable per-user persistence, real-time collaboration, permissions, and workspace search — WITHOUT compromising the two-plane truth/memory discipline that the audit (`audit-architecture.md` §1) identifies as the repo's strongest asset. The spike answers "could this work and at what cost/risk," not "should we adopt it." Adoption is a separate, later, explicitly-gated decision.

## 2. User / scientist value

None directly and immediately — this is infrastructure due-diligence. Indirect future value IF adopted: durable per-scientist workspaces (today hosted state is ephemeral and shared — `audit-architecture.md` §6.4), real-time co-editing of a draft, cross-experiment search, and per-project permission isolation. The spike's value is **de-risking**: it prevents a costly wrong turn by testing the hardest integration question (truth-core boundary + governance) on synthetic data before any commitment.

## 3. Mentor / demo value

A crisp, evidence-backed recommendation memo mentors can act on: "here is what an institutional ISAAC backend on Convex would cost in complexity, money, portability, lock-in, and governance, vs Postgres, vs SLAC-provided infrastructure, vs staying as-is." Demonstrates disciplined evaluation (rubric-first, synthetic-only, reversible) rather than technology chasing. A short live demo of two-session real-time draft editing is possible but strictly optional and clearly labeled "throwaway spike, not the product."

## 4. Architectural value

Forces an explicit answer to the open institutional question the audits flag repeatedly: identity + users/orgs/roles + durable persistence are **entirely greenfield** (`audit-architecture.md` §6.3, `audit-backend.md` §5, §"Flags"). The spike tests whether a reactive BaaS can fill that gap while **preserving** the two-plane boundary — i.e., whether Convex can be a pure store/transport/realtime/permission layer with the Python core still producing every verdict. It also stress-tests the `MemoryReader` Protocol's claim (`memory.py:50-60`) that a "hosted memory service or login-gated institutional backend" can sit behind the existing interface.

## 5. Dependencies

- **Sequencing:** OPTIONAL and POST-CORE. Do not start until the approved 23→26 arc is complete (P24 done; P25 Grounded Assistant and P26 Real Search not started per `PLANNING-BASELINE.md`). This spike must NOT preempt, reorder, or consume the arc's implementation attention.
- **Inputs available today:** the deterministic FastAPI validation endpoint (`POST /api/experiments/{id}/validate` → `{ok, errors, schema, dry_run}`, routes.py:347-381) as the truth-core call target; the sanitized `memory-snapshot.json` projection shape (`memory.py`) as the memory-import fixture; the official schema version string (`EXPECTED_VERSION="1.05"`, official.py:23) and record/sidecar shapes for hashing.
- **External:** Convex CLI/runtime installed **only inside the sandbox**; a Node toolchain. Nothing added to the ISAAC repo's dependency manifests.

## 6. Scope

A quarantined, synthetic-only prototype that exercises, as small gated slices:
one synthetic user + one synthetic org; one persistent experiment; one draft; append-only revision history; two-session real-time propagation; a Convex→FastAPI validation call with the verdict stored alongside `input_hash` + `core_version_hash` + `schema_hash`; workspace full-text search over synthetic experiments/drafts/evidence metadata; import of a sanitized memory snapshot into Convex-backed dynamic storage; per-project/per-org permission isolation; Convex-down and FastAPI-down degradation behavior. Plus a written analysis of developer complexity, cost, portability, institutional governance, migration path, and lock-in risk, and a four-way comparison ending in explicit adoption/rejection criteria.

## 7. Non-goals

- NOT adoption, NOT a migration, NOT production wiring.
- NOT a Graphify replacement. Graphify stays the memory-construction/indexing tool; Convex is only tested as an application/data plane.
- NOT moving validation authority off Python. Convex must never compute `{ok/valid/passed/verdict}`.
- NO real/private SLAC/SSRL data, ever — synthetic only (CLAUDE.md §6).
- NO changes to `apps/`, `src/`, `schema/`, CI, Dockerfile, Railway/Vercel config, or the truth/memory planes.
- NOT a second scientific domain, not new slash commands, not real uploads.
- NOT a commitment to real-time collaboration or multi-tenancy as product features — only a test of whether the platform *could* support them.

## 8. Current baseline (cite files)

- **No database anywhere**; persistence is filesystem JSON in two disjoint stores: experiments/drafts/records under `ISAAC_UI_WORKSPACE` (default `/tmp/isaac-ui-workspace`) via `apps/api/isaac_api/workspace.py`, and CLI-exported records via `src/isaac_records/cli.py` (`audit-backend.md` §4).
- **No repository/persistence abstraction:** `Experiment` (workspace.py:80-184) bakes file I/O into the dataclass; swapping stores means rewriting call sites — CONTRAST with the clean `MemoryReader` seam (`audit-backend.md` §4, `audit-architecture.md` §2).
- **Auth = single shared-secret bearer**, app-wide, on/off only; no user/session/org/role/scope (`auth.py`, `audit-backend.md` §5).
- **Hosted state is ephemeral + shared:** one workspace, auto-seeds one demo experiment, wiped on Railway restart (`audit-architecture.md` §6.4).
- **Search absent** and its absence is a tested invariant (`audit-backend.md` §6; help-and-honesty / memory-concepts tests).
- **Background jobs / notifications / audit-history persistence: all absent** (`audit-backend.md` §8).
- **Memory provider seam is production-grade** and explicitly invites a hosted/DB/login-gated reader behind the `MemoryReader` Protocol (`memory.py:50-60`, 157-166).
- **Truth-core call target exists:** `POST /api/experiments/{id}/validate` delegates to `export_draft`/`official.py` and returns a structured verdict (routes.py:347-381).

## 9. Files likely touched

- **Inside the ISAAC repo: ONLY documentation.** This plan, and (on completion) a findings/recommendation memo under `docs/` (e.g. `docs/superpowers/spikes/2026-07-19-convex-findings.md`). Possibly one line in `docs/project-memory-map.md` "back-burner" table referencing the spike outcome.
- **Everything executable lives OUTSIDE the repo working tree** in the quarantine sandbox (see §10, §14). No repo source/config/CI files are created or edited.

## 10. Files that must NOT be touched

`apps/**`, `src/**`, `schema/**`, `pyproject.toml`, `apps/web/package.json`, `Dockerfile`, `railway.json`, `apps/web/vercel.json`, `.github/workflows/ci.yml`, `graphify-out/**`, `examples/**`, `records/**`, `drafts/**`, and every truth-path file listed in CLAUDE.md §13. The spike must not add any dependency to any repo manifest, must not import `isaac_records`, and must not alter any test. Verification: `git status --short` inside the repo shows ONLY the two docs above changing.

## 11. Data flow

Two flows are prototyped and compared to today's `React → FastAPI → Python core`:

- **Application/data flow (new, Convex-owned):** React (Convex client, reactive hooks) ⇄ Convex (documents: users, orgs, experiments, drafts, revisions, evidence-metadata, imported memory) with reactive subscriptions pushing live updates to all subscribed sessions. Permissions enforced inside Convex query/mutation functions keyed on synthetic user/org identity.
- **Truth-verdict flow (must stay Python-authoritative):** a Convex **action** calls the FastAPI validation endpoint → FastAPI calls the deterministic Python core → returns `{ok, errors, schema}`. Convex stores the verdict as a document **annotated with `input_hash` (hash of the exact draft/record payload sent), `core_version_hash` (identifier of the core/CLI version that judged it), and `schema_hash` (hash of `schema/isaac_record_v1.json` / the `1.05` version marker)**. The stored verdict is provenance-stamped and treated as a cached transport artifact, never as an independently-recomputable truth. Convex runs no validation logic.

The governing invariant: **data and realtime may live in Convex; validity is produced only by Python and merely stored by Convex.**

## 12. API / contracts

The spike defines only sandbox-local Convex functions and reuses the EXISTING FastAPI validate contract unchanged. No new ISAAC API route is designed or built. Contracts characterized (not committed):
- Convex schema for users/orgs/experiments/drafts/revisions/evidence-metadata/memory-import (documented in findings).
- The action→FastAPI request/response shape (reuse routes.py:347-381 as-is).
- The verdict-storage document shape including the three hashes (§11).
- The permission predicate shape (org-scoped read/write).
Comparison note: a real adoption would still need a versioned ISAAC API story (`audit-backend.md` §"Flags": no `/api/v1`, no pagination) — the spike records this as a cost, does not solve it.

## 13. UI behavior

A throwaway sandbox React page only, clearly labeled "SPIKE — synthetic, not the product." It demonstrates: sign-in as a synthetic user in a synthetic org; open one experiment/draft; edit the draft in session A and observe the live update in session B; view revision history; trigger validation and see the stored, provenance-stamped verdict; run a workspace search; and observe honest degraded states when Convex or FastAPI is down. It must reproduce the honesty discipline of the real app (no fake verdicts, plane/source labels, degraded banners) so the comparison is fair — but it is never merged into `apps/web`.

## 14. Security / governance constraints

- **Synthetic-only, enforced.** All users, orgs, experiments, drafts, evidence, and memory data are unmistakably fake (CLAUDE.md §6). No `examples/`, no real SLAC/SSRL artifacts, no real experiment data leaves the machine.
- **Convex Cloud is a third-party US SaaS.** Even synthetic data sent to Convex Cloud must be governance-reviewed; **the spike defaults to self-hosted/local Convex** to keep data on the machine, and evaluates Convex Cloud only as an analysis dimension (data-residency/DOE implications), not as a data sink for anything real.
- **No secrets in repo.** Any Convex deploy keys live only in the sandbox, never committed.
- **Truth boundary is a security constraint here too:** the spike must actively prove Convex cannot become an alternate validation authority (verdict provenance hashes exist precisely to make silent recomputation detectable).
- Governance report per CLAUDE.md §6: what files were read, that all data was synthetic, whether any external service saw content, `git status --short`, and that nothing under `examples/` was staged.

## 15. Risks

- **Architecture-inversion risk:** adopting Convex reshapes the app from "React→FastAPI→Python" to "React⇄Convex + Convex→FastAPI(validation)." That is a large frontend + backend change; the spike must quantify it, not gloss it.
- **Truth-discipline erosion risk:** the strongest asset (two-plane, test-enforced) could rot if validation/business logic drifts into Convex TypeScript. HIGH-severity; mitigated by the hash-provenance test and an explicit "no verdict in Convex" acceptance check.
- **Lock-in risk:** Convex functions, schema, and reactivity are platform-specific; leaving Convex is a rewrite. Portability must be scored.
- **Governance/data-residency risk:** institutional (DOE/SLAC) data policy may forbid third-party cloud storage; self-hosting Convex adds operational burden.
- **Cost opacity risk:** usage-based pricing is hard to forecast for an institutional workload.
- **Scope-bleed risk:** the spike could quietly become "the new backend." Mitigated by isolation, reversibility, and the explicit non-goals.
- **Opportunity-cost risk:** effort here is effort not on the core arc — hence POST-CORE gating.

## 16. Tests

Spike tests live only in the sandbox and validate the spike's own claims (they are evidence, not product tests):
- User/org created; experiment + draft persist across a simulated restart (durability vs today's ephemeral `/tmp`).
- Revision history is append-only and ordered.
- Two-session reactivity: a mutation in session A is observed in session B without a manual refresh.
- Validation: verdict returned by FastAPI matches the Python core's verdict for the same input; the stored verdict carries correct `input_hash`/`core_version_hash`/`schema_hash`; **assert Convex computes no verdict itself** (verdict provenance always traces to the core call).
- Workspace search returns expected synthetic hits with provenance.
- Memory import round-trips the sanitized snapshot projection shape.
- Permission isolation: org B cannot read org A's experiment/draft/memory.
- Degradation: Convex-down (client behavior) and FastAPI-down (validation unavailable, stored data still readable) both degrade honestly, no fake verdicts.

## 17. Verification

- Sandbox tests above pass and are reproducible from a clean sandbox checkout.
- `git -C <repo> status --short` shows ONLY the plan + findings docs changed.
- `grep` proves no `convex`/Convex dependency entered any repo manifest and no repo source imports it.
- The ISAAC repo's own suite is UNCHANGED and still green (backend 461, frontend 137) — run once at the end to prove non-interference.
- The findings memo's comparison matrix and adoption/rejection verdict are populated with real spike observations, not speculation.

## 18. Deployment impact

**None.** Nothing deploys. Railway/Vercel/CI untouched. The spike sandbox is never deployed to any ISAAC-associated environment. If Convex Cloud is exercised at all it is a personal throwaway dev deployment holding only synthetic data, torn down at slice end.

## 19. Documentation impact

Adds a findings/recommendation memo under `docs/` and (optionally) one back-burner-table line in `docs/project-memory-map.md` recording the outcome. Does NOT modify the arc-decisions doc, mentor-brief, or any spec. If the recommendation is "reject," the memo states why so the question isn't reopened without new information; if "revisit later," it states the trigger conditions.

## 20. Bite-sized slices

Each slice: one subagent, independently reviewable, sandbox-only, with a hard STOP gate. A slice may not begin until the prior slice's gate is cleared by the user. Any slice may terminate the spike early if it hits a disqualifying finding.

### Slice A — Quarantine + rubric-first charter (NO Convex install)
- **Objective:** create the isolated sandbox OUTSIDE the repo; write the adoption/rejection rubric (§22) and get it approved BEFORE any install; assemble synthetic fixtures (one user, one org, one experiment, one draft, evidence metadata, a copy of the sanitized memory-snapshot projection).
- **Files touched:** sandbox only; inside repo, only this plan already exists.
- **Files forbidden:** all of §10; do NOT install Convex in this slice.
- **Model:** Opus (governance/architecture-sensitive) for the rubric; Sonnet may assemble fixtures.
- **Acceptance:** sandbox path confirmed outside repo; rubric approved; fixtures unmistakably synthetic.
- **Tests:** n/a (setup); confirm `git status` clean.
- **Report:** sandbox location, rubric, fixture inventory, governance note.
- **Commit strategy:** no repo commit yet (plan already committed separately if approved).
- **Stop point:** STOP for rubric approval. No install without it.

### Slice B — Convex bootstrap + data model (self-hosted/local first)
- **Objective:** install Convex in the sandbox (prefer self-hosted/local per §14); model schema for users/orgs/experiments/drafts/revisions/evidence-metadata; insert the synthetic user+org+experiment+draft; record developer-complexity observations.
- **Model:** Opus (data-model design).
- **Acceptance:** synthetic entities persist and reload; schema documented; complexity notes captured.
- **Tests:** persistence + simulated-restart durability.
- **Stop point:** STOP; review data model and complexity before realtime.

### Slice C — Real-time + revision history
- **Objective:** two-session reactive subscription (edit in A, observe in B); append-only ordered revision history on the draft.
- **Model:** Opus.
- **Acceptance:** live propagation verified across two sessions; revisions ordered and immutable.
- **Tests:** reactivity + revision-history tests (§16).
- **Stop point:** STOP.

### Slice D — Truth-core boundary (CRITICAL)
- **Objective:** Convex action → FastAPI `/validate` → Python core; store the verdict with `input_hash`+`core_version_hash`+`schema_hash`; prove Convex computes no verdict; test Convex-down and FastAPI-down degradation.
- **Model:** Opus (truth-boundary + security-sensitive).
- **Acceptance:** stored verdict matches core verdict for identical input; hashes correct; NO verdict logic in Convex; both degradations honest (no fabricated PASS/FAIL).
- **Tests:** validation-parity, hash-provenance, no-verdict-in-Convex, dual-degradation (§16).
- **Stop point:** STOP. A failure here (e.g., pressure to move logic into Convex) is a candidate rejection trigger — report immediately.

### Slice E — Workspace search
- **Objective:** Convex full-text search over synthetic experiments/drafts/evidence metadata; compare to the P26 deterministic/plane-labeled/permission-aware/honest-degradation requirement (`PLANNING-BASELINE.md` P26 line).
- **Model:** Opus.
- **Acceptance:** typed, provenance-bearing hits; assessment of whether Convex search meets P26's honesty + permission constraints.
- **Tests:** search-hit + provenance test.
- **Stop point:** STOP.

### Slice F — Sanitized memory import + permission isolation
- **Objective:** import the sanitized memory-snapshot projection into Convex dynamic storage; enforce per-project/per-org permission isolation; verify org B cannot read org A.
- **Model:** Opus (governance/permissions).
- **Acceptance:** snapshot round-trips; cross-org isolation holds; relationship to the `MemoryReader` Protocol documented (Convex as a possible future reader impl vs a parallel store).
- **Tests:** memory-import + permission-isolation tests (§16).
- **Stop point:** STOP.

### Slice G — Analysis, comparison, recommendation + teardown
- **Objective:** score developer complexity, cost, portability, institutional governance/data-residency, migration path, lock-in; build the four-way comparison matrix (§ below); write the findings memo with EXPLICIT adoption + rejection criteria (§22); tear down the sandbox; run the repo suite to prove non-interference.
- **Model:** Opus (final judgment).
- **Acceptance:** matrix populated from real observations; explicit go/no-go criteria stated; sandbox deleted; repo suite green; `git status` shows only docs.
- **Tests:** repo backend+frontend suites unchanged/green.
- **Report:** full findings memo + governance report.
- **Commit strategy:** commit ONLY the findings memo (+ optional back-burner line) to `docs/`, only if the user approves.
- **Stop point:** STOP for the adoption/rejection decision. The spike ends here regardless.

### Four-way comparison matrix (built in Slice G)

| Dimension | (current) FastAPI + local JSON | Conventional PostgreSQL | Institution-provided infra | Convex |
|---|---|---|---|---|
| Persistence durability | Ephemeral `/tmp`, shared | Durable, standard | Durable, managed by SLAC | Durable, managed BaaS |
| Persistence abstraction | None (baked-in I/O) | Add repository interface | Add repository interface | Convex schema/functions |
| Real-time collaboration | None | Add SSE/websocket layer | Depends on offering | Native reactive queries |
| Workspace search | None (tested-absent) | Postgres FTS / external | Depends | Native FT/vector search |
| Background jobs | None | Add worker/queue | Depends | Native scheduled/cron |
| Identity / users / orgs | None (greenfield) | Build on Postgres | Institutional SSO (OIDC/SAML) | Convex Auth / integrations |
| Permissions / multi-tenancy | None | Build in app | Institutional | In Convex functions |
| Dev complexity to reach parity | — (baseline) | Medium-high | Medium (governance-heavy) | Low-medium (platform does a lot) |
| Cost | ~free | Infra + ops | Institutional/absorbed | Usage-based (cloud) or self-host ops |
| Portability / lock-in | High portability | High portability | Medium | **Low portability / high lock-in** |
| Data residency / DOE governance | On our host | Our/institution host | **Best fit** | Cloud = risk; self-host = OK-ish |
| Fit with Python-authoritative truth | Native | Native | Native | Requires strict action→FastAPI discipline |
| Migration effort from today | — | Medium | Medium-high | Medium-high + rewrite risk |

(Cells above are the hypotheses to CONFIRM/REVISE with spike evidence, not conclusions.)

## 21. Model / subagent assignment

Fable = orchestrator/planner/reviewer/verifier only (never implements). Opus 4.8 = every architecture/truth-boundary/security/governance/permissions slice (A rubric, B, C, D, E, F, G). Sonnet 5 = mechanical fixture assembly only. Every slice is independently assignable, reviewable in the sandbox, and gated. Fable reviews each slice's evidence before the next slice's install/build proceeds.

## 22. Acceptance criteria

Spike is "complete" when: all slices ran (or an early slice fired a documented disqualifier), the sandbox produced real observations for every dimension in §6, the comparison matrix is evidence-backed, the repo suite is still green, `git status` shows only docs, and the findings memo states an EXPLICIT verdict under the rubric below.

**Adoption criteria (all must hold to recommend a deeper/production evaluation — still NOT adoption):**
1. Truth boundary provably intact: Convex stored every verdict with correct provenance hashes and computed none itself; no pressure emerged to move validation into Convex.
2. Real-time, revision history, search, and per-org permission isolation all worked on synthetic data with honest degradation.
3. Convex-down and FastAPI-down both degraded honestly (stored data readable; no fabricated verdicts).
4. A **self-hosted** Convex path exists that keeps data on institution-controlled infrastructure (satisfies likely DOE/SLAC residency).
5. Developer complexity and forecastable cost are clearly lower than, or competitive with, the Postgres option for the same feature set.
6. A credible migration/exit path off Convex was identified (lock-in is bounded, not fatal).

**Rejection criteria (ANY one recommends NOT pursuing Convex):**
1. The two-plane truth discipline cannot be preserved without awkward or fragile guarantees (verdict logic tends to leak into Convex).
2. Only Convex Cloud is viable for the needed features and institutional data-residency policy forbids third-party cloud — with no acceptable self-host path.
3. Lock-in/portability cost is judged unacceptable for a research-institution codebase that must outlive vendors.
4. Cost is unforecastable or exceeds a conventional Postgres/institution-provided stack for the same needs.
5. It duplicates or would cannibalize the clean `MemoryReader` seam or the Graphify memory-construction role rather than complementing them.
6. The added architectural complexity (React⇄Convex + Convex→FastAPI) outweighs the benefit over simply adding a repository abstraction + Postgres + institutional SSO on the existing FastAPI.

## 23. Stop / approval gates

- **Gate 0 (now):** approve running the spike at all + the quarantine + the rubric (Approval decisions §1-5). No install before this.
- **Gate per slice (A→G):** each slice STOPS for user review; no next slice without clearance. Slice D is the critical truth-boundary gate.
- **Gate final (after G):** adoption/rejection decision. The spike ENDS here. Any production consideration is a brand-new, separately-planned, separately-approved effort — this document authorizes none of it.

## 24. Deferred items

Explicitly out of this spike, deferred to a hypothetical future effort only if the spike recommends proceeding: real IdP/SSO integration; real (non-synthetic) data; production persistence migration; a `PersistenceRepository` Protocol for `workspace.py` (a Postgres-path prerequisite, independent of Convex); versioned `/api/v1` + pagination; real uploads/object storage; audit-history persistence; notifications; and the P26 real-search build (which proceeds on its own arc plan regardless of this spike). Record all of these in the findings memo's "if we proceed" section without acting on them.

## 25. Explicit questions for the user

1. Should this spike be scheduled at all, and strictly AFTER the core 23→26 arc, or shelved until the institutional/multi-user requirement is real and funded?
2. Is a **self-hosted** Convex the only acceptable form given DOE/SLAC data-governance, or is a synthetic-only Convex Cloud dev deployment acceptable for the throwaway spike?
3. Is the quarantine-outside-the-repo model acceptable, with only the findings memo returning to `docs/`?
4. Should the spike ALSO produce a minimal Postgres + repository-abstraction sketch as the primary comparison baseline (since that path is Convex-independent and may be the better default), or is a written comparison sufficient?
5. Do you want a live two-session real-time demo as a deliverable, or is the written recommendation enough?
6. Who owns the institutional-infrastructure facts (SLAC-provided Postgres/object store/SSO availability) needed to fill comparison column (c) credibly — should the spike gather these or receive them?
