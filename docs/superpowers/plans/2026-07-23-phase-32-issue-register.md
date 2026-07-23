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
- **§13-enumerated truth path** (`schema/isaac_record_v1.json`, `official.py`, `draft_validator.py`,
  `export.py`, `audit.py`, `cli.py`) unchanged across all of Phase 31 (verified: `git show --stat 80042f3`
  touches none of them). **Correction (indep. review 2026-07-23):** an earlier draft of this line said
  "`src/isaac_records/` unchanged" — that OVERCLAIMED. P31.1 (`80042f3`) modified the NON-truth extract
  layer `src/isaac_records/extract/structured.py` (+95): added `parse_structured_text`/`_read_csv_text`
  (in-memory) and refactored the shared row reader; the path-based `parse_structured`/`_read_csv` behavior
  is byte-identical and regression-covered (11 extract tests green). The ledger P31.1 entry documents this
  correctly; this register line is now reconciled to it.

## F. P31.4 / Phase-31 closure independent-review findings (verdict: SHIP, 0 critical / 0 important)

| # | File:line | Behavior | Risk | Test requirement | Disposition | Category |
|---|---|---|---|---|---|---|
| F1 | `apps/web/src/lib/types.ts:552` | `ApiCsvPreview.warnings: string[]` mismatches the backend, which emits `list[dict]` `{code,count,message}` (`csv_ingest.py:363-370`). Inert today — `CsvReconcilePanel` never reads `preview.warnings` (only `unknown_header_warnings`); fixtures use `[]`, so tsc/tests don't catch it. Consequence: the backend `unmapped_fields_skipped` count is never surfaced in the UI. | Low — no runtime effect; wrong type + a deferred UI count. | A typed fixture with a populated `warnings` dict + either render it or correct the type. | Minor — fix in Phase 32 (align type; decide whether to surface the count, consistent with the ledger's deferred "precise unmapped-field count"). | functional + documentation |
| F2 | `apps/api/isaac_api/routes.py:817-833` | No `text/csv` media-type gate — the endpoint accepts the raw body regardless of `Content-Type`. | Low — defense-in-depth already rejects non-UTF-8 (`decode_body`) and non-CSV structure (`_validate_header`); no bypass found. | A test asserting a non-CSV media type is rejected (415) if a gate is added. | Minor — evaluate a 415 media-type gate in the Phase 32 backend-security slice. | security (low) |
| F3 | `apps/api/tests/` | UTF-8 BOM handling is by-design (`csv_ingest.py:120` `utf-8-sig`) but has no dedicated test; every other matrix cell is covered. | Low — behavior correct, coverage gap only. | Add a BOM-prefixed CSV regression test. | Minor — add in the Phase 32 test-hardening slice. | test |
| F4 | `apps/web/src/components/CsvReconcilePanel.tsx:95,262` | Client staleness (`previewVersion !== version`) only fires when the parent re-renders with a changed `version` prop; auto-staleness depends on live-sync cadence, else a manual refresh. Backend stays version-bound via If-Match regardless. | Low — UX-freshness gap, not a correctness hole (dupe of the C1 live-sync automation caveat). | Covered by `csv-reconcile-panel.test.tsx:256-264`; consider an in-panel "re-check" affordance. | Minor — consider in Phase 32; overlaps C1. | functional / accessibility |

Residual risks recorded by the reviewer (all non-blocking): `absent_from_record` hosted-unreachable on the
canonical seed (C4; unit-only); no explicit per-chunk memory cap (`_read_bounded_body` caps the running
total after each chunk → peak = `MAX_BODY_BYTES` + one chunk; ledger defers explicit per-chunk cap to P32);
two-window passive-poll staleness human-only (C1).

## G. Phase 32.0 whole-codebase audit — CONSOLIDATED & DEDUPLICATED (2026-07-23 @ `266340e`)

Read-only audit by 4 subagents (backend/security · frontend a11y/responsive · truth/authority ·
tests/CI/docs, all Opus except tests=Sonnet) + orchestrator hosted survey. **No Critical findings. No
Important product/security/truth findings.** Backend security boundaries and the truth/authority path
verified clean (single-source workflow/classifier/ETag; runtime-retrieval is a projection; no-guessing
enforced; confirmed-write surface NOT extended by Phase 31). The two Important items are a test-flake risk
and a stale top-level doc.

**Dedup:** the P31.4 review items map to audit IDs — A1≡FE-1, A2≡FE-3, A3≡FE-2, F1≡FE-4, F4≡FE-5. Rows
below are the merged truth.

**Independent challenge-review (separate Opus, 2026-07-23):** VERDICT — register substantively accurate;
every severity, rejection (F2/FE-5/TR-2/TC-3), dedup mapping, TR-1 (7 pre-existing write keys, zero
Phase-31 touch of `complete.py`), and the §H order verified against real code/tests/git. Only 2
non-severity citation fixes applied (TC-5 `:29→:21`, TC-6 `:23→:27`). No missing findings, no scope-creep,
no dedup/order errors.

| ID (merged) | Subsystem | File:line | Finding | Severity | Category | Disposition |
|---|---|---|---|---|---|---|
| TC-1 | tests/CI | `completion-export.test.tsx:536,558,649,668,699` | 5 assertions with the confirmed B1 flake shape: `fireEvent.click` an AssistantPanel guided chip → **synchronous** `getByText` on the async-swapped answer, same AppRoutes+`stubFetchRoutes` harness as B1. | **Important** | test | FIX → `await findByText` (mirrors B1). Highest priority (CI stability). |
| TC-4 | docs | `README.md:33,87` | Stale counts: "411 Python (plus 138 frontend)" vs actual **887 / 542**; frozen since `0b116f0` (2026-07-19). | **Important** | documentation | FIX → correct counts (ledger already accurate). |
| FE-2 (A3) | frontend a11y | `CsvReconcilePanel.tsx:156-163` | Hidden file `<input>` lacks `tabIndex={-1}` → phantom tab stop (esp. loading/done states with no visible trigger). | Minor | accessibility | FIX → `tabIndex={-1}` + test asserting not a tab stop. |
| FE-6 | frontend | `EvidenceExplorer.tsx:125` vs `214` | `if (!selected)` early-return renders before `<CsvReconcilePanel>`, so a **zero-evidence record can't reach reconciliation**. | Minor | functional | Needs intent decision; if reconciliation should be evidence-independent, hoist the panel above the guard. |
| FE-4 / F1 | frontend + api | `types.ts:552`; `csv_ingest.py:357-384` | Backend emits top-level `warnings: list[dict]` (`unmapped_fields_skipped` count); FE types it `string[]` **and never renders it** → count silently dropped + wrong type. | Minor | functional/documentation | FIX type; decide whether to surface the count (overlaps ledger's deferred "precise unmapped-field count"). |
| FE-1 / A1 | frontend | `CsvReconcilePanel.tsx:57-65` | `safeErrorMessage` trusted-`body.message` branch is unreachable for CSV statuses (`mutationError` attaches body only for 412/400). Dead-ish; safe. | Minor | cleanup | Drop the branch (rely on per-status switch) or comment as forward-looking. |
| FE-3 / A2 | frontend | `types.ts:530` | Per-item `stale` field never read (panel derives staleness itself). Faithful wire mirror. | Minor / arguably not-a-defect | cleanup | Keep (wire-mirror policy) or trim whole mirror — not piecemeal. |
| F3 | tests | `apps/api/tests/` | No dedicated UTF-8 BOM test (behavior correct via `utf-8-sig`). | Minor | test | ADD a BOM regression test. |
| BK-1 | backend | `routes.py:931-932` | `post_validate` defensive `except` interpolates `{exc}` into the body (only if `export_draft` raises; `pragma: no cover`; untriggerable on synthetic data). | Minor | security(low)/cleanup | Return a fixed message; log detail server-side. |
| BK-3 | backend | `routes.py:795-814` | `_read_bounded_body` checks total *after* append → peak = cap + one chunk. (= ledger's deferred per-chunk cap.) | Minor | cleanup | Optional; deferred. |
| TC-2 | tests | `assistant.test.tsx:166-177`, `assistant-conversation.test.tsx:188-219` | Same click→sync-getByText shape but bare `render` (no router/fetch race) → lower flake likelihood. | Minor | test | Optional defensive `findByText`. |
| TC-5 | docs | `README.md:21` | "Works today" omits Phases 25–31. | Minor | documentation | Add a Phase 25–31 pointer. |
| TC-6 | docs | `README.md:27` | "five Claude authoring skills" — actual 8. | Minor | documentation | Correct the count. |
| TC-7 | docs | `docs/architecture.md` | Scopes to the CLI/truth pipeline only; no web/api/memory/ingestion (no false claim, coverage gap). | Minor | documentation | Note the CLI scope or add a companion pointer. |
| TR-1 | truth (doc) | `complete.py:51-179` | Confirmed-write surface is **7** pre-existing keys (`asset-uri, series, descriptor, descriptor_label, edge, qc, timestamp`) — the "5-key" shorthand is imprecise; `qc`/`timestamp` predate Phase 31 (`git log` confirms). No truth risk (reconciliation is read-only). | Documentation-only | documentation | Correct the shorthand where cited. |
| BK-2 | backend (gov) | `auth.py:31-39` | Auth disabled if `ISAAC_UI_API_KEY` unset. **Mitigated in deploy** — hosted probes return 401 on protected routes, so Railway has the key set. | Documentation-only / human-only | governance | Document the hosted-must-set requirement. |
| C1 | frontend/QA | (live-sync) | Two-visible-window passive-poll stale transition — CDP hidden-tab throttling; unit-covered. | Human-only | verification | Human two-window session. |
| C4 | ingestion/QA | (seed) | `absent_from_record` hosted-unreachable on canonical seed; unit-only. | Human-only | verification | Add a hosted fixture only if it doesn't pollute the canonical demo. |

**Rejected as Not-a-defect (with evidence):**
- **F2** (no `text/csv` media-type gate) — client MIME is untrusted/forgeable; `decode_body` (empty/NUL/invalid-UTF-8→400) + `_validate_header` (missing headers→422) + 256 KB body-limit are the authoritative structural boundary; a 415 gate adds browser-incompat risk with no security gain. Matrix suite green. **Do not add.**
- **FE-5 / F4** (prop-driven staleness) — works as intended via the `useRecordSession` poller (`EvidenceExplorer.tsx:46-49`); `csv-reconcile-panel.test.tsx:256-264` codifies it.
- **TR-2** (CSV reconciliation write) — pure read; no `apply_answers`/`save_versioned` in `csv_ingest.py`.
- **TC-3 / B2** (the 1 skip) — legitimate real-graph smoke test gated on the gitignored `graphify-out/graph.json`; correctly justified.

**Verified-clean (high-confidence, from the audit):** filename/path-traversal (`safe_source_name`, `sources._guard_name`), reset governance (synthetic-gate + confirm phrase + `extra=forbid` + direct-child removal), ETag/If-Match (428/412/400, opaque token), runtime-mode fail-closed (refuses boot in `real`/invalid), CORS (credentials off, ETag exposed), uploads 403, `.dockerignore`/Dockerfile allowlist (no secret, `examples/`/`records/`/`drafts/` excluded), atomic writes, single-source workflow/classifier/ETag, no-guessing extraction, snapshot gate 17/17, 0 `.only`, fake-timers correct, global session-isolation `afterEach`.

## H. Recommended implementation order (Phase 32 slices)

1. **S1 — CI stability** (Important): TC-1 (+ TC-2 defensively) → `await findByText`. No product behavior change; de-risks every downstream closure gate.
2. **S2 — accessibility** (Minor→user-facing): FE-2 `tabIndex={-1}` + test.
3. **S3 — documentation truth** (Important+Minor): TC-4/TC-5/TC-6/TC-7 + TR-1/BK-2 notes; README/architecture reconciliation.
4. **S4 — frontend cleanup**: FE-4/F1 (type + count decision), FE-1 (dead branch), FE-3 (mirror policy), FE-6 (zero-evidence panel — intent decision).
5. **S5 — backend cleanup/tests**: BK-1 (fixed error message), F3 (BOM test), BK-3 (optional per-chunk cap).
6. **S6 — data-governance/doc pass**, then Project-Memory refresh, full hosted E2E QA, final independent review, release closure.

Dependencies: S1 is independent and first (unblocks stable CI for all others). S3 depends on final counts (stable after S1/S2). Truth/authority need no fixes (clean).

## E. Not yet audited / deferred to later Phase 32 slices

Full hosted E2E synthetic journey (search · runtime triage · assistant read/explain · export artifacts ·
offline/degraded on canonical data) beyond the CSV surface already QA'd; static Project Memory refresh
(after code+docs stabilize); narrow-viewport responsive **human** check (automation renders at fixed
~1483px — see §C). Each implementation slice: test-first, affected full suite, snapshot/R4.3, independent
Opus review, hosted QA when user-visible, ≤5 subagents, subagents never commit.
