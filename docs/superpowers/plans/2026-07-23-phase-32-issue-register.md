# Phase 32 — Issue Register (initial seed)

Status: **OPEN / in progress.** Created 2026-07-23 at HEAD `265e23f` (P31.3 shipped, Phase 31 not yet
closed). This register seeds Phase 32 with the **known carried-forward findings** from the independent
reviews, prior-phase QA caveats, and a bounded read-only codebase hygiene grep. It is NOT a completed
whole-codebase audit — the exhaustive audit + fixes proceed as Phase 32 slices, each independently
reviewed. Nothing here is fabricated; each row cites concrete evidence.

Orchestrator this session: **Opus 4.8** (Fable 5 unconfirmed in-account; ratified fallback per CLAUDE.md
§17). Implementation is delegated to Opus/Sonnet subagents; subagents do not commit/push.

Classification: Critical · Important · Minor · Documentation-only · Human-only verification.

## A. P31.3 independent-review Minor findings (SHIP; carried forward)

| # | File:line | Behavior | Risk | Test requirement | Disposition | Category |
|---|---|---|---|---|---|---|
| A1 | `apps/web/src/components/CsvReconcilePanel.tsx:57-65` (`safeErrorMessage` trusted-body branch) | The trusted `body.message` branch is near-dead for CSV ingress: `mutationError` (`api.ts`) only attaches `body` for statuses 412/400, so 413/422/403/428 always use the client's per-status sentence. | Low — all fallbacks are path-free; safe. Dead-ish branch is a maintainability smell only. | A unit test that asserts either the branch is reachable for a defined status, or removes it and pins the per-status sentences. | Minor — clean up or cover; no behavior change. | cleanup |
| A2 | `apps/web/src/lib/types.ts` (`ApiCsvReconcileItem.stale`) | Per-item `stale` is fetched but never rendered; staleness is derived at the component level (`previewVersion !== version`). | None functional; redundant field. | Test documenting single source of staleness; optionally drop the unused field. | Minor — cleanup. | cleanup |
| A3 | `apps/web/src/components/CsvReconcilePanel.tsx:156-163` (always-mounted hidden file input) | The visually-hidden `<input type=file>` and its trigger `<button>` are both in the tab order → two focus stops for one action. | Minor a11y redundancy; both are labeled and functional. | a11y test asserting a single logical focus path (e.g. `tabindex=-1` on the input, or a `<label>`-driven trigger). | Minor — a11y refinement in the Phase 32 accessibility slice. | accessibility + cleanup |

## B. CI / test stability

| # | File:line | Behavior | Risk | Test requirement | Disposition | Category |
|---|---|---|---|---|---|---|
| B1 | `apps/web/src/__tests__/memory-status.test.tsx:290-293` | Clicked a guided chip then **synchronously** asserted the answer text (`getByText`) with no wait. Passed CI at `7b202b6`, **failed** CI at `265e23f` (flake — CI DOM dump showed the pre-answer panel), passes locally 17/17 ×3. | **Important** — a nondeterministic frontend test would intermittently fail CI, repeatedly blocking the "CI green on every closure commit" gate across Phase 32's many pushes. | Post-click assertion now uses `await findByText` (retry-until-present). | **FIXED** 2026-07-23 (test-only, no production change) — justified as blocking since it caused a real CI failure. | cleanup (test) |
| B2 | (repo-wide) 1 skipped test present | One `skip` marker exists in the suite (grep count = 1). | Low until identified. | Identify the skip, justify or re-enable. | Minor — enumerate in the audit slice. | cleanup |

## C. Carried-forward QA caveats (from ledger + project memory)

| # | Source | Behavior | Risk | Disposition | Category |
|---|---|---|---|---|---|
| C1 | Phase 27/28 gates + memory `hosted-qa` | Passive-poll **two-visible-window** live-sync check (idle live banner + ~8s cadence + offline indicator) is unit-verified but NOT automation-observable (CDP hidden-tab throttling). | None (mechanism unit-tested). | **Human-only verification** — one genuine two-window session. Do not label visually verified otherwise. | human-only |
| C2 | memory `artifact-stale-not-ui-reachable` (P28.2) | Exported-artifact `stale` transition is backend/unit-verified but not UI-reachable (exported records read-only). | None. | Revisit in the Phase 32 UI audit if an exported-record edit path is ever surfaced. | human-only / documentation |
| C3 | Phase 30 closure notes | Degraded-assistant + live conflicting/insufficient/unknown evidence states are unit-verified but not exercised on canonical synthetic data (no such states in the seed). | None. | Note in audit; add a synthetic fixture only if it doesn't pollute the canonical demo. | documentation / human-only |
| C4 | Phase 31 plan §11 + this session's hosted QA | `absent_from_record` is unreachable via hosted upload against the canonical seed (all FIELD_MAP paths populated); unit-covered (`test_csv_reconcile.py`). | None. | Verify via component/integration tests; add a hosted fixture only if it doesn't pollute the canonical demo. | documentation / test |

## D. Bounded codebase hygiene (read-only grep, 2026-07-23 @ `265e23f`)

- TODO/FIXME/HACK/XXX in `apps/api/isaac_api`, `apps/web/src`, `src/isaac_records`: **0**.
- `.only` focused tests in `apps/web/src`: **0**.
- Skipped tests (frontend+backend): **1** (see B2).
- Truth path untouched by P31 (`src/isaac_records/`, `schema/` unchanged).

## E. Not yet audited (Phase 32 slices to run)

Frontend visual refinement · accessibility audit · responsive audit · backend security audit ·
data-governance audit · authority/state-consistency audit · documentation refresh (incl. any stale test
counts) · static Project Memory refresh · dead-code sweep · disabled-controls sweep · internal-path/leak
sweep. Each runs test-first where implementation is required, with a separate Opus 4.8 reviewer per
release slice, ≤5 subagents per task, subagents never committing.
