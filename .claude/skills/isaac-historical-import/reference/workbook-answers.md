# A filled question workbook (`bundle answers import`)

The question workbook is the spreadsheet of ISAAC questions a scientist is sent: one tab per kind of
question, a header row, an `ISAAC question ID` column and a yellow **YOUR ANSWER** column. When it comes
back filled in, read it back with:

`<isaac> bundle answers import <bundle> <workbook.xlsx> --by "<name>" [--orcid <id>] [--folder <name> [--folder-differs-ok]] [--supersede] [--apply] [--json]`

It works on ONE bundle: a row is this bundle's when its `Folder` is the folder the bundle records.
Rows of other beamtimes are counted, never read; run it once per bundle. An id row (or Athena row) whose
Folder cell is blank is no bundle's: it is listed (`blank_folder`), not read; a free-text row with no
Folder (a rule) is every bundle's. `--folder <name>` must be a folder the workbook names (else exit 3),
and when it is not the folder the bundle records it is refused (exit 2) unless the user confirms the rows
are this bundle's with `--folder-differs-ok`.

## The order, always

1. **Copy the bundle** (`cp -R <bundle> <copy>`) and preview against the copy. Preview is the default and
   writes nothing, not even a lock file: every decision is dry-run through the decide path on a temporary
   copy of `bundle.json`.
2. **Apply to the copy** (`--apply`), then show the scientist (or the user who sent the workbook) what it
   planned and recorded: counts by tab, every decision, everything not applied, every free-text row.
3. **Apply for real only on the user's word.** `--apply` refuses a bundle inside any folder whose name
   starts with `_runs` (exit 4, nothing recorded): those are the protected real bundles.

A second `--apply` records nothing new (every decision is `unchanged`; an off-list word only re-stamps
the request it already kept, as `decide --as-said` does). `bundle check <bundle>` stays valid.

**A decision recorded since the workbook was made is never replaced silently.** The workbook carries no
bundle id or decisions fingerprint, so every target is checked: when the decide path would record a
workbook answer on a target that already holds a DIFFERENT scientist decision, that row is refused
(`refused_replaces`) and the existing decision is named (who, when, what, its id). Ask which holds.
`--supersede` records the workbook's answer over it, and the report says `REPLACED a later decision: …`.

## How a cell is read

| The cell | What is planned |
|---|---|
| blank | nothing. A blank row is never inferred, never filled from a neighbour |
| `yes` / `ok` (any case) | accepts the suggestion SHOWN on that row: `confirm` when it is the files' own value now (and the question allows confirm), else `correct` with the shown value, but only when that value is exactly one ISAAC offers for the question now (a hint literal, its suggested value, or a "sets X = …" proposal's own value). A proposal that "confirms the value the files give" is only ever a confirm, refused (`stale`) when the files now give another value. Anything else (stale, or text with commentary) is not applied: "type the value itself" |
| a typed value | `correct` with it, parsed as `template import` parses a cell (numbers as numbers, a temperature with its unit). A field with a list: the value goes through decide with `--as-said`, so a word off the list is kept as a vocabulary request in `--by`'s name, never recorded as a value |
| `no`, `?`, `unsure`, `don't know` | nothing; listed (`declined` / `unsure`). Never turned into a reject or a defer |
| a placeholder: `-`, `—`, `none`, `TBD`, `n.a.`, `not applicable`, `unknown` … | nothing; listed (`placeholder`): never a value, never a vocabulary request. On the Athena tabs `none` is a listed answer |
| a formula | nothing; listed (`invalid`) |
| `same for all` / `same as above` / `ditto` (in the answer or the notes) | listed under `same_for_all`, never expanded. Ask which rows they mean and answer those |

Kinds with their own answer words: element and edge (`Pt L3`, `Co K`; an element alone is not applied),
clock time zone (an IANA name, `set_clock_time_zone`), file-name numbers (`counter`, only when the
question asks about one position, then `<isaac> bundle group <bundle> --regroup`; `sequence`
→ `set_not_counter_positions`; anything else needs a person), merge or keep apart (`Keep apart` →
`keep_apart`; `Merge` → step 1 of a merge, then regroup and confirm the combined group), Athena versions
(`v01`, `v02` … → `select_athena_version`; `none` needs a person).

A **collapsed row** (a `G-…` id, whose Ref a per-record row names in `Covered by collapsed row`) answers
each per-record row it covers, citing the collapsed row's cell; `yes` accepts the value the collapsed row
shows. A collapsed row that shows no suggestion takes `yes` only where its Allowed answers say "each
record's own" value; otherwise its `yes` is listed, never spread onto the records' own suggestions. When
those records show different values it takes `yes` only. A per-record row with its own answer overrides
the collapsed row for that record (listed as `overridden`). The same question answered differently in two
cells of the same kind: neither is recorded.

Each decision is listed as the exact `bundle decide` it is (question id, `--field` for one field of a
several-field question, decision, value, note) with its outcome (`would_record` / `recorded`,
`unchanged`, `would_keep_vocabulary_request` / `vocabulary_request_kept`, `refused` with the reason). The
note cites the cell: `workbook <file> '<tab>'!<cell>`.

## Never applied: translate these with the scientist

- **Rules (`R…`), new questions (`N…`), rule proposals (`CR…`)**, and any answered row without an id:
  free text. Work out with the scientist which `decide` calls (or which params-file entries) each one
  means, say each back, and record it only on their yes. A rule never answers rows by itself.
- **Athena merges**: each row names a project file, an Athena group and the answer (a group id or run
  name, `yes` for the one near group shown, `no`, `none`). The report gives the params-file entry it
  reads as (`params_entry`) and the three shapes to use (`params_entries_to_use`):
  `{"athena_match": {"<group id>": [{"project": "<project file>", "athena_group": "<Athena group>"}]}}`,
  the same under `athena_match_not` (their "no" for that group), or `{"athena_ignore": [...]}` (no group's).
  Put the confirmed entries in one params file and run
  `<isaac> process <bundle> --source <folder> --params-file <file>`; keep passing that file (see
  `grouping-and-processing.md`).

## Not resolving

An id that no longer resolves in the bundle (re-imported, regrouped) is listed per answered row with the
reason, and counted per tab for unanswered rows (`id_rows.not_resolving_by_tab`). A row whose field is now
asked in its own question (e.g. a temperature row of a several-field question, now a per-group question)
is listed as `asked_elsewhere`, naming that question; it is not applied. Never re-import before
applying a workbook made from a bundle: its ids are that bundle's.

## Tabs

Tabs and columns are found from each tab's header row, never its title: `questions` (YOUR ANSWER and
an id column), `free_text` (YOUR ANSWER and Ref), `athena_merges` (Athena project and group columns),
`no_answer` (no YOUR ANSWER: ids counted only), `info` (no header row), and `unknown` (YOUR ANSWER but no
Ref and no id: listed in `unknown_tabs`, not read). Several-field optional questions take the field from
the row's own field path, else its Topic (a fixed, tested list); a topic it does not know is listed.

`scripts/scientist_workbook/` holds the checks behind this: `idcheck.py` (does every id still resolve),
`idcompare.py` (two idcheck runs, row by row) and `wbdiff.py` (two workbook versions, cell by cell).
