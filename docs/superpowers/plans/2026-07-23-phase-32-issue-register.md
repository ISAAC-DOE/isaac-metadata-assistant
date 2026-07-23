# Phase 32 — Issue Register (initial seed)

Status: **CLOSED 2026-07-23** at HEAD `058fccc` (see the Phase 32 Closure section at the end).
Created 2026-07-23 at HEAD `265e23f` (P31.3 shipped, Phase 31 not yet
closed). This register seeded Phase 32 with the **known carried-forward findings** from the independent
reviews, prior-phase QA caveats, and a bounded read-only codebase hygiene grep, then grew into the full
whole-codebase audit + fixes across slices S1–S6, each independently reviewed. Nothing here is
fabricated; each row cites concrete evidence.

Orchestrator this session: **Opus 4.8** (Fable 5 unconfirmed in-account; ratified fallback per CLAUDE.md
§17). Implementation is delegated to Opus/Sonnet subagents; subagents do not commit/push.

Classification: Critical · Important · Minor · Documentation-only · Human-only verification.

## A. P31.3 independent-review Minor findings (SHIP; carried forward)

| # | File:line | Behavior | Risk | Test requirement | Disposition | Category |
|---|---|---|---|---|---|---|
| A1 | `apps/web/src/components/CsvReconcilePanel.tsx:57-65` (`safeErrorMessage` trusted-body branch) | The trusted `body.message` branch is near-dead for CSV ingress: `mutationError` (`api.ts`) only attaches `body` for statuses 412/400, so 413/422/403/428 always use the client's per-status sentence. | Low — all fallbacks are path-free; safe. Dead-ish branch is a maintainability smell only. | A unit test that asserts either the branch is reachable for a defined status, or removes it and pins the per-status sentences. | Minor — clean up or cover; no behavior change. | cleanup |
| A2 | `apps/web/src/lib/types.ts` (`ApiCsvReconcileItem.stale`) | Per-item `stale` is fetched but never rendered; staleness is derived at the component level (`previewVersion !== version`). | None functional; redundant field. | Test documenting single source of staleness; optionally drop the unused field. | Minor — cleanup. | cleanup |
| A3 | `apps/web/src/components/CsvReconcilePanel.tsx:156-163` (always-mounted hidden file input) | The visually-hidden `<input type=file>` and its trigger `<button>` are both in the tab order → two focus stops for one action. | Minor a11y redundancy; both are labeled and functional. | a11y test asserting a single logical focus path (e.g. `tabindex=-1` on the input, or a `<label>`-driven trigger). | **FIXED** at `bf85578` (S2) — `tabIndex={-1}` on the hidden input + 3 a11y tests; independent Opus review = SHIP. | accessibility + cleanup |

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
| TC-1 | tests/CI | `completion-export.test.tsx:536,558,649,668,699` | 5 assertions with the confirmed B1 flake shape: `fireEvent.click` an AssistantPanel guided chip → **synchronous** `getByText` on the async-swapped answer, same AppRoutes+`stubFetchRoutes` harness as B1. | **Important** | test | **FIXED** at `a93ea0a` (S1) — `await findByText` (mirrors B1's earlier fix at `e45db20`). Root cause: the "B1 flake shape" (sync `getByText` after async chip render). |
| TC-4 | docs | `README.md:33,87` | Stale counts: "411 Python (plus 138 frontend)" vs actual **887 / 542**; frozen since `0b116f0` (2026-07-19). | **Important** | documentation | **FIXED** (S3, this pass) — README counts corrected to **887 / 545** (frontend count grew 542 → 545 via the S2 a11y tests) and consolidated to one authoritative line; the quickstart comment no longer hardcodes a count. |
| FE-2 (A3) | frontend a11y | `CsvReconcilePanel.tsx:156-163` | Hidden file `<input>` lacks `tabIndex={-1}` → phantom tab stop (esp. loading/done states with no visible trigger). | Minor | accessibility | **FIXED** at `bf85578` (S2) — `tabIndex={-1}` + 3 a11y tests; independent Opus review = SHIP. Frontend suite 542 → 545. |
| FE-6 | frontend | `EvidenceExplorer.tsx:125` vs `214` | `if (!selected)` early-return renders before `<CsvReconcilePanel>`, so a **zero-evidence record can't reach reconciliation**. | Minor | functional | **ACCEPTED / working-as-intended (S4)** — the zero-evidence branch is an *honest* empty state ("No evidence has been recorded"), and excluding panels from it is a **documented intentional** design decision (`EvidenceExplorer.tsx:151-157`: subordinate panels mount "ONLY on this loaded path — never in ... the zero-evidence empty state"). Reconciliation is reachable for every record that has evidence (all canonical demo records). Hosting reconciliation on a bare empty-state screen is a UX/product expansion, not an audit fix; deferred as a possible future enhancement. No false "evidence passed" implication exists today. |
| FE-4 / F1 | frontend + api | `types.ts:552`; `csv_ingest.py:357-384` | Backend emits top-level `warnings: list[dict]` (`unmapped_fields_skipped` count); FE types it `string[]` **and never renders it** → count silently dropped + wrong type. | Minor | functional/documentation | **FIXED at S4 (this pass) ** — added authoritative `ApiCsvWarning {code, message, count?}`; `ApiCsvPreview.warnings: string[]` → `ApiCsvWarning[]`; render as a separate "Processing warnings" list via `warningText()` (safe `message` + `(count)` when finite>0; never dumps the raw object / `[object Object]` / unknown fields). 3 render tests (message+count, empty, unknown-extra-field guard). |
| FE-1 / A1 | frontend | `CsvReconcilePanel.tsx:57-65` | ~~`safeErrorMessage` trusted-`body.message` branch is unreachable for CSV statuses~~ — **audit correction (S4):** the branch is **REACHABLE for status 400**: `api.ts mutationError` attaches `.body` for 400/412, and the 400 `malformed_if_match` body carries a path-free `{message}` (the 412 body has no `message`); there is no `case 400` in the switch, so removing the branch would silently downgrade a real 400 message. | Minor | cleanup | **FIXED / KEPT at S4 (this pass)** — branch retained (proven reachable), 2 pins added (safe-400-message renders; a path/Traceback/workspace 400 message is rejected → per-status fallback) + an explaining comment. The original "unreachable/dead" characterization was imprecise. |
| FE-3 / A2 | frontend | `types.ts:530` | Per-item `stale` field never read (panel derives staleness itself). Faithful wire mirror. | Minor / arguably not-a-defect | cleanup | **FIXED / KEPT at S4 (this pass)** — kept as a deliberate wire mirror; added interface + field comments documenting that staleness is component-derived and the field must not be trimmed piecemeal. No behavior change. |
| F3 | tests | `apps/api/tests/` | No dedicated UTF-8 BOM test (behavior correct via `utf-8-sig`). | Minor | test | **FIXED (S5)** — 4 pinning tests in `test_csv_ingress_matrix.py`: `decode_body` strips the leading BOM; a BOM-prefixed preview recognizes all 5 headers with a clean first header (no BOM contamination); the path stays read-only (no rev bump); invalid non-UTF-8 bytes are still rejected (`invalid_encoding`/400). Parser unchanged. |
| BK-1 | backend | `routes.py:931-932` | `post_validate` defensive `except` interpolates `{exc}` into the body (only if `export_draft` raises; `pragma: no cover`; untriggerable on synthetic data). | Minor | security(low)/cleanup | **FIXED (S5)** — returns a fixed path-free `"Validation could not be completed."` (same `{ok,errors,schema,dry_run}` shape, HTTP 200); real detail logged server-side via `_log.exception`. Test forces the branch (monkeypatch `export_draft` to raise) and asserts no exc/path/Traceback/mount leaks to the client + `caplog` captured the detail server-side. `pragma: no cover` removed (now executed). |
| BK-3 | backend | `routes.py:795-814` | ~~`_read_bounded_body` checks total *after* append → peak = cap + one chunk.~~ **Audit correction (S5):** the premise was WRONG — the code does `total += len(chunk)` then raises `if total > max_bytes` **BEFORE** `chunks.append(chunk)`, so the crossing chunk is never retained and the buffer is bounded at ≤ `MAX_BODY_BYTES` (256 KB). | Minor | cleanup | **ACCEPTED — no code change (S5).** The only overshoot is the single transient stream chunk the ASGI server already read (inherent to any streaming reader; cannot be rejected before it is yielded). The proposed "check before append" fix is semantically identical (same rejection, same retained peak) → pure churn with streaming-path regression risk. Pinned by 2 tests (under-cap returns all bytes; over-cap raises `request_too_large`/413 at the crossing chunk, `consumed==[0,1,2]`, never draining the full body). |
| TC-2 | tests | `assistant.test.tsx:166-177`, `assistant-conversation.test.tsx:188-219` | Same click→sync-getByText shape but bare `render` (no router/fetch race) → lower flake likelihood. | Minor | test | Optional defensive `findByText`. |
| TC-5 | docs | `README.md:21` | "Works today" omits Phases 25–31. | Minor | documentation | **FIXED** (S3, this pass) — added a "Works today" bullet summarizing Phases 25–31 (grounded assistant, search/triage, ETag editing, export artifacts, reconciliation-only CSV). |
| TC-6 | docs | `README.md:27` | "five Claude authoring skills" — actual 8. | Minor | documentation | **FIXED** (S3, this pass) — corrected to "eight `isaac-*` Claude skills (five authoring/query + checkpoint/profile/resume)", explicitly reconciling the total with the 5-authoring-skill references at README:84/:120/commands table (independent review caught the original "eight"-vs-"five" contradiction; the split wording resolves it). |
| TC-7 | docs | `docs/architecture.md` | Scopes to the CLI/truth pipeline only; no web/api/memory/ingestion (no false claim, coverage gap). | Minor | documentation | **FIXED** (S3, this pass) — added a scope note pointing to README.md and docs/project-memory-map.md for the web/api/memory/ingestion surfaces; architecture content unchanged. |
| TR-1 | truth (doc) | `complete.py:51-179` | Confirmed-write surface is **7** pre-existing keys (`asset-uri, series, descriptor, descriptor_label, edge, qc, timestamp`) — the "5-key" shorthand is imprecise; `qc`/`timestamp` predate Phase 31 (`git log` confirms). No truth risk (reconciliation is read-only). | Documentation-only | documentation | Corrected where cited (S3, this pass): README's skill count and phase-coverage bullet now match this row; the 7-key precision here in the register already stands as the authoritative shorthand correction — confirmed, no change needed to this row's text. |
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

1. **S1 — CI stability** (Important): TC-1 (+ TC-2 defensively) → `await findByText`. No product behavior change; de-risks every downstream closure gate. **DONE at `a93ea0a`.**
2. **S2 — accessibility** (Minor→user-facing): FE-2 `tabIndex={-1}` + test. **DONE at `bf85578`.**
3. **S3 — documentation truth** (Important+Minor): TC-4/TC-5/TC-6/TC-7 + TR-1/BK-2 notes; README/architecture reconciliation. **DONE this pass** (TC-4/TC-5/TC-6/TC-7 fixed; TR-1 shorthand confirmed as already correctly documented in this register; BK-2 left as-is for a later slice, per scope).
4. **S4 — frontend cleanup**: FE-4/F1 (type + count decision), FE-1 (dead branch), FE-3 (mirror policy), FE-6 (zero-evidence panel — intent decision). **DONE** — FE-4 FIXED (ApiCsvWarning type + honest count render); FE-1 KEPT (proven reachable for 400, pinned; audit "dead" claim corrected); FE-3 KEPT (wire-mirror, documented); FE-6 ACCEPTED/working-as-intended (honest empty state + documented intentional panel exclusion). Frontend suite 545 → 550.
5. **S5 — backend cleanup/tests**: BK-1 (fixed error message), F3 (BOM test), BK-3 (optional per-chunk cap). **DONE** — BK-1 FIXED (fixed path-free message + server-side log, test-first); F3 FIXED (4 BOM pinning tests); BK-3 ACCEPTED (audit premise corrected — buffer already bounded at ≤cap; 2 pinning tests). Backend `apps/api/tests` 755 → 762.
6. **S6 — data-governance/doc pass**, then Project-Memory refresh, full hosted E2E QA, final independent review, release closure.

Dependencies: S1 is independent and first (unblocks stable CI for all others). S3 depends on final counts (stable after S1/S2). Truth/authority need no fixes (clean).

## E. Not yet audited / deferred to later Phase 32 slices

Full hosted E2E synthetic journey (search · runtime triage · assistant read/explain · export artifacts ·
offline/degraded on canonical data) beyond the CSV surface already QA'd; static Project Memory refresh
(after code+docs stabilize); narrow-viewport responsive **human** check (automation renders at fixed
~1483px — see §C). Each implementation slice: test-first, affected full suite, snapshot/R4.3, independent
Opus review, hosted QA when user-visible, ≤5 subagents, subagents never commit.

---

## Phase 32 Closure (CLOSED 2026-07-23 @ `058fccc`)

**Verdict: SHIP.** Final independent Opus review (fresh reviewer, did not implement any slice) over the
cumulative range `266340e..058fccc`: **0 Critical, 0 Important**; every register disposition verified
against the actual code; both audit corrections (FE-1 reachable-for-400, BK-3 buffer-already-bounded)
independently confirmed accurate.

### Slice commits (each: test-first → focused + full suite → tsc/build → snapshot regen if manifest-listed → independent Opus review → commit → push → exact-HEAD CI green)
- **S1** `a93ea0a` — TC-1 CI-stability (5 `await findByText` fixes; sibling B1 `e45db20`).
- **S2** `bf85578` — FE-2 a11y (`tabIndex={-1}` on the hidden CSV input + 3 tests).
- **S3** `225bcb4` — documentation truth (TC-4/5/6/7, TR-1) + register/ledger reconciliation.
- **S4** `3ccfd10` — FE-4 warning contract + honest render; FE-1 kept (reachable-for-400, corrected); FE-3 wire-mirror documented; FE-6 accepted.
- **S5** `058fccc` — BK-1 fixed error message + server log; F3 BOM tests; BK-3 accepted (premise corrected).
- **S6** (this closure) — README counts 894/550, register closure, ledger, known limitations; final review + verification.

### Final disposition of every finding
| Finding | Final status |
|---|---|
| TC-1 (Important, CI flake) | **FIXED** `a93ea0a` |
| TC-4 (Important, README counts) | **FIXED** `3ccfd10` doc-truth → finalized **894/550** in S6 |
| FE-2 / A3 (a11y) | **FIXED** `bf85578` |
| FE-4 / F1 (warning type + count) | **FIXED** `3ccfd10` |
| FE-1 / A1 (trusted-body branch) | **FIXED / KEPT** `3ccfd10` — proven reachable for 400; audit "dead" label corrected |
| FE-3 / A2 (per-item `stale`) | **KEPT** `3ccfd10` — documented wire mirror |
| FE-6 (zero-evidence panel) | **ACCEPTED / working-as-intended** — honest empty state; documented intentional panel exclusion |
| BK-1 (defensive `{exc}` echo) | **FIXED** `058fccc` — fixed message + server-side log |
| BK-3 (bounded-body peak) | **ACCEPTED** `058fccc` — buffer already bounded ≤cap; audit premise corrected |
| F3 (BOM test) | **FIXED** `058fccc` — 4 pinning tests |
| F2 (media-type gate) | **NOT A DEFECT** — structural boundary (decode/header/256KB) authoritative; 415 adds no security |
| FE-5 / F4 (prop staleness) | **NOT A DEFECT** — works via the poller; test-codified |
| TR-1 (5-vs-7 write-surface shorthand) | **DOCUMENTED** — corrected where cited; reconciliation is read-only |
| TR-2 (CSV write) | **NOT A DEFECT** — pure read; no `apply_answers`/`save_versioned` in the CSV path |
| TC-2 (assistant defensive `findByText`) | **DEFERRED** — bare `render`, no router/fetch race; not observed flaking; optional hardening |
| TC-3 / TC-5 / TC-6 / TC-7 | **FIXED** (S3) |
| BK-2 (auth-off if key unset) | **DOCUMENTED / hosted-verified** — production returns 401 on protected routes (key IS set on Railway); confirmed by S6 hosted probe |
| B2 (1 skip marker) | **ACCEPTED** — a `@pytest.mark.skipif(not _REAL_GRAPH.exists())` env-gate on an optional real-graph fixture (`test_memory.py:856`), not a disabled test. No `.only`, no unconditional `.skip`, no vitest skips. |
| C1 (two-window live-sync) | **HUMAN-ONLY** — CDP hidden-tab throttling; unit-covered; not claimed hosted-observed |
| C2 (exported-artifact stale) | **HUMAN-ONLY / documentation** — not UI-reachable (read-only exports) |
| C3 (degraded/insufficient states) | **DOCUMENTATION** — unit-verified; not in canonical seed |
| C4 (`absent_from_record` hosted) | **HUMAN-ONLY** — unreachable on the canonical seed (all FIELD_MAP paths populated); unit-covered |

**Zero unresolved Critical. Zero unresolved Important.** Residual items are Minor-deferred (TC-2),
accepted-with-rationale (FE-6, BK-3, F2, FE-5, TR-2, B2, BK-2), or honestly-scoped human-only (C1/C2/C4)
and narrow-viewport responsive.

### Final verification (clean tree @ `058fccc`)
Backend **894 passed** · frontend **550 passed** · tsc 0 · Vite build clean · snapshot `--check` no-drift ·
committed-snapshot gate 17/17 · synthetic demo byte-identical · `isaac validate --official` PASS v1.05 ·
evidence audit PASS 33/33 · secret/path/raw-content/`.only`/`.skip`/TODO scans clean · no raw-CSV
persistence · `examples/` unstaged.

### Hosted verification (read-only, observation-only — no auth capture/replay, no mutation)
- Railway `/api/health` → `{status: ok, mode: "synthetic-only", commit: "058fccc…"}` — serving the exact
  final runtime commit in synthetic-only mode.
- Protected routes (`/api`, `/api/experiments`, `/api/runtime`) → **401** (auth boundary active in prod).
- Vercel frontend → **200**; the canonical baseline renders exactly: **2/1/1/1** (Needs Attention 2,
  In Review 1, Ready to Export 1, Done 1 · exported `01SYNTHXANESSEED0000000005`), "Synthetic" mode chip,
  "1 ready to export"; console clean (no errors/exceptions).
- **Human-only (NOT claimed hosted-observed):** the full interactive mutation journey (edit/stale/
  conflict/export/CSV upload matrix), two-visible-window passive-poll live-sync (C1), `absent_from_record`
  (C4), and narrow-viewport reflow. These are covered deterministically by the 894 backend + 550 frontend
  tests (CSV reconciliation matrix, ETag/concurrency, assistant, export, search, degradation); CDP
  hidden-tab throttling + the observation-only credential rule + the canonical seed prevent visual
  automation proof. A human two-window session against the deployed demo remains the recommended check.

### Deployment sync (four axes, independently confirmed)
Local↔GitHub `0/0` clean · GitHub↔CI green · GitHub↔Vercel 200 · GitHub↔Railway serving `058fccc`
synthetic-only. Service identities unchanged (existing Krish-owned GitHub/Railway/Vercel).

Phase 32 is complete. No new phase started; the next phase requires explicit user approval.
