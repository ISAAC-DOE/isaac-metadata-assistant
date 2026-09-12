# ISAAC Product Scope V2 — North Star

**Status:** **APPROVED — IMPLEMENTATION AUTHORIZED 2026-09-12.**
**Created:** 2026-09-12
**Authorizing instruction:** project-owner planning directive of 2026-09-12 ("ISAAC PRODUCT SCOPE V2"),
relayed in-session. This is an owner instruction, not an artifact this repository can witness — the
same evidentiary class §15 uses for operator testimony. A reader can check the BOUNDARY written here;
a reader cannot check from inside the repository that the instruction was given. **Only Krish can
confirm that.**
**Companion artifacts:** [`2026-09-12-isaac-master-implementation-plan.md`](2026-09-12-isaac-master-implementation-plan.md) ·
[`ISAAC_EXECUTION_LEDGER.md`](ISAAC_EXECUTION_LEDGER.md) ·
[`ISAAC_PRODUCT_DECISIONS.md`](ISAAC_PRODUCT_DECISIONS.md) ·
[`2026-09-12-isaac-ux-ia-plan.md`](2026-09-12-isaac-ux-ia-plan.md) ·
[`2026-09-12-isaac-blockers-and-risks.md`](2026-09-12-isaac-blockers-and-risks.md)

---

> ## STATUS CHANGED 2026-09-12 — IMPLEMENTATION AUTHORIZED
> Krish approved moving from planning into implementation. The planning gate is **CLEARED**.
> Every external-owner, security, migration and data-governance boundary in this document is
> **UNCHANGED**. Decision statuses are reconciled in
> [`ISAAC_PRODUCT_DECISIONS.md`](ISAAC_PRODUCT_DECISIONS.md) — read that first where it disagrees
> with prose written before the gate cleared. Source: `2026-09-12-plan-review-and-revisions.md`.


## 0. Verified state this document was written against

Measured at the start of the planning run, not quoted from a prior session report.

| Fact | Value | How verified |
|---|---|---|
| Canonical checkout | `/Users/krishverma/Documents/ISAAC` | `pwd`, `git remote -v` |
| Canonical remote | `origin` = `ISAAC-DOE/isaac-metadata-assistant` | `git remote -v` |
| Branch / tree | `main`, clean | `git status --short --branch` |
| HEAD | `2f9a1133bcda7f45e1d751110641d1322586f60e` | `git rev-parse HEAD` |
| Upstream divergence | `0 0` | `git rev-list --left-right --count HEAD...@{upstream}` |
| Worktrees | one (the main checkout) | `git worktree list --porcelain` |
| Stashes | none | `git stash list` |
| Open PRs | none | `gh pr list --state open` |
| CI for HEAD | run `34709792004`, `success` | `gh run list --branch main` |
| Release for HEAD | **`v0.0.232`** | `git rev-list -n1 v0.0.232` resolves to `2f9a1133…` |
| Image publish | `Build and Push to GHCR` run `34711838575`, `success` | `gh run list --branch main` |

**Three corrections to the supplied checkpoint.** It reported PR #247's CI "still in progress" and
"no release for `2f9a1133` claimed": **both are now resolved** — CI concluded `success` and the
release gate admitted `v0.0.232`, cross-checked by tag→SHA resolution. It also did not record that
the deployment had rolled out; it has (next table).

### Hosted deployment — OBSERVED, 2026-09-12

The project owner authenticated their own browser session and the hosted app was then observed
**read-only**. No credential was entered by an agent, no mutation was performed, and no record
content was read. This is the first hosted observation this repository can point at in some time,
and it closes part of a long-standing `HOSTED QA PENDING` item — the **rollout**, not the QA.

`GET https://isaac.slac.stanford.edu/krish/api/health` → `200`:

| Field | Hosted value | Significance |
|---|---|---|
| `commit` | `2f9a1133…` | **hosted is at current `main` HEAD** — `v0.0.232` has rolled out |
| `mode` | `synthetic-only` | unchanged |
| `database.record_display` | `closed` | gate **G2** still closed, as designed |
| `database.contains_production_derived_records` | `true` | unchanged |
| `experiment_storage.backend` / `durable` | `postgres` / `true` | **durable persistence is live in production** |
| `run_projection.last_pass` | `{complete:0, stale:0, never_projected:0, unavailable:3, mismatch:0}` | **all three hosted experiments have an unreadable run projection** |
| `submission.blockers` | `["no_attributable_actor"]` | **one blocker, not two** — locally it is `["no_durable_storage","no_attributable_actor"]` |

`GET /krish/api/about` → `200`, same `build_commit`, `record_schema_version 1.05`,
`persistence "durable"`. `GET /krish/api/providers/capabilities` → `200`,
`any_provider_configured: false`, transcription and capture-extraction seams `unconfigured`.

**`GET https://isaac.slac.stanford.edu/krish/api/mcp` → `404 {"detail":"Not Found"}`** — while
`docs/` cites that exact URL. This is the single most consequential measured fact for Pillar 1 and
is carried into the blocker matrix rather than buried here.

---

## 1. The product, in one sentence

> **ISAAC helps scientists capture new experiments and recover historical experiments into
> organized, provenance-rich, scientist-reviewed, deterministically validated scientific records.**

And in the form a scientist would recognize:

> Capture today's science. Recover yesterday's science. Keep it organized. Preserve where every
> claim came from. Let scientists resolve uncertainty. Deterministically validate the resulting
> record.

## 2. What narrowed, and what that costs

ISAAC is **not** becoming a general "Automate Science" platform. It is becoming a two-job product
with one durable home. The sophisticated architecture underneath stays; the scientist-facing
surface gets smaller.

**What this scope change buys:** a product a beamline scientist can learn in one sitting.
**What it costs, stated plainly rather than left to be discovered:** several capabilities that
already work — the Evidence Graph visualization, the Schema and Vocabulary browsers, the Endpoint
Explorer, Project Memory, the always-present Assistant rail — stop being first-class destinations.
None of them is deleted by this document. Demotion is a navigation decision; deletion is a
separate decision requiring its own dependency analysis, and §40 of the authorizing directive
forbids conflating them.

## 3. Target users

Unchanged from the recovered product definition, and this is deliberate — the narrowing is about
surface, not audience.

- **Beamline and laboratory scientists** recording conditions and interpreting results. The primary
  user. Must not need Claude Code, a terminal, a local MCP server, an API key, or Python.
- **Interns and data curators** translating heterogeneous source material into ISAAC records. The
  primary user of Pillar 2.
- **Reviewers** verifying evidence, conflicts, and readiness.
- **Domain owners** (Angel) who decide scientific classification questions ISAAC must never decide.
- **Operators** (Dean) who own SLAC infrastructure, migrations, authentication boundaries and
  provider configuration.
- **External AI clients** — a scientist's own Claude — operating through a least-privilege MCP
  interface. A client, never an authority.

## 4. The two pillars

### Pillar 1 — New Science: capture work while it is happening

A scientist should be able to create or open an Experiment, focus a Run, speak naturally or type,
capture observations and changing conditions, **preserve uncertainty rather than resolve it**,
produce proposals, review mappings, accept / edit / reject, validate, and come back later.

The preferred ordinary-scientist path under investigation is **Claude Voice or Claude Chat → remote
ISAAC MCP connector → safe ISAAC operations**. That path is currently blocked at the first hop: the
hosted MCP endpoint answers `404`.

### Pillar 2 — Historical Science: recover fragmented work that already exists

Filename conventions, directory structures, spreadsheets, CSV, Google Sheets and Docs, READMEs,
plaintext, Markdown, run and macro files including `.mac`, beamline-specific text formats, and
eventually photographs of written notes — reconstructed into candidate Experiments, Runs, metadata,
provenance, ambiguities and conflicts, then put through **the same** scientist-review and
validation system as Pillar 1.

**The pilot is SSRL BL15-2** (canonical identifier to be confirmed from primary evidence before any
identifier is hard-coded; note that `bl152-users` and `bl152-staff` are Authentik groups and
explicitly **not** ISAAC roles).

> **PILLAR 2 IS BLOCKED ON DATA, NOT ON ENGINEERING.** Measured this session: this repository
> contains **no historical BL15-2 source material at all** — zero `.mac` files, zero `.xlsx`/`.xls`
> files, anywhere in the tree. Everything under a beamline-shaped filename in `examples/` is
> machine-generated synthetic content from `scripts/make_synthetic_examples.py`, with fictional
> people and a fictional year-2099 session, labelled `SYNTHETIC` in its own header. `openpyxl` is
> not even a project dependency. Designing a `.mac` parser now would be designing against zero
> measured examples, which §5's no-guessing rule forbids. The first Pillar 2 deliverable is
> therefore a **data request**, not a parser.

### The third responsibility that carries both

**The Experiment Library** — find saved Experiments, organize them, return later, continue drafts,
search, filter, sort, browse Runs, see what needs review, validate, inspect provenance, reach
imported historical work, and create a revision from submitted work. This is core product
behaviour, not secondary functionality.

## 5. Two surfaces, and why the website is not optional

The architecture question that must be answered explicitly: *if Claude Voice + MCP becomes useful,
is the product now Claude, with ISAAC a hidden backend?*

**No.**

| Claude should excel at | ISAAC website should excel at |
|---|---|
| hands-free narration; conversational interaction | the Experiment Library; folders and organization |
| semantic interpretation; clarification | durable scientific state; Runs; structured metadata |
| natural language; historical semantic reconstruction | capture history; proposal review |
| heterogeneous-document reasoning | ambiguity resolution; conflict review |
| proposing mappings; identifying ambiguity | **deterministic validation** |
| asking clarifying questions | provenance and source inspection |
| calling safe MCP operations | Historical Import sessions; revisions; submission and export |

The test that settles it: **a scientist must be able to return six months later and understand an
Experiment from ISAAC alone, without locating the original Claude conversation.** A conversation is
not a durable provenance record. That single requirement is why the website stays canonical.

## 6. The scientific authority model — unchanged, and load-bearing

These are **hard constraints**, not preferences, and this scope change does not touch one of them.

- The assistant may accelerate curation; it may **not** decide scientific truth.
- **Deterministic validation is the truth plane.** The Record Validator **stays**. It is not
  replaced by a model, and it is not weakened to simplify the UX. What changes is its
  *presentation*.
- The official schema and approved vocabulary outrank prose, model output, Graphify, or remembered
  convention.
- Missing facts stay missing. Ambiguous facts stay **visibly uncertain** until a scientist accepts
  them.
- A proposal becomes authoritative only after explicit scientist acceptance through the server's
  concurrency and audit boundaries.
- Provenance proves where a claim came from, **not** that the claim is correct.
- No external agent performs final Submit. **Claude may never Submit.**
- Client-supplied identity is never authoritative.
- **One Run produces exactly one ISAAC record.** A submitted Experiment fans out to one official
  record per eligible Run.
- Fail closed when identity or provider trust is absent. No fake `Connected`. No model output in
  the truth path.

## 7. Ambiguity is a product requirement, not an edge case

> "Temperature is around 425, maybe 430."

ISAAC must **not** silently select 425 or 430. It must preserve the original statement, the
uncertainty, candidate 425, candidate 430, the unit context if explicit, the proposal target if
safely known, the provenance, and the requirement that a human review it. The scientist may then
choose 425, choose 430, enter another value, or **leave it unresolved**.

The historical analogue is the same shape:

```
README        -> 425 C
Spreadsheet   -> 430 C
.mac source   -> setpoint 430 C
```

Show the evidence and the disagreement. Decide nothing.

**Do not invent range semantics.** If the official schema has no native uncertainty or range
representation at the target path, the candidate set is an assistant-side (draft / sidecar)
construct and ambiguity must be resolved to a single value **before** export. That is a constraint
on the model, not a reason to collapse the candidates early.

## 8. In scope

Application-side, and each item inherits the existing authorization boundaries in `CLAUDE.md` §15
unless a new committed sentence is added there:

1. Product-shell and information-architecture simplification.
2. The Experiment Library as the website home, with search, sort, status facets and organization.
3. Application-level folders, with folder membership as **organization only** — moving an Experiment
   must not change scientific metadata, record identity, Run values, or any validation result.
4. A small task-focused Experiment workspace set.
5. Reopening and editing saved work, including the UX-visible "Edit Experiment" over a submitted
   revision, preserving audit history.
6. A shared candidate / ambiguity / conflict model serving live capture **and** historical import.
7. Source-evidence provenance for conversational and historical candidates.
8. MCP application-side readiness: safe-operation taxonomy, proposal creation, least-privilege
   reads, deep links, change-feed targeting, bounded payloads.
9. Historical Import as an explicit, auditable workflow (Import Session, Source Bundle, manifest,
   deterministic parse, review, merge into the Library).
10. Validator **presentation** improvement.
11. Native capture retained with a deliberately-decided role.
12. Tests, documentation, migration artifacts, PRs, and safe integration for all of the above.

## 9. Out of scope, and why

Not deferred by taste — withheld by an owner, a boundary, or a decision already taken.

| Out of scope | Why |
|---|---|
| Autonomous scientific decision-making; experiment or equipment control | never the product |
| AI final Submit | rejected decision; scientist is final authority |
| Claude embedded in ISAAC through MCP | technically false — MCP is client→server; ISAAC cannot call Claude over it |
| A production external model or transcription provider | endpoint, credential, network path, billing, approval — Dean **deferred D1–D9** |
| Identity / role enforcement | conditional on a trusted authentication boundary ISAAC has not built |
| Applying any migration to the hosted database | the operator's act; no agent may do it |
| `isaac-k8` or SLAC infrastructure changes; bypassing Authentik | not ours |
| Hosted per-record display | gate **G2**, closed by default by the database owner |
| The five withheld aggregates | gate **G3**, open question for Dean |
| Graphify as a truth layer | rejected |
| Evidence Graph as a primary scientist destination | narrowed by this document |
| An apply route for `POST /ingestion/csv/preview` | a **committed human decision** — reconciliation-only is a deliberate authority boundary, **not residual work** |
| Storing large scientific file bytes in the official record | the schema models pointers and hashes |
| Universal all-beamline ingestion immediately | BL15-2 first, and honestly |
| Images / handwriting before the core historical formats work | sequencing decision |
| Requiring ordinary scientists to use Claude Code or manage tokens | contradicts the target user |
| New slash commands | existing project rule |
| Angel's scientific classifications | not an agent's to make |

## 10. Success criteria

A scientist, unaided, can:

1. Open ISAAC and understand what is theirs, what needs review, and what is ready.
2. Create an Experiment and a Run, and enter shared metadata once.
3. Capture new science by speaking or typing, with uncertainty preserved.
4. Import a historical source bundle and see what ISAAC thinks it found **and why**.
5. Review proposals, ambiguities and conflicts in one consistent place.
6. Answer only the questions that actually block export.
7. Understand a validation verdict without reading JSON.
8. Trace any accepted value to its source.
9. Return months later, find the Experiment, and continue.
10. Correct submitted work through a revision without understanding version-control machinery.
11. Submit, and know that nothing but their own action did so.

And the product must be able to demonstrate, with evidence:

- no fabricated scientific value reaches a record;
- no ambiguity is silently collapsed;
- every accepted value has a traceable source;
- the deterministic verdict is unchanged by any of this.

## 11. The non-negotiable test for every future slice

Two questions, both of which must be answerable before a slice merges:

1. **Which committed sentence authorizes what this slice did?** "It seemed covered" is not an
   authorization basis. This repository records **five** occasions on which a table or a statement
   class reached the write path before any committed sentence named it.
2. **What did this slice claim that it did not verify?** This repository's dominant defect class is
   not broken code — it is a true-looking claim beside green tests. Every honesty guard listed in
   the verification plan exists because that happened.
