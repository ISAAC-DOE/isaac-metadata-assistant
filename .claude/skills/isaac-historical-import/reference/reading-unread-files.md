# Reading what code could not (Step 4)

Read this at Step 4. Step 6 (processing) does not start until this step is done.

`<isaac> bundle list <bundle> unread --limit 50 --offset 0` — each entry has `relative_path`, `source_id`,
`source_type` and `reason_code`. An Athena project is listed as a file and nothing reads it: processing never uses
Athena (its row has `athena_project: true`). The page's `not_listed.companion_not_opened` counts the files a run reader
kept beside a run without opening them (`.rgn/.det/.exp`, `profile.txt`, `binary/` originals): not unread,
and not read; `unread --all` lists them with `run_id` and `role`, and `bundle show <bundle> source <id>`
says the same (`read_as.opened: false`). Read them only if the scientist asks. Work through the unread
files in this order, and tell the scientist which you are on.

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
  The blocks themselves are not printed (they are the text file); `--blocks` prints them inline too.
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
- **A Word logbook AND its .txt copy: read both.** A copy loses tables, highlighting, images and their
  captions. Run the extractor on the `.docx` and open EVERY image it wrote with Read; read the copy too.
  Two versions that disagree: write both findings and say so.

## Read a logbook completely

A logbook holds what no parser reads: the electrolyte per sample, each potential set-point, the cell, the
reference electrode, and which scans to leave out. A skim misses them. So:

- **Every line, never a skim.** Split a long logbook into sections of a few hundred lines and read each
  in full (Read with offset/limit). For a very long one (over ~800 lines) start one parallel reader per
  section (a subagent), each given its line range, these rules and the run list; merge their findings
  into the ONE findings file and check it (below).
- **Link a step table to runs by its file number.** A logbook's step table often has a "File Number"
  column: that number is the run folder's leading number (`27` is run `27_...`). Link a sample section to
  runs by the sample token in the run names. Check each link from the text itself; a table with no file
  numbers links by step order only, and every such finding is `inferred`, with the order in `reasoning`.
- **Scope a statement to what it is about.** A sentence about one sample is a `runs` finding for that
  sample's runs. A general sentence ("In ALL experiments we used 0.1 M KOH") that a sample section
  contradicts: write both findings (the general one for the runs it covers, the section's for its runs)
  and tell the scientist they disagree. Never pick one.
- **One written step, never more.** A section that says only "vs reference", in a logbook that names
  exactly ONE reference electrode elsewhere, gives that electrode as `inferred`, with both lines in
  `reasoning`. Two named electrodes, or none: no finding. Never infer from what labs usually do.
- **Curation notes are scan notes.** "Discard the first scan", "start from scan #5", "only scans 1-8
  usable", "ignore scan 8 (went to open circuit)", "the potentiostat jumped to 2.5 V": write each as a
  `scan_note` finding (below). Processing applies them when it decides which scans to keep.
- **Scan headers and alignment files.** Read the SPEC files' `#C` comment lines and the alignment
  file's "mono reset" lines: they say when the energy or the sample changed.
- **What fits no field** (a sample history, a beam dump, a changed detector setting): tell the scientist,
  with the file and line numbers. Never force it into a field.

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
   "source": {"path": "<relative to the imported folder>", "locator": "line 65"},
   "quote": "<verbatim, at most 25 words, from that line>",
   "strength": "stated | inferred",
   "reasoning": "<why the quote supports the value; the one inference step, if any>"}]}
```

- `stated`: the quote states the value word for word (the number with its unit, the list member, every word of
  the name). `inferred`: ONE written step from what it says ("100 mV" for `0.1` V is one step). Nothing from what a
  lab "usually" does. A name in a file or folder name is evidence; say it is a name.
- A checked `stated` finding can FILL its field green (the code decides, by its rule). A checked `inferred` one fills
  it as a GUESS, yellow: listed apart in the end review and named in the final check before upload, so the scientist
  sees it was your reading, not the file's words. So never mark a finding `stated` to make it green: an honest
  `inferred` is what keeps green meaning certain. A guess is never made of a sample's own code as its material, of the
  environment (the convention question settles it), or where two readings disagree.
- The environment: write what the logbook STATES (a line that says "operando" or "in situ"). Never infer one from a
  potential or a cell: the beamtime's convention question settles those runs.
- **The quote is checked when the file is loaded.** Copy at least 3 words (or 12 characters), or a
  whole short line ("Ar sat") cited by its own `line N`, exactly from the file (spacing, quote marks and dashes may differ; letters and case may not). Cite the file
  itself, by its path inside the imported folder, never the extractor's output in `<bundle>-notes/`.
  - Text: the line it is on, `line N` (or `lines N-M`, at most 20 lines, for a quote over several);
    it must start within 3 lines. A locator holding a number that is not a line fails.
  - `.docx/.pptx/.xlsx`: `paragraph N`, `table N`, `slide N` or `sheet <name> row N` is checked on that
    part of the extractor's text; any other locator is reported "found in document, locator not checked".
  - SPEC headers: `scan 5 #C` checks that scan's `#` lines. PDF: `page N` checks that page; a locator
    with no number searches every page.
  - A scanned PDF page ("no text layer") or a file outside the imported folder (`../`) cannot be checked.
    A transcription you make of one goes in `<bundle>-notes/` (never in the scientist's folder), and is
    not citable: tell the scientist what it says as "my reading of <file>, page N", with no finding.
  - A file under the folder that the import did not read (`source_not_imported` in the report) has no
    hash tying it to the import: say so when you report what it holds.
- **Naming runs.** `runs` takes each run's `stem` (the file name the scientist knows) or its `run_id`,
  both printed by `<isaac> bundle list <bundle> runs`; where two runs share a stem (the same name in
  two folders) the row also prints `path`, and that path or the `run_id` names one of them. Never use
  `label`: it reorders the name's tokens and drops some, so two runs (`_12_1200mV`, `_1_1200mV`) can
  share one. A reference that names more than one run is skipped, never spread over both.
- `"scope": "runs"` whenever the statement is about particular conditions or runs; `{"scope": "samples", "samples":
  ["<the sample's name as the files write it>"]}` when it is about a SAMPLE (its material, its form): it reaches every
  run of that sample; `"experiment"` only when the source says it of the whole beamtime. Two files that disagree:
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
  preview skips them ("no live record group yet"): load the same file again in Step 5, after the regroup, and after
  every later regroup (loading it again adds only what is new). They show as suggestions on the absorber question.
  Only the scientist's `set_absorber` answer gives the absorber.

## Scan notes

A logbook's notes on which scans to use go in the same findings file, one `scan_note` each:

```json
{"kind": "scan_note",
 "applies_to": {"scope": "runs", "runs": ["<stem>"]},
 "action": "exclude | start_from | keep_only | flag",
 "scans": [1],
 "reason": "<plain words>",
 "source": {"path": "...", "locator": "line 1300"}, "quote": "...",
 "strength": "stated | inferred", "reasoning": "..."}
```

`exclude` lists the scans to leave out; `start_from` takes ONE number (the first scan to keep);
`keep_only` lists the scans to keep; `flag` takes no `scans` (advice that changes nothing: "the
potentiostat jumped to 2.5 V during this file", material loss). Scan numbers are the logbook's own.
"Probably discard the first 2" is `exclude [1, 2]`, `inferred`, and the reason says "probably".

- A scan note is my reading of the logbook, not the scientist's decision.
- Processing applies `exclude`, `start_from` and `keep_only` notes when it decides which scans to keep, and shows the
  note as the reason (marked "inferred" when it is). The scientist can override any of them (Step 6).
- See them with `<isaac> bundle list <bundle> scan-notes` and `<isaac> bundle show <bundle> run <id>`.

## Check, then load

```
<isaac> bundle check-readings <bundle> <findings.json> --root <folder>                                   # quotes only
<isaac> bundle annotate <bundle> --from-readings <findings.json> --model "<model name>" --root <folder>  # preview
<isaac> bundle annotate <bundle> --from-readings <findings.json> --model "<model name>" --root <folder> --apply
```

Always run the preview before `--apply`, even when `check-readings` passed. `check-readings` checks the quotes only.
The preview also shows which findings it cannot place and how many targets each one reaches.

`<folder>` is the folder that was imported: when the bundle records it, `--root` may be left out and
any other folder is refused; when not, a folder of another name is refused, and so is one holding none of the imported files with the bytes the import read. `check-readings` and the preview report every quote as
`pass` or `fail` (and where a quote was found when it is not near its locator). `--apply` records NO
finding whose quote was not found, whose run reference names no run (or more than one), or whose value
is not on its field's list (`refused_by_reason`); there is no way to skip the check. Fix the file and
load it again until nothing is refused. The preview also lists, per finding, how many targets it
reaches and every finding it could NOT place (no such field in this bundle): fix those or tell the
scientist.
A checked, stated reading whose quote states the value fills its field (rule `isaac.fill.reading_stated.v1`, green);
a checked inferred one fills it as a guess (rule `isaac.fill.reading_inferred.v1`, yellow); both go to the end review.
Every other reading is a suggestion with its citation, shown beside its question, and the scientist's answer is what
counts. Loading the same file again adds nothing. Never present a reading as confirmed.

## Before you leave this step

End this step's message to the scientist with:

- what each file held, and what fit no field (with line numbers);
- which files nobody could read;
- how many scan notes you loaded (`total` in `<isaac> bundle list <bundle> scan-notes --limit 1`), or that you read the
  whole logbook and it says nothing about which scans to use, or that the folder has no logbook.

If you find a logbook statement later, after curves were approved: load it, tell the scientist, and re-process the
groups it names (`grouping-and-processing.md`, "If evidence arrives after a curve was approved").
