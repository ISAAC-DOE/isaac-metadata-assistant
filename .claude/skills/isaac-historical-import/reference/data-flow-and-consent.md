# Data flow and consent (Step 1)

Source of truth: `docs/local-first-data-flows.md`. Three flows exist and are approved separately.

| Flow | What happens | What leaves the computer |
|---|---|---|
| A. ISAAC's own code | reads files here, writes a bundle folder here | nothing. Only `isaac import` prints counts alone; every other command prints names or values, so what you see of it is flow B |
| B. Claude reads | anything you open with Read, and EVERY command output you see: `summary.md`, `bundle questions`, `list`, `show`, `group`, `process`, `crosscheck-plan`, `excerpt`, `reveal`, `decide`, `check`, `extract`, `build-records`, `validate`, `export`, `template` previews | that text goes to the Claude model service |
| C. Upload to ISAAC | not available in this build | nothing (dry run only) |

## What to say (adapt, keep it short)

> Before I start: I'll have ISAAC read **<folder name>** on this computer. That step sends nothing
> anywhere. After that, whenever I open a file or look at a command's output myself, that text goes
> to the Claude service. Are you allowed to let Claude read this data (your group's and SLAC's
> rules, and your data owner's OK)? If you're not sure, say so and I'll stick to the parts that
> stay on your computer. What name should I record your answers under? One step is optional: I can
> read a few files myself before I see what ISAAC found, as a spot check; say if you'd rather skip it.

Record: "Consent given by <name> at <time> for <folder>" in your reply. Use that name as `--by` for
every decision; do not ask it again. Do not treat a yes about one folder as a yes about another.

## If the answer is "no" or "not sure"

Run `isaac import` and nothing else; report only its short stdout (three lines, four when it found
the scientists' processed files). Do not open `summary.md`, any file in the source folder or any
bundle file, and run no other command: every other one prints names or values that would reach you.
Give the scientist the commands to run in their own terminal and tell them what each produces.
Offer to continue once they have permission.

## Never

Do not route file text to another tool or service. Do not paste file contents into a message
beyond the excerpt a question needs. Read only inside the folder the scientist approved. If a
document beside it (a proposal, slides) looks relevant, name it and ask before opening it; their
yes covers that one file. Cite it as `../<name>` only after they agree.
