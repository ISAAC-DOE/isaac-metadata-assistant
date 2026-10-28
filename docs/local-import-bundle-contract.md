# ISAAC Local Import Bundle — contract v1

Status: **v1.1.0** (LOCAL-2, 2026-10-28; v1.0.0 introduced by LOCAL-1 the same day). Machine contract:
[`apps/api/isaac_api/local_import/bundle-v1.schema.json`](../apps/api/isaac_api/local_import/bundle-v1.schema.json)
(JSON Schema draft 2020-12) plus the checks in
[`bundle.py`](../apps/api/isaac_api/local_import/bundle.py) `validate_bundle` that JSON
Schema cannot express. Producer: `isaac import <folder-or-zip> --out <dir>`.

**A bundle is NOT an official ISAAC record.** `is_official_record` is the schema constant
`false`, `readiness.official_record_ready` is the constant `false`, and every bundle carries
`official_record_notice`. It is extraction output plus its evidence. An official record is
produced only by `isaac export` from a reviewed draft, and judged only by
`isaac validate --official` (CLAUDE.md §1, §4).

## 1. What produces it

`isaac import` runs on the scientist's own machine with no server and no database. The
reading is `historical_import.read_local_archive(path)` → `read_archive_at(root, …)`, which
is **the same chain the hosted Historical Import runs** (`read_archive` resolves a committed
fixture or `staged:` name, then calls the same `read_archive_at`). There is no second parser.
Parity is a test (`test_local_import_engine.py`): for the multi-operator corpus and the gold
mini corpus, the fixture route, the `staged:` route and the local-path route produce identical
`ArchiveReading.to_state()` except `root_label` / `archive_name` / `inventory.root_label`
(what the archive is *called*), and identical candidates.

Reading an archive imports neither FastAPI nor `isaac_api.routes`: the field-path derivations
the engine needs moved to `isaac_api/field_paths.py`, which `routes` re-exports as the same
objects. The vendored schema is located by one resolver, `isaac_api/schema_locator.py`
(`ISAAC_SCHEMA_PATH`, then an upward search, then a fail-closed `SchemaNotFound`).

## 2. Files in a bundle directory

| File | What it is |
|---|---|
| `bundle.json` | The full v1 bundle. Validated before it is written; nothing is written if it fails. |
| `summary.md` | Compact, scientist-readable (target ≤ 6 KB; 3.0 KB on the 9-run fixture). Says it is not a validated official record. |
| `runs.json`, `conflicts.json`, `questions.json`, `unread_files.json` | Sections of `bundle.json` with their `total`, for direct reading. |
| `reading.full.json` | The raw engine state (`ArchiveReading.to_state()` + every candidate's `to_state()`), for lookup. Not the contract. |

`--force` overwrites only these seven files and deletes nothing. `--out` inside the folder
being read is refused (the next import would read the bundle as a source).

## 3. Sections

| Section | Content | Authority |
|---|---|---|
| `generator` | tool, version, engine, `isaac_commit` (from `.git` files, else `null`), walker, classifiers, readers (+ versions), naming profiles, the `--profile` request | — |
| `source_root` | the folder/ZIP **name**, kind, counts, truncation; `local_only: true`. `local_root_hint` (absolute path) only with `--record-local-root` | source evidence |
| `sources[]` | one per inventoried file: relative path, classification, reader outcome, size, `content_sha256` (computed by the walk over the bytes read on this machine), naming profile per source, `local_only: true` | source evidence |
| `unread_files[]` | every file no reader read, and every member the walk refused, with a reason code. What a later AI step may read | source evidence |
| `experiment` | beamtime-level context candidates, element evidence, temperature statements. Context only — never copied onto a run | evidence / extraction |
| `samples[]` | run groupings by the filename group token, with the sample-name readings. A grouping, not a confirmed identity | extraction |
| `runs[]` | one per measurement unit: stable `run_key` (file name + bytes, never the legacy number), label, scans, declaring macros, note rows, duplicate-legacy flags (`legacy_number_shared`, `shares_legacy_number_with`), candidates, conflicts, contributors, data-quality notes, signal-selection *suggestion* | extraction |
| `contributors[]` | people the sources name — **evidence** (`role: provenance`, `is_actor: false`, `is_naming_profile: false`), each with witnesses. Separate from the naming profile and from the run | source evidence |
| `naming_profiles[]` | the convention bindings in force and how many sources each read | extraction |
| `candidates[]` | every value the engine produced, with state, evidence and eligibility | extraction |
| `conflicts[]` | every disagreement: run-level, field-level and corpus-level (duplicate legacy numbers, macros declaring never-acquired targets), each reading with all its witnesses and the engine's non-authoritative recommendation | evidence + extraction |
| `missing_values[]` | each writable target path no source states (per run, or per record for record-scope paths). `value: null`, always | — |
| `unmapped_statements[]` | references to candidates with no official field (kept as evidence) | extraction |
| `extended_context[]` | ISAAC Extended Context (Level 4) entries, verbatim | source evidence |
| `data_quality_notes[]` | the files' own notes remarks, verbatim; `writes_qc_status: false` | source evidence |
| `questions[]` | what a scientist is asked: one per conflict, one per needs-review value that has a field | — |
| `ai_interpretations[]` | **empty in v1 output**; schema defined now for a later slice | extraction-interpretation |
| `scientist_decisions[]` | **empty in v1 output**; schema defined now for a later slice | scientist confirmation |
| `validation` | bundle-schema result at write time; `official_record_validation: not_applicable` | deterministic validation |
| `readiness`, `counts`, `bounds`, `authorities` | derived summaries; see §7 for bounds | — |

## 4. The four authorities — kept distinct

1. **Source evidence** — what a file literally says, at a locator. Never rewritten;
   normalisation is recorded *beside* the literal (`evidence[].normalization`), not over it.
2. **Extraction / interpretation** — what deterministic readers, stored rules and (later) AI
   interpretations made of the evidence. Suggestions. An AI interpretation can raise a value
   to `needs_review` and never higher.
3. **Scientist confirmation** — `scientist_decisions[]` only. The sole producer of
   `scientist_confirmed` and `rejected`. Recorded by the local user;
   `decided_by.basis: self_reported_local_user` says this build cannot verify identity.
4. **Deterministic schema validation** — the official schema and validators. They judge
   official *records*, not bundles. A bundle is checked only against bundle-v1.

## 5. Evidence model

One value can have many witnesses. Each candidate carries `evidence[]`, one entry per
witness, never one flattened origin:

```
{evidence_id, source_id, relative_path, locator, statement_key, literal_value,
 method: deterministic_parser | stored_rule | ai_interpretation | scientist_answer,
 method_id,              # reader id (e.g. bl15_spec_acquisition_v1) or rule id
 relation: supports | contradicts | context,
 reading_index,          # which disagreement reading this witness states, else null
 normalization: [{step, rule_id, from, to, unit}]}
```

Derived from the engine's `SemanticCandidate`: `supporting_statements` (witnesses that
`support` the value), `disagreement` (each reading's witnesses, `contradicts`, with
`reading_index`), `resolved_by_rule` (`method: stored_rule`), `supporting_source_ids`, and the
engine's own `SourceEvidence` (reader id and normalisation rule) looked up by
`(concept, locator)`. The engine keeps a *window* of supporting statements; `evidence_total`
says how many the value rests on and `evidence_truncated` says when the list is a window.

## 6. Value states

`source_recorded | candidate_extracted | needs_review | conflicting | scientist_confirmed |
rejected | unmapped | missing`. Mapped from the EXISTING contracts — not a second machine:

The single key is `SemanticCandidate.review_status` (itself derived from `kind`, `determinism`, `unresolved_reason`, `not_proposable_reason`, `resolved_by_rule` and the target path); `bl15/mapping.py` statuses are listed only as what they usually produce — measured on the 9-run fixture, `deterministic`/`normalized` concepts also land in `needs_review` (e.g. a local-time timestamp) and `needs_domain_review` lands in `unmapped` 3 times.

| Existing contract | Bundle `extracted_state` |
|---|---|
| `SemanticCandidate.review_status == "ready"` (field kind, a target path this build can write — `field_paths.PROPOSAL_TARGET_PATHS` — no `unresolved_reason`, no `not_proposable_reason`) — on the fixtures always mapping status `normalized` or `deterministic`. The server would let a person open a proposal (`proposals.STATE_OPEN`) for it | `candidate_extracted` |
| `review_status == "needs_review"`: a target path exists but something holds the value — mapping `needs_domain_review`, `blocked_by_build` (no write path), local time with no zone, a structural run/experiment candidate, a beamtime-scope value, a logbook sentence with no value | `needs_review` |
| `review_status == "sources_conflict"` (`unresolved_reason == "sources_disagree"`) | `conflicting` |
| `review_status == "unmapped"` (field kind, `target_field_path is None`; mapping `not_expressible`) | `unmapped` |
| `review_status == "resolved"` (a stored convention rule or standing resolution applied) and proposable | `candidate_extracted` (`method: stored_rule`) |
| `review_status == "resolved"`, not proposable | `needs_review` |
| a writable target path no candidate states for that run (or for the record) | `missing` |
| extended context, data-quality notes, contributors | `source_recorded` |

| Recorded later | `value_state` | Proposal-lifecycle analogue |
|---|---|---|
| `scientist_decisions` `confirm` / `choose_reading` / `provide_value` | `scientist_confirmed` | `proposals.STATE_ACCEPTED` (which on the server also needs a trusted actor) |
| `scientist_decisions` `reject` | `rejected` | `proposals.STATE_REJECTED` |
| `ai_interpretations` on a `missing` / `unmapped` / `candidate_extracted` value | `needs_review` | — (an interpretation is never a proposal acceptance) |

The derivation is `bundle.derive_value_state(extracted_state, decision, interpreted)`; the
validator recomputes it for every candidate, missing value and conflict and refuses a bundle
whose stored `value_state` differs. `scientist_confirmed` and `rejected` are **not**
`extracted_state` values (schema enum), so parser output cannot produce them; a hand-edited
`"value_state": "scientist_confirmed"` with no decision is contract-invalid. A later decision
for the same target supersedes an earlier one (last wins). A conflict stays `conflicting`
under an AI interpretation. **Missing stays missing**: no default, no room-temperature
assumption, and a beamtime fact is never copied onto a run (DEC-69: environment, reaction
and cell type are never filled from a beamtime statement); `missing_values[].value` is the
schema constant `null`.

### Eligibility for an official record

`eligibility_for_official_record: {eligible, reason}` per value. **Rule: eligible only when
`value_state == scientist_confirmed` AND there is a value AND the target path has a write
route in this build (`PROPOSAL_TARGET_PATHS`).** Nothing a parser or AI produced is eligible
on its own — not even `candidate_extracted`, because on the server such a value still needs
a trusted person to accept the proposal. "Eligible" means "may be carried into a draft for
review and `isaac export`", never "is official". Every v1 bundle `isaac import` writes
therefore has `readiness.eligible_value_count == 0`.

## 7. Bounds

Enforced by the builder (refuse, or clamp visibly and count) and by the validator.

| Constant | Value | Why |
|---|---|---|
| `MAX_RUNS` | 5,000 | one run per acquisition at most; the walk inventories ≤ `ArchiveLimits.max_entries` (5,000 = 4× the measured 1,192-file corpus) |
| `MAX_CANDIDATES` | 4,000 | the engine's own `MAX_CANDIDATES_PER_SESSION`; ~1,000 measured on the real corpus. Engine truncation is reported in `bounds.candidates_truncated_by_engine` |
| `MAX_EVIDENCE_PER_CANDIDATE` | 256 | the engine keeps 5 supporting statements plus every disagreement reading; past 256 the list is a window with `evidence_truncated: true` |
| `MAX_STRING_CHARS` | 20,000 | above the engine's longest stored prose (12,000); a longer string is clamped with a visible marker and counted in `bounds.strings_truncated` |
| `MAX_BUNDLE_BYTES` | 64 MiB | 1,168,848 bytes on the 9-run fixture; a laptop-safe JSON load. `load_bundle` refuses an oversize file before parsing it |

`isaac bundle list` pages (`--limit` 1–200, `--offset`) and always reports `total`,
`omitted_before` and `omitted_after`; nothing is truncated silently.

## 8. Data minimisation

- Every source reference is **relative to the source root**; `relative_path` may not be
  absolute or contain `..` (schema + validator). A crafted ZIP member whose name is absolute
  or escapes the root is listed in `unread_files` with its name **withheld**.
- `source_root.label` is the folder/ZIP *name*. The absolute local path is recorded only as
  `source_root.local_root_hint`, only with `--record-local-root`, and is off by default.
- `local_only: true` on every source and unread file: these refer to files on the
  scientist's machine. **A remote server cannot open a local path** — a bundle sent anywhere
  carries descriptions, digests and literals, never access to the files.
- Nothing is extracted from a ZIP to disk; symlinks are never followed; no source is ever
  executed (macros are read as text; a test proves a macro containing shell text runs
  nothing).

## 9. Versioning

- `format` is fixed: `isaac.local-import-bundle`. `format_version` is semver.
- **Every object in the schema is `additionalProperties: false`**, so a validator only
  accepts fields its own schema declares. Consequently:
  - the **1.1.0 schema accepts 1.0.0 bundles** (every 1.1.0 addition is optional);
  - a **1.0.0 validator does NOT accept a 1.1.0 bundle** — it rejects the new fields. A
    reader must check `format_version` and validate with a schema at least that new.
    (The 1.0.0 text said "a v1.0 reader must still validate it after ignoring unknown
    optional fields"; that was inconsistent with `additionalProperties: false` and is
    withdrawn.)
- **Patch** (1.x.y): documentation or validator fixes that accept and refuse the same bundles.
- **Minor** (1.x.0): additive, optional fields and widened enums only.
- **Major** (2.0.0): any removal, rename, type change, new required field, or change to the
  state derivation or the eligibility rule; a new schema file.
- The value-state set and the rule that only `scientist_decisions` produce
  `scientist_confirmed` are part of the major version.

### What 1.1.0 added (LOCAL-2)

- `record_groups[]` (one record = one sample, one technique, one set of conditions; filled by
  LOCAL-P): `{group_id, experiment_key, member_run_keys[], basis{sample, technique,
  environment, conditions{<name>:{value, candidate_ids[]}}}, split_reasons[], status,
  questions[]}`. `status` is `proposed` unless a decision says `confirm` →
  `scientist_confirmed`, `split` → `split`, `merge` → `merged`, `reject` → `rejected`.
- `processing_results[]` (LOCAL-P): `{group_id, protocol_id, protocol_version,
  protocol_status, source, inputs[], steps[], outputs{files[{role, relative_path, sha256}],
  e0_eV, edge_step, points}, qc{metrics, verdict}, comparison, state}`. Named by
  `result_id`, else `<group_id>:<protocol_id>@<protocol_version>`. Without a decision `state`
  is `candidate_extracted` or `needs_review`; `approve` → `scientist_confirmed`, `reject` →
  `rejected`, `needs_changes` → `needs_review`.
- `exposures[]` — the blind protocol (§11).
- Decisions `correct`, `defer`, `split`, `merge`, `approve`, `needs_changes`;
  `decided_by.identity: "local_unverified"` (always) and `decided_by.orcid_claimed`
  (`basis: claimed_for_credit_not_authentication`). A decision on a CONFLICT also governs
  its candidate (the later of the two decides). `defer` decides nothing.
- Questions of kind `missing_value` — ONLY for values the official record REQUIRES
  (`bundle.required_record_paths`: the vendored schema's root `required`, the `required` of
  `sample`/`system`/`context`/`measurement`, recursed, plus the conditional rules that apply:
  `record_type: evidence` → `descriptors`, potentiostatic/galvanostatic → the set-point),
  ordered by record group (else run), record scope first.
- Candidate `readings` (the raw disagreement readings, the ONE index space for
  `chosen_reading_index`), `observed_literals_total`/`observed_literals_truncated`,
  `standing_resolution`; evidence `locator_kind` (`source_file` | `described` |
  `unlocated`); conflict `resolution` (a stored rule resolved it: `value_state:
  needs_review`, never confirmed); run `shares_file_name_with`, and a conflict of kind
  `same_file_name_different_folders` for acquisitions sharing a name in different folders.
- Eligibility additionally applies the target field's own checks: a `*_utc` value must be a
  zoned instant; the vendored schema's `enum` and `type` at that path.
- The validator re-derives `review_status`/`extracted_state` from each candidate's own
  facts, refuses a decision-free value no witness states and no recorded normalisation
  produced, requires a `conflicts[]` entry for every disagreement, and recomputes `counts`
  and `readiness.blocking`.

## 10. Exit codes (`isaac import` / `isaac bundle`)

0 ok · 1 `check` found the bundle invalid · 2 usage (bad arguments, unknown profile, the
local import package not installed) · 3 input refused (not found, not a folder or ZIP,
symlinked root, unreadable) · 4 output refused (`--out` non-empty without `--force`, a
file, or inside the source folder) · 5 bounds exceeded or self-validation failed — nothing
written · 6 not found (no bundle, or no object with that id).

Install for use from any directory: `scripts/install_local_cli.sh` (creates or reuses
`.venv` with Python ≥ 3.11, `pip install -e .`, and one `.pth` file pointing at
`<checkout>/apps/api`; touches neither system Python nor Docker).

## 11. Blind cross-checking

`exposures[]` records the first time each command printed a target's parser value
(`bundle show candidate|conflict|run|question`, `bundle list candidates`, `bundle reveal`);
the exposure is written BEFORE anything is printed, and if it cannot be written nothing is
printed. `summary.md` shows no non-conflicting parser value. `bundle annotate --blind` is
honoured only when no exposure exists for that target; otherwise the interpretation is
stored `blind: false` with the reason. `bundle list candidates --no-values` and
`bundle excerpt` (raw source text, re-read through the guarded walk, refused if the file's
sha256 changed) record nothing. `bundle crosscheck-plan` lists high-value targets with
locators and no values, and reports coverage: checked, blind-checked, unchecked — spot
checks, never a claim of verification. **Limit:** the CLI cannot see anyone read
`bundle.json`, `runs.json` or `reading.full.json` directly; a blind claim is only as good as
that discipline.

## 12. From bundle to official record

- `isaac bundle build-records <dir>` → `drafts/<group_id>.draft.json` (the repository's
  draft envelope) + `.composition.json` per `scientist_confirmed` record group. Values come
  only from eligible candidates, answered `missing_values`, and the group's APPROVED
  processing result (series from its normalised file, sha256-checked; qc `pass`→`valid`,
  `fail`→`failed`, `warn` unmapped; E0 → descriptor `edge_position`, uncertainty
  `basis: not_reported` unless the result reports one). Beamtime-scope confirmed values apply
  to every record except environment, reaction and cell type (DEC-69). Two confirmed values
  that differ inside one group fill nothing and are listed. Every required value nobody
  supplied is a `status: missing` envelope, listed; nothing is defaulted.
- `isaac bundle validate <dir>` → `validation/<group_id>.json`: `validate_draft`, the export
  DRY RUN `validate_official` +
  `check_exactness` (vendored v1.05), the offline upstream portal check, every error and
  warning verbatim, a plain summary, and `schema_drift` (vendored-only / upstream-only
  schema errors, the unknown-temperature case, and portal requirements for fields the
  vendored schema does not declare). Verdicts: `incomplete`,
  `invalid_official`, `portal_check_unavailable`, `portal_check_degraded`, `portal_hold`,
  `portal_reject`, `exportable`.
- `isaac bundle export <dir> --out <records_dir>` re-runs every gate and writes
  `<ULID>.json` + `<ULID>.evidence.json` (+ approved processing artifacts) ONLY for
  `exportable`. Everything else is listed with its verdict.
- `isaac bundle upload <records_dir> --dry-run [--portal-url URL]` prints the exact requests
  (`POST /portal/api/validate`, then `POST /portal/api/records`), headers with
  `Authorization: Bearer <from $ISAAC_PORTAL_TOKEN, not read>`, body size and sha256. No
  network call, and the token is never read. Without `--dry-run`: exit 2, "uploads are
  disabled in this build".
- The portal check runs the pinned upstream `portal/validation.validate_record_full`
  (`scripts/install_portal_validator.sh`, default commit `a1cb1c8`) in an isolated
  interpreter (`python -I`, scrubbed env, timeout, bounded output) started by
  `apps/api/isaac_portal_runner.py` — deliberately OUTSIDE the `isaac_api` package, whose
  no-subprocess guarantee (`test_attack_injection_and_containment.py`) stands unchanged; the
  server never imports the runner. Unavailable → `portal_check_unavailable`, never a pass.

Exit codes for the LOCAL-2 commands: `validate` and `export` exit 1 when any draft is not
`exportable`/not exported; mutations exit 5 when the change would leave the bundle invalid
(nothing written), 6 for an unknown target, 2 for a refused decision.

## 13. DEC-76: the local export targets the portal's pinned schema

- `validate` and `export` gate on ISAAC's OWN validators — `validate_official(record, root)`
  and `check_exactness(record, root)` — with `root` = the pinned upstream clone (the one the
  portal runner uses; `ISAAC_PORTAL_VALIDATOR_DIR` or `~/.cache/isaac/portal-validator/<sha>`),
  plus the offline portal check. The vendored v1.05 schema the website uses is computed and
  reported as `website_schema` for information; it gates nothing, and no report calls a
  record valid for the website. Every validation report and every sidecar carries
  `schemas_used` (source, commit, schema sha256). The truth-plane schema and `export.py` are
  not edited.
- The record is composed with `isaac_records.export.transform` and `export.set_path`; the
  sidecar with `export.build_sidecar`. `export.export_draft` is NOT used: its `transform` drops
  null fields, so it cannot write `temperature_K: null`.
- Upstream shapes: `attribution.produced_by {group, organization}` from scientist decisions
  only (answerable as record-scope missing values; the folder name is evidence to ask about,
  never a value); an unknown temperature is `temperature_K: null` + `temperature_basis:
  not_reported` (a derivation, listed in the composition report — never a number); a reaction
  goes to `context.reaction.name` (the deprecated `context.electrochemistry.reaction` is
  remapped), and then `context.reaction.drive` and `.catalysis` are required answers.
- Vocabulary, checked against upstream `data/vocabulary.json` @ a1cb1c8: descriptor
  `edge_position` (`descriptors.spectroscopy`, XAS), series `incident_energy` (eV) and
  channel `absorption` (`mu_normalized`, role `primary_signal`) as in the wiki's
  Measurement example, processing steps `calibration`, `spectrum_merging`,
  `normalization` (deglitch and qc have no token and are not written).
- The writable set now includes these portal-target fields
  (`bundle.UPSTREAM_TARGET_FIELDS`). They are NOT website write paths.

## 14. LOCAL-3: generic readers, grouping, processing

- `isaac import` (folders) runs `readers.collect_all_generic(root, skip=<files the engine
  read>)` after the engine. Each generic run is a `runs[]` entry with `source_type:
  generic:<profile>` and `reader {reader_id, profile, profile_version, statements_total,
  statements_kept}`; its statements are `extended_context` entries (`source_recorded`,
  `run_id`, at most 200 per run, the total stated). No statement maps to a field: there is no
  rule for it. Claimed files leave `unread_files`. A ZIP is not walked by the generic readers.
- `isaac bundle group <dir> [--regroup]` stores LOCAL-P's proposed `record_groups[]`
  (status `proposed`); `--regroup` keeps every group a scientist decided.
- `isaac process <dir> [--source] [--group ID] [--no-athena] [--params-file]` runs LOCAL-P's
  protocol and stores `processing_results[]` for groups in the bundle, each undecided (a
  result claiming confirmation is stored `needs_review`); decided results are kept. Exit 2
  "processing not installed" when its libraries are missing, or before grouping.

## 15. Known residue (DEC-77; the hosted path is deliberately unchanged)

- The engine pools HERFD scan statistics by scan-DIRECTORY name, so two same-named scan
  directories in different folders share one signal selection.
- Two same-named acquisitions in different folders produce DUPLICATE engine candidate ids in
  a hosted import session. The local bundle assigns candidates by position and is unaffected;
  the hosted session is not changed here.

## 16. LOCAL-4: consolidated questions, QC statements, real-format fixes

- `questions.json` is now **v2** (`isaac.questions` 2.0.0, `bundle.questions`' fine-grained v1
  list is unchanged inside `bundle.json`). `isaac bundle questions <dir> [--scope
  experiment|group:<id>|run:<id>] [--blocking-only] [--limit --offset]` prints it (hints are
  parser literals, so printing records an exposure). Rules: experiment > record group > run;
  shared fields asked once at experiment scope unless the bundle records differing values;
  sample fields shared across groups with the same sample reading, or asked once with the
  choice stated when nothing records any sample reading; run-level questions collapse to the
  record group; optional fields are one question per scope answered with `--field`; ordered
  blocking (required by the export-target schema, stated in `blocking_basis`; a disagreement
  about a required field is blocking), then conflicts that affect a record, then optional.
  `decide --question Q [--only group:<id>] [--field <path>]` records one decision per target.
  Allowed values come from the target schema's enum, else the pinned vocabulary.
- `decide --target <processing result> --decision approve --qc-status <pinned
  measurement.qc.status> [--qc-note ...]`: the scientist states the QC status; the protocol's
  own verdict and metrics are kept beside it (`qc_evidence`). `pass` maps to `valid` only
  through an approve decision; `warn` is never mapped.
- The composer reads LOCAL-P's `normalized.csv` by column NAME (`energy_eV`, `norm`; `flat`
  is not used) and refuses a file without them, with the reason. A contract test runs
  LOCAL-P's own writer.
- A record-scope field stated for only some runs is now still askable for the others.
- `build-records --test-marker TEXT` (self-tests only) writes the marker into the series, QC
  and sample notes.

## 17. Final-review hardening

- `blocked_by_schema_drift` is **not** a verdict (DEC-76: the portal-target schema gates; the
  vendored website schema is information). `schema_drift` stays in every report, informational.
- `build-records`, `validate` and `export` load the bundle AND `validate_bundle` it, refusing
  with the validator's findings (exit 1). `validate` and `export` re-compose every
  scientist-confirmed group from that validated bundle and use ONLY that fresh composition;
  an on-disk draft that differs is listed (`on_disk_drafts_ignored_because_they_differ`) and
  never used. `record_overrides` are an allowlist: `context.temperature_K: null` only.
- Processing output paths must be relative with no `..` (schema + validator); the composer
  and export read a file only when it resolves inside the bundle and its sha256 matches, and
  export writes artifacts only inside `--out`.
- `decide --decision approve` on a processing result REQUIRES `--qc-status`; no QC status is
  ever mapped from the protocol verdict. An approval records `approved_files` (role, path,
  sha256) and binds to exactly those: if the result later lists other files, nothing is used.
  Result ids follow LOCAL-P (`proc-<group>-<run_id>-isaac|athena`); a re-run is a new,
  undecided result.
- `decide --target <group> --decision approve_calibration --element X --edge K --by NAME`
  is the only way a calibration shift is applied: `isaac process` passes each group's latest
  such decision (element, edge, decided_by, decision_id) to processing. It does not change the
  group's status.
- `isaac bundle list <dir> groups | merge-candidates` and `show <dir> group <id>` present
  groups (the list prints plain fields; `show` prints basis readings and records exposures).
  `record_groups.json` is a mirror of `bundle.json`'s groups, rewritten by every `bundle group`.
- `--test-marker` is a flag that writes the fixed marker into series and QC notes only; the
  state is stored in `bundle.json` (`self_test`, set only by `build-records`, re-validated) and
  read from there, never from `drafts/index.json`.
- The portal validator counts only when its checkout HEAD is the pinned commit a1cb1c8. There
  is no override.
- `export` reports on-disk drafts it ignored (differing, or with no confirmed group) and says
  "Nothing was exported." when it wrote nothing.
- `ISAAC_SCHEMA_PATH` is honoured only inside the local CLI process; the server ignores it.
- An engine value produced by a NAMED rule from the statements (a lexicon member out of a
  structured logbook reading; a stored rule such as dry sample → ex_situ) carries a `derive`
  normalisation step naming that rule; the validator accepts it only when the rule id is the
  candidate's own and `from` is a witnessed reading.
