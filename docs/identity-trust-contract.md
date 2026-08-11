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

### 1.1 Identity headers in this repository: a permitted file set, now including five frontend files

**The invariant is a PERMITTED SET, not zero.** This document names these headers, and so does
`CLAUDE.md` §11 where it records the observation, so a tree-wide `0 matches` check would fire on the
very documents written to reason about the boundary.

> **Identity-forwarding header names appear only in files this section lists, and no application code
> path consumes any of them.** `X-Forwarded-For` and `X-Forwarded-Proto` are absent from code, config,
> tests and fixtures — the only occurrences tree-wide are the two in this sentence.
> *(It previously claimed "zero matches … in code, config, **docs**, tests or fixtures", which its own
> text falsified. Left visible: it is the trap this section names forty lines below — a document
> discussing the guard is itself a match.)*

**The heading and the invariant sentence used to say "exactly two files, both documentation". That was
false, and correction 4 below records when it stopped being true — it is not being silently
replaced.** Measured now:

```
$ rg --hidden -g '!.git' -g '!node_modules' -g '!.venv' -g '!.claude/worktrees' \
    -i "x-forwarded|x-auth-request|remote-user|remote-groups|x-real-ip|x-authentik|x-isaac-edge" \
    --files-with-matches
CLAUDE.md                                    # §11, which records the observation
docs/identity-trust-contract.md              # this file, which discusses the names
docs/dean-slack-draft-2026-08-03.md          # a question to Dean about the observation
docs/portal-identity-and-metrics-audit.md    # the audit that reasons about the boundary
apps/web/src/lib/myStatsContract.ts          # prose only: why no personal figure exists
apps/web/src/lib/currentUserContract.ts      # a FROZEN OBSERVATION TABLE — see below
apps/web/src/__tests__/my-stats.test.tsx     # the guard that scans the two modules above
apps/web/src/__tests__/current-user-contract.test.ts   # the guard over that table
apps/web/src/test/adapterFixtures.ts         # a test-only subject naming its origin header
```

**Which of those were already there, and which this slice added.** Two of the five `apps/web/src`
files predate the available-metrics/adapters slice: at `main` (`547276b`) the set was six files, and
`apps/web/src/lib/myStatsContract.ts` and `apps/web/src/__tests__/my-stats.test.tsx` were already among
them — pre-existing debt from the statistics-shell slice, and the invariant sentence was already false
when this slice began. The adapters slice added three: `lib/currentUserContract.ts`,
`__tests__/current-user-contract.test.ts` and `test/adapterFixtures.ts`. The count is stated as a
before/after file set rather than a total, for the reason recorded further down.

**What those five frontend files do with the names — and it is the case this section exists to flag.**
`lib/currentUserContract.ts` is the first module in this repository whose *subject* is identity, which
is exactly the shape §1.1 was written to catch, so it is stated explicitly rather than waved past:

- The seven names appear as `const` **string literals** in `IDENTITY_CANDIDATE_HEADERS` and in the
  frozen `HEADER_OBSERVATION_6A` record. That is code, not prose — a fair reading of the original
  invariant, which said "both documentation", is that this violates it.
- **Nothing reads a header by them.** There is no request object, no `Headers`, no `document.cookie`,
  no `fetch`, and no function in the module takes a header collection as an argument. The tuple is a
  transcription of §6A's table, kept beside the type it constrains so the disqualified pair can be
  *derived* from the observation rather than hand-listed twice.
- The tuple is **not an allowlist**, and the module says so at its declaration. Being nameable there is
  not permission to read the header, and `UsableIdentityClaimHeader` makes the two §6A.2-disqualified
  names untypeable as a subject source at compile time.
- `test/adapterFixtures.ts` names `x-authentik-username` as one fixture subject's `observedFrom`. It is
  test-only, and `__tests__/adapter-fixture-isolation.test.ts` asserts no production module imports it.
- The two `__tests__` files are the guards themselves, but they guard DIFFERENT surfaces and only one
  of them scans source. `my-stats.test.tsx` reads three modules as `?raw` and fails on a header read, a
  transport, an API-client call, a cookie or browser storage. `current-user-contract.test.ts` reads no
  source at all; its guard is a runtime one over `disabledCurrentUserSource.get()`. §1.4 states this
  precisely — and an earlier revision of THIS bullet said both files scan, 54 lines above the
  correction and first in reading order, which is the inversion §1.4's own wording exists to prevent.

**So the invariant is now two claims, and only the second one is still absolute.** "Confined to
documentation" is **spent** — it was false at `main` and this slice moved it further. "No application
code path consumes any of them" holds, is the claim that actually matters, and is the one now backed by
automated scans in the two test files above (§1.1's guard as a whole remains manual — see below).

**What the signal is.** A file *outside the list above*, and above all a match inside
`apps/api/isaac_api/`, means someone has started *consuming* a claim — which §8 forbids until Q4 and Q6
are answered, and which §6A.2 forbids permanently for two of the seven regardless of how Q4 and Q6 come
out. `apps/api/isaac_api/` is still at **zero**: `routes.py` contains no identity header name at all,
and did not even while the probe existed, because the candidate tuple lived in the probe module.

This is a **stronger** guard than the original `0 matches`, not a weaker one. `0 matches` could only
say "nobody mentions these"; the permitted set says "only the files that reason about them mention
them, and nothing consumes them". What it has lost since it was written is the ability to say "and none
of those files is code".

**Four corrections are recorded here rather than silently applied**, because this section's whole job
is accuracy and it has now failed at it repeatedly — three times on the invariant itself (corrections
1, 2 and 4; correction 3 is a gap in the pattern rather than a false statement), and three times on the
count:

1. **The original sentence** — *"No identity-forwarding header name appears anywhere — not in code,
   config, docs, tests, or fixtures"* — became false when the probe landed and was left standing three
   lines below a block that listed two code files naming these headers.
2. **The four-file form** (`identity_probe.py`, `test_identity_probe.py`, `docs/identity-probe.md`,
   this file) was correct only while the probe existed. All three probe files were deleted 2026-08-02;
   a stale "exactly four files" survived a dedicated review round before being caught.
3. **`x-isaac-edge` was missing from the pattern** until 2026-08-02, and its absence was a real hole:
   §6A.2 establishes that `X-Isaac-Edge` is the header **any client can set freely**, which makes
   "read `X-Isaac-Edge` to check the request came through the edge" the single most tempting misuse in
   the set — and exactly the one the guard could not see.
4. **The two-file form** (`CLAUDE.md` and this file, "both documentation") was **already false at
   `main` (`547276b`)**, where the set was six files and two of them — `apps/web/src/lib/myStatsContract.ts`
   and `apps/web/src/__tests__/my-stats.test.tsx` — sat inside `apps/web/src/`, the directory this
   section names as the strongest signal. It went unnoticed through the statistics-shell slice that
   introduced them, and this section was left unamended by the available-metrics/adapters slice that
   added three more, including the first module whose subject is identity. **The guard is manual by
   design, which means this document IS the guard**; leaving it stale did not merely mis-describe the
   tree, it disabled the check. Two lessons, both recorded rather than assumed learned: a slice that
   adds a header name must amend this section in the same commit, and "the header names are only in
   documentation" is no longer a claim this repository can make.

**The match COUNT is deliberately not recorded, and that is a fix rather than an omission.** It was
stated three times in two days — 61, then 24, then 33 — and was wrong within hours each time, because
*this document discussing the guard is itself a match*, so every edit explaining the guard invalidates
the guard's own number. **Compare the file list, never a total.**

**Nothing enforces the FILE SET automatically** — no test, no CI job, and none for the dead-link risk in
this document either. It is a manual check, and saying so beats implying a tripwire that does not exist.
Correction 4 is what a stale manual guard costs.

**One narrower thing IS enforced, and the distinction matters — but the two guards cover DIFFERENT
surfaces, and the first version of this paragraph read as though both scanned source text.** Corrected:

- **The source scan lives solely in `apps/web/src/__tests__/my-stats.test.tsx`** (trap 6,
  `:1024-1139`). It imports `screens/statistics/MyStats.tsx`, `lib/myStatsContract.ts` and
  `lib/currentUserContract.ts` as `?raw` and fails on a header access, a `fetch`, an API-client call,
  another transport, a cookie or browser storage. So *consumption inside those three modules* is a
  tripwire, whether or not the code ever runs.

  **Comment stripping applies to ONE of those scans, not all of them,** and an earlier revision of this
  bullet said "strips comments first" as though it covered the list. Measured: the stripper is built at
  `:1098` and only the cookie/browser-storage assertion (`:1109`) reads the stripped text; the header,
  `fetch`, API-client and transport scans all run against the unstripped module, and the test says why
  in line ("None of the THREE modules contains the substring `api.` in prose (checked …), so this
  needs no stripping"). The direction is conservative — an unstripped scan can only over-report — so this is a
  description defect, not a hole. The stripper has its own two guards against returning `''` or
  returning the text unchanged.
- **`apps/web/src/__tests__/current-user-contract.test.ts` reads no source at all.**
  `grep -n "?raw" apps/web/src/__tests__/current-user-contract.test.ts` returns nothing. Its guard is
  a RUNTIME one over `disabledCurrentUserSource.get()`: an own `document.cookie` accessor spy — itself
  proved to fire, so "never read" means something — plus `localStorage`/`sessionStorage` `getItem`
  spies and a stubbed `fetch`, all asserted not called. It catches a live read on the one code path
  this build executes, and would not see a dead one the source scan catches.

Both bite; neither substitutes for the other. And both cover only the modules that name the headers
today — not a fourth file appearing tomorrow, which is what the manual file-set check is for.

### 1.2 Every request header the backend reads — four, none of them identity

| Header | Location | Purpose |
|---|---|---|
| `authorization` | `apps/api/isaac_api/auth.py:45` | shared-secret bearer compare |
| `If-None-Match` | `apps/api/isaac_api/routes.py:909-911` | optimistic concurrency |
| `If-Match` | `routes.py:1049-1051, 1171-1173, 1291-1293, 1463-1465` | optimistic concurrency |
| `X-Filename` | `routes.py:1471-1473` | upload filename (the upload itself is refused) |

**Line numbers corrected 2026-08-01, and pinned to `7a9f15d`.** Every `routes.py` citation in this
file was stale by **+82** after commit `0d0a089` (`fix(demo): stop POST /api/demo/run from silently
destroying confirmed edits`), having been written before that commit landed. The originals were
`:827-829`, `:967-969, 1089-1091, 1209-1211, 1381-1383`, and `:1389-1391`.

**All `routes.py` line numbers in this document are as of commit `7a9f15d`.** They are stated with a
SHA because that is the only way a line number is checkable rather than merely stale-able: `git show
7a9f15d:apps/api/isaac_api/routes.py | sed -n '909,911p'` will always reproduce what was cited, whereas
the bare number silently drifts on the next unrelated edit and gives no signal that it has. **Prefer
the symbol over the line** wherever possible — re-derive with
`rg -n 'alias="If-Match"' apps/api/isaac_api/routes.py`.

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
four frozen allowlists and leak-scanned (the allowlist constants are `_DB_RECON_DATASET_KEYS`
`routes.py:3147`, `_DB_RECON_INTEGRITY_KEYS` `:3175`, `_DB_RECON_DATABASE_KEYS` `:3340`,
`_DB_RECON_GATE_KEYS` `:3357` — re-derive with
`rg -n '_DB_RECON_(DATASET|INTEGRITY|DATABASE|GATE)_KEYS' apps/api/isaac_api/routes.py`; the earlier
citation `:3065, 3093, 3258, 3275, 3341` was stale) — so the practical
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
| Group memberships | **Edge admission only** (`admin`, `researcher`) — **coarse deployment-access groups, NOT research-collaboration groups** (§5.3) | `developer-guide-k8s.md:58`; `deployment.md:118-122`; upstream `portal/api.py:66-67` | edge: yes | Authentik | Dean | the two groups are indistinguishable to the app, and keying collaboration to `researcher` would share every experiment with every researcher |
| Record ownership | **No** | `workspace.py:239-258` — `Experiment` has no owner field | n/a | `emptyDir`, wiped on restart | — | any authenticated user can edit or delete any record |
| Audit attribution | **No actor** — timestamps only | `answer_log` at `workspace.py:245`, appended at **two** sites, `routes.py:1097` and `:1224`, as `{"applied"/"edited": …, "at": ts}` (re-derive: `rg -n 'answer_log\.append' apps/api/isaac_api/routes.py`) | n/a | ephemeral | — | changes are untraceable to a person |
| Per-user settings | **No** | settings are deployment-scoped | n/a | n/a | — | — |
| Deactivation / account deletion | **No** | none | n/a | n/a | Authentik | the app cannot revoke anyone |
| Per-user API credentials | **No — deliberately** | `apps/web/src/screens/settings/ApiKeys.tsx:1-32`; `auth.py:26-56` | n/a | none | — | the one shared key is unset in prod, so there is no app-level authN behind the edge |

**False positives, stated so they cannot mislead.** Every match for
`user|actor|owner|group|role|permission|member|principal|subject|identity` across `src/` and
`apps/api/isaac_api/` is non-identity (**190** lines: `rg -wi -e user -e actor -e owner -e group -e role -e permission -e member -e principal -e subject -e identity src/ apps/api/isaac_api/ | wc -l`): ARIA `role=` attributes; the *scientific* enums
`measurement.series[].channels[].role` and `assets[].content_role`; the **PostgreSQL** login role
`metadata_assistant`; search-result grouping (`routes.py:2458-2481`, was cited `:2376-2399`); UI capability groups;
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

1. ~~**`uploaded_by` is dead in this codebase.** `rg -n "uploaded_by" src/ apps/ tests/ scripts/`
   returns **zero**.~~ **CORRECTED 2026-08-03 — this was FALSE, and the way it was false matters
   more than the fact.** The grep was accurate. The *inference* was wrong: there is no literal
   `uploaded_by` in `src/` because the passthrough was **structural** —
   `export.transform` copied the whole `attribution` dict, so a draft-authored value flowed into the
   official record with no code ever naming the field. A grep for a field name cannot detect a
   wholesale block copy, and "zero matches" was read as "never written".

   What was actually true until 2026-08-03: a draft carrying `attribution.uploaded_by` passed
   `validate_draft` with **zero errors and no evidence required**, `isaac export` printed
   *"PASS — valid against official ISAAC schema v1.05"*, and the exported record on disk carried the
   client's string — a value that can name a real person, in a field readers are told is
   server-stamped and tamper-proof. Three violations at once: the schema's normative guarantee, the
   no-guessing rule (an unevidenced non-null finalized field), and impersonation.

   **It is now refused, fail-closed, on the RECORD path.** `draft_validator` errors on key presence in
   both record-bound mechanisms — the `attribution` block and the `fields` dotted-path map (three
   spellings, see `_paths_authoring_uploaded_by`) — and `export.transform` enforces a final invariant
   over the assembled record, so no writer can emit the field. Stated precisely: a *list*-valued
   `attribution` slips both draft-side halves and is stopped by official validation as a type error,
   so the guarantee is on the **exported** record, not on `transform` output alone.
   **The evidence sidecar is deliberately NOT filtered** — two revisions of this branch filtered it
   and both were withdrawn, because a denylist over unvalidated caller-chosen key text cannot be
   closed by adding cases, and the filter silently deleted a legitimately-exported descriptor's
   evidence. An exporting draft can still name the field in a sidecar `implicit` entry; the sidecar
   makes no authentication claim, and the same author can write the same name under any key. A first attempt guarded each write
   mechanism individually and an independent adversarial review proved that **non-composing** (it
   found an unguarded second mechanism, and a third was found while fixing it) — hence the single
   chokepoint. See `tests/test_attribution_uploaded_by.py`.

   **Consequence for Q10:** its precondition is now *enforced* rather than merely undecided. ISAAC no
   longer carries a client value in this field, so Dean's answer is free to specify the identifier
   without first having to undo a laundering path. Nothing is stamped, and nothing will be until he
   answers.
2. **`contributors[]` IS fully wired through the truth core** — but as manually-authored,
   evidence-cited draft content, not as authenticated identity:
   `draft_validator.validate_draft`'s contributor loop requires each contributor to cite evidence and
   enforces `name|role` uniqueness; `export.transform` strips the envelope and passes `attribution`
   into the official record, after which `export._enforce_server_owned_invariant` enforces the
   `uploaded_by` refusal; `audit.py` keys sidecar evidence as `attribution:{name}|{role}`
   (`_block_targets`).

   **These are SYMBOL references, deliberately, and that is a correction of method rather than of a
   number.** This paragraph carried line ranges through five successive drifts in a single session —
   `export.py:99-100` stale from an earlier phase, then `draft_validator.py:271-291` which overshot
   the loop, then `270-283` which was correct until the next edit in the same branch, then
   `export.py:229`/`:233` which the descope invalidated and which landed inside an unrelated comment,
   then `279-292`. Every one was caught in review, and each fix was invalidated by the next edit to
   the same file. A line range is not an anchor for code that is still moving; a symbol name is.
   Re-derive with `rg -n "def _enforce_server_owned_invariant" src/isaac_records/export.py`.

**So record-level attribution does not need a new home outside the record.** What is missing is
(a) a decision on which claim populates `uploaded_by`, and (b) recognition that
`contributors[].role` is a **scientific contribution** enum and **cannot double as an authorization
role**. Conflating the two would be a schema-semantics error, not just a modelling shortcut.

---

## 5. Database structures for identity

Dean documents these tables (`postgres-test-db-guide.md:20-22`): `records`, `record_history`,
`templates`, `vocabulary_cache`, `vocabulary_sync_log`, `vocabulary_proposals`, `api_requests`,
`portal_access_log` — **eight**.

> **Open question for Dean, raised 2026-08-01: `record_acl` is missing from that list.** The portal has
> created it since **2026-06-30** — upstream commit `dc5da9c`, PR **#169**, *"Record editing:
> owner+co-author (ACL) edits, versioning, owner-reassign, evidence-drift detection"* (verified:
> `gh api repos/ISAAC-DOE/isaac-ai-ready-record/commits/dc5da9c`), with the DDL at
> `portal/database.py:241`. Dean's guide says the seeded schema *"is identical to the production ISAAC
> records database"*, so either the mirror omits `record_acl`, or the guide's list is incomplete.
> **Do not treat the 8-table list as an authoritative schema statement.** This is recorded as question
> **Q16**; it matters because `record_acl` is precisely the table any collaboration design would build
> on.

### 5.1 The portal's identity model — established by direct source audit, 2026-08-01

This section previously said *"No users table, no groups table, no memberships table is documented …
reported as absence of evidence, not as a negative finding: the portal's own identity model, if it has
one, is simply not described in this repository."* **That hedge is now resolvable, and is resolved.**
The upstream portal repository `ISAAC-DOE/isaac-ai-ready-record` is **public** (`gh api … --jq
'.visibility'` → `public`), so its source was read directly rather than inferred.

**Finding: the portal does not own users or research groups.**

- Enumerating every table it creates
  (`gh api …/contents/portal/database.py | base64 -d | grep -oE 'CREATE TABLE IF NOT EXISTS [a-z_]+'`)
  yields **22** tables across its two databases — the portal DB (`records`, `record_history`,
  `record_acl`, `templates`, `api_requests`, `portal_access_log`, `vocabulary_*`) and the Discovery DB
  (`discovery_meta`, `hyp_*`). **None** is a `users`, `accounts`, `identities`, `groups`,
  `memberships`, `roles`, `permissions`, `teams`, or `organizations` table.
- Identity is a **bare `TEXT` username string sourced from Authentik on every request** — never stored
  as a principal, only as a foreign value on rows: `records.data->'attribution'->>'uploaded_by'`,
  `record_history.actor`, `record_acl.grantee_identity`, `record_acl.granted_by`,
  `api_requests.username`, `portal_access_log.username`.
- It has **no `/me` endpoint, no group endpoint, and no membership API** among its ~60 routes
  (`grep -c '\.route(' portal/api.py` → 60; zero of those routes match `me|group|user`).

**Consequence for ISAAC design: do not imply the portal owns users or research groups.** There is no
upstream identity **service** — no user directory to read, join against, or inherit, and no API that
would expose one. Question **Q12** is therefore **answered — No** (see §7).

**Scope this claim precisely, because it load-bears.** What is established is what the portal's
**source** creates and exposes. The service conclusion is safe on the API evidence: an application
cannot serve users it has no route for. The *database* half is weaker — a table present in the
mirrored schema that `database.py` does not create would not appear in this audit, which is exactly
the guide-vs-code divergence **Q16** documents as live in this same schema. So: **no upstream identity
service to integrate with — proven; no identity table anywhere in that database — not proven, and not
needed for the design conclusion.**

**A second per-identity ACL exists upstream, and this document had not recorded it.** The Discovery
database defines `hyp_project_shares` (`portal/database.py:566-575`): `project_id`, `identity TEXT NOT
NULL`, `access TEXT DEFAULT 'read'`, `granted_by TEXT`, `UNIQUE (project_id, identity)`. So the portal
solves resource sharing **twice**, both times the same way — a per-resource grant row keyed on the
Authentik username string, with no group namespace anywhere. That consistency is itself evidence about
the intended model.

### 5.2 The upstream authorization pattern — a DESIGN SOURCE, not an implementation

`portal/record_authz.py` in the public upstream repository is the closest thing to a ratified ISAAC
authorization model that exists. **It is recorded here as a design source. Nothing in it is
implemented in this repository, and this note does not authorize implementing it.**

It is 71 lines, imports nothing but `__future__`, and its header reads *"PURE LOGIC (no DB, no Flask),
so the entire access-control matrix is unit-tested offline … **Locked after adversarial security
review (2026-06-30)**"*. The rules:

- **Edit rights = admin ∨ owner ∨ explicit `record_acl` editor grant.** Owner is
  `attribution.uploaded_by == caller`.
- **Default deny.** `can_edit_record` returns a reason code, not a bare boolean.
- **Unowned legacy records are admin-only** — explicitly *"never an unowned free-for-all"*.
- **Only the owner or an admin may manage the ACL.** An editor cannot re-grant: no privilege
  delegation.
- **The owner is never an ACL row** — ownership and grants are separate concepts, not two rows in one
  table.
- **Client-supplied `contributors[]` and ORCID confer no rights**, with a named regression test
  `test_orcid_in_body_confers_no_rights` (`tests/test_record_authz.py`).

**Two requirements ISAAC must satisfy if it adopts this pattern.** Both are stated as obligations on
ISAAC, deliberately and not as a stylistic preference: this repository is public, and a requirement
on ourselves carries the whole engineering lesson without describing what any other team's live
system does or does not do.

1. **ISAAC must verify that a grantee exists in the identity provider before writing a grant row,
   and must never treat the existence of a grant row as evidence that its grantee exists.** A grant
   is otherwise just a string write: a typo, a departed user, or a name that was never real would
   all persist indefinitely and read exactly like a valid grant. Whatever ISAAC keys grants on, that
   value must be resolved against the identity provider at write time, and the failure to resolve
   must refuse the write rather than record it hopefully.
2. **The decision layer is separable from the trust layer, and only the decision layer may be
   adopted.** An authorization rule set answers *"given a caller, what may they do"*; it says
   nothing about *"is this really the caller"*. That second question is the boundary §2 of this
   document identifies as the hard part, and it is the one ISAAC must answer on its **own**
   evidence — never by importing a trust mechanism from another team's system, whose operating
   conditions this project cannot observe, test, or fix. So: adopt the decision pattern, and **do
   not** adopt any foreign trust mechanism.

### 5.3 Authentik's groups are coarse deployment-access groups, not collaboration groups

`portal/api.py:66-67` hardcodes `ALLOWED_GROUPS = {"admin", "researcher"}` and
`ADMIN_GROUPS = {"admin"}`. (Naming them here discloses nothing: both already appear in this repository
at `docs/deployment.md:28` and `docs/developer-guide-k8s.md:59`.)

**Do not treat these as ISAAC research-collaboration groups.** They answer *may this person use the
deployment at all*, and every authenticated user of `/krish` is in one of exactly two buckets — which
§3 of this document already records as meaning "the two groups are indistinguishable to the app". They
carry no notion of a lab, a beamtime team, a project, or a co-author set. A collaboration feature keyed
to `researcher` would grant every researcher at SLAC access to every experiment. Note too that upstream
itself does not use them for sharing: it uses per-resource ACL rows (§5.1, §5.2), never group
membership.

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

## 6A. THE OBSERVATION — reported 2026-08-02 against hosted commit `d521dd7`

The temporary probe ran once, in an authenticated session, against hosted commit
**`d521dd70890101d4661ac7d8bed3d419c857fe3f`** (image `v0.0.42`). **Q1, Q2 and Q3 are answered for
the tested path.** The probe has been removed; this section is the durable record of what it saw.

> **This is OPERATOR TESTIMONY, not a captured artifact.** The probe kept nothing — it wrote no file
> and held no state by design — and the response body was not committed. This section is a summary
> table, where the (now-deleted) operating procedure asked for the response *verbatim*.
>
> It additionally rests on two premises that only the operator can confirm: that the canary was planted
> in **all seven** candidate headers, and that it was **distinctive and separator-free**. The procedure
> warned that violating either yields a wrong answer — a canary containing `,` or `|` defeats segment
> matching, and a canary equal to a value the edge genuinely injects produces a false `survived: true`.
> **Neither premise is re-checkable from this repository.**
>
> This is the same standing the DB-recon run has (`CLAUDE.md` §15, and §11 of this file's companion
> note): dated, release-tagged and accepted, but not a re-checkable record. Recorded explicitly because
> this repository has twice had to retract a claim that was stated more firmly than its evidence.

**No identity value was recorded, and none exists to record** — the probe is structurally incapable of
emitting one. What follows is presence, shape, consumption and canary survival, which is the whole of
what it returns. (`consumed_by_isaac` is a code constant from the frozen candidate tuple echoed back,
**not a measurement**. The claim is independently true and re-checkable by grep — §1.2 — which is
better evidence than a single request; it is flagged only so no reader credits the observation for it.)

| Claim | Header | Present | Shape | Consumed by ISAAC | Client canary survived |
|---|---|---|---|---|---|
| Username | `X-authentik-username` | yes | scalar | **no** | **no** |
| UID | `X-authentik-uid` | yes | scalar | **no** | **no** |
| Email | `X-authentik-email` | yes | scalar | **no** | **no** |
| Display name | `X-authentik-name` | yes | scalar | **no** | **no** |
| Groups | `X-authentik-groups` | yes | **list** | **no** | **no** |
| Entitlements | `X-authentik-entitlements` | yes | scalar | **no** | **YES** |
| Edge marker | `X-Isaac-Edge` | yes | scalar | **no** | **YES** |

### 6A.1 What the five core claims prove — and it is stronger than "the canary did not survive"

For `username`, `uid`, `email`, `name` and `groups` the canary was planted by the client and did **not**
come back. The shape column makes that result sharper than a bare "stripped or overwritten", because
`classify_shape` reports `duplicate` whenever a header arrives **more than once**
(`identity_probe.py`, `len(values) > 1`). Every one of these five came back as `scalar` or `list` —
i.e. **exactly one value** — and that value was not the canary.

> **On this path the edge supplied the value, and it did not APPEND.** The client's canary did not
> arrive as a whole value, nor as a `,`/`|`-delimited segment, and only one value arrived — so the
> edge did not add a second header line, and did not coalesce on either separator.

That matters because *append* is the dangerous outcome: the injected value and the forged value both
arrive, and any consumer that reads the first (or the last, or joins them) can be fed the client's
string. Append was specifically looked for and **did not occur** on this path.

> **It does NOT follow that the client's copy was removed, and an earlier draft of this section said
> it did.** `_split_segments` compared only `,` and `|`. Two non-replacement scenarios produce the
> identical observed signature `present ∧ scalar|list ∧ ¬survived`: an intermediary joining the client's
> copy with the injected value using a **separator outside `{",", "|"}`** (a space, a semicolon), or the
> client's copy **passing through transformed** — truncated, re-encoded, case-folded, or quoted. In the
> second case the client *did* influence the header, which is precisely the outcome this paragraph
> claims to exclude. The probe's own limitations said so: `false` means "not found in either compared
> form", **never "provably stripped"**.

**A point worth stating because the intuition runs the other way: `groups` is the STRONGEST case here,
not the weakest.** `list` means one value containing `,` or `|`, and segment matching compared every
segment — so the coalescing attack is *directly* excluded for `groups` in a way it is not for the four
scalars. The transformation hole above applies equally to all five. Note also that the
`groups` result is trustworthy only because of the coalescing fix shipped in this same release: before
it, a canary joined into the list by an intermediary would have been reported `false` — the wrong
answer in the unsafe direction. `false` for `groups` now means the canary is in **no segment** of the
value, not merely that it is not the whole value.

**What it still does not prove.** One request, one path, one moment. It does not establish that every
path strips forged copies, and it says nothing about a caller who reaches the pod's Service directly
(§2, Q4). The probe could not prove the caller was authenticated, and did not claim to.

### 6A.2 Entitlements and the edge marker — the finding, stated more precisely than "influenceable"

`X-authentik-entitlements` and `X-Isaac-Edge` came back **present, `scalar`, and carrying the client's
own canary**. Read the three together:

- `scalar` means **exactly one value arrived**.
- `client_canary_survived: true` means that value **was identical to the canary, up to surrounding
  whitespace** (the comparison stripped each candidate segment).

> **So the one value present was the client's own. The edge contributed nothing to these two headers
> on this path — it did not inject, did not overwrite, and did not strip.**

**This is a correction to a natural but unsupported reading of the same table**, and it is recorded
because the weaker reading was proposed: it is *not* established that "Authentik forwards entitlements
and the edge marker". Their `present: true` is **entirely explained by the client's own request**. Had
the edge also injected a value, the shape would have been `duplicate` (two values) or `list` (coalesced)
— it was neither. On this evidence the honest statement is: **the edge was not observed to supply these
two headers at all, and a client can set them freely.**

Either way the operational conclusion is the same and is **permanent unless infrastructure changes and
is independently re-verified**:

> `X-authentik-entitlements` and `X-Isaac-Edge` are **DISQUALIFIED** from every security decision:
> authentication, authorization, role assignment, proof that Authentik was traversed, and proof that
> the caller is an institutional user. `X-Isaac-Edge` is disqualified from the *one job its name
> implies* — it cannot witness that a request came through the edge, because any client can set it.

**This is a constraint on future implementation, not a live vulnerability.** ISAAC consumes none of the
seven (`consumed_by_isaac: false` throughout, and the backend still reads only `authorization`,
`If-None-Match`, `If-Match`, `X-Filename` — §1.2). Nothing can be spoofed into a decision that nothing
makes.

### 6A.3 UID is now a real candidate, and the §9.1 recommendation is narrowed rather than reversed

`X-authentik-uid` **is present**, which §9.1 could not assume — it was written when no `sub`-style
opaque claim was known to reach the pod at all. So the choice is now live:

- **UID** — likely opaque and provider-owned, the better *lifecycle* candidate in the abstract.
- **Username** — the required **compatibility key**, because every existing upstream ownership, ACL and
  audit row is keyed to it (§5.1). That has not changed and is not a preference.

**Neither is confirmed.** UID permanence and username non-reassignability are both institutional
lifecycle facts that no amount of observation can establish — presence in a header says nothing about
what happens at rename, departure, deactivation or rehire. The likely end state keeps **both**: UID as
the canonical internal key, username as the compatibility alias. **Adopt neither as authoritative until
Q5 and the new Q17 are answered**, and if UID is adopted it must arrive as a migration with a mapping
and an overlap rule, never as a field added because it looks cleaner (§9.1).

### 6A.4 Groups

`X-authentik-groups` arrives as a **list**, consistent with §5.3's finding from upstream source that the
vocabulary is the two coarse deployment-access groups.

> **Recorded knowingly: `list` is a multiplicity signal.** Per `classify_shape` it means one value
> containing a separator — i.e. **at least two segments**. Read against the admission vocabulary this
> repository already publishes (`admin`, `researcher` — `docs/deployment.md`, §5.3), that narrows the
> observing caller toward holding both. This is exactly the *"presence is itself a claim about a
> person"* risk §8 named, now committed durably rather than transiently observed. Three mitigating
> facts, none of which makes it disappear: no group **name** is emitted; the subject is this
> repository's own author; and the complete Authentik group set reaching the pod is unknown (Q7), so
> the inference is not tight.

**Nothing here changes §5.3's verdict:** these
answer *may this person use the deployment*, not *who collaborates with whom*. **ISAAC must not turn a
broad `researcher`-style access group into a shared experiment group** — that would share every
experiment with every researcher. Upstream itself never uses groups for sharing; it uses per-resource
ACL rows.

---

## 7. Decisions only Dean can make

`ISAAC-DOE/isaac-k8` — which holds every Kubernetes, ingress, and Authentik manifest — **is not in this
working tree** and is owned by Dean (`developer-guide-k8s.md:87-89`; `readiness-plan:19-20`;
`infrastructure-ownership.md:21-23`). This repository tracks no YAML except three GitHub Actions
workflows. Dean is therefore the only person who can answer Q1–Q4.

| # | Question |
|---|---|
| **Q1** | **PARTIALLY ANSWERED — deliberately not struck through.** The question asks for the *exact, complete* list of header names the outpost injects. §6A (hosted `d521dd7`) establishes that `username`, `uid`, `email`, `name` and `groups` arrive with edge-supplied values — but the probe tested a **fixed seven-name allowlist**, so what is answered is "which of these seven arrive", never "the complete list". **A header arriving under a name not on that list remains entirely unknown**, and no observation this repository can make will close that gap. Ask Dean only if the complete set matters for a specific design decision. |
| ~~Q2~~ | ~~Which are listed in the ingress `auth-response-headers` annotation and therefore actually reach the app~~ **ANSWERED empirically** — observation at the pod supersedes the annotation question for these five. The annotation's contents remain unread, but the outcome it controls has been measured. |
| ~~Q3~~ | ~~Does the ingress strip or overwrite client-supplied copies?~~ **ANSWERED for the tested path — the edge supplied the value and did NOT append** (§6A.1). Every core claim arrived as a single value that was not the planted canary, and `duplicate` was looked for and did not occur. **It does not follow that the client's copy was removed:** a copy joined on a separator outside `{",", "|"}`, or passed through truncated/re-encoded/case-folded/quoted, yields the same signature. **Scope: one request, one path, one moment**, and it says nothing about Q4. |
| Q4 | Can any workload in the cluster reach the `metadata-assistant` Service directly, bypassing the ingress and therefore Authentik? |
| Q5 | **Sharpened 2026-08-01.** ISAAC's provisional principal is the **Authentik username**, because all existing portal ownership/ACL/audit rows are keyed to it (§5.1, §9.1). The question is therefore no longer "which claim?" but: **is an Authentik/SLAC username non-reassignable across rename, departure, and rehire?** If it is not, what mapping should ISAAC hold, and does any `sub`-style opaque claim reach the pod at all? |
| Q6 | Are forwarded group claims authoritative for in-app authorization, or descriptive only? |
| Q7 | What is the complete set of Authentik groups ISAAC should recognise, and how do they map to app roles? **Context (§5.3):** `admin`/`researcher` are coarse deployment-access groups; upstream uses per-resource ACL rows, not groups, for sharing. |
| Q8 | On session expiry, what exactly does a browser XHR to `/krish/api/*` receive — a 302, a 401, or an HTML login page — and should the app treat all three identically? |
| Q9 | Is there a logout URL the app may link to, and should it be surfaced at all? |
| Q10 | Should this app server-stamp `attribution.uploaded_by` from the forwarded identity per the schema's own description, and from which claim? |
| Q11 | What are the columns of `record_history`, `api_requests`, and `portal_access_log`, and do any store a user identity? |
| ~~Q12~~ | ~~Does the ISAAC portal have a users/groups/memberships model in Postgres that this repository has not been told about?~~ **ANSWERED for the SERVICE — No** (2026-08-01, direct audit of the public upstream source; §5.1). The portal's source creates **22** tables across its two databases, none of them a users/accounts/identities/groups/memberships/roles/permissions/teams/organizations table; identity is a bare `TEXT` Authentik username written onto rows; and there is no `/me`, no group endpoint and no membership API among ~60 routes. **So there is no upstream identity *service* to inherit — that is the part that load-bears, and it rests on the API surface, which the source does establish.** *Precision added after review:* Q12 as originally worded asked about **Postgres**, and this evidence enumerates what the portal's **source** creates. Whether the mirrored database also carries a table `database.py` does not create is **unverified** — the same class of guide-vs-code divergence as **Q16**, which proves that class is live in this very schema. Retained struck-through rather than deleted so the resolution stays visible. |
| Q13 | May the app issue a metadata-only `information_schema.columns` query against those three tables — column names and types, no rows? |
| **Q14 (G6)** | **Do the 30 seeded records contain real personal identifiers in `data->'attribution'`, and does the G2 visibility decision cover personal data as distinct from scientific content?** |
| ~~Q15~~ | ~~May the deployment temporarily enable a presence-only identity probe?~~ **MOOT — the probe has been REMOVED** (2026-08-02). It ran once against hosted `d521dd7`, recorded §6A, and was deleted in a reviewed cleanup PR: the route now returns 404 and a test pins that. **The objection this row invited is preserved rather than erased**, because the sequence was real: the probe shipped *active by default* before you answered, which pre-empted a question that asked your permission. It is recorded so the pattern is visible, not repeated. Nothing is owed on this row now except, if you wish, an objection to how it was done. |
| **Q16** | **`record_acl` is absent from the 8-table list in `postgres-test-db-guide.md:20-22`, yet the portal has created it since 2026-06-30 (upstream `dc5da9c`, PR #169). Does the seeded mirror actually omit it, or is the guide's list incomplete?** (§5) |
| **Q17** | **Is `X-authentik-uid` permanent and non-reassignable across rename, departure, deactivation and rehire?** Raised 2026-08-02: the UID claim is now known to reach the pod (§6A), so it is a live alternative to the username as ISAAC's canonical internal key. Presence is observable; **lifecycle is not** — no request can reveal what happens to a UID when a person leaves and returns. Pairs with **Q5** (the same question for the username); ISAAC likely needs *both* answers, since the probable design keeps UID as the internal key and username as the compatibility alias. |
| **Q18** | **Will the infrastructure strip client-supplied `X-authentik-entitlements` and `X-Isaac-Edge`, or should ISAAC treat them as permanently untrusted?** On the tested path the edge supplied neither and the client's own values arrived untouched (§6A.2) — so `X-Isaac-Edge` cannot currently witness that a request traversed the edge, which is the one job its name implies. ISAAC's position is already "permanently disqualified from security decisions"; this asks whether that is also *your* intent, or whether the annotation is meant to cover them and does not. |
| **Q19** | **May the deployed ISAAC backend read each of the 30 production-derived records through the existing read-only path, clone each record only in memory, apply controlled field removals or schema-invalid mutations, run ISAAC's deterministic workflow, discard every copy, and return only aggregate pass/fail conclusions with no values, identifiers, per-record output, or database writes?** Raised 2026-08-02 for the corpus-validation phase. See the authorization audit recorded with that phase for why this is asked rather than assumed. |
| **Q25** | **RENUMBERED FROM `Q20` ON 2026-08-11, THE SAME DAY IT WAS RAISED — see the note below this table. The question text is unchanged.** **Does your answer to Q10 extend from `attribution.uploaded_by` to ISAAC's own actor columns — specifically the actor on a per-Run field OVERRIDE, on a SUBMISSION, and on each row of a REVISION history?** Raised 2026-08-11 by the scientist-capture programme. **Why this is not already Q10:** Q10 asks about one field of the *upstream official schema*, whose description already invites server-stamping. These three are different in kind — they are **ISAAC-owned application tables** (`isaac_experiments` today, `isaac_runs` and the deferred revision/submission tables of contract §8 D7 later), they are **append-only audit rows rather than a mutable metadata field**, and a wrong or reassigned principal in them **misattributes a scientific decision to a person who did not make it** and cannot be corrected by re-editing a field. So the blast radius differs even if the claim you name is the same. If the answer is "the same claim, stamped the same way", say so and the question closes; ISAAC will not infer that from Q10. **What ISAAC has already built rather than waiting:** the actor seam exists and is deliberately left **unset/unknown** — no client-supplied or user-typed actor is ever accepted as authoritative, and no submitter is fabricated. **The cost of this staying open is bounded and known:** overrides, validation and drafting all work without it; what cannot ship is an *attributed* submission or an *attributed* revision row. |

### The `Q20` collision, and why the actor question is now `Q25` (2026-08-11)

**This question was filed as `Q20` earlier the same day, and `Q20` was already taken.** It is
recorded here rather than silently corrected, because the mechanism that produced it is the exact
one `ai-integration-decision-packet.md:478` had already written a rule against, and a silent fix
would leave the next session free to repeat it.

`Q20` has meant **"may JSON Schema `format` enforcement be armed in the official validator?"** since
before 2026-08-05. That meaning is not merely documented — it is **load-bearing in committed code**:
`authorization.Q20_FORMAT_ENFORCEMENT_APPROVED` (`apps/api/isaac_api/authorization.py:118`) is
`False`, `APPROVAL_QUESTION_REFERENCE` points at `docs/dean-authorization-packet.md`, and **seven
files under `apps/api/` reference `Q20` in total — six besides `authorization.py` itself**
(`grep -rl '\bQ20\b' apps/api/`). An earlier revision said "seven *further* files", which
double-counted `authorization.py`; the number is quoted here at the precision the command supports. The question has also **already been put to Dean** in
that packet, alongside `Q19` — which is answered — so `Q20` is an identifier that has left the
repository and is awaiting an external answer.

**The concrete harm this avoids.** Had the handoff gone out with two live `Q20`s, a one-word reply
from Dean — *"Q20: yes"* — would have been ambiguous between arming a validator gate on the truth
path and authorizing server-stamped actor columns. Nothing downstream could have detected which was
meant, and one of the two readings silently changes official validation behaviour.

**The rule, applied:** identifiers sent to an external decision-maker are **append-only**. `Q1`–`Q24`
were all in use (measured: `grep -rhoE '\bQ[0-9]{1,3}\b' docs/ apps/ src/`), so the actor question
takes the next free number, `Q25`. `Q20` keeps its established meaning and is untouched. Nothing was
shifted.

---

## 8. Why a typed identity context is NOT being built now

The design does not strictly require knowing the header names: an env-supplied allowlist defaulting to
empty, returning `Principal | None` that is `None` unless every configured header is present, would be
a pure no-op in every current environment, exhaustively testable with synthetic headers, and would
never touch the truth core. The codebase already contains three reviewed instances of the needed
pattern — frozen-allowlist projection (`_DB_RECON_DATABASE_KEYS`, `routes.py:3340`),
raise-on-unlisted-key (`:3413-3419`), and an unconditional leak guard (`db_recon.scan_for_leaks`,
`:3439` and `:3762`). *(Line numbers refreshed 2026-08-01 after the +82 shift from `0d0a089`; re-derive
by symbol rather than trusting them.)*

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

> **⚠ HISTORICAL — READ THIS FIRST (added 2026-08-02). The probe described below is GONE.** It was
> removed the day after this block was written; the route returns 404 and a test pins that. Everything
> from here to the end of §8 is written in the present tense about a deployment state **that no longer
> exists**, and is kept because the reasoning — why an identity *seam* is still forbidden, and why a
> measurement instrument was not an exception to that — is still the governing decision. **The
> "residual risk … carried knowingly" paragraph below is discharged: that risk ended with the
> endpoint.** References below to `docs/identity-probe.md` point at a deleted file; its removal
> checklist was executed in full, and what the observation found is §6A of this document.
>
> **The decision itself is unchanged and still binds: do not build an identity seam.** §6A answers
> Q1–Q3 for one path; Q4 and Q6 remain open, and §6A.2 adds a permanent disqualification that no
> answer to Q4 or Q6 will lift.

> **Reconciliation, 2026-08-01 — this decision STANDS, and a probe is not an exception to it.**
>
> A temporary observation probe (`POST {base}/api/runtime/identity/probe`) was authorized and built
> after this section was written. That is not a reversal: §8 forbids an identity **seam** — a
> `get_principal()`-shaped affordance that a later slice can consume. The probe consumes nothing,
> exports no principal type, returns no value, persists nothing, and is scheduled for removal. Every
> one of the three reasons above still holds, and reason 1 in particular is why the probe must not be
> allowed to grow into `identity.py`.
>
> **Two deliberate divergences from the design sketched below, both recorded rather than quietly
> applied:**
>
> 1. **`GET` → `POST`.** The canary must travel in the request **body**. Uvicorn runs with default
>    access logging (`Dockerfile:50`), which writes the request line — including any query string —
>    to stdout. A canary in a query parameter would be logged; a body is not.
> 2. **`ISAAC_IDENTITY_PROBE` EXISTS, but its polarity is inverted: it is a kill switch, default ON,
>    not an enabler, default OFF. This is a genuine weakening of the design below, not a
>    technicality.** Setting a default-OFF switch means editing `isaac-k8`, which Dean owns, and the
>    authorizing instruction for this slice explicitly required *no new secret and no infrastructure
>    change*. A gate nobody is permitted to open does not make the probe safer — it makes it
>    incapable of ever observing anything, leaving the header contract unmeasured indefinitely. So
>    the switch is retained for the property that is actually worth having: setting it to a falsy
>    value disables the probe **without a code deploy**. An unrecognised value fails towards ON, so a
>    manifest typo cannot silently mute the probe and manufacture an empty result that reads like the
>    substantive finding "no identity header arrives".
>
> The compensating controls, stated so the trade is auditable: the probe returns **no value of any
> kind** — its maximum disclosure is a boolean vector over a fixed tuple of header names that is
> already public in this repository's source and documentation; **ISAAC consumes none of those
> headers**, so a forged one currently accomplishes nothing; and removal is a committed follow-up,
> not an aspiration (`docs/identity-probe.md` — **deleted 2026-08-02 with the probe; the removal was
> carried out in full**).
>
> The residual risk below is **not** neutralised by those controls and is carried knowingly: the
> probe is an ingress-configuration oracle for a caller who holds **both** an authenticated edge
> session **and** direct in-cluster network reach. That conjunction is not far-fetched at a national
> laboratory. It is bounded today only because no header is trusted by any code path, which is
> exactly the condition that ends the moment Q1–Q4 are answered — so the probe must be removed
> *before*, not after, any identity seam is built.

### If a runtime probe is later authorized (design only — nothing implemented)

`GET {base}/api/runtime/identity/probe`, returning **only**: `authenticated` (bool);
`claims_present` as `{name: bool}` **projected onto a compile-time constant tuple of header NAMES**;
`claim_source` as a code constant; `probe_contract_version`; and fixed `limitations` strings.

Never, under any circumstance: a header **value** (not truncated, not hashed, not length-reported);
an **unlisted** header name (projection, never a filter — a filter can leak a name, a projection
cannot); any **count** of headers received (that number fingerprints the ingress config); any echo of
`Authorization`, `Cookie`, or `X-Filename`; any logging of the probe's inputs.

Safety requirements: env-flag gated **default off** (`ISAAC_IDENTITY_PROBE`) **[SUPERSEDED, then MOOT —
the probe that shipped inverted this to a kill switch, default ON; it has since been removed entirely.
See the historical banner at the head of this block.]**, checked before the
request object is touched; the `strict=True` raise on the success path only (re-derive the surviving
example with `rg -n '_DB_RECON_DATABASE_KEYS' apps/api/isaac_api/routes.py` rather than by line number —
the two line citations that stood here, `:3643` and `:4041`, are **dead**: the probe's removal shortened
`routes.py` and `:4041` no longer exists; the comment above `_DB_RECON_DATABASE_KEYS` explains why the
failure envelope must *not* raise); the
existing unconditional leak guard; contract
tests asserting the exact key set, including that an unlisted header produces no observable difference
in the response bytes; and **time-bounded use** — enable, observe once, disable. It is a measurement
instrument, not a feature.

Risks, stated not minimised: it is an **ingress-configuration oracle** — `claims_present` is precisely
the list of header names to forge for an attacker who can reach the pod directly (§2). Presence is
itself a claim about a person (`groups: true` on a deployment admitting only two groups narrows the
caller). A point-in-time observation invites false confidence, since Dean can change the provider's
header set with no signal to this repo. And with `ISAAC_UI_API_KEY` unset in production, the env flag
is the **only** real gate — which is exactly why it must default off. **[SUPERSEDED — the shipped
probe defaults ON, so this gate is not gating anything until someone sets it. The burden is carried
instead by the fact that the operation cannot emit a value, that ISAAC consumes none of these headers,
and that removal is a committed follow-up. See the reconciliation block above.]**

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

### 9.1 What ISAAC should use instead — corrected 2026-08-01

This section previously concluded: *"What would be safe instead: an opaque, immutable,
non-reassignable subject claim (an Authentik `sub`/UUID, if one is forwarded), with a display name
resolved separately and never used as a key."* **That recommendation was made before the upstream
portal's storage model had been read, and it is superseded.** It is kept because it names a real
property worth wanting; it is corrected because acting on it would fork the identity namespace.

**The position to adopt, stated once and to be reproduced wherever the stable identifier is
discussed:**

> **Authentik username is the required compatibility key and the provisional ISAAC authorization
> principal, because existing portal ownership, ACL, and audit data are keyed to it. Institutional
> confirmation is still required that usernames are non-reassignable across rename, departure, and
> rehire lifecycles.**

Two halves, and neither may be dropped:

1. **Compatibility is not a preference.** §5.1 establishes by direct source audit that every upstream
   ownership, grant, and audit row stores a bare Authentik username string —
   `records.data->'attribution'->>'uploaded_by'`, `record_history.actor`,
   `record_acl.grantee_identity`, `record_acl.granted_by`, `api_requests.username`,
   `portal_access_log.username`, `hyp_project_shares.identity`. Those rows are already written. An
   ISAAC principal that is anything else cannot be compared to them without a mapping that does not
   exist.
2. **Username stability is a *technical stable-ID candidacy*, never an *institutional lifecycle
   guarantee*, and the two must never be stated as the same thing.** Nothing observed establishes that
   a SLAC/Authentik username is non-reassignable after a rename, a departure, or a rehire. Until an
   institution says so, "username is the key" means "username is the key we are compatible with", not
   "username identifies one human forever". That confirmation is question **Q5**, and it is
   **unanswered**.

**Do not introduce a second identity namespace based on `sub` without an explicit migration and
compatibility plan.** An opaque `sub` has better lifecycle properties in the abstract, but adopting it
alongside the username produces two principals for one person, with every existing portal row keyed to
the one ISAAC would not be using. If `sub` is ever adopted it must arrive as a migration — a mapping
table, a backfill, and a rule for which key authorizes during the overlap — not as a new field added
because it looked cleaner.

**ORCID is disqualified for this role, explicitly and permanently.** ORCID is **scientific-credit
metadata** — `attribution.contributors[].orcid`, alongside `name`, `affiliation`, `email` — and it
**must never confer authorization**. This is stated as a forward guard because the temptation is now
concrete rather than hypothetical: ORCID is visibly an *authentication* option at the Authentik login
page (see `developer-guide-k8s.md` §4, observed 2026-08-01), and upstream has already had to defend
against exactly this confusion — `portal/record_authz.py` treats client-supplied `contributors[]` and
ORCID as conferring **no** rights, guarded by a named regression test
`test_orcid_in_body_confers_no_rights` (`tests/test_record_authz.py`). Authenticating *via* ORCID and
being *credited* by ORCID are different facts; a record's contributor list is a scientific claim
authored by a human, not an access-control list.

---

## 10. Classification summary

| PROVEN (this repo) | NOT PRESENT IN THIS REPO | UNKNOWN — REQUIRES DEAN |
|---|---|---|
| Identity header names confined to **2 files, both documentation** — **none consumed by any code path** (§1.1). **No match total is quoted**; §1.1 records why. ~~"Zero identity headers anywhere (0 matches …, excluding the two docs that name them)"~~ and ~~"4 files — 61 matches, all measurement apparatus or documentation"~~ — both superseded. Note what happened to this cell, since it is a correction record that then repeated the failure it recorded: the first version survived a count refresh (498→501) that fixed the number beside it and left the false claim standing; the second outlived the probe by a day and this cell by two. **That is why the total is now omitted rather than maintained.** | Any k8s / ingress / Authentik manifest | The header names the outpost injects (Q1) |
| Backend reads exactly 4 headers, none identity | Any users / roles / groups / permissions model | Whether the ingress strips client copies (Q3) |
| `ApiKeyAuthMiddleware` = one shared secret, fail-open, **unset in prod** | Any logout, session, or expiry logic | Whether the pod is reachable bypassing the ingress (Q4) |
| No trusted-proxy config, no header-stripping middleware | Any record ownership or actor attribution | The intended subject-identifier claim (Q5) |
| SPA has no user/session/profile concept — every match is a false positive | ~~`uploaded_by` in any code — schema-only, 2 lines~~ **CORRECTED 2026-08-03: `uploaded_by` IS now in code** — refused in `draft_validator.py` and `export.py`, with `tests/test_attribution_uploaded_by.py`. It was never merely "schema-only": the passthrough was structural. See item 1 of "Two consequences" above. *(This cell was missed when the same commit corrected three other sites — exactly the failure the correction record three rows down warns about.)* | Columns of `record_history` / `api_requests` / `portal_access_log` (Q11) |
| Schema defines `attribution.uploaded_by` + `contributors[]` | `PII`/`email`/`username` in any DB-governance doc — **zero mentions** | Whether seeded rows carry real personal identifiers (Q14 / G6) |
| Recon already queries `information_schema`; table inventory computed but **not served** | — | Whether group claims may be authoritative in-app (Q6) |
| Edge is an Authentik proxy outpost — observed at `/outpost.goauthentik.io/start` | — | Whether `/krish` works **now**. **Amended 2026-08-01:** a rollout of `v0.0.38` and a recon run against it *were* observed by Krish (operator testimony — see the baseline matrix §0, Entry 2). **G1 is narrowed, not closed:** what is owed is the captured JSON, not the run. Unauthenticated probes from an agent session still return 302 |
| **Upstream portal owns no users or research groups** — 22 tables, none identity; bare `TEXT` Authentik username on rows; no `/me`, no group endpoint, no membership API (§5.1, public-source audit) | Any upstream user directory to read or join against | Whether an Authentik username is non-reassignable across rename/departure/rehire (**Q5** — a technical stable-ID candidate is not a lifecycle guarantee) |
| **Upstream `record_authz.py` is a locked, adversarially-reviewed authorization pattern** — admin ∨ owner ∨ ACL editor, default deny, no delegation (§5.2) | Any ISAAC implementation of it — **none exists, and none is authorized** | Whether the mirrored schema actually contains `record_acl` (**Q16**) |
