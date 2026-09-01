# Operator checklist — ISAAC Assistant artifact companion

**Every step below is external to this repository and cannot be performed by an
agent.** Each requires a human acting in a console an agent has no account in, or
taking a decision an agent has no authority to take.

**Do not start.** This checklist is the *specification* of what would be required.
Steps 1–3 are blocked on Dean's **D1/D2**, deferred 2026-08-12 and still deferred.

Evidence for every vendor claim: `docs/isaac-assistant-artifact-feasibility.md`
(verified 2026-08-31).

---

## Prerequisites — decisions, not actions

| # | Decision | Owner | Status |
|---|---|---|---|
| P1 | May the ISAAC MCP path be internet-reachable? | Dean / SLAC infra | **DEFERRED** (D1) |
| P2 | Which auth model on that path — hosted OAuth AS vs. edge-accepted token? | Dean / SLAC infra | **DEFERRED** (D2) |
| P3 | Does SLAC have a Claude **Team or Enterprise** organization, and who is Owner? | Krish | **UNKNOWN** — no artifact in this repository witnesses it |

**If P1 or P2 is unresolved, stop here.** Nothing below is safe to do.

---

## Steps

**1. Confirm the plan tier — and read both directions of the sentence.** Custom
connectors on a Team/Enterprise org can be added *only* by an Owner.
Organization-private artifact sharing requires Team or Enterprise: *"Internal
sharing is available on Team and Enterprise plans."*

**Corrected 2026-09-01.** This step already said *"A Pro or Max account can publish
**publicly only**"*, and the other half of that same sentence was never carried
into feasibility §4, which then argued as though publishing were available and
merely unauthorized. It is not available:

> *"Artifacts created on Team or Enterprise accounts can only be shared within your
> organization—they cannot be published publicly."*
> *"Publishing is available on Free, Pro, and Max plans."*

So on the SLAC Team org there is nothing to decline: `Publish` is not offered, and
neither is the `Get embed code` flow that hangs off it (feasibility §0/C2 and §4).

**Also confirm the plan and platform floor for MCP itself**, which is narrower than
the sharing floor and was not previously recorded: *"MCP integration for artifacts
is available on Pro, Max, Team, and Enterprise plans on Claude web and desktop."*
A scientist on **Free**, or working on **mobile**, has no artifact→MCP path at all.

**And know what the org-level switch is**, because it is not what an admin might
expect: *"Organization admins can enable or disable artifact MCP access at the
organization level but cannot manage which specific MCP servers artifacts can
use."* It is binary — artifacts may use MCP, or they may not. There is no
per-server allowlist to configure.

**2. Add the ISAAC remote MCP server as a custom connector — Team Owner only.**
Settings → Connectors → Add custom connector → the ISAAC MCP server URL, plus
OAuth Client ID/Secret if P2 lands on OAuth.
*Adding it makes it available. It connects nobody.*

**3. Each scientist connects it themselves.** Every user opens their own Claude
settings, enables the connector, and completes the OAuth grant. **No Owner, admin
or agent can do this for them**, and there is no org-wide bypass.

**4. Create the artifact from `artifacts/isaac-assistant/index.html`** and its
behaviour contract `artifact-prompt.md`. The repository is the source; the
published artifact is a build output. Never edit the artifact in place and leave
the repository behind.

*Create it in a conversation that contains nothing you would not share with the
whole organization:* *"When you share an artifact, viewers also gain access to any
attachments and files in the conversation that created it."* (Added 2026-09-01 from
the same re-fetch; feasibility §2.2.)

**5. Share it to the organization — `Share`, never `Publish`.**
`Share` = organization-only, viewers must be logged into the Team/Enterprise
account. `Publish` = public, anyone with the link, no sign-up.
**Publishing this artifact is out of scope and no agent may do it.**
*On a Team or Enterprise org `Publish` is not offered at all (step 1), so this
warning is not describing a button you must resist. It binds the case where someone
creates the companion on a personal Free/Pro/Max account instead — which is where
the publish button exists, and which forfeits the organization-private property
that was the requirement.*

**6. Approve the MCP tools on first use.** Each scientist gets an approval prompt
the first time the artifact reaches a tool. Grant only the ISAAC tools. Treat
`Allow always` as a decision, not a dismissal.

**7. Give the artifact URL to ISAAC as configuration — never as a commit.**
Set `ISAAC_ASSISTANT_ARTIFACT_URL` in the deployment environment. It must be
`https`, on `claude.ai`, with a path and **no query string or fragment**;
anything else is refused with a reason that does not echo the value.
Unset is the default and is a working state.

**8. Verify, and record what you actually observed.** With one scientist who has
*not* connected the connector, confirm the companion refuses honestly rather than
appearing to work. Then with one who has. Report both.

---

## Never

- **Never `Publish`** this artifact publicly.
- **Never embed** it in `isaac.slac.stanford.edu`. Embedding is documented only for
  publicly published artifacts; ISAAC deep-links instead (feasibility §4).
- **Never commit the artifact URL**, a token, an OAuth secret, or an account
  identifier. Step 7 is the only supported route.
- **Never put a scientific record, evidence entry, file path or hash into artifact
  persistent storage.** Its retention and visibility are undocumented (feasibility
  §3 Q10). Note also, added 2026-09-01: an organization-**shared** artifact has no
  persistent storage to misuse — *"Persistent storage is only available for
  published artifacts"* — so the rule binds a future published version, and that is
  exactly when the visibility argument is the only one left standing.
- **Never create the artifact in a conversation carrying sensitive attachments.**
  Sharing the artifact shares them (step 4).
- **Never present the companion as able to submit or export.** It cannot, by four
  independent structures in `policy.py`, and saying otherwise is a false claim
  about a governance boundary.
