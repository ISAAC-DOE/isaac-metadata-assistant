# Operator addendum — the `isaac_runs` reader now exists

**For:** Dean (infrastructure / database operator). **From:** Krish Verma. **Date:** 2026-08-27.
**Prepared by an agent; not sent by one. Krish forwards this or does not.**

**This addendum introduces NO new migration and asks for no new approval of migration bytes.**
`0005_run_projection` is unchanged, its packet
([`docs/migration-approval-packet-0005.md`](migration-approval-packet-0005.md)) is unchanged, and
its SHA-256 digests are unchanged. What changed is that the **reader** those artifacts were
written for now exists, which changes what applying `0005` would *do* — so the sequence is
restated here rather than left to be inferred from a packet written before the reader was built.

**Nothing here is urgent and nothing is blocked on it.** The application is correct in the current
state and stays correct if this is never actioned. §4 says precisely why.

---

## 1. What is new since the consolidated handoff

`isaac_runs` has had a **shadow write** since `0002` (applied 2026-08-12) and a **completeness
stamp** (`isaac_run_projection`, migration `0005`) specified since 2026-08-19. Until now **nothing
read either table** — that was Stage 2a, and it was deliberate.

A reader now exists. When an experiment's projection is **COMPLETE**, its runs are restored from
`isaac_runs` rather than from the copy embedded in the experiment document.

Contract: [`docs/isaac-runs-stage-2-contract.md`](isaac-runs-stage-2-contract.md) §7, written
before the reader and corrected twice by the implementation — both corrections are recorded in
place, including one where the contract was wrong and the implementer was right.

## 2. Why this does not require you to do anything

The reader distinguishes four states and **falls back to the document on three of them**:

| State | Predicate | Reader does |
|---|---|---|
| COMPLETE | a projection row exists AND its `(experiment_rev, experiment_generation)` equal the document's | reads `isaac_runs` |
| STALE | a row exists and the pair differs | reads the document |
| NEVER PROJECTED | no row | reads the document |
| UNAVAILABLE | either table absent | reads the document |

**`0005` is not applied to the hosted database.** So `isaac_run_projection` does not exist there,
every experiment resolves **UNAVAILABLE**, and every read comes from the document — byte for byte
what happens today. The reader is a no-op in the hosted environment until you choose otherwise.

That is not luck. It is the reason the reader could be built and merged without waiting for you:
the states that mean "I cannot prove this is complete" and the state that means "the tables are
not there" both read the document, so the code is safe by construction rather than by gating.

**A kill switch exists anyway**, for you rather than for the design: `ISAAC_RUN_ROWS_AUTHORITATIVE=0`
forces document reads for every experiment, without a redeploy.

## 3. What you would see if you applied `0005`

`GET /api/health` → `experiment_storage.run_projection` reports a per-experiment state
distribution — **counts only**; no record id, title, or content, and a test serialises the block
and searches it for exactly those to keep it that way.

**READ THIS ROW FIRST, because it is the one you will actually see.** The restore skips any
record whose working copy is already on disk, so a **warm pod classifies nothing** and
`last_pass` reads `null`. That is the healthy steady state, **not** a defect and not an empty
result — the distributions below appear only after a pod restart, or after a working copy goes
missing.

| When (after a pass that classified something) | Expected distribution |
|---|---|
| now (`0005` unapplied) | every experiment **UNAVAILABLE** |
| `0005` applied, backfill not run | every pre-existing experiment **NEVER PROJECTED**; anything saved after `0005` becomes **COMPLETE** on its next save |
| `0005` applied, backfill run and clean | every experiment **COMPLETE** |

**All three are the reader working correctly.** UNAVAILABLE and NEVER PROJECTED are not errors and
should not be read as ones.

## 4. The sequence, if and when you want it — three separate decisions, in order

1. **Apply `0005_run_projection`.** Packet unchanged; owner approval for its exact bytes is still
   required and is Krish's, not an agent's. Effect: the stamp table exists; ordinary saves begin
   stamping. Reads still come from the document for every pre-existing record.
2. **Run `python scripts/db_backfill_runs.py --apply`.** It has **never been executed anywhere**.
   It is idempotent, additive, and deliberately absent from the container image. It must report
   `experiments UNREADABLE: 0`, `refused: 0` and `failed: 0`.
3. **Confirm completeness with the two queries in
   [`docs/migration-approval-packet-0005.md`](migration-approval-packet-0005.md) §8A** — never-projected
   and stale — both returning **0**.

**Neither half of the gate substitutes for the other**: a clean script run over a table it could
not fully read proves nothing, and a clean query pair taken before the script finished describes an
incomplete pass. And note the script cannot report the gate figure itself — it deliberately never
reads `isaac_run_projection`, because doing so would make it that table's first reader, which is
the decision the gate exists to precede.

## 5. What the reader will never do

- **Never treat zero rows as "no runs".** That ambiguity is the entire reason the stamp exists;
  a reader that resolved it by guessing would silently delete every run of every pre-existing
  record and report success.
- **Never trust `run_count`.** It is the writer's intention (`len(desired_ids)`), not an
  observation, and the contract says so. The reader does not select it.
- **Never repair silently.** On a COMPLETE projection whose rows do not reproduce the document,
  it uses the **document**, counts a MISMATCH, and surfaces it. It rewrites no row and re-stamps
  nothing.
- **Never claim the cutover is done** on the strength of code, a green suite, or `0005` having
  been applied. The only honest statement is the measured distribution in §3.

## 6. What has NOT changed

`0001`–`0004` are untouched. No migration byte moved. `db_write.OWNED_TABLES` is unchanged — Stage
2b adds no table, no column and no migration; it reads two tables that already exist. The
production-derived `records` table is not named by any statement the reader issues, and the write
path's statement policy still refuses it by identifier in any position.

**No agent connected to any database, and none requested a kubeconfig, a port-forward, or a
Secret.** The reader was developed against an in-process fake and verified in CI against a
`postgres:18` service container.

## 7. Two things worth knowing that are not asks

- **A bare `pytest` used to write to whatever `PGHOST` named.** Measured across the suite: 1,392
  connections and 14,273 mutating statements, using exactly the five variables
  `docs/postgres-test-db-guide.md` tells an operator to export for the port-forward. CI was never
  exposed (it has an explicit guard); developer machines were, and a 2026-08-24 fix that was
  believed to have closed it had bounded it to one file out of ~30. It is now zero, by a
  session-scoped fixture that clears every `PG`-prefixed variable unless a suite explicitly opts
  in. **This is not a report that anything happened to your database** — it is a report that a
  guarantee people relied on did not exist.
- **The five submission-lifecycle tables are now refused `DELETE` and `UPDATE` by the
  application's own statement policy**, not only by a test that enumerates statements. It is still
  **not** a database-level guarantee — no trigger, no `REVOKE` — and must not be described as one:
  a psql session or any non-application client is unaffected. What it closes is the reachable case.

---

**Nothing in this document asks you to act today.** If `0005` is never applied, the application
behaves exactly as it does now, indefinitely, and the reader stays inert.
