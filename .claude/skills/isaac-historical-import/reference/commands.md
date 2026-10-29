# Command cheat sheet (exact flags)

`<isaac>` is the command found in Step 0. Bundle commands print JSON; exit codes below.

| Purpose | Command |
|---|---|
| Read a folder or ZIP | `<isaac> import <folder> --out <bundle> [--profile auto\|<id>] [--force] [--record-local-root]` |
| A page of items | `<isaac> bundle list <bundle> runs\|conflicts\|candidates\|questions\|unread [--limit N] [--offset M] [--state S] [--no-values]` |
| One item | `<isaac> bundle show <bundle> run\|conflict\|candidate\|source\|question <id>` (prints values) |
| Re-validate the bundle itself | `<isaac> bundle check <bundle>` |
| What to cross-check | `<isaac> bundle crosscheck-plan <bundle> [--limit N] [--offset M]` (ids and locators, no values) |
| Raw source text at a target | `<isaac> bundle excerpt <bundle> <id> [--source <folder>]` (no parser value; needs the original folder) |
| Record an AI reading | `<isaac> bundle annotate <bundle> --target <id> --value <text> [--json] --excerpt-locator "<where>" [--source-id <src>] --model "<model name>" [--blind] --rationale "<why>"` |
| Show the parser value, compare | `<isaac> bundle reveal <bundle> <id>` (marks the target as exposed) |
| Consolidated questions (use these) | `<isaac> bundle questions <bundle> [--scope experiment\|group:<id>\|run:<id>] [--blocking-only] [--limit N] [--offset M]` |
| Scientist decision | `<isaac> bundle decide <bundle> (--target <id> \| --targets-file <file> \| --question <Q> [--only group:<id>] [--field <path>]) --decision <d> [--value <v>] [--json] --by "<name>" [--orcid 0000-0000-0000-0000] [--note "<text>"] [--split-into '<json>'] [--merge-with <group ids>] [--qc-status <word> [--qc-note "<text>"]] [--element <symbol> --edge <edge>] [--positions N,N]` (`--qc-status` only with a processing result and `approve`; `--element`/`--edge` only with a record group and `approve_calibration` (the calibration reference) or `set_absorber` (the absorber); with `--question`, only a decision in that question's `allowed_decisions`) |
| Metadata template | `<isaac> bundle template export <bundle> --out <file.xlsx> [--force] [--no-suggestions]`; `<isaac> bundle template import <bundle> <file.xlsx> --by "<name>" [--orcid ...] [--apply] [--supersede] [--json]` (preview unless `--apply`) |
| Group runs into records | `<isaac> bundle group <bundle> [--regroup]` (proposes groups inside the bundle) |
| See the groups | `<isaac> bundle list <bundle> groups [--limit N] [--offset M]` · `<isaac> bundle list <bundle> merge-candidates` · `<isaac> bundle show <bundle> group <id>` |
| Process spectra (draft protocol) | `<isaac> process <bundle> --source <folder> [--group <id> ...] [--no-athena] [--params-file <json>]` (writes `processing/`) |
| Compose drafts | `<isaac> bundle build-records <bundle>` (never `--test-marker`: self-tests only) |
| All gates, per draft | `<isaac> bundle validate <bundle>` |
| Write passing records | `<isaac> bundle export <bundle> --out <records>` |
| What would be uploaded | `<isaac> bundle upload <records> --dry-run [--portal-url <url>]` |
| Pull text and images out of a document | `python -m isaac_api.local_import.extract <file> --out <dir> [--root <folder>]` or `--from-bundle <bundle>/unread_files.json --root <folder> [--limit N]` |

Decisions by target kind: candidate / missing value / conflict: `confirm` `correct` `reject` `defer`;
record group: `confirm` `split` `merge` `reject` `defer` `approve_calibration` (needs `--element` and `--edge`), `set_absorber` (needs `--element` and `--edge`; changes nothing else about the group); the experiment (`--target experiment`): `set_counter_positions` (needs `--positions`); processing result: `approve` (always with `--qc-status`) `reject`
`needs_changes` `defer`. `confirm` and `correct` on a conflict or missing value need `--value`.

Exit codes: 0 ok · 1 not valid / not exportable (validate, export, check) · 2 usage or refused
decision (upload without --dry-run is also 2) · 3 input refused · 4 output refused · 5 bounds
exceeded, or the change would leave the bundle invalid (nothing written) · 6 not found.
