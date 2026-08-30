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
| `edge-issued-bearer` | `unconfigured` (reserved, unimplemented) | **No** | nobody |
| `oauth-resource-server`, **not fully configured** | `unconfigured` (misconfigured) | **No** | nobody — **and the container refuses to boot** |
| `local-loopback` **with a bad scope string** | `unconfigured` (misconfigured) | **No** | nobody |
| `local-loopback` | `local-loopback` | **Yes**, at `{ISAAC_BASE_PATH}/api/mcp` | a **loopback** peer, with **no** credential, **no** proxy header, and **no** off-loopback `Origin` |
| `oauth-resource-server`, **fully configured** | `oauth-resource-server` | **Yes**, plus RFC 9728 metadata paths | a caller presenting a **valid OAuth 2.1 access token** for this resource. **No deployment is in this state** |

**Row 5 is new (2026-08-29) and the previous version of this table said the two reserved names
were both unimplemented. That is now true of `edge-issued-bearer` only.** The last row describes a
configuration that exists in code and in tests and **in no deployment**: it requires an issuer, a
canonical resource URI and a verification key set, none of which is written down anywhere in this
repository. `ISAAC_MCP_DEPLOYMENT` is unset everywhere, so rows 1–5 are the only states any
deployment has ever been in.

Every fail-closed row lands on the same binding for the same reason: an operator's
typo, an unimplemented placeholder, an incomplete OAuth configuration and a scope
list naming `isaac:submit` must all produce *nothing*, never a working read-only
server somebody then trusts. The OAuth row additionally **fails to boot** rather
than merely serving nothing — an operator who named that binding believes tokens
are being verified, and a deployment that silently serves no MCP route looks
identical to a working one.

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

One path, `POST` only, JSON-RPC 2.0, and **two MCP revisions**: `2026-07-28`
(*modern* — per-request `_meta`, no handshake) and `2025-06-18` (*legacy* — the
`initialize` handshake). The revision's own terms; a server implementing both is
what it calls **dual-era**.

**How the era is chosen is the client's decision, not a setting:** an `initialize`
request selects legacy semantics, and a request carrying
`params._meta["io.modelcontextprotocol/protocolVersion"]` — or naming
`server/discover`, which exists only in the modern revision — is served
statelessly under `2026-07-28`. Nothing an operator configures moves it.

**Nothing about the legacy path changed.** A `2025-06-18` client that sends
`initialize`, then `tools/list`, then `tools/call` behaves exactly as it did
before, sends none of the modern headers, and never sees a modern error. That is
deliberate: the compatibility matrix records "Legacy client / Modern server" as
*Fails*, because a legacy client has no fall-forward mechanism.

| Condition | Answer |
|---|---|
| `GET` | `405` — this server opens no server-initiated stream |
| `DELETE` | `405` — this server issues no `Mcp-Session-Id` |
| peer is not loopback, or ASGI reports no peer | `403 loopback_only` |
| any of `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Real-IP` present | `403 proxied_request_refused` — the *presence* is the refusal; the value is never read |
| `Origin` present and not a loopback host | `403 cross_origin_refused` (DNS-rebinding defence) |
| **the caller presented no credential this binding accepts** | `401` — **for every method, including `ping`, `notifications/initialized`, `server/discover` and an unknown one.** Authentication happens before any method is dispatched |
| a declared protocol version this server does not serve (header **or** `_meta`) | `400` with JSON-RPC `-32022` `UnsupportedProtocolVersionError`, listing `supported` |
| a **modern** request missing or contradicting `MCP-Protocol-Version` / `Mcp-Method` / `Mcp-Name` | `400` with JSON-RPC `-32020` `HeaderMismatch` |
| an unknown method, **modern** era | `404` with `-32601` |
| an unknown method, **legacy** era | `200` with `-32601` |
| `Content-Type` is not `application/json` | `415` |
| `Accept` cannot take JSON | `406` |
| body over 1 MiB | `413` |
| a JSON-RPC **batch** (array) | `400` — removed in revision `2025-06-18` |
| an **authenticated** notification (no `id`) | `202`, no body |
| deployment refused the caller | `401`, and **no fabricated `WWW-Authenticate`** |
| scope not granted | `403` |
| any other JSON-RPC error | `200` with a JSON-RPC error object — the transport succeeded, the application refused |

**Methods, per era.** Legacy: `initialize`, `notifications/initialized`, `ping`,
`tools/list`, `tools/call`. Modern: `server/discover`, `ping`, `tools/list`,
`tools/call`. An unknown-method refusal names its own era's list, so a legacy
client is never told about `server/discover` and a modern one is never told about
`initialize`.

**A worked modern request**, since three headers are required and the third is
conditional:

```http
POST /api/mcp HTTP/1.1
Content-Type: application/json
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: isaac_list_experiments

{"jsonrpc":"2.0","id":1,"method":"tools/call",
 "params":{"name":"isaac_list_experiments","arguments":{},
           "_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28"}}}
```

`Mcp-Name` is required for `tools/call` only, and may carry the revision's Base64
sentinel (`=?base64?…?=`), which this server decodes before comparing it to
`params.name`.

**One thing an operator should not be surprised by:** `2025-06-18` was the only
revision this server spoke until 2026-08-30, and the old refusal body for an
unrecognised version was `{"code": "unsupported_protocol_version", ...}` under
this transport's own error code. That body was not a recognized MCP error, so a
dual-era client fell back to `initialize` and worked — **by accident**. It is now
the real `-32022` envelope, which tells a modern client to retry with a supported
version instead of falling back.

**And ISAAC's own three error codes moved, in the same change.** They were
`-32001` (deployment refused), `-32002` (insufficient scope) and `-32003`
(transport refused); they are now **`-31001`, `-31002` and `-31003`**. The reason
is `2026-07-28`'s partition of the block JSON-RPC set aside for implementations:
`-32000`..`-32019` is a legacy sub-range new implementations *"**SHOULD NOT** use
… at all"*, `-32020`..`-32099` is reserved for the specification's own codes, and
`-32002` in particular is one implementations of this revision **MUST NOT** emit
(it meant *resource not found* in earlier revisions, and clients are told to keep
accepting it as such). A scope refusal arriving as `-32002` could therefore be
read by a conforming client as a missing resource. The specification's own
direction is to allocate *"outside the JSON-RPC reserved range (`-32768` to
`-32000`)"*, which is where they now are. Nothing else about those three
refusals — their HTTP status, their body shape, their `data.code` string —
changed.

No `Mcp-Session-Id` is ever issued. No RFC 9728 protected-resource-metadata document
is published: a challenge naming an authorization server ISAAC does not run would
invite a flow that cannot complete.

---

## 4. Scopes

Two, and they **do not nest**.

| Scope | Grants |
|---|---|
| `isaac:read` | the **seven** read tools — ~~six~~ |
| `isaac:draft.write` | *in addition to* `isaac:read`, the **three** draft-write tools (`isaac_create_run`, `isaac_update_draft`, `isaac_answer_questions`) — ~~two~~ |

> **COUNTS CORRECTED 2026-08-25**, and struck rather than edited because this table was
> otherwise the ONE place that got the scope semantics right. Re-derived:
>
> ```
> PYTHONPATH=apps/api:src python -c "import isaac_api.mcp.tools as t; \
>   o=t._tools(); r=[x for x in o if x.scope.name=='READ']; \
>   print(len(o), len(r), len(o)-len(r))"
> -> 10 7 3
> ```
>
> `isaac_answer_questions` is the write the old "two" omitted — the one that CLOSES a
> blocking question, and therefore the one a reader most needs counted. The same omission
> is recorded in `mcp/tools.py`'s module docstring, which is why that file now states the
> PROPERTY and lets `policy.PERMITTED_TOOL_NAMES` be the enumeration.
>
> **The semantics in this table were never wrong, and that is the finding worth keeping.**
> *"in addition to `isaac:read`"* and (below) *"a grant with no usable tool at all"* are
> exactly right — while `Settings -> Connect Your Agent` told a scientist the opposite until
> it was corrected in this same change. **The truthful copy existed in the docs and never
> reached the UI.**

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

* **ISAAC as an OAuth 2.1 resource server** (`oauth-resource-server`). ~~"reserved and
  unimplemented"~~ — **IMPLEMENTED 2026-08-29** (`apps/api/isaac_api/mcp/oauth.py`,
  `mcp/jwt.py`), disabled by default, reachable in no deployment. **The list below did not
  shrink and is not satisfied by the implementation** — every item is a value only Dean can
  supply, and the code refuses to boot without them, which is the point of listing them here:

  the authorization-server issuer URL (`ISAAC_MCP_OAUTH_ISSUER`); the **exact** canonical
  resource URI this server answers as, which must match what a scientist types into their
  client including the path (`ISAAC_MCP_OAUTH_RESOURCE`, compared to a token's `aud` by exact
  string equality, RFC 8707); the signing keys, **projected into the pod as a file**
  (`ISAAC_MCP_OAUTH_JWKS_FILE` — a JWKS *URL* is refused, because this build makes no outbound
  request); the URL at which the RFC 9728 metadata document is published, which **must** be
  given explicitly when `ISAAC_BASE_PATH` is in use because a path-mounted ISAAC cannot serve
  the RFC's origin-root path (`ISAAC_MCP_OAUTH_METADATA_URL`); the exact scope strings the
  issuer will mint — ISAAC's are `isaac:read` and `isaac:draft.write`, they **do not nest**,
  and there is no third; and confirmation that the edge passes OAuth traffic through rather
  than intercepting it.

  Two items the earlier list did not name and that are not application work: the token
  endpoint must accept `application/x-www-form-urlencoded`, and **Anthropic's egress range
  must reach both this endpoint and the issuer host** — see
  [`mcp-oauth-operator-requirements-2026-08-27.md`](mcp-oauth-operator-requirements-2026-08-27.md)
  §2, which is the item most likely to fail silently.

  The claim that carries scope is **not** a parameter: `scope` (RFC 6749, space-delimited) and
  `scp` (array or string) are both read, and a scope string ISAAC does not recognise is dropped
  rather than refused, so a token carrying `openid profile` alongside `isaac:read` works.
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
`apps/api/tests/test_mcp_protocol_eras.py` — **added 2026-08-30**: that no method
answers a caller who presented no credential (swept over every method in either
era, plus two the server does not implement), and the dual-era contract — era
selection, `server/discover`, the `-32022` and `-32020` error shapes, the modern
header rules, and the assertion that the legacy handshake never produces a modern
error, which is what a dual-era client's fallback depends on.

**None of them reads real data, touches a database, or sends anything off this
machine.** *This line previously said "None of them opens a socket", which was
false.* Exactly one test does — `test_a_real_client_over_a_real_loopback_socket_
completes_a_session` binds a `uvicorn` server to `127.0.0.1` on an ephemeral port
and drives it with a real HTTP client. That is the only way to prove the loopback
guard reads a **kernel-supplied** peer address rather than one the test wrote, so
it stays. It is also the only test here that can fail in a CI sandbox that
forbids binding a socket; every other test drives the ASGI application in process.
