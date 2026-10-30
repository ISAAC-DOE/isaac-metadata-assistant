# Troubleshooting

| What happened | Say | Do |
|---|---|---|
| `isaac` not found / "need the ISAAC local import package" | "ISAAC isn't set up on this computer yet." | give: `scripts/setup_isaac_local.sh` from the ISAAC folder |
| import exit 3 | "I can't read that folder (not found, a shortcut, or no permission)." | ask for the real folder path; never follow shortcuts |
| import exit 4 | "The output folder isn't empty or is inside your data." | choose a new, empty folder outside the data; `--force` only if they ask |
| import exit 5 | "ISAAC read the files but could not make a valid summary of them." | run `<isaac> import` again for the message; report the exact message to the ISAAC team; do not retry blindly |
| a beamtime with 0 runs | "No reader for these file types yet; N files were left unread." | go to Step 4 for what can be read; generic readers run automatically where present |
| `bundle show` / `excerpt` exit 6 | "That item doesn't exist in this bundle." | list again; ids change only when you re-import |
| a mutation exit 5 | "That change would leave the summary invalid, so nothing was saved." | read the message; fix the cause (usually a missing value with a decision) |
| `excerpt` exits 0 but its reply has `"refused"` (file changed, no longer in the folder, or inside a nested ZIP) | "I can't show that file's text: <the reason in its words>." | for a changed file, re-import into a new folder; otherwise read it another way (Step 4) |
| `decide` exit 2 | "That decision isn't allowed for this item." | read the allowed list in the message; for conflicts/missing values give `--value` |
| `decide` exit 2: "not one of the schema's allowed values" | "That answer isn't one the record can hold." | show the allowed values it lists, map their words to one, say it back, and ask; nothing was recorded |
| `decide` exit 2: merge "needs --merge-with" or "names no record group" | "I need to know which group to merge it with." | list the groups again and name a live one |
| `process` exit 2: "Pass --source" | "ISAAC needs the original folder to read the scans." | run it again with `--source <the imported folder>`; nothing was written |
| `setup_isaac_local.sh` says the installed skill differs from the ISAAC folder's | "My instructions here are out of date." | `scripts/setup_isaac_local.sh --install-skill` from the ISAAC folder, then restart Claude Code |
| `process` exit 2: "processing not installed (processing_unavailable)" | "Curves and quality checks need an extra install." | `scripts/setup_isaac_local.sh --with-processing`; continue without it |
| `process` exit 2: "is a ZIP file" | "Processing reads the scans from a folder, not a ZIP." | unzip it (outside the bundle), then `--source <the unzipped folder>` |
| validate exit 1 | "Some records aren't ready; here is why." | Step 8 table |
| validate exit 1 with `nothing_validated` | "There's nothing to check yet: no group is confirmed." | Step 5 (confirm groups), then `build-records` |
| `bundle check` prints `STALE` (exit 1) | "This working folder was made by an older ISAAC; it is not broken." | `<isaac> bundle build-records <bundle>` re-derives it and logs what changed; say how many values it lists |
| any command exit 2: "The bundle changed since it was read" | "Something else (often the Local Imports page) changed it a moment ago; nothing was saved." | run `bundle questions` again, then repeat the answer if it still applies |
| `import --profile` exit 2 | "That reading profile doesn't exist." | drop `--profile` (the default `auto` chooses) |
| the bundle folder looks inconsistent | "Something in the working folder doesn't add up." | `<isaac> bundle check <bundle>`; exit 1 prints exactly what is wrong |
| the scientist asks to upload | "This build can only show what would be sent. Upload through the ISAAC portal." | `upload --dry-run` only |

Never retry a refused command with a flag that weakens a check, and never pass `process --params-file`
on your own to loosen a quality threshold: a changed parameter is the scientist's protocol decision,
made explicitly after `needs_changes`, never a way past a refusal. If something is unexpected, show the
exact message and ask the scientist how to proceed.
