# ISAAC Baseline Completion Matrix

**Created:** 2026-07-31 · **Status:** LIVE — this is the authoritative definition of "baseline" for
ISAAC. Update it in the same PR as any slice that changes a row.

**Purpose.** Define exactly which capabilities must exist, be tested, be deployed, and be
runtime-verified before ISAAC is a stable foundation for new product feature work — and, just as
importantly, which capabilities are *deliberately not* part of baseline. This document exists so that
"baseline complete" is a checkable claim rather than a feeling.

**Starting state of this document:** org canonical `main` = `543aa3a` (merge of PR #28, Slice 2A),
image `v0.0.32`, Dean's guide at `b746b1a`, backend 1794 passing, frontend 2145 passing across 93 files.

---

## 0. Authority and the single most consequential finding

Sources of authority, in precedence order (per the authorizing prompt):

1. **Dean's committed guide** — `docs/postgres-test-db-guide.md` @ `b746b1a` (verified: this is the
   newest commit touching that file; `git log --oneline -3 -- docs/postgres-test-db-guide.md`).
2. Current canonical repository behavior.
3. Authoritative schema (`schema/isaac_record_v1.json`, v1.05) and validation code.
4. Deployed runtime evidence.
5. Tests.
6. Roadmap and closure records.
7. Prior reports.

### The finding that shapes this entire matrix

Dean's guide, `docs/postgres-test-db-guide.md:149-162`, section *Displaying record content*:

> Hosted display of per-record content is **closed by default** pending an explicit visibility
> decision. Aggregate output -- record counts, counts by type and domain, validation totals,
> schema version, database reachability -- is fine to build and show now. Per-record fields
> (titles, scientific values, evidence, full JSON) need the visibility decision first, so build
> any read path with that boundary in it rather than adding the gate afterwards.

**Consequence.** Every capability whose output includes per-record content derived from the database
— a real-record list, a real-record detail view, real-record evidence, real-record export — is
**NOT AUTHORIZED**. This is not an inference from silence; it is an explicit written default-closed
decision by the database owner. Reachability of the database does not imply authorization to display
its rows, and the guide says so directly ("Writing to this database is unrestricted. Rendering its
rows in the hosted app is not").

This resolves the authorizing prompt's Phase 3 decision as **Outcome B — Not Authorized**, which in
turn makes Phases 4, 5, and 6 (real-record adapter, user-facing real-record parity, real-record
validation/evidence/export surfaces) out of scope for baseline. The exact question Dean must answer
is recorded in §5.

A second, weaker but real point: the guide's authorization of aggregate output names a closed list —
"record counts, counts by type and domain, validation totals, schema version, database reachability".
Slice 2A's report stays inside that list. Any *new* aggregate not on that list (for example, a
per-field missingness histogram) is a judgement call, and §4 treats it as such rather than assuming
it is covered.

---

## 1. Legend

- **Baseline required** — must be true before ISAAC is declared a stable foundation. Marked `yes`
  only where the absence would leave a foundational ambiguity, an untruthful claim, or an unverifiable
  system. *Useful ≠ required.*
- **Current state** — `done` · `partial` · `absent` · `blocked`.
- **Runtime-verified** — proven against the deployed app, not only in tests. `no` here is the single
  biggest honest gap in the project today.
- **Owner** — `orch` (this agent) · `Krish` · `Dean`.

Where a row says an external party owns it, that is a genuine gate, not a deferral of convenience.

---

## 2. The matrix

### 2.1 Deployment and runtime

| Capability | Authority | Baseline required | Current state | User-facing | Read/write | Runtime-verified | Owner | Blocking issue |
|---|---|---|---|---|---|---|---|---|
| Deployment health (`GET {base}/api/health`) | repo + `docs/deployment.md` | **yes** | done | indirect (chip) | read | **no** | Krish | Authentik edge — not reachable from this environment |
| Runtime mode (`synthetic-only`, fail-closed at boot) | `runtime_mode.py` | **yes** | done | yes | read | no | Krish | same |
| `/krish` base-path correctness | `docs/deployment.md` | **yes** | done | yes | read | no | Krish | same |
| Flux rollout of `v0.0.32` | `.github/workflows/build-push.yaml` | **yes** | published | no | n/a | **no** | Krish | hosted SHA unobserved |
| Authentik edge behavior | Dean | **yes** | done (external) | yes | n/a | no | Krish | credentials are Krish's; agent must not authenticate |
| Session-expiration behavior | — | no | absent | yes | n/a | no | Krish | edge-owned; not an app defect |

### 2.2 Database (Slice 2A)

Every row here is **code-complete and test-verified, and none is runtime-verified.** That distinction
is the whole point of Phase 1 and must not be blurred.

| Capability | Authority | Baseline required | Current state | Read/write | Runtime-verified | Owner |
|---|---|---|---|---|---|---|
| DB configuration detection (`PGHOST` as feature switch) | guide "Connection" | **yes** | done | read | no | Krish |
| DB connectivity (one short-lived connection) | guide | **yes** | done | read | **no** | Krish |
| Identity gate (database name pinned to constant, never env) | Slice 2A | **yes** | done | read | no | Krish |
| Role gate + session-role gate | guide "Constraints of the role" | **yes** | done | read | no | Krish |
| TLS gate (`pg_stat_ssl`, refuses if unconfirmed) | guide (`hostssl`) | **yes** | done | read | no | Krish |
| Read-only transaction enforcement (server-verified) | Slice 2A | **yes** | done | read | no | Krish |
| Mutation tripwire (`rows_before == rows_after`, `rows_modified == 0`) | Slice 2A | **yes** | done | read | no | Krish |
| Connection-limit respect (single-flight lock, limit 5) | guide | **yes** | done | read | no | Krish |
| Aggregate reconnaissance report | guide "Displaying record content" | **yes** | done | no | read | **no** | Krish |
| Full-schema validation of scanned records | guide "The records table" | **yes** | done | read | no | Krish |
| Schema-drift **classification** (beyond a raw failure count) | §4 below | conditional | absent | read | no | orch → Dean |
| Real-record adapter | — | **no** | absent | — | — | **Dean** |
| Real-record listing / detail / evidence / export | guide `:154` | **no** | absent | — | — | **Dean** |
| Hosted per-record display | guide `:154` | **no** | **closed by default** | — | — | **Dean** |
| Any database write | guide (app may write) but out of scope | **no** | absent | — | — | Krish |

Note the asymmetry the guide is explicit about and this matrix preserves: **writing** to this database
is unrestricted by Dean, yet it remains out of baseline scope because nothing in baseline needs it.
**Displaying** is restricted by Dean. Do not collapse these into one permission.

### 2.3 Synthetic workspace (existing, must stay regression-free)

| Capability | Baseline required | Current state | Runtime-verified | Notes |
|---|---|---|---|---|
| Record list / My Experiments | **yes** | done | no | 11 SPA routes, `App.tsx` |
| Record detail (Record Workbench) | **yes** | done | no | |
| Guided completion | **yes** | done | no | |
| Evidence explorer + sidecar | **yes** | done | no | sidecar remains **advisory**, no formal schema |
| Validation (draft + official) | **yes** | done | no | truth core, unchanged by Slice 2A |
| Export readiness + export | **yes** | done | no | synthetic only |
| Statistics | **yes** | done | no | |
| Governance page | **yes** | done | no | copy corrected in Slice 2A |
| Assistant (deterministic, bounded catalog, no LLM) | **yes** | done | no | |
| Project Memory + Graph browse/explore | **yes** | done | no | committed snapshot, not live |
| Settings: Overview · Data & Privacy · About · API Access · Endpoint Explorer | **yes** | done | no | `SettingsPage.tsx:87-92` |
| Synthetic demo idempotence | **yes** | done (guarded) | no | P36.8 regression guard |
| Upload / ingestion | **no** | **fail-closed by design** | no | must stay refused |
| Persistence beyond pod lifetime | **no** | `emptyDir`, ephemeral | no | documented, intentional |

### 2.4 Quality infrastructure

| Capability | Baseline required | Current state | Owner | Blocking |
|---|---|---|---|---|
| Backend suite | **yes** | done — 1794 passing | orch | — |
| Frontend suite | **yes** | done — 2145 / 93 files | orch | — |
| TypeScript build | **yes** | done | orch | — |
| Production build | **yes** | done | orch | — |
| Docker build + smoke | **yes** | done (CI) | orch | — |
| Snapshot drift gate (both artifacts) | **yes** | done | orch | — |
| Secret / leak / real-data scans | **yes** | done | orch | — |
| Copy-truthfulness guards (frontend + backend, parity-enforced) | **yes** | done | orch | — |
| **Real-browser test baseline** | **yes** | **absent** | orch | none — executable now |
| **Accessibility engine baseline** | **yes** | **absent** | orch | none — executable now |
| **Responsive baseline (4 viewports)** | **yes** | **absent** | orch | none — executable now |
| **Real 200% browser zoom** | **yes** | **absent** | orch | none for automation; human sign-off is Krish's |
| Cached-validator correctness | **yes** | **deferred defect** | orch | none — executable now |
| Vocabulary-cache keying correctness | **yes** | **deferred defect** | orch | none — executable now |
| `POST /api/uploads` OpenAPI description accuracy | **yes** | **deferred defect** | orch | none — executable now |
| Performance baseline (measured) | **yes** (measurement) | absent | orch | none |
| Performance *improvements* | **no** | n/a | orch | only measured, low-risk ones |

### 2.5 Memory plane / graph

| Capability | Baseline required | Current state | Notes |
|---|---|---|---|
| Committed memory snapshot + deep graph artifact | **yes** | done | two artifacts, `--detail-out` mandatory |
| CI drift detection for both | **yes** | done | |
| Graph *freshness* mechanism (regeneration reproducible in CI) | **no** | point-in-time | must be **clearly disclosed**; does not block baseline |
| Graphify as truth | **never** | n/a | CLAUDE.md §2/§7 |

### 2.6 Governance, docs, and organizational

| Capability | Baseline required | Current state | Owner |
|---|---|---|---|
| Docs accurately describe implemented / not implemented / blocked | **yes** | partial | orch |
| Data-classification claims truthful | **yes** | done (Slice 2A sweep) | orch |
| Deployment + rollback documented | **yes** | done | orch |
| Baseline Completion Matrix (this file) maintained | **yes** | done | orch |
| Per-slice reporting requirement in durable instructions | **yes** | partial | orch |
| Legacy portal coexistence | **no** | `/portal` stays live | Dean |
| Personal deployment retirement | **no** (checklist only) | checklist owed | Krish |
| Collaboration | **no** — explicitly deferred | absent | — |
| Human hosted QA sign-off | **yes** | **open** | **Krish** |
| Responsive / 200%-zoom human sign-off | **yes** | **open** | **Krish** |

---

## 3. What is explicitly NOT baseline

Recorded so that a later session cannot quietly promote these into scope:

- Real-record adapter, listing, detail, evidence, export, or any hosted per-record display — **Dean's
  default-closed visibility decision** (`docs/postgres-test-db-guide.md:154`).
- Any database write, migration, or app-specific table — no baseline capability needs one.
- Upload / ingestion. The endpoint stays fail-closed.
- Durable persistence beyond the pod.
- Collaboration in every form (ownership, review assignment, comments, mentions, presence,
  notifications, approval workflows, conflict resolution, role-based controls).
- External LLM / model provider; new Assistant intelligence.
- Portal replacement or retirement; any `isaac-k8` change.
- New scientific domains, analytics, dashboards, cosmetic redesign.
- Graph freshness automation (disclosed and non-blocking instead).

---

## 4. Schema-drift: what may be built without further authorization

Slice 2A's report already includes a count of records failing full-schema validation. Dean's guide
frames a non-zero count as *expected and useful* ("Finding drift is a useful result, not a problem
with the database -- report it rather than working around it").

If the hosted scan reports drift, the next question is *what kind*. The authorized-aggregate list
does not obviously cover a drift taxonomy, so the boundary is drawn conservatively:

**Buildable without asking (aggregate, no record content):**
- Counts by `jsonschema` validator **keyword** (`required`, `additionalProperties`, `enum`, `type`,
  `format`) — a structural category, not a value.
- Counts by **schema path**, where each path segment is emitted only if it is a key defined in the
  authoritative schema (already implemented as `safe_key_segment`), never a data value.
- Counts by declared `schema_version` value in the record, masked through the schema's own vocabulary.

**Requires Dean's explicit approval:**
- Any example value, even truncated or hashed.
- Any per-record row, even de-identified.
- Any field whose content originates from the record rather than from the schema.

The distinguishing rule, stated once: **the schema may describe the data; the data may not describe
itself.** If an output string can only be produced by reading a record's value, it is per-record
content and is closed.

If drift cannot be classified within that boundary, that is a **hard stop** for Dean, not a licence
to widen the allowlist.

---

## 5. External gates — exact questions

| # | Gate | Owner | Exact question / action | Effect if unanswered |
|---|---|---|---|---|
| G1 | Hosted rollout + recon verification | **Krish** | Run the checklist in the slice report against `/krish` while signed in; paste back the sanitized JSON | Blocks Phase 1, Phase 2, and any claim that Slice 2A works |
| G2 | Per-record visibility decision | **Dean** | "May the hosted app display per-record fields from `metadata_assistant` — titles, scientific values, evidence, full JSON — and if so to which audience and at what granularity?" | Real-record functionality stays absent; baseline can still complete without it |
| G3 | Drift taxonomy beyond §4's boundary | **Dean** | Only if the hosted scan shows drift that §4's aggregates cannot classify | Drift stays partially unexplained; documented as such |
| G4 | Responsive / 200%-zoom human sign-off | **Krish** | Visual sign-off at 4 viewports + real 200% zoom | Quality row stays open |
| G5 | Personal-deploy retirement | **Krish** | Approve the disable-not-delete operation | Cosmetic; no functional effect |

None of G1–G5 is resolvable by this agent. G1 and G4 require credentials the agent must not use; G2
and G3 require the database owner's decision; G5 requires account access the agent must not exercise.

---

## 6. Collaboration — deferred, with seams recorded

Collaboration is **not** baseline and nothing here authorizes building any part of it. The only
obligation baseline work carries is *not to foreclose it*. The seams that matter:

| Seam | What baseline must avoid |
|---|---|
| Record identity | Keep the ULID `record_id` the stable external key. Do not introduce a second, surface-local identifier that a future ownership model would have to reconcile. |
| Authorship / actor | The app currently has no concept of an actor. **Do not invent one** as a side effect of another feature — no implicit "current user" derived from Authentik headers, because role mapping is an unmade decision (readiness plan §3). |
| Mutation history | `record_history` exists in the database schema but the app never writes it. Baseline stays read-only, so no write path can accidentally define a history semantics that a real review workflow would then inherit. |
| Evidence authority | The sidecar is **advisory and has no formal schema**. Do not strengthen its authority; a future reviewer-approval flow would need it to be authoritative, and quietly promoting it now would pre-decide that. |
| Workflow state | `derive_workflow` is **fully derived** from record state with no human-review step. Do not add a stored, mutable workflow status — that is the seam a review/approval feature would occupy. |

Recording these is the entire deliverable. Implementing any of them is out of scope.

## 7. Baseline verdict rule

Baseline may be declared **Complete With External Blockers** when every row marked
`Baseline required: yes` is either `done` **and** runtime-verified, or is explicitly attributed to a
named external owner in §5 with evidence. It may **never** be declared plain **Complete** while G1
is open, because an unverified deployment is precisely the foundational ambiguity this matrix exists
to eliminate.
