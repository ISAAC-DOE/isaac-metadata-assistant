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

---

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
