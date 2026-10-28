# ORCID account linking: design (not activated)

*Status: **DESIGN ONLY, 2026-10-28.** Nothing is implemented or enabled. Production identity
changes need Krish's approval, Dean's sign-off and a security review. This design keeps
`docs/identity-trust-contract.md` §9.1: ORCID is scientific-credit metadata and **must never confer
authorization**.*

## 1. Four identities that must stay separate

| | What it is | Who establishes it | What it may do |
|---|---|---|---|
| **Researcher identity** | an ORCID iD (`0000-000X-XXXX-XXXX`) | ORCID, via a verified link (§3) | credit: `attribution.contributors[].orcid` |
| **Account authentication** | the Authentik username (the compatibility key, §9.1) | the SLAC login, proven to ISAAC by a trusted boundary | authorize requests |
| **Connector activity** | an MCP OAuth token's `sub` → `ServicePrincipal` | the OAuth resource server (`mcp/jwt.py`) | transfer drafts and suggestions; never approve |
| **Scientific approval event** | one deliberate act by one authenticated human on one value | the browser path with a verified edge assertion | accept or correct a value |

ORCID on a record proves nothing about who approved a value. A login *through* ORCID proves nothing
to the backend unless the request crossed a trusted boundary. Today it did not: there is a
ClusterIP side door, and `identity._VERIFIERS` holds only `unconfigured` and `test_fixture`.

## 2. Prerequisite

Linking is meaningful only once ISAAC can verify the account (the browser identity boundary):
- a signed edge assertion checked by an `EdgeTrustVerifier`, minting
  `TRUST_BASIS_VERIFIED_EDGE_ASSERTION`; or
- a NetworkPolicy plus the header verifier.

Until then a link could be forged through the side door, so **no link is stored**.

## 3. Linking flow (preferred order)

**Option A: the claim comes from the identity provider.**
- If the person signed in through Authentik's ORCID source, Authentik already holds the verified
  ORCID connection. Hao is asked whether the signed edge assertion can carry it, as a custom claim
  such as `orcid`.
- ISAAC then stores `(authentik_username → orcid_id, verified_via: idp_source, linked_at)`.
- No new outbound network path from the pod. **Preferred.**

**Option B: ISAAC runs ORCID OAuth.**
- An authenticated user starts "Link ORCID". ISAAC redirects to ORCID's `/oauth/authorize` with
  scope `/authenticate`, PKCE and `state`, and takes the iD from the token response.
- It needs an ORCID client registration and outbound HTTPS from the pod to orcid.org, which is an
  egress decision for Dean.
- ISAAC stores the iD only. The ORCID access token is discarded at once and never stored.

**Never:** an ORCID typed into a form, read from a bundle, or read from `contributors[]` becomes a
link. Those stay unverified credit metadata (`test_orcid_in_body_confers_no_rights` precedent).

## 4. Rules

- **One-to-one.** One account links at most one ORCID, and one ORCID links to at most one account.
- **Conflict.** Linking an ORCID already linked elsewhere is refused (409 `orcid_already_linked`),
  and the new link is not stored. An operator resolves it by identity proofing, outside the app.
  Nothing is auto-moved.
- **Unlinking.** The account owner can unlink. Activity records `orcid_unlinked`. Past attribution
  rows keep the iD they were written with, because history is append-only. New records no longer
  get it suggested.
- **Revocation.** If ORCID access is revoked or the iD is deactivated, ISAAC cannot see it without
  calling ORCID. With option A it learns through the next edge assertion that lacks the claim, and
  marks the link `stale`. With option B it re-verifies on a schedule only if egress is approved.
  ISAAC never claims a link is current beyond its last verification time.
- **Account lifecycle.** Username reassignment is open question **Q5**. If a username is reassigned,
  its link must be cleared by an operator before reuse. Documented, not automated.
- **Use.**
  - A linked ORCID may be **suggested** into `attribution.contributors[].orcid` when that person
    adds themselves as a contributor. Adding it is still the person's explicit choice.
  - It is never added to someone else's contributor entry.
  - It never appears in an authorization check.
- **Activity.**
  - `orcid_linked` / `orcid_unlinked` / `orcid_link_stale` are account events.
  - Approval events record the **username** (the authorization principal), with the ORCID shown for
    display only.

## 5. What it would take

1. The browser identity boundary (Hao + Krish).
2. Hao answers whether Authentik can forward the ORCID claim (option A).
3. A storage decision: a new table means a migration and an approval packet, so the `DEC-49`
   precedent applies.
4. Security review.
5. Tests:
   - a link is refused without a verified edge assertion;
   - a body-supplied ORCID is ignored;
   - duplicate link → 409;
   - unlink keeps history;
   - a stale claim marks the link stale;
   - ORCID never appears in an authorization decision.
