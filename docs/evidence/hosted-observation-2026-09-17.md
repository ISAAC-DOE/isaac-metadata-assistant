# Hosted observation — 2026-09-17

**Read-only. No credential was entered. No database connection was opened.** Every figure below was
read from `https://isaac.slac.stanford.edu/krish/...` in a browser tab **the project owner had
already signed in**, using same-origin `GET` requests only.

## 0. Authorization basis and data boundary

**Authorization basis.** The project owner's in-session statement of 2026-09-17 that they had signed
in to Chrome, together with the standing pattern of
[`hosted-observation-2026-09-13.md`](hosted-observation-2026-09-13.md): `/krish` is readable
read-only from an already-authenticated tab, and an agent must never enter a credential
(`CLAUDE.md` §17 and the top-level safety rules).

**Data boundary.**

| question | answer |
|---|---|
| what was touched | four `GET` endpoints: `/krish/api/health`, `/krish/api/mcp`, `/krish/api/openapi`. Nothing else |
| writes | **none.** No `POST`, `PATCH`, `PUT` or `DELETE` was issued to any endpoint |
| credentials | **none entered.** The session cookie was already present in the owner's tab |
| database | **NO DATABASE CONNECTION WAS OPENED — and this is the strong form, which the 2026-09-13 observation could NOT use.** Verified in source before claiming it: `routes.py:1960-1967`'s `health()` states *"ZERO I/O in the database block … nothing here connects, queries, or blocks. This operation is the container readiness-probe target"*, and `run_authority_summary()` (`experiment_repository.py:1579-1585`) returns a copy of an **in-process dict** from a prior hydration pass. **No scan, recon or verification mode was triggered**, which is what opened a pod-side connection on 2026-09-13 |
| production-derived content | **none seen.** `record_display` is `closed` and no record id, title, or field value was requested or returned |
| what left the process | nothing. The figures below are configuration and aggregate state |

## 1. The deployed commit — a rollout VERIFIED rather than assumed

```
commit  70b48390747e780e689f840bc6f4597560a56809
version 0.1.0
mode    synthetic-only
status  ok
```

**`70b48390` is the merge commit of PR #263**, so the **Extended Context** work (`CTX-001`,
`CTX-002`, `CTX-003`, `DOM-001`) is deployed and serving. This is the first hosted rollout this
session has *observed* rather than recorded as `HOSTED QA PENDING`.

**It is one merge behind `main`**, which was `e34983a9` (PR #262) at observation time. #262 is
documentation-only, so the served API is identical — corroborated in §4 below, where the hosted
operation counts match a local measurement taken at `e34983a9` exactly.

**This is a rollout observation, NOT a QA pass.** No screen was exercised, no workflow was walked,
no narrow width or zoom was checked. `HOSTED QA PENDING (Krish)` is unchanged for every image.

## 2. `0005` — the hosted state CONFIRMS that approved ≠ applied

```
experiment_storage: { configured: true, backend: "postgres", durable: true, state: "durable",
  run_projection: { authoritative: true,
    last_pass: { complete: 0, stale: 0, never_projected: 0, unavailable: 3, mismatch: 0 } } }
```

**`unavailable: 3` — all three hosted experiments have an unreadable run projection**, exactly as
`EXT-08` records. That is the direct hosted consequence of `0005_run_projection` being
**owner-approved (2026-09-17) and applied NOWHERE**: the table does not exist, so the reader cannot
classify, so every experiment reports `unavailable` rather than a count.

This is the most useful single number here, because it is independent evidence for the boundary the
`0005` approval packet insists on: **an owner approval changes nothing about the deployed system.**
Only the operator's act does, and the eleven-step sequence is §12A of
[`migration-approval-packet-0005.md`](../migration-approval-packet-0005.md).

**One nuance, stated so the figure is not over-read:** `last_pass` is an *in-process observation
from a prior hydration pass*, not a live query — so it says three experiments were classified
`unavailable` at some earlier point in this pod's life, not that a query ran just now.

## 3. The three external blockers, confirmed on the real deployment

| blocker | hosted evidence |
|---|---|
| **`EXT-01`** trusted authentication boundary | `submission: { configuration_permits: false, blockers: ["no_attributable_actor"], requires_attributable_actor: true, actor_trust_basis: null, verifier_id: "unconfigured" }`. **The actor seam is unset in the real deployment** — which independently confirms that `unattributed` is the only honest actor value the Activity history (`ACT-001`/`ACT-002`, PR #264) could record, and that `ACT-005` is genuinely external |
| **`EXT-02`** remote MCP reachability | `GET /krish/api/mcp` → **404**. Health reports `mcp: { posture: "unmounted", binding: "unconfigured", serves_transport: false, requires_loopback_peer: true, refuses_proxy_headers: true, outstanding_decisions: [D1 DEFERRED 2026-08-12, D2 DEFERRED 2026-08-12] }`. An **absent route, not a broken one** |
| **`EXT-06` / G2** per-record display | `database.record_display: "closed"`. **Still closed by default**, unchanged |

Also observed: `database: { configured: true, classification: "isolated-app-postgres",
contains_production_derived_records: true, last_recon: null }`. **`last_recon: null`** — no
reconnaissance scan has run in this pod instance, and **none was triggered here.**

## 4. The documented-operations count, cross-checked against the deployment

```
GET /krish/api/openapi   ->   78 paths   /   88 method-operations
has_activity_route: false
```

**These match the local measurement at `e34983a9` exactly (78 / 88)**, which is independent
confirmation of the correction in PR #266: `CLAUDE.md` §11's instruction to *"quote 78 for
documented operations"* names the **paths** count while labelling it operations. The deployment
agrees that 78 is paths and 88 is operations.

`has_activity_route: false` is the expected and correct reading: the activity route is on PR #264,
which had not merged at observation time — and it is also the cause of that PR's a11y baseline
movement, since the Endpoint Explorer renders every operation the live document exposes.

## 5. What this observation does NOT establish

- **It is not a QA pass.** No screen, workflow, narrow width, zoom level, or microphone was
  exercised. `HOSTED QA PENDING (Krish)` stands for every image.
- **It does not close `G3`.** The five withheld aggregates were confirmed withheld by an inspected
  response body on 2026-09-13; re-confirming would require triggering a recon scan, which **would**
  open a pod-side database connection. It was deliberately not triggered, so this document makes no
  claim about it either way.
- **It does not close `G2`, `EXT-01` or `EXT-02`.** It confirms each is still in the state this
  repository records — which is the opposite of closing them.
- **It observed no record content**, so it says nothing about the 30 production-derived records.
