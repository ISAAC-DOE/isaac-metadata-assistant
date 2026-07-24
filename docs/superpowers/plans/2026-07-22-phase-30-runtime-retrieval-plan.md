# Phase 30 — Live Runtime Record Retrieval (P30.0 proof gate + plan)

Status: **Phase 30 COMPLETE (2026-07-22).** P30.0 proof gate REJECTED a persistent index on measured
evidence; shipped the thin Option-B provider (P30.1 `/runtime/records`, no index/cache/service) + one real
consumer (P30.3 cross-record triage in SearchDialog) + verification (P30.4) + hosted QA PASS (P30.5). Each
slice independently reviewed (all SHIP; P30.1 +2 leak/filter guards). Backend 821, frontend 524, truth path
frozen. Non-blocking caveats (triage-degradation not hosted-inducible; export-screen artifact path; two
P30.3 nits) in the ledger's Phase 30 gate. Next: Phase 31 (P31.0 format selection — possible human-gate 5).
Baseline: `main @ 5a935b8` · CI green · Railway `5a935b8` synthetic-only · Vercel 200 · backend 806 · frontend 509.

Derived from the P30.0 read-only proof (2 parallel tracks: search-capability/use-case audit; performance
measurement at 5/50/100/500 synthetic records). Obeys the master ledger; not a competing master plan.

**Governing principle:** runtime retrieval is a DERIVED READ MODEL over authoritative Workspace records —
never a second truth store, never a replacement for current-record loading / validation / evidence audit,
never a source of inferred values as facts, never durable chat, never Project-Memory-as-record-data.
Authority order: current open experiment → direct Workspace state; cross-record discovery → existing
search or a derived Workspace projection; code/docs/policy → Project Memory/Graphify.

---

## 1. Existing Workspace search (P26) — what it already provides

- `workspace_search(query, experiments, limit, offset)` (`search.py:530`) is a PURE function over the
  in-memory `list_experiments()` snapshot; `GET /search` (`routes.py:1231`) re-runs the full scan every
  call. **No persistent index** (`for exp in experiments:` `search.py:563`) → current-by-construction,
  reset-safe, deletion-safe, restart-safe with zero extra machinery.
- Searchable candidates: title, id, exported record_id, draft field value/label/path/status, pending
  blockers, evidence entries, source refs, exported-artifact lead. Deterministic ranking (tier → facet →
  created_utc → id), token-AND, snippets+offsets, `MAX_RESULTS=50`, path-scrubbed (`_is_pathlike`
  `search.py:240`), no verdict language, no filesystem access.
- A result exposes `{kind, experiment_id, record_id, title, label, status(coarse 4-value), match, navigate_to, plane}`.
  It does **NOT** carry workflow step-state, evidence classification, artifact freshness, or `record_rev`,
  and `/search` has **no structured filters** (only `q, scope, limit, offset`).

## 2. Cross-record use-case matrix (answerable-now vs missing)

- **Already cross-record (NOW):** incomplete / needs-attention / in-review / ready-to-export / exported —
  via `list_experiments` `_summary.status` + `ExperimentsHome` grouping (`adapt.ts:41`). Open the current
  version of a result — `navigate_to` + live detail load.
- **Free-text PARTIAL:** "mentions material/technique X", "contains a field with value V" — search hits the
  text but isn't a typed filter (single-path MVP: technique is trivially uniform).
- **MISSING cross-record (structured, derived-state):** which records are *blocked / reopened* (vs the
  coarse status), which have *conflicting / inferred-candidate / unknown* evidence, which have *stale*
  artifacts, the *rev* of a cross-record lead. All need **typed filters over derived axes — not free-text,
  not an index.** Their only current surface is **per-record** (`detail.workflow`, `/evidence-
  classification`, `detail.artifact`).
- **MISSING (assistant):** the assistant is strictly single-record (`useRecordSession` builds one
  `AgentContext` from one detail + pending + classification; no `REGISTRY` intent spans records). The
  approved use-case matrix + assistant-integration section explicitly want cross-record queries.
- **Speculative (no consumer):** "missing field Z" / negative filters, cross-record evidence-class *sweep*,
  cross-record stale-artifact *sweep*, rev-on-search-result — listed in the mandate but with NO shipped
  product surface requesting them.

## 3. Performance proof (T2; near-worst-case: all records forced into the export-dry-run branch)

`total scanned = N + 5` (canonical seeds always present). Warm-median ms, local SSD.

| Path | 5 | 50 | 100 | 500 |
|---|---|---|---|---|
| `list_experiments()` (disk only) | 0.9 | 4.9 | 9.6 | 61 |
| load-all-details (no status) | 0.9 | 4.9 | 10 | 83 |
| **structured filter w/ `status()`/record** | 4.2 | 30 | 61 | **315** |
| `workspace_search` (broad) | 8.0 | 50 | 98 | **478** |
| **full `/search` route** | **9.1** | **56** | **108** | **559** (p95 570) |

- **Interactive at 5–100** (well under 200 ms); **500 degrades to ~560 ms** (sub-second-but-laggy).
- Bottleneck = **`exp.status()` = a per-record `export_draft` dry-run** (~0.6 ms/rec, CPU-bound schema
  validation), which `workspace_search` calls once per record. NOT disk, NOT index-absence. Memory 21 MB @ 505.
- Response sizes trivial (search page ≤6 KB; 100-record projection ~25 KB).
- **Limitations:** synthetic, single-process, local SSD (Railway is CPU-comparable, network volume); one
  draft shape; worst-case status branch. No manufactured requirement — measured against "interactive hosted
  search at 5–100 synthetic records."

## 4. Architecture decision

| Option | Verdict | Why |
|---|---|---|
| **A** — search unchanged | insufficient alone | free-text can't do structured derived-state filters, and shouldn't be stretched (breaks the honest lead-finder contract). BUT the status-axis cross-record already ships. |
| **B** — thin direct runtime provider | **SELECTED (narrow)** | structured filters + safe projection over the SAME scan; current-by-construction; no index/cache/service; the right shape for the one real gap (cross-record assistant/triage). |
| **C** — short-lived rev-keyed cache | rejected (now) | measurements show direct derivation is interactive at ≤100; a cache adds invalidation complexity for no measured need. Revisit only if scale + the `status()` hot-path fix are both exhausted. |
| **D** — persistent index | **rejected** | search is already a fresh scan; measurements show no perf need at credible scale; an index adds a durable second store + sync/reset/deletion/recovery burden for zero justified benefit. "Future scale" is not sufficient. |

**Selected: Option B, scoped to ONE concrete consumer.** A read-only `runtime_records` provider derives, per
record, ONLY safe confirmed facts — `{experiment_id, title, status, pending_count, exported, record_id,
workflow: current_step + blocked/reopened flags, evidence_counts (5-class histogram), artifact_state
(none/current/stale), record_rev, updated_utc, navigate_to}` — from the same `list_experiments()` scan, with
**only** the typed filters its consumer uses (`status`, `workflow_state`, `artifact`, and evidence-has-
conflict). Consumer: a **deterministic cross-record assistant triage intent** ("which records need
attention / are blocked / have conflicts / are exportable now — open the match") + a matching filter in the
existing SearchDialog/triage. **Scoped OUT (no consumer → not built):** missing-field/negative filters,
full evidence-class sweep beyond has-conflict, rev-on-every-search-result.

## 5. Contracts

- **Confirmed-facts boundary:** include only the safe fields above (all already server-derived + shipped
  somewhere). EXCLUDE: unconfirmed proposals, inferred candidates as facts (they may appear ONLY behind an
  explicitly-labeled evidence-status query, never populating a confirmed field), rejected values, chat,
  unsent input, raw files, secrets, auth data, internal paths, stack traces, Project-Memory content as record
  state. Reuse the existing `_is_pathlike`/`_looks_unsafe` scrubbers.
- **Freshness:** each projected record carries `record_rev` + `updated_utc`; the projection is derived fresh
  per request (no cache). Opening a result → load the authoritative Workspace record + compare rev; the
  assistant must NOT use a cross-record summary as the source for a current-record scientific answer (it
  hands off to the direct record load).
- **Degradation:** provider failure must not block the current record, manual workflow, evidence review,
  export, P26 search, or Project Memory; the UI names the unavailable provider; no stale value labeled current.
- **Perf note (optional, not built speculatively):** if scale ever pushes the `status()` sweep past
  interactivity, skip/cache derived status in the hot path (removes ~65% of search cost) — cheaper than any
  index; deferred until measured need.

## 6. Slices (adapted; leaner than the mandate's sketch — no cache/index work, refresh is by-construction)

| Slice | Scope | Files (exclusive) |
|---|---|---|
| **P30.1** runtime record projection + typed filters | NEW `apps/api/isaac_api/runtime_records.py` (pure, derives the safe projection over `list_experiments()`, reusing `_summary`/`derive_workflow`/`classify_fields` counts/`artifact_state`) + `GET /runtime/records?filter=…` in routes.py; test-first (projection safety + filters + freshness metadata) | runtime_records.py, routes.py, tests |
| **P30.2** (folded into P30.1) | typed filters + stable ordering + pagination live with the provider | — |
| **P30.3** assistant + search cross-record integration | a deterministic cross-record triage intent in assistantAgent.ts (source-layer labeled; current-record handoff; never truth-substitutes) + a SearchDialog/triage filter surface consuming the provider | assistantAgent.ts, SearchDialog.tsx, api.ts, types.ts, tests |
| **P30.4** refresh/reset/degradation | verify by-construction freshness (mutation/reset/deletion) + honest provider-unavailable state; NO cache to invalidate | tests + minimal UI degraded-state |
| **P30.5** hosted QA + closure | cross-record queries, authority/freshness, mutation/reset, degradation, perf sanity | QA only |

## 7. Test-first (per slice) + independent Opus review per release slice; verification loop per the mandate.

## 8. Human gates: none. Selected design adds no database/service/secret/billing/index → proceed
automatically. Stop only if Option C/D or an infrastructure change becomes necessary (it does not).
