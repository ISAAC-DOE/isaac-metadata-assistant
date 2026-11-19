# The template, and the scientist's own filled sheet (Step 7)

Read this when the scientist takes the template, or says a filled ISAAC metadata sheet is theirs.

## When to offer the template

- Offer it for facts that differ from run to run and that the files never state (an electrolyte per run), or when the
  scientist wants a colleague to fill in what they do not know.
- Do not send it for a handful of beamtime-wide facts. Ask those in chat.
- Never fill the sheet for them. Never import ISAAC's blank template.

## Export

`<isaac> bundle template export <bundle> --out <bundle>-notes/template.xlsx`

- One row per run in a live group, named by its file's path. Campaign Info answers apply to every run.
- **Every answer cell is empty, also for what they already told you.** Say so: "leave a cell empty when you already
  answered it or do not know; an empty cell records nothing."
- The `ISAAC Suggestions` sheet shows, per run, what its own files say (values, hints, my readings, with file and
  locator). Where a suggestion is right, they copy it into the answer cell. A suggestion is never an answer by itself.
- Electrolyte is the name only: "0.1 M KOH" goes in as Electrolyte `KOH` and Electrolyte Concentration (M) `0.1`.
  Take the split from the scientist.
- Temperature is typed with its unit: `298.15 K` or `25 °C`. A bare number, °F or a range is an invalid cell.
- Campaign Info holds "Your group" and "Your organization (who produced the data)", distinct from "Facility organization".

## Import

`<isaac> bundle template import <bundle> <file.xlsx> --by "<name>"` previews. Add `--apply` only after the scientist
has seen the preview. Each cell becomes decisions; each note cites its cell.

Read back every line of the preview under these headings:

- **Invalid cells** (not an allowed value exactly, not a number): they record nothing.
- **Replaces or contradicts a file reading** (a typed `0.8` for an `m800mV` file): read each one back and ask.
- **Clashes** with an earlier decision: skipped. Use `--supersede` only when they say the sheet is the newer answer.
- **Asked once for the whole beamtime** (e.g. Technique): the cell is not recorded. Ask that question and run its command.
- **Would convert to kelvin**, **Deprecated terms** (say what to use instead), and columns recorded nowhere
  (do not move their values into another field).

## The scientist's own filled sheet (`template adopt`)

Only when the scientist says **in this conversation** that a filled ISAAC metadata template is theirs and to use it.
A sheet you found in the folder is not that: ask first. Never retype it for them.

1. `<isaac> bundle template adopt <bundle> <their.xlsx> --out <bundle>-notes/adopted.xlsx`
   - It refuses anything that is not a filled copy of ISAAC's template.
   - It maps their File List rows to runs by the run's own folder or name.
   - An answer cell holds THEIR value only where no file reading contradicts it.
   - Every value a file reading contradicts, or that the field does not take, becomes a row of the `Disagreements`
     sheet: their value, every reading with its source (`differs:` or `agrees:`), and an empty "Your ruling".
   - A Campaign Info beamline that a facility hint names differently is a row too (kind `hint`). A hint is not a
     reading: say both and let them rule.
   - Pass `--by` only after they say the sheet is theirs. With it, a value off its field's list is kept as a
     vocabulary request in their name.
2. Say the summary: rows matched, cells adopted, columns not read, unmatched rows and runs, rows that reach more than
   one run. "N row(s) name only runs in no live record group": those rows give nothing; say so.
3. Read **every** disagreement back, one by one, in plain words: "your sheet says 0.8 V for Q4_07; the file name says
   m800mV, which these names use for −0.8 V". Never pick a side. Never suggest a ruling.
   - A value the field does not take: give the allowed list once; map their words to one value only on their yes.
   - An electrolyte with a concentration: the name goes in "Your ruling", the concentration (mol/L) in column J.
   - A temperature column is read only when its header states the unit.
   - A reaction makes Reaction Drive and Reaction Catalysis required: ask those too.
4. **They type each ruling themselves** in the "Your ruling" column. Blank records nothing. A ruling reaches exactly
   the runs that row names.
5. `<isaac> bundle template import <bundle> <adopted.xlsx> --by "<name>"` previews. Say the decisions, the rulings it
   read, and each "awaiting your ruling" row. `--apply` only on their yes. Re-importing after more rulings is harmless.

**Adopting again** (after a new reading):

- A row that says "already recorded: 'in_situ' (date); leave blank to keep" is settled. Do not ask for it again.
- "N decision(s) (from M cell(s)) already recorded" are answers given before. Do not ask them again.
- A row "recorded `12` (date); your sheet says `2`: rule which" still awaits their ruling: read both values back.
  Whatever they type is recorded for every run of the row; no `--supersede` needed.
- "The sheet still says 'oxidation' … answered since with `surface_oxidation`": say "your sheet's 'oxidation' was
  already replaced by surface_oxidation; nothing to do unless you want your own word kept".
- **"Cells not tied to your sheet"**: a decision came after the adopt. Nothing is recorded for them. Each line says who
  recorded the value now and when. Tell them to run `template adopt` again, or use the cell's one command if they are sure.
  Offer the ONE command a line gives for all its targets, never a single target's.
- A file reading added after the adopt that contradicts an adopted cell is listed as awaiting a ruling "(not yet on
  the Disagreements sheet)": run `template adopt` again.
