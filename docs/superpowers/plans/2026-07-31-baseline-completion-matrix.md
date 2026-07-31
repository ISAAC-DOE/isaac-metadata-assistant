# ISAAC Baseline Completion Matrix

**Created:** 2026-07-31 · **Status:** LIVE — this is the authoritative definition of "baseline" for
ISAAC. Update it in the same PR as any slice that changes a row.

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

### A second finding: Slice 2A already went past Dean's enumerated list

The guide's authorization of aggregate output names a specific list — "record counts, counts by type
and domain, validation totals, schema version, database reachability". **The shipped Slice 2A report
is broader than that list**, and this document originally claimed otherwise. Measured against the `dataset` literal at
`routes.py:3296-3346`, it contains:

| Shipped field | On Dean's enumerated list? |
|---|---|
| `total_records`, `records_scanned`, `records_parsed`, `parse_failures` | yes — record counts |
| `by_record_type`, `by_record_domain` | yes — counts by type and domain |
| `records_passing_full_schema`, `records_failing_full_schema`, `total_validation_issues` | yes — validation totals |
| `by_rule_family`, `by_schema_path` | defensible — a breakdown of validation totals |
| `by_instance_path` | **no** — paths through the actual record data, schema-masked but record-derived |
| `distinct_structural_signatures` | **no** — a count of distinct record *shapes* |
| `total_link_count`, `dangling_link_count` | **no** — derived from `data->'links'` |
| `record_id_digest_count`, `vocabulary_term_count`, `expected_seed_rows`, `seed_count_matches` | not enumerated, but carry no record content |

None of these emits a scientific value, a title, an id, or any record text — the masking in
`safe_key_segment` (`db_recon.py:436-470`; note `:470` is the one branch that returns a key verbatim,
reached only after the declared-name check) holds. But three of them are **record-derived structural
facts that Dean did not enumerate**, and they are already merged and live in image `v0.0.32`. The
judgement call was made in Slice 2A, not deferred to §4.

Stating this plainly is the point of this document. A governance record that describes its own
project as more conservative than it actually is, is the precise failure mode it exists to prevent.
These three fields are flagged for gate **G3** — not because they are believed unsafe, but because
they were never explicitly authorized and the honest thing is to say so.

Scope of this audit, stated so it is not over-read: it covers the `dataset` block only. The response
also carries `database` (gate booleans plus `server_version` / `server_version_major` /
`expected_major_version_match`, `routes.py:3381-3396`) and `integrity` (`routes.py:3351-3375`, which
includes `rows_before` / `rows_after` — those are **record counts**, not merely statement counts).
Neither is a disclosure question: `rows_before`/`rows_after` duplicate `total_records`, which Dean
explicitly authorized. But the audit above is a `dataset` audit, not a whole-response audit, and must
not be cited as one.

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
| Aggregate reconnaissance report | guide "Displaying record content" | **yes** | done | read | **no** | Krish |
| Full-schema validation of scanned records | guide "The records table" | **yes** | done | read | no | Krish |
| Schema-drift **classification** (`by_rule_family`, `by_schema_path`) | §4 below | **yes** | **done — shipped in Slice 2A** | read | **no** | Krish |
| — its `by_instance_path` component | §0 / G3 | **no** — flagged, not endorsed | shipped | read | **no** | **Dean** (G3) |
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
| Backend suite | **yes** | done — **1801** passing (1794 + 7 mutation tests, PR #30) | orch | — |
| Frontend suite | **yes** | done — 2145 / 93 files, but see F1 | orch | — |
| TypeScript build | **yes** | done | orch | — |
| Production build | **yes** | done | orch | — |
| Docker build + smoke | **yes** | done (CI) | orch | — |
| Snapshot drift gate (both artifacts) | **yes** | done | orch | — |
| Secret / leak / real-data scans | **yes** | done | orch | — |
| Copy-truthfulness guards (frontend + backend, parity-enforced) | **yes** | done | orch | — |
| **Real-browser test baseline** | **yes** | **done** — Playwright/Chromium, PR #32 (`c36053d`); **579 passed on both macOS and Linux CI** | orch | — |
| **Accessibility engine baseline** | **yes** | **done** — axe-core, 18 surfaces × 5 projects, count-based baseline (1,974 darwin / 1,980 linux nodes) | orch | — |
| **Responsive baseline (4 viewports)** | **yes** | **done** — 1280×800, 1024×768, 768×1024, 375×812 | orch | — |
| **Real 200% browser zoom** | **yes** | **automated** — `{640×400, DPR 2}`, asserted not assumed. **Human sign-off still OPEN** | orch → **Krish** | G4; automation does not close it |
| Accessibility defects found (A1–A8 below) | **yes** — recorded | **found, not fixed** | orch | next slice; 2 are critical |
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
| Docs accurately describe implemented / not implemented / blocked | **yes** | partial — this slice fixed two false claims about shipped code (§0) and a stale `psycopg2` claim in the readiness plan §3; more may remain | orch |
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
- `by_schema_path` — counts per path through the *schema*.
- `by_instance_path` — counts per path through the *record*, every segment schema-masked.

So the hosted scan should already answer "what kind of drift" without any new endpoint. Build nothing
until the G1 report shows these are insufficient.

### 4.2 The distinguishing rule

**The schema may describe the data; the data may not describe itself.** If an output string can only
be produced by reading a record's value, it is per-record content and is closed.

`by_instance_path` is the deliberate boundary case: the *path* is schema-derived and masked, but the
*fact that the path is populated* is record-derived. It ships today. It is named here rather than
glossed over, and it is flagged for G3.

### 4.3 Three constraints the rule does not imply on its own

Obeying §4.2 literally still permits per-record disclosure by arithmetic. These are binding:

1. **Minimum cell size.** The *documented seed* is **30 rows** (`DOCUMENTED_SEED_ROWS`, `db_recon.py:133`);
   the actual row count is **unobserved** — the scan has never run, which is exactly why the report
   emits `seed_count_matches`. At that order of magnitude a count of `1` at a specific path is a
   per-record fact wearing aggregate clothing. Any *new* aggregate must
   suppress or bucket cells below a stated threshold. (The shipped fields predate this rule; whether
   they need it is part of G3.)
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

Found by PR #32, **all pre-existing application behaviour, none fixed** — the slice was authorized to
measure the app, not repair it, and fixing `apps/web/src/**` there would have made the diff
unreviewable. Every one was independently confirmed real by review; there are no phantoms.

| ID | Rule | Impact | Where |
|---|---|---|---|
| **A1** | `button-name` | **critical** | The global search trigger has **no accessible name at all** at 375px and at 200% zoom (`chrome.css:503` hides the label and kbd hint; the SVG is `aria-hidden`, no `aria-label`) |
| **A2** | `aria-allowed-attr` / `aria-allowed-role` | **critical** | 31 Evidence Trail entries are `<button role="listitem" aria-pressed>` — the role kills the button role and forbids `aria-pressed`, so selection state is not exposed |
| **A3** | `color-contrast` | serious | 1,610 nodes, every surface. **Three causes, not one**: `--text-disabled #c0c8d0` rendered as Evidence line numbers at **1.56:1**; genuinely low tokens; and **five `opacity` composites of tokens that pass at full strength** — darkening tokens will not fix those |
| **A4** | `scrollable-region-focusable` | serious | 3 pairs: `evidence` desktop/mobile, `settings-api` mobile |
| **A5** | `page-has-heading-one` | moderate | `/load` has no `<h1>` |
| **A6** | `landmark-unique` | moderate | Two unnamed `role="search"` landmarks on Endpoint Explorer |
| **A7** | LAYOUT-01 | — | Record StatusBar does not reflow: 575px of content in a 353px box at 375px, clipped and overlapping |
| **A8** | LAYOUT-02 | — | Record-context chip clipped: `chip-draft` on Evidence (macOS+Linux) and `chip-exported` on Export Readiness (**Linux only** — SF Pro hid it). One `.record-context` fix closes both |

**Do these block baseline?** A1 and A2 are critical accessibility defects, and §7's rule says "no
known Critical or Important findings". Read honestly: that rule is about findings against *new work*,
and these are pre-existing defects that baseline work **discovered and documented where nothing
previously measured them at all**. Going from no measurement to a ratcheted, per-node baseline is the
foundational improvement; leaving the defects unfixed is a known, owned debt, not an ambiguity.
They are the obvious next slice, and A1/A2 are small.

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
| G3 | Aggregates already shipped that Dean did not enumerate | **Dean** | "Slice 2A already returns `by_instance_path`, `distinct_structural_signatures`, and link counts. These are record-derived structural facts beyond your enumerated aggregate list, though none emits a value, title or id. Are they within what you intended, or should any be withdrawn?" | These stay live in `v0.0.32`; flagged, not hidden. Also covers any drift §4.1's taxonomy cannot classify |
| G4 | Responsive / 200%-zoom human sign-off | **Krish** | [`docs/hosted-qa-checklist.md`](../../hosted-qa-checklist.md) Part 2 — 4 viewports + real 200% zoom. Automated coverage runs locally only and does NOT close this | Quality row stays open |
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
that Slice 2A already emits three aggregates Dean did not enumerate, the first hosted observation of
`/api/runtime/database/recon` will be the first time *anyone* sees what those aggregates actually
contain. G1 is not a formality.
