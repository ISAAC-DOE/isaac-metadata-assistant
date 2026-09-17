# ISAAC — production unblock package for Hao

**Prepared 2026-09-17. PREPARED, NOT SENT** — sending it is the project owner's act, and this
repository cannot witness delivery.

**Addressee change.** Committed history in this repository names **Dean** as the infrastructure
owner, and those records stay as written because they record who answered what, when. **New asks
go to Hao.** Where a row below says "Dean deferred D1–D9 on 2026-08-12", that is a historical fact
about a decision that is still in force, not an instruction to ask Dean again.

---

## How to read this document

Nine subject areas, **A** through **I**, then a verification matrix (**J**). Every item carries the
same eight fields, in the same order, so nothing important can be quietly omitted:

| field | what it means |
|---|---|
| **Current measured state** | what is true today, with the command or file that shows it. Where the measurement is *hosted*, its date is given, because hosted state moves |
| **Desired state** | the end condition, written so it can be checked rather than judged |
| **Owner** | who can actually do it. `Hao` = SLAC infrastructure. `ISAAC` = application-side, already ours, filed in our ledger. `Krish` = project owner. `Angel` = domain owner. `Institution` = a policy decision above all of us |
| **Exact action or decision needed** | the single next act, not a programme |
| **Security boundary** | what must stay true while it happens |
| **How to verify success** | a check that produces evidence, preferring **non-secret** output |
| **Rollback / fail-closed behaviour** | what happens when it fails or is reverted — and in every case below, the failure mode is *refusal*, never silent degradation |
| **What ISAAC code already proves** | the part that is built and tested, so no effort is duplicated |

**Three rules this package holds itself to.**

1. **No secret value is requested anywhere in this document, and none should ever appear in a
   reply to it.** Every verification below is satisfiable with a status code, a boolean, a
   non-secret identifier, or a "present / absent" answer. If a check seems to need a secret, it is
   the wrong check.
2. **No application work is assigned to Hao.** Where ISAAC has a gap, it says so and names our own
   ledger task. Hao is not being asked to build any part of the ISAAC UI, API, or data model.
3. **Nothing here has been done to production.** This package is a description and a set of
   requests. No agent has connected to the hosted database, applied a migration, changed
   infrastructure, or entered a credential.

---

## A. Executive summary

**ISAAC is application-complete for its authorized scope and is blocked on a small, specific set of
infrastructure and policy decisions.** It is not blocked on engineering effort, and it is not
asking for a large programme of work.

**The single most consequential item is `B`, the trusted authentication boundary.** Everything in
`C` (audit history), the whole of submission, and any future sharing rests on it. Today ISAAC can
prove *what* changed but not *who* changed it — and it deliberately refuses to guess, which is why
the hosted app reports `submission.blockers: ["no_attributable_actor"]` rather than stamping a name
it cannot trust.

| # | Blocker | Owner | Blocks | Effort for Hao |
|---|---|---|---|---|
| **1** | **Trusted authentication boundary.** The Service is a plain ClusterIP with no NetworkPolicy, so forwarded identity headers are forgeable by any in-cluster pod | **Hao** | attribution, submission, audit actor, all future sharing | a NetworkPolicy, **or** a decision to use Bearer validation for the API path |
| **2** | **Remote MCP reachability and OAuth** (Dean's `D1`, `D2`, deferred 2026-08-12) | **Hao** | agent access to ISAAC from Claude | route/ingress + an authorization-server decision |
| **3** | **Migration `0005` + run backfill** | **Krish** approves, **operator** applies | Stage-2b run reads | one reviewed migration, one script run |
| **4** | **Governance decision on real scientific file bytes** | **Institution**, via Hao | real historical import of BL15-2 files | a retention/classification answer, not a build |
| **5** | **AI provider decision** (`D1`–`D9`) | **Hao / institution** — *deferred, and ISAAC is content with that* | production LLM and transcription only | nothing, unless the deferral is revisited |
| **6** | **Gate `G3`** — five withheld aggregates | **Hao** | one diagnostic response's completeness | a yes/no |

**What is NOT blocked.** Record capture, completion, validation, export, the evidence sidecar,
proposals, the change feed, run projection writes, the historical-import reference path, MCP
against a local binding, and the deterministic assistant all work today and are covered by
**9,967 backend and 6,149 frontend tests** — measured 2026-09-17
(`.venv/bin/pytest --collect-only -q` → `9967 tests collected`; `npx vitest run` from
`apps/web` → `236 files / 6149 passed`). The backend figure is a **collection** count,
not a run; the frontend figure is a passing run. ISAAC is not waiting on Hao to ship features; it is
waiting to be allowed to tell the truth about *who* did them.

**What ISAAC is NOT asking for.** Not a kubeconfig. Not a port-forward. Not a database credential.
Not a secret value of any kind. Not production access for any agent.

---

## B. Trusted identity

### ID-1 — The Service is reachable in-cluster without traversing Authentik

- **Current measured state.** **Operator testimony, 2026-08-12, reconfirmed:** the ISAAC Service is
  a **plain ClusterIP with no NetworkPolicy**, so any in-cluster pod can reach the application
  directly and **can forge forwarded identity headers**. The presence of `X-authentik-username`
  therefore does **not** prove authenticated edge traversal. ISAAC has never observed this itself —
  it is infrastructure configuration, reported by the infrastructure owner. Hosted
  `submission.blockers` includes `no_attributable_actor` as a direct consequence.
- **Desired state.** A request arriving at the application can be classified, by the application,
  into exactly one of: *provably traversed the authenticated edge*, or *did not*. Nothing in
  between, and no header-presence heuristic.
- **Owner.** **Hao.** This is not solvable in application code, and ISAAC should not try.
- **Exact action or decision needed.** Choose **one** of two, and tell ISAAC which:
  - **(a) Network path.** Apply a NetworkPolicy so the Service accepts traffic only from the
    Authentik outpost / ingress. Then forwarded headers on an accepted request are trustworthy
    *because the network says so*.
  - **(b) Cryptographic path.** Nominate an authorization server and have the API path validate a
    Bearer token independently of any header. This is the portal precedent Dean named — trusted
    edge for browser traffic, independent Bearer validation for API/service traffic.
  Either is sufficient. **(b)** also advances `D` below, which is why it may be the better value.
- **Security boundary.** **Until one of these exists, ISAAC must not stamp an actor, and must not
  be asked to.** No configuration flag, environment variable or "trusted mode" toggle may be used
  to make ISAAC believe a boundary exists that does not. A request that cannot be classified is
  `unattributed`, permanently and visibly.
- **How to verify success.** Non-secret, and both halves are needed:
  1. From **outside** the edge, an unauthenticated request to a protected path is refused or
     redirected — report the status code only.
  2. From **inside** the cluster, a direct request to the Service is **refused** (path a) or
     **reaches the application** (path b). **Report the status code, and nothing else** — that one
     value is the whole finding.
     **Do NOT verify this through `/api/health`.** Its `submission` block comes from
     `submission_store.capability()`, which the route documents as *"ZERO I/O … reads
     configuration"* — it is **process-level configuration state, not per-request state**, so a
     forged-header request moves neither `requires_attributable_actor` nor `actor_trust_basis`, and
     reading them would produce a confident non-answer. **No token, header value or username needs
     to be quoted.**
- **Rollback / fail-closed behaviour.** Reverting the NetworkPolicy or unsetting the verifier
  returns ISAAC to exactly today's state: `actor_trust_basis: null`, submission blocked,
  attribution absent. **There is no partial-trust state and no degraded-but-stamping state** —
  `record_attribution.py` requires `trust_basis == verified_edge_assertion` and stamps nothing
  otherwise.
- **What ISAAC code already proves.** The consuming side is built and has been waiting since
  2026-08-19. `apps/api/isaac_api/record_attribution.py` stamps at the ingestion boundary, never in
  the truth core; `export._enforce_server_owned_invariant` anticipates it; the trust-basis gate is
  enforced and tested; and the fixture verifier exercises the whole path in CI. **No verifier in
  any shipped deployment mints `verified_edge_assertion`, by design.** ISAAC needs a boundary, not
  code.

### ID-2 — The canonical principal is settled; do not reopen it

- **Current measured state.** Dean answered 2026-08-12: the edge injects/overwrites exactly five
  headers (`username`, `groups`, `email`, `name`, `uid`); **usernames are not reassigned**; the
  **username is canonical**. `X-authentik-entitlements` and `X-Isaac-Edge` are **permanently
  disqualified** from any authentication, authorization or edge-traversal claim — ISAAC observed
  that a client's own value for both arrived untouched.
- **Desired state.** Unchanged. One key, the username.
- **Owner.** Settled — **no action**. Listed so it is not re-litigated.
- **Exact action or decision needed.** **None.** Specifically: do **not** introduce UID↔username
  mapping infrastructure, and do not reopen UID permanence.
- **Security boundary.** The two disqualified headers stay disqualified unless infrastructure
  changes *and* is independently re-verified.
- **How to verify success.** `docs/identity-trust-contract.md` §6A, §7, §10.1 — already committed.
- **Rollback / fail-closed behaviour.** N/A; nothing is being changed.
- **What ISAAC code already proves.** ISAAC **consumes none of the seven candidate headers** today.
  The temporary probe that observed them was removed in a reviewed PR and the route returns 404,
  pinned by test. **Do not re-add it.**

### ID-3 — Groups exist but cannot yet be used

- **Current measured state.** `admin` and `researcher` are the relevant ISAAC groups at the
  authenticated edge (Dean, 2026-08-12). `bl152-users` / `bl152-staff` are **not** ISAAC roles.
  `X-authentik-groups` is authoritative **only** for a request known to have traversed the
  authenticated edge — a condition ISAAC currently cannot establish for **any** request.
- **Desired state.** Once `ID-1` lands, group membership becomes usable as an input to a future
  authorization model. **Not before.**
- **Owner.** **Hao** for the boundary (`ID-1`); **Krish** for whether ISAAC should have roles at all.
- **Exact action or decision needed.** **None now.** This is recorded so that `ID-1` landing does not
  trigger an unplanned roles feature.
- **Security boundary.** **No authorization decision may be derived from an untrusted forwarded
  header** — `DEC-45`. This is the constraint most likely to be violated accidentally by a future
  well-meaning change, which is why it is written as a forward rule and not just a past finding.
- **How to verify success.** N/A until `ID-1`.
- **Rollback / fail-closed behaviour.** Absent groups → no elevated capability, never a default-allow.
- **What ISAAC code already proves.** ISAAC has **no role enforcement** and makes no authorization
  decision from any header today. That is the correct state, not a gap.

---

## C. Activity / audit foundation

**This section is almost entirely ISAAC's own work, and is included so Hao can see the one place it
touches infrastructure — and so nobody assigns it to him.**

### AUD-1 — A durable activity/audit history is required, and the change feed cannot serve it

- **Current measured state.** **Measured 2026-09-17 by reading the module.** `change_feed` serves
  four kinds (`experiment`, `note`, `proposal`, `run`) at `CURSOR_VERSION = 3`. A `ChangeEntry`
  carries exactly `kind, entity_id, changed_at_rev, rev, generation, updated_utc, state` — **no
  actor, no before/after pair, no channel.** The module's own docstring says so: *"no actor"*, and
  it describes its **coalescing** property, where *"a proposal that was accepted between two polls
  is reported as being `accepted` NOW, with no entry saying an acceptance happened"*. Coalescing is
  correct for a feed and **disqualifying** for an audit log.
- **Desired state.** A **separate append-only activity/event model** recording, per act: actor,
  action, object, field, before, after, timestamp, and **source channel**
  (`web` | `mcp` | `historical_import` | `system`). Statistics **summarizes** this history and is
  **never** its source of truth (`DEC-44`).
- **Owner.** **ISAAC** for the model, API and UI. **Hao** for the *actor* column only, via `ID-1`.
- **Exact action or decision needed.** **Hao: nothing beyond `ID-1`.** ISAAC's tasks are filed in our
  own ledger. Recorded here purely so the dependency is legible.
- **Security boundary.** Append-only with **no `DELETE`**, matching the five existing
  submission-lifecycle tables (`db_write._APPEND_ONLY_TABLES` already refuses a `DELETE` on them).
  The history must never become a second read surface for scientific content it should not carry.
- **How to verify success.** Once built: an edit through the web UI and the same edit through MCP
  produce two entries distinguishable by `channel`, each with a before/after pair.
- **Rollback / fail-closed behaviour.** If the actor cannot be established, the entry records
  `unattributed` and **is still written**. A history with an honest gap is more useful than no
  history, and far better than a guessed name.
- **What ISAAC code already proves.** Two reusable precedents, both shipped: append-only tables
  with a mechanical no-`DELETE` guard, and `revision_history.py` — a read module deliberately
  separate from its write module, nine named query constants over the five history tables. The
  pattern is proven; only the event model is new.

---

## D. Remote MCP

### MCP-1 — The MCP route is unmounted in production

- **Current measured state.** Hosted `mcp.posture: "unmounted"`, `mcp.binding: "unconfigured"`,
  `mcp.reason: "unset"`, `mcp.selected_by: "ISAAC_MCP_DEPLOYMENT"`, `serves_transport: false`.
  **Attribution, narrowed:** only `mcp.posture: "unmounted"` (and the `D1`/`D2` deferral entries)
  were captured in the **2026-09-16** hosted observation; the other four come from the
  **2026-09-12** blocker register and from reproducing the identical unmounted binding locally on
  **2026-09-17**. `GET /api/mcp`
  returns **404** when unmounted, which is the designed behaviour and not a fault.
- **Desired state.** Posture `oauth-mounted`, reachable by an authorized remote client.
  **Note that `remote-ready` is deliberately unreachable by any configuration of this build** — it
  is kept as the *name of the destination*, so that ISAAC can honestly say *"you are at
  `oauth-mounted`, not `remote-ready`"*. What separates them is exactly **Dean's deferred decisions
  `D1` (public reachability) and `D2` (authentication model)** — *his* decision ids, deferred
  2026-08-12, not this document's item ids, which is why every item here is prefixed (`ID-`,
  `MCP-`, `READ-`, `WRITE-`, `AI-`, `FILE-`, `DB-`) and no item is called `D1`.
- **Owner.** **Hao** for reachability and the authorization-server decision; **ISAAC** sets the
  environment binding once told which.
- **Exact action or decision needed.** Two answers, no build:
  1. **Should the MCP transport be exposed at all**, and at which path/ingress?
  2. **Which authorization server issues tokens for it**, and what **resource/audience identifier**
     should ISAAC expect? (Value needed; **no secret needed** — an audience identifier is not a
     credential.)
- **Security boundary.** MCP must not become a way around the edge. The binding refuses proxy
  headers (`refuses_proxy_headers: true` today) and that must remain true. **Scopes are bounded and
  separate** — a read scope cannot write, and no MCP scope may accept a proposal, because
  acceptance requires an attributable human actor.
- **How to verify success.** Non-secret: `GET /krish/api/health` reports
  `mcp.posture: "oauth-mounted"` and `mcp.serves_transport: true`; `GET /krish/api/mcp` no longer
  404s; and an **unauthenticated** request to it is refused with `401` carrying a
  `WWW-Authenticate` challenge. Report status codes and the three health values.
- **Rollback / fail-closed behaviour.** Unset `ISAAC_MCP_DEPLOYMENT` → posture returns to
  `unmounted`, the route is not mounted, and the path 404s. **Unmounting is a single environment
  change and destroys no data.**
- **What ISAAC code already proves.** The whole resource-server implementation exists, disabled by
  default: `mcp/oauth.py`, `mcp/jwt.py`, `mcp/policy.py`, `mcp/transport.py`, `mcp/tools.py`, with
  four named postures and a closed posture set that a test enumerates. **The posture is DERIVED
  from the three inputs the application itself consults**, so the disclosure cannot disagree with
  what the deployment actually does.

### MCP-2 — The audience check is exact string equality, and that will bite

- **Current measured state.** ISAAC validates the token audience by **exact string equality**
  (`jwt.py:611-613`): if the configured resource is not literally present in `aud`, the token is
  rejected. **RFC 8707 §2.2 explicitly permits an authorization server to MAP** the `resource` a
  client requested onto a *different* audience value. **These two facts combine into the single
  most likely cause of a mysterious `401` after everything else is configured correctly.**
- **Desired state.** The value ISAAC is configured with (`ISAAC_MCP_OAUTH_RESOURCE`) is
  **byte-identical** to what the authorization server actually puts in `aud` — confirmed in
  advance, not discovered by debugging.
- **Owner.** **Hao** supplies the authoritative audience value; **ISAAC** configures it.
- **Exact action or decision needed.** State the **exact** `aud` string the chosen authorization
  server issues for this resource. Not the resource URL you *requested* — the value that **lands in
  the token**. If the server maps one to the other, ISAAC needs the mapped value.
- **Security boundary.** ISAAC must **not** relax the check to a prefix, suffix, case-insensitive or
  "contains" match to make a mismatch work. An audience check that is loose is not an audience check.
- **How to verify success.** **Offline and with no production call.**
  `apps/api/isaac_api/mcp/preflight.py` answers, from configuration alone, which of four verdicts a
  given pairing produces: `accepted`, `exact_string_mismatch`, `different_resource`, or
  `no_usable_audience_claim`. **It is an importable module, not a CLI** — there is no `__main__`
  and no route exposes it. From a repository checkout:

  ```bash
  PYTHONPATH=apps/api python -c "from isaac_api.mcp.preflight import audience_comparison; \
    print(audience_comparison('<configured-resource>', ['<expected-aud>']).as_dict())"
  ```

  Confirm the verdict is `accepted`. **This opens no socket, resolves no name and contacts no
  authorization server** — it is a diagnostic over values the operator already holds, and neither
  argument is a credential.
- **Rollback / fail-closed behaviour.** A mismatch produces a clean `401`, never a partial
  acceptance. Fail-closed is already the behaviour; the preflight exists so the *reason* is legible.
- **What ISAAC code already proves.** The preflight module exists precisely to make this finding
  legible before anyone points a client at anything, and it names all four failure shapes. This is
  ISAAC anticipating an operator's bad afternoon, not asking Hao to debug one.

---

## E. Required backend reads

### READ-1 — Hosted per-record display is closed by default (gate `G2`)

- **Current measured state.** Hosted `database.record_display: "closed"`, observed 2026-09-16 and
  unchanged since the gate was created. The database holds **30 production-derived records** — that count comes from the
  recon response body, **not** from `database.contains_production_derived_records`, which is a
  boolean and carries no number. Dean's guide requires the visibility
  boundary to be built into the read path from the start, not bolted on later.
- **Desired state.** An explicit decision — **open, stay closed, or open with named constraints**.
  ISAAC is content with "stay closed"; what it cannot do is guess.
- **Owner.** **Hao** (as data owner for the seeded corpus).
- **Exact action or decision needed.** A yes/no/conditional on: *may the hosted application display
  individual records from this database to an authenticated user?*
- **Security boundary.** **Database reachability is not display authorization**, and ISAAC treats
  them as unrelated. Until an answer exists, no record field, title, id, value or evidence entry
  leaves the pod.
- **How to verify success.** `GET /krish/api/health` → `database.record_display` reflects the
  decision.
- **Rollback / fail-closed behaviour.** Default is **closed**. Reverting the flag closes it again
  immediately; no data is exposed in the interim because the read path never builds the payload.
- **What ISAAC code already proves.** The read path is gated at the source, not at the renderer.
  The Slice-2A diagnostic returns **sanitized aggregates only**, with every response block
  projected onto a frozen allowlist so an unlisted key can never be served — and on the success
  path an unlisted key additionally **raises**, degrading into a sanitized envelope.

### READ-2 — Gate `G3`: five aggregates are withheld pending a decision

- **Current measured state.** Five record-*derived* aggregates were served in image `v0.0.32`,
  beyond the enumerated authorization: `by_instance_path`, `distinct_structural_signatures`, the
  `total_link_count`/`dangling_link_count` pair, and `vocabulary_term_count`. **They are no longer
  served.** Verified in the hosted response body on 2026-09-13: `dataset` carries sixteen keys and
  **none of the five**; `withheld_pending_visibility_decision` names exactly those five and nothing
  else; `vocabulary_term_count` is replaced by the boolean `vocabulary_cache_present`.
- **Desired state.** A decision on whether any of the five may be restored.
- **Owner.** **Hao.**
- **Exact action or decision needed.** For each of the five: restore, or keep withheld. The
  boundary case worth an opinion is `by_instance_path` — over a 30-row corpus, an `error_count` of
  1 at a path **is a single-record fact**, which is why ISAAC withdrew it rather than merely
  flagging it.
- **Security boundary.** The governing rule: *the schema may describe the data; the data may not
  describe itself.* Plus a minimum cell size, a cross-tabulation limit, and an absolute prohibition
  on caller-parameterized aggregation.
- **How to verify success.** The hosted recon response's
  `dataset.withheld_pending_visibility_decision` list shrinks to match the decision, and the
  restored keys appear in `dataset`. **Enumerate the block's keys; do not grep the serialized
  payload** — a flat-text search matches the withheld *list itself* and reports a false leak. This
  mistake has been made here once already.
- **Rollback / fail-closed behaviour.** Removing a key from the allowlist withholds it again
  immediately. The allowlist is the mechanism, so there is no code path that can serve a key the
  list omits.
- **What ISAAC code already proves.** All three nested blocks are allowlist-projected; the
  root-cause gap (only *top-level* keys were frozen, so five could ship inside `dataset` without
  tripping a test) is closed rather than relocated.

---

## F. Required draft writes

### WRITE-1 — Durable storage is configured hosted; submission is still blocked on the actor

- **Current measured state.** Hosted `experiment_storage` read `postgres` / `durable` when last
  observed (**2026-09-13**), and hosted `submission.blockers` read exactly
  `["no_attributable_actor"]` when last observed (**2026-09-12**) — **the storage blocker is
  already cleared; the identity one is not.** Both are dated because hosted state moves and this
  environment cannot re-check it; **re-measure via `J13` before acting on either.** (A default local build with no `PGHOST` reports both blockers
  and `backend: "filesystem"`, which is the correct fallback, not a defect.)
- **Desired state.** `submission.configuration_permits: true`, reached **only** by closing `ID-1`.
- **Owner.** **Hao**, via `ID-1`. Nothing else is outstanding.
- **Exact action or decision needed.** None separate from `ID-1`. Listed so that "why can't we
  submit?" has one answer and not two.
- **Security boundary.** **A submission must carry an attributable actor.** ISAAC must not be
  configured to submit anonymously, and there is deliberately no flag to do so.
- **How to verify success.** `GET /krish/api/health` → `submission.blockers` becomes `[]` and
  `submission.actor_trust_basis` becomes non-null.
- **Rollback / fail-closed behaviour.** Removing the boundary restores the blocker. Already-written
  history is append-only and is not rewritten — entries keep whatever attribution they had.
- **What ISAAC code already proves.** The entire submission lifecycle is built over five
  append-only tables with `0003`/`0004` owner-approved; the blocker list is **derived from
  configuration**, not hardcoded, so it will clear itself the moment the boundary exists.

### WRITE-2 — Writes are policy-restricted, mechanically

- **Current measured state.** `db_write.WriteStatementPolicy` refuses any statement naming a table
  outside `OWNED_TABLES`, refuses **every** `DELETE` against the five append-only history tables,
  and refuses all access to the production-derived `records` table. **ISAAC cannot write to
  `records` even by mistake.**
- **Desired state.** Unchanged.
- **Owner.** **ISAAC** — recorded so Hao knows the blast radius of granting write access.
- **Exact action or decision needed.** **None.** This is reassurance, not a request.
- **Security boundary.** The mechanical guard and the committed scope text must agree; widening one
  requires widening the other in the same change. This repository has recorded **five** occasions
  where a statement class or table reached the write path before a committed sentence named it, and
  the guard exists because of them.
- **How to verify success.** `apps/api/tests/` covers the policy directly; CI proves the migrations
  forward, backward and in the wrong order against a real `postgres:18`.
- **Rollback / fail-closed behaviour.** An unlisted table or a forbidden statement class **raises**;
  the transaction rolls back deterministically.
- **What ISAAC code already proves.** All of the above, in CI, on every commit.

---

## G. Claude / transcription governance

### AI-1 — No AI provider exists, and ISAAC is content with the deferral

- **Current measured state.** Dean **deferred `D1`–`D9`** on 2026-08-12: *"leave AI integration as
  future work rather than increasing scope at this point."* Every provider seam answers **`501
  no_provider_configured`** in every deployment — **including `POST /api/assistant/ask`, which is
  the seam, not the resolver** (measured 2026-09-17: `501`). The working, shipped question-answering
  path is **`POST /api/assistant/memory/query`**, a bounded deterministic resolver that involves no
  provider at all (measured: `200`). **There is no LLM anywhere in any build.**
  `POST /api/transcription` answers `501`. The Assistant panel *tells the user* there is no language model, on all five mounts.
- **Desired state.** Unchanged unless the institution revisits it. **ISAAC is not asking for this
  to be unblocked.**
- **Owner.** **Institution / Hao.**
- **Exact action or decision needed.** **None requested.** Listed for completeness, and so that a
  future "why is voice disabled?" has a committed answer.
- **Security boundary.** Three that must survive any future change: **no fake `Connected` state**;
  **no model output in the truth path, ever**; and the no-guessing rule applies to the assistant's
  own answers, so an unanswerable question is refused rather than fabricated.
- **How to verify success.** N/A while deferred.
- **Rollback / fail-closed behaviour.** Absent provider → `501`. The control still tells the
  scientist what to do instead, rather than failing silently.
- **What ISAAC code already proves.** Implementation against deterministic fakes is complete and
  owner-authorized. *Implementation complete* and *production provider configured* are different
  milestones, and ISAAC has reached only the first — deliberately.

### AI-2 — If speech is ever enabled, the question is institutional before it is technical

- **Current measured state.** Voice capture records audio **in-tab only**: no download, no casting,
  **no request of any kind**, pinned by a real-Chromium sweep over HTTP, WebRTC and WebSockets.
  Audio never leaves the browser. Transcription would require a provider that does not exist.
- **Desired state.** An answer to: **is scientific speech approved to flow through the
  organization's Claude environment, or any external ASR?**
- **Owner.** **Institution**, relayed by Hao.
- **Exact action or decision needed.** A policy answer. **Not a build.**
- **Security boundary.** **The Web Speech API is not a workaround** — in Chrome it routes scientist
  speech to a third party, which the egress boundary forbids. It must not be reached for as an
  "easy" alternative.
- **How to verify success.** N/A until answered.
- **Rollback / fail-closed behaviour.** No provider → the capture control refuses honestly and
  tells the scientist to type.
- **What ISAAC code already proves.** The privacy claim is not prose — it is measured, and a prior
  version of that same claim was found **false** and corrected, then pinned by a guard that catches
  8 of 8 plausible rephrasings.

---

## H. Real historical file upload

### FILE-1 — Uploads are an unconditional 403, and lifting that is a governance act

- **Current measured state.** `POST /api/uploads` returns **403 unconditionally** — verified
  2026-09-17 against a locally-served build. No multipart parser is reachable, and **no file byte
  is transmitted to the server by any path.**
  **But "a scientist cannot select a real file today" would be FALSE, and this is the fact most
  relevant to your decision.** Three non-test components declare an `<input type="file">` —
  `CsvReconcilePanel`, `RecordValidator`, and **`ImportFileStaging`, which is already the
  local-only staging path for real BL15-2 files**: it reads the chosen file in the browser,
  computes a checksum, labels it *"Local only — not sent to ISAAC"*, and **calls no upload route**.
  The repository's own guard pins exactly those three and the **polarity** of the disclosure,
  because an earlier version of that test passed an **inverted** one
  (`upload-claim-parity.test.tsx:480`, *"EXACTLY these three non-test files declare a file
  input"*).
  **So what is missing is not selection — it is permission to keep the bytes.**
- **Desired state.** Real BL15-2 files, **which a scientist can already select**, can be
  **transmitted, stored and ingested** — with the governance questions answered first. The gap is
  server-side retention, not the browser control.
- **Owner.** **Institution / Hao** for the decision. **ISAAC** for the implementation, which is
  owner-authorized (`DEC-33`) and gated on the answer.
- **Exact action or decision needed.** Four answers, none of them a build:
  1. **Classification.** What classification do raw beamline files carry?
  2. **Storage location.** May bytes rest in the app-owned volume/database, or must they stay in an
     institutional store ISAAC only points at?
  3. **Retention.** How long, and who may delete?
  4. **Egress.** Confirm bytes never leave the cluster — ISAAC's design assumes this, and would
     like it stated rather than assumed.
- **Security boundary.** Whatever is enabled must be **size- and type-bounded, traversal-safe, kept
  separate from official record bytes, discoverable through capability state, and disabled by
  default in governed production**. And the honesty rule that caused the previous implementation to
  be reverted: **a button that looks like an upload must actually upload, or not exist** — recording
  filenames while a scientist believes files were sent is worse than asking them to type.
- **How to verify success.** With the capability disabled: `POST /api/uploads` → `403`, and the UI
  offers the reference path. With it enabled: a bounded upload succeeds, an oversized or
  wrong-typed one is refused **by type, not by crash**, and a traversal attempt is refused.
- **Rollback / fail-closed behaviour.** Capability off → `403`, and the UI presents *Record a
  reference* instead. **The disabled state is the shipped default and is fully functional** — the
  historical-import reference path works today without any of this.
- **What ISAAC code already proves.** The BL15-2 corpus has been characterized end-to-end against
  **committed synthetic fixtures**, with the real corpus **never committed**: 45 concepts, a
  profile-based parser, conflict preservation, and a measured finding that only **5 of 45** concepts
  can reach a native official ISAAC field. **The parsing problem is solved; only the byte-handling
  permission is missing.**

---

## I. Outstanding database / migration state

### DB-1 — `0005_run_projection` is unapproved, and the backfill has never run

- **Current measured state.** `0001_experiments` applied hosted **2026-08-09**; `0002_runs` applied
  hosted **2026-08-12** (both by the infrastructure owner, both digest-verified against the
  approved bytes). `0003_revisions` + `0004_submissions` are **owner-approved 2026-08-17 and
  applied NOWHERE**. `0005_run_projection` is **not owner-approved**. `scripts/db_backfill_runs.py`
  has **never been run anywhere**. Observed hosted 2026-09-12:
  `run_projection.last_pass.unavailable: 3` — all three hosted experiments have an unreadable run
  projection.
- **Desired state.** `0003`+`0004` applied together; `0005` approved, applied, and backfilled;
  Stage-2b run reads cut over.
- **Owner.** **Krish** approves the migration text. **The operator** applies it. **No agent may do
  either.**
- **Exact action or decision needed.** In this order, and the order matters:
  1. Apply `0003`+`0004` **together** — `0004` declares a foreign key into a table `0003` creates,
     so they are one decision.
  2. Krish reviews and approves `0005`.
  3. Apply `0005`; run the backfill; confirm every `UNREADABLE`/`refused`/`failed` count is **0**.
  4. Run the operator's **two completeness queries** (`docs/migration-approval-packet-0005.md` §8A)
     and confirm **both return 0**. Only then may Stage-2b read from `isaac_runs`.
- **Security boundary.** **Use `scripts/db_migrate.py --through VERSION`** — and note **it is NOT
  in the container image.** `Dockerfile:59` copies exactly one script
  (`check_graphify_freshness.py`), so `db_migrate.py` and `db_backfill_runs.py` must be run **from
  a repository checkout with the libpq environment set**, not by exec-ing into the pod. **Do not
  improvise with raw `psql`** — applying the SQL by hand was explicitly considered and rejected
  (`docs/migration-approval-packet-0003.md`), because the runner is what records the ledger row.
  Without `--through`, `--apply`
  globs every migration on disk — which made the documented operator ask *mechanically impossible*
  to satisfy until it was fixed. Never apply a migration that has not been reviewed, and never
  apply past the version you intend.
- **How to verify success.** Non-secret: the hosted health block reports
  `run_projection.last_pass` with `unavailable: 0`; the two §8A queries return 0.
- **Rollback / fail-closed behaviour.** Each migration has a proven rollback, exercised in CI in the
  correct order, and **wrong-order application is refused**. The read cutover is the genuinely
  one-way step, which is exactly why it is gated on the two queries: a `SELECT` returning zero rows
  means *either* "no runs" *or* "never projected", and treating the second as the first would
  silently delete every run of every pre-existing record **and report success**.
- **What ISAAC code already proves.** CI applies `0001`–`0004` forward against a real `postgres:18`,
  proves the rollback order, and exercises cases blaming **41 of the 46 declared constraints** (run
  `32800763199`, job `97660962127`, at `c153ec9`). Three of the remaining five are *structurally*
  unblamable in isolation because the table's equality CHECKs subsume its shape CHECKs — they are
  proved refused, with the blame ambiguous by design. **What CI does not prove, and cannot:
  behaviour against the real data, roles and grants.** That is why the operator's step is separate.

---

## J. Verification matrix

**Every check below is satisfiable without disclosing a secret.** Where a value is needed it is an
identifier, a boolean, a status code or a count.

| # | Item | Check | Evidence to report | Secret needed? |
|---|---|---|---|---|
| **J1** | `ID-1` trusted boundary | in-cluster direct request to the Service | **status code only** — health's `submission` block is configuration-level and cannot witness a single request | **no** |
| **J2** | `ID-1` edge still enforcing | unauthenticated external request to a protected path | status code (302/401/403) | **no** |
| **J3** | `ID-2` principal | no action — confirm nothing was introduced | "no UID mapping added" | **no** |
| **J4** | `AUD-1` audit actor | depends on `J1` only | n/a until `J1` | **no** |
| **J5** | `D1` MCP mounted | `GET /krish/api/mcp` | status code; `mcp.posture`, `mcp.serves_transport` | **no** |
| **J6** | `D1` MCP refuses anon | unauthenticated request to the MCP path | `401` + presence of `WWW-Authenticate` | **no** |
| **J7** | `D2` audience | run `mcp/preflight.py` offline with the expected `aud` | one of four verdicts; `accepted` is the goal | **no** — an audience id is not a credential |
| **J8** | `READ-1` `AI-2` | health | `database.record_display` | **no** |
| **J9** | `READ-2` `G3` | recon response — **enumerate `dataset`'s keys** | key list + `withheld_pending_visibility_decision` | **no** |
| **J10** | `WRITE-1` submission | health | `submission.blockers` | **no** |
| **J11** | `FILE-1` uploads | `POST /krish/api/uploads` | status code (`403` expected). **Note three browser file-selection controls already exist and transmit nothing** | **no** |
| **J12** | `DB-1` migrations | health + the two §8A queries | `run_projection.last_pass`; two counts | **no** |
| **J13** | deployment currency | `GET /krish/api/health` | `commit`; compare to `git rev-parse origin/main` | **no** |

**One standing caveat on `J13`.** The last hosted observation from this environment was
**2026-09-16**, at commit `108ba4e4` (`v0.0.243`), which then matched `main` exactly. `main` has
since advanced to `9ef921d2` (`v0.0.245`). **Whether the hosted deployment has rolled forward is
unverified from here** and must be re-measured rather than assumed — `/krish` sits behind an
Authentik edge this environment cannot authenticate to.

---

## What this package deliberately does not do

- **It assigns no application work to Hao.** Section `C` is ISAAC's, and says so.
- **It requests no secret, at any point, in any check.**
- **It asks for no production change to be made by an agent**, and records that none has been.
- **It does not ask Dean anything.** His committed answers stand; new asks come here.
- **It does not treat the AI deferral as a blocker.** `G` is included for completeness and
  explicitly requests nothing.
