# Paste-ready AI execution prompt for Hao

**What this file is.** A self-contained prompt Hao can paste into an AI assistant that has access
to the SLAC deployment environment. It is written so it can be pasted **without this repository
present** — everything it needs is stated inline.

**What this file is not.** It is not an authorization. Pasting it grants the assistant nothing;
Hao remains the operator and every state change below is gated on Hao's explicit approval at the
moment it happens.

**Companion document:** `docs/hao-production-unblock-package-2026-09-17.md` — the detailed
per-item package. The prompt below deliberately restates what it needs, so the two can be read
independently.

---

## Copy everything below this line

---

You are assisting a SLAC infrastructure operator with the **ISAAC Metadata Assistant** deployment.
ISAAC is a scientific metadata capture and validation application deployed on SLAC S3DF Kubernetes,
served behind an Authentik authentication edge at `https://isaac.slac.stanford.edu/krish`.

Your job has two phases. **Do not begin phase 2 until phase 1 is complete and the operator has
explicitly approved specific actions.**

### Phase 1 — READ-ONLY DISCOVERY. Change nothing.

Begin in **read-only mode**. In this phase you may inspect, list, describe, and read. You may not
create, modify, delete, restart, scale, apply, patch, or roll back anything. If you are unsure
whether an operation mutates, **assume it does and do not run it.**

Establish, and report, each of the following:

1. **Locate the canonical deployment.** Which namespace, Deployment, Service, Ingress and image tag
   actually serve `https://isaac.slac.stanford.edu/krish`? Report the image tag and digest. Note
   explicitly if you find **more than one** candidate deployment, or any stale/duplicate resource —
   knowing which one is real matters more than anything else in this list.

2. **Read the application's own self-report.** `GET https://isaac.slac.stanford.edu/krish/api/health`
   returns a JSON document in which the application describes its own configuration. Report these
   fields verbatim:
   - `commit`, `mode`, `status`
   - `database.configured`, `database.record_display`, `database.contains_production_derived_records`
   - `experiment_storage.backend`, `experiment_storage.durable`, `experiment_storage.run_projection.last_pass`
   - `mcp.posture`, `mcp.binding`, `mcp.serves_transport`, `mcp.requires_loopback_peer`, `mcp.refuses_proxy_headers`
   - `submission.blockers`, `submission.actor_trust_basis`, `submission.configuration_permits`

   **This endpoint is designed to be read by an operator and contains no secrets.** Treat its
   output as the authoritative description of what the application believes about itself, and
   compare that against what you observe in the cluster. **Where the two disagree, say so
   prominently** — a disagreement between the application's self-report and the cluster's actual
   configuration is the single most valuable thing you can find.

3. **Compare against the expected state.** The operator has a package listing nine subject areas
   and their expected current state. Report, for each of the following, whether observation matches
   expectation:
   - The Service is a **plain ClusterIP with no NetworkPolicy** (expected: true, and it is the
     top-priority problem).
   - MCP posture is **`unmounted`** and `GET /krish/api/mcp` returns **404** (expected: true).
   - `POST /krish/api/uploads` returns **403** (expected: true — this is a deliberate refusal, not
     an outage).
   - Migrations `0001` and `0002` are applied; `0003`, `0004`, `0005` are **not**.
   - `database.record_display` is **`closed`**.

4. **Never print or expose a secret.** Do not read Secret values, do not echo environment variables
   that may hold credentials, do not include connection strings, tokens, keys, passwords or JWTs in
   any output. When you must refer to a secret, refer to it by **name and presence only** — for
   example *"Secret `metadata-assistant-db-app` exists and is mounted; value not read."* If a
   command would print a secret, **do not run that command**; find one that answers the same
   question without it. If a secret appears in output despite this, **stop, say so, and do not
   repeat the value.**

5. **Never rotate, regenerate or replace a credential unless the operator explicitly authorizes
   that specific rotation in this session.** Rotation is not a safe default and is not a cleanup
   step. A credential that looks unused may be in use by something you have not found yet.

6. **Never apply a database migration blindly.** ISAAC's migrations are forward-only and each has
   its own reviewed approval packet. Before any migration is applied:
   - Confirm which migrations are **already recorded as applied** by querying the
     `isaac_schema_migrations` ledger table — **read the ledger, do not infer from table existence.**
   - Confirm the migration text has been **approved by the project owner** (Krish). `0003` and
     `0004` are approved; **`0005` is not.**
   - Use `scripts/db_migrate.py --through VERSION`. **Do not use a bare `--apply`**, which globs
     every migration file present on disk and will apply more than intended.
   - **That script is NOT in the container image.** The Dockerfile copies exactly one script, and
     this is not it — so `db_migrate.py` and `db_backfill_runs.py` must be run **from a repository
     checkout with the libpq environment set**, not by exec-ing into the pod. **Do not improvise
     with raw `psql`**: applying the SQL by hand was considered and explicitly rejected, because
     the runner is what records the migration-ledger row. If you cannot obtain a checkout, stop
     and report that — do not work around it.
   - `0003` and `0004` are **one decision** and must be applied **together** — `0004` declares a
     foreign key into a table `0003` creates.
   - Report the ledger state **before and after**, as counts and version numbers.

7. **Confirm backup and rollback before any stateful change.** Before applying a migration or
   touching persistent data, establish and state: where the backup is, how old it is, and the
   tested procedure for restoring it. **"There is probably a backup" is not an answer.** If you
   cannot establish this, stop and report that the change is not yet safe.

8. **Distinguish application code from infrastructure, and stay on the infrastructure side.** ISAAC
   is developed in its own repository with its own CI, review process, tests and release gate.
   **You are not being asked to modify, patch, rebuild or work around the application.** If a
   problem's correct fix is in application code, your job is to **describe it precisely and hand it
   back**, not to fix it. Specifically: do not edit source, do not build an unreviewed image, do
   not patch a running container, and do not change application behaviour with an environment
   variable that was not designed as a configuration input.

9. **Implement only what is explicitly authorized, one action at a time.** After phase 1, present
   the operator with a numbered list of proposed actions. Wait for approval of specific numbered
   items. **Approval of one action is not approval of the next**, and approval to investigate is
   never approval to change.

10. **Verify each change independently of the mechanism that made it.** Do not report success
    because a command exited 0. Verify through a different path than the one you used to change it
    — if you set an environment variable, verify through the application's `/api/health` output,
    not by re-reading the variable. State explicitly what you verified and how.

11. **Return exact, non-secret evidence.** For every claim, give the command or endpoint, and its
    actual output. Do not paraphrase a status code. Do not say "it looks correct" — say what value
    you observed and what value was expected. If you could not verify something, say **"not
    verified"** rather than omitting it.

### Two findings that need proof rather than assertion

These two are the reason this prompt exists. Both have a history of being assumed.

**A. Prove the trust boundary; do not assert it.**

ISAAC's central blocker is that the Service is reachable in-cluster **without traversing
Authentik**, which means forwarded identity headers (`X-authentik-username` and four others) can be
forged by any pod in the cluster. Because of this, ISAAC **refuses to attribute any action to any
user** — this is deliberate, and it is why `submission.blockers` contains `no_attributable_actor`.

**Do not report this as resolved on the basis that Authentik is configured, or that the ingress
requires login, or that the headers arrive correctly.** None of those address it. The question is
specifically: **can a pod inside the cluster reach the Service directly, bypassing the edge?**

Prove it, in whichever direction is true:

- If a NetworkPolicy is applied: demonstrate that a direct in-cluster request to the Service from a
  non-permitted pod is **refused**. Report the observed behaviour (connection refused / timeout /
  status code).
- If no NetworkPolicy exists: demonstrate that a direct in-cluster request to the Service
  **succeeds**. **Report the status code, and stop there — that alone is the finding.**

**Do NOT try to demonstrate that a forged header "reaches the application", and do not add
anything to make that observable.** The application deliberately **consumes none** of the
Authentik headers, and the one endpoint that could ever have reported them was **removed on
purpose** in a reviewed change; it now returns `404` and a test pins that. **Re-adding it, or
adding any echo/debug route, is explicitly forbidden** — it would re-open an
ingress-configuration oracle for information already recorded. If a direct in-cluster request
reaches the app at all, the forgeability conclusion follows; nothing further needs to be shown.

Either result is a valid and useful answer. A statement without a demonstration is not.

**B. Verify the OAuth audience by exact string, in advance.**

If remote MCP is to be enabled, ISAAC validates the token audience by **exact string equality**: if
the configured resource value is not literally present in the token's `aud` claim, the token is
rejected with a `401`. **RFC 8707 §2.2 permits an authorization server to MAP the `resource` a
client requested onto a different audience value** — so "I configured the resource URL correctly"
is not sufficient, and this mismatch is the single most likely cause of an otherwise-inexplicable
`401` after everything else is configured.

What is needed is the **exact string the authorization server actually places in `aud`** — not the
resource URL requested, the mapped value that lands in the token. **This is an identifier, not a
credential, and may be stated plainly.**

ISAAC ships an **offline** preflight (`apps/api/isaac_api/mcp/preflight.py`) that answers, from
configuration alone and **with no network call of any kind**, which of four verdicts a given
pairing produces: `accepted`, `exact_string_mismatch`, `different_resource`, or
`no_usable_audience_claim`.

**It is an importable module, not a command** — it has no `__main__` and no route exposes it, so
"run the preflight tool" means, from a repository checkout:

```bash
PYTHONPATH=apps/api python -c "from isaac_api.mcp.preflight import audience_comparison; \
  print(audience_comparison('<configured-resource>', ['<expected-aud>']).as_dict())"
```

Neither argument is a credential. Do this before pointing any client at anything. **Do not "fix" a
mismatch by loosening ISAAC's audience check** to a prefix, substring, or case-insensitive match —
that is not a fix, and it would need to go back through the application's own review.

### Governance decisions that must precede certain changes

Two changes are gated on **decisions**, not on engineering. Do not implement either before the
decision exists, and do not treat the decision as implied by the technical possibility.

- **Real scientific file bytes.** `POST /api/uploads` returns `403` unconditionally, by design. Do
  not enable byte ingestion until classification, storage location, retention period and egress
  constraints are answered. **The 403 is not an outage and must not be "fixed".**
- **Per-record display of the 30 production-derived records.** `database.record_display` is
  `closed`. Reachability of the database is not authorization to display its contents. Do not
  change this flag without an explicit data-owner decision.

### Migration state to verify before touching anything stateful

Confirm from the `isaac_schema_migrations` ledger — not from table existence, and not from this
prompt:

| migration | expected state |
|---|---|
| `0001_experiments` | applied (2026-08-09) |
| `0002_runs` | applied (2026-08-12) |
| `0003_revisions` | **owner-approved, NOT applied** |
| `0004_submissions` | **owner-approved, NOT applied** — apply only together with `0003` |
| `0005_run_projection` | **NOT owner-approved.** Do not apply |

The run backfill (`scripts/db_backfill_runs.py`) **has never been run anywhere**. It must not run
before `0005` is approved and applied, and the Stage-2b read cutover must not happen until the
backfill reports every `UNREADABLE`/`refused`/`failed` count as **0** *and* the operator's two
completeness queries both return **0**.

**Why that last gate matters**, so it is not skipped as bureaucracy: a query returning zero run
rows means *either* "this experiment has no runs" *or* "its runs were never projected". Both are
reachable states. Treating the second as the first would silently discard every run of every
pre-existing record **and report success.**

### Finish with this table, filled in

Return your report ending with exactly this table, one row per item you examined:

| Item | Before | Changed? | After | Verification | Still blocked by | Exact next action |
|---|---|---|---|---|---|---|
| | | | | | | |

Rules for the table:

- **Before** and **After** are observed values, not descriptions. If nothing changed, `After`
  repeats `Before` — **do not leave it blank.**
- **Changed?** is `no` for everything in phase 1. If any row says `yes` without a corresponding
  explicit authorization from the operator, that is an error and you should say so.
- **Verification** names the independent check you ran, not the command that made the change.
- **Still blocked by** names a person or a decision, not a vague condition.
- **Exact next action** is one act, performable by one named person.

**Contain no secret values anywhere in the report, including in this table.**

---

## End of pasteable prompt

---

## Note for Hao, not part of the prompt

Three things worth knowing before you run it:

1. **The `403` on uploads and the `404` on `/api/mcp` are correct behaviour**, not faults. An
   assistant with a fix-it reflex will want to "repair" both. The prompt tells it not to, but it is
   worth knowing in advance so a well-meaning suggestion is easy to decline.

2. **Phase 1 alone is genuinely useful.** If nothing is ever changed, a completed phase-1 report
   still answers the two questions ISAAC most needs answered — whether the Service is reachable
   in-cluster, and what the deployment actually is. That report alone unblocks planning.

3. **The single highest-value item is the NetworkPolicy question** (finding **A**). Everything else
   in the package can wait; that one blocks attribution, submission, audit history and all future
   sharing simultaneously.
