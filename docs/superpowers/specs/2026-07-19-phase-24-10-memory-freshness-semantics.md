# Phase 24.10 — Memory Freshness Semantics (As-Built Record)

**Slice:** P24.10 · **Status:** Implemented — release/regen pending (Slice 8, below,
has not run: the committed sanitized snapshot has not yet been regenerated to embed
`memory_inputs`, and the work is not yet pushed to `origin/main`).
**Author:** Claude (Sonnet 5), documentation slice, from the as-built P24.10 commits.
**Date:** 2026-07-19
**Baseline commit:** `4f502c1` (P24.9-impl-6, `origin/main` HEAD at the time P24.10 started).
**Related:** [`2026-07-17-phase-24-9-hosted-project-memory-enablement.md`](2026-07-17-phase-24-9-hosted-project-memory-enablement.md)
(the design spec P24.10 extends — see its §13 "Freshness & commit/version
compatibility" for the mechanism this phase replaces); implementation commits
`fe835f7`, `517da3e`, `9e2b42a`, `e835677`, `7b96b60` (local `main`, ahead of
`origin/main`, not yet pushed as of this writing).
**Planes touched:** memory/query plane only —
`apps/api/isaac_api/memory.py`, `apps/api/isaac_api/routes.py`,
`scripts/build_memory_snapshot.py`, `apps/api/tests/*` (memory/snapshot suites),
`apps/web/src/*` (Project Memory screen + status chip). The deterministic truth
plane (`schema/`, `src/isaac_records/`) is untouched — see §7.

> This document records what was **actually implemented**, not a design proposal.
> It supersedes P24.9 spec §13's freshness mechanism (build-commit-vs-snapshot-commit
> comparison); every other part of the P24.9 spec (the snapshot artifact, the
> `SanitizedSnapshotSource` provider, delivery, governance) is unchanged and still
> the authority for those topics.

---

## 0. Problem statement

P24.9 gave `/api/graph/status` one conflated `status` field —
`fresh` / `stale` / `unknown` / `missing` — computed by comparing the snapshot's
`built_at_commit` against the deployed app's build commit
(`RAILWAY_GIT_COMMIT_SHA` / `ISAAC_BUILD_COMMIT`, read by `routes.py::_build_commit()`).

This was **honest but misleading in practice**: on the hosted demo, the app
redeploys on every push to `main`, so the deployed app-HEAD commit almost always
moves ahead of whatever commit the snapshot was built at — even when the
snapshot's *content* (the sanitization policy, the served files it embeds) had
not changed at all. The result was a chronic, false **"Stale"** reading that told
the operator nothing provable about the artifact itself, only that unrelated code
had shipped since the snapshot was generated.

The deeper issue: app-HEAD is not a property of the *snapshot's correctness* — it
is a property of *when the backend last redeployed*. Conflating the two into one
`status` value made a single field answer an unanswerable question ("is this
snapshot still good?") with an unrelated signal ("has anything shipped since?").

## 1. The redesign — separated, individually provable axes

P24.10 removes app-HEAD from all freshness computation and replaces the one
conflated field with independent axes, each provable (or honestly `"unknown"`)
on its own terms:

| Axis | Values | What it proves | Computed by |
|---|---|---|---|
| **availability** | `available` / `unavailable` | Is a reader resolvable and does it have data at all | `reader.status()["available"]` (unchanged semantics) |
| **integrity** | `verified` / `malformed` / `unsupported` / `unknown` | Is the artifact well-formed and schema-supported — **not** a check of its contents | `reader.status()["integrity"]` |
| **memory_policy** | `current` / `stale` / `unknown` | Does the shipped sanitization/exclusion policy (+ versions) match what the snapshot was built under | runtime recompute of `compute_memory_policy_fingerprint()` vs. the snapshot's embedded `policy_fingerprint`; Graphify-free, stdlib-only |
| **indexed_sources** | `current` / `stale` / `unknown` | Have the *served files already embedded in the snapshot* drifted since the snapshot was built | **CI-only.** A test-suite gate recomputes the manifest over exactly the files the snapshot already lists and fails the build on any mismatch. The hosted runtime never recomputes this (the served files are not shipped) and can only report `current`/`unknown`, never `stale`, at runtime. |

`deployed_app_commit` (`_build_commit()`) still appears in the response, but
**only as version metadata** — it is read for operator convenience ("what commit
is this backend running") and is never an input to `availability`, `integrity`,
`memory_policy`, or `indexed_sources`. No code path compares it to anything.

**Removed:** the old top-level `status` field (`fresh`/`stale`/`unknown`/`missing`)
and the top-level `source_graph_sha256` field. Neither exists in the new response
body.

**Documented limitation (stated verbatim in the code, three times, in
`apps/api/tests/test_committed_snapshot.py`):**

> Newly-added indexable files are not detected without a Graphify refresh.

The CI gate can only prove drift in files the snapshot *already* embeds. A file
added to the repo after the snapshot was last generated is invisible to the gate
until someone reruns Graphify and regenerates the snapshot — the gate recomputes
over the manifest's own path set, not the current repo's full indexable set.

## 2. `memory_inputs` — the embedded fingerprint block

`scripts/build_memory_snapshot.py` now embeds an additive, optional top-level
`memory_inputs` object in every generated `memory-snapshot.json` (Slice 2, commit
`517da3e`), built from pure primitives added to `apps/api/isaac_api/memory.py`
(Slice 1, commit `fe835f7`):

```jsonc
"memory_inputs": {
  "policy_fingerprint": "<sha256 hex>",
  "policy_version": 1,
  "projection_version": 1,
  "fingerprint_algo_version": 1,
  "served_manifest_fingerprint": "<sha256 hex>",
  "served_file_count": 190,
  "served_content_manifest": [
    { "path": "README.md", "sha256": "<sha256 hex>" }
    // … one entry per served file already in the snapshot, sorted by path
  ]
}
```

`memory_inputs` is **optional** for shape validity — a pre-P24.10 committed
snapshot (one generated before this phase, lacking the block entirely) still
validates and still serves; every freshness value degrades to `"unknown"`
(§1) rather than failing.

### Primitives (`apps/api/isaac_api/memory.py`, stdlib-only, Graphify-free)

- **`compute_memory_policy_fingerprint() -> str`** — sha256 hex digest of a
  canonical (`sort_keys=True`, fixed separators) JSON payload of the exclusion/
  projection/algorithm policy actually shipped in this build: `schema_version`,
  `policy_version`, `projection_version`, `algo_version`, sorted
  `excluded_prefixes` / `excluded_exact` / `binary_exts` / `secret_exts` /
  `secret_basenames`, and `max_rationale_chars`. Recomputable at runtime from
  constants already in `memory.py` — no filesystem access.
- **`compute_served_content_manifest(served_paths, repo_root) -> list[dict]`** —
  for each path: enforces the path-safety guard (`_is_unsafe`), the served
  allowlist (`_is_served`), and that it resolves strictly inside `repo_root`;
  reads the raw bytes and sha256-hexes them. Returns `[{"path", "sha256"}, ...]`
  sorted by path. Raises `ValueError` on any unsafe/unserved/missing path — the
  generator, not the runtime, calls this (it needs the files on disk).
- **`compute_served_manifest_fingerprint(manifest) -> str`** — an
  order-independent aggregate sha256 over the path-sorted
  `"path\0sha256"` pairs of a served-content manifest. Changes iff any path or
  any digest changes.

### Reader `status()` (Slice 3, commit `9e2b42a`)

Both `LocalGraphArtifactSource` and `SanitizedSnapshotSource` implement a
`status()` method added to the `MemoryReader` Protocol (it takes no
`build_commit` argument — a deliberate change from the P24.9 spec's §13(B)
proposal, which still threaded a build commit through). The shared helper
`_memory_input_freshness(available, memory_inputs)` derives `policy_consistency`
and `indexed_sources` **only** from a snapshot's embedded `memory_inputs`,
never from any deployed-commit input:

- `policy_consistency` = `"current"` iff the runtime-recomputed policy
  fingerprint equals the embedded one; `"stale"` iff both present and differ;
  `"unknown"` otherwise.
- `indexed_sources` = `"current"` iff `memory_inputs` is present and internally
  consistent (the recomputed aggregate over its own embedded
  `served_content_manifest` equals its own embedded
  `served_manifest_fingerprint`); otherwise `"unknown"` — **never** `"stale"` at
  runtime, because the hosted runtime does not ship the served files and cannot
  recompute their digests. Actual content drift is CI's authority alone (§3).

A live local graph (`LocalGraphArtifactSource`, no embedded `memory_inputs`)
passes `memory_inputs=None` and gets `policy_consistency="unknown"`,
`indexed_sources="unknown"`, both fingerprints `None` — honest: it has no
fingerprint reference to prove against. (Live-graph-vs-repo drift is a *different*,
still-valid concept owned by `scripts/check_graphify_freshness.py` / `graphify
update .` — see `docs/graphify-workflow.md` §5/§7 — out of scope here.)

## 3. The CI-only indexed-source content-drift gate (Slice 6, commit `e835677`)

Lives entirely in `apps/api/tests/test_committed_snapshot.py` — a pytest gate
over the **committed** `apps/api/isaac_api/data/memory-snapshot.json`, not a
separate script and not a runtime code path. It is dual-branch, so it works
before and after the snapshot is regenerated to embed `memory_inputs`:

- **Branch A — snapshot without `memory_inputs`** (today's committed reality,
  pre-Slice-8): asserts honest graceful degradation via
  `SanitizedSnapshotSource.status()` — `available=True`,
  `integrity="verified"`, both freshness concepts `"unknown"`, both
  fingerprints `None`.
- **Branch B — snapshot with `memory_inputs`** (activates automatically once
  Slice 8 regenerates the real snapshot; exercised green today against a golden
  fixture snapshot + its matching `served_root/` fixture files under
  `tests/fixtures/memory_snapshot/`): recomputes the served-content manifest
  over **exactly** the paths the snapshot already embeds, and asserts,
  entry-for-entry, that no included file's digest drifted; also re-verifies the
  aggregate `served_manifest_fingerprint`, the `policy_fingerprint`, and the
  `served_file_count`. A modified or deleted *included* file trips a distinct
  drift assertion.

Deterministic, offline, Graphify-free — enforced by an AST import guard in the
test module (the generator it drives, `scripts/build_memory_snapshot.py`,
imports `memory.py` but never `graphify` or `isaac_records`). It reads only the
snapshot dict and the already-included served files; it never touches
`graphify-out/`.

**This is the entire scope of "CI enforces indexed-source freshness."** There is
no runtime equivalent — the hosted backend cannot and does not recompute
`indexed_sources` from live file content (§1, §2).

## 4. The new `GET /api/graph/status` response body

`routes.py::graph_status()` resolves **one** reader and reads both its
`status()` and its `overview()` off that same instance — it never
`isinstance`-branches on provider type, which guarantees the freshness fields
and the additive counts always describe the same graph/snapshot.

Fields, in emission order:

```
plane, availability, integrity, provider, memory_policy, indexed_sources,
policy_fingerprint, served_manifest_fingerprint, served_file_count,
freshness_scope, freshness_basis, source_graph_commit, snapshot_schema_version,
deployed_app_commit, note,
# additive counts — real values when available, else explicit null:
node_count, edge_count, community_count, file_count, concept_count, graph_mtime
```

- `provider` is `st["provider_kind"]` (`"local-graph"` / `"sanitized-snapshot"`)
  when available, else the literal string `"unavailable"`.
- `freshness_scope` is always `"served_files_only"`; `freshness_basis` is always
  `"ci_content_manifest"` — both constants, present so a caller never has to
  guess what `indexed_sources` was proven against.
- `source_graph_commit` is the graph's/snapshot's `built_at_commit` — version
  metadata, same non-freshness-input treatment as `deployed_app_commit`.
- `note` is one of two fixed, plane-scoped honesty strings (`_GRAPH_STATUS_NOTES`
  in `routes.py`) keyed by availability — never a PASS/FAIL/verdict phrase.
- **Removed** (present in P24.9, absent now): top-level `status`,
  top-level `source_graph_sha256`.

## 5. Frontend wording (Slice 5, commit `7b96b60`)

`apps/web/src/components/GraphStatusChip.tsx` — the primary chrome chip now
reports **availability only**: `Memory: Available` / `Memory: Unavailable`. It
no longer renders `Fresh` / `Stale` / `Missing`; those finer axes live on the
Project Memory screen, not the global chip.

`apps/web/src/screens/ProjectMemory.tsx` — the status card renders three
separately-honest axis pills:

| Axis | Labels shown |
|---|---|
| Snapshot Integrity | Verified / Malformed / Unsupported / Unknown |
| Memory Policy | Current / **Out of date** (maps `stale`) / Unknown |
| Indexed Sources | Current / **Out of date** (maps `stale`) / Unknown |

The Indexed Sources pill carries an explicit scoping caption:

> Proven in CI over only the files already in the snapshot — newly added
> indexable files are not detected until Graphify re-indexes.

No PASS/FAIL/valid/invalid/verdict language appears on any memory axis;
`unknown` and `unavailable` render quietly (neutral tone), never as errors.
Counts displayed come only from the API response (`file_count`, etc.);
`served_file_count` is kept in the TypeScript type for contract fidelity but is
not surfaced as a user-visible figure.

## 6. Implementation as-built — 8 slices, mapped to commits

| Slice | What | Commit | Notes |
|---|---|---|---|
| 1 | Memory-input fingerprint + served-content-manifest primitives in `memory.py` | `fe835f7` | Pure, stdlib-only; no wiring yet |
| 2 | Generator (`scripts/build_memory_snapshot.py`) embeds the `memory_inputs` block | `517da3e` | Additive; optional key |
| 3 | Reader `status()` separated-freshness contract on both providers | `9e2b42a` | Protocol grows a 7th method |
| 4 | `/api/graph/status` route split onto the new contract | `9e2b42a` | Same commit as Slice 3 — the `status()` signature change forced the route change atomically |
| 5 | Frontend consumes the separated contract + honest wording | `7b96b60` | Implemented **after** Slice 6 below, chronologically — the two were done out of slice order but each is independently correct |
| 6 | CI-only indexed-source content-drift gate (dual-branch) | `e835677` | Test-suite only; no runtime code path; committed before Slice 5 in this history |
| 7 | Documentation (this record) | *(this file, uncommitted)* | Docs-only; no code/test/schema touched |
| 8 | Release: regenerate the committed snapshot to embed `memory_inputs`, then push + deploy | **pending** | Not yet run — the committed `apps/api/isaac_api/data/memory-snapshot.json` still lacks `memory_inputs` as of this writing; Branch A of the Slice-6 gate is the currently-exercised branch in CI until this runs |

Test results at Slice 6 (`e835677`): full backend suite 460 pass. Test results
at Slice 5 (`7b96b60`): frontend 137 pass, `tsc` + `vite build` clean. Slices 1–6
are committed on local `main`, ahead of `origin/main` by 5 commits; none of the
five have been pushed as of this writing.

## 7. Governance invariants preserved

1. **Runtime stays Graphify-free.** `memory.py` (including the new primitives
   and both `status()` implementations) remains stdlib-only; it imports neither
   `graphify` nor `isaac_records`. The isolation test suite covers this
   unchanged.
2. **Truth path untouched.** No file under `schema/` or `src/isaac_records/`
   was touched by any P24.10 slice. All P24.10 changes are confined to the
   memory/query plane (`apps/api/isaac_api/memory.py`, `routes.py`,
   `scripts/build_memory_snapshot.py`) and its tests/frontend consumer.
3. **No validation authority.** No memory-plane response — old or new — ever
   carries a `{ok, valid, passed, verdict, schema, errors}` key. `memory_policy`
   and `indexed_sources` are consistency/freshness signals about the *artifact*,
   never a correctness ruling about record content.
4. **Single-reader guarantee preserved.** `graph_status()` resolves exactly one
   reader instance and reads both `status()` and `overview()` from it — the
   redesign did not reintroduce a two-reader race or an `isinstance` branch.
5. **Honest degradation preserved.** Missing/unreadable artifacts still degrade
   to `available:false` with a stated reason; a malformed or unsupported
   snapshot reports `integrity="malformed"`/`"unsupported"` rather than crashing
   or fabricating `"verified"`. Nothing in this phase changed the never-raise
   contract.
6. **CI-only claims stay CI-only.** No runtime code path recomputes
   `indexed_sources` from live file content; that capability exists solely in
   the `apps/api/tests/test_committed_snapshot.py` gate (§3). This boundary is
   deliberate and documented, not an oversight.
