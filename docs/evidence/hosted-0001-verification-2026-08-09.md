# Hosted application of `0001_experiments` — verification evidence

**Date:** 2026-08-09 · **Hosted commit observed:** `5632300ee6c72f61f4c4e532bba41b8fdf01e728`

Migration `0001_experiments` **has been applied to the hosted database.** It was applied by
**Dean**, the infrastructure owner, who reported it as *"ok those tables are added to the db"*.
This document records what was measured afterwards, and — with equal weight — what was **not**.

The approval packet that was reviewed before this happened is
[`../migration-approval-packet-0001.md`](../migration-approval-packet-0001.md). It is preserved
unchanged as the record of *what was approved and why it was blocked*; this page is the record of
*what changed*.

---

## 0. What kind of evidence this is

Three separate things are recorded below, and they are **not** of equal strength. The section
headings say which is which, and no reader should have to work it out.

| Kind | Applies to |
|---|---|
| **Measured, in an authenticated browser session on 2026-08-09** | the `/api/health` body, the two recon runs, the create, the subsequent `GET /api/experiments` |
| **Structural inference from committed code** | that the created experiment's row is physically in PostgreSQL (§3) |
| ~~**Not measured at all**~~ → **Measured later the same day** | pod-restart durability — §4 said it was unmeasured; **§4.1 supersedes that**, after a deployment replaced the pod on its own. Read §4.1 for what it does and does not license. |

**No agent connected to the database.** The reconnaissance ran **inside the deployed pod**, which
is the design of Slice 2A and the only authorized execution path. No kubeconfig, port-forward or
Secret was requested or used, and the rule at
`docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52` was not exercised, tested, or
weakened. Applying the migration was likewise **not** an agent action.

**By what route Dean applied it is not recorded here.** `docs/create-experiment-persistence.md` §0
sets out five options (A–E) and this document cannot say which was taken. That is an open
question, not an omission being glossed: the *effect* is measured, the *method* is not.

### 0.1 One evidentiary status changed slightly — and it is NOT the masking claim

Every previous hosted recon run left **operator testimony and no artifact**, because the endpoint
keeps its result in process memory only (see
[`private-30-verification-2026-08-08.md`](private-30-verification-2026-08-08.md) §0.2, and
`docs/where-the-30-records-are.md:204`). This run is the first for which a **response body was
inspected** rather than read off a rendered screen. That is the whole of the change, and it is a
small one: it improves how the *fields listed in §1.2* were read. It does not widen what was read.

**CORRECTED 2026-08-09. An earlier revision of this section claimed more than was done**, and the
correction is recorded rather than silently swapped, because overstating an evidentiary status in
an evidence file is the one failure this file exists to avoid. It said that the claim that
`db_recon.safe_key_segment` masks what it is supposed to mask *"is now backed by code review plus
one inspected response body"*. **It is not. That claim remains backed by code review alone**, which
is exactly the position `CLAUDE.md` §15 states — the masking *"holds under static review; note this
is code review, **not** a runtime observation"* — and nothing here revises it.

Two reasons, either of which is sufficient on its own:

- **No leak scan was performed on that body.** Nobody looked for unmasked content. Reading a field
  and checking a field for leakage are different acts, and only the first happened.
- **The fields where masking operates were not among those inspected.** `safe_key_segment` masks
  the *key segments* of `by_rule_family` and `by_schema_path`. §1.2 enumerates scalar counts, two
  booleans, and one list of literal constant field names — none of which passes through that
  function at all. Reading eleven integers observes nothing about masking.

The narrower thing that a reader may take from this run is only this: for the enumerated fields,
the values in §1.2 were read from a response body rather than off a screen.

Two further precisions about *this* page, so it is not read as more than it is:

- the `/api/health` body in §1 is reproduced **verbatim** as returned;
- for the recon, this page records the **enumerated fields below**. The full response body is not
  committed to this repository, so a later reader can check the fields against this list but
  cannot re-derive them from a stored artifact.

---

## 1. What was measured

### 1.1 `GET https://isaac.slac.stanford.edu/krish/api/health`

```json
{"status":"ok","mode":"synthetic-only","core":"isaac_records","version":"0.1.0","commit":"5632300ee6c72f61f4c4e532bba41b8fdf01e728","database":{"configured":true,"classification":"isolated-app-postgres","contains_production_derived_records":true,"record_display":"closed","last_recon":null},"experiment_storage":{"configured":true,"backend":"postgres","durable":true,"state":"durable"}}
```

Three things in that body are worth reading deliberately:

- **`experiment_storage.state` is `durable`**, where the same block read
  `{durable: false, state: "unavailable"}` on 2026-08-08. This is the observable signature of the
  migration having been applied.
- **`record_display` is still `closed`.** Gate **G2** is untouched.
- **`commit` is `5632300`**, which is the local `main` head this document was written against. So
  the code the measurements ran against is the code in this repository, not an older image.
- **`last_recon` is `null`, and that is correct rather than puzzling.** It does not contradict the
  two recon runs in §1.2, and it is not a hint of a second replica answering the health read.
  **This health read came FIRST**, before either scan; the two scans then ran at 21:40:25Z and
  21:41:42Z. `last_recon` is process-local state written by `_db_recon_cache_put`
  (`apps/api/isaac_api/routes.py:5106`) and read back at `routes.py:901`, so at the moment this
  body was returned no recon had yet run in that process and `null` is the only correct answer.

### 1.2 `GET .../krish/api/runtime/database/recon` — run twice

Run 1 at **21:40:25Z**, run 2 at **21:41:42Z** — both **after** the `/api/health` read in §1.1,
which is why that body reports `last_recon: null`. Run 2 was taken **after** the experiment in
§1.3 was created. Both runs returned:

| Field | Value |
|---|---|
| `dataset.total_records` | **30** |
| `expected_seed_rows` | 30 |
| `seed_count_matches` | `true` |
| `records_passing_full_schema` | **30** |
| `records_failing_full_schema` | **0** |
| `total_validation_issues` | **0** |
| `integrity.rows_before` | 30 |
| `integrity.rows_after` | 30 |
| `integrity.rows_modified` | **0** |
| `dml_statements_issued` | **0** |
| `ddl_statements_issued` | **0** |
| `gates.records_table_present` | `true` |
| `withheld_pending_visibility_decision` | `["by_instance_path","distinct_structural_signatures","total_link_count","dangling_link_count","vocabulary_term_count"]` |

**The second run is the load-bearing one.** It was taken after an experiment had been created
through the hosted UI, and it still reports 30 records, 0 rows modified, 0 DML and 0 DDL. So
**creating an experiment did not perturb the production-derived corpus** — which is what
`db_write.OWNED_TABLES` and `_FORBIDDEN_TABLES` were built to guarantee, now observed on the
hosted database rather than only in CI against a `postgres:18` service container.

The five withheld aggregates are still withheld and still named. **Gate G3 remains OPEN** pending
Dean's answer; nothing here restores any of them.

### 1.3 An experiment was created through the hosted UI

| Field | Value |
|---|---|
| Experiment id | `01KZM7HYJVQY1C0X3KFV805YT2` |
| Title | `Durability check after 0001 (2026-08-09)` |
| `status` | `needs_attention` |
| `pending_count` | 3 |
| `exported` | `false` |

`GET .../krish/api/experiments` subsequently returned it — i.e. it survived a full page navigation
and a **fresh HTTP request**.

This identifier and title belong to an **application-created** experiment made for this check.
They are not from the production-derived thirty, and publishing them is not a G2 disclosure.

---

## 2. What this establishes

1. **`isaac_experiments` and `isaac_schema_migrations` exist in the hosted database.** A
   `POST /api/experiments` that reached the durable path and returned success cannot have happened
   otherwise (§3).
2. **The create path works end to end on the deployed application** — mint, persist, list.
3. **The protected corpus was not touched**, measured after the write, not only before it (§1.2).
4. **The application's own durability disclosure is now affirmative** rather than degraded.

## 3. The one structural inference, and its exact basis

**Claim:** the row for `01KZM7HYJVQY1C0X3KFV805YT2` is in PostgreSQL.

**This is inferred from the application's own storage-selection and write logic, not observed in
the database.** No query was run against `isaac_experiments`. The inference chain, each link cited:

1. `database_configured` is `bool(PGHOST)` and nothing else
   (`apps/api/isaac_api/db_write.py:339-352`). `PGHOST` is the deployment's documented feature
   switch; **the filesystem fallback engages only when it is unset** (or when the `PGDATABASE`
   gate refuses the target).
2. `repository()` returns `FilesystemExperimentRepository` **only** when `ordinary_store()` is
   `None`, i.e. only when `_postgres_available()` is false
   (`apps/api/isaac_api/experiment_repository.py:821-860`).
3. `/api/health` reported `backend: "postgres"`, which `storage_status` derives from that same
   `_postgres_available` call (`experiment_repository.py:889, 910`). So the Postgres repository was
   the one selected.
4. **A failed durable write does not degrade to the filesystem.** `PostgresOrdinaryStore.persist`
   raises `StorageUnavailable` on any driver or server failure, which the app renders as a typed
   `503`, and *"failing here means the workspace file is not rewritten either, so the record is not
   left looking saved"* (`experiment_repository.py:84-88`, and `persist` at `:626-684`).

Therefore a create that **succeeded** and is **listed** implies the `INSERT … ON CONFLICT`
committed. That is a strong inference from code that is under test — and it is still an inference.
**Do not cite this document as evidence that a stored row was read back.** It was not.

## 4. What was NOT measured — read this before quoting anything above

- ~~**Pod-restart durability was not measured. Nobody restarted the pod.**~~ **SUPERSEDED the same
  day — see §4.1 below.** The original entry is kept rather than deleted, because the rest of this
  document was written under it and a reader needs to see that it changed. What was true when written:
  the evidence was (a) the application's own self-report `{backend: postgres, durable: true,
  state: durable}`, and (b) an experiment surviving a fresh HTTP request — neither of which is a
  restart.
- **`durable: true` is not by itself proof of a working write.** `storage_status` opens no
  connection, and *"the FIRST health read after a process start says `durable: true`, because
  nothing has been attempted yet"* (`experiment_repository.py:101-106`). What upgrades this reading
  from optimistic to meaningful is the successful create in §1.3, not the health value alone.
- **No database row was read back and compared.** Same limitation as
  `private-30-verification-2026-08-08.md` §7, C12, and for the same structural reason.
- **The 30-record figures are aggregate.** They establish nothing about any individual record.
- **No image build or rollout was observed from this environment.** The hosted `commit` value in
  §1.1 is what the deployment reported about itself; no build log, registry push, or Flux
  reconciliation was witnessed here.
- **Two runs, ninety-two seconds apart, on one deployment.** That is reproducibility within a
  session, not stability over time.

### 4.1 — Pod-restart durability, MEASURED later the same day (2026-08-09)

The restart happened on its own, as a side effect of shipping. Merging PRs #92, #91 and #94 built a
new image and Flux rolled it, so the pod serving `/krish` was **replaced** — not restarted by hand
for a test, which is why this was not available when §4 was written.

| Fact | Before the roll | After the roll |
|---|---|---|
| `/api/health` `commit` | `5632300ee6c72f61f4c4e532bba41b8fdf01e728` | `608f587199ba061d7cbb855312c9734845ddd32f` |
| `01KZM7HYJVQY1C0X3KFV805YT2` in `GET /api/experiments` | present | **present**, `pending_count: 3`, `created_utc: 2026-08-09T21:41:10Z` unchanged |
| `experiment_storage` | `{postgres, durable: true, state: durable}` | unchanged |

**The process really is new, and that is corroborated rather than inferred from the commit string.**
`last_recon` reads `null` after the roll. That value is populated by `_db_recon_cache_put` and held
in **process memory only** — and two recon scans had been run against the previous pod earlier that
day (§1.2), which had set it. A fresh `null` is therefore a second, independent witness that a
different process is answering.

**What this does and does not license.** It licenses: *an experiment created through the hosted UI
survived replacement of the pod serving it.* It does **not** license "verified durable across
restart" in the unqualified form §4 prohibited, for one specific reason worth keeping: this
repository cannot verify that the workspace volume is an `emptyDir`. The manifest lives in the
Dean-owned `isaac-k8`, and `CLAUDE.md` §15 records that **zero** `emptyDir` / `persistentVolumeClaim`
tokens appear in any in-repo YAML — the ephemerality is asserted by our own docs, not observed. If
the volume were in fact persistent, survival across a pod roll would not on its own isolate
PostgreSQL as the thing that preserved the row.

So the honest composite is: the row survived pod replacement, **and** the app reports
`backend: postgres`, **and** §3's structural inference shows the write path targets PostgreSQL
whenever `PGHOST` is set. Three independent lines pointing the same way. That is materially stronger
than what §4 recorded, and still short of reading the row back out of the database — which nothing in
this repository is authorized to do.


## 5. What has NOT changed, and must not be read as having changed

| Thing | Status |
|---|---|
| Migration **`0002`** | **UNAPPLIED and UNAUTHORIZED for hosted application.** It needs its own approval packet and its own explicit approval. Nothing here touches it. |
| Gate **G2** — hosted per-record display | **CLOSED.** `/api/health` still reports `record_display: "closed"`. "0001 is applied" says nothing about whether record content may be displayed; the database owner's default-closed decision is unchanged. |
| Gate **G3** — the five withheld aggregates | **OPEN**, pending Dean's answer. All five are still withheld and still named in `dataset.withheld_pending_visibility_decision`. |
| The agent-side rule barring a laptop or CI connection to the database | **UNCHANGED and binding** (`docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52`). |
| `mode: synthetic-only` | **UNCHANGED.** It describes the *workspace* — uploads refused, seeding from committed fixtures. It has never meant "no real data exists anywhere in the process". |
| The verification truth plane, `db_provider`, `db_recon`, the official validator and export | **UNCHANGED.** No code was changed in producing this evidence. |
