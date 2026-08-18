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

## 1. Two migrations, approved and awaiting an operator

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

1. **Constraint coverage is partial.** The two files declare **46** named constraints; CI's constraint
   step blames **27** of them. 19 are declared and unexercised (17 never named in the workflow at
   all). They are listed by name in `0003`'s packet §12B. Nothing suggests they are wrong — the
   packets simply may not be cited as evidence that they behave.
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

## 2. External configuration ISAAC cannot create for itself

Each of these is **built and tested against a deterministic fake**, and each is inert until an
external endpoint/credential exists. None is a request to enable anything today; they are listed so
the dependency is visible in one place.

| # | What is needed | Why ISAAC cannot supply it | State in the repository |
|---|---|---|---|
| **E1** | A **trusted authentication boundary** for API/service traffic — the portal precedent: trusted-edge headers for browser traffic, independent Bearer validation for service traffic | The Service is a plain ClusterIP with **no NetworkPolicy**, so an in-cluster pod can reach the app directly and forge forwarded identity headers. Header presence is therefore **not** proof of authentication. | The identity seam exists and **fails closed**: no actor is stamped anywhere, and `trust_basis` is `unattributed` on every row. Actor stamping is authorized by you and **blocked in practice** until this exists. |
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

1. Recompute the four digests in §1 and refuse on any mismatch.
2. Apply `0003` and `0004` **together**, and report the `records` and `isaac_experiments` counts
   before and after.
3. Tell us the answer to **G2** and **G3** — those two gate more product work than anything else here.
4. Everything in §2 can wait; nothing is broken while it does, and no surface claims otherwise.
