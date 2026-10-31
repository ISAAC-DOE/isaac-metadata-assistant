# Blind cross-check (Step 3)

Purpose: get an independent reading of high-value facts BEFORE you see what the code extracted, so a
code error can be caught instead of echoed. It is a spot check, never a verification.

## Order (do not reorder)

1. `crosscheck-plan <bundle> --limit 30` — ids, categories and file locators. No values.
2. Choose targets: sample identity, potential/reference basis, reaction, environment, cell type,
   acquisition time (these six are the **high-value categories**; the plan lists them as
   `high_value_categories`). Prefer ones with several sources. Tell the scientist how many you will check.
   The plan's `high_value_total` is the denominator M: the items in those six categories that can be read
   blind (`excerptable: true`). `total` is larger (it also counts run-association, HERFD signal-choice and
   required-but-missing items), so never report `total` as the number of high-value items.
   Items carry `field_path`, `excerptable`, `locators` (at most 5) and `locators_total`, high-value
   items first. Only `excerptable: true` items can be read blind; a missing value (`excerptable: false`)
   has no source text, so it goes to the scientist as a question, never into the cross-check count.
3. For each target: `excerpt <bundle> <id> --source <folder>` — the raw source text at that locator. For a reading taken from a file name
   (`filename token N`) it shows the file name and which token, not the file's lines.
4. Read it. Write down what YOU read (a short value and the quote's locator).
5. `annotate <bundle> --target <id> --value "<your reading>" --excerpt-locator "<where>" --source-id <src> --model "<your model name>" --blind --rationale "<one line>"`.
   `--source-id` must be a source the excerpt showed (a target whose locators name sources refuses
   any other, exit 2); a target with no source locators takes any known source.
6. Only after annotating: `reveal <bundle> <id>` and compare (`agrees_with_parser` and `relation`: the same number, the same
   instant written two ways, or the same string agree; anything else differs). For a numeric field, a
   reading given as text (`--value "0.4"` without `--json`) is compared as the number it parses as, and
   says so (`compared_as: number`, `comparison_note`); prefer `--value 0.4 --json` for numbers. When the
   parser holds no value for the target (a missing value, a value-less candidate), `agrees_with_parser` and
   `relation` are null and `comparison_note` says there is nothing to compare: say "not comparable", never
   "agrees". A SCAN START TIME (the plan marks it `compared_as: local clock time` with a `read_note`) has no
   UTC value until the clock's zone is stated, but it IS compared: write the earliest scan's line-2 time as the
   header writes it or as `YYYY-MM-DDTHH:MM:SS`, no zone; `reveal` holds it against the header's local clock
   time (`parser.local_clock_start`) in any spelling, says when it is another scan's time, and gives null for a
   reading that names a zone or offset. Agreement, difference or not
   comparable — say which, in plain words. A difference is a question for the scientist, never
   something you settle.

## Honesty rules

- `--blind` counts only if no command had printed that target's value. If `annotate` stores
  `blind: false`, say so; do not call it blind.
- Never open `bundle.json`, `runs.json`, `reading.full.json`, `record_groups.json` or
  `processing_results.json` (SKILL.md Rule 8); the tool cannot see that, and a blind claim is only as
  good as your discipline.
- `summary.md` shows no parser value except in conflicts. Conflicts are therefore never blind.
- Report: "checked N of M high-value items (K blind); the rest were not examined." M is `high_value_total`;
  N and K are `coverage.high_value_checked` and `coverage.high_value_blind_checked` (a reading of an item outside
  the six categories is real, but is in neither number); `coverage.high_value_statement` words it.
- An AI reading never lifts a value above "needs review".
