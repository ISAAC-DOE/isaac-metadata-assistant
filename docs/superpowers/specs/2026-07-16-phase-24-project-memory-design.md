# Phase 24 — Project Memory (Design Mini-Spec, P24.0)

Date: 2026-07-16
Status: DESIGN ONLY — awaiting user review gate before any implementation.
Base: commit 73545a9 (Phase 23 complete/deployed), graph freshly regenerated.

This is a design deliverable. No code changes, no endpoints, no commits are made
by P24.0. It defines exactly what Project Memory v1 will be, what it will not be,
and the smallest safe way to build it. Every factual claim about the current repo
was verified against `graphify-out/graph.json`, `graphify-out/manifest.json`,
`graphify-out/.graphify_labels.json`, or a direct read of the named source file.

Follows the Phase 20 design-doc precedent (context → decisions → tables → honest
limitations → verification → out of scope → workflow).

---

## 0. Context

Project Memory today is a live but near-empty screen:
`apps/web/src/screens/ProjectMemory.tsx` renders a placeholder that fetches the
one shipped memory endpoint, `GET /api/graph/status` (routes.py §14), and shows
`GraphStatusChip` (Fresh / Stale / Missing, "memory plane, never a validator").
That is the entire memory surface. It is honest but thin.

Phase 24 turns it into a real project-knowledge memory interface — status,
concept lookup, and source/file provenance — backed by the regenerated Graphify
graph, with honest degraded states and no capability that only *looks* real.

The regenerated graph (verified today): 2,296 nodes / 3,447 edges / 214
communities / 203 indexed files, `built_at_commit` = 73545a9 (= HEAD). It is a
plain JSON file, parseable with stdlib `json`, and lives under the gitignored,
dockerignored `graphify-out/` tree.

---

## 1. The twelve acceptance questions

### 1. What exact files/docs/artifacts does Graphify currently index?

The authoritative index is `graphify-out/manifest.json` — a dict keyed by
repo-relative path (203 keys), each value `{mtime, ast_hash, semantic_hash}`.
Verified top-level breakdown of indexed paths:

- `apps/` — 593 nodes across the FastAPI backend (`apps/api/isaac_api/*.py`,
  `apps/api/tests/*`) and the React frontend (`apps/web/src/**`, configs,
  `apps/web/.vercel/project.json`, `apps/web/.vercel/README.txt`).
- `schema/` — 550 nodes (`isaac_record_v1.json`, `isaac_draft.schema.json`,
  `PROVENANCE.md`).
- `docs/` — 514 nodes (all handoff/architecture/query/plan/spec docs, incl.
  `docs/superpowers/plans/*` and `docs/superpowers/specs/*`).
- `tests/` — 163 nodes (unit + fixtures, incl. `tests/fixtures/official/*.json`,
  `tests/fixtures/synthetic/*`).
- `src/` — 159 nodes (`src/isaac_records/**` truth core).
- `.superpowers/` — 113 nodes (`.superpowers/sdd/*.md` SDD task briefs/reports).
- `ux-review/` — 45 nodes, including **24 `.png` screenshots** (binary).
- `.claude/` — 33 nodes (`.claude/skills/*/SKILL.md`, `.claude/settings.local.json`).
- Root docs: `CLAUDE.md` (24), `AGENTS.md` (19), `README.md` (16),
  `CONTRIBUTING.md` (9), `SECURITY.md`, `pyproject.toml`, `railway.json` (9),
  `.github/workflows/ci.yml`.

Node kinds (`file_type`): code 1,370; document 779; rationale 128 (extracted
docstring/comment summaries); concept 19 (curated god-nodes anchored to
`README.md` / `docs/proposal-v2.md`). Edges (`relation`): contains 1,931; calls
402; imports 368; references 288; imports_from 273; rationale_for 126; method 30;
inherits 8; indirect_call 8; re_exports 7; uses 5; shares_data_with 1. Plus 3
named hyperedges (e.g. the 5-command assistant workflow).

Governance-verified: `examples/` content is **not** indexed except
`examples/README.md` (the tracked governance-instructions doc). No `.env`, no
secrets, no real/private artifacts in the manifest.

### 2. Does the graph contain enough provenance to support a real file/source explorer?

Yes — for a **provenance/navigation** explorer, not a filesystem browser. Every
node carries `source_file` (repo-relative), `file_type`, `community` (int id),
and `source_location` (line ref). Every edge carries `source`/`target` node ids
(resolvable back to `source_file`), `relation`, `weight`, and `source_file`.
Community names are available from `graphify-out/.graphify_labels.json` (dict:
community-id-string → curated name, e.g. `"0" → "Official schema v1.05"`). From
these we can deterministically answer, per indexed file: its role (`file_type`),
its community grouping, its node count, and its related files/concepts (via edges).

What the graph does **not** contain: file *contents* (only structural metadata
and short extracted rationale strings), and any notion of record/experiment
similarity. So it supports a provenance explorer, not a content viewer and not a
"related records" feature.

### 3. If not, what is the smallest safe source-index layer we need?

No new persistent index is needed. The manifest + graph nodes already are the
index. The smallest safe layer is one **read-only, stdlib-only reader module** in
the presentation layer (`apps/api/isaac_api/memory.py`) that:

1. loads `graphify-out/{graph.json, manifest.json, .graphify_labels.json}` lazily,
   caching by mtime (re-parse only when the graph changes);
2. builds a **served allowlist** = manifest keys minus filtered sensitive
   prefixes/files/extensions (see §4);
3. answers status / concept / file-provenance lookups from the parsed structures.

It computes no verdicts, writes nothing, imports no third-party graph library,
and is never imported by `src/isaac_records/`. It is the memory-plane analogue of
the existing `sources.py` (governance-gated reader) — same shape, wider allowlist,
provenance instead of content.

### 4. What can Project Memory answer locally?

With `graphify-out/` present (local dev):
- **Status**: graph present? fresh/stale/missing? built at which commit? how many
  nodes/edges/files/concepts? (all real, from the parsed graph).
- **Concept lookup**: the 19 curated concepts — each concept's anchor file,
  community, and related files/concepts (leads to verify).
- **Source/file provenance**: for any file in the served allowlist — its role,
  community, node count, on-disk presence, related files/concepts, and a
  read-only local path reference.

All answers are framed as *leads to verify against the cited file*, never truth.

### 5. What can Project Memory answer in the hosted deployment if graph artifacts are absent?

Almost nothing — and it says so honestly. The Railway image excludes
`graphify-out/` (`.dockerignore` line 9) and the Dockerfile COPY allowlist never
adds it, so `graph.json`, `manifest.json`, and `.graphify_labels.json` are **all
absent** in the hosted container. Therefore:
- `GET /api/graph/status` → `status: "missing"` (unchanged behavior).
- Every `GET /api/memory/*` → `200 {available: false, reason: "graph_absent"}`
  with empty data (a missing memory plane is optional, never an error).
- The UI shows an honest "Project memory is unavailable in this hosted demo"
  panel. The source/file explorer is, **by construction, a local-only capability**
  this arc — no graph is shipped into Docker (arc decision 4).

### 6. How does the UI make local vs hosted memory behavior honest?

The UI never hardcodes availability — it renders whatever `available`/`status`
the live endpoints return. Hosted returns `available:false` → the UI shows the
unavailable panel; local returns real data → the UI shows concepts/files. The
existing `GraphStatusChip` already degrades a missing graph to a quiet neutral
"Missing" (never an error). The unavailable panel states plainly that the memory
graph is a local/dev artifact not shipped to the hosted demo. No screen ever
implies memory works when the endpoint says it does not (Governing Principle:
"no demo-looking UI that pretends a capability exists").

### 7. How do we prevent Project Memory from looking like validation?

Three layers, spelled out in §9:
- **Structural**: the memory reader lives outside `src/isaac_records/`, computes
  no verdict, and its responses carry **no** `ok`/`valid`/`passed`/`verdict`/
  `schema`/`errors` key — enforced by test.
- **Copy**: every response carries `plane: "memory"` and a `note` ("leads to
  verify — never a validation verdict"); UI labels say "memory plane", "leads to
  verify", "project knowledge, not scientific evidence".
- **Placement**: Project Memory stays a separate destination (`/memory`), never
  blended into the experiment queue or the export gate. It never appears in the
  validate/audit/export flow.

### 8. How do we prevent Project Memory from exposing private files or secrets?

- The only source of truth for "what may be surfaced" is the **served allowlist**
  (filtered manifest) — never an arbitrary filesystem path. A path not in the
  allowlist returns 404 `source_not_indexed`; a syntactically unsafe path
  (`..`, absolute, contains `/` beyond the manifest key) returns 400
  `unsafe_source_path`. Allowlist membership is a closed-set test, so traversal
  cannot reach anything off-list.
- The allowlist **filters out** sensitive/irrelevant indexed paths even though
  they are in the raw manifest: the entire `examples/**` prefix (governance-
  sensitive per CLAUDE.md §6, even `examples/README.md`), `.superpowers/**` (SDD
  ledgers), `apps/web/.vercel/**` (deployment linkage ids),
  `.claude/settings.local.json` (local harness config), and binary extensions
  (`.png` — the 24 `ux-review` screenshots). `.claude/skills/**` is **kept**
  (documented project skills, non-secret).
- **No file bytes are served** by the memory plane at all (§4 decision:
  metadata-only). Even a filtering miss can leak at most a path string + node
  counts, never content.
- Hosted has no graph, so there is nothing to expose there.

### 9. What does "source/file explorer" mean in this app?

A **provenance navigator** over the graph-indexed corpus — not a filesystem
browser and not a file viewer. Given the set of files Graphify indexed, it shows
each file's role (`file_type`), its community grouping, its related
files/concepts (from graph edges), its on-disk presence, and a read-only local
path reference. It answers "what does project memory know about this file and how
is it connected," never "show me arbitrary file bytes." Content viewing of the
*scientific evidence* fixtures remains the job of the existing governance-gated
`GET /api/experiments/{id}/source-preview` (a closed 2-file allowlist), which is
unchanged and is the only content-serving read surface in the app.

### 10. What is explicitly back burner?

From the arc decisions, unchanged: related records / record similarity /
experiment similarity; full graph explorer / raw network visualization; graph-in-
Docker; record indexing into memory; real/private data memory; LLM/freeform
assistant; real-data upload; second domain; portal parity; MCP; dark theme;
multi-user auth; rate limiting. **Added by this spec**: serving file *content*
of arbitrary indexed files (metadata-only in v1; content would need explicit
approval and a separately-justified filtered allowlist).

### 11. What tests prove this actually works rather than only looking real?

Backend endpoint tests asserting real graph-derived shapes (19 concepts; a known
file's real `file_type`/related set); allowlist governance tests (examples/,
.superpowers/, .vercel/, settings.local.json, .png absent from `/memory/files`;
`examples/README.md` → 404 even though it is in the raw manifest); traversal
tests (400); degraded tests (graph absent → `available:false`, malformed graph →
`available:false`, both 200 not 500); an honesty invariant test (no memory
response contains a validation key); a truth-core isolation test (mirrors the
existing `test_core_never_imports_graphify`); and frontend tests that the screen
renders real returned data and the unavailable/stale/backend-down states. Full
list in §10.

### 12. What should wait for Phase 25 or Phase 26?

- **Search/filter over memory** → Phase 26 (memory/project-knowledge search). P24
  ships a browse-by-grouping list with **no** search/filter input, to respect the
  P22 no-fake-search invariant and the arc ordering (Real Search = P26).
- **Grounded assistant using memory as context / guided prompts referencing
  memory** → Phase 25.
- **Related records / record similarity** → back burner (never P24–26).
- **Full graph visualization** → back burner.
- **Serving indexed file content** → deferred; needs explicit approval.

---

## 2. Architecture & module boundary

New code lives entirely in the presentation layer. The truth path
(`src/isaac_records/**`, `schema/`) is untouched.

```
apps/api/isaac_api/
  memory.py        NEW  stdlib-only graph/manifest/labels reader + served allowlist
  routes.py        EDIT adds GET /api/memory/* ; optional additive fields on /graph/status
  (sources.py)     reuse the _guard_name traversal pattern (or a shared copy)
apps/web/src/
  lib/types.ts     EDIT memory wire types
  lib/api.ts       EDIT api.getMemoryConcepts / getConcept / getMemoryFiles / getMemoryFile
  screens/ProjectMemory.tsx   EDIT build out real surface
  components/…     NEW small presentational pieces if needed (within design system)
```

`memory.py` constraints (all test-enforced): imports only `json`, `pathlib`
(stdlib); reads under `REPO_ROOT / "graphify-out"` only; never writes; never runs
`graphify`; never imports `isaac_records`; is never imported by `isaac_records`;
returns plain dicts with no verdict keys. Graph is parsed lazily and cached by
`graph.json` mtime (the ~1.8 MB parse happens at most once per graph change, and
only locally — hosted has no graph to parse).

---

## 3. Endpoint contracts

Base prefix `/api` (existing `APIRouter`). Auth posture unchanged: every route
except `GET /api/health` requires `Authorization: Bearer <ISAAC_UI_API_KEY>` when
that env var is set (auth disabled locally when unset). `_OPEN_PATHS` is **not**
modified — memory endpoints are authed exactly like `/api/graph/status` today.

**Common envelope — every memory response carries these three fields:**

```jsonc
"plane": "memory",
"note":  "Project memory returns leads to verify — never a validation verdict.",
"available": true            // false when the graph is absent/unreadable
```

When `available:false`, add `"reason": "graph_absent" | "graph_unreadable"` and
empty data (`"concepts": []` / `"files": []` / `"file": null`). Never 500 for an
absent or malformed graph — the memory plane is optional.

No memory response ever contains `ok`, `valid`, `passed`, `verdict`, `schema`, or
`errors`. (Honesty invariant, §9/§10.)

### 3.1 `GET /api/graph/status` — EXISTING, optionally extended

Current contract (kept byte-compatible; existing `test_graph_status` must still
pass):

```json
{ "status": "fresh|stale|missing",
  "plane": "memory",
  "note": "Graphify is a memory/query layer — never a validator." }
```

Proposed **additive** fields when the graph is present (all omitted/null when
missing — see approval Q4):

```jsonc
"built_at_commit": "73545a9bbbb4...",   // from graph.json
"node_count": 2296, "edge_count": 3447,
"file_count": 203, "concept_count": 19
```

### 3.2 `GET /api/memory/concepts` — concept lookup index

```jsonc
{ "plane":"memory", "note":"…", "available":true,
  "concepts":[
    { "id":"readme_two_layer_architecture",
      "label":"Two-layer architecture (draft to export to record + sidecar)",
      "community_id":"141", "community_name":"…",   // name null if labels file absent
      "source_file":"README.md", "on_disk":true } ,
    …  // 19 items
  ] }
```

### 3.3 `GET /api/memory/concepts/{concept_id}` — concept provenance + leads

```jsonc
{ "plane":"memory", "note":"…", "available":true,
  "concept": { "id":"…","label":"…","community_id":"…","community_name":"…",
               "source_file":"docs/proposal-v2.md","on_disk":true },
  "related": {
    "files":    [ {"path":"docs/proposal-v2.md","relation":"references","file_type":"document"} … ],  // ≤ 25, by edge weight
    "concepts": [ {"id":"…","label":"…","relation":"references"} … ]                                    // ≤ 25
  } }
```

Unknown clean id → `404 {"error":"concept_not_found","id":"…","plane":"memory"}`.

### 3.4 `GET /api/memory/files` — source/file provenance index (served allowlist)

```jsonc
{ "plane":"memory", "note":"…", "available":true,
  "files":[
    { "path":"src/isaac_records/export.py", "file_type":"code",
      "community_id":"131","community_name":"…",
      "node_count": 42, "on_disk":true } ,
    …  // filtered allowlist (~ manifest minus §4 exclusions)
  ] }
```

### 3.5 `GET /api/memory/file?path=<repo-relative>` — one file's provenance

Path is a **query param** (not a URL segment) so slashes are unambiguous.

```jsonc
{ "plane":"memory", "note":"…", "available":true,
  "file": { "path":"src/isaac_records/export.py","file_type":"code",
            "community_id":"131","community_name":"…","node_count":42,
            "on_disk":true, "local_reference":"src/isaac_records/export.py" },
  "related": { "files":[…≤25…], "concepts":[…≤25…] },
  "rationales": [ "Deterministic, doubly-gated export transform." … ]   // ≤ 10, from rationale nodes
}
```

Error tiers (mirror the existing `source-preview` two-tier convention):
- Unsafe path (`..`, absolute, backslash, `~`) → `400 {"error":"unsafe_source_path", …}`.
- Clean path not in the served allowlist → `404 {"error":"source_not_indexed","path":"…","plane":"memory"}`.

**No `content`/`lines` field exists on any memory response.** (§4 decision.)

---

## 4. Source/file explorer behavior & the served allowlist

**Decision: metadata-only. The memory plane serves provenance + a read-only local
path reference, never file content bytes.** Justification against exposure risk:

1. **Lowest exposure.** With no content path, `.claude/settings.local.json`,
   `.vercel/project.json`, or any file's bytes can never be streamed over the
   network — even through a future bug. A filtering miss leaks a path string, not
   a file.
2. **No duplication of the content surface.** The only content a scientist needs
   to *read* — cited evidence fixtures — is already served by the governance-
   gated `source-preview` (closed 2-file allowlist). A second, far larger content
   reader in the memory plane would widen the read surface with weaker
   justification.
3. **Right job for the plane.** Memory's job is navigation/provenance ("what is
   this, how is it connected, where does it live"), matching the arc decision
   ("source/file provenance", "readable source/file references" = a reference you
   can open, not a stream).
4. **Hosted has no graph**, so content-serving would be dead hosted and only
   benefit local dev — where the operator already has the repo open in an editor.
   Low value, non-trivial risk.
5. **Never implies scientific evidence.** A provenance card labeled "project
   knowledge" cannot be mistaken for an evidence viewer; content bytes rendered
   next to a record could be.

**Served allowlist construction** (in `memory.py`, computed once per graph load):

```
served = { path for path in manifest.keys()
           if not path.startswith(("examples/", ".superpowers/", "apps/web/.vercel/"))
           and path != ".claude/settings.local.json"
           and os.path.splitext(path)[1].lower() not in BINARY_EXTS }   # {".png", …}
```

Filtering rationale (all vetoable — §12):
- `examples/**` — governance-sensitive tree (CLAUDE.md §6). Filtered whole,
  including the one indexed `examples/README.md`, so a future real-data file added
  there can never surface through this path.
- `.superpowers/**` — internal SDD planning ledgers; engineering-process noise on
  a scientist/operator-facing surface. Remain in the graph (local `graphify`
  CLI navigation unaffected); just not surfaced by this API.
- `apps/web/.vercel/**` — deployment linkage identifiers (org/project ids). Not
  project knowledge.
- `.claude/settings.local.json` — local harness config; could hold local
  permission rules. Filtered. `.claude/skills/**` is **kept** (documented project
  commands, non-secret).
- Binary (`.png`, …) — the 24 `ux-review` QA screenshots; no textual provenance
  value, and metadata-only means no reason to list binaries.

**Path-traversal-proofing** is closed-set membership, not string sanitization:
a path is served only if it is an exact key in `served`. A defense-in-depth guard
(reused from `sources._guard_name`) rejects obviously unsafe strings with 400
before the lookup. Size: lists are inherently bounded (19 concepts, ~180 files);
`related` capped at 25, `rationales` at 10. A `MAX_CONTENT_BYTES` cap is reserved
only if content-serving is ever approved.

Files in the allowlist but missing on disk return provenance with
`"on_disk": false` (the graph is the index; the disk may have moved on). The UI
then shows provenance but offers no "open locally" affordance.

---

## 5. Degraded-state behavior matrix

| State | Detection | API response | UI |
|---|---|---|---|
| Graph absent (hosted) | `graphify-out/graph.json` missing | `/graph/status` → `status:"missing"`; `/memory/*` → `200 {available:false, reason:"graph_absent", …empty}` | "Project memory is unavailable in this hosted demo" panel; `GraphStatusChip` quiet "Missing" |
| Graph stale | freshness check = `stale` | `/graph/status` → `status:"stale"`; `/memory/*` serve data normally | Data shown + "Memory: Stale" chip + "leads may be out of date — re-verify against the cited file" |
| Graph malformed | JSON parse / unexpected shape error caught | `/memory/*` → `200 {available:false, reason:"graph_unreadable", …empty}` (never 500) | Same unavailable panel, distinct copy: "the memory index could not be read" |
| File in graph, missing on disk | path in allowlist, not on filesystem | provenance served with `on_disk:false` | Provenance shown; "not present locally — cannot open"; no open action |
| Backend down | `fetch` throws (ApiError `unreachable`) | n/a | Existing `BackendDown` component + retry (unchanged) |

Malformed/absent both degrade like the existing `_graph_freshness()` exception
path (→ "missing"): caught, never surfaced as a 500.

---

## 6. Local vs hosted behavior

| | Local dev | Hosted (Railway image) |
|---|---|---|
| `graphify-out/` present? | Yes | **No** (`.dockerignore` excludes it; Dockerfile COPY never adds it) |
| `graph.json` / `manifest.json` / `.graphify_labels.json` | present | absent |
| `GET /api/graph/status` | fresh/stale/missing (real) | `missing` |
| `GET /api/memory/*` | real data | `available:false, reason:"graph_absent"` |
| Source/file explorer | works (local-only capability) | honestly unavailable |

No graph is shipped into Docker this arc (arc decision 4). The source/file
explorer is therefore a local/dev capability by construction; the hosted demo
demonstrates the honest unavailable states, which is itself a real, testable
behavior — not a stub.

---

## 7. UI wireframe (words) — `/memory`, within the existing design system

No redesign, no new visual language. Reuses `AppShell` (full variant), `TopBar`
(home), `LeftNav` (active `memory`), the `.placeholder` / `.card` / `.eyebrow`
patterns, `GraphStatusChip`, `.mono`, `LoadingPanel`, `BackendDown`. Everything
lives in-page on `/memory` (no new routes — approval Q7); panels expand in place.

1. **Header** (unchanged copy): eyebrow "Memory / Query Plane"; h2 "Project
   Memory"; the existing honest intro paragraph (memory/navigation surface,
   separate from the queue, returns leads to verify — never validates/completes/
   supplies a value).

2. **Status card** (`.card`): live `GraphStatusChip` (Fresh/Stale/Missing) + a
   small mono line with `built_at_commit`, node/edge/file/concept counts when
   `available` (omitted when not) + the memory-plane note. `LoadingPanel` while
   fetching; `BackendDown` on unreachable.

3. **Concept lookup** (`.card`): a list of the 19 concept chips (label +
   community). Selecting one expands a provenance panel: anchor `source_file`
   (mono, read-only), community name, and two lead lists — related files and
   related concepts — each item a click-through that opens the corresponding
   file/concept panel. A standing caption: "leads — open the cited file to verify."

4. **Source/file provenance** (`.card`): the served-allowlist files grouped by
   community (or `file_type`), as a plain scrollable list — **no search/filter
   input** (deferred to Phase 26). Selecting a file expands a provenance panel:
   `file_type`, community, node count, related files/concepts (leads),
   `local_reference` (mono, read-only, "open locally at <path>"), and an
   `on_disk:false` note when applicable. Caption: "project knowledge — not
   scientific evidence."

5. **Degraded states**: when `available:false`, sections 3–4 collapse into a
   single honest "memory unavailable" panel (hosted / malformed copy per §5);
   stale shows the advisory chip + re-verify caption above real data.

Every lead points back to a cited file — mirroring the existing screen's promise
"every lead points back to a cited file to confirm."

---

## 8. What Project Memory is NOT (verbatim-honest)

- It is **not** a validator. It never decides whether a record is valid, and its
  responses carry no pass/fail/verdict.
- It is **not** part of the export gate. Nothing it returns can authorize,
  block, or influence export, completion, or audit.
- It is **not** a source of scientific truth. Its concepts, relationships, and
  file groupings are memory-plane leads — some edges may be dangling/collapsed
  (CLAUDE.md §7). Always open the cited file to confirm.
- It is **not** a filesystem browser. It surfaces only graph-indexed files that
  pass the served allowlist; arbitrary paths are refused.
- It does **not** serve file contents. It serves provenance metadata + a
  read-only local path reference. (Cited-evidence content lives only in the
  existing governance-gated `source-preview`.)
- It does **not** expose `examples/`, secrets, deployment identifiers, local
  harness config, SDD ledgers, or binary artifacts.
- It does **not** find related *records* or judge record/experiment similarity.
- It does **not** work in the hosted demo (no graph shipped there); it says so.
- It is **not** search. Phase 24 has no search/filter input — real search is
  Phase 26.

---

## 9. Guardrails proving memory never validates

- **Structural.** The memory reader is `apps/api/isaac_api/memory.py` — outside
  the truth core, stdlib-only, read-only, no `graphify` import, no
  `isaac_records` import, and never imported by `isaac_records`. It has no code
  path that returns a verdict key.
- **Copy-level.** Every response carries `plane:"memory"` + the never-a-validator
  note; every UI surface labels the plane "memory", results "leads to verify",
  and files "project knowledge, not scientific evidence".
- **Test-level.** A dedicated invariant test (mirrors
  `tests/test_export.py::test_core_never_imports_graphify`) asserts: (a) the truth
  core never imports the memory module or graphify; (b) `memory.py` imports only
  stdlib; (c) **no** `/api/memory/*` or `/api/graph/status` response JSON contains
  any key in `{ok, valid, passed, verdict, schema, errors}`.

---

## 10. Tests & acceptance criteria (per slice, TDD-able)

Backend (pytest, `apps/api/tests/`):
- **Concepts.** `GET /api/memory/concepts` → `available:true`, exactly 19
  concepts, each with `source_file` + `on_disk` + `community_id`.
- **Concept detail.** A known concept id returns its real anchor `source_file`
  and non-empty `related`; unknown clean id → 404 `concept_not_found`.
- **Files index.** `GET /api/memory/files` includes `src/isaac_records/export.py`
  with `file_type:"code"`; excludes every filtered path (below).
- **File provenance.** `GET /api/memory/file?path=src/isaac_records/export.py` →
  `file_type:"code"`, non-empty `related`, `on_disk:true`, **no** `content`/
  `lines` key.
- **Governance / allowlist.** `/memory/files` contains **no** path under
  `examples/`, `.superpowers/`, `apps/web/.vercel/`, no `.claude/settings.local.json`,
  no `.png`. `GET /api/memory/file?path=examples/README.md` → **404
  `source_not_indexed`** even though `examples/README.md` is in the raw manifest.
  `GET /api/memory/file?path=.claude/skills/isaac-draft/SKILL.md` → 200 (kept).
- **Traversal.** `path` in `{"../schema/isaac_record_v1.json", "/etc/passwd",
  "a/b.csv"}` → 400 `unsafe_source_path`.
- **Degraded — absent.** With `graphify-out/` pointed at an empty tmp dir,
  `/memory/*` → `200 {available:false, reason:"graph_absent"}` (not 500);
  `/graph/status` → `missing`.
- **Degraded — malformed.** With a `graph.json` containing invalid JSON,
  `/memory/*` → `200 {available:false, reason:"graph_unreadable"}` (not 500).
- **Envelope/honesty.** Every memory response has `plane=="memory"`, a `note`,
  and **no** key in `{ok, valid, passed, verdict, schema, errors}`.
- **Status back-compat.** Existing `test_graph_status` still passes; additive
  fields (if adopted) are optional and null/omitted when the graph is absent.

Isolation invariant (`tests/`):
- Truth core never imports the memory module or graphify (mirror
  `test_core_never_imports_graphify`); `memory.py` imports only stdlib.

Frontend (vitest, `apps/web/src/__tests__/memory.test.tsx`):
- Renders real concept + file lists from a stubbed `available:true` response.
- Renders the "memory unavailable" panel on `available:false` (hosted/malformed).
- Renders the stale advisory on `status:"stale"`; `BackendDown` on unreachable.
- Asserts the screen has **no** search/filter input (P22 no-fake-search invariant
  holds through P24).

---

## 11. Proposed implementation slices (Sonnet 5 implements)

| Slice | Size | Scope | Files touched |
|---|---|---|---|
| **P24.1** | S | `memory.py` reader: mtime-cached stdlib loader for graph/manifest/labels; served-allowlist builder; provenance helpers. No routes. | `apps/api/isaac_api/memory.py` (new), `apps/api/tests/test_memory.py` (new) |
| **P24.2** | S | Additive `/api/graph/status` fields (commit + counts) when graph present; keep existing contract. *(May fold into P24.3 — approval Q10.)* | `apps/api/isaac_api/routes.py`, `apps/api/tests/test_api.py` |
| **P24.3** | M | Concept endpoints `GET /api/memory/concepts` + `/concepts/{id}`; envelope + degraded states. | `routes.py`, `memory.py`, `apps/api/tests/test_api.py` |
| **P24.4** | M | File-provenance endpoints `GET /api/memory/files` + `/file?path=`; allowlist gate, traversal guard, `on_disk`, related; governance tests. | `routes.py`, `memory.py`, `apps/api/tests/test_api.py` |
| **P24.5** | S | Honesty/isolation invariant tests: no validation keys in any memory response; truth core never imports memory/graphify; allowlist excludes sensitive prefixes. | `tests/test_memory_governance.py` (new) or `apps/api/tests/` |
| **P24.6** | M | Frontend: memory wire types + `api.getMemory*` client methods + `ProjectMemory.tsx` build-out (status card, concept lookup, file provenance, degraded states) in the existing design system; screen tests. | `apps/web/src/lib/types.ts`, `lib/api.ts`, `screens/ProjectMemory.tsx`, small components + `screens.css`, `__tests__/memory.test.tsx` |
| **P24.7** | S | Docs: update `docs/project-memory-map.md` (or new `docs/project-memory.md`) + mentor brief; note metadata-only + local-only + hosted-unavailable. | `docs/*` |

Each slice is independently reviewable and leaves tests green. The truth path is
never touched in any slice.

---

## 12. Approval questions (every vetoable decision)

1. **Content vs metadata.** P24 serves provenance metadata + local path
   references only — **no file content bytes** from the memory plane. Accept, or
   do you want a (separately-justified, filtered) content reader now?
2. **Allowlist filtering.** Exclude `examples/**`, `.superpowers/**`,
   `apps/web/.vercel/**`, `.claude/settings.local.json`, and binaries (`.png`);
   **keep** `.claude/skills/**`. Agree with each?
3. **Endpoint namespace.** New endpoints under `/api/memory/*` while
   `/api/graph/status` stays where it is (a slight naming split). OK, or alias
   status under `/api/memory/status`?
4. **Status additive fields.** Add `built_at_commit` + node/edge/file/concept
   counts to `/api/graph/status`, or keep it minimal (status/plane/note only)?
5. **Community names.** Include curated community names (from
   `.graphify_labels.json`, a memory-plane label file) in concept/file responses,
   clearly labeled as memory grouping — or omit them?
6. **No search in P24.** Defer all search/filter UI to Phase 26; P24's file list
   is browse-by-grouping with no input box. Agree?
7. **No new routes.** Keep everything in-page on `/memory` (expandable panels)
   rather than adding `/memory/file` deep-link sub-routes. Agree?
8. **Graph parsed in the API layer.** ~1.8 MB `graph.json` parsed lazily and
   mtime-cached in `apps/api` (local only; hosted has no graph), stdlib `json`,
   no new dependency. Acceptable?
9. **Hosted experience.** Hosted Project Memory shows honest "unavailable" for
   the whole memory surface (concepts + files + provenance), not just the status
   chip — no graph in Docker this arc. Confirm this is the intended hosted demo.
10. **Slice granularity.** Keep P24.2 (status additive) as its own slice, or fold
    it into P24.3?
