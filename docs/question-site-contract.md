# The question site: data contract (v1.0.0)

A scientist answers a bundle's open questions on a small hosted site, a few at a time. Three pieces share two
files:

1. `isaac bundle site export <bundle_dir> --out <dir>` writes `<dir>/data/site-data.json` and `<dir>/data/img/*.png`
   (and copies the site's source beside them, so `<dir>` deploys as it is).
2. The site (`apps/question-site/`) shows the cards behind a password and a name, and stores each answer as it is
   clicked. Anyone signed in can download `answers.json`.
3. `isaac bundle site import <bundle_dir> <answers.json> --site-data <dir>/data/site-data.json` turns the answers
   into `bundle decide` calls. Preview is the default; `--apply` records them.

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
  "card_id": "C-1a2b3c4d5e",           // stable: sha256 of the field path + the sorted covered question ids, 10 hex
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
