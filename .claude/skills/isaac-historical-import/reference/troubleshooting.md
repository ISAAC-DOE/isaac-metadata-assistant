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
| `excerpt` refused: file changed | "The original file changed since import." | re-import into a new folder |
| `decide` exit 2 | "That decision isn't allowed for this item." | read the allowed list in the message; for conflicts/missing values give `--value` |
| process unavailable | "Curves and quality checks need an extra install." | `scripts/setup_isaac_local.sh --with-processing`; continue without it |
| validate exit 1 | "Some records aren't ready; here is why." | Step 8 table |
| the bundle folder looks inconsistent | "Something in the working folder doesn't add up." | `<isaac> bundle check <bundle>`; exit 1 prints exactly what is wrong |
| the scientist asks to upload | "This build can only show what would be sent. Upload through the ISAAC portal." | `upload --dry-run` only |

Never retry a refused command with a flag that weakens a check. If something is unexpected, show the
exact message and ask the scientist how to proceed.
