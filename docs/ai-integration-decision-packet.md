# AI & voice integration — decision packet

> # RESPONSE RECEIVED 2026-08-12 — TWO SEPARATE FACTS, AND BOTH ARE TRUE
>
> **This block exists because the two facts below are easy to collapse into one, and collapsing them
> in either direction misrepresents somebody.** Read them as two.
>
> ### FACT 1 — Dean DEFERRED D1–D9. This is his recommendation and it is recorded unsoftened.
>
> Dean's exact recommendation was to
>
> > *"leave AI integration as future work rather than increasing scope at this point"*
>
> **He did not approve D1–D9. He did not partially approve them. He did not ask for more
> information.** He recommended deferral of the whole external decision list — MCP reachability and
> auth (D1, D2), model provider, credential, billing (D3–D5), egress, retention, data policy
> (D6–D8), and transcription provider (D9). He is away for roughly a week.
>
> **Nothing in this document may be rewritten to read as though he approved any of it.** Every "until
> answered, ISAAC displays…" line in §5 is still the operative behaviour, and every **BLOCKED** row in
> §7 is still blocked.
>
> ### FACT 2 — The project owner (Krish) has elected to CONTINUE IMPLEMENTING the original scope.
>
> **Krish's decision, attributed to Krish and not to Dean:** implementation of MCP, "Connect Your
> Agent", the native LLM assistant, transcription/voice, and the provider architecture **continues**.
> The roadmap is **not cancelled and must not be recorded as cancelled.**
>
> These two facts are compatible because the thing Dean deferred and the thing Krish is continuing
> **are not the same thing** — which is the distinction §1 of this document already exists to protect,
> now applied to the programme itself:
>
> | | Meaning | Status |
> |---|---|---|
> | **Implementation complete** | code, APIs, UI, the auth abstraction, the provider abstraction, tests, **deterministic fake providers**, error handling, security boundaries | **Krish's call. PROCEEDING.** |
> | **Production provider configured** | the institutional endpoint, the credential, the network path, billing, provider approval | **Genuinely external, genuinely unavailable, and Dean has deferred it.** |
>
> > **The absence of the second is not a reason to skip the first.** A capability whose provider seam
> > is exercised only by a deterministic fake is a real, testable, reviewable capability; what it is
> > not is *connected*. Building it does not create a connection, incur a charge, send data anywhere,
> > or pre-empt any decision in §5.
>
> ### The invariants this decision does NOT relax — read them as binding on the continued work
>
> **§6 holds in full, and is the reason Fact 2 is safe.** In particular: **§6.1 no fake `Connected`
> state** — a screen may never imply a provider exists; **§6.2 external agents cannot submit**;
> **§6.3 no model output may enter the truth path**; **§6.4 the no-guessing rule applies to the
> assistant's own answers.** And §9's closing line — ***"build nothing that implies any of it
> exists"*** — is **not** overridden by Fact 2. Building the capability and advertising the
> capability are different acts; the first is authorized here, the second is not.
>
> **`CLAUDE.md` §15 still lists an external model provider / LLM as out of scope.** Fact 2 is an
> owner decision about *implementation*, recorded here and in `CLAUDE.md` §15; it does not by itself
> authorize a production provider, an outbound call to one, or a credential.
>
> **Standing:** Dean's recommendation is **operator testimony relayed by the project owner** — no
> transcript is committed here. Krish's decision is a **direct instruction from the project owner**,
> which is the top of the source-of-truth hierarchy and needs no external corroboration.
>
> **D1–D9 are NOT renumbered, NOT deleted, and NOT marked closed.** They are **deferred, unanswered,
> and still the labels an eventual answer will be given against.** See the DO-NOT-RENUMBER box in §5,
> which this response makes more relevant, not less: a deferred identifier is still an identifier that
> has left the repository.

**Audience.** Krish, to carry to Dean and Angel. Every item below is an external decision this
repository cannot make for itself. Nothing here asks for code approval; the code questions are
settled and recorded elsewhere.

**Status of this document.** It is a decision packet, not a plan and not a capability claim.

~~**No AI, model, MCP or voice capability is implemented in this repository.** That is measured,
not assumed — see §7 and §8.~~

> **SUPERSEDED 2026-08-24 — READ §7's SUPERSESSION BLOCK, WHICH THIS SENTENCE CONTRADICTED.**
> It was the FIRST status claim a reader met, and it stood while the same document said, further
> down, *"capability A is IMPLEMENTED (10 tools, 13 operations, a Connect Your Agent surface)"*.
> Struck in place, not deleted, because the scope note below is what makes it readable as a
> corrected claim rather than a drifting one.
>
> **What is implemented:** the MCP server (10 tools behind 13 policy operations, with
> `Settings → Connect Your Agent` as its surface), the native-assistant seam
> (`POST /api/assistant/ask`) and the transcription seam (`POST /api/transcription`).
>
> **What is NOT, and is the half the sentence was reaching for:** no hosted MCP endpoint
> (`POST /api/mcp` → **404** in the default environment, loopback binding off by default), and
> **no production model provider, credential, network path or charge anywhere** — both seams
> answer **`501 no_provider_configured`** in every deployment. D1–D9 remain deferred by Dean and
> **no D-row may be recorded as approved.** *Implementation complete* and *production provider
> configured* are different milestones; this document exists to keep them apart, which is why
> collapsing them into one status line was the wrong sentence even when it was true.

**Commit this was written and verified against:** `669b60c`. Every `file:line` citation below was
opened at that commit. **That pin partially scopes the struck sentence above and is the reason it
is struck rather than called a falsehood: it was accurate AT `669b60c`, and the citations under it
are still citations to that commit.** It stopped being accurate as the implementation landed, and a
status line that ages out of truth without saying so reads to the next reader exactly like one that
was never true. Where a file is likely to grow, the citation names a heading or quotes a
phrase instead of trusting a line number, because this repository has already broken its own
citations that way (an instance is recorded in §8, M7).

**How every claim is labelled.** Read the label; it is the point.

| Label | Means |
|---|---|
| **measured** | established by a command run in this session, at `669b60c`. The command is quoted. |
| **code-reviewed** | established by reading source, not by executing it. |
| **from-doc** | read from a committed document in this repository, and cited. Not independently re-derived here. |
| **operator-testimony** | reported by a human from an authenticated session; no artifact exists in this repository. |
| **inferred** | a conclusion drawn from the above. Reasoning is shown. |
| **unknown** | this repository cannot establish it. The person who can is named. |

---

## 1. The distinction this document exists to protect

Three different things get called "add AI to ISAAC". They have **different owners, different
risks, different costs, and different answers.** Approving any one of them delivers none of the
others. If this packet achieves only one thing, it should be that these three never again appear in
one sentence.

| | Capability | Direction of the call | Who pays | Who must decide | Does it give ISAAC inference? |
|---|---|---|---|---|---|
| **A** | **MCP server** — a scientist's own Claude calls ISAAC's tools | **inbound** to ISAAC | the scientist's own Claude subscription or API key | SLAC infrastructure (reachability + auth) | **No.** Never. |
| **B** | **Native assistant** — the ISAAC server calls a model | **outbound** from ISAAC | SLAC / the project | Dean + Angel (credential, billing, egress, data policy) | Yes — this is the only one that does. |
| **C** | **Voice / transcription** — speech becomes text, text becomes draft fields | **outbound** from the browser or the server to a transcription provider | SLAC / the project | Dean + Angel (provider, egress, retention) | Partially — it needs an external provider, but not necessarily a general model. |

### 1.1 The single most likely misunderstanding: MCP is one-way

> **Connecting Claude to ISAAC does not give ISAAC the ability to call a model.**

**from-doc, confidence recorded as "very high" by the audit that established it:**
`docs/mcp-capability-audit.md` §1 ("The finding that decides the product question") states
*"MCP is one-way. A Claude client calls ISAAC's tools. ISAAC cannot call a Claude model."* and
records that this is *"architectural, not a gap"* — servers respond to client requests; servers do
not initiate requests to models (`docs/mcp-capability-audit.md:15-19`).

The consequences, stated plainly because they are what gets conflated:

- **What a scientist gains from MCP (capability A):** their own Claude can read their ISAAC drafts,
  list runs, check validation findings, and call ISAAC tools on their behalf — **billed to that
  scientist's own Claude subscription or API key** (`docs/mcp-capability-audit.md:23-26`).
- **What ISAAC gains from MCP: nothing new.** Field completion, transcript extraction, evidence
  summarisation, or any inference *inside* ISAAC still requires ISAAC to hold its own credential
  and call a provider directly (`docs/mcp-capability-audit.md:27-30`).

So MCP does **not** reduce the native-assistant question to a UI problem. Capability B is a
separate capability with a separate credential and a separate billing relationship. **Anything on a
product screen implying otherwise would be false.**

The audit's own plain-language sentence for this packet is worth carrying verbatim
(`docs/mcp-capability-audit.md` §7):

> "Connecting Claude to ISAAC lets a scientist's own Claude … read and edit their ISAAC drafts
> through a controlled set of tools, paid for by that scientist's existing Claude subscription. It
> does not give ISAAC the ability to think. … These are two different decisions, and approving the
> first does not deliver the second."

### 1.2 A second conflation, smaller but live

**Voice (C) is not the native assistant (B).** Transcription turns speech into text; it does not
require a general-purpose model, and a provider approved for one is not thereby approved for the
other. The spec keeps them as three separate seams — `TranscriptionProvider`,
`CaptureExtractionProvider` and `AssistantProvider`
(`docs/superpowers/specs/2026-08-08-scientist-capture-data-contract.md:437-439`, DECISION D6) —
precisely so that one can be approved without silently authorising the others. **Approving a
transcription provider does not approve a model provider, and the reverse is also true.**

---

## 2. Capability A — MCP server (a scientist's Claude calls ISAAC)

### What exists today

~~**Nothing. Measured.** There is no MCP server, no JSON-RPC handling, and no MCP dependency anywhere
in the application or the truth core.~~ **SUPERSEDED 2026-08-24 — an MCP implementation SHIPS.** Re-running
this section's own command, `rg --text -i -e 'mcp' -e 'jsonrpc' -e 'model context protocol' apps/api
apps/web/src src scripts pyproject.toml apps/web/package.json | wc -l` → **487** (it recorded exit 1 /
zero matches). The registry holds **10** tools — `PYTHONPATH=apps/api:src .venv/bin/python -c "from
isaac_api.mcp.tools import TOOLS; print(len(TOOLS))"` → `10`, of which **7 read and 3 write** — behind
**13** policy operations, with `Settings → Connect Your Agent` as its surface. What remains true, and is
the part worth keeping: **no hosted MCP endpoint exists** — `POST /api/mcp` returns **404** in the
default environment and the loopback binding is off by default — so **no scientist's agent can connect
to the deployment.** Struck rather than rewritten, because it was true when taken. Established by:

```
rg --text -n -i -e 'mcp' -e 'jsonrpc' -e 'model context protocol' \
   apps/api apps/web/src src scripts pyproject.toml apps/web/package.json
→ exit 1 (zero matches)
```

The only MCP artifact in the repository is the audit document itself
(`find . -iname '*mcp*'` → `./docs/mcp-capability-audit.md`, one result). **So capability A is
specified and audited, but wholly unimplemented.**

> **SUPERSEDED 2026-08-24: capability A is IMPLEMENTED** (10 tools, 13 operations, a Connect Your Agent surface) **and UNREACHABLE** (no hosted endpoint; `POST /api/mcp` → 404 by default). Those are different claims and only the second still holds.

### What is buildable without any external answer

**from-doc** (`docs/mcp-capability-audit.md` §5, and corroborated by the capture spec's
"Not blocked by any of these" list, `…-capture-data-contract.md:514-517`, which names "the MCP
server implementation"): the server itself — tool definitions over the existing app APIs, the scope
model, per-scientist authorisation, optimistic-concurrency handling on draft writes reusing the
existing `If-Match`/ETag machinery, audit events, and a deterministic test suite against synthetic
fixtures.

### What is *not* demonstrable without an external answer

An actual scientist-to-hosted-ISAAC connection. Two independent requirements, **both outside this
repository** (`docs/mcp-capability-audit.md` §3):

1. **Public reachability.** Claude Code, Claude.ai and the Messages API all connect *from the client
   side*. An endpoint reachable only inside SLAC's network **cannot be added as a connector at
   all.** (`docs/mcp-capability-audit.md:55-57`.)
2. **A Claude client cannot traverse a third-party SSO edge.** ISAAC sits behind an Authentik
   forward-auth edge. A Claude client issues an HTTPS POST and expects a response; it cannot
   complete an interactive Authentik login, and the audit found **no documented pattern for
   transparent third-party-SSO traversal.** The two supported shapes are: ISAAC implements its own
   OAuth authorization server (advertised via `WWW-Authenticate` and
   `/.well-known/oauth-protected-resource`) with the edge passing OAuth traffic through; **or** the
   edge is configured to accept a pre-issued static token on the MCP path specifically.
   (`docs/mcp-capability-audit.md:58-63`.)

**One shortcut that does not work.** Claude *Enterprise-Managed Authorization* — admin authorises a
connector once, users inherit it through IdP groups — is **beta, Okta-first, and scoped to a named
list of connector providers**, and a custom first-party server like ISAAC is not on that list
(`docs/mcp-capability-audit.md` §3, "One correction to a tempting shortcut"; the audit records its
own confidence as medium-high and says to re-check before relying on it, because beta scope
changes). **Do not plan around EMA removing the per-user authentication step.**

### Why the auth question is harder than it looks: ISAAC has no identity

This is the part most likely to be waved through, so it is stated with its evidence.

**ISAAC consumes no identity header.** The Authentik edge supplies identity headers; the
application reads none of them. **operator-testimony for the observation, plus an independently
re-checkable grep for the consumption claim** — `docs/identity-trust-contract.md` §6A records a
probe that ran once against hosted commit `d521dd7` (image `v0.0.42`), and the section opens with an
explicit block stating **"This is OPERATOR TESTIMONY, not a captured artifact"**: the probe wrote no
file, held no state, and the response body was not committed
(`docs/identity-trust-contract.md:538-540`). The probe has since been **removed**; the route returns
404 and a test pins that.

What §6A's table records (`docs/identity-trust-contract.md:558-566`) — all seven candidate headers
**present**, and `Consumed by ISAAC` **"no"** for every one of the seven. The `consumed_by_isaac`
column is flagged in the source as *"a code constant from the frozen candidate tuple echoed back,
**not a measurement**"*, with the note that the claim is independently re-checkable by grep and that
this is *better* evidence than a single request (`:554-556`).

Two findings from §6A that **must not be flattened**, because a decision made on a flattened version
would be wrong:

- **`X-authentik-entitlements` and `X-Isaac-Edge` are permanently disqualified.** Both came back
  present, `scalar`, and **carrying the client's own planted canary** — meaning the one value that
  arrived was the client's own, and *"the edge contributed nothing to these two headers on this
  path — it did not inject, did not overwrite, and did not strip"*
  (`docs/identity-trust-contract.md:608-616`). They are therefore disqualified from
  **authentication, authorization, role assignment, proof that Authentik was traversed, and proof
  that the caller is an institutional user** (`:628-631`). `X-Isaac-Edge` is disqualified from *the
  one job its name implies* — it cannot witness that a request came through the edge, because any
  client can set it. This is **permanent unless infrastructure changes and is independently
  re-verified** (`:625-626`).
- **For the other five** (`username`, `uid`, `email`, `name`, `groups`) the edge **supplied the
  value and did not append** — one value arrived, it was not the canary, and `duplicate` was
  specifically looked for and did not occur (`docs/identity-trust-contract.md:576-582`). **It does
  NOT follow that the client's copy was removed.** §6A.1 names two non-replacement scenarios
  producing the identical signature: an intermediary joining the client's copy using a separator
  outside `{",", "|"}`, or the client's copy passing through **transformed** — truncated,
  re-encoded, case-folded, or quoted — *"In the second case the client did influence the header,
  which is precisely the outcome this paragraph claims to exclude"* (`:584-591`).
  **An earlier revision of a summary said the edge "replaced" the client's value; that was withdrawn
  as too strong. Do not restore it.** The probe's own limitation: `false` means *"not found in
  either compared form"*, **never "provably stripped"**.

**Why this matters for MCP.** An MCP caller is not a browser. It cannot complete an interactive
login, and there is no identity signal ISAAC currently trusts — so **"authenticate the MCP caller
the way we authenticate a scientist" is not an available option**, because ISAAC does not
authenticate a scientist today. Whatever auth model is chosen must be built, and it must be
built server-side (see §2.1).

**Also still open and not answered by any of the above:** Q4 — *can any workload in the cluster
reach the `metadata-assistant` Service directly, bypassing the ingress and therefore Authentik?*
(`docs/identity-trust-contract.md:688`). **unknown; Dean owns it.** Nothing observed proves the
probe's caller was authenticated (`:602-604`).

### 2.1 Enforcement is server-side, and MCP annotations are not a gate

**from-doc, and the audit states it as the important rule** (`docs/mcp-capability-audit.md` §4):
the MCP annotations `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` are
**HINTS, not enforcement** — the specification says so directly. A client *may* prompt for
confirmation; nothing guarantees it.

> **ISAAC's server must enforce every restriction itself, server-side. Marking a tool
> `destructiveHint: true` is documentation, not a gate.**

The corollary, which is an invariant and not a preference: a forbidden capability is enforced **by
not implementing the tool**, never by an annotation.

---

## 3. Capability B — native assistant (the ISAAC server calls a model)

### What exists today: a deterministic assistant with no model, measured

Phase 34 shipped **free-form deterministic Q&A with no LLM** over a bounded intent catalog
(`CLAUDE.md` §11: *"'Free-form' means flexible natural-language phrasing over a bounded,
deterministic intent catalog — **no LLM was added**"*). Verified here rather than taken on trust:

- **The catalog is finite and has exactly eight intents. measured / code-reviewed.**
  `apps/api/isaac_api/assistant_query.py:67-74` defines `PENDING_FIELDS`, `EXPORT_BLOCKERS`,
  `EXPORT_READINESS`, `WORKFLOW_STEP`, `FIELD_PROVENANCE`, `EVIDENCE_SUMMARY`, `RECORD_SUMMARY`,
  `MEMORY_LEAD`. Two non-intents follow at `:76-77`: `UNSUPPORTED = "unsupported"` and
  `AMBIGUOUS = "ambiguous"`.
- **Classification is string containment, not scoring.** The module header states classification is
  *"an explicit finite catalog of alias/phrase triggers matched by plain string-containment (NO
  probabilistic scoring, NO ML, NO fuzzy classifier)"* and that an unmatched/open-world question
  resolves to `unsupported` — *"never guessed"* (`assistant_query.py:29-34`). The trigger table
  itself is a literal `dict[str, tuple[str, ...]]` (`:80` onward), commented *"Kept explicit and
  finite — never a learned/scored classifier."*
- **It refuses rather than guesses.** `assistant_query.py:804-810` — the `UNSUPPORTED` branch is
  commented *"honest refusal, names what IS supported"*.
- **It is pure and takes no network action.** *"never imports `isaac_records`, never imports
  `graphify`, never imports `fastapi`, computes no verdict, and takes no filesystem/network
  action"* (`assistant_query.py:14-16`), asserted by `apps/api/tests/test_assistant_paths.py`.
- **The frontend agent is equally explicit.** `apps/web/src/lib/assistantAgent.ts:7-9` — *"It is
  DETERMINISTIC: there is NO external LLM, no freeform natural-language model, no generation — only
  a fixed registry of small pure functions"*.

### UPDATED 2026-08-19 — the seam is now REACHABLE OVER HTTP, and no screen advertises it

`POST /api/assistant/ask` exists. It is the assistant seam's HTTP consumer, and it was
missing: `providers/assistant.py` was a fully built, fully tested seam with **no route at
all**, so *"does this deployment have a native assistant?"* was answerable only by reading
Python. That is the same gap `POST /api/transcription` closed for its own seam, and the new
route is deliberately its twin — same two-status split, same refusal vocabulary, same
decision reference.

**It answers `501` in every deployment, and that is structural rather than a promise.**
`validate_provider_config_or_raise` refuses to boot an application whose
`ISAAC_ASSISTANT_PROVIDER` names the deterministic fake (DECISION **D6**), so no operator can
turn one on and no screen can be shown a connected state. The 200 path is exercised only by
a test that constructs the double directly, which is what the provider configuration
module's own docstring prescribes.

**What the route enforces, over the wire:**

- an answer carries `grounded_in` — the context keys it used — and an uncited answer cannot
  be constructed at all (`AssistantAnswer` raises);
- `authoritative` is a constant `false`, and the route is absent from the validation stack;
- the operation **fetches nothing**. It cannot read a record, a workspace or a database, so
  *"what was sent to the provider"* is exactly the `context` array the caller wrote. An
  unknown top-level key — `record_id` is the obvious one — is **refused**, not ignored,
  because answering `200` while dropping it would leave a caller believing the answer was
  grounded in a record nobody read;
- an unknown key **inside** a context item is refused too. `verified: true` is the case worth
  naming: it is the vocabulary of an evidence envelope, and a caller sending it would be
  asserting a classification this seam has no power to make;
- a question the supplied context does not cover is `422 outside_grounded_context`, never a
  paragraph from general knowledge.

**NO PRODUCT SCREEN CONSUMES IT, and that is a decision rather than an unfinished edge.**
§9's rule is *"build nothing that implies any of it exists"*, and a panel reporting an
assistant seam — even one reporting it as unconfigured — would put a model-backed assistant
in front of a scientist as a thing that is nearly here. The Assistant panel goes on saying
*"There is no language model"*, which is true of the shipped deterministic Q&A and stays
true. `GET /api/providers/capabilities` reports the seam's status for a client that asks;
`TranscriptCapturePanel` is the precedent for consuming that honestly if a surface is ever
authorized.

**Capability B still needs everything §3's "What capability B needs" lists, and none of it is
code.** Building the capability and advertising it are different acts; the first is
authorized by the project owner, the second is not.

### There is no model provider, no ASR client, and no outbound HTTP. Measured.

Three independent commands, each reported with the exit code of `rg` itself (**not** of a pipeline,
because a pipeline's `$?` is the last command's status):

```
# 1. model / ASR SDK tokens, whole tree
rg --text -n -i 'anthropic|openai|whisper|deepgram|assemblyai|google-cloud-speech|
   azure.*cognitiveservices|langchain|litellm|transformers|huggingface|ollama|bedrock|vertexai' \
   -g '!node_modules' -g '!.git' -g '!graphify-out' .
→ every hit is prose in a document, EXCEPT one false positive worth recording:
  apps/web/src/styles/tokens.css:111  /* … depth is a whisper */
  (re-checked in isolation: `rg --text -n -i 'whisper' apps src scripts` → that one CSS
   comment only. A naive grep for an ASR vendor name hits English prose.)

# 2. outbound HTTP in the runtime backend and the truth core
rg --text -n -e 'httpx' -e 'requests\.post' -e 'requests\.get' -e 'aiohttp' -e 'urllib\.request' \
   apps/api/isaac_api src/isaac_records
→ exit 1 (zero matches)

# 3. audio capture APIs, whole tree
rg --text -n -i 'MediaRecorder|SpeechRecognition|webkitSpeech|getUserMedia|AudioContext|
   navigator\.mediaDevices' -g '!node_modules' -g '!.git' .
→ 2 hits, BOTH prose in docs/superpowers/specs/2026-08-08-scientist-capture-data-contract.md
  (:407 and :420). ~~Zero in any source file.~~ **RE-MEASURED 2026-08-24: NOT zero.** The same command now
  reports **45** hits across **6** files (re-measured at `905c706`; ~~42~~ corrected 2026-08-24 by an independent truthfulness review, which found no commit on this branch yields 42 — the parent gives 41 and this branch gives 45) — `MediaRecorder` and `getUserMedia` both ship in
  `apps/web/src/components/TranscriptCapturePanel.tsx`. No audio leaves the browser and no ASR client
  exists; see the D6 supersession in the capture spec.
```

**One precision that a bare "no HTTP client" would get wrong.** `httpx>=0.27` **is** a declared
dependency — `pyproject.toml:23`, in the `api` optional extra. So the *library* is installable;
what does not exist is a **call site**. Its only occurrence in `apps/api` or `src` is a comment in
a test (`apps/api/tests/test_deploy_config.py:117`). The honest statement is therefore *"no
outbound HTTP call site exists in runtime code"*, not *"ISAAC could not make an HTTP request"*.
`docs/dean-integration-review-brief.md:28` records the same conclusion from an equivalent grep.

### The app currently tells users, in writing, that there is no model

This is a **dependency of capability B that is easy to miss**, and it is a truthfulness dependency,
not a cosmetic one. **measured** — `apps/web/src/lib/settingsContent.ts` carries two user-facing
claims:

- `:580` — *"No language model at all — the assistant answers from a bounded in-repository
  catalog."*
- `:587` — *"There is no language model in this build. The assistant answers from a bounded,
  deterministic catalog over the deployment's own data, and refuses anything outside it rather than
  guessing. **Nothing you type, and nothing shown on any screen here, is sent to a model
  provider.**"*

A third, at `:546`, tells the user that on export *"there is no upload, no third-party service, and
no model involved."*

> **Consequence: the day a native assistant is enabled, these strings become false.** Enabling
> capability B is not only a credential and a billing change; it is a **disclosure change**, and the
> disclosure must change in the same release as the capability, not after it.

This repository has a recorded history of exactly this failure mode, and two instances are cited
because they are re-checkable (**from-doc**):

- `CLAUDE.md:483-487` — a Phase 36R review caught *"a Settings claim that real artifacts are
  'refused before anything is read or extracted' when **no real-vs-synthetic detection exists
  anywhere in the codebase**"*, noting the app enforces synthetic *mode*, not synthetic *data*. The
  same passage records that these were *"honesty defects that every test passed through"*.
- `CLAUDE.md:506-510` — *"**Three claims that were FALSE and are now scoped, not deleted.**
  Governance & Safety and Load Materials asserted *'no file is read, parsed, or inspected'* while
  `RecordValidator` (one tab away) and `CsvReconcilePanel` read and POST a chosen file."* The fix
  was a parity test, `__tests__/upload-claim-parity.test.tsx`, which pins all three sites **and
  pins polarity, "because its first version passed an inverted disclosure."**

> **The transferable lesson: a disclosure string is not documentation, it is a claim under test.**
> Any release enabling capability B or C must move the strings and the pinning tests together.

### What capability B needs, and none of it is code

A provider, an institutional credential, billing, approved egress, and a data policy. Those are
§5's decisions D3–D8. `docs/mcp-capability-audit.md:118` names the owner: **Dean / Angel**, blocking
*"the **native** embedded assistant — a wholly separate question from everything above"*.

### And it is currently out of scope by explicit project rule

**Quoted, not paraphrased** (`CLAUDE.md:695-698`, the §15 "Out of scope unless explicitly approved"
list):

> "- Phase 37 and its dependencies (NOT authorized): portal module integration, **durable
> persistence / a PostgreSQL-backed record repository / any database write**, portal or personal API
> keys, **external model provider / LLM**, identity/role enforcement, retiring the blue portal,
> deleting/archiving the personal repo or the Vercel/Railway projects, and any `isaac-k8` change."

The same list separately bars *"advisory AI review implementation beyond isolated placeholder"*
(`CLAUDE.md:694`).

**Note the narrowings, so this is not over-read.** That paragraph has been narrowed twice — on
2026-07-31 for read-only aggregate Postgres recon, and on 2026-08-07 for durable Create Experiment
persistence (`CLAUDE.md:699-701` and the 2026-08-07 lift that follows it). **Neither narrowing
touches "external model provider / LLM", which remains prohibited in full.** A future reader should
not infer from "the database prohibition was lifted" that the model prohibition softened; it did
not.

---

## 4. Capability C — voice / transcription

### Three blockers, all recorded as measured by the spec that found them

`docs/superpowers/specs/2026-08-08-scientist-capture-data-contract.md` §6 is titled *"Voice — the
part of the brief with no legal path today"* and opens *"Three independent blockers, all measured"*
(`:411-413`). Each is re-verified here at `669b60c`:

**Blocker 1 — no byte store, so raw audio cannot be retained server-side** (`:415-417`).
Re-verified:

- `POST /api/uploads` is an **unconditional 403 that takes no parameters. measured.** The handler is
  `def uploads():` — **zero parameters** — and its body is three lines that build a fixed payload
  and return `JSONResponse(status_code=403, …)`. It is preceded by the section marker
  `# --- 15. uploads (always blocked) ---`. Its own inline comment reads *"Governance seam: no
  multipart is declared or parsed; no file is read or stored."* At this commit that is
  `apps/api/isaac_api/routes.py:5262` (handler) under the marker at `:5229`. **Prefer the section
  marker to the line number** — see §8, M7, for why.
- **`python-multipart` is not a dependency. measured.** `pyproject.toml:23` is exactly
  `api = ["fastapi>=0.110", "uvicorn>=0.29", "httpx>=0.27", "psycopg2-binary>=2.9"]`. Without it
  FastAPI **cannot parse a form** at all, so the refusal is structural and not merely a policy
  check.

The spec adds that there is no `write_bytes`/`wb` call anywhere in `apps/api/` or `src/`
(`:404`) — **from-doc; not re-derived in this session.** The gate it names is a byte store (PVC or
S3) in Dean-owned `isaac-k8`, **plus** lifting `CLAUDE.md:775` — re-checked, and that line still
lands on the row *"**3+** — PostgreSQL record repository, record loading, upload writes | **NOT
authorized.**"* — **plus** content validation that does not exist.

> So the honest position on "keep audio with the experiment": **there is nowhere to keep it.**
> Offering the choice would be a fake integration.

**Blocker 2 — no approved transcription provider** (`:418-423`). Re-verified: no ASR client and no
model provider of any kind (§3's measurements 1–3). **This is decision D9 in §5.**

**Blocker 3 — adding an audio source type is a truth-core change** (`:424-427`). Re-verified, and
this is the one place where **the code contradicts the spec; the code wins**:

- **The enumeration is closed at seven, none audio-related. measured.**
  `src/isaac_records/models.py:29-37` — `SOURCE_TYPES = ("document", "spreadsheet", "screenshot",
  "web_form", "file_listing", "user_confirmation", "derivation")`.
- **The TypeScript union mirrors it, also seven.** `apps/web/src/lib/types.ts:17-24`.
- **There are THREE total `Record<SourceType, …>` maps, not two, and one is not where the spec says
  it is.** `rg --text -n 'Record<SourceType' apps/web/src` → exactly three:
  - `apps/web/src/components/EvidenceRow.tsx:5-13` — `SRC_CLASS: Record<SourceType, string>`
  - `apps/web/src/components/icons.tsx:76-84` — `SOURCE_ICON: Record<SourceType, LucideIcon>`
  - `apps/web/src/lib/experimentGraph.ts:417` — `SOURCE_TYPE_PHRASE: Readonly<Record<SourceType, string>>`

  **The spec places both `SRC_CLASS` and `SOURCE_ICON` at `EvidenceRow.tsx:5-13` (`:425-427`).**
  `SOURCE_ICON` is defined in `icons.tsx` and only *imported* by `EvidenceRow.tsx:2`; and the spec
  does not mention `SOURCE_TYPE_PHRASE` at all. **The practical effect makes the change larger, not
  smaller:** an eighth member breaks compilation at **three** call sites plus both enumerations.
  Correct the spec, not this document.

> So "let the scientist dictate a note and cite it as evidence" is **not a UI feature**. It reaches
> the truth core (`src/isaac_records/models.py`), which `CLAUDE.md` §13 protects, and it would
> require the report §13 mandates.

### DECISION D6 (CAPTURE) — the honest v1 that is already agreed

> **NAMING WARNING, added 2026-08-24.** This document uses **"D6" for two unrelated decisions**: this
> one, the capture/recorder decision restated from the capture spec, and **§5's `### D6 — Approved
> egress`**, which is a Dean-owned data-governance question. They are not versions of each other.
> Cite this one as **D6 (capture)** and that one as **D6 (egress)**.

~~`…-capture-data-contract.md:429-439`~~ — **CITATION CORRECTED 2026-08-24: the canonical D6 is at
`docs/superpowers/specs/2026-08-08-scientist-capture-data-contract.md:1003-1013`.** `:429-439` is a
different passage; this document restated D6 against the wrong line range from the start. (DECISION D6
— *"the honest v1 is transcript-only, provider-abstracted, audio never persisted"*):

- Audio is captured in the browser and **never leaves it except to a configured, approved
  transcription provider**. ~~**With no provider configured, the recorder is not offered at all — not
  offered-and-broken.**~~ **SUPERSEDED 2026-08-24 by an explicit product decision of the project
  owner** — the recorder ships and is offered; every safety property D6 argued for is enforced in
  code, and the departure from "not offered at all" is recorded, with its one-line fix, at the D6
  supersession in the capture spec. **This restatement is not the decision record — do not amend D6
  here.**
- The **transcript** is JSON text, so it can be persisted in the existing `state` jsonb with **no
  new storage of any kind**. Retention choice therefore applies to the transcript, which is real,
  and **not** to raw audio, which has nowhere to go.
- `TranscriptionProvider`, `CaptureExtractionProvider` and `AssistantProvider` are three separate
  seams. Default implementation for all three: **unconfigured, surfaced truthfully.** A
  deterministic fake provider exists for tests only and is never reachable in production.

~~**None of D6 is implemented** (§3's measurement 3: zero audio APIs in any source file).~~
**SUPERSEDED 2026-08-24:** D6's transcript path and its recorder BOTH ship (`TranscriptCapturePanel`,
mounted at `RecordWorkbench.tsx:687`); the provider seams are still unconfigured and answer `501`. The
parenthetical measurement is stale — re-measured **45** hits across **6** files (re-measured at `905c706`; ~~42~~ corrected 2026-08-24 by an independent truthfulness review, which found no commit on this branch yields 42 — the parent gives 41 and this branch gives 45), not zero.

### 4.1 The browser `SpeechRecognition` risk — a RISK, not an established fact

This needs its own heading because it is the item most likely to be mis-cited in either direction.

The spec states (`…-capture-data-contract.md:418-423`) that the obvious "free" fallback is not free
of governance: *"the browser `SpeechRecognition` API in Chrome transmits audio to a third-party
service, which is an external egress of potentially scientific speech"*. It then says, in the same
breath and unambiguously:

> **"This must be confirmed against current vendor documentation before it is either used or ruled
> out — it is stated here as a design risk, not as an established fact."**

**This packet does not resolve it, and cannot.** The session producing this document had **no web
access**, so no vendor documentation was consulted. Do not present the risk as settled in either
direction: not as "Chrome uploads your audio, therefore forbidden", and not as "unproven, therefore
fine."

**What would settle it:** current published documentation from the browser vendor on where
`SpeechRecognition` audio is processed — specifically whether recognition is on-device or
server-side, whether that differs by platform and by the `processLocally`-style options current
implementations expose, and what is retained. That is a **vendor-documentation audit with web
access**, of the same kind and rigour as the one already performed for MCP
(`docs/mcp-capability-audit.md`, which records its date, its sources, and per-finding confidence).
Until such an audit exists and is committed, **`SpeechRecognition` is neither approved nor
excluded**, and the honest product state is ~~D6's: no provider configured, so no recorder offered~~
**2026-08-24: no provider configured, and a recorder IS offered** — a knowingly recorded departure from D6's
"not offered at all", documented at the D6 supersession in the capture spec.

---

## 5. The external decision list

**These are the asks.** Each row is one decision. For each: the owner, what precisely is being
asked, what ISAAC does today without it, what becomes possible with it, the risk or cost, and what
ISAAC displays until it is answered.

> **STATUS OF EVERY ROW IN THIS SECTION, 2026-08-12: DEFERRED BY DEAN — none answered.** His
> recommendation was to *"leave AI integration as future work rather than increasing scope at this
> point"*, and he is away for roughly a week. **No row below has been approved, conditionally
> approved, or narrowed.** Each "Today without it" and "Until answered, ISAAC displays" line remains
> the operative behaviour.
>
> **Separately and by a different decision-maker:** the project owner has elected to continue
> **implementing** MCP, Connect Your Agent, the native LLM assistant, transcription/voice and the
> provider architecture against **deterministic fake providers**. That decision is Krish's, is
> recorded in the block at the head of this document, and **changes no row here** — a fake provider
> answers none of D1–D9, because every one of them is a question about a *real* one.

**Summary table** (detail follows; the detail is the substance).

| # | Decision | Owner | Capability it unblocks | Status 2026-08-12 |
|---|---|---|---|---|
| **D1** | MCP public reachability | Dean / SLAC infrastructure | A — any connector at all | **DEFERRED** by Dean |
| **D2** | MCP auth model | Dean / SLAC infrastructure | A — a real, verifiable connection | **DEFERRED** by Dean |
| **D3** | Model provider (which one) | Dean / Angel | B | **DEFERRED** by Dean |
| **D4** | API credential — who holds it, where it lives | Dean / Angel | B | **DEFERRED** by Dean |
| **D5** | Billing | Dean / Angel | B (and C, if the provider is metered) | **DEFERRED** by Dean |
| **D6** | Approved egress — what data may leave SLAC, to whom | Dean / Angel + whoever owns data governance | B and C | **DEFERRED** by Dean |
| **D7** | Retention — what the provider retains | Dean / Angel (with the provider's terms in hand) | B and C | **DEFERRED** by Dean |
| **D8** | Data policy — what may be sent at all | Dean / Angel | B and C | **DEFERRED** by Dean |
| **D9** | Transcription provider | Dean / Angel | C — any voice capture at all | **DEFERRED** by Dean |

`docs/mcp-capability-audit.md` §6 and `…-capture-data-contract.md` §9 already record the owners for
D1, D2, D3/D4/D5 (as one line, "Institutional Anthropic API credential + billing") and D9; **D6,
D7 and D8 are separated out here because a credential decision is not a data-governance decision**,
and the capture spec's §9 gate table does not name them individually.

> ### DO NOT RENUMBER D1–D9. Added 2026-08-11, because a renumbering was proposed.
>
> A continuation prompt proposed a list in which `D1` is *authoritative identity*, `D2` is *apply
> `0002_runs`*, and D3–D9 are **this table's D1–D7 shifted down by two** — so its `D5` is this
> document's `D3` (model provider), its `D9` is this document's `D7` (retention), and this document's
> D8 and D9 fall off the end. **Both lists are internally coherent; adopting the second on top of the
> first is what would do the damage.** These identifiers have left the repository: they are the labels
> Dean and Angel are being asked to answer against, and a shifted `D5` silently redirects an answer
> about *retention* onto *which provider*. That failure is silent by construction — every row still
> reads plausibly.
>
> **So the two genuinely new decisions were added where they belong, not by shifting these:**
>
> | Proposed label | Where it actually lives | Why there |
> |---|---|---|
> | *authoritative identity* | `identity-trust-contract.md` §7, **Q5 / Q10 / Q17 / Q18** (principal, stamping, UID lifecycle, untrusted headers), **Q6 / Q7** for authorization, plus new **Q25** for ISAAC's own override / submission / revision actor columns — **filed as `Q20` and renumbered the same day, because `Q20` was already taken by `format` enforcement and is load-bearing in `authorization.py`; see `identity-trust-contract.md` §7, "The `Q20` collision"** | That document asks the question **more precisely than a single "D1" can**. It already separates *which claim arrives* (observed, §6A) from *whether the claim is trustworthy* (Q18) from *whether the identifier survives a rename or rehire* (Q5, Q17) — three different answers from three different kinds of authority. Collapsing them into one row would lose the distinction that §6A.1 exists to protect. |
> | *apply `0002_runs`* | `migration-approval-packet-0002.md`, STATUS + §12A.3 | It is not an open question any more. Krish approved it on 2026-08-11 and the condition on that approval is discharged. What remains is an **operator action with a runbook** (§8 → §9 → §10), not a decision needing a packet row. |
>
> The rule, stated so it survives the next continuation: **an identifier that has been sent to an
> external decision-maker is append-only.** Add the next **free** identifier. Never shift.
>
> **MEASURE THE NEXT FREE NUMBER; DO NOT ASSUME IT (added 2026-08-11).** This line previously read
> *"Add `D10`, `Q21`"* — and **`Q21` was already in use when that was written**
> (`docs/portal-identity-and-metrics-audit.md:133`, *which identifier string is the authenticated
> identity*). So the rule against reusing an identifier shipped with an example that reused one.
> That is not an idle correction: on 2026-08-11 the actor-columns question was in fact filed as
> `Q20` — also taken, and load-bearing in `apps/api/isaac_api/authorization.py` — and had to be
> renumbered to `Q25` before the Dean handoff went out. Both mistakes have the same root: a number
> guessed rather than measured. The command:
>
> ```bash
> grep -rhoE '\bQ[0-9]{1,3}\b' docs/ apps/ src/ | sort -u -V | tail -3
> grep -rhoE '\bD[0-9]{1,3}\b' docs/ apps/ src/ | sort -u -V | tail -5
> ```
>
> **Two commands, not one, and that is a correction too.** A combined
> `'\b(Q|D)[0-9]{1,3}\b' … | tail -5` was written here first; `sort -V` orders every `D` before
> every `Q`, so it **can never report a `D`**, and a `D` claim attributed to it did not come from it.
>
> At the time of writing the first yields `Q24` as the highest `Q` in use, so `Q25` is next — which
> is why the actor question is `Q25`.
>
> **`D10` is still correct FOR THIS DOCUMENT'S SERIES, and the qualifier is load-bearing.** The
> second command reports `D12` repo-wide: `D10`–`D12` are live Phase-33 UI decisions in
> `docs/superpowers/plans/2026-07-23-phase-33-ui-refinement.md`, a different series that never leaves
> the repository. `D9` is the highest in **§5's** series, the one Dean and Angel answer against.
>
> **And a cross-namespace `D7` collision already exists**, so this is not hypothetical: §5's `D7` is
> *Retention*, while `migration-approval-packet-0002.md` and `0002_runs.sql` cite *"contract §8
> DECISION D7"* for *should Runs be relational*. Both are established; neither moves. **Name the
> document whenever you quote a `D`.**

---

### D1 — MCP public reachability

- **Owner:** Dean / SLAC infrastructure. (`docs/mcp-capability-audit.md:116` — *"Decide whether the
  MCP path may be internet-reachable"*, blocking *"any connector at all"*.)
- **Precisely what is asked:** may the MCP path of the ISAAC deployment be reachable from a
  scientist's own machine over the public internet — yes or no? If yes, on what hostname/path, and
  with what rate and source restrictions?
- **Why it is unavoidable:** Claude Code, Claude.ai and the Messages API all connect **from the
  client side**. An endpoint reachable only inside SLAC's network cannot be added as a connector at
  all (`docs/mcp-capability-audit.md:59-62`).
- **Today without it:** ~~nothing. No MCP server exists (measured, §2)~~ — **CORRECTED 2026-08-24: an MCP
  server exists** (10 tools, 13 operations) — **and no scientist can connect**, which is the half that
  still holds and the half this row is actually about: there is no hosted endpoint.
- **With it:** a scientist can *attempt* a connection — **necessary but not sufficient**; D2 is
  still required.
- **Risk / cost:** exposing an application path to the public internet, on infrastructure this
  repository does not own or track (`docs/identity-trust-contract.md:678-681` — `isaac-k8` holds
  every Kubernetes, ingress and Authentik manifest, is **not in this working tree**, and is Dean's).
  ~~Also note Q4 remains open: whether an in-cluster workload can already reach the Service directly,
  bypassing Authentik (`:688`). **unknown; Dean.**~~ **ANSWERED 2026-08-12, and it makes D1 harder,
  not easier: YES.** The Service is a plain ClusterIP with **no NetworkPolicy**, so an in-cluster
  workload can already reach the app directly, bypassing Authentik, and **can forge forwarded
  identity headers**. Exposing an MCP path publicly would add a second unauthenticated route to an
  application that already has one from inside the cluster. **operator-testimony; Dean.**
- **Until answered, ISAAC displays:** `Requires organization configuration`, naming public
  reachability as the specific missing item. **Not** a connection state, and not a retry.

### D2 — MCP auth model

- **Owner:** Dean / SLAC infrastructure. (`docs/mcp-capability-audit.md:117` — *"Choose the auth
  model — ISAAC-hosted OAuth AS vs. edge-accepted static token on the MCP path"*, blocking
  *"`Connect Your Agent` showing a real connection"*.)
- **Precisely what is asked:** choose one of exactly two shapes (`docs/mcp-capability-audit.md`
  §3): **(a)** ISAAC implements its own OAuth 2.1 authorization server, advertises it via
  `WWW-Authenticate` and `/.well-known/oauth-protected-resource`, and the edge passes OAuth traffic
  through; or **(b)** the edge is configured to accept a **pre-issued static token** on the MCP path
  specifically. The audit records that Claude Code and Claude.ai custom connectors do accept fixed
  header auth — a static bearer token — for services that do not implement full OAuth
  (`docs/mcp-capability-audit.md:46`, confidence high).
- **Why the answer cannot be "reuse the existing login":** a Claude client cannot complete an
  interactive Authentik login, and the audit found no documented pattern for transparent
  third-party-SSO traversal (`docs/mcp-capability-audit.md:63-66`). And ISAAC has **no identity of
  its own to reuse**: it consumes **none** of the seven forwarded headers
  (`docs/identity-trust-contract.md:558-566`), and two of them — `X-authentik-entitlements` and
  `X-Isaac-Edge` — are **permanently disqualified** from authentication, authorization, role
  assignment and from proving edge traversal, because on the tested path the client's own planted
  value arrived untouched (`:608-631`). **So "trust the edge marker to prove the call came through
  Authentik" is specifically not available.**
- **Today without it:** nothing. There is no auth model because there is no server.
- **With it:** a scientist's Claude can authenticate to ISAAC, and `Connect Your Agent` can show a
  connection state it has actually verified.
- **Risk / cost:** option (a) is a substantial security-sensitive build (OAuth 2.1, RFC 8414 or OIDC
  discovery, RFC 8707 resource indicators, RFC 9207 issuer validation, and either RFC 7591 dynamic
  registration or client-ID metadata documents — `docs/mcp-capability-audit.md` §2, confidences
  high except registration at medium). Option (b) is far less work but introduces a long-lived
  shared secret whose scope and rotation must be owned by someone. **Whichever is chosen, a bearer
  token must never be issued to the browser** — see D4.
- **Until answered, ISAAC displays:** `Requires organization configuration`, naming the auth model
  as the missing item, and naming the two options so the reader knows a decision exists.

### D3 — Model provider (which one)

- **Owner:** Dean / Angel.
- **Precisely what is asked:** which provider, if any, is ISAAC permitted to call — and is it a
  commercial API, a SLAC-hosted/self-hosted model, or none? The name matters, because D6, D7 and D8
  are all *about that provider's* terms and network location.
- **Today without it:** the assistant is deterministic, bounded to eight intents, and refuses
  anything outside them (measured, §3). It is honest and it works; it simply cannot draft prose,
  summarise freely, or extract from unstructured text.
- **With it:** free-form assistance, transcript→field extraction, and evidence summarisation become
  *possible* — still gated on D4–D8.
- **Risk / cost:** per-call cost; a runtime external dependency in a system whose current selling
  point is determinism; and the reproducibility problem — a model's output is not a deterministic
  function of its input, which is in tension with the truth plane's guarantees. **Mitigation that
  must be a condition of approval, not an afterthought: no model output may enter the truth path.**
  See §6.
- **Until answered, ISAAC displays:** the current, true statement — *"There is no language model in
  this build"* (`settingsContent.ts:587`). **This is not a placeholder to be softened. It is
  accurate today and must stay until the day it stops being accurate.**

### D4 — API credential: who holds it, where it lives

- **Owner:** Dean / Angel.
- **Precisely what is asked:** who is the account holder of record; where does the secret live
  (a Kubernetes Secret in Dean-owned `isaac-k8` is the only in-cluster mechanism this repository
  knows of); who may rotate it; and what happens on compromise?
- **A hard constraint, not a preference — the credential must never reach the browser.** This is
  already settled in this repository and enforced by test. **measured / code-reviewed:**
  - The `VITE_API_KEY` frontend seam was **removed outright** on 2026-08-08, not gated.
    `apps/web/src/lib/api.ts:104` carries the tombstone comment *"There used to be an `apiKey()`
    here that read `import.meta.env.VITE_API_KEY`"*.
  - The reason is recorded plainly (`docs/settings-api-capability-audit.md:31`): Vite substitutes
    `VITE_*` **at build time**, so any value would have been compiled into the JavaScript served to
    every visitor — *"a bearer token published as public JS is not an authentication control."*
  - **The inverse is pinned with the key planted.** `apps/web/src/__tests__/api.test.ts:168-169` —
    *"sends no Authorization header even when `VITE_API_KEY` is set"*, stubbing
    `'planted-secret-that-must-never-be-sent'`. Several other suites plant a value as a leak canary
    (`__tests__/diagnostics.test.tsx:71`, `backend-down-state.test.tsx:194`,
    `live-sync-screens.test.tsx:227`, `reset-demo.test.tsx:701`).

  > **Therefore: there must be no `VITE_API_KEY`, and no browser-side secret of any kind. A model
  > credential is a server-side secret, called from the server, or it is not a credential.** The
  > residual consequence is deliberate and recorded: the backend's `ISAAC_UI_API_KEY` seam still
  > works, so `ISAAC_UI_API_KEY` is henceforth a control for **non-browser callers** — *"the only
  > kind that can hold a shared secret without publishing it"*
  > (`docs/settings-api-capability-audit.md:40`).
- **Today without it:** ISAAC holds no model credential and makes no outbound call (measured, §3 —
  zero outbound HTTP call sites in `apps/api/isaac_api` or `src/isaac_records`).
- **With it:** the server can call the provider. Note this also creates the first runtime secret in
  ISAAC's request path whose leakage would cost money, which changes the threat model.
- **Risk / cost:** secret sprawl and rotation ownership; and a new leak surface. This repository
  already has leak-canary infrastructure for exactly this class of mistake and any credential work
  should extend it rather than invent a new pattern.
- **Until answered, ISAAC displays:** nothing about a credential. There is no field, no "enter your
  key" affordance, and there must not be one in the browser.

### D5 — Billing

- **Owner:** Dean / Angel. (`docs/mcp-capability-audit.md:118` — *"Institutional Anthropic API
  credential + billing"*, blocking the native embedded assistant.)
- **Precisely what is asked:** which cost centre pays; is there a budget cap; and what should the
  application do when the cap is reached — degrade to the deterministic assistant, or refuse?
- **Today without it:** ISAAC costs nothing per request. **And note the asymmetry that makes MCP
  attractive: under capability A the scientist's own subscription pays, so D5 does not gate MCP at
  all** (`docs/mcp-capability-audit.md:23-26`).
- **With it:** metered inference inside ISAAC.
- **Risk / cost:** unbounded spend under load or abuse; and a **user-visible availability cliff** if
  a cap is hit with no defined fallback. Recommendation to carry into the conversation: the
  fallback should be the existing deterministic assistant, which is a real, shipped, working
  capability — not an error page.
- **Until answered, ISAAC displays:** the deterministic assistant, with no cost or quota surface.

### D6 (EGRESS) — Approved egress: what data may leave SLAC, and to whom

> **Not to be confused with §4's `DECISION D6 (CAPTURE)`.** Same label, unrelated decision, different owner.

- **Owner:** Dean / Angel, plus whoever owns SLAC data governance for this class of content.
  **Listed separately from D3/D4/D5 deliberately** — approving a credential is not approving an
  egress.
- **Precisely what is asked:** is ISAAC permitted to transmit data to a named external endpoint at
  all; and if so, which classes of content — user-typed prose only? record field values? evidence
  quotes? file listings? scientific speech? **Each is a separate answer.**
- **Why this is sharper than it may appear.** `mode: synthetic-only` does **not** mean no real data
  exists in the process. `CLAUDE.md:917-919` states it *"describes the **workspace** — uploads
  refused, seeding from committed fixtures only. It has never meant 'no real data exists anywhere in
  the process', and since Slice 2A production-derived records transit pod memory during a scan."*
  **from-doc.** There are 30 production-derived records in the app-owned database, and hosted
  per-record **display** is `closed by default` pending Dean's explicit visibility decision (gate
  **G2** — `CLAUDE.md:777` and `:886`, and `…-capture-data-contract.md:62-64` which records
  `/api/health` still reporting `record_display: "closed"`).

  > **The inference, stated as an inference:** if per-record content may not be **displayed** to an
  > authenticated institutional user in a browser, it cannot be **transmitted to a third-party
  > provider** on a weaker authorization. So **D6 for record content is gated behind G2 at minimum,
  > and plausibly needs its own answer beyond it.** Nobody should read "we approved an assistant" as
  > approving record egress.
- **Today without it:** nothing leaves. Measured: zero outbound HTTP call sites in the runtime
  backend or the truth core.
- **With it, scoped:** exactly the content classes named, and no others.
- **Risk / cost:** this is the highest-consequence row in the table. An over-broad answer is
  effectively an unbounded data-export authorization.
- **Until answered, ISAAC displays:** the current true claim that nothing is sent to a model
  provider (`settingsContent.ts:587`), and ~~offers no recorder and~~ offers no model-backed feature.
  **CORRECTED 2026-08-24: a recorder IS offered** (see the D6 supersession); the no-model-backed-feature half
  is unchanged and still measured.

### D7 — Retention: what the provider retains

- **Owner:** Dean / Angel, working from the chosen provider's **current** terms.
- **Precisely what is asked:** for the provider chosen in D3 and the transcription provider chosen
  in D9 — what is retained, for how long, is it used for training, is zero-retention available,
  and is there a written agreement?
- **Today without it:** no third party holds any ISAAC data, because none is sent.
- **With it:** retention becomes a known, documented, bounded fact rather than an assumption.
- **Risk / cost:** default commercial terms are frequently **not** zero-retention. An assumption
  here would be exactly the kind of claim this project has repeatedly had to retract.
- **Until answered, ISAAC displays:** no retention claim of any kind. **A retention claim that has
  not been confirmed against current vendor terms must not be written on a product screen** — see
  §6 and the eleven-stale-claims precedent in §3.
- **Note on D6 vs D7 for audio specifically:** D6 asks whether audio may leave; D7 asks what the
  provider keeps. Under DECISION D6-of-the-spec, **ISAAC** retains no audio regardless, because
  there is nowhere to put it (§4, Blocker 1). *ISAAC not retaining audio is not the same as the
  provider not retaining it,* and only the vendor's terms can answer the second.

### D8 — Data policy: what may be sent at all

- **Owner:** Dean / Angel.
- **Precisely what is asked:** the standing rule, expressed so the application can enforce it
  mechanically. Concretely: **may scientific speech leave? may record field values leave? may
  evidence quotes leave? may unstructured scientist notes leave?** And is the rule per-deployment,
  per-user, or per-record?
- **Distinct from D6** because D6 authorises an egress *channel* to a *recipient*; D8 is the
  *content* rule the application enforces on every call, including in future features nobody has
  designed yet. A channel approval without a content rule is how scope leaks.
- **A precedent from this repository, worth citing because it shows how a content rule should be
  built.** For the read-only database recon, the rule adopted was: *"the schema may describe the
  data; the data may not describe itself"* — if an output string can only be produced by reading a
  record's value, it is per-record content and is closed (`CLAUDE.md:896`). And the enforcement is
  **frozen allowlists with projection and raise-on-unlisted-key**, because the earlier version froze
  only top-level response keys, so five aggregates shipped inside a nested block *"without tripping
  a single contract test"* (`CLAUDE.md:806`); gate **G3** *"remains OPEN"* as a result
  (`CLAUDE.md:821`). **The lesson transfers directly: an egress policy enforced by review rather
  than by an allowlist will leak.**
- **Today without it:** the deterministic assistant is *structurally* incapable of egress — it
  imports no HTTP client and takes *"no filesystem/network action"* (`assistant_query.py:14-16`).
  The policy is currently enforced by absence, which is the strongest enforcement available.
- **With it:** a model-backed feature can be built with a mechanical, testable content boundary.
- **Risk / cost:** the moment an egress path exists, "enforced by absence" is gone forever and must
  be replaced by an allowlist plus tests.
- **Until answered, ISAAC displays:** the current true statements, and no model-backed feature.

### D9 — Transcription provider

- **Owner:** Dean / Angel. (`…-capture-data-contract.md:509` — gate *"Transcription provider"*,
  owner *"Dean / Angel"*, blocking **"any voice capture at all"**.)
- **Precisely what is asked:** name an approved transcription provider, or state that none is
  approved. If one is named, D6, D7 and D8 must be answered **for that provider**, and the
  `SpeechRecognition` question in §4.1 must be settled by a vendor-documentation audit before that
  API is either used or ruled out.
- **Today without it:** ~~no recorder, no ASR client, no audio capture anywhere (measured, §3
  measurement 3 — the two hits in the whole tree are prose in the spec). **Per DECISION D6 the
  recorder is not offered at all — not offered-and-broken.**~~ **CORRECTED 2026-08-24.** There IS a recorder
  and there IS audio capture (`MediaRecorder`, `getUserMedia`); re-measured **45** hits across **6** files (re-measured at `905c706`; ~~42~~ corrected 2026-08-24 by an independent truthfulness review, which found no commit on this branch yields 42 — the parent gives 41 and this branch gives 45), not two.
  **No ASR client still holds**, and no audio leaves the browser — the wire carries a blob COUNT
  (`held-in-tab:<n>`), never a `Blob`. The recorder is offered and its transcription button returns
  `501`, i.e. precisely the "offered-and-broken" state D6 forbade; that departure is recorded, with
  the one-line fix named, at the D6 supersession in the capture spec.
- **With it:** transcript-only voice capture becomes buildable: audio captured in the browser, sent
  only to that provider, never persisted by ISAAC; the transcript stored as JSON text in the
  existing `state` jsonb with **no new storage**.
- **Risk / cost:** external egress of potentially **scientific speech** — the most sensitive
  content class in the whole packet, because speech is unstructured and a scientist will say things
  they would not type into a field. Plus the truth-core cost of Blocker 3 if a transcript is to be
  cited as evidence: an eighth `source_type` breaks **three** total maps and **two** enumerations
  (§4, Blocker 3), and touching `src/isaac_records/models.py` triggers `CLAUDE.md` §13's truth-path
  reporting obligation.
- **Until answered, ISAAC displays:** ~~no recorder and no microphone affordance at all.~~
  **CORRECTED 2026-08-24: it displays both**, plus a truthful "no transcription provider is configured"
  disclosure ABOVE the controls. See the D6 supersession.

---

## 6. Invariants that hold regardless of any answer

These are not requests. They are constraints that survive every possible answer above, and a "yes"
to any decision does not relax them.

### 6.1 No fake `Connected` state

Until an external answer configures a capability, the truthful display is **`Requires organization
configuration`**, naming the specific missing item.

- It **must not** be presented as available-but-broken — no spinner, no retry, no `Disconnected`
  implying a connection that could exist, no greyed-out `Connected` toggle.
- It **must not** show a connection state the application has not verified
  (`docs/mcp-capability-audit.md` §5: *"The Settings surface must say so rather than showing a
  connection state it cannot verify."*)
- For voice, the equivalent is D6-of-the-spec: **with no provider configured the recorder is not
  offered at all — not offered-and-broken** (`…-capture-data-contract.md:432-433`).

~~**Measured, and it is a gap worth naming honestly:** the string `Requires organization
configuration` and the label `Connect Your Agent` currently exist **only in documents**.
`rg --text -n -i -e 'Requires organization configuration' -e 'Connect Your Agent' apps/web/src apps/api src`
→ **exit 1, zero matches.** So the truthful display state is **specified, not implemented.** A
reader must not mistake this section for a description of a shipped screen.~~

**SUPERSEDED 2026-08-16 — the display state is now IMPLEMENTED**, and the measurement above is kept
struck through in place rather than rewritten, because it was true when it was taken and a reader
should be able to see that this changed rather than find a document that was always right.

Settings gained a seventh tab, **Connect Your Agent** (`?tab=mcp`), whose status banner reads
`Requires organization configuration` — derived from `MCP_ENDPOINT === null`, not hard-coded as a
label. Re-run at this commit, the same command now reports **exit 0, 9 files**:
`lib/mcpConnectContent.ts`, `screens/settings/ConnectYourAgent.tsx`, `screens/SettingsPage.tsx`,
`lib/routes.ts`, `lib/settingsContent.ts` and four `__tests__/` files.

**What has NOT changed, and must not be read into this.** The tab is a *description* of the agent
interface and an honest report that no agent can reach this deployment; **D1 and D2 are still
deferred**, there is still no endpoint, no configured way to authenticate a caller, and nothing to
revoke. §6.1's rule is not relaxed by being satisfied — it is now enforced by
`__tests__/connect-your-agent.test.tsx`, which ratchets the bare word `connected` out of the tab's
text *and* out of every attribute on it, in both endpoint branches.

### 6.2 External agents cannot submit — an invariant, not a default

**Never expose over MCP:** final authoritative `Submit Record`; application of a migration; any
governance change; any destructive global deletion.

`…-capture-data-contract.md:300` states it flatly: **"External agents cannot submit. No MCP tool
exposes it, ever."** And `docs/mcp-capability-audit.md` §5 lists under **"Never build"**: *"a
`submit_record` tool, a tool that deletes an experiment, a tool that applies a migration, or
anything that changes governance."*

**Enforcement is by non-implementation, server-side — never by an annotation**, because annotations
are hints a client may ignore (§2.1). Two supporting facts already in place:

- Submission is a genuinely new *stored* state with no existing signal it can be derived from, and
  there is deliberately **no `Submit Anyway` path**: a required validation failure on any Run blocks
  the whole submission (`…-capture-data-contract.md:274-298`, DECISIONS D3 and D4).
- Applying a migration to the hosted database is **the owner's act, not an agent's**
  (`CLAUDE.md` §15). An MCP tool that applied one would hand that act to an external agent.

### 6.3 No model output may enter the truth path

`CLAUDE.md` §3 already places AI review at stage 4 and **advisory only** — it must never mark
records valid or invalid, mutate records silently, override official schema or portal validation, or
block export. `CLAUDE.md` §13 lists the protected truth path
(`schema/isaac_record_v1.json`, `official.py`, `draft_validator.py`, `export.py`, `audit.py`,
`cli.py`, and the tests enforcing them).

**Consequences a model-backed feature must satisfy from day one:** a model may propose; only a human
confirmation writes; every written value carries evidence or a `user_confirmation`
(`CLAUDE.md` §5); and a model-proposed value is **never** `verified` on the model's word.

### 6.4 The no-guessing rule applies to the assistant's *own* answers too

`CLAUDE.md` §5 forbids inventing scientific values, units, sha256 hashes, URIs, paths, raw-data
pointers, descriptors, uncertainties, QC status, links, timestamps, and interpretations. The current
deterministic assistant satisfies this **structurally** — an unmatched question resolves to
`unsupported` and is refused, *"never guessed"* (`assistant_query.py:29-34`, `:804-810`). A
model-backed assistant does not get that for free, and a refusal path is therefore a **requirement**
of capability B, not a nicety.

---

## 7. Implemented / specified-but-unimplemented / blocked on an external answer

**Read this table before quoting anything above as a capability.**

| Item | State | Basis |
|---|---|---|
| Deterministic 8-intent assistant, read-only, refuses the unsupported | **IMPLEMENTED** | measured — `assistant_query.py:67-74`, `:76-77`, `:804-810`; `assistantAgent.ts:7-9` |
| User-facing disclosure that there is no language model | **IMPLEMENTED** | measured — `settingsContent.ts:580`, `:587`, `:546` |
| `POST /api/uploads` refuses unconditionally; no form parsing possible | **IMPLEMENTED** | measured — `routes.py` `# --- 15. uploads (always blocked) ---`, `def uploads():` with no parameters; `pyproject.toml:23` has no `python-multipart` |
| No browser-side secret; `VITE_API_KEY` seam removed and inverse pinned | **IMPLEMENTED** | measured — `api.ts:104`; `__tests__/api.test.ts:168-169` |
| MCP server | ~~**NOT IMPLEMENTED** — specified + audited only~~ → **IMPLEMENTED 2026-08-24**: 10 tools, 7 read / 3 write, behind 13 policy operations. **Still NO HOSTED ENDPOINT** (`POST /api/mcp` → 404 by default), so no scientist's agent can connect; D1/D2 remain deferred | measured — ~~`rg … 'mcp'` → exit 1~~; the same `rg` now → **487 matches**; `len(TOOLS)` → **10** |
| `Requires organization configuration` display state | ~~**NOT IMPLEMENTED** — specified only~~ → **IMPLEMENTED 2026-08-16** as Settings → Connect Your Agent (`?tab=mcp`). It reports a state and offers no action; D1/D2 are still deferred and there is still no endpoint | measured — ~~`rg …` → exit 1~~; the same `rg` now → **exit 0, 9 files**. See §6.1's supersession note |
| Native model-backed assistant | **NOT IMPLEMENTED.** A **production provider** remains out of scope by project rule and is **DEFERRED by Dean** (2026-08-12). **Implementation against a deterministic fake provider is authorized by the project owner** — see the head-of-document block; that authorization covers code, the provider abstraction and tests, and covers no real endpoint, credential or outbound call | measured (no provider, no outbound call site) + `CLAUDE.md:695-698` + owner decision 2026-08-12 |
| Voice capture / recorder / ASR | ~~**NOT IMPLEMENTED** — DECISION D6 specified only~~ → **RECORDER IMPLEMENTED 2026-08-24** (`TranscriptCapturePanel`); **ASR still NOT implemented** — no client, no provider, `POST /api/transcription` → `501`. Manual transcript works with no ASR (`200`) | measured — ~~zero audio APIs in any source file~~; re-measured **45** hits in **6** files, **4** of them source (`TranscriptCapturePanel.tsx` 10, `transcript-capture.test.tsx` 16, `transcriptCaptureContent.ts` 1, `test_provenance.py` 1); ~~42 hits in 1 source file~~ was wrong in BOTH numbers |
| Audio `source_type` | **NOT IMPLEMENTED**, and a **truth-core change** if pursued | measured — `models.py:29-37` (7, closed); 3 total maps + 2 enumerations |
| Transcript persistence in `state` jsonb | **SPECIFIED, needs no migration** | from-doc — `…-capture-data-contract.md:471-473` (`from_state` is legacy-tolerant; adding optional keys needs no migration) |
| MCP connector actually working end-to-end | **BLOCKED** on D1 + D2 | from-doc — `docs/mcp-capability-audit.md` §3, §6 |
| Any voice capability at all | **BLOCKED** on D9 (+ D6, D7, D8) | from-doc — `…-capture-data-contract.md:509` |
| Any native inference | **BLOCKED** on D3–D8 | from-doc — `…-capture-data-contract.md:510`; `docs/mcp-capability-audit.md:118` |
| **Any of the three CONNECTED to a real provider** | **BLOCKED, and now also DEFERRED** — D1–D9 were all deferred by Dean on 2026-08-12, so these rows have no pending answer to wait on | Dean's recommendation, relayed 2026-08-12 |
| **The same capabilities built against deterministic FAKE providers** | **AUTHORIZED BY THE PROJECT OWNER, 2026-08-12** — code, APIs, UI, auth abstraction, provider abstraction, tests, error handling, security boundaries. Subject to §6 in full, and to §9's *"build nothing that implies any of it exists"* | owner decision; see the head-of-document block |

---

## 8. Provenance: what was measured here, and what is only read

### Measured in this session, at `669b60c`

Each of these was established by a command run against the worktree at `669b60c`. Where an exit code
is quoted it is **`rg`'s own**, not a pipeline's.

| # | Claim | Command / citation |
|---|---|---|
| **M1** | ~~No audio-capture API exists in any source file~~ → **FALSE as of 2026-08-24** | ~~→ 2 hits, both prose in the capture spec~~; re-measured **45** hits in **6** files — `MediaRecorder` + `getUserMedia` in `apps/web/src/components/TranscriptCapturePanel.tsx`, plus its test file, `transcriptCaptureContent.ts` and `test_provenance.py`. **13 of the 45 are in THIS DOCUMENT**, quoting the pattern back at itself, which is why the total moves whenever this row is edited and why the FILE LIST is the durable half of the claim. Command unchanged: `rg --text -n -i 'MediaRecorder\|SpeechRecognition\|webkitSpeech\|getUserMedia\|AudioContext\|navigator\.mediaDevices' -g '!node_modules' -g '!.git' .` |
| **M2** | No model or ASR SDK; one prose false positive | the vendor-token sweep in §3; the only non-doc hit is `apps/web/src/styles/tokens.css:111` (`depth is a whisper`) |
| **M3** | No outbound HTTP call site in the runtime backend or truth core | `rg --text -n -e 'httpx' -e 'requests\.post' -e 'requests\.get' -e 'aiohttp' -e 'urllib\.request' apps/api/isaac_api src/isaac_records` → **exit 1** |
| **M4** | `httpx` is a declared dependency with no call site | `pyproject.toml:23`; only occurrence is a comment, `apps/api/tests/test_deploy_config.py:117` |
| **M5** | ~~No MCP implementation anywhere~~ → **FALSE as of 2026-08-24**; the surviving true claim is *no hosted MCP ENDPOINT* | ~~→ **exit 1**; `find` → only `docs/mcp-capability-audit.md`~~; same command re-measured → **487 matches**, exit 0. `POST /api/mcp` → **404** in the default environment |
| **M6** | `python-multipart` is not a dependency | `pyproject.toml:23` |
| **M7** | `POST /api/uploads` is a no-parameter unconditional 403 | `apps/api/isaac_api/routes.py`, marker `# --- 15. uploads (always blocked) ---`, handler `def uploads():` |
| **M8** | `SOURCE_TYPES` is closed at seven, none audio | `src/isaac_records/models.py:29-37`; mirrored `apps/web/src/lib/types.ts:17-24` |
| **M9** | Three total `Record<SourceType, …>` maps | `rg --text -n 'Record<SourceType' apps/web/src` → `EvidenceRow.tsx:5`, `icons.tsx:76`, `experimentGraph.ts:417` |
| **M10** | Assistant catalog is exactly eight intents, plus `unsupported`/`ambiguous` | `assistant_query.py:67-74`, `:76-77` |
| **M11** | No browser secret; inverse pinned with a planted key | `api.ts:104`; `__tests__/api.test.ts:168-169` |
| **M12** | ~~The truthful display strings exist only in documents~~ **SUPERSEDED 2026-08-16** — both strings are now in `apps/web/src`; the measurement stands as a record of `669b60c`, not of HEAD | `rg --text -n -i -e 'Requires organization configuration' -e 'Connect Your Agent' apps/web/src apps/api src` → **exit 1** *at `669b60c`*; **exit 0, 9 files** at HEAD. §6.1 carries the detail |
| **M13** | The app currently tells users there is no language model | `settingsContent.ts:580`, `:587`, `:546` |
| **M14** | `CLAUDE.md:775` still lands on "upload writes — NOT authorized" | re-read at this commit |
| **M15** | `CLAUDE.md:695-698` is the "external model provider / LLM" prohibition | re-read at this commit |

### Two places where a committed document was imprecise, and the code wins

1. **`SOURCE_ICON` is not in `EvidenceRow.tsx`.** `…-capture-data-contract.md:425-427` places both
   `SRC_CLASS` and `SOURCE_ICON` at `EvidenceRow.tsx:5-13`. Measured: `SRC_CLASS` is there
   (`EvidenceRow.tsx:5-13`), but `SOURCE_ICON: Record<SourceType, LucideIcon>` is defined at
   `apps/web/src/components/icons.tsx:76-84` and merely **imported** at `EvidenceRow.tsx:2`. The
   spec also omits a **third** total map, `SOURCE_TYPE_PHRASE` at
   `apps/web/src/lib/experimentGraph.ts:417`. **The correction makes the audio-source-type change
   larger, not smaller.**
2. **`POST /api/uploads` has moved.** The spec cites `routes.py:3151-3157` (`:404`), pinned at
   commit `a5601e9`. At `669b60c` the handler is at `routes.py:5262`. The **behaviour is exactly as
   the spec describes** — no parameters, unconditional 403 — but the line numbers no longer land.
   This packet therefore cites the section marker `# --- 15. uploads (always blocked) ---` in
   preference to a line number, and does the same for `# --- intent catalog ---` and for the
   `settingsContent.ts` strings, all of which sit in files that grow.

Neither is a defect in the spec's *conclusions*; both are the ordinary drift `CLAUDE.md` warns
about. **Correct the spec in its own slice — this document deliberately edits no existing file.**

### Read from a document and not independently re-derived here

- The `SpeechRecognition` third-party-egress **risk** (`…-capture-data-contract.md:418-423`) — and
  the spec itself labels it a risk, not a fact. See §4.1.
- The absence of any `write_bytes`/`wb` call in `apps/api/` or `src/`
  (`…-capture-data-contract.md:404`).
- The MCP transport, OAuth and Enterprise-Managed-Authorization findings
  (`docs/mcp-capability-audit.md` §2, §3), which were audited **2026-08-08 against vendor
  documentation with web access**. This session had **no web access** and could not re-verify them.
  The audit records per-finding confidence; carry it.
- The Authentik header observation (`docs/identity-trust-contract.md` §6A) — **operator testimony**,
  explicitly *not a captured artifact*, resting on two premises only the operator can confirm
  (that the canary was planted in all seven headers, and that it was distinctive and separator-free
  — `:542-546`).

### What this repository cannot know, and who can answer

| Unknown | Who can answer |
|---|---|
| May the MCP path be internet-reachable? (D1) | Dean / SLAC infrastructure |
| Which auth model, and will the edge pass OAuth traffic or accept a static token on that path? (D2) | Dean / SLAC infrastructure |
| Can an in-cluster workload reach the Service directly, bypassing Authentik? (**Q4**, `identity-trust-contract.md:688`) | Dean |
| The **complete** set of headers the edge injects — the probe tested a fixed seven-name allowlist, so a header under any other name *"remains entirely unknown"* (**Q1**, `:685`) | Dean |
| Will the infrastructure strip client-supplied `X-authentik-entitlements` / `X-Isaac-Edge`? (**Q18**, `:702`) | Dean |
| Is the Authentik username non-reassignable? Is `X-authentik-uid` permanent? (**Q5**, **Q17**, `:689`, `:701`) — *"institutional lifecycle facts no observation can settle"* (`:647-648`) | SLAC identity owners, via Dean |
| Whether hosted per-record content may be displayed — gate **G2**, still `closed by default` | Dean |
| Whether the five withheld recon aggregates were within intent — gate **G3**, still OPEN | Dean |
| Where Chrome's `SpeechRecognition` processes audio, and what is retained (§4.1) | current vendor documentation, via a web-access audit — **not answerable here** |
| The chosen provider's current retention and training terms (D7) | the provider's terms, read by Dean / Angel |
| Institutional model credential, billing owner, and cost centre (D4, D5) | Dean / Angel |
| Whether the capture **brief** sections cited by the spec (§14, §27, §29, §30, §31, §33, §34, §51, §54, §64.19, §64.24) say what the citing documents report | **the brief is not in this repository.** `rg --text -l '§64\.24' docs` returns only the two documents that *cite* it. Krish holds the brief. |
| Whether Krish holds a SLAC cluster context | not recorded here; `CLAUDE.md` §15 lists it as **inferred/unknown** |

---

## 9. Recommended order

Not a decision — a sequencing suggestion, offered because the decisions are not independent.

1. **Ask D1 and D2 first.** They gate capability A, whose implementation is *already unblocked* and
   costs SLAC nothing per request (the scientist's own subscription pays). It is the highest
   value-per-approval item in the packet.
2. **Ask D9 with D6/D7/D8 attached, never alone.** "Yes, use a transcription provider" without an
   egress rule, a retention answer and a content policy is an approval the application cannot
   enforce.
3. **Commission the `SpeechRecognition` vendor audit** (§4.1) as a small, separate, web-access
   piece of work before anyone argues about it. It is cheap and it removes a genuine unknown.
4. **Ask D3/D4/D5 last**, and only if there is a named ISAAC feature that a deterministic path
   genuinely cannot deliver. The current assistant is honest, shipped, and free; capability B's
   cost is not only money but the loss of "enforced by absence" (D8).

**In the meantime, build nothing that implies any of it exists.** The one thing this packet is for
is that ISAAC's screens keep telling the truth while these questions are open.

> ### AMENDED 2026-08-12 — the sequence is deferred; the sentence above is NOT.
>
> Dean deferred **all nine** decisions, so steps 1–4 of this recommended order have no one to be
> asked of for roughly a week. The order is kept because it will be the right order when the
> questions are re-put; nothing about it was wrong.
>
> **The project owner has nonetheless elected to continue implementing** MCP, Connect Your Agent, the
> native assistant, transcription/voice and the provider architecture, against **deterministic fake
> providers** (see the block at the head of this document). That is compatible with the closing
> sentence above, and the compatibility is exact rather than convenient:
>
> - *"Build nothing that implies any of it exists"* constrains **what the product claims**, not what
>   the repository contains. §6.1's no-fake-`Connected`-state invariant is the enforceable form of it
>   and is untouched.
> - A provider seam exercised only by a fake **implies nothing**, because nothing user-facing may
>   announce it. If a screen would have to say a provider exists in order for the work to be visible,
>   that screen is out of scope until D3–D8 are answered.
>
> **Step 3 is the one item here that is NOT blocked by the deferral.** The `SpeechRecognition` vendor
> audit (§4.1) needs web access and a reader, not an institutional decision. It remains cheap, useful,
> and available now.
