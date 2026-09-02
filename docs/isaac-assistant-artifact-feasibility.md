# ISAAC Assistant as a Claude Artifact — feasibility, verified

**Verification date: 2026-08-31**; **§2.1 and §2.2's pages re-fetched and re-read
from raw bytes 2026-08-31/09-01, and both corrected — read §0 first.** Every vendor
claim below was fetched from `support.claude.com` and is quoted, not recalled. Every ISAAC claim
was measured against the working tree at `ddec2b5`. Where a page does not address a
question, this document says **NOT ADDRESSED** and stops — an unfetchable or silent
page is never converted into an assumed "yes".

**This document authorizes nothing.** It is an investigation. Dean deferred
**D1–D9** on 2026-08-12 (*"leave AI integration as future work rather than
increasing scope at this point"*), so no production endpoint, credential, network
path, billing arrangement or provider approval exists or may be created. The
project owner separately authorized **building against deterministic fakes**
(`CLAUDE.md` §15). Both are true; this slice lives entirely inside the second and
touches none of the first.

---

## 0. CORRECTIONS — 2026-09-01, after an independent review and a re-fetch

**Two of this document's conclusions rested on sentences that are on the pages it
cites and were not read.** Both are corrected in place and marked, never silently
edited, because "NOT ADDRESSED" and "the load-bearing gap" are exactly the kind of
claims a future session acts on. Every page was re-fetched and re-read **from raw
bytes** on 2026-08-31/09-01; the quotes below were located in the response body, not
recalled.

### C1 — The flagship "unknown" was answered, in the same paragraph, one clause later

The artifacts page carries this sentence **between two sentences §2.1 already
quotes**:

> *"In addition to Anthropic's official MCP integrations, artifacts can connect to
> any **custom MCP servers** you've configured."*
>
> — <https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them>

It is **in the same paragraph** as the "tools like Asana, Google Calendar, and
Slack" sentence, immediately after it, and the words *custom MCP servers* are a
**hyperlink to Intercom article 11175166** — the custom-connector page §2.3 cites.

**What it invalidates, named rather than quietly repaired:**

| Was | Is |
|---|---|
| §3 **Q2**: *"**SUPPORTED** for MCP; **NOT ADDRESSED** for *custom* connectors specifically"*, confidence Medium | **SUPPORTED**, confidence High |
| §3.2's argument: the three named examples are first-party, so custom connectors are *"a reasonable reading of the same sentence but … not separately documented"* | **Wrong.** The same paragraph names them explicitly and links to their page. |
| §7 item 1: *"That a Claude artifact can call a **custom** (self-hosted, unverified) remote MCP server … This is the load-bearing gap."* | **Not a gap.** Struck in §7, with the quote that closes it. |

**How the omission happened is the part worth carrying forward.** The paragraph was
read *for* the sentence being looked for — artifact→MCP — and the reading stopped
at that full stop. Everything downstream inherited the stop: §3.2's argument, §7's
headline item, and the slice's own commit message, which told a future reader that
*"the CUSTOM-connector page never mentions artifacts … It heads the
externally-unverifiable list."* (A commit message cannot be corrected in place; this
section is where that correction lives, and the follow-up commit says so.) It did
**not** reach `artifact_link.py`, the page source, the behaviour contract or the
operator checklist — measured, not assumed: `grep -rn custom` over those files
returns only the checklist's two references to *adding a custom connector*, which
are unaffected. Nothing was fabricated anywhere; **a silence was manufactured, and a
manufactured silence is indistinguishable from a measured one** once it is written
down as NOT ADDRESSED.

**Four further sentences from the same pages were missing** and are added at §2.1,
§2.2, §3.9 and §3.10. Three of them narrow what this companion may assume:

- *"Persistent storage is only available for published artifacts. During
  development and testing, storage operations will not succeed until the artifact
  is published."* — so an **organization-shared** companion has **no persistent
  storage at all**, which is a stronger fact than §3.10's rule and reaches it by a
  different route.
- *"MCP integration for artifacts is available on Pro, Max, Team, and Enterprise
  plans on Claude web and desktop."* — a **plan and platform floor** this document
  had not recorded: not Free, and not mobile.
- *"Organization admins can enable or disable artifact MCP access at the
  organization level but cannot manage which specific MCP servers artifacts can
  use."* — an org-level kill switch exists (a documented unavailability state for
  §3.9), and an org admin **cannot** restrict artifacts to ISAAC's connector alone.

**Every other §3 verdict was re-checked against the re-fetched pages.** Q1, Q3, Q4,
Q5, Q6, Q7, Q8, Q11 and Q12 are unchanged and rest on no part of the skipped
sentence. Q9 and Q10 **gain** the facts above without changing verdict: Q9 stays
partially documented (expiry and unreachability are still NOT ADDRESSED), and Q10
stays NOT ADDRESSED for retention and visibility.

### C2 — §4's dilemma rested on a fact the same page contradicts

§4 framed the choice as *"deep link, or take an unauthorized publishing decision"*,
which presents publishing as **available and merely forbidden**. On a SLAC Team
organization it is **not offered at all**:

> *"Artifacts created on Team or Enterprise accounts can only be shared within your
> organization—they cannot be published publicly."*
>
> *"Publishing is available on Free, Pro, and Max plans."* · *"Internal sharing is
> available on Team and Enterprise plans."*
>
> — <https://support.claude.com/en/articles/9547008-publish-and-share-artifacts>

**The decision does not change; it stops depending on an authorization argument.**
See the corrected §4.

**And this document already held the adjacent fact.** The operator checklist's step
1 said *"A Pro or Max account can publish **publicly only**"* — the same sentence's
other half, never carried back into §4. That tension is resolved in both places:
§4 now reasons from availability, and the checklist now states both directions and
cites the sentence.

---

## 1. The question

Could the ISAAC record-completion assistant be delivered as a Claude Artifact,
shared privately inside a SLAC Team organization, calling ISAAC's existing MCP
tools under each scientist's own Claude subscription — and could that artifact be
surfaced from `isaac.slac.stanford.edu`?

Short answer: **the artifact and MCP halves are documented and supported —
including MCP to a *custom* server, which §0/C1 corrects from an "unknown" to a
quoted "yes". The embedding half is not offered at all for a Team/Enterprise
artifact**, and the decision that follows is a deep link.

---

## 2. Sources, and exactly what each does and does not support

All five URLs fetched successfully on 2026-08-31. None failed.

### 2.1 What are artifacts and how do I use them
<https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them>

**Supports:**

- *"You can build artifacts that embed AI capabilities, turning them into
  AI-powered apps. Users of your artifacts can access Claude's intelligence through
  a text-based API."*
- *"Usage counts against each user's own Claude subscription limits, not yours."*
- *"For Team and Enterprise plans, when you share AI-powered artifacts within your
  organization, team members can use them without incurring additional costs to the
  creator."* (**Quote corrected 2026-09-01** — this document previously dropped the
  leading clause and recapitalised the sentence. The meaning is unchanged and the
  clause it dropped is the one that scopes it to exactly the plan tier ISAAC would
  use, so it should never have been trimmed.)
- *"Users authenticate with their Claude account and interact with their own
  instance of the artifact."*
- *"Artifacts can connect to external services through the Model Context Protocol
  (MCP), enabling interactive applications that read from and write to tools like
  Asana, Google Calendar, and Slack."*
- **ADDED 2026-09-01 (see §0/C1).** The very next clause of that same paragraph:
  *"In addition to Anthropic's official MCP integrations, artifacts can connect to
  any **custom MCP servers** you've configured."* — and *custom MCP servers* is a
  hyperlink to Intercom article **11175166**, i.e. to §2.3's page.
- **ADDED 2026-09-01.** *"MCP integration for artifacts is available on Pro, Max,
  Team, and Enterprise plans on Claude web and desktop."* (a callout heading the
  MCP section — a plan **and platform** floor: not Free, and not mobile).
- *"When an artifact needs to access an MCP tool, you'll be prompted to approve
  access on first interaction."*
- *"Each user must authenticate MCP servers independently, even when using shared
  or published artifacts."*
- **ADDED 2026-09-01.** The rest of that same callout: *"Organization admins can
  enable or disable artifact MCP access at the organization level but cannot
  manage which specific MCP servers artifacts can use."*
- *"Artifacts can store data across sessions"*; *"20 MB storage limit per artifact,
  Text-only input—no images, files, or binary data, Personal and shared storage are
  isolated."*
- **ADDED 2026-09-01.** *"Persistent storage is only available for published
  artifacts. During development and testing, storage operations will not succeed
  until the artifact is published."* And, heading that section: *"Persistent
  storage for artifacts is available on Pro, Max, Team, and Enterprise plans on
  Claude web and desktop."*
- *"By default, artifacts in Claude Code are only visible to the individual who
  created them. They can choose to share artifacts with the rest of their
  organization, and they can't be shared publicly."*

**Does NOT support / NOT ADDRESSED:** any JavaScript API surface for the
"text-based API" or for MCP calls; iframe or external-site embedding mechanics;
URL parameters or deep links carrying input; what logs or prompts are retained or
who can read them.

### 2.2 Publish and share artifacts
<https://support.claude.com/en/articles/9547008-publish-and-share-artifacts>

**Supports:**

- Publishing: *"Makes your artifact publicly available. Anyone with the link can
  view and interact with it."*
- Sharing: *"Makes your artifact available within your organization only. Viewers
  must be logged into your Team or Enterprise account to access it."*
- **ADDED 2026-09-01 (see §0/C2).** *"Artifacts created on Team or Enterprise
  accounts can only be shared within your organization—they cannot be published
  publicly."* With the two plan callouts that bracket it: *"Publishing is available
  on Free, Pro, and Max plans."* and *"Internal sharing is available on Team and
  Enterprise plans."* The page's own labels carry the tiers too — *"Publishing
  (Free, Pro, Max)"* and *"Sharing (Team, Enterprise)"*.
- **ADDED 2026-09-01.** *"When you share an artifact, viewers also gain access to
  any attachments and files in the conversation that created it. Consider this
  before sharing artifacts from conversations containing sensitive documents."*
  Found on the same re-fetch; it is a data-visibility fact this document's own
  standard required recording, and it is now a line in the operator checklist's
  **Never** list.
- Access to published: *"Non-users: View and interact with any published artifact
  without signing up."*
- Access to shared: *"Only members of your Team or Enterprise organization. Viewers
  must authenticate with their Team or Enterprise account."*
- Embedding: *"After publishing, you'll see a 'Get embed code' button… Click it to
  open a modal with automatically generated code you can copy and paste to embed
  your artifact on another website… You must specify which websites can embed your
  artifact by entering URLs in the **Allowed domains** field, separated by commas."*

**The page's own section order, which is load-bearing for §4:**

1. Publishing vs. sharing · 2. Publish artifacts · 3. Who can access published
artifacts · **4. Embed artifacts** · 5. Unpublish artifacts · 6. Build on a
published artifact · **7. Share artifacts within your organization** · 8. Who can
access shared artifacts · 9. Share artifacts with attachments · 10. Unshare
artifacts · 11. Learn more

**Does NOT support / NOT ADDRESSED:** embedding an organization-shared
(non-public) artifact — sections 7–10 contain no embedding instruction of any kind;
how a viewer of an embedded artifact authenticates; whether viewers spend their own
credits; what creators, org members or Anthropic can see; MCP inside a shared
artifact; URL parameters or launch-with-input.

### 2.3 Get started with custom connectors using remote MCP
<https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp>

**Supports:**

- *"Only Owners can add them to Team and Enterprise plans. Once a connector has
  been added to a Team or Enterprise organization, users individually connect to
  and enable that connector."*
- *"Custom connectors using remote MCP are available on Claude, Cowork, and Claude
  Desktop for users on Free, Pro, Max, Team, and Enterprise plans."*
- *"you'll typically go through an OAuth authentication process to securely sign in
  to the application and grant specific permissions."*
- *"You can revoke these permissions at any time by disconnecting the connector in
  Claude's settings or the third-party service's security settings."*
- *"Review Claude's tool approval requests carefully and only click 'Allow always'
  when using a server and tool that you trust to run unsupervised."*
- *"During the research process, Claude can invoke tools from your connectors
  automatically without further approval."*
- *"Claude can only access resources that you've given the server permission to
  access."*
- *"Custom connectors allow you to connect Claude to arbitrary services that have
  not been verified by Anthropic."*

**Does NOT support / NOT ADDRESSED:** behaviour on an **expired** or unreachable
connector; any logging or data-visibility statement.

~~whether **artifacts** specifically can call **custom** connectors (this page never
mentions artifacts)~~ — **CORRECTED 2026-09-01, and the precise form matters.** It
remains true that *this* page never mentions artifacts. What is false is the
inference drawn from that silence, because **the artifacts page names custom MCP
servers explicitly and links here** (§2.1, §0/C1). The support is asserted by the
artifacts page, not by this one; a page's silence about a subject is not evidence
when another page addresses it directly.

### 2.4 Use voice mode
<https://support.claude.com/en/articles/11101966-use-voice-mode>

**Supports:**

- *"Voice mode is a beta feature available to all plans (Free, Pro, Max, Team, and
  Enterprise) on Claude Mobile (iOS and Android), Claude Desktop, and the web."*
- *"Textual transcripts of your audio conversations are saved in your chat history
  just like text conversations."*
- *"In voice mode, Claude can use the tools you've connected, like Gmail, Google
  Calendar, Google Docs, and Slack."*
- *"Connected tools work the same way in voice mode as they do in text chat and
  follow the rules of your plan."*

**Does NOT support / NOT ADDRESSED — and each of these was on the "do not assume"
list:** that voice mode can control or type into an artifact's custom text field
(**NOT ADDRESSED**); that raw audio reaches anything other than Claude (**NOT
ADDRESSED**); that a *verbatim* transcript is available to an artifact (**NOT
ADDRESSED** — the page says transcripts are saved to *chat history*, which is not
the same claim); who can access those transcripts.

### 2.5 Subscription vs. API/Console billing
<https://support.claude.com/en/articles/9876003-i-have-a-paid-claude-subscription-pro-max-team-or-enterprise-plans-why-do-i-have-to-pay-separately-to-use-the-claude-api-and-console>

**Supports:**

- *"Claude paid plans and the Claude Console are separate products designed for
  different purposes."*
- *"A paid Claude subscription enhances your chat experience but doesn't include
  access to the Claude API or Console."*
- *"If you're interested in both enhanced chat features and API access, you'll need
  to sign up for a paid Claude plan and separately set up Console access for API
  usage."*

**Does NOT support / NOT ADDRESSED:** how artifacts, MCP or connectors bill against
subscription versus API credits.

**Why this page matters here.** It is the independent confirmation of
`docs/mcp-capability-audit.md` §1: a scientist's artifact usage runs on that
scientist's **subscription**, and it buys ISAAC **no API access whatsoever**. An
ISAAC-side model would still need a separate Console credential — which is D3/D4/D5,
deferred.

---

## 3. The twelve questions

Confidence is about the *evidence*, not about the desirability of the answer.

| # | Question | Verdict | Confidence |
|---|---|---|---|
| 1 | Private Team artifact uses AI under each viewer's own subscription? | **SUPPORTED** | High |
| 2 | Can it call a configured custom remote MCP server? | **SUPPORTED** (**corrected 2026-09-01** — was *"NOT ADDRESSED for custom connectors specifically", Medium*; see §0/C1) | High |
| 3 | Does each scientist authenticate MCP independently? | **SUPPORTED** (stated twice, on two pages) | Very high |
| 4 | Can the artifact remain private to the organization? | **SUPPORTED** | Very high |
| 5 | Can a private org-shared artifact be embedded in an external domain? | **NOT ADDRESSED** | High |
| 6 | If embedding is supported, what requirements apply? | **SUPPORTED** only for *public* artifacts (Allowed domains); everything else **NOT ADDRESSED** | High |
| 7 | Can ISAAC safely deep-link to the private artifact? | **SUPPORTED** by the access model; the term "deep link" is **NOT ADDRESSED** | High |
| 8 | Can the artifact receive an Experiment ID via a supported link mechanism? | **NOT ADDRESSED** | High |
| 9 | What happens when MCP is disabled / disconnected / denied / expired? | **SUPPORTED** for disable, disconnect, deny and an org-level switch; **NOT ADDRESSED** for expiry and unreachability | Medium |
| 10 | What data, logs, prompts and storage are visible to whom? | **NOT ADDRESSED** except storage shape | High |
| 11 | Can artifact code and configuration be version-controlled in ISAAC? | **NOT ADDRESSED** by vendor; **SUPPORTED** as a measured repository fact | High |
| 12 | What is deterministically testable without a live MCP endpoint or real data? | Measured repository fact | High |

### 1. AI under each viewer's own subscription — SUPPORTED

*"Usage counts against each user's own Claude subscription limits, not yours"* and
*"When you share AI-powered artifacts within your organization, team members can
use them without incurring additional costs to the creator."* Viewer auth is
explicit: *"Users authenticate with their Claude account and interact with their
own instance of the artifact."*

**This directly refutes the assumption that artifact AI works without user auth.**
It does not. Each viewer authenticates, and each viewer pays from their own plan.

### 2. Calling a custom remote MCP server — SUPPORTED

> **CORRECTED 2026-09-01.** ~~*"The artifacts page states artifacts "can connect to
> external services through the Model Context Protocol (MCP)". Its three named
> examples — Asana, Google Calendar, Slack — are all first-party/verified
> connectors. The custom-connector page, which is the one that governs
> self-hosted, unverified servers like ISAAC's, never mentions artifacts at all. So:
> artifact→MCP is documented. Artifact→ISAAC's own custom remote MCP server is a
> reasonable reading of the same sentence but is not separately documented, and this
> document will not upgrade it to a certainty. It is the single most important item
> on the externally-unverifiable list in §7."*~~
>
> **The argument was wrong, and it was wrong about the same paragraph it quoted.**
> It is struck rather than deleted because it was the stated basis for the
> flagship entry in §7 and for a "never" paragraph in
> `apps/api/isaac_api/artifact_link.py`'s neighbourhood; a reader who met only a
> repaired version would not know a conclusion had moved.

The artifacts page names custom MCP servers **explicitly**, in the clause
immediately after the one about Asana, Google Calendar and Slack, in the same
paragraph:

> *"In addition to Anthropic's official MCP integrations, artifacts can connect to
> any **custom MCP servers** you've configured."*

Three things make this the strongest form of the answer rather than a bare
sentence. It **contrasts** custom servers with Anthropic's official integrations,
so the three named examples are identified by the page itself as the *other*
category rather than as the whole of it. It says **any**. And *custom MCP servers*
is a **hyperlink to article 11175166** — §2.3's page, the one that governs
self-hosted, unverified servers like ISAAC's. The two pages are joined by the
vendor, not by this document's inference.

**What is still not documented, stated narrowly so the correction is not
over-read:** the *client API* an artifact would use to make such a call (§7 item 2,
unchanged, and the reason the companion's seam is unset); and whether any specific
server — ISAAC's included — is reachable, which is D1 and is Dean's.

**Two constraints this answer arrives with**, both from the same section and
neither previously recorded:

- *"MCP integration for artifacts is available on Pro, Max, Team, and Enterprise
  plans on Claude web and desktop."* A scientist on **Free**, or on **mobile**, has
  no MCP path in an artifact at all. That is a real eligibility floor for the
  companion and belongs in front of anyone planning a rollout.
- *"Organization admins can enable or disable artifact MCP access at the
  organization level but cannot manage which specific MCP servers artifacts can
  use."* So the org-level control is **binary**: artifacts may use MCP, or they may
  not. An admin cannot permit ISAAC's connector to artifacts while withholding
  others. Anyone reasoning about SLAC governance should reason about that switch,
  not about a per-server allowlist that does not exist.

### 3. Independent authentication per scientist — SUPPORTED, twice

*"Each user must authenticate MCP servers independently, even when using shared or
published artifacts."* And, on the connectors page: *"Only Owners can add them to
Team and Enterprise plans. Once a connector has been added to a Team or Enterprise
organization, users individually connect to and enable that connector."*

**This refutes the assumption that artifact MCP access is org-wide without each
user connecting.** An Owner adding the connector makes it *available*; it does not
connect anybody. Every scientist performs an OAuth step nobody can perform for them.
This is a feature for ISAAC, not a friction: it is what makes each tool call
attributable to a person rather than to a shared service account.

### 4. Organization-private — SUPPORTED

*"Makes your artifact available within your organization only. Viewers must be
logged into your Team or Enterprise account to access it."* and *"Only members of
your Team or Enterprise organization."*

### 5. Embedding a private org-shared artifact — NOT ADDRESSED

See §4 below. This is the decision point.

### 6. Embedding requirements — public artifacts only

The only documented control is *"the **Allowed domains** field"*, and it appears in
the **"Embed artifacts"** section that follows **"Publish artifacts"**. **CSP,
`frame-ancestors`, X-Frame-Options, origin checks, token passing, cookie/SSO
behaviour inside a frame, and viewer authentication within an embed are all NOT
ADDRESSED.** A design that assumed any of them would be inventing an interface.

### 7. Deep-linking to the private artifact — SUPPORTED by the access model

A deep link is a URL. The access decision is made by claude.ai, which *"Viewers
must be logged into your Team or Enterprise account to access it"* describes: a
scientist who is not in the org gets nothing, whatever link they hold. So a link
from `isaac.slac.stanford.edu` leaks no data — it leaks, at most, the existence of
an artifact.

Two safety consequences ISAAC must honour, and does:

- The URL is **operator-supplied and disabled by default**
  (`apps/api/isaac_api/artifact_link.py`). No literal is committed.
- ISAAC must not present the link as though it were an in-app feature that will
  "just work" — a scientist who has not connected the MCP connector will land on a
  companion that can do nothing. The link needs the connector prerequisite stated
  beside it.

### 8. Passing an Experiment ID by link — NOT ADDRESSED

Neither artifacts page mentions URL parameters, query strings, launch payloads or
deep links carrying input. **The companion therefore asks the scientist to paste
the Experiment ID**, and says in the interface why: *"No supported mechanism for
passing an Experiment ID into an artifact by link is documented, so this companion
does not pretend to receive one."*

`artifact_link.py` **refuses** a configured URL carrying a query string or
fragment, precisely so nobody smuggles an ID into a shape whose behaviour nobody
has verified.

### 9. MCP unavailable — partially documented

| State | Documented? |
|---|---|
| First use of a tool in an artifact | **SUPPORTED** — *"you'll be prompted to approve access on first interaction"* |
| User denies / withholds approval | **SUPPORTED** by implication of the approval prompt |
| User disables a specific tool | **SUPPORTED** — *"disable any tools that aren't relevant to the current conversation"* |
| User disconnects / revokes | **SUPPORTED** — *"You can revoke these permissions at any time by disconnecting the connector"* |
| Owner removes the connector org-wide | **SUPPORTED** — *"Click 'Remove'…"* |
| Org admin turns artifact MCP off entirely | **SUPPORTED** (added 2026-09-01) — *"Organization admins can enable or disable artifact MCP access at the organization level but cannot manage which specific MCP servers artifacts can use."* A binary org switch, not a per-server allowlist |
| User is on **Free**, or on **mobile** | **SUPPORTED** as an eligibility floor (added 2026-09-01) — *"MCP integration for artifacts is available on Pro, Max, Team, and Enterprise plans on Claude web and desktop."* |
| Token **expired** | **NOT ADDRESSED** |
| Server unreachable / erroring | **NOT ADDRESSED** |

Because the last two are undocumented, the companion's behaviour contract
(`artifacts/isaac-assistant/artifact-prompt.md`) requires an honest refusal in
*all* of them and forbids answering from a cached or remembered state. That is the
same posture `CLAUDE.md` §11 records four separate honesty defects for not taking.

### 10. Data, logs, prompts, storage visibility — NOT ADDRESSED

What **is** documented is only the shape of artifact storage: *"20 MB storage limit
per artifact, Text-only input—no images, files, or binary data, Personal and shared
storage are isolated"*, and *"Artifact creators determine which data uses personal
versus shared storage when building the artifact."*

**Added 2026-09-01, and it settles the question for this companion by a route the
rule below never needed:**

> *"Persistent storage is only available for published artifacts. During
> development and testing, storage operations will not succeed until the artifact
> is published."*

The companion is **organization-shared, never published** (§4, and the operator
checklist's step 5). So it has **no persistent storage at all** — not storage that
must be used carefully, none. The rule below therefore has two independent bases:
the visibility one it always had, and now the plain fact that the capability is
absent. Do not let the second retire the first: if this companion were ever
published, the visibility argument is the only thing still standing, and it is the
one that decides.

Nothing documents what prompts, tool-call arguments, results or logs are retained,
for how long, or who may read them. One adjacent fact **is** documented, and it is
about the artifact rather than about storage: *"When you share an artifact, viewers
also gain access to any attachments and files in the conversation that created
it."* That makes the **conversation the artifact is created in** part of what gets
shared, which is an operator instruction, not a design one (§2.2, and the
checklist's **Never** list).

**Consequence, stated as a rule rather than a preference: no ISAAC scientific
record, evidence entry, file path, hash or draft value may be written to artifact
persistent storage.** This refutes the assumption that artifact persistent storage
is appropriate for scientific records. It is not — not because it is known to be
unsafe, but because its retention and visibility are undocumented, and
`CLAUDE.md` §8 and §6 do not permit "undocumented" as a basis for placing
experimental data somewhere. ISAAC's own durable store remains the record of truth;
the companion is a window onto it.

### 11. Version control — SUPPORTED as a repository fact

Done in this slice: `artifacts/isaac-assistant/` holds the page source, the
behaviour contract and the tool-permission manifest; `apps/api/isaac_api/artifact_link.py`
holds the disabled-by-default configuration; `apps/api/tests/test_assistant_artifact_companion.py`
holds the tests. The vendor documentation does not address round-tripping an
artifact back out of claude.ai, so the repository is the **source**, and a
published artifact is a **build output** — never the other way round.

### 12. What is deterministically testable today — measured

Without any MCP endpoint, network, credential or real datum:

- **This slice: 40 tests**, `apps/api/tests/test_assistant_artifact_companion.py`
  (**25 as first written; 40 after the 2026-09-01 review fixes** — measured with
  `pytest apps/api/tests/test_assistant_artifact_companion.py -q`, not counted by
  hand). They pin the companion's declared tool set to
  `policy.PERMITTED_TOOL_NAMES` exactly, pin each declared scope and mutation flag
  to the tool's own annotation, pin the forbidden-token list to the server's,
  assert the config is unconfigured by default and refuses **eight distinct
  reasons across eleven shapes** without echoing any of them (a ninth, *"it is not
  a parseable URL"*, is unreachable in practice and is marked `pragma: no cover`)
  — now including a malformed port, which used to
  escape as an uncaught `ValueError` **quoting the value back**, and a raw control
  character, which used to be *validated* stripped and *stored* intact — assert
  that an accepted value is stored in the normalised form that was validated,
  assert `embed_markup` raises, and assert the page carries no artifact URL, no
  token and no account identifier.

  **Two of them changed from assertions about the file's bytes into assertions
  about the page's behaviour**, because a review passed both a visible lowercase
  *"connected to your ISAAC workspace and ready"* claim and a `runCompanionTurn`
  that fabricated `{ ok: true, record: { status: "complete", pending: 0, qc:
  "valid" } }`. The `Connected` guard is now case-insensitive, requires a negation
  before every occurrence, and separately requires the disclosure to be **rendered
  first inside the live region**; and the seam is **executed** in a Node harness
  with a minimal DOM stub, which takes a turn and asserts the returned object — one
  unconditional structural test backstops an environment with no Node.
- **Existing MCP suite: 383 test functions** across **15** files (`test_mcp_*.py`
  plus `test_attack_mcp_token_confusion.py`), driving the **real** server
  in-process. *Corrected 2026-09-01. The file count was simply wrong — it has been
  15 throughout, at `ddec2b5` and at `f201e78`. The function count was right at
  `ddec2b5` (**382**) and moved to **383** when `test_mcp_server.py` gained a test
  in `f201e78`; both are stated with their vantage point rather than one replacing
  the other. Command:*
  `grep -hEc "^[[:space:]]*(async )?def test_" apps/api/tests/test_mcp_*.py apps/api/tests/test_attack_mcp_token_confusion.py`
- **`apps/web/src/__tests__/connect-your-agent.test.tsx`: 51 cases**, including
  *"states that no agent can submit, in its own section and in the boundary list"*.

What is **not** testable here: that a real Claude artifact can reach a real custom
remote MCP server. Nothing in this repository can establish that. See §7.

---

## 4. DECISION — deep link, not embed

> **ISAAC deep-links to an organization-private artifact. ISAAC does not embed it.**

### The single strongest piece of evidence

The publish-and-share page places **"Embed artifacts"** at section **4**, between
*"Who can access published artifacts"* (3) and *"Unpublish artifacts"* (5) — wholly
inside the **publishing** branch — and its instruction opens with the word
***"After publishing***, you'll see a 'Get embed code' button." The
**organization-sharing** branch is sections **7–10** and contains **no embedding
instruction of any kind**.

Embedding is documented as a property of a **published (public)** artifact. It is
not documented as a property of a **shared (organization-private)** one.

### Why that settles it rather than merely leaving it open

> **CORRECTED 2026-09-01 — this subsection reasoned from an authorization where the
> same page states an availability.** The old closing sentence read: ~~*"So the
> choice is not 'embed vs. deep link, pick one'. It is 'deep link, or take an
> unauthorized publishing decision'. Deep link."*~~ That frames publishing as
> **offered and merely forbidden**. For the artifact this project would create it is
> **not offered**. The decision is unchanged and its basis is stronger; the old
> sentence is kept struck because a reader who thought the alternative existed
> would look for who could authorize it.

The only documented route to an embeddable artifact is to publish it publicly —
*"Anyone with the link can view and interact with it"*, and *"Non-users: View and
interact with any published artifact without signing up."*

**And that route does not exist on the account this companion would live on:**

> *"Artifacts created on Team or Enterprise accounts can only be shared within your
> organization—they cannot be published publicly."*
>
> *"Publishing is available on Free, Pro, and Max plans."*

So for an artifact created in a SLAC Team organization, the publish branch — and
therefore the **"Embed artifacts"** section that hangs off it — is unreachable.
Embedding is not a decision this project declines to take. It is a capability the
vendor does not offer for the artifact in question.

**The unauthorized decision the old sentence imagined is real, but it lives on a
different branch, and naming it is what keeps the correction from reading as a
loophole.** A Free, Pro or Max **personal** account *can* publish publicly and
therefore *can* embed. Building the companion there instead would:

- **destroy the property §3 Q4 establishes** — the artifact would no longer be
  organization-private, and *"Non-users: View and interact … without signing up"*
  would become its access model;
- be a visibility decision **no agent may take** (`CLAUDE.md` §15 reserves those to
  their owners, and gate **G2** holds closed by default for far less); and
- put an ISAAC surface on a public URL while Dean's **D1** — *whether the MCP path
  may be internet-reachable at all* — is **deferred**.

So the corrected form: **on the Team account, embedding is not available; off it,
embedding costs the organization-private property that was the whole requirement,
and requires a decision nobody has taken. Deep link.**

### Exactly what would unblock embedding

One vendor capability, and only one:

> **Anthropic documenting an embed flow for organization-shared (non-public)
> artifacts** — i.e. a `Get embed code` equivalent appearing under *"Share artifacts
> within your organization"*, **together with** a documented statement of how a
> viewer of the embedded frame authenticates to the Team/Enterprise organization
> (frame-ancestors / cross-origin / SSO behaviour), since §2.2 currently addresses
> neither.

**Sharpened 2026-09-01 by the correction above:** the change must land in the
**sharing** branch specifically. A change that only widened *publishing* would not
help, because a Team/Enterprise artifact cannot be published at all.

Both halves are required. An embed code without a documented in-frame
authentication story would leave ISAAC guessing at exactly the security boundary it
must not guess at.

Until then `artifact_link.embed_markup()` **raises**, and the raise carries this
reason. It is a refusal, not a gap.

---

## 5. The ISAAC side, as measured

Measured at `ddec2b5` by importing the modules, not by reading comments, and
**re-verified 2026-09-01 at `f201e78`** (this branch's rebase base). Only
`apps/api/tests/test_mcp_server.py` differs between the two commits — `policy.py`,
`tools.py`, `routes.py` and `proposals.py` are byte-identical — so every line
citation below still resolves, and the one figure that moved is called out in §5.5.

### 5.1 The MCP tool inventory — 10 tools, 2 scopes

| Tool | Scope | Mutates | What it does |
|---|---|---|---|
| `isaac_list_experiments` | `isaac:read` | no | List records |
| `isaac_get_experiment` | `isaac:read` | no | Read one record |
| `isaac_list_runs` | `isaac:read` | no | List a record's runs |
| `isaac_get_run` | `isaac:read` | no | Read one run |
| `isaac_list_questions` | `isaac:read` | no | List blocking questions |
| `isaac_inspect_evidence` | `isaac:read` | no | Inspect a record's evidence |
| `isaac_check_run` | `isaac:read` | no | Check a run (POST, but reads) |
| `isaac_create_run` | `isaac:draft.write` | yes | Add a run to a record |
| `isaac_update_draft` | `isaac:draft.write` | yes | Write draft values |
| `isaac_answer_questions` | `isaac:draft.write` | yes | Answer blocking questions |

**Seven reads, three writes.** Every write touches **draft content only** and
requires an `If-Match` precondition — and `client._render_headers` refuses
`If-Match: *`, a wildcard the HTTP API itself accepts, because this layer's caller
is a language model rather than a person.

`Scope` has exactly two members: `isaac:read` and `isaac:draft.write`. They
deliberately **do not nest** — `DRAFT_WRITE` does not imply `READ`.

### 5.2 What the policy refuses

Four independent structures, any one of which alone stops a finalisation tool
(`policy.py` module docstring):

1. **`Scope` has no `SUBMIT` member.** `parse_scope("isaac:submit")` returns
   `None`. The permission is not a string that can be typed.
2. **`OPERATIONS` is a closed table of 13 `(method, path)` pairs.** The client binds
   an operation *id*; it cannot construct a path.
3. **`ALLOWED_METHODS` = `{GET, POST, PATCH}`.** No `DELETE`, no `PUT`.
4. **`PERMITTED_TOOL_NAMES` (10) is closed, and two token sets are checked at
   import.**

**`FORBIDDEN_TOOL_TOKENS` — 21 destructive/finalising verbs**, refused in a tool
name at import time:

`accept · approve · delete · destroy · discard · drop · export · finalis ·
finaliz · governance · grant · migrat · publish · purge · remove · reset ·
revoke · sign_off · signoff · submit · truncate`

**`FORBIDDEN_PATH_TOKENS` — 15**, refused in an allowlisted route path:

`database · delete · demo · destroy · discard · drop · export · migrat · purge ·
remove · reset · submit · tutorial/sessions · uploads · verification`

The two sets are **deliberately not equal** and must not be made equal; what is
asserted is the narrower checkable property that **every destructive verb appears
in both**.

Note `accept` is in the tool set specifically because ISAAC's conflict-resolution
vocabulary is *accept a proposal*, so `isaac_accept_proposal` is an `ImportError`
rather than a review miss.

### 5.3 Proposals — an MCP client cannot create one

- Creation route exists: **`POST /api/experiments/{experiment_id}/proposals`**
  (`apps/api/isaac_api/routes.py:12568`, handler `:12643`).
- Review route: **`POST .../proposals/{proposal_id}/review`** (`routes.py:13215`),
  actions **`accept`, `reject`, `supersede`, `withdraw`** (`proposals.py:254-274`).
  There is **no `defer` action and no defer route** — a correction worth recording,
  because the feature is often described as having one.
- **No proposal route is in `OPERATIONS`.** The only occurrences of "proposal"
  anywhere under `apps/api/isaac_api/mcp/` are two *prose comments* at
  `policy.py:118` and `:120`.

Pinned by `test_DEC7_no_mcp_operation_or_tool_reaches_a_proposal_route`
(`apps/api/tests/test_ingestion_proposals.py:1496`).

**One honest sharp edge:** `accept` is a forbidden token, but **`propose` and
`proposal` are not**. A hypothetical `isaac_propose_value` tool would pass the token
check and be stopped only by the closed `PERMITTED_TOOL_NAMES` set — one structure
rather than two. Worth knowing before anyone designs a proposal-creating tool.

### 5.4 Submit — MCP cannot reach it, by four layers and ten tests

- The route exists: **`POST /api/experiments/{experiment_id}/submit`**
  (`routes.py:16305`, handler `:16382`), gated by
  `require_human_actor("submit")`.
- Sibling finalisation: `POST /api/experiments/{experiment_id}/export`
  (`routes.py:15574`).
- Both `submit` and `export` are in **both** token sets; neither path is in
  `OPERATIONS`; no scope reaches them.

Named tests, among others: `test_registering_a_submit_tool_raises_rather_than_being_ignored`
(`test_mcp_boundaries.py:126`), `test_no_mcp_scope_can_reach_an_accepting_finalising_or_exporting_operation`
(`:228`), `test_a_scope_named_submit_cannot_be_expressed_at_all` (`:288`),
`test_the_mounted_surface_cannot_reach_a_submit_or_export_path`
(`test_mcp_transport.py:1117`, with a non-vacuity assertion that `/export` really
is in the app's route table), and
`test_no_mcp_authenticated_caller_has_a_tool_to_accept_or_submit_with`
(`test_mcp_oauth_binding.py:1184`, driving a real `tools/list` with a live bearer
token).

This satisfies `docs/ai-integration-decision-packet.md` §6.2: *"External agents
cannot submit. No MCP tool exposes it, ever."*

### 5.5 What deterministic fakes exist — and one correction

**There is no fake or in-memory MCP client, and no fake MCP transport.** The MCP
tests drive the **real** stack: the production `AsgiApiClient` over
`httpx.ASGITransport` against the real FastAPI app in-process, plus
`fastapi.testclient.TestClient` for the JSON-RPC layer. `LocalLoopbackDeployment`
is **production code**, not a test double.

The deterministic fakes that *do* exist stand in for the **authorization server**,
not for ISAAC:

| Fake | Stands in for |
|---|---|
| `apps/api/tests/mcp_oauth_keys.py` (`SEED = 20260829`, `SyntheticKey`, `jwks()`, `sign()`) | The OAuth AS / JWKS signer. *"This module signs. The application never does."* |
| `fake_fetch` / `angry_fetch` (`test_mcp_oauth_never_leaks_a_token.py:480`, `:512`) | The `oauth.JWKS_FETCHER` network seam — no socket is opened |
| `_explode` (`test_mcp_server.py:200`) | A broken HTTP client, to prove the JSON-RPC loop leaks nothing |

*Three line citations corrected 2026-09-01: each was one greater than the line the
`def` is actually on (481→480, 513→512, 201→200). Re-derive rather than trusting
the numbers — `grep -n "def fake_fetch\|def angry_fetch" apps/api/tests/test_mcp_oauth_never_leaks_a_token.py`
and `grep -n "def _explode" apps/api/tests/test_mcp_server.py`.*

So the honest statement is: **ISAAC can already test its MCP server end-to-end with
no network and no credential.** What it cannot test is the *Claude client* half.

---

## 6. What this slice built, and what it deliberately did not

**Built:** `artifacts/isaac-assistant/` (page source, behaviour contract,
tool-permission manifest generated from `policy.py`);
`apps/api/isaac_api/artifact_link.py` (disabled-by-default operator configuration,
embedding refused); `apps/api/tests/test_assistant_artifact_companion.py` (**40**
tests — 25 as first written, see §3.12).

**EXTENDED 2026-09-01.** An independent audit measured that `artifact_link.py` was
**dead code**: `rg -an 'artifact_link'` over the repository (excluding `.md`)
returned only the module and its own test, so no route registered it and no
frontend referenced it — the architecture this document describes had no entry
point. A later slice gave it one: `GET /api/runtime/assistant-companion`
(three states, all 200, `unconfigured` by default), a Settings surface beside
Connect Your Agent, `apps/api/tests/test_assistant_artifact_companion_route.py`
(**59** tests) and `apps/web/src/__tests__/assistant-companion.test.tsx` (**44**).
`artifact_link.py` itself is UNCHANGED — it needed a consumer, not a rewrite.

**Deliberately not built:**

- **The companion's model/MCP call surface.** No vendor documentation defines a
  client API for AI-powered or MCP-calling artifacts (§2.1). `runCompanionTurn` is
  a single marked seam that fails closed and says nothing was sent. Writing the
  call from recall is what `CLAUDE.md` §5 forbids.
- ~~**Any route wiring.** `artifact_link.py` is not mounted anywhere.
  `apps/api/isaac_api/routes.py` was not touched.~~ — **BOTH CLAUSES SUPERSEDED
  2026-09-01, and struck rather than deleted because they were TRUE when written
  and a reader must see that they expired rather than drifted.** The module is
  now mounted at `GET /api/runtime/assistant-companion` and `routes.py` carries
  one new section plus one import. What has NOT changed is the decision this
  entry was protecting: the route serves a **deep link and never an embed**,
  `embed_markup` still always raises, and nothing was published.
- **Any published artifact.** Nothing was published, made public, or shared.
- **Any voice or transcript integration.** §2.4 supports none of the three
  assumptions that would be needed.

---

## 7. Externally unverifiable from this environment

Named rather than implied, because a silent gap reads as a solved one — and,
per §0/C1, because a **manufactured** gap reads exactly like a measured one.

1. ~~**That a Claude artifact can call a *custom* (self-hosted, unverified) remote
   MCP server.** The artifacts page documents artifact→MCP with first-party
   examples; the custom-connector page never mentions artifacts. This is the
   load-bearing gap.~~
   **STRUCK 2026-09-01 — THIS WAS NEVER A GAP, AND IT IS STRUCK RATHER THAN
   DELETED BECAUSE IT HEADED THIS LIST AND WAS CALLED LOAD-BEARING.** The artifacts
   page states it directly, in the clause after the one this document quoted:
   *"In addition to Anthropic's official MCP integrations, artifacts can connect to
   any **custom MCP servers** you've configured."* — and links to the
   custom-connector page from those words. See §0/C1 and the corrected §3.2. The
   list below is therefore **seven** live items, numbered 2–8 as before so that
   nothing cites a renumbered entry.
2. **The client API for AI-powered and MCP-calling artifacts.** Undocumented on
   every page fetched, and **re-confirmed absent on the 2026-09-01 re-read of both
   artifact pages** — the MCP and AI-powered sections describe capability,
   eligibility, approval and billing, and name no interface. This is now the
   load-bearing gap, and it is the one that keeps the companion's seam unset.
3. **Whether SLAC has a Claude Team or Enterprise organization at all**, and
   whether Krish or anyone else holds Owner rights in it. Nothing in this
   repository witnesses it.
4. **What is retained or visible** — prompts, tool arguments, results, logs — to
   creators, org members, or Anthropic.
5. **Failure semantics for an expired or unreachable connector.**
6. **Whether an org-shared artifact can ever be embedded.** Undocumented today —
   and, per §0/C2, a Team/Enterprise artifact **cannot be published at all**, so
   the publish-branch embed flow is unreachable rather than merely undocumented.
   §4 states exactly what would change that, and that it must change in the
   *sharing* branch.
7. **Everything Dean deferred (D1–D9)**, unchanged: MCP internet reachability, the
   auth model, provider, credential, billing, egress, retention, data policy,
   transcription provider.
8. **Every hosted QA.** `/krish` sits behind an Authentik edge this environment
   cannot authenticate to.
