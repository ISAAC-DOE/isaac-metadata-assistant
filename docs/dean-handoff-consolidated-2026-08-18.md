# Consolidated operator handoff — 2026-08-18

**For:** Dean (SLAC infrastructure / database operator), via Krish.
**From:** the ISAAC Metadata Assistant repository. **Not sent by an agent** — this is a ready-to-send
package for Krish to review and forward.

**Read this first.** Nothing here is a request to change how ISAAC is deployed. Every item is either
(a) a migration whose text is already reviewed and owner-approved and needs an operator to apply it,
or (b) an external configuration ISAAC cannot create for itself. **No agent has connected to the
hosted database, and none may** (`docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52`).

Repository state this package describes: `main` at the SHA printed by `git rev-parse origin/main` at
the time of sending. Re-print it before forwarding rather than trusting a copied value.

---

## 1. Migrations awaiting an operator — TWO approved, and a THIRD that is NOT

**Read the split before the table.** `0003` and `0004` are approved by the project owner and waiting
only on an operator window. **`0005_run_projection` is NOT approved and is NOT part of this ask** —
it is listed in §1A so it is not a surprise later, and it needs Krish's approval before it needs
yours. Do not apply it.

`0003_revisions` and `0004_submissions` are **ONE decision** — `0004` declares a foreign key into a
table `0003` creates, so 0003-without-0004 leaves the application unable to record a submission and
0004-without-0003 cannot be applied at all. `db_migrate` orders them lexicographically, so a single
`--apply` does both in the right order.

| | `0003_revisions` | `0004_submissions` |
|---|---|---|
| **Owner approval** | **APPROVED by Krish, 2026-08-17** | **APPROVED by Krish, 2026-08-17** |
| **Hosted application** | **NOT APPLIED** | **NOT APPLIED** |
| **Forward SHA-256** | `f17db0b90d8696c7eac430e247c9b81d01439093663a755a4172487d54d3d46f` | `0adabc629141f203ee3f27d3da5b4dabb5f5dad894de75e9639a157aea218f38` |
| **Rollback SHA-256** | `4af243393ededbaf7ceb6c32b3d97f75bb31ee8c6884d19bc8fd0b222e203645` | `a1a7962422c8f1be8d6b51a44a5fd44646311d482143db0693c436760af66403` |
| **Tables created** | `isaac_experiment_revisions`, `isaac_run_revisions`, `isaac_revision_changes` | `isaac_submissions`, `isaac_submission_runs` |
| **Packet** | [`docs/migration-approval-packet-0003.md`](migration-approval-packet-0003.md) | [`docs/migration-approval-packet-0004.md`](migration-approval-packet-0004.md) |

**Recompute both digests before applying, and refuse if either differs:**

```bash
shasum -a 256 apps/api/isaac_api/migrations/0003_revisions.sql \
              apps/api/isaac_api/migrations/0003_revisions.rollback.sql \
              apps/api/isaac_api/migrations/0004_submissions.sql \
              apps/api/isaac_api/migrations/0004_submissions.rollback.sql
```

That check is the only evidence that the bytes applied are the bytes approved. `0002`'s packet records
a period in which its own forward digest had gone stale and nothing noticed.

### What the SQL does, and what it deliberately does not

**Purely additive.** Every statement is `CREATE TABLE IF NOT EXISTS` or `CREATE INDEX IF NOT EXISTS`
and nothing else: no `ALTER`, no `DROP`, no `TRUNCATE`, no `GRANT`/`REVOKE`, no DML, no dollar-quoted
body, and **no `ON DELETE` clause in any statement** — so every foreign key takes the SQL default,
`NO ACTION`, and no cascade exists anywhere. Re-running either file is a no-op.

**It does not touch `records`.** The production-derived 30-row sample is neither read, written,
altered, nor referenced in a constraint. The write path's statement policy refuses any statement
naming it, and a test reads both files off disk and asserts the identifier does not appear.

### Evidence, and the limit on it

CI applies `0001`→`0004` forward against a `postgres:18` service container, proves the pending/applied
plan at each step, exercises constraints against input they should reject, runs the submission
lifecycle end to end, and proves the rollback order — including that `0003`'s rollback **fails** while
`isaac_submissions` still references it, and that the failed attempt destroys nothing.

**Two limits, stated because they are the reason your step is separate:**

1. **Constraint coverage is partial — and better than when this package was first written.**
   RE-MEASURED 2026-08-19: the two files declare **46** named constraints and CI's constraint step
   now blames **41** of them, up from 27. The seventeen that were declared and never exercised are
   now exercised, fourteen of them individually.

   **Three of the seventeen cannot be blamed individually, and that is a property of the schema
   rather than a gap in the testing.** `isaac_submission_runs` carries `record_id = unit_id` and
   `run_id IS NULL OR run_id = unit_id`, so any row violating `unit_id_shape`, `record_id_shape` or
   `run_id_shape` violates an equality CHECK at the same time, and PostgreSQL reports only the first
   constraint it happens to check. There is no assignment of those three columns that violates
   exactly one of them — defence in depth, not a defect. The workflow proves those rows ARE refused,
   by a CHECK on that table, through a deliberately weaker helper so it cannot be mistaken for the
   stronger claim.

   The remaining two — `isaac_revision_changes_revision_fk` and `isaac_submissions_experiment_fk` —
   appear in the workflow for other reasons without a refusal blamed on them.

   So: **41 of 46 individually blamed; 3 more proved refused with the blame ambiguous by
   construction; 2 named without a refusal.** `0003`'s packet §12B carries the accounting and the
   reasoning. **None of this changes the bytes you would apply** — the four digests are unchanged
   and re-verified below.
2. **The container is empty**, with a two-row synthetic stand-in for `records`. *"Is this valid,
   idempotent SQL whose constraints behave"* is answered. *"Does it behave against the real data,
   roles and grants"* is **not**, and only applying it resolves that.

### Apply path, prechecks and postchecks

Each packet carries its own operator section (§9 apply, §10 postchecks, §11 rollback). **Postchecks 1
and 2 — the `records` and `isaac_experiments` row counts, before and after — are REQUIRED and must be
reported.** `0002`'s record notes both as *not reported*, and "no mechanism exists to change them" is
not the same as "it was observed that they did not change."

**Rollback destroys the entire submission history irrecoverably** — unlike `isaac_runs`, these tables
are not a shadow of anything, and the experiment document carries no revision history. Dump first;
the commands are in `0003`'s packet.

---

## 1A. `0005_run_projection` — NOT APPROVED, NOT AN ASK. Listed so it is not a surprise.

| | `0005_run_projection` |
|---|---|
| **Owner approval** | **NOT APPROVED** (Krish has not reviewed the text) |
| **Hosted application** | **NOT APPLIED, anywhere** |
| **Forward SHA-256** | `ebff660fc51559cd4ab6ce66a7b1ec943de86f2362d37adde153f0c74c8ae7ee` |
| **Rollback SHA-256** | `54a17432150525f75a6e94557a137029a3ce3fd41cea9debced361abda90e735` |
| **Table created** | `isaac_run_projection` (one table, one index) |
| **Packet** | [`docs/migration-approval-packet-0005.md`](migration-approval-packet-0005.md) |

**What it is, in one paragraph.** `0002_runs`, which you applied on 2026-08-12, made `isaac_runs` a
shadow of the experiment document — rows are maintained, and nothing reads them. A reader cannot be
written against that alone, because `SELECT ... FROM isaac_runs WHERE experiment_id = %s` returning
**zero rows** means *either* "this experiment has no runs" *or* "its runs were never projected", and
both are reachable — the second is the normal state of every experiment saved before the shadow write
shipped, and of every save in the window between a merge and your `--apply`. A reader that guessed the
first would silently delete every run of every pre-existing record and report success. This table
records the claim explicitly, with the document version it was made at, so staleness is *detected*
rather than assumed absent.

**Same shape as the other three.** Purely additive: `CREATE TABLE IF NOT EXISTS` and
`CREATE INDEX IF NOT EXISTS`, nothing else. No `ALTER`, no `DROP`, no `TRUNCATE`, no DML, and **no
`ON DELETE` clause**, so deleting an experiment that still carries a claim is refused by the database.
It does not touch `records`, and a test reads the file off disk and asserts the identifier does not
appear in any statement.

**One rollback dependency that is NOT what the numbering suggests**, and it is the only thing here
worth reading twice: `isaac_run_projection` references `isaac_experiments`, **not** `isaac_runs`. So
it must be rolled back before `0001`, and it is **independent of `0002`** — rolling `0002` back while
this table stands is legal and leaves every claim describing rows that no longer exist. The
application handles that as a fallback to the document rather than as an error, which is why the
rollback file documents it instead of forbidding it. CI proves the order and proves that the
wrong order fails safely without dropping anything.

**Nothing reads it in the shipped build.** Exactly one statement in the application names the table,
it is a write, and a test measures that over the module-level statement set. Moving a reader onto
`isaac_runs` is a separate decision, and it is gated on a backfill having run and reported zero
unprojected experiments — a measurement, not a belief. The backfill script exists, has **never been
executed anywhere**, and is deliberately absent from the container image.

---

## 2. External configuration ISAAC cannot create for itself

Each of these is **built and tested against a deterministic fake**, and each is inert until an
external endpoint/credential exists. None is a request to enable anything today; they are listed so
the dependency is visible in one place.

| # | What is needed | Why ISAAC cannot supply it | State in the repository |
|---|---|---|---|
| **E1** | A **trusted authentication boundary** for API/service traffic — the portal precedent: trusted-edge headers for browser traffic, independent Bearer validation for service traffic | The Service is a plain ClusterIP with **no NetworkPolicy**, so an in-cluster pod can reach the app directly and forge forwarded identity headers. Header presence is therefore **not** proof of authentication. | **UPDATED 2026-08-19.** The seam is now complete on the application side and still **fails closed**: `attribution.uploaded_by` is server-stamped at the ingestion boundary, sourced only from a verifier, and requires `trust_basis == verified_edge_assertion` — which **no verifier in this build mints**, so no deployment stamps anything and `trust_basis` remains `unattributed` on every row. When this boundary exists, arming it is a verifier and a configuration value, not a product change. |
| **E2** | **Hosted MCP reachability and auth** | Ingress and auth are yours | MCP transport and tools exist behind a **fail-closed gate**; no unauthenticated hosted route is exposed. |
| **E3** | A **production model provider** — endpoint, credential, billing | Institutional | Provider abstraction + deterministic fake provider only. The UI states the assistant is unconfigured rather than implying one exists. |
| **E4** | A **production transcription provider** | Institutional | Same shape: provider-ready, refuses at boot, no audio leaves the process. |

**You deferred D1–D9 on 2026-08-12** and recommended leaving AI integration as future work. That
recommendation is recorded and unaltered. The project owner elected to continue *implementing* against
fakes; **nothing above asks you to approve a provider.**

---

## 3. Governance decisions still open — silence is not assent

| Gate | The question | Status |
|---|---|---|
| **G2** | May the hosted app display **per-record** content from the 30 production-derived records? | **CLOSED BY DEFAULT.** Your guide requires the boundary be built into the read path from the start. No real-record adapter, list, detail, evidence view or export exists. |
| **G3** | Five aggregates shipped in `v0.0.32` that went **beyond** your enumerated list — `by_instance_path`, `distinct_structural_signatures`, the `total_link_count`/`dangling_link_count` pair, and `vocabulary_term_count`. Were they within your intent? | **OPEN.** All five are now **withheld** from the HTTP response and named in `dataset.withheld_pending_visibility_decision`. Only you can say whether they were acceptable. |
| **G6** | The personal-data / seed constraint, if still active | **OPEN** |

Also unanswered from earlier rounds and therefore exactly as open as before: **Q11**, **Q13**,
**Q14**, **Q16**, and **Q20(f)** (does the portal enforce JSON Schema `format`?).

---

## 4. What this package does NOT ask for

- No kubeconfig, port-forward, or Secret. No agent-initiated database connection.
- No `isaac-k8` change, no ingress change, no NetworkPolicy — **E1 is a statement of dependency, not a
  change request**; how the boundary is provided is yours to decide.
- No new migration beyond the two above. A Run-store cutover migration is **not** proposed: the
  read-side transition is unbuilt and, when designed, will get its own packet.
- No credential, no billing arrangement, no provider approval.

---

## 5. If you only have five minutes

1. **Tell us the answer to G2 and G3.** They gate more product work than anything else in this
   package, and neither asks you to touch infrastructure — both are decisions. This is first now
   because the migrations have been waiting on an operator window since 2026-08-17 while these two
   have been waiting on nobody.
2. Recompute the four digests in §1 and refuse on any mismatch. **Re-verified 2026-08-19: all four
   still MATCH the values Krish approved**, so the bytes are unchanged and the approval stands.
3. Apply `0003` and `0004` **together**, and report the `records` and `isaac_experiments` counts
   before and after.
4. **Do NOT apply `0005`.** It appears in §1A only so it is not a surprise later. It has not been
   approved by Krish, and owner approval comes before an operator window, never after.
5. Everything in §2 can wait; nothing is broken while it does, and no surface claims otherwise.

---

## 6. What changed in the repository since this package was written

**None of it is a request.** It is here because two items above are easier to weigh with it, and
because a package that describes a repository should describe the current one.

**The product could not capture a record, and now can.** A record created through the application's
own Create Experiment path could not be completed or exported by ANY route — measured on `main` at
`b118ed6`, not inferred. Three independent causes: a QC verdict no request could supply, a spectrum
and a descriptor answerable only by confirming a worked example that a created record does not have,
and a Run that silently discarded everything already answered. All three are fixed, and a test now
walks create → answer → export with values written out rather than harvested from a fixture, because
every other export test in the repository started from a fixture draft that already carried them —
which is why a suite of thousands stayed green while the path did not work.

**Why that matters to your two decisions.** The submission lifecycle `0003`/`0004` record is now
reachable by a scientist rather than only by a fixture, so applying those migrations changes what a
real person can finish rather than what a test can. And **G2** is no longer only about the 30
production-derived records: the application now creates records of its own, so "may the hosted app
display per-record content" has a second, cleaner answer available — app-created records are not
production-derived and carry no visibility question at all.

**Constraint coverage moved 27 → 41 of 46**, validated against a real `postgres:18` in CI. See §1.

**A third migration now exists and is NOT in the ask.** `0005_run_projection` — see §1A. It is
mentioned here as well as there because the one thing this package must never do is let a new
migration file appear in the repository and read, by proximity to two approved ones, as a fourth
thing waiting on you.

**The MCP tool surface can now complete a record, and could not before.** An agent could add a Run
and write its five context/timing fields, and could not answer any OPEN blocking question at either
level — which on a record created through the application's own path is every question it has. Two
tools were added (ten in the registry). This changes nothing about MCP reachability or
authentication: **D1 and D2 remain deferred, no endpoint is exposed, and `Connect Your Agent` still
shows no connection.**

**The native-assistant seam is now reachable over HTTP and answers `501` in every deployment.** It
was a fully built seam with no route, so "does this deployment have a native assistant?" was
answerable only by reading Python. The application refuses to boot if an operator points it at the
test double, so no deployment can answer from one, and **no product screen advertises the seam at
all** — building the capability and advertising it are different acts. **D3/D4/D5 are untouched:
there is no provider, no credential, no outbound call and no charge.**

**E1 is unchanged in substance and complete in the application**: the identity seam now stamps
`attribution.uploaded_by` at the ingestion boundary and refuses unless the trust basis is
`verified_edge_assertion`, which no verifier in this build mints. Nothing is stamped anywhere. When
the boundary exists, arming it is a verifier and a configuration value.
