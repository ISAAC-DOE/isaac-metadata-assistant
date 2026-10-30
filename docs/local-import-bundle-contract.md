# ISAAC Local Import Bundle — contract v1

Status: **v1.7.0** (`context.electrochemistry.current_setpoint_mA_cm2` answerable, so a confirmed galvanostatic record can complete, 2026-10-29, §9 "What 1.7.0 added", DEC-92; v1.6.0 capture decisions — keep apart, the Athena result of record, "no counter" — a merge decision applied as one combined group, and question ids that survive answers, 2026-10-29, §9 "What 1.6.0 added"; v1.5.0 control mode answerable the same day; v1.4.0 the SSRL XDC scan start time, the instrument clock's time zone and its binding, 2026-10-29, §9 "What 1.4.0 added"; v1.3.0 absorber readings on record groups, a larger writable set and STALE bundles, the same day; v1.2.0 processed outputs 2026-10-28; v1.1.0 LOCAL-2 and v1.0.0 LOCAL-1 the same day). Machine contract:
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
| `extended_context[]` | ISAAC Extended Context (Level 4) entries, verbatim. A statement read from a processed output carries `processed_output_id` and never a `run_id` | source evidence |
| `processed_outputs[]` | **1.2.0.** The scientists' own Athena/Demeter outputs: reference results and evidence, **never runs and never record groups** (§9, "What 1.2.0 added") | source evidence (+ a proposed link) |
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
- Nothing is extracted from a ZIP to disk by the engine walk (§21: the generic readers stage a
  NESTED ZIP's accepted members in a private temporary directory that is deleted before the
  import returns); symlinks are never followed; no source is ever
  executed (macros are read as text; a test proves a macro containing shell text runs
  nothing).

## 9. Versioning

- `format` is fixed: `isaac.local-import-bundle`. `format_version` is semver.
- **Every object in the schema is `additionalProperties: false`**, so a validator only
  accepts fields its own schema declares. Consequently:
  - the **1.1.0 schema accepts 1.0.0 bundles** (every 1.1.0 addition is optional), and the
    **1.2.0 schema accepts 1.0.0 and 1.1.0 bundles** (`processed_outputs` is optional; absent
    means none was recorded, and no `processed_output*` count is expected);
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

### What 1.2.0 added (processed outputs)

**The defect it closes (measured on the real SSRL corpus at 05e11c2e):** the XDI reader reads
the scientists' own processed outputs, yet every XDI stem-group became an ordinary `runs[]`
entry, so `isaac bundle group` proposed record groups — future ISAAC records — made of
processed files, double-counting measurements (94 of 274 runs in one beamtime, 253 of 340 and
347 of 570 in two others).

- **`processed_outputs[]`** — one entry per XDI stem-group the reader already forms:
  `processed_output_id` (`po-` + 16 hex of sha256 over `processed:<output_key>`, stable),
  `output_key` (`xdi_v1:<dir>/<stem>`), `label`, `directory`, `role: reference_result`,
  `is_acquisition: false`, `becomes_a_record: false`, `reader`, `files[]` (source id, relative
  path, sha256, size, extension, column names, points, `processing_origin`), `states`
  (`processed_by`, `element_symbol`, `element_edge`, `demeter_output_filetype` — each the
  file's LITERAL header statement with its source and locator), `anomalies`,
  `extended_context_entry_ids`, `proposed_links` (at most one), `link_note`,
  `value_state: source_recorded`.
- **Which files (`isaac.processed_output.origin.v0`, `bundle.classify_processing_origin`).**
  Decided by the file's own header, never its extension or columns. Line 1 (`# XDI/1.0
  Name/version [Name/version ...]`) is read as tokens:
  - a token whose name is `Athena` or `Demeter` (`bundle.PROCESSING_APPLICATIONS`; the
    WHOLE name, case ignored — `SYN_Athenaish` is not one) → processed output, basis
    `line_1`;
  - only OTHER applications named → an acquisition run, as before, whatever the fields say.
    If it also carries `Demeter.output_filetype` or `Athena.*` fields, the file disagrees
    with itself and a `processing_statement_disagrees` anomaly (severity `note`) is recorded
    on the run; nothing is decided;
  - no application named → processed output only with a non-empty `Demeter.output_filetype`
    or `Athena.*` fields (basis `fields`).

  `files[].processing_origin` records the basis and every line-1 token. A stem-group whose
  files differ is split file by file. Measured: every XDI file in the real corpus names one
  of the two applications.
- **Evidence kept, attributed correctly.** Its header statements stay `extended_context[]`
  entries (`source_recorded`, `is_official_field_value: false`, `scope: processed_output`,
  `processed_output_id`, `run_id: null`, entry ids `<output_key>#p<k>`). Nothing becomes a
  run value, a candidate, a missing value or a question.
- **The link rule (`isaac.processed_output.link_by_run_stem.v0`) — proposes, never merges.**
  The output's name stem is compared with run `stem`s, case-sensitively, no other
  normalisation:
  1. `exact` — a run has exactly this name. ANY such run (zero-scan included) also blocks
     rule 2. Only runs that are run candidates with at least one scan can be linked; if the
     only exact-name runs have no scan, `link_note.code: exact_name_run_has_no_scans`;
  2. `scan_selection_suffix` — name = run stem + `_` + `N` or `N-M`, and EVERY number in it
     is a scan that run has: its scans' own `scan_index` values when any is stated
     (`scan_selection_basis: scan_indices`), else `1..scan_count` (`scan_count`). A number
     the run has no scan for (`SYN_cell_500`) may be another sample or condition: no link.

  Exactly one run → one `proposed` link; several → none, `link_note.code: ambiguous` with the
  run keys; none → `no_run_named_like_it`. A link's `group_id` is DERIVED by
  `apply_derivations` from LIVE `record_groups[]` membership (status `proposed`,
  `scientist_confirmed` or `merged`; null before grouping). Unlinked is the expected outcome
  when a scientist renamed the export (e.g. raw `SYN_run_07_condA` vs processed
  `SYN_condA_07_3.nor`); nothing guesses past the rule.
- **No question per processed file.** None is asked; `summary.md` states the count.
- **Counts** (only when the section is present): `processed_outputs`,
  `processed_output_files`, `processed_outputs_linked`, `processed_outputs_unlinked`.
  `summary.md` (only when there are any): "N processed files from the scientists
  (Athena/Demeter), kept as reference results, not records (… linked by the name rule …)".
  `isaac bundle list <dir> processed-outputs` (prints no header literal) and `show <dir>
  processed-output <id>` (prints them, so it records exposures of the output's sources and
  of its linked run first, §11).
- **Validator:** unique ids; known sources; relative paths; a processed-output file is never
  also a run's scan; a link names a known run by its own key and stem, and at most one;
  **the link rule is re-run over the stored runs and a stored link or `link_note` that
  differs is refused**; each link's `group_id` is recomputed; an `extended_context` entry with
  `processed_output_id` names a known one and no run.
- **Versions.** A `1.2.0` bundle REQUIRES `processed_outputs` (schema `if/then`). The writer
  never relabels an older bundle: a mutation keeps a bundle without the section at `1.1.0`
  (a `1.0.0` one is raised to `1.1.0`, as before). `isaac bundle group` and `isaac bundle
  build-records` REFUSE (exit 2, nothing written) a pre-1.2.0 bundle in which a
  `generic:xdi_v1` run's recorded header statements make it a processed output by the rule
  above (`bundle.legacy_processed_runs`): re-import the folder to separate them.
- **Regrouping (`isaac bundle group --regroup`, `isaac.grouping.binding_groups.v0`).** By
  each existing group's STATUS:
  - `scientist_confirmed` is BINDING: kept, and its runs are never re-proposed.
  - `rejected`, `split` and `merged` are HISTORY: kept as the record of that decision, and they
    do not hold their runs. `merged` is history, not binding: only a confirmed group becomes a
    record, so a merged group's runs must stay proposable. A fresh proposal identical to a
    rejected or split group is not re-proposed; one identical to a merged group is re-proposed
    under a distinct id (`reproposed_after_group_id`). **Since 1.6.0 the regroup APPLIES the merge
    (§9 "What 1.6.0 added"):** the groups now holding the merge's runs are replaced by ONE combined
    proposed group (`merged_by_decision`), for the scientist to confirm. Where it cannot be combined,
    a merge candidate (`scientist_decided_merge`, with the decision id) joins those groups and its
    detail says why. (Before 1.6.0 only that candidate was carried, which no decision could turn
    into one group — a defect, not a design.)
  - `proposed` (undecided, deferred, calibration-only) is replaced. A replaced group that a
    decision, a processing result or an AI interpretation (1.3.0: an absorber reading is
    recorded on a group) still names moves to `superseded_record_groups[]`
    (`group_id`, `member_run_keys`, `status: proposed`, `superseded_utc`, `reason`,
    `processing_result_ids`); it is never a record and is not decidable.

  STRUCTURAL: the fresh proposal is computed over the runs that are neither bound nor a
  zero-scan export of a bound run (`related_run_key` pointing at one), so every group, flag,
  engine-reading issue and question is computed from its real members. The sample-number
  consistency check and the counter question are computed over the FULL bundle. From the
  full-bundle proposal: where it would have joined fresh runs to a confirmed group, a merge
  candidate `matches_binding_group` names both; a bound run's export is offered to ITS group
  as a merge candidate (`group_ids: [<that group>]`, `run_keys: [<the export>]`), never as
  context of another group.

  A group's `merge_candidate_ids` is DERIVED (`apply_derivations`) from the stored merge
  candidates, on kept groups too. When a confirmed group exists, the counter question stays
  the beamtime's but says that its answer does not merge a confirmed group's runs
  (`candidates_resolved_by_position_excluding_confirmed`). The validator refuses a merge
  candidate naming a group or run that is not stored, a group listing a merge candidate that
  does not exist, a run in more than one live group (`proposed` or `scientist_confirmed`), and a processing result whose `group_id` is in neither
  `record_groups[]` nor `superseded_record_groups[]`. `isaac process` keeps every result of a
  superseded group (never deletes it). `decide --decision confirm` on a group whose run now
  sits in another live group is refused: "This group's run is now in proposal <id>; confirm
  or reject that proposal instead."
- **Scan-numbering assumption, stated.** A suffix link whose basis is `scan_count` carries
  `assumption` ("the run states no scan index; its N scans are taken to be numbered 1..N"),
  printed by `bundle show processed-output`, and `summary.md` says how many links rest on it.
- **Old bundles in `isaac process`.** It refuses the same pre-1.2.0 bundles as `bundle group`
  and `build-records`.
- **Exported-file misreads** (`grouping._exported_file_misreads`): a zero-scan run named like
  a run plus a data-file extension is joined to that run only when exactly ONE run with scans
  carries the name; when several do, it is flagged with `ambiguous_run_keys` and joined to
  none.
- **Not built:** feeding processed outputs into the Athena comparison (see the TODO in
  `processing/athena.py`), and any decision that confirms a link.

### What 1.3.0 added (absorber readings, a larger writable set, STALE bundles)

A minor version by the rules above: optional fields, and a writable set that only grows.

- `ai_interpretation.field_path` and `ai_interpretation.run_ids` (§20): an absorber reading
  recorded on a record group says which half it reads and, when its finding named runs, which of
  the group's runs (the validator refuses `run_ids` outside the target group, or on anything but
  a record-group absorber reading).
- **The writable set grew** (`bundle.WRITABLE_ADDED_IN["1.3.0"]`:
  `context.electrochemistry.potential_setpoint_V`). Eligibility is derived, so a bundle an older
  build stored can disagree with this build's derivation without anyone having edited it: a
  set-point a scientist confirmed under 1.2.0 was stored "no write path", and is eligible now.
- **STALE, not INVALID** (`bundle.stale_eligibility`, `validate_allowing_stale`). A
  disagreement is STALE only when the bundle's `format_version` is older AND the value's path is
  one that version could not write; any other disagreement stays INVALID (so a 1.3.0 bundle with
  the same disagreement is a tamper). `isaac bundle check` prints `STALE:`, each value (id, path,
  state, eligible before -> now, why, e.g. "this build can now write
  context.electrochemistry.potential_setpoint_V; a scientist confirmed it while the storing build
  could not write the field: eligible now; composes only beside a confirmed potential_scale"),
  the remedy, and the upgrade sentence below. §10 has no exit code for it, so it exits **1** like
  INVALID and says so. `bundle validate` / `export` refuse a STALE bundle with the same remedy
  instead of composing from the stored eligibility.
- **STALE vs INVALID is read from the stated `format_version`**, so hand-editing the label can
  turn a tampered eligibility into a STALE one. That cannot reach a draft: a STALE bundle is
  refused by `validate` / `export`, and `build-records` (like every write) re-derives eligibility
  under this build before composing, so a draft is composed only from this build's own derivation,
  never from a stored eligibility.
- **The upgrade is logged once and said everywhere** (`format_upgrades[]`, optional:
  `from_format_version`, `to_format_version`, `derived_by_format_version`, `upgraded_utc`,
  `decisions_before`, `newly_writable_paths`, `statement`). The first write of an older bundle by
  this build appends one entry and prints its statement once to stderr; `check` (VALID or STALE)
  and `summary.md` print it too: "upgraded from 1.2.0; fields this build can newly write have no
  answer slots on runs that lacked a parsed value — re-import to get them". A 1.2.0 bundle so
  written becomes 1.3.0 (its eligibility is now this build's); a bundle without
  `processed_outputs` keeps its older label, as before, and is logged the same way.
- **Re-derived on that write, and each moved value logged** (`eligibility_rederived[]`, optional:
  `kind`, `id`, `target_field_path`, `from_format_version`, `to_format_version`, `rederived_utc`,
  `value_state`, `eligible_before`, `eligible_now`, `decision_id`, `reason`). The values whose
  eligibility moved only for the reason above are read from the bundle AS STORED (on disk, under
  the lock, so a decision made in the same write is not mistaken for an old one).
- **The old wording is corrected on every write.** A candidate whose short reason is the engine's
  "this build cannot write it yet" on a path this local build writes gets
  `bundle.LOCAL_WRITE_PATH_REASON` in `state_basis.not_proposable_summary`; the engine's own text
  stays in `not_proposable_reason`. (An import has done this since 1.3.0.)
- **`build-records` re-derives first, under the bundle lock**, and returns
  `eligibility_rederived_now`. **The disclosure rule:** a composition report lists in
  `composed_only_by_this_build` (with `decision_id`, the old version and the reason) every
  composed value on a path the bundle's original build could not write
  (`format_upgrades[].newly_writable_paths`) whose GOVERNING decision was made before the upgrade
  (`decision_id` number ≤ `decisions_before`). That is the case the disclosure is for: a
  confirmation given while the build said the field could not be written, which still composes
  because the confirmation was about the value. It is listed on every build until a decision made
  after the upgrade governs the value; a decision made after the upgrade, under the corrected
  wording, is not listed, because the scientist answered knowing the field is written.
- **Not done by a re-derivation:** a missing value (an answer slot) for a newly writable field.
  Missing values are made by the import; a run of an old bundle with no parsed set-point gets one
  only from a re-import of the folder (the upgrade sentence says so).
- **The schema accepts the 1.3.0 optional fields under any version label**, as it accepted
  1.2.0's: there is one schema file, and only `processed_outputs` is tied to a label.
- A 1.3.0 bundle requires `processed_outputs`, like 1.2.0.

### What 1.4.0 added (the SSRL XDC scan start time and the instrument clock's time zone)

A minor version by the rules above: a widened decision enum (a 1.3.0 validator refuses a bundle
holding `set_clock_time_zone`, which is why the label moves), a widened question-kind enum, and
optional fields. **Nothing becomes newly writable** — `timestamps.acquired_start_utc` already was —
so `WRITABLE_ADDED_IN` is unchanged and no eligibility is STALE because of 1.4.0.

- **The rule `ssrl_xdc_scan_start_v1` (import time, profile `ssrl_xdc_v1` only).** One candidate
  per XDC run: `statement_key: acquisition_timestamp`, `target_field_path:
  timestamps.acquired_start_utc`, scope and write scope `run`, ids continuing the `cand-NNNN`
  sequence, listed in `runs[].candidate_ids`. Each scan's line 2 (`Tue Jul 14 10:23:45 2099`) is a
  LOCAL clock time with no zone, and there is no epoch line (unlike BL15-2 SPEC files, whose `#D`
  local time stays not-proposable evidence beside the epoch; those candidates are unchanged). One
  evidence entry per scan with a usable time (`locator: line:2`, `method: deterministic_parser`,
  `method_id: ssrl_xdc_scan_start_v1`, the literal verbatim, a `read_local_clock` normalisation to
  the naive local time). **The start is the EARLIEST parsed time**; that witness `supports`, the
  others are `context` (never `contradicts`). Evidence stays in scan-index order; when time order
  differs, `local_clock.order_note` and a run anomaly `scan_time_order_differs_from_index_order`
  say so — nothing is reordered. A scan whose time did not parse or names a weekday its date does
  not fall on (the reader already flags both) is NOT used and is listed in
  `local_clock.excluded_scans` (a window of at most 256, with `excluded_scans_total`); a run with no
  usable time gets no candidate (its start stays a missing value). **Bounded:** the evidence is a
  window of at most 256 witnesses (`MAX_EVIDENCE_PER_CANDIDATE`) in scan-index order that ALWAYS
  includes the earliest scan's witness, with `evidence_total` (every usable scan) and
  `evidence_truncated` stated; the variation rows are the same window with `rows_total`. The
  timestamp statements stay in `extended_context` as before.
- **No zone, no value.** Until a zone is stated the candidate's `value` is `null`, it is
  `needs_review`, not proposable, and its `not_proposable_reason` says the header writes a local
  clock time, names no time zone and states no epoch, and becomes a UTC value only after a
  scientist confirms the instrument clock's zone, with the command. `confirm` is refused (naming
  the command); `correct --value <UTC instant>` is always available. **`confirm --value` is
  refused at every stage** for these candidates (pointing to `correct --value`): a confirm stands
  only for the value the rule produced, and a value the scientist supplies is a correction.
- **The decision `set_clock_time_zone`** (`--target experiment --value <IANA name> --by NAME`): the
  time zone the INSTRUMENT CLOCK that wrote the headers was set to — not "the facility's time
  zone". ACCEPTED: `UTC`, and any Area/Location name `zoneinfo` knows, including the IANA links that
  keep that form (`US/Pacific`, `Asia/Calcutta`). REFUSED with a plain message, never mapped: a
  non-string or empty value; a fixed offset (`-08:00`, `UTC-8`, `Etc/GMT+8`); a name with no
  Area/Location form (abbreviations such as `PST`, `PDT`, `EST`, and one-word names such as `Japan`);
  another fixed `Etc/` zone; and an unknown name (`bundle.clock_zone_problem`, the one rule `decide`
  and the validator share). Idempotent; a later one supersedes the earlier (the
  latest wins; every one is kept).
- **The question.** While start-time candidates wait and no zone decision exists, ONE
  beamtime-scope question asks for it: v1 `questions[]` kind `confirm_clock_time_zone` (target
  `experiment`, `options: []`) and consolidated kind `clock_time_zone` (optional tier,
  `allowed_decisions: [set_clock_time_zone]`, `suggested_value: null`). It states how many runs it
  unblocks, one example literal with its file and locator, that no file states a zone, and the
  exact command. **It suggests no zone**: no file states one, and guessing from where the facility
  is is exactly what CLAUDE.md §5 forbids. Before a zone exists the consolidated list asks no per-run
  confirm question for these candidates; the fine-grained v1 `questions[]` list keeps its per-candidate
  `confirm_value` entry (v1 lists every needs-review value) but with `options: []` and a prompt saying
  it waits on the clock's zone — a local literal is never offered as an answer for a `*_utc` field.
  After a zone, its one option is the converted UTC value.
- **The conversion, re-derived on every save** (`apply_derivations`, rule
  `local_clock_to_utc_via_confirmed_zone_v1`, zoneinfo, DST-aware): the value becomes
  `YYYY-MM-DDTHH:MM:SSZ`, recorded as a `local_clock_to_utc` normalisation step on the supporting
  witness carrying `zone` and `zone_decision_id` (both new optional step fields), and in the
  candidate's optional `local_clock` block (`status`, `zone`, `zone_decision_id`, `local_time`,
  `literal`, `explanation`, the rule ids). **`not_proposable_reason` keeps meaning what its name
  says**: once converted it says why the value is not proposable to the website (its UTC value rests
  on a clock-zone statement the website's proposal route cannot carry), and what the conversion did
  is in `local_clock.explanation` and the question text. A local time that is **ambiguous** in the zone (the fall-back fold:
  both offsets valid) or **nonexistent** (the spring-forward gap) gets NO value; the reason names
  which and quotes the literal. Fold 0 is never picked silently. **Nothing stored is trusted:** the
  derivation converts the supporting witness's LITERAL, re-read with the reader's exact format and
  weekday check, never the stored `read_local_clock.to`; the validator refuses a witness whose literal
  does not read, whose `read_local_clock` step does not say exactly what its literal reads, or a
  `supports` witness that is not the earliest scan (ties: the lower scan index), and it re-runs the
  conversion and refuses a stored value, step, reason or block it does not reproduce.
- **The binding.** `confirm` without `--value` stores `value: null`, and the composed value is the
  candidate's LIVE value — which a later zone decision changes. So a confirmation of a start-time
  candidate records `clock_zone_binding {zone, zone_decision_id, value, rule_id}`: the zone and the
  converted value it was made under. A confirmed candidate whose current zone or value differs from
  its binding (or a confirm with no binding) is **not eligible**, and its reason says the clock
  time zone changed after it was confirmed and to confirm it again; re-confirming records a new
  binding. **DELIBERATE DEPARTURE from "any zone decision change invalidates":** the binding
  compares the zone AND the value, not the decision id, so restating the same zone (by anyone), or
  returning to the zone a confirmation was made under with the same value, keeps that confirmation;
  a different zone invalidates it even when it gives the identical value (e.g. `UTC` and
  `Europe/London` in January), and a different value invalidates it under the same zone. **A zone
  change is never silent:** `decide` returns `clock_zone` (the zone, its decision id,
  `confirmations_invalidated_now`, `candidate_ids_to_confirm_again` and a statement, also printed to
  stderr when anything was undone); `summary.md` states the recorded clock zone with its decision id
  and how many confirmations no longer count; and each such candidate is asked again in the
  consolidated list (`confirm_value`, `reason: clock_zone_changed_after_confirmation`) and its v1
  prompt says why. `decide` counts only what THAT decision undid (`to_confirm_again` /
  `to_correct`), never a confirmation already stale. Where the new zone gives no single instant
  (ambiguous or nonexistent) there is nothing to confirm: the statement, the eligibility reason and
  the re-ask (one per candidate) say "correct it" and give a `correct --value` command. A `correct` states its own UTC value and needs no binding.
  Bulk confirm is allowed (the candidate has source evidence). Older bundles stay valid: the field
  is optional and no older bundle holds such a candidate.
- **Composition** (`records.compose_group`): the composed `timestamps.acquired_start_utc` carries
  the file literal witness(es), the candidate's confirmation, and — only when the composed value is
  exactly what the rule produced under the current zone and the confirmation is bound to it — a
  `user_confirmation` for the zone decision (question: "What time zone was the instrument clock that wrote these scan headers set
  to?", with the conversion rule and the local time). A `correct`ed value carries no zone entry.
  Group disagreement is unchanged: two runs of one group with different starts fill nothing.
- **An older bundle** (1.3.0 or earlier) with `ssrl_xdc_v1` runs has none of these candidates; a
  save does not apply an import rule. Its first write by this build relabels it 1.4.0 (when it has
  `processed_outputs`, as before) and logs a `format_upgrades` entry whose statement adds "its
  ssrl_xdc_v1 runs were imported before rule ssrl_xdc_scan_start_v1 existed and carry none of its
  candidates — re-import to get them" (`bundle.IMPORT_RULES_ADDED_IN`, `import_rules_missing`).
- A 1.4.0 bundle requires `processed_outputs`, like 1.2.0 and 1.3.0.

### What 1.5.0 added (`context.electrochemistry.control_mode` becomes answerable)

A minor version by the rules above, of the same kind as 1.3.0: **the writable set grew**
(`bundle.WRITABLE_ADDED_IN["1.5.0"]`: `context.electrochemistry.control_mode`). Nothing in the
bundle's shape changes: no section, field or enum is added, and the schema change is the version
label alone (plus `processed_outputs` required at 1.5.0, as at 1.2.0–1.4.0).

- **STALE, not INVALID, exactly as at 1.3.0.** A 1.4.0 bundle whose stored eligibility for a value
  at this path differs from this build's derivation reports `STALE:` (`bundle check`, exit 1),
  naming each value and the remedy; any write re-derives it, logs it in `eligibility_rederived[]`
  and appends one `format_upgrades` entry ("upgraded from 1.4.0; fields this build can newly write
  have no answer slots on runs that lacked a parsed value — re-import to get them"). A bundle the
  1.4.0 build actually made holds no value at this path (no parser states one and the field had no
  answer slot), so it checks **VALID**; its first write still logs the upgrade, naming the path in
  `newly_writable_paths`. A write never adds the missing values: re-import to get them.
- **Value ids of older fields do not move** (`bundle.VALUE_IDS_APPEND_FROM`). Missing values are
  numbered in path order, except that a path made writable at or after 1.5.0 is numbered after
  every older path. Re-importing the same files with this build therefore gives every older missing
  value the id a 1.4.0 import gave it; the control-mode values are `miss-` ids after the last of
  them. (At 1.3.0 the set-point was numbered in path order, which shifted later ids; that is not
  changed retroactively.)
- See §20 ("Newly answerable fields") for what the field allows and how it interacts with the
  set-point.

### What 1.6.0 added (capture decisions, the merge applied, stable question ids — DEC-91)

A minor version by the rules above: widened enums (three decisions and the target kind
`merge_candidate`, which a 1.5.0 validator refuses — that is why the label moves) and optional
fields and one optional section. **Nothing becomes newly writable**, so `WRITABLE_ADDED_IN` is
unchanged and no eligibility is STALE because of 1.6.0; a 1.5.0 bundle checks VALID, and its first
write relabels it 1.6.0 with no `format_upgrades` entry (exactly as 1.4.0 relabelled a 1.3.0 bundle
with nothing to re-import). A 1.6.0 bundle requires `processed_outputs`, like 1.2.0–1.5.0. Each
decision CAPTURES a statement; none takes a scientific decision, and none is defaulted.

- **`keep_apart`** (`decide --target <mc-id> --decision keep_apart --by NAME`): the groups a merge
  candidate names are distinct. The candidate's `status` is DERIVED `kept_apart` (with
  `kept_apart_by_decision_id`) on every save, so it is no longer an open merge question
  (`bundle list merge-candidates` shows the status). **Nothing else changes:** no group's
  membership, status or questions move, and none is confirmed — keeping apart is what the proposal
  already does; each group is still confirmed (or not) on its own. A regroup that proposes the same
  candidate (same id) keeps it kept apart. One a regroup no longer proposes, while a decision names
  it, moves to the optional `superseded_merge_candidates[]` (`merge_candidate_id`, `group_ids`,
  `run_keys`, `superseded_utc`, `reason`) so the decision keeps its target, as
  `superseded_record_groups[]` does for groups. `keep_apart` is refused on any other target, and a
  merge candidate accepts no other decision (merging is the record-group decision below).
- **`merge` is applied (a fixed defect).** The required sequence:
  (1) `decide --target <group> --decision merge --merge-with <group ...> --by NAME` — the group's
  status becomes `merged` (history); (2) `isaac bundle group <dir> --regroup` — the fresh groups now
  holding the runs of the merged group and of every group in `merge_with` are replaced by ONE
  proposed group, id `rg-` + sha256(experiment key, its runs, `merged-by:<decision id>`), flag
  `merged_by_scientist_decision`, and `merged_by_decision` {`decision_id`, `merged_group_id`,
  `merge_with`, `decided_by`, `from_groups`, `basis_keys_dropped`, `statement`}; its basis keeps
  every reading the groups agree on — compared on what it says (value, kind), never on its per-run
  evidence ids, which are united — and drops (and names) the rest; (3) `decide --target <combined
  group> --decision confirm` — only this makes it a record. The regroup output lists
  `combined_by_merge_decision` and `merge_decisions_not_combined`.
  **The check FAILS CLOSED** (`mutations._merge_blockers`): the groups are combined only when
  NOTHING the import read or a scientist confirmed tells them apart — none of their runs is in a
  confirmed group; they share one role; every basis reading agrees (the name stem standing in for an
  unstated sample aside); the independent condition check (`grouping.condition_violations`) finds
  only the names; **the runs' file names have exactly the same tokens**; and no confirmed, eligible
  run-level answer (an answered missing value or a confirmed reading, e.g. the control mode) differs.
  **There is no exception by token shape.** Three review rounds measured that any shape rule leaks
  (`0.05V`/`0.5V` and `1.02`/`1.03` split on the decimal point; `05_mM`, `02_hrs`, `05_rpm` are units
  no list covered; `400`/`500` is a unitless potential), so ANY differing token blocks and the
  `scientist_decided_merge` candidate stays open, its detail naming the differing tokens and pointing
  to the counter question: saying a name position IS a run counter is `set_counter_positions`, after
  which `isaac bundle group --regroup` joins those runs itself (no merge is needed). Merge candidates
  that named a combined group name it instead. **A combined group that was itself decided**
  (rejected, split, or merged again) is that ruling on exactly that group: the regroup does not
  propose it again and asks no candidate about it (`merge_decisions_not_combined` says "already
  decided"); a merge of the combined group with another group is a new decision, combined in turn.
  Because a combined group's runs never differ in their names, a later not-counter answer cannot
  contradict one (the 1.6.0 draft's `contradicted_by_not_counter` flag is gone with the exception).
- **`select_athena_version`** (`decide --target <processing result> --decision select_athena_version
  --value <version id> --by NAME`): which of the result's listed `athena_versions[].version_id` is the
  scientist's result of record. ANY other value is refused (nothing recorded), as is a result that
  lists no versions; the validator refuses a stored selection that is not listed. DERIVED on every
  save from the latest such decision: `athena_result_of_record` (the version id, else `null`) and
  `athena_result_of_record_basis` {`decision_id`, `decided_by`, `statement`}; the flag
  `athena_result_of_record_not_selected` and the result's own question
  `which_athena_version_is_result_of_record` are present exactly while nothing is selected (the
  question drops out once answered). A selection made or changed AFTER the result was approved is
  noted on it (`athena_result_of_record_basis.changed_after_approval` {`approval_decision_id`,
  `selected_at_approval`, `note`}); it is not wired into export. **It is not a state decision**
  (`bundle.PROCESSING_STATE_DECISIONS`): the result's `state`, QC, outputs and processed values are
  never touched, a selection never supersedes the approval a record cites
  (`bundle.processing_state_decisions`), and `--qc-status` is refused with it. The composed record
  is unchanged by it (it uses the approved ISAAC curve, as before). **The selection is bound to the
  version's own identity, not its number:** version ids are positional (`<group>-vNN`, numbered over
  the projects sorted by path and group name), so adding or removing a project file renumbers them.
  The decision records `athena_version_provenance` {`prj_relative_path`, `athena_group`,
  `data_sha256_prefix`} (refused when two listed versions share it), and `athena_result_of_record` is
  the version with that identity (`bundle.athena_resolve`). Replaying a selection is "unchanged" only
  when it names the same identity (re-selecting an id that a renumbering gave to another curve is a new
  decision), and `changed_after_approval` compares identities, not ids. A selection alone does not freeze the
  result against `isaac process`: a fresh result of the same id replaces it when it holds a version
  with that identity — re-pointed to its new id if it moved, said in
  `athena_result_of_record_basis.repointed` {`decision_value`, `now`, `note`} — and otherwise the OLD
  result is kept, so a selection never points at nothing or at another curve. Only the latest
  selection counts, and the validator refuses one that resolves to no listed version.
- **`set_not_counter_positions`** (`decide --question <counter question> --decision
  set_not_counter_positions --by NAME`, which names the question's open positions; or `--target
  experiment --positions n[,m]`): those 1-based filename token positions are NOT run/acquisition
  counters — the numbers name distinct samples, electrodes or conditions, or are a plain sequence
  that does not mark repeats. Stored as `not_counter_positions` on the decision. **Grouping is
  unchanged by it:** runs whose names differ there were already proposed as separate groups and
  stay so, and each merge candidate between them stays open (merge it, or keep it apart); the
  decision says so. Refused for a position the latest `set_counter_positions` names (record
  `set_counter_positions` without it instead); a later `set_counter_positions` naming a position
  takes over (latest statement per position, `bundle.not_counter_positions`).
- **An answered counter question drops out.** The consolidated `naming_counter_positions` question
  asks only about its positions that no answer covers (a counter by the latest
  `set_counter_positions`, or not one by `set_not_counter_positions`), lists them in `positions`,
  says which are already answered, and is left out when none is open — under the same id
  throughout. It drops out after `set_counter_positions` even before the regroup applies it; the
  grouping step's own `grouping_questions[]` entry is kept as it wrote it.

### What 1.7.0 added (`context.electrochemistry.current_setpoint_mA_cm2` becomes answerable — DEC-92)

A minor version by the rules above, of the same kind as 1.3.0 and 1.5.0: **the writable set grew**
(`bundle.WRITABLE_ADDED_IN["1.7.0"]`: `context.electrochemistry.current_setpoint_mA_cm2`,
`bundle.CURRENT_SETPOINT_PATH`). Nothing in the bundle's shape changes: no section, field or enum is
added, and the schema change is the version label alone (plus `processed_outputs` required at 1.7.0,
as at 1.2.0–1.6.0).

- **Why.** Since 1.5.0 a scientist can confirm `control_mode: galvanostatic`, and the schema's own
  conditional rule then requires `current_setpoint_mA_cm2`, which had no write route: such a record
  was blocked for good. It now has an answer slot.
- **STALE, not INVALID, exactly as at 1.3.0 and 1.5.0.** A 1.6.0 (or older) bundle whose stored
  eligibility for a value at this path differs from this build's derivation reports `STALE:` (`bundle
  check`, exit 1); any write re-derives it, logs it in `eligibility_rederived[]` and appends one
  `format_upgrades` entry naming the path in `newly_writable_paths`. A bundle the 1.6.0 build made
  holds no value at this path (no parser states one and the field had no answer slot), so it checks
  **VALID**, and its first write logs the upgrade. A write never adds the missing values: re-import to
  get them. (From 1.4.0 the entry names both `control_mode` and this path; from 1.5.0 only this path,
  because 1.6.0 made nothing newly writable.)
- **Value ids of older fields do not move** (`bundle.VALUE_IDS_APPEND_FROM` is still 1.5.0): the
  current set-point's missing values are numbered after the control mode's, which come after every
  older field's.
- **The metadata template is 1.3.0:** File List gains the ISAAC-added numeric column `Current
  Set-point (mA/cm2)`, appended after `Control Mode`. A 1.2.0 workbook is read up to Control Mode
  (a 1.1.0 one up to pH); a value typed where a later column would be is reported under
  `recorded_nowhere`, never dropped silently. A non-number in the column is an invalid cell and
  nothing is recorded for it.
- See §20 ("Newly answerable fields") for what the field allows and why it has no companion gate.

## 10. Exit codes (`isaac import` / `isaac bundle`)

0 ok · 1 `check` found the bundle invalid, or STALE (stored by an older build, §9 "What 1.3.0
added": there is no code of its own; the output's first word says which) · 2 usage (bad arguments, unknown profile, the
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
  `run_id`, at most 200 per run, the total stated). No statement maps to a field unless an
  explicit, tested rule says so; there is exactly one, `ssrl_xdc_scan_start_v1` (§9 "What 1.4.0
  added"), and the statements stay extended context even then. Claimed files leave `unread_files`. A ZIP given AS THE ROOT is not walked by the
  generic readers; a ZIP found INSIDE a folder is (§21).
  **Since 1.2.0 an XDI file whose header states Athena/Demeter is a `processed_outputs[]`
  entry instead of a run** (§9, "What 1.2.0 added").
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
  **Question ids survive answers (1.6.0, DEC-91).** A question's scope and partition — and so its
  id — are read only from what the IMPORT recorded (candidates) and from the record groups, never
  from scientist answers. Answering a question, or one group of it (`--only`), takes exactly those
  targets out; the question for the rest keeps its id, and when answers given so far differ its
  text says so ("answer per group") and the question carries `answers_differ: true` (its
  `answer_command` says to answer per group), so an agent following the command is warned; the note
  needs at least one answer — differing file readings alone are the scope rule above. (Before 1.6.0 an answered value counted as "recorded", so one
  answered group re-asked a `sample=unrecorded` or shared-field question group by group under new
  ids — measured +99 and +111 new ids on two real beamtimes.) An answer can still ADD a question
  that was withheld until it existed, never rename one: a stated clock zone unlocks the start-time
  confirmations it gives (§9 "What 1.4.0 added"), a stated control mode makes its set-point
  required (§9 "What 1.5.0 added"), and a zone change re-asks the confirmations it undid.
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

## 18. Processing that does not apply is not a QC fail

Measured on six real beamtimes: every group the draft XAS protocol could not apply to was
reported QC `fail` — tab-separated `xes<N>` files, MCA arrays, headerless two-column files
(no absorption channel could be formed) and groups listing no scan. A `fail` tells a
scientist their spectrum is bad; the truth was "this protocol does not apply" or "there is
nothing to process".

- **Contract (additive, no format bump).** `processing_result.applicability` is OPTIONAL
  (absent = the protocol applied, so every older bundle is unchanged):
  `{status: "not_applicable", reason_code: "no_scans" | "no_xas_channel", detail, statement,
  what_the_data_states}`. The schema forbids `qc.verdict` and any `outputs.files` beside it.
  `processing_result` already allowed additional properties and `qc.verdict` was never
  required, so no `format_version` change is needed; `save_bundle`'s version rule is unchanged.
  `processing/processing_results.json` is format 0.2.0 (adds the field and
  `summary.not_applicable` / `summary.lines`).
- **The boundary is what the code detects, never a reader name.** `no_scans`: the group lists
  no scan at all. `no_xas_channel`: in NONE of the group's readable scans does
  `channels.choose_channels` form a channel (an energy axis and a signal), and no scan has a
  signal-side candidate column (I0, transmission, fluorescence name or `sum:` family member)
  that is present but not live. Such a dead candidate is a real QC failure,
  `fail signal_channel_dead`. When some scans form a channel and others do not, the first
  scan that forms one supplies the group's choice and the scans without those columns are
  skipped, each with `skip_reason: scan_lacks_chosen_columns` (flag `channel_from_a_later_scan`);
  any such skip makes QC at least `warn` (`scans_skipped_lacking_chosen_columns`, with the
  `scans_readable` and `scans_skipped_lacking_chosen_columns` metrics), never `pass`.
  A column whose label names time (whole-token `epoch`, `time`, `sec`, `seconds`, `timestamp`,
  `clock`, …) is never taken as the energy axis by value shape. Everything else — unreadable or
  missing files, too few points, a failed normalisation, a crash — is still judged and can still
  `fail`. A scan with a recognised energy column but no signal column under a recognised name is
  `no_xas_channel`: no column was judged, so no verdict is given.
- **What the data states, as literals.** `what_the_data_states` holds the runs' `source_type`,
  reader id and profile, that reader's stated file LAYOUT (`processing.run.READER_LAYOUT`, taken
  from each reader's own docstring — e.g. "two numbers per line, no header"), the scan format and
  its column labels. No technique is named: the `xes_tab_v1` reader itself does not say what
  technique produced the file, so neither does this.
- **Nothing to decide.** `decide` refuses every decision (approve, reject, needs_changes, defer)
  on a not-applicable result, and `validate_bundle` refuses a decision on one, a QC verdict on
  one, an output file on one, `preferred_for_record` on one, a `no_scans` reason that disagrees
  with the listed inputs, and a `no_xas_channel` reason whose own `channel_choice` formed a
  channel (or is absent), that read no scan, or that marks a scan used — checked against the
  result's own record.
- **Latest result decides.** A group is processing-blocked when its LATEST `isaac_protocol`
  result (last in `processing_results[]`) is not applicable; older kept results (e.g. a rejected
  `fail` from before this rule) are never deleted and do not make it approvable. A group that
  holds an APPROVED curve is never blocked: the record uses that curve.
- **Downstream.** `bundle questions`' `minimum_for_one_group` never offers "approve its
  processing result" for such a group, prefers a group processing can complete, and states
  `blocked: "no ISAAC processing protocol covers this data yet (...)"` when only such groups are
  left. `build-records` lists `blocked` on the draft and the composition says why; `validate`
  reports `processing_blocked` and the verdict `incomplete` (never a pass); export refuses it.
  `summary.md` and `isaac process` print the not-applicable groups apart from the QC verdicts
  (by reason, and the no-channel groups by reader profile).

## 19. The metadata template round trip

Many key fields are stated in no file (facility, beamline, environment, cell type, reaction,
sample form and formula). The template lets a scientist answer them in one sitting.

- `isaac bundle template export <dir> --out <file.xlsx> [--force] [--no-suggestions]` writes
  ISAAC's metadata template: sheets Campaign Info, Configurations, File List and Vocabulary,
  with ISAAC's header text and column order. **Every answer cell is empty**; no example value
  is written. File List has one row per run in a live record group (proposed or confirmed),
  named by its acquisition file's path in the import (`SampleA/scan_001` and `SampleB/scan_001`
  stay apart; where two runs share one file, the run label is added). If names would still
  repeat, the export is refused. After the template's own columns ISAAC adds ~~two~~ three
  (changed in template 1.2.0), labelled as its own: **Electrolyte Concentration (M)** and **pH**
  (both numeric) and **Control Mode** (`context.electrochemistry.control_mode`, a dropdown of the
  schema's enum, on the Vocabulary sheet after ISAAC's own lists). The template's
  **Electrolyte** column is the electrolyte name only; "0.1 M KOH" is two answers (name KOH,
  concentration 0.1), and both electrolyte columns show the whole AI reading in the
  suggestions so it can be split. Vocabulary and the dropdowns come from the export-target
  schema's enums, else the pinned vocabulary (as for questions), plus a Technique list for
  Configurations. Two sheets are added: **ISAAC Suggestions** (visible; the File List layout,
  each cell showing what the bundle already holds — an extracted value or literal, a question
  hint, or an AI reading — with its file and locator), and **`_isaac`** (hidden; format
  `isaac.metadata_template` ~~1.1.0~~ 1.2.0 (changed: adds Control Mode), `bundle_id`, export time, row → `run_id`/`run_key`/`group_id`,
  column → official path). Suggestions print parser values, so the export records an exposure
  first; `--no-suggestions` shows none and records none. Refused for a bundle with no live
  record group.
- `isaac bundle template import <dir> <file.xlsx> --by "<name>" [--orcid ...] [--apply]
  [--supersede] [--json]` is a **preview by default** (nothing written); `--apply` records.
  It refuses (exit 3) a workbook with no `_isaac` sheet, or one naming another bundle, so an
  example value in a raw template can never become an answer. It reads only non-empty answer
  cells. Each is validated first: an enum column must hold an allowed value exactly (no case
  folding); a numeric column must hold a number; a formula, a date in a text column, or a
  number Excel stored in a text column is refused. An invalid cell is reported by address and
  records nothing. A 1.1.0 workbook (exported before Control Mode existed) is still read:
  `template.file_columns_of` gives the columns that version wrote, and nothing past pH is read
  from it; a value typed there is listed under `recorded_nowhere` ("this workbook is template
  '1.1.0', which has no column P … re-export the template to answer it"), in the preview and on
  `--apply`, never dropped silently. A workbook labelled 1.2.0 without the column is refused like
  any moved column.
- Each valid cell becomes decisions through the same code as `decide` (identity
  `self_reported_local_user`, unverified). A Campaign Info cell fills the missing values of
  its path for the File List's runs (those still in a live record group) and any record-scope
  value, in one batch; missing values of other runs are listed as not filled, and extracted
  values are not touched (they are listed). A File List cell
  fills that run's missing value for the column's path (`correct`), or decides that run's
  extracted value: `confirm` when the cell equals it, `correct` otherwise. A Configurations
  Technique reaches a run through the row's Config ID. Every note cites the cell, e.g.
  `template beam.xlsx 'File List'!F12`.
- A cell that would change an earlier scientist decision is a **clash** and is skipped; with
  `--supersede` the new decision is recorded and wins by the last-wins rule (the earlier one is
  kept). The same value already decided is not recorded again. Two cells giving one target
  different values: neither is recorded.
- Nothing is dropped silently. Columns with no official field (Start Date, Proposal ID, Mode,
  channels, detectors, calibration, setup, notes, Gas Feed) and columns whose official field
  has no target in this bundle (for example Flow Mode) are reported with their cells as
  "recorded nowhere". A row's File Name must match the export exactly (no trimming); a row
  whose name was edited or moved is refused, never re-matched by guess, and a mapping that
  names one file or run on two rows is refused outright.

## 20. Suggestions: the absorber, facility hints, and a Claude reading pass

Three ways the import shows a scientist what the files already say, so they can answer in one
step. None of them is a value: each is a suggestion or hint, and only a scientist decision makes
anything `scientist_confirmed`.

- **The absorber** (`isaac.suggest.absorber.v0`, `suggestions.absorber_for_group`). It is
  read from every `Element.symbol` and `Element.edge` header statement of the processed outputs
  linked to a group. Those links are proposed by name and not confirmed. The beamtime's
  `experiment.element_evidence` (an acquisition macro's name, a shared readme) also counts.
  - A value is proposed only when every witness agrees. Two witnesses that differ propose
    nothing for that half (`status: disagrees`), and the group is asked on its own.
  - Groups that agree are asked once at experiment scope (`confirm_absorber`). The question is
    optional, because the official schema has no absorber field.
  - The answer is `decide --decision set_absorber --element <El> --edge <K|L1-L3|M1-M5>` on a
    record group. It never changes the group's status.
  - `build-records` writes the absorber to the draft's `implicit[]` (`absorbing_element`,
    `edge`). Without a decision the value is `null` and the witnesses are kept as evidence, the
    same way the hosted path carries an unconfirmed edge. It reaches the evidence sidecar only,
    never an official field.
  - **AI readings beside the file evidence, never part of it.** A reading pass's `system.element`
    / `system.edge` findings (below) are recorded on the group and listed in `ai_readings`
    (value, field, source path, locator, quote, strength, model, finding and interpretation ids).
    They never move `status`, `element`, `edge` or `readings`, which stay the files' alone.
    `ai_vs_files` says, per half, `agrees`, `differs`, `no_file_evidence` or `no_ai_reading`, and
    `ai_disagrees_with_files` is true when any half differs. Nothing chooses between them.
  - The absorber question is also asked for a group whose only evidence is AI readings: once at
    experiment scope per distinct (element, edge) pair the readings agree on (merged with the
    file-agreed groups of the same pair, the text saying how many rest only on an AI reading),
    per group when the readings disagree or name one half, and per group when an AI reading
    differs from file evidence that agrees. Hints list file evidence first, then each AI reading
    (`kind: ai_suggestion`, with `field`, the citation, `groups` and `differs_from_files`). The
    answer command pre-fills `--element`/`--edge` only when every group's files state them.
  - Without a `set_absorber` decision an AI reading writes nothing to `implicit[]`: a group
    whose only evidence is AI readings gets no absorber entry at all.
- **Every consolidated question says which decisions answer it** (`allowed_decisions`), and
  `decide --question` refuses any other. The absorber question targets record GROUPS, so without
  this rule `--decision confirm` on it would have bulk-confirmed every group it names.
- **Facility hints** (`suggestions.facility_hints`) appear on every `system.facility.*` question
  (in `field_hints` when the field is optional). They are the imported folder's name and, only
  when the runs' scan headers have that system's detector column names, the acquisition system
  (`experiment.acquisition_system`), with a locator saying literally what was seen ("N run(s)'
  scan headers have columns named vortDT, … (the column naming of: <system>)") and a note that a
  column name is not proof of the beamline. `experiment.acquisition_system` itself is the engine's build default, set on every
  import whatever the files are (kept for older readers), so it is never shown as a match on
  its own: a beamtime from another beamline used to be told its files were BL15-2 exports.
  Since 2026-10-29 the bundle applies the same test to the system's own name: `display_name`
  is present only when some run's headers carry its columns (§22).
  Hints are text and never an answer: a file layout or a folder name is not a statement of where
  data was taken.
- **A Claude reading pass**: `bundle annotate <bundle> --from-readings <findings.json> --model <id>`.
  - The file has format `isaac.reading_findings`. Each finding gives `field_path`, `value`,
    `applies_to` (`experiment`, or `runs` with exact run labels), `source.path`,
    `source.locator`, a `quote` (as the reader gives it: this build does not check it against
    the file), `strength` (`stated` or `inferred`) and `reasoning`. `source.path` must be relative
    to the imported folder, or carry one leading `../` for a document beside it.
  - Each finding becomes one AI interpretation per target it reaches: the missing value or
    extracted candidate of that field on every live run it names (the record group, for an
    absorber finding; below).
  - The interpretation carries the new optional fields `source_path`, `quote`, `strength` and
    `finding_id`. `source_refs` carries the `source_id` when the cited file is a bundle source.
  - The default is a preview that writes nothing. `--apply` records everything in one locked
    write. An identical reading of a target is never recorded twice.
  - A finding that cannot be placed is reported with its reason and never forced onto another
    field. Reasons include an unknown field, an unknown run label or a missing quote.
  - A finding about `context.electrochemistry.electrolyte` is offered, unsplit, on both
    `electrolyte.name` and `electrolyte.concentration_M`. Splitting it is the scientist's step.
  - A finding about `system.element` or `system.edge` (aliases `system.absorbing_element`,
    `system.absorption_edge`) has no record field. It is recorded on record GROUPS: every live
    group for `experiment`, every live group holding a named run for `runs` (the same unknown-label
    and no-live-group refusals). Its value must pass the same shape check as `set_absorber`
    (`bundle.is_absorber_element` / `is_absorber_edge`: a symbol's shape, an edge from K, L1-L3,
    M1-M5, exactly as written); another value is skipped with that reason, never normalised. A
    bundle with no live group skips it ("run `isaac bundle group`"). The interpretation carries
    the optional `field_path`, because a group target does not say which half it reads, and
    `field_path` is part of the identity that keeps a re-apply from recording it twice (element
    `K` and edge `K` from one line are two readings). The validator refuses such an
    interpretation on anything but a record group, or with a value of the wrong shape.
  - A `runs`-scope absorber finding is still recorded on the whole group, with `run_ids` naming
    which of the group's runs the finding named (also part of the identity). When that is fewer
    than all of them, the reading's `read_for` and its hint say so ("read for 1 of 4 runs in this
    group: <label> (<run id>)"), and so does the question text. An `experiment` finding carries
    no `run_ids`: it is about the whole group.
  - **After `bundle group --regroup`** the replaced groups that readings name are kept as
    superseded (§9), and the readings stay on them: they are never moved to the new groups by
    guess. The absorber question and `absorber_for_group` read only a live group's own readings,
    so apply the same findings file again; it lands on the new groups and adds only what is new.
  - **Versioning of these fields.** `source_path`, `quote`, `strength` and `finding_id` joined
    `ai_interpretation` at `1.2.0`; `field_path` and `run_ids` are `1.3.0` (§9 "What 1.3.0
    added"). The branch carrying 1.2.0 has been pushed, so a 1.2.0 bundle may exist outside this
    checkout; that is why this change is a version and not an edit of 1.2.0.
- **The fix this needed in the questions.** A missing value an AI reading lifted to
  `needs_review` used to drop out of `questions.json`: its question disappeared exactly when a
  suggestion arrived. It is now still asked. The reading is the first hint (`kind: ai_suggestion`,
  with the file, locator, quote and model), and the question text names it as a suggestion that
  needs confirmation.
- **Newly answerable fields** (`bundle.LOCAL_ANSWER_FIELDS`):
  `context.electrochemistry.electrolyte.name`, `.electrolyte.concentration_M`, `.pH`,
  `.potential_scale` and `.potential_setpoint_V`. Both the vendored v1.05 schema and the pinned
  portal schema declare them, the website has no write route for them, and beamtime notes often
  state them. They are `missing_values` like any other writable field (a run with a parsed
  potential has its candidate instead, and no missing value). Such a candidate's
  `not_proposable_summary` says this local import writes the field
  (`bundle.LOCAL_WRITE_PATH_REASON`, also for `UPSTREAM_TARGET_FIELDS`); the engine's "this build
  cannot write it yet" is about the website and stays in `not_proposable_reason`. A record whose
  electrolyte has a name but no concentration fails the schema at export, which is the gate working.
  - **The type gate is eligibility, not `decide`.** `decide` stores the answer it is given:
    `--value -0.8` without `--json` is the TEXT `"-0.8"`, and `"-0.8 V"` is text either way.
    `bundle.value_problem` then checks it against the vendored schema's `type` (`number` for
    pH, concentration and set-point), so the value is `scientist_confirmed` but not eligible
    ("must be number; got str"). `build-records` composes only eligible values, so the text
    never reaches the draft or the export; the group's report lists it under `not_composed` with
    that reason, so it cannot vanish unseen. The questions say which fields need `--json`. The
    metadata template refuses a non-number in a numeric column before anything is recorded.
  - **A non-finite number is never an answer (2026-10-29, no format bump).** Python's `json` reads
    `NaN`, `Infinity`, `-Infinity` (and `1e999`) as floats and writes them back as tokens that are
    not standard JSON. **The previous build accepted `decide --json --value=NaN`, stored the bare
    token, called the value eligible, and `bundle check` said VALID — silently; that silent VALID
    was the bug.** Now: `decide`/`annotate --json` refuse such a `--value` before recording anything
    (`mutations.parse_value`); `bundle.value_problem` makes one ineligible for every field; a save
    refuses any non-finite number the STORED file did not already hold (`bundle.new_non_finite_paths`),
    and an import refuses any; the template refuses such a cell; processing turns one into `null` and
    names it on the result (`non_finite_values`, review flag `athena_value_not_finite` /
    `value_not_finite`). An Athena group whose `bkg_eshift` is not finite is KEPT, never dropped (a
    dropped version would silently make the result-of-record choice): it stays a listed version with
    its identity (project file, group, data hash), so `select_athena_version` still binds to it, but it
    has no energy axis — no e0, comparison `not_comparable`, no curve file, no plot, never
    `preferred_for_record` by default — and the flag `athena_energy_frame_unknown` is on the version
    and on the stored result (the run's `athena.notes` also say `athena_group_eshift_not_finite`).
  - **Recovery for a bundle that already holds one.** It is never bricked: the token stays in the
    append-only decision log, and a write that adds nothing new is accepted. `bundle check` reports
    it as STALE first (the stored "eligible" is refused now; any write or `build-records` re-derives
    it), and on every later check, VALID or STALE, it NAMES each one under `NON-FINITE:`, saying
    whether a later decision replaced it. Remedy: answer the target again with a number
    (`decide --target <id> --decision correct --value=298.15 --json`); that answer is eligible and
    composes, and the old token is then listed as replaced. Removing the token itself needs a hand
    edit; nothing requires it.
  - **A set-point needs its scale (interim decision, pending review by the domain owners,
    Oscar and Angel; `bundle.COMPOSES_ONLY_WITH`).** The group's confirmed set-points are checked
    for disagreement FIRST, over all of them: differing values are a `disagreements` entry and
    nothing is filled. Only an agreed set-point meets the scale gate: it is filled only when EVERY
    run it comes from has an eligible `context.electrochemistry.potential_scale` filled in the
    draft (or the scale is beamtime-wide). If any run lacks one, none is filled: that run's value
    is listed under `not_composed` with "a potential setpoint needs its confirmed potential_scale;
    the number alone does not say what it is relative to", and the others with "another run of
    this record group has this potential setpoint without its confirmed potential_scale, so the
    group's setpoint is not filled". This holds for parsed candidates and answered missing values
    alike. The values stay confirmed in the bundle; nothing is guessed about the scale.
  - ~~**Follow-up, not built:** `context.electrochemistry.control_mode`. The hosted mapping writes
    it beside the set-point, the schema's conditional rules key the set-point requirement on it,
    and it is not locally writable. It is not added here.~~ **Changed in 1.5.0 (DEC-90): built.**
  - **`context.electrochemistry.control_mode` is answerable** (`bundle.LOCAL_ANSWER_FIELDS`,
    `bundle.CONTROL_MODE_PATH`; format 1.5.0, §9 "What 1.5.0 added"). No parser states it, so every
    run that becomes a record has a missing value for it. Nothing is defaulted.
    - **Allowed values are the official schema's own `enum`**, read at runtime by
      `bundle.value_problem` (the vendored schema; the pinned portal schema declares the same enum
      and the questions read the export-target schema). No list is written in this repository, so a
      schema refresh changes what is accepted. `decide` stores what it is given: an answer outside
      the enum (e.g. `Potentiostatic`, `OCV`) is `scientist_confirmed` but not eligible ("is not one
      of the schema's allowed values"), never composed, and listed under `not_composed`. If the
      vendored schema cannot be read, `value_problem` refuses every value (fail closed): nothing is
      eligible against a schema nobody checked.
    - **Run scope, like `potential_scale`**, and not in the questions' `SHARED_PATHS`: one beamtime
      can hold an open-circuit reference, potential holds and dry samples with no cell, so it is
      asked per record group, never once for the beamtime. An optional question now lists, in
      `field_allowed_values`, the VENDORED schema's enum for each field it closes — the one list
      eligibility checks, so an answer outside a listed set is never eligible (this applies to
      `potential_scale` too). A field closed only by the export-target schema or the pinned
      vocabulary (e.g. `context.reaction.drive`) is not listed there, because eligibility does not
      refuse an answer outside those lists.
    - **Never derived, either way.** A mode is never inferred from a set-point being present, and
      no set-point from a mode. A confirmed set-point leaves the mode missing; a confirmed mode
      fills no set-point.
    - **The set-point it requires.** `bundle.required_record_paths(control_mode=...)` reads every
      `allOf` rule keyed on `context.electrochemistry.control_mode` (its `const`) from the schema,
      so the modes are not listed in code (in the official schema: potentiostatic requires
      `potential_setpoint_V`, galvanostatic requires `current_setpoint_mA_cm2`). Only one rule shape
      is understood: a single `control_mode` `const` as the whole condition, and a `then` requiring
      electrochemistry members. Any other rule whose condition names `control_mode` (an `enum`, an
      extra condition, an `else`, a `then` with other constraints) raises
      `bundle.SchemaRuleNotUnderstood` rather than being skipped, so a refreshed schema cannot
      silently drop a requirement. The composer
      passes the mode the DRAFT carries (a confirmed, eligible, agreed answer), so a draft whose
      mode is `potentiostatic` and whose set-point did not compose — unanswered, or held back by
      the scale gate above — lists `potential_setpoint_V` under `missing_required` and is
      incomplete. Differing confirmed modes in one group are a `disagreements` entry, as for any
      field, and nothing is filled. The questions (`bundle.control_mode_by_run`) use the composer's
      rule too: a mode counts only once a scientist confirmed it and it fits the schema — a parser's
      candidate (none exists today) under its governing decision (rejected or unconfirmed: nothing;
      corrected: the correction), or an answer to that run's missing value. Such a run's set-point
      question becomes blocking, with the same question id. An off-enum answer requires nothing.
    - **For domain-owner review (Oscar/Angel):** in a record group of several runs, one run answered
      `potentiostatic` and another left unanswered composes `potentiostatic` for the whole group's
      record (and so requires its set-point), as every run-scope field does today. Whether an
      unanswered run should instead hold the group's mode back is not decided here.
    - ~~**Known gap:** a confirmed `galvanostatic` mode makes `current_setpoint_mA_cm2` required, and
      that field has no local write route, so such a record is blocked until it gets one. The gate
      is correct; the answer slot is a follow-up.~~ **Closed in 1.7.0 (DEC-92): see the next item.**
  - **`context.electrochemistry.current_setpoint_mA_cm2` is answerable** (`bundle.LOCAL_ANSWER_FIELDS`,
    `bundle.CURRENT_SETPOINT_PATH`; format 1.7.0, §9 "What 1.7.0 added"), at run scope like the
    potential set-point. No parser states it, so every run that becomes a record has a missing value
    for it. Nothing is defaulted.
    - **A number, by the schema's own `type`.** The vendored schema says only `{"type": "number"}`;
      `bundle.value_problem` reads that at runtime. `--value -5` without `--json` stores the TEXT
      `"-5"`, and `"5 mA"` is text either way: confirmed, not eligible ("must be number; got str"),
      never composed, listed under `not_composed`. The questions' answer commands add `--json` for it
      (a blocking question's `--value <value> --json`; an optional question names it among the fields
      that need `--json`). The template refuses a non-number in its column.
    - **When it is required.** Only through the schema's rule keyed on `control_mode: galvanostatic`
      (`bundle.required_record_paths`, unchanged): a draft whose composed mode is `galvanostatic`
      lists it under `missing_required` until an eligible answer composes, and that run's question
      becomes blocking. `potentiostatic`, `open_circuit` or no confirmed mode require nothing of it.
    - **No companion gate (DEC-92)** — unlike a potential, which composes only beside its confirmed
      `potential_scale` (`bundle.COMPOSES_ONLY_WITH`). The potential's gate exists because the schema
      itself says the number is "on the scale declared by potential_scale": without the scale it has
      no meaning. Nothing like that holds here. The unit, milliamperes per square centimetre, is in the
      field's name; no schema field declares a reference or basis it is relative to; and no schema
      rule requires anything beside it. `sample.geometry.geometric_area_cm2` (optional) would matter
      only to turn a total current in mA into a density, and that conversion is a derivation, which is
      never done: the scientist gives the density itself.
    - **Never derived.** Not from a total current and an area, not from the mode (a confirmed
      `galvanostatic` fills no current), and no mode from it (a confirmed current leaves the mode
      missing). Differing confirmed values in one record group are a `disagreements` entry and nothing
      is filled.
    - **For domain-owner review (Oscar/Angel):** the schema does not say, for this field, whether the
      density is per geometric or per electrochemically active area, nor its sign convention (the
      pinned schema's read-out `current_density_mA_cm2` descriptor is geometric and IUPAC-signed,
      negative for cathodic, but that is a different field). The value is stored exactly as the
      scientist gives it; neither is checked or converted.

## 21. Nested ZIPs and analysis files (`.larix`, `.pxp`) — no format bump

Additive and optional: no schema change, no `format_version` change. A 1.2.0 bundle that holds
none of this validates as before.

### Nested ZIPs

- **A `.zip` found inside a folder import is walked one level deep**, by the same guarded walk a
  ZIP import gets (`bl15.archive.inventory_zip`: `..`/absolute refusal, symlink refusal, per-entry
  size, declared AND measured compression ratio, entry-count and total-byte ceilings, CRC checks).
  The hosted path does not do this; only the local import does.
- **Member names.** A member's `relative_path` is `<archive path>!/<member path>`, e.g.
  `Normalized/2_Pt/Electrode2.zip!/Pt_10_m900mV.nor`. The separator is `!/` and only counts
  after a `.zip`, so a directory called `Hello!` is not one. The string is relative and carries
  no `..` segment, so it satisfies the schema's `relative_path` unchanged. Members get a source
  row, a classification and readers exactly as loose files do; `parent_dir` is `<archive path>!`
  (plus any member sub-folder) and `depth` counts the archive as one level.
- **The container** keeps its own source row (it is a file the scientist has, with a digest). Its
  reader is `nested_zip_walk_v1`: `content_read: true` when the members were walked, with no
  statements of its own. A ZIP that will not open stays in `unread_files` with
  `reason_code: reader_refused` and the walk's reason.
- **Budget.** The folder's `ArchiveLimits` are shared: members count against the same entry and
  total-byte ceilings, so a folder of ZIPs cannot buy one ceiling each.
- **Depth is 1.** A ZIP among a nested ZIP's members is listed in `unread_files` with
  `reason_code: nested_archive_too_deep` and is never opened. A hostile member name (absolute, or
  with `..`) is listed with its name withheld (§8), as for a top-level ZIP.
- **Duplicates.** Two members whose paths are equal once normalised (a member written twice,
  `./b.txt` beside `b.txt`) are ALL refused with `reason_code: duplicate_path`, as is a member whose
  nested path a real file in the folder already holds (the real file wins). This refusal is
  local-only: it also applies to a ZIP given as the root, and the hosted `inventory_zip` default
  still keeps every copy, unchanged.
- **Staging.** The generic readers read from disk, so a nested ZIP's ACCEPTED members are written
  into a private temporary directory for the duration of `collect_all_generic` and deleted before it
  returns. Each is staged at a collision-free name (`z<zip>/m<member number><suffix>`, never derived
  from the member's name, so case-insensitive volumes, Unicode forms, a member `x` beside `x/y` and
  over-long names cannot collide or fail) and its bytes are hashed against the walk's
  `content_sha256` before a reader sees them. A member that cannot be staged, or whose staged bytes
  differ, is not offered to the readers and, if no engine reader read it, is listed in
  `unread_files` with `reason_code: member_not_staged` and the reason; the import continues. The
  staging budget is the engine's (the folder's own accepted bytes and entries first). Nothing is
  written beside the source.
- **Not covered:** a ZIP given as the root does not expand ZIPs among its members (they are listed
  as ordinary unread files), and `isaac bundle show ... excerpt` re-walks without nested expansion,
  so it cannot show text from a nested member.

### Analysis files

A scientist's ANALYSIS file is **never a run, never a record group, never a processed output.**
Its source gets `classification.source_type: analysis_file:<kind>` (classifier id
`local_import_analysis_file_classifier_v1`) and `reader {reader_id, content_read: true,
statements_read, statements_suppressed, partial, skipped_total}`. Its statements are
`extended_context[]` entries: `source_recorded`, `scope: "analysis_file"`, `run_id: null`, no
`processed_output_id`, `official_path: null`, a verbatim `raw_literal` and a `locator`. They are
evidence a scientist may read; nothing maps one onto an official field.
A file that cannot be read stays in `unread_files` with `reason_code: reader_refused` and the
reader's reason; its source carries `content_read: false`.

Every file's first entry is `<kind>.reader_summary` (locator `file`): the reader's own counts,
caps and skips as JSON. A clipped literal ends with `[clipped: first N of M characters]`.

| Reader id | File | Read with | Concepts (locator) |
|---|---|---|---|
| `larch_session_v1` | `.larix` | gzip (or plain text beginning `##LARIX:`), standard library | `larch.header.*`, `larch.config.*` (`line N`); `larch.group.<attr>`, `larch.group.callargs.<fn>.<kw>`, `larch.xasgroup.filename/groupname` (`symbol <name>`); `larch.data_file`, `larch.param.<fn>.<kw>`, `larch.param.set.<attr>` (`command N`); `larch.command` (`command N (lines A-B)`) |
| `igor_pxp_v1` | `.pxp` | packed-file record headers, standard library | `igor.history_line` (`history line N`); `igor.procedure_text`, `igor.recreation_macros`, `igor.packed_file_text/name/type` (`record N (<kind>)`); `igor.data_folder` (`record N (data folder start)`); `igor.wave` (`record N (wave, data folder root:...)`); `igor.wave_note` (`record N (wave note)`) |

Bounds (also stated per file in its summary):

- **`.larix`**: decompressed text <= 64 MiB and <= 200x the compressed size; <= 200,000 history
  statements scanned; commands <= 6,000, data files <= 2,000, parameters <= 3,000, symbol-derived
  entries <= 6,000; a literal <= 500 characters (header, config, parameter and symbol values 300; names placed
  in a concept or in the summary 64, at most 40 listed there). `command N`
  numbers ALL history statements; display-only calls (`plot*`) are counted by name and not stored.
  Parameter entries are thinned on `(concept, literal)` (first locator kept, repeats counted).
  **Withheld, and counted:** the machine name, the machine id and the saving user's profile paths.
  The session is read as text; no statement is executed or evaluated.
- **`.pxp`**: <= 100,000 records; data folders nest <= 64 deep (starts past that are counted) and a folder
  path in a locator is clipped at 200 characters; a record with a negative length or one running past the end of
  the file ends the walk (`malformed_length`, what was read before it is kept); <= 1 MiB read of a
  text record and 16 MiB in all; history lines <= 5,000 (500 characters each), text records <= 8,000
  characters, waves <= 5,000, wave notes <= 1,000; a file over 256 MiB, or whose first header is
  plausible in neither byte order, is refused. Record types and waves it cannot parse are skipped and
  counted by type. The packed-file layout (type 8) is the one observed in a real Igor 6 experiment
  and anything else is skipped as `packed_file_unrecognised`. A wave's data is never read.
- Across all analysis files in one bundle: <= 30,000 entries.

## 22. What the build applies vs what the files show (2026-10-29) — no format bump

The engine reads every import with one acquisition system and one filename convention, both
Beamline 15-2's, whatever the files are. Their ids name code and stay everywhere
(`experiment.acquisition_system.system_id`, `generator.naming_profiles[]`, each source's
`naming_profile.profile_ids`). Their **display names** named a beamline, so a Beamline 4-3 or
6-2c bundle read as if its data were BL15-2 exports. The bundle now applies the facility hint's
own test (`DEC-88`, §20): does any run's scan headers carry the system's detector column names?

- **`experiment.acquisition_system`** keeps `system_id` and `candidate_channels` and gains
  `applied_as: "build_default"`, `runs_with_its_columns`, `columns_seen` and a `statement`.
  `display_name` is present **only when `runs_with_its_columns` > 0**; the statement then says
  column naming is not proof of the beamline. When it is 0 the statement says the name is not
  shown because nothing in the files says they were taken with that system.
- **`naming_profiles[]`**: a `build_default` binding scoped to the `acquisition_system` has
  `display_name: null` when the acquisition system is not shown, and its `selector_description`
  says the convention is applied whatever the files are and was not detected from them. A
  binding the user chose (`--profile`) or a stored rule made is unchanged.
- **`extended_context[]`**: a `filename token …` statement from a file whose name recurs in two
  or more folders of the import, and which is no run's acquisition or scan file, has a clause
  added to its `locator`: the name recurs in N folders, so it is reused and its tokens need not
  describe this run or beamtime. This is a count, not a template detector: `entry_id`,
  `concept`, `raw_literal` and the tokenization are unchanged. Measured on the real corpus,
  such tokens (`AgL3`, `MoS2` from reused `.exp` macro names) reached no sample, sample-name
  reading, candidate, question hint or record-group basis. They were only `unknown_token`
  context. A question cites such a file only as the path its own literal came from.

**Why no format bump.** `experiment.acquisition_system` is an untyped object in bundle-v1, and
`naming_profile.display_name` and `selector_description` were already `string | null`. The
1.6.0 schema accepts and refuses the same bundles. No question, missing-value, candidate,
group or extended-context id moves. A bundle written before this change still carries the old
display names; `suggestions.facility_hints` ignores them unless the column test passes, as
before. `reading.full.json` (the raw engine state, not the contract) is unchanged and still
holds the engine's names.
