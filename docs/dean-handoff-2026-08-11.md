# Dean handoff — 2026-08-11

**What this is.** A single index for everything ISAAC currently needs from Dean, assembled so that
Krish can send one message and one self-contained prompt, and Dean's Claude can act without any
conversational history from Krish's session.

**What this is not.** It is not a new set of questions. Every question below already exists in this
repository under an identifier that has, in most cases, already been put to Dean. This document
**routes** them; it does not renumber them. See "Identifier discipline" at the end — one collision was
found and fixed while assembling this, and it would have made a one-word reply from Dean ambiguous.

**Nothing in this document has been transmitted.** No approved workflow permits agent-to-Dean
communication. Sending is Krish's act.

---

## 0. Measured state at handoff

Every figure here was measured on 2026-08-11 at the commit named; none is recalled.

| Fact | Value | How measured |
|---|---|---|
| canonical repository | `https://github.com/ISAAC-DOE/isaac-metadata-assistant` | `git remote -v` (`origin`) |
| `main` HEAD | `64e93c9372d16958b941569252fbc9abdc373c00` | `git rev-parse HEAD` |
| working tree | clean, **0 ahead / 0 behind** `origin/main` | `git status -sb`, `git rev-list --left-right --count` |
| open PRs | **0** | `gh pr list --state open` |
| CI at that commit | **success, all four jobs** — run [31506181717](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/31506181717), event `push` | `gh run view` |
| PostgreSQL proof | job `migration and durable repository against a real PostgreSQL` ([93828219677](https://github.com/ISAAC-DOE/isaac-metadata-assistant/actions/runs/31506181717/job/93828219677)) → **success**, engine `PostgreSQL 18.4 (Debian 18.4-1.pgdg13+1)` printed by the server itself | `gh run view --job … --log` |
| hosted application | `https://isaac.slac.stanford.edu/krish/` serving commit **`64e93c9…`**, `mode: synthetic-only`, `experiment_storage: {backend: postgres, durable: true}`, `record_display: closed`, `last_recon: null` | authenticated browser read of `/krish/api/health` |

**The hosted deployment is running the exact commit this handoff is measured at.** That is unusually
clean and worth stating: there is no version skew to reason about.

**No database connection was opened from this environment.** No kubeconfig, port-forward or Kubernetes
Secret was requested or used, in preparing this document or anything it references. The rule at
`docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52` is untouched.

---

## 1. Migration `0002_runs` — an operator action, not an open question

**Krish approved this migration for hosted application on 2026-08-11.** The approval is recorded in
[`docs/migration-approval-packet-0002.md`](migration-approval-packet-0002.md) (STATUS block) and is
**specific to the exact reviewed bytes**. It does not authorize materially modified SQL.

### Identity — quote these, do not re-derive by eye

| | |
|---|---|
| version | `0002_runs` |
| forward | `apps/api/isaac_api/migrations/0002_runs.sql` |
| **forward sha256** | `c96e308d7fdfd508ab2c2aeffb08abcb18a88aae84db6f1d08b83f9cba8fda3e` |
| rollback | `apps/api/isaac_api/migrations/0002_runs.rollback.sql` |
| **rollback sha256** | `0206012116a443fb301e9c161b5eb2ffcfe0e99ee6f460ce83d80e30d327cdd5` |
| introduced | `b8f0a1a` |
| last substantive edit | `90b432d` — an in-place correction to the `isaac_runs_document_identity` CHECK, made while the migration was unapplied everywhere |
| commits touching it since | **none** — `git log --follow` returns exactly two commits for the forward file and one for the rollback |
| canonical packet | [`docs/migration-approval-packet-0002.md`](migration-approval-packet-0002.md) — read §8 → §9 → §10 in order |

**A stale-hash warning that is not hypothetical.** The forward digest in that packet was **wrong**
from `90b432d` until 2026-08-10: `90b432d` corrected the SQL in place and left the hash table pointing
at the superseded bytes. An operator following the packet's own instruction would have computed a
mismatch against the file they were about to apply. It is now pinned by a test
(`test_the_approval_packet_quotes_the_migration_it_describes`). **Historical reports in this
repository therefore contain more than one forward hash for `0002_runs`. The digest above is the only
current one** — it is the file at `64e93c9`, measured today, and it equals the packet's table.

### What it does

Two statements, both `CREATE … IF NOT EXISTS`:

1. table `isaac_runs` — `run_id` PK, `experiment_id` NOT NULL with a foreign key to
   `isaac_experiments`, `ordinal`, `state` jsonb, `rev`, `generation`, two server-side timestamps, and
   five named CHECK constraints;
2. index `isaac_runs_experiment_order_idx` on `(experiment_id, ordinal, run_id)`.

### What it does not do — each verified by reading the committed SQL

- **No `CASCADE`.** Stronger: the foreign key carries **no `ON DELETE` clause at all**, so the action
  is SQL's default `NO ACTION`, which for this non-deferrable constraint **refuses** a parent delete.
- **No `ALTER`, no `TRUNCATE`, no forward `DROP`.**
- **No DML of any kind** — no `INSERT`, `UPDATE`, `DELETE`. No backfill, no data movement.
- **The protected `records` table is not named**, in any position, in either file. Pinned by
  `test_no_committed_migration_may_reference_the_production_table`.
- **It does not move the currently-embedded Runs** out of the experiment document, and **it changes no
  application behaviour**: no statement this application can issue names `isaac_runs`, pinned by
  `test_0002_is_inert_for_this_build_no_statement_names_isaac_runs`. The app behaves identically with
  it applied and unapplied.
- It touches no `isaac-k8` manifest, no model provider, and no Authentik configuration.

### Proven in CI — and it is a real engine, not a fake

At `64e93c9` on a `push` event, against `postgres:18` (server reports `18.4`): the migration applies
to an empty database; a second apply is a no-op; the bookkeeping rows are deleted and it applies again
with an identical `information_schema.columns` digest across all three states; exactly the three
application-owned tables are added and none removed; a stand-in `records` table is byte-identical
afterwards; **twelve negative controls are each refused by the expected named object**, including the
foreign key refusing a parent delete; two deliberate admissions behave as designed; and both rollback
orders behave as documented — wrong order fails loudly and destroys nothing.

### NOT proven until Dean applies it — do not let the green check blur this

The hosted database's **roles, grants and existing objects**; its **real 30-row production-derived
data**; its **actual engine build** (parity with 18 is documented in `postgres-test-db-guide.md`, not
measured here); **observed locking** (§5's analysis is reasoned, no `pg_locks` observation exists);
and whether `isaac_experiments`, which is **not** empty there and whose contents are unknown here,
behaves as expected. A green `postgres-migration` job is **not** a hosted rehearsal.

### Prerequisite state

`0001_experiments` was applied to the hosted database by Dean on **2026-08-09**
([evidence](evidence/hosted-0001-verification-2026-08-09.md)). `0002_runs` is pending everywhere.

---

## 2. The four workstreams

**"Workstream" is a routing label for this handoff only. It is not a decision identifier and creates
none.** Each workstream points at questions that already have identifiers.

| # | Workstream | Kind | Existing identifiers | Where |
|---|---|---|---|---|
| **1** | Apply `0002_runs` | **Operator action** — approved, has a runbook | *(none — not a question)* | [`migration-approval-packet-0002.md`](migration-approval-packet-0002.md) §8→§9→§10 |
| **2** | Authoritative identity source | Infrastructure inspection **+** decisions | **Q1, Q4, Q5, Q6, Q7, Q8, Q9, Q10, Q17, Q18, Q25** | [`identity-trust-contract.md`](identity-trust-contract.md) §7 |
| **3** | MCP hosted reachability + auth | Infrastructure inspection **+** decisions | **D1, D2** | [`ai-integration-decision-packet.md`](ai-integration-decision-packet.md) §5 |
| **4** | Native AI + transcription | **Policy/institutional decisions**, mostly not technical | **D3, D4, D5, D6, D7, D8, D9** | [`ai-integration-decision-packet.md`](ai-integration-decision-packet.md) §5 |
| **appendix** | Six `system.configuration.*` fields | **Scientific** — Angel, not infrastructure | *(no `Q`/`D` — see §4 below)* | [`run-scope-decision-packet.md`](run-scope-decision-packet.md) §4 |

### Workstream 2 — what is already answered, so Dean is not asked twice

A temporary probe ran once against hosted `d521dd7` on 2026-08-02 and **has since been removed** (the
route now returns 404, pinned by a test). Do not re-add it. What it established
([`identity-trust-contract.md`](identity-trust-contract.md) §6A):

- All seven probed headers arrived. **ISAAC consumes none of them.**
- For `username`, `uid`, `email`, `name`, `groups`: the edge **supplied the value and did not append**
  the client's planted canary. **It does not follow that the client's copy was removed** — §6A.1 names
  two scenarios with the same signature, one of which means the client *did* influence the header.
- For **`X-authentik-entitlements` and `X-Isaac-Edge`, the client's own value arrived untouched.** So
  `X-Isaac-Edge` cannot witness that a request traversed the edge — the one job its name implies. Both
  are treated by ISAAC as permanently disqualified from any security decision.
- **Q4 is untouched by all of this**: whether an in-cluster workload can reach the Service directly,
  bypassing Authentik, is unobserved and is Dean's.

**So the open part is not "which header arrives" — it is whether the arriving value is trustworthy,
and whether the identifier survives a rename or rehire.** That is Q18, Q5 and Q17, plus Q25 for
ISAAC's own actor columns.

### Workstream 3 — the architectural fact that must not be lost

**MCP is one-way.** A scientist's Claude client calls ISAAC's tools. **Connecting MCP does not give
ISAAC native inference** — that is workstream 4, and the two are routinely conflated.
`ai-integration-decision-packet.md` §1.1 exists solely to protect this distinction.

The blocker is that Authentik forward-auth is not usable by a non-interactive external MCP client.
**No Authentik bypass is acceptable and no weakening of web authentication is on the table.**

### Workstream 4 — mostly not a technical question

D3–D9 are provider selection, credential custody, billing, egress policy, retention and data policy.
Dean's Claude can establish **what is technically available**; it must not invent policy, create paid
accounts, incur charges, or send any scientific data anywhere during discovery.

---

## 3. What Krish needs back

**For workstream 1** — a sanitized operator report: namespace and deployment actually used; migration
version applied; `records` count before and after; `isaac_experiments` count before and after; the
`isaac_schema_migrations` rows; `isaac_runs` schema and index as read back from the server; the
`isaac_runs` row count; the second-invocation idempotence result; application health afterwards; any
errors; and whether rollback was required. **No secrets, no connection strings, no record contents.**

**For workstreams 2–4** — answers against the **existing identifiers**, quoted by number, plus the
configuration evidence behind each infrastructure answer. Where a question needs Angel or an
institutional policy owner rather than Dean, saying so *is* the answer we need.

**A partial return is useful.** These are independent; workstream 1 does not wait on 2–4, and vice
versa. Application development continues in parallel and is not blocked on any of them.

---

## 4. Scientific appendix — six `system.configuration.*` fields

**Not Dean's decision, and not answerable from infrastructure.** These are scientific-semantics
questions for Angel or an equivalent domain owner; Dean is asked only to route them.

Full analysis, with schema text, current behaviour, and the cost of each wrong answer:
[`docs/run-scope-decision-packet.md`](run-scope-decision-packet.md) §4.

The question for each is the same: **does this field belong to the Experiment (entered once, inherited
by every Run) or to the Run (recorded per Run)?**

| Field | Type | Why Experiment-level is plausible | Why Run-level is plausible | Recommendation |
|---|---|---|---|---|
| `system.configuration.detector_model` | `str` | entered once; a run that differs files an audited override | a run that swapped detectors records its own value | **None** — a scientific judgement with no evidence in this repository |
| `system.configuration.monochromator_crystal` | `str` | same | same | **None** |
| `system.configuration.spectrometer_geometry` | `str` | same | same | **None** |
| `system.configuration.n_scans` | `int` | one value for the whole set | "number of scans **for this run**" is what the name reads like — *and reading like it is not evidence* | **None** |
| `system.configuration.proposal_id` | `str` | a proposal plausibly covers a whole experiment | each run carries its own | **No evidence-backed recommendation** — a stated *expectation* of experiment-level, offered to be corrected. Nothing in this repository says what scope an SSRL proposal covers |
| `system.configuration.session_id` | `str` | a session plausibly covers a whole experiment | each run carries its own | **No evidence-backed recommendation**, same basis |

**The cost of a wrong answer, both directions.** Experiment-level while the thing actually varied →
every Run's exported record names the one value, and a reader cannot tell which Runs diverged.
Run-level while it never varied → the same value is re-typed per Run with nothing checking that the
entries agree, so a typo yields a record attributed to a proposal or session that does not exist.

**One input changed on 2026-08-11 and makes a wrong answer cheaper to recover from.** Per-Run
overrides are now reachable over HTTP (`POST /experiments/{id}/runs/{run_id}/overrides` →
`set_run_override`, merged in [#109](https://github.com/ISAAC-DOE/isaac-metadata-assistant/pull/109)),
so divergence **is** now recordable as an audited override that preserves the displaced value. A
previous revision of the run-scope packet said no route reached it; that clause is false and is struck
there rather than deleted.

**This does not block the rest of the application.** All six are handled today without an answer.

---

## 5. Identifier discipline — read before adding anything

**Identifiers that have been sent to an external decision-maker are append-only. Add the next free
number; never shift, never reuse.**

Two violations were found and fixed while assembling this handoff, both from the same root — a number
guessed instead of measured:

1. **`Q20` had two live meanings.** It has meant *"may JSON Schema `format` enforcement be armed in
   the official validator?"* since before 2026-08-05, and that meaning is load-bearing in committed
   code (`authorization.Q20_FORMAT_ENFORCEMENT_APPROVED`, plus seven files under `apps/api/`). On
   2026-08-11 the scientist-capture programme filed a *different* question — server-stamped actor
   columns — as `Q20` as well. Had the handoff gone out that way, a reply of *"Q20: yes"* would have
   been ambiguous between arming a validator gate on the truth path and authorizing actor stamping,
   with nothing downstream able to detect which was meant. **The actor question is now `Q25`;** `Q20`
   keeps its established meaning.
2. **The rule's own example reused an identifier.** `ai-integration-decision-packet.md` said *"Add
   `D10`, `Q21`"* while `Q21` was already in use (`portal-identity-and-metrics-audit.md:133`). Now
   corrected to name the measuring command instead of a guessed number.

Measure the next free identifier before adding one:

```bash
grep -rhoE '\b(Q|D)[0-9]{1,3}\b' docs/ apps/ src/ | sort -u -V | tail -5
```

At `64e93c9` the highest in use are **`Q25`** and **`D9`** — so the next free are `Q26` and `D10`.

**Do not renumber `D1`–`D9`.** A previous continuation prompt proposed a list that shifted them by
two, which would have silently redirected an answer about *retention* onto *which provider*. The
rejection and its reasoning are recorded at
[`ai-integration-decision-packet.md`](ai-integration-decision-packet.md) §5.
