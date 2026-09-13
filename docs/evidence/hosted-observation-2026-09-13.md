# Hosted observation, 2026-09-13 — the first INSPECTED recon response body

**Status: READ-ONLY OBSERVATION, captured artifact.** This is not operator testimony. Every figure
below was read from a response body in an authenticated browser session in this environment, and the
commands that produced them are given so they can be re-run.

**Authorization basis.** The project owner stated in-session that the SLAC session was already
authenticated and invited debugging through the browser tab. `GET /api/runtime/database/recon` is the
route authorized by **Slice 2A** (`CLAUDE.md` §15, *"the deployed pod performs read-only
reconnaissance and returns a sanitized aggregate report"*, authorized 2026-07-31).

**No credential was entered, and no agent connected to any database.** The pod opened its own
short-lived read-only connection, which is the whole point of the deployment-mediated design. The
prohibition at `2026-07-24-phase-37-readiness-plan.md:48-52` is on a connection *originating from a
laptop or from CI*; none was made. No kubeconfig, port-forward or Secret was requested.

**Data boundary.** Only sanitized aggregates were read. No record id, title, scientific value,
evidence entry or record text was read or is recorded here. Two fields the browser tooling itself
withheld as sensitive (`session_user`, `app_commit`) are reported as withheld rather than guessed.
Every figure recorded below falls inside Dean's enumerated list — record counts, counts by type and
domain, validation totals, schema version, reachability. `by_record_type` and `by_record_domain`
values were **not fetched**, because they were not needed.

---

## 1. What the hosted deployment is running

| Field | Observed |
|---|---|
| `commit` | `2f9a1133bcda7f45e1d751110641d1322586f60e` |
| `mode` | `synthetic-only` |
| `core` / `version` | `isaac_records` / `0.1.0` |

**That commit is byte-for-byte the current `main`.** `git rev-parse main` and `git rev-parse
origin/main` both return `2f9a1133…`. So for the first time in many sessions the hosted
deployment is provably running the head this repository can inspect, rather than an unobserved image.

**A cross-check that could have looked like a defect and is not.** The hosted `/api/health` payload
carries **no `mcp` block**. `MCP-003` adds one — and `MCP-003` lives on PR #248, not on `main`
(`git show main:apps/api/isaac_api/routes.py | grep -c '"mcp"'` → **0**). The absence is exactly
what running `main` predicts.

## 2. Gate G2 holds, and the workspace is not empty — both at once

`database.record_display` reads **`closed`**, and `contains_production_derived_records` reads
**`true`**. The 30-record production-derived corpus is present and is not displayed.

`GET /api/experiments` returns **3 experiments**, and none of them is from that corpus — they are
records this application created through its own durable Create Experiment path:

| Title | Status | Pending | Exported |
|---|---|---|---|
| `Durability check after 0001 (2026-08-09)` | `needs_attention` | 3 | false |
| `SYNTHETIC Run-slice hosted QA (cf2a8bc)` | `needs_attention` | 6 | false |
| `b` | `needs_attention` | 3 | false |

These are the artifacts of the `0001` hosted verification and a later run-slice QA, persisted because
`experiment_storage` is `postgres` / `durable`. **So `record_display: closed` and a populated
workspace are consistent, not contradictory** — the two live in different tables.

**A memory note is thereby stale.** The tutorial-scope entry records *"normal My Experiments is
PERMANENTLY empty (no create path exists)"*. A create path exists, the hosted screen renders a
**Create Experiment** control, and three records sit in the list. That note described a true state
that has since been superseded.

**And the run-projection counter corroborates the row count exactly.** Health reports
`run_projection.last_pass: {complete: 0, stale: 0, never_projected: 0, unavailable: 3, mismatch: 0}`.
**`unavailable: 3` is the same 3.** It reads `unavailable` rather than `never_projected` because
`0005_run_projection` is **not applied to the hosted database** — correctly, since it is not
owner-approved. Two independent surfaces agreeing on 3 is the kind of coherence that is hard to fake.

## 3. The recon response body, INSPECTED

`CLAUDE.md` §15 says of this route's masking that it is *"backed by code review rather than by an
inspected response body"*, and of its results that they are *"operator-relayed testimony, not a
captured artifact"*. **Both qualifications are now discharged for this observation.** Payload: 4,123
bytes, `report_format_version: 1`, `status: ok`, `schema_version: 1.05`.

### 3.1 The five G3 aggregates are withheld ON THE WIRE

`dataset` carries **sixteen** keys and **not one** of the five is among them:

```
by_record_domain · by_record_type · by_rule_family · by_schema_path · expected_seed_rows
parse_failures · record_id_digest_count · records_failing_full_schema · records_parsed
records_passing_full_schema · records_scanned · seed_count_matches · total_records
total_validation_issues · vocabulary_cache_present · withheld_pending_visibility_decision
```

`dataset.withheld_pending_visibility_decision` names exactly the five, and nothing else:
`by_instance_path`, `distinct_structural_signatures`, `total_link_count`, `dangling_link_count`,
`vocabulary_term_count`. `vocabulary_cache_present` is present and `true` — the boolean that
replaced the withheld cardinality, and reachability *is* on Dean's list.

**MY FIRST CHECK FOR THIS WAS A FALSE POSITIVE OF MY OWN MAKING, and it is recorded because the
next person will write the same check.** I tested `JSON.stringify(payload).includes('"' + key +
'"')` for each of the five and got **all five back**, which reads as a leak. The substring matched
**the withheld list itself**, which necessarily names them as strings. The designed behaviour and
its own violation have the same signature under a flat-text search. *Enumerate the keys of the
block; do not grep the serialized payload.*

### 3.2 The scan I triggered mutated nothing, and the wire says so

| `integrity` field | Observed |
|---|---|
| `ddl_statements_issued` | **0** |
| `dml_statements_issued` | **0** |
| `read_statements_issued` | 19 |
| `rows_before` / `rows_after` | **30 / 30** |
| `rows_modified` | **0** |
| `transaction_read_only` | `true` |
| `schema_stable_across_run` | `true` |
| `full_schema_fingerprint_match` | `true` |
| `partial_schema_validation_runs` | 0 |
| `session_statements_issued` | withheld by the browser tooling as sensitive |

All six preflight `gates` read `true`: `current_user`, `database_identity`, `not_production_shaped`,
`records_table_present`, `tls`, `transaction_read_only`. `refusal_class` is `null`.

**`rows_before` and `rows_after` are BOTH reported, which narrows a recorded limitation.** The
2026-08-08 private-30 entry lists as a limitation that *"no database row was re-read and compared
after the sweep (the connection closes first)"*. That remains true **of the private verification
mode**, which is a different path; it is not true of this route, which reports both sides of the
scan and a modified count. The two must not be conflated.

### 3.3 Official validation on the production-derived corpus

| Field | Observed |
|---|---|
| `total_records` | 30 |
| `records_scanned` / `records_parsed` | 30 / 30 |
| `records_passing_full_schema` | **30** |
| `records_failing_full_schema` | **0** |
| `total_validation_issues` | 0 |
| `parse_failures` | 0 |
| `expected_seed_rows` / `seed_count_matches` | 30 / `true` |

30 of 30 pass official ISAAC v1.05 validation with zero issues. This agrees with the 2026-08-08
operator-relayed figure, and unlike that figure it was read here from a response body.

### 3.4 The hosted engine is PostgreSQL 18

`database.server_version_major` is **18**, with `expected_major_version_match: true`. CI proves the
migrations against a `postgres:18` service container, and `CLAUDE.md` §15 is careful that this *"is
not the same as proving it against the hosted database with its real data"*. That caveat stands
untouched — **but the engine major version is no longer an assumption**, which removes one of the
several ways the CI-to-hosted inference could have been wrong.

## 4. QA-019 confirmed as a real hosted defect

On `https://isaac.slac.stanford.edu/krish/experiments`, `document.title` is the bare
**`ISAAC Metadata Assistant`** — no route segment, on a route that is not the app root. That is the
WCAG 2.4.2 defect `QA-019` fixes, observed on the deployed product rather than argued from source.
The local dev tab in the same browser, running this branch, renders
**`Review Export Readiness · ISAAC Metadata Assistant`**.

The hosted left navigation shows **five** destinations (`My Experiments`, `Project Memory`,
`Governance & Safety`, `Statistics`, `Settings & API`); this branch's `UX-002` work reduces that to
three by making Project Memory and Statistics children of Settings. Both readings are consistent with
hosted running `main`.

## 5. The honesty chip, measured hosted

Visible text: **`Workspace`**. Accessible name, opening with that visible text, as
`CLAUDE.md` §11 records:

> Workspace — nothing in this build adds a built-in example record to this workspace — they are
> created only inside a guided-walkthrough session; file upload is refused, and no official
> institutional record is shown. This deployment is also configured to run a protected, read-only
> diagnostic against an isolated test database; it returns sanitized aggregate results only, and no
> database records are d… *(truncated by the read, not by the product)*

Matches the recorded text. `mode: synthetic-only` on the wire is unchanged.

## 6. What this observation does NOT establish

- **It is not a QA pass for any image built from PR #248.** Nothing on this branch is deployed;
  hosted runs `main`. Every image from this session remains `HOSTED QA PENDING (Krish)`.
- **It says nothing about narrow widths, 200% zoom, or a real microphone.** This tooling cannot
  drive any of the three — `resize_window` reports success while the rendered viewport does not
  follow, and every driven tab reports `visibilityState: "hidden"`, so change-feed-driven updates
  never fire.
- **It is not authorization for anything.** Gate **G2** (per-record display) is still closed and
  still Dean's; gate **G3** (the five withheld aggregates) is still open and still Dean's — this
  observation confirms the withholding is *implemented*, not that the five may be restored.
- **No migration was applied and none may be.** `0003`, `0004` and `0005` remain unapplied to the
  hosted database, and applying one is the operator's act.
- **`limitations` carries 7 items** which were counted but not transcribed; a future reader should
  read them from the live route rather than from this file.

## 7. Re-derivation

```bash
git rev-parse main origin/main          # expect 2f9a1133… twice
git show main:apps/api/isaac_api/routes.py | grep -c '"mcp"'   # expect 0
```

In an already-authenticated browser tab, read-only:

```js
await fetch('/krish/api/health').then(r => r.json())
await fetch('/krish/api/runtime/database/recon').then(r => r.json())
// enumerate Object.keys(payload.dataset) — do NOT grep the serialized payload
```
