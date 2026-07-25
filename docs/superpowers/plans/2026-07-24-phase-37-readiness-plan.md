# Phase 37 — Readiness Plan (NOT STARTED — planning only)

**Status:** PLANNING ONLY, 2026-07-24. **No Phase 37 work has begun.** Nothing here authorizes
implementation, access, connection, or credential handling. This document records what is known, what
is blocked, and the gates that must clear before any Phase 37 slice — per the 2026-07-24 execution
authorization's Phase 37 boundary.

Phase 37 = portal capability integration + real record data. It is the first phase that leaves the
synthetic-only, deterministic, single-image, edge-authenticated envelope Phase 35/36 established, so it
is **hard-gated** and staged.

---

## 1. Known facts (from Dean's written infrastructure answers)

- **`/portal` remains the active production portal**; **`/krish` remains a synthetic preview** on the
  same production track. The existing portal stays live until a verified replacement exists.
- **In-cluster Postgres is the preferred future record-data path** (direct DB), not the portal API.
  The portal API exists but is **not** the preferred application-integration path.
- **`ISAAC-DOE/isaac-k8` belongs to Dean** — all k8s manifest / ingress / resource / secret changes are
  his. The app repo never edits it.
- **Authentik forwarded headers are available** at the edge (identity/claims can be read from forwarded
  headers) — the basis for future app-level role mapping without a second login.
- **Production secrets live in Kubernetes**, configured by Dean.
- **Any external model-provider dependency** (an LLM/assist-layer) requires a **separate** billing,
  ownership, retention, and security decision — institution-owned credential, not a personal key.

## 2. Explicitly blocked / NOT authorized (hard gates)

Connect to **none** of these; implement none of them without an explicit, separate approval:

- Real / private SLAC/SSRL record data; leaving synthetic-only.
- In-cluster Postgres connection (even read-only) — a real DB connection is a staged, security-reviewed
  phase, never `emptyDir` → prod-writes directly.
- Portal API keys, portal module code integration from screenshots, or any portal-dependent module
  (Discovery, Ontology Editor, System Overview real analytics, API Keys, record consolidation, roles).
- Identity/role enforcement (app-level authZ) — mapped later from Authentik claims, no second login.
- External model provider / LLM / embeddings / assist-layer.
- Any `isaac-k8` change; retiring the blue portal; archiving/deleting the personal repo or the
  Vercel/Railway projects.

## 3. Required approvals & contracts (must exist before a Phase 37 slice)

- **Data governance approval** classifying any real data (public / internal / private /
  export-controlled) before a single real record is read, indexed, or sent anywhere.
- **Read-only Postgres reconnaissance design** — a reviewed, read-only connection plan (schema/table
  inventory, compatibility report, no writes) before any migration rehearsal.
- **API/DB contracts** — the real record schema/table contracts + how they map to the official ISAAC
  v1.05 record and the deterministic truth core (which must remain authoritative and LLM-free).
- **Role mapping** — Authentik group/claim → app role (Researcher / Reviewer / Ontology-Editor /
  Developer / Ops) with redaction rules (no raw IPs/usernames in any surface).
- **Security review + migration gates** — staged: read-only conn → compat report → synthetic migration
  rehearsal → staging DB → limited internal records → security review → prod cutover.
- **Legacy keep/merge/retire decisions** per portal module, only after per-module access + audit
  (purpose, users, backend owner, API contract, DB tables, auth claims, write semantics, scientific
  authority, data sensitivity, tests, perf, migration complexity, active/deprecated).
- **External-LLM decision** (if ever pursued): institution-owned credential + billing owner + k8s
  secret + retention + prompt-data policy + rate/cost controls + fallback + read-only guarantees; the
  truth core stays permanently LLM-free regardless.

## 4. Candidate first steps (only after the gates in §3 clear — NOT started)

1. Obtain portal access + per-module audit → capability matrix (Keep / Merge / Retire / Link / Defer).
2. Read-only Postgres reconnaissance (connection design + compatibility report) — no writes.
3. Role mapping design from Authentik forwarded headers (no second login, redaction rules).
4. Final IA extension only for destinations that become functional (functional-first, flat light IA).

## 5. Invariants that must survive into Phase 37

Deterministic truth core + official-schema authority + evidence audit + export behavior + no-guessing +
CSV reconciliation-only; truth plane LLM-free and Graphify-free; Assistant/memory advisory-only, never
record truth; light design system, no portal-shell leakage; account/continuity policy (no force-push,
no remote/identity/billing change without approval); snapshot drift gate; base-path cleanliness.

**Nothing above is authorized to execute. Phase 37 begins only on an explicit, separate Krish approval
after the §3 gates exist.**
