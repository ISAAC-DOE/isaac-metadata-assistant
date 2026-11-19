# Build, validate, export (Steps 8–9)

Read this at Step 8. The section "Reading summary.md" is for Step 2.

## Reading summary.md (Step 2)

- Do not quote its "Questions: N" (fine-grained items) or its "Run groups" (file-name groups, not records).
- The brackets after "Conflicts: N" say how many are real disagreements about a value and how many are something
  else (about files, or already decided). Say that split in words.
- The question count comes in Step 7 (`bundle questions` → `counts`).

## Build and validate

`<isaac> bundle build-records <bundle>` writes one draft per confirmed group and lists every required value nobody supplied.
`<isaac> bundle validate <bundle>` runs every check on each draft: the draft checks, an export dry run, the official
schema, and the offline portal check.

The reply of `validate` opens with:

- `exportable` / `not_exportable`;
- `by_reason`: verdicts and processing blockers, counted;
- `missing_required_by_field`;
- `not_exportable_first`: three groups with their plain reasons and the schema's first message;
- then `verdicts`, and `warnings`.

Explain the counts first ("all 78 lack the producing group; 70 wait for a curve approval; 5 have no protocol").
Open `validation/<group id>.json` only for a group those leave unexplained.
`nothing_validated` means no group is confirmed yet: go back to Step 5.

### Verdicts, in plain words, and the fix

| Verdict | Tell the scientist | Fix |
|---|---|---|
| `incomplete` | "These required facts are still missing: …" | answer the blocking questions (Step 7). `measurement.series`, `measurement.qc.status` and `descriptors.outputs` are missing until the group's curve is approved: the file's `processing_fix` says so, and the fix is Step 6. `processing_fix` is a template: never run it as it is |
| `invalid_official` | "A value is in the wrong form: …" (quote `first_official_error`) | correct that value |
| `portal_check_unavailable` | "The offline portal check is not installed, so this cannot count as ready." | `scripts/install_portal_validator.sh`, then `validate` again |
| `portal_check_degraded` | "The portal check ran only partly, so this cannot count as ready." | re-install the validator; if it persists, report it |
| `portal_hold` | "The portal would hold this record for a warning: …" | explain the warning; ask whether to fix or leave unexported |
| `portal_reject` | "The portal would reject this: …" | fix the stated value or leave it unexported |
| `exportable` | "Passes every check." | export |

**Record completeness** (`record_completeness`, gate `isaac.local.record_completeness.v1`) is a local gate beside the
verdicts and never changes one. A condition grouping used to keep two records of one sample apart (the potential,
the cycling history, the filter, which electrode) must be in the record or declined (`reject`) before `export` writes
it; two records that would say the same thing are held too.
- `validate` gives `ready_to_export`, what is open and `answer_first`. `bundle questions` lists those questions right
  after the blocking ones (each has `completeness`).
- `export` lists a held record under `refused` with `verdict: held_by_record_completeness` and
  `official_validation: passed`. Say "it passes validation but would be written without its potential" (or "these N
  records would be indistinguishable") and ask the question it names.
- Only when the scientist says to export anyway: `export --allow-indistinguishable --by "<name>"`. That is recorded
  in the bundle, so later exports keep those records.

Exit 1 from `validate` means at least one draft is not exportable. That is information, not an error.
After a fix, run `build-records` then `validate` again. Never hand-edit a draft or an evidence file. Never relax a check.

### Required because of another field

- An electrolyte name makes its `concentration_M` required (`required_because`).
- A potentiostatic record whose set-point is confirmed but whose potential scale is not: the set-point goes in only
  beside its scale, so the scale is listed as missing, never the set-point already answered.
- A set-point nobody answered lists its scale as missing too. Ask both at once.

### Warnings: a record can be exportable and still lack what defines it

A warning is not a refusal. It names something the record will be written without. Say each kind in words, with its
count, and ask the question it names. Its command is a template: run it only with their answer.

- Only the first 5 are printed, exportable groups' first (`group_exportable`), the serious ones first. `warnings_total`
  counts them; `warnings_full_list` says how: `validate --full` lists every one.
- **A potential the file names state** (`400mV`, `m800mV`) that the record will not carry until its scale is confirmed.
  When no set-point was read either, the warning names both (`also_needs`, `also_command`): ask the set-point in volts
  and the scale together.
- **`potential_sources_disagree`**: the run's name and its scan header write different numbers on the same scale. The
  scientist settles it. A scale missing on one side may be one potential on two scales: ask which applies.
- **`macro_setpoint_unanswered`**: a macro and a file name state different set-points. Ask the question it names.
- **`in_situ_conditions_not_in_record`**: an in-situ or operando electrochemical record carries no electrolyte, cell
  type or control mode. It quotes what the file names state (`10MNaOH`). Ask each field; nothing is filled from a name.
- **A name stating open circuit** (`OCV`) warns until the control mode is confirmed.
- **Start time left out**: see `start-times-and-clock.md`.
- **Portal warnings** (`portal_warnings`: a deprecated cell type, no data owner) never change a verdict, but are said.
- **`pending_vocabulary`**: a field still missing because the scientist's word waits on a vocabulary proposal. When
  the group is exportable, its statement adds "this does not block export; the record is
  written without it". Say that, never as a block.
- An unknown temperature is written as "not reported". Never press for one and never default one.

Re-importing to fix anything starts with no answers: decisions and filled sheets do not carry over. Do not suggest it.

## Record shape

When the scientist asks "what should this record hold?", answer from the upstream record contract, not from memory:
`~/.cache/isaac/portal-validator/<sha>/src/data/record_contract.json` and the wiki page "What an ISAAC record is".
One record is one result: one sample, one measurement, one set of conditions, the values it produced, the work they come from.

A record of an approved curve carries:

- the normalised curve and the merged raw average it was normalised from;
- the processing steps that were applied (alignment, merging, normalisation);
- the edge position (E0) as its one descriptor; the edge step is in the notes;
- in its evidence file, a `processing` block: the energy reference, each scan's shift, each scan's keep or drop with
  who decided and why, the normalisation, the QC, and the processing files with their checksums.
  The same files are copied beside the record in `<ULID>.artifacts/`.

`validation/<group>.json` also holds `website_schema` and `schema_drift`. They are for information only and gate nothing.

## Export

`<isaac> bundle export <bundle> --out <records>` writes `<ULID>.json`, `<ULID>.evidence.json` and `<ULID>.artifacts/`
for exportable drafts only.

- **Read `outcome`, never the exit code.** It exits 1 whenever any group is refused, even when it wrote records.
  `outcome`: "N record(s) ready (U unchanged since their export, W written), refused M group(s)".
- `records_ready` = N. `records_written` = W: new or replacing records only. When W is 0 say "nothing new was written".
- Do not read the `outcome` string out; it is long. Say: how many are ready, how many were refused and why
  (`refused_by_reason`, `missing_required_by_field`; `refused_every_summary_says` holds what every refused row repeats),
  then each warning kind with its record count ("87 records are written without their potential").
- Warnings by kind: `warnings_by_code` says each warning code once (records, variants, one example, the question to
  answer); relay those. `upload --dry-run` does the same in `notes_by_code`.
- Warnings: `warnings_by_text` and `portal_warnings` say each one once with its record count; a warning on SOME of the
  ready records lists every one of their `group_ids`. `exported[].warnings` lists a record's own;
  `records_written_with_warnings` counts those written now, `records_ready_with_warnings` every ready one.
- The reply lists in full every refused, withdrawn, replaced or restored row. Repeated ok rows are cut to the first 3
  (`exported_shown`, `exported_omitted`). `schemas_used` is said once at the top. `export --full` names every row.
- Each row has a `label`: the group's first file. Use it to name the record.
- **Exporting again is safe.** An unchanged record keeps its id (`export: unchanged`; `evidence_refreshed` when only
  its evidence file was rewritten). A changed one gets a new id and the old one moves to `isaac-export/superseded/`
  (`export: replaced`). One whose group is no longer exportable moves to `isaac-export/withdrawn/`. Say which.
- A confirmed follows label becomes a link in the later record. When the earlier record is not exported, the later
  one is written without the link and says so.
- In the evidence file, a `#D` local clock time beside the UTC start has `relation: not_comparable` until the clock's
  zone is stated. It is never a contradiction.

## The upload dry run

`<isaac> bundle upload <records> --dry-run`

- Its `statement` leads with "N records, 2 requests each, to <portal>", then each note and portal warning once.
- `records` lists in full every record that replaces an earlier one and every one with a note of its own; of the rest
  the first 3, with `records_total` and `records_omitted` (`--full` lists all).
- Name each record's `replaces_record_ids` and read its `replaces_statement`: a record already uploaded stays on the portal.
- State plainly: nothing was sent, this build cannot send, the key was not read.
- Never ask for or print a portal key. The records are in `<records>`; the portal upload is theirs to do.
