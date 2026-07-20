# Phase — Final Product Stabilization & Release (Plan)

Status: PROPOSED — awaiting approval. Direction **DECISION-LOCKED 2026-07-20** (required-now vs
institutional split confirmed; persistence stays ephemeral — richer synthetic seed instead of a
durable store). No implementation authorized.
Date: 2026-07-19 (decisions locked 2026-07-20) · Baseline commit: `f534a4c` · Author: Claude (planning)
Related: `2026-07-16-phases-23-26-arc-decisions.md`; `2026-07-20-remaining-work-decision-lock.md` (authoritative); P24 specs; this EXTENDS the approved arc. Runs **after** Phase 25 (Grounded Assistant) and Phase 26 (Workspace + Memory Search) so it stabilizes the *finished* feature set — but the truth-path / deploy / governance regression tracks can start independently at any time.
Approval decisions required: see §25 (most now RESOLVED by the decision-lock).

> Authoring note: this plan was written directly by the planning orchestrator after the delegated authoring agent failed to execute twice (returned no work). Content is grounded in the verified `f534a4c` baseline and the repo audits (`scratchpad/audit-*.md`).

---

## 1. Purpose
Take the completed ISAAC prototype (truth core + hosted FastAPI/React app + Project Memory + grounded assistant + real search) from "features shipped" to "demo-grade, release-verified, honestly-documented," with a repeatable release checklist and a deterministic regression net across both planes.

## 2. User/scientist value
A scientist can run the full draft→complete→validate→export→audit workflow, navigate freely (reload, deep-link, keyboard-only), and always sees honest states (loading / empty / error / backend-down / memory-degraded) — never a fabricated or broken screen.

## 3. Mentor/demo value
A single, rehearsed, reproducible demo path that never surprises; a one-command local bring-up; a green CI badge; and a documented "what is real vs synthetic vs institutional" story that survives hard questions.

## 4. Architectural value
Locks in the two-plane invariant with a consolidated regression suite, a route/type-alignment check, and a snapshot-drift gate, so future work cannot silently regress truth determinism, memory honesty, or the frontend/backend contract.

## 5. Dependencies
- P25 (Grounded Assistant) and P26 (Search) complete — for the assistant/search stabilization slices.
- Independent of P25/P26: truth-path regression, schema/export/audit, snapshot regen+drift, deployment/rollback, security/governance, docs-truth.
- No new dependencies introduced.

## 6. Scope
End-to-end behavioral verification, contract/type alignment, state-matrix coverage, performance/bundle sanity, deployment/rollback verification, security/governance audit, documentation-truth audit, and a final release checklist. Fixes found are small scoped corrections (each its own reviewed slice), not features.

## 7. Non-goals
- No new features. No redesign (that is the UI-refinement plan).
- No production-ops infrastructure pulled into the required core (see §14 judgment call).
- No real/private data. No second domain. No auth/persistence rearchitecture (that is the institutional plan).

## 8. Current baseline (cite files)
- Backend 461 tests (CI 460 pass + 1 conditional real-graph `skipif`); frontend 137/17 files; official validate `PASS v1.05`; audit `33/33`; CI green (run 29716773864); deployed `f534a4c`. Truth path untouched by P24.10.
- Degraded states already honest/reason-coded (`FetchStates.tsx`, memory reason codes). A11y baseline strong (skip link, ARIA dialog/focus-trap, `aria-live`). Health endpoint returns build commit. Rollback documented in `2026-07-11-phase-20-deployment.md` / `docs/deployment.md`.
- Gaps this plan closes: no consolidated E2E path test; no automated frontend/backend contract-alignment check; no keyboard-only walkthrough evidence; stale docs (see the deliverables plan).

## 9. Files likely touched
Tests only + docs: `apps/api/tests/*`, `apps/web/src/__tests__/*`, `.github/workflows/ci.yml` (only if a check must be added), `docs/deployment.md`, `docs/operator-playbook.md`, `docs/ui-local-dev.md`, a new `docs/release-checklist.md`. No product source unless a scoped bug fix is required (each such fix is its own slice with its own review).

## 10. Files that must NOT be touched
`schema/isaac_record_v1.json`; `src/isaac_records/*` (except a reviewed bug-fix slice); the committed snapshot except via `scripts/build_memory_snapshot.py --check`. No changes to the auth/persistence architecture here.

## 11. Data flow
Verification only — exercises existing flows (frontend → `/api/*` → `isaac_records`/memory reader → response). Adds no new data paths.

## 12. API/contracts
Produce a route inventory (21 backend routes at baseline; +1 `/api/search` after P26) cross-checked against the client methods in `lib/api.ts`; assert every client call maps to a real route and every non-internal route has a typed client shape. A contract-alignment test (backend response keys ↔ TS types) is the key new artifact.

## 13. UI behavior
No visual change. Verify each screen renders correctly in loading / data / empty / error / backend-down states and under keyboard-only navigation, reload, and deep-link.

## 14. Security/governance constraints
Secret/path/private-data sweep (no secrets committed; snapshot ships metadata-only; `git check-ignore` on generated artifacts); synthetic-only confirmation; truth core stays Graphify-free and authoritative.
**Judgment call — required-now vs institutional (explicit) — LOCKED (decision-lock 2026-07-20):**
- **Required now (in-core):** honest error/degraded states; deterministic health endpoint; documented rollback; CI gate; secret-hygiene; CORS correctness; the always-403 upload wall.
- **Deferred to Institutional plan / back-burner (do NOT add to required core):** rate limiting, WAF, third-party monitoring/APM vendors, log aggregation, uptime alerting, autoscaling. Rationale: this is a synthetic, protection-gated demo with a single shared key and ephemeral state; production-ops infra is the institution's responsibility and adding vendor dependencies now would violate the "functional with synthetic/demo providers" target and the dependency-discipline rule. If any single item is wanted for the demo (e.g., a minimal request log), it gets its own justified slice.

## 15. Risks
- E2E tests can be flaky (timing) — mitigate with the existing `useFetch`/stub harness patterns, deterministic fixtures.
- Ephemeral shared hosted workspace means hosted E2E must not assume persistence across restarts (verify the honest re-seed behavior instead).
- A stabilization bug fix could touch product source — each such fix is a separate reviewed slice, not folded in silently.

## 16. Tests
Consolidated E2E workflow test (draft→complete→validate→export→audit); navigation/reload/deep-link tests; keyboard-only walkthrough test; state-matrix tests (loading/error/empty/backend-down × key screens); memory-state matrix (missing/malformed/stale/current); auth-failure/expired-key test; contract-alignment test; snapshot `--check` + committed-snapshot gate (already exists — include in the release run); truth-path regression (existing suite). **Richer synthetic seed verification (decision-lock §5):** confirm the deterministic seed (owned by **Phase 26 / P26.0a**, not re-implemented here) reseeds honestly after restart, is stable across runs, covers the target workflow states, and is clearly synthetic/demo-labeled — the demo's richness comes from this seed, **not** from durable persistence.

## 17. Verification
`pytest -q` (backend, repo root), `npx vitest run` + `npm run build` (frontend), `isaac validate --official`, `isaac audit`, `scripts/build_memory_snapshot.py --check`, `scripts/check_graphify_freshness.py`, a manual keyboard-only + reload pass, and a hosted smoke (health commit match + Project Memory axes + a record workflow).

## 18. Deployment impact
No behavior change. May add a CI check (contract-alignment/E2E). Confirms Railway/Vercel deploy + rollback procedure; produces `docs/release-checklist.md`.

## 19. Documentation impact
Create `docs/release-checklist.md`; update `docs/operator-playbook.md` (rollback + verify steps) and `docs/deployment.md` if verification reveals drift. The stale-doc fixes are owned by the Documentation plan; this plan's docs-truth audit *flags* remaining ones.

## 20. Bite-sized slices
Each: objective · files touched · files forbidden · model · acceptance · tests · report · commit · stop.
- **S-STAB.1 — Route/contract inventory + alignment test.** Enumerate the routes (21 at baseline, +1 `/api/search` after P26) ↔ client methods; add a test asserting alignment. Files: `apps/api/tests/`, `apps/web/src/__tests__/`. Forbidden: product source. Model: Sonnet. Accept: every route/method mapped; test green. Commit: one. Stop: report the map + any mismatch found (mismatch → separate fix slice).
- **S-STAB.2 — E2E primary-workflow test.** One test driving draft→complete→validate→export→audit against the stub harness. Model: Sonnet. Stop after green.
- **S-STAB.3 — Navigation / reload / deep-link / keyboard-only tests + manual evidence.** Model: Opus (a11y judgment). Stop with a11y notes.
- **S-STAB.4 — State-matrix + memory-state-matrix tests.** loading/error/empty/backend-down × screens; memory missing/malformed/stale/current. Model: Sonnet. Stop after green.
- **S-STAB.5 — Auth-failure / expired-key behavior test + honest messaging check.** Model: Sonnet. Stop.
- **S-STAB.6 — Truth-path + schema + export + audit regression sweep** (run existing suites, document coverage; no code). Model: Sonnet. Stop.
- **S-STAB.7 — Snapshot regen + drift + memory-honesty verification** (`--check`, committed gate, freshness script). Model: Sonnet. Stop.
- **S-STAB.8 — Performance + bundle review** (bundle size trend, obvious N+1/latency on `/api/*`). Model: Opus. Stop with findings (fixes = separate slices).
- **S-STAB.9 — Security/governance audit** (secret/path/private-data sweep; synthetic-only; Graphify-free reconfirm; upload-wall). Model: Opus. Stop with a signed checklist.
- **S-STAB.10 — Documentation-truth audit + release checklist authoring** (flag stale claims for the Docs plan; write `docs/release-checklist.md`; label historical docs). Model: Sonnet. Stop.
- **S-STAB.11 — Deployment + rollback verification** (deploy a no-op, verify health-commit match, exercise rollback per playbook). Model: Opus. Stop.

## 21. Model/subagent assignment
Orchestrator = **Fable 5 when available, else Opus 4.8** (planner/reviewer/verifier; authors planning markdown; never implements production code). Opus 4.8 (implementation) for a11y, performance, security/governance, deployment/rollback judgment; Sonnet 5 (implementation) for mechanical test authoring, inventories, matrices, checklist formatting. Orchestrator reviews + verifies each slice.

## 22. Acceptance criteria
All new + existing tests green in CI; contract alignment proven by test; E2E + state matrices covered; keyboard-only + reload + deep-link verified with evidence; truth-path/schema/export/audit/snapshot regressions green; security/governance checklist signed; `docs/release-checklist.md` exists and was followed once end-to-end; no stale claims remain unflagged.

## 23. Stop/approval gates
Stop after each slice with a report. Hard gate before any hosted deploy in S-STAB.11. Final gate: present the completed release checklist + verification evidence for approval before declaring the product "release-verified."

## 24. Deferred items
Rate limiting, monitoring/APM vendors, log aggregation, uptime alerting, autoscaling, multi-user load testing → Institutional plan / back-burner. Visual polish → UI-refinement plan. Stale-doc *content rewrites* → Documentation plan (this plan only flags them).

## 25. Explicit questions for the user
1. ✅ **RESOLVED** — required-now vs institutional split in §14 confirmed (**NO** rate-limiting/monitoring vendors added to the core now).
2. ✅ **RESOLVED** — hosted E2E assumes the **ephemeral shared workspace** and verifies honest re-seed; durable persistence is **not** prioritized. Demo richness comes from the deterministic richer synthetic seed (Phase 26 / P26.0a), not a durable store.
3. **OPEN** — add a CI job for the frontend/backend contract-alignment test, or keep it local-only?
4. **OPEN** — is a minimal request/access log wanted for the demo, or explicitly deferred?
