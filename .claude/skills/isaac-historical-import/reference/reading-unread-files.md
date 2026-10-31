# Reading what code could not (Step 4)

`<isaac> bundle list <bundle> unread --limit 50 --offset 0` — each entry has `relative_path`, `source_id`,
`source_type`, `reason_code` and, for an Athena project, a short `read_by` marker (what it means is said once
on the page, in `read_by_note`). Work through them in this order, and tell the scientist which you are on.

1. **Logbooks, beamtime notes, proposals, spreadsheets that look like a sample list** (docx, xlsx,
   pdf, txt with prose). These hold sample names, conditions and who did what.
2. **Slides and reports** (pptx, pdf): figures and captions often state conditions.
3. **Images** (png/jpg/tif): open with Read; describe only what is visible; a plot is not a value.
4. Everything else last. Instrument binaries you cannot open are reported, not guessed.

## Tools

- Word/PowerPoint/Excel: `<python> -m isaac_api.local_import.extract <file> --root <folder> --out <bundle>-notes/extracted`
  (or `--from-bundle <bundle>/unread_files.json --root <folder> --limit 20` for a batch). It prints a compact
  JSON manifest and writes what it read under `--out`: a document's text in reading order (tables as rows)
  in `text_file`, each sheet's rows (the first 50, the bound is stated) in that sheet's own `text_file`
  (`row 3: a | b | c`), every embedded image with its position, alt text and caption, and counters for
  anything cut. Read each text file it names (the path is printed as it opens); open images with Read.
  An `--out` inside `--root`, inside the file's own folder, or inside a bundle is refused (exit 3).
- **A cut sheet is not read; page it.** A sheet past the preview bound has `preview_rows_not_returned`
  and a `read_rest` with the exact command for the next page (it starts with the interpreter that ran it):
  `<python> -m isaac_api.local_import.extract <file> --root <folder> --out <dir> --sheet "<name>" --rows-offset 50 --rows-limit 50`.
  Each page goes to its own text file (`sheet-01-rows-51-100.txt`).
  Run it until no `read_rest` is left before you say what the sheet holds; the last rows are often
  where the errors are. `--show-limits` prints every bound (left out by default).
- PDFs: Read with a page range of at most 20 pages (`pages: "1-20"`). The manifest lists ranges.
- Plain text: Read directly (use offset/limit for long files).
- Never run or open a file with any other program. Macros and scripts are only ever read as text.

## Read everything, not only the unread files

The files code DID read still hold statements no parser maps: readmes, macro comments
(e.g. "wait while running CVs" says the cell was under potential control), SPEC `#C` lines, the
run labels and folder names. Read those too. A document beside the folder (a proposal, slides) is
outside what the scientist approved: name it and ask before opening it.
Look hardest for what the files most often leave unstated: facility and beamline, environment
(operando / in situ / ex situ), cell type, reaction, electrolyte (name and concentration), pH,
potential scale (RHE, Ag/AgCl, ...), the potential set-point (volts), sample form and formula,
the absorbing element and edge, and who produced the data.

## Recording what you found: one findings file

Write every finding to ONE JSON file (`isaac.reading_findings`) in a working folder beside the bundle
(never inside it), then load it in one step:

```json
{"format": "isaac.reading_findings",
 "findings": [{
   "field_path": "context.environment",
   "value": "in_situ",
   "applies_to": {"scope": "runs", "runs": ["<the run's stem, as `bundle list <bundle> runs` prints it>"]},
   "source": {"path": "<relative to the imported folder; ../<name> only for a file beside it the scientist let you open>", "locator": "line 65"},
   "quote": "<verbatim, at most 25 words>",
   "strength": "stated | inferred",
   "reasoning": "<why the quote supports the value; the one inference step, if any>"}]}
```

- `stated`: the file says it. `inferred`: ONE written step from what it says. Nothing from
  what a lab "usually" does. A name in a file or folder name is evidence; say it is a name.
- **Naming runs.** `runs` takes each run's `stem` (the file name the scientist knows) or its `run_id`,
  both printed by `<isaac> bundle list <bundle> runs`; where two runs share a stem (the same name in
  two folders) the row also prints `path`, and that path or the `run_id` names one of them. Never use
  `label`: it reorders the name's tokens and drops some, so two runs (`_12_1200mV`, `_1_1200mV`) can
  share one. A reference that names more than one run is skipped, never spread over both. (An older
  findings file's `run_labels` is still read, with the same rule.)
- `"scope": "runs"` whenever the statement is about particular samples or conditions;
  `"experiment"` only when the source says it of the whole beamtime. Two files that disagree:
  write both findings and tell the scientist. Never pick one.
- `field_path` is the FULL path, as `bundle questions` prints it. Where and by whom: the facility is
  `system.facility.facility_name`, the beamline `system.facility.beamline`, the endstation
  `system.facility.endstation`, the site `system.facility.site`, the facility's organization
  `system.facility.organization`; who produced the data is `attribution.produced_by.group` and
  `attribution.produced_by.organization`. A short path (`facility.beamline`) is skipped, and the skip
  names the path it most likely meant (`did_you_mean`): fix the file and load it again.
- Vocabulary fields take one allowed value (see `bundle questions` → `allowed_values`).
- For `context.electrochemistry.electrolyte` give the whole statement ("0.1 M KOH"); it is
  offered on both the name and the concentration for the scientist to split.
- `context.electrochemistry.potential_setpoint_V` is a NUMBER in volts on the run's potential
  scale (`-0.8`, not `"-0.8 V"`; "100 mV" is `0.1`, one written step, so `inferred`). It lands on
  every named run whose files state no potential, and beside the parsed one where they do.
  Look for the scale too (`context.electrochemistry.potential_scale`): a set-point reaches the
  record only beside the confirmed scale of every run it comes from, so a bare number is listed
  as not composed.
- `context.electrochemistry.current_setpoint_mA_cm2` (a galvanostatic run's set-point) is a NUMBER,
  a current DENSITY in mA/cm², exactly as a file states it (`-10`, not `"-10 mA/cm2"`). A total
  current ("5 mA") is not one: never divide it by an electrode area — write no finding for this
  field and tell the scientist what the file says. It needs no scale beside it.
- The absorber has no record field: write `system.element` (a symbol, e.g. `Fe`) and
  `system.edge` (exactly `K`, `L1`-`L3` or `M1`-`M5`) as two findings. They are recorded on the
  record GROUPS holding the named runs (every live group for `"experiment"`). Before Step 5 the
  preview skips them ("no live record group yet"): apply the same file again after grouping
  (re-applying adds only what is new). They feed the absorber question in Step 7 as AI
  suggestions beside any file evidence. After a `--regroup`, apply it again for the new groups
  (the earlier readings stay on the replaced groups and are not moved). A `"runs"` finding on a
  group with other runs says which runs it was read for; tell the scientist.
  A value of another shape is skipped, never normalised. A reading that differs from the files
  is shown as differing; only the scientist's `set_absorber` answer gives the absorber.

Then:

```
<isaac> bundle annotate <bundle> --from-readings <findings.json> --model <your model id>          # preview
<isaac> bundle annotate <bundle> --from-readings <findings.json> --model <your model id> --apply
```

The preview lists, per finding, how many targets it reaches and every finding it could NOT place
(no such field in this bundle, a run reference that does not exist or names more than one run): fix
those or tell the scientist.
Each reading is an AI interpretation: cited, `needs_review` at most, never eligible on its own.
The questions in Step 7 show it as a suggestion beside the question; the scientist's answer is
what counts. Re-applying the same file adds nothing. Never present your reading as confirmed.
