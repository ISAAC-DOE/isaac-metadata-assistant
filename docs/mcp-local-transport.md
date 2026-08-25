# Running ISAAC's MCP server locally

ISAAC ships an MCP tool server — ten least-privilege tools over ISAAC's own HTTP
API — and, since this slice, a **Streamable HTTP transport** that a real MCP client
can speak to. It is off by default, and "off" means *there is no route*, not a route
that refuses.

This document is the operator's half. The design and the refusals are documented in
the code: `apps/api/isaac_api/mcp/transport.py`, `deployment.py`, `policy.py`.

> **Nothing here creates an internet-reachable endpoint, a credential, an outbound
> call, or a connection to hosted ISAAC.** Dean deferred D1 (reachability) and D2
> (authentication) on 2026-08-12 and neither is approved. This is the local,
> loopback-only development binding, and it is the only binding this build has.
> See `docs/mcp-capability-audit.md` §3 and §6.

---

## 1. What is reachable in each configuration state

| `ISAAC_MCP_DEPLOYMENT` | Binding | Route registered? | Reachable by |
|---|---|---|---|
| *unset* (**the default**) | `unconfigured` | **No** | nobody — the path 404s |
| `""` / whitespace | `unconfigured` | **No** | nobody |
| anything unrecognised (`true`, `hosted`, `LOCAL_LOOPBACK`, …) | `unconfigured` | **No** | nobody |
| `oauth-resource-server` / `edge-issued-bearer` | `unconfigured` (reserved, unimplemented) | **No** | nobody |
| `local-loopback` **with a bad scope string** | `unconfigured` (misconfigured) | **No** | nobody |
| `local-loopback` | `local-loopback` | **Yes**, at `{ISAAC_BASE_PATH}/api/mcp` | a **loopback** peer, with **no** credential, **no** proxy header, and **no** off-loopback `Origin` |

Every fail-closed row lands on the same binding for the same reason: an operator's
typo, an unimplemented placeholder and a scope list naming `isaac:submit` must all
produce *nothing*, never a working read-only server somebody then trusts.

---

## 2. Turning it on

```bash
export ISAAC_UI_WORKSPACE="$PWD/.local-workspace"
export ISAAC_MCP_DEPLOYMENT=local-loopback
# Optional. Unset grants isaac:read ALONE. The scopes do not nest, so a
# read-write agent needs both named explicitly.
export ISAAC_MCP_LOCAL_SCOPES="isaac:read,isaac:draft.write"
# Optional. Pins the connection to one worked-example session; unset uses the
# ordinary workspace. It comes from the BINDING, so no tool argument can move
# the connection between scopes.
# export ISAAC_MCP_LOCAL_TUTORIAL_SESSION="<session id>"

.venv/bin/uvicorn isaac_api.app:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

Then, from the same machine:

```bash
claude mcp add --transport http isaac http://127.0.0.1:8000/api/mcp
```

**`--host 127.0.0.1` is the operator's half of the loopback guarantee and it is not
optional.** The application refuses every request whose *socket peer* is not a
loopback address, which is the half an application can enforce. It cannot choose
what address a process it does not own bound to, and it cannot see through a reverse
proxy that strips its own forwarded headers. Bind loopback.

### Two combinations that do not work, on purpose

* **`ISAAC_UI_API_KEY` + `ISAAC_MCP_DEPLOYMENT=local-loopback`.** The app's key
  middleware demands `Authorization` on every path including this one; the transport
  hands whatever is in `Authorization` to the binding; the loopback binding refuses a
  credential it cannot verify. Both the wrong key and the right key are refused, by
  different layers. Leave `ISAAC_UI_API_KEY` unset for local MCP work. Do not "fix"
  this by teaching the transport to recognise the app's own key — that would turn a
  shared secret issued for the UI into an MCP credential nobody decided to issue.
* **Setting `ISAAC_MCP_DEPLOYMENT=local-loopback` in a hosted deployment.** It would
  register the route, and every request arriving through the Authentik edge would be
  refused as proxied or non-loopback. It buys nothing and advertises a path. Don't.

---

## 3. What the endpoint accepts

One path, `POST` only, JSON-RPC 2.0, MCP revision **`2025-06-18`**.

| Condition | Answer |
|---|---|
| `GET` | `405` — this server opens no server-initiated stream |
| `DELETE` | `405` — this server issues no `Mcp-Session-Id` |
| peer is not loopback, or ASGI reports no peer | `403 loopback_only` |
| any of `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Real-IP` present | `403 proxied_request_refused` — the *presence* is the refusal; the value is never read |
| `Origin` present and not a loopback host | `403 cross_origin_refused` (DNS-rebinding defence) |
| `MCP-Protocol-Version` present and not `2025-06-18` | `400` |
| `Content-Type` is not `application/json` | `415` |
| `Accept` cannot take JSON | `406` |
| body over 1 MiB | `413` |
| a JSON-RPC **batch** (array) | `400` — removed in revision `2025-06-18` |
| a notification (no `id`) | `202`, no body |
| deployment refused the caller | `401`, and **no fabricated `WWW-Authenticate`** |
| scope not granted | `403` |
| any other JSON-RPC error | `200` with a JSON-RPC error object — the transport succeeded, the application refused |

No `Mcp-Session-Id` is ever issued. No RFC 9728 protected-resource-metadata document
is published: a challenge naming an authorization server ISAAC does not run would
invite a flow that cannot complete.

---

## 4. Scopes

Two, and they **do not nest**.

| Scope | Grants |
|---|---|
| `isaac:read` | the six read tools |
| `isaac:draft.write` | *in addition to* `isaac:read`, the two draft-write tools |

`isaac_create_run` and `isaac_update_draft` require **both**, because both return the
record state they produced. So `ISAAC_MCP_LOCAL_SCOPES=isaac:draft.write` alone is a
grant with **no usable tool at all** — `tools/list` returns an empty array. That is
deliberate and is the opposite of implication: the write tools require *more*, never
does one grant silently become two.

Everything else remains unreachable by construction, not by omission: `Scope` has no
`SUBMIT` member, `OPERATIONS` is a closed `(method, path)` table, `ALLOWED_METHODS`
omits `DELETE` and `PUT`, and a tool name or operation path carrying a forbidden
capability token fails at **import**. Submit, export, deletion, migration and
governance are not tools that are switched off; they are tools that cannot be
registered.

---

## 5. What Dean / SLAC still own, exactly

Nothing in this slice narrows D1 or D2. What a hosted binding needs is a
configuration contract, and it is short — the seam
(`deployment.DeploymentBinding`) already accepts both shapes without redesign.

**D1 — reachability.** One decision: *may the MCP path be reachable from a
scientist's own machine over the public internet?* A Claude client connects from the
client side; an endpoint reachable only inside SLAC's network cannot be added as a
connector at all. If yes, the contract ISAAC needs is: the public URL of the MCP path,
and confirmation that the edge forwards `POST` to it with the request body and the
`Authorization` header intact.

**D2 — authentication.** One of two shapes, and ISAAC needs the parameters of
whichever is chosen:

* **ISAAC-hosted OAuth 2.1 resource server** (`oauth-resource-server`, reserved and
  unimplemented). ISAAC would need: the authorization-server issuer URL; the token
  endpoint; the expected `aud`/resource indicator value for this server (RFC 8707);
  the signing keys or JWKS URL; the claim that carries scope, and the exact scope
  strings the issuer will mint — ISAAC's are `isaac:read` and `isaac:draft.write`;
  and confirmation that the edge passes OAuth traffic through rather than
  intercepting it.
* **Edge-issued static bearer** (`edge-issued-bearer`, reserved and unimplemented).
  ISAAC would need: how the token is issued and rotated; how ISAAC verifies it
  (a shared secret it can compare, or a signature it can check — **not** "the edge
  checked it", because the Service is a plain ClusterIP with no NetworkPolicy and an
  in-cluster caller never meets the edge); which scopes a token carries and where;
  and per-scientist issuance, since one shared token makes every caller the same
  principal.

**What ISAAC must NOT be given, and will not accept:** a forwarded identity header
as proof of anything. `X-authentik-username` and the other four are authoritative on
the edge path and forgeable off it (`docs/identity-trust-contract.md` §2, Q4
answered against us, 2026-08-12), and `X-authentik-entitlements` / `X-Isaac-Edge` are
permanently disqualified. No binding in this build reads a header, and a future one
must not either.

Until one of those contracts exists, the honest state is the one this build has:
`ISAAC_MCP_DEPLOYMENT` unset and no route.

~~**and no product surface that mentions MCP at all.** This build ships no
`Connect Your Agent` screen — verify with
`rg -i 'Connect Your Agent' apps/web/src apps/api src`, which matches nothing —
and that absence is itself the honest state~~

**SUPERSEDED 2026-08-24 — AND THE PARAGRAPH'S OWN CITED COMMAND DISPROVED IT.** The
screen ships. Re-running the command exactly as written:

```
rg -i 'Connect Your Agent' apps/web/src apps/api src
→ 34 matches across 9 files, including
  apps/web/src/screens/settings/ConnectYourAgent.tsx
  apps/web/src/screens/SettingsPage.tsx
  apps/web/src/lib/mcpConnectContent.ts
  apps/web/src/lib/settingsContent.ts
  apps/web/src/lib/routes.ts
  (plus four test files)
```

It is struck in place rather than deleted because a claim that carried its own
falsifier is worth remembering: the sentence was self-checking and nobody re-ran it.

**What is still true, and is the half worth keeping:** there is still no hosted MCP
endpoint. `POST /api/mcp` returns **404** in the default environment and the loopback
binding is off by default, so no scientist's agent can connect to the deployment. The
`Connect Your Agent` screen says organization configuration is required rather than
showing a connection it cannot verify — which is what
`docs/ai-integration-decision-packet.md` §6.1 and §9 require ("build nothing that
implies any of it exists"): §9 forbids implying a CONNECTION exists, not describing a
capability that does.

> **The forward reference this replaces, kept for the record.** This note used to
> read: *"A separate branch (`feat/connect-agent`, PR #142) adds a `Connect Your
> Agent` screen … It is not on this branch and may land after it … when that branch
> merges, this note is what should be replaced with a present-tense statement."* That
> branch merged; this is the present-tense statement it asked for.

---

## 6. Tests

`apps/api/tests/test_mcp_transport.py` — the transport: the mount gate, the loopback
and origin guards, the fail-closed HTTP axes, the authorization seam, the CAS/validation
parity cases, and four negative controls that disable one guard each and assert the
behaviour changes.

`apps/api/tests/test_mcp_boundaries.py` — what must never be reachable.
`apps/api/tests/test_mcp_server.py` — every registered tool, in process.

**None of them reads real data, touches a database, or sends anything off this
machine.** *This line previously said "None of them opens a socket", which was
false.* Exactly one test does — `test_a_real_client_over_a_real_loopback_socket_
completes_a_session` binds a `uvicorn` server to `127.0.0.1` on an ephemeral port
and drives it with a real HTTP client. That is the only way to prove the loopback
guard reads a **kernel-supplied** peer address rather than one the test wrote, so
it stays. It is also the only test here that can fail in a CI sandbox that
forbids binding a socket; every other test drives the ASGI application in process.
