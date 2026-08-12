# Hosted application of `0002_runs` — verification evidence

**Date recorded:** 2026-08-12 · **Applied:** 2026-08-12 00:30 UTC · **Applied by:** Dean, the
infrastructure owner.

Migration `0002_runs` **has been applied to the hosted database.** The approval packet that was
reviewed before this happened is
[`../migration-approval-packet-0002.md`](../migration-approval-packet-0002.md). It is preserved as
the record of *what was approved and why*; this page is the record of *what changed*, and — with
equal weight — of what is **not** established by it.

This page follows the structure of
[`hosted-0001-verification-2026-08-09.md`](hosted-0001-verification-2026-08-09.md) deliberately, so
the two can be compared line for line.

---

## 0. What kind of evidence this is

> ### OPERATOR TESTIMONY, NOT A CAPTURED ARTIFACT.
>
> Every figure in §2 was **reported by Dean**. No response body, `psql` transcript, or log is
> committed to this repository, and none was inspected here. **No agent connected to the hosted
> database**, no kubeconfig, port-forward or Kubernetes Secret was requested or used, and the rule at
> `docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52` is untouched.
>
> This is the same evidentiary standing as the single DB-recon run and the Authentik header probe
> (`CLAUDE.md` §15; `identity-trust-contract.md` §6A): dated, attributed and accepted, but **not
> re-checkable from this repository.** Do not upgrade it by confident phrasing.

**One thing on this page IS re-checkable, and it is the one that matters most for identity of
content** — the two SHA-256 digests. See §1.

---

## 1. Hash verification — MEASURED HERE, and it MATCHES

Dean reported the digests of the SQL he applied. They were recomputed against the committed files in
this working tree:

```bash
shasum -a 256 apps/api/isaac_api/migrations/0002_runs.sql \
              apps/api/isaac_api/migrations/0002_runs.rollback.sql
```

| File | Digest Dean reported | Digest measured here | Verdict |
|---|---|---|---|
| `0002_runs.sql` | `c96e308d7fdfd508ab2c2aeffb08abcb18a88aae84db6f1d08b83f9cba8fda3e` | `c96e308d7fdfd508ab2c2aeffb08abcb18a88aae84db6f1d08b83f9cba8fda3e` | **MATCH** |
| `0002_runs.rollback.sql` | `0206012116a443fb301e9c161b5eb2ffcfe0e99ee6f460ce83d80e30d327cdd5` | `0206012116a443fb301e9c161b5eb2ffcfe0e99ee6f460ce83d80e30d327cdd5` | **MATCH** |

Both equal the digests in the approval packet's own table and in §12A.4 of that packet. **So the SQL
Dean applied is byte-identical to the SQL Krish approved**, which is precisely the property the
packet's hash table exists to make checkable — and which it once failed to provide (the forward hash
was stale from `90b432d` until 2026-08-10; see the packet header).

**Scope this precisely.** A matching digest establishes that Dean and this repository were looking at
the same bytes. It does not establish that those bytes are what the server executed — that is Dean's
report, not an observation here.

---

## 2. What Dean reported

### 2.1 Target

| | |
|---|---|
| namespace | `metadata-assistant` |
| deployment | `deploy/metadata-assistant` |
| database | `metadata_assistant` |
| CNPG primary | `isaac-psql-2` |

The database name matches the runner's own hard gate: `db_migrate` refuses unless `PGDATABASE` is
exactly `metadata_assistant`, and re-verifies server-side with `current_database()`.

### 2.2 Outcome

| Item | Reported |
|---|---|
| `0001_experiments` already present beforehand | yes |
| version applied | `0002_runs` **alone** — not `0001_experiments, 0002_runs` |
| `isaac_schema_migrations` afterwards | contains **both** versions |
| `isaac_runs` table | created; PK, FK, **five** CHECK constraints and the expected index **verified from the hosted server** |
| `ON DELETE` clause | **none**, no `CASCADE` |
| `isaac_runs` row count | **0**, at deployed build `a524708` |
| second invocation | an **idempotent no-op** |
| application health afterwards | OK / `postgres` / `durable`; no errors |
| rollback | **not required** |

**"applied: `0002_runs` alone" is the check §9 of the packet tells the operator to make**, and it
came back the way the packet said it should: a list naming `0001_experiments` would have meant that
database's bookkeeping row for 0001 was missing. It was not.

**Constraint shape was read back from the server, not assumed.** That is the one place where Dean's
report goes beyond "the command exited 0": PK, FK, five CHECKs and the index were verified against
the running database, which is exactly what the packet's postchecks 3 and 4 ask for.

---

## 3. What Dean did NOT report — named as gaps, not glossed

`docs/dean-handoff-2026-08-11.md` §3 asked for a specific sanitized operator report. Four of its
items are absent from what was relayed. They are recorded here because a gap that is not written
down becomes, in a later session, a fact that was never checked:

| Requested by the handoff | Status |
|---|---|
| `records` count **before** and **after** | **NOT REPORTED.** This is postcheck 1 in the packet — *"the one that matters"*, the guard on the 30 production-derived rows. |
| `isaac_experiments` count **before** and **after** | **NOT REPORTED.** Postcheck 2. |
| the `isaac_schema_migrations` rows themselves (versions + `applied_utc`) | **PARTIAL** — the report says both versions are present; the rows were not quoted. |
| hosted engine version / build string | **NOT REPORTED.** Parity with PostgreSQL 18 remains documented (`postgres-test-db-guide.md`), not measured. |

**How much this matters, stated honestly rather than either way.** The migration issues **zero DML**
and names `records` in no statement of either file — that is pinned by
`test_no_committed_migration_may_reference_the_production_table` and re-verified by the digest match
in §1. So there is no mechanism by which either count *could* have moved. What is missing is the
**measurement** that would have turned "no mechanism exists" into "and it did not happen". Do not
write that the corpus was verified unchanged after `0002`. It was not measured.

---

## 4. What this establishes

1. `isaac_runs` exists in the hosted database with the shape the approval packet describes, read back
   from the server.
2. `isaac_schema_migrations` records both `0001_experiments` and `0002_runs`.
3. The apply is idempotent in the hosted environment, not only against CI's `postgres:18` service
   container.
4. The application is unaffected — health `OK` / `postgres` / `durable`, which is the same reading as
   before the migration, exactly as §6 of the packet predicted (**no statement the application can
   issue names `isaac_runs`**, so identical behaviour applied and unapplied is the expected result,
   not a surprise).
5. The table is **empty**, which is the same prediction: nothing writes it yet.

## 5. What this does NOT establish

- **No agent observed any of it.** §0.
- **The corpus was not re-counted.** §3.
- **No row was read back out of `isaac_runs`** — there are none, so nothing could be.
- **`row count 0 at deployed build a524708` is a fact about that build, not a standing invariant.**
  It stays 0 only while no code writes the table; the run write path is a later slice.
- **No image build or rollout was observed from this environment.** `/krish` sits behind an Authentik
  edge this environment cannot authenticate to.
- **The locking analysis in packet §5 remains reasoned, not measured.** No `pg_locks` observation
  exists, before or after.

## 6. What has NOT changed, and must not be read as having changed

| Thing | Status |
|---|---|
| Gate **G2** — hosted per-record display | **CLOSED.** Dean's 2026-08-12 response does not mention it. Applying a migration is not a visibility decision. |
| Gate **G3** — the five withheld aggregates | **OPEN.** Not addressed in this response. |
| The agent-side rule barring a laptop or CI connection to the database | **UNCHANGED and binding** (`2026-07-24-phase-37-readiness-plan.md:48-52`). Dean applying a migration transfers no infrastructure authority to any agent. |
| `mode: synthetic-only` | **UNCHANGED.** It describes the *workspace*. |
| The verification truth plane, `db_provider`, `db_recon`, the official validator and export | **UNCHANGED.** No code was changed in producing this evidence; this slice is documentation only. |
| Migrations `0003`+ | **DO NOT EXIST.** Each will need its own packet and its own approval. Two applied migrations do not establish a standing permission for a third. |
| The run write path | **NOT AUTHORIZED BY THIS.** A table existing is not permission to write it. `db_write.OWNED_TABLES` listing `isaac_runs` "grants nothing on its own" (packet §4). |
