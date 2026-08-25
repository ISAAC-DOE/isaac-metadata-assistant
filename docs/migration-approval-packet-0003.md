# Migration approval packet — `0003_revisions`

> ## STATUS: **APPROVED BY THE PROJECT OWNER 2026-08-17. NOT APPLIED TO THE HOSTED DATABASE, ANYWHERE.**
>
> **Read both halves. They are different acts by different people, and collapsing them is the one
> misreading this block exists to prevent.**
>
> **The approval (Krish, project owner, 2026-08-17).** Krish approves the **exact bytes** recorded in
> the digest table below, conditional on five mechanical checks which were performed before this line
> was written and are recorded in §12D:
>
> 1. the forward file's SHA-256 still matches this packet's table — **verified, matches**;
> 2. the rollback file's SHA-256 still matches — **verified, matches**;
> 3. no material SQL change since technical review — **verified, and stronger than asked**: both SQL
>    files and both packets were introduced in ONE commit, `0896b07`, and `git log` shows no commit
>    has touched either `.sql` file since, so these bytes have had exactly one version, ever;
> 4. the prior review findings remain resolved — **verified**, see §12D;
> 5. no new material safety defect — **none found**, see §12D for what was actually checked.
>
> The approval is of these bytes and of nothing else. Editing either `.sql` file voids it: the digest
> would move, `test_the_approval_packet_digests_match_the_committed_files` would go red, and the
> correspondence between "the bytes approved" and "the bytes applied" — the only thing that makes an
> approval mean anything — would be gone. Re-issue the packet instead.
>
> **The application (Dean / the infrastructure operator) — STILL NOT DONE, AND STILL NOT THE AGENT'S
> TO DO.** Nothing in this packet has been run against the hosted database, and no agent may run it.
> `CLAUDE.md` §15's hard stop is unchanged by the fact that `0001` and `0002` have both been applied by
> Dean, and it is unchanged by this approval: owner approval is a **precondition** for the operator's
> act, not a substitute for it — as `CLAUDE.md` §15 puts it: *"two migrations having been applied by
> the infrastructure owner is not a precedent, a delegation, or a standing permission; `0003` and later
> each need their own packet, their own owner approval, and their own operator action."* This packet now
> has the first two. **The third is outstanding.**
>
> **Local and CI testing is authorized. Applying it to the hosted environment is the owner's act.**
> Do not request a kubeconfig, a port-forward, or a Secret, and do not connect to the SLAC database
> (`docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52`).
>
> **`0003_revisions` and `0004_submissions` are ONE decision, and must be applied together or not at all.**
> `0004_submissions` declares a foreign key into a table `0003_revisions` creates, so 0003 without
> 0004 leaves the application unable to record a submission, and 0004 without 0003 cannot be applied
> at all. `db_migrate` orders them lexicographically, so the single bounded command in §9
> (`--apply --through 0004_submissions`) does both in the right order and stops there. Read both
> packets before approving either.

## Authorization basis

**What authorizes this work, cited rather than assumed.** Two things, and neither is an inference
from the fact that `0001` and `0002` exist:

1. **The project owner's instruction in the run that produced this slice** — build durable,
   attributable submission recording over the experiments this application creates.
2. **`CLAUDE.md` §15's 2026-08-07 narrow lift** of the blanket "no database write" prohibition, which
   covers *"durable Create Experiment persistence in the existing app-owned PostgreSQL database, plus
   **the minimum supporting persistence architecture that feature requires**"*, and which enumerates
   *"forward-only, idempotent migrations (`apps/api/isaac_api/migrations/`, runner `db_migrate.py`,
   operator CLI `scripts/db_migrate.py`)"* among the things it covers.

**AND HERE IS THE GAP, STATED THE WAY THE `isaac_runs` SLICE STATED ITS OWN.** At the time this
migration was written, `CLAUDE.md` §15's enumerated list of app-owned tables named exactly three —
`isaac_experiments`, `isaac_schema_migrations`, and (added 2026-08-12) `isaac_runs`. **It did not
name any of the five tables `0003` and `0004` create**, and `db_write.OWNED_TABLES` adds all five —
which the slice had to do, because the statement policy refuses a `CREATE TABLE` naming an unlisted
table, so the migration could not run at all otherwise. So **no committed sentence named these five**,
and the authorization basis was item 1 plus the "minimum supporting persistence architecture" clause
in item 2 — not that list.

That is exactly the rule `CLAUDE.md` §15 added *because of* the `isaac_runs` incident: *"a slice that
cannot cite a committed sentence permitting what it does has not established its authorization basis,
and saying so is part of the slice."* Unlike the `isaac_runs` slice, this one did **not** find and
report the gap; an independent review did, and this section is the correction. The §15 list has been
amended in the same change, in the same style as the `isaac_runs` correction — the change recorded
rather than silently applied. **Read it as a recorded scope extension, not as a pre-existing
permission that was merely written down late.**

**What none of this authorizes, and none of it has changed:** applying this migration to the hosted
database (the owner's act — see the STATUS block above); any statement naming the production-derived
`records` table; any read surface over this history; and any identity or role enforcement.

## The bytes being approved

| File | SHA-256 |
|---|---|
| `apps/api/isaac_api/migrations/0003_revisions.sql` | `f17db0b90d8696c7eac430e247c9b81d01439093663a755a4172487d54d3d46f` |
| `apps/api/isaac_api/migrations/0003_revisions.rollback.sql` | `4af243393ededbaf7ceb6c32b3d97f75bb31ee8c6884d19bc8fd0b222e203645` |

Recompute before applying, and refuse if either differs:

```bash
shasum -a 256 apps/api/isaac_api/migrations/0003_revisions.sql \
              apps/api/isaac_api/migrations/0003_revisions.rollback.sql
```

That check is why this table exists. It is the only evidence that the bytes applied to the hosted
database are the bytes approved here, and `0002`'s packet records a period in which its own forward
digest had gone stale and nothing noticed.

---

## 1. Why this migration exists

A scientist finishing an experiment performs an act the application currently cannot record: a
**submission** — *"this is finished, and I am the one saying so."* Recording it needs an immutable
snapshot of exactly what was finished, and this migration creates the tables that hold one.

### Why it cannot live in the experiment document, mechanically

The cheaper design — "add a `revisions` array to `Experiment.to_state()`" — does not work, and the
reasons are mechanical rather than aesthetic. Both were measured against the code, not assumed:

1. **The durable compare-and-swap refuses it.** `experiment_repository.Q_UPSERT_EXPERIMENT` accepts
   a write only when the generation differs, **or** the offered `rev` is strictly ahead, **or** the
   document is byte-identical. A *changed* document at the *same* rev is refused by the database.
   Recording history is not a scientific mutation and must not bump the record's `rev`, so a history
   entry written into the document would be refused.
2. **The write would never be issued at all.** `workspace.Experiment.save_versioned` does not attempt
   a write unless `_authoritative_signature` moved, and that signature covers only
   `{title, source, draft, record_id, runs}`. A new document key is invisible to it.

There is therefore no "shadow it in the document first, promote it later" path available — the option
that `0002_runs` had. History needs its own tables from the first line of code.

## 2. The exact forward SQL

Commentary stripped (the runner drops `--` lines; psql treats them as comments, so the effective SQL
is identical either way). Six statements, separated by lines containing only `--;`:

```sql
CREATE TABLE IF NOT EXISTS isaac_experiment_revisions (
    revision_id        text        PRIMARY KEY
                       CONSTRAINT isaac_experiment_revisions_id_shape
                       CHECK (revision_id ~ '^[0-9A-Z]{26}$'),
    experiment_id      text        NOT NULL
                       CONSTRAINT isaac_experiment_revisions_experiment_fk
                       REFERENCES isaac_experiments (experiment_id),
    revision_no        bigint      NOT NULL
                       CONSTRAINT isaac_experiment_revisions_no_positive
                       CHECK (revision_no >= 1),
    experiment_rev     bigint      NOT NULL
                       CONSTRAINT isaac_experiment_revisions_rev_non_negative
                       CHECK (experiment_rev >= 0),
    generation         text        NOT NULL,
    state              jsonb       NOT NULL
                       CONSTRAINT isaac_experiment_revisions_state_is_object
                       CHECK (jsonb_typeof(state) = 'object'),
    content_signature  text        NOT NULL
                       CONSTRAINT isaac_experiment_revisions_signature_shape
                       CHECK (content_signature ~ '^[0-9a-f]{64}$'),
    reason             text        NOT NULL
                       CONSTRAINT isaac_experiment_revisions_reason_known
                       CHECK (reason IN ('submission')),
    subject            text
                       CONSTRAINT isaac_experiment_revisions_subject_non_empty
                       CHECK (subject IS NULL OR length(subject) > 0),
    trust_basis        text        NOT NULL
                       CONSTRAINT isaac_experiment_revisions_trust_basis_known
                       CHECK (trust_basis IN ('unattributed', 'test_fixture',
                                              'verified_edge_assertion')),
    created_utc        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_experiment_revisions_no_unique
    UNIQUE (experiment_id, revision_no),
    CONSTRAINT isaac_experiment_revisions_attribution
    CHECK ((trust_basis = 'unattributed') = (subject IS NULL))
);

CREATE INDEX IF NOT EXISTS isaac_experiment_revisions_experiment_time_idx
    ON isaac_experiment_revisions (experiment_id, created_utc, revision_id);

CREATE TABLE IF NOT EXISTS isaac_run_revisions (
    run_revision_id  text        PRIMARY KEY
                     CONSTRAINT isaac_run_revisions_id_shape
                     CHECK (run_revision_id ~ '^[0-9A-Z]{26}$'),
    revision_id      text        NOT NULL
                     CONSTRAINT isaac_run_revisions_revision_fk
                     REFERENCES isaac_experiment_revisions (revision_id),
    run_id           text        NOT NULL
                     CONSTRAINT isaac_run_revisions_run_id_shape
                     CHECK (run_id ~ '^[0-9A-Z]{26}$'),
    ordinal          bigint      NOT NULL DEFAULT 0
                     CONSTRAINT isaac_run_revisions_ordinal_non_negative
                     CHECK (ordinal >= 0),
    state            jsonb       NOT NULL
                     CONSTRAINT isaac_run_revisions_state_is_object
                     CHECK (jsonb_typeof(state) = 'object'),
    rev              bigint      NOT NULL DEFAULT 0
                     CONSTRAINT isaac_run_revisions_rev_non_negative
                     CHECK (rev >= 0),
    generation       text        NOT NULL,
    created_utc      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_run_revisions_revision_run_unique
    UNIQUE (revision_id, run_id),
    CONSTRAINT isaac_run_revisions_document_identity
    CHECK (state ->> 'id' = run_id)
);

CREATE INDEX IF NOT EXISTS isaac_run_revisions_run_idx
    ON isaac_run_revisions (run_id, revision_id);

CREATE TABLE IF NOT EXISTS isaac_revision_changes (
    change_id    text        PRIMARY KEY
                 CONSTRAINT isaac_revision_changes_id_shape
                 CHECK (change_id ~ '^[0-9A-Z]{26}$'),
    revision_id  text        NOT NULL
                 CONSTRAINT isaac_revision_changes_revision_fk
                 REFERENCES isaac_experiment_revisions (revision_id),
    unit_id      text        NOT NULL
                 CONSTRAINT isaac_revision_changes_unit_id_shape
                 CHECK (unit_id ~ '^[0-9A-Z]{26}$'),
    address      text        NOT NULL
                 CONSTRAINT isaac_revision_changes_address_non_empty
                 CHECK (length(address) > 0),
    change_kind  text        NOT NULL
                 CONSTRAINT isaac_revision_changes_kind_known
                 CHECK (change_kind IN ('added', 'removed', 'modified')),
    created_utc  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT isaac_revision_changes_unique
    UNIQUE (revision_id, unit_id, address)
);

CREATE INDEX IF NOT EXISTS isaac_revision_changes_address_idx
    ON isaac_revision_changes (unit_id, address, revision_id);
```

**Three tables. Three indexes. No `ALTER`, no `DROP`, no `TRUNCATE`, no data movement, no backfill.**

### Each element, and why it is there

| Element | Why |
|---|---|
| `isaac_experiment_revisions` | One row per captured snapshot of an experiment. `state` holds `Experiment.to_state()` verbatim — a **snapshot, not a diff**, because a diff chain is only as good as its oldest link and one corrupt link makes every later revision unreadable. |
| `revision_no` + `UNIQUE (experiment_id, revision_no)` | The human-facing ordinal, assigned as `previous + 1` inside the same transaction that inserts the row. The UNIQUE constraint is what makes that assignment safe under concurrency: two writers computing the same next number cannot both land, and the loser's whole transaction rolls back. It also supplies the index for "the latest revision of this experiment", so no separate index is created for that read. |
| `experiment_rev`, distinct from `revision_no` | `rev` counts every authoritative mutation and moves without anything being recorded here; `revision_no` counts rows in this table. Conflating them is the mistake this column pair exists to prevent. |
| `content_signature` + `CHECK (~ '^[0-9a-f]{64}$')` | The sha256 of the **submitted content** — ~~the export units' ids and drafts only~~ **the export units' ids and drafts, plus the record's stored conflict decisions (corrected in place; see the note under this table)**. It excludes `rev`, `updated_utc`, `record_id` and every server timestamp, so it is **stable across materialisation**: the value computed before the official records are written equals the one computed after. That stability is what makes it usable as an idempotency key and is why the column is not a digest of `state`. **One degraded exception (M4):** a materialised record that is unreadable, or whose own `record_id` disagrees with the file carrying it, drops out of its sibling group in `workspace._linkable`, which changes the links composed into its siblings' drafts and moves the signature. The claim holds for every readable, self-consistent artifact set. |
| `reason` + `CHECK (IN ('submission'))` | A closed set rather than free text, because an unconstrained column becomes a place to write prose nothing can query. One member today. |
| `subject`, nullable, `CHECK (subject IS NULL OR length(subject) > 0)` | The canonical Authentik username, or NULL. **Never** a display name, an email, or a uid — `docs/identity-trust-contract.md` §9 disqualifies email as an identifier and records it as personal data, and the 2026-08-12 decision is that the username is the one canonical key. **The non-empty CHECK closes the value that slips between the two halves of the attribution pairing (review item M1):** `''` is not NULL, so without it a row whose subject is the empty string reads as **attributed** while naming nobody. Unreachable from this application — `HumanActor` and `EdgeAssertion` both reject an empty subject before a row is built — and declared anyway, because `ALTER` is a forbidden verb and a CHECK omitted here would need a whole further migration. |
| `trust_basis` + `CHECK (IN ('unattributed','test_fixture','verified_edge_assertion'))` | **What vouched for `subject`, recorded in the row rather than inferable later.** No verifier in this build mints `verified_edge_assertion`, so no row can carry it yet; it is admitted so that the day one does, the older rows are already visibly labelled as something weaker. |
| `CONSTRAINT isaac_experiment_revisions_attribution` | `(trust_basis = 'unattributed') = (subject IS NULL)`. An **equality**, so both halves are closed: a row cannot carry a name nothing vouched for, and a row cannot claim an attribution basis while naming nobody. The first is the shape the whole identity seam exists to refuse. |
| `isaac_run_revisions` | One row per run per revision. An experiment with no runs contributes **zero** rows, correctly: its single export unit is the experiment itself, whose draft is already inside the snapshot. Writing a synthetic row for it would invent a run. |
| `isaac_run_revisions.run_id` — **no foreign key** | See §3. |
| `isaac_revision_changes` | Which addresses differ from the previous revision. See §2.1 for the exact, narrow meaning of "differ". |
| The three indexes | `isaac_experiment_revisions_experiment_time_idx` is the chronological listing (the UNIQUE constraint already indexes `(experiment_id, revision_no)` for the latest-revision read, so this is not a duplicate) and also serves the parent-side foreign-key check. `isaac_run_revisions_run_idx` and `isaac_revision_changes_address_idx` lead on a column the UNIQUE constraints do not, so each is a genuinely different access path. |

**CORRECTION IN PLACE, 2026-08-25 — the `content_signature` row above described a scope
one term too narrow, and the SQL is untouched.** `submissions.content_signature` now
digests the export units' ids and drafts **and** the record's stored conflict decisions
(`draft["conflict_resolutions"]`). Nothing about this migration changed: the column's
type, its `^[0-9a-f]{64}$` CHECK, the `UNIQUE (experiment_id, content_signature)` on
`isaac_submissions`, and the file's sha256 digests are all exactly as approved — what
widened is the application's computation of the value the column stores, which the
migration deliberately does not constrain.

Why it widened, briefly, because it bears on the `reason` row directly below. A conflict
decision taken AFTER a submission was recordable on a record with no runs and
unrecordable on a record with runs: the zero-run export unit's draft IS `exp.draft`,
where decisions are stored, while a run's composed draft deliberately excludes them
(`workspace.resolved_run_draft`). So the digest moved for one record shape and not the
other, and `isaac_submissions.conflict_summary` — the one place a submission discloses
that a person settled a conflicting field — could never be written again for a record
with runs. **The alternative fix was a second `reason` value** ("a decision" as its own
revision reason), and it was rejected precisely because of the row below: `reason` is a
closed CHECK set with one member, widening it needs an `ALTER`, `ALTER` is a forbidden
verb here, and it would require a further migration, a further packet and a further
operator action to record something the existing columns can already express.

Two consequences a reader of this packet should be able to check rather than take on
trust. **No stored row is invalidated**, because no `isaac_submissions` row exists
anywhere: `0003` and `0004` are applied in no deployment, and `submission_store.store()`
has no filesystem fallback. And **the M4 stability exception above is unaffected** — a
decision is not written by materialisation, so the "stable across materialisation"
property is exactly as strong as it was.

**AND THE SQL FILE'S OWN PROSE NOW SAYS SOMETHING FALSE — DISCLOSED HERE BECAUSE IT
CANNOT BE CORRECTED.** `0003_revisions.sql:122-123` documents the column as *"computed
by `submissions.content_signature` over the export units' ids and drafts **ONLY**"*.
That `ONLY` is now wrong, in exactly the way the table row above was wrong before it was
struck: the digest also covers the record's stored conflict decisions. **The comment is
not correctable, and the reason is the approval rather than the effort.** §"The bytes
being approved" pins this file's sha256; `git log --follow` shows the SQL has had exactly
one version ever (commit `0896b07`, never since touched); and the project owner approved
**those exact bytes** on 2026-08-17. Changing one comment character changes the digest,
so it would invalidate an owner approval of a migration whose operator step is still
outstanding. Re-opening an approval to reword a comment is the wrong trade; leaving the
staleness undisclosed is not an option either, so the staleness is recorded here instead
of being fixed.

**What a reader of that comment should treat as authoritative instead**, in this order:
the corrected `content_signature` row in the table above, and
`submissions.content_signature`'s own docstring, which states the coverage as the
experiment id, each export unit's id and fully resolved draft, and the record's stored
conflict decisions — and carries the measured defect that widened it. The scope is also
served rather than only documented: `submissions.SIGNATURE_SCOPE` reads
`export_unit_ids_drafts_and_conflict_decisions` and moved when the coverage moved. The
rest of that SQL comment — the exclusions of `rev`, `updated_utc`, `record_id` and every
server timestamp, the stability-across-materialisation property, and the M4 degraded
exception — is unchanged and still accurate; the single stale term is `ONLY`.

**Nothing about the migration changed, and this note changes nothing about it.** No SQL
byte, no column type, no CHECK, no UNIQUE constraint, no index, no digest in this packet
and no approval was altered — what widened is the application's computation of the value
the column stores, which the migration deliberately does not constrain.
`0004_submissions.sql:70-71` carries the same stale `only` about the same digest, and
[`docs/migration-approval-packet-0004.md`](migration-approval-packet-0004.md) §2
discloses it there in the same terms, because that is the packet for the table whose
`UNIQUE (experiment_id, content_signature)` actually uses the column.

### 2.1 What a change row means, stated narrowly

`submissions.address_changes` compares, for every export unit, the **`value` of each entry under
`draft["fields"]`**, canonicalised as JSON. It does **not** diff evidence entries, run overrides,
answer logs, assets, implicit claims, or anything nested inside a value beyond that value's canonical
form.

So a row here means *"this field's value differs from the previous revision"*, and the **absence** of
rows means only *"no field value differed"* — never *"nothing about this unit changed"*. The API
carries `changes_comparable` beside `change_count` so that a zero cannot be read as "nothing changed"
when the truth is "there was nothing to compare against".

### 2.2 Three unused indexes, disclosed rather than justified away

`isaac_run_revisions_run_idx` and `isaac_revision_changes_address_idx` serve reads **no code in this
build issues**. They are created now because `ALTER` is a forbidden verb in
`db_write._FORBIDDEN_KEYWORDS` and `CREATE TABLE IF NOT EXISTS` is a silent no-op against an existing
table — so anything omitted here needs a whole further migration, its own approval packet, and its
own operator action. The cost is one B-tree each, maintained on append-only tables. **This cuts both
ways and is stated as a cost: an index included here and later found wrong cannot be dropped either.**

## 3. `isaac_run_revisions.run_id` is deliberately NOT a foreign key

**History must survive the thing it describes.** A run can be removed from an experiment —
`Experiment.save` issues `Q_DELETE_ABSENT_RUNS` for every run the document no longer names — and when
it is, the row in `isaac_runs` goes away. A foreign key would then do one of two things, and both are
wrong:

* **without `CASCADE`:** refuse that deletion, freezing the live table behind its own audit log;
* **with `CASCADE`:** delete the history, which is the one outcome an append-only log may never have.

**Disclosed honestly, as `0002_runs` discloses the same thing:** `ON DELETE CASCADE` is *also*
unwritable under the current statement policy — the tokenizer reads the `delete` after `on` as naming
a table this application does not own — so the choice was never actually open. The design argument
stands on its own; this note exists so a reader is not told a constraint was a free choice when it
was also forced.

**The cost, stated:** nothing at the database level guarantees that a `run_id` in this table names a
row in `isaac_runs`. A reader must treat a run id here as a **historical name**, not a live reference.

`isaac_revision_changes.unit_id` is a plain column for the same reason.

## 4. What it deliberately does *not* do

* **It does not touch `records`.** The production-derived 30-row sample is neither read, written,
  altered, nor referenced in a constraint. `db_write._FORBIDDEN_TABLES` refuses any statement naming
  it in any position and any syntax, and
  `test_no_new_migration_or_rollback_names_the_production_table` reads all four committed files off
  disk and asserts the identifier does not appear.
* **It does not alter `isaac_experiments` or `isaac_runs`.** `alter` is a forbidden verb, so an
  altering migration could not run at all.
* **It moves no data and backfills nothing.** Every existing experiment has zero revisions after this
  applies, which is the truth: none of them was ever submitted.
* **It writes no `ON DELETE` clause anywhere**, so no single statement can destroy a history tree.
* **It changes no application behaviour on its own.** With 0003 applied and 0004 pending, the
  submission route answers `503 submission_unavailable / tables_absent` — see §6.

## 5. Transaction and locking behaviour

One transaction, opened by `db_write.write_transaction` with `SET LOCAL statement_timeout = 15000ms`
and `SET LOCAL lock_timeout = 3000ms`, and the bookkeeping row is written inside it — so "applied"
and "recorded" cannot disagree.

**Locks taken against tables that already have rows:** `isaac_experiment_revisions`' foreign key takes
`SHARE ROW EXCLUSIVE` on `isaac_experiments` for the duration. That table holds this application's own
experiments and is written only by short transactions; with a 3-second `lock_timeout`, the failure
mode of a concurrent write is that **this migration refuses**, not that the application blocks. The
other two tables reference only tables this migration itself creates, so they contend with nothing.

**No lock of any kind is taken on `records`.** No statement names it.

## 6. Idempotence, and the window while it is pending

Idempotent twice over, exactly as `0001` and `0002` are: `db_migrate` skips a version already recorded
in `isaac_schema_migrations`, **and** every statement is `CREATE ... IF NOT EXISTS`, so a re-run is a
no-op even if the bookkeeping row were lost.

**The pending window is a real deployment state and is handled explicitly.** The image rolls out on
merge and an operator applies migrations by hand afterwards, so a build routinely runs against a
database its own migration has not reached. `submission_store.PostgresSubmissionStore.preflight`
probes all five relations with `to_regclass` — which *answers* NULL rather than raising — **before any
official record is materialised**, and the route returns a typed `503` that publishes nothing. Every
other route is untouched: no read path names any of these tables.

## 7. Who can run it — and who cannot

The application cannot migrate itself. `db_migrate.migrate` is called by `scripts/db_migrate.py`, an
operator command, and by CI against a service container. A pod does not migrate itself on boot.

**No agent may apply this.** See the STATUS block.

## 8. Prechecks — run these first, and read the output

```bash
# 1. Confirm the target. Must print exactly: metadata_assistant
psql -Atc "select current_database()"

# 2. Confirm what is already applied. Expect exactly two rows: 0001_experiments, 0002_runs.
psql -Atc "select version from isaac_schema_migrations order by version"

# 3. See what WOULD be applied, UNBOUNDED — i.e. what the runner can see at all.
#    EXPECT: pending: 0003_revisions, 0004_submissions, 0005_run_projection
#    That third name is EXPECTED and is not a problem: 0005 is committed but not
#    owner-approved, and §9's command is bounded so it cannot reach it. If this
#    line names 0002_runs, or names anything you do not recognise, STOP.
#    Applies no MIGRATION — but it is NOT read-only: `pending_versions` opens a
#    transaction and ensures the bookkeeping table exists.
python scripts/db_migrate.py --plan

# 3b. The BOUNDED plan — this is the one §9 tells you to diff, and it is the same
#     selection §9's apply carries out.
#     EXPECT, exactly two lines:
#       pending through 0004_submissions: 0003_revisions, 0004_submissions
#       withheld by --through 0004_submissions: 0005_run_projection
python scripts/db_migrate.py --plan --through 0004_submissions

# 4. THE COUNT THAT MATTERS. Record it; postcheck 1 compares against it.
psql -Atc "select count(*) from records"

# 5. The experiment count. Record it; postcheck 2 compares against it.
psql -Atc "select count(*) from isaac_experiments"

# 6. Confirm none of the target tables already exists (expect 0).
psql -Atc "select count(*) from information_schema.tables where table_schema='public'
           and table_name in ('isaac_experiment_revisions','isaac_run_revisions',
                              'isaac_revision_changes')"

# 7. Confirm nothing is holding conflicting DDL on isaac_experiments (expect 0 rows).
#    The FK takes SHARE ROW EXCLUSIVE on it and the lock_timeout is 3s.
psql -Atc "select count(*) from pg_locks l join pg_class c on c.oid = l.relation
           where c.relname = 'isaac_experiments' and l.mode like '%Exclusive%'"

# 8. The engine build string, so the version actually under test is recorded.
psql -Atc "select version()"
```

## 9. The exact command — bounded to these two migrations

**Two invocations. Run the first, read its output against the block below, then run the second.**

```bash
python scripts/db_migrate.py --plan --through 0004_submissions
```

Expected output, exactly — two lines:

```
pending through 0004_submissions: 0003_revisions, 0004_submissions
withheld by --through 0004_submissions: 0005_run_projection
```

```bash
python scripts/db_migrate.py --apply --through 0004_submissions
```

Expected output, exactly — two lines:

```
applied through 0004_submissions: 0003_revisions, 0004_submissions
withheld by --through 0004_submissions: 0005_run_projection
```

**If either invocation prints anything else, STOP and report what it printed.** In particular, a
first line naming `0002_runs` means the database is not where precheck 2 said it was, and a first
line naming `0005_run_projection` means the bound was not applied — neither is a state to proceed
from.

Each migration gets its own transaction, in lexical order. The second line is a fact about the
committed migration files, not about your database: it names what this invocation deliberately left
alone, so *"`0005` was not applied"* is something you read rather than something you infer.

> **CORRECTED 2026-08-25 (second correction, same section) — the instruction above is now a
> BOUNDED command, and the two corrections are kept in order because they are different defects.**
>
> **The first correction** retired a false "exactly". §9 used to read: ~~*"It applies **both**
> `0003_revisions` and `0004_submissions`, in that order, one transaction each. Expected output,
> exactly: `applied: 0003_revisions, 0004_submissions`"*~~. That was true when written and stopped
> being true when `0005_run_projection.sql` was committed, so an operator who acted on the old
> "exactly" would have applied an unapproved migration to a database holding 30 production-derived
> records. That strike stands.
>
> **The first correction left the section honest and the ask impossible**, and it said so: it
> replaced the command with a bare `--apply` plus a table of states, one of whose rows was
> *"**STOP.** `0005` is not approved. Do not run `--apply` in this state"* — and that row is the
> state the hosted database is actually in. So §9's own instruction could not be carried out. The
> operator addendum recorded that as **BLOCKED** rather than pending, which was the right call and is
> now discharged: ~~*"`scripts/db_migrate.py` exposes `--plan` and `--apply` and **no `--only
> <version>`**"*~~ — **the runner now takes `--through VERSION`**, which applies every pending
> migration up to and including that version and nothing after it. It bounds `--plan` identically, so
> the plan you read above is the apply you get.
>
> **What `--through` is, and is not.** *Up to and including* is its only shape: there is no
> per-version pick and no way to skip one, because `0004` declares a foreign key into a table `0003`
> creates and a runner that could apply one without the other would be a runner for breaking a
> schema. It is **not a rollback** — it selects a prefix of the forward set, drops nothing, and
> deletes no bookkeeping row; it cannot even be pointed at a `*.rollback.sql` file, because the
> loader excludes those by suffix and an unrecognised version is a refusal. **A misspelled version
> refuses loudly, before any connection is opened**, and never falls back to applying everything or
> to applying nothing. And **every statement still passes `db_write.WriteStatementPolicy`** — that is
> why this is the resolution and "apply the SQL by hand with psql" was not.
>
> **Nothing about the bytes being approved changed.** The four digests in the STATUS block and in
> §"The bytes being approved" are unchanged; this is a change to the operator command, not to the
> migration.

## 10. Postchecks — what would prove it worked

**Postchecks 1 and 2 are REQUIRED and must be reported.** `0002`'s §12C records both as *not
reported* — the `records` count before/after (*"the one that matters"*) and the `isaac_experiments`
count before/after. The migration issues zero DML and names `records` in no statement, so there is no
mechanism by which either could move — but **"no mechanism exists" is not the same as "it was
measured"**, and this packet is asking for the measurement rather than the argument.

```bash
# 1. REQUIRED. Must be UNCHANGED from precheck 4.
psql -Atc "select count(*) from records"

# 2. REQUIRED. Must be UNCHANGED from precheck 5.
psql -Atc "select count(*) from isaac_experiments"

# 3. The three tables exist with the constraints this packet describes.
psql -c "\d+ isaac_experiment_revisions"
psql -c "\d+ isaac_run_revisions"
psql -c "\d+ isaac_revision_changes"

# 4. The three indexes exist with the columns named in §2.
psql -Atc "select indexname, indexdef from pg_indexes
           where tablename in ('isaac_experiment_revisions','isaac_run_revisions',
                               'isaac_revision_changes') order by indexname"

# 5. No ON DELETE action anywhere (expect every confdeltype to be 'a' = NO ACTION).
psql -Atc "select conname, confdeltype from pg_constraint
           where conrelid::regclass::text like 'isaac_%revision%' and contype = 'f'"

# 6. The versions are recorded. Quote the rows verbatim.
psql -Atc "select version, applied_utc from isaac_schema_migrations order by version"

# 7. All three are empty. Nothing backfills them.
psql -Atc "select (select count(*) from isaac_experiment_revisions),
                  (select count(*) from isaac_run_revisions),
                  (select count(*) from isaac_revision_changes)"

# 8. Idempotence: a second run applies nothing. KEEP THE BOUND ON. Without it
#    this postcheck would itself apply 0005_run_projection — the exact outcome
#    §9 exists to prevent, arriving through a check meant to prove nothing moved.
python scripts/db_migrate.py --apply --through 0004_submissions
#    EXPECT, exactly two lines:
#      nothing to apply through 0004_submissions (every migration up to it is already recorded)
#      withheld by --through 0004_submissions: 0005_run_projection

# 9. The engine build string again, so it is on the record either side.
psql -Atc "select version()"
```

**10. The application is unaffected.** Through the hosted UI: `/api/health` still reports
`experiment_storage {backend: "postgres", durable: true, state: "durable"}`; create an experiment; it
still works; My Experiments still lists it. `/api/health`'s new `submission` block reports
`configuration_permits: false` with `blockers: ["no_attributable_actor"]` — because no verifier is
configured on the hosted deployment, which is the correct and intended state (see §13).

## 11. Rollback

`apps/api/isaac_api/migrations/0003_revisions.rollback.sql`, run by a human with psql:

```bash
psql -v ON_ERROR_STOP=1 -f apps/api/isaac_api/migrations/0003_revisions.rollback.sql
```

The application cannot run it: `load_migrations` excludes `*.rollback.sql` by suffix, and the file
contains `DROP`, which `db_write.WriteStatementPolicy` refuses wherever it appears.

**One honest difference from `0001`'s rollback, the same one `0002`'s packet records:** every
statement in 0001's rollback is a `DROP`, so each is independently refused by the write policy. This
file also contains a `DELETE` against the bookkeeping table, and that statement *would* pass the
policy on its own. The file as a whole is still refused and the loader still never reads it — but the
stronger property is not true of this file, and a reader should not infer it from the shared filename.

### ORDER MATTERS, twice over

* **Within the file:** `isaac_run_revisions` and `isaac_revision_changes` both reference
  `isaac_experiment_revisions`, and no drop uses `CASCADE`, so the children go first. The file does
  this.
* **Across files:** `isaac_submissions` (0004) references `isaac_experiment_revisions`, so **this file
  FAILS while 0004 is applied.** The full order is **0004, 0003, 0002, 0001.** CI proves both the
  failure on the wrong order and the success on the right one.

### What rolling back costs

**The entire submission history, irrecoverably.** Unlike `isaac_runs`, these tables are not a shadow
of anything: the experiment document carries no revision history and never will (§1). Dropping them
destroys the only copy. Dump first:

```bash
psql -c "\copy (SELECT * FROM isaac_experiment_revisions) TO 'revisions.csv' CSV HEADER"
psql -c "\copy (SELECT * FROM isaac_run_revisions) TO 'run-revisions.csv' CSV HEADER"
psql -c "\copy (SELECT * FROM isaac_revision_changes) TO 'changes.csv' CSV HEADER"
```

### Roll back if

* any postcheck 1 or 2 count moved;
* a constraint or index does not match §2;
* the application's health degrades in a way that traces to these tables.

**Do not roll back for** an empty table set — that is the expected state.

## 12. Evidence, and what remains unproven — read this before approving

### 12A. What has been executed, and where

| Proof | Where | Executed? |
|---|---|---|
| The file loads, is create-only, passes the owned-tables statement policy | `apps/api/tests/test_submission_store.py` | **yes**, in the local suite |
| Every constraint this packet names is present in the committed text | same | **yes** |
| The rollback is unreachable from the application, and drops only what 0003 created, children first | same | **yes** |
| No committed migration or rollback names `records` | same | **yes** |
| The change kinds, the revision reason and the three trust bases agree between Python and SQL | same | **yes** |
| The application's write path against a connection double: one transaction, deterministic rollback, nothing written on any refusal | same | **yes** |
| **The SQL is valid PostgreSQL** | `.github/workflows/ci.yml` → `postgres-migration` | **YES — see 12B** |
| **Every constraint THAT STEP NAMES rejects what it claims to reject — 41 of the 46 declared** | same, step *"Prove every 0003 and 0004 constraint rejects what it claims to reject"* | **YES, for the 41** (run `32800763199`, job `97660962127`, at `c153ec9`). ~~"**YES, for the 27.** The other 19 are declared and unexercised"~~ was true of run `32099627898` at `fe374c0` and was overtaken on 2026-08-25 — see §12B. **5** remain unexercised, 3 of them unprovably so |
| **The submission lifecycle works end to end against a real engine** | same, step *"Exercise the submission lifecycle against the real engine"* | **YES** |
| **The rollbacks return the database to its prior table set** | same, incl. the wrong-order refusal | **YES** |

### 12B. What a real PostgreSQL has and has not executed

**CORRECTED 2026-08-17, and the old text is quoted here rather than silently replaced, because it was
a claim this packet was pinned on and it had gone false.** This section used to read:

> *"**No PostgreSQL has ever executed this file.** The machine it was written on has no PostgreSQL and
> no psycopg2 (`which psql` → not found). Every local proof above is a property of the committed
> **text** and of the application's behaviour against an **in-process connection double**. Until the
> `postgres-migration` job runs on this branch, `"this is valid SQL"` is an **unverified claim**, and
> this packet must not be cited for it."*

That was true when written, and **it is false now**, because the condition it named as the thing that
would falsify it — *"until the `postgres-migration` job runs"* — has happened. Worse, a test
(`test_the_packets_do_not_claim_a_hosted_application`) **pinned the sentence as a required literal**,
so the repository was mechanically enforcing a false claim about itself. The test has been changed in
the same commit to pin the invariant that actually matters — that this packet does not read as
hosted-applied — instead of a sentence about CI that time was always going to invalidate.

**What a real PostgreSQL HAS executed.** GitHub Actions run
[`32099627898`](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/32099627898), job
*"migration and durable repository against a real PostgreSQL"*, **conclusion `success`**, on `main` at
commit `fe374c0` — which carries these exact bytes (the digests in the table above are the digests at
that commit). Against a `postgres:18` service container it applied `0001`→`0004` forward, proved the
pending/applied plan at each step, ran the submission lifecycle end to end, and proved the rollback
order — including that `0003`'s rollback **fails** while `isaac_submissions` still references it, and
that the failed attempt destroys nothing.

### RE-MEASURED 2026-08-25 — a real PostgreSQL has now EXECUTED 41 of 46 on `main`

**The run.** GitHub Actions run
[`32800763199`](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/32800763199), job
`97660962127` *"migration and durable repository against a real PostgreSQL"*, **conclusion
`success`**, on `main` at commit `c153ec9` (the PR #171 merge, 2026-08-24 19:16 -0700). Its step
*"Prove every 0003 and 0004 constraint rejects what it claims to reject"* prints one `refused as
designed by <object>` line per case; that job emitted **67** such OUTPUT lines naming **58** distinct
objects (the set spans `0002`, `0003`/`0004` and `0005`), and intersecting them with the **46**
constraints declared across the two forward files gives exactly **41** — the same 41, and the same
five absences, that the file-based measurement gives.

> **THE TWO SUPPORTING FIGURES WERE WRONG AND ARE CORRECTED HERE, IN THE PACKET AN OPERATOR WEIGHS.**
> This paragraph read ~~"**70** such lines naming **57** distinct objects"~~. Re-derived on 2026-08-25
> from `gh api repos/ISAAC-DOE/isaac-metadata-assistant/actions/jobs/97660962127/logs`:
>
> ```
> lines containing "refused as designed by"                        : 70
>   of which are Actions echoing the run: block's own shell source :  3
> genuine OUTPUT lines                                             : 67
> distinct objects over those 67                                   : 58
> intersect(the 46 declared by 0003+0004, those objects)           : 41
> ```
>
> **70** counted the three lines where Actions echoes `echo "refused as designed by $3: $1"` as
> though they were results. **57** reproduces under neither counting: it came from a truncating
> regex (`[A-Za-z0-9_.]*`) that collapsed the three `column "…"` objects into one and captured the
> **empty string** from each of the three echoed lines — so an empty string was counted as a blamed
> object (53 + 4 = 57). **41 is unaffected**, because it is an intersection with the declared set and
> neither error reached it. The same correction is applied in `CLAUDE.md` and in
> `apps/api/tests/test_submission_store.py`; `docs/dean-operator-addendum-2026-08-25.md` §1 already
> carried **67** correctly, which is how the discrepancy was found.

> **THIS HEADING HAS BEEN WRONG TWICE, IN OPPOSITE DIRECTIONS. BOTH CORRECTIONS ARE KEPT, BECAUSE THE
> SEQUENCE — 41 (false) → 27 (true) → 41 (true, by a different run) — is what tells an operator that
> the number is measured rather than drifting.**
>
> **(i)** ~~"coverage improved from 27 to 41 of 46"~~ (2026-08-19) sat directly under "What a real
> PostgreSQL HAS executed" and was read as though a run had produced 41. It had not.
>
> **(ii)** ~~"the WORKFLOW FILE now declares 41 of 46; a real PostgreSQL has run 27"~~ (2026-08-24)
> was the CORRECT reading of the evidence then available, and it is **retired by events, not by
> error.** The fourteen extra cases arrived in commit `77de2db` (2026-08-19), which was not in `main`
> when (ii) was written; it **merged on 2026-08-25 via `c153ec9`**, and
> `git merge-base --is-ancestor 77de2db origin/main` now exits 0. Likewise ~~"Run `32099627898`, at
> `fe374c0`, is the only execution against a real PostgreSQL this repository can point to"~~ — there
> are now two, and the later one is the one this packet cites. And ~~"An operator weighing this
> packet's evidence should read 27."~~ — **an operator should now read 41.**
>
> **27 IS STILL EXACTLY RIGHT FOR RUN `32099627898` AT `fe374c0`**, and nothing here should be read as
> retracting it. A figure that is superseded by a later measurement is not a figure that was wrong.

**The seventeen that were declared and never exercised have now been exercised BY A REAL POSTGRESQL
(run `32800763199`), and the correction below is kept in place rather than deleted because it records
how the number moved and why three of the seventeen still cannot be counted.**

Measured with the same rule the guard test applies — a constraint is *blamed* only when it is the
third argument of a `refuse()` call, which is the object PostgreSQL must be shown to blame:

| | Then — `fe374c0`, run `32099627898` | **Now — `c153ec9`, run `32800763199`** |
|---|---|---|
| declared across the two forward files | 46 | **46** |
| blamed by a `refuse()` call | 27 | **41** |
| not blamed | 19 | **5** |
| named nowhere in the workflow | 17 | **3** |
| executed against a real PostgreSQL | **27** | **41** — ~~"**27 — unchanged**"~~, retired 2026-08-25 when `77de2db` reached `main` |

**FOURTEEN of the seventeen are now proved individually.** Each new case differs from an accepted row
in exactly one column, so the constraint it names is the only thing left to blame — which is the
property that makes a `refuse()` call evidence rather than a formality.

**THREE CANNOT BE PROVED INDIVIDUALLY, AND THAT IS A FACT ABOUT THE SCHEMA RATHER THAN A GAP IN THE
TESTING.** `isaac_submission_runs` carries two equality CHECKs — `record_id = unit_id`
(`one_record_per_unit`) and `run_id IS NULL OR run_id = unit_id` (`run_matches_unit`). So any row
that violates `isaac_submission_runs_unit_id_shape`, `_record_id_shape` or `_run_id_shape` violates
an equality CHECK at the same time:

* `unit_id` malformed and `record_id` equal to it → **both** shape CHECKs fail;
* `unit_id` malformed and `record_id` well-formed → the equality CHECK fails too;
* `run_id` malformed → `run_matches_unit` fails too.

There is no assignment of those three columns that violates exactly one of them, and PostgreSQL
reports only the first constraint it happens to check. **This is defence in depth, not a defect** —
the equality CHECKs subsume the shape CHECKs — but "every constraint is individually blamed" is a
claim this table cannot support. The workflow proves those rows ARE refused, by a CHECK on that
table, through a deliberately weaker helper (`refuse_by_the_table`) that greps the constraint-name
prefix instead of a single name, so nobody can mistake it for the stronger check.

**The remaining two are the pre-existing pair**: `isaac_revision_changes_revision_fk` and
`isaac_submissions_experiment_fk` appear in the workflow for other reasons without any refusal being
blamed on them.

So the honest summary is: **41 of 46 individually blamed; 3 more proved refused with the blame
ambiguous by construction; 2 named without being driven by a refusal.**

---

**THE ORIGINAL CORRECTION, KEPT: CONSTRAINT COVERAGE IS PARTIAL, AND AN EARLIER REVISION OF THIS
SECTION SAID "EVERY".** Corrected
after an independent review measured it; the measurement was then reproduced independently before this
paragraph was written. The two forward files declare **46 named constraints**. CI's step *"Prove every
0003 and 0004 constraint rejects what it claims to reject"* then made 31 `refuse()` calls blaming **27
distinct constraints**, and `refuse()`'s third argument is the object PostgreSQL must be shown to
blame — so a constraint the workflow never names is a constraint that was never exercised. **17
declared constraint names did not appear in `.github/workflows/ci.yml` at all:**

`isaac_experiment_revisions_no_positive`, `_rev_non_negative`, `_state_is_object`;
`isaac_run_revisions_id_shape`, `_run_id_shape`, `_ordinal_non_negative`, `_rev_non_negative`,
`_state_is_object`; `isaac_revision_changes_id_shape`, `_unit_id_shape`;
`isaac_submissions_id_shape`, `_conflict_summary_is_object`, `_trust_basis_known`;
`isaac_submission_runs_id_shape`, `_unit_id_shape`, `_run_id_shape`, `_record_id_shape`.

*(46 − 27 = 19 unexercised, of which 17 were never named anywhere in the workflow and 2 are named
elsewhere in it without being driven by a `refuse()` call.)*

**Why this matters enough to correct rather than footnote.** The owner's approval in the STATUS block
is recorded as resting partly on this evidence, and the flip of these rows from *"not yet"* to *"YES"*
was this slice's own act — so an overstatement here inflates the basis of an approval. Seven of the
seventeen are the anchored `^…$` id-shape CHECKs, which is the class CI's own commentary singles out as
data-correctness-critical. That class is genuinely proven for
`isaac_experiment_revisions_id_shape` and for the two signature columns, and **generalised to the rest
without being run**. Nothing suggests the unexercised constraints are wrong; the point is that this
packet may not be cited as evidence that they behave.

> **THAT LAST SENTENCE EXPIRED ON 2026-08-25 FOR FOURTEEN OF THE SEVENTEEN, and the paragraph above is
> left standing because it is the record of a real overstatement and of the vantage point that made it
> one.** Fourteen of the seventeen are now blamed by an individual `refuse()` call that a real
> PostgreSQL executed (run `32800763199`, at `c153ec9`), so this packet MAY now be cited as evidence
> that they behave. The three `isaac_submission_runs` shape CHECKs still may not be cited
> individually — see the subsumption argument above — and that limitation is permanent rather than
> pending.


**The still-unproven class, which CI does not touch and which is the whole reason the operator's act
is separate.** The service container is an **empty** `postgres:18` with a two-row synthetic stand-in
for `records` — not the hosted database with its 30 production-derived records, its roles, and its
existing grants. So *"is this valid, idempotent, self-contained SQL whose constraints behave"* is now
**answered**; *"does it behave against the real data, roles and grants"* is **not**, and only the owner
applying it resolves that. **Do not cite this section as evidence for the second question.**

~~*"CI, when it runs, removes the … class of risk."*~~ **That sentence is struck as of 2026-08-17: CI
HAS run** (see above), and *"when it runs"* read as though it had not — the very defect this section
was corrected for, surviving four lines below the correction. The distinction it drew is still right
and is stated once, above, rather than twice: CI retires *"is this valid, idempotent, self-contained
SQL"*; it does not retire *"does it behave against the real data, roles and grants"*, and — per the
paragraph immediately above — it retires the constraint question only for the 27 constraints its step
actually names.

### 12C. The immutability limit — do not let a reader infer a guarantee that is not here

These tables are **append-only by statement inventory and by test, not by the database.**

The two mechanisms that would make it a database guarantee are both unavailable, and neither absence
is an oversight:

* a `BEFORE UPDATE OR DELETE` trigger needs a function body, which needs dollar quoting, which
  `db_migrate.split_statements` refuses outright;
* `REVOKE UPDATE, DELETE` is refused by `db_write._FORBIDDEN_KEYWORDS`, which bans `revoke` and
  `grant` wherever they appear, in migrations included.

What holds the property is
`test_submission_store.py::test_no_submission_statement_updates_or_deletes_history`, which parses
every module-level `Q_*` constant in every backend module and fails if one issues an `UPDATE` or a
`DELETE` naming any of these tables — or an `INSERT ... ON CONFLICT DO UPDATE`, which is the same
defect wearing the upsert's clothes. That is a real guard over **this application's own code**. It is
**not** a guarantee about a psql session, a superuser, or a future application, and nothing in this
repository may describe these rows as immutable at the database level.


### 12D. The five approval checks, and what each one actually verified

Recorded here because the STATUS block's approval is *conditional* on them, and a condition nobody can
audit is not a condition. Performed 2026-08-17 on `main` at `fe374c0`, before the STATUS block was
written.

| # | Condition | Command / method | Result |
|---|---|---|---|
| 1 | Forward SHA-256 still matches this packet's table | `shasum -a 256` on the file, compared to the digest table above | **match** |
| 2 | Rollback SHA-256 still matches | same | **match** |
| 3 | No material SQL change since technical review | `git log --oneline -- <both .sql files>` | **one commit, ever** (`0896b07`); no commit has touched either file since, so there has never been a second version of these bytes to drift from |
| 4 | Prior review findings remain resolved | read the forward SQL end to end; the review items it names as fixed (**M1** the non-empty `subject` CHECK, **M4** the disclosed `content_signature` stability exception) are present in the committed text, and `test_the_approval_packets_named_constraints_are_in_the_committed_text` pins every constraint the packet claims | **resolved, and pinned** |
| 5 | No new material safety defect | structural scan of both files for `ALTER`/`DROP`/`TRUNCATE`/`GRANT`/`REVOKE`/DML and for any identifier naming `records`; verb inventory of the forward file; rollback inventory | **none found** — see below |

**What check 5 actually looked at, so it is not read as broader than it was.** Every statement in the
forward file is `CREATE TABLE IF NOT EXISTS` or `CREATE INDEX IF NOT EXISTS` and nothing else: no
`ALTER`, no `DROP`, no `TRUNCATE`, no `GRANT`/`REVOKE`, no DML, no dollar-quoted body, and no
`ON DELETE` clause in any statement — the phrase occurs only in comments — so every foreign key takes
the SQL default, `NO ACTION`, and no cascade exists. The identifier `records` appears in no statement in either file. The rollback drops only
tables this migration creates, children before parents, and deletes only its own bookkeeping row.

**This check was a READ of the committed text plus a structural scan — not a runtime observation, and
not a substitute for the independent technical review that produced this packet.** It is the
"has anything changed, and is anything obviously unsafe" pass the approval was made conditional on. The
behavioural evidence is §12A/§12B's; the residual risk is the one §12B names and only the operator can
retire.

## 13. What this packet does not cover

* **`0004_submissions`.** Separate packet, same decision — read both.
* **Any read surface over this history.** Nothing in this build lists revisions or renders a
  submission to a scientist. The write path exists; the reading of it is a later slice.
* **Identity.** No verifier that can prove edge traversal exists, and this migration does not create
  one. On the hosted deployment every submission is refused `409 human_actor_required`, which is the
  correct behaviour and is unchanged by applying this. **Q4 is answered against us** — the Service is
  a plain ClusterIP with no NetworkPolicy — and building a trusted authentication boundary is a
  separate, unapproved decision.
* **The production-derived `records` table**, in any way at all.
* **Any hosted action.** Applying this is the owner's act.
