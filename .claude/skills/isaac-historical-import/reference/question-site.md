# The question site (`bundle site export`, `bundle site import`)

Some scientists have no block of time for questions. The question site lets them answer a few at a time, on a
phone or a laptop: yes or no, pick an option, or type. You make the cards from the bundle, someone deploys
the folder, and later you read the answers back. Nothing is recorded until you import the answers, and each
decision is recorded under the name the scientist signed in with.

## Make the cards

`<isaac> bundle site export <bundle> --out <folder> [--suggestions <file>] [--include optional] [--include deferred] [--include approvals] [--site-template <folder>] [--json]`

- `--out` is a folder of its own, outside every git repository and outside the bundle folder (exit 4
  otherwise: it holds real data). It gets `data/site-data.json` and `data/img/`, and the site's own files
  when the site template exists, so the folder deploys as it is. The report says when only `data/` was written.
- By default the cards are the questions that block export, plus one processing question when the merged
  curves ask it (is a change after the first scan at a spot beam damage, or was the first scan still
  settling). `--include optional` adds the questions that are not needed to export, `--include deferred`
  the ones answered "I don't know" earlier, `--include approvals` one yes or no card per record group to
  confirm and per merged curve to approve.
- One card is one real ask. Questions the bundle itself says share a reading become one card (all
  measurements of one sample token). Different samples and different fields are never one card: a question the
  command line asks once for the whole beamtime is asked once per sample, and a file that names no sample gets
  a card of its own. A card that covers more than 40 measurements shows all of them, by sample, with counts.
- Read the report back: how many cards, in which sections, how many questions they cover, and every question
  left out with its reason. A question the site cannot word plainly is left out and counted, never shown raw.
- The export checks every card by a dry run, so it takes about a minute for a large beamtime. It writes to the
  bundle only the list of values it showed (the exposure log), never a decision.

**Only what remains.** A value a rule filled or guessed from the evidence gets no card: it waits for the end review (Step 10).
The environment convention is one beamtime card (operando, in situ, or it differs), and the per-run environment
questions it covers get no card of their own.

**Suggestions.** A card shows a suggestion when the bundle holds one: a value the files give, a reading you
loaded with `<isaac> bundle annotate <bundle> --from-readings <file> --model "<model name>" --root <folder> --apply`,
or an earlier answer when the scientist has the answer memory on. `--suggestions <file>` adds hints from a
file (see `docs/question-site-contract.md` for its two shapes). A suggestion is a hint with its source and its
quote. It is never recorded on its own: the scientist accepts it, picks another value, or types one. A value
that is not on a field's list is shown beside the card as a quote, never as a one-click answer.

## Read the answers back

`<isaac> bundle site import <bundle> <answers.json> --site-data <folder>/data/site-data.json [--apply] [--remember] [--note-read <card id>] [--json]`

`<answers.json>` is the file downloaded from the site. `--site-data` is the same `site-data.json` the site
was showing.

The order, always:

1. **Copy the bundle** (`cp -R <bundle> <copy>`) and preview against the copy. Preview is the default and
   writes nothing, not even a lock file.
2. **Apply to the copy** (`--apply`) and show the user what it recorded: applied, already recorded, refused
   with the reason, notes to read, and cards no longer asked.
3. **Apply for real only on the user's word.** `--apply` refuses a bundle inside any folder whose name starts
   with `_runs` (exit 4, nothing recorded).

What each answer becomes:

| The scientist | What is recorded |
|---|---|
| accepted the suggestion | the suggestion, only while the card still shows the value they saw; refused when it changed or the card has none |
| picked or typed a value | that value, checked as `bundle decide` checks it. A word they TYPED that is not on the field's list is kept as a vocabulary request in their name (no decision, no value); a picked value off the list is refused |
| said "I don't know" | `defer`. The question stays open and is not asked again unless you export with `--include deferred` |
| said yes on a yes or no card | the one decision the card stands for |
| said no on a yes or no card | nothing. Read their note and settle it with them |
| wrote a note | nothing. Every note is listed under "Notes to read"; none is turned into a decision |
| wrote a note on a card for several measurements | nothing for that card: it is **held**, because the note may name exceptions ("all but the pellet"). Read the note with the scientist. If it names none, import again with `--note-read <card id>`; if it does, answer those measurements yourself with `bundle decide` |

- Every decision is recorded by `<their name> (question site)`, with a note naming the card and when they
  answered it.
- A card the bundle no longer asks (it was answered since with another answer, or the bundle changed) is
  listed under "Cards no longer asked" and not applied. The answer already there is kept.
- A second run records nothing new. They can answer ten cards today and fifteen next week: import the new
  download each time.
- `--remember` also keeps the recorded answers in the answer memory, only when the scientist turned it on
  themselves (`<isaac> answer-memory on --by "<name>"`). When it is off, nothing is remembered and the report
  says so. Never turn it on for them.
- After an import, run `<isaac> bundle questions <bundle>` again, and export the site again when they want to
  go on: answered cards drop out, and card ids stay the same for the questions still open.
- The processing question changes which scans are merged: after it is answered, run `<isaac> process` again
  for the bundle before anyone approves a curve.

Say plainly what the site is: a way to collect their answers. Their answers become decisions only when you
import them, and you show them what was recorded.
