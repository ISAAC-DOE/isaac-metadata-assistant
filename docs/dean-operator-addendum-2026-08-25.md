# Operator addendum — 2026-08-25

**For:** Dean (SLAC infrastructure / database operator), via Krish.
**Successor to:** [`docs/dean-handoff-consolidated-2026-08-18.md`](dean-handoff-consolidated-2026-08-18.md),
which is **not replaced**. Read that package for the `0003`/`0004` ask; this document carries only
what is new or corrected since it was sent.

**Repository state this addendum describes:**

```
$ git rev-parse origin/main
c153ec980726b3da3d2425be03385d3da2e39bda
```

**No agent has connected to the hosted database, and none may**
(`docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52`). Every hosted figure in this
or any packet will be **operator testimony**, not a captured artifact. Nothing below is a request to
change how ISAAC is deployed.

---

## 0. What you must DO, and what is only FYI

| | |
|---|---|
| **DO — unchanged from 2026-08-18** | Answer **G2** and **G3** (§5). Neither touches infrastructure; both are decisions, and they gate more work than anything else here. |
| **DO — unchanged from 2026-08-18** | Apply **`0003_revisions` + `0004_submissions`** together, and report the `records` and `isaac_experiments` counts before and after. Their four digests are re-verified below and **unchanged**. |
| **DO NOT** | Apply **`0005_run_projection`**. It is **not owner-approved**. It is described in §2 so it is not a surprise, and because §2's last line is an operational consequence that survives whether or not you ever apply it. |
| **FYI — evidence got stronger** | The `0003`/`0004` constraint evidence is now **41 of 46 executed by a real PostgreSQL on `main`**, not 27. §1. This raises the evidence behind a decision you already have; it changes no byte you would apply. |
| **FYI — a correction to a number you were sent** | If your copy of the 2026-08-18 package shows `0005`'s forward digest as `ebff660f…`, that value is stale. §3. |
| **Not for you at all** | §4 (external configuration contracts, stated as contracts and **not** as requests) and §5 (open governance questions and their current fail-closed state). |

---

## 1. Correction: the `0003`/`0004` constraint evidence is now 41 of 46 executed, not 27

The sent package told you *"the number to act on is 27"*, and struck an earlier sentence claiming 41.
**That strike was correct and stays correct** — it retired a claim that credited run `32099627898`
(on `main` at `fe374c0`) with coverage that run could not have produced, because the fourteen extra
cases were on an unmerged branch.

**That branch has since merged, and a different run has now executed the 41.**

| Vantage point | Constraints | Evidence |
|---|---:|---|
| Executed by a real PostgreSQL at `fe374c0` | **27 of 46** | run [`32099627898`](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/32099627898), `success`, `2026-08-18T04:34:12Z` |
| **Executed by a real PostgreSQL at `c153ec9` (current `main`)** | **41 of 46** | run [`32800763199`](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/32800763199), job `97660962127`, step 20 *"Prove every 0003 and 0004 constraint rejects what it claims to reject"*, `success`, `2026-08-25T02:16:11Z` |

Re-derived here rather than quoted, by the rule the repository's own guard test applies
(`apps/api/tests/test_submission_store.py::test_the_two_constraint_numbers_are_each_still_the_measured_ones`):
the **denominator** is every `CONSTRAINT <name>` in the non-comment text of `0003_revisions.sql` and
`0004_submissions.sql`; a constraint is **blamed** only when it appears in `.github/workflows/ci.yml`
as the third argument of a `refuse()` call, which is the object PostgreSQL must be shown to blame.
Applying that rule to `git show fe374c0:.github/workflows/ci.yml` and
`git show c153ec9:.github/workflows/ci.yml`:

```
declared (0003+0004): 46
fe374c0: blamed 27 of 46
c153ec9: blamed 41 of 46
```

The branch carrying the extra cases is now in `main`:

```bash
git merge-base --is-ancestor 77de2db origin/main && echo in-main   # -> in-main
```

And, independently of the workflow file, from the job's own **output** — every
`refused as designed by <object>: <case>` line the run printed, fetched with
`gh api repos/ISAAC-DOE/isaac-metadata-assistant/actions/jobs/97660962127/logs` and intersected with
the declared set:

```
total 'refused as designed' OUTPUT lines in the job: 67
distinct blamed objects: 58        (all migrations: 0002 + 0003 + 0004 + 0005, plus columns)
of those, declared by 0003/0004: 41
```

So the 41 is not read off a file that says CI *would* blame them; a real engine printed each one.

Engine actually under test, quoted from that job's step 6:

```
PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2) on x86_64-pc-linux-gnu, compiled by gcc 14.2.0, 64-bit
```

**The five that are still not individually blamed, named:**

| Constraint | Why |
|---|---|
| `isaac_submission_runs_unit_id_shape` | `isaac_submission_runs` also carries `record_id = unit_id` and `run_id IS NULL OR run_id = unit_id`, so no assignment of those columns violates exactly one of the three shape CHECKs; PostgreSQL reports whichever it checks first. The rows **are** proved refused, by a CHECK on that table, through a deliberately weaker assertion so it cannot be read as the stronger claim. Defence in depth, not a defect. |
| `isaac_submission_runs_record_id_shape` | same |
| `isaac_submission_runs_run_id_shape` | same |
| `isaac_revision_changes_revision_fk` | appears in the workflow for other reasons, with no refusal blamed on it |
| `isaac_submissions_experiment_fk` | same |

**What this still does not prove, and it is the whole reason your step is separate:** the CI container
is **empty**, with a **two-row synthetic stand-in** for `records`. *"Is this valid, idempotent SQL
whose constraints behave"* is answered. ***"Does it behave against the real data, the real roles and
the real grants"* is not, and only applying it resolves that.**

`CLAUDE.md` and the two packets still quote "41 declared / 27 executed". They now **understate** the
executed figure; correcting them in the repository is our housekeeping, not your action.

---

## 2. `0005_run_projection` — NOT APPROVED, NOT AN ASK

| | |
|---|---|
| `main` SHA this describes | `c153ec980726b3da3d2425be03385d3da2e39bda` |
| Migration version | `0005_run_projection` |
| Forward | `apps/api/isaac_api/migrations/0005_run_projection.sql` |
| **Forward SHA-256** | `86bf111cf030c15cb3d2349f428370476ad84262da9e5127a1e213c62da98304` |
| Rollback | `apps/api/isaac_api/migrations/0005_run_projection.rollback.sql` |
| **Rollback SHA-256** | `54a17432150525f75a6e94557a137029a3ce3fd41cea9debced361abda90e735` |
| **Owner approval** | **NOT APPROVED.** Krish has not reviewed the text. The packet's STATUS line says so and no document in the repository records an approval. Owner approval precedes an operator window; it never follows one. |
| **Hosted application** | **NOT APPLIED, ANYWHERE** — not hosted, not by anyone. |
| Packet | [`docs/migration-approval-packet-0005.md`](migration-approval-packet-0005.md) |

Recompute before doing anything with it, and refuse on any mismatch:

```bash
shasum -a 256 apps/api/isaac_api/migrations/0005_run_projection.sql \
              apps/api/isaac_api/migrations/0005_run_projection.rollback.sql
```

**Purpose, in two sentences.** `0002_runs`, which you applied on 2026-08-12, made `isaac_runs` a
shadow of the experiment document, and a reader cannot be built on it because zero rows means *either*
"this experiment has no runs" *or* "its runs were never projected" — both reachable, the second being
the normal state of every experiment saved before the shadow write shipped and of every save between a
merge and your `--apply`. This table records the projection claim explicitly, with the document version
it was made at, so that ambiguity is *detected* rather than assumed away.

### Schema change and data movement — there is none, proved mechanically

Parsing the committed file and discarding comment lines:

```
total lines: 202
non-comment lines: 18
comment lines above CREATE TABLE: 177
SQL verbs in non-comment text: ['CREATE']
'records' in non-comment text: False
```

Two statements, split on a line containing only `--;` (the runner never splits on `;`):
`CREATE TABLE IF NOT EXISTS isaac_run_projection (…)` and
`CREATE INDEX IF NOT EXISTS isaac_run_projection_projector_idx …`. **No `INSERT`, `UPDATE`, `DELETE`,
`COPY`, `MERGE`, `TRUNCATE`, `ALTER`, `DROP`, `GRANT` or `REVOKE` anywhere outside comments.** The
table is created empty and this migration moves no row. `ON DELETE` and `CASCADE` occur in the file
**only inside comments** — see the operational consequence at the end of this section.

The rollback is four lines: `BEGIN;` / `DROP TABLE IF EXISTS isaac_run_projection;` /
`DELETE FROM isaac_schema_migrations WHERE version = '0005_run_projection';` / `COMMIT;` — so "the
table is gone" and "the version is no longer recorded" cannot disagree.

### Prerequisites and ordering

`0005` declares a foreign key **into `isaac_experiments`**, which `0001` creates. It does **not**
reference `isaac_runs`, so it is **independent of `0002`**, and it must be rolled back before `0001`.

**`scripts/db_migrate.py` has `--plan` and `--apply` and no `--only <version>`.** With `0003` and
`0004` still pending, a single `--apply` would land **three** migrations. Precheck 1 of the packet
(`select version from isaac_schema_migrations order by version`) is what catches that, which is why it
comes first.

### PostgreSQL evidence — what CI executed, on `main`

All of the following ran in run `32800763199`, job `97660962127`, on `main` at `c153ec9`, against
**PostgreSQL 18.6** — every step `success`:

- forward application in order with `0005` last; `--plan` creating nothing; idempotence, including
  with the bookkeeping row deleted;
- `records` **byte-identical** across the migration (md5 over every row, before and after) — the job
  prints `records: byte-identical; added exactly the nine application-owned tables`, and again after
  the application ran: `records: byte-identical after the application ran; table set unchanged`;
- **10 refusal cases on `0005`'s own constraints** over **9 distinct objects** (the foreign key is
  blamed twice — once for an orphan claim, once for a parent delete), each naming the object
  PostgreSQL must blame, counted from the step's output: the foreign key, both non-negative CHECKs,
  the closed `projector` value set, four NOT NULLs (`experiment_generation`, `experiment_rev`,
  `run_count`, `projector`), the primary key, and **the parent-delete refusal**;
- the claim the application's own save writes, read back from the server and compared against the
  document — `0005: the application's own claim matches the document AND the rows` — plus a second
  save superseding in place rather than appending;
- the documented rollback restoring the pre-migration table set, and the **wrong-order** rollback
  failing safely without dropping anything.

**NEW since the sent package, and the reason this section exists.** The packet's §9A listed two items
as *declared in the workflow and not yet run*. **They have now run**, in the same job:

- A step *"Prove the Stage-2b gate queries detect what the packet says they detect"* commits a row
  with **`projector = 'backfill'`** — the first time that value has ever been committed to any engine;
  its acceptance was previously only inferred from reading the CHECK — then builds one experiment
  stale **by rev**, one stale **by generation at the same rev**, and one **never projected**, and runs
  **both of packet §8A's Stage-2b gate queries verbatim**. Job output, quoted:

  ```
  baseline: never_projected=0 stale=1
  accepted and committed as designed: projector = backfill
  after: never_projected=1 stale=3
  backfill|3
  0005 §8A: both gate queries executed against a real engine and named the right rows
  ```

  The queries are **unscoped by design** — that is the query you would run — so the step asserts
  **deltas** against a baseline taken immediately before, and asserts by id *which* experiments each
  query names. The baseline `stale=1` is residue from earlier steps in the same job, which is exactly
  why deltas rather than absolutes are asserted.
- Three NOT NULL cases (`experiment_rev`, `run_count`, `projector`) were added to the constraint step
  and are in the 10 above.

**Source used for these claims:** the CI job log, fetched read-only via
`gh api repos/ISAAC-DOE/isaac-metadata-assistant/actions/jobs/97660962127/logs`, plus the step-level
conclusions from `gh api .../actions/jobs/97660962127`. Not the workflow file, and not inference.

### Constraint coverage for `0005`

`0005` declares **four** explicitly named constraints — measured with
`grep -o "CONSTRAINT isaac_run_projection_[a-z_]*"`, which returns `…_experiment_fk`,
`…_rev_non_negative`, `…_count_non_negative`, `…_projector_known` and nothing else — plus an unnamed
`PRIMARY KEY` that PostgreSQL auto-names `isaac_run_projection_pkey`, and **five** `NOT NULL`s
(`grep -n "NOT NULL"` on the non-comment lines: `experiment_rev`, `experiment_generation`,
`run_count`, `projector`, `projected_utc`). The job's 10 refusal lines blame **9 distinct objects**
(the foreign key appears twice: once for an orphan claim, once for the parent-delete refusal): all
four named constraints, the primary key, and the **four** `NOT NULL`s a caller can violate by
omission. The fifth, `projected_utc`, carries `DEFAULT now()` and so cannot be violated by omission.
**Nothing on `0005` is declared and unexercised.**

`0005`'s constraints have **never** been inside the "41 of 46" counter in §1: that counter is derived
only from names declared by `0003_revisions` and `0004_submissions`. The two numbers are about
different objects and must not be added together.

### Negative controls

- `--plan` is proved to create no table, so the plan output cannot be mistaken for an application.
- Neither §8A query can pass by being vacuously empty: the **current** claim is asserted to appear in
  **neither** result set, by id.
- The gate step restores the baseline counts at its end, so it leaves nothing behind for a later step
  to inherit.
- A test reads the SQL off disk and asserts the identifier `records` appears in no statement.
- `test_0005_is_written_by_the_write_path_and_read_by_nothing` measures, over the module-level
  statement set, that exactly one statement in the application names the table and it is a write.
- A local test now makes the same API calls the CI step does, without PostgreSQL, because an earlier
  revision of this step died on a method-signature error **while the packet claimed it as proven**.
  That is recorded in the packet rather than quietly fixed.

Verified here: `pytest apps/api/tests/ -k "0005 or run_projection"` → **11 passed**;
`pytest apps/api/tests/test_submission_store.py -k "coverage or constraint_numbers"` → **4 passed**.

### Prechecks · apply · postchecks · rollback

The packet is authoritative and carries the exact commands: **§5 prechecks**, **§6 apply**,
**§7 postchecks**, **§8 rollback**, **§8A the Stage-2b gate queries**. Three points worth pulling
forward:

1. **Precheck 4 is not optional** — baseline `records`, `isaac_experiments` and `isaac_runs` counts.
   `0002`'s operator report omitted the first two and that omission is recorded in its packet as a
   gap. A count not taken before cannot be compared after.
2. **Postchecks check constraints by NAME, never by row count.** Some engines catalogue NOT NULL as
   `pg_constraint` rows and some do not, so a total would fail for a reason unrelated to this
   migration.
3. **Rollback criteria.** Rolling `0005` back deletes every completeness claim, so every experiment
   becomes *never projected* again. **The run rows are untouched and nothing scientific is lost.** In
   the build that ships this migration the cost is **zero**, because no reader consults the table —
   exactly one statement names it and it is a write. Dump first anyway if a later build has a reader.

### The one operational consequence, whether or not you apply it

**The foreign key has no `ON DELETE` clause**, so it takes the SQL default `NO ACTION`, which for this
non-deferrable constraint behaves as `RESTRICT`:

> **Once `0005` is applied, an experiment that carries a projection row cannot be deleted until that
> row is deleted first.**

This is not theoretical — **it already broke a CI cleanup step**, which failed with
`violates foreign key constraint "isaac_run_projection_experiment_fk"`. That is the constraint working
as designed; `ON DELETE CASCADE` is declined in the packet's §3 because it turns one statement into an
unbounded silent multi-row deletion, and because `NO ACTION` is the reversible choice. **Any
operational script that removes experiments needs one extra statement**, deleting the projection row
first.

---

## 3. A digest you may have been sent is stale

`0005`'s forward SQL was changed by an independent review (verdict *approve with corrections*; all four
corrections applied). **The forward digest therefore changed; the rollback digest did not.**

```bash
git show 6dce6fd:apps/api/isaac_api/migrations/0005_run_projection.sql | shasum -a 256
#   ebff660fc51559cd4ab6ce66a7b1ec943de86f2362d37adde153f0c74c8ae7ee   (superseded)
shasum -a 256 apps/api/isaac_api/migrations/0005_run_projection.sql
#   86bf111cf030c15cb3d2349f428370476ad84262da9e5127a1e213c62da98304   (current)
git show 6dce6fd:apps/api/isaac_api/migrations/0005_run_projection.rollback.sql | shasum -a 256
#   54a17432150525f75a6e94557a137029a3ce3fd41cea9debced361abda90e735   (unchanged)
```

If your copy of the 2026-08-18 package shows `ebff660f…`, it predates the corrections. **This changes
nothing you are being asked to do** — `0005` is not in the ask either way — and **the four `0003`/`0004`
digests are unchanged** and re-verified against the files at `c153ec9`:

```
f17db0b90d8696c7eac430e247c9b81d01439093663a755a4172487d54d3d46f  0003_revisions.sql
4af243393ededbaf7ceb6c32b3d97f75bb31ee8c6884d19bc8fd0b222e203645  0003_revisions.rollback.sql
0adabc629141f203ee3f27d3da5b4dabb5f5dad894de75e9639a157aea218f38  0004_submissions.sql
a1a7962422c8f1be8d6b51a44a5fd44646311d482143db0693c436760af66403  0004_submissions.rollback.sql
```

**Also worth one line, because it is about authorization rather than bytes.** `isaac_run_projection`
was added to the application's owned-table list and named in `CLAUDE.md` §15 **one commit apart**, and
one artifact then carried an incomplete correction of that lateness. Both are corrected in place, in
the repository, rather than reworded. The point for you is only this: **the authorization basis for
this table is committed text, not a conversation** — and it is recorded as having been written down
one commit late rather than presented as having been there all along.

---

## 4. External configuration ISAAC cannot create for itself — contracts only

**Not requests.** Each capability is built and tested against a **deterministic fake** and is inert
until an external endpoint or credential exists. **You deferred D1–D9 on 2026-08-12 and recommended
leaving AI integration as future work; nothing here reopens that.** No production endpoint,
credential, network path, outbound call or charge exists or is sought.

| # | What would be needed | The configuration contract, exactly |
|---|---|---|
| **E1** | A **trusted authentication boundary** for API/service traffic | The Service is a plain ClusterIP with no NetworkPolicy, so an in-cluster pod can reach the app directly and forge forwarded identity headers — header presence is **not** proof of authentication. The application side is complete and **fails closed**: `attribution.uploaded_by` is stamped only when a verifier asserts `trust_basis == verified_edge_assertion`, and **no verifier in this build mints that**, so nothing is stamped in any deployment. Arming it is a verifier plus a configuration value, not a product change. |
| **E2** | **Hosted MCP reachability and auth** | The deployment binding is selected by `ISAAC_MCP_DEPLOYMENT`. Exactly one binding in this build serves a transport — `local-loopback`, which refuses any non-loopback socket peer, refuses a request carrying a proxy header, and **refuses a credential rather than accepting one**. Two binding names are **reserved and deliberately unregistered**, and they are the contract: `oauth-resource-server` (ISAAC runs its own OAuth 2.1 authorization server, publishes RFC 9728 protected-resource metadata, and the edge passes OAuth traffic through — blocked on D1 and D2) and `edge-issued-bearer` (the edge accepts a pre-issued static bearer on the MCP path specifically — blocked on D2 and on edge configuration, which is not application work). Selecting a reserved name fails closed. **No hosted MCP route is exposed by default.** |
| **E3** | A **production model provider** | Selected by `ISAAC_ASSISTANT_PROVIDER`. The complete set of values this build understands is `{unconfigured, deterministic-fake}` — measured, not asserted. **There is no configuration value that would cause an outbound model call**, and an unrecognised value fails closed to `unconfigured`. Reaching a real provider requires code, not configuration. |
| **E4** | A **production transcription provider** | Same shape, `ISAAC_TRANSCRIPTION_PROVIDER` (and `ISAAC_CAPTURE_EXTRACTION_PROVIDER` for extraction), same two-value set, same fail-closed default. No audio leaves the process. |

---

## 5. Governance questions still open — silence has been treated as refusal, not assent

| Gate / question | Current state in the deployed application |
|---|---|
| **G2** — may the hosted app display **per-record** content from the 30 production-derived records? | **CLOSED BY DEFAULT.** Your guide requires the boundary be built into the read path from the start. No real-record adapter, list, detail, evidence view or export exists. Note one thing that has changed the shape of the question: the application now creates records of its own, which are **not** production-derived and carry no visibility question — so G2 can be answered for the seeded corpus alone. |
| **G3** — were the five aggregates that shipped in `v0.0.32` beyond your enumerated list within your intent? (`by_instance_path`, `distinct_structural_signatures`, the `total_link_count`/`dangling_link_count` pair, `vocabulary_term_count`) | **OPEN, and all five are WITHHELD** from the HTTP response, named in `dataset.withheld_pending_visibility_decision`. `vocabulary_term_count` is replaced by a boolean `vocabulary_cache_present`, which is reachability and *is* enumerated. Each response block is projected onto a frozen allowlist, so an unlisted key cannot be served. |
| **G6** — the personal-data / seed constraint, if still active | **OPEN.** No behaviour depends on an assumed answer. |
| **Q11, Q13, Q14, Q16** | **OPEN**, exactly as open as before. |
| **Q20(f)** — does the portal enforce JSON Schema `format`? | **OPEN.** `format` enforcement remains **shadow-only, aggregate, non-gating, outside the truth plane**; arming it in the official validator is **not** authorized. Measured, not asserted: `authorization.Q20_FORMAT_ENFORCEMENT_APPROVED = False`. |
| **Logout path** — whether ISAAC should surface `/outpost.goauthentik.io/sign_out` | **OPEN and Krish's**, not yours; you were not asked and did not decide. |
| **Stage 2b** — moving a reader onto `isaac_runs` | **NOT DONE and gated on a measurement, not a belief:** the backfill having run in the target environment with `UNREADABLE: 0`, `refused: 0`, `failed: 0`, **and** both §8A queries returning 0 there. The backfill script `scripts/db_backfill_runs.py` **has never been executed anywhere** and is deliberately absent from the container image. |

---

## 6. What this addendum does NOT ask for

- No kubeconfig, no port-forward, no Secret, no agent-initiated database connection.
- No `isaac-k8` change, no ingress change, no NetworkPolicy. **§4 is a statement of dependency; how a
  boundary is provided is yours to decide.**
- **No approval of `0005`**, and no application of it. It needs Krish's review first.
- No credential, no billing arrangement, no provider approval. **D1–D9 stay deferred.**
- No change to `records`, the verification truth plane, the official validator, export behaviour, or
  any infrastructure you own.
