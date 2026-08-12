# Settings & API / connectors — capability audit

**Audited:** 2026-08-08, at main `fb971ae`. Read-only; no file was changed by the audit itself.

Measured surface: **39 `@router.<method>` registrations over 38 distinct paths** in
`apps/api/isaac_api/routes.py`. `_R_UNAUTHORIZED` is referenced 38 times outside its
definition — every operation except the liveness check documents a 401.

---

## 1. Capability table

| Capability | Build now? | Production ready? | Dean needed? | Exact missing requirement |
|---|---|---|---|---|
| HTTP API + self-generated OpenAPI | built | **yes** | no | nothing; `GET /api/openapi` returns `app.openapi()` unfiltered (`routes.py:3795-3804`) |
| **Programmatic access to the deployed API** | **no — infra-blocked** | **no** | **yes** | an ingress path or Authentik service token admitting a non-browser caller. `docs/developer-guide-k8s.md:79-80`: *"Scripted access (curl) to the deployed URL won't work without a browser session."* No app change fixes this. |
| Shared-secret bearer auth | built | code yes; **inactive in prod** | yes, to activate | `ISAAC_UI_API_KEY` set in the Deployment. Unset in k8s (`docs/deployment.md:86`), so `auth.py:41-42` passes **every** request through. **The Authentik edge is the sole control.** |
| Per-user API keys (issue/list/revoke/rotate) | **no — authorization** | no | **no** | no route exists. Needs credential table, hash-at-rest, revocation, scopes, audit — all app-owned. Blocked by `CLAUDE.md` §15 (Phase 37) **and** by the no-durable-persistence rule. |
| **OAuth / OIDC client in this app** | no | **no — does not exist** | no to build; yes to register | **Zero OAuth/OIDC implementation in the repo.** Grep returns only comments and negative test guards. "The deployment sits behind an OIDC proxy" ≠ "this app supports OAuth". |
| Callback / redirect URL | no | **none exists** | yes, to register | no `redirect_uri`/`client_id`/`client_secret` anywhere. The *route* is app-owned; the *registration* is Dean's. |
| Consuming edge identity | no | **no** | **yes** | ISAAC consumes none of the seven `X-authentik-*` headers. Needs **Q4** answered. `X-authentik-entitlements` and `X-Isaac-Edge` are permanently disqualified — a planted client value arrived untouched. |
| Application roles | **no — authorization** | no | no | no user model, no role model. Phase 37, not authorized. |
| **Server-side secret storage** | **no — absent entirely** | **no** | no | grep for `keyring\|vault\|fernet\|cryptography\|bcrypt\|argon2\|passlib\|jwt` across the API package and both manifests: **zero hits**. Every secret comes from process env and is never persisted. |
| Reading a k8s Secret | works indirectly | yes | yes for a *new* one | Secret `metadata-assistant-db-app` is projected into pod env. A new secret needs an `isaac-k8` manifest change. |
| **Third-party connectors** | no | **none exist** | no | no connector framework, no provider registry, no integration of any kind. |
| Outbound egress | n/a | deliberately none | no | no `requests`/`httpx`/`urllib`/`aiohttp` in the API package. The only outbound socket is libpq to the in-cluster Postgres; `sslmode` defaults to `require` — encrypts without verifying the server cert (disclosed `db_recon.py:1820`). |
| In-cluster Postgres read (aggregate) | built | **yes** | no — granted | `Q19` approved; `PGHOST` is the switch, `PGDATABASE` pinned. |
| Per-record DB display | **no — owner decision** | no | **yes** | gate **G2**; closed by default pending an explicit visibility decision. |
| External LLM | **no — authorization** | no | no | no provider client, no key seam. Phase 37. |
| File upload | no — governance gate | refusal is production-ready | no | `POST /api/uploads` always 403 by design (`routes.py:2882-2913`). |
| **`VITE_API_KEY` frontend seam** | **REMOVED 2026-08-08** | n/a — the seam no longer exists | **no — app-owned** | ~~`api.ts:102` reads `import.meta.env.VITE_API_KEY`~~. The reader and the `Authorization: Bearer` attach are **deleted**. Vite substitutes `VITE_*` **at build time**, so any value would have been compiled into the JavaScript served to every visitor — a bearer token published as public JS is not an authentication control. It was never set (`Dockerfile:22` passes only `VITE_BASE_PATH`/`VITE_API_BASE`), but a Phase-20 plan doc described baking in the same value as `ISAAC_UI_API_KEY`, which is precisely "expose secrets to the frontend". `__tests__/api.test.ts` now pins the inverse with the key **planted**: a set `VITE_API_KEY` must produce no `Authorization` header and must not appear anywhere in the request. |
| Inbound webhooks | no | none exist | no | no inbound integration route, no signature primitive. |

---

## 2. Application-owned — do NOT ask Dean

Escalating any of these wastes the infrastructure owner's time.

1. ~~**Remove or gate the `VITE_API_KEY` build-time seam** (`api.ts:102`).~~ **DONE 2026-08-08** — removed outright rather than gated. The residual consequence is deliberate and is recorded rather than hidden: the backend's `ISAAC_UI_API_KEY` seam still works, so a deployment that sets it will now 401 the browser client, which has no way to authenticate. `ISAAC_UI_API_KEY` is henceforth a control for **non-browser callers**, the only kind that can hold a shared secret without publishing it.
2. **Every item on the API-key requirements list** (`settingsContent.ts:486-492`) — hashed storage, per-key identity, revocation, expiry, scopes, audit. All backend code. (Blocked on *Krish's* phase approval, not Dean's.)
3. **A callback route**, if OAuth is ever built. Only the *registration* is Dean's.
4. **The Connect-an-Agent honesty fix** (§5 A and B). Copy only.
5. **CORS policy** (`app.py:42-45`).
6. **`PGSSLMODE` hardening to `verify-full`** — the app already names this as the remedy; it chooses the default.
7. **Making the Endpoint Explorer's auth marker deployment-accurate.** The backend knows whether the key is set and could report a boolean on `/api/health` without disclosing the value. Today's "cannot see whether it is switched on" is a limit of what the app chose to expose, not a fact about the world.
8. **Remove `RAILWAY_GIT_COMMIT_SHA`** (`routes.py:662`) — dead retired-platform fallback.

## 3. Genuinely blocked on the infrastructure owner

| # | Blocked | The one question |
|---|---|---|
| D1 | Any headless access to the deployed API | *Can `/krish/api/*` have an ingress path that bypasses Authentik forward-auth for a caller presenting ISAAC's own bearer key — or must all access go through an interactive session?* |
| D2 | Machine credentials via the IdP | *Does the Authentik outpost support a service-account/API token for headless callers to `/krish`?* |
| D3 | Trusting edge identity (**Q4**) | *Can any in-cluster caller reach the Service directly, bypassing the Authentik ingress?* |
| D4 | Turning on the app's own bearer auth | *Would you add `ISAAC_UI_API_KEY` from a Secret to the Deployment?* — app-side work is **zero**. |
| D5 | Registering ISAAC as an OAuth client | *Would you register ISAAC as an Authentik application with a redirect URI under `/krish`?* — ask only after §4 authorizes building the client. |
| D6 | Per-record display (**G2**) | *May ISAAC display individual record content in the hosted UI, and to whom?* |
| D7 | The five withdrawn aggregates (**G3**) | *Were they within your intent when you authorized aggregate output?* |
| ~~D8~~ | Identity permanence (**Q17**, **Q5**) | ~~*Is `X-authentik-uid` permanent, and is a username never reassigned?*~~ **ANSWERED 2026-08-12: usernames are NOT reassigned; the username is canonical; Q17 should NOT be reopened and no UID↔username infrastructure should be introduced.** The UID half was declined rather than answered — see `identity-trust-contract.md` §7 Q17. |

> **STATUS OF THIS TABLE AFTER DEAN'S 2026-08-12 RESPONSE.** **D3 is answered, and answered badly for
> us:** yes, any in-cluster caller can reach the Service directly — plain ClusterIP, no NetworkPolicy
> — so forwarded identity headers are forgeable and **`X-authentik-username`'s presence does not prove
> authenticated edge traversal**. Dean named the resolution pattern (trusted-edge for browser/UI
> traffic, independent Bearer validation for API/service traffic), which bears directly on **D1**,
> **D2** and **D4** — but he did **not** answer any of those three, nor **D5**, **D6 (G2)** or **D7
> (G3)**. Do not read the pattern as an approval of a specific mechanism. **These `D` identifiers are
> local to this audit** and are a different series from `ai-integration-decision-packet.md` §5's
> D1–D9, which Dean deferred wholesale; see that document's DO-NOT-RENUMBER box.

## 4. Blocked on authorization, not engineering — needs Krish, not Dean

Per-user API keys · **any durable persistence** (a hard prerequisite for the credential store, so API keys are *doubly* blocked) · identity/role enforcement · external LLM · portal integration · **Q20** format enforcement (`authorization.py:118` = `False`) · any `isaac-k8` change.

**Amended 2026-08-12.** Two entries move without leaving the list. **`Q20` format enforcement is now
answered — and answered "no"**: shadow mode is allowed (read-only, aggregates only, non-gating,
outside the truth plane), arming the official validator is **not** authorized, so `authorization.py`'s
`False` is confirmed rather than pending and the entry stays blocked by decision instead of by
silence. **"External LLM"** stays blocked for a *production* provider — Dean **deferred D1–D9** — while
the project owner has separately authorized **implementing** the provider architecture against
deterministic fake providers; building it is not connecting it. **Durable persistence** is no longer
blanket-blocked either: `isaac_experiments` and `isaac_runs` are both applied to the hosted database
(2026-08-09, 2026-08-12), under the narrow 2026-08-07 lift — which still authorizes no credential
store, so per-user API keys remain blocked on their own merits.

---

## 5. Claims the UI makes that the backend does not support

**No outright false sentence was found.** The defect is subtler and worse: a **false affordance created by de-duplication.** The tab's honest disclaimers were consolidated into one component, and a *different* component now presents an eight-step guide to something impossible on the deployment the reader is looking at.

**A — HIGH. "What an API Key Would Enable" is false for this deployment.**
`settingsContent.ts:468-471` states unconditionally that a program *"could call the operations listed on the Endpoint Explorer tab directly."* On the hosted deployment an API key enables **none of that** — Authentik rejects the request before it reaches ISAAC. Missing clause: *"…on a deployment that does not sit behind an interactive identity layer."*

**B — HIGH. "Connect an Agent" is an integration guide to an impossible integration.**
`ConnectAnAgent.tsx:73-107` gives eight steps under the lead *"only what this build actually supports"* (`:118-121`). No sentence is false, but it never says **no agent can connect at all on this deployment** — and the omission is documented as deliberate (`:22-25`): the boundary was de-duplicated out to a *sibling* component. Since `ConnectAnAgent` is itself a `<details>` a reader can open alone, they get step-by-step instructions with the disqualifying fact one component away.

**C — MODERATE.** "How Access Works Today" (`ApiKeys.tsx:114`, `settingsContent.ts:461-466`) asserts the credential is *"required on every operation except the liveness check."* In the deployed build it is required on **zero**. The trailing "this screen cannot see whether it is switched on" rescues it only if read. The same file gets the modality right elsewhere (`:340`, *"can additionally require"*).

**D — MODERATE.** The Quick Start auth row (`ApiDocs.tsx:189-197`) says the credential is *"sent on every call that needs it"* with an honest 401 count — but on the hosted build **no** operation will ever return a 401 from the application. The legend hedges; this row does not.

**E — MODERATE.** "Technical Requirements" (`settingsContent.ts:441,486-492`) lists five app-owned requirements and **omits the one that is not ours**: even with all five built, a program still cannot reach the hosted API. A reader takes this as the full path to shipping; it is the app half.

**F — LOW/MOD.** *"institutional single sign-on"* (`settingsContent.ts:340`). An observation of the Authentik flow found only Email/Username and ORCID — no SLAC SSO button at that stage, and later stages **unobserved**. The copy cannot name the vendor (tests forbid `authentik|sso|oauth|saml` on Settings tabs), so the fix is to **weaken** the claim, not specify it.

### Verified NOT findings
"Endpoint Explorer lists every operation" — **true** (unfiltered `app.openapi()`; the only excluded routes are SPA static fallbacks, not operations) · the disabled Create-API-Key button is genuinely disabled with an `aria-describedby` reason, no fake key · `ConnectAnAgent.tsx:85` is correctly modal · "no third-party network requests… loads nothing from a CDN" — verified for the frontend · `API_ACCESS_ROWS[2]` *"browsing this page does not give a program a way in"* is the sharpest true sentence on the tab.

---

## Bottom line

**API access as a product capability does not exist on the deployed instance.** The API is real, complete and documented; the path to it is not. `ApiKeyAuthMiddleware` is a pass-through no-op in production, so the Authentik edge is the sole control — and it admits browsers only.

**There is no OAuth, no OIDC, no callback URL, no secret storage, and no connector of any kind.** Not stubbed, not partial — absent.

**The single most consequential correction** is to carry `settingsContent.ts:473-476` into Connect-an-Agent and into "What an API Key Would Enable", and to add the edge requirement to Technical Requirements. All three are copy-only, application-owned, and need nothing from Dean.
