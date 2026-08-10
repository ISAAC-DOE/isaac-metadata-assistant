# Scientist-Friendly Data Capture — the data contract

~~**Status: contract only. No code in this document has been implemented.**~~
**SUPERSEDED 2026-08-10 — status: PARTLY IMPLEMENTED.** The strikethrough is deliberate: the
original line is kept visible because it is the first thing a reader sees and it is now the most
misleading sentence in the file. Shipped since it was written: the **export fan-out** and the Run
model (§1), **DEFECT C1's** database-side compare-and-swap and **autosave** (§4), and **DEFECT C2's**
per-record reset precondition (§4). Still contract-only: submission (D3/D4), voice (§6), the evidence
graph (§7), and migration `0002` (§8). Per-claim detail is in the re-verification block below.

It exists so that no later slice re-derives the record mapping, and so that the parts of the
requested feature that have *no legal implementation path today* are named before anyone builds
a UI that implies otherwise.

Every claim is cited to `file:line` in this repository at `a5601e9`, or to a measured hosted
observation. Where something is inferred, it says so.

> ### RE-VERIFIED 2026-08-10 at `2209b8e` — read this before quoting anything below
>
> Ten claims in this document had gone stale. **Each is left visible with a dated correction block
> beside it** — the same convention as the "CORRECTION 2026-08-08", "RESOLVED 2026-08-09" and
> "ADDENDUM — 2026-08-09" blocks already here — so a reader sees the change of state instead of a
> silently rewritten history. Nothing was deleted.
>
> **Two are decision-level, not citation-level, and a plan built on the old text would be wrong:**
>
> - **DEFECT C1 (§4) is RESOLVED.** The upsert IS a compare-and-swap in the database. It was written
>   as "the blocking prerequisite for autosave"; that prerequisite is discharged and autosave ships.
> - **DEFECT C2 (§4) is RESOLVED.** The reset/save race is closed by a per-record precondition, with
>   nine `test_c2_*` tests. This document said "No test asserts the property."
>
> **One is layer-level:** §1's "the application is currently hard-wired 1 experiment : 1 record" is
> **superseded at the application layer** — export fan-out ships — while remaining true at the
> truth-core layer, which is intentional.
>
> The other seven are drifted citations (§2, §3 ×3, §4, §5, §6, §8). **§6's is also incomplete**, and
> that one changes an argument about cost, not just a line number.
>
> **Citation style changed, and why.** Almost all of this staleness is line drift — the failure this
> file already warned about ("this file has already broken its own citations once by growing past
> them"). Corrections below therefore cite a **`def` name, a heading, or a quoted phrase** wherever
> the file is likely to keep growing; a line number, where one appears, is stamped with the SHA it
> was read at. Re-verify before quoting.
>
> **That policy justified itself within hours, and this is measured rather than argued.** While this
> pass was running, PR #106 merged into `main` and added 144 lines to `routes.py`. **Every
> `routes.py` line number written below is therefore ALREADY STALE against `main`**, by ~124 lines:
> `def uploads` `:5262` → `:5386`; `_DB_RECON_RECORD_DISPLAY` `:6411` → `:6535`; the *"every record
> this API can currently create"* phrase `:3631` → `:3755`. **The `def`-name and quoted-phrase
> citations all still resolve unchanged.** Treat every line number here as *"where it was at
> `2209b8e`"* — a navigation hint with an expiry date — and the name or phrase as the citation.
>
> **What was re-verified as STILL TRUE and left standing** is listed in §10, added for this pass — a
> correction sweep that only removes claims leaves a reader unable to tell what survived.

---

## 0. What was measured, and when

| Fact | Value | How |
|---|---|---|
| `main` | `a5601e9`, clean | `git status -sb` |
| Hosted commit | `a5601e9` | `GET /krish/api/health` in an authenticated browser session, 2026-08-08 |
| Hosted experiment storage | `{configured: true, backend: "postgres", durable: false, state: "unavailable"}` — **SUPERSEDED 2026-08-09, see the addendum below; the value is kept because it is what was measured on 2026-08-08** | same response |
| Backend tests | 2900 collected | `.venv/bin/pytest --collect-only` |
| Branch protection on `main` | absent (HTTP 404) | `gh api .../branches/main/protection` |

**`durable: false` was the load-bearing one, at the 2026-08-08 snapshot this whole document is
pinned to.** *(The paragraph that follows is preserved as written on 2026-08-08. It is no longer
current — read the addendum immediately after it. It is kept rather than rewritten because every
other claim in this document is cited "at `a5601e9`", and silently overwriting one dated
measurement would make the rest of that provenance untrustworthy.)*

> Migration `0001_experiments` is not applied, so `isaac_experiments` does not exist in the hosted
> database and a created experiment is not durable there. Any demo that claims durability before
> that migration is applied is claiming something untrue —
> `docs/migration-approval-packet-0001.md:282-289` already says so.

*(Line reference as written on 2026-08-08, left standing inside the quote because the quote is a
pinned snapshot. The packet has since grown and `:282-289` no longer lands on that passage. It is
now at `docs/migration-approval-packet-0001.md:320-330`, under the heading "Why it was unapplied as
of 2026-08-08: no *authorized* path from **here** to that database" — the list of "the three real
reasons it was unapplied", whose lead-in has itself been re-dated to the past tense. Prefer the
heading over the line numbers; a heading does not drift when the file grows.)*

### ADDENDUM — 2026-08-09: the migration has been applied, and the row above no longer holds

**Dean applied `0001_experiments` to the hosted database on 2026-08-09.** Measured the same day in
an authenticated browser session, at hosted commit `5632300`:

`experiment_storage` now reads `{configured: true, backend: "postgres", durable: true,
state: "durable"}`, and an experiment created through the hosted UI
(`01KZM7HYJVQY1C0X3KFV805YT2`) was returned by a subsequent `GET /api/experiments` — so it
survived a fresh HTTP request. A recon run taken *after* that create still reported 30/30 records,
`rows_modified: 0`, `dml_statements_issued: 0`, `ddl_statements_issued: 0`.

**Three limits travel with that, and this spec must not be quoted without them:**

- **Pod-restart durability was NOT measured — nobody restarted the pod.** That the row is
  physically in PostgreSQL is a *structural inference* from the app's own storage-selection logic
  (the filesystem fallback engages only when `PGHOST` is unset —
  `apps/api/isaac_api/db_write.py:339-352`, `experiment_repository.py:821-860`) plus the rule that
  a failed durable write raises rather than degrading (`experiment_repository.py:84-88`). Do not
  write "verified durable across restart".
- **Migration `0002` remains unapplied and unauthorized for hosted application.** §8's requirement
  that it get its own packet and its own approval is untouched.
- **Gate G2 (hosted per-record display) remains CLOSED**; `/api/health` still reports
  `record_display: "closed"`. "0001 is applied" is not "display is open". **Gate G3** (the five
  withheld aggregates) remains OPEN.

Full evidence, with every qualification attached:
[`docs/evidence/hosted-0001-verification-2026-08-09.md`](../../evidence/hosted-0001-verification-2026-08-09.md).

---

## 1. The record mapping — decided by the schema, not by preference

### One ISAAC record is one *condition*, not one experiment

- `context.required = ["environment", "temperature_K"]` and `temperature_K` is `{"type": "number"}`
  — **a scalar** (`schema/isaac_record_v1.json`, `context` at :428). A record cannot express two
  temperatures. The same holds for `context.electrochemistry.{control_mode, potential_setpoint_V,
  current_setpoint_mA_cm2}`, which the top-level `allOf` conditionals (:29-138) *require* singly.
- `timestamps.split_operation` (:208-210) is described verbatim as *"Provenance note when this
  record was produced by splitting a multi-condition source record."* The schema authors
  anticipated exactly this split and gave it a home.
- `measurement.series[].conditions_inherited_from` is described as *"record-split bookkeeping"*.
- `tags` (:1750) is the schema's designated grouping: *"how a user groups an arbitrary SET of
  records at any granularity (campaign, material system, study) without a rigid hierarchy."*
  A campaign is **a set of records**, not one record.
- `links[]` (:1112) with `rel ∈ {replica_of, follows, same_sample_as, derived_from}` and
  `basis ∈ {matched_operating_conditions, replicate_preparation, same_sample_id,
  shared_material_batch}` is how sibling runs are re-associated — machinery that would be
  pointless if every run lived inside one record.
- `sample.sample_id` (:306): *"Two records share a sample_id if and only if they measured the same
  physical object."* Explicitly anticipates many records per physical sample.

### DECISION D1 — one Run produces exactly one ISAAC record

`Experiment` is an **application-level grouping with no schema counterpart**. It exports to *N*
records, one per Run, related by `links[]` and a shared `tags` entry.

The uniform 1:1 is a deliberate choice over the alternative (collapsing same-condition replicates
into N `series` of one record), because:

- it keeps `Check Run` (§15 of the brief), run comparison (§45), and per-run validation addressing
  a single record each, with no special case;
- the schema already provides the correct relation for replicates — `rel: replica_of`,
  `basis: replicate_preparation` — so nothing is lost;
- `measurement.qc` is **one verdict per record** (:1076). Two runs sharing a record would have to
  share a QC verdict, which is scientifically wrong when one run failed and the other did not.

**Repeat raw scans within a single run are not Runs.** The existing sample record averages six
scans into one series and parks the count in `system.configuration.n_scans: 6`
(`docs/samples/01JQZ0SYNTHXANESDEMO000000.json`). A Run is what the scientist declares as a Run.

### What this breaks, and must be changed

The application is currently hard-wired 1 experiment : 1 record.

- `src/isaac_records/export.py:135` — `transform()` mints exactly one `record_id`.
- `src/isaac_records/export.py:267-286` — `export_draft()` returns a single `ExportResult`.
- `apps/api/isaac_api/workspace.py:379` — `record_id: str | None`, **singular**, overwritten on
  re-export (`routes.py:2045`).

Export must fan out. `Experiment.record_id` becomes per-Run, and the experiment carries the set.

### SUPERSEDED 2026-08-10 — the fan-out SHIPPED. "Hard-wired 1:1" is false at the application layer and still true at the truth-core layer

The paragraph and three bullets above are kept because they correctly recorded the starting state and
because two of the three cited facts are *still true and correct by design*. What has changed is the
conclusion: **"Export must fan out" is no longer work to be scheduled — it is built.** Verified at
`2209b8e`.

**What ships (all opened and read, not inferred):**

- `Experiment.export_units()` (`apps/api/isaac_api/workspace.py`, `def export_units` at `:2647` at
  this SHA) — *"Everything this experiment exports: N records for N runs, else exactly one."* It
  returns one `ExportUnit` per `sorted_runs()` with `target_id=run.id`, and for a zero-run experiment
  returns a single unit carrying `self.draft` itself.
- **Two-phase `post_export`** (`routes.py`, `def post_export`; the phases are labelled in the source
  as `# PHASE 1:` and `# PHASE 2:`). Phase 1 validates **every** eligible unit writing nothing
  (`export_draft` is a pure transform plus two validations); a single failure means no artifact is
  written for any unit — which is D4's rule, enforced rather than merely asserted. Phase 2 writes.
- `Run.record_id` exists — `record_id: str | None = None` on `Run` at `workspace.py:905`, alongside
  the `Experiment` one at `:2172`.
- `Experiment.all_units_exported()` / `any_unit_exported()` — run-aware, deliberately *added beside*
  `exported()` rather than redefining it, because ~15 call sites pair `exported()` with
  `record_path()` to read the experiment's own single artifact.

**The three cited proofs, one by one:**

| §1's citation | State at `2209b8e` | Verdict |
|---|---|---|
| `export.py:135` — `transform()` mints exactly one `record_id` | `def transform` is at `:129`; the mint is `"record_id": record_id or new_record_id()` at `:135` | **still true, and correct BY DESIGN.** Fan-out calls `transform` N times through `export_draft(..., record_id=unit.target_id)`. The truth core legitimately did not change. |
| `export.py:267-286` — `export_draft()` returns a single `ExportResult` | `def export_draft` still at `:267`, still `-> ExportResult` | **still true, and correct by design**, for the same reason. |
| `workspace.py:379` — `record_id: str \| None`, **singular** | `:379` is now a **comment block** (the D1 rationale prose). The field moved to `:2172`, and `Run.record_id` at `:905` now exists beside it | **superseded** — cite the `def`/field, not the line. |

**State the split plainly, because collapsing it is how a wrong plan gets built:** fan-out is
**superseded at the application layer** (`apps/api/isaac_api/`) and **still 1:1 at the truth-core
layer** (`src/isaac_records/export.py`), and that split is *intentional* — the application calls a
one-record transform N times rather than teaching the truth core about experiments, which have no
schema counterpart (D1).

#### The write phase is NOT atomic — stated here because its absence above is misleading

Phase 1's all-or-nothing **validation** does **not** imply an all-or-nothing **write**, and a reader
planning a transactional Submit (D4) must not assume it does. The endpoint's own description says so
verbatim (`routes.py`, export description): *"It is NOT atomic across the individual file writes: a
fault between them can leave some records on disk with the state still saying they were not
exported."* The Phase-2 loop is `for unit, unit_result in results: _write_record(exp, unit_result, unit)`
with **no rollback**; the state is saved **once**, after every file.

The failure shape is self-healing on a clean retry, and it is **tested, not asserted** —
`test_a_fault_between_two_unit_writes_leaves_a_state_that_reconciles`
(`apps/api/tests/test_export_fan_out.py:527`) monkeypatches `routes.atomic_write_text` to raise
`OSError` on exactly the second run's record path, then asserts both halves: the first run's pair is
on disk while **no** run holds a `record_id` (the state never claims a fan-out it did not complete),
and a clean retry republishes every not-yet-exported run and converges.

**Consequence for D4.** "Submit commits N records in one transaction" is not inherited from the
export path — the export path does not provide it. Whoever builds Submit must supply the atomicity
themselves, or scope the guarantee to what the export path actually gives: all-or-nothing
*validation*, plus a converging retry.

---

## 2. Shared experiment fields and run overrides

Derived from the schema's own structure, not from intuition.

**Experiment-level (entered once, inherited by every Run):**
`sample.*` (:219) — `material`, `sample_form`, `composition`, `sample_id`;
`system.domain`, `system.technique` (:317, :327);
`system.facility.*` (:370) — `facility_name`, `organization`, `beamline`, `endstation`;
`system.instrument.*`; `attribution.contributors` (:1701); `tags` (:1750).

**Run-level (must vary — this is what forces the record split):**
`context.*` (:428) — `environment`, `temperature_K`, `electrochemistry.*`, `transport.*`,
`thermodynamics.*`; `measurement.series[]` (:959) and `measurement.qc` (:1076);
`assets[]` (:1164); `descriptors.outputs[]` (:1244);
`timestamps.acquired_start_utc` / `acquired_end_utc` (:192, :196).

### CORRECTION 2026-08-08 — the two lists above are in SCHEMA space, and half of them do not exist in DRAFT space

The lists are kept exactly as written, because they are correct *about the official
record* and the line citations are to `schema/isaac_record_v1.json`. **They are not a
usable specification of where a draft keeps things, and the first implementation of the
Run model read them as if they were.** The error is this document's, not that slice's:
nothing above says which namespace it is describing, and every entry looks like a
dotted path.

A draft (`schema/isaac_draft.schema.json`) has **two** namespaces:

1. **`draft["fields"]`** — a map of dotted official path → evidence envelope, **scalars
   only**. `sample.material.name`, `context.temperature_K`, `system.facility.beamline`,
   `timestamps.acquired_start_utc` live here.
2. **Top-level draft blocks**, siblings of `fields`, which are arrays/objects and are
   **not dotted paths at all**: `series`, `qc`, `assets`, `descriptors_outputs`,
   `attribution`, `tags`, `links`, `implicit`.

**7 of the 14 entries above are blocks, not field keys** (enumerated against
`extract/structured.FIELD_MAP` and `extract/draft_builder`):

| §2 entry (schema space) | Where a draft actually keeps it | Level |
|---|---|---|
| `measurement.series[]` | block `series` | run |
| `measurement.qc` | block `qc` | run |
| `assets[]` | block `assets` | run |
| `descriptors.outputs[]` | block `descriptors_outputs` | run |
| `attribution.contributors` | block `attribution` (`draft_builder.py:269`) | experiment |
| `tags` | block `tags` (emitted by nothing today) | experiment |
| `system.instrument.*` | field-map path — **valid**, simply never emitted | experiment |

Only `system.instrument.*` is a false alarm: it is a legitimate field-map path
(`system.properties` = `{configuration, domain, facility, instrument, technique}`) that
the current extractor has no `FIELD_MAP` entry for. The other six matched **nothing** —
`field_level("qc")`, `field_level("series")` and `field_level("descriptors_outputs")` all
returned `unclassified`, and the experiment-level `attribution` and `tags` inherited
nothing at all. Zero consequence while no code consumed them; a live trap for the export
fan-out slice, which is the one that has to know where run data lives.

**The code is now namespace-explicit** (`apps/api/isaac_api/workspace.py`):
`EXPERIMENT_LEVEL_FIELD_PATHS` / `RUN_LEVEL_FIELD_PATHS` (segment-aware prefix tests over
field-map keys) and `EXPERIMENT_LEVEL_BLOCKS` / `RUN_LEVEL_BLOCKS` (exact match over block
keys), addressed through namespaced addresses `field:<path>` / `block:<key>` — because
`tags` is both a legal official path and a block name, so a bare name is ambiguous.

Two families remain **deliberately unclassified**, and that is an answer rather than a
gap: `system.configuration.*` and `timestamps.created_utc` (real extractor output that
neither list assigns), and the draft-only blocks `meta` / `pending` / `implicit` /
`block_evidence` / `links`. Assigning a level to any of them would be an unevidenced
scientific inference of the kind `CLAUDE.md` §5 forbids.

### RESOLVED 2026-08-09 — `system.configuration.*` is left UNCLASSIFIED, and that is the answer

An open question was carried forward asking whether `system.configuration.*` can vary per Run, so
that it could be assigned to one of the two lists above. **The question's premise was wrong, and it
is recorded here as resolved by evidence rather than left open.**

**Measured against `schema/isaac_record_v1.json` at this commit.** `system.properties.configuration`
declares **no fields at all** — the node is exactly `{"type": "object", "description": …}`, with no
`properties`, no `required`, and no `additionalProperties` restriction. *(One precision, because the
prompt that raised this described the node as declaring `properties: {}`: there is no `properties`
key in it whatsoever. Same consequence — zero declared fields — but the accurate form is "declares
none", not "declares an empty set", and the difference is the kind that quietly becomes a citation
somebody later cannot reproduce.)* Its description reads:

> *"THE designated open extension namespace: instrument/station/beamline-specific configuration that
> does not generalize across facilities (slits, pass energies, GC columns, channel IDs, logbook
> fields...). Anything that DOES generalize belongs in a schema field — request one."*

So **there is nothing in the schema to classify field-by-field.** The six paths that exist in
practice are conventions of this repository's extractor, not schema fields, and they live only in
`src/isaac_records/extract/structured.py` `FIELD_MAP` — `proposal_id` and `session_id` at **:66-67**,
`monochromator_crystal`, `spectrometer_geometry`, `detector_model` and `n_scans` at **:86-89**
(verified at this commit).

**The resolution: unclassified — fail-closed, inherited by nobody.** That is the `CLAUDE.md` §5
no-guessing answer, not a deferral. Whether two Runs of one experiment may legitimately differ in
detector model is a *scientific* question, and scientific judgement is not an inference unless it is
evidenced or user-confirmed.

**It is NOT hard-coded to either scope.** Classification is per full dotted path with a
segment-aware prefix test (`sample` matches `sample.material.name`; `system.domain` must not match a
hypothetical `system.domain_notes`), so a future per-field decision — "`proposal_id` is
Experiment-level, `n_scans` is Run-level" — needs a list entry and no mechanism change.

**Do not restate this as "the schema says configuration is Experiment-level" or "…Run-level".** It
says neither. The mechanism stays neutral, and that neutrality is the decision.

**The consequence, stated as the cost it is rather than as a neutral outcome.** `proposal_id` is
obviously campaign-level to any reader, and under this resolution a Run inherits nothing from it —
the scientist re-enters it, or it is absent. That is a real product gap and a known price of failing
closed. The thing that closes it is a decision about which of the six are per-run, which is a
question for Angel/Dean (or a slice that asks the user per field), not something this spec may
settle by inference.

**Where the mechanism lives — RE-CITED AGAINST `main` 2026-08-09, as the previous revision of this
paragraph asked.** `field_level()` (`apps/api/isaac_api/workspace.py:527`) and the pinning test
`test_every_field_map_path_the_real_extractor_emits_is_classified_or_knowingly_not`
(`apps/api/tests/test_run_domain_model.py:349`) are now **on `main`**, verified at `608f587`; PR #92
merged as `d0f1028`. The earlier wording — *"it is NOT in this tree … neither exists on `main` at
`5632300`"* — was accurate when written and is superseded rather than deleted, because it is the
reason the line number moved: `field_level` was at `:502` on the unmerged branch and is at `:527`
after the merge. Re-verify before citing; this file has already broken its own citations once by
growing past them.

The test pins the exact classified/unclassified set against the **real** extractor, so a new
`FIELD_MAP` entry cannot silently default — that is the guard that makes "unclassified" a recorded
decision rather than an omission. `timestamps.created_utc` is unclassified for the same reason and is
covered by the same test.

#### CORRECTION 2026-08-10 — `field_level` drifted again, `:527` → `:528`; cite the `def`, not the line

The paragraph above is left exactly as written, because it is right about everything except the
number, and because it is the paragraph that predicted this: *"Re-verify before citing; this file has
already broken its own citations once by growing past them."* It has now done so twice.

**Measured at `2209b8e`:** `field_level` is at `apps/api/isaac_api/workspace.py:528`, not `:527`.
Command: `grep -n "^def field_level" apps/api/isaac_api/workspace.py` → `528:def field_level(path: str) -> str:`.

**`:527` was CORRECT when written, and the drift is one line — which is the point.** Confirmed
against the SHA the paragraph above names: `git show 608f587:apps/api/isaac_api/workspace.py | grep -n
"def field_level"` → `527:def field_level(path: str) -> str:`. Nobody made a mistake; the file grew by
one line above it. A citation that a single inserted line can invalidate is not a citation worth
keeping.

**Per that same warning, the citation is hereby switched to a phrase and stays that way.** Cite it as
**`workspace.py`, `def field_level`, whose docstring opens *"Classify one key of `draft["fields"]`.
FIELD-MAP SPACE ONLY."*** — findable by `grep -n "def field_level"`, and drift-proof. Its sibling
`def block_level` has drifted the same way (`:558` at `608f587` → **`:574`** at `2209b8e`) and gets
the same treatment; cite the `def`.

The line-number citation for the pinning test
`test_every_field_map_path_the_real_extractor_emits_is_classified_or_knowingly_not` is likewise
retired in favour of the **test name**, which is unique in `apps/api/tests/` and cannot drift.

### DECISION D2 — inheritance is by reference, never by copy

A Run stores *the absence of an override*, not a duplicated value. The resolved value is computed
on read. An override is an explicit, audited act that records the inherited value it displaced.

On the exported record this has a schema-native home for the series case —
`measurement.series[].conditions_inherited_from` — and `timestamps.split_operation` records that
the record came from a multi-condition parent.

---

## 3. Status and the submission boundary

### What already exists and must not be rebuilt

Two independent, **derived-on-read, never-persisted** axes:

- `Experiment.status()` (`workspace.py:569-586`) → `needs_attention` | `in_review` |
  `ready_to_export` | `done`. This is what My Experiments already groups on
  (`apps/web/src/lib/adapt.ts:49-61`, four groups, empty ones hidden).
- `workflow.derive_workflow()` (`workflow.py:39-125`) → the five-step canonical sequence with
  `completed` | `current` | `reopened` | `blocked`.

#### CORRECTION 2026-08-10 — `Experiment.status()` is mis-cited, and its check ORDER is not what the prose above implies

Both bullets are kept. The `derive_workflow` citation still holds; the `status()` one does not, and
the order matters more than the number.

**The citation.** `workspace.py:569-586` does **not** contain `Experiment.status()`. At `2209b8e`
that range is the tail of `field_level`'s body (`:569-572`) plus the opening of **`block_level`'s
docstring** (`:574-586`) — a different function in a different namespace. `Experiment.status()` is at
**`workspace.py:2995-3020`**. Command:
`grep -n "    def status" apps/api/isaac_api/workspace.py` → `2995:    def status(self) -> str:`.
**Cite it as `workspace.py`, `Experiment.status`,** whose docstring opens *"Derive status
deterministically; never stored, always recomputed."*

**The order, which is the load-bearing part.** The body, read at this SHA, is:

```python
if self.all_units_exported():
    return DONE
if self.pending_count() > 0:
    return NEEDS_ATTENTION
return READY_TO_EXPORT if self._all_units_pass_dry_run() else IN_REVIEW
```

So the real order is **`all_units_exported()` → `DONE` FIRST**, then `pending_count() > 0` →
`NEEDS_ATTENTION`, then `READY_TO_EXPORT` / `IN_REVIEW`. That is **not** the order §3's prose
implies, and it is not even the order the method's *own docstring* lists (the docstring leads with
`pending > 0 -> needs_attention`). Read the body, not the docstring.

**Why it matters to the table below, concretely.** An exported record that has been edited back into
a pending state returns **`done`**, because the `DONE` short-circuit is evaluated before
`pending_count()` is ever consulted. The four-bucket table maps `Drafts ← needs_attention`, so such a
record does **not** appear under Drafts — it appears under the terminal bucket, no matter what it
contains. (`Experiment.export_ready()`, immediately below `status()` in the source, exists precisely
because it answers the *current* drafts' readiness *without* that short-circuit; `status()` and
`export_ready()` are deliberately different questions.)

**And the table does not reconcile `done`/`exported` with a future `submitted`.** Under D3 a
submission is a new stored axis, and `done` already means "every unit holds a record id". Nothing in
this document says what an experiment that is `done` but never submitted should display, nor what a
submitted experiment whose drafts later regress should display. That is an unresolved product
question, recorded here rather than left to be discovered by whoever builds the bucket.

### DECISION D3 — `submitted` is the one genuinely new *stored* state

Every existing status is recomputed from `pending_count` / `draft_ok` / `export_ready` /
`record_id`. **There is no signal from which "the scientist submitted this" can be derived** — no
reviewer, no approval, no transition endpoint, no `status` column exists anywhere
(`workflow.py` is documented as never persisted, `:60-61`).

So submission is stored, and it is the *only* new stored status axis:
`submitted_utc`, `submitted_by`, `submitted_rev`.

#### RE-VERIFIED 2026-08-10 — D3 STILL HOLDS; only the `workflow.py` line reference is corrected

**D3 is unchanged and was re-measured, not assumed.** There is still no stored submission anywhere:
`rg --text -n "submitted_utc|submitted_by|submitted_rev|isaac_submissions" apps/api src apps/web/src`
returns **two hits, both in a test, both naming `isaac_submissions` only as a *prospective* `0002`
table name** (`apps/api/tests/test_experiment_repository.py:1238`, `:1258`). No field, no column, no
route, no state key. `submitted` remains the one genuinely new *stored* state.

**The citation inside it is off, and the fix makes the claim stronger rather than weaker.**
`workflow.py:60-61` is not the categorical statement — at `2209b8e` those lines are inside
`derive_workflow`'s docstring explaining when a step is `reopened` vs `current`. The categorical
statement is the **module docstring, `workflow.py:5-7`**:

> *"The workflow is ONE permanent ordered sequence whose per-step state is computed on read from the
> current signals only — never persisted, never reordered, never recomputed on the client."*

**The claim itself is true and is mechanically tested**, which the original citation did not say:
`apps/api/tests/test_workflow_order.py` carries `test_workflow_is_not_persisted_in_state` (`:208`) and
`test_reopened_is_derived_not_persisted` (`:140`). Cite the module docstring, or those test names —
`workflow.py` is 125 lines and will drift.

My Experiments groups map as:

| Group | Derivation |
|---|---|
| Drafts | no submission record, `status() == needs_attention` |
| Needs Review | no submission record, `status() == in_review` |
| Ready to Submit | no submission record, `status() == ready_to_export` |
| Submitted | a submission record exists for the current revision |

#### CORRECTION 2026-08-10 — the four group labels in that table DO NOT EXIST in the product

The table is kept because its **derivations** are right — each row's right-hand column is a correct
statement about `status()`. Its **left-hand column is not a description of anything.** It reads as if
"Drafts / Needs Review / Ready to Submit / Submitted" were the labels a scientist sees. They are not,
and they never have been.

**What is actually rendered**, from `apps/web/src/lib/labels.ts` (the single authored-string module),
read at `2209b8e`:

```
groupNeedsAttention: 'Needs Attention'      // :127
groupInReview:       'In Review'            // :128
groupReady:          'Ready to Export'      // :129
groupDone:           'Done'                 // :130
```

`apps/web/src/lib/adapt.ts` maps status → group (`STATUS_TO_GROUP`: `needs_attention → needsAttention`,
`in_review → inReview`, `ready_to_export → ready`, `done → done`) and `GROUP_ORDER` renders each
group's heading from `LABELS.group*`. So the product vocabulary is
**Needs Attention / In Review / Ready to Export / Done**.

**Measured, not assumed — the exact command that establishes the negative.** For each of the four
words in the table, at the worktree root:

```
rg --text -n -F "<phrase>" apps/web/src
```

- `"Needs Review"` — **0 hits.**
- `"Ready to Submit"` — **0 hits.**
- `"Submitted"` — **0 hits.**
- `"Drafts"` — hits exist, but **none is a queue-group label**: every one is the server-authored
  OpenAPI tag `"Drafts & Answers"` (`apiDocsModel.ts:15`, `test/apiFixtures.ts:2236`/`:2289`,
  `__tests__/api-docs-model.test.ts`). Different vocabulary, different surface.

*(`-F` is deliberate — the phrases are literals. `--text` is deliberate and not decorative: see the
§6 correction, where its absence silently hid a whole file from an identical search.)*

**Cost of adopting the table's words, since this section reads as though it were free.** A rename
touches the four label strings in `labels.ts` **and** the assertions that pin them.
`labels.test.ts:58` pins `LABELS.groupReady === 'Ready to Export'` verbatim, and the four rendered
strings appear across many further frontend suites. Measured by
`rg --text -l -F "<phrase>" apps/web/src/__tests__/ | wc -l`:

| Phrase | Test files containing it |
|---|---|
| `Needs Attention` | 5 |
| `In Review` | 3 |
| `Ready to Export` | **15** |
| `Done` | 3 |

*(Honest limit: that is a literal-substring count over test files, so it is an upper bound on
*files touched* and not a count of *label assertions* — `Done` in particular is a common word, and
`Ready to Export` is also a screen title (`LABELS.screenExport`, `:124`) and a lifecycle suffix, not
only a group heading. It is offered as evidence that the rename is broad, not as a precise task
estimate.)*

**A fifth vocabulary exists and this document never mentions it.** `adapt.ts` also strips a
server-authored **lifecycle title suffix** — `KNOWN_TITLE_SUFFIXES` = `' · New Draft'`,
`' · Partially Completed'`, `' · Export Review Required'`, `' · Ready to Export'`,
`' · Exported Record'` (`stripLifecycleSuffix`). Those five strings are a *third* naming of the same
lifecycle, after the backend's `status()` enum and the frontend's group labels. Any renaming slice
that touches only `labels.ts` will leave this one inconsistent.

### DECISION D4 — `Submit Record` commits *N* records in one transaction

Because of D1, experiment-level submission is not "submit a record". It transactionally persists
one record per eligible Run. Success is reported only after commit. A required validation failure
on any Run blocks the whole submission; the brief (§14) forbids a `Submit Anyway` path and no
schema or governance rule supports one.

**External agents cannot submit.** No MCP tool exposes it, ever (brief §34, §64.19).

---

## 4. Concurrency — most of this is already built

Optimistic concurrency is **fully implemented** and stricter than the brief assumes:

- `version_contract.py:16` — `_PRECONDITION_REQUIRED = True`; the grace period is retired.
- `routes.py:507-511` → **428** when `If-Match` is absent; `:514-522` → **400** malformed;
  `:525-539` → **412** stale, returning `{expected_rev, current_rev, expected_version,
  current_version}` *and* echoing the current `ETag` so a client refreshes in one hop.
- `Experiment.version_token()` = `f"{generation}.{rev}"` (`workspace.py:425-431`).
- `save_versioned()` (`:497-520`) persists only when the authoritative signature changed, and
  bumps `max(self.rev, disk_rev) + 1` — a byte-stable no-op never bumps `rev`.

New Run-level and revision-level routes reuse this machinery. Nothing here needs reinventing.

#### CORRECTION 2026-08-10 — the last two bullets are mis-cited, and `rev` is a CONCURRENCY TOKEN, not a history

The behaviour described in all four bullets still holds. Two of the citations do not, and one of the
two lands on a **different method of a different class**, which is the kind of error that produces a
confidently wrong plan.

| §4's citation | State at `2209b8e` | How confirmed |
|---|---|---|
| `Experiment.version_token()` at `workspace.py:425-431` | **`:2232-2234`.** `:425-431` is unrelated prose in a module comment block. | `grep -n "    def version_token" apps/api/isaac_api/workspace.py` → `925`, `2232` |
| `save_versioned()` at `workspace.py:497-520` | **`:2801-2876`** (`def` at `:2801`; the docstring alone now runs to `:2857`). `:497-520` is now `def parse_address`. | `grep -n "    def save_versioned"` → `2801:    def save_versioned(self) -> bool:` |

**The trap in the first row.** `grep` finds **two** `version_token` methods. `workspace.py:925` is
**`Run.version_token`** — a *different* method on a different class, added by the run-domain work,
carrying its own `<generation>.<rev>`. Anyone re-deriving §4's citation by searching for the name will
land on it first. Cite the class: **`Experiment.version_token`** (`:2232`) vs **`Run.version_token`**
(`:925`). Both return `f"{self.generation}.{self.rev}"`; they are not interchangeable.

##### `rev` / `generation` / `save_versioned` are a CONCURRENCY TOKEN. They are NOT a history.

This document never says so, and §8's talk of `isaac_experiment_revisions` / `isaac_run_revisions`
makes it easy to read the existing `rev` as one. It is not, and the difference is architectural:

- There is **exactly one row per experiment** — `isaac_experiments` is keyed `(experiment_id)`, and
  `Q_UPSERT_EXPERIMENT` is an `INSERT ... ON CONFLICT (experiment_id) DO UPDATE SET state =
  EXCLUDED.state`. The prior document is **overwritten**. No prior revision's bytes survive anywhere.
- On disk it is the same shape: `save_versioned` rewrites the one `experiment.json`
  (`Experiment.state_path`, `:2229-2230`).
- `rev` therefore answers exactly one question — *"has this changed since the token you hold?"* — and
  it is deliberately built to answer only that: a byte-stable no-op **never bumps `rev`** and never
  reaches `save()` at all, and the bump is `max(self.rev, disk_rev) + 1` so a stale instance cannot
  regress the persisted value.

**Consequence for §8/D7.** Revision *history* is entirely unbuilt. `isaac_experiment_revisions` and
`isaac_run_revisions` are not a normalisation of something that exists; they are net-new retention of
bytes that are currently discarded on every save. Budget them as such.

### DEFECT C1 — the compare-and-swap is in application memory, not in the database

**This is the blocking prerequisite for autosave.**

`Q_UPSERT_EXPERIMENT` (`experiment_repository.py:361-365`):

```sql
INSERT INTO isaac_experiments (experiment_id, state) VALUES (%s, %s::jsonb)
 ON CONFLICT (experiment_id) DO UPDATE SET state = EXCLUDED.state, updated_utc = now()
```

There is **no `rev` or `generation` predicate**. `persist()` executes it blind (`:440`). The whole
`If-Match` check at `routes.py:1857-1873` is serialised only by `record_lock`
(`workspace.py:283-303`), a `threading.Lock`.

Consequence: with two or more replicas, two clients holding the same ETag can each pass their
`If-Match` check on different pods, and the second upsert silently wins. That loses real user data
in the ordinary (durable) workspace.

**Honest limits on this claim.** The replica count is **not discoverable from this repository** —
k8s manifests live in the Dean-owned `ISAAC-DOE/isaac-k8` and no `replicas:` token exists in any
in-repo YAML. At exactly one replica the defect is unreachable. The code itself contemplates more
than one (`experiment_repository.py:98-100`: *"With more than one replica, a health read answered
by a healthy process cannot know about a sibling's outage"*). So: **latent, unreachable at one
replica, unverifiable from here, and cheap to close.**

Fix direction — no migration required, because it changes a statement and not a schema: make the
conflict clause conditional on monotonic `rev` and use `RETURNING` to detect the no-op, raising a
conflict that surfaces as the 412 the API contract already promises. The `rev`-equal case needs
care: `save()` is reached on paths that do not bump `rev`, so a naive `<` predicate would refuse
legitimate writes.

### DEFECT C1 — RESOLVED 2026-08-10. The compare-and-swap IS in the database.

**Everything above is kept, and every sentence of it is now historical.** It is the single most
consequential stale claim in this document: it is labelled *"the blocking prerequisite for
autosave"*, and a plan built on it would schedule work that is already done and would treat autosave
as blocked when it ships. Verified at `2209b8e` by opening each site.

**The statement is no longer blind.** `Q_UPSERT_EXPERIMENT` is at
`apps/api/isaac_api/experiment_repository.py:540-550` (was cited `:361-365`), and it carries a
three-clause CAS predicate plus `RETURNING`:

```sql
INSERT INTO isaac_experiments (experiment_id, state) VALUES (%s, %s::jsonb)
 ON CONFLICT (experiment_id) DO UPDATE
 SET state = EXCLUDED.state, updated_utc = now()
 WHERE COALESCE(isaac_experiments.state ->> 'generation', '')
    <> COALESCE(EXCLUDED.state ->> 'generation', '')
    OR COALESCE((isaac_experiments.state ->> 'rev')::bigint, 0)
     < COALESCE((EXCLUDED.state ->> 'rev')::bigint, 0)
    OR isaac_experiments.state = EXCLUDED.state
 RETURNING experiment_id
```

Read the three clauses as one rule: **accept if the generation differs** (a different record lineage —
e.g. a reset minted a fresh generation), **or if `rev` strictly advances**, **or if the document is
byte-identical** (an idempotent retry must not be reported as a conflict). Everything else is refused.
The `rev`-equal hazard the fix direction warned about is handled by that third clause, not ignored.
`rev` and `generation` are read out of the stored `jsonb`, which is why **no migration was required** —
exactly as predicted.

**The refusal is detected, attributed and surfaced, not merely emitted:**

- **No-op detection** — `accepted = cursor.rowcount == 1` (`:671`). A conflict action whose `WHERE`
  is false updates nothing and raises nothing; `rowcount` over `RETURNING` is what makes that silence
  observable.
- **Winner read back in the same transaction** — `Q_ONE_EXPERIMENT` is executed on the not-accepted
  branch (`:674-675`) so the 412 can report the `rev` that actually exists.
- **`DurableWriteConflict`** (`experiment_repository.py:195`) is raised *after* the `with` block
  (`:684`), deliberately outside it, so the blanket `except Exception` cannot relabel a refusal as an
  outage. `_note_storage_success()` fires either way — a lost race is not evidence of a sick
  database, and `/api/health` must not start reporting one because two writers raced.
- **412 fallback** — `routes.py` `_save_versioned` catches it and returns `_stale_write(conflict.current_experiment(exp), ...)`,
  i.e. the 412 the API contract already promised; `app.py:185` registers
  `durable_write_conflict_handler` for any that escape.
- **Local winner adoption, to avoid wedging** — `Experiment._adopt_winner_locally`
  (`workspace.py:2358`, called at `:2345`) copies the winner's document into the local workspace file
  before re-raising. Without it a strict CAS introduces a wedge it can never leave: every subsequent
  mutation computes `max(self.rev, disk_rev) + 1`, which is the rev the row already holds, so the
  predicate refuses that write and the next one and the next — a permanent 412 over reads still
  serving the stale local file.
- **Pinned by test** — `test_the_upsert_predicate_is_a_compare_and_swap_and_not_a_blind_overwrite`
  (`apps/api/tests/test_experiment_repository.py:1844`), plus a family of lost-race tests asserting
  the 412 surfaces, that it is *not* a 503, and that it does not mark the deployment unhealthy.

**The prerequisite is discharged. Autosave shipped** — `apps/web/src/lib/useRunAutosave.ts`, consumed
by `RunCard.tsx` (`useRunAutosave` at `:50`/`:90`), with per-card `saving` / `saved` / `failed` /
`conflict` states in a `role="status"` region, and covered by `apps/web/src/__tests__/run-workspace.test.tsx`.

**DO NOT UPGRADE THIS INTO A MULTI-REPLICA SAFETY CLAIM.** What is verified is what the predicate
does and that the refusal path is wired end-to-end. The **replica count is still not discoverable
from this repository** — the original honest-limits paragraph above stands unchanged on that point,
and no observation in this pass touched a deployed pod or a database. The correct summary is: *the
race is now decided by the database rather than by one process's memory*, which is strictly stronger
than before and is not the same sentence as "multi-replica safe".

### DEFECT C2 — the reset/save race (the one §4B asked about)

Real, self-documented, and **narrower than C1**. `workspace.py:1381-1387` states it outright: a
per-record writer does not take `_reset_lock`, so a write can land between the digest check
(`:1572-1576`) and the per-id mutation (`:1598`).

- **Bounded to the worked-example session.** `reset_to_canonical_seed` requires a session id and
  refuses `None` (`:1556`), so the ordinary workspace is structurally unreachable.
- **Can lose data:** a confirmed answer that returned HTTP 200 inside the window is destroyed, and
  the response's `at_risk` summary under-reports by exactly what it destroyed (computed at `:1566`
  from the pre-write snapshot).
- **Cannot overwrite newer with older in the reverse direction** — every mutation reloads inside
  `record_lock` and re-checks `If-Match`, the reset mints a fresh `generation` per id (`:1534`),
  and `save_versioned` refuses to regress `rev`.
- **No test asserts the property.** `test_reset.py:356-367` looks like it covers reset-vs-write but
  its creator thread creates *new* records and its only contract is `assert errors == []`.

Autosave makes the loss modestly more likely and *false refusals* dramatically more likely, since
`_plan_digest` covers `version_token` and the authoritative signature (`:1455-1465`) — an
autosaving UI would make Reset nearly un-executable rather than lossy.

Fix direction: re-check each record's digest row *inside* its own `record_lock` before removing it,
and abort with the existing `plan_digest_stale` refusal. ~10 lines, no new lock, preserves the
documented lock ordering.

### DEFECT C2 — RESOLVED 2026-08-10. The fix direction above was implemented, essentially verbatim.

Kept as written, and now historical. **This one is flagged specially because the re-verification
brief for this pass listed C2 among the claims to confirm as *still true*. It is not.** The check was
run anyway, which is the point of running it.

**Every line number in the C2 block above is now wrong, by roughly 2,400 lines.** `workspace.py` grew
from 1,663 lines at `a5601e9` to 4,400+ at `2209b8e`, and the reset machinery moved wholesale. None of
`:1381-1387`, `:1556`, `:1566`, `:1572-1576`, `:1598`, `:1534` or `:1455-1465` lands on reset code any
more — `:1381-1387` is now a comment about a *different* defect (C6, fan-out validation), and `:1556`
and `:1598` are override- and evidence-related prose. **Do not chase them.** Use the names:
`reset_to_canonical_seed`, `_reset_lock`, `_plan_digest`, `_plan_digest_row`, `_current_plan_row`,
`_at_risk_summary`, `validate_tutorial_session_id`.

**The window is closed by a second, PER-RECORD precondition.** `reset_to_canonical_seed`
(`workspace.py:4142`) now checks the precondition **twice** — once workspace-wide over the whole
classification, and then again per record, inside that id's own `record_lock` and before that id is
touched, by rebuilding that one record's row via `_current_plan_row` (`:3999`) and comparing it to the
row classified at the top (`planned_rows`, `:4234`). A mismatch aborts that id unmutated and refuses
with the existing `plan_digest_stale` reason. The module says it in its own words at `_reset_lock`
(`:3844-3851`):

> *"**C2 closes it by making the precondition PER-RECORD as well** … The write therefore either
> SURVIVES or the reset REFUSES — never neither. `record_lock` still keeps the filesystem consistent;
> the row re-check is what keeps the outcome honest."*

**The architecture the defect rested on is unchanged, deliberately.** A per-record writer
(`/answers`, `/edit`, `/export`) still does **not** take `_reset_lock`, and never will — putting a
workspace-wide lock on the hot mutation path would invert the documented lock ordering and create the
very two-lock cycle the deadlock-freedom argument rules out. So a write can still *land* in the
window; what changed is that it can no longer be *destroyed in silence*.

**"No test asserts the property" is the sentence that most needs retracting.** There are now **nine**
`test_c2_*` tests in `apps/api/tests/test_reset_safety.py` (`rg --text -c "^def test_c2" apps/api/tests/test_reset_safety.py`
→ `9`), including
`test_c2_a_write_to_a_managed_legacy_record_in_the_window_is_not_removed` (`:952`),
`test_c2_a_torn_read_in_the_window_refuses_with_a_body_instead_of_raising` (`:1271`) and
`test_c2_an_export_self_heal_in_the_window_is_not_destroyed` (`:1345`). *(The old citation
`test_reset.py:356-367` still lands on `test_concurrent_execute_is_safe` at `:361`, and the criticism
of it stands — it is not the C2 test. The C2 tests live in a different file.)*

**Three consequences a later slice must not re-derive:**

- **The digest row is no longer a pure function of the in-memory `Experiment`.** It also stats whether
  each half of the artifact pair is on disk, because an export **self-heal** durably republishes a
  record while `save_versioned()` returns `False` (`record_id` did not move) — a 200 that moved no
  state component and was previously destroyed in silence. **Before adding any new filesystem write
  to a record's directory, check the row can see it**; a write the row cannot see is a write this
  guarantee does not cover.
- **A refusal is no longer always "made no changes".** A workspace-wide refusal still mutates
  nothing, but a per-record abort part-way leaves the ids *before* it already reset — which is why
  `final_count` / `plan_digest` / `at_risk` are **measured from disk** in that case rather than echoed
  from the snapshot. A partial reset is the deliberate price of never destroying an acknowledged
  write.
- **Statement order inside the lock is load-bearing:** `planned_rows` is built **before**
  `plan_digest`. Built second, it picked up the very repair the per-record check exists to notice,
  matched it, and waved the reset through — *"which is exactly how the fix for that defect failed its
  own test"*.

**What this does to the autosave paragraph above.** The predicted data *loss* is gone. The predicted
**false refusals** are not — autosave still drives `version_token` and the authoritative signature,
which the plan digest covers, so an autosaving UI can still make Reset hard to execute. That is now
the honest failure mode: **Reset refuses more often; it no longer destroys.**

---

## 5. Storage — what the schema actually wants

### DECISION D5 — ISAAC stores references and hashes, not bytes

This is not a workaround for missing infrastructure. It is what the schema specifies.

`assets[]` items (`schema/isaac_record_v1.json:1164`) are
`required: ["asset_id", "content_role", "uri", "sha256"]` with **`additionalProperties: false`**
and property set `{asset_id, caption_highlights, caption_verbatim, citation, content_role,
figure_label, media_type, notes, page, paper_conclusions_about_figure, sha256, uri}`.

There is **no `content`, `data`, `bytes`, `blob`, `path`, or `size` slot, and none can be added
without changing the official schema.** `content_role` includes the literal value
**`raw_data_pointer`** — a named role for "this asset is a pointer". The drafting path uses an
external archive scheme, `ssrl-archive://` (`src/isaac_records/extract/file_listing.py:20`), and
that module states it *"NEVER computes or invents a `sha256` — the hash is a downstream
`user_confirmation` blocker"* (`:6-9`), precisely because ISAAC never holds the bytes.

So the file model is: **the scientist's file stays where it lives; ISAAC records a URI, a
content_role, a media_type and a scientist-confirmed sha256, and links that asset to one or more
Runs.** One asset row, many Run links — which also satisfies the brief's §27 "store once, link
many" requirement without any byte store at all.

### What genuinely does not exist, and what each would cost

| Capability | State today | Gate |
|---|---|---|
| Durable raw-file storage | **None.** `POST /api/uploads` is an unconditional 403 taking no parameters (`routes.py:3151-3157`); `python-multipart` is not a dependency (`pyproject.toml:23`), so FastAPI *cannot* parse a form; there is no `write_bytes`/`wb` call anywhere in `apps/api/` or `src/` | byte store (PVC or S3) in Dean-owned `isaac-k8`, **plus** lifting "upload writes — NOT authorized" (`CLAUDE.md:775`), plus content validation that does not exist |
| Workspace durability | `ISAAC_UI_WORKSPACE`, asserted `emptyDir` by in-repo docs — **but the manifest is not in this repo** and zero `emptyDir`/`persistentVolumeClaim` tokens exist in any in-repo YAML. Unverifiable here | Dean |
| Exported artifacts in the DB | Not persisted; only `state` jsonb is (`experiment_repository.py:37-44`) | later slice |
| Audio / voice / ASR | **Nothing.** No `MediaRecorder`, no `SpeechRecognition`, no ASR client, no audio `source_type` | see §6 |

#### CORRECTION 2026-08-10 — the uploads citation drifted; the BEHAVIOUR is unchanged

Row 1 cites `routes.py:3151-3157` for the unconditional 403. **The behaviour is exactly as
described** — re-read at `2209b8e` and still an unconditional 403 taking no parameters, under the
section banner `# --- 15. uploads (always blocked) ---`, with the handler's own comment *"Governance
seam: no multipart is declared or parsed; no file is read or stored."*

Only the line numbers moved: `def uploads()` is now at **`routes.py:5262`**, its decorator at
`:5232-5260`. `grep -n "def uploads" apps/api/isaac_api/routes.py` → `5262:def uploads():`.
**Cite the section banner or `def uploads`** — `routes.py` is over 6,000 lines and grew ~2,100 lines
under this citation alone.

*(Unchecked in this pass, and therefore not re-asserted: the `python-multipart` and `write_bytes`/`wb`
claims in the same row. They were not part of the re-verification brief. Treat them as
**as-of-`a5601e9`** until someone re-measures them.)*

---

## 6. Voice — the part of the brief with no legal path today

Three independent blockers, all measured:

1. **No byte store, so raw audio cannot be retained server-side.** The brief (§29) offers the
   scientist "keep audio with experiment". There is nowhere to keep it. Building that choice would
   be a fake integration, which §64.24 forbids.
2. **No approved transcription provider.** There is no ASR client and no model provider of any
   kind. Note that the obvious "free" fallback is *not* free of governance: the browser
   `SpeechRecognition` API in Chrome transmits audio to a third-party service, which is an external
   egress of potentially scientific speech and is exactly what §54 prohibits without approval.
   **This must be confirmed against current vendor documentation before it is either used or
   ruled out** — it is stated here as a design risk, not as an established fact.
3. **Adding an audio `source_type` is a truth-core change.** `src/isaac_records/models.py:29-38`
   enumerates seven source types, none audio-related, and the frontend's `SRC_CLASS` /
   `SOURCE_ICON` are total `Record<SourceType, string>` maps (`EvidenceRow.tsx:5-13`) that break
   on an eighth member.

#### CORRECTION 2026-08-10 — blocker 3's citation is wrong AND incomplete. There are THREE total maps, not two, and this is an argument about cost.

Blocker 3 is kept, and its **conclusion is strengthened, not weakened** — which is why this matters:
§6 is an argument that adding audio is expensive, and it undercounted.

**What is wrong.** It places `SRC_CLASS` *and* `SOURCE_ICON` together at `EvidenceRow.tsx:5-13`. Only
the first is there. Verified at `2209b8e`:

| Total map | Location | Value type |
|---|---|---|
| `SRC_CLASS` | `apps/web/src/components/EvidenceRow.tsx:5-13` — **correct as cited** | `Record<SourceType, string>` |
| `SOURCE_ICON` | **`apps/web/src/components/icons.tsx:76-84`** — *not* `EvidenceRow.tsx`, which merely imports it (`:2`) | `Record<SourceType, LucideIcon>` |
| `SOURCE_TYPE_PHRASE` | **`apps/web/src/lib/experimentGraph.ts:417`** — **missed entirely by this spec** | `Readonly<Record<SourceType, string>>`, `Object.freeze`d |

All three are **total** over `SourceType` (the seven-member union at `apps/web/src/lib/types.ts:17-25`),
so all three fail `tsc` on an eighth member. Consumers of `SOURCE_ICON` are also wider than one
component — `EvidenceTrailPanel.tsx` indexes it at `:34` and `:119`.

**A fourth map exists and deliberately does NOT belong on that list:** `_SOURCE_PHRASE` in
`apps/web/src/lib/adapt.ts:642-647` is `Record<string, string>` with only four entries and a
fallback (`_SOURCE_PHRASE[st] ?? \`cited from ${st}\``). It is **partial by design** and would *not*
break — it would silently emit `"cited from audio"`. Which is arguably worse than a compile error,
and is worth knowing when scoping the change.

##### How this was missed, and the search rule that follows

`apps/web/src/lib/experimentGraph.ts` **contains a NUL byte** — `file` reports it as `data`, not as
text. Consequently:

```
rg -n "Record<SourceType" apps/web/src        # → 2 hits.  MISSES experimentGraph.ts. Exit 0.
rg --text -n "Record<SourceType" apps/web/src # → 3 hits.  Correct.
```

Plain `grep` is worse: `grep -n "SourceType" apps/web/src/lib/experimentGraph.ts` printed **nothing
and exited 1** on a file that contains the string on line 417 — indistinguishable from "not present".
`grep -a` / `rg --text` both find it.

**Rule: any exhaustive inventory over `apps/web/src` must pass `--text`, and a zero-hit result in
that tree is not evidence of absence until it has been re-run with it.** This trap has bitten this
project before; this is its first recorded appearance inside this spec.

**Cost restated.** Adding an audio `source_type` touches `src/isaac_records/models.py` (truth core),
**three** total frontend maps in three files across `components/` and `lib/`, and leaves a fourth,
partial map emitting an unreviewed fallback string. §6's "two maps in one file" framing understated
it.

### DECISION D6 — the honest v1 is transcript-only, provider-abstracted, audio never persisted

- Audio is captured in the browser and **never leaves it except to a configured, approved
  transcription provider**. With no provider configured, the recorder is not offered at all — not
  offered-and-broken.
- The **transcript** is JSON text, so it *can* be persisted in the existing `state` jsonb with no
  new storage of any kind. Retention choice therefore applies to the transcript, which is real,
  and not to raw audio, which has nowhere to go.
- `TranscriptionProvider`, `CaptureExtractionProvider` and `AssistantProvider` are three separate
  seams (brief §30). Default implementation for all three: **unconfigured**, surfaced truthfully.
  A deterministic fake provider exists for tests only and is never reachable in production.

---

## 7. Evidence graph contract

Derived deterministically from structured application state. No embeddings, no model, no Graphify.

**Nodes:** `Experiment` (root) · `Run` · `Sample` · `Context` · `Measurement` · `Asset` ·
`Descriptor` · `EvidenceEntry` · `ValidationFinding`.

**Edges — only these, each backed by a stored relation:**
`has_run` · `performed_on` · `measured_under` · `has_context` · `has_descriptor` ·
`references` (Run→Asset, from the run-asset link) · `supported_by` (field→EvidenceEntry, from the
sidecar) · `derived_from` · `validated_by` · `conflicts_with` (only where a stored conflict exists).

**Prohibited:** any edge asserting scientific causality. The graph carries the fixed disclosure
*"Edges show recorded schema, evidence, and provenance relationships — not inferred scientific
causality."*

Freshness: computed from current state on read. If cached, invalidated by the experiment's
`version_token`. The stale-index failure mode documented for Graphify in `CLAUDE.md` §7 must not
recur — a graph whose answers look authoritative while being stale is worse than no graph.

The existing Evidence plane (`EvidenceExplorer.tsx`, `EvidenceTrailPanel.tsx`, `EvidenceRow.tsx`,
`SourcePreview.tsx`) is **retained unchanged**; the graph is added beside it as
`Evidence List | Evidence Graph`.

---

## 8. Persistence shape, and why a second migration is needed

`from_state` is legacy-tolerant — verified by hydrating a row lacking `rev`, `updated_utc` and
`generation`, which produced `rev=0` and a deterministic fallback generation. **So adding optional
keys to the `state` document requires no migration at all.**

That tempts a design where Runs live inside the experiment's `state` blob. **Rejected**, on the
brief's own §5 requirement that Runs be independently persisted and loaded and that no single
enormous object become unusable at high run counts: one jsonb document rewritten on every autosave
keystroke, containing *N* runs, is precisely that object.

### DECISION D7 — Runs and revisions are relational rows; each row's document stays jsonb

This keeps 0001's stated rationale (`0001_experiments.sql:23-32` — the document shape is owned by
the truth core, and a column-per-field schema would drift) while making a Run the unit of write.

New tables for migration `0002` (names indicative):
`isaac_runs` · `isaac_experiment_revisions` · `isaac_run_revisions` · `isaac_assets` ·
`isaac_run_assets` · `isaac_submissions`.

Two constraints that shape the migration and are easy to trip:

- `db_write.OWNED_TABLES` is a closed `frozenset` of exactly
  `{isaac_schema_migrations, isaac_experiments}` (`db_write.py:124-129`). **Every new table needs a
  code edit there as well as a migration file**, or the write policy refuses it.
- `_FORBIDDEN_KEYWORDS` includes `alter` (`db_write.py:202-217`). `0002` must therefore be pure
  additive `CREATE ... IF NOT EXISTS`. It cannot alter `isaac_experiments`.

`0002` requires its own approval packet and its own explicit approval (brief §51). It must not be
applied to the hosted database by an agent.

### CORRECTION 2026-08-10 — the first constraint is ALREADY SATISFIED for `isaac_runs`; the second still binds

Both bullets are kept. The first now describes work that is done, and reading it as outstanding would
schedule a code edit that already exists.

**`db_write.OWNED_TABLES` is no longer the two-member set quoted above.** At `2209b8e`
(`apps/api/isaac_api/db_write.py:132-138`) it is:

```python
OWNED_TABLES: frozenset[str] = frozenset(
    {"isaac_schema_migrations", "isaac_experiments", "isaac_runs"}
)
```

`isaac_runs` was added for `0002_runs`, and the module says why in its own comment (`:125-131`):
listing a table *"grants nothing on its own"* — it is the deliberate, reviewable act that lets a later
slice write it. **The general rule the bullet states is still correct** (a table must be listed here
before its own `CREATE` can run; the migration file alone is not enough) — it simply no longer names
outstanding work for `isaac_runs`. The other five tables §8 proposes
(`isaac_experiment_revisions`, `isaac_run_revisions`, `isaac_assets`, `isaac_run_assets`,
`isaac_submissions`) are **not** listed, so for those the bullet stands unchanged.

**The second bullet still binds, and is the one to keep.** `_FORBIDDEN_KEYWORDS`
(`db_write.py:212`, consulted at `:297`) still includes `alter`, so **`0002` must remain purely
additive `CREATE ... IF NOT EXISTS` and cannot alter `isaac_experiments`.** Unchanged.

**`0002` is APPLICATION-INERT, which the section does not say and which changes how to reason about
the risk.** The migration file `apps/api/isaac_api/migrations/0002_runs.sql` exists, but **no
application code reads or writes `isaac_runs`** — pinned by
`test_0002_is_inert_for_this_build_no_statement_names_isaac_runs`
(`apps/api/tests/test_experiment_repository.py:1461`). So applying it would change nothing
observable in the running application: it creates a table nothing touches. Runs today persist inside
the experiment's `state` jsonb, not in `isaac_runs`.

**That is an argument about blast radius, NOT an authorization.** Applying `0002` to the hosted
database remains **NOT authorized** and remains the owner's act, not an agent's — the final sentence
above is unchanged and unconditional. "Inert" narrows what could go wrong; it does not narrow who may
do it.

---

## 9. Gates — who owns what

| Gate | Owner | Blocks |
|---|---|---|
| ~~Apply `0001_experiments`~~ — **RESOLVED 2026-08-09, applied by Dean** (evidence: [`hosted-0001-verification-2026-08-09.md`](../../evidence/hosted-0001-verification-2026-08-09.md)). The row is kept, not deleted, so a reader can see this gate existed and how it closed. | was: Krish / an operator with a SLAC cluster context — in the event, **Dean**, by a route this repository does not record | **nothing now.** It formerly blocked all hosted durability and the §61 hosted proof sequence steps 26-28. The **pod-restart** step of that sequence is still unrun. |
| Apply `0002` (runs/revisions) | Krish, after a packet | hosted Runs |
| Byte store for files/audio | Dean (`isaac-k8`) + lifting `CLAUDE.md:775` | durable file upload, raw-audio retention |
| Transcription provider | Dean / Angel | any voice capture at all |
| Native model provider | Dean / Angel | the embedded assistant |
| MCP org configuration | SLAC org admin, pending an official-docs audit | `Connect Your Agent` |
| Branch protection | Dean (admin; this token has `WRITE`) | nothing — do not block development on it |

**Not blocked by any of these:** the record fan-out, the Run model, C1 and C2, autosave against a
local/CI Postgres, My Experiments grouping, the Run workspace and schema accordion, inherited
fields, Check Run, Unmapped Notes, conflict UI, the evidence graph, run comparison, Validate &
Review, revisions, and the MCP server implementation.

### RE-VERIFIED 2026-08-10 — the gate table STANDS, unchanged

Re-read at `2209b8e`. **No gate changed owner and no gate opened.** Two precisions:

- **Hosted per-record display is still closed by default** — `_DB_RECON_RECORD_DISPLAY = "closed"`
  (`apps/api/isaac_api/routes.py:6411`), served in the health/recon payloads at `:975` and `:6546`.
  Gate **G2** is unchanged. This is a *literal constant*, not a computed state: it is closed because
  the database owner has not decided otherwise, exactly as `docs/postgres-test-db-guide.md` requires.
- **The "not blocked" list has partly *completed* rather than merely stayed unblocked.** The record
  fan-out, the Run model, **C1** and **C2** are now built, not pending — see the corrections in §1
  and §4. The row saying they are unblocked was never wrong; it is simply no longer the interesting
  fact about them.

---

## 10. What was RE-VERIFIED as still true (added 2026-08-10)

A correction sweep that only deletes risky claims leaves a reader unable to tell what survived. These
were re-measured this pass and **stand unchanged**:

| Claim | Status | Basis |
|---|---|---|
| **DECISION D3** — `submitted` is the only genuinely new *stored* state | **STILL TRUE** | No `submitted_utc` / `submitted_by` / `submitted_rev` / `isaac_submissions` exists in `apps/api`, `src` or `apps/web/src` except two *prospective* mentions in one test. No status column, no transition endpoint, no reviewer. |
| **`workflow.derive_workflow` is never persisted** | **STILL TRUE, and mechanically tested** | `workflow.py:5-7`; `test_workflow_is_not_persisted_in_state`, `test_reopened_is_derived_not_persisted`. Only the *line reference* in §3 was wrong. |
| **§9 gate table, incl. hosted per-record display closed by default** | **STILL TRUE** | `_DB_RECON_RECORD_DISPLAY = "closed"`, `routes.py:6411`. |
| **`0002` must be purely additive** (`alter` is a forbidden keyword) | **STILL TRUE** | `_FORBIDDEN_KEYWORDS`, `db_write.py:212`. |
| **`POST /api/uploads` is an unconditional 403** | **STILL TRUE** (citation moved) | `routes.py:5262`. |
| **`export.py` mints one record id per `transform()` call, and `export_draft` returns one `ExportResult`** | **STILL TRUE, and correct by design** | The truth core was legitimately not changed by fan-out. |
| **D1 / D2 / D5 / D6 / D7, §7's evidence-graph contract, §2's schema-space field lists** | **NOT re-verified this pass** | Out of scope for this sweep. Treat as **as-of-`a5601e9`**. Absence from this table is not a defect claim. |

**DEFECT C2 was on the list to confirm as still true, and it is NOT** — it is resolved. See §4.

### Known-stale CODE COMMENTS, reported not changed (2026-08-10)

Found while verifying the above. **Deliberately left in place** — this was a docs-only pass and each
file is a code slice's business, some held by concurrent PRs. Recorded here so they are not
rediscovered from scratch. All verified at `2209b8e`.

1. **`apps/api/isaac_api/workspace.py:392-410`** — the fan-out to-do list asserts
   `Experiment.status` / `pending` / `export_ready` are **"ALL THREE ARE RUN-BLIND"** and that this is
   **"UNREACHABLE TODAY — no route touches runs and nothing creates one in production"**. **Both
   clauses are now false.** `status()` consults `all_units_exported()` and `_all_units_pass_dry_run()`
   over `export_units()`; and runs are creatable over HTTP —
   `POST /api/experiments/{experiment_id}/runs` (`routes.py:2916-2917`), `PATCH .../runs/{run_id}`
   (`:3019-3020`), `POST .../runs/{run_id}/check` (`:3235-3236`).
2. **`apps/api/isaac_api/routes.py:3631`** — the export description calls a record with no runs
   *"every record this API can currently create"*. **False**, for the same reason as (1). It is
   **mirrored verbatim** into `apps/web/src/test/apiFixtures.ts:2495` and referenced by
   `apps/web/src/__tests__/fan-out-null-render.test.tsx:204`, so **all three must change together** or
   the fixture-parity assertions break.
3. **`Run.version_token`'s docstring** (`workspace.py:925-932`) — *"No route consumes it yet."*
   **Stale.** Routes consume it at `routes.py:2423`, `:2426`, `:2511`, `:3015`, `:3231`, `:3323`, and
   `PATCH .../runs/{run_id}` takes the run's own `If-Match` (`:2364`).
4. **`Override.to_state`** (`workspace.py:658-665`) — the comment claims omitting `displaced` keeps
   *"displaced no inherited value"* and *"displaced an inherited null"* distinguishable on disk.
   **Measured false:** the guard is `if self.displaced is not None`, so an explicit inherited `null`
   is omitted exactly like an absent one, and `from_state` reads both back via
   `state.get("displaced")` → `None`. The encoding cannot represent the second case. The *comment* is
   wrong; whether the *behaviour* should change is a design question, not a docs one.
