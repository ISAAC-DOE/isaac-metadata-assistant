# Experiment-Centered Groups and Collaborative Editing — Decision Record

**Created:** 2026-08-01 · **Status:** DESIGN LOCKED, IMPLEMENTATION BLOCKED · **Base:** `d7010f9`,
image `v0.0.39`

> ## Verdict: the model is decided; **exactly one** of ten slices is authorized, and it contains no collaboration semantics.
>
> This is not a scheduling preference. Nine slices are blocked on gates owned by Dean, and the block
> is *safety*, not politeness — §2 shows that building an identity reader before the trust boundary is
> known would create a spoofable authorization surface, not merely a premature one.

Authority order: Dean's committed guide → canonical repository → deployed runtime evidence →
authoritative schema → authorized database metadata → tests → durable docs.

Companion documents, which this one does not duplicate:
[`identity-trust-contract.md`](../../identity-trust-contract.md) ·
[`where-the-30-records-are.md`](../../where-the-30-records-are.md) ·
[`2026-07-31-baseline-completion-matrix.md`](2026-07-31-baseline-completion-matrix.md) §6.

---

## 1. The five findings that shape the design

Established by three parallel read-only workstreams at `d7010f9`. Each is evidenced; none is inferred.

### 1.1 Optimistic concurrency is already shipped — do not rebuild it

The prompt's Phase 6 "Required First Version" describes: client reads version *N* → submits against
*N* → server applies only if still *N* → otherwise a typed conflict. **That contract exists today.**

| Requirement | Status | Evidence |
|---|---|---|
| Records carry a version/revision token | **done** | `version_contract.py` — `VersionEnvelope{rev, updated_utc, version}`, one producer |
| Updates use optimistic concurrency | **done** | strong ETags; `If-Match` on every mutation |
| Stale updates rejected, never silently overwritten | **done** | **412 `stale_write`**, echoing `current_version`/`current_rev` so the client refreshes in one hop (`routes.py:238-244`, `:321`) |
| Missing precondition rejected | **done** | **428 `precondition_required`** — the one-release grace is retired, `_PRECONDITION_REQUIRED = True` is the single toggle point |
| Serialized apply | **done** | per-record `RLock` wraps `load → precondition → mutate → save` at the three version-gated sites (`routes.py:984`, `:1105`, `:1225`); a fourth `record_lock` at `:598` is the demo path — see §1.1a |
| UI explains conflicts; user can reload latest | **done** | `api.ts:268-358` parses the conflict payload; rendered by `GuidedCompletion.tsx:558-575`, `CsvReconcilePanel.tsx:92` and `AssistantPanel.tsx:676-685` (**not** `FetchStates`, which handles only 401/403/HTML-intercept) |
| No automatic merge of scientific values | **done** | `AssistantPanel.tsx:657-677` — on 412 it marks stale, explains, and performs **no retry and no merge** |
| Validation still runs after update | **done** | status is derived on read via an in-memory `export_draft` dry run (`workspace.py:14-16`) |
| **Every mutation attributed to a stable user identity** | **ABSENT** | no actor exists anywhere (§1.2) |
| **Audit event records who changed what, and when** | **PARTIAL** | `answer_log` records *what* and *when* (`workspace.py:245`; appended `routes.py:616`, `:1014`, `:1141`) but has **no actor field** |
| **Every state-mutating route is version-gated** | **NO — one gap** | `POST /api/demo/run` (`routes.py:524`) mutates persisted record state with **no `If-Match`**. See §1.1a |

**So the concurrency machinery is shipped, but the contract is not universal.** Two things remain:
attribution and audit (both need identity, both blocked), **and** the unversioned mutation path below
— which needs no identity at all and is therefore the one genuinely buildable item in this phase.

### 1.1a The one gap, and it is present-tense

`POST /api/demo/run` is not among the four `If-Match` sites (`routes.py:969`, `:1091`, `:1211`,
`:1383`). It calls `ws.create_experiment(..., id=target_id, ...)` under `ws.record_lock(target_id)`,
and `create_experiment` with an explicit id **constructs a fresh `Experiment` and `save()`s it**,
replacing the persisted title, source and draft.

The subtle part is the version token. `version_token()` is `f"{generation}.{rev}"`
(`workspace.py:285-287`), and `create_experiment` deliberately **preserves the on-disk `generation`**
(`:459`) so that repeated no-op demo runs do not churn ETags — the P36.8 idempotence guarantee.
Observed directly: the token was byte-identical (`"194b1839e67a2321.0"`) before and after a second
demo run. But a preserved generation with `rev` reset to 0 means **a content replacement can leave the
token unchanged**, and the token is what the precondition compares.

**Consequence.** A client that read a canonical demo id at `rev 0`, and writes after a concurrent
`demo/run` replaced that record's content, has its write **accepted against content it never
observed** — precisely the failure the 412 path prevents everywhere else. A client that had already
edited (so `rev ≥ 1`) is correctly caught, because the reset to `rev 0` changes the token.

**REPRODUCED 2026-08-01 — an earlier revision of this section hedged that no end-to-end lost update had
been demonstrated. That hedge was wrong and is withdrawn.** Independent review built the sequence with
the repo's own `test_strict_precondition.py` fixture; re-run independently by the orchestrator:

```
B0 seed:            version='79501e36e523dfb4.0'  content=326cb676ccea7231
B1 POST /answers with a matching If-Match          -> 200   (a real, confirmed user edit)
   after edit:      version='79501e36e523dfb4.1'  content=22084ee213d398ab
B2 POST /api/demo/run   (no precondition sent or accepted) -> 200
   after demo/run:  version='79501e36e523dfb4.0'  content=326cb676ccea7231
   token returned to the pre-edit value?  True
   the user's edit was destroyed?         True
B3 POST /answers with the ORIGINAL pre-edit token   -> 200 ACCEPTED
```

**Two demonstrated failures.** (a) `demo/run` silently destroyed a **committed** user edit — confirmed
answers, applied through the version-gated path, gone with no precondition and no signal. (b) The token
**ABA'd back to a previously-issued value**, so a precondition that must return 412 returned **200** —
defeating the `generation` nonce, which `workspace.py:255-258` says exists precisely so tokens *"differ
across a delete->recreate even when `rev` returns to 0 (ABA-safe)"*.

**Why the illustration first chosen here could never fire, recorded because it explains the wrong
hedge.** "Read at `rev 0` → demo replaces content → write accepted" cannot happen: on a pristine seed
`demo/run` reproduces **byte-identical** content on both canonical ids (measured). There is no
unobserved content *without an intervening edit*. The reachable path is one step further along.

**Why it matters now rather than later:** §1.2 establishes that all users share one workspace, so the
"two clients" in the scenario above are two real people on `/krish` today, not a hypothetical.

**Severity: CRITICAL** (upgraded from Important on reproduction). **Owner: orch. Classification: the
next authorized slice** — it is
application-owned, bounded, testable, needs no identity, no persistence, no infrastructure and no
real-record visibility. It is recorded as **W1** in the backlog.

### 1.2 There is no per-user dimension, so "My Experiments" is a misnomer

The experiment store is a filesystem path `workspace_root() / <experiment_id>` (`workspace.py:275`,
`:678`, `:702`). **No user segment exists at any level**, and `list_experiments()` returns every
directory. Combined with the `emptyDir` volume (`docs/deployment.md:29`), the consequence is:

> **Today, every authenticated user shares one experiment list, and it dies with the pod.**

This is the single most important product fact in the phase. Personal-vs-group scoping (Slice G) is
**not** an extension of an existing per-user model — there is no per-user model to extend. The first
time ISAAC has a "my", it will be because this phase created one.

### 1.3 Persistence gates nearly everything, and Dean has already answered part of it

Group-scoped experiments cannot live in an `emptyDir`: group data must outlive a pod restart or
membership is meaningless. So Slices E–I all depend on moving experiment state to Postgres.

**Dean's guide authorizes more of this than one might assume, in writing:**

- *"Writing to this database is unrestricted"* (`postgres-test-db-guide.md:151`)
- *"adding app-specific tables next to the mirrored schema is fine"* (`:136-140`)
- the `metadata_assistant` role *"owns the database and its `public` schema, so it can freely create
  and alter tables, indexes, sequences, and plpgsql trigger functions"* (`:138-140`)
- *"Nothing done here can affect production"* (`:26-30`) — pg_hba isolates the role entirely

**Read this carefully, because an earlier draft of this section over-claimed it and an independent
review was right to push back.** What Dean's guide removes is the **technical and role-level**
objection to storage location and schema ownership: the Postgres role *can* create tables, and Dean
says adding app-specific ones is fine. That is not the same as project authorization, for three
reasons:

1. **Two of the four quotes describe a role's grants, not a grant of project authority.** *"it can
   freely create and alter tables"* and the pg_hba isolation statement are capability descriptions.
   Only *"adding app-specific tables next to the mirrored schema is fine"* is genuinely permissive.
2. **`:151` is quoted out of its rhetorical function.** It sits under *"Displaying record content"*
   and exists to set up the contrast in its own next clause (*"Rendering its rows in the hosted app is
   not"*). Lifting it as a standalone migration authorization is the move its structure guards against.
3. **This repository independently blocks it, separately from Dean.**
   `2026-07-24-phase-37-readiness-plan.md:48-52` — *"Still blocked, unchanged: … writes of any kind
   (DML, **DDL**, …); a PostgreSQL-backed record repository"*. `CLAUDE.md` §15 lists *"durable
   persistence / a PostgreSQL-backed record repository / any database write"* as NOT authorized.
   **Dean's role grants and this project's authorization are two different gates.** Clearing one does
   not clear the other.

**So: of the six approvals this document proposes as a pre-migration checklist (§4), Dean's guide
removes the technical objection to two — storage location and schema ownership — and *no* project-level
gate is cleared by it.** ~~Storage location is additionally **contingent on Q12** (§4 option C): if a
portal identity service already owns users and groups, option A is the wrong target entirely.~~
**Resolved 2026-08-01: Q12 is answered "No"** — direct audit of the public upstream source found no
users/groups/memberships model anywhere (trust contract §5.1), so option A is the right target and this
contingency is discharged. Migration process, backup/retention, identity source, and group
administration policy are untouched.

The practical guidance, stated without the earlier overreach: **do not present Dean's guide as
migration approval, and do not re-ask him whether the role may create tables — he has answered that.**
Ask him the four open questions, and clear the project-level gate separately.

### 1.4 The schema already owns attribution — and the app has never used it

`schema/isaac_record_v1.json` (v1.05) defines `/attribution`:

- `uploaded_by` — *"Authenticated identity that submitted this record. Set by the server; any client
  value is overwritten."* The block description adds: *"SERVER-STAMPED from the authenticated identity
  at ingestion … (tamper-proof attribution). **Decided by D. Sokaras 2026-06-15.**"*
- `contributors[]` — `name`, `role`, `affiliation`, `orcid`, `email`, `notes`

~~Verified: `rg "uploaded_by" src/ apps/ tests/ scripts/` → **zero matches**; only 2 occurrences
exist, both inside the schema JSON.~~ **CORRECTED 2026-08-03.** The grep was accurate; the conclusion
drawn from it — that the field was inert — was **false**. `export.transform` copied the entire
`attribution` block, so a draft-authored `uploaded_by` reached the exported record and passed
official validation **without any code naming the field**, which is precisely why the grep found
nothing. "Verified" was doing work the command could not do. It is now refused fail-closed; see
[`docs/identity-trust-contract.md`](../../identity-trust-contract.md) §"Two consequences" item 1.
`attribution` is **optional** (not in the root `required` list).

Two consequences:

1. **Collaboration attribution does not need a home outside the record.** `uploaded_by` is the
   schema-blessed slot, designed for exactly this, by the schema's own author.
2. **`contributors[].role` cannot double as an authorization role.** Its enum is
   `data_owner | performed_measurement | performed_analysis | curated_record` — *scientific
   contribution*, not access control. Reusing it would be a schema-semantics error. Authorization
   roles must be a separate vocabulary.

Note also that `contributors[]` is already fully wired through the truth core as **evidence-cited draft
content** (`draft_validator.py:171-185` requires evidence per contributor;
`export.py:99-100`; `audit.py:83-84` keys sidecar evidence as `attribution:{name}|{role}`). A future
feature must not quietly convert that from *authored, evidenced content* into *system-derived identity*.

### 1.5 Identity is absent and its trust boundary is ~~unproven~~ NOW STATED BY DEAN — and the answer is that it can be bypassed

> **AMENDED 2026-08-12.** The heading's "unproven" is superseded: Dean answered. **The section's
> conclusion is not superseded — it is strengthened.** He **reconfirmed** that the Service is a
> **plain ClusterIP with no NetworkPolicy**, so any in-cluster pod can reach the app directly and
> **forge forwarded identity headers**, and therefore **`X-authentik-username`'s presence does NOT
> prove authenticated edge traversal** (Q4, answered against us). He also stated that the edge
> injects/overwrites exactly five headers and that the **canonical principal is the Authentik
> username**, and he **authorized server-stamping it** — *conditional on the request's identity having
> been established through the trusted authentication boundary*, which ISAAC has not built. So slices
> D–G below stay **BLOCKED**, now on ISAAC's own engineering rather than on Dean's silence. Operator
> testimony about configuration; not observed here. Full record:
> [`identity-trust-contract.md`](../../identity-trust-contract.md) §2, §6A.1, §7.

Full evidence in [`identity-trust-contract.md`](../../identity-trust-contract.md). The short form:
zero identity headers appear anywhere (0 matches / 498 files searched, excluding the two docs that
name them); the backend reads four headers, none of them
identity; there is no trusted-proxy configuration, no header-stripping middleware, and the pod binds
`0.0.0.0` with the app-level bearer key **unset in production**. Whether the ingress strips forged
copies is configuration in `isaac-k8`, which is not in this tree.

**Therefore: the moment one line of code reads an identity header, spoofing becomes live and
unmitigated.** This is gate **G7**.

---

## 2. Why this is a genuine hard stop, not caution

The authorizing prompt lists its own Hard Stops. **Five are met**, on evidence:

| Hard Stop | Met? | Evidence |
|---|---|---|
| "The stable identity claim cannot be proven." | **YES** | No document, plan, comment or config names any claim as the subject identifier. The readiness plan says only that headers "are available" (`:22`) |
| "Identity headers may be spoofed." | **YES** | No trusted-proxy config, no header stripping, pod on `0.0.0.0`, app key unset in prod; ingress behaviour unknowable from this repo |
| "User persistence requires an unapproved migration." | **YES** | Four of the six approvals **this document proposes** (§4) are unaddressed, and `readiness-plan:48-52` + `CLAUDE.md` §15 block it independently of all six (§1.3) |
| "Group membership policy is institution-owned and unresolved." | **YES** | Authentik `admin`/`researcher` are an *edge admission* gate; whether they may be authoritative in-app is undecided (Q6) |
| "Invitations would expose unapproved identity data." | **YES** | Any invite UI must render a person identifier; which identifier is safe is undecided (Q5) |

The prompt also instructs: *"Do not assume … Authentik group claims should automatically become ISAAC
groups"* and *"Email is a safe stable user identifier"*. Both cautions are **confirmed correct** —
§1.5 and the trust contract §9 show why.

---

## 3. The model (design locked, implementation gated)

Deliberately the smallest thing that makes the existing experiment workflow multi-user. **No project,
workspace, milestone, task board, due date, sprint, portfolio, or Gantt abstraction** appears anywhere
below, and none is a hidden dependency of anything below.

### 3.1 Entities

**User** — an authenticated institutional person. ~~Identified by an **opaque, immutable,
non-reassignable subject claim** (Q5).~~ **Corrected 2026-08-01** — see
[`docs/identity-trust-contract.md`](../../identity-trust-contract.md) §9.1, which supersedes this:
the principal is the **Authentik username**, because it is the **required compatibility key** — every
existing portal ownership, ACL, and audit row is already keyed to it
(`records.data->'attribution'->>'uploaded_by'`, `record_history.actor`, `record_acl.grantee_identity`,
`record_acl.granted_by`, `api_requests.username`, `portal_access_log.username`,
`hyp_project_shares.identity`; established by direct audit of the **public** upstream source).
~~Institutional confirmation is still required that usernames are **non-reassignable across rename,
departure, and rehire** — that is Q5, and it is unanswered, so username is a *technical stable-ID
candidate*, **not** a lifecycle guarantee.~~ **RECEIVED 2026-08-12: Dean states usernames are NOT
reassigned and the username is canonical.** The distinction this sentence drew was the right one, and
the thing it asked for is exactly what arrived — an *institutional* statement, not a technical
inference. **Q17 should not be reopened and no UID↔username infrastructure should be introduced**, so
the `sub` warning immediately below is now a settled prohibition rather than a caution. Operator
testimony, not observed here. **Do not introduce a second identity namespace based on
`sub` without an explicit migration and compatibility plan** — two principals for one person, with
every existing row keyed to the one ISAAC would not be using, is the expensive mistake here. Never
email (trust contract §9). **Never ORCID**: it is scientific-credit metadata and must never confer
authorization — upstream already guards this with `test_orcid_in_body_confers_no_rights`. Fields:
internal id; external IdP; Authentik username as the compatibility key; display name; email *only if a
product requirement forces it*; active state; created / last-seen.

**Group** — a lab, team, department, facility unit, or research collaboration. Owns **only**: name,
slug, description, membership, roles, its shared experiments, an activity summary, and basic settings.
It owns no schedule, no tasks, no status of its own.

> **These are ISAAC-defined collaboration groups and have nothing to do with Authentik's groups.**
> Authentik forwards only `admin` and `researcher` (upstream `portal/api.py:66-67`;
> `docs/deployment.md:28`; `docs/developer-guide-k8s.md:59`) — **coarse deployment-access groups**
> answering *may this person use the deployment at all*. They are not research-collaboration groups and
> must not be used as such: keying sharing to `researcher` would grant every researcher access to every
> experiment. Note that upstream itself never uses groups for sharing — it uses **per-resource ACL
> rows** keyed on the username, in both of its databases (trust contract §5.1, §5.3).

**Experiment / Record** — remains the primary unit of work, unchanged. Scope is either `personal` or
`group`. It continues to own its scientific metadata, evidence, confirmation state, validation, export
readiness, version, and audit history.

**No `Project` or `Workspace` entity.** Nothing in the repository evidence makes one unavoidable, and
§3.4's routing shows the three-level hierarchy is sufficient.

### 3.2 Roles — four, and no more until a real need is proven

| Role | Manage group | Manage members | Assign roles | View group experiments | Create | Edit | Confirm | Add evidence | Export |
|---|---|---|---|---|---|---|---|---|---|
| **Owner** | yes | yes | yes | yes | yes | yes | yes | yes | yes |
| **Admin** | no | ordinary members only | below own level | yes | yes | yes | yes | yes | yes |
| **Member / Editor** | no | no | no | yes | if permitted | per experiment | yes | yes | yes |
| **Viewer** | no | no | no | yes | no | no | **no** | no | **decide (Q-K5)** |

Invariants: **the last Owner cannot be removed or demoted**; an Admin cannot remove an Owner; an Admin
cannot perform institution-owned operations. **Reviewers are an experiment-level assignment, not a
group role** (Slice I) — the existing review semantics are per-record, and a permanent group-wide
"Reviewer" would invent authority the workflow does not have.

### 3.3 Permission matrix — enforced on the backend, always

| Action | Owner | Admin | Member | Viewer | Non-member |
|---|---|---|---|---|---|
| View group | ✓ | ✓ | ✓ | ✓ | ✗ |
| View membership | ✓ | ✓ | ✓ | ✓ | ✗ |
| Create experiment in group | ✓ | ✓ | if permitted | ✗ | ✗ |
| View group experiment | ✓ | ✓ | ✓ | ✓ | ✗ |
| Edit metadata | ✓ | ✓ | ✓ (per experiment, per §3.2) | ✗ | ✗ |
| Confirm values | ✓ | ✓ | ✓ | ✗ | ✗ |
| Add evidence | ✓ | ✓ | ✓ | ✗ | ✗ |
| Remove evidence | ✓ | ✓ | ✓ | ✗ | ✗ |
| Run validation | ✓ | ✓ | ✓ | ✓ (read-only) | ✗ |
| View export readiness | ✓ | ✓ | ✓ | ✓ | ✗ |
| Export | ✓ | ✓ | ✓ | Q-K5 | ✗ |
| Manage members | ✓ | partial | ✗ | ✗ | ✗ |
| Change roles | ✓ | below own level | ✗ | ✗ | ✗ |
| View audit history | ✓ | ✓ | ✓ | ✓ | ✗ |
| **Change experiment scope** (personal ↔ group) | ✓ | ✓ | ✗ — owner/admin only, since it changes who can see the record | ✗ | ✗ |
| Archive experiment | ✓ | ✓ | ✗ | ✗ | ✗ |

**Frontend hiding or disabling is never sufficient.** Every row is a backend check. The frontend may
only *reflect* a decision the backend has already made.

### 3.4 Experiment-flow preservation contract — binding

The current workflow stays primary. Concretely:

- **Navigation** keeps `My Experiments` first and `Create Experiment` reachable in one click from it.
  `Groups` is added as a **sibling**, never a parent. Proposed IA: `My Experiments · Groups ·
  Project Memory · Governance & Safety · Statistics · Settings & API`. Current routes are 10
  (`routes.ts ROUTE_PATTERNS`); this adds `/groups` and `/groups/:slug`.
- **No user may be required to enter a group before creating an experiment.**
- **Creation** gains at most one control: a scope selector, `Personal` | `Group: <name>`. It must not
  alter any scientific field, must not change validation semantics, must default explicitly and
  safely, and must offer only groups in which the user holds create permission.
- **Lists** — `My Experiments` shows what the user owns/created/edits/follows; a group page shows
  that group's experiments. **The same experiment is the same authoritative record in both.** No
  duplicate truth, no second experiment UI, no forked routes: group pages reuse the existing
  experiment cards and the existing `/record/:id/*` workflow.
- Synthetic demo behaviour stays deterministic and idempotent (the P36.8 guard must keep passing).

### 3.5 Audit contract

Events: experiment created · scope changed · metadata changed · confirmation added/changed · evidence
added/removed · validation run · export generated · member or permission changed.

Each event carries: event id · experiment id · group id · **actor stable id** · event type ·
timestamp · record version · a **safe structured summary** · a request/correlation id.

**Never stored:** tokens, full Authentik headers, secrets, unnecessary PII, full before/after record
copies by default, or raw scientific content in generic logs. Version history must not weaken the
authoritative current record — the current record remains the truth, and history is derived commentary
on it.

### 3.6 Deferred by design

Live presence · typing indicators · field-level locks · real-time cursors · WebSockets · CRDTs ·
operational transformation · simultaneous rich-text editing · comments · mentions · notifications ·
tasks. Implement only if ordinary multi-user editing proves insufficient. Nothing in §3 depends on any
of them.

---

## 4. Storage decision

| Option | Verdict |
|---|---|
| **A — same PostgreSQL, separate ISAAC application schema** | **RECOMMENDED, when unblocked.** The role already owns the database and its `public` schema and may freely create tables (guide `:136-140`); connectivity is already deployed and proven-by-config (`PGHOST` present in the pod); transactions are available; and Dean explicitly blesses *"adding app-specific tables next to the mirrored schema"*. Put them in a **named schema** (e.g. `app`) rather than loose in `public`, so the mirrored portal tables stay visibly separate. **Do not alter the existing `records` table.** |
| **B — separate collaboration database** | **Rejected on current evidence.** It buys isolation that pg_hba already provides, and costs new infrastructure, a new Secret, a new backup lifecycle, and cross-database linkage — every one of which is a Dean-owned change, converting a two-approval problem into a five-approval one. |
| **C — existing portal identity/group service** | ~~**Cannot be evaluated.**~~ **RULED OUT 2026-08-01 — no such service exists.** Direct audit of the **public** upstream source (`ISAAC-DOE/isaac-ai-ready-record`, `gh api … --jq '.visibility'` → `public`) found **22** tables across its two databases and **none** of them a users / accounts / identities / groups / memberships / roles / permissions / teams / organizations table; identity is a bare `TEXT` Authentik username written onto rows; and there is **no `/me`, no group endpoint, and no membership API** among its ~60 routes. **Q12 is answered — No** (trust contract §5.1). Option C therefore cannot supersede option A, and **A is no longer contingent on Q12**. What upstream *does* provide is a **pattern**, not a service: per-resource ACL rows (`record_acl`, `hyp_project_shares`) plus the locked authorization logic in `portal/record_authz.py` — a design source for ISAAC, explicitly **not** implemented here (trust contract §5.2). |

**Migration policy.** The six-item checklist below is **this document's proposed contract**, not a
pre-existing repository requirement — it appears nowhere else in the tree, and is named as a proposal
so a later session does not cite it as established policy. Proposed: no migration may be created
before Dean approves storage location (technical objection removed, but **contingent on Q12**),
schema ownership (technical objection removed), **migration process**, **backup/retention**,
**identity source**, and **group administration policy**. Independently of all six, the project-level
block in `readiness-plan:48-52` and `CLAUDE.md` §15 must be lifted.

---

## 5. Slice sequence, with an honest authorization verdict for each

| Slice | Content | Verdict | Blocking gate |
|---|---|---|---|
| **A** | Debt cleanup + backlog. No collaboration semantics | **AUTHORIZED — done this session** | — |
| **B** | Record location and access report | **AUTHORIZED — done this session** (`where-the-30-records-are.md`) | — |
| **C** | Identity trust contract | **DOCUMENT AUTHORIZED — done** (`identity-trust-contract.md`). **CODE STILL BLOCKED** | ~~**G7** (Q1–Q4, Q6)~~ **G7's questions were ANSWERED 2026-08-12** — Q1, Q4, Q5, Q6, Q7, Q8, Q9, Q10, Q17, Q18, Q25. **The gate MOVED rather than closed:** Q4's answer is that an in-cluster caller *can* bypass Authentik, and every authorization Dean gave is conditional on a **trusted authentication boundary ISAAC has not built**. D–G below stay blocked |
| **D** | `/api/me` + frontend session context | **BLOCKED** | G7 — cannot return a current user when no user can be safely identified |
| **E** | Users / groups / memberships persistence | **BLOCKED** | G7 + 4 of 6 migration approvals. ~~+ **Q12**~~ — **Q12 answered "No" 2026-08-01** (no upstream identity service exists; trust contract §5.1), so this is no longer a blocker on E, and option A no longer waits on it |
| **F** | Group navigation and membership UX | **BLOCKED** | depends on E; membership administration policy is institution-owned |
| **G** | Experiment scope (personal vs group) | **BLOCKED** | depends on E |
| **H** | Collaborative editing | **~80% ALREADY SHIPPED** (§1.1). The remaining 20% — actor attribution + audit — is **BLOCKED** on G7 | G7 |
| **I** | Experiment-level review permissions | **BLOCKED** | depends on E/G |
| **J** | Real-record collaboration | **BLOCKED** | **G2** (per-record visibility) **and G6** (personal data). Dean's default-closed decision |

**Exactly one slice of the ten contained implementable collaboration code, and it turned out to be
already implemented.** That is the honest summary.

### What could be built without identity, and why it should not be

Two candidates were considered and rejected:

- **An unwired `Principal` type with no call site.** Rejected: an `identity.py` exporting
  `get_principal()` is precisely the affordance that lets a later slice write
  `uploaded_by=principal.subject` without reopening the trust question. The matrix's own seam rule
  §6, the "Authorship / actor" row, says *"Do not invent [an actor] as a side effect of another
  feature"*.
- **Synthetic multi-user groups behind a feature flag.** Rejected: it would require inventing a fake
  identity source, which fixes the shape of the real one before Dean has chosen it — the exact
  pre-deciding the seam table forbids. It would also add a second experiment truth for the flagged
  path, violating §3.4.

---

## 6. Decisions needed

### From Dean (evidence-backed, none answerable here)

Identity — the 15 questions in [`identity-trust-contract.md`](../../identity-trust-contract.md) §7.
The four that gate everything: **Q1** header names injected; **Q2** which reach the app;
**Q3** whether forged copies are stripped; **Q4** whether the Service is reachable bypassing the edge.
Then **Q5** stable subject claim, **Q6** are group claims authoritative in-app, **Q7** group→role map.

Storage — ~~**Q12** does a portal identity/group service already exist?~~ **answered "No" 2026-08-01
by direct audit of the public upstream source** (trust contract §5.1) — no longer a question for Dean.
Remaining: migration process, backup/retention, and group administration policy. **New: Q16** — is
`record_acl` actually present in the mirrored schema? It exists upstream since 2026-06-30 (`dc5da9c`,
PR #169) but is absent from the 8-table list in `postgres-test-db-guide.md:20-22`, so that list should
not be treated as an authoritative schema statement.

Visibility — **G2** per-record display; **G6** personal data in `data->'attribution'`; **G3** the two
retained aggregate breakdowns.

### From Krish (product only — not institutional security policy)

| # | Question | Default if unanswered |
|---|---|---|
| K1 | May ordinary users create groups, or only an administrator? | administrator-managed |
| K2 | Is membership invite-based or administrator-managed? | administrator-managed (invites need Q5 first) |
| K3 | Are `Owner / Admin / Member / Viewer` the right names? | as written |
| K4 | Do **personal** experiments remain the default scope? | **yes** — §3.4 assumes it |
| K5 | May a Viewer export? | **no** |
| K6 | Do comments belong in the first collaboration release? | **no** — deferred (§3.6) |
| K7 | Should the recon result be captured as a durable committed artifact when G1 is run? | **yes** — recommended, and now the *only* thing G1 still needs. ~~"the withdrawn 30/30 claim"~~ **corrected 2026-08-01:** the 30/30 claim is **not withdrawn** — the scan ran against image `v0.0.38` (`ceea656`) and Krish has restated the result at field level. It is **operator testimony, not an artifact**, because the endpoint keeps its result in process memory only, by design. Capture converts testimony into evidence |

### Immediately actionable by Krish, unblocking the most

1. **Run [`hosted-qa-checklist.md`](../../hosted-qa-checklist.md) Part 1 and paste the JSON back** —
   now runnable, its placeholder filled this session. This is **capture, not discovery**: the scan
   already ran against `v0.0.38` and reported 30/30 with no leaks (operator testimony). Pasting the
   sanitized body back is what closes **G1**. A rerun is not needed for correctness —
   `db_recon.py`, `schema/isaac_record_v1.json` and `src/isaac_records/` are byte-identical between
   `ceea656` and HEAD and no `_DB_RECON` line in `routes.py` changed — so expect the same result with a
   newer `app_commit`.
2. **Forward the four G7 questions to Dean.** They are the critical path for nine of ten slices.
3. ~~**Ask Dean Q12** before any storage work — it could make option A the wrong answer.~~
   **Discharged 2026-08-01** — Q12 is answered "No" from public upstream source (trust contract §5.1);
   option A stands. **Instead ask Q16:** is `record_acl` in the mirrored schema? And ask **Q5** in its
   sharpened form: is an Authentik username non-reassignable across rename, departure, and rehire?

---

## 7. Boundary proof for this session

- No production-derived record exposed, read, or written. **No database connection was opened during
  this discovery session.** That statement is precise and must be kept in that form. It does **not**
  mean the deployed database has never been contacted — the deployed pod contacted it once, on
  2026-07-31, against image `v0.0.38`, observed by Krish in an authenticated session (see the baseline
  matrix §0, Entry 2). *Nothing was opened from here* and *nothing has ever been opened* are different
  claims; only the first is true.
- No record copied into Git. No new fixture contains anything but synthetic data.
- No unauthorized database write; no write of any kind.
- No schema weakened; `schema/`, `src/isaac_records/` and the API route logic untouched.
- No raw identity header exposed; no identity value logged, echoed, or stored — none exists to expose.
- No secret accessed. No infrastructure change. No `isaac-k8` interaction.
- No project-management layer added. No collaboration code written at all.
- No external model used; nothing sent to any external service.
- The only call to the **hosted deployment** was an unauthenticated `curl` to `/krish/api/health`,
  which returned **302** to the Authentik outpost. No credential was sent; the body was discarded.
  Read-only `gh` API calls were also made to **GitHub** — CI run status, release list, upstream
  repository visibility, and (2026-08-01) the **public** source of `ISAAC-DOE/isaac-ai-ready-record`
  (`portal/database.py`, `portal/api.py`, `portal/record_authz.py`, `portal/ontology.py`) plus commit
  metadata for `dc5da9c` — none of which touches SLAC infrastructure or any record. The upstream repo
  is public (`gh api … --jq '.visibility'` → `public`); reading it discloses nothing.
- An **unauthenticated** page load of the Authentik login flow
  (`/if/flow/default-authentication-flow/`) was observed on 2026-08-01 to correct a claim in
  `developer-guide-k8s.md`. No credential was entered and no session was created.
