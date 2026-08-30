# Remote MCP + OAuth — operator requirements

**For:** Dean (infrastructure / Authentik operator), and whoever administers the SLAC Claude
organization. **From:** Krish Verma. **Date:** 2026-08-27.
**Prepared by an agent; not sent by one. Krish forwards this or does not.**

**NOTHING HERE IS A REQUEST TO ACT.** It is a specification of what *would* be required if the
project decides to expose ISAAC's MCP interface to a scientist's own Claude. **D1 (public
reachability) and D2 (auth model) were deferred on 2026-08-12 and neither has been narrowed
since.** This document does not reopen them; it makes them answerable by replacing "configure
OAuth somehow" with a checklist that can be costed.

**Nothing in ISAAC is blocked on this.** The application is correct today and stays correct if
this is never actioned — the MCP route is **not registered at all** in the hosted deployment
(see §1), which is why the product screen truthfully says no agent can connect.

**Source of every vendor requirement below:**
[`docs/vendor-documentation-audit-2026-08-27.md`](vendor-documentation-audit-2026-08-27.md),
which fetched the vendor's own documentation on 2026-08-27 and records its limits. Requirements
are quoted there; this document does not re-derive them.

---

## 1. Current state, measured — not "not configured yet" but "structurally absent"

Verified in the hosted deployment on 2026-08-27 (authenticated session, read-only):

- `GET /krish/api/health` → `commit: 6d5bda61ce4b…`, i.e. the deployment serves `main` exactly.
- **The MCP route does not exist.** `app.py:313-328` registers it only when
  `ISAAC_MCP_DEPLOYMENT` is non-empty **and** the resolved binding declares `serves_transport`.
  `resolve_binding` (`mcp/deployment.py:500-525`) answers `UnconfiguredDeployment` for unset,
  empty, unrecognised or reserved values, and `UnconfiguredDeployment.serves_transport` is
  `False` (`deployment.py:340`). So there is no endpoint to secure, and no request can reach an
  MCP tool.
- The only binding that serves anything is **`local-loopback`**, which refuses a non-loopback
  socket peer, refuses any request carrying proxy headers, refuses a non-loopback `Origin`, and
  **refuses a credential outright** (`deployment.py:402-470`). It is a developer affordance and
  is not reachable through the edge.
- `oauth-resource-server` and `edge-issued-bearer` exist as **reserved, deliberately
  unregistered names** (`deployment.py:150-161`). Selecting one resolves to unconfigured. They
  are placeholders for exactly the two answers D2 could take.

**Consequence for the reader: nothing is half-open.** There is no misconfiguration to correct
and no exposure to close. The work below is greenfield.

---

## 2. The one genuinely new networking requirement

> **Anthropic's outbound traffic originates from `160.79.104.0/21`.**

This is the item no previous ISAAC document contained, and it is the one most likely to cause a
silent failure. It applies to **two** hosts, not one:

| Host | Why it must be reachable from `160.79.104.0/21` |
|---|---|
| The **MCP endpoint** itself | Claude connects out from Anthropic's infrastructure to your server |
| The **Authentik issuer host** | OAuth **discovery** requests come from the *same* range |

The vendor states the failure mode explicitly: *"a WAF in front of your identity provider can
break the flow even when your MCP server is reachable."* The symptom is diagnostic — the MCP
server receives the initial request and the authorization server sees **no traffic at all**.

**If SLAC will not allowlist an external range to Authentik, the remote-connector path is not
viable and D1 should be answered "no" on that basis.** That is a legitimate answer and is
cheaper to give now than after the code exists. See §7 for what ISAAC does instead in that case.

---

## 3. Endpoint and metadata requirements

### 3.1 Transport

**Streamable HTTP.** Not SSE — the vendor's Claude Code documentation states *"The SSE
(Server-Sent Events) transport is deprecated. Use HTTP servers instead."* ISAAC's transport is
already HTTP-only and refuses SSE and WebSocket by construction (`mcp/transport.py:282-297`,
`:225-228`), so **no ISAAC change is required here**.

### 3.2 The 401 handshake

The server must answer an unauthenticated request with:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer resource_metadata="https://<host>/.well-known/oauth-protected-resource"
```

Two constraints that are easy to get wrong:

- **The `401` status is required.** The vendor does not honour `WWW-Authenticate` on a `200`.
- **The `resource_metadata` URL need not be on the MCP server's origin.** It may be any HTTPS
  location serving the JSON. **This is the escape hatch for the Authentik edge** — ISAAC does
  not have to persuade the edge to serve `/.well-known/*` at the site root.

### 3.3 Protected-resource metadata (RFC 9728)

```json
{
  "resource": "https://isaac.slac.stanford.edu/krish/api/mcp",
  "authorization_servers": ["https://<authentik-issuer>"],
  "scopes_supported": ["isaac:read", "isaac:draft.write"]
}
```

- **`resource` must match the URL the user types into Claude, EXACTLY, including the path.**
  ISAAC's deployment is path-mounted at `/krish`, so this is a live mismatch risk that would
  otherwise be found only by trial and error.
- **`authorization_servers`: Claude uses the FIRST entry and does not fall back.** List the
  primary issuer first.
- The two scopes are ISAAC's, already defined and closed (`mcp/policy.py:73-87`). There is no
  third scope and neither means "may submit" (§5).

### 3.4 Authorization-server metadata (Authentik side)

Authentik must serve RFC 8414 or OIDC Discovery metadata at its `/.well-known/` paths, and that
metadata must advertise:

| Key | Required value | Why |
|---|---|---|
| `code_challenge_methods_supported` | must include `"S256"` | Claude sends `code_challenge_method=S256` on **every** authorization request |
| `registration_endpoint` | present **or** choose an alternative (§3.5) | Claude's default registration mechanism is DCR |
| `scopes_supported` | should list `offline_access` if refresh tokens are wanted | Claude appends it when advertised |

### 3.5 Client registration — three options, and a recommendation

| Option | What it needs | Note |
|---|---|---|
| **DCR** (RFC 7591) | Authentik exposes `registration_endpoint` | Registers a **new client on every fresh connection**. For a handful of scientists this is fine; the vendor warns against it only at directory scale |
| **CIMD** | metadata must advertise **both** `"client_id_metadata_document_supported": true` **and** `"none"` in `token_endpoint_auth_methods_supported` | If either is missing Claude silently falls back to DCR |
| **Anthropic-held credentials** | email `mcp-review@anthropic.com` with a `client_id`/`client_secret` | Consent-gated; **an external party then holds a SLAC credential** — likely a non-starter here, and named only for completeness |

**Recommendation: DCR if Authentik supports it, else static per-organization client credentials
entered when the connector is added** (the vendor allows an admin to supply their own client ID
and secret when adding a custom connector, which scopes the OAuth client to that organization
and avoids DCR entirely). **This is a recommendation, not a decision — D2 is Dean's.**

### 3.6 Redirect URIs to register

| Client | Redirect URI |
|---|---|
| Claude web / Desktop / mobile | `https://claude.ai/api/mcp/auth_callback` |
| Claude Code | RFC 8252 loopback on an **ephemeral port**. Claude Code declares `http://localhost/callback` and `http://127.0.0.1/callback`; **the authorization server must accept both with the port component ignored** |

The port-agnostic loopback match is the detail most likely to be missed, and it fails closed and
confusingly (the browser completes login and the client reports a redirect mismatch).

### 3.7 Token endpoint

- Must accept `Content-Type: application/x-www-form-urlencoded` (RFC 6749 §4.1.3). Note that
  `/register` uses `application/json` — different parsers.
- Must return **`invalid_grant`** (not a custom code) for a dead refresh token.
- Should **rotate refresh tokens** — DCR and CIMD register Claude as a *public* client.
- **Latency budget: 10 s** for discovery, registration and token; **30 s** for refresh. A slow
  endpoint produces intermittent, hard-to-diagnose connection failures.

---

## 4. Organization connector administration

For Team/Enterprise, an **owner** adds it at **Organization settings → Connectors → Add →
Custom → Web**, enters the URL, optionally supplies OAuth client credentials under Advanced.
**Members** then connect individually at **Customize → Connectors → Connect**.

Two facts worth knowing before scoping this as "an org-admin project":

- Free/Pro/Max users **can add a custom connector themselves**. A two-scientist pilot does not
  strictly require an org-wide connector to *connect* — though it still requires everything in
  §2 and §3.
- **A shared static credential is available in beta (`static_headers`) and ISAAC should not use
  it for writes.** It is one credential for the whole organization; ISAAC's invariants require a
  per-scientist verified identity for attribution and revision authorship. It would be
  acceptable only for a read-only, non-attributing demonstration.

---

## 5. What this does NOT change, and must not be read as changing

- **No agent can submit.** Submit is absent from the tool set by two independent mechanisms
  (`policy.FORBIDDEN_TOOL_TOKENS` and the closed `OPERATIONS` table). OAuth does not add it, and
  there is no scope that grants it. The vendor's own protocol makes tool annotations *hints, not
  enforcement*, which is why ISAAC's refusal is structural rather than advertised.
- **The production-derived `records` corpus stays unreachable**, independently of any token.
- **Gate G2 (per-record hosted display) stays closed** and is untouched by this.
- **Actor stamping stays unset.** OAuth would, for the first time, give ISAAC a *trusted*
  per-request identity — which is the precondition
  [`identity-trust-contract.md`](identity-trust-contract.md) names — but wiring it is a separate,
  separately-reviewed slice, and Dean's 2026-08-12 answer that the Service is a plain ClusterIP
  with no NetworkPolicy still stands. **An OAuth bearer validated by ISAAC would be the first
  identity in this system that a forged header cannot produce**, and that is the substantive
  reason to prefer it over `edge-issued-bearer`.
- **Nothing about voice.** Voice governance is a separate question with separate owners; see
  `vendor-documentation-audit-2026-08-27.md` §2 and §7.

---

## 6. What ISAAC would build, so the cost is visible

> **STATUS UPDATE, 2026-08-29 — items 1–5 below are now BUILT, and nothing about the ask has
> changed.** The application half exists at `apps/api/isaac_api/mcp/oauth.py` and
> `mcp/jwt.py`: RFC 9728 protected-resource metadata, RFC 8707 audience binding, RFC 6750
> `401`/`403` challenges, JWT signature/issuer/expiry/scope validation, and a fail-closed boot
> refusal. It is **disabled by default and reachable in no deployment** — `ISAAC_MCP_DEPLOYMENT`
> is unset everywhere, so no MCP route and no metadata route is registered, and §1 above is still
> true as written.
>
> **This changes the ask in exactly one way: it is now smaller.** Every item in §2, §3.4–§3.7 and
> §4 remains outstanding and none of it is application work — the firewall allowlist for
> `160.79.104.0/21` to *both* hosts, the Authentik issuer, `code_challenge_methods_supported`,
> client registration, the redirect URIs, and the connector administration. **D1 and D2 are still
> deferred and this does not narrow them.** What it removes is the "and then ISAAC has to write
> an OAuth implementation" line from any estimate.
>
> One requirement §3.3 flagged is now enforced rather than documented: if `ISAAC_BASE_PATH` is in
> use, the deployment **refuses to start** unless the protected-resource-metadata URL is named
> explicitly, because the RFC 9728 origin-root path is one a path-mounted ISAAC cannot serve.
> That was the "live mismatch risk" §3.3 warned about; it is now a container that does not boot
> instead of a connector that fails inside a browser.

Named so the operator can see this is not an open-ended ask. All of it is application-side,
disabled by default, and none of it requires an external answer to *write*:

1. Register the reserved `oauth-resource-server` binding: validate a bearer, bind the token's
   audience to the MCP URL, map validated claims to a `HumanActor`, enforce the two scopes.
2. Serve protected-resource metadata and the `401` + `WWW-Authenticate` handshake.
3. Fail closed: with no verifier configured, the binding resolves unconfigured and **no route is
   registered** — the behaviour that ships today, preserved.
4. Tests: forged-token, wrong-audience, expired, revoked, wrong-scope, scope-escalation, and a
   proof that no token reaches Submit.
5. No change to the truth path, no migration, no new table.

---

## 7. If the answer is "no"

If `160.79.104.0/21` cannot reach the deployment, or Authentik cannot host the flow, the honest
outcome is that **the remote connector is not available**, and ISAAC should say so on the
product screen — which is what it already says today, truthfully, with no placeholder address.

The fallback that remains available without any external change is **`local-loopback`**: a
scientist running Claude Code on a machine that also runs ISAAC locally. That is a developer and
demo path, not a beamline path, and it must not be described as the connected-companion product.

**"Not viable" is a legitimate and useful answer.** It closes D1/D2 rather than leaving them
open, and it redirects the effort to the website-first workflow, which needs no external
approval at all.
