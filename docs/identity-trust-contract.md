# ISAAC Identity Trust Contract

**Created:** 2026-08-01 · **Status:** LIVE — this is the authoritative statement of what identity
ISAAC receives, what it may trust, and what must be decided before any user, group, or attribution
feature is built. Update it in the same PR as any slice that changes a row.

> ## Verdict: **No identity reaches the application. The trust boundary is unproven and lives outside this repository.**
>
> Building persistent users, groups, memberships, roles, or per-actor attribution on top of the
> current state is **not authorized**, and would be unsafe rather than merely premature. The reasons
> are enumerated in §1 and §2; the exact questions that would unblock it are in §7.

Authority, in precedence order: Dean's committed guide; the canonical repository at `d7010f9`;
observed runtime evidence; the vendored ISAAC v1.05 schema; tests.

---

## 1. What the application actually receives

### 1.1 Identity headers in this repository: zero

```
$ rg --hidden -g '!.git' -g '!node_modules' -g '!.venv' \
    -g '!docs/identity-trust-contract.md' \
    -g '!docs/superpowers/plans/2026-08-01-experiment-centered-collaboration.md' \
    -i "x-forwarded|x-auth-request|remote-user|remote-groups|x-real-ip|x-authentik" --stats
0 matches / 0 files contained matches / 498 files searched
```

**The exclusion that matters is this document**, which now *discusses* these header names and would
otherwise match itself (3 lines) — the command is a forward guard, and a self-match would make it
useless for distinguishing "doc mentions a header" from "someone added a header read". The companion
plan is excluded **pre-emptively**; it does not currently match, and dropping that second `-g` gives
`0 matches / 499 files searched` — same verdict, different denominator. Run it as written; a non-zero
match count means real code changed. The *file count* tracks tree size and will drift with any new
file; only the match count is the signal.

No identity-forwarding header name appears anywhere — not in code, config, docs, tests, or fixtures.
`X-Forwarded-For` and `X-Forwarded-Proto` are absent too.

### 1.2 Every request header the backend reads — four, none of them identity

| Header | Location | Purpose |
|---|---|---|
| `authorization` | `apps/api/isaac_api/auth.py:45` | shared-secret bearer compare |
| `If-None-Match` | `apps/api/isaac_api/routes.py:827-829` | optimistic concurrency |
| `If-Match` | `routes.py:967-969, 1089-1091, 1209-1211, 1381-1383` | optimistic concurrency |
| `X-Filename` | `routes.py:1389-1391` | upload filename (the upload itself is refused) |

`rg -n "alias=" apps/api/isaac_api/routes.py` returns exactly those six lines and nothing else. The
only other `Request` uses are a bounded `request.stream()` and `request.app.openapi()`.

**The backend reads no identity header. Not one line.**

### 1.3 The SPA has no identity concept

Every match for `user|login|logout|profile|account|session` across `apps/web/src` is a **false
positive**. The exact count moves with the glob and word-boundary choices (231 lines / 50 files for
`rg -ni -e '\buser\b' -e '\blogin\b' … apps/web/src --glob '!**/__tests__/**'`), so no single figure is
quoted — what matters is that **none** is an identity concept: SVG "user units", "screen-reader user", `role: 'user'` conversation turns,
`assistant-msg-user` CSS, "the user presses". There is no `AuthContext`, no `useAuth`, no
`currentUser`, no profile, no session store.

The one auth-adjacent surface is **presentation only**: `apps/web/src/components/FetchStates.tsx:93-152`
turns a 401/403 or an intercepted HTML sign-in page into a "Sign-In Required" state whose sole remedy
is `window.location.reload()`. That is the app *reacting* to the edge, not *reading* identity.

### 1.4 `ApiKeyAuthMiddleware` is not an identity system, and is off in production

`apps/api/isaac_api/auth.py:26-56`, registered at `app.py:105`:

- Reads `ISAAC_UI_API_KEY` **once at construction**; if unset or empty, `dispatch` immediately calls
  through (`auth.py:41-42`) — **fail-open, entirely disabled**.
- When enabled: one `secrets.compare_digest` against a single process-wide secret. Open paths are
  `OPTIONS` and exactly `{base_path()}/api/health`.
- **No per-key identity, subject, expiry, scope, storage, issuance, or revocation.**
- **Unset in the hosted deployment** — `docs/deployment.md:86`, `:124-126`;
  `docs/developer-guide-k8s.md:62-64`.

**Consequence: Authentik is the sole authentication boundary in production**, and it is external.

### 1.5 No trusted-proxy configuration exists

```
$ rg -n "request.client|proxy_headers|forwarded_allow_ips|--proxy-headers|root_path|TrustedHost" apps/api/ Dockerfile
(no output)
```

`Dockerfile:50` runs `uvicorn … --host 0.0.0.0` with **no** `--proxy-headers` and no
`--forwarded-allow-ips`. There is no `TrustedHostMiddleware` and no middleware anywhere that strips,
validates, or rejects client-supplied headers. The only registered middlewares are
`ApiKeyAuthMiddleware` and `CORSMiddleware` (`app.py:105-113`).

### 1.6 Observed edge behaviour

```
$ curl -s -o /dev/null -w "%{http_code} %{redirect_url}" --max-time 20 \
    https://isaac.slac.stanford.edu/krish/api/health
302 https://isaac.slac.stanford.edu/outpost.goauthentik.io/start?rd=…%2Fkrish%2Fapi%2Fhealth
```

No credential was sent; the body was discarded. This **observationally confirms** an Authentik **proxy
outpost in nginx forward-auth mode** fronts `/krish`. The header set such an outpost emits is
determined by its Authentik **provider configuration** plus the ingress `auth-response-headers`
annotation — **neither of which is in this repository**. The names are therefore not guessed here.

---

## 2. The security finding that governs this whole phase

**Spoofing is moot today and becomes live the instant one line reads a header.**

- Today the app reads zero identity headers, so there is nothing to forge. A caller setting
  `X-Forwarded-Email` receives byte-identical output to one who does not.
- The moment any code reads such a header, spoofing is **immediately live and unmitigated**, because:
  (a) there is no trusted-proxy allowlist (§1.5); (b) there is no header-stripping middleware;
  (c) the pod binds `0.0.0.0`; and (d) whether the ingress strips client-supplied copies is **not
  knowable from this repository** — it is ingress configuration in `isaac-k8`.
- **Anything in the cluster that can reach the pod's Service directly bypasses the ingress, and
  therefore bypasses Authentik entirely.** The app-level bearer key that would have caught that is
  unset in production (§1.4).

> **The safety of forwarded identity depends entirely on ingress configuration this repository cannot
> see and does not control.** That is the single most important fact in this document.

A bounded corollary worth recording without alarm: the same in-cluster bypass applies to
`GET /api/runtime/database/recon`. Its exposure is limited by design — the response is projected onto
four frozen allowlists and leak-scanned (`routes.py:3065, 3093, 3258, 3275, 3341`) — so the practical
risk today is aggregate-only. It is named here because it is the same boundary, and it should be part
of the question put to Dean (Q4).

---

## 3. Existing capability matrix

| Capability | Exists | Source | Runtime verified | Persistent | Authoritative owner | Security implication |
|---|---|---|---|---|---|---|
| App-managed users | **No** | none | n/a | n/a | — | no user table, model, or record exists |
| Authentik-backed identities | **Edge only; invisible to the app** | `developer-guide-k8s.md:58-60`; observed 302 | edge: yes | Authentik | Dean | the app cannot distinguish two authenticated humans |
| User profiles | **No** | none | n/a | n/a | — | — |
| JIT provisioning | **No** | none | n/a | n/a | — | there is no local principal to provision into |
| Roles | **No** — only *proposed* | `readiness-plan:79` | n/a | n/a | Dean | every authenticated user has identical, full capability |
| Group memberships | **Edge admission only** (`admin`, `researcher`) | `developer-guide-k8s.md:58`; `deployment.md:118-122` | edge: yes | Authentik | Dean | the two groups are indistinguishable to the app |
| Record ownership | **No** | `workspace.py:239-258` — `Experiment` has no owner field | n/a | `emptyDir`, wiped on restart | — | any authenticated user can edit or delete any record |
| Audit attribution | **No actor** — timestamps only | `answer_log` at `workspace.py:245`, appended `routes.py:616, 1014, 1141` as `{"applied"/"edited": …, "at": ts}` | n/a | ephemeral | — | changes are untraceable to a person |
| Per-user settings | **No** | settings are deployment-scoped | n/a | n/a | — | — |
| Deactivation / account deletion | **No** | none | n/a | n/a | Authentik | the app cannot revoke anyone |
| Per-user API credentials | **No — deliberately** | `apps/web/src/screens/settings/ApiKeys.tsx:1-32`; `auth.py:26-56` | n/a | none | — | the one shared key is unset in prod, so there is no app-level authN behind the edge |

**False positives, stated so they cannot mislead.** Every match for
`user|actor|owner|group|role|permission|member|principal|subject|identity` across `src/` and
`apps/api/isaac_api/` is non-identity (**190** lines: `rg -wi -e user -e actor -e owner -e group -e role -e permission -e member -e principal -e subject -e identity src/ apps/api/isaac_api/ | wc -l`): ARIA `role=` attributes; the *scientific* enums
`measurement.series[].channels[].role` and `assets[].content_role`; the **PostgreSQL** login role
`metadata_assistant`; search-result grouping (`routes.py:2376-2399`); UI capability groups;
`_evidence_owner_label` (the JSON path owning an evidence entry, `search.py:255-260`); the Postgres
**table** owner; and "deploy identity" meaning the commit SHA on `/api/health`.

---

## 4. The schema already has an attribution home — and the app never uses it

`schema/isaac_record_v1.json` (official ISAAC v1.05) defines a top-level `attribution` block:

| JSON path | Schema's own description |
|---|---|
| `/attribution` | "**WHO: uploader, owner, analyst, curator.** uploaded_by is SERVER-STAMPED from the authenticated identity at ingestion — client-supplied values are overwritten (tamper-proof attribution)… **Decided by D. Sokaras 2026-06-15.**" |
| `/attribution/uploaded_by` | "**Authenticated identity that submitted this record. Set by the server; any client value is overwritten.**" |
| `/attribution/contributors[]` | required `name`, `role`; plus `affiliation`, `orcid`, `email`, `notes` |
| `/attribution/contributors[].role` | enum: `data_owner`, `performed_measurement`, `performed_analysis`, `curated_record` |

`attribution` is **optional** — not in the schema root `required` list.

Two consequences that matter for collaboration design:

1. **`uploaded_by` is dead in this codebase.** `rg -n "uploaded_by" src/ apps/ tests/ scripts/`
   returns **zero**. The only occurrences in the tree are the two inside the schema JSON itself
   (`:1704`, `:1706`) — plus, since 2026-08-01, this document and its companions, which is why the
   command is scoped to code directories. The field Dean designed for the authenticated identity has
   never been written.
2. **`contributors[]` IS fully wired through the truth core** — but as manually-authored,
   evidence-cited draft content, not as authenticated identity:
   `src/isaac_records/draft_validator.py:171-185` requires each contributor to cite evidence and
   enforces `name|role` uniqueness; `src/isaac_records/export.py:99-100` strips the envelope and passes
   `attribution` into the official record; `src/isaac_records/audit.py:83-84` keys sidecar evidence as
   `attribution:{name}|{role}`.

**So record-level attribution does not need a new home outside the record.** What is missing is
(a) a decision on which claim populates `uploaded_by`, and (b) recognition that
`contributors[].role` is a **scientific contribution** enum and **cannot double as an authorization
role**. Conflating the two would be a schema-semantics error, not just a modelling shortcut.

---

## 5. Database structures for identity

Dean documents these tables (`postgres-test-db-guide.md:19-22`): `records`, `record_history`,
`templates`, `vocabulary_cache`, `vocabulary_sync_log`, `vocabulary_proposals`, `api_requests`,
`portal_access_log`.

**No users table, no groups table, no memberships table is documented.** Reported as absence of
evidence, not as a negative finding: the portal's own identity model, if it has one, is simply not
described in this repository.

The only DDL Dean provides is `records` (`:100-112`) — and it has **no identity column**: no
`created_by`, no `uploaded_by`, no `user_id`.

**Column-level detail for `record_history`, `api_requests`, and `portal_access_log` is UNKNOWN.** This
repository contains no DDL, no column list, and no query for any of the three. Every occurrence is
non-informative: the name list in Dean's guide; a comment in `db_recon.py:293`; and
`"SELECT count(*) FROM record_history"` in a parametrized list at `tests/test_db_recon.py:419`
asserting the read-only guard *accepts* it — **no such query is ever issued.** Determining their
columns requires Dean, or a metadata-only deployed query (Q13).

**The recon already reads `information_schema`.** `Q_TABLE_INVENTORY` (`db_recon.py:1049`) selects
every public base-table name and is executed (`:1787`), landing in `run_recon`'s internal report as
`tables` (`:1929`) — but **`tables` is on none of the four frozen response allowlists, so it is
computed and not served.** `Q_VOCAB_COLUMNS` (`:1072`) already does column-level introspection for one
table, guarded by `safe_sql_identifier`/`_quote_ident`. Extending that to the three unknown tables
would be a narrow, precedented change — **and it is not authorized today.**

---

## 6. The personal-data finding nobody has named

Chaining three documented facts:

- The seed is *"the 30 earliest **real** records from production"* (guide `:23-24`).
- `data` holds the complete record JSON *"written by the isaac-ai-ready-record portal against v1.05"*
  (guide `:114-116`) — the same version vendored here.
- v1.05 says `attribution.uploaded_by` is *"SERVER-STAMPED from the authenticated identity"*, and
  `contributors[]` carries `email`, `orcid`, `affiliation`, `name`.

**Therefore the 30 seeded rows plausibly contain real SLAC personal identifiers inside
`data->'attribution'`** — and `Q_RECORDS_PAGE` (`db_recon.py:1064-1066`) pulls that entire `data`
column into pod memory on every scan.

```
$ rg -n -i -e 'PII' -e 'personal data' -e 'personally identifiable' -e 'email' -e 'username' \
    apps/api/isaac_api/db_recon.py apps/api/isaac_api/routes.py docs/postgres-test-db-guide.md
(no output — 0 matches)
```

**Zero mentions in the three files that could have named it.** Scoped deliberately: this document and
the baseline matrix both now discuss personal data, so including them would self-falsify the command.
Before 2026-08-01 neither mentioned it either. Gate **G2** is worded entirely around scientific content — *"titles, scientific
values, evidence, full JSON"* (`baseline-completion-matrix.md` §5, gate G2). **Its personal-data dimension is
unnamed, and as worded G2 would not surface it.**

To be scrupulous: **nothing is currently exposed.** The served `dataset` block is allowlist-projected,
and `by_schema_path` reports jsonschema *schema* locations, never instance values. This is a gap in the
**question**, not a live leak. It is recorded here as new gate **G6** (§7).

---

## 7. Decisions only Dean can make

`ISAAC-DOE/isaac-k8` — which holds every Kubernetes, ingress, and Authentik manifest — **is not in this
working tree** and is owned by Dean (`developer-guide-k8s.md:87-89`; `readiness-plan:19-20`;
`infrastructure-ownership.md:21-23`). This repository tracks no YAML except three GitHub Actions
workflows. Dean is therefore the only person who can answer Q1–Q4.

| # | Question |
|---|---|
| Q1 | What is the exact, complete list of HTTP header names the Authentik outpost injects into requests reaching the `metadata-assistant` pod? |
| Q2 | Which of those are listed in the ingress's `nginx.ingress.kubernetes.io/auth-response-headers` annotation, and therefore actually reach the app? |
| Q3 | Does the ingress strip or overwrite client-supplied copies of those headers, so a forged header cannot reach the pod? |
| Q4 | Can any workload in the cluster reach the `metadata-assistant` Service directly, bypassing the ingress and therefore Authentik? |
| Q5 | Which single claim should ISAAC treat as the stable, non-reassignable subject identifier, and is it stable across an email change, a name change, and a SLAC account rename? |
| Q6 | Are forwarded group claims authoritative for in-app authorization, or descriptive only? |
| Q7 | What is the complete set of Authentik groups ISAAC should recognise, and how do they map to app roles? |
| Q8 | On session expiry, what exactly does a browser XHR to `/krish/api/*` receive — a 302, a 401, or an HTML login page — and should the app treat all three identically? |
| Q9 | Is there a logout URL the app may link to, and should it be surfaced at all? |
| Q10 | Should this app server-stamp `attribution.uploaded_by` from the forwarded identity per the schema's own description, and from which claim? |
| Q11 | What are the columns of `record_history`, `api_requests`, and `portal_access_log`, and do any store a user identity? |
| Q12 | Does the ISAAC portal have a users/groups/memberships model in Postgres that this repository has not been told about? |
| Q13 | May the app issue a metadata-only `information_schema.columns` query against those three tables — column names and types, no rows? |
| **Q14 (G6)** | **Do the 30 seeded records contain real personal identifiers in `data->'attribution'`, and does the G2 visibility decision cover personal data as distinct from scientific content?** |
| Q15 | May the deployment temporarily enable a presence-only identity probe so the header contract can be observed once and recorded? |

---

## 8. Why a typed identity context is NOT being built now

The design does not strictly require knowing the header names: an env-supplied allowlist defaulting to
empty, returning `Principal | None` that is `None` unless every configured header is present, would be
a pure no-op in every current environment, exhaustively testable with synthetic headers, and would
never touch the truth core. The codebase already contains three reviewed instances of the needed
pattern — frozen-allowlist projection (`routes.py:3335`), raise-on-unlisted-key (`:3330-3334`), and an
unconditional leak guard (`:3341`).

**It is still the wrong move, for three reasons, the third decisive:**

1. **A no-op abstraction invites a non-no-op consumer.** `baseline-completion-matrix.md` §6, the "Authorship / actor" seam, is
   explicit: *"The app currently has no concept of an actor. **Do not invent one** as a side effect of
   another feature."* An `identity.py` exporting `get_principal()` is exactly the affordance that lets
   a later slice write `uploaded_by=principal.subject` without reopening the trust question.
2. **The trust boundary, not the parsing, is the hard part** — and it is entirely external (§1.5, §2,
   §7). Shipping the parser first solves the easy half while creating the appearance that the problem
   is handled.
3. **A configurable allowlist would be configured in `isaac-k8`, which Dean owns.** The mechanism that
   decides which headers are trusted lives in the repo whose owner we are waiting on. Building the
   reader before he sets the config buys nothing that waiting does not.

**Decision:** do not build a live identity seam. Wire nothing until Q1–Q4 and Q6 are answered.

### If a runtime probe is later authorized (design only — nothing implemented)

`GET {base}/api/runtime/identity/probe`, returning **only**: `authenticated` (bool);
`claims_present` as `{name: bool}` **projected onto a compile-time constant tuple of header NAMES**;
`claim_source` as a code constant; `probe_contract_version`; and fixed `limitations` strings.

Never, under any circumstance: a header **value** (not truncated, not hashed, not length-reported);
an **unlisted** header name (projection, never a filter — a filter can leak a name, a projection
cannot); any **count** of headers received (that number fingerprints the ingress config); any echo of
`Authorization`, `Cookie`, or `X-Filename`; any logging of the probe's inputs.

Safety requirements: env-flag gated **default off** (`ISAAC_IDENTITY_PROBE`), checked before the
request object is touched; the `strict=True` raise on the success path only (`routes.py:3303-3309`
explains why the failure envelope must *not* raise); the existing unconditional leak guard; contract
tests asserting the exact key set, including that an unlisted header produces no observable difference
in the response bytes; and **time-bounded use** — enable, observe once, disable. It is a measurement
instrument, not a feature.

Risks, stated not minimised: it is an **ingress-configuration oracle** — `claims_present` is precisely
the list of header names to forge for an attacker who can reach the pod directly (§2). Presence is
itself a claim about a person (`groups: true` on a deployment admitting only two groups narrows the
caller). A point-in-time observation invites false confidence, since Dean can change the provider's
header set with no signal to this repo. And with `ISAAC_UI_API_KEY` unset in production, the env flag
is the **only** real gate — which is exactly why it must default off.

---

## 9. Email is disqualified as the stable identifier

**No, and it should be treated as disqualified unless Dean explicitly says otherwise.**

1. **Email is mutable and reassignable.** SLAC addresses change on name change, role change, and
   departmental moves; a departed person's address can in principle be reassigned. An identifier used
   as `attribution.uploaded_by` must survive all of that, because the schema calls it *"tamper-proof
   attribution"*. Attribution that silently re-points to a different human is worse than none.
2. **It is direct PII in every surface it touches.** The readiness plan already forbids this:
   *"redaction rules (no raw IPs/usernames in any surface)"* (`readiness-plan:80`). An email is
   strictly more identifying than a username, and as a key it is guaranteed to appear in records,
   exports, sidecars, logs, and any future audit row.
3. **It collides with a schema field of different semantics.** `attribution.contributors[].email` is
   *scientific contact information a human deliberately supplied*. An authenticated-session email is
   *an authentication artifact*. One string for both conflates consent-to-be-contacted with
   was-logged-in, and no later code could distinguish them.
4. **Nothing in the repo proposes it.** No document, plan, or comment names email — or any other claim
   — as the intended subject identifier. Adopting it now would be **inventing** a decision, not
   recording one.

**What would be safe instead:** an opaque, immutable, non-reassignable subject claim (an Authentik
`sub`/UUID, if one is forwarded), with a display name resolved separately and never used as a key.
Whether such a claim is forwarded at all is **UNKNOWN — requires Dean** (Q1, Q5). Until then, no
identifier is chosen.

---

## 10. Classification summary

| PROVEN (this repo) | NOT PRESENT IN THIS REPO | UNKNOWN — REQUIRES DEAN |
|---|---|---|
| Zero identity headers anywhere (0 matches / 498 files, excluding the two docs that name them) | Any k8s / ingress / Authentik manifest | The header names the outpost injects (Q1) |
| Backend reads exactly 4 headers, none identity | Any users / roles / groups / permissions model | Whether the ingress strips client copies (Q3) |
| `ApiKeyAuthMiddleware` = one shared secret, fail-open, **unset in prod** | Any logout, session, or expiry logic | Whether the pod is reachable bypassing the ingress (Q4) |
| No trusted-proxy config, no header-stripping middleware | Any record ownership or actor attribution | The intended subject-identifier claim (Q5) |
| SPA has no user/session/profile concept — every match is a false positive | `uploaded_by` in any code — schema-only, 2 lines | Columns of `record_history` / `api_requests` / `portal_access_log` (Q11) |
| Schema defines `attribution.uploaded_by` + `contributors[]` | `PII`/`email`/`username` in any DB-governance doc — **zero mentions** | Whether seeded rows carry real personal identifiers (Q14 / G6) |
| Recon already queries `information_schema`; table inventory computed but **not served** | — | Whether group claims may be authoritative in-app (Q6) |
| Edge is an Authentik proxy outpost — observed at `/outpost.goauthentik.io/start` | — | Whether any hosted rollout works at all — **G1 open**, `/krish` → 302 |
