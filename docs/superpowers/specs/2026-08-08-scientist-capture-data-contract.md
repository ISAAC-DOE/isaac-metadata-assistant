# Scientist-Friendly Data Capture — the data contract

**Status: contract only. No code in this document has been implemented.**
It exists so that no later slice re-derives the record mapping, and so that the parts of the
requested feature that have *no legal implementation path today* are named before anyone builds
a UI that implies otherwise.

Every claim is cited to `file:line` in this repository at `a5601e9`, or to a measured hosted
observation. Where something is inferred, it says so.

---

## 0. What was measured, and when

| Fact | Value | How |
|---|---|---|
| `main` | `a5601e9`, clean | `git status -sb` |
| Hosted commit | `a5601e9` | `GET /krish/api/health` in an authenticated browser session, 2026-08-08 |
| Hosted experiment storage | `{configured: true, backend: "postgres", durable: false, state: "unavailable"}` | same response |
| Backend tests | 2900 collected | `.venv/bin/pytest --collect-only` |
| Branch protection on `main` | absent (HTTP 404) | `gh api .../branches/main/protection` |

**`durable: false` is the load-bearing one.** Migration `0001_experiments` is not applied, so
`isaac_experiments` does not exist in the hosted database and a created experiment is not durable
there. Any demo that claims durability before that migration is applied is claiming something
untrue — `docs/migration-approval-packet-0001.md:282-289` already says so.

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

### DECISION D3 — `submitted` is the one genuinely new *stored* state

Every existing status is recomputed from `pending_count` / `draft_ok` / `export_ready` /
`record_id`. **There is no signal from which "the scientist submitted this" can be derived** — no
reviewer, no approval, no transition endpoint, no `status` column exists anywhere
(`workflow.py` is documented as never persisted, `:60-61`).

So submission is stored, and it is the *only* new stored status axis:
`submitted_utc`, `submitted_by`, `submitted_rev`.

My Experiments groups map as:

| Group | Derivation |
|---|---|
| Drafts | no submission record, `status() == needs_attention` |
| Needs Review | no submission record, `status() == in_review` |
| Ready to Submit | no submission record, `status() == ready_to_export` |
| Submitted | a submission record exists for the current revision |

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

---

## 9. Gates — who owns what

| Gate | Owner | Blocks |
|---|---|---|
| Apply `0001_experiments` | Krish / an operator with a SLAC cluster context | **all hosted durability**; the §61 hosted proof sequence steps 26-28 |
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
