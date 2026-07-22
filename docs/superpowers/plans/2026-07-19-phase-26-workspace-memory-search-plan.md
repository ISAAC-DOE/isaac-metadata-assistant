# Phase 26 — Real Workspace + Project Memory Search

```
Status: ACTIVE — Phase 25 COMPLETE (fresh-session Chrome resilience PASSED, gate closed at 19a2300);
Phase 26 activated under the 2026-07-20 master authorization. P26.0 gate resolved 2026-07-21: D1–D6
unchanged; the four decision-lock §12 open items closed — result cap 50 / page 10, min query length 2,
D2 = 5-scenario seed (all 4 states), D3 = strict green-per-commit (no transient-red push). Baselines
reconciled to post-P25 HEAD (routes 21→22 w/ /api/search; MemoryReader = 7 methods, no search() yet;
backend/web tests 500/299 not 461/137; backend files byte-identical to f534a4c so §8–§11 citations hold).
P26.0a RELEASED (deterministic 5-scenario seed + idempotent demo; 18 behavior tests + full suite green,
independent Opus adversarial review APPROVE). P26.0b RELEASED 2026-07-21 (guarded synthetic-demo reset —
`POST /api/demo/reset` + Reset Demo control; commit `68fd910`, CI green run `29872521920`, deployed;
hosted QA GREEN — preview 13→ canonical 5 / legacy 8 / ambiguous 0, execute → exactly the five
(needs_attention 2 / in_review 1 / ready_to_export 1 / done 1), Run Demo ×3 held at 5). CQ-1 (demo/run
unbounded accumulation) CLOSED by P26.0a (prevention) + P26.0b (cleanup), verified live.
P26.1 RELEASED 2026-07-21 (commit `173780f`, CI green run `29876044687`, deployed): pure deterministic
`search.workspace_search(query, experiments, *, limit, offset)` — NFC/casefold/whitespace normalization,
token-AND, four-tier ranking (exact>prefix>token>substring), cap 50 / page 10 / min-len 2, snippet +
offsets + reason, six truth-plane result kinds; NO route, NO verdict, NO truth-core import, NO filesystem
traversal, defensive path-leak sanitizer; 53 behavior tests, backend suite 589 green, snapshot no drift,
R4.3 preflight PASS; two independent Opus reviews (APPROVE-WITH-MINORS → the Important path-leak-
enforcement gap + minors fixed).
P26.2 RELEASED 2026-07-21 (commit `51e8b24`, CI green run `29877645942`, Railway+Vercel healthy at HEAD):
`MemoryReader.search(query, limit, offset)` on the Protocol + BOTH providers via one shared pure helper —
NFC/casefold/whitespace normalization, token-AND four-tier ranking, cap 50 / page 10 / min-len 2, three
result kinds (concept / file / rationale), each `plane:"memory"`, `source:"memory:<provider_kind>"`,
`navigate_to /memory?concept=|?file=`; governance inherited by delegating ONLY to the public read surface
(no excluded/secret/unsafe path can surface), honest degradation never raises, stdlib-only (isolation
holds). 21 frozen local tests + snapshot search + non-vacuous local↔snapshot parity; backend suite 628
green; snapshot regenerated in-slice (§17 predictable drift, generator unchanged); independent Opus review
APPROVE.
P26.3 RELEASED 2026-07-21 (commit `f9d6b0a`, CI green run `29878778089`, Railway+Vercel healthy at HEAD,
`/api/search` live+auth-gated): `GET /api/search?q=&scope=all|workspace|memory&limit=10&offset=0` composes
both cores into ONE grouped, plane-labeled, no-verdict envelope (workspace/truth + memory groups, each with
own available/reason; memory carries MEMORY_NOTE). Out-of-scope plane present-but-blank; too-short query →
both groups query_too_short (plan §12); every core call wrapped → degraded provider yields a shaped 200,
never 5xx; auth inherited from middleware. +18 route tests (deterministic memory-absent client fixture);
backend suite 646 green; snapshot regenerated (routes.py served → sha256+fingerprint only). Independent Opus
review APPROVE-WITH-MINORS (M2 provider-label fixed, M3 pass-through coverage added, M1 kept as plan-mandated).
P26.4 RELEASED 2026-07-21 (commit `12c9c9e`, CI green run `29879274093`, Vercel+Railway healthy at HEAD):
thin typed `api.search(q, {scope?,limit?,offset?})` in `lib/api.ts` (forwards to `GET /api/search`, auth+base
via `request()`, deterministic query-string order, omits unspecified opts) + full envelope types in
`types.ts` + reusable search fixtures in `apiFixtures.ts`. NO visible UI — legacy no-search tests stay green;
frontend suite 330 green, tsc clean; snapshot regenerated (4 served frontend files → sha256+fingerprint only).
P26.5+P26.6 RELEASED 2026-07-21 (commit `1365b7f`, CI green run `29881081110`, deployed; hosted ⌘K smoke
GREEN): the real ⌘K SearchDialog (self-contained TopBar affordance, focus-trapped, ⌘K/Ctrl-K, 200ms debounce
with alive-flag race guard + <2-char client guard) rendering two clearly separated self-labeled groups —
Workspace (truth) + Project Memory (advisory, leads-not-verdict note verbatim, non-verdict tint) — with
offset-`<mark>` snippets, `hasVerdictLanguage` filter, honest loading/empty/too-short/backend-down/memory-
unavailable states, and deep-link navigation (`/record/<id>`, `/memory?concept=|?file=` with a ProjectMemory
param-reader that auto-opens only existing leads). Delivered in ONE strict-green commit WITH P26.6 (the two
legacy "no-search" tests inverted absence→presence + a functional backend-querying assertion; anti-fake
preserved; prose updated) so no pushed commit is red (D3). 16 search-command tests + rewritten legacy tests;
frontend suite 348 green, tsc + vite build clean, no-vertical-rail green; independent Opus honesty review
APPROVE-WITH-MINORS (invariant genuinely upgraded; M4 verdict-filter coverage added). Hosted browser QA:
trigger live on home+record variants, grouped results with marks + why-matched, PROJECT MEMORY advisory note,
result→/record/<id> navigation + dialog close verified, canonical five intact (2/1/1/1). NEXT: P26.7 (docs).
Date: 2026-07-19 (decisions locked 2026-07-20; activated + P26.0a/0b + P26.1/2/3/4/5/6 2026-07-21)  ·  Baseline commit: f534a4c  ·  Author: Claude (planning)
Related: 2026-07-16-phases-23-26-arc-decisions.md (arc item 9 governs); `2026-07-20-remaining-work-decision-lock.md`
         (authoritative); P24 specs (2026-07-16-phase-24-project-memory-design.md,
          2026-07-19-phase-24-10-memory-freshness-semantics.md); this doc EXTENDS the approved arc.

Approval decisions — **RESOLVED by the 2026-07-20 decision-lock:**
  D1 → **Single grouped `GET /api/search`** with **internal separate providers/helper layers** for
       workspace/truth-plane and Project Memory data.
  D2 → **⌘K + a visible TopBar search trigger** (NOT keyboard-only).
  D3 → The dedicated "no-fake-search" invariant rewrite (P26.6) is its **own reviewed slice**, run
       **only after** backend search behavior + visible trigger + working dialog + correct navigation
       + tests-prove-real-behavior exist. **OPEN sub-item:** the CI-green mechanic (co-reviewed pair
       with a documented transient red vs. strict green-per-commit).
  D4 → Vector/semantic embeddings **stay BACK-BURNER** (not built this phase). See §7, §24.
  D5 → Search is scoped to the **single shared workspace + single memory provider** (no per-user
       scoping; multi-user deferred — depends on greenfield identity). See §14.
  D6 → **No new env vars, no new dependencies.** See §18.
  (Also: a **deterministic richer synthetic seed** is added to this phase — see §6 item 0 and P26.0a —
   because workspace search is not demonstrable over the single seeded experiment.)
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
0. **Deterministic richer synthetic seed** (decision-lock §5): expand the workspace seed from the
   single demo experiment to a small deterministic set of synthetic experiments spanning varied
   workflow states (needs_attention / in_review / ready_to_export / done), exportable **and** blocked
   records, missing **and** completed fields, and different evidence conditions — so workspace search
   has real matches and assistant/queue views are meaningful. Uses the **existing filesystem seeding
   path** (`workspace.py` seed helpers); introduces **no** `ExperimentStore` seam and **no** durable
   store. Every fixture stays synthetic, deterministic, version-controlled, governed by existing data
   restrictions, and clearly labeled demo data — never fake product data.
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
    "provider": "workspace-store",              // which provider produced this group (decision-lock: source/provider)
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
        "plane": "truth",
        "source": "workspace-store"             // provider that produced this result (typed source/provider)
      }
    ]
  },
  "memory": {
    "plane": "memory",
    "provider": "memory:<resolved-reader-id>",  // which MemoryReader produced this group (source/provider)
    "note": "<MEMORY_NOTE — leads to verify, never a verdict>",
    "available": false,
    "reason": "graph_absent",                   // or graph_unreadable / unsupported / null
    "total": 0, "returned": 0, "limit": 10, "offset": 0,
    "results": [
      // when available:
      // { "kind":"concept"|"file"|"rationale", "id":…|null, "path":…|null, "label":…,
      //   "community_name":…|null,
      //   "match": {"field":"concept.label","snippet":"…","reason":"matched concept label"},
      //   "navigate_to":"/memory?concept=<id>"  |  "/memory?file=<path>",
      //   "plane":"memory", "source":"memory:<resolved-reader-id>" }
    ]
  }
}
```
Contract invariants:
- **Typed result metadata (decision-lock):** every result carries enough typed metadata to identify
  **result kind · plane · source/provider · stable identifier · title/label · snippet · why it
  matched (`match.reason`) · navigation target (`navigate_to`)**, and each group carries its own
  **availability/caveat** (`available`/`reason`, plus `note` for memory). The two groups stay clearly
  separated (never merged/interleaved) and one group may be `available:false` while the other returns
  results — partial results are reported honestly.
- **No verdict keys anywhere** — never emit `ok/valid/passed/verdict/schema/errors`; never emit
  PASS/FAIL text; search results are **never** presented as validation findings (mirrors the memory
  plane's contract, audit-architecture §1).
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
   *Mitigate*: demo scale stays tiny — the richer synthetic seed (§6 item 0 / P26.0a) adds only a
   small, deterministic handful of experiments (not hundreds); hard result caps; lazy per-experiment
   loads short-circuit on the summary; document a future index as back-burner (§24). No index built.
   *(Baseline note: today the workspace auto-seeds exactly ONE experiment; searching over one hit is
   why the richer seed is required for a meaningful demo.)*
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

### P26.0a — Deterministic richer synthetic seed (data-only; decision-lock §5) — ✅ RELEASED 2026-07-21
> **RELEASED 2026-07-21.** Five canonical scenarios (fixed Crockford ids `01SYNTHXANESSEED000000000{1..5}`,
> fixed `created_utc`): New Draft (5 pending → needs_attention), Partially Completed (2 pending →
> needs_attention), Ready to Export (0 pending, export dry-run ok, not exported), Export Review Required
> (0 pending, real `export_draft` failure `'uncertainty' is a required property` → in_review — truthfully
> reached, not faked), Exported Record (real export + record/sidecar on disk → done). `demo/run` made
> idempotent (ensure_seeded + upsert by fixed id; response shape `{experiment_id,steps,status}` preserved
> so the frontend is untouched). Files: `workspace.py`, `routes.py`, `tests/test_api.py`,
> new `tests/test_seed.py` (18 behavior-level tests), regenerated `memory-snapshot.json` (202 unchanged).
> Verified: full suite 518 green, snapshot no drift, independent Opus adversarial review APPROVE
> (byte-identical cross-workspace determinism; no truth-core/frontend/forbidden file touched).
- **Objective**: expand `workspace.py` seeding from one demo experiment to a small **deterministic**
  set of synthetic experiments covering varied states (needs_attention / in_review / ready_to_export
  / done), exportable **and** blocked records, missing **and** completed fields, and different
  evidence conditions — enough for meaningful workspace-search matches, queue views, and assistant
  answers. Add any new synthetic fixtures needed (unmistakably fake, deterministic). Uses the existing
  filesystem seeding path; introduces **no** `ExperimentStore` seam and **no** durable persistence.
- **Files touched**: `apps/api/isaac_api/workspace.py` (seed helpers), new committed synthetic
  fixtures under `tests/fixtures/` or `apps/api/isaac_api/data/`, `apps/api/tests/*` (seed
  determinism + state-coverage tests). **Forbidden**: `src/isaac_records/*`, `schema/*`, `memory.py`,
  `auth.py`, any durable store or new env var.
- **Model**: Opus 4.8 (data-model/governance-sensitive — must stay synthetic, deterministic, and not
  become fake product data). **Acceptance**: seeding is deterministic (stable ids/order across
  restarts); every seeded experiment is clearly synthetic/demo-labeled; each target workflow state is
  represented; `examples/` untouched; backend suite green. **Governance**: report which fixtures were
  added and that all are synthetic. **Report**: the seed catalog + determinism evidence. **Commit**:
  single. **Stop**: review before P26.1. *(Placement in Phase 26 is decided by the decision-lock;
  Stabilization only verifies it — it is not re-implemented there.)*

### P26.0b — Guarded synthetic-demo reset (corrective; closes CQ-1) — ✅ RELEASED 2026-07-21
> **RELEASED 2026-07-21** — commit `68fd910`, CI green run `29872521920`, deployed to Railway + Vercel.
> An UNPLANNED corrective slice: P26.0a prevented FUTURE accumulation, but the hosted shared Railway
> volume still held 8 stale pre-P26.0a random-id `demo/run` records (13 total). Adds
> `POST /api/demo/reset` (preview/execute) + a guarded, subordinate-destructive **Reset Demo** control on
> My Experiments, restoring the shared synthetic workspace to EXACTLY the five canonical scenarios.
> **Safety model**: typed `DemoResetRequest` (`extra="forbid"` → caller ids/paths rejected 422); removes
> ONLY records proven managed-legacy by the exact `source.description` marker; REFUSES with zero mutation
> if ANY ambiguous record is present; deterministic reseed via the truth core; idempotent; path-free
> typed response; NO general per-experiment DELETE route. **Frontend**: fail-closed synthetic-only gate
> (`GET /api/health` mode), preview-before-execute, shared-workspace disclosure, type-"RESET" arming,
> sync single-submit guard, refuse-with-no-bypass on ambiguous, focus-trap/return a11y, list refresh on
> success. **Concurrency**: two simultaneous resets can never raise an uncaught 500 — the remove path AND
> both read paths (`_load_all_experiments`, `list_experiments`) tolerate a dir removed mid-operation; a
> deterministic read-race regression test proves the guard (verified to FAIL without the fix).
> **Files**: `workspace.py`, `routes.py`, new `apps/api/tests/test_reset.py` (18); `apps/web` — new
> `components/ResetDemoDialog.tsx`, `lib/{api,types,labels}.ts`, `screens/ExperimentsHome.tsx`,
> `screens/screens.css`, `styles/base.css`, `test/apiFixtures.ts`, new `__tests__/reset-demo.test.tsx`
> (26); regenerated `memory-snapshot.json` (202 unchanged). **Verified**: backend 536, frontend 325,
> `tsc -b` + `vite build` clean, snapshot no drift, committed-snapshot gate 17, R4.3 full preflight PASS.
> **Review**: two independent Opus reviews (backend, then full-slice); the full-slice review found the
> read-path concurrency race (IMPORTANT) → fixed + deterministic test; two MINORs (constant synthetic
> gate → documented + deferred; Escape preventDefault → accepted). All Critical/Important resolved.
> **Hosted QA GREEN (production, browser-verified 2026-07-21)**: Reset Demo live and subordinate; preview
> reported exactly Current 13 / Canonical Preserved 5 / Legacy Removed 8 / Ambiguous 0 / Final 5; execute
> → ONE mutation request (`POST /demo/reset` 200) + one list refresh (`GET /experiments` 200); dashboard
> refreshed to EXACTLY five with distribution needs_attention 2 / in_review 1 / ready_to_export 1 / done
> 1; the Exported Record (`01SYNTHXANESSEED0000000005`) retained its Exported artifact; reload preserved
> the five; **Run Synthetic Demo ×3 held the count at 5** (each upserts the canonical `…0001`, all 200);
> Railway health 200 at `68fd910`; console clean; no failed request.
> **CQ-1 disposition — CLOSED**: root cause = `demo/run` created a new experiment on every call
> (unbounded accumulation, `routes.py`); PREVENTION = deterministic canonical ids + idempotent seeding
> (P26.0a); CLEANUP = this guarded reset (P26.0b); hosted result = 13→5 and three repeated demo runs stay
> at 5. Both prevention and cleanup are verified on production.
- **Not in the original §20**: surfaced from the P26.0a hosted-QA finding (the persistent Railway volume
  retained pre-P26.0a random-id demo records). Scoped, TDD, independently reviewed, one implementation
  commit.
- **Forbidden (honored)**: `src/isaac_records/*`, `schema/*`, `auth.py`, `memory.py`, `examples/`,
  `graphify-out/` — none touched. No new dependency, no new env var, no DELETE route.
- **Deferred to the post-Phase-26 architecture decision packet**: persistent-vs-ephemeral workspace
  storage, and wiring `is_synthetic_only()` / `/health` mode to an authoritative runtime signal (both are
  constants today — acceptable only because the prototype is synthetic-only by construction; the real
  defense is provenance → ambiguous → refuse).

### P26.1 — Workspace search core (no route) — ✅ RELEASED 2026-07-21
> **RELEASED 2026-07-21** — commit `173780f`, CI green run `29876044687`, Railway+Vercel healthy at HEAD.
> Added `apps/api/isaac_api/search.py`: pure, deterministic `workspace_search(query, experiments, *,
> limit, offset) -> WorkspaceSearchResults` (frozen dataclasses `MatchInfo`/`WorkspaceResult`/
> `WorkspaceSearchResults`). Normalization = NFC + casefold + whitespace-collapse, 256-char input cap,
> min length 2 (`query_too_short`). Token-AND matching over four tiers **exact > prefix > token >
> substring**; stable TOTAL-order rank `(tier, facet_priority, created_utc, id, match.field)`; result cap
> **50**, default page **10**, `limit`/`offset` clamped, `total = len(truncated)`; per-hit `snippet` +
> structured `offsets` + human `reason` + `tier`. Six navigable truth-plane kinds — `experiment`,
> `record_id`, `draft_field` (incl. pending blockers → `/complete`), `evidence`, `artifact`, `source_ref`
> — each `plane:"truth"`, `source:"workspace-store"`, `navigate_to:/record/<id>[/complete|/evidence|
> /export]`. **The signature intentionally OMITS the conceptual `loaders` param**: all searchable content
> is in-memory on the `Experiment`/draft, so no loader is required (directive §9 "where required"); the
> core is pure over the hardened `list_experiments()` snapshot and does ZERO filesystem access, so a
> concurrent reset can never make search raise (P26.0b read-race contract). **Governance**: no verdict
> keys/language, no truth-core import, stdlib-only (`re`/`unicodedata`); a defensive `_is_pathlike`
> sanitizer drops path-like aspects AND labels so `examples/**`, absolute, `/tmp`, and workspace-internal
> paths never surface even on dirty draft content. Lead dedup by `(experiment, kind, label, snippet,
> reason, tier)` collapses byte-identical leads while keeping distinct-label same-value fields.
> **Files**: `apps/api/isaac_api/search.py` (new), `apps/api/tests/test_search.py` (new, 53 behavior
> tests). No route, no frontend, no `memory.py`, no truth-core edit. **Verified**: full backend suite 589
> green, snapshot no drift, committed-snapshot gate 17, R4.3 full preflight PASS. **Review**: independent
> Opus adversarial review → APPROVE-WITH-MINORS; the one Important (docstring/plan no-leak guarantee not
> enforced + the plan-§15 dirty-data test missing) FIXED (sanitizer + 5 adversarial governance tests);
> minors (dedup fidelity for same-value distinct fields; docstring plane-label + ranking-premise
> precision) fixed. **Hosted QA**: backend-library-only slice not wired into any route → hosted browser QA
> not independently meaningful; regression check = Railway/Vercel healthy at `173780f`, no visible change.
- **Objective**: `apps/api/isaac_api/search.py` — pure `workspace_search(query, experiments, loaders,
  limit, offset)` returning typed workspace results; normalization, token-AND matching, ranking,
  caps, pagination, snippet + reason. TDD.
- **Files touched**: `search.py` (new), `apps/api/tests/test_search.py` (new).
  **Forbidden**: `src/isaac_records/*`, `schema/*`, `routes.py`, `memory.py`, frontend.
- **Model**: Opus 4.8 (search architecture/governance). **Acceptance**: all matching/ranking/caps/
  pagination/governance/no-verdict tests green; no truth-core import. **Tests**: as §16 workspace.
- **Report**: contract + ranking rules + what fields are searched. **Commit**: single. **Stop**: review before P26.2.

### P26.2 — MemoryReader.search() (no route) — ✅ RELEASED 2026-07-21
> **RELEASED 2026-07-21** — commit `51e8b24`, CI green run `29877645942`, Railway+Vercel healthy at HEAD.
> Added `search(self, query, limit=10, offset=0) -> dict` to the `MemoryReader` Protocol and implemented it
> in BOTH `LocalGraphArtifactSource` and `SanitizedSnapshotSource` via ONE shared pure module-level
> `_run_memory_search(reader, query, limit, offset)` (+ `_mem_normalize`/`_mem_tier`/`_mem_snippet_and_offsets`/
> `_mem_best_aspect`, `_MEM_*` constants). Deterministic: NFC + casefold + whitespace-collapse (256 cap,
> min length 2 → `query_too_short`), token-AND four-tier match (exact>prefix>token>substring), stable
> total-order rank `(tier, facet, natural_key, match.field)`, cap 50 / page 10, per-hit snippet + offsets +
> reason + tier. Three kinds — `concept` (label/id/community), `file` (path/type/community), `rationale`
> (file-detail text) — each `plane:"memory"`, `source:"memory:<provider_kind>"`, `navigate_to
> /memory?concept=<id> | ?file=<path>`. **Governance inherited**: the helper reads ONLY the reader's public
> methods (`overview/concepts/files/file/status`), never raw `_GraphState`/`_SnapshotState`, so every
> path/secret/anchor filter is inherited — adversarially probed, no excluded/secret/unsafe file can surface.
> **Honest degradation** (`graph_absent`/`graph_unreadable` → safe empties, never raises); `query_too_short`
> keeps `available:true`. **Stdlib-only** (adds `unicodedata`; no `re`, no truth-core/graphify/fastapi/
> `search.py` import) — `test_memory_module_imports_only_stdlib` still green (`_STDLIB_ROOTS` += `unicodedata`).
> **Snapshot generator UNTOUCHED** (plan §18 assumption held): `search()` scans the already-served
> projection at request time; `scripts/build_memory_snapshot.py` git-clean. **Files**: `memory.py`,
> `tests/test_memory.py` (21 frozen local behavior tests + isolation/protocol update), `tests/test_snapshot_
> source.py` (snapshot search + non-vacuous local↔snapshot parity), regenerated `memory-snapshot.json`
> (§17 predictable drift — memory.py + the two test files are manifest-listed served content; diff confined
> to their sha256 + `served_manifest_fingerprint`). **Verified**: backend suite 628 green, snapshot no drift,
> committed-snapshot gate 17, R4.3 full preflight PASS. **Review**: independent Opus adversarial review →
> APPROVE (only Minors: post-cap `total` intentional/consistent, per-file `file()` for rationales fine at
> demo scale, parity non-emptiness guard added). Backend-library-only → no hosted browser QA needed;
> Railway/Vercel healthy at `51e8b24`.
- **Objective**: add `search(query, limit, offset)` to the `MemoryReader` Protocol and implement in
  `LocalGraphArtifactSource` + `SanitizedSnapshotSource`; reuse existing governance/path-safety
  filters; honest degradation; stdlib-only. Confirm the snapshot generator needs no change (§18). TDD.
- **Files touched**: `memory.py`, extend `apps/api/tests/test_memory.py`.
  **Forbidden**: truth core, `routes.py`, frontend, `scripts/build_memory_snapshot.py` (touch only
  if P26.1 assumption is wrong — report it).
- **Model**: Opus 4.8. **Acceptance**: memory-search tests + degradation tests green; isolation
  test `test_memory.py:813` still green. **Tests**: §16 memory. **Report**: whether the generator
  was touched and why. **Commit**: single. **Stop**: review before P26.3.

### P26.3 — GET /api/search route — ✅ RELEASED 2026-07-21
> **RELEASED 2026-07-21** — commit `f9d6b0a`, CI green run `29878778089`, Railway+Vercel healthy at HEAD;
> `/api/search` live and auth-gated on Railway (401 without bearer). Added `GET /api/search` (routes.py §17,
> `search_records`) composing `search.workspace_search` + `memory.get_default_reader().search` into one
> grouped envelope: `{query, normalized_query, scope, workspace{plane:truth,provider,available,reason,
> total,returned,limit,offset,results}, memory{plane:memory,provider:"memory:<kind>",note:MEMORY_NOTE,
> available,reason,total,returned,limit,offset,results}}`. `scope` all|workspace|memory (unknown→all); an
> out-of-scope plane stays present with true availability but blank rows; a too-short query sets both
> groups' reason=query_too_short (§12) with each plane's own available honest; every core call wrapped so a
> degraded provider yields a shaped 200 — NEVER 5xx. WorkspaceResults serialized via `dataclasses.asdict`;
> memory results already JSON-ready. Auth inherited from `ApiKeyAuthMiddleware` (no per-route code). **Files**:
> `routes.py`, `tests/test_search.py` (+18 route tests: envelope shape, scope filtering, per-group
> independence with memory degraded, query_too_short, memory-available via golden snapshot, pagination
> pass-through, adversarial-params-never-5xx, no-verdict, auth-gating; deterministic memory-absent `client`
> fixture), regenerated `memory-snapshot.json` (routes.py served → sha256+fingerprint only; generator
> git-clean). `serialize.py` NOT needed (asdict); `test_deploy_config.py` unchanged (no route-enumeration
> test). **Verified**: backend suite 646 green, snapshot no drift, committed-snapshot gate 17, R4.3 preflight
> PASS. **Review**: independent Opus adversarial review (17 TestClient probes) → APPROVE-WITH-MINORS: M2
> (`memory:None` label edge) fixed, M3 (route pass-through coverage) added, M1 (query_too_short precedence)
> kept as the plan-mandated symmetric-envelope behavior. Not yet UI-consumed (P26.4/P26.5) → no hosted
> browser QA; regression check = Railway/Vercel healthy at `f9d6b0a`, `/api/search` reachable+gated.
- **Objective**: wire both cores into one grouped, plane-labeled, no-verdict envelope; `scope`,
  caps, pagination; auth inherited; per-group independence; never 5xx on a degraded provider.
- **Files touched**: `routes.py`, optionally `serialize.py`, extend `test_search.py` /
  `test_deploy_config.py`. **Forbidden**: truth core, `auth.py` logic, frontend.
- **Model**: Opus 4.8. **Acceptance**: route tests + auth-gated test green; full backend `pytest`
  green. **Tests**: §16 route. **Report**: envelope example + auth confirmation. **Commit**: single.
  **Stop**: review before frontend.

### P26.4 — Frontend API client + types (no visible UI) — ✅ RELEASED 2026-07-21
> **RELEASED 2026-07-21** — commit `12c9c9e`, CI green run `29879274093`, Vercel+Railway healthy at HEAD.
> `lib/api.ts` gains `search(q, {scope?,limit?,offset?}) -> Promise<ApiSearchResponse>` via `getJson` (auth
> header + base inherited from `request()`); query string built deterministically (`q` always, then
> scope/limit/offset in fixed order, only when provided). `lib/types.ts` gains the full envelope contract
> (`ApiSearchResponse` + `ApiWorkspaceSearchGroup`/`ApiMemorySearchGroup` + result/match types + reason
> unions) mirroring the P26.3 backend shapes. `test/apiFixtures.ts` gains reusable `searchResponse` /
> `searchResponseMemoryDown` / `searchRoutes()` for the P26.5 dialog. **No chrome/UI change** — the legacy
> "no search" tests (`help-and-honesty`, `memory-concepts`) stay green. **Verified**: frontend suite 330
> green, `tsc -b` clean (no `any`), 5 `api.search` contract tests. Snapshot regenerated in-slice (api.ts/
> types.ts/apiFixtures.ts/api.test.ts are manifest-served — diff confined to their sha256 + fingerprint;
> generator unchanged). Sonnet implementation (mechanical wiring per §21); orchestrator diff-review + verify
> gate (no separate Opus review needed for this mechanical slice). Backend untouched.
- **Objective**: `api.search(q, {scope, limit, offset})` + result types in `lib/api.ts`; fixtures in
  `test/apiFixtures.ts`. No chrome change yet — legacy "no search" tests still pass.
- **Files touched**: `lib/api.ts`, `test/apiFixtures.ts`, `api.test.ts`.
  **Forbidden**: `TopBar.tsx`, `AppShell.tsx`, the two legacy test files, backend.
- **Model**: Sonnet 5 (mechanical client wiring). **Acceptance**: client tests green; `npm test`
  green (legacy tests untouched + passing). **Tests**: request encoding + auth header + envelope
  parse. **Report**: method signature + types. **Commit**: single. **Stop**: review before P26.5.

### P26.5 — SearchDialog + ⌘K + TopBar trigger (feature) — ✅ RELEASED 2026-07-21 (with P26.6, atomic commit `1365b7f`)
> **RELEASED 2026-07-21** — one strict-green commit `1365b7f` with P26.6 (D3: no transient-red push). CI green
> run `29881081110`, Railway+Vercel healthy, hosted ⌘K smoke GREEN. `components/SearchDialog.tsx` (new,
> mirrors ResetDemoDialog): visible `role="search"` `.topbar-search` trigger (Search glyph + ⌘K hint) mounted
> in TopBar on every variant; document-level ⌘K/Ctrl-K opener; focus-trapped `role=dialog` (aria-modal,
> resolvable aria-labelledby, capture-phase Tab containment, ESC close + focus return, autofocused
> `type=search`). 200ms debounce → `api.search`, alive-flag ensures latest-query-wins, strict <2-char client
> guard (no fetch). Two clearly separated self-labeled groups — Workspace (truth) + Project Memory (advisory,
> `note` verbatim, `--advisory-*` tint + full border, NEVER a rail or verdict palette); rows show label +
> why-matched reason + offset-`<mark>` snippet; `hasVerdictLanguage` filters snippets. Honest states: loading,
> "No matches", too-short hint, backend-down (RUN_COMMAND, role=status), memory-unavailable (quiet non-alert
> note, workspace still renders). `screens/ProjectMemory.tsx` reads `?concept=<id>`/`?file=<path>` and
> auto-opens ONLY an existing lead. Mounted via TopBar (NOT AppShell — TopBar is the shared per-screen chrome).
> **Files**: `SearchDialog.tsx`+`search-dialog.css` (new), `TopBar.tsx`, `HelpPanel.tsx`, `icons.tsx` (Search
> glyph), `ProjectMemory.tsx`, new `search-command.test.tsx` (16). **Verified**: frontend suite 348 green, tsc
> + vite build clean, no-vertical-rail green. **Review**: independent Opus honesty review APPROVE-WITH-MINORS
> (debounce race guarded, plane honesty + a11y sound, invariant genuinely upgraded); M4 verdict-filter+`<mark>`
> coverage added; M1/M2/M3/M5/M6 accepted (documented low-risk defense-in-depth / coverage follow-ups).
> **Hosted QA GREEN**: trigger live (home+record), grouped results with marks + why-matched, PROJECT MEMORY
> advisory note + honest "No memory leads", result→`/record/<id>` navigation + dialog close, canonical five
> intact.
### P26.5 — SearchDialog + ⌘K + TopBar trigger (feature) [original plan]
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

### P26.6 — DEDICATED "no-fake-search" invariant rewrite (reviewed slice) — ✅ RELEASED 2026-07-21 (atomic with P26.5, commit `1365b7f`)
> **RELEASED 2026-07-21** — delivered in the SAME commit as P26.5 (`1365b7f`). D3 was resolved to STRICT
> green-per-commit (no transient-red push); since P26.5's feature necessarily reddens the two legacy
> "no-search" tests and only P26.6 can green them, they were shipped as ONE atomic commit — the rewrite kept
> unburied in its own dedicated test files with rationale comments (arc-#10 intent honored). `help-and-honesty
> .test.tsx`: the P22D absence assertions (`[role=search]`/`.topbar-search`/`⌘K`/`Search` all null) inverted
> to PRESENCE + a functional test that opens the dialog, queries the backend via `searchRoutes()`, and asserts
> the Workspace group renders (a dead decorative input fails it); anti-fake user-chip assertion preserved in
> its own describe; P22D comment marks Decision 1 superseded by P26. `memory-concepts.test.tsx`: the two
> "no inline searchbox" assertions KEPT (still true — the ⌘K palette is separate global chrome), title/comment
> clarified, + a new `?concept=` deep-link auto-open test. Prose updated in `TopBar.tsx` + `HelpPanel.tsx`
> docstrings ("no search" → the real ⌘K palette). Independent Opus review confirmed the honesty invariant was
> genuinely upgraded (present + functional + verdict-free), not gutted; no guardrail silently dropped.
### P26.6 — DEDICATED "no-fake-search" invariant rewrite (reviewed slice) [original plan]
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

- Orchestrator (**Fable 5 when available, else Opus 4.8**): planner/reviewer/verifier; the P26.0
  gate; reviews every slice diff. Authors planning markdown; **never implements production code**.
- Opus 4.8 (implementation): P26.0a (synthetic seed — governance-sensitive), P26.1, P26.2, P26.3
  (search architecture, governance, honest degradation), P26.5, P26.6 (UX/a11y/honesty-sensitive).
- Sonnet 5 (implementation): P26.4 (mechanical client wiring), P26.7 (docs).
- Every slice independently assignable/reviewable/verifiable/committable with a stop gate (MODEL RULE).

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

## 25. Explicit questions for the user — RESOLVED (2026-07-20 decision-lock)

1. **D1** ✅ **Single grouped `GET /api/search`** with internal separate providers.
2. **D2** ✅ **⌘K + a visible TopBar "Search ⌘K" trigger** (not keyboard-only); `/` left unbound.
3. **D3** ✅ Rewrite is a **dedicated reviewed slice (P26.6), after** real behavior/trigger/dialog/
   navigation/tests exist. **OPEN sub-item:** the CI-green mechanic — (a) co-reviewed pair with a
   documented transient red, or (b) strict green-per-commit. Arc decision #10 favors (a); confirm at
   P26.0.
4. **D4** ✅ Vector/semantic search stays **BACK-BURNER** (not built).
5. **D5** ✅ Scoped to the **single shared workspace + single memory provider**; UI must not imply
   per-user results.
6. **D6** ✅ **No new env vars, no new dependencies.**
7. **OPEN** — Result caps/pagination defaults (proposed cap 50, page 10) — confirm at P26.0.
8. **OPEN** — Minimum query length (proposed 2 chars) — confirm at P26.0.
9. **NEW (decision-lock)** — a **deterministic richer synthetic seed** is added (§6 item 0 / P26.0a),
   **placed in Phase 26** (Stabilization verifies, does not re-implement). **OPEN:** only the exact
   target state-coverage / number of synthetic experiments — confirm at P26.0.
```
