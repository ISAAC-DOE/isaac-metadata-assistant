# MCP operator preflight — telling the four failure modes apart

**What this document is.** A reference for whoever eventually operates ISAAC's MCP endpoint: the
four HTTP statuses a misconfigured deployment can produce, what each one actually means, and the
one trap in which **both ends look correctly configured and every call fails**.

> **NOTHING HERE ASKS ANYONE TO DO ANYTHING.**
>
> **No production call is authorized.** Mounting a reachable endpoint, creating a credential,
> registering a client, contacting an authorization server, and incurring a charge are **all
> unauthorized** — `CLAUDE.md` §15, and Dean deferred **D1** (reachability) and **D2** (the
> authentication model) on 2026-08-12 with neither narrowed since. This document does not reopen
> them and does not contain a single instruction to act. It describes **what an operator will
> observe when they eventually do mount it**, so the observation costs minutes rather than a day.
>
> **Every status in the table below is derived from this build's source, not from an observed
> hosted deployment.** No hosted observation was made or is claimed. `/krish` sits behind an
> Authentik edge that nothing in this environment can authenticate to. Where a cell's basis is a
> line of code, the line is cited so you can re-derive it rather than trust it.

**Companions, which this does not duplicate:** the local loopback binding's operator half is
[`mcp-local-transport.md`](mcp-local-transport.md); the external requirements that would have to
be met before any of this is reachable are
[`mcp-oauth-operator-requirements-2026-08-27.md`](mcp-oauth-operator-requirements-2026-08-27.md).

---

## 1. The local diagnostic

`apps/api/isaac_api/mcp/preflight.py` answers, from configuration alone, which outcome a given
configuration produces and why. It performs **no I/O of its own** — no socket, no name resolution,
no file read, no authorization server — and it is importable and useful with **nothing
configured**, which is the state you are most likely to be diagnosing from.

It does not resolve the OAuth binding for you, and that is deliberate rather than tidy:
`resolve_binding` on `oauth-resource-server` reaches `oauth.build_config`, which **probes the key
set on the filesystem** (`oauth.py:1370`). A diagnostic whose own success depended on the thing
being diagnosed would be useless exactly when you need it. So `binding_selection()` classifies the
*name*, and reports `mounts_transport: None` — *unknown without resolution* — for that one name;
pass an already-resolved binding to `transport_outcome()` when you want a definite answer.

**It never echoes a secret, and it never echoes an audience or a resource either.** For an audience
mismatch it reports the two **lengths**, the **index of first divergence**, and the **set of
standard URI normalisations** under which the two strings would be equal. The reasoning — including
why there is deliberately no option to turn echoing on — is in the module docstring. You already
have both strings; what you did not have was the comparison.

---

## 2. The status decision table

Each row was read out of the source at this commit. **`transport_outcome()` can produce the four
rows in this table**; the adjacent statuses in §4 are documented and deliberately not modelled.

| Status | Outcome | What it means | Where the decision is made |
|---|---|---|---|
| **404** | **unmounted** | `ISAAC_MCP_DEPLOYMENT` is unset, empty, unrecognised, reserved, or names a binding whose configuration does not resolve. **There is no route** — not a route that refuses. The 404 comes from the router with no ISAAC code running at all. | `app.py:68-89`, `app.py:313`, `app.py:356-366`, `transport.py:722`, `deployment.py:592` |
| **405** | **method not allowed** | The route exists, the entry guards passed, and the request was not a `POST`. Answered with `Allow: POST`. | `transport.py:388` |
| **403** | **entry guard refused** | The route exists and the binding's entry guards refused: the socket peer is not loopback, **or** a proxy header is present, **or** the browser `Origin` is outside loopback. Checked **before** the verb and before the body is read. | `transport.py:349`, `transport.py:504-548`, `deployment.py:527-534` |
| **401** | **credential required** | The route exists, the envelope is fine, and the binding wants a bearer token this request did not carry — or carried one that did not verify. **The audience mismatch in §3 lands here.** | `oauth.py:1035-1041`, `server.py:563-566`, `server.py:258`, `transport.py:595-596` |

### Reading the table in the one order that works

**Scope of everything in this section:** it describes how to *interpret* a status an authorized,
already-mounted deployment produced. It is not an instruction to mount one, to send a request, or
to call anything — none of which is authorized (see the box at the top).

```
404  ->  nothing is mounted. Look at ISAAC_MCP_DEPLOYMENT, and — for the OAuth binding —
         at whether the configuration resolves at all. A typo and a deliberate shutdown
         are indistinguishable from outside, on purpose.

405  ->  the route IS mounted. This is the single most useful signal you have, because
         nothing else distinguishes "mounted" from "absent" without sending a credential.
         A GET is the cheapest probe that answers "is it there?".

403  ->  mounted, and the binding will not serve this caller regardless of credentials.
         Three independent causes, and the refusal names which one.

401  ->  mounted, reachable, and the credential is the remaining question. Everything
         about the token — signature, issuer, expiry, AUDIENCE — lands here.
```

**The order is load-bearing and was wrong once.** With the method check first, a caller from off
loopback got `405 Allow: POST`, which answers *"does ISAAC speak MCP here?"* for a scanner that
never sent a `POST`. The peer check now runs first (`transport.py:321-328`), so a caller the
binding will not serve learns nothing from a verb.

### The 403 has three causes and says which

| `data.code` | Cause |
|---|---|
| `loopback_only` | The connection's own peer address is not loopback — including the case where ASGI reports no peer at all. Decided on the socket, **never** on a header, so a forwarded address cannot satisfy it. |
| `proxied_request_refused` | A proxy header is present (`forwarded`, `x-forwarded-for`, `x-forwarded-host`, `x-forwarded-proto`, `x-real-ip`). The value is never read; its presence alone is the refusal, because a loopback peer behind a relay is not the caller. |
| `cross_origin_refused` | The browser `Origin` is outside loopback. Any page can post to `127.0.0.1`, so the peer check alone is not a defence against DNS rebinding. An `Origin` of `null` — what a sandboxed iframe and a `file://` document send — is **refused**, not treated as absent. |

---

## 3. THE TRAP: a 100%-failing deployment that looks correct from both ends

**ISAAC's audience check is exact string equality.**

```python
audiences = _audiences(claims.get("aud"))      # jwt.py:611
if resource not in audiences:                  # jwt.py:612
    raise _reject("audience_mismatch")         # jwt.py:613
```

**RFC 8707 §2.2 permits an authorization server to MAP** the `resource` a client requested onto a
different audience value:

> The authorization server may use the exact `resource` value as the audience or it may map from
> that value to a more general URI or abstract identifier for the given resource.

**Provenance, stated because it matters more than the sentence:** that quotation and section number
are taken from
[`mcp-oauth-operator-requirements-2026-08-27.md`](mcp-oauth-operator-requirements-2026-08-27.md),
which already cites §2.2 verbatim and adds the companion sentence that the acceptable `resource`
values are *"at [the authorization server's] sole discretion based on local policy or
configuration"*. **This document did not re-read the RFC** and does not claim to. An earlier
revision of this page cited "§2" with a paraphrase — less precise than what the repository already
held.

**AND THE TRAP IS NOT A NEW FINDING.** That same document already names it —
*"an AS configured to map, rewrite or normalise the audience produces a 100%-failing deployment
that looks correct from both ends"* — and already instructs an operator to confirm the `aud` claim
contains `ISAAC_MCP_OAUTH_RESOURCE` **character for character**. It also records a second
constraint this page does not duplicate: **RFC 9728 §3.3 requires the published `resource` to be
identical to the URL the client called**, so "just set `ISAAC_MCP_OAUTH_RESOURCE` to whatever the
server mints" has to satisfy both constraints at once or discovery will not complete.

What did *not* exist is a way to **perform** that character-for-character comparison. A mismatch
checked by eye is precisely the comparison a trailing slash survives. §1's diagnostic is the
executable half of a warning the repository had already written down.

An authorization server may therefore mint `aud` as **its own canonical form** of what was asked
for, and be entirely correct:

| Configured `ISAAC_MCP_OAUTH_RESOURCE` | Audience the server issued | Difference |
|---|---|---|
| `https://isaac.example.org/api/mcp` | `https://isaac.example.org/api/mcp/` | a trailing slash |
| `https://isaac.example.org/api/mcp` | `https://ISAAC.example.org/api/mcp` | host case |
| `https://isaac.example.org/api/mcp` | `https://isaac.example.org:443/api/mcp` | an explicit default port |
| `https://isaac.example.org/api/mcp` | `https://isaac.example.org/api/%6Dcp` | a percent-encoded unreserved character |

**Every one of those is refused by ISAAC.** Not by preference — measured: each was put into a real,
correctly-signed, unexpired token and handed to the real verifier, which rejected all four with
`audience_mismatch`, while the same token shape carrying the exact string verified
(`apps/api/tests/test_mcp_preflight.py::test_the_real_verifier_really_does_refuse_every_one_of_those`).

### Why this is the hardest failure to diagnose without help

* **The authorization server thinks it is right**, and by the RFC it is.
* **ISAAC thinks it is right**, and by its own design it is — `oauth._canonical_uri`
  (`oauth.py:580`) deliberately *refuses* malformed configuration rather than *normalising* it,
  because *"a resource server that normalises is a resource server that accepts a token minted for
  a different string, and the `aud` comparison downstream is exact on purpose."*
* **The refusal message tells you almost nothing.** `audience_mismatch` reads *"The token was not
  issued for this resource. A resource server accepts only tokens whose audience is itself."* That
  is the correct message for the dangerous case — a token minted for somebody else — and it is
  indistinguishable from a trailing slash.
* **Nothing in the refusal says which strings were compared**, and that is a deliberate security
  property, not an omission: `jwt.py:106` records that no branch writes *"expected audience X, got
  Y"* because `Y` is attacker-supplied and the refusal body goes back to the caller.
* **The symptom is 100% failure, not intermittent failure**, so it looks like an outage rather than
  a configuration difference.

### The diagnostic

`preflight.audience_comparison(configured_resource, token_audiences)` reports one of four verdicts:

| Verdict | Meaning |
|---|---|
| `accepted` | One audience value is byte-identical to the configured resource. |
| `exact_string_mismatch` | **This trap.** At least one audience value is equal to the configured resource once standard URI normalisations are applied. `mapping_suspected` is `True`, and the report names *which* normalisations. The token may be perfectly valid. |
| `different_resource` | No audience value is within any known normalisation. The token was minted for something else, and **refusing it is correct** — that is the confused-deputy problem RFC 8707 exists to close. |
| `no_usable_audience_claim` | The `aud` claim is absent, or is not a string or list of strings. |

**The `exact_string_mismatch` / `different_resource` distinction is the point.** Reporting a
genuine confused-deputy attempt as a "mapping trap" would send an operator to widen their audience
configuration in response to an attack.

### The fix, and the fix that is not a fix

*(Remediation for a future authorized deployment. Nothing here is a request to configure anything
now, and §3's second constraint — RFC 9728 §3.3 — must be satisfied at the same time.)*

**Make the two strings identical.** Either the configured `ISAAC_MCP_OAUTH_RESOURCE` becomes the
exact value the authorization server puts in `aud`, or the server stops rewriting it.

**Do not "fix" it by teaching ISAAC to normalise.** A resource server that normalises accepts a
token minted for a different string, which is the whole reason the comparison is exact. The
asymmetry is the safe direction; the cost is that it needs a diagnostic.

### Two measured details that contradict the obvious guess

* **`aud: ""` is a *usable* claim naming a different resource**, not an unusable one.
  `jwt._audiences("")` returns `("",)` — a one-member tuple — so the comparison runs against a
  present-but-empty audience and refuses with `audience_mismatch`. Calling it "no usable audience
  claim" would point at claim serialization when the fault is a blank `resource` in the client's
  token request.
* **One non-string member voids the WHOLE claim.** `aud: ["https://isaac.example.org/api/mcp", 7]`
  yields **no** audiences at all, so the exact-matching member is never seen. Filtering instead
  would let `[<wrong>, 1]` read as a clean list. Confirmed against the real verifier, which also
  answers `audience_mismatch` here rather than a malformed-claim error.
* **Whitespace around the configured value is the only difference ISAAC tolerates.**
  `oauth._canonical_uri` returns the configured string `.strip()`ped and otherwise byte-for-byte
  unchanged. It does not lowercase, does not drop a trailing slash, and does not elide a default
  port; it *refuses* a fragment, a query string and userinfo outright.

---

## 4. Adjacent statuses — documented, and deliberately not modelled

An operator will meet these. They are not in the four-row table because
`preflight.transport_outcome()` does not model the JSON-RPC body ladder — `server.py` implements
that once, and a second implementation of an authorization decision can drift from the first while
still looking authoritative.

| Status | Outcome | Note |
|---|---|---|
| **400** | `token_in_query_string` | Any request carrying `access_token`, `bearer_token`, `token` or `apikey` in the query string, refused rather than served without it. **This is ISAAC's own choice, not a conformance requirement** — the `MUST NOT` is an obligation on the *client*, and OAuth 2.1 §5.1 defines no query-parameter method for a resource server to have an opinion about. The parameter's value is never read, so the refusal cannot itself log a credential. |
| **403** | `insufficient_scope` | The token verified and does not carry the ISAAC scope the tool needs. A token mapping to **no** ISAAC scope authenticates successfully and authorizes nothing — that is the honest outcome, not a bug. |
| **404** | `method_not_found` | A modern-era JSON-RPC request naming an RPC method this server does not implement. **A completely different thing from the unmounted 404**, with the same status: one comes from the router with no ISAAC code running, the other carries a JSON-RPC error body with code `-32601`. **Distinguish them by the body, never by the status.** |
| **401** | `credential_not_verifiable` | A request to the **local-loopback** binding carrying an `Authorization` header at all, whatever is in it — that binding refuses a credential rather than accepting one it cannot validate. **The operator trap:** with `ISAAC_UI_API_KEY` set, the application's own middleware demands that key in `Authorization`, the transport hands whatever is there to the binding, and the binding refuses it. The combination does not work and fails in the safe direction (`transport.py:71-81`). |

---

## 5. What the preflight will not tell you

Stated so nobody reads a clean preflight as a working deployment:

* **Whether the endpoint is reachable from anywhere.** That is D1, and it is not an application
  question.
* **Whether a specific token verifies.** The preflight accepts no token, by design. It compares an
  audience *claim* you supply; it does not check a signature, an issuer or an expiry.
* **Whether the authorization server exists, is configured, or will issue anything.** All external.
* **Anything about the hosted deployment.** Nothing here has observed it, and nothing here can.

The honest status of every hosted question in this document is `HOSTED QA PENDING (Krish)`.
