# `isaac_runs` Stage 2 — the completeness contract

**Status: contract + Stage 2a implemented. No read has moved. Migration `0005_run_projection` is
NOT APPLIED ANYWHERE, and applying it is the operator's act, not an agent's.**

Written 2026-08-19. This document exists because the instruction that authorized the work said
*"write an explicit contract first"* and *"prefer an explicit completeness/cutover model over
`rows exist -> use them`"*. Both of those are answers to a defect that was **measured** in this
repository, not anticipated, and §1 states it before anything is proposed.

---

## 1. The blocker, measured

Stage 1 (`0002_runs`, applied to the hosted database by Dean on 2026-08-12) made `isaac_runs` a
**shadow** of the experiment document: after `PostgresOrdinaryStore.persist` returns, the rows for
that experiment equal `exp.sorted_runs()`. Nothing reads them. `Experiment.to_state()` still
carries `runs`, and that document is authoritative.

A read cutover — "read the runs from the table instead of from the document" — **cannot be written
against Stage 1 as it stands**, and the reason is not performance or risk appetite. It is that

> **`SELECT ... FROM isaac_runs WHERE experiment_id = %s` returning zero rows is ambiguous.**

It means *either* "this experiment has no runs" *or* "this experiment's runs have never been
projected". Both are reachable, and the second is the **normal** state of every experiment that
was persisted before Stage 1 shipped:

| How zero rows arises | Reachable? | Evidence |
|---|---|---|
| The experiment genuinely has no runs | yes | a record with no `POST /runs` ever |
| Persisted before the shadow write existed | yes | every row written before this slice |
| Persisted while `isaac_runs` was absent | yes, routinely | the image rolls out on merge and the operator applies migrations by hand afterwards; `experiment_repository._table_available` skips the run writes for exactly this window, and `/api/health` keeps reporting `durable: true`, correctly |
| The operator rolled `0002` back under a running pod | yes | `forget_run_table_presence()` exists because it happened in design review |

A reader that treats zero rows as "no runs" therefore **silently deletes every run of every
pre-existing record** the first time it is switched on, and reports success. That is the defect
this contract exists to make unwritable.

**`rows exist -> use them` does not fix it either.** "Some rows exist" cannot distinguish a
complete projection from a partial one, and it answers the wrong question for the case that
matters most: an experiment with genuinely zero runs would fall back to the document forever, so
the cutover would never be complete and no measurement could ever say it was.

---

## 2. The contract

**A projection is a claim about an experiment at a version, made by a named projector, and it is
recorded as a row.** Absence of the row is absence of the claim.

```
isaac_run_projection (
    experiment_id          -> PK, FK to isaac_experiments
    experiment_rev         -> the rev of the document the rows were projected FROM
    experiment_generation  -> the generation of that document
    run_count              -> how many rows were written (0 is a real answer)
    projector              -> 'write-path' | 'backfill'
    projected_utc          -> server-side stamp
)
```

### 2.1 The four states, and every read must distinguish all four

| State | Predicate | What a reader may do |
|---|---|---|
| **COMPLETE** | a projection row exists AND its `(experiment_rev, experiment_generation)` equal the experiment document's | use `isaac_runs` |
| **STALE** | a row exists and the pair differs | use the document; the rows are behind |
| **NEVER PROJECTED** | no row | use the document; the rows say nothing |
| **UNAVAILABLE** | `isaac_runs` or `isaac_run_projection` absent | use the document |

`run_count = 0` with a matching pair is **COMPLETE and means zero runs** — which is the whole
point, and the state Stage 1 could not express.

### 2.2 Five invariants

1. **The stamp is written in the same transaction as the rows it describes, or not at all.** There
   is no code path that writes one without the other. Two statements in one transaction cannot
   disagree about whether they committed.
2. **The stamp embeds the version it was made at, so it cannot go stale while looking fresh.** A
   later save that does not maintain the rows advances the document's `rev` or `generation` past
   the stamp, and the pair stops matching. Staleness is *detected*, never *assumed absent*.
   *~~The one case where a document changes without `rev` moving is `Experiment.save()`, the
   unversioned primitive — and it goes through the same `persist`, so the rows are re-diffed and
   the stamp re-written in that same transaction.~~ **The conclusion holds and the reasoning was
   wrong; an independent review measured it.** `Q_UPSERT_EXPERIMENT`'s predicate accepts only
   three cases: the generation differs, the incoming `rev` is strictly greater, or the state is
   byte-identical. A CHANGED document at the SAME `(rev, generation)` matches none of them, so it
   is REFUSED — `DurableWriteConflict` — and nothing is re-diffed and nothing is re-stamped. The
   invariant survives for a better reason than the one first given: such a write does not land at
   all, so it cannot leave a stamp describing rows it did not write.*
3. **The stamp is written only inside the accepted branch of the experiment compare-and-swap.** A
   writer that lost the CAS stamps nothing. This is the same `if accepted` gate the run rows are
   already inside, and it is load-bearing for the same reason: a loser that stamped would claim
   completeness for a document it failed to write.
4. **`run_count` is the size of the row set the transaction ESTABLISHED, and no CHECK
   enforces it.** ~~"MEASURED, not asserted. It is the length of the row set the transaction
   actually wrote, not the length of `sorted_runs()` as an intention."~~ **That was FALSE and
   an independent review measured it.** The value returned is `len(desired_ids)`, and
   `desired_ids` is derived from `exp.sorted_runs()` — so it is *identically*
   `len(exp.sorted_runs())`, and relocating the same expression into the callee is not a
   measurement. Worse, the test that cited the invariant asserted exactly the equality the
   invariant denied.

   **What is true, and is the property a reader actually needs:** after the upsert-and-delete
   pair, the table holds exactly the desired set for that experiment, so the count and the
   rows agree *by construction of those two statements* rather than by observation. It is a
   writer-maintained projection, which `0005_run_projection` says of it in its own comment,
   and the honest place to check it against reality is a real engine — CI compares the stored
   `run_count` against an actual `count(*)` of `isaac_runs`. A per-save `SELECT count(*)`
   would make it observed and would cost a statement on every write to confirm something the
   two preceding statements already determine; that trade was considered and declined.
5. **No read moves in Stage 2a.** The table is written and nothing consults it. Turning a reader
   on is Stage 2b, is a separate reviewed slice, and requires the backfill of §3 to have run.

### 2.3 What is deliberately NOT in the contract

- **No `session_id`.** Same permanent reason as `isaac_runs`: `ALTER` is a forbidden verb in
  `db_write._FORBIDDEN_KEYWORDS` and `CREATE TABLE IF NOT EXISTS` is a silent no-op, so a
  worked-example projection that ever reached this table would be permanently unidentifiable and
  permanently uncleanable. Tutorial isolation is inherited by construction: the stamp is written
  inside `persist`, after `refuse_if_not_persistable`.
- **No global "the projection is complete" flag.** Completeness is per experiment. A deployment-wide
  boolean would be a claim about rows nobody counted.
- **No trigger.** `db_migrate.split_statements` refuses a dollar-quoted body, so a trigger is not
  expressible in a committed migration here. The invariant is held by there being exactly one
  writer.
- **`ON DELETE` is unwritten**, so the default `NO ACTION` applies and deleting an experiment that
  still has a projection row is refused by the database — the same choice `0002_runs` made, for the
  same two reasons (no unbounded silent cascade; and it is the reversible direction, since going
  from `CASCADE` back would need an `ALTER`).

---

## 3. The backfill, and why it is a separate operator action

Every experiment persisted before Stage 1 is **NEVER PROJECTED**. `scripts/db_backfill_runs.py`
walks `isaac_experiments`, projects each experiment's runs through the *same* code path the write
uses, and stamps `projector: 'backfill'`.

***THAT LAST CLAUSE WAS FALSE WHEN IT WAS COMMITTED, and it is corrected in place rather than
quietly reworded, because the sentence reads identically before and after and only a measurement
tells them apart.*** An independent security review measured it on 2026-08-24: the *only* call site
of `Q_UPSERT_RUN_PROJECTION` — `PostgresOrdinaryStore._stamp_projection` — hard-coded
`PROJECTOR_WRITE_PATH`, and the backfill reaches it through the same `persist()` an ordinary save
uses, so every row the backfill wrote claimed the higher-trust producer it had not earned. The
string `'backfill'` existed in exactly one place in the Python tree, and it was the script's own
docstring asserting this behaviour.

**Why that mattered rather than being a cosmetic label.** §2's row shape declares `projector` a
closed two-value set, `0005_run_projection.sql` gives it a CHECK *and* an index that leads on it,
and `docs/migration-approval-packet-0005.md` §8A tells the operator to group the completeness query
by it. All three exist so the operator can tell "these rows were maintained incidentally by ordinary
saves" from "these rows were established by the pass I just ran" — which is the question the
Stage-2b gate below actually asks. A column whose second value can never appear cannot answer it,
and a table with no `backfill` rows would have read as evidence the backfill had never run.

**The fix is a keyword argument threaded through `persist` (`projector=`, defaulting to
`write-path`), not a second writer** — invariant 5 and `_stamp_projection`'s own docstring forbid a
second write path, because `isaac_run_projection` has no `session_id` column and can never gain one.
`apps/api/tests/test_db_backfill_runs.py` now asserts the parameter tuple each caller causes, so this
paragraph can no longer be the only thing that says which projector is stamped.

It is **idempotent** (a re-run re-projects and re-stamps to the same values), **additive** (it
issues no `DELETE` except the write path's own `Q_DELETE_ABSENT_RUNS`, which removes rows the
document no longer names), and it **never names `records`** — the statement policy refuses that by
identifier in any position.

**It has never been executed.** Like `scripts/db_recon.py` it is deliberately absent from the
container image (the Dockerfile COPY allowlist), so no application route can reach it, and running
it is an operator action against an environment an agent may not connect to.

**Stage 2b must not begin until the backfill has run in the target environment and reported
zero unprojected experiments.** That is the completeness gate, and it is a measurement
rather than a belief.

***AN EARLIER VERSION OF THIS PARAGRAPH SAID THE BACKFILL "reported `never_projected: 0`".
IT DOES NOT AND CANNOT.*** An independent review measured that the string appears in no
print statement anywhere in the repository — and the reason is structural rather than an
oversight: the backfill never reads `isaac_run_projection`, because a read would make it
that table's first reader, which is precisely the Stage-2b decision this gate exists to
*precede* (and would break invariant 5 above).

**So the gate has two halves, and both are needed.** The script reports whether it did all
the work: `experiments UNREADABLE`, `refused` and `failed` must every one be **0**, or some
experiment was not projected. The operator then runs the two SQL queries in
`docs/migration-approval-packet-0005.md` §8A — never-projected and stale — and both must
return 0. Neither half substitutes for the other: a clean script run over a table it could
not fully read proves nothing, and a clean query pair taken before the script finished
describes an incomplete pass.

---

## 4. What Stage 2b will and will not be allowed to claim

When a reader is eventually moved onto `isaac_runs`:

- It reads the projection state first and falls back to the document on any of STALE, NEVER
  PROJECTED or UNAVAILABLE. Fallback is **normal operation**, not an error path.
- `runs` **stays in the experiment document.** Removing it is a third decision and is not justified
  by any measurement in this repository. The brief that motivates it — "contract §8 D7" — is cited
  by several files here and **committed to none of them**, which is recorded rather than treated as
  authority.
- No surface may report the cutover as done on the strength of code alone. The honest statement is
  the measured per-experiment state distribution.

---

## 5. Authorization basis

`CLAUDE.md` §15's 2026-08-07 write lift covers Create Experiment persistence *"plus the minimum
supporting persistence architecture that feature requires"*, and its enumerated table list has been
corrected twice — once for `isaac_runs`, once for the five submission-lifecycle tables — each time
because a slice added a table to `db_write.OWNED_TABLES` that no committed sentence named.

**`isaac_run_projection` is named in `CLAUDE.md` §15**, and it is named here, so the basis is
committed rather than conversational.

***AN EARLIER VERSION OF THIS SENTENCE SAID "in the same change that creates it". THAT WAS
FALSE BY ONE COMMIT, and an independent review measured it:*** the table shipped in `6dce6fd`,
which does not touch `CLAUDE.md`; §15 was updated in `8f7c650`. Recorded rather than softened,
because the claim was published and the point of the enumeration is that it is checkable. One
commit late is a smaller gap than the two previous times and is still not what was claimed. Listing a table in `OWNED_TABLES`
**grants nothing on its own** — it permits a statement naming it to pass the policy; what may be
written is decided by the module-level `Q_*` constants and the tests that enumerate them.

`0002_runs` is **not edited**, and no Stage-2 behaviour is hidden inside `0003_revisions` or
`0004_submissions`. The three were separately reviewed and the first is applied to the hosted
database; touching any of them would be the change this project's rules most explicitly forbid.

---

## 6. The operator packet

`docs/migration-approval-packet-0005.md`. It carries the SHA-256 of the exact bytes, the forward and
rollback statements, the prechecks and postchecks, and the same hard stop every packet carries:
**the owner reviews the migration text and the operator applies it. No agent applies a migration to
the hosted database, and no agent asks for a kubeconfig, a port-forward, or a Secret.**

---

# Stage 2b — the authoritative-read contract

**Written 2026-08-27, at `main` = `7668bf8`, BEFORE the reader was implemented.** §§1–6 above
are Stage 1 + Stage 2a and are unchanged. This section is the thing §4 said would need its own
reviewed slice.

## 7.1 What moves, precisely — and it is one function

> **TWO CORRECTIONS, 2026-08-27, AND THE SECOND ONE IS THIS PARAGRAPH FAILING ITS OWN TEST.**
> Both were found by an independent truthfulness audit, not by the author. Every line number
> below is now re-derived at commit **`8994525`** — the commit that added this section — because
> the numbers this paragraph originally carried came from `main` (`7668bf8`), not from its own
> HEAD, and that is mechanically checkable rather than inferred: `refuse_if_not_persistable`
> `:1307`, `persist` `:1336`, `hydrate` `:1661`, `stored_experiments` `:1773` and the Protocol's
> `create` `:1878` are EXACTLY the five line numbers `git show
> 7668bf8:apps/api/isaac_api/experiment_repository.py | grep -n "^    def "` prints, and NONE of
> them is HEAD's. The single exception — `experiment_repository.py:2182`, the delegating wrapper —
> IS HEAD's (`main`'s is `:1934`), so the paragraph was part-updated and part-copied, which is the
> worst of the two. The vantage point is stated so a later reader can re-derive rather than trust:
> `git show 8994525:apps/api/isaac_api/experiment_repository.py | grep -n "^    def "`.

~~"The application does **not** read experiments from PostgreSQL on the request path."~~ —
**FALSE, and it is the sentence the whole of §7 was built on top of.** Corrected in place rather
than reworded, because a reader who saw the old sentence needs to see that it moved.

**The application reads experiments from PostgreSQL on exactly one request path.**
`GET /api/experiments` — My Experiments, the product's primary screen — calls
`ws.list_experiments_with_hydration(scope)` (`routes.py:2180`), which calls
`_hydrate_ordinary_scope()` (`workspace.py:4628`), which calls
`PostgresOrdinaryStore.hydrate()` (`workspace.py:4719`), which reads `Q_ALL_EXPERIMENTS`. That is
not an accident of layering: `workspace.py:4645` carries a heading saying so outright — *"WHY ON
EVERY ORDINARY READ rather than once at boot. … an `emptyDir` is per-pod, so a second replica
starts empty while the first is serving, and a boot-time hydration would leave that replica
permanently blind to everything created before it started. Hydrating on read is one bounded
`SELECT` on a table this application owns, and it writes only what is genuinely absent."*

**`hydrate()` RESTORES; IT DOES NOT REFRESH** — its own docstring states that as a heading, and the
skip is on `experiment.json`, not on the row, so a record whose state file is already present is
left exactly as it is. The read is therefore bounded and almost always writes nothing. But it is
**per list request, not per restart**, and every cost estimate in this section has to be sized
against that.

Measured: `PostgresOrdinaryStore` exposes ~~exactly four methods~~ — **FIVE**, at `8994525` —
`refuse_if_not_persistable` (`:1461`), `persist` (`:1490`), `discard` (`:1815`), `hydrate`
(`:1909`) and `stored_experiments` (`:2021`); `create` belongs to the `ExperimentRepository`
Protocol (`:2126`), not to the store, and an earlier draft of this paragraph listed it here —
corrected before merge. **The second correction is worse than the first, because it is the same
defect this paragraph names.** `discard` was added by `d93b896`, a commit that was ALREADY an
ancestor of this document when the "exactly four" sentence was written; the enumeration was
copied from `main` rather than measured at HEAD, in the sentence that boasts about enumerations
having been published wrong four times. It is now five times, and this is the fifth.

**`discard` matters to Stage 2b specifically, which is why omitting it was not a cosmetic slip.**
It is the ONE method that **deletes** `isaac_run_projection` and `isaac_runs` rows — three
statements in foreign-key dependency order, in one transaction, guarded by the same
`_table_available` probes the write path uses. A Stage-2b reader must account for it: after a
discard the experiment has no projection row and no run rows, which is NEVER PROJECTED by §2.1's
predicate — and that is correct, because the experiment's durable row is gone too. Its one
production caller is `ws.discard_experiment` (`workspace.py:5366`), reached from
`routes.py:3073`.

Of the five, `stored_experiments` is called only by `scripts/db_backfill_runs.py` and by tests,
and `hydrate` has exactly two production callers: `workspace.py:4719` and the delegating wrapper
at `experiment_repository.py:2182`. The database is ~~a **write-through mirror**~~ **a
write-through mirror that is also read back on every ordinary list**; the filesystem workspace is
still the working store, and that half is unchanged.

The one place a stored document becomes a live record is
`PostgresOrdinaryStore.hydrate()` (`experiment_repository.py:1909`). It reads `Q_ALL_EXPERIMENTS`,
and for each row whose workspace directory is missing it writes the row's `state` JSON to
`<root>/<id>/experiment.json`. **The run list is the `runs` key inside that document**
(`ws.Experiment.to_state()` → `"runs": [r.to_state() for r in self.sorted_runs()]`).

> **Stage 2b is therefore exactly this: when hydrating an experiment whose projection is
> COMPLETE, build the restored document's `runs` key from `isaac_runs` rows instead of from
> `state["runs"]`. Nothing else moves.**

That is also where a silent-data-loss bug would live, which is why it is stated this narrowly:
get it wrong and a record is restored with no runs and the pass reports success.

## 7.2 The eighteen questions, answered

| # | Question | Answer |
|---|---|---|
| 1 | What proves the projection is complete? | A row in `isaac_run_projection` whose `(experiment_rev, experiment_generation)` equal the document's. Nothing else. Not row presence, not `run_count`. |
| 2 | Which version/completeness marker governs? | The **pair**, never `rev` alone — `generation` is what makes a delete-and-recreate distinguishable at `rev 0`. |
| 3 | How is staleness detected? | The pair stops matching. Detected, never assumed absent (§2.2 invariant 2). |
| 4 | How are legacy Experiments handled? | They are NEVER PROJECTED, so they read from the document, unchanged, forever — until a backfill or an ordinary save stamps them. **This is the normal path, not an error path.** |
| 5 | How does backfill happen? | `scripts/db_backfill_runs.py --apply`, an operator action, unchanged by this slice. It is **not** a precondition for shipping the reader (§7.3). |
| 6 | What does partial backfill mean? | Nothing special. Each experiment is independently COMPLETE or not. There is no global state to be half-way through. |
| 7 | How is mismatch handled? | See §7.4. Fall back to the document, **and disclose**. Never silently pick a side. |
| 8 | When may reads switch authority? | **Per experiment, the moment its projection is COMPLETE.** There is no global cutover instant. |
| 9 | Is fallback allowed? | Yes — on STALE, NEVER PROJECTED, UNAVAILABLE, and on mismatch. Fallback is normal operation. |
| 10 | When is fallback forbidden? | Never. There is no state in which the document may not be read. Removing that option is a **third** decision (§4) and is out of scope. |
| 11 | How does CAS operate during transition? | **Unchanged.** The compare-and-swap is on `isaac_experiments.state`, which still carries `runs`. Stage 2b changes where the run list is *read from*, never what is *written*. `Q_UPSERT_EXPERIMENT` is not touched. |
| 12 | How do revision snapshots behave? | Unchanged. `submission_store` snapshots the `ws.Experiment` in memory. If the reader is correct, that object is identical either way — which is the parity property §7.5 tests. |
| 13 | How does Submit choose Run state? | It does not choose. It uses the hydrated `Experiment`, exactly as today. |
| 14 | How does Run removal behave? | Unchanged. `POST .../runs/{id}/remove` mutates the document; `persist` re-diffs the rows and re-stamps in the same transaction, so the projection stays COMPLETE at the new pair. |
| 15 | How does restart behave? | ~~"A restart is precisely when `hydrate()` runs."~~ — **CORRECTED 2026-08-27, same root as §7.1's opening sentence.** `hydrate()` runs on **every ordinary-scope `GET /api/experiments`**, restart or not; a restart is merely the case in which it has the most to do, because the `emptyDir` workspace is empty and every row's directory is missing. The answer this row exists to give is unchanged and does not depend on the wrong half: authority is recomputed from the stamp on each pass, never remembered — there is no cached cutover bit to survive or fail to survive. |
| 16 | How do concurrent writes during transition behave? | Unchanged. A writer that loses the CAS stamps nothing (§2.2 invariant 3), so a losing writer cannot leave a projection claiming completeness for a document it failed to write. |
| 17 | Document and rows **intentionally** disagree? | **This state does not exist and must not be invented.** One transaction maintains both; there is no writer that updates one deliberately without the other. Any disagreement is unexpected — see the next row. |
| 18 | Document and rows **unexpectedly** disagree? | §7.4. |

## 7.3 Why the reader may ship before the backfill has run — and what that does NOT mean

§3 says *"Stage 2b must not begin until the backfill has run in the target environment."* That
sentence governs **when the cutover is complete**, and it is unchanged. It does not govern when
the reader may be written, and conflating the two would make the work unstartable: the backfill
is an operator action in an environment an agent may not connect to.

The reader is **safe by construction on day one**, and the reason is mechanical rather than
optimistic — but ~~"every experiment that predates the projection is NEVER PROJECTED"~~ names the
**wrong one of the four states for the situation that actually obtains today**, and §2.1 keeps
them as separate rows precisely so an operator can tell them apart. Corrected 2026-08-27:

- **Until `0005` is applied — which is the state of every environment, per this document's own
  status line — `isaac_run_projection` does not exist, so every experiment is `UNAVAILABLE`,**
  not NEVER PROJECTED.
- **Between `0005` being applied and the backfill having run, an experiment that has not been
  saved since is `NEVER PROJECTED`.**

Both read the document, which is why the conclusion is untouched: before the backfill, the reader
is a no-op for exactly the records the backfill exists to cover. Only the stated reason moves —
and it moves in the one direction that matters, because the two states are separately reported in
§7.6's distribution and an operator checking the health block against this prediction would find
it disagreeing.

Two consequences, both deliberate:

- **The cutover is per experiment and automatic.** An ordinary save stamps a COMPLETE
  projection in the same transaction as the rows, so a record saved after `0005` is applied
  reads from `isaac_runs` immediately — correctly, because its rows and its document were
  written by the same transaction. The backfill is needed only for records that have not been
  saved since.
- **No surface may report the cutover as done on the strength of code alone** (§4, unchanged).
  The honest statement remains the measured per-experiment state distribution, which is why
  §7.6 requires it to be observable.

**A kill switch is REQUIRED anyway** — prescriptive, like the rest of this section, which was
written before the reader existed. `ISAAC_RUN_ROWS_AUTHORITATIVE=0` must force every experiment
to NEVER-PROJECTED behaviour without a redeploy. It is defence for an operator, not a gate the
design depends on; the default is on, because a design that needed a flag to be safe would not
be safe.

## 7.4 Mismatch — the one genuinely new rule

A COMPLETE projection whose rows do not reproduce the document's `runs` is a **bug**, not a
state. Per §2.2 invariant 4 the two agree *by construction of the upsert-and-delete pair*, so a
disagreement means a writer, a migration, or an out-of-band statement broke that construction.

The rule, and it is fail-closed in the direction that cannot lose a scientist's work:

1. **Compare, always.** Even at COMPLETE, the reader compares the rows against
   `state["runs"]` — **over the FULL RUN DOCUMENTS, not the id set.**

   ~~"the reader compares the row set against `state["runs"]` by run id"~~ — **CORRECTED
   2026-08-27, and the implementing slice found it rather than this document.** Comparing ids
   alone contradicts rule 2 one line below: with a matching id set but divergent row CONTENT
   the rows would win and nothing would be disclosed. That is a worse failure than the one
   rule 1 was written to catch, because it substitutes different *science* rather than a
   different *count*. The implementer measured it rather than arguing it — an out-of-band row
   mutation was adopted silently — and pinned it with a test that said so before recommending
   the change. ~~"This costs one set comparison over data already in hand."~~ —
   **THE RULE STANDS; ITS PRICE TAG WAS WRONG, and it is corrected rather than deleted.** The
   comparison is now a per-run DOCUMENT comparison over data already in hand — corrected a
   second time, in the same direction as the first: it is `O(total runs across the experiments
   this pass actually restored)`, with a dict equality per run rather than one string-set
   compare. Still cheap, and still bounded by records genuinely missing locally, which on a warm
   pod is zero. The per-experiment cost
   is what it says. What was wrong is the FREQUENCY it was implicitly sized against: §7.1's
   opening sentence had this section believing `hydrate()` ran once per restart, so "one set
   comparison" read as one comparison per experiment per pod lifetime. It is **once per
   experiment per `GET /api/experiments`** — the product's primary screen, on every load. The
   honest sizing is therefore *O(runs) per experiment per list request*, and a Stage-2b
   implementation must measure it on a realistic workspace rather than assume it is free. It is
   still cheap enough to be the right rule: the alternative is a reader that cannot tell a
   healthy fallback from a corrupted projection, and this repository has already published one
   surface that could not (§7.5's negative-control note).
2. **On disagreement, use the DOCUMENT.** It is the side the CAS protects, the side Submit and
   export have always read, and the side a scientist's last write landed in. Preferring the rows
   here would let a stale or corrupted projection delete runs.
3. **Disclose it.** The mismatch is counted and surfaced (§7.6). A mismatch that only fell back
   would be indistinguishable from a healthy fallback, and the whole point of the stamp is that
   the two are distinguishable.
4. **Never repair silently.** The reader does not rewrite rows to match, and does not re-stamp.
   Repair is an ordinary save's job, or an operator's.

   **AND A NON-ZERO `mismatch` IS PERSISTENT, WHICH THIS RULE DID NOT SAY.** A row corrupted out
   of band stays corrupted, so every pass that reclassifies that experiment counts it again — the
   figure does not decay, and it does not distinguish *one mismatch once* from *one mismatch on
   every pass*. The distribution is overwritten per pass and deliberately carries no id, so the
   count is the only signal. **What an operator does with a non-zero `mismatch`:** nothing
   urgent — the reader is already using the document, so no scientist is seeing wrong runs — and
   the repair is an ordinary save of that experiment, which re-diffs the rows and re-stamps.
   Counts-only stays; naming the experiment would put a record id in a health endpoint.

**`run_count` is not used to detect this**, and that is deliberate: §2.2 invariant 4 records that
it is `len(desired_ids)` — a writer's intention, not an observation — so treating a matching
count as evidence of matching rows would be exactly the overclaim that invariant corrects.

## 7.5 What the proof suite must establish

Three phases, and a negative control that proves the suite can fail.

**Before completeness** — legacy source stays safe; row absence cannot erase runs. A
NEVER-PROJECTED experiment with three runs in its document hydrates with three runs while
`isaac_runs` holds none.

**During transition** — mismatches are visible and detected; writes cannot silently fork
authority. A COMPLETE projection with a row deleted out of band hydrates from the document, is
counted as a mismatch, and loses nothing.

**After completeness** — reads come from the rows; restart preserves authority (recomputed, not
remembered); CAS is unchanged.

**Negative control** — revert the reader (or delete a projection row) and prove the suite turns
RED. A parity suite that passes with the feature off is testing nothing, and this repository has
a written instance of exactly that: `test_detail_route_composes_each_run_once.py::_disable_threading`
silently failed to revert each newly-added seam until it was extended, **twice**.

**Real PostgreSQL for the truth-path cases.** The opt-in guard is
`ISAAC_RUN_REAL_ENGINE_PARITY=1` plus a loopback-only `PGHOST` check that **refuses `PGHOSTADDR`
outright** (a measured 2026-08-24 finding: `PGHOST=localhost` with `PGHOSTADDR=<hosted>` defeated
the loopback check). `ISAAC_REQUIRE_REAL_ENGINE_PARITY=1` turns an unreachable engine into a
failure rather than a skip. Both must be honoured; neither may be weakened.

**Ordering is a real trap.** `sorted_runs()` orders by `(ordinal, created_utc, id)` where
`created_utc` is the **document** field. `isaac_runs_experiment_order_idx` is
`(experiment_id, ordinal, run_id)` and its `created_utc` column is the **row** stamp. A reader
that orders by the index reproduces a different sequence. The reproducing sort is
`ORDER BY ordinal, state ->> 'created_utc', run_id` — 0002's own comment says so at
`0002_runs.sql:223-232`.

## 7.6 What must be observable, and what may never be claimed

`/api/health`'s **`experiment_storage.run_projection`** block gains a per-experiment **state
distribution**.

~~"`/api/health`'s `database` block gains…"~~ — **CORRECTED 2026-08-27; the implementing slice
was right and this section was wrong.** `routes.py:1553-1560` says the `database` block is about
the read-only diagnostic over the **production-derived** sample, and that conflating it with this
application's own experiments "would be the kind of error this file has made before".
`experiment_storage` is the block about this application's own experiments, which is exactly what
this distribution describes — and it is what this section's own justification below argues for.
The deviation is adopted, not merely tolerated.

**`last_pass` is `null` until a pass has CLASSIFIED something.** A warm pass with nothing to
restore does not overwrite it, or the informative post-restart measurement would be erased by the
next list request. And when the kill switch is off the block reports `authoritative: false` with a
null `last_pass` rather than labelling every experiment NEVER PROJECTED — that would report a
state the reader never measured.

It carries counts of
COMPLETE, STALE, NEVER PROJECTED, UNAVAILABLE, and MISMATCH from the most recent hydration pass.
Counts only: no ids, no titles, no record content. It is an aggregate about *this application's
own* tables, not about the production-derived `records` table, so gates **G2**/**G3** are
untouched.

Never claimable: that the cutover is complete, on the strength of code, or of a green suite, or
of `0005` having been applied. The only honest statement is the measured distribution, and the
prediction an operator would check that distribution against is **two predictions, not one**
(corrected 2026-08-27 — this sentence named the wrong state, and it is the one sentence here an
operator would actually test):

**THE CASE AN OPERATOR HITS FIRST IS NOT IN THIS TABLE, and omitting it would send them to
debug a healthy pod.** `hydrate()` RESTORES rather than refreshes: it skips any record whose
`experiment.json` is already on disk. So a **warm pod classifies nothing**, and `last_pass` is
`null` — not "all unavailable", not "all never projected". The distributions below appear only
after a restart, or after a working copy goes missing. **`null` on a healthy warm pod is the
expected reading, not a defect.**

| When (after a pass that classified something) | Expected distribution | Why |
|---|---|---|
| `0005` **not applied** — the state of every environment today, per this document's status line | **every experiment `UNAVAILABLE`** | §2.1: the predicate for UNAVAILABLE is `isaac_runs` **or** `isaac_run_projection` absent |
| `0005` applied, backfill **not run** | **every experiment `NEVER PROJECTED`**, except any saved since `0005` was applied, which are `COMPLETE` | an ordinary save stamps a COMPLETE projection in the same transaction as the rows |

~~"the expected distribution in the hosted deployment is **every experiment NEVER PROJECTED**"~~
was right about the second row and wrong about the first, which is the row that describes today.
Either way the reading is the same and is the point: **that is the reader working correctly, not
the reader being off.**

## 7.7 Authorization basis

`CLAUDE.md` §15's 2026-08-07 lift, its `isaac_run_projection` enumeration, and §4 of this
contract, which reserved Stage 2b as *"a separate reviewed slice"* and pre-specified the
four-state fallback this section implements. **Stage 2b adds no table, no column and no
migration** — it reads two tables that already exist, and **each of them has its own migration
header saying the build that shipped it would not read it** (corrected 2026-08-27: ~~"that
`0005`'s own header says the build that shipped it would not read"~~ attributed both tables to
one migration). `0005_run_projection.sql` says it of **`isaac_run_projection`** — *"No read path
in this application consults this table in the build that ships it — the write path stamps it and
nothing else."* `isaac_runs` is **`0002`'s**, and `0002_runs.sql` says it there — *"No application
code writes or reads `isaac_runs`."* Note that `0002`'s sentence has since been half-overtaken by
the shadow-write slice, which is exactly why it must be attributed to `0002` and read at its own
vantage point rather than folded into `0005`'s.

It writes nothing. `db_write.OWNED_TABLES` is unchanged, and no new enumeration is required.
~~"which is the first time in this programme that sentence has been true without a correction
attached to it"~~ — **WITHDRAWN 2026-08-27, and withdrawn rather than reworded because the
self-congratulation is the part that was wrong.** It was false when it was written and it is
false now: §7.1 of this same section carried an unchecked enumeration (*"exactly four methods"*,
measured five), and this paragraph carried a second misattribution. The sentence claimed a clean
record in the paragraph immediately after two defects of exactly the kind it was claiming to have
avoided. **The durable lesson is the one §15 of `CLAUDE.md` has now recorded five times: "no
enumeration is required here" is itself a checkable claim, and this one was published unchecked.**
