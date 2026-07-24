# Search architecture (Phase 26)

A short, accurate note on the real, API-backed search shipped in Phase 26. Governing design:
[`docs/superpowers/plans/2026-07-19-phase-26-workspace-memory-search-plan.md`](superpowers/plans/2026-07-19-phase-26-workspace-memory-search-plan.md)
(§20 has the per-slice RELEASED notes this page summarizes). For the two-plane discipline this
feature extends, see [`architecture.md`](architecture.md) and
[`project-memory-map.md`](project-memory-map.md).

## What shipped

`GET /api/search?q=<str>&scope=all|workspace|memory&limit=<int, default 10>&offset=<int, default 0>`
returns **one grouped, plane-labeled, no-verdict envelope** with two independently-honest groups:

- **`workspace`** — truth plane, `provider: "workspace-store"`.
- **`memory`** — advisory memory plane, `provider: "memory:<kind>"`, carries the same
  leads-not-a-verdict note used elsewhere in the memory plane (`MEMORY_NOTE`).

Each group reports its own `available`/`reason`, so one plane can be down while the other still
returns results — neither group is ever merged into a single verdict. `scope=workspace` /
`scope=memory` omit the other plane's results (the group stays present, availability still
reported). The route never returns 5xx for a degraded provider; it always returns a shaped 200.

## Deterministic, not semantic

No LLM, no embeddings, no database, no persistent index. Both search cores share the same
normalization and ranking discipline:

- Normalize: Unicode NFC + casefold + whitespace-collapse; 256-char input cap; **minimum query
  length 2** (shorter → `query_too_short`, both groups honest about it).
- Match: token-AND matching across four tiers, ranked **exact > prefix > token > substring**, with
  a stable total-order tie-break.
- Cap: result cap **50**, default page size **10**, `limit`/`offset` clamped and passed through.
- Every hit carries a `snippet`, structured match `offsets` (client renders `<mark>` without
  server-side HTML), and a human `reason` ("why this matched").

Vector/semantic embedding search and fuzzy ranking are **not built** — explicitly deferred
back-burner (decision D4); see [`project-memory-map.md`](project-memory-map.md#roadmap--back-burner-items).

## Two independent cores

- **Workspace core** — pure `search.workspace_search(query, experiments, *, limit, offset)`
  (`apps/api/isaac_api/search.py`) over the hardened in-memory workspace snapshot
  (`list_experiments()`). No filesystem traversal at query time, so a concurrent workspace reset
  cannot make search raise (read-race-safe). A defensive path-leak sanitizer drops any path-like
  match content so `examples/**`, absolute paths, and workspace-internal paths never surface.
  Imports no truth-core validation and emits no verdict keys.
- **Memory core** — `MemoryReader.search()` on the `MemoryReader` Protocol
  (`apps/api/isaac_api/memory.py`), implemented by both providers (`LocalGraphArtifactSource`,
  `SanitizedSnapshotSource`). It delegates only to each reader's already governance-filtered public
  read surface (`overview/concepts/files/file/status`) — never raw internal state — so every
  path/secret/anchor filter the memory plane already enforces is inherited; no excluded or secret
  path can surface through search. Stdlib-only, consistent with the memory plane's Graphify-free
  isolation guarantee.

## Frontend

`apps/web/src/lib/api.ts` gains a typed `search(q, {scope, limit, offset})` client method. A new
`SearchDialog` component is opened by a global **⌘K / Ctrl-K** shortcut and by a visible trigger in
`TopBar` (not keyboard-only). The dialog is focus-trapped and ARIA-labeled, groups results under
"Workspace" and "Project Memory" (never interleaved), and renders every honest state the backend can
report: loading, no matches, query-too-short, backend-down, and memory-degraded-but-workspace-OK.
Results navigate via a server-supplied `navigate_to` deep link.

## Retired invariant

Phase 22D added tests asserting search must **not** exist in the UI (`help-and-honesty.test.tsx`,
`memory-concepts.test.tsx`) — accurate at the time, since search was decorative chrome that had been
removed. Phase 26 (slice P26.6) rewrote those tests: the absence assertions are gone, replaced with
assertions that the ⌘K search is present **and functional** (opens a real dialog, queries the real
backend, renders real grouped results). The underlying principle these tests protect is unchanged —
decorative, fake, or verdict-implying search stays forbidden — only the "search doesn't exist" premise
was retired because it stopped being true.

## Auth and scope

`/api/search` is gated by the existing app-wide `ApiKeyAuthMiddleware` — no per-route auth code, no
new auth model, no user/session/org concept. Phase 26 added no new environment variables and no new
dependencies (backend or frontend).
