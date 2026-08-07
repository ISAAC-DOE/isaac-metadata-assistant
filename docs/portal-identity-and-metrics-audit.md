# Portal Identity & Metrics Audit — ISAAC-binding conclusions only

**Audit performed:** 2026-08-03 · **Status:** EVIDENCE — conclusions only. Nothing here authorizes an
implementation, and no identity or metrics wiring was added.

---

## 0. What this file is, and what it is not

An audit was carried out on 2026-08-03 to decide one question: **what, if anything, may `/krish`
reuse from the adjacent portal application for identity and for usage statistics?** It was a
read-only reading of published source. No authenticated request was made against any deployment, no
cookie or credential was handled, and no identity value, record content, or network address appears
here.

**The audit's findings about weaknesses in that third-party system are not recorded here.** That
application is operated by another team; it is not ours to deploy, change, or fix, and this
repository is public — so where an observation would describe a missing, absent, or degradable
control in a system this project does not own, it is raised with that system's owners directly
rather than written down.

**Read that as the narrow claim it is, because a broader one would be false.** This file is not a
repository-wide guarantee. Other documents in this repository — `identity-trust-contract.md` §5 and
the planning documents under `docs/superpowers/plans/` among them — do describe that system's
*design*: tables it has, routes it exposes, rules it enforces, defaults it applies. Those are
**positive** properties, several of them published by their own owners in this repository, and
describing a control that exists is not the same act as publishing one that is missing. The line
drawn here is between the two, not between "mentioned" and "unmentioned".

An earlier revision of this section claimed the broader form — that no operational detail about that
system appears *anywhere in this repository*. That was false when written, and it is recorded rather
than quietly narrowed, because a withholding notice a reader can falsify is worse than none: it
tells a future session there is nothing to look for.

What this file does keep is the set of conclusions that bind **ISAAC's own** engineering: the rules
a future session must not silently reverse, and the open questions ISAAC still needs answered.

Two consequences of that boundary, stated plainly so nothing here is read as more than it is:

- This file is **not** a complete record of the audit, and does not claim to be. It is the
  ISAAC-binding residue of one.
- Nothing in this file is a statement about the security posture of any system other than ISAAC.

---

## 1. Conclusions that bind ISAAC

These five are load-bearing. They are the reason the audit was worth doing, and each of them
constrains what ISAAC may build.

### 1.1 A forwarded identity header is not evidence of authentication

A username that reaches an application as a request header, and is rendered back into a page, is a
**string being displayed** — not proof that the subject was authenticated, and not proof of the path
the request travelled. ISAAC must not build ownership, roles, or per-user statistics on a forwarded
header. See [`identity-trust-contract.md`](identity-trust-contract.md) §6A, which records precisely
what ISAAC's own probe did and did not establish.

### 1.2 `X-authentik-entitlements` and `X-Isaac-Edge` are permanently disqualified

Neither header may be used for **authentication, authorization, role assignment, proof that an
authenticating edge was traversed, or proof that the caller is an institutional user** — unless the
infrastructure changes and the headers are independently re-verified. `X-Isaac-Edge` in particular
cannot witness edge traversal, which is the one job its name implies. This restates
[`identity-trust-contract.md`](identity-trust-contract.md) §6A and CLAUDE.md §15; it is not a new
allowance and does not soften either.

### 1.3 ISAAC must not ingest the portal's per-user or per-source-address metrics

Aggregates broken down by individual user, or by client network address, carry **other people's
identifiers and other people's network addresses** — foreign personal data that ISAAC has no
authorization to hold, store, or display. This conclusion stands on its own: it does not depend on
any observation about how the other application is built or configured.

### 1.4 Instrument ISAAC; do not siphon the portal

The honest route to a usage chart in ISAAC is **ISAAC's own request logging over ISAAC's own tables,
importing no foreign PII.** Copy the pattern, never the data. This needs durable storage, and ISAAC
reports `persistence: "ephemeral"`, so it is a Phase-37 item and is **not authorized now**.

### 1.5 There is no reusable upstream identity contract

There is **no endpoint to consult** — nothing ISAAC could call to ask who a user is, what groups they
belong to, or whether a session is valid. What looked like an identity contract is not one, so there
is nothing to reuse. Any ISAAC identity behaviour must therefore be justified on ISAAC's own
evidence, not inherited.

---

## 2. Reuse verdict for `/krish`

| Contract | Reusable? |
|---|---|
| **Identity** | **No.** No endpoint exists to consult; there is nothing to reuse (§1.5) |
| **Metrics** | **No, not as foreign data.** Any per-user or per-source-address breakdown is other people's personal data (§1.3) |
| **Direct read of another application's database** | **Recommend against.** It is not ISAAC's data store, and reading it directly bypasses that application's own access control |
| **The design** | **Yes — copy the pattern, not the data** (§1.4) |

---

## 3. Further ISAAC-binding conclusions

- **ORCID is record metadata, never a login identity.** An ORCID value in a record is a
  pattern-constrained metadata field. ISAAC must **not** treat it as an authenticated principal, and
  must not grant any right on the basis of one. A user signing in "via ORCID" is consistent with the
  identity provider federating it upstream, where ISAAC would never see it.
- **`attribution.uploaded_by` must be server-stamped, never accepted from a client.** ISAAC violated
  this: `export.transform` copied the whole `attribution` block, so a draft-authored `uploaded_by`
  reached an exported record and passed official validation. Fixed 2026-08-03 (PR #54, merge
  `d34f993`) — see [`identity-trust-contract.md`](identity-trust-contract.md) §"Two consequences".
  ISAAC was the outlier; the schema was right.
- **A username is a fragile primary key for ownership.** Where ownership relations are keyed on a
  username and no immutable internal identifier is stored, a rename at the identity provider silently
  transfers ownership. That is the substance of open questions **Q5** and **Q17**, and it is why the
  choice of canonical internal key is not a detail.
- **ISAAC has no telemetry of its own.** No request, usage, visit, session, error-rate or latency
  data exists: one middleware plus CORS, zero metrics dependencies, no counter identifier anywhere,
  and three test suites that actively forbid the Statistics page from implying otherwise. So an ISAAC
  "API usage over time" or "reliability" chart **cannot be built honestly from ISAAC's own data
  today.** Separately, seeded records carry hardcoded `created_utc` values, so a records-growth chart
  would plot fixture constants as a trend.

---

## 4. Open questions for Dean, raised by this audit

These extend the registry in [`identity-trust-contract.md`](identity-trust-contract.md) §7. They are
**not sent**; no approved workflow permits agent-to-Dean communication. Each is phrased as a decision
ISAAC needs, and none of them is a report about another system.

| # | Question | Blocks |
|---|---|---|
| **Q21** | The schema (2026-06-15) requires `uploaded_by` to be server-stamped from the authenticated identity. **Which identifier string is that** — an Authentik UID, an Authentik username, an ORCID subject, or something else? A username is the likely compatibility answer for existing upstream ownership rows, but see Q5/Q17. ISAAC currently stamps nothing. | Server-stamping; record ownership. Sharpens **Q10** |
| **Q22** | Are `/portal` and `/krish` served by the same Authentik application and the same forwarded-header policy? ISAAC's own observation on the `/krish` path suggests **not**, while `deployment.md` asserts they are. | Whether any header evidence gathered on one path transfers to the other |
| **Q23** | Should ISAAC consume aggregate usage metrics from elsewhere, or instrument its own requests? If consuming: which aggregates are approved for an ordinary signed-in user versus an administrator, and is a minimum aggregation threshold required? | General ISAAC usage metrics |
| **Q24** | May a signed-in user see **their own** API activity? This is distinct from record ownership and must not be conflated with it. | A bounded "My API Activity" section |

Also unchanged and still open: **Q4** (can an in-cluster caller reach the Service bypassing
Authentik?) — which gates everything identity-derived — plus **Q5**/**Q17** on identifier lifecycle,
and **Q19**/**Q20** in [`dean-authorization-packet.md`](dean-authorization-packet.md).

---

## 5. Method and limits

Static reading of published source. **This audit established nothing about any running deployment**
— not an edge's header-handling behaviour, not any production configuration, not whether any pod is
reachable in-cluster bypassing an authenticating edge, and not any database name. Each of those
requires deployment or infrastructure evidence this repository cannot see, and none was inferred. The
individual unknowns are not enumerated, because an enumeration is itself a checklist against a system
this project does not own. The `/krish` header observation referenced in §4 is **not** part of this
audit: it came from ISAAC's own probe of ISAAC's own path, and what it did and did not establish is
recorded in [`identity-trust-contract.md`](identity-trust-contract.md) §6A.

**On this file's own history.** Reducing a file in a later commit does not unpublish what earlier
commits contain — `SECURITY.md` §"If sensitive data is committed by accident" says so directly. The
statements above describe **this file as it now stands**; they are not a claim that this repository's
history, its branch refs, or any mirror of it has been altered. Any cleanup of that kind is the
repository owner's to coordinate and has not been performed here.
