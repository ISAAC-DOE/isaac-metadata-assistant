# Migration approval packet — `0005_run_projection`

> ## STATUS: **APPROVED BY THE PROJECT OWNER 2026-09-17. NOT APPLIED TO THE HOSTED DATABASE, ANYWHERE.**
>
> **Read both halves. They are different acts by different people, and collapsing them is the one
> misreading this block exists to prevent** — the same warning `0003` and `0004` carry, for the same
> reason.
>
> **The approval (Krish, project owner, 2026-09-17).** Krish approves the **exact bytes** recorded in
> the digest table below, conditional on a fresh SHA-256 recomputation matching this packet. That
> recomputation was performed before this line was written and is recorded in **§12**, together with
> four further mechanical checks — and a sixth, added in the same change, which verified §8A's own
> gate queries against the schema this migration declares. Both digests **match**, and they match in three independent places:
> the working tree, `git show origin/main:…`, and this packet's own table.
>
> The approval is of **these bytes and nothing else.** Editing either `.sql` file voids it: the digest
> stops matching and this packet then describes something other than what is on disk.
>
> **THE APPROVAL IS NOT AN APPLICATION, AND IT AUTHORIZES NO AGENT TO DO ANYTHING.** Applying this
> migration to the hosted database remains **the operator's act, and no agent may run it.** `CLAUDE.md` §15's hard stop is
> untouched: no agent may apply a migration, connect to the SLAC PostgreSQL, request a kubeconfig, a
> port-forward or a Secret, run the backfill, change Kubernetes, or perform the Stage-2b cutover.
> Owner approval is a **precondition** for the operator's step, never a substitute for it.
>
> **THIS APPROVAL ALSO DOES NOT AUTHORIZE THE STAGE-2b READ CUTOVER.** Creating the table and
> trusting it are two decisions. The gate is §8A's two queries plus a clean backfill, and it is
> restated as an ordered sequence in **§12A**.
>
> **TWO CORRECTIONS WERE MADE TO THIS PACKET IN THE SAME CHANGE THAT RECORDED THE APPROVAL**, because
> an operator reads this document before acting and a stale safety claim in it is worse than none:
> §4's *"nothing reads it"* is now **false** and is struck in place, and §6's code block showed the
> **unbounded** command while the prose authorized only the bounded one. See §12's checks 4 and 5.

> **POINTER, added 2026-08-25.** §9A below says its two new coverage items *"HAVE NOT YET RUN"*.
> **They have now run** — run `32800763199`, job `97660962127`, on `main` at `c153ec9`, every step
> `success`. The evidence, with the quoted job output, is in
> [`docs/dean-operator-addendum-2026-08-25.md`](dean-operator-addendum-2026-08-25.md) §2. §9A is left
> as written rather than rewritten, because this packet's own convention is that a claim promoted from
> "declared" to "proven" must be promoted by quoting a job, not by editing the sentence that said it
> had not happened. ~~**Approval status is unchanged: still NOT APPROVED.**~~ — **STALE as of
> 2026-09-17 and struck rather than deleted, because this pointer sits ABOVE the STATUS block and a
> reader scanning downward would meet it first.** The sentence was exactly true when written
> (2026-08-25) and described that date's state; the owner approved these bytes on **2026-09-17** —
> see the STATUS block immediately below and §12. **What has NOT changed, and is the half of this
> pointer still worth reading: NOT APPLIED ANYWHERE, and applying it is the operator's act.**

| | |
|---|---|
| Migration | `apps/api/isaac_api/migrations/0005_run_projection.sql` |
| SHA-256 (forward) | `86bf111cf030c15cb3d2349f428370476ad84262da9e5127a1e213c62da98304` |
| Rollback | `apps/api/isaac_api/migrations/0005_run_projection.rollback.sql` |
| SHA-256 (rollback) | `54a17432150525f75a6e94557a137029a3ce3fd41cea9debced361abda90e735` |
| Creates | one table, `isaac_run_projection`, and one index |
| Verbs used | `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`. Nothing else. |
| Touches `records` | **No.** The identifier does not appear in any statement, and a test reads the file off disk to assert it. |
| Touches `isaac_experiments`, `isaac_runs`, or the five submission tables | **No.** It declares a foreign key *into* `isaac_experiments`; it alters nothing. `ALTER` is a forbidden verb in `db_write._FORBIDDEN_KEYWORDS`. |
| Data moved | **None.** This migration creates an empty table. |

**Recompute the digests before approving.** They are the bytes this packet describes, and
if they differ from the file on disk then this packet describes something else:

```bash
shasum -a 256 apps/api/isaac_api/migrations/0005_run_projection.sql \
              apps/api/isaac_api/migrations/0005_run_projection.rollback.sql
```

---

## 1. Why this migration exists — a measured ambiguity, not a design preference

`0002_runs` (applied to the hosted database by Dean, 2026-08-12) made `isaac_runs` a
**shadow** of the experiment document. Nothing reads it. A reader cannot be written
against that alone, because

```sql
SELECT ... FROM isaac_runs WHERE experiment_id = %s
```

returning **zero rows** means *either* "this experiment has no runs" *or* "this
experiment's runs were never projected" — and both are reachable:

| How zero rows arises | Reachable? |
|---|---|
| The experiment genuinely has no runs | yes |
| Persisted before the shadow write shipped | yes — every pre-existing row |
| Persisted while `isaac_runs` was absent | **yes, routinely** — the image rolls out on merge and migrations are applied by hand afterwards |
| `0002` rolled back under a running pod | yes |

A reader that treated zero rows as "no runs" would **silently delete every run of every
pre-existing record** the first time it was switched on, and report success. This table
makes that unwritable: absence of a row is absence of a claim, and `run_count = 0` beside
a **matching version pair** is a positive statement that this experiment has no runs.

The full contract, including the four states every future read must distinguish, is
[`docs/isaac-runs-stage-2-contract.md`](isaac-runs-stage-2-contract.md).

## 2. The exact forward SQL

Two statements, separated by a line containing only `--;` (the runner splits on that
marker, never on `;`, so a semicolon in a comment or a string cannot split a statement).

```sql
CREATE TABLE IF NOT EXISTS isaac_run_projection (
    experiment_id          text        PRIMARY KEY
                           CONSTRAINT isaac_run_projection_experiment_fk
                           REFERENCES isaac_experiments (experiment_id),
    experiment_rev         bigint      NOT NULL
                           CONSTRAINT isaac_run_projection_rev_non_negative
                           CHECK (experiment_rev >= 0),
    experiment_generation  text        NOT NULL,
    run_count              bigint      NOT NULL
                           CONSTRAINT isaac_run_projection_count_non_negative
                           CHECK (run_count >= 0),
    projector              text        NOT NULL
                           CONSTRAINT isaac_run_projection_projector_known
                           CHECK (projector IN ('write-path', 'backfill')),
    projected_utc          timestamptz NOT NULL DEFAULT now()
)
--;
CREATE INDEX IF NOT EXISTS isaac_run_projection_projector_idx
    ON isaac_run_projection (projector, projected_utc)
```

The committed file carries **177 lines of comment above this** explaining every column and
constraint — measured, not estimated (`awk '/^CREATE TABLE/{print NR-1; exit}'`), and up from
~130 because the 2026-08-24 review struck two claims in place there. Read the file, not this
excerpt, before approving.

## 3. The foreign key refuses a parent delete — and that is a decision

No `ON DELETE` clause is written, so the action is the SQL default `NO ACTION`, which for
this non-deferrable constraint behaves as `RESTRICT`: **deleting an experiment that still
carries a projection claim is refused by the database.** Two independent reasons, the same
two `0002_runs` gives:

1. `ON DELETE CASCADE` turns one statement into an unbounded silent multi-row
   destruction. `DELETE FROM isaac_experiments` already passes the write policy.
2. It is the **reversible** choice. A future delete path can delete claims explicitly and
   then the experiment, with no schema change. Going the other way needs an `ALTER`, which
   the policy refuses.

**Disclosed as `0002` disclosed it:** `ON DELETE CASCADE` is *also unwritable* under the
current statement policy, which reads the `delete` after `on` as naming a table it does
not own. The design argument stands on its own; this note exists so a reader is not told a
constraint was a free choice when it was also forced.

## 4. What it deliberately does not do

- ~~**No read moves.** Exactly ONE statement in the application names this table
  (`experiment_repository.Q_UPSERT_RUN_PROJECTION`) and nothing reads it — pinned by
  `test_0005_is_written_by_the_write_path_and_read_by_nothing`, measured over the
  module-level constants rather than asserted.~~ **FALSE AT `37ff6e5b`, AND CORRECTED
  2026-09-17 IN THE SAME CHANGE THAT RECORDED THE OWNER APPROVAL. It is struck rather
  than rewritten because this is the document an operator reads before acting, and a
  reader who takes "nothing reads it" as current would mis-scope the blast radius of the
  table they are about to create.**

  Re-measured, not read — `grep -rn -a isaac_run_projection` over `apps/api/isaac_api/`
  and `scripts/`, then each hit classified by whether it is an SQL statement or a comment:
  **THREE statements name this table, and exactly ONE of them is a read.**

  | statement | site | kind |
  |---|---|---|
  | `Q_UPSERT_RUN_PROJECTION` | `experiment_repository.py:1143` | write — the write path's stamp |
  | `… FROM isaac_run_projection WHERE experiment_id = ANY(%s::text[])` | `experiment_repository.py:1210` | **read — the Stage-2b reader** |
  | `DELETE FROM isaac_run_projection WHERE experiment_id = %s` | `experiment_repository.py:1659` | delete, only with the experiment it describes |

  **The cited test no longer exists under that name**, and the codebase handled that
  honestly rather than silently: it is now
  `test_0005_is_written_by_the_write_path_and_read_by_ONE_reader`
  (`apps/api/tests/test_experiment_repository.py:2981`), whose docstring records that
  invariant 5 was *"DISCHARGED, NOT DELETED"* — the Stage-2a invariant's own second
  sentence said *"Turning a reader on is Stage 2b, is a separate reviewed slice"*, and
  that slice happened. `/api/health` says so on the wire
  (`run_projection.authoritative: true`). So the invariant was **superseded through the
  process it named**, not broken; it was only this packet that went stale.

  **WHAT THIS CHANGES FOR THE OPERATOR, AND WHAT IT DOES NOT.** It changes nothing about
  the migration bytes, which are unmoved and whose digests still match. It changes the
  consequence of applying it: the table is **read by this application**, so an
  **incomplete** table is not inert — it is a wrong answer to "how many runs does this
  experiment have". That is precisely why §8A's gate exists and why it is a gate rather
  than a postcheck, and it is why **§12A's sequence must not be reordered.**

- **The backfill still reads nothing.** This half of the old bullet **survives and is
  re-verified**: `scripts/db_backfill_runs.py` computes its report from the experiment
  documents and never reads the claim table (its own lines 102, 108, 189 say so). The
  Stage-2b completeness question is therefore answered by an SQL query an operator runs
  (§8A), not by a number the script prints.
- **No backfill runs.** `scripts/db_backfill_runs.py` exists, has **never been executed
  anywhere**, and is deliberately absent from the container image (the Dockerfile COPY
  allowlist ships one file out of `scripts/`; a test asserts this one is not it).
- **No `session_id` column, and none can ever be added.** `ALTER` is forbidden and
  `CREATE TABLE IF NOT EXISTS` is a silent no-op against an existing table, so a
  worked-example claim that ever reached this table would be permanently unidentifiable
  and permanently uncleanable. Tutorial isolation is inherited by construction: the stamp
  is written inside `persist`, after `refuse_if_not_persistable`.
- **No trigger.** `db_migrate.split_statements` refuses a dollar-quoted body, so a trigger
  is not expressible in a committed migration here. `run_count` is a writer-maintained
  projection and this packet says so rather than implying the database enforces it.

## 5. Prechecks — run these first, and read the output

```bash
# 1. Every earlier migration is applied. `0005` declares a foreign key into
#    `isaac_experiments`, which `0001` creates.
psql -Atc "select version from isaac_schema_migrations order by version"
#    EXPECT: 0001_experiments, 0002_runs, 0003_revisions, 0004_submissions
#
#    IF 0003 AND 0004 ARE ABSENT, STOP AND READ SECTION 6. They are owner-approved
#    and, as of this writing, NOT applied to the hosted database. Apply them from
#    their own packets with the bounded command
#    (`--apply --through 0004_submissions`), which is what stops a single
#    unbounded `--apply` landing all three at once.

# 2. The table does not already exist.
psql -Atc "select count(*) from information_schema.tables
           where table_schema='public' and table_name='isaac_run_projection'"
#    EXPECT: 0

# 3. The runner agrees, and applies nothing while saying so.
python scripts/db_migrate.py --plan
#    EXPECT (once 0003/0004 are applied): pending: 0005_run_projection
#    EXPECT (if they are not):            pending: 0003_revisions, 0004_submissions, 0005_run_projection
#
#    This is the SAME check as precheck 1, read from the runner instead of from the
#    table. Both are listed because they fail differently: precheck 1 catches a
#    bookkeeping row that exists without its table, and this catches a migration
#    file the runner cannot see.

# 4. Baseline counts, so the postchecks can be a comparison rather than an assertion.
psql -Atc "select count(*) from records"
psql -Atc "select count(*) from isaac_experiments"
psql -Atc "select count(*) from isaac_runs"

# 5. The engine build, recorded because the CI proof runs against postgres:18.
psql -Atc "select version()"
```

**Precheck 4 is not optional and its two `records`/`isaac_experiments` halves have been
skipped before.** `0002`'s operator report omitted exactly these, and the omission is
recorded in that packet as a gap. A count you did not take before cannot be compared
after.

## 6. The exact command — and it applies EVERY pending migration, not just this one

**READ THIS BEFORE RUNNING IT.** An **unbounded** `--apply` applies every pending migration in
lexical order. As of this writing `0003_revisions` and `0004_submissions` are owner-approved and
**not applied to the hosted database**, so against the real hosted database the unbounded command
would apply **three** migrations, two of which have their own packets and their own operator step.

~~`db_migrate` has `--plan` and `--apply` and **no `--only <version>`**.~~ **Corrected 2026-08-25:**
the runner takes **`--through VERSION`**, applying every pending migration up to and including that
version and nothing after it, and bounding `--plan` the same way. That is what makes sequence 1 below
reachable. It does not make this migration approved.

That is not a hidden hazard — precheck 1 is what catches it, and it is why the precheck comes
first. Two sequences were listed here; **the second is now marked NOT AUTHORIZED and the
correction is left visible, because it conflicted with the operator addendum in the operator's
own instruction.**

1. **Apply `0003` and `0004` first**, from their own packets, with the bounded command
   `python scripts/db_migrate.py --apply --through 0004_submissions`; confirm precheck 1 reads
   `0001, 0002, 0003, 0004`; then — **only if and when Krish has approved this migration** — run the
   command below and expect exactly `applied: 0005_run_projection`. **This is the only shape that is
   authorized.** ~~"and it is currently unreachable with the shipped runner, because `--apply` has no
   per-version option and would take `0005` along with `0003`/`0004`"~~ — **corrected 2026-08-25: it
   is now reachable.** `--through` bounds a run to a named version, which is resolution 3 of the
   three named in [`docs/dean-operator-addendum-2026-08-25.md`](dean-operator-addendum-2026-08-25.md)
   §0; that section now records the conflict as **resolved** rather than **BLOCKED**. **The tooling
   was the blocker, not the approval** — this migration is still unapproved, and reachability is not
   permission.
2. ~~**Apply all three together, deliberately**, having read all three packets, and expect
   `applied: 0003_revisions, 0004_submissions, 0005_run_projection`. Report the postchecks for
   all three.~~ **NOT AUTHORIZED, struck 2026-08-25.** It presupposes an owner approval of `0005`
   that **does not exist** — this packet's own STATUS block says so — and an operator cannot
   supply one. Offering it as *"acceptable"* directly contradicted the addendum's **DO NOT apply
   `0005_run_projection`** row. If Krish reviews and approves `0005`, this becomes the clean
   resolution; until then it is not a choice on the table.

What is NOT acceptable is running the command because this packet said to and discovering
afterwards that three migrations landed.

**THE CODE BLOCK BELOW SHOWED THE UNBOUNDED COMMAND UNTIL 2026-09-17, WHILE THE PROSE ABOVE IT
AUTHORIZED ONLY THE BOUNDED ONE. Corrected in the same change that recorded the owner approval.**
The old block is kept struck, because an operator who has read this packet before may remember the
command rather than the caveat — and the caveat was the whole content:

~~`python scripts/db_migrate.py --apply`~~ — **NOT the command to run.** It applies every pending
migration in lexical order. Now that `0005` is owner-approved, the failure mode it invites has
*changed shape rather than gone away*: an unbounded run against a hosted database still pending
`0003` and `0004` would land **three** owner-approved migrations in one step, collapsing three
operator acts — each with its own packet, its own prechecks and its own postchecks — into one
unverifiable event.

**THE AUTHORIZED COMMAND IS BOUNDED, ALWAYS, AND IT IS BOUNDED TWICE:**

```bash
# Step 1 — 0003 and 0004, from THEIR packets, bounded to 0004.
python scripts/db_migrate.py --apply --through 0004_submissions
#    EXPECT: applied: 0003_revisions, 0004_submissions
#    Then run 0003's and 0004's OWN postchecks before going further.

# Step 2 — this migration, bounded to itself.
python scripts/db_migrate.py --apply --through 0005_run_projection
#    EXPECT: applied: 0005_run_projection
#    If it reports anything else, STOP: the state is not what this packet describes.
```

`--through` applies every pending migration up to and including the named version and nothing after
it, and bounds `--plan` the same way. Use `--plan --through <version>` first, every time, and read
the output before the `--apply`.

**Do not use raw `psql` as a migration substitute.** The runner records the version in
`isaac_schema_migrations` inside the same transaction as the DDL; a hand-run `CREATE TABLE` produces
the table **without** its bookkeeping row, which is precisely the "a table that exists without its
ledger entry" state precheck 1 exists to catch, and which makes every later `--plan` wrong.

One transaction. The runner issues `CREATE TABLE IF NOT EXISTS isaac_schema_migrations`
once per transaction (which is what makes losing the bookkeeping table survivable), then
the two statements above, then records the version.

## 7. Postchecks — what would prove it worked

```bash
# The table, its constraints, and NO `ON DELETE`.
psql -c "\d+ isaac_run_projection"
psql -Atc "select conname, pg_get_constraintdef(oid) from pg_constraint
           where conrelid = 'isaac_run_projection'::regclass order by conname"
#    EXPECT the four NAMED constraints and the primary key to be PRESENT, and NO
#    occurrence of 'ON DELETE' or 'CASCADE' anywhere in the output.
#
#    DO NOT CHECK THE ROW COUNT. Some engines catalogue NOT NULL as pg_constraint
#    rows and some do not, so the total is engine-dependent and a count would fail
#    for a reason that has nothing to do with this migration. Check for each name:
#    isaac_run_projection_experiment_fk, _rev_non_negative, _count_non_negative,
#    _projector_known.

# Empty. This migration moves no data.
psql -Atc "select count(*) from isaac_run_projection"     # EXPECT: 0

# Idempotent.
python scripts/db_migrate.py --apply
#    EXPECT: nothing to apply (every migration is already recorded)

# Precheck 4's counts, unchanged.
psql -Atc "select count(*) from records"
psql -Atc "select count(*) from isaac_experiments"
psql -Atc "select count(*) from isaac_runs"

# The application is healthy and still durable.
curl -s <base>/api/health | jq '{mode, database}'
```

## 8. Rollback

`apps/api/isaac_api/migrations/0005_run_projection.rollback.sql`, run with
`psql -v ON_ERROR_STOP=1 -f`. Both statements in one transaction, so "the table is gone"
and "the version is no longer recorded" cannot disagree.

**The dependency is NOT the one the numbering suggests.** `isaac_run_projection`
references `isaac_experiments`, **not** `isaac_runs`. So:

- it must be rolled back before `0001`;
- it is **independent of `0002`** — rolling `0002` back while this table stands is legal,
  and leaves every claim in it describing rows that no longer exist. The four-state read
  model handles that as fallback, which is why the rollback file documents it rather than
  forbidding it.

**What rolling back costs:** every completeness claim is deleted, so every experiment
becomes NEVER PROJECTED again. The run rows are untouched, so **nothing scientific is
lost**. In the build that ships this migration the cost is **zero**, because no read
consults the table. **Dump first anyway** if a later build has a reader:

```bash
psql -c "\copy (SELECT * FROM isaac_run_projection) TO 'run-projection.csv' CSV HEADER"
```

## 8A. The Stage-2b completeness gate — a query YOU run, not a number a script prints

**FIVE committed artifacts once described this gate as "the backfill reported
`never_projected: 0`". No script prints that, and none can:** the backfill deliberately
never reads `isaac_run_projection`, because a read would make it the table's first reader
and that is the Stage-2b decision the gate exists to *precede*. An independent review
measured the gap. The gate is these two queries.

~~"Four committed documents"~~ — **RECOUNTED 2026-08-24, and the miscount is the point.**
The first sweep fixed `CLAUDE.md`, the Stage-2 contract, `scripts/db_backfill_runs.py` and
this section — and missed **`0005_run_projection.sql` itself**, where the same claim sat in
the header comment of the artifact the owner approves BYTE FOR BYTE, and **§11 of this very
document**. Both are corrected now. An enumeration written while correcting an enumeration
error was itself short, which is exactly the failure §10 records in the other direction.

**Run them AFTER `python scripts/db_backfill_runs.py --apply` has reported
`experiments UNREADABLE: 0`, `refused: 0` and `failed: 0`.** Any non-zero there means some
experiment was not projected, and the queries below would then be describing an incomplete
pass rather than a complete one.

```sql
-- 1. NEVER PROJECTED. Must be 0.
SELECT count(*) FROM isaac_experiments e
 WHERE NOT EXISTS (SELECT 1 FROM isaac_run_projection p
                    WHERE p.experiment_id = e.experiment_id);

-- 2. STALE — a claim exists but names a different document version. Must be 0.
SELECT count(*) FROM isaac_experiments e
  JOIN isaac_run_projection p ON p.experiment_id = e.experiment_id
 WHERE p.experiment_rev        <> COALESCE((e.state ->> 'rev')::bigint, 0)
    OR p.experiment_generation <> COALESCE(e.state ->> 'generation', '');
```

**Both must be 0, and 0 for query 1 is the answer that could not be given before this
migration existed** — an experiment with genuinely no runs and an experiment never
projected both looked like zero rows in `isaac_runs`.

**A third query is worth running and is NOT a gate**, because it can be legitimately
non-zero on a live deployment: it reports claims made by the write path versus the
backfill. If every row says `backfill`, no scientist has saved anything since the backfill
ran, which is information rather than a fault.

```sql
SELECT projector, count(*) FROM isaac_run_projection GROUP BY projector;
```

**What zero on both does NOT establish:** that the ROWS are right. It establishes that a
claim exists for every experiment and that each claim names the current document. The rows
are what the claim is about, and the claim is written in the same transaction as the rows
— which is the invariant, not a measurement. A reader built on this should still fall back
to the document on any mismatch; the contract's §2.1 four-state table is what it must
implement.

~~**A CI step that runs both of these against a real `postgres:18` was added on 2026-08-24
and HAS NOT YET RUN.** Until it does, nothing in this packet claims either query has ever
executed anywhere.~~ **SUPERSEDED 2026-08-25 — IT HAS RUN.** Struck rather than deleted because
the sentence was the honest state for one day and a reader should see that it expired rather than
that it never existed. Both queries executed **verbatim** against PostgreSQL 18.6 in run
[`32800763199`](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/32800763199),
job `97660962127`, step *"Prove the Stage-2b gate queries detect what the packet says they
detect"*, conclusion `success`, on `main` at `c153ec9`. Job output, quoted:

```
baseline: never_projected=0 stale=1
accepted and committed as designed: projector = backfill
after: never_projected=1 stale=3
backfill|3
0005 §8A: both gate queries executed against a real engine and named the right rows
```

The counts are asserted as **deltas** against a baseline taken immediately before, because the
queries are unscoped by design and the step must not rewrite the query you would actually run;
the step also asserts **by id** which experiments each query names, with the current claim in
neither result set, so neither can pass by being vacuously empty. Source: the job log, fetched
read-only with `gh api repos/ISAAC-DOE/isaac-metadata-assistant/actions/jobs/97660962127/logs`.
**This says nothing about the hosted database** — the gate is still a query an operator runs
there. See §9A, which records how these came to have no engine evidence at all.

## 9. Evidence, and what remains unproven — read this before approving

**Proven, against a real `postgres:18` service container in CI**
(`.github/workflows/ci.yml` → `postgres-migration`):

- forward application, in order, with `0005` last;
- the plan output naming it, and `--plan` creating no table;
- idempotence, including with the bookkeeping row deleted;
- the table set gaining **exactly nine** application-owned tables and `records` being
  byte-identical (an md5 over every row, before and after);
- **every one of the five constraints refusing what it claims to refuse**, each case
  naming the object PostgreSQL must blame — the foreign key, both non-negative CHECKs,
  the closed `projector` value set, `experiment_generation`'s NOT NULL, the primary key,
  and the parent-delete refusal;
- the rollback, in the documented order, restoring the pre-migration table set;
- the wrong-order rollback failing safely and dropping nothing.

**ONE ITEM WAS LISTED HERE AS PROVEN AND HAD NEVER EXECUTED. Recorded rather than quietly
re-listed once it did.** This section claimed *"the claim the application's own save writes,
read back from the server"* was proven in CI. It was not: the step that does it called
`exp.save_versioned(None)`, and that method takes no argument, so the job died on a
`TypeError` before the read-back, the projector assertion, the `run_count`-versus-`count(*)`
comparison and the supersede-in-place check ever ran. An independent review found the packet
asserting proof for a step that had never executed — which is the failure mode a packet
exists to prevent, appearing in the packet itself.

The signature is fixed, and a local test now makes the same API calls without Postgres so a
third signature mistake cannot reach CI.

**AND IT HAS NOW EXECUTED — job `96347581006`, on `a350af6`.** The row below is therefore
promoted from "pending" to proven, and the paragraph above is kept because a claim that was
once asserted without evidence should not be able to quietly become a claim that always had
it. The output, quoted rather than summarised:

```
experiment 01M0F0SBM5SY12W8Y6A0FHYVNW rev 1 runs 2
expected: 01M0F0SBM5SY12W8Y6A0FHYVNW|1|757a8e31c4e1ce17|2
actual:   01M0F0SBM5SY12W8Y6A0FHYVNW|1|757a8e31c4e1ce17|2
second save: rev 2 runs 3
0005: the application's own claim matches the document AND the rows
```

- **PROVEN:** the claim the application's own save writes, read back from the server and
  compared against the document it was projected from — the version pair (`rev` and
  `generation`), the projector, and `run_count` against an actual `count(*)` of `isaac_runs`.
  Plus a second save superseding in place rather than appending: one row, `run_count` 3.

**A separate consequence of `0005` also surfaced in CI and is worth an operator knowing**, because
it is the foreign key doing exactly what §3 says it does. A cleanup step that deleted an
experiment failed with `violates foreign key constraint "isaac_run_projection_experiment_fk"`
— once this migration is applied, **an experiment carrying a projection claim cannot be
deleted until the claim is deleted first.** That is the design (the alternative,
`ON DELETE CASCADE`, is declined in §3), and it means any operational script that removes
experiments needs one more statement.

### 9A. DECLARED IN THE WORKFLOW AND NOT YET RUN — added 2026-08-24; **RUN 2026-08-25, see §8A**

**Read this section as "written and reviewed", not as "observed".** The repository has
already had one packet assert proof for a step that had never executed (the paragraph
above), so new coverage is listed here in a section of its own until a real run exists,
and is promoted into §9 only by quoting the job.

An independent review measured that **the Stage-2b gate of §8A had no engine evidence at
all**: no CI step and no test ever constructed a projection row whose
`(experiment_rev, experiment_generation)` disagrees with the document, so **neither §8A query
had ever executed anywhere**; and **no row with `projector = 'backfill'` had ever been
committed to any engine** — the CHECK's *acceptance* of that value was inferred from reading
the CHECK, while every case that had run tested its *refusals*.

One new step and three cases added to an existing one now cover it. ~~**Neither has run**~~ —
**BOTH HAVE RUN, 2026-08-25**, in run `32800763199`, job `97660962127`, on `main` at `c153ec9`,
every step `success`. The heading of this section is kept, and this claim struck rather than
deleted, because the section exists to record the interval in which coverage was written but
unobserved — deleting the interval would make the two indistinguishable. The quoted job output is
in §8A above:

- *"Prove the Stage-2b gate queries detect what the packet says they detect"* — commits a
  `projector = 'backfill'` claim and reads it back; builds one experiment stale **by rev**,
  one stale **by generation at the same rev** (the delete-and-recreate case `generation`
  exists for), and one **never projected**; runs both §8A queries **verbatim**, asserts the
  deltas, and asserts by id **which** experiments each names — with the current claim in
  neither set, so neither query can pass by being vacuously empty. Counts are read as
  deltas against a baseline taken immediately before, because the §8A queries are unscoped
  by design and the step must not rewrite the query the operator will actually run.
- Three cases added to the existing constraint step for the NOT NULLs on
  **`experiment_rev`**, **`run_count`** and **`projector`**, which were declared and blamed
  by nothing. They blame `column "<name>"` rather than the bare name, because bare
  `projector` also occurs inside `isaac_run_projection_projector_known` and a CHECK failure
  would otherwise satisfy the grep.

**These do not move the "41 of 46 declared / 27 executed on `main`" figures** quoted in
`CLAUDE.md` and the `0003`/`0004` packets. That counter is derived only from constraint
names declared by `0003_revisions` and `0004_submissions`; `0005`'s constraints have never
been inside it. Re-derived, not assumed:
`test_submission_store.py::test_the_two_constraint_numbers_are_each_still_the_measured_ones`
passes unchanged.

**NOT proven, and this is the whole reason the operator's step is separate:** the CI
container is **empty**, with a two-row synthetic stand-in for `records`. So *"behaves
against the real data, the real roles and the real grants"* is unproven, exactly as it was
for `0001` through `0004`.

**Also not proven:** no agent has connected to the hosted database, and none may. Every
hosted figure in this packet will be **operator testimony**, not a captured artifact —
the same standing caveat `0002`'s report carries.

## 10. Authorization basis

`CLAUDE.md` §15's 2026-08-07 write lift covers Create Experiment persistence *"plus the
minimum supporting persistence architecture that feature requires"*, and its enumerated
table list **now names `isaac_run_projection`** (§15, "added 2026-08-19") — **ONE COMMIT
AFTER the table shipped**, not in the same change.

**Measured, and re-measurable:**

```bash
git log --diff-filter=A -- apps/api/isaac_api/migrations/0005_run_projection.sql
#   -> 6dce6fd   (its diffstat touches six files; CLAUDE.md is not one of them)
git log -S"isaac_run_projection" -- CLAUDE.md
#   -> 8f7c650 is the first, and 6dce6fd is an ancestor of it
```

~~"added in the same change that creates the table … **This is the first time the sentence
exists before the table is written**, and it is stated here so a future reader can see it
was not a permission written down late."~~ — **FALSE BY ONE COMMIT, struck 2026-08-24.**
An independent review measured it against git (the two commands above), and
`db_write.py`, the Stage-2 contract and `test_experiment_repository.py` each recorded the
correction at the time —
**this packet did not**, so for one commit `CLAUDE.md` asserted that "all four artifacts
now carry the correction in place" while the fourth still carried the original claim. That
second review is what caught it, and it is the durable part of this section.

**What is true, stated without the flourish:** the list has now been corrected three times
— `isaac_runs`, found and reported by the implementing slice; the five submission-lifecycle
tables, found only by an independent review; and this table, one commit late. Each time the
enumeration followed the write rather than preceding it. **This slice's authorization basis
is §15's "minimum supporting persistence architecture" clause PLUS the enumeration, and the
enumeration was committed after the table**, which is a smaller gap than the two before it
and is still not the thing that was claimed.

## 12. The six approval checks, and what each one actually verified

Recorded here because the STATUS block's approval is **conditional** on them, and a condition nobody
can audit is not a condition. Performed **2026-09-17** on `main` at **`37ff6e5b`**, before the STATUS
block was written. This follows `0003`'s §12D convention deliberately — **and diverges from it in two
places: check 3, where copying `0003`'s wording would have produced a false claim, and check 6, which
`0003` has no equivalent of because `0003` has no operator gate built on its own SQL.**

| # | Condition | Command / method | Result |
|---|---|---|---|
| 1 | Forward SHA-256 matches this packet's table | `shasum -a 256` on the working-tree file **and** `git show origin/main:… \| shasum -a 256` | **match, in both** — `86bf111cf030c15c…2da98304` |
| 2 | Rollback SHA-256 matches | same, both vantage points | **match, in both** — `54a17432150525f7…bda90e735` |
| 3 | No material SQL change since technical review | `git log --oneline --` on both files, then a diff of the **comment-stripped** forward file across the second commit | **TWO commits, not one** — see the divergence note below. **The executable statements have had exactly ONE version, ever;** the second commit changed comments only, measured, not taken on trust |
| 4 | Prior review findings remain resolved, and the constraints this packet names are in the committed text | read the forward SQL end to end; then grep every constraint name §7 tells the operator to look for | **resolved — but the pinning was MISSING and was added in this change.** See below |
| 5 | No new material safety defect | comment-stripped statement inventory of both files; token scan for `ALTER`/`DROP`/`TRUNCATE`/`GRANT`/`REVOKE`/DML/`ON DELETE`/`CASCADE`/dollar-quoting; search for any identifier naming `records` | **none found** |
| 6 | §8A's own gate queries are well-formed against the schema this migration declares | parsed the `CREATE TABLE` for declared columns and the §8A block for every `p.<column>` it references, then intersected | **every referenced column exists; none absent. And `run_count` is correctly NOT referenced** — contract §7.4 forbids it as a mismatch detector |

**CHECK 6 — THE GATE'S OWN QUERIES WERE RUN AGAINST THE SCHEMA THIS MIGRATION CREATES, NOT JUST
READ.** Added because §8A is the **gate** for a decision this migration enables, and a gate whose
SQL names a column that does not exist would fail at the worst possible moment: mid-window, after
the migration is applied, with the operator holding an error instead of a verdict. Checked by
parsing the `CREATE TABLE` for its declared columns and the §8A block for every `p.<column>` it
references:

| | |
|---|---|
| columns the migration creates | `experiment_id`, `experiment_rev`, `experiment_generation`, `run_count`, `projector`, `projected_utc` |
| columns §8A's two queries reference on this table | `experiment_id`, `experiment_rev`, `experiment_generation` |
| referenced-but-absent | **none** |

**And §8A correctly does NOT reference `run_count`** — verified mechanically, not assumed. That is
not an omission: `docs/isaac-runs-stage-2-contract.md` §7.4 **forbids** using it to detect a
mismatch, because §2.2 invariant 4 records that it is `len(desired_ids)` — an *intention*, not an
*observation*. A completeness gate built on it would compare the writer's belief against itself.

**What this check does NOT establish:** that either query *executes* against the hosted database, or
that either returns 0 there. It establishes that they are well-formed against the table as declared.
The execution is the operator's, at step 9 of §12A.

**CHECK 3 — THE DIVERGENCE FROM `0003`, STATED BECAUSE THE OBVIOUS WORDING WOULD HAVE BEEN WRONG.**
`0003`'s §12D says its bytes *"have had exactly one version, ever"*. **That is not true of `0005`**,
and an approval that copied the sentence would have asserted something checkably false. `git log`
gives two commits touching the forward file:

- `6dce6fd9` — *"feat(db): isaac_runs Stage 2a — the completeness claim, and NOT a read cutover"* (created it)
- `9b35c204` — *"docs(0005): four corrections an independent review required before approval"*

`9b35c204` is a **46-insertion, 7-deletion** change to the forward `.sql`, which is why it moved the
forward digest and is exactly the sort of thing an approval must not wave past. **Measured rather
than inferred from the commit message:** stripping every line whose first non-space characters are
`--` and diffing across that commit yields **an empty diff of executable lines.** The change was
comments — including the withdrawal of a `never_projected: 0` claim that this repository had already
recorded as impossible, sitting inside the artifact the owner approves byte-for-byte. Left alone,
approval would have frozen it there permanently, since `ALTER` is a forbidden verb and a comment in
an applied migration cannot be edited without a fresh packet. **The rollback file was never touched**,
which is why its digest is unchanged across both commits.

**CHECK 4 — THE PACKET TOLD THE OPERATOR TO VERIFY FOUR CONSTRAINT NAMES THAT NO TEST PINNED.**
§7's postcheck says, in capitals, to check for `isaac_run_projection_experiment_fk`,
`_rev_non_negative`, `_count_non_negative` and `_projector_known`. Measured at `37ff6e5b`:

```
grep -rl -a <each name> apps/api/tests/   ->   0 files, for all four
```

`0003` and `0004` have exactly this guard — `test_the_approval_packets_named_constraints_are_in_the_committed_text`
in `apps/api/tests/test_submission_store.py`, sixteen parametrized rows — and **`0005` was absent from
it.** So nothing in the repository guaranteed that the names this packet instructs an operator to look
for are the names the committed SQL actually declares; a rename, or a packet typo, would have sent the
operator hunting for a constraint that never existed and there would have been no failing test. The
four rows are added in this change. Its `_statements()` helper reads
`db_migrate.load_migrations()` generically, so it resolved `0005` without modification — the gap was
the parameter list, not the mechanism.

**WHAT CHECK 5 ACTUALLY LOOKED AT, so it is not read as broader than it was.** With comments stripped,
the forward file is **exactly two statements** and nothing else:

```sql
CREATE TABLE IF NOT EXISTS isaac_run_projection ( … )
CREATE INDEX IF NOT EXISTS isaac_run_projection_projector_idx ON isaac_run_projection (projector, projected_utc)
```

No `ALTER`, no `DROP`, no `TRUNCATE`, no `GRANT`/`REVOKE`, no DML, no dollar-quoted body, and **no
`ON DELETE` clause in any statement** — the phrase occurs only in comments, so the foreign key takes
the SQL default `NO ACTION` and no cascade exists. The identifier `records` appears in **no statement
in either file**. The rollback is three statements in one transaction: it drops only the table this
migration creates and deletes only its own bookkeeping row.

**This check was a READ of the committed text plus a structural scan — not a runtime observation, and
not a substitute for the independent technical review that produced this packet.** The behavioural
evidence is §9's, and §9's own *"DECLARED IN THE WORKFLOW AND NOT YET RUN"* framing is unchanged by
this approval. The residual risk is the one §9 names and **only the operator can retire it**: CI
proves this migration against an empty `postgres:18` container with a synthetic stand-in for
`records`, which is not the same as proving it against the hosted database with its real data, roles
and grants.

---

## 12A. The bounded operator sequence — ordered, and the order is the safety property

**This is the whole sequence, and no step may be skipped, reordered, or run in parallel with
another.** It is restated here as one block because three of its steps live in three different
packets, and the failure this ordering prevents is not a bad statement — it is a **correct statement
run at the wrong time**.

```text
 1.  verify backup / restore
 2.  verify the migration ledger          (this packet's §5 prechecks 1-5)
 3.  apply approved 0003 + 0004 TOGETHER  python scripts/db_migrate.py --apply --through 0004_submissions
 4.  verify                               0003's and 0004's OWN postchecks
 5.  apply approved 0005                  python scripts/db_migrate.py --apply --through 0005_run_projection
 6.  verify                               this packet's §7 postchecks
 7.  run the isaac_runs backfill          python scripts/db_backfill_runs.py --apply
 8.  REQUIRE every failed / refused / UNREADABLE count = 0
 9.  run BOTH §8A completeness queries
10.  REQUIRE both = 0
11.  only then may the Stage-2b read cutover be permitted
```

Five things about that sequence that are decisions rather than formalities:

- **Step 3 applies two migrations deliberately, and that is not a violation of the bounded rule.**
  `0003` and `0004` are ONE decision — `0004` declares a foreign key into a table `0003` creates —
  and they must be applied together or not at all. `--through 0004_submissions` is what makes
  "together" mean "and not `0005` as well".
- **Steps 4 and 6 are separate verifications and must not be merged.** Running 3 and 5 back to back
  and verifying once at the end produces a state where a failure cannot be attributed.
- **Step 8 is a REQUIREMENT, not a report.** A non-zero `UNREADABLE`, `refused` or `failed` means
  some experiment was not projected, and steps 9-10 would then be describing an incomplete pass
  **while returning 0** — the gate would pass for the wrong reason. This is the one place in the
  sequence where a green reading is actively misleading if step 8 was not checked first.
- **Step 11 is a DECISION, not a continuation.** Nothing in steps 1-10 authorizes it. §8A's queries
  returning 0 makes the cutover *safe to consider*; whether to make `isaac_runs` a read source is a
  separate reviewed slice, and removing `runs` from the experiment document is a **third** decision
  justified by no measurement in this repository.
- **Do not use raw `psql` as a migration substitute at any step**, and never issue an unbounded
  `--apply`. See §6.

**None of these eleven steps may be performed by an agent.** `CLAUDE.md` §15's hard stop is
unchanged and is not softened by the owner approval recorded above: no agent may apply a migration,
open a connection to the SLAC PostgreSQL, request a kubeconfig, a port-forward or a Secret, run the
backfill, or change Kubernetes.

---

## 11. What this packet does not cover

- **Stage 2b — moving a reader onto `isaac_runs`.** A separate reviewed slice, gated on
  **§8A** of this packet: the backfill having RUN in the target environment with
  `experiments UNREADABLE: 0`, `refused: 0` and `failed: 0`, **and** the operator's two
  completeness queries there both returning 0. That is a measurement, not a belief — but
  it is a measurement **you** take, not one a script hands you.

  ~~"gated on the backfill having RUN in the target environment and reported
  `never_projected: 0`."~~ — **STRUCK 2026-08-24: this document was arguing both sides of
  its own gate.** §8A above already records that the gate was once described that way and
  that **no script prints it and none can**, because the backfill deliberately never reads
  `isaac_run_projection`. `CLAUDE.md`, the Stage-2 contract and
  `scripts/db_backfill_runs.py` all carried the correction; **this packet — the one
  document an operator actually reads before acting — still contradicted itself twelve
  sections later**, and an independent review measured it. Kept struck rather than deleted
  so the contradiction reads as corrected rather than as never having existed.
- **Removing `runs` from the experiment document.** A third decision, justified by no
  measurement in this repository. The brief that motivates it ("contract §8 D7") is cited
  by several files here and committed to none of them.
- **Running the backfill.** An operator action, against an environment an agent may not
  connect to.
- **Any change to `records`, the verification truth plane, the official validator, export
  behaviour, or Dean-owned infrastructure.**
