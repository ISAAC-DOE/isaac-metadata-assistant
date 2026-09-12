# ISAAC Execution Ledger

**THE CANONICAL MULTI-SESSION TRACKER.** A future session resumes the project from this file plus
the repository — never from remembered chat context.

---

## SESSION HEADER

```
LAST UPDATED:          2026-09-12 (planning run)
CANONICAL REPO:        /Users/krishverma/Documents/ISAAC
                       origin = https://github.com/ISAAC-DOE/isaac-metadata-assistant.git
                       personal = https://github.com/Krish-Verma/isaac-metadata-assistant.git (historical mirror)
BRANCH:                main
HEAD:                  2f9a1133bcda7f45e1d751110641d1322586f60e
UPSTREAM DIVERGENCE:   0 ahead / 0 behind
DIRTY STATE:           SIX untracked planning artifacts under docs/superpowers/plans/
                       (four 2026-09-12-*.md + ISAAC_EXECUTION_LEDGER.md + ISAAC_PRODUCT_DECISIONS.md)
                       — no tracked file modified; no code touched
                       snapshot drift: NONE (exit 0, both artifacts) — verified after writing all six
OPEN PRS:              none
LATEST VERIFIED RELEASE: v0.0.232  (git rev-list -n1 v0.0.232 -> 2f9a1133…)
CI FOR HEAD:           run 34709792004, conclusion success
GHCR PUBLISH:          run 34711838575, conclusion success
HOSTED COMMIT:         2f9a1133…  (observed read-only at /krish/api/health, 2026-09-12)
HOSTED MODE:           synthetic-only · storage postgres/durable · record_display closed
VERIFIED BASELINE AT HEAD (main checkout, measured this session, exit codes captured not piped):
  backend   .venv/bin/pytest -q -rs        -> 7203 passed, 45 skipped, exit 0 (563.52 s)
  frontend  npx vitest run                 -> 206 files / 5465 tests, exit 0
  types     npx tsc -b                     -> exit 0
  playwright (counted with --list, NOT run) -> read-only 1600/20 files · mutation 121/15
                                              · trusted 8/3 · bench 7/7
  snapshot  build_memory_snapshot --check (both --out and --detail-out) -> exit 0, no drift
  a11y      A11Y_BASELINE_TOTAL_NODES = 877 darwin / 877 linux · 70 cells
            · 2 platform splits (both settings-explorer, net zero) · DARWIN_CARRIED_FORWARD = []
ORCHESTRATOR:          Opus 5 (claude-opus-5[1m]) — **DISCLOSED FALLBACK.** DEC-17 makes Fable 5.1
                       primary; Fable was not available to this session and Krish approved the
                       substitution. Orchestrator-only discipline preserved: plan, delegate,
                       review, integrate, verify, commit — no production code written by the
                       orchestrator. No other model silently substituted.
SUBORDINATE AGENTS:    4 implementers dispatched (DOC-007, UX-001/002, UX-003/004, CAP-001/009);
                       1 slot RESERVED for independent review. Ceiling 5 total, nested = forbidden.
CURRENT PHASE:         Phase 0 COMPLETE · DOC-007 COMPLETE (4552de54) · Phase A + CAP-001 IN FLIGHT
CURRENT TASK:          DOC-007 (docs truth alignment) · UX-001/UX-002 · UX-003/UX-004 · CAP-001/CAP-009
LAST COMPLETED TASK:   REC-001 … REC-012, DOC-001 … DOC-006, the six-pass plan review, and
                       the 2026-09-12 revision reconciliation into all six artifacts
NEXT EXECUTABLE TASK:  integrate + independently review the four in-flight slices, then LIB-001
UNVERIFIED WIP:        four in-flight implementation slices in the SHARED working tree, scoped to
                       disjoint file sets; all git operations are the orchestrator's
EXTERNAL BLOCKERS:     EXT-01 … EXT-12 (see ISAAC_PRODUCT_DECISIONS.md §C and the blockers doc)
PENDING KRISH DECISIONS: NONE BLOCKING. DEC-05, DEC-09, DEC-11 and DEC-13 were all RESOLVED by the
                       2026-09-12 revision; DEC-19 … DEC-24 were added, two of them overriding the
                       plan's own recommendation (see ISAAC_PRODUCT_DECISIONS.md §B2)
```

**Update this header after every substantive milestone, and immediately before any
context-exhaustion or rate-limit interruption.** A stale header is worse than none: it sends the
next session to build what already exists.

---

## STATUS VOCABULARY

`HARD CONSTRAINT` · `CONFIRMED CURRENT` · `USER PREFERENCE` · `IMPLEMENTED AND VERIFIED` ·
`IMPLEMENTED BUT NOT INDEPENDENTLY VERIFIED` · `REPORTED COMPLETE` · `IN PROGRESS` · `PLANNED` ·
`PROPOSED` · `SUPERSEDED` · `REJECTED` · `BLOCKED` · `UNKNOWN` · `CONFLICTING EVIDENCE`

---

## PHASE 0 — RECOVER CURRENT TRUTH · COMPLETE

| ID | Objective | Status | Evidence |
|---|---|---|---|
| REC-001 | Repo, branch, HEAD, divergence, worktrees, stashes | IMPLEMENTED AND VERIFIED | `git status -sb`; `rev-parse`; `rev-list --left-right --count`; `worktree list`; `stash list` |
| REC-002 | Open PRs and exact-head CI | IMPLEMENTED AND VERIFIED | `gh pr list --state open` → none; run `34709792004` success |
| REC-003 | Which release the gate admitted for HEAD | IMPLEMENTED AND VERIFIED | `git rev-list -n1 v0.0.232` → `2f9a1133…`. **Corrects the supplied checkpoint's "pending"** |
| REC-004 | Hosted rollout + configuration | IMPLEMENTED AND VERIFIED | read-only observation of `/krish/api/health`, `/about`, `/providers/capabilities` in the owner's authenticated session, 2026-09-12 |
| REC-005 | Live API operation inventory | IMPLEMENTED AND VERIFIED | `/api/openapi` → **69 paths / 77 method-operations**; no MCP path (and per `test_mcp_transport.py:296-302` its absence is asserted **even when mounted**, so OpenAPI is not evidence either way) |
| REC-006 | Rendered UI measurement across 9 surfaces | IMPLEMENTED AND VERIFIED | live Chrome; see the UX/IA plan Part 1 |
| REC-007 | Design-token + typography census | IMPLEMENTED AND VERIFIED | 82 tokens, 0 type/space axes; 1,073 `font-size` declarations in 20 values; UX plan Part 5 |
| REC-008 | MCP reality | IMPLEMENTED AND VERIFIED | hosted `404` is ISAAC's own string at `spa.py:46-47`; gate `app.py:313` / `ISAAC_MCP_DEPLOYMENT` unset; 14 tools / 17 operations / 3 scopes |
| REC-009 | Historical corpus reality | IMPLEMENTED AND VERIFIED | **zero `.mac`, zero `.xlsx`/`.xls` in the tree**; `examples/` is generated synthetic |
| REC-010 | Data model, owned tables, concurrency | IMPLEMENTED AND VERIFIED | **9** owned tables by importing `db_write.OWNED_TABLES`; `version = <generation>.<rev>`; `If-Match` 428/412; CAS predicate on `Q_UPSERT_EXPERIMENT` |
| REC-011 | Ambiguity defect reproduced | IMPLEMENTED AND VERIFIED | one-sentence "425 … maybe 430" → 1 candidate, 430 lost; cause `transcript_capture.py:810` |
| REC-012 | Vendor capability verification | IMPLEMENTED AND VERIFIED (with UNKNOWNs named) | official docs, 2026-09-12; voice+custom and retry behaviour are **UNKNOWN, not inferred** |
| DOC-001 | Product Scope V2 | IMPLEMENTED | `2026-09-12-isaac-product-scope-v2.md` |
| DOC-002 | Master Implementation Plan | IMPLEMENTED | `2026-09-12-isaac-master-implementation-plan.md` |
| DOC-003 | UX / IA Plan incl. Impeccable critique | IMPLEMENTED | `2026-09-12-isaac-ux-ia-plan.md` |
| DOC-004 | Product Decision Register | IMPLEMENTED | `ISAAC_PRODUCT_DECISIONS.md` |
| DOC-005 | This ledger | IMPLEMENTED | `ISAAC_EXECUTION_LEDGER.md` |
| DOC-006 | Blocker matrix + risk register + verification strategy | IMPLEMENTED | `2026-09-12-isaac-blockers-and-risks.md` |

**GATE CLEARED 2026-09-12 — implementation authorized.** External-owner, security, migration and
data-governance boundaries are unchanged.

### DOC-007 — documentation truth alignment · **COMPLETE** (`4552de54`)
- **Workstream** DOC · **Owner** Sonnet implementer · **Reviewer** reserved Opus slot
- **Objective** correct the measured-stale claims in `CLAUDE.md` and `docs/` so they stop steering
  future sessions wrong. Nine items, each independently re-derived by the implementer before edit.
- **Acceptance** the operation count (71 → **77**), the a11y total (871 → **877**), the plans-file
  count (~41 → **44**), two §15 "nothing reads it" claims, the phantom
  `isaac-runs-stage-2-contract.md` §8 citation, `browser-accessibility-testing.md`'s stale A11Y-01
  status, every `/krish/api/mcp`-as-live citation, and the "immutable at the database level" claim
  class are all corrected **in place with the old wording preserved** per house style.
- **Verification** `pytest apps/api/tests/test_about_and_openapi.py`; snapshot drift check with
  **both** `--out` and `--detail-out` — **`CLAUDE.md` IS in the served manifest, so this slice WILL
  drift the snapshot and must regenerate in the same commit.**
- **Outcome** 4 claims corrected (`CLAUDE.md` ×3 + `docs/` ×2); **5 needed no edit — already
  corrected in-repo**; **2 items in my brief were MY OWN errors and are withdrawn.**
- **The finding that matters most:** my brief said A11Y-01 was closed. **It is not** —
  `e2e/a11y-baseline.ts:634` and `:3562` both say so in terms, and A3 closed one of three causes.
  **The implementer refused the instruction** rather than writing a new false claim into a served
  document, and added dated additions recording what A3 actually fixed. The brief was the defect.
- **My second error:** "~41 plans files is stale, it is 44". `git ls-tree -r main` gives **41**; the
  directory reads 47 today only because **six are files I created this session**. I measured a
  directory while adding to it, and a prior agent had flagged that exact caveat.
- **Vantage point added to the hosted 404:** it was observed in the owner's **authenticated**
  session; an unauthenticated request gets **302** at the Authentik edge. Both true, different
  questions — only the authenticated 404 proves the request reached the application.
- **Snapshot deliberately deferred.** `CLAUDE.md` is manifest-listed so this slice drifts it, and a
  concurrent slice is editing manifest-listed CSS. **One regeneration after all slices settle.**
- **Residue, named not fixed:** `migration-approval-packet-0002.md` cites the phantom
  "contract §8 D7" unflagged, while the Stage-2 contract and `CLAUDE.md` both already flag it.
- **Next action** none — slice closed. Independent review folded into the integrated-diff review.

---

## PHASE A — DESIGN SYSTEM COMPLETION + HONESTY FIXES · unblocked

### UX-001 — Declare the four missing token axes
- **Workstream** UX · **Status** PLANNED · **Owner** Sonnet implementer + Opus reviewer
- **Dependencies** none. **This is the first executable task after approval.**
- **Objective** Add font-size, font-weight, line-height and spacing tokens to `styles/tokens.css`.
- **Evidence** `tokens.css` declares **82** tokens: 70 colour, 6 radii, 4 shadow, 2 font-family,
  **0** type, **0** spacing. Against it: **1,073** `font-size` declarations in **20** values,
  **8** weights (incl. non-standard 550/620/650), **2,407** spacing literals in **32** values,
  exactly **one** `16px` declaration in the product. Colour is **99.3%** tokenized with **0** live
  phantoms — that is the standard to match.
- **Acceptance** every axis declared; a ratchet test asserts no *new* raw literal in the axes
  covered; the existing phantom-property ratchet and `interaction-states` P22C guard are
  **unedited**; frontend + backend suites green; `tsc -b` exit 0.
- **Verification** `npx vitest run`; `npx tsc -b`; snapshot drift check with **both** `--out` and
  `--detail-out`.
- **Next action** after approval: read `tokens.css` and `base.css`, propose the axis values, get
  the scale ratified (**DEC-05** adjacent), then implement.

### UX-002 — Type scale, visible record title, per-workspace `h1`
- **Status** PLANNED · **Depends** UX-001 · **Owner** Opus implementer + Opus reviewer
- **Evidence** Record screen's largest **visible** text is 15 px (Capture) / 17 px (Graph). Its only
  `<h1>` is `sr-only`, 1×1 px, `clip: rect(0,0,0,0)`, and reads **`"Review Record"` on all four
  workspaces** — correct on one of four. Secondary screens all render a 22 px visible title; the
  primary work surface renders none.
- **Acceptance** a visible page title on the record screen; each workspace's accessible name matches
  that workspace; a test asserts the `h1` text differs per `?view=`; a11y baseline re-transcribed
  from **Linux CI** with the darwin column **measured locally**, never carried forward.

### UX-003 — Two false Help strings, fixed and pinned
- **Status** PLANNED · **Depends** none · **Owner** Sonnet + Opus reviewer
- **Evidence** `HelpPanel.tsx:7` promises draft extraction *"from your files"* while
  `POST /api/uploads` is an unconditional **403** and no path turns a file into a draft.
  `HelpPanel.tsx:10` attributes the whole verdict to the official schema — **stale** since
  `ok = schema_ok AND exactness_ok`.
- **Acceptance** both corrected; both pinned by an extension of the `upload-claim-parity` guard
  family; **polarity tested** (the guard must fail on the false version — this repo has shipped an
  inverted disclosure guard before).

### UX-004 — Reconcile the two workflow vocabularies; Help on record screens
- **Status** PLANNED · **Depends** UX-003 · **Owner** Sonnet + Opus reviewer
- **Evidence** Server spine: `Load Record · Complete Metadata · Review Evidence · Review Export
  Readiness · Export`. `HelpPanel`: `Draft · Complete · Export · Validate · Audit`. A first-timer
  reading Help is taught the second. Help renders only on the `home` TopBar variant, so it is
  **absent from every record screen**.
- **Acceptance** one vocabulary, the server's (it is derived, not written); Help reachable from a
  record screen; a test pins the single vocabulary.

---

## PHASE B — EXPERIMENT LIBRARY · unblocked · highest value

### LIB-001 — Extend `GET /api/experiments`  **(API before screen)**
- **Status** PLANNED · **Depends** none · **Owner** Opus + Opus reviewer
- **Evidence** the served payload is exactly `id · title · scenario · status · created_utc ·
  pending_count · evidenced_field_count · exported · record_id` (`routes.py:1260`). No run count,
  no technique/beamline.
- **`Last Updated` IS honestly available — DEC-07's open sub-question is RESOLVED, 2026-09-12, and
  my planning note was wrong.** I wrote *"no `updated_utc`, so sort by Last Updated is not
  implementable."* That was true of the **served payload** and false of the **model**. Measured:
  `Experiment`/`Run` both carry a **stored** `updated_utc` (`workspace.py:1232`, documented
  *"Never derived — it is stored"*); `__post_init__` anchors it to `created_utc` **only when it is
  empty**, i.e. for legacy documents; `isaac_experiments` has an `updated_utc timestamptz NOT NULL`
  column since `0001_experiments` (**already applied hosted**); and the change feed reads
  `exp.updated_utc` on the wire today (`change_feed.py:509`).
- **Two constraints that must travel with it, or the column becomes a lie.** (1) It is formatted to
  **whole seconds** (`_now_iso`), so two writes in one second are indistinguishable by it — which
  is precisely the **measured defect** that made the change feed abandon it as a sort key in favour
  of `changed_at_rev`. (2) The feed's own contract says it is *"still published because clients
  display it, and it is no longer load-bearing for correctness."* **So: display it, sort the list by
  it, and never use it for a correctness decision.** Do not reach for a sub-second timestamp — the
  feed rejected that deliberately as a repo-wide storage change trading a proven defect for an
  unproven assumption.
- **Acceptance** the Library can render every column it shows from one request; counts are the
  server's totals, never `array.length`; no per-record scientific content is added beyond what the
  list must show; response shape pinned by test.

### LIB-002 — Library screen: search, sort, facets, row identity
- **Status** PLANNED · **Depends** LIB-001
- **Acceptance** the shipped worked example's **five records all titled `XANES Example — CuO
  (Cu K-edge)`** are distinguishable in the list. That is the test.

### LIB-003 — Folders: migration-free VIRTUAL NESTED PATH-LABEL model  (revised per DEC-20)
- **Status** PLANNED · **Depends** LIB-001 · **Owner** Opus + independent Opus reviewer
- **Design** a top-level `folder` **path label** on the experiment state document, **included in
  `_authoritative_signature`**. Precedent: `title` — assistant-side, mutable, organizational,
  reaching neither the official record nor `content_signature`.
- **A path MATERIALIZES when at least one Experiment is assigned to it.** There is no durable
  folder entity.
- **v1 MUST support** assign/create a folder path while creating, moving or importing · nested
  paths · breadcrumbs · browse · cross-folder search · clear/move.
- **v1 MUST NOT PRETEND to have** durable empty folder entities · folder ACLs · sharing · folder
  ownership · **atomic folder rename**. Those need a separate persistence/identity decision *if
  later shown necessary*. **Do not ship UI that implies any of them exist.**
- **Migration verdict** **NO new table, NO migration, NO `OWNED_TABLES` change, NO new §15 sentence
  for the location** — cite the 2026-08-07 lift's *"normal application state"*, exactly as
  `ingestion-proposal-contract.md` §8.1 does for proposals. If implementation evidence proves this
  cannot work, **DEC-24 applies: stop the slice and surface the dependency; do not force it.**
- **Mechanical trap** `save_versioned()` returns `False` **writing nothing** when
  `_authoritative_signature` is unchanged, and `from_state` drops unknown keys. So `folder` must be
  a real dataclass field **and** join that signature, or the assignment is silently discarded.
- **Costs to state in the PR** an assignment bumps `rev` and invalidates held ETags (as `title`
  already does) but does **not** move `content_signature`; and because the change feed keys on the
  authoritative signature, **every folder assignment emits an `experiment` event and causes a
  bundle refetch on every open client**.
- **Acceptance** `LIB-003a` — a test proves a folder assignment changes **no** scientific metadata,
  **no** record identity, **no** run value, **no** validation result, does **not** move
  `content_signature`, and that `folder` reaches **no** exported record and **no** sidecar.
- **Not in scope** ownership, sharing, ACLs — blocked by the absent trusted authentication
  boundary. Four forward-compatibility rules: label-not-container; never a permission boundary;
  never derived from a person; any owner stamp server-set at an ingestion boundary with a
  `trust_basis`.

### LIB-004 — Breadcrumbs, cross-folder search, destination on create/import
- **Status** PLANNED · **Depends** LIB-003

### LIB-005 — Reopen-and-continue
- **Status** PLANNED · **Depends** LIB-002

---

## PHASE C — WORKSPACES, UNIFIED REVIEW, VALIDATOR PRESENTATION · unblocked

| ID | Objective | Status | Depends | Key evidence / acceptance |
|---|---|---|---|---|
| UX-010 | Five workspaces + compact next-action strip | PLANNED | UX-002 | resolves 3 nav taxonomies in one 212 px rail and 3 inert steps printing one identical 34-char sentence 3× ; spine stays **server-derived and gated** |
| UX-011 | `Review` as its own workspace (**DEC-08**) | PLANNED | UX-010 | six things (proposals, ambiguities, conflicts, unmapped, missing, export readiness) live in four places today |
| UX-012 | Redundancy collapse | PLANNED | UX-011 | **validation stated in 9 places; next-action in 6 on one screen; pending counts in 5.** `WorkflowProgressBanner`'s `excludeSteps` prop must become unnecessary, not load-bearing |
| VAL-001 | Validator **presentation** only | PLANNED | UX-012 | `schema_ok` stays visible; exactness findings in their own list, **never** as official-schema errors; advisory can **never** flip PASS→FAIL; no CLI transcript |
| UX-013 | Assistant 5 mounts → 1–2, collapsed by default | PLANNED | UX-010 | **not a directory delete** — 6 lib modules have non-Assistant consumers, `assistant.css` shared with `GuidedPrompt`; `ASSISTANT_NO_MODEL_CLAIM` preserved on every surviving mount |
| EVG-001 | ~~Close the `derived_from` CHAIN gap~~ **WITHDRAWN — there is no chain; see the note below the table** | **WITHDRAWN** | — | ~~`GET /experiments/{id}/provenance` loses its only frontend caller, and `derived_from` chains would go invisible~~ — **OVERSTATED IN TWO WAYS; CORRECTED 2026-09-12 by first-hand measurement, and kept struck because it was driving a mandatory PR ordering.** (1) **The fetcher is not the graph.** `api.getProvenance(id)` is called from `screens/EvidenceExplorer.tsx:709`; `screens/graph/EvidenceGraphPanel.tsx:398` merely receives `provenance?: EvidenceSubFetch<…>` as a **prop**. Removing the graph removes a prop *consumer*, not the *caller*. (2) **Provenance is ALREADY readable outside the graph.** `components/EvidenceTrailPanel.tsx:163-175` renders a two-chip pair — origin + review state — computed client-side by the pure functions in `lib/provenance.ts`, with its own comment stating the design: *"THE SERVER IS AUTHORITATIVE. `GET .../provenance` computes the same two dimensions from the same stored content; these helpers exist so this panel — which already holds the trail — does not need a second request."* **The residual is narrower and is the only thing EVG-001 must now close:** the chips give **per-entry** origin, not a **multi-hop `derived_from` chain**. Verify whether any surface renders the chain; if none does, that — and only that — is the prerequisite for EVG-002. **I published this claim second-hand from a planning agent and did not verify it; the ordering constraint survives, but the slice is much smaller than stated.** |
| EVG-002 | Evidence Graph out of primary navigation (**DEC-04**) | PLANNED | ~~EVG-001~~ — **no build dependency.** `DEC-11` step 4's dependency recheck still applies at removal time | 6,169 lines, 123 tests, **0 backend routes, 0 backend tests, 0 other consumers, 0 a11y baseline cells**; `?view=graph` bookmarks safe (`list` is the fallback); depth = **DEC-11** |
| UX-014 | Scientist-facing labels; schema path under disclosure | PLANNED | UX-010 | today `reduced_spectrum`, `qc_status`, `required_for_evidence_record`, `Environment & Context context` are product copy; the path is **never removed** — it is how a curator maps a field |
| UX-015 | **RAISED, NOT ACTIONED — Project Memory** | PROPOSED | — | ~7,800 lines, **578 test cases (largest single test mass in the app)**, one of five top-level slots, for a graph of **this repository's own source code** shown to scientists. **Not named in the authorizing directive** → Krish's call |


> ### EVG-001 IS DISSOLVED — measured 2026-09-12, third and final correction to this claim
>
> My mandatory ordering *"EVG-001 must land before EVG-002"* rested on a `derived_from` **chain**
> that does not exist. Measured first-hand:
>
> * **`derived_from` is not a provenance chain.** It is one of the official schema's
>   **`links[].rel`** relation values — a record-to-record link. `workspace.py:2678` says it in
>   terms: *"`derived_from` — nothing in the model records that one run was derived from"*.
> * **It is already rendered, outside the graph.** The Relationships / Record Info surface renders
>   `links[]` today — pinned by `apps/web/src/__tests__/record-info-and-links.test.tsx:271-298`,
>   which calls `renderLinks({ links: [{ rel: 'derived_from', target: … }] })`. The live record
>   screen shows it as the **`Relationships links`** section.
> * **The graph explicitly does not own it.** Its single mention is a comment at
>   `EvidenceGraphPanel.tsx:89` saying `derived_from` links *"cannot be edges of a tree"* — i.e. the
>   graph **excludes** them from its layout.
>
> So there is **no prerequisite slice**. `EVG-001` is withdrawn; `EVG-002` has no build dependency.
> **What still binds:** `DEC-11` step 4's dependency recheck must be clean *at removal time*, and
> §38's rule stands — provenance is not removed to simplify the UI. Nothing here weakens either.
>
> **Three readings of one claim, kept in sequence because the sequence is the lesson:**
> (i) *"`/provenance` loses its only frontend caller and `derived_from` chains go invisible"* —
> second-hand, unverified, and it created a mandatory ordering;
> (ii) *"overstated twice; the residual is the multi-hop chain"* — a real correction, still wrong
> about the residual;
> (iii) **there is no chain.** Each step was closer, and only the third came from reading the code
> that defines the term.

---

## PHASE D — AMBIGUITY MODEL + CAPTURE PROVENANCE · unblocked · scientific core

| ID | Objective | Status | Depends | Key evidence / acceptance |
|---|---|---|---|---|
| CAP-001 | `search` → `finditer` + ambiguity acceptance suite | PLANNED | — | **Acceptance is the motivating case verbatim:** one sentence, `"around 425, maybe 430"` → **two candidates, neither preferred, item explicitly unresolved.** A negative control must prove the old behaviour red |
| CAP-002 | Persist the conflict grouping | PLANNED | CAP-001 | `review_required` appears **once** in `routes.py` (:15273) and **zero** times in `notes.py`/`proposals.py` — computed, served once, never stored |
| CAP-003 | Sibling proposals + **derived** grouping (Option B) | PLANNED | CAP-002 | extending `proposed_value` would break `IMMUTABLE_PROPOSAL_FIELDS`, falsify wire-serialized `PROPOSAL_TARGET_SCOPE`, change `accept_proposal`'s signature and `ACCEPTED_FROM_VALUES`, and leave OpenAPI **and** MCP contracts wrong. Option B changes **none** of the 24 fields |
| CAP-004 | Explicit `unresolved` read | PLANNED | CAP-003 | `open` conflates "unreviewed" with "deliberately undecided"; `conflict_resolution`'s `deferred` is the precedent |
| CAP-005 | *Offered*, never automatic, sibling supersession | PLANNED | CAP-004 | today accepting one sibling leaves the other open and silently stale |
| CAP-006 | Capture + proposal provenance | PLANNED | CAP-003 | today `source` is inherited from the note and `trust_basis` is always `unattributed` — **a reviewer cannot tell "my Claude" from "the CSV importer"** |
| CAP-007 | Unify the four intake classes (**DEC-15**) | PLANNED | CAP-006 | `PROPOSAL_SOURCES` already enumerates all four. **The one case against unifying is CSV** — cross-record, nowhere to live in a per-experiment document; its apply route is a committed human decision |
| CAP-008 | **Constraint, not a task:** ambiguity is assistant-side | HARD CONSTRAINT | — | the schema **does** carry uncertainty, at exactly `$.descriptors.outputs[].descriptors[].uncertainty` — descriptor-only; `context.temperature_K` has no sibling. `bounds:[425,430]` would assert an interval nobody stated. `_refuse_a_confidence` already draws this line in code |

---

## PHASE E — MCP APPLICATION-SIDE READINESS · app-side unblocked

| ID | Objective | Status | Depends | Key evidence / acceptance |
|---|---|---|---|---|
| MCP-001 | **MCP note creation + `client_request_key`** | PLANNED | CAP-006 | **THE LARGEST GAP IN THE PROGRAMME, and nobody had filed it.** There is no MCP note-creation operation and `isaac_propose_field_value` **requires** an existing `note_id` (`tools.py:1654-1657`). **Without this, not one word of a Claude conversation can enter ISAAC, even with every external gate open.** Vendor **retry behaviour is UNKNOWN** — hence the idempotency key is not optional |
| MCP-002 | Default read bounds | PLANNED | — | now a **vendor-compatibility** requirement: documented tool-result ceiling ≈ **150,000 characters**; ISAAC's unbounded reads exceed it ≈ **50×** at 1,000 runs |
| MCP-003 | `/api/health` MCP disclosure | PLANNED | — | **MCP is the only seam that says nothing about itself on the wire** — which is exactly why the hosted 404's cause is unresolvable from outside *by construction* |
| MCP-004 | Operator preflight tooling | PLANNED | MCP-003 | must prove a token's `aud` matches **character-for-character**: RFC 8707 permits audience *mapping*, ISAAC's check is exact, so a mapping AS gives a **100%-failing deployment that looks correct from both ends**. Ship the status-code decision table: 404 unmounted / 405 mounted / 403 loopback+remote / 401 OAuth-no-token |
| MCP-005 | `note` kind in the change feed | PLANNED | — | notes reach the feed today only via `_authoritative_signature` hashing, so the trigger fires on **any** authoritative change |
| MCP-006 | Proposal deep link | PLANNED | UX-011 | **no `?proposal=` parameter exists** |
| MCP-007 | `create_run` retry-ambiguity sentence | PLANNED | — | one free sentence |
| MCP-008 | `IngestionProposalsPanel` destructive-silent-failure fix | PLANNED | — | `IngestionProposalsPanel.tsx:786` — a failed background refresh replaces the list and can destroy typed text **with no user action at all**. `UnmappedNotesPanel` has the fixed shape; this one does not |
| MCP-009 | **Decision to surface, not a task:** authless remote MCP is vendor-**permitted** | PROPOSED | — | auth type `none` is documented "Supported". **So OAuth is ISAAC's choice, not a vendor gate** — a stronger and cheaper argument to Dean. **But it does not close EXT-01:** an OAuth bearer yields a `ServicePrincipal`, so **EXT-01 survives EXT-02** |

---

## PHASE F — REMOTE CONNECTOR + LIVE-CAPTURE DEMONSTRATION · externally blocked

| ID | Objective | Status | Blocker |
|---|---|---|---|
| MCP-020 | **Text-chat demonstration first** | BLOCKED | EXT-02 only. **Depends on voice/mobile availability not at all** — it exercises the identical MCP contract and converts two unverifiable capability questions into one demonstrable workflow. **Build and demo this first.** |
| MCP-021 | Voice demonstration | BLOCKED | EXT-02 + **voice+custom-connector UNKNOWN** (one observation by Krish settles it, and mobile with it) |
| SEC-001 | End-to-end proof: identity, authorization, run/experiment scope, provenance, ambiguity, retries, duplicate prevention, network failure, reconnect, session expiry, **absence of Submit authority**, **absence of hidden scientific mutation** | BLOCKED | EXT-01, EXT-02 |

---

## PHASE G — HISTORICAL IMPORT · gated on DEC-13; the shell is not

| ID | Objective | Status | Depends |
|---|---|---|---|
| **HIST-000** | **Issue the BL15-2 data request.** This is the phase's first deliverable and its gate. | **PLANNED — do this immediately on approval; it costs nothing and unblocks everything else** | — |
| HIST-001 | Import Session + Source Bundle + manifest, reusing `assets[]` pointer-only (`"NO BYTES, EVER"`) | PLANNED | CAP-003 |
| HIST-002 | First-wave deterministic parsers (filenames, directories, spreadsheet cells — needs `openpyxl`, not currently a dependency — CSV, explicit key/value) | **BLOCKED on DEC-13** | HIST-000 |
| BL15-001 | `.mac` parser | **BLOCKED — no representative file exists anywhere in reach.** §5 forbids designing against assumptions | HIST-000 |
| HIST-003 | Semantic reconstruction into the **shared** Phase-D pipeline | BLOCKED on DEC-13 | HIST-002 |
| HIST-004 | Import review surface. **Banned pattern: Upload → Spinner → Mysterious JSON** | PLANNED (shell) | HIST-001 |
| HIST-005 | Merge into the ordinary Library | PLANNED | HIST-004, LIB-003 |
| HIST-006 | Gold-standard evaluation; the headline metric is **fabricated-value rate**, not fields-filled. Every metric must name the artifact required to compute it | BLOCKED on DEC-13 | HIST-005 |
| SRC-001 | **Already satisfied — do not rebuild.** Multi-source disagreement for a value in the draft is representable **today**: `evidence_classify.asserted_values` → `conflicting_evidence` at ≥2 values; `conflict_resolution` stores `competing_values` + set-digest with `deferred` first-class; `build_sidecar` copies the **whole** evidence list, so the record carries one value and the sidecar preserves the disagreement | CONFIRMED CURRENT | — |

---

## PHASE H — IMAGES / HANDWRITING · deliberately last

`HIST-010` — PLANNED, after the non-image formats work. Source identity preserved; OCR/model output
is never truth; proposals reviewable; source image referenced; scientist decides.

## PHASE I — HARDENING AND ASSURANCE

`QA-001` full suites · `QA-002` exact-head **and merge-result** CI · `QA-003` a11y re-transcription
· `QA-004` release provenance · `QA-005` hosted QA · **`QA-006` true 200% zoom (HUMAN — no CDP
method can drive it)** · **`QA-007` narrow widths (HUMAN — `resize_window` reports success while the
rendered viewport does not follow)** · **`QA-008` real-microphone + OS-indicator check (HUMAN)**.

---

## TASKS ADDED BY THE 2026-09-12 REVISION

| ID | Objective | Phase | Status | Depends / blocked |
|---|---|---|---|---|
| `DOC-007` | Documentation truth alignment — nine measured-stale claims in `CLAUDE.md` and `docs/`. **Do this first: stale instructions steer implementation.** | 0 | **IN PROGRESS** | — |
| `UX-018` | **Project Memory demoted** to `Settings → Advanced/Developer` per **DEC-19**. **Capability and tests PRESERVED** — this is a navigation change, not a deletion. Measured stake: ~7,800 lines and 578 test cases, the largest single test mass in the app. *(I inferred this ID from the revision note, which lists `UX-018` without defining it. If Krish meant a different task by `UX-018`, correct this row rather than building the wrong thing.)* | C | PLANNED | UX-010 |
| `REV-001` | **Revision-state modelling** per **DEC-21**: a submitted snapshot is immutable; the workspace may hold `Current Working Changes` for the next snapshot. Expose revision history. **Never describe a submitted revision as mutable.** | C | PLANNED | UX-010 |
| `REV-002` | **Revision-state UI**: visibly distinguish **`Last Submitted Revision`** from **`Current Working Changes`**, show the path to the next submission, and **surface the rename trap rather than hiding it** — a rename does not move `content_signature`, so submit → rename → resubmit yields `409 already_submitted`. | C | PLANNED | REV-001 |
| `MCP-019` | **Local/synthetic end-to-end MCP proof** — `MCP client → create note → proposal/candidate → change-feed event → website Review → accept/edit/reject under an explicitly-enabled trusted TEST identity → deterministic validation`. Also prove: duplicate/retry protection, payload/read bounds enforced, provenance identifies the source channel, ambiguity stays unresolved when appropriate, **MCP cannot final Submit**, and **no production provider, account or data is needed**. **Must be green BEFORE the operator is asked to mount the production endpoint.** | E | PLANNED | MCP-001, MCP-002, CAP-004 |
| `HIST-003a` | **Provider-neutral semantic-reconstruction contract**, exercised with a **deterministic fake** over synthetic/authorized fixtures. Prove semantic output enters the shared proposal/ambiguity/conflict Review pipeline and **cannot become record truth automatically**. | G | **PLANNED — UNBLOCKED** | HIST-001 |
| `HIST-003b` | **Real BL15-2 Claude/model reconstruction.** | G | **BLOCKED** | **EXT-10** (corpus) **AND** institutional provider/data-egress approval (**DEC-22**) |

### Two rules the revision hardened, recorded here because they reverse the plan's own advice

- **`MCP-009` is REJECTED as a production route (DEC-23).** I had surfaced vendor-permitted
  **authless** remote MCP as *"a stronger, cheaper argument to put to Dean."* The owner rejected
  that: **trusted attribution is load-bearing**, so vendor permission is not a reason to drop it.
  Authless mode survives **only** for explicitly approved local/synthetic/non-sensitive smoke
  testing — never as a governance shortcut, and never for real SLAC scientific data.
- **"Zero migrations" is a TARGET, not a promise (DEC-24).** The plan's "zero migrations across all
  31 PRs, by design rather than luck" stands as intent but must never become pressure to force a
  requirement into an unsuitable existing structure. A slice that genuinely needs persistence
  **stops, documents, adds the authorization sentence, prepares the operator packet, does not
  apply it, and moves to other unblocked work.**

---

## TASKS ADDED BY THE SIX-PASS REVIEW

Recorded here so the ledger and the plan cannot disagree. Full rationale in the master plan §8–§9.

| ID | Objective | Phase | Status | Depends / blocked |
|---|---|---|---|---|
| `UX-016` | Create-vs-import fork; Historical Import empty state; first-run discovery of Pillar 2. **Found in Pass 3:** with Historical Import promoted to one of three top-level destinations, its empty state becomes a first-run surface, and nothing handled a scientist with zero experiments who wants to import rather than create | B/C | PLANNED | LIB-002 |
| `UX-017` | Statistics disposition: **REMOVE-FROM-PRIMARY** — merge `My Stats` into the Library, move `General ISAAC` under Settings. **Found in Pass 2:** it is the densest screen in the app (3 820 px, 422 visible text elements) and one of five top-level slots, and its disposition was implied but never stated | C | PLANNED | UX-010 |
| `CAP-009` | Live-capture utterance evaluation suite — seven named cases (plain value · **"around 425, maybe 430"** · correction · observation · app command · inherited value · scientific doubt), each with its expected outcome. **Found in Pass 6** as an omission against the directive | D | PLANNED | CAP-004 |
| `BL15-002` | Beamline Profile abstraction: filename patterns, directory and run-number conventions, column aliases, terminology, `.mac` conventions, stable facility identifiers, legacy vocabulary aliases. **CONSTRAINT: a Beamline Profile must not become an unofficial validator** — its role is repeatable source interpretation, and **only conventions supported by actual corpus evidence** may be encoded. **Found in Pass 6** as an omission against the directive | G | **BLOCKED** | **DEC-13 / EXT-10** |
| `MCP-001a` | Size and rate bounds on MCP note creation. **Found in Pass 4:** with EXT-01 open, an untrusted in-cluster caller could flood notes. "Inert to export" is not the same as "harmless to the record" | E | PLANNED | MCP-001 |
| `LIB-003a` | Assert `folder` reaches **no** exported record and **no** sidecar. **Found in Pass 4:** `LIB-003`'s acceptance proved the move does not shift `content_signature` but never that the value cannot reach an exported artifact — which is the only reason the design is safe. It is the property `title` already has | B | PLANNED | LIB-003 |

### Two cross-cutting facts the review established, recorded so they are not re-derived

- **Letting Claude create a NOTE does not put model output in the truth path** — the product's own
  copy already states a note is *"Stored word for word. It is not a field value and not evidence,
  and it will not appear in an exported record."* Notes are structurally inert to export. That is
  exactly why note creation is the safe MCP entry point and a direct field write is not.
- **Folders will emit change-feed traffic.** `folder` must join `_authoritative_signature` to be
  persisted at all, and the change feed keys on that signature — so **every folder move emits an
  `experiment` event and causes a bundle refetch on every open client.** It is the same cost a
  rename already pays, and it is a second, independent reason to defer folder rename (O(N) writes
  would be O(N) events).

---

## CONTINUATION PROTOCOL

Every future session starts here, in this order:

1. Read `CLAUDE.md` and `AGENTS.md`.
2. Read `2026-09-12-isaac-product-scope-v2.md`.
3. Read `2026-09-12-isaac-master-implementation-plan.md`.
4. Read **this ledger**, starting with the SESSION HEADER.
5. Read `ISAAC_PRODUCT_DECISIONS.md`.
6. Read `2026-09-12-isaac-blockers-and-risks.md`.
7. Recover fresh state: `git status -sb` · `git rev-parse HEAD` ·
   `git rev-list --left-right --count HEAD...@{upstream}` · `git worktree list` · `git stash list` ·
   `gh pr list --state open` · `gh run list --branch main` · `git tag --sort=-creatordate | head` ·
   and resolve the latest tag to a SHA with `git rev-list -n1 <tag>`.
8. Compare reality to the SESSION HEADER. **Correct the header before doing anything else.**
9. Find the first executable unblocked task. Continue from there.

**Never resume from remembered chat context. The repository plus these artifacts must be
sufficient.**

### Measurement rules that are not optional

Each exists because it was violated, and each cost real time:

- **Never report a count you did not just measure.** Quote the command.
- **Never pipe a test command to `tail`/`head` and report the exit code** — you get the pipe's
  status. This already produced a wrong suite count in this project.
- **Quote the checkout with every backend skip count.** A count taken in a git **worktree** is
  `+2` against the main checkout (`graphify-out/graph.json` is gitignored, absent from every
  worktree, and exactly two tests gate on it).
- **`rg`/`grep` over `apps/web/src` is only evidence of absence with `-a`.** A zero-hit result
  without it is indistinguishable from a skipped file.
- **Use a reader that cannot fail silently for binary content** —
  `python3 -c "print(open(f,'rb').read().count(b'\x00'))"`, not `tr … | wc -c`, which aborts on
  macOS and still exits 0 with a plausible wrong number.
- **`rm` is aliased to `rm -i`** — always `rm -f` inside a compound command.
- **Exact-head-green protects the HEAD, not the MERGE.** Before merging a PR whose base has moved,
  re-run `tsc -b` and the suite **on the merge result**. This produced two `main`-red counterexamples
  nine minutes apart.
- **Regenerate the snapshot with BOTH `--out` and `--detail-out`.** Without `--detail-out`,
  `--check` prints "ok: no drift" over a stale deep artifact.
- **Every tab this tooling drives reports `visibilityState: "hidden"`** — the change feed never
  polls, CSS transitions never advance, media loading is deferred. A "panels never refresh" finding
  measured that way is a tooling artifact, not a defect.
- **Impeccable's mechanical detector is non-functional in this environment** (negative-control
  proven: no findings, exit 0, on deliberately broken TSX). Never cite "0 findings" from it.
