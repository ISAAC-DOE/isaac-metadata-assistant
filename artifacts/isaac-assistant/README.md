# ISAAC Assistant artifact companion — repository source

This directory holds the **source** of a Claude Artifact companion for the ISAAC
Metadata Assistant. Nothing here is published, and publishing it is not an agent's
act — see `docs/isaac-assistant-artifact-operator-checklist.md`.

## What this is, stated narrowly

A scientist's own Claude, in a Team-shared artifact, calls ISAAC's existing MCP
tools on that scientist's behalf. That is the **only** capability in scope. It does
not give ISAAC inference, a model, a credential, or a billing relationship
(`docs/mcp-capability-audit.md` §1: *"MCP is one-way. A Claude client calls ISAAC's
tools. ISAAC cannot call a Claude model."*).

## Files

| File | What it is |
|---|---|
| `tool-permission-manifest.json` | The exact tools the companion may call, generated from `apps/api/isaac_api/mcp/policy.py`. A declaration, not an enforcement point. |
| `artifact-prompt.md` | The companion's instructions — the behaviour contract, including its refusal paths. |
| `index.html` | The companion's page source. Its model/MCP call surface is a **declared, unimplemented seam** — see below. |

## The seam is deliberately unimplemented, and that is a finding, not an omission

`index.html` contains no call into any Claude artifact runtime API. The vendor
documentation verified on 2026-08-31
(`docs/isaac-assistant-artifact-feasibility.md` §2) states that artifacts *can*
embed AI capabilities and *can* call MCP, but **documents no JavaScript API surface
for either**. Writing one from recall would be inventing an interface, which
`CLAUDE.md` §5 forbids for exactly the reason it matters here: a wrong guess fails
in the operator's hands, not in CI.

So the seam is marked, tested for honesty, and left unset — the same posture
`apps/api/isaac_api/mcp/deployment.py` takes with `UnconfiguredDeployment`, and the
same one the assistant and transcription providers take with
`501 no_provider_configured`. Closing it needs one externally-verifiable fact: the
vendor-documented client API for AI-powered and MCP-calling artifacts.

## What this companion may never do

Submit, export, finalise, delete, discard, apply a migration, or change governance.
Those are refused server-side by non-implementation (`policy.py`'s four independent
structures) and re-declared in `tool-permission-manifest.json` so that a
well-meaning future edit is a failing test rather than a production discovery.
