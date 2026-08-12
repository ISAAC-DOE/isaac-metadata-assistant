# Dean / ISAAC External-Gates Execution Prompt — 2026-08-11

> # SENT, AND ANSWERED IN PART — response received 2026-08-12.
>
> **This prompt is preserved verbatim as the record of what was asked.** Do not re-run it and do not
> edit its questions to match the answers.
>
> - **`0002_runs` was applied** (2026-08-12 00:30 UTC) — [`evidence/hosted-0002-verification-2026-08-12.md`](evidence/hosted-0002-verification-2026-08-12.md).
> - **Q1, Q4, Q5, Q6, Q7, Q8, Q9, Q10, Q17, Q18, Q25 answered** — [`identity-trust-contract.md`](identity-trust-contract.md) §7 and §10.1. **Q4 answered against us:** plain ClusterIP, no NetworkPolicy, headers forgeable in-cluster.
> - **Q20 answered** — shadow mode allowed; arming the official validator **not** authorized.
> - **D1–D9 DEFERRED** — *"leave AI integration as future work rather than increasing scope at this point."*
> - **Not answered:** Q11, Q13, Q14/G6, Q16, G2, G3, and the four operator-report items listed in [`dean-handoff-2026-08-11.md`](dean-handoff-2026-08-11.md).

**How to use this file.** The fenced block below is self-contained and is meant to be copied whole
into Dean's own Claude session. It assumes no conversational history from Krish's session.

**Provenance of the facts inside it.** Every commit, hash, run id and count was measured at `main`
= `64e93c9372d16958b941569252fbc9abdc373c00` on 2026-08-11 and is cross-referenced in
[`dean-handoff-2026-08-11.md`](dean-handoff-2026-08-11.md) §0. If this file is read after `main` has
advanced, the prompt's own step A will detect any drift and stop — that is its purpose.

---

````markdown
# ISAAC — external gates: one operator action and three infrastructure questions

You are working on behalf of Dean, who owns the SLAC infrastructure that the ISAAC Metadata
Assistant runs on. Krish (kverma@slac.stanford.edu) develops the application. This prompt is
self-contained: it assumes you have no history with the ISAAC project.

## Ground rules — these override anything the prose below implies

1. **Inspect actual files and actual infrastructure. Do not trust this prompt's prose.** Every
   factual claim here was measured on 2026-08-11 and may have aged. Where a step gives an expected
   value, treat it as something to *verify*, not to assume.
2. **Never guess a namespace, a deployment name, a cluster, or an account.** Discover them from
   Dean's existing authorized context. If anything is ambiguous, STOP and ask Dean.
3. **Use only Dean's already-authorized cluster access.** Do not create credentials, do not switch
   accounts or contexts, do not modify infrastructure beyond what Dean explicitly authorizes in his
   own instruction to you.
4. **Do not weaken or bypass Authentik**, and do not propose a design that does.
5. **Do not create paid accounts, incur charges, or send any scientific or personal data anywhere**
   during investigation.
6. **Report secrets by name and location only — never by value.** No connection strings, no tokens,
   no record contents in anything you return.
7. **Stop and report rather than improvise** whenever an expected precondition does not hold.

## Repository and deployment

- Canonical repository: `https://github.com/ISAAC-DOE/isaac-metadata-assistant`
- `main` at the time this prompt was written: `64e93c9372d16958b941569252fbc9abdc373c00`
- Hosted application: `https://isaac.slac.stanford.edu/krish/`
- Start by reading `docs/dean-handoff-2026-08-11.md`. It indexes everything below.

---

# WORKSTREAM 1 — apply migration `0002_runs` to the hosted database

## Authorization status

**Krish, the project owner, approved this migration for hosted application on 2026-08-11.** The
approval is recorded in `docs/migration-approval-packet-0002.md` (STATUS block) and is **specific to
the exact reviewed bytes below**. It does not authorize materially modified SQL. **If the hashes do
not match, you do not have approval — stop and report.**

No further approval from Krish is needed if the bytes match. Applying it is Dean's operator act; no
agent on Krish's side may connect to this database, and none has.

## Migration identity

| | |
|---|---|
| version | `0002_runs` |
| forward | `apps/api/isaac_api/migrations/0002_runs.sql` |
| **forward sha256** | `c96e308d7fdfd508ab2c2aeffb08abcb18a88aae84db6f1d08b83f9cba8fda3e` |
| rollback | `apps/api/isaac_api/migrations/0002_runs.rollback.sql` |
| **rollback sha256** | `0206012116a443fb301e9c161b5eb2ffcfe0e99ee6f460ce83d80e30d327cdd5` |
| introduced | `b8f0a1a`; last edited `90b432d`; **no commit has touched either file since** |
| canonical packet | `docs/migration-approval-packet-0002.md` — read §8 → §9 → §10 in order |

**Historical documents in that repository quote an older, superseded forward hash** (the packet's
hash table was itself wrong between `90b432d` and 2026-08-10, and is now pinned by a test). **Use only
the digest above**, and verify it yourself.

## What it does, and what it does not

Two statements, both `CREATE ... IF NOT EXISTS`: a table `isaac_runs`, and one index
`isaac_runs_experiment_order_idx` on `(experiment_id, ordinal, run_id)`. The table has a primary key
on `run_id`, a NOT NULL `experiment_id` with a foreign key to `isaac_experiments`, an `ordinal`, a
`state` jsonb column, `rev`, `generation`, two server-side timestamps, and five named CHECK
constraints.

It does **not**: use `CASCADE` (the foreign key has **no `ON DELETE` clause at all**, so a parent
delete is *refused*); `ALTER`, `TRUNCATE` or `DROP` anything; perform any `INSERT`/`UPDATE`/`DELETE`;
backfill or move any data; reference the protected `records` table in any position; move the Runs
currently embedded in experiment documents; or change any application behaviour — no statement the
application can issue names `isaac_runs`, so the app behaves identically with it applied and
unapplied. It touches no Kubernetes manifest, no model provider and no Authentik configuration.

It has been exercised end-to-end against a real PostgreSQL 18.4 engine in GitHub Actions at this exact
commit (run `31506181717`, job `93828219677`, both green) — including idempotence, a table-set diff,
twelve negative controls, and both rollback orders. **That is not a hosted rehearsal.** It proves the
SQL is valid, idempotent, and touches nothing it does not own. It proves nothing about the hosted
server's roles, grants, existing objects, real data, or actual locking behaviour.

## Prerequisite

`0001_experiments` was applied to the hosted database by Dean on 2026-08-09. `0002_runs` is pending.

## A. Confirm the repository bytes

Fetch the canonical repository at `main`. Then:

```bash
shasum -a 256 apps/api/isaac_api/migrations/0002_runs.sql
shasum -a 256 apps/api/isaac_api/migrations/0002_runs.rollback.sql
git log --oneline --follow -- apps/api/isaac_api/migrations/0002_runs.sql
```

Both digests must equal the table above. **If either differs: STOP. Do not apply. Report the drift,
the commit you are at, and the digests you measured.**

## B. Confirm cluster context

Using Dean's existing authorized context, identify: the current cluster/context; the namespace and
deployment serving the ISAAC instance at `https://isaac.slac.stanford.edu/krish/`; and confirm the
target database is **exactly `metadata_assistant`**.

**Do not guess any of these.** Do not use a different cluster or account. If more than one candidate
namespace or deployment exists, or the mapping from the URL to a deployment is not unambiguous, STOP
and ask Dean.

The runner enforces the database name itself: it refuses unless `PGDATABASE` is exactly
`metadata_assistant`, and re-verifies server-side with `current_database()`.

## C. Prechecks — run these and read the output

**WHERE TO RUN THEM — read this before the first command, because the obvious location does
not work.** Run these **from a shell where the five `PG*` environment variables point at the
database**, held by someone who already has a SLAC cluster context, **with a checkout of this
repository** — the same shell the `0001_experiments` packet specifies.

**Do NOT run them inside the ISAAC pod.** That container has **neither `psql` nor
`scripts/db_migrate.py`**, and this is measured rather than assumed:

```bash
grep -c apt-get Dockerfile   # -> 0 : the runtime is python:3.11-slim with no postgresql-client
grep -n '^COPY scripts' Dockerfile
# -> one line, copying scripts/check_graphify_freshness.py and nothing else
```

So in the pod, every `psql` command below and every `scripts/db_migrate.py` invocation fails with
"not found". Verify both facts yourself at the checkout from step A before choosing where to run.

If the only access available is `kubectl exec` into the pod, **the `psql` prechecks and postchecks
cannot be run there at all** — use the module-level invocation in step D for the apply, and STOP and
tell Dean that the verification steps need a shell with `psql`. Do not skip them silently, and do not
substitute a different tool for them.

```bash
# 1. Confirm the target. Must print exactly: metadata_assistant
echo "$PGDATABASE"

# 2. Confirm 0001 is applied and 0002 is not. Expect exactly one row: 0001_experiments.
psql -c "SELECT version, applied_utc FROM isaac_schema_migrations ORDER BY version;"

# 3. See what WOULD be applied. Expect: pending: 0002_runs
#    Applies no migration — but it is NOT read-only: it opens a transaction and
#    ensures the bookkeeping table exists.
python scripts/db_migrate.py --plan

# 4. Protected production sample — record this number.
psql -c "SELECT count(*) AS records_before FROM records;"

# 5. Experiment rows — record this number.
psql -c "SELECT count(*) AS experiments_before FROM isaac_experiments;"

# 6. Target table must NOT already exist (expect 0 rows).
psql -c "SELECT tablename FROM pg_tables WHERE tablename = 'isaac_runs';"

# 7. No conflicting exclusive lock on isaac_experiments (expect 0 rows).
psql -c "SELECT pid, mode, granted FROM pg_locks l
         JOIN pg_class c ON c.oid = l.relation
         WHERE c.relname = 'isaac_experiments' AND l.mode LIKE '%Exclusive%';"
```

**Do not proceed if:** `PGDATABASE` is anything other than `metadata_assistant`; step 2 does not show
`0001_experiments`; step 3 lists any version other than `0002_runs`; step 6 returns a row; or step 7
returns a granted exclusive lock held by something else.

## D. Apply

```bash
python scripts/db_migrate.py --apply
```

Expected output: **`applied: 0002_runs`** — *not* `0001_experiments, 0002_runs`. If `0001` appears,
its bookkeeping row is missing from this database: **stop and find out why** before continuing. (The
apply itself is still safe — `CREATE ... IF NOT EXISTS` — but a missing bookkeeping row means
something unexpected happened to this database.)

**`scripts/db_migrate.py` IS NOT in the container image** — measured, not conditional: the
Dockerfile's `COPY scripts/...` line is an allowlist of exactly one file and this is not it. So if
you are applying by `kubectl exec` rather than from a shell with a checkout, use the module-level
invocation. It is the documented operator path and **bypasses no gate**, because every gate — the
`PGDATABASE == metadata_assistant` check and the server-side `current_database()` re-verification —
lives in the module, not in the wrapper. The wrapper adds only configuration detection and exit-code
mapping:

```bash
kubectl -n <namespace-you-discovered> exec deploy/<deployment-you-discovered> -- python -c "
import os,sys; sys.path.insert(0,'/app/apps/api')
from isaac_api import db_migrate; print(db_migrate.migrate(os.environ))"
```

The placeholders are placeholders. Substitute what you discovered in step B; do not invent them.

**The application must not be changed to auto-migrate.** It never runs migrations, by design.

## E. Postchecks

```bash
# 1. UNCHANGED from precheck 4. This is the one that matters.
psql -c "SELECT count(*) AS records_after FROM records;"

# 2. UNCHANGED from precheck 5.
psql -c "SELECT count(*) AS experiments_after FROM isaac_experiments;"

# 3. Columns and constraints.
psql -c "\d isaac_runs"

# 4. Index on (experiment_id, ordinal, run_id).
psql -c "SELECT indexdef FROM pg_indexes WHERE tablename = 'isaac_runs';"

# 5. Version recorded.
psql -c "SELECT version, applied_utc FROM isaac_schema_migrations ORDER BY version;"

# 6. Row count.
psql -c "SELECT count(*) FROM isaac_runs;"

# 7. Idempotence: a second invocation must apply nothing.
python scripts/db_migrate.py --apply

# 8. Application health, through the hosted UI:
#    /api/health -> experiment_storage {backend: "postgres", durable: true, state: "durable"}
#    create an experiment; confirm it works and still lists in My Experiments.
```

**Expected `isaac_runs` row count: 0**, because no application code writes this table in the build
described here. **Verify this against the code as it actually stands rather than assuming it** — a
later slice will introduce the run write path, and if that has already merged, a non-zero count is
correct and expected. Check before treating a non-zero count as a fault.

**The migration has failed its own contract if** the count in step 1 differs from precheck 4 by any
amount in either direction, or step 2 differs from precheck 5.

## F. Rollback — do NOT do this automatically

**Do not roll back a successful additive migration merely to "undo" it.** The table is additive and
inert while nothing writes it, and the application already tolerates a configured-but-unmigrated
database.

Roll back only if: a count in postcheck 1 or 2 moved (**understand the cause first** — rollback does
not restore either table); the application fails to start or serve reads against the migrated
database; or a defect is found in the table shape that cannot be fixed forward.

```bash
psql -v ON_ERROR_STOP=1 -f apps/api/isaac_api/migrations/0002_runs.rollback.sql
```

That file is `BEGIN; DROP TABLE IF EXISTS isaac_runs; DELETE FROM isaac_schema_migrations WHERE
version = '0002_runs'; COMMIT;` — one transaction, so "dropped" and "unrecorded" cannot disagree.

**ORDER MATTERS if both migrations are ever rolled back: `0002` FIRST, then `0001`.**
`0001_experiments.rollback.sql` drops `isaac_experiments` *without* `CASCADE`, and `isaac_runs`
references it, so rolling back `0001` first **fails**. That is a safe failure — nothing is destroyed —
but do not discover it under pressure.

## G. Return evidence

The sanitized report described at the end of this prompt.

---

# WORKSTREAM 2 — the authoritative identity source

## Do not re-answer what is already answered

A temporary probe ran once against the hosted deployment on 2026-08-02 and **has since been removed**
(the route returns 404 and a test pins that). **Do not re-add it.** Full record:
`docs/identity-trust-contract.md` §6A. What it established:

- All seven probed headers arrived at the application. **ISAAC consumes none of them today.**
- For `X-authentik-username`, `-uid`, `-email`, `-name`, `-groups`: the edge **supplied the value and
  did not append** a planted client canary — no second header line, no coalescing on `,` or `|`.
  **It does not follow that the client's copy was removed:** a copy joined on another separator, or
  truncated / re-encoded / case-folded / quoted, produces the same signature. §6A.1 names the
  scenarios.
- For **`X-authentik-entitlements` and `X-Isaac-Edge`, the client's own planted value arrived
  untouched.** So `X-Isaac-Edge` cannot witness that a request traversed the edge — the one job its
  name implies. ISAAC treats both as permanently disqualified from any security decision.

**Dean has already established that the username is the canonical user identity.** That is settled.

## The actual open question

**What trusted, server-side, edge-derived source gives the application that username safely?**

Inspect the actual ingress / Authentik / proxy configuration in `ISAAC-DOE/isaac-k8` (which Krish's
repository does not contain and cannot read) and determine:

1. The **exact** header or claim carrying the username, and **which layer injects it**.
2. Whether arbitrary client-supplied copies are **stripped or overwritten** — from the configuration,
   not from the single observation above. What does the `auth-response-headers` annotation actually
   list? (**Q1** asks for the complete injected set; the probe only tested a fixed seven-name
   allowlist, so a header arriving under an unlisted name remains entirely unknown.)
3. Whether the application receives it **only after** authentication completes.
4. Whether it survives the `/krish` deployment path specifically.
5. **Q4 — the one the probe could not touch:** can any workload in the cluster reach the
   `metadata-assistant` Service **directly**, bypassing the ingress and therefore Authentik? Nothing
   observed so far proves the caller was authenticated at all.
6. How the application should **fail closed** when the trusted identity is absent.
7. Behaviour for **service / agent principals** as distinct from human users.
8. Whether **MCP identity can use the same model** (see workstream 3).

**Do not endorse a generic `X-Forwarded-User` or similar without inspecting the actual edge
configuration.** Directly-forwarded in-cluster headers are already recognized as unsafe here.

## The shape of the answer we need

> For normal authenticated web requests, ISAAC may trust `<exact source>` after `<exact trusted
> proxy>`, because user-supplied copies are `<stripped / overwritten>`. The canonical application
> actor is the username in `<claim/header>`. Direct or non-edge requests must not gain an actor from
> arbitrary forwarded headers.

Return **exact configuration evidence** — the manifest, annotation or policy text, quoted, with its
file and location.

## Decisions, by existing identifier — quote these numbers in your reply

All are in `docs/identity-trust-contract.md` §7. **Do not renumber them and do not invent new ones**;
they have already been sent externally.

| # | Question |
|---|---|
| **Q1** | The *complete* list of header names the outpost injects (partially answered — the probe tested only seven). |
| **Q4** | Can an in-cluster workload reach the Service directly, bypassing Authentik? |
| **Q5** | Is an Authentik/SLAC **username** non-reassignable across rename, departure and rehire? If not, what mapping should ISAAC hold? |
| **Q6** | Are forwarded **group** claims authoritative for in-app authorization, or descriptive only? |
| **Q7** | The complete set of Authentik groups ISAAC should recognise, and their mapping to app roles. |
| **Q8** | On session expiry, what does a browser XHR to `/krish/api/*` actually receive — 302, 401, or an HTML login page — and should the app treat all three identically? |
| **Q9** | Is there a logout URL the app may link to, and should it be surfaced? |
| **Q10** | Should the app server-stamp `attribution.uploaded_by` from the forwarded identity, and from which claim? |
| **Q17** | Is `X-authentik-uid` **permanent and non-reassignable** across rename, departure, deactivation and rehire? (Presence is observable; lifecycle is not.) |
| **Q18** | Will the infrastructure strip client-supplied `X-authentik-entitlements` and `X-Isaac-Edge`, or should ISAAC treat them as permanently untrusted? |
| **Q25** | Does the Q10 answer extend to ISAAC's **own** actor columns — the actor on a per-Run field override, on a submission, and on each row of a revision history? These are ISAAC-owned append-only audit rows, not a mutable upstream metadata field, so a wrong principal misattributes a scientific decision and cannot be corrected by re-editing. If the answer is "same claim, same stamping", say so; ISAAC will not infer it from Q10. |

**Q5 and Q17 are institutional lifecycle facts that no observation can settle** — they need a person
who knows how SLAC accounts behave, not a probe.

**If a small infrastructure or application change is required, prepare the exact patch and state who
owns it.** Do not modify Dean-owned infrastructure unless Dean's own instruction to you explicitly
authorizes that.

---

# WORKSTREAM 3 — MCP hosted reachability and authentication

## The architectural fact this workstream must preserve

**MCP is one-way.** A scientist's Claude client calls ISAAC's tools. **Connecting MCP does NOT give
ISAAC native inference** — that is workstream 4. These two are routinely conflated and
`docs/ai-integration-decision-packet.md` §1.1 exists to keep them apart.

**Current blocker:** Authentik forward-auth is an interactive browser flow and is not usable by an
external, non-interactive MCP client.

No MCP server exists yet. Krish is building one locally regardless of this answer; what is blocked is
a *hosted, connectable* endpoint.

## Reachability — decision **D1**

Inspect the actual hosted routing configuration and answer:

- May a dedicated MCP endpoint be reachable from a scientist's own machine over the public internet —
  yes or no? (Claude Code, Claude.ai and the Messages API all connect **from the client side**; an
  endpoint reachable only inside SLAC's network cannot be added as a connector at all.)
- If yes: on what hostname and path, with what rate and source restrictions?
- Can it coexist safely with the current `/krish` web deployment?

Note that **Q4** (workstream 2) is directly relevant: if an in-cluster workload can already reach the
Service bypassing Authentik, that changes the threat model for any new path.

## Authentication — decision **D2**

Which mechanism is **institutionally acceptable and implementable**? Evaluate at least:

- an ISAAC-hosted OAuth-compatible MCP path;
- an edge- or infrastructure-issued scoped bearer token;
- another SLAC-approved non-interactive service/client authentication mechanism.

**Do not invent an Authentik bypass. Do not weaken web authentication.**

## Identity and scopes

How does an authenticated MCP identity map to the canonical username (workstream 2)? MCP must be
**least privilege**.

**Final Submit must never be exposed through MCP.** That is an invariant, not a default: submission
of a scientific record is a scientist's explicit act. Enforcement is server-side; MCP tool
annotations are not a gate.

## Return

Recommended design; exact infrastructure changes; exact application changes; secrets or credentials
required and who would hold them; whether Dean can authorize them now; and any remaining blocker that
needs policy input rather than a technical decision.

---

# WORKSTREAM 4 — native AI and transcription

**Keep this separate from workstream 3.** "Native ISAAC AI" means the ISAAC *server* calls a model.
"Transcription" means audio or text reaches an approved ASR provider. Neither is MCP.

Measured current state, so nothing here is assumed: the application has **no model provider, no ASR
client, and no outbound HTTP** in its runtime backend or truth core. The assistant that ships today is
deterministic, with no model behind it, and the app already tells users so in writing.

**Establish what is technically available; do not invent policy.** Where institutional policy requires
a human decision by Dean, Angel, or a data-governance owner, **say so explicitly** — that is a
complete and useful answer.

Return a concise decision matrix against these existing identifiers
(`docs/ai-integration-decision-packet.md` §5). **Do not renumber D1–D9** — a previous proposal shifted
them by two, which would have silently redirected an answer about *retention* onto *which provider*.

### Native model

| # | Decision |
|---|---|
| **D3** | Which model provider? Are any approved provider candidates already available institutionally? |
| **D4** | The API credential — who holds it, and where does it live? What secret-storage mechanism is available? |
| **D5** | Billing — which project or account owns the spend? |
| **D6** | Approved egress — what data may leave SLAC, and to whom? What network egress exists from the pod? |
| **D7** | Retention — what does the provider retain, and for how long? (Needs the provider's terms in hand.) |
| **D8** | Data policy — what may be sent at all? Scientific-data handling constraints. |

### Transcription

| # | Decision |
|---|---|
| **D9** | Which ASR / transcription provider, if any is approved? May audio leave the browser, the server, or SLAC at all? Who owns the credential and the billing? What is retained? Is raw-audio storage permitted? |

**No raw file storage decision is required right now.** ISAAC uses the schema's native asset
references — URI, media type, SHA-256, provenance — and does not need ISAAC-owned bytes today. Do not
raise a storage request on ISAAC's behalf.

**Constraints while investigating:** create no paid accounts, incur no charges, and send no scientific
data anywhere.

---

# WHAT TO RETURN

Structure the reply as four sections plus a summary. Distinguish clearly, throughout, between **what
you performed**, **what you observed**, **what you inferred**, and **what needs a human decision**.

## 1. Workstream 1 — operator report (sanitized)

- namespace and deployment actually used
- migration version applied
- `records` count **before and after**
- `isaac_experiments` count **before and after**
- the `isaac_schema_migrations` rows
- `isaac_runs` schema and index, as read back from the server
- `isaac_runs` row count
- second-invocation idempotence result
- application health afterwards
- any errors encountered
- whether rollback was required, and if so why

**No secrets, no connection strings, no record contents, no personal data.**

## 2. Workstream 2 — identity

The concrete trust contract in the shape given above, with quoted configuration evidence, plus an
answer or an explicit "needs a human / needs policy" against **Q1, Q4, Q5, Q6, Q7, Q8, Q9, Q10, Q17,
Q18, Q25**.

## 3. Workstream 3 — MCP

Recommended design and exact changes, plus **D1** and **D2**.

## 4. Workstream 4 — native AI and transcription

The decision matrix, plus **D3, D4, D5, D6, D7, D8, D9**.

## 5. Summary

Split every item into:

- **actions you performed** using Dean's authorized environment;
- **decisions Dean himself must make**;
- **decisions requiring Angel or scientific/policy input**;
- **things already approved by Krish** (workstream 1 only);
- **anything you refused to guess**, and what would unblock it.

A **partial return is useful.** These workstreams are independent. Workstream 1 does not wait on 2–4,
and application development continues in parallel and is blocked on none of them.

## One scientific appendix, for routing only

Six fields — `system.configuration.detector_model`, `monochromator_crystal`,
`spectrometer_geometry`, `n_scans`, `proposal_id`, `session_id` — need a scientist to say whether each
belongs to the **Experiment** (entered once, inherited by every Run) or to the **Run** (recorded per
Run). This is scientific semantics, **not** an infrastructure question, and ISAAC's own analysis
reaches no evidence-backed recommendation for any of the six. Full analysis, including what each wrong
answer costs in both directions: `docs/run-scope-decision-packet.md` §4. **Please route to Angel or
the appropriate domain owner; no infrastructure work is implied.** Nothing in the application is
blocked on it.
````
