# Vendor-documentation audit — 2026-08-27

**Purpose.** Re-verify, against **current official vendor documentation with live web access**, the
voice / MCP / connector facts that the ISAAC programme has been planning against. This is an
**addendum to [`docs/mcp-capability-audit.md`](mcp-capability-audit.md) (audited 2026-08-08)**, not a
replacement: that document's §1 finding — *MCP is one-way; a Claude client calls ISAAC's tools and
ISAAC cannot call a Claude model* — is re-confirmed and untouched.

**Method.** Each row below was fetched from the vendor's own documentation on **2026-08-27** and is
quoted rather than paraphrased where the exact wording carries the constraint. Confidence is recorded
per finding. Where a page does **not** answer a question, this document says so rather than inferring
— the §4.1 failure mode the AI packet warns about.

**Sources fetched (all 2026-08-27):**

| # | URL |
|---|---|
| S1 | `https://support.claude.com/en/articles/11101966-use-voice-mode` |
| S2 | `https://code.claude.com/docs/en/voice-dictation` |
| S3 | `https://claude.com/docs/connectors/custom/remote-mcp` |
| S4 | `https://claude.com/docs/connectors/building/authentication` |
| S5 | `https://code.claude.com/docs/en/mcp` |
| S6 | `https://modelcontextprotocol.io/specification/2026-07-28/server/resources` |
| S7 | `https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition` |

---

## 1. Corrections — statements the programme has been carrying that are now measured FALSE

These are recorded as corrections, in the repository's established style, because each has appeared
in a planning document or a session prompt as an assumed fact.

### 1.1 "Voice mode is available on Claude web and desktop for Team and Enterprise users" — **FALSE**

S1 states, verbatim:

> "Voice mode is a beta feature available to all plans (Free, Pro, Max, Team, and Enterprise)"

and on platforms:

> "Claude Mobile (iOS and Android), Claude Desktop, and the web, but is built to work best from your
> phone."

**Two errors in the old sentence, in opposite directions.** It *understated* plan availability (it is
all plans, not Team/Enterprise only) and it *omitted mobile*, which the vendor names as the **best**
surface. For ISAAC this matters in a concrete way: the connected-companion design has assumed a
scientist at a desktop beside the beamline. Mobile being the vendor's primary voice surface makes
"scientist speaks into a phone while their hands are busy, and the proposals appear on the workstation
already open in front of them" the *central* scenario rather than an edge case — which strengthens,
not weakens, the argument for a persistent server-side proposal inbox rather than an ephemeral
client-side one. Confidence: **high** (direct quotation).

### 1.2 "Organization policy can disable voice" — **TRUE, but not self-service**

S1: *"If you are an Enterprise owner and would like to disable voice mode for your organization,
please reach out to Support."* So it is a **support request**, not an admin toggle. S2 independently
confirms the enforcement exists on the Claude Code side, via the error string *"Voice mode is disabled
by your organization's policy."*

**Consequence for the voice-governance packet:** the question to route is not "flip the setting" but
"has SLAC already asked Support to disable it, and if not, is it on by default for this tenant?"
Confidence: **high**.

### 1.3 MCP resource subscriptions do **not** use `resources/subscribe` in the current spec

The programme has repeatedly described subscriptions as `resources/subscribe` /
`resources/unsubscribe`. In the **2026-07-28** specification (S6) that is **not** the mechanism.
Clients subscribe by sending a **`subscriptions/listen`** request carrying the resource URIs in a
**`notifications.resourceSubscriptions`** filter; the server then delivers
`notifications/resources/updated` on the resulting stream, correlated by an
`io.modelcontextprotocol/subscriptionId` in `_meta`.

The capability declaration is:

```json
{ "capabilities": { "resources": { "listChanged": true, "subscribe": true } } }
```

and S6 states servers **"may advertise either feature independently, together or neither"**, and that
a server supporting neither **may omit** the sub-object entirely.

**This vindicates the existing plan of record and hardens it.** The instruction "use subscriptions
only if the actual client proves support" was right; what is now measured is that ISAAC declaring
`"subscribe": false` (or omitting the keys) is an *explicitly blessed* server posture, not a
shortfall. **`get_changes_since(cursor)` is therefore the primary mechanism, not a fallback.**
Confidence: **high** (normative spec text).

One further constraint from S6 that the change-feed design must respect, because it cuts against an
obvious implementation:

> the resource set **"MUST NOT vary per-connection or as a side effect of other requests on the
> connection. The set MAY vary by the authorization presented on the request — for example, returning
> only the resources the caller's granted scopes permit — since credentials are per-request input, not
> connection state."**

So a companion session **must not** be allowed to narrow `resources/list` as connection state. Scoping
has to ride on the **authorization presented per request**. This is a genuine design constraint on the
companion-session model and it is the opposite of the intuitive "attach narrows the connection"
reading.

---

## 2. Claude Code voice dictation — confirmed, with one fact that settles a governance question

S2, verbatim:

> **"Voice dictation streams your recorded audio to Anthropic's servers for transcription. Audio is
> not processed locally."**

Also established, and each is load-bearing for the voice-governance packet:

| Fact | Quote / detail | Why it matters to ISAAC |
|---|---|---|
| Requires a Claude.ai account | *"the speech-to-text service is only available when you authenticate with one, and is not available when Claude Code is configured to use an Anthropic API key directly, Amazon Bedrock, Google Cloud's Agent Platform, or Microsoft Foundry"* | A SLAC-Bedrock-style procurement route **does not** get voice. Voice implies a Claude.ai tenant. |
| Not available remotely | *"voice dictation does not work in remote environments such as Claude Code on the web or SSH sessions"* | A scientist SSH'd into a beamline workstation **cannot** dictate. Local machine only. |
| Not metered | *"Transcription does not consume Claude messages or tokens and does not count toward the limits shown in `/usage`"* | Removes a cost objection; does **not** remove the data-egress question. |
| Org policy enforced | error: *"Voice mode is disabled by your organization's policy"* | Confirms §1.2 from the other side. |

**The governance consequence is unchanged and now rests on a quotation rather than an inference:** if a
scientist dictates experimental detail through `/voice`, **that audio leaves SLAC and reaches
Anthropic.** D6 (egress), D8 (data policy) and D9 (transcription provider) are therefore *live* for the
Claude-Code path specifically — they are not deferred merely because ISAAC has configured no provider
of its own. ISAAC does not control this path and cannot mitigate it in code; it is a policy question
for Dean and SLAC. Confidence: **high**.

---

## 3. Remote MCP connector — administration

From S3:

- **Team/Enterprise:** *owners* add the connector at **Organization settings → Connectors → Add →
  Custom**, choosing type **Web**, entering the remote MCP server URL, optionally configuring an OAuth
  Client ID/Secret under Advanced. **Members** then connect individually via **Customize → Connectors
  → Connect**. This confirms the programme's existing statement.
- **NEW, and not previously recorded:** Free/Pro/Max users can add a custom connector **themselves**
  (*Customize → Connectors → Add custom connector*). The programme has described org-admin
  registration as the only path. It is the only path *for an org-wide connector*; it is not the only
  path that exists. A pilot with one or two scientists on individual plans does not strictly require
  an org-admin action to *connect* — though it still requires everything in §4 to be reachable.
- **`static_headers` is in beta**, allowlisted to a fixed set of header names (`authorization`,
  `x-api-key`, `x-auth-token`, …), **maximum four headers**, and *"each name is reviewed before Claude
  will send it to a third-party server."*
- Claude sends a header value **exactly as entered, with no scheme prefix added** — an `Authorization`
  header value must itself include `Bearer `.

**ISAAC-relevant judgement, stated as a judgement and not as a vendor fact:** `static_headers` is a
**single organization-wide shared credential**. S3: *"Request headers suit services where everyone in
your organization shares one credential… If each person needs to sign in with their own account, use
OAuth instead."* ISAAC's scientific invariants require a **verified per-scientist identity** for actor
stamping, attribution and revision authorship. A shared bearer token **cannot** satisfy that and must
not be used for Draft mutations. It remains viable **only** for a read-only, non-attributing
demonstration. This is consistent with the existing rule "no shared bearer credential for Draft
mutations", and now has a vendor-sourced basis.

---

## 4. Authentication — the concrete requirements, several of which the programme has never recorded

S4 is the most operationally valuable page fetched, because it converts "Dean must configure OAuth"
from a gesture into a checklist. Every item below is a **direct requirement**.

### 4.1 The requirement nobody has written down: Anthropic's egress range

> **"Anthropic's outbound traffic to your server originates from `160.79.104.0/21`."**

And, critically, it applies to the **authorization server too**:

> *"that host must also be reachable from Anthropic's published egress range… Discovery requests to
> the authorization server come from the same IP range as requests to your MCP server, so a WAF in
> front of your identity provider can break the flow even when your MCP server is reachable."*

**This is a new, concrete, routable SLAC networking ask** that the existing packets do not contain.
"D1 — MCP public reachability" has been carried as a vague question; it is in fact two specific
allowlist entries: the **MCP endpoint** *and* the **Authentik issuer host**, both from
`160.79.104.0/21`. Confidence: **high**.

### 4.2 Callback URLs — exact values

| Client | Redirect URI to register |
|---|---|
| Claude.ai web, Desktop, mobile, Cowork | `https://claude.ai/api/mcp/auth_callback` |
| Claude Code | RFC 8252 loopback on an **ephemeral port**; declares `http://localhost/callback` and `http://127.0.0.1/callback` in its Client ID Metadata Document, and the authorization server **must accept both with the port component ignored** |

The port-agnostic loopback match is a real Authentik configuration detail that will fail silently if
missed. Confidence: **high**.

### 4.3 The discovery handshake

> ```http
> HTTP/1.1 401 Unauthorized
> WWW-Authenticate: Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource"
> ```

- **The `401` status is required** — *"Claude does not honor a `WWW-Authenticate` header on a `200`
  response."*
- The `resource_metadata` URL **need not be on the MCP server's origin**; any HTTPS location serving
  the JSON works. **This is the escape hatch for ISAAC's Authentik-edge problem**, because it means
  ISAAC does not have to persuade the edge to serve `/.well-known/*` at the root.
- Fallback probing (`/.well-known/oauth-protected-resource/<path>`, then
  `/.well-known/oauth-protected-resource`) exists but is *"a fallback"* and adds round-trips.
- The protected-resource document's **`resource` field must match the MCP server URL exactly as the
  user enters it in Claude, including any path component.** For ISAAC that path component is `/krish`
  — an easy and silent mismatch.
- **`authorization_servers`: Claude uses the FIRST entry and does not fall back to later entries.**

### 4.4 PKCE, registration, and what is *not* supported

- Claude sends `code_challenge_method=S256` on **every** authorization request, and the AS metadata
  must advertise `"code_challenge_methods_supported": ["S256"]`.
- Registration options: **DCR** (RFC 7591), **CIMD**, or **Anthropic-held credentials**
  (`mcp-review@anthropic.com`). CIMD is selected **only** when the AS metadata advertises **both**
  `"client_id_metadata_document_supported": true` **and** `"none"` in
  `token_endpoint_auth_methods_supported`; otherwise Claude falls back to DCR.
- **A pure machine-to-machine `client_credentials` grant is NOT supported.** *"Every connection
  requires user consent."*

  **This is decisive for ISAAC and should be read twice.** It independently forecloses the
  "service-principal token for the companion" shortcut at the *vendor* level, in addition to ISAAC's
  own rule. There is no configuration in which a connected Claude acts as an unattended service
  account. **Every companion connection is consented to by a named human** — which is exactly the
  posture the scientific invariants require, and it is now guaranteed by the client rather than only
  asserted by the server.

### 4.5 Operational limits

- Token endpoint **must** accept `Content-Type: application/x-www-form-urlencoded`; `/register` uses
  `application/json`. *"don't assume the same parser works for both."*
- Timeouts: **10 s** for discovery, registration and token; **30 s** for refresh.
- Refresh is **reactive on 401**, with proactive refresh up to five minutes before expiry.
- Return **`invalid_grant`** (RFC 6749-compliant) for a dead refresh token, not a custom code.
- Public clients (DCR and CIMD register Claude as one) — **rotate refresh tokens**.

---

## 5. Claude Code MCP transport — confirmed

S5: four transports (HTTP/streamable-http, SSE, WebSocket, stdio).

> *"HTTP servers are the recommended option for connecting to remote MCP servers."*
> *"The SSE (Server-Sent Events) transport is deprecated. Use HTTP servers instead, where available."*

Confirms the plan of record. Newly recorded: `claude mcp login <name>` exists as a command-line OAuth
entry point (v2.1.186+), alongside `/mcp`; and `.mcp.json` supports a **`headersHelper`** executable
for dynamically-computed auth headers — which is a legitimate route for a scientist to present a
short-lived SLAC-issued credential without it being stored statically. Confidence: **high**.

---

## 6. `SpeechRecognition` — the open question from `ai-integration-decision-packet.md` §4.1 is now ANSWERED

§4.1 said the browser-`SpeechRecognition` egress concern *"must be confirmed against current vendor
documentation before it is either used or ruled out — it is stated here as a design risk, not as an
established fact"*, and that settling it required *"a vendor-documentation audit with web access"*.
**This is that audit.** The answer has two halves and quoting only one would be the §4.1 failure
itself.

**Half one — the risk is CONFIRMED for the default path.** MDN (S7), verbatim:

> **"On some browsers, like Chrome, using Speech Recognition on a web page involves a server-based
> recognition engine. Your audio is sent to a web service for recognition processing, so it won't work
> offline."**

So the spec's design risk was **correct**, and "free browser speech recognition" would in fact have
been an uncontrolled egress of scientific speech to a third party. Confidence: **high**.

**Half two — a documented mitigation now exists that did not when §4.1 was written.** The API has
gained on-device processing: **`SpeechRecognition.processLocally`** — *"Specifies whether speech
recognition must be performed locally on the user's device"* — together with
`SpeechRecognition.available()` to query per-language availability and `SpeechRecognition.install()`
to install language packs. Chromium's own announcement of the feature describes it as letting sites
*"ensure that neither audio nor transcribed speech are sent to a third-party service for
processing."*

**The honest verdict, and it is not "approved":** MDN marks the feature **"Limited availability"**,
meaning it lacks broad cross-browser support. `processLocally` is therefore a **request that can
fail**, not a guarantee. Any ISAAC use would have to (a) call `available()` first, (b) refuse to
record at all when on-device is unavailable rather than silently falling back to the cloud engine, and
(c) never present the cloud path as local.

**Recommendation, offered as a recommendation and not a decision:** ISAAC should **not** adopt
browser `SpeechRecognition` for the connected-companion pilot. It is not needed — the companion path
routes speech through the scientist's own Claude client, where the egress is governed by Anthropic's
terms and by SLAC's tenant policy rather than by ISAAC's code — and adopting a "limited availability"
API whose failure mode is *silent cloud egress of experimental speech* buys nothing the pilot needs.
The finding is recorded so the option is **understood** rather than perpetually re-litigated. §4.1 may
now be cited as resolved, in both directions, against this document.

---

## 7. What this changes for ISAAC — actionable, and separated by owner

**Application-side (no external answer needed; ISAAC can build these now):**

1. Declare MCP `resources` capability with **`subscribe` absent or `false`**, and make
   `get_changes_since(cursor)` the primary change mechanism — now a *blessed* posture (§1.3), not a
   compromise.
2. Ensure per-request authorization scoping of any resource list, never per-connection narrowing
   (§1.3, normative).
3. Implement the `401` + `WWW-Authenticate: Bearer resource_metadata="…"` handshake and a
   protected-resource-metadata document whose `resource` matches the deployed URL **including the
   `/krish` path** (§4.3).
4. Keep `static_headers` strictly out of any Draft-mutating path (§3).

**Dean / SLAC infrastructure (external — prepare the ask, do not perform it):**

5. Allowlist **`160.79.104.0/21`** to **both** the MCP endpoint **and** the Authentik issuer host
   (§4.1). *This is new and is the single most concrete unblocking item this audit produced.*
6. Register redirect URIs `https://claude.ai/api/mcp/auth_callback` and port-agnostic loopback for
   Claude Code (§4.2).
7. Confirm Authentik advertises `code_challenge_methods_supported: ["S256"]`, and decide DCR vs CIMD
   vs Anthropic-held credentials (§4.4).
8. Confirm the token endpoint accepts form-urlencoded and responds within 10 s (§4.5).

**Voice governance (external):**

9. `/voice` in Claude Code **sends audio to Anthropic** and requires a Claude.ai account (§2). Whether
   a scientist may dictate experimental content is a SLAC policy question, not an ISAAC setting.
10. Voice is on by default on all plans; disabling is a **Support request** (§1.2).

---

## 8. Limits of this audit — stated so it is not over-cited

- Every finding is from **published vendor documentation read on 2026-08-27**. **Nothing here was
  tested against a live Claude client**, no connector was registered, and no OAuth flow was executed.
  Documentation describing a behaviour is weaker evidence than observing it.
- **No statement here is an authorization.** It establishes what *would be required*; it does not
  approve reachability, egress, a tenant, a credential, or any scientific data use. D1–D9 are exactly
  as open as they were.
- S1 **does not** state where Claude *voice mode* audio (as opposed to Claude Code `/voice`) is
  transcribed. It says only that *"Textual transcripts of your audio conversations are saved in your
  chat history."* Inferring from S2 that voice-mode audio also reaches Anthropic's servers is
  **likely but not documented on S1**, and is recorded here as an inference, not a quotation.
- The MCP specification audited is **`2026-07-28`**. Claude's own authentication page currently cites
  the **`2025-11-25`** authorization spec. That version skew is real and unresolved here; where the
  two differ on authorization, the **client's** documented behaviour governs what actually connects.
