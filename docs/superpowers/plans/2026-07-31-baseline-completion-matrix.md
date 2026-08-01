# ISAAC Baseline Completion Matrix

**Created:** 2026-07-31 · **Status:** LIVE — this is the authoritative definition of "baseline" for
ISAAC. Update it in the same PR as any slice that changes a row.

> ## Verdict: **Baseline Code-Complete, Runtime Unverified**
>
> Defined in **§7.1**, justified line by line in **§7.2**.
>
> **Three of the original reasons for this verdict have since been falsified, and are corrected here
> rather than quietly dropped.** As first written it said "the hosted SHA is unknown, the final
> runtime code is not yet in any published image, … the real database has never been contacted".
> All three were true when written and **all three are now false**: merge `ceea656` was published as
> image `v0.0.38` (source metadata resolving to that commit), Flux rolled it, hosted
> `/krish/api/health` was observed reporting `ceea656`, and the Slice 2A reconnaissance has run
> against the real database — its returned aggregates were re-scanned with the repo's own
> `db_recon.scan_for_leaks` (**no leaks**), all four frozen allowlists matched exactly, and it
> reported zero schema drift (30/30). Preserved rather than erased, because a verdict whose stated
> grounds silently change is not checkable.
>
> **The verdict itself still stands, for reasons that are current.** The 2026-08-01 responsive
> remediation (§3C) closed one Critical and five Important defects that were live in the deployed
> `ceea656` build, so the deployed runtime is now known to be **behind** the repository; that code
> is not yet in any published image. **G3** is open, and real **200% browser-zoom sign-off** is open
> and is not automatable — §3C's `zoom-200` project is the layout-level *equivalent* of 200%, never
> the browser's own zoom command. Plain **Baseline Complete** and **Complete With External Blockers**
> remain unavailable, for the reasons enumerated in §7.2. This verdict makes **no claim of any kind**
> about the current state of `/krish`.

**Purpose.** Define exactly which capabilities must exist, be tested, be deployed, and be
runtime-verified before ISAAC is a stable foundation for new product feature work — and, just as
importantly, which capabilities are *deliberately not* part of baseline. This document exists so that
"baseline complete" is a checkable claim rather than a feeling.

**Starting state of this document:** org canonical `main` = `543aa3a` (merge of PR #28, Slice 2A),
image `v0.0.32`, Dean's guide at `b746b1a`, backend 1794 passing, frontend 2145 passing across 93 files.

**State after the baseline-restoration slices (2026-07-31):** `main` = `c36053d`. PRs **#29** (baseline
definition, graph + performance decisions, retirement checklist), **#30** (truth-core correctness
D1–D3), **#31** (hosted QA checklist), **#32** (real-browser / accessibility / responsive baseline).
Backend **1801**, frontend **2145 / 93**, e2e **579** on macOS *and* on Linux CI. All CI green on every
merged SHA. **No hosted rollout has been observed** — see G1.

**State after the closure slice (2026-07-31).** `origin/main` = `610540e255d78818d897f9872aee8cf7ad248a03`
(PR **#33**, docs); local `main` clean, 0 ahead / 0 behind. The closure slice itself is **not yet
merged** at the time of writing. Measured in the working tree, each number quoted with the command
that produced it:

| Suite | Result | Command |
|---|---|---|
| Frontend | **2156 passed, 94 files** (was 2145 / 93 — the new `a11y-critical-fixes.test.tsx` adds 11) | `cd apps/web && npm test` |
| TypeScript | exit 0 | `cd apps/web && npx tsc -b` |
| End-to-end / a11y | **579 passed, 1 skipped** on macOS **and on Linux CI** (run `30677607861`, `a911b8c`) | `cd apps/web && npx playwright test` |
| Backend | **1814 passed, 0 failed** | `.venv/bin/pytest -q -p no:cacheprovider` |
| Recon endpoint | **130 passed** | `.venv/bin/pytest apps/api/tests/test_db_recon_endpoint.py -q` |
| Snapshot drift | **ok, no drift** (both artifacts) | `build_memory_snapshot.py … --detail-out --check` |

**Resolved during this slice, recorded rather than erased.** The backend suite first measured
**1810 passed, 1 failed** — `apps/api/tests/test_committed_snapshot.py`, expected snapshot drift,
because `routes.py` and `EvidenceTrailPanel.tsx` are both served-content manifest entries
(CLAUDE.md §17). The orchestrator regenerated both committed artifacts once after the tree settled,
and the suite then measured **1814 passed, 0 failed** with the drift check clean. Both numbers are
kept here because reporting only the final one would hide that the gate fired and was answered.

**A correction to a claim made earlier in this effort.** An earlier report stated that *no image
newer than `v0.0.32` was published*. **That was false.** `.github/workflows/build-push.yaml` has no
path filters, so **every** push to `main` publishes — including docs-only merges. Images `v0.0.33`
through `v0.0.37` were all built and pushed by successful CI runs (`e8a02a1`→0.0.33,
`91b74f8`→0.0.34, `c36a0f5`→0.0.35, `c36053d`→0.0.36, `610540e`→0.0.37); each git tag was created
**by `github-actions`** 60–78 s after its merge commit, verified through
`git for-each-ref --format='%(taggername) %(taggerdate)'`, so the tags are workflow output rather
than a human's. Two limits on that, stated because they change what the sentence is worth:
**registry-side confirmation was not possible** (anonymous `ghcr.io` token failed;
`gh api /orgs/ISAAC-DOE/packages` → 403 for missing `read:packages`), so those digests are CI's
record of what it pushed, not an independent read of the registry; and **which image the cluster
selects is UNDETERMINED** — no Flux `ImagePolicy` or `ImageUpdateAutomation` manifest exists in this
repository, it lives in `isaac-k8`, and it is not guessed here.

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
its rows. The guide says so directly at `:151` — "Writing to this database is unrestricted. Rendering
its rows in the hosted app is not, because the seeded records are production-derived" — and again at
`:154`. It adds at `:160-162` that anything behind the "DB configured" switch "goes live on the next
image roll. Decide the boundary before shipping the read path, not after."

This resolves the authorizing prompt's Phase 3 decision as **Outcome B — Not Authorized**, which in
turn makes Phases 4, 5, and 6 (real-record adapter, user-facing real-record parity, real-record
validation/evidence/export surfaces) out of scope for baseline. The exact question Dean must answer
is recorded in §5.

### A second finding: Slice 2A went past Dean's enumerated list — by **five** fields, now **withdrawn**

The guide's authorization of aggregate output names a specific list — "record counts, counts by type
and domain, validation totals, schema version, database reachability". **The Slice 2A report shipped
in `v0.0.32` was broader than that list**, and this document originally claimed otherwise, then
undercounted the overage as *three*. It was **five**:

| Field served in `v0.0.32` | On Dean's enumerated list? | Status now |
|---|---|---|
| `total_records`, `records_scanned`, `records_parsed`, `parse_failures` | yes — record counts | retained |
| `by_record_type`, `by_record_domain` | yes — counts by type and domain | retained |
| `records_passing_full_schema`, `records_failing_full_schema`, `total_validation_issues` | yes — validation totals | retained |
| `by_rule_family`, `by_schema_path` | defensible — a breakdown of validation totals, produced by the **public** schema | **retained, with reasoning** |
| `by_instance_path` | **no** — paths through the actual record data, schema-masked but record-derived | **WITHDRAWN** |
| `distinct_structural_signatures` | **no** — a count of distinct record *shapes* | **WITHDRAWN** |
| `total_link_count`, `dangling_link_count` | **no** — derived from `data->'links'` | **WITHDRAWN** |
| `vocabulary_term_count` | **no** — cardinality of a stored table | **WITHDRAWN**, coarsened to the boolean `vocabulary_cache_present` |
| `record_id_digest_count`, `expected_seed_rows`, `seed_count_matches` | not enumerated, but carry no record content | retained |

None of these emits a scientific value, a title, an id, or any record text — the masking in
`safe_key_segment` (`db_recon.py:436-470`; note `:470` is the one branch that returns a key verbatim,
reached only after the declared-name check) holds under static review. Say "static review" and mean
it: that is **code reading, not a runtime observation**, and the scan has never run.

**What changed, and what did not.** All five are now removed from the HTTP response and **named** in
`dataset.withheld_pending_visibility_decision`, so the narrowing is auditable instead of invisible.
The root cause was structural rather than a slip of judgement: only **top-level** response keys were
frozen, so a record-derived aggregate could ship inside `dataset` without tripping a contract test.
`dataset` and `integrity` are now built from frozen allowlists — `_DB_RECON_DATASET_KEYS` and
`_DB_RECON_INTEGRITY_KEYS` — and an unlisted key **raises**, failing closed into a sanitized
`projection` failure envelope rather than being served. `run_recon` still computes the wider report
for the offline `scripts/db_recon.py`, which the Dockerfile `COPY` allowlist keeps **out of the
image** (`Dockerfile:37` copies only `scripts/check_graphify_freshness.py`), pinned by test.

**What withdrawal does not do is undo the past.** The five **were served in a published image**. G3
therefore stays open, but its character has changed: it is no longer a live exposure awaiting a
decision, it is a **question** — *were any of these within what you intended, and may they be
restored?* Stating this plainly is the point of this document. A governance record that describes its
own project as more conservative than it actually was is the precise failure mode it exists to
prevent, and so is one that quietly rewrites history once the code is fixed.

Scope of this audit, stated so it is not over-read: it covers the `dataset` block only. The response
also carries `database` (gate booleans plus `server_version` / `server_version_major` /
`expected_major_version_match`, built by `_db_recon_database_block`) and `integrity` (built from
`_DB_RECON_INTEGRITY_KEYS`, which includes `rows_before` / `rows_after` — those are **record
counts**, not merely statement counts). Neither is a disclosure question: `rows_before`/`rows_after`
duplicate `total_records`, which Dean explicitly authorized, and every other `integrity` field is an
operational property of the scan itself. But the audit above is a `dataset` audit, not a
whole-response audit, and must not be cited as one. Symbol names are used here in place of line
numbers deliberately: `routes.py` moved under the G3 narrowing, and a line citation that drifts is
worse than no citation.

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
| Image publication (every push to `main`) | `.github/workflows/build-push.yaml` | **yes** | done — `v0.0.33`–`v0.0.37` all built and pushed by successful CI runs; no path filters, so docs-only merges publish too | no | n/a | **no** — CI's record of what it pushed, **not** a registry read (`ghcr.io` anon token failed; `gh api /orgs/ISAAC-DOE/packages` → 403) | orch | — |
| Flux rollout onto `/krish` | `isaac-k8` (not in this repo) | **yes** | **UNDETERMINED** — no `ImagePolicy` / `ImageUpdateAutomation` manifest exists here, so which tag the cluster selects is unknown and is not guessed | no | n/a | **no** | Krish / Dean | hosted `/krish/api/health` returned **HTTP 302** (Authentik edge); running image UNKNOWN |
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
| Aggregate reconnaissance report | guide "Displaying record content" | **yes** | done | read | **no** | Krish |
| Full-schema validation of scanned records | guide "The records table" | **yes** | done | read | no | Krish |
| Schema-drift **classification** (`by_rule_family`, `by_schema_path`) | §4 below | **yes** | **done — shipped in Slice 2A, retained** | read | **no** | Krish |
| — the five record-derived aggregates: `by_instance_path`, `distinct_structural_signatures`, `total_link_count`, `dangling_link_count`, `vocabulary_term_count` | §0 / G3 | **no** — never authorized | **WITHDRAWN** — served in `v0.0.32`, removed from the projection, named in `dataset.withheld_pending_visibility_decision`; `vocabulary_term_count` coarsened to boolean `vocabulary_cache_present` | read | **no** | **Dean** (G3) |
| `dataset` / `integrity` frozen key allowlists (unlisted key fails closed) | §0 | **yes** | done | read | **no** | Krish |
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
| Record list / My Experiments | **yes** | done | no | 10 route patterns (`routes.ts` `ROUTE_PATTERNS`) + `/` and `*` redirects = 12 `<Route>` elements in `App.tsx` |
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
| Backend suite | **yes** | done — **1814 passed, 0 failed** (`.venv/bin/pytest -q -p no:cacheprovider`), after the snapshot regeneration that the first run (1810 passed / 1 failed, expected manifest drift) correctly demanded | orch | — |
| Frontend suite | **yes** | done — **2156 / 94 files** (`cd apps/web && npm test`), but see F1 | orch | — |
| TypeScript build | **yes** | done | orch | — |
| Production build | **yes** | done | orch | — |
| Docker build + smoke | **yes** | done (CI) | orch | — |
| Snapshot drift gate (both artifacts) | **yes** | done | orch | — |
| Secret / leak / real-data scans | **yes** | done | orch | — |
| Copy-truthfulness guards (frontend + backend, parity-enforced) | **yes** | done | orch | — |
| **Real-browser test baseline** | **yes** | **done** — Playwright/Chromium, PR #32 (`c36053d`); **579 passed, 1 skipped** locally on macOS after the closure fixes; Linux CI is the authority | orch | — |
| **Accessibility engine baseline** | **yes** | **done** — axe-core, 18 surfaces × 5 projects, count-based baseline. **Tightened to 1,628 darwin / 1,634 linux** (from 1,974 / 1,980) when A1 and A2 were fixed and their entries deleted. **darwin measured locally; linux MEASURED by CI** (run `30677607861` on `a911b8c` — the three deleted entries assert ZERO nodes and passed under Linux font metrics), so 1,634 is validated, not arithmetic | orch | — |
| **Responsive baseline (4 viewports)** | **yes** | **done** — 1280×800, 1024×768, 768×1024, 375×812 | orch | — |
| **200% zoom — layout-level model, automated** | **yes** | **done as a model, not as the thing.** The `zoom-200` project is `{640×400, DPR 2}`, asserted not assumed. Probed directly: DPR contributes **nothing** to CSS layout (DPR 2 and DPR 1 measured byte-identically), and **no CDP method, launch flag or Playwright API can drive Chrome's own zoom control** — so viewport-halving is the correct *and only available* model | orch | — |
| **Real browser zoom at 200% (`Cmd`/`Ctrl`-`+`)** | **yes** | **OPEN — human only.** Not automatable in Chromium at all; not a deferral of effort | **Krish** | **G4**; automation cannot close it |
| Accessibility defects found (A1–A8 below) | **yes** — recorded | **partial** — **A1 and A2 (both critical) FIXED**, baseline entries deleted so a regression fails as `new`; **A3–A8 OPEN and deliberately deferred**, each still baselined at an exact node count | orch | §3B; the 4 open a11y findings are serious/moderate, the 2 open layout findings are unrated |
| Cached-validator correctness — D1 | **yes** | **done** — PR #30, merge `91b74f8` | orch | — |
| Vocabulary-cache keying correctness — D2 | **yes** | **done** — PR #30 | orch | — |
| `POST /api/uploads` OpenAPI description accuracy — D3 | **yes** | **done** — PR #30 | orch | — |
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
| Docs accurately describe implemented / not implemented / blocked | **yes** | partial — an earlier slice fixed two false claims about shipped code (§0) and a stale `psycopg2` claim in the readiness plan §3; the closure slice corrected three more: the overage was **five** aggregates not three, an earlier report's "no image newer than `v0.0.32` was published" was **false**, and the `zoom-200` project was described as "REAL 200% browser zoom" when it is a layout-level model. **More may remain** — that is why this row is `partial`, and it should stay `partial` until a sweep proves otherwise rather than because nobody looked | orch |
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
  default-closed visibility decision** (`docs/postgres-test-db-guide.md:154`). **Classify this
  correctly:** it is an **external blocker (G2)** owned by the database owner, **not application
  debt and not a defect of this project**. It is absent because the owner withheld it, not because
  it was skipped, and it must never be counted against the verdict in §7.2 or listed alongside
  findings like A3–A8. The guide is explicit that database *reachability* is not display
  authorization (`:149-162`).
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

## 4. Schema-drift: what Slice 2A already emits, and where the boundary sits

Dean's guide frames a non-zero failure count as *expected and useful* ("Finding drift is a useful
result, not a problem with the database -- report it rather than working around it").

### 4.1 Already shipped (do not rebuild)

A drift **taxonomy** is not future work — it is merged and live in `v0.0.32`:

- `by_rule_family` — counts per validator keyword. **The label set depends on which engine ran, and
  the deployed pod will not use the one it is tempting to quote.** `run_recon` prefers the diagnostics
  enricher when it loads (`db_recon.py:1807-1811`, setting `engine = "diagnostics"`), and `src/` *is*
  in the image (`Dockerfile:33`), so it will load. That engine labels a family with the raw jsonschema
  keyword — `str(err.validator)`, `diagnostics.py:394` — which is an **open set** (`minItems`,
  `maxLength`, `multipleOf`, `dependentRequired`, …). Only the fallback `official` engine uses the 12
  normalized patterns in `_FAMILY_PATTERNS` (`db_recon.py:901-921`), plus `other` for no match
  (`:942`). This is deliberate, not a bug: `db_recon.py:925-933` records that "the family label each
  engine emits is NOT rewritten … renaming its taxonomy would misreport that." The report says which
  engine produced it. **Do not predict the label set before the scan runs.**
- `by_schema_path` — counts per path through the *schema*. **Retained.** Honest caveat: it is
  populated by the diagnostics enricher; if that enricher fails to load, this comes back **empty**
  and `by_rule_family` is the only breakdown carrying signal. An empty list is therefore not
  evidence of a clean database.
- `by_instance_path` — counts per path through the *record*, every segment schema-masked.
  **WITHDRAWN from the response** (§0). Still computed for the out-of-image offline script.

So the hosted scan should already answer "what kind of drift" without any new endpoint, using the two
retained breakdowns. Build nothing until the G1 report shows these are insufficient.

### 4.2 The distinguishing rule

**The schema may describe the data; the data may not describe itself.** If an output string can only
be produced by reading a record's value, it is per-record content and is closed.

`by_instance_path` was the deliberate boundary case: the *path* is schema-derived and masked, but the
*fact that the path is populated* is record-derived. **It shipped in `v0.0.32` and has since been
withdrawn** — along with `distinct_structural_signatures`, `total_link_count`, `dangling_link_count`
and `vocabulary_term_count` — and named in `dataset.withheld_pending_visibility_decision`. The rule
above is what decided it, applied consistently: `by_rule_family` and `by_schema_path` survive because
the **public vendored schema** produces them; the five do not, because reading the stored documents
is what produces them. G3 asks whether any may come back.

### 4.3 Three constraints the rule does not imply on its own

Obeying §4.2 literally still permits per-record disclosure by arithmetic. These are binding:

1. **Minimum cell size.** The *documented seed* is **30 rows** (`DOCUMENTED_SEED_ROWS`, `db_recon.py:133`);
   the actual row count is **unobserved** — the scan has never run, which is exactly why the report
   emits `seed_count_matches`. At that order of magnitude a count of `1` at a specific path is a
   per-record fact wearing aggregate clothing. Any *new* aggregate must
   suppress or bucket cells below a stated threshold. (The withdrawn fields predated this rule.
   Whether the two **retained** breakdowns need it — `by_rule_family` and `by_schema_path` can both
   report a count of 1 — is part of G3, and is the sharpest remaining question in this section.)
2. **No cross-tabulation that narrows to an individual.** Two coarse breakdowns can intersect to
   n=1. Adding a dimension to an existing breakdown is not a free extension of it.
3. **No caller-parameterized aggregation, ever.** The endpoint takes no parameters and must not.
   A filter such as `?record_type=…` lets a caller difference two responses to reconstruct
   per-record facts while every individual response looks compliant.

### 4.4 Requires Dean's explicit approval

- Any example value, even truncated or hashed.
- Any per-record row, even de-identified — including one reached by arithmetic (§4.3).
- Any field whose content originates from the record rather than from the schema.

If drift cannot be classified within this boundary, that is a **hard stop** for Dean, not a licence
to widen the allowlist.

---

## 3A. F1 — a pre-existing load-sensitive frontend flake

Found while verifying B1, and **proven pre-existing** rather than assumed.

`apps/web/src/__tests__/graph-real-artifact.test.tsx` reads the real 493,985-byte
`memory-graph-detail.json` from disk (`:84`) and asserts DOM bounds under a 5 s default timeout. It
fails intermittently when the machine is busy. Observed on the *same commit*, same code: 49 failures,
then 39, then 17, monotonically decreasing as load average fell from 97 to 27 — every failure a
`Test timed out in 5000ms`.

**Proof it is not caused by B1**, in two independent ways:

1. *By construction* — B1 changes zero `apps/web/` files, and `memory-graph-detail.json` is
   byte-identical to `e8a02a1` (`git diff --stat e8a02a1 -- <artifact>` is empty). The test's entire
   dependency closure is unchanged.
2. *Empirically* — stashing all B1 changes and running the file on clean `e8a02a1` reproduces the
   failure identically (`1 failed | 2 passed`).

**Why it matters beyond the nuisance:** a suite that fails differently on each run cannot support the
claim "the frontend suite passes", which is a baseline-required row. CI has not caught it because
GitHub runners are lightly loaded — every CI run in this session was green. That makes it a latent
false-green: the gate works only while the machine is quiet.

**Not fixed here** — it is outside B1's authorized file set, and fixing it means either raising the
timeout (hides the real cost) or shrinking the fixture (weakens a test that deliberately measures
*real* payload size). Both are judgement calls that deserve their own slice. Recorded so the next
frontend slice owns it, and so nobody reads an intermittent red as a regression.

## 3B. A1–A8 — accessibility and layout defects found by the new baseline

Found by PR #32, all **pre-existing application behaviour**; that slice was authorized to measure the
app, not repair it, so it fixed none of them. Every one was independently confirmed real by review;
there are no phantoms.

**The closure slice fixed the two critical ones and no others.** Severities below are the ones
originally recorded. **None has been downgraded**, and none may be: an open finding does not become
less serious because closing the phase would look tidier.

| ID | Rule | Impact | Status | Where |
|---|---|---|---|---|
| **A1** | `button-name` | **critical** | **FIXED** | The global search trigger had **no accessible name at all** at 375px and at 200% zoom (`chrome.css:503` hides the label and kbd hint; the SVG is `aria-hidden`, no `aria-label`). **Fix:** `aria-label="Search"` on the trigger in `apps/web/src/components/SearchDialog.tsx`; **no CSS changed**, so the name no longer depends on a media query. **Baseline impact:** entry deleted, **−36 nodes** |
| **A2** | `aria-allowed-attr` / `aria-allowed-role` | **critical** | **FIXED** | 31 Evidence Trail entries were `<button role="listitem" aria-pressed>` — the role killed the button role and forbids `aria-pressed`, so selection state was not exposed. **Fix:** in `apps/web/src/components/EvidenceTrailPanel.tsx` the `role="listitem"` moved onto a wrapper `<div class="trail-item">`, leaving a plain `<button>` with its implicit role and a now-valid `aria-pressed`. **Baseline impact:** both entries deleted, **−310 nodes** (155 per rule) |
| **A3** | `color-contrast` | **serious** | **OPEN — deferred** | 1,610 nodes, every surface. **Three causes, not one**: `--text-disabled #c0c8d0` rendered as Evidence line numbers at **1.56:1**; genuinely low tokens; and **five `opacity` composites of tokens that pass at full strength** — darkening tokens will not fix those |
| **A4** | `scrollable-region-focusable` | **serious** | **OPEN — deferred** | 3 pairs: `evidence` desktop/mobile, `settings-api` mobile |
| **A5** | `page-has-heading-one` | moderate | **OPEN — deferred** | `/load` has no `<h1>` |
| **A6** | `landmark-unique` | moderate | **OPEN — deferred, and explicitly NOT closed by A1** | Two unnamed `role="search"` landmarks on Endpoint Explorer. The `aria-label` added for A1 sits on the `<button>`, **not** on the `role="search"` wrapper `<div>`, so it does not name the landmark — naming one requires `aria-label`/`aria-labelledby` on the landmark element itself. Its 10-node baseline entry is unchanged |
| **A7** | LAYOUT-01 | — | **OPEN — deferred** | Record StatusBar does not reflow: 575px of content in a 353px box at 375px, clipped and overlapping |
| **A8** | LAYOUT-02 | — | **OPEN — deferred** | Record-context chip clipped: `chip-draft` on Evidence (macOS+Linux) and `chip-exported` on Export Readiness (**Linux only** — SF Pro hid it). One `.record-context` fix closes both |

**Why A1 and A2 were fixed and A3–A8 were not — the rationale, so it is a decision rather than an
omission.** A1 and A2 are the two **critical** findings, and both are single-component,
CSS-free changes whose effect is provable in the accessibility tree: one attribute added, one role
moved. Each is fully covered by a deleted baseline entry, so the fix is enforced on every run rather
than trusted. A3–A8 are not like that:

- **A3** is a design-system change. Its own analysis shows the naive fix is wrong — five of the
  failures are `opacity` composites of tokens that already pass at full strength, so darkening tokens
  cannot close them. It needs a palette decision, not a patch.
- **A4** changes keyboard-focus semantics of scroll containers (adding `tabindex="0"` introduces new
  tab stops); **A5** adds a heading to `/load` and must also drop `expectH1: false` from its surfaces
  entry; **A6** names two landmarks and needs the two names to be *meaningfully* distinct, which is
  copy, not markup.
- **A7 / A8** are CSS reflow changes to shared record chrome, which move layout on **every** record
  surface at **every** viewport and would move axe counts on **both** platforms — one of which cannot
  be measured from a laptop at all (§6.1 of the browser/a11y doc). That is a slice with a CI
  round-trip in it, not a closure-slice add-on.

**Baseline impact of leaving A3–A8 open:** each remains enumerated in `e2e/a11y-baseline.ts` or
`e2e/layout-baseline.ts` at an exact per-`surface@project` node count, with an identity guard, and
the ratchet fails on `new`, `grew`, `improved`, `new-target` and `new-foreground`. Nothing is
suppressed and no axe rule is disabled. The debt is **measured and cannot silently grow** — which is
the property baseline actually requires.

**Do the open ones block baseline?** §7's rule says "no known Critical or Important findings". Both
**Critical** findings are now closed. The remaining findings are serious/moderate and unrated-layout,
they are pre-existing, and baseline work **discovered and documented them where nothing previously
measured them at all**. Going from no measurement to a ratcheted, per-node baseline is the
foundational improvement; leaving A3–A8 open is a known, owned, bounded debt with a named next slice
— not a foundational ambiguity. They do **not** block the verdict in §7. What blocks it is stated
there, and it is not this.

## 3C. C1 and I1–I5 — the responsive defect set, and the probes that hid it

Found by the Local Production UI Verification (2026-07-31) against the deployed merge `ceea656`, and
closed by the Responsive Baseline Remediation slice (PR **#35**, branch
`fix/responsive-baseline-remediation`). All were **pre-existing**; all were present through every
green run of the 579-test suite.

### The single most consequential finding of this slice

**"579 tests green" and "the UI is sound at 375px" were never the same claim, and `ceea656` was a
concrete counterexample.** Three probes were each blind in a different, specific way — their
assertions were weaker than their names implied:

| Probe | The hole | The proof |
|---|---|---|
| `horizontalPageScroll` | read only `document.documentElement` and `document.body` | `/experiments`@375 reported a clean `375 == 375` while `main.screen-main.pad` measured **scrollWidth 476 vs clientWidth 353** |
| `findClippedText` | exempted **every** `text-overflow: ellipsis` element regardless of magnitude, **and** skipped zero-width elements before inspecting them | `.record-title` — clientWidth **0**, scrollWidth **395**, i.e. 100% content loss with not even an ellipsis glyph painted — was **doubly** exempt |
| `findObscuredControls` | scanned only **interactive** elements, and hit-tested the centre of the **visible intersection** | a non-interactive `<span>` painting across the search button was outside its universe entirely; a **4.9px** visible sliver of a 128px button hit-tested to itself and passed |

Anyone citing a green e2e count as evidence of responsive correctness should read this table first.
**Do not write, anywhere, that the 579-test baseline proved the 375px UI sound.** It proved the
assertions it actually made, and those are now enumerated above.

### Defects closed

Measured on the production build at 375×812 unless noted; before → after.

| ID | Sev | Root cause | Before → After |
|---|---|---|---|
| **C1** | **Critical** | `.record-context` was shrunk to the top bar's whole remainder (69px at 375, 14px at 320) while `overflow: visible`, so its `nowrap` children painted across the search button and mode chip | `elementFromPoint` at 5 points across `.record-surface`: **3 of 5 foreign → 0 of 5**, verified on 5 record routes × 7 widths (320/375/390/640/768/1024/1280) |
| **I4** | Important | `.record-title` is a flex item with `overflow: hidden`, so `min-width: auto` resolved to 0 | `0/395` at 375 **and at 768** → `329/395` and `710/710`. It had been visible **nowhere**: the page `<h1>` on these routes is `sr-only` |
| **I1** | Important | `.page-actions` was `flex: none` + `nowrap` at **447.7px** in a 353px box. `.page-header` **already** wrapped — it was never the cause, and a test now guards that | `39..486.7` (122.7px past the content edge) → `39..336`, hit-testable at 320 and 375 |
| **I2** | Important | row flex with a `flex: none` 151.7px action squeezing a `flex: 1` body | body `88.2×465.2` → `227×187.6`; action on its own line |
| **I3** | Important | selection differed **only** by background and border colour | fails SC 1.4.11 at **1.03:1 / 1.31:1** → 6×6 `::before` status dot at **5.23:1 / 5.38:1**, zero layout shift, `aria-pressed` untouched |
| **I5** | Important | one global `max-height: 34vh` sized for the narrow drawer, applied to the desktop rail with 424.5px free above | list `114` of `475` scrollHeight → `178`; 0 orphan headings at 1280×800/600, 1440×900, 1920×1080 |
| **M1** | Minor | `.exp-trailing` is `flex: none` at 180.4px; `.exp-main` had `min-width: 0`, so it took `rowContent − 196.4` **and** the row could never break | `.exp-title`@320 `12/67` → `208/208`; `.exp-scenario-text` `0/8` → `191/191` |
| **M3** | Minor | — | **still open, retained as debt.** Recorded as `LAYOUT-02`; its darwin instance is now fixed by C1 and was deleted, its **Linux** instance is retained because Linux font metrics cannot be measured from this environment |

Two design notes worth keeping, because both were arrived at by rejecting the obvious fix:

- **C1 was not closed by hiding the leaf crumb.** That was the proposed approach; measurement refuted
  it — there was no freed width to reclaim (69px *was* the whole remainder), and the crumb does not
  duplicate a visible heading, because the page `<h1>` is `sr-only`. Hiding it would have deleted the
  surface name from every visible location. The bar wraps to two rows at ≤1024 on record surfaces
  instead.
- **I3 was not closed with a leading border.** `design-handoff/05-design-system/no-vertical-rail-rule.md`
  forbids it and names the selected evidence row as its own case 4; the repo's `no-vertical-rail.test.ts`
  caught the attempt. The approved status-dot pattern was used instead. *(That design doc is
  **gitignored**, so the correction recording the dot could not be committed; the committed
  enforcement is the test plus the CSS comments.)*

### The strengthened responsive-test contract

Binding on every future slice:

1. **Nested overflow** — `findOverflowingRegions` reports any element with `scrollWidth > clientWidth + 1`
   whose computed `overflow-x` actually clips or scrolls, naming the culprit. Document-level checking
   alone is not sufficient and never was.
2. **Content loss is magnitude-aware** — `text-overflow: ellipsis` no longer excuses a clip on its own,
   and zero-width elements are no longer skipped. Truncation is tolerated only while a meaningful
   fragment survives (24px, or 40px for critical labels, or ≥20% of the string).
3. **Occlusion covers critical non-interactive labels** through an enumerated selector set, tests
   usable width and the **intended** box rather than the visible intersection, and treats a sliver as
   unusable.
4. **Exemptions are narrow and cite intent.** `e2e/layout-allowlist.ts` requires a **class** selector
   (tag, universal and subtree selectors are forbidden), an exhaustive surface list, and a citation of
   the `src/**` line that declares the behaviour deliberate. **Geometric exemption is forbidden** — a
   "clientWidth ≤ 1 is fine" rule would have swallowed the zero-width `record-title`, which is the
   whole reason the file exists.
5. **Known defects go in `layout-baseline.ts` with exact per-instance selectors**, never a substring or
   a wildcard, and never an annotation used to make a failure disappear.

### Debt this slice recorded rather than fixed, deliberately

- **LAYOUT-03** — the floating Assistant trigger (`position: fixed`, `z-index: 45`, ≤1024px) paints
  **completely** over the StatusBar's honesty statement "hosted preview · no telemetry" (visible-area
  ratio 1.00, survives `scrollIntoView`). 17 instances. Pre-existence proven by re-running the probe
  against the stashed CSS. Outside this slice's authorized defect list.
- **LAYOUT-04** — nested horizontal overflow, 16 keys / **20 instances**, across `evidence`,
  `record-detail`, `export-readiness`, `export-readiness-done`, `guided-completion`, `load`. Two causes:
  `div.screen-card` inheriting the non-reflowing StatusBar's width, and `main` regions whose min-content
  exceeds a phone viewport. The `/experiments` case that motivated the hardening is **absent** — it was
  fixed by I1, so it fails if it returns.
- **The width sweep probes occlusion at one scroll offset**, and is therefore blind to 17 occlusion
  instances visible only at the bottom offset — all of them the LAYOUT-03 class. Measured, and
  **disclosed in the spec itself** rather than left implicit. Fixing it is a baseline-authoring
  decision (17 new `@width-<n>` instances), not a probe defect.

### Accessibility baseline movement, and why it is not a weakened test

darwin total **1628 → 1629**, from three measured per-surface changes. Two are **increases**, and both
are pre-existing failures moving from axe's `incomplete` bucket into `violations` because removing the
overlaps let axe **resolve backgrounds it previously could not**:

- `.guided-suggestion-not` (`guided-completion@mobile-375x812`, 7 → 8). A/B with only the CSS reverted:
  identical geometry (102.5×35.6) and identical colour (`rgb(120,131,143)`), while `incomplete` fell
  6 → 3 and `.record-surface` and `.guided-suggestion-head` became resolvable **and passing**.
  Corroboration: **Linux already counted 8** — the wider Linux face had made the same node measurable
  long before this slice.
- `.record-file` (`evidence@tablet-768x1024`, 70 → 71). It previously hung **105.3px outside**
  `.record-context`; containing it made it measurable, and it fails.

The third, `settings-explorer@mobile-375x812` 55 → 54, is a genuine improvement, **lowered** rather
than left stale — a stale number would re-admit the defect.

## 4A. The three deferred correctness defects, defined

Previously these were named in §2.4 with no definition anywhere in the repository, which made them
unactionable and — under §7's verdict rule — a permanent baseline blocker. Defined here.

**D1 — cached validator hands every caller the same mutable schema.**
`src/isaac_records/official.py:30-39`. `_validator_for` is `@lru_cache`d and returns **one shared
`Draft202012Validator`** whose `.schema` dict is mutable in place by any in-process caller.
Reproduced: mutating the cached `record_type` enum makes `validate_official` return `ok: True` for a
bogus value, while `schema_fingerprint` still reports the pristine on-disk digest — so
`GET /api/runtime/database/recon` would report `authority.stable: true` and be wrong.
**Latent, not live:** no current caller mutates it (`rg` over `src/`, `apps/api/`, `scripts/`,
`tests/` finds no `.schema` mutation), and `GET /api/schema` (`routes.py:2972`) does a fresh
`json.loads`, so it is not reachable over HTTP. Severity: high if ever triggered, in the truth core.
`diagnostics.py:56-61` and `:199-206` currently document this as an accepted live caveat — that copy
becomes false in the honest direction once fixed, and must be updated in the same slice.

**D2 — recon vocabulary anchor can diverge from the validating schema.**
`apps/api/isaac_api/db_recon.py:372-373`. The `lru_cache` **is** correctly keyed on its argument (the
prior "M8" note mis-stated this). The real defect is that five internal call sites hardcode the
module-level `REPO_ROOT` (`:460`, `:770`, `:841`, `:882`, `:964`) while `run_recon(root=X)` forwards
`X` to validation — so `run_recon` with a non-default root would validate against schema X and mask
with vocabulary from `REPO_ROOT`. **Unreachable today** (no caller passes a non-default root) and it
**cannot leak a scientific value** — worst case is an internally inconsistent report. Severity: low;
a consistency/honesty defect, not a data-leak defect. The cache also lacks the mtime component that
`official.py` has.

**D3 — `POST /api/uploads` 403 description overclaims exclusivity.**
`apps/api/isaac_api/routes.py:2046-2078`. The 403 description asserts it is "the only outcome" while
`_R_UNAUTHORIZED` also declares a 401 on the same operation. The endpoint itself is correctly
fail-closed; the *description* is the defect. Fixing it moves the OpenAPI character total, which is
why it was deferred out of Slice 2A.

**All three were fixed in PR #30 (merge `91b74f8`).** Exported-record behavior and official schema
compliance are unchanged, proven by identical validate / diagnose / export hashes — including the
schema digest and the evidence sidecar — across every committed fixture, old implementation vs new.
Seven mutation tests were each observed failing on revert, independently by implementer and reviewer.

One correction worth carrying forward, because it was nearly shipped as a false guarantee: the new
cache key `(path, st_mtime_ns, st_size)` is a **heuristic, not content identity**. A replacement
written in the same nanosecond tick *and* at the same byte length is still served from the stale
entry. It is strictly stronger than the float `st_mtime` it replaced, and closing the remaining gap
would mean hashing the schema on every call — the exact cost the cache exists to avoid. The
docstrings now state the limit rather than the guarantee.

## 5. External gates — exact questions

| # | Gate | Owner | Exact question / action | Effect if unanswered |
|---|---|---|---|---|
| G1 | Hosted rollout + recon verification | **Krish** | Run [`docs/hosted-qa-checklist.md`](../../hosted-qa-checklist.md) Part 1 against `/krish` while signed in; paste back the sanitized JSON | Blocks Phase 1, Phase 2, and any claim that Slice 2A works |
| G2 | Per-record visibility decision | **Dean** | "May the hosted app display per-record fields from `metadata_assistant` — titles, scientific values, evidence, full JSON — and if so to which audience and at what granularity?" | Real-record functionality stays absent; baseline can still complete without it |
| G3 | Aggregates shipped in `v0.0.32` that Dean did not enumerate — **now withdrawn** | **Dean** | "Image `v0.0.32` returned **five** aggregates beyond your enumerated list: `by_instance_path`, `distinct_structural_signatures`, `total_link_count`, `dangling_link_count`, `vocabulary_term_count`. They are record-derived structural facts; none emits a value, title or id. **All five have been withdrawn** from the response and are named in `dataset.withheld_pending_visibility_decision`. Were any within what you intended, and may they be restored? Separately: `by_rule_family` and `by_schema_path` are **retained** because the public vendored schema produces them — do you agree, given either can report a count of 1 against a ~30-row table?" | Nothing further is served; the withdrawal stands. The five **were** live in `v0.0.32` and that is not undone. Also covers any drift §4.1's retained taxonomy cannot classify |
| G4 | Responsive / 200%-zoom human sign-off | **Krish** | [`docs/hosted-qa-checklist.md`](../../hosted-qa-checklist.md) Part 2 — 4 viewports + real 200% zoom. Automated coverage runs locally only, **and for 200% it is a viewport-halving model of zoom rather than zoom itself** — probed directly, Chromium exposes no automation surface for its own zoom control at all. This gate is not closable by any amount of further automation | Quality row stays open |
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

**Attribution must be per-row, not a blanket sweep.** As of this writing every row in §2.1, §2.2 and
§2.3 that is marked baseline-required reads `Runtime-verified: no`, so a single wave of the hand at G1 would let "Complete With
External Blockers" describe a state in which **nothing whatsoever has been observed running**. That
label is generous enough already; it must not also be cheap. A row may be attributed to G1 only if
G1's checklist actually covers that row. If the hosted checklist does not exercise a capability, the
honest status is "not verified, and not covered by any open gate either" — which is a gap in this
matrix, not a pass.

A corollary worth stating because it is load-bearing: Dean's guide warns at `:160-162` that anything
behind the "DB configured" switch **goes live on the next image roll**. Combined with §0's finding
that `v0.0.32` emitted five aggregates Dean did not enumerate, the first hosted observation of
`/api/runtime/database/recon` will be the first time *anyone* sees what the remaining aggregates
actually contain. G1 is not a formality.

### 7.1 The status labels, defined

Three labels, in decreasing strength. They are defined here so that the verdict in §7.2 is a
checkable claim rather than a mood.

| Label | Condition |
|---|---|
| **Baseline Complete** | Every `Baseline required: yes` row is `done` **and** runtime-verified. Unavailable while G1 is open, by the rule above. |
| **Complete With External Blockers** | Every `Baseline required: yes` row is either `done` **and** runtime-verified, **or** attributed **per-row** to a named external owner in §5 whose gate actually covers that row. Requires that the code being attributed is the code that will run — i.e. it is in a published image and no un-merged, un-published change is load-bearing for the claim. |
| **Baseline Code-Complete, Runtime Unverified** *(new, defined 2026-07-31)* | Every `Baseline required: yes` row is `done` **in the repository** and green under the project's own verification (tests, typecheck, build, drift gates, browser/a11y suite), **and** every remaining gap is either an external gate in §5 or the absence of a runtime observation. **Nothing in the deployed system has been observed.** This label makes no claim about `/krish` whatsoever. |

**Why the third label exists rather than stretching the second.** "Complete With External Blockers"
carries an implicit promise that what remains is *only* somebody else's decision. That is not the
present state: some of the code the claim rests on has not been published in any image, so there is
also a step **we** still owe. Conflating the two would let a self-owned gap hide inside an
externally-owned label. §7's own warning — that the label "is generous enough already; it must not
also be cheap" — is what forced this distinction.

### 7.2 The verdict, as of 2026-07-31

> ## Baseline Code-Complete, Runtime Unverified

Neither stronger label is available, and here is exactly why each fails, so that no future session
has to re-derive it:

**Why not plain "Baseline Complete":**

1. **G1 is open.** No `Baseline required: yes` row anywhere in §2.1, §2.2 or §2.3 is
   runtime-verified. The rule in §7 forbids plain Complete while G1 is open, without exception.

**Why not "Complete With External Blockers":**

2. **The final runtime code is not in any published image.** The closure slice — the A1/A2
   accessibility fixes and the G3 narrowing of the `dataset` block — is **not merged** at the time of
   writing. Every image that exists (`v0.0.32`–`v0.0.37`) predates it. A label whose remaining work
   is "external only" cannot be applied while an un-merged, un-published change is load-bearing for
   the claim.
3. **The hosted SHA is unknown.** `GET /krish/api/health` returned **HTTP 302** to the Authentik
   edge. Which image is running was not observed. Worse for attribution: the cluster's
   image-selection policy is **UNDETERMINED** — no Flux `ImagePolicy`/`ImageUpdateAutomation`
   manifest exists in this repository — so it cannot even be *inferred* which tag would be selected.
   That is not a per-row attribution to a named owner; it is an unknown.
4. **G3 is open.** The five aggregates were withdrawn, but the question to Dean is unanswered, and
   five of them **were served in a published image**. Withdrawal narrows the exposure; it does not
   resolve the gate.
5. **The real database has never been contacted. No scan has ever run.** Every §2.2 row — every gate,
   every tripwire, every aggregate — is verified by tests against fakes and by static reading of the
   code. Not one has executed against the actual database even once. Attributing all of §2.2 to G1
   is exactly the "single wave of the hand" §7 prohibits.
6. **G4 is open, and it is not automatable.** Real `Cmd`/`Ctrl`-`+` zoom sign-off has no automation
   surface in Chromium at all. It is a genuine external gate and *is* correctly attributable — it is
   listed here for completeness, not as an argument against the label.

Items 2, 3 and 5 are the decisive ones: 2 is work **we** still owe, and 3 and 5 are simply unknowns.
Only items 4 and 6 are clean external attributions.

**What this verdict does NOT say.** It does not say the deployment is healthy, degraded, rolled,
stale, or anything else. **No hosted rollout has been observed by this project at any point.** Any
future sentence combining "baseline" with a claim about `/krish` requires the G1 report as its
evidence, and must cite it.

**What would move this to "Complete With External Blockers":** merge and publish the closure image;
Krish runs [`docs/hosted-qa-checklist.md`](../../hosted-qa-checklist.md) Part 1 and confirms `commit`
matches the closure merge SHA; the recon endpoint returns a report (`ok` **or** a named refusal —
both are results); §2.2 rows are then attributed **per-row** to what that report actually exercised,
and any row it does not exercise is recorded as "not verified, and not covered by any open gate
either" rather than swept in. G2, G3 and G4 may remain open under that label; G1 may not.
