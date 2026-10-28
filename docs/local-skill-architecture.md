# Local-first import: architecture for developers

Record-shape guidance comes from the upstream record contract (`data/record_contract.json` in the pinned clone under `~/.cache/isaac/portal-validator/<sha>/src/`, and the wiki "What an ISAAC record is").

Companion to `docs/local-import-bundle-contract.md` (the machine contract), `docs/local-first-data-flows.md`
(which flows carry data where), and decisions `DEC-76`…`DEC-84` in
`docs/superpowers/plans/ISAAC_PRODUCT_DECISIONS.md`. Scientist-facing: `docs/local-skill-quickstart.md`.

## Shape

```
folder or ZIP ──isaac import──▶ bundle dir ──(group, process, annotate, decide)──▶ drafts ──validate──▶ records
   (local)        deterministic     JSON, not a record        local mutations            gates         export
                                         ▲                                                              │
                          Claude Code skill (instructions only) drives every command            upload: dry run only
```

Nothing is a server. The Claude Code skill (`.claude/skills/isaac-historical-import/`) contains no
code: it is instructions that call the `isaac` command and the extractor. Every state change goes
through a CLI command that validates before it writes; a person or model never edits JSON.

## Stages and commands

| Stage | Command | Module | Writes |
|---|---|---|---|
| read | `isaac import <folder> --out <b>` | `local_import/cli.py`, `bundle.py`, `historical_import.read_local_archive`, `local_import/readers/` | `bundle.json` + section files |
| read (unread files) | `python -m isaac_api.local_import.extract` | `local_import/extract.py` | manifests, text, images in a chosen folder |
| inspect | `bundle list/show/check` | `cli.py` | nothing (`show`/`list candidates` record an *exposure*) |
| cross-check | `crosscheck-plan`, `excerpt`, `annotate --blind`, `reveal` | `mutations.py` | `ai_interpretations[]`, `exposures[]` |
| group | `bundle group`; read with `bundle list <b> groups`, `bundle list <b> merge-candidates`, `bundle show <b> group <id>` | `grouping.py` | `record_groups[]` in `bundle.json` |
| process | `process <b> --source <folder>` | `local_import/processing/` | `processing_results[]`, `processing/<group>/` (plot, csv, qc) |
| ask | `bundle questions [--scope] [--blocking-only]` | `questions.py` | `questions.json` v2 (consolidated: experiment-scope questions asked once, run questions collapsed to groups, blocking first; each with plain text, why it blocks, hints, allowed values, the exact `decide --question` command) |
| decide | `bundle decide` (`--target`, `--targets-file`, or `--question Q [--only group:<id>] [--field <path>]`; `--qc-status`/`--qc-note` with `approve` on a processing result) | `mutations.py` | `scientist_decisions[]` (one per target, each listed) |
| compose | `bundle build-records [--test-marker]` (self-tests only: writes the fixed self-test marker into the series and QC notes) | `records.py` | `drafts/<group>.draft.json` + `.composition.json` |
| validate | `bundle validate` | `records.py`, `portal.py` | `validation/<group>.json` |
| export | `bundle export --out <r>` | `records.py` | `<ULID>.json`, `.evidence.json` (exportable only) |
| upload | `bundle upload <r> --dry-run` | `records.py` | nothing; no network, key not read |

`scripts/setup_isaac_local.sh` installs it; `scripts/isaac_selftest.sh` runs the whole chain on the
synthetic `multi_operator_corpus` with decisions labelled `SYNTHETIC SELF-TEST (not a scientist)`.

## Bundle sections (see the contract for fields)

`generator`, `source_root`, `sources[]`, `unread_files[]`, `experiment`, `samples[]`, `runs[]`,
`contributors[]`, `naming_profiles[]`, `candidates[]`, `conflicts[]`, `missing_values[]`,
`unmapped_statements[]`, `extended_context[]`, `data_quality_notes[]`, `questions[]`,
`ai_interpretations[]`, `scientist_decisions[]`, `record_groups[]`, `processing_results[]`,
`exposures[]`, `validation`, `readiness`, `counts`, `bounds`, `authorities`.

## Four authorities (never blended)

1. **Source evidence**: what a file literally says, at a locator.
2. **Extraction / interpretation**: deterministic readers, stored rules, AI readings (never above
   `needs_review`; `derive_value_state`).
3. **Scientist confirmation**: only `scientist_decisions[]`, identity `local_unverified`; ORCID is a
   claimed credit value.
4. **Deterministic validation**: `validate_draft`, the export dry run, `validate_official` and
   `check_exactness`, and the pinned portal validator. A value is `exportable` only when all pass.

## Validation gates (DEC-76)

Per draft, `bundle validate` runs: draft no-guessing checks → export dry run (`isaac_records.export`)
→ the official schema and exactness check → the **offline upstream portal validator** pinned at
`a1cb1c8` (isolated interpreter, `scripts/install_portal_validator.sh`). Every report names which
schema each verdict used: the vendored v1.05 schema stays the website's authority, the pinned
upstream schema is what the portal enforces. Where they disagree, the verdict is
`invalid_official` or `portal_reject` with the validator's reason, and the `schema_drift` block in `validation/<group>.json` says where the two schemas differ (information, not a verdict); nothing is defaulted to pass. An
absent or partly running portal check is `portal_check_unavailable` / `_degraded`, never a pass.
Verdicts: `incomplete`, `invalid_official`, `portal_check_unavailable`,
`portal_check_degraded`, `portal_hold`, `portal_reject`, `exportable`.

## Data flows (`docs/local-first-data-flows.md`)

A: ISAAC code on the laptop, nothing leaves. B: anything Claude opens or sees in a command's output
goes to the Claude service (the skill asks first; without consent it runs `isaac import` only). C: MCP
transfer to ISAAC is design-only. Upload is disabled (DEC-80).

## Honesty properties worth keeping under test

- QC status is the scientist's: `approve` takes `--qc-status` from the pinned vocabulary; `warn` never auto-maps.
- Consolidated questions never suppress a difference: a field the bundle records with different values per group is asked per group, and hints are labelled hints.
- `--test-marker` is for `scripts/isaac_selftest.sh` only; the skill forbids it with a real scientist.
- `apps/api/tests/test_local_skill_files.py` checks every command and flag the skill names against the live `--help`.
- `import` writes no absolute path unless `--record-local-root`.
- `annotate --blind` is honoured only when no command has printed the target's value.
- Bulk `decide` refuses values with no source evidence; a conflict or missing value needs `--value`.
- Without an approved processing result a draft has no spectrum and stays `incomplete`.
- `export` writes only `exportable` records; `upload` without `--dry-run` exits 2.

## Extension points

- **New beamline or format reader.** Add `local_import/readers/<name>.py` with `READER_ID`,
  `PROFILE_ID`, `READER_VERSION`, `sniff(path)`, `read(path)` and `collect_from_files(files, limits,
  claimed) -> ReaderResult` (literal parsing only; flag anomalies, never repair; record locators).
  Register it in `readers.READERS` at the right precedence (specific before general). Add synthetic
  tests including near-miss sniffing. Output is a `GenericRun`; the importer turns it into runs and
  evidence without a second pipeline.
- **New naming/convention profile.** `bl15/` naming profiles and convention rules (`--profile`).
- **Processing protocol.** `local_import/processing/`; protocols are versioned
  (`isaac.xas.v0`, `draft_unreviewed`); a new protocol needs a new id and a recorded review status.
- **Skill.** Edit `.claude/skills/isaac-historical-import/SKILL.md` and `reference/`; keep SKILL.md
  short and put detail in `reference/`. Re-run `scripts/setup_isaac_local.sh --install-skill` to
  refresh the installed copy (it replaces the copy, never links).
