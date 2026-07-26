# Phase 36R — Closure

**Status:** COMPLETE at org canonical `main` `5b08ce5`, image `v0.0.19`.
**Plan:** `docs/superpowers/plans/2026-07-25-phase-36r-interaction-ia-graph-refinement.md`
**Scope:** repository-local · synthetic-only · deterministic · **no LLM added** ·
no portal · no real data · **no new npm dependency** · **no backend route added or
changed** · truth path untouched · **no Phase 37 work**.

---

## 1. Starting → ending state

| Axis | Start | End |
|---|---|---|
| HEAD | `424d021` | **`5b08ce5`** |
| Image | `v0.0.12` | **`v0.0.19`** (8 semver publications) |
| Backend tests | 1029 | **1029** |
| Frontend tests | **751** / 62 files | **1120** / 69 files (+369) |
| Bundle JS | 391 095 B | 501 771 B (+110 676) |
| Bundle CSS | 110 424 B | 145 467 B (+35 043) |
| Hosted `/krish` | not readable here | **not readable here** — Authentik edge |

Every merge was a **merge commit**. No squash, no rebase, no force-push, no
manual tag, no direct push to `main`.

## 2. Slices → PRs

| PR | Slices | Merge | Image |
|---|---|---|---|
| [#11](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/11) | 1 + 2 — shared width system, Assistant conversation redesign | `f25b0f2` | `v0.0.13` |
| [#12](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/12) | 3 + 6 — native Graph Explore/Browse, graph help | `243898b` | `v0.0.14` |
| [#13](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/13) | 4 + 5 — command bar, Assistant graph intents | `a137a4e` | `v0.0.15` |
| [#14](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/14) | 7 — Concepts master-detail | `c29c293` | `v0.0.16` |
| [#15](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/15) | 8 — Governance IA, Schema Reference | `21a6ec3` | `v0.0.17` |
| [#16](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/16) | 9 — Settings IA, OpenAPI browser | `c1f22a7` | `v0.0.18` |
| [#17](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/17) | 10 — cross-surface polish | `5b08ce5` | `v0.0.19` |

Every slice: Opus implementation → **independent Opus review that implemented
none of the work under review** → all Critical and Important findings fixed
before merge → green CI (3 checks incl. a Docker production-image smoke test) →
merge commit → semver image, tag verified against HEAD.

## 3. What the reviews caught

Six independent reviews returned **APPROVE WITH FIXES**; none returned APPROVE
unchanged. The findings that mattered were almost all **honesty defects that
every test passed through**.

### Four false claims shipped to users, each disproven by executing the code

1. **The Assistant stated a count the action did not produce.** It said
   "draws 14 nodes"; applying drew **0**. The intent context carried three filter
   dimensions but not `typeFilter`/`search`, while the reducer intersects with all
   of them. All 1004 tests passed — they exercised only default filter state.
   Fixed by construction: the proposal now folds its own actions through the
   **real reducer** and reads the model's own `visibleNodeIds`.
2. **"The cited source is not included in this deployed snapshot"** — the
   authorizing prompt's own prescribed copy, propagated verbatim by this plan.
   `on_disk` is a filesystem check; the cited sources **are** in the snapshot.
   The app told users a document was absent, then rendered that document's
   metadata from the snapshot one click later. Recorded as **R9**.
3. **"Workspace state … is gone when it restarts."** It is a filesystem
   directory. Two `create_app()` instances over one workspace returned the same
   5 experiments.
4. **"Any access restriction is applied … outside this application"** and
   **"stores no credentials."** `ApiKeyAuthMiddleware` is installed at
   `app.py:60`, holds the expected bearer in memory, and returns **401
   in-application** when `ISAAC_UI_API_KEY` is set.

### The most serious finding — a governance guarantee the code does not make

Settings claimed real artifacts were **"refused before anything is read or
extracted."** There is **no real-vs-synthetic detection anywhere in the
codebase**. `POST /api/uploads` is a blanket 403 that parses nothing — but
`POST /api/experiments/{id}/ingestion/csv/preview` accepts a raw CSV body and
parses it into a field preview, reachable from a real file picker in
`CsvReconcilePanel`. The app enforces synthetic **mode**, not synthetic **data**.

The corrected copy names the gap rather than hiding it, and states that keeping
real artifacts out is an **operator responsibility, not a check the software
performs** — the honest statement, and the more useful one.

### Defects that would have shipped invisibly

- A cluster could be **coloured on the canvas yet absent from the legend**, then
  silently misattributed to the neutral "every other cluster" swatch. Invisible
  on today's payload; proven with the project's own fixture.
- A test **could not distinguish a derived relationship from a hard-coded one**:
  the fixture slug was a *superstring* of the production slug. Verified fixed by
  mutation — hard-coding the needle now **fails 4 tests**.
- The vocabulary citation could **fabricate provenance**: files are auto-globbed
  and the only guard was a 3-character minimum, so a future `units.json` would
  have asserted "N schema fields cite Units" for every description containing the
  word.
- "Related conditional rules" **over-matched on 76 of 271 fields**, attributing a
  rule to every descendant of any path it named.
- `graphModel.ts` contained three literal **NUL bytes**, so git treated it as
  binary — its diff in PR #12 was unreviewable, and every future diff would have
  been. The emitted bundle hash is unchanged, proving the fix byte-identical.

## 4. Reconciliations recorded (never silent)

`R1` Graphify HTML unusable (gitignored, CDN, withheld paths, 2.55 MB) → native
build, zero dependencies · `R2` conversation region white-on-lavender, since the
rail is already lavender · `R3` no colored left/right edge (CI-enforced) ·
`R4` hosted verification impossible from this environment · `R5` 112 communities
mostly singletons with meaningless names · `R6` Assistant graph intents resolve
client-side against the same index · `R7` Vocabulary is **not** empty ·
`R8` full-graph Explore default, superseding a pre-measurement criterion, with
the deleted guards **replaced** not dropped · `R9` the prescribed Concepts copy
was false.

## 5. Verification at closure

Backend **1029 passed** · frontend **1120 passed / 69 files**, eleven consecutive
clean runs · `tsc -b` clean · production build clean · snapshot regenerated in
every commit that touched a manifest-listed file, `--check` reporting no drift ·
Docker production-image smoke test green on every PR · no `.only`, no skipped
tests · no secrets, absolute paths, or CDN references introduced · browser QA at
1920 / 1440 / 1280 / 1024 / 768 / 375 and 200% zoom, most recently **65
viewport × route combinations with zero horizontal overflow and zero console
errors**.

**The `memory-status` flake was fixed, not hidden.** The assertion awaited a
*synchronous* chip answer with `findByText`'s 1 s poll. The poll was removed
(`act()` + `getByText`); the timeout was not raised and nothing was skipped.

## 6. Open — Krish's calls, not this phase's

1. **HOSTED QA — every image `v0.0.13`…`v0.0.19` is unverified.** `/krish` sits
   behind an Authentik edge that this environment cannot authenticate to; the
   host did not even resolve on some attempts. **No rollout is claimed as
   verified.** After Flux rolls `v0.0.19`, `/krish/api/health` should report
   commit `5b08ce5`.
2. **Human visual sign-off** — responsive and 200%-zoom. Automated browser QA is
   not a person looking at it. Open since Phase 33.
3. **Personal-deploy retirement** (Vercel `isaac-demo-web` + Railway) — dashboard
   action.

## 7. Deferred, with reasons

- **Graphify re-index.** The served manifest (200 entries) omits this phase's new
  source files because it derives from a graph built at `caab1d0`. Re-indexing was
  **not** run: Graphify's concept extraction calls an external model, which this
  phase forbids. The limitation is already disclosed in-product.
- **A backend test scanning the real `/api/openapi`** for the forbidden-substring
  list — the frontend guard is fixture-bound.
- Schema-evolution hazards in `schemaBrowser.ts` (`then`-clause enums,
  array-scope rule paths), a stale hosted-deployment note in
  `ProjectMemory.tsx`'s unavailable branch, and the `Community`/`Cluster` label
  mix on three detail panes (a terminology migration, not polish).

## 8. Phase 37 boundary

**No Phase 37 work was performed.** Untouched: portal integration, Postgres or
durable persistence, real data, portal/personal API keys, external model
provider, embeddings, vector retrieval, identity/role enforcement, `isaac-k8`,
new production secrets, Authentik removal, and Vercel/Railway deletion. Phase 37
remains **unauthorized**; readiness plan only.
