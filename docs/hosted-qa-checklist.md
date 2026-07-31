# Hosted QA Checklist — for Krish

**Created:** 2026-07-31 · Closes gates **G1** and **G4** in the
[Baseline Completion Matrix](superpowers/plans/2026-07-31-baseline-completion-matrix.md).

**Why this is yours and not the agent's.** `/krish` sits behind an Authentik forward-auth edge.
Reaching it requires signing in, and an agent must not enter credentials or handle your session.
This has been attempted and stopped at the login flow — no rollout, gate, or reconnaissance result
has ever been observed from the agent's side, and none is claimed. Everything below is unverified
until you run it.

**Two expectations to set before you start, so a correct result does not look like a failure:**

1. **A failed scan returns HTTP 200**, with `status: "refused"` and a named gate. Only a concurrent
   scan returns 409. A refusal is the system working, not breaking.
2. **`records_failing_full_schema > 0` is likely and is a useful result.** Dean's guide says schema
   conformance is "expected but **unverified**" and that "finding drift is a useful result, not a
   problem with the database". Do not treat drift as a bug to be worked around.

---

## Part 1 — Rollout (G1)

Sign in to `https://isaac.slac.stanford.edu/krish` first, so the session cookie is present.

### 1.1 Health — `GET /krish/api/health`

| Field | Expected | Meaning if different |
|---|---|---|
| `commit` | the merge SHA you are verifying (`91b74f8` or later) | Flux has not rolled yet — wait and re-check, do not chase it |
| `mode` | `synthetic-only` | correct and expected; it describes the **workspace**, not the database |
| `database.configured` | `true` | `false` means `PGHOST` is not reaching the pod → Dean |
| `database.classification` | `isolated-app-postgres` | — |
| `database.contains_production_derived_records` | `true` | — |
| `database.record_display` | `closed` | anything else is a **stop-and-report** |

Health opens **no database connection** by design — it is the Kubernetes readiness-probe target, and
a database outage must never take the pod out of service. Its `last_recon` is a per-process memo, not
live state.

### 1.2 Reconnaissance — `GET /krish/api/runtime/database/recon`

`database.gates` is an object with exactly **seven** boolean keys. These are the names you will
actually see in the JSON — all seven should be `true`:

- [ ] `database_identity`
- [ ] `current_user`
- [ ] `session_user`
- [ ] `tls`
- [ ] `records_table_present`
- [ ] `transaction_read_only`
- [ ] `not_production_shaped`

If the scan **refuses**, `refusal_gate` names the gate that stopped it, and that name comes from a
wider internal set than the seven above — it may also be `opt_in`, `pgdatabase_env`, `no_mutation`,
or `schema_root`. A refusal is a complete, honest answer; send it as-is and I will classify whether
it is ours, Dean's, or the environment's.

Check integrity:

- [ ] `rows_modified` is **0**
- [ ] `rows_before` equals `rows_after`
- [ ] `dml_statements_issued` is **0**
- [ ] `partial_schema_validation_runs` is **0**
- [ ] `schema_fingerprint` identical before and after; `schema_stable_across_run` is `true`

### 1.3 Read the JSON yourself — do not trust the tests

Scan the whole response for anything that should never appear:

- [ ] no record ID (raw or hashed) — only `record_id_digest_count`
- [ ] no record title
- [ ] no scientific value
- [ ] no evidence content
- [ ] no full or partial record JSON
- [ ] no person's name or identity
- [ ] no host, port, username, password, secret name, or connection string

If **any** of these appears, stop and send it to me before sharing the response further.

### 1.4 UI spot-check

- [ ] Top-bar chip reads `Synthetic workspace · test DB diagnostics`
      (or `· test DB check failed` if the last scan refused — both are honest)
- [ ] My Experiments, Record Detail, Statistics, Project Memory all behave exactly as before
- [ ] No record from the database appears anywhere in the UI
- [ ] Browser console: no errors

### 1.5 Send back

Paste the recon JSON. **It is safe by construction** — that is the whole design — but §1.3 is your
independent check on that claim, and it is worth doing precisely because nobody has ever seen the
real output.

---

## Part 2 — Responsive and 200% zoom sign-off (G4)

Still open from Phase 33/34, and still yours. Automated coverage from the browser/accessibility
slice, where it exists, runs against a **local** instance only — it can never run against `/krish`,
because of the Authentik edge. Automation does not close this gate.

Surfaces: My Experiments · Record Detail · Guided Completion · Evidence · Export Readiness ·
Project Memory (incl. Graph) · Governance (incl. Validator) · Statistics · Settings (all five tabs).

Viewports: **1280×800**, **1024×768**, **768×1024**, **375×812**.

Then **real browser zoom at 200%** (`Cmd +` / `Ctrl +`, not a narrow window — they are genuinely
different: zoom halves the CSS layout viewport *and* doubles device pixel ratio).

At each: no clipping, no overlap, no horizontal page scroll, focus visible when tabbing, dialogs
dismissable with Escape.

---

## Part 3 — Two things that need your decision, not your testing

- **Personal deployments** are still live, public and unauthenticated; Railway is 77 commits stale
  and has a **persistent volume**, so deleting destroys data that pausing preserves. Facts and an
  approval-gated order are in [`personal-deployment-retirement.md`](personal-deployment-retirement.md).
  Recommendation: do nothing until G1 closes.
- **Compression** — one observation would settle a deferred performance question. In DevTools →
  Network, load `/krish` and check whether a `.js` asset response carries
  `content-encoding: gzip` or `br`. If it does, the app should add nothing. If it does not, adding
  compression is worth a slice. The ingress config lives in `isaac-k8`, which is Dean's and not in
  this repository, so this cannot be checked any other way from here.

---

## Part 4 — Questions for Dean (not yours to answer)

- **G2** — may the hosted app display per-record fields from `metadata_assistant`, and to whom?
  Everything real-record-facing is blocked on this and is deliberately unbuilt.
- **G3** — Slice 2A already returns `by_instance_path`, `distinct_structural_signatures` and link
  counts. These are record-*derived* structural facts beyond his enumerated aggregate list, though
  none emits a value, title or id. Were they within what he intended, or should any be withdrawn?
