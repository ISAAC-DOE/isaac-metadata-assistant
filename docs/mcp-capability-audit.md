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
* ~~"The one binding that serves a transport"~~ — **CORRECTED 2026-08-29: there are now two, and
  neither is reachable.** `local-loopback` is unchanged in every respect: it refuses every request
  whose **socket peer** is not a loopback address, refuses one carrying a proxy header, refuses an
  off-loopback browser `Origin`, and refuses a credential it cannot verify. `oauth-resource-server`
  (`apps/api/isaac_api/mcp/oauth.py`) is ~~a complete OAuth 2.1 protected resource~~ **an OAuth 2.1
  protected resource for the MCP *authorization* chapter** — RFC 9728 metadata, RFC 8707 audience
  binding, RFC 6750 challenges, JWT validation per OAuth 2.1 §5.2 — and it **resolves to
  the unconfigured binding unless an operator supplies an issuer, a canonical resource URI and a
  verification key set.** None of those exists in this repository, in any manifest, or in any
  deployment. In both bindings, **no header is ever read as evidence of identity.**

  > **"Complete" is struck 2026-08-30, in the same change that struck it in `oauth.py`, because a
  > correction that lands in the code and not in the document an outsider reads is not a
  > correction.** Two things the word covered up:
  >
  > 1. **It named no chapter.** What is implemented is the Authorization chapter in the
  >    resource-server role. Four divergences are now enumerated in `oauth.py`'s module docstring
  >    rather than implied away — including one from the *Transports* chapter: unlike
  >    `local-loopback`, this binding performs **no `Origin` validation at all**, deliberately,
  >    because a token is not ambient authority and no allowlist exists to enforce.
  > 2. **Three JSON-RPC methods answered before authentication.** On the day the bullet above was
  >    written, `ping`, `notifications/initialized` and the unknown-method path returned `200` to a
  >    caller carrying no token — harmless under `local-loopback`, whose socket-peer guard refuses a
  >    stranger first, and live under this binding, which has no such guard by design. Fixed
  >    2026-08-30: every method authenticates before it produces anything. The bullet's own claim
  >    that this binding is disabled and unreachable was true throughout and is unchanged; what was
  >    not true is that the code behind the switch was complete.
  >
  > The server also now speaks **two protocol revisions** — `2026-07-28` (modern, per-request
  > `_meta`, `server/discover`) and `2025-06-18` (legacy, `initialize` handshake). §2's reading of
  > the transport is unaffected: the era is chosen by how a client opens, not by configuration, and
  > no route exists in any deployment either way.
* **Nothing about D1 or D2 is answered, narrowed, or implied.** No internet-reachable path, no
  credential, no outbound call, no billing, and no hosted connection exists or is authorized.
  ~~"The two reserved binding names remain unimplemented, and selecting one still resolves to the
  unconfigured binding."~~ — **CORRECTED 2026-08-29, and the correction is narrow.** One of the two
  (`oauth-resource-server`) is now IMPLEMENTED; `edge-issued-bearer` is still reserved and
  unimplemented. Selecting either **still resolves to the unconfigured binding** in every state
  this repository can reach, for different reasons: the reserved one because it is not registered,
  the implemented one because it has no configuration. **Implementing the application half is not
  answering D2.** D2 asks which authentication model SLAC will operate, and answering it requires
  an issuer, a registered client, a redirect-URI policy and a firewall decision — every one of them
  Dean's, none of them written down anywhere here. What changed is that the question can now be
  costed against reviewable code instead of a plan. See
  [`docs/mcp-oauth-operator-requirements-2026-08-27.md`](mcp-oauth-operator-requirements-2026-08-27.md) §6.
* ~~"No product screen mentions MCP (verified: `apps/web/src` contains no reference)"~~ —
  **CORRECTED 2026-08-25, AND IT WAS FALSE ON THE DAY IT WAS COMMITTED.** Re-running the check the
  sentence itself offers:

  ```
  git grep -ic mcp 6baadc8 -- apps/web/src
  → 151 matching lines across 9 files, including
    apps/web/src/screens/settings/ConnectYourAgent.tsx        (43)
    apps/web/src/lib/mcpConnectContent.ts                     (18)
    apps/web/src/screens/SettingsPage.tsx                      (8)
    apps/web/src/__tests__/connect-your-agent.test.tsx        (70)
    apps/web/src/lib/routes.ts, settingsContent.ts,
    transcriptCaptureContent.ts, ConnectAnAgent.tsx,
    __tests__/upload-claim-parity.test.tsx
  ```

  `mcpConnectContent.ts` was added in `a1b8ee0` on **2026-08-13**; this bullet was added in
  `b4b5e9f` on **2026-08-16** (`git log --diff-filter=A -- apps/web/src/lib/mcpConnectContent.ts`
  and `git log -S "No product screen mentions" -- docs/mcp-capability-audit.md` — deliberately
  searching a PREFIX of the retired sentence rather than the whole of it, because the guard named
  below refuses an unstruck copy of the full claim even inside a citation, and a guard that has to be
  worked around by the document it protects is a guard nobody trusts). So the screen had shipped
  three days before the audit said no screen mentioned MCP.

  **THE CONCLUSION IS UNCHANGED AND IS NOT WHAT WENT WRONG.** `Connect Your Agent` states that
  organization configuration is required and shows no connection it cannot verify, so nothing
  implies a connection exists and `ai-integration-decision-packet.md` §6.1 and §9 remain intact —
  §9 forbids implying a CONNECTION exists, not describing a capability that does. What went wrong is
  the **evidence**: a parenthetical citing a command nobody re-ran, in a document read as an audit.

  **THIS IS THE SAME SENTENCE `docs/mcp-local-transport.md` ALREADY STRUCK ON 2026-08-24**, with the
  note that *"a claim that carried its own falsifier is worth remembering: the sentence was
  self-checking and nobody re-ran it"* — and that sweep **missed this copy**, which is the same
  enumeration failure `CLAUDE.md` §15 records for the `isaac_run_projection` correction: the fix
  landed in the document somebody was already editing, and the duplicate went unlooked-for. The two
  are now pinned together by `apps/web/src/__tests__/connect-your-agent.test.tsx`, so neither can be
  corrected alone again.

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

The spectrum, the QC verdict, the descriptors and the asset hashes are **not** among
those five. They are run-owned, answered through `/answers` and `/edit` — and since
2026-08-19 the record-level route **refuses** them with `409 belongs_to_a_run` once the
record has runs, because writing them there produced a value no exported record reads.
The UI gained `POST .../runs/{run_id}/answers` and `.../edit` in the same change.

**THE ABSORPTION EDGE IS NOT AMONG THE REFUSED KEYS, AND THIS PARAGRAPH SAID IT WAS.**
An independent review found the claim still standing here after the code had gone the
other way, so the correction is recorded rather than swapped in silently. `edge` lives in
the record's `implicit` derivations, and `resolved_run_draft` merges those onto a run only
while that run has recorded no override at all (`inherit=not
_diverges_from_experiment(...)`) — so answering `edge` on the record DOES reach every
non-diverging run, and refusing it would have made it answerable by no route while
putting two false sentences in the refusal body. It was refused for one commit on the
belief that the merge was unconditional, and the exemption was restored.

**Both errors are recorded because they cut in opposite directions**, and a reader needs
to know which one is current: a review measured a `200` with `changed_fields: ['edge']`
against a run whose composed `implicit` was empty — that is real, is a write no exported
record reads, and is **the accepted cost of the exemption**, not an argument that has been
answered. It is disclosed on the `409` body and, since this review, in the `200`
`response_description` too, because a caller who receives a 200 never sees a 409.

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
| answer the absorption `edge` on the record | yes — it is NOT refused | yes; it reaches every non-diverging run, and reaches nothing on a diverged one |
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

### 5A.2 THREE CLAIMS IN THE FIRST VERSION OF 5A.1 WERE FALSE. An independent review measured each.

Recorded rather than swapped in, because two of them were **in the tool descriptions a
model reads as its interface contract**, and one had been *pinned by a test* — the same
failure mode as the `write-draft` copy this slice was fixing.

**1. "`/edit` refuses a field nothing has answered yet" — it did not; it wrote it.**
Measured over MCP: `correcting: true` on an OPEN `series` returned **200**, stored the
value with a fresh `user_confirmation`, and left the question **open** —
`apply_corrections` deliberately never touches `pending`. So the honest statement of the
prior state is not "`/edit` refuses" but *"`/edit` wrote the value and left the question
open, so the record still could not export"*: a success report about a write that
resolved nothing, while the description guaranteed a refusal.

**It is now true rather than reworded.** `routes._refuse_correcting_an_unanswered_key`
returns `422 not_yet_answered`, naming every offending key and the operation that takes
it, at both levels. A typed refusal rather than a dropped key, because dropping it would
produce `unrecognized_field` — "this application does not know that field" — when the
field is recognised and only its state is wrong. **Two conditions are required, and the
second was found by a test going red:** a key is refused only when it is both listed as
open AND absent from the draft, because a legacy run's materialised question list names
`qc` even when the run already holds a verdict.

**2. "The previous confirmation is kept beside the new one" — true for `qc`, assets and
`edge`; FALSE for `series` and `descriptor`.** `complete.py` **assigns**
`block_evidence[f"series:{id}"] = [one entry]` and rebuilds `descriptors_outputs`
wholesale, so after correcting a spectrum the record retains no evidence that a different
one was ever confirmed. The claim was strongest exactly where it was least true.
Compounding it, the test named `..._and_keeps_the_earlier_confirmation` asserted **nothing
about a confirmation** — the name was the only carrier of the claim. Both surfaces now
state the difference in both directions, the test is renamed to what it proves, and the
real behaviour is measured in
`test_what_a_CORRECTION_does_to_THE_EARLIER_CONFIRMATION_is_per_field`.

**3. "Field paths only" on the `write-draft` screen row — inverted.**
`isaac_update_draft`'s **record-level** branch posts to `/edit`, which takes
blocking-question keys: it writes exactly the spectrum and QC verdict the row said it
could not, and **refuses** the official field path the row said was all it took. Only its
**run**-level branch is field paths. `isaac_update_draft`'s own description carried the
same false sentence and was **pre-existing** — not introduced by this slice, and the
reason the new copy read plausibly. Both are corrected and both directions are now pinned
by `test_update_draft_record_level_takes_ANSWER_KEYS_and_refuses_a_field_path`.

Also corrected from the review, smaller but the same kind: the success result's own `etag`
is the **record's** validator, so feeding it back into a second run-level call is a `412`
(the description now says to use `data.run_version`); `blocker_key` is the bare `id` on a
record with no runs; and `edge` is exempt from the `409`, which both new surfaces stated
without qualification.

**One thing the review flagged that is a DECISION rather than a defect, and is left open:**
`isaac_list_questions` hands an agent the canonical seeds' `demo_answer`, and
`isaac_answer_questions` will store it with `confirmed_by_user: true` — recording a
`user_confirmation` for a value no user confirmed. `_example_scope` restricts it to
`ws.CANONICAL_IDS`, the payload carries its own `label` and `provenance`, and the
description says sending it back is asserting the scientist confirmed it. The records are
synthetic. The guard is prose in a description, and that is stated rather than dressed up.

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

*(That middle row was also false for `edge` when it was written — see the correction
above. It is kept as written, because this table is the historical record of what §5A
said, and editing it would destroy the thing it is being kept for.)*

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
