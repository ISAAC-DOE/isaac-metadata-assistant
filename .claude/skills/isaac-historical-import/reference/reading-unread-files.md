# Reading what code could not (Step 4)

`<isaac> bundle list <bundle> unread --limit 50 --offset 0` — each entry has a path, a reason code and
`source_type`. Work through them in this order, and tell the scientist which you are on.

1. **Logbooks, beamtime notes, proposals, spreadsheets that look like a sample list** (docx, xlsx,
   pdf, txt with prose). These hold sample names, conditions and who did what.
2. **Slides and reports** (pptx, pdf): figures and captions often state conditions.
3. **Images** (png/jpg/tif): open with Read; describe only what is visible; a plot is not a value.
4. Everything else last. Instrument binaries you cannot open are reported, not guessed.

## Tools

- Word/PowerPoint/Excel: `<python> -m isaac_api.local_import.extract <file> --root <folder> --out <bundle>/extracted`
  (or `--from-bundle <bundle>/unread_files.json --root <folder> --limit 20` for a batch). It prints a JSON
  manifest: text in reading order, tables as rows, every embedded image written to disk with its
  position, alt text and caption, bounded previews for sheets (the bound is stated), and counters for
  anything cut. Read the text file it names; open images with Read.
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

Write every finding to ONE JSON file (`isaac.reading_findings`), then load it in one step:

```json
{"format": "isaac.reading_findings",
 "findings": [{
   "field_path": "context.environment",
   "value": "in_situ",
   "applies_to": {"scope": "runs", "run_labels": ["<runs[].label exactly>"]},
   "source": {"path": "<relative to the imported folder; ../<name> only for a file beside it the scientist let you open>", "locator": "line 65"},
   "quote": "<verbatim, at most 25 words>",
   "strength": "stated | inferred",
   "reasoning": "<why the quote supports the value; the one inference step, if any>"}]}
```

- `stated`: the file says it. `inferred`: ONE written step from what it says. Nothing from
  what a lab "usually" does. A name in a file or folder name is evidence; say it is a name.
- `"scope": "runs"` whenever the statement is about particular samples or conditions;
  `"experiment"` only when the source says it of the whole beamtime. Two files that disagree:
  write both findings and tell the scientist. Never pick one.
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
(no such field in this bundle, a run label that does not exist): fix those or tell the scientist.
Each reading is an AI interpretation: cited, `needs_review` at most, never eligible on its own.
The questions in Step 7 show it as a suggestion beside the question; the scientist's answer is
what counts. Re-applying the same file adds nothing. Never present your reading as confirmed.
