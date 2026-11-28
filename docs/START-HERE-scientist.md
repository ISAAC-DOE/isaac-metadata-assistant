# Start here: turning a past beamtime into ISAAC records

This is for you if you have a folder of files from an old beamtime and want ISAAC records out of it.
You do not need to program. Plan on about an hour per beamtime, most of it answering questions about
your experiment.

## What you need

- A Mac.
- Claude Code installed and signed in (typing `claude` in Terminal should start it).
- git (type `git --version` in Terminal; if the Mac offers to install developer tools, say yes).
- Access to this repository on GitHub.
- About 2 GB of free disk space.

Python 3.11 is also needed. You probably do not have to do anything: the setup script finds it, or
tells you the one thing to install if it cannot.

## Four steps

1. **Get the folder.** In Terminal:

   ```
   git clone https://github.com/ISAAC-DOE/isaac-metadata-assistant.git
   cd isaac-metadata-assistant
   ```

2. **Run the setup** (once; 10 to 20 minutes, needs internet):

   ```
   scripts/setup_isaac_local.sh
   ```

   It makes a private Python 3.11 environment inside this folder and installs the ISAAC tools, the
   spectrum processing and the portal's own record checker. It asks for no password and changes
   nothing else on your Mac. It ends with a checklist. Every line should start with `[ok]`, apart
   from two that are fine as they are:
   - `[optional] pdf pages` (see "If something fails" below);
   - `[skipped] update check`: it could not compare this folder with GitHub (for example you are
     offline, or GitHub did not answer in time). Nothing is wrong; it just could not check for a
     newer version.

3. **Open Claude Code in this folder** (the `isaac-metadata-assistant` folder, not your beamtime folder):

   ```
   claude
   ```

   The first time, it asks whether you trust the folder. Say yes. Claude Code then uses this folder's
   own copy of the import skill, so there is nothing else to install.

4. **Type `/isaac-historical-import`** and tell it where your beamtime folder is, for example
   `~/Desktop/my-beamtime`. A ZIP works too.

## What happens next

- It reads your files on your computer: scan files, logbooks, spreadsheets, slides.
- It fills in everything your files state, and asks you only what they do not say or where they
  disagree. That is usually a handful of questions.
- At the end it shows you a review of every value, colour coded:
  - **green**: read from your files, or your own answer;
  - **yellow**: its best guess, or something it worked out, for you to confirm;
  - **red**: it needs you.
- It writes the finished records into a `records` folder. **It never uploads anything.** When you
  are happy with them, you upload that folder yourself through the ISAAC portal.

You can stop at any point and pick up later; your answers are saved.

## If something fails

Run this in the same folder and look at the lines that do not say `[ok]`:

```
scripts/setup_isaac_local.sh --check
```

Each line says what is wrong and the command that fixes it. Running `scripts/setup_isaac_local.sh`
again is always safe.

Common ones:

- **No Python 3.11**: it tells you to install `uv` (one command) or Python 3.11, then run the setup again.
- **`[optional] pdf pages`**: Claude can still read text PDFs. For scanned logbooks, install poppler
  with Homebrew: `brew install poppler`.

## Who to ask

Krish. Send him the output of `scripts/setup_isaac_local.sh --check`, and what you typed when it went wrong.
