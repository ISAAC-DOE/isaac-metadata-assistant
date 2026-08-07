# Slack message to Dean — DRAFT, NOT SENT

**Status: NOT SENT.** No approved workflow permits agent-to-Dean communication. This is drafted for
Krish to send, edit, or discard. Evidence behind every claim:
[`portal-identity-and-metrics-audit.md`](portal-identity-and-metrics-audit.md).

---

Hi Dean — four things on the metadata assistant, roughly in order of how much they block us.

**1. `attribution.uploaded_by` — which identifier?**

Your schema note (2026-06-15) says `uploaded_by` is server-stamped from the authenticated identity,
client values overwritten. The portal does exactly that in `save_record`. The metadata assistant did
**not** — it copied the draft's attribution block through, so a hand-authored `uploaded_by` reached
an exported record and passed schema validation. We've made it fail closed (refused at draft
validation) rather than guess a value, so nothing is stamped and nothing will be until you answer.

Which string counts as "the authenticated identity" — Authentik **UID**, Authentik **username**, an
ORCID subject, or something else? The portal keys ownership and ACLs on the username, so that's the
compatibility answer, but it means a rename at the IdP silently transfers record ownership. Is the
username non-reassignable across rename/departure/rehire? Is `X-authentik-uid` stable and permanent?

**2. Can an in-cluster caller reach our Service without passing Authentik?**

This one gates everything else. If yes, forwarded `X-authentik-*` headers can't be trusted for
anything, and we won't build ownership, roles, or per-user stats on them.

Related: on the `/krish` path we observed a client-supplied value in one of the headers `/portal`'s
identity check depends on arrive **untouched**, which suggests the two paths don't get the same
header treatment. Our deployment doc claims `/krish` runs on the same `isaac-portal` Authentik
application policy — is that actually true? (Specifics of what that implies for `/portal`'s own
configuration are deliberately kept out of this public file; ask privately.)

**3. Portal usage metrics — may we consume them, and how much may we show?**

We traced the dashboard numbers to `api_requests` and `portal_access_log` (the portal's own tables,
written by its `after_request` hook — not GitHub PR data, which we'd previously assumed).

- May `/krish` call `GET /portal/api/usage/summary`, or should we instrument our own requests?
- Which aggregates are OK for an ordinary signed-in user vs admin-only?
- Any minimum aggregation threshold you want enforced? Neither app has one today.
- May a signed-in user see *their own* API activity?

**4. One thing to look at in the portal, privately**

> **Redacted for public release.** This item is a missing-authorization finding in the portal: a
> surface renders personal data that the portal's own code marks administrator-only. **The
> component and the specifics are withheld from this public repository** — it is another team's
> live system, the finding was not fixed by us, and publishing it would disclose an unremediated
> vulnerability in infrastructure we do not own.
>
> **Krish: send this item to Dean privately (Slack/DM), not through this file.** Do not re-add the
> specifics here, and do not restate them in a PR title, commit message, or issue.

How exposed it is depends on the ingress, so we did not test it against the deployment.

**Still open from before:** Q19 (may the deployed backend read the 30 records in memory only, mutate
copies, and return aggregate pass/fail with no values or writes?) and Q20 (should we arm `format`
enforcement in the validator?). Both still block work that's otherwise ready.

No rush on 3 and 4 — 1 and 2 are the blockers.

---

## Gate → answer mapping

| Dean's answer | Unblocks |
|---|---|
| Which identifier is "the authenticated identity" (Q21 / sharpens Q10) | Server-stamping `uploaded_by`; record ownership |
| Username non-reassignable? (Q5) / UID permanent? (Q17) | Choosing the canonical internal key; any ACL row |
| In-cluster bypass possible? (Q4) | **Everything** identity-derived: current-user context, ownership, roles, My Stats |
| Same Authentik application for `/portal` and `/krish`? (Q22) | Whether portal header evidence transfers to `/krish` |
| May `/krish` consume `usage/summary`? (Q23) | General ISAAC usage metrics — otherwise instrument ourselves, which needs durable persistence |
| Which aggregates for ordinary users? Min cell size? (Q23) | General ISAAC card set; also settles **G3** |
| Personal API activity visible to its owner? (Q24) | A bounded "My API Activity" section in My Stats |
| Q19 | The private-corpus mutation runner |
| Q20 | `format` enforcement |
| G2 / G6 | Any real-record display, and whether personal data is covered separately |

## What does NOT need Dean

Stated so the list above is not read as blocking more than it does. The `uploaded_by` refusal is
already shipped and needed no authorization — it removes a false claim rather than adding a
capability. ISAAC-side request instrumentation (Q23's fallback) is an application-owned design, though
it needs durable storage and so waits on Phase 37 regardless.
