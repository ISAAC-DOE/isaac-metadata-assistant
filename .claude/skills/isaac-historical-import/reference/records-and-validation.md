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
  type or control mode. It quotes what the file names state (`10MNaOH`). Ask each field it names: a name that gives
  no value fills nothing.
- **A name stating open circuit** (`OCV`) warns until the control mode is confirmed.
- **Start time left out**: see `start-times-and-clock.md`.
- **Portal warnings** (`portal_warnings`: a deprecated cell type, no data owner) never change a verdict, but are said.
- **`pending_vocabulary`**: a field still missing because the scientist's word waits on a vocabulary proposal. When
  the group is exportable, its statement adds "this does not block export; the record is
  written without it". Say that, never as a block.
- An unknown temperature is written as "not reported". Never press for one and never default one.

Re-importing to fix anything starts with no answers: decisions and filled sheets do not carry over. Do not suggest it.

## The end review (Step 10)

Read this at Step 10. The owner's direction: the scientist reviews the final records, not each value as it is found.

`<isaac> bundle review <bundle> --json` (after `build-records`; it reads only):

- `fields[]`: every value a rule filled that the built records carry and nobody has reviewed, by field. Per value:
  `value_words` (with its unit, and a potential with its scale: "0.06 V vs RHE"), `values` (how many runs' values) and
  `records` (how many records carry it) — say both words; `rule` (why, in plain words); `witness` (what shows it: the
  beamtime folder's name for the facility, organization and group, a header line only when it names them; "read from
  N of the beamline's own acquisition files" for the domain; a header number said as what its motor is; otherwise the
  shortest quote, `by` saying whether the files or a Claude reading); and for the environment `convention` (their
  answer, how many measurements it was given for, how many it reached). Each value also has its `colour` and `kind`:
  `guess` (yellow: your inferred reading, its witness the quote it rests on), `deduction` (yellow: a rule worked it out
  from other values, the group from the folder's PI or the organization from the facility, or the environment the
  convention reaches) or `read` (green). `values_by_kind` counts them.
- `scan_decisions[]`: per record, the scans the processing rule kept and dropped, each drop with its reasons, and the
  curve's plot file. Read from the stored results; open a plot with Read if they ask.
- `reviewed_earlier`, `reviewed_changed_since`: values reviewed before, and reviewed values whose value, rule or
  evidence changed since: `listed_again` (filled again, in the listing), `filled_outside_records` (filled again, in no
  built record yet) and `now_asked` (no rule fills them any more: they are back among the questions). An old review
  never confirms a changed value.
- `records_built_since_last_change: false`: the records changed since `build-records`. Build again first.
- `listing`: the digest of exactly what is listed. The accept command in `next` carries it.
- No record built yet (no group confirmed): `next` says to confirm groups and run `build-records` first.

Show it in ONE message, by field, as a short list: "Environment: operando, in 12 records (you said such measurements
are operando; it reached 40 measurements)". **The guesses first, under their own heading** ("Guesses: my best reading
of your files, please check"), each with the quote it rests on; then the deductions; then what was read from the files.
Quote each witness. Say the scan drops with why. No ids, no rule ids.
Then ask: "Does all of this look right, or what should change?" A yes covers the guesses too: they turn green.

- **Yes:** run the command `next` gives: `<isaac> bundle review <bundle> --accept --by "<name>" --listing <digest>`
  shows what it would record; run it again with `--apply`. It records ONE review decision binding each listed value
  (its target, value, rule and a hash of its evidence), and only if the listing is still the one you showed: when the
  values changed since, it is refused ("the values changed since you were shown them"): run `bundle review` again and
  show the scientist the new listing. Each value is then confirmed by the scientist (basis `reviewed_final_records`).
  If any of them changes later it is filled again (or asked, when no rule fills it any more); `bundle status` says which.
- **Yes for some fields only:** `bundle review <bundle> --field <path> --field <path>` lists just those (one listing,
  one digest), and its `next` accepts just those: one decision. After an `--apply` the records changed, so run
  `build-records` again, then `bundle review` for what is left; never accept a second field from the first listing.
- **A change:** `decide --target <the value's id from the --json> --decision correct --value <their value>`, then
  `build-records` and `bundle review` again. A decision always wins over a fill and over a review. **A scan to keep or
  drop** instead of the rule's choice: Step 6.3 (`set_scan_decision`), re-process the group, show the new curve and
  approve it only on their yes; then `build-records` and review again.
- After the review: `build-records`, `validate` and `export` again, so the records carry the confirmation (an exported
  record that changed gets a new id; the old one moves to `isaac-export/superseded/`).
- Export never waits for the review: a value not yet reviewed goes out as inferred, naming its rule. Say so if they
  stop before reviewing.

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

## The upload dry run and the final check

`<isaac> bundle upload <records> --dry-run --bundle <bundle>`

**The final check comes first.** When any record carries a yellow value (a guess, or a value a rule worked out from
others, such as the group from the folder's PI or the organization from the facility, that the scientist has not
confirmed), the dry run lists them, by field and value, with how many records carry each and the quote or rule it rests
on, and sends nothing (exit 1, `sent: false`). Ask ONE plain question, its `question`: "These N values are my guesses
from your files or worked out by a rule (G guesses, D worked out by a rule). Send them as they are, or check them
first?" A record with no readable evidence file is listed too ("I cannot tell"): what it holds cannot be told.

- **Send:** the same command with `--guesses-ok <digest> --by "<name>"` (the digest it printed). It is refused if the
  list changed since you showed it. It records one `submit_with_guesses` decision in the bundle (who, when, the list):
  the values stay yellow there; the yes is the audit of what was sent unconfirmed.
- **Check first:** `bundle review` (Step 10), then build, validate and export again. An answer changes this list only
  after a new `build-records` and `export`; a yes to an older export is refused ("the records are older than your
  answers").
- The yes needs the bundle the records were exported from (`--bundle`): the export index must name it for every record
  with a guess, else the yes is refused. The same yes to the same list is recorded once.
- Say plainly: this only records their yes. **This build sends nothing**; they upload the records folder through the
  ISAAC portal themselves, and the portal does not run this check. The export index flags each record holding yellow
  values (`unconfirmed_values`). The portal copy will not show which values were guesses: the ISAAC record has no place
  for that note.

- Its `statement` leads with "N records, 2 requests each, to <portal>", then each note and portal warning once.
- `records` lists in full every record that replaces an earlier one and every one with a note of its own; of the rest
  the first 3, with `records_total` and `records_omitted` (`--full` lists all).
- Name each record's `replaces_record_ids` and read its `replaces_statement`: a record already uploaded stays on the portal.
- State plainly: nothing was sent, this build cannot send, the key was not read.
- Never ask for or print a portal key. The records are in `<records>`; the portal upload is theirs to do.
