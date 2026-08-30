# ISAAC Baseline Completion Matrix

**Created:** 2026-07-31 · **Status:** LIVE — this is the authoritative definition of "baseline" for
ISAAC. Update it in the same PR as any slice that changes a row.

> ## Verdict: **Baseline Code-Complete, Runtime Unverified**
>
> Defined in **§7.1**, justified line by line in **§7.2**.
>
> ### Correction history for this block — read both entries; the second supersedes the first
>
> This callout has been corrected twice in one day, in opposite directions. Both entries are kept,
> because a verdict whose stated grounds change without notice is not checkable — and that principle
> cuts in both directions, including against a correction that over-corrects.
>
> #### Entry 1 (2026-08-01, earlier): reconciled DOWN — **now itself superseded**
>
> A revision added by docs-only commit `7e9a387` (1 file, +126/−7, **no data artifact**) asserted that
> three original grounds for the verdict were "now false" — that hosted `/krish/api/health` **was
> observed** reporting `ceea656`, and that the Slice 2A reconnaissance **has run** against the real
> database, reporting no leaks and zero schema drift (**30/30**).
>
> A later revision **WITHDREW** the second and third of those as "unsupported", on the grounds that no
> artifact existed and that "the evidence runs **8 statements to 1**" against them.
>
> **That withdrawal was methodologically wrong, and is itself now withdrawn.** Its two arguments do not
> survive the dating check that was never performed on them:
>
> - **The "8 statements" were pre-run status markers, not post-run observations.** Every one of them
>   was last written at or before `a911b8c` (2026-07-31 18:17:27 −0700), which `git merge-base
>   --is-ancestor a911b8c ceea656` confirms is an **ancestor of `ceea656`** — the merge that became the
>   very image `v0.0.38` the scan was run against, cut 41 minutes later at 18:58:48. Not one of them has
>   been updated since. The most-cited, the `db_recon.py:19-21` docstring *"this module has **never been
>   run against any database**"*, was written in `e7fd755` at 2026-07-31 04:27:45 −0700 — about **21
>   hours before** the run (`git log -1 --format='%h %ad' --date=iso -S 'never been run against any
>   database' -- apps/api/isaac_api/db_recon.py`). Citing an unmaintained pre-run status marker as
>   evidence that the run did not happen is circular: it says only that nobody had edited the file.
> - **"No artifact" was guaranteed in advance by the design, so it discriminates nothing.** The endpoint
>   holds its result in **process memory only** — a deepcopy under a TTL lock (`routes.py` ~3698-3721),
>   discarded on pod restart, never written to disk. "No artifact exists" was going to be true whether
>   or not the scan ran. Treating a designed-in absence as counter-evidence inverts it.
>
> #### Entry 2 (2026-08-01, current): the established status
>
> | Sub-claim | Status |
> |---|---|
> | `ceea656` → image `v0.0.38`; `d7010f9` → image `v0.0.39` | **VERIFIED.** `git rev-list -n1` on each tag; both tagged by `github-actions`; `Build and Push to GHCR` run `30692848940` on `d7010f9` succeeded. This is CI's record of what it pushed, **not** a registry read |
> | "the final runtime code is not yet in any published image" | **FALSE, and struck.** The responsive remediation is in `v0.0.39` |
> | "hosted `/krish/api/health` was observed reporting `ceea656`" | **OPERATOR TESTIMONY — accepted, not independently re-checkable.** Recorded in `7e9a387`; the hosted edge is not reachable from this environment, so no agent can confirm or refute it |
> | "the reconnaissance has run … 30/30, no leaks" | **OPERATOR TESTIMONY — accepted, not independently re-checkable.** See the field-level corroboration below |
>
> **The status, stated once and to be reproduced verbatim wherever this comes up:**
>
> > The deployed pod contacted the database at least once. The scan was observed by Krish in an
> > authenticated session against image `v0.0.38` (merge `ceea656`), and its result — no leaks, all four
> > frozen allowlists matched, zero schema drift, 30/30 — is **authenticated operator testimony, dated
> > and release-tagged, with no committed artifact because the endpoint is designed to produce none.**
> > The scanning logic and the schema are unchanged at HEAD, so the result still describes the current
> > release. It is **not** "verified": it is testimony, not a re-checkable record. It is equally **not**
> > "never happened".
>
> **What raises this above a bare assertion.** Krish has since independently restated the result at
> **field level**, and the fields map one-to-one onto `_DB_RECON_INTEGRITY_KEYS`
> (`apps/api/isaac_api/routes.py:3175-3187`): thirty rows before and after (`rows_before` /
> `rows_after`), zero rows modified (`rows_modified`), zero DML and zero DDL statements issued
> (`dml_statements_issued` / `ddl_statements_issued`), a full-schema fingerprint match
> (`full_schema_fingerprint_match`), thirty records passing schema v1.05, zero validation issues, and no
> prohibited response content. **Commit `7e9a387` recorded none of those six integrity field names** —
> `git show 7e9a387 | grep -E 'rows_before|rows_after|rows_modified|full_schema_fingerprint_match|dml_statements_issued|ddl_statements_issued'`
> returns nothing — and they appear in no other committed document. Detail that exists in no document
> can only come from having seen a response body.
>
> **No rerun is warranted, and the earlier result is not stale.**
> `git diff --stat ceea656..7a9f15d -- apps/api/isaac_api/db_recon.py schema/isaac_record_v1.json src/isaac_records/`
> is **empty** — those paths are byte-identical — and
> `git diff ceea656..7a9f15d -- apps/api/isaac_api/routes.py | grep -c '_DB_RECON'` returns **0**. The
> scanning logic, the schema it validates against, and the response projection are all unchanged; only
> `app_commit` in the response would differ.
>
> **The distinction to hold, everywhere.** *"No database connection was opened during this discovery
> session"* is **true** and must be preserved. *"The deployed database has never been contacted"* is
> **false as written** and must not be repeated.
>
> **The verdict itself stands, on these grounds.** The scan result is testimony rather than a
> re-checkable artifact, and the hosted state is unobserved *from here*; **G3** is open; and real
> **200% browser-zoom sign-off** is open and is not automatable — §3C's `zoom-200` project is the
> layout-level *equivalent* of 200%, never the browser's own zoom command. Plain **Baseline Complete**
> and **Complete With External Blockers** remain unavailable, for the reasons in §7.2. This verdict
> makes **no claim** about the *current* state of `/krish`; the testimony is point-in-time and
> release-tagged to `v0.0.38`. **G1 is narrowed, not closed — see §5.**

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
merged SHA. **No hosted rollout had been observed at the time this paragraph was written** (last
edited `a911b8c`, 2026-07-31 18:17:27 −0700). Superseded 2026-08-01: a rollout of `v0.0.38` and a
reconnaissance run against it were subsequently observed by Krish in an authenticated session and are
recorded as operator testimony in §0, Entry 2. Kept as written so the timeline stays legible — see G1.

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

**State at `d7010f9` (2026-08-01).** The block above is a **dated historical** measurement at
`610540e` and is deliberately left intact. These are the current numbers, each re-measured in this
session with the command quoted. Note the platform split — it is real, not a discrepancy:

| Suite | Result | Command / source |
|---|---|---|
| Frontend | **2206 passed, 99 files** | `cd apps/web && npm test` (local) — identical on Linux CI run `30692848942` |
| TypeScript | exit 0 | `cd apps/web && npx tsc -b` |
| End-to-end / a11y | **591 passed, 49 skipped** of **640 tests in 11 files** | Linux CI run `30692848942`, job *browser accessibility and responsive baseline*; `npx playwright test --list` for the total |
| Backend | **1811 passed, 3 skipped** on **Linux CI**; **1814 passed** locally on **macOS** | CI run `30692848942` / `.venv/bin/pytest -q -p no:cacheprovider` |
| Snapshot drift | **ok, no drift** (both artifacts) | `build_memory_snapshot.py … --detail-out --check` |
| CI on `d7010f9` | all three jobs **success**; `Build and Push to GHCR` (`30692848940`) **success** → `v0.0.39` | `gh run view` |

The backend split (1811 Linux / 1814 macOS) is **three platform-skipped tests**, not three failures.
Quote the platform whenever quoting the number; a bare "1814" is a macOS figure and CI will disagree
with it.

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
it: that is **code reading, not a runtime observation**. (Written when the scan had not yet run.
Corrected 2026-08-01: it has since run once — §0, Entry 2 — but the result was **testimony, not a
captured body**, so the masking still has no runtime observation behind it and this caveat stands
unchanged in substance.)

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
| Image publication (every push to `main`) | `.github/workflows/build-push.yaml` | **yes** | done — `v0.0.33`–`v0.0.39` all built and pushed by successful CI runs (`v0.0.38`→`ceea656`, `v0.0.39`→`d7010f9`); no path filters, so docs-only merges publish too | no | n/a | **no** — CI's record of what it pushed, **not** a registry read (`ghcr.io` anon token failed; `gh api /orgs/ISAAC-DOE/packages` → 403) | orch | — |
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
| Backend suite | **yes** | done — **1811 passed, 3 skipped** on Linux CI (`30692848942`); **1814 passed** locally on macOS. The split is three platform-skipped tests, not failures — always quote the platform | orch | — |
| Frontend suite | **yes** | done — **2206 passed / 99 files** (`cd apps/web && npm test`), same on Linux CI, but see F1 | orch | — |
| TypeScript build | **yes** | done | orch | — |
| Production build | **yes** | done | orch | — |
| Docker build + smoke | **yes** | done (CI) | orch | — |
| Snapshot drift gate (both artifacts) | **yes** | done | orch | — |
| Secret / leak / real-data scans | **yes** | done | orch | — |
| Copy-truthfulness guards (frontend + backend, parity-enforced) | **yes** | done | orch | — |
| **Real-browser test baseline** | **yes** | **done** — Playwright/Chromium, PR #32 (`c36053d`); **591 passed, 49 skipped** of 640 tests in 11 files on **Linux CI** (`30692848942`, `d7010f9`); Linux CI is the authority | orch | — |
| **Accessibility engine baseline** | **yes** | **done** — axe-core, 18 surfaces × 5 projects, count-based baseline. **Tightened to 1,628 darwin / 1,634 linux** (from 1,974 / 1,980) when A1 and A2 were fixed and their entries deleted. **darwin measured locally; linux MEASURED by CI** (run `30677607861` on `a911b8c` — the three deleted entries assert ZERO nodes and passed under Linux font metrics), so 1,634 is validated, not arithmetic | orch | — |
| **Responsive baseline (4 viewports)** | **yes** | **done** — 1280×800, 1024×768, 768×1024, 375×812 | orch | — |
| **200% zoom — layout-level model, automated** | **yes** | **done as a model, not as the thing.** The `zoom-200` project is `{640×400, DPR 2}`, asserted not assumed. Probed directly: DPR contributes **nothing** to CSS layout (DPR 2 and DPR 1 measured byte-identically), and **no CDP method, launch flag or Playwright API can drive Chrome's own zoom control** — so viewport-halving is the correct *and only available* model | orch | — |
| **Real browser zoom at 200% (`Cmd`/`Ctrl`-`+`)** | **yes** | **OPEN — human only.** Not automatable in Chromium at all; not a deferral of effort | **Krish** | **G4**; automation cannot close it |
| Accessibility defects found (A1–A8 below) | **yes** — recorded | **partial** — **A1, A2 (both critical), A4 and A5 FIXED**, baseline entries deleted so a regression fails as `new`; **A6 HALF fixed** (~~"and A6 FIXED"~~ — corrected 2026-08-27 from CI run 33025558592: the search half closed, 7 nodes remain and the entry is restored at 1); **A3, A7 and A8 OPEN and deliberately deferred**, each still baselined at an exact node count | orch | §3B. A3 is a PALETTE DECISION and is the owner's, not a slice's (`styles/tokens.css:3-5`) — though one `.section-tab` USAGE of a low token moved on 2026-08-26, −378 nodes across 119 cells, transcribed from CI; A7/A8 are the record-chrome reflow slice. Two a11y findings remain open (A3 serious, A6 residue moderate), the 2 open layout findings are unrated |
| Cached-validator correctness — D1 | **yes** | **done** — PR #30, merge `91b74f8` | orch | — |
| Vocabulary-cache keying correctness — D2 | **yes** | **done** — PR #30 | orch | — |
| `POST /api/uploads` OpenAPI description accuracy — D3 | **yes** | **done** — PR #30 | orch | — |
| Performance baseline (measured) | **yes** (measurement) | **done** — measured and recorded in [`2026-07-31-graph-and-performance-baseline.md`](2026-07-31-graph-and-performance-baseline.md) Part 2 (§2.1–2.5). This row read `absent` while its own companion document held the measurement | orch | — |
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
- ~~Any database write, migration, or app-specific table — no baseline capability needs one.~~
  **SUPERSEDED, twice, and struck rather than deleted so the change of scope is visible.** (a) The
  project owner lifted the blanket prohibition on 2026-08-07, narrowly, for durable Create
  Experiment persistence in app-owned tables (`CLAUDE.md` §15). (b) Migration `0001_experiments`
  was **applied to the hosted database by Dean on 2026-08-09**
  ([evidence](../../evidence/hosted-0001-verification-2026-08-09.md)); the deployment now reports
  `experiment_storage: {backend: "postgres", durable: true, state: "durable"}`.
  **The original sentence's own claim remains true and is the reason it is not simply replaced:**
  *no baseline capability needs one*. Durable persistence is still **not** a baseline row, and
  nothing here promotes it into one — what changed is that it exists, not that baseline requires
  it. `0002` remains unapplied and unauthorized for hosted application.
- Upload / ingestion. The endpoint stays fail-closed.
- ~~Durable persistence beyond the pod.~~ **Same supersession as the bullet above** — it is no
  longer absent, and it is still not baseline. Note what it does *not* extend to: **pod-restart
  durability has not been measured** (nobody restarted the pod), and exported artifact files still
  live only in the workspace directory (`docs/create-experiment-persistence.md` §5).
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

1. **Minimum cell size.** The *documented seed* is **30 rows** (`DOCUMENTED_SEED_ROWS`, `db_recon.py:133`).
   ~~the actual row count is **unobserved** — the scan has never run~~ **Corrected 2026-08-01:** the
   scan has run once and Krish's testimony reports `rows_before` and `rows_after` both **30**, matching
   the documented seed (§0, Entry 2). Treat that as testimony, not a measurement this document can
   re-check; `seed_count_matches` exists precisely so the comparison is made in-pod either way. At that
   order of magnitude a count of `1` at a specific path is a
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

**REFRAMED 2026-08-01 — F1 is not a flaky test file. It is a suite-wide load sensitivity.**
The framing above invites someone to "fix" one file and declare the class closed. It cannot be one
file: `graph-real-artifact.test.tsx` contains **three** tests, so 49 failures were necessarily
suite-wide. The cause was isolated by elimination, with measurements:

- **Artifact loading cost is excluded.** One-off timing of the real file: 493,745 chars,
  `readFileSync` **0.858 ms**, `JSON.parse` **1.853 ms** — **2.7 ms of a 5,000 ms budget (0.05%)**.
- **Shared state is excluded** — `setup.ts:6-16` runs `cleanup()`, `clearAllSessions()` and
  `sessionStorage.clear()` after every test; the file adds `vi.unstubAllGlobals()`.
- **Product and test nondeterminism are excluded** — `selectDenseFile` sorts `(-count, path)`, the
  layout is seeded, and every assertion is a bound or a count derived from the artifact.
- **The actual cause is process scheduling under contention.** The expensive test is a *serial chain*
  of ~10 render-then-poll steps, each `waitFor` polling at 50 ms. Four isolated runs on a moderately
  loaded machine (load 8–13) measured it at **1406–1587 ms** — ~31% of budget, ≈3.2× headroom. At the
  load average 97 recorded above, that headroom is gone. `vite.config.ts` sets no `testTimeout` and no
  `pool`, so **every** frontend test shares one undifferentiated 5 s wall clock across 10 forks.

**No code fix is recommended, and raising the timeout is explicitly not one.** Splitting the loop into
its own `it()` is a timeout raise in disguise; sharing the render via `beforeAll` breaks the isolation
`setup.ts` deliberately enforces; shrinking the fixture defeats the test's stated purpose. Containment
instead: never run vitest alongside the Playwright suite; treat a lone `Test timed out in 5000ms` as
suspect until reproduced in isolation on a quiet machine; **CI is the authority** for the frontend
count and is green at `d7010f9` (2206 / 99); and if the class ever reaches CI, reduce fork concurrency
rather than raising a timeout. The same class is already documented for the Playwright probes at
`docs/browser-accessibility-testing.md:466-476`.

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
| **A3** | `color-contrast` | **serious** | **OPEN — deferred** | 1,610 nodes, every surface. **Three causes, not one**: ~~`--text-disabled #c0c8d0` rendered as Evidence line numbers at **1.56:1**~~; genuinely low tokens; and **five `opacity` composites of tokens that pass at full strength** — darkening tokens will not fix those. **The struck clause is FIXED as of 2026-08-29** — `evidence.css`'s `.preview-line .ln` asks for `--text-slate` #5b6b7d instead, 1.49–1.69:1 → 4.81–5.46:1 across the four grounds it is drawn on (the worst is the `--cited-line-bg` highlight at **1.49:1**, worse than the 1.56:1 recorded here and previously unmeasured). **No token value changed**, so this is a *usage* correction like `.section-tab` and **A3 REMAINS OPEN** — it is still the owner's palette decision, and cause (3) in particular is unfixable by darkening anything. Effect: `evidence@*` −22 nodes on all seven scan projects. Decision record: `docs/browser-accessibility-testing.md` §6.1a |
| **A4** | `scrollable-region-focusable` | **serious** | **FIXED 2026-08-26** | was 6 pairs once the narrow sweep landed (`evidence` desktop/mobile/320/390, `settings-api` mobile/320). `div.preview-lines.scroll-x` and `pre.api-samples-code` now carry `tabIndex={0}` + `role="group"` + `aria-label`, following `.rc-tablewrap`. Baseline entry DELETED, **−6 nodes on both platforms** |
| **A5** | `page-has-heading-one` | moderate | **FIXED 2026-08-26** | was 7 pairs. `/load` renders `<h1 class="sr-only">Load Materials</h1>`; `expectH1: false` dropped from `e2e/surfaces.ts`. `sr-only` text is not `isVisibleOnScreen`, so no `load@*` `color-contrast` count moves. Baseline entry DELETED, **−7 nodes on both platforms** |
| **A6** | `landmark-unique` | moderate | **FIXED — search half 2026-08-26, region half 2026-08-29** ~~HALF FIXED 2026-08-26 — 7 nodes still OPEN~~ ~~FIXED 2026-08-26~~ | Two unnamed `role="search"` landmarks on Endpoint Explorer. The `aria-label` added for A1 sat on the `<button>`, **not** on the `role="search"` wrapper `<div>`. Both landmarks now carry their own `aria-label` — "Site search" (`SearchDialog.tsx`) and "Endpoint search" (`settings/ApiDocs.tsx`). ~~"Its baseline entry — 14 nodes once the narrow sweep landed — is DELETED, −14 nodes on both platforms"~~ — **CORRECTED 2026-08-27 from CI run 33025558592.** Only ONE of the two nodes per pair was a search landmark. The other is a duplicate `region`: `/settings?tab=explorer` renders **two regions both named "Endpoint Explorer"**, the `SettingsCard` wrapper (`SettingsPage.tsx:326`) and `<section class="api-explorer">` (`settings/ApiDocs.tsx:357`). PRE-EXISTING, not a regression — the pre-fix `targetPattern` `^(\.card\|\.topbar-search-region)$` names two different elements, so the old `note` was simply wrong about the second. Entry **RESTORED at 1 × 7 pairs**, net **−7 nodes on both platforms**, not −14. ~~One-line fix available (distinct name, or drop the inner section's `aria-labelledby`); not taken because it changes product DOM and needs a browser run to confirm~~ — **TAKEN 2026-08-29, second option, and the browser run happened.** `settings/ApiDocs.tsx`'s `<section class="api-explorer">` now carries no `aria-labelledby`, so it is not a landmark; the `<h3>` is untouched. The shared `SettingsCard` was deliberately left alone. A local macOS sweep reported `improved:landmark-unique` on all seven pairs and moved no other rule; the baseline entry is **DELETED, −7 nodes on both columns**. The linux half is asserted, not measured — a duplicated accessible *name* is a DOM/ARIA fact with no text measurement in it. Pinned in the fast job by `src/__tests__/a11y-landmarks-headings-and-tabs.test.tsx` |
| **A7** | LAYOUT-01 | — | **FIXED 2026-08-29 (darwin measured; linux CI round-trip pending)** ~~OPEN — deferred~~ | Record StatusBar did not reflow: 575px of content in a 353px box at 375px, clipped and overlapping. **Fix:** `src/components/chrome.css`, inside the existing `@media (max-width: 1024px)` block — `min-height: 52px` + `flex-wrap: wrap` in place of a hard `height: 52px` nowrap row, so the segments reflow onto further rows. **Nothing hidden, nothing truncated:** every segment is a trust signal. **MEASURED:** all 20 recorded darwin offenders across 8 keys not-fired in one run, no new clipped or occluded finding. It also closed **four LAYOUT-04 keys** — that entry's own cause (a) is "`div.screen-card` inherits the non-reflowing StatusBar's width". Linux lists retained (a single `.statusbar-seg` is itself a nowrap row a wider face could overrun) |
| **A8** | LAYOUT-02 | — | **OPEN — Linux only, ONE instance** | ~~Record-context chip clipped: `chip-draft` on Evidence (macOS+Linux) and `chip-exported` on Export Readiness (**Linux only** — SF Pro hid it). One `.record-context` fix closes both~~ — **CORRECTED 2026-08-29: the Evidence instance has not existed since 2026-08-01** and this row asserted it for four weeks. `e2e/layout-baseline.ts`'s LAYOUT-02 holds exactly one key, `export-readiness-done@mobile-375x812`, whose darwin list is `[]` (a measurement — the C1/I4 change gave `.record-context` `overflow: hidden` at every width, and the suite's own staleness signal named the Evidence instance not-fired). What remains is `chip-exported` running 315→372 in a container ending at 365, Linux only. **2026-08-29:** `chrome.css` now states the crumb's shrink contract (`flex: none; max-width: 100%` on the chip, `flex: 0 1 auto` on `.record-surface`), making containment structural rather than font-dependent — but that is **NOT claimed as a measured fix**, because darwin already read `[]`. Only CI can retire the entry |

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
  copy, not markup. **A4 and A5 were closed on 2026-08-26; A6 was half closed** (~~"All three were
  closed"~~ — corrected 2026-08-27, see its row). The reasoning here is kept rather than deleted,
  because each concern was real and each shows in the fix: the new tab stops are unconditional and
  documented at the call site, `expectH1: false` went in the same change as the heading, and the two
  landmark names were chosen for distinctness after a first attempt that reused one string for two
  elements had to be withdrawn. **And A6's residue is the lesson this bullet did not anticipate:**
  the concern recorded here was about the two names being distinct, and they are — what was missed is
  that the entry had never been counting only those two elements. Its own `targetPattern` said so and
  its `note` did not, and the `note` was believed.
- **A7 / A8** are CSS reflow changes to shared record chrome, which move layout on **every** record
  surface at **every** viewport and would move axe counts on **both** platforms — one of which cannot
  be measured from a laptop at all (§6.1 of the browser/a11y doc). That is a slice with a CI
  round-trip in it, not a closure-slice add-on. **A7 WAS TAKEN AS EXACTLY THAT SLICE ON 2026-08-29,
  and one half of this reasoning was measured and did not hold.** The layout half was right: 20
  offenders across 8 keys moved, and four LAYOUT-04 keys moved with them. The a11y half was
  **wrong** — the reflow moved **no** `color-contrast` node on any record surface at any viewport,
  because wrapping changes which ROW a text node sits on and axe counts elements, not lines. Worth
  keeping, because the prediction was reasonable and the measurement is the only thing that settles
  it. The CI round-trip is still real and still outstanding, for the linux column.

**Baseline impact of leaving A3 and A8 open** (~~"A3, A6's residue, A7 and A8"~~ — corrected
2026-08-29: **A6's residue is closed and its entry deleted; A7 is fixed at source with only its
linux list awaiting a CI round-trip**. A4 and A5 are closed; the sentence used to read "A3–A8", was
corrected to "A4–A6 are closed", was corrected again on 2026-08-27 because A6 was then only half
closed, and is corrected a third time here — every correction kept rather than deleted so the
changes of status are visible): each remains enumerated in `e2e/a11y-baseline.ts` or
`e2e/layout-baseline.ts` at an exact per-`surface@project` node count, with an identity guard, and
the ratchet fails on `new`, `grew`, `improved`, `new-target` and `new-foreground`. Nothing is
suppressed and no axe rule is disabled. The debt is **measured and cannot silently grow** — which is
the property baseline actually requires.

**Do the open ones block baseline?** §7's rule says "no known Critical or Important findings". Both
**Critical** findings are now closed. The remaining findings are serious/moderate and unrated-layout,
they are pre-existing, and baseline work **discovered and documented them where nothing previously
measured them at all**. Going from no measurement to a ratcheted, per-node baseline is the
foundational improvement; leaving A3, A7 and A8 open is a known, owned, bounded debt with a named next slice
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
  over the StatusBar's honesty statement "hosted preview · no telemetry". 17 instances, on the four
  record routes only (`/record/:id`, `/complete`, `/evidence`, `/export` — Project Memory mounts the
  drawer but no StatusBar). Present **at rest**, no scrolling required: `.screen-card` is
  `min-height: calc(100vh - 32px)` so the 52px footer is pinned to the viewport bottom at every
  scroll offset, and the trigger sits at `bottom: 16px`. Survives `scrollIntoView`.
  **CORRECTED 2026-08-01:** an earlier revision said the trigger paints "**completely**" over the
  label, citing "visible-area ratio 1.00". That inference was wrong — `ratio` compares `visibleRect`
  to `getBoundingClientRect`, and `visibleRect` intersects only clipping/scrolling ancestors and the
  viewport (`helpers/layout.ts:821-843`), so it measures **clipping, not occlusion**. 1.00 means
  "fully laid out and unclipped". The occlusion measure is the 5-point hit test, whose own figure is
  "**3 to 5** of 5". Coverage is therefore **partial-to-total depending on surface**; the reliably
  lost part is the *trailing* half — the words carrying the telemetry claim.
  **No interactive control is blocked** — a measured negative, not an assumption: `SEL_INTERACTIVE`
  is scanned on every surface and the e2e suite is green at `d7010f9` (591 passed), and the StatusBar
  contains zero focusable elements. **No keyboard impact at rest** — the drawer's focus trap is
  guarded by `if (!open) return`. The disclosure's *environment* half is duplicated in persistent
  chrome (`LeftNav.tsx:46`), but the *telemetry* half exists only on Settings → Data & Privacy and
  the Statistics `NoAnalytics` block — so the badge is the only always-on carrier of "no telemetry".
  **Severity: Important**, because the repo's own probe lists `.statusbar-right` in
  `SEL_CRITICAL_LABELS` as a label "whose disappearance changes what the user believes about the
  system". Pre-existence proven by re-running the probe against the stashed CSS.
  **Disposition: fold into one "record chrome reflow" slice with A7/LAYOUT-01, A8/LAYOUT-02 and
  LAYOUT-04 Cause A** — all four name `src/components/chrome.css` as their fix address, and fixing
  the trigger offset alone treats the symptom of the non-reflowing footer. Not fix-now: it moves
  overlap geometry, which §3C shows moves axe counts on **both** platforms, and Linux is the
  authority and is unmeasurable from a laptop.
- **LAYOUT-04** — nested horizontal overflow, 16 keys / **20 instances** (darwin), across `evidence`,
  `record-detail`, `export-readiness`, `export-readiness-done`, `guided-completion`, `load`. The
  `/experiments` case that motivated the hardening is **absent** — it was fixed by I1, so it fails if
  it returns.

  **CORRECTED 2026-08-01: there are FOUR distinct root causes, not two.** Treating all 20 instances as
  one issue is what made this look unschedulable. Triaged:

  | Cause | Instances | Selector | Overflow behaviour | Severity | Disposition |
  |---|---|---|---|---|---|
  | **A** — `div.screen-card` inheriting the non-reflowing StatusBar | 10 — `record-detail`, `export-readiness`, `export-readiness-done` @320/375/390, `evidence`@320 | `div.screen-card < div.app` | `overflow: hidden` — **clips**, right ~222px of the footer lost with no ellipsis (`scrollWidth 575 vs clientWidth 353`) | **Important** | **Not independently fixable** — it *is* LAYOUT-01 seen from the overflow side. Ship with A7 |
  | **B** — a `main` region whose descendant exceeds the phone viewport | 6 — `export-readiness-done`@320/375 (B1), `guided-completion`@320 darwin / @375 **linux-only** (B2), `load`@320/375/390 (B3) | `main#main.screen-main.*` | `auto` — **scrolls**; content reachable but the page acquires a sideways gesture inside `main` | Minor | **B2 culprit known** (`span.upcoming-path`, 367 vs 364 — 3px, a font-metric boundary case; fix `.upcoming-label { min-width: 0; overflow-wrap: anywhere }` at `assistant.css:1598-1620`). **B1 and B3 have no recorded culprit** — see B-ANNOT |
  | **C** — an inner `section` that is itself a scroll container | 3 — `evidence`@320/375/390 | `section.preview` | `auto` — accidental two-axis scroller | Minor | **Smallest well-scoped item in the set.** Culprit recorded in the probe source: `h2.preview-prov-title` at 418, an `inline-flex` heading whose children cannot shrink (`evidence.css:198-205`). Fix: `flex-wrap: wrap` + `min-width: 0` |
  | **D** — `section.field-group` | 1 — `record-detail`@width-320 | `section.field-group` | `overflow: hidden` — **clips**. No scroll affordance, no ellipsis | Minor exposure, **Important failure mode** | Culprit not recorded. **Do not close LAYOUT-04 without knowing what this one loses** |

  **A mechanism this record previously omitted, and which changes the fix.** Per CSS Overflow, when one
  axis is non-`visible` the other computes to `auto`. `.screen-main { overflow-y: auto }` and
  `.preview { overflow-y: auto }` are therefore both silently **two-axis** scrollers, which is why
  `findOverflowingRegions` attributes findings to `main` rather than to the wide child.
  **Consequence: clamping the axis is the wrong repair** — `overflow-x: clip` would convert an
  unintended scroller into silent content loss. Fix the child's `min-width`/wrapping instead.

  **No allowance is proposed for any of A–D.** `layout-allowlist.ts:15-31` forbids tag, universal and
  subtree selectors and requires a class selector, an exhaustive surface list, a citation of the
  `src/**` line declaring the intent, and a statement of what the user can still do. An accidental
  two-axis scroller and an `overflow: hidden` clip are not "correct by design"; all four stay in
  `layout-baseline.ts` until fixed, which is where they already are.
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
| G1 | Hosted rollout + recon verification — **NARROWED 2026-08-01, not closed** | **Krish** | The substantive question is **answered by operator testimony** (§0, Entry 2): the scan ran against image `v0.0.38` (`ceea656`) with no leaks, all four frozen allowlists matched, zero schema drift, 30/30, and field-level integrity values that map one-to-one onto `_DB_RECON_INTEGRITY_KEYS`. **Slice 2A is therefore no longer unproven.** What G1 still requires is narrower and purely evidentiary: **paste the sanitized JSON back** so the result becomes a re-checkable artifact rather than testimony, per [`docs/hosted-qa-checklist.md`](../../hosted-qa-checklist.md) Part 1. A rerun is **not** required for correctness — `db_recon.py`, `schema/isaac_record_v1.json` and `src/isaac_records/` are byte-identical between `ceea656` and HEAD, and zero `_DB_RECON` lines changed in `routes.py` — so re-running merely re-obtains a body that can be captured. | Blocks any claim that a §2.2 row is **runtime-verified in the artifact sense**, and blocks the per-row attribution in §7.2. Does **not** any longer block the claim that Slice 2A works |
| G2 | Per-record visibility decision | **Dean** | "May the hosted app display per-record fields from `metadata_assistant` — titles, scientific values, evidence, full JSON — and if so to which audience and at what granularity?" | Real-record functionality stays absent; baseline can still complete without it |
| G3 | Aggregates shipped in `v0.0.32` that Dean did not enumerate — **now withdrawn** | **Dean** | "Image `v0.0.32` returned **five** aggregates beyond your enumerated list: `by_instance_path`, `distinct_structural_signatures`, `total_link_count`, `dangling_link_count`, `vocabulary_term_count`. They are record-derived structural facts; none emits a value, title or id. **All five have been withdrawn** from the response and are named in `dataset.withheld_pending_visibility_decision`. Were any within what you intended, and may they be restored? Separately: `by_rule_family` and `by_schema_path` are **retained** because the public vendored schema produces them. Sharpened 2026-08-01: there is **no minimum-cell-size suppression anywhere in the codebase** (`rg 'MIN_CELL|suppress'` over `db_recon.py` and `routes.py` → 0 matches), so both can report a count of 1 against a ~30-row table. And `by_rule_family` carries **two** measures per family, not one: `records_affected: 1` is strictly stronger than `error_count: 1` — it states that a *single* record accounts for every error in that family, and two such families can be differenced into a per-record failure *profile*. Do you accept both as-is, or should a floor apply?" | Nothing further is served; the withdrawal stands. The five **were** live in `v0.0.32` and that is not undone. Also covers any drift §4.1's retained taxonomy cannot classify |
| G4 | Responsive / 200%-zoom human sign-off | **Krish** | [`docs/hosted-qa-checklist.md`](../../hosted-qa-checklist.md) Part 2 — 4 viewports + real 200% zoom. Automated coverage runs locally only, **and for 200% it is a viewport-halving model of zoom rather than zoom itself** — probed directly, Chromium exposes no automation surface for its own zoom control at all. This gate is not closable by any amount of further automation | Quality row stays open |
| G5 | Personal-deploy retirement | **Krish** | Approve the disable-not-delete operation | Cosmetic; no functional effect |
| **G6** | **Personal data in the seeded records** *(new, 2026-08-01)* | **Dean** | "Do the 30 seeded records contain real personal identifiers in `data->'attribution'` — `uploaded_by`, `contributors[].email`, `contributors[].orcid`, `contributors[].name` — and does the G2 visibility decision cover **personal data** as distinct from scientific content?" | G2 as worded would not surface it. Nothing is currently exposed — the `dataset` projection is aggregate-only and `by_schema_path` reports *schema* locations, never instance values — so this is a gap in the **question**, not a live leak |
| ~~**G7**~~ | **Identity trust boundary** — **ANSWERED BY DEAN 2026-08-12, and the answer is not the reassuring one** | **Dean** → now **ISAAC engineering** | ~~The 15 questions in `identity-trust-contract.md` §7. The four that gate everything else…~~ **Answered:** the edge injects/overwrites exactly `X-authentik-username`, `-groups`, `-email`, `-name`, `-uid`, and **only those**; `X-authentik-entitlements` and `X-Isaac-Edge` remain **untrusted**; the **canonical principal is the username** and usernames are **not reassigned**; groups are `admin`/`researcher` and are authoritative **only for an edge-traversed request**; server-stamping the username for `uploaded_by`, Run overrides, submissions and revision rows is **authorized, provided identity was established through the trusted authentication boundary**; client-supplied username is never authoritative. **AND — the part that governs everything else — Dean RECONFIRMED the bypass:** the Service is a **plain ClusterIP with no NetworkPolicy**, so any in-cluster pod can reach the app directly and forge forwarded identity headers, and **`X-authentik-username`'s presence does NOT prove authenticated edge traversal.** Operator testimony about configuration, **not** an observation by this repository. | **The gate has MOVED, not closed.** What blocked it was an unanswered external question; what blocks it now is an **unbuilt trusted authentication boundary** — Dean named the pattern (trusted-edge for browser/UI traffic, independent Bearer validation for API/service traffic) and ISAAC has neither. **Still blocks per-actor attribution, roles and authorization**, and now blocks them on our own engineering rather than on Dean. **Nothing may be stamped until that boundary exists.** |

**Why G6 exists, stated so it is not read as alarm.** Chaining three documented facts: the seed is
*"the 30 earliest **real** records from production"* (guide `:23-24`); `data` holds the complete record
JSON *"written by the isaac-ai-ready-record portal against v1.05"* (`:114-116`); and v1.05's
`attribution.uploaded_by` is *"SERVER-STAMPED from the authenticated identity"*, with `contributors[]`
carrying `email`, `orcid`, `affiliation`, `name`. So those rows plausibly carry real SLAC personal
identifiers, and `Q_RECORDS_PAGE` pulls the whole `data` column into pod memory on every scan.

The dimension had never been named anywhere. Measured 2026-08-01, and **scoped precisely, because an
earlier draft of this paragraph over-claimed**: the search covers the three files that could have
named it, and deliberately **excludes this file**, which now discusses personal data in this very
entry and would otherwise self-falsify the command:

```
$ rg -n -i -e 'PII' -e 'personal data' -e 'personally identifiable' -e 'email' -e 'username' \
    apps/api/isaac_api/db_recon.py apps/api/isaac_api/routes.py docs/postgres-test-db-guide.md
(no output — 0 matches)
```

G2 is worded entirely around *"titles, scientific values, evidence, full JSON"*.

> **STATUS AFTER DEAN'S 2026-08-12 RESPONSE.** **G7 is answered** (row above) — and answered in a way
> that converts it from an external gate into an internal engineering prerequisite, so it is struck
> through in the `#` column but **not** removed. **G2 and G3 are UNTOUCHED and remain OPEN**: the
> response addressed neither per-record visibility nor the five withdrawn aggregates. **G6 is
> likewise unaddressed.** Applying a migration is not a visibility decision, and **silence on G2, G3
> and G6 must never be read as assent** — that is the exact misreading the G3 entry exists to record,
> since `v0.0.32` shipped five aggregates by assuming intent. G1, G4 and G5 are Krish's and are
> unaffected.
>
> **Separately, and outside this table:** Dean **deferred D1–D9** (AI/MCP/voice) with the
> recommendation to *"leave AI integration as future work rather than increasing scope at this
> point"*; the **project owner has elected to continue implementing** against deterministic fake
> providers. Neither fact touches G1–G7. See `docs/ai-integration-decision-packet.md`.

None of G1–G7 is resolvable by this agent. G1 and G4 require credentials the agent must not use; G2
and G3 require the database owner's decision; G5 requires account access the agent must not exercise;
G6 and G7 require the database owner and the infrastructure owner respectively.

**On G3-B, a position rather than a shrug.** No bucketing has been applied and none should be applied
unilaterally, for four reasons. (1) Bucketing destroys the signal Dean explicitly called useful —
*"Finding drift is a useful result … report it rather than working around it"*; over a 30-row seed a
floor of 3 or 5 collapses most of the taxonomy to `<5`, which is operationally indistinguishable from
"we did not classify it". (2) **The argument that justified withdrawing `by_instance_path` does not
transfer.** §4.3.1 says a count of 1 *"at a specific path"* is a per-record fact — and "path" there
means an **instance** path, which reveals that a specific *field* of a record is populated and wrong.
A schema path and a jsonschema keyword are facts about the **public vendored schema**; `error_count: 1`
at `properties/record_type/enum` names no field value, no title and no id, and no stored document had
to be read to produce the string. §4.2 is satisfied on its face. (3) §4.3's other two constraints are
already structurally satisfied — the operation takes no parameter, body or filter, and the two
breakdowns are independent 1-D lists never crossed with each other or with
`by_record_type`/`by_record_domain`. (4) Deciding it unilaterally would repeat the exact error G3
exists to record: `v0.0.32` shipped five aggregates by assuming intent one way; quietly coarsening two
schema-derived breakdowns would assume it the other way — and worse, would degrade the very output
Dean must look at in order to rule.

**Where the objection genuinely bites, conceded:** the `records_affected` × `error_count` pair is
reconstructible by arithmetic in a way a single measure is not, which is precisely §4.3's warning. The
G3 text now asks about that explicitly. **If Dean rules that a floor is required,** implement it at
*projection* time in `routes.py` only — never in `run_recon`, which must keep exact figures for the
out-of-image script — and emit a `suppressed_below` marker so the coarsening is auditable, mirroring
`withheld_pending_visibility_decision`.

---

## 6. Collaboration — deferred, with seams recorded

Collaboration is **not** baseline and nothing here authorizes building any part of it. The only
obligation baseline work carries is *not to foreclose it*. The seams that matter:

| Seam | What baseline must avoid |
|---|---|
| Record identity | Keep the ULID `record_id` the stable external key. Do not introduce a second, surface-local identifier that a future ownership model would have to reconcile. |
| Authorship / actor | The app currently has no concept of an actor. **Do not invent one** as a side effect of another feature — no implicit "current user" derived from Authentik headers. ~~because role mapping is an unmade decision (readiness plan §3)~~ **AMENDED 2026-08-12: the stated REASON is now partly obsolete, and the RULE is unchanged and if anything stronger.** Dean has answered role mapping (`admin`/`researcher`) and has **authorized** server-stamping the canonical Authentik username for `uploaded_by`, Run overrides, submissions and revision rows. But he authorized it **only for a request whose identity was established through the trusted authentication boundary** — and in the same response reconfirmed that the Service is a plain ClusterIP with no NetworkPolicy, so **a header's presence does not prove the request came through Authentik.** So "do not invent an actor" now rests on a *sharper* reason than an unmade decision: **an actor derived from an Authentik header today would be forgeable by any in-cluster caller.** Nothing may be stamped until ISAAC builds the boundary. See `docs/identity-trust-contract.md` §2 and §7 Q4/Q10/Q25. |
| Mutation history | `record_history` exists in the database schema but the app never writes it. Baseline stays read-only, so no write path can accidentally define a history semantics that a real review workflow would then inherit. |
| Evidence authority | The sidecar is **advisory and has no formal schema**. Do not strengthen its authority; a future reviewer-approval flow would need it to be authoritative, and quietly promoting it now would pre-decide that. |
| Workflow state | `derive_workflow` is **fully derived** from record state with no human-review step. Do not add a stored, mutable workflow status — that is the seam a review/approval feature would occupy. |

Recording these is the entire deliverable. Implementing any of them is out of scope.

### 6.1 What the 2026-08-01 collaboration investigation established

A read-only discovery pass (three parallel workstreams) was run against `d7010f9` to scope an
experiment-centered groups-and-collaboration phase. **No collaboration code was written.** Five facts
that change the shape of that phase, recorded here so they are not re-derived:

1. **Optimistic concurrency is already shipped — the seam is occupied, correctly.** `version_contract.py`
   surfaces `{rev, updated_utc, version}`; `If-Match` is **mandatory** (428 when absent, the
   one-release grace retired); a mismatch returns **412 `stale_write`** echoing `current_version` so the
   client refreshes in one hop; a per-record `RLock` serialises `load → precondition → mutate → save`
   (`routes.py:230-348`, `:969-1225`); the frontend consumes the conflict payload (`api.ts:268-358`) and
   the Assistant explicitly **refuses to merge or retry** on 412 (`AssistantPanel.tsx:657-677`). What a
   collaboration phase would add is **attribution and audit**, not concurrency.
2. **There is no per-user dimension anywhere, so "My Experiments" is a misnomer.** The store is
   `workspace_root() / <experiment_id>` (`workspace.py:275`, `:678`, `:702`) with no user segment, and
   `list_experiments()` returns every directory. Combined with `emptyDir` (`docs/deployment.md:29`),
   every authenticated user today shares one experiment list that dies with the pod. Personal-vs-group
   scoping is not an extension of an existing per-user model — **there is no per-user model.**
3. **Persistence is therefore the gate on nearly all of it.** Group-scoped experiments cannot live in an
   `emptyDir`. Dean's guide removes the **technical and role-level** objection to storage location and
   schema ownership — *"adding app-specific tables next to the mirrored schema is fine"* (guide
   `:138-140`), and the role owns its own database and `public` schema (`:136-138`).
   **That is not project authorization, and this row must not be read as one.** Three reasons, set out
   in full in the collaboration decision record §1.3: two of the supporting quotes describe a *Postgres
   role's grants* rather than a grant of project authority; guide `:151` (*"Writing to this database is
   unrestricted"*) sits under *"Displaying record content"* and exists to set up its own next clause, so
   lifting it as standalone migration approval is the move its structure guards against; and this
   repository **independently** blocks the work — `2026-07-24-phase-37-readiness-plan.md:48-52` bars
   *"writes of any kind (DML, **DDL**, …); a PostgreSQL-backed record repository"*, and `CLAUDE.md` §15
   lists durable persistence as NOT authorized. **CORRECTED 2026-08-09 — the last clause is no longer
   an accurate citation, and the conclusion survives it.** `CLAUDE.md` §15 was narrowed on 2026-08-07:
   durable persistence for **Create Experiment, in app-owned tables**, is authorized, and Dean applied
   `0001_experiments` to the hosted database on **2026-08-09**. What §15 still does **not** authorize is
   what this paragraph is actually about — a repository over `records`, record loading, upload writes,
   and anything group- or user-scoped — and the readiness-plan bar and Q12 contingency below are
   untouched. So the row's verdict stands; only this one supporting citation had gone stale.
   Storage location is additionally **contingent on Q12**
   (does a portal identity service already own users and groups?). Migration process, backup/retention,
   identity source and group administration policy are untouched.
4. **The schema already owns record attribution, and the app has never used it.** `/attribution/uploaded_by`
   is described in v1.05 as *"SERVER-STAMPED from the authenticated identity at ingestion … Decided by
   D. Sokaras 2026-06-15"*, and `/attribution/contributors[]` carries `name|role|affiliation|orcid|email`.
   ~~`rg "uploaded_by" src/ apps/ tests/ scripts/` → **zero**.~~ **CORRECTED 2026-08-03:** the grep
   was accurate but the inference ("the app has never used it") was **wrong** — the passthrough was
   *structural*, so no code named the field while `export.transform` copied the whole `attribution`
   block, and a draft-authored `uploaded_by` reached an exported record and passed official schema
   validation. It is now refused fail-closed at draft validation with a final invariant in
   `transform`; see [`docs/identity-trust-contract.md`](../../identity-trust-contract.md) §"Two
   consequences" item 1. So attribution does **not** need a home
   outside the record. But `contributors[].role` is `data_owner|performed_measurement|performed_analysis|curated_record`
   — a **scientific contribution** enum. It **cannot** double as an authorization role.
5. **Identity is absent and its trust boundary is ~~unproven~~ now stated by Dean — as bypassable.**
   Amended 2026-08-12: G7's questions are answered, and the answer that governs is Q4 — the Service is
   a plain ClusterIP with no NetworkPolicy, so forwarded identity headers are forgeable in-cluster and
   **a header's presence does not prove authenticated edge traversal.** Stamping the canonical
   Authentik username is authorized *only* for a request established through a trusted authentication
   boundary, which ISAAC has not built. **Identity remains absent from the app, and the finding stands
   with a sharper reason.** Full evidence:
   [`docs/identity-trust-contract.md`](../../identity-trust-contract.md); the gate is **G7**, moved
   from external to internal.

**The seam table above remains binding, and item 1 does not weaken it.** In particular the
"Authorship / actor" row stands: the existence of a conflict contract is not permission to populate it
with an actor.

### 6.2 W1 — an unversioned mutation path, found by the collaboration investigation

**The one defect the investigation found that is fixable today, and needs no identity.**

`POST /api/demo/run` (`routes.py:524`) mutates persisted record state with **no `If-Match`** — the four
precondition sites are `routes.py:969`, `:1091`, `:1211`, `:1383`, and this is not among them. It calls
`ws.create_experiment(..., id=target_id)`, which builds a fresh `Experiment` and `save()`s it over the
existing one, while **preserving the on-disk `generation`** (`workspace.py:459`) so that repeated no-op
demo runs do not churn ETags — the P36.8 idempotence guarantee. Since `version_token()` is
`f"{generation}.{rev}"` (`:285-287`), a **content replacement can leave the token unchanged**. Observed:
byte-identical `"194b1839e67a2321.0"` across a second demo run.

**Consequence.** A client that read a canonical demo id at `rev 0` and writes after a concurrent
`demo/run` has its write accepted against content it never observed — the exact failure the 412 path
prevents everywhere else. A client that had already edited (`rev ≥ 1`) *is* caught, because the reset
to `rev 0` changes the token. Because §6.1 item 2 establishes that all users share one workspace, the
"two clients" are two real people on `/krish`, not a hypothetical.

**REPRODUCED 2026-08-01. An earlier revision of this entry hedged that an end-to-end lost update was
"NOT demonstrated" and "must not be cited as one". That hedge was wrong and is withdrawn.** An
independent review constructed the sequence with the repo's own `test_strict_precondition.py` fixture,
and it was re-run independently by the orchestrator. Measured:

```
B0 seed:            version='79501e36e523dfb4.0'  content=326cb676ccea7231
B1 POST /answers with a matching If-Match          -> 200   (a real, confirmed user edit)
   after edit:      version='79501e36e523dfb4.1'  content=22084ee213d398ab
B2 POST /api/demo/run   (no precondition sent or accepted) -> 200
   after demo/run:  version='79501e36e523dfb4.0'  content=326cb676ccea7231
   token returned to the pre-edit value?  True
   the user's edit was destroyed?         True
B3 POST /answers with the ORIGINAL pre-edit token   -> 200 ACCEPTED
```

**Two demonstrated failures, not one.** (a) `demo/run` **silently destroyed a committed user edit** —
confirmed answers, applied through the version-gated path, gone with no precondition and no signal.
(b) The token **ABA'd back to a previously-issued value**, so a precondition that must return 412
returned **200**. That defeats the stated purpose of the `generation` nonce, which `workspace.py:255-258`
says exists precisely so tokens *"differ across a delete->recreate even when `rev` returns to 0
(ABA-safe)"*.

**Why the first probes missed it, recorded because it explains the earlier wrong hedge.** The
illustration originally chosen — read at `rev 0`, demo replaces content, write accepted — *cannot* fire:
on a pristine seed `demo/run` reproduces byte-identical content on both canonical ids (measured; token
same, content same). There is no unobserved content **without an intervening edit**. The reachable path
is one step further along, and it is trivial.

**Severity: CRITICAL** (upgraded from Important once reproduced — silent destruction of confirmed
scientific answers, one button click, on a workspace §6.1 item 2 shows every authenticated user shares)
**· Owner: orch · Fix-now eligible on every criterion** (application-owned,
bounded, testable, no identity, no persistence, no infrastructure, no real-record visibility).
**Deliberately not fixed in the documentation slice that found it**, because the repair is a backend
contract change with a frontend counterpart — the demo button would have to send a precondition — and
that deserves its own slice with its own review. Candidate approaches, to be decided in that slice:
require `If-Match` on `demo/run`; or mint a fresh `generation` whenever the upsert actually changes
content (preserving idempotence only for true no-ops); or refuse the run when the target's authoritative
signature differs from the seed. The second is the smallest and preserves P36.8's guarantee exactly — measured: on a true no-op the
content hash is identical, so the generation is preserved and the ETag never churns; on the changed
-content case it mints `G' != G`, turning B3's 200 into a 412. The primitive already exists —
`Experiment._persisted_sig_and_rev()` (`workspace.py:319-329`) is the on-disk authoritative signature
`save_versioned()` already compares.

**But note precisely what each approach closes, so the follow-up slice does not close W1 believing both
failures are gone.** Approach (2) fixes the **token**, not the **path**: after it, B2 still destroys the
edit — the ETag merely stops lying about it afterwards, so the next writer gets an honest 412 instead of
a silent 200. Only (1) and (3) prevent the destructive overwrite itself. A complete fix is (2) **plus**
one of (1) or (3). Approach (1) is also larger than it looks: the route calls `ensure_seeded()` first,
which may *create* the target, so a precondition against a not-yet-existing record needs defined
semantics.

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

1. **G1 is open — narrowed 2026-08-01, but open.** No `Baseline required: yes` row anywhere in §2.1,
   §2.2 or §2.3 is runtime-verified **in the artifact sense**. The one real execution (§0, Entry 2) is
   operator testimony and was not captured, so no row can be attributed to it per-row. The rule in §7
   forbids plain Complete while G1 is open, without exception.

**Why not "Complete With External Blockers":**

2. ~~**The final runtime code is not in any published image.**~~ **RESOLVED 2026-08-01 — this item no
   longer applies and is retained struck through rather than deleted, so the verdict's history stays
   checkable.** When written, the closure slice was unmerged. It merged as `ceea656` and was published
   as `v0.0.38`; the subsequent responsive remediation merged as `d7010f9` and was published as
   `v0.0.39`. Both tags verified by `git rev-list -n1` and both created by `github-actions`. **No
   un-merged change is load-bearing for the claim any more.**
3. **The hosted SHA is unknown *from here*, and unobserved *since* `v0.0.38`.** `GET
   /krish/api/health` returned **HTTP 302** to the Authentik edge — re-observed **2026-08-01**,
   redirecting to `/outpost.goauthentik.io/start`. Treat that as a point-in-time probe, not a standing
   fact. Krish observed the endpoint reporting `ceea656` (image `v0.0.38`) in an authenticated session
   (§0, Entry 2), so the SHA is not wholly unobserved — but that was testimony, point-in-time, and
   predates `v0.0.39`. Which image is running **now** was not observed. Worse for
   attribution: the cluster's
   image-selection policy is **UNDETERMINED** — no Flux `ImagePolicy`/`ImageUpdateAutomation`
   manifest exists in this repository — so it cannot even be *inferred* which tag would be selected.
   That is not a per-row attribution to a named owner; it is an unknown.
4. **G3 is open.** The five aggregates were withdrawn, but the question to Dean is unanswered, and
   five of them **were served in a published image**. Withdrawal narrows the exposure; it does not
   resolve the gate.
5. ~~**The real database has never been contacted. No scan has ever run.**~~ **Corrected 2026-08-01
   — this sentence is false as written and must not be repeated.** It was accurate when written
   (`a911b8c`, 2026-07-31 18:17:27 −0700), 41 minutes before the `ceea656` merge whose image the scan
   was later run against; it was never updated. **The deployed pod contacted the database at least
   once** (§0, Entry 2 — operator testimony against image `v0.0.38`). The surviving, narrower point:
   every §2.2 row is *documented here* only by tests against fakes and by static reading of the code,
   and the one real execution produced **no captured artifact**, so no row can be cited as
   runtime-verified *in the artifact sense* until the JSON is pasted back. Attributing all of §2.2 to
   G1 is still exactly the "single wave of the hand" §7 prohibits.
6. **G4 is open, and it is not automatable.** Real `Cmd`/`Ctrl`-`+` zoom sign-off has no automation
   surface in Chromium at all. It is a genuine external gate and *is* correctly attributable — it is
   listed here for completeness, not as an argument against the label.

**Items 3 and 5 are now the decisive ones**, and both are simply unknowns (item 2, the one piece of
work *we* owed, is resolved). Only items 4 and 6 are clean external attributions. Note what this
changes and what it does not: the project no longer owes a publication step, so the remaining distance
to "Complete With External Blockers" is entirely **observation** — one signed-in run of the hosted
checklist. It is nonetheless still distance, and the label stays unavailable until that run happens.

**What this verdict does NOT say.** It does not say the deployment is *currently* healthy, degraded,
rolled, or stale. ~~**No hosted rollout has been observed by this project at any point.**~~ **Corrected
2026-08-01:** one has — `v0.0.38` (`ceea656`), observed by Krish in an authenticated session and
recorded as operator testimony in §0, Entry 2. What remains true is that **no hosted state has ever
been observed from an agent session**, that the observation is point-in-time and release-tagged rather
than a standing fact, and that it produced no artifact. Any future sentence combining "baseline" with a
claim about `/krish` must cite its evidence and must say whether that evidence is an **artifact** or
**testimony**.

**What would move this to "Complete With External Blockers":** ~~merge and publish the closure image~~
(**done** — `v0.0.38`/`v0.0.39`); Krish runs
[`docs/hosted-qa-checklist.md`](../../hosted-qa-checklist.md) Part 1 and confirms `commit`
matches the closure merge SHA; the recon endpoint returns a report (`ok` **or** a named refusal —
both are results); §2.2 rows are then attributed **per-row** to what that report actually exercised,
and any row it does not exercise is recorded as "not verified, and not covered by any open gate
either" rather than swept in. G2, G3 and G4 may remain open under that label; G1 may not.
