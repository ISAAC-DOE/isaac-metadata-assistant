# Data flow and consent (Step 1)

Read this at Step 1, before you read anything else, in every conversation.

Source of truth: `docs/local-first-data-flows.md`. Three flows exist and are approved separately (A–C);
row D is the scientist's own action on the website, outside this skill, said here so they know it.

| Flow | What happens | What leaves the computer |
|---|---|---|
| A. ISAAC's own code | reads files here, writes a bundle folder here | nothing. Only `isaac import` prints counts alone; every other command prints names or values, so what you see of it is flow B |
| B. Claude reads | anything you open with Read, and EVERY command output you see: `summary.md`, `bundle questions`, `list`, `show`, `group`, `process`, `crosscheck-plan`, `excerpt`, `reveal`, `decide`, `check`, `extract`, `build-records`, `validate`, `export`, `template` previews | that text goes to the Claude model service |
| C. Upload to ISAAC | not available in this build | nothing (dry run only) |
| Earlier answers (opt-in) | once the scientist says yes (`answer-memory on`), the answers they confirm are kept in `~/.isaac/answer-memory.json` on this computer (field, value, their name, date, beamtime folder NAME) and shown as hints on later beamtimes | nothing: it is a local file. The hints you see in `bundle questions` are command output (flow B) |
| Setup update check (Step 0) | `setup_isaac_local.sh --check` runs `git fetch` from the ISAAC folder's `origin` (GitHub); `--update`, on the scientist's yes, fast-forwards the ISAAC code | nothing of theirs: it is a code DOWNLOAD that changes no file in their ISAAC folder (it updates git's record of what's on GitHub). GitHub sees a request from this computer, as for any download; no file, name or value is sent. `--offline` skips it |
| D. Save a term proposal | the scientist loads the `propose-terms` drafts file on the Schema Proposals page and saves a proposal (their choice, never yours) | the term, its counts and its file-name citations go to the ISAAC server that page uses (the hosted server when they use the website); nothing before they save |

## What to say (adapt, keep it short)

> Before I start: I'll have ISAAC read **<folder name>** on this computer. That step sends nothing
> anywhere. After that, whenever I open a file or look at a command's output myself, that text goes
> to the Claude service. Are you allowed to let Claude read this data (your group's and SLAC's
> rules, and your data owner's OK)? If you're not sure, say so and I'll stick to the parts that
> stay on your computer. What name should I record your answers under? One step is optional: I can
> read a few files myself before I see what ISAAC found, as a spot check; say if you'd rather skip it.

Record it in the working folder once the import exists: `<isaac> bundle consent <bundle> --by "<name>"` (a
withdrawal: add `--withdraw`). Use that name as `--by` for every decision; do not ask it again. Do not treat a yes about
one folder as a yes about another: the record names its folder.

## What is kept between conversations, and what is not

- **The consent and the name are kept** in the working folder once recorded with `bundle consent`. In a new
  conversation run `<isaac> bundle status <bundle>` first (it prints no file value): it says who consented and when.
  Then greet them by that name and continue; do not ask again.
- **Only when status says "not recorded" or WITHDRAWN**, ask the one consent line before anything else:
  "Welcome back. Am I still allowed to read this beamtime's files and outputs, and under which name do I record?"
- Every answer, approval and export so far IS kept. Never ask those again (Step 2, "A working folder that already exists").

## Looking writes nothing to the bundle

Commands that only look (`status`, `list`, `show`, `questions`, `check`, `site export`) never change `bundle.json`. The
values they show are noted in `exposures.pending.jsonl` beside it, and a newer ISAAC upgrades the format only at the
next answer. So a second conversation or the Local Imports page looking at the same folder does not get "The bundle
changed since it was read". Two sessions both ANSWERING at once still can: run the command again.

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
yes covers that one file. A finding cannot cite it: quotes are checked only against files inside the
imported folder. Tell the scientist what it says instead (with its page or line).
