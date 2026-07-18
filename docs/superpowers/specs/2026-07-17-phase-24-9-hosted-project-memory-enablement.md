# Phase 24.9 — Hosted Project Memory Enablement (Design Spec)

**Slice:** P24.9 · **Status:** DESIGN ONLY — implementation gated on explicit user approval.
**Author:** Opus 4.8 architect · **Date:** 2026-07-17
**Planes touched by the *implemented* work (not this doc):** memory/query plane only. Truth plane is untouched (§22).

> This document is a specification. It describes interfaces, data shapes, and
> processes. It contains **no** implementation and authorizes **no** code change.
> Nothing here modifies `graphify-out/`, runs Graphify, or commits.

---

## 0. Problem statement (grounded in live facts)

Project Memory is real and correct **locally**: the deterministic, stdlib-only,
Graphify-free reader `apps/api/isaac_api/memory.py::LocalGraphArtifactSource`
parses `graphify-out/{graph.json,manifest.json,.graphify_labels.json}` and serves
metadata-only provenance through `/api/memory/*` and `/api/graph/status`
(`apps/api/isaac_api/routes.py` §14 + §16).

In the **hosted demo** it is honestly *unavailable*:

- The Railway image is built from the repo-root `Dockerfile`, whose COPY is an
  explicit allowlist (`pyproject.toml`, `src/`, `apps/api/`, `schema/`,
  `tests/fixtures/synthetic/`, `scripts/check_graphify_freshness.py`). It **never**
  copies `graphify-out/`, and `.dockerignore` lists `graphify-out` explicitly.
- So `graph.json`/`manifest.json`/`.graphify_labels.json` are all absent in the
  container. Every `/api/memory/*` returns `200 {available:false, reason:"graph_absent"}`;
  `/api/graph/status` returns `status:"missing"`.
- The hosted backend runs `mode:"synthetic-only"` and all memory endpoints are
  behind `ISAAC_UI_API_KEY` (bearer), so they 401 without the key. `GET /api/health`
  stays open for Railway health checks.

**Goal:** make hosted Project Memory *genuinely functional* — real status/counts,
real Source Index, real concept browse/detail, honest empty leads — **without**
shipping the raw `graphify-out/` directory, without loosening any P24/P24.8
governance boundary, and shaped so later institutional integration is a
provider swap, not a rewrite.

**The seam already exists.** `memory.py` was authored for exactly this: its
module docstring states a "future database source, mounted graph-snapshot volume,
hosted memory service, or login-gated institutional backend can replace/supplement
[`LocalGraphArtifactSource`] without rewriting callers," and `get_default_reader()`
already resolves `ISAAC_MEMORY_DIR` as "the mounted-volume seam." P24.9 fills that
seam with a safe hosted provider.

---

## 1. Recommended hosted-memory option (+ concur/dissent)

**Recommendation: Option A (deterministic sanitized snapshot) for the *artifact*,
delivered by Option-B-style path indirection through the existing env seam — i.e.
the hybrid the user named.**

Concretely:

- **Artifact:** a single deterministic, sanitized JSON file — `memory-snapshot.json`
  — generated *from* `graphify-out/` artifacts but containing **only** the exact
  metadata the six `MemoryReader` methods return (§3). Never the raw graph, never
  file contents, never excluded paths.
- **Consumption:** a new `SanitizedSnapshotSource` implementing the `MemoryReader`
  Protocol, selected by `get_default_reader()` via a new env var
  `ISAAC_MEMORY_SNAPSHOT` (a *file* path), sitting alongside the existing
  `ISAAC_MEMORY_DIR` (a *directory*) seam (§11).
- **Delivery for the current demo:** **commit the snapshot and Docker-COPY it**
  (Option A delivery). It is small, reviewable in PRs, versioned with the code that
  reads it, and rolls back atomically with `git revert`. The identical
  `SanitizedSnapshotSource` also reads a **Railway-volume-mounted** snapshot
  (Option B delivery) with zero code change — same env var, same file — so the
  delivery mechanism is a deployment decision, not a code decision.

**I concur with the user's preferred direction**, with one sharpening: the seam
that routes local-vs-hosted should be a **new file-path env var
(`ISAAC_MEMORY_SNAPSHOT`)**, *not* an overload of `ISAAC_MEMORY_DIR`. Reason:
`ISAAC_MEMORY_DIR` is documented and coded as a *directory of live Graphify
artifacts* consumed by `LocalGraphArtifactSource`; a sanitized single-file snapshot
is a different artifact with a different reader and different trust properties.
Keeping them as distinct, explicit vars makes the trust boundary legible in config
and prevents "is this a live graph or a sanitized snapshot?" ambiguity in ops.

**Dissent I considered and rejected:** Options C (DB) and D (hosted service) are the
*right long-term shape* but are over-engineered for a synthetic single-tenant demo
and would add auth/migration/network-failure surface with no demo payoff. They
remain the migration target (§20), and A→B→C→D all slot into the same seam.

---

## 2. Why A(+B delivery) is preferable — tradeoff table

| Dimension | **A — Committed sanitized snapshot (Docker-COPY)** | **B — Railway volume snapshot** | **C — DB-backed index** | **D — Hosted/institutional service** |
|---|---|---|---|---|
| Safety / leak surface | **Highest**: one file, human-reviewable in every PR, secret-scanned pre-write (§8) | High: same file, but not in git diff review; drift possible | Medium: schema + rows not diff-reviewed; SQL surface | Medium: depends on external operator; data leaves the repo trust boundary |
| Governance fit (metadata-only, no raw content) | **Exact**: artifact = the 6-method return shape, nothing more | Exact (same artifact) | Requires re-modeling metadata into tables; drift risk | Requires trusting external contract |
| Determinism / reproducibility | **Byte-identical** from same graph (§7) | Same generator; delivery non-deterministic (upload) | Migrations + row ordering complicate determinism | External; not reproducible from repo |
| Code/version consistency | **Atomic**: snapshot rolls back with the code that reads it (`git revert`) | Volume outlives code → skew risk (mitigated by `built_at_commit`, §13) | DB outlives code → migration skew | Fully decoupled; contract-versioning needed |
| Update workflow | Regen → scan → validate → commit → auto-deploy (§16) | Regen → scan → validate → upload to volume | Regen → migrate → load | External publish pipeline |
| Rollback | **Trivial** (`git revert` + push; both platforms converge) | Volume must be restored separately | DB restore/migration-down | Provider rollback, out of our control |
| CI enforceability | **Full**: schema-validate + determinism + secret-scan + stale-vs-commit all in CI (§9) | Partial: CI can validate the file, but not what's on the volume | Partial | Minimal |
| Operational complexity | **Lowest**: one COPY line + one env var | Medium: volume provisioning + upload step | High: DB provisioning, connection mgmt, migrations | Highest: service SLA, network, auth |
| Image size cost | Small (metadata JSON ≪ the 1.9 MB raw `graph.json`; see §3 sizing) | Zero image cost (on volume) | Zero image cost | Zero image cost |
| Demo readiness | **Now** | Now (extra ops step) | Weeks | Not feasible this arc |
| Long-term institutional fit | Transitional | Transitional | Good | **Best** |

**Verdict:** A gives the strongest safety + determinism + CI story for a synthetic
demo at the lowest operational cost, and — because consumption is env-routed through
the same `SanitizedSnapshotSource` — upgrading delivery to B (volume) or the model
to C/D later touches *only* the provider selection, not the product. That is exactly
the "swap the provider, don't rewrite the product" objective.

---

## 3. Exact sanitized artifact / data model

**Design rule (leak-minimization):** the snapshot carries **the reader's *returned*
fields, not raw graph-node fields.** The current API already strips most
node-internal fields (e.g. concept nodes carry a free-text `rationale` in
`graph.json`, but `concept()`/`concepts()` never surface it). Every field below maps
1:1 to a `MemoryReader` method return so `SanitizedSnapshotSource` consumes it
unchanged.

> **Known governance gap the hosted path MUST close (C1/M4).** Pre-computing the
> reader's *returned* shape is **not** sufficient on its own, because the live
> reader does **not** run `_is_served` on concept anchors or related-file paths:
> `concepts()`/`concept()` emit `node["source_file"]` verbatim, and `_related()`
> emits `other["source_file"]` for `related.files[]` verbatim — **neither is
> allowlist-filtered.** This is a *latent leak*: e.g. the live concept
> `examples_readme_examples_dir` has `source_file="examples/README.md"` — an
> `examples/`-prefixed path that fails `_is_served` yet is surfaced today. Current
> real-world impact is low (`examples/README.md` is the single public
> ignore-exception file), but the **principle "every emitted path passes
> `_is_served`" is violated**, and any future concept anchored under a genuinely
> sensitive `examples/` file (or `.superpowers/`, secret, etc.) would be baked into
> a committed snapshot. The generator (§6/§8) and the recommended source-fix
> (§4.2, approval Q11, slice P24.9-impl-0) therefore filter **every** emitted path,
> including concept `source_file` and `related.files[].path`, through `_is_served`.
> `files()`/`file_detail` keys are already served-only (they iterate the `served`
> set), so only the concept/related anchors need closing.

### 3.1 Top-level shape (`memory-snapshot.json`)

```jsonc
{
  "snapshot_schema_version": 1,               // integer; bumped on shape change
  "kind": "isaac-memory-snapshot",            // constant marker
  "generator": "scripts/build_memory_snapshot.py",
  "hosted": true,                             // marks a hosted snapshot → on_disk forced false (§5)

  // --- provenance / freshness (honest, derived from the source graph) ---
  "built_at_commit": "73545a9bbbb46842be656cb18a629d198418488b",  // == source graph.json.built_at_commit
  "source_graph_sha256": "<hex64>",           // sha256 of the exact source graph.json bytes (§7)
  "graph_mtime": 0.0,                          // §5/§7 — deterministic 0.0 ("no live file in this deployment"); NOT the source file mtime (nondeterministic)

  // --- overview() payload (1:1 with reader.overview() available branch) ---
  "overview": {
    "built_at_commit": "73545a9b...",
    "graph_mtime": 0.0,                         // same value as top-level graph_mtime (deterministic 0.0)
    "node_count": 2296,
    "edge_count": 3447,
    "community_count": 214,
    "concept_count": 19,
    "served_file_count": 190,                   // len(served) after §4 filtering (live value @ 73545a9b)
    "manifest_file_count": 232                  // len(manifest keys), pre-filter
  },

  // --- concepts() : sorted list, each == a concept summary ---
  "concepts": [
    { "id": "readme_two_layer_architecture",
      "label": "Two-layer architecture (draft to export to record + sidecar)",
      "community_id": "141",
      "community_name": "…curated label or null…",
      "source_file": "README.md",
      "on_disk": false }
    // … sorted by (label, id), exactly as concept_summaries.sort(...)
  ],

  // --- concept(id) : detail map (summary + related), keyed by concept id ---
  "concept_detail": {
    "readme_two_layer_architecture": {
      "id": "readme_two_layer_architecture",
      "label": "…", "community_id": "141", "community_name": "…",
      "source_file": "README.md", "on_disk": false,
      "related": {
        "files":    [ { "path": "src/isaac_records/export.py", "relation": "references", "file_type": "code" } ],
        "concepts": [ { "id": "docs_proposal_v2_official_isaac_schema", "label": "…", "relation": "references" } ]
      }
    }
    // … one entry per concept id
  },

  // --- files() : sorted list, each == a file summary (served allowlist only) ---
  "files": [
    { "path": "src/isaac_records/export.py", "file_type": "code",
      "community_id": "131", "community_name": "…",
      "node_count": 42, "on_disk": false }
    // … sorted by path, exactly as files() returns sorted(file_summaries)
  ],

  // --- file(path) : detail map keyed by served repo-relative path ---
  "file_detail": {
    "src/isaac_records/export.py": {
      "path": "src/isaac_records/export.py", "file_type": "code",
      "community_id": "131", "community_name": "…", "node_count": 42,
      "on_disk": false,
      "local_reference": "src/isaac_records/export.py",   // repo-relative, == path (§5)
      "related": { "files": [ … ], "concepts": [ … ] },
      "rationales": [ "…extracted docstring/comment summary…", … ]   // ≤ MAX_RATIONALES, served files only
    }
    // … one entry per served path
  },

  // --- served allowlist (for classify_path membership) ---
  "served": [ "AGENTS.md", "CLAUDE.md", "src/isaac_records/export.py", … ]  // sorted
}
```

### 3.2 Method-to-field mapping (the seam consumes this unchanged)

| `MemoryReader` method | Returns (available branch) | Snapshot source of truth |
|---|---|---|
| `overview()` | `{available, built_at_commit, graph_mtime, node_count, edge_count, community_count, concept_count, served_file_count, manifest_file_count}` | `overview` object (+ `available:true`) |
| `concepts()` | `list[ {id,label,community_id,community_name,source_file,on_disk} ]` sorted | `concepts` array |
| `concept(id)` | that summary + `related:{files:[{path,relation,file_type}], concepts:[{id,label,relation}]}}` or `None` | `concept_detail[id]` or `None` |
| `files()` | `list[ {path,file_type,community_id,community_name,node_count,on_disk} ]` sorted by path | `files` array |
| `file(path)` | summary + `local_reference` + `related` + `rationales` or `None` | `file_detail[path]` or `None` |
| `classify_path(path)` | `"unsafe" \| "served" \| "not_indexed"` | reuse `_is_unsafe(path)` (pure) + membership in `served` |

**Redundancy note:** `concepts`/`files` arrays are projections of the detail maps
(drop `related`/`rationales`/`local_reference`). They are materialized at generation
(not derived at read) for byte-stability and a trivial reader. A CI consistency check
asserts the projections match the maps (§9).

### 3.3 Sizing

Raw `graph.json` is ~1.9 MB and `manifest.json` ~37 KB — neither ships. The snapshot
carries only summaries + capped `related` (`MAX_RELATED=25`) + capped `rationales`
(`MAX_RATIONALES=10`) for ~190 served files + 19 concepts. Estimated **150–400 KB**
minified. Small enough to Docker-COPY and to diff-review comfortably.

---

## 4. Fields included and excluded (allow/deny, tied to real `_is_served`)

### 4.1 Allowed *paths* (served allowlist — computed exactly as `memory.py::_is_served`)

A manifest key is served **iff** it passes every current check:

- **NOT** under `EXCLUDED_PREFIXES = ("examples/", ".superpowers/", "apps/web/.vercel/")`.
- **NOT** in `EXCLUDED_EXACT = {".claude/settings.local.json"}`.
- Extension **NOT** in `BINARY_EXTS = {.png,.jpg,.jpeg,.gif,.webp,.ico,.pdf}`.
- **P24.8:** extension **NOT** in `SECRET_EXTS = {.key,.pem,.p12,.pfx,.pkcs12,.p8,.keystore,.jks}`.
- **P24.8:** basename **NOT** `.env` and **NOT** starting `.env.` (precise basename match).
- **P24.8:** basename **NOT** in `SECRET_BASENAMES = {id_rsa,id_dsa,id_ecdsa,id_ed25519,.netrc,.pgpass,.pypirc,.htpasswd,credentials,credentials.json}`.
- **P24.8:** basename **NOT** ending `.local.json`.
- **Kept:** `.claude/skills/**` (`SKILL.md` served as project-knowledge metadata only).

The generator **reuses the exact `_is_served` function** — it does not re-implement
the predicate. This guarantees the snapshot's served set is identical to what the
local API would serve, and inherits any future tightening automatically.

### 4.2 Allowed *fields* per served path / concept

Only the exact returned fields in §3.2. Specifically permitted: `path`, `file_type`,
`community_id`, `community_name` (curated memory-plane label), `node_count`,
`on_disk` (always `false`, §5), `local_reference` (repo-relative, == path), `related`
(paths/ids + `relation` + `file_type`/`label`), `rationales` (extracted
docstring/comment summaries, **served files only**, ≤10), and the concept fields
`id`/`label`/`source_file`.

### 4.2a Non-negotiable path invariant — EVERY emitted path passes `_is_served`

Because the live reader does not allowlist-filter concept anchors or related-file
paths (§3 gap box, C1/M4), the hosted path **must** enforce, without exception, that
every path-bearing value in the snapshot passes `_is_served`:

- `files[].path` and `file_detail{}` keys — *already* served-only (iterate `served`).
- `local_reference` — equals the served `path`, so already covered.
- `related.files[].path` — **must be filtered**: drop any entry whose `path` fails
  `_is_served`.
- concept `source_file` / `concept_detail[].source_file` — **must be filtered**: when
  the anchor path fails `_is_served`, the concept is still listed but its
  `source_file` is set to `null` (the anchor path is withheld, never emitted).

**Preferred resolution — fix at source in the memory plane (approval Q11,
recommended).** Apply `_is_served` inside `memory.py` (non-truth-path) so
`concepts()`, `concept()`, and `_related()` filter paths *themselves*: NULL a
concept's `source_file` when its anchor fails `_is_served`, and DROP
`related.files[]` entries that fail `_is_served`. This closes the **live** leak,
keeps **local == hosted parity** (so the §18 parity test needs no field whitelist),
and the snapshot inherits the fix for free (the generator just serializes the
already-filtered returns). The non-recommended alternative — filter only in the
generator and add a parity-test whitelist for these two fields — leaves the live
local API leaking and splits local/hosted behavior; rejected.

### 4.3 Explicitly excluded (deny list)

- **Raw file contents / bytes** — never. (Cited-evidence content stays only in the
  governance-gated `source-preview`, unchanged.)
- **Raw `graph.json` / `manifest.json` / `.graphify_labels.json`** — never shipped.
- **Concept node `rationale` free-text field** — not in the API contract; excluded.
- **Node-internal fields** not returned by the API: `_origin`, `norm_label`,
  `source_location`, `source_url`, `captured_at`, `author`, `contributor`,
  `confidence`, `confidence_score`, `context`, raw `weight` values, hyperedges.
- **Any path failing `_is_served`** (`examples/**`, `.superpowers/**`,
  `apps/web/.vercel/**`, secrets/keys, `.env*`, `*.local.json`, binaries).
- **Absolute / local-machine paths** (`/Users/...`, `/home/...`, `C:\...`, the build
  machine's repo root) — scanned for and rejected (§8).
- **Runtime records / drafts / workspace state / `records/`** — not in the graph;
  not in the snapshot.
- **Private Claude settings, SDD ledgers, credential/key material, deployment
  identifiers** — excluded by the allowlist and re-checked by the scan.

---

## 5. Local absolute paths → sanitized representation

The artifact carries **only repo-relative paths.** Two fields warrant explicit rules
for a hosted context where source files are *not on disk*:

- **`on_disk`** — locally computed by `LocalGraphArtifactSource._on_disk()` as an
  existence check under `repo_root`. In the hosted image the indexed source files are
  **not present** (the Dockerfile copies only a subset; the snapshot ships no files).
  Therefore the snapshot **bakes `on_disk: false` uniformly** at generation, and
  `SanitizedSnapshotSource` returns it verbatim — it performs **no filesystem check**
  (that would be nondeterministic and could re-introduce a path dependency). This is
  honest: "we are not asserting these files exist in this deployment."
- **`local_reference`** — locally set to the *repo-relative* `path` (not an absolute
  path). The snapshot preserves this repo-relative value unchanged. The frontend
  copy already frames it as "project knowledge, not a fetchable URL," so no UI change
  is needed. It never becomes an absolute or build-machine path.

**Invariant (scanned, §8):** no string value anywhere in the snapshot may contain an
absolute path, a `~`, a Windows drive prefix, or the generator machine's repo-root
string. `graph_mtime` is a deterministic `0.0` (not a filesystem timestamp — §7), so
it too carries no path and no machine-specific value.

---

## 6. Generation command / process (interface spec — not built here)

**Recommended interface: a standalone script `scripts/build_memory_snapshot.py`**,
peer to the existing `scripts/check_graphify_freshness.py`.

Rationale for a `scripts/` script over an `isaac` CLI subcommand: `src/isaac_records/cli.py`
is **truth-path protected** (§22); adding a subcommand there touches the truth path
for a memory-plane tool. A standalone script keeps the truth core untouched and mirrors
the established `scripts/` pattern. (Approval Q9 records this choice.)

**Interface:**

```
python scripts/build_memory_snapshot.py \
    --graph-dir graphify-out \                 # input: live Graphify artifacts dir
    --out memory-snapshot.json \               # output: sanitized snapshot
    [--repo-root .] \                           # anchors _is_served semantics (paths only)
    [--check]                                   # scan+validate only, write nothing, exit non-zero on any issue
```

- **Inputs:** `graphify-out/graph.json` (+ `manifest.json`, `.graphify_labels.json`).
  The script **imports and reuses** `apps/api/isaac_api/memory.py` — it constructs a
  `LocalGraphArtifactSource(graph-dir, repo_root)`, drives the six public methods over
  the full concept id set and full served path set, and serializes their *returned*
  values into the §3 shape. **It does not re-derive graph logic** — same code path the
  API uses, so the snapshot is guaranteed faithful to the live reader.
- **Sanitize pass:** force every `on_disk` to `false` (§5); and enforce §4.2a — every
  emitted path passes `_is_served` (NULL an excluded concept `source_file`, DROP
  excluded `related.files[]`). With the recommended source-fix (P24.9-impl-0) the
  reader already returns filtered paths, so this pass becomes a re-assertion rather
  than a mutation; without it, the generator performs the filtering itself. Either
  way, the pre-write scan (§8) hard-fails if any excluded path survives.
- **Secret/private scan (§8):** run before writing; abort on any hit.
- **Determinism (§7):** stable key ordering, sorted arrays, no wall-clock timestamps.
- **Output:** one JSON file. In `--check` mode, writes nothing and exits non-zero if
  the on-disk committed snapshot is stale, malformed, or fails the scan (CI use, §9).

The script lives in the memory/query plane and imports Graphify-free `memory.py`.
It must **not** import `isaac_records`.

---

## 7. Determinism & reproducibility requirements

Given the same source `graph.json`/`manifest.json`/`.graphify_labels.json` bytes,
the generator must produce a **byte-identical** snapshot:

- **Stable key order:** serialize with `json.dumps(..., sort_keys=True)` (or an explicit
  fixed field order) and a fixed separator/indent.
- **Sorted arrays:** `concepts` sorted by `(label, id)` (mirrors `concept_summaries.sort`);
  `files` and `served` sorted by path (mirrors `files()`); `related.files` by `(-weight, path)`
  then serialized; `related.concepts` by `(-weight, id)` — all already deterministic in the
  reader (§`_related`), so the snapshot inherits stable order.
- **No timestamps-from-nowhere:** the only time-like field is `graph_mtime`.
  **Recommendation: bake `graph_mtime = 0.0`** ("no live file in this deployment") —
  the deterministic, honest default, and the same reasoning §5 already uses to refuse
  a filesystem check for `on_disk`. **The rejected option is the source `graph.json`
  file mtime:** `graph.json` has **no internal timestamp** (its top-level keys are
  `built_at_commit`, `directed`, `graph`, `hyperedges`, `links`, `multigraph`,
  `nodes`), so its "mtime" is filesystem metadata that differs across machines and
  across every `git checkout`. Using it would violate the "byte-identical from the
  same graph bytes" requirement and break the §9.2 CI determinism check after any
  checkout. `0.0` is copied identically into both `graph_mtime` and
  `overview.graph_mtime`. (Real provenance is already carried honestly by
  `built_at_commit` + `source_graph_sha256`, which *are* stable from the graph bytes.)
- **Honest build identity:** `built_at_commit` is copied from the source
  `graph.json.built_at_commit` (the commit the graph was built at — currently
  `73545a9b…`). `source_graph_sha256` is the sha256 of the exact source `graph.json`
  bytes, so any change to the input is detectable and the snapshot is provably derived
  from a specific graph. Neither is fabricated.
- **Reproducibility check:** regenerating from the same input twice yields identical
  bytes; CI enforces this against a committed fixture graph (§9).

---

## 8. Secret / private-data scanning (pre-write gate)

The generator runs a **fail-closed** scan before writing. Any hit aborts with a
non-zero exit and writes nothing (never emit a leaking artifact).

**Reuse the P24.8 exclusion set from `memory.py`** (import the constants, don't
re-declare): `EXCLUDED_PREFIXES`, `EXCLUDED_EXACT`, `BINARY_EXTS`, `SECRET_EXTS`,
`SECRET_BASENAMES`, plus the `.env*` and `*.local.json` basename rules — applied via
the same `_is_served` function.

**Path assertions (closed-set re-check — every path-bearing value, no exceptions):**

- Every path in `served`, `files[].path`, `file_detail{}` keys, `local_reference`,
  every `related.files[].path`, **and every concept `source_file` /
  `concept_detail[].source_file`** (when non-null) **passes `_is_served`**. This is
  the explicit closure of the C1/M4 gap: the live reader does *not* filter concept
  anchors or related-file paths, so the generator asserts them here even after the
  source-fix (defense-in-depth). A `null` concept `source_file` is allowed (withheld
  excluded anchor); a *non-null excluded* anchor is a hard failure.
- No path is absolute, contains `..` as a segment, contains a backslash, or starts
  with `~` (reuse `LocalGraphArtifactSource._is_unsafe`, the staticmethod — or its
  module-scope promotion per §11/m9, so generator and reader share the identical
  guard).

**Value assertions (scan all string values, including `rationales`, `label`,
`community_name`, `relation`):**

- No occurrence of `/Users/`, `/home/`, `/root/`, a Windows drive prefix (`[A-Za-z]:\`),
  or the generator machine's resolved repo-root string.
- No private-key headers (`-----BEGIN … PRIVATE KEY-----`, `-----BEGIN OPENSSH`).
- No high-entropy/credential-shaped tokens matching common patterns (AWS `AKIA…`,
  `xoxb-`/`xoxp-` Slack, generic `sk-`/`ghp_`/bearer-length hex). This is a heuristic
  backstop; the primary control is that the reader never returns content.
- **No validation keys** anywhere: no `ok`, `valid`, `passed`, `verdict`, `schema`,
  `errors` key (§honesty invariant).

**`rationales` are the single highest-risk field** (LLM-extracted free text derived
from source comments/docstrings). Controls: they are only ever included for **served**
files (the reader already restricts this — `file_detail` only has served paths), they
are capped at `MAX_RATIONALES=10`, and they pass the full value scan above. If any
rationale trips the scan, the generator aborts. **Recommended additional control: a
per-rationale character cap** (e.g. truncate to ~280 chars) to bound how much derived
comment text is committed. Because committing this text is permanent in git history
(threat-model T1) and reviewed per §16.4, keeping each string short reduces both the
review burden and the permanence footprint. (Cap value is approval Q10.)

---

## 9. CI checks

Add to `.github/workflows/ci.yml` (presentation/tooling, not truth path). A committed
fixture graph under `tests/fixtures/` drives deterministic checks without needing a
live `graphify-out/`.

1. **Schema-validate the artifact.** Validate the committed `memory-snapshot.json`
   against a JSON Schema (or a `--check` validator in the generator) asserting the §3
   shape, `kind`/`snapshot_schema_version`, and required fields.
2. **Determinism check.** Regenerate from the committed fixture graph twice; assert
   byte-identical output (and, if the committed snapshot is fixture-derived, that it
   matches).
3. **Secret-scan.** Re-run the §8 scan over the committed snapshot as an independent CI
   gate (defense-in-depth: not only pre-write, but on every push).
4. **Stale-vs-commit check.** Assert `snapshot.built_at_commit` and
   `source_graph_sha256` are internally consistent, and enforce the chosen refresh
   policy (approval Q6): e.g. warn (or fail) if `snapshot.built_at_commit` is not an
   ancestor of `HEAD`, so a wildly stale snapshot cannot ship silently.
5. **Projection consistency.** Assert `concepts`/`files` arrays equal the detail-map
   projections (§3.2).
6. **Parity + isolation** (also unit tests, §18): a CI step runs the parity test
   (`SanitizedSnapshotSource` over a fixture snapshot == `LocalGraphArtifactSource`
   over the fixture graph) and the existing honesty-invariant test (no verdict keys;
   truth core never imports memory/graphify) is extended to cover the new module.

---

## 10. Docker / deployment changes required

**Truth-plane behavior is untouched:** `mode:"synthetic-only"`, workspace on the
Railway volume, auth via `ISAAC_UI_API_KEY`, health open — all unchanged.

**Option A delivery (recommended for the demo):**

- **Dockerfile — two placement choices (approval Q3):**
  - **(a) Under `apps/api/isaac_api/memory-snapshot.json` → ZERO Dockerfile change**
    (m10). The existing allowlist already does `COPY apps/api/ apps/api/`, so a file
    under `apps/api/` ships automatically; `.dockerignore` excludes `graphify-out`
    and `apps/web` but **not** `apps/api`. Env then points at
    `/app/apps/api/isaac_api/memory-snapshot.json` (adjust to the image WORKDIR).
  - **(b) A repo-root `memory-snapshot.json` → add exactly one COPY line**
    (`COPY memory-snapshot.json /app/memory-snapshot.json`).
  Either way, `graphify-out/` remains excluded by both the COPY allowlist and
  `.dockerignore`, and the image still contains **no** raw graph, no `examples/`, no
  `drafts/`, no `records/`.
- **Derived-artifact norm exception:** committing a `graphify-out/`-derived artifact
  is a deliberate, documented exception to the "never commit generated/derived
  artifacts" norm (CLAUDE.md §9 / global rules). It is justified because the snapshot
  is sanitized, deterministic, secret-scanned, human-reviewed, and version-locked to
  the reader — but it must be called out explicitly and is surfaced by approval Q1.
- **Env (Railway):** set `ISAAC_MEMORY_SNAPSHOT` to the chosen path. With it set,
  `get_default_reader()` returns `SanitizedSnapshotSource` (§11).
- **`railway.json`:** typically no change (env vars are set in Railway config, not the
  file). If the file pins config, add the env var there per repo convention.

**Option B delivery (drop-in alternative, no Dockerfile change):**

- Mount a Railway volume containing `memory-snapshot.json`; set
  `ISAAC_MEMORY_SNAPSHOT=/data/memory/memory-snapshot.json`. Same reader, same env var.
- Update the snapshot by replacing the file on the volume (no redeploy); accept the
  §13 skew tradeoff (volume outlives code) mitigated by `built_at_commit`.

**Frontend (Vercel):** no change. `apps/web/vercel.json` (SPA rewrite) and the
`VITE_API_BASE`/`VITE_API_KEY` build-time vars are untouched; the `/api/memory/*`
JSON contract is byte-identical, so the existing `ProjectMemory.tsx` surface just
starts receiving `available:true`.

---

## 11. Provider / data-source abstraction

**New class `SanitizedSnapshotSource` in `apps/api/isaac_api/memory.py`** (memory
plane; stdlib-only; no `isaac_records` import; no `graphify` import), implementing the
full `MemoryReader` Protocol:

```
class SanitizedSnapshotSource:   # implements MemoryReader
    def __init__(self, snapshot_path, ...): ...
    # same mtime-cache pattern as LocalGraphArtifactSource:
    #   key = mtime(snapshot_path); rebuild only on change; atomic swap.
    def overview(self)  -> dict           # snapshot["overview"] + available:true, or degraded
    def concepts(self)  -> list           # snapshot["concepts"]
    def concept(self, cid) -> Optional[dict]   # snapshot["concept_detail"].get(cid)
    def files(self)     -> list           # snapshot["files"]
    def file(self, path) -> Optional[dict]     # snapshot["file_detail"].get(path)
    def classify_path(self, path) -> str  # LocalGraphArtifactSource._is_unsafe(path) → membership in snapshot["served"]
```

- **Degradation parity (§14):** missing snapshot file → `overview() = {available:False,
  reason:"graph_absent"}`; unparseable/wrong-shape snapshot → `{available:False,
  reason:"graph_unreadable"}`. Reuse the **exact reason strings** so routes and frontend
  need zero change. Never raises; never 500s.
- **`get_default_reader()` selection** (extend the existing accessor):

  ```
  ISAAC_MEMORY_SNAPSHOT set & non-empty   → SanitizedSnapshotSource(that file)
  else ISAAC_MEMORY_DIR set & non-empty   → LocalGraphArtifactSource(that dir)      # unchanged
  else                                     → LocalGraphArtifactSource(repo/graphify-out)  # unchanged
  ```

  Keep the memoized-instance + rebuild-on-resolved-change behavior already in
  `get_default_reader()` (extend the cache key to include which source/path was chosen).
- **`ENV_MEMORY_SNAPSHOT = "ISAAC_MEMORY_SNAPSHOT"`** constant added beside
  `ENV_MEMORY_DIR`.
- **Shared unsafe-path guard (m9):** `classify_path` must use the *identical*
  traversal guard as the local reader. That guard is today
  `LocalGraphArtifactSource._is_unsafe` (a **staticmethod**, not a module-level
  function like `_is_served`). Either call it via the class, or promote `_is_unsafe`
  to module scope so `SanitizedSnapshotSource.classify_path` and the generator share
  one definition. (`_is_served` is already module-level and is shared as-is.)
- **Protocol method count (m7):** the **six data methods**
  (`overview/concepts/concept/files/file/classify_path`) are **unchanged**, so the
  `routes.py` memory handlers (§16) work verbatim against either source. If the
  recommended freshness design (§13, option B) is adopted, the `MemoryReader`
  Protocol **grows to seven methods** with an additive `status(build_commit)`,
  implemented by both sources and covered by tests (§18). If the non-recommended
  `isinstance`-branch freshness design is chosen instead, the Protocol stays at six.

This is the entire local-vs-hosted routing: one new class + one selector branch + one
env constant (+ optionally the `status()` seam method), all inside the memory plane.

---

## 12. Local vs hosted behavior (identical API contract)

| | **Local dev** | **Hosted (Railway)** |
|---|---|---|
| Env | `ISAAC_MEMORY_SNAPSHOT` unset | `ISAAC_MEMORY_SNAPSHOT=/app/memory-snapshot.json` |
| Reader | `LocalGraphArtifactSource` over live `graphify-out/` | `SanitizedSnapshotSource` over the snapshot |
| Data freshness | live graph, mtime-cached | pinned to snapshot's `built_at_commit` |
| `/api/memory/*` shape | identical | identical |
| `on_disk` | real existence check | uniformly `false` (§5) |
| Auth | disabled if `ISAAC_UI_API_KEY` unset | bearer-gated (401 without key) |

The response JSON is byte-shape-identical between planes. The only observable
differences are `on_disk` (real vs uniformly false) and freshness semantics (§13) —
both honest and both already handled by the frontend.

---

## 13. Freshness & commit/version compatibility

- **Embed `built_at_commit`** (from source `graph.json`) in the snapshot; the backend
  build commit is read at runtime by `routes.py::_build_commit()` (L92) which returns
  `ISAAC_BUILD_COMMIT` → `RAILWAY_GIT_COMMIT_SHA` → **`None`** (never guessed).
- **Null-commit is the common case, not an error (M3).** `docs/deployment.md` states
  the build commit is often `null` at runtime and that "that is the honest state." A
  naive `snapshot.built_at_commit == build_commit` therefore **lies**: it reports
  chronic `stale` whenever the build commit is null (a real SHA never equals `null`),
  and would fabricate `fresh` if it ever compared `null == null`. **Required rule:**
  when **either** commit is null/unknown, report a neutral honest **`"unknown"`**
  freshness (never `fresh`, never `stale`); only compare two known SHAs into
  `fresh`/`stale`. `missing` remains the value when the snapshot is unavailable.
- **`/api/graph/status` in snapshot mode:** `fresh` iff both commits are known and
  equal; `stale` iff both known and differ; `"unknown"` iff either is null;
  `missing` iff the snapshot is unavailable. This avoids the local-only source-scan
  path (`scripts/check_graphify_freshness.py`), which needs the full repo tree the
  image does not contain.
- **Implementation choice (approval Q7):** (A) the `graph_status` handler branches on
  reader type, or (B, **recommended**) add a `status(build_commit)` method to the
  `MemoryReader` seam, implemented by both sources (local delegates to the existing
  `_graph_freshness`; snapshot does the null-safe commit comparison above). B is safer
  for a concrete reason (m8): the current handler reaches `reader.artifacts_dir`
  (`routes.py` L561) to anchor `_graph_freshness` — an attribute
  `SanitizedSnapshotSource` does **not** have. Moving freshness behind a `status()`
  method removes that concrete-attribute reach, keeps the decision inside the seam,
  and preserves the single-source guarantee (the handler can never emit
  `status:"missing"` alongside populated counts, since both come from the one
  resolved reader). Adopting B grows the Protocol to seven methods (m7, §11). Either
  way, the additive count fields come from `overview()` unchanged.
- **Skew handling:** in Option A (Docker-copy) the snapshot rolls with the code (no
  skew). In Option B (volume) the snapshot can outlive code; when both commits are
  known, `built_at_commit` surfaces the skew as an honest `stale`, and when the build
  commit is null it surfaces as honest `"unknown"` — never silent wrongness.

---

## 14. Stale / malformed / missing behavior

Reuse the existing honest-degradation contract **verbatim** — no new states, no
fabrication, never a 500:

| Condition | `overview()` result | Effect on `/api/memory/*` | `/api/graph/status` |
|---|---|---|---|
| Snapshot file absent | `{available:False, reason:"graph_absent"}` | `available:false`, empty data (`concepts:[]`/`files:[]`/`file:null`) | `missing` |
| Snapshot unparseable / wrong shape / type-corrupt | `{available:False, reason:"graph_unreadable"}` | same empty-data envelope | `missing` |
| Snapshot present, both commits known & differ | `{available:True, …}` | real data | `stale` |
| Snapshot present, both commits known & equal | `{available:True, …}` | real data | `fresh` |
| Snapshot present, build commit `null` (or snapshot commit null) | `{available:True, …}` | real data | `"unknown"` (M3 — never `fresh`/`stale`) |
| `classify_path` on `..`/absolute/`~`/backslash | (availability-independent) | `400 unsafe_source_path` | n/a |
| `classify_path` on non-served path (available) | — | `404 source_not_indexed` | n/a |

The route handlers in `routes.py` §16 already branch on `overview["available"]`,
`overview["reason"]`, and `classify_path()` — so they need **no change** for these
states; they just receive them from `SanitizedSnapshotSource`. Mirror
`LocalGraphArtifactSource._build`'s blanket never-raise guard: any error during snapshot
parse/derive degrades to `graph_unreadable`, never propagates.

---

## 15. Rollback process

- **Option A (recommended):** snapshot + code are one commit-set. **`git revert` the
  offending commit and push** — Railway and Vercel converge on the known-good code and
  the matching snapshot atomically. Platform-level Instant Rollback (Vercel) /
  redeploy-previous (Railway) are the fast stopgap; a failed Railway build/health-check
  never replaces the running healthy backend, so a broken snapshot push degrades to
  "old backend keeps serving," not downtime.
- **Seam safety net:** if a rolled-back or malformed snapshot slips through, the reader
  degrades to `graph_absent`/`graph_unreadable` (honest "unavailable"), never a crash.
- **Option B (volume):** the volume is outside git rollbacks — after any code rollback,
  restore/replace the snapshot on the volume to the matching `built_at_commit`, or the
  status will honestly read `stale`. Env vars (`ISAAC_MEMORY_SNAPSHOT`, keys, CORS) do
  not roll back with code; confirm they still match after any rollback.

---

## 16. Snapshot update process

1. Rebuild the graph locally: `graphify update .` (memory plane; never committed —
   `graphify-out/` is gitignored).
2. Regenerate: `python scripts/build_memory_snapshot.py --graph-dir graphify-out --out memory-snapshot.json`.
3. The generator runs the §8 secret-scan and §7 determinism serialization; it aborts on
   any leak.
4. Review the `git diff` of `memory-snapshot.json` — and, specifically, **read every
   `rationales[]` string in the diff** (they are LLM-derived comment/docstring text
   being committed permanently to git history; §8 length cap keeps this tractable).
   Do not rubber-stamp the diff as "just metadata": the rationale strings are the one
   free-text surface and the one that warrants a line-by-line read (threat-model T1).
5. Run CI checks locally (`--check` mode) and the parity test.
6. Commit the snapshot (Option A) — auto-deploys to Railway + Vercel — or upload to the
   volume (Option B).
7. Verify on the hosted demo (§19).

**Cadence (approval Q6):** recommend regenerating whenever the graph materially changes
(new modules/docs) and at minimum keeping `built_at_commit` within a bounded distance of
`HEAD` so status doesn't chronically read `stale`. A future CI job could regenerate on a
schedule, but that is out of P24.9 scope.

---

## 17. Authentication implications

- Memory endpoints **stay behind `ISAAC_UI_API_KEY`** exactly as today — `_OPEN_PATHS`
  is not modified; only `GET /api/health` and CORS `OPTIONS` remain open. Hosted memory
  returns 401 without the bearer key. (Approval Q5 confirms we keep this.)
- The snapshot **carries no secrets** (§8), so even if the artifact leaked it would
  expose only already-public-shaped project metadata (schema names, code file names,
  community groupings) — the same metadata the local API returns to an authorized
  caller. The API key remains "as secret as frontend access" (nuisance-abuse
  prevention for a synthetic demo), unchanged from Phase 20's honest scope.
- **Future institutional posture (§20):** when memory moves to a login-gated
  institutional API (Option D), auth graduates from a shared bearer to real per-user
  auth *at the provider*, behind the same seam — no change to the truth plane.

---

## 18. Tests

**Backend (new/extended, under `apps/api/tests/`):**

- **Protocol parity:** build a snapshot from the committed **fixture graph** via the
  generator, then assert `SanitizedSnapshotSource(snapshot)` returns results **equal**
  to `LocalGraphArtifactSource(fixture graph)` for `overview` (modulo `on_disk`,
  which is forced false and asserted false in the snapshot), `concepts`, every
  `concept(id)`, `files`, every `file(path)`, and `classify_path` on
  served/not-indexed/unsafe inputs. **With the recommended source-fix (P24.9-impl-0),
  both sides apply `_is_served` to concept/related anchors identically, so parity
  holds with NO field whitelist** (the non-recommended generator-only filtering would
  force a whitelist and split behavior).
- **Path-filter hardening (P24.9-impl-0, C1/M4):** using a fixture graph containing a
  concept anchored to an excluded path (e.g. `examples/README.md`) and a related-file
  edge to an excluded path, assert the **live** `LocalGraphArtifactSource`:
  (a) still *lists* the concept, (b) returns its `source_file` as `null`, and
  (c) omits the excluded `related.files[]` entry. A regression assertion:
  `examples/README.md` (and any `_is_served`-failing path) **never** appears as any
  concept `source_file` or any related path in any `/api/memory/*` response, local or
  hosted.
- **Degradation:** missing snapshot → `graph_absent`; truncated/invalid-JSON /
  wrong-shape / type-corrupt snapshot → `graph_unreadable`; never raises; routes return
  the empty-data envelope, never 500.
- **Secret-absence:** assert no served path fails `_is_served`; no absolute/local path
  in any value; no private-key/token patterns; no `{ok,valid,passed,verdict,schema,errors}`
  key anywhere in any `/api/memory/*` or `/api/graph/status` response served from the
  snapshot.
- **Determinism:** generator produces byte-identical output twice from the fixture graph.
- **`classify_path` safety:** `..`-segment, absolute, `~`, backslash → `unsafe` even
  when the snapshot is absent (availability-independent guard preserved).
- **Freshness:** status `fresh`/`stale`/`missing` by `built_at_commit` vs build commit.
- **Isolation invariant (extend existing):** the truth core never imports `memory`/
  `graphify`; `memory.py` (incl. `SanitizedSnapshotSource`) imports only stdlib;
  `scripts/build_memory_snapshot.py` imports `memory` but never `isaac_records`.

**Frontend (`apps/web`):** the response *shape* is unchanged, but the path-filter
hardening introduces one new **possible value**: a concept's `source_file` may now be
`null` (excluded anchor withheld). `ConceptLookupDetail` in
`apps/web/src/screens/ProjectMemory.tsx` currently renders `{concept.source_file}`
**unconditionally** (L603, inside the "anchor source" row). Specify the honest empty
rendering: when `source_file` is `null`/empty, render an explicit
"anchor withheld (excluded source)" line (or omit the anchor row) instead of an empty
`<span className="mono">`. Add a screen test for the null-anchor case. Otherwise the
existing `__tests__/memory.test.tsx` passes without change; add one **hosted-parity**
assertion: a mocked `available:true` memory response renders real status/counts,
Source Index, and concept detail — proving the hosted path lights up the same UI as
local.

**Generator tests:** scan catches a planted secret / absolute path / excluded path and
aborts non-zero; `--check` fails on a stale/malformed committed snapshot.

---

## 19. Browser verification (hosted demo, once wired)

Manual QA on the deployed Vercel frontend against the Railway backend (with the bearer
key), documented as a checklist (no automated hosted browser test this arc):

1. `/api/graph/status` (authorized) returns `status:"fresh"` (or honest `stale`) with
   real `node_count`/`edge_count`/`concept_count`/`file_count` — not `missing`.
2. **Project Memory** page shows the status card with real counts and the memory-plane
   note ("leads to verify — never a validation verdict").
3. **Source Index** lists served files (allowlist) with `file_type`/community grouping;
   `examples/**`, `.superpowers/**`, `apps/web/.vercel/**`, `.env*`, secrets, binaries
   are **absent**.
4. **Concept browse** lists the 19 concepts; opening one shows provenance + related
   files/concepts (honest empty leads where none exist), no verdict/validation language.
5. **File detail** shows metadata + capped rationales + related; `on_disk` renders as
   the honest "not in this deployment" state; no file contents are fetchable.
6. **Leak spot-check:** no absolute/local paths, no secrets, no `records/`/`drafts/`
   data, no `ok/valid/verdict` keys in any network response (DevTools).
7. **Degradation:** temporarily point `ISAAC_MEMORY_SNAPSHOT` at a missing/garbage file
   → UI shows honest "unavailable," not an error page.

---

## 20. Migration path to institutional servers / databases / login

All four options are **the same seam** — a `MemoryReader` selected by
`get_default_reader()`. Each upgrade replaces the provider, not the product:

- **A → B:** same `SanitizedSnapshotSource`, same `ISAAC_MEMORY_SNAPSHOT`; point it at a
  volume-mounted file instead of an image-copied one. **Zero code change.**
- **B → C (DB-backed):** add a `DatabaseMemorySource(MemoryReader)` that reads the same
  metadata model from tables; select it via a `ISAAC_MEMORY_DSN` env var. Routes,
  frontend, and the six-method contract are unchanged; the snapshot JSON becomes the DB
  seed/migration source. Governance boundaries (metadata-only, no verdict keys) carry
  over as table constraints + the same isolation test.
- **C/B → D (hosted/institutional service):** add a `HostedMemorySource(MemoryReader)`
  that calls an external/institution-hosted API behind the seam; network failures
  degrade to `graph_unreadable`/`graph_absent` (honest unavailable), never 500. Auth
  graduates to real per-user login *at the provider*. The truth plane never learns any
  of this happened.

Because §14 degradation and §9/§18 governance tests are written against the
**Protocol**, not against `LocalGraphArtifactSource`, they validate every future
provider for free.

---

## 21. Files likely touched (implementation, when approved)

- `scripts/build_memory_snapshot.py` — **new** generator (imports `memory.py`; scan +
  determinism).
- `apps/api/isaac_api/memory.py` — (P24.9-impl-0) `_is_served` filtering of concept
  `source_file` (NULL when excluded) and `related.files[]` (drop excluded) in
  `concepts()`/`concept()`/`_related()`; optional `_is_unsafe` module-scope promotion
  (m9). Then **new** `SanitizedSnapshotSource`, `ENV_MEMORY_SNAPSHOT`, extended
  `get_default_reader()` selection; optional `status(build_commit)` seam method (§13).
- `apps/api/isaac_api/routes.py` — **only** the `graph_status` freshness branch (§13);
  memory handlers `/api/memory/*` unchanged.
- `memory-snapshot.json` — **new** committed artifact (Option A) at the agreed location
  (approval Q3).
- `Dockerfile` — **+1 COPY** line (Option A only).
- `railway.json` — env note if the repo pins config there (usually unchanged).
- `.github/workflows/ci.yml` — schema-validate, determinism, secret-scan, stale-vs-commit,
  parity/isolation steps.
- `apps/api/tests/` — parity, degradation, secret-absence, determinism, freshness tests;
  generator tests.
- `apps/web/src/screens/ProjectMemory.tsx` — `ConceptLookupDetail` (L~603) honest
  rendering when concept `source_file` is `null` (excluded anchor withheld).
- `apps/web/src/screens/__tests__/memory.test.tsx` — one hosted-parity assertion + a
  null-anchor rendering test (response shape otherwise unchanged).
- Docs: `docs/deployment.md`, `docs/project-memory*.md` / mentor brief, and this spec's
  status.
- `tests/fixtures/` — a small committed fixture graph for deterministic CI.

---

## 22. Files that MUST NOT be touched (truth path)

The deterministic, Graphify-free truth core stays exactly as is:

- `schema/isaac_record_v1.json`
- `src/isaac_records/official.py`
- `src/isaac_records/draft_validator.py`
- `src/isaac_records/export.py`
- `src/isaac_records/audit.py`
- `src/isaac_records/cli.py` (truth logic — this is *why* the generator is a
  `scripts/` script, not a CLI subcommand)
- their tests (`tests/test_official.py`, `tests/test_export.py`, etc.)

Invariants preserved: the truth core imports **no** memory/graphify module; `memory.py`
and the new source remain stdlib-only and `isaac_records`-free; `graphify-out/` stays
gitignored and out of the image; nothing in P24.9 can authorize, block, or influence
validation/export/audit.

---

## 23. Bite-sized implementation slices

Each is small, independently reviewable, testable, committable, and leaves the truth
path untouched.

- **P24.9-impl-0 — Memory-plane path-filter hardening (pre-req, C1/M4).**
  In `apps/api/isaac_api/memory.py` (memory plane, non-truth-path), apply `_is_served`
  to concept anchors and related-file paths: `concepts()`/`concept()` NULL a concept's
  `source_file` when its anchor fails `_is_served`; `_related()` drops
  `related.files[]` entries that fail `_is_served`. *Acceptance:* excluded anchors are
  no longer surfaced by the **live** API; a new test asserts `examples/README.md`
  (and any `_is_served`-failing path) never appears as any concept `source_file` or
  related path; the concept is still *listed* with `source_file:null`; all existing
  memory tests pass; local == hosted parity preserved. Optionally promote `_is_unsafe`
  to module scope (m9). No snapshot code yet.

- **P24.9-impl-1 — Snapshot data model + generator + scan.**
  New `scripts/build_memory_snapshot.py` + a committed fixture graph + generator unit
  tests. *Acceptance:* generates the §3 shape from the fixture graph; `--check` and
  secret-scan work; determinism (byte-identical twice, incl. `graph_mtime:0.0`); scan
  aborts on planted secret/absolute/excluded path (incl. an excluded concept/related
  anchor); no API wiring yet; no real snapshot committed.

- **P24.9-impl-2 — `SanitizedSnapshotSource` + seam selection.**
  New class in `memory.py`, `ENV_MEMORY_SNAPSHOT`, extended `get_default_reader()`.
  *Acceptance:* Protocol parity with `LocalGraphArtifactSource` over the fixture graph
  (all six methods, `on_disk` forced false); degradation → `graph_absent`/
  `graph_unreadable`; never raises; `classify_path` safety preserved; isolation test
  extended; `/api/memory/*` handlers work unchanged against the snapshot.

- **P24.9-impl-3 — Snapshot-aware `/api/graph/status`.**
  Freshness by `built_at_commit` vs build commit (via the §13 chosen mechanism).
  *Acceptance:* `fresh`/`stale`/`missing` correct; additive counts from `overview()`;
  existing `test_graph_status` still passes for the local path; memory handlers
  untouched.

- **P24.9-impl-4 — Real snapshot + CI gates.**
  Generate + commit the real `memory-snapshot.json` from a fresh local graph; add CI
  checks (schema-validate, determinism, secret-scan, stale-vs-commit, projection
  consistency). *Acceptance:* CI green; committed snapshot passes scan; parity test
  green in CI.

- **P24.9-impl-5 — Deploy wiring + docs + browser QA.**
  Dockerfile COPY (Option A) or volume wiring (Option B) + `ISAAC_MEMORY_SNAPSHOT` env;
  update `docs/deployment.md` + project-memory doc + mentor brief; run the §19 hosted
  checklist. *Acceptance:* hosted `/api/graph/status` reports real counts; Project
  Memory surfaces work with honest empty leads; leak spot-check clean; truth-plane
  behavior (`synthetic-only`, auth, health) unchanged.

---

## 24. Approval questions (decide before implementation)

1. **Commit vs generate-at-release.** Commit `memory-snapshot.json` (Option A,
   recommended — reviewable, atomic rollback) or generate at release/upload to a volume?
   Committing is a **deliberate exception** to the "never commit derived artifacts"
   norm (§10) — confirm you accept that exception for this sanitized/deterministic
   artifact.
2. **Delivery mechanism.** Docker-COPY (A) vs Railway volume (B) vs A-generation +
   B-delivery hybrid? (Recommendation: A now; the same reader supports B later.)
3. **Artifact location + name.** Repo-root `memory-snapshot.json`, or
   `apps/api/isaac_api/memory-snapshot.json`, or a `memory/` dir? (Affects the COPY path
   and env value.)
4. **Env var.** New file var `ISAAC_MEMORY_SNAPSHOT` (recommended) vs overloading the
   existing directory var `ISAAC_MEMORY_DIR`?
5. **Auth.** Keep memory endpoints behind `ISAAC_UI_API_KEY` exactly as today
   (recommended). Confirm — no public unauthenticated memory.
6. **Refresh cadence.** How current must the snapshot be? (Every deploy from HEAD? Manual
   on material change? CI-enforced `built_at_commit` ancestor-of-HEAD bound?)
7. **Freshness implementation.** `graph_status` `isinstance` branch (A) vs new
   `status()` method on the `MemoryReader` seam (B, recommended)?
8. **`graph_mtime` for hosted.** Bake `graph_mtime = 0.0` (**recommended** —
   deterministic, honest "no live file"). The source-file-mtime option is **rejected**:
   `graph.json` has no internal timestamp, so file mtime is nondeterministic across
   machines/checkouts and would break the CI determinism check (§7). Confirm `0.0`.
9. **Generator form.** `scripts/build_memory_snapshot.py` (recommended — keeps truth-path
   `cli.py` untouched) vs an `isaac` CLI subcommand?
10. **Free-text surfaces (labels + rationales).** Include curated `community_name`
    labels (memory-plane grouping, parity with local)? AND — for the `rationales[]`
    free text — accept committing LLM-derived comment/docstring text permanently to git
    (threat-model T1), and what **per-rationale length cap** (recommended ~280 chars,
    §8) do you want, if any?
11. **Path-leak fix location (C1/M4).** Fix the concept/related `_is_served` leak **at
    source in `memory.py`** (recommended — closes the live leak, keeps local==hosted
    parity, no parity-test whitelist) via slice P24.9-impl-0, or filter **only in the
    generator** and whitelist those fields in the parity test (non-recommended — leaves
    the live local API leaking)?

---

## Security & governance threat model

For each risk: what could leak, and the control that prevents it.

| # | Risk (what could leak) | Control(s) |
|---|---|---|
| T1 | **Raw source-file contents** ship in the snapshot; **and** the `rationales[]` LLM-derived comment/docstring text is committed **permanently to git history** (Option A) — unremovable without history rewrite | The snapshot carries only the reader's *returned* metadata fields (§3.2); the reader has no content path. `rationales` are the only derived text: served-files-only, capped at `MAX_RATIONALES=10`, recommended per-string length cap (§8, Q10), value-scanned (§8), and **read line-by-line in every snapshot diff** (§16.4). Accepting git permanence is an explicit approval decision (Q10). |
| T2 | **Excluded/sensitive paths** appear — including via the **latent live-reader gap (C1/M4):** `concepts()`/`concept()`/`_related()` do **not** run `_is_served` on concept `source_file` or `related.files[].path`, so today the live API already surfaces `examples/README.md` as a concept anchor | The hosted path **closes** the gap: recommended source-fix (P24.9-impl-0) NULLs excluded concept anchors and drops excluded related paths in `memory.py`; the generator reuses the exact `_is_served` predicate (P24.8 set) and §8 re-asserts **every** path-bearing value (files, `local_reference`, related paths, **and concept `source_file`**) passes `_is_served`; a regression test asserts `examples/README.md` never appears as any anchor/related path; CI secret-scan re-checks on every push. |
| T3 | **Secrets / private keys / credentials** embedded in `rationales`/labels | §8 value-scan for private-key headers, credential-token patterns, and the P24.8 basenames; fail-closed (abort, write nothing) on any hit; CI re-scan. |
| T4 | **Absolute / local-machine paths** leak the build environment | §5 mandates repo-relative-only; `on_disk` forced false (no fs check); §8 scans for `/Users/`, `/home/`, drive prefixes, repo-root string; `local_reference` stays repo-relative. |
| T5 | **Path-traversal / arbitrary-file browse** via `/api/memory/file` | `classify_path` reuses `_is_unsafe` (rejects `..`-segment/absolute/`~`/backslash) + closed-set membership in the baked `served` list; unsafe guard is availability-independent. |
| T6 | **Memory masquerading as validation** (a verdict key slips in) | Snapshot mirrors the reader's fields only; §8 + §9 + §18 assert no `{ok,valid,passed,verdict,schema,errors}` key in any memory response; `plane:"memory"` + never-a-validator note on every response. |
| T7 | **Graphify creeps into the truth core** via the new tooling | Generator is a `scripts/` script (not `cli.py`); `memory.py`/`SanitizedSnapshotSource` stay stdlib-only and `isaac_records`-free; the isolation invariant test is extended to cover the new module (§18). |
| T8 | **Stale snapshot silently serves wrong metadata** | `built_at_commit` + `source_graph_sha256` embedded; `/api/graph/status` reports honest `fresh`/`stale`; CI stale-vs-commit gate; Option A rolls snapshot with code atomically. |
| T9 | **Unauthenticated exposure** of the memory surface | Endpoints stay behind `ISAAC_UI_API_KEY` (401 without key); `_OPEN_PATHS` unmodified; snapshot carries no secrets so worst-case exposure is already-authorized-shaped public metadata. |
| T10 | **Malformed snapshot crashes the API (500)** | `SanitizedSnapshotSource` mirrors `_build`'s blanket never-raise guard → degrades to `graph_absent`/`graph_unreadable`; routes already handle the empty-data envelope; never 500. |

---

## Governance invariants (must hold for the implemented work)

1. All hosted memory responses come from a **real, approved, secret-scanned artifact**
   through the `MemoryReader` seam. **No fabricated memory results, ever.**
2. **No raw file contents.** Metadata + repo-relative references only.
3. **No arbitrary path browsing.** Closed served allowlist + `_is_unsafe` guard.
4. **No related-*records* claims.** Only file/concept leads (relationships), never
   record/experiment similarity or judgment.
5. **No validation authority / verdict keys.** Memory never marks anything valid/invalid
   and never influences export/audit/completion.
6. **No Graphify dependency in the deterministic truth core.** The memory plane stays
   stdlib-only and truth-isolated; `graphify-out/` never enters the image.
