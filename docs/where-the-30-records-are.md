# Where the 30 production-derived records are, and how Krish can access them

**Created:** 2026-08-01 · **Status:** LIVE · **Verdict:** **Database-Only Records**

This document answers one question directly, so it never has to be re-derived: *where are the 30
production-derived ISAAC records, and what can Krish actually do to see them?*

Authority, in precedence order: Dean's committed guide
[`docs/postgres-test-db-guide.md`](postgres-test-db-guide.md) @ `b746b1a`; the canonical repository at
`d7010f9`; the vendored schema; tests. Nothing here is inferred without being labelled as inferred.

---

## The short answer

**The 30 production-derived records are not stored in GitHub.**

Not in the tracked tree, not anywhere in git history, not in Git LFS, not in a release asset, not in
the container image, and not in any fixture. No script in this repository has ever read, written,
imported, or exported them. The searches that establish this are in §6.

They exist in exactly one place: **a PostgreSQL database inside the SLAC cluster.**

| Property | Value | Source |
|---|---|---|
| Database | `metadata_assistant` | guide `:17-18` |
| Cluster | in-cluster CloudNativePG, Postgres 18 | guide `:17-18` |
| Host | `isaac-psql-rw.isaac-psql.svc.cluster.local:5432` (cluster-internal DNS) | guide `:43-44` |
| Namespace | `isaac-psql` | guide `:91` |
| Table | `records` — one row per record | guide `:100-117` |
| Record payload | `data JSONB` — the complete ISAAC v1.05 JSON document | guide `:114-117` |
| Key | `record_id CHAR(26)` — a ULID, blank-padded, needs `.strip()` | guide `:114-117`, `:128-130` |
| Owning role | `metadata_assistant` (least-privilege login, owns the DB and its `public` schema) | guide `:17-18`, `:136-140` |

**How they were seeded.** Dean seeded them, outside this repository: *"Seed data: the 30 earliest real
records from production (by `created_at`), plus the full production `vocabulary_cache` contents so
vocabulary validation can run against real terms"* (guide `:23-25`). **No seed script, dump, migration,
or importer exists in this repo** — proven in §6.4. There is no source import artifact here.

**They are copies.** The originals remain in the **production ISAAC records database — the
`isaac-ai-ready-record` portal's DB** (guide `:19-21`). `metadata_assistant` is isolated from it: the
role's only pg_hba grant is into its own database, *"so it cannot reach the production records DB at
all"* (guide `:26-30`).

---

## How Krish can access them

Two paths exist today. Neither is the ISAAC app, and that is deliberate.

### Path 1 — the existing ISAAC portal (recommended first)

The 30 rows were copied *from* production, and the mirrored schema is *"identical to the production
ISAAC records database (the isaac-ai-ready-record portal's DB)"* (guide `:19-21`). The portal is the
sanctioned UI for exactly this data, already authenticated by the same Authentik SSO with the same
`admin`/`researcher` group policy (`docs/developer-guide-k8s.md:58-59`), and already audited by its own
`portal_access_log` / `api_requests` tables.

- **Governance risk:** lowest. No new surface, no new data movement, no decision required.
- **Effort:** zero. It already exists.
- **Caveat, stated because it is not proven:** that these specific 30 rows are individually locatable in
  the portal UI *follows* from "seeded from production" plus "schema identical", but **Dean never says
  it**, and this repository does not record the portal's URL. Treat as inferred.

### Path 2 — `kubectl port-forward`, only if Krish already holds a SLAC cluster context

Dean documents this himself: *"Only relevant if you already have a SLAC cluster context. This is a
convenience for poking at the database by hand"* (guide `:83-96`).

```bash
kubectl port-forward -n isaac-psql svc/isaac-psql-rw 5432:5432
```

then export the five `PG*` variables against `localhost`, with the password taken from the
`metadata-assistant-db-app` Secret in the `metadata-assistant` namespace.

**This is the only path that would let Krish read the record content itself.** Two things must be said
plainly about it:

1. **The repository contains no evidence that Krish holds a cluster context, and none of how to obtain
   one.** Cluster, secrets, and manifests are owned by the ISAAC/SLAC team through the `isaac-k8`
   GitOps repo (`docs/infrastructure-ownership.md:21-23`; `docs/developer-guide-k8s.md:87-89`). Whether
   Krish gets a context is therefore Dean's decision, not a product decision.
2. **The project rule forbidding this path applies to the automation, not to Krish.**
   `docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52` blocks *any connection
   originating from a laptop or from CI*, and blocks the agent from requesting a kubeconfig,
   port-forward, or Secret. That is a constraint on this agent. It does not restrict what the human
   database consumer may do with access his institution has granted him.

### What is NOT a path: the hosted app

`GET /krish/api/runtime/database/recon` is shipped and is the supported *in-app* route, but it returns
**aggregates only** — counts, counts by type and domain, validation totals, gate results. It will never
show a record. The procedure for running it is already written at
[`docs/hosted-qa-checklist.md`](hosted-qa-checklist.md) Part 1.

### The distinction that is easy to get wrong

Dean closed **hosted display**, not Krish's own inspection.

> *"Writing to this database is unrestricted. Rendering its rows in the hosted app is not, because the
> seeded records are production-derived."* — guide `:151`
>
> Hosted per-record display is *"closed by default pending an explicit visibility decision."* — guide `:154`

Krish opening a psql session over a port-forward is not what that sentence forbids. Building a record
viewer into `/krish` is.

---

## Access options, compared

| # | Option | Data exposed | Auth | Auditability | Governance risk | Effort | Authorization required |
|---|---|---|---|---|---|---|---|
| 1 | **Existing portal** | full per-record, in its sanctioned home | Authentik SSO, `admin`/`researcher` | portal-owned (`portal_access_log`, `api_requests`) | **lowest** | **zero** | none, if Krish is already in the group |
| 2 | **Dean-provided DB viewer/tooling** | unknown | unknown | unknown | unknown | n/a | **no evidence any such tool exists** — worth one question to Dean |
| 3 | **Bounded read-only viewer in this app** | per-record fields | Authentik edge | would need new audit | **highest** — precisely what Dean closed | large | **G2 — Dean. NOT AUTHORIZED** |
| 4 | **Sanitized manifest** (ids and/or titles) | per-record content by definition | Authentik | as the endpoint | **high** — a ULID list *is* per-record data; excluded by the §4.2 rule | small | **G2 — Dean** |
| 5 | **Dean-approved export** | whatever Dean chooses | out of band | Dean's | depends on Dean's terms; the file is then private and must never be committed | trivial | **Dean, explicitly**, plus a data-classification decision (readiness plan `:62-63`) |
| 6 | **No per-record access in the app** | aggregates only | Authentik | endpoint `outcome=`, leak-scanned, allowlist-projected | **lowest in-app** | zero — shipped | **the current authorized state** |

**Recommendation:** try option 1 before anything is built — it answers "what do these records look
like?" at no governance cost. Ask Dean about option 2. Options 3–5 all reduce to gate G2 and none may
be started before it is answered.

---

## What Dean must approve before per-record access exists in the app

Gate **G2**, recorded verbatim in
[`2026-07-31-baseline-completion-matrix.md`](superpowers/plans/2026-07-31-baseline-completion-matrix.md) §5:

> *"May the hosted app display per-record fields from `metadata_assistant` — titles, scientific values,
> evidence, full JSON — and if so to which audience and at what granularity?"*

Until answered, a real-record adapter, list, detail, evidence view, or export is **not deferred by
preference — it is withheld by the data owner.** Database *reachability* is not display authorization,
and the guide says so directly at `:149-162`.

---

## What must never be copied into Git

- Any row of `metadata_assistant.public.records`, in whole or in part.
- Any record id, title, or scientific value from it — including in a test fixture, a doc example, a
  commit message, a CI log, or a memory-snapshot entry.
- Any dump, export, or manifest derived from it.

This is already enforced structurally, and the enforcement should not be weakened:
`Dockerfile:4-9` declares the `COPY` list an explicit allowlist and states that `examples/`, `drafts/`,
`records/`, and `graphify-out/` *"must NEVER be added"*. The only data files in the image are the public
vendored schema, the synthetic fixtures, and the sanitized memory snapshot.

Putting these 30 rows in Git would move production scientific data into a repository, an image, CI
logs, and every clone at once. There is no GitHub path because there should not be one.

---

## The "30/30" claim — resolved as operator testimony (superseding this section's earlier finding)

A separate question was asked: *what evidence exists that the reconnaissance scan ran and reported
30 records, all passing schema?*

### The earlier finding, kept because it was wrong in an instructive way

This section previously concluded: *"There is one prose sentence, no durable artifact, and the same
working tree contradicts it in eight places"*, and directed that the 30/30 figure not be repeated. It
enumerated 8 statements across 3 files, listed below unchanged.

The claim under examination, at `2026-07-31-baseline-completion-matrix.md`, added by docs-only commit
`7e9a387` (1 file, +126/−7, no data artifact):

> merge `ceea656` was published as image `v0.0.38` … hosted `/krish/api/health` was observed reporting
> `ceea656`, and the Slice 2A reconnaissance **has run against the real database** … it **reported zero
> schema drift (30/30)**.

The 8 statements, as enumerated then (line numbers are as-of that enumeration and have since shifted
where the statements were corrected in place):

| Location | Text | Last written |
|---|---|---|
| matrix §0, "A second finding" | "code reading, not a runtime observation, and **the scan has never run**" | `a911b8c` |
| matrix §4.3, constraint 1 | "the actual row count is **unobserved** — the scan has never run" | `a911b8c` |
| matrix §7.2, item 5 | "**The real database has never been contacted. No scan has ever run.**" | `a911b8c` |
| matrix §"State after the baseline-restoration slices" | "**No hosted rollout has been observed** — see G1" | `a911b8c` |
| matrix §2.2 | every baseline-required database row reads `Runtime-verified: no` | ≤ `a911b8c` |
| same file §5 | G1 still listed **open** | ≤ `a911b8c` |
| `docs/hosted-qa-checklist.md:11`, `:157` | "The real database has never been contacted; no scan has ever run." | `a911b8c` |
| `apps/api/isaac_api/db_recon.py:19-21` | "this module has **never been run against any database** … Do not cite its output as an observation until then." | `e7fd755` |

### Why that finding does not hold — the dating check nobody ran

**Every one of the eight predates the image the scan was run against.** `a911b8c` is dated
2026-07-31 18:17:27 −0700 and `git merge-base --is-ancestor a911b8c ceea656` confirms it is an
**ancestor of `ceea656`** — the merge cut 41 minutes later at 18:58:48 that became image `v0.0.38`.
`e7fd755` is dated 2026-07-31 04:27:45 −0700, roughly **21 hours before** the run
(`git log -1 --format='%h %ad' --date=iso -S 'never been run against any database' -- apps/api/isaac_api/db_recon.py`).
None has been updated since.

They are therefore **pre-run status markers, not post-run observations**. An unmaintained status
marker cannot be evidence that an event did not occur; it records only that nobody edited the file.
Counting eight of them as eight independent contradictions compounded a single stale fact eightfold.

**And "no durable artifact" was guaranteed in advance.** The endpoint holds its result **in process
memory only** — a deepcopy under a TTL lock (`apps/api/isaac_api/routes.py` ~3698-3721) — discarded on
pod restart, never written to disk. The absence of an artifact was going to be true whether or not the
scan ran, so it discriminates nothing.

### The established status

> The deployed pod contacted the database at least once. The scan was observed by Krish in an
> authenticated session against image `v0.0.38` (merge `ceea656`), and its result — no leaks, all four
> frozen allowlists matched, zero schema drift, 30/30 — is **authenticated operator testimony, dated
> and release-tagged, with no committed artifact because the endpoint is designed to produce none.**
> The scanning logic and the schema are unchanged at HEAD, so the result still describes the current
> release. It is **not** "verified" — testimony is not a re-checkable record — and equally **not**
> "never happened".

**What raises it above assertion.** Krish independently restated the result at **field level**, mapping
one-to-one onto `_DB_RECON_INTEGRITY_KEYS` (`apps/api/isaac_api/routes.py:3175-3187`): `rows_before`
and `rows_after` both 30, `rows_modified` 0, `dml_statements_issued` and `ddl_statements_issued` both
0, `full_schema_fingerprint_match`, thirty records passing v1.05, zero validation issues, no prohibited
content. **Commit `7e9a387` named none of those six integrity fields**, and no other committed document
does either — so the detail cannot have been read off a document.

**No rerun is warranted.** `git diff --stat ceea656..7a9f15d -- apps/api/isaac_api/db_recon.py
schema/isaac_record_v1.json src/isaac_records/` is empty (byte-identical), and
`git diff ceea656..7a9f15d -- apps/api/isaac_api/routes.py | grep -c '_DB_RECON'` returns 0. Only
`app_commit` in the response would differ.

**The distinction to hold.** *"No database connection was opened during this discovery session"* is
**true**. *"The deployed database has never been contacted"* is **false as written** and must not be
repeated.

**What remains open.** Gate **G1** is **narrowed, not closed**: the substantive question is answered,
and what is still owed is purely evidentiary — paste the sanitized JSON back per
[`docs/hosted-qa-checklist.md`](hosted-qa-checklist.md) Part 1 so the result becomes an artifact rather
than testimony. The 30/30 figure **may** now be cited, provided it is labelled as testimony against
`v0.0.38` and never as a verified measurement.

---

## Evidence appendix

### 6.1 Tracked files
`git ls-files records/ drafts/` → `.gitkeep` only. `git ls-files examples/` → `examples/README.md`
only (`.gitignore:6-7` = `examples/*` + `!examples/README.md`); the working-copy contents are four
generated synthetic files from `scripts/make_synthetic_examples.py`.

### 6.2 Git history
`git log --all --diff-filter=A --name-only` → 509 distinct paths ever added. Differenced against
`git ls-files` (`comm -23`), only **12** were ever added and later removed, all code/config refactors (e.g.
`src/isaac_records/validator.py`, `railway.json`, `vercel.json`). No record dump, no `.sql`, no export.

### 6.3 ULID scan
32 distinct 26-character candidates across the tree, every one self-evidently fabricated:
`01JQZ0SYNTHXANESDEMO000000` (**84** matching lines — `rg -c … -g '!node_modules' -g '!docs/where-the-30-records-are.md'`, excluding this file, which now quotes the string), `01SYNTHXANESSEED00000000{01..05}`, `01JQZ0FAKEREC0N*`,
`01MISSINGRECORD00000000000`, `01EXPERIMENTA/B*`, plus 10 in the vendored public upstream fixtures.

### 6.4 Seeders and migrations
`rg -i 'INSERT INTO|CREATE TABLE|alembic|migration'` returns only: the DDL **quoted in Dean's guide**
(`:101`), negative-test strings asserting the read-only guard *rejects* them
(`tests/test_db_recon.py:385,390`; `apps/api/tests/test_db_recon_endpoint.py:546,550,594`), and prose.
`scripts/` holds 6 files, none DB-related except the unexecuted `db_recon.py`.

### 6.5 Fixtures
`tests/fixtures/synthetic/README.md`: *"synthetic intake artifacts — safe to commit, never real data …
fictional people (Ada Lovelace, Grace Hopper), a made-up 2099 SSRL beamline session."*
`tests/fixtures/official/*.json` are copied verbatim from the **public** upstream
`ISAAC-DOE/isaac-ai-ready-record` `examples/` directory (`schema/PROVENANCE.md`; upstream confirmed
`"visibility": "public"` via `gh api`).

### 6.6 LFS and releases
No `.gitattributes` exists, so no LFS pointers are possible. `gh release list` and
`gh api .../releases` → empty. The 39 semver tags are build-workflow output and carry no assets.

### 6.7 Docker build context
`Dockerfile:32-37`, `:41` COPY allowlist: `pyproject.toml`, `src/`, `apps/api/`, `schema/`,
`tests/fixtures/synthetic/`, `scripts/check_graphify_freshness.py`, and the built SPA.

### 6.8 Reconnaissance code
`apps/api/isaac_api/db_recon.py` reads `record_id, record_type, record_domain, data` into memory to
validate (`Q_RECORDS_PAGE:1064`) and emits only counts, schema-masked structural paths, enum-recognised
labels, and salted truncated digests, behind nine fail-closed gates and a final leak scan.
`routes.py` projects a strictly narrower view through four frozen allowlists
(`_DB_RECON_DATASET_KEYS`, `_INTEGRITY`, `_DATABASE`, `_GATE`); an unlisted key raises and fails closed.
`_DB_RECON_RECORD_DISPLAY = "closed"` is surfaced in `/api/health` as `database.record_display`.
`runtime_records.py:1-5`: *"NO index, NO cache, NO database, NO service, NO persisted state."*

### 6.9 Proven vs. inferred

**Proven:** absence of the records from tracked files, full history, LFS, releases, and the image;
absence of any seeder or importer; the database name, host, namespace, table, and seed provenance (from
Dean's committed guide); the recon code's read-only aggregate-only behaviour; the in-memory-only
lifetime of its result; the absence of a durable recon artifact; ~~the eight contradictions of the
30/30 claim~~ (**corrected 2026-08-01** — the eight exist as text, but all eight predate image
`v0.0.38` and are pre-run status markers, so they are *not* contradictions of a later event; see the
section above); the tag→commit mapping; that `db_recon.py`, `schema/` and `src/isaac_records/` are
byte-identical between `ceea656` and HEAD.

**Operator testimony, accepted but not re-checkable here:** that the recon scan ran against image
`v0.0.38`, returning no leaks, four matching allowlists, zero schema drift, 30/30, with
`rows_before == rows_after == 30` and zero DML/DDL; that hosted `/krish/api/health` reported `ceea656`.

**Inferred, flagged as such:** that the same 30 records are individually viewable in the production
portal; the portal's URL; whether Krish holds a SLAC cluster context (**note:** Dean's guide documents
`kubectl port-forward` as an option for whoever already holds one — that is authorization for such a
person, not evidence that Krish is one).

**Unknown and not guessed:** which image `/krish` is currently running (no Flux `ImagePolicy` exists in
this repository), and in particular whether `v0.0.39` has rolled; ~~whether the recon scan actually
ran~~ (**corrected** — see above); the actual row count in `records` as an artifact-backed measurement,
as distinct from the testimony figure of 30.
