# ISAAC Local Import Bundle — contract v1

Status: **v1.21.0** (the end review: after `build-records`, `isaac bundle review` lists every value a rule filled that the built records carry, by field, with its record count, its rule in plain words and its shortest witness, and the processing rule's scan keep / drop decisions; the scientist's yes is ONE experiment decision `review` (`bundle review --accept --by --apply`, never `decide`) binding each listed fill by target, value, rule and an evidence hash, so each bound fill derives `scientist_confirmed` (basis `reviewed_final_records`) until any part of it changes, when it is `filled` again; a decision beats the review; no rule changed, so the fill rule set stays 3, 2026-11-26, DEC-99, §9 "What 1.21.0 added"; v1.20.0 the folder, the people and the held potential: the sample measurements held at a potential their own files give, with corroboration that they were electrochemical, take the environment convention the scientist gives ONCE for the beamtime (`set_environment_convention`: operando, in situ, or per run), asked by one question that covers each run's own environment question meanwhile; the facility and beamline the folder name and the SPEC fingerprint agree on, for each run whose own headers carry the fingerprint; the producing organization as that facility; the producing group from the PI the folder names, beside a second source that agrees; the import keeps the readme's header lines; fill rule set 3, so a 1.19.0 bundle is STALE where a value moves, 2026-11-25, DEC-98, §9 "What 1.20.0 added"; v1.19.0 fills from CHECKED, STATED Claude readings: `annotate --from-readings --apply` keeps each reading's quote check — result, checker, a reading-pass id, the checked file's `content_sha256` and a `reading_sha256` over the reading itself, all recomputed by the validator — and its scope; `isaac.fill.reading_stated.v1` fills what a checked stated reading's quote itself states (the number, the list member, every significant word), never an inferred reading, a sample's own label as its material, or a beamtime reading on a run-level or sample field; fill rule set 2, so a 1.18.0 bundle is STALE where a value moves, 2026-11-25, DEC-97, §9 "What 1.19.0 added"; v1.18.0 fill first, review at the end: the value state `filled` — a value a registered fill rule supports, `isaac.fill.parser_exact.v1`, `isaac.fill.stored_convention.v1` or `isaac.fill.domain_from_acquisition.v1`, and no scientist decided — is eligible, goes into a draft as `inferred` naming its rule, and is not asked; a decision always wins; a 1.2.0–1.17.0 bundle is STALE until its next write, which logs each filled value, 2026-11-25, DEC-96, §9 "What 1.18.0 added"; v1.17.0 the scientist's consent to Claude reading the files, and their name, kept in `consents` so a second session reads it with `isaac bundle status` instead of asking again; a command that only reads never writes `bundle.json`, and the values it prints are recorded beside it in `exposures.pending.jsonl`, 2026-11-23, §9 "What 1.17.0 added"; v1.16.0 the second round of the 18 Nov 2026 audit's import rules: the potential an SSRL XDC run's name writes, as a suggestion that needs review; a scan title naming other scans makes a processed output, never a run; an overwritten macro, two comment-line events and a position within motor resolution are no conflicts; the clock zone an #E / #D pair gives is suggested; a BL4-3 standard named as one proposes the role reference and the scanned range a witness for the absorber, 2026-11-22, §9 "What 1.16.0 added"; v1.15.0 the `export_despite_completeness` record-group decision: a record the local record-completeness gate holds is exported anyway, for that record body, and later exports keep it, 2026-11-22, §9 "What 1.15.0 added"; v1.14.0 four import rules of the 18 Nov 2026 audit: a signed potential token in a file name, the technique from the instrument configuration, pellet-standard fields asked only where mentioned, and a comment line left over from an earlier run flagged; every id an earlier build gave stands on a re-import, 2026-11-19, §9 "What 1.14.0 added"; v1.13.0 a file whose own scan title states an average beside SPEC acquisitions — the scientists' averages, such as a PyMca `.mca` — is a processed output linked by legacy number, never a run; a `MERGE` folder alone only flags a run; and a processed product's file name is no longer read as a condition or sample reading of its run, 2026-11-18, §9 "What 1.13.0 added"; v1.12.0 a reading pass's quotes are checked against the cited file when it is loaded, and its notes about a run's scans are kept as `scan_notes`, AI readings never decisions, 2026-11-17, §9 "What 1.12.0 added"; v1.11.0 a file the engine classifies `processed_spectrum` — the scientists' quick merges — is a processed output linked by legacy number, never a run, 2026-11-09, §9 "What 1.11.0 added"; v1.10.0 an answer refused only because it is not on its field's list is kept as a vocabulary request, `vocabulary_requests`, and `bundle propose-terms` drafts it, 2026-10-30, §9 "What 1.10.0 added", §29; v1.9.0 (`set_counter_positions` may name the LAST file-name token, `--positions last`, and a scientist's merge has a working path, 2026-10-30, §9 "What 1.9.0 added", §27; v1.8.0 the bounds on `scientist_decisions` and `ai_interpretations` raised to 200,000, so an append-only log can no longer lock a bundle; decide refuses a value its field refuses, 2026-10-29, §9 "What 1.8.0 added", §25; v1.7.0 `context.electrochemistry.current_setpoint_mA_cm2` answerable, so a confirmed galvanostatic record can complete, 2026-10-29, §9 "What 1.7.0 added", DEC-92; v1.6.0 capture decisions — keep apart, the Athena result of record, "no counter" — a merge decision applied as one combined group, and question ids that survive answers, 2026-10-29, §9 "What 1.6.0 added"; v1.5.0 control mode answerable the same day; v1.4.0 the SSRL XDC scan start time, the instrument clock's time zone and its binding, 2026-10-29, §9 "What 1.4.0 added"; v1.3.0 absorber readings on record groups, a larger writable set and STALE bundles, the same day; v1.2.0 processed outputs 2026-10-28; v1.1.0 LOCAL-2 and v1.0.0 LOCAL-1 the same day). Machine contract:
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
| `exposures.pending.jsonl` | **1.17.0.** Present only after a command that only reads printed parser values: one exposure per line (`bundle_id`, `target`, `command`, `at_utc`), read back by every load and folded into `exposures[]` by the next write, which removes it (§11). Not written by `import`. |

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
| `consents[]` | **1.17.0, optional.** The scientist's answer to whether Claude may read this beamtime's files (ISAAC usage agreement), the name it was given under, when, and the folder; append-only, the latest entry holds (§9, "What 1.17.0 added") | scientist's own word |
| `validation` | bundle-schema result at write time; `official_record_validation: not_applicable` | deterministic validation |
| `readiness`, `counts`, `bounds`, `authorities` | derived summaries; see §7 for bounds | — |

## 4. The four authorities — kept distinct

1. **Source evidence** — what a file literally says, at a locator. Never rewritten;
   normalisation is recorded *beside* the literal (`evidence[].normalization`), not over it.
2. **Extraction / interpretation** — what deterministic readers, stored rules and AI
   interpretations made of the evidence. ~~Suggestions. An AI interpretation can raise a value
   to `needs_review` and never higher.~~ **Superseded 2026-11-25 by DEC-96 (1.18.0):** a value a
   REGISTERED fill rule supports (`bundle.FILL_RULES`, carried as `fill.rule_id`) and no scientist
   decided is `filled`: it goes into a draft as `inferred` with a derivation entry naming the rule,
   and the scientist reviews it at the end. Everything else stays a suggestion, and an AI
   interpretation on its own still raises a value to `needs_review` and never higher.
   **Narrowed 2026-11-25 by DEC-97 (1.19.0):** "an AI interpretation on its own" now means an
   UNCHECKED one. A STATED Claude reading whose quote check is stored on it (`quote_check`, tied to
   the bundle's own source bytes and to the reading itself) and whose quote itself states the value is
   the evidence of one registered rule, `isaac.fill.reading_stated.v1` (§9 "What 1.19.0 added"); an
   inferred reading, and a reading without the block (`annotate --target`, an older bundle), never fill.
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

`source_recorded | candidate_extracted | needs_review | conflicting | filled | scientist_confirmed |
rejected | unmapped | missing` (`filled` since 1.18.0, DEC-96). Mapped from the EXISTING contracts — not a second machine:

The single key is `SemanticCandidate.review_status` (itself derived from `kind`, `determinism`, `unresolved_reason`, `not_proposable_reason`, `resolved_by_rule` and the target path); `bl15/mapping.py` statuses are listed only as what they usually produce — measured on the 9-run fixture, `deterministic`/`normalized` concepts also land in `needs_review` (e.g. a local-time timestamp) and `needs_domain_review` lands in `unmapped` 3 times.

| Existing contract | Bundle `extracted_state` |
|---|---|
| `SemanticCandidate.review_status == "ready"` (field kind, a target path this build can write — `field_paths.PROPOSAL_TARGET_PATHS` — no `unresolved_reason`, no `not_proposable_reason`) — on the fixtures always mapping status `normalized` or `deterministic`. The server would let a person open a proposal (`proposals.STATE_OPEN`) for it | `candidate_extracted` |
| `review_status == "needs_review"`: a target path exists but something holds the value — mapping `needs_domain_review`, `blocked_by_build` (no write path), local time with no zone, a structural run/experiment candidate, a beamtime-scope value, a logbook sentence with no value | `needs_review` |
| `review_status == "sources_conflict"` (`unresolved_reason == "sources_disagree"`) | `conflicting` |
| `review_status == "unmapped"` (field kind, `target_field_path is None`; mapping `not_expressible`) | `unmapped` |
| `review_status == "ready"` but every file witness is a notes (logbook) sentence about the WHOLE beamtime (a `bl15.notes.*_statement.v1` reading with no `section`, no `file_numbers`, no `named_samples`; polish c6-a): beamtime context, not the run's value. The local import holds it (`state_basis.not_proposable_reason` = `bundle.BEAMTIME_WIDE_REASON`, so `review_status` re-derives to `needs_review`); an older bundle is held the same way IN MEMORY by every reader (`mutations.load`, the CLI's `list` / `show` / `check`, the web page's `read_bundle`; the counts it moves move with it, and a read writes nothing: the version stays the stored bytes' hash), and on disk by the next save (`save_bundle`), which logs each value the stored file gave as extracted in `eligibility_rederived[]` (reason `bundle.BEAMTIME_WIDE_REDERIVED_REASON`; eligibility does not move: an extracted value was never eligible) and prints one stderr line ("held N value(s) read only from a beamtime-wide notes sentence for review"). The per-value log, not `format_upgrades[]`: the hold changes no format and no writable path, and a `format_upgrades` entry marks an upgrade done and drives the composition's disclosure rule (polish c6-r). No shape change, no format bump; the hosted engine is unchanged | `needs_review` |
| `review_status == "resolved"` (a stored convention rule or standing resolution applied) and proposable | `candidate_extracted` (`method: stored_rule`) |
| `review_status == "resolved"`, not proposable | `needs_review` |
| a writable target path no candidate states for that run (or for the record) | `missing` |
| extended context, data-quality notes, contributors | `source_recorded` |

| Recorded later | `value_state` | Proposal-lifecycle analogue |
|---|---|---|
| `scientist_decisions` `confirm` / `choose_reading` / `provide_value` | `scientist_confirmed` | `proposals.STATE_ACCEPTED` (which on the server also needs a trusted actor) |
| `scientist_decisions` `reject` | `rejected` | `proposals.STATE_REJECTED` |
| no decision at all (not even a `defer`), and a registered fill rule supports the value (1.18.0, DEC-96; the `fill` block names the rule and the value) | `filled` | — (no person accepted it: the end review is where the scientist sees it) |
| no decision, and a CHECKED, STATED Claude reading whose quote states the value supports it (1.19.0, DEC-97: `isaac.fill.reading_stated.v1`; the `fill` block names the rule, the value and the readings) | `filled` | — (the end review is where the scientist sees it) |
| a fill the scientist's END REVIEW still binds: a `review` decision names this target with the same rule, value and evidence hash the fill has now (1.21.0, DEC-99; the `fill` block stays, and the `review` block names the decision and the basis `reviewed_final_records`) | `scientist_confirmed` | `proposals.STATE_ACCEPTED`, accepted by reviewing the final records |
| `ai_interpretations` on a `missing` / `unmapped` / `candidate_extracted` value no rule fills | `needs_review` | — (an interpretation is never a proposal acceptance) |

The derivation is `bundle.derive_value_state(extracted_state, decision, interpreted, fill_rule)`,
in this order: a decision decides; else a fill rule (`bundle.fill_rule_for`) makes the value
`filled`; else an AI interpretation lifts it to `needs_review`; else the parser's state stands. An
AI reading that AGREES with the value never stops a fill; one that disagrees (another value, or
none) always does, because the rule itself refuses it. The
validator recomputes it for every candidate, missing value and conflict and refuses a bundle
whose stored `value_state` (or `fill` block) differs, so a hand-written `filled` no rule gives is
contract-INVALID. `filled` is not an `extracted_state` (schema enum). `scientist_confirmed` and `rejected` are **not**
`extracted_state` values (schema enum), so parser output cannot produce them; a hand-edited
`"value_state": "scientist_confirmed"` with no decision is contract-invalid. A later decision
for the same target supersedes an earlier one (last wins). A conflict stays `conflicting`
under an AI interpretation. **Missing stays missing**: no default, no room-temperature
assumption (since 1.18.0 a missing value is `filled` only by a registered rule that names its
evidence — `system.domain` from the acquisition files, and since 1.19.0 a checked Claude reading of the
field (DEC-97) — a rule, never a default), and a
beamtime fact is never copied onto a run (DEC-69: environment, reaction
and cell type are never filled from a beamtime statement); `missing_values[].value` is the
schema constant `null`.

### Eligibility for an official record

`eligibility_for_official_record: {eligible, reason}` per value. ~~**Rule: eligible only when
`value_state == scientist_confirmed` AND there is a value AND the target path has a write
route in this build (`PROPOSAL_TARGET_PATHS`).** Nothing a parser or AI produced is eligible
on its own — not even `candidate_extracted`, because on the server such a value still needs
a trusted person to accept the proposal. … Every v1 bundle `isaac import` writes
therefore has `readiness.eligible_value_count == 0`.~~ **Superseded 2026-11-25 by DEC-96
(1.18.0): eligible only when `value_state` is `scientist_confirmed` OR `filled`, AND there is a
value (for a filled value, the value its rule fills), AND the target path has a write route in
this build (`bundle._writable_paths`), AND the value fits its field.** A `candidate_extracted`
value no rule fills, and anything an UNCHECKED AI reading alone gave, is still not eligible (since
1.19.0, DEC-97, a value a checked, stated reading fills under the reading rule is `filled`, so eligible). A filled value
composes into a draft as `status: "inferred"` with the evidence entry
`{"source_type": "derivation", "rule": "<rule id>", …}` (`records.fill_derivation`, the shape
`draft_validator` accepts, as `context.temperature_basis` does under DEC-76), and the field is
`inferred` whenever ANY contributing value is filled (`verified` only when every one is
confirmed). A filled value composes into a record group only when every measured run of the
group has the same filled or confirmed value (or a beamtime-wide one covers them all); DEC-69
still holds. "Eligible" means "may be carried into a draft for review and `isaac export`",
never "is official". A fresh import's `readiness.eligible_value_count` is therefore the number of
values a rule filled (`counts.filled`).

## 7. Bounds

Enforced by the builder (refuse, or clamp visibly and count) and by the validator.

| Constant | Value | Why |
|---|---|---|
| `MAX_RUNS` | 5,000 | one run per acquisition at most; the walk inventories ≤ `ArchiveLimits.max_entries` (5,000 = 4× the measured 1,192-file corpus) |
| `MAX_CANDIDATES` | 4,000 | the engine's own `MAX_CANDIDATES_PER_SESSION`; ~1,000 measured on the real corpus. Engine truncation is reported in `bounds.candidates_truncated_by_engine` |
| `MAX_EVIDENCE_PER_CANDIDATE` | 256 | the engine keeps 5 supporting statements plus every disagreement reading; past 256 the list is a window with `evidence_truncated: true` |
| `MAX_STRING_CHARS` | 20,000 | above the engine's longest stored prose (12,000); a longer string is clamped with a visible marker and counted in `bounds.strings_truncated` |
| `MAX_SCIENTIST_DECISIONS` | 200,000 | (1.8.0; 20,000 before) `scientist_decisions` is append-only, so its bound must sit with the other per-entry bounds (`missing_values` and `exposures`: 200,000), not below them. A `decide` that would pass it is refused up front with the reason (`mutations.log_full_message`), before anything is appended; in practice `MAX_BUNDLE_BYTES` binds first, and a write past it is refused by the validator the same way |
| `MAX_AI_INTERPRETATIONS` | 200,000 | (1.8.0; 20,000 before) `ai_interpretations` is append-only too; an `annotate` past it is refused up front the same way |
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
  nested ZIP's, or a ZIP root's, accepted members in a private temporary directory that is
  deleted before the import returns); symlinks are never followed; no source is ever
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
  `scientist_confirmed`, `split` → `split`, `merge` → `merged`, `reject` → `rejected`. A `split`
  also makes ONE proposed group per `split_into` list (§28; before 2026-10-30 the lists were stored and
  never read).
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
  zoned instant; the field's allowed values (`bundle.allowed_values`, §26) and the vendored schema's
  `type` at that path.
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
    do not hold their runs. A `split` group's runs are held by the groups its decision made (§28): the
    regroup proposes them again under their own ids and keeps their runs out of the fresh proposal. `merged` is history, not binding: only a confirmed group becomes a
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
  only the names; **the runs' file names have the same tokens** once repeat markers and the positions a
  scientist declared run counters are left out — or, where they still differ, the same
  `sample.material.name` is confirmed for every run (1.9.0, §27); and no confirmed, eligible
  run-level answer (an answered missing value or a confirmed reading, e.g. the control mode) differs.
  **There is no exception by token shape.** Three review rounds measured that any shape rule leaks
  (`0.05V`/`0.5V` and `1.02`/`1.03` split on the decimal point; `05_mM`, `02_hrs`, `05_rpm` are units
  no list covered; `400`/`500` is a unitless potential), so ANY differing token blocks and the
  `scientist_decided_merge` candidate stays open, its detail naming the differing tokens; since 1.9.0
  the `merge_decisions_not_combined` entry also lists `next_commands` that, followed, combine the runs
  on the next regroup (§27). Merge candidates
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
  the version with that identity (`bundle.athena_resolve`). A SET of the scientist's per-scan Athena
  groups (`provenance.per_scan_set`; its project file and Athena group are its first member's) has
  `data_sha256_prefix` `set-` + 16 hex of a sha256 over each member's data hash and parameters, so a
  selection recorded on one curve never resolves to a set that holds it, nor a set's to one curve
  (c10-r). A project whose set is identical to another's (same curves, same parameters) is one set, named
  in `provenance.per_scan_set.identical_in_projects` (and the Athena result's `inputs[].per_scan_set`) and in
  the `identical_athena_set_in_several_projects` note of `isaac process`; copies in several projects are one
  curve only when their parameters are the same too. Replaying a selection is "unchanged" only
  when it names the same identity (re-selecting an id that a renumbering gave to another curve is a new
  decision), and `changed_after_approval` compares identities, not ids. A selection alone does not freeze the
  result against `isaac process`: a fresh result of the same id replaces it when it holds a version
  with that identity — re-pointed to its new id if it moved, said in
  `athena_result_of_record_basis.repointed` {`decision_value`, `now`, `note`}. When it holds NO such
  version (c10-r) the fresh result replaces it too: the choice is never carried over to another curve
  nor left on a stale result. `athena_result_of_record` is `null`, the result carries
  `athena_selection_not_carried_over` {`decision_id`, `value`, `decided_by`, `statement`}, its question
  is asked again (its text says which earlier choice no longer matches), and `isaac process` replies
  `athena_selections_not_carried_over` {`results`, `statement`} (also a summary line). The note drops
  out once a new selection resolves. A result nothing fresh replaces is kept as it was. Only the latest
  selection counts, and the validator refuses one that resolves to no listed version unless the
  result's `athena_selection_not_carried_over` names that decision.
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
- **`defer` on the experiment** (`decide --question <counter question> --decision defer --by NAME`, or
  `--target experiment --decision defer`): "I don't know which positions are counters". Recorded as an
  ordinary `defer` decision on the experiment target; it names no position, so grouping is unchanged by
  it. The counter question stays open under the same id and carries `deferred` {`by`, `decided_utc`,
  `decision_id`} while the latest of the question's answers (`set_counter_positions`,
  `set_not_counter_positions`, `defer`) is a defer (`questions.counter_deferral`); a later answer
  supersedes it. No shape changes: `defer` and the experiment target were already in the schema.
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

### What 1.8.0 added (the bounds of the append-only logs)

A minor version: the schema **accepts more** (it refuses nothing 1.7.0 accepted). `scientist_decisions`
and `ai_interpretations` may hold up to 200,000 entries (`bundle.MAX_SCIENTIST_DECISIONS`,
`bundle.MAX_AI_INTERPRETATIONS`; the schema's `maxItems` is the same number, pinned by a test). At the
1.7.0 bound of 20,000 the next decision failed validation, and since the log is append-only every later
write did too, with no recovery. Nothing in the bundle's shape changes, nothing becomes newly writable,
and `processed_outputs` is required at 1.8.0 as at 1.2.0–1.7.0.

- **A 1.8.0 validator accepts 1.0.0–1.7.0 bundles;** a 1.7.0 validator refuses a 1.8.0 one (the label),
  and one past 20,000 entries.
- **The upgrade is disclosed, never silent.** The first write by this build of an older bundle appends
  one `format_upgrades` entry whose statement includes `bundle.CHANGES_ADDED_IN["1.8.0"]` (printed once
  to stderr, shown by `check` and summary.md). No eligibility moves for it.
- **A write past either bound is refused up front** (exit 2) with a sentence naming the log, how many it
  holds and the bound; nothing is appended (§7, §25).

### What 1.9.0 added (the last token as a counter)

A minor version: the schema **accepts more**. A `set_counter_positions` decision may name `-1` among
its `positions` — the LAST file-name token, whatever the name's length (`grouping.LAST_POSITION`;
`decide --positions last`, or `3,last`). Measured on a real beamtime, the counter was always the last
token, at positions 3..10, and a fixed list also named a non-counter token of the longer names.
`set_not_counter_positions` takes whole-number positions only. Nothing else changes, nothing becomes
newly writable, and `processed_outputs` is required at 1.9.0 as at 1.2.0–1.8.0.

- **A 1.9.0 validator accepts 1.0.0–1.8.0 bundles;** a 1.8.0 validator refuses a 1.9.0 one (the label),
  and one holding `-1`.
- **The upgrade is disclosed**: the first write by this build of an older bundle appends one
  `format_upgrades` entry whose statement includes `bundle.CHANGES_ADDED_IN["1.9.0"]`.

### What 1.10.0 added (vocabulary requests)

A minor version: the schema **accepts more**. The optional top-level `vocabulary_requests` section
(at most 20,000, `bundle.MAX_VOCABULARY_REQUESTS`) keeps each answer a scientist gave that its field
refused ONLY because it is not on the field's allowed list (`bundle.off_list_only`: every other check
passes). Each holds `request_id` (`vr-00001`), `field_path`, `term` (exactly as given), `requested_by`
(the `--by`, `local_unverified`; `null` when no name was given), `requested_utc`, `scope`, `targets`,
`run_ids`, `source` (`decide_answer` / `template_cell` / `adopted_sheet_cell`, the command, and the
decision and question, or the file NAME and cells; `as_said: true` on a `decide_answer` kept with
`--as-said`), the scientist's own `note`, and an optional `reaffirmed_utc` (the same `--as-said` answer given
again). An older 1.10.0 build refuses a bundle once a request carries `reaffirmed_utc`, because a request is
`additionalProperties: false` there. It is **never a
decision and never a value**: no record, question or eligibility reads it. Nothing becomes newly
writable, and `processed_outputs` is required at 1.10.0 as at 1.2.0–1.9.0.

- **A 1.10.0 validator accepts 1.0.0–1.9.0 bundles;** a 1.9.0 validator refuses a 1.10.0 one (the label),
  and one holding the section.
- **The upgrade is disclosed**: the first write by this build of an older bundle appends one
  `format_upgrades` entry whose statement includes `bundle.CHANGES_ADDED_IN["1.10.0"]`. A statement may
  now be 1,500 characters (600 before): from 1.4.0 or older, every change since no longer fit.

### What 1.11.0 added (the scientists' quick merges, by the engine's classification)

A minor version: the schema **accepts more**, and only where the project owner approved it. Measured on a real
BL15-2 beamtime: 32 headerless two-column `.txt` files in a `MERGE/` folder (the scientists' quick merges at the
beamline) each became a run through the two-column reader — 32 measurements nobody performed, each with a record
group and questions.

- **Origin** `isaac.processed_output.origin.engine_classification.v0` (`processing_origin.basis:
  engine_classification`; `bundle.ENGINE_ORIGIN_RULE_ID`): a file a generic reader read whose ENGINE classification
  (`sources[].classification.source_type`, `bl15.classify`: no header, every opening line two numbers) is
  `processed_spectrum` is a processed output, never a run — ONLY when the bundle also holds an engine SPEC acquisition
  run (`bundle.quick_merges_apply`). A root of headerless two-column files alone (another facility's energy/mu
  exports) keeps them as runs, each with the run anomaly `engine_reads_processed_spectrum` asking a scientist which it
  is. The folder and the file name decide nothing: the same file outside `MERGE/` is kept the same way. Every
  statement-derived origin field is empty or false (the file states nothing about itself). `.mca` files are the
  engine's `detector_product` and are not touched. The validator re-derives the condition from the stored runs (an
  engine-classified output without a SPEC run, or — in a bundle a 1.11.0 build imported — such a file kept as a run
  beside SPEC runs, is refused) and re-derives what it can of the origin: the source is classified
  `processed_spectrum`, is the same file (path, sha256), and the output states nothing a headerless file cannot. The
  classification itself is not re-run: it reads the file's content, which a bundle does not hold.
- **Link** `isaac.processed_output.link_by_legacy_number.v0` (`bundle.LEGACY_LINK_RULE_ID`, `match: legacy_number`),
  for these outputs ONLY (an XDI output keeps `link_by_run_stem.v0`, byte for byte). The whole-number tokens a name
  starts with: the last is the electrode number and must equal the run's second token (both absent is equal, and then
  the two names must also share a word after the number, else `no_run_named_like_it`); the others are legacy numbers,
  matched to `runs[].legacy_number`, which the validator re-derives from an engine run's stem
  (`bl15.applicability.legacy_number_of`). One legacy number and exactly one fitting run with
  scans: a proposed link, whose `assumption` says what was read and how the rest of the names differ (`f10` /
  `filter10_again`; never deciding). Several legacy numbers (`43_44_04_…`): `link_note.code: spans_several_runs`
  with every fitting run, no link. Several fitting runs (a shared legacy number): `ambiguous`. One fitting run
  without scans: `run_has_no_scans`. No leading number, or no fitting run: `no_run_named_like_it`. The validator
  re-runs the rule.
- **Processing** (`isaac.processed_output.quick_merge_compare.v0`, `processing/quick_merge.py`): each LINKED quick
  merge is compared with ISAAC's own result under `processing_results[].scientist_quick_merges` — a rough reference,
  never `preferred_for_record`, never truth, moving no id or verdict. Column 1 is read as energy only when strictly
  monotonic and inside the group's energy range (an assumption, recorded). Already normalised: compared as stored,
  edge step 1. Otherwise: raw signal against ISAAC's merged mu, the curve normalised with ISAAC's own parameters
  (said), and, for at most 10 scans, the one subset that alone rebuilds it named as an `exclude_scans` HINT, never
  applied.
- **A 1.11.0 validator accepts 1.0.0–1.10.0 bundles;** a 1.10.0 validator refuses a 1.11.0 one (the label), and one
  holding either rule. Nothing becomes newly writable; `processed_outputs` is required at 1.11.0 as at 1.2.0–1.10.0.
- **The upgrade is disclosed**: the first write of an older bundle appends one `format_upgrades` entry whose
  statement includes `bundle.CHANGES_ADDED_IN["1.11.0"]`: a bundle imported before holds such files as runs until it
  is re-imported, and when it still holds any beside SPEC runs the statement names them (`bundle.quick_merge_runs`)
  and says a re-import keeps them as processed outputs. Answers given to questions about those runs do not carry over: `isaac bundle answers import`
  reports each such row as `not_resolving` and applies nothing for it.

### What 1.12.0 added (the quote check, and scan notes)

Measured on a real BL15-2 beamtime: a careful reading pass over a 1,936-line logbook found the electrolyte per
sample, every potential set-point (linked by the step table's "File Number" = the run folder's leading number), the
cell, atmosphere, reaction and reference electrode, and the logbook's notes on which scans to leave out. The loader
took every quote as the reader gave it. Now:

- **The quote check** (`reading_check.py`; `annotate --from-readings [--root <folder>]`, `bundle check-readings`).
  Each finding's quote (at least 3 words or 12 characters; a shorter one only as at least 80 % of a text line its
  `line N` / at-most-3-line locator names, never for a whole-file or whole-document search) is held, whitespace-normalised (non-breaking spaces,
  curly quotes and dashes as their plain forms; case kept), against the file it cites under the imported folder
  (`source_root.local_root_hint` when recorded, and then `--root` must be that folder; else `--root`, whose name must
  be `source_root.label`'s). The cited path is resolved as the folder spells it (`./a`, `a/`, a case-only alias),
  and the bundle source is found by that path, so its hash check always applies; a file under the folder that is no
  source is reported `source_not_imported`. Text: within 3 lines of a `line N` / `lines N-M` (at most 20 lines)
  locator, in any of the forms `line5`, `Line #5`, `l. 5`, `ll. 4-9`, `row 5` (found elsewhere: fails, saying the
  line it is on); a locator holding any other number fails; one with no number searches the file. `.docx/.pptx/.xlsx`:
  in `extract`'s text, produced again in a temporary folder (no image written; every sheet paged to its end), on the
  `paragraph N` / `table N` / `slide N` / `[sheet S] row N` the locator names, else anywhere ("found in document,
  locator not checked"); in the `#` header lines (one scan's, for `scan N #C`)
  for a SPEC header locator; in a `.pdf`'s text layer, read page by page with `pypdf` (the `reading` extra, which
  `scripts/setup_isaac_local.sh` installs): a `page N` locator is checked on that page (on another page: fails,
  naming it), any other locator searches every page and reports the page. A page with no text layer (a scan)
  fails with "no text layer, so its quotes cannot be checked: tell the scientist what the page says instead"; without `pypdf` a PDF quote fails,
  naming the install command. An absolute
  path, a `..` part, a symbolic link anywhere along the path, a missing or non-regular file, or a bundle source
  whose bytes changed since the import (`content_sha256`) fails. The preview reports `pass`/`fail` per finding
  (`quote_check`); `--apply` records no finding that fails, and refuses (exit 2, nothing written) when no folder is
  known to check against. There is no flag to skip it. `check-readings` prints the same report and exits 1 when a
  quote was not found. A pass says the quote is in the file near its locator, never that the reading is right.
- **Refusals** are listed in `skipped` with `refused` (`quote_not_found`, `unknown_run`, `ambiguous_run`,
  `not_allowed_value`: a vocabulary field's value off its allowed list, `bundle.allowed_values`), counted in
  `refused_by_reason`. Before 1.12.0 an off-list value was recorded as an AI reading.
- **`scan_notes`** (optional section; `scan_notes.py`): a finding `{"kind": "scan_note", "applies_to": {"scope":
  "runs", "runs": [...]}, "action", "scans", "reason", "source", "quote", "strength", "reasoning"}`. `exclude` and
  `keep_only` list scan numbers, `start_from` exactly one, `flag` none (advice that changes nothing). Numbers are the
  file's own. Stored once (`scan_note_id`, a digest of runs, action, scans and citation) with its citation, `model`,
  `authority: ai_reading` and `recorded_utc`; a number past a run's `scan_count` adds `scan_count_note`. The
  validator checks the shape per action and that every run and source it names is in the bundle. A note naming more
  than 500 runs is refused alone; one on a run in no live group is kept, marked `run_live: false`. Notes on one run
  that cannot both be followed (`exclude` and `keep_only` of one scan, two different `start_from` or `keep_only`, a
  `keep_only` scan before a `start_from`) are listed as `conflicts` on each note, `scan_note_conflicts` on `show run`
  and `conflicts` on `list scan-notes`; nothing picks one. Read by
  `scan_notes.scan_notes_for_run(bundle, run_id)` (the processing step's accessor), `bundle show <dir> run <id>`
  (`scan_notes`) and `bundle list <dir> scan-notes`. AN AI READING, NEVER A DECISION: no record reads it and no scan
  is left out by it; the processing step may cite it in a scan-selection proposal, which the scientist decides.
- **A 1.12.0 validator accepts 1.0.0–1.11.0 bundles;** a 1.11.0 validator refuses a 1.12.0 one (the label), and one
  holding the section. Nothing becomes newly writable; `processed_outputs` is required at 1.12.0 as at 1.2.0–1.11.0.
- **The upgrade is disclosed**: the first write of an older bundle appends one `format_upgrades` entry whose
  statement includes `bundle.CHANGES_ADDED_IN["1.12.0"]`.

### What 1.13.0 added (the scientists' averages)

Measured on a real BL15-2 beamtime: beside its 32 headerless quick merges, the `MERGE/` folder held two PyMca `.mca`
averages (`#S 1 Average of 11 from Norm. …`). The engine classifies an `.mca` as a `detector_product`, so the 1.11.0
rule left them alone; the generic MCA reader made each a run, with a record group and questions, and processing said
`bl15_2_energy_column_missing`. And the engine attached each MERGE product to the run sharing its legacy number and
read its FILE NAME as that run's evidence, so a re-spelled merge name (`…after1200Cycling…` for the acquisition's
`…after1200mVCycling…`) became a spurious disagreement and a question.

- **The third origin rule**, `isaac.processed_output.origin.average_title.v0` (`processing_origin.basis:
  average_title`, `bundle.AVERAGE_TITLE_ORIGIN_RULE_ID`): beside SPEC acquisition runs (`bundle.quick_merges_apply`, as
  for the engine rule), a file a generic reader read whose OWN scan title states an average of N spectra
  (`<n> Average of <N> from <name>`, PyMca's title; `bundle.is_average_title`) is a processed output (`role:
  reference_result`), never a run, wherever it sits. Its statements stay evidence on the output. It is linked by
  `isaac.processed_output.link_by_legacy_number.v0`, as an engine-classified output is (`bundle.is_quick_merge` covers
  both). With no SPEC run beside it, the file stays a run, as before.
- **A folder name is never evidence** (review of PR #335, the lesson of #333). Any other file in a folder named
  `MERGE` (any case, any depth; `bundle.in_merge_folder`) stays a run, with an `in_merge_folder` note on it
  (`bundle.MERGE_FOLDER_NOTE_KIND`): "In a MERGE folder: is this the scientists' quick merge?". The scientist rejects
  its group (a quick merge, never a record) or confirms it (a measurement).
- **The validator** re-derives it: the source exists and is the same file (path, sha256), the output keeps that
  file's `scan_title` statement and it is an average title, and a SPEC acquisition run is beside it. In a bundle a
  1.13.0 build imported, a generic run every scan file of which states an average title beside SPEC runs is refused
  (`bundle.average_title_runs`).
- **A processed product is not evidence of its run.** The engine's reconstruction reads a unit's acquisition, scans
  and declaring macros only; `processed_products` stays on the run's `other_relationships`, as a relationship.
- **The scientist sets a group's role** (`set_role`, `bundle.ROLE_DECISION`): `decide --target <group id> --decision
  set_role --value sample|reference|alignment --by "<name>"` records what the group IS over the role grouping
  proposed (a `foil` / `align` name token, a header, the engine's class). Latest wins; every derivation sets the
  group's `role` from it, with `role_basis: {rule_id: isaac.record_group.role.scientist_decision.v0, basis:
  scientist_decision, decision_id, proposed_role, proposed_basis}`: the role grouping proposed is kept beside it. A
  group whose runs all come from a decided group (identical after a regroup, or a part of a split; never a merge,
  which holds more) takes that group's role (`carried_from_group`). It moves no status. The validator refuses another
  value or target kind.
- **A 1.13.0 validator accepts 1.0.0–1.12.0 bundles;** a 1.12.0 validator refuses a 1.13.0 one (the label), and one
  holding the new rule. A 1.12.0 bundle holding such files as runs stays valid. Nothing becomes newly writable;
  `processed_outputs` is required at 1.13.0 as at 1.2.0–1.12.0.
- **The upgrade is disclosed**: the first write of an older bundle appends one `format_upgrades` entry whose
  statement includes `bundle.CHANGES_ADDED_IN["1.13.0"]` and names the runs it still holds of such averages
  ("re-import to keep them as processed outputs").

### What 1.15.0 added (the scientist's "export it anyway")

- **One new decision**, `export_despite_completeness` on a record group (`bundle.EXPORT_ANYWAY_DECISION`). Its
  `value` is `{"body_sha256", "held_by"}`: the sha256 of what the record says was measured (every `sample`, `system`
  and `context` field of its draft, `completeness.body_digest`) and why the local record-completeness gate
  (`isaac.local.record_completeness.v1`) held it.
- It is recorded only by `bundle export --allow-indistinguishable --by "<name>"`, for each record the gate holds,
  before anything is written; `bundle decide` refuses it. A later export honours it while the record body is the same,
  so a plain export no longer withdraws those records. A changed record is held again, and the export says which
  earlier records it withdrew and why.
- The validator accepts it only on a record group, with a 64-hex body and a non-empty `held_by`. A 1.14.0 validator
  refuses the new enum value, hence the version; a 1.14.0 bundle stays valid, and its first save by this build says
  so (`CHANGES_ADDED_IN["1.15.0"]`). Nothing becomes newly writable; `processed_outputs` is required as before.

### What 1.14.0 added (readings the import makes itself; every id stands)

Measured on five real beamtime folders (audit of 18 Nov 2026): a run held at a negative potential had no potential,
the technique was asked of every group with macro names as its only readings, three fields of one pellet standard
were asked of every sample, and a comment line copied from the run before was read as the run's own. The bundle's
shape is unchanged; only what the import reads changed, so only a re-import applies it.

- **A signed potential token** (`bl15.filenames.signed_potential.v1`): a leading lower-case `m` or a `-` on a
  potential token is a minus sign (`m800mV` is -0.8 V). No set-point is read from several different potential
  tokens (a range, a sweep window: `bl15.filenames.no_single_setpoint.v1`), from a pair marked `Pos` / `Neg`
  (`bl15.filenames.pulsed_levels.v1`) or from a name whose last potential word is `OCV` / `OCP`; each such token is
  kept as an unread token that says why. A value read is a candidate that needs review.
- **The technique from the instrument configuration** (`isaac.suggest.technique_from_configuration.v1`, candidate key
  `technique_from_configuration`, one beamtime-level candidate that needs review): an emission motor held on an
  emission line of the element whose edge the energy scan crosses suggests `HERFD-XAS`; an SSRL XDC run's own
  experiment file stating `EXPT_TYPE` with a schema technique suggests it. Valued only when every run that records
  something about the technique states the same one; a run held off the line blocks the value and is named, and runs
  that record nothing are counted apart and named. Where it has a value, a candidate that rests only on a macro's or a
  script's name stops targeting `system.technique` (it stays as evidence). Energies:
  `local_import/readers/xray_tables.json`, a snapshot of xraydb with its provenance.
- **Pellet-standard fields** (`isaac.import.optional_field_asked_where_mentioned.v1`):
  `sample.composition.CuO2_mass_fraction`, `sample.composition.sucrose_mass_fraction` and
  `sample.geometry.pellet_diameter_mm` are asked of a run only where its name, comment line or readings mention them.
- **A comment line left over from an earlier run** (`isaac.import.comment_possibly_stale.v1`): an SSRL XDC comment
  line identical to the line an earlier run (in acquisition order) was acquired with, while the potential the name
  writes changed, is flagged on the run (`other_relationships.anomalies[]`, kind `comment_possibly_stale`); the
  set-point and scale read from it are not offered and its candidate says why; an AI reading citing it is loaded as
  inferred, never stated.
- **Ids stand on a re-import.** Value ids are numbered by the position the earlier build gave: a slot this build newly
  fills (by a new candidate) or no longer asks (a pellet field) keeps its number, unused, so value ids may have gaps;
  a slot this build newly asks (a run whose macro-name technique reading no longer targets the technique) is numbered
  after every other. A candidate this build newly reads (a set-point from a signed token, the technique suggestion) is
  numbered after every other candidate, and its conflict after every other conflict. Every id the earlier build gave
  names what it named (measured on the six real beamtimes: 0 value, candidate or conflict ids moved).
- **A 1.14.0 validator accepts 1.0.0–1.13.0 bundles;** a 1.13.0 validator refuses a 1.14.0 one (the label).
  `format_upgrades[].statement` may be up to 3000 characters (1500 before). Nothing becomes newly writable;
  `processed_outputs` is required at 1.14.0 as at 1.2.0–1.13.0.
- **The upgrade is disclosed**: the first write of an older bundle appends one `format_upgrades` entry whose
  statement includes `bundle.CHANGES_ADDED_IN["1.14.0"]`, which names the four rules and says only a re-import
  applies them.

### What 1.16.0 added (readings the import makes itself)

The second round of the 18 Nov 2026 audit. The bundle's shape is unchanged; only what the import reads changed, so
only a re-import applies it. A value that needs interpretation is a suggestion with its evidence, confirmed with one
click; nothing scientific is filled in silently.

- **The potential an SSRL XDC run's name writes** (`isaac.suggest.name_potential.v1`, candidate key
  `potential_magnitude`): the last potential token of the name, read by the file-name token rules (a leading `m` or
  `-` is a minus sign), is a set-point candidate that needs review, as the engine already reads a SPEC name. It is
  compared with the run's comment lines: the same value confirms it (the line is shown as context); a different one
  is shown beside it and neither is offered (the comment line's candidate says the same); a line that only mentions
  a potential, with no value read from it, keeps its candidate and id but targets no field, and is evidence on the
  name's. A `Pos` / `Neg` pair is a pulsed step (no set-point); a number above 3 V is not offered. The scientists'
  rule: the potential is inferable from the experiment.
- **A merge caution that no longer fires**: since a potential in an SSRL XDC name is now a classified condition, the
  merge candidate's `nothing_classified` caution (and the `.exp DATA_FILE` agreement it carries) no longer appears for
  XDC runs named only by a potential; it still does for runs whose files classify nothing.
- **Open circuit in a name** (`isaac.suggest.name_open_circuit.v1`, candidate key `control_mode_statement`): an `OCV`
  / `OCP` token with no potential token after it suggests the control mode `open_circuit` (SSRL XDC and SPEC runs).
- **A scan title that names other scans is a processed output** (`bl15.classify.processed_scan_title.v1`): the
  engine classifies a SPEC-format file (`#F` header) whose first `#S` line is an average (`Average of 8 from A 1.1 X
  to A 8.1 X`), an arithmetic expression (`(A 3.1 X + A 1.1 X)/2`) or a normalised copy (`Norm. (A 1.1 X + ...)`)
  as `processed_spectrum`, by its content and whatever its name or folder. Beside SPEC acquisitions it is kept by the
  1.13.0 average-title origin rule, with its title as an extended-context `scan_title` statement the validator
  re-derives it from; the same test now covers a PyMca `.mca`. A file name (`_ave`, `_norm`, `removedScan`) or a
  folder (`averages/`, `Normalized/`) alone decides nothing.
- **Linked by the scans its title names** (`isaac.processed_output.link_by_title_scans.v0`, match `title_scans`, a new
  enum value): to the one run with scans whose stem the title names and which has every scan named; several files
  named gives `spans_several_runs`, none fitting `no_run_named_like_it`. A title naming no scans keeps the 1.11.0
  legacy-number rule. The validator re-runs it.
- **A macro-driven run no macro declares is not a conflict** (`isaac.import.macro_run_line.v1`): an acquisition
  whose own `#C <date>.  do <macro>.` line names a macro that ran it gets no `acquired_never_declared` conflict when no
  macro in the import declares it (the macro may have been overwritten since; that is not checked). Its candidate keeps its id, says why, and is no longer a disagreement;
  `counts.disagreements_not_conflicts` counts them, and the summary says so.
- **SPEC `#C` lines are an event log** (`isaac.import.comment_lines_are_events.v1`): two comment lines of different
  kinds, or two events (only the verbs `do <macro>` and `<motor> reset from A to B`), are not competing readings of one
  field; two different session lines (`spec User = ...`), or any other dated line (`potential set to 1.2 V`), still
  disagree. **A read-back position equal to the commanded one
  within motor resolution** (a whole spread under 1e-3 of the motor's unit: `Sx -21.2782` and `Sx -21.27825`) is one position
  (`isaac.import.position_within_motor_resolution.v1`); positions further apart (another spot) still disagree. Either
  way the candidate keeps its id and its readings as evidence and says why; no conflict and no question is made.
- **The clock zone from a SPEC `#E` / `#D` pair** (`isaac.suggest.clock_zone_from_epoch_pair.v1`): the header writes
  one instant as a UTC epoch and, on the next line, as local wall time, so their difference (rounded to 15 min) is
  the clock's offset. Where the pairs come from the same acquisition system as the start times the clock-zone question
  waits on, and every pair gives the offset the named facility's zone has on that date (daylight saving included; the
  facility from `acquisition_system.fingerprint`), that zone is the question's `suggested_value`, the pairs are its `clock_offset_pair` hints, and its text gives the one command that
  confirms it. Nothing is applied; pairs that fit no such zone suggest nothing and say why; pairs from another
  instrument (the SPEC computer's clock, beside SSRL XDC start times, the only case this build asks about) are a
  labelled hint and suggest nothing; the question id is unchanged. (The question is asked only where a run states its start in local clock time alone, an SSRL XDC run.)
- **A reference standard named as one at BL4-3** (`isaac.grouping.xdc_standard_name.v1`): an SSRL XDC run whose name
  is a mineral (`ANATASE`, `rutile`) or `elemental` before an element symbol, or a weight-percent dilution
  (`0p7wtpc`, `5wt`) or dilution matrix (`sucrose`, `sugar`, `BN`, `cellulose`) beside nothing but stoichiometric
  formulas (`0p7wtpc_Ti2O3`), proposes the role `reference`, said as judged from the name (`set_role` overrides
  it); never beside a potential, a pH, an electrolyte, a support, form or history word (`film`, `postXAS`), a
  sample's own name (`CoMOF_10wt_BN`), or a temperature, and never from a formula alone.
- **The BL4-3 absorber from the scanned range** (`isaac.suggest.absorber_from_scanned_range.v1`): a scan whose
  `Requested Energy` grid has a finest-step window with a pre-edge and a post-edge region around it names the edge of
  1 keV or more that window brackets (`readers/xray_tables.json`; of several, the one K or L3 edge, else none). One
  `experiment.element_evidence[]` entry per run whose scans name one edge (role `scanned_range`, with its `run_key`
  and the window as its literal) is a witness for that run's group's `confirm_absorber` suggestion only. Never a
  value: the answer command stays a template.
- **Ids on a re-import.** Every new candidate is numbered after every other candidate; a slot it fills keeps its
  number, unused (as at 1.14.0); a conflict no longer made keeps its number, unused. A file that is no longer a run
  takes its run's ids with it, so the run, candidate and value ids after it renumber (as at 1.11.0 and 1.13.0); a
  bundle imported before holds such files as runs until re-imported. **Some question ids then name other runs**: a
  run-scoped question id is built from its group and field, so measured on the real beamtimes 6 (PtOxidation), 42
  (PtCCorrosion) and 10 (IrOxAcid) question ids target other runs after a re-import (IrOxBase, TiON and MOF-Co: 0).
  `bundle answers import` therefore checks a row's `Record (run names)` and `File` against the runs its question
  targets now and refuses a row made for others (`problem: stale`), never applying it to them.
- **An older bundle keeps the rules it was imported with.** The widened title test and the title-link re-check apply
  only to a bundle a 1.16.0 build imported (`_imported_by_at_least`); an older bundle (1.15.0 or before) stays valid and keeps taking
  decisions, and its first save names the runs a re-import would keep as processed outputs
  (`processed_title_runs`: "re-import to keep them as processed outputs").
- **A 1.16.0 validator accepts 1.0.0–1.15.0 bundles;** a 1.15.0 validator refuses a 1.16.0 one (the label and the new enum values). Nothing
  becomes newly writable; `processed_outputs` is required at 1.16.0 as at 1.2.0–1.15.0.
- **The upgrade is disclosed**: the first write of an older bundle appends one `format_upgrades` entry whose
  statement includes `bundle.CHANGES_ADDED_IN["1.16.0"]`.

### What 1.17.0 added (consent kept; a read writes nothing)

C4 and C7 of the 22 Nov 2026 plan; skill audit of 18 Nov 2026, findings 10, 13 and 15.

- **One optional section, `consents[]`** (`$defs/consent`). Each entry: `consent_id` (`consent-NNNN`), `answer`
  (`given` or `withdrawn`), `scope` (the constant `claude_reads_files`: Claude may read the imported folder's files and
  every command output on this bundle, flow B of the skill's `data-flow-and-consent.md`), `agreement` (the constant
  `ISAAC usage agreement`), `given_by` (the name, `self_reported_local_user`, `local_unverified`: a claim, never an
  identity), `folder` (the imported folder's name), `recorded_utc`, `command`, optional `note`. Append-only; the LATEST
  entry holds (`bundle.current_consent`), so a withdrawal never erases the consent before it.
- **Recorded only by `isaac bundle consent <dir> --by "<name>" [--withdraw] [--note ...]`**
  (`mutations.record_consent`). The same answer under the same name as the entry that holds records nothing and writes
  nothing.
- **`isaac bundle status <dir> [--json]`** (`status.py`) says in about seven plain lines where an import stands: the
  folder and format (an upgrade pending is said, not made), the scientist and the consent, runs and live record groups,
  records exportable at the last `bundle validate`, open questions (blocking, disagreements affecting a record,
  optional), the last processing, and the one thing to do next. It reads only and prints no parser value.
- **A command that only reads never writes `bundle.json`** (`list`, `show`, `questions`, `check`, `status`,
  `crosscheck-plan`, `excerpt`, `reveal`, `check-readings`, `propose-terms`, `site export`, `template export`, and the
  Local Imports page's progress and questions routes). The parser values it prints are still recorded first (§11), in
  `exposures.pending.jsonl` beside it (`mutations.record_exposures`), read back by every load and folded into
  `exposures[]` by the next write, which then removes the file. So two readers never trip "The bundle changed since it
  was read", and an older bundle is upgraded by the next write, never by a look. A line of another `bundle_id` (a
  folder re-imported since), or naming a target the bundle no longer holds, is never folded in; an unreadable line is
  refused, not skipped.
- **`bundle list <dir> processing-results`** lists only the results of live record groups; the results of a group that
  no longer exists or is merged, rejected or split are counted in `not_listed` (`group_no_longer_live`) and listed with
  `--all`.
- **`format_upgrades[].statement` may be up to 4000 characters** (3000 before): the statement of an older bundle's
  upgrade appends each later version's note, and a 1.7.0 bundle's passed 3000 with this one.
- **A 1.17.0 validator accepts 1.0.0–1.16.0 bundles;** a 1.16.0 validator refuses a 1.17.0 one (the label, the
  section when present, and a longer statement). Nothing becomes newly writable; `processed_outputs` is required at 1.17.0 as at 1.2.0–1.16.0.
  An older build that writes a bundle with a pending exposures file ignores the file; this build folds it in later.
- **The upgrade is disclosed**: the first write of an older bundle appends one `format_upgrades` entry whose
  statement includes `bundle.CHANGES_ADDED_IN["1.17.0"]`.

### What 1.18.0 added (fill first, review at the end — DEC-96)

The project owner's decision of 2026-11-25 (`docs/fill-first-design-2026-11-25.md`): do not ask
what the evidence already answers; fill it, and the scientist reviews the final records at the end.
Slice 1 of that design. **This changes the state derivation and the eligibility rule, which §9's
rules above call a major change;** it is labelled a minor version, 1.18.0, by the design's own
decision, and the stale path below is what keeps every older bundle readable rather than refused.

- **One new value state, `filled`** (`bundle.STATE_FILLED`; the schema's `value_state` enum, never
  `extracted_state`), and one optional block on candidates and missing values, `fill`
  (`{rule_id, value}`, `$defs/fill`; `rule_id` one of `bundle.FILL_RULES`). Derived on every
  write; the validator re-derives both and refuses a stored `filled` or `fill` no rule gives.
- **Three registered rules** (each an id and one sentence, `bundle.FILL_RULES`). The two candidate
  rules share every exclusion (`bundle._fill_exclusions_pass`):
  - `isaac.fill.parser_exact.v1` — STRICTLY a reading: a `candidate_extracted` value with
    determinism `deterministic` and no INFERENCE step (`bundle._inferred_derive_rule_ids`): a
    `derive` step counts as inference when its rule is not the same witness's own reading rule, or is
    a registered convention (`STORED_CONVENTION_RULES`). A reader mapping its own term to the
    vocabulary — DEC-71's logbook lexicon, identified by its rule ids (`bundle._logbook_rule_ids`),
    which writes a normalize step and then a derive step under ONE rule (a logbook flow-cell statement →
    `flow_cell`) — is reading and is filled. Also this build's own instrument-configuration
    technique rule (1.14.0, `isaac.suggest.technique_from_configuration.v1`, valued only when every
    run agrees).
  - `isaac.fill.stored_convention.v1` — a value one of the engine's REVIEWED stored conventions
    derived (`bundle.STORED_CONVENTION_RULES`, an explicit allowlist): today only
    `bl15.environment.dry_sample_is_ex_situ.v1` (DEC-70: a measurement whose own name says `dry`,
    or `NoElectrolyte` — read as the medium `none` by the file-name reader, no second rule — is
    `ex_situ`). The candidate's own rule must be that convention and every `derive` step must name
    it; the draft's derivation entry names both the fill rule and the convention
    (`convention_rule`). **Not on the list:** DEC-71's logbook lexicon (`bl15.notes.*_statement.v1`),
    which is not an inference convention: its term mapping is reading, filled under `parser_exact`
    above, with every DEC-71 safeguard in force (a negated, hedged, ambiguous or passing sentence, or a
    beamtime-wide one, gives no value or is held).
  - **The shared exclusions — never:** a value a convention or standing resolution from ANOTHER
    beamtime gave (`review_status: resolved`, `resolved_by_rule`, `standing_resolution`);
    `context.electrochemistry.potential_scale` or `control_mode` (`bundle.PARSER_EXACT_NEVER_FILLS`:
    `control_mode_by_run`, which the questions read, counts only confirmed modes); a local clock
    time; a beamtime value of a run-only field (DEC-69); a field the sources disagree about for
    that run (a conflicting candidate, or a conflict naming it); **any other reading of the same
    field for the same run (or the beamtime) whose value differs or is none, unless a scientist
    rejected it** (`bundle._other_reading_dissents`: every SPEC run holds
    an #E epoch start beside an #D local start with no value until a zone is stated, so the epoch is
    not filled while the #D reading is open; the design's "one dissenting witness means no fill");
    a value read from a file-name number by its POSITION before the naming is settled (below); a
    held value (beamtime-wide notes, a cell named in passing); a `contradicts` witness; a value its
    field refuses; or a value an AI reading disagrees with.
  - `isaac.fill.domain_from_acquisition.v1` — `system.domain = "experimental"` when every run's
    acquisition was read by a beamline acquisition READER (`bundle.ACQUISITION_READER_IDS`: SPEC,
    SSRL XDC, XDI, MCA, XES table; a reference pellet or an alignment scan the SPEC reader read
    counts — measured on a real BL15-2 beamtime; the headerless two-column reader does not) and no
    source is classified as a calculation output (`bundle.CALCULATION_OUTPUT_SOURCE_TYPES`, empty
    today: the classifier has no such class). A candidate stating another domain, or a disagreeing
    AI reading, blocks it. The draft cites, for the group's own measured runs, a literal header line
    each run's reader read (real locator, reader id), and says in a `note` which readers read them.
- **File-name readings and the naming question.** The file-name reader recognises every token by
  its shape or word wherever it sits (`dry`, `NoElectrolyte`, `100mV`), and its ONE ordering rule is
  the bare-integer ordinal (`bl15.filenames.bare_integer_ordinal.v1`: the first bare number the
  legacy number, the second the sample/electrode number;
  `bundle.POSITION_DEPENDENT_NAME_RULES`). Only a value read under that rule waits for the naming:
  it is filled once `bundle.naming_check` says `decided` (a `set_counter_positions` /
  `set_not_counter_positions` decision, nothing open) or `grouped_no_counter_question` (the grouping
  step ran, `grouping_questions` is stored, and it asks no counter question); at `not_grouped` (a
  fresh import) and `counter_question_open` it is not. Eligibility therefore moves blocked → filled
  as the workflow advances (import, `bundle group`, the counter answer). `bundle status` shows the
  outcome (`facts.naming`). **The same wait applies to a logbook reading bound to its run only through
  the name's sample number** (`bundle._bound_by_name_number`): a sample section that lists no file
  numbers (its reading has a `section`, an integer `sample_number` and no `file_numbers`; it reaches
  the runs whose name's second bare integer is that number), or a beamtime sentence naming samples
  (`named_samples`, mapped by the same token). **A section that lists file numbers is not gated:**
  it binds through the run's legacy number, a literal agreement of the logbook's File Number column
  with the number the name leads with, and no counter decision changes which number that is
  (`runs[].legacy_number` is read once at import; a counter answer is read only by grouping).
- **A decision always wins.** Any decision on the target, a `defer` included, means no fill: a
  `correct` or `confirm` makes it `scientist_confirmed`, a `reject` `rejected`, a `defer` leaves the
  parser's state (asked again). In a record group, BEFORE the disagreement check, a filled value is
  dropped wherever a scientist confirmed the same field for the same run (a beamtime-wide fill
  beside any confirmed value of the field), and a run-level fill is dropped for a run holding ANY
  decision on its own targets for the field, a defer included (`records.FILL_BEATEN_BY_DECISION`).
- **A beamtime-wide fill is scoped per run.** A run's own decision on the field (a defer on its
  answer slot included; a `reject` of a reading is no statement about the value), or a run's own
  undecided reading that is open or differs, stops a beamtime-wide fill for THAT run only
  (`bundle.fill_run_blocks`, `bundle.runs_a_fill_cannot_reach`): the groups without such a run
  compose the fill; a group holding one composes nothing for the field and is asked (its run's own
  reading, or its slot). A scientist REJECTING a run's own missing value (or reading) does not stop
  a beamtime-wide fill reaching that run: a reject means "no statement here", not "this value is
  wrong for this run". Measured on a real BL15-2 replay: the instrument-configuration technique
  (90 of 90 recording runs) beside one reference pellet whose name says `transmission`. A
  beamtime-wide answer SLOT is dead only under a scientist's beamtime-wide answer, never under a
  fill, so a slot deferred under a fill stays asked.
- **Composition.** A filled value composes as `inferred` with a derivation entry naming its rule;
  only when every measured run of the group has the same filled or confirmed value; a disagreement
  is worded by state (confirmed, filled, or one of each). **Asked when the group cannot take it:**
  a fill whose group's runs were filled with different values, or not every run has one
  (`questions.group_unusable_fills`, mirroring the composer step by step), is asked like the value it
  was read as, an optional field included; for a beamtime-wide fill a run does not take, that run's
  own targets are asked, not the fill.
- **Not asked, still addressable.** `questions.consolidate` asks no filled value and none is
  blocking (except the ones above), and a fill counts where an answer does in the conflict cover and
  the sample family. With `include_answered` a filled
  target is back in the question that would ask it, under the same id, so `decide --question`,
  `bundle answers import` (a workbook row) and `bundle site import` (a card exported before the fill)
  record a correction, and it wins. A site card is recorded so only when EVERY target of the
  question it covers is filled (`question_site_import._Ctx.filled_cover`); a card over a filled
  target and one a scientist answered since is reported as answered since, never written over the
  newer answer. Answer memory never learns a fill (it reads decisions only).
- **Counts.** `counts.filled` counts candidates AND missing values a rule filled (unlike the other
  state counts, which count candidates only), present at 1.18.0+; `readiness.eligible_value_count`
  counts filled values; `bundle check` lists `filled` among the candidate states and prints
  `counts.filled`; `bundle status` counts the filled values NO question asks (`counts.filled` less
  `questions.fills_asked`), so it agrees with the questions; the Local Imports page's counts carry
  `filled`.
- **The fill rule set** (`fill_rule_set`, optional, written by every write of a bundle this build
  fills; `bundle.FILL_RULE_SET`, raised whenever a rule is added or any exclusion changes). A 1.18.0+
  bundle an earlier rule set wrote (or with none recorded) whose stored fills disagree with this
  build's is STALE, not INVALID (`bundle.fill_rule_set_stale`); its next write re-derives it and logs
  each value whose fill moved (either way) in `eligibility_rederived`, with no `format_upgrades`
  entry (the format did not change). A NEWER rule set than this build's is refused as a newer
  format is (`validate` errors `format: fill_rule_set N is newer…`; a write is refused, never
  rewritten).
- **An older bundle is STALE, not INVALID.** A 1.2.0–1.17.0 bundle (one the next save labels
  1.18.0: it holds `processed_outputs`, `bundle.fills_apply`) is derived with fills, so its stored
  states disagree; `bundle.stale_eligibility` lists each value a rule now fills (reason naming the
  rule), `check` prints `STALE:`, `validate` / `export` refuse it with the remedy, and the next
  write raises it to 1.18.0, appends one `format_upgrades` entry (with
  `bundle.CHANGES_ADDED_IN["1.18.0"]`) and logs every filled value in `eligibility_rederived`
  (`value_state: filled`, eligible false → true), as 1.3.0 did. A 1.0.0/1.1.0 bundle without
  `processed_outputs` keeps its label on a save and is never filled.
- **`format_upgrades[].statement` may be up to 6000 characters** (4000 before): an older bundle's
  statement appends every later version's note, and with the run lists of 1.11.0–1.16.0 it passed
  4000 once 1.18.0's note was added.
- **A fill rests on hand-editable inputs.** The candidates, evidence and decisions a fill is derived
  from live in `bundle.json` like everything else, so an edit to them moves the fill on the next
  derivation; the validator re-derives every fill from what the bundle holds, which proves the fill
  follows its rule, not that the inputs are what the import read (the same trust every derived state
  here has).
- **Known pre-existing behaviour, unchanged:** CONFIRMED values compose into a merged group with
  partial coverage (one run confirmed, another with nothing for the field) as they did before
  1.18.0; only a fill must cover every measured run.
- **Known gap:** a field a rule filled for some runs of a group and that is optional is asked only
  through `group_unusable_fills`; a fill that no group holds (a run outside every live group) is
  neither composed nor asked, as an extracted value was before.
- **Not in this slice:** the reading fills (slice 2, 1.19.0,
  below), the folder and people fills, the end review (`bundle review`), and SKILL.md (slices 3–4 of
  the design).

### What 1.19.0 added (fills from checked, stated readings — DEC-97, slice 2 of DEC-96)

Slice 2 of `docs/fill-first-design-2026-11-25.md` (review findings 3, 6 and 9). The format moves because
fields join `ai_interpretation` and `fill`, and a 1.18.0 validator refuses them (`additionalProperties: false`)
as well as the new rule id; a rule set alone would not have needed one.

**Revised the same day after a real-beamtime replay (outside the repository) and an independent review.** The
first version, replayed on a real BL15-2 beamtime, filled 21 values right and 62 wrong: 49 `sample.material.name`
values were the sample's own code (the quote, a sample heading, names the sample, not its material), and 13
`context.environment` values were an inference from two quotes that state no environment. So: an inferred
reading never fills; a stated one fills only when its quote itself states the value; a sample's own label is never
its material; and a beamtime finding is held to every sample and every target it reaches (below).

- **A reading keeps its quote check** (design item 6). `bundle annotate --from-readings <file> --root
  <folder> --apply` already held every quote against its cited file (`reading_check`, §9 "What 1.12.0
  added"); it now stores the result on each interpretation it writes, as `quote_check`:
  - `result` (`pass`; `fail` is allowed and never fills), `checker` (`isaac.reading_check.v1`,
    `bundle.QUOTE_CHECKER_ID`);
  - `reading_pass_id` — one per `--apply` call: `rp-` and 32 hex digits of the sha256 of the model id, a
    newline and `findings_sha256` (`bundle.reading_pass_id_of`). **Deterministic, by choice:** anyone with
    the findings file and the model id can recompute it and tie a fill to the pass that made it, it needs
    no clock or random number, and loading the same file again records nothing new and names the same pass.
    The validator recomputes it from the reading's `model.model_id` and `findings_sha256`;
  - `findings_sha256` — the findings AS PARSED in canonical JSON (keys sorted, no whitespace, UTF-8), so a
    re-indented file is the same pass and any changed finding is another;
  - `quote_sha256` — the sha256 of the quote the reading keeps (the quote that was checked);
  - `reading_sha256` — the sha256 of the reading as it was checked (`bundle.reading_sha256`,
    `bundle.READING_SHA_FIELDS`): its target, `proposed_value`, `strength`, `scope`, `field_path`,
    `finding_field_path`, `run_ids`, `source_refs`, `excerpt_locator`, `source_path` and `quote`, and each
    checked file's path, source id, `content_sha256` and lines. The validator recomputes it, so a value
    edited by hand, a strength flipped, or a block copied onto another target is refused. **It catches an edit
    or a copy, not someone who deliberately recomputes the hashes:** a bundle is a local file and nothing in it
    is signed;
  - `files` — the file the quote was found in: `path` (as the folder spells it), `source_id` (`null` for a
    file the import did not read), `content_sha256` (the bytes at the check), `lines` (`[first, last]` of a
    plain-text quote, `reading_check.quote_lines`) and `at` (the check's own words, not hashed).

  The CLI report (`bundle check-readings`, the preview's `quote_check`) prints neither `content_sha256` nor
  `lines`. `annotate --target`, and this package's synthetic `check_quotes=False` path, store no block.
  A reading an earlier build recorded without the block is not "already recorded" when the same findings
  are loaded again with the check: the checked reading is recorded beside it (the log is append-only), and
  only that one can fill. The quote is part of a reading's identity on a re-apply, so a corrected quote is
  recorded (review M5). A findings file holding `NaN` or `Infinity` is refused, never a traceback (review M1).
- **A reading keeps its scope**: `scope` (`experiment` or `runs`, as the finding's `applies_to` said), part
  of a reading's identity on a re-apply. A finding offered unsplit on several fields (the electrolyte as a
  whole, on its name and concentration, §20) keeps `finding_field_path` and never fills: splitting it is the
  scientist's step.
- **The validator ties the block to the bundle and to the reading.** The schema checks its shape;
  `bundle.quote_check_errors` refuses a block whose `quote_sha256`, `reading_sha256` or `reading_pass_id` does
  not match, or which names a source id whose path or `sources[].content_sha256` differs (stale or forged), or
  which names a source's path with no source id. A failed check, or a file the import did not read, is not an
  error: it never fills (`bundle.reading_quote_problem`, which a fill re-checks itself).
- **`isaac.fill.reading_stated.v1`** — THE ONE reading rule (`bundle.reading_fill_for`). It fills the candidate or
  missing value a reading targets when ALL hold:
  - the reading's strength is `stated`, and its stored check holds (above);
  - **its quote itself states the value** (the lexical tie, `reading_tie.tie_problem`, checked against the quote AS
    STORED, possibly truncated at 300 characters, review M3): a NUMBER appears in the quote WITH ONE OF ITS FIELD'S OWN
    UNITS or a unit a declared conversion takes (`reading_tie.FIELD_UNITS`: the potential in V, or mV converted; the
    current density in mA/cm², or µA/cm² converted; the concentration in M or mol/L, or mM converted; the temperature
    in K, or °C converted — `°C`, `degC`, or a bare `C` not followed by "rate"; the pH right after its own word). A
    number carrying any other unit never ties, nor one followed by a rate word right after its unit, a two-word unit
    included (`0.1 mV/s`, `100 mV s-1`, `100 mV s^{-1}`, `100 mV sec-1`, `100 mV per second`, `10 mA cm-2 s-1`: scan
    rates and ramps are no set-point or current density; `0.1 M` is no temperature; `1 C rate`, a charge rate, is no temperature), nor a number inside a heading or
    an identifier (`Sample 1`, `scan 5`, `01_01`); the pH ties only a number written right after the word pH (`pH 13`,
    `pH = 13`, `pH of 13`, `pH13`), never a bare count (`2 electrodes`, `500 cycles`); a numeric field `FIELD_UNITS`
    does not list never ties; so "room temperature" never fills a temperature. A LIST member's own words (`in_situ` as `in situ` / `in-situ`) or a
    registered synonym (`reading_tie.MEMBER_SYNONYMS`, explicit and small, each pinned by a test) appear as whole words,
    in a SENTENCE holding no negation (`not`, `never`, `no`, `without`, `n't`, `neither`, `nor`, `cannot`, `unable`,
    `impossible`, `instead`, `rather`, `failed`, `absent`, `unavailable`, `lacking`) before or after them (sentences end
    at `;`, a full stop that is not a decimal point, and a blank line — never a single line end, so a wrapped logbook
    line "in situ was planned / but not done" is one sentence and is asked; "measured ex situ instead of in situ" and
    "we were unable to measure in situ" are asked too: "an in situ measurement was not
    possible", "the cell was never, at any point, operated in situ" and "In situ: not possible" do not tie `in_situ`;
    "in situ, not ex situ" is asked rather than filled, the safe direction); every SIGNIFICANT WORD of FREE TEXT (letters and digits, 3 or more characters, any case, a short
    stopword list left out) is a word of the quote; any other kind of value never ties;
  - the value passes `value_problem` for the field, and is no value any fill rule refuses
    (`bundle.fill_value_problem`): **a sample's own LABEL is never its material** — a `sample.material.*` value equal,
    without case or punctuation, to the run's file-name sample token, its `sample_id` or `group_token`, a logbook
    sample heading's code (`Sample 3 ZZ9 in base (SYNTHETIC)` → `ZZ9`), or a heading code in the reading's own quote — or one ANY of
    whose words is such a label (`ZZ1 film`: a sample named after its material is then asked, which is acceptable), or
    whose run-together text holds a label of 3 or more characters with a letter (`ZZ 1 film`); and
    **an
    electrolyte name carrying a concentration (a number followed by M, mM or mol/L) or a pH** never fills (review
    M2). Both apply to `parser_exact` as well;
  - every AI reading of the target (checked or not) states the same value; no other reading of the field for the
    run (or the beamtime) is open or differs (slice 1's dissent rule, `bundle._field_dissents`), and no AI reading of
    another target of the field for the run (or the beamtime) differs; the sources do not disagree about the field;
  - and the slice 1 exclusions: never the potential scale or the control mode, never a time (`*_utc`: a time is on
    its clock, whose zone is the scientist's), and on a candidate never a convention of another beamtime, a held
    value, a local clock time, a contradicting or passing witness, a value a conflict names, a position-read name
    number before the naming is settled, or against the candidate's own file value. A missing value whose run holds
    a candidate of the same field is left to that candidate (never two fills).
- **An INFERRED reading never fills** (DEC-97, revised): an inference from indirect quotes is a judgment, so the
  scientist is asked; the reading stays a suggestion shown with the question. (The first version's
  `isaac.fill.reading_inferred.v1`, two independent agreeing witnesses, filled 13 wrong environments on the replay
  and is removed: no rule id, no dead code.)
- **DEC-69 for readings, the samples, and the naming gate** (design item 3, reviews I2–I4,
  `bundle.reading_scope_problem`, `bundle.reading_run_level`). A reading scoped to the whole beamtime never fills a
  run-level field — `records.RUN_ONLY_PATHS` (environment, reaction, cell type), the composer's `context.reaction.name`
  and every `context.reaction.*` field, the run's measurement conditions (the potential and current set-points, the
  potential scale, the control mode) — **nor any `sample.*` field**: a beamtime statement about one sample must not
  fill every sample. The one exception: a beamtime with exactly ONE sample (every measurement run has the same
  `sample_id` and the same file-name sample token, and — since `sample_id` comes from the file name — the logbook's
  sample headings give at most one sample code, `bundle._one_sample`), where a statement about the beamtime's
  sample is one about every run's. No reading fills a beamtime-level target of a run-level field. **One dissenting
  target stops the whole finding** (review I4, `bundle._dissented_findings`): a beamtime finding one of whose targets
  disagrees — a scientist's other answer or a reject (a defer is no statement), an AI reading, the target's own file
  value, another reading of the field for its run, or the sources disagreeing — fills NONE of its targets. Readings
  only; slice 1's per-run scoping of a file value's beamtime fill is unchanged. A reading scoped to the runs it names
  reaches only those runs' own targets. **A reading reaches a run by the run's name** (`applies_to.runs`: a stem or
  run id), so one whose quote is in a file that is not the run's own (a logbook, a readme) rests on the reader's
  matching of a statement to run names — the position-dependent binding slice 1 gates (`_bound_by_name_number`): it
  fills only once `naming_check` is `decided` or `grouped_no_counter_question`. A quote in the run's own acquisition
  or scan file is not gated. A reading with no `scope` (written before 1.19.0) never fills.
- **What a fill attaches to.** A reading's target is a candidate or a missing value (`readings_to_interpretations`:
  every live run's value of the field for `experiment`, the named runs' for `runs`); that target is what is
  filled. A record-group reading (the absorber, which has no record field) and a run, source or
  processing-result reading never fill. A group reaches its runs through their own targets, and the 1.18.0
  coverage rule holds: a group composes a fill only when every measured run has the same filled or confirmed
  value.
- **The file-name sample token in slice 1** (checked for the replay's 49): the file-name reader's sample token is a
  `sample.material.name` candidate with NO value, held for the scientist (`needs_review`: the engine says only the
  scientist knows whether the token is a material or an electrode label), so `parser_exact` never filled it; its
  literal is shown as a hint (`file_literal`, `carries_value: false`), never offered as the value. The 49 came from
  readings targeting that valueless candidate; the label rule now refuses them, and a label-valued candidate from any
  reader.
- **Precedence, unchanged:** any decision, a defer included, beats a fill. A FILE rule comes first: a checked
  stated reading that ties and agrees with a `parser_exact`, `stored_convention` or `domain_from_acquisition` fill is
  listed on that fill (`fill.readings`, `fill.reading_pass_ids`) under the file rule's id — one fill — and a reading
  that disagrees blocks it (no fill at all).
- **The `fill` block** may carry `readings` (the interpretation ids, sorted, at most 50) and `reading_pass_ids`.
  The composer (`records.reading_witnesses`) adds one witness per reading: `source_type: document`, the file,
  locator and verbatim quote, `method: ai_interpretation` with the model id, `relation: supports`, the
  interpretation id, strength, reading pass and the checked `content_sha256`; and the derivation entry
  `{"source_type": "derivation", "rule": "isaac.fill.reading_stated.v1", …, "readings", "reading_pass_ids"}`.
  `draft_validator` reads the witness as observed evidence and the entry as the stated rule (unchanged).
- **A run's own differing AI reading stops a beamtime-wide fill for that run** (`bundle.fill_run_blocks` rows
  `("reading", target id, value, its target's decision)`), as a run's own differing file reading did since
  1.18.0; the composer and `questions.group_unusable_fills` read the same rows.
- **Fill rule set 2** (`bundle.FILL_RULE_SET`). A 1.18.0 bundle (rule set 1) whose re-derived fills differ is
  STALE, never INVALID, and its next write raises it to 1.19.0 and logs each moved value in
  `eligibility_rederived`; one with nothing moved is valid and raised the same way. A newer rule set is still
  refused. `ai_interpretations[].max_state` stays the constant `needs_review` it always was (an append-only
  field): it names what a reading ALONE gives; a fill is a registered rule's, named in `fill.rule_id`.
- **Answer memory never learns a reading fill** (it reads decisions only); a correction by `decide`, a workbook
  row or a site card is recorded and wins, as for every fill.
- **A question says which filled values it leaves out** (every fill rule, `questions.left_out_filled_text`): a
  question some of whose targets a rule filled leaves them out (questions skip filled values) and its text ends
  "Left out, because a rule filled the value from the evidence: N value(s), for <runs>; to change one, `isaac bundle
  decide <bundle_dir> --target <id> …`, or change it in the end review", with `left_out_as_filled`
  (`[{run_id, target_id}]`). Answering the question (`decide --question`, a workbook row, a site card) answers the
  runs it asks and leaves the filled run filled; `decide --target <the filled target>` corrects that one. A site card
  lists, first among its context, the filled measurements of its own sample it does not cover, with each value.
  Question ids are unchanged (the left-out targets were never part of the open question).
- **Not in this slice:** the folder and people fills, the end review and SKILL.md (slices 3–4).

### What 1.20.0 added (the folder, the people and the held potential — DEC-98, slice 3 of DEC-96)

Slice 3 of `docs/fill-first-design-2026-11-25.md`. The format moves because four rule ids join `fill.rule_id`, one
experiment decision joins `scientist_decisions[].decision` (`set_environment_convention`), and the import keeps a new
optional field; a 1.19.0 validator refuses all three. Fill rule set 3.

All four are rules of MISSING values, tried after the file rules of candidates and before the reading rule
(`bundle.folder_fill_for`). A candidate of the field for the run (or the beamtime) leaves the missing value to it,
whatever its value (never two fills); any decision on the target, a defer included, beats the fill; a checked stated
reading that agrees is listed on the fill, one that disagrees blocks it. Every value is re-derived on each write and
by the validator, and its witnesses are re-derived when the draft is composed (`bundle.folder_fill_witnesses`, from id
indexes and a run-to-fingerprint-line map built once per fill context), never stored.

- **`isaac.fill.environment_from_held_potential.v1` — a per-beamtime convention, answered ONCE.** Why a question and
  not a fixed value: the beamline scientist answered `operando` for every potential-held run of one real beamtime,
  set-points below the reaction onset included, while another real beamtime's own filled metadata sheet calls the same
  class of runs `in situ`. Which word a beamtime uses is the scientist's convention; a fixed rule would write a wrong
  value on every run of a beamtime that uses the other one. So:
  - **A run qualifies** (`bundle.environment_basis`) when ALL hold:
    - **its own files give a set-point**: a run-scoped `context.electrochemistry.potential_setpoint_V` candidate with a
      finite value, determinism `deterministic`, every file witness a `deterministic_parser` one (a file-name token
      such as `100mV`, or a header or macro line), its sources agreeing, not conflicting, not held, no conflict naming
      it, no `contradicts` witness, no other reading of the set-point for the run open or differing, no AI reading of
      it disagreeing, and no scientist rejecting it (a confirm or correct leaves it a set-point). **The potential scale
      plays no part** and is not required; DEC-88's gate on the set-point itself composing is unchanged;
    - **something shows it was electrochemical** (`bundle._held_potential_facts`): for the run or the whole beamtime, a
      candidate no scientist rejected, a scientist's answer, or a checked stated reading, with a VALUE at the
      electrolyte name or concentration, the pH, the cell type, the reaction or the control mode (never a value that
      states nothing, such as `not_reported`, nor one saying there was no electrolyte); or a reading of any field,
      of ANY strength, whose quote passed the quote check and has a sentence naming chronoamperometry,
      chronopotentiometry or a potentiostat with no negation in it — corroboration is the checked quote's own words
      (the experiment was electrochemical), never the reading's value, so an inferred reading counts this way and only
      this way. Round 4 (`bundle._quote_corroboration`): such a quote corroborates only when the matched sentence holds
      no word of a plan or an intent (`planned`, `will`, `would`, `should`, `intended`, `could`, `unable`, `may`, …;
      round 5: `May` beside a day or a year is a date, and `next` counts only in "next beamtime / time / week /
      visit"), and the clause that names the control is not conditional (round 5: the sentence is cut at commas and
      "then", and only an `if` / `unless` in the control's own clause, or a sentence that opens with one and has no
      "then", stops it: "if it drifted it was reset, then chronoamperometry continued" corroborates); the quote holds
      no word saying something was dry, ex situ or without electrolyte (anywhere; `dry` right before a purge gas or
      a box — `dry N2`, `dry Ar`, `dry box` — is no dry sample), nor as-is, nor open circuit (`OCV`, `OCP`), anywhere,
      except an open-circuit step tied to the control that FOLLOWS it in the same sentence ("OCV for 5 min, then
      chronoamperometry at 1.4 V", "chronoamperometry after OCV"; "chronoamperometry, then measured at OCV" still
      stops it — kept quote-wide, not only in the matched sentence, so an OCV said of a sample elsewhere in the quote
      never becomes operando); and the reading's own value says none of those (an environment reading proposing
      `ex_situ` never corroborates). A quote that names a sample — `sample <code>` with a CASE-SENSITIVE code (a
      digit, or two or more capitals: "samples were measured" names none), a `Sample <n> <code>` heading, or a run's
      own sample label (slice 2's `sample_labels`) — corroborates only the runs carrying that label, none when no run
      does (an unknown code names another sample: "for sample ZZ9 only"); a quote naming no sample corroborates the
      reading's own scope. Round 6: the samples are read only from the CONTROL'S OWN CLAUSE (the matched sentence cut
      at `,`, `;` and "then"); a sample named anywhere else in the quote ("ZZ1 held at OCV, then chronoamperometry on
      ZZ2", "…; ZZ1 was kept in the dry box") means the quote speaks of several samples in several states, and it
      corroborates nothing. The leading-"if" test sets aside a leading `<word>:` or date prefix ("Note: if it held,
      chronoamperometry …" is a condition). A file name's `acid` / `base` is NOT corroboration: the reader gives it no value;
    - **it is a sample measurement a record is built from**: not `standard_or_reference` or `alignment`,
      `grouping.run_role` says `sample`, no live record group holding it has another role, `run_candidate` is true and
      it is not kept only as context (the question and the fill reach exactly the same runs). The groups' status and role are now derived before the fills
      in `apply_derivations`, so a `set_role` or a reject of a group is read in the same derivation (before, a reject
      after `set_role reference` was refused as INVALID);
    - **nothing blocks it**: no environment word in the run's own name (split at `_`, `-`, spaces and dots: `insitu`,
      `exsitu`, `ex-situ`, `in situ`, `operando`, `postmortem`, `air`, `ambient`, `pristine`, `vacuum`, open circuit
      `OCV` / `OCP` / `atOCV` / `OCV-1`, `dry` / `dried`, `NoElectrolyte`, `asIs` / `as is`, each with digits after it
      too (`insitu1`, `dry2`); `exs` is not on the list, because it could not be checked against real run names; never `after`, since a
      potential-held run is named `after500Cycling_100mV`); nothing — a candidate, an answer or a reading of any
      strength, of the run or of the beamtime — saying open circuit or no electrolyte (`none`, `None (dry)`, `dry`,
      `no electrolyte`, `without`, `not used`, `n/a`, a concentration of zero): such a value blocks and never
      corroborates; no STATED reading of its environment (such a run is asked on its own, never covered by the
      question); no candidate of the
      environment for the run or the beamtime (the dry convention's `ex_situ`, a logbook term, a sheet value); and the
      sources not disagreeing about the environment.
  - **The question** (`questions.ENV_CONVENTION_KIND`, `environment_convention`; its id `ENV_CONVENTION_QUESTION_ID`,
    from its scope, kind and field only): asked once, at experiment scope and blocking, while at least one qualifying
    run has an undecided environment and no convention is recorded: "N measurements were taken in electrolyte while
    the cell was held at a potential (for example <two or three run names at their set-points>). Is their measurement
    environment operando or in situ?" Its answers are `operando`, `in_situ` and `per_run` (it differs by
    measurement). Its hints are the runs' own set-point tokens and the corroborating quotes or answers; an INFERRED
    reading of those runs' environment is shown only as "an earlier reading suggested …", never as the answer.
    `covers_value_ids` names the runs it reaches, and `earlier_reading_runs` the runs an inferred reading suggested an
    environment for.
  - **While it is open, each run's own environment question it reaches is covered**: a question all of whose targets
    it reaches is no longer blocking and names it in `covered_by` (its id unchanged); one that also asks other runs
    keeps only those (`covered_by_convention` lists the ones it leaves out). So the blocking list shows one question,
    not one per run.
  - **The answer** — `decide --question <its id> --decision set_environment_convention --value operando|in_situ|per_run`,
    or `decide --target experiment` with the same decision; a value off that list is refused by `decide` and by the
    validator. Latest wins. **The answer is bound to the runs it was asked about:** the decision keeps their
    environment value ids (`environment_convention_covers`). When later evidence (a reading, a regroup) brings more
    runs under it, they are filled too — one answer for the beamtime, every fill reviewed at the end — but never
    silently: the fill's derivation note says the run qualified after the answer, `bundle status` says "N more
    measurement(s) now take it" (`facts.environment_convention.more_since_the_answer`), and the question re-opens,
    OPTIONAL, under its own id ("N more measurements now take your answer"), with `extends_to_value_ids`. The question
    site has no card for the re-opened question; the status line gives the `decide --question <id>` command. Answering
    it again with the same value records a new decision covering them (it is never "nothing new") and closes it.
    `operando` / `in_situ`: every qualifying run is filled with that value under the rule
    (`bundle.environment_fill_basis`), except a run whose STATED reading of its environment (checked or not) gives
    another value, which stays asked; an INFERRED reading that differs no longer blocks, since the scientist settled
    the convention. `per_run`: nothing is filled, and each run's environment question is asked again, under its id.
  - **The draft** cites the set-point's file witnesses, the corroboration (each candidate's file witness, each reading's
    quote, each answer) and the convention answer itself (a `user_confirmation`), and the derivation's `note` says what
    it rests on. Answer memory never learns the convention (it reads value decisions only), so it is never suggested
    as a run's answer on another beamtime.
  - **The question site** asks it on one beamtime card (`question_site.ENV_CONVENTION_TARGET_ID`), with the three
    answers, the runs it covers (named in its detail, the first three and "and N more", and listed with their
    set-points), the runs an earlier inferred reading suggested an environment for, and the corroborating quotes; the card records the same decision on the
    experiment, and `site import` brings it back (an answer recorded since is "no longer asked"). The covered per-run
    questions get no card of their own while it is open.
- **`isaac.fill.facility_from_folder.v1`** — `system.facility.facility_name` and `system.facility.beamline`, the two
  fields the facility hints already suggested (`template.HINTED_PATHS`), for every run (`bundle.folder_facility`,
  `bundle.facility_identified`). The folder name's facility word (the token right before its BL token, as the hints
  read it) must equal the facility of every SPEC fingerprint match (case aside), and its BL token must agree with
  every match's beamline (`bundle._beamline_agrees`); the fingerprint's spelling is the value (`SSRL`, `BL15-2`). The
  beamline is filled only when the folder names the same beamline exactly (a folder that states no branch the
  fingerprint states fills only the facility). **Each run needs its own evidence:** at least one of the run's own
  header lines the fingerprint matched (a detector column or the SPEC account); a run without one is not filled.
  Never when the fingerprint disagrees with the folder (`disagrees_with_folder_name`), either source is missing, the
  matches name several facilities or beamlines, a candidate, an answer or a reading anywhere in the bundle names
  another facility name or beamline, or **a scientist REJECTS any facility name, beamline or producing-organization
  target**: a rejected fill says the identity is wrong somewhere, so neither field is filled for any run, nor the
  organization. `site`, `organization` and `endstation` are not filled. The fingerprint's own `statement` now says
  that the two agreeing hints are this rule's evidence; with a disagreeing folder or several beamlines it still says
  "Both are hints, never answers".
- **`isaac.fill.organization_from_facility.v1`** — `attribution.produced_by.organization`, the beamtime: the facility
  `facility_from_folder` identified, beside at least one run's fingerprint line. The scientist answered on 2026-11-25
  that the producing organisation is the facility named in the beamtime folder. Never when no facility is identified
  so, the facility is disputed (a reject included), or a candidate, an answer or a reading names another organization.
- **`isaac.fill.group_from_folder_pi.v1`** — `attribution.produced_by.group`, the beamtime (`bundle.folder_pi`,
  `bundle.group_from_folder`). The folder must be `<FACILITY>_<BEAMLINE>_<YYYY-MM>_<Surname>_<project>`, and the PI
  token must look like a surname (`bundle.surname_like`): letters of any script with an inner hyphen or apostrophe at
  most, a capital first, a lower-case letter somewhere (so an acronym is not one), not an element symbol or a formula
  (`bundle.reads_as_chemistry`: each hyphen part a run of element symbols, each optionally followed by digits or
  x / y / z, so `Pt`, `Co`, `IrOx`, `TiON`, `Cu-Zn` are refused; a word like `Brown` is not a run of symbols), and
  no part of it a technique word or one of `bundle.NOT_A_SURNAME`'s project, housekeeping, month and group words
  (`Lab`, `Group`, `Team`: `Mehta-Lab` is refused). **A second source must agree**: the readme's month header
  (`# 2031-01_Surname`, or `2031-01_Surname` without the `#`: a readme line that is the month token alone, round 4;
  round 5: or `2031-01_Surname_<project>` when the project is the folder's own),
  a SPEC `#F` data path with `<YYYY-MM>_<Surname>`, a contributor whose name ends in it, or a
  full name ending in it at a labelled position; the folder's token alone is not filled (it stays asked, with the
  folder as its hint). A label's separator is `:`, `=`, a dash with spaces round it (`# PI - Bob Smith`,
  `PI – Bob Smith`), or a dash right before a capital (`PI-Bob Smith`). A trailing comma segment naming an
  institution (University, Institute, Lab, Laboratory, Center / Centre, Inc, College, National, School, Department)
  is dropped before the people are counted (`PI: Ada Quillfeather, University of …` names one person). **A PI line takes precedence** (`PI:` or `Principal investigator:`, in any case: `# PI: bob
  smith` names a person; a PI line naming several people, `PI: Bob Smith and Ada Quillfeather`, means no fill, since
  the field holds one group): when one names people, one of them must end in the folder's surname, else no fill; a users
  or group line only backs a match up and never overrides a PI line (`# PI: Bob Smith` beside `# Users: Ada
  Quillfeather, Cy Jones` is not filled, in either order); without a PI line, a users or group line that names people,
  none of them the folder's PI, stops it too. A full name is taken from a PI line first, and from a users or group
  line or a contributor only when no PI line gives one. **A full name is read only from a labelled position** — `PI:`, `Principal investigator:`,
  `Users:`, `Group:` on a readme header line or in a checked stated reading, "group of <name>", or a contributor's
  name — never from any capitalised words ("Thanks Ada Quillfeather" names no PI). The value is "<full name> group"
  when exactly one such full name is found, else "<Surname> group" exactly as the folder writes it. Never when the
  readme's header or a data path names ANOTHER name-like token right after the beamtime's month, whatever its case
  (two candidate PIs); when a labelled line names people and none of them ends in the folder's surname (`# PI: Bob
  Smith`, `# Users: Bob Smith, Cy Jones`); or when a candidate, an answer or a reading names another group. A SPEC
  `#C … User = <account>` line is never read as a labelled position: it names an account. **The owner's direction:**
  when the folder literally names the PI, asking "is this the X group?" wastes the scientist's time. This supersedes
  the skill's "never name the group from the folder name" (SKILL.md is rewritten in slice 4).
- **The readme's header lines** (`experiment.beamtime_header_lines`, optional): the import reads the shared readme's
  first 20 lines and keeps, as literals with their source, path and line, up to 8 that are comment lines (`#`), label
  the PI, the group or the users, or are a month token alone (`2031-01_Surname`). The readme reader still assigns them no concept. The group rule fills only a
  bundle that holds this field (possibly empty), so a bundle imported before 1.20.0 takes the group fill only once
  it is imported again; the other three rules need nothing new and apply on its next write.
- **Fill rule set 3** (`bundle.FILL_RULE_SET`). A 1.19.0 bundle (rule set 2) whose re-derived fills differ is STALE,
  never INVALID; its next write raises it to 1.20.0 (with `bundle.CHANGES_ADDED_IN["1.20.0"]` in its
  `format_upgrades` entry) and logs each moved value in `eligibility_rederived`. A newer rule set is still refused.
- **Questions, status, composition.** A filled target is left out of its question with the 1.19.0 wording ("Left out,
  because a rule filled the value from the evidence…", `left_out_as_filled`), and question ids do not move;
  `counts.filled` and `bundle status`'s `values_filled` count the new fills; a filled value composes as `inferred` with
  the derivation entry `{"source_type": "derivation", "rule": <rule id>, …, "note"}` and only when every measured run
  of the group has the same filled or confirmed value. The folder's name is cited as a `file_listing` witness.
- **Not in this slice:** the end review and SKILL.md (slice 4).

### What 1.21.0 added (the end review — DEC-99, slice 4 of DEC-96)

Slice 4 of `docs/fill-first-design-2026-11-25.md`, design item 10. The owner's direction (2026-11-25): "at the end,
when the user has the final version of the record output, we can just have them review that". The format moves because
one decision joins `scientist_decisions[].decision` (`review`), with two decision fields (`reviewed_fills`,
`reviewed_bundle_version`), and an optional block joins candidates and missing values (`review`); a 1.20.0 validator
refuses all three. No fill rule changed: `FILL_RULE_SET` stays 3.

- **`isaac bundle review <dir> [--field <path> ...] [--limit N] [--json]`** (`review.review`), after `build-records`
  (refused before, exit 1, saying to confirm groups first when none is confirmed). `--field` repeats and takes either
  the questions' path or the record's (`records.FIELD_REMAP`: `context.electrochemistry.reaction` is
  `context.reaction.name`); a path no built record carries is refused (exit 2) naming the reviewable fields. It READS
  ONLY, the version and the bundle read under one lock: `bundle.json` is not written, and the values it prints are recorded in
  `exposures.pending.jsonl` (1.17.0). It composes the confirmed groups NOW (`records.fresh_compositions`) and compares
  each draft with the one `build-records` wrote (`records_built_since_last_change`). It lists:
  - every value a rule FILLED that a built record carries (`composition.filled_by_rule`, which since 1.21.0 names only
    unreviewed fills, and only fields the record carries: a set-point the scale gate or a slot rule took out is no fill
    of the record), grouped by field and value: the value in words with its unit (a potential with its scale, "0.06 V
    vs RHE", or "scale not stated"), how many values and how many records, the rule in plain words
    (`review.RULE_WORDS`), and the witness a beamline scientist accepts (`review.witness`, from the evidence of that field
    AND value only, and only entries whose `relation` is `supports` or unstated — never a contradicting or context line,
    never a bare number that is another value: the beamtime folder's name for the facility, organization and group,
    found by its locator, then a scan-header line of the runs' own files naming that row's own value (the facility, or
    the beamline) as a whole word, never a `User = <login>` line; for the group, the corroborating line its basis
    recorded; for the environment, the run's own set-point and what shows it was electrochemical; "read from N of the beamline's
    own acquisition files" for the domain; a header number said as what its motor is, only where it is what the value
    rests on (the emission analyser for the technique, or the number shown itself); otherwise the shortest quote of a
    document line, a folder listing or a sheet cell, a checked Claude reading's quote included; never the derivation
    entry or an answer). The organization is listed as "organization", the record's own word;
  - for `isaac.fill.environment_from_held_potential.v1`: the scientist's convention answer, how many measurements it was
    given for (`environment_convention_covers`), and how many it reached (the environment values that rule fills);
  - separately, the scan keep / drop decisions as each composed group's processing result stores them
    (`processing_results[].scan_decisions`, the approved result when there is one; never re-derived): counts, every
    dropped scan with its reasons, every scan the scientist decided, and the curve's plot file;
  - `reviewed_earlier` (fills a review still binds) and `reviewed_changed_since` (`bundle.review_changed_since`).
  The plain output names no id and no rule id; `--json` carries both, the `bundle_version` and the LISTING DIGEST
  (`review.listing_digest`: 16 hex of the sha256 of exactly the items listed — target, value, rule, evidence hash —
  and the field filter). It ends with what to do: "looks right" → the accept command with that `--listing`; a change →
  `decide`, then `build-records` again.
- **`--accept --by "<name>" --listing <digest> [--orcid] [--note] [--field <path> ...] [--version <bundle_version>]
  [--apply]`** (`review.accept`): a preview unless `--apply` (the convention of `annotate --from-readings` and the two
  answer imports; `decide` itself records at once). `--apply` REQUIRES `--listing` (exit 2 without). Under the bundle
  lock it re-lists for the same fields and refuses (exit 1, nothing recorded) when the listing's digest is not the one
  given ("the values changed since you were shown them"), when the records changed since `build-records`, or when no
  record is built; `--version` also refuses a bundle that moved (exit 2), and `--limit` is refused (it binds every value
  the listing shows). The preview runs without `--listing` and says `--apply` will need it. Several `--field`s are one
  listing, one digest and one decision. After an `--apply` the records changed, so its statement and `next` say: run
  `build-records` again, then `bundle review` for what is left. It records ONE decision: target `experiment`, decision `review`, value `null`,
  `reviewed_fills: [{target: {kind, id}, value, rule_id, evidence_sha256}]` and `reviewed_bundle_version`. Nothing
  waiting: nothing is recorded. `decide --decision review` is refused (`mutations._decide_arguments`).
- **The binding** (`bundle.review_item`, `bundle.review_binding_holds`; the clock-zone binding pattern of 1.4.0): each
  item names its target, the value and rule its fill had, and `evidence_sha256` (`bundle.fill_evidence_sha256`), the
  sha256 in canonical JSON of what the fill rests on: its `fill` block, each named reading's `reading_sha256`, and per
  kind a candidate's file witnesses (source, path, locator, literal, relation, reader) or, for a missing value, what its
  rule read (the environment's set-point candidates and corroboration WITH their values, literals and quotes, and the
  convention decision; the facility the folder and
  the fingerprint agree on and the run's matched header lines; the group's surname, full name and agreeing lines; the
  readers of every run for the domain). It is re-derived on every derivation, never stored on the value.
- **The derivation** (`bundle.derive_value_state(..., reviewed=)`, in `apply_derivations`): a value a rule fills, with
  no decision, whose latest binding (`bundle.review_bindings`: each target's latest across every review) still holds is
  `scientist_confirmed`, keeps its `fill` block and carries `review: {decision_id, basis: "reviewed_final_records"}`;
  it is eligible with the fill's value. **Any change to a bound item** — its value (the convention answered again), its
  rule, or its evidence (a witness edited, a reading reloaded) — returns exactly that item to `filled`; `bundle status`
  counts it ("N reviewed value(s) changed since the review") and the next review lists it again. **A decision beats the
  review**: any decision on the target (a defer included) means no fill, so nothing is bound; such a target is not
  counted as changed (the decision is the answer now).
- **The validator** re-derives the `review` block like the `fill` block and refuses one it cannot re-derive (a
  hand-written review, or a review left on a value that is filled again), and refuses a `review` decision that is not on
  the experiment, carries a value, binds no item, names a target that does not exist in the bundle, a rule that is not
  registered or that never fills that target (`bundle._review_item_fillable`, TIMELESS facts only, since a review is
  append-only history no command can repair: the kind and field the rule fills, `bundle.REVIEW_RULES_BY_KIND` and
  `bundle.REVIEW_RULE_PATHS`, and for the reading rule a stated, quote-checked reading of that very target; never the
  vocabulary, the never-fills lists or a candidate's current value, which a later build may change — such an item
  simply stops binding and is said as changed since), a target a scientist had decided before the review (no fill was there to bind), or no
  64-hex evidence hash, and `reviewed_fills` on any other decision (`bundle.review_decision_errors`).
- **Composition** (`records.compose_group`): a reviewed fill composes through the fill path (its witnesses and its
  derivation entry, so the sidecar still names the rule) plus a `user_confirmation` of the review (the decision, who,
  when, `basis: reviewed_final_records`); the field is `verified` when every contributing value is confirmed or
  reviewed, `inferred` while any is an unreviewed fill. A reviewed fill keeps a fill's composition rules (a decision on
  the run beats it; a merged group composes it only when every measured run has it). The report lists reviewed fills in
  `reviewed_by_rule`, and `filled_by_rule` only the unreviewed ones. The draft validator accepts both shapes.
- **Questions** ask no reviewed value; with `include_answered` it is back in the question that would ask it, under the
  same id, so `decide --question` records a correction. A reviewed fill is still a fill to `group_unusable_fills` and to
  a dead answer slot's rule, as the composer treats it.
- **`bundle status`**: ONE line on the values a rule filled: how many are not yet reviewed (`values_filled`, as
  before) and how many confirmed in the review (`values_reviewed`); of the unreviewed, how many in the built records wait
  for the review (`values_to_review`) and how many are in no built record yet (their groups not confirmed, or not built),
  so the review cannot reach them; or that every one in the built records is reviewed. And what became of reviewed
  values that changed since (`reviewed_changed`: filled again, waiting for the next review, or now asked). "Next:" points to
  `isaac bundle review` once records are built and values in them wait; before `build-records` its last step names the
  review between building and validating. `summary.md`'s line about fills is unchanged and stays true.
- **Answer memory never learns a review** (it reads `confirm` / `correct` decisions of value targets only), so a reviewed
  fill is never offered as a scientist's answer on another beamtime.
- **Older bundles** load as before: a 1.2.0–1.17.0 bundle is STALE where a rule fills; a 1.18.0–1.20.0 bundle holds no
  review, derives the same states, and is raised to 1.21.0 by its next write (with `bundle.CHANGES_ADDED_IN["1.21.0"]` in
  its `format_upgrades` entry).
- **Not built:** review of record groups (design finding 7: still one bulk question in Step 5) and a per-value accept
  (`--field` narrows it to one field).

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
(`bundle show candidate|conflict|run|question`, `bundle list candidates`, `bundle reveal`,
`bundle propose-terms` (§24), `bundle questions`: each hint's candidate, each conflict, and every
candidate whose value a confirm question's text states — `questions.confirm_value_shown`, all of
them, not only the hinted ones; polish c6-r);
the exposure is written BEFORE anything is printed, and if it cannot be written nothing is
printed. Since 1.17.0 a command that only reads writes it to `exposures.pending.jsonl` beside `bundle.json`, never to
`bundle.json` itself; every load reads it back, and the next write folds it into `exposures[]` (§9, "What 1.17.0
added"). `summary.md` shows no non-conflicting parser value. `bundle annotate --blind` is
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
  `exportable`. Everything else is listed with its verdict. Re-export is idempotent (§25):
  `<records_dir>/isaac-export/index.json` keeps each group's record id.
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
- The evidence sidecar `export.build_sidecar` writes may carry one more key, added by `local_import` after it
  (`export.py` unchanged): `notes`, a list of plain sentences saying what the record was written WITHOUT —
  today the start time left out while the instrument clock's zone is deferred or not answered yet
  (`records.START_TIME_WARNING`). Absent when there is nothing to say; `upload --dry-run` repeats each.

## 14. LOCAL-3: generic readers, grouping, processing

- `isaac import` runs `readers.collect_all_generic(root, skip=<files the engine read>)` after
  the engine for a folder, and `readers.collect_all_generic_zip(zip, skip=...)` for a ZIP given as
  the root (§21, "A ZIP given as the root"). Each generic run is a `runs[]` entry with `source_type:
  generic:<profile>` and `reader {reader_id, profile, profile_version, statements_total,
  statements_kept}`; its statements are `extended_context` entries (`source_recorded`,
  `run_id`, at most 200 per run, the total stated). No statement maps to a field unless an
  explicit, tested rule says so; there is exactly one, `ssrl_xdc_scan_start_v1` (§9 "What 1.4.0
  added"), and the statements stay extended context even then. Claimed files leave `unread_files`. Since 2026-11-09 a ZIP given AS THE ROOT is read
  by the generic readers too, over the members the engine accepts (§21); a ZIP found INSIDE a
  folder is walked one level deep (§21).
  **Since 1.2.0 an XDI file whose header states Athena/Demeter is a `processed_outputs[]`
  entry instead of a run** (§9, "What 1.2.0 added").
- `isaac bundle group <dir> [--regroup]` stores LOCAL-P's proposed `record_groups[]`
  (status `proposed`); `--regroup` keeps every group a scientist decided.
- `isaac process <dir> [--source] [--group ID] [--no-athena] [--params-file]` runs LOCAL-P's
  protocol and stores `processing_results[]` for groups in the bundle, each undecided (a
  result claiming confirmation is stored `needs_review`); decided results are kept. Exit 2
  "processing not installed" when its libraries are missing, or before grouping.
  **The raw scans must be readable.** They are read from `--source`, else from the folder the
  bundle recorded at import (`source_root.local_root_hint`, only with `--record-local-root`;
  each scan is still checked against its recorded `content_sha256`). Exit 2, naming
  `--source <the beamtime folder you imported>`, with NOTHING written (no `record_groups.json`,
  no `processing/`, `bundle.json` unchanged) when neither is given, when that folder does not
  exist, or when not one scan file the groups list is found there with its imported bytes. Some
  scans missing is not refused: each is reported on its own result (`source_file_not_found`).
  **`--group ID` (repeatable) replaces only the named groups' results.** Every other group's
  results are kept exactly as stored, decided or not (the output counts them as
  `kept_other_groups`; `new` counts only the named groups'). Within a named group, an undecided
  result is replaced by this run's. A DECIDED result (approve, reject, needs_changes, defer) is
  never replaced or removed: its decision is bound to its `result_id`, which is derived from
  the protocol version, the group and the sha256 of every input and parameter. Re-processing
  with the same inputs yields the same `result_id`, so the decided result stays and no
  duplicate is stored; with different inputs or parameters the new result gets a new id and is
  stored, undecided, BESIDE the decided one, which keeps its state until a scientist decides the
  new one. `processing/processing_results.json` holds the last run's results only (the bundle
  holds them all).

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
  parser literals, and a confirm question's text states every value `confirm` records, so printing
  records an exposure of each). Rules: experiment > record group > run;
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
- **Template 1.4.0: the template can finish a record.** Every field the record composer needs a
  scientist to supply has a cell. Campaign Info gains three rows after the template's own five:
  B8 **Your group (who produced the data)** (`attribution.produced_by.group`), B9 **Your
  organization (who produced the data)** (`attribution.produced_by.organization`) and B10
  **Domain** (`system.domain`, a dropdown). File List gains **Reaction Drive** and **Reaction
  Catalysis** (`context.reaction.drive` / `.catalysis`, dropdowns), after the current
  set-point. Every list is `bundle.allowed_values`. Campaign Info B4, always
  `system.facility.organization`, now reads **Facility organization (e.g. SLAC / SSRL)**. A
  1.3.0 workbook, which reads "Organization" there and has five rows, still imports
  (`template.campaign_fields_of`, `Column.aliases`). A File List cell's suggestion is that run's
  own evidence: a consolidated question's readings of OTHER runs, and beamtime-wide hints such
  as the folder name, are not shown beside a row (the Campaign Info block still shows them).
- Output: `template export` prints a short summary (path, rows, sheets, how to import);
  `--json` gives the full result with every column's mapping. `template import` prints one line
  per Campaign Info or Configurations cell and per File List column (the number of decisions,
  their kind, the value), then every invalid cell, clash, refusal and refused row in full,
  then totals; cells recorded nowhere and unmapped columns get one line per column. `--full`
  lists every decision and cell; `--json` prints the whole report.
- **A filled question workbook** (the spreadsheet of consolidated questions a scientist is sent, one tab per kind,
  an `ISAAC question ID` column and a `YOUR ANSWER` column): `isaac bundle answers import <dir> <file.xlsx> --by
  "<name>" [--orcid ...] [--folder <name> [--folder-differs-ok]] [--supersede] [--apply] [--json]` (`workbook_answers.py`). A preview by default:
  each answered row of this bundle's folder becomes the exact `bundle decide` it stands for, dry-run through
  `mutations.decide_question` / `mutations.decide` (`dry_run=True`) on a temporary copy of `bundle.json`, so
  the bundle folder is not touched. `yes`/`ok` accepts the row's shown suggestion only when it is the files'
  value (`confirm`) or exactly a value the question offers now (`correct`); a typed value is a `correct`,
  parsed as a template cell, an off-list word kept as a vocabulary request as `decide --as-said` keeps it;
  blank, `no` and `unsure` record nothing. Rules, new questions, rule proposals and the Athena merges tab
  are reported (Athena rows with their `athena_match` / `athena_match_not` / `athena_ignore` entries),
  never applied; "same for all" is reported, never expanded. `--apply` records through the same calls with
  the note `workbook <file> '<tab>'!<cell>`; a second run records nothing new. It refuses (exit 4) a bundle
  inside a folder named `_runs…`. Tabs and columns are found from header rows, not titles; an unknown tab
  is listed, an id that no longer resolves is listed per row with the reason. The workbook carries no bundle id
  or decisions fingerprint, so freshness is checked per target: an answer the decide path would record over a
  DIFFERENT scientist decision already held (same target, same decision family) is refused, naming that
  decision, unless `--supersede`. A "confirms the value the files give" proposal is only ever a confirm of the
  files' current value; placeholders (`-`, `none`, `TBD` …) record nothing; a blank Folder on an id row is no
  bundle's; a per-record answer overrides its collapsed row.
- **The question site** (a small hosted site where a scientist answers a few questions at a time):
  `isaac bundle site export <dir> --out <folder> [--suggestions <file>] [--include optional|deferred|approvals]
  [--site-template <folder>] [--json]` writes `<folder>/data/site-data.json` and the images its cards show
  (`question_site.py`), one plain-words card per real ask, each card's decide calls dry-run on a temporary copy
  of `bundle.json`; `--out` must be outside every git working tree and the bundle folder (exit 4). It writes to
  the bundle only `exposures` (command `bundle site export`). `isaac bundle site import <dir> <answers.json>
  --site-data <folder>/data/site-data.json [--apply] [--remember] [--json]` (`question_site_import.py`) reads the
  site's answers back: a preview by default, `--apply` through `mutations.decide_question` / `mutations.decide`
  under `<name> (question site)` with a note naming the card and its time, the `_runs…` refusal, and nothing new
  on a second run. The two files, every rule and every addition are in `docs/question-site-contract.md`.

## 20. Suggestions: the absorber, facility hints, and a Claude reading pass

Three ways the import shows a scientist what the files already say, so they can answer in one
step. None of them is a value: each is a suggestion or hint, and only a scientist decision makes
anything `scientist_confirmed`. (Since 1.19.0, DEC-97, a stated reading-pass finding whose quote check is
stored on it and whose quote states the value can be FILLED by the registered reading rule, §9 "What 1.19.0
added"; an inferred finding, the absorber and the facility hints are still never filled.)

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
  data was taken. **Since 1.20.0 (DEC-98)** the two hints together are the evidence of one fill rule: where the
  folder name's facility word and BL token and the SPEC fingerprint name the same facility and beamline, the
  facility name and the beamline are filled (`isaac.fill.facility_from_folder.v1`, §9 "What 1.20.0 added"); one
  hint alone, or two that disagree, still only shows.
- **A Claude reading pass**: `bundle annotate <bundle> --from-readings <findings.json> --model <id>`.
  - The file has format `isaac.reading_findings`. Each finding gives `field_path`, `value`,
    `applies_to` (`experiment`, or `runs` with exact run labels), `source.path`,
    `source.locator`, a `quote`, `strength` (`stated` or `inferred`) and `reasoning`. `source.path`
    must be relative to the imported folder. Since 1.12.0 every quote is CHECKED against the cited
    file (§9 "What 1.12.0 added"); a `../` document beside the folder cannot be checked, so its
    findings are refused.
  - Each finding becomes one AI interpretation per target it reaches: the missing value or
    extracted candidate of that field on every live run it names (the record group, for an
    absorber finding; below).
  - The interpretation carries the new optional fields `source_path`, `quote`, `strength` and
    `finding_id`. `source_refs` carries the `source_id` when the cited file is a bundle source.
  - The default is a preview that writes nothing. `--apply` records everything in one locked
    write. An identical reading of a target is never recorded twice. Since 1.19.0 each reading keeps
    its quote check and scope, and a checked, stated reading whose quote states the value can FILL it
    (§9 "What 1.19.0 added", DEC-97); an inferred or unchecked one stays a suggestion.
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
    - **Allowed values are the export target's list** (`bundle.allowed_values`, §26: the portal's
      pinned vocabulary copy, which for this field equals the vendored and pinned schemas' `enum`),
      read at runtime by `bundle.value_problem`. No list is transcribed into code, so a refresh of the
      pinned copy changes what is accepted. `decide` stores what it is given: an answer outside
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
  returns. Each is staged in a directory of its own (`z<zip>/m<member number>/`, never derived from
  the member's name, so case-insensitive volumes, Unicode forms and a member `x` beside `x/y` cannot
  collide) under its REAL basename, so a reader sees the same `Path.suffix` a loose copy of the file
  gives it (`SAMPLEA.nor (copy)` -> `.nor (copy)`). Only a basename that cannot be written safely (a
  control character, over 255 bytes, or one the staging volume refuses) is staged as
  `m<member number><suffix>` instead, keeping a plain `.abc` suffix. (Until 2026-11-09 every member was
  staged under that numbered name, so a nested member whose suffix was not a plain `.abc` reported
  `extension: ""` in `processed_outputs[].files[]` where its loose copy reported the suffix; the
  reader's own run hints are not written to the bundle.) Its bytes are hashed against the walk's `content_sha256` before a reader sees
  them. A member that cannot be staged, or whose staged bytes
  differ, is not offered to the readers and, if no engine reader read it, is listed in
  `unread_files` with `reason_code: member_not_staged` and the reason; the import continues. The
  staging budget is the engine's (the folder's own accepted bytes and entries first). Nothing is
  written beside the source.
- **Not covered:** a ZIP given as the root does not expand ZIPs among its members (each is listed in
  `unread_files`: a member that is itself a ZIP and was not otherwise read with `reason_code:
  zip_inside_zip_not_opened`, see below), and `isaac bundle show ... excerpt` re-walks without nested expansion,
  so it cannot show text from a nested member.

### A ZIP given as the root (2026-11-09)

- **The generic readers read a top-level ZIP's members** (`readers.collect_all_generic_zip`). Before
  this, `isaac import <x>.zip` ran only the engine, so a beamtime of SSRL XDC scans, XDI or other
  generic formats handed over as a ZIP imported no runs while the same files as a folder did.
- **The members are the engine's.** The walk is the engine's own call for a ZIP root
  (`bl15.archive.inventory_zip(..., refuse_duplicates=True)`), so every guard and refusal of §21's
  nested walk applies, and each member is offered under the very `archive_path` the engine gives
  it: the member path, with a "compress this folder" wrapper stripped (`common_root_prefix`), never
  a `<zip>!/` prefix. `skip`, the bundle's `sources[]` and every claim are one set of strings.
- **`__MACOSX/` and `.DS_Store` are left out**, as the engine leaves them out, each reported in
  `unread_files` as `operating_system_metadata`: the whole `__MACOSX/` tree as ONE row, and each
  `.DS_Store` as a row of its own (in a folder too). An AppleDouble `._<name>` member OUTSIDE
  `__MACOSX/` is an ordinary member, as the same file is in a folder.
- **Staging** is as for a nested ZIP (`z0001/m<member number>/<real basename>`, digest re-checked
  against the generic side's own walk of the ZIP, as a folder's generic walk is its own pass too;
  removed before the import returns; `member_not_staged` for a member that could not be offered).
  The members are offered in the order the folder walk lists the same files (`b/x` before `b.txt`).
- **What is the same and what is not.** A ZIP of a folder gives the same sources, runs, run ids,
  candidates and candidate ids, missing values, questions, extended context (in the same order),
  processed outputs (extensions included) and the same proposed record groups (members, roles,
  basis) as the folder. What differs, and why:
  - `source_root.kind` (`zip`), `source_root.label` and `experiment.label` (the ZIP's file name,
    `X.zip`, where the folder gives `X`), and `source_root.refused_count`;
  - **record-group and merge-candidate ids**: they are hashed from the experiment key, which is
    `source_root.label` (`grouping.experiment_key_of`), so `X.zip` and `X` give different ids for
    the same groups. This was already so for a ZIP the engine read, and is left as it is;
  - a Finder ZIP's `__MACOSX/` tree is ONE extra `unread_files` row (`operating_system_metadata`),
    which the folder does not have; each `.DS_Store` is a row of its own, in the ZIP and in a folder
    alike, so it differs only when one of the two holds a `.DS_Store` the other does not.
- **A ZIP among a top-level ZIP's members is not opened**, by the engine or by the generic readers
  (a ZIP inside a FOLDER is). Since 2026-11-09 a member named `.zip` whose bytes ARE a ZIP (it opens
  and its member list reads: the test a folder's nested walk passes) and that no reader read gets
  `reason_code: zip_inside_zip_not_opened` (it was `no_reader_for_source_type`, whose "this build has
  no reader for this kind of source" text wrongly suggested ZIPs cannot be read), with the reason
  "This ZIP is inside the ZIP that was imported, and a ZIP inside a ZIP is not opened ... import the
  unzipped folder instead: a ZIP inside a folder is opened." Its source's `reader.refused_reason` says
  the same. A file only NAMED `.zip` (empty, junk, a scan saved so) keeps its `no_reader_for_source_type`
  row, since the unzipped folder would refuse it too. `isaac import` prints one line with the count
  of inner ZIPs and that advice. Only a ZIP-root import does this; a folder's rows are unchanged
  (`nested_archive_too_deep` for a ZIP inside a ZIP inside a folder, `reader_refused` for one that
  will not open). `reason_code` is an open string in the schema, so no format change.
- Processing still reads a folder: after a ZIP import, `--source` is the unzipped folder, and when
  everything in the ZIP sits in one folder, that folder (the bundle's paths start inside it).

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

## 23. The local questions screen (2026-10-29, `DEC-94`) — no format bump

The website can read and answer a bundle **on the scientist's own computer only**: the API process
must be started with `ISAAC_LOCAL_BUNDLES_DIR` naming a folder of bundle folders
(`apps/api/isaac_api/local_bundles.py`; how to run it: `docs/ui-local-dev.md`). It adds nothing to
the bundle's shape, so the format version is unchanged.

| Operation | What it does | Writes |
|---|---|---|
| `GET /api/local-bundles` | each bundle folder: name, imported-folder label, beamline readings, `format_version`, the `bundle check` status (VALID / STALE / INVALID, decided in `cmd_bundle_check`'s order), counts, readiness, `bundle_version` | nothing |
| `GET …/{bundle}/progress` | record groups by status, processing results by state, consolidated question counts, `minimum_answers_for_one_group`, what blocks export, the last `validation/<group>.json` verdicts (flagged when older than `bundle.json`); `missing_share` is `null` — no command computes one | `exposures[]`: each candidate whose value the minimum's warnings state (`values_shown_from`), command `bundle progress` |
| `GET …/{bundle}/questions` | `questions.consolidate` filtered by `kind` / `blocking_only` / `scope`, paged like `bundle questions`; each question gains a `display` block (scopes with run names, suggestions with who made them, file, locator, quote, `confirmed: false`, the value rule from `template.rule_for_path` with a unit read from the field name's suffix) and `capture` lists open merge candidates and unselected Athena versions | `exposures[]`: every parser value shown — at least what `bundle questions` records |
| `GET …/{bundle}/questions/answered` | the questions `questions.answered_question` calls `status: answered` (every target answered; a defer leaves one open), under the id they were asked with, each with `current_answers` (decision, value or element/edge or positions, `targets`, `by`, `decided_utc`), filtered by `kind`, paged; `display` shows only what `bundle show question` prints (hints, the values a confirm question's text states — no scope's own suggestions) | `exposures[]`: exactly what `bundle show question` records for each question shown (`cli._question_exposures`), command `bundle show question` |
| `POST …/{bundle}/questions/{id}/answer` | `mutations.decide_question` (also the CLI's `decide --question` path), `dry_run` for a preview; an ANSWERED question (`RESOLVABLE_WHEN_ANSWERED`) is resolved too, as decide resolves it: a later decision replaces an earlier one, a repeat records nothing, a whole absorber re-answer returns `kept_per_group_answers` | `scientist_decisions[]` |
| `POST …/{bundle}/decisions` | `keep_apart`, `merge`, `select_athena_version` only, via `mutate` + `record_decision` | `scientist_decisions[]` |

**Who may ask.** Every operation is refused before anything is read unless the client is loopback,
the `Host` names this computer (`localhost` / `127.0.0.1` / `[::1]` with the server's port; 421
otherwise), any `Origin` is on the CORS allowlist or the server's own loopback origin, and the request
carries `X-ISAAC-Local: 1` (403 otherwise). The boot refuses `ISAAC_LOCAL_BUNDLES_DIR` beside
`ISAAC_BASE_PATH` or a detectable non-loopback `--host` / `UVICORN_HOST`.

**Per-group suggestions.** On missing-value and confirm questions each scope lists its `own_suggestions`
(its targets' extracted values and the AI readings made for them, never confirmed) and the question says
`suggestions_differ`. A dry run returns `by_scope` with `differs: true` for every scope whose own
suggestions exist and do not include the value being written, and the count
`scopes_whose_files_suggest_otherwise`. A confirm question's distinct values are counted over every target. Each own suggestion carries `from_own_files` — true only when the cited source is one of the scope's
runs' own files (acquisition or scan file); a reading quoted from another run's file or a shared document
is `false` and labelled so (`provenance_label`). `only_scopes` answers exactly several named scopes (refused
whole if any has no open target, and with `only`); the screen's "accept for the groups whose own files
suggest it" uses it, through the preview, counting only `from_own_files` groups. Targets are per run, so each multi-run scope also carries `per_target`, `mixed` (its runs' suggestions
differ) and `has_unanimous_value` / `unanimous_value` / `unanimous_from_own_files`; a dry run's `differs` is
set when ANY target's own suggestions exclude the value, and `differing_targets` names those runs.

**The version a write names.** `bundle_version` is `sha256:` of `bundle.json`'s bytes
(`mutations.bundle_version`; the routes read `bundle.json` once and hash and parse those same bytes, and a write returns the version read under its own lock). A write without `expected_version` is 428; one whose version is no
longer stored is 412 (`StaleBundleVersion`), checked under `.bundle.lock` before the load, and the
question is resolved to its targets under that same lock. `isaac bundle decide` passes no version
and behaves as before (its `--question` path now resolves targets under the lock too).

**Typing.** A field answer is the text typed, parsed by the metadata template's cell rules
(`template.parse_answer`): numbers become numbers, as `--json` would make them; a closed list takes an
allowed value exactly. An off-list value is refused (the CLI would store it confirmed but ineligible).
Identity is `local_unverified`, with the typed `by` name, exactly as the CLI's `--by`.

## 24. Values outside the vocabulary: `isaac bundle propose-terms` (2026-10-29) — no format bump

```
isaac bundle propose-terms <bundle_dir> [--out <file.json>] [--force]
```

Lists the values in a bundle that are **outside a fixed list**, grouped by field, with counts and
citations, and writes one **draft proposal per term** in the website's own Schema Proposals
portal format. Everything happens on this machine; **nothing is sent** and no network call is
made. Code: `apps/api/isaac_api/local_import/propose_terms.py`.

**Which lists.** A field is judged by the vendored schema's `enum` at its path (the WEBSITE's list;
since §26 `bundle.value_problem` refuses outside the export target's list instead, so a value on the
portal's list but not the vendored enum is eligible, and is reported here as "the schema lags the
portal", never drafted) and by the portal vocabulary snapshot's term list for it
(`apps/api/isaac_api/data/portal_vocabulary_a1cb1c8.json`, the list the portal checks a proposed
term against). Both are read at run time; a field with neither is never judged. `missing_from`
says which list lacks each term.

**Which values**, each counted under `by_origin`:
- `scientist_confirmed`: a candidate or missing value in state `scientist_confirmed`, with its
  value as the governing decision leaves it;
- `parser_reading`: a candidate's value that no scientist has confirmed;
- `ai_reading`: an AI interpretation's `proposed_value` (`annotate`, `annotate --from-readings`).

**Not read:** a reading pass's findings file. It is not part of a bundle. A term it lists under
`not_found`, or mentions in its notes, is not counted. On the real corpus, the reaction and
cell-type terms the coverage note calls "outside the vocabulary" are recorded only there.

**Citations** are `{file, locator}` only: an evidence entry's `relative_path` and `locator`, or an
AI reading's `source_path` and `excerpt_locator`. No quote is copied out. At most 20 are kept per
term; `citations_total` and `citations_truncated` say how many there were.

**Drafts.** A draft is made only for a term at a field the portal has a term list for. It is the
body and notes of `GET /api/schema-proposals/{id}/portal-payload`, built by the same function
(`schema_proposal_rules.portal_payload`). `description` is **empty**: what a term means is the
proposer's statement, so every draft is `ready_to_send: false`, `sent_by_isaac: false`,
`description_present: false` with `missing: ["description"]` (ISAAC never marks a draft ready to send)
(the portal refuses a description under 20 characters). Before drafting, the website's own
checks run on the term: shape (one word), case convention, and near-duplicates of an allowed
term (`in situ`, `insitu` against `in_situ`). A term they refuse is listed with
`drafted: false`, `problems` and the website's own sentence, and is **never rewritten** into one
they would accept. Also not drafted:
- a field the portal has no list for: no portal payload exists, and the reason says to raise it
  as a schema change;
- a term already in the portal's list but not in the vendored schema's enum: the schema lags the
  portal, and no term is missing.

**Exposure.** The report carries parser values, so every candidate it prints is recorded in
`exposures[]` under `bundle propose-terms` before anything is printed or written (§11). That
write is an ordinary bundle save: on a bundle written by an older build it also raises the format
to this build's, logging the upgrade in `format_upgrades` and any re-derived eligibility in
`eligibility_rederived` (§9), exactly as `bundle list candidates` does. A report with no parser
value writes nothing.

**Output.** JSON with `format: "isaac.term-proposal-drafts"`, `format_version: "1"`,
`sent_by_isaac: false`, the two lists' labels and hashes, `totals` (fields, terms, occurrences,
drafts) and `fields[]`. `--out` writes the file atomically. An existing file is refused (exit 4)
unless `--force`, and so is a directory. A missing bundle exits 6.

**On the website (2026-10-30).** The Schema Proposals page (*Propose a Change*) has a
**Load drafts from a local import** control. It reads this file with the browser's own file
reader and does not upload it. It lists every term with its field, its counts (`count`,
`by_origin`), runs (the term's `runs` when the file has one; otherwise the distinct
`ref.run_id` of its citations, only when every citation names one and none were left out; else
"not stated"; a vocabulary request is counted as "asked by the scientist (N)", never as a reading),
the scientist's own words (a term's structured `scientist_notes`: only `term_as_said` and `note` are
shown in quotation marks, with who, when and where outside them; a note without that structure is not
shown; a file written before §29 carries none, and the page says so), its citations and the problems the
file reports. A `carried_over` term is listed as "no longer found in the bundle" and has no button.
A term with `drafted: false`, or one the server's current vocabulary would refuse, is listed
with its reason and has no button. **Propose This Term** opens the ordinary form on that list and
term. The section comes from the server's `proposal_sections`, the description is **empty and
required** (at least 20 characters, written by the scientist), and the reviewer notes are filled
only from the file: `gate0.problem` (the count, field and missing lists), `gate0.examples` (the
citations, within the limit, with "and N more"), and `gate0.affected_records_estimate` (the
counts). `gate0.flip_list` is never filled. A note the file has no fact for is left empty and
marked required. Nothing is sent until the scientist saves. Saving sends one proposal to the ISAAC
server the page talks to: the server on this computer in a local build, or the hosted server,
where proposals are temporary. The proposal carries a `source` block:
`{kind: "local_import", format: "isaac.term-proposal-drafts", bundle_id?, field_path, term,
occurrences, runs?, citations_total}`. The server accepts it on `add_term` only
(`schema_proposal_rules._validate_source`). Its `field_path` and `term` must be the proposal's
own category and term, any other key is `unknown_field`, and it requires `gate0.examples` and
`gate0.affected_records_estimate`. The status stays `pending`, a duplicate pending proposal is
still `409`, and nothing is approved, applied or sent.

**Measured 2026-10-29** on copies of the six real beamtime bundles (counts only): 618
occurrences of 16 distinct off-list values in 4 fields. All are AI readings; no parser value
and no confirmed value is off a list. They produce 2 drafts, for one term in two beamtimes: 131
readings of a potential scale that neither list has. The other 14 are phrases or sentences the
website refuses as a term, in `system.technique` and in `sample.material.provenance`, a field
the portal closes with a six-word list. They are listed, not drafted. No exposure was written,
because no parser value was printed.

## 25. Decide, evidence, validate and export hardening (2026-10-29 audit) — format 1.8.0 for the bounds only

- **`decide` refuses a value its field refuses** (`mutations._decided_value_problem`, shared by the CLI and
  the local questions screen). A `confirm`/`correct` on a candidate, missing value or conflict whose value
  eligibility would reject (`bundle.value_problem`: the field's allowed values — since §26 the export
  target's list, `bundle.allowed_values` — the vendored schema's `type`, the `*_utc`
  rule, non-finite numbers) on a path this build writes is refused, exit 2, naming the allowed values (or
  the `--json` hint for a number); nothing is written, and a bulk answer is all-or-nothing. Before, such a
  value was stored `scientist_confirmed`, was never eligible, and its question closed: the record stayed
  blocked with nothing left to ask. A bundle an older build stored with one still loads and writes;
  `bundle.value_unfit_reason` identifies it, and a later `correct` with an allowed value is recorded.
  Asking such values again is `questions.py`'s, through ONE definition: `bundle.unusable_answer_reason`
  (a scientist-confirmed value that is not eligible on a path an answer reaches — an unfit value, of
  which `value_unfit_reason` is the narrower view, or no value) is open again under its question's id.
- **A replay is "unchanged" only when it is the decision that governs now.** A candidate's value is
  governed by the later of its own decision and its conflict's (`bundle.candidate_decision`). After
  `correct` cand → A, `confirm` conflict → B, a second `correct` cand → A is recorded (it changes the
  value back to A); before, it was dropped as a replay. The same in the other order. Two more replays are
  recorded: an approval restated after its result's files changed, and (`decide` only) a value restated after
  a vocabulary request on its field that it can answer — said at or after the earlier decision, reaching what
  it applies to (a run it names, or the whole beamtime), and with a readable time strictly before now (`mutations.restated_after_request`, read
  as `propose-terms` reads an answer), so `in_situ`, then their word `--as-said`, then `in_situ` again
  answers the request. A sheet import records nothing for a cell equal to the current value; the scientist
  answers with `decide` then. A re-recorded decision gets a new `decision_id` and time, so a record exported
  again cites it.
- **A corrected value's evidence says so.** In a draft and its exported sidecar, each file quote keeps
  its `relation` (`supports` / `contradicts` / `context`). When the composed value is not the parser's
  (a `correct`, or a reading chosen on a conflict), the recorded relation is kept as
  `relation_to_parser_value` and `relation` says whether the quote states the value of record; a quote
  of the old value is `contradicts`, never support. The confirmation entry carries `provenance`
  (`scientist_correction` or `scientist_confirmation`) and, when the value changed, `previous_value`.
- **A merge must name something to merge.** `merge` on a record group is refused without
  `--merge-with`, with an unknown id, with the group itself, or with a group that is not live
  (rejected, merged, split). A merge decision an older build stored that combines nothing is listed in
  `group --regroup`'s `merge_decisions_not_combined` with its reason, never skipped.
- **`validate` names the processing approval.** `measurement.series`, `measurement.qc.status` and
  `descriptors.outputs` come only from an approved processing result; until one is approved they are in
  `missing_required` (and `missing_from_processing`), the verdict is `incomplete`, and `processing_fix`
  / the summary give the command (`isaac bundle decide <dir> --target <result id> --decision approve
  --qc-status <value> --by "<name>"`, or `isaac process <dir> --source <the beamtime folder you imported>`
  first when there is no result). Before,
  the verdict was `invalid_official` with "Missing required values: none".
- **Re-export reuses the record id.** `isaac bundle export` keeps `<out>/isaac-export/index.json`
  (`isaac.local-export-index`: per bundle id and group id, the record id, the `content_sha256` of the
  draft and composer overrides it was composed from, and the export time) — in a subfolder, so nothing
  that reads `<out>/*.json` as the records sees it. An unchanged group is
  rewritten under the same id and time, byte for byte (`export: unchanged`). A changed group gets a new
  id; the record it replaces is moved to `<out>/isaac-export/superseded/` (kept, never in an upload plan) and the row
  says so (`export: replaced`, `replaces_record_id`). A group exported before that is now refused is
  WITHDRAWN (§26): its record moves to `<out>/isaac-export/withdrawn/`. `upload --dry-run` lists neither. Records exported before the
  index existed are not recognised (no group id is in a record), so export to a fresh `--out` once.

## 26. Audit round 2 (2026-10-30) — no format bump

- **One list of allowed values: what the export validates against** (`bundle.allowed_values`). The
  local export gates on the portal's pinned schema (`a1cb1c8`) AND the portal's own
  `validate_record_full`, whose vocabulary layer refuses a string off the vocabulary list for its path.
  At the pinned commit every such list equals the pinned schema's `enum` where it has one, so a field's
  list is the pinned vocabulary's entry for its path (read from the repository's verbatim copy,
  `apps/api/isaac_api/data/portal_vocabulary_a1cb1c8.json`, never from the installed validator, so
  stored eligibility does not depend on the machine) and, where the vocabulary has none, the vendored
  schema's `enum`. It is the ONE source for what is offered (questions' `allowed_values` and
  `field_allowed_values`, the template's and the local screen's `rule_for_path`) and what is checked
  (`bundle.value_problem`, so `decide` and eligibility). Before, offering read the export target and
  checking read the vendored v1.05 enum: `system.technique` listed `EPR` and `decide` refused it, the
  cell type listed `not_reported` and refused it, and the sample form, material provenance, reaction
  drive and catalysis listed the portal's words while `decide` accepted anything. A test pins the copy
  to `portal.PINNED_COMMIT` and, when the pinned validator is installed, to its file byte for byte and
  every writable path's list to its schema `enum` intersected with its vocabulary list.
- **Values an older build judged by the vendored list alone** (`bundle.allowed_list_rederivations`) are
  STALE, not INVALID: `check` lists each (eligible before → now, and why); the next write re-derives
  them and logs each in `eligibility_rederived` (no format change). E.g. a confirmed `EPR` becomes
  eligible; a confirmed sample form off the portal's list becomes not eligible and is asked again.
- **Confirm is offered only where `decide` takes it.** A `confirm_value` target whose extracted value
  its field refuses (e.g. an older build's confirm of it, now asked again) is answered like a value-less
  one: `allowed_decisions` are `correct`, `reject`, `defer`. A MIXED question (some targets value-less or
  unfit) keeps `confirm` for the scopes where every target can be confirmed (`confirmable_scopes`) and
  its command names `--only <scope>`, since `decide` refuses a whole answer when one target cannot be
  confirmed; `targets_with_an_unfit_value` counts the unfit ones. The local screen's Accept
  (`distinct_extracted_values`) lists only values `decide` would confirm, and is empty when no
  whole-question confirm is offered; a per-group Accept is offered only for a fit value in a
  confirmable scope.
- **Same value, not text** (`records.same_value`). A quote's `relation` and a confirmation's
  `provenance` compare numbers numerically (`1` = `1.0`, the parser's reading in the unit it normalised
  to), a `*_utc` field's zoned instants as instants (`...Z` = `...+00:00`), and strings exactly. A
  `correct` whose value is the parser's is a `scientist_confirmation`, with no `previous_value`.
- **Withdrawn exports.** A group exported before that is not exportable now — refused by a gate, or no
  longer a scientist-confirmed group — has its record moved to `<out>/isaac-export/withdrawn/` (kept,
  never in an upload plan; nothing replaces it, so it is not "superseded"), its index entry marked
  `withdrawn_utc`, and the export result lists it under `withdrawn` (and on its `refused` row:
  `withdrawn`, `withdrawn_record_id`, `withdrawn_files`). If it was uploaded already, the portal still
  holds it. Exporting the same content later restores it under the same id (`restored_from_withdrawn`).
  An index naming anything that is not an ISAAC record id is refused whole, before any file is touched.
- **A QC status that says something is wrong needs a note.** `decide --qc-status compromised|failed`
  without `--qc-note` is refused, exit 2, nothing written (`mutations.qc_note_problem`). The local screen
  records no processing approval (approval stays a command-line act), so there is nothing to enforce there.
- **The nearest group** (`minimum_for_one_group`) names only the decisions still to make (not "confirm
  the group" once confirmed, not "approve its processing result" once one is approved), is never a group
  with nothing left (counted in `groups_with_nothing_left`; `group_id: null` with a statement when every
  group is done), and with `--scope group:<id>` is that group.
- **Wording.** The technique question says the technique is chosen here, from its allowed values (the
  engine's hosted text, "in Add to Experiment", is unchanged on the website and replaced on save in an
  older bundle). The schema-drift note says an unknown temperature does not block the local export. The
  processing remedy names `isaac process <bundle_dir> --source <the beamtime folder you imported>`.
  `process` on a bundle whose recorded local root is a ZIP says it is a ZIP and to pass the unzipped
  folder as `--source`. A lock file that cannot be opened safely makes THAT bundle "not accessible" in
  the local screen's list (the others still list) and a 409 on its routes, never a 500.

## 27. A scientist's merge has a working path (2026-10-30) — format 1.9.0 for `last` only

Found walking the skill on two real beamtimes (`tests/test_local_import_merge_paths.py`, synthetic):
a merge of two repeat runs that state no sample was refused, and the counter answer the refusal named
changed nothing (the grouping step never joins runs with no stated sample; the merge check ignored the
answer). Default behaviour on an undecided bundle is unchanged: the same groups, merge-candidate and
question ids (measured on the synthetic fixtures and both beamtimes).

- **A merge decision is combined** (`mutations._merge_blocker_details`) when, besides everything §9's
  merge check already requires, the file names agree once repeat markers (`again`, `repeat`, `rep2`,
  `redo`, and a number right after one; `rep2` no longer, §27.1) and the digit tokens at positions declared run counters
  (`set_counter_positions`, `last` included) are left out — or, where they still differ, a scientist
  confirmed the same `sample.material.name` for every run (§27.1: and `--same-conditions`). A token's shape alone still never makes it a
  counter. An unclassified reading read off the names (`unknown_token`, `new_spot`) follows the names;
  one from elsewhere needs the same confirmed sample.
- **Never combined:** runs whose classified readings or conditions differ, and names that differ in a
  token stating a quantity (`400mV`, `0p5wt`, a decimal `7.02`, `pH7`) whatever was confirmed. The
  reason says so plainly and names keeping them apart (confirm each group).
- **Every refusal names commands that work.** `merge_decisions_not_combined[].next_commands` lists them,
  and the reason quotes each in backticks: the counter answer (only when the names differ in whole
  numbers at one position, or always the last token, that no scientist said is not a counter), the
  sample confirmation (one `decide` per run, unless different samples are confirmed), else confirming
  each group. Tests follow each one and regroup.
- **One candidate per set of groups.** A refused merge whose groups already have the rule's candidate
  leads that candidate with `scientist_decided_merge`, under the rule candidate's id.
- **Merge candidates say what they are:** `reason_code` (`grouping.MERGE_REASON_ORDER`), `reason_codes`,
  and `caution` — `names_state_different_samples_or_conditions` when the groups' names differ in more
  than numbers and repeat markers, `no_condition_classified` when no group states a sample, environment
  or condition — each with a plain sentence that also leads the candidate's question. `bundle list
  merge-candidates` adds each group's run labels (file-name stems, 5 per group, the rest counted);
  `bundle show <dir> merge-candidate <id>` shows one (no reading's value, so no exposure).
- **Live groups by default.** `bundle list groups` lists proposed and confirmed groups and counts the
  rest under `not_listed`; `--all` lists history too. `bundle group` adds `live_record_groups`.

### 27.1 Review fixes (2026-10-30): the same sample is not the same conditions — still format 1.9.0

Found in review (`tests/test_local_import_merge_conditions.py`, synthetic); nothing had shipped, so the
additions stay in 1.9.0. Undecided bundles are unchanged (the same group, merge-candidate and question ids
on the synthetic fixtures).

- **A sample confirmation alone no longer combines names that differ.** `Q4_…_pristine` and `Q4_…_cycled`
  were combined once one sample was confirmed for both — true of one material measured in two
  conditions. Now the merge decision must also carry `same_conditions_tokens` (`decide … --decision merge
  --same-conditions`): the words the names differ in, which the scientist states are labels, not
  conditions. It covers only those words (a group added later, differing in another word, is not
  combined). `--same-conditions` is refused on anything but a merge, when the names do not differ, and
  when they differ in a quantity. The refusal asks "same sample AND same conditions? the names differ
  in: cycled / pristine" and its `next_commands` are the sample confirmations and the merge recorded
  again with `--same-conditions` on its own target (replacing the refused decision).
- **Quantities fail closed.** Any token mixing letters and digits (`T300`, `E1`, `s1`, `T300K`, `E0p4V`,
  `cyc10`, `spot2`) states a possible quantity: names differing in one are never combined. A bare number
  is left to the counter and unit-word rules. Names holding the same words in another order, or a word
  another number of times, are never combined either: there is no word to acknowledge.
- **`RepN` is a replicate on the merge path.** A glued `Rep1`/`rep2` is compared as a token (another
  sample), so `Rep1_ZnO` / `Rep2_ZnO` need the same answers as any word. The default grouping still
  reads it as a repeat marker (unchanged). `again`, `repeat`, `redo` (and a number after one) remain
  markers, and the repeat path combines only when the marker is the ONLY difference.
- **`last` is a counter only where it is one** (`grouping.last_counter_exempt`). Among names sharing a
  prefix (the name up to its trailing whole numbers) whose trailing numbers differ in count, only the
  longest is read as ending in a counter: `…_pH2_3` / `…_pH2_4` beside `…_pH2_3_001` are no longer
  joined. Where every name of a prefix ends the same way (every name ending in a counter, names of
  different length) nothing changes.
- **`decide … set_counter_positions` says what it would do:** `regroup_preview` (`groups_joined`, `into`,
  `groups_split`, `statement`) counts the current proposed groups the next regroup would join, computed
  as the regroup computes it; nothing is regrouped.

## 28. A split makes exactly the groups the scientist named (2026-10-30) — no format bump

Found by a docs review, then measured (`tests/test_local_import_polish_c8s.py`, synthetic): `decide
--decision split --split-into '[[…],[…]]'` stored the lists on the decision and no code read them. The
split group became history, its runs were proposed afresh on the next regroup, and that proposal —
identical to the split group — was skipped as already ruled on: a 3-run group split 2+1 left its three runs
in NO live group. Undecided bundles are unchanged: the same groups, merge candidates, grouping questions and
question ids, byte for byte, on five synthetic fixtures (also after a merge, a counter answer and a confirm).

- **`decide` refuses a split that cannot make groups**, plainly, recording nothing: no `--split-into`; fewer
  than two lists; an empty list; a run key the bundle does not hold, or one the group does not hold; a run in
  two lists; a run of the group left out. A group whose runs another live group now holds (an earlier split's
  parts) is not split again: split or decide that group. `--split-into` goes with `split` only.
- **The split makes ONE proposed group per list, at once.** Each part is what the grouping rule proposes over
  its runs alone (a part the rule would keep apart, from a group a merge combined, is combined as a merge is);
  its id is `grouping.group_id_for(experiment_key, its run keys + ["split-from:<split group id>"])`, stable on
  every regroup and never an id the rule gives. It carries `split_by_decision` (`decision_id`,
  `split_group_id`, `part`, `of`, `decided_by`, `statement`) and the flag `split_by_scientist_decision`. It is
  `proposed`: the scientist confirms (or merges, rejects, splits) each. The reply lists them in
  `split_into_groups` and says them in its `statement`. (`record_group` allows additional properties, so a
  1.9.0 validator accepts the field: no format bump.)
- **A regroup keeps a split as named** while it is the group's latest status decision (a later confirm,
  reject, merge or defer supersedes it, as for a merge). Its parts are proposed again under the same ids and
  their runs kept out of the fresh proposal, as a confirmed group's are: a counter answer cannot join them, no
  rule merge candidate names them, and `matches_binding_group` does not offer a confirmed part to its sibling.
  A part a decision moved is kept as that decision left it (confirmed; rejected — a fresh proposal of exactly
  its runs is not made again; split again — its own parts; merged — the merge is applied as §27). The counter
  question's text says the split stands where it would otherwise have joined them.
- **The regroup reply** adds `splits_applied[]` (`decision_id`, `group_id`, `groups[{group_id,
  member_run_keys, status}]`, `applied_now`, `statement`) and `split_decisions_not_applied[]` (`decision_id`,
  `group_id`, `reason`, `next_commands`) when a split is in force; neither appears otherwise.
- **An older bundle** that holds a split decision with no parts gets them on the next regroup (`applied_now`,
  and the statement says so): the same ids and the same groups, merge candidates and question ids this build's
  decide and regroup give; every other group keeps its id. A stored split whose lists cannot make groups (an
  older build accepted a split with none) makes no group: `split_decisions_not_applied` names why and the
  `decide … --split-into` that fixes it (its runs, in no live group, can be split again).

## 29. Vocabulary requests and the second drafts run (2026-10-30) — format 1.10.0 for the section only

Walking the skill on a real beamtime: five words the scientist gave (a technique, an environment, a
reaction, a cell type, a potential scale) were refused by `decide`, `template import` and `template
adopt`, kept nowhere, and `bundle propose-terms` drafted nothing (0 terms).

- **Kept as a vocabulary request** (§9 "What 1.10.0 added"). `decide` (by target or `--question`; a
  bulk call keeps one request for every target the same answer reached) ONLY with `--as-said`, the
  scientist's statement that the value is their own word (c10-d: without it an off-list value keeps
  NOTHING, and the refusal adds "Nothing was kept (no vocabulary request): if this is the scientist's own
  word, repeat with --as-said", so a value tried while working out a mapping is never put in their name;
  `--as-said` without `--value` is refused, and (c10-r) so is `--as-said` with any decision but `confirm` or
  `correct`; on a value the field accepts it is recorded as ever and the reply says "--as-said kept nothing";
  a request it keeps records `source.as_said: true`; the Local Imports page passes no `as_said` and never keeps
  one), `template import --apply` (one
  request per field and word, with its cells and runs; a preview keeps nothing and says "would be kept")
  and `template adopt` (their sheet's not-allowed values, ONLY with `--by`, passed once the scientist says the sheet is
  theirs, recorded before the workbook is written; without it nothing is kept and the summary says
  "Off-list values were not kept as requests: no name given") keep the word when it is refused ONLY for being off the list. The word is
  kept and the command did what was asked: `decide --as-said` exits 0 and prints `vocabulary_request_kept`,
  `decision_recorded: false` and a statement that begins "'<word>' is kept as a vocabulary request;
  `isaac bundle propose-terms` can draft it" (r5f), then says no decision and no value was recorded, and why
  (the allowed values listed). The library call still raises `OffListRefused` (with `kept`). Without `--as-said` the
  refusal is as before (exit 2, nothing kept). The same answer by the same person from the same place
  keeps nothing new and writes nothing. Any other refusal (a word in a number field, a local time with no
  zone) keeps nothing. Per-run answer slots a refused `--only group:<id>` answer made are dropped; the
  request names their runs.
- **`propose-terms` reads them** (origin `scientist_request`), beside the AI readings. An AI reading whose
  target a scientist has since confirmed or corrected with an allowed value is NOT counted
  (`skipped.ai_readings_already_answered`). Each term carries `runs` (a count), `run_ids` and
  `scientist_notes` (`{term_as_said, note, by, when, source, request_id}`: `term_as_said` is the answer as
  given and `note` the scientist's own `--note` (or `null`) — their words, and nothing else is; `by`, `when`
  and `source` (`kind`, `said_in`, `file`, `cells`, `question_id`) are the attribution, said outside any
  quotation), and each citation `run_ids` and a file NAME without folders — the keys the website's loader
  reads. The drafts file stays `format_version: "1"` (the additions are keys a version-1 reader ignores).
- **Equivalences and near terms** (`propose_terms.EQUIVALENT_TERMS`, `NEAR_TERMS`). A word that names an
  existing term — at `potential_scale` and `reference_electrode.type`:
  `reversible_hydrogen_electrode`/`RHE`, `standard_hydrogen_electrode`/`SHE`,
  `saturated_calomel_electrode`/`SCE`, `silver_silver_chloride`/`Ag/AgCl` (never bare `silver_chloride`, the salt), matched
  ignoring case, spaces and hyphens, only while the term is on the list — is not drafted:
  `use_existing`, problem `equivalent_existing_term`, "Use `RHE` (an existing term)", and `decide`'s refusal
  says it too. A close term (`XANES`, `EXAFS` beside `XAS`/`HERFD-XAS`; any existing term sharing a whole run
  of words, `three_electrode` in `three_electrode_static_cell`) is drafted with `check_existing` and
  `check_existing_question` (also a payload note): the description must say why none of them fits. A
  genuinely new term is never blocked.
- **A term the website refuses for its shape** (a space) is still not drafted; its draft adds `ask`: the
  term as one word, e.g. `cathodic_corrosion`. ISAAC never writes that word as the term.
- **`--merge`** updates an existing `--out` file instead of exit 4: this run's terms (new ones added, counts,
  citations, runs and notes re-read; `scientist_notes` come ONLY from the bundle's `vocabulary_requests`,
  never from the file), a description in a draft's body kept (`description_kept_from_earlier_file`,
  `description_written_by: null`: the file is editable, so who wrote it is not known; `description_present`
  when the website's rules pass it; `ready_to_send` stays false), and a term no longer found carried over
  (`carried_over: true`, `current: false`, count 0, no notes or citations, the file's counts under
  `as_in_earlier_file`; never proposed, and the website will not file it). The CLI says "a description in the
  file was kept (who wrote it is not known)". A file that is not a drafts file, or one for another bundle, is refused (exit 4);
  `--merge` needs `--out` and not `--force` (exit 2). The file gains `merges[]`.
- **`bundle validate` adds `pending_vocabulary`** (`field_path`, `term`, `groups` (10 shown),
  `groups_total`, `request_ids`, `statement`): a confirmed group whose draft lacks the field and holds one
  of the request's runs (every group for a beamtime-wide request). (c14) `groups_exportable` counts those groups
  whose verdict is `exportable`; then the statement adds "This does not block export; the record is written without it".
- **(c14) A draft counts only what still asks for the term.** A request answered since for every run it names
  (`propose_terms.request_fully_answered`) is set apart when another request for the term is still open: the draft's
  `runs`, `run_ids`, `count`, `by_origin` and citations are the open requests' and readings' only
  (`answered_requests_apart` counts what was set apart), `partly_answered` is read over the open requests, and
  `earlier_requests_answered` / `earlier_requests_answered_note` name the open request(s) and the request(s) answered
  since ("… is not part of this draft"); a request whose runs are all in no live record group never counts as open. A term answered throughout keeps all its counts, as before. `--merge` keeps an answered
  term's `earlier_description` "only in case the scientist asks for the word again; … not to be filed", counted in
  `merges[].descriptions_kept_for_answered_terms`, not `descriptions_kept`. `totals.need_one_word` counts the terms
  not drafted until given as one word (`ask`).
- **(c14) `decide` says what the record holds and what it answers.** The kept-request reply names the allowed value
  a scientist's decision already gives the field ("the record keeps `surface_oxidation` meanwhile; ask whether that is
  acceptable until the term exists"), or says the field stays missing. A value decision that leaves an open request
  answered (read as `propose-terms` reads it) adds "This answers your request for 'oxidation' (vr-…); it is no longer
  drafted" (or what still drafts it) and `answers_requests`.
- **(c14) Adopting a sheet again.** A Disagreements row whose field a scientist's confirming decision already gives
  an allowed value for every run it names (a whole-beamtime row: every target its answer reaches) is SETTLED (c14g)
  only when, for every run, that value equals the sheet's or was recorded by a ruling on the same disagreement in an
  earlier import of this sheet (the decision's note names "ruling on disagreement Dn: <their file> <their cells> =
  <their value>", and (c14h) their cell still holds that value: a cell edited since, or a note without the value,
  awaits a ruling; `template import` reads their value from the `_isaac` sheet, never the editable column D). (c14k)
  That ruling may be ANY decision of the unbroken same-value run ending at the decision that governs: walking back
  through the decisions on the target (for a candidate, those naming it and its conflicts, in decision-log order, as
  the governing decision is chosen) while each confirms the same value; a different value, a reject or a defer ends
  the run, and the row awaits a ruling again. A ruling that keeps the value already recorded, but is not in that run
  as a ruling on their cell as it reads now (c14i), is recorded again with the same value (`rulings_tied_to_sheet`;
  the summary counts them among the decisions recorded: "N decision(s) recorded, including 1 ruling cell that kept
  the same value and is now tied to your sheet (9 targets)", and never lists them as replacing or contradicting a file
  reading), so adopting this sheet again reads it as ruled until a different value, a reject or a defer is recorded;
  the same workbook imported again records nothing more. Two sheets of theirs ruled the same value each tie once and
  both stay settled: a later tie extends the run, it never replaces the earlier ruling. (c14j) Only a ruling made
  against a decision of that run is tied: adopt keeps, per Disagreements row, the decisions it read (`_isaac`
  `governing_decisions`, every target a whole-beamtime row reaches; with the column there, a damaged value is never
  tied). A workbook adopted with nothing recorded for the target is tied when every decision recorded on it since is
  of that run (both sheets adopted first, then imported in either order, settle both with no extra round); never when
  a different value, a reject or a defer came between. A workbook adopted before that column existed is tied only
  when it was adopted at or after a decision of the run (by its `exported_utc`; an unreadable time never ties). A
  ruling on a workbook adopted before the run began records nothing and is listed apart (`stale_rulings`: "ruled on a workbook adopted
  before d-000N, and a different value was recorded since (d-000M); nothing is recorded for this ruling: the value
  is already 12; adopt again to settle this row", with no command to record a value already there), never as
  "already recorded". (c14l) Adopt also keeps the decision log's length (`_isaac` `decisions_at_adopt`), so
  "recorded since" is a place in the log: a reject, a defer or an off-list value recorded before the adopt never stops
  a tie, and a reason says "since" only when that place (or, for a workbook without it, a readable time strictly after
  the workbook's) proves it. With `--supersede`, a ruling giving a different value is recorded over the value that
  governs only when it was made against it (a decision of that run was among those its row read, or nothing was
  recorded on the target since the adopt); otherwise it is listed in `stale_rulings` ("… this ruling was made against
  an earlier value, so nothing is recorded for it, even with --supersede …"), so two workbooks ruling different values
  never flip the value at each import. The report lists them under "Cells not tied to your sheet" and the summary
  says "N cell(s) not tied to your sheet (nothing recorded)" (rulings and adopted cells alike); each reason says why. A damaged
  `governing_decisions` list (any element that is not a decision id) is never tied. A ruling takes its target from a
  File List cell giving the same value.
  (c14m) **The rule.** A ruling is made against the value recorded now when one of the same-value run that governs
  now is among the decisions its row read at adopt (`governing_decisions`), or was recorded from this very workbook
  (adopt writes a random `_isaac` `adopt_id`, and each ruling's note ends with "(adopt id <id>)" after its provenance,
  so a scientist correcting their own ruling supersedes it; another adoption of the same sheet has another id), or
  nothing was recorded on the target since the adopt (a ruling that keeps the value: nothing but that run). Only then
  is a same-value ruling tied, or a different value recorded with `--supersede`; otherwise the ruling is listed in
  `stale_rulings` with its reason ("your earlier ruling on this row (d-N) is what is recorded now"; "made before d-N
  recorded the value now, so it never saw it" for a workbook adopted with nothing recorded), which ends with the
  command that records it directly (`isaac bundle decide <bundle_dir> --target <id> --decision correct --value=<v>
  --by "<your name>"`, so a value starting with "-" is never read as an option; for a per-run answer slot the import
  added, `--question <id> --only run:<run id>`, which `decide` takes for a question asked once for the beamtime;
  adopting again also works), as every clash reason does. "Since" is a place in the log, trusted
  only while the log's first `decisions_at_adopt` decisions hash to the `_isaac` `decisions_fingerprint` (sha256 of
  each one's `decision_id`, `decided_utc`, `target`, `decision` and `value` as canonical JSON); a copied, restored or
  forked bundle (same `bundle_id`, decision ids that repeat) fails it, and the workbook is unplaceable: nothing of it
  is tied or recorded over another value ("this bundle's decisions changed since the workbook was adopted (copied or
  restored?); adopt again"). A ruling cell is all or nothing: when any target it reaches is stale, none is recorded
  and every one is listed. A workbook without the fingerprint or the adopt id is read as before (a fingerprint row
  kept with a blank value is unplaceable). (c14n) A decision carrying this workbook's adopt id counts only when the
  same person (`--by`) recorded it: a copy of the workbook shares its id, so a colleague's ruling on a copy is listed
  in `stale_rulings` ("Name's ruling on this row (d-N), from another copy of this workbook, is what is recorded now").
  An adopted File List answer cell is held to the same rule: with `--supersede` it records over a different value
  only when its workbook is placeable and the decision governing now is one it saw at adopt (`_isaac` `[adopted]`
  `governing`; a workbook without them, by its place in the log), its own, or nothing was recorded on the
  target since the adopt; otherwise it is listed in `stale_rulings`. A cell not adopted from their sheet (one of a
  template never adopted, or typed into an empty cell) records with `--supersede` as before.
  (c14o) Every gated cell (a ruling, or an adopted File List, Campaign Info or Technique answer cell, a Technique cell
  being one per File List row) is all or nothing: when any target it reaches is stale, or clashes (a different value
  from an earlier decision without `--supersede`, or from another cell of this workbook), none is recorded and every
  one is listed (`stale_rulings` or `clashes`), naming the target that stopped it. `--by` is compared stripped, as a
  decision stores it. One person importing two copies of one workbook that rule differently, each with `--supersede`
  and the same `--by`, alternates the value at each import, as intended: each import is their own correction of the
  value their last one recorded. (c14p) A target that already holds the ruling's value never holds back the rest (it
  is listed: "the value is already X; adopt again to settle this row"); a cell held back with another target's clash
  is listed with `blocked_by` naming it, and the summary counts those apart from the clashes. An adopted cell, never
  a ruling, is "this cell", and is settled by adopting again then importing with `--supersede`; a target of one that
  already holds its value is listed with just "the value is already X" (no "adopt again to settle this row", which is
  a ruling's). (c15a) A clash that `--supersede` would record is said so only when every clash of its cell is one: when
  another target is unseen or split, the line says `--supersede` records none of the cell's targets, and why. A target
  that already holds the value is not counted as held back in the summary. The rule is
  asymmetric on purpose: an adopted Campaign Info cell is all or nothing, while the same cell typed into a template
  that was never adopted is not gated and records target by target, as before.
  Settled, it says "already recorded: <value> (<date>); leave blank to keep" (the adopt result's `already_recorded`,
  counted apart in the summary); otherwise it awaits a ruling and says "recorded `12` (date); your sheet says `2`:
  rule which" (`recorded_note`). An Electrolyte row stating a concentration is settled only when the name and the
  concentration are; with the name alone, the name is listed as recorded and the concentration awaits a ruling
  (`awaiting_ruling`, column J). With `--by`, a sheet word whose cells or runs changed is kept again only for the runs
  no request for the same word answered since, citing only their cells (c14h); `template import` lists such a row
  left blank under `disagreements_already_recorded`, never `awaiting_ruling`, and records nothing for it. A sheet word
  whose request (the one kept earlier, or with no `--by` any request for the same field and word) was answered since
  says "The sheet still says … answered since with …" with or without `--by`; one answered for every run
  (`every_run`) is listed apart (`vocabulary_requests_not_kept.answered_since`), never as a word to keep or draft. The
  import summary says "N decision(s) (from M cell(s)) already recorded".
- **(c15b) A ruling the row asked for; one line and one command per cell.** Adopt keeps, per Disagreements row, the
  fields whose recorded values its statement named (`_isaac` `recorded_shown`, a JSON list). A ruling giving such a
  field a different value is recorded over the value that governs WITHOUT `--supersede` when it was made against it:
  the workbook is placeable (c14m) and one of the same-value run governing now is among the decisions the row read at
  adopt (`governing_decisions`). It is listed in `rulings_over_the_value_recorded` ("Rulings … over the value recorded
  now"). A row that did not name the value (a whole-beamtime row where some runs held nothing), a workbook without the
  column, a decision recorded since the adopt, a copy of the workbook (c14n) or a correction recorded from this same
  adoption still need `--supersede`, and every c14l-c14p rule (stale, all or nothing, never flipped by two adoptions
  or copies) is unchanged. Every clash reason says what is recorded now, by whom, when and from where ("recorded now:
  '12' by Name (2099-01-01), from a decide | a template import | another adoption | an earlier import of this workbook |
  another copy of this workbook"); no reason names a decision id (entries keep `decision_id`, `existing`). The text
  report prints clashes and cells not tied to the sheet one line per cell (`clashes_by_cell`, `stale_by_cell`: targets,
  runs, clashes, held back, already holding the value, the cell's reason and ONE `decide` command naming every target
  that does not hold it; `decide` takes `--target` once per target), and the summary counts clashes by cell ("2
  cell(s) clash (286 target(s): …)"); a per-target reason of a cell reaching several targets ends by naming that
  command, never its own. A target already holding the value, in a cell another of whose targets still holds a
  different recorded value, is not told adopting again settles the row. `decide` on a target whose governing decision
  came from a ruling that reached several targets (the same note and `batch_id`) warns when that ruling's other targets
  still hold another value (`same_ruling_left`); nothing else ties targets to one sheet row, so nothing else is said.
  A re-adopted row says, when its runs hold different values, how many hold each ("recorded `-0.8` (8 runs), `-0.6` (1
  run)"). A ruling note from a build before c14h (provenance, no value, no adopt id) settles its row at adopt, which
  says so ("by your ruling on this row from an earlier build …"); it is never read when tying or superseding. Adopt
  says when Campaign Info still reaches the runs on none of their rows, and names `--by` in its next command; an
  `--apply` that records nothing says "Nothing new recorded"; the same sheet's off-list word adopted under another
  `--by` is not kept twice (a request keeps one name; the bundle schema has no second), and `propose-terms` counts an
  older duplicate of one sheet's cells once.
