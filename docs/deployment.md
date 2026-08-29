# Deployment — SLAC Kubernetes (isaac.slac.stanford.edu/krish)

The synthetic UI prototype is hosted on SLAC-owned infrastructure. Nothing
about validation, audit, or export changed — the deployed backend runs the
same deterministic core in a container.

## Architecture

- **One image, one container** — the repo-root `Dockerfile` is multi-stage: a
  Node stage builds the Vite/React SPA with the deploy prefix baked in
  (`BASE_PATH` build arg, default `/krish`), and the Python stage serves both
  the API (`{base}/api/*`) and the static SPA (`ISAAC_STATIC_DIR`, with an
  `index.html` fallback for client-side routes). The COPY allowlist is
  unchanged: never `examples/`, `drafts/`, `records/`, or `graphify-out/`.
  The image ships one committed, sanitized
  `apps/api/isaac_api/data/memory-snapshot.json` (P24.9, metadata/provenance
  only, no file contents), which powers hosted Project Memory.
- **CI/CD** — pushing to `main` on `ISAAC-DOE/isaac-metadata-assistant` runs
  `.github/workflows/ci.yml`, and **only when that run concludes successfully**
  does `.github/workflows/build-push.yaml` follow (a `workflow_run` trigger plus
  a gate job that re-checks the Actions API for that exact commit — see
  [`release-gating.md`](release-gating.md)). Until 2026-08-08 the two triggered
  independently on the same push and raced, so a commit whose tests failed still
  shipped an image. Once gated, build-push
  builds the image, pushes
  `ghcr.io/isaac-doe/isaac-metadata-assistant:<semver>` (auto-incremented
  patch, e.g. v0.0.1 -> v0.0.2) plus `:latest`, and tags the repo. Flux image
  automation in the `isaac-k8` repo detects the new semver tag and bumps the
  deployment manifest; k8s manifests never reference `:latest`.
- **Hosting** — a Deployment/Service/Ingress in the `metadata-assistant`
  namespace of the ISAAC vCluster (manifests live in `isaac-k8/metadata-assistant/`).
  The ingress serves `path: /krish` (Prefix, no rewrite — the app owns its
  subpath) on `isaac.slac.stanford.edu`, behind Authentik forward auth
  (admin or researcher group, same policy as `/portal`).
- **State** — TWO STORES, and conflating them is a defect this document has
  already shipped once. ~~"an `emptyDir` volume at `ISAAC_UI_WORKSPACE`.
  Contents are synthetic-only and self-seed deterministically on first read, so
  pod restarts reset state harmlessly."~~ — **corrected 2026-08-27, and struck
  rather than reworded because "restarts reset state harmlessly" is a claim an
  operator plans around.** It was written before the 2026-08-07 durable
  persistence work and describes only the first of these:
  - **The workspace directory** — still an `emptyDir` volume at
    `ISAAC_UI_WORKSPACE`, still synthetic-only, still self-seeding
    deterministically on first read. It holds each experiment's working copy and
    the official records and evidence sidecars an export writes. **A pod restart
    does take it**, and for exported artifacts that loss is real: they are not
    held in a database, so a restored experiment can still be marked as exported
    with its artifact files gone, which the readers report as `stale`
    (`apps/api/isaac_api/experiment_repository.py`, module docstring).
  - **Experiment records** — **NOT** reset by a pod restart on this deployment.
    Since `0001_experiments` was applied (2026-08-09) the authoritative state of
    every experiment created through `POST /api/experiments` is written to
    `isaac_experiments` in the app-owned PostgreSQL database and the workspace
    copy is rehydrated from it. Measured on `/krish` on 2026-08-27: two
    experiments created 2026-08-09 and 2026-08-10 were still being served after
    dozens of image rollouts, alongside `experiment_storage: {"backend":
    "postgres", "durable": true, "state": "durable"}`
    ([`evidence/hosted-qa-2026-08-27.md`](evidence/hosted-qa-2026-08-27.md) §2.2).

  Which of the two is in force is not a constant and must not be read as one.
  `GET /api/health`'s `experiment_storage.state` — mirrored by `GET /api/about`'s
  `persistence` since 2026-08-27, so the two cannot disagree **within one server
  process** — reports `durable`, `ephemeral` (no database configured; the
  workspace is all there is) or `unavailable` (a database is configured and
  experiment records are **not** reaching it). The bound on "cannot disagree" is
  not pedantry: part of what `storage_status()` reports is `storage_failure()`,
  which `experiment_repository`'s module docstring documents as process-local
  ("each replica observes its own failures"), so with more than one replica two
  calls can legitimately differ.
  A worked-example walkthrough is never written to the database in any state.

  **`unavailable` has TWO causes and they behave oppositely** — the state's own
  comment in `storage_status()` says so ("because the PGDATABASE gate refused it,
  or because it stopped answering"), and only `experiment_storage.backend`
  separates them. ~~"in which case `POST /api/experiments` returns `503` having
  written nothing"~~ is struck rather than reworded, because it is true of one
  cause and denies exactly what the other does:

  | `backend` | cause | `POST /api/experiments` |
  |---|---|---|
  | `postgres` | the configured database is selected and records are **not reaching it** — it is unreachable, or it is answering but a relation a migration has not created is missing (`_not_provisioned`), or a failure was recorded earlier and has not been cleared | **`503 experiment_storage_unavailable`**, having written nothing — **while that condition is current and on the write path**; otherwise **`201`, durably** (see the correction below) |
  | `filesystem` | `PGDATABASE` is not the expected name, so `_postgres_available()` refuses it and the app degrades to the workspace repository (its docstring documents this as the intended degradation) | **`201`** — the record is created and listed, in a working directory that is not durable |

  Measured over HTTP on 2026-08-27 with no database contacted (outbound
  connections stubbed to raise).

  **CORRECTED 2026-08-28 — the `postgres` row was as over-narrow as the sentence
  it replaced, and the correction is kept visible for the same reason.**
  ~~"the configured database is selected and is not answering"~~ named one fact
  out of at least three, and an operator diagnosing an unapplied `0003`/`0004`/
  `0005` would have read the row as not describing their deployment when it does.
  ~~"**`503`**, having written nothing"~~ is not determined by the state either:
  `experiment_repository.repository()` branches on `_postgres_available(env)`
  **alone** and never consults `storage_failure()`, so with `backend: "postgres"`
  the PostgreSQL repository is still the one that runs. A recorded failure is not
  re-tested; if it came from a read path, or from `_not_provisioned` while writes
  work, or the database has simply recovered, the create **succeeds into
  PostgreSQL and IS durable**, and `_note_storage_success()` then clears the flag.

  ~~What holds under both, and is the only thing a surface given `state` alone may
  assert, is that **no experiment record created in this state is durable**.~~
  **That absolute is false on the recovered-write path**, and it errs by
  understating persistence — the same direction as the defect this section was
  written to correct. What a surface given `state` alone may assert is narrower:
  **a database is configured and records are not reaching it, the create may fail
  outright, and nothing in this state establishes that a record created in it is
  stored durably.** A caller that needs to know reads the record back.
- **Health** — `GET /krish/api/health`; pod probes hit the container port
  directly (bypassing ingress/auth), and this path stays open even when
  API-key auth is enabled.

## Project Memory snapshot (P24.9)

Hosted Project Memory is served from a committed, sanitized snapshot rather than
a live graph (`graphify-out/` is gitignored and never shipped).

- **Delivery** — `apps/api/isaac_api/data/memory-snapshot.json` ships inside the
  existing `COPY apps/api/` layer; no extra Dockerfile COPY is needed. The reader
  auto-selects it by on-disk presence (`SanitizedSnapshotSource`), so no env var
  is required for the packaged path. `ISAAC_MEMORY_SNAPSHOT` can point at an
  alternate file if delivery changes later.
- **Content** — metadata/provenance only: counts, served-file allowlist, curated
  concepts, and length-capped rationales. Never file contents; every `on_disk` is
  forced `false`; secret/path-excluded strings are scanned out at generation.
- **Freshness (redesigned P24.10)** — `GET {base}/api/graph/status` no longer
  compares the deploy's build commit to the snapshot; `deployed_app_commit` is
  surfaced as version metadata only, never a freshness input. Freshness is two
  separated, provable axes instead: `memory_policy` (current/stale/unknown — the
  shipped sanitization/exclusion policy recomputed at runtime against the
  snapshot's embedded fingerprint) and `indexed_sources` (current/stale/unknown —
  a CI-only content-drift gate over the files already embedded in the snapshot;
  the hosted runtime never recomputes it, since the served files aren't
  shipped). A missing/unreadable snapshot still degrades to the honest
  unavailable panel regardless. See
  [`2026-07-19-phase-24-10-memory-freshness-semantics.md`](superpowers/specs/2026-07-19-phase-24-10-memory-freshness-semantics.md).
- **Refresh / rollback** — regenerate with
  `python scripts/build_memory_snapshot.py` from a fresh local graph, review the
  diff (including every `rationales[]` string), and recommit; `test_committed_snapshot.py`
  gates shape, provenance, and leaks in CI. Rollback is atomic with code via
  `git revert`. See the P24.9 spec §16 (update) and §15 (rollback).
- **Verification scope (two independent guarantees).** The committed snapshot's
  **shape + leak scan** (`test_committed_snapshot.py`) runs unconditionally in every
  backend test run — it reads only the committed artifact and needs no graph, so a
  malformed or leaking snapshot is always caught, including in CI. **Byte-drift
  detection** (`python scripts/build_memory_snapshot.py --check`, which regenerates
  from the source graph and compares) is different: it requires the local Graphify
  artifacts (`graphify-out/`). Where those artifacts are present the check is
  deterministic and catches any drift between the committed snapshot and the graph;
  where they are absent — e.g. CI, which does not ship `graphify-out/` — drift cannot
  be recomputed, and CI does **not** and **cannot** regenerate the graph, because the
  Graphify inputs are not available there. Keeping the committed snapshot current is
  therefore a local, human-run step (§16), not something CI can do on its own.

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `ISAAC_BASE_PATH` | image ENV (from `BASE_PATH` build arg) | Deploy prefix for API routes and SPA serving; must match the prefix the frontend was built with |
| `ISAAC_STATIC_DIR` | image ENV | Built SPA `dist/` dir; unset locally (API-only, exactly the pre-k8s behavior) |
| `ISAAC_UI_WORKSPACE` | k8s manifest | Workspace dir; set to the emptyDir mount path |
| `ISAAC_UI_CORS_ORIGINS` | k8s manifest | Comma-separated browser origins; mostly moot now that the SPA is same-origin |
| `ISAAC_UI_API_KEY` | (unset in k8s) | Shared-secret bearer key; unset -> auth disabled. Authentik forward auth gates access at the edge instead |
| `PORT` | container | Listen port (default 8000) |
| `ISAAC_BUILD_COMMIT` | Docker build arg (CI passes `github.sha`) | Build/commit identity on `GET {base}/api/health` |
| `VITE_BASE_PATH` / `VITE_API_BASE` | Docker build (frontend stage) | Baked base path and same-origin API base (`/krish/`, `/krish/api`) |
| `PGHOST` / `PGPORT` / `PGDATABASE` / `PGUSER` / `PGPASSWORD` | k8s manifest + Secret `metadata-assistant-db-app` (Dean-owned) | libpq contract for the in-cluster `metadata_assistant` Postgres. **Already present in the pod.** `PGHOST` is the feature switch: unset (local dev, CI) means no database and today's synthetic behavior; set means the read-only reconnaissance path is live. See [`postgres-test-db-guide.md`](postgres-test-db-guide.md) |
| `ISAAC_EDGE_TRUST_VERIFIER` | **unset everywhere; set by no committed deploy artifact** | Selects which edge-trust verifier resolves a caller's identity. Unset means *no verifier*, which means **no request can be attributed to a person** and every operation requiring one refuses with `409 human_actor_required`. The only value this build accepts is `test_fixture`, which selects `identity.FixtureEdgeVerifier`. **Setting it is not cosmetic: it is the switch that turns submissions from "always refused" into durable, attributed rows in `isaac_experiment_revisions` and `isaac_submissions`.** The verifier reads its subject from the **process environment**, never from a request header — a header-reading verifier would rebuild exactly the forgeable-header hazard Q4 is answered against — and every row it causes is stamped `trust_basis = 'test_fixture'` permanently, so a deployment that enabled it by mistake is identifiable from the data. `/api/health`'s `submission.actor_trust_basis` surfaces it. Used by the local test suite and by one CI job; `apps/api/tests/test_deploy_config.py` asserts no committed deploy artifact names it |
| `ISAAC_FIXTURE_ACTOR_SUBJECT` / `ISAAC_FIXTURE_ACTOR_GROUPS` | **unset everywhere; set by no committed deploy artifact** | The subject (and optional comma-separated groups) `FixtureEdgeVerifier` attributes to. Meaningless unless `ISAAC_EDGE_TRUST_VERIFIER=test_fixture`. With the verifier selected and no subject set, the verifier returns *not traversed* and requests are refused with reason `unverified_edge_traversal` — a different fact from "no verifier configured", and the two carry different messages because they suggest different next steps |

`ISAAC_UI_CORS_ORIGINS` values must be exact origins — scheme://host with no
trailing slash and no path — because browsers match origins exactly and a
trailing slash silently breaks CORS.

Local dev needs none of these — defaults reproduce the pre-hosting behavior
exactly (localhost CORS, `/tmp/isaac-ui-workspace`, auth off, API at `/api`,
no SPA serving; run the Vite dev server separately as always). Do **not** set the
`PG*` variables locally: the database is unreachable from outside the cluster by
design, and local runs and CI use fakes only.

### Database status on `GET {base}/api/health`

Health reports a `database` block derived from the environment alone — it opens
**no connection**, because health is the Kubernetes readiness probe target and a
database outage must never remove a pod from service. Reconnaissance runs only on
an explicit request to `GET {base}/api/runtime/database/recon`, which uses one
short-lived read-only connection, serialises concurrent scans, and returns
sanitized aggregates only.

Note that `mode: synthetic-only` on that same response describes the **workspace**
— uploads refused, seeding from committed fixtures only. It does not mean the
process never touches real data: since Slice 2A, production-derived records transit
pod memory during a scan and are never persisted, logged, or returned.

## Auth model (honest scope)

Access control is enforced at the edge: the nginx ingress forward-auths every
`/krish` request against the cluster's Authentik outpost, and the existing
`isaac-portal` application policy admits the `admin` and `researcher` groups
(same policy as `/portal`). Unauthenticated users are redirected to login;
authenticated users outside those groups are denied.

The app's own `ISAAC_UI_API_KEY` bearer-auth seam still exists but is left
unset in k8s — it was nuisance-abuse prevention for the public demo hosting
and is redundant behind Authentik. `GET {base}/api/health` stays open
regardless so pod probes never need credentials.

## Resetting the synthetic workspace

```bash
kubectl -n metadata-assistant exec deploy/metadata-assistant -- rm -rf /data/workspace
# or simply restart the pod; emptyDir state is disposable
kubectl -n metadata-assistant rollout restart deploy/metadata-assistant
```

The backend auto-seeds fresh synthetic demo experiments on the next request.

## Rollback and failure recovery

Frontend and backend ship in one image, so there is no split-brain: every
deployed tag is a single tested commit. Recovery paths:

- **Bad release** — `git revert` the offending commit and push; CI builds the
  next patch tag and Flux rolls it out. For an immediate stopgap, edit the
  image tag in `isaac-k8/metadata-assistant/deployment.yaml` back to the last
  good semver and push that repo (Flux applies it; if image automation
  re-bumps to a broken newer tag, revert in this repo first so a fixed tag
  supersedes it).
- **Failed rollout** — a pod that never passes `GET /krish/api/health`
  readiness never receives traffic; the old ReplicaSet keeps serving.
- **Workspace state** — untouched by rollbacks and disposable (see reset
  above).
