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

   What it covers: the straight line from import to an upload dry run (import, check, spot check, groups,
   processing, a handful of decisions, build, validate, export). What it does not cover yet: loading logbook
   readings and scan notes, the counter question and a regroup, answering several questions at once, "I don't
   know", scan and dose decisions, a second export, a ZIP, the template and the question workbook. A pass means
   the installation works; it does not test those paths.

Run `scripts/setup_isaac_local.sh --check` any time to see what is installed. It also tells you:

- when the skill copy in `~/.claude/skills` (or the folder you pass with `--skill-dir`) differs from the
  one in the ISAAC folder (`[stale]`). Claude Code uses that copy. The skill notices this itself, says so,
  runs `scripts/setup_isaac_local.sh --refresh-skill` (it copies the skill only: nothing is downloaded or
  installed) and carries on with the new instructions; you do not need to restart Claude Code.
- when your ISAAC folder is behind the latest version on GitHub (`[behind N commits]`). To find out it
  runs `git fetch`, which **downloads** code and sends none of your data; it changes no file in your
  ISAAC folder (it updates git's record of what's on GitHub). When GitHub is not reached the line says
  `[skipped]` with the reason and nothing fails (`--offline` skips the check). The skill asks before updating.
  `scripts/setup_isaac_local.sh --update` updates only when it is safe: the folder must be on `main`,
  with no local changes to ISAAC's files and no commits of its own, and the update must not replace
  any file git does not track (such as your data in `examples/`); otherwise it says why and changes
  nothing. It then refreshes the skill copy; if the tools' dependencies changed it prints the command
  that refreshes them (a download) instead of running it. It only changes the ISAAC code, never your
  data or bundles.

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
   5. **Groups.** Which scans belong in one record (same sample, same conditions). Claude shows you a
      table of the groups that are as proposed, for one confirmation, and then only the ones that need a
      look. You can ask to see any group.
   6. **Spectra.** ISAAC processes each group: it aligns every scan on its in-scan reference, decides
      which scans to keep by a written rule (never on intensity alone) and says why it dropped each one.
      Claude shows the curves that passed every check in one table with a few example plots, for one
      approval, and then each curve that needs a look with its plot. You can ask to see any curve and
      overrule any scan decision. When you approve you state the **QC status** yourself (the program never
      turns a warning into a status for you). The processing recipe is a draft until the ISAAC
      processing reviewers have reviewed it.
   7. **Questions.** In up to three messages: first only what blocks a record, as yes/no or a pick,
      asked once for the whole beamtime where the answer is shared ("this applies to 9 groups"); then
      one list of values ISAAC proposes from your files (start time, absorber, potentials and their
      reference, cycling history, filter, sample ids) for you to confirm; then, only if you want, the
      rest. "I don't know" is fine: Claude says what it costs (those records cannot be exported until
      someone answers) and offers a sheet to pass to a colleague. Where the record takes only
      fixed words (for example `in_situ`, `powder`), Claude matches your words to one of them and
      asks you to confirm it; ISAAC refuses any other word. Some items are only listed for
      information, because no answer could go into the record; you are not asked about them.
      If you prefer, you can answer the same questions in a browser on your own computer: the
      *Local Imports* page (setup in `docs/ui-local-dev.md`). It runs the same checks.
   8. **Checks.** Each record is checked against the schema and the portal's rules. Claude explains
      anything that fails and how to fix it.
   You can stop at any point and come back later. Start Claude Code again, type
   `/isaac-historical-import` and name the same folder: it checks what is already recorded and carries on
   from there. It asks the permission question and your name again (one line); it does not ask again for
   anything you already answered.
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
- **One schema.** Records are checked against the schema the portal uses, and from this release on
  the ISAAC website validates against the same document (the same upstream commit). A hosted
  website still serves its older schema until it is redeployed with this release. It can say "temperature not
  reported" and who produced the data. An unknown temperature does not stop a record from being
  exported, and no temperature is guessed.
- **Readers.** Built in: Beamline 15 SPEC scans and macros, SSRL EXAFS Data Collector text scans,
  Athena/Demeter exports, XDI files, XES tab files, PyMca MCA files, simple two-column text, Larch
  session (`.larix`) files and Igor (`.pxp`) experiments, and nested ZIPs. Other formats are listed as
  unread and Claude reads what it can.
- Needs a Mac (Linux works the same way). Uploading is not part of this version.

## If something goes wrong

Claude explains each message in words. The usual fixes: `scripts/setup_isaac_local.sh` (not
installed), a new empty output folder (output refused), `scripts/setup_isaac_local.sh` again (portal
check missing: it sets up the copy shipped in `vendor/isaac-portal-validator/`). For anything else, send the exact message to the ISAAC team.
