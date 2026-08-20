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

A **Streamable HTTP transport** ships in `apps/api/isaac_api/mcp/transport.py`, so the tools
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

## 5A. A CAPABILITY GAP OPENED ON 2026-08-19, was recorded, and was CLOSED the same day

**An agent can create a Run and cannot give it any science.** That was true before too,
and was invisible; it became visible on 2026-08-19, and the reason is worth writing down.
**It is now closed — see §5A.1, which also records that the gap was WIDER than this
section said.** The original text is kept because the reasoning for leaving it open for
even one slice is part of the record, not because it still describes the toolset.

`isaac_update_draft` has two paths. With a `run_id` it calls
`PATCH /api/experiments/{id}/runs/{run_id}`, which accepts exactly the **five**
`RUN_WRITABLE_FIELD_PATHS` — `context.environment`, `context.temperature_K`,
`context.thermodynamics.atmosphere` and the two `timestamps.acquired_*`. Without one it
calls `POST /api/experiments/{id}/edit`, the record-level correction route.

The spectrum, the QC verdict, the descriptors, the asset hashes **and the absorption
edge** are **not** among those five. They are run-owned, answered through `/answers` and
`/edit` — and since 2026-08-19 the record-level route **refuses** them with
`409 belongs_to_a_run` once the record has runs, because writing them there produced a
value no exported record reads. The UI gained `POST .../runs/{run_id}/answers` and
`.../edit` in the same change. **MCP did not.**

`edge` is in that list for a reason worth stating: it lives in `implicit`, which is
merged onto a run only while that run holds every one of the record's values, so a
single override withholds it entirely. It was briefly exempted from the refusal on the
belief that the merge was unconditional; an independent review measured a `200` with
`changed_fields: ['edge']` against a run whose composed `implicit` was empty.

### 5A.1 CLOSED 2026-08-19 — and the gap was wider than 5A described

**The measurement that widened it.** 5A said an agent could not give a Run its science.
It could not answer an **open blocking question at either level**: `OPERATIONS` held no
`/answers` entry at all, and `/edit` refuses a field nothing has answered yet. On a
record created through ISAAC's own Create Experiment path that is every question the
record has — so the honest statement of the old state is not "runs are unreachable" but
**"an agent could not complete any record"**.

**A second thing was missing and 5A did not notice it: discovery.** The answer keys are
not field paths and not guessable — `series`, `qc`, `descriptor`, a per-file asset URI,
plus the `run_id` that owns each once a record has runs. `isaac_get_experiment` carries a
pending *count*, not the questions; `isaac_check_run` carries one run's. Shipping the
writes alone would have produced a tool whose description named an endpoint this server
is not allowed to call.

**Two tools, ten in the registry, four new operations:**

| Tool | Scope | Operations |
|---|---|---|
| `isaac_list_questions` | `READ` | `list_questions` |
| `isaac_answer_questions` | `DRAFT_WRITE` | `answer_record_question`, `answer_run_question`, `correct_record_field`, `correct_run_field` |

| Act | Before | Now |
|---|---|---|
| create a Run | yes | yes |
| set a Run's five context/timestamp fields | yes | yes |
| see what a record is waiting for | **no** | yes |
| answer an open record-level question | **no** | yes |
| give a Run its spectrum, verdict or descriptors | **no** | yes |
| correct a value a Run already confirmed | **no** | yes |
| correct a run-owned value on the record instead | no — `409 belongs_to_a_run` | **still no, deliberately** |
| check a Run, read its evidence | yes | yes |

**THE LEVEL IS THE CALLER'S EXPLICIT CHOICE AND THE REFUSAL IS KEPT.** The obvious
shortcut was to infer it from the key — see `series`, find the runs, pick one. That is
this server deciding which run measured a spectrum, which is a scientific fact about the
record and not a fact about the string `"series"`; and it would silently redirect a
request, so a caller holding the record's ETag would get a `412` from a route it never
asked for. So the record-level call still goes to the record and is still refused with
`409 belongs_to_a_run`, and the refusal reaches the caller intact, naming every run and
the operation that can take the answer. A test asserts exactly that, including that
nothing was written.

**What 5A got right and is preserved.** `confirmed_by_user` is **passed through from the
caller and never hard-coded** on the new handler too — asserted by its own test, because
it is a separate handler and inheriting the rule by proximity is not inheriting it.
Mutation-tested: hard-coding `True` fails that test; routing the run-level answer to the
record fails three; ignoring `correcting` fails one.

**Still absent, and named rather than implied:** nothing in this pair exports, finalises
or submits — `FORBIDDEN_TOOL_TOKENS` makes a tool named for it an `ImportError` — and
`Connect Your Agent` still shows no connection, because §6's external decisions are
untouched by this change.

---

**The original 5A state, kept for the record:**

| Act | Possible? |
|---|---|
| create a Run | yes |
| set a Run's five context/timestamp fields | yes |
| give a Run its spectrum, verdict or descriptors | **no** |
| correct them on the record instead | **no — `409 belongs_to_a_run`** |
| check a Run, read its evidence | yes |

**Why it was not closed in the same change.** Adding a run-level write to the tool surface
is a new authorized write path for scientific values, and this project's rule is that
each of those gets its own slice and its own independent review. It also inherits a
question the existing tools already answer, and must answer the same way:
`confirmed_by_user` is **passed through from the caller and never hard-coded**, because
hard-coding it "would have been one line and would have recorded a user confirmation
that no user gave" — the scientist's own Claude asserts it on the scientist's behalf, and
the server has no way to tell the difference. Extending that to a spectrum is a larger
claim than extending it to a temperature.

**The refusal was informative rather than silent**, which is what made leaving the gap
acceptable at the time: the `409` body names the run, names
`POST /api/experiments/{experiment_id}/runs/{run_id}/answers`, and says nothing was
written. An agent that reads it knows exactly what it cannot do and where the capability
would live.

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
