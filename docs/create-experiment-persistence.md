# Create Experiment — durable persistence

**Status, 2026-08-09: implemented, tested, and APPLIED to the hosted database.**
`0001_experiments` was applied by **Dean** on 2026-08-09. `/api/health` on `/krish` reports
`experiment_storage: {configured: true, backend: "postgres", durable: true, state: "durable"}`,
and an experiment created through the hosted UI survived a fresh HTTP request. Evidence, with
its limits attached:
[`docs/evidence/hosted-0001-verification-2026-08-09.md`](evidence/hosted-0001-verification-2026-08-09.md).

*Status before that: "implemented and tested. NOT applied to the hosted database." Applying the
migration was the owner's act, and this document is what he reviewed first.*

~~**Two things that did not change with it.** Migration `0002` is still unapplied and still
unauthorized for hosted application, and it needs its own packet. And **pod-restart durability
has not been measured** — see §0's closing note and the evidence page §4.~~

**BOTH HALVES OF THAT SENTENCE ARE NOW SUPERSEDED, and it is kept visible rather than replaced.**

- **`0002_runs` HAS been applied to the hosted database** — by Dean, 2026-08-12 00:30 UTC. It did get
  its own packet ([`migration-approval-packet-0002.md`](migration-approval-packet-0002.md)) and its
  own owner approval first, which is why the sentence above was the right thing to say at the time.
  Evidence, with every gap named:
  [`evidence/hosted-0002-verification-2026-08-12.md`](evidence/hosted-0002-verification-2026-08-12.md).
  **This changes nothing for this feature**: `isaac_runs` is empty, no statement this application can
  issue names it, and the create-experiment path behaves identically with `0002` applied and
  unapplied — pinned by `test_0002_is_inert_for_this_build_no_statement_names_isaac_runs`.
- **Pod-restart durability HAS been measured** — see the 0001 evidence page §4.1, which supersedes its
  own §4 after a deployment replaced the pod on its own.

**What has NOT changed:** applying a migration to the hosted database remains **the owner's act, not
an agent's**; `0003` and later each need their own packet and their own approval; and the prohibition
on an agent connecting to that database (`2026-07-24-phase-37-readiness-plan.md:48-52`) is untouched by
either application.

---

## 0. ~~OPEN BLOCKER~~ — RESOLVED 2026-08-09. Kept as the record of how the migration became reachable

> **RESOLVED.** This section asked "how, at all" the migration could be applied. It was applied by
> Dean on 2026-08-09. **This repository does not record which of options A–E below he used**, and
> that is an honest gap rather than a detail omitted for brevity: the *effect* is measured, the
> *method* is not. If it matters later — for example when `0002` needs applying — ask him rather
> than inferring it from this page.
>
> **The measured facts in the table below are still accurate statements about this repository**
> (re-checked 2026-08-09: `Dockerfile:42` still copies exactly one file out of `scripts/`, and the
> base image still has no `psql`). So option A was **not** taken in this repository, and the
> section is kept because the same question returns verbatim for `0002`.
>
> **It did return for `0002`, and it got the same non-answer (2026-08-12).** Dean applied `0002_runs`
> and reported the namespace, deployment, database and CNPG primary — but **not which of options A–E
> he used**. So this remains an open, honestly-named gap for both migrations. Ask him if it matters
> for `0003`.
>
> **The one row that IS superseded** is the third: applying a migration to hosted was not
> authorized *for this agent*, and still is not. It was applied by the operator, which is the path
> the rule always contemplated.

**Read this before anything else. It is the one decision only the owner can make,
and nothing below it can happen until he makes it.** *(Historical framing, 2026-08-07. He made it
on 2026-08-09.)*

Section 4 documents an operator procedure that begins `python scripts/db_migrate.py
--plan`. **That command cannot be run anywhere it needs to be run.** The procedure
was written without checking where the script actually lives at runtime, and it does
not survive the check.

### The measured facts

| Fact | Evidence |
|---|---|
| `scripts/db_migrate.py` is **not in the container image** | `Dockerfile` COPY allowlist ships exactly one file from `scripts/`: `COPY scripts/check_graphify_freshness.py scripts/check_graphify_freshness.py`. Nothing else under `scripts/` is copied. |
| There is **no `psql` in the image** | Base image is `python:3.11-slim`; no `postgresql-client` is installed. So the committed `.sql` files cannot be applied by hand from inside the pod either. |
| Applying a migration to hosted is **not authorized** | `CLAUDE.md` §15 — Phase 37, "PostgreSQL record repository, record loading, upload writes" is NOT authorized; this document's own §1 records that no SLAC database was contacted and no kubeconfig, port-forward or Secret was requested. |
| Running it from a laptop is **forbidden by project rule** | `docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52` blocks "any connection originating from a laptop or from CI; local kubeconfig, port-forward, or Secret retrieval". |

**One precision, because the gap is narrower than "the migration is not in the
image" and the narrower version is what makes the options tractable.** The
Dockerfile does `COPY apps/api/ apps/api/`, so **the runner module
(`apps/api/isaac_api/db_migrate.py`) and both committed `.sql` files
(`apps/api/isaac_api/migrations/`) ARE in the image.** What is missing is only the
thin CLI wrapper that gives them a command line. That is why option A below costs
one line rather than a redesign.

### Why this mattered when it was written *(2026-08-07; resolved 2026-08-09)*

`docs/postgres-test-db-guide.md:160-162`: *"PGHOST is already set in the deployed
pod, so anything placed behind the 'DB configured' switch goes live on the next
image roll."* The pod's `PGDATABASE` is `metadata_assistant`, exactly
`db_write.EXPECTED_DATABASE` — so the durable backend **selects itself on the next
deploy, whether or not the table exists.**

The application no longer breaks in that state (see §0.1), but it also cannot
*work*: creating an experiment returns `503` until the migration is applied. So the
question is not "when is it convenient" but "how, at all".

### The options. The owner must choose one; none of them is taken here.

| Option | What it is | The trade-off, in one line |
|---|---|---|
| **A. Add `scripts/db_migrate.py` to the Dockerfile COPY allowlist** | One line, so an operator can `kubectl exec … python scripts/db_migrate.py --plan/--apply` | Cheapest and most reviewable, but it puts a schema-changing command inside the running image, where anyone with `exec` can invoke it. |
| **B. A one-shot Kubernetes Job** | A separate manifest running the same image with `--apply`, applied deliberately and then deleted | Auditable and outside the serving pod, but it is an `isaac-k8` change, which is Dean-owned and out of scope for this repository. |
| **C. A guarded admin HTTP route** | e.g. `POST /api/admin/migrate` behind a typed confirmation | Needs no cluster access at all, but it makes a schema change reachable over HTTP — the exact shape `db_write`'s whole design exists to keep out of the app. **Recommend against.** |
| **D. Operator applies the SQL directly** | A human with a SLAC cluster context runs the committed `.sql` with psql from their own machine | No repository change, and it keeps the app unable to migrate itself — but it needs someone who holds that context, and this repository contains no evidence that Krish does (`docs/where-the-30-records-are.md` lists it as inferred/unknown). |
| **E. Do nothing yet** | Ship the code; leave the feature returning `503` on hosted | Honest and safe; the feature is simply not usable on the deployed app until one of A–D happens. |

**Nothing was applied, added to the image, or run against any database in
preparing this note.** Option A in particular was deliberately NOT taken on the
implementer's own initiative: it changes what a deployed image can do to its own
schema, which is an owner's decision, not a tidy-up.

### §0.1 — What the app does when the migration has NOT been applied

*(Written as "in the meantime". Re-titled 2026-08-09: this is no longer the hosted deployment's
state, but it is still the state of a fresh environment, a rolled-back one, and the window before
any future migration — so the behaviour below is a live property and the table is unchanged. The
`postgres-migration` CI job proves it on every PR, deliberately before it applies anything.)*

It **degrades, and discloses**, rather than failing. Verified by
`apps/api/tests/test_experiment_repository.py` §10 and by the CI step
*"Prove the app DEGRADES when the migration has not been applied yet"*:

| Operation | Un-migrated database |
|---|---|
| `GET /api/experiments` | **200**, with the workspace-directory view |
| `GET /api/experiments/{id}` (known) | **200** |
| `GET /api/experiments/{id}` (unknown) | **404** — not a 500 |
| `POST /api/experiments` | **503**, typed, and nothing is written anywhere |
| `GET /api/health` → `experiment_storage` | `durable: false`, `state: "unavailable"` |

The UI reads that state and stops promising durability. It does **not** silently
write an ephemeral record, because the reader was told their work is kept.

~~"it says the database is not answering and that creating will not work until it does"~~ —
corrected 2026-08-27. That described the copy accurately, and the copy was wrong: `unavailable`
has **two** causes and the sentence named only this one. The table above is the
`backend: "postgres"` row. The other cause is the `PGDATABASE` gate refusing the configured
name, where `_postgres_available()` is false, the filesystem repository is selected, and
`POST /api/experiments` answers **201** into a working directory that is not durable — its own
docstring documents that as the intended degradation. `state` does not separate the two;
`experiment_storage.backend` does, and the UI is given the state. So the copy
(`LABELS.storageUnavailable`, and the three Data & Privacy cards) now states the invariant that
holds under both — nothing created in this state is durable — and says outright that it cannot
tell which outcome applies. See `docs/deployment.md` for the measured pair.

---

## 1. What was authorized, and what was not

Authorized (2026-08-07, narrowly): durable Create Experiment persistence using the
existing app-owned PostgreSQL database, plus the minimum supporting persistence
architecture that feature requires.

Not authorized, and not done:

- modifying, reading, altering or migrating the `records` table — the
  production-derived 30-row sample;
- any change to the verification truth plane, `db_provider`, `db_recon`, or the
  official validator/export behaviour;
- any Dean-owned infrastructure change;
- destructive migration, `DROP` / `TRUNCATE` / `ALTER` of anything, or broad schema
  cleanup;
- **applying the migration to the hosted environment.** No SLAC database was
  contacted. No kubeconfig, port-forward or Secret was requested or used.

---

## 2. The migration

File: `apps/api/isaac_api/migrations/0001_experiments.sql`
Rollback: `apps/api/isaac_api/migrations/0001_experiments.rollback.sql`
Runner: `apps/api/isaac_api/db_migrate.py` · Operator CLI: `scripts/db_migrate.py`

Statements are separated by a line that is exactly `--;` (a SQL comment, so each
file stays valid runnable SQL for review with psql). Splitting on a bare `;` would
cut a statement in half inside the `CHECK` regex below.

### Exact SQL

```sql
CREATE TABLE IF NOT EXISTS isaac_schema_migrations (
    version      text        PRIMARY KEY,
    applied_utc  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS isaac_experiments (
    experiment_id  text        PRIMARY KEY
                   CONSTRAINT isaac_experiments_id_shape
                   CHECK (experiment_id ~ '^[0-9A-Z]{26}$'),
    state          jsonb       NOT NULL,
    created_utc    timestamptz NOT NULL DEFAULT now(),
    updated_utc    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS isaac_experiments_created_idx
    ON isaac_experiments (created_utc);
```

### Tables and columns created

| Object | Type | Purpose |
|---|---|---|
| `isaac_schema_migrations` | table | Migration bookkeeping. One row per applied version. |
| `isaac_schema_migrations.version` | `text` PK | The migration filename stem, e.g. `0001_experiments`. |
| `isaac_schema_migrations.applied_utc` | `timestamptz` | When it was applied. |
| `isaac_experiments` | table | One row per experiment **this application created**. |
| `isaac_experiments.experiment_id` | `text` PK, CHECK | The ULID. `text` not `char(26)` deliberately — `char(n)` blank-pads on read, which the verification path already has to strip. |
| `isaac_experiments.state` | `jsonb` NOT NULL | The same JSON document the filesystem repository writes to `experiment.json` (`workspace.Experiment.to_state()`). Stored whole rather than as a column per field, because the document's shape is owned by the truth core and a column schema here would become a second, drifting definition of it. |
| `isaac_experiments.created_utc` | `timestamptz` | Row creation. |
| `isaac_experiments.updated_utc` | `timestamptz` | Last upsert. |
| `isaac_experiments_created_idx` | index | The one read the app performs: every experiment, oldest first. |

Nothing else is created. No table that this application did not create is named
anywhere in the migration.

### Idempotence

Twice over, and both halves are proven in CI:

1. The bookkeeping table skips a version already recorded.
2. Every statement is `CREATE ... IF NOT EXISTS`, so re-running is a no-op **even
   if the bookkeeping row is lost**. CI deletes the bookkeeping rows and re-applies,
   then diffs `information_schema.columns` to prove the schema did not move.

One transaction per migration, with the bookkeeping row written inside it — so
"applied" and "recorded" cannot disagree.

---

## 3. Rollback strategy

`apps/api/isaac_api/migrations/0001_experiments.rollback.sql`:

```sql
DROP TABLE IF EXISTS isaac_experiments;
DROP TABLE IF EXISTS isaac_schema_migrations;
```

- **The application cannot run it.** Every statement is a `DROP`, and
  `db_write.WriteStatementPolicy` refuses `DROP` wherever it appears. The only way
  to run it is a human (or CI) driving psql deliberately. That is the intent: a
  rollback is an operator action, not something an app does to itself on a bad boot.
- **It names only tables `0001` created.** `records` is not named and must never be.
- **It destroys user data.** Every experiment a person created is deleted. Before
  running it against a database that has served real users, dump first:

  ```
  \copy (SELECT experiment_id, state FROM isaac_experiments) TO 'experiments.csv' CSV
  ```

- Dropping `isaac_experiments` drops its index and CHECK constraint with it.

---

## 4. Verification plan

### Already run, here

Measured on 2026-08-07, after the review-fix pass. Every figure here is quoted with
the command that produced it, and none is carried over from a previous revision —
the previous revision's backend figure (2787) was already stale when it was written.

- Backend suite: **2829 passed, 2 skipped**
  (`PYTHONPATH=src:apps/api pytest -q`), with **no** `PGHOST`, so the filesystem
  fallback is what the whole suite exercises.
- Frontend suite: **3149 passed / 126 files** (`cd apps/web && npx vitest run`).
- `tsc -b`: exit 0.
- Snapshot drift, BOTH committed artifacts (`build_memory_snapshot.py --check`
  with `--detail-out`): exit 0, no drift.
- `apps/api/tests/test_experiment_repository.py`: **91 tests** covering the route,
  the seam, the write path, the isolation refusals, the migration runner, the
  privilege-statement refusals, and the un-migrated-database degradation —
  **against an in-process fake driver**, which proves the shape and not the SQL.

### Specified in CI — and, since 2026-08-09, EXECUTED. `.github/workflows/ci.yml` → `postgres-migration`

**CORRECTED 2026-08-09, and the heading has now been wrong in both directions, which is why the
history is kept.** It first read *"Already run, in CI"* when the job had never run — false. It was
then corrected to *"NOT YET EXECUTED"* — true when written, and false by the time it was read.

Measured, with the command quoted rather than recalled:

```
$ gh run list --workflow=ci.yml -L 1 --json databaseId -q '.[0].databaseId' \
    | xargs -I{} gh run view {} --json jobs -q '.jobs[] | "\(.name) :: \(.conclusion)"'
migration and durable repository against a real PostgreSQL :: success
browser accessibility and responsive baseline :: success
frontend tests and build :: success
tests and synthetic demo :: success
```

That run is the merge of PR #89 (`5632300`, 2026-08-09T00:23:07Z) — the commit the hosted
deployment reports serving. So the steps enumerated below **have** run green against a real
`postgres:18` service container, and may now be quoted as results.

**What that does NOT license** is unchanged and is set out in *"What CI does NOT prove"* below: a
green service-container run is not a hosted rehearsal.

*The paragraph this section carried while the job was unrun is preserved, because the reasoning in
it is what kept the earlier false claim from being repeated:*

> **Read the heading literally.** An earlier revision of this section was titled
> *"Already run, in CI"*, and that was false: the job is new on this branch, the
> branch had not been pushed when it was written, and **this job has never run**.
> The steps below are what it is written to do, not what it has been observed doing.
> Nothing in this section may be quoted as a result until a run exists.

*(A run now exists, so that last sentence has been satisfied rather than overruled.)*

The version qualification stands regardless: a `postgres:18` service container is *pinned*, and
whether the hosted server is really 18 is a separate question answered below.

A `postgres:18` service container. `docs/postgres-test-db-guide.md:18` states the
SLAC cluster runs Postgres 18, so the version is **documented parity, not measured
parity** — this environment cannot reach the hosted server to confirm the running
version.

0. **THE UN-MIGRATED STATE, PROVEN FIRST.** Before anything is applied — the only
   point in the job at which that state exists — a database is configured and
   `isaac_experiments` does not exist. Assert the list returns **200** with the
   workspace view, an unknown id returns **404**, a known id returns **200**, the
   create returns a typed **503** having written nothing, and
   `/api/health.experiment_storage` reports `durable: false`,
   `state: "unavailable"`. *(Re-dated 2026-08-09, and the step is unchanged. This
   line read "This is the deployed pod's state on the next image roll (§0)" —
   true when written, false since `0001_experiments` was applied to the hosted
   database. What the step proves is still a live property: this is the state of
   a **fresh** environment, of a **rolled-back** one, and of the window before
   any future migration such as `0002`. Only the justification needed re-dating.)*
   The job previously stepped straight over it.
1. `--plan` reports `0001_experiments` and creates no application table.
2. Apply. Assert `applied: 0001_experiments`.
3. Apply again. Assert it is a no-op, and that `information_schema.columns` is
   unchanged. Then delete the bookkeeping rows, apply again, assert unchanged.
4. Diff `information_schema.tables` before and after: exactly
   `isaac_experiments isaac_schema_migrations` added, nothing removed.
5. A stand-in `records` table (synthetic rows, same shape as
   `db_provider.Q_RECORD_PAGE`) is seeded **before** the migration and asserted
   byte-identical after.
6. The durable repository end to end against the real engine: create, read the row
   back, `rmtree` the workspace to simulate a pod restart, and prove the list and
   the detail read still answer. Then open a worked-example session, prove the
   create is refused with 409, and prove the database gained nothing.
7. Run the documented rollback with psql; assert the table set returns to its
   pre-migration state and `records` is still byte-identical.

8. The application's own `records` digest check, taken **after** the repository
   step has run — so "the sample is untouched" covers the running write path and
   not only the DDL.

Two further guards live in the default `test` job: it asserts `PGHOST` is unset and
that `repository()` therefore selects the filesystem backend with `durable: false`.
That keeps the fallback covered by construction rather than by omission.

### Negative controls — run 2026-08-07, and one of them found a real defect

Every guard below was verified by **breaking it on purpose**, running the tests,
recording the result, and reverting. A control that produces zero failures is a
gap, not a pass.

| # | Mutation | Failures | Verdict |
|---|---|---|---|
| a | Create button rendered but not wired to the API | 3 | caught |
| b1 | tutorial gate removed from `workspace._ordinary_store` | 2 | caught |
| b2 | route's 409 removed; create writes into the tutorial scope | 2 | caught |
| c | client-supplied `id` accepted instead of server-minted | 2 | caught |
| d | repository selection ignores `PGHOST`, always filesystem | 5 | caught |
| e | UI claims durability while the filesystem repository is active | 2 | caught |
| f1 | migration gains `ALTER TABLE records ADD COLUMN …` | 3 | caught |
| f2 | migration gains `CREATE INDEX … ON records (record_id)` | **1** | **DEFECT — see below** |
| g | write path builds SQL by string interpolation | 3 | caught |

**Control f2 was the finding.** `WriteStatementPolicy` did not refuse it. `on` had
been deliberately kept out of `_TABLE_INTRODUCERS` so that
`INSERT … ON CONFLICT` would not be read as naming a table called `conflict` — but
that left *every* statement which attaches an object to a table unchecked, because
they all name the table after `ON`. `CREATE INDEX … ON records` and
`CREATE TRIGGER … ON records` both passed. Neither reads or writes a row, which is
why they read as harmless; both take a lock on the production-derived sample and
change its schema permanently.

The single failure it did produce came from a statement-**count** assertion
(`len(statements) == 3`), not from the policy. Had the statement replaced an
existing one rather than being appended, **nothing would have failed**.

Two independent fixes, because the first one is a grammar judgement and grammar is
where the bug lived:

1. `on` is now an introducer, with `conflict` excepted in `_table_after`;
2. `_FORBIDDEN_TABLES = ("records",)` refuses the identifier **anywhere in any
   statement, in any position**, with no syntax to get right.

Re-running control f2 after the fix produces **4 failures**, three of them from the
policy. The refusal set is pinned by
`test_the_statement_policy_refuses_anything_outside_this_applications_tables`, and a
new `test_no_committed_migration_may_reference_the_production_table` scans the
committed migration files directly.

### What CI does NOT prove

CI removes the *"is this valid PostgreSQL / is it idempotent / does it touch other
tables"* class of risk. It does **not** remove *"does this behave correctly against
the hosted database with its real 30-row dataset, its roles and its grants"*. Only
the owner applying it, deliberately, resolves that.

### What the owner should run, in order, when he chooses to apply

> **APPLIED 2026-08-09 by Dean, by a route this repository does not record — so the sequence below
> is the approved procedure, not a transcript of what ran.** The paragraph that follows is kept
> verbatim because it still describes this repository accurately and the same obstacle returns for
> `0002`.
>
> **This sequence is not runnable as written — see §0.** `scripts/db_migrate.py` is
> not in the container image and there is no `psql` in it either, so neither the
> Python command nor the raw SQL can be run from the pod; and running it from a
> laptop is blocked by project rule. The sequence below is the CORRECT sequence
> once the owner has chosen how the command becomes reachable (options A–E in §0).
> It is kept, rather than deleted, because the *steps* are right and only the
> *entry point* is missing.

```
# 1. see the plan. Applies nothing.
python scripts/db_migrate.py --plan
#    expect: pending: 0001_experiments

# 2. record the table set BEFORE, so the diff is his own measurement
psql -Atc "select table_name from information_schema.tables
           where table_schema='public' order by table_name"

# 3. record the real records table's digest BEFORE
psql -Atc "select md5(string_agg(record_id || data::text, '|' order by record_id))
           from records"

# 4. apply
python scripts/db_migrate.py --apply

# 5. re-run steps 2 and 3 and diff. Expect exactly two added tables and an
#    identical records digest.

# 6. hosted smoke: GET {base}/api/health -> experiment_storage should read
#    {"configured": true, "backend": "postgres", "durable": true,
#     "state": "durable"}
#    then create an experiment in the UI, restart the pod, and confirm it is
#    still listed.
#
#    BEFORE applying, the same block reads
#    {"configured": true, "backend": "postgres", "durable": false,
#     "state": "unavailable"} once anything has read the experiments list — which
#    is the honest signal that the migration has not been applied yet. On a pod
#    that has just started and been asked nothing, it reads `durable: true`,
#    because nothing has been attempted and /api/health may not open a connection
#    to find out. Read the list once, then read health.
```

---

## 5. Architecture

```
POST /api/experiments  (routes.py)
        │  knows nothing about storage
        ▼
experiment_repository.repository(env)      ← selection, environment-driven
        ├── FilesystemExperimentRepository   (no PGHOST)      durable: false
        └── PostgresExperimentRepository     (PGHOST + gate)  durable: true
                    │
                    ▼
            PostgresOrdinaryStore  ── persist() / hydrate()
                    │
                    ▼
            db_write.write_transaction  ── one connection, explicit transaction,
                                           statement policy, deterministic
                                           rollback and close
```

- **Selection** keys off `PGHOST`, the deployment's documented feature switch. No
  `PGHOST` ⇒ filesystem, which is every developer machine and every CI job except
  `postgres-migration`. `PGDATABASE` is then gated to `metadata_assistant`; a
  mismatch degrades to the filesystem and **says so** (`configured: true,
  durable: false`), rather than creating tables somewhere unintended.
- **The filesystem stays the working copy.** Postgres is the system of record for
  authoritative experiment *state*; the workspace directory is a cache of it. Every
  ordinary-scope `save()` writes through (durable write FIRST, so a failed write
  does not leave a change the reader can see); every ordinary-scope list, and a miss
  on a load, hydrates any row whose directory is gone.
- **Known limit, stated rather than discovered later:** exported ARTIFACT FILES
  (`records/<id>.json` and the evidence sidecar) live only in the workspace
  directory and are not in the database. A pod restart restores an exported
  record's state, including `record_id`, while its artifact files are gone. The
  artifact readers already tolerate that (`routes._read_artifact_json` → `None`,
  `dependencies.artifact_state` → `stale`), so it degrades to a state the app
  already handles. Persisting artifacts is a separate slice.

---

## 6. Tutorial isolation

**A worked-example session's records never reach the database.** Enforced three
times, at three levels, so one of them being wired wrongly is not enough:

1. `workspace.Experiment.save()` consults `_ordinary_store(session_id)`, which
   returns `None` for any non-`None` session before it looks at the environment.
2. `PostgresOrdinaryStore.refuse_if_not_persistable` **raises** `NotPersistable` on
   a non-`None` `session_id` — so a future caller that reaches it directly is
   refused, not merely unusual.
3. It raises on a canonical example id in **any** scope, so the five built-in
   examples cannot be made durable even from a workspace left by an older build
   that already holds them.

`POST /api/experiments` additionally refuses a `X-Isaac-Tutorial-Session` header
with `409 ordinary_scope_required`, writing nothing.

---

## 7. Safety properties of the write path

`apps/api/isaac_api/db_write.py` is a **separate** path from `db_provider` and
`db_recon`. Those two are read-only by construction (`SET TRANSACTION READ ONLY`,
server-side re-verification, a frozen statement allowlist) and are **unchanged** —
no guarantee on the verification path was weakened, reused, or relaxed.

- `OWNED_TABLES = {isaac_schema_migrations, isaac_experiments}`. `records` is
  deliberately, permanently absent.
- `WriteStatementPolicy` refuses `DROP`, `TRUNCATE`, `ALTER`, `GRANT`, `REVOKE`,
  `COPY`, `VACUUM`, `REINDEX`, `CLUSTER`, `ROLE`, `USER`, `DATABASE`, `EXTENSION`
  and `AUTHORIZATION` anywhere, and any statement naming a table outside
  `OWNED_TABLES`. Every statement the app issues is routed through it.
  - **The last five were added on 2026-08-07 because the module's own docstring
    claimed them and the code did not.** It stated that `CREATE ROLE` / `USER` /
    `DATABASE` / `EXTENSION` were refused "anywhere at all"; measured against the
    policy, all four were ACCEPTED, as were `SET ROLE postgres` and
    `SET SESSION AUTHORIZATION postgres`. In a module whose entire purpose is
    refusing statements, the docstring is the specification — so the list was
    extended to match it rather than the sentence softened to match the list.
    `SET ROLE` is included on its own merits: it changes the identity later
    statements run as, which is the one move that could make every other guard
    here irrelevant. All eight statements the application issues and all three
    committed migration statements were re-verified against the extended list.
  - **A known, accepted limit, now documented in `db_write.py` rather than
    lurking:** the policy is a tokenizer, not a SQL parser, so a forbidden verb
    assembled at run time inside a `DO $$ … $$` body is not seen. It is not
    reachable here — the only SQL that reaches the policy is a module-level
    constant or a committed migration file, both human-reviewed — and
    `db_migrate.split_statements` now REFUSES a migration containing a
    dollar-quote outright, both because it closes that route and because the
    line-based splitter would otherwise mangle such a body silently.
- Every value is a `%s` parameter. There is no caller-supplied SQL anywhere.
- One short-lived connection per call; `autocommit = False`; `SET LOCAL
  statement_timeout = 15s` and `lock_timeout = 3s`; a server-side
  `current_database()` check that refuses a redirected connection; rollback on any
  exception; cursor and connection closed in a `finally`.
- `application_name = isaac_app_write`, so an operator reading `pg_stat_activity`
  can tell it from `isaac_db_recon` and `isaac_record_verification`.
