# The question site: data contract (v1.0.0)

A scientist answers a bundle's open questions on a small hosted site, a few at a time. Three pieces share two
files:

1. `isaac bundle site export <bundle_dir> --out <dir>` writes `<dir>/data/site-data.json` and `<dir>/data/img/*.png`
   (and copies the site's source beside them, so `<dir>` deploys as it is).
2. The site (`apps/question-site/`) shows the cards behind a password and a name, and stores each answer as it is
   clicked. Anyone signed in can download `answers.json`.
3. `isaac bundle site import <bundle_dir> <answers.json> --site-data <dir>/data/site-data.json [--apply] [--remember]`
   turns the answers into `bundle decide` calls. Preview is the default; `--apply` records them.

Nothing here changes a question ID, the truth plane, or what a decision means.

## `site-data.json` (`format: "isaac.question_site"`, `format_version: "1.0.0"`)

```jsonc
{
  "format": "isaac.question_site",
  "format_version": "1.0.0",
  "bundle_id": "…",                    // the bundle's own id
  "bundle_version": "…",               // mutations.bundle_version at export time
  "title": "SYN_BL00_2100-01_Synthetic",   // the imported folder's name
  "generated_at": "2026-11-18T20:00:00Z",
  "totals": {"records": 92, "cards": 31, "blocking_cards": 24},
  "sections": [                        // in display order; a section with no card is left out
    {"id": "beamtime",   "title": "About the whole beamtime", "blurb": "One answer covers every record."},
    {"id": "samples",    "title": "About each sample",        "blurb": "One answer covers every measurement of that sample."},
    {"id": "records",    "title": "About single measurements", "blurb": ""},
    {"id": "processing", "title": "Processing",                "blurb": "How the spectra were merged."},
    {"id": "optional",   "title": "Nice to have",              "blurb": "Not needed to export, but makes the records more useful."}
  ],
  "cards": [ /* Card, in the order a scientist should meet them: blocking first, widest reach first */ ]
}
```

### Card

```jsonc
{
  "card_id": "C-1a2b3c4d5e",           // stable: sha256 of the field path + the sorted covered ids, 10 hex (see "Additions")
  "section": "beamtime",
  "blocking": true,                    // true if any covered question is blocking
  "audience": "scientist",             // or "processing" (a question for whoever owns the reduction)
  "title": "Which technique was used?",            // plain words, one sentence, no field paths, no command names
  "detail": "The files call the scan 'ZzL3_xas'. ISAAC needs one of its own technique names.",   // optional, ≤ 2 sentences
  "field": {"path": "system.technique", "label": "technique"},   // null for a card that sets no record field
  "applies_to": {
    "count": 92,
    "summary": "All 92 records",       // or "8 measurements of sample ZZ1", or one file name
    "items": ["01_01_ZZ1_acid_after500Cycling_filter10_100mV", "…"]   // run/file names, at most 40, then "more": n
  },
  "unblocks": 92,                      // records that cannot export until this card is answered (0 if not blocking)
  "answer": {
    "kind": "choice",                  // "choice" | "text" | "number" | "yes_no"
    "options": [{"value": "HERFD-XAS", "label": "HERFD-XAS"}],   // every allowed value, for "choice"; [] otherwise
    "common": ["HERFD-XAS", "XAS"],    // optional: the few options to show as buttons first
    "allow_text": true,                // the scientist may type their own word (kept as a vocabulary request if off-list)
    "unit": null,                      // "V", "M", … for "number"
    "placeholder": null
  },
  "suggestion": {                      // null when there is nothing honest to suggest
    "value": "HERFD-XAS",
    "label": "HERFD-XAS",
    "confidence": "high",              // "high" | "medium" | "low"
    "basis": "files",                  // "files" | "logbook" | "reading" | "earlier_answer" | "rule" | "general_knowledge"
    "reason": "Every scan records an emission energy at one emission line and a crystal analyzer.",   // ≤ 2 plain sentences
    "evidence": [{"quote": "…", "file": "logbook.docx", "locator": "line 54"}]
  },
  "context": [                         // what question_context already builds; at most ~6 items
    {"kind": "quotes", "label": "Logbook", "items": [{"quote": "…", "file": "…", "locator": "…"}]},
    {"kind": "values", "label": "From the files", "columns": ["file", "filter", "potential"], "rows": [["…", "…", "…"]]},
    {"kind": "image",  "label": "Merged curve", "image": "img/3fa9….png", "alt": "…"}
  ],
  "covers": [                          // how an answer becomes decisions; the site never shows this
    {
      "question_id": "Q-5a4bd3a297",
      "same_reading": true,            // pass --same-reading (one decide covers the question's same-reading group)
      "only_scopes": null,             // or a list of scopes, when the card covers part of a question
      "on_accept": {"decision": "confirm", "value": null},              // what "yes, the suggestion is right" records
      "on_value":  {"decision": "correct"},                             // the chosen or typed value is passed as --value
      "on_dont_know": {"decision": "defer"},
      "target": null                   // for a decision that is not a question: {"target": "experiment", "decision": "set_dose_reading"}
    }
  ]
}
```

Rules for the export:

- One card per real ask. Questions that share a `same_reading_group`, or ask one field for one sample token across
  many groups, collapse into one card. A card never joins questions whose honest answers could differ (different
  sample tokens, different fields).
- A suggestion is always a hint. It comes from the bundle (a value in `needs_review` with its sources, an AI
  reading with its quote, an earlier answer from answer memory, a rule the skill states) or from a
  `--suggestions <file>` of extra hints (same shape as `suggestion`, keyed by `question_id` or by
  `field` + `applies_to`). Every suggestion says where it came from. `general_knowledge` is always `low` or `medium`.
- `title` and `detail` are plain words. The CLI's own question text is never shown on the site.
- Images are the PNG/JPEG files question context already serves, copied to `data/img/<sha256>.<ext>` and checked by
  magic bytes. No other file type is copied.
- People's names found in files are treated as question context treats them today.

## `answers.json` (`format: "isaac.question_site_answers"`, `format_version: "1.0.0"`)

The site's download. One entry per card that has a current answer, plus the full event log.

```jsonc
{
  "format": "isaac.question_site_answers",
  "format_version": "1.0.0",
  "bundle_id": "…",
  "bundle_version": "…",               // copied from site-data.json
  "exported_at": "2026-11-20T18:02:11Z",
  "answers": [
    {
      "card_id": "C-1a2b3c4d5e",
      "action": "accept",              // "accept" | "value" | "dont_know"
      "value": "HERFD-XAS",            // accept: the suggestion's value as shown; value: the picked or typed value; dont_know: null
      "typed": false,                  // true when the value was typed, not picked
      "note": "",                      // free text the scientist added; reported, never applied
      "by": "SYN Scientist",                   // the name given at sign-in
      "at": "2026-11-20T17:58:40Z"
    }
  ],
  "log": [ /* every save and every clear, oldest first: {card_id, action | "clear", value, typed, note, by, at} */ ]
}
```

Rules for the import:

- Preview by default. `--apply` records each decision through `mutations.decide_question` / `mutations.decide`,
  with `by` = the answer's own `by` followed by " (question site)", and a note naming the card and the time.
- `accept` is refused for a card whose suggestion in `site-data.json` no longer equals the answer's `value`, and
  for a card with no suggestion.
- `value` goes through the decide path's own checks. A typed word off the field's list is kept as a vocabulary
  request, exactly as `decide --as-said` keeps it.
- `dont_know` records `defer`.
- A `note` is reported in the preview and the apply report. It is never turned into a decision.
- A card the bundle no longer asks (answered since, or the bundle changed) is reported, not applied.
- `--apply` refuses a bundle inside a folder whose name starts with `_runs`, as the workbook import does.
- A second run records nothing new.
- With `--remember`, applied answers are also written to answer memory when the scientist has opted in to it.

## Additions (all additive; no shape above changed)

These were added while the export and the import were built
(`apps/api/isaac_api/local_import/question_site.py`, `question_site_import.py`, `question_site_hints.py`). A site
written against the shapes above keeps working; it may ignore every key it does not know.

### One answer never reaches groups whose honest answer could differ

- A question the command line asks once for several record groups is one card **per sample the grouping
  states** (its sample name and loading or thickness, never the electrode number), answered with
  `only_scopes` = that sample's groups. A group whose files state no sample is a card of its own. The same holds
  for a same-reading group that asks for a value; one that only confirms the value each file itself gives stays
  one card ("yes" confirms each file's own value). `card_id` then hashes `Q-…@group:<id>` for each of the card's
  groups.
- A reading of "the samples" (`--suggestions`) is not offered as a one-click answer on a card about a file that
  states no sample, unless the entry names that file's group; it is shown as context.
- A card for several measurements says so in its detail: "One answer covers all N measurements; if any
  differs, add a note and nothing is recorded until it has been read."
- **An answer that carries a note, on a card whose `applies_to.count` is more than 1, is held by the import**:
  outcome `held`, reason "held: the note may name exceptions …", nothing recorded for that card. Once a person
  has read the note and it names no exception, `--note-read <card_id>` applies the answer as it was given. A
  note on a card about one measurement is reported and the answer applied.
- A card that reaches more than 40 measurements lists the first 40 in `applies_to.items` and **all** of them in
  `applies_to.breakdown`: `[{"label": "sample ZZ1" | "no sample named in the files", "count": n, "example":
  "<one file>"}]`, one row per stated sample and one per measurement that names none. The same table is the
  card's first context item ("Everything one answer covers: N measurements").

### What a card can carry beyond the example

- `applies_to.more` is present only when there are more than 40 items; `applies_to.breakdown` then lists
  everything (above).
- `answer.common` is present only when there is a short list to show first. It lists option **values**.
- A context item may carry `source` (a sentence saying where it came from: ISAAC's parser, ISAAC's processing, or
  "an AI reading of the files (not file evidence…)"). A `values` item may carry `more` (rows not shown).
  File names are shown as a `values` item with the one column `File`.
- `detail` may be an empty string.
- `covers` is a list. Most cards have one entry. A card about a PART of a same-reading group (one file-name token
  that names two materials, told apart by the grouping's own sample identity) has one entry per question; the
  import records the same answer through each.
- A cover may carry:
  - `field`: the one field of an optional-values question the call answers (`decide --field`);
  - `questions`: every question id the call answers (for a same-reading call, the whole group);
  - `on_yes` / `on_no`, on a `yes_no` card (below);
  - `on_accept: null` when the card has no suggestion, and `on_dont_know: null` when "I don't know" records
    nothing on that card (the dose card, a `yes_no` card, a question that takes no `defer`).
  - in `on_accept`, `from_earlier_answer`: the answer-memory entry the suggestion came from (the import adds
    where the value came from to the decision's note).
- `card_id` covers ids that are not question ids: `Q-…@group:<id>` for a card that covers one group of a
  question (`only_scopes`), `experiment:set_dose_reading` for the dose card, `<group id>:confirm` and
  `<result id>:approve` for the two approval cards.

### `yes_no` cards

The contract lists the kind and not what the site sends. The site sends **`action: "value"` with `value: true`
or `false`** (a JSON boolean), and the import reads that (it also takes `"yes"` / `"no"`, `"y"` / `"n"`, any
case). For a `number` card the site sends a JSON number.
`yes` records the cover's `on_yes`. `no` records nothing: its note says what a person should do, and it is
reported under "Nothing to record". `accept` is refused on a `yes_no` card (it has no suggestion) and
`dont_know` records nothing.

`yes_no` cards are: a condition label ISAAC proposes from the file names (`--include optional`: yes confirms each
proposal), confirming a record group, and approving a merged curve (`--include approvals`). A label card shows every
distinct proposed value with its count and an example file (context `values`, columns Proposed, Measurements,
For example); a label with more than 12 different values is left out and counted.

### The processing card and the approval cards

- The dose card (`section: "processing"`, `audience: "processing"`, `field: null`, `blocking: false`) is in the
  default export while any merged curve carries the open question "beam damage, or a first scan still
  settling" and the beamtime holds no answer. Its options are the three values `set_dose_reading` takes. Its
  cover has `question_id: null` and `target: {"target": "experiment", "decision": "set_dose_reading"}`.
- `--include approvals` adds one `yes_no` card per record group still to confirm (`target: {"target":
  "<group id>", "decision": "confirm"}`) and per merged curve still to approve (`target: {"target": "<result id>",
  "decision": "approve"}`, `on_yes: {"decision": "approve", "qc_status": "valid"}`, with the curve's picture).
  Left out and counted: every group while the question about counters in the file names is open, a curve with an
  open processing question, a curve whose quality check did not pass, a curve with no picture.

### What the export leaves out, and says so

The report counts every open question that is on no card, by reason: not needed to export (without
`--include optional`); answered "I don't know" earlier (without `--include deferred`); a kind with no plain
wording; for information only; about something no record field holds; about how the data files are laid out;
answered at once by a beamtime-wide question the site does not ask; an optional field asked once per
measurement; a card whose calls a dry run refuses; and a per-group question that a beamtime-wide card settles
(found by recording a probe answer on a throwaway copy of `bundle.json`), so the same thing is not asked twice.

The export also writes to the bundle's `exposures` log, under `bundle site export`: the parser values the cards
show, as `bundle questions` records the ones it prints. Nothing else in the bundle changes.

### `--suggestions <file>`: two shapes

A file may be a list of entries, `{"suggestions": [...]}`, or a map from question id to suggestion. An entry
is in one of two shapes.

The contract's own:

```jsonc
{"question_id": "Q-5a4bd3a297", "suggestion": { /* value, label?, confidence, basis, reason, evidence */ }}
{"field": "sample.sample_form", "applies_to": "ZZ1", "suggestion": { /* … */ }}
// applies_to: "all" (or absent): every card of that field; a sample name as the files write it; one file
// name; or a list of file names that names every file the card is about
```

A reading audit's (what a quote-checked reading of the whole folder writes):

```jsonc
{
  "field": "sample.material.name",            // "a / b" names two fields; "processing: …" or "grouping: …" is no record field
  "applies_to": {"sample_token": "ZZ1", "electrodes": ["01"], "group_ids": ["rg-…"], "files": ["…"]},   // or "beamtime…"
  "question_ids": ["Q-…"],
  "suggested_value": "…",                      // -> suggestion.value
  "alternatives": ["…"],
  "confidence": "high",                        // high | medium | low
  "evidence": [{"quote": "…", "file": "…", "locator": "line 8"}],   // -> suggestion.evidence (the first three)
  "reasoning": "…",                            // -> suggestion.reason (its first two sentences, at most 320 characters)
  "general_knowledge_note": null               // not shown
}
```

Its basis is `reading`. An entry is matched to a card most specific first, and a card takes only the entries
of its best match: (1) one of `question_ids` is a question the card covers; (2) the field is the card's and
every group the card is about is in `applies_to.group_ids`; (3) the field is the card's and the entry is
beamtime-wide.

What a match becomes:

- a **suggestion**, when its value can be recorded with one click: a single value, on the field's list where
  the field has one (a word followed by a remark in brackets is read as the word). The accept call is dry-run
  like every other; a value the decide path refuses is not offered.
- **context** (a `quotes` item, labelled with what the reading suggests), when it cannot: a value off the
  field's list, a value with several parts, entries of one card that give different values, a value the decide
  path refuses, or a card whose files already give another value.
- An entry about no record field is context on the processing card it matches (the dose card when it speaks of
  beam damage or settling, or names `experiment:set_dose_reading` in `question_ids`; an approval card of a
  group it names): quotes only, never a suggestion.
- `alternatives` are the card's `answer.common` for a choice field (only values on the list), or are named in
  `detail` for a text field.
- A value with one part per record field (`{"name": …, "concentration_M": …}` on `…electrolyte`) is read for
  the card of each part; a value keyed by file name is read for the card of that one file.
- A suggestion that comes from a reading replaces "None of your files say." in the card's detail.
- An entry with `basis: "general_knowledge"` and `confidence: "high"`, a confidence or basis off the lists, no
  evidence quote at all, or (the contract's shape) a reason that is missing or holds a field path, a flag or an id
  is not used; the report says which and why.
- Entries matched by question id must between them name every question the card answers; otherwise they are
  context ("read for only some of these measurements"). The suggestion takes the lowest confidence of the
  entries that offer it.
- `high` is kept only when one of the quotes holds the value itself (as written, in words, as the option's
  label, or as one of the entry's optional `synonyms`); otherwise the card says `medium` at most.

A value the files give, which a card confirms as it stands (`basis: "files"`), is never replaced by an entry.

AI readings loaded into the bundle (`isaac bundle annotate --from-readings`) become suggestions too, with no
file: `basis: "reading"`, the reading's quote as evidence, `confidence: "medium"` when the reading says the
quoted line states the value and `"low"` when it infers it. Only when every question of the card carries the
same reading; a reading of some of a card's measurements is not offered for all of them.

### The import's outcomes

Each answer ends as one of: `recorded` (preview: `would_record`), `vocabulary_request_kept` (preview:
`would_keep_vocabulary_request`), `already_recorded`, `refused` (with the decide path's own reason),
`no_longer_asked`, `nothing_to_record` (a "no", or an "I don't know" on a card that takes none), `held` (a note on
a card for several measurements, above), `superseded` (an earlier answer to a card answered again in the same
file). Two answers to one card: the later `at` wins.
The decision's note is `question site card <card_id> "<title>", answered <at>`; an answer already recorded is
recognised by that note and the name, so a second run writes nothing.

### The site template copy

`--site-template` (default: the repository's `apps/question-site/`) is copied into `--out` so the folder
deploys as it is. Never copied: a top-level `data/`, `test/`, `dev-server.js`, `.dev-store.json`, `.impeccable/`
and `README.md`; at any depth, `.vercel/`, `node_modules/`, `.git/` and every `.env*` file (one can hold the
site's password); and every path the template's own `.vercelignore` lists. When the template does not exist only `data/` is written, and the report says so.
