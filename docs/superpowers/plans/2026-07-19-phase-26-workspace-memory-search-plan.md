# Phase 26 — Real Workspace + Project Memory Search

```
Status: PROPOSED — awaiting approval. No implementation authorized.
Date: 2026-07-19  ·  Baseline commit: f534a4c  ·  Author: Claude (planning)
Related: 2026-07-16-phases-23-26-arc-decisions.md (arc item 9 governs); P24 specs
         (2026-07-16-phase-24-project-memory-design.md,
          2026-07-19-phase-24-10-memory-freshness-semantics.md); this doc EXTENDS the approved arc.
Approval decisions required:
  D1. Single grouped GET /api/search route (recommended) vs. two routes.
  D2. Affordance: ⌘K command palette + a visible TopBar search trigger (recommended) vs. ⌘K only.
  D3. Sequencing of the dedicated "no-fake-search" test-invariant rewrite (see §20 P26.6 —
      co-reviewed pair vs. green-per-commit retire-then-replace).
  D4. Confirm vector/semantic embeddings stay BACK-BURNER (not built this phase). See §7, §24.
  D5. Confirm search is scoped to the single shared workspace + single memory provider
      (no per-user scoping; multi-user scoping deferred — depends on greenfield identity). See §14.
  D6. Confirm NO new env vars and NO new dependencies. See §18.
```

This plan is the proposed content of the **P26.0 design mini-spec** that the arc requires to
stop for user review before any implementation. It plans **both** approved search systems (arc
decision #9): workspace/truth-plane search and Project Memory/memory-plane search. Time is not
tight; both are planned in full.

---

## 1. Purpose

Add **real, API-backed, deterministic** search across the two existing planes:

- **Workspace search** (truth plane) over real application state: experiments, record identifiers,
  draft field paths/values/units/status, pending/completed status, evidence entries, exported
  artifacts, and source references — everything the existing per-resource endpoints already expose.
- **Project Memory search** (memory plane) over real memory data via the `MemoryReader` Protocol:
  concepts, indexed/served project files, community labels, anchors/provenance, related
  files/concepts, and rationales.

Search is deterministic (no LLM, no embeddings), typed, scoped, permission-aware at the existing
auth seam, source/plane-labeled, explainable ("why this matched"), navigable, tested, and honest
when a provider is unavailable. It replaces the deliberately-absent, test-guarded "no search"
state with a genuine backend build — never decorative chrome.

## 2. User / scientist value

One place to find "where did I see Cu K-edge", "which experiments still block export", "which
record has ULID …", "which doc/concept mentions the governance allowlist" — without clicking
through every experiment. Cross-resource lookup exists nowhere today (audit-architecture §4:
"NO cross-experiment index or query endpoint"). Every hit is a real, navigable lead with its
source labeled — a scientist can jump straight to the Evidence, Completion, or Memory surface.

## 3. Mentor / demo value

Demonstrates the two-plane discipline under a new feature: one query returns **two visually and
structurally separate groups** (truth vs. memory), each honest about availability, neither
producing a verdict. ⌘K is a recognizable, credible affordance. It proves the `MemoryReader`
Protocol seam extends cleanly (a `search()` method), and proves the "must actually work"
governing principle (arc §Governing principle) — real API, real keyboard behavior, real tests.

## 4. Architectural value

- Extends the repo's cleanest seam: adds `search()` to the `MemoryReader` Protocol
  (`apps/api/isaac_api/memory.py:157-166`), implemented by both providers, so the hosted
  sanitized-snapshot provider gains search for free.
- Introduces the first **cross-resource aggregation** over the workspace store in a dedicated
  module, without coupling it to the truth core.
- Reuses the "prompt/query → structured lookup → typed, provenance-labeled, no-verdict results"
  grounding layer established by Phase 25 (per master roadmap §4, P25 is the source; P26 consumes
  it). There is no hard dependency either way (§5), but sequencing P26 after P25 avoids rework.

## 5. Dependencies

- P24 memory plane is DONE (Protocol + 2 providers + precedence + hosted snapshot). Confirmed by
  baseline (`memory.py` 1183 lines; `test_memory.py`).
- No dependency on P25 (grounded assistant). Search and assistant are independent
  (audit-architecture §5). P26 may proceed whether or not P25 has shipped.
- No dependency on identity/persistence work (greenfield, out of scope — §7).
- Requires the P26.0 review gate to pass before implementation (arc §Arc order).

## 6. Scope

IN scope:
1. Backend workspace-search core module + typed contract.
2. Backend memory-search via a new `MemoryReader.search()` Protocol method + both provider impls.
3. One HTTP route (`GET /api/search`) returning a grouped, plane-labeled envelope.
4. Frontend: typed API client method, a ⌘K command palette / search dialog, result rendering,
   navigation, full a11y, and all degraded states.
5. The dedicated, reviewed rewrite of the two P22-era "no fake search" regression tests.
6. Docs updates (back-burner registry, architecture note).

## 7. Non-goals (do NOT build)

- **Vector search / semantic embeddings** — BACK-BURNER only, listed in §24; explicitly not built
  (arc back-burner; baseline "MODEL RULE" / P26 constraint).
- LLM / freeform anything (arc decision #8).
- Full-text search over **source-file bytes** — memory search stays metadata/provenance-only,
  consistent with P24 (audit-frontend §5: Source Index "never file content").
- New auth model, per-user scoping, users/orgs/roles, durable/multi-user persistence — greenfield,
  deferred (audit-architecture §6.3, back-burner "multi-user auth").
- Real-data / upload ingestion (uploads stay 403), second domain, portal parity, MCP, dark theme.
- Indexing records into memory, related-records / record-similarity (arc back-burner).
- A persistent search index / background indexing job (§15 mitigation: none needed at demo scale).

## 8. Current baseline (cite files)

- **Search absent, by design, and test-guarded** (audit-backend §6; audit-frontend §3):
  - Backend: zero real `\bsearch\b` hits; no `/search` route among the 21 routes
    (`apps/api/isaac_api/routes.py`).
  - Frontend chrome states it outright: `components/TopBar.tsx:47-48` ("There is no search: this
    prototype doesn't have one, so the chrome doesn't pretend to"); `components/HelpPanel.tsx:15`.
  - Regression tests assert absence:
    - `apps/web/src/__tests__/help-and-honesty.test.tsx:33-39` — `[role="search"]`, `.topbar-search`,
      `/⌘K/`, `/Search records/i` all null (comment line 27: "decorative search + '⌘K' promise are
      gone (Decision 1)").
    - `apps/web/src/__tests__/memory-concepts.test.tsx:214-216` — `input[type="search"]` and
      `role="searchbox"` null ("still no search/filter input anywhere on the screen (Phase 26)").
- **Data is queryable per-resource, not cross-resource** (audit-architecture §4):
  - Workspace: `GET /api/experiments` → `_summary` `{id,title,status,created_utc,pending_count,
    evidenced_field_count,exported,record_id}` (`routes.py:59-70,206-208`); `/experiments/{id}/draft`,
    `/pending`, `/evidence`, `/artifacts`.
  - Memory: `MemoryReader` methods `overview/concepts/concept/files/file/classify_path/status`
    (`memory.py:157-166`); concept summaries `{id,label,community_id,community_name, anchor?}`
    (`memory.py:527-536`); files served-allowlist + rationales; related files/concepts already
    computed with governance/path-safety filters (`memory.py:640-677`).
- **Auth seam** = one app-wide shared-secret bearer middleware; `GET /api/health` + `OPTIONS` open;
  no per-route `Depends`, no user/session/org concept (`apps/api/isaac_api/auth.py`; audit-backend §5).
- **Honest degradation** convention: reason-coded (`graph_absent`/`graph_unreadable`/`unsupported`),
  shape-stable nulls, never-raise (`memory.py`; `routes.py` memory handlers; audit-backend §9).
- **Isolation tests** (must keep passing): `test_export.py:169`, `test_e2e.py:112` (truth core
  no-graphify); `test_memory.py:813` (memory imports ⊆ stdlib, disjoint from
  `{isaac_records,graphify,fastapi,isaac_api}`).
- **Frontend a11y precedent**: ARIA `dialog`+focus-trap modals with ESC + focus-return
  (`HelpPanel.tsx:30-75`, `ExportReadiness.tsx:149-185`); `FetchStates.tsx` LoadingPanel/BackendDown;
  `lib/api.ts` typed client + `lib/useFetch.ts` 3-state hook (audit-frontend §6-7).

## 9. Files likely touched

Backend:
- `apps/api/isaac_api/search.py` — NEW. Workspace-search core (pure functions over the workspace store).
- `apps/api/isaac_api/memory.py` — add `search()` to the `MemoryReader` Protocol + implement in
  `LocalGraphArtifactSource` and `SanitizedSnapshotSource`.
- `apps/api/isaac_api/routes.py` — add `GET /api/search`.
- `apps/api/isaac_api/serialize.py` — only if a shared result serializer helps (optional).
- `apps/api/tests/` — NEW `test_search.py` (workspace + route); extend `test_memory.py`
  (memory `search()` + isolation still holds); possibly `test_deploy_config.py` (auth on `/search`).

Frontend:
- `apps/web/src/lib/api.ts` — add `search(q, opts)` + result types.
- `apps/web/src/components/SearchDialog.tsx` — NEW command palette / dialog.
- `apps/web/src/components/AppShell.tsx` — mount the dialog + global ⌘K handler.
- `apps/web/src/components/TopBar.tsx` — visible search trigger (replaces the "no search" prose).
- `apps/web/src/components/HelpPanel.tsx` — update the "no search" honesty prose.
- `apps/web/src/lib/routes.ts` — deep-link helpers if new ones are needed (reuse existing where possible).
- CSS (`components/chrome.css` or a scoped file) — dialog styling; no new colored "verdict rail".
- `apps/web/src/__tests__/` — NEW `search-command.test.tsx`; REWRITE `help-and-honesty.test.tsx` +
  `memory-concepts.test.tsx` (dedicated slice, §20 P26.6); test fixtures in `test/apiFixtures.ts`.

Docs:
- `docs/project-memory-map.md` (back-burner registry), `docs/superpowers/specs/` (P26.0 mini-spec),
  a short architecture note.

## 10. Files that MUST NOT be touched

- Truth core: `src/isaac_records/*` (official.py, draft_validator.py, export.py, audit.py, cli.py,
  models.py, ids.py, complete.py, review.py, portal_warnings.py, extract/*), `schema/*`. Search
  computes NO verdicts and imports NO truth-core validation.
- Auth model (`auth.py`) beyond confirming `/search` is gated — no new auth, no user model.
- Uploads governance (`POST /api/uploads` stays 403); the source-preview allowlist (`sources.py`).
- `graphify-out/`, `examples/`, drafts/records with real data — never staged, never indexed.
- The memory plane's stdlib-only + Graphify-free + no-`isaac_records` invariant (adding `search()`
  must not introduce any non-stdlib import — `test_memory.py:813` must stay green).

## 11. Data flow

Workspace search (truth plane):
```
UI ⌘K query ─▶ GET /api/search?q=&scope= ─▶ routes.py
   └▶ search.workspace_search(query, ws.list_experiments(), loaders)
        • iterate experiment summaries + (lazy) draft/pending/evidence/artifact for each
        • normalize + token-match over already-exposed fields ONLY
        • rank, cap, paginate ─▶ typed workspace results (plane:"truth")
```
Memory search (memory plane):
```
   └▶ reader = memory.get_default_reader(); reader.search(query)
        • provider scans its already-parsed, governance-filtered projection
          (concept summaries, served files, rationales) — reuses _is_served / _is_unsafe /
          _served_source_file guards; never raises (returns available:false + reason on degrade)
        ─▶ typed memory results (plane:"memory", MEMORY_NOTE attached)
```
Route composes both into ONE grouped envelope; each group carries its own `available`/`reason`,
so one plane can be down while the other returns results. No merging into a single verdict
(mirrors the `getRecordBundle` "keep every value separate" discipline, audit-frontend §7).

## 12. API / contracts

**D1 (recommended): single route.**
```
GET /api/search?q=<str>&scope=<all|workspace|memory>&limit=<int, default 10>&offset=<int, default 0>
```
Response (200 always when the query is well-formed; degradation is in-body, never a 5xx):
```jsonc
{
  "query": "cu k-edge",
  "normalized_query": "cu k-edge",
  "scope": "all",
  "workspace": {
    "plane": "truth",
    "available": true,
    "total": 12, "returned": 10, "limit": 10, "offset": 0,
    "results": [
      {
        "kind": "experiment" | "record_id" | "draft_field" | "evidence" | "artifact" | "source_ref",
        "experiment_id": "…",
        "record_id": "…" | null,
        "title": "…",
        "label": "…",                         // human label for the hit
        "status": "needs_attention" | "in_review" | "ready_to_export" | "done" | null,
        "match": {
          "field": "draft.beamline.value",     // where the match occurred
          "snippet": "…cu k-edge…",             // surrounding text, match offsets returned separately
          "reason": "matched draft field value" // human "why this matched"
        },
        "navigate_to": "/record/<id>/evidence", // client deep-link
        "plane": "truth"
      }
    ]
  },
  "memory": {
    "plane": "memory",
    "note": "<MEMORY_NOTE — leads to verify, never a verdict>",
    "available": false,
    "reason": "graph_absent",                   // or graph_unreadable / unsupported / null
    "total": 0, "returned": 0, "limit": 10, "offset": 0,
    "results": [
      // when available:
      // { "kind":"concept"|"file"|"rationale", "id":…|null, "path":…|null, "label":…,
      //   "community_name":…|null,
      //   "match": {"field":"concept.label","snippet":"…","reason":"matched concept label"},
      //   "navigate_to":"/memory?concept=<id>"  |  "/memory?file=<path>", "plane":"memory" }
    ]
  }
}
```
Contract invariants:
- **No verdict keys anywhere** — never emit `ok/valid/passed/verdict/schema/errors`; never emit
  PASS/FAIL text (mirrors the memory plane's contract, audit-architecture §1).
- `scope=workspace` omits the memory group's results (group present, `available` still reported);
  `scope=memory` omits workspace results. Default `all`.
- **Query guards**: `q` normalized (Unicode NFC, lowercased, whitespace-collapsed). Min length 2
  after normalization → each group returns `total:0` + `reason:"query_too_short"`. Max length cap
  (e.g. 256 chars) → truncate + still deterministic. Empty `q` → `query_too_short`.
- Match offsets returned as structured data (`match.offsets: [[start,end]]`) so the client
  renders `<mark>` safely without server-side HTML (no injection).

Error taxonomy (in-body, never 5xx): `query_too_short`; per-group `graph_absent` /
`graph_unreadable` / `unsupported` (memory only). Auth failure = 401 from the middleware (before
the route runs).

## 13. UI behavior

- **Affordance (D2, recommended)**: global **⌘K / Ctrl-K** opens a command-palette dialog; a
  visible TopBar trigger button ("Search  ⌘K") gives a discoverable, non-keyboard path. `/` is NOT
  bound (avoids typing conflicts). ESC closes and returns focus to the trigger.
- **Dialog**: `role="dialog" aria-modal="true"`, labeled, focus-trapped with Tab-wrap, ESC-to-close
  + focus-return — reuse the existing `HelpPanel`/`ExportReadiness` modal pattern
  (`HelpPanel.tsx:30-75`; audit-frontend §accessibility). Backdrop click closes. The search input is
  `role="searchbox"` / `type="search"`, `aria-label="Search experiments and project memory"`,
  autofocused on open.
- **Query behavior**: debounced fetch (≈200 ms) via a `useFetch`-style call keyed on the normalized
  query; results re-render on each settled response. `aria-live="polite"` result-count region.
- **Grouping**: two clearly separated sections — **"Workspace" (truth)** and **"Project Memory"
  (memory)** — never interleaved, each with its own header + plane label + a memory-plane
  "leads, not a verdict" caption (reuse MEMORY_NOTE styling; no red for a degraded memory group,
  matching `memory-concepts` honesty).
- **Result row**: kind badge + title/label + "why this matched" line (`match.reason` + `<mark>`ed
  snippet) + a source/plane label. Rows are native `<button>`/`<a>` (native keyboard activation,
  no custom onKeyDown — matches the `ProjectMemory.tsx:403,654` precedent). Enter/click navigates
  via `navigate_to` and closes the dialog.
- **Keyboard nav**: Up/Down move a roving `aria-activedescendant`/focus through results across both
  groups; Enter activates the focused row.
- **States**:
  - *Loading*: `LoadingPanel` (`role="status" aria-live="polite"`).
  - *Empty (valid query, zero hits)*: honest "No matches in workspace or project memory" — never a
    fabricated row (mirrors `FetchStates` "never placeholder data").
  - *Query too short*: quiet hint "Type at least 2 characters", no rows.
  - *Backend down*: `BackendDown` (`role="alert"`) with the RUN_COMMAND, same as every live screen.
  - *Memory provider unavailable but workspace OK*: workspace results render normally; the memory
    section shows a compact honest "Project memory search is unavailable (<reason>)" note, NOT an
    error/red block — degraded advisory plane ≠ broken truth plane (audit-frontend §6).
- **No-verdict language**: the dialog never renders PASS/FAIL/valid/invalid; reuse the
  `hasVerdictLanguage` guard pattern (`lib/assistant.ts:30-32`) as a defensive filter on any
  snippet text.

## 14. Security / governance constraints

- **Permission-aware at the EXISTING auth seam**: `/api/search` sits behind `ApiKeyAuthMiddleware`
  automatically (app-wide, `auth.py`); no per-route auth code. When the key is set, the client
  sends `Authorization: Bearer` exactly as for every other endpoint (`lib/api.ts`). Because there
  is **no user/session/org concept** (audit-backend §5), search is explicitly scoped to the single
  shared deployment workspace + the single resolved memory provider. The plan and UI must NOT imply
  per-user results. Multi-user/per-owner scoping is deferred (§24, back-burner "multi-user auth") —
  it depends on greenfield identity + persistence.
- **No new data exposure**: workspace search only reads fields the existing endpoints already
  return; memory search reuses the reader's existing governance filters (`_is_served`,
  `_is_unsafe`, `_served_source_file`) so it can never surface `examples/**`, secrets, absolute /
  traversal paths, or governance-excluded anchors. Source-file **bytes** are never searched
  (metadata/provenance only). Uploads stay 403.
- **Plane labeling**: every result carries `plane` ("truth" | "memory"); memory results carry
  MEMORY_NOTE. Memory search is presented as leads, never validation authority (arc decisions #5, #9).
- **Isolation preserved**: `search()` on the providers uses stdlib only; `test_memory.py:813` must
  still pass. The route imports no truth-core validator.

## 15. Risks

1. **Breaks the memory stdlib-only isolation test** if `search()` pulls a non-stdlib import.
   *Mitigate*: pure stdlib (`re`, `unicodedata`); run `test_memory.py:813` in the same slice.
2. **Governance leakage via snippets** (a match surfaces an excluded path/value).
   *Mitigate*: only match/snippet over already-served fields; reuse existing filters; add a test
   that an `examples/**` / secret path never appears in results even if it "matches".
3. **Verdict language leaking into snippets** from record/audit content.
   *Mitigate*: defensive `hasVerdictLanguage` filter + a no-verdict-keys test on the route.
4. **The dedicated test-invariant rewrite sequencing** (transient red between UI + test slices).
   *Mitigate*: §20 P26.6 + open question D3.
5. **Performance** if the workspace grows large (O(N) scan + per-experiment loads).
   *Mitigate*: demo scale is tiny (auto-seeds ONE experiment); hard result caps; lazy per-experiment
   loads short-circuit on the summary; document a future index as back-burner (§24). No index built.
6. **⌘K conflicts** with browser/OS shortcuts. *Mitigate*: standard command-palette pattern
   (`preventDefault` only when our dialog handles it), visible trigger fallback, ESC to close.
7. **Ephemeral shared hosted workspace** means search reflects only the shared demo state
   (audit-backend §hosted). *Mitigate*: documented; not a code risk.

## 16. Tests

Backend (`apps/api/tests/test_search.py`, extend `test_memory.py`):
- Workspace core: case-insensitive substring; multi-token AND; min-length + too-short reason;
  ranking order deterministic; per-group cap; limit/offset pagination + `total`; matches across
  each `kind` (experiment title, record_id, draft field value, evidence source/quote, artifact);
  snippet + `match.reason` present; governance path never surfaced; no-verdict-keys / no PASS-FAIL.
- Memory `search()`: matches concept label/id, served file path, rationale text; honest degradation
  returns `available:false` + `graph_absent`/`graph_unreadable`/`unsupported`, never raises;
  excluded/unsafe paths never surface; **isolation test still green** (`test_memory.py:813`).
- Route: 200 grouped envelope; `scope` filtering; per-group independence (memory down, workspace
  up); plane labels + MEMORY_NOTE present; auth-gated when `ISAAC_UI_API_KEY` set (extend
  `test_deploy_config.py` / mirror `test_memory_api.py:606-614`).

Frontend (`search-command.test.tsx`; fixtures in `test/apiFixtures.ts`):
- ⌘K opens the dialog; TopBar trigger opens it; ESC closes + returns focus; focus trap + Tab-wrap;
  backdrop close.
- Debounced query drives `api.search`; grouped rendering with distinct Workspace/Memory sections +
  plane labels; "why matched" snippet with `<mark>`; result navigation deep-links + closes dialog;
  keyboard Up/Down/Enter across results.
- States: loading, empty-valid-query, query-too-short, backend-down (RUN_COMMAND),
  memory-unavailable-but-workspace-ok (no red), no-verdict language.
- Dedicated rewrite (§20 P26.6): the two legacy files assert real search PRESENT and functional,
  and that decorative/fake search stays forbidden.

## 17. Verification

- Backend: `.venv/bin/pytest` (all green, including the two isolation tests + new `test_search.py`);
  `.venv/bin/isaac validate … --official` unchanged (truth path untouched).
- Frontend: `npm test` (vitest, all green incl. the rewritten files) + `npm run build` in `apps/web`.
- Manual smoke via the `/run` skill: launch API + web, press ⌘K, run a query that hits both planes,
  a query that hits only workspace, and a query with the memory provider unavailable; confirm
  navigation + honest states. Report commands + results (per CLAUDE.md §6, §14).

## 18. Deployment impact

- **No new env vars, no new dependencies** (D6). Search is in-process over the existing filesystem
  workspace + the resolved `MemoryReader`.
- Works unchanged on Railway (backend) + Vercel (frontend). The hosted sanitized-snapshot provider
  gains search automatically via the Protocol method — no Docker/snapshot pipeline change required
  **unless** the snapshot projection must precompute a searchable field. Plan assumption: `search()`
  scans the already-served projection, so `scripts/build_memory_snapshot.py` is UNTOUCHED; confirm
  during P26.2 and note if wrong.
- CI unchanged (2 jobs); no deploy step added.

## 19. Documentation impact

- Update `docs/project-memory-map.md` "Roadmap / back-burner" table: move "real search" from
  deferred to shipped; keep "vector/semantic search" explicitly on back-burner.
- Persist the P26.0 mini-spec into `docs/superpowers/specs/` (arc decision #11).
- Short architecture note: the `/search` route, the grouped envelope, the `MemoryReader.search()`
  extension, and the retired "no-fake-search" invariant with its replacement.
- Do NOT touch the known-stale docs owned by the Documentation plan (baseline §"Stale docs").

## 20. Bite-sized slices

Each slice is one subagent, independently reviewable/committable, with an explicit stop gate.
Backend precedes frontend so the client wires to a real route. The dedicated test-invariant rewrite
is isolated per arc decision #10.

### P26.0 — Design mini-spec review gate (this document)
- **Objective**: user reviews/approves this plan (D1–D6) before any code.
- **Files touched**: this doc only. **Forbidden**: all code/tests/schema.
- **Model**: Fable (orchestrator). **Acceptance**: user approval recorded. **Tests**: none.
- **Report**: decisions resolved. **Commit**: docs commit if edited. **Stop**: HARD gate — no
  implementation until approved.

### P26.1 — Workspace search core (no route)
- **Objective**: `apps/api/isaac_api/search.py` — pure `workspace_search(query, experiments, loaders,
  limit, offset)` returning typed workspace results; normalization, token-AND matching, ranking,
  caps, pagination, snippet + reason. TDD.
- **Files touched**: `search.py` (new), `apps/api/tests/test_search.py` (new).
  **Forbidden**: `src/isaac_records/*`, `schema/*`, `routes.py`, `memory.py`, frontend.
- **Model**: Opus 4.8 (search architecture/governance). **Acceptance**: all matching/ranking/caps/
  pagination/governance/no-verdict tests green; no truth-core import. **Tests**: as §16 workspace.
- **Report**: contract + ranking rules + what fields are searched. **Commit**: single. **Stop**: review before P26.2.

### P26.2 — MemoryReader.search() (no route)
- **Objective**: add `search(query, limit, offset)` to the `MemoryReader` Protocol and implement in
  `LocalGraphArtifactSource` + `SanitizedSnapshotSource`; reuse existing governance/path-safety
  filters; honest degradation; stdlib-only. Confirm the snapshot generator needs no change (§18). TDD.
- **Files touched**: `memory.py`, extend `apps/api/tests/test_memory.py`.
  **Forbidden**: truth core, `routes.py`, frontend, `scripts/build_memory_snapshot.py` (touch only
  if P26.1 assumption is wrong — report it).
- **Model**: Opus 4.8. **Acceptance**: memory-search tests + degradation tests green; isolation
  test `test_memory.py:813` still green. **Tests**: §16 memory. **Report**: whether the generator
  was touched and why. **Commit**: single. **Stop**: review before P26.3.

### P26.3 — GET /api/search route
- **Objective**: wire both cores into one grouped, plane-labeled, no-verdict envelope; `scope`,
  caps, pagination; auth inherited; per-group independence; never 5xx on a degraded provider.
- **Files touched**: `routes.py`, optionally `serialize.py`, extend `test_search.py` /
  `test_deploy_config.py`. **Forbidden**: truth core, `auth.py` logic, frontend.
- **Model**: Opus 4.8. **Acceptance**: route tests + auth-gated test green; full backend `pytest`
  green. **Tests**: §16 route. **Report**: envelope example + auth confirmation. **Commit**: single.
  **Stop**: review before frontend.

### P26.4 — Frontend API client + types (no visible UI)
- **Objective**: `api.search(q, {scope, limit, offset})` + result types in `lib/api.ts`; fixtures in
  `test/apiFixtures.ts`. No chrome change yet — legacy "no search" tests still pass.
- **Files touched**: `lib/api.ts`, `test/apiFixtures.ts`, `api.test.ts`.
  **Forbidden**: `TopBar.tsx`, `AppShell.tsx`, the two legacy test files, backend.
- **Model**: Sonnet 5 (mechanical client wiring). **Acceptance**: client tests green; `npm test`
  green (legacy tests untouched + passing). **Tests**: request encoding + auth header + envelope
  parse. **Report**: method signature + types. **Commit**: single. **Stop**: review before P26.5.

### P26.5 — SearchDialog + ⌘K + TopBar trigger (feature)
- **Objective**: build the command palette (`SearchDialog.tsx`), global ⌘K in `AppShell.tsx`, a
  visible trigger in `TopBar.tsx`, grouped/plane-labeled result rendering, navigation, full a11y,
  all states (§13). New functional tests in `search-command.test.tsx`.
- **Files touched**: `SearchDialog.tsx` (new), `AppShell.tsx`, `TopBar.tsx`, CSS, `routes.ts`
  (if needed), `search-command.test.tsx` (new). **Forbidden**: backend; the two legacy test files
  (rewritten in P26.6, not here — keep the rewrite unburied).
- **Model**: Opus 4.8 (UX/a11y/honesty). **Acceptance**: `search-command.test.tsx` green + manual
  ⌘K smoke passes. NOTE: this commit makes the two legacy "no search" tests RED (search now exists);
  that is expected and resolved in P26.6 — see D3 for how to keep CI green (co-reviewed pair vs.
  green-per-commit retire-then-replace). **Tests**: §16 frontend (functional). **Report**: the red
  legacy tests + the D3 approach chosen. **Commit**: single (feature only). **Stop**: review before P26.6.

### P26.6 — DEDICATED "no-fake-search" invariant rewrite (reviewed slice)
- **Objective (arc decision #10)**: rewrite ONLY the two legacy test files with rationale comments:
  (a) explain why the invariant changes — P26 shipped real, API-backed, keyboard-driven, tested
  search, so "search must not exist" is obsolete; (b) remove ONLY the obsolete absence assertions
  (`help-and-honesty.test.tsx:33-39`; `memory-concepts.test.tsx:214-216`); (c) replace them with
  functional-behavior assertions (⌘K opens a real dialog, real results render with plane labels and
  navigation); (d) PRESERVE the principle — add/keep assertions that decorative/fake/authority-
  implying search stays forbidden (no fabricated rows; no verdict language; memory group labeled as
  leads). Also update the "no search" honesty prose in `TopBar.tsx:47-48` / `HelpPanel.tsx:15`.
- **Files touched**: `help-and-honesty.test.tsx`, `memory-concepts.test.tsx`, `TopBar.tsx`,
  `HelpPanel.tsx` (prose only). **Forbidden**: backend; `SearchDialog.tsx` logic; unrelated tests.
- **Model**: Opus 4.8 (honesty-sensitive). **Acceptance**: both files green; full `npm test` green;
  reviewer confirms the diff is a clean, commented invariant change, not buried in feature code.
- **Tests**: the rewritten assertions. **Report**: before/after of each removed assertion + its
  replacement + the preserved fake-search-forbidden assertions. **Commit**: single, dedicated,
  clearly labeled. **Stop**: review before P26.7.

### P26.7 — Docs
- **Objective**: update back-burner registry, persist the mini-spec, add the architecture note (§19).
- **Files touched**: `docs/project-memory-map.md`, `docs/superpowers/specs/…`, architecture note.
  **Forbidden**: code/tests; the known-stale docs owned by the Documentation plan.
- **Model**: Sonnet 5. **Acceptance**: docs accurate, no stale claims introduced. **Tests**: none.
  **Report**: files changed. **Commit**: single. **Stop**: phase complete → user gate.

## 21. Model / subagent assignment

- Fable 5: orchestrator/planner/reviewer/verifier; the P26.0 gate; reviews every slice diff.
- Opus 4.8: P26.1, P26.2, P26.3 (search architecture, governance, honest degradation), P26.5, P26.6
  (UX/a11y/honesty-sensitive).
- Sonnet 5: P26.4 (mechanical client wiring), P26.7 (docs).
- Every slice independently assignable/reviewable/verifiable/committable with a stop gate (arc MODEL RULE).

## 22. Acceptance criteria (phase)

- One `GET /api/search` route returns a grouped, plane-labeled, no-verdict envelope; both planes
  searchable; per-group availability independent; auth-gated at the existing seam.
- `MemoryReader.search()` implemented on both providers; memory isolation + truth-core no-graphify
  tests still green.
- ⌘K + visible trigger open a real, accessible, focus-trapped dialog with grouped results,
  "why matched", navigation, and every honest state; debounced live queries.
- Search surfaces NO governance-excluded content and NO verdict; snippets are safe.
- Backend `pytest` + frontend `npm test` + `npm run build` all green; manual ⌘K smoke passes.
- The two legacy "no fake search" tests are rewritten in a dedicated, commented, reviewed slice that
  keeps "fake/decorative search forbidden" enforced.
- No new env vars, no new deps, no truth-core edits, deploy unaffected.

## 23. Stop / approval gates

- **HARD gate at P26.0**: no implementation until this plan (D1–D6) is approved.
- Per-slice stop gate after each of P26.1–P26.7 (review diff before the next slice).
- P26.5 → P26.6 is an ordered pair (D3): resolve the CI-green sequencing at approval.
- Do not begin any adjacent phase (e.g. institutional persistence/identity) — out of scope.

## 24. Deferred items (back-burner)

- **Vector search / semantic embeddings / fuzzy ranking** — future option only; NOT built (D4).
- Persistent / background-built search index (only needed if the workspace grows large; O(N) scan
  suffices at demo scale).
- Per-user / per-owner search scoping, cross-tenant filtering — depends on greenfield identity +
  durable persistence (audit-architecture §6.3); back-burner "multi-user auth".
- Searching source-file **bytes**, related-records / record-similarity, indexing records into memory
  (arc back-burner — memory stays metadata/provenance-only).
- Full graph explorer / raw network visualization (arc decision #6, back-burner).
- Update `docs/project-memory-map.md` back-burner table accordingly (do not silently drop items).

## 25. Explicit questions for the user

1. **D1** — Single grouped `GET /api/search` route (recommended, matches "group workspace vs memory"
   + "honest when one provider is down"), or two separate routes?
2. **D2** — Affordance: ⌘K **plus** a visible TopBar "Search ⌘K" trigger (recommended for
   discoverability), or ⌘K only? Any objection to leaving `/` unbound?
3. **D3** — Sequencing for the dedicated invariant rewrite (P26.5 feature → P26.6 rewrite): prefer
   (a) co-reviewed pair merged together with a documented transient red between commits, or
   (b) strict green-per-commit "retire absence assertions first, then add UI + functional
   assertions" (splits removal and replacement across two commits)? Arc decision #10 wants remove +
   replace in one dedicated slice, which favors (a).
4. **D4** — Confirm vector/semantic search stays BACK-BURNER (not built this phase)?
5. **D5** — Confirm search is scoped to the single shared workspace + single memory provider (no
   per-user scoping; UI must not imply otherwise) until identity/persistence exist?
6. **D6** — Confirm NO new env vars and NO new dependencies for this phase?
7. Result caps/pagination defaults: per-group hard cap and default page size (proposed: cap 50,
   page 10) — acceptable, or different?
8. Minimum query length (proposed: 2 chars) — acceptable?
```
