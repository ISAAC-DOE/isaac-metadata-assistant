# Migration approval packet — `0004_submissions`

> ## STATUS: **NOT APPROVED, NOT APPLIED, ANYWHERE.**
>
> This packet is a request. Nothing in it has been run against the hosted database, and no agent may
> run it. `CLAUDE.md` §15's hard stop is unchanged by the fact that `0001` and `0002` have both been
> applied by Dean: *"two migrations having been applied by the infrastructure owner is not a
> precedent, a delegation, or a standing permission; `0003` and later each need their own packet,
> their own owner approval, and their own operator action."*
>
> **Local and CI testing is authorized. Applying it to the hosted environment is the owner's act.**
> Do not request a kubeconfig, a port-forward, or a Secret, and do not connect to the SLAC database
> (`docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52`).
>
> **`0004_submissions` and `0003_revisions` are ONE decision, and must be applied together or not at all.**
> `0004_submissions` declares a foreign key into a table `0003_revisions` creates, so 0003 without
> 0004 leaves the application unable to record a submission, and 0004 without 0003 cannot be applied
> at all. `db_migrate` orders them lexicographically, so a single `--apply` does both in the right
> order. Read both packets before approving either.

## Authorization basis

**Stated in full here rather than by cross-reference, because a packet that cannot be read on its own
cannot be approved on its own.** It is the same basis `0003`'s packet records.

**What authorizes this work:**

1. **The project owner's instruction in the run that produced this slice** — build durable,
   attributable submission recording over the experiments this application creates.
2. **`CLAUDE.md` §15's 2026-08-07 narrow lift** of the blanket "no database write" prohibition,
   covering *"durable Create Experiment persistence in the existing app-owned PostgreSQL database,
   plus **the minimum supporting persistence architecture that feature requires**"*, and enumerating
   forward-only, idempotent migrations under `apps/api/isaac_api/migrations/` among the things it
   covers.

**AND THE GAP, STATED PLAINLY.** At the time this migration was written, `CLAUDE.md` §15's enumerated
list of app-owned tables named exactly three — `isaac_experiments`, `isaac_schema_migrations`, and
(added 2026-08-12) `isaac_runs`. **It named neither `isaac_submissions` nor `isaac_submission_runs`**,
nor the three tables `0003` creates, and `db_write.OWNED_TABLES` adds all five — which the slice had
to do, because the statement policy refuses a `CREATE TABLE` naming an unlisted table. So **no
committed sentence named these tables**, and the authorization basis was item 1 plus the "minimum
supporting persistence architecture" clause in item 2.

`CLAUDE.md` §15's own rule, added *because of* the `isaac_runs` incident, is that *"a slice that
cannot cite a committed sentence permitting what it does has not established its authorization basis,
and saying so is part of the slice."* This slice did **not** report the gap; an independent review
found it. The §15 list has been amended in the same change as this section, in the style of the
`isaac_runs` correction. **It is a recorded scope extension, not a pre-existing permission written
down late.**

**What none of this authorizes:** applying this migration to the hosted database (the owner's act —
see the STATUS block); any statement naming the production-derived `records` table; any read surface
over submissions or revisions; and any identity or role enforcement.

## The bytes being approved

| File | SHA-256 |
|---|---|
| `apps/api/isaac_api/migrations/0004_submissions.sql` | `0adabc629141f203ee3f27d3da5b4dabb5f5dad894de75e9639a157aea218f38` |
| `apps/api/isaac_api/migrations/0004_submissions.rollback.sql` | `a1a7962422c8f1be8d6b51a44a5fd44646311d482143db0693c436760af66403` |

Recompute before applying, and refuse if either differs:

```bash
shasum -a 256 apps/api/isaac_api/migrations/0004_submissions.sql \
              apps/api/isaac_api/migrations/0004_submissions.rollback.sql
```

That check is why this table exists. It is the only evidence that the bytes applied to the hosted
database are the bytes approved here, and `0002`'s packet records a period in which its own forward
digest had gone stale and nothing noticed.

---

## 1. Why this migration exists

**Submitting is not exporting, and this migration exists because the two are different acts.**

Export is a mechanical transform: it mints one official ISAAC record per run and writes an artifact
pair. It answers *"does this validate"*, it can be performed by any caller at any time, and it needs
no attributable person.

Submission is a **declaration by a person** — *"this experiment is finished, and I am the one saying
so."* It answers *"who finalised this, when, over exactly what content"*.

Nothing in `Experiment.to_state()`, in `isaac_experiments`, or in `isaac_runs` can answer that, and
**deriving "submitted" from "exported" would be a fabrication**: it would attribute a declaration
nobody made. `test_submission.py::test_exporting_records_no_submission_of_any_kind` pins that in the
one direction that matters.

Why it cannot live in the experiment document: the same two mechanical reasons `0003_revisions`'
packet §1 sets out. They are not repeated here.

## 2. The exact forward SQL

Commentary stripped. Four statements, separated by lines containing only `--;`:

```sql
CREATE TABLE IF NOT EXISTS isaac_submissions (
    submission_id      text        PRIMARY KEY
                       CONSTRAINT isaac_submissions_id_shape
                       CHECK (submission_id ~ '^[0-9A-Z]{26}$'),
    experiment_id      text        NOT NULL
                       CONSTRAINT isaac_submissions_experiment_fk
                       REFERENCES isaac_experiments (experiment_id),
    revision_id        text        NOT NULL
                       CONSTRAINT isaac_submissions_revision_fk
                       REFERENCES isaac_experiment_revisions (revision_id)
                       CONSTRAINT isaac_submissions_revision_unique
                       UNIQUE,
    content_signature  text        NOT NULL
                       CONSTRAINT isaac_submissions_signature_shape
                       CHECK (content_signature ~ '^[0-9a-f]{64}$'),
    idempotency_key    text
                       CONSTRAINT isaac_submissions_idempotency_key_non_empty
                       CHECK (idempotency_key IS NULL OR length(idempotency_key) > 0),
    unit_count         bigint      NOT NULL
                       CONSTRAINT isaac_submissions_unit_count_positive
                       CHECK (unit_count >= 1),
    conflict_summary   jsonb       NOT NULL DEFAULT '{}'
                       CONSTRAINT isaac_submissions_conflict_summary_is_object
                       CHECK (jsonb_typeof(conflict_summary) = 'object'),
    subject            text
                       CONSTRAINT isaac_submissions_subject_non_empty
                       CHECK (subject IS NULL OR length(subject) > 0),
    trust_basis        text        NOT NULL
                       CONSTRAINT isaac_submissions_trust_basis_known
                       CHECK (trust_basis IN ('unattributed', 'test_fixture',
                                              'verified_edge_assertion')),
    submitted_utc      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_submissions_signature_unique
    UNIQUE (experiment_id, content_signature),
    CONSTRAINT isaac_submissions_idempotency_unique
    UNIQUE (experiment_id, idempotency_key),
    CONSTRAINT isaac_submissions_attribution
    CHECK ((trust_basis = 'unattributed') = (subject IS NULL))
);

CREATE INDEX IF NOT EXISTS isaac_submissions_experiment_time_idx
    ON isaac_submissions (experiment_id, submitted_utc, submission_id);

CREATE TABLE IF NOT EXISTS isaac_submission_runs (
    submission_run_id  text        PRIMARY KEY
                       CONSTRAINT isaac_submission_runs_id_shape
                       CHECK (submission_run_id ~ '^[0-9A-Z]{26}$'),
    submission_id      text        NOT NULL
                       CONSTRAINT isaac_submission_runs_submission_fk
                       REFERENCES isaac_submissions (submission_id),
    unit_id            text        NOT NULL
                       CONSTRAINT isaac_submission_runs_unit_id_shape
                       CHECK (unit_id ~ '^[0-9A-Z]{26}$'),
    run_id             text
                       CONSTRAINT isaac_submission_runs_run_id_shape
                       CHECK (run_id IS NULL OR run_id ~ '^[0-9A-Z]{26}$'),
    record_id          text        NOT NULL
                       CONSTRAINT isaac_submission_runs_record_id_shape
                       CHECK (record_id ~ '^[0-9A-Z]{26}$'),
    created_utc        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_submission_runs_unit_unique
    UNIQUE (submission_id, unit_id),
    CONSTRAINT isaac_submission_runs_one_record_per_unit
    CHECK (record_id = unit_id),
    CONSTRAINT isaac_submission_runs_run_matches_unit
    CHECK (run_id IS NULL OR run_id = unit_id)
);

CREATE INDEX IF NOT EXISTS isaac_submission_runs_record_idx
    ON isaac_submission_runs (record_id, submission_id);
```

**Two tables. Two indexes. No `ALTER`, no `DROP`, no `TRUNCATE`, no data movement, no backfill.**

### Each element, and why it is there

| Element | Why |
|---|---|
| `isaac_submissions` | One row per act of submitting. `submission_id` names the ACT; the records it published are named in `isaac_submission_runs`. |
| `revision_id` FK + `UNIQUE` | **One submission per revision, enforced by the database.** The revision is the immutable snapshot of exactly what was submitted; a second submission over the same snapshot would be a second declaration over one body of content, with nothing to distinguish them. |
| `content_signature` + `UNIQUE (experiment_id, content_signature)` | **The natural idempotency key**, and the reason the route is safe across processes without a distributed lock: two callers submitting the same unchanged content compute the same signature and the database admits exactly one. It duplicates the column on the revision row deliberately — the uniqueness is a property of the *submission*, and a UNIQUE constraint cannot reach through a join. |
| `idempotency_key`, nullable + `UNIQUE (experiment_id, idempotency_key)` | An optional client token, echoed on a replay. PostgreSQL's default NULLS DISTINCT is what makes the nullable column work: any number of rows may carry NULL, while two rows may not share a non-NULL key for one experiment. `CHECK` non-empty when present, because `''` is a key every keyless retry could collide with. |
| `unit_count` + `CHECK >= 1` | A submission that published nothing is not a submission. |
| `conflict_summary jsonb` + object CHECK | See §3. |
| `subject` / `trust_basis` / `isaac_submissions_attribution` / `isaac_submissions_subject_non_empty` | Identical in meaning, closed set, paired CHECK **and non-empty CHECK** to `isaac_experiment_revisions` — see 0003's packet §2, including why the non-empty CHECK exists (review item M1: `''` is not NULL, so the pairing would read a row naming nobody as *attributed*). Stored on **both** rows because a revision may in future be captured by something other than a submission, and a submission's author is a fact about the submission. |
| `submitted_utc timestamptz NOT NULL DEFAULT now()` | **The server assigns the submission time.** No client value is accepted, and the API reports back what the database stamped rather than what the application guessed before the write. |
| `isaac_submission_runs` | One row per export unit published, which under contract §1 D1 is one row per official ISAAC record. |
| `CHECK (record_id = unit_id)` | **The one-run-one-record rule written into the schema.** `ExportUnit.mark_exported` already refuses to let a unit's target id and its record id diverge; this is the same invariant one layer down, where an application bug cannot reach it. Both columns are kept rather than collapsed because they *mean* different things — a unit is a thing to publish, a record is the published thing — and a schema that states the equality can be read without knowing the domain rule by heart. |
| `run_id` nullable + `CHECK (run_id IS NULL OR run_id = unit_id)` | NULL for the single unit of an experiment with no runs. **NULL rather than a copy of `unit_id`**: such an experiment *has* no run, and writing its own id into a column called `run_id` would assert one exists. |
| The two indexes | `isaac_submissions_experiment_time_idx` is the chronological listing — both UNIQUE constraints serve a *lookup* and neither can order by time — and it also serves the parent-side foreign-key check. `isaac_submission_runs_record_idx` is the reverse lookup from a record id back to the act that published it; **no code in this build issues that read yet**, and it is created now for the reason 0003's packet §2.2 gives. |

## 3. `conflict_summary` — recorded and disclosed, deliberately NOT gated on

A field becomes `conflicting_evidence` (`evidence_classify._classify_entry` rule 1) as soon as two
distinct non-null answers are recorded for it. **Ordinary editing produces exactly that:**
`routes._apply_run_field` **appends** a `user_confirmation` entry every time and never replaces one,
and **no route in this application removes an evidence entry.**

So a scientist who answers a question, notices a typo, and answers it again has manufactured a
conflict **they cannot clear through any surface this build offers.** Gating submission on it would
be a permanent, inescapable block produced by correcting a mistake.

It is therefore **recorded** in this column, **disclosed** in the response, and **blocks nothing** —
and `gating: "disclosed_not_gated"` is written into the stored object itself, so a reader who finds a
non-zero count can see from the object that it did not block anything.

**It carries counts and addresses, never values.** The conflicting values are in the revision snapshot
beside this row; copying them here would put scientific content into a column whose purpose is
navigation, and would give the same value two places to live.
`test_the_conflict_summary_carries_addresses_and_never_values` pins that.

## 4. What it deliberately does *not* do

* **It does not touch `records`.** Neither read, written, altered, nor referenced in a constraint.
* **It does not alter any table 0001, 0002 or 0003 created.**
* **It moves no data and backfills nothing.** Every existing experiment has zero submissions after
  this applies, which is the truth: none of them was ever submitted.
* **It writes no `ON DELETE` clause**, so no single statement can destroy a submission tree.
* **It does not make submission possible on the hosted deployment.** That additionally requires an
  attributable actor, which no hosted verifier provides — see §13.

## 5. Transaction and locking behaviour

One transaction, `statement_timeout` 15s, `lock_timeout` 3s, bookkeeping row inside it. The
`isaac_submissions` foreign keys take `SHARE ROW EXCLUSIVE` on `isaac_experiments` (which has rows)
and on `isaac_experiment_revisions` (which `0003` has just created empty). With a 3-second
`lock_timeout` the failure mode of a concurrent write is that **this migration refuses**, not that the
application blocks.

**No lock of any kind is taken on `records`.**

## 6. Idempotence, and the window while it is pending

Idempotent twice over — bookkeeping plus `CREATE ... IF NOT EXISTS` — exactly as 0001, 0002 and 0003.

The pending window is handled the same way 0003's packet §6 describes: `preflight` probes all five
relations with `to_regclass` **before any official record is materialised**, and the route returns a
typed `503` that publishes nothing.

## 7. Who can run it — and who cannot

Identical to 0003's packet §7. **No agent may apply this.**

## 8. Prechecks

Run 0003's prechecks 1–3, 4, 5, 7 and 8 unchanged (a single `--apply` does both migrations), plus:

```bash
# 6b. Confirm neither target table already exists (expect 0).
psql -Atc "select count(*) from information_schema.tables where table_schema='public'
           and table_name in ('isaac_submissions','isaac_submission_runs')"
```

## 9. The exact command

```bash
python scripts/db_migrate.py --apply
```

The same single command applies 0003 and then 0004. Expected output, exactly:

```
applied: 0003_revisions, 0004_submissions
```

## 10. Postchecks — what would prove it worked

**Postchecks 1 and 2 are REQUIRED and must be reported**, for the reason 0003's packet §10 gives:
`0002`'s §12C records both as *not reported*, and "no mechanism exists" is not the same as "it was
measured".

```bash
# 1. REQUIRED. Must be UNCHANGED from precheck 4.
psql -Atc "select count(*) from records"

# 2. REQUIRED. Must be UNCHANGED from precheck 5.
psql -Atc "select count(*) from isaac_experiments"

# 3. Both tables exist with the constraints this packet describes.
psql -c "\d+ isaac_submissions"
psql -c "\d+ isaac_submission_runs"

# 4. The two indexes exist with the columns named in §2.
psql -Atc "select indexname, indexdef from pg_indexes
           where tablename in ('isaac_submissions','isaac_submission_runs')
           order by indexname"

# 5. No ON DELETE action anywhere (expect every confdeltype to be 'a' = NO ACTION).
psql -Atc "select conname, confdeltype from pg_constraint
           where conrelid::regclass::text like 'isaac_submission%' and contype = 'f'"

# 6. The versions are recorded. Quote the rows verbatim.
psql -Atc "select version, applied_utc from isaac_schema_migrations order by version"

# 7. Both are empty. Nothing backfills them.
psql -Atc "select (select count(*) from isaac_submissions),
                  (select count(*) from isaac_submission_runs)"

# 8. Idempotence: a second run applies nothing.
python scripts/db_migrate.py --apply     # -> nothing to apply (every migration is already recorded)

# 9. The engine build string.
psql -Atc "select version()"
```

**10. The application is unaffected**, and the new capability is correctly reported as unavailable:
`/api/health` → `experiment_storage {backend: "postgres", durable: true, state: "durable"}` unchanged,
and `submission {configuration_permits: false, blockers: ["no_attributable_actor"], basis:
"configuration_only", actor_trust_basis: null}`. **A `submission` block reporting
`configuration_permits: true` on the hosted deployment after this is applied would be a defect** — it
would mean a verifier had been configured, which is a separate, unapproved decision.

## 11. Rollback

```bash
psql -v ON_ERROR_STOP=1 -f apps/api/isaac_api/migrations/0004_submissions.rollback.sql
```

Unreachable from the application, for the same two reasons 0003's packet §11 gives, and carrying the
same honest difference about its `DELETE` against the bookkeeping table.

### ORDER MATTERS, twice over

* **Within the file:** `isaac_submission_runs` references `isaac_submissions`, no `CASCADE`, so the
  child goes first. The file does this.
* **Across files: THIS FILE MUST RUN FIRST OF ALL FOUR ROLLBACKS.** `isaac_submissions` references
  both `isaac_experiments` (0001) and `isaac_experiment_revisions` (0003), so each of those rollbacks
  fails while these tables exist. Full order: **0004, 0003, 0002, 0001.**

### What rolling back costs

**Every record of who submitted what, irrecoverably.** There is no second copy. The revision snapshots
in 0003 survive, so the *content* is not lost — but the declaration, its author and its timestamp are.
Dump first:

```bash
psql -c "\copy (SELECT * FROM isaac_submissions) TO 'submissions.csv' CSV HEADER"
psql -c "\copy (SELECT * FROM isaac_submission_runs) TO 'submission-runs.csv' CSV HEADER"
```

### Roll back if

Same criteria as 0003's packet §11.

## 12. Evidence, and what remains unproven — read this before approving

### 12A. What has been executed, and where

Identical in structure to 0003's packet §12A, over the same two test files and the same CI job. The
local suite proves the committed **text** and the application's behaviour against an **in-process
connection double**; the `postgres-migration` job proves the SQL and the constraints against a real
`postgres:18`, and **has not yet run on this branch.**

Constraints CI's *"Prove every 0003 and 0004 constraint rejects what it claims to reject"* step
exercises for this migration specifically: the one-submission-per-revision uniqueness, the
content-signature uniqueness, the idempotency-key uniqueness **and** its NULLS DISTINCT absence, the
empty-key CHECK, the `unit_count >= 1` CHECK, the attribution CHECK in both directions, the
one-run-one-record CHECK, the run-matches-unit CHECK, the per-submission unit uniqueness, and that
each foreign key **refuses a parent delete** rather than cascading.

### 12B. What has NOT been executed

**No PostgreSQL has ever executed this file.** Same statement, same reasons, same limits as 0003's
packet §12B, and the same distinction between what CI removes and what only the owner applying it can.

### 12C. The immutability limit

Identical to 0003's packet §12C, and it applies to these two tables equally: **append-only by
statement inventory and by test, not by the database.** Nothing here may be described as immutable at
the database level.

## 13. What this packet does not cover

* **`0003_revisions`.** Separate packet, same decision — read both. This migration cannot be applied
  without it.
* **Making submission actually work on the hosted deployment.** That needs an attributable actor, and
  **no verifier that can prove edge traversal exists.** Q4 is answered against us: the Service is a
  plain ClusterIP with no NetworkPolicy, so any in-cluster pod can forge a forwarded identity header.
  Until a trusted authentication boundary is built and independently reviewed — a separate, unapproved
  decision — every hosted submission is refused `409 human_actor_required`, and that refusal is the
  correct behaviour rather than a gap this migration closes.
* **Any read surface over submissions.** Nothing lists or renders one to a scientist.
* **The production-derived `records` table**, in any way at all.
* **Any hosted action.** Applying this is the owner's act.
