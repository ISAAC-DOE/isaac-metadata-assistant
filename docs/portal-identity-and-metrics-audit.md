# Portal Identity & Metrics Audit

**Created:** 2026-08-03 · **Status:** EVIDENCE — findings only. Nothing here authorizes an
implementation, and no identity or metrics wiring was added.

**Subject:** the deployed ISAAC portal at `/portal`, audited from its public source,
`ISAAC-DOE/isaac-ai-ready-record` @ `61bf689`. Read-only: no network authentication was attempted,
no cookie or credential was handled, and no identity value, record content, or IP address is
reproduced below. Field names, header names, table names and code structure only.

**Why this audit exists.** A screenshot of the portal shows an authenticated username, a
database-online indicator, and aggregate usage metrics. The standing conclusion in this repository
was that identity and statistics are simply unavailable to ISAAC. That conclusion was incomplete in
one direction and wrong in another, and both corrections matter for what `/krish` may build.

---

## 1. The displayed username is not evidence of authentication

The portal renders the username by echoing a forwarded header into server-rendered HTML. There is
**no `/me`, `/whoami`, `/session`, or `/profile` route anywhere** in the portal.

So the thing that looked like an identity contract is a header being printed. **ISAAC cannot ask the
portal who a user is**, because there is nothing to ask.

> **Redacted for public release.** This section previously carried a mechanism-level comparison of
> the portal's two identity paths, including the specific guard used on the weaker one and the
> condition under which it degrades. That is another team's live production system, the weakness is
> not ours to fix, and it was not fixed at the time of publication — so the operational specifics
> are withheld from the public record and routed to the owning team privately. The conclusions that
> govern **ISAAC's** engineering are kept in full below, because they are what future sessions must
> not silently reverse.

### What ISAAC may conclude

Two processes run with entirely separate identity models. One authenticates properly — a
server-to-server call to the identity provider, cached briefly, fail-closed. The other **does not
authenticate the subject at all**: it establishes at most that a request arrived over a channel
presenting a shared secret, which is a **channel** assertion, not a **subject** one — unsigned,
unbound to the username, replayable, and identical for any two parties holding it. The two paths
also derive administrator status from different sources, so **the same record can be
admin-editable through one door and not the other.**

Of the forwarded `X-authentik-*` headers, the portal consumes exactly **one**: `username`. `uid`,
`email`, `groups`, `name` and `entitlements` are received and discarded.

**Binding consequence for ISAAC:** a forwarded identity header is not proof of authentication, and
ISAAC must not build ownership, roles, or per-user statistics on one. See
[`identity-trust-contract.md`](identity-trust-contract.md) §6A.

---

## 2. ORCID is record metadata, never a login identity

The only ORCID in the portal is `attribution.contributors[].orcid` — an optional, pattern-constrained
metadata field. There is **no ORCID OAuth client, redirect URI, or token exchange**, and no `orcid`
database column.

It is affirmatively stripped of authority in three independent places, including a regression test
named `test_orcid_in_body_confers_no_rights` and the comment *"keyed on Authentik username, never
ORCID"*.

A user logging in "via ORCID" is consistent with Authentik federating ORCID upstream: the portal
would never see it, only `X-authentik-username`. **Do not treat an ORCID value in a record as an
authenticated principal.**

---

## 3. Record ownership exists upstream — and ISAAC violated the same contract

The portal has a real ownership and authorization model, all keyed on the **Authentik username**:

- `records.data->'attribution'->>'uploaded_by'` — **server-stamped**; `portal/database.py`
  `save_record()`: *"Client-supplied uploaded_by is overwritten."*
- `record_acl (record_id, grantee_identity, role, granted_by)` — explicit co-author grants, role
  constrained to `editor` so there is no higher tier to escalate to.
- `record_authz.py` — admin OR owner OR ACL editor; default deny; unowned legacy records are
  admin-only; **only owner or admin may manage the ACL**, so an editor cannot re-grant.

**This is the same guarantee the vendored ISAAC v1.05 schema states and ISAAC failed to honour.**
ISAAC's `export.transform` copied the whole `attribution` block, so a draft-authored `uploaded_by`
reached an exported record and passed official validation. Fixed 2026-08-03 (PR #54, merge
`d34f993`) — see [`identity-trust-contract.md`](identity-trust-contract.md) §"Two consequences".
ISAAC was the outlier, not the schema.

**Consequence worth recording:** because the username is the primary key of every ownership relation
and no immutable internal id is stored, a username reassignment at the IdP silently transfers
ownership of records, ACL grants and projects. That is the substance of open questions **Q5** and
**Q17**.

---

## 4. The metrics are the portal's own request log — definitively not GitHub PR data

A repo-wide search for pull-request or GitHub-API usage returns exactly one hit: `"Pr"`, the chemical
symbol for praseodymium. **Any claim that these are pull-request metrics is false.**

Every number comes from two Postgres tables the portal writes about itself. `api_requests` is
populated by a Flask `after_request` hook (fire-and-forget, so it **silently undercounts** on any DB
failure); `portal_access_log` gets one row per Streamlit session.

| Metric | What it actually counts | Scope |
|---|---|---|
| API Requests | rows in `api_requests` in window | **only `/portal/api/*`**, `/health` excluded — Streamlit activity is absent entirely |
| Distinct Users | `COUNT(DISTINCT username)` | **API-token callers, not portal visitors**; NULLs (unauthenticated) excluded |
| Rejections | `COUNT(*) FILTER (WHERE status BETWEEN 400 AND 499)` | as above |
| System Errors | `COUNT(*) FILTER (WHERE status >= 500)` | as above |
| Portal Visits | `COUNT(*)` of `portal_access_log` — **all time, not windowed**, unlike everything else on the panel | one row per Streamlit *session* |
| Requests over time / by user / by endpoint / unauth by IP | `date_trunc('day')`, `GROUP BY username`, `GROUP BY method\|\|endpoint`, `GROUP BY ip` | top 20; `endpoint` stores the **route rule**, so record ids are not written into the metrics table |

Freshness: Streamlit caches for 60s **process-globally** (one viewer's result is served to the next);
the Flask API computes live.

### A finding in the portal, reported not acted on

> **Redacted for public release.** A missing-authorization finding was identified in the portal
> during this audit: one surface renders personal data that the portal's own code marks as
> administrator-only. The component, the data classes, and the reason the gate is absent are
> **deliberately withheld from this public document.**
>
> Rationale: this is **another team's repository and another team's live deployment.** It was not
> tested against the deployment, not fixed by us, and not disclosed publicly. Publishing the
> specifics would be disclosing an unremediated vulnerability in a system we do not own and cannot
> patch. The detail is routed to the owning team privately.
>
> Exploitability depends on the ingress, which is not in that repository, so the honest bound is
> *any authenticated institutional user, not necessarily the public.*

**Binding consequence for ISAAC:** ISAAC must not ingest the portal's per-user or per-source-address
metrics. That conclusion is independent of the finding above and is restated in §6.

---

## 5. Evidence that `/portal` and `/krish` do NOT receive identical headers

`docs/deployment.md` asserts — with no manifest, no citation and no observation — that `/krish` runs
on the same `isaac-portal` Authentik application policy as `/portal`.

**There is now evidence against it.** ISAAC's own probe observed that on the `/krish` path, a
client-planted value in one of the headers the portal's security model depends on **arrived
untouched** ([`identity-trust-contract.md`](identity-trust-contract.md) §6A.2). Had the edge
overwritten that header globally, the planted value could not have survived. So the two paths do
not demonstrably receive the same header treatment, and the deployment doc's claim is unsupported.

> **Redacted for public release.** The inference this supports about the *portal's* current
> configuration state — and the environment setting it turns on — is withheld here for the same
> reason as §4: it describes a possible weakness in a live system we do not own. It is Dean's to
> answer privately.

**Operational consequence for ISAAC — unchanged and load-bearing: ISAAC must not copy the portal's
edge-header trust pattern.** On the ingress as actually observed, an ISAAC copy of it would be
fail-open. This is why `X-Isaac-Edge` is permanently disqualified as evidence of edge traversal in
[`identity-trust-contract.md`](identity-trust-contract.md) §6A.

---

## 6. Reuse verdict for `/krish`

| Contract | Reusable? |
|---|---|
| **Identity** | **No.** No endpoint exists to consult. There is nothing to reuse |
| **Metrics** | Technically, via the portal's usage-summary endpoint — but admin-token gated, **unversioned** (no OpenAPI, no version segment, no service-account concept; tokens are per-human and short-lived), and its per-user and per-source-address breakdowns carry other people's usernames and client IPs that ISAAC has no authorization to ingest |
| **Portal DB direct read** | **Recommend against.** Separate logical database and role; would bypass every guard in `record_authz.py` |
| **The design** | **Yes — copy the pattern, not the data.** ISAAC's own request logging is ~40 lines over its own tables and imports no foreign PII |

The last row is the honest route to a usage chart in ISAAC: **instrument ISAAC, do not siphon the
portal.** It needs durable storage, and ISAAC reports `persistence: "ephemeral"`, so it is a Phase-37
item and is not authorized now.

---

## 7. What this changes about ISAAC Statistics

ISAAC has **no** request, usage, visit, session, error-rate or latency telemetry: one middleware
(plus CORS), zero metrics dependencies, no counter identifier anywhere. Three existing test suites
actively forbid the Statistics page from implying otherwise.

Therefore an ISAAC "API usage over time" or "reliability" chart **cannot be built honestly from
ISAAC's own data**, and building it from the portal's data is gated by §6. Separately, the five
seeded records carry **hardcoded** `created_utc` values, so a records-growth chart would plot fixture
constants as a trend.

---

## 8. New questions for Dean, raised by this audit

These extend the registry in [`identity-trust-contract.md`](identity-trust-contract.md) §7. They are
**not sent**; no approved workflow permits agent-to-Dean communication.

| # | Question | Blocks |
|---|---|---|
| **Q21** | The schema (2026-06-15) requires `uploaded_by` to be server-stamped from the authenticated identity. **Which identifier string is that** — Authentik UID, username, an ORCID subject, or something else? The portal keys ownership on the username; ISAAC currently stamps nothing. | Server-stamping; record ownership. Sharpens **Q10** |
| **Q22** | Are `/portal` and `/krish` served by the same Authentik application and the same `auth-response-headers`? Observation suggests **not** (§5), while `deployment.md` asserts they are. | Whether portal header evidence transfers to `/krish` |
| **Q23** | May `/krish` consume `GET /portal/api/usage/summary`, or should ISAAC instrument its own requests? If consuming: which aggregates are approved for an ordinary signed-in user vs admin-only, and is a minimum aggregation threshold required? (Neither app has one today.) | General ISAAC usage metrics |
| **Q24** | May a signed-in user see **their own** API activity? This is distinct from record ownership and must not be conflated with it. | A bounded "My API Activity" section |

Also unchanged and still open: **Q4** (can an in-cluster caller reach the Service bypassing
Authentik?) — which gates everything identity-derived — plus **Q5**/**Q17** on identifier lifecycle,
and **Q19**/**Q20** in [`dean-authorization-packet.md`](dean-authorization-packet.md).

---

## 9. Method and limits

Static source reading of a public repository at a pinned commit. **Nothing about the running
deployment was established**: not the ingress's header-rewriting behaviour, not any production
environment setting, not whether the pod is reachable in-cluster bypassing the edge, not any
database name, and not whether the surface described in §4 is reachable by a non-administrator in
practice. Each requires deployment or infrastructure evidence this repository cannot see, and none
was inferred. The individual unknowns are not enumerated here, because the enumeration itself
sketched a checklist against another team's live system.
