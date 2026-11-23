# Command cheat sheet (exact flags)

Look a command up here; the step's own reference file says when and how to use it.
`<isaac>` and `<python>` are the commands found in Step 0. Bundle commands print JSON.
Every list returns one page (`--limit` at most 200): follow its `more` line until none is left.

## Read and look

| Purpose | Command |
|---|---|
| Read a folder or ZIP | `<isaac> import <folder> --out <bundle> [--profile auto\|<id>] [--force] [--record-local-root]` |
| Is the bundle sound | `<isaac> bundle check <bundle>` |
| Where things stand (start of a later session) | `<isaac> bundle status <bundle> [--json]` (reads only; no file value) |
| Record the scientist's consent and name | `<isaac> bundle consent <bundle> --by "<name>" [--withdraw] [--note "<their words>"]` |
| A page of items | `<isaac> bundle list <bundle> runs\|conflicts\|candidates\|questions\|unread\|groups\|merge-candidates\|processed-outputs\|processing-results\|scan-notes [--limit N] [--offset M] [--state S] [--no-values] [--all]` |
| One item | `<isaac> bundle show <bundle> run\|conflict\|candidate\|source\|question\|group\|merge-candidate\|processed-output\|processing-result <id> [--full]` |
| Pull text and images out of a document | `<python> -m isaac_api.local_import.extract <file> --out <dir> [--root <folder>] [--sheet <name> --rows-offset N --rows-limit M] [--show-limits] [--blocks]` |

- `import --force` overwrites the bundle files in a used `--out`: every answer and approval in it is lost. Never offer it for a bundle that holds decisions (Step 2).
- `list --state`: for `candidates` (value state) and `processing-results` (`needs_review`, `scientist_confirmed`, `rejected`).
- `list --no-values`: `candidates` only; lists them without printing, so without exposing, any value.
- `list --all`: `groups` adds rejected, merged and split ones; `merge-candidates` those that propose nothing; `processing-results` the results of groups that no longer exist or are not live; `unread` the files a run reader kept beside a run without opening them.
- `unread` is the files no reader claimed. Athena projects are listed there as files; nothing ever reads them.
- `show` prints values. `show question` takes the `Q-…` ids `bundle questions` prints; an answered one shows who answered and when (`current_answers`).
- `show source`: which reader read the file and what it gave.
- `show processing-result --full`: every scan row and metric.

## Cross-check and readings (Steps 3–4)

| Purpose | Command |
|---|---|
| What to cross-check | `<isaac> bundle crosscheck-plan <bundle> [--limit N] [--offset M]` (ids and locators, no values) |
| Raw source text at a target | `<isaac> bundle excerpt <bundle> <id> [--source <folder>]` (no parser value) |
| Record one AI reading | `<isaac> bundle annotate <bundle> --target <id> --value <text> [--json] --excerpt-locator "<where>" [--source-id <src>] --model "<model name>" [--blind] --rationale "<why>"` |
| Show the parser value, compare | `<isaac> bundle reveal <bundle> <id>` (marks the target as seen) |
| Check a findings file's quotes | `<isaac> bundle check-readings <bundle> <file> --root <folder>` (reads only; exit 1 when a quote was not found) |
| Load a findings file | `<isaac> bundle annotate <bundle> --from-readings <file> --model "<model name>" --root <folder> [--apply]` (preview unless `--apply`) |
| Scan notes that were loaded | `<isaac> bundle list <bundle> scan-notes` |

- A reading that says the files state nothing ("not stated", "unknown") is refused: record nothing then.
- `--apply` records no finding whose quote was not found, whose run is unknown, or whose value is off its list.

## Groups and processing (Steps 5–6)

| Purpose | Command |
|---|---|
| Propose groups | `<isaac> bundle group <bundle> [--regroup]` |
| Process spectra (draft protocol) | `<isaac> process <bundle> --source <folder> [--group <id> ...] [--params-file <json>]` |

- `process` writes `processing/`. Without a readable `--source` it exits 2 and writes nothing.
- `--group` redoes only the named groups and keeps the others.

## Questions and answers (Step 7)

| Purpose | Command |
|---|---|
| The questions (use these) | `<isaac> bundle questions <bundle> [--scope experiment\|group:<id>\|run:<id>] [--blocking-only] [--distinguishing-only] [--limit N] [--offset M] [--skip-deferred] [--with-targets] [--include-outside-live-groups] [--each-group] [--no-context]` |
| A decision | `<isaac> bundle decide <bundle> (--target <id> [--target <id> ...] \| --targets-file <file> \| --question <Q> [--only group:<id> ...] [--field <path>] [--same-reading]) --decision <d> [--value <v> [--as-said]] [--json] --by "<name>" [--orcid 0000-0000-0000-0000] [--note "<text>"]` |
| …more `decide` flags | `[--split-into '<json of run keys>'] [--merge-with <group ids> [--same-conditions]] [--qc-status <word> [--qc-note "<text>"]] [--element <symbol> --edge <edge> [--accept-shift <eV>]] [--scans "<scan id>,..."] [--positions N,N or last] [--same-sample [--names-differ-ok]] [--from-earlier-answer <entry id>]` |
| The metadata template | `<isaac> bundle template export <bundle> --out <file.xlsx> [--force] [--no-suggestions] [--json]` · `<isaac> bundle template import <bundle> <file.xlsx> --by "<name>" [--orcid ...] [--apply] [--supersede] [--full] [--json]` · `<isaac> bundle template adopt <bundle> <their.xlsx> --out <file.xlsx> [--by "<name>"] [--force] [--no-suggestions] [--json]` |
| A filled question workbook | `<isaac> bundle answers import <bundle> <workbook.xlsx> --by "<name>" [--orcid <id>] [--folder <name> [--folder-differs-ok]] [--supersede] [--apply] [--json]` |
| The question site: the cards | `<isaac> bundle site export <bundle> --out <folder> [--suggestions <file>] [--include optional] [--include deferred] [--include approvals] [--site-template <folder>] [--json]` (`<folder>` outside every git repository and the bundle folder; see `question-site.md`) |
| The question site: its answers | `<isaac> bundle site import <bundle> <answers.json> --site-data <folder>/data/site-data.json [--apply] [--remember] [--note-read <card id>] [--json]` (preview unless `--apply`; refused in a `_runs…` folder) |
| Words outside the vocabulary | `<isaac> bundle propose-terms <bundle> [--out <file.json>] [--force \| --merge]` (prints values, sends nothing) |
| Earlier answers (opt-in) | `<isaac> answer-memory on --by "<name>"` · `off` · `status` · `list [--field <path>] [--beamtime <folder name>]` · `forget (--entry <id> \| --beamtime <folder name> \| --all)` · `learn <bundle> --by "<name>"` |

Rules of `decide`:

- It refuses a value the field cannot hold, records nothing, and lists the allowed values.
- A bulk call (several targets, a targets file, `--same-reading`, several `--only`) is all or nothing. A refusal names every refused target and why.
- With `--question`, only a decision in that question's `allowed_decisions`.
- `--qc-status` only with a processing result and `approve`.
- Every `--out` of `template` and `propose-terms` goes in `<bundle>-notes/`.

Decisions by target:

- **A value, a missing value, a conflict:** `confirm` · `correct` · `reject` · `defer`. `confirm` and `correct` on a conflict or missing value need `--value`.
- **A record group:** `confirm` · `split` (`--split-into`) · `merge` (`--merge-with`, `--same-conditions`) · `reject` · `defer` · `set_role` (`--value sample|reference|alignment`) · `set_absorber` (needs `--element` and `--edge`) · `set_scan_decision` (`--value keep|drop` with `--scans`) · `set_dose_reading` (`--value beam_damage|first_scan_settling|not_beam_damage`) · `approve_calibration` (needs `--element` and `--edge`; a shift above 2 eV also needs `--accept-shift <the shift shown>`, e.g. `--accept-shift -8.6`, else refused with nothing recorded).
- **A merge candidate (`mc-…`):** `keep_apart`.
- **The beamtime (`--target experiment`):** `set_counter_positions` (`--positions`) · `set_not_counter_positions` (`--positions`) · `defer` ("I don't know" to the counter question; no `--value`) · `set_clock_time_zone` (`--value` an IANA name such as Area/Location, or `UTC`) · `set_dose_reading`.
- **A processing result:** `approve` (always with `--qc-status valid|compromised|failed|pending`) · `reject` · `needs_changes` · `defer`.

## Build, validate, export (Steps 8–9)

| Purpose | Command |
|---|---|
| Compose drafts | `<isaac> bundle build-records <bundle> [--full]` |
| Every check, per draft | `<isaac> bundle validate <bundle> [--full]` |
| Write the passing records | `<isaac> bundle export <bundle> --out <records> [--full] [--allow-indistinguishable --by "<name>"]` |
| What would be uploaded | `<isaac> bundle upload <records> --dry-run [--portal-url <url>] [--full]` |

- `build-records`: counts and the first 3 drafts; `--full` prints every row. Never `--test-marker`: it is for self-tests only.
- `validate`: `by_reason`, `missing_required_by_field`, `not_exportable_first`, `pending_vocabulary`, then `verdicts`. `warnings` shows the first 5, exportable groups' first (`group_exportable`), with `warnings_total` and `warnings_full_list`: `validate --full` lists all.
- `export`: safe to repeat. An unchanged record keeps its id. A changed one gets a new id; the old one moves to `<records>/isaac-export/superseded/`. One whose group is no longer exportable moves to `<records>/isaac-export/withdrawn/`. `exported[].warnings` lists a record's warnings that still apply; `records_written_with_warnings` counts records written now, `records_ready_with_warnings` every ready one.
- `upload` without `--dry-run` is refused (exit 2). Nothing is ever sent.

Exit codes: 0 ok · 1 not valid / not exportable (validate, export, check) · 2 usage or a refused decision · 3 input
refused · 4 output refused · 5 bounds exceeded, or the change would leave the bundle invalid (nothing written) · 6 not found.
