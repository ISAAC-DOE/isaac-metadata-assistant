# Phase 36 — Repository-Local Native Enhancements · Closure

**Status:** CLOSED 2026-07-24 at org `main` `5bb25a8` (image `v0.0.11`) — feature slices P36.1–P36.6
plus the **P36.8 workflow-progression + demo-idempotence closure slice** (see §4). Hardening H3 decided;
H1/H2 specified and staged for Dean-in-the-loop PRs (not auto-merged — see §3).
**Owner:** orchestrator (Opus 4.8, ratified fallback for Fable 5).
**Plan of record:** `docs/superpowers/plans/2026-07-24-phase-36-native-enhancements-plan.md`.

All slices: synthetic-only, deterministic, no LLM, no portal dependency, no real data, no Postgres, no
new secret, truth core (`schema/`, `src/isaac_records/`) untouched. Each shipped slice ran: Sonnet
implement → independent Opus review → full backend+frontend suites + `tsc -b` + snapshot regen +
committed-snapshot gate → PR → **Create-a-merge-commit** → GHCR image + Flux. **Hosted QA of every
image is Krish-gated** (Authentik edge; not self-verifiable from this environment).

---

## 1. Shipped slices

| Slice | Image | Merge commit | Impl / Review | Backend / Frontend tests |
|---|---|---|---|---|
| **P36.1** Assistant empty-state cleanup | `v0.0.5` | `05a051e` | Sonnet / Opus **SHIP** | 993 / 672→(no net) |
| **P36.2** Project Memory Graph tab | `v0.0.6` | `5e8edfc` | Sonnet+Opus-arch / Opus **SHIP** | 993 / 685 |
| **P36.3** Standalone Validator | `v0.0.7` | `b9f1288` | Sonnet / Opus **SHIP** | 1006 / 700 |
| **P36.4** API Docs + Help/About | `v0.0.8` | `e8a576d` | Sonnet / orchestrator-run review* | 1018 / 715 |
| **P36.6** Schema & Vocabulary browser | `v0.0.9` | `5d99fcb` | Sonnet / Opus **SHIP-w-nits** (fixed) | 1028 / 735 |

*P36.4's independent-review subagent was preempted by an account session limit; the orchestrator ran
the deterministic review battery (live `/about`+`/openapi` leak scan → clean, no-CDN, no-mutation,
base-path, truth-core-untouched) + full code inspection. All other slices had a fresh independent Opus
review before merge.

- **P36.1** — removed the redundant resting Assistant placeholder; the single `aria-live="polite"`
  reply element stays mounted (announcements preserved); no filler card. All 5 mounting surfaces.
- **P36.2** — new "Graph" tab: a deterministic, capped, read-only **served-file reference projection**
  of the committed snapshot (`GET /api/memory/graph`, stdlib-only `memory_graph.py`, no Graphify/
  `isaac_records` import, no forbidden keys, honest `available:false`). Bounded SVG + textual node list
  as the primary a11y affordance; real 5 relation types preserved; underlying source graph
  (2988/4465/257) disclosed "not embedded." NOT an ontology.
- **P36.3** — Standalone Validator in Governance & Safety, reusing the authoritative
  `validate_official` (`POST /api/validate/record`; 512 KB bound-before-parse → 413; 422 on
  malformed/non-object; no content logging/persistence/mutation; verdict parity tested).
- **P36.4** — Settings made functional: `GET /api/about` (non-sensitive app metadata; leak-scanned
  clean) + `GET /api/openapi` (base-path-correct); self-contained API-docs renderer (no CDN/Swagger).
- **P36.6** — read-only Schema & Vocabulary browser (`GET /api/schema`, byte-faithful to on-disk +
  `vocabulary/*.json`); Governance & Safety reorganized into Policy / Validator / Schema tabs; `allOf`/
  `if`/`then` relationships rendered verbatim (nothing invented). NOT the portal Ontology system.

---

## 2. Skipped slices (documented, no code)

- **P36.5 — New Record coverage audit → SKIP.** An Opus audit ran the real core end-to-end (export
  `ok`, official `ok`, all blockers resolved) + 156 focused tests and traced every enum/structured
  entry point. **No material (A) gaps:** required-field coverage is complete, export is schema-valid
  v1.05, validation parity holds (`pending=0` does not grant export — S6 runs the real official dry-run
  and blocks on failure), and no enum is settable to an invalid value. Findings were all (B)
  acceptable-as-is or (C) out-of-scope (electrochemistry/computation/simulation domains, real-data
  ingest — not authorized). **Optional future tidies (non-gaps, deferred):** (B1) a self-authored
  `tags[]` input to reduce the standing advisory `NO_LINKS` nudge (`export.py` already serializes
  `tags`; `draft_validator.py` treats them evidence-exempt; the local `_no_links` heuristic would also
  need to consider `tags`); (B2) a one-line comment noting the unreachable latent `qc` pending blocker
  (`draft_builder.py` emits a `qc` blocker whose key is not in the `_answers_to_apply_shape` set —
  unreachable because the committed CSV always carries `qc_status` and file upload is 403-blocked).
- **P36.7 — Workspace Overview → SKIP (redundant).** A synthetic-only overview would duplicate **My
  Experiments** (the record queue + statuses) and **Settings → Help/About** (build/schema metadata), or
  require fabricated analytics (explicitly forbidden). The genuine operational **System Overview** (real
  analytics, role-gated, IP-redacted) is portal/real-data-dependent → Phase 37, not authorized. No
  redundant page or nav item added.

---

## 3. Hardening

- **H3 — `ApiKeyAuthMiddleware` → RETAIN + defer removal (decided; zero code change).** `auth.py` is a
  presentation-layer shared-secret bearer gate that is **disabled (pass-through) when `ISAAC_UI_API_KEY`
  is unset** — which is the production configuration (Authentik at the edge is the auth boundary), so it
  is a **no-op in prod**. It provides real value for a non-Authentik dev/demo deployment. Removing it
  has no prod benefit and loses that capability. The "loud startup warning for asymmetric config"
  option is **not implementable correctly**: the asymmetry is server key set (`ISAAC_UI_API_KEY`) while
  the SPA key (`VITE_API_KEY`) is unset, but `VITE_API_KEY` is a frontend build-time variable the
  backend cannot observe at runtime — a backend warning cannot reliably detect it. Decision: **retain
  as-is, defer removal, document the asymmetric-config caveat.** No personal or SPA key is introduced in
  production. Any future change requires tests + an independent security review.

- **H1 — remove mutable `:latest` (specified; NOT auto-merged).** `build-push.yaml`'s "Build and push"
  step tags both `${version}` and `:latest`. The exact fix is to delete the single line
  `${{ env.REGISTRY }}/${{ steps.image.outputs.name }}:latest` from the `tags:` block; the semver tag,
  the git-tag step, and Flux (which follows immutable semver per Dean's guide §6) are all unaffected.
  **Why not auto-merged this session:** (a) `build-push.yaml` triggers **only** on push-to-main / `v*`
  tags — it does **not** run in PR CI — so a bad edit surfaces only at the next production deploy,
  uncatchable pre-merge from this environment; (b) the "confirm no deployment component depends on
  `:latest`" bar requires visibility into `ISAAC-DOE/isaac-k8` (Flux manifests), which is out of scope
  and forbidden to modify. Dean's guide asserts semver-only, so the change aligns with his contract, but
  it should land as a focused PR **with Dean in the loop** (deploy workflow ownership + isaac-k8
  awareness). **Residual:** cannot prove from this repo that no out-of-repo consumer pulls `:latest`.

- **H2 — pin GitHub Actions to commit SHAs (specified; NOT auto-merged for the deploy workflow).**
  Actions in use: `actions/checkout@v4` (build-push, pr-smoke) and `@v5` (ci); `docker/login-action@v3`;
  `docker/build-push-action@v5`; `actions/setup-python@v6`; `actions/setup-node@v4`. Pinning = replace
  each `@vX` with `@<immutable-commit-sha>  # vX` (no permissions/behavior change). **CI-plane workflows
  (`ci.yml`, `pr-docker-smoke.yml`) are PR-CI-verified** — a wrong SHA fails the PR before merge — so
  those can be pinned in a normal reviewed PR safely. **`build-push.yaml` is NOT PR-CI-verified** (runs
  only post-merge), so pinning it carries the same "surfaces only at deploy" risk as H1 → land it with
  Dean in the loop. Requires an independent supply-chain review (resolve each tag→SHA at PR time).

**Bottom line:** H3 decided; H1 + H2 fully specified with exact diffs + residual risks, staged as
Dean-in-the-loop PRs rather than autonomously merged deploy-workflow changes.

---

## 4. P36.8 — Workflow-progression + demo-idempotence closure slice

**Shipped `v0.0.11`, merge `5bb25a8`, PR #9. Sonnet implement → independent Opus review (SHIP; 0
critical, 0 important) → frontend 751 / backend 1029 / `tsc -b` + vite build / snapshot regen (no drift)
+ gate 17 → Create-a-merge-commit → GHCR `v0.0.11` + Flux.** Frontend-only; truth/validation/export/
workflow-derivation path (`schema/`, `src/isaac_records/`, `official.py`, `workflow.py`) byte-untouched;
no new backend endpoint; runtime mode / persistence / auth unchanged.

- **Root cause (Task 2):** export-readiness is **fully derived** by `workflow.py::derive_workflow`
  (`current_step` = first unsatisfied step; export unlocks automatically when `pending_count == 0` and the
  official-schema export dry-run passes). There is **no** human "review readiness" step (no button/flag/
  route; `review.py` is inert) — so the "populated but Export-gated" screenshot is **UX ambiguity, not a
  state-transition bug**. Key invariant the copy relies on: `current_step == 'review_export_readiness'`
  can occur **only** when `pending==0 && draft_ok` and the official dry-run is **failing** (else
  `current_step` would already be `export`).
- **The banner** (`apps/web/src/components/WorkflowProgressBanner.tsx`, mounted on the four record
  screens via `AppShell`): compact, state-driven, driven purely by `workflow.current_step` +
  `pending_count`. States — `complete_metadata` → "N items need your attention"; `review_evidence` →
  "Evidence review needed"; `review_export_readiness` (dry-run failing) → **"Not ready to export yet"**
  (never a serene "complete"); `export` (dry-run passing) → "Ready to export"; done → no banner.
  Suppressed on the step's own surface (no duplicate CTA) and where a screen already owns the CTA
  (`RecordWorkbench` `excludeSteps=['complete_metadata']`, deferring to its resident `.needsyou-banner`).
  react-router navigation preserves record context / `/krish` base-path / back-forward; never mutates a
  value or bypasses a gate; moves focus to `<main>` on the destination (AppShell one-shot `focusMain`
  effect + `tabIndex=-1`).
- **Synthetic-demo idempotence (Task 4):** audit found repeated **Run Synthetic Demo** already
  **idempotent by construction** — fixed `CANONICAL_IDS`, upsert-in-place, count pinned at 5, no random
  ULID on that path, real data untouchable (synthetic-only fail-closed, committed fixtures, uploads
  403). The five XANES records are **intentional distinct workflow-state examples**, not repeated-run
  artifacts. **No code/UI change; no Reset button added** (a guarded `demo_reset` already exists,
  correctly separated). Added one **regression guard** (`test_repeated_mixed_demo_runs_only_ever_canonical_ids`)
  asserting the id set stays exactly `CANONICAL_IDS` across 8 interleaved `draft_only`/`full` runs.
- **Accessibility:** `role="note"`, named `<button>`, keyboard-operable, `aria-hidden` icon, meaning by
  icon+heading+text (not color alone), focus-to-`<main>`; CSS token-only, no fixed heights, 640px stack
  → structurally 200%/narrow-safe. The **human responsive / 200%-zoom render sign-off remains Krish's**.

## 5. Open items carried forward (Krish / Dean)

- **Hosted QA** of `v0.0.4`–`v0.0.11` at `/krish` (Authentik-gated): `/krish/api/health` `commit` should
  read `5bb25a8` once Flux rolls `v0.0.11`; smoke the Assistant (no resting card), the Graph tab, the
  Validator, Help/About + API Docs (Settings), the Schema & Vocabulary browser (Governance & Safety
  tabs), and the **new progression banner** across the record screens (correct next-action per state; no
  duplicate CTA on a step's own surface; keyboard + focus move).
- **Responsive / 200%-zoom human visual sign-off** (standing gate) across the new surfaces.
- **Personal-deploy retirement** (Vercel `isaac-demo-web` + Railway — dashboard disable-not-delete).
- **H1 + H2 hardening PRs** (Dean in the loop); **H3** documented decision (retain + defer).

No Phase 37 work started. The truth/no-guessing/synthetic-only boundaries held throughout.
