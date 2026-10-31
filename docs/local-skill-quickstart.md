# Turn an old beamtime folder into ISAAC records: quick start

*For scientists. No programming needed. Status: working on made-up (synthetic) data; real data
needs your group's and SLAC's permission first (see "What happens to your data").*

## What this does

You point Claude Code at a folder of measurement files from a past beamtime. ISAAC's own program
reads what it can, Claude reads what the program cannot (logbooks, slides, spreadsheets, figures),
and **you decide** every value that is uncertain. At the end you get records in the format the
ISAAC portal expects, plus a plain list of what is still missing. **It never uploads anything.**

## Install (once, about 10 minutes, needs internet)

1. Get the ISAAC folder from your group (a copy of the ISAAC repository).
2. Open **Terminal**, go to that folder, and run:

   ```
   scripts/setup_isaac_local.sh --install-skill
   ```

   It sets up a private Python environment inside that folder, installs the ISAAC tools, the
   spectrum-processing add-on and the offline portal checker, and copies the Claude Code skill to
   `~/.claude/skills`. It needs no administrator password and changes nothing else on your Mac.
   If it says no Python 3.11 is found, it tells you the one thing to install, then you run it again.
3. Check it works, on made-up data (takes about a minute):

   ```
   scripts/isaac_selftest.sh
   ```

   You want to see `0 failed` at the end. Lines marked `SKIP` are parts you have not installed.

Run `scripts/setup_isaac_local.sh --check` any time to see what is installed. It also tells you
when the skill copy in `~/.claude/skills` differs from the one in the ISAAC folder (for example after
you update the folder). Claude Code uses that copy, so refresh it with
`scripts/setup_isaac_local.sh --install-skill` and restart Claude Code.

## Run it

1. In Terminal, go to a folder **above** your beamtime folder and start Claude Code: `claude`
2. Type `/isaac-historical-import` and tell it the folder.
3. Answer what it asks. It works in this order, and tells you where you are ("3 of 12 groups
   confirmed"):
   1. **Permission check.** It asks whether you are allowed to let Claude read this data. Say no (or
      "not sure") and it does only the parts that stay on your computer.
   2. **Import.** ISAAC reads the folder and reports what it found.
   3. **Spot check.** Claude reads a few key facts from the raw files *before* seeing what the
      program extracted, then compares. Differences become questions for you.
   4. **Files the program could not read.** Claude reads Word, PowerPoint, Excel, PDFs and images.
   5. **Groups.** Which scans belong in one record (same sample, same conditions). You confirm,
      split or merge.
   6. **Spectra.** ISAAC processes each group and shows a plot and a quality verdict. You approve or
      reject each, and when you approve you state the **QC status** yourself (the program never turns
      a warning into a status for you). The processing recipe is a draft until Oscar and Angel review it.
   7. **Questions.** Only what blocks a record comes first, asked once for the whole beamtime where
      the answer is shared ("this applies to 9 groups") and once per group where it differs. Claude
      tells you how many answers make a group ready (often 4 to 7). Conflicts that affect a record
      come next; "I don't know" is fine and the value stays missing. Where the record takes only
      fixed words (for example `in_situ`, `powder`), Claude matches your words to one of them and
      asks you to confirm it; ISAAC refuses any other word. Some items are only listed for
      information, because no answer could go into the record; you are not asked about them.
      If you prefer, you can answer the same questions in a browser on your own computer: the
      *Local Imports* page (setup in `docs/ui-local-dev.md`). It runs the same checks.
   8. **Checks.** Each record is checked against the schema and the portal's rules. Claude explains
      anything that fails and how to fix it.
4. **What you get:** a folder of records (`<id>.json` and `<id>.evidence.json`) for every record that
   passes every check, plus a summary of what was not ready and why. `upload --dry-run` shows what
   *would* be sent to the portal; **nothing is sent**. You upload through the portal yourself.

## What happens to your data

| What | Where it goes |
|---|---|
| ISAAC's own reading, grouping, processing, checks and export | stays on your computer; no internet use |
| Anything Claude opens or sees in a command's output (a logbook page, an excerpt, a value) | **is sent to the Claude service** |
| Upload to the ISAAC portal | not possible in this version |

Local file access is not permission to send file contents to Claude. Ask your group and SLAC's
rules before using real data (`docs/local-first-data-flows.md`). The skill asks you each time.

## What you will be asked

- Permission to let Claude read the data.
- Which scans belong together; whether a curve looks acceptable, and its QC status.
- Which reading is right when sources disagree (it never picks for you).
- Your name once (recorded as who decided), and optionally your ORCID (as a credit, not a login).
- Facts nobody wrote down, such as who produced the data, the sample form, the environment.

## Limitations (please read)

- **The processing recipe is a draft** (`isaac.xas.v0`) until a beamline scientist reviews it. Your
  approval of a curve means "I looked and accept this for this record".
- **Spot checks are not verification.** Claude's independent reading covers a sample of key facts;
  the summary says how many.
- **Names are not verified.** Decisions are recorded as `local_unverified`.
- **Two schemas.** Records are checked against the schema the portal uses. The ISAAC website's
  older July (v1.05) schema cannot hold some of what the portal needs, for example "temperature not
  reported" or who produced the data. The checks report that for information only: an unknown
  temperature does not stop a record from being exported, and no temperature is guessed.
- **Readers.** Built in: Beamline 15 SPEC scans and macros, SSRL EXAFS Data Collector text scans,
  Athena/Demeter exports, XDI files, XES tab files, PyMca MCA files, simple two-column text, Larch
  session (`.larix`) files and Igor (`.pxp`) experiments, and nested ZIPs. Other formats are listed as
  unread and Claude reads what it can.
- Needs a Mac (Linux works the same way). Uploading is not part of this version.

## If something goes wrong

Claude explains each message in words. The usual fixes: `scripts/setup_isaac_local.sh` (not
installed), a new empty output folder (output refused), `scripts/install_portal_validator.sh` (portal
check missing). For anything else, send the exact message to the ISAAC team.
