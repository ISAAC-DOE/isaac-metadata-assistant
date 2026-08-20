# MCP capability audit — what `Connect Your Agent` can and cannot mean

**Purpose.** Settle, against current official documentation rather than memory, what "let a
scientist connect their Claude environment to ISAAC" actually delivers — so the Settings surface
states something true, and so the Dean/Angel decision packet describes a real boundary.

**Audited 2026-08-08** against `modelcontextprotocol.io`, `platform.claude.com`,
`code.claude.com`, `claude.com/docs` and `support.claude.com`. Confidence is recorded per finding.
Where the audit could not establish something authoritatively, it says so instead of inferring.

---

## 1. The finding that decides the product question

> **MCP is one-way. A Claude client calls ISAAC's tools. ISAAC cannot call a Claude model.**

Confidence: **very high** — this is architectural, not a gap. Servers respond to client requests;
servers do not initiate requests to models. The Messages API MCP connector supports **tool calls
only**.

Consequences, stated plainly because §31 of the capture brief warns against exactly this conflation:

- A scientist connecting Claude to ISAAC gets: Claude reading their drafts, listing runs, checking
  validation findings, and calling ISAAC tools on their behalf — **billed to that scientist's own
  Claude subscription or API key**.
- ISAAC gets **nothing new** from that connection. Field completion, transcript extraction,
  evidence summarisation, or any inference *inside* ISAAC still requires ISAAC to hold its own
  credential and call the API directly.

So MCP does **not** reduce the native-assistant question to a UI problem. It is a genuinely
separate capability with a separate credential and a separate billing relationship. Anything that
implies otherwise on a product screen is false.

---

## 2. Transport and authentication

| Item | Finding | Confidence |
|---|---|---|
| Transport | **Streamable HTTP**. The SSE-only transport from the 2024-11-05 spec is **deprecated** | high |
| Auth baseline | OAuth 2.1 with bearer tokens in `Authorization`, never in a query string | high |
| AS discovery | RFC 8414 authorization-server metadata **or** OpenID Connect Discovery; clients must support both | high |
| Resource binding | RFC 8707 resource indicators — the client names the MCP server as the target resource | high |
| Issuer validation | RFC 9207 — the client validates `iss` against recorded metadata (confused-deputy defence) | high |
| Registration | RFC 7591 dynamic registration, or client-ID metadata documents | medium |
| Pragmatic alternative | Claude Code and Claude.ai custom connectors also accept **fixed header auth** (a static bearer token) for services that do not implement full OAuth | high |

---

## 3. The blocker for ISAAC, and it is not a coding problem

ISAAC sits behind an **Authentik forward-auth edge**. Two independent requirements follow, and
both are outside this repository:

1. **The MCP endpoint must be reachable from a scientist's own machine over the public internet.**
   Claude Code, Claude.ai and the Messages API all connect *from the client side*. An endpoint
   reachable only inside SLAC's network cannot be added as a connector at all.
2. **A Claude client cannot traverse a third-party SSO edge.** It issues an HTTPS POST and expects
   a response; it cannot complete an interactive Authentik login. There is no documented pattern
   for transparent third-party-SSO traversal. The supported options are:
   - ISAAC implements **its own OAuth authorization server**, advertises it via `WWW-Authenticate`
     and `/.well-known/oauth-protected-resource`, and the edge passes OAuth traffic through; or
   - the edge is configured to accept a **pre-issued static token** on the MCP path specifically.

**Both are Dean/infrastructure decisions, not application work.** Until one is made,
`Connect Your Agent` cannot show a working connection. Per capture-brief §33 it must therefore show
`Requires organization configuration` and name exactly what is required — which is what this
document supplies.

### One correction to a tempting shortcut

Claude **Enterprise-Managed Authorization** (admin authorises a connector once, users inherit it
through IdP groups) is **beta, Okta-first, and scoped to a named list of connector providers**. A
custom first-party server like ISAAC is not on that list. Do **not** plan around EMA removing the
per-user authentication step. Confidence: medium-high — the provider list is explicit, but beta
scope changes, so re-check before relying on it.

---

## 4. Tool-design constraints that shape a least-privilege toolset

- **No specified cap on tool count or schema size.** The real constraint is context budget; large
  toolsets should defer loading rather than ship dozens of always-present schemas.
- **Annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) are HINTS,
  not enforcement.** The spec says so directly. A client *may* prompt for confirmation; nothing
  guarantees it.

**The rule that follows, and it is the important one:** ISAAC's server must enforce every
restriction itself, server-side. Marking a tool `destructiveHint: true` is documentation, not a
gate. In particular, capture-brief §34 and §64.19 require that **no MCP tool can perform final
authoritative `Submit Record`** — that is enforced by not implementing the tool, never by an
annotation.

---

## 5. What this means for the build

**Buildable now, with no external dependency:** the MCP server itself — tool definitions over the
existing app APIs, scope model, per-scientist authorisation, optimistic-concurrency handling on
draft writes (reusing the existing `If-Match`/ETag machinery), audit events, and a deterministic
test suite against synthetic fixtures.

**Not demonstrable until an infrastructure decision:** an actual scientist-to-hosted-ISAAC
connection. The Settings surface must say so rather than showing a connection state it cannot
verify.

**Never build:** a `submit_record` tool, a tool that deletes an experiment, a tool that applies a
migration, or anything that changes governance.

### Status update — the transport is now built, and D1/D2 are untouched by that

A **Streamable HTTP transport** ships in `apps/api/isaac_api/mcp/transport.py`, so the eight tools
are genuinely runnable by a real MCP client — **when, and only when,
`ISAAC_MCP_DEPLOYMENT=local-loopback` is set**. Operator guide, the full
configuration-state table, and the exact contract Dean would have to supply for either D2 shape:
[`docs/mcp-local-transport.md`](mcp-local-transport.md).

Read the boundary precisely, because "the transport exists" is easy to over-read:

* **The default deployment registers no MCP route at all** — an absent path, not a path that
  answers 403. A route that refuses still advertises the capability.
* The one binding that serves a transport refuses every request whose **socket peer** is not a
  loopback address, refuses one carrying a proxy header, refuses an off-loopback browser `Origin`,
  and refuses a credential it cannot verify. No header is ever read as evidence of identity.
* **Nothing about D1 or D2 is answered, narrowed, or implied.** No internet-reachable path, no
  credential, no outbound call, no billing, and no hosted connection exists or is authorized. The
  two reserved binding names remain unimplemented, and selecting one still resolves to the
  unconfigured binding.
* No product screen mentions MCP (verified: `apps/web/src` contains no reference), so nothing
  implies a connection exists — `ai-integration-decision-packet.md` §6.1 and §9 are intact.

---

## 5A. A CAPABILITY GAP OPENED ON 2026-08-19, and it is recorded rather than closed

**An agent can create a Run and cannot give it any science.** That was true before too,
and was invisible; it is now visible, and the reason is worth writing down.

`isaac_update_draft` has two paths. With a `run_id` it calls
`PATCH /api/experiments/{id}/runs/{run_id}`, which accepts exactly the **five**
`RUN_WRITABLE_FIELD_PATHS` — `context.environment`, `context.temperature_K`,
`context.thermodynamics.atmosphere` and the two `timestamps.acquired_*`. Without one it
calls `POST /api/experiments/{id}/edit`, the record-level correction route.

The spectrum, the QC verdict, the descriptors and the asset hashes are **not** among
those five. They are run-level BLOCKS, answered through `/answers` and `/edit` — and
since 2026-08-19 the record-level route **refuses** them with `409 belongs_to_a_run`
once the record has runs, because writing them there produced a value no exported record
reads. The UI gained `POST .../runs/{run_id}/answers` and `.../edit` in the same change.
**MCP did not.**

So today, through MCP:

| Act | Possible? |
|---|---|
| create a Run | yes |
| set a Run's five context/timestamp fields | yes |
| give a Run its spectrum, verdict or descriptors | **no** |
| correct them on the record instead | **no — `409 belongs_to_a_run`** |
| check a Run, read its evidence | yes |

**Why it is not closed in the same change.** Adding a run-level write to the tool surface
is a new authorized write path for scientific values, and this project's rule is that
each of those gets its own slice and its own independent review. It also inherits a
question the existing tools already answer, and must answer the same way:
`confirmed_by_user` is **passed through from the caller and never hard-coded**, because
hard-coding it "would have been one line and would have recorded a user confirmation
that no user gave" — the scientist's own Claude asserts it on the scientist's behalf, and
the server has no way to tell the difference. Extending that to a spectrum is a larger
claim than extending it to a temperature.

**The refusal is informative rather than silent**, which is what makes leaving the gap
acceptable for now: the `409` body names the run, names
`POST /api/experiments/{experiment_id}/runs/{run_id}/answers`, and says nothing was
written. An agent that reads it knows exactly what it cannot do and where the capability
would live.

**This is remaining work, not a decision.** It is named here so `Connect Your Agent`'s
copy cannot drift into implying a completeness the toolset does not have.

## 6. Exact external actions

| Action | Owner | Blocks | Status |
|---|---|---|---|
| Decide whether the MCP path may be internet-reachable | Dean / SLAC infrastructure | any connector at all | **DEFERRED 2026-08-12** (= D1) |
| Choose the auth model — ISAAC-hosted OAuth AS vs. edge-accepted static token on the MCP path | Dean / SLAC infrastructure | `Connect Your Agent` showing a real connection | **DEFERRED 2026-08-12** (= D2) |
| Institutional Anthropic API credential + billing | Dean / Angel | the **native** embedded assistant — a wholly separate question from everything above | **DEFERRED 2026-08-12** (= D3/D4/D5) |

> **DEAN DEFERRED ALL THREE, 2026-08-12** — *"leave AI integration as future work rather than
> increasing scope at this point."* He is away for roughly a week. **None of them is approved,
> narrowed, or conditionally approved**, and every "blocks" entry above is still in force.
>
> **Separately, and by a different decision-maker:** the project owner has elected to **continue
> implementing** the MCP server, Connect Your Agent, the native assistant and the provider
> architecture against **deterministic fake providers**. That authorizes code, APIs, UI, the auth and
> provider abstractions, tests, error handling and security boundaries — and authorizes **no**
> internet-reachable path, **no** credential, **no** billing, and **no** real connection. §6.1 of
> `ai-integration-decision-packet.md` still forbids any screen implying a `Connected` state. See that
> document's head-of-file block for both facts stated in full.

---

## 7. Plain-language statement for the decision packet

Connecting Claude to ISAAC lets a scientist's own Claude — in the desktop app, the browser, or the
command line — read and edit their ISAAC drafts through a controlled set of tools, paid for by that
scientist's existing Claude subscription. It does not give ISAAC the ability to think. ISAAC's own
features — drafting a field from a transcript, summarising evidence, answering questions inside the
purple assistant — need ISAAC itself to hold an Anthropic API key and to be billed for what it uses.
These are two different decisions, and approving the first does not deliver the second.
